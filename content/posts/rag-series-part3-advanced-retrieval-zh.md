---
title: "RAG 完全指南（三）：進階檢索技術——混合搜尋、HyDE、Multi-Query、Reranker"
date: 2026-05-18T09:00:00+08:00
draft: false
description: "Naive RAG 的搜尋精準度不夠？本篇深入四大進階檢索技術：BM25 混合搜尋、假設性文件嵌入（HyDE）、多查詢檢索（Multi-Query）、以及 Cross-Encoder Reranker，每個都有核心原理、程式碼與最佳使用場景。"
categories: ["AI", "Engineering", "all"]
tags: ["RAG", "Hybrid Search", "HyDE", "Reranker", "BM25", "LangChain", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "30 min"
---

## 前言

Naive RAG 的核心問題：**搜尋品質決定了答案品質**。

一個常見的現象是，明明知識庫裡有答案，但因為使用者的問題措辭跟文件不同，向量搜尋就找不到。或者，找到的 Top-5 結果裡，真正相關的其實排在第 4 位，LLM 因此被無關資訊干擾。

這篇介紹四個能顯著提升搜尋品質的技術。

---

## 技術 1：混合搜尋（Hybrid Search）

### 核心問題

純向量搜尋（Semantic Search）擅長找「語意相近」的內容，但對**精確術語、專有名詞、縮寫**效果差。

```
問題：「GPT-4o 的 context window 是多少？」

純向量搜尋找到：「大型語言模型通常有輸入長度限制...」（語意相近但沒答案）
BM25 關鍵字搜尋找到：「GPT-4o 支援 128K token 的 context window」（精確命中）
```

**混合搜尋 = 語意搜尋 + 關鍵字搜尋**，兩者結果用 RRF 或加權融合。

### BM25 簡介

BM25 是 TF-IDF 的改進版，計算關鍵字與文件的相關度：

```
Score(D, Q) = Σ IDF(qi) * (tf(qi, D) * (k1 + 1)) / (tf(qi, D) + k1 * (1 - b + b * |D| / avgdl))
```

不需要理解公式，只需知道：BM25 對精確詞彙匹配非常靈敏。

### Reciprocal Rank Fusion（RRF）

RRF 是融合兩個排序結果的標準方法：

```python
def rrf_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """
    rankings: 每個搜尋方法的文件 ID 排序列表
    k: 平滑常數（通常用 60）
    回傳：每個文件 ID 的融合分數
    """
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
```

### 完整混合搜尋實作

```python
from rank_bm25 import BM25Okapi
import numpy as np
import openai
import jieba  # 中文分詞

client = openai.OpenAI(api_key="your-api-key")


class HybridRetriever:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks

        # 建立 BM25 index（中文需要先分詞）
        tokenized = [list(jieba.cut(c)) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

        # 建立向量 index
        self.embeddings = self._embed_all(chunks)

    def _embed_all(self, texts: list[str]) -> np.ndarray:
        response = client.embeddings.create(
            input=texts, model="text-embedding-3-small"
        )
        return np.array([r.embedding for r in response.data])

    def _embed(self, text: str) -> np.ndarray:
        response = client.embeddings.create(
            input=text, model="text-embedding-3-small"
        )
        return np.array(response.data[0].embedding)

    def semantic_search(self, query: str, top_k: int = 10) -> list[int]:
        """語意搜尋，回傳文件索引排序"""
        q_emb = self._embed(query)
        # 餘弦相似度
        sims = self.embeddings @ q_emb / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb) + 1e-9
        )
        return np.argsort(-sims)[:top_k].tolist()

    def keyword_search(self, query: str, top_k: int = 10) -> list[int]:
        """BM25 關鍵字搜尋，回傳文件索引排序"""
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens)
        return np.argsort(-scores)[:top_k].tolist()

    def hybrid_search(
        self, query: str, top_k: int = 5, alpha: float = 0.5
    ) -> list[str]:
        """
        混合搜尋
        alpha=0.0: 純關鍵字, alpha=1.0: 純語意, alpha=0.5: 各半
        """
        sem_ranking = self.semantic_search(query, top_k=20)
        kw_ranking  = self.keyword_search(query,  top_k=20)

        # RRF 融合
        k = 60
        scores: dict[int, float] = {}
        for rank, idx in enumerate(sem_ranking, 1):
            scores[idx] = scores.get(idx, 0) + alpha * (1 / (k + rank))
        for rank, idx in enumerate(kw_ranking, 1):
            scores[idx] = scores.get(idx, 0) + (1 - alpha) * (1 / (k + rank))

        top_indices = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return [self.chunks[i] for i in top_indices]


# 使用範例
chunks = [
    "GPT-4o 支援 128K token 的 context window，是目前 OpenAI 最強的多模態模型。",
    "大型語言模型通常有輸入長度的限制，這個限制被稱為 context window。",
    "Python 在機器學習領域被廣泛使用，常見框架有 TensorFlow 和 PyTorch。",
]

retriever = HybridRetriever(chunks)
results = retriever.hybrid_search("GPT-4o context window 大小", top_k=2)
for r in results:
    print(r)
```

**優點**：結合兩種搜尋的優點，對術語和語意都能命中  
**缺點**：需要維護兩個索引；alpha 值需要根據資料集調整  
**最佳使用場景**：技術文件、法律/醫療知識庫、有大量專有名詞的領域

---

## 技術 2：假設性文件嵌入（HyDE）

### 核心問題

使用者的問題和文件的語言風格不同：

- **問題**：「如何減少 API 延遲？」（問句）
- **文件**：「使用連線池可以將 API 延遲降低 40%」（陳述句）

問句和陳述句的向量距離比陳述句之間的距離更大，導致搜尋效果差。

### HyDE 的解法

讓 LLM 先根據問題**生成一個假設性的答案文件**，再用這個假設答案去搜尋。假設答案的語言風格跟知識庫文件更接近，搜尋效果更好。

```
問題（問句）→ LLM → 假設答案（陳述句）→ 向量化 → 搜尋 → 真實文件
```

即使假設答案的事實不正確也沒關係，它的**語言模式**已經足夠引導搜尋。

### 完整實作

```python
import openai

client = openai.OpenAI(api_key="your-api-key")


def generate_hypothetical_document(question: str) -> str:
    """讓 LLM 生成一個假設性的回答文件"""
    prompt = f"""請根據以下問題，寫一段簡短的技術說明（3-5 句話），
就像這是從技術文件中摘錄的一段內容。
不需要完全正確，重點是語言風格要像技術文件。

問題：{question}

技術文件段落："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,  # 稍高一點，讓生成的文件更多樣
        max_tokens=200,
    )
    return response.choices[0].message.content


def get_embedding(text: str) -> list[float]:
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding


class HyDERetriever:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.embeddings = [get_embedding(c) for c in chunks]

    def retrieve(self, question: str, top_k: int = 3) -> list[str]:
        # Step 1: 生成假設性文件
        hypothetical_doc = generate_hypothetical_document(question)
        print(f"🤔 假設性文件：{hypothetical_doc[:100]}...")

        # Step 2: 用假設性文件的向量做搜尋（而非原始問題）
        hypo_embedding = get_embedding(hypothetical_doc)

        import numpy as np
        emb_matrix = np.array(self.embeddings)
        q_emb = np.array(hypo_embedding)

        sims = emb_matrix @ q_emb / (
            np.linalg.norm(emb_matrix, axis=1) * np.linalg.norm(q_emb) + 1e-9
        )
        top_indices = np.argsort(-sims)[:top_k]
        return [self.chunks[i] for i in top_indices]


# 使用範例
chunks = [
    "使用連線池（Connection Pooling）可以將 API 的平均延遲降低 30-50%，因為避免了反覆建立 TCP 連線的開銷。",
    "非同步 I/O（asyncio）可以讓單一 Python 程序同時處理數千個並發請求，大幅提升吞吐量。",
    "CDN（內容分發網路）可以將靜態資源快取到離使用者最近的節點，減少網路傳輸延遲。",
    "資料庫查詢優化：使用索引、避免 N+1 問題、適當的快取策略，是降低後端延遲的關鍵。",
]

retriever = HyDERetriever(chunks)
results = retriever.retrieve("如何減少 API 的回應時間？")
for r in results:
    print(f"  📄 {r}")
```

**優點**：有效彌補問句與文件語言風格的差異；實作簡單  
**缺點**：多一次 LLM 呼叫（延遲 + 成本）；假設性文件可能引入偏見  
**最佳使用場景**：使用者問題措辭跟文件風格差異大的場景，例如：口語化問題 vs 正式技術文件

---

## 技術 3：多查詢檢索（Multi-Query Retrieval）

### 核心問題

一個問題換一種說法，搜尋結果可能完全不同：

```
原始問題：「Python 比 Java 快嗎？」
→ 搜尋結果：[Python 效能評測, Java 效能測試]

換一種說法：「Java 的執行速度是否優於 Python？」
→ 搜尋結果：[JVM 效能優化, 動態語言速度分析]  ← 可能更相關！
```

單一查詢的搜尋結果受措辭影響很大，會遺漏相關文件。

### 解法：自動生成多個查詢版本

```python
import openai
from typing import Any

client = openai.OpenAI(api_key="your-api-key")


def generate_query_variations(original_query: str, n: int = 3) -> list[str]:
    """用 LLM 生成同一個問題的多種不同表達方式"""
    prompt = f"""你是一個搜尋查詢優化助手。
請將以下問題改寫成 {n} 個不同的表達方式，
角度可以不同（例如：換用不同詞彙、從反面問、更具體、更抽象）。
每個改寫版本單獨一行，不要加編號或額外解釋。

原始問題：{original_query}

改寫版本："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    variations = response.choices[0].message.content.strip().split("\n")
    return [v.strip() for v in variations if v.strip()][:n]


def get_embedding(text: str) -> list[float]:
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding


class MultiQueryRetriever:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        import numpy as np
        self.embeddings = np.array([get_embedding(c) for c in chunks])

    def retrieve(self, question: str, top_k: int = 3) -> list[str]:
        import numpy as np

        # 生成多個查詢版本
        variations = generate_query_variations(question, n=3)
        all_queries = [question] + variations

        print("🔍 查詢版本：")
        for q in all_queries:
            print(f"  - {q}")

        # 對每個查詢版本做搜尋，收集所有結果
        seen_indices = set()
        candidate_scores: dict[int, float] = {}

        for query in all_queries:
            q_emb = np.array(get_embedding(query))
            sims = self.embeddings @ q_emb / (
                np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb) + 1e-9
            )
            # 取每個查詢的 top_k 結果
            top_indices = np.argsort(-sims)[:top_k]
            for rank, idx in enumerate(top_indices):
                # 用 RRF 融合多個查詢的排名
                candidate_scores[int(idx)] = (
                    candidate_scores.get(int(idx), 0) + 1 / (60 + rank + 1)
                )

        # 按融合分數排序，去重後取 top_k
        top_indices = sorted(candidate_scores, key=candidate_scores.get, reverse=True)
        return [self.chunks[i] for i in top_indices[:top_k]]


# 使用範例
chunks = [
    "Python 是一種直譯語言，執行速度比 Java 慢約 5-10 倍，但開發效率更高。",
    "Java 透過 JIT 編譯器將程式碼編譯成機器碼，執行效能接近 C++。",
    "對於 CPU 密集型任務，Java 的效能通常優於 Python；但 Python 的 NumPy 等函式庫利用 C 底層可以媲美 Java。",
    "Python 的 GIL（全域解釋鎖）限制了真正的多執行緒並行，而 Java 沒有這個限制。",
]

retriever = MultiQueryRetriever(chunks)
results = retriever.retrieve("Python 和 Java 哪個比較快？")
print("\n📑 檢索結果：")
for r in results:
    print(f"  {r}")
```

**優點**：覆蓋更多相關文件，減少因措辭導致的遺漏；實作相對簡單  
**缺點**：多次 Embedding 計算（成本增加 N 倍）；可能引入不相關結果  
**最佳使用場景**：使用者問題措辭不穩定、知識庫術語多樣的場景

---

## 技術 4：Cross-Encoder Reranker

### 核心問題

向量搜尋的 Top-K 結果，排序不一定最優。向量搜尋用**雙塔模型（Bi-Encoder）**——問題和文件分別向量化，再計算距離——速度快但精準度有限。

**Reranker（Cross-Encoder）**：把問題和每個候選文件一起送進模型，讓模型直接判斷這對「問題+文件」的相關程度。精準度更高，但速度慢（適合在取得候選後做二次排序）。

```
向量搜尋（Bi-Encoder）: 問題向量 vs 文件向量 → 距離計算
Cross-Encoder Reranker: [問題 + 文件] → 相關分數（0-1）
```

### 完整實作

```python
# 安裝：pip install sentence-transformers
from sentence_transformers import CrossEncoder
import openai
import numpy as np

client = openai.OpenAI(api_key="your-api-key")

# 載入 Cross-Encoder 模型（本地，不需要 API）
# 中文推薦：cross-encoder/ms-marco-MiniLM-L-6-v2（英文為主）
# 或 BAAI/bge-reranker-base（中英文）
reranker = CrossEncoder("BAAI/bge-reranker-base")


def get_embedding(text: str) -> list[float]:
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding


class RerankRetriever:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.embeddings = np.array([get_embedding(c) for c in chunks])

    def retrieve(
        self, query: str, initial_top_k: int = 20, final_top_k: int = 5
    ) -> list[dict]:
        """
        兩階段檢索：
        1. 向量搜尋取 top 20（召回）
        2. Cross-Encoder rerank 取 top 5（精排）
        """
        # Stage 1: 向量搜尋（粗召回）
        q_emb = np.array(get_embedding(query))
        sims = self.embeddings @ q_emb / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb) + 1e-9
        )
        initial_indices = np.argsort(-sims)[:initial_top_k].tolist()
        candidates = [(i, self.chunks[i]) for i in initial_indices]

        # Stage 2: Cross-Encoder Rerank（精排）
        pairs = [[query, chunk] for _, chunk in candidates]
        scores = reranker.predict(pairs)  # 每對的相關分數

        # 按 reranker 分數重新排序
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )[:final_top_k]

        return [
            {"chunk": chunk, "rerank_score": float(score)}
            for (idx, chunk), score in ranked
        ]


# 使用範例
chunks = [
    "Python 的 async/await 語法讓非同步程式設計變得更直覺。",
    "要減少 API 延遲，可以使用 asyncio 搭配 aiohttp 進行並發請求。",
    "asyncio 是 Python 的標準非同步 I/O 框架，適合 I/O 密集型工作。",
    "Python GIL 在多執行緒場景下限制了 CPU 密集型任務的並行。",
    "使用 Redis 作為快取層可以顯著降低資料庫查詢次數，減少延遲。",
    "CDN 加速靜態資源的分發，降低使用者的載入時間。",
    "連線池（Connection Pool）避免反覆建立 TCP 連線的開銷。",
]

retriever = RerankRetriever(chunks)
results = retriever.retrieve(
    "如何用 Python 優化 API 的回應速度？",
    initial_top_k=6,
    final_top_k=3,
)

print("📊 Rerank 後的結果：")
for i, r in enumerate(results, 1):
    print(f"  {i}. [分數: {r['rerank_score']:.4f}] {r['chunk']}")
```

**優點**：排序精準度顯著優於純向量搜尋；可以有效過濾掉「語意相近但不相關」的結果  
**缺點**：推理較慢（每個候選都要跑一次 model）；不適合作為第一層搜尋（要先用向量搜縮小候選集）  
**最佳使用場景**：高精準度要求的問答系統；候選集大（20-100 個）但需要精確 Top-5 的場景

---

## 四種技術的組合策略

實際生產系統通常**組合使用**多種技術：

```
使用者問題
    │
    ├── [Multi-Query] 生成 3 個查詢版本
    │
    ├── 每個版本做 [Hybrid Search]（語意 + BM25）
    │   → 合併去重，取 Top-30 候選
    │
    ├── [Reranker] 對 Top-30 精排
    │   → 取 Top-5 最相關 chunks
    │
    └── 送給 LLM 生成答案
```

對特定問題類型，加入 HyDE：

```
使用者問題（措辭非正式/口語化）
    │
    ├── [HyDE] 生成假設性文件
    │
    └── 用假設性文件向量做 [Hybrid Search] + [Reranker]
```

---

## 小結

| 技術 | 解決的問題 | 延遲增加 | 成本增加 |
|------|-----------|---------|---------|
| Hybrid Search | 術語/關鍵字精確匹配 | 低 | 低 |
| HyDE | 問句 vs 文件語言風格差異 | 中（一次 LLM 呼叫） | 中 |
| Multi-Query | 措辭不穩定、遺漏相關文件 | 中（N 次 Embedding） | 中 |
| Reranker | 召回後的排序精準度 | 中高（本地模型推理） | 低（用本地模型） |

下一篇，我們進入**查詢轉換**與**Context 壓縮**——當問題本身就很複雜，需要拆解或轉換，以及 context 太多時如何過濾噪音。

---

**系列導覽**

- [第一篇](/posts/rag-series-part1-foundations-zh/)：基礎概念與第一個 RAG 系統
- [第二篇](/posts/rag-series-part2-chunking-vectordb-zh/)：Chunking 策略與向量資料庫選型
- **第三篇（本篇）**：進階檢索技術（混合搜尋、HyDE、Multi-Query、Reranker）
- [第四篇](/posts/rag-series-part4-optimization-zh/)：查詢優化與 Context 壓縮
- [第五篇](/posts/rag-series-part5-production-zh/)：生產級 RAG 評估與 Agentic RAG
