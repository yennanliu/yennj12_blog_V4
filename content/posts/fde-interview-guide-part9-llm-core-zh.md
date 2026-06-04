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

## 面試情境

> **面試官：**「你的 RAG 系統的 context budget 怎麼設計的？如果你要讓 LLM 做複雜推理，你用什麼 Prompting 技法？為什麼選 text-embedding-004 而不是 OpenAI 的 embedding？」

這三個問題把 Token、Prompt Engineering、Embedding 串在一起問，測的是你有沒有把這些工具整合進系統設計的意識。

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

**選型速查：**

| 模型 | 提供商 | 維度 | 特點 | 推薦場景 |
|------|--------|------|------|---------|
| `text-embedding-004` | Google | 768 | 支援 task_type，GCP 原生 | GCP 生態系 |
| `text-embedding-3-small` | OpenAI | 1536 | 成本低，混合雲 | 非 GCP 場景 |
| `BGE-M3` | BAAI | 1024 | 開源，多語言，中文強 | 中文為主 |
| `multilingual-e5-large` | MS | 1024 | 開源，多語言均衡 | 多語言均等場景 |

**`text-embedding-004` 的 task_type 設計：**

| Task Type | 使用場景 |
|-----------|---------|
| `RETRIEVAL_QUERY` | 用戶查詢問題（Query 端） |
| `RETRIEVAL_DOCUMENT` | 被索引的文件 Chunk（Document 端） |
| `SEMANTIC_SIMILARITY` | 計算兩段文字的語意相似度 |
| `CLASSIFICATION` | 文字分類任務 |

Query 和 Document 分開指定 task_type，讓兩者的 embedding 空間對齊，retrieval 效果通常優於兩者用相同 task_type。

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

## 面試官地雷題

**地雷 1：「CoT 和 ReAct 的差別是什麼？你什麼時候選哪個？」**

```
答：CoT（Chain-of-Thought）讓 LLM 在一次生成中展示推理步驟，
    但它不能執行外部工具，只能靠 LLM 自己的知識推理。
    ReAct 在 CoT 的基礎上加入 Tool Calling Loop——
    LLM 不只是想，還能執行動作、觀察結果、再繼續思考。
    
    選擇：
    純推理、不需要外部資料 → CoT（便宜，只需一次呼叫）
    需要查詢外部工具或即時資料 → ReAct
    兩者可以結合：ReAct 的 Thought 部分可以用 CoT 風格讓推理更清晰。
```

**地雷 2：「Self-Consistency 的代價是什麼？適合什麼場景？」**

```
答：Self-Consistency 對同一個問題跑 N 次（N 通常是 5-10 次），
    取最常出現的答案作為最終結果。
    代價：N 倍的 LLM 呼叫 = N 倍成本和延遲。
    適合：
    高風險的推理問題（數學、邏輯），答案正確性比成本更重要
    Batch 評估場景（離線跑，不在乎延遲）
    不適合：
    客服問答（Latency 敏感，成本敏感）
    需要創意的任務（取眾數反而消除多樣性）
```

**地雷 3：「Context Window 大了，就不需要 RAG 了嗎？（Gemini 1M token 的場景）」**

```
答：不能完全替代。原因有三：
    1. Lost-in-the-Middle：LLM 對 context 中間位置的資訊注意力顯著弱化，
       1M token 的 context 中間的資訊可能被「忽略」
    2. 成本：1M token 的 input 成本比 RAG 的 Top-5 chunks 高很多
    3. 延遲：處理 1M token 的 attention 計算遠慢於 retrieval
    適合「全文傳入」的場景：合約審查（整份合約都要看）、一次性文件分析。
    不適合「頻繁查詢同一知識庫」的場景：那還是 RAG 更划算。
```

---

## 面試回答完整示範

```
面試官問：「這三塊——Token、Prompt Engineering、Embedding——
         你在系統設計裡怎麼用？」

Token + Context Budget：
「設計 RAG 系統時，我會明確規劃 context budget：
 System Prompt 約 500 tokens，User Query 約 100 tokens，
 剩下的空間分給 Retrieved Chunks 和對話 History。
 Chunk Size 設多大、Top-K 取幾個，都是由 context budget 決定的，
 不是隨意設的。」

Prompt Engineering：
「對於需要多步推理的問題，我用 CoT——
 在 Prompt 加上『請一步步思考』讓 LLM 展示推理過程，
 這能顯著提升複雜問題的準確率。
 如果需要查外部資料，改用 ReAct——
 讓 LLM 的推理和 Tool Calling 交替進行。
 對準確率要求極高的場景，考慮 Self-Consistency——
 跑 5 次取眾數，但代價是 5 倍成本，要跟客戶確認 budget。」

Embedding 選型：
「GCP 環境我選 text-embedding-004，因為原生整合、支援 task_type。
 中文為主的知識庫，我會認真評估 BGE 系列的實際 recall@k，
 因為它在中文 benchmark 上明顯優於通用多語言模型。
 最終選型我不靠直覺——用客戶的真實資料跑 retrieval recall@5 比較。」
```

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

ML 基礎入門（Part 3）：Transformer / Embedding / Fine-tuning / 評估指標
    ↓
ML 基礎完整版（Part 8）：傳統 ML → Deep Learning → Transformer（更深）

LLM 核心（Part 9）：Token / Prompt Engineering / Embedding

System Design 實戰（Part 4）
```

這個地圖不是要你全部背下來。  
是要你在面試官問到任何一個節點時，能夠自然地往相鄰的節點延伸，而不是在那個節點就停住了。

**FDE 面試最終考的，是你有沒有把這些拼在一起的能力。**

---

*本系列已完結。如有特定主題想深入，歡迎留言。*
