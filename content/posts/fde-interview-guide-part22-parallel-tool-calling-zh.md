---
title: "FDE 面試準備指南（二十二）：RKK 實戰——動態並行 Tool-Calling 與依賴解析引擎"
date: 2026-06-04T15:00:00+08:00
draft: false
description: "以系統設計視角拆解 Multi-Tool 並行執行架構：為什麼順序執行是延遲瓶頸、DAG 依賴解析引擎的設計原理、動態並行 vs 靜態並行的 trade-off，以及 Google ADK Tool Registry 的落地方案"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Tool-Calling", "Concurrency", "DAG", "Parallel", "ADK", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> LLM 說「我需要查 User Profile、Order History、Risk Score」。  
> 最差的工程師說：「好，我一個一個查。」  
> FDE 說：「三個互相獨立——我同時查，總延遲從 T₁+T₂+T₃ 降到 max(T₁,T₂,T₃)。」  
> 這就是這題考的核心思維。

---

## 面試情境

> **面試官：** 「Gemini 判定需要同時呼叫三個工具：get_user_profile、get_order_history、get_risk_score。這三個工具執行時間不同。有時候工具 B 的輸入必須依賴工具 A 的輸出。你如何設計動態工具執行引擎最大化並行，並處理這種動態依賴關係？」

---

## 一、核心問題：順序執行的延遲代價

```
場景：LLM 決定需要呼叫三個工具

  get_user_profile  → 150ms
  get_order_history → 400ms
  get_risk_score    → 300ms

順序執行（最差的方案）：

  時間軸：
  0     150   550   850ms
  │─────│─────│─────│
  [Profile] [Orders] [Risk]
  
  Total: 150 + 400 + 300 = 850ms

並行執行（最優方案，如果互相獨立）：

  時間軸：
  0                 400ms
  │─────────────────│
  [Profile 150ms]
  [Orders  400ms  ] ← 決定總延遲
  [Risk    300ms  ]

  Total: max(150, 400, 300) = 400ms（節省 53%）
```

**在 Multi-turn Agent 中，每次推理前的 Tool 執行延遲會直接累積到 E2E 延遲：**

```
5 輪對話 × 每輪 3 個工具 × 850ms（順序）= 12,750ms
5 輪對話 × 每輪 3 個工具 × 400ms（並行）= 6,000ms

用戶體驗差距：12.75 秒 vs 6 秒
```

---

## 二、依賴關係的三種模式

```
模式 1：完全獨立（Full Independence）
  → 可以全部並行

  get_user_profile ─────────────────────────────────── ✓ 並行
  get_order_history ────────────────────────────────── ✓ 並行
  get_risk_score ──────────────────────────────────── ✓ 並行
  
  所有工具同時啟動，等最慢的那個完成

模式 2：線性依賴（Sequential Dependency）
  → 必須按順序執行

  get_user_credit_limit
        │ 依賴輸出
        ▼
  calculate_max_loan(credit_limit=?)
        │
        ▼
  generate_offer(max_loan=?)
  
  不能並行，每一步都需要上一步的結果

模式 3：部分依賴（Partial Dependency）─── 最常見也最複雜
  → 混合策略：能並行的並行，有依賴的順序

  get_user_profile ────────────────────────┐
  get_account_balance ─────────────────────┤
                                           ▼
                                   calculate_risk(profile+balance)
                                           │
                                           ▼
                                   get_recommended_products(risk_level)
```

---

## 三、DAG-based 動態工具執行引擎架構

```
┌──────────────────────────────────────────────────────────────┐
│                   LLM 回傳工具呼叫請求                        │
│                                                              │
│  [                                                           │
│    { id: "t1", tool: "get_user_profile", depends_on: [] },  │
│    { id: "t2", tool: "get_order_history", depends_on: [] }, │
│    { id: "t3", tool: "get_risk_score", depends_on: ["t1"] },│
│    { id: "t4", tool: "generate_offer", depends_on: ["t2","t3"] }
│  ]                                                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│            DAG Dependency Resolver                           │
│                                                              │
│  解析依賴關係，建立執行圖：                                    │
│                                                              │
│       t1 ──────────────────────────────┐                    │
│                                        ▼                    │
│       t2 ──────────────┐         t3 (depends t1)           │
│                        │               │                    │
│                        ▼               ▼                    │
│                   t4 (depends t2, t3) ─────────────────     │
│                                                              │
│  執行層次（Execution Tiers）：                               │
│  Tier 1: [t1, t2]  → 無依賴，立即並行執行                   │
│  Tier 2: [t3]      → 等 t1 完成後執行                       │
│  Tier 3: [t4]      → 等 t2 和 t3 都完成後執行               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             Parallel Execution Engine                        │
│                                                              │
│  Tier 1 執行（並行）：                                        │
│  ├── Coroutine: get_user_profile() ────── 150ms             │
│  └── Coroutine: get_order_history() ───── 400ms             │
│                                                              │
│  等 Tier 1 全部完成（400ms）                                 │
│                                                              │
│  Tier 2 執行（t1 的結果已就緒）：                             │
│  └── Coroutine: get_risk_score(profile=t1.result) ─ 300ms  │
│                                                              │
│  等 Tier 2 完成（300ms）                                     │
│                                                              │
│  Tier 3 執行（t2, t3 的結果都就緒）：                         │
│  └── Coroutine: generate_offer(orders=t2, risk=t3) ─ 200ms │
│                                                              │
│  Total: 400 + 300 + 200 = 900ms                             │
│  vs 順序執行: 150 + 400 + 300 + 200 = 1,050ms               │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、執行引擎的設計選型

```
選項比較：

                asyncio.gather()     ThreadPoolExecutor    Google ADK
──────────────────────────────────────────────────────────────────────
適用場景         I/O 密集型工具       CPU 密集型 / 阻塞呼叫  ADK 整合的工具
                （HTTP API 呼叫）     （舊版同步 SDK）
GIL 影響         不受影響             受影響（Python GIL）   不受影響
延遲              最低                有線程切換開銷          ADK 管理
DAG 支援         需自建               需自建                 內建
Tool Registry    需自建               需自建                 內建
錯誤隔離         需手動              需手動                  內建
可觀測性         需手動加 Trace       需手動加 Trace          內建 Trace

推薦策略：
  └── 新建系統、在 Google Cloud 上：Google ADK（最省開發成本）
  └── 已有 LangChain/LangGraph 系統：asyncio.gather() 為主
  └── 有大量同步遺留 SDK：ThreadPoolExecutor（但注意 GIL）
```

---

## 五、Google ADK 的 Tool Registry 架構

```
ADK Tool Registry 解決什麼問題：

傳統做法：
  工具定義分散在程式碼各處
  依賴關係靠 LLM 自行推斷或手動 hardcode
  每次新增工具都要修改 Agent 邏輯

ADK Tool Registry：

  ┌─────────────────────────────────────────────────────┐
  │  Tool Registry（工具目錄）                           │
  │                                                     │
  │  每個工具都宣告：                                    │
  │  ├── name: "get_risk_score"                         │
  │  ├── description: "計算用戶的信用風險評分"           │
  │  ├── input_schema: { user_id, profile_data }        │
  │  ├── output_schema: { risk_level, risk_score }      │
  │  └── depends_on: ["get_user_profile"]  ← 顯式宣告  │
  └─────────────────────────────────────────────────────┘
           │ LLM 查詢 Registry，自動理解依賴關係
           ▼
  ┌─────────────────────────────────────────────────────┐
  │  ADK Orchestrator                                    │
  │  ├── 自動解析依賴圖                                  │
  │  ├── 自動並行執行獨立工具                            │
  │  └── 自動將上游工具輸出注入下游工具輸入              │
  └─────────────────────────────────────────────────────┘
```

---

## 六、錯誤處理策略

```
並行執行時的錯誤處理：

策略 1：Fail-fast（一個失敗，全部停止）
  適用：所有工具的結果都必須有，缺一不可
  例：生成財務報告必須同時有用戶資料和帳戶餘額，缺一則報告無意義

策略 2：Partial Success（允許部分失敗）
  適用：某些工具的結果是 optional 的
  例：產品推薦可以在沒有 Risk Score 的情況下降級處理

策略 3：Retry with Fallback
  ┌──────────────────────────────────────────────────────┐
  │  工具執行失敗                                         │
  │       │                                              │
  │       ▼                                              │
  │  重試 1 次（立即）                                    │
  │       │ 仍失敗                                       │
  │       ▼                                              │
  │  重試 2 次（延遲 1s）                                 │
  │       │ 仍失敗                                       │
  │       ▼                                              │
  │  使用 Fallback 值或 Cached 舊結果                    │
  │       │                                              │
  │  記錄 Warning，讓 LLM 知道某個工具不可用              │
  │  讓 LLM 決定是否能在部分資訊下繼續                   │
  └──────────────────────────────────────────────────────┘
```

---

## 七、動態依賴：LLM 自行生成依賴關係

```
進階設計：讓 LLM 自己宣告工具間的依賴

Prompt 設計（讓 LLM 輸出帶依賴資訊的 Tool Call）：

  System Prompt 補充：
  「當你決定呼叫多個工具時，請在 tool_calls 中標明：
   - 哪些工具可以並行執行（depends_on: []）
   - 哪些工具依賴其他工具的輸出（depends_on: ["tool_id"]）
   
   這有助於系統最佳化執行順序。」

LLM 可能輸出：
  [
    { "id": "t1", "tool": "get_market_data", "depends_on": [] },
    { "id": "t2", "tool": "get_competitor_info", "depends_on": [] },
    { "id": "t3", "tool": "analyze_opportunity",
      "depends_on": ["t1", "t2"],
      "note": "需要市場數據和競品資訊才能分析" }
  ]

這讓執行引擎能動態構建 DAG，而不是每次都重新推斷
```

---

## 八、面試答題要點

> *「這道題的核心是：識別哪些工具可以並行，哪些有依賴關係，然後設計執行引擎最大化並行度。*
>
> *架構設計：LLM 輸出 tool_calls 後，中間層先建立 DAG 依賴圖。無依賴的工具分為同一個 Execution Tier，並行執行（asyncio.gather() 或 Google ADK 的並行框架）；有依賴的工具等上游完成後才啟動，並自動注入上游的輸出結果。*
>
> *延遲改善量化：原本 T₁+T₂+T₃=850ms，並行後 max(T₁,T₂,T₃)=400ms，降低 53%。在多輪對話中效果更顯著。*
>
> *Google ADK 的優點：Tool Registry 可以讓工具顯式宣告依賴關係，Orchestrator 自動管理並行和輸出傳遞，省去手動 DAG 解析的工程量。*
>
> *錯誤策略：依業務需求選 Fail-fast（缺任何工具都不行）或 Partial Success（部分工具失敗可降級處理），並有 Retry with Fallback 機制。」*

---

**系列導覽：**  
← [（二十一）RKK 實戰：長任務 Agent 的異步分散式架構](../fde-interview-guide-part21-async-longrunning-agent-zh/)  
→ [（二十三）RKK 實戰：多租戶 Agent 的限流、Fair-Share 與 Token 預算控制](../fde-interview-guide-part23-ratelimit-fairshare-zh/)
