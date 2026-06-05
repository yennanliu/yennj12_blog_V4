---
title: "FDE 面試準備指南（三十七）：RKK 實戰——企業 AI 的「連接組織」：Legacy 系統整合、API 橋接與安全邊界設計"
date: 2026-06-05T15:00:00+08:00
draft: false
description: "以 Google FDE 視角拆解企業 AI 部署最困難的部分：如何把 Gemini / ADK 接上客戶的 SAP、舊版 REST API、Oracle DB 和 mainframe 資料孤島；API 橋接層的設計模式；安全邊界的連接工程（Private Service Connect、CMEK、VPC-SC）；以及當客戶說「我的資料在五個不同的系統裡」時 FDE 的系統設計方法"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Integration", "Legacy", "API", "GCP", "VPC", "Security", "Enterprise", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "21 min"
---

> JD 裡說的「connective tissue」——  
> 不是一個浪漫的比喻，是 FDE 最常踩的坑。  
> Gemini 很強大，ADK 架構很漂亮。  
> 但如果你沒辦法讓 Agent 安全地讀到客戶的 SAP 資料，  
> 整個系統在 Demo 結束後就停在那裡，永遠進不了生產。

---

## 面試情境

> **面試官：**「客戶是一家製造業，有 30 年歷史。他們的資料分散在三個地方：一套 SAP ERP（有 REST API 但文件很爛）、一套 Oracle 資料庫（只有 DB 直連，沒有 API）、還有一個每天從 mainframe 匯出的 CSV 檔案。他們想讓 AI 可以回答『我們的庫存狀況如何、哪個供應商最近交期有問題』。你怎麼設計這個整合層？」

---

## 一、「連接組織」是什麼問題

```
FDE 日常工作的現實：

  理想（Demo 時）：
    Agent → Tool → API → 資料 → 回答

  現實（客戶端）：
    Agent
      ↓
    Tool（你寫的）
      ↓
    ???（客戶的系統邊界）
      ├── SAP API（文件不完整，認證方式客製化）
      ├── Oracle DB（沒有 API，需要直連）
      ├── CSV 檔案（每天凌晨 2 點才有，格式偶爾會變）
      └── Excel 報表（在某個 SharePoint 上，有密碼保護）

  「連接組織」的工程任務：
    1. 了解每個資料來源的存取方式和限制
    2. 設計一個讓 Agent 可以安全、可靠存取的介面層
    3. 處理格式轉換、認證、錯誤處理、資料新鮮度
    4. 確保整個路徑符合客戶的安全和合規要求

  這個工作不性感，但是決定 AI 系統能不能進生產環境的關鍵。
```

---

## 二、Legacy 系統整合的三種模式

### 模式一：API 橋接（最常見）

```
適用場景：資料來源有 API，但 API 設計不適合直接給 Agent 用。

問題範例：
  SAP 的 REST API：
  GET /api/v1/material/{material_id}/stock
  → 回傳一個 200 欄位的 JSON，其中 agent 只需要 5 個欄位
  → 認證方式是 SAP OAuth + 額外的 client certificate
  → Rate limit: 10 requests/sec per user

設計模式：在 Agent 和 SAP API 之間加一個「橋接層」

  Agent Tool
       ↓
  ┌──────────────────────────────────────┐
  │  Internal Adapter Service（你寫的）   │
  │                                       │
  │  功能：                               │
  │  ├── 處理 SAP 認證（隱藏 credentials）│
  │  ├── 資料轉換（200 欄位 → 5 欄位）    │
  │  ├── Rate Limiting 和 Retry 邏輯      │
  │  ├── Response Caching（TTL 5 分鐘）   │
  │  └── Schema 標準化（統一輸出格式）     │
  └──────────────────────────────────────┘
       ↓
  SAP REST API

橋接層的設計原則：
  對 Agent：簡單、穩定的介面（「查庫存」函數）
  對 SAP：隱藏所有複雜的認證和格式問題

  Agent Tool 的樣子（橋接後）：
  def get_inventory_status(material_id: str, warehouse: str) -> dict:
      """查詢指定物料在指定倉庫的庫存狀況。
      回傳：available_quantity, unit, last_updated。"""
      return adapter.query_sap_inventory(material_id, warehouse)

  Agent 看到的是簡單的函數，
  不知道背後是 SAP + 複雜認證 + 資料轉換。
```

### 模式二：資料庫直連層（DB 沒有 API）

```
適用場景：Oracle 資料庫，沒有 API wrapper，只能 JDBC / ODBC 直連。

風險：
  ├── Agent 直接生成 SQL 執行 → SQL Injection 風險
  ├── Agent 可能跑昂貴的 full table scan → 效能問題
  └── 資料庫憑證需要安全管理

安全設計：

  原則：Agent 永遠不直接生成 SQL 並執行。
  
  方案 A：Stored Procedure 層（推薦生產用）
    → 把所有 Agent 需要的查詢包成 Stored Procedures
    → Agent 只能呼叫 Stored Procedures，不能執行任意 SQL
    → 好處：SQL 由 DBA 審核，不能被 injection 攻擊

  方案 B：ORM 查詢層（程式碼層面防注入）
    → 用 SQLAlchemy 等 ORM，用 parameterized queries
    → 永遠不用字串拼接 SQL
    → 限制：只開放特定的查詢操作（select only，不開 update/delete）

  實作範例（SQLAlchemy + Parameterized Query）：

  def get_supplier_delivery_performance(
      supplier_id: str,
      date_from: str,
      date_to: str
  ) -> list[dict]:
      """查詢指定供應商在時間範圍內的交期達成率。"""
      # ✅ Parameterized query，防止 SQL Injection
      query = text("""
          SELECT supplier_name, order_count,
                 on_time_count,
                 ROUND(on_time_count * 100.0 / order_count, 1) as on_time_rate
          FROM supplier_delivery_history
          WHERE supplier_id = :supplier_id
            AND delivery_date BETWEEN :date_from AND :date_to
      """)
      result = db.execute(query, {
          "supplier_id": supplier_id,
          "date_from": date_from,
          "date_to": date_to
      })
      return [dict(row) for row in result]

  憑證管理：
    ├── 不在代碼裡寫 DB password
    ├── 用 Secret Manager 儲存，Runtime 取得
    └── DB 帳號只有 SELECT 權限（最小權限原則）
```

### 模式三：批次資料攝取（CSV / 非即時資料）

```
適用場景：每天從 mainframe 匯出的 CSV，資料新鮮度要求不高。

設計原則：批次資料不應該讓 Agent 即時讀取原始 CSV。

推薦架構：

  Mainframe CSV 匯出（凌晨 2 點）
       ↓
  Cloud Storage（GCS）
       ↓
  Data Validation（Cloud Dataflow 或簡單的 Cloud Function）
  ├── Schema 驗證（欄位數量、資料型別）
  ├── 異常值偵測（庫存為負值？）
  └── 版本比較（格式今天有沒有改變？）
       ↓
  BigQuery（結構化儲存，有 SQL 查詢能力）
       ↓
  Agent Tool（查 BigQuery，不查原始 CSV）

為什麼不直接讓 Agent 讀 CSV：
  ├── CSV 格式偶爾改變 → Agent 會解析錯誤
  ├── 大檔案（百萬行）直接讀進 context → Token 爆炸
  └── 沒有 schema validation → 髒資料直接進 AI

Agent 看到的 Tool：
  def get_daily_production_summary(date: str) -> dict:
      """查詢指定日期的生產摘要。資料每日更新一次（凌晨更新）。"""
      # 查 BigQuery，不讀 CSV
      return bigquery_client.query(
          f"SELECT * FROM production_summary WHERE date = '{date}'"
      )

資料新鮮度的溝通：
  Tool 的 docstring 要說清楚「每日更新一次（凌晨更新）」
  → 讓 LLM 在回答時知道告訴用戶：「此資料截至昨日」
  → 管理用戶對即時性的預期
```

---

## 三、安全邊界的連接工程

### Private Service Connect：讓 Agent 不走公共網路

```
問題：ADK Agent 在 Cloud Run 上，需要呼叫客戶的內部 Oracle DB。
      如果走公共網路：資料經過網際網路，不符合企業安全政策。

解法：Private Service Connect

架構：

  Cloud Run（Agent）
       ↓ 私有網路（不走公共網路）
  VPC Network
       ↓
  Private Service Connect Endpoint
       ↓
  客戶的 On-premise 網路（透過 Cloud VPN 或 Cloud Interconnect）
       ↓
  Oracle DB（在客戶內部）

設定要點：
  ├── Agent 所在的 VPC 和客戶 On-premise 之間要有 Cloud VPN
  ├── Oracle DB 的 IP 在 VPC 內部可路由
  ├── Cloud Run 的 Egress 設定為「僅 VPC」（不能走公共網路）
  └── Firewall Rules 只允許 Cloud Run 的 Service Account 連 DB port

面試的回答方式：
  「我不會讓 Agent 透過公共網路連 Oracle DB。
   設計是：Cloud Run 設定 VPC Connector，
   所有 Outbound traffic 走 VPC，
   透過 Cloud VPN tunnel 接到客戶的內部網路。
   這樣資料不出客戶的安全邊界。」
```

### VPC Service Controls：防止資料外洩

```
VPC-SC 是 GCP 的資料邊界控制：
  不是「防止人進來」（那是 IAM 的工作），
  而是「防止資料出去」。

使用情境：
  客戶擔心：「如果 Agent 被 Prompt Injection 攻擊，
             會不會把敏感資料傳送到外部？」

VPC-SC 的效果：
  ├── BigQuery 資料無法透過 API 傳到 VPC 邊界外
  ├── Cloud Storage 的資料無法被 VPC 外部的 service 存取
  └── 即使 Agent 的代碼被 compromise，也無法把資料「搬出去」

設定：
  建立一個 Service Perimeter，把以下資源包在裡面：
  ├── BigQuery（生產資料）
  ├── Cloud Storage（文件、CSV）
  ├── Vertex AI（LLM 呼叫）
  └── Cloud Run（Agent 執行環境）

  在 Perimeter 外的服務一律無法存取 Perimeter 內的資源。

注意：VPC-SC 會阻斷合法的 API 呼叫，設定前要先盤點所有服務間的通信。
```

### CMEK：客戶自己掌控加密金鑰

```
CMEK（Customer-Managed Encryption Keys）的意義：
  GCP 預設用 Google 管理的金鑰加密資料。
  CMEK 讓客戶用自己的 Cloud KMS 金鑰加密——
  Google 員工無法在沒有客戶金鑰的情況下讀取資料。

適用場景：
  ├── 金融業（監管要求對加密金鑰有完整控制）
  ├── 醫療業（PHI 資料的合規要求）
  └── 政府機關（資料主權要求）

代價：
  ├── 效能開銷（每次加解密都要呼叫 Cloud KMS）
  ├── 運維複雜度（金鑰輪換、備份是客戶的責任）
  └── 如果客戶不小心刪除了金鑰，資料永久無法讀取

FDE 的溝通方式：
  不說「你應該用 CMEK」，
  說：「CMEK 讓你對加密金鑰有完整控制權，
        但這也意味著金鑰管理的責任在你這邊。
        你的合規要求是什麼？我們可以根據要求決定是否需要 CMEK。」
```

---

## 四、資料孤島整合的實際工程流程

```
FDE 到客戶現場的第一天，資料整合的 Discovery 流程：

Week 1：資料盤點
  問題清單：
  ├── 你的資料在哪裡？（列出所有資料來源）
  ├── 每個資料來源的存取方式是什麼？（API / DB / 檔案 / 人工 Excel）
  ├── 更新頻率是多少？（即時 / 每日 / 每週 / 手動）
  ├── 有沒有 API 文件？（有 / 沒有 / 有但過時）
  ├── 認證方式是什麼？（OAuth / API Key / IP Whitelist / VPN）
  └── 有哪些安全和合規限制？（PII / 不能出 VPC / 需要審計日誌）

  輸出：資料地圖（Data Map）
  ┌────────────────────────────────────────────────────────────────┐
  │ 資料來源   │ 存取方式   │ 更新頻率 │ 安全限制    │ 整合模式      │
  ├────────────┼────────────┼──────────┼─────────────┼───────────────┤
  │ SAP ERP    │ REST API   │ 即時     │ 需在 VPC    │ API 橋接層    │
  │ Oracle DB  │ DB 直連    │ 即時     │ 不能出內網  │ Stored Proc   │
  │ Mainframe  │ CSV 匯出   │ 每日     │ 無 PII      │ GCS → BigQuery│
  └────────────────────────────────────────────────────────────────┘

Week 2：建立橋接層原型
  按照資料地圖，逐一建立每個資料來源的 Adapter。
  每個 Adapter 要通過：
  ├── 功能測試（能讀到資料）
  ├── 安全測試（認證正確，不暴露憑證）
  └── 邊界測試（資料來源掛掉時，Adapter 如何回應）

Week 3：Agent Tool 整合
  把所有 Adapter 包裝成 ADK Tool，
  確保 Tool 的 docstring 讓 LLM 知道：
  ├── 什麼時候用這個 Tool
  ├── 資料的新鮮度限制
  └── 哪些查詢範圍是這個 Tool 不支援的
```

---

## 五、面試官地雷題

**地雷 1：「Agent 呼叫外部 API 失敗了。你的 Tool 應該怎麼處理？」**

```
答：三層錯誤處理：

    Layer 1：重試（Transient Error）
      HTTP 429（Rate Limited）、503（Service Unavailable）→ 指數退避重試
      最多 3 次，退避間隔：1s → 2s → 4s
      
    Layer 2：降級（Graceful Degradation）
      如果重試後仍失敗：
      ├── 有 Cache？→ 回傳 stale cache + 告知用戶「資料可能不是最新」
      └── 沒有 Cache？→ 回傳結構化的錯誤訊息（不是 exception）
      
      Tool 回傳：
      {
        "status": "error",
        "error_type": "external_api_unavailable",
        "message": "SAP 庫存系統目前無法連線，請稍後再試。",
        "fallback_data": None,
        "last_successful_query": "2026-06-05T10:30:00"
      }
      
      讓 Agent 的 LLM 能理解這個錯誤，並給用戶合理的回應，
      而不是把底層的 ConnectionError 吐給用戶。

    Layer 3：Circuit Breaker
      如果某個 API 連續失敗 5 次 → 開啟 Circuit Breaker
      接下來 60 秒不再嘗試，直接回傳 fallback
      避免 Agent 反覆嘗試一個確定掛掉的服務
```

**地雷 2：「客戶說 SAP 的 API 有 Rate Limit（10 req/sec），
但高峰時 Agent 可能有 100 個並發請求。你怎麼設計？」**

```
答：三個策略組合：

    1. Request Queue + Rate Limiter（最根本）
       在橋接層加入 Token Bucket 或 Leaky Bucket 算法
       確保對 SAP API 的呼叫不超過 10 req/sec
       多餘的請求排隊等待（設定 queue timeout）

    2. Caching（減少實際呼叫量）
       庫存查詢：TTL 5 分鐘（庫存資料不需要秒級新鮮度）
       供應商資料：TTL 1 小時
       Cache Hit Rate 如果能達到 70%，實際 API 呼叫量降到 30%

    3. 主動溝通 Rate Limit 到客戶
       不只是工程解法，也要讓客戶知道：
       「SAP API 的 Rate Limit 是 AI 系統的瓶頸之一。
        如果未來並發用戶超過 X，我們需要和你的 SAP 團隊
        申請更高的 Rate Limit，或者討論 API Gateway 的方案。」
```

**地雷 3：「客戶的 IT 說『資料不能離開我們的內部網路』。
但你需要用 Vertex AI 的 Gemini API（在 Google Cloud 上）。
這兩者怎麼同時成立？」**

```
答：這是「資料主權」和「AI 計算能力」的張力，需要釐清限制的範圍。

    首先問清楚：「不能離開內部網路」指的是什麼？
    
    情況 A：原始業務資料（庫存數字、合約內容）不能出去
      → 解法：用 PII Tokenization / 資料摘要
              Agent 把原始資料做成 query/context 後，
              只把「問題和相關片段」送給 Gemini，
              不把整個資料庫 dump 傳過去
              Vertex AI 呼叫的內容是「查詢 + 相關段落」，
              不是完整的業務資料庫
              
              同時，用 Private Service Connect 讓
              Cloud Run（Agent）→ Vertex AI 的呼叫走私有網路

    情況 B：任何資料都不能離開（最嚴格解釋）
      → 需要 Google Distributed Cloud（GDC）
        在客戶的資料中心部署 Vertex AI 服務
        AI 計算在客戶內部發生，資料完全不離開
        → 代價：更高的部署成本和維護複雜度
    
    FDE 的工作是幫客戶釐清哪個情況符合他們的實際需求，
    而不是一開始就說「那就不能用 Gemini」。
```

---

## 六、面試回答完整示範

```
面試官問：三個資料來源（SAP / Oracle / Mainframe CSV），如何整合？

資料盤點先行（30 秒）：
「在設計之前，我需要先問幾個問題：
 SAP API 有文件嗎？有 Rate Limit 嗎？
 Oracle 能加 Stored Procedures 嗎，還是只能 SELECT？
 CSV 的 Schema 穩定嗎？有沒有安全合規要求？
 這些答案決定了整合的複雜度和設計方向。」

三層整合設計（2 分鐘）：
「根據你描述的場景，我的設計是：

 SAP：API 橋接層，包裝認證和 Rate Limiting，
 Agent 看到的是簡單的『查庫存』函數，
 不知道背後的 SAP 認證複雜度。

 Oracle：Stored Procedures 層，
 DBA 把 Agent 需要的查詢包成 4-5 個預定義的 Stored Procedures，
 Agent 只能呼叫這些 Procedures，
 不能執行任意 SQL，防止 injection 攻擊。

 CSV：建立批次攝取 Pipeline——
 CSV 每天匯出後自動上傳到 GCS，
 Cloud Function 做 Schema 驗證，
 寫入 BigQuery。
 Agent 查 BigQuery，不讀原始 CSV。
 Tool docstring 明確說明：此資料每日更新，非即時。

安全設計（30 秒）：
 Cloud Run（Agent）透過 VPC Connector 走私有網路，
 用 Private Service Connect 連到客戶內部的 Oracle 和 SAP。
 所有 credentials 存在 Secret Manager，
 不在代碼裡硬寫密碼。」
```

---

**FDE 的核心競爭力之一，是讓 AI 系統接上現實世界——**  
**那個充滿 30 年老系統、沒有 API 文件、IT 政策限制的現實世界。**  
**這個能力，不是靠讀 Gemini 文件學來的，而是靠一個又一個真實整合案例累積的判斷力。**
