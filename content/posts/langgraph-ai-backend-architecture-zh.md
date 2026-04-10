---
title: "LangGraph AI 後端架構設計模式：從單體到分佈式"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "LangGraph", "architecture"]
tags: ["LangGraph", "AI", "架構", "後端設計", "系統設計", "可擴展性"]
summary: "深入講解如何設計可擴展、高性能的 LangGraph AI 後端架構，涵蓋從單體應用到微服務的演進，包括 Agent 拓撲、數據流、錯誤恢復、分佈式協調等生產級設計模式。"
readTime: "40 min"
---

構建生產級的 LangGraph AI 後端不僅僅是寫代碼，更需要從系統層面考慮**可擴展性、可靠性、可追蹤性**。本文介紹如何設計健壯的 LangGraph 架構，從單機應用進化到分佈式系統。

---

## 單體應用架構

### 最簡單的架構

```
用戶請求
    ↓
[FastAPI 服務]
    ↓
[LangGraph 工作流]
    ├→ [Agent 1]
    ├→ [Agent 2]
    └→ [Agent 3]
    ↓
[數據庫]
```

```python
from fastapi import FastAPI
from langgraph.graph import StateGraph, START, END
from dataclasses import dataclass
import json

app = FastAPI()

@dataclass
class RequestState:
    user_input: str
    agent_results: dict = None
    final_output: str = None

def build_simple_workflow():
    """最簡單的工作流"""
    workflow = StateGraph(RequestState)
    
    def process_agent(state: RequestState):
        state.agent_results = {
            "analysis": f"分析: {state.user_input}",
            "summary": f"摘要: {state.user_input[:20]}..."
        }
        return state
    
    workflow.add_node("process", process_agent)
    workflow.add_edge(START, "process")
    workflow.add_edge("process", END)
    return workflow.compile()

workflow = build_simple_workflow()

@app.post("/process")
async def process_request(request: dict):
    state = RequestState(user_input=request["input"])
    result = workflow.invoke(state)
    return {"output": result.agent_results}
```

### 問題：單點故障

```
┌─────────────────────────────────────┐
│      FastAPI (單點)                   │
│  ┌────────────────────────────────┐  │
│  │ LangGraph 工作流 (單進程)       │  │
│  └────────────────────────────────┘  │
└─────────────────────────────────────┘

故障：
- 服務崩潰 → 所有請求失敗
- 模型加載 → 啟動時間長
- 內存限制 → 無法擴展
```

---

## 分層架構

### 架構演進

```
客戶端層
    ↓
[API Gateway / Load Balancer]
    ↓
服務層
    ├→ [FastAPI Service 1]
    ├→ [FastAPI Service 2]
    └→ [FastAPI Service 3]
    ↓
Worker 層
    ├→ [LangGraph Worker 1]
    ├→ [LangGraph Worker 2]
    └→ [LangGraph Worker 3]
    ↓
數據層
    ├→ [PostgreSQL]
    ├→ [Redis Cache]
    └→ [Vector DB]
```

### 實現分層

```python
# Layer 1: API 層
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uuid

app = FastAPI()

class ProcessRequest(BaseModel):
    input: str
    priority: str = "normal"

@app.post("/tasks")
async def create_task(request: ProcessRequest, bg_tasks: BackgroundTasks):
    """創建異步任務"""
    task_id = str(uuid.uuid4())
    
    # 立即返回，後台處理
    bg_tasks.add_task(process_in_worker, task_id, request.input)
    
    return {
        "task_id": task_id,
        "status": "queued"
    }

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查詢任務狀態"""
    result = redis_client.get(f"task:{task_id}")
    return json.loads(result) if result else {"status": "not_found"}

# Layer 2: Worker 層
def process_in_worker(task_id: str, user_input: str):
    """在 Worker 中處理"""
    state = RequestState(user_input=user_input)
    result = workflow.invoke(state)
    
    # 保存結果
    redis_client.setex(
        f"task:{task_id}",
        3600,  # 1 小時過期
        json.dumps({
            "status": "completed",
            "result": result.agent_results,
            "timestamp": datetime.now().isoformat()
        })
    )
```

---

## Agent 拓撲設計

### 1. 線性拓撲（Simple Chain）

```
用戶輸入 → [Agent A] → [Agent B] → [Agent C] → 輸出

優點：
- 簡單、易調試
- 各 Agent 結果清晰

缺點：
- 無法並行
- 前面失敗影響後續
```

```python
workflow = StateGraph(State)
workflow.add_node("agent_a", agent_a_node)
workflow.add_node("agent_b", agent_b_node)
workflow.add_node("agent_c", agent_c_node)

workflow.add_edge(START, "agent_a")
workflow.add_edge("agent_a", "agent_b")
workflow.add_edge("agent_b", "agent_c")
workflow.add_edge("agent_c", END)
```

### 2. 並行拓撲（Fan-out/Fan-in）

```
                ┌→ [Agent A1] ──┐
輸入 → [分配器] ├→ [Agent A2] ──┤ → [合並] → 輸出
                └→ [Agent A3] ──┘

優點：
- 充分利用資源
- 加速處理

缺點：
- 複雜度高
- 需要合併邏輯
```

```python
def distribute_work(state: State):
    """分配工作給多個 Agent"""
    return {
        "task1": process_task1(state),
        "task2": process_task2(state),
        "task3": process_task3(state)
    }

def merge_results(state: State):
    """合併結果"""
    return {
        "final": combine(state.task1, state.task2, state.task3)
    }

workflow = StateGraph(State)
workflow.add_node("distribute", distribute_work)
workflow.add_node("merge", merge_results)
workflow.add_edge(START, "distribute")
workflow.add_edge("distribute", "merge")
workflow.add_edge("merge", END)
```

### 3. 循環拓撲（Agentic Loop）

```
    ┌─────────────────────┐
    │                     ↓
輸入 → [Decision Agent] → [執行 Agent] 
    ↑                     │
    └─────────────────────┘

Agent 決定是否繼續迴圈
```

```python
def decision_agent(state: State) -> str:
    """決定是否繼續"""
    if should_continue(state):
        return "execute"
    else:
        return "end"

workflow.add_conditional_edges(
    "decide",
    decision_agent,
    {
        "execute": "execute",
        "end": END
    }
)

workflow.add_edge("execute", "decide")
```

### 4. 樹形拓撲（Tree Structure）

```
                    [根 Agent]
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
    [分類 Agent]    [驗證 Agent]    [路由 Agent]
        │               │               │
    ┌───┴───┐       ┌───┴───┐       ┌──┴───┐
    ↓       ↓       ↓       ↓       ↓      ↓
 [A1]    [A2]    [B1]    [B2]    [C1]   [C2]
```

```python
def build_tree_workflow():
    workflow = StateGraph(State)
    
    # 第一層
    workflow.add_node("root", root_agent)
    workflow.add_edge(START, "root")
    
    # 第二層
    workflow.add_node("classify", classify_agent)
    workflow.add_node("validate", validate_agent)
    workflow.add_node("route", route_agent)
    
    # 連接
    workflow.add_edge("root", "classify")
    workflow.add_edge("root", "validate")
    workflow.add_edge("root", "route")
    
    # 第三層...
    return workflow.compile()
```

---

## 數據流架構

### 狀態管理模式

```python
from typing import Annotated
from dataclasses import dataclass, field

@dataclass
class DistributedState:
    """分佈式狀態設計"""
    # 请求信息（不變）
    request_id: str
    user_id: str
    created_at: str
    
    # 处理中間狀態（易變）
    current_agent: str
    processing_history: list[dict] = field(default_factory=list)
    
    # 結果（最終）
    results: dict = field(default_factory=dict)
    
    # 元數據
    metadata: dict = field(default_factory=dict)

# 狀態分區策略
# 用於不同的 Worker 處理
def partition_state(state: DistributedState) -> dict:
    """分割狀態以支持分佈式處理"""
    return {
        "immutable": {
            "request_id": state.request_id,
            "user_id": state.user_id,
        },
        "mutable": {
            "current_agent": state.current_agent,
            "processing_history": state.processing_history,
        },
        "results": state.results
    }
```

### 數據持久化模式

```python
from sqlalchemy import create_engine, Column, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class WorkflowExecution(Base):
    """工作流執行記錄"""
    __tablename__ = "workflow_executions"
    
    execution_id = Column(String, primary_key=True)
    request_id = Column(String)
    current_state = Column(JSON)  # 序列化的 State
    step_history = Column(JSON)   # 每個步驟的結果
    status = Column(String)        # queued, running, completed, failed
    created_at = Column(String)
    updated_at = Column(String)

# 保存進度
def save_checkpoint(execution_id: str, state: DistributedState):
    """保存檢查點"""
    session = SessionLocal()
    
    execution = session.query(WorkflowExecution).filter(
        WorkflowExecution.execution_id == execution_id
    ).first()
    
    if execution:
        execution.current_state = state.dict()
        execution.updated_at = datetime.now().isoformat()
        session.commit()

# 恢復進度
def restore_from_checkpoint(execution_id: str) -> DistributedState:
    """從檢查點恢復"""
    session = SessionLocal()
    execution = session.query(WorkflowExecution).filter(
        WorkflowExecution.execution_id == execution_id
    ).first()
    
    if execution:
        return DistributedState(**execution.current_state)
    return None
```

---

## 錯誤恢復架構

### 重試策略

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class ResilientAgent:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def execute(self, state: State) -> State:
        """自動重試，指數退避"""
        try:
            return self.process(state)
        except Exception as e:
            state.errors.append({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            raise
```

### 降級策略

```python
def fallback_agent(state: State) -> State:
    """降級到簡化版本"""
    try:
        return full_featured_agent(state)
    except TimeoutError:
        # 降級到快速版本
        return fast_fallback_agent(state)
    except Exception:
        # 最後降級到緩存結果
        return use_cached_result(state)
```

---

## 監控和可觀測性架構

### 嵌入式監控

```python
from datetime import datetime
import logging

class ObservableWorkflow:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def instrument_node(self, node_name: str):
        """為節點添加監控"""
        def wrapper(func):
            def inner(state):
                start_time = datetime.now()
                
                try:
                    result = func(state)
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    self.logger.info(f"Node {node_name} completed", extra={
                        "node": node_name,
                        "duration_ms": duration * 1000,
                        "status": "success"
                    })
                    
                    return result
                except Exception as e:
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    self.logger.error(f"Node {node_name} failed", extra={
                        "node": node_name,
                        "duration_ms": duration * 1000,
                        "error": str(e),
                        "status": "failed"
                    })
                    raise
            
            return inner
        return wrapper

# 使用
observable = ObservableWorkflow()

@observable.instrument_node("analysis")
def analysis_node(state: State) -> State:
    return state
```

### 指標收集

```python
from prometheus_client import Counter, Histogram, Gauge

# 定義指標
workflow_executions = Counter(
    'workflow_executions_total',
    'Total workflow executions',
    ['status']
)

workflow_duration = Histogram(
    'workflow_duration_seconds',
    'Workflow duration'
)

active_workflows = Gauge(
    'active_workflows',
    'Active workflows'
)

# 記錄指標
def track_workflow(workflow_func):
    def wrapper(*args, **kwargs):
        active_workflows.inc()
        start = datetime.now()
        
        try:
            result = workflow_func(*args, **kwargs)
            workflow_executions.labels(status='success').inc()
            return result
        except Exception as e:
            workflow_executions.labels(status='failure').inc()
            raise
        finally:
            duration = (datetime.now() - start).total_seconds()
            workflow_duration.observe(duration)
            active_workflows.dec()
    
    return wrapper
```

---

## 架構選擇指南

| 場景 | 架構推薦 | 原因 |
|------|--------|------|
| MVP / 原型 | 單體 | 快速驗證 |
| 低流量應用 | 單體 + 緩存 | 簡單可靠 |
| 中等流量 | 分層 | 平衡複雜度和性能 |
| 高流量 | 微服務 | 獨立擴展 |
| 複雜工作流 | 樹形/循環拓撲 | 滿足業務邏輯 |

---

## 總結

設計 LangGraph AI 後端的關鍵原則：

1. **分層**：API 層、服務層、Worker 層、數據層
2. **Agent 拓撲**：根據業務邏輯選擇合適的結構
3. **狀態管理**：清晰的狀態定義和持久化
4. **容錯**：重試、降級、熔斷
5. **可觀測**：完整的日誌、指標、追蹤

好的架構設計能讓系統在流量增長時平穩擴展，故障時快速恢復。
