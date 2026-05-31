---
title: "FDE 面試準備指南（七）：Agent 深度設計——ReAct vs Planner、Tool Routing、Multi-Agent"
date: 2026-05-31T10:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 Agent 系統設計的五大主題：ReAct vs Planner-Executor 架構選擇、Tool Routing 設計、Multi-Agent vs Single-Agent 的 trade-off、Loop 終止策略，以及 Memory 設計"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "ReAct", "Planner", "Multi-Agent", "Tool Routing", "Memory", "LangGraph", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> Agent 面試題的陷阱不是問你能不能架起來。  
> 而是問你在什麼情況下選哪種架構，以及出問題時你怎麼 debug。  
> 架構選擇題沒有標準答案，有的是 trade-off 意識。

---

## 一、ReAct vs Planner-Executor：你什麼時候選哪個

這是 Agent 設計最核心的架構決策。  
面試官問法：

> *「你的 Agent 用什麼架構？為什麼？」*

---

### ReAct（Reasoning + Acting）

ReAct 是目前最主流的 Agent 架構。核心循環：

```
Thought → Action → Observation → Thought → Action → ...
```

每一步，LLM 先「思考」，再決定要執行什麼工具，看到結果後再繼續思考。

**範例：**
```
Thought: 用戶問的是 Q4 銷售數字，我需要查資料庫
Action: query_database(query="SELECT SUM(revenue) FROM sales WHERE quarter='Q4'")
Observation: 結果是 $4.2M
Thought: 我已經有數字了，可以回答
Action: final_answer("Q4 銷售額為 $4.2M")
```

**優點：**
- 彈性高，可以根據 Observation 動態調整
- 適合任務不確定、需要探索的場景
- 實作相對簡單

**缺點：**
- 每步都依賴 LLM 決策，延遲高
- 容易陷入循環（見後面的 Loop Termination）
- 長任務的 context 累積快，容易超出 window

---

### Planner-Executor

把規劃和執行分開：

```
Planner LLM → 產出完整計畫（步驟清單）
      ↓
Executor → 逐步執行計畫中的每個步驟
      ↓
（可選）Reviewer → 驗證結果，決定是否需要重新規劃
```

**範例計畫輸出：**
```json
{
  "steps": [
    {"id": 1, "tool": "search_knowledge_base", "input": "Q4 sales target"},
    {"id": 2, "tool": "query_database", "input": "Q4 actual revenue"},
    {"id": 3, "tool": "calculate", "input": "actual / target * 100"},
    {"id": 4, "tool": "generate_report", "input": "steps 1-3 results"}
  ]
}
```

**優點：**
- 計畫可以並行執行無依賴的步驟（速度快）
- 更容易 debug（計畫是顯式的）
- 適合任務結構清楚的場景

**缺點：**
- 計畫一旦定下來就較難動態調整
- 如果初始規劃錯誤，後續執行全部跑偏
- 需要更複雜的框架（LangGraph 的 DAG 模式）

---

### 選哪個？

| 場景 | 建議 |
|------|------|
| 任務結構清楚，步驟可預測 | Planner-Executor |
| 任務需要探索，不確定幾步 | ReAct |
| 需要並行執行多個子任務 | Planner-Executor + 並行節點 |
| 快速原型 | ReAct（更容易上手） |
| 需要可審計、可解釋的流程 | Planner-Executor |

---

## 二、Tool Routing：讓 Agent 找到正確的工具

當 Agent 有很多工具（10+），Tool Routing 就是一個重要的設計問題。

面試官問：

> *「你的 Agent 有 20 個工具，它怎麼知道用哪個？」*

---

### 方法一：讓 LLM 自己選（Function Calling）

把所有工具的 schema 都放進 system prompt，讓 LLM 決定呼叫哪個。

**優點：** 簡單，LLM 自然語言理解能力強  
**問題：** 工具太多時，prompt 變長，LLM 選擇準確率下降（needle in a haystack 問題）

---

### 方法二：Tool Retrieval（工具搜尋）

把工具的 description embed 成向量。  
用戶輸入進來時，先搜尋最相關的 Top-K 個工具，只把這 K 個放進 context。

```python
# 工具向量庫
tool_embeddings = embed([tool.description for tool in all_tools])

# 每次查詢
query_embedding = embed(user_query)
relevant_tools = vector_search(query_embedding, tool_embeddings, top_k=5)

# 只送 5 個工具給 LLM 選
response = llm.call(tools=relevant_tools, query=user_query)
```

**優點：** 解決工具過多的問題  
**缺點：** 如果搜尋沒找到正確工具，LLM 也選不了

---

### 方法三：Rule-Based Router

對特定 pattern 直接指定工具，不過 LLM。

```python
def route(query):
    if "sql" in query.lower() or "database" in query.lower():
        return sql_tool
    if "image" in query.lower() or "圖片" in query:
        return vision_tool
    return default_llm_router(query)
```

**優點：** 速度快，可預測，成本低  
**缺點：** Pattern 需要維護，處理不了模糊情況

---

### 方法四：Classifier Router

訓練一個小分類器（或用 embedding 的 few-shot 分類），判斷 query 屬於哪個工具類別。

比 Rule-Based 靈活，比 LLM 便宜。  
適合：工具類別固定、流量大、對 latency 敏感的場景。

---

### 實務設計建議

```
入口 Query
    ↓
Rule-Based 快速過濾（能確定的先過）
    ↓
Tool Retrieval（縮減候選工具數）
    ↓
LLM 最終選擇（從 Top-K 工具中選）
```

三層漏斗，從快到慢，從便宜到貴。

---

## 三、Multi-Agent vs Single-Agent：什麼時候拆開

面試官問：

> *「你為什麼用 Multi-Agent？Single-Agent 不夠嗎？」*

這題考的是你有沒有真正理解拆分的代價和收益。

---

### Single-Agent 的極限

Single-Agent 在以下情況開始撐不住：

1. **任務太長**：Context window 裝不下所有的 Thought/Action/Observation 歷史
2. **技能太雜**：一個 Agent 又要寫程式又要分析財報又要搜尋網頁，prompt 很難設計好
3. **需要並行**：Single-Agent 是序列的，無法同時做兩件事
4. **需要驗證**：沒有獨立的視角來驗證自己的輸出

---

### Multi-Agent 的設計模式

**Supervisor-Worker 模式：**
```
Supervisor Agent（協調者）
    ├── Worker Agent A（負責資料搜尋）
    ├── Worker Agent B（負責程式碼生成）
    └── Worker Agent C（負責報告撰寫）
```

Supervisor 負責任務分解和結果整合，Worker 專注於特定能力。

**Pipeline 模式：**
```
Agent 1（資料收集）→ Agent 2（資料分析）→ Agent 3（報告生成）
```

Sequential，每個 Agent 的輸出是下一個的輸入。

**Peer Review 模式：**
```
Generator Agent → Critic Agent → Generator Agent（修訂）→ ...
```

一個生成，一個批評，循環改進。

---

### Multi-Agent 的代價

| 代價 | 說明 |
|------|------|
| **Latency 增加** | Agent 間通信有 overhead，LLM 呼叫次數增加 |
| **Error Propagation** | 前一個 Agent 的錯誤會傳遞到下一個 |
| **Debug 困難** | 不知道是哪個 Agent 出問題 |
| **State 管理** | Agent 間共享狀態需要設計 |
| **成本** | 更多 LLM 呼叫 = 更高成本 |

---

### 決策框架

```
任務可以一個 context window 解決？→ Single-Agent
    ↓ 不行
任務可以分解成獨立子任務？→ 並行 Multi-Agent
    ↓
任務有明確的階段性？→ Pipeline Multi-Agent
    ↓
任務需要反覆驗證改進？→ Peer Review Multi-Agent
```

---

## 四、Loop Termination：Agent 什麼時候該停

這是 Agent 最容易出問題的地方。  
面試官問：

> *「你的 Agent 如果陷入無限循環怎麼辦？」*

---

### Loop 的四種類型

**1. 進度停滯（Stagnation）**  
Agent 一直在嘗試同樣的工具，得到相似的結果，但沒有進展。

**2. 矛盾循環（Contradiction）**  
Agent A 說「做 X」，Agent B 說「不要 X」，兩者互相推翻。

**3. 資源耗盡（Resource Exhaustion）**  
LLM 不斷生成 Thought，context 越來越長，最終 OOM 或 timeout。

**4. 目標漂移（Goal Drift）**  
原本要做 A，中途工具呼叫把目標引到 B，越走越偏。

---

### 終止策略

**1. 硬性限制（Hard Limits）**

```python
MAX_STEPS = 20
MAX_TOKENS = 50000
MAX_TIME = 60  # seconds

if steps > MAX_STEPS or tokens > MAX_TOKENS or elapsed > MAX_TIME:
    return {"status": "terminated", "reason": "limit_exceeded"}
```

最基本，必須有。

**2. 進度偵測（Progress Detection）**

每 N 步檢查一次：最近的 observation 和上上次是否高度相似？  
如果相似度超過 threshold，視為停滯，強制終止。

```python
if similarity(last_observation, prev_observation) > 0.9:
    raise StagnationError("Agent appears stuck in a loop")
```

**3. Reflection Step**

每 K 步讓 Agent 做一次「自我反思」：

```
你已經執行了 {K} 步。
回顧你的目標：{original_goal}
你目前的進度：{summary}
你認為你在正確的方向上嗎？如果沒有，請重新規劃。
```

**4. External Supervisor**

另一個 LLM 負責監控主 Agent 的行為，判斷是否偏離目標。  
代價：多一次 LLM 呼叫。

---

## 五、Memory 設計：Agent 怎麼記住事情

面試官問：

> *「你的 Agent 如何在多輪對話中記住上下文？」*

---

### Memory 的四種類型

**1. In-Context Memory（即時記憶）**

就是 conversation history。把所有對話歷史放在 context 裡。

**優點：** 簡單，全部資訊都在  
**缺點：** 隨對話增長，context 越來越長，成本增加，且超出 window 後截斷

---

**2. External Memory（外部記憶）**

把歷史資訊存到外部儲存，需要時 retrieve：

- **Key-Value Store**：用戶偏好、設定（Redis）
- **Vector Store**：語意記憶，「上次你說你喜歡簡潔的回答」
- **Relational DB**：結構化歷史記錄

---

**3. Episodic Memory（情節記憶）**

記住特定事件或過去的任務執行記錄。

```python
# 儲存一次任務執行的摘要
memory_store.save({
    "timestamp": "2024-01-15",
    "task": "generate Q4 report",
    "outcome": "success",
    "tools_used": ["sql_query", "chart_generator"],
    "key_insight": "Q4 revenue exceeded target by 12%"
})
```

下次類似任務時，retrieve 相關的 episodic memory 作為參考。

---

**4. Procedural Memory（程序記憶）**

記住「怎麼做事」——工作流程、best practice、常見錯誤。

通常實作為 system prompt 或 few-shot examples 的一部分。

---

### 記憶的 CRUD 設計

好的 Memory 設計要能：

| 操作 | 說明 |
|------|------|
| **Write** | 新的重要資訊自動儲存 |
| **Read** | 相關記憶在需要時自動 retrieve |
| **Update** | 過時的記憶可以更新（用戶改了偏好）|
| **Forget** | 不相關或過期的記憶可以清除 |

---

### 記憶壓縮（Memory Summarization）

Context 太長時，不是直接截斷，而是用 LLM 先做摘要：

```python
if len(history) > MAX_HISTORY_LENGTH:
    summary = llm.summarize(history[:SUMMARIZE_N])
    history = [{"role": "system", "content": f"對話摘要：{summary}"}] + history[SUMMARIZE_N:]
```

這讓 Agent 保留關鍵資訊的同時，控制 context 長度。

---

## 架構選擇速查表

| 問題 | 選擇 |
|------|------|
| 任務需要動態決策 | ReAct |
| 任務結構清楚可拆解 | Planner-Executor |
| 工具太多（10+） | Tool Retrieval + LLM Router |
| 任務複雜、需要並行 | Multi-Agent |
| 防止無限循環 | Hard limits + Progress detection |
| 需要跨 session 記憶 | External memory（Vector Store） |

---

## 下一篇

[FDE 面試準備指南（八）：ML 基礎必備——從傳統機器學習到 Deep Learning](/posts/fde-interview-guide-part8-ml-fundamentals-zh/)
