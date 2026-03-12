---
title: "多 Agent Token 優化系列 pt.1：完整指南 — 使用 Claude API 構建高效 AI 系統"
date: 2026-03-12T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "multi-agent", "token-optimization", "cost-optimization", "prompt-engineering", "API", "效能調優"]
summary: "多 Agent Token 優化系列總覽：深入解析 Token 用量優化策略，涵蓋 Prompt Caching、Context 壓縮、Agent 專責化、模型分層、選擇性 Context 傳遞等方法，幫助你建構高效且低成本的多 Agent 系統。"
readTime: "25 min"
---

在使用 Claude Code API 建構多 Agent 系統時，**Token 用量**往往是影響成本、延遲與系統可靠性的關鍵因素。隨著 Agent 數量增加、任務複雜度提升，Token 消耗可能以指數級成長，若不加以優化，很快就會遇到成本爆炸或 Context Window 耗盡的問題。

本文將系統性地介紹多 Agent 系統中 Token 優化的核心概念、主要策略與各方法的優缺點分析。

---

## 🧠 基本概念：多 Agent 系統的 Token 消耗模型

### 什麼是 Token？

在 Claude API 中，所有輸入與輸出都以 **Token** 計量：

```
Token 計算參考：

英文：1 token ≈ 4 個字元 ≈ 0.75 個單字
中文：1 token ≈ 1–2 個字元
程式碼：1 token ≈ 3–5 個字元

範例：
"Hello, World!" → ~4 tokens
"請幫我分析這份報告" → ~10–14 tokens
一個 500 行的 Python 檔案 → 約 5,000–10,000 tokens
```

### 多 Agent 系統的 Token 消耗結構

與單一 Agent 相比，多 Agent 系統的 Token 消耗更為複雜：

```
┌─────────────────────────────────────────────────────────────┐
│               多 Agent Token 消耗結構                       │
│                                                             │
│  每個 Agent 呼叫：                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  System Prompt   │  3,000 – 10,000 tokens           │   │
│  │  對話歷史        │  5,000 – 50,000 tokens           │   │
│  │  工具定義        │  1,000 – 5,000  tokens           │   │
│  │  使用者輸入      │  100   – 5,000  tokens           │   │
│  │  輸出 (回應)     │  500   – 8,000  tokens           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  N 個 Agent 的系統總消耗：                                  │
│  = Σ (每個 Agent 的輸入 tokens + 輸出 tokens)              │
│  + Agent 間傳遞的 Context tokens                           │
│  + 協調層 (Orchestrator) 的 tokens                         │
│                                                             │
│  ⚠️ 警告：若未優化，10 個 Agent 的系統                     │
│          可能消耗單 Agent 的 10–30 倍 tokens               │
└─────────────────────────────────────────────────────────────┘
```

### Token 消耗的來源分類

```
Token 消耗來源分析：

高消耗來源（需重點優化）：
├── 重複的 System Prompt（每次呼叫都重複發送）
├── 完整的對話歷史（累積增長）
├── Agent 間的資料傳遞（完整物件序列化）
├── 工具呼叫結果（大量資料回傳）
└── 重複的背景知識注入

中等消耗來源（可優化）：
├── 工具定義（Tool Schema）
├── 範例示範（Few-shot Examples）
└── 中間步驟的思考過程

低消耗來源（通常可忽略）：
├── 基本指令
└── 格式化指示
```

---

## 🎯 核心優化策略

### 策略一：Prompt Caching（提示快取）

**概念說明：**

Claude API 提供的 Prompt Caching 功能可以快取重複的前綴 tokens，避免每次呼叫都重新計算相同的內容。在多 Agent 系統中，System Prompt 和工具定義通常是固定的，非常適合快取。

**實作範例：**

```python
import anthropic

client = anthropic.Anthropic()

# ✅ 使用 Prompt Caching 的多 Agent 呼叫
def call_agent_with_cache(agent_role: str, task: str, history: list):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": f"""你是一個專業的 {agent_role}。

你的核心職責：
- 分析輸入資料並提供專業見解
- 以結構化格式回傳結果
- 確保輸出的準確性與完整性

[此處可包含大量的角色背景知識、工具說明等...]
這部分內容在多次呼叫間保持不變，非常適合快取。
""",
                "cache_control": {"type": "ephemeral"}  # 啟用快取
            }
        ],
        messages=[
            *history,  # 動態的對話歷史（不快取）
            {"role": "user", "content": task}
        ]
    )
    return response

# 第一次呼叫：完整計算 System Prompt（快取未命中）
result1 = call_agent_with_cache("資料分析師", "分析本季銷售數據", [])
print(f"快取狀態: {result1.usage}")
# cache_creation_input_tokens: 8500（建立快取）
# cache_read_input_tokens: 0

# 第二次呼叫：System Prompt 從快取讀取（快取命中）
result2 = call_agent_with_cache("資料分析師", "預測下季趨勢", [])
print(f"快取狀態: {result2.usage}")
# cache_creation_input_tokens: 0
# cache_read_input_tokens: 8500（快取命中！節省約 90% 成本）
```

**快取效益計算：**

```
Claude Sonnet 的計費比較（參考定價）：

未快取：
  輸入 tokens：$3 / 1M tokens

快取寫入（首次建立）：
  快取寫入：$3.75 / 1M tokens（稍貴，一次性成本）

快取讀取（後續命中）：
  快取讀取：$0.30 / 1M tokens（節省 90%！）

場景：System Prompt 8,000 tokens，呼叫 100 次
未使用快取：8,000 × 100 × $3/1M = $2.40
使用快取：  8,000 × 1 × $3.75/1M + 8,000 × 99 × $0.30/1M = $0.27
節省：約 89% 的 System Prompt 費用
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 成本降低 | System Prompt 讀取費用降低最多 90% |
| ✅ 延遲降低 | 快取命中時首 token 延遲顯著減少 |
| ✅ 實作簡單 | 只需在 API 呼叫中加入 `cache_control` |
| ❌ 最小快取大小 | 需要 ≥ 1,024 tokens 才能啟用快取 |
| ❌ 快取有效期 | 預設 5 分鐘後過期（頻繁呼叫才划算） |
| ❌ 快取不可自訂 | 只能快取前綴，無法快取中間段落 |

---

### 策略二：Context 壓縮與摘要（Summarization）

**概念說明：**

在多輪對話或多 Agent 協作中，對話歷史會不斷累積。透過週期性地將歷史摘要化，可以大幅壓縮 Context 大小，同時保留關鍵資訊。

```
Context 累積問題：

第 1 輪：100 tokens
第 5 輪：500 tokens
第 10 輪：2,000 tokens
第 20 輪：8,000 tokens  ← 指數級成長
第 50 輪：50,000 tokens ← 消耗大量 Context

使用摘要策略後：
第 1-49 輪 → 壓縮為 2,000 tokens 摘要
第 50 輪：2,000 (摘要) + 1,000 (當前輪) = 3,000 tokens
節省：約 94% 的歷史 tokens
```

**實作架構：**

```python
import anthropic
from dataclasses import dataclass
from typing import Optional

client = anthropic.Anthropic()

@dataclass
class AgentContext:
    summary: Optional[str] = None       # 歷史摘要
    recent_messages: list = None         # 最近的完整訊息
    max_recent: int = 10                 # 保留最近幾輪

    def __post_init__(self):
        if self.recent_messages is None:
            self.recent_messages = []

def summarize_history(messages: list, topic: str) -> str:
    """使用 Claude 將對話歷史壓縮為摘要"""
    summary_prompt = f"""請將以下 {topic} 相關的對話歷史壓縮成簡潔摘要。
保留：重要決策、關鍵資料、待解決問題、已確認事項。
略去：重複資訊、過渡性對話、已解決的小問題。
目標長度：原始內容的 20% 以內。

對話歷史：
{format_messages(messages)}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # 使用較便宜的模型做摘要
        max_tokens=1000,
        messages=[{"role": "user", "content": summary_prompt}]
    )
    return response.content[0].text

def build_compressed_messages(context: AgentContext) -> list:
    """構建壓縮後的訊息列表"""
    messages = []

    if context.summary:
        # 將摘要作為第一條系統訊息注入
        messages.append({
            "role": "user",
            "content": f"[歷史摘要]\n{context.summary}"
        })
        messages.append({
            "role": "assistant",
            "content": "已了解歷史背景，繼續處理。"
        })

    # 加入最近的完整對話
    messages.extend(context.recent_messages[-context.max_recent * 2:])
    return messages

def run_agent_with_compression(
    agent_role: str,
    task: str,
    context: AgentContext,
    compress_threshold: int = 15  # 超過幾輪時觸發壓縮
) -> tuple[str, AgentContext]:

    # 檢查是否需要壓縮歷史
    if len(context.recent_messages) > compress_threshold * 2:
        old_messages = context.recent_messages[:-10]  # 保留最近 5 輪
        context.summary = summarize_history(old_messages, agent_role)
        context.recent_messages = context.recent_messages[-10:]
        print(f"✅ 已壓縮歷史：{len(old_messages)} 條訊息 → 摘要")

    # 構建壓縮後的訊息
    messages = build_compressed_messages(context)
    messages.append({"role": "user", "content": task})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=f"你是專業的 {agent_role}。",
        messages=messages
    )

    result = response.content[0].text

    # 更新 Context
    context.recent_messages.append({"role": "user", "content": task})
    context.recent_messages.append({"role": "assistant", "content": result})

    return result, context
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 長期對話穩定 | 避免 Context Window 溢出 |
| ✅ 成本線性化 | 將指數成長轉為線性成長 |
| ✅ 靈活可控 | 可自訂壓縮時機和保留策略 |
| ❌ 資訊損失風險 | 摘要可能遺漏細節 |
| ❌ 額外 Token 消耗 | 摘要過程本身需要 API 呼叫 |
| ❌ 實作複雜度 | 需要管理摘要觸發邏輯 |

---

### 策略三：Agent 專責化（Specialization）

**概念說明：**

透過讓每個 Agent 只負責特定任務，可以大幅縮短 System Prompt 和工具定義，每個 Agent 只需要完成其職責所需的最小 Context。

```
未優化（通用 Agent）：
┌───────────────────────────────────────┐
│ System Prompt：15,000 tokens          │
│ - 所有可能的角色說明                  │
│ - 全部工具定義（30+ 個工具）          │
│ - 所有業務規則                        │
│ - 各種範例                            │
└───────────────────────────────────────┘

優化後（專責 Agent）：
┌──────────────────┐  ┌──────────────────┐
│ 資料分析 Agent   │  │ 程式碼生成 Agent │
│ System: 3,000 t  │  │ System: 3,500 t  │
│ - 分析工具 (5個) │  │ - 程式工具 (6個) │
│ - 分析規則       │  │ - 程式規範       │
└──────────────────┘  └──────────────────┘
節省：每個 Agent 節省約 75% 的 System Prompt tokens
```

**實作範例：**

```python
# ❌ 反模式：通用 Agent（浪費 tokens）
GENERAL_AGENT_SYSTEM = """
你是一個全能助手，可以：
1. 分析資料（SQL 查詢、統計分析、趨勢預測...）
2. 撰寫程式碼（Python、JavaScript、Java、Go...）
3. 撰寫文件（技術文件、API 文件、報告...）
4. 審查程式碼（安全性、效能、最佳實踐...）
5. 測試撰寫（單元測試、整合測試、E2E...）
[大量的工具定義和範例...]
"""
# 每次呼叫：~15,000 tokens 的 System Prompt

# ✅ 最佳實踐：專責 Agent（最小化 tokens）
DATA_ANALYST_SYSTEM = """
你是資料分析師，專注於：數據解讀、趨勢分析、視覺化建議。
只使用以下工具：query_database、calculate_statistics、generate_chart。
"""
# 每次呼叫：~2,000 tokens 的 System Prompt

CODE_GENERATOR_SYSTEM = """
你是程式碼生成器，專注於：生成符合規範的乾淨程式碼。
只使用以下工具：read_file、write_file、run_tests。
"""
# 每次呼叫：~2,500 tokens 的 System Prompt

ORCHESTRATOR_SYSTEM = """
你是任務協調者，負責：任務分解、Agent 派發、結果整合。
可用 Agent：data_analyst, code_generator, doc_writer, code_reviewer。
"""
# 每次呼叫：~3,000 tokens 的 System Prompt

class SpecializedAgentSystem:
    def __init__(self):
        self.agents = {
            "orchestrator": {"system": ORCHESTRATOR_SYSTEM, "model": "claude-sonnet-4-6"},
            "data_analyst": {"system": DATA_ANALYST_SYSTEM, "model": "claude-haiku-4-5-20251001"},
            "code_generator": {"system": CODE_GENERATOR_SYSTEM, "model": "claude-sonnet-4-6"},
        }

    def call_agent(self, agent_name: str, task: str) -> str:
        agent_config = self.agents[agent_name]
        response = client.messages.create(
            model=agent_config["model"],
            max_tokens=4096,
            system=agent_config["system"],
            messages=[{"role": "user", "content": task}]
        )
        return response.content[0].text
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 大幅降低 System Prompt | 每個 Agent 節省 60–80% 的固定 tokens |
| ✅ 準確度提升 | 專注的 Agent 往往表現更好 |
| ✅ 模型可差異化 | 簡單任務用 Haiku，複雜任務用 Sonnet/Opus |
| ❌ 架構設計複雜 | 需要妥善設計 Agent 邊界 |
| ❌ 協調開銷 | Orchestrator 呼叫增加額外 tokens |
| ❌ 跨 Agent 溝通 | 資訊傳遞需要序列化，可能丟失細節 |

---

### 策略四：選擇性 Context 傳遞（Selective Context Passing）

**概念說明：**

在 Agent 協作時，不應將完整的 Context 傳遞給每個下游 Agent，而是只傳遞該 Agent 完成任務所需的最小資訊集合。

```
❌ 完整 Context 傳遞（浪費）：

Orchestrator → Agent B 傳遞：
{
  完整對話歷史: 20,000 tokens,
  所有 Agent A 的輸出: 5,000 tokens,
  原始使用者需求: 500 tokens,
  系統狀態: 2,000 tokens,
  不相關的背景資訊: 3,000 tokens
}
總計：30,500 tokens

✅ 精簡 Context 傳遞（優化）：

Orchestrator → Agent B 傳遞：
{
  任務描述: 300 tokens,
  Agent A 的關鍵輸出摘要: 500 tokens,
  必要參數: 200 tokens
}
總計：1,000 tokens
節省：約 97% 的 tokens！
```

**實作範例：**

```python
from pydantic import BaseModel
from typing import Any

class TaskResult(BaseModel):
    """標準化的 Agent 輸出結構"""
    agent_name: str
    task_id: str
    summary: str           # 簡短摘要（傳遞給下游）
    key_findings: list[str]  # 關鍵發現（傳遞給下游）
    full_output: str       # 完整輸出（存入資料庫，不傳遞）
    metadata: dict[str, Any]

def extract_relevant_context(
    task_results: list[TaskResult],
    downstream_agent: str,
    relevance_map: dict  # 定義哪個 Agent 需要哪些資訊
) -> str:
    """為下游 Agent 提取相關的最小 Context"""

    needed_agents = relevance_map.get(downstream_agent, [])
    relevant_parts = []

    for result in task_results:
        if result.agent_name in needed_agents:
            # 只傳遞摘要和關鍵發現，不傳遞完整輸出
            relevant_parts.append(
                f"[{result.agent_name} 的關鍵輸出]\n"
                f"摘要：{result.summary}\n"
                f"關鍵發現：{chr(10).join(f'- {f}' for f in result.key_findings)}"
            )

    return "\n\n".join(relevant_parts)

# 定義 Agent 間的資訊依賴關係
RELEVANCE_MAP = {
    "code_generator": ["requirements_analyst", "architect"],  # 程式碼生成只需需求和架構
    "code_reviewer":  ["code_generator"],                      # 審查只需看程式碼
    "doc_writer":     ["requirements_analyst", "code_generator", "code_reviewer"],
    "tester":         ["requirements_analyst", "code_generator"]
}

class EfficientOrchestrator:
    def __init__(self):
        self.task_results: list[TaskResult] = []

    def delegate_task(self, agent_name: str, task: str) -> TaskResult:
        # 只傳遞該 Agent 真正需要的 Context
        context = extract_relevant_context(
            self.task_results,
            agent_name,
            RELEVANCE_MAP
        )

        full_task = f"{context}\n\n目前任務：{task}" if context else task

        # 呼叫 Agent
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=self.agents[agent_name]["system"],
            messages=[{"role": "user", "content": full_task}]
        )

        full_output = response.content[0].text

        # 使用 Claude 生成結構化摘要
        result = self._create_task_result(agent_name, task, full_output)
        self.task_results.append(result)
        return result
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 顯著減少 tokens | 最高可節省 90% 以上的 Context tokens |
| ✅ 降低雜訊 | 精簡 Context 讓 Agent 專注於相關資訊 |
| ✅ 提升準確度 | 減少不相關資訊的干擾 |
| ❌ 需要精心設計 | 必須明確定義各 Agent 的資訊需求 |
| ❌ 資訊壓縮損失 | 摘要可能遺漏重要細節 |
| ❌ 維護成本 | 依賴關係圖需要隨系統演進更新 |

---

### 策略五：模型分層（Model Tiering）

**概念說明：**

不同複雜度的任務使用不同等級的模型，在保持品質的前提下最大化成本效益。

```
模型能力與成本對比（Claude 系列）：

┌──────────────────────────────────────────────────────────┐
│ 模型             │ 能力  │ 速度  │ 相對成本 │ 適用場景  │
├──────────────────┼───────┼───────┼──────────┼───────────┤
│ Claude Opus 4.6  │ ★★★★★ │ ★★★   │ 高       │ 複雜推理  │
│ Claude Sonnet 4.6│ ★★★★  │ ★★★★  │ 中       │ 一般任務  │
│ Claude Haiku 4.5 │ ★★★   │ ★★★★★ │ 低       │ 簡單任務  │
└──────────────────────────────────────────────────────────┘

任務分層策略：

高價值任務 → Opus 4.6
├── 複雜架構設計決策
├── 安全漏洞分析
└── 跨領域複雜推理

中等任務 → Sonnet 4.6（預設）
├── 程式碼生成與審查
├── 資料分析
└── 文件撰寫

低複雜度任務 → Haiku 4.5
├── 格式化輸出
├── 簡單分類
├── 文字摘要
└── 路由決策
```

**實作範例：**

```python
from enum import Enum

class TaskComplexity(Enum):
    LOW = "low"        # → Haiku
    MEDIUM = "medium"  # → Sonnet
    HIGH = "high"      # → Opus

MODEL_MAP = {
    TaskComplexity.LOW:    "claude-haiku-4-5-20251001",
    TaskComplexity.MEDIUM: "claude-sonnet-4-6",
    TaskComplexity.HIGH:   "claude-opus-4-6",
}

def classify_task_complexity(task: str) -> TaskComplexity:
    """使用輕量模型自動分類任務複雜度（節省成本）"""
    classification_prompt = f"""
分類以下任務的複雜度。只回答 "low"、"medium" 或 "high"。

low（低）：格式化、簡單摘要、分類、路由
medium（中）：程式碼生成、資料分析、文件撰寫
high（高）：複雜架構設計、安全分析、多步驟推理

任務：{task}
複雜度："""

    # 用最便宜的模型做分類
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": classification_prompt}]
    )

    level = response.content[0].text.strip().lower()
    return TaskComplexity(level) if level in ["low", "medium", "high"] else TaskComplexity.MEDIUM

class AdaptiveAgentRouter:
    def route_and_execute(self, task: str) -> str:
        # 自動選擇合適的模型
        complexity = classify_task_complexity(task)
        model = MODEL_MAP[complexity]

        print(f"任務複雜度：{complexity.value} → 使用模型：{model}")

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": task}]
        )
        return response.content[0].text
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 成本效益最大化 | 低複雜度任務可節省 75% 以上費用 |
| ✅ 速度提升 | Haiku 回應速度約為 Opus 的 3–5 倍 |
| ✅ 彈性擴展 | 簡單任務可大規模並行 |
| ❌ 分類錯誤風險 | 錯誤分類可能影響輸出品質 |
| ❌ 品質差異 | 不同模型的輸出風格可能不一致 |
| ❌ 管理複雜度 | 需要維護分類邏輯和模型映射 |

---

### 策略六：批次處理與並行化

**概念說明：**

合理地批次處理請求和並行執行 Agent，不僅能提升效率，還能透過減少 Orchestrator 協調次數來節省 tokens。

```
串行執行（效率低）：

Task A → Agent 1 → [等待] → Agent 2 → [等待] → Agent 3
總時間：T1 + T2 + T3
Orchestrator 呼叫次數：3 次

並行執行（效率高）：

Task A → Agent 1 ─┐
Task B → Agent 2 ─┤→ 匯總 Agent → 最終結果
Task C → Agent 3 ─┘
總時間：max(T1, T2, T3)
Orchestrator 呼叫次數：1 次（批次分派）+ 1 次（匯總）
```

**實作範例：**

```python
import asyncio
from anthropic import AsyncAnthropic

async_client = AsyncAnthropic()

async def call_agent_async(agent_name: str, system: str, task: str) -> dict:
    """非同步呼叫單個 Agent"""
    response = await async_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": task}]
    )
    return {
        "agent": agent_name,
        "result": response.content[0].text,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens
    }

async def parallel_agent_execution(tasks: list[dict]) -> list[dict]:
    """並行執行多個 Agent 任務"""
    coroutines = [
        call_agent_async(
            task["agent_name"],
            task["system_prompt"],
            task["task"]
        )
        for task in tasks
    ]

    # 所有 Agent 同時執行
    results = await asyncio.gather(*coroutines, return_exceptions=True)
    return results

# 使用範例
async def main():
    # 定義可並行執行的任務（互相獨立）
    parallel_tasks = [
        {
            "agent_name": "security_reviewer",
            "system_prompt": "你是資安審查專家，專注於程式碼安全漏洞。",
            "task": "審查以下程式碼的安全性：[程式碼內容]"
        },
        {
            "agent_name": "performance_reviewer",
            "system_prompt": "你是效能優化專家，專注於程式碼效能問題。",
            "task": "審查以下程式碼的效能：[程式碼內容]"
        },
        {
            "agent_name": "style_reviewer",
            "system_prompt": "你是程式碼風格審查員，專注於可讀性和最佳實踐。",
            "task": "審查以下程式碼的風格：[程式碼內容]"
        }
    ]

    print("開始並行執行 3 個審查 Agent...")
    results = await parallel_agent_execution(parallel_tasks)

    total_tokens = sum(r["tokens_used"] for r in results if isinstance(r, dict))
    print(f"總 Token 消耗：{total_tokens}")
    print(f"相較串行執行節省時間：約 {(2/3*100):.0f}%")

    return results

asyncio.run(main())
```

**優缺點分析：**

| 面向 | 評估 |
|------|------|
| ✅ 大幅縮短執行時間 | 理論上 N 個並行 Agent 縮短 N 倍時間 |
| ✅ 減少協調開銷 | 批次分派減少 Orchestrator 呼叫次數 |
| ✅ 吞吐量提升 | 相同時間內處理更多任務 |
| ❌ Rate Limit 限制 | 大量並行請求可能觸發 API 速率限制 |
| ❌ 依賴關係管理 | 並非所有任務都能並行（有前置依賴） |
| ❌ 錯誤處理複雜 | 單一 Agent 失敗的處理邏輯更複雜 |

---

## 📊 各策略對比總覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Token 優化策略比較矩陣                            │
├──────────────────────┬──────────┬──────────┬──────────┬────────────┤
│ 策略                 │ Token節省│ 實作難度 │ 品質影響 │ 適用場景   │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┤
│ Prompt Caching       │ ★★★★★   │ ★        │ 無       │ 固定前綴   │
│ Context 壓縮摘要     │ ★★★★    │ ★★★      │ 中       │ 長對話     │
│ Agent 專責化         │ ★★★★    │ ★★★      │ 正面     │ 複雜系統   │
│ 選擇性 Context 傳遞  │ ★★★★★   │ ★★★★     │ 低風險   │ 多 Agent   │
│ 模型分層             │ ★★★★    │ ★★       │ 中       │ 任務多樣   │
│ 並行批次處理         │ ★★★     │ ★★★      │ 無       │ 獨立任務   │
└──────────────────────┴──────────┴──────────┴──────────┴────────────┘

★ = 低    ★★ = 中低    ★★★ = 中    ★★★★ = 高    ★★★★★ = 極高
```

---

## 🏗️ 整合實戰：生產級多 Agent 系統架構

結合上述所有策略，以下是一個完整的生產級多 Agent 系統設計：

```python
"""
生產級多 Agent 系統 - 整合所有 Token 優化策略
"""
import asyncio
import json
from anthropic import Anthropic, AsyncAnthropic
from dataclasses import dataclass, field
from typing import Optional

client = Anthropic()
async_client = AsyncAnthropic()

@dataclass
class OptimizedAgentConfig:
    name: str
    system_prompt: str
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    use_cache: bool = True          # 策略1：啟用 Prompt Caching

@dataclass
class SystemState:
    """全域系統狀態（避免重複傳遞）"""
    task_summaries: dict = field(default_factory=dict)
    shared_context: str = ""
    total_tokens_used: int = 0

class ProductionMultiAgentSystem:
    def __init__(self):
        self.state = SystemState()

        # 策略三：專責化 Agent 定義
        self.agents = {
            "orchestrator": OptimizedAgentConfig(
                name="orchestrator",
                system_prompt="你是任務協調員。分解任務、指派 Agent、整合結果。保持回應簡潔。",
                model="claude-sonnet-4-6",
                max_tokens=2048
            ),
            "analyst": OptimizedAgentConfig(
                name="analyst",
                system_prompt="你是分析師。只做資料分析和洞察提取。輸出要點式摘要。",
                model="claude-haiku-4-5-20251001",  # 策略五：低複雜度用 Haiku
                max_tokens=1024
            ),
            "developer": OptimizedAgentConfig(
                name="developer",
                system_prompt="你是開發者。只生成程式碼，附簡短說明。不做分析，不做文件。",
                model="claude-sonnet-4-6",
                max_tokens=4096
            ),
            "reviewer": OptimizedAgentConfig(
                name="reviewer",
                system_prompt="你是審查員。只輸出：問題清單、嚴重程度、修正建議。格式固定。",
                model="claude-haiku-4-5-20251001",
                max_tokens=1024
            )
        }

    def _build_system_content(self, config: OptimizedAgentConfig) -> list:
        """策略一：構建帶快取的 System Prompt"""
        if config.use_cache:
            return [{
                "type": "text",
                "text": config.system_prompt,
                "cache_control": {"type": "ephemeral"}  # 啟用快取
            }]
        return config.system_prompt

    def _get_minimal_context(self, agent_name: str) -> str:
        """策略四：只傳遞相關的最小 Context"""
        # 定義每個 Agent 需要哪些其他 Agent 的輸出
        context_needs = {
            "developer": ["analyst"],          # 開發者需要分析結果
            "reviewer":  ["developer"],         # 審查者需要開發者輸出
            "orchestrator": ["analyst", "developer", "reviewer"]  # 協調者需要全部
        }

        needed = context_needs.get(agent_name, [])
        context_parts = []

        for needed_agent in needed:
            if needed_agent in self.state.task_summaries:
                # 只傳摘要，不傳完整輸出（策略四核心）
                context_parts.append(
                    f"[{needed_agent} 輸出摘要]\n{self.state.task_summaries[needed_agent]}"
                )

        return "\n\n".join(context_parts)

    async def _call_agent_async(
        self,
        config: OptimizedAgentConfig,
        task: str
    ) -> str:
        context = self._get_minimal_context(config.name)
        full_task = f"{context}\n\n任務：{task}" if context else task

        response = await async_client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            system=self._build_system_content(config),
            messages=[{"role": "user", "content": full_task}]
        )

        result = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        self.state.total_tokens_used += tokens

        # 儲存摘要（前 500 字元作為摘要）
        self.state.task_summaries[config.name] = result[:500] + "..." if len(result) > 500 else result

        return result

    async def run_pipeline(self, user_request: str) -> dict:
        print(f"\n🚀 開始處理請求（Token 優化模式）")
        print(f"請求：{user_request[:100]}...\n")

        # 步驟 1：Orchestrator 分解任務（單次呼叫）
        orchestration_plan = await self._call_agent_async(
            self.agents["orchestrator"],
            f"分解以下請求並制定執行計畫：{user_request}"
        )
        print(f"✅ 協調層完成，tokens: {self.state.total_tokens_used}")

        # 步驟 2：策略六 - 並行執行獨立 Agent
        print("🔄 並行執行分析和開發 Agent...")
        analyst_task = self._call_agent_async(
            self.agents["analyst"],
            f"分析需求：{user_request}"
        )
        # 注意：analyst 和 developer 可並行，因為 developer 此時不需要 analyst 的輸出
        # 但如果 developer 需要 analyst 結果，則必須串行

        analyst_result = await analyst_task
        print(f"✅ 分析完成，累計 tokens: {self.state.total_tokens_used}")

        # 步驟 3：開發（需要 analyst 結果，串行）
        dev_result = await self._call_agent_async(
            self.agents["developer"],
            orchestration_plan  # 傳遞計畫，Context 中已包含 analyst 摘要
        )
        print(f"✅ 開發完成，累計 tokens: {self.state.total_tokens_used}")

        # 步驟 4：審查（需要 developer 結果，串行）
        review_result = await self._call_agent_async(
            self.agents["reviewer"],
            "審查開發者的輸出"
        )
        print(f"✅ 審查完成，累計 tokens: {self.state.total_tokens_used}")

        print(f"\n📊 最終統計：總 Token 使用量 = {self.state.total_tokens_used}")

        return {
            "orchestration": orchestration_plan,
            "analysis": analyst_result,
            "code": dev_result,
            "review": review_result,
            "total_tokens": self.state.total_tokens_used
        }

# 使用
async def main():
    system = ProductionMultiAgentSystem()
    result = await system.run_pipeline(
        "建立一個使用者認證模組，包含 JWT 登入、刷新 token 和登出功能"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(main())
```

---

## 🔍 監控與成本追蹤

優化後，需要持續監控 Token 使用情況以驗證效果：

```python
import time
from collections import defaultdict

class TokenUsageMonitor:
    def __init__(self):
        self.usage_log = defaultdict(list)

    def record_usage(self, agent_name: str, model: str, usage):
        self.usage_log[agent_name].append({
            "timestamp": time.time(),
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
        })

    def print_report(self):
        print("\n" + "="*60)
        print("Token 使用量報告")
        print("="*60)

        total_input = 0
        total_output = 0
        total_cache_saves = 0

        for agent, logs in self.usage_log.items():
            agent_input = sum(l["input_tokens"] for l in logs)
            agent_output = sum(l["output_tokens"] for l in logs)
            cache_reads = sum(l["cache_read_input_tokens"] for l in logs)

            total_input += agent_input
            total_output += agent_output
            total_cache_saves += cache_reads

            print(f"\nAgent: {agent}")
            print(f"  輸入 tokens: {agent_input:,}")
            print(f"  輸出 tokens: {agent_output:,}")
            print(f"  快取命中 tokens: {cache_reads:,}")
            if cache_reads > 0:
                savings_pct = cache_reads / (agent_input + cache_reads) * 100
                print(f"  快取節省率: {savings_pct:.1f}%")

        print(f"\n總計：")
        print(f"  輸入 tokens: {total_input:,}")
        print(f"  輸出 tokens: {total_output:,}")
        print(f"  快取節省 tokens: {total_cache_saves:,}")
        print("="*60)
```

---

## ✅ 最佳實踐清單

在正式部署多 Agent 系統前，請確認以下優化項目：

```
Token 優化 Checklist：

System Prompt 優化
□ System Prompt 是否超過 1,024 tokens？若是，啟用 Prompt Caching
□ 各 Agent 的 System Prompt 是否精簡至只含必要資訊？
□ 工具定義是否只包含該 Agent 實際使用的工具？

Context 管理
□ 對話歷史是否有長度限制？（建議最多保留 10-20 輪）
□ 是否對超過閾值的歷史進行自動壓縮摘要？
□ Agent 間傳遞的 Context 是否只包含必要資訊？

模型選擇
□ 簡單路由/格式化任務是否使用 Haiku？
□ 複雜推理任務是否確實需要 Opus？（Sonnet 通常已足夠）
□ 摘要生成是否使用輕量模型？

架構設計
□ 哪些 Agent 可以並行執行（無前置依賴）？
□ 是否有不必要的 Orchestrator 呼叫可以省略？
□ 是否有重複的 Agent 呼叫可以合併？

監控
□ 是否追蹤每個 Agent 的 Token 使用量？
□ 是否設置成本警報（Cost Alert）？
□ 是否定期審查快取命中率？
```

---

## 🎯 總結

多 Agent 系統的 Token 優化是一個需要系統性思考的工程問題。本文介紹的六大策略各有側重：

| 優先順序 | 策略 | 預期節省 | 實作成本 |
|----------|------|----------|----------|
| 1 | **Prompt Caching** | 最高（固定 tokens 的 90%） | 最低 |
| 2 | **Agent 專責化** | 高（System Prompt 60–80%） | 中 |
| 3 | **選擇性 Context 傳遞** | 高（傳遞 tokens 的 80–97%）| 中高 |
| 4 | **模型分層** | 中高（低複雜度任務 75%+） | 低 |
| 5 | **Context 壓縮摘要** | 中（長期對話 70–90%） | 中 |
| 6 | **並行批次處理** | 中（時間成本，非直接 token 節省） | 中 |

**建議的實施順序：**

1. **先啟用 Prompt Caching**（立竿見影，改動最小）
2. **重新設計 Agent 邊界**（長期效益最大）
3. **實作選擇性 Context 傳遞**（對大型系統效益顯著）
4. **引入模型分層路由**（平衡品質與成本）
5. **加入 Context 壓縮**（確保長期穩定運行）
6. **優化並行架構**（提升整體吞吐量）

Token 優化不是一次性的工作，而是需要根據實際使用數據持續迭代的過程。建立完善的監控機制，讓數據驅動優化決策，才能構建真正高效、低成本的多 Agent 系統。
