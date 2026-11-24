---
title: "DE SQL 面試指南 Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜"
date: 2026-11-24T09:01:00+08:00
draft: false
weight: 2
description: "查詢慢的時候先別加索引。本篇從一個查詢的生命週期講起：最佳化器怎麼用統計值估列數、怎麼選 join 演算法，EXPLAIN 要看哪三個數字，索引何時有用，以及分散式引擎上資料傾斜與 shuffle 的診斷與改寫。"
categories: ["all", "engineering"]
tags: ["RKK", "Interview", "Data Engineering", "SQL", "Query Optimization", "EXPLAIN", "Index", "Data Skew", "Spark", "PostgreSQL"]
authors: ["yen"]
readTime: "11 min"
series: ["sql-interview-for-de"]
---

> 多數人遇到慢查詢，第一個動作是加索引，第二個動作是加機器。  
> 索引加了沒被使用，機器加了一倍，查詢還是卡在同一個 task 上。  
> 查詢的成本由兩件事決定：**讀了多少列，以及搬動了多少列**。  
> 先看執行計畫，找出「估計列數」與「實際列數」差最多的那一步，問題通常就在那裡。

這是「DE SQL 面試指南」的第二篇。[Part 1](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/) 講怎麼寫出正確的查詢，本篇講怎麼讓它跑得快，以及怎麼解釋它為什麼慢。前半以 PostgreSQL 為例說明單機資料庫，後半說明 Spark、Trino 這類分散式引擎多出來的問題。

---

## 面試情境

> **面試官**：「這個每日報表查詢上個月還跑 3 分鐘，現在要 50 分鐘。SQL 沒有人改過，叢集規格也沒變。請你說明排查的順序，以及每一步你要看什麼。」

SQL 沒變、機器沒變，那變的就是**資料**：資料量、資料分佈，或最佳化器對資料的認知。本篇的內容就是這題的答案。

---

## 一、核心問題：SQL 只說要什麼，不說怎麼拿

SQL 是宣告式語言：你描述要的結果，由**最佳化器（optimizer）** 決定怎麼取得。同一個查詢可以有上千種執行方式——先 JOIN 哪兩張表、用哪種 JOIN 演算法、走不走索引——各種方式的耗時可以差到一萬倍。

最佳化器靠**估計**來選擇。它不知道一個條件實際會留下幾列，只能根據統計值去猜。猜得準，計畫就好；猜錯，就會選到災難性的計畫。

所以效能調校有兩個方向：

1. **給最佳化器正確的資訊**：新鮮的統計值、正確的資料型別、它看得懂的條件式。
2. **給它更好的選項**：索引、分區、預先彙總的表，或一個讀更少資料的寫法。

「加索引」只是第二類中的一種。多數「SQL 沒變卻變慢」的案例屬於第一類。

---

## 二、一個查詢的生命週期

```
 SQL text
    │
    ▼
┌──────────────┐  syntax tree
│ 1 Parse      │───────────────┐
└──────────────┘               ▼
                        ┌──────────────┐  resolve tables, columns, types
                        │ 2 Analyze    │  (catalog lookup)
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐  rule-based rewrites:
                        │ 3 Logical    │  predicate pushdown, column
                        │   optimize   │  pruning, constant folding
                        └──────┬───────┘
                               ▼
┌──────────────┐        ┌──────────────┐  cost-based choices:
│ statistics   │───────▶│ 4 Physical   │  join order, join algorithm,
│ (row counts, │ feeds  │   planning   │  scan method (index or full)
│  histograms) │        └──────┬───────┘
└──────────────┘               ▼
                        ┌──────────────┐
                        │ 5 Execute    │──▶ rows
                        └──────────────┘
```

第 3 步的改寫不看資料，只套用永遠成立的規則。兩個最重要的規則是：

- **述詞下推（predicate pushdown）**：把 `WHERE` 條件盡量往資料來源推，越早濾掉越好。Part 1 講的邏輯順序是「先 JOIN 再 WHERE」，但實際上最佳化器會先過濾再 JOIN，只要結果相同。
- **欄位裁剪（column pruning）**：只讀查詢用到的欄位。在欄式儲存上，這直接決定要讀多少位元組（Part 3）。

第 4 步才看統計值，為每個候選計畫估一個成本，挑最低的。**效能問題幾乎都發生在第 4 步選錯**，而不是引擎執行得不夠快。

---

## 三、讀 EXPLAIN：三個要看的數字

`EXPLAIN` 顯示最佳化器選的計畫；`EXPLAIN ANALYZE` 會真的執行查詢，並列出每一步的實際列數與時間。下面是一個示意輸出（數字為說明用途而設計），`orders` 有 5,000 萬列：

```
Hash Join  (cost=1250.00..1183431.55 rows=120 width=24)
           (actual time=18.4..5140.7 rows=48211 loops=1)
  Hash Cond: (o.user_id = u.user_id)
  ->  Seq Scan on orders o  (cost=0.00..1180000.00 rows=400 width=16)
                            (actual time=0.02..4890.3 rows=161204 loops=1)
        Filter: ((status = 'paid') AND (created_at >= '2026-11-01'))
        Rows Removed by Filter: 49838796
  ->  Hash  (cost=1000.00..1000.00 rows=20000 width=12)
            (actual time=17.9..17.9 rows=20000 loops=1)
        ->  Seq Scan on users u  (cost=0.00..1000.00 rows=20000 width=12)
              Filter: (country = 'TW')
Planning Time: 0.4 ms
Execution Time: 5151.2 ms
```

計畫是一棵樹，**由最內層、最下面的節點開始讀**，資料由下往上流。每個節點看三件事。

**1. 估計列數與實際列數差多少。** `orders` 的掃描估 400 列，實際 161,204 列，差了 400 倍。差距在 10 倍以內通常無妨；超過 100 倍，上層的每個決定（JOIN 順序、演算法、記憶體配置）都是根據錯的數字做的。這是最重要的訊號。

**2. 時間花在哪個節點。** 總時間 5,151 ms 中，4,890 ms 花在 `orders` 的循序掃描。JOIN 本身只花了大約 250 ms。

**3. 讀了多少、留下多少。** 這個掃描讀了 5,000 萬列，留下 16 萬列，丟掉 99.7%。讀取量遠大於需要量，代表缺少一個可以直接定位資料的結構。

診斷結論：`(status, created_at)` 的條件只留下 0.3% 的列，卻用了全表掃描，因為沒有可用的索引。建立 `CREATE INDEX ON orders (status, created_at)` 之後，掃描會變成 Index Scan，只讀符合條件的那 16 萬列。估計值偏差的問題要另外處理，見第六節。

還有一個數字要留意：`loops`。Nested Loop 的內層節點顯示的時間與列數是**每次迴圈的平均值**，要乘上 `loops` 才是總量。`actual time=0.05 loops=200000` 是 10 秒，不是 0.05 毫秒。

分散式引擎的對應工具：Spark 用 `EXPLAIN FORMATTED` 與 Spark UI 的 SQL 分頁，Trino 用 `EXPLAIN ANALYZE`，Snowflake 與 BigQuery 用查詢歷史裡的 query profile／execution graph。看的東西相同：每個階段的輸入列數、輸出列數、耗時。

---

## 四、索引與 sargable 條件

### B-tree 索引怎麼運作

**B-tree 索引**是一份依鍵值排序的目錄，每個項目指向資料列的位置。因為有序，它能做兩件事：用對數時間找到某個值（1 億列大約 4 層），以及從那個位置往後循序讀出一段範圍。

**複合索引**的欄位順序決定它能回答哪些查詢。`(status, created_at)` 就像先依姓氏、再依名字排序的電話簿：

| 條件 | 能否使用 `(status, created_at)` |
|---|---|
| `status = 'paid'` | 可以，使用前綴 |
| `status = 'paid' AND created_at >= '2026-11-01'` | 可以，最理想：先定位再讀一段 |
| `created_at >= '2026-11-01'` | 效果差，沒有前導欄位，無法定位起點 |
| `status IN ('paid','refunded') AND created_at >= ...` | 可以，每個值各定位一次 |

排欄位順序的經驗法則：**等值條件的欄位放前面，範圍條件的欄位放最後**。範圍條件之後的欄位無法再用來縮小搜尋範圍。

如果索引本身就包含查詢需要的所有欄位，引擎可以完全不回資料表讀取，稱為 **covering index**（PostgreSQL 的 Index Only Scan）。`CREATE INDEX ON orders (status, created_at) INCLUDE (amount)` 讓「某狀態在某期間的金額加總」只讀索引。

### 索引何時沒用

索引掃描對每一列都可能是一次隨機讀取；全表掃描是循序讀取，每列便宜得多。所以條件留下的比例高時，全表掃描反而快。分界點依硬體與列寬而異，經驗上大約落在百分之幾到 10–20% 之間。`WHERE status = 'done'` 而 95% 的訂單都是 `done` 時，最佳化器不用索引是正確的決定。

索引也不是免費的：每多一個索引，每次 `INSERT`、`UPDATE`、`DELETE` 都要多維護一份結構，並占用儲存空間。寫入頻繁的表上，五個沒人用的索引是實際的成本。

### Sargable：讓條件用得上索引

一個條件能利用索引（或分區、min/max 統計值）直接定位資料，就稱為 **sargable**（Search ARGument ABLE）。原則是：**欄位要單獨站在比較運算子的一邊，不要被函數或運算包住**。

| 寫法（用不上索引） | 改寫（用得上） | 原因 |
|---|---|---|
| `WHERE DATE(created_at) = '2026-11-01'` | `WHERE created_at >= '2026-11-01' AND created_at < '2026-11-02'` | 索引存的是欄位值，不是函數的結果 |
| `WHERE amount * 1.05 > 100` | `WHERE amount > 100 / 1.05` | 把運算移到常數那一邊 |
| `WHERE user_id = '123'`（欄位是整數，或反過來） | 型別一致 | 隱含轉型可能套在欄位上 |
| `WHERE email LIKE '%@x.com'` | 存一個反轉或網域欄位 | 開頭萬用字元無法定位起點 |
| `WHERE COALESCE(status,'x') = 'paid'` | `WHERE status = 'paid'` | 函數包住了欄位 |

這個原則不限於索引。分區裁剪也適用：對分區欄位套函數，引擎就可能掃所有分區。這是資料倉儲帳單暴漲最常見的單一原因。

---

## 五、JOIN 演算法

引擎實際執行 JOIN 的方法有三種。知道它們的適用條件，才看得懂計畫為什麼這樣選。

| 演算法 | 作法 | 適合 | 成本（左 N 列、右 M 列） |
|---|---|---|---|
| **Nested Loop** | 對外層每一列，到內層找配對 | 外層很小，且內層有索引 | 有索引 O(N log M)，沒有則 O(N×M) |
| **Hash Join** | 用較小的表建雜湊表，掃較大的表逐列探查 | 等值 JOIN、兩邊都大、較小邊放得進記憶體 | O(N + M) |
| **Sort-Merge Join** | 兩邊各自依鍵排序，再同步往前合併 | 兩邊都很大，或資料本來就已排序 | O(N log N + M log M) |

三個推論：

- **Nested Loop 加上錯誤的估計是最常見的災難。** 最佳化器以為外層只有 10 列而選了 Nested Loop，實際有 100 萬列，就變成 100 萬次索引查找。第三節看到估計差 400 倍時，要擔心的就是這個。
- **Hash Join 只支援等值條件。** `ON a.ts BETWEEN b.start_ts AND b.end_ts` 這種範圍 JOIN 沒有等值鍵可以雜湊，容易退化成 Nested Loop。改善方法是加一個等值條件（例如先依日期或 `user_id` 相等，再比範圍）。
- **雜湊表放不進記憶體時會溢出到磁碟。** PostgreSQL 的計畫會顯示 `Batches: 8`，Spark 會顯示 spill。這時要減少建表那一邊的列數或欄位數。

---

## 六、統計值與資料分佈

### 最佳化器知道什麼

最佳化器對每個欄位保存一份摘要：列數、相異值數量、NULL 比例、**最常見值清單（MCV）** 及其頻率，以及描述其餘值分佈的**直方圖**。PostgreSQL 由 `ANALYZE`（通常由 autovacuum 自動觸發）收集；Spark 與 Hive 表需要 `ANALYZE TABLE ... COMPUTE STATISTICS`，Iceberg、Delta 等格式則在寫入時記錄檔案層級的統計值。

估計出錯有三個典型來源。

**1. 統計值過期。** 一次匯入 3,000 萬列之後還沒重新收集，最佳化器仍以為表只有 100 萬列。這是開頭面試題的首要嫌疑：先檢查上次 `ANALYZE` 的時間，並比較估計與實際列數。

**2. 欄位之間有關聯。** 最佳化器預設各欄位彼此獨立，把選擇率相乘。`city = 'Taipei' AND country = 'TW'`：各自的選擇率是 3% 與 4%，相乘得 0.12%，但台北必然在台灣，實際是 3%，低估了 25 倍。PostgreSQL 可以用 `CREATE STATISTICS` 建立多欄位統計值來修正。

**3. 資料傾斜（skew）。** 值的分佈極度不平均時，同一個查詢對不同的參數有不同的最佳計畫：

```
 orders.status distribution (50M rows)

 done      ████████████████████████████████████████  47.5M  95.0%
 paid      ██                                         2.0M   4.0%
 refunded  ▏                                          0.45M  0.9%
 pending   ▏                                          0.05M  0.1%

 WHERE status = 'pending'  ->  index scan   (50K rows)
 WHERE status = 'done'     ->  seq scan     (47.5M rows)
```

如果應用程式用預備語句（prepared statement）而引擎快取了一份通用計畫，`pending` 與 `done` 就會共用同一個計畫，其中一個必然很慢。症狀是「同一個查詢，換個參數就慢一百倍」。

### 面試中的說法

「我會先看 `EXPLAIN ANALYZE` 裡估計列數與實際列數的差距。差距大的話，先確認統計值是不是過期，再看條件中的欄位是否有關聯或嚴重傾斜。確認資訊正確之後，才考慮加索引或改寫。」

---

## 七、分散式引擎：搬動資料才是成本

Spark、Trino、BigQuery、Snowflake 把資料切成很多份，分散在多台機器上平行處理。掃描與過濾可以各自獨立完成。但 `JOIN`、`GROUP BY`、`DISTINCT`、window function 需要把**相同鍵的列放到同一台機器**，這個重新分配的動作叫 **shuffle**：每一列依鍵的雜湊值，透過網路送到對應的分割。

Shuffle 是分散式查詢中最貴的操作，因為它要序列化、傳輸、有時還要落磁碟。分散式 SQL 的調校幾乎都圍繞著三件事：**少 shuffle、shuffle 少一點資料、讓 shuffle 之後的分割大小平均**。

### Broadcast join：小表不用 shuffle

一邊的表夠小時，引擎把整張小表複製到每一台機器上，大表就不必移動。Spark 的門檻由 `spark.sql.autoBroadcastJoinThreshold` 控制，預設 10 MB。事實表 JOIN 維度表通常都該走這條路。

如果計畫顯示大表 JOIN 小維度表卻用了 Sort-Merge Join，原因多半是引擎不知道那張表很小（沒有統計值），或它在過濾之後才變小。可以收集統計值，或用 hint 指定：`SELECT /*+ BROADCAST(d) */ ...`。反過來，被廣播的表其實很大時，會把 driver 或 executor 的記憶體撐爆。

### 資料傾斜：一個 task 拖住整個階段

Shuffle 依鍵分配資料。某一個鍵特別多時，持有它的那個分割就特別大：

```
 shuffle partitions for JOIN ON user_id  (200 partitions, 4 shown)

 p000  ██                               1.1M rows     12 s
 p001  ██                               1.0M rows     11 s
 p002  ██████████████████████████████   310M rows     47 min  <- user_id IS NULL
 p003  ██                               1.2M rows     13 s

 stage time = slowest task = 47 min; adding executors does not help
```

這正是開頭面試題最可能的答案：SQL 沒變，但某個鍵的資料量長大了。辨識方法是在 Spark UI 的 stage 頁面看 task 耗時的分佈——中位數 12 秒、最大值 47 分鐘，就是傾斜。加機器沒有用，因為同一個鍵的列必須在同一個分割。

用一個查詢確認是哪個鍵：

```sql
SELECT user_id, COUNT(*) AS n
FROM events
GROUP BY user_id
ORDER BY n DESC
LIMIT 20;
```

處理方式依原因而定：

| 原因 | 處理 |
|---|---|
| 鍵是 NULL 或預設值（`0`、`'unknown'`、空字串） | 這些列本來就配對不到，在 JOIN 前先濾掉，需要保留時事後 `UNION ALL` 回來 |
| 少數真實的熱門鍵（大客戶、機器人帳號） | 開啟 Spark AQE 的 skew join 處理（3.2 起 AQE 預設開啟），它會自動拆開過大的分割 |
| AQE 處理不了，或引擎沒有對應功能 | 把熱門鍵拆出來單獨處理（對小表做 broadcast），其餘照常，再 `UNION ALL` |
| 彙總時傾斜 | 兩階段彙總：先依（鍵, 隨機數）分組做部分彙總，再依鍵做最終彙總（salting） |

### 分區裁剪與動態裁剪

資料依欄位（通常是日期）分成不同目錄時，`WHERE dt = '2026-11-23'` 讓引擎只列出並讀取那一個目錄，稱為**分區裁剪（partition pruning）**。這是資料湖上效果最大的單一最佳化，前提是條件要 sargable（第四節）。

條件值要在執行時才知道的情況，例如事實表 JOIN 一張過濾過的日期維度表，Spark 與 Trino 支援**動態分區裁剪**：先算出維度表過濾後的鍵，再把它當成事實表的分區條件。計畫裡會出現 `dynamicpruning` 字樣。它沒有生效時，可以把日期範圍直接寫成事實表上的字面條件。

---

## 八、改寫清單

這些改寫都不改變結果，只減少讀取或搬動的資料量。

**1. 只選需要的欄位。** `SELECT *` 在欄式儲存上讀取所有欄位；一張 200 欄的表只需要 5 欄時，讀取量可以差 40 倍。它也讓 covering index 與 broadcast join 失效。

**2. 先過濾、先彙總，再 JOIN。** 把大表先彙總到 JOIN 需要的顆粒度，shuffle 的列數就大幅減少：

```sql
-- Before: joins 2B event rows to users, then aggregates.
SELECT u.country, COUNT(*) AS events
FROM events e JOIN users u ON u.user_id = e.user_id
WHERE e.event_ts >= DATE '2026-11-01'
GROUP BY u.country;

-- After: aggregates to one row per user first (2B rows -> ~5M), then joins.
WITH per_user AS (
  SELECT user_id, COUNT(*) AS events
  FROM events
  WHERE event_ts >= DATE '2026-11-01'
  GROUP BY user_id
)
SELECT u.country, SUM(p.events) AS events
FROM per_user p JOIN users u ON u.user_id = p.user_id
GROUP BY u.country;
```

**3. 只是篩選就用 `EXISTS`。** Semi join 找到第一個配對就停，也不會造成 fan-out，後面不必再用 `DISTINCT` 補救。

**4. `UNION ALL` 取代 `UNION`，拿掉不必要的 `DISTINCT`。** 兩者都需要對全部結果做雜湊或排序。`DISTINCT` 常被用來掩蓋 fan-out，應該修正 JOIN 而不是事後去重。

**5. 用 window function 取代自我連接。** 「每列與同組前一列比較」用 `LAG` 是一次排序；自我連接則是一次 JOIN，鍵有傾斜時還可能爆量。

**6. 大範圍的 `COUNT(DISTINCT)` 改用近似演算法。** 精確去重要把所有相異值集中比對。`APPROX_COUNT_DISTINCT`（Spark、BigQuery、Snowflake）與 `approx_distinct`（Trino）使用 HyperLogLog，以固定的少量記憶體換取誤差，典型的標準誤差約 2%（Trino 預設 2.3%，Spark 預設 5%，可調）。儀表板上的日活躍使用者通常可以接受；計費與對帳不行。

**7. 分頁用 keyset，不用大 `OFFSET`。** `OFFSET 1000000 LIMIT 50` 要先產生並丟掉 100 萬列。改用上一頁最後一列的鍵當條件，配合索引可以直接定位：

```sql
SELECT order_id, created_at, amount
FROM orders
WHERE (created_at, order_id) < ('2026-11-20 10:15:00', 884213)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

**8. `OR` 跨不同欄位時考慮拆成 `UNION ALL`。** `WHERE a = 1 OR b = 2` 常常無法同時利用兩個索引；拆成兩個查詢（第二個排除第一個已涵蓋的列）可以各自走索引。先看計畫，引擎已經處理得好就不必改。

---

## 九、症狀與診斷

| 症狀 | 先看什麼 | 常見原因 | 處理 |
|---|---|---|---|
| SQL 沒改，突然變慢 | 估計列數與實際列數 | 統計值過期；資料量跨過門檻導致計畫改變 | 重新收集統計值 |
| 換個參數就慢百倍 | 兩個參數各自的計畫 | 值分佈傾斜而共用同一個計畫 | 強制重新規劃，或拆成兩個查詢 |
| 全表掃描而且丟掉 99% 的列 | `Rows Removed by Filter` | 沒有索引，或條件不 sargable | 改寫條件；建立複合索引 |
| 有索引卻不用 | 條件的選擇率、欄位型別 | 留下的比例太高；隱含轉型；函數包住欄位 | 多半是正確決定；否則改寫條件 |
| Spark 階段卡在最後幾個 task | task 耗時的最大值與中位數 | 鍵傾斜，常見是 NULL 或預設值 | 濾掉無效鍵；AQE；拆出熱門鍵 |
| 大量 spill 或記憶體不足 | 每個分割的大小、JOIN 類型 | 分割太大；廣播了大表；`SELECT *` | 增加分割數；修正 join 策略；裁欄位 |
| 掃描量遠大於預期 | 被讀取的分區數 | 分區欄位被函數包住；缺少分區條件 | 改成 sargable；強制要求分區條件 |
| 輸出列數比輸入多很多 | JOIN 節點的輸入與輸出列數 | JOIN 鍵不唯一造成 fan-out | 先彙總到正確顆粒度再 JOIN |

排查順序固定是：**先量測（計畫與實際列數），再假設，一次只改一件事，然後再量一次**。沒有量測就改寫，是在碰運氣。

---

## 十、重點回顧與系列導航

- 最佳化器根據估計做決定。估計列數與實際列數的差距，是計畫中最重要的訊號。
- 索引只在條件留下少量資料時有用；複合索引把等值欄位放前面、範圍欄位放最後。
- 欄位不要被函數或運算包住。Sargable 的寫法同時決定了索引、分區裁剪與 min/max 統計值能否生效。
- Nested Loop、Hash、Sort-Merge 各有適用條件；範圍 JOIN 與錯誤的估計最容易導致災難性的計畫。
- 分散式引擎上，成本來自 shuffle。小表用 broadcast，傾斜的鍵要先找出來再個別處理。
- 「SQL 沒變卻變慢」的原因在資料：資料量、分佈，或過期的統計值。

**DE SQL 面試指南**

- [Part 1：核心觀念——執行順序、NULL 與顆粒度](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/)
- **Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜**（本篇）
- [Part 3：儲存與建模——存得便宜，查得到位](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/)
- [Part 4：資料轉換——冪等、增量與 MERGE](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/)
- [Part 5：正確性、交易、除錯與 Code Review](/posts/sql-interview-for-de-part5-correctness-transactions-review-zh/)

**延伸閱讀**

- PostgreSQL 文件：Using EXPLAIN、Planner Statistics、Multivariate Statistics、Indexes
- Apache Spark 文件：Performance Tuning（Adaptive Query Execution、Join Strategy Hints）
- Markus Winand, *SQL Performance Explained*（use-the-index-luke.com）
- Viktor Leis et al., "How Good Are Query Optimizers, Really?"（VLDB 2015）——基數估計誤差如何影響計畫品質
