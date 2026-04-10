---
title: "LangGraph AI 後端邏輯設計：狀態流、決策路由和條件轉移"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "LangGraph", "logic-design"]
tags: ["LangGraph", "邏輯設計", "狀態流", "路由", "決策", "工作流"]
summary: "深入探討 LangGraph 工作流的邏輯設計，包括狀態定義、決策路由、條件轉移、複雜路徑選擇等，透過實戰案例展示如何設計清晰、高效、易維護的 AI 後端邏輯。"
readTime: "42 min"
---

LangGraph 的核心價值在於能表達**複雜的決策邏輯**和**動態的工作流**。相比線性的 Chain，LangGraph 允許根據中間狀態做出決策，選擇不同的處理路徑。本文深入講解如何設計 LangGraph 的邏輯層。

---

## 狀態設計的藝術

### 狀態vs消息的權衡

```
消息模式（LangChain Chain）：
input → [處理] → output

狀態模式（LangGraph）：
state = {data1, data2, ..., flags, counters, history}
state → [Agent A] → state' → [Agent B] → state''

狀態的優勢：
1. 保留歷史信息
2. 支持複雜決策
3. 可追蹤性強
4. 支持重試和恢復
```

### 分層狀態設計

```python
from dataclasses import dataclass, field
from typing import Optional, Annotated
from datetime import datetime

@dataclass
class RequestMetadata:
    """請求元數據（不變）"""
    request_id: str
    user_id: str
    timestamp: str
    priority: str  # low, medium, high, critical

@dataclass
class ProcessingContext:
    """處理上下文（易變）"""
    current_step: str  # 當前步驟
    step_history: list[str] = field(default_factory=list)  # 完成的步驟
    retry_count: int = 0
    last_error: Optional[str] = None
    checkpoint_data: dict = field(default_factory=dict)  # 檢查點

@dataclass
class IntermediateResults:
    """中間結果（逐步累積）"""
    analysis: Optional[str] = None
    validation_status: Optional[bool] = None
    routing_decision: Optional[str] = None
    extracted_data: dict = field(default_factory=dict)

@dataclass
class FinalOutput:
    """最終輸出"""
    response: Optional[str] = None
    confidence_score: float = 0.0
    model_version: Optional[str] = None

@dataclass
class CompleteState:
    """完整狀態 = 元數據 + 上下文 + 中間結果 + 最終輸出"""
    metadata: RequestMetadata
    context: ProcessingContext
    intermediate: IntermediateResults
    output: FinalOutput

# 狀態訪問模式
def get_state_summary(state: CompleteState) -> dict:
    """獲取狀態摘要用於決策"""
    return {
        "is_retrying": state.context.retry_count > 0,
        "has_analysis": state.intermediate.analysis is not None,
        "is_high_priority": state.metadata.priority == "critical",
        "last_step": state.context.step_history[-1] if state.context.step_history else None
    }
```

### 狀態更新的原則

```python
# ❌ 反面：直接修改狀態
def bad_update(state: CompleteState):
    state.intermediate.analysis = result  # 不安全
    return state

# ✅ 正確：構造新狀態
def good_update(state: CompleteState):
    return CompleteState(
        metadata=state.metadata,  # 保持不變
        context=ProcessingContext(
            current_step="analysis",
            step_history=state.context.step_history + ["analysis"],
            retry_count=state.context.retry_count
        ),
        intermediate=IntermediateResults(
            analysis=result,
            validation_status=state.intermediate.validation_status,
            routing_decision=state.intermediate.routing_decision
        ),
        output=state.output
    )
```

---

## 決策路由設計

### 1. 二元決策（If-Else）

```python
def simple_condition(state: CompleteState) -> str:
    """簡單的是/否決策"""
    if state.intermediate.analysis:
        return "proceed"
    else:
        return "retry"

workflow.add_conditional_edges(
    "analysis_node",
    simple_condition,
    {
        "proceed": "validation_node",
        "retry": "analysis_node"
    }
)
```

### 2. 多路決策（Switch）

```python
def multi_way_router(state: CompleteState) -> str:
    """根據類型選擇不同路徑"""
    category = state.intermediate.extracted_data.get("category")
    
    router_map = {
        "technical": "technical_handler",
        "billing": "billing_handler",
        "account": "account_handler",
        "other": "default_handler"
    }
    
    return router_map.get(category, "default_handler")

workflow.add_conditional_edges(
    "classification_node",
    multi_way_router,
    {
        "technical_handler": "technical_handler",
        "billing_handler": "billing_handler",
        "account_handler": "account_handler",
        "default_handler": "default_handler"
    }
)
```

### 3. 優先級路由

```python
def priority_router(state: CompleteState) -> str:
    """根據優先級選擇處理路徑"""
    priority = state.metadata.priority
    
    if priority == "critical":
        return "fast_track"
    elif priority == "high":
        return "priority_track"
    else:
        return "normal_track"

# 不同優先級的 SLA
fast_track_sla = 60      # 1 分鐘
priority_track_sla = 300 # 5 分鐘
normal_track_sla = 3600  # 1 小時
```

### 4. 複雜決策（AI 輔助）

```python
def ai_powered_router(state: CompleteState) -> str:
    """使用 AI 做複雜決策"""
    from langchain_anthropic import ChatAnthropic
    
    model = ChatAnthropic()
    
    prompt = f"""
    根據以下信息決定下一步：
    
    分析結果：{state.intermediate.analysis}
    驗證狀態：{state.intermediate.validation_status}
    錯誤信息：{state.context.last_error}
    重試次數：{state.context.retry_count}
    
    可選路徑：
    1. "escalate" - 升級給人工
    2. "retry" - 重試
    3. "proceed" - 繼續
    4. "abort" - 中止
    
    選擇最合適的路徑：
    """
    
    response = model.invoke(prompt)
    decision = response.content.strip().lower()
    
    # 確保返回有效的選擇
    valid_choices = ["escalate", "retry", "proceed", "abort"]
    return decision if decision in valid_choices else "proceed"

workflow.add_conditional_edges(
    "decision_node",
    ai_powered_router,
    {
        "escalate": "human_escalation",
        "retry": "analysis_node",
        "proceed": "validation_node",
        "abort": END
    }
)
```

---

## 複雜工作流邏輯

### 1. 重試邏輯

```python
@dataclass
class RetryableState:
    max_retries: int = 3
    retry_count: int = 0
    last_error: Optional[str] = None

def retry_decision(state: RetryableState) -> str:
    """決定是否重試"""
    if state.retry_count >= state.max_retries:
        return "max_retries_exceeded"
    
    # 某些錯誤不應該重試
    non_retryable_errors = [
        "validation_error",
        "unauthorized",
        "not_found"
    ]
    
    if any(error in state.last_error for error in non_retryable_errors):
        return "non_retryable"
    
    return "retry"

def retry_with_backoff(state: RetryableState) -> RetryableState:
    """指數退避重試"""
    import time
    
    backoff = 2 ** state.retry_count  # 1s, 2s, 4s
    time.sleep(min(backoff, 30))  # 最多等待 30 秒
    
    state.retry_count += 1
    return state
```

### 2. 並行執行後的合併邏輯

```python
@dataclass
class ParallelTasksState:
    task_a_result: Optional[dict] = None
    task_b_result: Optional[dict] = None
    task_c_result: Optional[dict] = None
    all_succeeded: bool = False

def merge_parallel_results(state: ParallelTasksState) -> ParallelTasksState:
    """合併並行任務的結果"""
    
    # 檢查是否所有任務都成功
    all_results = [
        state.task_a_result,
        state.task_b_result,
        state.task_c_result
    ]
    
    state.all_succeeded = all(r is not None for r in all_results)
    
    if state.all_succeeded:
        # 合併邏輯
        merged = {
            "summary": f"A: {state.task_a_result.get('summary', '')}",
            "analysis": f"B: {state.task_b_result.get('analysis', '')}",
            "recommendation": f"C: {state.task_c_result.get('recommendation', '')}"
        }
        return state
    else:
        # 某些任務失敗，決定是重試還是降級
        return state

def decide_after_parallel(state: ParallelTasksState) -> str:
    """並行任務完成後的決策"""
    if state.all_succeeded:
        return "proceed"
    elif state.task_a_result and state.task_b_result:
        return "partial_proceed"  # 至少 2 個成功
    else:
        return "retry_failed_tasks"
```

### 3. 分支合並（Join）邏輯

```python
@dataclass
class BranchJoinState:
    branch_path: Optional[str] = None
    # 各分支的結果
    path_a_result: Optional[dict] = None
    path_b_result: Optional[dict] = None
    path_c_result: Optional[dict] = None
    join_result: Optional[dict] = None

def join_branches(state: BranchJoinState) -> BranchJoinState:
    """合併分支結果"""
    
    if state.branch_path == "a":
        result = state.path_a_result
    elif state.branch_path == "b":
        result = state.path_b_result
    elif state.branch_path == "c":
        result = state.path_c_result
    else:
        result = None
    
    state.join_result = result
    return state

# 工作流示例
workflow = StateGraph(BranchJoinState)

def route_to_branch(state: BranchJoinState) -> str:
    """路由到不同分支"""
    priority = state.metadata.priority
    if priority == "critical":
        return "path_a"
    elif priority == "high":
        return "path_b"
    else:
        return "path_c"

workflow.add_conditional_edges(
    "route",
    route_to_branch,
    {
        "path_a": "branch_a",
        "path_b": "branch_b",
        "path_c": "branch_c"
    }
)

# 所有分支在 join 點匯聚
workflow.add_edge("branch_a", "join")
workflow.add_edge("branch_b", "join")
workflow.add_edge("branch_c", "join")
```

---

## 狀態轉移圖設計

### 狀態機模式

```python
from enum import Enum

class WorkflowStatus(Enum):
    """工作流狀態定義"""
    PENDING = "pending"           # 等待開始
    ANALYZING = "analyzing"       # 分析中
    VALIDATING = "validating"     # 驗證中
    ROUTING = "routing"           # 路由中
    PROCESSING = "processing"     # 處理中
    SUCCEEDED = "succeeded"       # 成功
    FAILED = "failed"             # 失敗
    ESCALATED = "escalated"       # 升級

# 有效的狀態轉移
VALID_TRANSITIONS = {
    WorkflowStatus.PENDING: [WorkflowStatus.ANALYZING],
    WorkflowStatus.ANALYZING: [
        WorkflowStatus.VALIDATING,
        WorkflowStatus.FAILED
    ],
    WorkflowStatus.VALIDATING: [
        WorkflowStatus.ROUTING,
        WorkflowStatus.FAILED
    ],
    WorkflowStatus.ROUTING: [
        WorkflowStatus.PROCESSING,
        WorkflowStatus.ESCALATED
    ],
    WorkflowStatus.PROCESSING: [
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.FAILED
    ],
    WorkflowStatus.FAILED: [WorkflowStatus.ANALYZING],  # 重試
    WorkflowStatus.ESCALATED: [],  # 終態
    WorkflowStatus.SUCCEEDED: []   # 終態
}

def validate_transition(current: WorkflowStatus, next_status: WorkflowStatus) -> bool:
    """驗證狀態轉移是否合法"""
    return next_status in VALID_TRANSITIONS.get(current, [])

@dataclass
class StateMachineState:
    current_status: WorkflowStatus = WorkflowStatus.PENDING
    
    def transition_to(self, new_status: WorkflowStatus):
        if validate_transition(self.current_status, new_status):
            self.current_status = new_status
            return True
        else:
            raise ValueError(
                f"Invalid transition from {self.current_status} to {new_status}"
            )
```

---

## 決策邏輯的可測試性

### 單元測試決策函數

```python
import pytest

def test_priority_router():
    """測試優先級路由"""
    state = CompleteState(
        metadata=RequestMetadata(
            request_id="test",
            user_id="user1",
            timestamp="2024-01-01",
            priority="critical"
        ),
        context=ProcessingContext(current_step="init"),
        intermediate=IntermediateResults(),
        output=FinalOutput()
    )
    
    result = priority_router(state)
    assert result == "fast_track"

def test_retry_logic():
    """測試重試邏輯"""
    state = RetryableState(max_retries=3, retry_count=0)
    assert retry_decision(state) == "retry"
    
    state.retry_count = 3
    assert retry_decision(state) == "max_retries_exceeded"

def test_merge_results():
    """測試結果合併"""
    state = ParallelTasksState(
        task_a_result={"data": "a"},
        task_b_result={"data": "b"},
        task_c_result={"data": "c"}
    )
    
    result = merge_parallel_results(state)
    assert result.all_succeeded == True
```

---

## 邏輯設計最佳實踐

### 1. 清晰的決策點

```python
# ❌ 不清楚
def process(state):
    if state.data and state.status and len(state.data) > 5:
        return "path_a"
    else:
        return "path_b"

# ✅ 清晰
def should_use_fast_path(state: CompleteState) -> bool:
    """檢查是否應該使用快速路徑"""
    has_data = state.intermediate.analysis is not None
    status_valid = state.intermediate.validation_status is True
    sufficient_confidence = len(state.intermediate.analysis) > 100
    
    return has_data and status_valid and sufficient_confidence

def route_based_on_path_decision(state: CompleteState) -> str:
    if should_use_fast_path(state):
        return "fast_path"
    else:
        return "normal_path"
```

### 2. 決策的文檔化

```python
def complex_router(state: CompleteState) -> str:
    """
    複雜路由決策
    
    決策樹：
    1. 如果優先級是 critical → fast_track (SLA: 1 min)
    2. 否則，如果有驗證錯誤 → escalate (SLA: 5 min)
    3. 否則，如果分析置信度 > 0.9 → proceed (SLA: 30 min)
    4. 否則 → manual_review (SLA: 1 hour)
    
    Args:
        state: 完整狀態
    
    Returns:
        下一個節點的名稱
    """
    # 實現...
    pass
```

### 3. 降級策略

```python
def route_with_fallback(state: CompleteState) -> str:
    """帶降級的路由"""
    try:
        # 首選：AI 輔助決策
        return ai_powered_router(state)
    except Exception as e:
        logger.warning(f"AI router failed: {e}")
        # 降級：規則型決策
        return rule_based_router(state)
```

---

## 邏輯複雜度分析

| 邏輯類型 | 複雜度 | 可測試性 | 調試難度 |
|---------|-------|--------|--------|
| 簡單線性 | O(1) | 高 | 低 |
| 二元決策 | O(1) | 高 | 低 |
| 多路決策 | O(n) | 中 | 低 |
| 優先級決策 | O(n) | 中 | 中 |
| AI 輔助決策 | O(1) | 低 | 高 |
| 複雜並行 | O(n²) | 低 | 高 |

---

## 總結

LangGraph 的邏輯設計原則：

1. **狀態第一**：清晰的狀態定義是基礎
2. **顯式決策**：決策點應該明確、可追蹤
3. **容錯設計**：失敗應該導向降級而不是崩潰
4. **可測試**：邏輯應該能被單獨測試
5. **可維護**：複雜邏輯應該有文檔和清晰的命名

好的邏輯設計能讓 AI 後端系統既強大又可靠。
