---
title: "AI 工程從零開始｜Phase 17 Part 2：AI 系統可觀測性 — 當模型行為成為監控對象"
date: 2026-06-22T03:00:00+08:00
draft: false
weight: 37
description: "深入解析 AI 系統可觀測性工程：LLM 追蹤（Traces/Spans）、提示版本管理、模型效能漂移偵測、成本歸因分析與 AI 告警策略"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Infrastructure", "Observability", "Monitoring", "LLM", "Tracing", "Production", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> 大多數工程師把 LLM 呼叫當成黑箱：記錄 HTTP 狀態碼、回應時間，然後就沒了。
> 正確的做法是：追蹤每一個 Prompt 版本、每一次工具呼叫、每一個 Token 成本，並量化模型行為漂移。
> 傳統 APM 只告訴你系統「掛了沒」；AI 可觀測性要告訴你模型「答得好不好」。
> 沒有這層監控，你永遠不知道提示更新讓答案品質下降了 12%，還是模型供應商悄悄換了版本。

---

## 面試情境

**面試官問：**「你們的 RAG 問答系統上線後，客服主管反應『最近答案怪怪的』，但 p99 延遲和錯誤率都正常。你身為 SRE/AI 工程師，會怎麼設計可觀測性系統來定位這類問題？請說明你的 Traces 設計、漂移偵測機制，以及如何在成本和覆蓋率之間取得平衡。」

---

## 一、核心問題：AI 系統的可觀測性為什麼與傳統系統不同

傳統服務的可觀測性三支柱——Metrics、Logs、Traces——在 AI 系統上全都「不夠用」，但原因各不相同。

**傳統系統的失敗模式是二元的**：請求成功或失敗，HTTP 200 或 500，延遲高或低。失敗有明確的邊界。當資料庫 query 耗時 800ms，你知道哪裡壞了。

**AI 系統的失敗模式是漸進的、語意的**：
- 模型回傳 HTTP 200，但答案從準確滑向「有點對但不夠精確」
- Prompt 被改了一個詞，召回率悄悄下降 8%
- 供應商在 2AM 更新基礎模型，語氣風格改變，用戶滿意度在 48 小時後才反映在 CSAT
- Token 用量因為對話上下文累積，每週成本靜靜地增長 15%

這就是為什麼 AI 可觀測性需要新的維度：

| 維度 | 傳統系統 | AI 系統 |
|------|---------|---------|
| 品質訊號 | Error rate, p99 latency | 語意相似度、答案忠實度、幻覺率 |
| 版本追蹤 | Code git SHA | Prompt version + Model version + RAG index version |
| 成本單元 | CPU/Memory/Network | Input tokens + Output tokens + Embedding calls |
| 漂移型態 | 無（確定性系統） | 概念漂移、分佈漂移、模型版本漂移 |
| 告警閾值 | 靜態（> 500ms alert） | 動態（品質分數 7 日移動平均下降 > 5%） |

面試官問的「答案怪怪的」就是典型的**語意品質退化**。系統層面一切正常，但輸出品質已悄悄崩潰。沒有 AI-native 可觀測性，這種問題的 MTTR 往往超過 3 天。

---

## 二、三個演進階段（POC / MVP / Scale）

### ╔══════════════════════════════════════╗
### ║  Phase 1：POC（< 10K 用戶）          ║
### ╚══════════════════════════════════════╝

**核心假設**：先讓系統跑起來，可觀測性夠用就好。

```
┌──────────────────────────────────────────────┐
│                  LLM 應用                     │
│  ┌──────────┐    ┌──────────┐                │
│  │  FastAPI  │───▶│ LLM SDK  │               │
│  └────┬─────┘    └────┬─────┘               │
│       │               │                      │
│       ▼               ▼                      │
│  ┌──────────────────────────┐                │
│  │   Stdout / File Logs     │                │
│  │  (prompt, response, ms)  │                │
│  └──────────────────────────┘                │
└──────────────────────────────────────────────┘
```

**新增組件**：結構化 JSON 日誌（prompt text, model, latency_ms, token counts）。

**成本/複雜度**：每月 $0 額外基礎設施，0.5 工程師天設定。

**解決的問題**：
- 知道每次呼叫的 Token 用量
- 可以手動翻 log 查問題

**未解決的問題**：
- 無法追蹤跨服務的完整請求鏈
- 無版本管理，無法比較 prompt 修改前後
- 成本歸因粒度只到「整個系統」

---

### ╔══════════════════════════════════════╗
### ║  Phase 2：MVP（10K–200K 用戶）       ║
### ╚══════════════════════════════════════╝

**核心假設**：開始有足夠流量讓統計指標有意義，需要主動監控而非被動翻 log。

```
┌────────────────────────────────────────────────────────┐
│                    LLM 應用叢集                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │  FastAPI  │───▶│ LLM SDK  │───▶│  Prompt Registry │  │
│  └────┬─────┘    └────┬─────┘    └──────────────────┘  │
│       │               │                                  │
│       ▼               ▼                                  │
│  ┌────────────────────────────────────────────────┐     │
│  │          OpenTelemetry Collector               │     │
│  └───────┬──────────────────────────┬────────────┘     │
│           │                          │                   │
│           ▼                          ▼                   │
│  ┌──────────────┐          ┌──────────────────────┐     │
│  │  Jaeger/     │          │  Prometheus +         │     │
│  │  Tempo       │          │  Grafana              │     │
│  │  (Traces)    │          │  (Metrics/Alerts)     │     │
│  └──────────────┘          └──────────────────────┘     │
└────────────────────────────────────────────────────────┘
```

**新增組件**：
- OpenTelemetry 自動埋點 + 手動 Span（Prompt 版本 ID 注入 Trace Context）
- Prompt Registry（版本 hash + 部署時間戳）
- Prometheus 收集 Token 用量、品質分數（透過非同步評估 worker）

**成本/複雜度**：基礎設施 $200–500/月（Grafana Cloud 或自建），1.5 工程師週設定。

**解決的問題**：
- 端對端 Trace 可見度，可看到 RAG 檢索 + LLM 呼叫的完整鏈路
- Prompt 版本變更可比較前後品質指標
- Token 成本按功能模組分組

**未解決的問題**：
- 品質評估仍是規則式（無語意品質分數）
- 無模型漂移偵測
- 成本歸因無法細到「每個用戶」

---

### ╔══════════════════════════════════════╗
### ║  Phase 3：Scale（200K–1M+ 用戶）    ║
### ╚══════════════════════════════════════╝

**核心假設**：規模夠大，每個百分點的品質退化都影響數千用戶和數萬美元成本。

```
┌──────────────────────────────────────────────────────────────┐
│                      AI 可觀測性平台                           │
│                                                              │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │  LLM 應用   │──▶│  OTel SDK    │──▶│  Telemetry       │  │
│  │  叢集       │   │  + AI Plugin  │   │  Pipeline        │  │
│  └─────────────┘   └──────────────┘   └────────┬─────────┘  │
│                                                  │            │
│              ┌───────────────────────────────────┤            │
│              │               │                   │            │
│              ▼               ▼                   ▼            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Trace Store  │  │  Metrics DB  │  │  LLM Quality     │   │
│  │  (Tempo)      │  │  (Thanos)    │  │  Evaluator       │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                     │             │
│         └─────────────────┴─────────────────────┘            │
│                                 │                             │
│                    ┌────────────▼────────────┐               │
│                    │  AI Observability Hub    │               │
│                    │  - Drift Detection       │               │
│                    │  - Cost Attribution      │               │
│                    │  - Prompt A/B Analysis   │               │
│                    │  - Alert Engine          │               │
│                    └─────────────────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

**新增組件**：
- LLM Quality Evaluator（非同步，使用輕量模型評估答案忠實度、相關性）
- Drift Detection Service（統計檢驗：KS test、PSI）
- Cost Attribution Engine（按 user_id / feature / model 的細粒度計費）
- Thanos（長期 Metrics 儲存，支援跨叢集查詢）

**成本/複雜度**：基礎設施 $2,000–8,000/月，3–4 工程師月建置，0.5 FTE 維護。

**解決的問題**：
- 語意品質漂移在 < 2 小時內偵測到（vs 之前 2–3 天）
- 成本細粒度到每個 feature × user segment
- 自動化 Prompt A/B 測試，有統計顯著性判斷

**未解決的問題**（Scale 後的下一步）：
- 需要人類評估者校準自動品質分數
- 跨模型供應商的統一 Trace 格式仍有缺口

---

## 三、LLM 追蹤：Prompt / Completion / Tool Call 的 Span 設計

傳統 Trace 只有「服務呼叫」這個維度。LLM 系統需要更細的 Span 層級，對應 AI 特有的執行單元。

```
Trace: user_request_abc123
│
├── Span: api_handler [5ms]
│   ├── attr: user_id=u_456, feature=qa_search
│   │
│   ├── Span: rag_retrieval [120ms]
│   │   ├── attr: query_embedding_model=text-embed-v3
│   │   ├── attr: top_k=5, similarity_threshold=0.75
│   │   ├── attr: docs_retrieved=5, docs_filtered=3
│   │   └── attr: retrieval_latency_ms=118
│   │
│   ├── Span: prompt_construction [3ms]
│   │   ├── attr: prompt_version=v2.3.1
│   │   ├── attr: prompt_hash=sha256:4a7f...
│   │   ├── attr: context_tokens=1840
│   │   └── attr: system_tokens=256
│   │
│   └── Span: llm_completion [890ms]
│       ├── attr: model=claude-3-5-sonnet
│       ├── attr: input_tokens=2096, output_tokens=312
│       ├── attr: cost_usd=0.00847
│       ├── attr: finish_reason=stop
│       ├── attr: temperature=0.3
│       └── Span: tool_call:search_web [340ms]
│           ├── attr: tool_name=search_web
│           ├── attr: tool_input={"query": "..."}
│           └── attr: tool_output_tokens=580
```

**關鍵設計決策：Span 屬性的標準化**

每個 LLM Span 必須攜帶：

```python
# 非明顯實作：用 context manager 確保屬性一致性
from opentelemetry import trace
from opentelemetry.semconv.ai import SpanAttributes  # AI 語意慣例

@contextmanager
def llm_span(tracer, model: str, prompt_version: str):
    with tracer.start_as_current_span("llm_completion") as span:
        span.set_attribute(SpanAttributes.LLM_SYSTEM, "anthropic")
        span.set_attribute(SpanAttributes.LLM_REQUEST_MODEL, model)
        span.set_attribute("ai.prompt.version", prompt_version)
        span.set_attribute("ai.prompt.hash", compute_hash(prompt_version))
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR)
            raise
```

**Sampling 策略：不能 100% 採樣的原因**

在 Scale 階段（> 1M 請求/天），如果每個 Span 都記錄完整 Prompt 和 Response 文字，儲存成本是每月 $15,000–30,000。需要分層採樣：

| 採樣層 | 採樣率 | 保留內容 |
|--------|--------|---------|
| 系統指標 Span | 100% | Tokens, latency, cost（無文字） |
| 品質評估 Span | 5% | 完整 prompt + response（用於評估） |
| 錯誤 Span | 100% | 完整內容（finish_reason ≠ stop） |
| 用戶回饋 Span | 100% | 有明確正負回饋的請求 |

**診斷鏈：當 p99 正常但品質差時**

```
症狀：CSAT 下降，但 Traces 顯示 latency p99=920ms（正常）
↓
查 Spans：llm_completion 的 finish_reason 分佈
→ 發現 finish_reason=length 佔比從 2% 升到 18%（截斷！）
↓
查 prompt_construction Span：context_tokens 從平均 1800 增到 2900
→ RAG 檢索策略改變（top_k 從 5 升到 8），注入過多 context
↓
根本原因：兩週前的 RAG 調優，沒人意識到會增加截斷率
修復：降回 top_k=5，或增加 max_output_tokens
MTTR：有 Traces = 2 小時；無 Traces = 預計 3 天
```

---

## 四、提示版本管理與 A/B 測試可觀測性

Prompt Engineering 是 AI 系統最頻繁的「部署」，但大多數團隊用 Git commit 管理 Prompt，根本無法做生產環境的 A/B 測試。

**Prompt Registry 的最小可行設計：**

```
Prompt Registry
┌─────────────────────────────────────────────────────┐
│  prompt_id: qa_system_prompt                        │
│  ┌─────────────────────────────────────────────┐   │
│  │ version: v2.3.1  (current, 60% traffic)     │   │
│  │ hash: sha256:4a7f...                        │   │
│  │ deployed_at: 2026-06-20T14:00:00Z           │   │
│  │ metrics_7d:                                  │   │
│  │   faithfulness_score: 0.87                  │   │
│  │   avg_output_tokens: 312                    │   │
│  │   cost_per_request: $0.0084                 │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ version: v2.4.0-beta  (challenger, 40%)     │   │
│  │ hash: sha256:9c2e...                        │   │
│  │ deployed_at: 2026-06-21T09:00:00Z           │   │
│  │ metrics_7d:                                  │   │
│  │   faithfulness_score: 0.91 (+4.6%)          │   │
│  │   avg_output_tokens: 287 (-8.0%)            │   │
│  │   cost_per_request: $0.0077 (-8.3%)         │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**A/B 測試觀測的統計陷阱：**

品質指標（如 faithfulness score）往往方差很大（標準差 ±0.15），需要足夠樣本才能達到統計顯著性。

經驗法則：要偵測 5% 的品質差異，在 α=0.05, power=0.80 的條件下，需要約 **3,200 個樣本/組**。在 10K DAU 系統上，40% 流量的 challenger 每天約收到 4,000 請求，**大約需要 1 天**才能下結論。

低於 1,000 QPS 的系統：不要急著做 A/B，至少跑 3 天收集足夠樣本。

**Prompt 版本的四種變更類型（影響告警閾值不同）：**

| 變更類型 | 範例 | 監控重點 | 回滾閾值 |
|---------|------|---------|---------|
| 措辭微調 | 換同義詞 | 品質分數 ±3% | 品質下降 > 5% |
| 結構重組 | 重排 sections | 品質分數 ±8% | 品質下降 > 8% |
| 指令新增 | 加 "always cite sources" | 輸出長度、Token 成本 | 成本增加 > 20% |
| 系統角色改變 | 換 persona | 所有指標 | 品質下降 > 10% |

---

## 五、模型效能漂移：語意偏移 vs 分佈偏移偵測

「漂移」在 AI 系統有兩種截然不同的根本原因，必須分開偵測。

```
漂移類型分類
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  輸入分佈偏移                   模型行為漂移             │
│  ┌──────────────────┐          ┌──────────────────────┐ │
│  │ 用戶問題類型改變  │          │ 供應商更新基礎模型    │ │
│  │ 新領域問題出現   │          │ Prompt 版本更新       │ │
│  │ 語言/語氣轉變    │          │ RAG index 更新        │ │
│  └────────┬─────────┘          └──────────┬───────────┘ │
│           │                               │              │
│           ▼                               ▼              │
│  偵測方法：PSI / KS test         偵測方法：品質分數趨勢  │
│  (輸入 embedding 分佈比較)        (移動平均 + 閾值告警)  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**輸入分佈偏移偵測（PSI - Population Stability Index）：**

PSI 是風控領域借來的工具，比較「基線期」和「當前期」的特徵分佈差異：

```
PSI = Σ (實際佔比 - 基線佔比) × ln(實際佔比 / 基線佔比)

PSI < 0.1：分佈穩定，無需處理
PSI 0.1–0.2：輕微偏移，需留意
PSI > 0.2：顯著偏移，需調查
```

對於 LLM 輸入，做法是：
1. 將用戶 query 做 embedding（用輕量模型，如 text-embed-v3）
2. 用 PCA 降到 20 維
3. 每個維度計算 PSI，取最大值作為整體偏移分數

**模型行為漂移偵測（語意品質分數時序分析）：**

不是用靜態閾值，而是用 **7 日移動平均 + 標準差通道**：

```
品質分數趨勢
0.90 ┤
     │    ╭──╮  ╭─────
0.87 ┤────╯  ╰──╯     ← 7日均線
     │  ╔═══════╗
0.84 ┤  ║ 正常帶║      ← ±1.5σ
     │  ╚═══════╝
0.81 ┤           ╲___  ← 漂移警告觸發點
     │
     └─────────────────────────────▶ 時間
     D-14      D-7      D-1  Today
```

**診斷鏈：語意品質漂移的排查流程**

```
症狀：faithfulness_score 7日均值從 0.87 降到 0.81（-6.9%）
↓
Step 1：查 Prompt 版本變更記錄
→ 5天前有 v2.3.0 → v2.3.1 的微調
→ 但下降從 3 天前開始（不匹配）
↓
Step 2：查供應商 changelog
→ 供應商在 4 天前推送了模型小版本更新（無公告）
↓
Step 3：隔離驗證
→ 用舊版 Trace 中儲存的 prompt + context，重放到新模型
→ 品質分數確認下降 7.2%
↓
根本原因：模型供應商靜默更新，新版本在特定領域問題上較為保守
修復：調整 temperature 0.3→0.5，品質分數回升到 0.85
MTTR：有漂移偵測 = 6 小時；無 = 預計 5 天
```

---

## 六、成本歸因：按功能 / 用戶 / 模型的細粒度成本分析

AI 系統的成本結構跟傳統服務完全不同——**同一個功能，不同用戶的成本可以相差 10 倍**，因為上下文長度差異。

**三層成本歸因模型：**

```
成本歸因層級
┌─────────────────────────────────────────────────┐
│  Level 3：用戶層（user_id）                      │
│  Top 1% 用戶產生 23% Token 成本                  │
│  可能是 API 濫用或 power user                    │
├─────────────────────────────────────────────────┤
│  Level 2：功能層（feature_id）                   │
│  qa_search: $0.0084/req × 50K req/day = $420/day│
│  doc_summary: $0.031/req × 8K req/day = $248/day│
│  chat_assistant: $0.0062/req × 80K = $496/day   │
├─────────────────────────────────────────────────┤
│  Level 1：模型層（model_id）                     │
│  claude-3-5-sonnet: 68% of total cost           │
│  claude-3-haiku: 28% of total cost              │
│  embedding model: 4% of total cost              │
└─────────────────────────────────────────────────┘
```

**Token 成本的隱性爆炸點：**

對話記憶（ConversationHistory）是最常見的成本炸彈。如果每輪對話都把完整歷史帶入 context：

```
輪次 1：system(256) + user(80) = 336 input tokens
輪次 2：system(256) + history(336) + user(90) = 682 input tokens
輪次 5：system(256) + history(2100) + user(70) = 2426 input tokens
輪次 10：system(256) + history(6800) + user(85) = 7141 input tokens

→ 第 10 輪的成本是第 1 輪的 21 倍
```

在 Metrics 中追蹤 **context_token_ratio**（context tokens / total tokens）。若此比值超過 0.7，代表對話窗口管理有問題。告警閾值：7 日滑動均值 > 0.65 時告警。

**成本異常偵測（3σ 規則）：**

| 指標 | 基線 | 告警閾值 | 典型原因 |
|------|------|---------|---------|
| cost_per_request | $0.0084 | > $0.025 (+3σ) | Prompt 加了大量 context |
| output_tokens_p99 | 420 | > 1,200 | 模型開始囉嗦（溫度過高） |
| embedding_calls/request | 1.2 | > 5 | 重複 embedding 無快取 |
| 月成本環比增長 | 8% | > 25% | 新功能未做成本評估 |

---

## 七、AI 告警策略：品質指標 vs 系統指標的告警設計

AI 系統的告警分兩個截然不同的維度，必須用不同的告警哲學處理。

```
AI 告警維度
┌──────────────────────────────────────────────────┐
│                                                  │
│  系統指標告警              品質指標告警           │
│  （傳統 SRE）              （AI-native）          │
│                                                  │
│  • 靜態閾值                • 動態基線             │
│  • 即時告警（< 5 分鐘）    • 趨勢告警（1–24 小時）│
│  • PagerDuty 半夜叫人      • 工作時間通知         │
│  • 二元（正常/異常）       • 漸進嚴重度           │
│                                                  │
└──────────────────────────────────────────────────┘
```

**系統指標告警（立即處理）：**

| 告警 | 條件 | 嚴重度 | 行動 |
|------|------|--------|------|
| LLM API 可用性 | success_rate < 99% for 5min | P0 | 自動切換備援模型 |
| 請求延遲 | p99 > 5,000ms for 10min | P1 | 擴容/告知用戶 |
| Token 配額耗盡 | quota_remaining < 10% | P1 | 限流 + 告警 |
| 費用異常 | hourly_cost > 3× baseline | P2 | 通知 + 人工審查 |

**品質指標告警（趨勢型）：**

| 告警 | 條件 | 嚴重度 | 行動 |
|------|------|--------|------|
| 品質分數漂移 | 7日均值下降 > 5% | P2 | 工程師調查，工作時間 |
| 輸入分佈偏移 | PSI > 0.2 持續 2 天 | P3 | 分析師審查，下個 Sprint |
| 截斷率上升 | finish_reason=length > 10% | P2 | 調整 max_tokens |
| 幻覺指標 | contradiction_score > 0.15 | P1 | 即時告警，可能需要暫停功能 |

**避免告警疲勞的關鍵設計：**

品質告警不應半夜打電話。使用 **「趨勢 + 確認期」機制**：

```
品質告警觸發邏輯：
IF (current_7d_avg < baseline × 0.95)       ← 下降 5%
AND (trend_direction == "declining" for 2d) ← 持續下降 2 天
AND (sample_count > 500)                    ← 樣本足夠
THEN: send_slack_alert(severity="warning", on_call=False)

IF (current_7d_avg < baseline × 0.88)       ← 下降 12%
AND (sample_count > 200)
THEN: send_pagerduty_alert(severity="high")
```

---

## 八、為什麼選 X 不選 Y

### 決策 1：OpenTelemetry vs 自建 SDK

| 選擇 | 選 OTel 的理由 | 不選自建的理由 |
|------|--------------|--------------|
| OpenTelemetry | 業界標準，供應商中立；Jaeger/Tempo/Datadog 均可接收；AI semantic conventions 社群持續更新 | 自建 SDK：維護成本高；換後端需重寫；無法吸收社群的 AI 語意慣例更新 |

**Flip Condition**：自建 SDK 合理的情況——你需要的 AI-specific Spans（如多模態 image tokens）在 OTel 規範中尚未標準化，且你有 > 1 FTE 維護能力。

---

### 決策 2：Grafana Cloud vs Datadog for AI Metrics

| 選擇 | 選 Grafana Cloud 的理由 | 不選 Datadog 的理由 |
|------|----------------------|------------------|
| Grafana Cloud | 成本：$200/月 vs Datadog $2,000+/月（同等指標量）；開源技術棧可自建；Prometheus 生態整合天然 | Datadog：LLM Observability 功能完整但定價按 log ingestion 計費，AI 系統 log 量極大，成本失控風險高 |

**Flip Condition**：當工程團隊 < 3 人且沒有 DevOps 能力時，Datadog 的 LLM Observability 一體化方案減少維護負擔，$2,000/月 換來的工程師時間更值錢。

---

### 決策 3：LLM-as-Judge vs Rule-based 品質評估

| 選擇 | 選 LLM-as-Judge 的理由 | 不選 Rule-based 的理由 |
|------|---------------------|-------------------|
| LLM-as-Judge | 語意品質無法用規則量化；可評估忠實度、相關性、連貫性；與人類評分相關性 Pearson r ≈ 0.78 | Rule-based：只能偵測格式問題（長度、關鍵詞）；無法偵測語意退化；假陰性率高 |

**Flip Condition**：當 QPS > 5,000 且需要同步品質評分時，LLM-as-Judge 的延遲（300–800ms）不可接受，需要回歸規則式或使用快取評估結果。5% 採樣非同步評估是最佳折衷。

---

### 決策 4：Tempo（分散式 Trace 後端）vs Zipkin

| 選擇 | 選 Tempo 的理由 | 不選 Zipkin 的理由 |
|------|--------------|----------------|
| Grafana Tempo | 物件儲存後端（S3）成本低 $0.023/GB/月；與 Grafana 無縫整合；支援 TraceQL 查詢語言 | Zipkin：Elasticsearch 後端成本 $0.10–0.25/GB/月；查詢語言弱；社群活躍度下降 |

**Flip Condition**：團隊已深度投資 Zipkin + Elasticsearch 且 Trace 量 < 1GB/天時，遷移成本 > 收益。

---

### 決策 5：PSI vs Wasserstein Distance 作為分佈偏移指標

| 選擇 | 選 PSI 的理由 | 不選 Wasserstein 的理由 |
|------|------------|---------------------|
| PSI | 計算 O(n)，極快；閾值有業界共識（0.1/0.2）；易解釋給非技術利害關係人 | Wasserstein：計算 O(n²)，在 10K+ 樣本時成本高；閾值無共識，需要領域專家設定 |

**Flip Condition**：當輸入分佈是多模態（如混合語言查詢）時，PSI 會低估偏移，Wasserstein Distance 或 Maximum Mean Discrepancy（MMD）更準確。

---

### 決策 6：按請求採樣 vs 按用戶採樣 Trace

| 選擇 | 選按用戶採樣的理由 | 不選按請求採樣的理由 |
|------|----------------|-----------------|
| 按用戶採樣 | 確保每個用戶至少有完整的 Trace 供調查；對 power user 可 100% 採樣；對正常用戶 1–5% 採樣；成本降低 80% | 按請求採樣：對高頻用戶的問題無法完整重現；調查特定用戶投訴時常常沒有 Trace 可查 |

**Flip Condition**：當系統是純 API 服務（無 user_id 概念），按請求採樣結合 Head-based + Tail-based（對慢請求 100% 保留）是標準做法。

---

## 九、系統效應：無可觀測性 vs 完整監控

以一個 100K MAU、日均 80K 請求的 AI 問答系統為基準：

| 指標 | 無可觀測性 | Phase 2 監控 | Phase 3 完整監控 |
|------|----------|------------|----------------|
| 品質退化 MTTR | 3–5 天 | 8–24 小時 | 2–6 小時 |
| 成本異常偵測延遲 | 1 個月（帳單到時） | 1–3 天 | < 2 小時 |
| Prompt 更新失敗率 | 30%（無資料盲改） | 15%（有 A/B 但慢） | 5%（快速統計驗證） |
| 月 Token 成本浪費 | $1,200（無優化依據）| $400（部分優化） | $120（精準歸因優化）|
| 供應商漂移偵測 | 從不（靠用戶投訴） | 1–2 天 | 4–8 小時 |
| 工程師除錯時間 | 16 小時/事件 | 6 小時/事件 | 1.5 小時/事件 |

**ROI 試算（Phase 3 投資回報）：**

- 基礎設施成本：$5,000/月
- 節省的 Token 浪費：$1,080/月
- 節省工程師時間（假設每月 4 次事件）：(16 - 1.5) × 4 × $150/hr = **$8,700/月**
- 淨收益：$8,700 + $1,080 - $5,000 = **$4,780/月正收益**

> 在 100K MAU 規模，Phase 3 可觀測性平台的 ROI 轉正約在上線後第 2 個月。

---

## 十、面試答題要點

**面試官問**：「RAG 問答系統的答案品質下降，但系統指標正常，你怎麼設計可觀測性來定位這類問題？」

> *「這是典型的語意品質漂移問題，系統層面無法偵測。我會設計三層防禦：首先，在 LLM 呼叫的 Span 中注入 prompt_version、input/output tokens、finish_reason 等 AI-specific 屬性，並對 5% 的請求做完整文字採樣；其次，用非同步 LLM-as-Judge 每隔 15 分鐘評估採樣樣本的 faithfulness score，維護 7 日滑動均值，當下降超過 5% 觸發 P2 告警；第三層，用 PSI 比較每日輸入 embedding 分佈，PSI > 0.2 代表輸入已偏移，需要 Prompt 重新校準。這套系統可以在 10K–200K 用戶規模以 $300–500/月的基礎設施成本，將品質退化 MTTR 從 3–5 天壓到 6–8 小時。排查時，先看 finish_reason 分佈確認是否截斷，再看 prompt_version 時序確認是否有提示更新，最後查供應商 changelog 確認是否有靜默模型更新——三步通常能在 2 小時內找到根本原因。」*

---

## 十一、系列導航

← [Phase 17 Part 1：AI 系統部署策略 — 從 Shadow Mode 到 Canary Release](/posts/ai-eng-from-scratch-phase17-part1-deployment-zh/)

→ [Phase 17 Part 3：AI 系統成本工程 — Token 優化與快取架構](/posts/ai-eng-from-scratch-phase17-part3-cost-engineering-zh/)

---

*本文屬於「AI 工程從零開始」系列第 17 Phase 的第 2 篇，聚焦 AI 可觀測性的工程實踐。如有問題或建議，歡迎透過 GitHub Issues 或 Twitter 聯繫。*
