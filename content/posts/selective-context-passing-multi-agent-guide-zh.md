---
title: "多 Agent Token 優化系列 pt.5：選擇性 Context 傳遞 — 打造高效協作系統"
date: 2026-03-12T20:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "multi-agent", "context-passing", "token-optimization", "agent-orchestration", "API"]
summary: "多 Agent Token 優化系列 pt.5：深入探索選擇性 Context 傳遞策略，從依賴關係映射、結構化輸出到相關性過濾，提供完整實作範例，幫助你大幅降低 Agent 間通訊的 Token 消耗。"
readTime: "35 min"
---

在前一篇文章《多 Agent 系統的 Token 用量調優指南》中，我們介紹了 **選擇性 Context 傳遞** 作為多 Agent 系統中最具影響力的優化策略之一。本文將深入實作層面，探討如何在真實系統中建構精確的 Context 傳遞機制，讓每個 Agent 只接收完成任務所需的最小資訊集合。

---

## 為什麼 Context 傳遞是關鍵瓶頸？

### 多 Agent 系統的 Context 爆炸

```
傳統的完整 Context 傳遞：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Orchestrator                                                       │
│       │                                                             │
│       │ 傳遞完整 Context (30,000 tokens)                            │
│       ├─────────────────────────────────────────────────────────▶  │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent A    │ 實際只需要 2,000 tokens                            │
│  │  資料分析師  │ 浪費：28,000 tokens (93%)                          │
│  └─────────────┘                                                    │
│       │                                                             │
│       │ 傳遞完整 Context + Agent A 輸出 (35,000 tokens)             │
│       ├─────────────────────────────────────────────────────────▶  │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent B    │ 實際只需要 3,000 tokens                            │
│  │  程式開發者  │ 浪費：32,000 tokens (91%)                          │
│  └─────────────┘                                                    │
│       │                                                             │
│       │ 傳遞完整 Context + 所有輸出 (45,000 tokens)                 │
│       ├─────────────────────────────────────────────────────────▶  │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent C    │ 實際只需要 1,500 tokens                            │
│  │  文件撰寫者  │ 浪費：43,500 tokens (97%)                          │
│  └─────────────┘                                                    │
│                                                                     │
│  總 Token 消耗：110,000 tokens                                      │
│  實際所需：~6,500 tokens                                            │
│  浪費比例：94%                                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 選擇性傳遞的效益

```
優化後的選擇性 Context 傳遞：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Orchestrator                                                       │
│       │                                                             │
│       │ 只傳遞相關 Context (2,000 tokens)                           │
│       ├─────────────────▶                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent A    │ 輸出結構化摘要 (500 tokens)                        │
│  │  資料分析師  │                                                    │
│  └─────────────┘                                                    │
│       │                                                             │
│       │ 只傳遞 Agent A 摘要 + 相關需求 (3,000 tokens)               │
│       ├─────────────────▶                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent B    │ 輸出結構化結果 (800 tokens)                        │
│  │  程式開發者  │                                                    │
│  └─────────────┘                                                    │
│       │                                                             │
│       │ 只傳遞文件所需資訊 (1,500 tokens)                           │
│       ├─────────────────▶                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────┐                                                    │
│  │  Agent C    │                                                    │
│  │  文件撰寫者  │                                                    │
│  └─────────────┘                                                    │
│                                                                     │
│  總 Token 消耗：6,500 tokens                                        │
│  節省：94%                                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 核心概念：Context 依賴圖

### 定義 Agent 間的資訊依賴

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class ContextType(Enum):
    """Context 類型"""
    FULL_OUTPUT = "full_output"       # 完整輸出
    SUMMARY = "summary"               # 摘要
    KEY_FINDINGS = "key_findings"     # 關鍵發現
    STRUCTURED_DATA = "structured"    # 結構化資料
    METADATA = "metadata"             # 元資料
    NONE = "none"                     # 不需要

@dataclass
class ContextDependency:
    """Context 依賴定義"""
    source_agent: str                 # 來源 Agent
    context_type: ContextType         # 需要的 Context 類型
    required_fields: list[str] = field(default_factory=list)  # 需要的特定欄位
    max_tokens: Optional[int] = None  # 最大 token 數限制
    priority: int = 1                 # 優先級（用於裁剪）

@dataclass
class AgentContextSpec:
    """Agent 的 Context 規格"""
    agent_name: str
    dependencies: list[ContextDependency] = field(default_factory=list)
    requires_original_task: bool = True
    requires_shared_state: bool = False
    max_total_context: int = 8000     # 最大總 Context

# 定義依賴關係圖
CONTEXT_DEPENDENCY_GRAPH = {
    "orchestrator": AgentContextSpec(
        agent_name="orchestrator",
        dependencies=[],  # Orchestrator 接收原始請求
        requires_original_task=True,
        max_total_context=4000
    ),

    "requirements_analyst": AgentContextSpec(
        agent_name="requirements_analyst",
        dependencies=[],  # 只需要原始任務
        requires_original_task=True,
        max_total_context=6000
    ),

    "architect": AgentContextSpec(
        agent_name="architect",
        dependencies=[
            ContextDependency(
                source_agent="requirements_analyst",
                context_type=ContextType.KEY_FINDINGS,
                required_fields=["functional_requirements", "non_functional_requirements"],
                max_tokens=1500
            )
        ],
        requires_original_task=True,
        max_total_context=8000
    ),

    "developer": AgentContextSpec(
        agent_name="developer",
        dependencies=[
            ContextDependency(
                source_agent="requirements_analyst",
                context_type=ContextType.SUMMARY,
                max_tokens=500
            ),
            ContextDependency(
                source_agent="architect",
                context_type=ContextType.STRUCTURED_DATA,
                required_fields=["architecture_decision", "tech_stack", "api_design"],
                max_tokens=2000
            )
        ],
        requires_original_task=False,  # 不需要原始任務
        max_total_context=10000
    ),

    "code_reviewer": AgentContextSpec(
        agent_name="code_reviewer",
        dependencies=[
            ContextDependency(
                source_agent="developer",
                context_type=ContextType.FULL_OUTPUT,  # 需要完整程式碼
                max_tokens=5000
            ),
            ContextDependency(
                source_agent="architect",
                context_type=ContextType.SUMMARY,
                required_fields=["coding_standards"],
                max_tokens=500
            )
        ],
        requires_original_task=False,
        max_total_context=8000
    ),

    "doc_writer": AgentContextSpec(
        agent_name="doc_writer",
        dependencies=[
            ContextDependency(
                source_agent="requirements_analyst",
                context_type=ContextType.KEY_FINDINGS,
                max_tokens=800
            ),
            ContextDependency(
                source_agent="architect",
                context_type=ContextType.SUMMARY,
                max_tokens=600
            ),
            ContextDependency(
                source_agent="developer",
                context_type=ContextType.METADATA,
                required_fields=["file_list", "api_endpoints", "function_signatures"],
                max_tokens=1000
            ),
            ContextDependency(
                source_agent="code_reviewer",
                context_type=ContextType.SUMMARY,
                max_tokens=400
            )
        ],
        requires_original_task=True,
        max_total_context=6000
    )
}
```

### 視覺化依賴關係

```
Agent 依賴關係圖：

                    ┌─────────────────┐
                    │  原始任務請求    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Orchestrator   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              │              │
    ┌─────────────────┐      │              │
    │ Requirements    │      │              │
    │ Analyst         │      │              │
    └────────┬────────┘      │              │
             │               │              │
     ┌───────┴───────┐       │              │
     │ KEY_FINDINGS  │       │              │
     ▼               ▼       │              │
┌─────────┐    ┌─────────┐   │              │
│Architect│    │Doc      │◀──┘              │
└────┬────┘    │Writer   │                  │
     │         └────▲────┘                  │
     │ STRUCTURED   │                       │
     ▼              │                       │
┌─────────┐        │                       │
│Developer│────────┤ METADATA              │
└────┬────┘        │                       │
     │             │                       │
     │ FULL_OUTPUT │                       │
     ▼             │                       │
┌─────────┐        │                       │
│Code     │────────┘ SUMMARY               │
│Reviewer │                                │
└─────────┘                                │

圖例：
─────▶ Context 傳遞方向
標籤為 Context 類型
```

---

## 策略一：結構化輸出格式

強制 Agent 輸出結構化資料，便於下游選擇性提取。

### 定義標準輸出格式

```python
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum

class OutputSection(Enum):
    """輸出區段類型"""
    SUMMARY = "summary"
    KEY_FINDINGS = "key_findings"
    DETAILED_ANALYSIS = "detailed_analysis"
    RECOMMENDATIONS = "recommendations"
    STRUCTURED_DATA = "structured_data"
    METADATA = "metadata"
    RAW_OUTPUT = "raw_output"

class AgentOutput(BaseModel):
    """標準化 Agent 輸出"""
    agent_name: str
    task_id: str

    # 必要的摘要區段（永遠保留）
    summary: str = Field(
        description="簡短摘要，100-200 字",
        max_length=500
    )

    # 關鍵發現（高優先級保留）
    key_findings: list[str] = Field(
        default_factory=list,
        description="關鍵發現清單，每項 50 字以內"
    )

    # 結構化資料（可選擇性提取欄位）
    structured_data: dict[str, Any] = Field(
        default_factory=dict,
        description="結構化資料，便於下游精確提取"
    )

    # 詳細內容（通常不傳遞給下游）
    detailed_output: Optional[str] = Field(
        default=None,
        description="完整詳細輸出，僅在需要時傳遞"
    )

    # 元資料（輕量級資訊）
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="執行元資料：時間、tokens、狀態等"
    )

    def get_section(self, section: OutputSection, max_tokens: Optional[int] = None) -> str:
        """取得特定區段，可選擇性截斷"""
        content = ""

        if section == OutputSection.SUMMARY:
            content = self.summary
        elif section == OutputSection.KEY_FINDINGS:
            content = "\n".join(f"- {f}" for f in self.key_findings)
        elif section == OutputSection.STRUCTURED_DATA:
            import json
            content = json.dumps(self.structured_data, ensure_ascii=False, indent=2)
        elif section == OutputSection.DETAILED_ANALYSIS:
            content = self.detailed_output or ""
        elif section == OutputSection.METADATA:
            import json
            content = json.dumps(self.metadata, ensure_ascii=False)
        elif section == OutputSection.RAW_OUTPUT:
            content = self.detailed_output or self.summary

        # 截斷處理
        if max_tokens and len(content) > max_tokens * 4:  # 粗略估算
            content = content[:max_tokens * 4] + "\n...[已截斷]"

        return content

    def to_minimal_context(self) -> str:
        """轉換為最小 Context（僅摘要和關鍵發現）"""
        parts = [f"[{self.agent_name} 輸出摘要]", self.summary]
        if self.key_findings:
            parts.append("\n關鍵發現：")
            parts.extend(f"- {f}" for f in self.key_findings[:5])
        return "\n".join(parts)

    def to_full_context(self) -> str:
        """轉換為完整 Context"""
        parts = [
            f"[{self.agent_name} 完整輸出]",
            f"\n摘要：{self.summary}",
        ]
        if self.key_findings:
            parts.append("\n關鍵發現：")
            parts.extend(f"- {f}" for f in self.key_findings)
        if self.detailed_output:
            parts.append(f"\n詳細內容：\n{self.detailed_output}")
        return "\n".join(parts)


# 特定 Agent 的輸出格式
class RequirementsAnalystOutput(AgentOutput):
    """需求分析師輸出"""
    structured_data: dict = Field(default_factory=lambda: {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "constraints": [],
        "assumptions": [],
        "user_stories": []
    })

class ArchitectOutput(AgentOutput):
    """架構師輸出"""
    structured_data: dict = Field(default_factory=lambda: {
        "architecture_decision": "",
        "tech_stack": {},
        "api_design": [],
        "data_model": {},
        "coding_standards": [],
        "deployment_strategy": ""
    })

class DeveloperOutput(AgentOutput):
    """開發者輸出"""
    structured_data: dict = Field(default_factory=lambda: {
        "file_list": [],
        "api_endpoints": [],
        "function_signatures": [],
        "dependencies": [],
        "code_files": {}
    })

class CodeReviewerOutput(AgentOutput):
    """程式碼審查者輸出"""
    structured_data: dict = Field(default_factory=lambda: {
        "issues": [],
        "suggestions": [],
        "security_concerns": [],
        "performance_notes": [],
        "approval_status": ""
    })
```

### Agent 輸出格式化器

```python
import anthropic
import json
from typing import Type

client = anthropic.Anthropic()

class StructuredOutputAgent:
    """
    強制結構化輸出的 Agent

    確保輸出符合標準格式，便於下游選擇性提取
    """

    OUTPUT_FORMAT_PROMPT = """
你必須以以下 JSON 格式輸出結果：

{{
    "summary": "簡短摘要（100-200字）",
    "key_findings": ["發現1", "發現2", ...],
    "structured_data": {{
        // 根據任務類型的結構化資料
        {structured_fields}
    }},
    "detailed_output": "完整詳細內容（可選）"
}}

重要：只輸出 JSON，不要其他說明。
"""

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        output_class: Type[AgentOutput] = AgentOutput,
        model: str = "claude-sonnet-4-20250514"
    ):
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.output_class = output_class
        self.model = model

    def _get_structured_fields_hint(self) -> str:
        """取得結構化欄位提示"""
        if self.output_class == RequirementsAnalystOutput:
            return """
        "functional_requirements": ["需求1", "需求2"],
        "non_functional_requirements": ["效能要求", "安全要求"],
        "constraints": ["限制1"],
        "user_stories": ["作為...我想要...以便..."]
"""
        elif self.output_class == ArchitectOutput:
            return """
        "architecture_decision": "架構決策說明",
        "tech_stack": {"backend": "...", "frontend": "...", "database": "..."},
        "api_design": [{"endpoint": "/api/...", "method": "GET", "description": "..."}],
        "coding_standards": ["標準1", "標準2"]
"""
        elif self.output_class == DeveloperOutput:
            return """
        "file_list": ["file1.py", "file2.py"],
        "api_endpoints": ["/api/endpoint1", "/api/endpoint2"],
        "function_signatures": ["def func1(a: int) -> str", ...],
        "code_files": {"filename.py": "code content..."}
"""
        elif self.output_class == CodeReviewerOutput:
            return """
        "issues": [{"severity": "high/medium/low", "description": "..."}],
        "suggestions": ["建議1", "建議2"],
        "security_concerns": ["安全問題1"],
        "approval_status": "approved/needs_revision/rejected"
"""
        return "{}"

    def execute(self, task: str, context: str = "") -> AgentOutput:
        """執行任務並返回結構化輸出"""
        format_prompt = self.OUTPUT_FORMAT_PROMPT.format(
            structured_fields=self._get_structured_fields_hint()
        )

        full_prompt = f"{context}\n\n任務：{task}\n\n{format_prompt}" if context else f"任務：{task}\n\n{format_prompt}"

        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.system_prompt,
            messages=[{"role": "user", "content": full_prompt}]
        )

        # 解析輸出
        output_text = response.content[0].text
        try:
            # 處理可能的 markdown 程式碼區塊
            if "```json" in output_text:
                output_text = output_text.split("```json")[1].split("```")[0]
            elif "```" in output_text:
                output_text = output_text.split("```")[1].split("```")[0]

            data = json.loads(output_text.strip())

            return self.output_class(
                agent_name=self.agent_name,
                task_id="",  # 由呼叫者設定
                summary=data.get("summary", ""),
                key_findings=data.get("key_findings", []),
                structured_data=data.get("structured_data", {}),
                detailed_output=data.get("detailed_output"),
                metadata={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                }
            )
        except (json.JSONDecodeError, KeyError) as e:
            # 降級處理：將原始輸出作為 detailed_output
            return self.output_class(
                agent_name=self.agent_name,
                task_id="",
                summary=output_text[:200] + "..." if len(output_text) > 200 else output_text,
                key_findings=[],
                structured_data={},
                detailed_output=output_text,
                metadata={"parse_error": str(e)}
            )
```

---

## 策略二：Context 提取器

根據下游 Agent 的需求，從上游輸出中精確提取所需資訊。

### 完整實作

```python
import anthropic
from dataclasses import dataclass
from typing import Optional

client = anthropic.Anthropic()

@dataclass
class ExtractionRequest:
    """提取請求"""
    source_output: AgentOutput
    target_agent: str
    dependency: ContextDependency

class ContextExtractor:
    """
    Context 提取器

    根據依賴規格從 Agent 輸出中提取所需資訊
    """

    def __init__(self, use_llm_extraction: bool = True):
        """
        Args:
            use_llm_extraction: 是否使用 LLM 進行智能提取（更準確但有成本）
        """
        self.use_llm_extraction = use_llm_extraction

    def extract(self, request: ExtractionRequest) -> str:
        """
        從來源輸出提取目標 Agent 所需的 Context
        """
        source = request.source_output
        dep = request.dependency

        # 根據 Context 類型選擇提取策略
        if dep.context_type == ContextType.NONE:
            return ""

        elif dep.context_type == ContextType.SUMMARY:
            return self._extract_summary(source, dep)

        elif dep.context_type == ContextType.KEY_FINDINGS:
            return self._extract_key_findings(source, dep)

        elif dep.context_type == ContextType.STRUCTURED_DATA:
            return self._extract_structured_data(source, dep)

        elif dep.context_type == ContextType.METADATA:
            return self._extract_metadata(source, dep)

        elif dep.context_type == ContextType.FULL_OUTPUT:
            return self._extract_full_output(source, dep)

        return source.to_minimal_context()

    def _extract_summary(self, source: AgentOutput, dep: ContextDependency) -> str:
        """提取摘要"""
        content = f"[{source.agent_name} 摘要]\n{source.summary}"
        return self._truncate(content, dep.max_tokens)

    def _extract_key_findings(self, source: AgentOutput, dep: ContextDependency) -> str:
        """提取關鍵發現"""
        parts = [f"[{source.agent_name} 關鍵發現]"]

        # 如果指定了特定欄位，只提取那些欄位
        if dep.required_fields:
            for field in dep.required_fields:
                if field in source.structured_data:
                    value = source.structured_data[field]
                    if isinstance(value, list):
                        parts.append(f"\n{field}:")
                        parts.extend(f"  - {item}" for item in value[:10])
                    else:
                        parts.append(f"\n{field}: {value}")
        else:
            # 提取所有關鍵發現
            for finding in source.key_findings[:10]:
                parts.append(f"- {finding}")

        content = "\n".join(parts)
        return self._truncate(content, dep.max_tokens)

    def _extract_structured_data(self, source: AgentOutput, dep: ContextDependency) -> str:
        """提取結構化資料"""
        import json

        if dep.required_fields:
            # 只提取指定欄位
            extracted = {}
            for field in dep.required_fields:
                if field in source.structured_data:
                    extracted[field] = source.structured_data[field]
            data = extracted
        else:
            data = source.structured_data

        content = f"[{source.agent_name} 結構化資料]\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        return self._truncate(content, dep.max_tokens)

    def _extract_metadata(self, source: AgentOutput, dep: ContextDependency) -> str:
        """提取元資料"""
        import json

        if dep.required_fields:
            # 從 structured_data 中提取指定的元資料欄位
            extracted = {}
            for field in dep.required_fields:
                if field in source.structured_data:
                    extracted[field] = source.structured_data[field]
            data = extracted
        else:
            data = source.metadata

        content = f"[{source.agent_name} 元資料]\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        return self._truncate(content, dep.max_tokens)

    def _extract_full_output(self, source: AgentOutput, dep: ContextDependency) -> str:
        """提取完整輸出"""
        content = source.to_full_context()
        return self._truncate(content, dep.max_tokens)

    def _truncate(self, content: str, max_tokens: Optional[int]) -> str:
        """截斷內容"""
        if max_tokens is None:
            return content
        # 粗略估算：1 token ≈ 4 字元（中英混合）
        max_chars = max_tokens * 3
        if len(content) > max_chars:
            return content[:max_chars] + "\n...[已截斷]"
        return content

    def extract_with_llm(
        self,
        source: AgentOutput,
        target_agent: str,
        extraction_prompt: str
    ) -> str:
        """
        使用 LLM 進行智能提取

        適用於需要更精確理解和提取的情況
        """
        prompt = f"""從以下 Agent 輸出中提取 {target_agent} 所需的資訊。

來源 Agent：{source.agent_name}
來源輸出：
{source.to_full_context()}

提取要求：
{extraction_prompt}

請只輸出提取後的內容，保持簡潔。"""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # 使用便宜模型做提取
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text


class ContextBuilder:
    """
    Context 建構器

    根據依賴圖為目標 Agent 建構完整的 Context
    """

    def __init__(
        self,
        dependency_graph: dict[str, AgentContextSpec],
        extractor: Optional[ContextExtractor] = None
    ):
        self.dependency_graph = dependency_graph
        self.extractor = extractor or ContextExtractor()
        self._output_store: dict[str, AgentOutput] = {}

    def store_output(self, output: AgentOutput):
        """儲存 Agent 輸出"""
        self._output_store[output.agent_name] = output

    def build_context(
        self,
        target_agent: str,
        original_task: str
    ) -> str:
        """
        為目標 Agent 建構 Context

        Args:
            target_agent: 目標 Agent 名稱
            original_task: 原始任務描述

        Returns:
            建構好的 Context 字串
        """
        spec = self.dependency_graph.get(target_agent)
        if not spec:
            return original_task

        context_parts = []
        total_tokens = 0

        # 1. 添加原始任務（如果需要）
        if spec.requires_original_task:
            task_context = f"[原始任務]\n{original_task}"
            context_parts.append(task_context)
            total_tokens += len(task_context) // 3  # 粗略估算

        # 2. 按優先級排序依賴
        sorted_deps = sorted(spec.dependencies, key=lambda d: d.priority, reverse=True)

        # 3. 提取每個依賴的 Context
        for dep in sorted_deps:
            if dep.source_agent not in self._output_store:
                continue

            source_output = self._output_store[dep.source_agent]

            request = ExtractionRequest(
                source_output=source_output,
                target_agent=target_agent,
                dependency=dep
            )

            extracted = self.extractor.extract(request)

            # 檢查是否會超過總限制
            extracted_tokens = len(extracted) // 3
            if total_tokens + extracted_tokens > spec.max_total_context:
                # 嘗試截斷
                remaining = spec.max_total_context - total_tokens
                if remaining > 100:
                    extracted = extracted[:remaining * 3] + "\n...[已截斷]"
                else:
                    continue  # 跳過這個依賴

            context_parts.append(extracted)
            total_tokens += extracted_tokens

        return "\n\n---\n\n".join(context_parts)

    def get_context_stats(self, target_agent: str) -> dict:
        """取得 Context 統計"""
        spec = self.dependency_graph.get(target_agent)
        if not spec:
            return {}

        stats = {
            "target_agent": target_agent,
            "max_total_context": spec.max_total_context,
            "dependencies": []
        }

        for dep in spec.dependencies:
            dep_info = {
                "source": dep.source_agent,
                "type": dep.context_type.value,
                "max_tokens": dep.max_tokens,
                "available": dep.source_agent in self._output_store
            }
            stats["dependencies"].append(dep_info)

        return stats
```

---

## 策略三：相關性過濾

使用 LLM 判斷哪些資訊與目標任務相關。

### 完整實作

```python
import anthropic
import json
from dataclasses import dataclass
from typing import Optional

client = anthropic.Anthropic()

@dataclass
class RelevanceScore:
    """相關性評分"""
    content: str
    score: float  # 0-1
    reason: str
    should_include: bool

class RelevanceFilter:
    """
    相關性過濾器

    使用 LLM 判斷內容與目標任務的相關性，
    只保留高相關性的內容
    """

    RELEVANCE_PROMPT = """分析以下內容與目標任務的相關性。

目標任務：
{task}

目標 Agent：{target_agent}
目標 Agent 職責：{agent_role}

待評估內容：
{content}

請以 JSON 格式評估相關性：
{{
    "score": 0.0-1.0,
    "reason": "簡短說明",
    "key_relevant_parts": ["相關部分1", "相關部分2"],
    "irrelevant_parts": ["不相關部分1"]
}}

評分標準：
- 1.0: 完全相關，必須包含
- 0.7-0.9: 高度相關，建議包含
- 0.4-0.6: 部分相關，可選包含
- 0.1-0.3: 低相關，通常不需要
- 0.0: 完全不相關

只返回 JSON。"""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",
        relevance_threshold: float = 0.5
    ):
        self.model = model
        self.relevance_threshold = relevance_threshold
        self._cache: dict[str, RelevanceScore] = {}

    def _compute_cache_key(self, task: str, content: str) -> str:
        import hashlib
        combined = f"{task[:100]}|{content[:200]}"
        return hashlib.md5(combined.encode()).hexdigest()

    def score_relevance(
        self,
        content: str,
        task: str,
        target_agent: str,
        agent_role: str
    ) -> RelevanceScore:
        """評估內容相關性"""
        # 檢查快取
        cache_key = self._compute_cache_key(task, content)
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = self.RELEVANCE_PROMPT.format(
            task=task,
            target_agent=target_agent,
            agent_role=agent_role,
            content=content[:3000]  # 限制長度
        )

        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].split("```")[0]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())

            result = RelevanceScore(
                content=content,
                score=data.get("score", 0.5),
                reason=data.get("reason", ""),
                should_include=data.get("score", 0.5) >= self.relevance_threshold
            )
        except (json.JSONDecodeError, KeyError):
            result = RelevanceScore(
                content=content,
                score=0.5,
                reason="評估失敗，使用預設值",
                should_include=True
            )

        self._cache[cache_key] = result
        return result

    def filter_context_parts(
        self,
        parts: list[str],
        task: str,
        target_agent: str,
        agent_role: str,
        max_parts: Optional[int] = None
    ) -> list[str]:
        """
        過濾 Context 部分，只保留相關內容

        Args:
            parts: Context 片段列表
            task: 目標任務
            target_agent: 目標 Agent
            agent_role: Agent 職責描述
            max_parts: 最多保留幾個部分

        Returns:
            過濾後的 Context 片段列表
        """
        scored_parts = []

        for part in parts:
            if not part.strip():
                continue
            score = self.score_relevance(part, task, target_agent, agent_role)
            if score.should_include:
                scored_parts.append((score.score, part))

        # 按相關性排序
        scored_parts.sort(key=lambda x: x[0], reverse=True)

        # 限制數量
        if max_parts:
            scored_parts = scored_parts[:max_parts]

        return [part for _, part in scored_parts]


class SmartContextFilter:
    """
    智能 Context 過濾器

    結合規則和 LLM 的混合過濾策略
    """

    # 不同 Agent 角色的關鍵字
    AGENT_KEYWORDS = {
        "developer": ["程式", "code", "實作", "implement", "API", "函數", "class"],
        "architect": ["架構", "architecture", "設計", "design", "模式", "pattern"],
        "reviewer": ["審查", "review", "問題", "issue", "建議", "suggestion"],
        "doc_writer": ["文件", "document", "說明", "description", "API", "用法"],
        "tester": ["測試", "test", "用例", "case", "驗證", "verify"]
    }

    def __init__(
        self,
        use_llm_filter: bool = True,
        relevance_threshold: float = 0.5
    ):
        self.use_llm_filter = use_llm_filter
        self.llm_filter = RelevanceFilter(relevance_threshold=relevance_threshold) if use_llm_filter else None

    def _keyword_filter(self, content: str, target_agent: str) -> bool:
        """基於關鍵字的快速過濾"""
        keywords = self.AGENT_KEYWORDS.get(target_agent, [])
        if not keywords:
            return True
        content_lower = content.lower()
        return any(kw.lower() in content_lower for kw in keywords)

    def filter(
        self,
        context_parts: list[str],
        task: str,
        target_agent: str,
        agent_role: str
    ) -> list[str]:
        """
        智能過濾 Context

        流程：
        1. 關鍵字快速過濾
        2. LLM 相關性評估（如果啟用）
        """
        # 階段 1：關鍵字快速過濾
        keyword_filtered = [
            part for part in context_parts
            if self._keyword_filter(part, target_agent)
        ]

        # 如果過濾後內容很少，保留全部
        if len(keyword_filtered) <= 2:
            keyword_filtered = context_parts

        # 階段 2：LLM 相關性過濾
        if self.use_llm_filter and self.llm_filter:
            return self.llm_filter.filter_context_parts(
                keyword_filtered,
                task,
                target_agent,
                agent_role,
                max_parts=5
            )

        return keyword_filtered
```

---

## 策略四：完整的多 Agent 協調系統

整合所有策略的生產級系統。

### 系統架構

```
完整的選擇性 Context 傳遞系統：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                        Orchestrator                                 │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                                                               │ │
│  │  1. 任務解析與規劃                                            │ │
│  │  2. Agent 調度                                                │ │
│  │  3. 結果整合                                                  │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                  Context Manager                              │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │ │
│  │  │ Dependency  │  │  Context    │  │ Relevance   │           │ │
│  │  │ Graph       │  │  Extractor  │  │ Filter      │           │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │ │
│  │                                                               │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │ │
│  │  │ Output      │  │  Context    │  │ Token       │           │ │
│  │  │ Store       │  │  Builder    │  │ Counter     │           │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│              ┌───────────────┼───────────────┐                     │
│              │               │               │                      │
│              ▼               ▼               ▼                      │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │    Agent A      │ │    Agent B      │ │    Agent C      │       │
│  │  (結構化輸出)   │ │  (結構化輸出)   │ │  (結構化輸出)   │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
import json
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
import time

client = anthropic.Anthropic()

@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    role: str
    system_prompt: str
    output_class: type = AgentOutput
    model: str = "claude-sonnet-4-20250514"
    max_output_tokens: int = 4096

@dataclass
class TaskResult:
    """任務執行結果"""
    task_id: str
    agent_name: str
    output: AgentOutput
    context_tokens_used: int
    output_tokens: int
    execution_time_ms: float
    success: bool
    error: Optional[str] = None

class SelectiveContextOrchestrator:
    """
    選擇性 Context 傳遞的 Multi-Agent Orchestrator

    核心功能：
    1. 管理 Agent 依賴關係
    2. 建構最小化 Context
    3. 協調 Agent 執行
    4. 追蹤 Token 使用
    """

    def __init__(
        self,
        dependency_graph: dict[str, AgentContextSpec],
        enable_relevance_filter: bool = True,
        enable_smart_extraction: bool = True
    ):
        self.dependency_graph = dependency_graph

        # 核心組件
        self.context_builder = ContextBuilder(dependency_graph)
        self.extractor = ContextExtractor(use_llm_extraction=enable_smart_extraction)
        self.relevance_filter = SmartContextFilter(use_llm_filter=enable_relevance_filter)

        # Agent 註冊表
        self.agents: dict[str, AgentConfig] = {}

        # 執行記錄
        self._execution_history: list[TaskResult] = []
        self._stats = {
            "total_context_tokens": 0,
            "total_output_tokens": 0,
            "context_tokens_saved": 0,
            "agents_executed": 0
        }

    def register_agent(self, config: AgentConfig):
        """註冊 Agent"""
        self.agents[config.name] = config

    def _create_agent_executor(self, config: AgentConfig) -> StructuredOutputAgent:
        """創建 Agent 執行器"""
        return StructuredOutputAgent(
            agent_name=config.name,
            system_prompt=config.system_prompt,
            output_class=config.output_class,
            model=config.model
        )

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 數"""
        return len(text) // 3  # 粗略估算

    def _build_optimized_context(
        self,
        target_agent: str,
        original_task: str
    ) -> tuple[str, int, int]:
        """
        建構優化的 Context

        Returns:
            (context, actual_tokens, potential_tokens_without_optimization)
        """
        spec = self.dependency_graph.get(target_agent)
        agent_config = self.agents.get(target_agent)

        if not spec or not agent_config:
            return original_task, self._estimate_tokens(original_task), self._estimate_tokens(original_task)

        # 收集所有可能的 Context
        all_context_parts = []
        potential_tokens = 0

        # 原始任務
        if spec.requires_original_task:
            all_context_parts.append(f"[原始任務]\n{original_task}")

        # 從依賴中提取
        for dep in spec.dependencies:
            if dep.source_agent not in self.context_builder._output_store:
                continue

            source_output = self.context_builder._output_store[dep.source_agent]

            # 計算未優化情況下的 tokens（完整輸出）
            full_context = source_output.to_full_context()
            potential_tokens += self._estimate_tokens(full_context)

            # 提取優化後的 Context
            request = ExtractionRequest(
                source_output=source_output,
                target_agent=target_agent,
                dependency=dep
            )
            extracted = self.extractor.extract(request)
            all_context_parts.append(extracted)

        # 相關性過濾
        filtered_parts = self.relevance_filter.filter(
            all_context_parts,
            original_task,
            target_agent,
            agent_config.role
        )

        # 組合最終 Context
        final_context = "\n\n---\n\n".join(filtered_parts)

        # 確保不超過限制
        max_tokens = spec.max_total_context
        actual_tokens = self._estimate_tokens(final_context)

        if actual_tokens > max_tokens:
            # 截斷
            final_context = final_context[:max_tokens * 3] + "\n...[Context 已截斷]"
            actual_tokens = max_tokens

        return final_context, actual_tokens, potential_tokens

    def execute_agent(
        self,
        agent_name: str,
        original_task: str,
        task_id: str = ""
    ) -> TaskResult:
        """
        執行單個 Agent

        自動建構最小化 Context 並執行
        """
        start_time = time.time()

        agent_config = self.agents.get(agent_name)
        if not agent_config:
            return TaskResult(
                task_id=task_id,
                agent_name=agent_name,
                output=AgentOutput(agent_name=agent_name, task_id=task_id, summary=""),
                context_tokens_used=0,
                output_tokens=0,
                execution_time_ms=0,
                success=False,
                error=f"Agent {agent_name} 未註冊"
            )

        # 建構優化 Context
        context, actual_tokens, potential_tokens = self._build_optimized_context(
            agent_name, original_task
        )

        # 執行 Agent
        executor = self._create_agent_executor(agent_config)

        try:
            output = executor.execute(original_task, context)
            output.task_id = task_id

            # 儲存輸出供下游使用
            self.context_builder.store_output(output)

            execution_time = (time.time() - start_time) * 1000
            output_tokens = output.metadata.get("output_tokens", 0)

            # 更新統計
            self._stats["total_context_tokens"] += actual_tokens
            self._stats["total_output_tokens"] += output_tokens
            self._stats["context_tokens_saved"] += (potential_tokens - actual_tokens)
            self._stats["agents_executed"] += 1

            result = TaskResult(
                task_id=task_id,
                agent_name=agent_name,
                output=output,
                context_tokens_used=actual_tokens,
                output_tokens=output_tokens,
                execution_time_ms=execution_time,
                success=True
            )

        except Exception as e:
            result = TaskResult(
                task_id=task_id,
                agent_name=agent_name,
                output=AgentOutput(agent_name=agent_name, task_id=task_id, summary=""),
                context_tokens_used=actual_tokens,
                output_tokens=0,
                execution_time_ms=(time.time() - start_time) * 1000,
                success=False,
                error=str(e)
            )

        self._execution_history.append(result)
        return result

    def execute_pipeline(
        self,
        original_task: str,
        agent_sequence: list[str],
        task_id: str = ""
    ) -> list[TaskResult]:
        """
        執行 Agent 管線

        按順序執行多個 Agent，自動傳遞 Context
        """
        results = []

        for i, agent_name in enumerate(agent_sequence):
            print(f"\n{'='*50}")
            print(f"執行 Agent {i+1}/{len(agent_sequence)}: {agent_name}")
            print(f"{'='*50}")

            result = self.execute_agent(
                agent_name,
                original_task,
                task_id=f"{task_id}_{i}" if task_id else str(i)
            )

            results.append(result)

            if result.success:
                print(f"✅ 成功")
                print(f"   Context tokens: {result.context_tokens_used}")
                print(f"   Output tokens: {result.output_tokens}")
                print(f"   執行時間: {result.execution_time_ms:.0f}ms")
            else:
                print(f"❌ 失敗: {result.error}")

        return results

    def get_stats(self) -> dict:
        """取得統計資訊"""
        total_potential = self._stats["total_context_tokens"] + self._stats["context_tokens_saved"]
        savings_pct = (
            self._stats["context_tokens_saved"] / total_potential * 100
            if total_potential > 0 else 0
        )

        return {
            **self._stats,
            "total_tokens": self._stats["total_context_tokens"] + self._stats["total_output_tokens"],
            "context_savings_pct": f"{savings_pct:.1f}%",
            "execution_count": len(self._execution_history)
        }

    def get_execution_summary(self) -> str:
        """取得執行摘要"""
        lines = ["執行摘要：", ""]

        for result in self._execution_history:
            status = "✅" if result.success else "❌"
            lines.append(
                f"{status} {result.agent_name}: "
                f"Context {result.context_tokens_used} tok, "
                f"Output {result.output_tokens} tok, "
                f"{result.execution_time_ms:.0f}ms"
            )

        lines.append("")
        stats = self.get_stats()
        lines.append(f"總 Context tokens: {stats['total_context_tokens']}")
        lines.append(f"總 Output tokens: {stats['total_output_tokens']}")
        lines.append(f"Context 節省: {stats['context_savings_pct']}")

        return "\n".join(lines)


# 使用範例
def create_development_pipeline() -> SelectiveContextOrchestrator:
    """創建軟體開發管線"""

    orchestrator = SelectiveContextOrchestrator(
        dependency_graph=CONTEXT_DEPENDENCY_GRAPH,
        enable_relevance_filter=True,
        enable_smart_extraction=True
    )

    # 註冊 Agents
    orchestrator.register_agent(AgentConfig(
        name="requirements_analyst",
        role="需求分析師，負責理解和整理使用者需求",
        system_prompt="""你是專業的需求分析師。
分析使用者需求，產出結構化的需求文件。
重點關注：功能需求、非功能需求、限制條件、使用者故事。""",
        output_class=RequirementsAnalystOutput
    ))

    orchestrator.register_agent(AgentConfig(
        name="architect",
        role="系統架構師，負責設計系統架構和技術選型",
        system_prompt="""你是資深系統架構師。
根據需求設計系統架構，包括技術選型、API 設計、資料模型。
考慮可擴展性、可維護性、效能需求。""",
        output_class=ArchitectOutput
    ))

    orchestrator.register_agent(AgentConfig(
        name="developer",
        role="軟體開發者，負責實作程式碼",
        system_prompt="""你是資深軟體開發者。
根據架構設計實作乾淨、可維護的程式碼。
遵循最佳實踐和程式碼規範。""",
        output_class=DeveloperOutput
    ))

    orchestrator.register_agent(AgentConfig(
        name="code_reviewer",
        role="程式碼審查者，負責審查程式碼品質",
        system_prompt="""你是程式碼審查專家。
審查程式碼的品質、安全性、效能和可維護性。
提供具體的改進建議。""",
        output_class=CodeReviewerOutput,
        model="claude-3-5-haiku-20241022"  # 審查用較輕量模型
    ))

    orchestrator.register_agent(AgentConfig(
        name="doc_writer",
        role="技術文件撰寫者，負責撰寫文件",
        system_prompt="""你是技術文件撰寫專家。
撰寫清晰、完整的技術文件。
包括 API 文件、使用說明、架構說明。""",
        model="claude-3-5-haiku-20241022"
    ))

    return orchestrator


if __name__ == "__main__":
    # 創建管線
    orchestrator = create_development_pipeline()

    # 執行任務
    task = """
    開發一個簡單的待辦事項 API，需要：
    1. CRUD 操作（建立、讀取、更新、刪除待辦事項）
    2. 使用者認證（JWT）
    3. 待辦事項可以設定優先級和截止日期
    4. 支援分頁查詢
    """

    results = orchestrator.execute_pipeline(
        original_task=task,
        agent_sequence=[
            "requirements_analyst",
            "architect",
            "developer",
            "code_reviewer",
            "doc_writer"
        ],
        task_id="todo_api"
    )

    print("\n" + "="*60)
    print(orchestrator.get_execution_summary())
```

---

## 進階：動態依賴調整

根據任務類型動態調整依賴關係。

```python
from typing import Callable

class DynamicDependencyManager:
    """
    動態依賴管理器

    根據任務特性動態調整 Agent 間的依賴關係
    """

    def __init__(self, base_graph: dict[str, AgentContextSpec]):
        self.base_graph = base_graph
        self.modifiers: list[Callable[[str, dict], dict]] = []

    def add_modifier(self, modifier: Callable[[str, dict], dict]):
        """添加依賴修改器"""
        self.modifiers.append(modifier)

    def get_graph_for_task(self, task: str) -> dict[str, AgentContextSpec]:
        """根據任務取得調整後的依賴圖"""
        import copy
        graph = copy.deepcopy(self.base_graph)

        for modifier in self.modifiers:
            graph = modifier(task, graph)

        return graph


def security_focused_modifier(task: str, graph: dict) -> dict:
    """安全敏感任務的修改器"""
    security_keywords = ["安全", "認證", "加密", "權限", "security", "auth"]

    if any(kw in task.lower() for kw in security_keywords):
        # 增加 code_reviewer 對 architect 的依賴
        if "code_reviewer" in graph:
            graph["code_reviewer"].dependencies.append(
                ContextDependency(
                    source_agent="architect",
                    context_type=ContextType.STRUCTURED_DATA,
                    required_fields=["security_requirements"],
                    max_tokens=1000,
                    priority=2
                )
            )
        # 增加最大 context 限制
        if "developer" in graph:
            graph["developer"].max_total_context = 15000

    return graph


def simple_task_modifier(task: str, graph: dict) -> dict:
    """簡單任務的修改器"""
    simple_indicators = ["簡單", "基本", "simple", "basic", "小型"]

    if any(ind in task.lower() for ind in simple_indicators):
        # 簡化依賴
        for spec in graph.values():
            spec.max_total_context = min(spec.max_total_context, 4000)
            # 只保留 SUMMARY 類型的依賴
            spec.dependencies = [
                dep for dep in spec.dependencies
                if dep.context_type in [ContextType.SUMMARY, ContextType.KEY_FINDINGS]
            ]

    return graph


# 使用範例
def create_adaptive_orchestrator(task: str) -> SelectiveContextOrchestrator:
    """創建自適應的 Orchestrator"""

    manager = DynamicDependencyManager(CONTEXT_DEPENDENCY_GRAPH)
    manager.add_modifier(security_focused_modifier)
    manager.add_modifier(simple_task_modifier)

    adapted_graph = manager.get_graph_for_task(task)

    return SelectiveContextOrchestrator(
        dependency_graph=adapted_graph,
        enable_relevance_filter=True
    )
```

---

## 效能比較與分析

```
選擇性 Context 傳遞效益分析：

┌─────────────────────────────────────────────────────────────────────┐
│                    Token 使用量對比                                  │
├──────────────────┬──────────────┬──────────────┬───────────────────┤
│ 場景             │ 完整傳遞     │ 選擇性傳遞   │ 節省              │
├──────────────────┼──────────────┼──────────────┼───────────────────┤
│ 5 Agent 管線     │ 150,000 tok  │ 25,000 tok   │ 83%               │
│ 10 Agent 管線    │ 450,000 tok  │ 55,000 tok   │ 88%               │
│ 複雜專案開發     │ 800,000 tok  │ 95,000 tok   │ 88%               │
│ 簡單任務         │ 30,000 tok   │ 8,000 tok    │ 73%               │
└──────────────────┴──────────────┴──────────────┴───────────────────┘

成本節省計算（假設 Sonnet $3/1M input tokens）：

場景：每日 100 個 5-Agent 管線任務

完整傳遞：100 × 150,000 × $3 / 1M = $45/天 = $1,350/月
選擇性傳遞：100 × 25,000 × $3 / 1M = $7.5/天 = $225/月

月度節省：$1,125（83%）
```

---

## 最佳實踐清單

```
選擇性 Context 傳遞 Checklist：

依賴設計
□ 是否明確定義了每個 Agent 的依賴關係？
□ 是否為每個依賴指定了 Context 類型？
□ 是否設定了合理的 max_tokens 限制？

輸出格式
□ Agent 輸出是否結構化？
□ 是否區分了 summary 和 detailed_output？
□ 是否定義了 structured_data 的欄位？

提取策略
□ 是否只提取下游 Agent 真正需要的資訊？
□ 是否使用了相關性過濾？
□ 是否處理了 Context 超長的情況？

效能監控
□ 是否追蹤每個 Agent 的 Context tokens？
□ 是否計算節省的 tokens 數量？
□ 是否有 Token 使用警報？

品質保障
□ 過濾後的 Context 是否足夠支援任務？
□ 是否有機制在需要時請求更多 Context？
□ 是否驗證了 Agent 輸出品質？
```

---

## 總結

選擇性 Context 傳遞是多 Agent 系統中最具影響力的優化策略，可以節省 70-95% 的 Context tokens。本文介紹的方案涵蓋：

| 策略 | 節省效果 | 實作複雜度 | 適用場景 |
|------|----------|------------|----------|
| 結構化輸出 | 中 | 低 | 所有場景 |
| Context 提取 | 高 | 中 | 明確依賴 |
| 相關性過濾 | 高 | 中高 | 動態任務 |
| 完整系統 | 最高 | 高 | 生產環境 |

關鍵原則：

1. **明確依賴**：每個 Agent 只接收它真正需要的資訊
2. **結構化輸出**：便於下游精確提取所需欄位
3. **分層提取**：summary → key_findings → structured_data → full_output
4. **持續監控**：追蹤 Token 使用，驗證節省效果

透過選擇性 Context 傳遞，你可以建構高效、低成本的多 Agent 協作系統，同時保持輸出品質。
