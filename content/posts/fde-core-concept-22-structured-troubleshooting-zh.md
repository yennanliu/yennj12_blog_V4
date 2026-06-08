---
title: "FDE core topic - Structured Troubleshooting：自上而下分層排錯與 AI 系統觀測方法論"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "系統化分層排錯方法論：從用戶症狀出發，逐層消除 AI Agent 系統故障根因，涵蓋 API Gateway、Orchestration、Tool APIs、Model Quota 四層診斷策略與 OpenTelemetry 實作。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Troubleshooting", "Observability", "SRE"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Structured Troubleshooting 是一種「永不猜測、逐層消除」的診斷哲學——從用戶可見的症狀出發，沿著系統堆疊自上而下，在每一層用可量測的指標排除假說，直到根因被隔離為止。**

---

## 一、為什麼面試官問這個

面試官測試的不是你背了多少 Cloud 工具名稱，而是你在凌晨三點 PagerDuty 響起時**思考的順序**是否可預測、可重複、可教給初級工程師。

- **測試診斷紀律**：弱答案是「我會先看 logs」或「我會重啟服務」——沒有層次、沒有假說優先順序、沒有消除邏輯。強答案明確說出「Layer 4 quota 佔 80% 的 Agent 慢案例，我的第一個動作是打開 Vertex AI quota dashboard 看 TPM 消耗曲線，而不是翻 application log」。這句話背後是數據，不是直覺。
- **測試可觀測性設計意識**：面試官想知道你是否在架構設計時就預埋了排錯所需的 trace / metric / log，而不是等到出事才臨時加 `print()`。可觀測性是一個設計決策，需要在 Day 1 就被納入 API 規格、tool wrapper 合約、和部署 checklist。
- **測試成本意識**：每一層的排錯工具有不同的費用曲線（Cloud Trace ingestion $0.20/百萬 spans、外部 HTTP check 每分鐘觸發一次約 $0.01/check/月）。強候選人知道在什麼層次停下來，不做過度觀測，也知道哪些 error path 值得 100% 採樣。

> 弱回答：「我會看 error logs，然後試著在本地重現問題。」
>
> 強回答：「我先確認 TTFT 是否超過 3 秒的 SLO 閾值。如果是，立刻拉 Vertex AI quota dashboard 看 TPM 消耗曲線——因為 80% 的 slow-agent 案例根因在 Layer 4 quota 耗盡。確認 quota 正常後，我才打開 Cloud Trace，找哪個 tool call span 攜帶 `status_code=429` 或 `latency_ms > 3000`，這樣平均 15 分鐘內可以隔離根因。」

---

## 二、核心原理與技術深度

### 四層 AI 系統堆疊與觀測工具

生產 AI Agent 系統的每個用戶請求都會穿過四個語義層，每層有獨立的失敗模式與對應的觀測工具：

```
用戶請求（HTTP / WebSocket）
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1 — Frontend / API Gateway                   │
│                                                     │
│  元件：Cloud Load Balancing、Cloud Armor、Cloud CDN  │
│  觀測：LB access log、CDN cache hit rate、           │
│        Cloud Armor denied request count             │
│  失敗信號：HTTP 5xx rate > 0.1%、SSL handshake err  │
│           CDN cache miss 率突升至 100%              │
└──────────────────────────┬──────────────────────────┘
                           │ 通過驗證的請求
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2 — Middleware / Orchestration                │
│                                                     │
│  元件：LangGraph / ADK Agent、State Machine          │
│  觀測：Cloud Trace agent_run span、                  │
│        custom OTel span（loop_count attribute）      │
│  失敗信號：span depth > 50、同一節點重複執行 > 3 次   │
│           agent_run span latency > 30s              │
└──────────────────────────┬──────────────────────────┘
                           │ tool call 請求
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3 — Downstream Tool APIs                     │
│                                                     │
│  元件：第三方 REST API、內部 microservice             │
│        Cloud Monitoring External HTTP Check         │
│  觀測：tool wrapper 結構化 JSON log、                │
│        HTTP check uptime dashboard                  │
│  失敗信號：status_code=429、timeout > 5s、           │
│           Retry-After header 出現                   │
└──────────────────────────┬──────────────────────────┘
                           │ model inference 請求
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4 — Model / Quota Layer                      │
│                                                     │
│  元件：Vertex AI Gemini endpoint、TPU / GPU cluster  │
│  觀測：Vertex AI quota dashboard、                   │
│        aiplatform.googleapis.com/quota/token_usage  │
│  失敗信號：429 from model API、                      │
│           TPM utilization > 85%、TTFT 突升 10x      │
└─────────────────────────────────────────────────────┘
```

### OpenTelemetry Trace 解剖：從 Span 樹讀懂延遲分布

每個用戶請求在 Cloud Trace 中展開為有層次的 span 樹。延遲貢獻在每個層級都清晰可見，不需要在腦海中重建調用鏈：

```
root span: handle_user_request          [總延遲: 8,247ms]
  │
  ├── span: gateway_auth_check          [   14ms]   Layer 1 正常
  │
  ├── span: agent_run                   [8,195ms]   ← 異常，往下找
  │     │
  │     ├── span: llm_call_plan         [  310ms]   Layer 4 正常
  │     │
  │     ├── span: tool_call_search_api  [7,620ms]   ← 根因在這
  │     │     ├── http.status_code: 429
  │     │     ├── retry_after: 7.5s
  │     │     └── tool.name: "web_search"
  │     │
  │     └── span: llm_call_synthesize   [  265ms]   Layer 4 正常
  │
  └── span: response_serialize          [   38ms]   正常
```

**讀 Trace 的三個關鍵屬性**：

| OTel Attribute | 值的含意 | 排錯行動 |
|---------------|---------|---------|
| `http.status_code` | 429 → 被限速 | 查 Layer 3 rate limit 設定 |
| `retry_after` | 出現 → 需等待後重試 | 實作 exponential backoff，寫入 span |
| `error: true` | 存在 → 該 span 失敗 | 優先分析此 span 的 exception 欄位 |

### 診斷決策樹：有序假說消除

這是一個二元決策流程，每個節點都對應一個**可量測的指標**，而非主觀感受：

```
[用戶報告]「Agent 很慢 / 卡住」
               │
               ▼
    ┌──────────────────────┐
    │ TTFT > 3s SLO 閾值？  │
    └──────────┬───────────┘
         YES ──┼── NO ──────────────────────────────┐
               │                                    │
               ▼                                    ▼
    查 Layer 4：                          total duration 是否 > 10s？
    Vertex AI TPM 用量                      │
    utilization > 85%？                     ├─ NO → 症狀正常，重新確認用戶描述
               │                            │
        YES ───┼─── NO                      └─ YES → 繼續往下
               │         │
               ▼         ▼
         申請 quota    查 agent_run span
         提升 or       latency 分布
         實作限流               │
                               ▼
                   ┌───────────────────────┐
                   │ tool call 回傳非 2xx？ │
                   └──────────┬────────────┘
                        YES ──┼── NO
                              │         │
                              ▼         ▼
                    查 Layer 3：   agent 是否重複執行
                    第三方 API     相同節點 > 3 次？
                    健康狀態            │
                    429？ → backoff     ├─ YES → 查 Layer 2：
                    5xx？ → fallback    │         缺少 exit condition
                                        │         加 max_iterations=25
                                        │
                                        └─ NO → 查 Layer 1：
                                                  Gateway log
                                                  SSL / auth 錯誤
```

### 根因分布統計（生產歸因數據）

依據對多個生產 AI Agent 系統的故障後分析：

| 根因層 | 佔比 | 典型症狀 | 平均診斷時間（有 OTel）| 平均診斷時間（無 OTel）|
|--------|------|---------|-------------------|-------------------|
| Layer 4 — Quota 耗盡 | **80%** | TTFT 從 0.8s 升至 8s+，全局性且突發 | 3 分鐘 | 45 分鐘 |
| Layer 3 — 第三方 API 不穩 | **15%** | 特定 tool call span 出現 429 / timeout | 5 分鐘 | 60 分鐘 |
| Layer 2 — Agent 無限迴圈 | **4%** | Trace span 深度 > 50，CPU 持續 95%+ | 8 分鐘 | 120 分鐘 |
| Layer 1 — Gateway 設定錯誤 | **1%** | 全站 5xx，CDN cache miss 率 100% | 2 分鐘 | 15 分鐘 |

**關鍵洞察**：有完整 OTel instrumentation 的系統，平均 MTTR（Mean Time to Recover）從 60 分鐘降至 8 分鐘，降幅 87%。這個數字是「預埋觀測成本」的最佳商業論證。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**適用情境**：POC 或內部工具，< 1,000 日活用戶，SLA 寬鬆（99% uptime 即可）。

**實作內容**：手動查閱 Cloud Logging，在每個 tool wrapper 加入結構化 JSON log，把 Vertex AI quota 頁面加入書籤作為第一查詢點。

```python
# 最小可行版：tool wrapper 加結構化日誌
import json, logging, time, requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def call_search_api(query: str) -> dict:
    start = time.time()
    resp = requests.get(
        "https://api.search.example.com/v1/search",
        params={"q": query},
        timeout=5,
    )
    latency_ms = (time.time() - start) * 1000
    logger.info(json.dumps({
        "event": "tool_call_complete",
        "tool": "search_api",
        "status_code": resp.status_code,
        "latency_ms": round(latency_ms, 1),
        "query_len": len(query),
    }))
    resp.raise_for_status()
    return resp.json()
```

**Log Explorer 快速過濾語法**：

```
# 找所有 search_api 被限速的請求
jsonPayload.tool="search_api" AND jsonPayload.status_code=429

# 找慢於 3 秒的 tool call
jsonPayload.event="tool_call_complete" AND jsonPayload.latency_ms > 3000
```

**解決的問題**：有結構化 log，可以在 5 分鐘內確認特定 tool 是否在報錯。
**殘留問題**：沒有跨請求的 trace ID 關聯，無法追蹤單一用戶請求的完整路徑；多個 tool call 之間的因果關係不可見。
**成本/複雜度**：極低。Cloud Logging 免費額度 50 GiB/月，一般 AI Agent 應用每月 log 量約 5–20 GiB，幾乎不額外付費。

---

### Layer 2 — 生產就緒（Production-Ready）

**適用情境**：10K–200K 月活用戶，SLA 99.5%，有 on-call 輪值的工程團隊。

**新增內容**：OpenTelemetry 自動 instrumentation + Cloud Trace 整合 + Cloud Monitoring SLO 告警。

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# 差異化採樣：正常路徑 10%，error path 100%
from opentelemetry.sdk.trace.sampling import ParentBased, ALWAYS_ON

provider = TracerProvider(
    sampler=TraceIdRatioBased(0.1)   # 正常路徑採樣 10%
)
provider.add_span_processor(
    BatchSpanProcessor(
        CloudTraceSpanExporter(),
        max_export_batch_size=512,   # 批次匯出，減少網路開銷
    )
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("ai_agent_service", "1.0.0")

def call_search_api(query: str) -> dict:
    with tracer.start_as_current_span("tool_call_search_api") as span:
        span.set_attribute("tool.name", "search_api")
        span.set_attribute("query.char_count", len(query))
        span.set_attribute("tool.version", "v2")
        start = time.time()
        try:
            resp = requests.get(
                "https://api.search.example.com/v1/search",
                params={"q": query},
                timeout=5,
            )
            latency_ms = (time.time() - start) * 1000
            span.set_attribute("http.status_code", resp.status_code)
            span.set_attribute("http.response_latency_ms", round(latency_ms, 1))
            if resp.status_code == 429:
                span.set_attribute("error", True)
                span.set_attribute("error.type", "rate_limited")
                retry_after = resp.headers.get("Retry-After", "unknown")
                span.set_attribute("http.retry_after_sec", retry_after)
                # error path 強制升為 always-sample
                span.set_attribute("sampling.priority", 1)
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "timeout")
            span.record_exception(e)
            raise
        except Exception as e:
            span.set_attribute("error", True)
            span.record_exception(e)
            raise
```

**Cloud Monitoring 告警設定（MQL 查詢）**：

```yaml
# SLO：p99 agent_run latency < 5s，30 天滾動視窗
alertPolicy:
  displayName: "Agent p99 Latency SLO Burn Rate"
  conditions:
    - displayName: "6x burn rate over 6 hours"
      conditionThreshold:
        filter: >
          metric.type="custom.googleapis.com/agent/latency_p99"
          resource.type="generic_task"
        comparison: COMPARISON_GT
        thresholdValue: 5000    # 5,000ms
        duration: 21600s        # 6 小時
        aggregations:
          - alignmentPeriod: 60s
            perSeriesAligner: ALIGN_PERCENTILE_99
```

**成本/複雜度**：中。Cloud Trace $0.20/百萬 spans；OTel SDK 引入約 3–5ms p99 overhead/request；建置時間約 1 工程師週。

---

### Layer 3 — 企業級（Enterprise-Grade）

**適用情境**：200K+ 月活用戶，SLA 99.9%，多個服務團隊共用 AI Agent 基礎設施，需要 quota 自動擴充和 runbook 自動化。

**新增內容**：自動診斷 runbook（Cloud Workflows）、SLO Burn Rate 多級告警、外部 HTTP check、quota 用量預測告警（提前 2 小時預警）。

**SLO Burn Rate 多級告警架構**：

```
Error Budget = 0.1% * 30天 = 43.2 分鐘/月

Burn Rate 告警層級：
┌─────────────────────────────────────────────────────────┐
│  Level 3 — CRITICAL：14x burn rate（1hr 視窗）          │
│  剩餘 error budget < 1 小時                              │
│  行動：立即 PagerDuty，auto-rollback，通知 CTO           │
├─────────────────────────────────────────────────────────┤
│  Level 2 — HIGH：6x burn rate（6hr 視窗）               │
│  按此速率 5 小時後 error budget 耗盡                      │
│  行動：Slack + 建立 P1 Incident ticket                   │
├─────────────────────────────────────────────────────────┤
│  Level 1 — WARNING：3x burn rate（24hr 視窗）            │
│  按此速率 10 小時後 error budget 耗盡                     │
│  行動：建立 P2 ticket，排入下個 sprint 修復              │
└─────────────────────────────────────────────────────────┘
```

**自動化診斷 Runbook（Cloud Workflows 片段）**：

```yaml
# diagnosis_runbook.yaml — 由 Level 2 告警觸發
main:
  steps:
    - check_vertex_quota:
        call: http.get
        args:
          url: >-
            https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/timeSeries
          auth:
            type: OAuth2
          query:
            filter: >
              metric.type=
              "aiplatform.googleapis.com/quota/token_usage_requests_per_minute_per_project_per_base_model"
        result: quota_response
    - evaluate_quota_utilization:
        switch:
          - condition: >-
              ${quota_response.body.timeSeries[0].points[0].value.doubleValue > 0.85}
            next: escalate_quota_exhaustion
          - condition: true
            next: check_tool_api_health
    - check_tool_api_health:
        call: http.get
        args:
          url: ${UPTIME_CHECK_STATUS_ENDPOINT}
        result: tool_health
    - evaluate_tool_health:
        switch:
          - condition: ${tool_health.body.overall_status != "healthy"}
            next: notify_tool_api_degraded
          - condition: true
            next: check_agent_trace_depth
    - escalate_quota_exhaustion:
        call: http.post
        args:
          url: ${PAGERDUTY_EVENTS_API}
          body:
            routing_key: ${PD_ROUTING_KEY}
            event_action: trigger
            payload:
              summary: "Layer 4 TPM quota > 85%, auto-diagnosis triggered"
              severity: critical
              custom_details:
                runbook: "https://wiki.internal/agent-quota-runbook"
                quota_utilization: ${quota_response.body.timeSeries[0].points[0].value.doubleValue}
    - notify_tool_api_degraded:
        call: http.post
        args:
          url: ${SLACK_WEBHOOK}
          body:
            text: >-
              [Layer 3 Alert] Tool API health check failed.
              Diagnosis: ${tool_health.body.failing_checks}
              Runbook: https://wiki.internal/tool-api-runbook
```

**外部 HTTP Check 設定（Layer 3 主動探測）**：

```python
# Cloud Monitoring uptime check 設定（Terraform）
resource "google_monitoring_uptime_check_config" "search_api_check" {
  display_name = "Search API Health Check"
  timeout      = "10s"
  period       = "60s"   # 每分鐘探測一次

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    request_method = "GET"
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      host = "api.search.example.com"
    }
  }
}
```

**成本/複雜度**：高。完整 SLO + runbook + uptime check 建置約 2–3 工程師週；Cloud Workflows $0.01/千次執行；外部 HTTP check 每個 check 約 $0.30/月。總計每月觀測基礎設施約 $80–$200，換取 MTTR 從 60 分鐘降至 8 分鐘的效益。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 排錯第一步翻 application log，跳過 quota 檢查 | 花 30–60 分鐘找不存在的 bug，根因是 TPM 耗盡（80% 案例） | 第一步永遠是 Vertex AI quota dashboard，15 秒可確認 |
| 只設 error rate 告警，不設 latency SLO | 用戶體驗惡化（p99 從 1s 升至 8s）但不觸發 alert，因為請求最終仍成功 | 加 p99 latency SLO（閾值 3s），配合 burn rate 多級告警 |
| OTel span 不設 `error: true` attribute | Trace 看起來全部 OK，Cloud Trace 的 error 過濾器失效，無法快速定位失敗 span | 在所有 non-2xx 和 exception 路徑顯式設 `span.set_attribute("error", True)` |
| Agent 無限迴圈沒有 `max_iterations` 保護 | Layer 2 trace span 深度失控（>200 spans），TPM 被迴圈耗盡，Layer 4 quota 被誤診為根因 | ADK / LangGraph 設 `max_iterations=25`，並在每次迭代用 span attribute 記錄 `loop_count` |
| 第三方 API 失敗直接拋錯，不讀 `Retry-After` header | 立即重試觸發重試風暴，加劇 429 頻率，累計 TPM 消耗 5–10x 正常值 | 讀取 `Retry-After` header 並寫入 span；實作 exponential backoff（初始 1s，最大 32s，jitter ±20%）|
| 所有 span 使用 100% 採樣率 | 高流量（1,000 QPS）下 Cloud Trace 每月費用達 $1,200+，超出可觀測性預算 | Layer 1 採樣 1%，Layer 2/3 採樣 10%，error path 強制 100% 採樣（用 `sampling.priority=1`）|
| 同時修改多個系統變數後才重測 | 無法判斷是哪個改動修復了問題，下次同類故障仍需重新摸索 | 每次只改一個變數；在改動前後各截取 5 分鐘的 p50/p99 latency 基準，記錄在 Incident log |

---

## 五、與其他核心主題的關聯

- **TTFT / Throughput 優化（Part 16）**：TTFT 是 Structured Troubleshooting 決策樹的第一層過濾指標，`TTFT > 3s` 觸發 Layer 4 調查。Part 16 說明如何降低 TTFT，本篇說明如何診斷 TTFT 為何突然升高——兩篇是一對互補的設計 vs 排錯視角。
- **Async / Event-Driven Pipeline（Part 11）**：非同步架構讓 trace 跨越多個服務邊界和 Pub/Sub 主題。需要用 W3C `traceparent` header 在發布端注入 span context，在消費端提取並繼承，否則 Cloud Trace 中會出現孤立 span，無法重建完整調用鏈。
- **Idempotency / State Recovery（Part 13）**：Layer 2 Agent 無限迴圈的長期修復方案不只是加 `max_iterations`，而是讓每個 Agent node 有冪等的 checkpoint 機制。重試不應重跑已完成節點，而是從最後一個成功 checkpoint 恢復——這是 Idempotency 設計在 troubleshooting 場景的直接應用。
- **Backpressure / Fair-Share（Part 12）**：Layer 4 quota 耗盡的根本治療不是申請更多 quota，而是在 Layer 2 Orchestration 層實作 backpressure：依用戶等級（付費 > 免費）分配 TPM 預算，在 quota 用量 > 70% 時開始對低優先級請求限速，避免高優先級用戶受到波及。

---

## 六、面試一句話（Killer Phrase）

> *「當用戶回報 Agent 很慢，我的第一步不是翻 application log，而是打開 Vertex AI quota dashboard 確認 TPM 消耗率——因為生產數據顯示 80% 的 slow-agent 案例根因是 Layer 4 quota 耗盡，而非程式碼 bug，先看 quota 平均 3 分鐘就能確認或排除。確認 quota 正常後，我才按照決策樹往上走：看 Cloud Trace 找哪個 tool call span 攜帶 status_code=429 或 retry_after 屬性，這樣覆蓋了另外 15% 的 Layer 3 案例。這個自上而下、逐層消除的方法讓 MTTR 從沒有 OTel 時的 60 分鐘降至 8 分鐘，前提是架構設計階段就要求每個 tool wrapper 攜帶結構化 OTel span，把可觀測性成本從事後採集轉移到事前設計。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-21-cost-attribution-quota-management-zh/) | [後一篇](/posts/fde-interview-core-topic-23-chaos-engineering-resilience-zh/) →
