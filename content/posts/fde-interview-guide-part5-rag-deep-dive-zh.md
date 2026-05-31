---
title: "FDE 面試準備指南（五）：RAG 深度技術——Chunking、Embedding、向量資料庫與混合搜尋"
date: 2026-05-31T09:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 RAG 的技術細節：Chunking 策略選擇、Embedding 模型挑選、向量資料庫設計、混合搜尋與 Reranking，以及 Context Window 爆炸的處理方式"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "RAG", "Chunking", "Embedding", "Vector DB", "Hybrid Search", "Reranking", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> 第一篇講了 RAG 是什麼。  
> 這篇講你在面試中被追問到第三層時，你能不能答上來。  
> 面試官最喜歡的問法是：「那你為什麼這樣設計？有沒有考慮過別的方案？」

---

## Chunking 策略：不是切越小越好

Chunking 是 RAG 最常被輕描淡寫的環節，但它直接決定你的檢索品質。

面試官問法通常是：

> *「你的 RAG 系統 Chunking 怎麼設計的？為什麼？」*

---

### Fixed-Size Chunking（固定大小切分）

最簡單的做法：每 N 個 token 切一塊，加上一點 overlap。

```
chunk_size = 512
chunk_overlap = 50
```

**優點：**
- 實作簡單
- 預測性高，每塊大小一致
- Embedding 成本可控

**缺點：**
- 完全不管語意邊界
- 一個句子可能被切成兩半
- 段落邏輯可能斷裂

**適用場景：**
- 文件格式高度結構化（例如：財報、合約）
- 快速原型，先跑起來再優化

---

### Semantic Chunking（語意切分）

根據語意相似度決定切分點。計算相鄰句子的 embedding 距離，距離突然變大的地方就是自然的段落邊界。

**優點：**
- 保留語意完整性
- 每塊的內聚度更高，向量品質更好
- 特別適合長文、報告、文章

**缺點：**
- 計算成本更高（每個句子都要先 embed）
- Chunk 大小不固定，向量 DB 設計要考慮
- 實作複雜度較高

**工具：** LangChain 的 `SemanticChunker`、`llmsherpa`

---

### 其他進階策略

| 策略 | 說明 | 適用 |
|------|------|------|
| **Recursive Character Splitter** | 先試 `\n\n`，再試 `\n`，再試空格，依序退退 | 一般文本的預設選擇 |
| **Markdown / HTML Splitter** | 依據標題、段落結構切 | Markdown 文件、網頁 |
| **Sentence-Window Chunking** | Embed 單句，但 retrieve 時帶回前後 N 句 | 需要精準定位又要完整上下文 |
| **Parent-Child Chunking** | 小塊做搜尋，大塊送進 context | 兼顧精準與完整 |

---

### 面試怎麼答

被問到 Chunking，不要只說「我用 512 token 切」。  
標準回答結構：

1. **我的資料特性是什麼**（長文、短條目、有無結構）
2. **我選了什麼策略，為什麼**
3. **我怎麼驗證它有效**（用什麼 metric 衡量 chunk 品質）

---

## Embedding 模型選擇：不是只有 OpenAI

面試官問：

> *「你用哪個 Embedding 模型？為什麼不用別的？」*

這題考的是你有沒有實際評估過，還是只是跟著教學抄。

---

### 主流模型比較

| 模型 | 提供商 | 維度 | 特點 |
|------|--------|------|------|
| `text-embedding-004` | Google | 768 | Gemini 生態系首選，支援 task type |
| `text-embedding-3-large` | OpenAI | 3072 | 高維，效果強，成本高 |
| `text-embedding-3-small` | OpenAI | 1536 | 平衡選擇 |
| `BGE-M3` | BAAI | 1024 | 開源，支援多語言，中文很強 |
| `E5-mistral-7b` | Microsoft | 4096 | 開源裡效果最好之一 |
| `bge-large-zh` | BAAI | 1024 | 中文專用，效能極佳 |

---

### 選模型的考量維度

**1. 語言支援**  
你的資料是中文？英文？多語言？  
`text-embedding-004` 支援多語言但中文效果不如 BGE。  
中文為主 → 考慮 `bge-large-zh`。

**2. Task Type**  
Google `text-embedding-004` 支援 `task_type` 參數：
```python
# 語意搜尋的 query 端
embeddings.embed_query(text, task_type="RETRIEVAL_QUERY")

# 文件端
embeddings.embed_documents(texts, task_type="RETRIEVAL_DOCUMENT")
```
Query 和 Document 用不同 task type，效果通常更好。

**3. 維度 vs 成本**  
維度越高，表達能力越強，但儲存和計算成本也越高。  
Matryoshka Representation Learning（MRL）讓你可以截短維度但保留大部分效果。

**4. 評估方式**  
不要靠直覺選。用你自己的資料跑 MTEB 的子集，或用 retrieval recall@k 評估。

---

## 向量資料庫設計

面試官問：

> *「你的 Vector DB 怎麼設計的？為什麼選這個？」*

---

### 主流 Vector DB 比較

| DB | 特點 | 適合場景 |
|----|------|---------|
| **Pinecone** | 全託管，易用，貴 | 快速上線，不想維運 |
| **Weaviate** | 混合搜尋內建，開源 | 需要 hybrid search |
| **Qdrant** | Rust 寫的，快，開源 | 高效能，自架 |
| **ChromaDB** | 輕量，本地開發友好 | Prototype、本地測試 |
| **pgvector** | PostgreSQL 擴充 | 已有 PG 基礎設施 |
| **Vertex AI Vector Search** | GCP 託管，Gemini 整合 | GCP 生態系 |

---

### 設計時要考慮的問題

**Index 類型：**
- `HNSW`（Hierarchical Navigable Small World）：目前最常用，ANN 搜尋，快但近似
- `IVF`（Inverted File Index）：適合超大規模，精準度略低
- `Flat`：精準但慢，只適合小資料集

**Metadata Filtering：**  
向量搜尋 + metadata filter 是常見模式。  
例如：「只搜尋 2024 年後的文件」「只搜尋 dept=engineering 的資料」

設計時要注意：
- Filter 要在 ANN 之前還是之後？（pre-filter vs post-filter）
- Pre-filter 縮小搜尋空間，但如果 filter 太嚴可能導致 recall 下降

**Namespace / Collection 設計：**  
不同用戶的資料要隔離？  
→ 用 namespace（Pinecone）或不同 collection（Qdrant）  
→ 多租戶設計時注意資料洩漏風險

---

## 混合搜尋：BM25 + Vector

這是 FDE 面試的高頻題。  
問法：

> *「純向量搜尋有什麼問題？你怎麼解決？」*

---

### 純向量搜尋的盲點

向量搜尋是語意匹配，但它有一個致命弱點：**關鍵字完全不匹配時會找錯**。

例子：  
搜尋 `"GPT-4o release date"`  
→ 向量搜尋可能找到「語言模型發布歷史」這種語意相關但沒有 `GPT-4o` 關鍵字的文件  
→ 但你想要的是明確包含 `GPT-4o` 的文件

**BM25 就是傳統的 TF-IDF 關鍵字搜尋。** 它在關鍵字精確匹配上比向量搜尋強。

---

### Hybrid Search 架構

```
Query
  ├── BM25 搜尋 → Top-K (sparse results)
  └── Vector 搜尋 → Top-K (dense results)
        ↓
    融合排名 (RRF 或加權)
        ↓
    Reranker（可選）
        ↓
    Final Top-N → LLM Context
```

**Reciprocal Rank Fusion (RRF)：**  
最常用的融合方法。公式：

```
score(d) = Σ 1 / (k + rank_i(d))
```
其中 `k=60` 是常用預設值，`rank_i` 是文件在第 i 個搜尋結果中的排名。

**優點：** 不需要調整各搜尋分數的量綱，robust。

**工具：** Weaviate 內建 hybrid search、LangChain 的 `EnsembleRetriever`、Elasticsearch

---

## Reranking：搜尋的最後一道防線

Vector 搜尋找出候選，Reranker 決定哪個最相關。

**為什麼需要 Reranker？**  
ANN 向量搜尋的 Top-K 是近似結果，不保證 Top-1 是最相關的。  
Reranker 用更重的模型（Cross-Encoder）重新評估 query 和每個 candidate 的相關性。

---

### Bi-Encoder vs Cross-Encoder

| | Bi-Encoder | Cross-Encoder |
|--|------------|---------------|
| 做法 | Query 和 Doc 分別 embed，算餘弦相似度 | Query 和 Doc 一起輸入，輸出相關性分數 |
| 速度 | 快（預先 embed） | 慢（每次都要跑模型） |
| 精準度 | 較低 | 高 |
| 用途 | 第一階段搜尋 | Reranking |

---

### 常用 Reranker

- `cross-encoder/ms-marco-MiniLM-L-6-v2`：輕量，快
- `Cohere Rerank`：API 服務，效果好
- `BGE-Reranker`：開源，中文強
- Vertex AI `Ranking API`：GCP 生態系

---

### Reranking 的代價

每次 rerank 都要跑 Cross-Encoder，`Top-50 candidates × 1 query` 就是 50 次推理。  
高流量系統要考慮：
- Reranker 的 latency budget
- 是否只在特定 query type 才用 reranking
- Reranker 模型的大小選擇

---

## Context Window Overflow：RAG 最容易忽略的地方

面試官問：

> *「你的 RAG 系統，如果 retrieve 到的內容超過 context window 怎麼辦？」*

---

### 為什麼會發生

- Chunk size 設太大
- Top-K 設太高
- 用戶問了一個需要多個文件才能回答的問題
- 文件本身很長（合約、報告）

---

### 處理策略

**1. Truncation（截斷）**  
最簡單，超過就截。  
問題：截掉的可能是關鍵資訊。

**2. Map-Reduce**  
把每個 chunk 分別送給 LLM 提取摘要，再把摘要合併後送給 LLM 回答。  
適合：需要跨多文件綜合的問題。  
缺點：多次 LLM 呼叫，延遲高、成本高。

**3. Refine（精煉）**  
依序處理每個 chunk，每次都把「前一次的答案 + 新 chunk」送進去更新答案。  
適合：答案需要累積推理的問題。

**4. Contextual Compression**  
在送進 LLM 之前，先用一個輕量模型把每個 chunk 壓縮成只保留和 query 相關的部分。  
LangChain 的 `ContextualCompressionRetriever` 就是這個概念。

**5. 重新設計 Chunk Size**  
如果頻繁 overflow，通常是 chunk size 設計問題。  
→ 縮小 chunk size  
→ 或改用 Parent-Child chunking

---

## 面試回答框架整理

這篇覆蓋的技術，面試中通常以這個順序被問到：

```
系統設計題：「設計一個 RAG 系統」
    ↓
「你的 Chunking 怎麼做？」
    ↓
「為什麼選這個 Embedding 模型？」
    ↓
「向量 DB 怎麼選？Schema 怎麼設計？」
    ↓
「純 vector search 夠嗎？你有沒有考慮 hybrid？」
    ↓
「Reranker 你有沒有用？為什麼？」
    ↓
「Context window 滿了怎麼辦？」
```

每一層都要能說清楚：**選了什麼、為什麼、trade-off 是什麼**。

這才是 FDE 面試的答題深度。

---

## 下一篇

[FDE 面試準備指南（六）：RAG 進階——檢索失敗、Grounding、評估指標與成本控制](/posts/fde-interview-guide-part6-rag-eval-zh/)
