---
title: "Idempotency & State Recovery：分佈式 Agent 的精確一次斷點續傳"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入剖析如何透過 Checkpoint + Compare-And-Swap 保證分佈式 Agent 在 Pod OOM、搶佔或網路分割後，重啟時精確跳過已完成步驟，實現零重複副作用的斷點續傳。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Distributed", "Idempotency", "LangGraph"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Idempotency & State Recovery 是透過「執行前寫 Checkpoint、執行後 CAS 更新狀態、恢復時重播已完成步驟」的三段式協議，確保分佈式 Agent 在任意時間點中斷並重啟後，每個工具呼叫的副作用（扣款、通知、寫 DB）恰好執行一次，不多不少。**

---

## 一、為什麼面試官問這個

面試官真正在測試的是你對 **分佈式系統可靠性** 與 **副作用管理** 的成熟度。這題的背後問題是：「你知不知道 Agent 不是函數——它的執行跨越多個 Pod、多個時間視窗，任何一步都可能在已產生副作用之後失敗？」

- **測試點一：副作用的不可逆性。** 能否清楚區分「可重試的讀操作」與「不可重試的寫操作（發信、扣款、呼叫第三方 API）」，並說明為何後者必須有去重機制。面試官想知道你是否理解「at-least-once delivery」與「exactly-once semantics」的本質差異：前者是訊息系統的保證，後者是應用層必須自己實現的語意。

- **測試點二：一致性模型的選擇。** 能否說明為何 Checkpoint 需要強一致性（Cloud Spanner external consistency）而非最終一致性（Firestore default mode），以及這個選擇的 latency 代價（~10ms vs ~1ms）。最終一致性在此場景下會造成新 Worker 讀到舊快照，誤判步驟未完成，重複執行已完成的工具。

- **測試點三：恢復路徑的完整性。** 能否說明 `StateGraph.update_state()` 如何注入已完成步驟的輸出、跳過重新執行，並在 split-brain 情境下靠 Compare-And-Swap 避免雙 Worker 各自推進狀態。

**弱答案長相：** 「重試的時候我們就再跑一次，加個 try-catch 就好。」沒有提到去重 key、沒有提到 Checkpoint 持久化、沒有說明如何判斷哪些步驟已完成、也沒有提到下游服務如何識別重複呼叫。這個答案在面試官眼中等同於「不懂分佈式」。

**強答案長相：** 從「寫 pending → 執行 → 寫 completed（CAS）」三段式出發，說明 CAS 防止 split-brain，Recovery 時透過 `StateGraph.update_state()` 重播 StateGraph，最後給出具體數字：Spanner 寫入 ~10ms、恢復時間 < 100ms、重複通知率 0.03%（99.97% 的 Pod 失敗可被正確恢復）。

---

## 二、核心原理與技術深度

### 問題根源：Agent 執行的「原子性幻覺」

傳統函數呼叫有一個隱性假設：函數要麼全部執行完、要麼完全沒執行。這在單機同步執行中成立，但在分佈式 Agent 中完全不成立。

```
傳統函數呼叫（原子幻覺）：
┌───────────────────────────────────┐
│  f(x) → side_effect + result     │  失敗 → stack unwind，沒有部分狀態
└───────────────────────────────────┘

分佈式 Agent 執行（非原子，跨網路邊界）：

  Step 1        Step 2        Step 3        Step 4
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│ Tool A   │─▶│ Tool B   │─▶│ Tool C   │─▶│ Notification │
│ 扣款     │  │ 寫訂單DB │  │ 呼叫物流 │  │ 發確認信     │
│ ✓ 完成   │  │ ✓ 完成   │  │ ✓ 完成   │  │ ← Pod 在此   │
└──────────┘  └──────────┘  └──────────┘    OOM 崩潰     │
                                                           │
                              ← 物流 API 已呼叫，但系統     │
                                 不知道它完成了             │
                              ← 重啟後：重跑 Tool C？      │
                                 → 雙重呼叫物流 = 兩筆出貨單 │
```

這就是 **「部分執行問題」（Partial Execution Problem）**：Pod 在工具 C 完成後、POST-WRITE 狀態更新前崩潰，重啟後系統無從得知工具 C 是否已產生副作用。

**問題的三個維度：**

1. **可見性（Visibility）**：新 Worker 不知道舊 Worker 走到哪一步。沒有持久化 Checkpoint，新 Worker 只能從頭執行。
2. **冪等性（Idempotency）**：重跑已完成的工具是否安全？扣款、發信通常不安全；純查詢通常安全。必須針對每個工具逐一分析。
3. **一致性（Consistency）**：多個 Worker 同時恢復時，誰有權推進狀態？沒有協調機制會導致 split-brain，兩個 Worker 各自執行同一步驟，重複產生副作用。

**「恰好一次」（Exactly-Once）的語意邊界：**

「恰好一次」並不是說工具只被呼叫一次，而是說工具的 **有效副作用** 恰好發生一次。實現方式是允許多次呼叫，但每次呼叫攜帶相同的 `idempotency_key`，下游服務偵測到相同 key 後回傳已快取的結果而不執行。因此「恰好一次」是 **呼叫方（Checkpoint 協議）** 與 **被呼叫方（idempotency_key 去重）** 的聯合責任，缺一不可。

---

### Checkpoint 三段式協議的完整機制

```
┌──────────────────────────────────────────────────────────────┐
│  STEP N 的完整執行協議                                         │
│                                                               │
│  ① PRE-WRITE（強一致寫入）                                     │
│     Spanner.insert({                                          │
│       user_id:    "u-8821",                                   │
│       step_id:    "step-003",                                 │
│       version_id: 5,          ← 樂觀鎖版本號（單調遞增整數）   │
│       tool_name:  "call_logistics_api",                       │
│       inputs:     {order_id: "ORD-441"},                      │
│       status:     "pending",                                  │
│       created_at: TrueTime.now()                              │
│     })                                                        │
│     → 若此步驟失敗（Spanner 不可用）：工具不執行，安全重試       │
│                                                               │
│  ② EXECUTE（工具呼叫，攜帶 idempotency_key）                   │
│     idempotency_key = sha256("u-8821:step-003:v5")           │
│     result = logistics_api.call(                              │
│       inputs, idempotency_key=idempotency_key                 │
│     )                                                         │
│     ← 若此步驟後 Pod 崩潰：工具已執行，副作用已產生             │
│       重啟後重跑此步驟時，物流 API 憑 idempotency_key 去重     │
│                                                               │
│  ③ POST-WRITE（CAS 條件寫入）                                  │
│     Spanner.update(                                           │
│       WHERE user_id="u-8821" AND step_id="step-003"          │
│             AND version_id = 5,    ← CAS 條件                │
│       SET   status="completed",                               │
│             output=result,                                    │
│             version_id=6,                                     │
│             completed_at=TrueTime.now()                       │
│     )                                                         │
│     → CAS 失敗（version_id 不符）：另一個 Worker 已寫入        │
│       → 讀最新快照，確認 status="completed"，繼續下一步        │
└──────────────────────────────────────────────────────────────┘
```

### Cloud Spanner External Consistency 的關鍵作用

Cloud Spanner 使用 **TrueTime API** 提供 **external consistency**——這是比 linearizability 更強的保證：任何在事務 T1 提交後啟動的事務 T2，其讀取一定能看到 T1 的寫入，即使 T2 在不同區域執行。

```
為什麼 external consistency 在跨 Pod 恢復中至關重要：

時序：
t=0ms: Worker A 在 us-central1 寫 completed（step-003）
t=5ms: Worker A 崩潰
t=8ms: Worker B（在 us-east1）啟動，讀取 step-003 的狀態

使用最終一致性（Firestore default）：
  Worker B 可能讀到舊快照（status="pending"）← 觀察延遲 50–200ms
  Worker B 重跑 step-003 → 雙重副作用

使用 Cloud Spanner external consistency：
  Worker B 的讀取 timestamp > Worker A 的提交 timestamp
  → 必然看到 status="completed"
  → 跳過 step-003，繼續 step-004
  Write latency：~10ms（single-region），~40ms（multi-region nam6）
```

### Compare-And-Swap 防止 Split-Brain

Split-brain 是分佈式系統中最危險的情境：舊 Worker 未完全死亡（網路抖動恢復），與新 Worker 同時持有執行權。

```
Split-Brain 時序：
t=0:   Worker A 持有 step-003 的執行權，網路抖動 30 秒
t=5:   Pub/Sub ACK 超時，訊息重新投遞
t=10:  Worker B 接收訊息，讀 Spanner：step-003 status="pending"
t=15:  Worker B 開始執行 step-003 的工具
t=28:  Worker B 嘗試 POST-WRITE：version_id=5 → 成功（v→6）
t=30:  Worker A 網路恢復，也嘗試 POST-WRITE：version_id=5 → 失敗！

CAS 失敗處理（Worker A）：
  1. 讀最新 Spanner 快照
  2. 看到 step-003 status="completed"（由 Worker B 寫入）
  3. 靜默退出此 step，不產生任何副作用
  4. 若 Worker A 的工具呼叫已成功：物流 API 憑 idempotency_key 去重
```

### Dead Letter Topic 的觸發條件與處理流程

```
正常恢復路徑：
Pub/Sub 投遞 → Worker 失敗 → Pub/Sub 重投遞（指數退避：1s→2s→4s→8s→16s）
                                                              ↑ 5 次後
                                                     Dead Letter Topic
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                         PagerDuty     Slack Alert      BigQuery Log
                                         on-call 告警   #prod-incidents  (for audit)
                                              │
                                              ▼
                                     SRE 人工介入：
                                     1. 檢視最後 Checkpoint 快照
                                     2. 確認工具是否已產生副作用
                                     3. 手動標記 completed 或 rollback
                                     SLA：DLT 訊息 30 分鐘內必須人工處理
```

### Idempotency Key 的設計要點

`idempotency_key` 是讓下游服務去重的核心機制，其設計有幾個關鍵原則：

```
idempotency_key 的組成：
sha256( user_id + ":" + step_id + ":" + version_id )
  └─ user_id：確保不同用戶的同一步驟不衝突
  └─ step_id：確保同一用戶的不同步驟不衝突
  └─ version_id：確保重試（version++ 後）與原始呼叫不衝突

範例：
  user_id  = "u-8821"
  step_id  = "step-003"
  version_id = 5
  key = sha256("u-8821:step-003:5") = "a3f9c2..."

重試時（版本遞增）：
  version_id = 6  ← CAS 寫入後 version 變成 6
  key = sha256("u-8821:step-003:6") = "d71e4b..."  ← 不同 key，新的呼叫
```

**為什麼 version_id 要納入 key？**

若只用 `user_id + step_id`，當某個步驟在 pending 狀態下被重跑（例如 POST-WRITE 失敗，系統決定整個步驟重新執行），重跑的呼叫會攜帶與原始呼叫相同的 key，讓下游誤判為重複呼叫而去重 → 實際上是兩次語意不同的呼叫（一次成功、一次因為 POST-WRITE 失敗需要確認）。納入 `version_id` 後，每次嘗試都有唯一 key，下游去重語意精確。

**下游服務不支援 idempotency_key 時的降級策略：**

```
┌─────────────────────────────────────────────────────────────┐
│  工具類型           是否支援去重      降級策略                │
│                                                             │
│  Stripe / Twilio   ✓ 原生支援         直接傳 idempotency_key │
│  REST API（自建）   ✓ 需自行實作       在 Header 傳 X-Idempotency-Key │
│  資料庫寫入         ✓ UNIQUE 約束      ON CONFLICT DO NOTHING │
│  Email（SendGrid）  △ 部分支援         48 小時內相同 key 去重  │
│  第三方無去重支援    ✗ 不支援           在 Spanner 維護「已呼叫清單」│
│                                        呼叫前先查清單，已在清單 → 跳過 │
└─────────────────────────────────────────────────────────────┘
```

對於完全不支援去重的第三方 API，解法是在 Spanner 維護一張 `external_calls` 表（call_id = idempotency_key, status, response），工具呼叫前先 INSERT OR IGNORE，若 INSERT 成功才真正呼叫 API，否則直接返回已快取的 response。

---

**具體數字一覽：**

| 指標 | 數值 | 備註 |
|------|------|------|
| Spanner 單區寫入延遲（p50） | ~10ms | `us-central1` 單節點 |
| Spanner 單區讀取延遲（p50） | ~5ms | strong read，單點 |
| Spanner 多區寫入延遲（p50） | ~40ms | `nam6`：us-central1 + us-east1 + us-east4 |
| Checkpoint 快照讀取（N=10 步驟） | ~15ms | 含網路 RTT |
| `StateGraph.update_state()` 重播 | ~2ms/step | LangGraph 內部 state merge |
| 總恢復時間（10 步驟 Agent） | < 100ms | 讀快照 + 重播 state |
| 重複通知率（5 次 retry 後） | 0.03% | 99.97% 的 Pod 失敗可被正確恢復 |
| DLT 積壓 SLO | < 30 分鐘 | 超過即觸發 P1 事件 |
| Spanner read/write unit 成本 | $0.003 / $0.009 per million ops | 10 萬次/天執行 × 10 步驟 × 2 writes ≈ $0.18/天 |

---

## 三、三個實作層次

### StateGraph.update_state() 的恢復機制細節

LangGraph 的 `update_state()` 是 Recovery 路徑的核心。它允許外部程式碼在不重新執行節點的情況下，直接注入節點輸出到 graph 的 state 中：

```
Recovery 時的 StateGraph 操作：

1. 讀 Spanner 快照，取得 completed steps：
   [step-001: output_A, step-002: output_B, step-003: output_C]

2. 建立初始 state：
   state = AgentState(messages=original_input)

3. 逐步注入已完成輸出（不觸發節點執行）：
   graph.update_state(
       config={"configurable": {"thread_id": user_id}},
       values={"tool_output": output_A},
       as_node="tool_a"        ← 告訴 graph：tool_a 已執行完畢
   )
   graph.update_state(..., values={"tool_output": output_B}, as_node="tool_b")
   graph.update_state(..., values={"tool_output": output_C}, as_node="tool_c")

4. 從最後一個已完成節點的下一個節點繼續執行：
   graph.stream(None, config)  ← None 表示繼續（不重新注入 input）
   → 直接從 step-004（notification）開始執行
```

關鍵點：`update_state()` 使用 `as_node` 參數模擬節點執行完畢，LangGraph 的 state machine 因此正確計算出下一個應執行的節點，而不是從頭跑 graph。這讓 Recovery 邏輯與 Agent 的業務邏輯完全解耦。

---

### Layer 1 — 最小可行（Minimal）

**加了什麼：** 在 Agent 主迴圈加入記憶體內 `completed_steps: Dict[str, Any]`，工具執行前先查字典，完成後記錄輸出。搭配 `idempotency_key` 傳遞給外部 API。

```python
# 最簡單的記憶體去重
class InMemoryCheckpointer:
    def __init__(self):
        self.completed: dict[str, Any] = {}

    def is_completed(self, step_id: str) -> bool:
        return step_id in self.completed

    def get_output(self, step_id: str) -> Any:
        return self.completed[step_id]

    def mark_completed(self, step_id: str, output: Any):
        self.completed[step_id] = output

def run_tool_idempotent(checkpointer, step_id, tool_fn, inputs):
    if checkpointer.is_completed(step_id):
        return checkpointer.get_output(step_id)   # 跳過，直接返回快取
    result = tool_fn(inputs)
    checkpointer.mark_completed(step_id, result)
    return result
```

**解決的問題：** 同一個 Worker 進程內的邏輯重試（LangGraph 內部迴圈觸發的重複呼叫）。防止函數層面的重複執行。

**未解決的問題：** Pod 崩潰後記憶體清空，完全無法跨 Pod 恢復。無法處理 split-brain。下游 API 若不支援 `idempotency_key`，仍會重複執行。

**適用場景：** 單機開發環境、低流量 PoC（< 100 並發 Agent 執行）、工具全部為讀操作或本身已冪等的場景。

**成本/複雜度：** 零基礎設施成本，0.5 天實作。

---

### Layer 2 — 生產就緒（Production-Ready）

**加了什麼：**

1. **Checkpoint 持久化至 Cloud Spanner**：`status=pending/completed/failed`，強一致性讀寫。
2. **Compare-And-Swap 條件寫入**：`WHERE version_id = expected`，防止 split-brain 雙寫。
3. **`idempotency_key` 傳遞給所有外部 API**：`sha256(user_id + step_id + version_id)`。
4. **Pub/Sub + Dead Letter Topic**：失敗 5 次後送 DLT，觸發 PagerDuty。
5. **基本恢復邏輯**：新 Worker 啟動時讀 Spanner 最新快照，跳過已完成步驟。

```
請求流（正常路徑）：
                    ┌────────────────────────────────────┐
Client ────────────▶│ Pub/Sub Topic                      │
                    └────────────────┬───────────────────┘
                                     │ at-least-once delivery
                                     ▼
                    ┌────────────────────────────────────┐
                    │ Worker Pod（GKE Autopilot）         │
                    │                                    │
                    │  1. 讀 Spanner：找已完成步驟         │
                    │  2. 重播 StateGraph（skip done）    │
                    │  3. 執行下一個 pending 工具          │
                    │     PRE-WRITE → EXECUTE → CAS      │
                    └────────────────┬───────────────────┘
                                     │
                    ┌────────────────▼───────────────────┐
                    │ Cloud Spanner（single-region）      │
                    │  checkpoints 表                    │
                    │  user_id | step_id | version_id    │
                    │  status  | inputs  | output        │
                    └────────────────────────────────────┘
```

**解決的問題：** Pod OOM、GKE 節點搶佔、節點重啟後的跨 Pod 恢復。Split-brain 情境下的 CAS 防護。外部 API 重複呼叫（透過 idempotency_key）。

**未解決的問題：** 單區域 Spanner 在 GCP 單區域宕機時失去可用性（約每年 0–1 次，99.99% uptime SLA）。沒有 Checkpoint 清理機制（舊快照累積，月底儲存成本攀升）。缺乏 per-step 的可觀測性（無法快速定位哪個步驟卡住）。

**成本/複雜度：**
- Cloud Spanner single-region，1 node：~$0.90/node-hour ≈ $648/月
- 儲存：$0.30/GB/月（假設 10 萬次執行，每次 10 步驟 × 1KB = 1GB → $0.30/月）
- 工程投入：1–2 週（含單元測試與恢復測試）
- 適合流量：1,000–50,000 日活 Agent 執行

---

### Layer 3 — 企業級（Enterprise-Grade）

**加了什麼：**

1. **Cloud Spanner multi-region 配置（`nam6`）**：三個副本跨區域，TrueTime external consistency，單區域故障不影響可用性。
2. **LangGraph `BaseCheckpointSaver` 整合**：實作 `AsyncSpannerSaver`，每個 LangGraph node 前後自動寫 Checkpoint，不需手動呼叫三段式協議。
3. **Checkpoint TTL 自動清理**：completed 超過 30 天自動歸檔至 BigQuery，從 Spanner 刪除，降低儲存成本。
4. **細粒度可觀測性（Cloud Monitoring）**：每個 `step_id` 的 recovery_rate、dup_execution_rate、dlt_backlog、p99_recovery_latency。
5. **Checkpoint 版本壓縮**：只保留每個 `user_id` 最新的 completed snapshot 在 Spanner，完整歷史在 BigQuery。

```
企業級架構全景：

┌─────────────────────────────────────────────────────────────────┐
│  LangGraph StateGraph（with AsyncSpannerSaver）                  │
│                                                                  │
│  graph.compile(checkpointer=AsyncSpannerSaver(                   │
│      spanner_client,                                            │
│      database="agent-checkpoints",                              │
│      table="checkpoints",                                        │
│      ttl_days=30                                                 │
│  ))                                                              │
│                                                                  │
│  每個 node 執行前後，自動寫 Spanner checkpoint                    │
│  Recovery 時自動從最新 checkpoint 重播 state                      │
└────────────────────────┬────────────────────────────────────────┘
                         │ CAS write（~40ms, multi-region）
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cloud Spanner Multi-Region（nam6）                              │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  us-central1    │  │  us-east1       │  │  us-east4       │  │
│  │  (leader)       │  │  (replica)      │  │  (witness)      │  │
│  │  Paxos quorum   │◀─▶│  Paxos quorum  │◀─▶│  Paxos quorum  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  TrueTime → 全域排序 → 任一節點失效後仍可強一致性讀寫              │
│  SLA：99.999%（five-nines）                                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ TTL 清理（30 天）
                               ▼
                    ┌─────────────────────┐
                    │  BigQuery           │
                    │  checkpoint_archive  │  完整稽核日誌
                    │  （cold storage）   │  用於合規 / 事後分析
                    └─────────────────────┘
```

**解決的問題：** 區域級故障（GCP 單區宕機）下的強一致性保證。儲存成本膨脹（TTL 清理）。LangGraph 整合複雜度（`BaseCheckpointSaver` 介面自動化三段式）。可觀測性缺口（per-step 指標）。

**成本/複雜度：**
- Cloud Spanner multi-region（`nam6`）：最少 3 nodes → ~$9/node-hour × 3 ≈ $19,440/月
- 適用場景：金融、醫療、政府——有強監管要求（SOC2、HIPAA）或 SLA ≥ 99.99% 的場景
- 工程投入：4–8 週（含 LangGraph 整合、壓力測試、chaos engineering 驗證）

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 只做記憶體去重，不寫持久化 Checkpoint | Pod 崩潰後記憶體清空，所有步驟重跑，扣款/發信重複執行 | 每個 step 在 Spanner 寫 pending/completed，強一致性持久化 |
| Checkpoint 使用最終一致性儲存（Firestore default） | 新 Worker 可能讀到 50–200ms 前的舊快照，誤判步驟未完成，重複執行 | Cloud Spanner strong read，或 Firestore `consistency=STRONG`（僅 Datastore 模式支援） |
| 忘記傳 `idempotency_key` 給外部 API | 第三方 API 無法去重：雙扣款、雙發信、雙出貨單 | 每個工具呼叫攜帶 `sha256(user_id + step_id + version_id)` 作為 idempotency key |
| POST-WRITE CAS 失敗時視為工具執行失敗並重試 | 工具實際已完成，重試產生重複副作用；CAS 失敗通常是 split-brain，不是工具問題 | CAS 失敗 → 重新讀 Spanner 快照；若 status 已是 completed 則靜默跳過 |
| `version_id` 使用時間戳（毫秒）而非遞增整數 | 時鐘偏移（clock skew）導致同一 version_id 被兩個 Worker 使用，CAS 失效 | version_id 用單調遞增整數（應用層計數器或 Spanner sequence），絕不用時間戳 |
| DLT 無人監控，無告警規則 | 無聲失敗積壓，用戶 Agent 永遠卡住；問題可能數小時後才被發現 | DLT 積壓 > 0 立即觸發 PagerDuty；設 SLO：DLT 訊息 30 分鐘內必須人工處理完畢 |
| Checkpoint 永不清理，無 TTL | Spanner 儲存成本每月線性成長；單一高頻用戶可累積萬筆舊快照，讀取變慢 | completed 快照保留 30 天後歸檔至 BigQuery，從 Spanner 刪除；設 Cloud Monitoring 告警：Spanner 儲存 > 50GB |

---

## 五、與其他核心主題的關聯

- **Part 11（Async Event-Driven Pipeline）**：Pub/Sub 的 at-least-once delivery 是 State Recovery 的觸發機制——正是因為 Pub/Sub 會在 ACK 超時後重複投遞，才需要 Checkpoint 去重。若改為 exactly-once Pub/Sub（Kafka 語意），仍需 Checkpoint，因為 Worker 本身可能崩潰，與訊息系統的保證正交。兩者是不同層次的保證，必須同時存在。

- **Part 10（CMEK / BYOK）**：Checkpoint 中可能包含敏感資料（inputs 欄位含用戶 PII、訂單金額）。Cloud Spanner Checkpoint 表應啟用 CMEK，確保靜態資料加密符合 GDPR / HIPAA 要求；同時需要 Cloud KMS key rotation 政策，避免長期 Checkpoint 使用過期金鑰。

- **Part 1（Context Management）**：LangGraph `StateGraph` 的 `state` 物件既是 Context Window 的載體，也是 Checkpoint 的主體。理解 state 的序列化格式（預設 JSON，可換 protobuf 節省 30–60% 空間）直接影響 Spanner 的儲存成本與寫入延遲。State 過大時（> 100KB），Checkpoint 本身會成為寫入瓶頸。

- **fde-interview-guide Part 35–38**（生產工程落地）：Checkpoint 的 write latency（single-region ~10ms，multi-region ~40ms）會疊加到每個 tool call 上，對高頻 Agent（每秒 100+ tool calls）不可忽略。生產環境需將此納入 SLO 延遲預算計算，並考慮 Spanner 的 read/write unit 成本（10 萬次執行/天 × 10 步驟 × 2 writes ≈ 約 $0.18/天）。

**快速判斷框架：你需要哪個層次？**

```
你的 Agent 有對外副作用（扣款/發信/呼叫第三方 API）？
  └─ 否 → 純讀操作，記憶體去重即可（Layer 1）
  └─ 是 ↓

Pod 可能被 OOM / 搶佔 / 節點重啟？（GKE 幾乎必然）
  └─ 否（Lambda，執行時間 < 15 分鐘）→ Layer 1 + idempotency_key
  └─ 是 ↓

SLA 要求？
  ├─ 99.9% → Layer 2（Spanner single-region）
  ├─ 99.99% → Layer 2 + multi-AZ Spanner
  └─ 99.999% / 金融醫療 → Layer 3（Spanner multi-region nam6）

日活 Agent 執行量？
  ├─ < 10K → Layer 2 即可，Spanner 1 node
  ├─ 10K–100K → Layer 2，監控 Spanner CPU < 65%
  └─ > 100K → Layer 3，考慮 Checkpoint 壓縮與 TTL 清理
```

---

## 六、面試一句話（Killer Phrase）

> *「分佈式 Agent 最容易被忽略的問題是『部分執行』——Pod 可能在工具已產生副作用之後崩潰，導致重啟時無法判斷該步驟是否已完成。我的解法是三段式 Checkpoint 協議：執行前寫 pending 到 Cloud Spanner，執行後用 Compare-And-Swap 更新 completed；CAS 的 version_id 條件寫入同時解決 split-brain 問題，防止兩個 Worker 各自推進狀態。恢復時，新 Worker 讀最新快照，透過 LangGraph 的 `StateGraph.update_state()` 注入已完成步驟的輸出，精確從中斷點續傳。Spanner external consistency 保證跨區域故障下快照不會被錯過；5 次失敗後送 Dead Letter Topic 觸發人工介入。實測：Spanner 寫入 ~10ms，總恢復時間 < 100ms，99.97% 的 Pod 失敗可被無重複副作用地恢復。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-12-vector-search-retrieval-zh/) | [後一篇](/posts/fde-interview-core-topic-14-multi-agent-orchestration-zh/) →
