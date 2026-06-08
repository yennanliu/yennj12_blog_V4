---
title: "Backpressure & Fair-Share：多租戶流量削峰與公平資源排程"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析 Token Bucket 反壓機制與加權公平排隊，說明多租戶 AI 平台如何在突發流量下保障每個租戶的最低吞吐量，並以 Redis Lua 腳本實現亞毫秒級限速。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Scalability", "RateLimiting", "MultiTenant"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Backpressure 是下游受限資源（GPU 配額、LLM 速率上限）主動向上游發出「放慢」訊號的機制；Fair-Share 排程確保在削峰過程中每個租戶仍獲得保證的最低吞吐量，讓流量尖峰不會讓任何單一租戶將其他人餓死。**

---

## 一、為什麼面試官問這個

多租戶 AI 平台的核心挑戰不是「如何服務單一大客戶」，而是「如何讓 500 個中小租戶與 5 個企業租戶共存，同時保證 SLA」。面試官用這個題目測試三件事：

- **系統思維**：你是否理解流量從 API Gateway → Queue → Worker → LLM 整條鏈的壓力傳導方式，而不只是會設定 nginx rate limit。拿到這類題目，強答案一定會在 2 分鐘內畫出流量路徑，標明每個節點的限速機制。
- **數字直覺**：Redis Token Bucket 0.5 ms vs DB-based 15 ms；在 50K req/s 的規模下，這個差距決定了你的 rate-limit 層是否成為系統瓶頸。能說出這個數字，代表你有實際操作過，不是只讀過文件。
- **公平性設計**：高付費租戶應優先，但「優先」不等於「獨占」。能說清楚 floor rate 與 burst allowance 的區別，以及它們如何透過獨立 worker pool 實現隔離，才算真正懂多租戶設計。

**弱答案長這樣**：「我會用 nginx 的 limit_req 或 API Gateway 的 quota 設定來限速，超限就回 429。」— 這只說到最表層；沒提 Token Bucket 內部機制、Redis 的原子性問題、Pub/Sub 作為無限緩衝的作用，也沒有 Fair-Share 的 weighted queuing 概念。

**強答案長這樣**：從 Token Bucket 的數學定義出發，說明為什麼需要 Lua 腳本保原子性，再展示 Pub/Sub + KEDA 如何形成租戶隔離的工作池，最後給出「15× 突發下 P99 延遲從 >30s 降到 <2s」這類可量化的效果。面試官聽到這樣的回答，會接著問「如果 Redis 掛了怎麼辦」和「KEDA scale-up 的延遲是多少」—— 這才是真正技術深度的對話。

---

## 二、核心原理與技術深度

### 2.1 Token Bucket 數學模型

Token Bucket 是業界最廣泛使用的平滑限速演算法，比 Leaky Bucket 和 Fixed Window Counter 都更貼近真實業務流量的特性。每個租戶擁有獨立的桶：

```
容量（Capacity）  ： C tokens        ← 最大突發量（burst headroom）
補充速率（Refill）： R tokens/s      ← 穩態允許吞吐量，對應 SLA 等級
請求成本（Cost）  ： T tokens        ← 通常 = 1；或依 prompt token 數計費
```

當請求到達時執行以下邏輯：

```
1. Δt = now - last_refill_time
2. tokens = min(C,  tokens + R × Δt)   ← 補充但不超過上限
3. if tokens >= T:
       tokens -= T;  allow()
   else:
       reject(429) or enqueue(Pub/Sub)
```

**突發吸收能力分析**：一個 `C = 500, R = 100 tokens/s` 的桶，允許租戶在 1 秒內瞬間打出 500 個請求，之後穩定在 100 req/s。這讓正常業務的週期性小突發（整點 cron job、批次上傳）不會被誤殺。

**Leaky Bucket 的比較**：Leaky Bucket 以固定速率「漏」出請求，輸出極為平滑，但完全不允許突發。Token Bucket 的 C 參數讓系統在突發容量內表現出 Leaky Bucket 特性，超出容量才開始排隊，更符合 AI 平台的工作負載（訓練任務週期性大請求 + 推論任務持續小請求並存）。

### 2.2 Redis Lua 腳本：原子 check-and-decrement

分散式場景下，「查桶→判斷→扣減」三步必須原子執行，否則在 10K req/s 的高並發下極易發生 race condition：兩個 worker 同時讀到桶有 1 token，都判斷可放行，都執行扣減，實際消費 2 tokens，等於超限放行。

Redis 的 Lua 腳本在單執行緒模型下保證整段腳本原子執行：

```lua
-- KEYS[1] = "tb:{tenant_id}"
-- ARGV[1] = capacity (C)
-- ARGV[2] = refill_rate (R, tokens per second)
-- ARGV[3] = cost (T)
-- ARGV[4] = now_ms (current time in milliseconds)

local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])
local now      = tonumber(ARGV[4])

local data        = redis.call("HMGET", key, "tokens", "last_refill")
local tokens      = tonumber(data[1]) or capacity
local last_refill = tonumber(data[2]) or now

-- 依時間差補充 tokens，使用毫秒精度避免 1 秒截斷問題
local delta  = math.max(0, now - last_refill) / 1000.0   -- 轉為秒
local tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
if tokens >= cost then
    tokens  = tokens - cost
    allowed = 1
end

-- 持久化新狀態；TTL = 桶填滿所需時間 + 5 秒緩衝
redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
redis.call("PEXPIRE", key, math.ceil(capacity / rate * 1000) + 5000)
return allowed
```

部署時用 `SCRIPT LOAD` 預載腳本取得 SHA，後續呼叫 `EVALSHA` 節省頻寬：

```python
sha = redis_client.script_load(LUA_SCRIPT)

def check_token_bucket(tenant_id: str, cost: int = 1) -> bool:
    allowed = redis_client.evalsha(
        sha,
        1,                          # numkeys
        f"tb:{tenant_id}",          # KEYS[1]
        str(CAPACITY[tenant_id]),   # ARGV[1]
        str(RATE[tenant_id]),       # ARGV[2]
        str(cost),                  # ARGV[3]
        str(int(time.time() * 1000))  # ARGV[4]
    )
    return bool(allowed)
```

### 2.3 延遲數字：為什麼 Redis 是唯一選擇

```
方案              P50 延遲    P99 延遲    50K req/s 總開銷
──────────────────────────────────────────────────────────
Redis（同區域）   0.3 ms      0.8 ms      40 ms（P99 視角）
Redis（跨區域）   2 ms        5 ms        250 ms
Cloud Spanner    5 ms        20 ms       1,000 ms  ← 成為瓶頸
PostgreSQL       3 ms        15 ms       750 ms    ← 成為瓶頸
本地 pod 記憶體   0.01 ms     0.1 ms      N/A（無法分散式）
```

**為什麼不用本地快取**：若每個 API Gateway pod 各自維護計數器，100 個 pod 就有 100 倍超額放行。本地快取只能作為「第一道預過濾」（過濾明顯超限的瞬間爆量），真正的 check-and-decrement 必須在集中式 Redis 執行。

### 2.4 Fair-Share 加權公平排隊

Token Bucket 決定「是否放行」；Fair-Share 決定「被排隊的請求以什麼順序執行」，以及「每個租戶等級保證的最低吞吐量」。

```
租戶等級      Refill Rate   Bucket Cap   Floor Rate    月費（示例）
─────────────────────────────────────────────────────────────────
Enterprise    1,000 req/s   5,000        100 req/s     $10,000+
Premium         200 req/s   1,000         20 req/s     $1,000+
Standard         50 req/s     200          5 req/s       $100+
Free             10 req/s      50          1 req/s       $0
```

**Floor Rate 的關鍵性**：即使 Enterprise 租戶正在全速衝擊系統，Standard 租戶仍保證 5 req/s。這不是靠優先佇列「謙讓」實現的，而是透過**完全獨立的資源池**達成：Enterprise worker pool 有 100 個 pod，Standard pool 有 10 個 pod，兩個 pool 之間沒有任何資源共享，Standard 的 pod 永遠不會被 Enterprise 流量搶走。

### 2.5 系統架構流程

```
                    ┌──────────────────────────────────────────┐
  用戶請求           │             API Gateway                  │
 ──────────▶        │   驗證 JWT → 解析 tenant_id → 取得 tier  │
                    └──────────────────┬───────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │          Redis Token Bucket              │
                    │   EVALSHA lua_sha  ← 0.5ms P99          │
                    │   ┌──────────────────────────────────┐   │
                    │   │  key: tb:tenant-abc              │   │
                    │   │  tokens: 487 / 500  (Enterprise) │   │
                    │   │  last_refill: 1749340800123 ms   │   │
                    │   └──────────────────────────────────┘   │
                    └───────────┬─────────────────┬────────────┘
                                │ allowed = 1     │ allowed = 0
                                ▼                 ▼
               ┌────────────────────────┐  ┌───────────────────────┐
               │  Publish to Pub/Sub    │  │  HTTP 429             │
               │  Topic（依 tier 路由） │  │  Retry-After: 0.5s    │
               └──────────┬─────────────┘  └───────────────────────┘
                          │
          ┌───────────────┼──────────────────┐
          ▼               ▼                  ▼
 ┌────────────────┐ ┌──────────────┐  ┌──────────────────┐
 │  enterprise-   │ │  premium-    │  │  standard-       │
 │  subscription  │ │  subscription│  │  subscription    │
 └────────┬───────┘ └──────┬───────┘  └────────┬─────────┘
          │                │                    │
 KEDA ScaledObject  KEDA ScaledObject   KEDA ScaledObject
 min:10 max:100     min:5  max:30       min:2  max:10
          │                │                    │
          └────────────────┴────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   Vertex AI / LLM     │
               │   共用配額 Pool        │
               │   （各 tier 有獨立    │
               │    配額子分配）        │
               └───────────────────────┘
```

### 2.6 Pub/Sub Flow Control 的反壓訊號

Pub/Sub subscriber 端的 `FlowControlSettings` 是反壓的最後一道防線，確保 worker pod 不會因接收速度遠超處理速度而 OOM：

```python
# Cloud Pub/Sub Python SDK（套件名為 google-cloud-pubsub）
from google.cloud import pubsub_v1

flow_control = pubsub_v1.types.FlowControl(
    max_outstanding_messages=50,          # 每個 worker pod 最多 50 筆 in-flight
    max_outstanding_bytes=100 * 1024 * 1024,  # 100 MB in-flight 上限
)

subscriber.subscribe(
    subscription_path,
    callback=process_message,
    flow_control=flow_control,
)
```

**反壓傳播鏈**：當 worker 處理速度跟不上時，Pub/Sub client library 停止向 broker 發出 `ACK`，broker 判定 subscriber 「忙碌」後停止推送新訊息給該 pod，訊息留在 Pub/Sub（預設 7 天保留）。這形成一條完整的反壓傳播鏈：

```
LLM Quota 壓力
     ↓ worker 處理慢
Pub/Sub 停止推送
     ↓ 訊息累積在 broker
Token Bucket 持續排隊
     ↓ 新請求排入 Pub/Sub
API Gateway 感知 queue depth → 動態調低 burst headroom（可選）
```

**突發吸收數字**：假設平常流量 3K req/s，flash sale 觸發 15× 突發（45K req/s），持續 30 秒：
- Token Bucket 在前 5 秒吸收 ~25K 請求（Enterprise 桶容量 5K × 5 個 shard）
- 剩餘 ~1.1M 請求排入 Pub/Sub（45K × 30 - 25K = ~1.1M）
- Worker pool 以穩態速率 3K req/s 處理，約 367 秒（6 分鐘）清空佇列
- 整個過程系統不崩潰，Standard 租戶 floor rate 5 req/s 全程保持

### 2.7 KEDA ScaledObject 配置

KEDA（Kubernetes Event-Driven Autoscaling）根據 Pub/Sub subscription 的 backlog 數量自動調整 worker pod 數：

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: enterprise-worker-scaler
spec:
  scaleTargetRef:
    name: enterprise-worker
  minReplicaCount: 10       # 保持 floor rate 的最小資源
  maxReplicaCount: 100      # 不超過後端 LLM 配額上限
  cooldownPeriod: 60        # 縮容冷卻 60 秒，避免 scale thrashing
  triggers:
    - type: gcp-pubsub
      metadata:
        subscriptionName: enterprise-subscription
        value: "500"        # 每 500 筆 backlog 觸發新增 1 個 pod
```

**Scale-up 延遲**：KEDA 輪詢間隔預設 30 秒，scale-up 最快約 35–60 秒。這意味著突發流量的前 1 分鐘主要靠 Token Bucket 的桶容量 + 現有 worker 消化；60 秒後新 pod 就緒，處理速率提升。

### 2.8 優先佇列排序：緊急請求如何插隊

在 Fair-Share 架構中，即使是低等級租戶的「緊急請求」（如系統告警、付款確認）也需要能夠插隊到高優先位置。Pub/Sub 本身不支援訊息優先級，但可以用以下兩種方式模擬：

**方案 A：多 Topic 優先級分層**

```
┌─────────────────────────────────────────────────────┐
│  API Gateway — 依請求類型路由到不同 Topic            │
└────────────┬─────────────┬───────────────┬──────────┘
             │             │               │
             ▼             ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ critical-    │ │ enterprise-  │ │ standard-    │
    │ topic        │ │ topic        │ │ topic        │
    │（告警/付款）  │ │（一般請求）   │ │（批次任務）   │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
    Worker 先拉 critical，再拉 enterprise，最後拉 standard
    （透過 worker 輪詢順序實現優先）
```

**方案 B：單 Topic + 訊息屬性過濾**

Pub/Sub 支援在 subscription 層設定 filter，worker 可設定只訂閱帶有特定屬性的訊息：

```python
# 緊急 worker：只消費 priority=critical 的訊息
subscriber.create_subscription(
    name=critical_subscription_path,
    topic=topic_path,
    filter='attributes.priority = "critical"',
)

# 一般 worker：消費 priority != critical 的訊息
subscriber.create_subscription(
    name=normal_subscription_path,
    topic=topic_path,
    filter='attributes.priority != "critical"',
)
```

**選擇條件**：訊息量 < 10K/s → 方案 B（維運簡單，只需設 filter）；訊息量 > 10K/s 或需要嚴格 FIFO 保證 → 方案 A（獨立 topic，隔離更乾淨，可分別設定不同的 retain period 和 acknowledgement deadline）。

### 2.9 演算法選型：為什麼選 Token Bucket 不選其他

面試中常被追問「為什麼不用 Fixed Window 或 Sliding Window」，以下是完整的比較：

```
演算法              突發吸收   邊界效應   記憶體複雜度   Redis 實作複雜度
───────────────────────────────────────────────────────────────────────
Fixed Window        無         嚴重        O(1)           極低（INCR + EXPIRE）
Sliding Window Log  精確       無          O(N)，N=請求數 中（ZADD + ZRANGEBYSCORE）
Sliding Window Ctr  近似精確   弱          O(W)，W=窗格數 中（多個 INCR）
Token Bucket        有（C tokens）無        O(1)           中（HMSET Lua）
Leaky Bucket        無         無          O(1)           低（INCR 速率控制）
```

**Fixed Window 的邊界效應**：窗口重置瞬間，兩個相鄰窗口可以各打滿 quota，實際突發量達設定值的 2 倍。例如 100 req/min 的限制，在 00:59 到 01:01 的 2 秒內可以打出 200 個請求。對 AI 平台這是嚴重問題，因為 LLM 呼叫成本高，2× 突發可能直接觸發配額告警。

**Sliding Window Log 的記憶體問題**：需要儲存每一筆請求的時間戳，在 1K req/s 的租戶下，1 分鐘窗口需儲存 60K 個 timestamp，每筆 8 bytes = 480 KB/租戶。500 個租戶 = 240 MB Redis 記憶體，僅用於限速計數。

**Token Bucket 的適用條件翻轉**：
- 若業務要求輸出速率絕對平滑（如串流語音合成、即時字幕），改用 Leaky Bucket，犧牲突發吸收換取穩定輸出。
- 若業務需要精確的「過去 N 分鐘請求數」審計（合規需求），加上 Sliding Window Log 作為事後審計層，Token Bucket 依然用於即時限速。

### 2.10 容錯設計：Redis 掛了怎麼辦

Redis 是限速架構的單點，面試官一定會追問這個問題。有三種策略：

```
策略                  行為                   適用場景              風險
────────────────────────────────────────────────────────────────────────
Fail-Open（預設放行）  Redis 不可用時放行所有請求  消費者 API，SLA 優先    短暫超限，LLM 配額壓力
Fail-Closed（預設拒絕）Redis 不可用時拒絕所有請求  金融交易，嚴格合規      服務中斷，客戶體驗差
Local Fallback        切換到本地計數器，降級限速  多數 AI 平台            quota 精確度降低約 10×
```

**實際推薦**：使用 Redis Sentinel（3 節點，一主二從）或 Redis Cluster（6 節點，三主三從）的自動 failover（< 5 秒），加上本地 Fallback 作為降級保底。Sentinel 適合 < 50K ops/s 的中型場景，成本約 $150/月；Cluster 適合 > 100K ops/s，成本約 $800–2,000/月。本地 Fallback 的 quota 設為正式 quota 的 1/10（pod 數的倒數），保守放行，避免 LLM 配額爆炸。

```python
def check_rate_limit(tenant_id: str) -> bool:
    try:
        return redis_check_token_bucket(tenant_id)
    except redis.RedisError:
        # Redis 不可用：切換本地計數器，quota = 正式值 / replica_count
        logger.warning("Redis unavailable, switching to local fallback")
        return local_fallback_check(tenant_id, quota_divisor=10)
```

**監控指標**：`redis_circuit_open_total`（Redis 斷路次數）、`fallback_mode_duration_seconds`（降級持續時間）。若降級超過 30 秒，立即 PagerDuty alert。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**適用規模**：< 5K req/s，租戶數 < 50，後端單一 LLM endpoint

**做法**：
- API Gateway（Kong 或 Cloud Endpoints）內建 quota plugin，設定每租戶 QPS 上限。
- 超限直接回 429，配合客戶端 exponential backoff + jitter。
- 無獨立佇列；限速計數器用 Gateway 本身的 in-memory counter 或單一 Redis 實例。
- 無 Fair-Share；所有租戶共用相同的 Gateway worker thread pool。

**成本**：幾乎零額外基礎設施成本；1 個工程師，1 週可完成。

**缺點與觸發升級的條件**：
- 超限請求直接丟失，客戶看到大量 429，使用者體驗差。
- 多 Gateway pod 時，本地計數器使 quota 實際為設定值 × pod 數。
- 當租戶數 > 50 或單一大租戶佔用 > 80% 處理能力時，必須升至 Layer 2。

---

### Layer 2 — 生產就緒（Production-Ready）

**適用規模**：5K–50K req/s，租戶數 50–500，需要 SLA 保證

**新增元件**：
- **Redis Memorystore**（HA 模式，Primary + Replica）執行 Token Bucket Lua 腳本，分散式原子限速。
- **Cloud Pub/Sub** 作為緩衝佇列；每個租戶等級一個獨立 subscription，訊息保留 7 天。
- **KEDA** 根據 Pub/Sub backlog 自動擴縮各等級的 worker deployment。
- **FlowControlSettings** 限制每個 worker pod 的 in-flight 訊息數量，防止 OOM。
- **基本 Prometheus 指標**：throttle_rate_per_tenant、bucket_fill_level、queue_depth_per_tier。

**成本增量**：
- Redis HA（4 GB）：~$300/月
- Pub/Sub：~$0.04/百萬訊息，50K req/s 月流量約 $50–100/月
- KEDA operator：免費（開源）
- 合計約 $400–600/月額外成本

**新解決問題**：突發流量不丟失；租戶間工作池隔離；系統可從突發中自動恢復。

---

### Layer 3 — 企業級（Enterprise-Grade）

**適用規模**：50K+ req/s，租戶數 500+，SOC2 / GDPR 合規需求

**新增元件**：
- **Redis Cluster**（6 nodes，每個 node 16 GB）分片儲存租戶 bucket 狀態，叢集峰值支援 > 200K ops/s，單節點故障自動 failover < 5 秒。
- **動態 Floor Rate 調整**：根據租戶的即時付費狀態（從 Cloud Spanner 查詢）動態更新 Redis 中的 R 和 C 參數，支援臨時升級配額（如大客戶購買額外 burst pack）。
- **Cost Attribution**：每個請求的 LLM token 消耗寫入 BigQuery，按租戶、模型、時間維度聚合，用於精確帳單計算和配額超用警告。
- **Circuit Breaker**：若下游 Vertex AI endpoint P99 > 5 秒，自動 half-open；限制新請求進入 worker，防止 timeout 積壓耗盡 goroutine pool。
- **Multi-region Pub/Sub**：在多個區域部署獨立的 subscription + worker pool，透過 anycast 路由讓請求優先在最近的區域處理，降低跨區延遲。
- **完整告警策略**：floor rate 被觸碰時 PagerDuty alert；Redis 記憶體使用 > 80% 時提前擴容；KEDA scale-up 超過 2 分鐘未完成時 on-call 通知。

**成本增量**：
- Redis Cluster（6 × 16 GB）：~$2,000/月
- 監控 + 告警基礎設施：~$500/月
- Multi-region Pub/Sub：~$300/月
- 合計約 $2,800–3,500/月額外成本

**架構複雜度**：從 Layer 2 升至 Layer 3 約需 2 倍工程人力；需要專職 SRE 負責 Redis Cluster 的日常運維與容量規劃。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 用非原子操作（GET → 判斷 → DECR 三次呼叫）實作 Token Bucket | Race condition：高並發下超限放行，實際吞吐超出 quota 30–50%；審計日誌不符 | 必須用 Redis Lua 腳本或 EVALSHA 保證三步原子執行 |
| 所有租戶共用同一 Pub/Sub subscription 和 worker pool | Enterprise 突發時 Standard 請求排到隊尾，延遲爆炸；floor rate 無從保證 | 每個租戶等級獨立 subscription + 獨立 KEDA worker deployment |
| Token Bucket 容量 C 設為 0 或等於 R（無突發空間） | 正常業務的週期性小突發（整點 cron job、批次上傳）全部被 429；用戶體驗極差 | C 至少設為 R × 5（允許 5 秒突發吸收），避免誤殺合法流量 |
| 用 Redis EXPIRE（秒級精度）計時補充 | 補充速率最小粒度 1 秒，對 < 10 req/s 的 Free 租戶造成不公平截斷，整秒才補 1 token | 改用 PEXPIRE（毫秒精度）+ 桶內存毫秒 timestamp，補充連續平滑 |
| KEDA maxReplicaCount 設定過大，不設後端 quota 上限 | 突發時 worker 無限擴縮，下游 LLM 配額在幾分鐘內耗盡，產生大量 LLM API 503 錯誤 | maxReplicaCount = 後端能承受的最大並發數；搭配 LLM quota 監控 |
| 不設 FlowControlSettings，worker pod 無限接收 | Worker 接收速度遠超處理速度，in-flight 訊息積壓，記憶體 OOM，pod crash loop | 每 pod max_outstanding_messages ≤ 後端單連接最大並發；通常 20–100 |
| 限速計數器儲存在各 pod 本地記憶體 | 10 個 API Gateway pod 各自計數，實際吞吐為設定 quota 的 10 倍；quota 形同虛設 | 計數器必須在集中式 Redis；本地快取只做「明顯超限的瞬時預過濾」 |

---

## 四-B、系統效應：Before vs After

部署完整 Backpressure + Fair-Share 架構後，可量化的改善：

```
指標                         Before（無 Backpressure）    After（Token Bucket + Fair-Share）
──────────────────────────────────────────────────────────────────────────────────────────
15× 突發下 P99 延遲           > 30 秒（大量 timeout）      < 2 秒（Pub/Sub 緩衝 + KEDA 擴縮）
Standard 租戶 floor rate      0 req/s（被 Enterprise 餓死） 5 req/s（獨立 worker pool 保證）
突發流量遺失率                 40–60%（直接丟棄）           < 0.1%（7 天 Pub/Sub 保留）
LLM 配額超限告警次數/月        8–12 次                     0–1 次（Token Bucket 精確控制）
Rate-limit 層自身延遲增加      N/A                         + 0.5 ms P99（Redis Lua）
Redis 記憶體使用（500 租戶）   N/A                         ~50 MB（每桶 ~100 bytes × 500）
工程師 on-call 事件數/月       15+（系統崩潰 + 恢復）        2–3（監控告警，無崩潰）
```

**Redis 記憶體計算**：每個 Token Bucket 在 Redis 中以 Hash 儲存兩個欄位（tokens + last_refill），每個 Hash 約 64–100 bytes。500 租戶 × 100 bytes = 50 KB，遠低於任何 Redis 實例的記憶體下限。即使擴展到 10 萬個租戶，也只需 10 MB，Token Bucket 是極度記憶體友善的限速方案。

---

## 五、與其他核心主題的關聯

- **Part 11 非同步事件驅動管線**（`fde-interview-core-topic-11-async-event-driven-pipeline-zh`）：Backpressure 的佇列緩衝層（Pub/Sub）正是非同步管線的核心基礎設施；Fair-Share worker pool 即為事件驅動管線的消費者端，兩篇合起來構成完整的「非同步 + 限速」架構藍圖。
- **Part 3 狀態機 & DAG**（`fde-interview-core-topic-3-state-machine-dag-zh`）：多步驟 AI 工作流中，每個 DAG 節點的 LLM 呼叫都需過 Token Bucket；Backpressure 訊號可觸發 DAG 狀態機進入 `WAITING` 狀態而非直接失敗，讓工作流在配額恢復後自動重試。
- **Part 9 資料主權 & Sovereign AI**（`fde-interview-core-topic-9-data-residence-sovereign-ai-zh`）：不同地理區域的租戶需要獨立的 Redis Cluster 與 Pub/Sub topic；Backpressure 架構必須在跨區域部署時確保 bucket 狀態不跨境同步（避免 GDPR 問題）。
- **FDE Interview Guide Part 35–38（Production Engineering）**：限速層的 Prometheus 指標設計（throttle_rate、bucket_utilization）、KEDA ScaledObject 的 HPA 參數調優、Redis Cluster 的記憶體容量規劃，直接對應 Production Engineering 章節的 SRE 日常實踐。

---

## 六、面試一句話（Killer Phrase）

> *「Backpressure 是一個訊號機制，不是一個拒絕機制：當 GPU 配額或 LLM 速率上限被觸及時，正確的做法是讓上游放慢並將請求排入 Pub/Sub 緩衝，而不是直接丟棄。Token Bucket 用 Redis Lua 腳本在 0.5 ms 內原子地決定放行或排隊，比 DB-based 方案快 30 倍，在 50K req/s 規模下這個差距從 25 ms 放大到 750 ms，限速層本身就會成為瓶頸。Fair-Share 透過每個租戶等級獨立的 Pub/Sub subscription 加上 KEDA 自動擴縮的 worker pool，確保即使 Enterprise 客戶正在全速衝擊，Standard 租戶仍保證 5 req/s 的 floor rate；關鍵在於 floor rate 不是靠優先佇列「謙讓」來保證，而是靠完全獨立的資源池來隔離，這才是多租戶 SLA 設計的本質：優先不等於獨占。」*

---

**系列導航**
← [前一篇：Async Event-Driven Pipeline](/posts/fde-interview-core-topic-11-async-event-driven-pipeline-zh/) | [後一篇：Part 13](/posts/fde-interview-core-topic-13-zh/) →
