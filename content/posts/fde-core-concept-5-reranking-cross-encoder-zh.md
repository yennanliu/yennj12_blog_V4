---
title: "Re-ranking & Cross-Encoder：向量粗召回後的精準重排序機制"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入拆解兩階段檢索架構——ANN 快速粗召回搭配 Cross-Encoder 精準重排，如何將 RAG 系統的 MRR@5 從 0.61 提升至 0.79、幻覺率降低 40%。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "RAG", "CrossEncoder", "Reranking"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Re-ranking 是「先用 Bi-Encoder 快速縮小候選集，再用 Cross-Encoder 精準評分」的兩階段架構——用 10ms 的粗召回換取可接受的候選集，再用 150ms 的深度交互換取 LLM 真正需要的高品質上下文。**

---

## 一、為什麼面試官問這個

面試官實際測試的能力：

- **你知道「快」和「準」之間的工程取捨嗎？** Bi-Encoder 可預計算、延遲低，Cross-Encoder 不可預計算但精準——能不能說清楚這兩者的差異，是區分背了課文還是真正理解原理的關鍵。
- **你能把數字說出來嗎？** 弱答：「Re-ranking 可以提升準確率。」強答：「ANN-only MRR@5 約 0.61，加上 Cross-Encoder 重排後升至 0.79，提升約 30%，幻覺率同步下降約 40%。」
- **你知道什麼時候不該用嗎？** 盲目加 Cross-Encoder 在延遲 SLA < 200ms 的場景會直接違反 SLA。強答必須包含 skip 條件。

**弱答 vs 強答對比：**

| 維度 | 弱答 | 強答 |
|------|------|------|
| 定義 | 「對搜索結果重新排序」 | 解釋 Bi-Encoder 獨立編碼 vs Cross-Encoder 聯合編碼的機制差異 |
| 數字 | 無 | MRR@5 +30%、幻覺 -40%、延遲 +150ms、成本 +$0.002/query |
| 取捨 | 「有點慢」 | 說明延遲預算分配：ANN 10ms + CE 150ms + LLM 800ms ≈ 960ms |
| 跳過條件 | 未提及 | 明確指出 <200ms SLA 應改用 ColBERT 或接受 ANN 品質 |

---

## 二、核心原理與技術深度

### Bi-Encoder 與 Cross-Encoder 的本質差異

兩種模型架構解決同一個問題（語意相關性），但用完全不同的方式：

```
Bi-Encoder（雙塔模型）
─────────────────────────────────────────────────────────────
Query ──▶ [BERT Encoder A] ──▶ q_embedding (768d)
                                        │
                                        │ cosine_sim( q, d )
                                        │
Doc   ──▶ [BERT Encoder B] ──▶ d_embedding (768d)
─────────────────────────────────────────────────────────────
優點：Doc embedding 可離線預計算並存入向量資料庫
缺點：Query 與 Doc 從不「看到」彼此，失去詞級交互

Cross-Encoder（交互模型）
─────────────────────────────────────────────────────────────
[CLS] query [SEP] document [SEP]
         │
         ▼
   [BERT Encoder — 全注意力，query 每個 token 都能關注 doc 每個 token]
         │
         ▼
   [CLS] hidden state ──▶ Linear(768 → 1) ──▶ score ∈ [0, 1]
─────────────────────────────────────────────────────────────
優點：完整注意力交互，精準度遠高於 Bi-Encoder
缺點：必須在 query 到來後才能計算，無法預計算，O(Q×N) 複雜度
```

### 兩階段檢索流程

```
用戶 Query
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 1：粗召回（Retrieve）  ~10ms                       │
│                                                          │
│  Query ──▶ Bi-Encoder ──▶ q_vec                         │
│                               │                          │
│                               ▼                          │
│  向量資料庫（HNSW / ScaNN）ANN 搜索                       │
│  返回 Top-50 候選文件（含向量距離分數）                    │
└──────────────────────┬───────────────────────────────────┘
                       │ 50 candidates
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 2：精排（Re-rank）  ~150ms                        │
│                                                          │
│  for each (query, doc_i) in candidates:                  │
│      score_i = CrossEncoder([CLS] query [SEP] doc_i)     │
│                                                          │
│  sort by score_i → 取 Top-5                              │
└──────────────────────┬───────────────────────────────────┘
                       │ 5 high-quality docs
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 3：生成（Generate）  ~800ms                       │
│                                                          │
│  LLM（Gemini / GPT）接收 Top-5 作為 context              │
│  生成最終回答                                             │
└──────────────────────────────────────────────────────────┘

總延遲：10 + 150 + 800 ≈ 960ms（多數場景可接受）
```

### 為什麼重排能降低幻覺

LLM 幻覺率與上下文品質高度相關。當 context 包含不相關文件時，LLM 被迫在「有用資訊」和「雜訊」之間混合生成，錯誤率上升。

| 指標 | ANN-only Top-50 | Cross-Encoder Top-5 | 差異 |
|------|----------------|---------------------|------|
| MRR@5 | 0.61 | 0.79 | +30% |
| Context 中不相關文件比例 | ~60% | ~15% | -75% |
| LLM 幻覺率（人工標注） | 基準 | 基準 × 0.60 | -40% |
| Context token 數 | ~8,000 | ~800 | -90% |
| LLM 推理成本 | 基準 | 基準 × 0.15 | -85% |

Context token 減少 90% 同時帶來 LLM 成本大幅下降，這讓 Cross-Encoder 的 $0.002/query 額外成本在多數情況下是正 ROI。

### Vertex AI Ranking API

Vertex AI 提供受管理的 Cross-Encoder 服務，不需要自行部署模型：

```
POST https://discoveryengine.googleapis.com/v1/projects/{project}/locations/global/rankingConfigs/default_ranking_config:rank

{
  "query": "如何設計高可用的分散式快取",
  "records": [
    {"id": "doc_001", "content": "Redis Sentinel 配置方式..."},
    {"id": "doc_002", "content": "Memcached vs Redis 比較..."},
    ...  // 最多 200 筆
  ],
  "topN": 5
}

回應延遲：~100–200ms（50 筆候選）
定價：$0.002 per 50 records ranked
```

### ColBERT：中間路線

ColBERT（Contextualized Late Interaction over BERT）是 Bi-Encoder 與 Cross-Encoder 之間的折衷方案：

```
ColBERT Late Interaction
─────────────────────────────────────────────────────────────
Query tokens: [q1, q2, q3, q4]  ──▶ BERT ──▶ Q_matrix (4×128)
Doc tokens:   [d1, d2, ..., dn] ──▶ BERT ──▶ D_matrix (n×128)

                       可離線預計算並壓縮存儲

Score = Σ_i max_j( Q_matrix[i] · D_matrix[j]^T )
        ─────────────────────────────────────────
        MaxSim：每個 query token 找最相關的 doc token

延遲：~30–50ms（介於 Bi-Encoder 10ms 和 Cross-Encoder 150ms 之間）
精準度：高於 Bi-Encoder，略低於 Cross-Encoder
─────────────────────────────────────────────────────────────
```

**三種方案速查：**

| 方案 | 延遲 | MRR@5 | 可預計算 | 成本/query |
|------|------|-------|---------|-----------|
| Bi-Encoder ANN-only | ~10ms | 0.61 | 是 | ~$0 |
| ColBERT | ~30–50ms | ~0.73 | 部分（Doc 端可） | ~$0.0005 |
| Cross-Encoder Rerank | ~150ms | 0.79 | 否 | ~$0.002 |

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標**：驗證 Re-ranking 是否對業務有幫助，快速上線。

**架構**：
```
Query ──▶ Vertex AI Vector Search（ANN Top-20）
              │
              ▼
         sentence-transformers cross-encoder/ms-marco-MiniLM-L-6-v2
         （Cloud Run，1 個 instance，CPU 推理）
              │
              ▼
         Top-3 ──▶ Gemini API
```

- 使用開源輕量 Cross-Encoder（MiniLM-L-6，22MB），CPU 推理約 200–300ms
- 部署在 Cloud Run，按需啟動，冷啟動 ~2s（可接受，首次請求慢）
- 無快取，無監控
- **成本**：Cloud Run 按請求計費，低流量下幾乎免費
- **解決問題**：驗證品質提升假設
- **剩餘問題**：冷啟動、無 SLA 保障、模型版本無管理

### Layer 2 — 生產就緒（Production-Ready）

**目標**：穩定服務真實流量，P95 < 500ms。

**架構**：
```
Query ──▶ ANN Top-50
              │
              ▼
         Vertex AI Ranking API（受管理 Cross-Encoder）
         ├─ 100–200ms 穩定延遲
         ├─ 自動擴縮，無冷啟動
         └─ SLA 99.9%
              │
              ▼
         Top-5 + score ──▶ Cache Layer（Redis TTL 5min）
              │
              ▼
         Gemini（含 score 過濾：score < 0.3 的文件不傳入 context）
```

新增元件：
- **Vertex AI Ranking API**：消除自維護模型的負擔
- **Redis 快取**：相同 query 的 rerank 結果快取 5 分鐘，命中率通常 15–30%
- **Score 過濾**：CE score < 0.3 視為不相關，即使 Top-5 也丟棄（防止強制填充低品質 context）
- **Cloud Monitoring**：追蹤 rerank_latency_p95、score_distribution、cache_hit_rate

**成本 delta**：ANN $0 → Ranking API $0.002/query + Redis ~$50/月

### Layer 3 — 企業級（Enterprise-Grade）

**目標**：多租戶、合規、可觀測、持續品質提升。

**架構**：
```
┌─────────────────────────────────────────────────────────────────┐
│  API Gateway（Rate Limiting、Auth、Tenant Routing）              │
└────────────────────────┬────────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    Tenant A        Tenant B        Tenant C
    ANN Index       ANN Index       Shared Index
          │              │              │
          └──────────────┼──────────────┘
                         ▼
              ┌─────────────────────┐
              │  Re-ranking Layer   │
              │                     │
              │  Primary: Vertex AI │
              │  Ranking API        │
              │                     │
              │  Fallback: Self-    │
              │  hosted ColBERT     │
              │  (GKE, 2 replicas)  │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Quality Monitor    │
              │                     │
              │  - A/B test: ANN    │
              │    vs CE (5% split) │
              │  - MRR@5 tracking   │
              │  - Hallucination    │
              │    rate (LLM-judge) │
              └─────────────────────┘
```

新增元件：
- **Fallback 機制**：Vertex AI Ranking API 不可用時自動切換至 GKE 上的 ColBERT（延遲增加 ~50ms，品質略降）
- **A/B 測試框架**：5% 流量走 ANN-only，持續計算 MRR 和幻覺率差異，驗證重排 ROI
- **LLM-as-Judge**：每小時抽樣 1% 回答，用獨立 LLM 評估幻覺率，自動觸發告警
- **Fine-tuning Pipeline**：收集用戶點擊/評分，每月用 MS MARCO 格式 fine-tune Cross-Encoder，Domain adaptation
- **成本 delta vs Layer 2**：+GKE fallback ~$200/月 + A/B infra + LLM-judge ~$50/月

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 直接用 Cross-Encoder 搜索全庫（跳過 ANN 粗召回） | O(N) 逐一評分，10萬文件需 ~1000 秒，完全不可用 | 必須先用 ANN 縮小至 20–100 候選，再 CE 精排 |
| Rerank Top-50 但傳給 LLM 仍是 Top-50 | Reranking 完全無效，幻覺率未改善 | Reranking 後只傳 Top-3 到 Top-5 給 LLM |
| 忽略 CE score 過濾，強制填滿 Top-5 | 低分文件（score < 0.3）仍進入 context，引入雜訊 | 設定最低 score 門檻，寧可傳 2 篇高分也不傳 5 篇低分 |
| 在 <200ms SLA 場景強上 Cross-Encoder | CE 本身 150ms，加上 ANN 和 LLM 必然破 SLA | SLA < 200ms 用 ColBERT 或 ANN-only；SLA < 500ms 用 CE |
| Bi-Encoder 和 Cross-Encoder 使用不同的 tokenizer / 訓練域 | 分數分布不一致，score 過濾閾值難以設定 | 使用同一訓練集 fine-tune 兩個模型，或使用 Vertex AI 統一服務 |
| 不監控 score 分布漂移 | 資料分布變化後 CE 分數系統性偏移，Top-5 品質悄悄下降 | Cloud Monitoring 追蹤 score P50/P95，設定告警 |
| 快取 key 僅用 query 字串，忽略租戶 ID | 不同租戶的 query 相同但 index 不同，返回錯誤租戶的結果 | Cache key = hash(tenant_id + query + index_version) |

---

## 五、與其他核心主題的關聯

- **Part 3 — 向量資料庫與 HNSW**：Re-ranking 的 Stage 1 完全依賴 ANN 索引，HNSW recall@50 的品質上限決定了 CE 能優化的空間——若 ANN 連 50 個候選都召回不全，CE 再強也無能為力。
- **Part 4 — RAG Pipeline 設計**：Re-ranking 是 RAG retrieve → rerank → generate 三步中的核心 rerank 環節；Part 4 說明了完整 pipeline，本篇深入 rerank 機制。
- **Part 6 — Embedding Model 選型與 Fine-tuning**：Bi-Encoder 的 embedding 品質決定粗召回品質；對 Cross-Encoder 做 domain fine-tuning 需要同樣的 MS MARCO 格式訓練數據。
- **fde-interview-guide Part 31–32（ADK / Vertex AI 產品棧）**：Vertex AI Ranking API 是本篇 Layer 2 的核心元件，理解 Vertex AI 整體產品棧有助於評估受管理服務 vs 自建的取捨。

---

## 六、面試一句話（Killer Phrase）

> *「Re-ranking 的本質是用兩階段架構平衡召回效率與精排品質：Bi-Encoder 因為 query 和 doc 獨立編碼，可離線預計算向量並在 ANN 索引中 10ms 內召回 Top-50 候選；Cross-Encoder 則把 query 和 doc 拼接成 `[CLS] q [SEP] d [SEP]` 後過完整 BERT 注意力層，query 的每個 token 都能和 doc 的每個 token 交互，精準度遠高於 Bi-Encoder，但無法預計算、延遲約 150ms。兩階段合計 ANN 10ms + CE 150ms + LLM 800ms ≈ 960ms，多數 RAG 場景可接受。引入 Cross-Encoder 後 MRR@5 從 0.61 升至 0.79（+30%），LLM 幻覺率因高品質 context 降低約 40%——代價是每 query 增加約 $0.002。對延遲 SLA < 200ms 的場景，我會改用 ColBERT 的 token 級 Late Interaction，延遲壓至 30–50ms，品質介於兩者之間。」*

---

**系列導航**

← [前一篇：RAG Pipeline 整體架構設計](/posts/fde-interview-core-topic-4-rag-pipeline-zh/) | [後一篇：Embedding Model 選型與 Fine-tuning](/posts/fde-interview-core-topic-6-embedding-model-zh/) →
