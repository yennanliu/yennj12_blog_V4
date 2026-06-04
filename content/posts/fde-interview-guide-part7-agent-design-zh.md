---
title: "FDE 面試準備指南（七）：Agent 深度設計——ReAct vs Planner、Tool Routing、Multi-Agent"
date: 2026-05-31T10:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 Agent 系統設計的五大主題：ReAct vs Planner-Executor 架構選擇、Tool Routing 四層漏斗、Multi-Agent 邊界、Loop 終止策略，以及 Memory 系統設計"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "ReAct", "Planner", "Multi-Agent", "Tool Routing", "Memory", "LangGraph", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> Agent 面試的陷阱不是問你能不能架起來。  
> 是問你在什麼情況下選哪種架構，以及出問題時你怎麼 debug。  
> 架構選擇題沒有標準答案，有的是 trade-off 意識。

---

## 面試情境

> **面試官：**「你設計的 Agent 系統用的是 ReAct 還是 Planner-Executor？為什麼？如果這個 Agent 有 20 個工具，你怎麼讓它找到正確的工具？多輪對話中它怎麼記住之前說過的事？」

這三個問題連在一起問，是 FDE RKK 的標準深度追問模式。

---

## 一、ReAct vs Planner-Executor：核心架構選擇

### ReAct（Reasoning + Acting）

```
ReAct 的執行模型：

  任務輸入
     │
     ▼
  Thought（LLM 推理：我現在應該做什麼？）
     │
     ▼
  Action（呼叫 Tool 或輸出最終答案）
     │
     ▼
  Observation（Tool 的執行結果）
     │
     └──────────────────────────────→ 再回到 Thought
                                      直到輸出 final_answer

特性：
  ├── 每一步都由 LLM 動態決策
  ├── 可以根據 Observation 隨時調整策略
  └── Context 隨步驟累積（第 20 步的 context 包含前 19 步的 trace）
```

**ReAct 的適用場景：**
- 任務需要「探索」——不確定要幾步、中途可能改方向
- 工具的回應結果會影響下一步選擇
- 快速原型，架構簡單

**ReAct 的限制：**
- 每步都呼叫 LLM，延遲高、成本高
- Context 線性累積，長任務很快接近 window 上限
- 容易陷入循環（Observation 沒有進展但 LLM 繼續嘗試）

---

### Planner-Executor

```
Planner-Executor 的執行模型：

  任務輸入
     │
     ▼
  Planner LLM（一次生成完整計畫）
     │
     ▼
  計畫（顯式的 DAG）：
  {
    steps: [
      {id:1, tool:"search_kb", input:"Q4 target",   depends:[]},
      {id:2, tool:"query_db",  input:"Q4 revenue",  depends:[]},
      {id:3, tool:"calculate", input:"2/1 * 100",   depends:[1,2]},
      {id:4, tool:"gen_report",input:"steps 1-3",   depends:[3]}
    ]
  }
     │
     ▼
  Executor（按 DAG 執行，能並行無依賴的步驟）
     │
     ▼
  Steps 1,2 並行執行（各自不依賴對方）
  Step 3 等 1,2 完成後執行
  Step 4 等 3 完成後執行
     │
     ▼
  （可選）Reviewer LLM 驗證結果，判斷是否需要重新規劃
```

**Planner-Executor 的適用場景：**
- 任務結構清楚，可以預先規劃步驟
- 有可並行的子任務（大幅降低延遲）
- 需要可審計的執行記錄（計畫是顯式的）

**Planner-Executor 的限制：**
- 初始計畫錯了，後續全部跑偏（需要 Reviewer 補救）
- 無法處理「下一步取決於上一步結果的不確定情況」
- 架構更複雜，需要 DAG 執行引擎

---

### 選哪個：決策矩陣

```
                    任務結構清楚？
                         │
            ┌────────────┼────────────┐
           是              否
            │                          │
    需要並行執行？          需要探索？
            │                          │
     ┌──────┴──────┐           ┌───────┴────────┐
    是              否         是                否
     │               │          │                 │
Planner-Executor   Planner-   ReAct           ReAct
（並行 DAG）        Executor   （探索型）      （預設選擇）

額外因素：
  ├── 需要可審計的執行記錄 → Planner-Executor
  ├── 快速原型 → ReAct
  └── 任務長、context 容易爆 → Planner-Executor（Planner 不帶 Observation history）
```

---

## 二、Tool Routing：20 個工具怎麼找到正確的一個

當 Agent 有很多工具（10+），把所有 schema 都塞進 context 會有問題：

```
工具過多的後果：

  10 個工具 × 平均 200 tokens/schema = 2,000 tokens
  50 個工具 × 平均 200 tokens/schema = 10,000 tokens
                                        ↑
                          這還沒包含 system prompt、history、context
                          LLM 選工具的準確率也會隨工具數量增加而下降
                          （Needle-in-a-Haystack 問題）
```

### 四層漏斗架構

```
用戶輸入
    │
    ▼
┌──────────────────────────────────────────┐
│  Layer 1：Rule-Based 快速過濾             │
│  Pattern 確定的 → 直接路由，不過 LLM      │
│  「查訂單」→ CRM Tool                    │
│  「上傳圖片」→ Vision Tool               │
│  費用：幾乎為零                           │
└──────────────────┬───────────────────────┘
                   │（Pattern 不確定）
    ▼
┌──────────────────────────────────────────┐
│  Layer 2：Tool Retrieval（向量搜尋）      │
│  把所有工具的 description embed 成向量   │
│  用 Query 搜尋最相關的 Top-5 個工具      │
│  費用：embedding 呼叫，極低              │
└──────────────────┬───────────────────────┘
                   │（Top-5 候選）
    ▼
┌──────────────────────────────────────────┐
│  Layer 3：LLM 最終決策                   │
│  只送 Top-5 工具的 schema 給 LLM         │
│  LLM 從 5 個裡選 1 個，準確率高          │
│  費用：LLM token，但 schema 大幅縮短      │
└──────────────────┬───────────────────────┘
                   │（選定工具 + 參數）
    ▼
┌──────────────────────────────────────────┐
│  Layer 4：Input Validation               │
│  驗證 LLM 生成的 tool call 參數合法      │
│  例如：SQL injection、越權操作           │
└──────────────────────────────────────────┘
```

---

### Tool Description 的設計質量

這是容易被忽略但很重要的細節：

```
差的 tool description（搜尋找不到）：
  "get_data" - "Get data from the system"

好的 tool description（語意清楚，搜尋準確）：
  "query_crm_order_status" - "Query the CRM system to get the current
  shipping status, estimated delivery date, and order history for a
  customer's order. Use when user asks about order tracking,
  delivery, or shipment."

原則：
  ├── 說清楚「在什麼情況下用這個工具」（比功能描述更重要）
  ├── 包含用戶可能說的關鍵詞（order tracking, delivery, shipment）
  └── 說清楚工具的輸出是什麼
```

---

## 三、Multi-Agent 的設計邊界

面試官最愛問：「你為什麼需要 Multi-Agent？Single-Agent 加更多 Tool 不夠嗎？」

### Single-Agent 的真正極限

```
Single-Agent 開始撐不住的四個信號：

信號 1：Context Window 逼近上限
  20 輪 × 每輪平均 2,000 tokens = 40,000 tokens，
  加上 system prompt + context，已接近許多模型的上限

信號 2：一個 Agent 要扮演太多不同角色
  「你是法律助理，同時也是數據分析師，同時也是報告撰寫者」
  → System Prompt 互相矛盾，模型無所適從

信號 3：有可並行的獨立子任務
  「同時搜集市場資料 + 分析競品 + 撰寫摘要」
  Sequential 跑完需要 T1+T2+T3，Parallel 只需要 max(T1,T2,T3)

信號 4：需要獨立的驗證視角
  Generator 驗證自己的輸出，效果差。
  獨立的 Critic Agent 有不同的 system prompt，更容易找到問題
```

### 三種模式的選擇邏輯

```
Supervisor-Worker：
  適合：任務可分解為獨立子任務，需要協調
  警告：Supervisor 的 prompt 設計要避免「轉述失真」
        Supervisor 看到的是 Worker 的摘要，不是完整執行 trace

Pipeline：
  適合：有明確的線性依賴關係（A 的輸出是 B 的輸入）
  警告：前段的錯誤會放大——Step 1 錯了，Step 2、3、4 都跑偏

Peer Review（Generator + Critic）：
  適合：輸出品質要求高，允許多輪迭代的成本
  警告：必須設定最大迭代次數，否則可能無限循環
```

---

## 四、Loop 終止：四種停滯模式

**面試官最想看到的是：你對每種失敗模式都有對應的偵測機制，而不只是說「加 max_loops」。**

```
停滯模式 1：進度停滯（Stagnation）
  症狀：LLM 一直嘗試同樣的工具，Observation 類似但沒有進展
  偵測：比較最近 Observation 的語意相似度
        similarity(obs[n], obs[n-2]) > 0.9 → 視為停滯

停滯模式 2：矛盾循環（Contradiction）
  症狀：Agent A 指示「執行 X」，Agent B 指示「不要執行 X」
        在 Multi-Agent 中常見
  偵測：追蹤「對同一個狀態字段的衝突寫入」
  解法：Conflict Resolution Policy（最新覆蓋 or 高優先級 Agent 優先）

停滯模式 3：目標漂移（Goal Drift）
  症狀：原本要做 A，中途工具呼叫引導到 B，越走越偏
  偵測：每 K 步比較當前 Context 和 original goal 的語意距離
  解法：定期注入「你的原始目標是 X，你目前的進度符合嗎？」的 Reflection Prompt

停滯模式 4：資源耗盡（Resource Exhaustion）
  症狀：LLM 不斷生成 Thought，context 線性增長，最終超出 window
  偵測：監控 current_token_count / context_window_limit
        超過 80% 時觸發壓縮或終止

應對設計：
  ├── Hard Limits（最基礎）：max_steps + timeout + token_budget
  ├── Progress Detector（偵測停滯）：每 5 步執行
  ├── Reflection Prompt（偵測漂移）：每 10 步執行
  └── Human-in-the-Loop（高風險操作）：即時觸發
```

---

## 五、Memory 系統設計

面試官問：「你的 Agent 如何在多輪對話中記住上下文？記憶滿了怎麼辦？」

### 四種記憶類型與設計位置

```
┌──────────────────────────────────────────────────────────────────┐
│                      Agent Memory 架構                            │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  In-Context Memory（即時記憶）                             │   │
│  │  對話 history 放在 context window 裡                       │   │
│  │  優點：簡單、全部可見   缺點：隨輪次增長，成本 O(n)        │   │
│  └───────────────────────────────────────────────────────────┘   │
│                              ↓ 超過閾值，觸發壓縮               │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  Summary Buffer（壓縮記憶）                                │   │
│  │  超過 N 輪的歷史 → LLM 壓縮成摘要                         │   │
│  │  保留近期完整 history + 早期摘要                           │   │
│  │  優點：控制長度   缺點：壓縮會遺失細節                     │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  External Memory（外部記憶）                               │   │
│  │  ├── Key-Value Store：用戶偏好、設定（Redis）              │   │
│  │  ├── Vector Store：語意記憶，相關時 retrieve（Pinecone）   │   │
│  │  └── Relational DB：結構化歷史，可查詢（Cloud SQL）        │   │
│  │  優點：不佔 context   缺點：需要 retrieve 機制             │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  Episodic Memory（情節記憶）                               │   │
│  │  記住過去任務的「事件摘要」：用了什麼工具、結果是什麼      │   │
│  │  下次類似任務時 retrieve，作為執行參考                     │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 記憶設計的三個關鍵決策

```
決策 1：什麼值得記住？
  └── 不是所有對話都值得存進長期記憶
      標準：會影響未來行為的資訊才存
      例子：「用戶偏好簡短回答」值得記，「用戶今天問了天氣」不值得

決策 2：記憶什麼時候更新？
  └── Write-on-Update：用戶說「我改變主意了」→ 立刻更新
  └── Periodic Consolidation：每 N 輪對話做一次「記憶整理」
  └── Importance-based：只有「重要事件」才寫入長期記憶

決策 3：如何 Retrieve？
  └── 語意搜尋（Vector Store）：找「概念相似」的記憶
  └── 關鍵字搜尋：找「包含特定詞」的記憶
  └── 時間加權：最近的記憶優先（但不能唯一標準）
```

---

## 六、架構選擇速查表

```
問題                              選擇
────────────────────────────────────────────────────────────
任務需要動態決策                    ReAct
任務結構清楚，有並行子任務           Planner-Executor + 並行 DAG
工具太多（10+）                    Tool Retrieval + LLM Router（漏斗架構）
任務複雜、需要專業分工              Multi-Agent（Supervisor-Worker）
防無限循環                         Hard Limits + Progress Detection + Reflection
需要跨 session 記憶                External Memory（Vector Store）
記憶超出 context 上限              Summary Buffer + 壓縮策略
高風險操作                         Human-in-the-Loop + Timeout Policy
```

---

## 七、面試官地雷題

**地雷 1：「ReAct 和 Chain-of-Thought 有什麼差別？」**

```
答：CoT 只有「Thought」，沒有「Action」和「Observation」。
    CoT 是讓 LLM 在一次生成中展示推理步驟，但它不能執行工具。
    ReAct 在 CoT 的基礎上加了 Tool Calling Loop——
    LLM 不只是想，還能執行動作，觀察結果，再繼續思考。
    ReAct 是「可以互動環境的 CoT」。
```

**地雷 2：「Tool Retrieval 如果搜尋到錯誤的工具怎麼辦？」**

```
答：這是 Tool Retrieval 最大的風險——
    如果正確的工具沒有被搜尋到，LLM 就沒有機會選它。
    解法有三個：
    1. 提高 Top-K（從 5 增加到 10），降低遺漏率，但增加 LLM 的選擇 context
    2. 提升 Tool Description 的質量（讓 embedding 更精確）
    3. 對「找不到適合工具」的場景設計 fallback——
       例如 LLM 說「我沒有能回答這個問題的工具」，而不是硬選一個錯的
```

**地雷 3：「External Memory 的 retrieve 要用什麼 embedding？和 RAG 的 embedding 一樣嗎？」**

```
答：不一定。
    RAG 的 embedding 是為了「文件語意相似度」優化的。
    Memory 的 embedding 有時候需要「情節相似度」——
    例如「上次處理類似訂單糾紛的步驟」，
    這需要對任務類型、工具使用模式做 embedding，
    而不只是文字語意。
    高品質的 Memory 系統通常需要專門為 episodic memory 設計的 embedding，
    或者加上結構化過濾（時間、任務類型）輔助搜尋。
```

---

## 八、面試回答完整示範

```
面試官問：「你的 Agent 用 ReAct 還是 Planner-Executor？
         工具有 20 個，怎麼處理？記憶怎麼設計？」

完整回答：

架構選擇：
「我會先問：任務的步驟是否可以預先規劃？
 如果是——例如定期報告生成——我選 Planner-Executor，
 因為步驟 1 和步驟 2 互相獨立，可以並行，
 總延遲從 T1+T2 降到 max(T1,T2)。
 如果任務需要探索、下一步取決於上一步結果，我選 ReAct。」

Tool Routing：
「20 個工具，我不會把所有 schema 都塞進 context。
 我設計一個四層漏斗：
 Rule-Based 過濾確定 pattern 的 → 
 Tool Retrieval 縮小到 Top-5 候選 →
 LLM 從 5 個裡選 1 個 →
 Input Validation 確保 tool call 參數安全。
 這樣 LLM 只需要看 5 個工具的 schema，選擇準確率高，
 而且 Rule-Based 這層對大量確定性的查詢幾乎零成本。」

Memory 設計：
「短期對話用 In-Context Memory 加 Summary Buffer——
 超過 20 輪的歷史壓縮成摘要，保留最近 5 輪完整記錄。
 跨 session 的用戶偏好和重要事件存 Vector Store，
 每輪 retrieve 和 query 最相關的過去記憶注入 context。
 什麼值得存長期記憶？
 只有『會影響未來行為』的資訊——偏好、重大決策——才值得存。
 天氣問題、日常查詢不需要長期記憶。」
```

---

**架構選擇的深度，決定了你在面試官眼中是「用過這些工具的人」**  
**還是「知道這些工具的邊界在哪裡的人」。**

下一篇：[**ML 基礎必備**](/posts/fde-interview-guide-part8-ml-fundamentals-zh/) — Transformer、Embedding 與評估指標的工程視角。
