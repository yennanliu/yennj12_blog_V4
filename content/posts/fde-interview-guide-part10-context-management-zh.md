---
title: "FDE 面試準備指南（十）：RKK 實戰——AI Agent 的 Context Management"
date: 2026-06-03T09:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 AI Agent 在 RKK 面試中最常被問的 Context Management 問題：Context Window 壓縮策略、對話歷史管理、Sliding Window vs Summary Buffer，以及 Multi-turn Agent 的 context 設計"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Context Management", "LLM", "Context Window", "Memory", "LangGraph", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> RKK 的 context management 題型，不是考你背得出 Gemini 的 context window 有多大。  
> 是考你在 context 快滿的時候，你的 Agent 怎麼辦。  
> 這才是工程師每天在生產環境面對的真實問題。

---

## 一、為什麼 Context Management 是 FDE 必考題

FDE 的日常就是把客戶的 Agent prototype 推上生產。而生產環境裡，context 管理不好會導致：

- **幻覺率升高**：context 太長或太雜，LLM 開始忽略重要資訊
- **延遲爆炸**：每個 token 都要過 attention，context 越長越慢
- **成本失控**：input token 計費，context 每輪翻倍很快燒錢
- **系統崩潰**：超過 context window 直接報錯，Agent 中斷

面試官問法：

> *「你的 multi-turn Agent 在第 50 輪對話時，會發生什麼問題？你怎麼設計解決它？」*

---

## 二、Context Window 的工程現實

### 數字要記住

| 模型 | Context Window | 實際可用（建議） |
|------|---------------|-----------------|
| Gemini 1.5 Pro | 1M tokens | ~700K（留空間給 output） |
| Gemini 2.0 Flash | 1M tokens | ~700K |
| GPT-4o | 128K tokens | ~100K |
| Claude 3.5 Sonnet | 200K tokens | ~150K |

「有 1M context 所以不用管理」——這是錯誤的工程思維。

**原因：**
1. **Lost-in-the-Middle 效應**：LLM 對中段資訊的注意力最弱
2. **延遲隨 context 線性成長**：1M token 的推理成本是 100K 的 10 倍
3. **成本**：1M token input 在 Gemini Pro 大約 $3.5，多輪對話快速累積

---

## 三、Multi-turn Agent 的 Context 累積問題

### 問題示意

```
輪次 1: system_prompt (500t) + user_msg (50t) + assistant (200t) = 750t
輪次 2: system_prompt (500t) + history (750t) + user_msg (50t) + assistant (200t) = 1500t
輪次 3: system_prompt (500t) + history (1500t) + user_msg (50t) + assistant (200t) = 2250t
...
輪次 N: context ≈ N × avg_turn_size
```

**到第 100 輪，context 可能超過 20K tokens**，如果每輪平均 200 tokens。長文本任務（Agent 處理文件、搜尋、分析）每輪可能 2000+ tokens，10 輪就超過 20K。

面試官考點：

> *「你會怎麼處理 conversation history 讓它不爆掉？」*

---

## 四、四種 Context 管理策略

### 策略一：Sliding Window（滑動視窗）

只保留最近 N 輪的對話歷史：

```python
class SlidingWindowMemory:
    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self.history: list[dict] = []
    
    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        # 超過上限時，移除最舊的一輪（user + assistant = 2筆）
        while len(self.history) > self.max_turns * 2:
            self.history.pop(0)
            self.history.pop(0)
    
    def get_context(self) -> list[dict]:
        return self.history.copy()
```

**優點：** 實作簡單，context 大小可預測  
**缺點：** 丟失早期對話，可能失去重要背景資訊

**適用場景：** 閒聊型 chatbot、每輪相對獨立的任務

---

### 策略二：Summary Buffer（摘要緩衝）

舊對話壓縮成摘要，只保留近期完整歷史：

```python
class SummaryBufferMemory:
    def __init__(self, llm, max_token_limit: int = 2000, recent_turns: int = 5):
        self.llm = llm
        self.max_token_limit = max_token_limit
        self.recent_turns = recent_turns
        self.summary = ""
        self.recent_history: list[dict] = []
    
    def add(self, role: str, content: str):
        self.recent_history.append({"role": role, "content": content})
        
        if self._estimate_tokens() > self.max_token_limit:
            self._compress_oldest()
    
    def _compress_oldest(self):
        # 取最舊的幾輪來壓縮
        to_compress = self.recent_history[:-self.recent_turns * 2]
        self.recent_history = self.recent_history[-self.recent_turns * 2:]
        
        # 用 LLM 壓縮成摘要
        compress_prompt = f"""
        以下是對話歷史，請壓縮成一段簡潔的摘要，保留關鍵資訊：
        
        現有摘要：{self.summary}
        
        新增對話：
        {self._format_history(to_compress)}
        
        更新後的摘要：
        """
        self.summary = self.llm.generate(compress_prompt)
    
    def get_context(self) -> str:
        return f"[對話摘要]\n{self.summary}\n\n[近期對話]\n{self._format_history(self.recent_history)}"
```

**優點：** 保留語意連貫性，context 大小可控  
**缺點：** 壓縮本身需要額外 LLM 呼叫（增加延遲和成本）；壓縮可能丟失細節

**適用場景：** 長對話 customer service、需要「記得以前說過什麼」的 Agent

---

### 策略三：Selective Retrieval（選擇性檢索）

不存整段歷史，改為把對話寫入向量資料庫，每輪只檢索相關片段：

```python
class RetrievalMemory:
    def __init__(self, vector_store, embedder, top_k: int = 3):
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k
    
    def add(self, role: str, content: str, turn_id: int):
        embedding = self.embedder.embed(content)
        self.vector_store.upsert(
            id=f"turn_{turn_id}_{role}",
            vector=embedding,
            metadata={"role": role, "content": content, "turn": turn_id}
        )
    
    def get_relevant(self, current_query: str) -> list[dict]:
        query_embedding = self.embedder.embed(current_query)
        results = self.vector_store.query(
            vector=query_embedding,
            top_k=self.top_k
        )
        return [r.metadata for r in results]
```

**優點：** context 完全可控；能檢索到很久以前的相關資訊  
**缺點：** 需要維護向量資料庫；檢索結果可能打亂對話連貫性

**適用場景：** 長期客戶服務、需要跨 session 記憶的 Agent

---

### 策略四：Structured State（結構化狀態）

不存原始對話，只更新結構化的「狀態物件」：

```python
# Agent 的狀態不是對話歷史，而是提煉後的結構
class AgentState(TypedDict):
    task_goal: str           # 用戶最終要什麼
    current_step: str        # 現在執行到哪步
    completed_steps: list    # 已完成的步驟摘要
    key_findings: dict       # 重要發現（從工具回傳中提取）
    user_constraints: list   # 用戶給的限制條件
    pending_questions: list  # 還需要釐清的問題

# 每輪更新 state，而不是累積對話歷史
def update_state(state: AgentState, llm_output: str) -> AgentState:
    # 從 LLM 輸出提取結構化更新
    updates = parse_structured_output(llm_output)
    return {**state, **updates}
```

**優點：** context 大小完全穩定；資訊密度高  
**缺點：** 需要精心設計 state schema；可能丟失對話的自然流暢感

**適用場景：** Task-oriented Agent、有明確工作流程的業務 Agent

---

## 五、Lost-in-the-Middle 的工程應對

### 什麼是 Lost-in-the-Middle

研究發現，當 context 很長時，LLM 對「放在中間的資訊」注意力顯著下降。

```
[開頭資訊] ← LLM 注意力強
[中間資訊] ← LLM 容易忽略 ⚠️
[結尾資訊] ← LLM 注意力強
```

### 工程應對策略

**1. 重要資訊放頭尾**

```python
def build_prompt(system_instructions, retrieved_docs, user_query):
    # ❌ 錯誤：重要指令被淹沒在中間
    # return system_instructions + "\n" + lots_of_docs + "\n" + user_query
    
    # ✅ 正確：關鍵指令放開頭和結尾
    return f"""
    {system_instructions}
    
    === 參考資料 ===
    {retrieved_docs}
    === 資料結束 ===
    
    記住上方的指示。現在請回答：{user_query}
    """
```

**2. 結構化標記**

```python
# 用清晰的標記幫助 LLM 定位重要資訊
prompt = """
<system_instructions>
你是一個財務分析 Agent。回答時必須：
1. 只引用提供的文件，不推測
2. 用繁體中文回答
3. 數字要加上單位
</system_instructions>

<documents>
[文件內容...]
</documents>

<user_query>
{query}
</user_query>
"""
```

---

## 六、Token 計數與監控

面試官考點：

> *「你怎麼確保你的 Agent 不會意外超過 context limit？」*

```python
import tiktoken  # OpenAI tokenizer
# 或使用 Gemini 的 count_tokens API

class ContextMonitor:
    def __init__(self, model: str, max_tokens: int, warning_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.warning_threshold = warning_threshold
        self.encoder = tiktoken.encoding_for_model(model)
    
    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))
    
    def check_context(self, context: str) -> dict:
        token_count = self.count_tokens(context)
        usage_ratio = token_count / self.max_tokens
        
        return {
            "token_count": token_count,
            "max_tokens": self.max_tokens,
            "usage_ratio": usage_ratio,
            "status": "warning" if usage_ratio > self.warning_threshold else "ok",
            "should_compress": usage_ratio > self.warning_threshold
        }
    
    def trim_to_fit(self, messages: list[dict], reserve_for_output: int = 2000) -> list[dict]:
        available = self.max_tokens - reserve_for_output
        result = []
        total = 0
        
        # 從最新的訊息往回加，確保保留最近的對話
        for msg in reversed(messages):
            tokens = self.count_tokens(msg["content"])
            if total + tokens > available:
                break
            result.insert(0, msg)
            total += tokens
        
        return result
```

---

## 七、面試答題框架

被問到 context management 類題目，用這個框架回答：

**SCOPE 框架：**

| 字母 | 意義 | 你要說的 |
|------|------|---------|
| **S** | Size | 這個場景的 context 會長多快？估算一下 |
| **C** | Cost | context 長了對成本和延遲有什麼影響 |
| **O** | Options | 你有哪些策略（sliding window / summary / retrieval / state） |
| **P** | Pick | 你選哪個？為什麼（trade-off） |
| **E** | Edge Cases | 什麼情況下你的策略會失效？怎麼處理 |

---

### 範例完整回答

面試官：「你有一個客服 Agent，用戶一個 case 可能有 100 輪對話。你怎麼設計 context management？」

> *「好，讓我先估算規模。每輪平均 300 tokens，100 輪就是 30K tokens，加上 system prompt 和工具呼叫的 context，可能到 50K。Gemini Flash 雖然有 1M window，但 50K token 的每次推理費用和延遲都是有感的。*
>
> *我會用 Summary Buffer + Structured State 的混合策略：*
> *1. 保留最近 10 輪完整對話（約 3K tokens）*
> *2. 把早期對話壓縮成「case summary」儲存（約 500 tokens），包含：問題描述、已嘗試解法、用戶情緒*
> *3. 同時維護一個 structured state 記錄關鍵欄位：product_id、error_code、resolution_status*
>
> *失效場景：如果壓縮時丟掉了關鍵的錯誤碼，後面的 Agent 可能給錯誤解答。所以壓縮 prompt 要特別標記「以下資訊必須保留」的欄位。*
>
> *我還會加 token 監控，當 context 超過 80% 時自動觸發壓縮，確保不會意外超限。」*

---

## 八、快速複習卡

```
Context Management 四策略：
├── Sliding Window    → 簡單，適合短期任務
├── Summary Buffer    → 保語意，適合長對話
├── Retrieval Memory  → 最彈性，需向量 DB
└── Structured State  → 最穩定，需設計 schema

Lost-in-the-Middle：重要資訊放頭尾，用結構化標記

Token 監控：超過 80% threshold 就壓縮，留 reserve 給 output

SCOPE 框架：Size → Cost → Options → Pick → Edge Cases
```

---

**系列導覽：**  
← [（九）LLM 核心知識](../fde-interview-guide-part9-llm-core-zh/)  
→ [（十一）RKK 實戰：Agent 線上除錯與故障排除](../fde-interview-guide-part11-agent-debugging-zh/)
