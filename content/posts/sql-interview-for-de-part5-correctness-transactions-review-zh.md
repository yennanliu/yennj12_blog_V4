---
title: "DE SQL 面試指南 Part 5：正確性、交易、除錯與 Code Review"
date: 2026-11-24T09:04:00+08:00
draft: false
weight: 5
description: "資深與否的差別，在於能不能證明一個查詢是對的，以及看出別人的查詢哪裡會錯。本篇講隔離等級與並行更新、數字不對時的除錯流程、一個完整的 SQL code review 實例、時區與方言差異、安全與測試，最後附全系列的檢查清單。"
categories: ["all", "engineering"]
tags: ["RKK", "Interview", "Data Engineering", "SQL", "Transaction", "Isolation Level", "Code Review", "Debugging", "Data Quality", "Best Practices"]
authors: ["yen"]
readTime: "12 min"
series: ["sql-interview-for-de"]
---

> 多數人把 SQL 寫到「跑得出結果」就送出，數字看起來合理就當作正確。  
> 三個月後有人發現月報少算了每個月最後一天，而且沒有人說得出是從哪一版開始的。  
> 跑得出來與正確是兩回事，而錯誤的數字不會自己報錯。  
> 資深工程師的價值在於：**能證明查詢是對的，並且在 review 時看出它在什麼資料下會錯**。

這是「DE SQL 面試指南」的最後一篇。前四篇講怎麼寫（[Part 1](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/)）、怎麼跑得快（[Part 2](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/)）、怎麼存（[Part 3](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/)）、怎麼轉換（[Part 4](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/)）。本篇補上其餘在面試與實務中都會遇到的主題：並行與交易、除錯方法、code review、時間處理、方言差異、安全與測試。

---

## 面試情境

> **面試官**：「這是同事送審的查詢，用途是找出十月消費最高的 100 位使用者，要排除測試帳號，以及已核准退款的訂單。請你做 code review：指出問題、說明每個問題在什麼資料下會出錯，並給出修改後的版本。」
>
> ```sql
> SELECT DISTINCT u.user_id, u.country, SUM(o.amount) AS total
> FROM users u, orders o
> LEFT JOIN refunds r ON r.order_id = o.order_id
> WHERE u.user_id = o.user_id
>   AND DATE(o.created_at) BETWEEN '2026-10-01' AND '2026-10-31'
>   AND o.user_id NOT IN (SELECT user_id FROM test_accounts)
>   AND r.status <> 'approved'
> GROUP BY 1, 2
> ORDER BY 3 DESC
> LIMIT 100;
> ```

這個查詢可以執行，也會回傳 100 列看起來合理的資料。它至少有七個問題，其中三個會讓結果錯誤。第五節逐一說明。

---

## 一、核心問題：錯的數字不會報錯

程式的 bug 通常會讓程式當掉；SQL 的 bug 通常只是讓數字偏一點。沒有例外、沒有警告，報表照常產出。所以 SQL 的品質保證不能依賴「跑過了」，而要依賴三個習慣：

1. **寫的時候**：每一步都知道顆粒度，對 NULL、重複鍵、空集合三種情況有明確的處理。
2. **交付之前**：用獨立的方法驗證總數（對帳），而不是看結果「感覺合理」。
3. **Review 的時候**：不是問「這段 SQL 做了什麼」，而是問「什麼樣的資料會讓它出錯」。

本篇的每一節都是這三個習慣在不同面向的應用。

---

## 二、交易與隔離等級

**交易（transaction）** 把多個操作包成一個單位，保證 **ACID**：全部完成或全部不做（Atomicity）、不違反約束（Consistency）、並行的交易互不干擾（Isolation）、提交後不會遺失（Durability）。面試最常深入問的是 I。

多個交易同時執行時，可能出現以下現象：

| 現象 | 說明 |
|---|---|
| Dirty read | 讀到另一個交易尚未提交的資料，而它後來可能回滾 |
| Non-repeatable read | 同一個交易內，同一列讀兩次得到不同的值 |
| Phantom read | 同一個交易內，同一個條件查兩次，多出或少了列 |
| Write skew | 兩個交易各自讀取一組資料、各自做了單獨看合法的寫入，合起來卻違反規則 |

**隔離等級**規定允許哪些現象。等級越高，異常越少，但等待與重試越多：

| 隔離等級 | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| Read Uncommitted | 可能 | 可能 | 可能 |
| Read Committed | 不會 | 可能 | 可能 |
| Repeatable Read | 不會 | 不會 | 可能（標準定義） |
| Serializable | 不會 | 不會 | 不會 |

實作與標準有出入，這是面試中容易加分的地方：

- **預設等級不同。** PostgreSQL、Oracle、SQL Server 預設 Read Committed；MySQL InnoDB 預設 Repeatable Read。
- **多數資料庫用 MVCC。** MVCC（多版本並行控制）保留每列的多個版本，讓每個交易看到一份一致的快照，讀取不會擋住寫入。PostgreSQL 的 Repeatable Read 實際上是快照隔離：不會有 phantom read，但仍可能發生 write skew。
- **Serializable 會讓交易失敗。** 資料庫偵測到無法序列化的衝突時，會中止其中一個交易，應用程式必須重試。

### 這跟資料工程有什麼關係

**擷取時的一致性。** 從交易資料庫分別擷取 `orders` 與 `order_items` 兩張表，如果是兩個獨立的查詢，中間有新訂單提交，就會擷取到「有訂單明細、沒有訂單」的資料。把擷取放在同一個 Repeatable Read 交易中，兩張表才來自同一個時間點；或改用 CDC，依交易記錄的順序套用。

**長交易的代價。** 一個跑兩小時的擷取查詢，在 MVCC 資料庫中會讓這段時間內所有被更新的舊版本都不能回收，造成表膨脹，在複本上還可能因衝突而被取消。大量擷取應該在讀取複本上執行，並依鍵或時間分段。

**倉儲與 lakehouse 的寫入衝突。** Iceberg、Delta 這類格式採用樂觀並行控制：每個寫入者先產生新檔案，提交時檢查表在這段期間是否被別人改過，有衝突就失敗重試。兩個作業同時 MERGE 同一張表的相同分區時，其中一個會失敗。設計時讓並行的作業寫不同的分區，或把它們排成先後執行。

---

## 三、並行更新：lost update

兩個工作程序同時處理同一筆庫存：

```
 time   worker A                         worker B
 ────   ──────────────────────────────   ──────────────────────────────
  t1    SELECT stock  -> 1
  t2                                     SELECT stock  -> 1
  t3    UPDATE SET stock = 0
  t4                                     UPDATE SET stock = 0
        both succeed; two units sold, one unit existed
```

在 Read Committed 之下這完全合法，因為沒有任何一步讀到未提交的資料。這叫 **lost update**。三種修法：

```sql
-- 1. Atomic update: let the database do read-modify-write in one statement.
UPDATE inventory
SET    stock = stock - 1
WHERE  sku = 'A100' AND stock > 0;
-- Check the affected row count; 0 means out of stock.

-- 2. Pessimistic lock: hold the row until commit.
BEGIN;
SELECT stock FROM inventory WHERE sku = 'A100' FOR UPDATE;
-- ... application logic ...
UPDATE inventory SET stock = stock - 1 WHERE sku = 'A100';
COMMIT;

-- 3. Optimistic lock: detect that someone else changed the row.
UPDATE inventory
SET    stock = :new_stock, version = version + 1
WHERE  sku = 'A100' AND version = :version_read;
-- 0 rows affected means a concurrent change: re-read and retry.
```

能用第 1 種就用第 1 種：沒有來回、鎖持有的時間最短。衝突少時用樂觀鎖，衝突多時用悲觀鎖。

**死結（deadlock）** 發生在兩個交易各自持有對方需要的鎖。資料庫會偵測並中止其中一個。預防方法是讓所有交易以**相同的順序**取得鎖（例如一律依主鍵由小到大更新），並讓交易保持簡短。

同樣的競爭也出現在 DE 的工作中：兩個排程同時對同一個鍵做「先查是否存在，不存在就新增」，會新增兩筆。解法是唯一約束加上 upsert（Part 4），而不是在應用程式裡先查再寫。

---

## 四、除錯：數字不對時怎麼找

Part 1 的面試題是「營收多了 8%」。這類問題有固定的排查流程，核心是**找出數字第一次偏離的那一步**。

```
┌──────────────────────────────┐
│ 1 Agree on the definition    │  which statuses, which time zone, net or
│   and a trusted reference    │  gross? what number is it compared with?
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ 2 Shrink the problem         │  one day, one country, then one key whose
│                              │  result is wrong
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ 3 Count rows and distinct    │  after every CTE / join:
│   keys after every step      │  COUNT(*), COUNT(DISTINCT key), SUM(amount)
└──────────────┬───────────────┘
               ▼
        first step where the numbers diverge
               │
   ┌───────────┼─────────────────────────┐
   ▼           ▼                         ▼
┌──────────┐ ┌───────────────┐ ┌───────────────────────────┐
│ rows     │ │ rows shrank   │ │ same rows, different sum  │
│ grew     │ │               │ │                           │
│ fan-out: │ │ inner join or │ │ type or rounding, NULL in │
│ join key │ │ WHERE dropped │ │ an aggregate, time zone,  │
│ not      │ │ unmatched or  │ │ duplicated source rows    │
│ unique   │ │ NULL rows     │ │                           │
└──────────┘ └───────────────┘ └───────────────────────────┘
```

第 3 步的工具是一個逐步計數的查詢：

```sql
WITH base AS (
  SELECT * FROM orders
  WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+08'
    AND created_at <  TIMESTAMPTZ '2026-11-01 00:00:00+08'
),
with_user AS (
  SELECT b.*, u.country FROM base b JOIN users u ON u.user_id = b.user_id
),
with_pay AS (
  SELECT w.*, p.pay_id FROM with_user w JOIN payments p ON p.order_id = w.order_id
)
SELECT 'base' AS step, COUNT(*) AS n,
       COUNT(DISTINCT order_id) AS orders, SUM(amount) AS amt
FROM base
UNION ALL
SELECT 'with_user', COUNT(*), COUNT(DISTINCT order_id), SUM(amount)
FROM with_user
UNION ALL
SELECT 'with_pay', COUNT(*), COUNT(DISTINCT order_id), SUM(amount)
FROM with_pay;
```

讀法：

- `n` 與 `orders` 在某一步開始不相等：那一步發生了 fan-out。
- `orders` 在某一步變少：那個 JOIN 丟掉了沒有配對的訂單，要確認是不是預期行為。
- 列數都對、金額不對：往型別、四捨五入、NULL 與時區找。

找到偏離的步驟之後，挑一個具體的鍵（例如某一筆出現兩次的 `order_id`）把相關的列全部列出來。看到實際的資料，原因通常就很明顯。

**要避免的作法**：加上 `DISTINCT` 或調整條件，直到數字對上參考值。數字對上不代表邏輯正確，下個月換一批資料就會再錯一次。

---

## 五、Code review 實例

回到開頭的查詢。逐項檢查：

| # | 問題 | 什麼資料下會錯 | 嚴重度 |
|---|---|---|---|
| 1 | `r.status <> 'approved'` 寫在 `WHERE` | 沒有退款的訂單，`r.status` 是 NULL，比較結果是 UNKNOWN，整筆訂單被濾掉。結果只剩下「有退款但未核准」的訂單，與原意相反 | 結果錯誤 |
| 2 | JOIN 到 `refunds`（一對多）之後加總 `o.amount` | 一筆訂單有兩筆未核准的退款申請，金額被算兩次 | 結果錯誤 |
| 3 | `BETWEEN '2026-10-01' AND '2026-10-31'` 配合 `DATE()` | 這裡因為先轉成日期所以碰巧正確；但只要有人為了效能拿掉 `DATE()`，10 月 31 日 00:00 之後的資料就全部消失。另外沒有指定時區 | 脆弱 |
| 4 | `NOT IN (SELECT user_id FROM test_accounts)` | `test_accounts.user_id` 只要有一個 NULL，整個查詢回傳零列 | 結果錯誤（視資料而定） |
| 5 | `DATE(o.created_at)` 包住欄位 | 不影響正確性；但索引與分區裁剪失效，掃描整張表 | 效能 |
| 6 | `SELECT DISTINCT` 加在 `GROUP BY` 之上 | 沒有作用，只是多一次去重。它透露作者不確定結果的顆粒度 | 可讀性／效能 |
| 7 | `FROM users u, orders o` 混用逗號與明確 JOIN；`GROUP BY 1, 2`、`ORDER BY 3` | 有人在 `SELECT` 插入一個欄位，分組與排序就悄悄改變 | 可維護性 |
| 8 | `ORDER BY ... LIMIT 100` 沒有決勝欄位 | 第 100 名與第 101 名金額相同時，每次執行可能回傳不同的人 | 不可重現 |

另外要向作者確認兩件查詢本身看不出來的事：已取消或未付款的訂單算不算消費？「十月」依哪個時區？

修改後的版本：

```sql
-- Top 100 users by October 2026 spend (Asia/Taipei), paid orders only,
-- excluding test accounts and orders with an approved refund.
SELECT
  u.user_id,
  u.country,
  SUM(o.amount) AS total
FROM orders o
JOIN users u ON u.user_id = o.user_id
WHERE o.created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+08'
  AND o.created_at <  TIMESTAMPTZ '2026-11-01 00:00:00+08'
  AND o.status = 'paid'
  AND NOT EXISTS (
        SELECT 1 FROM test_accounts t WHERE t.user_id = o.user_id)
  AND NOT EXISTS (
        SELECT 1 FROM refunds r
        WHERE r.order_id = o.order_id AND r.status = 'approved')
GROUP BY u.user_id, u.country
ORDER BY total DESC, u.user_id
LIMIT 100;
```

兩個 `NOT EXISTS` 都是 anti join：不改變顆粒度（一列仍是一筆訂單），也不受 NULL 影響。時間條件用半開區間並寫明時區，同時可以使用 `created_at` 上的索引或分區。

### Review 時的檢查順序

1. **意圖**：查詢要回答什麼問題？輸出的顆粒度是什麼？
2. **正確性**：每個 JOIN 之後顆粒度有沒有變？外連接的條件位置對不對？NULL、重複鍵、空集合怎麼處理？時間邊界與時區？
3. **可重現性**：有沒有 `CURRENT_DATE`、沒有決勝欄位的排序、不確定的 `ROW_NUMBER`？
4. **效能**：條件是否 sargable？有沒有分區條件？有沒有 `SELECT *`？JOIN 前能不能先彙總？
5. **可維護性**：明確的欄位清單與 JOIN 語法、有意義的 CTE 名稱、註解說明「為什麼」而不是「做什麼」。

順序很重要。先談正確性，再談效能；一個很快的錯誤查詢沒有 review 效能的必要。回饋時說明「在什麼資料下會錯」，比只說「這樣寫不好」更容易被接受。

---

## 六、時間與時區

時間是 SQL 錯誤數字的第二大來源，僅次於 JOIN 的顆粒度。

**儲存用 UTC，呈現時才轉換。** 用帶時區的時間戳記型別存絕對時間點。只在報表需要「當地的一天」時轉換：

```sql
-- "Day" as seen in Taipei, from timestamps stored as absolute instants.
SELECT (created_at AT TIME ZONE 'Asia/Taipei')::date AS local_day,
       SUM(amount) AS revenue
FROM orders
GROUP BY 1;
```

台北時間 11 月 24 日 01:00 的訂單，UTC 是 11 月 23 日 17:00。依 UTC 日期分組，它算在 23 日；依台北日期，算在 24 日。兩份「每日營收」報表對不上，常常只是這個原因。

**時間範圍用半開區間。** `>= 起點 AND < 終點`。`BETWEEN` 包含兩端，用在時間戳記上有兩個問題：`BETWEEN '2026-10-01' AND '2026-10-31'` 漏掉 31 日 00:00 之後的一整天；改成 `AND '2026-11-01'` 又把 11 月 1 日 00:00:00 整點的資料算進兩個月。

**一天不一定是 24 小時。** 有日光節約時間的時區，一年有一天是 23 小時、一天是 25 小時。「加 24 小時」與「加 1 天」結果不同；以當地時間儲存而沒有時區資訊時，還會出現重複或不存在的時刻。

**分清楚三種時間。** 事件時間（事情發生的時刻）、擷取時間（資料進入系統的時刻）、處理時間（作業執行的時刻）。業務指標用事件時間；增量條件與除錯用擷取時間；處理時間不該出現在業務邏輯中（Part 4）。

---

## 七、常見反模式

| 反模式 | 問題 | 改法 |
|---|---|---|
| `SELECT *` 用在正式查詢或視圖 | 讀取不需要的欄位；上游加欄位時下游行為改變 | 明確列出欄位 |
| 用 `DISTINCT` 消除重複列 | 掩蓋 fan-out，而且金額相同的不同列會被誤刪 | 找出重複的來源，在 JOIN 前修正顆粒度 |
| `NOT IN (子查詢)` | 子查詢有 NULL 時回傳零列 | `NOT EXISTS` |
| 金額用浮點數 | `0.1 + 0.2 <> 0.3`，加總後對不上帳 | `DECIMAL`，或以最小貨幣單位存整數 |
| 對欄位套函數再比較 | 索引與分區裁剪失效 | 把運算移到常數那一邊 |
| `COUNT(*)` 用在外連接後 | 沒有配對的列也算 1 | `COUNT(右表的鍵)` |
| 比率用整數相除 | 在部分引擎得到 0 | 乘上 `1.0` 或明確轉型，分母用 `NULLIF` |
| `GROUP BY 1, 2` 用在正式程式碼 | `SELECT` 一改，分組就跟著變 | 寫出欄位名稱 |
| 子查詢裡的 `ORDER BY` | 外層不保證保留順序 | 只在最外層排序 |
| 依賴沒有 `ORDER BY` 的結果順序 | 順序取決於執行計畫，隨時會變 | 需要順序就明確排序 |
| `LIMIT` 沒有完整的排序鍵 | 同值的列每次回傳不同的組合 | 排序鍵加上唯一欄位 |
| 用字串比較日期或數字 | `'10' < '9'`；`'2026-1-5' > '2026-01-10'` | 使用正確的型別 |

---

## 八、方言差異

SQL 有標準，但每個引擎都有偏離。換工作或換引擎時，下面這幾項最容易造成「同樣的 SQL、不同的結果」：

| 行為 | PostgreSQL | MySQL 8 | Spark SQL | Trino | BigQuery | Snowflake |
|---|---|---|---|---|---|---|
| `1 / 2` | `0` | `0.5000` | `0.5` | `0` | `0.5` | `0.5` |
| 遞增排序時 NULL 的位置 | 最後 | 最前 | 最前 | 最後 | 最前 | 最後 |
| 過濾 window 結果 | 子查詢 | 子查詢 | 子查詢（Databricks SQL 有 `QUALIFY`） | 子查詢 | `QUALIFY` | `QUALIFY` |
| Upsert | `MERGE`（15+）、`ON CONFLICT` | `ON DUPLICATE KEY UPDATE` | `MERGE`（Delta、Iceberg） | `MERGE`（依連接器） | `MERGE` | `MERGE` |
| 字串串接 | `\|\|` | `CONCAT()`（`\|\|` 預設是邏輯 OR） | `\|\|`、`concat` | `\|\|` | `\|\|`、`CONCAT` | `\|\|` |
| 截斷到月 | `DATE_TRUNC('month', ts)` | `DATE_FORMAT(ts, '%Y-%m-01')` | `DATE_TRUNC('month', ts)` | `DATE_TRUNC('month', ts)` | `TIMESTAMP_TRUNC(ts, MONTH)` | `DATE_TRUNC('month', ts)` |

另外三個常見的差異：未加引號的識別字，PostgreSQL 會轉成小寫，Snowflake 轉成大寫，跨系統搬資料時欄位名稱會對不上；字串比較是否區分大小寫，取決於引擎與定序設定；空字串與 NULL 在 Oracle 中是同一個值，在其他引擎不是。

版本與設定會改變這些行為，表中是各引擎的預設情況。實務上的規則是：**不依賴預設行為**。明確寫出 `NULLS LAST`、明確轉型再相除、用標準語法，遷移時就少一類問題。面試時不必背整張表，但要說得出「這個行為各引擎不同，我會查文件並明確指定」。

---

## 九、安全、測試與可維護性

### 安全

- **參數化查詢。** 絕不把使用者輸入串接進 SQL 字串。`"... WHERE name = '" + input + "'"` 遇到 `x' OR '1'='1` 就回傳整張表，這是 SQL injection。用驅動程式的參數綁定；動態的表名或欄位名無法參數化，要比對白名單。
- **最小權限。** 管線帳號只拿它需要的表與操作。唯讀的分析帳號不該有 `DELETE`；每個管線用獨立的帳號，出事時才查得出是誰做的。
- **列與欄的存取控制。** 多租戶或含個資的表，使用資料庫提供的 row-level security 與欄位遮罩，而不是靠每個查詢記得加 `WHERE tenant_id = ...`。
- **個資最小化。** 分析用的表盡量不帶直接識別資訊；需要關聯時用加鹽雜湊後的鍵。刪除請求要能傳遞到所有衍生表，包含舊快照（Part 3 的清理作業）。

### 測試

SQL 可以測試，而且測試比想像中便宜：

- **資料測試**：在每次執行後檢查結果的性質——鍵唯一、必要欄位非 NULL、值在允許的集合內、外鍵都找得到對應。dbt 內建這四種測試，也可以直接寫成「應該回傳零列」的查詢（Part 4 第八節）。
- **單元測試**：準備幾列刻意設計的輸入，比對輸出。輸入至少涵蓋：重複鍵、NULL、沒有配對的列、同分、跨日與跨月的邊界。
- **回歸比對**：重構查詢時，用新舊兩版各跑一次，互相 `EXCEPT`，兩個方向都是空的才算等價：

```sql
(SELECT * FROM result_old EXCEPT SELECT * FROM result_new)
UNION ALL
(SELECT * FROM result_new EXCEPT SELECT * FROM result_old);
```

`EXCEPT` 是集合運算，不會發現「同一列多出現一次」的差異，所以另外比對兩邊的 `COUNT(*)`。

### 可維護性

- 一個 CTE 做一件事，名稱說明它的顆粒度（`orders_per_user`、`latest_event_per_session`）。
- 明確的 `JOIN ... ON`，每個欄位帶表別名，讀的人不用猜欄位來自哪張表。
- 註解寫業務規則與原因：「排除內部測試帳號，名單由財務維護」。SQL 本身已經說明了它在做什麼。
- 共用的邏輯（例如「有效訂單」的定義）放在一個視圖或模型中，不要在二十個查詢裡各寫一次。定義改變時，各自複製的版本一定會不一致。
- SQL 與其他程式碼一樣進版本控制、經過 review、有 CI 檢查。

---

## 十、系列總結與導航

把五篇濃縮成寫完每一個查詢之後自問的十個問題：

| # | 問題 | 出處 |
|---|---|---|
| 1 | 每一步之後，一列代表什麼？JOIN 有沒有改變它？ | Part 1 |
| 2 | NULL、重複鍵、沒有配對的列，各會發生什麼事？ | Part 1 |
| 3 | 同分時的排序是確定的嗎？ | Part 1 |
| 4 | 這個查詢讀了多少資料？條件能不能用上索引或分區裁剪？ | Part 2 |
| 5 | 估計列數與實際列數差多少？JOIN 鍵有沒有傾斜？ | Part 2 |
| 6 | 型別、分區、排序是對著最常見的查詢選的嗎？ | Part 3 |
| 7 | 重跑一次，結果會完全相同嗎？ | Part 4 |
| 8 | 增量邏輯會漏掉晚到、刪除或沒更新時間戳記的資料嗎？ | Part 4 |
| 9 | 時間範圍是半開區間嗎？時區寫明了嗎？ | Part 5 |
| 10 | 我用什麼獨立的方法驗證了這個數字？ | Part 5 |

本篇的重點：

- 隔離等級決定並行交易能看到什麼。知道預設等級，並用原子更新、鎖或版本欄位處理 lost update。
- 數字不對時，逐步計算列數、相異鍵數與加總，找出第一個偏離的步驟，不要調條件去湊數字。
- Code review 先看意圖與顆粒度，再看正確性、可重現性、效能、可維護性；回饋時說明在什麼資料下會錯。
- 時間以 UTC 儲存、以半開區間過濾，轉換時區時寫明是哪一個。
- 不依賴各引擎的預設行為；用參數化查詢與最小權限；用資料測試與回歸比對證明查詢正確。

**DE SQL 面試指南**

- [Part 1：核心觀念——執行順序、NULL 與顆粒度](/posts/sql-interview-for-de-part1-core-concepts-execution-order-zh/)
- [Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/)
- [Part 3：儲存與建模——存得便宜，查得到位](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/)
- [Part 4：資料轉換——冪等、增量與 MERGE](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/)
- **Part 5：正確性、交易、除錯與 Code Review**（本篇）

**延伸閱讀**

- PostgreSQL 文件：Transaction Isolation、Explicit Locking、Date/Time Types
- Hal Berenson et al., "A Critique of ANSI SQL Isolation Levels"（SIGMOD 1995）
- Martin Kleppmann, *Designing Data-Intensive Applications* 第 7 章（Transactions）
- dbt 文件：Data tests、Unit tests
- [DE 系統設計面試指南 Part 5：完整模擬面試與常見情境](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/)
