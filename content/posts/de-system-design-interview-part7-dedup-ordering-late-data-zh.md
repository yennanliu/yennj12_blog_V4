---
title: "DE 系統設計面試指南 Part 7：重複、亂序與晚到——事件正確性的處理策略"
date: 2026-11-24T10:00:00+08:00
draft: false
weight: 7
description: "重複、亂序、晚到是三個不同的問題，各有自己的策略選單：event_id 去重的狀態大小、跨分區重複、MERGE 與 Bloom filter、版本號取代到達順序、晚到分佈決定回溯天數與定案規則，附依用途選策略的決策表。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Deduplication", "Late Data", "Watermark", "Streaming", "Data Quality", "AWS"]
authors: ["yen"]
readTime: "16 min"
series: ["de-system-design-interview"]
aliases: ["/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/"]
---

> 多數人把「重複、亂序、晚到」當成同一個問題，用一句「我會用 watermark 加去重」帶過。  
> 結果去重狀態開到 300 GB，晚到的事件照樣被丟掉，重跑一次數字又往上漂。  
> 正確的作法是把三個問題拆開：各自從哪裡來、影響哪個指標、哪個策略在這個指標上最便宜。  
> 很多時候最好的去重，是把指標設計成根本不怕重複。

這是「策略深入」的第三篇，處理的問題是（也是 [Part 10](/posts/de-system-design-interview-part10-mock-interview-scenarios-zh/) 結尾自我檢查清單的第三題）：「事件重複、亂序或晚到時，數字還對嗎？」[Part 3](/posts/de-system-design-interview-part3-streaming-realtime-zh/) 已經說明 event time、watermark 與視窗的基本機制；本篇不重複這些，而是把每個問題的**策略選單**攤開：怎麼做、花多少、什麼時候失效、什麼條件下該換一個。

---

## 面試情境

> **面試官**：「我們的行動 App 有 1,000 萬日活。使用者常在捷運、飛機或訊號差的地方使用，App 會把事件存在手機上，連上網路後才補送，最晚可能晚 3 天才到。產品與財務都看同一張儀表板：每日活躍使用者（DAU）與每日購買數、購買金額。他們要求這兩個數字是『對的』。你會怎麼設計？」

這題的關鍵字是「晚 3 天」與「對的」。在動手之前要先問：「對」是指今天就對，還是某個時間點之後就不再變動？

---

## 一、核心問題：三個問題，三種後果

先算規模（假設值，面試中要說出口）：

```
DAU                  = 10,000,000
events/user/day      = 100
events/day           = 1,000,000,000
avg events/s         = 1e9 / 86,400            ≈ 11,600 /s
peak events/s        = 11,600 × 3              ≈ 35,000 /s
raw size             = 1 KB/event  -> 1 TB/day (JSON)
Parquet (≈ 150 B/ev) = 150 GB/day
purchases/day        = 300,000   (≈ 2% of DAU × 1.5 orders)
```

三個問題要分開談，因為它們破壞的東西不同：

| 問題 | 定義 | 會壞掉的指標 | 不會壞的指標 |
|---|---|---|---|
| 重複 | 同一個事件被記錄兩次以上 | 計數、加總（購買數、金額） | 去重計數（DAU）、最大值、存在與否 |
| 亂序 | 到達順序與發生順序不同 | 「目前狀態」（訂單已退款？）、序列分析（漏斗） | 可交換的聚合（count、sum） |
| 晚到 | 事件在結果已輸出後才到 | 已輸出的任何聚合 | 尚未輸出的結果 |

這張表是全篇的地圖。注意右欄：**DAU 天生不怕重複**，同一個使用者被記兩次，`COUNT(DISTINCT user_id)` 還是 1；**sum 天生不怕亂序**，加的順序不影響總和。面試中先把這兩點說出來，等於告訴面試官你不會在不需要的地方付錢。

還有一個要先釐清的口徑：**購買數的事實來源是什麼？** 離線的手機無法完成付款，付款一定經過後端。所以「每日購買」應該來自訂單資料庫（經 CDC），而不是 App 送出的 `purchase` 事件；後者只用來做漏斗分析。這一句話就把購買指標的晚到問題縮小到「後端寫入到資料湖的延遲」，剩下的難題集中在 DAU。

---

## 二、三個演進階段

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  Nightly batch by arrival date (POC)                        ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐  HTTPS   ┌──────────┐  hourly   ┌─────────────────────────┐
│ App SDK  │─────────▶│ Collector│──────────▶│ S3 raw/ingest_date=D/   │
└──────────┘          └──────────┘           └───────────┬─────────────┘
                                                         │ nightly Spark
                                                         ▼
                                  ┌──────────────────────────────────────┐
                                  │ dedup ROW_NUMBER within ingest_date  │
                                  │ DAU(D) = distinct users in ingest D  │
                                  └──────────────────────────────────────┘
```

**作法**：每晚處理「昨天收到的」事件，在當天分區內去重，算出 DAU。

**優點**：一個 Spark 作業就完成；結果寫一次就不再改變。

**何時失效**：DAU 是依**到達日**而非**發生日**計算的。週五在飛機上的使用者週日才被算進週日的 DAU；而同一事件若週五送出一次、週六重送一次，分別落在兩個到達日分區，各自的分區內去重都看不到另一份。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  Event-date tables + 3-day lookback + MERGE (MVP)           ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐      ┌─────────────────────┐   dedup vs last 3   ┌─────────┐
│ S3 raw   │─────▶│ new events today    │──── ingest days ───▶│ clean   │
│ ingest=D │      │ (first seen only)   │                     │ events  │
└──────────┘      └─────────────────────┘                     └────┬────┘
                                                                   │ MERGE
┌──────────┐ CDC  ┌─────────────────────┐                          ▼
│ Orders DB│─────▶│ orders_current      │   ┌──────────────────────────┐
└──────────┘      │ LWW by LSN          │   │ user_daily_activity      │
                  └──────────┬──────────┘   │ (user_id, event_date)    │
                             │              └────────────┬─────────────┘
                             ▼                           ▼
                  ┌──────────────────────────────────────────────────┐
                  │ daily_metrics(event_date, dau, purchases, gmv,   │
                  │               status = provisional | final)      │
                  └──────────────────────────────────────────────────┘
```

**新增元件**：依事件日期歸屬的中間表 `user_daily_activity`、跨到達日的去重、以 LSN 決定新舊的訂單表、`provisional / final` 狀態欄位。

**成本與複雜度**：每晚多讀最近 3 天的原始到達分區做去重比對；多一張每天 1,000 萬列的小表。仍然是一套批次程式。

**解決**：DAU 歸屬到正確的日期；跨到達日的重複被擋下；晚到的使用者活動以 MERGE 補進對應日期，D 日數字在 D+4 定案。

**仍存在的問題**：今天的數字要等到隔天才看得到；定案規則要和產品、財務談好。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Streaming provisional + late side output + finalize (scale)║
╚══════════════════════════════════════════════════════════════════════╝

                 ┌───────────────────────┐  provisional,  ┌──────────────┐
            ┌───▶│ Flink: HLL DAU/minute │  every 10 s    │ Serving      │
┌───────┐   │    │ allowed lateness 1 h  │───────────────▶│ (ClickHouse) │
│ Kafka │───┤    └──────────┬────────────┘                └──────▲───────┘
│ events│   │               │ side output: too late              │
└───────┘   │               ▼                                    │ final
            │    ┌───────────────────────┐   touched dates  ┌────┴───────┐
            └───▶│ S3 raw + late log     │─────────────────▶│ batch MERGE│
                 └───────────────────────┘   only           │ + finalize │
                 ┌───────────────────────┐                  └────────────┘
                 │ lateness histogram    │◀── metrics from every stage
                 └───────────────────────┘
```

**新增元件**：串流路徑提供今天的暫定值（DAU 用 HLL 近似）、晚到旁路輸出、只重算「被晚到事件觸及的日期」的批次作業、晚到分佈的監控。

**成本與複雜度**：多一條串流路徑與一個服務層；兩條路徑的 DAU 定義要一致（用同一份去重與歸屬規則），並每天比對差異。

**解決**：當日數字 10 秒內可見；最終值仍由批次路徑以精確計算產生。

**仍存在的問題**：手機時鐘不可信、超過 3 天才到的事件怎麼處理——第六節討論。

---

## 三、重複從哪裡來

去重策略的選擇取決於重複**在哪一層產生**，因為不同來源的重複有不同的時間跨度：

```
  client          collector       Kafka           consumer        backfill
┌────────┐ (1)  ┌──────────┐ (2) ┌───────┐ (3)  ┌──────────┐ (4) ┌────────┐
│ SDK    │─────▶│ HTTP API │────▶│ topic │─────▶│ Flink /  │────▶│ rerun  │
│ queue  │ retry│          │retry│       │replay│ Spark    │     │ / CDC  │
└────────┘      └──────────┘     └───────┘      └──────────┘     │ resnap │
                                                                 └────────┘
 (1) span ≤ 72 h,   key: event_id      (2) span: seconds, key: producer seq
 (3) span: 1 ckpt, key: offset/ckpt   (4) span: days,    key: primary key
```

| 來源 | 典型情境 | 時間跨度 | 能用的識別 |
|---|---|---|---|
| (1) 用戶端重試 | 上傳成功但回應在斷線時遺失，SDK 下次連線重送整批 | 最長等於 SDK 保留期，本題 72 小時 | SDK 產生的 `event_id`（UUID） |
| (2) 生產者重試 | collector 寫 Kafka 逾時後重送 | 秒級 | 冪等生產者的序號（Kafka 層自動處理） |
| (3) 至少一次的消費者 | 消費者處理完、提交 offset 前崩潰，重啟後重讀 | 一個檢查點／提交間隔 | offset，或業務鍵 |
| (4) 重播與回補 | 修 bug 後從 S3 重跑某幾天；CDC 重新做全量快照 | 天到月 | 主鍵（`order_id`），快照列沒有原事件的 id |

兩個推論。第一，**(2) 和 (3) 有現成的機制**——冪等生產者、檢查點加冪等 sink，Part 3 第四節已說明。真正要設計的是 (1) 與 (4)。第二，(1) 的跨度是 72 小時，這個數字直接決定去重狀態有多大，下一節會算。

CDC 重新快照值得單獨提：Debezium 之類的工具重做初始快照時，每一列以 `op = r`（read）重新送出一次。下游若把它當成新事件 append，訂單數會加倍。**以主鍵 MERGE 的表不怕這種重複，append 的事實表會怕**。

---

## 四、去重策略選單

### 4.1 總表

| 策略 | 怎麼做 | 優點 | 缺點 | 成本 | 何時選 | 何時失效 |
|---|---|---|---|---|---|---|
| 冪等生產者 | Kafka 依生產者序號丟棄重送 | 免費，預設開啟 | 只擋 (2) | ≈ 0 | 永遠開 | 用戶端重試、重播 |
| 串流 keyed state | 以 `event_id` 為鍵保留 TTL 時間，看過即丟 | 即時、精確 | 狀態隨 TTL 線性成長 | 見 4.2 | 需要即時的計數／加總 | TTL 短於重複的跨度 |
| 批次 `ROW_NUMBER` | 在分區內依 `event_id` 取第一筆 | 簡單、精確 | 只看得到同一批次內的重複 | 一次掃描 | 每日批次 | 重複跨越分區邊界（4.3） |
| 以鍵 MERGE | 目標表上 `event_id` 不存在才插入 | 跨任何時間跨度都精確 | 每次寫入要比對目標表 | 依比對範圍而定 | 金額、計費 | 比對範圍沒涵蓋重複的跨度 |
| Bloom filter | 以位元陣列近似判斷「看過」 | 記憶體約精確法的 1/50 | 偽陽性會**丟掉真事件** | 見 4.4 | 量極大、可容忍少算 | 任何要對帳的指標 |
| 冪等聚合 | 指標本身用集合、HLL、max | 不必去重 | 只適用於特定指標 | ≈ 0 | DAU、是否轉換 | 計數、加總 |

### 4.2 Keyed state 的 TTL 與記憶體

狀態大小 = 每秒新鍵數 × TTL × 每鍵成本。RocksDB 中一個 UUID 鍵連同中繼資料約 100 bytes（保守估計）：

```
all events, TTL 72 h : 1e9/day × 3 days × 100 B        = 300 GB
all events, TTL 1 h  : 11,600/s × 3,600 s × 100 B      ≈ 4.2 GB
purchases,  TTL 72 h : 300,000/day × 3 days × 100 B    = 90 MB
```

300 GB 的狀態不是做不到，但每次檢查點、每次擴縮容的狀態重新分配都很痛。這組數字給出的設計是：**只對會被重複破壞的指標做長 TTL 去重**。購買事件 90 MB，隨便做；DAU 用的瀏覽事件根本不需要去重（第一節的表）；需要即時計數的一般事件（例如「每分鐘點擊數」）用 1 小時 TTL 擋住絕大多數的重送，剩下的交給批次路徑修正。

TTL 的依據要來自量測，不是猜：統計「同一 `event_id` 第二次到達與第一次的時間差」的分佈，取 p99.9 再加餘裕。

### 4.3 批次去重與跨分區邊界

Phase 1 的錯誤在於只在當天的到達分區內去重。修正方式是讓今天的資料與過去幾天已處理過的資料一起比對，只保留「今天第一次看到」的事件：

```sql
-- keep events whose FIRST arrival is in ingest_date = :d
WITH candidates AS (
  SELECT e.*,
         ROW_NUMBER() OVER (PARTITION BY event_id
                            ORDER BY server_received_at) AS rn
  FROM raw_events e
  WHERE ingest_date BETWEEN date_sub(:d, 3) AND :d
)
SELECT * FROM candidates
WHERE rn = 1 AND ingest_date = :d;
```

回溯 3 天對應 SDK 的 72 小時保留期。代價是每晚多讀 3 天的原始資料：只需要 `event_id`、`server_received_at`、`ingest_date` 三欄，Parquet 欄式讀取下約為整列的 10–15%，150 GB × 3 × 15% ≈ 70 GB，遠小於重讀全部欄位。

更穩的作法是讓「看過的 `event_id`」成為一張有主鍵的表，用 MERGE 只插入不存在的：

```sql
MERGE INTO clean_events t
USING (SELECT * FROM staged_new_events            -- already ROW_NUMBER'd
       WHERE event_date >= date_sub(:d, 4)) s
ON  t.event_id = s.event_id
AND t.event_date >= date_sub(:d, 4)               -- partition pruning
WHEN NOT MATCHED THEN INSERT *;
```

兩個容易錯的細節。第一，`ON` 裡加日期範圍是為了只掃最近的分區，但**來源也必須套用同一個範圍**：否則一筆 `event_date` 更早的重複事件在範圍內找不到配對，會被當成新事件插入。超出範圍的事件應該導到另一張「過晚事件」表，由第六節的定案規則處理。第二，來源內部必須先去重：同一批裡出現兩份相同 `event_id`，`NOT MATCHED` 會把兩份都插進去。

### 4.4 Bloom filter 的帳

Bloom filter 以 m 個位元、k 個雜湊函數判斷「可能看過」或「一定沒看過」。要容納 n 個元素、偽陽性率 p：

```
m = −n · ln(p) / (ln 2)²       k = (m / n) · ln 2

n = 1e9/day, p = 0.1%
m = 1e9 × 6.91 / 0.480         ≈ 14.4e9 bits ≈ 1.8 GB
k ≈ 14.4 × 0.693               ≈ 10 hash functions
```

1.8 GB 對比精確狀態的 100 GB／天，省了約 55 倍。但後果要說清楚：**偽陽性意味著一個從沒出現過的事件被判定為重複而丟掉**。0.1% 的偽陽性率在每天 10 億筆上就是最多約 100 萬筆真事件被靜默丟棄，而且無法事後找回（被丟的事件沒有任何記錄）。

所以 Bloom filter 的正確位置是：**擋在精確去重前面的快速通道**——「一定沒看過」的直接放行（這是 Bloom filter 不會錯的那一邊），「可能看過」的再去查精確狀態或目標表。這樣省下大部分查詢，又不會丟資料。單獨使用只適合「少算 0.1% 無所謂」的指標，例如曝光熱度排行。

### 4.5 把指標設計成不怕重複

| 聚合 | 重複一次的效果 | 冪等？ |
|---|---|---|
| `count += 1` / `sum += amount` | 多算一次 | 否 |
| 集合加入 `user_id` | 無變化 | 是 |
| HyperLogLog 加入 `user_id` | 無變化（同一元素映射到同一暫存器） | 是 |
| `max(last_seen_at)` | 無變化 | 是 |
| 以 `(user_id, event_date)` 為鍵 upsert | 覆寫同一列 | 是 |

Phase 2 的 `user_daily_activity` 就是這個想法：DAU 不從 10 億筆事件現算，而是維護一張「誰在哪天活躍過」的表，每天約 1,000 萬列。晚到或重複的事件只是對這張表做一次「不存在才插入」，DAU 等於某一天的列數。重複事件對它完全無害，晚到事件的修正成本也從「重掃 3 天原始資料」降到「MERGE 幾萬列」。

HLL 的誤差也要算：標準誤差約 1.04/√m，m = 2¹⁴ 個暫存器（約 12 KB）時為 0.81%，在 1,000 萬 DAU 上約 ±8 萬人。這比第六節估的晚到影響還大，所以 HLL 只適合即時暫定值與多維度切片，**定案的 DAU 要用精確計數**。

---

## 五、亂序：用版本取代到達順序

亂序只在兩種情況下需要處理：維護「目前狀態」，以及分析事件序列。聚合計數不需要。

### 5.1 策略選單

| 策略 | 怎麼做 | 優點 | 缺點 | 何時選 | 何時失效 |
|---|---|---|---|---|---|
| 分區 key 保序 | 同一實體的事件用同一個 key，Kafka 分區內有序 | 免費 | 只保證**寫入**順序；多個生產者時無效 | 單一來源（CDC） | 事件來自多台裝置或多個服務 |
| 版本號 / 序號 | 事件帶每實體遞增的 `version`，下游丟棄較舊版本 | 與到達順序完全脫鉤 | 來源要能產生單調版本 | 狀態表、upsert | 多個寫入者沒有共同的序號來源 |
| CDC LSN | 以資料庫日誌位置作為版本 | 天然單調、與提交順序一致 | 只適用於資料庫來源 | 訂單、帳戶 | 重建資料庫後 LSN 重新起算 |
| 可交換聚合 | 只用 count、sum、min、max、集合 | 順序完全無關 | 不能回答「目前狀態」 | 指標聚合 | 漏斗、session 這類序列分析 |
| 緩衝排序 | 每個 key 緩衝 T 秒，依事件時間排序後輸出 | 下游看到有序資料 | 延遲 +T、記憶體隨 T 成長 | 序列分析、CEP | 晚到超過 T 的事件 |

### 5.2 Last-write-wins 要依版本，不是依到達

本題的購買金額來自訂單表，一張訂單會經過 `paid → refunded`。若 `refunded` 的變更先寫進資料湖、`paid` 後到，依到達順序覆寫會讓已退款的訂單「復活」，GMV 多算。訂單資料來自 CDC，所以用 LSN 比較：

```sql
MERGE INTO orders_current t
USING orders_cdc_batch s            -- reduced to max(lsn) per order_id first
ON t.order_id = s.order_id
WHEN MATCHED AND s.lsn > t.lsn THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

這與 [Part 2](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/) 第五節「只在來源較新時覆寫」是同一個原則；這裡要補的是它同時解決了亂序與重播：CDC 重新快照送來的舊列，LSN 不大於現有值，自然被忽略。

App 端的事件沒有 LSN。若需要依使用者排序（例如漏斗：「看了商品 → 加入購物車 → 結帳」），SDK 應在每台裝置上維護遞增的 `seq_no`。它比裝置時鐘可靠：使用者改了手機時間，`seq_no` 仍然單調。但它只在**同一台裝置內**有意義：同一位使用者的手機與平板各自都有 `seq_no = 1`，兩者之間無法用它比較先後。跨裝置的順序只能靠校正後的 `event_time`（6.2 節），精確度就是時鐘校正的精確度；若漏斗的步驟必須嚴格有序，就把分析限制在單一裝置的序列內。

### 5.3 緩衝排序的代價

```
buffer memory = peak rate × T × event size
              = 35,000/s × 10 s × 1 KB      ≈ 350 MB   (spread over all tasks)
added latency = T = 10 s
```

10 秒的緩衝很便宜，但它只排得好 10 秒內的亂序。本題的晚到是 72 小時，不可能在串流中緩衝排序。所以漏斗這類序列分析放在批次路徑，對 `event_date` 定案後的資料依 `(user_id, device_id, seq_no)` 排序計算；需要跨裝置合併時，再以校正後的 `event_time` 交錯各裝置的序列。

---

## 六、晚到：從量測分佈開始

### 6.1 先量晚到，再談策略

晚到程度 = `server_received_at − event_time`。每個策略的參數（allowed lateness、回溯天數、定案時間）都應該從這個分佈讀出來。以下是本題的**假設分佈**，實際要以直方圖量測：

```
lateness percentile   value      what it implies
───────────────────────────────────────────────────────────────
p50                   2 s        normal online traffic
p90                   15 s       mobile network batching
p99                   10 min     brief offline (elevator, tunnel)
p99.9                 18 h       overnight offline
p99.99                60 h       weekend trip
max                   72 h       SDK drops events older than this
```

同一個分佈，事件層級與使用者層級的影響不同。晚到事件集中在少數離線使用者身上：假設 99.9% 的事件在 18 小時內到達，事件層級只差 0.1%；但如果有 0.5% 的使用者整天都在離線狀態（例如長途飛行），他們當天的**所有**事件都晚到，DAU 在隔天早上就少了約 5 萬人。所以要分別量測兩個直方圖：事件晚到分佈與「使用者首次活動」的晚到分佈。DAU 只受後者影響。

### 6.2 手機時鐘不可信

`event_time` 來自手機，可能錯好幾天。常見作法是 SDK 在上傳時附上「送出當下的裝置時間」`device_sent_at`，伺服器以自己的時間校正：

```
offset             = server_received_at − device_sent_at
corrected_event_ts = event_time + offset
```

這假設時鐘偏差在離線期間不變，且忽略網路傳輸時間（秒級）。校正後仍落在未來，或早於 App 安裝時間的事件，改用 `server_received_at` 歸屬並計數。若這類事件的比例突然上升，通常是某一版 SDK 的時間戳 bug。

### 6.3 策略選單

| 策略 | 怎麼做 | 優點 | 缺點 | 成本 | 何時選 |
|---|---|---|---|---|---|
| watermark + 丟棄 | 視窗關閉後到的事件忽略，只計數 | 最簡單，狀態最小 | 數字永遠少 | 低 | 營運監控、趨勢 |
| allowed lateness | 視窗關閉後保留 L 時間，晚到事件觸發更新 | 中短期晚到被修正 | 視窗狀態保留 L；下游必須能接更新 | 狀態 × L | L 覆蓋到 p99–p99.9 時 |
| 旁路輸出 | 超過 L 的事件寫到另一條輸出，交給修正路徑 | 不丟資料、主路徑狀態小 | 需要第二條路徑 | 一條批次作業 | 有任何對帳需求 |
| retract / upsert 輸出 | 更新以「撤回舊值 + 新值」或依鍵覆寫送到下游 | 下游永遠是最新值 | 下游若 append 就會重複計算 | sink 要支援 | 串流直接餵服務層 |
| 週期性回溯重算 | 每天重算最近 N 天的 `event_date` | 精確、邏輯單一 | 重算成本 × N | 見 6.4 | 定案的數字 |

Flink 中後三者常一起出現：視窗設 `allowedLateness(1 小時)`，再以 `sideOutputLateData(tag)` 把更晚的事件寫到 S3 的晚到記錄。輸出到服務層時以 `(metric, event_date, minute)` 為鍵 upsert。一個常見的錯誤是把帶更新的結果 append 到 Kafka 再由下游加總：視窗每更新一次，下游就多加一份，數字隨晚到事件增加而膨脹。

### 6.4 回溯天數與定案

回溯天數 N 由分佈與完整性目標決定：

```
target completeness 99.99%  ->  lateness p99.99 = 60 h  ->  N = 3 days
SDK max retention 72 h      ->  nothing can arrive after D+3 + upload lag
finalize D at               =  D+4 02:00   (72 h + day boundary + 2 h margin)
run at D+4 02:00 recomputes =  event_date D, D+1, D+2, D+3   (4 partitions)
```

注意最後一行：定案 D 的那一次執行**必須把 D 自己算進去**。D 當天深夜發生的事件，可能在 D+3 的深夜、也就是 D+3 那一晚的批次跑完之後才送達。如果 D+4 的批次只重算「最近三個 `event_date`」（D+1 到 D+3），這筆事件就永遠不會被算進 D，而 D 卻被標成定案。所以「回溯 3 天」的意思是昨天再往前 3 天，每晚重算 4 個分區；一個分區只有在被重算過最後一次之後才能標記定案。

重算的成本取決於重算什麼。重掃原始事件：每天要讀 4 個 `event_date` 分區，150 GB × 4 = 600 GB；在 Athena 上以每 TB 掃描 5 美元計，約 3 美元／天。用 4.5 節的 `user_daily_activity` 只 MERGE 被晚到事件觸及的 `(user_id, event_date)`：每天約數萬到數十萬列，成本可以忽略。前者簡單但隨回溯天數線性成長，後者需要維護中間表。回溯天數超過一週時（例如廣告歸因要回溯 30 天），差距就會很明顯。

定案規則要寫下來並讓使用者看見：

| 狀態 | 期間 | 儀表板顯示 | 之後的變動 |
|---|---|---|---|
| 即時 | 當天 | 串流暫定值，標示「即時、未含離線補送」 | 隨時更新 |
| 暫定 | D+1 到 D+4 | 批次值，標示「可能上修」 | 每天 MERGE 晚到資料 |
| 定案 | D+4 02:00 之後 | 不再變動 | 更晚的事件只計數，不改歷史 |

定案後還是有東西會到：時鐘錯得離譜的事件、回補時發現的 bug。兩種政策：**不重述**（只記在「過晚事件」表並監控比例），或**重述並留記錄**（重算後在變更記錄寫下哪天、改了多少、為什麼）。計費類數字通常不改已結帳的期間，而是在當期記一筆調整，與 [Part 11](/posts/de-system-design-interview-part11-payments-ledger-reconciliation-zh/) 帳本的沖銷原則相同。

---

## 七、依用途選策略

同一份事件流，不同的消費者需要不同的組合。這張表是面試中最能展現判斷力的部分：

| 用途 | 重複 | 亂序 | 晚到 | 可容忍誤差 |
|---|---|---|---|---|
| 購買金額 / 計費 | 以 `order_id` MERGE，精確 | LWW by LSN | 不受影響（事實來源在後端）；定案後只做調整 | 0 |
| DAU 儀表板（定案） | 不需要：集合語意 | 不需要 | 回溯 3 天（含 D 共 4 個分區）MERGE，D+4 定案 | 0（定案後） |
| DAU 儀表板（即時） | 不需要：HLL | 不需要 | allowed lateness 1 小時，其餘交給批次 | ~1% |
| 營運監控（每分鐘事件數） | 1 小時 TTL keyed state | 不需要 | watermark + 丟棄並計數 | 數 % |
| 漏斗 / session 分析 | `event_id` 批次去重 | 依 `(user_id, device_id, seq_no)` 排序；跨裝置用校正後的 `event_time` | 定案後才算 | 小 |
| ML 訓練資料 | 精確去重 | 版本號 | **以特徵值可用的時間作為「何時可知」** | 0 洩漏 |
| ML 線上特徵 | 短 TTL 去重 | 可交換聚合 | 丟棄 | 數 % |

ML 訓練那一列值得多說一句：一筆週五發生、週日才到的事件，在週六做預測時是不可能看到的。訓練資料若依 `event_time` 回填，就把未來的資訊放進了過去——這正是 [Part 14](/posts/de-system-design-interview-part14-streaming-media-feature-platform-zh/) 的時間點正確性問題。所以特徵的 as-of join 不能用 `event_time`。用 `server_received_at` 也還不夠：事件可能在預測前就到了伺服器，卻在預測之後才被算進線上特徵。正確的截止點是**這個特徵值在線上儲存中生效的時間**——每個特徵版本要記下它何時可被讀到，as-of join 取預測時刻之前最後一個已生效的版本；`event_time` 只用來決定事件屬於特徵的哪個時間窗。

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| 購買來自訂單 CDC vs App 事件 | 付款必經後端，沒有離線晚到；有主鍵與 LSN | App 事件會重送、會晚到，且可能付款失敗 | 沒有後端記錄可用，例如第三方商店的內購只回傳用戶端收據 |
| DAU 用 `user_daily_activity` 表 vs 每次重掃事件 | 冪等、晚到修正只 MERGE 少量列 | 重掃成本 × 回溯天數 | 回溯 1 天以內、資料量小，直接重掃比維護中間表簡單 |
| 定案 DAU 用精確計數 vs HLL | 0.81% 的誤差大於晚到修正本身 | HLL 無法說「這個數字是對的」 | 需要任意維度切片、上千種組合預先聚合時，近似才划算 |
| 串流 keyed state 去重 vs 批次 MERGE 去重 | 即時、重複不會出現在儀表板上 | 72 小時 TTL 對全部事件要 300 GB 狀態 | 只對小量、高價值事件（購買）做長 TTL，其餘交給批次 |
| 精確去重 vs 單獨使用 Bloom filter | 不會靜默丟掉真事件 | 0.1% 偽陽性 = 每天約 100 萬筆真事件被丟 | 指標可容忍少算、且記憶體是硬限制；或把 Bloom 放在精確去重前當快速通道 |
| 版本號 LWW vs 到達順序覆寫 | 重播、亂序、重新快照都不會讓舊值蓋新值 | 到達順序受網路與重試影響 | 來源只有單一寫入者且經單一分區保序，到達順序就是版本順序 |

---

## 九、症狀到診斷

這類錯誤幾乎不會讓作業失敗，只會讓數字悄悄偏移。每一列都是「看到什麼 → 先查什麼 → 通常是什麼原因」：

| 症狀 | 先看的訊號 | 常見原因 | 處置 |
|---|---|---|---|
| 重跑某天後，計數比上次高 | 重跑前後 `COUNT(*)` 與 `COUNT(DISTINCT event_id)` 的差 | 去重只在單一到達分區內，重跑時讀到跨分區的重複 | 去重比對範圍涵蓋 SDK 保留期；改為 MERGE |
| 某天購買數突然翻倍 | 該時段 CDC 事件的 `op` 欄位 | CDC 重新快照，`op = r` 被當成新事件 append | 事實表改為以主鍵 MERGE。不要直接濾掉 `op = r`：故障復原後的快照可能帶有下游缺漏的訂單，濾掉就少算 |
| 已退款訂單又出現在 GMV | 該訂單各版本的 LSN 與寫入時間 | 依到達順序覆寫，舊版本後到 | MERGE 條件加 `s.lsn > t.lsn` |
| 昨天的 DAU 每天往上漲，第四天後停止 | 各 `event_date` 的數字隨時間的變化 | 這是正常的晚到修正 | 在儀表板標示「暫定」；告知使用者定案日 |
| 昨天的 DAU 在第五天之後還在變 | 「過晚事件」比例、時鐘校正失敗比例 | 某版 SDK 時間戳錯誤；或定案規則沒有生效 | 依 SDK 版本切分；檢查定案狀態欄位 |
| 即時 DAU 與隔天批次 DAU 差 2% 以上 | 兩條路徑的使用者歸屬日期 | 一邊用 `event_time`、另一邊用到達時間；或 HLL 精度設定太低 | 統一歸屬規則；調整 HLL 暫存器數 |
| 串流的分鐘指標持續膨脹 | 下游收到的同一 `(metric, minute)` 筆數 | allowed lateness 觸發更新，下游卻 append 加總 | 下游改依鍵 upsert，或處理 retract 訊息 |
| 去重作業檢查點越來越大 | 狀態大小趨勢 | TTL 沒設，或 TTL 長於需要 | 以重複時間差分佈的 p99.9 設 TTL |

最小的監控集合：事件與使用者兩個晚到直方圖（每天的 p99、p99.9、max）、每天的重複率（`1 − distinct/total`，依來源與 SDK 版本切分）、過晚事件數、時鐘校正失敗數、暫定與定案值的差距。重複率突然從 0.3% 跳到 3%，通常是某版 SDK 的重試邏輯改了——這個訊號比任何作業告警都早。

---

## 十、系統效應與系列導航

以情境為例，從 Phase 1 到 Phase 3 的變化（數字依前面的假設估算）：

| 指標 | Phase 1（依到達日批次） | Phase 3（事件日 + 回溯 + 定案） |
|---|---|---|
| DAU 歸屬的日期 | 到達日，離線使用者被算到錯的一天 | 事件日（校正後的時鐘） |
| 跨到達日的重複 | 進入結果 | 被 3 天回溯去重或 MERGE 擋下 |
| D 日 DAU 隔天早上的完整度 | 少約 0.5%（離線使用者落到後面的日期） | 暫定值同樣少約 0.5%，D+4 定案時 ≥ 99.99% |
| 購買數受 App 重送影響 | 會 | 不會（事實來源為訂單 CDC） |
| 已退款訂單復活 | 可能 | 不會（LSN 比較） |
| 當日數字可見時間 | 隔天 | 10 秒內（暫定值） |
| 去重狀態 | 無 | 購買 90 MB；一般事件 1 小時 TTL 約 4 GB |
| 每日晚到修正成本 | 不修正 | MERGE 數萬列，或重掃 600 GB（約 3 美元） |

改造後最重要的變化不在任何一個元件，而在**數字有了狀態**：使用者知道今天的數字是暫定的、知道哪天會定案、知道定案後不會再變。「對的」不是一個瞬間的性質，而是一個附帶時間點的承諾。

**本篇重點**

- 重複、亂序、晚到破壞的指標不同；先判斷指標是否天生不怕它，再決定要不要付錢處理。
- 去重的狀態大小 = 鍵速率 × TTL × 每鍵成本；TTL 由重複的跨度決定，長 TTL 只給高價值事件。
- 批次去重要跨分區邊界比對；MERGE 的日期範圍要同時套在來源與目標上。
- Bloom filter 的偽陽性會丟掉真事件，適合當精確去重前的快速通道。
- 亂序用版本號解決，不用到達順序；可交換的聚合根本不需要排序。
- 晚到的參數（allowed lateness、回溯天數、定案時間）都從量測到的晚到分佈讀出來，並把定案規則公開給使用者。

**DE 系統設計面試指南**

- [Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
- [Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
- [Part 3：串流與即時系統](/posts/de-system-design-interview-part3-streaming-realtime-zh/)
- [Part 4：儲存、倉儲與 Lakehouse 設計](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)
- [Part 5：誰在查、要多新鮮、要多準——依新鮮度選架構](/posts/de-system-design-interview-part5-freshness-sla-tiers-zh/)
- [Part 6：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part6-idempotency-rerun-backfill-zh/)
- **Part 7：重複、亂序與晚到——事件正確性的處理策略**（本篇）
- [Part 8：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part8-schema-evolution-zh/)
- [Part 9：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part9-storage-query-efficiency-zh/)
- [Part 10：完整模擬面試與常見情境](/posts/de-system-design-interview-part10-mock-interview-scenarios-zh/)
- [Part 11：支付業案例——帳本、對帳與可稽核的資料平台](/posts/de-system-design-interview-part11-payments-ledger-reconciliation-zh/)
- [Part 12：廣告業案例——點擊計費、預算控制與歸因](/posts/de-system-design-interview-part12-adtech-click-billing-attribution-zh/)
- [Part 13：叫車業案例——即時位置、供需與行程資料](/posts/de-system-design-interview-part13-ride-hailing-geo-realtime-zh/)
- [Part 14：影音串流案例——觀看事件、特徵平台與實驗指標](/posts/de-system-design-interview-part14-streaming-media-feature-platform-zh/)
- [Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板](/posts/de-system-design-interview-part15-cybersecurity-saas-dashboard-zh/)

**延伸閱讀**

- Tyler Akidau, Slava Chernyak, Reuven Lax,《Streaming Systems》（O'Reilly, 2018）第 2–3 章：watermark、trigger 與 accumulation mode
- Martin Kleppmann,《Designing Data-Intensive Applications》第 11 章：Stream Processing（時鐘、冪等與 exactly-once）
- Burton H. Bloom, "Space/Time Trade-offs in Hash Coding with Allowable Errors"（Communications of the ACM, 1970）
- Philippe Flajolet et al., "HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm"（2007）
- Apache Flink 文件：Windows — Allowed Lateness、Getting late data as a side output；State TTL
- Debezium 文件：Snapshots（`op = r` 的快照事件）
