---
title: "FDE 面試準備指南（三十七）：RKK 實戰——企業 AI 的「連接組織」：Legacy 系統整合、API 橋接與安全邊界設計"
date: 2026-06-05T15:00:00+08:00
draft: false
description: "以系統設計視角拆解 FDE 最常遇到的現場問題：如何把 ADK Agent 接上 SAP、Oracle DB、Mainframe CSV 等 Legacy 資料孤島；API 橋接層的選型邏輯；安全邊界連接工程（Private Service Connect、VPC-SC、CMEK）；以及每種整合模式對系統效能、穩定性、成本和風險的影響"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Integration", "Legacy", "API", "GCP", "VPC", "Security", "Enterprise", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "19 min"
---

> Demo 時 Agent 很漂亮。  
> 到客戶現場才發現：資料在 SAP（文件很爛）、Oracle（只有 DB 直連）、  
> 還有一個每天凌晨 2 點才匯出的 CSV 檔案。  
> 「連接組織」，是 FDE 和 AI 工程師最核心的差距之一。

---

## 面試情境

> **面試官：**「客戶是一家有 30 年歷史的製造業。資料在三個地方：SAP ERP（有 REST API 但文件很爛）、Oracle 資料庫（只有 DB 直連）、一個每天從 mainframe 匯出的 CSV。他們希望 AI 能回答：庫存狀況、哪個供應商交期有問題。你怎麼設計這個整合層？」

---

## 一、問題本質：Legacy 整合的三種挑戰

```
Demo 的 Tool：

  def get_inventory(item_id: str) -> dict:
      return requests.get(f"https://api.example.com/inventory/{item_id}")

客戶現場的現實：

  SAP API：
  ├── 認證：OAuth + Client Certificate（文件在某個 Confluence 頁面，過期了）
  ├── Rate Limit：10 req/sec per user（AI 可能觸發 100 并發）
  ├── 回傳格式：200 欄位的 XML（Agent 只需要 5 個）
  └── 錯誤碼：自定義的 SAP 錯誤碼（不是標準 HTTP）

  Oracle DB：
  ├── 沒有 API，只能 JDBC/ODBC 直連
  ├── 沒有任何文件，Schema 要靠 DBA 解釋
  └── 有 SQL Injection 和 full table scan 的風險

  Mainframe CSV：
  ├── 每天凌晨 2 點才有新資料（不是即時）
  ├── 格式偶爾會改變（沒有版本控制）
  └── 直接讀大 CSV 到 context = token 爆炸

這三個資料來源，需要三種不同的整合模式。
```

---

## 二、整合模式選型框架

```
選型決策矩陣：

  資料來源特性          → 建議整合模式
  ──────────────────────────────────────────────────────────────
  有 API，但設計複雜      → API 橋接層
  （認證複雜、格式冗餘、Rate Limit）
  ──────────────────────────────────────────────────────────────
  只有 DB 直連，沒有 API  → 資料庫查詢層（Stored Procedure）
  ──────────────────────────────────────────────────────────────
  批次檔案（CSV、Excel）  → 批次攝取 Pipeline（GCS → BigQuery）
  ──────────────────────────────────────────────────────────────
  即時串流資料            → Pub/Sub → BigQuery → Agent Query
  ──────────────────────────────────────────────────────────────

三種模式的系統特性對比：

  模式              延遲      資料新鮮度    設計複雜度    適用場景
  ──────────────────────────────────────────────────────────────
  API 橋接層        低（ms）   即時          高            SAP 庫存查詢
  ──────────────────────────────────────────────────────────────
  DB 查詢層         中（ms）   即時          中            Oracle 訂單狀態
  ──────────────────────────────────────────────────────────────
  批次攝取 Pipeline  秒-分      T+1（次日）   低            Mainframe 月報
  ──────────────────────────────────────────────────────────────

製造業客戶的對應：
  SAP → API 橋接層
  Oracle → DB 查詢層
  Mainframe CSV → 批次攝取 Pipeline
```

---

## 三、模式一：API 橋接層設計

```
設計目標：隱藏 SAP API 的所有複雜性，
          讓 Agent Tool 看到的是簡單、穩定的介面。

架構：

  ┌──────────────────────────────────────────────────────────────┐
  │  ADK Agent                                                    │
  │  def get_inventory(item_id, warehouse) → dict                │
  │  （Agent 只看到這個簡單函數）                                  │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  SAP Adapter Service（你寫的橋接層）                           │
  │                                                              │
  │  ├── 認證管理                                                 │
  │  │   Secret Manager 取 OAuth token + Client Certificate      │
  │  │   Token 自動更新（expiry 前 5 分鐘刷新）                   │
  │  │                                                           │
  │  ├── Rate Limiting（Token Bucket，10 req/sec）                │
  │  │   超過上限的請求排隊等待，設定 queue timeout = 5s           │
  │  │                                                           │
  │  ├── 格式轉換                                                 │
  │  │   200 欄位 XML → 5 欄位 JSON                              │
  │  │   {available_qty, unit, location, last_updated, status}   │
  │  │                                                           │
  │  ├── Response Cache（Redis，TTL 5 分鐘）                      │
  │  │   相同 item_id+warehouse 的查詢，5 分鐘內走 Cache          │
  │  │                                                           │
  │  └── 錯誤處理                                                 │
  │      HTTP 429 / SAP-specific 錯誤碼 → 統一轉換成 Retry 或     │
  │      結構化錯誤訊息（Agent 能理解的格式）                       │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  SAP REST API（原始系統）                                      │
  │  認證複雜、格式冗餘、Rate Limit 10 req/sec                     │
  └──────────────────────────────────────────────────────────────┘

Cache 的效益：
  假設有 80% 的查詢是重複的相同 item_id：
  SAP API 實際呼叫量降低 80%，Rate Limit 問題基本消失。
  對 SAP 系統的壓力大幅降低，減少影響生產系統的風險。
```

---

## 四、模式二：資料庫查詢層（Stored Procedure）

```
核心安全問題：Agent 不能直接生成 SQL 並執行。

  風險分析：
  ❌ 直接讓 Agent 生成 SQL：
     Agent: SELECT * FROM orders WHERE supplier = '{user_input}'
     攻擊者輸入：' OR 1=1; DROP TABLE orders; --
     → SQL Injection，資料庫損毀

  ❌ 直接 SELECT *：
     對大型 Oracle 表的 full table scan
     可能讓生產資料庫效能崩潰

  ✅ 正確設計：Stored Procedure 層

架構：

  ADK Agent Tool
  def get_supplier_delivery(supplier_id, date_from, date_to)
         │
         │ 呼叫預定義的 Stored Procedure
         ▼
  Oracle DB
  EXEC sp_GetSupplierDelivery(?, ?, ?)
  └── 由 DBA 審核的查詢邏輯
  └── 只開放 SELECT，有索引，不會 full scan
  └── 參數化，防止 SQL Injection

  Agent 只能呼叫這些預定義的 Stored Procedures，
  不能執行任意 SQL。

DB 帳號權限設計：
  ┌──────────────────────────────────────────────────────────┐
  │  AI_SERVICE_ACCOUNT（AI 系統使用的 DB 帳號）              │
  │                                                          │
  │  ✅ 允許：EXECUTE sp_GetInventory                         │
  │           EXECUTE sp_GetSupplierDelivery                 │
  │           EXECUTE sp_GetProductionStatus                 │
  │                                                          │
  │  ❌ 拒絕：SELECT / UPDATE / DELETE / DROP 任意表          │
  │           CREATE / ALTER 任何物件                         │
  └──────────────────────────────────────────────────────────┘

  最小權限原則：AI 系統帳號只有呼叫特定 SP 的權限。
```

---

## 五、模式三：批次攝取 Pipeline

```
核心問題：為什麼不直接讓 Agent 讀 CSV？

  直接讀 CSV 的問題：
  ├── 大檔案（100 萬行）直接讀進 context → Token 爆炸（成本 × 1000）
  ├── CSV 格式改變 → Agent 解析錯誤，靜默失敗
  └── 沒有 Schema 驗證 → 髒資料直接進 AI

批次攝取架構：

  Mainframe 匯出 CSV（凌晨 2:00）
         │
         ▼
  Cloud Storage（GCS）
  gs://customer-data/mainframe/YYYYMMDD/inventory.csv
         │
         ▼
  Cloud Function（觸發於新檔案上傳）
  ├── Schema 驗證
  │   ├── 欄位數量是否正確？（今天 52 欄，昨天也是 52 欄？）
  │   ├── 關鍵欄位的型別是否正確？（庫存數量是 integer？）
  │   └── 異常值偵測（庫存為負值？數量是 0 但有訂單？）
  │
  └── 如果 Schema 變了 → Alert 工程師，暫停 Pipeline
         │
         ▼
  BigQuery（inventory_daily 表）
         │
         ▼
  Agent Tool（查 BigQuery SQL，不讀原始 CSV）

  def get_production_summary(date: str) -> dict:
      """查詢指定日期的生產摘要。注意：資料每日凌晨更新，非即時。"""
      query = """
          SELECT product_line, total_units, defect_rate, completion_rate
          FROM `project.manufacturing.inventory_daily`
          WHERE report_date = @date
      """
      # Parameterized query，防止 SQL Injection
      job_config = bigquery.QueryJobConfig(
          query_parameters=[bigquery.ScalarQueryParameter("date", "DATE", date)]
      )
      return bq_client.query(query, job_config=job_config)

重要設計：
  Tool docstring 明確說明「每日凌晨更新，非即時」
  → LLM 在回答時會告知用戶：「此資料截至昨日」
  → 管理用戶對即時性的預期，避免用戶誤以為是即時庫存
```

---

## 六、安全邊界的連接工程

```
問題：Agent 在 GCP 上，客戶的 Oracle 在內部。
      如何讓資料不走公共網路？

Private Service Connect 架構：

  ┌──────────────────────────────────────────────────────────────┐
  │  GCP（Cloud Run / ADK Agent）                                 │
  │                                                              │
  │  Cloud Run → VPC Connector                                   │
  │  （所有 Outbound traffic 走 VPC，不走 Public Internet）        │
  └──────────────────────────┬───────────────────────────────────┘
                             │ 私有網路（不走 Public Internet）
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Private Service Connect Endpoint                            │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Cloud VPN / Cloud Interconnect                              │
  │  （GCP VPC ↔ 客戶內部網路的加密隧道）                          │
  └──────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  客戶內部網路                                                  │
  │  ├── Oracle DB（允許 AI_SERVICE_ACCOUNT 連接）                │
  │  └── SAP Application Server                                  │
  └──────────────────────────────────────────────────────────────┘

VPC-SC vs IAM vs CMEK：選哪個，為什麼

  控制目標              用 IAM              用 VPC-SC            用 CMEK
  ──────────────────────────────────────────────────────────────────
  「誰」能存取資料       ✅ 主要工具          輔助（限制 Network）   ❌ 無關
  ──────────────────────────────────────────────────────────────────
  資料「在哪」能被存取   ❌ 無法控制          ✅ 限制在 VPC 邊界內   ❌ 無關
  ──────────────────────────────────────────────────────────────────
  防止資料被「搬出去」   ❌ 無法防止           ✅ 即使代碼被 Exploit  ❌ 無關
                                             也無法傳出 Perimeter
  ──────────────────────────────────────────────────────────────────
  加密金鑰控制          ❌ 無關              ❌ 無關               ✅ 客戶掌控金鑰
  ──────────────────────────────────────────────────────────────────
  適合場景              所有 GCP 資源存取     Prompt Injection 防護  金融/政府合規
  ──────────────────────────────────────────────────────────────────

  三者是互補的，不是互斥的。
  一般企業：IAM + Private Service Connect（必要）
  高合規要求（金融/醫療）：加上 VPC-SC
  政府/金融的金鑰主權要求：加上 CMEK
```

---

## 七、系統效應：整合設計的影響

```
維度          有橋接層設計                    直接讓 Agent 呼叫原始 API
──────────────────────────────────────────────────────────────────
穩定性        SAP 認證更新不影響 Agent 代碼    SAP API 格式一改，Agent 壞掉
──────────────────────────────────────────────────────────────────
效能          Cache Hit Rate 70-80%，         每次都直接打 SAP，
              實際 SAP 呼叫量降低 80%          Rate Limit 頻繁觸發
──────────────────────────────────────────────────────────────────
安全性        Credentials 在橋接層，          Credentials 在 Agent 代碼，
              Agent 不知道 SAP 密碼            洩漏風險高
──────────────────────────────────────────────────────────────────
可維護性      SAP API 版本升級，只改橋接層     需要改所有 Agent Tool 代碼
──────────────────────────────────────────────────────────────────
開發速度      建立橋接層 2-3 天，              初期快，
              後續維護低                      但 SAP 每次改版都要修
──────────────────────────────────────────────────────────────────
資料新鮮度    CSV 批次模式：T+1（次日）         即時（但 CSV 就是次日資料）
              API 模式：即時                   即時
──────────────────────────────────────────────────────────────────

結論：橋接層的 2-3 天設計成本，換來的是長期的穩定性和可維護性。
     跳過橋接層是快速上線的選擇，但每次 SAP 版本升級都要付出代價。
```

---

## 八、面試答題要點

> *「這道題考的是 FDE 如何讓 AI 系統在真實企業環境中落地，而不只是在 Demo 環境裡跑。*
>
> *三種資料來源，三種整合模式：SAP 用 API 橋接層（隱藏認證複雜性、Rate Limiting、Cache）；Oracle 用 Stored Procedure 層（防 SQL Injection、最小權限、索引優化）；Mainframe CSV 用批次攝取 Pipeline（GCS → Schema 驗證 → BigQuery，Agent 查 BigQuery 不讀原始 CSV）。*
>
> *安全設計：Cloud Run 透過 VPC Connector 走私有網路，不讓資料經過公共網路。Credentials 存在 Secret Manager，Agent 代碼裡沒有任何密碼。Oracle DB 帳號只有 EXECUTE 特定 SP 的權限，沒有任何 SELECT/UPDATE 權限。*
>
> *批次資料的資料新鮮度：Tool docstring 說明「每日凌晨更新，非即時」，讓 LLM 在回答時主動告知用戶資料截止時間，管理預期。*
>
> *橋接層的 Trade-off：多了 2-3 天設計成本，但讓 Agent 和 Legacy 系統之間有一個穩定的隔離層——SAP 改版了，只需要改橋接層，不需要改所有 Agent 代碼。」*

---

**系列導覽：**  
← [（三十六）生產級 Eval Pipeline 設計](../fde-interview-guide-part36-eval-pipeline-zh/)  
→ [（三十八）從 POC 到 Production：生產化清單](../fde-interview-guide-part38-prototype-to-production-zh/)
