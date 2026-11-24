---
title: "DE 系統設計面試指南 Part 13：Schema 演進——契約、相容性與變更流程"
date: 2026-11-24T10:30:00+08:00
draft: false
weight: 13
description: "Schema 變更的難處不在改欄位，而在 30 個下游誰先升級。講清楚各類變更的安全性、BACKWARD/FORWARD/FULL 相容模式、Avro 與 Protobuf 的解析規則、Iceberg 欄位 ID，以及 expand–contract 等變更策略。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Schema Evolution", "Schema Registry", "Avro", "Protobuf", "Iceberg", "Data Contracts", "AWS"]
authors: ["yen"]
readTime: "16 min"
series: ["de-system-design-interview"]
---

> 多數人談 schema 演進，答案是「上 schema registry，規定只能加欄位」。  
> 面試官接著問：「那改名呢？金額從分改成元呢？30 個下游作業誰先改？」答案就斷了。  
> Registry 只檢查**結構**；最貴的事故是結構完全相容、**語意**卻變了的那一種。  
> 好的回答把 schema 當成契約來管：分類變更、決定升級順序、用 expand–contract 讓新舊並存，再用對帳證明沒有算錯。

這是「策略深入」組的第四篇，展開 [Part 5](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/) 模擬面試中那句「Schema 之後會變，你怎麼處理？」。[Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/) 講過「只做加可為空欄位的變更」這條基本規則，[Part 4](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/) 講過 Iceberg 以 ID 追蹤欄位。本篇處理基本規則擋不住的情況：改名、改型別、改語意，以及一個生產者對應幾十個消費者時的變更流程。

---

## 面試情境

> **面試官**：「我們的 `order_completed` 事件每天約 2,000 萬筆，有 30 個下游作業在讀，包括營收報表、對帳、推薦特徵與財務月結。產品團隊下個月要做兩件事：把欄位 `amt` 改名為 `amount`，並把它從整數的『分』改成兩位小數的『元』。請設計這次變更的流程，確保沒有任何一個下游在過程中算錯或停擺。」

---

## 一、核心問題：schema 是一份有多個簽約方的契約

一個 schema 描述的是生產者與每一個消費者之間的約定：欄位叫什麼、型別是什麼、**數值代表什麼**。生產者只有一個，消費者有 N 個，而且他們不會同時部署。所以 schema 演進真正要回答的是：

1. **這個變更屬於哪一類？** 有些變更對所有人都安全，有些只對先升級的一方安全，有些對誰都不安全。
2. **誰必須先升級？** 生產者先，還是消費者先？
3. **舊資料怎麼辦？** Kafka 保留 7 天、資料湖保留 2 年；新程式碼要能讀兩年前寫下的檔案。
4. **怎麼證明沒算錯？** 結構相容不代表數字正確。

先把常見的變更分類。下表的「相容方向」以 Avro 加上 schema registry 的規則為準；第四節再說明 Protobuf 與 JSON 的差異。

| 變更 | 例子 | 新讀者讀舊資料 | 舊讀者讀新資料 | 判定 |
|---|---|---|---|---|
| 加欄位，有預設值 | 加 `coupon_id`，預設 null | 可，補預設值 | 可，忽略新欄位 | 安全（FULL） |
| 加欄位，無預設值 | 加必填 `channel` | 失敗，舊資料沒有這欄 | 可，忽略 | 只有 FORWARD |
| 刪欄位，原本有預設值 | 刪 `legacy_flag` | 可，忽略 | 可，補預設值 | 安全（FULL） |
| 刪欄位，原本無預設值 | 刪必填 `amt` | 可，忽略 | 失敗，舊讀者找不到 | 只有 BACKWARD |
| 改名 | `amt` → `amount` | 等同刪一個加一個；Avro 讀者可用 `aliases` 對回舊名 | 失敗或讀到 null | 破壞性 |
| 型別放寬 | `int` → `long` | 可，Avro 允許提升 | 失敗，`int` 裝不下 `long` | 只有 BACKWARD |
| 型別收窄 | `long` → `int` | 失敗 | 可，但可能截斷 | 視為破壞性 |
| 同型別改語意 | 分 → 元，仍是 `long` | 可 | 可 | **Registry 全部放行，最危險** |
| 巢狀 struct 加欄位 | `shipping.zip` | 規則同頂層 | 規則同頂層 | 結構上同上；部分查詢引擎對 struct 內部變更支援較差 |
| enum 加值 | `status` 加 `REFUNDED` | 可 | 舊讀者遇到未知值會失敗，除非 reader 的 enum 宣告了 `default` | 只有 BACKWARD |

這張表有兩個面試時要主動說出的結論：

- **改名與改語意不是「一個變更」**，而是一次遷移。它們沒有任何相容模式能直接放行（改名）或擋下（改語意）。
- **「相容」永遠有方向**。說一個變更相容，必須接著說「對誰相容」，那就是下一個問題：誰先升級。

---

## 二、三個演進階段

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Schema-on-read (POC, 1 producer team, < 5 consumers)       ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐ JSON  ┌──────────┐      ┌──────────────┐     ┌──────────┐
│ App      │──────▶│ Kinesis/ │─────▶│ S3 raw JSON  │────▶│ Glue     │
│ producer │       │ Firehose │      │ dt=...       │     │ crawler  │
└──────────┘       └──────────┘      └──────────────┘     └────┬─────┘
                                                               ▼
                                                   Athena / Spark reads
                                                   whatever it finds
```

**作法**：生產者送 JSON，原樣落地，由 crawler 推斷 schema。沒有任何地方檢查欄位。

**優點**：零設定，生產者可以隨意加欄位，原始資料一個 byte 都不會丟。

**仍存在的問題**：變更的後果出現在查詢時，而且通常是隔天早上。crawler 可能因為某天全是整數就把 `price` 推成 `bigint`、隔天又看到小數；各分區的 schema 不一致時，Athena 查詢會報 `HIVE_PARTITION_SCHEMA_MISMATCH`。改名則完全不會報錯，只是新欄位在舊分區、舊欄位在新分區都變成 null。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  Registry-enforced at ingestion (MVP, 5-30 consumers)       ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────┐ Avro + schema id ┌────────────┐   ┌──────────────────┐
│ Producer     │─────────────────▶│ Kafka (MSK)│──▶│ Bronze: raw Avro │
│ (serializer) │                  └─────┬──────┘   │ kept as-is       │
└──┬───────────┘                        │          └────────┬─────────┘
   │ register new schema;               │ fails to          ▼
   │ rejected if incompatible           │ deserialize ┌──────────────┐
   ▼                                    ▼             │ Silver:      │
┌────────────────────┐           ┌──────────────┐     │ Iceberg,     │
│ Schema registry    │           │ quarantine   │     │ typed cols   │
│ compat = FULL      │           │ topic + alert│     └──────────────┘
└────────────────────┘           └──────────────┘
```

**新增元件**：schema registry（Confluent Schema Registry，或不另收費的 AWS Glue Schema Registry）、Avro 序列化、Iceberg 銀層、隔離 topic。

**解決**：不相容的 schema 在**生產者註冊時**就被拒絕，而不是在下游讀取時才爆；Iceberg 以欄位 ID 追蹤，加欄位、改名不必重寫歷史檔案。

**成本／複雜度**：registry 本身便宜，代價在於每個生產者都要接序列化器，而且生產者團隊第一次被擋下時會抱怨。

**仍存在的問題**：registry 管不到語意；它也不知道誰在讀這個欄位，所以一個「相容」的刪除照樣可能弄壞某張報表。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Data contracts + CI + lineage (Scale, 30+ consumers)       ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────────┐  PR  ┌──────────────────────────────────────────┐
│ contract.yaml    │─────▶│ CI: 1) registry compat check (transitive)│
│ schema + owner + │      │     2) semantic rules (unit, range, enum)│
│ semver + SLA     │      │     3) lineage: list affected consumers  │
└──────────────────┘      │     4) MAJOR bump needs consumer sign-off│
                          └────────────────────┬─────────────────────┘
                                               ▼ merge
                ┌───────────────────────────────────────────────────┐
                │ Runtime: expand-contract, deprecation dates,      │
                │ reconciliation checks old field vs new field      │
                └───────────────────────────────────────────────────┘
```

**新增元件**：版本控制中的契約檔（schema 加上負責人、單位、值域、版本號）、CI 檢查、欄位層級的血緣（lineage）、棄用流程。

**解決**：破壞性變更在 PR 階段就知道影響哪 30 個作業、誰要簽核；語意規則（例如「`amount` 單位為元、範圍 0–1,000,000」）讓單位改變至少有機會被擋下或被偵測。

**成本／複雜度**：需要一個平台團隊維護 CI 與血緣，每次破壞性變更從「改一行」變成以週計的遷移專案。這是刻意的：讓破壞性變更變貴，大家就會盡量設計成加法變更。

**仍存在的問題**：血緣只涵蓋登記過的消費者；有人用筆電直接查 S3 的話，CI 不會知道。

---

## 三、相容模式：誰必須先升級

Confluent Schema Registry 的相容模式定義的是：**新註冊的 schema 與既有版本之間，哪個方向必須讀得通**。記法是先問「新 schema 拿來做什麼」：

| 模式 | 定義 | 允許的變更（Avro） | 誰先升級 |
|---|---|---|---|
| `BACKWARD`（預設） | 用**新** schema 的消費者讀得了**舊** schema 寫的資料 | 刪欄位、加有預設值的欄位 | **消費者先** |
| `FORWARD` | 用**舊** schema 的消費者讀得了**新** schema 寫的資料 | 加欄位、刪有預設值的欄位 | **生產者先** |
| `FULL` | 兩個方向都要成立 | 只能加或刪有預設值的欄位 | 任意順序 |
| `NONE` | 不檢查 | 任何變更 | 自己協調 |

升級順序是從定義推出來的，不需要背：

```
BACKWARD: new reader can read old data
  t0  producer v1 ──writes v1──▶ topic ──▶ consumers v1
  t1  producer v1 ──writes v1──▶ topic ──▶ consumers v2   (v2 reads v1: OK)
  t2  producer v2 ──writes v2──▶ topic ──▶ consumers v2   (all on v2)
      => producer first would let v1 readers meet v2 data: not guaranteed

FORWARD: old reader can read new data
  t0  producer v1 ──writes v1──▶ topic ──▶ consumers v1
  t1  producer v2 ──writes v2──▶ topic ──▶ consumers v1   (v1 reads v2: OK)
  t2  producer v2 ──writes v2──▶ topic ──▶ consumers v2   (upgrade at leisure)
```

一個生產者、30 個消費者時，「消費者先」代表要等 30 個團隊都部署完，生產者才能開始寫新版本；「生產者先」只需要一個團隊動。所以一對多的事件串流比較適合 `FORWARD` 或 `FULL`：**生產者想改就能改，消費者照自己的節奏跟上**。反過來，當消費者只有一個（例如自家的 ETL）而生產者很多時，`BACKWARD` 比較順手。

**Transitive 變體**（`BACKWARD_TRANSITIVE`、`FORWARD_TRANSITIVE`、`FULL_TRANSITIVE`）把檢查範圍從「最新一版」擴大到「所有歷史版本」。差別出現在消費者需要重讀舊資料時：

```
v1: { order_id }
v2: { order_id, channel (default "web") }  BACKWARD vs v1: OK
v3: { order_id, channel (no default) }     vs v2: OK   (v2 data has it)
                                           vs v1: FAIL (v1 data lacks it)
```

非 transitive 模式只拿 v3 和 v2 比，會放行；但資料湖裡還有兩年前用 v1 寫的檔案，用 v3 去讀就會失敗。**只要有長期保留、會被重讀的資料（資料湖、compacted topic、重播），就用 transitive**。AWS Glue Schema Registry 的對應名稱是 `BACKWARD_ALL`、`FORWARD_ALL`、`FULL_ALL`。

設定與預檢都透過 REST API。CI 可以在合併前先問 registry「這個 schema 註冊得進去嗎」，而不是等生產者上線才被拒：

```bash
# 把 subject 設成 FULL_TRANSITIVE
curl -X PUT -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data '{"compatibility": "FULL_TRANSITIVE"}' \
  http://registry:8081/config/order_completed-value

# CI 預檢：依 subject 的模式比對（transitive 時比對所有版本）
# 回傳 {"is_compatible": true|false}
curl -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data @new_schema_payload.json \
  http://registry:8081/compatibility/subjects/order_completed-value/versions
```

---

## 四、格式本身的行為：Avro、Protobuf、JSON

Registry 的判定是建立在格式的解析規則上的，三種格式差很多。

**Avro：讀者與寫者 schema 解析。** Avro 的二進位資料不帶欄位名，讀取時需要兩份 schema：寫入時用的（writer schema，透過訊息前綴的 schema id 從 registry 取得）與讀者自己的（reader schema）。解析規則是：

- 依**欄位名**對應；寫者有、讀者沒有的欄位被略過。
- 讀者有、寫者沒有的欄位，用讀者的 `default`；沒有預設值就報錯。
- 允許的型別提升：`int → long / float / double`、`long → float / double`、`float → double`、`string ↔ bytes`。反方向不行，型別不符時會看到類似 `Found long, expecting int` 的錯誤。
- 讀者可以用 `aliases` 宣告舊名，讀舊資料時對回去；但舊讀者看不懂新名，所以改名仍然只是單向相容。

**Protobuf：以欄位編號為準。** 線上傳輸的是欄位編號，不是名稱，所以：

- 改名在二進位層面不影響相容性，但會改變 JSON 映射與產生的程式碼，消費者照樣要改。
- **刪除欄位後必須 `reserved` 它的編號與名稱**，否則有人重用編號 7 塞進別的型別，舊資料會被解讀成錯的值，而且不會報錯。
- proto3 的欄位都有零值，加刪欄位在線上大致相容；`int32`、`int64`、`uint32`、`uint64`、`bool` 在線上可互換，但大數會被截斷。Confluent 的文件建議 Protobuf 使用 `BACKWARD_TRANSITIVE`，原因是新增 message 型別並不是 forward 相容的。

```protobuf
message OrderCompleted {
  reserved 4;              // was: int64 amt = 4;  never reuse this number
  reserved "amt";
  string order_id = 1;
  string amount   = 5;     // decimal as string, e.g. "19.99"
  string currency = 6;     // ISO 4217
}
```

**JSON：格式本身沒有任何保證。** 不經 registry 的 JSON 什麼都能送：`"amount": 1999` 與 `"amount": "19.99"` 可以出現在同一個 topic。Confluent 也支援 JSON Schema 並做相容性檢查，但 JSON Schema 的開放／封閉內容模型（是否允許額外屬性）讓相容規則比 Avro 難推理。面試中說「JSON 加上驗證」可以，但要說明驗證點在哪裡，而且接受它比 Avro 鬆。

| 格式 | 欄位對應依據 | 改名 | 主要陷阱 |
|---|---|---|---|
| Avro | 名稱（加 aliases） | 讀者端可單向處理 | 忘了給預設值，新讀者讀不了舊資料 |
| Protobuf | 編號 | 線上相容，程式碼不相容 | 重用編號，靜默讀錯 |
| JSON（無 registry） | 名稱，無型別 | 靜默變 null | 同欄位多種型別，下游轉型失敗 |

---

## 五、落到表格之後：table format 與檔案層

訊息格式只管傳輸。資料進了湖以後，演進規則換成檔案格式與 table format 的規則，而這裡的陷阱更隱蔽，因為檔案會存好幾年。

**Parquet：每個檔案自帶 schema，引擎決定怎麼對應。** 檔尾 footer 記錄該檔的欄位。引擎讀取時有兩種對應方式：

```
 table now:        order_id | amount  | channel     (amt renamed to amount)
                      │          │         │
 file A (old):     order_id | amt     |  ─
   by NAME      -> amount = NULL                        (silent NULL)
   by POSITION  -> amount = amt                         (lucky)
 file B (older):   order_id | coupon  | amt          (coupon dropped later)
   by POSITION  -> amount = coupon, channel = amt     (silently wrong)
 Iceberg:          id 1     | id 2    | id 3         (rename keeps id 2)
   by FIELD ID  -> amount = value stored under id 2   (correct)
```

- **依名稱**：改名後舊檔案的該欄變成 null。Spark 與 Athena 讀 Parquet 預設依名稱。
- **依位置**：改名看似沒事，但只要刪掉中間一欄或調換順序，後面的欄位就整體錯位，而且型別剛好相容時不會報錯。Athena 讀 ORC 預設依位置，Hive 的 ORC 也有依位置的歷史行為。
- Spark 讀多個 schema 不同的 Parquet 檔時，`mergeSchema` 預設關閉，可能只採用其中一個檔案的 schema，新欄位就「不見了」。

**Iceberg：欄位 ID。** 每個欄位在建立時得到一個永不重用的 ID，資料檔記錄的是 ID。所以改名只改 metadata 中 ID 對應的名稱；刪除後再加回同名欄位會拿到新 ID，不會把舊資料讀回來；調換順序也安全。型別放寬支援 `int → long`、`float → double`、提高 decimal 的精度。**它不支援把 `long` 改成 `decimal`**——這正是情境中「分改成元」不能用 `ALTER COLUMN` 一步完成的原因。

**Delta Lake：column mapping。** 預設依名稱對應實體欄位。啟用 column mapping（`delta.columnMapping.mode = 'name'`）後，每個欄位有獨立的實體名稱，才能做 `RENAME COLUMN` 與 `DROP COLUMN` 而不重寫資料。較新的版本另外提供有限的型別放寬（type widening）功能，使用前要確認讀取端的引擎版本也支援。

**Hive Metastore / Glue Catalog：schema 存在兩層。** 表有一份 schema，**每個分區也各有一份**。`ALTER TABLE ADD COLUMNS` 預設只改表層級，舊分區保留舊 schema；Hive 需要加 `CASCADE` 才會一併更新分區。Athena 在表與分區 schema 不一致時，會出現前面提過的 `HIVE_PARTITION_SCHEMA_MISMATCH`，或是新欄位在舊分區讀成 null。這也是換到 Iceberg 的主要理由之一：Iceberg 的 schema 只有一份，存在表的 metadata 裡。

---

## 六、策略選單

沒有單一策略能處理所有變更。實務上是組合使用，下表列出每個策略的適用範圍與失效條件。

| 策略 | 怎麼做 | 優點 | 缺點／成本 | 何時選 | 何時失效 |
|---|---|---|---|---|---|
| Schema-on-read 原始落地 | Bronze 原樣保存所有欄位，下游讀時解釋 | 永不丟資料；之後可重新解析 | 錯誤延後到查詢時；每個讀者自己解釋，定義分歧 | 第三方或外部來源、無法控制生產者 | 下游多、需要一致定義時，必須再加一層強制 schema 的銀層 |
| 擷取時強制契約 | 生產者序列化時經 registry 檢查 | 不相容變更在源頭被擋 | 生產者要接 SDK；被擋時要有處理流程 | 自家服務產生的事件 | 擋不住語意變更 |
| 資料契約 + CI | schema、單位、值域、負責人放在版本控制，PR 時檢查 | 變更前就知道影響誰；語意規則可檢查 | 需要平台團隊與文化配合 | 消費者超過 10 個、跨團隊 | 契約沒涵蓋的消費者；規則寫得太鬆 |
| Expand–contract（平行變更） | 先加新欄位並雙寫，消費者逐一遷移，最後移除舊欄位 | 每一步都相容，可隨時暫停或回退 | 期間以週計；雙寫期間要對帳 | 改名、改型別、改單位 | 主鍵或分區鍵要改時，同一個 topic 內無法並存 |
| 版本化 topic／表（v2）+ 雙寫 | 另開 `orders.v2`，生產者兩邊都寫，消費者切換 | 新舊完全隔離，可大改 | 雙倍儲存；雙寫一致性；消費者易重複讀 | key、分區方式或粒度改變 | 雙寫沒做對帳時兩邊逐漸不一致 |
| 隔離區（DLQ／quarantine） | 解析或驗證失敗的紀錄寫到另一處並告警 | 管線不中斷、壞紀錄不丟 | 要有人處理隔離區，否則變成黑洞 | 任何會遇到不合格資料的入口 | 大量紀錄同時失敗（多半是 schema 變了），應該停下而不是全部隔離 |
| 相容性檢視 | 新表上建舊名稱與舊單位的 view | 未遷移的消費者完全不必改 | View 要記得移除；效能略差 | 倉儲端的改名與單位換算 | 消費者直接讀檔案而非經過 view |
| 資料集語意化版本 | MAJOR＝破壞性、MINOR＝加法、PATCH＝資料修正 | 消費者看版本號就知道要不要動 | 需要真的遵守 | 對外或跨部門發佈的資料集 | 沒有人檢查版本號與實際變更是否一致 |

隔離區那一列的「何時失效」值得展開。如果平常隔離率是 0.01%，某天突然變成 100%，代表的不是 2,000 萬筆壞資料，而是生產者部署了不相容的版本。這時應該**觸發斷路、停止消費並告警**，而不是把整天的資料都丟進隔離區，因為修好之後還得從隔離區重放全部資料。實作上就是設定一個隔離率門檻（例如 5 分鐘內超過 1% 就停）。Kafka Connect 的 sink connector 內建 `errors.tolerance=all` 與 `errors.deadletterqueue.topic.name`，但門檻判斷要自己加在監控上。

**上游是 OLTP 資料庫時（CDC）。** 用 Debezium 這類 CDC 連接器時，上游 DBA 的一個 `ALTER TABLE` 就是一次 schema 變更，而且事前通常沒人通知資料團隊。連接器讀到 DDL 後產生新版本的 schema 並嘗試註冊；如果相容模式不允許（例如 MySQL 把一個 `NOT NULL` 欄位改名，等於刪一個必填欄位再加一個），註冊失敗，connector task 停下，CDC 延遲開始上升。這其實是好的失敗方式。要防的是另一種：DBA 把欄位從 `INT` 改成 `BIGINT`、或把金額欄位的意義改了，registry 放行而下游沒人知道。對策是把資料庫 migration 也納入契約的 CI：遷移腳本的 PR 會觸發相同的影響分析。

**血緣與影響分析。** 「誰在讀 `amt`？」要能在一分鐘內回答。來源有三種：dbt 的模型相依（加上 dbt 的 model contract 可在 build 時強制欄位與型別）、OpenLineage 由 Spark／Airflow 回報的執行期血緣、以及查詢引擎的查詢日誌（例如掃描 Athena 的查詢歷史找出引用該欄位的查詢）。前兩者準確但只涵蓋已接入的作業；查詢日誌涵蓋臨時查詢，適合用來找「不在名單上的消費者」。

---

## 七、情境實作：改名加改單位，30 個下游

把題目拆開，它其實是三個變更疊在一起：改名（`amt` → `amount`）、改型別（`long` → `decimal`）、改單位（分 → 元）。任何一個單獨做都已經是破壞性變更，所以答案是 **expand–contract，而且新欄位一次到位**，不要分三次遷移。

先估算規模與成本（假設每筆事件 1 KB、Kafka 保留 7 天、3 副本、MSK 儲存約 $0.10/GB-月）：

```
events/day              = 20,000,000
extra fields            ≈ 16 B/event × 20M      ≈ 320 MB/day (negligible)

if we used a v2 topic instead (dual-write full events):
  extra raw/day         = 20M × 1 KB          = 20 GB
  extra on brokers      = 20 GB × 7 days × 3  = 420 GB
  extra storage cost    ≈ 420 GB × $0.10      ≈ $42 / month
consumer migration      = 30 jobs / ~5 per week ≈ 6 weeks of expand phase
```

成本不是決定因素，兩種做法每月都只差幾十美元。決定因素是**key 有沒有變**：這次 key 仍是 `order_id`、分區方式不變，所以同一個 topic 內的 expand–contract 就夠，不必讓 30 個消費者改訂閱的 topic。

```
 week 0       week 0-1          week 1-6               week 7-8       week 9+
 ──────┬────────────┬──────────────────────┬──────────────┬─────────────────▶
 EXPAND│ DUAL-WRITE │ MIGRATE consumers    │ DEPRECATE    │ CONTRACT
 add   │ producer   │ in waves (lineage    │ amt: readers │ drop amt
 new   │ fills both │ list), recon check   │ = 0 for 2 wk?│ (MAJOR bump),
 field │ fields     │ every hour           │ alert if not │ reserve name/id
 ──────┴────────────┴──────────────────────┴──────────────┴─────────────────
 compat: FULL_TRANSITIVE for weeks 0-7; BACKWARD_TRANSITIVE for the drop
```

**步驟一：Expand。** 只新增欄位，舊欄位 `amt` 一個字都不動。兩個新欄位都是可為空、有預設值，所以在 `FULL_TRANSITIVE` 下可以直接註冊：

```json
{"name": "amt",      "type": "long",
 "doc": "DEPRECATED 2026-12-01. Minor units (cents). Use amount + currency."},
{"name": "amount", "type": ["null", {"type": "bytes",
   "logicalType": "decimal", "precision": 18, "scale": 2}],
 "default": null, "doc": "Major units, e.g. 19.99"},
{"name": "currency", "type": ["null", "string"], "default": null,
 "doc": "ISO 4217"}
```

順手加上 `currency`。整數「分」假設每種貨幣都有兩位小數，但日圓沒有小數、有些貨幣有三位；既然都要改，就一次把單位講清楚。

一個常見的錯誤是「順便把 `amt` 改成 `["null","long"]`，方便之後刪除」。這在 Avro 不是 FORWARD 相容的：舊讀者的 `long` 讀不了寫者 union 中的 `null` 分支，registry 會拒絕。另一個錯誤是給 `amt` 加上 `"default": 0`：預設值本身相容，但萬一有作業還在讀 `amt`，之後讀到不含它的資料會得到 0 而不是報錯——營收靜默歸零。

**步驟二：雙寫與對帳。** 生產者同時填兩個欄位。從這一刻起，每小時執行一次對帳，門檻是零：

```sql
SELECT count(*) AS mismatches
FROM silver.order_completed
WHERE event_date = current_date
  AND amt IS NOT NULL
  AND (amount IS NULL OR CAST(amount * 100 AS BIGINT) <> amt);
-- expected 0; any row means the producer's conversion is wrong
-- (JPY etc. need currency-aware minor units: check by currency)
```

**步驟三：分批遷移消費者。** 從血緣拿到 30 個作業的清單，依風險排序：先遷移推薦特徵這類容錯高的，最後才是財務月結。倉儲端的消費者可以先不改程式，改讀一個相容性 view：

```sql
CREATE OR REPLACE VIEW gold.order_completed_v1_compat AS
SELECT order_id, CAST(amount * 100 AS BIGINT) AS amt, ...
FROM silver.order_completed;
```

每遷移一批，比對該作業新舊版本的輸出（例如每日營收差異應為 0），再進行下一批。

**步驟四：Contract。** 血緣與查詢日誌確認 `amt` 連續兩週無人讀取，而且所有消費者部署的 reader schema 都已不含 `amt` 之後，才移除舊欄位，資料集版本升 MAJOR。注意這一步依第一節的表是「刪除無預設值的欄位」，**只有 BACKWARD 相容**：新 schema 讀得了舊資料，但仍以舊 reader schema 解碼的消費者會失敗。所以這次註冊要把 subject 暫時切到 `BACKWARD_TRANSITIVE`，而「消費者先升級」這個前提，正是步驟三已經用血緣驗證過的事。如果是 Protobuf，把編號與名稱加入 `reserved`。

資料湖的歷史分區不必為此重寫：銀層提供 `COALESCE(amount, CAST(amt AS DECIMAL(18,2)) / 100)` 的欄位，舊分區照樣有 `amount`。只有在要真正刪除 `amt` 實體欄位時，才需要一次性回補舊分區（Iceberg 上的 `UPDATE` 會重寫那些檔案）。

**回退方案**：步驟一到三的任何一點，生產者都還在寫 `amt`，所以回退只是讓消費者改回讀舊欄位。只有步驟四是單向的，這也是它要等兩週的原因。

---

## 八、症狀 → 診斷

| 症狀（你會看到的訊號） | 可能原因 | 怎麼確認 | 修正 |
|---|---|---|---|
| 某欄的 null 比例從 0.1% 跳到 100%，從某個日期分區開始 | 上游改名；依名稱讀取的引擎找不到舊名 | 比對該分區前後檔案 footer 的 schema（`pyarrow.parquet.read_schema`）；查 registry 的版本歷史 | 在銀層對應新舊名；Iceberg 表用 rename 而非新增欄位 |
| 新欄位只在部分分區有值，其他分區是 null | Hive／Glue 表層級加了欄位，舊分區 schema 未更新；或 Spark 沒開 `mergeSchema` | 比對表與分區的 schema（Glue `GetPartition`） | `ADD COLUMNS ... CASCADE`，或遷到 Iceberg |
| 作業在轉型時失敗：`Found long, expecting int`、`HIVE_PARTITION_SCHEMA_MISMATCH` | 型別被放寬，但讀者還是舊 schema；或分區間型別不一致 | 看錯誤從哪個分區、哪個 schema id 開始 | 消費者先升級（BACKWARD 的順序）；統一分區 schema |
| 隔離率從 0.01% 跳到 100% | 生產者部署了不相容的版本，且繞過了 registry 檢查 | 隔離區樣本的 schema id 與 registry 比對 | 觸發斷路；回退生產者；修好後從 offset 重放，而非從隔離區重放 |
| 營收一夜變成 100 倍或 1/100，所有結構檢查都通過 | 同型別改單位（分 ↔ 元） | 金額中位數與分佈的日對日變化；與交易系統或帳本總額對帳（見 Part 6） | 修正後回補受影響日期；在契約中加上單位與值域規則 |
| 營收剛好變成 2 倍 | 雙寫期間有消費者同時讀了新舊兩份：以正則訂閱 `orders.*` 讀到 v1 與 v2，或把 `amt/100` 與 `amount` 相加 | 依 `order_id` 計算重複筆數；檢查訂閱清單 | 消費者只讀一份；對 `order_id` 去重（見 Part 12） |
| CDC 延遲持續上升，connector task 狀態為 FAILED | 上游 `ALTER TABLE` 產生的新 schema 註冊失敗 | Connector 日誌中的 registry 錯誤；DBA 的 migration 紀錄 | 依相容模式調整（例如先加預設值）；把 DB migration 納入契約 CI |

前三列是**大聲的失敗**：作業會報錯或數字明顯歸零，通常當天就被發現。後兩列是**安靜的失敗**：所有檢查都綠燈，數字卻錯了。面試中要主動指出，只有安靜的失敗需要額外的偵測機制——分佈檢查與對帳——而 registry 對它們毫無作用。

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| `FULL_TRANSITIVE` vs 預設的 `BACKWARD`（一對多的事件 topic） | 生產者與 30 個消費者可任意順序部署；資料湖的舊檔案永遠讀得了 | `BACKWARD` 要求消費者先升級，30 個團隊要全部到齊；非 transitive 會放過與舊版不相容的 schema | 只有一個消費者、資料保留期短、從不重讀舊資料；或 expand–contract 的移除那一步，確認消費者都已升級後短暫切到 `BACKWARD_TRANSITIVE` |
| Expand–contract 同一 topic vs 開 v2 topic | 消費者不必改訂閱，可逐一遷移、隨時回退；不會因雙讀而重複計算 | v2 需要所有消費者切換 topic，且雙寫期間容易被重複讀 | key、分區方式或事件粒度改變，同一 topic 無法並存兩種語意 |
| 新欄位一次到位（名稱、型別、單位、幣別）vs 分三次變更 | 30 個消費者只遷移一次 | 每次遷移都要 6 週與一次對帳；三次就是一個季度 | 某個變更有急迫的合規期限，必須先單獨上線 |
| Bronze 保留原始資料 + 銀層強制 schema vs 只在入口強制 | 入口擋不住的語意錯誤，修正後可從原始資料重算 | 只在入口強制時，已被接受但解讀錯的資料無法重建 | 原始資料含不能保留的個資，必須在落地前轉換 |
| Iceberg 欄位 ID vs Hive 表加 Parquet | 改名、刪除、調換順序不重寫資料、不錯位；schema 只有一份 | Hive 表的分區各有 schema，依名稱讀改名變 null、依位置讀可能錯位 | 表很小、schema 幾乎不變，且讀取引擎不支援 Iceberg |
| 隔離率門檻斷路 vs 一律隔離後繼續 | 大規模不相容時停下，修好後從 offset 重放即可 | 一律隔離會把整天資料搬進隔離區，重放更複雜，且下游看到的是殘缺資料 | 來源是不可重送的外部推送，停止消費就會遺失資料 |

---

## 十、系統效應與系列導航

以情境的 `order_completed` 為例，比較「直接改欄位」與「契約 + expand–contract」兩種做法。數字沿用第七節的假設。

| 指標 | 直接改（產品團隊改完就上線） | 契約 + expand–contract |
|---|---|---|
| 破壞性變更被發現的時間 | 隔天早上報表異常，或月結時 | PR 階段，CI 列出受影響的 30 個作業 |
| 期間算錯的作業數 | 未知，最多 30 個 | 0（對帳門檻為零，相容 view 承接未遷移者） |
| 營收 100 倍這類安靜錯誤的偵測 | 靠人眼 | 單位規則 + 分佈檢查 + 與帳本對帳 |
| 回退成本 | 修正後回補所有受影響日期 | 步驟一到三可隨時回退，不需回補 |
| 變更總時程 | 1 天（加上事後數週的修補） | 約 9 週 |
| 額外成本 | 0 | 每天約 320 MB 的雙欄位資料；平台團隊維護 CI 與血緣 |

最後兩列是誠實的代價：**一個破壞性變更從一天變成兩個月**。面試中要說出這是設計目的——讓破壞性變更變貴，大部分變更就會被設計成加法；真正必要的破壞性變更，則以可回退的步驟完成。

**本篇重點**

- 先分類變更：加有預設值的欄位是安全的；改名、改型別、改語意都是遷移，不是變更。
- 相容模式決定升級順序：`BACKWARD` 消費者先、`FORWARD` 生產者先、`FULL` 任意；有長期保留的資料就用 transitive。
- Avro 依名稱加預設值、Protobuf 依編號並 `reserved`、JSON 沒有保證；資料湖用 Iceberg 的欄位 ID 避開 Parquet 依名稱或依位置的陷阱。
- 破壞性變更用 expand–contract：新欄位一次到位、雙寫加零門檻對帳、依血緣分批遷移、確認無人讀取後才移除。
- Registry 管結構，管不了語意；單位改變要靠契約中的值域規則、分佈檢查與對帳。

**DE 系統設計面試指南**

- [Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
- [Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
- [Part 3：串流與即時系統](/posts/de-system-design-interview-part3-streaming-realtime-zh/)
- [Part 4：儲存、倉儲與 Lakehouse 設計](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)
- [Part 5：完整模擬面試與常見情境](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/)
- [Part 6：支付業案例——帳本、對帳與可稽核的資料平台](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/)
- [Part 7：廣告業案例——點擊計費、預算控制與歸因](/posts/de-system-design-interview-part7-adtech-click-billing-attribution-zh/)
- [Part 8：叫車業案例——即時位置、供需與行程資料](/posts/de-system-design-interview-part8-ride-hailing-geo-realtime-zh/)
- [Part 9：影音串流案例——觀看事件、特徵平台與實驗指標](/posts/de-system-design-interview-part9-streaming-media-feature-platform-zh/)
- [Part 10：誰在查、要多新鮮、要多準——依新鮮度選架構](/posts/de-system-design-interview-part10-freshness-sla-tiers-zh/)
- [Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part11-idempotency-rerun-backfill-zh/)
- [Part 12：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)
- **Part 13：Schema 演進——契約、相容性與變更流程**（本篇）
- [Part 14：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- Confluent 文件：Schema Evolution and Compatibility（各相容模式的定義與升級順序）
- Apache Avro Specification：Schema Resolution 一節
- Protocol Buffers 文件：Updating A Message Type 與 Reserved Fields
- Apache Iceberg 文件：Schema Evolution
- Martin Kleppmann,《Designing Data-Intensive Applications》第 4 章 Encoding and Evolution
- Danilo Sato, "Parallel Change"（martinfowler.com，expand–contract 模式）
