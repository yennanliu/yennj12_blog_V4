---
title: "DE SQL 面試指南 Part 4：資料轉換——冪等、增量與 MERGE"
date: 2026-11-24T09:03:00+08:00
draft: false
weight: 4
description: "轉換作業的品質看兩件事：重跑一次結果會不會一樣，以及每次要重算多少資料。本篇講全量重建、分區覆寫與 MERGE 三種寫入模式的取捨，增量條件的陷阱、SCD2 的 SQL 實作、彙總表與可合併的 sketch，以及發布前的驗證。"
categories: ["all", "engineering"]
tags: ["RKK", "Interview", "Data Engineering", "SQL", "ETL", "MERGE", "Idempotency", "Incremental Load", "SCD", "Data Quality"]
authors: ["yen"]
readTime: "13 min"
series: ["sql-interview-for-de"]
---

> 多數人寫的轉換作業是一句 `INSERT INTO ... SELECT`，排程每天跑一次。  
> 某天作業失敗後被重跑，報表上的營收就多了一倍，沒有人立刻發現。  
> 一個轉換寫得好不好，看的是：**同一天的資料重跑三次，結果是否完全相同**。  
> 先保證可以安全重跑，再縮小每次重算的範圍；順序反過來，省下的運算會用在追查錯誤數字上。

這是「DE SQL 面試指南」的第四篇。[Part 3](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/) 講資料怎麼存，本篇講資料怎麼從來源變成那些表：用哪種方式寫入、怎麼只處理有變動的部分、怎麼預先算好常用的答案。管線層級的排程與重試設計見 [DE 系統設計面試指南 Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)，本篇聚焦在 SQL 本身。

---

## 面試情境

> **面試官**：「我們有一張 20 億列的訂單事實表，每天從交易資料庫同步。目前的作法是每晚全量重建，要跑 4 小時，而且越來越久。訂單在建立後 30 天內狀態都可能改變。請你把它改成增量處理，並說明怎麼確保結果跟全量重建一致。」

這題有三個要點：選哪種寫入模式、增量的範圍怎麼定、怎麼證明結果正確。

---

## 一、核心問題：失敗後重跑會發生什麼

批次作業一定會失敗：機器被回收、上游延遲、逾時。排程系統的回應是重試。所以每一個轉換都要回答：**寫到一半失敗，或成功之後又被執行一次，目標表會變成什麼樣子？**

```sql
-- Not idempotent: every run appends the same rows again.
INSERT INTO daily_revenue
SELECT created_at::date AS dt, SUM(amount) AS revenue
FROM orders
WHERE created_at >= CURRENT_DATE - 1 AND created_at < CURRENT_DATE
GROUP BY 1;
```

這段有兩個問題。第一，跑兩次就有兩列相同的資料。第二，它用了 `CURRENT_DATE`：今天重跑上週失敗的那一次，處理的會是昨天的資料，不是上週的。

**冪等（idempotent）** 的意思是：同一組輸入執行一次與執行多次，目標表的最終狀態相同。達成它需要兩個條件：

1. **寫入方式是「取代」而不是「附加」。** 下一節的三種模式都符合。
2. **處理範圍由參數決定，不由執行時間決定。** 排程系統傳入邏輯日期（例如 `:run_date`），SQL 裡不出現 `CURRENT_DATE`、`NOW()`。

---

## 二、三種寫入模式

```
 (1) full refresh            (2) partition overwrite      (3) MERGE (upsert)

 source ──▶ rebuild all      source ──▶ rebuild only      changed rows ──▶ match
            │                           dt = run_date                      on key
            ▼                           │                                  │
 ┌──────────────────┐        ┌──────────▼───────┐         ┌───────────────▼──┐
 │ ████████████████ │        │ dt=11-21  (kept) │         │ row A   (kept)   │
 │ ████████████████ │        │ dt=11-22  (kept) │         │ row B   UPDATED  │
 │ ████████████████ │        │ dt=11-23  ██████ │         │ row C   (kept)   │
 │  whole table     │        │  one partition   │         │ row D   INSERTED │
 └──────────────────┘        └──────────────────┘         └──────────────────┘
 cost ∝ table size           cost ∝ partition size        cost ∝ files touched
```

| | 全量重建 | 分區覆寫 | MERGE |
|---|---|---|---|
| 每次處理 | 整張表 | 受影響的分區 | 有變動的列 |
| 冪等 | 天生冪等 | 是，以分區為單位取代 | 是，前提是鍵唯一且來源已去重 |
| 邏輯複雜度 | 最低 | 低 | 最高 |
| 處理刪除 | 自動（來源沒有就不會出現） | 分區內自動 | 要明確處理 |
| 適合 | 小表、維度表、邏輯常改的表 | 只附加的事件、依日期分區的事實表 | 會被更新的實體、變動分散在很多分區 |

**從最簡單的開始。** 一張 500 萬列的維度表，全量重建只要幾十秒，沒有理由寫 MERGE。只有當全量重建的時間或費用成為實際問題時，才往右邊移動。每往右一格，要多證明一件事：增量的結果與全量相同。

### 全量重建

```sql
CREATE TABLE dim_product_new AS
SELECT ... FROM staging.products;

-- Swap atomically so readers never see an empty or half-built table.
BEGIN;
ALTER TABLE dim_product RENAME TO dim_product_old;
ALTER TABLE dim_product_new RENAME TO dim_product;
COMMIT;
```

不要用 `TRUNCATE` 之後再 `INSERT`：兩個動作之間，讀取端會看到空表。先建好新表再切換；倉儲通常提供原子性的 `CREATE OR REPLACE TABLE` 或 swap 指令。

### 分區覆寫

```sql
-- Spark SQL / Hive style: replaces exactly the partitions present in the result.
SET spark.sql.sources.partitionOverwriteMode = dynamic;

INSERT OVERWRITE TABLE fact_events
SELECT event_id, user_id, event_type, amount, event_ts,
       CAST(event_ts AS DATE) AS dt
FROM staging.events
WHERE event_ts >= :run_date AND event_ts < :run_date + INTERVAL 1 DAY;
```

沒有 `INSERT OVERWRITE` 的資料庫，用交易包住「先刪再寫」：

```sql
BEGIN;
DELETE FROM daily_revenue WHERE dt = :run_date;
INSERT INTO daily_revenue
SELECT created_at::date, SUM(amount)
FROM orders
WHERE created_at >= :run_date AND created_at < :run_date + 1
GROUP BY 1;
COMMIT;
```

這是修正第一節那段 SQL 的寫法。重跑幾次，`:run_date` 那一天都只有一份資料。

---

## 三、增量範圍：哪些資料變了

增量處理的難處不在寫入，而在**判斷哪些來源資料需要處理**。最常見的作法是用 `updated_at` 當水位線（watermark）：

```sql
SELECT * FROM source.orders
WHERE updated_at > :last_watermark;
```

這個條件有四個會漏資料的情況。

**1. 交易提交的順序與時間戳記的順序不同。** 一筆交易在 10:00:00 取得 `updated_at`，10:00:07 才提交。作業在 10:00:05 執行，把水位線推進到 10:00:05，這筆資料就永遠不會被讀到。解法是每次往回多讀一段**回看視窗（lookback）**，例如 `updated_at > :last_watermark - INTERVAL '15 minutes'`，再靠冪等的寫入吸收重複讀到的列。

**2. 有些更新不會動到 `updated_at`。** 手動修資料、批次修補、沒有觸發器的舊系統。先確認這個欄位由誰維護、是否有例外。

**3. 實體刪除看不到。** 被 `DELETE` 的列不會出現在任何查詢結果中。來源要改成軟刪除（`deleted_at`），或改用 **CDC（Change Data Capture）** 讀取資料庫的交易記錄，才能取得刪除事件。

**4. 晚到的資料。** 以事件時間分區的表，昨天的事件可能今天才送到。只處理「今天」的分區就會漏掉。

對於第 4 點，以及面試情境中「30 天內狀態都可能改變」的需求，直接的作法是**重算一個滑動視窗**：

```sql
-- Rebuild the last 30 daily partitions on every run.
INSERT OVERWRITE TABLE fact_orders
SELECT ...
FROM staging.orders
WHERE order_date >= :run_date - INTERVAL 30 DAY
  AND order_date <= :run_date;
```

20 億列的表，假設涵蓋三年，30 天大約占 2.7%，約 5,500 萬列。每晚處理 5,500 萬列而不是 20 億列，而且寫法仍然是簡單的分區覆寫，不需要 MERGE。超過 30 天才改變的少數例外，交給每週或每月一次的全量校正。

**視窗長度由資料決定，不是用猜的。** 量測「事件時間」到「抵達時間」的延遲分佈，選一個涵蓋 99.9% 的長度，剩下的由定期校正補齊。

---

## 四、MERGE：語法與四個陷阱

`MERGE` 把來源與目標依鍵比對，配對到的更新，沒配對到的新增：

```sql
MERGE INTO dim_customer AS t
USING (
  SELECT customer_id, email, country, updated_at
  FROM (
    SELECT s.*,
           ROW_NUMBER() OVER (
             PARTITION BY customer_id ORDER BY updated_at DESC
           ) AS rn
    FROM staging.customers s
    WHERE updated_at > :last_watermark - INTERVAL '15 minutes'
  ) x
  WHERE rn = 1                               -- one row per key
) AS s
ON t.customer_id = s.customer_id
WHEN MATCHED AND s.updated_at > t.updated_at THEN
  UPDATE SET email = s.email, country = s.country, updated_at = s.updated_at
WHEN NOT MATCHED THEN
  INSERT (customer_id, email, country, updated_at)
  VALUES (s.customer_id, s.email, s.country, s.updated_at);
```

PostgreSQL 15 起支援 `MERGE`，更早的版本用 `INSERT ... ON CONFLICT (key) DO UPDATE`；MySQL 用 `INSERT ... ON DUPLICATE KEY UPDATE`。Snowflake、BigQuery、Spark SQL（Delta、Iceberg）、SQL Server 都有 `MERGE`。

**陷阱 1：來源的鍵不唯一。** 同一個 `customer_id` 在來源出現兩次時，目標的一列會配對到兩列。多數引擎會直接報錯（PostgreSQL、BigQuery、Delta、Snowflake 的預設設定都是如此），少數設定下會不確定地挑一列。所以 `USING` 裡一定先用 `ROW_NUMBER` 去重，這就是 Part 1 的去重題型。

**陷阱 2：亂序的更新蓋掉較新的資料。** 回看視窗會重讀舊資料，回補時也可能載入舊版本。`WHEN MATCHED AND s.updated_at > t.updated_at` 確保只有較新的版本才能覆寫，這也讓整個 MERGE 可以安全重跑。

**陷阱 3：刪除沒有被處理。** 來源刪掉的列，在目標裡會一直存在。來源提供刪除標記時，加一個分支：`WHEN MATCHED AND s.is_deleted THEN DELETE`。沒有標記時，只能定期全量比對。

**陷阱 4：MERGE 掃了整張目標表。** `ON t.customer_id = s.customer_id` 沒有任何可以裁剪的條件，引擎要讀完整張目標表才能找出配對的列。在分區表上，把分區條件加進 `ON`：

```sql
ON  t.order_id = s.order_id
AND t.order_date >= :run_date - INTERVAL 30 DAY   -- prunes target partitions
```

前提是來源的列都落在這個範圍內，而且同一個鍵不會換分區。否則範圍外的既有列配對不到，會被當成新資料再寫入一次，產生重複。

### Lakehouse 上 MERGE 的實際成本

Parquet 檔案不能就地修改。在 Iceberg、Delta 這類格式上更新一列有兩種作法：

| | Copy-on-write | Merge-on-read |
|---|---|---|
| 寫入時 | 重寫包含該列的整個檔案 | 只寫一個小的刪除檔／差異檔 |
| 讀取時 | 直接讀，沒有額外成本 | 要把資料檔與刪除檔合併 |
| 適合 | 更新少、讀取多 | 更新頻繁、可以定期壓實 |

Copy-on-write 之下，更新 1 萬列如果散落在 1 萬個 512 MB 的檔案，就要重寫 5 TB。所以 MERGE 的成本取決於**被碰到的檔案數**，不是被更新的列數。變動集中（最近的分區、依鍵排序的表）時便宜，變動分散時昂貴。這也是為什麼「重算最近 30 天的分區」常常比「MERGE 進整張表」更快也更簡單。

---

## 五、SCD Type 2 的 SQL 實作

Part 3 定義了 SCD2 表的結構：每個版本一列，帶 `valid_from`、`valid_to`、`is_current`。維護它需要兩個步驟，放在同一個交易中：

```sql
BEGIN;

-- Step 1: close the current version of every key whose attributes changed.
UPDATE dim_user d
SET    valid_to = s.updated_at, is_current = FALSE
FROM   staging.users s
WHERE  d.user_id = s.user_id
  AND  d.is_current
  AND  d.row_hash <> s.row_hash;

-- Step 2: insert a new current version for keys that have none.
--         That covers brand-new keys and the keys closed in step 1.
INSERT INTO dim_user
       (user_id, country, plan, row_hash, valid_from, valid_to, is_current)
SELECT s.user_id, s.country, s.plan, s.row_hash,
       s.updated_at, TIMESTAMP '9999-12-31', TRUE
FROM   staging.users s
LEFT JOIN dim_user d
       ON d.user_id = s.user_id AND d.is_current
WHERE  d.user_id IS NULL;

COMMIT;
```

三個設計重點：

- **用 `row_hash` 偵測變更。** 把所有要追蹤的屬性串接後取雜湊，存成一個欄位，比對一個值就知道有沒有變。串接時要加分隔符號並處理 NULL，否則 `('ab', 'c')` 與 `('a', 'bc')` 會得到相同的雜湊。
- **第二步用 anti join 而不是「有變更的清單」。** 第一步關閉舊版本之後，那些鍵就沒有現行版本了，於是與全新的鍵一起被第二步選中。
- **重跑是安全的。** 第二次執行時，現行版本的雜湊已經與來源相同，兩個步驟都不會影響任何列。

`staging.users` 必須是每個 `user_id` 一列。一天內改了三次而只同步到最後一次時，中間的版本會遺失；需要完整歷史就要用 CDC 取得每一次變更。

---

## 六、預先計算：彙總表與物化視圖

Part 3 的成本試算顯示，每日彙總表可以把查詢的讀取量再降幾個數量級。預先計算是用儲存空間與維護成本，換取查詢時間。

### 可加總與不可加總

彙總表能不能再往上彙總，取決於指標的性質：

| 指標 | 能否從日彙總加總成週 | 說明 |
|---|---|---|
| `SUM(amount)`、`COUNT(*)` | 可以 | 可加總 |
| `MIN`、`MAX` | 可以 | 取每日結果的最小／最大 |
| `AVG(amount)` | 不能直接平均 | 改存 `SUM` 與 `COUNT`，查詢時相除 |
| `COUNT(DISTINCT user_id)` | 不行 | 同一人出現多天會被重複計算 |
| 中位數、百分位數 | 不行 | 每日的 p95 平均起來不是整週的 p95 |

設計彙總表的原則：**存可以合併的元件，不存最終的比率**。存 `paid_orders` 與 `orders` 兩欄，轉換率在查詢時計算，就能在任何維度組合上重新加總。

### 相異計數：存 sketch

**HyperLogLog（HLL）** 是一種機率資料結構，用固定的少量空間（通常數 KB）估計相異值的數量，而且**兩個 sketch 可以合併**成聯集的估計。把每天、每個國家的使用者集合存成一個 sketch，就能在查詢時合併任意多天：

```sql
-- Trino syntax. Build: one sketch per (dt, country).
CREATE TABLE daily_country_rollup AS
SELECT dt, country,
       SUM(amount)                               AS revenue,
       COUNT(*)                                  AS events,
       CAST(approx_set(user_id) AS VARBINARY)    AS users_hll
FROM fact_events
GROUP BY dt, country;

-- Query: weekly active users per country, no double counting.
SELECT country,
       SUM(revenue)                                       AS revenue,
       cardinality(merge(CAST(users_hll AS HyperLogLog))) AS active_users
FROM daily_country_rollup
WHERE dt >= DATE '2026-11-17' AND dt < DATE '2026-11-24'
GROUP BY country;
```

BigQuery 的對應函數是 `HLL_COUNT.INIT`／`HLL_COUNT.MERGE`，Snowflake 是 `HLL_ACCUMULATE`／`HLL_COMBINE`／`HLL_ESTIMATE`。誤差約為百分之一到二（依精度設定）。儀表板可以接受，計費與對帳要用精確值。百分位數的對應工具是 t-digest 或 KLL sketch。

### 物化視圖還是自己維護的表

**物化視圖（materialized view）** 把查詢結果存起來，由引擎負責更新。差別在於誰來維護、能表達多少邏輯：

| | 物化視圖 | 排程維護的彙總表 |
|---|---|---|
| 更新 | 引擎自動，部分引擎支援增量更新 | 自己寫作業（本篇前幾節） |
| 查詢改寫 | 部分引擎會自動把對基礎表的查詢導向視圖 | 查詢要明確指向彙總表 |
| 邏輯限制 | 多：常見不支援外連接、window function、非確定性函數 | 沒有限制 |
| 適合 | 簡單的單表或少量 JOIN 彙總 | 多步驟邏輯、需要回補與版本控制 |

各引擎的能力差異很大（PostgreSQL 的物化視圖只能整個重新整理；BigQuery、Snowflake 支援有限制的增量維護），在面試中說明你會先查清楚所用引擎的限制即可。

彙總表不是越多越好。每一張都是一份需要回補、需要監控、可能與來源不一致的副本。只為查詢記錄中真正高頻的查詢建立。

---

## 七、回補與邏輯變更

增量管線遲早要重算歷史：修了一個 bug、加了一個欄位、來源補送了資料。

**依分區回補。** 寫入模式是分區覆寫、範圍由 `:run_date` 參數決定時，回補就是用不同的日期重跑同一段 SQL，可以多天平行執行。這是第一節堅持不用 `CURRENT_DATE` 的實際好處。

**邏輯改變時，增量表會新舊混雜。** 修改轉換邏輯之後，舊分區是舊邏輯算的，新分區是新邏輯算的。兩個選擇：全部回補，或記錄每列的邏輯版本並明確接受差異。不能什麼都不做。

**回補的順序由相依關係決定。** 下游表依賴上游表時，先回補上游。有累計性質的表（例如餘額、SCD2）必須依時間順序處理，不能平行。

**控制成本。** 一次回補三年的每日分區，可能相當於平常三年的運算量。先用一週的資料估算費用，並考慮用一次性的大範圍查詢取代一千次每日作業——只要邏輯允許一次處理多天。

---

## 八、發布前驗證：Write-Audit-Publish

增量處理的正確性不能只靠相信。把檢查放在資料對讀取端可見**之前**：

```
┌──────────────┐  write   ┌──────────────────┐  audit   ┌──────────────────┐
│ transform    │─────────▶│ staging table or │─────────▶│ checks           │
│ (this run)   │          │ unpublished      │          │ row count, keys, │
└──────────────┘          │ branch/snapshot  │          │ sums, nulls      │
                          └──────────────────┘          └────────┬─────────┘
                                                    pass         │   fail
                                    ┌────────────────────────────┴───┐
                                    ▼                                ▼
                          ┌──────────────────┐            ┌──────────────────┐
                          │ publish: swap or │            │ stop, alert,     │
                          │ fast-forward     │            │ readers still    │
                          └──────────────────┘            │ see old data     │
                                                          └──────────────────┘
```

每次執行至少做四類檢查，全部都是簡單的 SQL：

```sql
-- 1. Key uniqueness: must return zero rows.
SELECT order_id, COUNT(*) FROM stg.fact_orders
WHERE order_date = :run_date
GROUP BY order_id HAVING COUNT(*) > 1;

-- 2. Reconciliation against the source: counts and sums must match.
SELECT 'source' AS side, COUNT(*) AS n, SUM(amount) AS amount
FROM source.orders   WHERE order_date = :run_date
UNION ALL
SELECT 'target', COUNT(*), SUM(amount)
FROM stg.fact_orders WHERE order_date = :run_date;

-- 3. Required columns: must return zero.
SELECT COUNT(*) FROM stg.fact_orders
WHERE order_date = :run_date AND (user_id IS NULL OR amount IS NULL);

-- 4. Volume vs. recent history: flag if far outside the usual range.
SELECT COUNT(*) AS today_rows FROM stg.fact_orders WHERE order_date = :run_date;
```

回到面試情境的第三個要點：怎麼確保增量與全量一致。答案是**定期對帳**：每週用全量邏輯重算一次（或抽樣幾個舊分區重算），與增量維護的結果逐分區比較列數與金額加總。有差異就代表增量邏輯漏了某種變更，這比等使用者發現數字不對要早得多。

---

## 九、為什麼選 X 不選 Y

| 決定 | 選擇與理由 | 什麼情況改選另一邊 |
|---|---|---|
| 全量重建 vs 增量 | 先用全量：邏輯最簡單，不會新舊混雜，天生冪等 | 執行時間或費用超過可接受範圍，且已有對帳機制 |
| 分區覆寫 vs MERGE | 事件與依日期分區的事實表用分區覆寫：不需要鍵比對，成本可預期 | 變更分散在多數分區，或表沒有合適的分區鍵 |
| 滑動視窗重算 vs 精準追蹤變更 | 視窗重算：不依賴 `updated_at` 的可靠性 | 視窗內資料量太大，或變更可能發生在任意久之前 |
| `updated_at` 水位線 vs CDC | 水位線：不需要額外基礎設施 | 需要捕捉刪除、每一次中間變更，或分鐘級的延遲 |
| Copy-on-write vs merge-on-read | 讀多寫少用 copy-on-write：讀取沒有額外負擔 | 更新頻繁且分散，並且能排程壓實 |
| 彙總表 vs 直接查明細 | 高頻且形狀固定的查詢用彙總表 | 查詢形狀多變的探索式分析，彙總表涵蓋不了 |
| 精確相異計數 vs sketch | 儀表板用 sketch：可合併、成本固定 | 計費、對帳、法規報表等不容許誤差的用途 |

---

## 十、重點回顧與系列導航

- 每個轉換都要能安全重跑。用取代式寫入，處理範圍由參數決定，不用 `CURRENT_DATE`。
- 寫入模式由簡到繁：全量重建、分區覆寫、MERGE。只在成本迫使時才往複雜的方向移動。
- `updated_at` 水位線會漏掉晚提交的交易、沒更新時間戳記的修改與實體刪除。用回看視窗加上冪等寫入來吸收。
- MERGE 之前先把來源去重成每個鍵一列，加上版本條件防止舊資料覆寫新資料，並在 `ON` 裡加分區條件。
- 彙總表存可合併的元件：`SUM` 與 `COUNT` 而不是平均，sketch 而不是相異計數的結果。
- 資料先寫到未發布的位置，檢查通過才發布；定期用全量結果對帳，證明增量邏輯沒有漂移。

**DE SQL 面試指南**

- [Part 1：核心觀念——執行順序、NULL 與顆粒度](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/)
- [Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/)
- [Part 3：儲存與建模——存得便宜，查得到位](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/)
- **Part 4：資料轉換——冪等、增量與 MERGE**（本篇）
- [Part 5：正確性、交易、除錯與 Code Review](/posts/sql-interview-for-de-part5-correctness-transactions-review-zh/)

**延伸閱讀**

- PostgreSQL 文件：MERGE、INSERT ... ON CONFLICT
- Apache Iceberg 文件：Row-Level Deletes（copy-on-write 與 merge-on-read）、Branching and Tagging（Write-Audit-Publish）
- Delta Lake 文件：Table deletes, updates, and merges
- Philippe Flajolet et al., "HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm"（2007）
- Maxime Beauchemin, "Functional Data Engineering — a modern paradigm for batch data processing"（2018）
- [DE 系統設計面試指南 Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
