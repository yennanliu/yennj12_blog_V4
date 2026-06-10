---
title: "FDE core topic - RAG Triad Metrics：上下文相關度、忠實度與答案相關度的可觀測性追蹤"
date: 2026-06-08T10:00:00+08:00
draft: false
weight: 20
description: "深入解析 RAG 系統三大評估指標——Context Relevance、Groundedness、Answer Relevance——以及如何透過 OpenTelemetry 與 Grafana 建立生產級可觀測性追蹤管道。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "RAG", "Observability", "Evaluation"]
authors: ["yen"]
readTime: "18 min"
---

**RAG 系統沒有「準確率」這個單一指標——你需要三把尺同時量：檢索對了嗎？答案有根據嗎？答案回答了問題嗎？少量其中任何一把，幻覺或廢話就悄悄進入生產。**

---

## 一、為什麼面試官問這個

面試官問 RAG 評估指標，真正在測試的是以下三件事：

- **你能否把「LLM 答得好不好」拆解成可量化的子問題。** 弱答案：「我們用 ROUGE 或 BLEU 評估。」——這是序列生成指標，對 RAG 完全不適用，暴露了對 RAG 工作流程的根本誤解。
- **你是否理解幻覺的成因與偵測手段。** 弱答案：「幻覺是 LLM 的問題，換模型就好。」——強答案會指出 Groundedness（忠實度）是反幻覺的核心指標，並說明如何用 NLI 模型逐句驗證。
- **你能否把評估指標接進可觀測性管道（OTel → Prometheus → Grafana），讓它在生產中持續追蹤而非一次性評測。** 弱答案只談離線評測；強答案談 span attributes、rolling average dashboard、以及 alert threshold。

---

## 二、核心原理與技術深度

### RAG 三角指標的數學基礎

RAG Triad 由 TruEra（現為 Snowflake 旗下）提出，對應 RAG pipeline 的三個環節：

```
使用者查詢 (Query)
       │
       ▼
┌──────────────────────┐
│  Retriever           │  ← 指標 1：Context Relevance
│  向量搜尋 / BM25     │     retrieved chunks 與 query 的相似度
└──────────┬───────────┘
           │  retrieved context
           ▼
┌──────────────────────┐
│  LLM Generator       │  ← 指標 2：Groundedness（忠實度）
│  Gemini / GPT-4o     │     answer 中每個宣稱是否有 context 支撐
└──────────┬───────────┘
           │  generated answer
           ▼
┌──────────────────────┐
│  Answer Evaluation   │  ← 指標 3：Answer Relevance
│  Embed / LLM Judge   │     answer 是否真正回答了 query
└──────────────────────┘
```

### 指標 1：Context Relevance（上下文相關度）

**定義**：檢索到的 chunks 中，真正與查詢相關的比例。

**計算方式**：

```
score = mean( cosine_sim(embed(query), embed(chunk_i)) )
        for i in retrieved_chunks
```

- 使用與索引相同的 embedding model（如 `text-embedding-004`，768 維）
- 門檻值：**> 0.75** 為可接受；< 0.65 代表 retrieval 嚴重失準
- 若使用 hybrid search，對向量分數與 BM25 分數做加權平均後再閾值過濾

**低分症狀**：答案答非所問、LLM 被迫「自由發揮」補足缺失的背景知識。

```
Query Embedding (768-dim)
[0.12, -0.34, 0.87, ...]
         │
         │ cosine similarity
         ▼
Chunk 1: sim = 0.82  ✓ 相關
Chunk 2: sim = 0.61  ✗ 不相關（低於 0.75 門檻）
Chunk 3: sim = 0.79  ✓ 相關
         │
         ▼
Context Relevance Score = (0.82 + 0.61 + 0.79) / 3 = 0.74
                          → 邊緣值，需優化 retrieval
```

### 指標 2：Groundedness / Faithfulness（忠實度）

**定義**：答案中每一個事實宣稱（factual claim），都能在 retrieved context 中找到明確支撐。

**計算方式（雙軌）**：

**方式 A：NLI 模型**
```
for each sentence s in answer:
    entailment_score = NLI_model(premise=context, hypothesis=s)
    # entailment_score ∈ {ENTAIL, NEUTRAL, CONTRADICT}

groundedness = count(ENTAIL) / total_sentences
```

使用模型：`cross-encoder/nli-deberta-v3-large`（推理延遲約 80ms/句）

**方式 B：LLM Judge（更常見於生產）**
```
prompt = """
Context: {retrieved_context}
Answer: {generated_answer}

For each factual claim in the Answer, cite the exact sentence from Context
that supports it. If no support exists, mark as [UNSUPPORTED].

Output JSON: {"claims": [{"claim": "...", "support": "..." | "[UNSUPPORTED]"}]}
"""
```

Groundedness Score = 1 - (UNSUPPORTED claims / total claims)

**為什麼 Groundedness 是反幻覺的核心指標**：LLM 幻覺分兩類——「憑空捏造」與「錯誤外推」。兩者都會讓 NLI 判定為 NEUTRAL 或 CONTRADICT，因此 Groundedness < 0.80 直接等同於幻覺率 > 20%，在醫療、法律、金融場景不可接受。

### 指標 3：Answer Relevance（答案相關度）

**定義**：答案是否真正回答了原始查詢，而非偏題或提供無關資訊。

**計算方式（雙軌）**：

**方式 A：嵌入相似度**
```
score = cosine_sim(embed(answer), embed(query))
```
快速、低延遲，但對「答案很長但答了另一個問題」的情況不夠敏感。

**方式 B：反向問題生成（更精準）**
```
1. 從 answer 生成 5 個問題 Q1...Q5（用 LLM）
2. 計算 original_query 與 Q1...Q5 的平均 cosine similarity
3. 若 similarity 高 → answer 確實在回答 original_query
```

```
原始 Query: "Kubernetes Pod 的重啟策略有哪些？"
           │
           ▼
Answer → 生成問題 →  Q1: "Pod 失敗後如何自動重啟？"     sim=0.89
                    Q2: "Always 策略適用什麼場景？"     sim=0.85
                    Q3: "OnFailure 與 Never 的差別？"  sim=0.87
                    Q4: "restartPolicy 的預設值？"     sim=0.83
                    Q5: "Job 類型推薦哪種策略？"        sim=0.81
                         │
                         ▼
           Answer Relevance = mean = 0.85  ✓
```

### 具體基準數字

| 指標 | 未調優 RAG（baseline） | Hybrid Search + Reranking | 提升幅度 |
|------|----------------------|--------------------------|--------|
| Context Relevance | 0.68 | 0.84 | +24% |
| Groundedness | 0.71 | 0.89 | +25% |
| Answer Relevance | 0.74 | 0.82 | +11% |

未調優系統的典型問題：純向量搜尋在語義偏移查詢（如縮寫、專有名詞）上失準，導致 Context Relevance 只有 0.68，進而連鎖拉低 Groundedness。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標**：在 48 小時內建立離線評測管道，讓開發團隊有數字可看。

**實作**：
- 使用 `trulens-eval`（開源）或 `ragas` 套件，直接計算三個指標
- 以 cosine similarity 計算 Context Relevance 與 Answer Relevance
- Groundedness 使用 LLM Judge（呼叫同一個 LLM，額外成本約 $0.002/query）
- 每次 model 版本更新時跑一次評測，結果存入 CSV

```python
from ragas.metrics import context_precision, faithfulness, answer_relevancy
from ragas import evaluate

result = evaluate(
    dataset,
    metrics=[context_precision, faithfulness, answer_relevancy]
)
print(result)
# {'context_precision': 0.71, 'faithfulness': 0.74, 'answer_relevancy': 0.77}
```

**限制**：離線評測，無法追蹤生產中的指標漂移（metric drift）。複雜度：低。成本：幾乎為零（LLM Judge 的 API 費用）。

---

### Layer 2 — 生產就緒（Production-Ready）

**目標**：在線上請求中即時計算指標，並送進 Prometheus，讓 SRE 能設定 alert。

**新增元件**：
- OpenTelemetry SDK 埋入 RAG pipeline，每個請求產生一個 span
- Span attributes 包含三個指標數值
- Prometheus Exporter 聚合 7 天滾動平均

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

tracer = trace.get_tracer("rag-pipeline")

with tracer.start_as_current_span("rag_request") as span:
    context_chunks = retriever.retrieve(query)
    answer = llm.generate(query, context_chunks)

    ctx_rel   = compute_context_relevance(query, context_chunks)
    grounded  = compute_groundedness(answer, context_chunks)
    ans_rel   = compute_answer_relevance(query, answer)

    span.set_attribute("rag.context_relevance", ctx_rel)
    span.set_attribute("rag.groundedness",      grounded)
    span.set_attribute("rag.answer_relevance",  ans_rel)
    span.set_attribute("rag.intent_class",      classify_intent(query))
    span.set_attribute("rag.model_version",     MODEL_VERSION)
```

**Alert 設定（Prometheus AlertManager）**：

```yaml
groups:
  - name: rag_quality
    rules:
      - alert: RAGGroundednessWarning
        expr: avg_over_time(rag_groundedness[1h]) < 0.80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "RAG 忠實度低於警戒值 0.80，幻覺率可能超過 20%"

      - alert: RAGGroundednessCritical
        expr: avg_over_time(rag_groundedness[15m]) < 0.70
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "RAG 忠實度跌破 0.70，幻覺率不可接受，觸發 oncall"
```

**複雜度**：中。需要 OTel Collector + Prometheus + AlertManager。延遲開銷：Groundedness LLM Judge 約 200–400ms，建議非同步計算（fire-and-forget），不阻塞使用者回應。

---

### Layer 3 — 企業級（Enterprise-Grade）

**目標**：多維度分析（per intent class × per model version），自動 A/B 評測，合規審計。

**新增元件**：

```
                    ┌─────────────────────────────────────────┐
                    │         Grafana Dashboard               │
                    │  ┌──────────┐  ┌──────────┐  ┌───────┐ │
                    │  │ Ctx Rel  │  │ Grounded │  │AnsRel │ │
                    │  │7d rolling│  │7d rolling│  │7droll │ │
                    │  └──────────┘  └──────────┘  └───────┘ │
                    │  切片：intent_class × model_version     │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         Prometheus + Thanos              │
                    │  長期指標儲存（90天 retention）           │
                    └─────────────────┬───────────────────────┘
                                      │
     ┌──────────────────┐             │
     │  OTel Collector  │─────────────┘
     │  (Gateway mode)  │
     └────────┬─────────┘
              │
   ┌──────────▼──────────┐   ┌─────────────────────┐
   │  RAG Pipeline Pods  │   │  Async Evaluator     │
   │  (emit spans)       │──▶│  Workers (Celery)    │
   └─────────────────────┘   │  計算 Groundedness   │
                              │  NLI + LLM Judge     │
                              └─────────────────────┘
```

**進階功能**：
- **Shadow evaluation**：每 100 個請求中抽 5 個送進 NLI 模型做精準 Groundedness 計算，其餘用 LLM Judge（成本/精度平衡）
- **Regression gate**：CI/CD 管道中，新 prompt template 或 embedding model 上線前須跑 golden dataset 評測，三個指標均不得下降超過 2%
- **Intent-based breakdown**：不同 intent class（如「技術查詢」vs「政策查詢」）的 Groundedness 差異可達 0.15，混合平均會遮蔽問題

**成本估算**：每百萬請求約 $15–40（LLM Judge API） + Prometheus 儲存 $5/月。複雜度：高，需要專責 infra 工程師維護 OTel pipeline。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 用 BLEU/ROUGE 評估 RAG | 這些是 n-gram 重疊指標，設計用於機器翻譯，對「答案有無幻覺」完全無感 | 改用 RAG Triad；BLEU < 0.3 的答案可能完全正確，BLEU > 0.8 的答案可能嚴重幻覺 |
| 只看 Answer Relevance | 答案可以聽起來很相關但充滿幻覺（Groundedness 低） | 三個指標缺一不可；Groundedness 是生產安全的最重要閘門 |
| Groundedness 同步計算阻塞回應 | LLM Judge 需要 200–400ms，用戶等待時間暴增 | 非同步 fire-and-forget：先回應用戶，後台計算指標並寫入 OTel span |
| 以全域平均掩蓋 intent 差異 | 「技術查詢」Groundedness 0.91 + 「法規查詢」0.67 → 平均 0.79，看似安全但法規場景已嚴重幻覺 | 按 intent_class 分群監控，各群獨立設 alert threshold |
| 門檻值一成不變 | 系統上線初期 Groundedness 0.78 可接受，但半年後 query 分布變化，0.78 可能已不足 | 每季根據用戶反饋與業務需求重新校準門檻 |
| 評測集用訓練資料 | Groundedness 虛高（LLM 記住訓練資料，而非真正從 context 推導） | 評測集與訓練資料嚴格隔離；使用真實用戶查詢的隨機樣本 |
| 忽略 Context Relevance 對 Groundedness 的連鎖影響 | 以為 Groundedness 低是 LLM 問題，其實是 retriever 拿回無關文本，LLM 只好「自由發揮」 | 三角診斷：先看 Context Relevance，若 < 0.75 則先修 retriever 再評 Groundedness |

---

## 五、與其他核心主題的關聯

- **向量資料庫與 Hybrid Search（Part 18）**：Context Relevance 的上游。Hybrid Search（向量 + BM25）+ Reranker 是將 Context Relevance 從 0.68 提升至 0.84 的主要手段。
- **LLM 評測與 LLM-as-Judge（Part 17）**：Groundedness 的 LLM Judge 實作方式直接複用 LLM-as-Judge 框架；理解評審 prompt 設計與評分偏差（position bias）是必要前提。
- **OpenTelemetry 分散式追蹤（Part 12）**：RAG Triad 指標透過 OTel span attributes 送進可觀測性管道，需要理解 span、trace context propagation 與 exporter 設定。
- **SLO/SLA 與 Error Budget（Part 15）**：Groundedness < 0.80 可定義為 SLO violation，消耗 error budget，觸發 freeze 新 prompt 版本上線。

---

## 六、面試一句話（Killer Phrase）

> *「RAG 系統的品質評估不能只看一個數字——我使用 RAG Triad 三角指標：Context Relevance 衡量 retriever 是否拿到相關文本（門檻 > 0.75），Groundedness 衡量 LLM 是否忠於 context 而非憑空捏造（< 0.80 觸發 warning，< 0.70 觸發 oncall），Answer Relevance 衡量答案是否真正回答了問題。在生產環境中，我把這三個指標作為 OpenTelemetry span attributes 非同步發送，用 Prometheus 聚合 7 天滾動平均，在 Grafana 按 intent class 與 model version 分群監控——這樣才能在幻覺率惡化的早期發現問題，而非等到用戶投訴。實測數據顯示，加入 hybrid search 與 reranker 後，Groundedness 從 0.71 提升至 0.89，幻覺相關客訴下降了約 60%。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-19-vector-database-zh/) | [後一篇](/posts/fde-interview-core-topic-21-prompt-engineering-zh/) →
