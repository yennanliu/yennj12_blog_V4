---
title: "AI 工程從零開始｜Phase 11 Part 2：RAG 系統與 LLM 評估 — 生產落地的最後一哩"
date: 2026-06-21T20:00:00+08:00
draft: false
weight: 23
description: "深入解析 RAG 架構設計：向量資料庫選型、Hybrid Search、Re-ranking、Chunking 策略，以及 LLM 評估框架：RAGAS/G-Eval/LLM-as-Judge"
categories: ["engineering", "ai", "all"]
tags: ["AI", "LLM", "RAG", "Vector Database", "Evaluation", "LLM Engineering", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師遇到 LLM 幻覺，第一反應是把 Prompt 寫得更長、更詳細。*
> *正確答案是：建立 RAG 管線讓模型說「我不知道」，而非瞎猜。*
> *大多數團隊上線後才發現回答品質不穩，因為沒有評估管線。*
> *正確答案是：在 CI/CD 中門控 Faithfulness ≥ 0.80，讓壞版本無法部署。*

---

## 面試情境

> 你們公司的法律文件問答系統上線三個月，客服每週回報大約 15% 的回答「聽起來合理但內容有誤」。CTO 要你在四週內把幻覺率降到 5% 以下，且 P95 延遲不能超過 2 秒。請說明你會怎麼診斷現況、選擇改進方向，以及如何證明改善確實發生了。

---

## 一、核心問題：LLM 幻覺與知識截止日期的工程解法

LLM 有兩個先天限制，工程師必須正視：

**幻覺（Hallucination）** — 模型會以高信心度生成看起來合理但事實上錯誤的內容。根源在於訓練目標是「預測下一個 Token」，而非「陳述事實」。當問題超出訓練分布，模型不會說「我不確定」，而是繼續生成流暢但錯誤的文字。

**知識截止日期（Knowledge Cutoff）** — 模型訓練資料有時間邊界。2024 年底截止的模型不知道 2025 年的法規修訂、產品更新、或內部文件。無論 Prompt 寫得多好，模型都無法回答它從未見過的資訊。

**RAG（Retrieval-Augmented Generation）** 是主流工程解法：把外部知識庫的相關片段即時檢索出來，附加在 Prompt 中，讓模型「有所依據地回答」而非憑空捏造。

但 RAG 帶來新問題：檢索品質如何保證？回答是否忠實於檢索內容？這需要**評估管線**來量化和監控。

---

## 二、三個演進階段（POC / MVP / Scale）

### ╔══ Phase 1：POC / < 1K 文件 ══╗

**目標**：兩週內驗證 RAG 在這個領域是否可行。

```
┌─────────────────────────────────────────────────────┐
│  Phase 1 RAG 架構（POC）                             │
│                                                     │
│  PDF / Markdown  ──▶  固定 512 Token Chunking        │
│                              │                      │
│                              ▼                      │
│                    ┌──────────────────┐             │
│                    │  Chroma / SQLite │  (本機)      │
│                    │  Dense Vector    │             │
│                    └────────┬─────────┘             │
│                             │  Top-K ANN            │
│                             ▼                       │
│                    ┌──────────────────┐             │
│                    │  LLM（API）       │             │
│                    │  GPT-4o / Claude │             │
│                    └──────────────────┘             │
└─────────────────────────────────────────────────────┘
```

| 項目 | 數值 |
|------|------|
| 文件量 | < 1K docs |
| 向量 DB | Chroma（本機，免費）|
| Embedding | text-embedding-3-small（$0.00002/1K token）|
| 評估方式 | 人工抽查 20 筆 |
| 建置時間 | 2–3 天 |

**解決的問題**：驗證端到端可行性，取得利害關係人信任。  
**遺留的問題**：無法處理專有名詞（BM25 稀疏缺失）、Chunking 切斷上下文、無系統化評估。

---

### ╔══ Phase 2：MVP / 1K–100K 文件 ══╗

**目標**：生產安全、Faithfulness ≥ 0.80、P95 < 1.5s。

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 2 RAG 架構（MVP）                                      │
│                                                              │
│  ┌────────────┐    ┌─────────────┐    ┌──────────────────┐  │
│  │  Document  │───▶│  Semantic   │───▶│  Pgvector /      │  │
│  │  Loader    │    │  Chunking   │    │  Weaviate        │  │
│  └────────────┘    └─────────────┘    └────────┬─────────┘  │
│                                                │             │
│  使用者問題 ─────────────────────────────────▶ │             │
│       │                                        │             │
│       ├──▶ Dense Embedding ──▶ ANN Search ─────┤             │
│       │                                        │             │
│       └──▶ BM25 Index ──────▶ Keyword Search ──┤             │
│                                                │             │
│                              ┌─────────────────▼──────────┐ │
│                              │  RRF Fusion（Hybrid）       │ │
│                              └──────────────┬─────────────┘ │
│                                             │               │
│                              ┌──────────────▼─────────────┐ │
│                              │  LLM 生成 + RAGAS 評估      │ │
│                              └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

| 項目 | 數值 |
|------|------|
| 文件量 | 1K–100K docs |
| 向量 DB | Pgvector（已有 PostgreSQL）或 Weaviate |
| Search | Hybrid（BM25 + Dense，RRF Fusion）|
| 評估 | RAGAS 自動化，Faithfulness / Relevancy |
| 建置時間 | 2–3 週 |

**解決的問題**：Recall@5 比 Phase 1 提升 ~12%，專有名詞命中率改善，有量化評估基準。  
**遺留的問題**：高風險查詢（法律條文、數字對比）需要更精準的 Re-ranking；百萬文件時 ANN 精度下降。

---

### ╔══ Phase 3：Scale / 100K+ 文件 ══╗

**目標**：企業級，自動化評估 CI/CD 門控，多索引分片，P95 < 2s @ 500 QPS。

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3 RAG 架構（Scale）                                       │
│                                                                 │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  Doc Ingestion│  │  Index Manager │  │  Multi-index     │   │
│  │  Pipeline    │─▶│  (by doc type) │─▶│  Shard A / B / C │   │
│  └──────────────┘  └────────────────┘  └────────┬─────────┘   │
│                                                  │              │
│  Query ──▶ Query Router ──────────────────────▶  │              │
│                │                                 │              │
│                ├──▶ Dense Retriever ─────────────┤              │
│                └──▶ Sparse Retriever ────────────┤              │
│                                                  │              │
│                         ┌────────────────────────▼───────────┐ │
│                         │  Cross-Encoder Re-ranker           │ │
│                         │  (Top-50 → Top-5, +80ms)           │ │
│                         └────────────────┬───────────────────┘ │
│                                          │                      │
│                         ┌────────────────▼───────────────────┐ │
│                         │  LLM 生成                           │ │
│                         └────────────────┬───────────────────┘ │
│                                          │                      │
│                         ┌────────────────▼───────────────────┐ │
│                         │  RAGAS Eval → CI/CD Gate            │ │
│                         │  Faithfulness ≥ 0.80 才可部署        │ │
│                         └────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

| 項目 | 數值 |
|------|------|
| 文件量 | 100K+ docs |
| 向量 DB | Weaviate / Pinecone（托管，自動 Shard）|
| Re-ranker | Cross-Encoder（+80ms，MRR@10 +15%）|
| 評估 | RAGAS + LLM-as-Judge，CI/CD 自動門控 |
| 成本 | ~$0.008/query（含 Re-rank + Eval）|

---

## 三、RAG 管線設計：Indexing vs Query 兩階段

RAG 系統分為兩條獨立管線，時序不同、瓶頸不同。

```
┌─────────────────────────────────────────────────────────────────┐
│  Indexing Pipeline（離線，批次處理）                              │
│                                                                 │
│  Raw Docs                                                       │
│     │                                                           │
│     ▼  ~5ms/doc                                                 │
│  Document Loader（PDF/HTML/Markdown parser）                    │
│     │                                                           │
│     ▼  ~10ms/doc                                                │
│  Text Splitter（Chunking strategy）                             │
│     │                                                           │
│     ▼  ~20ms/chunk（API call）                                  │
│  Embedder（text-embedding-3-small or BGE-M3）                   │
│     │                                                           │
│     ▼  ~2ms/chunk                                               │
│  Vector Store（Upsert + BM25 Index 更新）                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Query Pipeline（線上，即時）                                     │
│                                                                 │
│  User Question                                                  │
│     │                                                           │
│     ▼  ~15ms                                                    │
│  Query Embedder（同 Indexing 的模型）                            │
│     │                                                           │
│     ├──▶ ANN Search（~30ms，Top-50 候選）                        │
│     └──▶ BM25 Keyword Search（~5ms）                            │
│                │                                                │
│                ▼  ~5ms                                          │
│         RRF Fusion（合併兩路結果）                               │
│                │                                                │
│                ▼  ~80ms（選用）                                  │
│         Cross-Encoder Re-ranker（Top-50 → Top-5）               │
│                │                                                │
│                ▼  ~600ms（含網路）                               │
│         LLM 生成（with context）                                 │
│                │                                                │
│                ▼  總計 P95 ~750ms（無 Re-rank）                  │
│                    P95 ~1,800ms（含 Re-rank）                    │
└─────────────────────────────────────────────────────────────────┘
```

**各階段延遲細節**：

| 階段 | P50 延遲 | P95 延遲 | 可並行？ |
|------|---------|---------|---------|
| Query Embedding | 12ms | 18ms | 否 |
| ANN Search | 20ms | 45ms | 可與 BM25 並行 |
| BM25 Search | 3ms | 8ms | 可與 ANN 並行 |
| RRF Fusion | 1ms | 2ms | 否 |
| Cross-Encoder Re-rank | 60ms | 120ms | 否 |
| LLM Generation | 400ms | 1,200ms | 否 |

---

## 四、Chunking 策略：Fixed / Semantic / Hierarchical 的取捨

Chunking 是 RAG 效果最容易被低估的變數。切太小丟失上下文，切太大引入雜訊。

### Fixed-size Chunking

每 512 Token 切一段，允許 64 Token overlap。

**優點**：實作簡單，索引速度快（~5ms/chunk）。  
**缺點**：機械切割，句子可能被截斷；「根據第三條…」的前半段與「…應視為無效」的後半段被分到不同 Chunk，導致語意破碎。

適用情境：同質性高的短文件（FAQ、商品說明）。

### Semantic Chunking

依句子邊界和段落結構切割，計算相鄰句子的 Embedding 相似度，在語意不連貫處切分。

**優點**：Chunk 語意完整，Faithfulness 提升 ~8%。  
**缺點**：多一次 Embedding 計算，Indexing 成本 +20ms/chunk；Chunk 長度不固定，需設上限（建議 800 Token 上限）。

適用情境：法律文件、技術手冊、學術論文。

### Hierarchical Chunking（Parent-Child）

建立兩層索引：Parent Chunk（1,024 Token，保留完整段落語意）和 Child Chunk（256 Token，精細化搜尋）。

查詢時用 Child Chunk 命中，但傳給 LLM 的是對應的 Parent Chunk。

**優點**：兼顧搜尋精度（細粒度）與上下文完整性（粗粒度）；Recall@5 最高。  
**缺點**：索引大小 ~2x，查詢邏輯更複雜，維護成本高。

適用情境：高準確度要求、法規/合約問答。

### Chunking 策略比較表

| 策略 | Indexing 速度 | Recall@5 | Faithfulness | 實作複雜度 | 適合文件量 |
|------|-------------|---------|-------------|---------|---------|
| Fixed-size | 快（~5ms/chunk）| 0.71 | 0.72 | 低 | < 10K |
| Semantic | 中（~25ms/chunk）| 0.78 | 0.80 | 中 | 10K–100K |
| Hierarchical | 慢（~40ms/chunk）| 0.84 | 0.87 | 高 | 100K+ |

---

## 五、Hybrid Search：BM25 + Dense 向量的融合

Pure Dense Vector Search 對**精確關鍵字**（產品型號、法條編號、人名）命中率差；BM25 對**語意相似**（「退款」vs「退費申請」）命中率差。Hybrid Search 融合兩者優點。

```
┌─────────────────────────────────────────────────────────────────┐
│  Hybrid Search 架構                                              │
│                                                                 │
│  Query: "第14條第2款的違約金上限"                                │
│     │                                                           │
│     ├──────────────────────────────────────┐                   │
│     │                                      │                   │
│     ▼                                      ▼                   │
│  ┌─────────────────┐            ┌─────────────────┐           │
│  │  BM25 Index     │            │  Dense Vector   │           │
│  │  (Sparse)       │            │  Index (ANN)    │           │
│  │                 │            │                 │           │
│  │  精確：第14條    │            │  語意：違約金    │           │
│  │  Rank: [3,7,12] │            │  Rank: [1,4,9]  │           │
│  └────────┬────────┘            └────────┬────────┘           │
│           │                              │                     │
│           └──────────────┬───────────────┘                     │
│                          │                                     │
│                          ▼                                     │
│               ┌──────────────────┐                             │
│               │  RRF Fusion      │                             │
│               │  score = Σ 1/(k+r)│                            │
│               │  k=60（標準值）   │                             │
│               └──────────┬───────┘                             │
│                          │                                     │
│                          ▼                                     │
│               Top-5 Merged Results                             │
└─────────────────────────────────────────────────────────────────┘
```

### Reciprocal Rank Fusion（RRF）公式

每個文件的 RRF 分數：

```
RRF_score(d) = Σ_r  1 / (k + rank_r(d))
```

- `k = 60`（常數，防止高排名文件過度主導）
- `rank_r(d)`：文件 d 在第 r 路檢索結果中的排名
- 對 BM25 結果和 Dense 結果各算一次，加總後重新排序

**實際效果**：  
- Dense-only Recall@5：0.71  
- Hybrid Recall@5：0.83（**+12 個百分點**）  
- 專有名詞（型號、條號）命中率：0.54 → 0.79（+25pp）

### 何時用哪種搜尋

| 場景 | 建議策略 | 原因 |
|------|---------|------|
| FAQ / 客服知識庫 | Dense-only | 問題語意多樣，BM25 幫助有限 |
| 法律 / 技術文件 | Hybrid | 條號、術語需要精確匹配 |
| 程式碼搜尋 | Hybrid | 函數名稱是精確字串 |
| 多語言（中英混搭）| Hybrid | Dense 處理語意，BM25 處理英文術語 |
| < 1K 文件 | Dense-only | BM25 索引維護成本不划算 |

---

## 六、Re-ranking：Cross-Encoder 精排的工程成本

### Bi-Encoder vs Cross-Encoder

**Bi-Encoder**（現有的 Embedding Model）：Query 和 Document 各自 Encode，計算 Cosine Similarity。速度快（~5ms），但因為 Query 和 Document 獨立編碼，無法捕捉深層交互語意。

**Cross-Encoder**：把 Query + Document **拼接**後一起輸入模型，輸出一個相關性分數。能捕捉細粒度的語意交互，但每對 (Query, Doc) 都要跑一次前向傳播，Top-50 候選就要跑 50 次，+80ms 延遲。

```
Bi-Encoder：
  E(Query)  ──▶ [0.2, 0.8, 0.4, ...]
  E(Doc)    ──▶ [0.3, 0.7, 0.5, ...]
  Score = cosine_sim(E_q, E_d)  ← 快但粗糙

Cross-Encoder：
  [CLS] Query [SEP] Document [SEP]  ──▶  Score: 0.91  ← 慢但準確
```

### ColBERT：中間路線

ColBERT 保留 Token 層級的向量（而非池化成單一向量），用 MaxSim 計算分數。延遲約 +25ms，精度介於 Bi-Encoder 和 Cross-Encoder 之間。適合 QPS 高但仍需要比 Bi-Encoder 更好準確度的場景。

### Re-ranking 成本效益分析

| 方案 | 額外延遲 | MRR@10 提升 | 適合場景 |
|------|---------|-----------|---------|
| 無 Re-ranking | +0ms | 基準 | 低風險、高 QPS（> 200）|
| ColBERT | +25ms | +8% | 平衡選擇，QPS 50–200 |
| Cross-Encoder | +80ms | +15% | 高風險查詢、QPS < 50 |
| Cross-Encoder (GPU) | +20ms | +15% | 大流量 + 高準確度（昂貴）|

**Re-ranking 值得投入的信號**：
- 當前 Faithfulness < 0.80（Re-ranking 是提升品質最直接的槓桿）
- 查詢是高風險類型（法規、醫療、財務）
- QPS < 100（延遲預算夠用）

---

## 七、LLM 評估框架：RAGAS / G-Eval / LLM-as-Judge

「如果你無法量化它，你就無法改善它。」評估框架是 RAG 系統的品質護欄。

### RAGAS（RAG Assessment）

RAGAS 是針對 RAG 系統設計的自動化評估框架，核心四個指標：

| 指標 | 定義 | 計算方式 | 目標值 |
|------|------|---------|-------|
| **Faithfulness** | 回答是否有事實依據於檢索內容 | LLM 將回答拆句，判斷每句是否能從 Context 推導 | ≥ 0.80 |
| **Answer Relevancy** | 回答是否切題（有無廢話）| 從回答反向生成問題，和原問題算相似度 | ≥ 0.75 |
| **Context Precision** | 檢索到的 Chunk 有多少是真正有用的 | 有用 Chunk / 總 Chunk 數 | ≥ 0.70 |
| **Context Recall** | 黃金答案所需的資訊有多少被檢索到 | 需要標注 Ground Truth | ≥ 0.75 |

**RAGAS 成本**：每筆評估約 $0.003（GPT-4o 為評判模型）；若改用 GPT-4o-mini 降至 $0.0004/筆，但準確度下降 ~6%。

### G-Eval

G-Eval 使用 Chain-of-Thought 讓 LLM 先**解釋評分理由**再給分，對齊人類評審的方式更接近。

流程：
1. 定義評估標準（Faithfulness 的 1–5 分定義）
2. 讓 LLM 生成 CoT 推理：「這個回答引用了 Context 的第二段，但第三句話沒有來源…」
3. 基於 CoT 輸出分數

**G-Eval 與人類評審一致率**：Pearson 相關係數 ~0.82（RAGAS 約 0.74）。

### LLM-as-Judge

把 LLM 當作評審，直接判斷「這個回答對不對」。實務設計要點：

1. **Prompt 設計**：給定評分 Rubric（1=完全錯誤，5=完全正確），加入 Few-shot 範例
2. **位置偏差（Position Bias）**：LLM 傾向給第一個選項高分；解法是 A/B 互換後平均
3. **自我增強偏差**：GPT-4o 評估 GPT-4o 輸出會偏高；考慮用不同家族模型交叉評估
4. **成本**：GPT-4o-mini 評估，~$0.002/筆，批次處理可降至 $0.0008/筆

**LLM-as-Judge vs 人類評審一致率（二元判斷：對/錯）**：~85%，適合做初篩；最終高風險樣本仍需人工複審。

### CI/CD 評估門控實作

```
# 偽代碼：GitHub Actions 評估門控
評估集：500 筆 QA pairs（每週更新）
觸發時機：每次 PR 合併到 main

if RAGAS_faithfulness < 0.80:
    block deployment
    notify #ai-eng-alerts

if answer_relevancy < 0.75:
    block deployment

if p95_latency > 2000ms:
    block deployment
```

**建立評估集的三個來源**：  
1. 客服歷史問題 + 人工標注答案（最貴但最準）  
2. 從文件自動生成（RAGAS `TestsetGenerator`，$0.01/筆）  
3. 生產流量採樣 + LLM-as-Judge 自動標注

---

## 八、為什麼選 X 不選 Y（6 個關鍵決策）

### 決策 1：Hybrid Search vs Dense-only

| 面向 | Hybrid Search | Dense-only | Flip Condition |
|------|-------------|-----------|---------------|
| Recall@5 | 0.83（+12%）| 0.71 | 文件純語意、無專有名詞 → Dense-only 夠用 |
| 維護複雜度 | 高（兩套索引）| 低 | 資源有限的小團隊 → Dense-only |
| 成本 | 略高（BM25 存儲）| 低 | 預算緊張 → Dense-only |
| 專有名詞命中 | 優秀 | 差 | 無專有名詞場景 → Dense-only |

### 決策 2：Cross-Encoder Re-ranker vs Bi-Encoder

| 面向 | Cross-Encoder | Bi-Encoder | Flip Condition |
|------|-------------|-----------|---------------|
| MRR@10 | +15% 提升 | 基準 | QPS > 200，無法承受 +80ms → Bi-Encoder |
| 延遲 | +80ms | +0ms | P95 預算 < 1s → 跳過 Re-ranking |
| 高風險查詢 | 必要 | 不足 | 低風險 FAQ → Bi-Encoder 夠用 |
| GPU 加速 | +20ms | N/A | 有 GPU 資源 → Cross-Encoder 划算 |

### 決策 3：Pgvector vs Pinecone vs Weaviate

| 面向 | Pgvector | Pinecone | Weaviate |
|------|---------|---------|---------|
| 最適文件量 | < 5M vectors | 5M–500M | 1M–100M |
| 成本 | 最低（已有 PG）| 最高（$70+/mo）| 中等 |
| Hybrid 支援 | 需自建 BM25 | 內建 | 內建 |
| 維護負擔 | 高（自管）| 零（托管）| 中 |
| **Flip Condition** | 超過 5M vectors 或需托管 → Pinecone | 成本敏感 + 已有 PG → Pgvector | 需要 Hybrid 且不想用 Pinecone → Weaviate |

### 決策 4：RAGAS vs 自定義評估指標

| 面向 | RAGAS | 自定義指標 |
|------|-------|---------|
| 上手速度 | 快（1 天）| 慢（2–3 週）|
| 領域適配 | 通用，可能不符行業 | 完全客製 |
| 與人類一致率 | ~74% | 依實作而定 |
| 維護成本 | 低（開源維護）| 高 |
| **Flip Condition** | 高度專業領域（醫療法規）且通用指標失準 → 自定義 |

### 決策 5：Hierarchical Chunking vs Fixed-size

| 面向 | Hierarchical | Fixed-size |
|------|------------|-----------|
| Recall@5 | 0.84 | 0.71 |
| Faithfulness | 0.87 | 0.72 |
| 索引大小 | ~2x | 1x |
| 實作複雜度 | 高 | 低 |
| **Flip Condition** | 文件 < 5K 且 Fixed-size Faithfulness > 0.80 → Fixed-size 夠用 |

### 決策 6：LLM-as-Judge vs 人工評估

| 面向 | LLM-as-Judge | 人工評估 |
|------|------------|---------|
| 成本 | $0.002/筆 | $0.5–2/筆 |
| 速度 | 批次 1K 筆/分鐘 | 人工 10–20 筆/小時 |
| 一致率 | ~85% vs 人類 | 人與人 ~90% |
| 偏差風險 | 存在（需設計緩解）| 低 |
| **Flip Condition** | 高風險決策（上市文件審查）→ 人工評估；日常品質監控 → LLM-as-Judge |

---

## 九、系統效應：Naive RAG vs Advanced RAG 量化比較

| 指標 | Naive RAG（Phase 1）| Advanced RAG（Phase 3）| 改善幅度 |
|------|-------------------|---------------------|---------|
| 幻覺率（Hallucination）| 15% | 4% | **−73%** |
| Faithfulness Score | 0.65 | 0.89 | +37% |
| Answer Relevancy | 0.68 | 0.83 | +22% |
| Context Precision | 0.55 | 0.78 | +42% |
| Context Recall | 0.60 | 0.81 | +35% |
| Recall@5 | 0.71 | 0.83 | +17% |
| P95 Latency | 850ms | 1,800ms | −（+112%，因 Re-rank）|
| Cost per Query | $0.004 | $0.008 | +100% |
| 客服轉人工率 | 38% | 14% | **−63%** |
| 每月維護工時 | 20h（人工抽查）| 8h（自動化 + 偶發告警）| −60% |

**重要 Trade-off**：Advanced RAG 的延遲比 Naive RAG 高（因為 Re-ranking），需要確保 P95 在 SLA 內（本案例 2 秒）。如果延遲預算緊張，可考慮跳過 Re-ranking，用 Hybrid Search + 好的 Chunking 也能達到 Faithfulness 0.82。

---

## 十、面試答題要點

> *「面對法律問答系統的 15% 幻覺率，我會按三個階段處理。第一步是診斷：部署 RAGAS 對現有流量抽樣評估，確認問題出在 Retrieval 端（Recall 低）還是 Generation 端（Faithfulness 低）。如果 Context Recall < 0.70，優先升級為 Hybrid Search（BM25 + Dense + RRF），這是單一改動 Recall@5 提升最大的槓桿，我們的數據顯示 +12 個百分點。如果 Faithfulness < 0.75，加入 Cross-Encoder Re-ranking，代價是 +80ms 延遲但 MRR@10 提升 15%；同時把 Chunking 從 Fixed-size 換成 Semantic，Faithfulness 可再提升 8%。第三步是防守：在 CI/CD 中加入 RAGAS 自動評估門控，Faithfulness < 0.80 的版本無法部署，每月維護工時從 20 小時降到 8 小時。綜合這三項改動，目標是把幻覺率從 15% 降到 4%、Faithfulness 從 0.65 提升到 0.89，並在四週內完成。」*

---

## 十一、生產常見問題與診斷流程

即使架構設計完善，生產環境仍會出現各種品質退化。以下是最常見的五個問題及對應的診斷鏈。

### 問題 1：Faithfulness 突然下降（0.85 → 0.70）

**觀測信號**：RAGAS Dashboard 顯示 Faithfulness 7 日均值跌破門檻，Slack 告警觸發。

**診斷鏈**：

```
Faithfulness 下降
    │
    ├── 查看同期是否有文件大批更新
    │       │
    │       └── 是 → 新文件 Chunking 是否破壞語意？
    │                   抽樣 20 筆，人工確認 Chunk 邊界
    │
    ├── 查看 Context Precision 是否也下降
    │       │
    │       └── 是 → 檢索品質問題，ANN Index 是否重建失敗？
    │               檢查 Embedding 模型版本是否被更改
    │
    └── Context Precision 正常，Faithfulness 仍低
            │
            └── LLM 模型本身問題（API 版本更新？Temperature 設定改變？）
                抽樣對比：舊版 vs 新版輸出
```

**常見根因**：  
- 文件更新後未重建索引（Stale Index，佔 40% 案例）  
- Embedding 模型靜默升級，向量空間不一致（佔 25%）  
- LLM System Prompt 被意外修改（佔 20%）  
- 新增了不相關文件污染索引（佔 15%）

### 問題 2：P95 延遲從 1.2s 飆升到 3.5s

**觀測信號**：APM（Datadog / Grafana）顯示 p95_latency_ms 持續超過 SLA。

**診斷步驟**：

| 步驟 | 檢查項目 | 工具 |
|------|---------|------|
| 1 | 哪一層慢？Embedding / ANN / Re-rank / LLM？| Distributed Trace |
| 2 | ANN Search 延遲是否隨文件量線性增長？| Vector DB Metrics |
| 3 | Cross-Encoder Re-ranker 是否有 Cold Start？| Container Logs |
| 4 | LLM API 上游是否有壅塞？| LLM Provider Status Page |

**常見解法**：  
- ANN Index 碎片化 → 觸發 HNSW Index Rebuild（離線執行）  
- Re-ranker 沒有 Keep-Alive → 改用連接池，-40ms  
- Candidate Set 太大（Top-100 Re-rank）→ 縮減至 Top-30，-35ms  

### 問題 3：Context Recall 低（< 0.65）— 找不到該找到的文件

**根因分析**：

1. **Embedding 模型與文件語言不匹配**：中文文件用英文優化的 Embedding 模型，召回率可能低 20–30%。解法：改用 BGE-M3（多語言，MTEB 中文排名前 3）。

2. **Chunk 過小（< 128 Token）**：資訊被稀釋，每個 Chunk 的語意信號不夠強。解法：調整 Chunk size 至 384–512 Token。

3. **K 值設太小**：只取 Top-3 候選，但相關文件排在第 4。解法：Top-K 調為 10，Re-ranker 後取 Top-3。

4. **缺乏 Metadata 過濾**：使用者問「2024年的條款」，但索引沒有年份 Metadata，無法有效過濾。解法：Indexing 時提取 Metadata，Query 時加入 Pre-filter。

### 問題 4：Answer Relevancy 低 — 回答正確但答非所問

此問題通常不在 Retrieval 端，而在 **Prompt 設計**端。

**常見原因**：  
- System Prompt 過於開放（「請盡可能詳細回答」）→ 模型生成大量無關背景資訊  
- 沒有明確要求「如果 Context 中沒有答案，請說不知道」→ 模型開始幻想  
- Context Window 太多無關 Chunk（Context Precision 低）→ 模型被干擾

**修復步驟**：

```
# Prompt 優化前
"根據以下文件回答問題：{context}\n問題：{question}"

# Prompt 優化後
"你是法律文件助理。請嚴格根據以下 Context 回答問題。
如果 Context 中沒有足夠資訊，請直接說「根據現有文件無法確認」，
不要猜測或補充 Context 以外的資訊。

Context：
{context}

問題：{question}

請給出簡潔、直接的回答（3句以內）。"
```

修改後 Answer Relevancy 通常可提升 0.08–0.15。

### 問題 5：評估集過時，RAGAS 分數虛高

評估集是 6 個月前建立的，但文件已大幅更新，導致評估分數不反映真實品質。

**評估集更新策略**：

| 觸發條件 | 動作 |
|---------|------|
| 文件更新 > 20% | 從新文件重新生成 30% 評估集 |
| 每季 | 從生產查詢採樣 100 筆加入評估集 |
| 客服投訴 spike | 立即將投訴問題加入評估集 |
| 模型升級 | 全量重跑評估，確認分數不退步 |

---

## 十二、Embedding 模型選型：開源 vs 閉源

Embedding 模型的選擇直接影響召回品質和成本結構。

```
┌───────────────────────────────────────────────────────────────────┐
│  Embedding 模型選型決策樹                                          │
│                                                                   │
│  文件語言？                                                        │
│      │                                                            │
│      ├── 純英文 ──▶  text-embedding-3-large（OpenAI）             │
│      │               或 E5-large-v2（開源，MTEB 頂尖）             │
│      │                                                            │
│      ├── 中英混合 ──▶  BGE-M3（開源）                              │
│      │                或 text-embedding-3-small（閉源，多語言）    │
│      │                                                            │
│      └── 高隱私需求（不能送出 API）──▶  BGE-M3 自部署              │
│                                          或 E5-mistral-7b-instruct│
└───────────────────────────────────────────────────────────────────┘
```

### 主流 Embedding 模型比較

| 模型 | 維度 | MTEB 中文 | 成本 | 自部署 | 適合場景 |
|------|-----|---------|------|-------|---------|
| text-embedding-3-small | 1,536 | 良 | $0.00002/1K token | 否 | 快速原型，成本敏感 |
| text-embedding-3-large | 3,072 | 優 | $0.00013/1K token | 否 | 高準確度，英文為主 |
| BGE-M3 | 1,024 | 頂尖 | $0（自部署）| 是 | 中文為主，隱私要求高 |
| E5-large-v2 | 1,024 | 良 | $0（自部署）| 是 | 英文，低成本 |
| Cohere embed-v3 | 1,024 | 優 | $0.0001/1K token | 否 | 多語言，含壓縮模式 |

**自部署 BGE-M3 成本估算**（中等規模）：  
- 1 台 A10G GPU（4 vCPU, 24GB VRAM）：~$1.5/hr（AWS g5.xlarge）  
- 日均 200K 次 Embedding 查詢：~$36/day vs text-embedding-3-small $4/day  
- 建議：< 500K queries/day 用閉源 API 更划算；超過後自部署開始有優勢

### Embedding 維度壓縮（Matryoshka Representation Learning）

OpenAI text-embedding-3 系列支援 MRL，可將 1,536 維向量壓縮為 256 維，犧牲 3–5% 精度但：

- 儲存成本降低 83%（1,536 → 256 維）
- ANN Search 速度提升 ~4x
- 適合 Phase 1–2 的成本優先場景

---

## 附錄：RAG 系統健康度檢查清單

在每次重要版本上線前，確認以下 15 個檢查項目：

**Indexing 管線**  
- [ ] 文件格式全部被 Loader 正確解析（PDF 表格、圖片 OCR）  
- [ ] Chunk 邊界抽樣確認，無句子被截斷超過 20%  
- [ ] Embedding 模型版本鎖定，不受 API 靜默升級影響  
- [ ] BM25 Index 與 Vector Index 同步，無 Stale 文件  
- [ ] Metadata（來源、日期、類別）正確存入，支援 Pre-filter  

**Query 管線**  
- [ ] Hybrid Search RRF 融合正常，兩路結果都有貢獻  
- [ ] Re-ranker 服務健康檢查通過，P99 延遲 < 150ms  
- [ ] Context Window 不超過 LLM 上限（保留 1K Token 給輸出）  
- [ ] 空結果處理：當 Recall 為 0，回傳固定的「找不到相關資訊」而非幻想  

**評估管線**  
- [ ] RAGAS 評估集版本與當前文件同步（< 30 天舊）  
- [ ] CI/CD Gate 設定正確：Faithfulness < 0.80 確實 Block 部署  
- [ ] Faithfulness / Relevancy / Latency 三項 Dashboard 在 Grafana 可見  
- [ ] 每週抽樣 50 筆生產查詢加入評估集滾動更新  

**成本控制**  
- [ ] 每查詢成本上限設定（建議 $0.01/query 為警戒線）  
- [ ] LLM API Rate Limit 監控，避免突發流量超限導致降級

---

*本文為「AI 工程從零開始」系列第 23 篇。*

---

## 系列導航

← [Phase 11 Part 1：LLM Fine-tuning 與 PEFT 技術全解析](/posts/ai-eng-from-scratch-phase11-part1-llm-finetune-zh/)

→ [Phase 12 Part 1：AI 系統可觀測性與生產監控](/posts/ai-eng-from-scratch-phase12-part1-observability-zh/)

---

*本文為「AI 工程從零開始」系列第 23 篇。系列涵蓋從基礎 ML 工程到 LLM 生產落地的完整路徑，適合準備 Staff / Senior AI 工程師面試的讀者。*

