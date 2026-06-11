---
title: "FDE 面試指南 Part 48：高可靠性 Agent Graph 的多重工具 Fallback 與自我修復機制"
date: 2026-06-08T09:00:00+08:00
draft: false
weight: 48
description: "深入解析如何在 LangGraph 中設計 Compiler-Validator Pattern，透過 Pydantic 強型別校驗、Critic Agent 反思重寫、Circuit Breaker 與 Human-in-the-loop，打造能自我修復的高可靠性供應鏈 Agent 架構。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "FDE", "LangGraph", "Agent", "Self-Healing", "LLM", "Reliability"]
authors: ["yen"]
readTime: "26 min"
---

> 大多數工程師的方法：在工具呼叫外面包一層 `try-catch`，失敗就 retry 三次。
> 資深工程師的方法：把「校驗」與「推理」分離，讓 Agent 的反思循環成為架構的一等公民。
> 普通做法：靠運氣假設外部 API 永遠回傳正確格式。
> 正確做法：用強型別 Schema 把「偽正確」的垃圾數據攔截在下游之前，Critic Agent 重寫參數，Circuit Breaker 隔離毒源。

---

## 面試情境

> 你在一家跨境電商公司擔任 FDE，負責設計一個基於 LangGraph 的供應鏈自動化 Agent。
> 系統每天處理約 50,000 筆訂單，依賴三家第三方物流商的 API 進行貨況追蹤。
> 某天凌晨兩點，主要物流商的 API 開始回傳 HTTP 200 但夾帶格式錯誤的日期欄位（`DD/MM/YYYY` 而非 `YYYY-MM-DD`），
> 導致下游的 SQL Agent 批次寫入失敗，28% 的訂單狀態更新卡住。
> **面試官問：你如何在 Graph 設計層面實作自動容錯，讓系統不需要人工介入就能自我修復？
> 以及當自我修復三次仍失敗時，你的降級策略是什麼？**

---

## 一、核心問題：為什麼 try-catch 是必要但不充分的

### 1.1 兩種不同性質的故障

外部 API 的失敗分為兩種截然不同的類型，絕大多數工程師只處理了第一種：

```
故障類型 A：硬故障（Hard Failure）
  ├─ HTTP 4xx / 5xx
  ├─ Connection Timeout
  ├─ DNS 解析失敗
  └─ 對策：try-catch + exponential backoff ← 大家都做了

故障類型 B：軟故障（Soft / Silent Failure）
  ├─ HTTP 200，但 payload 格式錯誤（日期、時區、貨幣單位）
  ├─ HTTP 200，但欄位語意漂移（status: "in_transit" 變成 "IN_TRANSIT"）
  ├─ HTTP 200，但數值精度錯誤（公斤 vs 磅的混用）
  └─ 對策：需要 Schema 校驗 + 反思修正 ← 多數人沒有做
```

軟故障是最危險的，因為它**看起來成功**。下游的 SQL Agent 或 Pandas DataFrame 會靜默地接受垃圾數據，直到幾小時後報表出現異常才被發現，彼時已有幾萬筆記錄污染了資料庫。

### 1.2 為什麼純 Retry 不夠

純 retry 假設「失敗是暫時的」，但軟故障具有**持續性**：同一個有 Bug 的 API 端點，第二次、第三次仍然回傳同樣格式錯誤的資料。無腦 retry 只會讓垃圾數據被寫入三次。

正確的解法需要三個能力：
1. **偵測（Detection）**：Schema 強型別校驗，攔截格式錯誤
2. **診斷（Diagnosis）**：Critic Agent 分析失敗原因，推斷修正策略
3. **修復（Recovery）**：動態修改工具參數，或切換備用工具

---

## 二、三個演進階段

### ╔══ Phase 1（POC / < 10K 用戶）══╗

**目標**：最小可行容錯，能擋住硬故障即可，讓產品先跑起來。

```
┌──────────────────────────────────────────┐
│              LangGraph POC               │
│                                          │
│  ┌─────────────┐    ┌─────────────────┐  │
│  │  Worker     │───▶│  Next Node      │  │
│  │  (工具呼叫) │    │  (業務邏輯)     │  │
│  └──────┬──────┘    └─────────────────┘  │
│         │ Exception                       │
│         ▼                                 │
│  ┌─────────────┐                          │
│  │  try-catch  │  max_retries=3           │
│  │  + sleep    │  exponential backoff     │
│  └──────┬──────┘                          │
│         │ 3次失敗後                        │
│         ▼                                 │
│  ┌─────────────┐                          │
│  │  Error Log  │  終止流程，人工查看日誌  │
│  └─────────────┘                          │
└──────────────────────────────────────────┘
```

**Phase 1 新增元件**：
- 基本 try-catch 包裝器
- 固定 3 次 retry + 2 秒 backoff
- 錯誤寫入 Cloud Logging

**代價與限制**：
- 月費：~$20（單機 Cloud Run，日誌費用）
- 軟故障完全無防禦：格式錯誤數據直接流入下游
- 無備用工具切換能力
- 調試靠人工翻日誌，MTTD（平均偵測時間）約 2–4 小時

---

### ╔══ Phase 2（MVP / 10K–200K 用戶）══╗

**目標**：加入 Schema 校驗與單層 Fallback，消滅軟故障盲區。

```
┌────────────────────────────────────────────────────────────────┐
│                     LangGraph MVP                              │
│                                                                │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │  Worker     │───▶│  Validator Node  │───▶│  Next Node   │  │
│  │  (工具呼叫) │    │  (Pydantic 校驗) │    │  (業務邏輯)  │  │
│  └──────┬──────┘    └────────┬─────────┘    └──────────────┘  │
│         │                    │ ValidationError                 │
│         │                    ▼                                 │
│         │           ┌──────────────────┐                      │
│         │           │  Fallback Node   │                      │
│         │           │  (備用 API 呼叫) │                      │
│         │           └────────┬─────────┘                      │
│         │                    │ 仍失敗                          │
│         │                    ▼                                 │
│         └──────────▶ ┌──────────────────┐                     │
│                      │  Dead Letter     │  Slack 通知          │
│                      │  + 人工升級      │                      │
│                      └──────────────────┘                     │
└────────────────────────────────────────────────────────────────┘
```

**Phase 2 新增元件 vs Phase 1**：
- Pydantic BaseModel Schema 定義（每個 Tool Output 一個 Model）
- Validator Node：校驗失敗路由到 Fallback
- 單一備用 API 切換
- Cloud Pub/Sub → Slack 通知
- State 增加 `retry_count` 與 `error_log` 欄位

**代價與複雜度增量**：
- 月費：~$80（多一個 Fallback API 呼叫費 + Pub/Sub）
- 軟故障偵測率：~85%（覆蓋已知 Schema 違規）
- 仍無自動參數修正能力：格式問題需要人工調整後重跑
- MTTD 降至：~15 分鐘（Slack 通知）

---

### ╔══ Phase 3（Scale / 200K–1M+ 用戶）══╗

**目標**：Compiler-Validator Pattern，完整的自我修復循環，Circuit Breaker 防止雪崩。

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    LangGraph Production（Self-Healing Graph）              │
│                                                                           │
│  ┌──────────────┐   ┌───────────────────┐          ┌──────────────────┐  │
│  │  Worker Node │──▶│  Validator Node   │─(成功)──▶│  Next Node       │  │
│  │  (執行工具)  │   │  (Pydantic 硬校驗)│          │  (業務邏輯)      │  │
│  └──────┬───────┘   └────────┬──────────┘          └──────────────────┘  │
│         ▲                    │ ValidationError                            │
│         │                    ▼                                            │
│         │           ┌───────────────────┐                                │
│         │           │  Circuit Breaker  │ 連續 5 次失敗 → OPEN 狀態       │
│         │           └────────┬──────────┘                                │
│         │                    │ CLOSED / HALF-OPEN                        │
│         │                    ▼                                            │
│         │           ┌───────────────────┐   retry_count >= max_retries   │
│         │           │  Critic Agent     │──────────────────────────────▶ │
│  (動態  │           │  (反思重寫)       │                     ┌────────┐  │
│  修正參數)          │  - 分析失敗原因   │                     │ Dead   │  │
│         │           │  - 重寫工具參數   │                     │ Letter │  │
│         │           │  - 選擇備用工具   │                     │ State  │  │
│         │           └────────┬──────────┘                     └───┬────┘  │
│         │                    │ 修正後重試                         │       │
│         └────────────────────┘                                    │       │
│                                                                    ▼       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  Human-in-the-loop Node                                             │  │
│  │  Pub/Sub → Slack → 人工審核 → 批准後重新入佇列                      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

**Phase 3 新增元件 vs Phase 2**：
- Critic Agent Node（獨立 LLM 呼叫，上下文：原始意圖 + 失敗日誌 + 備用工具清單）
- Circuit Breaker：連續失敗 5 次 → OPEN（自動隔離問題 API）
- max_retries=3 護欄 + Dead Letter State（防無限循環）
- Fallback Matrix（三層：主 API → 備用 API → 靜態快取）
- Prometheus + Grafana 面板：即時追蹤 retry_count、validation_error_rate
- MTTD：< 1 分鐘（自動偵測）；MTTR < 5 分鐘（自動修復率 ~78%）

**代價**：月費 ~$380（Critic Agent LLM 呼叫 + 監控基礎設施）

---

## 三、Pydantic Validator Node 的設計細節

### 3.1 Schema 定義策略

每一個工具的輸出都必須有對應的 Pydantic Model，且要設計得「嚴格但有彈性」：

```python
from pydantic import BaseModel, validator, Field
from datetime import date
from typing import Optional, Literal
import re

class LogisticsTrackingOutput(BaseModel):
    """
    主物流商 API（TrackingAPI v2）的輸出 Schema。
    嚴格校驗日期格式與狀態枚舉，防止軟故障流入下游。
    """
    tracking_number: str = Field(..., regex=r'^[A-Z]{2}\d{9}[A-Z]{2}$')
    status: Literal["pending", "in_transit", "delivered", "exception"]
    estimated_delivery: date  # Pydantic 會自動解析 YYYY-MM-DD，拒絕其他格式
    weight_kg: float = Field(..., gt=0, lt=10000)
    carrier_code: Literal["DHL", "FEDEX", "UPS", "LOCAL_A", "LOCAL_B"]

    @validator('estimated_delivery', pre=True)
    def parse_date(cls, v):
        # 明確拒絕 DD/MM/YYYY 格式
        if isinstance(v, str) and re.match(r'^\d{2}/\d{2}/\d{4}$', v):
            raise ValueError(
                f"日期格式錯誤：收到 DD/MM/YYYY ({v})，預期 YYYY-MM-DD。"
                f"請使用 Critic Agent 修正 API 呼叫參數。"
            )
        return v
```

**關鍵設計原則**：
- `Literal` 類型強制枚舉：`"IN_TRANSIT"` 和 `"in_transit"` 是不同的值，前者會直接被拒絕
- 自訂 `@validator` 提供**人類可讀的錯誤訊息**，Critic Agent 能直接解讀並推理修正策略
- 數值範圍校驗（`gt=0, lt=10000`）攔截單位混淆（公斤 vs 磅）

### 3.2 Validator Node 的條件路由實作

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List

class AgentState(TypedDict):
    task: str
    tool_output: dict
    validation_error: Optional[str]
    retry_count: int
    max_retries: int          # 護欄：最大 3 次
    fallback_tools: List[str] # 備用工具清單
    dead_letter: bool

def validator_node(state: AgentState) -> AgentState:
    """Pydantic 硬校驗節點，失敗時把錯誤訊息寫入 state"""
    try:
        validated = LogisticsTrackingOutput(**state["tool_output"])
        return {**state, "validation_error": None}
    except ValidationError as e:
        return {
            **state,
            "validation_error": str(e),
            "retry_count": state["retry_count"] + 1,
        }

def route_after_validation(state: AgentState) -> str:
    """條件路由：校驗結果決定下一個節點"""
    if state["validation_error"] is None:
        return "next_business_node"
    elif state["retry_count"] >= state["max_retries"]:
        return "dead_letter_node"
    else:
        return "critic_agent_node"

# 圖的組裝
graph = StateGraph(AgentState)
graph.add_node("worker", worker_node)
graph.add_node("validator", validator_node)
graph.add_node("critic_agent", critic_agent_node)
graph.add_node("next_business_node", business_node)
graph.add_node("dead_letter_node", dead_letter_node)

graph.add_edge("worker", "validator")
graph.add_conditional_edges(
    "validator",
    route_after_validation,
    {
        "next_business_node": "next_business_node",
        "dead_letter_node": "dead_letter_node",
        "critic_agent_node": "critic_agent",
    }
)
graph.add_edge("critic_agent", "worker")  # 修正後回到 worker 重試
```

---

## 四、Critic Agent 的反思重寫設計

### 4.1 上下文工程（Context Engineering）

Critic Agent 的品質完全取決於它收到的上下文。三個必要元素缺一不可：

```
┌─────────────────────────────────────────────────────────────┐
│                  Critic Agent 上下文結構                     │
│                                                             │
│  ① 原始用戶意圖                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ "查詢訂單 ORD-2026-00431 的最新物流狀態，             │  │
│  │  預計到達日期，以及是否有異常"                         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ② 失敗的工具呼叫參數 + 報錯日誌                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Tool: primary_logistics_api                           │  │
│  │ Params: {"tracking_id": "TW123456789TW",              │  │
│  │          "date_format": "auto"}                       │  │
│  │ Error: ValidationError: estimated_delivery            │  │
│  │        日期格式錯誤：收到 DD/MM/YYYY (08/06/2026)，   │  │
│  │        預期 YYYY-MM-DD                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ③ 備用工具清單（Fallback Matrix）                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [0] primary_logistics_api (失敗中，retry 1/3)         │  │
│  │ [1] backup_logistics_api  (健康，支援 date_format 參數)│  │
│  │ [2] static_cache_lookup   (最後更新: 4小時前)         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Critic Agent 的決策邏輯

```python
CRITIC_PROMPT = """
你是一個工具修復專家。分析以下失敗情況，決定修復策略。

## 原始任務
{original_intent}

## 失敗工具呼叫
工具名稱：{failed_tool}
呼叫參數：{failed_params}
錯誤訊息：{error_message}

## 可用工具清單
{available_tools}

## 你的任務
1. 分析錯誤根因（是參數問題？格式問題？還是工具本身故障？）
2. 決定策略：
   - 策略A：修正原工具的呼叫參數後重試
   - 策略B：切換到備用工具（說明選哪個、為什麼）
   - 策略C：使用靜態快取數據（說明可接受的數據時效性）
3. 輸出修正後的工具呼叫配置（JSON 格式）

注意：若錯誤是格式問題（如日期格式），優先嘗試策略A，加上明確的 date_format 參數。
若錯誤持續（retry_count >= 2），切換到備用工具（策略B）。

輸出格式：
{
  "root_cause": "...",
  "strategy": "A|B|C",
  "tool_name": "...",
  "corrected_params": {...},
  "reasoning": "..."
}
"""

def critic_agent_node(state: AgentState) -> AgentState:
    """
    Critic Agent 節點：分析失敗原因，修正工具呼叫參數
    """
    prompt = CRITIC_PROMPT.format(
        original_intent=state["task"],
        failed_tool=state.get("last_tool", "unknown"),
        failed_params=state.get("last_tool_params", {}),
        error_message=state["validation_error"],
        available_tools=state["fallback_tools"],
    )

    # 呼叫 LLM 進行反思（使用較小的模型降低延遲與成本）
    response = llm.invoke(prompt)
    correction = json.loads(response.content)

    return {
        **state,
        "current_tool": correction["tool_name"],
        "current_tool_params": correction["corrected_params"],
        "validation_error": None,  # 重置，讓 worker 重新嘗試
        "critic_reasoning": correction["reasoning"],
    }
```

**Critic Agent 實際修復範例**：

| 錯誤類型 | 根因分析 | 修復策略 | 修正後參數 |
|---------|---------|---------|-----------|
| 日期格式 DD/MM/YYYY | API 端預設格式變更 | 策略A：加 `date_format=ISO` | `{"date_format": "YYYY-MM-DD"}` |
| status 大小寫漂移 | API 版本升級 | 策略A：加 `response_version=v1` | `{"api_version": "1.0"}` |
| 重量單位磅→公斤 | 新部署的端點 | 策略B：切備用 API | 切換至 `backup_logistics_api` |
| API 持續 500 | 服務宕機 | 策略B → C | 先備用 API，若也失敗用快取 |

---

## 五、Circuit Breaker 防雪崩設計

### 5.1 三態機器的狀態轉換

Circuit Breaker 防止系統持續攻打一個已知損壞的 API，避免資源浪費與雪崩效應：

```
┌─────────────────────────────────────────────────────────────────┐
│                   Circuit Breaker 狀態機                         │
│                                                                 │
│         連續失敗 ≥ 5 次                                         │
│  CLOSED ─────────────────────────▶ OPEN                        │
│  (正常)                            (隔離)                       │
│    ▲                                  │                         │
│    │                                  │ timeout = 60 秒後       │
│    │                                  ▼                         │
│    │  成功               HALF-OPEN ◀──                         │
│    └────────────────────── (探測)                               │
│                            放行 1 req/10s                       │
│                            失敗 → 回 OPEN                       │
│                                                                 │
│  狀態存儲：Redis（TTL 300s），支援多 Worker 共享狀態             │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Circuit Breaker 實作

```python
import redis
from datetime import datetime, timedelta

class CircuitBreaker:
    def __init__(self, tool_name: str, failure_threshold: int = 5,
                 timeout_seconds: int = 60):
        self.tool_name = tool_name
        self.failure_threshold = failure_threshold
        self.timeout = timeout_seconds
        self.redis = redis.Redis(host="redis-service", port=6379)
        self.state_key = f"cb:{tool_name}:state"
        self.failure_key = f"cb:{tool_name}:failures"
        self.open_since_key = f"cb:{tool_name}:open_since"

    def get_state(self) -> str:
        """回傳 CLOSED / OPEN / HALF_OPEN"""
        state = self.redis.get(self.state_key)
        if state is None or state == b"CLOSED":
            return "CLOSED"
        if state == b"OPEN":
            open_since = float(self.redis.get(self.open_since_key) or 0)
            if datetime.now().timestamp() - open_since > self.timeout:
                self.redis.set(self.state_key, "HALF_OPEN")
                return "HALF_OPEN"
            return "OPEN"
        return "HALF_OPEN"

    def record_failure(self):
        failures = self.redis.incr(self.failure_key)
        self.redis.expire(self.failure_key, 300)  # 5 分鐘滾動窗口
        if failures >= self.failure_threshold:
            self.redis.set(self.state_key, "OPEN")
            self.redis.set(self.open_since_key, datetime.now().timestamp())

    def record_success(self):
        self.redis.set(self.state_key, "CLOSED")
        self.redis.set(self.failure_key, 0)

    def can_proceed(self) -> bool:
        state = self.get_state()
        return state in ("CLOSED", "HALF_OPEN")
```

### 5.3 Fallback Matrix（三層降級策略）

```
┌────────────────────────────────────────────────────────────────┐
│                    Fallback Matrix                             │
│                                                                │
│  Layer 1（主 API）：primary_logistics_api                      │
│  ├─ 回應時間：< 200ms P99                                      │
│  ├─ 可用性 SLA：99.5%                                          │
│  └─ 失敗條件：CB = OPEN 或 Validator 失敗 retry >= 2          │
│          │                                                     │
│          ▼ 切換（延遲 < 50ms，CB 切換本身）                    │
│  Layer 2（備用 API）：backup_logistics_api                     │
│  ├─ 回應時間：< 500ms P99（較慢但穩定）                        │
│  ├─ 費用：主 API 的 1.8 倍                                     │
│  └─ 失敗條件：同樣進入 CB 判斷                                 │
│          │                                                     │
│          ▼ 切換（使用靜態數據）                                 │
│  Layer 3（靜態快取）：Redis Cache + GCS 快照                   │
│  ├─ 數據時效：最近 4 小時的成功查詢結果                        │
│  ├─ 費用：~$0.002 / 1000 次讀取                               │
│  ├─ 回應時間：< 5ms                                           │
│  └─ 限制：無法取得即時狀態，需在回應中標注 "cached_at" 時間戳  │
└────────────────────────────────────────────────────────────────┘
```

---

## 六、Dead Letter State 與 Human-in-the-Loop

### 6.1 Dead Letter State 設計

當三次自我修復全部失敗，不能讓 Agent 無限循環，必須有一個明確的「終止並上報」機制：

```python
class DeadLetterState(TypedDict):
    task_id: str
    original_task: str
    failure_history: List[dict]   # 三次嘗試的詳細記錄
    last_error: str
    circuit_breaker_states: dict  # 各 API 的 CB 狀態快照
    escalation_level: Literal["slack", "pagerduty", "manual"]
    created_at: str

def dead_letter_node(state: AgentState) -> AgentState:
    """
    進入 Dead Letter：
    1. 記錄完整失敗歷史到 Firestore
    2. 根據業務優先級決定升級路徑
    3. 發布到 Cloud Pub/Sub → 觸發通知
    """
    dead_letter = DeadLetterState(
        task_id=state["task_id"],
        original_task=state["task"],
        failure_history=state.get("failure_history", []),
        last_error=state["validation_error"],
        circuit_breaker_states=get_all_cb_states(),
        escalation_level=determine_escalation(state),
        created_at=datetime.utcnow().isoformat(),
    )

    # 持久化到 Firestore（不丟失）
    firestore_client.collection("dead_letters").add(dead_letter)

    # 發布通知事件
    pubsub_client.publish(
        topic="agent-dead-letters",
        data=json.dumps(dead_letter).encode(),
    )

    return {**state, "dead_letter": True, "status": "ESCALATED"}
```

### 6.2 Human-in-the-Loop 升級路徑

```
業務優先級判斷矩陣：

  訂單金額 > $1000 或 VIP 客戶：
    → PagerDuty（立即喚人，24/7）
    → MTTA（平均接收時間）目標：< 5 分鐘

  一般訂單，失敗訂單數 > 100：
    → Slack #oncall-supply-chain 頻道
    → 附上自動生成的 Runbook 連結
    → MTTA 目標：< 30 分鐘

  低優先級，失敗訂單數 < 10：
    → 寫入 Firestore dead_letters collection
    → 每日彙整報告（次日 09:00 自動發送）
    → 人工批次處理
```

---

## 七、可觀測性：讓自我修復過程透明

### 7.1 關鍵指標設計

自我修復機制若缺乏可觀測性，就是一個「黑箱治癒」——你不知道它在修什麼、修了幾次、花了多久。

```
┌─────────────────────────────────────────────────────────────────┐
│                  Prometheus 指標設計                             │
│                                                                 │
│  agent_tool_calls_total{tool, status}                          │
│  ├─ status: success / validation_error / http_error            │
│  └─ 用途：計算各工具的錯誤率                                   │
│                                                                 │
│  agent_validation_errors_total{tool, error_type}               │
│  ├─ error_type: date_format / enum_mismatch / range_violation  │
│  └─ 用途：識別最常見的軟故障類型                               │
│                                                                 │
│  agent_critic_interventions_total{tool, strategy}              │
│  ├─ strategy: param_fix / tool_switch / cache_fallback         │
│  └─ 用途：Critic Agent 決策品質評估                            │
│                                                                 │
│  agent_self_healing_success_rate（每 5 分鐘滾動窗口）           │
│  └─ 用途：核心 SLA 指標，目標 > 75%                            │
│                                                                 │
│  circuit_breaker_state{tool}                                   │
│  └─ 值：0=CLOSED, 1=HALF_OPEN, 2=OPEN                         │
│                                                                 │
│  dead_letter_queue_size（即時計數）                             │
│  └─ 告警閾值：> 50 筆 → PagerDuty                              │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Trace 設計（追蹤自我修復路徑）

每一次自我修復嘗試都必須在分散式追蹤中留下完整記錄：

```
Trace: task_id=ORD-2026-00431
  ├─ Span: worker_node (duration: 230ms)
  │    tool: primary_logistics_api
  │    params: {tracking_id: "TW123456789TW"}
  │    result: ValidationError (date_format)
  │
  ├─ Span: validator_node (duration: 2ms)
  │    error: "DD/MM/YYYY format detected"
  │    retry_count: 1/3
  │
  ├─ Span: critic_agent_node (duration: 1840ms) ← LLM 呼叫延遲
  │    strategy: A (param_fix)
  │    corrected_params: {date_format: "YYYY-MM-DD"}
  │    model: gemini-1.5-flash (低延遲選擇)
  │
  ├─ Span: worker_node (duration: 195ms) ← 第二次嘗試
  │    tool: primary_logistics_api（修正參數）
  │    result: SUCCESS ✓
  │
  └─ Total: 2267ms（含 LLM 修復時間）
     自我修復用時：2267 - 230 = 2037ms
```

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|------------|--------------|----------------|
| **Pydantic 硬校驗** vs 僅 try-catch | 攔截格式正確但語意錯誤的「偽正確」數據；ValidationError 訊息人類可讀，Critic Agent 能直接解讀 | try-catch 只攔截異常，HTTP 200 + 垃圾數據完全透傳，下游靜默污染 | 若外部 API 有 OpenAPI/JSON Schema 規範且嚴格遵守，try-catch 可能已足夠（但罕見） |
| **Critic Agent（LLM 反思）** vs 規則引擎 | 應對未知格式漂移；LLM 能推理「DD/MM/YYYY → 加 date_format 參數」這種語意關聯 | 規則引擎需要預先枚舉所有可能錯誤，第三方 API 的格式變化無法預測 | 若錯誤類型有限且已知（< 10 種），純規則引擎成本更低（無 LLM 呼叫費 $0.008/次） |
| **Circuit Breaker（Redis 共享）** vs 本地狀態 | 多個 Worker 共享 CB 狀態，一個 Worker 發現 API 失敗立即保護所有 Worker | 本地 CB 狀態無法跨 Pod 共享，每個 Pod 都要踩一遍失敗才能觸發保護 | 單一 Worker / 單機部署時，本地 CB 足夠，省去 Redis 依賴 |
| **max_retries=3 護欄** vs 無限重試 | 防止 Agent 陷入修復循環消耗 LLM Token 與 API 配額；最差情況下成本可預測 | 無限重試可能在 API 端修復前持續消耗，每次 Critic Agent 呼叫約 $0.008，無限重試 = 無限燒錢 | 若任務極其重要（如金融交割），可考慮 max_retries=10 但加上費用上限熔斷 |
| **Cloud Pub/Sub 通知** vs 直接 Slack API 呼叫 | 解耦通知與業務邏輯；Pub/Sub 有持久化保證，即使 Slack 暫時無法連線也不丟失事件 | 直接呼叫 Slack API 若失敗則通知丟失；且 Pub/Sub 可扇出至多個下游（PagerDuty、Email、JIRA 同時觸發） | 若系統規模小（< 100 事件/天），直接 Slack 呼叫複雜度更低 |
| **gemini-1.5-flash for Critic** vs GPT-4 | Critic Agent 任務結構化明確，Flash 延遲 < 800ms，成本 $0.002/次；GPT-4 需要 3–5 秒，$0.03/次 | GPT-4 在非結構化推理上更強，但修復任務有固定 Prompt 範本，Flash 品質足夠（實測修復成功率 Flash 72% vs GPT-4 78%，差距 6%，但成本差 15 倍） | 若 Critic 需要處理極其複雜的參數重寫（如 GraphQL 查詢重構），換 claude-3-5-sonnet 或 GPT-4 |

---

## 九、系統效應：前後對比

| 指標 | 導入前（純 try-catch） | 導入後（Self-Healing Graph） | 改善幅度 |
|------|----------------------|------------------------------|---------|
| **軟故障偵測率** | 0%（靜默失敗） | 94%（Pydantic 攔截 + Validator） | +94 pp |
| **自動修復率**（無需人工） | 0% | 78%（Critic Agent 修復成功） | +78 pp |
| **MTTD**（平均偵測時間） | 2–4 小時（查報表才發現） | < 1 分鐘（即時 Validator） | -99% |
| **MTTR**（平均修復時間） | 45 分鐘（人工排查 + 重跑） | 2.3 分鐘（自動修復），27 分鐘（人工介入） | -95% / -40% |
| **資料庫污染筆數**（事件期間） | ~28,000 筆（一夜未發現） | 0 筆（Validator 在寫入前攔截） | -100% |
| **Critic Agent 平均延遲** | N/A | 1.8 秒（P50），3.2 秒（P99） | 新增 |
| **月額外成本** | $0 | +$180（LLM 呼叫 + Redis + Pub/Sub） | +$180/月 |
| **Dead Letter 事件率** | ~100%（所有錯誤都上報） | 22%（其餘被自動修復） | -78% |
| **On-call 警報量**（月） | 340 次 | 75 次（其中 22% 為真正需人工介入） | -78% |
| **API 切換延遲**（CB 觸發） | 無（只有人工操作） | < 50ms（CB 狀態讀取 Redis） | 新增能力 |
| **P99 端對端延遲**（含修復） | 230ms（無修復）/ 無限（掛掉） | 230ms（正常）/ ~3.5 秒（含 Critic） | SLA 可預測 |

---

## 十、面試答題要點

> *「我會在 LangGraph 中引入 Compiler-Validator Pattern：每個工具輸出都綁定一個 Pydantic BaseModel，Validator Node 做強型別硬校驗，成功走下一節點，失敗導向 Critic Agent。Critic Agent 拿到三份上下文——原始意圖、失敗日誌、備用工具清單——重新推理修正參數或切換工具，修正後回到 Worker 重試。State 機器設定 max_retries=3 護欄防無限循環，這一層能覆蓋約 78% 的自動修復場景。底層我還會部署 Circuit Breaker（Redis 共享狀態），連續 5 次失敗自動隔離問題 API，防止雪崩。若 3 次修復全部失敗，Dead Letter State 發布事件到 Cloud Pub/Sub，依訂單金額決定升級至 Slack 或 PagerDuty。這套架構的核心價值是：把「偵測」和「推理」分離，讓反思循環成為架構一等公民，而不是在業務邏輯裡散落一堆 try-catch，實測將 MTTD 從 4 小時降至 1 分鐘，資料庫污染事件歸零。」*

---

## 十一、面試常見追問與應對

**Q：Critic Agent 自己呼叫 LLM 會不會也出錯？你如何確保 Critic Agent 的輸出可靠？**

應對：Critic Agent 的輸出同樣需要 Schema 校驗。Critic 必須輸出嚴格 JSON（`strategy`、`tool_name`、`corrected_params`），若 JSON 解析失敗或不符合 Schema，直接跳過修復，進入 Dead Letter，不讓 Critic 本身的 Bug 再引發新的修復循環（「修復者的修復者」的無窮遞歸問題）。

**Q：如果備用 API 也壞了，靜態快取數據有多久的時效性？業務可以接受嗎？**

應對：這取決於業務 SLA。在供應鏈場景中，我們設定快取 TTL = 4 小時，並在回應中明確標注 `cached_at` 時間戳，讓下游業務邏輯自行判斷是否接受。對於「包裹到哪了」這種查詢，4 小時前的數據可能還可以接受（告知用戶「最後更新於 XX:XX」）；但對於「庫存是否足夠接單」，快取數據可能造成超賣，此時必須阻斷並上報人工。

**Q：Critic Agent 每次呼叫 LLM 有額外延遲，如何保證端對端 SLA？**

應對：Critic Agent 使用輕量模型（gemini-1.5-flash，P99 < 3.2 秒），且只在異常路徑觸發，正常路徑延遲不受影響（仍是 < 300ms）。異常路徑的 SLA 可以放寬：使用者寧可等 3 秒收到正確數據，也不要立刻收到錯誤數據。在 SLA 合約中，我們將自動修復路徑的 P99 設為 5 秒，與正常路徑的 300ms 分開計算。

---

**系列導航**

← [Part 47：供應鏈 Agent 的分散式追蹤與可觀測性](/posts/fde-interview-guide-part47-supply-chain-observability-zh/) | [Part 49：多 Agent 協作系統的工作流編排與衝突解決](/posts/fde-interview-guide-part49-multi-agent-orchestration-zh/) →
