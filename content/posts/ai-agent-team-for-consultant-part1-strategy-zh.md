---
title: "用 AI Bot 打造顧問團隊（一）：策略與技術路線選擇"
date: 2026-04-30T09:00:00+08:00
draft: false
description: "想用純 AI Bot 建立一支 AI 顧問團隊？本文從商業角度出發，分析三條技術路線（Claude Code + agent.md、Gemini CLI、LangGraph + LLM），比較優缺點與適用場景，幫助你在動手之前先想清楚架構。"
categories: ["AI", "Agent", "Business", "all"]
tags: ["AI Agent", "Claude Code", "Gemini CLI", "LangGraph", "AI Consultant", "Multi-Agent", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "15 min"
---

## 前言

想像你是一家小型 AI 顧問公司的創辦人。客戶問你：「我們公司要怎麼導入 AI？」  
你不可能 24 小時隨時接電話，但 **AI Bot 可以**。

這個系列文章將帶你從零開始，用純 Bot 建立一支能夠：
- 接受客戶需求、提問、釐清問題
- 產出顧問報告草稿
- 自動分派任務給不同專業角色
- 追蹤執行狀況並彙整成果

的 **AI 顧問團隊**。

本篇（第一篇）專注在**策略層面**：應該選哪條技術路線？各自的優缺點和適用場景是什麼？

---

## 商業背景：我們要解決什麼問題？

根據 [ai_consultant](https://github.com/BrotherSupport/ai_consultant) 這個商業計劃的核心理念，AI 顧問的工作可以拆成幾個主要環節：

```
客戶需求輸入 → 問題釐清與診斷 → 方案設計 → 報告產出 → 執行追蹤
```

傳統顧問公司靠**人**來完成每個環節。我們的目標是：

> 用一組協作的 AI Agent 取代或增強每個環節，讓少數人力就能服務更多客戶。

這不是「一個超級 AI 什麼都做」，而是**多個專責 Agent 分工合作**的概念。

---

## 三條技術路線

### 路線 A：Claude Code + Skills / AGENTS.md

**核心概念：** 利用 Claude Code CLI 的原生 multi-agent 機制，透過 `AGENTS.md`（或 `CLAUDE.md`）定義每個 Agent 的角色、工具權限與行為邊界，搭配 **Skills**（可重複呼叫的 slash command 腳本）讓 Agent 之間能互相協作。

```
專案目錄結構
├── AGENTS.md          ← 定義整個團隊的角色分工
├── .claude/
│   └── settings.json  ← 工具權限、hook 設定
├── skills/
│   ├── intake.md      ← 客戶需求收集 Agent
│   ├── diagnose.md    ← 問題診斷 Agent
│   └── report.md      ← 報告產出 Agent
└── workspace/         ← Agent 的工作區
```

**優點：**
- 設定簡單，幾乎零程式碼
- Claude Code 原生支援 sub-agent 與 task delegation
- 可透過 hooks 自動化觸發（例如客戶提交表單後自動啟動流程）
- 適合快速 MVP，一天內可建立雛形

**缺點：**
- 強依賴 Claude Code 平台，廠商鎖定風險
- 複雜流程（條件分支、迴圈、錯誤重試）需要額外設計
- 多 Agent 之間的狀態同步靠檔案或對話上下文，不夠可靠

**適用場景：**
- 單一顧問或小型團隊的快速原型
- 需求相對線性（A → B → C）的顧問流程
- 已經在用 Claude Code 做日常工作的團隊

---

### 路線 B：Gemini CLI + Google Ecosystem

**核心概念：** 使用 Google 的 Gemini CLI 搭配 Google Workspace（Docs、Sheets、Drive、Calendar），讓 Agent 能直接讀寫客戶的 Google 文件、自動排程會議、建立試算表報表。

```
Gemini CLI
    ↓
Google Drive (客戶文件)
Google Docs  (報告產出)
Google Sheets (追蹤進度)
Gmail        (客戶溝通)
```

**優點：**
- 與 Google Workspace 原生整合，客戶易於接受
- Gemini 1.5/2.0 有超長 context window（100 萬 tokens），適合處理大型文件
- Google 生態圈工具成熟，權限控管清楚
- 適合以文件為核心的顧問工作流

**缺點：**
- Gemini CLI 成熟度不如 Claude Code（截至 2026 年 Q1）
- 需要管理 Google Cloud 權限，設定成本較高
- 程式碼撰寫能力相對 Claude 弱一些

**適用場景：**
- 客戶主要使用 Google Workspace
- 需要大量文件分析（財務報表、合約審閱）
- 顧問公司本身也在 Google 生態圈內

---

### 路線 C：LangGraph + LLM（程式碼驅動）

**核心概念：** 用 [LangGraph](https://github.com/langchain-ai/langgraph) 建立有向圖（DAG）狀態機，明確定義每個 Agent 節點、轉換條件、錯誤處理與狀態持久化，底層 LLM 可以是 Claude、GPT-4o、Gemini 或本地模型。

```python
# 簡化示意
from langgraph.graph import StateGraph

graph = StateGraph(ConsultantState)
graph.add_node("intake", intake_agent)
graph.add_node("diagnose", diagnose_agent)
graph.add_node("report", report_agent)
graph.add_edge("intake", "diagnose")
graph.add_conditional_edges("diagnose", route_by_complexity)
graph.add_edge("report", END)
```

**優點：**
- 最高的靈活性與可控性
- 支援複雜流程：條件分支、迴圈、人機協作（human-in-the-loop）
- 狀態持久化（可用 PostgreSQL/Redis），適合長時間運行的任務
- 模型無關，可以混用不同 LLM
- 有完整的可觀測性工具（LangSmith）

**缺點：**
- 開發成本最高，需要 Python 工程師
- 需要自己維護基礎設施（資料庫、Queue、部署）
- Debug 複雜，Agent 行為需要大量測試

**適用場景：**
- 有工程資源的中大型顧問公司
- 需要與現有系統（CRM、ERP）整合
- 要求高可靠性、可審計、可回溯的企業級流程

---

## 技術路線比較總覽

| 面向 | Claude Code + Skills | Gemini CLI | LangGraph + LLM |
|------|---------------------|------------|-----------------|
| 上手難度 | ★☆☆ 低 | ★★☆ 中 | ★★★ 高 |
| 開發速度 | 最快（天） | 中（週） | 最慢（週～月） |
| 靈活性 | 低～中 | 中 | 高 |
| 可靠性 | 中 | 中 | 高 |
| 廠商鎖定 | 高（Anthropic） | 高（Google） | 低 |
| 維護成本 | 低 | 中 | 高 |
| 適合團隊規模 | 1～5 人 | 3～10 人 | 5 人以上（含工程師） |

---

## 如何選擇？決策框架

```
你有 Python 工程師嗎？
├── 沒有 → 你主要用 Google Workspace 嗎？
│           ├── 是 → 路線 B（Gemini CLI）
│           └── 否 → 路線 A（Claude Code + Skills）
└── 有 → 你需要與外部系統整合或高可靠性嗎？
          ├── 是 → 路線 C（LangGraph）
          └── 否 → 先用路線 A 驗證，再遷移到路線 C
```

**推薦的漸進策略：**

1. **第 1 週：** 用路線 A（Claude Code）快速建立 MVP，驗證客戶接受度
2. **第 1 個月：** 根據實際使用痛點，決定是否要升級到路線 C
3. **長期：** 路線 C 作為核心引擎，路線 A/B 作為前端介面

---

## AI 顧問團隊的角色分工設計

不管選哪條技術路線，「角色分工」的設計是關鍵。以下是建議的 Agent 角色架構：

```
┌─────────────────────────────────────────────┐
│              AI 顧問團隊                      │
│                                             │
│  ① Intake Agent（需求收集師）                 │
│     → 接待客戶、提問、釐清需求                 │
│                                             │
│  ② Analyst Agent（問題分析師）                │
│     → 診斷問題根源、評估複雜度                 │
│                                             │
│  ③ Strategist Agent（策略顧問）               │
│     → 設計解決方案、評估 ROI                  │
│                                             │
│  ④ Writer Agent（報告撰寫師）                 │
│     → 產出結構化顧問報告                      │
│                                             │
│  ⑤ Coordinator Agent（協調員）               │
│     → 分派任務、追蹤進度、彙整成果              │
└─────────────────────────────────────────────┘
```

每個 Agent 都有：
- **明確的職責範圍**（做什麼、不做什麼）
- **專屬的 System Prompt**（定義角色人設與行為準則）
- **工具清單**（能呼叫哪些外部工具）
- **輸出格式規範**（讓下游 Agent 能正確解析）

---

## 小結

| 如果你是... | 建議路線 |
|------------|---------|
| 一人顧問，想快速驗證想法 | 路線 A（Claude Code + Skills）|
| 顧問公司，客戶都在 Google 生態 | 路線 B（Gemini CLI）|
| 有技術團隊，要做產品化 | 路線 C（LangGraph + LLM）|

第二篇文章將進入**實作**：每條路線的具體設定步驟、範例程式碼與 System Prompt 設計。

---

*本系列文章：*
- **第一篇（本篇）：** 策略與技術路線選擇
- [第二篇：各路線實作步驟與範例程式碼](/posts/ai-agent-team-for-consultant-part2-implementation-zh/)
- [第三篇：評估、維運與優化計畫](/posts/ai-agent-team-for-consultant-part3-devops-zh/)
