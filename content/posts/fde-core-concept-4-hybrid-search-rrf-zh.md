---
title: "FDE core topic - Hybrid Search & RRF：混合檢索與倒數排名融合演算法"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析混合檢索（Dense + Sparse）與 Reciprocal Rank Fusion 的核心原理、實作層次及面試答題策略，涵蓋 BM25、HNSW、SPLADE、Vertex AI Search 等關鍵技術與具體效能數字。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "RAG", "VectorSearch", "BM25"]
authors: ["yen"]
readTime: "18 min"
---

**單一檢索模態最多只能取得 72% 的 Recall；混合 Dense + Sparse 搭配 RRF 融合，可將 Recall@10 推至 84%——多 12 個百分點就是 RAG 系統品質的分水嶺。**

---

## 一、為什麼面試官問這個

面試官透過這個題目在測試三個層次的能力，每個層次都有明確的弱答案與強答案之分：

**測試點一：你是否理解「向量相似度 ≠ 文字匹配」的本質差異**

純 Dense 搜尋對「GPT-4o」、「CVE-2024-1234」、「iPhone 16 Pro Max」這類精確字串幾乎無效。Bi-encoder 把這些字串編碼到連續向量空間後，拼寫上的微小差異可能造成 cosine similarity 大幅下降，但語意上確實是同一件事。反過來，純 BM25 對「汽車」vs「轎車」、「機器學習」vs「ML」的語意等價完全失明——詞彙不交疊，BM25 分數為零。沒有一種模態可以獨立超越 75% 的 Recall。

**測試點二：你是否能量化 tradeoff，而非只說「混合比較好」**

弱答案：「我會把兩個結果合併起來，這樣召回率會更高。」

強答案：「dense-only recall@10 = 72%，sparse-only recall@10 = 68%，hybrid RRF = 84%。關鍵在 k=60 的平滑常數讓兩個信號貢獻均衡；若某個模態明顯更優（差距 > 15pp），改用 k=10–20 放大強模態影響力。」

**測試點三：你是否了解雲端具體實作路徑**

能說出「Vertex AI Search 內建 hybrid mode」和「BigQuery Vector Search 可用 `VECTOR_SEARCH()` + `SEARCH()` 在 SQL 層組合」的候選人，遠比只談演算法理論的人有說服力。這說明你真的在生產環境中做過，而不是只讀過論文。

---

## 二、核心原理與技術深度

### Dense 檢索：語意向量空間

Bi-encoder 模型（如 `text-embedding-005`、`text-multilingual-embedding-002`）將 query 與 document 各自獨立編碼為固定維度向量（通常 768 或 1536 維），在高維向量空間中以 cosine similarity 或 inner product 衡量相關性。

**為什麼用 Bi-encoder 而非 Cross-encoder？**

Cross-encoder 將 query + document 一起餵進模型，準確度更高，但時間複雜度是 O(n)——對 1M 篇文件做查詢需推理 1M 次，不可行。Bi-encoder 預先計算所有 document embedding（離線），查詢時只需計算 query embedding 一次，再做向量相似度搜尋，時間複雜度降至 O(log n)。

索引結構使用 **HNSW（Hierarchical Navigable Small World）**：

```
HNSW 多層圖索引（概念示意）

Layer 2（稀疏長程連接）:  [A] ────────────────────── [G]
                            \                          /
Layer 1（中密連接）    :  [A] ──── [C] ──── [E] ──── [G]
                            \      |         |        /
Layer 0（全量節點）    :  [A][B] [C][D]   [E][F]  [G][H]
                                        ↑
                                   Query 進入點（貪婪搜尋）
```

- 建構超參數 `M`（每節點最大連接數，通常 16–64）和 `ef_construction`（建構時候選池大小，通常 200–400）控制 recall vs 建構時間 tradeoff
- 查詢超參數 `ef_search`（搜尋時候選池大小）：`ef_search=100` 約 recall=0.95，`ef_search=200` 約 recall=0.99，延遲增加約 2x
- 查詢時間複雜度：O(log n)，1M 向量規模 p99 < 10 ms
- 記憶體需求：4 bytes × 維度 × 文件數；1M 篇 × 768 維 ≈ 3 GB RAM

**Dense 的核心盲點**：OOV（Out-of-Vocabulary）詞彙、產品型號（A100 vs H100）、縮寫詞（NLP vs Natural Language Processing 倒還好，但 CVE 編號就糟了）、以及訓練語料中完全未見過的實體名稱。Embedding 模型看到 "gpt-4o-mini" 和 "gpt-4o" 可能算出很高的相似度，但用戶就是要搜具體型號。

---

### Sparse 檢索：詞頻統計空間

**BM25 完整公式**：

```
              ⎡    N - df(q_i) + 0.5 ⎤   f(q_i, D) × (k1 + 1)
BM25(D,Q) = Σ ⎢log ──────────────────⎥ × ─────────────────────────────────
         q_i  ⎣     df(q_i) + 0.5    ⎦   f(q_i,D) + k1×(1 - b + b×|D|/avgdl)
```

關鍵參數含義：

- `N`：語料庫總文件數
- `df(q_i)`：包含詞 q_i 的文件數（計算 IDF）
- `f(q_i, D)`：詞 q_i 在文件 D 中的出現次數（詞頻）
- `k1 ≈ 1.2`：詞頻飽和係數。詞頻從 1 增至 10 時分數只增長約 1.5x，而非 10x——防止垃圾文件通過重複關鍵字刷高分
- `b ≈ 0.75`：文件長度正規化係數。b=0 完全不考慮長度，b=1 完全正規化
- `avgdl`：語料庫平均文件長度（詞數）

BM25 的實作成本極低：倒排索引（Inverted Index）查詢 < 5 ms，無需 GPU，記憶體佔用約 0.5 GB（1M 篇文件），完全精確的字串匹配。

**SPLADE（Sparse Lexical and Expansion）進化版**

SPLADE 用 BERT 做詞彙擴展，將輸入文字膨脹為稀疏詞彙向量：

```
輸入文字: "車輛購買"

BM25 索引詞彙:
  車輛: 1, 購買: 1

SPLADE 擴展後索引詞彙:
  車輛: 2.3, 汽車: 1.8, 轎車: 1.5,
  購買: 2.1, 購置: 1.7, 採購: 1.2,
  機動車: 1.1, 交通工具: 0.9, ...
```

SPLADE 解決了 BM25 的詞彙不匹配問題，但有推理開銷（延遲約 20–50 ms，比 BM25 慢 4–10x）。生產上通常用 SPLADE 做離線索引建構（可接受），查詢時用輕量版 SPLADE 或直接用 BM25。

---

### RRF：倒數排名融合演算法

兩路檢索各返回 Top-K 結果後，用 RRF 合併排名（無需知道原始分數，只需排名位置）：

```
RRF(d) = Σ  1 / (k + rank_i(d))
          i∈{dense, sparse}
```

- `k = 60`：標準平滑常數（來自 Cormack et al. 2009 年論文，在多個 TREC benchmark 上驗證有效）
- `rank_i(d)`：文件 d 在第 i 路檢索中的排名，**從 1 開始計數**
- 若文件 d 在某一路未出現，通常設 rank = ∞（貢獻為 0），或設為 Top-K 之後的虛擬排名

**具體計算範例（以 k=60 為例）**：

```
Query: "GPT-4o 的 API 定價方式"

Dense 結果:  [doc_B, doc_D, doc_A, doc_F, doc_C, ...]
Sparse 結果: [doc_A, doc_C, doc_B, doc_E, doc_F, ...]

文件 A：Dense rank=3，Sparse rank=1
  RRF(A) = 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226

文件 B：Dense rank=1，Sparse rank=3
  RRF(B) = 1/(60+1) + 1/(60+3) = 0.01639 + 0.01587 = 0.03226  ← 對稱，完全相等

文件 C：Dense rank=5，Sparse rank=2
  RRF(C) = 1/(60+5) + 1/(60+2) = 0.01538 + 0.01613 = 0.03151

文件 D：Dense rank=2，Sparse rank=∞（未出現）
  RRF(D) = 1/(60+2) + 0 = 0.01613

最終排名: A=B (0.0323) > C (0.0315) > D (0.0161) > ...
```

**關鍵洞察**：doc_A 在 Sparse 排第一（精確字串命中），doc_B 在 Dense 排第一（語意最相關），RRF 認為兩者同樣有價值——RRF 本質上是「兩個模態都看好的文件排前面，只有一個模態看好的文件次之」。

**k 值的影響分析**：

```
k 值   rank=1 的貢獻   rank=10 的貢獻   rank1/rank10 比率
─────────────────────────────────────────────────────────
k=10   1/11 = 0.0909   1/20 = 0.0500   1.82x
k=60   1/61 = 0.0164   1/70 = 0.0143   1.15x  ← 差異最小（均衡）
k=200  1/201= 0.0050   1/210= 0.0048   1.04x  ← 幾乎相等（極度均衡）
```

- `k=10`：排名差距放大約 1.8x，適合一個模態明顯更優的情況
- `k=60`：標準均衡選擇，推薦預設值
- `k=200`：差距壓縮至接近平等，適合完全不確定哪個模態更好時

**何時應調整 k 值**：線下跑 Recall 評估，若 Dense Recall = 82%、Sparse Recall = 55%，兩者差距 27pp，這時 k=60 讓 Sparse 貢獻過多雜訊，應調低 k 至 20–30。反之若兩者 Recall 接近，k=60 是最優選擇。

---

### 系統資料流與延遲分解

```
                  ┌──────────────────────────────────────────┐
                  │   Query: "GPT-4o 定價 API 免費額度"        │
                  └───────────────────┬──────────────────────┘
                                      │
          ┌───────────────────────────┴────────────────────────────┐
          │ Fan-out（並行，deadline=250ms）                          │
          ▼                                                        ▼
┌─────────────────────────┐                     ┌─────────────────────────┐
│   Dense Retrieval       │                     │   Sparse Retrieval      │
│                         │                     │                         │
│  1. Query Embedding     │                     │  1. Tokenize + IDF      │
│     (API call, ~30ms)   │                     │     lookup (~1ms)       │
│  2. HNSW ANN search     │                     │  2. Inverted index      │
│     ef_search=100       │                     │     posting list merge  │
│     (~8ms on 1M vecs)   │                     │     (~4ms on 1M docs)   │
│  3. Return Top-50       │                     │  3. BM25 score + sort   │
│     by cosine sim       │                     │  4. Return Top-50       │
│                         │                     │     by BM25 score       │
│  總延遲: ~38ms (p50)     │                     │  總延遲: ~5ms (p50)     │
└────────────┬────────────┘                     └────────────┬────────────┘
             │  [doc_B:1, doc_D:2, doc_A:3, ...]             │  [doc_A:1, doc_C:2, ...]
             └───────────────────────┬────────────────────────┘
                                     ▼
                   ┌─────────────────────────────────┐
                   │   RRF Fusion Service             │
                   │                                  │
                   │  for each doc in union:          │
                   │    score = 1/(60+rank_dense)     │
                   │           + 1/(60+rank_sparse)   │
                   │  sort by score DESC              │
                   │  return Top-20                   │
                   │                                  │
                   │  延遲: ~1ms（純計算，無 I/O）      │
                   └──────────────────┬──────────────┘
                                      │
                                      ▼
                   ┌─────────────────────────────────┐
                   │   (Optional) Cross-Encoder       │
                   │   Reranker                       │
                   │                                  │
                   │  Top-20 → Rerank → Top-10        │
                   │  text-ranking-gecko@003          │
                   │  延遲: ~60ms (p50), ~120ms (p99) │
                   └──────────────────┬──────────────┘
                                      ▼
                   ┌─────────────────────────────────┐
                   │   LLM Context（RAG Generation）   │
                   │   Top-5 chunks → Gemini          │
                   └─────────────────────────────────┘

總端到端延遲（含 Reranker）: p50=100ms, p99=200ms
```

---

### 效能數字對照

| 指標 | Dense Only | Sparse Only | Hybrid RRF | Hybrid + Reranker |
|------|-----------|------------|------------|-------------------|
| Recall@10 | 72% | 68% | **84%** | 84%（Recall 不變）|
| Precision@5 | 61% | 58% | 72% | **79%** |
| P50 查詢延遲 | 38 ms | 5 ms | 40 ms | 100 ms |
| P99 查詢延遲 | 85 ms | 15 ms | 90 ms | 200 ms |
| 索引建構時間（1M 文件） | ~45 min | ~8 min | ~53 min | 不影響索引 |
| 記憶體需求（1M × 768 維） | ~3 GB | ~0.5 GB | ~3.5 GB | +model ~2 GB |
| 精確字串匹配（OOV 詞彙） | 差 | 優 | 優 | 優 |
| 語意等價匹配（car ↔ automobile） | 優 | 差 | 優 | 優 |
| 多義詞消歧（bank 銀行/河岸） | 優（context-aware） | 差 | 優 | 優 |

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標**：1–2 天上線，快速驗證 Hybrid 對你的資料集是否有效，取得 Recall 基準數字。

**核心選擇**：使用 **Elasticsearch 8.x** 的 `knn` retriever + `standard` retriever 組合，ES 8.8+ 已內建 `rrf` retriever，無需自行實作融合邏輯：

```json
{
  "retriever": {
    "rrf": {
      "retrievers": [
        { "knn": { "field": "embedding", "query_vector": [...], "k": 50 } },
        { "standard": { "query": { "match": { "content": "GPT-4o 定價" } } } }
      ],
      "rank_constant": 60,
      "rank_window_size": 50
    }
  },
  "size": 10
}
```

- Dense 模型：呼叫 Vertex AI Embeddings API（`text-embedding-005`），不自行 host 模型
- Sparse：ES 預設 BM25 分析器，無需額外設定
- Top-K=10，不做 Reranker

**成本/複雜度**：單台 ES 節點（`n2-standard-8`，約 \$200/月），Vertex AI Embeddings API 約 \$0.025/1000 次 query。1–2 天完成整合。

**解決了什麼**：快速取得 Recall@10 基準數字；若比 dense-only 提升 < 5pp，表示資料集語意覆蓋已足夠，或資料品質本身有問題，值得先解決資料問題再做 Hybrid。

**仍有的問題**：ES 單點無高可用；Dense 索引段（segment）不支援線上增量更新，需定期重建（每 24 小時 full rebuild 或每 4 小時 segment merge）；沒有查詢延遲 SLO 保障；BM25 分析器若語言是中文需確認已安裝 `analysis-smartcn` plugin。

---

### Layer 2 — 生產就緒（Production-Ready）

**目標**：支撐 500 QPS 以下的真實流量，p99 < 50 ms，服務可用性 99.5%+。

**方案 A：Vertex AI Search（推薦，最快落地）**

Vertex AI Search 是全託管服務，內建 hybrid search mode，免除向量資料庫維運：

- 建立 Data Store 時設定 `content_search_spec.search_result_mode: CHUNKS`
- 呼叫 `search()` API 時設 `query_expansion_spec.condition: AUTO`（自動做 query 擴展）
- 支援 `filter` 做 metadata 過濾（在 Hybrid 結果上疊加結構化篩選）
- 價格：約 \$2.5 / 1000 次 search 請求

**方案 B：BigQuery Vector Search（適合已有 BQ 資料倉儲）**

在 SQL 層組合 Dense 與 Sparse，利用現有 BQ 基礎設施：

```sql
WITH dense_results AS (
  SELECT
    base.doc_id,
    base.content,
    ROW_NUMBER() OVER (ORDER BY distance ASC) AS dense_rank
  FROM VECTOR_SEARCH(
    TABLE `project.dataset.doc_embeddings`,
    'embedding',
    (SELECT embedding FROM ML.GENERATE_EMBEDDING(
      MODEL `project.models.textembedding`,
      (SELECT 'GPT-4o 定價 API 免費額度' AS content)
    )),
    top_k => 50,
    distance_type => 'COSINE'
  )
),
sparse_results AS (
  SELECT
    doc_id,
    content,
    ROW_NUMBER() OVER (ORDER BY score DESC) AS sparse_rank
  FROM (
    SELECT doc_id, content, score
    FROM `project.dataset.documents`
    WHERE SEARCH(content, 'GPT-4o 定價 API 免費額度')
  )
  LIMIT 50
),
rrf_fusion AS (
  SELECT
    COALESCE(d.doc_id, s.doc_id) AS doc_id,
    COALESCE(d.content, s.content) AS content,
    (1.0 / (60 + COALESCE(d.dense_rank, 9999)))
    + (1.0 / (60 + COALESCE(s.sparse_rank, 9999))) AS rrf_score
  FROM dense_results d
  FULL OUTER JOIN sparse_results s USING (doc_id)
)
SELECT doc_id, content, rrf_score
FROM rrf_fusion
ORDER BY rrf_score DESC
LIMIT 10
```

- 加入 Cross-encoder Reranker（`text-ranking-gecko@latest`）對 Top-20 結果做精排
- 監控：Cloud Monitoring 追蹤 Recall@10（需維護 golden dataset 和定期評估 pipeline）、查詢延遲 p50/p99

**成本/複雜度**：Vertex AI Search 按請求計費；BQ Vector Search 按掃描量計費（100GB 掃描約 \$0.50）。3–5 天完成整合。

**解決了什麼**：高可用（Vertex AI SLA 99.9%）、自動縮放、原生 Vertex AI 監控整合、無向量資料庫維運負擔。

**仍有的問題**：Vertex AI Search 的 BM25 分析器設定不完全透明；BQ 方案在高 QPS（>100 QPS）下成本呈線性增長，可能不划算；無法細調 HNSW 超參數。

---

### Layer 3 — 企業級（Enterprise-Grade）

**目標**：10,000+ QPS、多租戶隔離、p99 < 30 ms、完整可觀測性、合規審計。

**架構概覽**：

```
┌─────────────────────────────────────────────────────────────────┐
│  API Gateway（Cloud Endpoints）                                   │
│  速率限制、JWT 驗證、租戶識別                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Query Service   │ │  A/B Config  │ │  Eval Pipeline   │
│  (Cloud Run)     │ │  (Firestore) │ │  (Cloud Run Job) │
│  Fan-out 並行    │ │  k 值實驗     │ │  每日 Recall 報告 │
└────────┬─────────┘ └──────────────┘ └──────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐  ┌───────┐
│Weaviate│  │Weaviate│   ← 租戶 A / 租戶 B（class 隔離）
│Dense  │  │Sparse │     Cloud KMS 各自加密金鑰
│(HNSW) │  │(BM25) │
└───────┘  └───────┘
    ↑           ↑
    └─────┬─────┘
          │
┌─────────────────────┐
│  Indexing Pipeline  │
│  (Cloud Run Jobs)   │
│  Pub/Sub 觸發        │
│  增量更新，每 5 分鐘  │
└─────────────────────┘
```

**關鍵設計決策**：

1. **向量資料庫**：Weaviate（GKE Autopilot），搭配 `text2vec-transformers` module（Dense）和 `bm25` module（Sparse）。或 Qdrant 作為替代，Qdrant 支援原生稀疏向量索引（sparse vector index），天生適合 SPLADE。
2. **查詢路由層**：Cloud Run 做 fan-out，同時呼叫 Dense 和 Sparse 端點，設 250 ms deadline；任一端點超時則 fallback 到單模態（Circuit Breaker pattern）。
3. **動態 k 值**：RRF k 值從 Firestore 讀取（每個 query 類型可設不同 k），搭配 Cloud Experiments 做 A/B 測試（實驗組 k=30，對照組 k=60，追蹤 Recall@10 和用戶 CTR）。
4. **Reranker**：Cross-encoder 部署於 GKE（`n2-standard-4`，2 replica），使用 `text-ranking-gecko@003`，對 Top-30 重排後取 Top-10，p99 < 80 ms。
5. **可觀測性**：Cloud Trace 追蹤每一跳延遲（embedding、dense search、sparse search、RRF、rerank）；BigQuery Export 儲存所有 query + Top-10 結果，每週跑 Recall 評估 pipeline（用 LLM 自動標注相關性）。
6. **多租戶**：Weaviate class 隔離（`Tenant_A_Documents` vs `Tenant_B_Documents`）；Cloud KMS 管理各租戶的 embedding 加密金鑰；BigQuery 審計表記錄誰在何時搜了什麼。

**成本/複雜度**：GKE 叢集 + Weaviate 約 \$2,000–5,000/月（視資料量和 QPS）；Reranker GKE 約 \$400/月。2–4 週完成整合，需 ML Platform + SRE + Security 協作。

**解決了什麼**：企業 SLA 99.9%、細粒度 k 值 A/B 實驗、完整審計軌跡、多租戶合規隔離、增量索引更新（無需 full rebuild）。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 用加權平均原始分數做 score fusion（如 `0.7 × cosine_sim + 0.3 × bm25_score`） | Dense 分數範圍 [0,1]，BM25 分數無上界（可能是 25.7），量級完全不同，加權平均被 BM25 主導，效果比單模態更差 | 改用 RRF（只用排名，不依賴原始分數）；或對兩路分數各自做 min-max 正規化後再加權 |
| Chunk 級別搜尋後忘記在文件級別去重 | 同一長文被切成 10 個 Chunk，Top-10 結果中 7 個來自同一篇文件，LLM 拿到重複 context，答案品質下降，有效 context 窗口浪費 | Chunk 搜尋後按 `parent_doc_id` group by，取每個父文件中 RRF score 最高的 chunk，再做父文件級別排名 |
| k=60 套用在所有場景不根據資料特性調整 | 當 Dense Recall = 82%、Sparse Recall = 55%，差距 27pp，k=60 讓弱勢的 Sparse 貢獻過多雜訊，融合後 Recall 反而低於單用 Dense | 先在 evaluation set 上測試 k={10, 20, 40, 60, 100}，選 Recall@10 最高的 k 值；Recall 差距 > 20pp 時通常 k=20–30 更優 |
| 未建立 offline Recall 評估 pipeline，只靠用戶回饋 | 無法量化每次 embedding 模型升級、索引參數調整對 Recall 的影響；優化方向靠直覺，失去實驗可重複性 | 建立 golden dataset（≥200 個 query-relevant_doc pair），每次部署前自動跑 Recall@5、Recall@10、MRR，存入 BigQuery 比較趨勢 |
| Reranker 放在 RRF 之前（對 Dense Top-K 重排再做 RRF） | Reranker 已包含語意精排信息，再與 Sparse 做 RRF 造成 Dense 信號被雙重計算，排名偏差加劇 | Reranker 永遠放在 RRF 之後，作為最終精排步驟；正確順序：Dense retrieval → Sparse retrieval → RRF fusion → Reranker → LLM |
| 用 cosine similarity threshold 過濾 Dense 結果後再送 RRF（例如「相似度 < 0.7 的過濾掉」） | 低相似度但高 BM25（精確字串命中）的文件被提前丟棄，Hybrid 的互補效益消失，退化為純 Sparse | 不做閾值過濾；RRF 本身已處理低排名（分母大、貢獻小）；若需控制品質，在 RRF 之後設最終 score 的下界 |
| Embedding 模型語言與 BM25 斷詞器不匹配（英文 embedding + 未設定中文斷詞的 BM25） | Dense 向量可能無法捕捉中文語意；BM25 用英文空格斷詞導致中文字切成單字，IDF 計算完全偏差，Sparse 結果無意義 | 使用支援多語言的 Bi-encoder（如 `text-multilingual-embedding-002`）；Elasticsearch BM25 安裝 `analysis-smartcn` 或 `analysis-ik` 中文分詞插件 |

---

## 五、與其他核心主題的關聯

- **RAG Pipeline 整體架構**（fde-interview-guide Part 31–32）：Hybrid Search 是 RAG 的 Retrieval 階段核心。Recall 的上限直接決定 Generation 的品質上限——LLM 無法從未檢索到的文件中生成正確答案，任何 prompt engineering 都無法彌補 Retrieval 的失誤。
- **Embedding 模型選型與微調**（fde-core-topics Part 3）：Dense 檢索的品質取決於 Bi-encoder 的領域適配性；對垂直領域語料做 contrastive fine-tuning 可將 Dense Recall 從 72% 提升至 78–80%，縮小與 Hybrid 的差距，影響是否值得維護兩套索引的架構決策。
- **向量資料庫選型**（fde-core-topics Part 5）：HNSW 的 `ef_construction` 和 `M` 超參數直接影響 Dense Recall vs 延遲的 tradeoff；Weaviate、Qdrant、Milvus 對 Sparse 向量的原生支援程度各異，選型時需確認是否支援 SPLADE 格式的稀疏向量。
- **Reranking 與 Cross-Encoder**（fde-core-topics Part 6）：RRF 是輕量級排名融合（純計算，< 1 ms，無需推理），Cross-encoder Reranker 是重量級精排（需模型推理，60–120 ms）；兩者分工明確——RRF 負責廣度（Recall），Reranker 負責精度（Precision@5）。

---

## 六、面試一句話（Killer Phrase）

> *「Hybrid Search 的本質是承認沒有任何單一相關性信號能覆蓋所有查詢類型——Dense 向量搜尋擅長語意等價但對精確字串盲目，BM25 擅長精確匹配但對語意變體無感，兩者各自的 Recall@10 分別只有 72% 和 68%。RRF 的聰明之處是用排名而非原始分數做融合，k=60 的平滑常數讓排名差距被壓縮，防止任何一個信號的極端排名主導最終結果，融合後 Recall@10 達到 84%，多了 12 個百分點。在生產上我會先用 Vertex AI Search 的內建 hybrid mode 快速驗證資料集上的 Recall 提升是否顯著，確認值得投資後再根據 QPS 和成本評估是否自建 Weaviate + SPLADE 方案，並用 A/B 實驗動態調整 k 值——k=60 是良好起點，但若兩個模態的 Recall 差距超過 20pp 就應該調低 k 讓強模態主導。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-3-zh/) | [後一篇](/posts/fde-interview-core-topic-5-zh/) →
