---
title: "RAG 完全指南（四）：查詢轉換、Self-RAG 與 Context 壓縮"
date: 2026-05-19T09:00:00+08:00
draft: false
weight: 4
description: "當問題本身就是問題：深入三大 RAG 優化技術——Step-Back Prompting、Self-RAG 自我反思、以及 Context Compression。了解它們的核心原理、實作方式、優缺點與最佳使用場景。"
categories: ["AI", "Engineering", "all"]
tags: ["RAG", "Self-RAG", "Context Compression", "Query Transformation", "LangChain", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "28 min"
---

## 前言

前兩篇解決了「搜尋」的問題。這篇要解決兩個更深層的問題：

1. **問題本身就難以直接搜尋**：複雜問題需要先轉換或拆解
2. **Context 品質不夠純粹**：塞給 LLM 的資訊裡有太多噪音

這裡介紹三個技術：**Step-Back Prompting（退一步提問）**、**Self-RAG（自我反思 RAG）**、**Context Compression（上下文壓縮）**。

---

## 技術 1：查詢轉換（Query Transformation）

### 問題：複雜問題無法直接搜尋

有些問題不適合直接拿來做向量搜尋：

```
❌ 直接搜尋困難的問題類型：

「為什麼我們公司的 API 最近變慢了？」
→ 問題太具體，知識庫不可能有這個答案

「除了 Redis，還有哪些快取方案？」
→ 包含否定條件，搜尋容易找到 Redis 的文章

「比較 PostgreSQL 和 MySQL 的優缺點，然後說明哪個適合我們的場景」
→ 多個子問題，一次搜尋無法全部覆蓋
```

### Step-Back Prompting（退一步提問）

核心思想：先把具體問題「退一步」抽象化，搜尋更通用的背景知識，再回答具體問題。

```
具體問題：「Estrogen 會影響 BRCA1 的 transcription 嗎？」
退一步：「BRCA1 基因的調控機制是什麼？」
→ 先搜尋通用知識，再回答具體問題
```

```python
import openai

client = openai.OpenAI(api_key="your-api-key")


def step_back_query(original_query: str) -> str:
    """生成一個比原始問題更抽象的退一步問題"""
    prompt = f"""你是一個搜尋查詢優化助手。
將以下具體問題「退一步」，改寫成一個更通用、更基本的問題，
這個更通用的問題可以幫助找到回答原始問題所需的背景知識。

具體問題：{original_query}

更通用的退一步問題（只輸出問題，不要解釋）："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def rag_with_step_back(query: str, retriever) -> str:
    """Step-Back RAG pipeline"""
    # 退一步問題
    abstract_query = step_back_query(query)
    print(f"🔍 原始問題：{query}")
    print(f"🔙 退一步問題：{abstract_query}")

    # 用兩個問題分別搜尋
    specific_chunks  = retriever.retrieve(query,          top_k=3)
    abstract_chunks  = retriever.retrieve(abstract_query, top_k=2)

    # 合併 context
    context = "\n\n---\n\n".join(specific_chunks + abstract_chunks)

    prompt = f"""請根據以下背景知識回答問題。

【背景知識】
{context}

【問題】{query}

請先概述相關背景，再回答具體問題："""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content
```

### Query Decomposition（問題分解）

對複雜的多步驟問題，先分解成子問題再各自搜尋：

```python
import json

def decompose_query(complex_query: str) -> list[str]:
    """將複雜問題分解成可獨立搜尋的子問題"""
    prompt = f"""將以下複雜問題分解成 2-4 個簡單的子問題，
每個子問題都可以獨立在知識庫中搜尋。
以 JSON 陣列格式輸出，例如：["子問題1", "子問題2"]

複雜問題：{complex_query}

子問題 JSON："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return [complex_query]  # fallback：退回原始問題


def rag_with_decomposition(complex_query: str, retriever) -> str:
    """問題分解 RAG pipeline"""
    sub_questions = decompose_query(complex_query)
    print(f"📋 子問題：")
    for q in sub_questions:
        print(f"  - {q}")

    # 每個子問題分別搜尋，收集所有 context
    all_chunks = []
    for sub_q in sub_questions:
        chunks = retriever.retrieve(sub_q, top_k=2)
        all_chunks.extend(chunks)

    # 去重
    unique_chunks = list(dict.fromkeys(all_chunks))
    context = "\n\n---\n\n".join(unique_chunks)

    prompt = f"""請根據以下參考資料，完整回答這個複雜問題。

【參考資料】
{context}

【問題】{complex_query}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content


# 示範
# complex_q = "比較 Redis 和 Memcached 的架構差異，並說明各自適合哪些使用場景？"
# answer = rag_with_decomposition(complex_q, retriever)
```

**優點**：對複雜、多跳（multi-hop）問題效果顯著  
**缺點**：多次 LLM 呼叫，延遲和成本增加  
**最佳使用場景**：分析類問題、比較類問題、需要推理的多步驟問題

---

## 技術 2：Self-RAG（自我反思 RAG）

### 核心思想

Naive RAG 盲目地把所有檢索到的 chunk 塞給 LLM，不管它們是否真的相關。  
**Self-RAG** 讓 LLM 在整個流程中「自我反思」：

1. **是否需要檢索？**（有些問題 LLM 直接回答就好）
2. **檢索到的文件是否相關？**（過濾不相關的 chunk）
3. **生成的回答是否有充分根據？**（檢查答案是否基於 context）
4. **回答是否有用？**（自我評分）

```
問題
 ↓
[ISREL?] 這個問題需要外部知識嗎？
 ├── No → 直接生成答案
 └── Yes → 檢索文件
              ↓
           [ISREL] 每個文件相關嗎？過濾不相關的
              ↓
           生成多個草稿答案
              ↓
           [ISSUP] 答案有文件支持嗎？
              ↓
           [ISUSE] 哪個答案最有用？
              ↓
           輸出最佳答案
```

### 簡化版 Self-RAG 實作

```python
import openai

client = openai.OpenAI(api_key="your-api-key")


def needs_retrieval(question: str) -> bool:
    """判斷問題是否需要外部知識"""
    prompt = f"""判斷以下問題是否需要查詢外部知識庫才能回答（Yes/No）。

需要外部知識的例子：詢問具體事實、最新資訊、特定領域知識
不需要外部知識的例子：數學計算、常識性問題、語言翻譯

問題：{question}
回答（只輸出 Yes 或 No）："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5,
    )
    return response.choices[0].message.content.strip().lower() == "yes"


def is_relevant(question: str, chunk: str) -> bool:
    """判斷文件片段是否與問題相關"""
    prompt = f"""判斷以下【文件片段】是否包含回答【問題】的有用資訊（Yes/No）。

【問題】：{question}
【文件片段】：{chunk[:300]}

是否相關（只輸出 Yes 或 No）："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5,
    )
    return response.choices[0].message.content.strip().lower() == "yes"


def is_grounded(answer: str, context: str) -> bool:
    """判斷答案是否有 context 的支持，而非憑空捏造"""
    prompt = f"""判斷以下【回答】是否完全基於【參考資料】中的內容，
沒有加入參考資料以外的資訊（Yes/No）。

【參考資料】：{context[:500]}
【回答】：{answer[:300]}

是否有根據（只輸出 Yes 或 No）："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5,
    )
    return response.choices[0].message.content.strip().lower() == "yes"


def self_rag(question: str, retriever, max_retries: int = 2) -> str:
    """Self-RAG pipeline"""

    # Step 1: 是否需要檢索？
    if not needs_retrieval(question):
        print("💭 直接回答（不需要外部知識）")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": question}],
            temperature=0,
        )
        return response.choices[0].message.content

    print("🔍 需要外部知識，開始檢索...")

    for attempt in range(max_retries):
        # Step 2: 檢索文件
        raw_chunks = retriever.retrieve(question, top_k=5)

        # Step 3: 過濾不相關的文件
        relevant_chunks = [c for c in raw_chunks if is_relevant(question, c)]
        print(f"  📄 過濾後相關 chunk 數量：{len(relevant_chunks)}/{len(raw_chunks)}")

        if not relevant_chunks:
            if attempt < max_retries - 1:
                print("  ⚠️ 找不到相關文件，嘗試重新查詢...")
                continue
            return "根據現有資料，無法回答此問題。"

        context = "\n\n---\n\n".join(relevant_chunks)

        # Step 4: 生成回答
        prompt = f"""請根據以下參考資料回答問題。
只使用參考資料中的資訊，不要加入其他知識。

【參考資料】
{context}

【問題】{question}"""

        answer = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        ).choices[0].message.content

        # Step 5: 檢查答案是否有根據
        if is_grounded(answer, context):
            print("  ✅ 答案有文件支持")
            return answer
        else:
            print(f"  ⚠️ 答案可能包含幻覺，嘗試 {attempt + 1}/{max_retries}")

    return answer  # 即使可能有問題，還是返回最後一次的答案


# 使用範例
# answer = self_rag("Python 的 GIL 是什麼？", retriever)
# answer = self_rag("2 + 2 等於多少？", retriever)  # 不需要外部知識的問題
```

**優點**：大幅降低幻覺；對不需要 RAG 的問題不浪費搜尋資源；有自我品質把關  
**缺點**：多次 LLM 呼叫，延遲顯著增加；每步判斷的準確度依賴模型能力  
**最佳使用場景**：高可信度要求的問答（醫療、法律、財務）；需要精確溯源的系統

---

## 技術 3：Context Compression（上下文壓縮）

### 核心問題

向量搜尋取回的 chunk 通常包含大量與當前問題無關的「噪音」：

```
問題：「asyncio 的事件迴圈如何工作？」

取回的 chunk：
「Python 在 3.4 版本引入了 asyncio 模組，
提供非同步 I/O 的支援。asyncio 的核心是事件迴圈（Event Loop），
它透過單執行緒的方式調度協程（coroutine）。
Python 的 asyncio 可以搭配 aiohttp 做非同步 HTTP 請求，
也可以搭配 asyncpg 做非同步資料庫操作。此外，
Python 3.11 對 asyncio 的效能做了大幅改進...」

↑ 很多內容（aiohttp、asyncpg、效能改進）跟問題無關，但都會佔用 context window
```

Context Compression 的目標：**只保留 chunk 中與問題直接相關的部分**。

### 方法一：LLM 提取壓縮

```python
def compress_with_llm(question: str, chunk: str) -> str | None:
    """用 LLM 從 chunk 中提取與問題相關的句子"""
    prompt = f"""從以下【文件片段】中，只提取出與【問題】直接相關的句子。
如果整個片段都不相關，輸出「不相關」。
只輸出相關句子，不要加任何解釋或格式。

【問題】：{question}
【文件片段】：{chunk}

相關句子："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
    )
    result = response.choices[0].message.content.strip()
    return None if "不相關" in result else result


def rag_with_compression(question: str, retriever, top_k: int = 6) -> str:
    """帶 Context Compression 的 RAG pipeline"""
    # 故意取多一點 chunk（因為壓縮後會過濾掉部分）
    raw_chunks = retriever.retrieve(question, top_k=top_k)

    # 壓縮每個 chunk
    compressed = []
    for chunk in raw_chunks:
        result = compress_with_llm(question, chunk)
        if result:
            compressed.append(result)

    print(f"📉 壓縮：{len(raw_chunks)} chunks → {len(compressed)} 個相關片段")

    if not compressed:
        return "找不到相關資料。"

    context = "\n\n".join(compressed)

    prompt = f"""根據以下資料回答問題：

{context}

問題：{question}"""

    return client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    ).choices[0].message.content
```

### 方法二：嵌入相似度過濾（無需 LLM 呼叫）

```python
import numpy as np

def compress_by_sentence_similarity(
    question: str, chunk: str, threshold: float = 0.75
) -> str:
    """把 chunk 切成句子，過濾掉跟問題語意距離遠的句子"""
    import re

    # 切成句子（簡單版：按句號切）
    sentences = re.split(r'[。！？\.\!\?]', chunk)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    if not sentences:
        return chunk

    # 取得問題和所有句子的 embedding
    all_texts  = [question] + sentences
    embeddings = np.array([get_embedding(t) for t in all_texts])

    q_emb   = embeddings[0]
    s_embs  = embeddings[1:]

    # 計算每個句子與問題的相似度
    sims = s_embs @ q_emb / (
        np.linalg.norm(s_embs, axis=1) * np.linalg.norm(q_emb) + 1e-9
    )

    # 只保留相似度超過閾值的句子
    relevant_sentences = [s for s, sim in zip(sentences, sims) if sim >= threshold]

    return "。".join(relevant_sentences) if relevant_sentences else ""
```

### 方法三：LangChain ContextualCompressionRetriever

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
base_retriever = Chroma(
    embedding_function=OpenAIEmbeddings()
).as_retriever(search_kwargs={"k": 6})

# 建立壓縮器
compressor = LLMChainExtractor.from_llm(llm)

# 包裝成壓縮式 Retriever
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=base_retriever,
)

# 使用方式跟一般 retriever 相同
docs = compression_retriever.invoke("asyncio 的事件迴圈如何工作？")
for doc in docs:
    print(doc.page_content)
```

**優點**：減少 LLM 的 context 長度 → 降低 token 成本、提升回答焦點；有效過濾噪音  
**缺點**：LLM 壓縮方法增加延遲；Embedding 方法可能過度過濾  
**最佳使用場景**：文件較長且包含混雜主題；context window 有限；需要降低 LLM token 成本

---

## 組合使用：完整的進階 RAG Pipeline

把這篇和上一篇的技術組合，可以建立一個健壯的生產級 RAG：

```python
class AdvancedRAGPipeline:
    """結合 Query Decomposition + Hybrid Search + Reranker + Context Compression"""

    def __init__(self, chunks: list[str]):
        # 初始化各元件（略，見前幾篇）
        self.hybrid_retriever   = HybridRetriever(chunks)
        self.reranker           = CrossEncoder("BAAI/bge-reranker-base")

    def run(self, question: str) -> dict:
        # 1. 判斷是否需要問題分解
        sub_questions = decompose_query(question)
        is_complex = len(sub_questions) > 1

        if is_complex:
            print(f"🧩 複雜問題，分解為 {len(sub_questions)} 個子問題")
            all_candidates = []
            for sub_q in sub_questions:
                chunks = self.hybrid_retriever.hybrid_search(sub_q, top_k=10)
                all_candidates.extend(chunks)
            candidates = list(dict.fromkeys(all_candidates))[:20]
        else:
            candidates = self.hybrid_retriever.hybrid_search(question, top_k=20)

        # 2. Rerank
        pairs  = [[question, c] for c in candidates]
        scores = self.reranker.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        top_chunks = [c for c, _ in ranked[:6]]

        # 3. Context Compression
        compressed = []
        for chunk in top_chunks:
            result = compress_with_llm(question, chunk)
            if result:
                compressed.append(result)

        if not compressed:
            return {"answer": "找不到足夠的相關資料。", "sources": []}

        context = "\n\n---\n\n".join(compressed)

        # 4. 生成最終答案
        prompt = f"""根據以下參考資料詳細回答問題。

【參考資料】
{context}

【問題】{question}"""

        answer = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        ).choices[0].message.content

        return {"answer": answer, "context_used": compressed}
```

---

## 小結

| 技術 | 核心思想 | 解決的問題 |
|------|---------|-----------|
| Step-Back Prompting | 先抽象再具體 | 具體問題難以直接搜尋 |
| Query Decomposition | 分而治之 | 複雜多跳問題 |
| Self-RAG | 讓 LLM 自我把關 | 幻覺、不相關資料混入 |
| Context Compression | 只保留相關句子 | 噪音過多、token 浪費 |

下一篇（最終篇），我們進入**生產級 RAG 評估**：如何量化你的 RAG 品質？RAGAS 指標是什麼？以及 **Agentic RAG**——當 RAG 和 AI Agent 結合，能做到什麼？

---

**系列導覽**

- [第一篇](/posts/rag-series-part1-foundations-zh/)：基礎概念與第一個 RAG 系統
- [第二篇](/posts/rag-series-part2-chunking-vectordb-zh/)：Chunking 策略與向量資料庫選型
- [第三篇](/posts/rag-series-part3-advanced-retrieval-zh/)：進階檢索技術（混合搜尋、HyDE、Multi-Query、Reranker）
- **第四篇（本篇）**：查詢優化與 Context 壓縮
- [第五篇](/posts/rag-series-part5-production-zh/)：生產級 RAG 評估與 Agentic RAG
