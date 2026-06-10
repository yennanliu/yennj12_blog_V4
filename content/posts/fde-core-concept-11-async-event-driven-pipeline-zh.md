---
title: "FDE core topic - Async Event-Driven Pipeline：解耦同步 HTTP 與保護後端連線池"
date: 2026-06-08T10:00:00+08:00
draft: false
weight: 11
description: "深入剖析如何以非同步訊息傳遞取代同步 HTTP 請求，防止 LLM 推論延遲（2–30 秒）耗盡 Web Server 連線池，支撐 50,000+ 並發用戶，改善幅度達 250 倍。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Architecture", "PubSub", "AsyncDesign"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Async Event-Driven Pipeline 是將每個長時間運算（如 LLM 推論）拆成「接受請求 → 寫訊息佇列 → 立即回 202 → 背景 Worker 處理 → 客戶端輪詢或推送結果」五個步驟，徹底切斷 HTTP 連線與運算時間的綁定關係，讓連線池資源不再成為系統瓶頸。**

---

> **面試情境：** 「你們的 AI 寫作助理功能在發布後一週內，DAU 從 500 成長到 8,000，但後端開始出現大量 503，LLM 回應也從 3 秒變成 30 秒超時。你作為 FDE，如何診斷問題並提出架構改善方案？你的方案需要能支撐 50,000 DAU 而不需要垂直升級 LLM endpoint。」

---

## 一、為什麼面試官問這個

面試官真正在測試的是你對**連線資源生命週期**與**系統容量天花板**的直覺，以及你能否在架構層面解決「延遲長」這個根本矛盾，而不是靠「加機器」硬撐。這題在 FDE 面試中特別常見，因為 LLM 整合幾乎是現代應用的標配，而 LLM 的推論延遲（2–30 秒）與 Web Server 的同步模型之間存在根本性衝突。

**測試點一：容量計算能力。** 你能否當場估算「1,000 並發 × 15 秒 LLM 延遲 = 需要同時持有 1,000 個連線」，並說明為什麼典型的 Gunicorn + FastAPI 配置在 200–500 個並發時就會開始出現 503。面試官想看到的是工程師對資源約束的量化思維，而不是模糊的「系統會變慢」。

**測試點二：解耦設計思維。** 你能否清楚說明「接受請求」與「完成運算」是兩個應該獨立的生命週期，以及為什麼這個解耦不是效能優化，而是架構正確性問題。強候選人會主動提出：同步架構下你無法在不改變 API 合約的前提下水平擴展 LLM 層，但 async 架構可以讓 Web Server 和 Worker 完全獨立地擴縮。

**測試點三：端到端系統觀。** 能否講清楚 Job ID 追蹤、Pub/Sub 保證、Worker 自動擴縮、Backpressure 控制、冪等性設計、死信處理、客戶端結果取得方式等完整鏈路。弱答案只說「放個 queue 就好」，強答案把每個元件的選型理由和失敗模式都說清楚。

**弱答案典型樣貌：**「我會用 Redis 做 queue，然後用 worker 去拉。」缺乏具體數字、沒有 at-least-once 語義討論、沒講客戶端如何取得結果、沒提 autoscaling、沒有 idempotency 設計。

**強答案典型樣貌：** 從連線池耗盡的具體數字切入（「200 並發就是極限」），清楚描述五步驟流程，點出 Pub/Sub at-least-once + idempotency key 的配合，說明 KEDA 如何依據未確認訊息數量在 90 秒內從 0 擴到 100 個 Pod，最後給出 200 → 50,000 並發的量化改善（250 倍），並主動提到 SSE 推送比輪詢更省錢的理由。

---

## 二、核心原理與技術深度

### 同步架構的連線池耗盡機制

HTTP/1.1 與 HTTP/2 的 Web Server（Nginx、Gunicorn、Cloud Run）都有一個有限的連線池。每個進來的請求佔用一個連線，直到回應送出為止。當 LLM 推論需要 15 秒，這個連線在整整 15 秒內都無法被其他請求使用。

```
連線池容量計算：

  Gunicorn sync worker（最常見生產配置）：
    workers = 2 × CPU_cores + 1 = 9（4-core machine）
    每個 worker 同時處理 1 個請求（sync）
    → 最大並發 = 9 個請求

  Gunicorn gevent async worker：
    workers = 9，worker_connections = 1000
    → 理論上限 = 9,000 個並發連線
    → 但 LLM endpoint 本身有連線限制（通常 100–500）
    → 實際瓶頸在 LLM endpoint，不在 Web Server

  現實場景（FastAPI + uvicorn + async LLM client）：
    LLM endpoint max connections = 200
    LLM 推論延遲 = 15 秒
    每秒可完成的請求 = 200 / 15 = 13 個
    每秒進來 100 個請求 → 積壓速率 = 87 個/秒
    10 秒後積壓 = 870 個等待連線 → 全部超時或被拒
```

這就是為什麼「加 Web Server 機器」無法解決問題：瓶頸在 LLM endpoint 的連線數上限，而不在 Web Server 本身。唯一的出路是讓每個 HTTP 連線只佔用毫秒級的時間（寫 Pub/Sub），然後由獨立的 Worker 層管理 LLM 連線池。

**為什麼「加 Web Server 機器」無效的直覺解釋：** 假設 LLM endpoint 同時能處理 200 個連線，每個連線耗時 15 秒，則每秒能完成 200/15 ≈ 13 個請求。無論你加多少台 Web Server，這 13 req/s 的上限都不會改變——因為瓶頸在 LLM endpoint，而不在 Web Server。Async pipeline 的本質是讓 Worker 有計劃地消費 LLM endpoint 的容量（由 MaxOutstandingMessages 控制），而不是讓所有用戶的請求同時衝向 LLM endpoint。

### 非同步 Pipeline 的五步驟架構

五個步驟中，**步驟二**（Web Server 寫 Pub/Sub + 回 202）是整個設計的核心：Web Server 的工作從「執行運算」退化到「接收請求並委派」，回應時間從 2–30 秒壓縮到 < 50ms。這個 50ms 包含 Pub/Sub publish 的網路往返（通常 < 10ms）+ Firestore 初始狀態寫入（5–8ms）+ 序列化開銷（< 2ms）。剩下的所有計算複雜度都移到了獨立的 Worker 層，Web Server 本身變得完全無狀態、高度可擴縮。

```
步驟一：Client 送出請求
┌──────────────────┐
│  Client          │──── POST /generate ────▶
└──────────────────┘     { prompt, user_id }

步驟二：Web Server 接受並寫入 Pub/Sub（< 50ms）
┌──────────────────────────────────────────────┐
│  Web Server（FastAPI / Cloud Run）           │
│  1. 生成 job_id = UUID4                      │
│  2. publish({ job_id, prompt, user_id })     │
│     to Pub/Sub Topic: llm-jobs               │
│  3. Firestore.set(job_id, {status: pending}) │
│  4. return HTTP 202 { job_id }               │
└──────────────────────────────────────────────┘
                    ▼ publish（< 10ms）
┌──────────────────────────────────────────────┐
│  Cloud Pub/Sub                               │
│  Topic: llm-jobs                             │
│  - at-least-once delivery                    │
│  - 7-day message retention                   │
│  - Dead-Letter Topic: llm-jobs-dlq           │
└──────────────────────────────────────────────┘
                    ▼ pull
步驟三：Worker 處理（2–30 秒，完全非同步）
┌──────────────────────────────────────────────┐
│  Worker Pod（GKE Deployment）                │
│  1. pull message from subscription           │
│  2. idempotency check（Firestore）           │
│  3. call LLM endpoint（2–30s）              │
│  4. write result to Firestore                │
│  5. ack message                              │
└──────────────────────────────────────────────┘
                    ▼ write result
┌──────────────────────────────────────────────┐
│  Firestore                                   │
│  /jobs/{job_id}                              │
│  { status: done, result: "...", ts: ... }    │
└──────────────────────────────────────────────┘
                    ▲ read / push
步驟四＋五：Client 取得結果
┌──────────────────┐
│  Client          │◀── SSE push（job done）
│                  │    或 GET /jobs/{job_id}
└──────────────────┘    （輪詢）
```

### Pub/Sub 的三個關鍵保證與其代價

**At-least-once delivery（至少一次投遞）：** Pub/Sub 保證每條訊息至少被投遞一次，但不保證恰好一次。網路重傳、Worker 未在 ack deadline 內確認、訂閱者重啟——這些都會造成重複投遞。代價是 Worker 必須實作冪等性（idempotency），否則同一個 LLM 請求可能被呼叫兩次，費用翻倍。

**7 天訊息保留：** 即使所有 Worker Pod 同時崩潰，訊息不會遺失。Pod 恢復後從最早的未確認訊息繼續處理。這個保證讓 Worker 可以安心做 rolling update、scale down 到 0，不需要擔心資料遺失。

**Dead-Letter Topic：** 訊息投遞失敗超過 `max_delivery_attempts`（建議設 5）次後，自動轉送到 Dead-Letter Topic。常見觸發原因：訊息格式錯誤（JSON 解析失敗）、LLM endpoint 持續 5xx、Worker 邏輯 bug 導致每次都拋例外。Dead-Letter Topic 搭配 Cloud Monitoring alert，讓運維人員在問題擴散前看到訊號。

### Backpressure 控制：MaxOutstandingMessages

```
問題場景：Worker Pod 記憶體 = 4GB
每個 LLM 請求記憶體峰值 = 400MB（含 model response buffer）
若不設限，Worker 同時拉取 100 條訊息：
  100 × 400MB = 40GB >> 4GB → OOM kill → Pod 重啟 → 訊息重新入隊

正確設定：
  MaxOutstandingMessages = floor(4GB / 400MB) × 安全係數 0.7 ≈ 7
  （保守值，確保不 OOM）

效果：
  Pub/Sub Subscription 等待 Worker ack 後才推送下一條
  Worker 永遠只同時處理 ≤ 7 條訊息
  記憶體峰值 = 7 × 400MB = 2.8GB（在 4GB 以內，有 buffer）
  
副作用（需要知道）：
  每個 Pod 吞吐量 = 7 / 15s（LLM 延遲）= 0.47 jobs/s
  要達到 100 jobs/s 的吞吐量，需要 ceil(100 / 0.47) = 213 個 Pod
  → 這正是 KEDA 自動擴縮要解決的問題
```

### KEDA 自動擴縮：從 0 到 100 Pod 的 90 秒

KEDA（Kubernetes Event-Driven Autoscaling）透過 GCP Pub/Sub Scaler，監控 subscription 的 `num_undelivered_messages`（未確認訊息數量），動態調整 Worker Deployment 的 replica 數量。這讓 idle 期間 Pod 縮到 0 個（節省費用），流量突增時快速擴出。

```
KEDA 決策公式：

  target_replicas = ceil(num_undelivered / messages_per_replica)
  
  其中：
  messages_per_replica = MaxOutstandingMessages = 7（上例）
  
  場景一（idle）：
    num_undelivered = 0 → target = 0 pods
    
  場景二（突發流量）：
    t=0s:  1,000 條訊息進入 Pub/Sub
    t=10s: KEDA 偵測到 num_undelivered = 1,000
           target = ceil(1000 / 7) = 143 pods
    t=90s: GKE 完成 node provisioning + pod scheduling
           143 pods 就緒，開始處理訊息
    t=120s: num_undelivered 快速下降 → pod 數也隨之縮減
    
  冷啟動延遲（需要對 Client 說明）：
    0 → 1 pod：60–90 秒（GKE node auto-provisioning）
    已有 node 但 pod 未就緒：20–30 秒
    → 可設 minReplicaCount = 1 保留一個「暖機 pod」避免首次冷啟動
```

### 客戶端結果取得的三種模式比較

客戶端取得非同步結果的方式選擇，直接影響費用結構與用戶體驗。這是面試中常被忽略但很能展現系統設計細節的部分。

```
模式一：Polling（輪詢）
  Client                     Web Server          Firestore
    │─── GET /jobs/{id} ────▶│─── get(id) ──────▶│
    │◀── { status: pending }─│◀── { pending } ────│
    │    （等 2 秒）          │                    │
    │─── GET /jobs/{id} ────▶│─── get(id) ──────▶│
    │◀── { status: done } ───│◀── { done, result }│
  
  費用：reads = (LLM 延遲 / 輪詢間隔) × 並發用戶數
  15s / 2s × 10,000 = 75,000 Firestore reads / 批次

模式二：SSE（Server-Sent Events）推送
  Client                  Web Server              Firestore
    │─── GET /jobs/{id}/stream ▶│                 │
    │    （建立 SSE 長連線）     │                 │
    │                           │◀── onSnapshot ──│（Worker 寫入時觸發）
    │◀── data: {status: done} ──│                 │
    │    （Client 關閉連線）     │                 │
  
  費用：1 次 Firestore read（onSnapshot 觸發）
  適合：結果延遲 2–30 秒，用戶在頁面上等待

模式三：Webhook 回呼（適合 Server-to-Server）
  Client 呼叫者提供 callback_url 在請求中
  Worker 完成後直接 POST callback_url
  Client 不需要保持連線
  
  費用：0 Firestore reads（直接推送）
  適合：API 整合、批次處理、不在瀏覽器的用戶
```

**選擇建議：** 瀏覽器用戶 → SSE；延遲 < 3s 且用戶有耐心 → 輪詢（簡單）；Server-to-Server API → Webhook；需要雙向串流（如多輪對話）→ WebSocket。實務上，大多數 LLM 應用會同時支援 SSE（主要 Web 用戶）與 Webhook（企業 API 用戶），輪詢則作為 SSE 連線失敗時的 fallback。

---

### 訊息重複處理的冪等性設計

```python
# Worker 處理訊息的正確模式（偽代碼）

def process_message(message: pubsub_v1.Message):
    job_id = message.message_id   # Pub/Sub 保證 message_id 全域唯一
    payload = json.loads(message.data)

    # Firestore 事務：原子性讀寫，防止 race condition
    job_ref = db.collection("jobs").document(job_id)
    
    @firestore.transactional
    def try_claim(transaction):
        snapshot = job_ref.get(transaction=transaction)
        if snapshot.exists and snapshot.get("status") != "pending":
            return False   # 已處理，跳過
        transaction.update(job_ref, {"status": "processing"})
        return True
    
    if not try_claim(db.transaction()):
        message.ack()   # 重複投遞，安全忽略
        return
    
    try:
        result = call_llm(payload["prompt"])   # 2–30 秒
        job_ref.update({"status": "done", "result": result})
    except Exception as e:
        job_ref.update({"status": "error", "error": str(e)})
        message.nack()   # 讓 Pub/Sub 重新投遞（最多 max_delivery_attempts 次）
        return
    
    message.ack()
```

---

## 三、三個實作層次

三個層次反映現實中的演進路徑，而不是「一次到位」的理想設計。**Layer 1** 讓你在 1–2 天內驗證 async pipeline 的核心假設（連線池不再是瓶頸）；**Layer 2** 讓系統能安全承受真實用戶流量而不需要 SRE 半夜起床處理；**Layer 3** 則是當業務規模和合規要求都提升後的自然演進。每一個層次的升級都有明確的觸發條件，不要因為「以後可能需要」就跳層。

### Layer 1 — 最小可行（Minimal）

**核心實作：**
- Web Server 寫 job 到 Cloud Pub/Sub，立即回 202 + `job_id`（< 50ms）
- 單一 Worker Deployment（replicas = 1）訂閱 Pub/Sub Subscription
- 結果寫入 Firestore /jobs/{job_id}
- Client 用固定頻率輪詢 GET /jobs/{job_id}（每 2 秒）
- 無 Dead-Letter Topic，無 idempotency check，MaxOutstandingMessages 使用預設值（1,000）

**解決的核心問題：** Web Server 連線不再被 LLM 延遲佔用，可支撐的並發用戶從 200 提升到幾千個（瓶頸移到 Worker 處理速度）。

**還沒解決的問題：**
- Worker 單點故障：Pod crash → 同一條訊息要等 ack deadline（預設 10 秒）過期才重試
- 無冪等性：重複投遞 → 重複 LLM 呼叫 → 費用加倍
- 無 Backpressure：Worker 可能 OOM，造成 Pod 重啟雪崩
- Client 輪詢造成不必要的 Firestore 讀取費用（10,000 用戶 × 2次/秒 = 20,000 reads/s ≈ $0.06/s = $5,000/月）

**成本估算：** 低。1 個 Cloud Run Job 或 1 個 GKE Pod，1–2 天可上線。Pub/Sub 費用約 $0.04 / 百萬條訊息。以 50,000 DAU、每人每天 5 個 LLM 請求計算，每月 Pub/Sub 費用約 $0.30——幾乎可忽略，系統主要成本仍在 LLM API 呼叫與 GKE 節點上。

Layer 1 最適合的部署目標：**驗證 async pipeline 的可行性**，並讓工程團隊熟悉 Pub/Sub + Firestore 的操作模式，為後續升級到 Layer 2 打好基礎。不要跳過 Layer 1 直接做 Layer 3——KEDA + CMEK + 多 region 的複雜度會讓「能不能 work」這個最基礎的問題變得難以除錯。

---

### Layer 2 — 生產就緒（Production-Ready）

**相較 Layer 1 新增的元件與設計決策：**

**① 冪等性（Idempotency）：** Firestore 事務 + message_id 作為 document ID，確保重複投遞安全忽略。LLM API 費用節省可觀——Pub/Sub 重複率通常 < 1%，但在 Worker rolling update 期間可能短暫升至 5–10%。

**② MaxOutstandingMessages 設定：** 依 Pod RAM / 單一請求記憶體峰值計算，防止 OOM kill。這是最容易被忽視但影響最大的配置。

**③ Dead-Letter Topic + Monitoring：**
- Dead-Letter Topic `llm-jobs-dlq` 接收 > 5 次失敗的訊息
- Cloud Monitoring alert：dlq 訊息數量 > 10 → PagerDuty
- 搭配 Cloud Logging 查看失敗原因（格式錯誤、LLM 持續 5xx 等）

**④ Worker replicas ≥ 2：** 消除單點故障。一個 Pod 升級時另一個繼續處理訊息。

**⑤ SSE（Server-Sent Events）推送結果，取代 Client 主動輪詢：**
```
Client 與 Web Server 建立 SSE 連線（長連線，但不佔 LLM 連線）
Worker 寫入 Firestore 後，觸發 Firestore onSnapshot listener
Web Server 透過 SSE 推送 { job_id, status, result }
Client 收到後關閉 SSE 連線

費用對比：
  輪詢（2s 間隔）：10,000 users × 30 reads/user × $0.06/100K reads = $1,800/月
  SSE：每個 job 只有 1 次 Firestore write + 1 次 onSnapshot = 幾乎可忽略
```

**⑥ Ack deadline 延長：** 將 ack deadline 設為 60 秒（LLM 最大延遲 30s 的 2 倍），並在 LLM 呼叫過程中每 30 秒呼叫 `modifyAckDeadline(60s)` 延長，防止 Pub/Sub 誤判超時而重複投遞。

**⑦ 優雅關閉（Graceful Shutdown）：** Worker Pod 收到 SIGTERM 時，停止拉取新訊息，等待當前正在處理的 LLM 請求完成（最多等 `terminationGracePeriodSeconds = 90s`），再退出。這確保 GKE rolling update 不會中斷正在進行的 LLM 呼叫，避免未 ack 的訊息回到 queue 被重新處理。

**解決的新問題：** 重複 LLM 呼叫的費用問題、Worker OOM 雪崩、死信可見性、Client 體驗（即時推送 vs 等待輪詢）、Worker 升級期間的服務連續性。

**成本估算：** 中。SSE endpoint 開發 + Firestore 事務設計 + Dead-Letter Monitoring，約需 3–5 個工作天。月費用增加約 $50–200（SSE 保持連線的 Cloud Run 費用）。

---

### Layer 3 — 企業級（Enterprise-Grade）

**相較 Layer 2 新增的元件與設計決策：**

**① KEDA ScaledObject（自動擴縮至 0）：**
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: llm-worker-scaler
spec:
  scaleTargetRef:
    name: llm-worker
  minReplicaCount: 0        # idle 時縮到 0，節省費用
  maxReplicaCount: 100
  cooldownPeriod: 300       # 5 分鐘冷卻，避免 pod 頻繁啟停
  triggers:
  - type: gcp-pubsub
    metadata:
      subscriptionName: llm-jobs-sub
      value: "7"            # 每個 Pod 對應 7 個 unacked messages
```

**② 分層儲存（Tiered Storage）：**
- 熱層：Firestore（TTL 24 小時）—— Client 取結果用，< 10ms 讀取
- 溫層：GCS（保留 30 天）—— 稽核、重放、分析用
- 清理 Cloud Function：每小時掃描 Firestore TTL 過期文件並複製到 GCS

**③ 訊息加密（Cloud KMS CMEK）：**
- Pub/Sub 訊息含用戶 prompt（可能含 PII）
- Cloud KMS CMEK 加密 Pub/Sub 訊息與 Firestore 文件
- 符合 HIPAA/GDPR 合規要求（金融、醫療產業必備）

**④ 分散式追蹤（Distributed Tracing）：**
- `job_id` 作為 trace context propagation 的 carrier
- Cloud Trace 呈現完整延遲鏈路：Web Server（2ms） → Pub/Sub publish（8ms） → queue wait（Xs） → Worker LLM call（15s） → Firestore write（5ms）
- 讓 SRE 精確定位「慢在哪一段」，而不是在整個系統中盲目搜索

**⑤ 多 Region Pub/Sub + 跨區 Worker：**
- Pub/Sub Global Topic 自動在多個 region 複製訊息
- GKE Multi-Region Deployment 讓 Worker 就近處理，降低網路延遲
- 單 region 故障不影響整體服務

**⑥ 費用標籤與成本分配：**
```
每條 Pub/Sub 訊息加入 attributes：
  { user_tier: "premium", job_type: "translation", region: "us-west1" }

BigQuery 分析每日費用：
  SELECT job_type, user_tier, SUM(llm_cost_usd)
  FROM llm_job_costs
  GROUP BY 1, 2
  
→ 為不同 job_type 設定差異化的 SLA 與費用分攤
```

**成本估算：** 高。KEDA 安裝設定（約 1 天）、CMEK 金鑰管理流程（合規審查 1–2 週）、多 region 配置增加 Pub/Sub 費用約 20%，但 idle 時 Pod 縮到 0 可節省 60–80% 的運算費用（LLM workload 通常非 24/7 滿載）。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| Worker 不做 idempotency check，直接處理每條訊息 | Pub/Sub at-least-once 重複投遞 → 重複呼叫 LLM，費用倍增；若 LLM 有副作用（如寫 DB），資料重複 | 用 Pub/Sub message_id 作為 Firestore document ID，事務內檢查 status ≠ "pending" 則直接 ack 跳過 |
| 不設 MaxOutstandingMessages，Worker 無限拉取 | 大量訊息同時進入 Worker → 記憶體溢出（OOM kill）→ Pod 重啟 → 訊息重新入隊 → 雪崩效應，所有訊息都在重試 | 依 Pod RAM / 單一請求記憶體峰值計算，加 0.7 安全係數；4GB Pod + 400MB/request → MaxOutstandingMessages = 7 |
| Client 輪詢頻率過高（每 500ms 一次） | Firestore 讀取費用激增；10,000 用戶 × 2次/秒 = 20,000 reads/s ≈ $5,000/月；Firestore 也可能觸發流量限制 | 改用 SSE 或 WebSocket 推送；若仍用輪詢，用 exponential backoff（1s → 2s → 4s → max 30s），並在 job 完成後停止輪詢 |
| Pub/Sub ack deadline 設太短（預設 10s） | LLM 推論 15 秒 > ack deadline 10s → Pub/Sub 誤判超時重投 → 同一 job 被多個 Worker 同時處理 → 競爭條件，結果可能被覆蓋 | 將 ack deadline 設為 max_llm_latency × 2（例如 60s）；LLM 呼叫過程中每 30 秒呼叫 modifyAckDeadline 延長 |
| 不設 Dead-Letter Topic | 持續失敗的訊息（格式錯誤、LLM 持續 5xx）無限重試，佔用 Worker 資源；真正的 backlog 被「毒訊息」堵塞 | 設 max_delivery_attempts = 5，配置 Dead-Letter Topic + Monitoring alert；人工或自動 replay 機制處理 DLQ 訊息 |
| KEDA minReplicaCount = 0，但沒說明冷啟動影響 | 流量突然湧入時，0 → 第一個 Pod 就緒需要 60–90 秒（含 GKE node provisioning）；這段時間訊息積壓，用戶等待結果 | 在 SLA 中明確說明「首次請求可能需要 2 分鐘」；或設 minReplicaCount = 1 維持暖機 Pod（約 $30/月，避免冷啟動） |
| 同步等待 Pub/Sub publish 完成才回 202 | publish() 若遇 Pub/Sub 短暫延遲（罕見），Web Server 回應時間變長；失去「< 50ms 立即回應」的核心優勢 | 使用 async publish（fire-and-forget with callback）；publish 失敗透過 retry policy 處理，Web Server 不等待 publish 完成 |

---

## 五、與其他核心主題的關聯

- **Part 7（LLM Serving 與推論優化）**：Worker 呼叫 LLM 的方式（streaming vs batch、token budget 控制、retry 策略）直接影響 Pub/Sub 的 ack deadline 設定與 Worker Pod 的記憶體需求——streaming 模式需要更長的 ack deadline，但可以更早開始寫部分結果到 Firestore。

- **Part 9（資料庫選型：Firestore vs Spanner vs Redis）**：job 狀態儲存需要兼顧寫入速度與讀取一致性；Firestore 適合 per-job document 存取模式（每個 job_id 獨立文件，無熱點）；Redis 可作為熱點狀態快取，讓 Client 輪詢時在 < 1ms 內得到回應，而不是每次都打 Firestore。

- **Part 14（Observability：Traces、Metrics、Logs 三位一體）**：job_id 作為 trace context propagation 的 carrier，讓 Web Server → Pub/Sub → Worker → LLM 的完整延遲鏈路在 Cloud Trace 中可視化。關鍵 metric：Pub/Sub unacked message count（容量指標）、Worker LLM call P99 latency（效能指標）、DLQ 訊息數量（健康指標）。

- **Part 19（Cost Engineering：算力費用優化）**：KEDA 將 Worker Pod 縮到 0 是 async pipeline 最大的成本優勢——同步架構需要預留足夠 worker capacity 應付峰值（假設峰值是均值的 10 倍，就要常備 10 倍的機器），async 架構只在有訊息時才有 Pod 費用，閒置期間費用接近 $0。

---

## 六、為什麼選 X 不選 Y

面試官幾乎必然追問：「為什麼不用 Redis Queue？為什麼不用 WebSocket 取代 SSE？為什麼不用 Cloud Tasks？」以下逐一說明，並點出什麼情況下答案會反轉。

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Y 何時反轉成正確選擇 |
|------|------------|--------------|-------------------|
| **Cloud Pub/Sub** vs Redis Queue | 原生 at-least-once 保證、7 天訊息保留、Dead-Letter Topic 內建、Serverless（無需管理 Redis Cluster）、自動多 region 複製 | Redis Queue（Bull/BullMQ）需要自行管理 Cluster HA、Persistence、Monitoring；Redis 重啟可能遺失未持久化的訊息 | 延遲要求極低（< 5ms queue write），或已有 Redis 基礎設施且團隊熟悉 Bull/BullMQ；Redis 的訊息 TTL 可設得更靈活 |
| **SSE（Server-Sent Events）** vs WebSocket | SSE 是單向推送（Server → Client），實作比 WebSocket 簡單；HTTP/2 可多路複用 SSE 流；不需要維護雙向連線狀態；Cloud Run/Load Balancer 原生支援 SSE 長連線 | WebSocket 需要有狀態的連線管理（哪個 connection 對應哪個 user）；Cloud Run 的 WebSocket 連線時間限制（1 小時）與 scale-to-zero 衝突 | 需要雙向互動（如即時對話、協作編輯）；LLM streaming token 逐字推送（SSE 也可，但 WebSocket 更自然） |
| **Firestore** vs Cloud Spanner（狀態儲存） | per-job document 存取模式無全域事務需求；Firestore 自動多 region、TTL 內建、無需管理 schema；< 10ms 讀寫；成本比 Spanner 低 10–20 倍 | Spanner 適合需要跨文件強一致性事務的場景（如金融帳務）；job 狀態之間通常無交叉依賴，不需要 Spanner 的全域事務 | job 之間有依賴關係（如 job B 必須在 job A 完成後才能執行）且需要強一致性保證；或已有 Spanner 基礎設施 |
| **KEDA** vs HPA（Kubernetes HPA） | HPA 基於 CPU/Memory metrics，無法直接感知 Pub/Sub unacked message count；Pub/Sub 負載與 CPU 相關性弱（Worker 主要在等 LLM IO，CPU 低但 backlog 高）；KEDA 支援 scale-to-zero | HPA 是 Kubernetes 原生，無需額外安裝；對 CPU-bound workload（如圖像處理）仍然適用 | Workload 是 CPU-bound 且與 queue depth 正相關；或團隊不想引入 KEDA 的額外依賴（KEDA Operator 需要維護） |
| **Pull Subscription** vs Push Subscription | Pull 讓 Worker 自己控制拉取速率（配合 MaxOutstandingMessages 實作 Backpressure）；Worker 不健康時不拉取，不會被 Pub/Sub 強推訊息過來 | Push Subscription 讓 Pub/Sub 主動呼叫 Worker HTTP endpoint，實作更簡單（Worker 像普通 HTTP server）；不需要 Worker 常駐輪詢 | Worker 是無狀態 HTTP server（如 Cloud Run）且不需要精細控制 Backpressure；或訊息量小、LLM 延遲短（< 1s），Worker 不會被壓垮 |
| **Pub/Sub + Firestore**（job 追蹤）vs 只用 Pub/Sub | Pub/Sub 本身不提供 job 狀態查詢（只能知道訊息有沒有被 ack，不知道處理結果）；Client 需要查詢 job 狀態；Firestore 提供 < 10ms 的 point lookup | 若 Client 完全不需要查詢狀態（fire-and-forget），只用 Pub/Sub 就夠；Firestore 增加一層儲存費用與寫入延遲 | 純 fire-and-forget 場景（如非同步日誌處理、ETL pipeline），Client 不需要得知處理結果或狀態 |

---

## 七、系統效應：同步 vs 非同步的量化對比

| 指標 | 同步架構 | Async Pipeline（Layer 2） | 改善幅度 |
|------|---------|--------------------------|---------|
| **最大並發用戶** | ~200（連線池上限） | 50,000+（Pub/Sub + KEDA） | 250× |
| **Web Server 回應時間** | 2–30 秒（等 LLM 完成） | < 50ms（寫 Pub/Sub + 回 202） | 400× P50 |
| **LLM endpoint 連線數** | 與並發用戶數正比（200 用戶 = 200 連線） | 與 Worker Pod 數正比（獨立控制，上限 100 pods × MaxOutstandingMessages = 700 連線） | 解耦 |
| **503 錯誤率（峰值）** | 流量超過 200 並發 → 50%+ 503 | 流量超過 100 pods × 0.47 jobs/s = 47 jobs/s → 訊息積壓，但不 503 | 無雪崩 |
| **Pod idle 費用** | 需要常備 worker 應付峰值（峰值 10× 均值 → 常備 10× 費用） | KEDA scale-to-zero，idle 費用 $0 | 60–80% 節省 |
| **訊息遺失風險** | HTTP timeout 後客戶端無從得知結果 | Pub/Sub 7 天保留，Pod crash 後自動重試 | 近零遺失 |
| **部署複雜度** | 低（單一 Web Server Deployment） | 中（Web Server + Pub/Sub + Worker + Firestore + KEDA） | +4 個元件 |
| **LLM 費用（重複呼叫）** | 無重複（sync，每請求呼叫一次） | 有重複（at-least-once，但 idempotency check 後實際重複 < 1%） | 費用增加 < 1% |

**關鍵轉折點（Flip Point）：** 若 LLM 推論延遲 < 500ms（如小型模型或快取命中），同步架構仍然可行且更簡單。Async Pipeline 的引入成本（4 個新元件、idempotency 設計、KEDA 維運）只在延遲 > 1 秒、並發 > 100 用戶時才值得。另一個值得注意的指標是「部署複雜度」欄：從 1 個元件增加到 5 個元件，意味著 oncall runbook、監控 dashboard、告警規則都需要同步擴充，這是工程師在架構決策中常常低估的隱性成本。

---

## 八、面試一句話（Killer Phrase）


> *「同步 LLM 架構的根本問題不是速度，而是資源佔用時間：一個 15 秒的推論請求讓 HTTP 連線整整被持有 15 秒，1,000 個並發用戶就需要 1,000 個同時持有的連線，超過連線池上限後整個系統雪崩，加機器也無法解決因為瓶頸在 LLM endpoint 的連線數上限。Async Event-Driven Pipeline 的核心是將『接受請求』與『完成運算』的生命週期完全解耦——Web Server 在 50ms 內寫訊息到 Cloud Pub/Sub 並回 202，Worker Pool 獨立訂閱並處理，以 Pub/Sub message_id 作為 idempotency key 防止重複 LLM 呼叫，結果透過 SSE 推送給 Client；再搭配 KEDA 依 unacked message 數量在 90 秒內從 0 自動擴到 100 個 Pod，整體架構讓相同的後端資源從支撐 200 個並發用戶提升到 50,000 個，改善幅度 250 倍，而且 idle 期間 Pod 縮到 0，費用幾乎為零。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-10-caching-strategies-zh/) | [後一篇](/posts/fde-interview-core-topic-12-vector-search-embedding-pipeline-zh/) →

---

*本文是「FDE 面試核心主題」系列第 11 篇，共 25 篇。每篇聚焦一個高頻考題，從原理到實作到面試表達方式完整覆蓋。*
