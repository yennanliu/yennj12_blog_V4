---
title: "FDE 面試準備指南（三十五）：RKK 實戰——生產級可觀測性設計：Granular Tracing、Span 樹與 Cloud Trace 整合"
date: 2026-06-05T13:00:00+08:00
draft: false
weight: 35
description: "以系統設計視角拆解 Agentic AI 系統的可觀測性：為什麼 Log 不夠、Span 樹的結構設計、OpenTelemetry 與 Cloud Trace 的整合模式、Sampling 策略的 Trade-off，以及一條 Trace 應該回答哪五個診斷問題"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Observability", "Tracing", "OpenTelemetry", "Cloud Trace", "Vertex AI", "Agent", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "18 min"
---

> 面試官問「P95 延遲突然升高，你怎麼辦？」  
> 多數人說「我去看 Logs」。  
> 強力雇用的答案是：「我打開 Trace，找哪個 hop 吃掉了時間。」  
> Log 告訴你發生了什麼；Trace 告訴你在哪裡、花了多少。

---

## 面試情境

> **面試官：**「你幫客戶部署了一個 ADK Multi-Agent 系統：並行查三個後端、彙整後做決策。上線後客戶回報：有時候 2 秒，有時候 15 秒。你不在客戶現場。你如何在 5 分鐘內定位問題？你的可觀測性設計是什麼？」

---

## 一、為什麼 Log 不夠，需要 Trace

```
Log 的問題：只記錄「發生了什麼」，不記錄「在哪裡、花了多久」

一個 Multi-Agent 請求的真實路徑：

  User Query
      │
      ▼
  Orchestrator Agent
      ├── LLM Call #1（決策）         ?ms
      ├── ParallelAgent
      │    ├── Sub-Agent A             ?ms
      │    │    ├── Embedding Call
      │    │    ├── Vector Search      ← 瓶頸在這裡？
      │    │    └── LLM Call #2
      │    ├── Sub-Agent B             ?ms
      │    │    └── DB Query
      │    └── Sub-Agent C             ?ms
      │         └── External API      ← 還是這裡？
      └── LLM Call #3（整合）         ?ms

  Log 只能告訴你：「LLM Call #3 回傳了 X」
  Trace 能告訴你：「整條路徑花了 15 秒，
                   其中 12 秒在 Sub-Agent A 的 Vector Search」

  沒有 Trace：猜
  有 Trace：找到
```

---

## 二、Span 樹的結構設計

```
一條 Trace = Root Span + 多層 Child Spans（樹狀結構）

┌─────────────────────────────────────────────────────────────────┐
│  ROOT SPAN: agent.run（orchestrator）           total: 15,240ms │
│                                                                  │
│  ├── SPAN: llm.generate #1                           280ms      │
│  │   attrs: model=gemini-2.0-flash                              │
│  │          input_tokens=1,200  output_tokens=85                │
│  │          finish_reason=STOP                                   │
│  │                                                              │
│  ├── SPAN: parallel_agent.run                      14,700ms     │
│  │   │                                                          │
│  │   ├── SPAN: sub_agent.A                         14,650ms ← ! │
│  │   │   ├── SPAN: embedding.create                   45ms      │
│  │   │   ├── SPAN: vector_search          ← 14,520ms ← !! │
│  │   │   │   attrs: index=prod-v2, top_k=5                      │
│  │   │   │          num_results=5, query_len=128                 │
│  │   │   └── SPAN: llm.generate #2                    85ms      │
│  │   │                                                          │
│  │   ├── SPAN: sub_agent.B                            320ms     │
│  │   │   └── SPAN: tool.db_query                      290ms     │
│  │   │                                                          │
│  │   └── SPAN: sub_agent.C                            480ms     │
│  │       └── SPAN: tool.external_api                  450ms     │
│  │                                                              │
│  └── SPAN: llm.generate #3                          260ms      │
│      attrs: input_tokens=3,400  output_tokens=320               │
└─────────────────────────────────────────────────────────────────┘

5 分鐘診斷：瀑布圖一眼看出 vector_search 佔了 95% 的延遲。
根本原因：vector index 過大，缺少 min-instances，每次 cold query 重新載入。
```

---

## 三、Span 的 Attribute 設計

```
每種 Span 類型應記錄的關鍵 Attributes：

  Span 類型          必錄 Attributes                   用途
  ───────────────────────────────────────────────────────────────────
  agent.run          agent_name, input_len,             追蹤哪個 Agent 慢
                     output_len, iteration_count
  ───────────────────────────────────────────────────────────────────
  llm.generate       model, input_tokens,               成本和速度監控
                     output_tokens, latency_ms,
                     finish_reason, tokens_per_sec
  ───────────────────────────────────────────────────────────────────
  tool.call          tool_name, success (bool),         找失敗的 Tool
                     error_type, latency_ms
  ───────────────────────────────────────────────────────────────────
  vector_search      index_name, top_k,                 找 Retrieval 瓶頸
                     num_results, latency_ms
  ───────────────────────────────────────────────────────────────────
  embedding.create   model, input_len, latency_ms       Embedding 成本

「Granular」的定義：
  不只記錄「整個 Agent 跑了多久」，
  而是每一個 LLM 呼叫、每一個 Tool 呼叫、每一個 Vector Search
  都有自己的 Span 和精確的時間戳記。

不應該記錄在 Span Attributes 裡的：
  ❌ Prompt 原文（可能含有 PII）
  ❌ LLM 輸出原文（可能含有敏感業務資料）
  ✅ 只記錄長度、token 數、結構化的狀態碼
```

---

## 四、OpenTelemetry + Cloud Trace 整合

```
工具選擇：為什麼用 OpenTelemetry（OTel）

  OTel 是業界標準框架：
  ├── 語言無關（Python、Node.js、Go、Java）
  ├── 後端無關（Cloud Trace、Jaeger、Datadog、Zipkin）
  └── ADK 和 Vertex AI SDK 都有 OTel 整合點

  替代方案比較：
  ┌─────────────────┬──────────────────────┬──────────────────────┐
  │                 │  OTel + Cloud Trace   │  直接用 Cloud Logging │
  ├─────────────────┼──────────────────────┼──────────────────────┤
  │  瀑布圖視覺化    │  ✅ 原生支援           │  ❌ 需要自己解析時間   │
  │  跨 Agent 追蹤  │  ✅ Trace ID 串聯      │  ❌ 要手動 JOIN Log    │
  │  P95 分析       │  ✅ Cloud Trace 內建   │  ❌ 要自己寫 Query     │
  │  設定複雜度      │  中（需要 Exporter）  │  低（已有 Log）        │
  │  廠商鎖定        │  低（OTel 是開放標準）│  中（Cloud Logging）  │
  └─────────────────┴──────────────────────┴──────────────────────┘
  結論：生產 Multi-Agent 系統，OTel + Cloud Trace 是必要的。
        Log 只能做補充，不能替代 Trace。

整合架構：

  ADK Agent Code
      │ OTel SDK（instrument 每個 Span）
      ↓
  OTLP Exporter（BatchSpanProcessor）
      │ 批次上送，降低對 Agent 的效能影響
      ↓
  Cloud Trace API（GCP）
      │
      ↓
  Cloud Trace UI（瀑布圖 / 延遲分佈 / Span 搜尋）
```

---

## 五、一條 Trace 應該回答的五個診斷問題

```
問題 1：哪個 hop 是延遲瓶頸？
  → 看 Span duration，找最長的那個
  → 範例：Vector Search 14,520ms（總延遲的 95%）
  → 行動：調整 Vector Search 配置（min-instances / index 優化）

問題 2：Token 在哪裡被消耗？
  → 看每個 llm.generate Span 的 input_tokens
  → 範例：Orchestrator LLM Call #3 的 input_tokens=3,400
           （Sub-Agent 的結果被完整傳入，沒有做摘要）
  → 行動：在 Sub-Agent 輸出進入 Orchestrator 前做摘要截斷

問題 3：哪個 Tool 最常失敗？
  → 過濾 tool.success=false 的 Span
  → 範例：external_api 在 14:00-16:00 有 12% 失敗率
  → 行動：外部 API 問題，不是 AI 問題，通知客戶

問題 4：Sub-Agent 有沒有真正並行？
  → 看 ParallelAgent 的 child spans 時間是否重疊
  → 範例：Sub-Agent B 和 C 在等 Sub-Agent A 跑完才開始
           （並行設計失效，實際是序列）
  → 行動：ADK ParallelAgent 配置問題，檢查依賴關係

問題 5：LLM 有沒有被截斷？
  → 看 llm.generate Span 的 finish_reason
  → 範例：finish_reason=MAX_TOKENS（被截斷，沒有完整輸出）
  → 行動：增加 max_output_tokens 或減少 input context
```

---

## 六、Sampling 策略的 Trade-off

```
問題：100% Trace 在高流量下成本太高

  50,000 QPS × 20 Spans/request = 100 萬 Spans/秒
  Cloud Trace 計費：$0.20 per 100 萬 Spans
  = $17,280/天（100% Sampling）← 不可接受

分層 Sampling 策略：

  流量類型              Sampling Rate     理由
  ──────────────────────────────────────────────────────────────
  異常請求              100%              需要完整診斷資料
  （latency > 5s 或 error）
  ──────────────────────────────────────────────────────────────
  Dev / Staging         100%              找問題時需要完整資料
  ──────────────────────────────────────────────────────────────
  Production 正常流量   1%                控制成本，統計上足夠
  ──────────────────────────────────────────────────────────────
  Production 高峰       0.1%              高峰期成本控制
  ──────────────────────────────────────────────────────────────

  策略：Head-based Sampling（在請求開始時決定要不要採樣）
  + Tail-based Sampling（結束後如果 latency > threshold，強制保留）

  實作：
  from opentelemetry.sdk.trace.sampling import (
      TraceIdRatioBased,   # 按比例隨機採樣
      ParentBased,         # 繼承 parent 的採樣決策
  )
  # 生產：1% 隨機 + 100% 保留異常
  sampler = ParentBased(root=TraceIdRatioBased(0.01))
```

---

## 七、系統效應：加入 Tracing 對系統的影響

```
維度            有 Tracing               沒有 Tracing
──────────────────────────────────────────────────────────────────
問題定位時間    5 分鐘（看瀑布圖）        數小時（猜測 + 加 Log + 重現）
──────────────────────────────────────────────────────────────────
效能影響        < 1% 延遲增加             無
（BatchExporter 非同步上送）
──────────────────────────────────────────────────────────────────
成本            Cloud Trace 費用          節省 Trace 費用，
                （依 Sampling 調整）       但付出更多工程師 Debug 時間
──────────────────────────────────────────────────────────────────
穩定性洞察      每個外部依賴的 P95        只知道整體慢，
                分開可見                   不知道是哪個依賴
──────────────────────────────────────────────────────────────────
Root Cause 能力 精確到 Span 層級           只能到「系統」層級
                （vector_search 14s）      （「系統有時候慢」）
──────────────────────────────────────────────────────────────────
合規風險        需確保 PII 不進 Spans      相對安全，但失去診斷能力

關鍵設計原則：
  Tracing 是上線前必須建好的基礎設施，不是出問題後才加的補救工具。
  「出問題再加 Tracing」代表你永遠無法診斷「第一次出問題」的情況。
```

---

## 八、Trade-off 總覽

```
選擇面         選項 A                   選項 B              建議
─────────────────────────────────────────────────────────────────
Trace Backend  Cloud Trace（GCP 原生）  Jaeger/Zipkin（自建）Cloud Trace（省維護）
─────────────────────────────────────────────────────────────────
Sampling       1% Random               100%                分層策略（右欄說明）
               低成本                   高成本/高覆蓋
─────────────────────────────────────────────────────────────────
Instrumentation 手動 OTel              ADK 內建 Logging     OTel（Span 粒度更細）
─────────────────────────────────────────────────────────────────
PII 處理       記錄 Prompt 內容         只記錄 token 數/長度  只記錄數字，不記錄內容
               （高 Debug 能力）         （合規安全）
─────────────────────────────────────────────────────────────────

什麼場景可以跳過 Granular Tracing？
  ├── Dev / POC 階段（Cloud Logging 夠用）
  ├── 單一 LLM 呼叫的簡單應用（沒有 Multi-Agent 複雜性）
  └── 流量 < 100 QPS（問題可以靠 Log 追查）

什麼場景一定要有 Granular Tracing？
  ├── Multi-Agent 系統（多層呼叫，Log 無法重建執行路徑）
  ├── 有 SLA 要求（P95 < 5s，需要量化每個 hop 的貢獻）
  └── 有外部依賴（外部 API / DB，需要區分是誰的問題）
```

---

## 九、面試答題要點

> *「這道題的核心是：當 Multi-Agent 系統出問題，你如何在不重現問題的情況下找到根因。*
>
> *架構設計：每個 Agent.run、LLM.generate、Tool.call、Vector Search 都有獨立的 Span，帶 latency_ms、token 數、success/fail 等 Attributes。用 OpenTelemetry SDK + Cloud Trace Exporter，BatchSpanProcessor 非同步上送，對 Agent 的效能影響 < 1%。*
>
> *診斷流程：打開 Cloud Trace，過濾 latency > 10s 的請求，看瀑布圖找最長 Span。如果是 vector_search：索引或配置問題。如果是 tool.call 且 success=false：外部依賴問題。如果是 llm.generate 且 input_tokens 異常大：context 截斷問題。*
>
> *Sampling 策略：Production 正常流量 1% 採樣，異常請求（latency > 5s）100% 保留。控制 Cloud Trace 成本，同時確保能診斷所有異常。*
>
> *PII 原則：Span Attributes 只記錄 token 數和長度，不記錄 Prompt 原文和 LLM 輸出內容——這些可能含有 PII，不應該進入 Trace 儲存。」*

---

**系列導覽：**  
← [（三十四）RKK Mock 情境題庫](../fde-interview-guide-part34-mock-scenarios-zh/)  
← [（三十六）生產級 Eval Pipeline 設計](../fde-interview-guide-part36-eval-pipeline-zh/)
