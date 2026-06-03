---
title: "FDE 面試準備指南（十五）：RKK 實戰——AI Agent 規模化與 Cache 策略"
date: 2026-06-03T14:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 AI Agent 系統的規模化挑戰與 Cache 策略：Semantic Cache、KV Cache、多層快取架構、水平擴展設計，以及如何在 RKK 面試中展現系統設計思維"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Scale", "Cache", "KV Cache", "Semantic Cache", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> 把 Agent 從 1 個用戶擴展到 10 萬個用戶，  
> 最先崩潰的不是 LLM，而是 cache 沒設計好。  
> 規模化題型考的是系統思維：你知道瓶頸在哪，你知道 trade-off 是什麼。

---

## 一、為什麼 Scale 是 RKK 必考題

JD 明確提到：**「Knowledge of LLM-native metrics and techniques for optimizing state management and granular tracing.」**

「Optimizing state management」= 你知道怎麼讓 Agent 系統在高負載下還能工作。

面試官問法：

> *「你現在有一個 RAG Agent，每天有 10 萬個請求。你的系統設計會怎麼調整？」*

---

## 二、AI Agent 系統的三個規模化挑戰

```
挑戰 1：LLM 推理延遲高（每次請求 2-10 秒）
   → 無法靠多線程「魔法解決」，需要 cache 和批次處理

挑戰 2：成本與規模正相關
   → 10 萬請求 × $0.01/請求 = $1000/天
   → 必須找辦法減少不必要的 LLM 呼叫

挑戰 3：Stateful 系統的水平擴展
   → Agent 有 session state、memory
   → 傳統 stateless 的水平擴展方式不直接適用
```

---

## 三、Cache 策略一：Semantic Cache（語意快取）

### 什麼是 Semantic Cache

傳統快取是精確匹配（exact match）：

```python
# 傳統 cache：必須完全一樣才命中
cache = {"Q4 銷售數字是多少？": "Q4 銷售額為 $4.2M"}
query = "Q4 的銷售業績？"  # → cache miss（文字不同）
```

**Semantic Cache** 用向量相似度找「語意相似的問題」：

```python
class SemanticCache:
    def __init__(self, vector_store, embedder, similarity_threshold: float = 0.92):
        self.vector_store = vector_store
        self.embedder = embedder
        self.threshold = similarity_threshold
    
    def get(self, query: str) -> str | None:
        query_embedding = self.embedder.embed(query)
        
        # 找最相似的快取 entry
        results = self.vector_store.query(
            vector=query_embedding,
            top_k=1,
            filter={"type": "cache"}
        )
        
        if not results:
            return None
        
        best_match = results[0]
        
        if best_match.score >= self.threshold:
            # Cache hit：語意相似度高於閾值
            self._log_cache_hit(query, best_match.metadata["original_query"])
            return best_match.metadata["response"]
        
        return None  # Cache miss
    
    def set(self, query: str, response: str, ttl_seconds: int = 3600):
        embedding = self.embedder.embed(query)
        
        self.vector_store.upsert(
            id=generate_id(),
            vector=embedding,
            metadata={
                "type": "cache",
                "original_query": query,
                "response": response,
                "cached_at": datetime.now().isoformat(),
                "ttl": ttl_seconds
            }
        )
    
    def get_stats(self) -> dict:
        return {
            "hit_rate": self._hit_count / max(self._total_requests, 1),
            "estimated_cost_savings_usd": self._hit_count * 0.01  # 每次 LLM 呼叫省 $0.01
        }
```

### Semantic Cache 的相似度閾值選擇

```
0.95+ → 非常保守，只有幾乎一模一樣的問題才命中，hit rate 低但準確
0.90  → 平衡點，多數情況下效果好（推薦起點）
0.85  → 積極快取，hit rate 高，但可能回傳語意相近但答案不同的回應
< 0.80 → 太激進，容易出錯
```

---

## 四、Cache 策略二：KV Cache（LLM 層快取）

### 什麼是 KV Cache

LLM 的 attention 機制在處理每個 token 時，都要計算「這個 token 和所有之前 token 的關聯」。KV Cache 把這個計算結果（Key-Value matrix）快取起來，重複的 prefix 不需要重新計算。

```
沒有 KV Cache：
每次請求 → 重新計算整個 prompt 的 attention → 慢

有 KV Cache：
System prompt（固定的）→ 計算一次，快取
每次請求 → 只計算新增的部分 → 快 3-5x
```

### Google Gemini / Vertex AI 的 Context Cache

```python
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Content

# Vertex AI 的 Context Cache（Gemini 1.5 Pro）
# 把固定的 system prompt 和大型知識庫快取起來

# 建立 cache（通常需要 32K+ tokens 才划算）
cached_content = vertexai.preview.caching.CachedContent.create(
    model_name="gemini-1.5-pro-001",
    system_instruction=long_system_prompt,       # 幾千 token 的系統指令
    contents=[large_knowledge_base_content],     # 幾萬 token 的知識庫
    ttl=datetime.timedelta(hours=1)              # 快取 1 小時
)

# 之後的請求使用快取的 content
model = GenerativeModel.from_cached_content(cached_content)

# 成本節省：快取的 token 計費約為正常的 1/4
# 若 system prompt = 50K tokens，每次請求省：
# 50K * ($1.25/1M) * (1 - 0.25) = $0.047 per request
```

### OpenAI / Anthropic 的 Prompt Cache

```python
# Anthropic Claude 的 cache_control
response = anthropic.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": large_knowledge_base,  # 大型知識庫
            "cache_control": {"type": "ephemeral"}  # 標記為可快取
        }
    ],
    messages=[{"role": "user", "content": user_query}]
)

# 首次請求：cache_creation_input_tokens（貴）
# 後續請求：cache_read_input_tokens（便宜 ~90%）
print(response.usage)
# Usage(cache_creation_input_tokens=10000, cache_read_input_tokens=10000, ...)
```

---

## 五、多層快取架構

企業級系統應該設計多層快取：

```
請求進來
    │
    ▼
[L1: Application Cache - Redis]
├── Session state（用戶當前對話狀態）
├── Hot queries（最近 N 分鐘的熱門請求）
└── TTL: 5-15 分鐘
    │ miss
    ▼
[L2: Semantic Cache - Vector DB]
├── 語意相似的歷史回答
├── 按用戶分組（個人化快取）
└── TTL: 1-24 小時（依問題類型）
    │ miss
    ▼
[L3: KV Cache - LLM 層]
├── System prompt / Knowledge base prefix
└── 由 LLM provider 管理
    │ miss（真正的 LLM 推理）
    ▼
[LLM 推理]
    │
    ▼
結果回寫到 L2、L1
```

**實作：**

```python
class MultiLayerCache:
    def __init__(self, redis_client, semantic_cache, llm_client):
        self.l1 = redis_client          # 快速，小容量
        self.l2 = semantic_cache        # 語意匹配，中容量
        self.llm = llm_client           # 最慢，最準確
        self.metrics = {"l1_hits": 0, "l2_hits": 0, "llm_calls": 0}
    
    async def get_response(self, query: str, user_id: str) -> str:
        # L1: Redis exact match
        cache_key = f"q:{hash(query)}:u:{user_id}"
        l1_result = await self.l1.get(cache_key)
        if l1_result:
            self.metrics["l1_hits"] += 1
            return l1_result.decode()
        
        # L2: Semantic cache
        l2_result = self.l2.get(query)
        if l2_result:
            self.metrics["l2_hits"] += 1
            # Backfill L1
            await self.l1.setex(cache_key, 300, l2_result)
            return l2_result
        
        # L3: Actual LLM call（KV cache 在 LLM provider 層自動處理）
        self.metrics["llm_calls"] += 1
        response = await self.llm.generate(query)
        
        # Write to L1 and L2
        await self.l1.setex(cache_key, 300, response)
        self.l2.set(query, response)
        
        return response
    
    def get_cache_efficiency(self) -> dict:
        total = sum(self.metrics.values())
        return {
            "l1_hit_rate": self.metrics["l1_hits"] / max(total, 1),
            "l2_hit_rate": self.metrics["l2_hits"] / max(total, 1),
            "llm_call_rate": self.metrics["llm_calls"] / max(total, 1),
            "cost_reduction_estimate": 1 - self.metrics["llm_calls"] / max(total, 1)
        }
```

---

## 六、水平擴展：Stateful Agent 的挑戰

傳統 Web 服務是 stateless，可以輕鬆水平擴展：

```
請求 → 任意 instance 都能處理
```

Agent 是 stateful，有 session state 和 memory：

```
問題：
用戶在 Instance A 開始了對話 → 有 context
下一個請求可能到 Instance B → B 沒有 context
```

**解法：外部化狀態**

```python
class StatelessAgentInstance:
    """
    Agent instance 本身不儲存任何狀態
    所有狀態都存在外部的 Redis / Database
    """
    
    def __init__(self, redis_client, memory_store):
        self.redis = redis_client
        self.memory_store = memory_store
    
    async def process(self, session_id: str, user_message: str) -> str:
        # 從 Redis 載入 session state
        session = await self.redis.get_session(session_id)
        
        # 從 Memory Store 載入用戶記憶
        user_profile = self.memory_store.get_profile(session.user_id)
        relevant_memories = self.memory_store.recall(
            user_id=session.user_id,
            query=user_message
        )
        
        # 組建 context
        context = self._build_context(session, user_profile, relevant_memories)
        
        # 執行 Agent
        response = await self._run_agent(context, user_message)
        
        # 更新 session state 並存回 Redis
        session.add_turn(user_message, response)
        await self.redis.set_session(session_id, session)
        
        return response

# 水平擴展：任意 instance 都能處理任意 session
# 因為狀態全在 Redis，不在 instance 裡
```

---

## 七、關鍵設計決策：什麼可以快取，什麼不行

| 內容類型 | 可快取？ | 原因 | TTL 建議 |
|---------|---------|------|---------|
| FAQ 類問題 | ✅ 強烈建議 | 重複率高，答案穩定 | 24 小時 |
| 產品規格查詢 | ✅ | 內容不常變 | 6 小時 |
| 個人化回答 | ❌ | 因人而異，不應共享 | - |
| 即時數據查詢（股價/庫存） | ❌ | 資料時效性要求高 | - |
| 多步驟任務中間結果 | ⚠️ 謹慎 | 依賴前後步驟，需確認 context 相同 | 15 分鐘 |

---

## 八、面試答題框架

被問到規模化題型，用這個框架：

**CAPE 框架：**

| 字母 | 意義 | 你要說的 |
|------|------|---------|
| **C** | Capacity | 估算當前規模：請求量、token 量、成本 |
| **A** | Architecture | 你的多層快取和擴展架構 |
| **P** | Performance | 各層的 hit rate 和預期效益 |
| **E** | Edge Cases | 快取失效（cache invalidation）、冷啟動問題 |

### 範例完整回答

面試官：「10 萬 DAU 的 RAG Agent，你怎麼設計？」

> *「先估算規模。10 萬 DAU，每人平均 3 次查詢，30 萬請求/天。Gemini Flash 每次約 $0.002，每天 $600，月費 $18,000。這個成本驅動了快取的必要性。*
>
> *我的架構是三層快取加外部化狀態：*
>
> *L1：Redis 做 hot query cache，針對最近 15 分鐘的熱門查詢做 exact match，預估 hit rate 約 15%。*
>
> *L2：Semantic Cache 用向量資料庫，針對語意相似的問題複用答案，相似度閾值 0.92，FAQ 類場景 hit rate 可達 40-50%。*
>
> *L3：Vertex AI Context Cache，把固定的 system prompt 和知識庫（通常 50K+ tokens）在 LLM 層快取，每次請求的 input token 成本降低約 75%。*
>
> *整合下來，實際打到 LLM 的請求可能只剩 35%，月費從 $18K 降到約 $6-8K。*
>
> *Agent instance 本身無狀態，所有 session state 外部化到 Redis，隨意水平擴展。*
>
> *邊界情況：快取失效要有機制（例如知識庫更新時清除相關 semantic cache）；新用戶和冷門查詢會全走 LLM，這是預期行為。」*

---

## 九、快速複習卡

```
三種 Cache 策略：
├── Semantic Cache   → 向量相似度，複用語意相近的答案
├── KV Cache         → LLM 推理層，prefix 共享
└── Application Cache → Redis，session state + hot queries

水平擴展關鍵：
└── 外部化狀態（Redis/DB），Agent instance 無狀態

CAPE 答題框架：
Capacity（估規模）→ Architecture（多層 cache）→ 
Performance（預估效益）→ Edge Cases（失效/冷啟動）

成本優化三板斧：
1. Semantic Cache 減少重複 LLM 呼叫
2. KV Cache 降低 prefix token 成本（省 75%）
3. 最小化 output token（精確 prompt 設計）
```

---

**系列導覽：**  
← [（十四）RKK 實戰：AI Agent Memory 架構設計](../fde-interview-guide-part14-memory-architecture-zh/)  
← [系列首篇：（一）RAG 完全攻略](../fde-interview-guide-part1-rag-zh/)
