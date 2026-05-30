---
title: "FDE 面試準備指南（一）：RAG 完全解析"
date: 2026-05-30T10:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，解析 FDE 面試中 RAG 最高頻考題，包含核心架構、Chunk 策略、幻覺改善與實戰建議"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "RAG", "LLM", "Vector DB", "Interview", "Google"]
authors: ["yen"]
readTime: "12 min"
---

> 我在 Google 做 AI 工程，也是面試官。  
> 這是一份寫給準備 FDE 面試的人看的系列。  
> 不是教科書，是我站在白板前問過你才懂的那種。

---

## 為什麼 RAG 是第一篇

FDE 的 JD 幾乎都明寫：

> *"Experience with Retrieval-Augmented Generation (RAG) architectures"*

這不是裝飾。這是你第一關就會被問到的東西。

我面試過不少人，能把 RAG 說清楚的，比你想像中少。

---

## RAG 是什麼

用一句話說完：

> **RAG = 讓 LLM 在回答前，先去查資料。**

不讓它憑空捏造，而是給它上下文，再要求它根據上下文回答。

### 完整流程，五個步驟

```
使用者問題
    ↓
① Embedding（把問題變成向量）
    ↓
② Retrieval（從向量資料庫搜尋相關文件）
    ↓
③ Context Injection（把文件塞進 Prompt）
    ↓
④ Generation（LLM 根據 Prompt 生成回答）
    ↓
回答
```

#### ① Embedding

把文字轉成一個數字向量，讓機器能比較「語意距離」。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
query_vector = model.encode("什麼是向量資料庫？")
# → [0.12, -0.34, 0.87, ...]  # 384 維向量
```

重點：**兩個向量越接近，代表語意越相似。**

#### ② Retrieval（向量資料庫）

常見選擇：

| 工具 | 適合場景 |
|------|----------|
| Pinecone | 雲端託管，快速上手 |
| Weaviate | 支援 hybrid search |
| pgvector | PostgreSQL 擴充，低門檻 |
| Chroma | 本地開發 / 原型 |
| Vertex AI Vector Search | GCP 全託管，生產首選 |

```python
import chromadb

client = chromadb.Client()
collection = client.get_or_create_collection("company_docs")

# 查詢最相近的 5 筆
results = collection.query(
    query_embeddings=[query_vector.tolist()],
    n_results=5
)
```

#### ③ Context Injection

把查到的文件塞進 Prompt：

```python
context = "\n\n".join(results["documents"][0])

prompt = f"""
根據以下資料回答問題。若資料不足，請說「我不知道」，不要猜測。

資料：
{context}

問題：{user_question}
"""
```

這個 `不要猜測` 很重要，後面會說為什麼。

#### ④ Generation

```python
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}]
)
print(response.content[0].text)
```

---

## 面試必考：RAG vs Fine-tuning

這是我最愛問的對比題。

很多人答得很模糊。讓我給你一個清楚的版本：

| 維度 | RAG | Fine-tuning |
|------|-----|-------------|
| **知識更新** | 即時（改資料庫就好） | 需要重新訓練 |
| **成本** | 低（inference + retrieval） | 高（GPU 訓練費用） |
| **可引用來源** | 可以（查到哪篇文件） | 幾乎不行 |
| **私有資料** | 很適合 | 有資料外洩風險 |
| **推理格式** | 彈性 | 固定（訓練時決定） |
| **幻覺風險** | 相對低（有 context 約束） | 相對高 |

**什麼時候選 Fine-tuning？**

- 你需要改變模型的「說話方式」（語氣、格式、風格）
- 任務高度特化，且訓練資料充足（例如法律文件解析）
- 對 latency 要求極高，不允許每次查資料庫

**什麼時候選 RAG？**

- 資料頻繁更新（產品文件、政策、FAQ）
- 需要追溯來源（企業知識庫、客服系統）
- 預算有限，快速上線

---

## 面試必考：Chunk Size 怎麼選

這題問的人很多，但能說清楚 trade-off 的人不多。

### Chunk 是什麼

在把文件放進向量資料庫之前，要先把它切成小塊（chunk），每塊各自 embedding。

問題是：**切多大？**

```
原始文件（10,000 tokens）
    ↓ 切成 chunks
[chunk_1: 500 tokens]
[chunk_2: 500 tokens]
[chunk_3: 500 tokens]
...
```

### 三種常見大小的差異

| Chunk Size | Recall | Precision | Cost | 適合 |
|-----------|--------|-----------|------|------|
| 小（~200 tokens） | 低 | 高 | 低 | 精確問答、FAQ |
| 中（~500 tokens） | 中 | 中 | 中 | 通用首選 |
| 大（~1000 tokens） | 高 | 低 | 高 | 長段落理解 |

**小 chunk**：每塊資訊集中，查到的東西很精準，但可能漏掉需要跨段落的上下文。

**大 chunk**：查到的東西上下文豐富，但塞進 Prompt 的 token 多，成本高，也可能稀釋相關資訊。

### 實務建議

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,        # 目標大小
    chunk_overlap=50,      # 重疊部分（避免邊界截斷）
    separators=["\n\n", "\n", "。", " "]  # 優先按段落切
)

chunks = splitter.split_text(document_text)
```

**Overlap 很重要**：沒有 overlap 的話，一個句子可能剛好被切到兩個 chunk 的邊界，語意就斷了。

### 我在面試中想聽到什麼

不是「500 tokens」這個數字，而是：

> *「我會先看文件的結構——是密集技術文件還是 FAQ？然後設計評估指標，跑幾組 chunk size，看 Recall@5 和 Answer Relevance，再決定。」*

這才是工程師的思維。

---

## 面試必考：RAG 幻覺怎麼改善

RAG 的幻覺比純 LLM 少，但不是零。

常見的幻覺場景：

1. 查到的文件和問題其實不相關，但 LLM 還是硬回答
2. 文件有多個版本，LLM 混著用
3. Prompt 太長，LLM 忽略了關鍵段落

### 五個改善方向

#### 1. 更好的 Chunking

按語意切，而非固定長度：

```python
# 不好：固定切 500 個字
text[:500], text[500:1000], ...

# 好：按段落 / 標題切
splitter = RecursiveCharacterTextSplitter(
    separators=["\n## ", "\n### ", "\n\n", "\n"]
)
```

#### 2. Metadata Filtering

查資料時加過濾條件，避免查到不相關的文件：

```python
results = collection.query(
    query_embeddings=[query_vector],
    n_results=5,
    where={
        "department": "engineering",    # 只查工程部門的文件
        "version": {"$gte": "2024"},    # 只查 2024 年後的版本
        "language": "zh-TW"
    }
)
```

#### 3. Hybrid Search

純向量搜尋有時候抓不到特定關鍵字。結合全文搜尋（BM25）效果更好：

```python
# 語意搜尋：找「相似意思」的文件
semantic_results = vector_db.query(query_embedding)

# 關鍵字搜尋：找「包含這個詞」的文件
keyword_results = bm25_index.search(query_text)

# 結合（RRF: Reciprocal Rank Fusion）
final_results = reciprocal_rank_fusion(semantic_results, keyword_results)
```

Google 自家的 Vertex AI Search 預設就有 hybrid search。

#### 4. Reranking

第一輪搜尋取回 20 筆，再用更強的 cross-encoder 重新排序，只取前 5 筆：

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# 計算 (query, chunk) 的相關分數
pairs = [(query, chunk) for chunk in candidate_chunks]
scores = reranker.predict(pairs)

# 取最高分的 5 筆
top_chunks = [chunk for _, chunk in sorted(
    zip(scores, candidate_chunks), reverse=True
)][:5]
```

**為什麼不直接用 cross-encoder 查？** 因為它太慢，不適合掃整個資料庫。先用向量搜尋縮小範圍，再用 reranker 精選。

#### 5. Evaluation Pipeline

沒有評估就沒有改善。

常用指標：

```python
# RAGAS 框架（開源）
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_recall

results = evaluate(
    dataset=qa_pairs,
    metrics=[faithfulness, answer_relevancy, context_recall]
)

# faithfulness：回答是否忠於查到的文件（最重要）
# answer_relevancy：回答是否和問題相關
# context_recall：有沒有把正確的文件查出來
```

---

## 完整 RAG Pipeline 範例

```python
import chromadb
from sentence_transformers import SentenceTransformer
import anthropic

class SimpleRAG:
    def __init__(self):
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.db = chromadb.Client()
        self.collection = self.db.get_or_create_collection("docs")
        self.llm = anthropic.Anthropic()

    def add_documents(self, docs: list[dict]):
        texts = [d["content"] for d in docs]
        embeddings = self.embedder.encode(texts).tolist()
        self.collection.add(
            ids=[d["id"] for d in docs],
            embeddings=embeddings,
            documents=texts,
            metadatas=[d.get("metadata", {}) for d in docs]
        )

    def query(self, question: str) -> str:
        q_vec = self.embedder.encode([question]).tolist()
        results = self.collection.query(query_embeddings=q_vec, n_results=5)
        context = "\n\n---\n\n".join(results["documents"][0])

        prompt = f"""根據以下資料回答問題。若資料不足，請說「資料中沒有相關資訊」。

資料：
{context}

問題：{question}"""

        response = self.llm.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
```

---

## 面試答題模板

如果面試官問「解釋一下你對 RAG 的理解」，我建議這樣組織你的回答：

1. **一句話定義**：RAG 讓 LLM 在生成前先查資料，以減少幻覺並支援知識更新
2. **流程**：Embedding → Retrieval → Context Injection → Generation
3. **vs Fine-tuning**：RAG 適合知識頻繁更新、需要來源引用的場景
4. **主要挑戰**：Chunk 策略、Retrieval 品質、幻覺控制
5. **你的實作經驗**（如果有的話，要說具體數字）

---

## 小結

RAG 是 FDE 必考的第一題。

不要只背定義，面試官在意的是：

- 你知道每個環節的 trade-off
- 你有辦法設計評估，而不是憑感覺調參數
- 你遇到問題時，有系統性的改善方向

下一篇：**Agent System Design** — 如何設計一個不會失控的 AI Agent 系統。
