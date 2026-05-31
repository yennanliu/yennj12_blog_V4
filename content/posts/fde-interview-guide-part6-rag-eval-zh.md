---
title: "FDE 面試準備指南（六）：RAG 進階——檢索失敗、Grounding、評估指標與成本控制"
date: 2026-05-31T09:30:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 RAG 系統的四大進階主題：檢索失敗的原因與修復、Grounding 策略、RAG 評估指標設計，以及生產環境中的成本控制"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "RAG", "Grounding", "Evaluation", "RAGAS", "Cost Control", "Interview", "Google"]
authors: ["yen"]
readTime: "14 min"
---

> RAG 跑起來很容易。  
> 讓它在生產環境穩定運行、能量化效果、還要控制成本——這才是難的。  
> 面試官想知道你有沒有這層意識。

---

## 一、檢索失敗：你的 RAG 為什麼沒找到正確答案

這是 RAG 系統最常見的實際問題，也是面試官最愛問的：

> *「你的 RAG 系統回答品質不好，你怎麼 debug？」*

---

### 檢索失敗的五大原因

**1. Query 和 Document 的語意空間不對齊**

用戶問的方式和文件寫的方式不同。

- 用戶問：「這個功能怎麼用？」
- 文件寫的是：「操作說明 3.2.1 節」

向量搜尋找不到，因為語意距離太遠。

**修復方式：**
- **HyDE（Hypothetical Document Embeddings）**：先讓 LLM 根據 query 生成一個假設答案，用假設答案的 embedding 去搜尋，而不是 query 本身
- **Query Rewriting**：讓 LLM 把用戶的問題改寫成更像文件的表述
- **Query Expansion**：生成多個 query 變體，分別搜尋後合併結果

**2. Chunk 切壞了**

答案跨越了 chunk 邊界。  
修復：調整 chunk overlap，或改用 Parent-Child chunking。

**3. Embedding 模型選錯**

模型的訓練域和你的資料域不匹配。  
例如：用通用 embedding 做法律文件搜尋，效果就差。  
修復：換 domain-specific embedding，或 fine-tune embedding 模型。

**4. Top-K 設太小**

正確答案在第 K+1 個位置。  
修復：增加 Top-K，或加 Reranker 重新排序。

**5. 資料本身有問題**

文件品質差、重複、過時、格式亂。  
修復：資料清洗 pipeline，定期更新索引。

---

### Retrieval Failure 的診斷方法

```
Step 1: 用 RAGAS 跑 Context Recall
→ 正確答案有沒有在 retrieved context 裡？

Step 2: 如果 Context Recall 低 → 檢索問題
→ 看 embedding 品質、chunk 設計、query 改寫

Step 3: 如果 Context Recall 高但答案還是錯 → Generation 問題
→ 看 prompt 設計、LLM 的 grounding 能力
```

---

## 二、Grounding 策略：讓 LLM 不要亂說話

Grounding 是指讓 LLM 的回答紮根於你提供的資料，而不是它自己的訓練知識。

面試官問：

> *「你怎麼防止 LLM 幻覺？你的 Grounding 策略是什麼？」*

---

### Grounding 的核心問題

LLM 有兩個知識來源：
1. 訓練時學到的知識（parametric knowledge）
2. 你 retrieve 到的 context（non-parametric knowledge）

當兩者衝突，或 context 不夠，LLM 就可能「自己補」——這就是幻覺。

---

### Grounding 策略

**1. Prompt 層的 Grounding 指令**

明確告訴 LLM：只根據以下資料回答。

```
你是一個企業知識庫助理。
請只根據以下 [CONTEXT] 的內容回答用戶問題。
如果 [CONTEXT] 中沒有足夠的資訊，請直接說「我沒有足夠資訊回答這個問題」，不要猜測。

[CONTEXT]
{retrieved_chunks}

[QUESTION]
{user_query}
```

**2. Citation（引用來源）**

要求 LLM 在回答中標明來源。  
不只讓答案可驗證，也讓 LLM 更傾向於「有根據地回答」。

```
請在回答中標明每個陳述的來源，格式為 [文件名, 段落 X]。
```

**3. Faithfulness Check（忠實度驗證）**

用另一個 LLM 或規則來驗證回答是否和 context 一致。  
RAGAS 的 `faithfulness` 指標就是做這件事。

**4. Abstain（拒絕回答）**

比壞答案更好的是誠實說不知道。  
設計 threshold：如果 retrieval score 低於某個值，就不生成答案，改回覆「找不到相關資訊」。

**5. Grounding with Google Search（外部搜尋）**

Vertex AI 的 Grounding with Google Search 功能，讓 LLM 在回答時可以查詢即時網頁資訊，並自動附上來源。  
適合：需要即時資訊的場景（新聞、市場動態）。

---

## 三、評估指標：你怎麼知道你的 RAG 有多好

面試官問：

> *「你怎麼衡量你的 RAG 系統效果？你用什麼 metric？」*

如果你答不出來，面試官會認為你只是在做 demo，沒有真正在生產環境跑過。

---

### RAG 的評估框架：RAGAS

RAGAS（Retrieval Augmented Generation Assessment）是最常用的 RAG 評估框架。

核心指標：

| 指標 | 評估什麼 | 計算方式 |
|------|---------|---------|
| **Context Recall** | Retrieved context 有沒有包含正確答案所需的資訊 | 正確答案的關鍵資訊有多少比例出現在 context 中 |
| **Context Precision** | Retrieved context 有多少是真正相關的 | 相關 chunk 佔所有 retrieved chunk 的比例 |
| **Faithfulness** | LLM 回答有沒有忠於 context | 回答中每個陳述有多少比例可以從 context 推導 |
| **Answer Relevancy** | 回答有沒有回答到問題 | 回答和問題的語意相關性 |

---

### 評估的兩個層次

**第一層：Component-level evaluation（元件層）**

分別評估 retrieval 和 generation：
- Retrieval: `Context Recall`, `Context Precision`, `MRR`, `NDCG`, `Hit Rate`
- Generation: `Faithfulness`, `Answer Relevancy`, `Answer Correctness`

**第二層：End-to-end evaluation（端對端）**

從用戶角度評估最終答案的品質：
- `Answer Correctness`（需要 ground truth）
- 人工評分（最準但最貴）
- LLM-as-judge（用 GPT-4 或 Gemini 當評判）

---

### LLM-as-Judge

沒有 ground truth？讓 LLM 來評：

```python
prompt = """
你是一個 RAG 系統評估專家。
請評估以下回答的品質（1-5分）：

問題：{question}
參考資料：{context}
系統回答：{answer}

評分標準：
- 5: 完全忠於資料，準確回答問題
- 3: 部分準確，有輕微偏差
- 1: 嚴重錯誤或幻覺

請給出分數和理由。
"""
```

**注意：** LLM-as-judge 有 position bias（傾向評高第一個選項）和 verbosity bias（傾向評長答案更好）。要用 multiple sampling 或 swap position 來校正。

---

### 線上指標（Production Metrics）

除了離線評估，生產環境還要監控：

| 指標 | 說明 |
|------|------|
| **Latency P50/P95/P99** | 用戶等待時間 |
| **Retrieval Latency** | 向量搜尋耗時 |
| **LLM Latency** | Generation 耗時 |
| **Token Usage** | Input/Output token 數，直接影響成本 |
| **Thumbs Up/Down Rate** | 用戶回饋，最直接的品質訊號 |
| **Fallback Rate** | 多少比例的問題觸發「找不到答案」 |
| **Citation Click Rate** | 用戶有沒有點進去驗證來源 |

---

## 四、成本控制：RAG 在生產環境的現實

面試官問：

> *「你的 RAG 系統，如果每天有 10 萬次查詢，你的成本估算是怎樣的？你有哪些控制成本的方法？」*

這題測的是你有沒有真正做過生產系統。

---

### RAG 的成本來自哪裡

```
Embedding Cost (Indexing)
+ Embedding Cost (Query, 即時)
+ Vector DB 儲存與查詢
+ Reranker 推理（如有）
+ LLM Generation Cost
= 總成本
```

**最大的成本通常是 LLM Generation**，因為 Output token 比 Input token 貴。

---

### 成本控制策略

**1. 選對 LLM**

不是所有問題都需要最強的模型。

```
簡單 FAQ 查詢 → Gemini Flash / GPT-3.5
複雜推理 → Gemini Pro / GPT-4o
```

實作 Router：先判斷問題複雜度，再決定用哪個模型。

**2. 控制 Context 長度**

送進 LLM 的 token 越多越貴。  
- 減少 Top-K（從 10 減到 5）
- 用 Contextual Compression 壓縮每個 chunk
- 設定 max_context_tokens 上限

**3. Caching（快取）**

同樣的問題不要重複呼叫 LLM。

- **Exact Match Cache**：完全相同的 query 直接回快取結果（Redis）
- **Semantic Cache**：語意相似的 query 也回快取（`GPTCache`、`Momento`）
  - 把 query embed，在快取裡搜尋語意相似的歷史 query
  - 相似度超過 threshold → 回快取答案

```python
# 語意快取示意
cache_key = embed(query)
cached = vector_cache.search(cache_key, threshold=0.95)
if cached:
    return cached.answer
else:
    answer = rag_pipeline(query)
    vector_cache.store(cache_key, answer)
    return answer
```

**4. Embedding 批次處理（Indexing 階段）**

建索引時用 batch embedding，而不是一次一個文件。  
API 成本通常相同，但可以減少網路 overhead 和 rate limit 風險。

**5. 分層儲存**

熱資料（常被查詢）放在向量 DB。  
冷資料（很少被查詢）考慮壓縮或不建索引。

**6. 監控 Token Budget**

設定每個 session 的 token 上限。  
超過上限時提示用戶，而不是繼續無限生成。

---

### 成本估算範例（給面試用）

假設：
- 每天 10 萬次查詢
- 每次 query embed：~1,000 tokens
- 每次 context：~2,000 tokens
- 每次 LLM output：~500 tokens

使用 Gemini 1.5 Flash：
```
Query Embedding: 100,000 × 1,000 tokens × $0.00002/1K = $2/day
LLM Input: 100,000 × 2,000 tokens × $0.000075/1K = $15/day
LLM Output: 100,000 × 500 tokens × $0.0003/1K = $15/day
Total: ~$32/day = ~$960/month
```

加上 cache hit rate 50%：
```
實際成本: ~$480/month
```

面試時能給出這個量級的估算，就已經比大多數候選人強了。

---

## 小結

這四個主題是 RAG 系統從「能跑」到「能上線」的距離：

| 主題 | 關鍵問題 |
|------|---------|
| 檢索失敗 | 為什麼找不到？HyDE / Query Rewriting / 資料品質 |
| Grounding | 怎麼讓 LLM 不亂說？Prompt 設計 / Citation / Abstain |
| 評估指標 | 怎麼量化效果？RAGAS / LLM-as-judge / 線上指標 |
| 成本控制 | 怎麼活到 Day 100？Model routing / Caching / Token budget |

---

## 下一篇

[FDE 面試準備指南（七）：Agent 深度設計——ReAct vs Planner、Tool Routing、Multi-Agent](/posts/fde-interview-guide-part7-agent-design-zh/)
