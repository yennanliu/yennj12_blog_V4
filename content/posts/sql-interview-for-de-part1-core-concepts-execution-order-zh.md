---
title: "DE SQL 面試指南 Part 1：核心觀念——執行順序、NULL 與顆粒度"
date: 2026-11-24T09:00:00+08:00
draft: false
weight: 1
description: "SQL 面試很少考語法，考的是你能不能預測每一步之後「一列代表什麼」。本篇用邏輯執行順序、NULL 三值邏輯與 JOIN 顆粒度三個觀念，串起 window function、CTE 與五個必考題型，每題附可直接執行的寫法與常見錯誤。"
categories: ["all", "engineering"]
tags: ["RKK", "Interview", "Data Engineering", "SQL", "Window Function", "JOIN", "NULL", "PostgreSQL"]
authors: ["yen"]
readTime: "14 min"
series: ["sql-interview-for-de"]
---

> 多數人準備 SQL 面試的方法是刷一百題，背下每一題的寫法。  
> 面試官換一個資料表、多加一筆重複資料，背下來的寫法就給出錯的數字。  
> SQL 題目真正在考三件事：**子句的執行順序、NULL 怎麼比較、JOIN 之後一列代表什麼**。  
> 這三件事想清楚，一百題會收斂成五、六個題型，而且你能說出為什麼這樣寫是對的。

這是「DE SQL 面試指南」的第一篇。整個系列有五篇：本篇講核心觀念，[Part 2](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/) 講查詢效能，[Part 3](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/) 講儲存與建模，[Part 4](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/) 講資料轉換，[Part 5](/posts/sql-interview-for-de-part5-correctness-transactions-review-zh/) 講正確性、交易、除錯與 code review。

範例一律使用 PostgreSQL 語法，其他引擎（Spark SQL、Trino、BigQuery、Snowflake）有差異的地方會另外標註。全系列共用三張表：

```sql
users  (user_id, country, signup_date)
orders (order_id, user_id, status, amount, created_at)
events (event_id, user_id, event_type, event_ts)
```

---

## 面試情境

> **面試官**：「這個查詢要算每個國家上個月的營收。上線之後財務說數字比帳上多了大約 8%。資料沒有重複匯入。請你說說你會怎麼找原因。」
>
> ```sql
> SELECT u.country, SUM(o.amount) AS revenue
> FROM orders o
> JOIN users u    ON u.user_id = o.user_id
> JOIN payments p ON p.order_id = o.order_id
> WHERE o.created_at >= DATE '2026-10-01'
> GROUP BY u.country;
> ```

這題沒有語法錯誤，查詢跑得出來，數字卻不對。答案在第四節。

---

## 一、核心問題：SQL 考的是「一列代表什麼」

**顆粒度（grain）** 是一張表或一個中間結果裡「一列代表什麼」：一筆訂單、一個使用者一天、一次付款。寫 SQL 時最重要的習慣，是在每一步之後都說得出目前的顆粒度。

會出錯的 SQL 幾乎都是顆粒度在某一步悄悄改變了：

- JOIN 之後一列從「一筆訂單」變成「一筆訂單的一次付款」，`SUM(amount)` 就重複加總。
- `GROUP BY` 少寫一個欄位，兩個不同的群組被合成一個。
- `WHERE` 把 `LEFT JOIN` 補出來的 NULL 列濾掉，結果少了該出現的列。

所以面試中的第一句話應該是確認顆粒度：「`orders` 一列是一筆訂單嗎？一筆訂單會有多筆付款嗎？結果要一個國家一列，對嗎？」這句話本身就是面試官想看的訊號。

---

## 二、邏輯執行順序：寫的順序不是跑的順序

SQL 的書寫順序從 `SELECT` 開始，但引擎在**邏輯上**是從 `FROM` 開始計算的。

```
 written order            logical evaluation order
 ─────────────            ──────────────────────────────────────────────
 SELECT        ─┐         1  FROM / JOIN    build the row set
 FROM           │         2  WHERE          filter rows
 WHERE          │         3  GROUP BY       collapse rows into groups
 GROUP BY       ├───────▶ 4  HAVING         filter groups
 HAVING         │         5  window funcs   compute over surviving rows
 ORDER BY       │         6  SELECT         evaluate expressions, aliases
 LIMIT         ─┘         7  DISTINCT       remove duplicate rows
                          8  ORDER BY       sort (aliases visible here)
                          9  LIMIT/OFFSET   cut
```

這是語意上的順序，實際執行時最佳化器可以重排（Part 2 會講），但結果必須跟照這個順序算出來的一樣。記住這張圖，下面四個常見問題都能直接推導出來，不需要背。

**為什麼 `WHERE` 不能用 `SELECT` 的別名？** 因為 `WHERE` 在第 2 步，別名到第 6 步才存在。`ORDER BY` 在第 8 步，所以可以用。

**`WHERE` 和 `HAVING` 差在哪？** `WHERE` 在分組前濾「列」，`HAVING` 在分組後濾「群組」。能寫在 `WHERE` 的條件就不要寫在 `HAVING`：先濾掉的列不用參與分組，比較省。

```sql
SELECT user_id, SUM(amount) AS total
FROM orders
WHERE status = 'paid'            -- row filter, before grouping
GROUP BY user_id
HAVING SUM(amount) > 1000;       -- group filter, after grouping
```

**為什麼不能在 `WHERE` 裡寫 `ROW_NUMBER() ... = 1`？** Window function 在第 5 步才算，`WHERE` 早就跑完了。要包一層子查詢或 CTE；Snowflake、BigQuery、Databricks SQL、DuckDB 則提供 `QUALIFY` 子句，專門用來過濾 window function 的結果。

**Window function 看得到被 `WHERE` 濾掉的列嗎？** 看不到。它只對第 2–4 步留下來的列計算。想要「先算排名再篩選」，篩選條件必須放在外層查詢。

---

## 三、NULL：三值邏輯

NULL 的意思是「不知道」，不是空字串也不是 0。任何值跟 NULL 比較，結果不是 TRUE 也不是 FALSE，而是第三個值 **UNKNOWN**。`WHERE` 只留下結果為 TRUE 的列，所以 UNKNOWN 的列會被濾掉。

| 運算式 | 結果 | 說明 |
|---|---|---|
| `NULL = NULL` | UNKNOWN | 兩個「不知道」不能說相等，要用 `IS NULL` |
| `NULL <> 1` | UNKNOWN | 所以 `WHERE col <> 1` 不會回傳 NULL 列 |
| `TRUE OR NULL` | TRUE | 其中一邊已經是 TRUE |
| `FALSE AND NULL` | FALSE | 其中一邊已經是 FALSE |
| `TRUE AND NULL` | UNKNOWN | 結果取決於未知的那一邊 |
| `1 + NULL` | NULL | 算術運算遇到 NULL 就是 NULL |

由此衍生出五個在面試中常見的陷阱。

**1. `NOT IN` 遇到 NULL 會回傳零列。**

```sql
-- If blocked_users.user_id contains even one NULL, this returns nothing.
SELECT * FROM users
WHERE user_id NOT IN (SELECT user_id FROM blocked_users);
```

`x NOT IN (1, 2, NULL)` 等於 `x <> 1 AND x <> 2 AND x <> NULL`。最後一項永遠是 UNKNOWN，整個條件就不可能是 TRUE。改用 `NOT EXISTS`，它只檢查「有沒有符合的列」，不受 NULL 影響：

```sql
SELECT * FROM users u
WHERE NOT EXISTS (
  SELECT 1 FROM blocked_users b WHERE b.user_id = u.user_id
);
```

**2. `COUNT(*)` 與 `COUNT(col)` 不同。** `COUNT(*)` 算列數，`COUNT(col)` 只算 `col` 不是 NULL 的列，`COUNT(DISTINCT col)` 也忽略 NULL。

**3. 彙總函數忽略 NULL。** `AVG(score)` 的分母是非 NULL 的列數。三筆資料 `10, NULL, 20` 的平均是 15，不是 10。如果 NULL 應該當成 0，要明確寫 `AVG(COALESCE(score, 0))`，而且要先問清楚業務上哪一種才對。

**4. JOIN 的鍵是 NULL 時不會配對。** `a.key = b.key` 在任一邊為 NULL 時是 UNKNOWN，所以兩邊都是 NULL 的列不會被連起來。需要把 NULL 視為相等時用 `IS NOT DISTINCT FROM`（PostgreSQL、Snowflake、BigQuery、Trino 都支援；Spark SQL 另有 `<=>`）。

**5. `GROUP BY` 把所有 NULL 視為同一組。** 這跟第 1 點的比較規則不一致，但標準就是這樣定的：分組和 `DISTINCT` 把 NULL 當成同一個值。

NULL 的排序位置則因引擎而異：PostgreSQL 與 Snowflake 把 NULL 視為最大，MySQL 與 SQL Server 視為最小。需要固定行為時寫明 `ORDER BY col NULLS LAST`。

---

## 四、JOIN 與顆粒度

### JOIN 的種類

| 種類 | 保留哪些列 | 典型用途 |
|---|---|---|
| `INNER JOIN` | 兩邊都配對到的列 | 只要有對應資料的紀錄 |
| `LEFT JOIN` | 左表全部，右表沒配對到補 NULL | 「所有使用者，以及他們的訂單（如果有）」 |
| `FULL OUTER JOIN` | 兩邊全部 | 對帳：找出只存在於其中一邊的紀錄 |
| `CROSS JOIN` | 兩邊所有組合 | 產生日期 × 維度的完整骨架 |
| Semi join（`EXISTS`） | 左表中有配對的列，**不重複** | 「下過單的使用者」 |
| Anti join（`NOT EXISTS`） | 左表中沒有配對的列 | 「從未下單的使用者」 |

Semi join 與 `INNER JOIN` 的差別就是顆粒度：一個使用者有 5 筆訂單，`INNER JOIN` 回傳 5 列，`EXISTS` 回傳 1 列。只是要「篩選」而不需要右表的欄位時，用 `EXISTS` 才不會改變顆粒度。

### Fan-out：面試情境的答案

回到開頭那題。假設一筆訂單分兩次付款：

```
 orders                         payments
 ┌──────────┬────────┐          ┌────────┬──────────┬──────┐
 │ order_id │ amount │          │ pay_id │ order_id │ paid │
 ├──────────┼────────┤          ├────────┼──────────┼──────┤
 │ o1       │ 100    │          │ p1     │ o1       │ 60   │
 └──────────┴────────┘          │ p2     │ o1       │ 40   │
                                └────────┴──────────┴──────┘
          orders JOIN payments ON order_id
 ┌──────────┬────────┬────────┬──────┐
 │ order_id │ amount │ pay_id │ paid │   grain is now one row per PAYMENT
 ├──────────┼────────┼────────┼──────┤
 │ o1       │ 100    │ p1     │ 60   │   SUM(amount) = 200   (wrong)
 │ o1       │ 100    │ p2     │ 40   │   SUM(paid)   = 100   (right)
 └──────────┴────────┴────────┴──────┘
```

JOIN 到一對多的表之後，顆粒度從「一筆訂單」變成「一次付款」，訂單金額被重複加總。這叫 **fan-out**。8% 的差距代表大約有 8% 的訂單金額落在多次付款的訂單上。

修法有兩種，依需求選：

```sql
-- (a) You only need to know whether a payment exists: use a semi join.
SELECT u.country, SUM(o.amount) AS revenue
FROM orders o
JOIN users u ON u.user_id = o.user_id
WHERE o.created_at >= DATE '2026-10-01'
  AND EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)
GROUP BY u.country;

-- (b) You need payment columns: aggregate payments to order grain first.
WITH pay AS (
  SELECT order_id, SUM(paid) AS paid_total
  FROM payments
  GROUP BY order_id
)
SELECT u.country, SUM(o.amount) AS revenue, SUM(pay.paid_total) AS collected
FROM orders o
JOIN users u ON u.user_id = o.user_id
JOIN pay     ON pay.order_id = o.order_id
WHERE o.created_at >= DATE '2026-10-01'
GROUP BY u.country;
```

不要用 `SUM(DISTINCT o.amount)` 來「修」：兩筆不同的訂單剛好都是 100 元時，它會只算一次。`DISTINCT` 蓋掉的是症狀，顆粒度的問題還在。

驗證的方法是比較 JOIN 前後的列數。`SELECT COUNT(*), COUNT(DISTINCT order_id)` 兩個數字不相等，就代表發生了 fan-out。

### LEFT JOIN 被 WHERE 變成 INNER JOIN

```sql
-- Intent: every user, with their paid-order count (0 if none).
SELECT u.user_id, COUNT(o.order_id) AS paid_orders
FROM users u
LEFT JOIN orders o ON o.user_id = u.user_id
WHERE o.status = 'paid'          -- bug: removes users with no orders
GROUP BY u.user_id;
```

沒有訂單的使用者，`o.status` 是 NULL，`NULL = 'paid'` 是 UNKNOWN，整列被 `WHERE` 濾掉。右表的條件要寫在 `ON` 裡：

```sql
LEFT JOIN orders o ON o.user_id = u.user_id AND o.status = 'paid'
```

規則是：**`ON` 決定怎麼配對，`WHERE` 決定配對完留下哪些列**。對 `INNER JOIN` 兩者結果相同，對外連接則不同。注意這裡用 `COUNT(o.order_id)` 而不是 `COUNT(*)`，沒有訂單的使用者才會得到 0 而不是 1。

---

## 五、彙總：GROUP BY 與條件彙總

`GROUP BY` 之後，`SELECT` 裡的每個欄位只能是分組鍵或彙總函數的結果。原因是一組有多列，引擎不知道該挑哪一列的值。

最實用的技巧是**條件彙總**：用一次掃描算出多個指標，取代多個子查詢各掃一次。

```sql
SELECT
  user_id,
  COUNT(*)                                          AS orders,
  COUNT(*) FILTER (WHERE status = 'paid')           AS paid_orders,
  SUM(amount) FILTER (WHERE status = 'paid')        AS paid_amount,
  SUM(CASE WHEN status = 'refunded' THEN amount ELSE 0 END) AS refunded_amount
FROM orders
GROUP BY user_id;
```

`FILTER` 是標準 SQL 語法，PostgreSQL、Trino、Spark SQL 3、DuckDB 支援；`SUM(CASE WHEN ...)` 則到處都能用。把列轉成欄（pivot）也是同一招。

兩個細節：

- `SUM` 沒有任何符合的列時回傳 NULL，不是 0。報表需要 0 時包一層 `COALESCE`。
- 比率要小心整數除法。PostgreSQL、Trino、SQL Server 的 `1 / 2` 是 `0`；MySQL、BigQuery、Snowflake、Spark SQL 回傳 `0.5`。可攜的寫法是 `paid_orders * 1.0 / NULLIF(orders, 0)`，`NULLIF` 順便避免除以零。

要同時算小計與總計時，用 `GROUP BY GROUPING SETS ((country, status), (country), ())`，一次掃描產生三個層級，比 `UNION ALL` 三個查詢省。

---

## 六、Window Function：不壓縮列的彙總

`GROUP BY` 把一組列壓成一列。Window function 也對一組列計算，但**每一列都保留**，計算結果附在每一列上。這是 DE 面試中出現頻率最高的主題。

一個 window 由三個部分組成：

```sql
SUM(amount) OVER (
  PARTITION BY user_id                                -- which rows form a group
  ORDER BY created_at, order_id                       -- order inside the group
  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW    -- frame: which rows to use
)
```

### 三個排名函數

分數為 100、90、90、80 的四列：

| 分數 | `ROW_NUMBER()` | `RANK()` | `DENSE_RANK()` |
|---|---|---|---|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

選哪一個取決於題目怎麼處理同分：「每組取一筆」用 `ROW_NUMBER`；「前三名，同分並列」用 `RANK`；「第二高的薪資是多少」用 `DENSE_RANK`。面試時先問同分規則，再選函數。

`ROW_NUMBER` 遇到同分時，誰排前面是不確定的，同一個查詢跑兩次可能挑出不同的列。在 `ORDER BY` 加上唯一的欄位當決勝條件（例如 `order_id`），結果才可重現。

### Frame 的預設值是陷阱

寫了 `ORDER BY` 卻沒寫 frame 時，預設是 `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`。`RANGE` 會把排序鍵**相同**的列視為同一批（peers），一起納入計算。

```sql
-- Two orders on the same day both show the full-day running total.
SUM(amount) OVER (ORDER BY created_at::date)
```

要逐列累加，明確寫 `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`，並在 `ORDER BY` 加決勝欄位。

同樣的原因讓 `LAST_VALUE` 看起來「壞掉」：預設 frame 只到目前這一列，所以它回傳的就是目前這一列。要拿分組的最後一筆，frame 要寫到 `UNBOUNDED FOLLOWING`，或改用 `FIRST_VALUE` 配合反向排序。

### LAG 與 LEAD

`LAG(col)` 取前一列的值，`LEAD(col)` 取後一列。用來算與前一期的差、兩個事件的間隔，取代自我連接（self join）：

```sql
SELECT
  month,
  revenue,
  revenue - LAG(revenue) OVER (ORDER BY month) AS mom_change,
  revenue * 1.0
    / NULLIF(LAG(revenue, 12) OVER (ORDER BY month), 0) - 1 AS yoy_growth
FROM monthly_revenue;
```

`LAG(revenue, 12)` 假設每個月都有一列。中間缺月份時，往前數 12 列就不是去年同月。資料可能有缺口時，先用日期骨架表 `LEFT JOIN` 補齊，或改用以日期為條件的自我連接。

---

## 七、CTE、子查詢與集合運算

**CTE（Common Table Expression，`WITH` 子句）** 把一個子查詢命名，讓查詢可以由上而下閱讀。它主要是可讀性工具：每個 CTE 做一件事、有一個明確的顆粒度。

CTE 會不會被重複計算，取決於引擎。PostgreSQL 12 之前，CTE 一律先物化成暫存結果，外層的條件推不進去；12 之後，只被引用一次且沒有副作用的非遞迴 CTE 會被展開成子查詢，可用 `MATERIALIZED` / `NOT MATERIALIZED` 明確指定。多數分析引擎會把 CTE 展開，所以同一個 CTE 被引用兩次時可能被算兩次。這在面試中值得主動提一句。

**相關子查詢（correlated subquery）** 是指內層查詢引用外層的欄位。語意上它對外層每一列執行一次；最佳化器通常能把它改寫成 JOIN，但不保證。`EXISTS` 形式的相關子查詢幾乎都能被改寫成 semi join，可以放心用；放在 `SELECT` 清單裡的純量子查詢則比較容易真的逐列執行。

**集合運算**有一個重點：`UNION` 會去除重複，需要排序或雜湊整個結果；`UNION ALL` 只是把兩邊接起來。確定兩邊不重複，或本來就要保留重複時，一律用 `UNION ALL`。`EXCEPT` 與 `INTERSECT` 適合拿來對帳——兩張表互相 `EXCEPT` 都是空的，就代表內容相同（它們把 NULL 視為相等，這一點比 JOIN 方便）。

---

## 八、五個必考題型

### 1. 去重：每個鍵保留最新一筆

```sql
SELECT *
FROM (
  SELECT e.*,
         ROW_NUMBER() OVER (
           PARTITION BY event_id
           ORDER BY event_ts DESC, ingested_at DESC
         ) AS rn
  FROM events_raw e
) t
WHERE rn = 1;
```

這是 DE 工作中最常寫的一段 SQL。要說明的是「最新」怎麼定義，以及排序鍵是否唯一。

### 2. 每組前 N 名

結構與上一題相同，把條件改成 `rn <= 3`；同分要並列時把 `ROW_NUMBER` 換成 `RANK` 或 `DENSE_RANK`。

### 3. 累計與移動平均

```sql
SELECT
  dt,
  revenue,
  SUM(revenue) OVER (
    ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS running_total,
  AVG(revenue) OVER (
    ORDER BY dt ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS ma_7d
FROM daily_revenue;
```

`6 PRECEDING` 是「前 6 列」，不是「前 6 天」。某一天沒有資料時，七列就涵蓋超過七天。前六天的 `ma_7d` 也只用了不足七列計算，報表上通常要標示或排除。

### 4. Gaps and islands：連續登入天數

要找出每個使用者連續登入的區段。關鍵觀察是：在連續的日期中，「日期」減去「該列的序號」會得到同一個值。

```
 login_date   row_number   date - row_number
 2026-11-01       1          2026-10-31   ┐
 2026-11-02       2          2026-10-31   ├ island A, streak = 3
 2026-11-03       3          2026-10-31   ┘
 2026-11-06       4          2026-11-02   ┐ island B, streak = 2
 2026-11-07       5          2026-11-02   ┘
```

```sql
WITH days AS (
  SELECT DISTINCT user_id, event_ts::date AS login_date
  FROM events
  WHERE event_type = 'login'
),
grouped AS (
  SELECT user_id, login_date,
         login_date - (ROW_NUMBER() OVER (
           PARTITION BY user_id ORDER BY login_date
         ))::int AS island
  FROM days
)
SELECT user_id,
       MIN(login_date) AS streak_start,
       MAX(login_date) AS streak_end,
       COUNT(*)        AS streak_days
FROM grouped
GROUP BY user_id, island;
```

第一個 CTE 的 `DISTINCT` 不能省：同一天登入兩次會讓序號多跳一格，把一個連續區段切成兩段。這一步就是在把顆粒度固定成「一個使用者一天一列」。

### 5. Sessionization：把事件切成工作階段

規則是「同一個使用者，兩個事件間隔超過 30 分鐘就算新的工作階段」。先用 `LAG` 標出每個新階段的起點，再用累計加總把起點變成階段編號：

```sql
WITH flagged AS (
  SELECT user_id, event_id, event_ts,
         CASE
           WHEN LAG(event_ts) OVER w IS NULL
             OR event_ts - LAG(event_ts) OVER w > INTERVAL '30 minutes'
           THEN 1 ELSE 0
         END AS is_new_session
  FROM events
  WINDOW w AS (PARTITION BY user_id ORDER BY event_ts, event_id)
)
SELECT user_id, event_id, event_ts,
       SUM(is_new_session) OVER (
         PARTITION BY user_id ORDER BY event_ts, event_id
         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS session_seq
FROM flagged;
```

「標記邊界，再累計加總」這個兩步驟的手法，可以解決所有「依條件把連續的列分組」的題目，第 4 題也可以用它來寫。

---

## 九、答題流程

寫 SQL 題時依這個順序進行，每一步都說出來：

1. **確認輸入的顆粒度與鍵。** 每張表一列代表什麼？鍵是否唯一？哪些欄位可能是 NULL？
2. **確認輸出的顆粒度。** 結果一列代表什麼？沒有資料的群組要不要出現（決定用 `INNER` 還是 `LEFT JOIN`）？
3. **問邊界條件。** 同分怎麼排？時間區間含不含結尾？時區是哪一個？
4. **由內而外寫，一個 CTE 一個顆粒度。** 先寫出最內層的資料集，再往外疊。
5. **用小資料驗證。** 拿兩三列在腦中跑一遍，特別檢查重複鍵、NULL、空群組三種情況。
6. **最後才談效能。** 說明資料量大時哪一步最貴，會怎麼改（Part 2 的內容）。

先寫出正確的版本，再談最佳化。一個快但數字錯的查詢，在面試與正式環境中都沒有價值。

---

## 十、重點回顧與系列導航

- 每一步之後都說得出「一列代表什麼」。顆粒度改變而沒有察覺，是錯誤數字的主要來源。
- 邏輯順序是 `FROM → WHERE → GROUP BY → HAVING → window → SELECT → DISTINCT → ORDER BY → LIMIT`；別名、`HAVING`、`QUALIFY` 的規則都由此推導。
- NULL 的比較結果是 UNKNOWN。`NOT IN` 改用 `NOT EXISTS`，分清楚 `COUNT(*)` 與 `COUNT(col)`。
- JOIN 到一對多的表之前，先把它彙總到目標顆粒度；右表的條件放 `ON` 而不是 `WHERE`。
- Window function 明確寫出 frame，排序鍵加上唯一的決勝欄位。
- 去重、每組前 N、累計、gaps and islands、sessionization 五個題型涵蓋大部分的考題。

**DE SQL 面試指南**

- **Part 1：核心觀念——執行順序、NULL 與顆粒度**（本篇）
- [Part 2：查詢效能——執行計畫、索引、統計值與資料傾斜](/posts/sql-interview-for-de-part2-query-optimization-execution-plan-zh/)
- [Part 3：儲存與建模——存得便宜，查得到位](/posts/sql-interview-for-de-part3-storage-modeling-cost-zh/)
- [Part 4：資料轉換——冪等、增量與 MERGE](/posts/sql-interview-for-de-part4-transform-incremental-merge-zh/)
- [Part 5：正確性、交易、除錯與 Code Review](/posts/sql-interview-for-de-part5-correctness-transactions-review-zh/)

**延伸閱讀**

- PostgreSQL 文件：SELECT、Window Functions、WITH Queries (Common Table Expressions)
- Markus Winand, *SQL Performance Explained* 與 modern-sql.com（`FILTER`、`IS DISTINCT FROM`、window frame 的各引擎支援表）
- [DE 系統設計面試指南 Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
