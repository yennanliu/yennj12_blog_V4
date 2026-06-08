---
title: "FDE 面試指南 Part 50：生產環境 GenAI 自動化評估管線與 LLM-as-a-Judge 漂移監控"
date: 2026-06-08T09:00:00+08:00
draft: false
description: "深度解析如何在生產環境中建立多階抽樣的 LLM 自動化評估管線，涵蓋分層抽樣、RAG 三元組評估、位置偏見消除、Drift Alert 設計，以及 95% 成本控制策略。Staff FDE 級別實戰解答。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "GenAI", "LLM", "Evaluation", "MLOps", "Vertex AI", "Observability"]
authors: ["yen"]
readTime: "26 min"
---

> 多數工程師的做法：每次模型更新後，手動抽幾十筆對話，憑感覺評估品質有沒有退步。
> 問題是，樣本量不足無法代表真實用戶分佈，而且人工評估無法在 CI/CD 流程中自動執行。
> 正確的做法：建立三層自動化評估管線，用統計學方法精準抽樣 5% 送 LLM 裁判，
> 其餘 95% 走免費傳統指標，並在 Sigma 2 漂移時自動觸發 PagerDuty 警報。

---

## 面試情境

> 你的團隊正在維護一個 B2B SaaS 平台上的 RAG Agent，每天處理約 50 萬筆客戶支援對話。
> 上週你們將底層模型從 Gemini 1.5 Pro 升級至 Gemini 2.0 Flash，同時調整了 System Prompt。
> 產品團隊要求你在 48 小時內確認新系統的回答品質沒有惡化，並建立一套長期可用的
> 自動化觀測機制。你有 Vertex AI 的使用權限，預算受限，你會怎麼設計這套系統？

---

## 一、核心問題：為什麼 GenAI 的品質監控比傳統服務更難？

傳統後端服務的品質監控相對直觀：HTTP 4xx/5xx 錯誤率、P99 延遲、資料庫查詢失敗數。
這些指標全都是**客觀的、可計算的、接近零成本的**。

GenAI 系統的品質卻天生是**主觀的**：一個回答是否「夠好」，取決於事實準確度、
語氣適切性、上下文相關性、甚至法律合規性。這帶來三個根本性挑戰：

### 挑戰一：評估本身就需要智慧

你無法用 `if response == expected_answer` 來評分自由文本。傳統 BLEU / ROUGE 指標
只能衡量字面重疊，無法判斷語意正確性。唯一可靠的裁判是另一個 LLM——但這就是
**評估成本 ≥ 生產成本**的陷阱：

```
每天 500,000 筆對話
× Gemini 1.5 Pro 裁判費用 $0.00035/1K tokens
× 平均每筆評估消耗 2,000 tokens（含 CoT prompt）
= $350/天 = $10,500/月（僅評估費用）
```

而實際生產環境用 Gemini 2.0 Flash 的費用大約只有 $0.000075/1K tokens，
也就是說**裁判費用可能是生產費用的 4-5 倍**。不做成本控制，評估管線本身就會破產。

### 挑戰二：LLM 裁判天生帶偏見

已有多篇 NeurIPS / ACL 論文記錄了兩個關鍵偏見：

- **Self-enhancement Bias（自我增強偏見）**：GPT-4 偏愛 GPT-4 生成的答案；
  Gemini 偏愛 Gemini 生成的答案，偏好程度比隨機高 10–15%。
- **Position Bias（位置偏見）**：當裁判模型看到 A、B 兩個答案時，
  傾向給排在**第一位**的答案更高分，與品質無關的偏好約 20–30%。

### 挑戰三：漂移是漸進的、難以察覺的

System Prompt 的細微措辭改變、模型版本更新、RAG 知識庫的資料老化——
這些都會造成回答品質的**緩慢下滑**（Gradual Drift），
而不是像 HTTP 500 那樣立即暴露的崩潰。
沒有持續性的統計監控，工程師可能要等到客戶投訴量激增才察覺問題。

---

## 二、三個演進階段

### ╔══ Phase 1（POC / < 10K 用戶）══╗

**目標**：快速建立可用的評估能力，用最低成本驗證評估框架是否有效。

```
┌──────────────────────────────────────────────────────────┐
│                   Phase 1 架構：手動批次評估               │
│                                                          │
│  ┌─────────────────┐    每日 Cron Job                    │
│  │  Cloud Logging  │──────────────────┐                  │
│  │  (生產對話日誌)  │                  ▼                  │
│  └─────────────────┘     ┌───────────────────────┐       │
│                          │  Python 腳本（本地）   │       │
│                          │  隨機抽樣 10% 對話     │       │
│                          │  計算 BLEU / ROUGE     │       │
│                          └──────────┬────────────┘       │
│                                     │                    │
│                                     ▼                    │
│                          ┌───────────────────────┐       │
│                          │  Gemini API 裁判       │       │
│                          │  (同步呼叫，無管線)    │       │
│                          └──────────┬────────────┘       │
│                                     │                    │
│                                     ▼                    │
│                          ┌───────────────────────┐       │
│                          │  試算表 / CSV 匯出      │       │
│                          │  人工檢視結果           │       │
│                          └───────────────────────┘       │
└──────────────────────────────────────────────────────────┘
```

**新增元件（vs 無評估）**：
- Cloud Logging Export（免費層級）
- Python 評估腳本（本地執行，無基礎建設費用）
- Gemini API 裁判呼叫（按量計費）

**成本/複雜度**：
- 每日評估費用約 $2–5（10% 抽樣，Gemini Flash 裁判）
- 無需 Kubernetes 或 Vertex AI Pipelines
- 部署時間：1 名工程師 3 天可完成

**尚待解決的問題**：
- 抽樣無分層，可能遺漏特定租戶或意圖類別的品質退化
- 無即時警報，只有每日批次報告
- 裁判 Prompt 未做偏見控制
- 結果存在試算表，難以與 CI/CD 整合

---

### ╔══ Phase 2（MVP / 10K–200K 用戶）══╗

**目標**：建立具備統計代表性的分層抽樣、消除裁判偏見、接入基本警報系統。

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Phase 2 架構：結構化評估管線                    │
│                                                                      │
│  ┌──────────────┐  Log Sink   ┌──────────────┐                      │
│  │ Cloud Logging│────────────▶│  BigQuery    │                      │
│  │ (100% logs)  │             │  eval_logs   │                      │
│  └──────────────┘             └──────┬───────┘                      │
│                                      │ 分層抽樣 SQL                  │
│                                      ▼                               │
│              ┌───────────────────────────────────────┐              │
│              │         第一階：輕量指標（100%）        │              │
│              │  BLEU / ROUGE / 重複率 / 長度變異度     │              │
│              │  Tool-calling 失敗率 / 空回答率         │              │
│              └────────────────┬──────────────────────┘              │
│                               │ 異常樣本標記                          │
│                               ▼                                      │
│              ┌───────────────────────────────────────┐              │
│              │    第二階：LLM 裁判（5% 分層抽樣）      │              │
│              │  Vertex AI Pipelines (DAG)             │              │
│              │  CoT Prompt + 位置隨機化               │              │
│              │  RAG 三元組打分（F/R/C）               │              │
│              └────────────────┬──────────────────────┘              │
│                               │                                      │
│                               ▼                                      │
│              ┌───────────────────────────────────────┐              │
│              │   Prometheus → Grafana Dashboard        │              │
│              │   週移動平均 ± Sigma 2 警報線           │              │
│              └────────────────┬──────────────────────┘              │
│                               │ 觸發警報                             │
│                               ▼                                      │
│              ┌───────────────────────────────────────┐              │
│              │   Cloud Monitoring → Email / Slack     │              │
│              └───────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────┘
```

**新增元件（vs Phase 1）**：
- BigQuery Log Sink（結構化儲存全量日誌）
- Vertex AI Pipelines（DAG 管線，可重現、可稽核）
- 分層抽樣 SQL（按租戶 + 意圖分類）
- CoT 裁判 Prompt + 位置隨機化邏輯
- Prometheus + Grafana（指標視覺化與警報）

**成本/複雜度**：
- 每日評估費用約 $8–15（5% 抽樣，RAG 三元組 CoT Prompt ≈ 3,000 tokens/筆）
- 每月 BigQuery 儲存費用約 $20–50（視對話大小）
- 部署時間：2 名工程師 2 週

**尚待解決的問題**：
- 無 Shadow Evaluation（新模型上線前無法做對比評估）
- Grafana 警報規則需人工維護
- 大規模裁判呼叫無速率限制保護，峰值可能超出配額

---

### ╔══ Phase 3（Scale / 200K–1M+ 用戶）══╗

**目標**：企業級自動化，支援多模型 A/B 對比、Shadow Evaluation、
自動化品質閘門（Quality Gate）整合 CI/CD 流程。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Phase 3 架構：企業級評估平台                          │
│                                                                             │
│  ┌─────────────┐  Pub/Sub   ┌──────────────────┐                           │
│  │ Cloud       │───────────▶│  BigQuery        │                           │
│  │ Logging     │            │  (分區表，依日期) │                           │
│  │ (100% logs) │            └────────┬─────────┘                           │
│  └─────────────┘                     │                                     │
│                                      ▼                                     │
│          ┌───────────────────────────────────────────────────────┐         │
│          │              第一階：無成本指標（100% 即時）            │         │
│          │  Dataflow Streaming Pipeline                           │         │
│          │  ├── BLEU / ROUGE / 重複率                            │         │
│          │  ├── Tool-calling 失敗率                               │         │
│          │  ├── 語言一致性檢測                                    │         │
│          │  └── 有害內容關鍵字掃描                                │         │
│          └──────────────────────┬────────────────────────────────┘         │
│                                 │ 5% 分層抽樣                               │
│                                 ▼                                           │
│          ┌───────────────────────────────────────────────────────┐         │
│          │       第二階：LLM 裁判（Vertex AI Pipelines）           │         │
│          │  ┌─────────────────┐    ┌──────────────────────────┐  │         │
│          │  │  RAG 三元組評估  │    │  Shadow Evaluation        │  │         │
│          │  │  Faithfulness   │    │  (新模型 vs 舊模型 1%)     │  │         │
│          │  │  Relevance      │    │  A/B Score Comparison     │  │         │
│          │  │  Completeness   │    └──────────────────────────┘  │         │
│          │  └─────────────────┘                                  │         │
│          └──────────────────────┬────────────────────────────────┘         │
│                                 │                                           │
│                                 ▼                                           │
│          ┌───────────────────────────────────────────────────────┐         │
│          │           Prometheus + Grafana + Alert Manager         │         │
│          │  ├── 週移動平均 Sigma 2 漂移偵測                       │         │
│          │  ├── 租戶級別品質分群                                  │         │
│          │  └── 意圖分類品質熱力圖                                │         │
│          └──────────────────────┬────────────────────────────────┘         │
│                                 │                                           │
│          ┌──────────────────────▼────────────────────────────────┐         │
│          │                  雙路警報與閘門                          │         │
│          │  ┌──────────────┐    ┌────────────────────────────┐   │         │
│          │  │ PagerDuty    │    │  CI/CD Quality Gate         │   │         │
│          │  │ (P1 警報)    │    │  (PR 合併前品質驗證)         │   │         │
│          │  └──────────────┘    └────────────────────────────┘   │         │
│          └───────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**新增元件（vs Phase 2）**：
- Cloud Pub/Sub（異步解耦，日誌串流到 BigQuery 無延遲）
- Dataflow Streaming（第一階指標從批次改為即時串流計算）
- Shadow Evaluation 模組（1% 流量做新舊模型對比）
- CI/CD Quality Gate（PR 合併前在 staging 環境跑評估，未達門檻阻斷合併）
- 租戶級品質分群（Tenant-level Quality Segmentation）
- 意圖分類品質熱力圖（Intent × Quality 二維視覺化）

**成本/複雜度**：
- 每日評估費用約 $25–50（規模化後攤分，含 Shadow 評估）
- 部署時間：3 名工程師 6 週（含 CI/CD 整合）
- 每月平台運維費用約 $300–500（Dataflow + BigQuery + Vertex AI Pipelines）

---

## 三、分層抽樣設計：確保統計代表性

### 為什麼隨機抽樣不夠？

假設你有以下用戶分佈：

| 租戶類型 | 日對話量 | 佔比 |
|---------|---------|------|
| 大型企業（Top 10） | 200,000 | 40% |
| 中型企業（100 家） | 200,000 | 40% |
| 小型用戶（10,000 家） | 100,000 | 20% |

如果純隨機抽樣 5%，你會得到 25,000 筆，其中小型用戶只有 5,000 筆。
但小型用戶的 intent 分佈與大型企業完全不同——如果某個 intent 類別只有 300 筆對話，
隨機抽到的可能只有 15 筆，**樣本量不足以做統計顯著性檢定**（Z-test 最低需要 30 筆）。

### 分層抽樣公式

```python
import math

def stratified_sample_size(population_size: int,
                           confidence: float = 0.95,
                           margin_of_error: float = 0.05,
                           p: float = 0.5) -> int:
    """
    計算每個分層所需的最小樣本量
    population_size: 該分層的母體大小
    confidence: 信心水準（0.95 = 95%）
    margin_of_error: 誤差範圍（0.05 = ±5%）
    p: 估計比例（保守估計用 0.5）
    """
    z = 1.96  # 95% 信心水準的 Z 值
    n_0 = (z**2 * p * (1 - p)) / (margin_of_error**2)
    # 有限母體修正
    n = n_0 / (1 + (n_0 - 1) / population_size)
    return math.ceil(n)

# 範例：某意圖分類有 500 筆對話
# 最小樣本量 = 218 筆（95% 信心，±5% 誤差）
# 遠超過 5% 隨機抽樣的 25 筆
```

### BigQuery 分層抽樣 SQL

```sql
-- 按租戶 + 意圖分類做分層抽樣
WITH base AS (
  SELECT
    conversation_id,
    tenant_id,
    intent_category,
    response_text,
    retrieved_context,
    user_query,
    -- 在分層內做隨機排序
    ROW_NUMBER() OVER (
      PARTITION BY tenant_id, intent_category
      ORDER BY RAND()
    ) AS rn,
    COUNT(*) OVER (
      PARTITION BY tenant_id, intent_category
    ) AS stratum_size
  FROM `project.eval_logs.conversations`
  WHERE DATE(created_at) = CURRENT_DATE() - 1
    AND is_sampled = FALSE  -- 避免重複抽樣
),
sample_targets AS (
  SELECT
    tenant_id,
    intent_category,
    -- 動態計算每個分層的抽樣上限（最少 30 筆，最多 200 筆）
    LEAST(200, GREATEST(30, CAST(stratum_size * 0.05 AS INT64))) AS target_n
  FROM base
  GROUP BY tenant_id, intent_category, stratum_size
)
SELECT b.*
FROM base b
JOIN sample_targets t
  ON b.tenant_id = t.tenant_id
  AND b.intent_category = t.intent_category
WHERE b.rn <= t.target_n;
```

---

## 四、RAG 三元組評估與 CoT 裁判設計

### RAG 三元組定義

RAG 系統的品質由三個維度決定，缺一不可：

| 維度 | 英文 | 評估問題 | 常見失敗模式 |
|------|------|---------|------------|
| 忠實度 | Faithfulness | 回答是否完全基於 Context，沒有幻覺？ | 模型「補充」了 Context 中沒有的資訊 |
| 相關度 | Relevance | 回答是否直接回應了用戶問題？ | 回答正確但答非所問 |
| 完整性 | Completeness | 是否涵蓋了 Context 中所有相關資訊？ | 只回答了問題的一半 |

### CoT 裁判 Prompt 設計

強制 Chain-of-Thought 的關鍵在於**先輸出理由，再輸出分數**，
防止模型「反推理由合理化預設答案」的懶惰評分行為：

```python
JUDGE_PROMPT_TEMPLATE = """
你是一位嚴格的 RAG 系統品質評審員。請評估以下對話的品質。

## 用戶問題
{user_query}

## 檢索到的 Context（{context_position}）
{context_text}

## 系統回答（{answer_position}）
{answer_text}

---
請依以下格式輸出（必須先給理由，後給分數）：

### 忠實度評估
**理由**：[詳細說明回答中哪些部分有 / 沒有 Context 依據，列出具體句子]
**分數**：[1-5 的整數，1=嚴重幻覺，5=完全基於 Context]

### 相關度評估
**理由**：[詳細說明回答是否直接回應了問題，哪些部分偏離了問題]
**分數**：[1-5 的整數，1=完全不相關，5=精準回應]

### 完整性評估
**理由**：[說明 Context 中有哪些重要資訊沒有被包含在回答中]
**分數**：[1-5 的整數，1=嚴重遺漏，5=完整涵蓋]

### 最終判定
**總分**：[三項平均分，保留一位小數]
"""

def build_judge_prompt(sample: dict) -> str:
    """動態隨機化 Context 和 Answer 的位置，消除 Position Bias"""
    import random
    if random.random() > 0.5:
        # Context 在前
        return JUDGE_PROMPT_TEMPLATE.format(
            user_query=sample['user_query'],
            context_position="輸入 A",
            context_text=sample['retrieved_context'],
            answer_position="輸入 B",
            answer_text=sample['response_text']
        )
    else:
        # Answer 在前（交換位置）
        return JUDGE_PROMPT_TEMPLATE.format(
            user_query=sample['user_query'],
            context_position="輸入 B",
            context_text=sample['retrieved_context'],
            answer_position="輸入 A",
            answer_text=sample['response_text']
        )
```

### 位置偏見消除的統計驗證

執行一段時間後，可以用以下方法驗證位置偏見是否已被消除：

```python
# 將同一批樣本分別以 Context-First 和 Answer-First 順序送評
# 理想情況：兩組分數的 Wilcoxon Signed-Rank Test p-value > 0.05（無顯著差異）
from scipy.stats import wilcoxon

scores_context_first = [...]  # n 筆
scores_answer_first = [...]   # 同 n 筆，順序交換

stat, p_value = wilcoxon(scores_context_first, scores_answer_first)
if p_value < 0.05:
    # 仍存在顯著位置偏見，需要調整 Prompt
    alert("Position bias detected, p={:.4f}".format(p_value))
```

---

## 五、漂移偵測：Sigma 2 警報設計

### 週移動平均線 + 控制圖方法

```
品質分數趨勢圖（忠實度，週移動平均）

5.0 ┤
    │
4.5 ┤         ████████████
    │        █            █
4.0 ┤   ████              █████
    │  █                       █
3.5 ┤ █                         ████← Sigma 2 上界 = μ + 2σ
    │                               ████
3.0 ┤────────────────────────────────────← μ（歷史均值）
    │                                   ████
2.5 ┤────────────────────────────────────────← Sigma 2 下界 = μ - 2σ
    │                                       ▼ 警報觸發點
2.0 ┤                                        ████
    │
1.5 ┤
    └───────────────────────────────────────────────
    Week 1   Week 2   Week 3   Week 4   Week 5
```

### Prometheus 指標設計

```python
from prometheus_client import Gauge, Histogram, Counter

# 週移動平均指標（按租戶和意圖分類維度）
rag_faithfulness_score = Gauge(
    'rag_faithfulness_score',
    'RAG faithfulness score (7-day moving average)',
    ['tenant_id', 'intent_category', 'model_version']
)

rag_relevance_score = Gauge(
    'rag_relevance_score',
    'RAG relevance score (7-day moving average)',
    ['tenant_id', 'intent_category', 'model_version']
)

# 評估管線的監控指標
eval_pipeline_duration = Histogram(
    'eval_pipeline_duration_seconds',
    'Time taken to complete evaluation pipeline',
    buckets=[60, 300, 600, 1800, 3600]
)

judge_api_errors = Counter(
    'judge_api_errors_total',
    'Total LLM judge API errors',
    ['error_type', 'model_version']
)
```

### Grafana Alert Rule（YAML）

```yaml
# grafana/alerts/rag_drift_alert.yaml
groups:
  - name: rag_quality_drift
    interval: 1h
    rules:
      - alert: RAGFaithfulnessDrift
        expr: |
          (
            avg_over_time(rag_faithfulness_score[7d])
            - avg_over_time(rag_faithfulness_score[30d] offset 7d)
          )
          / stddev_over_time(rag_faithfulness_score[30d] offset 7d)
          < -2  # Sigma 2 下界
        for: 6h  # 持續 6 小時才觸發，避免誤報
        labels:
          severity: critical
          team: fde
        annotations:
          summary: "RAG 忠實度分數下滑超過 2 個標準差"
          description: |
            租戶 {{ $labels.tenant_id }} 的忠實度週均分
            較歷史基線下滑 {{ $value | printf "%.2f" }} 個標準差。
            可能原因：模型版本更新、Prompt 漂移、知識庫資料過期。
          runbook_url: "https://wiki.internal/runbooks/rag-drift"
```

---

## 六、Shadow Evaluation：新模型上線前的 A/B 對比

### Shadow Traffic 架構

```
┌─────────────────────────────────────────────────────────────────┐
│                    Shadow Evaluation 流程                        │
│                                                                 │
│  用戶請求                                                        │
│      │                                                          │
│      ▼                                                          │
│  ┌───────────┐   99% 流量   ┌─────────────────┐               │
│  │  API      │─────────────▶│  生產模型 (v1)   │──▶ 用戶回應   │
│  │  Gateway  │              │  Gemini 2.0 Flash│               │
│  └─────┬─────┘              └─────────────────┘               │
│        │                                                        │
│        │ 1% 流量複製（非同步，不影響延遲）                       │
│        ▼                                                        │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │  Pub/Sub Topic  │────────▶│  Shadow 模型(v2) │               │
│  │  (shadow_eval)  │         │  Gemini 2.5 Pro  │               │
│  └─────────────────┘         └────────┬────────┘               │
│                                       │ 回應（丟棄，不回用戶）   │
│                                       ▼                         │
│                               ┌───────────────────┐            │
│                               │  BigQuery          │            │
│                               │  shadow_eval_logs  │            │
│                               └────────┬──────────┘            │
│                                        │                        │
│                                        ▼                        │
│                               ┌───────────────────┐            │
│                               │  LLM 裁判對比評分  │            │
│                               │  v1 vs v2 A/B      │            │
│                               │  Mann-Whitney U 檢定│            │
│                               └────────┬──────────┘            │
│                                        │                        │
│                                   通過 → 批准上線               │
│                                   不通過 → 阻斷部署              │
└─────────────────────────────────────────────────────────────────┘
```

### Shadow 評估的統計判定標準

```python
from scipy.stats import mannwhitneyu
import numpy as np

def should_approve_model_upgrade(
    v1_scores: list[float],
    v2_scores: list[float],
    min_improvement: float = 0.05,  # 新模型至少要好 5%
    alpha: float = 0.05
) -> dict:
    """
    判定新模型是否可以安全上線
    使用非參數檢定（不假設分數服從常態分佈）
    """
    # Mann-Whitney U 檢定（雙尾）
    stat, p_value = mannwhitneyu(v2_scores, v1_scores, alternative='two-sided')

    v1_mean = np.mean(v1_scores)
    v2_mean = np.mean(v2_scores)
    improvement = (v2_mean - v1_mean) / v1_mean

    decision = (
        p_value < alpha and           # 統計顯著
        improvement >= min_improvement # 實質改善
    )

    return {
        'approved': decision,
        'v1_mean': v1_mean,
        'v2_mean': v2_mean,
        'improvement_pct': improvement * 100,
        'p_value': p_value,
        'reason': (
            f"v2 比 v1 改善 {improvement*100:.1f}%，p={p_value:.4f}"
            if decision else
            f"未達標（改善 {improvement*100:.1f}%，p={p_value:.4f}）"
        )
    }
```

---

## 七、Vertex AI Pipelines 管線實作

### 管線 DAG 設計

```python
from kfp import dsl
from kfp.dsl import component, pipeline

@component(base_image="python:3.11")
def extract_samples(
    bq_project: str,
    eval_date: str,
    output_gcs_path: dsl.Output[dsl.Dataset]
):
    """從 BigQuery 執行分層抽樣，輸出到 GCS"""
    # 執行前述分層抽樣 SQL
    pass

@component(base_image="python:3.11")
def compute_lightweight_metrics(
    samples: dsl.Input[dsl.Dataset],
    metrics_output: dsl.Output[dsl.Metrics]
):
    """計算 BLEU / ROUGE / 重複率等無成本指標"""
    pass

@component(base_image="python:3.11")
def run_llm_judge(
    samples: dsl.Input[dsl.Dataset],
    model_name: str,
    judge_scores: dsl.Output[dsl.Dataset]
):
    """呼叫 Gemini 裁判，含 CoT 和位置隨機化"""
    # 加入指數退避重試 + 速率限制保護
    # max_workers=10（避免超出 Gemini API quota）
    pass

@component(base_image="python:3.11")
def push_metrics_to_prometheus(
    judge_scores: dsl.Input[dsl.Dataset],
    prometheus_pushgateway_url: str
):
    """將評估分數推送到 Prometheus Pushgateway"""
    pass

@pipeline(name="rag-eval-pipeline")
def rag_evaluation_pipeline(
    bq_project: str,
    eval_date: str,
    model_name: str = "gemini-2.0-flash-001",
    prometheus_url: str = "http://pushgateway:9091"
):
    extract_task = extract_samples(
        bq_project=bq_project,
        eval_date=eval_date
    )
    metrics_task = compute_lightweight_metrics(
        samples=extract_task.outputs['output_gcs_path']
    )
    judge_task = run_llm_judge(
        samples=extract_task.outputs['output_gcs_path'],
        model_name=model_name
    ).after(metrics_task)  # 確保輕量指標先跑完
    push_task = push_metrics_to_prometheus(
        judge_scores=judge_task.outputs['judge_scores'],
        prometheus_pushgateway_url=prometheus_url
    )
```

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|-----------|-------------|----------------|
| **Vertex AI Pipelines vs 自建 Airflow** | 原生整合 BigQuery / Gemini API，無需維護 K8s 叢集；自動版本管理，管線可重現 | Airflow 需要自建 K8s，維護成本 $200+/月；DAG 調試困難，缺乏 ML 原生資料型別 | 若已有 Airflow 基礎建設且日均執行 > 100 個 DAG，遷移成本不划算 |
| **BigQuery Log Sink vs Elasticsearch** | BigQuery 與 Dataflow / SQL 生態原生整合；分區表讓歷史查詢成本極低；按量計費 | Elasticsearch 叢集需預置容量，50GB/天日誌約需 $500+/月固定費用；無原生 ML 整合 | 若已有 Elasticsearch 且需要全文搜尋能力，遷移成本 > 6 個月，暫保留 |
| **CoT Prompt（理由先於分數）vs 直接評分** | CoT 強制模型顯式推理，懶惰評分機率降低 40%（實測）；評分可稽核，便於 debug | 直接評分 token 消耗少 30%，但分數方差大，同一樣本重複評估標準差 σ ≈ 0.8 vs CoT 的 σ ≈ 0.3 | 若預算極度受限且只需粗略趨勢，可用直接評分節省 30% 裁判費用 |
| **分層抽樣（5%）vs 全量 LLM 裁判** | 5% 抽樣在 95% 信心水準下誤差 ±3%，足以偵測顯著品質退化；節省 95% 裁判費用 | 全量裁判成本 ≈ $350/天，且評估排隊延遲會讓 SLA 從 2 小時拉長到 12+ 小時 | 法規合規場景（金融 / 醫療）需要 100% 審計日誌時，考慮混合方案：全量輕量指標 + 全量人工抽查 |
| **週移動平均 + Sigma 2 vs 固定閾值警報** | 移動平均可自動適應季節性波動（如節假日對話品質自然下滑）；Sigma 2 = 95.4% 的正常範圍，誤報率低 | 固定閾值（如「分數 < 3.5 就警報」）在模型升級後需手動調整基線，維護成本高；誤報率通常高 20–30% | 若業務有明確的 SLA 品質下限（如「忠實度必須 ≥ 4.0」），固定閾值更直觀且易於向非技術管理層解釋 |
| **Pub/Sub 解耦 vs 同步寫入 BigQuery** | 非同步解耦讓日誌管線不影響生產路徑延遲；Pub/Sub 可重播消息，防止 BigQuery 寫入失敗導致數據遺失 | 同步寫入若 BigQuery 出現 503 或 quota 超限，會傳播錯誤到生產 API，P99 延遲增加 50–200ms | 若日誌量 < 1,000 筆/天，直接寫 BigQuery 成本更低且架構更簡單 |

---

## 九、成本分析：三層架構如何降低 95% 評估費用

### 評估成本拆解

假設場景：每天 500,000 筆對話，平均每筆 1,500 tokens 輸入 + 500 tokens 輸出

| 評估策略 | 每日評估量 | 每筆 Token 成本 | 每日費用 | 每月費用 |
|---------|---------|--------------|---------|---------|
| 全量 LLM 裁判（樸素方案） | 500,000 筆 | 3,000 tokens × $0.00035/1K = $0.00105 | $525 | $15,750 |
| 三層架構（5% 抽樣） | 25,000 筆 | 同上 | $26.25 | $787.50 |
| **節省** | — | — | **$498.75/天** | **$14,962.50/月** |

第一層（輕量指標，100% 對話）的成本幾乎為零——BLEU/ROUGE 計算純 CPU，
每 10 萬筆對話在 Dataflow 上的計算費用約 $0.50。

---

## 十、系統效應：導入評估管線前後對比

| 指標 | 導入前 | 導入後（Phase 2）| 導入後（Phase 3）| 說明 |
|------|-------|---------------|---------------|------|
| **品質退化偵測時間** | 5–7 天（等客訴） | 24 小時（批次評估） | 2–6 小時（Dataflow 串流 + 即時警報） | 從被動反應到主動偵測 |
| **每次模型升級驗證成本（人工）** | $2,000–5,000（3–5 名工程師 × 2 天） | $200–500（自動化，人工只審 Sigma 異常） | $50–150（CI/CD 自動閘門，人工接近零） | 節省 90%+ 人工成本 |
| **模型升級失敗上線率** | ~15%（無系統性驗證） | ~5%（Shadow 評估 + 抽樣驗證） | < 1%（A/B 統計顯著性閘門） | 避免品質退化到達用戶 |
| **每日 LLM 裁判費用** | — | $20–30 | $25–50（含 Shadow） | 95% vs 全量評估的成本節省 |
| **評估覆蓋率（統計代表性）** | 0%（無評估）或 < 1%（人工） | 5%（分層，具統計代表性） | 5% LLM 裁判 + 100% 輕量指標 | 分層 > 隨機 > 人工 |
| **漂移警報誤報率** | — | 8–12%（初期，Sigma 2 基線需 2 週建立） | < 3%（移動基線 + Sigma 2，穩定後） | 週移動平均適應季節性 |
| **第一層指標計算延遲** | — | 15–30 分鐘（批次） | < 60 秒（Dataflow 串流） | 近即時品質監控 |
| **RAG 忠實度提升（副作用）** | 基線 3.2/5 | 3.8/5（評估本身迫使 Prompt 改善） | 4.2/5（持續迭代優化） | 評估驅動改進 |

---

## 十一、面試答題要點

> *「面對 GenAI 品質監控，我會建立三層自動化評估管線：第一層對 100% 的生產日誌跑免費的輕量指標（BLEU、Tool-calling 失敗率），捕捉顯而易見的退化；第二層用統計學分層抽樣精準抽取 5% 的代表性對話，按租戶和意圖分類確保每個分層都有足夠樣本（最少 30 筆），送入 Vertex AI Pipelines 跑 LLM 裁判；裁判設計上，用 Chain-of-Thought 強制先輸出理由再給分，並動態隨機交換 Context 和 Answer 的輸入順序來消除 Position Bias——這兩個設計讓評分方差從 σ=0.8 降到 σ=0.3。監控層用週移動平均 Sigma 2 控制圖取代固定閾值，當 RAG 三元組任一維度下滑超過兩個標準差時，Cloud Monitoring 自動觸發 PagerDuty P1 警報。新模型上線前，先在 1% 影子流量上做 A/B 對比，用 Mann-Whitney U 檢定驗證改善是否統計顯著，這套流程讓模型升級失敗上線率從 15% 降到 1% 以下，同時把每日裁判費用控制在 $25–50，比全量評估節省 95%。」*

---

## 延伸閱讀

- [Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges](https://arxiv.org/abs/2406.12624)（NeurIPS 2024）
- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217)（2023）
- [Large Language Models are not Fair Evaluators](https://arxiv.org/abs/2305.17926)（ACL 2024，Position Bias 分析）
- Vertex AI Pipelines 官方文件：自動化 ML 評估管線建置指南

---

**系列導航**

← [Part 49：FDE 面試指南 Part 49](/posts/fde-interview-guide-part49-multi-agent-orchestration-zh/) | [Part 51：FDE 面試指南 Part 51](/posts/fde-interview-guide-part51-zh/) →
