---
title: "FDE 面試準備指南（九）：LLM 核心知識——Token、Prompt Engineering 與 Embedding"
date: 2026-05-31T11:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，整理 FDE 面試中最關鍵的 LLM 實用知識：Token 與 Context Window 的工程意涵、Prompt Engineering 五大技法，以及 Embedding 在語意搜尋中的原理與選型"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "LLM", "Prompt Engineering", "Embedding", "Token", "RAG", "CoT", "ReAct", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> 這篇是 FDE 面試系列的最後一篇基礎知識篇。  
> LLM 的這三塊——Token、Prompt Engineering、Embedding——  
> 是你每天都在用的工具，但能說清楚的人比你想像中少。  
> 說得清楚，就是專業的訊號。

---

## 一、Token：不是字，是 LLM 的計量單位

面試官問：

> *「Context Window 是什麼？對你的系統設計有什麼影響？」*

---

### Token 是什麼

LLM 不是以字元或單詞為單位處理文字，而是以 **Token** 為單位。

Token 是 Tokenizer 切出來的文字片段，大小不固定：

```
"Hello world"  →  ["Hello", " world"]         → 2 tokens
"LLM"          →  ["L", "LM"]                 → 2 tokens（或 1 token，取決於 tokenizer）
"不可思議"      →  ["不", "可", "思", "議"]    → 4 tokens（中文通常 1 字 = 1 token）
```

**粗略換算（GPT/Gemini 系列）：**
- 英文：約 1 token ≈ 0.75 個單詞，1000 tokens ≈ 750 個英文字
- 中文：約 1 token ≈ 1 個中文字

---

### Input Token vs Output Token

| | Input Token | Output Token |
|--|-------------|--------------|
| 是什麼 | 你送進去的：system prompt + history + context + user query | LLM 生成的回答 |
| 計費 | 通常比 output 便宜 | 通常比 input 貴（約 3-5x） |
| 設計影響 | 長 prompt / 多 few-shot → 成本增加 | 長回答 → 成本和延遲都增加 |

---

### Context Window

Context Window 是 LLM 在一次推理中能「看到」的最大 token 數。

```
Context Window = Input tokens + Output tokens
```

常見 Context Window（2024-2025 年資料）：

| 模型 | Context Window |
|------|---------------|
| Gemini 1.5 Pro | 1,000,000 tokens |
| Gemini 1.5 Flash | 1,000,000 tokens |
| Gemini 2.0 Flash | 1,048,576 tokens |
| GPT-4o | 128,000 tokens |
| Claude 3.5 Sonnet | 200,000 tokens |

---

### Context Window 的工程意涵

Context Window 不只是理論限制，它是你設計 RAG 和 Agent 時每天要想的事：

**1. RAG 的 context budget：**
```
Context Window
  - System Prompt (~500 tokens)
  - Conversation History (動態)
  - Retrieved Chunks (你能控制的部分)
  = 留給生成的空間
```

你能塞多少 retrieved chunks，直接決定了 Top-K 的上限。

**2. 超出 window 的後果：**
- 硬截斷（錯誤）
- 滑動視窗（丟失早期資訊）
- 要求用戶縮短問題（差的用戶體驗）

**3. Long Context 不等於 Good Performance：**
研究顯示，LLM 對放在 context 中間的資訊的關注度，比頭尾的資訊低（**Lost in the Middle** 效應）。  
→ 把最重要的資訊放在 context 的開頭或結尾。

---

## 二、Prompt Engineering：五大技法

Prompt Engineering 是 FDE 日常工作的核心技能。  
面試官不太會直接問「什麼是 Few-shot」，但他們會在系統設計題中評估你有沒有這些工具。

---

### 1. Zero-Shot Prompting

不給任何範例，直接讓 LLM 完成任務。

```
Classify the following customer review as Positive, Negative, or Neutral:
"The product arrived late but the quality was excellent."
```

**適合：** 任務清楚、LLM 能力足夠的場景  
**問題：** 複雜任務或邊界情況容易出錯

---

### 2. Few-Shot Prompting

給幾個輸入/輸出範例，引導 LLM 理解任務格式和期望。

```
Classify the customer review:

Review: "Shipping was fast, product works great." → Positive
Review: "Terrible quality, broke after one day." → Negative
Review: "It's okay, nothing special." → Neutral

Review: "The product arrived late but the quality was excellent." → ?
```

**為什麼有效？**
- 讓 LLM 理解你的輸出格式
- 減少對 task instruction 的歧義
- 可以引導 LLM 處理 edge case

**面試要能說的重點：**
- Example 的品質比數量重要
- Example 要覆蓋各種情況，不要全是正面例子
- 對成本有影響（每次都要帶著 few-shot examples）

---

### 3. Chain of Thought (CoT)（思維鏈）

要求 LLM 在給出答案之前，先「一步一步地思考」。

**Without CoT：**
```
Q: Roger has 5 tennis balls. He buys 2 more cans of tennis balls.
   Each can has 3 balls. How many tennis balls does he have now?
A: 11
```

**With CoT：**
```
Q: （同上問題）Let's think step by step.
A: Roger started with 5 balls.
   He bought 2 cans × 3 balls = 6 balls.
   Total: 5 + 6 = 11 balls.
   Answer: 11
```

**為什麼有效？**  
LLM 生成 token 的過程本身就是推理過程。強迫它「說出思考步驟」等於給它更多「計算空間」，減少跳躍推理的錯誤。

**實務應用：**
- 複雜計算題
- 多步推理
- 程式碼生成前先解釋邏輯

---

### 4. Self-Consistency（自我一致性）

對同一個問題用高溫度（high temperature）採樣多次，選出最多次出現的答案。

```
Question: X
→ Sample 1: Answer A
→ Sample 2: Answer A
→ Sample 3: Answer B
→ Sample 4: Answer A

Final Answer: A（出現 3 次，最多）
```

**為什麼有效？**  
LLM 有隨機性，有時候「運氣差」會給出錯誤答案。多次採樣 + 投票可以提高準確率。

**代價：** 多次 LLM 呼叫，成本和延遲倍增。  
**適合：** 答案精準度非常重要的場景，且 latency 不是首要考量。

---

### 5. ReAct（Reasoning + Acting）

這在前面 Agent 篇有詳細介紹，這裡強調它作為 Prompt Engineering 技法的角度。

ReAct 把「思考（Reasoning）」和「行動（Acting）」交替輸出：

```
Thought: 用戶想知道 Q4 銷售數字，我需要查詢資料庫
Action: query_database[SELECT SUM(revenue) FROM sales WHERE quarter='Q4']
Observation: $4,200,000
Thought: 我有了 Q4 的數字，可以回答用戶
Action: final_answer[Q4 銷售額為 $4.2M]
```

**Google JD 為什麼特別點名 ReAct？**  
因為 FDE 的工作是幫客戶設計 Agent 系統，而 ReAct 是 Agent 的事實標準模式。不熟悉 ReAct，就是不熟悉 Agent。

---

### Prompt Engineering 的實務建議

| 建議 | 說明 |
|------|------|
| **System Prompt 明確定義角色** | 「你是 X，你的任務是 Y，你只回答 Z 類問題」 |
| **Output Format 明確指定** | 「以 JSON 格式回答」「只輸出一個詞：Positive/Negative/Neutral」|
| **加入 Negative Instructions** | 「不要猜測」「如果不確定，說不知道，不要捏造」 |
| **版本控制 Prompt** | Prompt 就是程式碼，要版本控制、測試、追蹤效果 |
| **測試 Edge Cases** | 用戶會輸入奇怪的東西，你的 prompt 要 robust |

---

## 三、Embedding：語意搜尋的基礎

面試官問：

> *「你用什麼方式做語意搜尋？Embedding 是怎麼運作的？」*

---

### 什麼是 Embedding

Embedding 是把文字（或其他資料）轉換成**固定長度的數值向量**的技術。

```
"今天天氣很好" → [0.23, -0.15, 0.87, ..., 0.42]  (768 維向量)
"The weather is great today" → [0.24, -0.14, 0.85, ..., 0.41]  (語意相似 → 向量相近)
```

核心性質：**語意相似的文字，向量距離近**。

---

### Word Embedding vs Sentence Embedding

**Word Embedding（詞嵌入）：**  
早期方法，每個詞有一個固定向量（Word2Vec, GloVe）。  
問題：「bank」這個詞在「river bank」和「bank account」中應該有不同的向量，但 Word Embedding 無法區分（沒有上下文）。

**Sentence Embedding / Contextual Embedding：**  
基於 Transformer，每個詞的向量根據上下文動態計算。  
整個句子或段落壓縮成一個向量。

這是現在 RAG 系統用的方式。

---

### Vector Embedding 的計算

以 BERT/Sentence-BERT 為例：

```
Input: "今天天氣很好"
↓
Tokenizer → [101, 231, 56, 78, 99, 102]（token IDs）
↓
Transformer Encoder → 每個 token 的 contextual representation
↓
Pooling（取 [CLS] token 或平均所有 token）
↓
Output: [0.23, -0.15, 0.87, ..., 0.42]（例如 768 維）
```

---

### Semantic Search（語意搜尋）流程

```
建索引：
  Documents → Embedding Model → Vectors → 存入 Vector DB

查詢：
  Query → Embedding Model → Query Vector
  Query Vector → 在 Vector DB 做 ANN 搜尋 → Top-K 相似文件
```

**相似度計算：**
- **Cosine Similarity**：最常用，計算兩個向量夾角的餘弦值（-1 到 1）
- **Dot Product**：適合模型訓練時用 dot product 優化過的 embedding
- **Euclidean Distance**：歐幾里得距離（越小越相似）

---

### 常用 Embedding 模型（FDE 視角）

**Google 生態系：**
```python
from vertexai.language_models import TextEmbeddingModel

model = TextEmbeddingModel.from_pretrained("text-embedding-004")
embeddings = model.get_embeddings(
    texts=["這是第一個句子", "這是第二個句子"],
    task_type="RETRIEVAL_DOCUMENT"  # 重要！指定 task type
)
```

`text-embedding-004` 的 `task_type` 參數：
| Task Type | 用途 |
|-----------|------|
| `RETRIEVAL_QUERY` | Query 端 |
| `RETRIEVAL_DOCUMENT` | 文件端 |
| `SEMANTIC_SIMILARITY` | 計算語意相似度 |
| `CLASSIFICATION` | 文字分類 |

**開源選擇：**
```python
from sentence_transformers import SentenceTransformer

# 中文強，多語言支援
model = SentenceTransformer('BAAI/bge-m3')
embeddings = model.encode(["句子1", "句子2"])

# 或用 HuggingFace
model = SentenceTransformer('intfloat/multilingual-e5-large')
```

---

### Embedding Fine-tuning

什麼時候需要 fine-tune embedding 模型？

**需要 fine-tune 的情況：**
- 你的 domain 非常特殊（醫療、法律、特定行業術語）
- 通用 embedding 在你的資料上 retrieval 效果差
- 你有足夠的 query-document relevance pair 資料

**Fine-tuning 方法：**
- Contrastive Learning（對比學習）：正例（相關 pair）距離拉近，負例距離推遠
- 使用 `sentence-transformers` 的 `MultipleNegativesRankingLoss`

**不需要 fine-tune 的情況（大多數 FDE 場景）：**
- 通用文件搜尋
- 多語言支援
- 快速上線需求

---

### Embedding 在 RAG 系統中的全局定位

```
原始文件
    ↓ (Chunking)
文字 Chunks
    ↓ (Embedding Model)
向量
    ↓ (Vector DB)
    ←←←←←←←←←←←←←←←
用戶 Query → Embedding → 向量 DB 搜尋 → Top-K Chunks → LLM Context
```

Embedding 的品質直接決定 retrieval 的品質。  
這就是為什麼選對 Embedding 模型、使用正確的 task_type、評估 retrieval recall，是 RAG 工程師的核心功課。

---

## 系列總結

九篇走完，這是整個 FDE 面試知識地圖的架構：

```
RAG 基礎（Part 1）
    ↓
RAG 深度技術（Part 5）：Chunking / Embedding / Vector DB / Hybrid Search
    ↓
RAG 進階（Part 6）：檢索失敗 / Grounding / 評估 / 成本

Agent 基礎（Part 2）
    ↓
Agent 深度設計（Part 7）：ReAct vs Planner / Tool Routing / Multi-Agent / Memory

ML 基礎（Part 8）：傳統 ML → Deep Learning → Transformer

LLM 核心（Part 9）：Token / Prompt Engineering / Embedding

System Design 實戰（Part 4）
```

這個地圖不是要你全部背下來。  
是要你在面試官問到任何一個節點時，能夠自然地往相鄰的節點延伸，而不是在那個節點就停住了。

**FDE 面試最終考的，是你有沒有把這些拼在一起的能力。**

---

*本系列已完結。如有特定主題想深入，歡迎留言。*
