---
title: "RAG 完全指南（二）：Chunking 策略與向量資料庫選型"
date: 2026-05-17T09:00:00+08:00
draft: false
weight: 2
description: "深入探討 RAG 系統的兩個核心基礎：如何切塊才能保留語意完整性，以及如何選擇適合的向量資料庫。包含五種 Chunking 策略比較與主流向量 DB 的實測比較。"
categories: ["AI", "Engineering", "all"]
tags: ["RAG", "Chunking", "Vector Database", "ChromaDB", "Pinecone", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "25 min"
---

## 前言

[上一篇](/posts/rag-series-part1-foundations-zh/)我們建立了一個最基本的 RAG pipeline。  
但實際上，**Chunking 策略**和**向量資料庫的選型**會直接決定你的 RAG 系統品質。

這篇深入討論這兩個核心基礎建設。

---

## Part 1：Chunking 策略

Chunking 是把長文件切成小片段的過程。切法不對，後面的搜尋再精準也救不了。

### 為什麼 Chunking 很重要？

想像你有一篇 10,000 字的技術文章，如果直接整篇丟進去，問「Python 的優點是什麼」，向量搜尋要在 10,000 字的「語意海洋」裡找到準確答案，難度極高。

好的 Chunking 原則：
- **每個 chunk 應該是語意完整的單元**（不要切斷句子、段落中間）
- **大小適中**：太小 → 資訊不夠完整；太大 → 搜尋精準度下降
- **有適度重疊（overlap）**：避免邊界上的資訊遺漏

---

### 策略 1：固定大小切塊（Fixed-Size Chunking）

最簡單的方法，按字元數或 token 數切割。

```python
from langchain_text_splitters import CharacterTextSplitter

splitter = CharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separator="\n",  # 優先在換行處切割
)

text = "你的長文字..."
chunks = splitter.split_text(text)
```

**優點**：簡單、可預測、實作快速  
**缺點**：可能把語意相關的句子切開  
**適合**：快速原型、結構單純的文件

---

### 策略 2：遞迴字元切塊（Recursive Character Chunking）

這是最常用的預設策略。它會依照優先順序嘗試不同分隔符：
`\n\n` → `\n` → `. ` → ` ` → 字元

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=60,
    # 預設分隔符順序：段落 → 換行 → 句子 → 空格
    separators=["\n\n", "\n", "。", ".", " ", ""],
)

chunks = splitter.split_text(text)
```

**優點**：比固定大小更尊重自然語言結構  
**缺點**：chunk 大小仍然不均勻  
**適合**：一般文章、說明文件、知識庫（**大多數情況的首選**）

---

### 策略 3：語意切塊（Semantic Chunking）

根據「語意斷裂點」切割，而非字元數。比較相鄰句子的向量相似度，相似度突然下降的地方就是切點。

```python
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

splitter = SemanticChunker(
    embeddings=embeddings,
    breakpoint_threshold_type="percentile",  # 超過第 95 百分位的語意差距就切
    breakpoint_threshold_amount=95,
)

chunks = splitter.split_text(text)
```

**優點**：每個 chunk 的語意完整性最高  
**缺點**：需要呼叫 Embedding API（索引成本更高）、速度較慢  
**適合**：高品質知識庫、法律文件、醫療資料

---

### 策略 4：文件結構切塊（Structure-Aware Chunking）

針對有明確結構的文件（Markdown、HTML、程式碼），按結構切割。

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter

# 按 Markdown 標題層級切割
headers_to_split_on = [
    ("#",  "H1"),
    ("##", "H2"),
    ("###","H3"),
]
splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
chunks = splitter.split_text(markdown_text)

# 每個 chunk 會帶有 metadata，例如：
# {"content": "...", "metadata": {"H1": "章節標題", "H2": "小節標題"}}
```

**優點**：chunk 有結構 metadata，可以用標題做 filter；語意非常完整  
**缺點**：只適合有結構的文件  
**適合**：技術文件、Wiki、程式碼說明文件

---

### 策略 5：父子切塊（Parent-Child Chunking / Small-to-Big）

儲存時用小 chunk（提升搜尋精準度），但回傳時用大 chunk（提供更多 context 給 LLM）。

```python
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 子 chunk：用於向量搜尋（小）
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)

# 父 chunk：返回給 LLM（大）
parent_splitter = RecursiveCharacterTextSplitter(chunk_size=800)

vectorstore = Chroma(embedding_function=OpenAIEmbeddings())
store = InMemoryStore()

retriever = ParentDocumentRetriever(
    vectorstore=vectorstore,
    docstore=store,
    child_splitter=child_splitter,
    parent_splitter=parent_splitter,
)
```

**核心思想**：小 chunk 搜尋精準，大 chunk 提供足夠的前後文脈  
**優點**：兼顧搜尋精準度和 context 完整性  
**缺點**：實作稍複雜，需要額外維護文件儲存  
**適合**：高品質問答系統、企業知識庫

---

### 策略比較表

| 策略 | 語意完整性 | 實作複雜度 | 索引成本 | 適用場景 |
|------|-----------|-----------|---------|---------|
| 固定大小 | ★★☆☆☆ | ★☆☆☆☆ | 低 | 快速原型 |
| 遞迴字元 | ★★★☆☆ | ★★☆☆☆ | 低 | 一般文件（首選） |
| 語意切塊 | ★★★★★ | ★★★☆☆ | 高 | 高品質知識庫 |
| 結構感知 | ★★★★☆ | ★★★☆☆ | 低 | 技術文件、Wiki |
| 父子切塊 | ★★★★☆ | ★★★★☆ | 中 | 企業問答系統 |

---

## Part 2：向量資料庫選型

向量資料庫負責儲存和搜尋 Embedding 向量。選錯工具可能導致效能瓶頸或維護惡夢。

### 主流選項比較

#### ChromaDB — 開發首選

```python
import chromadb

# 本地模式（開發用）
client = chromadb.Client()

# 持久化模式
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="my_knowledge_base",
    metadata={"hnsw:space": "cosine"},  # 使用餘弦相似度
)

# 新增文件
collection.add(
    documents=["文件內容 1", "文件內容 2"],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],
    metadatas=[{"source": "doc1.pdf", "page": 1}, {"source": "doc2.pdf", "page": 5}],
    ids=["id1", "id2"],
)

# 查詢（帶 metadata filter）
results = collection.query(
    query_embeddings=[query_vec],
    n_results=5,
    where={"source": "doc1.pdf"},  # 只搜尋特定來源
)
```

**優點**：開源、零設定、本地運行、支援 metadata filter  
**缺點**：不適合超大規模（> 百萬筆）生產環境  
**定價**：免費

---

#### Pinecone — 雲端託管首選

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

# 建立 index
pc.create_index(
    name="my-rag-index",
    dimension=1536,           # text-embedding-3-small 的維度
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
)

index = pc.Index("my-rag-index")

# 寫入（帶 metadata）
index.upsert(vectors=[
    {
        "id": "chunk_001",
        "values": embedding_vector,
        "metadata": {"source": "annual_report.pdf", "page": 12, "topic": "finance"},
    }
])

# 查詢
results = index.query(
    vector=query_embedding,
    top_k=5,
    filter={"topic": {"$eq": "finance"}},  # metadata filter
    include_metadata=True,
)
```

**優點**：全託管、自動擴展、高可用、filter 功能強大  
**缺點**：有費用、資料在第三方雲端  
**定價**：免費額度 + 按用量計費  
**適合**：需要快速上線、不想維護基礎設施的團隊

---

#### Qdrant — 自託管生產首選

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)

client = QdrantClient(url="http://localhost:6333")  # 或 QdrantClient(":memory:")

# 建立 collection
client.create_collection(
    collection_name="knowledge_base",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# 寫入
client.upsert(
    collection_name="knowledge_base",
    points=[
        PointStruct(
            id=1,
            vector=embedding_vector,
            payload={"source": "doc.pdf", "page": 3, "category": "finance"},
        )
    ],
)

# 查詢（帶複雜 filter）
results = client.search(
    collection_name="knowledge_base",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="finance"))]
    ),
    limit=5,
)
```

**優點**：高效能、豐富 filter、支援多向量、可自託管或用 Qdrant Cloud  
**缺點**：比 ChromaDB 設定稍複雜  
**適合**：需要自託管且有複雜過濾需求的生產系統

---

#### pgvector — PostgreSQL 擴充

如果你的應用已經在用 PostgreSQL，pgvector 可以讓你不需要引入新的資料庫。

```sql
-- 安裝擴充
CREATE EXTENSION IF NOT EXISTS vector;

-- 建立有向量欄位的表
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    source VARCHAR(255),
    embedding vector(1536)  -- 向量維度
);

-- 建立 HNSW index（加速查詢）
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops);

-- 插入資料
INSERT INTO documents (content, source, embedding)
VALUES ('文件內容', 'doc.pdf', '[0.1, 0.2, ...]'::vector);

-- 相似度搜尋
SELECT content, source, 1 - (embedding <=> '[0.3, 0.1, ...]'::vector) AS similarity
FROM documents
ORDER BY embedding <=> '[0.3, 0.1, ...]'::vector
LIMIT 5;
```

```python
# Python 操作
import psycopg2
import numpy as np

conn = psycopg2.connect("postgresql://user:password@localhost/mydb")
cur = conn.cursor()

query_vec = np.array(get_embedding("你的查詢")).tolist()

cur.execute("""
    SELECT content, source,
           1 - (embedding <=> %s::vector) AS similarity
    FROM documents
    ORDER BY embedding <=> %s::vector
    LIMIT 5
""", (query_vec, query_vec))

results = cur.fetchall()
```

**優點**：不增加新系統、可以跟業務資料做 JOIN、事務支援  
**缺點**：效能不如專門的向量 DB（百萬級以上需要仔細調校）  
**適合**：已有 PostgreSQL、規模中等（< 500 萬筆）的應用

---

### 選型決策樹

```
你的資料量有多大？
├── < 10 萬筆，主要是開發/測試
│   └── → ChromaDB（本地，零設定）
│
├── 10 萬 ~ 500 萬筆，生產環境
│   ├── 已有 PostgreSQL？
│   │   └── → pgvector（最省事）
│   ├── 想自託管？
│   │   └── → Qdrant（效能最好的開源選項）
│   └── 想雲端託管？
│       └── → Pinecone（最省維運）
│
└── > 500 萬筆，高並發
    ├── 自託管 → Qdrant / Milvus
    └── 雲端 → Pinecone / Weaviate Cloud
```

---

## 實作：帶 Metadata Filter 的完整 RAG

結合上述兩個概念，這裡展示一個帶有來源過濾的實用 RAG 系統：

```python
import chromadb
import openai
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path

client = openai.OpenAI(api_key="your-api-key")
chroma = chromadb.PersistentClient(path="./rag_db")
collection = chroma.get_or_create_collection(
    "company_docs",
    metadata={"hnsw:space": "cosine"},
)

def embed(text: str) -> list[float]:
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding

def index_file(filepath: str, category: str) -> int:
    """索引單一檔案，帶來源 metadata"""
    text = Path(filepath).read_text(encoding="utf-8")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)

    collection.add(
        documents=chunks,
        embeddings=[embed(c) for c in chunks],
        metadatas=[{"source": filepath, "category": category} for _ in chunks],
        ids=[f"{filepath}_chunk_{i}" for i in range(len(chunks))],
    )
    return len(chunks)

def rag_with_filter(query: str, category: str | None = None, top_k: int = 4) -> dict:
    """支援 category filter 的 RAG 查詢"""
    where = {"category": category} if category else None

    results = collection.query(
        query_embeddings=[embed(query)],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks    = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # 過濾低相關度（餘弦距離 > 0.5 表示相似度 < 0.5）
    filtered = [
        (c, m) for c, m, d in zip(chunks, metadatas, distances) if d < 0.5
    ]

    if not filtered:
        return {"answer": "找不到相關資料。", "sources": []}

    context = "\n\n---\n\n".join(c for c, _ in filtered)
    sources  = list({m["source"] for _, m in filtered})

    prompt = f"""根據以下參考資料回答問題。請在回答末尾標注資料來源。

【參考資料】
{context}

【問題】{query}"""

    answer = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    ).choices[0].message.content

    return {"answer": answer, "sources": sources}


# 使用範例
if __name__ == "__main__":
    # 索引不同類別的文件
    # index_file("hr_policy.md", category="hr")
    # index_file("engineering_guide.md", category="engineering")

    # 只在工程文件裡搜尋
    result = rag_with_filter(
        query="如何申請 production deploy?",
        category="engineering",
    )
    print(result["answer"])
    print("來源：", result["sources"])
```

---

## 小結

這篇涵蓋了：

- **5 種 Chunking 策略**的原理、優缺點與選擇時機
- **4 種向量資料庫**的特性比較與選型決策樹
- **帶 Metadata Filter 的完整 RAG 實作**

有了扎實的資料基礎，下一篇我們進入真正的進階技術：  
**混合搜尋、HyDE（假設性文件嵌入）、Multi-Query Retrieval、Reranker**——  
讓你的 RAG 在複雜問題上也能精準命中。

---

**系列導覽**

- [第一篇](/posts/rag-series-part1-foundations-zh/)：基礎概念與第一個 RAG 系統
- **第二篇（本篇）**：Chunking 策略與向量資料庫選型
- [第三篇](/posts/rag-series-part3-advanced-retrieval-zh/)：進階檢索技術（混合搜尋、HyDE、Multi-Query、Reranker）
- [第四篇](/posts/rag-series-part4-optimization-zh/)：查詢優化與 Context 壓縮
- [第五篇](/posts/rag-series-part5-production-zh/)：生產級 RAG 評估與 Agentic RAG
