---
title: "DE 系統設計面試指南 Part 10：誰在查、要多新鮮、要多準——依新鮮度選架構"
date: 2026-11-24T09:00:00+08:00
draft: false
weight: 10
description: "新鮮度不是一個可以隨意調的旋鈕，而是一條有斷崖的成本曲線。從 T+1、數小時、15 分鐘、1 分鐘到秒級，逐層比較架構、怎麼量新鮮度、成本、維運負擔與正確性代價，並示範如何回應「把日報改成即時」的要求。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Data Freshness", "SLA", "Streaming", "Micro-batch", "Lakehouse", "AWS"]
authors: ["yen"]
readTime: "16 min"
series: ["de-system-design-interview"]
---

> 多數人聽到「我們要即時」，就開始畫 Kafka、Flink 與即時 OLAP。  
> 面試官要看的卻是你有沒有先問：數字變了之後，誰會做什麼、多快做？  
> 新鮮度不是一個可以連續調整的旋鈕，而是一條有**斷崖**的成本曲線——跨過某些點，成本與維運負擔會整段跳上去。  
> 正確的答案是：**替每個消費者選它能容忍的最慢層級**，而不是替整個平台選最快的那一層。

[Part 5](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/) 的結尾把整個系列濃縮成五個自問題，第一題就是「誰在查、要多新鮮、要多準？」。Part 10 到 Part 14 是「策略深入」：每篇把其中一題展開成完整的選項清單。本篇處理第一題。批次與串流的基本機制分別在 [Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/) 與 [Part 3](/posts/de-system-design-interview-part3-streaming-realtime-zh/)，這裡不重講，而是聚焦在「該選哪一層、跨層的代價是什麼、什麼條件會讓選擇翻轉」。

---

## 面試情境

> **面試官**：「我們是一家電商，每天約 500 萬張訂單、3 億筆點擊事件。營收儀表板目前每天早上 8 點更新前一天的資料。上週大促時，行銷副總說『我們需要即時的營收儀表板』。你是負責的資料工程師，你會怎麼做？」

題目沒有問「怎麼做串流」，而是問「你會怎麼做」。直接開始設計串流架構，等於把需求原封不動地照做；面試官要看的是你能不能把「即時」這個詞翻譯成一個可以驗收的規格。

---

## 一、核心問題：新鮮度是一條有斷崖的成本曲線

先用一個固定的工作量，比較五種新鮮度的成本。假設：

```
clickstream      = 300M events/day × 1 KB     = 300 GB/day raw
parquet          = 300 GB / 6 (assumed)        ≈ 50 GB/day
batch work       = 16 node-hours per day of data (measured on daily job)
node-hour        ≈ $0.48  (m5.2xlarge on-demand + EMR fee, us-east-1)
MSK broker       ≈ $0.21/h (kafka.m5.large) × 3 brokers
OLAP node        ≈ $0.504/h (r5.2xlarge) × 6 nodes (3 shards × 2 replicas)
prices are list prices at time of writing; compute only, storage excluded
```

各層級的計算方式：

```
T+1 daily   : 1 run × 16 nodes × 1 h          = 16 node-h/day  → $7.7/day
~3 h        : 24 runs × 4 nodes × 20 min      = 32 node-h/day  → $15.4/day
              (10 min startup/commit + 10 min real work per run)
15–60 min   : always-on 4 nodes × 24 h        = 96 node-h/day  → $46/day
              (startup would eat half of a 15-min interval)
1–5 min     : stream 6 nodes × 24 h = $69.1 + MSK $15.1       → $84/day
seconds     : stream $69.1 + MSK $15.1 + OLAP 6 × $0.504 × 24 → $157/day
```

換成月成本，並把「串流層級仍然需要每日批次產生最終值」算進去：

```
monthly compute (30 days)                         × vs daily
T+1 daily    ██                          $230       1.0×
~3 h         ████                        $461       2.0×
15–60 min    ████████████                $1,382     6.0×
1–5 min      ████████████████████████    $2,757    12.0×   (+ daily final)
seconds      ████████████████████████████████████████████
                                         $4,934    21.4×   (+ daily final)
```

這張圖要注意的不是絕對金額（換一組假設就會變），而是兩個**斷崖**：

1. **從「按次付費」變成「24×7 常駐」**（約 1 小時 → 15 分鐘之間）。間隔長的時候，每次啟動叢集、處理、關掉；間隔短到啟動時間佔掉一半以上時，只能讓叢集常駐，成本從「做了多少事」變成「時鐘走了多久」。
2. **從「讀檔案」變成「維護狀態與服務層」**（分鐘 → 秒之間）。秒級需要一個持續寫入的服務層（Druid、Pinot、ClickHouse 或鍵值儲存）、有狀態的串流作業，以及另一條修正用的批次路徑。

成本之外還有兩條同形狀的曲線：**維運負擔**（多少元件要有人 24×7 待命）與**正確性代價**（越新的數字越不完整）。三條曲線的斷崖幾乎在同一個位置，這就是為什麼「再快一點」通常不是線性的加碼，而是換一套系統。

---

## 二、先問消費者：決策節奏決定新鮮度

「要多新鮮」是使用者答不好的問題——每個人都會說越快越好。要問的是**決策節奏**：數字變了之後，誰會做什麼、多快做。

| 問題 | 為什麼問 | 聽到這個答案時 |
|---|---|---|
| 這個數字變了，你會採取什麼行動？ | 沒有行動的新鮮度是浪費 | 「看看而已」→ T+1 或數小時 |
| 從看到到行動要多久？誰去做？ | 人的反應時間是新鮮度的下限 | 「開會討論後調預算」→ 天；「值班人員暫停活動」→ 15 分鐘 |
| 你多久看一次？ | 每天早會看一次的報表，每分鐘更新沒有人看得到 | 「早會」→ T+1；「大促期間一直開著」→ 分鐘級 |
| 晚一小時知道，損失大概多少？ | 把新鮮度換算成金額，才能和成本比較 | 損失小於每月多出的成本 → 不值得升級 |
| 數字差 1% 會怎樣？會拿去對帳、計算獎金或對外揭露嗎？ | 決定準確度層級，見第五節 | 「會拿去對帳」→ 需要最終值與重述流程 |
| 數字之後被修正，可以接受嗎？ | 決定能不能用暫定值 | 「不行」→ 只能等資料到齊，新鮮度會變差 |

**機器做決策時是另一回事**。風控擋交易、廣告預算控制、推薦特徵，這些消費者在秒級內自動行動，秒級新鮮度是真實需求（見 [Part 7](/posts/de-system-design-interview-part7-adtech-click-billing-attribution-zh/) 的預算控制）。但它們通常不是「儀表板」，而是一個有狀態的線上系統。**當有人說「即時儀表板」，看的人是人；人的決策節奏很少快於 5 分鐘。**

把答案對應到層級的一個簡化規則：

```
              who acts on the number?
                       │
          ┌────────────┴────────────┐
        a person                 a machine
          │                         │
   how fast can they act?     seconds: stream + state
          │                   (fraud, budget pacing)
   ┌──────┼───────────┬───────────────┐
 next day  same shift   within the hour  within minutes
   │         │              │              │
 T+1      ~3 h          15–60 min       1–5 min
 daily    micro-batch   micro-batch /   stream into OLAP
          / incremental buffered load   (rarely for people)
```

---

## 三、五個新鮮度層級

| 層級 | 典型架構 | 最壞情況新鮮度 | 月成本倍數 | 維運負擔 | 主要失敗模式 | 正確性代價 |
|---|---|---|---|---|---|---|
| T+1 每日 | 排程器每天一次；Spark／倉儲 SQL 重算昨日分區 | 最長約 32 小時（見下） | 1× | 上班時間處理即可 | 上游晚到導致作業延後；整天的資料一次出錯 | 幾乎沒有：截止時間後才計算，晚到資料最少 |
| 數小時 | 每小時增量模型（dbt incremental、MERGE）；暫態叢集 | 約 2 小時 | 2× | 夜間可能被叫醒 | 執行重疊、單次失敗累積落後 | 最近 1–2 小時是暫定值 |
| 15–60 分鐘 | Firehose／Snowpipe 類的緩衝載入 + 常駐叢集做頻繁的增量批次；或 Spark `availableNow` | 約 30–60 分鐘 | 6× | 需要自動重試與自癒 | 小檔案、compaction 與寫入衝突、排程器負載 | 最近一個視窗明顯偏低 |
| 1–5 分鐘 | Kafka + Spark Structured Streaming（微批次）或 Flink → OLAP／lakehouse | 約 2–5 分鐘 | 12× | 24×7 待命 | 消費延遲、檢查點失敗、小檔案爆量 | 需要 watermark；暫定值與最終值分離 |
| 秒級 | Kafka + Flink（有狀態）→ Druid／Pinot／ClickHouse 或鍵值儲存 | 約 2–10 秒 | 21× | 24×7 待命 + 狀態與服務層兩套專業 | 狀態膨脹、背壓、服務層擷取落後 | 幾乎全是暫定值，必須有批次修正 |

### 3.1 T+1：「每日」其實是最長 32 小時

日報 08:00 更新前一天的資料。前一天 00:00 發生的事件要到隔天 08:00 才看得到，延遲 32 小時；23:59 的事件延遲約 8 小時。「T+1」描述的是排程，不是新鮮度。

它的價值在於**完整**：計算開始時，前一天的資料已經等了 8 小時，絕大多數晚到事件都已到達。對帳、財報、獎金計算都應該停在這一層。

### 3.2 數小時：「3 小時內新鮮」怎麼兌現

假設規格是「p95 新鮮度 3 小時以內」，每小時跑一次。最壞情況的時間預算：

```
window length         60 min   (events from 10:00–10:59)
wait for late data    30 min   (start at 11:30)
run duration          20 min   (incl. startup and commit)
publish + BI cache    10 min
──────────────────────────────
worst case           120 min   → 60 min headroom = one full retry
```

**3 小時這個數字選得好，是因為它容得下一次失敗加重跑而不需要叫醒人**。同樣的架構若規格寫成「1 小時」，任何一次失敗都會違反 SLA。訂規格時先算預算，再決定數字。

### 3.3 15–60 分鐘：排程器開始不是對的工具

每 15 分鐘一次，一天 96 次。暫態叢集從申請到可用通常要數分鐘到十分鐘，會吃掉大半個間隔，所以必須常駐。這一層有兩種常見做法：

- **緩衝載入 + 增量模型**：Firehose 依大小或時間緩衝後寫入 S3（緩衝時間最長 900 秒），或用 Snowpipe 類的自動載入；倉儲上每 15–30 分鐘跑一次增量模型。注意 Firehose 直接寫入的計費以每筆記錄進位到 5 KB 計算，1 KB 的小事件應在用戶端先合併成較大的記錄。
- **Spark Structured Streaming 搭配 `trigger(availableNow=True)`**（Spark 3.3 起）：用串流的檢查點追蹤「哪些檔案已處理」，但像批次一樣處理完就結束。好處是重跑與 exactly-once 的檔案追蹤由引擎負責，不必自己記錄進度。

### 3.4 1–5 分鐘與秒級：從檔案到狀態

1–5 分鐘仍然可以用微批次（Structured Streaming 每分鐘一個 trigger），寫入 lakehouse 或 OLAP。秒級則需要逐筆處理的 Flink，以及能持續擷取、查詢時聚合的即時 OLAP。機制與 Lambda／Kappa 的取捨見 [Part 3](/posts/de-system-design-interview-part3-streaming-realtime-zh/)，這裡只強調一件事：**秒級的數字幾乎全部是暫定值**，因為 watermark 再短，也還有事件在路上。

---

## 四、怎麼量新鮮度：端到端延遲，而不是排程

「作業每 15 分鐘跑一次」不等於「資料 15 分鐘內新鮮」。新鮮度要從使用者的角度量：

```
per-event lag     = query_visible_time − event_time
table staleness   = now − completeness_watermark
                    (latest event_time up to which the table is complete)

SLO example       : p95(per-event lag) ≤ 3 h over a rolling 7 days
                    AND staleness ≤ 3 h at any moment (alert)
```

兩個指標回答不同的問題。**per-event lag 的 p95** 說明多數事件多快可見，適合寫進 SLO；**staleness** 說明「現在這張表停在哪裡」，適合即時告警。只看排程器的作業成功率會漏掉最常見的故障：作業成功了，但讀到的是空的或舊的上游分區。

量測最可靠的方法是**心跳事件**（canary）：每分鐘由一個合成的生產者送出一筆帶 `event_time` 的事件，走完整條管線；另一個探針定期查詢服務層，記下每筆心跳第一次可被查到的時間。

```sql
-- heartbeat_observations: one row per synthetic event,
-- visible_at = first time the probe saw it in the serving table
SELECT
  approx_percentile(date_diff('second', event_time, visible_at), 0.95)
    AS p95_lag_s,
  max(date_diff('second', event_time, visible_at)) AS max_lag_s,
  count_if(visible_at IS NULL)                      AS never_seen
FROM heartbeat_observations
WHERE event_time > current_timestamp - INTERVAL '1' DAY
  AND event_time < current_timestamp - INTERVAL '3' HOUR;  -- only judged ones
```

最後一行的條件很重要：最近 3 小時內的心跳還沒到 SLO 的期限，`visible_at` 為空是正常的，不能算成遺失。

**告警分兩級**，以 3 小時 SLO 為例：

| 級別 | 條件 | 動作 |
|---|---|---|
| 警告 | staleness > 2 h（預算用掉三分之二） | 通知頻道，白天處理 |
| 呼叫 | staleness > 2 h 30 min，或連續兩次執行失敗 | 叫醒值班人員 |
| 缺席告警 | 30 分鐘內沒有新的心跳被看到 | 叫醒值班人員：管線整段停了 |

### 症狀到診斷

| 症狀 | 先看的訊號 | 常見原因 | 處置 |
|---|---|---|---|
| 作業全部成功，儀表板卻停在 3 小時前 | staleness 上升，作業成功率 100% | 上游分區沒寫入，作業處理了空分區 | 依資料就緒觸發；加上「輸入列數為 0」的檢查 |
| 圖表最右邊一段總是往下掉 | 最近視窗的列數與前一天同時段相比 | 視窗尚未完整（部分視窗），不是業務下滑 | 標示暫定或不顯示未完成的視窗 |
| p95 正常，但每天早上總有人抱怨 | max lag 與 p95 的差距；依小時分佈的延遲 | 夜間的批次回補與白天作業爭搶資源 | 隔離資源佇列；回補限速 |
| 新鮮度隨時間緩慢變差 | 每次執行的耗時趨勢、表格檔案數 | 小檔案累積，列檔與開檔時間上升 | 排程 compaction（第八節） |
| 心跳正常，但某個來源的資料很舊 | 依來源拆分的 staleness | 心跳只走了主路徑，沒涵蓋這個來源 | 每個來源各自有心跳或各自的完成標記 |

---

## 五、準確度層級：近似、暫定、最終、重述

「要多準」和「要多新鮮」是同一枚硬幣的兩面。越早給的數字，包含的資料越少。以行動裝置事件為例，假設晚到分佈如下：

```
completeness of a window vs. how long we wait after it closes
(assumed distribution for mobile events)

wait     1 min  ██████████████████████████████████████████████  90.0%
wait    15 min  ██████████████████████████████████████████████████▌ 99.0%
wait     6 h    ██████████████████████████████████████████████████▉ 99.9%
wait     3 d    ███████████████████████████████████████████████████ 99.99%
```

分鐘級儀表板上最近一分鐘的數字，在這個假設下少了約 10%。這就是第四節「圖表右邊往下掉」的來源。所以除了新鮮度，每個數字還要宣告它屬於哪一種準確度：

| 層級 | 定義 | 典型來源 | 可以用來 | 不可以用來 |
|---|---|---|---|---|
| 近似 | 有界誤差的估計，例如 HyperLogLog 不重複人數 | 串流聚合 | 看趨勢、發現異常 | 對帳、計費 |
| 暫定 | 對已到達資料的精確計算，但資料還沒到齊 | 分鐘級或小時級路徑 | 營運決策、即時監控 | 對外揭露、獎金 |
| 最終 | 過了晚到截止時間後的精確計算 | 每日批次 | 財報、對帳、正式 KPI | — |
| 重述 | 最終值因 bug 或極晚資料被修正後的新版本 | 回補作業 | 取代舊的最終值 | 默默覆蓋而不留記錄 |

近似值的誤差可以事先算出來：HyperLogLog 用 2^14 個暫存器時，標準誤差約 1.04 / √16384 ≈ 0.81%，每個計數器約 12 KB。暫定值的誤差則取決於晚到分佈，事前只能估計，所以必須**標示**。

**重述要有規則**。最終值一旦發佈，就只能透過重述改變，而重述需要：改變的原因、前後差異、受影響的日期範圍，並通知下游。最常見的事故不是數字錯，而是同一個數字在週一和週三被兩個人截圖，兩張截圖不一樣，卻沒有任何記錄說明為什麼。

---

## 六、混用層級：熱路徑加冷修正

多數真實系統不會只有一個層級，而是**熱路徑提供暫定值、冷路徑提供最終值**，服務層讓最終值優先。[Part 3](/posts/de-system-design-interview-part3-streaming-realtime-zh/) 已經說明這個形狀；這裡補上讓它在儀表板上可用的三個細節。

**一、在資料列上標示狀態，並以最終值的截止點切分。**

```sql
CREATE OR REPLACE VIEW revenue_hourly AS
SELECT hour, channel, gmv, orders, 'final' AS status, published_at AS as_of
FROM revenue_hourly_final
UNION ALL
SELECT p.hour, p.channel, p.gmv, p.orders, 'provisional' AS status,
       p.updated_at AS as_of
FROM revenue_hourly_provisional p
WHERE p.hour > (SELECT max(hour) FROM revenue_hourly_final);
```

`WHERE` 條件確保同一個小時不會同時出現兩個版本；最終值發佈後，對應的暫定列自動退出檢視，不必去刪它。

**二、儀表板顯示狀態**：暫定的區段用虛線或不同底色，並在標題旁顯示「資料更新至 HH:MM，最近 N 小時為暫定值」。這一行字能避免大部分「數字為什麼變了」的詢問。

**三、每天比較兩條路徑的差異**：暫定值在被最終值取代前的最後版本，與最終值相比差多少。這個差異是熱路徑的品質指標，超過門檻（例如 0.5%）代表熱路徑漏了事件或邏輯不一致。

```
            hot path (provisional)
 ┌────────┐    every 15 min    ┌──────────────────────┐
 │ Orders │──▶ incremental ───▶│ revenue_hourly_      │──┐
 │ CDC +  │    MERGE           │ provisional          │  │
 │ clicks │                    └──────────────────────┘  │  ┌────────────┐
 │ in S3  │                                              ├─▶│ view:      │
 │        │──▶ daily 06:00 ───▶┌──────────────────────┐  │  │ final wins │
 └────────┘    full recompute  │ revenue_hourly_final │──┘  └─────┬──────┘
            cold path (final)  └──────────┬───────────┘           │
                                          ▼                       ▼
                               ┌──────────────────────┐    ┌────────────┐
                               │ diff check:          │    │ dashboard  │
                               │ last provisional vs  │    │ labels     │
                               │ final, alert > 0.5%  │    │ status     │
                               └──────────────────────┘    └────────────┘
```

混用的代價是**兩份邏輯**。降低它的方法是讓兩條路徑跑同一份 SQL 模型，只差在輸入範圍與執行頻率；dbt 的 incremental 模型與完整重建模式共用同一份定義，就是這種做法。

---

## 七、三個演進階段

回到面試情境。候選人問完第二節的問題後得到的答案是：財務與管理層仍然看每日的最終數字；大促期間，行銷的活動經理需要知道「某個活動是不是壞了」（有流量但沒有訂單、優惠碼失效），發現後會暫停活動或修正設定，希望 30 分鐘內知道；沒有人會根據秒級的數字採取行動。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Run the daily model hourly (POC, one promo)                ║
╚══════════════════════════════════════════════════════════════════════╝

┌────────────┐ hourly  ┌──────────────┐ hourly ┌──────────────────────┐
│ Orders     │────────▶│ S3 raw       │───────▶│ same daily SQL,      │
│ replica    │ extract │ dt=, hr=     │ +30min │ filtered to today    │
└────────────┘         └──────────────┘        └──────────┬───────────┘
                                                          ▼
                                               ┌──────────────────────┐
                                               │ "today so far" tab   │
                                               │ (provisional label)  │
                                               └──────────────────────┘
```

**新增**：把既有的每日模型改成每小時跑一次「今天截至目前」的版本，放在儀表板另一個分頁。**成本**：約 2 倍運算，零新元件。**解決**：大促當天可以每小時看到活動表現。**仍存在**：新鮮度約 2 小時，達不到 30 分鐘；每小時重算整天，越接近午夜越慢；沒有新鮮度監控。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  15-min incremental tier + daily final (MVP)                ║
╚══════════════════════════════════════════════════════════════════════╝

┌─────────┐ CDC  ┌─────────┐        ┌──────────────┐ 15-min ┌───────────┐
│ Orders  │─────▶│ Kafka / │───────▶│ S3 / Iceberg │───────▶│ MERGE     │
│ DB      │      │ Kinesis │        │ bronze       │        │ provision.│
└─────────┘      └─────────┘   ┌───▶│              │        └─────┬─────┘
┌─────────┐ SDK  ┌──────────┐  │    └──────┬───────┘              │
│ Clicks  │─────▶│ Firehose │──┘           │ daily 06:00          │
└─────────┘      │ buf 5 min│              │ full recompute       │
                 └──────────┘              ▼                      ▼
                                    ┌──────────────┐       ┌────────────┐
                                    │ final table  │──────▶│ view +     │
                                    └──────────────┘       │ dashboard  │
┌─────────────────────────────┐                            └────────────┘
│ heartbeat → freshness probe │──▶ staleness alerts
└─────────────────────────────┘
```

**新增**：常駐的小叢集（或倉儲）每 15 分鐘做增量 MERGE；第六節的狀態標示與檢視；心跳與 staleness 告警；每日 compaction。**成本**：運算約 6 倍（約 $1,400／月，依第一節假設），多出 3–4 個元件；需要自動重試，夜間的失敗由下一次執行自然補上。**解決**：活動問題 30 分鐘內可見；財務數字不受影響。**仍存在**：若之後要做「自動暫停壞掉的活動」，30 分鐘對機器來說太慢。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Freshness tiers as a platform contract (scale)             ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────┐
│ catalog: every table declares tier, SLO, accuracy, owner         │
│   revenue_final     T+1    p95 ≤ 32 h   final      finance-data  │
│   campaign_health   15 min p95 ≤ 45 min provisional growth-data  │
│   campaign_guard    seconds p95 ≤ 10 s  approx     ads-platform  │
└───────────────┬──────────────────────────────────────────────────┘
                │ drives scheduler config, alerts, compaction, labels
     ┌──────────┼──────────────────┬──────────────────────┐
     ▼          ▼                  ▼                      ▼
┌──────────┐ ┌──────────────┐ ┌──────────────────┐ ┌──────────────┐
│ daily    │ │ 15-min       │ │ Flink → Pinot    │ │ SLO report   │
│ batch    │ │ incremental  │ │ only for the one │ │ per tier,    │
│          │ │              │ │ machine consumer │ │ per owner    │
└──────────┘ └──────────────┘ └──────────────────┘ └──────────────┘
```

**新增**：目錄中每張表宣告層級、SLO、準確度與負責人，排程、告警與標示由宣告產生；只有真正由機器消費的那一條（自動暫停活動）走秒級。**成本**：秒級路徑本身約 $4,700／月，加上一組要懂 Flink 與 OLAP 的值班人員。**解決**：新需求進來時，先對照層級表選一層，而不是每次重新爭論。**仍存在**：層級宣告與實際表現會漂移，需要每月的 SLO 報告來校正。

| | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 最快層級 | 約 2 小時 | 約 30–45 分鐘 | 秒級（僅一條） |
| 月運算成本（相對每日） | 2× | 6× | 6× + 秒級路徑 |
| 新增元件 | 0 | 3–4 | 6 以上 |
| 夜間呼叫 | 無 | 少（自動重試） | 秒級路徑需 24×7 |

---

## 八、3 小時、1 天、15 分鐘：哪些東西跟著變

同一個資料集，新鮮度從 1 天改成 3 小時再改成 15 分鐘，改變的不只是 cron 表達式。

**排程器。** 每次執行的失敗率假設為 1%，一天至少失敗一次的機率是：

```
daily    : 1 − 0.99^1   = 1%    → about one failure every 100 days
hourly   : 1 − 0.99^24  ≈ 21%   → about one failing day per week
15 min   : 1 − 0.99^96  ≈ 62%   → most days have at least one failure
```

每日作業失敗可以等人來處理；15 分鐘的作業若每次失敗都要人介入，值班人員會被告警淹沒。所以頻率越高，越需要**冪等的增量處理**——失敗的那一次不必修，下一次會把它的範圍一起處理掉（[Part 11](/posts/de-system-design-interview-part11-idempotency-rerun-backfill-zh/) 會展開）。另外，在 Airflow 類的排程器上每 15 分鐘產生一個 DAG run，排程器本身的負載與「上一次還沒跑完」的重疊都會成為問題；這時改用長駐的串流或 `availableNow` 作業、由引擎自己追蹤進度，通常比讓排程器高頻觸發更穩定。

**檔案大小與小檔案。** 以每天 50 GB 的 Parquet 為例：

| 頻率 | 每次寫入量 | 每天檔案數 | 平均檔案大小 |
|---|---|---|---|
| 每日（重新分區到 256 MB） | 50 GB | 約 200 | 256 MB |
| 每小時（沒調整，200 個 shuffle 分區） | 2.1 GB | 4,800 | 約 10 MB |
| 每 15 分鐘（16 個寫入 task） | 520 MB | 1,536 | 約 33 MB |
| 每 1 分鐘（16 個寫入 task） | 35 MB | 23,040 | 約 2.2 MB |

每分鐘寫入一年會累積約 840 萬個檔案。小檔案讓查詢的列檔與開檔時間上升，新鮮度也會跟著慢慢變差（第四節的症狀）。解法是定期 compaction（例如 Iceberg 的 `rewrite_data_files`），但它會和高頻寫入搶同一張表的提交，造成重試；常見做法是只 compact 已經不再寫入的分區（例如兩小時前的分區）。細節在 [Part 4](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)。

**運算成本的形狀。** 每日與每小時是「做多少付多少」，閒置時不花錢；15 分鐘以下是「開著就付錢」，即使凌晨三點沒有流量。這也是為什麼常駐層級值得考慮 spot 或保留執行個體，而按次執行的層級不太需要。

**On-call。**

| 新鮮度 | 失敗後的修復窗口 | 值班型態 |
|---|---|---|
| 1 天 | 從失敗到 08:00 的數小時；最壞就晚一天 | 上班時間處理 |
| 3 小時 | 約 1 小時（預算中的重跑空間） | 夜間偶爾被叫醒 |
| 15 分鐘 | 幾乎沒有，必須自動恢復 | 處理的是「持續落後」而非單次失敗 |
| 秒級 | 無 | 24×7，需要懂狀態與服務層的人 |

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| 每個消費者各自選層級 vs 整個平台統一最快層級 | 只有少數消費者付秒級的成本；其他維持便宜、完整 | 統一最快層級讓所有表都背負常駐運算與暫定值的複雜度 | 多數消費者都是機器、都需要分鐘級以內 |
| 15 分鐘增量批次 vs 秒級串流（給人看的活動儀表板） | 人的反應時間在 15–30 分鐘；成本約 6× 而非 21× | 秒級的新鮮度沒有人能用上，卻要 24×7 維運狀態與服務層 | 由機器自動行動（自動暫停、預算控制），或延遲的損失以分鐘計價 |
| 以 p95 端到端延遲定 SLO vs 以排程間隔定義 | 量的是使用者看到的結果，涵蓋上游延遲與空分區 | 排程成功不代表資料新；作業可能處理了空分區 | 沒有能力量測可見時間時，至少以 staleness 告警代替 |
| 暫定值 + 最終值 vs 只發佈等資料到齊的數字 | 早期可行動，正式數字仍準確 | 只發佈最終值會讓新鮮度被晚到資料的長尾拖住 | 數字一旦公開就不能修正（對外揭露、法規申報） |
| 3 小時 SLO vs 1 小時 SLO（同樣每小時執行） | 預算容得下一次完整重跑，失敗不必叫人 | 1 小時 SLO 下任何一次失敗都違約，夜間必須有人值班 | 消費者真的在 1–2 小時內行動，且願意付夜間值班的成本 |
| `availableNow` 增量作業 vs 排程器每 15 分鐘觸發批次 | 引擎追蹤已處理的檔案，失敗後自然接續；排程器負載低 | 高頻 DAG run 容易重疊，進度要自己記錄 | 團隊沒有 Spark，或倉儲原生的增量模型已能滿足 |

---

## 十、系統效應與系列導航

以面試情境為例，從「把日報整個改成即時」與「依消費者分層」兩種回應的比較。

| 指標 | 全部改成秒級串流 | 分層（每日最終 + 15 分鐘暫定） |
|---|---|---|
| 活動問題被發現的時間 | 數秒（但人 15–30 分鐘後才會看） | 30–45 分鐘 |
| 財務數字 | 暫定值，需另建批次對帳 | 每日最終值，不變 |
| 月運算成本（依第一節假設） | 約 $4,900 | 約 $1,400 |
| 新增需 24×7 維運的元件 | Kafka、Flink、OLAP | 無（自動重試 + 白天處理） |
| 數字的準確度 | 幾乎全是暫定值，最終值要另建批次 | 最近一天暫定、其餘為最終值 |
| 交付時間 | 數個月 | 數週 |

面試的收尾可以這樣說：「我不會把整個儀表板改成即時。財務與管理層維持每日最終值；活動經理需要的是 30 分鐘內發現活動壞掉，所以我加一個 15 分鐘的暫定層級，明確標示、每天與最終值比對，並以 p95 端到端延遲定 SLO。如果之後要讓系統自動暫停活動，那一個消費者才值得秒級路徑。」**這個回答拒絕了字面上的需求，卻滿足了真正的需求，而且說得出在什麼條件下會改變主意。**

**本篇重點**

- 新鮮度的成本曲線有兩個斷崖：按次付費 → 常駐運算，以及讀檔案 → 維護狀態與服務層。
- 問決策節奏，不問「要多快」：數字變了誰做什麼、多快做。
- 新鮮度以端到端延遲（可見時間 − 事件時間）的 p95 量測，不是排程間隔；用心跳事件與 staleness 告警。
- 越新的數字越不完整：每個數字標示近似、暫定、最終或重述。
- 頻率提高時，排程方式、檔案大小、成本形狀與值班型態一起改變。

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
- **Part 10：誰在查、要多新鮮、要多準——依新鮮度選架構**（本篇）
- [Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part11-idempotency-rerun-backfill-zh/)
- [Part 12：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)
- [Part 13：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part13-schema-evolution-zh/)
- [Part 14：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- Betsy Beyer et al.,《Site Reliability Engineering》第 4 章 Service Level Objectives
- Tyler Akidau, Slava Chernyak & Reuven Lax,《Streaming Systems》第 2–3 章（watermark 與完整性）
- Martin Kleppmann,《Designing Data-Intensive Applications》第 10–11 章
- Apache Spark 文件：Structured Streaming Programming Guide — Triggers
- Amazon Data Firehose 文件：Buffering hints 與 Pricing
