---
title: "FDE 面試準備指南（三十五）：RKK 實戰——生產級 AI 系統的可觀測性：Granular Tracing、Observability Framework 與 Cloud Trace 整合"
date: 2026-06-05T13:00:00+08:00
draft: false
description: "以 Google FDE 視角深度拆解生產級 Agentic 系統的可觀測性設計：什麼是 Granular Tracing、一條 Trace 應該回答哪五個問題、OpenTelemetry 與 Cloud Trace 的整合模式、Vertex AI Experiments 的評估追蹤，以及當系統在客戶端出問題時 FDE 的第一反應"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Observability", "Tracing", "OpenTelemetry", "Cloud Trace", "Vertex AI", "Agent", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "20 min"
---

> 面試官問「系統 P95 延遲突然升高，你怎麼辦？」  
> 多數人的答案是「我去看 Logs」。  
> 強力雇用的答案是：「我打開 Trace，找到哪個 hop 吃掉了時間——  
> 是 Embedding、是 Vector Search、是 LLM 呼叫、還是 Tool 執行。」  
> 這兩個答案的差距，就是 Granular Tracing 的價值。

---

## 面試情境

> **面試官：**「你的團隊幫一家製造業客戶部署了一個 ADK Multi-Agent 系統，上線兩週後客戶回報：有時候回應需要 15 秒，但有時候只要 2 秒。你不在客戶現場。你的第一步是什麼？你的 Observability 設計應該讓你在 5 分鐘內定位到問題在哪裡。請說明你的系統設計。」

---

## 一、為什麼 Logs 不夠，需要 Tracing

```
傳統系統的 Observability 三柱：
  Logs（記錄發生了什麼）
  Metrics（量化指標的趨勢）
  Traces（單一請求的完整執行路徑）

Agentic AI 系統的特殊性：

  一個用戶 query 可能觸發：
  ┌─────────────────────────────────────────────────┐
  │ User Query                                       │
  │    ↓                                             │
  │ Orchestrator Agent                               │
  │    ├── LLM Call #1（決策：要呼叫哪個工具）         │
  │    ├── Tool Call → External API（200ms？2000ms？）│
  │    ├── Sub-Agent #1                              │
  │    │      ├── Embedding Call（向量化 query）      │
  │    │      ├── Vector Search（找相關文件）          │
  │    │      └── LLM Call #2（生成局部答案）          │
  │    ├── Sub-Agent #2（並行）                       │
  │    │      ├── DB Query                           │
  │    │      └── LLM Call #3                        │
  │    └── LLM Call #4（整合答案）                    │
  └─────────────────────────────────────────────────┘

  Log 只能告訴你：「LLM Call #3 回傳了 X」。
  Trace 能告訴你：「整條路徑花了 15 秒，
                   其中 12 秒在 Sub-Agent #1 的 Vector Search。」

  沒有 Trace，你只能「猜」。
  有 Trace，你「找到」。
```

---

## 二、Granular Tracing 的核心概念

### Trace 的結構

```
一條 Trace = 一個 Root Span + 多個 Child Spans

Span 是什麼：
  ├── 一個有開始時間和結束時間的操作單元
  ├── 帶有 attributes（metadata）
  └── 有 parent-child 關係（樹狀結構）

Agentic 系統的 Span 類型：

  Span 類型                     應該記錄的 Attributes
  ──────────────────────────────────────────────────────────────────
  agent.run                    agent_name, input_length, output_length
  llm.generate                 model_name, input_tokens, output_tokens,
                               latency_ms, finish_reason
  tool.call                    tool_name, input_params, success/fail,
                               latency_ms, error_type
  vector_search                query_length, top_k, num_results,
                               latency_ms, index_name
  embedding.create             model_name, input_length, latency_ms
  sub_agent.invoke             agent_name, parent_agent, latency_ms

「Granular」的意思：
  每一個 LLM 呼叫、每一個 Tool 呼叫、每一個 Vector Search
  都有自己的 Span，都有精確的時間戳記和 metadata。
  不是只記錄「整個 Agent 跑了多久」，
  而是「每個 hop 分別花了多少時間，帶了什麼資料」。
```

### 一條 Trace 應該能回答的五個問題

```
問題 1：哪個 hop 是延遲瓶頸？
  → 看 Span 的 duration，找最長的那個
  → 例：發現 Vector Search 的 P95 是 8 秒（正常應 < 500ms）
  → 結論：Vector Search 索引過大 or 查詢設計問題

問題 2：Token 在哪裡被消耗？
  → 每個 llm.generate Span 上的 input_tokens + output_tokens
  → 例：發現 Orchestrator 的 input_tokens 每次都是 15,000
  → 結論：系統 Prompt 太長，或 conversation history 沒有被截斷

問題 3：Tool 呼叫有沒有失敗？
  → 每個 tool.call Span 上的 success/fail + error_type
  → 例：發現 CRM API 有 15% 的呼叫 timeout
  → 結論：外部 API 問題，不是 LLM 問題

問題 4：Sub-agent 的執行是否按預期並行？
  → 看 ParallelAgent 的 child spans 的時間是否重疊
  → 例：發現兩個 sub_agent 是序列執行而非並行（並行設計失效）
  → 結論：ADK ParallelAgent 的配置問題

問題 5：在哪個步驟上下文開始退化？
  → 看每個 llm.generate Span 的 finish_reason
  → 如果是 "max_tokens"，表示被截斷了
  → 如果出現在早期步驟，後續所有答案品質都有問題
```

---

## 三、實作：OpenTelemetry + Cloud Trace

### OpenTelemetry 是什麼，為什麼選它

```
OpenTelemetry（OTel）是業界標準的可觀測性框架：
  ├── 標準化 Span / Trace / Metric 的格式
  ├── 語言無關（Python、Node.js、Go、Java 都有 SDK）
  ├── 後端無關（可以輸出到 Cloud Trace、Jaeger、Zipkin、Datadog）
  └── ADK 和 Vertex AI SDK 都有 OTel 整合

對 FDE 的意義：
  你用 OTel 寫的 Instrumentation 代碼，
  在客戶的 AWS 環境和 GCP 環境都能用，
  只需要換 Exporter 的設定。
```

### ADK Agent 的 OTel Instrumentation

```python
# 基本設定（在 Agent 啟動時執行一次）

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

# 設定 Cloud Trace Exporter
provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(CloudTraceSpanExporter())
)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("fde.claims_agent")

# 在 ADK Tool 裡加入 Instrumentation
def query_claims_database(claim_id: str) -> dict:
    """查詢理賠記錄。"""
    with tracer.start_as_current_span("tool.query_claims_db") as span:
        span.set_attribute("tool.name", "query_claims_database")
        span.set_attribute("claim_id", claim_id)

        start = time.time()
        try:
            result = db.query(claim_id)
            span.set_attribute("tool.success", True)
            span.set_attribute("result.record_count", len(result))
            return result
        except Exception as e:
            span.set_attribute("tool.success", False)
            span.set_attribute("tool.error_type", type(e).__name__)
            span.record_exception(e)
            raise
        finally:
            span.set_attribute("tool.latency_ms",
                               (time.time() - start) * 1000)
```

### LLM 呼叫的 Instrumentation（最關鍵）

```python
# 包裝 Gemini API 呼叫，記錄 token 使用和延遲

def instrumented_llm_call(model, prompt, system_instruction=None):
    with tracer.start_as_current_span("llm.generate") as span:
        span.set_attribute("llm.model", model.model_name)
        span.set_attribute("llm.input_length", len(prompt))

        start = time.time()
        response = model.generate_content(
            prompt,
            system_instruction=system_instruction
        )
        latency = (time.time() - start) * 1000

        # 記錄 token 使用（最重要的成本指標）
        span.set_attribute("llm.input_tokens",
                           response.usage_metadata.prompt_token_count)
        span.set_attribute("llm.output_tokens",
                           response.usage_metadata.candidates_token_count)
        span.set_attribute("llm.latency_ms", latency)
        span.set_attribute("llm.finish_reason",
                           response.candidates[0].finish_reason.name)

        # 計算 tokens/sec（LLM-native 效能指標）
        if latency > 0:
            tps = response.usage_metadata.candidates_token_count / (latency / 1000)
            span.set_attribute("llm.tokens_per_sec", round(tps, 1))

        return response
```

---

## 四、Cloud Trace 的實際使用

```
Cloud Trace 的三個核心功能：

1. Trace 搜尋和瀑布圖
   → 用 Trace ID 找到特定的慢請求
   → 瀑布圖顯示每個 Span 的時間線
   → 一眼看出哪個 hop 佔了最多時間

2. 延遲分佈分析
   → 看 P50 / P95 / P99 的趨勢
   → 找到「偶爾慢」vs「持續慢」的差異
   → 例：P50 是 2 秒，P99 是 15 秒
      → 說明多數請求很快，但有少數請求極慢（tail latency 問題）

3. Span 的 Attribute 過濾
   → 只看 tool.success = false 的 Span
   → 只看 llm.input_tokens > 10000 的 Span
   → 找出「哪個 Tool 最常失敗」或「哪個 query 最貴」

FDE 的實際工作流程（客戶回報系統慢）：

  Step 1：Cloud Trace 搜尋最近 1 小時的 P95 最慢的 10 條 Trace
  Step 2：打開瀑布圖，找最長的 Span
  Step 3：看那個 Span 的 Attributes（是哪個 Tool？哪個 LLM？）
  Step 4：用 Span Attributes 過濾更多同類請求，確認是否系統性問題
  Step 5：有了「哪裡慢、多慢、影響多少比例的請求」之後
          才去找根本原因（代碼 / 配置 / 外部依賴）

  沒有 Trace：「系統好像有時候比較慢，不知道為什麼。」
  有 Trace：「P95 慢的請求 100% 有一個共同點：
             fraud_detection Tool 呼叫超過 8 秒。
             正常請求的 fraud_detection 是 300ms。
             問題在詐欺偵測服務，不在 AI 部分。」
```

---

## 五、Vertex AI Experiments：品質追蹤

可觀測性不只是延遲和錯誤，還包括**品質的長期追蹤**。

```
Vertex AI Experiments 的用途：

  記錄每次評估的指標，追蹤品質隨時間的變化：

  experiment = aiplatform.Experiment("claims-agent-eval")
  run = experiment.start_run(run_name=f"v{model_version}-{date}")

  run.log_metrics({
      "faithfulness": 0.87,
      "answer_relevance": 0.91,
      "context_recall": 0.83,
      "tool_success_rate": 0.96,
      "avg_latency_ms": 2340,
      "avg_input_tokens": 4200,
      "avg_output_tokens": 680,
      "p95_latency_ms": 8100
  })

  run.log_params({
      "model": "gemini-2.0-flash",
      "chunk_size": 512,
      "top_k": 5,
      "system_prompt_version": "v3"
  })

這讓你能回答：
  「上週我們把 chunk_size 從 256 改成 512，
   Context Recall 從 0.75 升到 0.83，
   但 avg_latency_ms 從 1800 升到 2340。
   這個 trade-off 客戶可以接受。」

沒有 Experiments 記錄，每次系統更新後你都不知道品質有沒有退化。
```

---

## 六、Structured Logging：Trace 的補充

```
Trace 記錄結構，Log 記錄內容。
兩者要互相連結（用 Trace ID 串聯）。

Structured Log 的格式設計：

  import json
  import logging

  def log_agent_event(event_type, trace_id, span_id, **kwargs):
      record = {
          "timestamp": datetime.utcnow().isoformat(),
          "trace_id": trace_id,
          "span_id": span_id,
          "event_type": event_type,
          **kwargs
      }
      logging.info(json.dumps(record))

  # 使用範例
  log_agent_event(
      "llm.response",
      trace_id=current_trace_id,
      span_id=current_span_id,
      model="gemini-2.0-flash",
      input_tokens=3200,
      output_tokens=450,
      finish_reason="STOP",
      # 不記錄原始 Prompt 和 Response 內容——
      # 可能含有 PII，Cloud Logging 不是 PII 安全儲存
      response_length=len(response.text),
      has_tool_calls=len(response.parts) > 1
  )

重要設計原則：
  ├── Log 裡不放 PII（姓名、帳號、診斷）
  ├── Log 裡不放完整 Prompt（可能含有敏感業務邏輯）
  ├── Log 用 Trace ID 和 Span ID 連結到 Cloud Trace
  └── 用 jsonPayload 而不是 textPayload，讓 Log Explorer 可以過濾欄位
```

---

## 七、面試官地雷題

**地雷 1：「ADK 有沒有內建 Tracing？你還需要自己寫 OTel 嗎？」**

```
答：ADK 有基本的執行日誌，但不是 production-grade 的 Granular Tracing。
    ADK 的內建日誌告訴你「Agent A 呼叫了 Tool B，結果是 C」，
    但不告訴你每個 LLM 呼叫用了多少 token、
    Vector Search 花了多少毫秒、哪個 hop 的 P95 是多少。
    
    如果你要在 Cloud Trace 看到完整的瀑布圖、
    在 Cloud Monitoring 設 Alert（「Tool 失敗率超過 5% 就 PagerDuty」），
    你需要自己加 OTel Instrumentation。
    
    ADK 的計畫是越來越深度整合 OTel，但目前（2026）
    生產部署仍然需要手動加 Instrumentation。
```

**地雷 2：「你說要記錄每個 LLM 呼叫的 input_tokens，
但這樣不會在 Log 裡暴露敏感 Prompt 嗎？」**

```
答：這是很重要的設計問題。
    我記錄的是 input_tokens（數字），不是 prompt_text（內容）。
    Token 數量是中性的效能指標，不含敏感資訊。
    
    原始 Prompt 的內容：
    ├── 不記錄到 Log（有 PII 洩漏風險）
    ├── 不記錄到 Cloud Trace（同上）
    └── 如果需要 Debug 用途，用獨立的加密審計儲存，
        有 RBAC 和 TTL，只有授權的工程師能存取
    
    Tracing 的目標是效能和可靠性的可觀測性，
    不是重現完整的對話內容。
    兩個目的需要不同的儲存機制和不同的存取控制。
```

**地雷 3：「客戶說他們的系統有時候 15 秒、有時候 2 秒。
你如何用 Trace 區分這是『偶發的外部依賴問題』
還是『輸入特性造成的系統性問題』？」**

```
答：兩步驟的分析流程：

    Step 1：按 Span 類型分群
    在 Cloud Trace 過濾 latency > 10s 的請求，
    看這些慢請求的最長 Span 是什麼類型：
      → 如果都是 tool.call（外部 API）→ 外部依賴問題
      → 如果都是 llm.generate → LLM 回應問題（可能 token 過多）
      → 如果都是 vector_search → 索引或查詢問題

    Step 2：看慢請求的 input 特徵
    慢請求的 Span Attributes 裡看：
      → 慢請求的 llm.input_tokens 是不是特別高？
        如果是 → 長輸入造成的系統性問題（需要截斷策略）
      → 慢請求都發生在特定時間段？
        如果是 → 外部依賴的負載問題（不是你的系統）
      → 慢請求有沒有共同的 query 類型？
        如果有 → 特定類型的 query 觸發了更多 Tool 呼叫

    有了這個分析，你能跟客戶說：
    「15 秒的請求 100% 發生在 fraud_detection API 回應超過 8 秒的時候。
     你的詐欺偵測服務在下午 2-4 點有負載問題。
     這不是 AI 系統的問題，是你的後端服務問題。」
    這個明確的根因，是沒有 Trace 的系統永遠說不出來的。
```

**地雷 4：「Granular Tracing 有什麼代價？你會在所有環境都開啟嗎？」**

```
答：三個代價：
    1. 效能開銷：每個 Span 的建立和 export 有 CPU 和網路成本。
       通常 < 1% 的額外延遲，對多數場景可接受。
       但高頻場景（50,000 QPS）需要 sampling。
    
    2. 儲存成本：Cloud Trace 按 Span 數量計費。
       每個請求 20 個 Span，50,000 QPS = 每秒 100 萬個 Span。
       要設計 Sampling 策略（例如：100% 採樣慢請求，1% 採樣正常請求）。
    
    3. 敏感資料：Span Attributes 必須避免含有 PII，
       否則 Cloud Trace 成為合規問題。
    
    我的策略：
      Dev / Staging：100% Sampling（找問題時要完整資料）
      Production 正常流量：1-5% Random Sampling
      Production 異常流量（latency > threshold 或 error）：100% Sampling
      這樣能捕捉所有異常，同時控制正常流量的成本。
```

---

## 八、面試回答完整示範

```
面試官問：「P95 延遲突然從 2 秒升到 15 秒，你的第一步是什麼？」

可觀測性先行（30 秒）：
「我的第一步是打開 Cloud Trace，
 過濾最近 1 小時 latency > 10 秒的請求，
 看瀑布圖找最長的 Span。
 這個步驟應該在 2 分鐘內告訴我延遲在哪個 hop。」

根因分析（1 分鐘）：
「如果最長 Span 是 tool.call：
   我看 tool_name 和 error_type——
   是外部 API 變慢，還是 timeout 在重試？
   如果是第三方 API 的問題，解法是加 Circuit Breaker，
   fallback 到 cached 結果或降級回應。

 如果最長 Span 是 llm.generate：
   我看 input_tokens——
   如果慢請求的 input_tokens 都 > 10,000，
   問題是 context 沒有被截斷，
   解法是加 context budget 和 summarization。

 如果最長 Span 是 vector_search：
   我看 index_name 和 query_length——
   可能是索引過大或缺少 min_instances 設定導致 cold start。」

跟客戶溝通（30 秒）：
「在 5 分鐘的分析後，我能告訴客戶：
 『P95 延遲的問題定位在 X 元件。
   影響範圍是 Y% 的請求，集中在 Z 時間段。
   根本原因是 W，預計修復時間 N 小時。
   在修復完成前，這個 fallback 機制可以把 P95 降回 3 秒以內。』
 這是有 Trace 才能在 5 分鐘內說出的診斷。」
```

---

**Granular Tracing 是 FDE 的第一工具，不是最後手段。**  
**系統上線的第一天，Observability 就要在。等問題出現了才加，已經太晚了。**
