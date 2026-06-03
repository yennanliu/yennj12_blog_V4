---
title: "FDE 面試準備指南（十二）：RKK 實戰——AI Agent 統計評估與品質量化"
date: 2026-06-03T11:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 AI Agent 的統計評估方法：LLM-native 指標（tokens/sec、cost-per-request）、RAG 評估三角、Agent 任務成功率，以及如何設計 eval pipeline 說服客戶信任 Agent 系統"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Evaluation", "Metrics", "RAG", "RAGAS", "LLM", "Observability", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> 客戶問：「你怎麼知道這個 Agent 夠好、可以上線？」  
> 如果你回答「我覺得還不錯」——你就出局了。  
> FDE 的職責是把感覺轉化成數字，把數字轉化成信心。

---

## 一、為什麼評估是 RKK 必考題

JD 上明確寫：**「Build evaluation pipelines and observability frameworks to ensure agentic systems meet requirements for accuracy, safety, and latency.」**

這不是加分項，是核心職責。

面試官問法：

> *「你要把一個 RAG Agent 從 demo 推上生產，你用什麼方式確認它達到了上線標準？」*

---

## 二、評估的三個維度

```
Agent 評估
├── 效能指標（Performance Metrics）    ← 系統層面：快不快、貴不貴
├── 品質指標（Quality Metrics）        ← 輸出層面：對不對、準不準
└── 業務指標（Business Metrics）       ← 價值層面：有沒有解決問題
```

這三個維度缺一不可。只看品質、不看效能，上線後延遲爆炸；只看效能、不看業務，系統跑很快但沒人想用。

---

## 三、效能指標（LLM-native Metrics）

JD 特別提到「LLM-native metrics」——這是面試時能讓你加分的詞。

### 核心指標

```python
performance_metrics = {
    # 吞吐量
    "tokens_per_second": 120,          # 每秒產生多少 token
    "requests_per_second": 5.2,        # 系統整體 QPS
    
    # 延遲（分位數比平均值更重要）
    "ttft_p50_ms": 450,                # Time to First Token，p50
    "ttft_p95_ms": 1200,               # p95，大多數用戶的體驗
    "e2e_latency_p50_ms": 3500,        # 端到端延遲
    "e2e_latency_p95_ms": 8000,
    
    # 成本
    "input_tokens_per_request": 2500,  # 每次請求的 input token 數
    "output_tokens_per_request": 400,  # 每次請求的 output token 數
    "cost_per_request_usd": 0.0085,    # 每次請求成本
    "monthly_cost_at_1k_dau_usd": ..., # 預估月費
}
```

**計算成本的公式（以 Gemini 1.5 Pro 為例）：**

```python
def estimate_cost(
    daily_requests: int,
    avg_input_tokens: int,
    avg_output_tokens: int,
    input_price_per_1m: float = 1.25,   # USD per 1M tokens
    output_price_per_1m: float = 5.00,  # USD per 1M tokens
) -> dict:
    daily_input_cost = (daily_requests * avg_input_tokens / 1_000_000) * input_price_per_1m
    daily_output_cost = (daily_requests * avg_output_tokens / 1_000_000) * output_price_per_1m
    daily_total = daily_input_cost + daily_output_cost
    
    return {
        "daily_cost_usd": daily_total,
        "monthly_cost_usd": daily_total * 30,
        "cost_per_request_usd": daily_total / daily_requests
    }

# 範例：1000 DAU，每人 5 次對話
estimate_cost(
    daily_requests=5000,
    avg_input_tokens=2500,
    avg_output_tokens=400
)
# → daily: ~$15, monthly: ~$450
```

---

## 四、RAG 品質評估三角

這是 RAG Agent 評估的核心框架：

```
        RAG 評估三角
        
       Faithfulness
           △
          / \
         /   \
        /     \
       /       \
      ●─────────●
  Context    Answer
  Relevance  Relevance
```

### 三個核心指標

| 指標 | 英文 | 問的問題 | 計算方式 |
|------|------|---------|---------|
| **Context Relevance** | Context Relevance | 檢索到的文件和問題有關嗎？ | retrieved chunks 和 query 的語意相似度 |
| **Faithfulness** | Faithfulness | 回答有沒有超出文件範圍（幻覺）？ | 回答中每個聲明是否可在文件中找到依據 |
| **Answer Relevance** | Answer Relevance | 回答有沒有回答到問題？ | 回答和問題的語意相似度 |

**用 RAGAS 框架實作：**

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_relevancy,
    context_recall
)
from datasets import Dataset

# 準備評估資料集
eval_data = {
    "question": [
        "Gemini 1.5 Pro 的 context window 有多大？",
        "如何在 Vertex AI 部署自訂模型？",
    ],
    "answer": [
        "Gemini 1.5 Pro 的 context window 是 128K tokens。",  # 故意答錯
        "在 Vertex AI 部署自訂模型需要...",
    ],
    "contexts": [
        ["Gemini 1.5 Pro 支援最高 1M tokens 的 context window..."],
        ["Vertex AI 提供 Model Garden 和 Custom Training..."],
    ],
    "ground_truth": [
        "Gemini 1.5 Pro 的 context window 是 1M tokens。",
        "在 Vertex AI 部署自訂模型的步驟是...",
    ]
}

dataset = Dataset.from_dict(eval_data)

result = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_relevancy, context_recall]
)

print(result)
# faithfulness: 0.5  ← 第一個答案答錯了，faithfulness 低
# answer_relevancy: 0.85
# context_relevancy: 0.9
# context_recall: 0.75
```

---

## 五、Agent 任務評估：超越 RAG

Agent 不只是問答，還有複雜的多步驟任務。評估方式不同：

### 任務完成率（Task Success Rate）

```python
@dataclass
class AgentEvalCase:
    task_description: str
    expected_outcome: dict   # 預期的最終結果
    actual_outcome: dict     # Agent 實際產出的結果
    
    def evaluate(self) -> dict:
        # 根據任務類型定義成功標準
        return {
            "task_completed": self._check_task_completion(),
            "correct_answer": self._check_answer_correctness(),
            "efficient_path": self._check_efficiency(),
        }
    
    def _check_task_completion(self) -> bool:
        required_fields = self.expected_outcome.get("required_fields", [])
        return all(field in self.actual_outcome for field in required_fields)
    
    def _check_efficiency(self) -> dict:
        expected_steps = self.expected_outcome.get("max_steps", 10)
        actual_steps = self.actual_outcome.get("step_count", 0)
        return {
            "within_budget": actual_steps <= expected_steps,
            "efficiency_score": min(1.0, expected_steps / max(actual_steps, 1))
        }

# 批量評估
def run_eval_suite(test_cases: list[AgentEvalCase]) -> dict:
    results = [case.evaluate() for case in test_cases]
    
    return {
        "task_completion_rate": sum(r["task_completed"] for r in results) / len(results),
        "correctness_rate": sum(r["correct_answer"] for r in results) / len(results),
        "avg_efficiency_score": sum(r["efficient_path"]["efficiency_score"] for r in results) / len(results),
        "sample_size": len(results)
    }
```

### 步驟品質評估（Trajectory Evaluation）

```python
# 不只看最終結果，也評估每一步是否合理
def evaluate_trajectory(steps: list[dict], ground_truth_steps: list[dict]) -> dict:
    """
    評估 Agent 的執行路徑是否合理
    
    - 有沒有執行了不必要的工具呼叫？
    - 有沒有漏掉關鍵步驟？
    - 步驟順序是否合理？
    """
    actual_tools = [s.get("tool") for s in steps if s.get("tool")]
    expected_tools = [s.get("tool") for s in ground_truth_steps if s.get("tool")]
    
    # 計算工具呼叫的 Precision 和 Recall
    actual_set = set(actual_tools)
    expected_set = set(expected_tools)
    
    precision = len(actual_set & expected_set) / max(len(actual_set), 1)
    recall = len(actual_set & expected_set) / max(len(expected_set), 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    return {
        "tool_precision": precision,
        "tool_recall": recall,
        "tool_f1": f1,
        "extra_tools_used": list(actual_set - expected_set),
        "missing_tools": list(expected_set - actual_set)
    }
```

---

## 六、LLM-as-Judge：用 LLM 評估 LLM

當沒有 ground truth 時，可以用另一個 LLM 當評審：

```python
def llm_judge(
    question: str,
    answer: str,
    context: str,
    judge_llm
) -> dict:
    judge_prompt = f"""
    你是一個 AI 回答品質評審。根據以下標準評分（1-5分）：
    
    問題：{question}
    提供的背景資料：{context}
    AI 的回答：{answer}
    
    評分標準：
    1. 忠實性（Faithfulness）：回答有沒有超出背景資料的範圍？
       - 5分：完全基於背景資料
       - 3分：大部分基於資料，少量推斷
       - 1分：有明顯不在資料中的聲明
    
    2. 相關性（Relevance）：回答有沒有回答到問題？
       - 5分：完全回答了問題
       - 3分：部分回答
       - 1分：沒有回答問題
    
    請以 JSON 格式回覆：
    {{
        "faithfulness_score": <1-5>,
        "faithfulness_reason": "<原因>",
        "relevance_score": <1-5>,
        "relevance_reason": "<原因>",
        "overall_assessment": "<整體評估>"
    }}
    """
    
    response = judge_llm.generate(judge_prompt)
    return parse_json(response)
```

**LLM-as-Judge 的注意事項：**

```
優點：
✓ 不需要 ground truth，適合開放性問題
✓ 可以評估細膩的品質維度

缺點（面試必須主動提出）：
✗ 評審 LLM 自己也可能有偏見
✗ 評分不穩定（同一個答案不同次評分可能不同）
✗ 對自家模型的輸出可能過於寬容（自我評分偏差）

緩解方法：
- 用不同的 LLM 當評審（避免同源偏差）
- 增加評審次數取平均（減少隨機性）
- 設計具體的評分 rubric，而不是讓 LLM 自由發揮
```

---

## 七、建立 Eval Pipeline

面試官問：

> *「你會怎麼設計一個 eval pipeline，讓它能持續追蹤 Agent 的品質？」*

```python
class AgentEvalPipeline:
    """持續評估 Agent 品質的 pipeline"""
    
    def __init__(self, agent, eval_dataset, metrics):
        self.agent = agent
        self.eval_dataset = eval_dataset  # 黃金測試集
        self.metrics = metrics
        self.baseline = None
    
    def run_eval(self, tag: str = "current") -> dict:
        results = []
        
        for case in self.eval_dataset:
            response = self.agent.run(case["question"])
            
            scores = {}
            for metric in self.metrics:
                scores[metric.name] = metric.evaluate(
                    question=case["question"],
                    answer=response,
                    context=case.get("context"),
                    ground_truth=case.get("ground_truth")
                )
            
            results.append({"case": case["question"][:50], "scores": scores})
        
        summary = self._aggregate(results)
        summary["tag"] = tag
        return summary
    
    def regression_test(self) -> dict:
        """比較當前版本和 baseline"""
        if not self.baseline:
            raise ValueError("請先設定 baseline")
        
        current = self.run_eval("current")
        
        regressions = {}
        for metric_name, current_score in current.items():
            if metric_name == "tag":
                continue
            baseline_score = self.baseline.get(metric_name, 0)
            delta = current_score - baseline_score
            
            if delta < -0.05:  # 下降超過 5% 視為 regression
                regressions[metric_name] = {
                    "baseline": baseline_score,
                    "current": current_score,
                    "delta": delta,
                    "severity": "high" if delta < -0.1 else "medium"
                }
        
        return {
            "has_regression": len(regressions) > 0,
            "regressions": regressions,
            "current_scores": current,
            "baseline_scores": self.baseline
        }
```

---

## 八、跟客戶溝通評估結果

FDE 的工作不只是做評估，還要讓客戶理解評估結果。

**客戶常見問題 & 你的回答：**

> *「為什麼要做 eval？模型不是已經很聰明了嗎？」*

「Gemini 確實很強大，但「強大」不等於「在你的資料上也對」。我們做 eval 是為了量化它在你的具體場景下的表現，並且有辦法在每次我們改系統的時候，確認改動沒有讓品質下降。這是讓系統能安全上線的基礎。」

> *「faithfulness 0.85 代表什麼？夠好嗎？」*

「意思是在我們的測試集裡，約 15% 的回答包含了知識庫以外的資訊。這樣夠不夠好，取決於你的業務場景。如果是醫療建議，我們可能要求 0.95+；如果是一般 FAQ，0.85 可能可以接受。我會建議我們先定義你的 acceptable threshold，然後朝那個目標優化。」

---

## 九、快速複習卡

```
評估三維度：效能（速度/成本）→ 品質（對不對）→ 業務（有沒有用）

RAG 評估三角：
├── Context Relevance  → 檢索到的文件夠不夠相關
├── Faithfulness       → 回答有沒有幻覺
└── Answer Relevance   → 回答有沒有回答問題

LLM-native Metrics：
├── tokens/sec（吞吐量）
├── TTFT p95（用戶體驗延遲）
└── cost-per-request（成本）

Eval Pipeline：測試集 → 跑指標 → 比較 baseline → Regression test
```

---

**系列導覽：**  
← [（十一）RKK 實戰：Agent 線上除錯與故障排除](../fde-interview-guide-part11-agent-debugging-zh/)  
→ [（十三）RKK 實戰：Prompt Injection 攻防與 Agent 安全](../fde-interview-guide-part13-prompt-injection-zh/)
