---
title: "FDE 面試指南 Part 43：跨國電商百萬級購物車 Agent 的分散式動態權限與狀態回復"
date: 2026-06-08T09:00:00+08:00
draft: false
description: "深度剖析黑五大促銷期間 200 萬在線用戶購物車 Agent 的異步架構設計：GKE Autopilot + KEDA + Cloud Pub/Sub 彈性伸縮、Cloud Spanner 強一致性 Checkpointer、LangGraph StateGraph 精確一次冪等恢復，以及多租戶隔離與流量整形策略。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "LangGraph", "GKE", "Pub/Sub", "Spanner", "Agent", "Distributed Systems", "Async Architecture"]
authors: ["yen"]
readTime: "28 min"
---

> 大多數工程師看到「購物車 Agent」，第一反應是加一個 HTTP 呼叫。
> 資深工程師看到的是：200 萬個並發狀態機、隨時會蒸發的 Pod、以及絕不允許重複扣款的業務紅線。
> 前者寫了一個能示範的 Demo，後者設計了一個能活過黑五的系統。
> 差距不在代碼行數，在於你把「失敗」當作例外還是當作設計輸入。

---

## 面試情境

> **面試官提問（Staff FDE L6 考題）：**
>
> 你的電商平台計劃在黑五期間為 **200 萬名在線用戶** 同時運行「自動購物車談判 Agent」。
> Agent 必須在背景異步監控庫存、與供應鏈 Agent 協商折扣，並在完成後推送通知。
> 已知 GKE 節點在大促期間會因搶佔（Preemption）和 OOM 隨機重啟，
> 請問你如何設計這個系統的異步架構？
> 當一個執行到第 5 輪反思循環（Reflection Loop）的 LangGraph Agent Pod 突然消失時，
> 你如何保證不遺失狀態、不重複通知、不重複扣款？

---

## 一、核心問題：為什麼同步 HTTP 在這裡是個死路

### 1.1 規模帶來的物理上限

200 萬在線用戶同時觸發購物車事件，假設每個 Agent 執行一次完整談判流程需要 **8–15 秒**（含多輪 LLM 推理、供應鏈 API 呼叫），同步模型意味著：

```
同步 HTTP 模型的致命算術
─────────────────────────────────────────────────────
並發請求量     ：2,000,000 個用戶 × 黑五流量因子 3× = 6M req
平均持續時間   ：~12s（5 輪反思 × 2.4s/輪）
所需最低 Worker：6,000,000 req / (1 Worker 每 12s) = 500,000 Workers
成本估算       ：500K pods × $0.024/hr (n2-standard-2) ≈ $12,000/小時
結論           ：系統在第一波流量就 OOM → 全場崩潰
```

### 1.2 Agent 狀態的特殊性

普通 HTTP 請求是無狀態的，失敗可以直接重試。但 LangGraph Agent 攜帶：

- **訊息歷史（Message History）**：已累積的 LLM 對話紀錄，重試代表重新呼叫 LLM，浪費金錢
- **工具執行副作用（Side Effects）**：供應鏈 API 已被呼叫、優惠券已被鎖定
- **跨輪反思變數（Intermediate Variables）**：反思循環中的內部推理狀態

若不持久化這些狀態，Pod 死亡等於業務損失，而非技術故障。

### 1.3 業務紅線

| 場景 | 後果 | 嚴重等級 |
|------|------|----------|
| 重複發送 Push 通知 | 用戶體驗差，客訴飆升 | P2 |
| 重複鎖定優惠券庫存 | 供應商損失，合規風險 | P1 |
| 重複扣款 | 財務損失，法律責任 | P0 |
| 狀態完全遺失 | 用戶購物車空白，流失轉化 | P1 |

---

## 二、三個演進階段

### ╔══ Phase 1：POC / 用戶 < 10K ══╗

**目標**：在 2 週內驗證 Agent 談判邏輯的可行性，不需要生產級容錯。

```
Phase 1 架構（POC）

┌──────────────┐  HTTP POST   ┌───────────────────────────────┐
│  前端購物車   │─────────────▶│  FastAPI Gateway              │
│  (Next.js)   │              │  /cart/add                    │
└──────────────┘              └───────────┬───────────────────┘
                                          │ enqueue
                                          ▼
                              ┌───────────────────────────────┐
                              │  Redis List (簡單 Queue)       │
                              │  LPUSH cart_jobs               │
                              └───────────┬───────────────────┘
                                          │ BRPOP
                                          ▼
                              ┌───────────────────────────────┐
                              │  Celery Worker (單節點)        │
                              │  LangGraph Agent              │
                              │  MemorySaver (in-memory)      │
                              └───────────┬───────────────────┘
                                          │
                              ┌───────────┴───────────────────┐
                              │  Firebase Push Notification   │
                              │  Stripe API (扣款)             │
                              └───────────────────────────────┘
```

**Phase 1 特點：**
- **Checkpointer**：`MemorySaver`，狀態存在 Worker 記憶體中
- **Queue**：Redis List，單點、無持久化保證
- **Worker**：單節點 Celery，無水平擴展
- **成本**：~$50/月（1 台 n2-standard-4 VM）

**Phase 1 殘留問題：**
- Worker 重啟 → 所有進行中的 Agent 狀態全部遺失
- Redis 無持久化，重啟後 Queue 消失
- 無法承受 > 100 QPS 並發
- 缺乏多租戶隔離（所有用戶共用同一 Worker）

---

### ╔══ Phase 2：MVP / 10K–200K 用戶 ══╗

**目標**：引入持久化 Checkpointer 和 Kubernetes 水平擴展，支撐中等規模促銷。

```
Phase 2 架構（MVP）

┌──────────────┐            ┌───────────────────────────────────┐
│  前端購物車   │──Publish──▶│  Cloud Pub/Sub Topic              │
│              │            │  cart-agent-jobs                  │
└──────────────┘            └──────────────────┬────────────────┘
                                               │
                            ┌──────────────────▼────────────────┐
                            │  GKE Standard Cluster             │
                            │  ┌────────────────────────────┐   │
                            │  │  Cart Agent Worker Pods    │   │
                            │  │  (Deployment, 3–20 replicas│   │
                            │  │   手動 HPA by CPU)          │   │
                            │  │                            │   │
                            │  │  LangGraph Agent           │   │
                            │  │  + MongoDBSaver            │   │
                            │  └────────────┬───────────────┘   │
                            └───────────────│───────────────────┘
                                            │ read/write state
                                            ▼
                            ┌───────────────────────────────────┐
                            │  MongoDB Atlas (M10 Cluster)      │
                            │  db: cart_agent                   │
                            │  collection: checkpoints          │
                            │  index: { user_id: 1, ts: -1 }   │
                            └───────────────────────────────────┘
                                            │
                            ┌───────────────▼───────────────────┐
                            │  Firebase / APNs Push Service     │
                            └───────────────────────────────────┘
```

**Phase 2 新增元件（vs Phase 1）：**
- Cloud Pub/Sub 取代 Redis List，提供 at-least-once 保證與 7 天訊息保留
- `MongoDBSaver` 作為持久化 Checkpointer，Pod 死亡後狀態可恢復
- HPA（CPU-based）提供基礎水平擴展
- Dead Letter Topic 處理反覆失敗訊息

**Phase 2 成本 delta**：~$800/月（GKE 節點 + MongoDB Atlas M10 + Pub/Sub）

**Phase 2 殘留問題：**
- MongoDB 讀寫一致性依賴 `majority` write concern，延遲 ~15ms，節點跨區時更高
- HPA 基於 CPU，對 LLM 密集型 I/O 工作負載反應慢（scale-out lag ~2–3 分鐘）
- 無 `version_id` CAS 機制，存在雙 Worker 並發寫入同一 Checkpoint 的競態條件
- 黑五流量峰值（~200K 並發）時 MongoDB 連線池成為瓶頸

---

### ╔══ Phase 3：Scale / 200K–1M+ 用戶 ══╗

**目標**：企業級容錯、精確一次語義、毫秒級 Checkpoint 寫入、多租戶隔離。

```
Phase 3 架構（Enterprise Scale）

┌────────────────────────────────────────────────────────────────────┐
│  流量入口層                                                          │
│  ┌─────────────┐  Token Bucket  ┌─────────────────────────────┐    │
│  │  API Gateway │──限流 1K QPS──▶│  Priority Queue Router      │    │
│  │  (Cloud Run) │               │  VIP: HIGH / 一般: NORMAL    │    │
│  └─────────────┘               └──────────────┬──────────────┘    │
└──────────────────────────────────────────────│───────────────────┘
                                               │ Publish
                               ┌───────────────▼──────────────────────┐
                               │  Cloud Pub/Sub                       │
                               │  Topic: cart-agent-{high,normal}     │
                               │  Subscription: ack-deadline = 600s   │
                               │  Dead Letter: cart-agent-dlq         │
                               └───────────────┬──────────────────────┘
                                               │ Pull (Streaming)
                               ┌───────────────▼──────────────────────┐
                               │  GKE Autopilot Cluster               │
                               │  ┌──────────────────────────────┐    │
                               │  │  KEDA ScaledObject           │    │
                               │  │  trigger: pubsub queue depth │    │
                               │  │  min: 2 / max: 500 pods      │    │
                               │  └──────────┬───────────────────┘    │
                               │             │ scale                   │
                               │  ┌──────────▼───────────────────┐    │
                               │  │  Cart Agent Worker Pod       │    │
                               │  │  ┌────────────────────────┐  │    │
                               │  │  │  LangGraph StateGraph  │  │    │
                               │  │  │  + SpannerCheckpointer │  │    │
                               │  │  │  + version_id CAS      │  │    │
                               │  │  └─────────┬──────────────┘  │    │
                               │  └────────────│──────────────────┘    │
                               └───────────────│──────────────────────┘
                                               │ atomic write
                               ┌───────────────▼──────────────────────┐
                               │  Cloud Spanner (Regional, 3 nodes)   │
                               │  Table: agent_checkpoints            │
                               │  PK: (tenant_id, user_id, version_id)│
                               │  Strong Consistency TrueTime         │
                               └───────────────┬──────────────────────┘
                                               │ skip/resume signal
                               ┌───────────────▼──────────────────────┐
                               │  Idempotency Layer                   │
                               │  StateGraph.update_state()           │
                               │  skip already-executed tool nodes    │
                               └───────────────┬──────────────────────┘
                                               │
                         ┌─────────────────────┴──────────────────────┐
                         │                                             │
              ┌──────────▼──────────┐                   ┌────────────▼────────────┐
              │  Push Notification  │                   │  Stripe / Payment API   │
              │  Firebase / APNs    │                   │  Idempotency-Key header  │
              └─────────────────────┘                   └─────────────────────────┘
```

**Phase 3 新增元件（vs Phase 2）：**
- GKE **Autopilot** 取代 Standard，節點管理全自動，消除手動補丁和節點組配置
- **KEDA** 基於 Pub/Sub queue depth 觸發 scale，反應時間 < 30 秒
- **Cloud Spanner** 取代 MongoDB，提供 TrueTime 強一致性和 CAS 語義
- **Token Bucket + Priority Queue** 前置限流，VIP 用戶優先處理
- **Idempotency-Key** 注入所有下游 API 呼叫

**Phase 3 成本 delta**：~$8,000–12,000/月（黑五期間 burst 時 ~$2,000/天）

---

## 三、GKE Autopilot + KEDA 的事件驅動彈性伸縮

### 3.1 為什麼 KEDA 優於原生 HPA

原生 HPA 以 CPU/Memory 作為 scale 觸發器，對 LLM 工作負載有根本性缺陷：

```
LLM Agent Worker 的資源特性（反直覺）

CPU 利用率低時：Worker 可能正在等待 LLM API 回應（I/O bound）
CPU 利用率高時：Worker 可能在執行 Python 字串解析，業務其實已快結束

正確的 scale 信號：Cloud Pub/Sub 待處理訊息數量（undelivered message count）
```

KEDA ScaledObject 配置（簡化版）：

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: cart-agent-scaler
spec:
  scaleTargetRef:
    name: cart-agent-worker
  minReplicaCount: 2
  maxReplicaCount: 500
  cooldownPeriod: 120       # 防止 scale-in 過快導致 in-flight 任務遺失
  triggers:
  - type: gcp-pubsub
    metadata:
      subscriptionName: cart-agent-normal-sub
      value: "50"           # 每個 Pod 處理 50 條訊息時的目標佇列深度
      activationValue: "10" # 至少 10 條才 scale-out（防止空轉）
```

**關鍵參數說明：**
- `cooldownPeriod: 120`：確保 Pod 在 scale-in 前有足夠時間完成最後一批任務
- `value: 50`：GKE Autopilot 節點預熱約 45 秒，每 Pod 目標佇列深度需考慮這段 lag
- KEDA 觸發 → Pod 就緒的 end-to-end 延遲：Autopilot **< 90 秒**（Standard < 45 秒）

### 3.2 GKE Autopilot 搶佔（Preemption）的本質

GKE Autopilot 使用 Spot node pool 降低成本，搶佔（Preemption）是設計的一部分，不是 Bug：

```
搶佔事件時序
─────────────────────────────────────────────────────────
T+0s    GCP 基礎設施決定收回節點（30 秒預告）
T+0s    Kubelet 收到 SIGTERM，發送給所有 Pod
T+2s    Pod 的 preStop hook 執行（最多 30 秒窗口）
T+15s   Worker 完成當前 LLM 呼叫，flush Checkpoint 到 Spanner
T+30s   強制 SIGKILL，Pod 被終止
T+35s   Pub/Sub Ack Deadline（600s）倒計時繼續
T+580s  Ack Deadline 超時，訊息重新入隊（redelivery）
T+581s  新 Pod 拾取訊息，從 Spanner 讀取最後 Checkpoint，Resume
```

`preStop` hook 是關鍵：在 SIGTERM 到 SIGKILL 之間的 30 秒窗口內，Worker 必須：
1. 停止拉取新訊息（stop new pulls）
2. 等待當前 LLM 呼叫完成（或超時 abort）
3. 將 `StateSnapshot` 寫入 Spanner（< 10ms，Spanner 承諾 SLA）

---

## 四、Cloud Spanner Checkpointer 與精確一次語義

### 4.1 Checkpointer 的核心資料結構

```sql
-- Cloud Spanner DDL
CREATE TABLE agent_checkpoints (
  tenant_id       STRING(64)  NOT NULL,   -- 多租戶隔離的 Row Key 前綴
  user_id         STRING(128) NOT NULL,
  session_id      STRING(64)  NOT NULL,
  version_id      INT64       NOT NULL,   -- 單調遞增，每次 Tool 執行前 +1
  checkpoint_data JSON        NOT NULL,   -- StateSnapshot 完整序列化
  tool_node_name  STRING(128),            -- 當前執行到的 Tool 節點名稱
  tool_output_hash STRING(64),            -- 工具輸出的 SHA-256，用於冪等判斷
  created_at      TIMESTAMP   NOT NULL OPTIONS (allow_commit_timestamp=true),
  is_committed    BOOL        NOT NULL DEFAULT (FALSE), -- 原子性旗標
) PRIMARY KEY (tenant_id, user_id, session_id, version_id DESC);

-- 覆蓋索引：快速查詢某用戶最新已提交的 Checkpoint
CREATE INDEX idx_latest_committed
ON agent_checkpoints (tenant_id, user_id, is_committed)
STORING (version_id, tool_node_name);
```

**Row Key 設計的考量：**
- `tenant_id` 作為前綴：確保同一租戶的資料在同一 Spanner Split 上，避免跨 Split 的分佈式事務
- `version_id DESC`：最新 Checkpoint 在物理儲存上排在前面，範圍掃描成本低
- `is_committed`：區分「寫入中」和「已完成」的 Checkpoint，防止讀到半寫狀態

### 4.2 Write-Before-Execute 的原子性保證

每次 Tool 執行前後，Worker 執行以下事務：

```python
# Phase 3 Worker 核心邏輯（簡化版）
async def execute_agent_step(
    state: AgentState,
    tool_node: str,
    spanner_client: SpannerClient,
) -> AgentState:

    # Step 1: Write-Before-Execute（CAS 語義）
    new_version = state.version_id + 1
    with spanner_client.batch() as batch:
        batch.insert(
            table="agent_checkpoints",
            columns=["tenant_id", "user_id", "session_id",
                     "version_id", "checkpoint_data",
                     "tool_node_name", "is_committed",
                     "created_at"],
            values=[(
                state.tenant_id, state.user_id, state.session_id,
                new_version,
                serialize_state(state),   # JSON 序列化
                tool_node,
                False,                    # 尚未 committed
                spanner.COMMIT_TIMESTAMP,
            )]
        )
    # Spanner 在此 commit → TrueTime 保證全域可見

    # Step 2: 執行 Tool（可能有副作用）
    tool_output = await invoke_tool(tool_node, state)

    # Step 3: Write-After-Execute（標記 committed + 儲存輸出 hash）
    output_hash = sha256(serialize(tool_output))
    with spanner_client.batch() as batch:
        batch.update(
            table="agent_checkpoints",
            columns=["tenant_id", "user_id", "session_id",
                     "version_id", "is_committed", "tool_output_hash"],
            values=[(
                state.tenant_id, state.user_id, state.session_id,
                new_version, True, output_hash,
            )]
        )

    return apply_tool_output(state, tool_output)
```

### 4.3 新 Pod 的 Resume 邏輯

```python
# 新 Pod 接管後的恢復邏輯
async def resume_agent(
    user_id: str,
    tenant_id: str,
    session_id: str,
    graph: StateGraph,
    spanner_client: SpannerClient,
) -> None:

    # Step 1: 從 Spanner 讀取最後一個已 committed 的 Checkpoint
    results = spanner_client.execute_sql("""
        SELECT version_id, checkpoint_data, tool_node_name, tool_output_hash
        FROM agent_checkpoints
        WHERE tenant_id = @tenant_id
          AND user_id = @user_id
          AND session_id = @session_id
          AND is_committed = TRUE
        ORDER BY version_id DESC
        LIMIT 1
    """, params={"tenant_id": tenant_id, "user_id": user_id,
                 "session_id": session_id})

    if not results:
        # 全新 session，從頭開始
        await graph.ainvoke(initial_state)
        return

    last_checkpoint = results[0]
    state = deserialize_state(last_checkpoint["checkpoint_data"])

    # Step 2: 檢查是否有「寫入中但未 committed」的 Checkpoint
    # 若存在，說明 Tool 可能已執行但未記錄結果（需冪等重試）
    uncommitted = spanner_client.execute_sql("""
        SELECT version_id, tool_node_name
        FROM agent_checkpoints
        WHERE tenant_id = @tenant_id
          AND user_id = @user_id
          AND session_id = @session_id
          AND version_id > @last_version
          AND is_committed = FALSE
        LIMIT 1
    """, params={..., "last_version": last_checkpoint["version_id"]})

    if uncommitted:
        # 使用 idempotency-key 安全重試 Tool（下游 API 保證冪等）
        next_node = uncommitted[0]["tool_node_name"]
        graph.update_state(state, skip_nodes_before=next_node)
    else:
        # 從 last committed 節點的下一個節點繼續
        next_node = get_next_node(last_checkpoint["tool_node_name"])
        graph.update_state(state, resume_from=next_node)

    # Step 3: 繼續執行圖
    await graph.ainvoke(state)
```

### 4.4 Pub/Sub Ack Deadline 與 DLT 設計

```
Pub/Sub 訊息生命週期

┌───────────────────────────────────────────────────────────────┐
│  Producer publish message                                     │
│  Message ID: abc123                                           │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│  Subscription: cart-agent-normal-sub                          │
│  Ack Deadline: 600 seconds（足夠完成 5 輪反思 × 2min/輪）      │
│  Max Delivery Attempts: 5                                     │
└──────────────────────────────┬────────────────────────────────┘
                               │ Pull
                               ▼
                  ┌────────────────────────┐
                  │  Worker Pod A          │
                  │  執行 Agent...         │
                  │  (Pod 在 T+120s OOM)   │
                  └────────────────────────┘
                               │
                    Ack Deadline 超時 (T+600s)
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Worker Pod B (新)     │   ← Redelivery
                  │  讀取 Spanner Checkpoint│
                  │  從斷點 Resume         │
                  └────────────────────────┘
                               │
                  （若連續 5 次失敗）
                               ▼
┌───────────────────────────────────────────────────────────────┐
│  Dead Letter Topic: cart-agent-dlq                           │
│  訂閱者：DLQ Processor（告警 + 人工審查 + 補償事務）            │
└───────────────────────────────────────────────────────────────┘
```

**Ack Deadline 設定原則：**
- 設定為 Agent 最大預期執行時間的 **1.5 倍**
- 5 輪反思 × 平均 80s/輪 = 400s → Ack Deadline = 600s
- Worker 必須定期呼叫 `modifyAckDeadline()` 延長 Deadline（heartbeat 機制）

---

## 五、LangGraph StateGraph 的冪等 Skip 與 Resume

### 5.1 LangGraph 狀態圖的節點結構

```
購物車 Agent 的 LangGraph 狀態圖

┌─────────────────────────────────────────────────────────┐
│  StateGraph: CartNegotiationAgent                       │
│                                                         │
│  START ──▶ [inventory_check] ──▶ [supplier_negotiation] │
│                 │                        │              │
│                 │ (loop if stock < min)  │              │
│                 ▼                        ▼              │
│           [reflection_loop] ──▶ [discount_calculation] │
│                 │                        │              │
│                 │ (max 5 iterations)     │              │
│                 ▼                        ▼              │
│           [send_push_notification] ──▶ [payment_charge] │
│                                         │               │
│                                         ▼               │
│                                        END              │
└─────────────────────────────────────────────────────────┘

節點         工具副作用              冪等性設計
──────────────────────────────────────────────────────────
inventory_check     讀操作（無副作用）   天然冪等
supplier_negotiation 鎖定優惠券庫存     Idempotency-Key = session_id + version_id
reflection_loop     LLM 推理（有成本）  Skip if tool_output_hash exists
discount_calculation 計算（無副作用）   天然冪等
send_push_notification 寫 FCM          Idempotency-Key = user_id + session_id
payment_charge      Stripe 扣款        Idempotency-Key = order_id（全域唯一）
```

### 5.2 update_state() 的 Skip 機制原理

`StateGraph.update_state()` 允許外部注入狀態並覆寫圖的執行游標，這是實現 Resume 的關鍵 API：

```python
# 假設 Agent 在 discount_calculation 節點後崩潰
# Spanner 中最後 committed 的節點是 discount_calculation

# 恢復時：直接跳過已完成的節點
graph.update_state(
    config={"configurable": {"thread_id": session_id}},
    values={
        # 注入最後已知的完整狀態
        **deserialize_state(last_checkpoint),
        # 明確告知圖從 send_push_notification 開始繼續
        "__next__": ["send_push_notification"],
    },
    as_node="discount_calculation",  # 假裝是從這個節點的輸出回來的
)
# 之後調用 graph.ainvoke() 將從 send_push_notification 繼續
```

**為什麼這能保證不重複扣款：**

- `payment_charge` 節點只有在 `send_push_notification` 成功後才執行
- 每次呼叫 Stripe API 時帶上 `Idempotency-Key: order_{order_id}_{session_id}`
- Stripe 在 24 小時內對相同 key 的請求直接回傳上次的成功結果（不重複扣款）
- 即使 Resume 後再次觸達 `payment_charge`，也不會造成雙重扣款

---

## 六、多租戶隔離與流量整形

### 6.1 多租戶隔離策略

```
多租戶隔離層次

Layer 1 - Pub/Sub Topic 層
  topic: cart-agent-jobs-{tenant_id}  (Premium 租戶獨立 topic)
  topic: cart-agent-jobs-shared       (Standard 租戶共用 topic)

Layer 2 - Spanner Row Key 層
  PRIMARY KEY: (tenant_id, user_id, session_id, version_id DESC)
  確保不同租戶資料物理上位於不同 Spanner Split
  → 防止「熱」租戶的大量寫入影響其他租戶的讀取延遲

Layer 3 - GKE Namespace 層
  namespace: tenant-{tier}
  ResourceQuota: Premium 租戶可使用 max 200 pods
                 Standard 租戶共用 300 pods pool

Layer 4 - Application 層
  每個 Worker Pod 的 context 包含 tenant_id
  LLM 呼叫的 system prompt 根據租戶配置動態載入
  供應鏈 API 的認證 token 按租戶隔離（KMS 加密儲存）
```

### 6.2 Token Bucket 限流設計

```
Token Bucket 限流架構

┌──────────────┐   每個用戶 1 req/s    ┌─────────────────────────┐
│  API Gateway │──────────────────────▶│  Rate Limiter           │
│  (Cloud Run) │                       │  Redis Cluster          │
└──────────────┘                       │  INCR cart:{user_id}    │
                                       │  EXPIRE 1s              │
                                       └──────────┬──────────────┘
                                                  │
                                   ┌──────────────▼──────────────┐
                                   │  通過：publish to Pub/Sub   │
                                   │  拒絕：429 + Retry-After: 1 │
                                   └─────────────────────────────┘

Priority Queue 路由規則
───────────────────────────────────────────────────────────
用戶等級      訂閱名稱                    最大 Pod 數  Ack Timeout
VIP (>$1000)  cart-agent-high-sub         200         900s
Premium       cart-agent-normal-sub       300         600s
Standard      cart-agent-low-sub          500         300s
```

**黑五流量整形的實際效果（Phase 3 測試數據）：**
- 無限流：瞬間 6M req 打爆 Pub/Sub ingestion，訊息延遲 > 30 秒
- 有 Token Bucket：峰值被壓平至 2M req/min，Pub/Sub 延遲 < 1 秒
- Priority Queue 效果：VIP 用戶 p99 處理延遲 < 45 秒；Standard 用戶 p99 < 8 分鐘

---

## 七、供應鏈 Agent 協調與反射循環設計

### 7.1 多 Agent 協調架構

購物車 Agent 不是孤立運行的，它需要與供應鏈 Agent 動態協商折扣：

```
多 Agent 協調（事件驅動）

┌──────────────────────────────────────────────────────────────────┐
│  Cart Agent（用戶側）          │  Supply Chain Agent（供應商側）   │
│                                │                                  │
│  1. 發送 RFQ（詢價請求）        │  1. 接收 RFQ                    │
│     → Pub/Sub: rfq-requests    │     ← Pub/Sub: rfq-requests     │
│                                │  2. 查詢倉庫庫存 API             │
│  2. 等待報價（異步等待）         │  3. 計算可承受折扣               │
│     Long Poll / Pub/Sub        │  4. 回傳報價                    │
│     subscription               │     → Pub/Sub: rfq-responses    │
│                                │                                  │
│  3. 評估報價（Reflection）      │                                  │
│  4. 計數器出價 / 接受 / 拒絕    │                                  │
│     （最多 5 輪）              │                                  │
└──────────────────────────────────────────────────────────────────┘

最大談判輪次：5 輪（約 10 分鐘）
每輪 Pub/Sub round-trip：~30–120 秒（取決於供應商 API 延遲）
Ack Deadline 需覆蓋完整談判：600s（保守設計）
```

### 7.2 反射循環的中斷恢復

反射循環（Reflection Loop）是最容易在中途崩潰的環節，因為它可能持續 2–10 分鐘：

```python
# 反射循環節點（帶 Checkpoint）
async def reflection_loop_node(state: CartAgentState) -> CartAgentState:
    iteration = state.get("reflection_iteration", 0)
    max_iterations = 5

    if iteration >= max_iterations:
        # 已達上限，強制進入下一階段
        return {**state, "should_accept_offer": True}

    # 每輪反思前 Checkpoint
    # （由外層 Checkpointer 機制自動處理，節點粒度）

    # LLM 反思推理（最昂貴的步驟）
    reflection = await llm.ainvoke([
        SystemMessage(content=NEGOTIATION_REFLECTION_PROMPT),
        *state["messages"],
        HumanMessage(content=f"Round {iteration+1}: Evaluate current offer...")
    ])

    decision = parse_decision(reflection.content)

    return {
        **state,
        "reflection_iteration": iteration + 1,
        "messages": [*state["messages"], reflection],
        "current_decision": decision,
        # Checkpoint 此狀態 → version_id + 1
    }
```

**崩潰恢復場景：**
- 若在第 3 輪反思後崩潰：Spanner 有 version 3 的 Checkpoint
- 新 Pod Resume：從第 4 輪反思開始，不重跑前 3 輪（節省 LLM 呼叫成本）
- LLM 成本節省估算：每輪 ~$0.01（GPT-4o）× 200 萬用戶 × 平均 2.5 輪被節省 = **$50,000 節省/次黑五**

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|------------|--------------|----------------|
| **Cloud Spanner** vs **MongoDB Atlas** | TrueTime 強一致性，CAS 語義原生支援；跨區複製延遲 < 8ms；Row Key 設計消除熱點 | MongoDB `majority` write concern 跨區延遲 15–40ms；無原生 CAS，需應用層樂觀鎖；分片鍵設計不當易產生 chunk migration 卡頓 | 若 MAU < 50K 且無跨區需求：MongoDB Atlas M10 ($57/月) 已足夠，Spanner 基礎費用 $270/月起 |
| **Cloud Pub/Sub** vs **Redis Streams** | 7 天訊息保留，天然支援 Dead Letter Topic；全託管，無需管理 broker；Ack Deadline 可達 600s | Redis Streams 無原生 DLT；Redis Cluster 在高寫入下易產生 hot key；大促期間需手動擴展 Shard | 若訊息量 < 1K QPS 且延遲容忍 < 5s：Redis Streams 延遲更低（< 1ms vs ~5ms for Pub/Sub） |
| **GKE Autopilot** vs **GKE Standard** | 節點自動管理，無需維護 node pool；bin packing 更優，成本節省 20–30%；搶佔節點自動補充 | Standard 需手動配置 node pool、設定 taints/tolerations；節點安全補丁需手動觸發；管理複雜度高 | 若需要特定硬體（GPU A100）或自定義 kernel 參數：必須用 Standard Cluster |
| **KEDA (Pub/Sub 觸發)** vs **HPA (CPU 觸發)** | 直接反映業務積壓量；scale-out 決策基於真實工作量；支援 scale-to-zero（黑五後省錢） | HPA 對 I/O bound LLM 工作負載 CPU 信號失真；scale-out lag 2–3 分鐘；無法 scale-to-zero | 若工作負載是純計算密集（如圖像編碼）：HPA by CPU 更直接，不需要額外 KEDA 部署複雜度 |
| **LangGraph MongoDBSaver / SpannerCheckpointer** vs **自行實作 Checkpoint** | 原生整合 StateGraph API；`update_state()` / `get_state()` 無縫對接；社區維護，減少 Bug | 自行實作需處理序列化版本升級、並發寫入競態、Schema migration；維護成本高；易遺漏 edge case | 若 StateGraph 非常簡單（< 3 個節點，無 Loop）：直接 Redis Hash 儲存更輕量，無需引入 LangGraph Checkpointer 框架開銷 |
| **version_id CAS** vs **分佈式鎖（Redlock）** | Spanner 原生支援條件寫入，無需額外鎖服務；版本號可用於 Skip 判斷；無鎖超時問題 | Redlock 需 5 個 Redis 節點多數決；網路分區時可能同時產生兩個 Leader；釋放鎖失敗需 TTL 自動過期，期間資源被浪費 | 若需要真正的排他性跨服務臨界區（如資料庫 schema 遷移協調）：Redlock 或 Cloud Spanner 悲觀鎖更合適 |

---

## 九、Exactly-Once 語義的完整保證鏈

### 9.1 端到端 Exactly-Once 矩陣

```
精確一次（Exactly-Once）的保證鏈

操作                    保證機制                           最終語義
─────────────────────────────────────────────────────────────────────────
Pub/Sub 訊息消費     Ack-after-commit + Ack Deadline     At-Least-Once (Pub/Sub 本身)
Spanner 寫入         TrueTime + 單調 version_id          Exactly-Once (CAS)
LLM 呼叫             Skip if tool_output_hash exists     At-Most-Once（節省成本）
供應鏈 API           Idempotency-Key = session+version   Exactly-Once（冪等 API）
Push 通知            Idempotency-Key = user+session      Exactly-Once（FCM 去重）
Stripe 扣款          Idempotency-Key = order_id          Exactly-Once（Stripe 24h 去重）
─────────────────────────────────────────────────────────────────────────
整體系統語義：       所有有副作用操作 Exactly-Once，LLM 推理 At-Most-Once（優化成本）
```

### 9.2 競態條件：雙 Worker 問題

極端情況：Pub/Sub 因網路分區提前 Redeliver，兩個 Worker 同時處理同一訊息：

```
雙 Worker 競態（Worker A 緩慢，Worker B 搶先接管）

Worker A: 寫入 version=5 到 Spanner (is_committed=false)
Worker B: 同時嘗試寫入 version=5（相同 PK）
          → Spanner 第二個寫入失敗（PK 衝突，409 AlreadyExists）
          → Worker B 讀取現有 version=5，發現 is_committed=false
          → Worker B 等待 500ms 後重新檢查
Worker A: T+200ms 完成工具執行，更新 is_committed=true
Worker B: T+500ms 讀到 is_committed=true，跳過該節點，繼續 version=6
結果：只有一個 Worker 有效執行每個節點（Exactly-Once）
```

---

## 十、系統效應：大促前後的量化對比

| 指標 | Phase 1（POC）| Phase 2（MVP）| Phase 3（Scale）|
|------|--------------|--------------|----------------|
| **最大并發用戶數** | 500 | 50,000 | 2,000,000 |
| **Agent 啟動延遲 p99** | 200ms | 800ms | 1.2s（Pub/Sub 傳遞） |
| **狀態恢復延遲 p99** | N/A（無恢復）| 2,500ms（MongoDB 跨區）| 18ms（Spanner 本地讀）|
| **Pod 崩潰後任務遺失率** | 100% | < 5%（MongoDB eventual）| < 0.001%（Spanner strong）|
| **重複通知率** | ~8%（無冪等）| ~0.5% | < 0.001% |
| **重複扣款率** | ~2%（無冪等）| ~0.1% | 0%（Idempotency-Key）|
| **Scale-out 延遲** | N/A | 3–5 分鐘（HPA CPU）| < 45 秒（KEDA Pub/Sub）|
| **黑五峰值成本** | $50/月 | $2,400/天（手動擴展）| $1,800/天（Autopilot 優化）|
| **DLQ 訊息比例** | N/A | ~3% | < 0.5% |
| **LLM 冗余呼叫節省** | 0% | ~15% | **~60%**（Checkpoint Skip）|
| **Ack Timeout 導致的重試** | N/A | ~12% | ~0.8% |
| **工程師 On-call 告警數/黑五** | ~300 | ~80 | < 15 |

---

## 十一、面試答題要點

> *「面對 200 萬并發購物車 Agent，我的核心設計圍繞三個演進階段展開。Phase 1 用 Celery + Redis + LangGraph MemorySaver 快速驗證談判邏輯，但無狀態持久化，適合 < 500 并發的 POC；Phase 2 引入 Cloud Pub/Sub 替代 Redis Queue 獲得 at-least-once 保證，並以 MongoDBSaver 作為 Checkpointer，支撐 5 萬用戶但 MongoDB 跨區 15ms 寫延遲在高并發下仍是瓶頸；Phase 3 的核心突破是以 Cloud Spanner 的 TrueTime 強一致性替代 MongoDB，搭配單調遞增的 version_id 實現 CAS 語義，確保雙 Worker 並發寫入時只有一個成功，徹底解決 Exactly-Once 問題。當 Pod 因搶佔蒸發後，Pub/Sub Ack Deadline（600s）超時觸發 Redelivery，新 Worker 在 18ms 內從 Spanner 讀出最後已 committed 的 StateSnapshot，透過 StateGraph.update_state() 將執行游標跳至正確節點 Resume，已完成的工具節點透過 tool_output_hash 比對直接 Skip，LLM 重複呼叫節省高達 60%；最終 KEDA 基於 Pub/Sub 佇列深度觸發 scale-out，將反應時間從 HPA 的 3 分鐘壓縮至 45 秒，重複扣款率從 2% 降至絕對零。」*

---

## 關鍵架構決策速查表

| 場景 | 選擇 | 理由 |
|------|------|------|
| Agent 狀態持久化（> 200K 用戶）| Cloud Spanner | TrueTime + CAS，18ms 讀取 |
| 任務佇列（大規模）| Cloud Pub/Sub | 7 天保留 + DLT + 600s Ack |
| 彈性伸縮觸發器 | KEDA + Pub/Sub trigger | 直接反映業務積壓，< 45s scale-out |
| Pod 搶佔保護 | preStop hook + Checkpoint flush | 30s 視窗內完成狀態持久化 |
| 精確一次扣款 | Stripe Idempotency-Key | 24h 去重，100% 安全 |
| 多租戶隔離 | Spanner Row Key 前綴 | 防熱點 + 資料隔離 |

---

**系列導航**

← [Part 42：跨國電商多語言向量搜尋與個性化排序架構](/posts/fde-interview-guide-part42-multilingual-vector-search-zh/) | [Part 44：大規模即時推薦系統的特徵工程與線上學習架構](/posts/fde-interview-guide-part44-realtime-recommendation-zh/) →
