---
title: "FDE 面試準備指南（十一）：RKK 實戰——AI Agent 線上除錯與故障排除"
date: 2026-06-03T10:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 AI Agent 在 RKK 面試中的 Troubleshooting 與 Online Debugging 題型：幻覺追蹤、工具呼叫失敗、無限迴圈、觀測性框架設計，以及 Google Doc 模擬情境的應答技巧"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Debugging", "Troubleshooting", "Observability", "Tracing", "LangGraph", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "17 min"
---

> FDE 的核心價值之一，是在客戶的生產環境裡快速找到問題在哪。  
> Agent debugging 不像傳統程式 debug——你沒辦法設中斷點，LLM 的決策過程是不透明的。  
> 面試官想看的是：你有沒有系統化的思維，能在混沌中找到訊號。

---

## 一、為什麼 Agent Debugging 是必考題

RKK 面試有一個常見題型：**Google Doc 模擬情境**。面試官給你一個假設的客戶 case，問你「這個 Agent 出了什麼問題，你會怎麼排查」。

典型場景：

> *「客戶的 RAG Agent 上線後，回答品質比 demo 時差很多，有時給的答案根本不在文件裡，有時完全不回答問題。你是負責的 FDE，你怎麼 debug？」*

這道題考的不是你背了多少工具，而是你的**排查思路**。

---

## 二、Agent 的五大故障模式

在排查之前，先建立故障分類的心智模型：

```
Agent 故障模式
├── 1. 幻覺（Hallucination）       ← LLM 捏造了不存在的資訊
├── 2. 工具呼叫失敗（Tool Failure） ← 工具沒被正確呼叫或回傳錯誤
├── 3. 無限迴圈（Infinite Loop）   ← Agent 陷入重複行為
├── 4. 任務偏移（Task Drift）      ← Agent 偏離原始目標
└── 5. Context 錯亂（Context Confusion） ← 資訊混淆或 context 超限
```

每種故障模式有不同的診斷方法和根本原因。

---

## 三、故障模式一：幻覺（Hallucination）

**症狀：** Agent 回答的內容不在知識庫裡，或引用了不存在的文件段落

**診斷步驟：**

```
1. 確認 retrieval 是否正確
   └─ 日誌裡，retrieval 有沒有回傳相關文件？相似度分數多少？

2. 確認 prompt 有沒有正確注入 context
   └─ LLM 收到的 prompt 裡，context 段落有沒有出現？

3. 確認 LLM 有沒有「超出 context 範圍回答」
   └─ 比對答案和 retrieved context，用 NLI 模型跑 faithfulness 分數
```

**程式碼：追蹤幻覺的 Instrumentation**

```python
import logging
from dataclasses import dataclass

@dataclass
class RAGTrace:
    query: str
    retrieved_chunks: list[str]
    retrieved_scores: list[float]
    llm_prompt: str
    llm_response: str
    
    def check_faithfulness(self) -> dict:
        """檢查回答是否有 context 支撐"""
        # 簡化版：檢查關鍵字是否在 retrieved chunks 中
        response_tokens = set(self.llm_response.lower().split())
        context_tokens = set(" ".join(self.retrieved_chunks).lower().split())
        
        # 過濾常見詞，只看實質性 token
        stopwords = {"的", "了", "是", "在", "有", "和", "a", "the", "is", "are"}
        response_keywords = response_tokens - stopwords
        
        coverage = len(response_keywords & context_tokens) / max(len(response_keywords), 1)
        
        return {
            "faithfulness_score": coverage,
            "potential_hallucination": coverage < 0.3,  # 低於 30% 視為潛在幻覺
            "retrieved_count": len(self.retrieved_chunks),
            "avg_relevance_score": sum(self.retrieved_scores) / max(len(self.retrieved_scores), 1)
        }

# 在 RAG pipeline 中加入追蹤
def rag_with_tracing(query: str, vector_store, llm) -> dict:
    # Retrieval
    results = vector_store.query(query, top_k=5)
    chunks = [r.text for r in results]
    scores = [r.score for r in results]
    
    # Build prompt
    context = "\n".join(chunks)
    prompt = f"根據以下文件回答問題：\n{context}\n\n問題：{query}"
    
    # LLM call
    response = llm.generate(prompt)
    
    # Create trace
    trace = RAGTrace(
        query=query,
        retrieved_chunks=chunks,
        retrieved_scores=scores,
        llm_prompt=prompt,
        llm_response=response
    )
    
    # Log trace for debugging
    faithfulness = trace.check_faithfulness()
    if faithfulness["potential_hallucination"]:
        logging.warning(f"Potential hallucination detected: {faithfulness}")
    
    return {"response": response, "trace": trace, "faithfulness": faithfulness}
```

**根本原因 & 解法：**

| 根本原因 | 診斷訊號 | 解法 |
|---------|---------|------|
| Retrieval 精度差 | 相似度分數低（< 0.7） | 調整 embedding model、增加 top_k |
| Context window 太短 | prompt 被截斷 | 增加 context 長度限制 |
| LLM 過於自信 | 回答超出 context 範圍 | 加強 system prompt 的限制指令 |
| 知識庫覆蓋不足 | query 與所有 chunk 相似度都低 | 補充知識庫內容 |

---

## 四、故障模式二：工具呼叫失敗（Tool Failure）

**症狀：** Agent 沒有呼叫應該呼叫的工具，或工具呼叫格式錯誤

**診斷步驟：**

```
1. 查看 LLM 的原始輸出
   └─ LLM 有沒有輸出 tool call？格式正確嗎？

2. 確認工具定義（schema）是否清晰
   └─ tool description 夠不夠清楚？parameter 說明有沒有歧義？

3. 確認工具執行有沒有報錯
   └─ tool execution layer 的 exception log
```

**程式碼：Tool Call 追蹤**

```python
class InstrumentedTool:
    """包裝工具以加入觀測能力"""
    
    def __init__(self, name: str, func, description: str):
        self.name = name
        self.func = func
        self.description = description
        self.call_log = []
    
    def __call__(self, **kwargs):
        import time
        start = time.time()
        
        log_entry = {
            "tool": self.name,
            "input": kwargs,
            "timestamp": start,
            "success": False,
            "output": None,
            "error": None,
            "latency_ms": None
        }
        
        try:
            result = self.func(**kwargs)
            log_entry["success"] = True
            log_entry["output"] = result
            return result
        except Exception as e:
            log_entry["error"] = str(e)
            logging.error(f"Tool {self.name} failed: {e}, inputs: {kwargs}")
            raise
        finally:
            log_entry["latency_ms"] = (time.time() - start) * 1000
            self.call_log.append(log_entry)

# 使用方式
search_tool = InstrumentedTool(
    name="search_knowledge_base",
    func=actual_search_function,
    description="搜尋公司知識庫，回傳相關文件段落。輸入：query（字串），top_k（整數，預設5）"
)
```

**常見工具呼叫失敗原因：**

```python
# ❌ 工具描述太模糊
{
    "name": "search",
    "description": "搜尋東西"  # LLM 不知道什麼時候該用這個工具
}

# ✅ 工具描述清晰、有使用時機說明
{
    "name": "search_knowledge_base",
    "description": """
    搜尋公司產品知識庫，回傳相關文件段落。
    使用時機：當用戶詢問產品規格、使用方法、故障排除步驟時。
    不適用：一般常識問題、計算問題。
    輸入參數：
    - query (string): 搜尋關鍵字，建議用繁體中文
    - top_k (int, optional): 回傳結果數量，預設 5，最大 20
    """,
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
            "top_k": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
}
```

---

## 五、故障模式三：無限迴圈（Infinite Loop）

**症狀：** Agent 一直在重複相同的動作，不斷呼叫同一個工具或產生相似的 thought

**診斷：**

```python
class LoopDetector:
    def __init__(self, window: int = 5, similarity_threshold: float = 0.9):
        self.window = window
        self.threshold = similarity_threshold
        self.action_history = []
    
    def check_loop(self, current_action: dict) -> bool:
        self.action_history.append(current_action)
        
        if len(self.action_history) < self.window:
            return False
        
        recent = self.action_history[-self.window:]
        
        # 簡單版：檢查最近 N 步是否有重複的 tool + 相似 input
        tool_calls = [a.get("tool") for a in recent]
        if len(set(tool_calls)) == 1:  # 全部都是同一個工具
            # 進一步檢查 input 是否相似
            inputs = [str(a.get("input", "")) for a in recent]
            if len(set(inputs)) <= 2:  # 幾乎相同的 input
                return True  # 偵測到迴圈
        
        return False
    
    def get_loop_report(self) -> dict:
        return {
            "detected": True,
            "repeated_actions": self.action_history[-self.window:],
            "suggestion": "Agent 可能卡在等待不會改變的條件，建議加入退出條件或限制最大步數"
        }
```

**迴圈的根本原因：**

1. **缺乏終止條件**：Agent 不知道什麼時候「完成了」
2. **工具回傳不變的結果**：每次查詢都沒有新資訊，但 Agent 不知道要換策略
3. **System prompt 矛盾**：被要求「一直確認直到用戶滿意」但用戶沒有反饋

**解法：**

```python
# 加入明確的終止條件和最大步數限制
agent_config = {
    "max_steps": 20,           # 硬上限
    "loop_detection_window": 5, # 偵測視窗
    "force_final_answer_after": 15,  # 超過 15 步強制輸出結果
}
```

---

## 六、觀測性框架設計（Observability）

面試官問法：

> *「你怎麼確保你部署的 Agent 在生產環境是可觀測的（observable）？」*

### 三層觀測性

```
Layer 1: Metrics（指標）       ← 系統健康狀態
Layer 2: Traces（追蹤）        ← 單次請求的執行路徑
Layer 3: Logs（日誌）          ← 詳細事件記錄
```

**Metrics 要收集什麼：**

```python
# 關鍵指標
metrics = {
    # 效能指標
    "p50_latency_ms": ...,   # 一般情況的延遲
    "p95_latency_ms": ...,   # 大多數用戶的延遲
    "p99_latency_ms": ...,   # 最差情況的延遲
    
    # 工具使用指標
    "tool_call_success_rate": ...,  # 工具呼叫成功率
    "avg_tool_calls_per_request": ...,  # 每個請求平均呼叫幾次工具
    
    # 品質指標
    "avg_steps_to_completion": ...,  # 完成任務平均需要幾步
    "loop_detection_rate": ...,  # 無限迴圈偵測率
    "fallback_rate": ...,  # 回退到 fallback 的比例
    
    # 成本指標
    "avg_input_tokens": ...,
    "avg_output_tokens": ...,
    "cost_per_request_usd": ...
}
```

**Trace 要記錄什麼：**

```python
@dataclass
class AgentTrace:
    request_id: str
    user_query: str
    steps: list[dict]  # 每一步的 thought + action + observation
    total_tokens: int
    total_latency_ms: float
    final_answer: str
    outcome: str  # "success" | "loop_detected" | "max_steps" | "error"
    
    def to_log(self) -> dict:
        return {
            "request_id": self.request_id,
            "query_preview": self.user_query[:100],
            "step_count": len(self.steps),
            "outcome": self.outcome,
            "total_tokens": self.total_tokens,
            "latency_ms": self.total_latency_ms,
            # 可以把完整 trace 存到 BigQuery/Cloud Storage，這裡只存摘要
        }
```

---

## 七、Google Doc 模擬情境應答技巧

RKK 面試中，面試官可能在 Google Doc 裡貼一段「對話記錄」或「Agent log」，問你看出什麼問題。

**應答框架（DARK）：**

| 字母 | 意義 | 你要說的 |
|------|------|---------|
| **D** | Diagnose | 根據症狀，最可能是哪種故障模式 |
| **A** | Ask | 你還需要什麼資訊才能確認（log、metrics、trace） |
| **R** | Root Cause | 推斷最可能的根本原因 |
| **K** | Kill it | 你會怎麼修，以及怎麼預防 |

### 範例情境演練

面試官貼出這段 log：

```
Step 1: Thought: 用戶問 Q4 銷售數字，我需要查資料庫
        Action: query_database(query="Q4 sales")
        Observation: Error: timeout after 30s

Step 2: Thought: 查詢失敗，我重試
        Action: query_database(query="Q4 sales")
        Observation: Error: timeout after 30s

Step 3: Thought: 再試一次
        Action: query_database(query="Q4 sales")
        Observation: Error: timeout after 30s
...（重複 20 次）

Step 22: [Agent stopped: max_steps reached]
```

**你的回答：**

> *「我看到的問題有兩層：*
>
> *第一層是工具層——資料庫查詢 timeout，這可能是網路問題、資料庫負載過高、或查詢本身沒有加 index 導致太慢。我需要查資料庫的 slow query log 和監控。*
>
> *第二層是 Agent 層——Agent 在工具失敗後只會重試，沒有退避策略（exponential backoff），也沒有在多次失敗後換策略（例如改查快取或回覆用戶「資料庫暫時不可用」）。*
>
> *修法：工具層加 retry with backoff（前 3 次）；第 4 次失敗後回報給 Agent「工具不可用」，由 Agent 決定是否能用其他方式回答，或直接告知用戶。同時在 tool wrapper 加警報，超過 3 次失敗就觸發告警。」*

---

## 八、快速複習卡

```
五大 Agent 故障模式：
├── 幻覺        → 追蹤 retrieval 品質 + faithfulness 分數
├── 工具失敗    → 清晰 tool description + instrumented wrapper
├── 無限迴圈    → loop detector + max_steps 硬上限
├── 任務偏移    → 每步確認與原始 goal 的對齊
└── Context 錯亂 → token monitor + 壓縮策略

觀測性三層：Metrics（健康）→ Traces（路徑）→ Logs（細節）

DARK 應答框架：Diagnose → Ask → Root Cause → Kill it
```

---

**系列導覽：**  
← [（十）RKK 實戰：AI Agent 的 Context Management](../fde-interview-guide-part10-context-management-zh/)  
→ [（十二）RKK 實戰：Agent 統計評估與品質量化](../fde-interview-guide-part12-agent-evaluation-zh/)
