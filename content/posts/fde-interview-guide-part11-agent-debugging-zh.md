---
title: "FDE 面試準備指南（十一）：RKK 實戰——AI Agent 線上除錯與故障排除"
date: 2026-06-03T10:00:00+08:00
draft: false
weight: 11
description: "以系統設計視角拆解 AI Agent 的 Troubleshooting：為什麼 Agent 難 debug、觀測性架構怎麼設計、五大故障模式怎麼追蹤——含完整架構圖與 Google Doc 模擬情境應答框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Debugging", "Troubleshooting", "Observability", "Tracing", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "17 min"
---

> Agent debugging 和傳統程式 debug 的本質差異：  
> 傳統程式出錯，你找 stack trace。  
> Agent 出錯，LLM 的「決策過程」是不透明的——你找不到 stack trace。  
> 所以你必須**在設計時就把觀測能力建進去**，而不是出問題後再想怎麼查。

---

## 一、核心問題：為什麼 Agent 難 debug

```
傳統程式：
  Input → [確定性邏輯] → Output
                ↑
           出錯有 stack trace

Agent：
  Input → [LLM 決策] → [Tool Call] → [LLM 決策] → ... → Output
                ↑                           ↑
        決策過程不透明              中間狀態沒有自動記錄
```

三個讓 Agent debugging 特別難的原因：

1. **非確定性**：同樣的 input 可能產生不同的執行路徑
2. **多步驟**：一個錯誤可能在步驟 1 發生，但直到步驟 8 才顯現
3. **工具依賴**：問題可能在 LLM 層、工具層、還是 data 層——不好定位

---

## 二、系統全貌：觀測性架構

解決思路：在 Agent 的每個關鍵節點插入觀測點。

```
用戶請求
    │
    ▼
┌──────────────────────────────────────────┐
│            Agent Execution               │
│                                          │
│   ┌─────────┐    ┌──────────────────┐    │
│   │  LLM    │    │   Tool Gateway   │    │
│   │         │ ←→ │  (instrumented)  │    │
│   └─────────┘    └──────────────────┘    │
│        │                  │              │
│        ▼                  ▼              │
│   ┌──────────────────────────────────┐   │
│   │         Trace Collector          │   │
│   │  每一步的 thought/action/result  │   │
│   └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              Observability Stack            │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Metrics  │  │  Traces  │  │   Logs   │  │
│  │ (Grafana)│  │(Langfuse)│  │(Cloud    │  │
│  │          │  │          │  │ Logging) │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│       │              │             │        │
│       ▼              ▼             ▼        │
│  系統健康狀態    單次請求路徑    詳細事件記錄  │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              Alerting Layer                  │
│  threshold breach → PagerDuty / Slack alert  │
└─────────────────────────────────────────────┘
```

---

## 三、觀測性三層：各層收集什麼

### Layer 1：Metrics（系統健康）

```
關鍵指標 Dashboard：

延遲                    成本                   品質
─────────────          ──────────────         ──────────────
TTFT p50: 450ms        input tokens/req: 2500  loop_rate: 0.2%
TTFT p95: 1200ms       output tokens/req: 400  fallback_rate: 3.1%
E2E p50:  3.5s         cost/req: $0.0085       tool_fail_rate: 1.4%
E2E p95:  8.0s         monthly: ~$450

← 趨勢異常時第一個看這裡
```

### Layer 2：Traces（請求路徑）

```
Request ID: req_abc123
User: "Q4 銷售數字是多少？"

Step 1  [50ms]  LLM Think    → "需要查資料庫"
Step 2  [230ms] Tool Call    → query_database(q="Q4 sales")
Step 3  [850ms] Tool Result  → {revenue: 4200000}  ← 這步慢
Step 4  [45ms]  LLM Think    → "可以回答了"
Step 5  [380ms] LLM Generate → "Q4 銷售額為 $4.2M"

Total: 1555ms  |  Tokens: 2340  |  Outcome: success
```

### Layer 3：Logs（詳細事件）

```
[WARN] 2026-06-03 14:23:01 req=req_abc123
  Tool: query_database
  Latency: 850ms (threshold: 500ms)
  Query: SELECT SUM(revenue) FROM sales WHERE quarter='Q4'
  Rows returned: 1
  Suggestion: query missing index on `quarter` column

[INFO] 2026-06-03 14:23:01 req=req_abc123
  Faithfulness check: 0.94 (threshold: 0.8) ✓
  Answer grounded in retrieved data
```

---

## 四、五大故障模式：如何識別與根除

### 故障模式總覽

```
Agent 故障樹
│
├── 幻覺（Hallucination）
│       症狀：答案超出知識庫範圍
│       根源：Retrieval 精度差 / Prompt 沒限制 / Context 超限
│
├── 工具呼叫失敗（Tool Failure）
│       症狀：應該用工具卻沒用，或呼叫格式錯誤
│       根源：Tool description 不清楚 / Schema 錯誤
│
├── 無限迴圈（Infinite Loop）
│       症狀：Agent 重複執行相同動作
│       根源：缺乏終止條件 / 工具持續回傳錯誤
│
├── 任務偏移（Task Drift）
│       症狀：Agent 偏離原始目標
│       根源：Multi-turn 後 goal 被稀釋
│
└── Context 錯亂（Context Confusion）
        症狀：Agent 混用不同用戶的資訊
        根源：Session isolation 問題
```

---

### 故障一：幻覺的診斷路徑

```
症狀：回答包含知識庫以外的資訊
    │
    ▼
Q1：Retrieval 有沒有回傳相關文件？
    ├── 沒有（score < 0.7）
    │       → 問題在 Retrieval 層
    │         解法：調整 embedding model、降低 score threshold、
    │               或補充知識庫內容
    │
    └── 有（score ≥ 0.7）
            │
            ▼
        Q2：LLM 收到的 prompt 裡有沒有 context？
            ├── 沒有 → 問題在 Prompt Assembly
            │         解法：Debug context injection 邏輯
            │
            └── 有
                    │
                    ▼
                Q3：LLM 有沒有「超出 context 範圍回答」？
                    → 跑 Faithfulness 評分
                    → < 0.8 → 加強 system prompt 限制：
                               "只根據提供的文件回答，
                                如果文件中沒有答案，
                                回覆：我沒有相關資訊"
```

---

### 故障二：工具呼叫失敗

```
Tool 描述品質 vs 呼叫成功率：

模糊描述：
┌────────────────────────────────┐
│ name: "search"                 │
│ description: "搜尋東西"        │  ← LLM 不知道何時用
└────────────────────────────────┘
  結果：工具被忽略或被濫用

清晰描述：
┌────────────────────────────────────────────────┐
│ name: "search_knowledge_base"                   │
│ description:                                    │
│   "搜尋公司產品知識庫。                          │
│    使用時機：用戶詢問產品規格、故障排除時。       │
│    不適用：一般常識、計算問題。                  │
│ parameters:                                     │
│   query (string): 搜尋關鍵字，建議繁體中文       │
│   top_k (int, default=5): 回傳數量，最大 20"    │
└────────────────────────────────────────────────┘
  結果：工具呼叫率和成功率顯著提升
```

---

### 故障三：無限迴圈偵測

```
迴圈偵測邏輯：

Action History Buffer (sliding window = 5)
│
├── [tool_A, tool_A, tool_A, tool_A, tool_A] → 全部一樣 ⚠️
│       └→ 觸發迴圈警告
│
├── [tool_A, tool_B, tool_A, tool_B, tool_A] → 交替重複 ⚠️
│       └→ 也是迴圈
│
└── [tool_A, tool_B, tool_C, tool_D, tool_E] → 正常進展 ✓

介入策略：
step <= 10  → 繼續執行
step 11~15  → 注入提示："請評估你是否已經獲得足夠資訊可以回答"
step > 15   → 強制輸出當前最佳答案
step > 20   → 硬性終止，回傳 fallback 訊息
```

---

## 五、Debug Session 的工作流

```
生產環境 Agent 出問題，你的排查順序：

Step 1：看 Metrics Dashboard
    │  p95 延遲有沒有異常？tool_fail_rate 有沒有升高？
    │  → 定位問題層（LLM 層 / Tool 層 / Infrastructure 層）
    │
    ▼
Step 2：找出問題請求（Trace 查詢）
    │  按 outcome = "error" 或 latency > p99 過濾
    │  找出 2~3 個具代表性的 trace
    │
    ▼
Step 3：重現問題
    │  拿問題請求的 exact input → 在 staging 重跑
    │  看能不能穩定重現
    │
    ▼
Step 4：逐步縮小範圍
    │  把 Agent 的每個步驟拆開測試：
    │  - Retrieval 單獨測（query → chunks 結果對嗎？）
    │  - Tool 單獨測（直接呼叫，不經 LLM）
    │  - LLM 單獨測（給定 context，回答合理嗎？）
    │
    ▼
Step 5：確認根本原因 → 修復 → 寫 regression test
```

---

## 六、Google Doc 模擬情境應答框架：DARK

RKK 面試中，面試官可能在 Google Doc 貼一段 log，問你分析：

```
D → Diagnose   根據症狀，最可能是哪種故障模式？
A → Ask        你還需要什麼資訊才能確認？（要主動問）
R → Root Cause 推斷最可能的根本原因
K → Kill it    怎麼修，以及怎麼預防再次發生
```

**範例情境：**

面試官貼出：
```
Step 1: Action: query_database → Error: timeout
Step 2: Action: query_database → Error: timeout
Step 3: Action: query_database → Error: timeout
... (重複 20 次)
Step 22: [stopped: max_steps reached]
```

**你的回答：**

> *「這裡有兩個層面的問題。*
>
> *D（診斷）：Tool 層故障 + Agent 層缺乏錯誤處理邏輯。工具持續失敗，但 Agent 只知道重試，不知道換策略。*
>
> *A（我還需要什麼）：資料庫的 slow query log、這段時間的資料庫監控（CPU/connection 數）、這個 query 有沒有 index。*
>
> *R（根本原因）：最可能是資料庫側的問題（高負載或 query 太慢），加上 Agent 的 error handling 缺乏退避和降級邏輯。*
>
> *K（修法）：工具層加 retry with exponential backoff，3 次失敗後回傳結構化錯誤訊息給 Agent。Agent 層收到 tool_unavailable 後，能選擇降級（查快取、回覆用戶資料庫暫時無法存取）。同時在 tool wrapper 加監控，連續 3 次失敗就觸發告警。」*

---

## 七、快速複習卡

```
觀測性三層：
  Metrics（系統健康）→ Traces（請求路徑）→ Logs（事件細節）

五大故障模式：
  幻覺 → Retrieval 診斷 + Faithfulness 評分
  工具失敗 → Tool description 品質 + Instrumented wrapper
  無限迴圈 → Action history 偵測 + max_steps 硬上限
  任務偏移 → 每步對齊 original goal
  Context 錯亂 → Session isolation 驗證

Debug 順序：Metrics → Trace → 重現 → 縮小範圍 → 根因 → 修復 → Regression test

DARK 框架：Diagnose → Ask → Root Cause → Kill it
```

---

**系列導覽：**  
← [（十）RKK 實戰：AI Agent 的 Context Management](../fde-interview-guide-part10-context-management-zh/)  
→ [（十二）RKK 實戰：Agent 統計評估與品質量化](../fde-interview-guide-part12-agent-evaluation-zh/)
