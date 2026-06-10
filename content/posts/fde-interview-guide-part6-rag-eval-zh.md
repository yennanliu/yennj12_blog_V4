---
title: "FDE 面試準備指南（六）：RAG 進階——檢索失敗、Grounding、評估指標與成本控制"
date: 2026-05-31T09:30:00+08:00
draft: false
weight: 6
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

## 面試情境

> **面試官：**「你的 RAG 系統上線後，客戶反映回答品質下降了。你怎麼診斷問題在 Retrieval 還是 Generation？你用什麼指標量化 RAG 的品質？如果成本超出預算，你怎麼優化？」

這是 FDE 最貼近生產現實的考題——不是設計新系統，而是診斷一個已上線系統的問題。

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

```
Prompt 結構：
  你是一個 RAG 系統評估專家。
  請評估以下回答的品質（1-5分）：
  
  問題：{question}
  參考資料：{context}
  系統回答：{answer}
  
  評分標準：
  - 5：完全忠於資料，準確回答問題
  - 3：部分準確，有輕微偏差
  - 1：嚴重錯誤或幻覺
  
  請給出分數和理由。
```

**注意：** LLM-as-judge 有兩個 bias 要校正：

```
Position Bias：傾向評高第一個出現的選項
  校正方法：把同一組答案用不同順序送兩次，取平均

Verbosity Bias：傾向評更長的答案更好
  校正方法：在 Prompt 明確說明「長度不是評分標準」
```

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

```
Semantic Cache 流程：

  用戶 Query
       │
       ▼
  Embed Query → 向量
       │
       ▼
  搜尋 Cache（Vector Store）
       │
  ┌────┴────────────────────────────────────────┐
  │ 相似度 > 0.95？                              │
  ├── 是 → 直接回 Cache 的答案（跳過整個 Pipeline）│
  └── 否 → 走正常 RAG Pipeline → 存入 Cache       │
       └─────────────────────────────────────────┘

效果：語意相似的問題（「什麼是年假」vs「年假怎麼計算」）共享 cache
代價：Cache 的 embedding 查詢本身也有成本（但遠低於 LLM 呼叫）
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

## 面試官地雷題

**地雷 1：「Context Recall 和 Answer Relevancy 都高，但用戶還是說回答不好。可能是什麼問題？」**

```
答：Context Recall 高 = 正確資訊有被查出來。
    Answer Relevancy 高 = 回答和問題相關。
    但這兩個指標都沒有衡量「回答的完整性」。
    用戶投訴的「不好」可能是：
    1. 答案截斷了——相關資訊有，但沒有完整組合成完整回答
    2. 回答太技術性——內容正確但語言不適合目標受眾
    3. 沒有 actionable 的建議——問「怎麼申請年假」，只說了規定沒說流程
    這些是 RAGAS 指標捕捉不到的「體驗品質」問題，需要人工評估或更細粒度的指標。
```

**地雷 2：「HyDE 和 Query Rewriting 的差別是什麼？你什麼時候選哪個？」**

```
答：Query Rewriting 是把用戶的口語問題改寫成更像文件的表述，
    解決「用戶說法和文件說法不同」的問題。
    HyDE（Hypothetical Document Embedding）更進一步——
    讓 LLM 根據 Query 生成一個假設的答案文件，
    用這個假設文件的 embedding 去搜尋，而不是 Query 本身。
    差別：Query Rewriting 是改寫問題，HyDE 是生成假設答案。
    選擇：
    如果問題表述問題 → Query Rewriting（成本低）
    如果查詢和文件語意空間差距很大 → HyDE（效果更強，成本稍高）
```

**地雷 3：「LLM-as-judge 的分數可以直接拿來比較兩個系統嗎？」**

```
答：要謹慎。LLM-as-judge 有兩個 bias：
    Position bias（傾向評高第一個出現的答案）
    Verbosity bias（傾向評長答案更好）
    直接比較兩個系統時，如果評估 prompt 沒有控制這兩個 bias，
    比較結果可能不公平。
    正確做法：同一對答案送兩次（調換順序），取平均分；
    或者用一個「比較型」的 prompt（直接問哪個更好），
    而不是分別打分再比較。
```

---

## 面試回答完整示範

```
面試官問：「客戶說回答品質下降了，你怎麼處理？」

診斷（1 分鐘）：
「我會先用 RAGAS 跑一批測試問題，
 看 Context Recall 和 Faithfulness 各是多少。
 Context Recall 低 → Retrieval 有問題：
   可能是資料更新了但 Index 沒更新，
   或者 Embedding 模型對新加入的文件類型效果差。
 Context Recall 高但 Faithfulness 低 → Generation 問題：
   LLM 在 hallucinate，Grounding Prompt 可能被改過或者不夠強。」

根因修復（1 分鐘）：
「如果是 Retrieval 問題，我會先看最近有沒有新增文件類型——
 如果有，可能需要重新評估 Embedding 模型是否適合新的內容。
 如果是 Generation 問題，我會加強 Prompt 的 Grounding 指令，
 明確要求 LLM『只根據以下資料回答，資料不足請說不知道』，
 並加入 Citation 機制，讓每個回答都要引用具體的文件段落。」

成本控制（30 秒）：
「如果成本超出預算，第一個動作是加 Semantic Cache——
 相似的問題直接回快取，不過 LLM。
 第二個動作是把 FAQ 類的簡單問題路由到較便宜的模型（Flash 而不是 Pro）。
 這兩步通常可以把成本降 40-60%，而不影響複雜問題的回答品質。」
```

---

下一篇：[FDE 面試準備指南（七）：Agent 深度設計——ReAct vs Planner、Tool Routing、Multi-Agent](/posts/fde-interview-guide-part7-agent-design-zh/)
