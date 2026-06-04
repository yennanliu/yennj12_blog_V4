---
title: "FDE 面試準備指南（三十一）：RKK 實戰——Google ADK 深度設計：Agent 類型、Tool 宣告與 Multi-Agent 協調"
date: 2026-06-05T09:00:00+08:00
draft: false
description: "以系統設計視角深度拆解 Google Agent Development Kit（ADK）：四種 Agent 類型的選擇邏輯、Tool 宣告系統的設計原理、Multi-Agent 的狀態共享機制，以及 ADK 在 Vertex AI 上的部署模式與 LangGraph 的根本差異"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "ADK", "Agent", "Google", "Vertex AI", "Multi-Agent", "Tool", "System Design", "RKK", "Interview"]
authors: ["yen"]
readTime: "18 min"
---

> ADK 不只是「Google 版的 LangGraph」。  
> 它是一個針對 Gemini + Google Cloud 生態系優化的 Agent 框架，  
> 在抽象層次、狀態管理、部署模式上都有自己的設計哲學。  
> 面試官考這題，是在測試你能不能幫客戶在 ADK 和 LangGraph 之間做出有依據的選擇。

---

## 面試情境

> **面試官：**「客戶是一家保險公司，已經在用 Google Workspace 和 GCP。他們想部署一個多步驟的理賠審核 Agent，需要並行查詢三個系統（核保資料庫、醫療記錄、詐欺偵測），然後由一個審核 Agent 整合結果做決策。你會用 ADK 還是 LangGraph？如果用 ADK，架構怎麼設計？」

---

## 一、ADK 在 Google AI 棧中的定位

```
Google AI Agent 工具棧（由低到高抽象）：

┌─────────────────────────────────────────────────────────────┐
│  Level 1：Gemini API + Function Calling（最底層）            │
│  你自己管理所有狀態、Tool 呼叫、循環邏輯                      │
│  適合：完全客製化，或需要接非 Gemini 模型                     │
└─────────────────────────────────────────────────────────────┘
                              ↓ 抽象提升
┌─────────────────────────────────────────────────────────────┐
│  Level 2：Google ADK（本篇主題）                              │
│  提供 Agent 類型、Tool 宣告、Multi-Agent 協調的標準框架       │
│  原生整合 Gemini、Vertex AI、Google Search                    │
│  適合：需要客製化邏輯，但不想從零搭框架                       │
└─────────────────────────────────────────────────────────────┘
                              ↓ 抽象提升
┌─────────────────────────────────────────────────────────────┐
│  Level 3：Vertex AI Agent Builder（最高層）                   │
│  低代碼/無代碼界面，拖拉設定 Agent 工作流                     │
│  適合：快速原型、業務人員自助、標準企業聊天機器人              │
└─────────────────────────────────────────────────────────────┘

FDE 的判斷原則：
  「如果 Agent Builder 能做到，就不用 ADK。
   如果 ADK 能做到，就不用從頭用 Gemini API 寫。」
```

---

## 二、ADK vs LangGraph：根本差異

```
比較維度          ADK                          LangGraph
──────────────────────────────────────────────────────────────────
模型綁定          Gemini 原生（可接其他）         任何 LLM
抽象層次          高（有 Agent 類型概念）          低（Node + Edge 圖）
狀態管理          Session State（框架管理）        StateGraph（你定義 schema）
Multi-Agent       AgentTeam + sub_agents          自己設計節點間通信
部署              Vertex AI Agent Engine 原生     需要自己包 Container
Google Cloud 整合 原生（GCS、BigQuery、Search）    需要額外配置
學習曲線          低（比 LangGraph 少 boilerplate）高（但控制粒度更細）
適合場景          GCP 生態、快速落地              複雜自定義工作流、多模型混用

關鍵判斷點：
  客戶在 GCP + 用 Google Workspace + 需要快速 POC → ADK
  客戶需要複雜的條件分支 + 不同步驟用不同 LLM → LangGraph
  客戶想混用 GPT-4o 和 Gemini → LangGraph（ADK 對非 Gemini 模型支援有限）
```

---

## 三、ADK 的四種 Agent 類型

ADK 的核心設計是「Agent 類型決定執行模式」，而不是讓你手動畫控制流程圖。

### LlmAgent（基礎推理 Agent）

```
最常用的 Agent 類型。

核心能力：
  ├── 接收用戶輸入
  ├── 用 Gemini 做推理決策
  ├── 呼叫宣告的 Tools
  └── 輸出最終答案

執行流程：
  Input → LLM（帶 Tools） → Tool Call or Final Answer
     ↑______Observation___|

適合場景：
  ├── 單一任務，需要動態決策哪個工具
  ├── ReAct 模式的直接實作
  └── 大多數的「單 Agent + 多 Tool」場景

設計範例（理賠問答 Agent）：

  LlmAgent(
    name = "claims_assistant",
    model = "gemini-2.0-flash",
    instruction = "你是保險理賠助理，根據用戶的問題查詢相關資料並給出準確的回答",
    tools = [query_policy_db, search_case_history, create_ticket]
  )
```

---

### SequentialAgent（順序執行）

```
讓多個 sub_agents 按固定順序執行，前一個的輸出傳給下一個。

執行流程：
  Input
    ↓
  Sub-Agent 1（資料收集）
    ↓ output 存入 Session State
  Sub-Agent 2（資料分析）
    ↓ output 存入 Session State
  Sub-Agent 3（報告生成）
    ↓
  Final Output

Pipeline 依賴性：
  ├── Agent 2 需要 Agent 1 的結果才能執行
  └── 任何一步失敗 → 後面的步驟都不執行

適合場景：
  ├── 有明確執行順序的多步驟工作流
  ├── 文件處理 Pipeline（擷取 → 分析 → 摘要）
  └── 資料轉換鏈（原始資料 → 清洗 → 分析 → 報告）
```

---

### ParallelAgent（並行執行）

```
讓多個 sub_agents 同時執行，等全部完成後再彙整結果。

執行流程：

  Input
    │
    ├──────────────┬──────────────┐
    ↓              ↓              ↓
  Sub-Agent A    Sub-Agent B    Sub-Agent C
  （查核保 DB）  （查醫療記錄）  （跑詐欺偵測）
    │              │              │
    └──────────────┴──────────────┘
                   ↓ 三者都完成後
            Aggregator Agent
            （整合結果，做決策）

延遲計算：
  順序：T_A + T_B + T_C（例如 200+300+250 = 750ms）
  並行：max(T_A, T_B, T_C)（例如 max(200,300,250) = 300ms）
  節省：60%

適合場景：
  ├── 多個獨立查詢（互相不依賴）
  ├── 同時調用多個外部系統
  └── Fan-out + Fan-in 的資料收集模式

⚠ 注意：sub_agents 必須真的互相獨立，
  如果 Agent B 需要 Agent A 的結果 → 用 SequentialAgent
```

---

### LoopAgent（條件循環）

```
讓一個 sub_agent 重複執行，直到滿足退出條件。

執行流程：

  Input
    ↓
  ┌──────────────────────────────────┐
  │  Sub-Agent 執行                   │
  │       ↓                          │
  │  檢查退出條件                      │
  │       ├── 未滿足 → 繼續循環        │
  │       └── 滿足 → 退出             │
  └──────────────────────────────────┘
    ↓
  Final Output

退出條件設計（關鍵）：
  ├── 明確的成功條件（例如：Draft 評分 ≥ 8 分）
  ├── 最大迭代次數（max_iterations，防止無限循環）
  └── Timeout（防止單次執行時間過長）

適合場景：
  ├── Generator-Evaluator 模式（生成 → 評估 → 修正）
  ├── Self-Reflection Loop
  └── 「重試直到成功」的任務

⚠ 沒有設定 max_iterations 的 LoopAgent 是危險的
```

---

## 四、Tool 宣告系統

ADK 的 Tool 宣告比 LangGraph 更標準化，有三種類型。

### 類型一：Python Function Tool（最常用）

```
設計原則：
  函數的 docstring 就是 Tool Description
  → LLM 用 docstring 判斷何時呼叫這個工具
  → 寫好 docstring 比寫好程式碼更重要

Tool Description 的品質差異：

  ❌ 差的：
  def get_data(id: str) -> dict:
      """Get data."""  ← LLM 不知道什麼時候用

  ✅ 好的：
  def query_insurance_policy(policy_id: str) -> dict:
      """查詢保險保單的詳細資訊，包含保障範圍、理賠限額、生效日期。
      當用戶詢問保單內容、保障項目或理賠資格時使用此工具。
      輸入：policy_id（保單號碼，格式：POL-XXXXXX）
      輸出：包含 coverage、limit、effective_date 的字典"""

Tool 的型別宣告：
  ADK 從 Python 型別標注（Type Hints）自動生成 JSON Schema
  → str、int、float、bool、list、dict 都支援
  → Optional[str] 表示非必填參數
  → Enum 可以限制允許的值

安全設計：
  ├── 只讀工具 vs 寫入工具 要明確分開
  ├── 寫入工具加上 require_confirmation=True（Human-in-the-loop）
  └── 工具的副作用要在 docstring 裡說清楚
```

### 類型二：Built-in Tool

```
ADK 內建的 Google 服務工具，直接宣告使用：

  google_search    → 即時網路搜尋
  code_execution   → Python 程式碼執行（沙盒環境）
  vertex_ai_search → 查詢 Vertex AI Search 索引（企業 RAG）

使用時機：
  google_search：Agent 需要查詢即時資訊（新聞、最新文件）
  code_execution：Agent 需要做計算或資料分析
  vertex_ai_search：Agent 需要查詢企業內部文件（你的 RAG）
```

### 類型三：Agent-as-Tool

```
把一個 Agent 包裝成 Tool，讓另一個 Agent 呼叫。

這是 ADK Multi-Agent 最重要的設計模式：

  Parent Agent（協調者）
       │
       ├── query_policy_agent（作為 Tool）
       │       └── 實際上是一個 LlmAgent
       │
       ├── fraud_detection_agent（作為 Tool）
       │       └── 實際上是一個 LlmAgent
       │
       └── make_decision()（普通 Python 函數 Tool）

效果：
  Parent Agent 的 LLM 看到的是「我可以呼叫 query_policy_agent 這個 Tool」
  它不知道（也不需要知道）這個 Tool 內部是另一個 Agent
  → 保持 Parent 的 context 乾淨
  → Sub-agent 有自己的 context 邊界
```

---

## 五、Multi-Agent 協調：Session State

ADK 的 Multi-Agent 用 **Session State** 做共享狀態，這是和 LangGraph 的關鍵差異之一。

```
LangGraph 的狀態模型：
  你定義 TypedDict，每個節點讀/寫這個 dict
  所有節點在同一個狀態空間裡

ADK 的狀態模型：
  Session State 是一個 key-value store
  所有 Agent 和 Tool 都可以讀寫
  框架管理持久化（支援 in-memory / Cloud Firestore / Cloud SQL）

Session State 的三個 scope：

  user:xxx    → 跨 session 持久化（用戶偏好、歷史）
  session:xxx → 在當前 session 內共享（本次任務的中間結果）
  temp:xxx    → 當前 Agent 執行週期內有效（暫時計算結果）

實際設計範例（理賠審核）：

  Step 1：ParallelAgent 執行三個查詢
    policy_agent → 寫入 session:policy_data
    medical_agent → 寫入 session:medical_data
    fraud_agent → 寫入 session:fraud_score

  Step 2：Aggregator Agent 讀取並決策
    讀 session:policy_data + session:medical_data + session:fraud_score
    → 輸出最終審核結論

  注意：不要把敏感資料（PII）存入 user: scope
  → user: scope 會跨 session 持久化，有資料洩漏風險
```

---

## 六、部署模式

### 選項 A：Vertex AI Agent Engine（推薦生產）

```
ADK Agent → Vertex AI Agent Engine

特點：
  ├── 全託管（不需要管 Container、Scaling、Load Balancing）
  ├── 原生整合 Vertex AI 的監控和日誌
  ├── Session State 自動持久化到 Firestore
  ├── 支援 Streaming（逐字回應）
  └── 內建 Rate Limiting 和 Auth

適合：標準企業 Agent 部署，想要最少的 Infra 維護

限制：
  └── 目前不支援所有 ADK 功能（某些 custom 設定需要 Cloud Run）
```

### 選項 B：Cloud Run（靈活）

```
ADK Agent → Container → Cloud Run

特點：
  ├── 完整控制（可以加入任何 custom middleware）
  ├── Serverless，自動 Scale-to-Zero
  ├── 部署靈活（任何能打包成 Container 的都能跑）
  └── 成本低（沒有流量時不計費）

適合：需要 custom auth、middleware、或 Agent Engine 不支援的功能

部署架構：

  ADK Agent Code
       ↓
  Docker Container（+ FastAPI wrapper）
       ↓
  Artifact Registry（存放 Image）
       ↓
  Cloud Run（Serverless 執行）
       ↓
  Cloud Load Balancing（可選，多 Region）
```

---

## 七、面試官地雷題

**地雷 1：「ADK 的 ParallelAgent 和自己用 asyncio.gather 並行呼叫 Tools 有什麼差別？」**

```
答：功能上類似，但 ADK ParallelAgent 做了更多事：
    1. 狀態隔離：每個 sub_agent 有自己的 context，不會互相污染
    2. 錯誤隔離：一個 sub_agent 失敗不影響其他（LangGraph 需要自己實作）
    3. 可觀測性：ADK 框架自動記錄每個 sub_agent 的執行 trace
    4. 重試策略：可以設定 per-agent 的 retry policy
    asyncio.gather 只是並行執行，沒有這些 Agent 層面的保護。
    對生產系統，ADK ParallelAgent 比 asyncio.gather 更可靠。
```

**地雷 2：「LoopAgent 和 LlmAgent 的 ReAct loop 有什麼差別？」**

```
答：本質不同。
    LlmAgent 的 ReAct loop 是 LLM 內部的推理循環（Thought→Action→Observation），
    由 LLM 自己決定何時結束（輸出 final_answer）。
    LoopAgent 是框架層面的外部循環——
    它讓整個 sub_agent（可以是 LlmAgent）重複執行，
    退出條件由外部邏輯（max_iterations、條件函數）控制，
    而不是由 LLM 決定。
    LoopAgent 適合「需要外部條件判斷是否繼續」的場景，
    例如 Generator-Evaluator 模式，評估通過才退出。
```

**地雷 3：「Session State 的 user: scope 和 session: scope 怎麼選？」**

```
答：關鍵問題是「這個資料需要跨 session 存活嗎？」
    user: scope → 跨 session 持久化，適合用戶偏好、長期設定
    session: scope → 只在當前 session 有效，適合任務的中間狀態
    
    安全原則：PII（姓名、身份證、帳號）不能存 user: scope，
    因為它會持久化，增加資料洩漏的攻擊面。
    中間計算結果用 temp: scope，任務結束就清除。
```

**地雷 4：「你什麼時候放棄 ADK，改用 LangGraph？」**

```
答：三個主要情況：
    1. 需要混用多個 LLM 廠商（部分任務用 Gemini，部分用 GPT-4o）
       → ADK 對非 Gemini 模型的支援有限
    2. 需要極其複雜的條件控制流程（例如：某個條件成立時要回退到前面的節點）
       → LangGraph 的 DAG 更適合複雜條件分支
    3. 客戶的部署環境不在 GCP
       → ADK 的 Vertex AI 整合是優勢，但也是強依賴
    如果三個都不是 → ADK 通常是更快、更少維護成本的選擇。
```

---

## 八、面試回答完整示範

```
面試官情境：保險公司需要並行查三個系統後做審核決策

架構選擇（30 秒）：
「我選 ADK。客戶在 GCP + Google Workspace，
 ADK 原生整合 Vertex AI，不需要額外配置，
 而且這個工作流的結構很清楚——並行查詢 + 彙整決策——
 ADK 的 ParallelAgent + LlmAgent 直接對應這個模式，
 比用 LangGraph 從零搭少很多 boilerplate。」

架構設計（2 分鐘）：
「最外層是一個 SequentialAgent，兩個步驟：
 步驟一：ParallelAgent，三個 sub_agents 同時執行：
   policy_agent 查核保資料庫，
   medical_agent 查醫療記錄，
   fraud_agent 跑詐欺偵測模型。
 三個結果都寫入 session: scope 的 State。
 步驟二：decision_agent（LlmAgent），
   讀取 session State 裡的三份資料，
   用 Gemini Pro 做最終審核決策。

 理賠金額超過閾值，decision_agent 有一個 Tool 是 require_human_approval，
 觸發 Human-in-the-Loop，等審核人員確認再執行。」

部署（30 秒）：
「部署到 Vertex AI Agent Engine——
 全託管、不需要管 Container，
 Session State 自動持久化到 Firestore，
 審計日誌直接進 Cloud Audit Logs。
 如果之後需要客製化 middleware（例如加入 PII 遮罩層），
 再遷移到 Cloud Run。」
```

---

**ADK 的設計哲學是：讓你聚焦在「這個 Agent 應該做什麼」，而不是「這個 Agent 的執行流程怎麼寫」。**  
**理解這個哲學，是說清楚 ADK vs LangGraph 選擇依據的關鍵。**
