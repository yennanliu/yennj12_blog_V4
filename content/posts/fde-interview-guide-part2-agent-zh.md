---
title: "FDE 面試準備指南（二）：Agent System Design"
date: 2026-05-30T10:30:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，解析 FDE 面試中 Agent 系統設計考題，包含 ReAct、Multi-Agent、LangGraph、ADK 與失控防範"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "LangGraph", "CrewAI", "ADK", "MCP", "ReAct", "Interview", "Google"]
authors: ["yen"]
readTime: "14 min"
---

> 這篇是 FDE 面試系列第二篇。  
> RAG 是知識，Agent 是行動。  
> FDE 的工作常常是兩者都要。

---

## 為什麼 Agent 幾乎必考

JD 裡通常明寫：

- LangGraph
- CrewAI
- ADK（Google Agent Development Kit）
- ReAct
- Hierarchical Delegation
- MCP（Model Context Protocol）

這些詞出現在 JD 不是意外。FDE 的日常工作就是幫客戶設計和部署這些東西。

---

## 什麼是 Agent

用一句話說：

> **Agent = LLM + Tools + Loop**

LLM 負責決策，Tools 負責執行，Loop 讓它可以反覆思考直到完成任務。

最經典的 Loop 模式叫 **ReAct**：

```
Thought: 我需要查一下這個客戶的訂單狀態
Action: call_tool("get_order", customer_id="C123")
Observation: 訂單 #456 目前在「出貨中」狀態
Thought: 我知道答案了，可以回覆用戶
Action: respond("您的訂單 #456 目前正在出貨，預計明天到達")
```

**Reason（思考）→ Act（行動）→ Observe（觀察）→ 再思考**，這就是 ReAct。

---

## 系統設計考題：AI Customer Support Agent

這是面試最常出現的設計題。

面試官可能問：

> *「設計一個 AI 客服系統，能夠查訂單、回答 FAQ、轉接人工。」*

### 第一步：畫架構圖

```
用戶
 ↓
API Gateway（身份驗證、Rate Limiting）
 ↓
Orchestrator Agent（主控）
 ↓ ↓ ↓
Tool Router
 ├── CRM Tool（查訂單、客戶資料）
 ├── Knowledge Base Tool（RAG，查 FAQ / 政策文件）
 ├── Escalation Tool（轉接人工）
 └── Ticketing Tool（建立工單）
 ↓
LLM（Claude / Gemini）
 ↓
Response
```

### 第二步：定義每個元件的職責

**Orchestrator（主控 Agent）**

- 接收用戶輸入
- 決定呼叫哪個 Tool
- 整合 Tool 結果，生成最終回應

**Tool Router**

- 根據意圖路由到對應 Tool
- 管理 Tool 的輸入 / 輸出格式

**Knowledge Base Tool**（這是 RAG）

- 查內部文件：退款政策、產品說明、FAQ
- 回傳相關段落

**CRM Tool**

- 查訂單狀態、交易記錄
- 需要安全控管，不能讓 AI 隨意修改資料

### 第三步：用 LangGraph 實作

LangGraph 的核心概念是**狀態圖**：Agent 在不同節點之間流動，每個節點處理一件事。

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END

class SupportState(TypedDict):
    user_message: str
    intent: str              # 訂單查詢 / FAQ / 轉接
    tool_results: Annotated[list, operator.add]
    final_response: str
    escalate: bool

def classify_intent(state: SupportState) -> SupportState:
    """判斷用戶意圖"""
    # 呼叫 LLM 分類
    intent = llm_classify(state["user_message"])
    return {"intent": intent}

def query_crm(state: SupportState) -> SupportState:
    """查 CRM 訂單資料"""
    order_info = crm_tool.get_order(state["user_message"])
    return {"tool_results": [order_info]}

def query_knowledge_base(state: SupportState) -> SupportState:
    """查知識庫（RAG）"""
    relevant_docs = rag_tool.search(state["user_message"])
    return {"tool_results": [relevant_docs]}

def generate_response(state: SupportState) -> SupportState:
    """根據 Tool 結果生成回應"""
    context = "\n".join(state["tool_results"])
    response = llm_generate(context, state["user_message"])
    return {"final_response": response}

def route_by_intent(state: SupportState) -> str:
    """根據意圖決定下一個節點"""
    intent = state["intent"]
    if intent == "order_inquiry":
        return "query_crm"
    elif intent == "general_faq":
        return "query_knowledge_base"
    elif intent == "escalate":
        return "escalate"
    return "generate_response"

# 建立狀態圖
workflow = StateGraph(SupportState)
workflow.add_node("classify_intent", classify_intent)
workflow.add_node("query_crm", query_crm)
workflow.add_node("query_knowledge_base", query_knowledge_base)
workflow.add_node("generate_response", generate_response)

workflow.set_entry_point("classify_intent")
workflow.add_conditional_edges("classify_intent", route_by_intent)
workflow.add_edge("query_crm", "generate_response")
workflow.add_edge("query_knowledge_base", "generate_response")
workflow.add_edge("generate_response", END)

app = workflow.compile()
```

---

## 面試必考：什麼時候要用 Multi-Agent

這是我最愛問的判斷題。

很多人的答案是「當任務複雜的時候」。這個答案不夠好。

### 正確的判斷邏輯

**單一 Agent 就夠了，當：**

- 任務流程是線性的
- 工具少（5 個以內）
- 任務可以在一個 context window 裡完成

**需要 Multi-Agent，當：**

- 任務需要**並行**執行（不同 Agent 同時工作）
- 任務需要**專業分工**（不同角色做不同的事）
- 任務太長，單一 context window 裝不下
- 需要**相互檢查**（一個 Agent 驗證另一個 Agent 的輸出）

### 典型 Multi-Agent 架構

```
Planner（規劃師）
    ↓ 分配任務
    ├── Researcher（研究員）—— 搜集資料
    ├── Analyst（分析師）—— 分析數據
    └── Writer（撰寫者）—— 生成報告
    ↓
Reviewer（審核者）—— 檢查輸出品質
    ↓
最終輸出
```

用 CrewAI 實作：

```python
from crewai import Agent, Task, Crew

researcher = Agent(
    role="研究員",
    goal="蒐集關於{topic}的最新市場資料",
    backstory="你是一位專業的市場研究員，擅長快速找到可靠的資訊來源",
    tools=[search_tool, scraper_tool]
)

analyst = Agent(
    role="數據分析師",
    goal="分析研究員提供的資料，找出關鍵趨勢",
    backstory="你是一位資深的數據分析師，善於從大量資料中提取洞察",
    tools=[calculator_tool, chart_tool]
)

writer = Agent(
    role="報告撰寫者",
    goal="根據分析結果撰寫清晰易懂的執行摘要",
    backstory="你是一位商業寫作專家，能把複雜資訊轉化為清楚的報告"
)

research_task = Task(
    description="搜集 {topic} 的市場現況、競爭者分析",
    agent=researcher,
    expected_output="包含來源連結的市場研究報告"
)

analysis_task = Task(
    description="分析研究員的報告，找出 3 個關鍵洞察",
    agent=analyst,
    expected_output="3 個數據支撐的市場洞察",
    context=[research_task]  # 依賴 research_task 的輸出
)

write_task = Task(
    description="根據分析洞察撰寫執行摘要報告",
    agent=writer,
    expected_output="清晰易懂的執行摘要，不超過一頁",
    context=[research_task, analysis_task]
)

crew = Crew(
    agents=[researcher, analyst, writer],
    tasks=[research_task, analysis_task, write_task]
)
```

---

## 面試必考：Agent Loop 如何避免失控

這是面試官想知道你有沒有工程常識的題目。

設計 Agent 最大的風險之一：**無限循環**。

Agent 決策錯誤 → 再嘗試 → 還是錯 → 繼續嘗試 → 無限循環 → 費用爆炸。

### 四道防線

#### ① Max Iterations（迭代上限）

```python
MAX_ITERATIONS = 10

iteration = 0
while not task_complete:
    if iteration >= MAX_ITERATIONS:
        return "任務超過最大迭代次數，請人工處理"
    
    result = agent.step()
    iteration += 1
```

#### ② Timeout（時間上限）

```python
import asyncio

async def run_agent_with_timeout(agent, task, timeout_seconds=60):
    try:
        result = await asyncio.wait_for(
            agent.run(task),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        agent.stop()
        return "任務超時，已強制停止"
```

#### ③ Cost Budget（費用預算）

```python
class BudgetedAgent:
    def __init__(self, max_cost_usd: float = 1.0):
        self.max_cost = max_cost_usd
        self.current_cost = 0.0
    
    def call_llm(self, prompt: str) -> str:
        estimated_cost = estimate_cost(prompt)
        
        if self.current_cost + estimated_cost > self.max_cost:
            raise BudgetExceededError(
                f"預算已達上限 ${self.max_cost}，已使用 ${self.current_cost:.4f}"
            )
        
        response = llm.invoke(prompt)
        self.current_cost += actual_cost(response)
        return response
```

#### ④ Human Approval（人工確認）

高風險操作不讓 Agent 自己決定：

```python
HIGH_RISK_ACTIONS = [
    "delete_customer_data",
    "process_refund",
    "send_mass_email",
    "modify_pricing"
]

def execute_action(action_name: str, params: dict) -> str:
    if action_name in HIGH_RISK_ACTIONS:
        # 暫停，等待人工確認
        approval = request_human_approval(
            action=action_name,
            params=params,
            timeout=300  # 5 分鐘內沒確認就取消
        )
        if not approval.approved:
            return f"操作 {action_name} 已取消"
    
    return execute(action_name, params)
```

---

## MCP：Model Context Protocol

這是 Google / Anthropic 都在推的標準協議。

簡單說：**定義 AI 如何和外部工具溝通的規範**。

就像 HTTP 讓瀏覽器和伺服器能溝通，MCP 讓 Agent 和工具能用標準方式溝通。

```
Agent
  ↓ MCP 請求（標準格式）
MCP Server（你的 CRM / 資料庫 / API）
  ↓ MCP 回應（標準格式）
Agent
```

好處：工具只要實作 MCP Server，任何支援 MCP 的 Agent 框架都能用。

```python
# MCP Server 範例（簡化）
from mcp.server import MCPServer

server = MCPServer(name="crm-service")

@server.tool("get_customer_order")
async def get_customer_order(customer_id: str) -> dict:
    """查詢客戶訂單狀態"""
    order = await crm_db.fetch_order(customer_id)
    return {
        "order_id": order.id,
        "status": order.status,
        "estimated_delivery": order.eta
    }

@server.tool("create_support_ticket")
async def create_support_ticket(
    customer_id: str,
    issue_description: str,
    priority: str = "normal"
) -> dict:
    """建立客服工單"""
    ticket = await ticketing_system.create(
        customer_id=customer_id,
        description=issue_description,
        priority=priority
    )
    return {"ticket_id": ticket.id, "status": "created"}
```

---

## Google ADK 簡介

如果面試的是 Google 客戶相關的 FDE 職位，ADK（Agent Development Kit）可能被問到。

核心概念：

```python
from google.adk.agents import Agent
from google.adk.tools import google_search, code_execution

root_agent = Agent(
    name="enterprise_assistant",
    model="gemini-2.0-flash",
    instruction="""
    你是一位企業 AI 助理。
    你可以搜尋資訊、執行程式碼分析數據。
    回答時請保持專業，並引用資料來源。
    """,
    tools=[google_search, code_execution]
)

# ADK 內建的 Agent Loop
response = root_agent.run("分析上個季度的銷售數據趨勢")
```

ADK 和 LangGraph 的定位不同：

- **LangGraph**：給你完整控制，你自己定義每個節點和邊
- **ADK**：更高層的抽象，Gemini 原生支援，適合快速原型

---

## 面試答題框架

系統設計題的回答結構：

```
1. 釐清需求（2 分鐘）
   - 用戶是誰？
   - 最關鍵的幾個功能？
   - 有什麼特殊限制？（latency / cost / compliance）

2. 畫高層架構（5 分鐘）
   - 畫出主要元件
   - 說明每個元件的職責

3. 深入細節（10 分鐘）
   - 選一兩個最關鍵的部分深入
   - 說明 trade-off

4. 說明失敗模式（3 分鐘）
   - 這個設計最容易在哪裡出問題？
   - 怎麼偵測？怎麼恢復？
```

---

## 小結

Agent 系統設計考的不是你記了多少框架的 API，而是：

- 你知道什麼時候該用 Single Agent，什麼時候要 Multi-Agent
- 你清楚 Agent 的失控風險，而且有對策
- 你能在白板上畫出一個可以實際落地的架構

下一篇：**傳統 ML / AI 基礎知識** — FDE 面試中哪些經典 ML 知識還是必須知道的。
