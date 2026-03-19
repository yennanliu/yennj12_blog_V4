---
title: "多 Agent Token 優化系列 pt.7：專責化 Agent 協作模式 — 從團隊設計到生產級協調"
date: 2026-03-19T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "multi-agent", "agent-orchestration", "token-optimization", "system-design", "API", "協作模式"]
summary: "多 Agent Token 優化系列 pt.7：深入探討專責化 Agent 的協作模式，涵蓋團隊組織架構、動態路由、任務分解策略、狀態管理、錯誤處理等生產級實作，幫助你打造高效協調的 Agent 團隊。"
readTime: "40 min"
---

在前一篇《Agent 專責化實戰指南》中，我們學會了如何設計單一職責的精簡 Agent。然而，擁有一群優秀的專家還不夠——關鍵在於如何讓他們**高效協作**。本文將深入探討專責化 Agent 的協作模式，從團隊架構設計到生產級的協調機制。

---

## 核心挑戰：從個體到團隊

### 專責化帶來的協調複雜度

```
專責化前（單體 Agent）：
┌───────────────────────────────────────────────────────┐
│                    全能 Agent                          │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 分析 → 設計 → 開發 → 審查 → 文件             │  │
│  │ (全部在同一個 Context 內完成)                   │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  優點：無協調開銷                                      │
│  缺點：System Prompt 巨大，Token 浪費                 │
└───────────────────────────────────────────────────────┘

專責化後（Agent 團隊）：
┌───────────────────────────────────────────────────────┐
│                                                        │
│  ┌──────────────┐                                     │
│  │ Orchestrator │ ←── 協調開銷                        │
│  └──────┬───────┘                                     │
│         │                                              │
│    ┌────┴────┬────────┬────────┬────────┐            │
│    ▼         ▼        ▼        ▼        ▼            │
│  ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐         │
│  │分析│   │設計│   │開發│   │審查│   │文件│         │
│  └────┘   └────┘   └────┘   └────┘   └────┘         │
│                                                        │
│  優點：各 Agent System Prompt 精簡                    │
│  缺點：需要協調機制，可能增加總呼叫次數               │
└───────────────────────────────────────────────────────┘

關鍵問題：協調開銷是否小於 System Prompt 節省？
答案：設計得當時，節省 >> 開銷
```

### 協調的 Token 成本模型

```python
def calculate_coordination_overhead(
    num_agents: int,
    orchestrator_tokens: int,
    context_passing_tokens: int,
    avg_handoff_tokens: int
) -> int:
    """
    計算協調的額外 Token 開銷

    組成：
    1. Orchestrator 呼叫（任務分解 + 結果整合）
    2. Agent 間 Context 傳遞
    3. Handoff 訊息
    """
    orchestrator_overhead = orchestrator_tokens * 2  # 開始 + 結束
    context_overhead = context_passing_tokens * (num_agents - 1)
    handoff_overhead = avg_handoff_tokens * num_agents

    return orchestrator_overhead + context_overhead + handoff_overhead


def calculate_system_prompt_savings(
    general_agent_prompt: int,
    specialized_prompts: list[int],
    num_calls: int
) -> int:
    """
    計算 System Prompt 節省

    假設：每個任務只呼叫相關的專責 Agent
    """
    # 通用 Agent：每次呼叫都發送完整 prompt
    general_cost = general_agent_prompt * num_calls

    # 專責 Agent：只發送該 Agent 的精簡 prompt
    specialized_cost = sum(specialized_prompts)  # 假設每個 Agent 呼叫一次

    return general_cost - specialized_cost


# 範例計算
general_prompt = 16000  # 通用 Agent 的 System Prompt
specialized_prompts = [2500, 3000, 2800, 2200, 1800]  # 各專責 Agent
num_agents = len(specialized_prompts)

# 假設完成一個完整任務需要呼叫 5 個功能
# 通用 Agent：呼叫 5 次，每次 16000 tokens
# 專責 Agent：每個專責 Agent 呼叫 1 次

savings = calculate_system_prompt_savings(
    general_prompt,
    specialized_prompts,
    num_calls=5
)

overhead = calculate_coordination_overhead(
    num_agents=5,
    orchestrator_tokens=2000,
    context_passing_tokens=500,
    avg_handoff_tokens=300
)

print(f"System Prompt 節省: {savings:,} tokens")
print(f"協調開銷: {overhead:,} tokens")
print(f"淨節省: {savings - overhead:,} tokens")
print(f"節省比例: {(savings - overhead) / (general_prompt * 5) * 100:.1f}%")

# 輸出：
# System Prompt 節省: 67,700 tokens
# 協調開銷: 7,500 tokens
# 淨節省: 60,200 tokens
# 節省比例: 75.3%
```

---

## 協作架構模式

### 模式一：Hub-and-Spoke（中心輻射）

```
架構圖：

                    ┌──────────────────┐
                    │   Orchestrator   │
                    │   (Hub 中心)     │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────┐        ┌─────────┐        ┌─────────┐
    │ Agent A │        │ Agent B │        │ Agent C │
    │ (Spoke) │        │ (Spoke) │        │ (Spoke) │
    └─────────┘        └─────────┘        └─────────┘

特點：
- 所有通訊經過 Orchestrator
- 簡單、可控
- Orchestrator 可能成為瓶頸
- 適合：任務明確、Agent 數量適中的場景
```

```python
import anthropic
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum

client = anthropic.Anthropic()


class AgentRole(Enum):
    ORCHESTRATOR = "orchestrator"
    ANALYST = "analyst"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    DOC_WRITER = "doc_writer"


@dataclass
class TaskResult:
    """標準化的任務結果"""
    agent: AgentRole
    task_id: str
    status: str  # "success", "partial", "failed"
    output: str
    summary: str  # 精簡摘要（用於傳遞給下游）
    tokens_used: int
    metadata: dict = field(default_factory=dict)


class HubAndSpokeOrchestrator:
    """
    Hub-and-Spoke 協作模式

    所有 Agent 通訊經過中心 Orchestrator：
    1. Orchestrator 接收任務，分解為子任務
    2. 依序（或並行）派發給各 Spoke Agent
    3. 收集結果，決定下一步或整合最終輸出
    """

    def __init__(self):
        self.agents = self._initialize_agents()
        self.task_results: list[TaskResult] = []
        self._token_budget = 0
        self._tokens_used = 0

    def _initialize_agents(self) -> dict:
        """初始化各專責 Agent 的配置"""
        return {
            AgentRole.ORCHESTRATOR: {
                "model": "claude-sonnet-4-20250514",
                "system": """你是任務協調者。

職責：
1. 分解複雜任務為子任務
2. 決定執行順序和依賴關係
3. 整合各 Agent 的輸出

輸出格式（JSON）：
{
    "subtasks": [
        {"id": "1", "agent": "analyst", "task": "...", "depends_on": []},
        {"id": "2", "agent": "developer", "task": "...", "depends_on": ["1"]}
    ],
    "execution_plan": "sequential|parallel|mixed"
}""",
                "max_tokens": 2048
            },

            AgentRole.ANALYST: {
                "model": "claude-sonnet-4-20250514",
                "system": """你是需求分析師。

職責：分析需求，提取關鍵資訊。

輸出格式：
- 功能需求（列表）
- 非功能需求（列表）
- 關鍵限制（列表）
- 建議（列表）""",
                "max_tokens": 2048
            },

            AgentRole.DEVELOPER: {
                "model": "claude-sonnet-4-20250514",
                "system": """你是程式開發者。

職責：根據需求實作程式碼。

輸出格式：
1. 完整可執行的程式碼
2. 簡短說明（3-5 行）
3. 使用方式""",
                "max_tokens": 4096
            },

            AgentRole.REVIEWER: {
                "model": "claude-3-5-haiku-20241022",  # 輕量任務用 Haiku
                "system": """你是程式碼審查員。

職責：審查程式碼品質。

輸出格式（按嚴重度排序）：
🔴 嚴重問題：[...]
🟡 建議改進：[...]
🟢 良好實踐：[...]""",
                "max_tokens": 1024
            },

            AgentRole.DOC_WRITER: {
                "model": "claude-3-5-haiku-20241022",
                "system": """你是技術文件撰寫者。

職責：撰寫清晰的技術文件。

輸出格式（Markdown）：
## 概述
## 安裝
## 使用方式
## API 參考""",
                "max_tokens": 2048
            }
        }

    def _call_agent(
        self,
        role: AgentRole,
        task: str,
        context: str = ""
    ) -> TaskResult:
        """呼叫單個 Agent"""
        config = self.agents[role]

        # 組合輸入（Context + Task）
        full_input = f"{context}\n\n任務：{task}" if context else task

        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            system=config["system"],
            messages=[{"role": "user", "content": full_input}]
        )

        output = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        self._tokens_used += tokens

        # 生成精簡摘要（前 500 字元）
        summary = output[:500] + "..." if len(output) > 500 else output

        return TaskResult(
            agent=role,
            task_id=f"{role.value}_{len(self.task_results)}",
            status="success",
            output=output,
            summary=summary,
            tokens_used=tokens
        )

    def _build_context_for_agent(
        self,
        target_agent: AgentRole,
        dependency_results: list[TaskResult]
    ) -> str:
        """
        為目標 Agent 建構最小化 Context

        核心：只傳遞摘要，不傳遞完整輸出
        """
        if not dependency_results:
            return ""

        context_parts = []
        for result in dependency_results:
            context_parts.append(
                f"[{result.agent.value} 的分析結果]\n{result.summary}"
            )

        return "\n\n---\n\n".join(context_parts)

    def execute(self, task: str, token_budget: int = 50000) -> dict:
        """
        執行完整的協作流程

        Args:
            task: 使用者任務
            token_budget: Token 預算上限
        """
        self._token_budget = token_budget
        self._tokens_used = 0
        self.task_results = []

        print(f"\n{'='*60}")
        print("Hub-and-Spoke 協作模式")
        print(f"{'='*60}")
        print(f"任務: {task[:100]}...")
        print(f"Token 預算: {token_budget:,}")

        # Step 1: Orchestrator 分解任務
        print("\n[Step 1] Orchestrator 分解任務...")
        plan_result = self._call_agent(
            AgentRole.ORCHESTRATOR,
            f"請分解以下任務並制定執行計畫：\n\n{task}"
        )
        self.task_results.append(plan_result)
        print(f"  ✓ 計畫完成，tokens: {plan_result.tokens_used}")

        # Step 2: 依序執行各 Agent
        # （簡化版：固定流程，實際可根據計畫動態調整）
        pipeline = [
            (AgentRole.ANALYST, "分析需求"),
            (AgentRole.DEVELOPER, "實作程式碼"),
            (AgentRole.REVIEWER, "審查程式碼"),
            (AgentRole.DOC_WRITER, "撰寫文件")
        ]

        for i, (role, action) in enumerate(pipeline, start=2):
            print(f"\n[Step {i}] {role.value}: {action}...")

            # 檢查 Token 預算
            if self._tokens_used >= self._token_budget * 0.9:
                print(f"  ⚠️ 接近 Token 預算，跳過後續步驟")
                break

            # 建構 Context（只傳遞前一步的摘要）
            context = self._build_context_for_agent(
                role,
                self.task_results[-2:]  # 只取最近 2 個結果
            )

            # 執行
            result = self._call_agent(role, task, context)
            self.task_results.append(result)
            print(f"  ✓ 完成，tokens: {result.tokens_used}")

        # Step 3: Orchestrator 整合結果
        print("\n[Final] Orchestrator 整合結果...")
        final_context = self._build_context_for_agent(
            AgentRole.ORCHESTRATOR,
            self.task_results
        )

        final_result = self._call_agent(
            AgentRole.ORCHESTRATOR,
            "請整合所有專家的輸出，生成最終報告",
            final_context
        )
        self.task_results.append(final_result)

        # 統計
        print(f"\n{'='*60}")
        print("執行統計")
        print(f"{'='*60}")
        print(f"總 Token 使用: {self._tokens_used:,} / {self._token_budget:,}")
        print(f"Agent 呼叫次數: {len(self.task_results)}")

        return {
            "final_output": final_result.output,
            "all_results": self.task_results,
            "total_tokens": self._tokens_used,
            "budget_usage": f"{self._tokens_used / self._token_budget * 100:.1f}%"
        }
```

### 模式二：Pipeline（流水線）

```
架構圖：

┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Agent A│───▶│ Agent B│───▶│ Agent C│───▶│ Agent D│───▶│ Agent E│
│  分析  │    │  設計  │    │  開發  │    │  審查  │    │  文件  │
└────────┘    └────────┘    └────────┘    └────────┘    └────────┘
     │             │             │             │             │
     ▼             ▼             ▼             ▼             ▼
  需求文件      設計文件      程式碼        審查報告      文件

特點：
- 線性執行，前一個完成後啟動下一個
- 無需複雜的協調邏輯
- 延遲較高（串行）
- 適合：有明確順序依賴的任務流程
```

```python
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class PipelineStage:
    """流水線階段"""
    role: AgentRole
    system_prompt: str
    model: str
    max_tokens: int
    input_transformer: Optional[Callable[[str, list], str]] = None
    output_validator: Optional[Callable[[str], bool]] = None


class PipelineOrchestrator:
    """
    Pipeline 協作模式

    特點：
    1. 嚴格的線性執行順序
    2. 每個階段的輸出是下一階段的輸入
    3. 可選的輸入轉換和輸出驗證
    """

    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages
        self.execution_log: list[dict] = []

    def _transform_input(
        self,
        stage: PipelineStage,
        original_task: str,
        previous_outputs: list[str]
    ) -> str:
        """轉換輸入"""
        if stage.input_transformer:
            return stage.input_transformer(original_task, previous_outputs)

        # 預設：組合原始任務 + 上一階段輸出
        if previous_outputs:
            last_output = previous_outputs[-1]
            # 只取摘要（前 1000 字元）
            summary = last_output[:1000] + "..." if len(last_output) > 1000 else last_output
            return f"背景：\n{summary}\n\n任務：{original_task}"

        return original_task

    def _validate_output(
        self,
        stage: PipelineStage,
        output: str
    ) -> tuple[bool, str]:
        """驗證輸出"""
        if stage.output_validator:
            is_valid = stage.output_validator(output)
            return is_valid, "" if is_valid else "輸出驗證失敗"

        # 預設驗證：非空
        if not output or len(output.strip()) < 10:
            return False, "輸出過短或為空"

        return True, ""

    def execute(
        self,
        task: str,
        stop_on_failure: bool = True
    ) -> dict:
        """
        執行流水線

        Args:
            task: 原始任務
            stop_on_failure: 驗證失敗時是否停止
        """
        outputs: list[str] = []
        self.execution_log = []
        total_tokens = 0

        print(f"\n{'='*60}")
        print("Pipeline 協作模式")
        print(f"{'='*60}")
        print(f"階段數: {len(self.stages)}")

        for i, stage in enumerate(self.stages):
            print(f"\n[{i+1}/{len(self.stages)}] {stage.role.value}")

            # 準備輸入
            stage_input = self._transform_input(stage, task, outputs)

            # 呼叫 Agent
            response = client.messages.create(
                model=stage.model,
                max_tokens=stage.max_tokens,
                system=stage.system_prompt,
                messages=[{"role": "user", "content": stage_input}]
            )

            output = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens
            total_tokens += tokens

            # 驗證輸出
            is_valid, error = self._validate_output(stage, output)

            log_entry = {
                "stage": i + 1,
                "role": stage.role.value,
                "tokens": tokens,
                "valid": is_valid,
                "error": error
            }
            self.execution_log.append(log_entry)

            if is_valid:
                outputs.append(output)
                print(f"  ✓ 完成，tokens: {tokens}")
            else:
                print(f"  ✗ 驗證失敗: {error}")
                if stop_on_failure:
                    print("  ⚠️ 流水線中止")
                    break
                outputs.append("")  # 空輸出，繼續下一階段

        return {
            "final_output": outputs[-1] if outputs else "",
            "all_outputs": outputs,
            "total_tokens": total_tokens,
            "stages_completed": len([l for l in self.execution_log if l["valid"]]),
            "log": self.execution_log
        }


# 建立開發流水線
def create_development_pipeline() -> PipelineOrchestrator:
    """創建標準開發流水線"""
    stages = [
        PipelineStage(
            role=AgentRole.ANALYST,
            system_prompt="你是需求分析師。提取功能需求、非功能需求、限制條件。輸出 JSON。",
            model="claude-sonnet-4-20250514",
            max_tokens=2048
        ),
        PipelineStage(
            role=AgentRole.DEVELOPER,
            system_prompt="你是程式開發者。根據需求實作 Python 程式碼。輸出完整可執行程式碼。",
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            output_validator=lambda x: "def " in x or "class " in x  # 簡單驗證
        ),
        PipelineStage(
            role=AgentRole.REVIEWER,
            system_prompt="你是程式碼審查員。審查程式碼的正確性、可讀性、安全性。",
            model="claude-3-5-haiku-20241022",
            max_tokens=1024
        ),
        PipelineStage(
            role=AgentRole.DOC_WRITER,
            system_prompt="你是文件撰寫者。為程式碼撰寫 README 文件。",
            model="claude-3-5-haiku-20241022",
            max_tokens=2048
        ),
    ]

    return PipelineOrchestrator(stages)
```

### 模式三：Parallel with Merge（並行合併）

```
架構圖：

                    ┌──────────────────┐
                    │   Task Splitter  │
                    │   (任務拆分)      │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────┐        ┌─────────┐        ┌─────────┐
    │ Agent A │        │ Agent B │        │ Agent C │
    │ (並行)  │        │ (並行)  │        │ (並行)  │
    └────┬────┘        └────┬────┘        └────┬────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   Result Merger  │
                    │   (結果合併)      │
                    └──────────────────┘

特點：
- 獨立子任務並行執行
- 大幅縮短總延遲
- 需要設計好合併邏輯
- 適合：可並行的獨立審查、多角度分析
```

```python
import asyncio
from anthropic import AsyncAnthropic

async_client = AsyncAnthropic()


@dataclass
class ParallelTask:
    """並行任務定義"""
    id: str
    role: AgentRole
    task: str
    system_prompt: str
    model: str
    max_tokens: int


class ParallelMergeOrchestrator:
    """
    Parallel with Merge 協作模式

    適用場景：
    1. 多角度分析（安全、效能、可讀性審查）
    2. 多專家意見收集
    3. 獨立子任務處理
    """

    def __init__(self):
        self.results: dict[str, TaskResult] = {}

    async def _execute_single(self, task: ParallelTask) -> TaskResult:
        """非同步執行單個任務"""
        try:
            response = await async_client.messages.create(
                model=task.model,
                max_tokens=task.max_tokens,
                system=task.system_prompt,
                messages=[{"role": "user", "content": task.task}]
            )

            output = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens

            return TaskResult(
                agent=task.role,
                task_id=task.id,
                status="success",
                output=output,
                summary=output[:500],
                tokens_used=tokens
            )

        except Exception as e:
            return TaskResult(
                agent=task.role,
                task_id=task.id,
                status="failed",
                output="",
                summary="",
                tokens_used=0,
                metadata={"error": str(e)}
            )

    async def execute_parallel(
        self,
        tasks: list[ParallelTask],
        timeout: float = 60.0
    ) -> list[TaskResult]:
        """並行執行所有任務"""
        print(f"\n並行執行 {len(tasks)} 個任務...")

        # 創建所有協程
        coroutines = [self._execute_single(task) for task in tasks]

        # 並行執行（帶超時）
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*coroutines, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            print("⚠️ 部分任務超時")
            results = []

        # 過濾結果
        valid_results = []
        for r in results:
            if isinstance(r, TaskResult):
                valid_results.append(r)
                self.results[r.task_id] = r
            elif isinstance(r, Exception):
                print(f"  ✗ 任務失敗: {r}")

        return valid_results

    def merge_results(
        self,
        results: list[TaskResult],
        merge_strategy: str = "concatenate"
    ) -> str:
        """
        合併並行結果

        策略：
        - concatenate: 串連所有輸出
        - summarize: 使用 LLM 總結
        - structured: 結構化整合
        """
        if merge_strategy == "concatenate":
            merged = []
            for r in results:
                merged.append(f"## {r.agent.value}\n\n{r.output}")
            return "\n\n---\n\n".join(merged)

        elif merge_strategy == "structured":
            # 結構化整合
            structured = {
                "results": [],
                "summary": "",
                "consensus": []
            }

            for r in results:
                structured["results"].append({
                    "agent": r.agent.value,
                    "key_points": r.summary
                })

            return str(structured)

        else:
            raise ValueError(f"未知的合併策略: {merge_strategy}")


# 建立並行審查系統
def create_parallel_review_system():
    """創建並行程式碼審查系統"""

    async def review_code(code: str) -> dict:
        orchestrator = ParallelMergeOrchestrator()

        # 定義並行審查任務
        tasks = [
            ParallelTask(
                id="security_review",
                role=AgentRole.REVIEWER,
                task=f"從安全性角度審查以下程式碼：\n\n{code}",
                system_prompt="你是安全專家。專注於：SQL 注入、XSS、認證漏洞、敏感資料洩露。",
                model="claude-3-5-haiku-20241022",
                max_tokens=1024
            ),
            ParallelTask(
                id="performance_review",
                role=AgentRole.REVIEWER,
                task=f"從效能角度審查以下程式碼：\n\n{code}",
                system_prompt="你是效能專家。專注於：時間複雜度、記憶體使用、N+1 查詢、快取策略。",
                model="claude-3-5-haiku-20241022",
                max_tokens=1024
            ),
            ParallelTask(
                id="maintainability_review",
                role=AgentRole.REVIEWER,
                task=f"從可維護性角度審查以下程式碼：\n\n{code}",
                system_prompt="你是架構師。專注於：程式碼結構、命名、單一職責、可讀性。",
                model="claude-3-5-haiku-20241022",
                max_tokens=1024
            ),
        ]

        # 並行執行
        results = await orchestrator.execute_parallel(tasks)

        # 合併結果
        merged = orchestrator.merge_results(results, "concatenate")

        total_tokens = sum(r.tokens_used for r in results)

        return {
            "merged_review": merged,
            "individual_reviews": {r.task_id: r.output for r in results},
            "total_tokens": total_tokens,
            "parallel_speedup": f"{len(tasks)}x (理論值)"
        }

    return review_code


# 使用範例
async def main():
    review_code = create_parallel_review_system()

    sample_code = '''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    result = db.execute(query)
    return result
'''

    result = await review_code(sample_code)
    print(result["merged_review"])

# asyncio.run(main())
```

---

## 動態路由與任務分配

### 智慧路由器設計

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import re


class TaskCategory(Enum):
    """任務類別"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    DEBUGGING = "debugging"
    UNKNOWN = "unknown"


@dataclass
class RoutingDecision:
    """路由決策"""
    category: TaskCategory
    primary_agent: AgentRole
    supporting_agents: list[AgentRole]
    confidence: float
    reasoning: str


class IntelligentRouter:
    """
    智慧任務路由器

    功能：
    1. 分析任務類型
    2. 選擇最適合的 Agent
    3. 決定是否需要多 Agent 協作
    """

    # 關鍵字到類別的映射
    KEYWORD_PATTERNS = {
        TaskCategory.CODE_GENERATION: [
            r"寫[一個]?程式", r"實作", r"開發", r"create", r"implement",
            r"build", r"code", r"function", r"class"
        ],
        TaskCategory.CODE_REVIEW: [
            r"審查", r"review", r"檢查", r"check", r"分析.*程式碼",
            r"有.*問題", r"bug", r"錯誤"
        ],
        TaskCategory.DATA_ANALYSIS: [
            r"分析.*資料", r"統計", r"趨勢", r"data", r"analysis",
            r"chart", r"圖表", r"視覺化"
        ],
        TaskCategory.DOCUMENTATION: [
            r"文件", r"document", r"說明", r"readme", r"api.*doc",
            r"寫.*文"
        ],
        TaskCategory.ARCHITECTURE: [
            r"架構", r"設計", r"architecture", r"design", r"系統",
            r"微服務", r"database.*設計"
        ],
        TaskCategory.TESTING: [
            r"測試", r"test", r"單元", r"整合", r"unit", r"integration"
        ],
        TaskCategory.DEBUGGING: [
            r"除錯", r"debug", r"修復", r"fix", r"錯誤", r"crash"
        ]
    }

    # 類別到 Agent 的映射
    CATEGORY_AGENT_MAP = {
        TaskCategory.CODE_GENERATION: {
            "primary": AgentRole.DEVELOPER,
            "supporting": [AgentRole.ANALYST, AgentRole.REVIEWER]
        },
        TaskCategory.CODE_REVIEW: {
            "primary": AgentRole.REVIEWER,
            "supporting": []
        },
        TaskCategory.DATA_ANALYSIS: {
            "primary": AgentRole.ANALYST,
            "supporting": []
        },
        TaskCategory.DOCUMENTATION: {
            "primary": AgentRole.DOC_WRITER,
            "supporting": [AgentRole.ANALYST]
        },
        TaskCategory.ARCHITECTURE: {
            "primary": AgentRole.ANALYST,  # 架構師（若有的話）
            "supporting": [AgentRole.DEVELOPER]
        },
        TaskCategory.TESTING: {
            "primary": AgentRole.DEVELOPER,
            "supporting": [AgentRole.REVIEWER]
        },
        TaskCategory.DEBUGGING: {
            "primary": AgentRole.DEVELOPER,
            "supporting": [AgentRole.REVIEWER]
        }
    }

    def __init__(self, use_llm_fallback: bool = True):
        self.use_llm_fallback = use_llm_fallback
        self._routing_history: list[RoutingDecision] = []

    def _keyword_classify(self, task: str) -> tuple[TaskCategory, float]:
        """基於關鍵字的快速分類"""
        task_lower = task.lower()
        scores = {}

        for category, patterns in self.KEYWORD_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    score += 1
            scores[category] = score

        if not scores or max(scores.values()) == 0:
            return TaskCategory.UNKNOWN, 0.0

        best_category = max(scores, key=scores.get)
        # 信心度 = 匹配數 / 總模式數
        confidence = scores[best_category] / len(self.KEYWORD_PATTERNS[best_category])

        return best_category, min(confidence, 1.0)

    def _llm_classify(self, task: str) -> tuple[TaskCategory, float]:
        """使用 LLM 進行精確分類（較貴但更準確）"""
        classification_prompt = f"""分類以下任務。只回答類別名稱。

類別：
- code_generation: 寫程式碼、實作功能
- code_review: 審查現有程式碼
- data_analysis: 分析資料、統計
- documentation: 撰寫文件
- architecture: 系統設計、架構規劃
- testing: 撰寫或執行測試
- debugging: 除錯、修復問題
- unknown: 無法分類

任務：{task}

類別："""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # 使用便宜的模型做分類
            max_tokens=20,
            messages=[{"role": "user", "content": classification_prompt}]
        )

        result = response.content[0].text.strip().lower()

        # 解析結果
        for category in TaskCategory:
            if category.value in result:
                return category, 0.9  # LLM 分類給予較高信心度

        return TaskCategory.UNKNOWN, 0.5

    def route(self, task: str) -> RoutingDecision:
        """
        路由任務到適當的 Agent

        邏輯：
        1. 先用關鍵字快速分類
        2. 信心度低時，使用 LLM 分類
        3. 根據類別選擇 Agent
        """
        # 快速分類
        category, confidence = self._keyword_classify(task)

        # 信心度低時使用 LLM
        if confidence < 0.5 and self.use_llm_fallback:
            llm_category, llm_confidence = self._llm_classify(task)
            if llm_confidence > confidence:
                category = llm_category
                confidence = llm_confidence

        # 選擇 Agent
        agent_config = self.CATEGORY_AGENT_MAP.get(
            category,
            {"primary": AgentRole.ORCHESTRATOR, "supporting": []}
        )

        decision = RoutingDecision(
            category=category,
            primary_agent=agent_config["primary"],
            supporting_agents=agent_config["supporting"],
            confidence=confidence,
            reasoning=f"根據任務內容，分類為 {category.value}，信心度 {confidence:.2f}"
        )

        self._routing_history.append(decision)
        return decision

    def get_routing_stats(self) -> dict:
        """取得路由統計"""
        if not self._routing_history:
            return {"total": 0}

        category_counts = {}
        for decision in self._routing_history:
            cat = decision.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total": len(self._routing_history),
            "by_category": category_counts,
            "avg_confidence": sum(d.confidence for d in self._routing_history) / len(self._routing_history)
        }


class AdaptiveOrchestrator:
    """
    自適應協調器

    根據任務特性自動選擇協作模式：
    - 簡單任務 → 單 Agent
    - 中等任務 → Pipeline
    - 複雜任務 → Hub-and-Spoke
    - 可並行任務 → Parallel
    """

    def __init__(self):
        self.router = IntelligentRouter()
        self.hub_spoke = HubAndSpokeOrchestrator()
        self.pipeline = create_development_pipeline()

    def _estimate_complexity(self, task: str, routing: RoutingDecision) -> str:
        """估算任務複雜度"""
        # 簡單啟發式
        word_count = len(task.split())

        if routing.confidence > 0.8 and word_count < 30:
            return "simple"
        elif len(routing.supporting_agents) == 0:
            return "simple"
        elif len(routing.supporting_agents) >= 2:
            return "complex"
        else:
            return "medium"

    def execute(self, task: str) -> dict:
        """自適應執行任務"""
        # 路由決策
        routing = self.router.route(task)
        complexity = self._estimate_complexity(task, routing)

        print(f"\n路由決策：")
        print(f"  類別: {routing.category.value}")
        print(f"  主要 Agent: {routing.primary_agent.value}")
        print(f"  支援 Agent: {[a.value for a in routing.supporting_agents]}")
        print(f"  複雜度: {complexity}")
        print(f"  信心度: {routing.confidence:.2f}")

        # 根據複雜度選擇模式
        if complexity == "simple":
            # 單 Agent 執行
            print("\n使用模式：單 Agent")
            result = self._execute_single_agent(task, routing.primary_agent)

        elif complexity == "medium":
            # Pipeline 執行
            print("\n使用模式：Pipeline")
            result = self.pipeline.execute(task)

        else:
            # Hub-and-Spoke 執行
            print("\n使用模式：Hub-and-Spoke")
            result = self.hub_spoke.execute(task)

        return {
            "routing": routing,
            "mode": complexity,
            "result": result
        }

    def _execute_single_agent(self, task: str, role: AgentRole) -> dict:
        """單 Agent 執行"""
        config = self.hub_spoke.agents[role]

        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            system=config["system"],
            messages=[{"role": "user", "content": task}]
        )

        return {
            "output": response.content[0].text,
            "tokens": response.usage.input_tokens + response.usage.output_tokens
        }
```

---

## 狀態管理與錯誤處理

### 分散式狀態管理

```python
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import json
import time


class TaskStatus(Enum):
    """任務狀態"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class AgentState:
    """Agent 狀態"""
    role: AgentRole
    current_task: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    last_output: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    tokens_consumed: int = 0


@dataclass
class WorkflowState:
    """工作流程狀態"""
    workflow_id: str
    original_task: str
    agent_states: dict[str, AgentState] = field(default_factory=dict)
    shared_context: dict[str, Any] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    current_step: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    def to_dict(self) -> dict:
        """序列化為字典（用於持久化）"""
        return {
            "workflow_id": self.workflow_id,
            "original_task": self.original_task,
            "agent_states": {
                k: {
                    "role": v.role.value,
                    "status": v.status.value,
                    "retries": v.retries,
                    "tokens_consumed": v.tokens_consumed
                }
                for k, v in self.agent_states.items()
            },
            "current_step": self.current_step,
            "total_steps": len(self.execution_order),
            "elapsed_time": time.time() - self.start_time
        }


class StatefulOrchestrator:
    """
    帶狀態管理的協調器

    功能：
    1. 追蹤每個 Agent 的狀態
    2. 支援斷點續傳
    3. 錯誤恢復和重試
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self):
        self.current_workflow: Optional[WorkflowState] = None
        self.agents = self._initialize_agents()

    def _initialize_agents(self) -> dict:
        """初始化 Agent 配置"""
        return {
            AgentRole.ANALYST: {
                "model": "claude-sonnet-4-20250514",
                "system": "你是需求分析師。分析需求並輸出 JSON。",
                "max_tokens": 2048
            },
            AgentRole.DEVELOPER: {
                "model": "claude-sonnet-4-20250514",
                "system": "你是程式開發者。根據需求實作程式碼。",
                "max_tokens": 4096
            },
            AgentRole.REVIEWER: {
                "model": "claude-3-5-haiku-20241022",
                "system": "你是審查員。審查程式碼並列出問題。",
                "max_tokens": 1024
            }
        }

    def _create_workflow(self, task: str) -> WorkflowState:
        """創建新的工作流程"""
        workflow_id = f"wf_{int(time.time())}"

        workflow = WorkflowState(
            workflow_id=workflow_id,
            original_task=task,
            execution_order=[
                AgentRole.ANALYST.value,
                AgentRole.DEVELOPER.value,
                AgentRole.REVIEWER.value
            ]
        )

        # 初始化各 Agent 狀態
        for role_name in workflow.execution_order:
            role = AgentRole(role_name)
            workflow.agent_states[role_name] = AgentState(role=role)

        return workflow

    def _execute_agent_with_retry(
        self,
        role: AgentRole,
        task: str,
        context: str = ""
    ) -> tuple[str, int]:
        """帶重試的 Agent 執行"""
        config = self.agents[role]
        state = self.current_workflow.agent_states[role.value]

        full_input = f"{context}\n\n任務：{task}" if context else task

        for attempt in range(self.MAX_RETRIES):
            try:
                state.status = TaskStatus.IN_PROGRESS
                state.current_task = task

                response = client.messages.create(
                    model=config["model"],
                    max_tokens=config["max_tokens"],
                    system=config["system"],
                    messages=[{"role": "user", "content": full_input}]
                )

                output = response.content[0].text
                tokens = response.usage.input_tokens + response.usage.output_tokens

                state.status = TaskStatus.COMPLETED
                state.last_output = output
                state.tokens_consumed += tokens
                state.error = None

                return output, tokens

            except Exception as e:
                state.retries += 1
                state.error = str(e)

                if attempt < self.MAX_RETRIES - 1:
                    print(f"  ⚠️ 重試 {attempt + 1}/{self.MAX_RETRIES}: {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    state.status = TaskStatus.FAILED
                    raise

    def execute(self, task: str, resume_from: Optional[str] = None) -> dict:
        """
        執行工作流程

        Args:
            task: 任務描述
            resume_from: 可選，從指定工作流程 ID 續傳
        """
        # 創建或恢復工作流程
        if resume_from:
            # TODO: 從持久化存儲載入
            print(f"續傳模式：{resume_from}")
        else:
            self.current_workflow = self._create_workflow(task)

        print(f"\n{'='*60}")
        print(f"工作流程: {self.current_workflow.workflow_id}")
        print(f"{'='*60}")

        results = []
        total_tokens = 0

        # 執行各步驟
        for i, role_name in enumerate(self.current_workflow.execution_order):
            if i < self.current_workflow.current_step:
                print(f"[{i+1}] {role_name}: 跳過（已完成）")
                continue

            role = AgentRole(role_name)
            state = self.current_workflow.agent_states[role_name]

            print(f"\n[{i+1}] {role_name}")

            try:
                # 構建 Context（前一步的摘要）
                context = ""
                if results:
                    last_result = results[-1]
                    context = f"[上一步輸出摘要]\n{last_result[:1000]}..."

                # 執行
                output, tokens = self._execute_agent_with_retry(role, task, context)
                results.append(output)
                total_tokens += tokens

                print(f"  ✓ 完成，tokens: {tokens}")

                # 更新進度
                self.current_workflow.current_step = i + 1

                # 保存 checkpoint（可選：持久化）
                self._save_checkpoint()

            except Exception as e:
                print(f"  ✗ 失敗: {e}")
                return {
                    "status": "failed",
                    "failed_at": role_name,
                    "error": str(e),
                    "partial_results": results,
                    "workflow_state": self.current_workflow.to_dict()
                }

        # 完成
        self.current_workflow.end_time = time.time()

        return {
            "status": "completed",
            "workflow_id": self.current_workflow.workflow_id,
            "final_output": results[-1] if results else "",
            "all_outputs": results,
            "total_tokens": total_tokens,
            "elapsed_time": self.current_workflow.end_time - self.current_workflow.start_time,
            "workflow_state": self.current_workflow.to_dict()
        }

    def _save_checkpoint(self):
        """保存檢查點（用於斷點續傳）"""
        # 實際應用中，這裡會寫入資料庫或檔案
        state = self.current_workflow.to_dict()
        # print(f"  📍 Checkpoint: step {state['current_step']}/{state['total_steps']}")


class ErrorRecoveryOrchestrator(StatefulOrchestrator):
    """
    帶錯誤恢復的協調器

    策略：
    1. 重試（帶退避）
    2. 降級（使用備用 Agent）
    3. 跳過（標記為可選步驟）
    4. 中止（關鍵步驟失敗）
    """

    def __init__(self):
        super().__init__()

        # 定義步驟的關鍵性
        self.step_criticality = {
            AgentRole.ANALYST.value: "critical",    # 失敗則中止
            AgentRole.DEVELOPER.value: "critical",
            AgentRole.REVIEWER.value: "optional",   # 失敗可跳過
        }

        # 備用 Agent 映射
        self.fallback_agents = {
            AgentRole.DEVELOPER: AgentRole.ANALYST,  # 開發者失敗時，嘗試分析師
        }

    def _handle_failure(
        self,
        role: AgentRole,
        error: Exception
    ) -> tuple[str, str]:
        """
        處理失敗

        Returns:
            (action, reason): 行動和原因
        """
        criticality = self.step_criticality.get(role.value, "critical")

        if criticality == "optional":
            return "skip", f"{role.value} 為可選步驟，跳過"

        if role in self.fallback_agents:
            fallback = self.fallback_agents[role]
            return "fallback", f"嘗試使用備用 Agent: {fallback.value}"

        return "abort", f"關鍵步驟 {role.value} 失敗，中止流程"
```

---

## 生產級最佳實踐

### Token 預算管理

```python
@dataclass
class TokenBudget:
    """Token 預算配置"""
    total_budget: int
    per_agent_limits: dict[str, int]
    reserve_ratio: float = 0.1  # 保留 10% 給協調開銷

    def get_available(self, role: AgentRole) -> int:
        """取得可用 Token"""
        limit = self.per_agent_limits.get(role.value, 2000)
        return limit

    def can_afford(self, estimated_tokens: int, used: int) -> bool:
        """檢查是否能負擔"""
        available = self.total_budget * (1 - self.reserve_ratio) - used
        return estimated_tokens <= available


class BudgetAwareOrchestrator:
    """Token 預算感知的協調器"""

    def __init__(self, budget: TokenBudget):
        self.budget = budget
        self.tokens_used = 0

    def _estimate_tokens(self, task: str, role: AgentRole) -> int:
        """估算任務所需 Token"""
        # 簡單估算：System Prompt + 輸入 + 預期輸出
        base_estimate = {
            AgentRole.ANALYST: 3000,
            AgentRole.DEVELOPER: 6000,
            AgentRole.REVIEWER: 2000,
            AgentRole.DOC_WRITER: 3000,
            AgentRole.ORCHESTRATOR: 2500
        }
        return base_estimate.get(role, 3000)

    def execute_within_budget(self, task: str) -> dict:
        """在預算內執行"""
        steps = [
            AgentRole.ANALYST,
            AgentRole.DEVELOPER,
            AgentRole.REVIEWER
        ]

        results = []
        for role in steps:
            estimated = self._estimate_tokens(task, role)

            if not self.budget.can_afford(estimated, self.tokens_used):
                print(f"⚠️ 預算不足，跳過 {role.value}")
                continue

            # 執行...
            # result, tokens = self._execute(role, task)
            # self.tokens_used += tokens
            # results.append(result)

        return {
            "results": results,
            "tokens_used": self.tokens_used,
            "budget_remaining": self.budget.total_budget - self.tokens_used
        }
```

### 監控與可觀測性

```python
import time
from dataclasses import dataclass, field


@dataclass
class AgentMetrics:
    """Agent 指標"""
    role: str
    invocations: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0
    errors: int = 0
    retries: int = 0

    @property
    def avg_tokens(self) -> float:
        return self.total_tokens / self.invocations if self.invocations > 0 else 0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.invocations if self.invocations > 0 else 0

    @property
    def error_rate(self) -> float:
        return self.errors / self.invocations if self.invocations > 0 else 0


class MetricsCollector:
    """指標收集器"""

    def __init__(self):
        self.agent_metrics: dict[str, AgentMetrics] = {}
        self.workflow_metrics: list[dict] = []

    def record_agent_call(
        self,
        role: AgentRole,
        tokens: int,
        latency_ms: float,
        success: bool
    ):
        """記錄 Agent 呼叫"""
        role_key = role.value

        if role_key not in self.agent_metrics:
            self.agent_metrics[role_key] = AgentMetrics(role=role_key)

        metrics = self.agent_metrics[role_key]
        metrics.invocations += 1
        metrics.total_tokens += tokens
        metrics.total_latency_ms += latency_ms

        if not success:
            metrics.errors += 1

    def get_report(self) -> str:
        """生成報告"""
        lines = [
            "="*60,
            "Agent 協作系統監控報告",
            "="*60,
            ""
        ]

        for role, m in self.agent_metrics.items():
            lines.extend([
                f"【{role}】",
                f"  呼叫次數: {m.invocations}",
                f"  總 Tokens: {m.total_tokens:,}",
                f"  平均 Tokens: {m.avg_tokens:.0f}",
                f"  平均延遲: {m.avg_latency_ms:.0f}ms",
                f"  錯誤率: {m.error_rate*100:.1f}%",
                ""
            ])

        # 總計
        total_tokens = sum(m.total_tokens for m in self.agent_metrics.values())
        total_calls = sum(m.invocations for m in self.agent_metrics.values())

        lines.extend([
            "-"*60,
            f"總呼叫: {total_calls}",
            f"總 Tokens: {total_tokens:,}",
            "="*60
        ])

        return "\n".join(lines)
```

---

## 完整範例：生產級開發團隊

```python
"""
生產級專責化 Agent 開發團隊

整合：
1. 智慧路由
2. Hub-and-Spoke 協調
3. 狀態管理
4. 錯誤恢復
5. Token 預算
6. 監控
"""

class ProductionAgentTeam:
    """生產級 Agent 團隊"""

    def __init__(
        self,
        token_budget: int = 50000,
        enable_metrics: bool = True
    ):
        # 核心組件
        self.router = IntelligentRouter()
        self.orchestrator = StatefulOrchestrator()

        # 預算
        self.budget = TokenBudget(
            total_budget=token_budget,
            per_agent_limits={
                "analyst": 3000,
                "developer": 8000,
                "reviewer": 2000,
                "doc_writer": 3000,
                "orchestrator": 2500
            }
        )

        # 監控
        self.metrics = MetricsCollector() if enable_metrics else None

        self.tokens_used = 0

    def process_request(self, request: str) -> dict:
        """處理使用者請求"""
        start_time = time.time()

        print(f"\n{'='*60}")
        print("生產級 Agent 團隊")
        print(f"{'='*60}")
        print(f"請求: {request[:100]}...")
        print(f"Token 預算: {self.budget.total_budget:,}")

        # 1. 路由決策
        routing = self.router.route(request)
        print(f"\n路由決策: {routing.primary_agent.value} (信心度: {routing.confidence:.2f})")

        # 2. 執行工作流程
        result = self.orchestrator.execute(request)

        # 3. 更新統計
        elapsed = (time.time() - start_time) * 1000

        if self.metrics:
            # 從工作流程狀態提取各 Agent 的指標
            for role_name, state in self.orchestrator.current_workflow.agent_states.items():
                self.metrics.record_agent_call(
                    role=AgentRole(role_name),
                    tokens=state.tokens_consumed,
                    latency_ms=elapsed / len(self.orchestrator.current_workflow.agent_states),
                    success=state.status == TaskStatus.COMPLETED
                )

        # 4. 返回結果
        return {
            "status": result["status"],
            "output": result.get("final_output", ""),
            "total_tokens": result.get("total_tokens", 0),
            "elapsed_ms": elapsed,
            "routing": {
                "category": routing.category.value,
                "primary_agent": routing.primary_agent.value,
                "confidence": routing.confidence
            },
            "workflow_id": result.get("workflow_id")
        }

    def get_metrics_report(self) -> str:
        """取得監控報告"""
        if self.metrics:
            return self.metrics.get_report()
        return "監控未啟用"


# 使用範例
if __name__ == "__main__":
    team = ProductionAgentTeam(token_budget=30000)

    # 處理請求
    result = team.process_request("""
    開發一個簡單的 REST API：
    - 使用者註冊和登入
    - JWT 認證
    - 基本的 CRUD 操作
    """)

    print(f"\n結果：")
    print(f"  狀態: {result['status']}")
    print(f"  Tokens: {result['total_tokens']:,}")
    print(f"  延遲: {result['elapsed_ms']:.0f}ms")

    print(f"\n{team.get_metrics_report()}")
```

---

## 優化效果總結

```
專責化 + 協作優化的綜合效果：

┌─────────────────────────────────────────────────────────────────────┐
│                    優化前 vs 優化後對比                              │
├────────────────────┬───────────────┬───────────────┬────────────────┤
│ 指標               │ 優化前        │ 優化後        │ 改善           │
│                    │ (通用 Agent)  │ (專責+協作)   │                │
├────────────────────┼───────────────┼───────────────┼────────────────┤
│ System Prompt      │ 16,000 tok    │ 2,500 tok     │ -84%           │
│ 工具定義           │ 5,000 tok     │ 800 tok       │ -84%           │
│ 每任務固定成本     │ 21,000 tok    │ 3,300 tok     │ -84%           │
│ 協調開銷           │ 0             │ +1,500 tok    │ +1,500         │
│ 淨節省             │ -             │ -             │ -80%           │
├────────────────────┼───────────────┼───────────────┼────────────────┤
│ 5 任務總成本       │ 105,000 tok   │ 23,000 tok    │ -78%           │
│ 10 任務總成本      │ 210,000 tok   │ 43,000 tok    │ -80%           │
└────────────────────┴───────────────┴───────────────┴────────────────┘

額外效益：
✅ 模型差異化選擇：簡單任務用 Haiku，再省 50%+
✅ 並行執行：延遲降低 50-70%
✅ 錯誤隔離：單一 Agent 失敗不影響整體
✅ 可觀測性：精確追蹤各環節消耗
```

---

## 最佳實踐清單

```
專責化 Agent 協作 Checklist：

架構選擇
□ 根據任務特性選擇協作模式（Hub-Spoke / Pipeline / Parallel）
□ 確認協調開銷小於專責化節省
□ 設計清晰的 Agent 邊界和介面

路由設計
□ 實作關鍵字快速分類
□ 可選：LLM 精確分類（作為後備）
□ 持續優化分類準確度

狀態管理
□ 追蹤每個 Agent 的執行狀態
□ 支援斷點續傳
□ 定義步驟關鍵性（critical / optional）

錯誤處理
□ 實作重試機制（帶指數退避）
□ 定義降級策略
□ 適當的錯誤傳播和中止條件

資源管理
□ 設定 Token 預算上限
□ 各 Agent 獨立預算控制
□ 預留協調開銷空間

監控
□ 追蹤各 Agent 的 Token 消耗
□ 追蹤延遲和錯誤率
□ 定期審查和優化
```

---

## 總結

專責化 Agent 的協作設計是發揮其最大價值的關鍵。本文介紹的協作模式涵蓋：

| 模式 | 適用場景 | Token 效率 | 延遲 |
|------|----------|-----------|------|
| Hub-and-Spoke | 一般任務 | 高 | 中 |
| Pipeline | 順序依賴 | 高 | 高 |
| Parallel | 獨立子任務 | 高 | 低 |
| Adaptive | 混合場景 | 最高 | 可變 |

核心原則：

1. **最小化協調開銷**：確保協調成本小於專責化節省
2. **精準的 Context 傳遞**：只傳遞必要的摘要，不傳完整輸出
3. **智慧路由**：根據任務特性自動選擇最佳模式
4. **穩健的狀態管理**：支援斷點續傳和錯誤恢復
5. **持續監控優化**：數據驅動的效能調校

透過合理的協作設計，專責化 Agent 團隊可以在保持 80%+ Token 節省的同時，提供更可靠、更快速的服務。
