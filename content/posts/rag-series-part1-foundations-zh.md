---
title: "RAG 完全指南（一）：基礎概念與你的第一個 RAG 系統"
date: 2026-05-16T09:00:00+08:00
draft: false
description: "從零開始理解 RAG（Retrieval-Augmented Generation）：為什麼 LLM 需要外部知識、RAG 的核心架構是什麼，以及如何用 Python 實作一個最基本的 RAG pipeline。"
categories: ["AI", "Engineering", "all"]
tags: ["RAG", "LLM", "Vector Database", "Embeddings", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "20 min"
---

## 前言

如果你曾經問過 ChatGPT 最新的新聞，它會告訴你它的知識有截止日期（knowledge cutoff）。  
如果你問它你公司內部的文件，它完全不知道。

這是大型語言模型（LLM）的根本限制：**訓練資料是靜態的**。

**RAG（Retrieval-Augmented Generation）** 就是解決這個問題的主流方法。它讓 LLM 在回答前先「查資料」，就像一個學生考試時可以翻開參考書——而不是完全靠記憶。

這個系列共五篇，帶你從基礎到進階，完整掌握 RAG 的設計與優化。

---

## 為什麼 LLM 需要 RAG？

### LLM 的三大知識限制

| 問題 | 說明 |
|------|------|
| **知識截止日期** | 模型只知道訓練時間點之前的資訊 |
| **無法存取私有資料** | 公司內部文件、資料庫、個人筆記都不在訓練集裡 |
| **幻覺（Hallucination）** | 對不確定的問題，模型會「編造」聽起來合理的答案 |

### 解法比較

```
方案 A：Fine-tuning（微調）
  優點：模型真正「學會」知識
  缺點：成本高、資料需要大量、難以更新、模型大小增加

方案 B：RAG（檢索增強生成）
  優點：即時更新、成本低、可追溯來源
  缺點：需要維護向量資料庫、回答品質受檢索品質影響
```

**結論**：對大多數企業應用，RAG 是更實際的選擇。Fine-tuning 適合改變模型「風格」或「推理方式」，不適合注入大量知識。

---

## RAG 的核心架構

一個標準的 RAG 系統分成兩個主要流程：

### 1. 索引流程（Indexing Pipeline）— 離線執行

```
原始文件（PDF、Word、網頁）
    ↓
文字擷取（Text Extraction）
    ↓
切塊（Chunking）— 將長文件切成小片段
    ↓
向量化（Embedding）— 將文字轉成數字向量
    ↓
存入向量資料庫（Vector Store）
```

### 2. 查詢流程（Query Pipeline）— 即時執行

```
使用者問題（Query）
    ↓
向量化（Query Embedding）
    ↓
向量搜尋（Similarity Search）— 找出最相關的文件片段
    ↓
組合 Prompt（Context + Question）
    ↓
LLM 生成答案（Generation）
    ↓
回傳給使用者
```

這個最基本的架構被稱為 **Naive RAG**（樸素 RAG）。

---

## 核心概念解釋

### Embedding（向量嵌入）

Embedding 是把文字轉成一串數字（向量）的過程。  
語意相近的文字，它們的向量在空間中也會很接近。

```python
# 概念示意
"貓喜歡睡覺" → [0.12, -0.34, 0.87, ...]  # 768 維向量
"狗喜歡跑步" → [0.15, -0.31, 0.72, ...]  # 語意不同，但都是動物，有些維度接近
"量子物理"   → [-0.88, 0.92, -0.11, ...] # 語意差很多，向量距離遠
```

### 向量相似度

最常用的相似度計算方式是**餘弦相似度（Cosine Similarity）**：

```python
import numpy as np

def cosine_similarity(vec_a, vec_b):
    dot = np.dot(vec_a, vec_b)
    norm = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    return dot / norm

# 值域 -1 到 1，越接近 1 表示越相似
```

### Chunking（切塊）

為什麼要切塊？

1. LLM 的 context window 有限制
2. 太長的文件會「稀釋」相關資訊，降低搜尋精準度
3. 讓每個 chunk 專注在單一主題，提升匹配品質

---

## 實作：用 Python 建立你的第一個 RAG

### 環境安裝

```bash
pip install openai chromadb tiktoken langchain-text-splitters
```

### 完整範例程式碼

```python
import openai
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---- 設定 ----
client = openai.OpenAI(api_key="your-api-key")
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("my_docs")

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL  = "gpt-4o-mini"

# ---- 工具函式 ----

def get_embedding(text: str) -> list[float]:
    """將文字轉成向量"""
    response = client.embeddings.create(input=text, model=EMBED_MODEL)
    return response.data[0].embedding


def index_documents(docs: list[str]) -> None:
    """索引流程：切塊 → 向量化 → 存入向量 DB"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,       # 每塊最多 500 字元
        chunk_overlap=50,     # 前後重疊 50 字元，避免斷句
    )

    all_chunks = []
    for doc in docs:
        chunks = splitter.split_text(doc)
        all_chunks.extend(chunks)

    embeddings = [get_embedding(chunk) for chunk in all_chunks]

    collection.add(
        documents=all_chunks,
        embeddings=embeddings,
        ids=[f"chunk_{i}" for i in range(len(all_chunks))],
    )
    print(f"✅ 已索引 {len(all_chunks)} 個 chunks")


def retrieve(query: str, top_k: int = 3) -> list[str]:
    """查詢流程：向量搜尋，取出最相關的 chunks"""
    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
    return results["documents"][0]  # 回傳 top_k 個文字片段


def generate_answer(query: str, context_chunks: list[str]) -> str:
    """組合 Prompt，讓 LLM 根據 context 回答"""
    context = "\n\n---\n\n".join(context_chunks)

    prompt = f"""你是一個知識庫問答助手。請根據以下【參考資料】回答【問題】。
如果參考資料中沒有足夠資訊，請直接說「根據現有資料無法回答」，不要自行推測。

【參考資料】
{context}

【問題】
{query}

【回答】"""

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,  # RAG 場景建議設低，減少創意發揮
    )
    return response.choices[0].message.content


# ---- 主程式 ----

def rag_pipeline(query: str) -> str:
    """完整的 RAG pipeline"""
    # Step 1: 檢索
    relevant_chunks = retrieve(query, top_k=3)

    # Step 2: 生成
    answer = generate_answer(query, relevant_chunks)

    return answer


# ---- 示範 ----

if __name__ == "__main__":
    # 準備知識文件（實際場景可以是 PDF、Markdown、資料庫內容）
    documents = [
        """
        Python 是一種高階、直譯式程式語言，由 Guido van Rossum 在 1991 年發布。
        Python 的設計哲學強調程式碼的可讀性，使用縮排來表示程式碼區塊。
        Python 廣泛應用於資料科學、機器學習、網頁開發和自動化腳本。
        """,
        """
        向量資料庫是專門儲存和搜尋向量嵌入的資料庫系統。
        常見的向量資料庫包括：Chroma、Pinecone、Weaviate、Qdrant、Milvus。
        向量資料庫使用近似最近鄰搜尋（ANN）演算法，可以在百萬筆資料中快速找到最相似的向量。
        """,
        """
        RAG（Retrieval-Augmented Generation）是一種結合資訊檢索與文字生成的 AI 架構。
        RAG 的主要優點是可以讓 LLM 存取外部知識庫，解決模型知識過時的問題。
        RAG 系統通常由三個部分組成：文件索引、相似度搜尋、語言模型生成。
        """,
    ]

    # 索引文件
    index_documents(documents)

    # 查詢
    questions = [
        "RAG 有哪些主要優點？",
        "有哪些常見的向量資料庫？",
        "Python 是誰發明的？",
    ]

    for q in questions:
        print(f"\n❓ 問題：{q}")
        answer = rag_pipeline(q)
        print(f"💡 回答：{answer}")
```

### 預期輸出

```
✅ 已索引 3 個 chunks

❓ 問題：RAG 有哪些主要優點？
💡 回答：根據參考資料，RAG 的主要優點是可以讓 LLM 存取外部知識庫，解決模型知識過時的問題。

❓ 問題：有哪些常見的向量資料庫？
💡 回答：常見的向量資料庫包括：Chroma、Pinecone、Weaviate、Qdrant、Milvus。

❓ 問題：Python 是誰發明的？
💡 回答：Python 是由 Guido van Rossum 發明的，並於 1991 年發布。
```

---

## Naive RAG 的局限性

這個基本實作已經可以運作，但在實際應用中會碰到幾個問題：

| 問題 | 現象 | 後續篇章 |
|------|------|----------|
| **Chunking 策略粗糙** | 語意被切斷，搜尋精準度低 | 第二篇 |
| **只有語意搜尋** | 關鍵字搜尋效果有時更好 | 第三篇（混合搜尋） |
| **單次查詢不夠** | 複雜問題需要多次查詢才能拼湊完整答案 | 第三篇（Multi-Query） |
| **沒有 Reranking** | Top-K 結果可能不是最相關的 | 第三篇（Reranker） |
| **Context 太長** | 塞入過多不相關 chunk，LLM 反而混淆 | 第四篇（Context Compression） |
| **沒有評估指標** | 不知道 RAG 品質好不好 | 第五篇 |

---

## 小結

這篇介紹了：

- **為什麼需要 RAG**：LLM 的知識限制
- **RAG 的核心架構**：索引流程 vs 查詢流程
- **關鍵概念**：Embedding、向量相似度、Chunking
- **第一個 RAG 實作**：用 ChromaDB + OpenAI 建立完整 pipeline

下一篇我們會深入探討 **Chunking 策略**與**向量資料庫的選型**，讓 RAG 的基礎打得更扎實。

---

**系列導覽**

- **第一篇（本篇）**：基礎概念與第一個 RAG 系統
- [第二篇](/posts/rag-series-part2-chunking-vectordb-zh/)：Chunking 策略與向量資料庫選型
- [第三篇](/posts/rag-series-part3-advanced-retrieval-zh/)：進階檢索技術（混合搜尋、HyDE、Multi-Query、Reranker）
- [第四篇](/posts/rag-series-part4-optimization-zh/)：查詢優化與 Context 壓縮
- [第五篇](/posts/rag-series-part5-production-zh/)：生產級 RAG 評估與 Agentic RAG
