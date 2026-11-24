---
title: "DE 系統設計面試指南 Part 4：儲存、倉儲與 Lakehouse 設計"
date: 2026-11-21T12:00:00+08:00
draft: false
weight: 4
description: "儲存層設計就是預先為查詢模式付費。講解 warehouse、lake、lakehouse 的差異、Iceberg 等 table format 的運作、分區與叢集的裁剪效果、star schema 與 SCD、分層與治理，附 AWS 成本試算。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Lakehouse", "Iceberg", "Data Warehouse", "Data Modeling", "S3", "AWS"]
authors: ["yen"]
readTime: "17 min"
series: ["de-system-design-interview"]
---

> 多數人設計資料湖時，想的是「把資料用 Parquet 存到 S3，再依日期、小時、類型分區」。  
> 一年後得到的是三千萬個小檔案、每月上萬美元的掃描帳單，以及一個查三分鐘的儀表板。  
> 儲存設計的本質不是「放在哪裡」，而是**替未來的查詢預先決定可以跳過哪些資料**。  
> 每一個分區鍵、排序鍵與資料模型，都是在回答同一個問題：最常見的查詢長什麼樣子。

這是系列的第四篇。前兩篇談資料怎麼進來（[批次](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)與[串流](/posts/de-system-design-interview-part3-streaming-realtime-zh/)），本篇談資料落地之後怎麼存、怎麼建模、怎麼被查。讀完你應該能解釋 lakehouse 解決了資料湖的什麼問題、估算一個分區設計能省多少掃描量，並為不同的查詢模式選擇服務引擎。

---

## 面試情境

> **面試官**：「我們在 S3 上累積了三年、約 400 TB 的 Parquet 事件資料，依 `dt/hour/event_type` 分區，用 Athena 查詢。現在有三個問題：Athena 帳單每個月都在漲、分析師抱怨常用查詢要跑三分鐘、而且每日回補作業執行期間，查詢偶爾會回傳不完整的結果。請重新設計儲存層。」

三個症狀對應三個不同的根因，本文會逐一拆解。

---

## 一、核心問題：儲存設計是預先為查詢付費

[Part 1](/posts/de-system-design-interview-part1-framework-fundamentals-zh/) 算過一個結論：在雲端上**儲存便宜、掃描貴**。用情境的數字再算一次：

```
storage    400 TB × $0.023 /GB-month           ≈ $9,200 / month
one full scan with Athena: 400 TB × $5 /TB     = $2,000 / query
```

掃完整張表五次，就超過一整個月的儲存費。所以儲存層的設計目標很明確：**讓每個查詢碰到的位元組數盡可能少**。

查詢引擎有四個層次可以跳過資料，由粗到細：

```
400 TB table, query: last 7 days, one event_type, 5 of 80 columns

┌────────────────────────────────────────────────────────────────────┐
│ 1 no pruning            read everything        400 TB     $2,000   │
├────────────────────────────────────────────────────────────────────┤
│ 2 partition pruning     7 of ~1,100 days       2.5 TB     $12.50   │
├────────────────────────────────────────────────────────────────────┤
│ 3 column pruning        5 of 80 columns        ~160 GB    $0.80    │
├────────────────────────────────────────────────────────────────────┤
│ 4 file / row-group      1 event_type ≈ 10%     ~16 GB     $0.08    │
│   skipping (min/max)    (data sorted by type)                      │
└────────────────────────────────────────────────────────────────────┘
```

每一層都是設計決定的結果：第 2 層靠分區鍵，第 3 層靠欄式格式，第 4 層靠檔案內的排序與統計值。假設各欄大小相近、`event_type` 佔比約 10%；實際比例要用真實資料量測。同一個查詢從 $2,000 降到不到一毛錢，差了四個數量級——這張階梯圖值得在面試白板上畫出來。

回到情境的三個症狀，根因分別是：

| 症狀 | 根因 | 對應章節 |
|---|---|---|
| 帳單持續上漲 | 分區過細產生小檔案、沒有排序所以第 4 層跳過無效、分析師直接查原始層 | 四、六 |
| 常用查詢三分鐘 | 引擎花大量時間列出與開啟數萬個小檔案 | 三、四 |
| 回補時結果不完整 | 直接改寫 S3 路徑不是原子操作，讀者看到寫到一半的狀態 | 三 |

---

## 二、三個演進階段

先釐清三個常被混用的名詞。

| | Data Warehouse | Data Lake | Lakehouse |
|---|---|---|---|
| 儲存 | 引擎專屬格式，儲存與運算綁在一起（或由同一產品管理） | 物件儲存上的開放格式檔案 | 物件儲存上的開放格式檔案 + table format |
| Schema | 寫入時強制（schema-on-write） | 讀取時解釋（schema-on-read） | 寫入時強制，可演進 |
| 交易（ACID） | 有 | 無 | 有 |
| 資料型態 | 結構化 | 任何型態 | 任何型態，表格部分有交易保證 |
| 多引擎存取 | 受限 | 可以 | 可以 |
| AWS 代表 | Redshift | S3 + Glue Catalog + Athena | S3 + Iceberg + Athena／EMR／Redshift |

Lakehouse 可以理解成：**在資料湖的便宜儲存上，補回倉儲才有的交易與 schema 管理**。補上的那一層就是 table format。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Raw lake (where the scenario is today)                     ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐ write ┌───────────────────────────────────────┐   ┌────────┐
│ Jobs     │──────▶│ S3  /events/dt=/hour=/event_type=/    │◀──│ Athena │
└──────────┘       │ 30M small Parquet files, Hive layout  │   └────────┘
                   └───────────────────────────────────────┘
```

**優點**：最容易開始，沒有額外元件。**問題**：就是情境中的三個症狀。資料量在數 TB 以下、只有追加寫入、沒有並行讀寫衝突時，這個階段其實夠用。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  Lakehouse tables + layers                                  ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐      ┌─────────────────────────────────────────────────┐
│ Jobs     │─────▶│ Iceberg tables on S3                            │
└──────────┘      │ ┌─────────┐   ┌─────────┐   ┌────────────────┐  │
                  │ │ Bronze  │──▶│ Silver  │──▶│ Gold           │  │
┌──────────┐      │ │ raw     │   │ cleaned │   │ modeled / aggr │  │
│ Compact  │─────▶│ └─────────┘   └─────────┘   └────────────────┘  │
│ + expire │      └───────────────────────┬─────────────────────────┘
└──────────┘                              │
                                 ┌────────┴────────┐
                                 │ Athena / EMR    │
                                 └─────────────────┘
```

**新增**：table format（原子提交）、重新設計的分區與排序、定期合併小檔案與清理舊快照的維護作業、三層資料分層。

**解決**：回補不再讓讀者看到半成品；檔案數從千萬級降到百萬級以下；分析師查的是已聚合的 Gold 層而非原始資料。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Purpose-built serving + governance                         ║
╚══════════════════════════════════════════════════════════════════════╝

                     ┌──────────────────────────┐
                     │ Iceberg tables on S3     │
                     │ (single source of truth) │
                     └───┬─────────┬────────────┘
          ad hoc, large  │         │ load Gold      ┌─────────────────┐
                         ▼         ▼                │ Catalog, column │
                  ┌──────────┐  ┌──────────────┐    │ access control, │
                  │ Athena / │  │ Redshift or  │    │ lineage, tiering│
                  │ Trino    │  │ ClickHouse   │    └─────────────────┘
                  └──────────┘  └──────┬───────┘
                                       ▼
                                BI dashboards, p95 < 2 s
```

**新增**：針對高並行儀表板的專用服務引擎、欄位層級的存取控制與資料血緣、依存取頻率的儲存分層。

**解決**：儀表板查詢從數十秒降到秒級以下；成本可依團隊歸屬；個資的存取與刪除有機制可循。

**代價**：Gold 層的資料多存一份在服務引擎中，需要同步作業與一致性檢查。

---

## 三、Table Format：資料湖缺的那一層

**直覺**：傳統資料湖中，「一張表」就是「一個資料夾底下的所有檔案」。這個定義有兩個問題：要知道表裡有什麼，得列出整個資料夾；而改動多個檔案時，沒有任何東西能保證讀者不會看到改到一半的狀態。Table format 把定義換成「**一份中繼資料清單所列出的那些檔案**」。

**機制**（以 Iceberg 為例）：

```
┌──────────────────────┐
│ Catalog              │  table name -> current metadata file
│ (Glue)               │  commit = atomic swap of this one pointer
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ metadata.json        │  schema, partition spec, list of snapshots
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ manifest list        │  one per snapshot: which manifests, with
│ (snapshot S42)       │  partition value ranges for each
└─────┬──────────┬─────┘
      ▼          ▼
┌──────────┐ ┌──────────┐
│ manifest │ │ manifest │  list of data files, with per-file
└────┬─────┘ └────┬─────┘  row count and column min/max
     ▼            ▼
┌─────────┐  ┌─────────┐
│ data    │  │ data    │   immutable Parquet files
│ files   │  │ files   │
└─────────┘  └─────────┘
```

寫入的流程是：先寫出新的資料檔與新的中繼資料檔（這時讀者完全看不到），最後一步才把 catalog 的指標從舊的 metadata 換成新的。這一步是原子的比較並交換——成功就整批可見，失敗就整批不可見。**這就是情境中「回補時結果不完整」的解法**：讀者永遠讀到某一個完整的快照。

這個結構順帶提供了四個能力：

| 能力 | 怎麼來的 | 面試中怎麼用 |
|---|---|---|
| 原子提交與快照隔離 | 單一指標的原子替換 | 回補與查詢並行不互相干擾；實作 [Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/) 的 WAP |
| 時間旅行（time travel） | 舊快照在過期前仍保留 | 重現昨天的報表數字；誤刪後回復 |
| 規劃查詢不必列出目錄 | 檔案清單與統計值在 manifest 中 | 解決「列檔比讀資料還久」 |
| Schema 與分區演進 | 欄位以 ID 追蹤；分區規格可換新 | 加欄位、改分區方式都不必重寫歷史資料 |

兩個並行寫入者同時提交時，後到的那個會發現指標已經變了，於是重新檢查衝突並重試（樂觀並行控制）。追加寫入之間通常不衝突；兩個作業改寫同一批檔案則會有一個失敗重來。

### 3.1 列級更新：Copy-on-Write 與 Merge-on-Read

Parquet 檔案不可變，所以「更新一筆資料」有兩種做法：

| | Copy-on-Write（CoW） | Merge-on-Read（MoR） |
|---|---|---|
| 更新時 | 重寫包含該筆資料的整個檔案 | 只寫一個小的刪除／差異檔 |
| 讀取時 | 直接讀，無額外成本 | 要把資料檔與差異檔合併 |
| 寫入成本 | 高 | 低 |
| 讀取成本 | 低 | 隨差異檔累積而升高，需定期合併 |
| 適合 | 每日批次、讀多寫少 | CDC 高頻更新、近即時寫入 |

### 3.2 三種主流格式

| | Iceberg | Delta Lake | Hudi |
|---|---|---|---|
| 中繼資料 | 快照 + manifest 樹 | 交易日誌（JSON + 定期 checkpoint） | 時間軸（timeline） |
| 強項 | 引擎中立、分區演進、隱藏分區 | 與 Spark／Databricks 整合最深 | 高頻 upsert 與增量讀取 |
| AWS 上 | Athena、EMR、Glue、Redshift 皆原生支援 | EMR、Glue 支援 | EMR、Glue 支援 |

面試中不需要宣稱哪個最好。合理的說法是：「三者解決同一個問題，我會依團隊主要使用的引擎選擇；在以 Athena 為主的 AWS 環境我選 Iceberg，因為各引擎的支援最一致。」

---

## 四、分區、排序與檔案大小

### 4.1 分區過細是最常見的錯誤

情境中的 `dt/hour/event_type` 看起來合理，算一下就知道問題在哪（假設 50 種事件類型）：

```
partitions  = 1,100 days × 24 hours × 50 types = 1,320,000
avg size    = 400 TB / 1.32M                   ≈ 300 MB per partition
files       = 30,000,000  ->  avg 13 MB per file, ~23 files per partition
```

每個分區平均只有 300 MB，卻被切成 20 幾個小檔案（通常來自每小時多次的小批次寫入）。查詢最近 7 天要先處理 8,400 個分區、近 20 萬個檔案的中繼資料，這就是「三分鐘」的來源——時間花在規劃與開檔，不是讀資料。

分區設計的三條經驗法則：

1. **分區鍵用低基數、幾乎每個查詢都會過濾的欄位**。通常只有日期符合。
2. **每個分區至少數 GB**。小於 1 GB 的分區代表切得太細。
3. **其他過濾欄位交給排序與統計值**，不要做成分區。

重新設計後：

```
partition by   day(event_time)       -> 1,100 partitions, ~365 GB each
sort within    event_type, user_id   -> min/max skipping on both
target file    512 MB                -> ~700 files per day, ~800K total
```

檔案數從 3,000 萬降到約 80 萬，查詢最近 7 天只需規劃約 5,000 個檔案。

Iceberg 的**隱藏分區**在這裡有實際好處：分區定義為 `day(event_time)` 這個轉換，查詢只要寫 `WHERE event_time >= ...`，引擎自動換算成分區過濾。傳統 Hive 式分區需要使用者記得同時過濾 `dt` 欄位，忘了就是全表掃描——這也是帳單上漲的常見原因之一。

### 4.2 排序與叢集

分區只能處理一個低基數的維度。對於高基數的過濾欄位（`user_id`、`event_type` 加上其他條件），要靠檔案內的資料排列。

**機制**：每個檔案與 row group 記錄各欄的最小值與最大值。資料依某欄排序後，每個檔案只涵蓋該欄的一小段範圍，查詢條件不在範圍內的檔案整個跳過。若資料未排序，每個檔案的最小值到最大值幾乎涵蓋全部範圍，統計值就毫無用處。

```
unsorted: every file spans the whole range   -> must read all 4 files
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ min a    │ │ min a    │ │ min b    │ │ min a    │
│ max z    │ │ max y    │ │ max z    │ │ max z    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘

sorted by event_type: WHERE event_type = 'purchase' -> read 1 file
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ min a    │ │ min g    │ │ min n    │ │ min t    │
│ max f    │ │ max m    │ │ max s    │ │ max z    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
                           ^ only this one
```

單一排序鍵只對第一個欄位最有效。當查詢會分別用兩三個不同欄位過濾時，可以用 **Z-order**：把多個欄位的位元交錯成一個排序值，讓每個欄位都保有部分的區域性。代價是每個欄位的跳過效果都不如單獨排序，而且寫入成本較高。超過三、四個欄位後效果會明顯稀釋。

### 4.3 檔案大小與維護

目標檔案大小通常落在 128 MB 到 1 GB。太小則中繼資料與開檔成本主導；太大則無法細緻跳過，且單一檔案的重寫成本高。

串流與高頻批次寫入必然產生小檔案，所以 lakehouse 需要固定的維護作業，面試中要主動提出：

- **合併（compaction）**：把小檔案重寫成目標大小，並順便重新排序。每日或每小時對最近的分區執行。
- **快照過期**：刪除超過保留期（例如 7 天）的舊快照及其不再被引用的檔案。不做的話，儲存量會因為每次重寫都保留舊版而持續膨脹。
- **孤兒檔案清理**：清除失敗寫入留下、沒有任何快照引用的檔案。

---

## 五、資料建模：Star Schema 與 SCD

儲存格式決定資料「怎麼放」，資料模型決定「放什麼」。面試中常以「請設計這個業務的資料表」的形式出現。

### 5.1 Star Schema

**直覺**：把資料分成兩類——**發生了什麼事**（事實，fact）與**事情的背景**（維度，dimension）。事實表又長又窄，記錄量測值；維度表又短又寬，記錄描述性屬性。

```
                    ┌──────────────────┐
                    │ dim_date         │
                    │ date_key, month, │
                    │ quarter, holiday │
                    └────────┬─────────┘
                             │
┌──────────────────┐  ┌──────┴────────────────┐  ┌──────────────────┐
│ dim_customer     │  │ fact_order_item       │  │ dim_product      │
│ customer_key,    ├──┤ date_key, customer_key├──┤ product_key,     │
│ name, tier, city │  │ product_key, store_key│  │ name, category,  │
└──────────────────┘  │ quantity, amount      │  │ brand            │
                      └──────┬────────────────┘  └──────────────────┘
                             │
                    ┌────────┴─────────┐
                    │ dim_store        │
                    │ store_key, region│
                    └──────────────────┘
```

設計事實表的第一步，也是面試官最想聽到的一句話，是**宣告粒度（grain）**：「這張表的一列代表一張訂單中的一個品項。」粒度決定了哪些量測值可以放進來、哪些聚合是安全的。把訂單層級的運費放進品項粒度的表，`SUM` 之後就會重複計算。

把維度再正規化成多層（產品 → 品類 → 部門各一張表）稱為 **snowflake schema**。它省下少量儲存，但每個查詢多幾次 join；在欄式儲存中維度的重複值壓縮得很好，所以通常不值得。

### 5.2 緩慢變動維度（SCD）

維度會變：客戶搬家、升級會員等級。問題是，去年的訂單應該對應**當時**的等級還是**現在**的等級？

| 類型 | 作法 | 歷史 | 適用 |
|---|---|---|---|
| Type 1 | 直接覆寫 | 不保留 | 修正錯字；歷史值沒有分析意義 |
| Type 2 | 新增一列並標記有效期間 | 完整保留 | 需要依當時狀態分析（等級、區域、價格） |

Type 2 的實際樣子：

| customer_key | customer_id | tier | valid_from | valid_to | is_current |
|---|---|---|---|---|---|
| 1001 | C-17 | silver | 2025-03-01 | 2026-06-14 | false |
| 2417 | C-17 | gold | 2026-06-15 | 9999-12-31 | true |

`customer_id` 是來源系統的業務鍵；`customer_key` 是倉儲自己產生的代理鍵，每個版本一個。事實表存的是 `customer_key`，所以 2025 年的訂單自然指向 silver 那一列，不需要在查詢時比對日期。

### 5.3 寬表與建模方法論

| 取向 | 作法 | 取捨 |
|---|---|---|
| Kimball（維度建模） | 由下而上，依業務流程建立 star schema 的資料市集 | 交付快、查詢直覺；跨市集的維度需要刻意保持一致 |
| Inmon（企業倉儲） | 由上而下，先建正規化的企業模型再衍生市集 | 一致性高；前期投入大、交付慢 |
| 寬表（One Big Table） | 把事實與常用維度預先 join 成一張寬表 | 查詢最簡單、在欄式引擎上很快；維度變更時要重寫、難以表達多種粒度 |

實務上的常見組合是：Silver 層維持接近 star schema 的結構作為單一事實來源，Gold 層針對特定儀表板產出寬表。

---

## 六、分層：Bronze、Silver、Gold

三層（medallion）架構替每份資料回答「它被處理到什麼程度、誰可以直接用」。

| 層 | 內容 | 寫入方式 | 主要使用者 | 保留 |
|---|---|---|---|---|
| Bronze | 與來源一致的原始資料，只加上擷取時間等中繼欄位 | 只追加 | 資料工程師 | 長期（重算的依據） |
| Silver | 去重、型別修正、過濾無效資料、統一命名後的乾淨資料 | 依鍵 MERGE 或分區覆寫 | 資料科學家、進階分析師 | 長期 |
| Gold | 依業務定義聚合或建模後的資料 | 分區覆寫 | 分析師、BI、下游服務 | 依需求 |

分層的價值在於**邊界**。Bronze 保證「來源給了什麼都留著」，所以任何下游的錯誤都能從這裡重算；Gold 保證「指標定義只有一份」，所以兩個儀表板不會對同一個指標算出不同數字。

回到情境的帳單問題：把分析師最常執行的 20 個查詢整理成幾張 Gold 聚合表後，這些查詢掃描的資料量從數百 GB 降到數百 MB。**多數掃描成本來自少數重複執行的查詢**，所以先從查詢記錄中找出這些查詢，是成本最佳化的第一步，比調整任何參數都有效。

---

## 七、服務引擎的選擇

沒有一個引擎適合所有查詢。依查詢模式選擇：

| 查詢模式 | 特徵 | 適合的引擎 | 原因 |
|---|---|---|---|
| 臨時探索 | 低並行、大範圍掃描、容許數十秒 | Athena（或自建 Trino） | Athena 無需常駐叢集、依掃描量計費；自建 Trino 要負擔常駐叢集的固定成本，查詢量夠大才划算 |
| BI 儀表板 | 高並行、重複查詢、要求秒級 | Redshift、ClickHouse | 常駐運算、本地快取與結果快取 |
| 依鍵查詢 | 極高 QPS、個位數毫秒 | DynamoDB、Redis | 鍵值存取，不做掃描 |
| 全文與日誌搜尋 | 關鍵字、前綴、相關性 | OpenSearch | 反向索引 |
| 重度轉換 | 小時級、TB 級 shuffle | Spark on EMR／Glue | 可容錯的大規模批次運算 |

依掃描量計費與依常駐運算計費之間有一個交叉點，值得在面試中用數字說明。假設常用儀表板每天產生 2,000 次查詢，每次在 Gold 表上掃描 5 GB：

```
Athena:    2,000 × 5 GB × $5 /TB × 30 days   ≈ $1,500 / month
Cluster:   fixed monthly cost, regardless of query count
```

當穩定查詢量的掃描費超過一個小型常駐叢集的月費，而且使用者需要秒級回應時，就該把 Gold 層載入專用的服務引擎。查詢量低而零散時，依量計費比較划算。

---

## 八、治理、刪除與成本

### 8.1 治理的最小集合

| 項目 | 回答的問題 | AWS 上的做法 |
|---|---|---|
| 資料目錄 | 有哪些表、欄位是什麼意思、誰負責 | Glue Data Catalog 加上擁有者與說明 |
| 存取控制 | 誰能看到哪些欄與列 | Lake Formation 的欄位與資料列層級權限 |
| 個資標記 | 哪些欄位是敏感資料 | 欄位標籤，權限依標籤授予 |
| 血緣 | 這張表的資料從哪來、誰在用 | 由排程器與查詢記錄產生 |

### 8.2 刪除個資

「使用者要求刪除他的資料」在不可變檔案的資料湖上並不直觀，是很好的深挖題。完整的答案有五步：

1. 在 table format 上執行列級刪除，產生新的快照。
2. **資料檔可能還沒被改寫**。以 merge-on-read 方式執行的刪除只是多寫一個刪除檔，原本的資料檔仍含有那些資料列，所以要先重寫受影響的資料檔（合併時套用刪除檔）。
3. **舊快照仍然引用舊檔案**，所以接著讓舊快照過期、實體刪除不再被引用的檔案，並確認檔案確實消失。
4. **副本與衍生資料也要刪**：Gold 表、載入服務引擎（Redshift、ClickHouse）的副本、快取與匯出檔，都要傳播刪除並驗證。
5. Bronze 層的原始資料同樣要處理。把識別碼在進入 Bronze 前以代碼取代（tokenization）、另存對照表，可以讓這一步便宜很多：刪除對照表中的那一列，代碼就無法再對回個人。但這是**假名化而非匿名化**——如果事件中還有 email、IP、精確位置等其他可識別欄位，仍然要逐一處理或直接刪除原始資料列。

### 8.3 儲存分層

三年的資料並非同樣常被查詢。S3 的儲存類別價差很大：

| 類別 | 每 GB 每月（us-east-1 約略牌價） | 特性 |
|---|---|---|
| Standard | $0.023 | 無取回費 |
| Standard-IA | $0.0125 | 讀取每 GB 另收約 $0.01；最短計費 30 天 |
| Glacier Instant Retrieval | $0.004 | 取回費更高；最短計費 90 天 |

假設最近 90 天約 100 TB 維持 Standard，其餘 300 TB 移到 Standard-IA：

```
before:  400 TB × $0.023                         ≈ $9,200 / month
after:   100 TB × $0.023 + 300 TB × $0.0125      ≈ $6,050 / month
```

每月省約三分之一。要提醒的限制是：低頻類別的讀取要收取回費，若有作業定期全表掃描舊資料，反而更貴。分層規則應該根據實際的存取記錄而非猜測。

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| Lakehouse（Iceberg）vs 純倉儲 | 儲存便宜且開放、多引擎共用一份資料、原始與非結構化資料同處 | 純倉儲在數百 TB 的原始事件上儲存成本高，且綁定單一引擎 | 資料在數 TB 內、全是結構化資料、團隊以 SQL 分析師為主，單一倉儲最省事 |
| Table format vs 裸 Parquet 目錄 | 原子提交、快照隔離、免列目錄、可演進 | 裸目錄在並行讀寫時會讀到半成品，且規劃查詢要列出所有檔案 | 只追加、單一寫入者、資料量小、沒有回補與更新 |
| 只依日期分區 vs 多層細分區 | 分區數少、檔案大、規劃快；其他維度交給排序 | 細分區產生上百萬分區與千萬個小檔案 | 某個維度基數很低、每個查詢必帶、且每個分區仍有數 GB |
| 排序／Z-order vs 加更多分區 | 高基數欄位也能跳過檔案，不增加分區數 | 分區只適合低基數欄位 | 資料量太小，整個分區只有一兩個檔案，排序沒有可跳過的對象 |
| CoW vs MoR | 讀取無合併成本，適合每日批次與讀多寫少 | MoR 的讀取效能取決於合併是否跟得上 | CDC 高頻更新、要求分鐘級新鮮度 |
| Star schema vs 全部做成寬表 | 維度變更只改一處；多種粒度可並存；指標定義集中 | 寬表在維度變更時要重寫，且容易出現多份不一致的副本 | 單一用途的儀表板資料、維度穩定、追求最簡單的查詢 |
| SCD Type 2 vs Type 1 | 歷史分析依當時狀態計算 | Type 1 覆寫後，去年的報表數字會隨今天的屬性改變 | 屬性變更只是修正錯誤，或業務明確只關心現況 |
| 專用服務引擎 vs 全部用 Athena | 高並行下秒級回應、成本可預測 | 依掃描計費在高頻重複查詢下費用線性成長，延遲不穩定 | 查詢量低而零散、可接受數秒到數十秒 |

---

## 十、系統效應與系列導航

把情境從 Phase 1 改造到 Phase 3 的前後對照。查詢相關的數字基於以下假設：每天 300 個分析查詢，改造前平均掃描 400 GB，改造後多數查詢落在 Gold 表上、平均掃描 20 GB。

| 指標 | 改造前 | 改造後 |
|---|---|---|
| 分區數 | 約 132 萬 | 約 1,100 |
| 資料檔案數 | 約 3,000 萬（平均 13 MB） | 約 80 萬（目標 512 MB） |
| 常用查詢時間 | 約 3 分鐘 | 設計目標：Athena 約 10 秒、服務引擎上 < 2 秒（需以實際工作負載量測） |
| 每日掃描費用 | 300 × 400 GB × $5/TB ≈ $600 | 300 × 20 GB × $5/TB ≈ $30 |
| 每月儲存費用 | 約 $9,200 | 約 $6,050（分層後） |
| 回補期間的查詢結果 | 偶爾不完整 | 一律讀到完整快照 |
| 誤刪或錯誤寫入後的回復 | 從備份還原，以小時計 | 回到前一個快照，以分鐘計 |
| 新增的維運工作 | 無 | 合併、快照過期、Gold 同步、權限管理 |

**本篇重點**

- 儲存設計的目標是讓查詢少讀資料；裁剪有四層：分區、欄位、檔案、row group。
- Table format 把「表」定義為中繼資料列出的檔案集合，以單一指標的原子替換提供交易。
- 分區只用低基數且查詢必帶的欄位，其餘靠排序與統計值；每個分區至少數 GB、檔案 128 MB–1 GB。
- 建模先宣告粒度；需要依當時狀態分析的維度用 SCD Type 2。
- 成本最佳化從找出少數重複執行的昂貴查詢開始，把它們變成 Gold 表。

**DE 系統設計面試指南**

- [Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
- [Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
- [Part 3：串流與即時系統](/posts/de-system-design-interview-part3-streaming-realtime-zh/)
- **Part 4：儲存、倉儲與 Lakehouse 設計**（本篇）
- [Part 5：完整模擬面試與常見情境](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/)
- [Part 6：支付業案例——帳本、對帳與可稽核的資料平台](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/)
- [Part 7：廣告業案例——點擊計費、預算控制與歸因](/posts/de-system-design-interview-part7-adtech-click-billing-attribution-zh/)
- [Part 8：叫車業案例——即時位置、供需與行程資料](/posts/de-system-design-interview-part8-ride-hailing-geo-realtime-zh/)
- [Part 9：影音串流案例——觀看事件、特徵平台與實驗指標](/posts/de-system-design-interview-part9-streaming-media-feature-platform-zh/)
- [Part 10：誰在查、要多新鮮、要多準——依新鮮度選架構](/posts/de-system-design-interview-part10-freshness-sla-tiers-zh/)
- [Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part11-idempotency-rerun-backfill-zh/)
- [Part 12：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)
- [Part 13：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part13-schema-evolution-zh/)
- [Part 14：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- [AWS DynamoDB 完整指南與最佳化](/posts/aws-dynamodb-complete-guide-optimization/)
- Apache Iceberg 文件：Table Spec、Partitioning、Maintenance
- Ralph Kimball & Margy Ross,《The Data Warehouse Toolkit》第 1–5 章
- Michael Armbrust et al., "Lakehouse: A New Generation of Open Platforms that Unify Data Warehousing and Advanced Analytics"（CIDR 2021）
- AWS 文件：Amazon S3 Storage Classes、Athena Performance Tuning
