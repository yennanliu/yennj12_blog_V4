---
title: "DE 系統設計面試指南 Part 9：儲存與查詢效率——讀得少、算得少、存得巧"
date: 2026-11-24T11:00:00+08:00
draft: false
weight: 9
description: "倉儲帳單一年漲四倍、儀表板要 40 秒，先別換引擎。從查詢記錄找出前 N 個查詢與各自的掃描量，再從三個槓桿挑解法：讀得少（裁剪、叢集、Parquet 統計值、檔案大小）、算得少（rollup、物化視圖、sketch、快取、join 策略）、存得巧（壓縮、分層、保留與降採樣）。附 Athena 成本試算。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Query Optimization", "Cost Optimization", "Parquet", "Iceberg", "Athena", "AWS"]
authors: ["yen"]
readTime: "19 min"
series: ["de-system-design-interview"]
aliases: ["/posts/de-system-design-interview-part14-storage-query-efficiency-zh/"]
---

> 多數人看到倉儲帳單暴漲，第一個反應是「換一個比較快、比較便宜的引擎」。  
> 搬完之後才發現，同樣的全表掃描只是換了一個地方付錢，儀表板也沒有快多少。  
> 成本與延遲幾乎都來自三件事：**讀了不需要的資料、重複算同一個答案、用最貴的方式存放沒人看的資料**。  
> 先從查詢記錄量出是哪幾個查詢在燒錢，再為每個查詢挑對槓桿——引擎是最後才換的那一個。

這是「策略深入」組的第五篇，處理的問題是（也是 [Part 10](/posts/de-system-design-interview-part10-mock-interview-scenarios-zh/) 結尾自我檢查清單的第四題）：「最常見的查詢需要讀多少資料？」[Part 4](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/) 已經講過 table format、分區、排序、star schema 與 S3 儲存類別的基礎，本篇不重複，而是把「讓查詢更省」整理成一份可以逐項套用的策略清單：每個策略怎麼運作、代價是什麼、什麼條件下會失效。

---

## 面試情境

> **面試官**：「我們的分析倉儲建在 S3 + Iceberg + Athena 上。一年前每月帳單約一萬美元，現在四萬；主管每天早上看的營收儀表板要 40 秒才出來，業務團隊已經在抱怨。預算不會增加。請你在一季內把成本和延遲都降下來，說明你會先做什麼、怎麼知道有沒有效。」

關鍵字是「先做什麼」與「怎麼知道」。面試官要看的是方法，不是一串最佳化技巧。

---

## 一、核心問題：帳單是「查詢次數 × 每次讀的位元組」

在依掃描量計費的引擎上（Athena、自建 Trino 的運算時間也近似如此），成本可以拆成一個乘式：

```
monthly cost = Σ over query families ( runs per month × bytes per run × $ per byte )
               + storage ( GB-month × $ per GB-month )
```

延遲也大致跟「每次讀的位元組」與「要開的檔案數」成正比。所以每一個最佳化手段，都是在壓低這個乘式中的某一項。本篇把手段分成三個槓桿：

```
             query log: top-N query families ranked by bytes scanned
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│ 1 READ LESS       │     │ 2 COMPUTE LESS    │     │ 3 STORE SMARTER   │
│ partition pruning │     │ rollup / MV       │     │ codec + encoding  │
│ cluster / sort    │     │ sketches (HLL)    │     │ storage tiers     │
│ row-group stats   │     │ result cache      │     │ retention and     │
│ file sizing       │     │ join strategy     │     │ downsampling      │
└─────────┬─────────┘     └─────────┬─────────┘     └─────────┬─────────┘
          │ lowers bytes/run        │ lowers runs or          │ lowers $/GB-month
          │                         │ bytes/run (pre-shaped)  │ (and bytes/run)
          └─────────────────────────┴─────────────────────────┘
                                    ▼
                 serving engine chosen by query shape (section 七)
```

順序很重要。**先讀得少、再算得少、然後存得巧，最後才決定引擎**。反過來做，會把浪費原封不動搬到更貴的地方：一個每次掃 3 TB 的查詢，搬到常駐叢集上照樣要掃 3 TB，只是帳單從「每 TB 計費」變成「需要更大的叢集」。

面試中最有力的開場是：「我不會先猜。我會先匯出過去 30 天的查詢記錄，依查詢樣式分組，看每一組的執行次數與掃描量。多數成本通常集中在少數幾個重複執行的查詢上，我從那裡開始。」

---

## 二、三個演進階段

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Measure, then fix the SQL                     (week 1-2)   ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────┐ daily  ┌───────────────┐ top-N  ┌──────────────────────┐
│ Athena query │───────▶│ ops.query_log │───────▶│ fix predicates,      │
│ history API  │ export │ (Iceberg)     │        │ drop SELECT *, turn  │
└──────────────┘        └───────────────┘        │ on result reuse,     │
                                                 │ workgroup scan limit │
                                                 └──────────────────────┘
```

**新增**：查詢記錄表、依樣式分組的成本報表、每個 workgroup 的單次查詢掃描上限。**成本與複雜度**：幾乎為零，一個每日匯出作業。**解決**：找出燒錢的查詢；修掉讓分區裁剪失效的寫法，這一步常常就能砍掉一大塊。**仍存在**：資料排列與模型沒變，常用查詢還是要掃上百 GB。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  Reshape the data for the top queries          (month 1-2)  ║
╚══════════════════════════════════════════════════════════════════════╝

┌────────────┐   ┌───────────────────────┐   ┌──────────────────────────┐
│ Silver     │──▶│ maintenance job       │   │ Gold rollups             │
│ events     │   │ compact to 512 MB,    │──▶│ daily_revenue (grain:    │
│ (Iceberg)  │   │ sort by country,      │   │ day x country x channel  │
└────────────┘   │ ZSTD, expire snapshots│   │ x device)                │
                 │                       │   │ daily_user_hll (sketch)  │
                 └───────────────────────┘   └────────────┬─────────────┘
                                                          ▼
                                             dashboards read Gold only
```

**新增**：合併與排序的維護作業、Gold 聚合表與 sketch 表、壓縮與生命週期規則。**成本與複雜度**：多了幾個排程作業與它們的監控；Gold 表的定義要有人負責。**解決**：前幾大查詢的掃描量下降二到四個數量級，帳單大幅回落。**仍存在**：Athena 每次查詢有排隊與規劃的固定開銷，高並行時延遲不穩定；儀表板想要秒級以下仍有落差。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Serving tier and cost guardrails              (quarter 2+) ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────┐ load   ┌────────────────────┐        ┌──────────────┐
│ Gold rollups │───────▶│ ClickHouse or      │───────▶│ dashboards   │
│ (Iceberg)    │ hourly │ Redshift           │        │ p95 < 1 s    │
└──────┬───────┘        └────────────────────┘        └──────────────┘
       └──▶ Athena: ad hoc and long tail, with per-team scan limits
```

**新增**：一個常駐的服務引擎只承接已經縮小的 Gold 資料；依團隊歸屬成本；新查詢上線前檢查掃描量。**成本與複雜度**：多一個要維運的系統與一條同步管線，Gold 資料多存一份。**解決**：儀表板延遲穩定、成本可預測、新的浪費在上線前被攔下。**仍存在**：同步延遲與兩份資料的一致性，要用 [Part 5](/posts/de-system-design-interview-part5-freshness-sla-tiers-zh/) 的新鮮度分級來決定可以接受多少。

---

## 三、先量測：從查詢記錄找出前 N 個查詢

### 3.1 拿到記錄

各引擎都會記錄每個查詢的掃描量，欄位名稱不同而已：

| 引擎 | 來源 | 關鍵欄位 |
|---|---|---|
| Athena | `ListQueryExecutions` + `BatchGetQueryExecution` API，每日匯出 | `DataScannedInBytes`、`EngineExecutionTimeInMillis`、`QueryQueueTimeInMillis` |
| Snowflake | `ACCOUNT_USAGE.QUERY_HISTORY` | `BYTES_SCANNED`、`PARTITIONS_SCANNED`、`PARTITIONS_TOTAL` |
| Redshift | `SYS_QUERY_HISTORY` 等系統表 | 執行時間、回傳列數；各步驟的讀取細節在 `SYS_QUERY_DETAIL` |

Snowflake 的 `PARTITIONS_SCANNED / PARTITIONS_TOTAL` 接近 1 的查詢，就是裁剪完全失效的查詢。

### 3.2 依查詢樣式分組

儀表板每次執行的 SQL 只差在日期與篩選值，所以要先把字面值換掉，才能把「同一個查詢」聚在一起：

```sql
WITH q AS (
  SELECT regexp_replace(                                     -- numeric literals
           regexp_replace(lower(query_text), '''[^'']*''', '?'),  -- string literals
           '\b\d+(\.\d+)?\b', '?') AS fingerprint,
         data_scanned_bytes, engine_ms
  FROM ops.query_log
  WHERE start_time >= current_date - INTERVAL '30' DAY)
SELECT fingerprint, count(*) AS runs,
       sum(data_scanned_bytes) / 1e12     AS tb_scanned,
       sum(data_scanned_bytes) / 1e12 * 5 AS usd_at_5_per_tb,
       approx_percentile(engine_ms, 0.95) AS p95_ms
FROM q GROUP BY fingerprint ORDER BY tb_scanned DESC LIMIT 20;
```

### 3.3 情境的量測結果

先定下情境的假設：主要事件表每天新增約 80 GB（壓縮後 Parquet）、保留兩年共 730 天約 58.4 TB、約 60 個欄位，依 `dt` 字串欄位做 Hive 式分區。Athena 以每 TB 掃描 $5 計（us-east-1 牌價，每個查詢最少計 10 MB）。量測後的前幾名：

| # | 查詢樣式 | 次數／天 | 每次掃描 | 每月費用 | 初步判斷 |
|---|---|---|---|---|---|
| Q1 | 營收趨勢儀表板：近 30 天、選定國家 | 600 | 192 GB | $17,280 | 分區有裁剪，但其他條件無法跳過任何檔案 |
| Q2 | 營運漏斗：「昨天」的轉換率，每小時排程 | 24 | 2,920 GB | $10,512 | 分區裁剪失效，掃了全部 730 天 |
| Q3 | 近 30 天不重複使用者數（DAU／MAU） | 48 | 240 GB | $1,728 | 精確 `COUNT(DISTINCT)`，每次重讀使用者 ID |
| Q4 | 資料科學家的臨時探索與 join | 不定 | 不定 | $3,000 | 樣式分散，沒有單一熱點 |
| — | 其他長尾 | — | — | $7,480 | — |
| | **合計** | | | **$40,000** | |

各列的算式（欄位裁剪後的比例是假設，實際要看各欄的壓縮後大小）：

```
Q1  30 days × 80 GB × 8% of bytes (4 columns)    = 192 GB/run
    192 GB × 600 runs × 30 days = 3,456 TB        × $5 = $17,280 / month
Q2  730 days × 80 GB × 5% of bytes                = 2,920 GB/run
    2,920 GB × 24 runs × 30 days = 2,102 TB       × $5 = $10,512 / month
Q3  30 days × 80 GB × 10% of bytes (user_id etc.) = 240 GB/run
    240 GB × 48 runs × 30 days = 345.6 TB         × $5 = $1,728 / month
```

這張表同時回答了「為什麼一年漲四倍」：Q1 這個儀表板是今年才上線的，而 Q2 因為裁剪失效，**成本隨表的天數線性成長**——表多一天，每次查詢就多掃一天。三個查詢樣式佔了 74% 的費用，這就是要先動手的地方。

---

## 四、槓桿一：讀得少

### 4.1 分區裁剪：最常見的失效方式

分區設計的原則在 [Part 4](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/) 已經講過。實務上更常見的問題是：分區設計沒錯，但**查詢的寫法讓引擎無法裁剪**。Q2 就是這樣：

```sql
-- 裁剪失效：表依字串欄 dt 分區，條件卻寫在 event_ts 上，而且套了函數
WHERE date(event_ts) = current_date - INTERVAL '1' DAY

-- 可以裁剪：直接以分區欄比對
WHERE dt = date_format(current_date - INTERVAL '1' DAY, '%Y-%m-%d')
```

這個改寫成立的前提是 **`dt` 就是事件日期**（寫入時由 `event_ts` 以同一個時區導出），本文的情境採用這個假設。如果表是依**到達日期**分區，兩個條件選到的列並不相同：昨天發生、今天才到的事件在今天的分區裡，改寫後會被漏掉。這時要保留 `event_ts` 的條件，另外加上一段涵蓋晚到範圍的分區條件來裁剪，例如 `dt BETWEEN 昨天 AND 昨天 + 3 天`（晚到上限見 [Part 7](/posts/de-system-design-interview-part7-dedup-ordering-late-data-zh/)）。

引擎只在條件能對應到分區欄的值時才能跳過分區。三種常見的失效寫法：條件寫在非分區欄（如上）；對分區欄套函數或做運算；分區欄與比較值的型別不一致而被隱式轉換（行為依引擎而定）。Iceberg 的隱藏分區（`day(event_ts)`）能自動把 `event_ts` 的範圍條件換算成分區過濾，所以遷移到 Iceberg 分區規格後，應該寫**原始欄位上的範圍條件**（`event_ts >= ... AND event_ts < ...`），而不是對它套 `date()`。

修正後 Q2 只讀一天：`80 GB × 5% = 4 GB/run`，每月從 $10,512 降到 `4 GB × 24 × 30 = 2.88 TB × $5 ≈ $14`。一行 SQL 省下四分之一的帳單——這就是 Phase 1 要先做的原因。

### 4.2 叢集：線性排序、Z-order 與 Hilbert

Q1 的分區裁剪正常，但它還帶一個「選定國家」的條件，而資料在每天的分區內沒有依國家排列，所以每個檔案的 `country` min/max 幾乎都是 `AD` 到 `ZW`，一個檔案也跳不掉。

| 策略 | 怎麼運作 | 優點 | 缺點 | 何時選 | 何時失效 |
|---|---|---|---|---|---|
| 線性排序（sort key） | 依 (a, b) 字典序排列 | 對 a 的跳過效果最好；Redshift sort key、Iceberg sort order 都支援 | 只對前導欄位有效，b 單獨過濾時幾乎沒用 | 一個欄位出現在大多數過濾條件中 | 過濾條件分散在多個欄位 |
| Z-order | 把多欄的位元交錯成一個值再排序 | 2–3 個欄位各自保有部分跳過效果 | 每個欄位都不如單獨排序；曲線在象限交界跳躍 | 2–3 個欄位被分別過濾 | 欄位超過三、四個，效果稀釋 |
| Hilbert 曲線 | 以 Hilbert 曲線排序多欄 | 每一步只移到相鄰格，檔案的 min/max 範圍比 Z-order 緊 | 計算較複雜，支援的工具較少 | 與 Z-order 相同情境，想要更好的區域性 | 同上 |
| 增量叢集（Delta liquid clustering、Snowflake automatic clustering） | 系統在背景持續重排新寫入的資料 | 不必手動排程；可更換叢集鍵而不重寫全部歷史 | 背景運算持續計費；行為由平台決定 | 寫入頻繁、查詢模式會變 | 叢集鍵選錯，持續花錢卻沒有跳過效果 |

Z-order 與 Hilbert 的差別可以用 4×4 的格子說明，數字是排序後的順序：

```
Z-order                    Hilbert
 0  1 |  4  5               0  1  14 15
 2  3 |  6  7               3  2  13 12
------+------               4  7   8 11
 8  9 | 12 13               5  6   9 10
10 11 | 14 15
```

Z-order 從 7（右上象限的右下角）跳到 8（左下象限的左上角），跨過整張圖；剛好跨過跳躍點的檔案，min/max 會被撐大到幾乎涵蓋全範圍。Hilbert 曲線每一步都只走到相鄰格，所以同樣大小的檔案涵蓋的範圍較緊。Delta Lake 的 liquid clustering 即以 Hilbert 曲線為基礎。

情境中 Q1 一律帶國家條件，所以單欄排序就夠了。假設選定國家平均佔 5% 的資料，加上邊界檔案的損耗，排序後約讀 8% 的位元組：`192 GB × 8% ≈ 15.4 GB/run`，每月降到約 $1,382。在 Iceberg 上用 Spark 程序執行：

```sql
CALL glue.system.rewrite_data_files(
  table      => 'silver.events',
  strategy   => 'sort',
  sort_order => 'country ASC NULLS LAST',   -- or 'zorder(country, channel)'
  where      => 'dt >= "2026-10-01"',         -- re-sort only the hot range first
  options    => map('target-file-size-bytes', '536870912')
);
```

排序要重寫資料，所以先只處理最近、最常被查的區間；回寫整個歷史的運算成本要另外估。

### 4.3 Parquet 檔案內的跳過層次

分區與檔案層級的跳過之外，Parquet 檔案內部還有幾層：

```
part-00017.parquet  (target 512 MB)
┌──────────────────────────────────────────────────────────────┐
│ Row group 0 (~128 MB)                                        │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│ │ country      │ │ user_id      │ │ revenue      │   ...     │
│ │ dictionary + │ │ plain pages  │ │ plain pages  │           │
│ │ RLE pages    │ │ (+ bloom)    │ │              │           │
│ └──────────────┘ └──────────────┘ └──────────────┘           │
├──────────────────────────────────────────────────────────────┤
│ Row group 1 .. 3                                             │
├──────────────────────────────────────────────────────────────┤
│ Footer: schema; per row group and column: min/max, null      │
│ count, offsets; optional page index; bloom filter offsets    │
└──────────────────────────────────────────────────────────────┘
```

讀取器先讀 footer，再依序嘗試跳過：

| 機制 | 能跳過什麼 | 對哪種條件有效 | 何時沒用 |
|---|---|---|---|
| Row group min/max | 整個 row group | 範圍與等值，前提是資料已排序 | 未排序的高基數欄位 |
| Page index（column index） | row group 內的個別 page | 同上，粒度更細 | 同上 |
| 字典過濾 | 字典中沒有該值的 row group | 低基數欄位的等值條件 | 字典過大而退回 plain 編碼時 |
| Bloom filter | 確定不含該值的 row group | 高基數欄位的等值條件（`user_id = ?`） | 範圍條件；值幾乎每個 row group 都有時 |
| 欄位裁剪 | 沒被 SELECT 的欄位 | 所有查詢 | `SELECT *`；把整包 JSON 存成單一字串欄 |

Bloom filter 要在寫入時指定欄位才會產生（例如 Iceberg 的 `write.parquet.bloom-filter-enabled.column.user_id = true`），它解決「從數十億列中查單一使用者」，對 Q1 這種聚合沒有幫助。最後一列則提醒：整包 JSON 存成字串欄，查一個欄位也要讀整個字串；常用欄位應展開成型別明確的欄位或巢狀 struct。

### 4.4 檔案大小：小檔案的帳要算出來

假設串流作業有 16 個 writer、每分鐘提交一次：

```
files per day   = 16 writers × 1,440 commits      = 23,040 files
avg file size   = 80 GB / 23,040                  ≈ 3.5 MB
30-day query    = 23,040 × 30                     = 691,200 files

assume ~30 ms to open a file and read its footer, 200 parallel readers
open overhead   = 691,200 × 30 ms / 200           ≈ 104 s
after compaction to 512 MB: 80 GB / 512 MB ≈ 160 files/day
                = 4,800 files × 30 ms / 200       ≈ 0.7 s
```

此外每個檔案至少要好幾次 S3 GET（footer 加上各欄的 column chunk），以每千次 $0.0004、每檔 3 次估，69 萬個檔案約 $0.83——錢不多，但時間全耗在開檔上。這就是「掃描量沒變、查詢卻越來越慢」的典型原因。合併作業的細節見 Part 4；這裡要補的是：**合併頻率要跟著寫入頻率走**，每分鐘寫入的表，至少每小時合併一次最近的分區。

---

## 五、槓桿二：算得少

### 5.1 預先聚合：rollup、物化視圖與 cube

Q1 每天被執行 600 次，但它的答案一天只變一次（昨天的資料定稿後）。重複從原始事件算同一個聚合，是最大的浪費。

| 策略 | 怎麼運作 | 優點 | 缺點 | 何時選 | 何時失效 |
|---|---|---|---|---|---|
| Rollup 表 | 排程作業把事件依固定粒度聚合成表 | 完全掌控粒度與更新時機；任何引擎都能讀 | 要自己寫增量邏輯、處理晚到資料與重算 | 少數穩定、高頻的查詢樣式 | 查詢的維度組合經常變 |
| 物化視圖：增量刷新 | 引擎只把新變動套用到已存的結果 | 新鮮度高，刷新成本與變動量成正比 | 支援的 SQL 有限制（例如 Snowflake 的 MV 只能基於單表；Redshift 的增量刷新不支援所有語法） | 查詢符合限制、需要接近即時 | 含複雜 join、視窗函數或非確定性函數 |
| 物化視圖：完整刷新 | 每次刷新重算整個結果 | 任何 SQL 都可以 | 刷新成本與總資料量成正比，隨時間變貴 | 結果小、來源小 | 來源是持續成長的大事件表 |
| Cube | 預先計算多個維度所有組合的聚合 | 任意切片都能直接查 | d 個維度有 2^d 種組合，6 維是 64 種、10 維是 1,024 種 | 維度少且固定的 OLAP 報表 | 高基數維度或維度很多 |

情境以 Athena 為主，選擇自己掌控更新邏輯的 Rollup 表。粒度選 `day × country × channel × device`：

```
rows per day   = 200 countries × 10 channels × 5 devices = 10,000 rows
30-day query   = 300,000 rows, a few MB → billed at the 10 MB minimum
dashboard      = 600 × 30 × 10 MB = 180 GB/month          ≈ $0.90
daily build    = 1 day × 80 GB × 8% = 6.4 GB × 30 days    ≈ $0.96
```

Q1 從 $17,280 降到每月約 $2。**粒度是 rollup 設計的核心決定**：只能往上聚合，不能往下鑽。若儀表板之後要依城市切，這張表就要重建；所以粒度要比目前的需求細一層，但不能細到失去縮減效果（以使用者為粒度的 rollup 幾乎等於原始資料）。可加總的指標（sum、count）可以從日粒度再加總成週與月；**不可加總**的指標（不重複數、百分位數、比率）不行——三十天的不重複使用者數不等於每日不重複數的總和。這就是下一節的問題。

### 5.2 近似計算：sketch

Q3 每次都要重讀 30 天的 `user_id` 來算精確的不重複數。HyperLogLog（HLL）把一組值壓成一個固定大小的摘要（sketch），而且**兩個 sketch 可以合併**——這讓不重複數變成「可加總」的指標：

```sql
-- 每日建一列 sketch（Trino / Athena engine v3）
-- 重建某一天時先刪後寫（或 INSERT OVERWRITE 該分區），不可只追加
DELETE FROM gold.daily_user_hll WHERE dt = '2026-11-23';
INSERT INTO gold.daily_user_hll
SELECT dt, country, CAST(approx_set(user_id) AS varbinary) AS hll
FROM silver.events
WHERE dt = '2026-11-23'
GROUP BY dt, country;

-- 近 30 天不重複使用者：合併 30 個 sketch，不碰原始事件
SELECT cardinality(merge(CAST(hll AS HyperLogLog))) AS mau
FROM gold.daily_user_hll
WHERE dt >= '2026-10-25';
```

sketch 表的更新必須是**取代**而不是追加。sketch 只能合併、不能扣除：某一天因修正而少了一批使用者，重跑時若只是再 `INSERT` 一次，舊的 sketch 還留在表裡，之後的 `merge` 會把新舊兩份一起併進去，被移除的使用者仍然算在內。所以重建某一天要連同該天所有國家的列一起換掉，而且最好是原子的（Iceberg 上的 `INSERT OVERWRITE` 或一次 `MERGE`）；上面的先刪後寫在兩個陳述式之間有一小段空窗。

Trino 的 HLL 標準誤差約在 1.6%–2.3% 之間（`approx_distinct` 預設 2.3%，可用參數調低，代價是 sketch 變大）。百分位數（p50、p95 延遲）對應的是 t-digest 或 KLL 這類分位數 sketch，同樣可以合併。

| 指標類型 | 精確做法 | 近似做法 | 誤差 | 什麼時候不能用近似 |
|---|---|---|---|---|
| 不重複數 | `COUNT(DISTINCT)`，每次重讀 | HLL sketch 合併 | 約 1–2%（依參數） | 計費、對帳、合約數字 |
| 百分位數 | 排序全部值 | t-digest、KLL | 依參數，尾端通常較準 | 法規或 SLA 判定的臨界值 |

Q3 從每月 $1,728 降到不到 $1。面試中要主動說出誤差，並確認使用者接受：儀表板上的 MAU 差 2% 通常沒問題，但同一個數字若要拿去開發票，就必須精確計算（見 [Part 12](/posts/de-system-design-interview-part12-adtech-click-billing-attribution-zh/) 的計費設計）。

### 5.3 結果快取

最便宜的查詢是不執行的查詢。Q2 每小時跑一次，但「昨天」的答案一天只變一次——24 次中有 23 次是重算同一個結果。

| 快取層 | 機制 | 失效條件 |
|---|---|---|
| Athena 查詢結果重用 | 相同查詢在設定的最長時效內直接回傳上次結果 | 查詢文字不同、超過時效；它不會偵測底層資料是否變動，時效要自己設 |
| Snowflake 結果快取 | 相同查詢、底層資料未變時，24 小時內重用 | 資料一有變動即失效 |
| Redshift 結果快取、BI 工具的 extract | 引擎或工具保存結果 | 資料變動或依工具排程 |

所以 Athena 的重用適合「答案在時效內不會變」的查詢（昨天的報表），不適合查今天、持續有新資料的查詢。

### 5.4 Join 策略與資料傾斜

Rollup 之後仍有長尾的臨時查詢與 Gold 表的建置作業，它們的成本主要在 join 與 shuffle。

| 策略 | 怎麼運作 | 何時選 | 何時失效 |
|---|---|---|---|
| Broadcast join | 把小表完整複製到每個節點 | 一邊很小（Spark 預設門檻 `autoBroadcastJoinThreshold` 為 10 MB，可調） | 小表其實不小，複製到每個節點會耗盡記憶體 |
| Shuffle（hash／sort-merge）join | 兩邊依 join key 重新分配 | 兩邊都大 | 某個 key 特別多，形成傾斜 |
| 動態過濾（Trino dynamic filtering、Spark runtime filter） | 先掃小表得到 key 集合，再拿去裁剪大表 | 維度表上有選擇性條件 | 維度條件不具選擇性 |

傾斜的數字：10 億列、Spark 預設 200 個 shuffle partition，若一個 key 佔 30%：

```
hot task    = 1B × 30%                 = 300M rows
other tasks = 700M / 199               ≈ 3.5M rows each
salted into 16 sub-keys: 300M / 16     ≈ 18.75M rows per task
```

一個 task 的工作量是其他的 85 倍，整個 stage 都在等它。解法依序是：Spark 3 的 AQE 傾斜處理（`spark.sql.adaptive.skewJoin.enabled`）；把熱門 key 拆出來單獨走 broadcast；或對熱門 key 加鹽（salting）分散到多個子鍵。

Star schema 與寬表的取捨見 Part 4 第五節；從效率角度補一句：**寬表把 join 的成本從讀取時搬到寫入時**。在 join 能力有限的 ClickHouse、Druid、Pinot 上寬表幾乎必要；在 Redshift、Snowflake 上，star schema 加上合適的分佈與排序鍵通常就夠快。

---

## 六、槓桿三：存得巧

### 6.1 壓縮與編碼

在依掃描量計費的引擎上，計費的是**壓縮後**的位元組，所以壓縮率不只省儲存，也直接省查詢費。

| Codec | 壓縮率 | 解壓速度 | 適合 |
|---|---|---|---|
| Snappy | 較低 | 很快 | CPU 吃緊、寫入延遲敏感；Spark 寫 Parquet 的預設 |
| ZSTD | 較高，等級可調 | 快 | 多數分析表的預設選擇；Iceberg 新版本的 Parquet 預設 |
| GZIP | 高 | 慢 | 冷資料、很少讀取的歸檔 |

ZSTD 比 Snappy 省多少取決於資料，要用自己的資料量測。以「省 20%」作為試算假設：每天 80 GB 變 64 GB，長尾的 $7,480 掃描費也同比例下降約 $1,500，儲存費也少 20%。

編碼比 codec 更依賴資料排列。字典編碼把低基數字串換成整數代碼；RLE（run-length encoding）把連續相同值壓成「值 × 次數」；delta 編碼適合遞增的時間戳。**排序會同時提升 RLE 的效果**：依國家排序後，`country` 欄變成一長串連續相同值。另外兩個常見的浪費：把時間戳與數字存成字串：未壓縮時比 int64 大兩三倍，查詢時又常要轉型，轉型一旦套在欄位上就讓 min/max 跳過失效。

### 6.2 儲存分層、保留與降採樣

S3 儲存類別的價格見 Part 4 第八節。這裡補上取回費與可查詢性，us-east-1 約略牌價、作為假設：

| 類別 | 每 GB 每月 | 取回費 | 最短計費 | Athena 能否直接查 |
|---|---|---|---|---|
| Standard | $0.023 | 無 | 無 | 可以 |
| Standard-IA | $0.0125 | 約 $0.01/GB | 30 天 | 可以 |
| Glacier Instant Retrieval | $0.004 | 約 $0.03/GB | 90 天 | 可以（毫秒級取回） |
| Glacier Flexible Retrieval | 約 $0.0036 | 依速度 | 90 天 | 不行，要先還原 |
| Glacier Deep Archive | 約 $0.00099 | 依速度，數小時 | 180 天 | 不行，要先還原 |

情境中 730 天的原始事件放在 Standard，每月約 `58,400 GB × $0.023 ≈ $1,343`。注意這和每月 $40,000 的掃描費相比很小——**在 Athena 上，先優化掃描，再優化儲存**。分層試算：

```
before:  58.4 TB × $0.023                              ≈ $1,343 / month
tiered:  last 90 days  7.2 TB × $0.023 = $166
         older        51.2 TB × $0.004 = $205  (Glacier IR)  ≈ $371 / month
risk:    if 2 TB/month of old data is still read: 2,000 GB × $0.03 = $60
```

比分層更徹底的是**降採樣**：原始事件只保留 90 天，更早的只保留小時級與日級 rollup。原始資料從 58.4 TB 降到 7.2 TB，rollup 只有幾 GB。代價是無法再從舊的原始事件**算出新指標**；所以降採樣前要確認 Bronze 層或某個冷存的歸檔仍保有可重算的副本，或業務明確接受「新指標只從上線日開始有歷史」。個資保留期限通常也會強制這個決定。

### 6.3 刪除向量與快照清理

**Deletion vector**（Delta、Iceberg v3；Iceberg v2 是 position delete）讓刪除與更新只記下「哪幾列無效」而不重寫整個檔案：寫入變快，代價是讀取時要合併，刪除檔累積後查詢會變慢，所以合併作業要順便把刪除套用進資料檔。另一面是舊檔案：每次更新與合併都會留下舊版本，要靠**快照過期**（Iceberg `expire_snapshots`、Delta `VACUUM`）刪除超過保留期的版本，再以孤兒檔案清理收掉失敗寫入的殘留；兩者都不做，儲存量會比資料量長得快。

試算：每天合併最近 3 天的分區（約 240 GB），快照保留 7 天，則隨時有約 `240 GB × 7 = 1.68 TB` 的舊版本仍佔儲存。保留期越長，時間旅行的能力越強，儲存也越多——這是一個要明說的取捨。

---

## 七、服務引擎：依查詢形狀選

前三個槓桿做完之後，才輪到這個問題。選擇的依據是查詢的形狀，不是引擎的名氣：

| 引擎類型 | 計費方式 | 擅長的查詢形狀 | 弱點 | 何時選 |
|---|---|---|---|---|
| Athena／Trino | 依掃描量（Athena）或叢集時間（自建 Trino） | 低並行、範圍大、可等數秒到數十秒的臨時查詢 | 每次查詢有固定開銷；高並行時要排隊 | 查詢零散、資料已在湖上、不想維運叢集 |
| Redshift／Snowflake | 依運算時間（叢集、RPU 或 credit） | 中高並行的 BI、複雜 join、重複查詢（結果快取） | 閒置也可能付費；資料要載入或外部表較慢 | 穩定的儀表板負載、以 SQL 分析師為主 |
| ClickHouse／Druid／Pinot | 常駐節點 | 高並行、秒級以下的聚合；寬表上的切片與篩選 | join 能力有限；要預先決定資料形狀；維運負擔 | 對外的分析產品、上百人同時看的即時儀表板 |

Druid 可在寫入時 rollup，Pinot 有預先聚合的 star-tree 索引——等於把第五節的「算得少」內建進引擎。

情境的判斷：Phase 2 之後，儀表板讀的是每天 1 萬列的 rollup，在 Athena 上一個月只花幾美元，**成本已經不是換引擎的理由**。理由只剩延遲與並行：如果早上九點有上百人同時打開儀表板，Athena 的排隊時間（`QueryQueueTimeInMillis`）會讓 p95 不穩定，這時才把 Gold 表同步到一個小型常駐引擎。因為只同步 Gold，那個引擎可以很小。

---

## 八、症狀與診斷

| 症狀（你看到的） | 檢查什麼 | 可能的根因 | 對應槓桿 |
|---|---|---|---|
| 查詢隨表變大而線性變慢、變貴，條件明明只查最近幾天 | 每次掃描量是否也線性成長；`EXPLAIN` 是否出現分區過濾；Snowflake 的 partitions scanned ≈ total | 分區裁剪失效：條件寫在非分區欄、對分區欄套函數、型別轉換 | 4.1 |
| 掃描量穩定，執行時間卻越來越長 | Iceberg `"db"."events$files"` 的檔案數與平均大小；刪除檔數量；快照與 manifest 數 | 小檔案、刪除檔未合併、中繼資料膨脹 | 4.4、6.3 |
| 排序後一開始很快，幾週後又變慢 | 新分區的檔案是否有排序；Snowflake 的 clustering 資訊 | 新寫入的資料沒有排序，合併作業沒有重排 | 4.2 |
| Spark 作業大多數 task 早已完成，卡在最後一兩個 | Spark UI 中同一 stage 的 task 時間最大值與中位數之比 | 資料傾斜 | 5.4 |
| 儀表板只在早上慢，其他時間正常 | Athena 的佇列時間與執行時間分開看 | 並行排隊，不是掃描量問題 | 5.3、七 |
| 儲存量成長比資料寫入快 | 快照數、孤兒檔案、生命週期規則是否生效 | 快照未過期、失敗寫入殘留 | 6.3 |
| 某個 rollup 上線後帳單沒有下降 | 查詢記錄中舊樣式的查詢是否還在跑 | 儀表板仍指向原始表；或 rollup 粒度太細，縮減有限 | 5.1、三 |

最後一列提醒的是驗收方式：**每個最佳化都要回到查詢記錄看前後對照**，而不是相信它「應該」有效。

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| 先修查詢與資料排列 vs 直接換引擎 | 成本是「次數 × 位元組」，先把位元組降下來，換不換引擎都受益 | 換引擎不會減少掃描量，還多一套系統與遷移成本 | 掃描量已經很小，剩下的問題是並行與延遲 |
| Rollup 表 vs 物化視圖 | 粒度、更新時機與晚到資料處理完全可控，任何引擎都能讀 | 物化視圖受 SQL 限制，且各引擎行為不同 | 引擎的增量刷新支援這個查詢，且團隊不想維護排程作業 |
| HLL sketch vs 精確 COUNT DISTINCT | 不重複數變成可合併，30 天的查詢只讀 30 個小 sketch | 精確計算每次要重讀全部使用者 ID | 數字用於計費、對帳或合約，必須精確 |
| 單欄排序 vs Z-order／Hilbert | 查詢一律帶同一個欄位時，單欄排序對它的跳過效果最好 | 多維曲線把效果分給多個欄位，每個都打折 | 有兩三個欄位被分別、頻繁地過濾 |
| ZSTD vs Snappy | 壓縮率較高，在依掃描計費時同時省儲存與查詢費 | Snappy 檔案較大，每次查詢多付位元組 | 寫入端 CPU 是瓶頸，或延遲極度敏感的串流寫入 |
| 降採樣後刪除 vs 全部搬到 Glacier | 儲存量下降一個數量級，查詢也不會誤掃舊原始資料 | 全部保留仍要付儲存費，舊資料偶爾被掃時還有取回費 | 經常需要從舊原始事件重算新指標，或法規要求保留原始紀錄 |

---

## 十、系統效應與系列導航

依第三節的假設，把三個主要查詢樣式改造後的月費對照：

| 查詢樣式 | 改造前 | 手段 | 改造後 |
|---|---|---|---|
| Q1 營收趨勢 | $17,280 | 排序（中間步驟 $1,382）→ rollup | 約 $2 |
| Q2 昨日漏斗 | $10,512 | 修正分區條件（＋結果重用） | 約 $14（重用後不到 $1） |
| Q3 不重複使用者 | $1,728 | 每日 HLL sketch | 不到 $1 |
| Q4 臨時探索 | $3,000 | workgroup 掃描上限、提供 Silver 抽樣表 | 假設不變 $3,000 |
| 長尾 | $7,480 | 暫不處理（ZSTD 可再省約 20%） | 假設不變 $7,480 |
| **掃描費合計** | **$40,000** | | **約 $10,500（−74%）** |
| 儲存費 | $1,343 | 90 天後轉 Glacier IR | 約 $371 |

延遲方面：Q1 從每次讀 192 GB 變成讀一個幾 MB 的 rollup，主要時間只剩 Athena 的排隊與規劃開銷；Phase 3 把 rollup 同步到常駐引擎後，設計目標是 p95 低於 1 秒。這些延遲數字是設計目標，要以實際負載量測驗收。新增的維運工作：查詢記錄匯出、合併與排序作業、rollup 與 sketch 的建置及晚到資料重算（見 [Part 6](/posts/de-system-design-interview-part6-idempotency-rerun-backfill-zh/)）、快照過期、生命週期規則，以及 Phase 3 的同步管線。

**本篇重點**

- 帳單是「查詢次數 × 每次讀的位元組」加上儲存；先用查詢記錄找出前 N 個查詢樣式，再挑槓桿。
- 讀得少：確認分區裁剪沒有被函數或型別轉換破壞；用排序或 Hilbert／Z-order 讓 min/max 有用；檔案維持數百 MB。
- 算得少：高頻且答案少變的查詢做成 rollup；不可加總的指標用可合併的 sketch；答案不變的查詢交給結果快取。
- 存得巧：ZSTD 在依掃描計費時同時省兩種錢；用存取記錄決定分層，用重算需求決定降採樣。
- 引擎最後才換，而且只為了延遲與並行，不是為了掩蓋掃描量。

**DE 系統設計面試指南**

- [Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
- [Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
- [Part 3：串流與即時系統](/posts/de-system-design-interview-part3-streaming-realtime-zh/)
- [Part 4：儲存、倉儲與 Lakehouse 設計](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)
- [Part 5：誰在查、要多新鮮、要多準——依新鮮度選架構](/posts/de-system-design-interview-part5-freshness-sla-tiers-zh/)
- [Part 6：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part6-idempotency-rerun-backfill-zh/)
- [Part 7：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part7-dedup-ordering-late-data-zh/)
- [Part 8：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part8-schema-evolution-zh/)
- **Part 9：儲存與查詢效率——讀得少、算得少、存得巧**（本篇）
- [Part 10：完整模擬面試與常見情境](/posts/de-system-design-interview-part10-mock-interview-scenarios-zh/)
- [Part 11：支付業案例——帳本、對帳與可稽核的資料平台](/posts/de-system-design-interview-part11-payments-ledger-reconciliation-zh/)
- [Part 12：廣告業案例——點擊計費、預算控制與歸因](/posts/de-system-design-interview-part12-adtech-click-billing-attribution-zh/)
- [Part 13：叫車業案例——即時位置、供需與行程資料](/posts/de-system-design-interview-part13-ride-hailing-geo-realtime-zh/)
- [Part 14：影音串流案例——觀看事件、特徵平台與實驗指標](/posts/de-system-design-interview-part14-streaming-media-feature-platform-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- Apache Parquet 文件：File Format、Page Index、Bloom Filter
- Apache Iceberg 文件：Maintenance（rewrite_data_files、expire_snapshots）、Configuration
- AWS 文件：Top 10 Performance Tuning Tips for Amazon Athena、Amazon S3 Storage Classes
- Philippe Flajolet et al., "HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm"（2007）
- Ted Dunning & Otmar Ertl, "Computing Extremely Accurate Quantiles Using t-Digests"（2019）
- Jim Gray et al., "Data Cube: A Relational Aggregation Operator Generalizing Group-By, Cross-Tab, and Sub-Totals"（1997）
