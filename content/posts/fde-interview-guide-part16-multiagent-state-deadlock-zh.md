---
title: "FDE 面試準備指南（十六）：RKK 實戰——Multi-Agent 狀態管理與死鎖排除"
date: 2026-06-04T09:00:00+08:00
draft: false
weight: 16
description: "以系統設計視角拆解 Multi-Agent 的狀態管理與死鎖問題：為什麼階層式授權架構會產生死循環、State Reducer 的設計原理、分散式 Checkpoint 策略，以及如何在 LangGraph 中設計收斂的 Agent 圖"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Multi-Agent", "LangGraph", "State Management", "Deadlock", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "18 min"
---

> 面試官不只想聽你說「加 max_loops 限制」。  
> 他想聽的是：你知道為什麼會死鎖、死鎖發生在哪個環節、  
> 以及你的架構設計如何讓問題**根本不會發生**。

---

## 面試情境

> **面試官：** 「客戶使用 LangGraph 部署了一個階層式的 Multi-Agent 系統。Router Agent 分發任務給法務審查 Agent 和財務計算 Agent。上線後，特定的複雜查詢會導致系統 Timeout，或是多個 Agent 互相死循環呼叫。你在 Google Doc 看到對話日誌，如何定位問題？架構上如何設計 State Management 與護欄？」

---

## 一、核心問題：Multi-Agent 為什麼比 Single-Agent 更容易死鎖

```
Single-Agent（線性執行）：

User → Agent → Tool → Tool → Answer
          ↑
     狀態簡單，只有一個執行者，
     不存在競爭條件

Multi-Agent（網狀執行）：

              ┌─────────────────┐
              │   Router Agent   │
              └────────┬────────┘
               ↙               ↘
   ┌──────────────┐    ┌──────────────┐
   │  法務 Agent  │    │  財務 Agent  │
   └──────┬───────┘    └──────┬───────┘
          │                   │
          └──────┬────────────┘
                 ▼
         ┌──────────────┐
         │ Review Agent │  ← 可能再呼叫回 Router
         └──────────────┘
                 │
                 ▼ ???
```

**死鎖發生的三個根本原因：**

```
原因 1：循環依賴（Circular Dependency）
  Router → 法務 → Router → 法務 → ...
  沒有明確的終止條件

原因 2：全域狀態競爭（Race Condition）
  法務 Agent 和財務 Agent 同時寫入同一個 Global State
  後寫者覆蓋先寫者的結果 → 資料遺失 → 下一輪再重試 → 無限循環

原因 3：等待鏈（Wait Chain）
  法務 Agent 等財務 Agent 的結果
  財務 Agent 等法務 Agent 的批准
  → 互相等待，永遠不推進
```

---

## 二、系統架構：階層式 Multi-Agent 的完整設計

```
┌──────────────────────────────────────────────────────────────┐
│                    入口層（Entry Layer）                       │
│                                                              │
│   User Request → API Gateway → Task Queue (Cloud Pub/Sub)   │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                   協調層（Orchestration Layer）                │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │                  Router Agent                        │   │
│   │                                                      │   │
│   │   ┌───────────────┐      ┌───────────────────────┐   │   │
│   │   │ Intent        │      │  Task Dispatcher      │   │   │
│   │   │ Classifier    │  →   │  (DAG-based routing)  │   │   │
│   │   └───────────────┘      └───────────┬───────────┘   │   │
│   └────────────────────────────────────┬─┘               │   │
└───────────────────────────────────────┼──────────────────┘
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼              ▼
              ┌───────────────┐ ┌───────────────┐ ┌──────────┐
              │  法務 Agent   │ │  財務 Agent   │ │  其他    │
              │               │ │               │ │  Agents  │
              │  [只寫自己的  │ │  [只寫自己的  │ └──────────┘
              │   Substate]   │ │   Substate]   │
              └───────┬───────┘ └───────┬───────┘
                      └────────┬────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   狀態持久層（State Store）                    │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  Global State (Immutable + Append-only)              │   │
│   │  ┌───────────┐  ┌───────────┐  ┌───────────────────┐ │   │
│   │  │ messages  │  │ legal_    │  │ finance_          │ │   │
│   │  │ (append)  │  │ output    │  │ output            │ │   │
│   │  └───────────┘  └───────────┘  └───────────────────┘ │   │
│   └──────────────────────────────────────────────────────┘   │
│   Cloud Memorystore (Redis) / Firestore                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、死鎖診斷：如何從日誌中找到問題

面試官給你這段日誌，你怎麼看：

```
[14:23:01] Router  → 分派任務到法務 Agent (iteration=1)
[14:23:03] 法務    → 需要財務確認金額，呼叫 財務 Agent
[14:23:05] 財務    → 金額有法律風險，需要法務確認，呼叫 法務 Agent
[14:23:07] 法務    → 需要財務確認金額，呼叫 財務 Agent  ← 重複了！
[14:23:09] 財務    → 金額有法律風險，需要法務確認，呼叫 法務 Agent  ← 重複了！
[14:23:11] Router  → 分派任務到法務 Agent (iteration=2)  ← Router 也在循環
...
[14:24:31] TIMEOUT after 90 seconds
```

**診斷步驟：**

```
Step 1：計算迭代次數
  同一個 Agent 被呼叫幾次？次數一直增加 → 確認是無限迴圈

Step 2：追蹤呼叫鏈
  法務 → 財務 → 法務 → 財務
  ↑ 這是雙向等待：典型的「循環依賴」死鎖

Step 3：檢查 State
  Global State 有沒有推進？
  如果 state["legal_status"] 一直是 "pending" → State 沒有更新
  原因可能是：Agent 呼叫彼此但都沒有寫入確定的輸出

Step 4：定位根本原因
  ├── 缺乏「我已完成」的退出信號
  ├── 兩個 Agent 的任務邊界沒有清晰定義
  └── 沒有 max_iteration 護欄
```

---

## 四、解決策略：四個層面的設計

### 策略一：明確的 Agent 邊界（最根本的解法）

```
問題根源：法務 Agent 和財務 Agent 的職責邊界模糊
→ 法務 Agent 覺得自己需要財務確認才能完成
→ 財務 Agent 覺得自己需要法務確認才能完成
→ 誰都不敢先給出確定答案

正確設計：每個 Agent 必須能獨立完成自己的子任務

  法務 Agent 的職責定義：
  ├── 輸入：合約文本
  ├── 任務：分析法律風險，輸出風險評級（高/中/低）
  └── 輸出：{ legal_risk: "HIGH", reasons: [...] }
           ↑ 這是確定性的輸出，不依賴財務 Agent

  財務 Agent 的職責定義：
  ├── 輸入：財務條款 + 法務 Agent 的風險評級（可選）
  ├── 任務：計算財務影響
  └── 輸出：{ financial_impact: 5000000, currency: "TWD" }

  Router Agent 的職責：
  └── 收集兩者的輸出 → 綜合判斷 → 最終決策
```

### 策略二：State Reducer（防止 Race Condition）

```
❌ 錯誤設計：多個 Agent 覆寫同一個 Global State

  Agent A 寫入：state["result"] = "批准"
  Agent B 寫入：state["result"] = "拒絕"   ← 覆蓋了 A 的結果！
  系統看到 "拒絕" → 重新執行 A → 無限循環

✅ 正確設計：Append-only Reducer，每個 Agent 只寫自己的 substate

  Global State 結構：
  {
    "messages": [...],          ← 只能 append，不能覆寫
    "legal_output": null,       ← 只有法務 Agent 能寫這個
    "finance_output": null,     ← 只有財務 Agent 能寫這個
    "iteration_count": 0,       ← 全域計數器
    "final_decision": null      ← 只有 Router 能寫這個
  }

  Reducer 規則：
  ├── messages：新訊息只能 append 到末尾
  ├── legal_output：一旦寫入就 immutable，不允許覆蓋
  └── iteration_count：每次 Agent 執行自動 +1
```

### 策略三：最大迭代護欄（收斂保證）

```
Graph 的 Conditional Edge 邏輯：

  任何邊（Edge）在路由前，先檢查：

  ┌─────────────────────────────────────┐
  │  if state["iteration_count"] >= 5:  │
  │      → 強制跳轉到 Fallback Node     │
  │                                     │
  │  elif state["legal_output"] and     │
  │       state["finance_output"]:      │
  │      → 跳轉到 Router（綜合決策）    │
  │                                     │
  │  else:                              │
  │      → 繼續執行下一個 Agent         │
  └─────────────────────────────────────┘

  Fallback Node 的動作：
  ├── 回傳：「系統無法自動完成此任務，已轉交人工審核」
  ├── 觸發 Cloud Logging Alert（嚴重警告）
  └── 將當前 State 快照存入 Firestore 供人工檢視
```

### 策略四：分散式 Checkpoint（故障恢復）

```
執行流程與 Checkpoint 點：

User Request
    │
    ▼
[Checkpoint 0] ← 任務開始，寫入 Firestore
    │
    ▼
Router 分派任務
    │
    ├── 法務 Agent 執行
    │       │
    │       ▼
    │   [Checkpoint 1] ← legal_output 寫入 Redis
    │
    └── 財務 Agent 執行
            │
            ▼
        [Checkpoint 2] ← finance_output 寫入 Redis
    │
    ▼
Router 綜合決策
    │
    ▼
[Checkpoint 3] ← 最終決策存入 Firestore

故障恢復邏輯：
  Worker 崩潰 → 排程器偵測到心跳停止
             → 讀取最後一個 Checkpoint
             → 從 Checkpoint N 重新開始（不是從頭）
             → 避免重複消耗 Token 成本
```

---

## 五、技術選型：各狀態存儲方案的 Trade-off

```
狀態存儲選型比較：

                   Redis (Memorystore)      Firestore
─────────────────────────────────────────────────────
讀寫延遲           < 1ms                    10~50ms
資料持久性         依配置（可選持久化）        強持久化
查詢能力           Key-Value / 簡單 TTL      富查詢（索引）
成本               較高（記憶體）             較低（磁碟）
適合存什麼         短期 Session State        長期 Checkpoint
                   Hot Checkpoint           完整任務歷史
                   Lock / Semaphore         用戶資料

推薦組合：
  Redis  → 正在執行中的 Agent State（Hot Path）
  Firestore → 已完成任務的歷史 + 可查詢的任務記錄
```

---

## 六、架構演進：從 LangGraph 的角度

```
LangGraph Graph 結構設計：

節點（Nodes）：
  ┌─────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────┐
  │ Router  │  │ LegalAgent │  │FinanceAgent │  │ Fallback │
  └─────────┘  └────────────┘  └─────────────┘  └──────────┘

邊（Edges）與條件路由：

  START → Router
  Router → LegalAgent   (if "legal_required" in task)
  Router → FinanceAgent (if "finance_required" in task)
  LegalAgent  → Router  (if legal_output is set)
  FinanceAgent → Router (if finance_output is set)
  Router → END          (if both outputs are set)

  所有邊都有護欄：
  任何邊 → if iteration_count >= 5: → Fallback → END

關鍵設計原則：
  ✓ 圖必須是有向無環圖（DAG）或有明確收斂條件的有環圖
  ✓ 所有 Cycle 都必須有計數器護欄
  ✓ 每個 Node 的輸出必須是確定性的（寫入 substate 後不再改變）
```

---

## 七、面試答題要點

> *「問題有兩個層面。第一層是架構設計問題：法務 Agent 和財務 Agent 的職責邊界沒有明確定義，導致兩者互相等待，形成循環依賴。根本解法是讓每個 Agent 能獨立輸出確定性結果，由 Router 負責綜合判斷，而不是讓子 Agent 互相協調。*
>
> *第二層是 State Management 問題：多個 Agent 同時寫入 Global State 會有 Race Condition。解法是用 Append-only Reducer，每個 Agent 只能寫入自己的 substate，確保互相隔離。*
>
> *護欄設計：在每條 Conditional Edge 上加 iteration_count >= 5 的硬性跳出，超過就轉 Fallback，觸發 Alert，等待人工處理。*
>
> *狀態持久化：用 Redis 存 Hot Path 的 Checkpoint，用 Firestore 存完整任務歷史，確保 Worker 崩潰後能從斷點續傳。」*

---

**系列導覽：**  
← [（十五）RKK 實戰：Agent 規模化與 Cache 策略](../fde-interview-guide-part15-scale-cache-zh/)  
→ [（十七）RKK 實戰：MCP 與 Tool-Calling 安全隔離](../fde-interview-guide-part17-mcp-tool-oauth-zh/)
