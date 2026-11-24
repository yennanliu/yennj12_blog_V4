---
title: "DE 系統設計面試指南 Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略"
date: 2026-11-24T09:30:00+08:00
draft: false
weight: 11
description: "把「重跑結果會一樣嗎」拆成冪等寫入、確定性計算與輸入釘選三件事：六種寫入策略的優缺點與失效條件、八種非確定性來源、外部副作用的 outbox 與冪等鍵，以及 90 天營收重算如何用影子表比對後原子切換，不弄壞下游儀表板。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Idempotency", "Backfill", "Iceberg", "Spark", "Data Quality", "AWS"]
authors: ["yen"]
readTime: "18 min"
series: ["de-system-design-interview"]
---

> 多數人被問到可重跑，答案是「用 INSERT OVERWRITE，日期用參數傳進來」。  
> 面試官接著問：「同一天跑兩次，營收差了 0.3%，為什麼？要重算 90 天，儀表板會不會看到一半新一半舊？已經寄出去的對帳單怎麼辦？」  
> 覆寫只保證**寫入**不重複，它不保證**計算**每次相同，也不保證**讀到的輸入**每次相同，更管不到寫進表以外的副作用。  
> 「重跑結果一樣」是三個條件同時成立，回補則是在這三個條件之上，再加一套切換與比對的流程。

這是「策略深入」組的第二篇，展開 [Part 5](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/) 結尾五個自問中的第二題：「這個作業重跑一次，結果會一樣嗎？」[Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/) 已經講過基本功——日期參數化、分區覆寫、以鍵 MERGE、先刪後寫、回補就是迴圈。本篇不重複這些，而是往下挖：每種寫入策略**什麼時候會壞**、計算結果為什麼會悄悄變動、輸入怎麼釘住、表外的副作用怎麼處理，以及大範圍回補怎麼做才不會讓下游看到中間狀態。

---

## 面試情境

> **面試官**：「我們有一個每日營收作業 `fct_daily_revenue`，從訂單、退款和匯率表算出每天、每個國家、每個通路的營收，下游有 CFO 儀表板、月營收表，以及每月寄給 1,200 家合作夥伴的分潤對帳單。財務剛發現：90 天前上線的版本把部分退款當成全額退款扣除，營收被低估。你要重算過去 90 天，而且過程中儀表板不能出現空白或半新半舊的數字。另外，我們試過把某一天重跑兩次，總額差了 0.3%。請說明你怎麼處理。」

---

## 一、核心問題：「重跑結果一樣」是三個條件

先把一個作業寫成函數。輸出由三樣東西決定：程式碼、輸入、參數。

```
output = f_code( input @ version , params )
              │          │            │
              │          │            └─ logical date, run config
              │          └─ which snapshot of each input table
              └─ git sha of the transform
```

「重跑結果一樣」需要三個條件同時成立，每一個對應一種常見的錯誤：

| 條件 | 意思 | 缺了它會怎樣 |
|---|---|---|
| **冪等寫入**（idempotent write） | 同一份結果寫 N 次，表的狀態與寫 1 次相同 | 重試產生重複列，或失敗時留下半套輸出 |
| **確定性計算**（deterministic compute） | 相同程式碼、相同輸入，算出相同的列 | 重跑兩次總額不同，像情境裡的 0.3% |
| **輸入釘選**（pinned input） | 「相同輸入」真的是同一份資料，而不是「現在的」那份 | 重跑讀到被修改過的維度表或晚到的資料 |

這三個條件也區分出三種不同的「重跑」，面試時先把它們分開講，答案會清楚很多：

- **重試（retry）**：作業失敗後再跑一次。程式碼與輸入都**應該**不變，目標是輸出完全相同。
- **重新處理（reprocess）**：輸入被更正了（晚到的退款補進來）。程式碼不變，輸入**刻意**變了。
- **回補（backfill）**：程式碼修了 bug。輸出**應該**改變，而且只在 bug 影響的地方改變。

情境裡的 90 天重算是第三種。它的難處在於：你要讓輸出改變，同時證明改變的只有該改的部分——而這要靠前兩種重跑都已經是確定的。如果同一天重跑本來就會差 0.3%，你就無法分辨回補後的差異哪些來自修 bug、哪些來自雜訊。

---

## 二、三個演進階段

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Idempotent writes (POC, one team, < 20 daily jobs)         ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────┐  ds = {{ ds }}   ┌─────────────┐  INSERT OVERWRITE
│ Airflow      │─────────────────▶│ Spark job   │──────────────────┐
└──────────────┘                  └──────┬──────┘                  ▼
                                         │ reads "latest"   ┌─────────────┐
                                         ▼                  │ fct_ table  │
                                  ┌─────────────┐           │ dt=...      │
                                  │ orders, fx  │           └─────────────┘
                                  └─────────────┘
```

**作法**：Part 2 的基本功。邏輯日期由排程器傳入、輸出覆寫整個日期分區。

**解決**：重試不再產生重複；回補可以寫成對日期的迴圈。

**仍存在的問題**：輸入讀的是「現在的」表，重跑舊日期會用到今天的匯率修正值與今天的客戶等級；計算中的平手排序、浮點加總順序沒處理；回補直接覆寫正式表，儀表板會在 90 個分區陸續被覆寫的那一個多小時內看到新舊混雜。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  Pinned inputs + determinism checks (MVP, 20-200 jobs)      ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ run manifest │──▶│ Spark job            │──▶│ commit: data +       │
│ ds, git sha, │   │ reads orders@snap_id │   │ manifest as snapshot │
│ input snaps  │   │ DECIMAL, tie-breaker │   │ properties (Iceberg) │
└──────────────┘   └──────────────────────┘   └──────────┬───────────┘
                                                         ▼
                                   ┌──────────────────────────────────┐
                                   │ CI: golden dataset, run twice,   │
                                   │ diff row count + checksum        │
                                   └──────────────────────────────────┘
```

**新增元件**：每次執行的 run manifest（參數、程式版本、每張輸入表的快照 ID）；以快照 ID 讀取輸入；CI 中的黃金資料集與「跑兩次比對」測試。

**成本與複雜度**：每張輸入表要能時間旅行或保留不可變分區，快照保留期因此拉長，儲存成本上升（見第五節）；每個作業多一個 manifest 欄位要維護。

**解決**：重試的輸出位元相同；非確定性在上線前就被測試抓到。

**仍存在的問題**：大範圍回補仍是就地覆寫；表外的副作用（寄信、呼叫付款 API）沒有被保護。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Shadow backfill + side-effect outbox (Scale, 200+ jobs)    ║
╚══════════════════════════════════════════════════════════════════════╝

            ┌──────────────────┐   ┌───────────────────┐
 new code ─▶│ shadow tables    │──▶│ diff vs prod      │
            │ (backfill queue) │   │ expected / not    │
            └────────┬─────────┘   └─────────┬─────────┘
                     │                       │ all diffs explained
                     ▼                       ▼
            ┌──────────────────┐   ┌───────────────────┐
            │ lineage: rebuild │──▶│ atomic swap of    │
            │ downstream shadow│   │ fct + agg tables  │
            │ in topo order    │   └─────────┬─────────┘
            └──────────────────┘             │
                                             ▼
                                   ┌───────────────────┐
                                   │ outbox + sender   │
                                   │ (idempotency key) │
                                   └───────────────────┘
```

**新增元件**：影子表與專用的回補佇列；自動化差異報告；依血緣（lineage）決定下游重算順序；副作用改走 outbox。

**成本與複雜度**：回補期間儲存與運算約加倍（影子與正式並存）；需要一套回補流程工具與審核步驟。

**解決**：下游永遠只看到「全舊」或「全新」；每一筆差異都有解釋才放行；重跑不會重寄信。

**仍存在的問題**：已經對外交付、無法撤回的數字（已關帳的月報、已付出的分潤）只能用調整分錄處理，見第七節。

| | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 重試輸出位元相同 | 不保證 | 是 | 是 |
| 回補中下游看到混合狀態 | 會 | 會 | 不會 |
| 能證明回補只改了該改的 | 否 | 部分（有 checksum） | 是（差異分類） |
| 副作用重複風險 | 高 | 高 | 低 |
| 額外儲存 | 0 | 快照保留期延長 | 回補期間約 2 倍 |

---

## 三、寫入策略：六種做法與各自的失效條件

Part 2 介紹了三種冪等寫入。完整的選單有六種，差別在**原子性的單位**與**讀者在寫入過程中看到什麼**。

| 策略 | 怎麼做 | 優點 | 缺點 | 何時選 | 何時壞 |
|---|---|---|---|---|---|
| 追加（append） | `INSERT INTO` | 最便宜，寫入不需讀舊資料 | 本身不冪等 | 原始事件落地層，且下游以事件 ID 去重 | 任何重試或回補都會重複 |
| 分區覆寫 | `INSERT OVERWRITE ... PARTITION (dt=...)` | 以分區為單位冪等，回補是迴圈 | 粒度是整個分區；一列錯也要重寫整天 | 依日期切分的事實表、聚合表 | 晚到資料散在多個分區；動態覆寫遇到空輸出（見下） |
| 以自然鍵 MERGE | `MERGE ... ON key` | 只動到有變的列；適合「目前狀態」表 | 新輸出中消失的鍵不會被刪除；同鍵多筆來源會報錯 | 維度表、CDC 同步表 | 鍵不穩定（重算後會變）；需要刪除語意卻沒處理 |
| 交易內先刪後寫 | `BEGIN; DELETE ...; INSERT ...; COMMIT;` | 任意範圍（不必對齊分區）；在倉儲中直覺 | 欄式倉儲的刪除只是標記，需要後續整理（例如 Redshift 的 `VACUUM`） | 不支援分區覆寫的倉儲、範圍不規則的修正 | 不在同一個交易內時，讀者看到空窗 |
| 暫存後原子切換 | 寫到新表或新路徑，再 `SWAP` / 改指標 | 整張表一次切換；舊版可以留著回退 | 需要兩倍空間；切換前後的權限、統計資訊要一起處理 | 整表重建、大範圍回補 | 用 S3 rename 當切換（S3 沒有原子 rename，是複製加刪除） |
| Table format 快照提交 | Iceberg / Delta 的 overwrite、replace、merge 都是一次 commit | 讀者只看到提交前或提交後的快照；可回退到舊快照 | 並行提交會衝突重試；快照過期後無法回退 | 資料湖上的所有正式表 | 數十個回補任務同時提交同一張表，重試次數用盡 |

幾個表格放不下、但面試官常追問的細節：

**分區覆寫的兩種模式。** Spark 的 `spark.sql.sources.partitionOverwriteMode` 預設是 `static`：如果 `INSERT OVERWRITE` 沒有寫明分區值，會刪掉**所有**符合分區規格的分區——沒寫規格就是整張表。改成 `dynamic` 後，只覆寫輸出中**出現的**分區。動態模式有個反向的坑：如果修正後某一天的正確輸出是空的（例如那天的訂單全部被判定為測試單），那個分區不會出現在輸出裡，舊的錯誤資料就原封不動地留著。回補時要嘛明確寫出分區值，要嘛先確認每個目標分區都有輸出。

**MERGE 不會刪除「消失的列」。** 修 bug 之後，某個 `(dt, country, channel)` 組合可能不該再存在。一般的 `WHEN MATCHED / WHEN NOT MATCHED` 只處理來源中有的鍵，目標中多出來的列會殘留。部分引擎支援 `WHEN NOT MATCHED BY SOURCE THEN DELETE`（例如 Delta Lake、SQL Server），但一定要把它限制在回補範圍內，否則範圍外的資料會全部被刪：

```sql
MERGE INTO fct_daily_revenue t
USING (SELECT * FROM staged_revenue
       WHERE dt BETWEEN '2026-08-26' AND '2026-11-23') s
ON  t.dt = s.dt AND t.country = s.country AND t.channel = s.channel
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
-- without the dt filter this deletes every row outside the window
WHEN NOT MATCHED BY SOURCE
     AND t.dt BETWEEN '2026-08-26' AND '2026-11-23' THEN DELETE;
```

對聚合表而言，這種情況通常代表分區覆寫比 MERGE 更適合：聚合結果是整天一起算出來的，就該整天一起換掉。

**「原子」是指讀者，不是指寫入者。** 判斷一個策略安不安全，問的是：寫到一半時，查詢會看到什麼？Hive 風格的表直接把檔案寫進 S3 分區路徑，寫到一半時查詢會讀到部分檔案。安全的替代是寫到新的 S3 前綴，完成後用 `ALTER TABLE ... PARTITION (dt=...) SET LOCATION` 把分區指過去——那是一次中繼資料更新。

**並行提交的衝突。** Iceberg 用樂觀並行控制：每次提交都基於某個快照，提交時若表已被別人更新，就重新驗證並重試。修改不同分區的覆寫通常能重試成功，但 90 個任務同時提交時，每個任務可能要重試很多次，超過 `commit.retry.num-retries`（預設 4）就失敗。實務上的解法是限制同時寫同一張表的任務數，或讓多天的結果在暫存區算完後，由一個任務一次提交。

---

## 四、非確定性的八個來源

情境裡「同一天跑兩次差 0.3%」幾乎一定來自下表其中一項。前兩項是**輸入**不同，其餘是**計算**不同。

| 來源 | 典型寫法 | 症狀 | 修法 |
|---|---|---|---|
| 系統時鐘 | `current_date`、`now()` 寫在過濾條件或欄位裡 | 補跑舊日期算到錯的日期；`processed_at` 每次不同 | 只用排程器傳入的邏輯日期；稽核時間欄位排除在比對之外 |
| 讀「最新」而非釘選版本 | `FROM fx_rates`（沒有指定版本） | 重跑時匯率或客戶等級已被修改 | 以快照 ID 或時間旅行讀取（第五節） |
| 平手排序 | `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at)` | 同一時間戳的兩筆退款，每次留下不同的一筆 | 排序鍵補上唯一欄位作為平手決勝 |
| 隨機與 UUID | `rand()` 抽樣、`uuid()` 當代理鍵 | 抽樣結果不同；代理鍵每次不同，下游 join 斷掉 | 固定種子；代理鍵改用自然鍵的雜湊 |
| 非確定的 UDF 與函數 | Python UDF 迭代 `set`；Spark 的 `first()`、`collect_list()` 沒有排序 | 字串組合、取第一筆的結果隨分區順序變動 | 明確排序；Python 的字串雜湊受 `PYTHONHASHSEED` 影響，不要依賴 set 的順序 |
| 外部 API 查詢 | 在作業中呼叫匯率 API、地理編碼 API | API 回應隨時間改變，或偶爾失敗回傳預設值 | 先把 API 結果落地成有版本的表，作業只讀那張表 |
| 執行時可變的維度表 | `JOIN customers`（目前的等級） | 客戶升級後，歷史營收被歸到新等級 | 用 SCD Type 2 做 as-of join：`event_time` 落在 `[valid_from, valid_to)` |
| 浮點加總順序 | `SUM(amount)`，`amount` 是 `DOUBLE` | 末幾位小數不同；分區數改變後差異更明顯 | 金額用 `DECIMAL`；或在比對時設容差 |

平手排序是最常見、也最難從程式碼看出來的一項。錯誤與修正並排：

```sql
-- nondeterministic: two refunds with the same updated_at tie
ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC)

-- deterministic: refund_id breaks the tie, same row wins every run
ROW_NUMBER() OVER (PARTITION BY order_id
                   ORDER BY updated_at DESC, refund_id DESC)
```

浮點加總不滿足結合律，這不是理論問題。IEEE 754 雙精度下：

```
(0.1 + 0.2) + 0.3 = 0.6000000000000001
0.1 + (0.2 + 0.3) = 0.6
```

Spark 的加總先在各分區內算部分和，再合併，合併順序取決於哪個 task 先完成。單筆誤差很小，但「跑兩次逐位元比對」會因此失敗，讓確定性測試失去意義。金額欄位一律用 `DECIMAL(18,2)` 或以最小貨幣單位存成整數，問題就消失。

**從症狀反推原因。** 對同一天跑兩次的輸出做比對，依下面的順序縮小範圍：

```
run A vs run B on dt=2026-11-10
        │
        ├─ row count differs?
        │     yes ─▶ dedup tie (ROW_NUMBER) or input read "latest"
        │            check: count rows per order_id with rank ties
        │
        ├─ same rows, SUM(amount) differs in last digits?
        │     yes ─▶ DOUBLE aggregation order  -> cast to DECIMAL
        │
        ├─ same rows, SUM differs by a real amount (0.3%)?
        │     yes ─▶ joined dimension changed between runs
        │            check: fx_rates / customers snapshot ids in manifest
        │
        └─ same sums, row-level hash differs?
              yes ─▶ rand()/uuid() or processed_at column in the output
```

情境的 0.3% 屬於第三類：總額差的是真實金額，不是末位小數。最可能的原因是 `fx_rates` 在兩次執行之間被財務修正過——作業讀的是「目前的」匯率表。這正是下一節要解決的問題。

---

## 五、釘選輸入：日期參數、水位線與快照 ID

「相同輸入」有三種實作，強度依序遞增：

**1. 邏輯日期參數。** Part 2 的做法：`WHERE order_date = '{{ ds }}'`。它釘住了**讀哪一段**，但沒有釘住**那一段的內容**。如果輸入表會被更新（退款晚到、匯率修正），同一個日期仍可能讀到不同資料。只有當輸入本身是不可變的日期分區時，日期參數才足夠。

**2. 水位線（high-water mark）。** 增量作業記錄「已經處理到哪裡」，例如 `max(updated_at)`。常見的錯誤是只存一個全域的「目前水位線」：今天重跑上週二的作業時，它讀到的是今天的水位線，處理的區間就完全不對。正確的做法是把每次執行的區間 `[lo, hi)` 記在那次執行的紀錄裡，重試時沿用記錄下來的區間；全域水位線只在資料成功提交時前進，而且**和資料在同一次提交中**寫入。Iceberg 可以在 Spark 寫入時用 `snapshot-property.<key>` 選項，把水位線寫進快照的摘要屬性，於是「資料」與「處理到哪裡」不會一個成功、一個失敗。

**3. 快照 ID。** 最強的釘選：直接記下每張輸入表在作業開始時的版本，用時間旅行讀取。

```sql
-- Spark 3.3+ with Iceberg; Delta Lake uses the same VERSION AS OF syntax
SELECT * FROM lake.orders   VERSION AS OF 8744213902117
SELECT * FROM lake.fx_rates VERSION AS OF 8744213902560
```

每次執行產生一份 run manifest，和輸出一起保存：

```
{
  "job": "fct_daily_revenue", "ds": "2026-11-10",
  "git_sha": "a41c9e2",
  "inputs": { "orders": 8744213902117, "refunds": 8744213902398,
              "fx_rates": 8744213902560 },
  "output_snapshot": 8744213903001
}
```

有了它，「重試」就是用同一份 manifest 再跑；「為什麼兩次結果不同」就是比對兩份 manifest 哪一欄不同。

**快照保留期是這個方法的上限。** 快照會過期：Iceberg 需要定期執行 `expire_snapshots` 清掉舊檔案，Delta Lake 的 `VACUUM` 預設只保留 7 天內不再被引用的檔案。要能釘選 90 天前的輸入，有兩種做法：

- 輸入層本身是**不可變的每日分區**（原始層只追加、每天一個分區），那麼「日期參數」就等於快照，不需要時間旅行。
- 對**manifest 引用到的每一個快照**打標籤並設定保留期，例如 Iceberg 的 `ALTER TABLE ... CREATE TAG ... AS OF VERSION ... RETAIN 400 DAYS`。標籤只保住它指向的那一個快照：只在月結時打一個標籤，其餘 29 天的 manifest 所引用的快照照樣會過期，90 天後的回補就讀不到。所以要嘛由作業在寫 manifest 時順手替輸入快照打標籤，要嘛把表的快照保留期（`history.expire.max-snapshot-age-ms`）設得比最長的回補範圍還長，並接受多出來的儲存成本。

**回補時該釘哪一版？** 這是一個業務問題，不是技術問題，面試時要主動提出：

| 選擇 | 意思 | 適用 |
|---|---|---|
| 釘原始版本 | 用當時執行的 manifest，只換程式碼 | 要證明「只修了 bug」；差異分析最乾淨 |
| 用目前最新版本 | 晚到的退款、修正過的匯率都納入 | 財務要的是「以目前所知」重編歷史數字 |

情境裡建議**分兩步**：先用原始輸入版本跑新程式碼，產出的差異就純粹來自修 bug，可以逐筆解釋；確認無誤後，再決定是否要用最新輸入重跑一次，把晚到資料的影響另外列出。兩種差異混在一起，就沒有人能說清楚數字為什麼變了。

---

## 六、表外的副作用：exactly-once 與 outbox

表的寫入可以覆寫、可以回退。寄出去的信、呼叫過的付款 API 不行。所以要先講清楚 exactly-once 的實際意思：

> **exactly-once 的「效果」= 至少一次的投遞 + 冪等或交易式的接收端。** 沒有系統能保證訊息只被「送出」一次，只能保證重送時接收端的狀態不會變第二次。

在表內，接收端是 table format 的提交或 Kafka 的交易（Flink 的兩階段提交 sink 就是這個組合）。在表外，接收端是別人的系統，你必須自己提供冪等的依據。

情境中的分潤對帳單是典型例子。如果作業的最後一步是「對每個合作夥伴寄信」，那麼回補 90 天會寄出 3 個月份 × 1,200 家 = 3,600 封信，其中大部分內容和上次一樣。做法是 **outbox 模式**：作業不直接寄信，而是把「應該寄什麼」寫進 outbox，和資料在同一次提交中完成；另一個獨立的發送程式讀 outbox、帶著冪等鍵呼叫外部系統，並記錄已發送。

```
┌──────────────────────────┐ same commit ┌──────────────────────────┐
│ fct_partner_statement    │◀───────────▶│ outbox                   │
│ month=2026-10            │             │ key = hash(partner_id,   │
└──────────────────────────┘             │   month, content_hash)   │
                                         └────────────┬─────────────┘
                                                      │ poll
                                                      ▼
┌──────────────────────────┐  skip if key  ┌──────────────────────────┐
│ sent_log (own ledger)    │◀──────────────│ sender                   │
│ key, sent_at, provider_id│   already     │ Idempotency-Key header   │
└──────────────────────────┘   present     └──────────────────────────┘
```

「同一次提交」要看儲存層做不做得到。Iceberg 的交易範圍是**單一張表**：對帳單表與 outbox 表分兩次提交，中間失敗就會留下有對帳單沒事件、或有事件沒對帳單的狀態。可行的做法有三種：把 outbox 欄位（冪等鍵、核准狀態）直接放在對帳單表的同一批資料列上，一次單表提交就涵蓋兩者，圖中的兩個方框其實是同一張表的兩組欄位；改用支援多表交易的儲存（Redshift、Postgres 這類倉儲或資料庫）；或使用 Project Nessie 這類支援多表提交的 catalog。

設計重點有五個：

- **冪等鍵包含內容雜湊。** 鍵是 `hash(partner_id, month, content_hash)`：重跑產出相同內容時鍵相同，發送程式直接略過；修 bug 後金額改變，鍵不同，才會進入「需要發更正」的流程，而不是悄悄重寄一封新的對帳單。
- **自己保存已發送紀錄。** 不少付款與通知服務支援 `Idempotency-Key` 標頭，但服務端只保留這些鍵一段有限的時間（例如 Stripe 文件說明鍵在至少 24 小時後可能被清除）。90 天的回補遠超過這個範圍，所以不能只依賴對方去重。
- **「已被對方接受、但自己沒記到」是不確定狀態，要有對帳的方法。** 發送程式在呼叫前先寫一筆 `sending`（意圖），成功後改成 `sent` 並記下對方回傳的 `provider_id`。若在兩者之間當掉，重啟時這筆是「不知道有沒有送出」：先用冪等鍵或自訂的參考編號向對方查詢，查得到就補記，查不到才重送。對方的鍵若已過期又無法查詢，就不能自動重送，要轉人工，或讓接收端自己去重（例如信件帶對帳單編號與版本，收件端系統以它為鍵）。
- **回補預設關閉副作用，而且由發送程式把關。** `side_effects=off` 只擋得住作業本身；outbox 的列還是會寫進去，而發送程式是獨立輪詢的。所以每一列要帶核准狀態：回補寫入的列是 `pending_approval`，發送程式**只送 `approved` 的列**。要不要發更正通知，由人在看過差異報告後把狀態改成 `approved` 或 `cancelled`。

---

## 七、回補策略：以 90 天營收重算為例

### 7.1 就地覆寫 vs 影子表

| | 就地覆寫（in-place） | 影子表 + 比對 + 切換（shadow） |
|---|---|---|
| 怎麼做 | 對 90 個日期分區逐一 `INSERT OVERWRITE` 正式表 | 寫到 `fct_daily_revenue__bf`，比對後一次發佈：只把這 90 個分區以一次提交換進正式表，或整表切換（影子表要先補齊範圍外的分區） |
| 下游在過程中看到 | 新舊混雜，持續約一小時 | 全舊，切換後全新 |
| 回退 | 靠 table format 快照回退；快照過期就沒了 | 舊表留著，切回去即可 |
| 能否先審核差異 | 不能，寫了就是正式資料 | 能，差異報告通過才切換 |
| 成本 | 1 倍 | 回補期間儲存加倍，多一次比對作業 |
| 何時選 | 少數幾天、修正明確、沒有對外交付 | 範圍大、金額相關、下游有人在看 |

營收、計費、對外報表一律用影子表。就地覆寫只適合「昨天的作業跑到一半失敗」這種重試。

### 7.2 情境的數字

假設與規模估算：

```
orders              3,000,000 rows/day, ~50 bytes/row in Parquet
90 days of input    3M x 90 = 270M rows ~ 13.5 GB      (small)
output              ~30,000 rows/day x 90 = 2.7M rows   (< 1 GB)

one day's job       ~4 min on an 8-node EMR cluster (assumed)
serial              90 x 4 min = 360 min = 6 h
parallel 6          ceil(90 / 6) = 15 waves x 4 min = 60 min (+ commit retries)

cluster price       m5.2xlarge on-demand, us-east-1:
                    $0.384 EC2 + $0.096 EMR = $0.48 / node-hour
8 nodes x 1 h       ~ $3.84 per backfill run
run twice + diff    ~ $8 to $10 in total
```

運算成本幾乎可以忽略。這題真正的成本在**正確性與協調**：下游有三個消費者、有一個月份已經關帳、有 1,200 封已寄出的對帳單。面試時把這個結論說出來，比把叢集規格算得更精細有價值。

### 7.3 執行流程

```
 1. freeze      pause the daily job's writes to the 90-day window
                (today's partition keeps running on the old path)
       │
 2. shadow      run new code into fct_daily_revenue__bf
                inputs pinned to the original manifests
                (whole-table swap only: seed partitions older than 90 d)
       │
 3. determinism run step 2 twice -> row count + checksum must match
       │
 4. diff        shadow vs prod per partition, classify every change
       │
 5. downstream  rebuild agg_monthly_revenue__bf from the shadow,
                in lineage order; statements -> outbox, side effects off
       │
 6. publish     pause the daily job; copy partitions it committed since
                step 2 into the shadow; swap fct + agg together;
                resume the daily job; dashboard cache refresh
       │
 7. corrections closed month: adjustment entry, not restatement
                partners: correction notice for changed keys only
```

幾個步驟需要展開：

**發佈時不能弄丟回補範圍以外的資料。** 整表切換有兩個容易漏掉的洞。第一，正式表通常有超過 90 天的歷史分區，影子表只算了 90 天，直接切換會讓更早的資料消失：要嘛先把範圍外的分區補進影子表，要嘛不換整張表，只把 90 個分區以一次原子提交換進正式表（Iceberg 的 `ReplacePartitions` 一次提交可以涵蓋多個分區）。第二，影子表建置的那一小時裡，每日作業仍在對正式表寫入今天的分區；影子表準備好之後才提交的分區，切換後就不見了。所以步驟 6 要先暫停每日作業、把這段期間新提交的分區補進影子表，再切換、再恢復。只換分區的做法沒有第二個問題，因為今天的分區根本不在被換的範圍內。

**順序與並行度。** 這個作業每天的輸出只依賴當天的輸入，90 天彼此獨立，可以並行；並行度受兩件事限制：叢集佇列（回補要用獨立佇列，不能擠掉每天早上的正式作業）與同一張表的提交衝突（第三節）。如果作業帶有**跨日狀態**——累計營收、客戶生命週期價值、依賴前一天輸出的 SCD 表——就必須依日期**循序**執行，因為第 N 天的正確輸入是重算後的第 N−1 天。面試時先問「這張表有沒有讀自己的前一個分區」，答案決定能不能並行。

**下游依血緣順序重算。** 月營收表讀 `fct_daily_revenue` 的 30 個分區，所以要在日表的影子完成後才算，而且也算到影子裡。如果只切換日表、月表晚一天才重算，CFO 儀表板上的日加總和月數字就會對不起來——這正是面試官說的「半新半舊」，只是發生在表與表之間，而不是分區之間。所以日表與月表要**一起切換**：Iceberg 單一表的提交是原子的，但多張表的同時切換需要額外機制，例如在支援交易式 DDL 的倉儲（如 Redshift）中把兩次 rename 放進同一個交易，或讓儀表板讀一個由發佈步驟一次更新的 view，或使用 Project Nessie 這類支援多表提交的 catalog。注意 Snowflake 的 DDL 會自動提交，兩個 `SWAP` 放進同一個交易並不會變成原子操作。

**已關帳的月份不重編。** 回補範圍裡如果有已經關帳、已交給稽核的月份，通常不能直接改寫那個月的數字。財務的慣例是在**當期**記一筆調整，並保留原始數字可追溯（這和 [Part 6](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/) 講的「關帳後的數字可重現」是同一件事）。資料平台要做的是：正式表存「以目前所知」的正確數字，另外有一張依關帳版本凍結的報表或一個標籤版本，兩者並存。

---

## 八、驗證：怎麼證明重跑結果一樣、回補只改了該改的

**跑兩次比對。** 確定性測試最直接的做法：同一份 manifest 跑兩次，比對每個分區的筆數、金額加總與一個與順序無關的列雜湊。

```sql
SELECT dt,
       COUNT(*)                                   AS row_cnt,
       SUM(revenue)                               AS revenue_sum,
       BIT_XOR(XXHASH64(country, channel, revenue)) AS row_hash
FROM fct_daily_revenue__bf
GROUP BY dt;
```

`XOR` 與順序無關，所以分區或 task 的排列不影響結果；但兩筆完全相同的列會互相抵消成 0，因此一定要搭配 `COUNT(*)` 一起比。比對時要排除 `processed_at` 這類稽核欄位，它們本來就應該每次不同。

**差異要分類，而不只是計數。** 回補的驗證問題不是「有沒有差異」，而是「差異是否都在預期之內」。這次 bug 只影響有部分退款的訂單，所以：

| 類別 | 條件 | 期望 |
|---|---|---|
| 預期變動 | 該 `(dt, country, channel)` 內有部分退款 | 新值 > 舊值，差額 = 部分退款被多扣的金額 |
| 不應變動 | 沒有任何部分退款 | **位元相同** |
| 新增或消失的列 | 舊表沒有或新表沒有的鍵 | 每一筆都要能說出原因 |

只要「不應變動」那一類出現任何差異，就代表這次修改碰到了 bug 以外的東西，或者作業本身還不確定——兩者都要先停下來查。這也是為什麼第四節的確定性必須先做好：否則這一類會充滿雜訊，整套分類就失效了。

**黃金資料集。** 在 CI 裡放一組小而刻意設計的輸入：同一時間戳的兩筆退款、部分退款、跨日的時區邊界、匯率缺值。每次改程式都跑一次，輸出要和存起來的期望結果完全相同。它抓得到平手排序與時區錯誤這類只在特定資料出現的問題，而正式資料量的「跑兩次比對」太貴，不適合每次提交都跑。

**監控訊號。** 在正式環境持續觀察的指標：同一個 `(job, ds)` 的不同執行之間 `row_hash` 是否改變（manifest 相同卻改變就是非確定性）；回補期間每日作業的佇列等待時間（回補是否擠到正式作業）；Iceberg 提交的重試次數（並行度是否過高）。

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| 影子表回補 vs 就地覆寫 | 下游只看到全舊或全新；差異可先審核；舊表可立即切回 | 就地覆寫期間下游看到混合狀態，寫了就無法先審 | 只修一兩天、重試性質、沒有對外交付的數字 |
| 聚合表用分區覆寫 vs MERGE | 整天一起算就整天一起換；消失的列自然被移除 | MERGE 不刪除新輸出中消失的鍵，要額外寫限定範圍的刪除 | 表很大但每次只有少數鍵改變，例如 CDC 同步的目前狀態表 |
| 以快照 ID 讀輸入 vs 只用日期參數 | 輸入表會被更新時，日期相同不代表內容相同 | 日期參數重跑會讀到之後的修正與晚到資料 | 輸入層本身就是不可變的每日分區 |
| 金額用 DECIMAL vs DOUBLE | 加總與順序無關，可以逐位元比對 | DOUBLE 的加總結果隨分區合併順序變動 | 科學量測、機器學習特徵等本來就容忍誤差，且不做位元比對的欄位 |
| 副作用走 outbox vs 作業內直接呼叫 | 重跑不重寄；發送與資料同一次提交 | 直接呼叫時，作業重試一次就寄兩次，失敗時又可能資料已寫、信沒寄 | 副作用本身冪等且無成本，例如刷新快取 |
| 回補用原始輸入版本 vs 最新版本 | 差異純粹來自程式修改，可以逐筆解釋 | 最新版本把晚到資料與 bug 修正混在一起 | 財務明確要求「以目前所知」重編，且已另外量化過晚到資料的影響 |

---

## 十、系統效應與系列導航

以情境的營收作業為例，從 Phase 1 走到 Phase 3 後的變化。數字沿用前文假設。

| 指標 | 改造前（Phase 1） | 改造後（Phase 3） |
|---|---|---|
| 同一天重跑兩次的差異 | 0.3%（讀到修正後的匯率） | 0（manifest 釘選、DECIMAL、平手決勝） |
| 90 天回補期間儀表板 | 約一小時新舊混雜，日表與月表對不上 | 切換前全舊、切換後全新 |
| 回補後能否說明每筆差異 | 不能，只知道總額變了 | 能，差異分成預期、不應變動、新增消失三類 |
| 回補對合作夥伴的影響 | 可能重寄 3,600 封對帳單 | 只對金額改變的鍵發更正，經人工核准 |
| 回補的運算成本 | 約 $4 | 約 $8–10（影子加上跑兩次比對） |
| 回退所需時間 | 依快照是否還在，可能無法回退 | 切回舊表，分鐘級 |

最後一個誠實的代價：Phase 3 需要回補工具、差異報告與審核流程，對 20 個作業的團隊是過度設計。**只在金額、計費、對外交付的表上全套使用**，其餘表停在 Phase 2 就夠了。

**本篇重點**

- 「重跑結果一樣」是三個條件：冪等寫入、確定性計算、輸入釘選，缺一項就會出現不同的症狀。
- 六種寫入策略的差別在原子性的單位與讀者在過程中看到什麼；動態分區覆寫遇到空輸出、MERGE 遇到消失的鍵，是兩個最常見的坑。
- 非確定性從症狀反推：筆數不同看平手與輸入版本，末位小數不同看浮點，真實金額不同看維度表。
- 表外副作用用 outbox 加上包含內容雜湊的冪等鍵，並自己保存已發送紀錄。
- 大範圍回補用影子表：釘原始輸入、跑兩次確認確定、差異分類、下游一起重算、一起切換。

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
- **Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略**（本篇）
- [Part 12：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)
- [Part 13：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part13-schema-evolution-zh/)
- [Part 14：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- Maxime Beauchemin, "Functional Data Engineering — a modern paradigm for batch data processing"（2018）
- Martin Kleppmann,《Designing Data-Intensive Applications》第 11 章（stream processing 與 exactly-once 的討論）
- Apache Iceberg 文件：Spark Procedures（`rollback_to_snapshot`、`expire_snapshots`）與 Branching and Tagging
- Apache Spark 文件：`spark.sql.sources.partitionOverwriteMode` 設定說明
- Chris Richardson, *Microservices Patterns*：Transactional Outbox 模式
- Stripe API 文件：Idempotent Requests
