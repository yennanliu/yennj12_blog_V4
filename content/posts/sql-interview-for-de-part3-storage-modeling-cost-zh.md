---
title: "DE SQL 面試指南 Part 3：儲存與建模——存得便宜，查得到位"
date: 2026-11-24T09:02:00+08:00
draft: false
weight: 3
description: "查詢能跳過多少資料，在寫入那一刻就決定了。本篇講列式與欄式儲存、Parquet 的編碼與統計值、資料型別、分區與排序鍵的選法、正規化與 star schema 的取捨、SCD2，並用一張事件表試算儲存與掃描成本。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "SQL", "Data Modeling", "Parquet", "Partitioning", "Star Schema", "Cost Optimization", "Data Warehouse"]
authors: ["yen"]
readTime: "11 min"
series: ["sql-interview-for-de"]
---

> 多數人建表時只想到「欄位夠不夠用」，型別全用字串，分區照著直覺切。  
> 半年後同一個儀表板查詢，每跑一次要掃過整張表，帳單與等待時間一起成長。  
> 查詢引擎再聰明，也只能跳過**儲存格式允許它跳過**的資料。  
> 型別、分區、排序、模型這四個建表時的決定，決定了之後每一個查詢的成本下限。

這是「DE SQL 面試指南」的第三篇。[Part 2](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/) 講查詢端怎麼少讀資料，本篇講儲存端怎麼讓「少讀」成為可能，同時把每 GB 的儲存費用壓低。資料湖的 table format（Iceberg、Delta）與 lakehouse 架構在 [DE 系統設計面試指南 Part 4](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/) 已有說明，本篇聚焦在寫 DDL 時要做的決定。

---

## 面試情境

> **面試官**：「我們每天有 5 億筆 App 事件，目前以 JSON 存在物件儲存，分析師用 SQL 引擎直接查。最常見的查詢是『過去 7 天各國家的營收與活躍使用者』。現在每跑一次要好幾分鐘，而且很貴。請你設計這張表：格式、型別、分區、排序，並估算改善幅度。」

這題要的是一組有順序的決定，以及每個決定省下多少。第八節會算出數字。

---

## 一、核心問題：成本在寫入時就決定了

分析型查詢的成本可以寫成一個式子：

```
query cost  ≈  bytes read  =  rows not skipped  ×  columns read  ×  bytes per value
```

三個因子分別由儲存端的三類決定控制：

| 因子 | 由什麼決定 | 本篇章節 |
|---|---|---|
| 沒被跳過的列 | 分區、排序／叢集、檔案統計值 | 五、六 |
| 讀取的欄位 | 欄式儲存、模型的寬窄 | 二、七 |
| 每個值的位元組 | 資料型別、編碼、壓縮 | 三、四 |

儲存費用則是 `總位元組 × 每 GB 單價 × 保留時間`，由第三個因子與保留政策決定。同一組決定同時影響兩種成本，所以值得在建表時想清楚——事後重寫一張 10 TB 的表，本身就是一筆費用。

---

## 二、列式與欄式儲存

**列式儲存（row store）** 把一列的所有欄位放在一起；**欄式儲存（column store）** 把同一欄的所有值放在一起。

```
 logical table                 row store (PostgreSQL, MySQL)
 ┌────┬─────────┬────────┐     ┌───────────────────────────────────────┐
 │ id │ country │ amount │     │ 1,TW,100 │ 2,TW,250 │ 3,JP,80 │ ...   │
 ├────┼─────────┼────────┤     └───────────────────────────────────────┘
 │ 1  │ TW      │ 100    │       one row = one contiguous read
 │ 2  │ TW      │ 250    │
 │ 3  │ JP      │ 80     │     column store (Parquet, ORC, warehouses)
 └────┴─────────┴────────┘     ┌───────────┐ ┌──────────┐ ┌────────────┐
                               │ 1,2,3,... │ │ TW,TW,JP │ │ 100,250,80 │
                               └───────────┘ └──────────┘ └────────────┘
                                 SUM(amount) reads only the last block
```

| | 列式 | 欄式 |
|---|---|---|
| 讀一整列（依主鍵查一筆訂單） | 一次讀取 | 每個欄位各讀一次，慢 |
| 讀少數欄位的大量列（彙總） | 必須讀過整列 | 只讀需要的欄位 |
| 單筆寫入與更新 | 快，就地修改 | 慢，通常要重寫整個檔案或區塊 |
| 壓縮率 | 低，相鄰的值型別各異 | 高，相鄰的值型別相同且常重複 |
| 典型用途 | OLTP：交易系統、API 後端 | OLAP：報表、分析、資料倉儲 |

所以答案不是哪一種比較好，而是工作負載是哪一種。**OLTP**（線上交易處理）的查詢是「依鍵讀寫少數幾列」；**OLAP**（線上分析處理）的查詢是「掃描大量列、只用少數欄位」。一張 40 欄的事件表，查詢只用 3 欄時，欄式儲存在還沒做任何其他最佳化之前，讀取量就已經少了一個數量級。

---

## 三、欄式檔案的內部：編碼與統計值

以 Parquet 為例。一個檔案分成多個 **row group**（預設約 128 MB），每個 row group 裡每一欄是一個 **column chunk**，再切成多個 **page**（預設約 1 MB）。檔案結尾的 footer 記錄了每個 column chunk 的位置與**最小值、最大值、NULL 數量**。

```
 Parquet file
 ┌──────────────────────────────────────────────────────────────────┐
 │ Row group 0                                                      │
 │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐  │
 │  │ dt   min=11-01  │ │ country         │ │ amount  min=1      │  │
 │  │      max=11-01  │ │ dictionary enc. │ │         max=980    │  │
 │  └─────────────────┘ └─────────────────┘ └────────────────────┘  │
 │ Row group 1                                                      │
 │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐  │
 │  │ dt   min=11-02  │ │ country         │ │ amount  min=2      │  │
 │  │      max=11-02  │ │ dictionary enc. │ │         max=7400   │  │
 │  └─────────────────┘ └─────────────────┘ └────────────────────┘  │
 ├──────────────────────────────────────────────────────────────────┤
 │ Footer: schema, row-group offsets, per-column min / max / nulls  │
 └──────────────────────────────────────────────────────────────────┘
   WHERE dt = '2026-11-02'  ->  footer says row group 0 cannot match,
                                so it is never read
```

這個結構帶來兩種省法。

**跳過資料。** 引擎先讀 footer，把條件與每個 row group 的最小值、最大值比對，不可能符合的整塊跳過。這只在**資料依該欄位排序**時有效：如果每個 row group 的 `dt` 範圍都是整個月，沒有一塊可以跳過。第六節會回到這一點。

**壓縮資料。** 同一欄的值放在一起，可以先做編碼再壓縮：

| 編碼 | 作法 | 適合 |
|---|---|---|
| Dictionary | 把相異值存成字典，資料只存代號 | 低基數欄位：國家、狀態、裝置類型 |
| Run-length（RLE） | 連續重複的值存成「值 × 次數」 | 排序後的低基數欄位 |
| Delta | 只存與前一個值的差 | 遞增的 ID、時間戳記 |
| Bit-packing | 用剛好夠用的位元數存整數 | 範圍小的整數、字典代號 |

編碼之後再套通用壓縮。Snappy 解壓縮快、壓縮率中等；ZSTD 壓縮率較高、速度略慢；Gzip 壓縮率接近 ZSTD 但明顯較慢。在依掃描量計費或儲存量大的情境，ZSTD 通常是合理的預設值。

排序同時改善這兩件事：排過序的欄位，min/max 範圍變窄（能跳過更多），相同的值也聚在一起（RLE 與字典更有效）。同一份資料排序前後，檔案大小差上數成並不少見，實際幅度取決於資料本身，要用自己的資料量測。

---

## 四、資料型別：最便宜的最佳化

型別選錯不會讓查詢失敗，只會讓每一個查詢都慢一點、貴一點，而且事後很難改。

| 資料 | 常見的錯誤 | 建議 | 原因 |
|---|---|---|---|
| 金額 | `FLOAT` / `DOUBLE` | `DECIMAL(18,2)`，或以最小貨幣單位存整數 | 浮點數無法精確表示 0.1，加總會出現誤差 |
| ID | 數字存成字串 | `BIGINT` | 8 位元組對上十幾到數十位元組；比較與雜湊也快 |
| UUID | 36 字元的字串 | 原生 `UUID`（16 位元組）或二進位 | 10 億列差 20 GB（壓縮前） |
| 時間 | 字串，或不含時區的時間 | `TIMESTAMP WITH TIME ZONE`，統一存 UTC | 字串無法做範圍裁剪；時區不明就無法正確比較 |
| 日期 | `TIMESTAMP` 當日期用 | `DATE` | 分區鍵與 JOIN 鍵不必再套函數 |
| 布林、列舉 | 自由文字 | `BOOLEAN`，或值域受控的短字串 | 字典編碼有效；避免 `'Y'`、`'yes'`、`'1'` 並存 |
| 半結構化 | 整包 JSON 字串 | 常用欄位拆成具型別的欄，其餘保留在 JSON／`VARIANT` | 字串裡的欄位沒有統計值，也無法裁剪 |

兩個常被問到的細節：

- **JOIN 鍵兩邊的型別要一致。** 一邊 `BIGINT`、一邊 `VARCHAR`，引擎得逐列轉型，索引與裁剪都失效（Part 2 的 sargable 原則）。
- **欄位宣告得太寬通常不佔空間，但會影響規劃。** 多數欄式格式裡 `VARCHAR(10)` 與 `VARCHAR(1000)` 存相同內容時大小一樣，但有些引擎依宣告長度配置記憶體。重點是選對型別類別，其次才是長度。

---

## 五、分區：決定哪些檔案根本不用打開

**分區（partitioning）** 依某個欄位的值，把資料放進不同的目錄或區段。查詢條件包含這個欄位時，引擎只需要讀對應的分區。

```sql
CREATE TABLE events (
  event_id   BIGINT,
  user_id    BIGINT,
  country    STRING,
  event_type STRING,
  amount     DECIMAL(18,2),
  event_ts   TIMESTAMP,
  dt         DATE
)
USING parquet
PARTITIONED BY (dt);
```

### 怎麼選分區鍵

三個條件要同時成立：

1. **幾乎每個查詢都用它過濾。** 時間是最常見的選擇，因為分析查詢幾乎都有時間範圍。
2. **基數低而且穩定。** 分區數量 = 相異值數量。依日期分區，三年是 1,095 個；依 `user_id` 分區是幾百萬個，行不通。
3. **每個分區夠大。** 目標是每個分區至少數百 MB 到數 GB，裡面的檔案落在 128 MB–1 GB。

### 分區切太細的代價

每天 20 GB 的資料，依 `dt` 分區是每天 20 GB、大約 40 個 512 MB 的檔案。如果改成依 `(dt, hour, country)` 分區，假設有 200 個國家，就是每天 24 × 200 = 4,800 個分區，平均每個只有 4 MB。

小檔案的問題有三個：每個檔案都有固定的開檔與讀 footer 的成本；物件儲存的列舉（list）請求變多；中繼資料膨脹，光是規劃查詢就要花數秒到數十秒。**分區是粗粒度的工具**，更細的過濾交給下一節的排序與統計值。

### 兩個實務要點

- **分區欄位要直接出現在條件中。** `WHERE dt >= DATE '2026-11-17'` 會裁剪；`WHERE DATE(event_ts) >= ...` 在傳統 Hive 式分區上不會，因為引擎不知道 `event_ts` 與 `dt` 的關係。Iceberg 的 hidden partitioning 記錄了這層轉換，寫 `event_ts` 的條件也能裁剪。
- **強制要求分區條件。** 許多倉儲可以設定「查詢沒有分區條件就拒絕」（例如 BigQuery 的 `require_partition_filter`）。這是防止意外全表掃描最便宜的方法。

---

## 六、排序與叢集：分區內再跳過

分區之內，資料的排列順序決定了第三節的 min/max 統計值有沒有用。

假設一個分區有 40 個檔案，查詢是 `WHERE country = 'TW'`：

- **沒有排序**：每個檔案都有各國的資料，`country` 的範圍都是 `AE`–`ZA`，40 個檔案全部要讀。
- **寫入時依 `country` 排序**：台灣的資料集中在一、兩個檔案，其餘 38 個從統計值就能排除。

各引擎的說法不同，概念相同：

| 引擎／格式 | 機制 |
|---|---|
| Spark／Hive | 寫入時 `SORT BY` 或 `sortWithinPartitions` |
| Iceberg | 表層級的 sort order，壓實（compaction）時套用 |
| Delta Lake | `OPTIMIZE ... ZORDER BY`、liquid clustering |
| BigQuery | `CLUSTER BY`（最多 4 個欄位） |
| Snowflake | clustering key，micro-partition 的自動統計值 |
| Redshift | sort key |
| ClickHouse | `ORDER BY`（主鍵的稀疏索引） |

### 選排序鍵

- **選最常出現在 `WHERE` 的欄位**，等值條件的優先。
- **只有第一個排序欄位能完全受益。** 依 `(country, user_id)` 排序，`country` 的範圍很窄，`user_id` 只在同一個國家內有序。這與 Part 2 複合索引的前綴原則相同。
- **兩三個欄位同等重要時用多維叢集。** Z-order 等空間填充曲線把多個欄位交錯編碼，讓每個欄位都有部分的局部性，代價是每一個都不如單獨排序。
- **高基數欄位的等值查詢用 bloom filter。** `WHERE user_id = 12345` 在沒有依 `user_id` 排序的表上，min/max 幾乎排除不了任何東西。Parquet 與 ORC 可以為指定欄位寫入 bloom filter，快速回答「這個區塊一定沒有這個值」。

一張表只能有一種實體排列順序。兩組查詢需要不同的排序時，選流量大的那一組，另一組用彙總表或物化視圖支援（Part 4）。

---

## 七、建模：正規化、star schema 與寬表

### 三種形狀

```
 normalized (3NF)             star schema                 one big table
 ┌────────┐   ┌─────────┐         ┌──────────┐            ┌──────────────┐
 │ orders │──▶│ users   │         │ dim_user │            │ order_id     │
 └───┬────┘   └────┬────┘         └────┬─────┘            │ user_country │
     │             ▼                   │                  │ user_plan    │
     ▼        ┌─────────┐  ┌──────┐ ┌──┴──────────┐       │ product_name │
 ┌────────┐   │ country │  │ dim_ │ │ fact_orders │       │ category     │
 │ items  │   └─────────┘  │ date │◀┤ (keys +     │       │ amount       │
 └───┬────┘                └──────┘ │  measures)  │       │ ...          │
     ▼                              └──┬──────────┘       └──────────────┘
 ┌────────┐                       ┌────┴────────┐
 │products│                       │ dim_product │
 └────────┘                       └─────────────┘
 many joins, no redundancy    one join per dimension      no joins
```

| | 正規化（3NF） | Star schema | 寬表（OBT） |
|---|---|---|---|
| 重複資料 | 沒有 | 維度屬性在維度表中重複 | 每一列都重複 |
| 更新一個屬性 | 改一列 | 改維度表的一列（或新增一個版本） | 重寫所有相關的列 |
| 查詢需要的 JOIN | 多 | 每個維度一次，通常可以 broadcast | 無 |
| 適合 | OLTP、來源系統 | 多數分析倉儲的預設選擇 | 單一用途的服務層、儀表板 |

**正規化**的目的是讓每個事實只存一份，更新時不會不一致，這是交易系統的需求。分析系統的資料寫入後很少修改，讀取遠多於寫入，所以可以用重複換取較少的 JOIN。

**Star schema** 的中心是**事實表（fact table）**：每列是一個事件或一筆交易，存外鍵與可加總的數值。周圍是**維度表（dimension table）**：存用來過濾與分組的描述性屬性。設計事實表時先宣告顆粒度（「一列是一筆訂單明細」），這與 Part 1 的原則是同一件事。

**寬表**在欄式儲存上並不像直覺中那麼浪費：重複的維度值經過字典與 RLE 編碼後很小，查詢又只讀需要的欄位。它的真正代價是維度屬性變更時要重寫歷史資料，以及一張表只服務一種顆粒度。常見的組合是：以 star schema 作為核心模型，再為高流量的儀表板產生寬表。

### SCD：維度會變的時候

使用者從免費方案升級到付費方案。去年的訂單該算在哪一種方案下？**緩慢變動維度（Slowly Changing Dimension, SCD）** 處理這個問題：

- **Type 1：覆寫。** 只保留現況。簡單，但歷史報表會隨著維度改變而改變。
- **Type 2：新增版本。** 每次變更新增一列，並記錄有效期間。可以還原任何時間點的狀態。

```sql
CREATE TABLE dim_user (
  user_sk     BIGINT,        -- surrogate key, one per version
  user_id     BIGINT,        -- business key
  country     VARCHAR(2),
  plan        VARCHAR(20),
  valid_from  TIMESTAMP,
  valid_to    TIMESTAMP,     -- '9999-12-31' for the current version
  is_current  BOOLEAN
);

-- Point-in-time join: the plan the user had when the order was placed.
SELECT d.plan, SUM(f.amount) AS revenue
FROM fact_orders f
JOIN dim_user d
  ON  d.user_id    = f.user_id
  AND f.created_at >= d.valid_from
  AND f.created_at <  d.valid_to
GROUP BY d.plan;
```

有效期間用**半開區間**（含起點、不含終點），相鄰的版本才不會重疊或留下空隙。同一個 `user_id` 的區間如果重疊，這個 JOIN 就會 fan-out，所以「區間不重疊」是 SCD2 表必須有的資料品質檢查。Type 2 的維護寫法在 Part 4。

---

## 八、成本試算：同一份資料的四種存法

回到面試情境。假設（皆為說明用的設定值，實際數字要自行量測）：

- 每天 5 億筆事件，原始 JSON 平均 400 位元組，即每天 200 GB，保留一年共 73 TB。
- 轉成 Parquet + ZSTD 後為原始大小的十分之一：每天 20 GB，一年 7.3 TB。
- 事件表有 40 個欄位；目標查詢用到 `dt`、`country`、`user_id`、`amount`，假設這些欄位占檔案位元組的 8%。
- 儲存單價以 S3 Standard 每 GB 每月 0.023 美元計；掃描單價以 Athena 每 TB 5 美元計（us-east-1 公告價，使用前請確認現行價格）。

查詢：過去 7 天各國家的營收與活躍使用者。

| 存法 | 每次查詢讀取量 | 每次查詢費用 | 一年資料的每月儲存費 |
|---|---|---|---|
| A. 原始 JSON，不分區 | 73 TB | $365 | $1,679 |
| B. Parquet + ZSTD，不分區 | 7.3 TB × 8% = 584 GB | $2.92 | $168 |
| C. B + 依 `dt` 分區 | 7 × 20 GB × 8% = 11.2 GB | $0.056 | $168 |
| D. 每日彙總表（`dt`, `country`） | 數 MB 以下 | 低於 $0.001 | 可忽略 |

```
 bytes read per query (log scale, each step = 10x)

 A  raw JSON          ████████████████████████  73 TB
 B  Parquet + ZSTD    ████████████████          584 GB
 C  + partition (dt)  ██████████                11.2 GB
 D  daily rollup      ██                        ~MBs
```

四個觀察：

- **A 到 B 省了 125 倍**，其中 10 倍來自壓縮，12.5 倍來自只讀需要的欄位。換格式是最先該做的事。
- **B 到 C 再省 52 倍**（365 天對 7 天），而且這個倍數會隨保留時間成長：資料保留三年時是 156 倍。
- **排序在這個查詢上沒有額外幫助**，因為它不依 `country` 過濾。排序幫助的是「只看台灣」這種有選擇性的查詢。每個手段省的是特定形狀的查詢，要對著實際的查詢記錄選。
- **D 的活躍使用者不能從每日彙總直接加總。** 同一個人在 7 天內出現 5 天，會被算 5 次。營收可以加總，相異計數不行；解法是在彙總表中保存可合併的 sketch（Part 4）。

面試中把這個順序說出來：「先換成欄式格式並壓縮，再依日期分區，然後看查詢記錄決定排序鍵，最後為最常跑的查詢做彙總表。每一步都拿查詢的掃描量驗證。」

---

## 九、保留、分層與檔案維護

儲存成本的另一半是「存多久、存在哪」。

**保留政策。** 為每張表寫下保留期限與理由。原始資料通常是保留期限內唯一無法重新產生的東西，衍生表可以重算。分區表的過期處理是直接刪除整個分區，幾乎不花錢；沒有分區的表則要逐列刪除並重寫檔案。

**降採樣。** 明細資料保留 90 天，之後只保留每日彙總。這個決定不可逆：彙總之後就無法回答當初沒預先計算的問題，所以要先確認沒有重算與稽核的需求。

**儲存分層。** 物件儲存提供較便宜、但讀取要收費或有最短存放期的層級。規則依存取頻率而定：過去 30 天的熱資料留在標準層，一年前幾乎沒人查的分區移到低頻層。要用存取記錄驗證「沒人查」這個假設，否則一次回補就會把省下的錢付回去。

**檔案維護。** 串流寫入與頻繁的小批次會產生大量小檔案；更新與刪除會留下過時的檔案版本。兩項例行工作：

- **壓實（compaction）**：把小檔案合併成目標大小，並在此時套用排序。
- **清理舊版本**：Iceberg 的 `expire_snapshots`、Delta 的 `VACUUM`。沒做的話，已刪除的資料仍在計費，也不符合個資刪除的要求。

---

## 十、重點回顧與系列導航

- 查詢成本約等於讀取的位元組：沒被跳過的列 × 讀取的欄位 × 每個值的大小。三個因子都在建表時決定。
- 分析負載用欄式格式。它讓引擎只讀需要的欄位，並用編碼與壓縮把每個值變小。
- 型別選對：金額用 `DECIMAL`、ID 用整數、時間用帶時區的時間戳記，JOIN 鍵兩邊一致。
- 分區鍵要是幾乎每個查詢都會過濾的低基數欄位。切太細會產生小檔案，得到反效果。
- 分區內依最常過濾的欄位排序，min/max 統計值才有東西可以排除。
- 分析模型預設用 star schema，先宣告事實表的顆粒度；需要還原歷史狀態時用 SCD Type 2 與半開區間。
- 最佳化的順序：格式與壓縮、分區、排序、彙總表。每一步都對著實際查詢量測。

**DE SQL 面試指南**

- [Part 1：核心觀念——執行順序、NULL 與顆粒度](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/)
- [Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/)
- **Part 3：儲存與建模——存得便宜，查得到位**（本篇）
- [Part 4：資料轉換——冪等、增量與 MERGE](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/)
- [Part 5：正確性、交易、除錯與 Code Review](/posts/sql-interview-for-de-part5-correctness-transactions-review-zh/)

**延伸閱讀**

- Apache Parquet 文件：File Format、Encodings、Bloom Filter
- Apache Iceberg 文件：Partitioning（hidden partitioning）、Maintenance
- Ralph Kimball & Margy Ross, *The Data Warehouse Toolkit*（維度建模與 SCD）
- Daniel Abadi et al., "Column-Stores vs. Row-Stores: How Different Are They Really?"（SIGMOD 2008）
- [DE 系統設計面試指南 Part 4：儲存、倉儲與 Lakehouse 設計](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)
