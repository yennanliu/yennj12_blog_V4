---
title: "LangGraph + AI 後端實戰：構建智能客服工單處理系統"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "LangGraph", "backend"]
tags: ["LangGraph", "LangChain", "AI", "客服系統", "工作流", "多 Agent", "生產級應用"]
summary: "詳細講解如何使用 LangGraph 和 AI 構建生產級的智能客服工單處理系統，涵蓋架構設計、Agent 定義、狀態管理、錯誤處理和實際案例，幫助你快速上線 AI 驅動的客服系統。"
readTime: "45 min"
---

客服工單處理是企業運營中的關鍵環節：需要快速分類、智能路由、實時回應和全程追蹤。傳統方案依賴人工，效率低、成本高。而 LangGraph 作為新一代 Agent 編排框架，使得我們可以構建**可預測、可追蹤、可控制**的 AI 客服系統。本文詳細介紹如何用 LangGraph 打造生產級的智能工單系統。

---

## 系統架構設計

### 整體架構

```
用戶提交工單
    ↓
[工單接收服務]
    ↓
[LangGraph 工作流引擎]
    ├→ [分類 Agent]        - 識別工單類型（技術問題、賬戶、計費等）
    ├→ [優先級 Agent]      - 評估緊急程度
    ├→ [路由 Agent]        - 決定分配給哪個部門
    ├→ [回應 Agent]        - 生成初始回覆
    └→ [質量檢查 Agent]    - 驗證回應質量
    ↓
[存儲和通知]
```

### 工單生命週期

```
工單狀態流：

┌─────────────┐
│  新建        │ (open)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  分類中      │ (classifying)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  等待分配    │ (assigned)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  処理中      │ (in_progress)
└──────┬──────┘
       │
       ├→ ┌─────────────┐
       │  │  已解決      │ (resolved)
       │  └─────────────┘
       │
       └→ ┌─────────────┐
          │  已關閉      │ (closed)
          └─────────────┘

全程可追蹤
```

---

## LangGraph 核心實現

### 1. 定義狀態（State）

```python
from typing import Annotated, Literal
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class TicketState:
    """工單狀態模型"""
    # 基本信息
    ticket_id: str
    user_id: str
    created_at: datetime
    subject: str
    description: str
    
    # 分類結果
    category: Literal[
        "technical", "billing", "account", 
        "feature_request", "bug_report", "other"
    ] = None
    category_confidence: float = 0.0
    
    # 優先級
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    urgency_score: float = 0.0
    
    # 路由信息
    assigned_department: str = None
    assigned_agent_id: str = None
    
    # 對話歷史
    messages: list[dict] = field(default_factory=list)
    
    # 回應信息
    response: str = None
    response_quality_score: float = 0.0
    
    # 狀態追蹤
    status: str = "open"
    current_node: str = None
    processing_history: list[dict] = field(default_factory=list)
    
    # 錯誤處理
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
```

### 2. 定義 Agent 節點

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
import json

class TicketAgents:
    def __init__(self):
        self.model = ChatAnthropic(model="claude-3-5-sonnet-20241022")
    
    # Agent 1: 分類 Agent
    def classify_agent(self, state: TicketState) -> TicketState:
        """識別工單類型和關鍵信息"""
        
        prompt = ChatPromptTemplate.from_template("""
        分析以下客服工單，提取關鍵信息和分類。
        
        工單主題：{subject}
        工單描述：{description}
        
        請以 JSON 格式返回：
        {{
            "category": "technical|billing|account|feature_request|bug_report|other",
            "confidence": 0.0-1.0,
            "key_issues": ["issue1", "issue2"],
            "urgency_signals": ["signal1", "signal2"],
            "extraction": {{
                "affected_product": "...",
                "error_message": "...",
                "account_related": true/false,
                "payment_related": true/false
            }}
        }}
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "subject": state.subject,
            "description": state.description
        })
        
        # 解析回應
        result = json.loads(response.content)
        state.category = result["category"]
        state.category_confidence = result["confidence"]
        state.current_node = "classify"
        
        # 記錄処理歷史
        state.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "node": "classify",
            "result": result
        })
        
        return state
    
    # Agent 2: 優先級評估 Agent
    def priority_agent(self, state: TicketState) -> TicketState:
        """評估工單的優先級"""
        
        prompt = ChatPromptTemplate.from_template("""
        基於以下信息評估工單的優先級：
        
        類別：{category}
        主題：{subject}
        描述：{description}
        
        評估因素：
        1. 系統中斷？(critical)
        2. 用戶無法訪問？(high)
        3. 功能受限？(medium)
        4. 功能請求/建議？(low)
        
        返回 JSON：
        {{
            "priority": "low|medium|high|critical",
            "urgency_score": 0.0-1.0,
            "reasoning": "...",
            "sla_hours": 24|12|4|1
        }}
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "category": state.category,
            "subject": state.subject,
            "description": state.description
        })
        
        result = json.loads(response.content)
        state.priority = result["priority"]
        state.urgency_score = result["urgency_score"]
        state.current_node = "priority"
        
        state.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "node": "priority",
            "result": result
        })
        
        return state
    
    # Agent 3: 路由 Agent
    def routing_agent(self, state: TicketState) -> TicketState:
        """決定工單應該分配給哪個部門"""
        
        # 部門配置
        departments = {
            "technical": {
                "name": "技術支持部",
                "skills": ["api", "integration", "performance"],
                "avg_response_time": 2,
                "available_agents": 5
            },
            "billing": {
                "name": "計費部",
                "skills": ["invoicing", "payment", "refund"],
                "avg_response_time": 4,
                "available_agents": 3
            },
            "account": {
                "name": "賬戶管理部",
                "skills": ["login", "profile", "security"],
                "avg_response_time": 1,
                "available_agents": 4
            }
        }
        
        prompt = ChatPromptTemplate.from_template("""
        根據工單的類別和優先級，決定分配給哪個部門。
        
        類別：{category}
        優先級：{priority}
        部門信息：{departments_info}
        
        返回 JSON：
        {{
            "assigned_department": "technical|billing|account",
            "reasoning": "...",
            "estimated_wait_time": "X minutes",
            "fallback_department": "..."
        }}
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "category": state.category,
            "priority": state.priority,
            "departments_info": json.dumps(departments, ensure_ascii=False)
        })
        
        result = json.loads(response.content)
        state.assigned_department = result["assigned_department"]
        state.current_node = "routing"
        
        state.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "node": "routing",
            "result": result
        })
        
        return state
    
    # Agent 4: 回應生成 Agent
    def response_agent(self, state: TicketState) -> TicketState:
        """根據工單類型生成初始回覆"""
        
        prompt = ChatPromptTemplate.from_template("""
        根據工單信息生成專業的初始回覆。回覆應該：
        1. 感謝用戶報告問題
        2. 確認已收到工單
        3. 解釋接下來的步驟
        4. 如果可能，提供初步解決方案
        
        類別：{category}
        優先級：{priority}
        主題：{subject}
        描述：{description}
        部門：{department}
        
        生成專業、友好的客服回覆（中文，150-300 字）：
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "category": state.category,
            "priority": state.priority,
            "subject": state.subject,
            "description": state.description,
            "department": state.assigned_department
        })
        
        state.response = response.content
        state.current_node = "response_generation"
        
        state.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "node": "response_generation",
            "response": state.response
        })
        
        return state
    
    # Agent 5: 質量檢查 Agent
    def quality_check_agent(self, state: TicketState) -> TicketState:
        """驗證回應質量"""
        
        prompt = ChatPromptTemplate.from_template("""
        評估以下客服回覆的質量：
        
        工單：{subject}
        回覆：{response}
        
        評估維度：
        1. 專業性 (0-1)
        2. 清晰性 (0-1)
        3. 完整性 (0-1)
        4. 友好性 (0-1)
        5. 相關性 (0-1)
        
        返回 JSON：
        {{
            "overall_score": 0.0-1.0,
            "scores": {{
                "professionalism": 0.0-1.0,
                "clarity": 0.0-1.0,
                "completeness": 0.0-1.0,
                "friendliness": 0.0-1.0,
                "relevance": 0.0-1.0
            }},
            "issues": ["issue1", "issue2"],
            "recommendations": ["fix1", "fix2"],
            "approved": true/false
        }}
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "subject": state.subject,
            "response": state.response
        })
        
        result = json.loads(response.content)
        state.response_quality_score = result["overall_score"]
        state.current_node = "quality_check"
        
        # 如果質量不符合要求，生成改進建議
        if not result["approved"]:
            state.errors.append(f"質量檢查未通過：{result['issues']}")
            return state
        
        state.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "node": "quality_check",
            "score": state.response_quality_score,
            "approved": True
        })
        
        return state
```

### 3. 構建 LangGraph

```python
from langgraph.graph import StateGraph, END
from langgraph.graph.graph import START

def build_ticket_workflow():
    """構建工單處理工作流"""
    
    workflow = StateGraph(TicketState)
    agents = TicketAgents()
    
    # 添加節點
    workflow.add_node("classify", agents.classify_agent)
    workflow.add_node("priority", agents.priority_agent)
    workflow.add_node("routing", agents.routing_agent)
    workflow.add_node("response_generation", agents.response_agent)
    workflow.add_node("quality_check", agents.quality_check_agent)
    
    # 添加邊（節點間的轉移）
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "priority")
    workflow.add_edge("priority", "routing")
    workflow.add_edge("routing", "response_generation")
    workflow.add_edge("response_generation", "quality_check")
    
    # 質量檢查的條件轉移
    def check_quality(state: TicketState):
        if state.response_quality_score >= 0.8:
            return "end"
        else:
            return "response_generation"  # 重新生成
    
    workflow.add_conditional_edges(
        "quality_check",
        check_quality,
        {
            "end": END,
            "response_generation": "response_generation"
        }
    )
    
    return workflow.compile()
```

---

## 運行工作流

### 執行工單處理

```python
# 初始化工作流
ticket_processor = build_ticket_workflow()

# 創建新工單
new_ticket = TicketState(
    ticket_id="TKT-2024-001",
    user_id="user_123",
    created_at=datetime.now(),
    subject="API 認證失敗導致集成中斷",
    description="""
    我們的應用無法連接到您的 API。
    錯誤信息：401 Unauthorized
    這發生在上午 10:00 UTC，影響了所有用戶。
    """
)

# 執行工作流
print("開始處理工單...")
result = ticket_processor.invoke(new_ticket)

# 查看結果
print(f"工單 ID: {result.ticket_id}")
print(f"分類: {result.category} (置信度: {result.category_confidence:.2%})")
print(f"優先級: {result.priority}")
print(f"分配部門: {result.assigned_department}")
print(f"回應質量分數: {result.response_quality_score:.2f}")
print(f"生成的回覆:\n{result.response}")
print(f"\n処理歷史:")
for entry in result.processing_history:
    print(f"  - {entry['node']}: {entry['timestamp']}")
```

---

## 高級特性

### 1. 上下文感知的多輪對話

```python
def conversation_agent(self, state: TicketState) -> TicketState:
    """支持多輪對話的 Agent"""
    
    # 構建對話歷史
    history = "\n".join([
        f"{msg['role']}: {msg['content']}" 
        for msg in state.messages[-5:]  # 最近 5 條消息
    ])
    
    prompt = ChatPromptTemplate.from_template("""
    你是一個客服代理。基於以下工單歷史和對話，提供幫助。
    
    工單背景：
    - 類別：{category}
    - 優先級：{priority}
    
    對話歷史：
    {history}
    
    用戶最新消息：{user_message}
    
    生成有幫助的回覆：
    """)
    
    chain = prompt | self.model
    response = chain.invoke({
        "category": state.category,
        "priority": state.priority,
        "history": history,
        "user_message": state.messages[-1]["content"]
    })
    
    # 添加到消息歷史
    state.messages.append({
        "role": "assistant",
        "content": response.content,
        "timestamp": datetime.now().isoformat()
    })
    
    return state
```

### 2. 錯誤恢復和重試

```python
def add_error_handling(workflow):
    """為工作流添加錯誤處理機制"""
    
    def handle_error(state: TicketState, error: Exception):
        state.errors.append(str(error))
        state.retry_count += 1
        
        if state.retry_count >= state.max_retries:
            state.status = "escalated"
            # 升級給人工客服
            return "escalate_to_human"
        else:
            # 重試
            return f"retry_{state.current_node}"
    
    return workflow
```

### 3. 實時監控和告警

```python
def monitor_workflow(state: TicketState):
    """實時監控工作流狀態"""
    
    metrics = {
        "ticket_id": state.ticket_id,
        "status": state.status,
        "processing_time": calculate_processing_time(state),
        "quality_score": state.response_quality_score,
        "retry_count": state.retry_count,
        "error_count": len(state.errors)
    }
    
    # 發送到監控系統
    send_to_monitoring_system(metrics)
    
    # 告警規則
    if state.retry_count >= 2:
        alert(f"工單 {state.ticket_id} 重試次數過多")
    
    if state.response_quality_score < 0.7:
        alert(f"工單 {state.ticket_id} 回應質量低")
```

---

## 生產部署

### Docker 容器化

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### FastAPI 服務包裝

```python
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI()
ticket_processor = build_ticket_workflow()

class TicketRequest(BaseModel):
    user_id: str
    subject: str
    description: str

@app.post("/tickets")
async def create_ticket(request: TicketRequest, background_tasks: BackgroundTasks):
    """創建新工單"""
    
    ticket = TicketState(
        ticket_id=generate_ticket_id(),
        user_id=request.user_id,
        created_at=datetime.now(),
        subject=request.subject,
        description=request.description
    )
    
    # 後台處理工單
    background_tasks.add_task(process_ticket, ticket)
    
    return {"ticket_id": ticket.ticket_id, "status": "accepted"}

async def process_ticket(ticket: TicketState):
    """處理工單"""
    result = ticket_processor.invoke(ticket)
    save_to_database(result)
    notify_user(result)
```

---

## 性能指標

| 指標 | 目標值 | 實現方式 |
|------|-------|--------|
| 平均響應時間 | <5 秒 | 並行處理，快速模型 |
| 工單分類準確率 | >95% | 微調模型，人工審查 |
| 首次解決率 | >70% | 知識庫集成，持續優化 |
| 質量滿意度 | >4.5/5 | 質量檢查 Agent，人工評審 |
| 成本 / 工單 | <$0.1 | 批量處理，快速模型 |

---

## 總結

使用 LangGraph 構建 AI 客服系統的優勢：

1. **可預測性**：每個步驟可追蹤，結果可解釋
2. **可控性**：清晰的工作流，易於調試和修改
3. **可擴展性**：輕鬆添加新的 Agent 或修改邏輯
4. **成本效益**：自動化 70-80% 的工單，大幅降低成本
5. **用戶體驗**：快速回應，減少等待時間

LangGraph 讓 AI 驅動的客服系統成為可能，同時保持人類的監督和控制。
