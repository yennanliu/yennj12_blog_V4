---
title: "AI Forward Deployed Engineer 必備技能指南（二）：多智慧體系統與框架實戰"
date: 2026-05-26T16:55:10+09:00
draft: false
weight: 2
description: "深入探討多智慧體系統架構設計，包含 LangGraph、CrewAI 框架實作，以及 Model Context Protocol (MCP) 的企業級應用"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Multi-Agent", "LangGraph", "CrewAI", "MCP", "Agent Framework", "cheatsheet"]
authors: ["yen"]
readTime: "15 min"
---

## 前言

多智慧體系統是現代 AI 應用的重要發展方向，能夠處理複雜的企業級任務。作為 AI FDE，掌握多智慧體框架的設計與實作是核心技能之一。本文將深入探討 LangGraph、CrewAI 等主流框架，以及 Model Context Protocol (MCP) 的實際應用。

## 1. 多智慧體系統核心概念

### 基礎架構原理

**Agent 核心組件：**
- **感知器 (Perception)**：接收與理解環境信息
- **決策器 (Decision Making)**：基於目標與狀態規劃行動
- **執行器 (Action)**：與環境互動執行任務
- **記憶體 (Memory)**：儲存狀態、經驗與知識

**協作模式：**
```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any

class CoordinationPattern(Enum):
    SEQUENTIAL = "sequential"      # 順序執行
    PARALLEL = "parallel"         # 並行執行
    HIERARCHICAL = "hierarchical" # 階層式管理
    COLLABORATIVE = "collaborative" # 協作式決策

@dataclass
class AgentTask:
    task_id: str
    description: str
    agent_id: str
    dependencies: List[str]
    priority: int
    metadata: Dict[str, Any]

class MultiAgentOrchestrator:
    def __init__(self, coordination_pattern: CoordinationPattern):
        self.pattern = coordination_pattern
        self.agents = {}
        self.task_queue = []
        
    def execute_workflow(self, tasks: List[AgentTask]):
        if self.pattern == CoordinationPattern.SEQUENTIAL:
            return self._execute_sequential(tasks)
        elif self.pattern == CoordinationPattern.PARALLEL:
            return self._execute_parallel(tasks)
        # 其他模式實作...
```

## 2. LangGraph 框架深度實作

### 狀態圖設計架構

**核心概念實作：**
```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    current_task: str
    completed_tasks: Annotated[list, operator.add]
    context: dict
    iteration_count: int

def create_research_workflow():
    workflow = StateGraph(AgentState)
    
    # 定義節點
    workflow.add_node("planner", planning_agent)
    workflow.add_node("researcher", research_agent)
    workflow.add_node("analyzer", analysis_agent)
    workflow.add_node("synthesizer", synthesis_agent)
    workflow.add_node("tools", ToolNode(research_tools))
    
    # 定義邊與條件
    workflow.set_entry_point("planner")
    
    workflow.add_conditional_edges(
        "planner",
        should_continue,
        {
            "continue": "researcher",
            "end": END
        }
    )
    
    workflow.add_edge("researcher", "tools")
    workflow.add_edge("tools", "analyzer")
    workflow.add_edge("analyzer", "synthesizer")
    workflow.add_edge("synthesizer", "planner")
    
    return workflow.compile()

def planning_agent(state: AgentState):
    """規劃代理：分解任務與分配工作"""
    messages = state["messages"]
    current_task = state.get("current_task", "")
    
    planning_prompt = f"""
    基於以下訊息規劃研究任務：
    {messages[-1]["content"] if messages else ""}
    
    當前任務狀態：{current_task}
    已完成任務：{state.get("completed_tasks", [])}
    
    請分析並決定下一步行動：
    1. 如果需要更多研究，返回具體的研究計劃
    2. 如果資訊足夠，返回 "完成研究" 
    """
    
    # LLM 呼叫邏輯
    response = llm.invoke(planning_prompt)
    
    return {
        "messages": [{"role": "planner", "content": response.content}],
        "current_task": response.content,
        "iteration_count": state.get("iteration_count", 0) + 1
    }

def should_continue(state: AgentState) -> str:
    """決定工作流程是否繼續"""
    messages = state["messages"]
    iteration_count = state.get("iteration_count", 0)
    
    if iteration_count > 10:
        return "end"
    
    last_message = messages[-1]["content"] if messages else ""
    if "完成研究" in last_message or "research complete" in last_message.lower():
        return "end"
    
    return "continue"
```

### 進階功能實作

**檢查點與狀態持久化：**
```python
from langgraph.checkpoint.sqlite import SqliteSaver

# 設定檢查點保存
checkpoint_saver = SqliteSaver.from_conn_string(":memory:")

# 編譯時加入檢查點功能
app = workflow.compile(checkpointer=checkpoint_saver)

# 帶狀態恢復的執行
thread_config = {"configurable": {"thread_id": "research-session-001"}}

# 執行並自動保存狀態
result = app.invoke(
    {"messages": [{"role": "user", "content": "研究 AI 在醫療領域的應用"}]},
    config=thread_config
)

# 從檢查點恢復並繼續執行
resumed_result = app.invoke(
    {"messages": [{"role": "user", "content": "請提供更詳細的分析"}]},
    config=thread_config
)
```

**人工干預機制：**
```python
from langgraph.prebuilt import create_react_agent

def create_human_in_loop_agent():
    def human_approval_node(state: AgentState):
        last_action = state["messages"][-1]
        
        # 檢查是否需要人工確認
        if requires_approval(last_action):
            print(f"需要確認以下行動：{last_action['content']}")
            approval = input("是否繼續？ (y/n): ")
            
            if approval.lower() != 'y':
                return {
                    "messages": [{"role": "system", "content": "行動已被用戶取消"}],
                    "current_task": "awaiting_user_input"
                }
        
        return state
    
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_edge("analyzer", "human_approval")
    workflow.add_edge("human_approval", "synthesizer")

def requires_approval(action):
    """定義需要人工確認的行動類型"""
    high_risk_actions = [
        "發送郵件", "修改資料庫", "刪除檔案", 
        "執行系統指令", "進行付款操作"
    ]
    
    return any(risk_action in action["content"] for risk_action in high_risk_actions)
```

## 3. CrewAI 框架企業應用

### 團隊協作架構

**CrewAI 核心實作：**
```python
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from langchain_openai import ChatOpenAI

class DataAnalysisTool(BaseTool):
    name: str = "數據分析工具"
    description: str = "分析業務數據並產生洞察報告"
    
    def _run(self, data_query: str) -> str:
        # 實際數據分析邏輯
        analysis_result = perform_data_analysis(data_query)
        return f"數據分析結果：{analysis_result}"

class MarketResearchTool(BaseTool):
    name: str = "市場研究工具"
    description: str = "收集市場趨勢與競爭分析"
    
    def _run(self, market_segment: str) -> str:
        market_data = fetch_market_data(market_segment)
        return f"市場研究報告：{market_data}"

def create_business_intelligence_crew():
    # 初始化 LLM
    llm = ChatOpenAI(model="gpt-4")
    
    # 定義專業代理
    data_analyst = Agent(
        role="資深數據分析師",
        goal="分析業務數據並識別關鍵趨勢與機會",
        backstory="""
        您是一位擁有 10 年經驗的資深數據分析師，
        專長於商業智能與數據挖掘，能夠從複雜數據中
        提取有價值的商業洞察。
        """,
        tools=[DataAnalysisTool()],
        llm=llm,
        verbose=True
    )
    
    market_researcher = Agent(
        role="市場研究專家",
        goal="提供深度市場分析與競爭情報",
        backstory="""
        您是市場研究領域的專家，具備敏銳的市場洞察力，
        能夠識別新興趨勢並評估競爭威脅與機會。
        """,
        tools=[MarketResearchTool()],
        llm=llm,
        verbose=True
    )
    
    strategy_consultant = Agent(
        role="策略顧問",
        goal="整合分析結果並制定可執行的業務策略",
        backstory="""
        您是一位經驗豐富的策略顧問，擅長將數據洞察
        轉化為具體的業務行動計劃與投資建議。
        """,
        llm=llm,
        verbose=True
    )
    
    # 定義任務流程
    data_analysis_task = Task(
        description="""
        分析過去 12 個月的業務數據：
        1. 識別收入趨勢與季節性模式
        2. 分析客戶行為變化
        3. 評估產品效能表現
        4. 提供數據驅動的洞察
        """,
        expected_output="詳細的數據分析報告，包含關鍵指標與趨勢分析",
        agent=data_analyst
    )
    
    market_research_task = Task(
        description="""
        進行全面市場研究：
        1. 分析市場規模與成長潛力
        2. 識別主要競爭對手與其策略
        3. 評估新興技術趨勢影響
        4. 分析客戶需求變化
        """,
        expected_output="市場研究報告，包含競爭分析與機會評估",
        agent=market_researcher,
        dependencies=[data_analysis_task]
    )
    
    strategy_formulation_task = Task(
        description="""
        基於數據分析與市場研究結果制定策略：
        1. 整合所有分析結果
        2. 識別核心業務機會
        3. 制定具體行動計劃
        4. 設定關鍵績效指標 (KPI)
        """,
        expected_output="完整的業務策略文件，包含執行計劃與成功指標",
        agent=strategy_consultant,
        dependencies=[data_analysis_task, market_research_task]
    )
    
    # 組建團隊
    crew = Crew(
        agents=[data_analyst, market_researcher, strategy_consultant],
        tasks=[data_analysis_task, market_research_task, strategy_formulation_task],
        verbose=True,
        process="sequential"  # 或 "hierarchical" 用於階層式管理
    )
    
    return crew

# 執行業務智能分析
def run_business_intelligence_analysis():
    crew = create_business_intelligence_crew()
    
    result = crew.kickoff(inputs={
        "business_context": "電子商務平台",
        "analysis_period": "2024年度",
        "focus_areas": ["客戶增長", "產品優化", "市場擴張"]
    })
    
    return result
```

### 階層式代理管理

**Manager Agent 實作：**
```python
from crewai.process import Process

def create_hierarchical_crew():
    # 管理者代理
    manager = Agent(
        role="專案經理",
        goal="協調團隊工作並確保專案按時交付",
        backstory="""
        您是一位經驗豐富的專案經理，擅長團隊協調與資源分配，
        能夠識別潛在風險並制定緩解策略。
        """,
        llm=llm,
        allow_delegation=True,  # 允許委派任務
        max_delegation_depth=2  # 最大委派層級
    )
    
    # 專業執行代理
    technical_lead = Agent(
        role="技術主管",
        goal="負責技術決策與架構設計",
        backstory="您是技術團隊的領導者，負責確保技術方案的可行性。",
        llm=llm
    )
    
    quality_assurance = Agent(
        role="品質保證專員",
        goal="確保交付成果符合品質標準",
        backstory="您專注於品質控制與測試驗證。",
        llm=llm
    )
    
    crew = Crew(
        agents=[manager, technical_lead, quality_assurance],
        tasks=[project_planning_task, implementation_task, quality_review_task],
        process=Process.hierarchical,  # 階層式流程
        manager_llm=llm  # 管理者使用的 LLM
    )
    
    return crew
```

## 4. Model Context Protocol (MCP) 實作

### MCP 核心架構

**協定實作框架：**
```python
from typing import Protocol, runtime_checkable
import asyncio
import json

@runtime_checkable
class MCPServer(Protocol):
    async def handle_request(self, request: dict) -> dict:
        """處理 MCP 請求"""
        pass
    
    async def initialize(self, capabilities: dict) -> dict:
        """初始化服務器能力"""
        pass

class CustomMCPServer:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {}
        }
    
    async def handle_request(self, request: dict) -> dict:
        method = request.get("method")
        params = request.get("params", {})
        
        if method == "tools/call":
            return await self.handle_tool_call(params)
        elif method == "resources/read":
            return await self.handle_resource_read(params)
        elif method == "prompts/get":
            return await self.handle_prompt_get(params)
        else:
            return {"error": f"Unsupported method: {method}"}
    
    async def handle_tool_call(self, params: dict):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "database_query":
            return await self.execute_database_query(arguments)
        elif tool_name == "api_request":
            return await self.execute_api_request(arguments)
        
        return {"error": f"Unknown tool: {tool_name}"}
    
    async def execute_database_query(self, arguments: dict):
        """執行資料庫查詢工具"""
        query = arguments.get("query")
        
        try:
            # 實際資料庫操作
            results = await execute_sql_query(query)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"查詢結果：{json.dumps(results, ensure_ascii=False)}"
                    }
                ]
            }
        except Exception as e:
            return {"error": f"資料庫查詢失敗：{str(e)}"}
    
    def register_tool(self, name: str, description: str, schema: dict):
        """註冊新工具"""
        self.capabilities["tools"][name] = {
            "description": description,
            "inputSchema": schema
        }
```

### 企業級 MCP 整合

**多服務協調架構：**
```python
class MCPOrchestrator:
    def __init__(self):
        self.servers = {}
        self.routing_rules = {}
    
    def register_server(self, name: str, server: MCPServer, capabilities: list):
        """註冊 MCP 服務器"""
        self.servers[name] = server
        
        for capability in capabilities:
            if capability not in self.routing_rules:
                self.routing_rules[capability] = []
            self.routing_rules[capability].append(name)
    
    async def route_request(self, capability: str, request: dict):
        """智能路由請求到適當的服務器"""
        if capability not in self.routing_rules:
            return {"error": f"No server available for capability: {capability}"}
        
        # 負載均衡與故障轉移
        available_servers = self.routing_rules[capability]
        
        for server_name in available_servers:
            try:
                server = self.servers[server_name]
                result = await server.handle_request(request)
                
                if "error" not in result:
                    return result
                    
            except Exception as e:
                print(f"Server {server_name} failed: {e}")
                continue
        
        return {"error": "All servers failed to handle the request"}

# 實際使用範例
async def setup_enterprise_mcp():
    orchestrator = MCPOrchestrator()
    
    # 註冊資料庫服務器
    db_server = CustomMCPServer("database-service", "1.0.0")
    db_server.register_tool("query", "Execute SQL queries", {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL query to execute"}
        }
    })
    
    orchestrator.register_server("database", db_server, ["data_access"])
    
    # 註冊 API 服務器
    api_server = CustomMCPServer("api-service", "1.0.0")
    api_server.register_tool("http_request", "Make HTTP requests", {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "headers": {"type": "object"}
        }
    })
    
    orchestrator.register_server("api", api_server, ["external_integration"])
    
    return orchestrator
```

## 5. 生產級部署與最佳實務

### 效能監控與可觀測性

**代理效能追蹤：**
```python
import time
import logging
from functools import wraps
from typing import Dict, Any

class AgentPerformanceMonitor:
    def __init__(self):
        self.metrics = {
            "task_completion_time": {},
            "success_rate": {},
            "resource_usage": {}
        }
        
        # 設定日誌
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def monitor_agent_performance(self, agent_id: str):
        """代理效能監控裝飾器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    
                    # 記錄成功執行
                    execution_time = time.time() - start_time
                    self._record_success(agent_id, execution_time)
                    
                    self.logger.info(
                        f"Agent {agent_id} completed task in {execution_time:.2f}s"
                    )
                    
                    return result
                    
                except Exception as e:
                    # 記錄失敗
                    self._record_failure(agent_id, str(e))
                    self.logger.error(f"Agent {agent_id} failed: {e}")
                    raise
                    
            return wrapper
        return decorator
    
    def _record_success(self, agent_id: str, execution_time: float):
        """記錄成功執行指標"""
        if agent_id not in self.metrics["task_completion_time"]:
            self.metrics["task_completion_time"][agent_id] = []
        
        self.metrics["task_completion_time"][agent_id].append(execution_time)
        
    def _record_failure(self, agent_id: str, error_message: str):
        """記錄失敗案例"""
        if agent_id not in self.metrics["success_rate"]:
            self.metrics["success_rate"][agent_id] = {"success": 0, "failure": 0}
        
        self.metrics["success_rate"][agent_id]["failure"] += 1
    
    def get_performance_report(self) -> Dict[str, Any]:
        """生成效能報告"""
        report = {}
        
        for agent_id in self.metrics["task_completion_time"]:
            times = self.metrics["task_completion_time"][agent_id]
            
            if times:
                report[agent_id] = {
                    "average_completion_time": sum(times) / len(times),
                    "min_completion_time": min(times),
                    "max_completion_time": max(times),
                    "total_tasks": len(times)
                }
        
        return report

# 使用範例
monitor = AgentPerformanceMonitor()

@monitor.monitor_agent_performance("research-agent")
async def research_agent_task(query: str):
    # 代理執行邏輯
    await asyncio.sleep(1)  # 模擬處理時間
    return f"Research completed for: {query}"
```

### 錯誤處理與恢復機制

**彈性化錯誤處理：**
```python
from retry import retry
import asyncio

class RobustAgentExecutor:
    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
    
    @retry(tries=3, delay=1, backoff=2)
    async def execute_with_retry(self, agent_func, *args, **kwargs):
        """帶重試機制的代理執行"""
        try:
            return await agent_func(*args, **kwargs)
        except Exception as e:
            print(f"Agent execution failed: {e}")
            
            # 檢查是否為可恢復錯誤
            if self.is_recoverable_error(e):
                raise  # 觸發重試
            else:
                # 不可恢復錯誤，直接失敗
                raise Exception(f"Non-recoverable error: {e}")
    
    def is_recoverable_error(self, error: Exception) -> bool:
        """判斷錯誤是否可恢復"""
        recoverable_errors = [
            "timeout",
            "connection",
            "rate limit",
            "temporary",
            "503",
            "502"
        ]
        
        error_message = str(error).lower()
        return any(recoverable in error_message for recoverable in recoverable_errors)
    
    async def execute_with_fallback(self, primary_agent, fallback_agent, *args, **kwargs):
        """主要代理失敗時的後備執行"""
        try:
            return await self.execute_with_retry(primary_agent, *args, **kwargs)
        except Exception as e:
            print(f"Primary agent failed, using fallback: {e}")
            return await self.execute_with_retry(fallback_agent, *args, **kwargs)
```

## 6. 安全性與權限管理

### 代理安全框架

**權限控制系統：**
```python
from enum import Enum
from typing import Set, Dict

class Permission(Enum):
    READ_DATA = "read_data"
    WRITE_DATA = "write_data"
    EXECUTE_COMMANDS = "execute_commands"
    ACCESS_EXTERNAL_APIs = "access_external_apis"
    MANAGE_USERS = "manage_users"

class SecurityContext:
    def __init__(self, agent_id: str, permissions: Set[Permission]):
        self.agent_id = agent_id
        self.permissions = permissions
        self.session_token = self._generate_session_token()
    
    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions
    
    def _generate_session_token(self) -> str:
        import secrets
        return secrets.token_urlsafe(32)

class SecureAgentDecorator:
    def __init__(self, security_context: SecurityContext):
        self.security_context = security_context
    
    def require_permission(self, permission: Permission):
        """權限檢查裝飾器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.security_context.has_permission(permission):
                    raise PermissionError(
                        f"Agent {self.security_context.agent_id} "
                        f"lacks permission: {permission.value}"
                    )
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator

# 安全代理實作範例
class SecureDataAgent:
    def __init__(self, security_context: SecurityContext):
        self.security_context = security_context
        self.secure_decorator = SecureAgentDecorator(security_context)
    
    @SecureAgentDecorator.require_permission(Permission.READ_DATA)
    async def read_sensitive_data(self, data_id: str):
        """讀取敏感數據"""
        print(f"Reading data {data_id} with agent {self.security_context.agent_id}")
        return f"Sensitive data: {data_id}"
    
    @SecureAgentDecorator.require_permission(Permission.EXECUTE_COMMANDS)
    async def execute_system_command(self, command: str):
        """執行系統命令"""
        if self.is_safe_command(command):
            print(f"Executing command: {command}")
            return f"Command executed: {command}"
        else:
            raise SecurityError("Potentially dangerous command blocked")
    
    def is_safe_command(self, command: str) -> bool:
        """檢查命令是否安全"""
        dangerous_commands = ["rm -rf", "del", "format", "shutdown"]
        return not any(dangerous in command.lower() for dangerous in dangerous_commands)
```

## 總結

本文深入介紹了多智慧體系統的核心概念與實作：

1. **架構設計**：Agent 組件、協作模式與工作流程管理
2. **LangGraph 框架**：狀態圖設計、檢查點機制與人工干預
3. **CrewAI 企業應用**：團隊協作、階層管理與業務智能
4. **MCP 協定**：服務器實作、企業整合與多服務協調
5. **生產部署**：效能監控、錯誤處理與恢復機制
6. **安全管理**：權限控制、安全框架與風險緩解

下一篇將探討企業級 AI 整合與部署策略，包含雲端平台部署、安全性管理與數據管道架構。
