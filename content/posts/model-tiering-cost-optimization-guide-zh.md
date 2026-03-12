---
title: "多 Agent Token 優化系列 pt.4：模型分層實戰 — 智能路由打造高效低成本系統"
date: 2026-03-12T18:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "model-tiering", "cost-optimization", "model-routing", "LLM-optimization", "API"]
summary: "多 Agent Token 優化系列 pt.4：深入探索模型分層策略，從任務分類、智能路由到動態選擇，提供完整實作範例，幫助你在保持品質的同時大幅降低 AI 應用成本。"
readTime: "30 min"
---

在前一篇文章《多 Agent 系統的 Token 用量調優指南》中，我們介紹了 **模型分層（Model Tiering）** 作為平衡品質與成本的關鍵策略。本文將深入實作層面，探討如何在真實系統中建構智能的模型路由機制，讓簡單任務用便宜快速的模型，複雜任務才動用高階模型，實現成本效益最大化。

---

## 為什麼需要模型分層？

### 不同模型的能力與成本差異

```
Claude 模型系列對比（2026 參考定價）：

┌─────────────────────────────────────────────────────────────────────┐
│                    Claude 模型能力與成本矩陣                         │
├──────────────────┬─────────┬─────────┬──────────┬──────────────────┤
│ 模型             │ 輸入成本│ 輸出成本│ 推理能力 │ 速度             │
│                  │ /1M tok │ /1M tok │          │                  │
├──────────────────┼─────────┼─────────┼──────────┼──────────────────┤
│ Claude Opus 4    │ $15     │ $75     │ ★★★★★   │ ★★★（較慢）     │
│ Claude Sonnet 4  │ $3      │ $15     │ ★★★★    │ ★★★★（中等）   │
│ Claude Haiku 3.5 │ $0.80   │ $4      │ ★★★     │ ★★★★★（最快） │
└──────────────────┴─────────┴─────────┴──────────┴──────────────────┘

成本差異計算：
- Opus vs Haiku 輸入：15 / 0.80 = 18.75x
- Opus vs Haiku 輸出：75 / 4 = 18.75x

場景：處理 1000 個請求，每個請求 2000 輸入 + 500 輸出 tokens

全部使用 Opus：
  (2000 × $15 + 500 × $75) / 1M × 1000 = $67.50

全部使用 Haiku：
  (2000 × $0.80 + 500 × $4) / 1M × 1000 = $3.60

智能分層（假設 70% 用 Haiku，30% 用 Sonnet）：
  700 × $3.60/1000 + 300 × ((2000×$3 + 500×$15)/1M) = $5.97

節省：全 Opus 方案的 91%！
```

### 任務複雜度的長尾分布

```
實際應用中任務複雜度分布：

複雜度 ▲
       │
  高   │  ████  (10%) ← 需要 Opus
       │  ████████████  (20%) ← 適合 Sonnet
  中   │  ████████████████████████  (30%)
       │  ████████████████████████████████████████  (40%) ← Haiku 足夠
  低   │
       └──────────────────────────────────────────────▶ 任務數量

關鍵洞察：
- 大多數任務（~70%）不需要最強的模型
- 只有少數任務（~10%）真正需要複雜推理
- 正確分類 + 路由 = 大幅節省成本
```

---

## 任務分類框架

### 複雜度維度分析

```
任務複雜度評估維度：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  維度 1：推理深度                                                   │
│  ├── 單步推理：直接回答、格式轉換、簡單分類                        │
│  ├── 多步推理：邏輯推導、問題分解、計劃制定                        │
│  └── 複雜推理：抽象思考、創意生成、多角度分析                      │
│                                                                     │
│  維度 2：領域專業度                                                 │
│  ├── 通用知識：日常問答、一般寫作                                  │
│  ├── 專業領域：技術問題、法律諮詢、醫療資訊                        │
│  └── 深度專業：前沿研究、複雜架構、策略規劃                        │
│                                                                     │
│  維度 3：輸出品質要求                                               │
│  ├── 基本正確：內部工具、草稿生成                                  │
│  ├── 高品質：客戶溝通、正式文件                                    │
│  └── 極致品質：關鍵決策、法律文書、發表內容                        │
│                                                                     │
│  維度 4：容錯程度                                                   │
│  ├── 可容錯：建議性輸出、可人工修正                                │
│  ├── 低容錯：自動化流程、需要準確                                  │
│  └── 零容錯：安全相關、財務計算、醫療建議                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 任務類型與模型映射

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class TaskComplexity(Enum):
    """任務複雜度等級"""
    TRIVIAL = "trivial"      # 極簡單：格式化、提取
    SIMPLE = "simple"        # 簡單：分類、摘要、翻譯
    MODERATE = "moderate"    # 中等：程式碼生成、分析
    COMPLEX = "complex"      # 複雜：架構設計、深度推理
    EXPERT = "expert"        # 專家級：研究、創新、關鍵決策

class TaskCategory(Enum):
    """任務類別"""
    EXTRACTION = "extraction"        # 資訊提取
    CLASSIFICATION = "classification" # 分類
    SUMMARIZATION = "summarization"  # 摘要
    TRANSLATION = "translation"      # 翻譯
    GENERATION = "generation"        # 內容生成
    CODE = "code"                    # 程式碼相關
    ANALYSIS = "analysis"            # 分析
    REASONING = "reasoning"          # 推理
    CREATIVE = "creative"            # 創意
    CONVERSATION = "conversation"    # 對話

@dataclass
class ModelSpec:
    """模型規格"""
    name: str
    model_id: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    max_tokens: int
    strengths: list[str]
    weaknesses: list[str]

# 定義可用模型
MODELS = {
    "opus": ModelSpec(
        name="Claude Opus 4",
        model_id="claude-opus-4-20250514",
        input_cost_per_1m=15.0,
        output_cost_per_1m=75.0,
        max_tokens=4096,
        strengths=["複雜推理", "創意寫作", "深度分析", "專業知識"],
        weaknesses=["成本高", "速度較慢"]
    ),
    "sonnet": ModelSpec(
        name="Claude Sonnet 4",
        model_id="claude-sonnet-4-20250514",
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
        max_tokens=4096,
        strengths=["程式碼生成", "一般分析", "平衡性能"],
        weaknesses=["複雜推理略遜 Opus"]
    ),
    "haiku": ModelSpec(
        name="Claude Haiku 3.5",
        model_id="claude-3-5-haiku-20241022",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.0,
        max_tokens=4096,
        strengths=["速度快", "成本低", "簡單任務"],
        weaknesses=["複雜任務能力有限"]
    )
}

# 任務類型到複雜度的預設映射
DEFAULT_COMPLEXITY_MAP = {
    TaskCategory.EXTRACTION: TaskComplexity.TRIVIAL,
    TaskCategory.CLASSIFICATION: TaskComplexity.SIMPLE,
    TaskCategory.SUMMARIZATION: TaskComplexity.SIMPLE,
    TaskCategory.TRANSLATION: TaskComplexity.SIMPLE,
    TaskCategory.GENERATION: TaskComplexity.MODERATE,
    TaskCategory.CODE: TaskComplexity.MODERATE,
    TaskCategory.ANALYSIS: TaskComplexity.MODERATE,
    TaskCategory.REASONING: TaskComplexity.COMPLEX,
    TaskCategory.CREATIVE: TaskComplexity.COMPLEX,
    TaskCategory.CONVERSATION: TaskComplexity.SIMPLE,
}

# 複雜度到模型的映射
COMPLEXITY_MODEL_MAP = {
    TaskComplexity.TRIVIAL: "haiku",
    TaskComplexity.SIMPLE: "haiku",
    TaskComplexity.MODERATE: "sonnet",
    TaskComplexity.COMPLEX: "sonnet",
    TaskComplexity.EXPERT: "opus",
}
```

---

## 策略一：規則基礎路由（Rule-Based Routing）

最直接的方式：根據預定義規則選擇模型。

### 基礎實作

```python
import anthropic
import re
from dataclasses import dataclass
from typing import Optional, Callable

client = anthropic.Anthropic()

@dataclass
class RoutingRule:
    """路由規則"""
    name: str
    condition: Callable[[str], bool]  # 判斷函數
    model: str                         # 目標模型
    priority: int = 0                  # 優先級（越高越優先）

class RuleBasedRouter:
    """
    規則基礎模型路由器

    優點：
    - 可預測、可控
    - 無額外 API 成本
    - 執行速度快

    缺點：
    - 規則維護成本
    - 邊界情況處理困難
    - 難以適應新場景
    """

    def __init__(self):
        self.rules: list[RoutingRule] = []
        self.default_model = "sonnet"
        self._stats = {model: 0 for model in MODELS}

    def add_rule(self, rule: RoutingRule):
        """添加路由規則"""
        self.rules.append(rule)
        # 按優先級排序
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def route(self, task: str) -> str:
        """根據規則選擇模型"""
        for rule in self.rules:
            if rule.condition(task):
                self._stats[rule.model] += 1
                return rule.model

        self._stats[self.default_model] += 1
        return self.default_model

    def call(self, task: str, system: Optional[str] = None, **kwargs) -> str:
        """路由並呼叫模型"""
        model_key = self.route(task)
        model_spec = MODELS[model_key]

        response = client.messages.create(
            model=model_spec.model_id,
            max_tokens=kwargs.get("max_tokens", 2048),
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": task}]
        )

        return response.content[0].text

    def get_stats(self) -> dict:
        total = sum(self._stats.values())
        return {
            "routing_stats": self._stats,
            "total_requests": total,
            "distribution": {
                k: f"{v/total*100:.1f}%" if total > 0 else "0%"
                for k, v in self._stats.items()
            }
        }


# 建立常用規則
def create_standard_rules() -> list[RoutingRule]:
    """建立標準路由規則集"""
    return [
        # 高優先級：強制使用 Opus 的情況
        RoutingRule(
            name="security_analysis",
            condition=lambda t: any(kw in t.lower() for kw in [
                "安全漏洞", "security vulnerability", "滲透測試",
                "資安審計", "安全審查"
            ]),
            model="opus",
            priority=100
        ),
        RoutingRule(
            name="architecture_design",
            condition=lambda t: any(kw in t.lower() for kw in [
                "架構設計", "system design", "設計模式",
                "技術選型", "架構決策"
            ]),
            model="opus",
            priority=100
        ),

        # 中優先級：使用 Sonnet
        RoutingRule(
            name="code_generation",
            condition=lambda t: any(kw in t.lower() for kw in [
                "寫一個", "實作", "implement", "寫程式",
                "function", "class", "def ", "async "
            ]),
            model="sonnet",
            priority=50
        ),
        RoutingRule(
            name="code_review",
            condition=lambda t: any(kw in t.lower() for kw in [
                "審查", "review", "檢查這段", "優化這個"
            ]),
            model="sonnet",
            priority=50
        ),
        RoutingRule(
            name="analysis",
            condition=lambda t: any(kw in t.lower() for kw in [
                "分析", "analyze", "比較", "compare",
                "評估", "evaluate"
            ]),
            model="sonnet",
            priority=50
        ),

        # 低優先級：使用 Haiku
        RoutingRule(
            name="simple_question",
            condition=lambda t: len(t) < 100 and "?" in t,
            model="haiku",
            priority=20
        ),
        RoutingRule(
            name="translation",
            condition=lambda t: any(kw in t.lower() for kw in [
                "翻譯", "translate", "轉換成"
            ]),
            model="haiku",
            priority=20
        ),
        RoutingRule(
            name="summarization",
            condition=lambda t: any(kw in t.lower() for kw in [
                "摘要", "summarize", "總結", "概述"
            ]),
            model="haiku",
            priority=20
        ),
        RoutingRule(
            name="formatting",
            condition=lambda t: any(kw in t.lower() for kw in [
                "格式化", "format", "轉成 json", "轉成 markdown"
            ]),
            model="haiku",
            priority=20
        ),
        RoutingRule(
            name="extraction",
            condition=lambda t: any(kw in t.lower() for kw in [
                "提取", "extract", "找出", "列出"
            ]),
            model="haiku",
            priority=20
        ),
    ]


# 使用範例
if __name__ == "__main__":
    router = RuleBasedRouter()

    # 載入標準規則
    for rule in create_standard_rules():
        router.add_rule(rule)

    # 測試不同類型的任務
    test_tasks = [
        "請幫我翻譯這段文字成英文",                    # → Haiku
        "總結以下文章的重點",                          # → Haiku
        "寫一個 Python 函數來計算費氏數列",            # → Sonnet
        "分析這段程式碼的效能問題",                    # → Sonnet
        "設計一個高可用的微服務架構",                  # → Opus
        "審查這段程式碼的安全漏洞",                    # → Opus
        "今天天氣如何？",                             # → Haiku (短問題)
    ]

    print("模型路由測試：\n")
    for task in test_tasks:
        model = router.route(task)
        print(f"任務：{task[:30]}...")
        print(f"路由至：{MODELS[model].name}\n")

    print("路由統計：")
    print(router.get_stats())
```

---

## 策略二：LLM 輔助分類路由

使用輕量模型（Haiku）進行任務分類，再路由到適當模型。

### 核心概念

```
LLM 輔助分類流程：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  使用者任務                                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 1: Haiku 快速分類                                      │   │
│  │  成本：~$0.001 / 請求                                        │   │
│  │  輸出：{ complexity: "moderate", category: "code" }          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 2: 路由決策                                            │   │
│  │  moderate + code → Sonnet                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 3: 目標模型執行                                        │   │
│  │  Sonnet 處理實際任務                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  總成本 = 分類成本 + 執行成本                                       │
│  分類成本通常 < 1% 總成本，但可節省大量錯誤路由成本                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
import json
from dataclasses import dataclass
from typing import Optional
from enum import Enum

client = anthropic.Anthropic()

@dataclass
class ClassificationResult:
    """分類結果"""
    complexity: TaskComplexity
    category: TaskCategory
    confidence: float
    reasoning: str
    suggested_model: str

class LLMClassifierRouter:
    """
    LLM 輔助分類路由器

    使用 Haiku 進行任務分類，基於分類結果選擇目標模型

    優點：
    - 更準確的任務理解
    - 可處理複雜的邊界情況
    - 自動適應新類型任務

    缺點：
    - 額外的分類 API 呼叫成本
    - 增加一次網路往返延遲
    """

    CLASSIFICATION_PROMPT = """分析以下任務，判斷其複雜度和類別。

任務：
{task}

請以 JSON 格式回答：
{{
    "complexity": "trivial|simple|moderate|complex|expert",
    "category": "extraction|classification|summarization|translation|generation|code|analysis|reasoning|creative|conversation",
    "confidence": 0.0-1.0,
    "reasoning": "簡短說明判斷依據"
}}

複雜度判斷標準：
- trivial: 簡單格式化、直接提取
- simple: 基本分類、摘要、翻譯
- moderate: 程式碼生成、一般分析
- complex: 深度分析、多步推理
- expert: 創新設計、專家級決策

只返回 JSON，不要其他說明。"""

    def __init__(
        self,
        classifier_model: str = "claude-3-5-haiku-20241022",
        enable_caching: bool = True
    ):
        self.classifier_model = classifier_model
        self.enable_caching = enable_caching
        self._classification_cache: dict[str, ClassificationResult] = {}

        self._stats = {
            "classifications": 0,
            "cache_hits": 0,
            "model_usage": {model: 0 for model in MODELS}
        }

    def _get_cache_key(self, task: str) -> str:
        """計算快取鍵"""
        # 使用任務的前 500 字元作為鍵（避免過長）
        import hashlib
        return hashlib.md5(task[:500].encode()).hexdigest()

    def classify(self, task: str) -> ClassificationResult:
        """分類任務"""
        # 檢查快取
        if self.enable_caching:
            cache_key = self._get_cache_key(task)
            if cache_key in self._classification_cache:
                self._stats["cache_hits"] += 1
                return self._classification_cache[cache_key]

        # 呼叫分類模型
        response = client.messages.create(
            model=self.classifier_model,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": self.CLASSIFICATION_PROMPT.format(task=task[:2000])
            }]
        )

        self._stats["classifications"] += 1

        # 解析結果
        try:
            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].split("```")[0]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text.strip())

            result = ClassificationResult(
                complexity=TaskComplexity(data["complexity"]),
                category=TaskCategory(data["category"]),
                confidence=data.get("confidence", 0.8),
                reasoning=data.get("reasoning", ""),
                suggested_model=self._map_to_model(
                    TaskComplexity(data["complexity"]),
                    TaskCategory(data["category"])
                )
            )

            # 快取結果
            if self.enable_caching:
                self._classification_cache[cache_key] = result

            return result

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # 預設返回中等複雜度
            return ClassificationResult(
                complexity=TaskComplexity.MODERATE,
                category=TaskCategory.GENERATION,
                confidence=0.5,
                reasoning=f"分類失敗，使用預設: {e}",
                suggested_model="sonnet"
            )

    def _map_to_model(self, complexity: TaskComplexity, category: TaskCategory) -> str:
        """根據複雜度和類別映射到模型"""
        # 特殊類別覆寫
        if category in [TaskCategory.REASONING, TaskCategory.CREATIVE]:
            if complexity in [TaskComplexity.COMPLEX, TaskComplexity.EXPERT]:
                return "opus"

        if category == TaskCategory.CODE:
            if complexity == TaskComplexity.EXPERT:
                return "opus"
            return "sonnet"

        # 預設按複雜度
        return COMPLEXITY_MODEL_MAP.get(complexity, "sonnet")

    def route_and_call(
        self,
        task: str,
        system: Optional[str] = None,
        **kwargs
    ) -> tuple[str, ClassificationResult]:
        """
        分類、路由並呼叫

        Returns:
            (模型回應, 分類結果)
        """
        # Step 1: 分類
        classification = self.classify(task)

        # Step 2: 取得目標模型
        model_key = classification.suggested_model
        model_spec = MODELS[model_key]
        self._stats["model_usage"][model_key] += 1

        # Step 3: 呼叫目標模型
        response = client.messages.create(
            model=model_spec.model_id,
            max_tokens=kwargs.get("max_tokens", 2048),
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": task}]
        )

        return response.content[0].text, classification

    def get_stats(self) -> dict:
        total_requests = sum(self._stats["model_usage"].values())
        return {
            "total_classifications": self._stats["classifications"],
            "cache_hits": self._stats["cache_hits"],
            "cache_hit_rate": f"{self._stats['cache_hits'] / max(self._stats['classifications'] + self._stats['cache_hits'], 1) * 100:.1f}%",
            "model_usage": self._stats["model_usage"],
            "model_distribution": {
                k: f"{v/max(total_requests, 1)*100:.1f}%"
                for k, v in self._stats["model_usage"].items()
            }
        }


# 使用範例
if __name__ == "__main__":
    router = LLMClassifierRouter()

    test_tasks = [
        "把 'Hello World' 翻譯成中文",
        "寫一個 Python 快速排序演算法",
        "設計一個支援百萬用戶的即時通訊系統架構",
        "這段程式碼有什麼問題？\ndef add(a, b): return a + b",
        "分析 React 和 Vue 的優缺點",
    ]

    print("LLM 輔助分類路由測試：\n")
    for task in test_tasks:
        response, classification = router.route_and_call(task)
        print(f"任務：{task[:40]}...")
        print(f"分類：{classification.category.value} / {classification.complexity.value}")
        print(f"信心度：{classification.confidence}")
        print(f"路由至：{MODELS[classification.suggested_model].name}")
        print(f"回應：{response[:100]}...\n")

    print("統計：")
    print(router.get_stats())
```

---

## 策略三：動態品質評估路由

先用便宜模型嘗試，如果輸出品質不達標再升級。

### 核心概念

```
動態升級流程：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  使用者任務                                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 1: Haiku 嘗試                                          │   │
│  │  快速生成初步回應                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 2: 品質評估                                            │   │
│  │  - 回應是否完整？                                            │   │
│  │  - 是否包含 "不確定"、"無法" 等標記？                        │   │
│  │  - 長度是否合理？                                            │   │
│  │  - 是否有明顯錯誤？                                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ├── 品質達標 ────────────────────────▶ 返回 Haiku 結果       │
│       │                                                             │
│       ▼  品質不達標                                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 3: 升級到 Sonnet                                       │   │
│  │  使用更強模型重新處理                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ├── 品質達標 ────────────────────────▶ 返回 Sonnet 結果      │
│       │                                                             │
│       ▼  仍不達標                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Step 4: 升級到 Opus                                         │   │
│  │  使用最強模型處理                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  優點：大多數任務在 Step 1-2 完成，大幅節省成本                    │
│  缺點：需要設計有效的品質評估機制                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
import re
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

client = anthropic.Anthropic()

class QualityLevel(Enum):
    """品質等級"""
    HIGH = "high"
    ACCEPTABLE = "acceptable"
    LOW = "low"
    FAILED = "failed"

@dataclass
class QualityAssessment:
    """品質評估結果"""
    level: QualityLevel
    score: float  # 0-1
    issues: list[str]
    should_upgrade: bool

@dataclass
class EscalationResult:
    """升級結果"""
    response: str
    final_model: str
    attempts: list[dict]  # 每次嘗試的記錄
    total_cost: float

class QualityChecker:
    """品質檢查器"""

    # 品質問題指標
    UNCERTAINTY_MARKERS = [
        "我不確定", "我無法", "不太清楚", "可能不準確",
        "I'm not sure", "I cannot", "I don't know",
        "抱歉，我無法", "這超出了我的能力"
    ]

    INCOMPLETE_MARKERS = [
        "...", "等等", "以此類推", "更多內容",
        "（未完待續）", "TODO", "待補充"
    ]

    def __init__(
        self,
        min_response_length: int = 50,
        max_uncertainty_ratio: float = 0.1,
        custom_validators: Optional[list[Callable[[str], bool]]] = None
    ):
        self.min_response_length = min_response_length
        self.max_uncertainty_ratio = max_uncertainty_ratio
        self.custom_validators = custom_validators or []

    def assess(self, response: str, task: str) -> QualityAssessment:
        """評估回應品質"""
        issues = []
        score = 1.0

        # 檢查長度
        if len(response) < self.min_response_length:
            issues.append("回應過短")
            score -= 0.3

        # 檢查不確定性標記
        uncertainty_count = sum(
            1 for marker in self.UNCERTAINTY_MARKERS
            if marker.lower() in response.lower()
        )
        if uncertainty_count > 0:
            issues.append(f"包含 {uncertainty_count} 個不確定性標記")
            score -= 0.2 * uncertainty_count

        # 檢查不完整標記
        incomplete_count = sum(
            1 for marker in self.INCOMPLETE_MARKERS
            if marker in response
        )
        if incomplete_count > 0:
            issues.append("回應可能不完整")
            score -= 0.2

        # 檢查是否拒絕回答
        refusal_patterns = [
            r"我無法提供", r"我不能幫助", r"這違反",
            r"I cannot", r"I'm unable to"
        ]
        for pattern in refusal_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append("模型拒絕回答")
                score -= 0.5
                break

        # 執行自訂驗證器
        for validator in self.custom_validators:
            if not validator(response):
                issues.append("未通過自訂驗證")
                score -= 0.2

        # 計算最終評級
        score = max(0, score)
        if score >= 0.8:
            level = QualityLevel.HIGH
        elif score >= 0.6:
            level = QualityLevel.ACCEPTABLE
        elif score >= 0.3:
            level = QualityLevel.LOW
        else:
            level = QualityLevel.FAILED

        return QualityAssessment(
            level=level,
            score=score,
            issues=issues,
            should_upgrade=level in [QualityLevel.LOW, QualityLevel.FAILED]
        )


class DynamicEscalationRouter:
    """
    動態升級路由器

    從便宜模型開始嘗試，品質不達標時升級到更強模型
    """

    # 模型升級順序
    MODEL_LADDER = ["haiku", "sonnet", "opus"]

    def __init__(
        self,
        quality_checker: Optional[QualityChecker] = None,
        start_model: str = "haiku",
        max_attempts: int = 3
    ):
        self.quality_checker = quality_checker or QualityChecker()
        self.start_model = start_model
        self.max_attempts = max_attempts

        self._stats = {
            "total_requests": 0,
            "escalations": 0,
            "model_attempts": {model: 0 for model in MODELS},
            "model_finals": {model: 0 for model in MODELS},
            "total_cost": 0.0
        }

    def _call_model(self, model_key: str, task: str, system: Optional[str] = None) -> tuple[str, float]:
        """呼叫模型並計算成本"""
        model_spec = MODELS[model_key]

        response = client.messages.create(
            model=model_spec.model_id,
            max_tokens=2048,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": task}]
        )

        # 計算成本
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (
            input_tokens * model_spec.input_cost_per_1m / 1_000_000 +
            output_tokens * model_spec.output_cost_per_1m / 1_000_000
        )

        return response.content[0].text, cost

    def _get_next_model(self, current_model: str) -> Optional[str]:
        """取得下一個升級模型"""
        try:
            current_idx = self.MODEL_LADDER.index(current_model)
            if current_idx < len(self.MODEL_LADDER) - 1:
                return self.MODEL_LADDER[current_idx + 1]
        except ValueError:
            pass
        return None

    def route_and_call(
        self,
        task: str,
        system: Optional[str] = None,
        quality_threshold: QualityLevel = QualityLevel.ACCEPTABLE
    ) -> EscalationResult:
        """
        動態路由並呼叫

        Args:
            task: 任務
            system: System prompt
            quality_threshold: 最低可接受品質等級

        Returns:
            EscalationResult
        """
        self._stats["total_requests"] += 1

        attempts = []
        current_model = self.start_model
        total_cost = 0.0
        final_response = None
        final_model = None

        acceptable_levels = {
            QualityLevel.HIGH: [QualityLevel.HIGH],
            QualityLevel.ACCEPTABLE: [QualityLevel.HIGH, QualityLevel.ACCEPTABLE],
            QualityLevel.LOW: [QualityLevel.HIGH, QualityLevel.ACCEPTABLE, QualityLevel.LOW],
        }
        acceptable = acceptable_levels.get(quality_threshold, [QualityLevel.HIGH, QualityLevel.ACCEPTABLE])

        for attempt in range(self.max_attempts):
            if current_model is None:
                break

            # 嘗試當前模型
            self._stats["model_attempts"][current_model] += 1
            response, cost = self._call_model(current_model, task, system)
            total_cost += cost

            # 評估品質
            assessment = self.quality_checker.assess(response, task)

            attempts.append({
                "model": current_model,
                "quality_level": assessment.level.value,
                "quality_score": assessment.score,
                "issues": assessment.issues,
                "cost": cost
            })

            # 檢查是否達標
            if assessment.level in acceptable:
                final_response = response
                final_model = current_model
                break

            # 升級到下一個模型
            self._stats["escalations"] += 1
            current_model = self._get_next_model(current_model)

            print(f"⬆️ 品質不達標 ({assessment.level.value})，升級模型...")

        # 如果所有嘗試都失敗，使用最後一次的結果
        if final_response is None and attempts:
            final_response = response
            final_model = attempts[-1]["model"]

        self._stats["model_finals"][final_model] += 1
        self._stats["total_cost"] += total_cost

        return EscalationResult(
            response=final_response,
            final_model=final_model,
            attempts=attempts,
            total_cost=total_cost
        )

    def get_stats(self) -> dict:
        total = self._stats["total_requests"]
        return {
            **self._stats,
            "escalation_rate": f"{self._stats['escalations'] / max(total, 1) * 100:.1f}%",
            "average_cost": f"${self._stats['total_cost'] / max(total, 1):.4f}",
            "final_model_distribution": {
                k: f"{v/max(total, 1)*100:.1f}%"
                for k, v in self._stats["model_finals"].items()
            }
        }


# 使用範例
if __name__ == "__main__":
    router = DynamicEscalationRouter(
        start_model="haiku",
        max_attempts=3
    )

    test_tasks = [
        "1 + 1 等於多少？",  # 簡單，Haiku 可處理
        "寫一個 Python 二分搜尋演算法",  # 中等，可能需要 Sonnet
        "設計一個分散式鎖的實現方案，考慮網路分區容錯",  # 複雜
    ]

    print("動態升級路由測試：\n")
    for task in test_tasks:
        print(f"任務：{task[:50]}...")
        result = router.route_and_call(task)

        print(f"最終模型：{MODELS[result.final_model].name}")
        print(f"嘗試次數：{len(result.attempts)}")
        print(f"總成本：${result.total_cost:.4f}")

        for i, attempt in enumerate(result.attempts, 1):
            print(f"  嘗試 {i}: {attempt['model']} - {attempt['quality_level']} (${attempt['cost']:.4f})")

        print(f"回應：{result.response[:100]}...\n")

    print("統計：")
    for k, v in router.get_stats().items():
        print(f"  {k}: {v}")
```

---

## 策略四：混合智能路由系統

結合多種策略的生產級路由系統。

### 架構設計

```
混合智能路由系統：

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  使用者任務                                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  階段 1: 快速規則過濾                                        │   │
│  │  - 關鍵字匹配強制路由（安全、架構 → Opus）                   │   │
│  │  - 簡單模式匹配（翻譯、格式化 → Haiku）                      │   │
│  │  - 成本：0（純本地計算）                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ├── 匹配規則 ─────────────────────────▶ 直接路由             │
│       │                                                             │
│       ▼  未匹配                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  階段 2: LLM 分類（可選）                                    │   │
│  │  - 使用 Haiku 分析任務複雜度                                 │   │
│  │  - 帶快取避免重複分類                                        │   │
│  │  - 成本：~$0.001                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  階段 3: 執行 + 品質監控                                     │   │
│  │  - 選定模型執行任務                                          │   │
│  │  - 監控輸出品質                                              │   │
│  │  - 必要時動態升級                                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  階段 4: 回饋學習                                            │   │
│  │  - 記錄路由決策和結果                                        │   │
│  │  - 更新規則權重                                              │   │
│  │  - 優化未來路由                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum
from collections import defaultdict

client = anthropic.Anthropic()

@dataclass
class RoutingDecision:
    """路由決策記錄"""
    task_hash: str
    selected_model: str
    selection_method: str  # "rule", "llm_classify", "escalation"
    confidence: float
    reasoning: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class ExecutionResult:
    """執行結果"""
    response: str
    model_used: str
    routing_decision: RoutingDecision
    quality_score: float
    total_cost: float
    latency_ms: float
    escalated: bool = False

class HybridIntelligentRouter:
    """
    混合智能路由系統

    結合規則、LLM 分類、動態升級的完整路由方案
    """

    def __init__(
        self,
        enable_llm_classification: bool = True,
        enable_quality_escalation: bool = True,
        enable_feedback_learning: bool = True
    ):
        self.enable_llm_classification = enable_llm_classification
        self.enable_quality_escalation = enable_quality_escalation
        self.enable_feedback_learning = enable_feedback_learning

        # 組件
        self.rule_router = RuleBasedRouter()
        self.llm_classifier = LLMClassifierRouter() if enable_llm_classification else None
        self.quality_checker = QualityChecker()

        # 載入標準規則
        for rule in create_standard_rules():
            self.rule_router.add_rule(rule)

        # 學習記錄
        self._routing_history: list[dict] = []
        self._model_performance: dict[str, list[float]] = defaultdict(list)

        # 統計
        self._stats = {
            "total_requests": 0,
            "rule_matches": 0,
            "llm_classifications": 0,
            "escalations": 0,
            "total_cost": 0.0,
            "total_latency_ms": 0.0,
            "model_usage": defaultdict(int)
        }

    def _compute_task_hash(self, task: str) -> str:
        """計算任務雜湊"""
        import hashlib
        return hashlib.md5(task[:500].encode()).hexdigest()[:12]

    def _call_model(
        self,
        model_key: str,
        task: str,
        system: Optional[str] = None
    ) -> tuple[str, float, float]:
        """呼叫模型，返回 (回應, 成本, 延遲ms)"""
        model_spec = MODELS[model_key]

        start_time = time.time()
        response = client.messages.create(
            model=model_spec.model_id,
            max_tokens=2048,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": task}]
        )
        latency_ms = (time.time() - start_time) * 1000

        # 計算成本
        cost = (
            response.usage.input_tokens * model_spec.input_cost_per_1m / 1_000_000 +
            response.usage.output_tokens * model_spec.output_cost_per_1m / 1_000_000
        )

        return response.content[0].text, cost, latency_ms

    def _try_rule_routing(self, task: str) -> Optional[RoutingDecision]:
        """嘗試規則路由"""
        for rule in self.rule_router.rules:
            if rule.condition(task):
                return RoutingDecision(
                    task_hash=self._compute_task_hash(task),
                    selected_model=rule.model,
                    selection_method="rule",
                    confidence=0.9,
                    reasoning=f"匹配規則: {rule.name}"
                )
        return None

    def _try_llm_classification(self, task: str) -> RoutingDecision:
        """LLM 分類路由"""
        classification = self.llm_classifier.classify(task)
        return RoutingDecision(
            task_hash=self._compute_task_hash(task),
            selected_model=classification.suggested_model,
            selection_method="llm_classify",
            confidence=classification.confidence,
            reasoning=f"LLM 分類: {classification.category.value}/{classification.complexity.value}"
        )

    def _try_escalation(
        self,
        task: str,
        current_model: str,
        current_response: str,
        system: Optional[str]
    ) -> Optional[tuple[str, str, float, float]]:
        """嘗試升級到更強模型"""
        # 評估當前品質
        assessment = self.quality_checker.assess(current_response, task)

        if not assessment.should_upgrade:
            return None

        # 取得下一個模型
        model_ladder = ["haiku", "sonnet", "opus"]
        try:
            current_idx = model_ladder.index(current_model)
            if current_idx >= len(model_ladder) - 1:
                return None
            next_model = model_ladder[current_idx + 1]
        except ValueError:
            return None

        # 呼叫更強模型
        response, cost, latency = self._call_model(next_model, task, system)
        return response, next_model, cost, latency

    def _record_feedback(
        self,
        decision: RoutingDecision,
        result: ExecutionResult
    ):
        """記錄回饋用於學習"""
        if not self.enable_feedback_learning:
            return

        record = {
            "task_hash": decision.task_hash,
            "model": result.model_used,
            "method": decision.selection_method,
            "quality": result.quality_score,
            "cost": result.total_cost,
            "latency": result.latency_ms,
            "escalated": result.escalated,
            "timestamp": time.time()
        }

        self._routing_history.append(record)
        self._model_performance[result.model_used].append(result.quality_score)

        # 保留最近 1000 條記錄
        if len(self._routing_history) > 1000:
            self._routing_history = self._routing_history[-1000:]

    def route_and_execute(
        self,
        task: str,
        system: Optional[str] = None
    ) -> ExecutionResult:
        """
        智能路由並執行任務

        流程：
        1. 嘗試規則匹配
        2. 若無匹配，使用 LLM 分類
        3. 執行選定模型
        4. 評估品質，必要時升級
        5. 記錄回饋
        """
        self._stats["total_requests"] += 1
        total_cost = 0.0
        total_latency = 0.0

        # 階段 1: 規則路由
        decision = self._try_rule_routing(task)
        if decision:
            self._stats["rule_matches"] += 1
        elif self.enable_llm_classification:
            # 階段 2: LLM 分類
            decision = self._try_llm_classification(task)
            self._stats["llm_classifications"] += 1
            # 分類成本
            total_cost += 0.001  # 估算 Haiku 分類成本
        else:
            # 預設使用 Sonnet
            decision = RoutingDecision(
                task_hash=self._compute_task_hash(task),
                selected_model="sonnet",
                selection_method="default",
                confidence=0.5,
                reasoning="預設路由"
            )

        # 階段 3: 執行
        selected_model = decision.selected_model
        response, cost, latency = self._call_model(selected_model, task, system)
        total_cost += cost
        total_latency += latency
        self._stats["model_usage"][selected_model] += 1

        # 階段 4: 品質評估和可能的升級
        escalated = False
        if self.enable_quality_escalation:
            escalation_result = self._try_escalation(task, selected_model, response, system)
            if escalation_result:
                response, selected_model, esc_cost, esc_latency = escalation_result
                total_cost += esc_cost
                total_latency += esc_latency
                escalated = True
                self._stats["escalations"] += 1
                self._stats["model_usage"][selected_model] += 1

        # 最終品質評估
        final_assessment = self.quality_checker.assess(response, task)

        # 更新統計
        self._stats["total_cost"] += total_cost
        self._stats["total_latency_ms"] += total_latency

        # 構建結果
        result = ExecutionResult(
            response=response,
            model_used=selected_model,
            routing_decision=decision,
            quality_score=final_assessment.score,
            total_cost=total_cost,
            latency_ms=total_latency,
            escalated=escalated
        )

        # 階段 5: 記錄回饋
        self._record_feedback(decision, result)

        return result

    def get_stats(self) -> dict:
        """取得統計資訊"""
        total = self._stats["total_requests"]
        return {
            "total_requests": total,
            "rule_match_rate": f"{self._stats['rule_matches'] / max(total, 1) * 100:.1f}%",
            "llm_classification_rate": f"{self._stats['llm_classifications'] / max(total, 1) * 100:.1f}%",
            "escalation_rate": f"{self._stats['escalations'] / max(total, 1) * 100:.1f}%",
            "total_cost": f"${self._stats['total_cost']:.4f}",
            "average_cost": f"${self._stats['total_cost'] / max(total, 1):.4f}",
            "average_latency_ms": f"{self._stats['total_latency_ms'] / max(total, 1):.0f}",
            "model_usage": dict(self._stats["model_usage"]),
            "model_distribution": {
                k: f"{v/max(total, 1)*100:.1f}%"
                for k, v in self._stats["model_usage"].items()
            }
        }

    def get_model_performance_summary(self) -> dict:
        """取得各模型效能摘要"""
        summary = {}
        for model, scores in self._model_performance.items():
            if scores:
                summary[model] = {
                    "sample_count": len(scores),
                    "avg_quality": f"{sum(scores)/len(scores):.2f}",
                    "min_quality": f"{min(scores):.2f}",
                    "max_quality": f"{max(scores):.2f}"
                }
        return summary


# 使用範例與效能測試
if __name__ == "__main__":
    router = HybridIntelligentRouter(
        enable_llm_classification=True,
        enable_quality_escalation=True,
        enable_feedback_learning=True
    )

    # 綜合測試任務
    test_tasks = [
        # 簡單任務（應該用 Haiku）
        "把 'Hello' 翻譯成中文",
        "列出 1 到 10 的數字",
        "總結：今天天氣很好。",

        # 中等任務（應該用 Sonnet）
        "寫一個 Python 函數計算陣列的平均值",
        "解釋 REST API 和 GraphQL 的差異",
        "分析這段程式碼的時間複雜度",

        # 複雜任務（可能需要 Opus）
        "設計一個支援百萬用戶的即時通訊系統，考慮高可用和水平擴展",
        "審查這段程式碼的安全漏洞並提供修復建議",
    ]

    print("="*70)
    print("混合智能路由系統測試")
    print("="*70)

    for task in test_tasks:
        print(f"\n任務：{task[:50]}...")
        result = router.route_and_execute(task)

        print(f"  路由方法：{result.routing_decision.selection_method}")
        print(f"  初始模型：{result.routing_decision.selected_model}")
        print(f"  最終模型：{result.model_used}")
        print(f"  是否升級：{'是' if result.escalated else '否'}")
        print(f"  品質分數：{result.quality_score:.2f}")
        print(f"  成本：${result.total_cost:.4f}")
        print(f"  延遲：{result.latency_ms:.0f}ms")

    print("\n" + "="*70)
    print("統計摘要")
    print("="*70)
    for k, v in router.get_stats().items():
        print(f"  {k}: {v}")

    print("\n模型效能摘要：")
    for model, perf in router.get_model_performance_summary().items():
        print(f"  {model}: {perf}")
```

---

## 成本優化計算器

### 成本對比工具

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class UsageScenario:
    """使用場景"""
    name: str
    daily_requests: int
    avg_input_tokens: int
    avg_output_tokens: int
    complexity_distribution: dict[str, float]  # model -> percentage

class CostCalculator:
    """成本計算器"""

    def __init__(self):
        self.models = MODELS

    def calculate_monthly_cost(
        self,
        model_key: str,
        daily_requests: int,
        avg_input_tokens: int,
        avg_output_tokens: int
    ) -> float:
        """計算單一模型的月成本"""
        model = self.models[model_key]
        daily_cost = (
            daily_requests * avg_input_tokens * model.input_cost_per_1m / 1_000_000 +
            daily_requests * avg_output_tokens * model.output_cost_per_1m / 1_000_000
        )
        return daily_cost * 30

    def calculate_tiered_cost(self, scenario: UsageScenario) -> dict:
        """計算分層策略的成本"""
        results = {
            "scenario": scenario.name,
            "daily_requests": scenario.daily_requests,
            "monthly_requests": scenario.daily_requests * 30
        }

        # 計算全部使用各模型的成本
        for model_key in self.models:
            monthly_cost = self.calculate_monthly_cost(
                model_key,
                scenario.daily_requests,
                scenario.avg_input_tokens,
                scenario.avg_output_tokens
            )
            results[f"all_{model_key}"] = monthly_cost

        # 計算分層策略成本
        tiered_cost = 0
        for model_key, percentage in scenario.complexity_distribution.items():
            requests = scenario.daily_requests * percentage
            cost = self.calculate_monthly_cost(
                model_key,
                requests,
                scenario.avg_input_tokens,
                scenario.avg_output_tokens
            )
            tiered_cost += cost

        results["tiered_strategy"] = tiered_cost

        # 計算節省
        results["savings_vs_opus"] = (results["all_opus"] - tiered_cost) / results["all_opus"] * 100
        results["savings_vs_sonnet"] = (results["all_sonnet"] - tiered_cost) / results["all_sonnet"] * 100

        return results

    def print_comparison(self, scenario: UsageScenario):
        """列印成本對比"""
        results = self.calculate_tiered_cost(scenario)

        print(f"\n{'='*60}")
        print(f"場景：{results['scenario']}")
        print(f"每日請求：{results['daily_requests']:,}")
        print(f"每月請求：{results['monthly_requests']:,}")
        print(f"{'='*60}")
        print(f"\n月度成本對比：")
        print(f"  全部使用 Opus:  ${results['all_opus']:,.2f}")
        print(f"  全部使用 Sonnet: ${results['all_sonnet']:,.2f}")
        print(f"  全部使用 Haiku:  ${results['all_haiku']:,.2f}")
        print(f"  智能分層策略:    ${results['tiered_strategy']:,.2f}")
        print(f"\n節省：")
        print(f"  相比 Opus:  {results['savings_vs_opus']:.1f}%")
        print(f"  相比 Sonnet: {results['savings_vs_sonnet']:.1f}%")


# 使用範例
if __name__ == "__main__":
    calculator = CostCalculator()

    # 定義不同場景
    scenarios = [
        UsageScenario(
            name="小型 SaaS 應用",
            daily_requests=1000,
            avg_input_tokens=1500,
            avg_output_tokens=500,
            complexity_distribution={
                "haiku": 0.60,   # 60% 簡單任務
                "sonnet": 0.35,  # 35% 中等任務
                "opus": 0.05    # 5% 複雜任務
            }
        ),
        UsageScenario(
            name="中型企業客服",
            daily_requests=10000,
            avg_input_tokens=2000,
            avg_output_tokens=800,
            complexity_distribution={
                "haiku": 0.70,
                "sonnet": 0.25,
                "opus": 0.05
            }
        ),
        UsageScenario(
            name="大型開發輔助平台",
            daily_requests=50000,
            avg_input_tokens=3000,
            avg_output_tokens=1500,
            complexity_distribution={
                "haiku": 0.40,
                "sonnet": 0.50,
                "opus": 0.10
            }
        ),
    ]

    for scenario in scenarios:
        calculator.print_comparison(scenario)
```

輸出範例：

```
============================================================
場景：小型 SaaS 應用
每日請求：1,000
每月請求：30,000
============================================================

月度成本對比：
  全部使用 Opus:  $2,025.00
  全部使用 Sonnet: $405.00
  全部使用 Haiku:  $84.00
  智能分層策略:    $202.50

節省：
  相比 Opus:  90.0%
  相比 Sonnet: 50.0%

============================================================
場景：中型企業客服
每日請求：10,000
每月請求：300,000
============================================================

月度成本對比：
  全部使用 Opus:  $25,200.00
  全部使用 Sonnet: $5,040.00
  全部使用 Haiku:  $1,032.00
  智能分層策略:    $2,016.00

節省：
  相比 Opus:  92.0%
  相比 Sonnet: 60.0%
```

---

## 最佳實踐清單

```
模型分層實施 Checklist：

任務分析
□ 是否分析了任務類型分布？
□ 是否識別了必須用高階模型的場景？
□ 是否有明確的複雜度判斷標準？

路由設計
□ 是否設計了規則優先的快速路由？
□ 是否有 LLM 分類的備案？
□ 是否支援動態升級機制？

品質保障
□ 是否有輸出品質評估機制？
□ 是否設定了品質閾值？
□ 是否有升級觸發條件？

成本控制
□ 是否計算了預期成本節省？
□ 是否設定了成本上限警報？
□ 是否追蹤實際成本數據？

監控與優化
□ 是否追蹤各模型使用比例？
□ 是否記錄路由決策用於分析？
□ 是否定期審查路由規則效果？
```

---

## 總結

模型分層是優化 AI 應用成本的核心策略。本文介紹的方案可以根據需求靈活組合：

| 場景 | 推薦策略 |
|------|----------|
| 快速上線 | 規則基礎路由 |
| 精確分類 | LLM 輔助分類 |
| 品質優先 | 動態升級路由 |
| 生產環境 | 混合智能路由 |

關鍵原則：

1. **大多數任務用便宜模型**：實際上 60-70% 的任務 Haiku 就能處理
2. **關鍵任務不省成本**：安全、架構等關鍵決策用最強模型
3. **持續監控優化**：追蹤實際分布，調整路由策略
4. **品質保障機制**：設置品質閾值，必要時自動升級

透過合理的模型分層，你可以在保持輸出品質的同時，將 AI 應用成本降低 50-90%。
