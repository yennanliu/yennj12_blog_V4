---
title: "FDE 面試準備指南（二）：Agent System Design"
date: 2026-05-30T10:30:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，解析 FDE 面試中 Agent 系統設計考題，包含 ReAct 架構、Multi-Agent 判斷邏輯、失控防禦設計、MCP 協定與 Google ADK 定位"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "LangGraph", "CrewAI", "ADK", "MCP", "ReAct", "Interview", "Google"]
authors: ["yen"]
readTime: "14 min"
---

> RAG 是知識，Agent 是行動。  
> FDE 的工作常常是兩者都要。  
> Agent 面試的考點不是「你能不能架起來」，  
> 而是「你知不知道它什麼時候會出問題，以及出了問題你怎麼設計讓它不失控」。

---

## 面試情境

> **面試官：**「請設計一個 AI 客服系統，能夠查詢訂單狀態、回答 FAQ、在必要時轉接人工客服。然後告訴我：你的 Agent 如果陷入無限循環，你的架構怎麼防止它失控？」

---

## 一、Agent 的本質：LLM + Tools + Loop

用一句話說：

> **Agent = LLM + Tools + Loop**

LLM 負責決策，Tools 負責執行，Loop 讓它反覆思考直到完成任務。

最主流的 Loop 模式叫 **ReAct（Reasoning + Acting）**：

```
用戶：「我的訂單 #456 到了嗎？」
           │
           ▼
    Thought：「我需要查 CRM 確認訂單狀態」
           │
           ▼
    Action：call_tool("get_order", order_id="456")
           │
           ▼
    Observation：「訂單 #456 狀態：出貨中，預計明天到達」
           │
           ▼
    Thought：「我已經有答案了，可以回覆用戶」
           │
           ▼
    Action：final_answer("您的訂單 #456 目前正在出貨，預計明天到達")
```

**Reason → Act → Observe → 再 Reason**，這個循環一直跑到任務完成或觸發終止條件。

---

## 二、AI 客服 Agent 的完整系統架構

### 步驟一：釐清需求（先問，再設計）

```
你應該問的問題：

├── 日均 query 量是多少？（影響 scaling 設計）
├── 需要處理哪些語言？
├── 訂單查詢需要用戶身分驗證嗎？
├── 轉人工的觸發條件是什麼？（用戶主動要求？還是 AI 判斷不確定？）
└── 對話歷史需要跨 session 保留嗎？
```

### 步驟二：完整架構圖

```
┌──────────────────────────────────────────────────────────────┐
│                         用戶                                   │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼──────────────────────────────────┐
│              API Gateway（身份驗證 + Rate Limiting）           │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                   Orchestrator Agent                           │
│                                                               │
│   ① 接收用戶輸入                                              │
│   ② 維護對話狀態（Short-term Memory）                         │
│   ③ ReAct Loop：決定呼叫哪個 Tool                             │
│   ④ 整合 Tool 結果，生成最終回應                              │
│   ⑤ 判斷是否需要終止或轉接                                    │
└──────────┬──────────────────┬──────────────────┬─────────────┘
           │                  │                  │
┌──────────▼──────┐  ┌────────▼────────┐  ┌─────▼──────────────┐
│   CRM Tool       │  │  Knowledge Base  │  │  Escalation Tool   │
│                  │  │  Tool (RAG)      │  │                    │
│  查訂單狀態      │  │  查 FAQ /        │  │  轉接人工客服       │
│  查客戶資料      │  │  退款政策        │  │  建立工單           │
│                  │  │  產品說明        │  │                    │
│  ⚠ 只讀，不允    │  │                  │  │  需要人工確認的     │
│  許 Agent 修改   │  │                  │  │  高風險操作         │
└──────────────────┘  └─────────────────┘  └────────────────────┘
```

### 步驟三：意圖分類的位置與設計

```
意圖分類放在 Orchestrator 內部，有兩種設計方式：

方式 A：讓 LLM 自己選 Tool（Function Calling）
  優點：彈性高，能處理模糊意圖
  缺點：Tool 多時 prompt 變長，選擇準確率下降
  適合：Tool 數量 < 10，任務多樣

方式 B：前置分類器 + LLM 選 Tool
  訂單查詢 ──→ CRM Tool
  FAQ 問題 ──→ Knowledge Base Tool
  轉接請求 ──→ Escalation Tool
  其他     ──→ LLM 自行判斷

  優點：快速路徑成本低（分類器比 LLM 便宜很多）
  缺點：需要維護分類器
  適合：意圖類別固定、高流量、latency 敏感
```

---

## 三、Multi-Agent：什麼時候要拆開

這是面試官最愛問的判斷題。「任務複雜就用 Multi-Agent」這個答案不夠好。

### 正確的判斷框架

```
Single Agent 就夠的條件：
  ├── 任務流程是線性的，沒有並行需求
  ├── Tool 數量 ≤ 10
  ├── 一個 context window 裝得下整個任務
  └── 不需要獨立視角驗證輸出

Multi-Agent 的觸發條件（這四個才是關鍵）：
  ├── 需要並行執行（Research + Analysis + Writing 同時跑）
  ├── 需要專業分工（不同 Agent 有不同的 System Prompt 和 Tool 集）
  ├── 任務太長，單一 context window 裝不下所有 history
  └── 需要相互驗證（Generator + Critic 循環改進）
```

### 三種主流 Multi-Agent 模式

```
模式 A：Supervisor-Worker
（適合任務可分解、需要協調）

  Supervisor Agent（任務分解 + 結果整合）
       ├── Worker A：資料搜尋
       ├── Worker B：數據分析
       └── Worker C：報告撰寫

  注意：Supervisor 的 context 只看摘要，不看每個 Worker 的完整 trace

模式 B：Pipeline
（適合有明確順序依賴的任務）

  Agent 1（資料收集）─→ Agent 2（分析）─→ Agent 3（撰寫）
  每個 Agent 的輸出是下一個的輸入

模式 C：Peer Review
（適合需要反覆驗證、輸出品質要求高）

  Generator Agent ─→ Critic Agent ─→ Generator Agent（修訂）
       ↑_______________________________________|
  循環直到 Critic 滿意或達到最大迭代次數
```

### Multi-Agent 的代價（不能不說）

```
代價                    說明
────────────────────────────────────────────────────────────
Latency 增加            每個 Agent 間有通信 overhead，LLM 呼叫次數增加
Error Propagation       前一個 Agent 的錯誤會傳給下一個，放大影響
Debug 困難              不知道是哪個 Agent 出問題，需要完整 tracing
State 管理複雜          Agent 間共享狀態需要設計同步和衝突解決
成本增加                更多 LLM 呼叫 = 更高費用
```

**面試官最想聽的一句話：**  
「Multi-Agent 的複雜度必須由它帶來的具體收益（並行加速、專業分工、品質驗證）來 justify。如果這些收益不顯著，Single-Agent + 更好的 Tool 設計通常是更好的選擇。」

---

## 四、失控防禦：四道護欄

Agent 最大的生產風險是**無限循環**——決策錯誤 → 重試 → 還是錯 → 繼續重試 → 費用爆炸。

```
四道護欄的設計層次：

┌──────────────────────────────────────────────────────────┐
│  護欄 1：Hard Limits（硬性上限）← 最基本，必須有          │
│  最大迭代次數（Max Steps）= 20                            │
│  最大執行時間（Timeout）= 60 秒                           │
│  最大 Token 消耗 = 50,000                                 │
│  任何一個觸發 → 強制終止，回報「任務無法完成，請人工處理」 │
└──────────────────────────────────────────────────────────┘
          ↓（Hard Limits 沒觸發）
┌──────────────────────────────────────────────────────────┐
│  護欄 2：Progress Detection（進度偵測）                    │
│  每 N 步比較最近的 Observation 和前 N 步的 Observation     │
│  如果相似度 > 90% → Agent 停滯，強制觸發 Reflection 或終止 │
└──────────────────────────────────────────────────────────┘
          ↓（沒有偵測到停滯）
┌──────────────────────────────────────────────────────────┐
│  護欄 3：Cost Budget（費用預算）                           │
│  每次 LLM 呼叫前估算累積費用                              │
│  超過預算上限 → 暫停，通知用戶或觸發降級策略              │
└──────────────────────────────────────────────────────────┘
          ↓（費用在預算內）
┌──────────────────────────────────────────────────────────┐
│  護欄 4：Human-in-the-Loop（高風險操作人工確認）           │
│  高風險動作清單：退款、刪除資料、發送大量通知、修改定價    │
│  觸發時：暫停 Agent，等待人工審核（設定 5 分鐘 timeout）   │
│  超時未確認 → 取消操作，記錄日誌                          │
└──────────────────────────────────────────────────────────┘
```

**設計原則：** 從最便宜的護欄（Hard Limits）到最貴的（Human Review），依序觸發。

---

## 五、MCP：Model Context Protocol

這是 Anthropic 和 Google 都在推的標準化工具協定。

```
為什麼需要 MCP？

沒有 MCP 的世界：
  每個 Agent 框架（LangGraph / ADK / CrewAI）
  各自定義工具呼叫格式
  → 同一個 CRM 工具，換一個框架就要重寫 connector

有 MCP 的世界：
  CRM 只要實作一個 MCP Server
  任何支援 MCP 的框架都能直接用
  → 就像 HTTP 讓任何瀏覽器都能訪問任何網站

MCP 的架構：

  Agent（MCP Client）
       │ 標準 JSON-RPC 請求
       ▼
  MCP Server（CRM / ERP / 資料庫的 adapter）
       │ 標準回應格式
       ▼
  Agent 接收結果，繼續 ReAct loop
```

MCP 解決的核心問題是**工具的可移植性**。一旦有人寫好了 Salesforce 的 MCP Server，所有 Agent 框架都能用，不需要重複開發。

---

## 六、Google ADK 的定位

FDE 面試 Google 職位，ADK 可能被問到。

```
ADK vs LangGraph 的核心差異：

                LangGraph                   Google ADK
──────────────────────────────────────────────────────────────
抽象層次        低（細粒度控制）             高（開箱即用）
Gemini 整合     需要自己配置                 原生支援
Multi-Agent     需要自己設計通信              內建 AgentTeam
工具生態        LangChain Tools              Google Cloud Tools
適合場景        複雜自定義工作流              快速原型、GCP 生態系

GCP 整合：

ADK 天然整合 Google Cloud 服務：
  ├── Vertex AI Agent Builder（低代碼部署）
  ├── Cloud Run（Serverless 部署 Agent）
  ├── BigQuery（結構化資料查詢 Tool）
  ├── Google Search / Workspace（原生 Tool）
  └── Cloud Monitoring（Agent 追蹤）

面試中什麼時候提 ADK：
  客戶已在 GCP 生態、希望快速上線 → ADK
  需要複雜的自定義狀態管理和工作流 → LangGraph
```

---

## 七、面試官地雷題

**地雷 1：「Single-Agent 加更多 Tool 和 Multi-Agent 有什麼本質差異？」**

```
答：Single-Agent + 多 Tool 的 context 只有一個，
    所有的 Thought / Action / Observation 都在同一個 window 裡，
    工具之間沒有隔離，長任務很快就會 context overflow。

    Multi-Agent 讓每個 Agent 有自己的 context 邊界，
    Supervisor 只看 Worker 的結果摘要，不看完整 trace，
    所以可以處理 Single-Agent context window 裝不下的任務。

    但代價是：多了 Agent 間的通信 overhead 和 error propagation 風險。
```

**地雷 2：「你的 Agent 每次都呼叫 LLM 做決策，太慢怎麼辦？」**

```
答：兩個方向：
    1. 對確定性的路徑用 Rule-Based Router 繞過 LLM（例如「查訂單」就直接路由到 CRM Tool）
    2. 用 Planner-Executor：先讓 LLM 一次生成完整計畫（一次呼叫），
       再用輕量 Executor 逐步執行，不需要每步都呼叫完整的大模型。
```

**地雷 3：「MCP 和直接 Function Calling 有什麼差別？」**

```
答：Function Calling 是 LLM 廠商定義的呼叫格式（每家不同）。
    MCP 是跨框架的標準協定，讓工具只需要實作一次，就能被任何支援 MCP 的框架使用。
    本質差異：Function Calling 是 LLM 層的 interface，
              MCP 是工具層的 standard protocol。
```

**地雷 4：「Human-in-the-loop 怎麼設計才不會讓 Agent 卡住？」**

```
答：關鍵是設定 confirmation timeout：
    等待人工確認的動作設一個時間窗口（例如 5 分鐘）。
    超時有三個處理選項：
    1. 取消操作，把任務放回隊列（適合非緊急）
    2. 降級到更保守的動作（例如建 ticket 而不是直接退款）
    3. 通知用戶「需要人工協助」

    不能讓 Agent 無限等待——那比無限循環還糟。
```

---

## 八、面試回答完整示範

```
面試官期待聽到的回答：

釐清需求（1 分鐘）：
「在設計之前，我想先確認幾個需求。
 這個客服系統的日均查詢量大概是多少？
 訂單查詢需要驗證用戶身分嗎？
 轉人工的觸發條件是什麼——是用戶主動說『我要找人工』，
 還是 AI 判斷自己不確定時就要轉？」

架構（2 分鐘）：
「我的設計是單一 Orchestrator Agent，帶三個 Tool：
 CRM Tool（只讀，查訂單和客戶資料），
 Knowledge Base Tool（RAG，查 FAQ 和退款政策），
 Escalation Tool（轉接人工或建工單）。
 不用 Multi-Agent，因為這三個任務是順序的、不需要並行，
 單一 context window 夠裝，Multi-Agent 只會增加複雜度。」

失控防禦（2 分鐘）：
「防失控我設計四道護欄：
 第一道是 Hard Limits——最大 20 步、60 秒 timeout，
 任何一個觸發就強制終止並通知用戶。
 第二道是 Progress Detection——每 5 步比較最近的 Observation，
 相似度超過 90% 就視為停滯，強制進入 Reflection 模式。
 第三道是 Cost Budget——設定每個 session 的 token 上限。
 第四道是 Human-in-the-Loop——退款等高風險操作，
 Agent 不自己決定，暫停等人工確認，5 分鐘沒回應就取消。」
```

---

**Agent 系統設計考的不是你記了多少框架 API，**  
**而是你知道它什麼時候會出問題，以及你的架構如何讓問題可控。**

下一篇：[**ML 基礎知識**](/posts/fde-interview-guide-part3-ml-fundamentals-zh/) — FDE 面試中哪些 ML 基礎仍然必考。
