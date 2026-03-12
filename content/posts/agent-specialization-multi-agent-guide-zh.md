---
title: "多 Agent Token 優化系列 pt.6：Agent 專責化實戰指南 — 打造精準高效的專家團隊"
date: 2026-03-12T22:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "multi-agent", "agent-specialization", "token-optimization", "system-design", "API"]
summary: "深入探索 Agent 專責化策略：從單一通用 Agent 到專業分工的專家團隊，涵蓋職責劃分、System Prompt 精簡、工具最小化配置、模型差異化選擇等完整實作，幫助你大幅降低 System Prompt 的 Token 消耗並提升輸出品質。"
readTime: "35 min"
---

在《多 Agent 系統的 Token 用量調優指南》中，我們介紹了 **Agent 專責化** 作為降低 System Prompt Token 消耗的核心策略。本文將深入實作層面，探討如何將臃腫的「全能 Agent」拆分為精準的「專家團隊」，讓每個 Agent 只專注於單一職責，從而大幅減少每次 API 呼叫的固定成本。

---

## 為什麼需要 Agent 專責化？

### 通用 Agent 的問題

```
通用 Agent（反模式）的 System Prompt：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  "你是一個全能 AI 助手，可以幫助使用者完成以下任務：               │
│                                                                     │
│  【資料分析】                                                       │
│  - SQL 查詢撰寫和優化                                               │
│  - 統計分析和趨勢預測                                               │
│  - 資料視覺化建議                                                   │
│  - ETL 流程設計                                                     │
│  [詳細說明... 2000 tokens]                                          │
│                                                                     │
│  【程式開發】                                                       │
│  - Python、JavaScript、Go、Rust、Java 開發                          │
│  - 前端和後端開發                                                   │
│  - API 設計和實作                                                   │
│  - 資料庫設計                                                       │
│  [詳細說明... 3000 tokens]                                          │
│                                                                     │
│  【系統架構】                                                       │
│  - 微服務設計                                                       │
│  - 雲端架構                                                         │
│  - 效能優化                                                         │
│  [詳細說明... 2500 tokens]                                          │
│                                                                     │
│  【文件撰寫】                                                       │
│  - 技術文件                                                         │
│  - API 文件                                                         │
│  - 使用手冊                                                         │
│  [詳細說明... 1500 tokens]                                          │
│                                                                     │
│  【程式碼審查】                                                     │
│  - 安全性審查                                                       │
│  - 效能審查                                                         │
│  - 最佳實踐檢查                                                     │
│  [詳細說明... 2000 tokens]                                          │
│                                                                     │
│  【工具定義】                                                       │
│  - 30+ 個工具的 Schema                                              │
│  [工具定義... 5000 tokens]                                          │
│                                                                     │
│  總計：~16,000 tokens 的 System Prompt                              │
│  問題：每次呼叫都發送全部內容，即使只做簡單翻譯                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 專責化的效益

```
專責化 Agent 團隊：

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ 資料分析 Agent  │  │ 程式開發 Agent  │  │ 架構設計 Agent  │
│                 │  │                 │  │                 │
│ System: 2,500t  │  │ System: 3,000t  │  │ System: 2,800t  │
│ Tools: 5 個     │  │ Tools: 6 個     │  │ Tools: 4 個     │
│ Model: Haiku    │  │ Model: Sonnet   │  │ Model: Opus     │
└─────────────────┘  └─────────────────┘  └─────────────────┘

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ 文件撰寫 Agent  │  │ 程式審查 Agent  │  │ 協調者 Agent    │
│                 │  │                 │  │                 │
│ System: 1,800t  │  │ System: 2,200t  │  │ System: 1,500t  │
│ Tools: 3 個     │  │ Tools: 4 個     │  │ Tools: 2 個     │
│ Model: Haiku    │  │ Model: Haiku    │  │ Model: Sonnet   │
└─────────────────┘  └─────────────────┘  └─────────────────┘

效益計算：
- 通用 Agent 每次呼叫：16,000 tokens
- 專責 Agent 平均每次：2,300 tokens
- 節省：85% 的 System Prompt tokens
- 額外好處：可針對任務選擇最適合的模型
```

---

## 核心概念：職責邊界設計

### 職責劃分原則

```
Agent 職責劃分的 SOLID 原則：

S - Single Responsibility（單一職責）
    每個 Agent 只負責一種類型的任務
    ❌ "分析資料並生成報告和撰寫程式碼"
    ✅ "分析資料" → Agent A
    ✅ "生成報告" → Agent B
    ✅ "撰寫程式碼" → Agent C

O - Open/Closed（開放封閉）
    Agent 可擴展新能力，但核心職責不變
    ✅ 資料分析 Agent 可支援新的資料來源
    ❌ 資料分析 Agent 不應該開始寫程式碼

L - Liskov Substitution（里氏替換）
    同類型 Agent 應可互換
    ✅ Python 開發 Agent 和 TypeScript 開發 Agent 有相同介面

I - Interface Segregation（介面隔離）
    Agent 只暴露必要的介面
    ✅ 程式碼審查 Agent 只需要 read_file，不需要 write_file

D - Dependency Inversion（依賴反轉）
    Agent 依賴抽象的 Context，不依賴具體實作
    ✅ 透過 Orchestrator 傳遞標準化 Context
```

### 常見的 Agent 職責模式

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class AgentRole(Enum):
    """Agent 角色類型"""
    # 分析類
    REQUIREMENTS_ANALYST = "requirements_analyst"
    DATA_ANALYST = "data_analyst"
    SECURITY_ANALYST = "security_analyst"

    # 設計類
    ARCHITECT = "architect"
    UI_DESIGNER = "ui_designer"
    API_DESIGNER = "api_designer"

    # 開發類
    BACKEND_DEVELOPER = "backend_developer"
    FRONTEND_DEVELOPER = "frontend_developer"
    DATABASE_DEVELOPER = "database_developer"

    # 品質類
    CODE_REVIEWER = "code_reviewer"
    SECURITY_REVIEWER = "security_reviewer"
    PERFORMANCE_REVIEWER = "performance_reviewer"

    # 文件類
    DOC_WRITER = "doc_writer"
    API_DOC_WRITER = "api_doc_writer"

    # 測試類
    TEST_DESIGNER = "test_designer"
    TEST_IMPLEMENTER = "test_implementer"

    # 協調類
    ORCHESTRATOR = "orchestrator"
    TASK_ROUTER = "task_router"

@dataclass
class AgentCapability:
    """Agent 能力定義"""
    role: AgentRole
    description: str
    core_skills: list[str]
    tools_needed: list[str]
    typical_output: str
    recommended_model: str = "claude-sonnet-4-20250514"
    max_system_tokens: int = 3000

# 預定義的 Agent 能力庫
AGENT_CAPABILITIES = {
    AgentRole.REQUIREMENTS_ANALYST: AgentCapability(
        role=AgentRole.REQUIREMENTS_ANALYST,
        description="分析和整理使用者需求",
        core_skills=["需求提取", "使用者故事撰寫", "驗收標準定義"],
        tools_needed=["read_document"],
        typical_output="結構化需求文件",
        recommended_model="claude-sonnet-4-20250514",
        max_system_tokens=2500
    ),

    AgentRole.BACKEND_DEVELOPER: AgentCapability(
        role=AgentRole.BACKEND_DEVELOPER,
        description="實作後端程式碼和 API",
        core_skills=["Python/Go/Node.js", "API 設計", "資料庫操作"],
        tools_needed=["read_file", "write_file", "run_command"],
        typical_output="可執行的後端程式碼",
        recommended_model="claude-sonnet-4-20250514",
        max_system_tokens=3500
    ),

    AgentRole.CODE_REVIEWER: AgentCapability(
        role=AgentRole.CODE_REVIEWER,
        description="審查程式碼品質和最佳實踐",
        core_skills=["程式碼分析", "問題識別", "改進建議"],
        tools_needed=["read_file"],
        typical_output="審查報告和建議",
        recommended_model="claude-3-5-haiku-20241022",  # 輕量任務用 Haiku
        max_system_tokens=2000
    ),

    AgentRole.ORCHESTRATOR: AgentCapability(
        role=AgentRole.ORCHESTRATOR,
        description="協調多個 Agent 完成複雜任務",
        core_skills=["任務分解", "Agent 調度", "結果整合"],
        tools_needed=["delegate_task"],
        typical_output="整合後的最終結果",
        recommended_model="claude-sonnet-4-20250514",
        max_system_tokens=2000
    ),
}
```

---

## 策略一：System Prompt 精簡化

### 設計最小化的 System Prompt

```python
import anthropic
from dataclasses import dataclass
from typing import Optional

client = anthropic.Anthropic()

@dataclass
class MinimalSystemPrompt:
    """最小化 System Prompt 結構"""
    role_definition: str       # 角色定義（必要）
    core_responsibility: str   # 核心職責（必要）
    output_format: str         # 輸出格式（必要）
    constraints: list[str]     # 限制條件（可選）
    examples: Optional[str] = None  # 範例（僅複雜任務需要）

    def build(self) -> str:
        """建構最小化的 System Prompt"""
        parts = [
            f"# 角色\n{self.role_definition}",
            f"\n# 職責\n{self.core_responsibility}",
            f"\n# 輸出格式\n{self.output_format}",
        ]

        if self.constraints:
            constraints_text = "\n".join(f"- {c}" for c in self.constraints)
            parts.append(f"\n# 限制\n{constraints_text}")

        if self.examples:
            parts.append(f"\n# 範例\n{self.examples}")

        return "\n".join(parts)

    def token_estimate(self) -> int:
        """估算 token 數"""
        return len(self.build()) // 3


class SpecializedAgentFactory:
    """專責 Agent 工廠"""

    # 預定義的精簡 System Prompts
    SPECIALIZED_PROMPTS = {
        AgentRole.REQUIREMENTS_ANALYST: MinimalSystemPrompt(
            role_definition="你是需求分析師，專精於理解和結構化使用者需求。",
            core_responsibility="""從使用者描述中提取：
1. 功能需求（必須有的功能）
2. 非功能需求（效能、安全、可用性）
3. 限制條件
4. 驗收標準""",
            output_format="""以 JSON 格式輸出：
{
    "functional_requirements": [...],
    "non_functional_requirements": [...],
    "constraints": [...],
    "acceptance_criteria": [...]
}""",
            constraints=[
                "只分析需求，不提供實作方案",
                "保持客觀，不加入假設",
                "不確定的需求標記為 [待確認]"
            ]
        ),

        AgentRole.BACKEND_DEVELOPER: MinimalSystemPrompt(
            role_definition="你是後端開發者，專精於 Python/FastAPI 開發。",
            core_responsibility="根據需求和設計實作乾淨、可維護的後端程式碼。",
            output_format="""輸出完整可執行的程式碼：
1. 必要的 import
2. 完整的實作
3. 基本的錯誤處理
4. 簡短的使用說明""",
            constraints=[
                "遵循 PEP 8 風格",
                "函數單一職責",
                "加入類型提示"
            ]
        ),

        AgentRole.CODE_REVIEWER: MinimalSystemPrompt(
            role_definition="你是程式碼審查員，專注於發現問題和提供改進建議。",
            core_responsibility="""審查程式碼的：
1. 正確性
2. 可讀性
3. 效能
4. 安全性""",
            output_format="""以列表形式輸出：
- 🔴 嚴重問題：[問題描述和建議]
- 🟡 建議改進：[改進點和原因]
- 🟢 做得好的地方：[肯定的部分]""",
            constraints=[
                "只審查，不修改程式碼",
                "每個問題都要有具體建議",
                "按嚴重程度排序"
            ]
        ),

        AgentRole.DOC_WRITER: MinimalSystemPrompt(
            role_definition="你是技術文件撰寫者，專精於清晰易懂的文件。",
            core_responsibility="根據程式碼和設計撰寫技術文件。",
            output_format="""Markdown 格式，包含：
1. 概述
2. 安裝/使用方法
3. API 說明
4. 範例""",
            constraints=[
                "使用簡潔清晰的語言",
                "包含程式碼範例",
                "面向目標讀者撰寫"
            ]
        ),

        AgentRole.ORCHESTRATOR: MinimalSystemPrompt(
            role_definition="你是任務協調者，負責分解任務並協調多個專家完成。",
            core_responsibility="""分析任務後：
1. 分解為子任務
2. 指派給合適的專家
3. 整合各專家的輸出""",
            output_format="""JSON 格式的執行計畫：
{
    "subtasks": [
        {"id": 1, "description": "...", "assigned_to": "agent_type"},
        ...
    ],
    "execution_order": [1, 2, 3],
    "dependencies": {"2": [1], "3": [1, 2]}
}""",
            constraints=[
                "最小化子任務數量",
                "明確定義依賴關係",
                "每個子任務單一職責"
            ]
        ),
    }

    @classmethod
    def create_agent(
        cls,
        role: AgentRole,
        custom_constraints: Optional[list[str]] = None
    ) -> "SpecializedAgent":
        """創建專責 Agent"""
        base_prompt = cls.SPECIALIZED_PROMPTS.get(role)
        capability = AGENT_CAPABILITIES.get(role)

        if not base_prompt or not capability:
            raise ValueError(f"未定義的角色: {role}")

        # 合併自訂限制
        if custom_constraints:
            prompt = MinimalSystemPrompt(
                role_definition=base_prompt.role_definition,
                core_responsibility=base_prompt.core_responsibility,
                output_format=base_prompt.output_format,
                constraints=base_prompt.constraints + custom_constraints,
                examples=base_prompt.examples
            )
        else:
            prompt = base_prompt

        return SpecializedAgent(
            role=role,
            system_prompt=prompt.build(),
            model=capability.recommended_model,
            tools=capability.tools_needed
        )


class SpecializedAgent:
    """專責 Agent"""

    def __init__(
        self,
        role: AgentRole,
        system_prompt: str,
        model: str,
        tools: list[str]
    ):
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.tools = tools
        self._stats = {
            "calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0
        }

    def execute(self, task: str, context: str = "") -> str:
        """執行任務"""
        full_task = f"{context}\n\n任務：{task}" if context else task

        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.system_prompt,
            messages=[{"role": "user", "content": full_task}]
        )

        # 更新統計
        self._stats["calls"] += 1
        self._stats["total_input_tokens"] += response.usage.input_tokens
        self._stats["total_output_tokens"] += response.usage.output_tokens

        return response.content[0].text

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "system_prompt_tokens": len(self.system_prompt) // 3,
            "model": self.model,
            "tools_count": len(self.tools)
        }


# 使用範例
if __name__ == "__main__":
    # 創建專責 Agents
    analyst = SpecializedAgentFactory.create_agent(AgentRole.REQUIREMENTS_ANALYST)
    developer = SpecializedAgentFactory.create_agent(AgentRole.BACKEND_DEVELOPER)
    reviewer = SpecializedAgentFactory.create_agent(AgentRole.CODE_REVIEWER)

    print("專責 Agent System Prompt 大小：")
    print(f"  需求分析師: ~{analyst.get_stats()['system_prompt_tokens']} tokens")
    print(f"  後端開發者: ~{developer.get_stats()['system_prompt_tokens']} tokens")
    print(f"  程式碼審查: ~{reviewer.get_stats()['system_prompt_tokens']} tokens")

    # 對比通用 Agent
    general_prompt_tokens = 16000
    specialized_avg = (
        analyst.get_stats()['system_prompt_tokens'] +
        developer.get_stats()['system_prompt_tokens'] +
        reviewer.get_stats()['system_prompt_tokens']
    ) / 3

    print(f"\n對比通用 Agent ({general_prompt_tokens} tokens):")
    print(f"  專責 Agent 平均: ~{specialized_avg:.0f} tokens")
    print(f"  節省: {(1 - specialized_avg/general_prompt_tokens) * 100:.1f}%")
```

---

## 策略二：工具最小化配置

### 每個 Agent 只配置必要的工具

```python
from typing import Any

# 完整的工具定義庫
TOOL_DEFINITIONS = {
    "read_file": {
        "name": "read_file",
        "description": "讀取檔案內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "檔案路徑"}
            },
            "required": ["path"]
        }
    },
    "write_file": {
        "name": "write_file",
        "description": "寫入檔案",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    "run_command": {
        "name": "run_command",
        "description": "執行系統命令",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"]
        }
    },
    "query_database": {
        "name": "query_database",
        "description": "執行資料庫查詢",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "database": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    "search_web": {
        "name": "search_web",
        "description": "搜尋網頁資訊",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    "delegate_task": {
        "name": "delegate_task",
        "description": "將任務委派給其他 Agent",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_type": {"type": "string"},
                "task": {"type": "string"},
                "context": {"type": "string"}
            },
            "required": ["agent_type", "task"]
        }
    },
    "analyze_code": {
        "name": "analyze_code",
        "description": "分析程式碼結構和依賴",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"}
            },
            "required": ["code"]
        }
    },
    "run_tests": {
        "name": "run_tests",
        "description": "執行測試套件",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string"},
                "coverage": {"type": "boolean"}
            },
            "required": ["test_path"]
        }
    }
}

# Agent 角色到工具的映射（最小化配置）
ROLE_TOOL_MAPPING = {
    AgentRole.REQUIREMENTS_ANALYST: [
        "read_file",  # 讀取需求文件
    ],
    AgentRole.DATA_ANALYST: [
        "read_file",
        "query_database",
    ],
    AgentRole.ARCHITECT: [
        "read_file",
        "search_web",  # 搜尋最佳實踐
    ],
    AgentRole.BACKEND_DEVELOPER: [
        "read_file",
        "write_file",
        "run_command",
    ],
    AgentRole.FRONTEND_DEVELOPER: [
        "read_file",
        "write_file",
        "run_command",
    ],
    AgentRole.CODE_REVIEWER: [
        "read_file",  # 只需要讀取，不需要寫入
        "analyze_code",
    ],
    AgentRole.SECURITY_REVIEWER: [
        "read_file",
        "analyze_code",
    ],
    AgentRole.DOC_WRITER: [
        "read_file",
        "write_file",
    ],
    AgentRole.TEST_DESIGNER: [
        "read_file",
    ],
    AgentRole.TEST_IMPLEMENTER: [
        "read_file",
        "write_file",
        "run_tests",
    ],
    AgentRole.ORCHESTRATOR: [
        "delegate_task",
    ],
}


class MinimalToolConfigurator:
    """最小化工具配置器"""

    def __init__(self):
        self.tool_definitions = TOOL_DEFINITIONS
        self.role_mapping = ROLE_TOOL_MAPPING

    def get_tools_for_role(self, role: AgentRole) -> list[dict]:
        """取得角色所需的最小工具集"""
        tool_names = self.role_mapping.get(role, [])
        return [
            self.tool_definitions[name]
            for name in tool_names
            if name in self.tool_definitions
        ]

    def estimate_tools_tokens(self, role: AgentRole) -> int:
        """估算工具定義的 token 數"""
        import json
        tools = self.get_tools_for_role(role)
        tools_json = json.dumps(tools, ensure_ascii=False)
        return len(tools_json) // 3

    def compare_tool_overhead(self) -> dict:
        """比較不同角色的工具開銷"""
        # 計算全部工具的開銷
        import json
        all_tools_tokens = len(json.dumps(list(self.tool_definitions.values()), ensure_ascii=False)) // 3

        results = {
            "all_tools_tokens": all_tools_tokens,
            "role_tools": {}
        }

        for role in AgentRole:
            if role in self.role_mapping:
                tokens = self.estimate_tools_tokens(role)
                results["role_tools"][role.value] = {
                    "tokens": tokens,
                    "tools_count": len(self.role_mapping[role]),
                    "savings_pct": f"{(1 - tokens/all_tools_tokens) * 100:.1f}%"
                }

        return results


class ToolMinimizedAgent:
    """工具最小化的 Agent"""

    def __init__(
        self,
        role: AgentRole,
        system_prompt: str,
        model: str = "claude-sonnet-4-20250514"
    ):
        self.role = role
        self.system_prompt = system_prompt
        self.model = model

        # 只配置必要的工具
        configurator = MinimalToolConfigurator()
        self.tools = configurator.get_tools_for_role(role)

        self._tool_calls: list[dict] = []

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """處理工具呼叫（示範實作）"""
        # 實際應用中，這裡會呼叫真正的工具
        self._tool_calls.append({"name": tool_name, "input": tool_input})

        if tool_name == "read_file":
            return f"[模擬] 讀取檔案 {tool_input.get('path')} 的內容..."
        elif tool_name == "write_file":
            return f"[模擬] 已寫入 {tool_input.get('path')}"
        elif tool_name == "run_command":
            return f"[模擬] 執行命令: {tool_input.get('command')}"
        else:
            return f"[模擬] 工具 {tool_name} 執行完成"

    def execute(self, task: str, context: str = "") -> str:
        """執行任務（支援工具呼叫）"""
        messages = []

        if context:
            messages.append({"role": "user", "content": f"{context}\n\n任務：{task}"})
        else:
            messages.append({"role": "user", "content": task})

        # 迭代處理工具呼叫
        while True:
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools if self.tools else None,
                messages=messages
            )

            # 檢查是否有工具呼叫
            tool_use_blocks = [
                block for block in response.content
                if block.type == "tool_use"
            ]

            if not tool_use_blocks:
                # 沒有工具呼叫，返回文字回應
                text_blocks = [
                    block.text for block in response.content
                    if hasattr(block, "text")
                ]
                return "\n".join(text_blocks)

            # 處理工具呼叫
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                result = self._handle_tool_call(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result
                })

            messages.append({"role": "user", "content": tool_results})

    def get_tool_stats(self) -> dict:
        """取得工具使用統計"""
        return {
            "configured_tools": len(self.tools),
            "tool_calls_made": len(self._tool_calls),
            "tools_used": list(set(tc["name"] for tc in self._tool_calls))
        }


# 使用範例
if __name__ == "__main__":
    configurator = MinimalToolConfigurator()
    comparison = configurator.compare_tool_overhead()

    print("工具配置對比：")
    print(f"全部工具: {comparison['all_tools_tokens']} tokens\n")

    for role, stats in comparison["role_tools"].items():
        print(f"{role}:")
        print(f"  工具數: {stats['tools_count']}")
        print(f"  Tokens: {stats['tokens']}")
        print(f"  節省: {stats['savings_pct']}")
```

---

## 策略三：模型差異化選擇

### 根據任務複雜度選擇模型

```python
from enum import Enum
from dataclasses import dataclass

class ModelTier(Enum):
    """模型層級"""
    FAST = "fast"       # Haiku - 快速便宜
    BALANCED = "balanced"  # Sonnet - 平衡
    POWERFUL = "powerful"  # Opus - 最強

@dataclass
class ModelConfig:
    """模型配置"""
    tier: ModelTier
    model_id: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    best_for: list[str]

MODEL_CONFIGS = {
    ModelTier.FAST: ModelConfig(
        tier=ModelTier.FAST,
        model_id="claude-3-5-haiku-20241022",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.0,
        best_for=["分類", "摘要", "格式化", "簡單審查", "路由決策"]
    ),
    ModelTier.BALANCED: ModelConfig(
        tier=ModelTier.BALANCED,
        model_id="claude-sonnet-4-20250514",
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
        best_for=["程式碼生成", "分析", "一般任務", "協調"]
    ),
    ModelTier.POWERFUL: ModelConfig(
        tier=ModelTier.POWERFUL,
        model_id="claude-opus-4-20250514",
        input_cost_per_1m=15.0,
        output_cost_per_1m=75.0,
        best_for=["複雜架構", "創意設計", "深度分析", "關鍵決策"]
    ),
}

# Agent 角色到模型層級的映射
ROLE_MODEL_MAPPING = {
    # 快速模型 - 簡單任務
    AgentRole.CODE_REVIEWER: ModelTier.FAST,
    AgentRole.DOC_WRITER: ModelTier.FAST,
    AgentRole.TEST_DESIGNER: ModelTier.FAST,
    AgentRole.TASK_ROUTER: ModelTier.FAST,

    # 平衡模型 - 一般任務
    AgentRole.REQUIREMENTS_ANALYST: ModelTier.BALANCED,
    AgentRole.BACKEND_DEVELOPER: ModelTier.BALANCED,
    AgentRole.FRONTEND_DEVELOPER: ModelTier.BALANCED,
    AgentRole.DATA_ANALYST: ModelTier.BALANCED,
    AgentRole.ORCHESTRATOR: ModelTier.BALANCED,
    AgentRole.TEST_IMPLEMENTER: ModelTier.BALANCED,

    # 強力模型 - 複雜任務
    AgentRole.ARCHITECT: ModelTier.POWERFUL,
    AgentRole.SECURITY_ANALYST: ModelTier.POWERFUL,
    AgentRole.SECURITY_REVIEWER: ModelTier.POWERFUL,
}


class ModelOptimizedAgentSystem:
    """模型優化的 Agent 系統"""

    def __init__(self):
        self.agents: dict[AgentRole, SpecializedAgent] = {}
        self._cost_tracker = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "by_tier": {tier: {"tokens": 0, "cost": 0.0} for tier in ModelTier}
        }

    def get_model_for_role(self, role: AgentRole) -> str:
        """取得角色對應的模型"""
        tier = ROLE_MODEL_MAPPING.get(role, ModelTier.BALANCED)
        return MODEL_CONFIGS[tier].model_id

    def get_model_tier(self, role: AgentRole) -> ModelTier:
        """取得角色對應的模型層級"""
        return ROLE_MODEL_MAPPING.get(role, ModelTier.BALANCED)

    def register_agent(self, role: AgentRole, system_prompt: str):
        """註冊 Agent"""
        model = self.get_model_for_role(role)

        # 取得最小化工具
        configurator = MinimalToolConfigurator()
        tools = configurator.get_tools_for_role(role)

        self.agents[role] = SpecializedAgent(
            role=role,
            system_prompt=system_prompt,
            model=model,
            tools=[t["name"] for t in tools]
        )

    def execute(self, role: AgentRole, task: str, context: str = "") -> str:
        """執行任務並追蹤成本"""
        if role not in self.agents:
            raise ValueError(f"Agent {role} 未註冊")

        agent = self.agents[role]
        tier = self.get_model_tier(role)
        config = MODEL_CONFIGS[tier]

        # 執行
        result = agent.execute(task, context)

        # 追蹤成本
        stats = agent.get_stats()
        input_tokens = stats["total_input_tokens"]
        output_tokens = stats["total_output_tokens"]

        cost = (
            input_tokens * config.input_cost_per_1m / 1_000_000 +
            output_tokens * config.output_cost_per_1m / 1_000_000
        )

        self._cost_tracker["total_input_tokens"] += input_tokens
        self._cost_tracker["total_output_tokens"] += output_tokens
        self._cost_tracker["total_cost"] += cost
        self._cost_tracker["by_tier"][tier]["tokens"] += input_tokens + output_tokens
        self._cost_tracker["by_tier"][tier]["cost"] += cost

        return result

    def get_cost_report(self) -> dict:
        """取得成本報告"""
        return {
            "total_tokens": self._cost_tracker["total_input_tokens"] + self._cost_tracker["total_output_tokens"],
            "total_cost": f"${self._cost_tracker['total_cost']:.4f}",
            "by_tier": {
                tier.value: {
                    "tokens": stats["tokens"],
                    "cost": f"${stats['cost']:.4f}"
                }
                for tier, stats in self._cost_tracker["by_tier"].items()
            }
        }

    def estimate_savings_vs_single_model(self) -> dict:
        """估算相比單一模型的節省"""
        total_tokens = (
            self._cost_tracker["total_input_tokens"] +
            self._cost_tracker["total_output_tokens"]
        )

        if total_tokens == 0:
            return {"error": "尚無執行記錄"}

        # 假設全部使用各層級模型的成本
        all_opus_cost = total_tokens * (15.0 + 75.0) / 2 / 1_000_000
        all_sonnet_cost = total_tokens * (3.0 + 15.0) / 2 / 1_000_000
        all_haiku_cost = total_tokens * (0.8 + 4.0) / 2 / 1_000_000

        actual_cost = self._cost_tracker["total_cost"]

        return {
            "actual_cost": f"${actual_cost:.4f}",
            "if_all_opus": f"${all_opus_cost:.4f}",
            "if_all_sonnet": f"${all_sonnet_cost:.4f}",
            "if_all_haiku": f"${all_haiku_cost:.4f}",
            "savings_vs_opus": f"{(1 - actual_cost/all_opus_cost) * 100:.1f}%" if all_opus_cost > 0 else "N/A",
            "savings_vs_sonnet": f"{(1 - actual_cost/all_sonnet_cost) * 100:.1f}%" if all_sonnet_cost > 0 else "N/A",
        }
```

---

## 策略四：完整的專責化系統

### 整合所有策略的生產級系統

```python
import anthropic
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from enum import Enum
import json
import time

client = anthropic.Anthropic()

@dataclass
class AgentExecutionResult:
    """Agent 執行結果"""
    role: AgentRole
    output: str
    input_tokens: int
    output_tokens: int
    model_used: str
    execution_time_ms: float
    cost: float
    success: bool
    error: Optional[str] = None

@dataclass
class SpecializedAgentConfig:
    """專責 Agent 配置"""
    role: AgentRole
    system_prompt: str
    model_tier: ModelTier
    tools: list[str]
    max_tokens: int = 4096

    # 可選的自訂處理器
    output_parser: Optional[Callable[[str], Any]] = None
    pre_processor: Optional[Callable[[str], str]] = None


class SpecializedAgentOrchestrator:
    """
    專責化 Agent 協調系統

    整合：
    1. 最小化 System Prompt
    2. 最小化工具配置
    3. 模型差異化選擇
    4. 成本追蹤
    """

    def __init__(self):
        self.agents: dict[AgentRole, SpecializedAgentConfig] = {}
        self.tool_configurator = MinimalToolConfigurator()

        self._execution_history: list[AgentExecutionResult] = []
        self._stats = {
            "total_executions": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "by_role": {},
            "by_model": {}
        }

    def register_agent(self, config: SpecializedAgentConfig):
        """註冊專責 Agent"""
        self.agents[config.role] = config
        self._stats["by_role"][config.role.value] = {
            "executions": 0,
            "tokens": 0,
            "cost": 0.0
        }

    def register_from_factory(self, role: AgentRole, custom_constraints: list[str] = None):
        """從工廠註冊 Agent"""
        # 取得預定義的 System Prompt
        base_prompt = SpecializedAgentFactory.SPECIALIZED_PROMPTS.get(role)
        if not base_prompt:
            raise ValueError(f"未定義角色 {role} 的 System Prompt")

        # 建構 System Prompt
        if custom_constraints:
            prompt = MinimalSystemPrompt(
                role_definition=base_prompt.role_definition,
                core_responsibility=base_prompt.core_responsibility,
                output_format=base_prompt.output_format,
                constraints=base_prompt.constraints + custom_constraints,
                examples=base_prompt.examples
            )
        else:
            prompt = base_prompt

        # 取得模型和工具配置
        model_tier = ROLE_MODEL_MAPPING.get(role, ModelTier.BALANCED)
        tools = [t["name"] for t in self.tool_configurator.get_tools_for_role(role)]

        config = SpecializedAgentConfig(
            role=role,
            system_prompt=prompt.build(),
            model_tier=model_tier,
            tools=tools
        )

        self.register_agent(config)

    def _get_model_id(self, tier: ModelTier) -> str:
        """取得模型 ID"""
        return MODEL_CONFIGS[tier].model_id

    def _calculate_cost(self, tier: ModelTier, input_tokens: int, output_tokens: int) -> float:
        """計算成本"""
        config = MODEL_CONFIGS[tier]
        return (
            input_tokens * config.input_cost_per_1m / 1_000_000 +
            output_tokens * config.output_cost_per_1m / 1_000_000
        )

    def execute_agent(
        self,
        role: AgentRole,
        task: str,
        context: str = ""
    ) -> AgentExecutionResult:
        """執行單個專責 Agent"""
        if role not in self.agents:
            return AgentExecutionResult(
                role=role,
                output="",
                input_tokens=0,
                output_tokens=0,
                model_used="",
                execution_time_ms=0,
                cost=0,
                success=False,
                error=f"Agent {role.value} 未註冊"
            )

        config = self.agents[role]
        model_id = self._get_model_id(config.model_tier)

        # 預處理
        if config.pre_processor:
            task = config.pre_processor(task)

        # 組合輸入
        full_task = f"{context}\n\n任務：{task}" if context else task

        # 取得工具定義
        tools = self.tool_configurator.get_tools_for_role(role) if config.tools else None

        start_time = time.time()

        try:
            kwargs = {
                "model": model_id,
                "max_tokens": config.max_tokens,
                "system": config.system_prompt,
                "messages": [{"role": "user", "content": full_task}]
            }

            if tools:
                kwargs["tools"] = tools

            response = client.messages.create(**kwargs)

            # 提取文字輸出
            text_output = "\n".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )

            # 後處理
            if config.output_parser:
                text_output = config.output_parser(text_output)

            execution_time = (time.time() - start_time) * 1000
            cost = self._calculate_cost(
                config.model_tier,
                response.usage.input_tokens,
                response.usage.output_tokens
            )

            result = AgentExecutionResult(
                role=role,
                output=text_output,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model_used=model_id,
                execution_time_ms=execution_time,
                cost=cost,
                success=True
            )

        except Exception as e:
            result = AgentExecutionResult(
                role=role,
                output="",
                input_tokens=0,
                output_tokens=0,
                model_used=model_id,
                execution_time_ms=(time.time() - start_time) * 1000,
                cost=0,
                success=False,
                error=str(e)
            )

        # 更新統計
        self._update_stats(result, config.model_tier)
        self._execution_history.append(result)

        return result

    def _update_stats(self, result: AgentExecutionResult, tier: ModelTier):
        """更新統計"""
        self._stats["total_executions"] += 1
        tokens = result.input_tokens + result.output_tokens
        self._stats["total_tokens"] += tokens
        self._stats["total_cost"] += result.cost

        # 按角色
        role_key = result.role.value
        if role_key in self._stats["by_role"]:
            self._stats["by_role"][role_key]["executions"] += 1
            self._stats["by_role"][role_key]["tokens"] += tokens
            self._stats["by_role"][role_key]["cost"] += result.cost

        # 按模型
        tier_key = tier.value
        if tier_key not in self._stats["by_model"]:
            self._stats["by_model"][tier_key] = {"executions": 0, "tokens": 0, "cost": 0.0}
        self._stats["by_model"][tier_key]["executions"] += 1
        self._stats["by_model"][tier_key]["tokens"] += tokens
        self._stats["by_model"][tier_key]["cost"] += result.cost

    def execute_pipeline(
        self,
        task: str,
        pipeline: list[AgentRole],
        context_builder: Optional[Callable[[list[AgentExecutionResult]], str]] = None
    ) -> list[AgentExecutionResult]:
        """
        執行 Agent 管線

        Args:
            task: 原始任務
            pipeline: Agent 執行順序
            context_builder: 自訂 Context 建構器

        Returns:
            所有執行結果
        """
        results = []

        for i, role in enumerate(pipeline):
            print(f"\n{'='*50}")
            print(f"Step {i+1}/{len(pipeline)}: {role.value}")
            print(f"{'='*50}")

            # 建構 Context
            if context_builder and results:
                context = context_builder(results)
            elif results:
                # 預設：使用上一個 Agent 的輸出摘要
                last_result = results[-1]
                context = f"[上一步 {last_result.role.value} 的輸出]\n{last_result.output[:2000]}..."
            else:
                context = ""

            # 執行
            result = self.execute_agent(role, task, context)
            results.append(result)

            # 輸出狀態
            if result.success:
                print(f"✅ 成功")
                print(f"   模型: {result.model_used}")
                print(f"   Tokens: {result.input_tokens + result.output_tokens}")
                print(f"   成本: ${result.cost:.4f}")
                print(f"   時間: {result.execution_time_ms:.0f}ms")
            else:
                print(f"❌ 失敗: {result.error}")

        return results

    def get_stats(self) -> dict:
        """取得統計"""
        return {
            **self._stats,
            "avg_tokens_per_execution": (
                self._stats["total_tokens"] / self._stats["total_executions"]
                if self._stats["total_executions"] > 0 else 0
            ),
            "avg_cost_per_execution": (
                self._stats["total_cost"] / self._stats["total_executions"]
                if self._stats["total_executions"] > 0 else 0
            )
        }

    def get_optimization_report(self) -> str:
        """取得優化報告"""
        lines = [
            "="*60,
            "專責化 Agent 系統優化報告",
            "="*60,
            "",
            f"總執行次數: {self._stats['total_executions']}",
            f"總 Token 使用: {self._stats['total_tokens']:,}",
            f"總成本: ${self._stats['total_cost']:.4f}",
            "",
            "按模型層級分布:",
        ]

        for tier, stats in self._stats["by_model"].items():
            pct = stats["tokens"] / self._stats["total_tokens"] * 100 if self._stats["total_tokens"] > 0 else 0
            lines.append(f"  {tier}: {stats['tokens']:,} tokens ({pct:.1f}%), ${stats['cost']:.4f}")

        lines.extend([
            "",
            "按角色分布:",
        ])

        for role, stats in self._stats["by_role"].items():
            if stats["executions"] > 0:
                lines.append(f"  {role}: {stats['executions']} 次, {stats['tokens']:,} tokens, ${stats['cost']:.4f}")

        # 估算節省
        if self._stats["total_tokens"] > 0:
            # 假設全部使用 Opus
            all_opus_cost = self._stats["total_tokens"] * (15.0 + 75.0) / 2 / 1_000_000
            savings = (all_opus_cost - self._stats["total_cost"]) / all_opus_cost * 100

            lines.extend([
                "",
                "成本優化效果:",
                f"  若全部使用 Opus: ${all_opus_cost:.4f}",
                f"  實際成本: ${self._stats['total_cost']:.4f}",
                f"  節省: {savings:.1f}%"
            ])

        lines.append("="*60)
        return "\n".join(lines)


# 使用範例
def create_development_team() -> SpecializedAgentOrchestrator:
    """創建開發團隊"""
    orchestrator = SpecializedAgentOrchestrator()

    # 註冊各專責 Agent
    roles = [
        AgentRole.REQUIREMENTS_ANALYST,
        AgentRole.ARCHITECT,
        AgentRole.BACKEND_DEVELOPER,
        AgentRole.CODE_REVIEWER,
        AgentRole.DOC_WRITER,
    ]

    for role in roles:
        try:
            orchestrator.register_from_factory(role)
            print(f"✅ 註冊 {role.value}")
        except ValueError as e:
            print(f"⚠️ 跳過 {role.value}: {e}")

    return orchestrator


if __name__ == "__main__":
    # 創建專責團隊
    team = create_development_team()

    # 定義開發任務
    task = """
    開發一個簡單的 URL 縮短服務：
    - 接受長 URL，返回短碼
    - 支援重定向
    - 記錄訪問統計
    """

    # 執行開發管線
    pipeline = [
        AgentRole.REQUIREMENTS_ANALYST,
        AgentRole.BACKEND_DEVELOPER,
        AgentRole.CODE_REVIEWER,
        AgentRole.DOC_WRITER,
    ]

    results = team.execute_pipeline(task, pipeline)

    # 輸出報告
    print("\n")
    print(team.get_optimization_report())
```

---

## 效能比較與分析

```
專責化 vs 通用 Agent 對比：

┌─────────────────────────────────────────────────────────────────────┐
│                    Token 使用量對比                                  │
├────────────────────┬───────────────┬───────────────┬────────────────┤
│ 項目               │ 通用 Agent    │ 專責 Agent    │ 節省           │
├────────────────────┼───────────────┼───────────────┼────────────────┤
│ System Prompt      │ 16,000 tok    │ 2,500 tok     │ 84%            │
│ 工具定義           │ 5,000 tok     │ 800 tok       │ 84%            │
│ 每次呼叫固定成本   │ 21,000 tok    │ 3,300 tok     │ 84%            │
├────────────────────┼───────────────┼───────────────┼────────────────┤
│ 5 次呼叫總固定成本 │ 105,000 tok   │ 16,500 tok    │ 84%            │
└────────────────────┴───────────────┴───────────────┴────────────────┘

成本計算（假設 Sonnet $3/1M input）：

5 個任務的固定成本：
- 通用 Agent: 105,000 × $3 / 1M = $0.315
- 專責 Agent: 16,500 × $3 / 1M = $0.0495
- 節省: $0.2655 (84%)

模型差異化額外節省：
- 若 3/5 任務使用 Haiku: 再節省 ~60%
- 總節省: 90%+
```

---

## 最佳實踐清單

```
Agent 專責化 Checklist：

職責設計
□ 每個 Agent 是否只負責單一類型任務？
□ Agent 之間的職責邊界是否清晰？
□ 是否避免了職責重疊？

System Prompt 優化
□ System Prompt 是否精簡到必要最小？
□ 是否移除了不相關的說明和範例？
□ 是否使用了結構化的格式？

工具配置
□ 每個 Agent 是否只配置必要的工具？
□ 是否移除了不會使用的工具？
□ 工具定義是否精簡？

模型選擇
□ 簡單任務是否使用輕量模型（Haiku）？
□ 複雜任務是否使用強力模型（Opus）？
□ 是否根據實際效能調整模型選擇？

監控
□ 是否追蹤各 Agent 的 Token 使用？
□ 是否追蹤各模型層級的成本分布？
□ 是否有優化效果的量化指標？
```

---

## 總結

Agent 專責化是降低多 Agent 系統固定成本的核心策略。本文介紹的方案涵蓋：

| 優化面向 | 策略 | 預期節省 |
|----------|------|----------|
| System Prompt | 精簡到必要最小 | 70-85% |
| 工具配置 | 只配置必要工具 | 60-80% |
| 模型選擇 | 任務匹配模型 | 40-70% |
| 綜合效果 | 全面專責化 | 80-95% |

關鍵原則：

1. **單一職責**：每個 Agent 專注於一種任務類型
2. **最小配置**：只包含完成任務必要的 Prompt 和工具
3. **模型匹配**：簡單任務用便宜模型，複雜任務用強力模型
4. **持續優化**：根據實際使用數據調整配置

透過 Agent 專責化，你可以在保持系統功能的同時，將固定成本降低 80% 以上，打造真正高效的多 Agent 系統。
