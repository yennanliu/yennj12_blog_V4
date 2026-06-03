---
title: "FDE 面試準備指南（十九）：RKK 實戰——Multi-Agent 系統的統計評估與細粒度追蹤"
date: 2026-06-04T12:00:00+08:00
draft: false
description: "以系統設計視角拆解 Multi-Agent 系統的 Observability 架構：為什麼多 Agent 的評估比 RAG 複雜一個量級、Granular Tracing 的設計原理、Trajectory Evaluation 方法，以及如何找出是哪個 Agent 拖累了整體表現"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Evaluation", "Tracing", "Observability", "LangSmith", "OpenTelemetry", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> 評估 RAG 系統：一個問題進去，一個答案出來，量化兩者的關係。  
> 評估 Multi-Agent 系統：一個問題進去，4 個 Agent 跑了 10 次工具，最後出來一個答案。  
> 中間任何一個環節出了問題，你都看不到——除非你事先設計好追蹤架構。

---

## 面試情境

> **面試官：** 「這是一個由 4 個 Agent 組成、包含 10 次 Tool-calling 的複雜工作流。客戶說最終答案正確率很低。你如何建立統計評估管線？如何進行 Granular Tracing 抓出是哪個 Agent 或哪次 Tool-calling 出問題？」

---

## 一、核心問題：Multi-Agent 的評估為什麼比 RAG 難一個量級

```
RAG 評估的輸入/輸出模型：

  Input: Query
    ↓
  [Single Pipeline]
    ↓
  Output: Answer

  評估點：3 個指標（Context Relevance, Faithfulness, Answer Relevance）
  定位問題：要麼是 Retrieval，要麼是 Generation

Multi-Agent 評估的現實：

  Input: User Request
    ↓
  Router Agent → 分派
    ├── Agent A → Tool 1 → Tool 2 → Output A
    ├── Agent B → Tool 3 → Tool 4 → Tool 5 → Output B
    └── Agent C → Tool 6 → Output C
         ↓
  Synthesis Agent → 整合 A + B + C → Final Answer

  評估點：
  ├── Router 的分派決策對不對？（Routing Accuracy）
  ├── Agent A 的工具呼叫成功率？（Tool Success Rate）
  ├── Agent B 是不是最慢的瓶頸？（Latency by Agent）
  ├── Agent C 的輸出品質？（Output Quality by Agent）
  └── Synthesis Agent 整合時有沒有幻覺？（Faithfulness）

  問題可能在 10 個地方的任何一個
```

---

## 二、可觀測性架構：三層追蹤設計

```
┌──────────────────────────────────────────────────────────────┐
│              User Request 進入                               │
│              分配唯一的 trace_id（e.g. tr_abc123）           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  Agent Execution Layer                       │
│                                                              │
│  每個 Agent Node 自動注入追蹤：                              │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Span: router_agent                                  │    │
│  │  ├── span_id: sp_001                                 │    │
│  │  ├── parent: trace_id                                │    │
│  │  ├── start: 14:23:01.000                             │    │
│  │  ├── end:   14:23:01.450                             │    │
│  │  ├── input: { user_query: "..." }                    │    │
│  │  └── output: { route_to: ["legal", "finance"] }     │    │
│  └──────────────────────────────────────────────────────┘    │
│                          │                                   │
│          ┌───────────────┴───────────────┐                   │
│          │                               │                   │
│  ┌───────▼────────────┐     ┌────────────▼───────────┐       │
│  │ Span: legal_agent  │     │ Span: finance_agent    │       │
│  │ ├── span_id: sp_002│     │ ├── span_id: sp_003    │       │
│  │ ├── parent: sp_001 │     │ ├── parent: sp_001     │       │
│  │ ├── duration: 1.2s │     │ ├── duration: 3.8s ⚠️  │       │
│  │ └── [子 Span: Tool]│     │ └── [子 Span: Tools]   │       │
│  └────────────────────┘     └────────────────────────┘       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│               Telemetry Collector                            │
│                                                              │
│   OpenTelemetry SDK → Cloud Trace / LangSmith / Phoenix     │
│                                                              │
│   每個 Span 的資料：                                         │
│   ├── Latency（每個 Agent 和每次 Tool 呼叫的延遲）            │
│   ├── Token Usage（每個節點消耗多少 token）                   │
│   ├── Input / Output（可選：詳細的輸入輸出記錄）              │
│   └── Error / Exception（工具呼叫失敗的詳細原因）             │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、Granular Tracing：如何定位瓶頸

### 瀑布圖分析

```
一個 Request 的 Trace 視覺化（瀑布圖）：

Time →
0    100ms  500ms  1s    2s    3s    4s    5s
│    │      │      │     │     │     │     │
│
├─── Router Agent ─────────────────────────────── 450ms
│         │
│         ├── Intent Classification ────── 200ms
│         └── Task Dispatch ────────────── 250ms
│
├─── Legal Agent ───────────────────────────────────────── 1,200ms
│         │
│         ├── Tool: search_contracts ──── 800ms ⚠️ 慢！
│         └── LLM Generation ────────── 400ms
│
└─── Finance Agent ─────────────────────────────────────────────────── 3,800ms
          │
          ├── Tool: get_exchange_rate ── 150ms
          ├── Tool: query_erp ──────── 2,900ms ⚠️⚠️ 超慢！
          └── LLM Generation ────────── 750ms

Total E2E: 5,450ms（基本上由 Finance Agent 的 ERP 查詢決定）

結論：瓶頸在 Tool: query_erp（2.9s）
      → 優先優化：加 Cache / 改查詢 SQL / 升級 ERP 連接
```

---

## 四、評估指標體系：Multi-Agent 專用

### 指標分類

```
四類評估指標：

┌─────────────────────────────────────────────────────────────┐
│  1. Routing Accuracy（路由準確性）                           │
│                                                             │
│  問題：Router Agent 有沒有把任務分派給正確的子 Agent？        │
│                                                             │
│  評估方法：                                                  │
│  ├── 準備黃金測試集：每個 Query 標注「應該路由到哪些 Agent」  │
│  ├── 比較 Router 實際路由 vs 預期路由                        │
│  └── 計算：Precision / Recall / F1                          │
│                                                             │
│  例：Query = "分析 Q4 合約的財務風險"                        │
│      預期路由：[legal, finance]                              │
│      實際路由：[finance] （漏了 legal）                      │
│      → Recall = 0.5，有改進空間                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  2. Tool Execution Accuracy（工具執行準確性）                │
│                                                             │
│  問題：LLM 生成的 Tool Call 參數是否正確？工具是否成功執行？  │
│                                                             │
│  指標：                                                      │
│  ├── Tool Call Success Rate：工具成功執行的比例              │
│  ├── Parameter Accuracy：參數是否符合預期格式                │
│  └── Retry Rate：因參數錯誤需要重試的比例                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  3. Trajectory Exact Match（執行路徑評估）                   │
│                                                             │
│  問題：Agent 的執行路徑是否符合預期的最優路徑？               │
│                                                             │
│  黃金路徑（Golden Trajectory）：                             │
│    Router → Legal → Finance → Synthesis → Answer           │
│                                                             │
│  Agent 實際路徑：                                            │
│    Router → Legal → Finance → Legal（多了一步）→ Synthesis  │
│                                                             │
│  Path Efficiency = |Golden Steps| / |Actual Steps|         │
│                  = 4 / 5 = 0.80                            │
│  多了一步說明 Agent 不夠自信，可能需要優化 Prompt            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  4. Cost/Token Efficiency（成本效率）                        │
│                                                             │
│  問題：完成一次任務平均消耗多少 Token 和成本？               │
│                                                             │
│  指標：                                                      │
│  ├── Tokens per Task：完成一次完整任務的 token 消耗          │
│  ├── Cost per Task：以美元計算的成本                         │
│  └── Steps per Task：平均需要幾步才能完成                    │
│                                                             │
│  追蹤趨勢：如果 Tokens/Task 隨時間上升                       │
│  → 可能是歷史 Context 累積過長，需要壓縮策略                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、Eval Pipeline 架構設計

```
┌──────────────────────────────────────────────────────────────┐
│                   Eval Dataset 準備                          │
│                                                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │ 真實用戶查詢    │  │ 邊界情況         │  │ 黃金路徑   │  │
│  │ (生產 logs 抽樣)│  │ (手動設計)       │  │ (人工標注) │  │
│  └─────────────────┘  └──────────────────┘  └────────────┘  │
│               ↓ 100~500 個測試案例                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Automated Eval Runner                           │
│              （Vertex AI Pipelines）                         │
│                                                              │
│  對每個測試案例：                                            │
│  ├── 執行 Multi-Agent 系統，收集完整 Trace                   │
│  ├── 提取每個 Agent 的輸入/輸出/延遲                         │
│  └── 與黃金答案比較                                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│               Multi-level Scoring                            │
│                                                              │
│  Agent Level：                                               │
│  ├── Legal Agent：Accuracy: 0.91, Avg Latency: 1.2s        │
│  ├── Finance Agent：Accuracy: 0.73 ⚠️, Avg Latency: 3.8s ⚠️│
│  └── Synthesis Agent：Faithfulness: 0.88                   │
│                                                              │
│  System Level：                                              │
│  ├── End-to-end Accuracy: 0.82                              │
│  ├── Avg Cost per Task: $0.023                              │
│  └── Avg Steps per Task: 6.2                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│            Regression Detector                               │
│                                                              │
│  與 Baseline 比較：                                          │
│  ├── Finance Agent Accuracy: 0.73 → Baseline: 0.85          │
│  │   下降 14% ⚠️ → 觸發 Alert，阻止部署                     │
│  └── 自動生成診斷報告：哪個 Agent 退步、退步在哪類 Query 上  │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、工具選型：Tracing 平台比較

```
Tracing 工具選型：

                Cloud Trace +        LangSmith           Phoenix (Arize)
                Cloud Logging
──────────────────────────────────────────────────────────────────────────
整合方式        OpenTelemetry SDK    LangChain SDK       OpenTelemetry
LLM 理解度      基礎                 深度（專為 LLM）    深度（專為 LLM）
Token 追蹤      需手動               自動                自動
視覺化          Cloud Console        專屬 UI             專屬 UI
GCP 整合        原生                 需設定             需設定
開源            ✅                   ❌（部分付費）      ✅
適合場景        GCP-native 環境      LangChain 專案      通用 LLM 追蹤

FDE 推薦策略：
  生產環境監控   → Cloud Trace + Cloud Logging（GCP 原生整合）
  開發調試      → LangSmith 或 Phoenix（更好的 LLM 視覺化）
  兩者可以並行，用 OpenTelemetry 統一 instrumentation
```

---

## 七、找到根本原因：從 Trace 到 Insight

```
診斷流程（Finance Agent Accuracy 下降的例子）：

Step 1：Aggregate View
  Finance Agent Accuracy: 0.73
  按 Query 類型分解：
  ├── 匯率計算：0.95（正常）
  ├── ERP 數據查詢：0.51（⚠️ 這裡有問題）
  └── 財務報表分析：0.88（正常）

Step 2：深入 ERP 查詢的 Trace
  查看 Tool Call: query_erp 的 Input/Output
  發現：LLM 生成的 SQL 參數中，日期格式是 "2026-06" 
        但 ERP API 期望的格式是 "202606"
  → Tool Call 參數格式錯誤 → ERP 回傳 Error → Agent 幻覺填補 → 答案錯誤

Step 3：Root Cause
  Finance Agent 的 Tool 描述沒有說明日期格式
  LLM 使用了自以為合理的 ISO 格式，但和 ERP 不符

Step 4：Fix
  更新 Tool Schema：明確說明 date_format: "YYYYMM"
  + 在 Tool Middleware 加 date format validation

Step 5：Verify
  重新跑 Eval → ERP 查詢 Accuracy 從 0.51 回升到 0.91 ✓
```

---

## 八、面試答題要點

> *「Multi-Agent 的評估需要比 RAG 多一個維度：不只看最終答案，也要看每個 Agent 的個別表現。*
>
> *追蹤架構：用 OpenTelemetry 為 Graph 中的每個 Node 和每次 Tool Call 注入 Span，統一收集到 Cloud Trace。每個 Span 記錄：延遲、token 用量、輸入輸出、錯誤原因。*
>
> *評估指標四層：Routing Accuracy（Router 分派對不對）、Tool Execution Accuracy（工具呼叫成功率）、Trajectory Exact Match（執行路徑效率）、Cost/Token Efficiency（成本效率）。*
>
> *診斷方法：從 Aggregate 視圖找到哪個 Agent 分數低，再 drill down 到那個 Agent 的 Trace，找到是哪類 Query、哪個 Tool Call 出問題，最後追到 Root Cause（可能是 Tool Schema 描述不清、API 格式不符等具體問題）。*
>
> *Eval Pipeline 整合進 CI/CD，每次部署前跑完整評估，和 Baseline 比較，任何 Agent 指標下降超過 5% 就阻止部署並觸發 Alert。」*

---

**系列導覽：**  
← [（十八）RKK 實戰：三層記憶體架構與 LLM 成本調優](../fde-interview-guide-part18-memory-cost-tuning-zh/)  
→ [（二十）RKK 實戰：間接 Prompt Injection 與 Dual-LLM 防禦架構](../fde-interview-guide-part20-indirect-prompt-injection-zh/)
