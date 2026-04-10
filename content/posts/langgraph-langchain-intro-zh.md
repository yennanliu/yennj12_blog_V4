---
title: "LangGraph + LangChain 完全入門指南：從基礎到生產"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "LangChain", "LangGraph"]
tags: ["LangChain", "LangGraph", "AI", "Agent", "工作流", "RAG", "介紹"]
summary: "全面介紹 LangChain 和 LangGraph 的核心概念、架構和實戰應用，涵蓋從簡單的 Chain 到複雜的多 Agent 工作流，幫助開發者快速掌握現代 AI 應用開發框架。"
readTime: "50 min"
---

在 AI 應用開發中，LangChain 和 LangGraph 是兩個最流行的框架：LangChain 提供組件和工具，而 LangGraph 提供編排能力。對於想要構建生產級 AI 應用的開發者來說，理解這兩個框架的區別與協作方式至關重要。本文深入講解它們的核心概念、架構和實戰應用。

---

## LangChain 基礎

### 什麼是 LangChain？

LangChain 是一個 Python 框架，用於開發由大語言模型（LLM）驅動的應用。它提供了一套標準接口和工具，使得開發者可以輕鬆構建 LLM 應用。

```
LangChain 的核心目標：
簡化 LLM 應用開發 = 模型 + 記憶 + 工具 + 流程
```

### LangChain 核心組件

#### 1. Models（模型）

```python
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

# 初始化不同的模型
claude = ChatAnthropic(model="claude-3-5-sonnet-20241022")
gpt4 = ChatOpenAI(model="gpt-4-turbo")

# 發送消息
response = claude.invoke("What is LangChain?")
print(response.content)
```

#### 2. Prompts（提示詞）

```python
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

# 簡單模板
simple_prompt = PromptTemplate.from_template(
    "告訴我關於 {topic} 的 3 個有趣的事實。"
)

# 聊天模板（更靈活）
chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一個知識淵博的 AI 助手。"),
    ("human", "{user_input}"),
    ("assistant", "我會幫你..."),
    ("human", "{follow_up}")
])

# 使用模板
formatted = chat_prompt.format(
    user_input="什麼是 LangChain?",
    follow_up="有什麼優勢?"
)
```

#### 3. Chains（鏈）

Chain 是一系列組件的組合，按順序執行。

```python
from langchain_core.runnables import RunnableSequence

# 構建簡單的 Chain
prompt = ChatPromptTemplate.from_template("解釋 {concept}")
model = ChatAnthropic()
output_parser = StrOutputParser()

chain = prompt | model | output_parser

# 執行
result = chain.invoke({"concept": "LangChain"})
print(result)

# 更複雜的 Chain（多步）
from langchain_core.runnables import RunnableParallel

parallel_chain = RunnableParallel(
    summary=prompt | model,
    examples=ChatPromptTemplate.from_template(
        "給出 {concept} 的 3 個例子"
    ) | model
)

result = parallel_chain.invoke({"concept": "LangChain"})
print(f"總結: {result['summary']}")
print(f"例子: {result['examples']}")
```

#### 4. Memory（記憶）

```python
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory

# 簡單的緩衝記憶
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# 添加對話
memory.chat_memory.add_user_message("你好")
memory.chat_memory.add_ai_message("你好！有什麼我可以幫助的嗎？")

# 獲取記憶
print(memory.load_memory_variables({}))

# 基於摘要的記憶（適合長對話）
summary_memory = ConversationSummaryMemory(
    llm=model,
    buffer="最近對話摘要..."
)
```

#### 5. Tools（工具）

```python
from langchain_core.tools import tool
from datetime import datetime

@tool
def get_current_time(timezone: str = "UTC") -> str:
    """獲取當前時間"""
    return f"當前時間 ({timezone}): {datetime.now().isoformat()}"

@tool
def search_internet(query: str) -> str:
    """搜尋互聯網"""
    return f"搜尋結果：{query}..."

@tool
def calculate(expression: str) -> str:
    """計算數學表達式"""
    return str(eval(expression))

# 工具列表
tools = [get_current_time, search_internet, calculate]

# 模型可以使用這些工具
model_with_tools = claude.bind_tools(tools)
```

#### 6. Retrievers（檢索器）

```python
from langchain_community.vectorstores import FAISS
from langchain_embeddings import OpenAIEmbeddings
from langchain_text_splitters import CharacterTextSplitter

# 準備文檔
documents = [
    {"text": "LangChain 是..."},
    {"text": "LangGraph 是..."},
    {"text": "Agents 可以..."}
]

# 分割文本
text_splitter = CharacterTextSplitter(chunk_size=1000)
splits = text_splitter.split_documents(documents)

# 創建向量存儲
embeddings = OpenAIEmbeddings()
vector_store = FAISS.from_documents(splits, embeddings)

# 創建檢索器
retriever = vector_store.as_retriever(search_type="similarity", k=3)

# 使用檢索器
relevant_docs = retriever.invoke("什麼是 LangChain?")
```

### LangChain 實戰示例：RAG（檢索增強生成）

```python
from langchain_core.runnables import RunnablePassthrough

# 構建 RAG Chain
rag_prompt = ChatPromptTemplate.from_template("""
基於以下上下文回答問題。

上下文：
{context}

問題：{question}

答案：
""")

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | rag_prompt
    | model
    | output_parser
)

# 使用
answer = rag_chain.invoke("LangChain 的優勢是什麼?")
print(answer)
```

---

## LangGraph 進階

### 什麼是 LangGraph？

LangGraph 是在 LangChain 基礎上構建的框架，用於構建**可狀態追蹤、有向無環圖（DAG）結構**的工作流。相比 Chain 的線性執行，LangGraph 提供了：

1. **狀態管理**：跨步驟保持狀態
2. **條件轉移**：根據狀態決定下一步
3. **循環和並行**：複雜的工作流邏輯
4. **可追蹤性**：每個步驟都可以記錄

```
LangChain Chain：線性管道
input → [step1] → [step2] → [step3] → output

LangGraph：複雜工作流
          ┌─→ [step2a]
input → [step1] → [路由器] → ┤
                  └─→ [step2b]
                         ↓
                      [step3]
                         ↓
                      output
```

### LangGraph 核心概念

#### 1. 定義狀態

```python
from typing import Annotated, Optional
from dataclasses import dataclass, field

@dataclass
class WorkflowState:
    """工作流狀態"""
    # 輸入
    user_input: str
    
    # 中間結果
    analysis: Optional[str] = None
    research: Optional[str] = None
    
    # 輸出
    final_response: Optional[str] = None
    
    # 追蹤信息
    steps_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
```

#### 2. 定義節點（Nodes）

```python
from langgraph.graph import StateGraph, END, START

def analysis_node(state: WorkflowState) -> WorkflowState:
    """分析節點"""
    analysis = f"分析: {state.user_input}..."
    state.analysis = analysis
    state.steps_completed.append("analysis")
    return state

def research_node(state: WorkflowState) -> WorkflowState:
    """研究節點"""
    research = f"研究: 基於 {state.analysis}"
    state.research = research
    state.steps_completed.append("research")
    return state

def synthesis_node(state: WorkflowState) -> WorkflowState:
    """合成節點"""
    final = f"最終回應: {state.analysis} + {state.research}"
    state.final_response = final
    state.steps_completed.append("synthesis")
    return state
```

#### 3. 定義邊（Edges）和路由

```python
from langgraph.graph import StateGraph

# 構建圖
graph = StateGraph(WorkflowState)

# 添加節點
graph.add_node("analysis", analysis_node)
graph.add_node("research", research_node)
graph.add_node("synthesis", synthesis_node)

# 添加邊（簡單連接）
graph.add_edge(START, "analysis")
graph.add_edge("analysis", "research")
graph.add_edge("research", "synthesis")
graph.add_edge("synthesis", END)

# 添加條件邊（路由）
def should_do_research(state: WorkflowState) -> str:
    """決定是否進行研究"""
    if len(state.analysis) > 10:
        return "research"
    else:
        return "synthesis"

graph.add_conditional_edges(
    "analysis",
    should_do_research,
    {
        "research": "research",
        "synthesis": "synthesis"
    }
)

# 編譯圖
workflow = graph.compile()
```

#### 4. 帶有工具的 Agent 工作流

```python
from langgraph.graph import StateGraph, END, START
from langgraph.types import Command
import json

@dataclass
class AgentState:
    messages: list[dict]
    tools_used: list[str] = field(default_factory=list)
    final_answer: Optional[str] = None

def agent_node(state: AgentState) -> AgentState:
    """Agent 決策節點"""
    # 調用模型
    response = model.invoke(state.messages)
    
    # 檢查是否調用了工具
    if hasattr(response, 'tool_calls') and response.tool_calls:
        # 執行工具
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            
            # 根據工具名執行
            if tool_name == "search":
                result = search_internet(tool_args['query'])
            elif tool_name == "calculate":
                result = calculate(tool_args['expression'])
            
            # 添加結果到消息
            state.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls
            })
            state.messages.append({
                "role": "tool",
                "tool_use_id": tool_call['id'],
                "content": result
            })
            state.tools_used.append(tool_name)
    else:
        # 模型給出最終答案
        state.final_answer = response.content
    
    return state

def should_continue(state: AgentState) -> str:
    """決定是否繼續或結束"""
    if state.final_answer:
        return "end"
    else:
        return "agent"

# 構建 Agent 工作流
agent_graph = StateGraph(AgentState)
agent_graph.add_node("agent", agent_node)
agent_graph.add_edge(START, "agent")
agent_graph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "agent": "agent",
        "end": END
    }
)

agent_workflow = agent_graph.compile()
```

### LangGraph 高級特性

#### 1. 子圖（Sub-graphs）

```python
# 創建一個子工作流
def create_analysis_subgraph():
    subgraph = StateGraph(AnalysisState)
    subgraph.add_node("parse", parse_node)
    subgraph.add_node("extract", extract_node)
    subgraph.add_edge(START, "parse")
    subgraph.add_edge("parse", "extract")
    subgraph.add_edge("extract", END)
    return subgraph.compile()

# 在主圖中使用子圖
main_graph.add_node("analysis", create_analysis_subgraph())
```

#### 2. 持久化和檢查點

```python
from langgraph.checkpoint import MemorySaver

# 創建帶檢查點的工作流
checkpointer = MemorySaver()
workflow = graph.compile(checkpointer=checkpointer)

# 執行並保存狀態
config = {"configurable": {"thread_id": "user_123"}}
result = workflow.invoke(initial_state, config=config)

# 稍後恢復狀態
result = workflow.invoke(updated_input, config=config)
```

#### 3. 流式執行

```python
# 流式輸出每個節點的結果
for output in workflow.stream(initial_state):
    node_name, result = next(iter(output.items()))
    print(f"節點 {node_name} 完成")
    print(f"  結果: {result}")
```

---

## LangChain + LangGraph 實戰：多 Agent 系統

### 場景：研究和報告生成系統

```python
from dataclasses import dataclass, field
from typing import Annotated, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnablePassthrough

@dataclass
class ResearchState:
    """研究工作流狀態"""
    topic: str
    research_queries: list[str] = field(default_factory=list)
    research_results: dict = field(default_factory=dict)
    analysis: Optional[str] = None
    report: Optional[str] = None
    quality_score: float = 0.0

class ResearchAgents:
    def __init__(self):
        self.model = ChatAnthropic(model="claude-3-5-sonnet-20241022")
        self.research_tool = self._create_research_tool()
    
    def _create_research_tool(self):
        @tool
        def search_knowledge(query: str) -> str:
            """搜尋知識庫"""
            return f"搜尋 '{query}' 的結果..."
        return search_knowledge
    
    # Agent 1: 查詢規劃 Agent
    def query_planner(self, state: ResearchState) -> ResearchState:
        """根據主題規劃搜尋查詢"""
        prompt = ChatPromptTemplate.from_template("""
        為以下主題規劃 5 個搜尋查詢：
        主題: {topic}
        
        返回 JSON 列表：
        ["查詢1", "查詢2", ...]
        """)
        
        chain = prompt | self.model
        response = chain.invoke({"topic": state.topic})
        
        import json
        queries = json.loads(response.content)
        state.research_queries = queries
        return state
    
    # Agent 2: 研究 Agent
    def researcher(self, state: ResearchState) -> ResearchState:
        """執行搜尋和收集信息"""
        for query in state.research_queries:
            result = self.research_tool.invoke(query)
            state.research_results[query] = result
        return state
    
    # Agent 3: 分析 Agent
    def analyzer(self, state: ResearchState) -> ResearchState:
        """分析收集的信息"""
        prompt = ChatPromptTemplate.from_template("""
        基於以下研究結果分析主題：
        
        主題: {topic}
        研究結果: {results}
        
        提供深入的分析：
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "topic": state.topic,
            "results": str(state.research_results)
        })
        
        state.analysis = response.content
        return state
    
    # Agent 4: 報告生成 Agent
    def report_generator(self, state: ResearchState) -> ResearchState:
        """生成最終報告"""
        prompt = ChatPromptTemplate.from_template("""
        基於以下信息生成專業報告：
        
        主題: {topic}
        分析: {analysis}
        
        格式：
        1. 執行摘要
        2. 背景
        3. 主要發現
        4. 建議
        5. 結論
        """)
        
        chain = prompt | self.model
        response = chain.invoke({
            "topic": state.topic,
            "analysis": state.analysis
        })
        
        state.report = response.content
        return state
    
    # Agent 5: 質量檢查 Agent
    def quality_checker(self, state: ResearchState) -> ResearchState:
        """檢查報告質量"""
        prompt = ChatPromptTemplate.from_template("""
        評估報告質量 (0-1)：
        
        報告：{report}
        
        評估維度：
        1. 完整性
        2. 準確性
        3. 清晰性
        4. 相關性
        
        返回平均分數：
        """)
        
        chain = prompt | self.model
        response = chain.invoke({"report": state.report})
        
        score = float(response.content.strip())
        state.quality_score = score
        return state

# 構建多 Agent 工作流
def build_research_workflow():
    workflow = StateGraph(ResearchState)
    agents = ResearchAgents()
    
    # 添加節點
    workflow.add_node("plan", agents.query_planner)
    workflow.add_node("research", agents.researcher)
    workflow.add_node("analyze", agents.analyzer)
    workflow.add_node("report", agents.report_generator)
    workflow.add_node("quality_check", agents.quality_checker)
    
    # 連接節點
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "research")
    workflow.add_edge("research", "analyze")
    workflow.add_edge("analyze", "report")
    workflow.add_edge("report", "quality_check")
    
    # 質量檢查的條件轉移
    def check_quality(state: ResearchState):
        return "end" if state.quality_score >= 0.8 else "analyze"
    
    workflow.add_conditional_edges(
        "quality_check",
        check_quality,
        {"end": END, "analyze": "analyze"}
    )
    
    return workflow.compile()

# 使用
research_workflow = build_research_workflow()
initial_state = ResearchState(topic="人工智能的未來")
result = research_workflow.invoke(initial_state)

print(f"主題: {result.topic}")
print(f"質量分數: {result.quality_score:.2f}")
print(f"報告:\n{result.report}")
```

---

## 最佳實踐

### 1. 錯誤處理和恢復

```python
from langgraph.graph import StateGraph

try:
    result = workflow.invoke(state)
except Exception as e:
    # 記錄錯誤
    state.errors.append(str(e))
    
    # 重試或升級
    if should_retry(e):
        result = workflow.invoke(state)
    else:
        escalate_to_human(state)
```

### 2. 性能優化

```python
# 並行執行節點
parallel_graph = StateGraph(State)
parallel_graph.add_node("task1", node1)
parallel_graph.add_node("task2", node2)
parallel_graph.add_node("task3", node3)

# 所有任務同時執行
parallel_graph.add_edge(START, "task1")
parallel_graph.add_edge(START, "task2")
parallel_graph.add_edge(START, "task3")
parallel_graph.add_edge("task1", "combine")
parallel_graph.add_edge("task2", "combine")
parallel_graph.add_edge("task3", "combine")
```

### 3. 監控和日誌

```python
def log_node_execution(state: State, node_name: str):
    """記錄節點執行信息"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "node": node_name,
        "state_keys": list(state.__dict__.keys()),
        "errors": getattr(state, 'errors', [])
    }
    logger.info(json.dumps(log_entry))
```

---

## 總結

| 方面 | LangChain | LangGraph |
|------|----------|----------|
| 用途 | 構建 LLM 應用組件 | 編排複雜工作流 |
| 結構 | 線性 Chain | DAG 圖結構 |
| 狀態管理 | 隱式 | 顯式 |
| 適用場景 | 簡單應用 | 複雜、多步驟應用 |
| 學習曲線 | 平緩 | 中等 |

## 何時使用

- **只用 LangChain**：簡單的 QA、摘要、翻譯
- **LangChain + LangGraph**：多步驟工作流、多 Agent 系統、複雜決策邏輯

兩個框架的結合提供了強大的能力，是構建現代 AI 應用的最佳選擇。
