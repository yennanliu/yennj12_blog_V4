---
title: "FDE 面試準備指南（三十）：顧問實戰——Constraint-First 架構設計：VPC 限制下的 GCP AI 系統"
date: 2026-06-04T21:00:00+08:00
draft: false
weight: 30
description: "以 Google FDE 顧問視角拆解限制驅動的 AI 架構設計：當客戶說「所有資料不能離開我們的 VPC」，你的 Vertex AI 架構要怎麼調整、VPC Service Controls 的設計原理、Private Service Connect 的部署模式，以及金融與政府客戶常見的合規限制應對"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Consultant", "VPC", "Security", "Vertex AI", "GCP", "Compliance", "Architecture", "Interview", "Google", "RKK"]
authors: ["yen"]
readTime: "17 min"
---

> 大多數的架構設計課程從「最優解」出發。  
> 但 FDE 的真實工作，是從「客戶的限制」出發。  
> 「所有資料不能出 VPC」、「模型不能用 SaaS API」、「每個 API call 都要有審計日誌」——  
> 這些限制不是問題，是你設計的起點。

---

## 面試情境

> **面試官：**「你的客戶是一家銀行。他們的 IT 安全政策規定：所有含有客戶 PII 的資料不能傳送到外部網路，所有 API 呼叫必須在私有網路內完成，並且每個 AI 模型的調用都要有審計日誌。他們想在這個條件下部署一個 RAG-based 合約審閱 Agent。你的架構是什麼？」

---

## 一、FDE 面對限制的第一步：分類

收到限制條件，先做分類，不要立刻開始設計架構：

```
限制分類框架：

類型 1：資料主權限制（Data Residency）
  「資料不能離開特定地理區域」
  → GCP Region 選擇問題
  → 影響：model endpoint 必須在指定 Region

類型 2：網路隔離限制（Network Isolation）
  「API 呼叫必須在私有網路內」
  → VPC 架構問題
  → 影響：需要 Private Service Connect / VPC-SC

類型 3：資料分類限制（Data Classification）
  「PII 不能傳給外部服務」
  → 資料流設計問題
  → 影響：需要 PII detection + 資料遮罩 pipeline

類型 4：審計與合規限制（Audit & Compliance）
  「所有 AI 調用要有 audit log」
  → Observability 架構問題
  → 影響：Cloud Audit Logs + SIEM 整合

本題的限制：類型 2 + 3 + 4，三個同時
```

---

## 二、核心技術：VPC Service Controls（VPC-SC）

這是 Google Cloud 上的金融/政府客戶必備知識：

```
沒有 VPC-SC 的預設架構：

┌──────────────────────────────────────────────┐
│  Client VPC                                   │
│                                               │
│  Application → Vertex AI API（公開 endpoint）│
│                       ↑                      │
│               資料流出 VPC，經過公共網路      │
│               ← 銀行 IT 不接受                │
└──────────────────────────────────────────────┘

加入 VPC-SC 後：

┌─────────────────────────────────────────────────────────┐
│  VPC Service Perimeter（安全邊界）                       │
│                                                         │
│  ┌─────────────────┐    ┌──────────────────────────┐   │
│  │  Client VPC      │    │  Restricted Google APIs  │   │
│  │                 │    │                          │   │
│  │  Application    │───→│  Vertex AI（限制在邊界內）│   │
│  │  GKE / Cloud Run│    │  Cloud Storage           │   │
│  │                 │    │  BigQuery                │   │
│  └─────────────────┘    └──────────────────────────┘   │
│                                                         │
│  邊界外的任何服務無法存取邊界內的資料                    │
└─────────────────────────────────────────────────────────┘

效果：
├── Vertex AI 的 API 呼叫不經過公共網路
├── 資料留在客戶的 GCP Organization 內
└── 即使 IAM 憑證外洩，也無法從 VPC 外存取資料
```

---

## 三、完整架構：VPC 限制下的 RAG 合約審閱 Agent

```
┌─────────────────────────────────────────────────────────────────┐
│                   VPC Service Perimeter                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Customer VPC（asia-east1）                               │   │
│  │                                                          │   │
│  │  ┌────────────┐    ┌──────────────────────────────────┐ │   │
│  │  │ User Browser│    │  Private Load Balancer           │ │   │
│  │  │ (Internal) │───→│  (Internal IP only)              │ │   │
│  │  └────────────┘    └──────────────┬───────────────────┘ │   │
│  │                                   │                      │   │
│  │                    ┌──────────────▼───────────────────┐ │   │
│  │                    │  RAG Orchestration Service        │ │   │
│  │                    │  (Cloud Run, VPC Connector)       │ │   │
│  │                    └──────┬───────────────┬───────────┘ │   │
│  │                           │               │             │   │
│  │              ┌────────────▼──┐   ┌────────▼──────────┐ │   │
│  │              │  PII Scanner  │   │  Document Retrieval│ │   │
│  │              │  (Cloud DLP)  │   │  Pipeline         │ │   │
│  │              └────────────┬──┘   └────────┬──────────┘ │   │
│  │                           │               │             │   │
│  │                    ┌──────▼───────────────▼───────────┐ │   │
│  │                    │  Private Service Connect          │ │   │
│  │                    └──────────────┬───────────────────┘ │   │
│  └──────────────────────────────────┼───────────────────── │   │
│                                     │                       │   │
│  ┌──────────────────────────────────▼───────────────────┐  │   │
│  │  Restricted Google APIs（透過 VPC-SC 保護）           │  │   │
│  │                                                       │  │   │
│  │  ├── Vertex AI Gemini（LLM Generation）               │  │   │
│  │  ├── Vertex AI Embedding（text-embedding-004）        │  │   │
│  │  ├── Vertex AI Vector Search（向量索引）               │  │   │
│  │  ├── Cloud Storage（合約 PDF 儲存）                   │  │   │
│  │  └── Cloud Audit Logs（所有 API 調用記錄）            │  │   │
│  └───────────────────────────────────────────────────────┘  │   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、PII 處理：資料不出去，但 LLM 需要看文件

這是最微妙的部分。銀行說「PII 不能傳給外部服務」，但 Vertex AI 是 GCP 的服務——在同一個 VPC-SC Perimeter 內，這算不算「外部」？

```
正確的理解框架：

VPC-SC Perimeter 內的 Vertex AI ≠ 外部服務
├── 資料不會離開 GCP Organization
├── Google 不會用客戶資料訓練模型（BAA 可簽）
└── 對銀行 IT 的說法：「資料在你們的 GCP 組織邊界內」

但仍然需要 PII 最小化設計：

做法 1：Cloud DLP（Data Loss Prevention）掃描
  在文件進入 RAG Pipeline 之前，先掃描 PII：
  
  from google.cloud import dlp_v2
  
  dlp = dlp_v2.DlpServiceClient()
  
  # 定義要偵測的 PII 類型
  info_types = [
      {"name": "PERSON_NAME"},
      {"name": "PHONE_NUMBER"},
      {"name": "EMAIL_ADDRESS"},
      {"name": "FINANCIAL_ACCOUNT_NUMBER"},
  ]
  
  # 在文件 Indexing 時掃描（不是在 Query 時）
  inspect_config = dlp_v2.InspectConfig(info_types=info_types)
  
  # 可選：Redact（遮罩）或 Tokenize（標記化）
  # 視 use case 決定：合約審閱通常不需要遮罩，只需要掃描

做法 2：Tokenization（敏感欄位替換）
  如果合約裡有客戶的真實姓名和帳號，
  在進入 LLM 前替換成 TOKEN_001, ACCOUNT_002：
  
  合約原文：「乙方王大明（身分證 A123456789）同意...」
  Tokenized：「乙方 [PERSON_001]（ID: [ID_001]）同意...」
  
  LLM 回答後，再把 TOKEN 還原成真實值
  好處：LLM 不會「看到」真實 PII，符合最嚴格的合規要求
```

---

## 五、審計日誌：每個 AI 調用都要留記錄

```
Vertex AI 的 Audit Log 設定：

# 在 GCP Organization 層級啟用 Data Access Audit Logs
gcloud organizations add-iam-policy-binding ${ORG_ID} \
  --member="allUsers" \
  --role="roles/logging.viewer" \
  --condition=None

# 啟用 Vertex AI 的 Data Access log
gcloud projects set-iam-policy ${PROJECT_ID} policy.yaml

policy.yaml 內容：
  auditConfigs:
  - service: aiplatform.googleapis.com
    auditLogConfigs:
    - logType: DATA_READ   # 記錄模型調用的 input
    - logType: DATA_WRITE  # 記錄模型調用的 output

每次 Vertex AI 調用會自動記錄：
  ├── 誰調用的（User / Service Account）
  ├── 什麼時間
  ├── 調用了哪個模型
  ├── Request 和 Response 的摘要（不是全文，避免 log 太大）
  └── Latency 和 Status
```

### 審計 Log 的架構整合

```
Vertex AI Audit Logs
       ↓
Cloud Logging（集中儲存，保留 7 年）
       ↓
Log Sink → BigQuery（供合規查詢）
       ↓
Log Sink → Pub/Sub → SIEM（如 Splunk / Chronicle）
       ↓
Client 的 Security Operations Center（SOC）即時監控

這個設計讓銀行的合規團隊可以：
├── 查「2026 年 Q1，哪些合約被 AI 審閱過」
├── 查「誰在什麼時間用 AI 查了什麼文件」
└── 對接現有的 SIEM 告警規則
```

---

## 六、Private Service Connect：確保流量不出 VPC

```
為什麼需要 Private Service Connect（PSC）？

預設的 Vertex AI API 呼叫路徑：
  Your VPC → 公共網路 → Vertex AI endpoint
  
  問題：流量經過公共網路（銀行 IT 說 NO）

PSC 的路徑：
  Your VPC → PSC Endpoint（Internal IP）→ Vertex AI
  
  整個路徑不離開 Google 的骨幹網路，
  不需要配置 NAT 或 Firewall 開外網洞

設定步驟：
# 1. 在 VPC 內建立 PSC endpoint
gcloud compute addresses create vertex-ai-psc \
  --region=asia-east1 \
  --subnet=my-subnet \
  --addresses=10.0.0.100  # 私有 IP

# 2. 建立 Forwarding Rule 指向 Vertex AI 服務
gcloud compute forwarding-rules create vertex-ai-psc-rule \
  --region=asia-east1 \
  --network=my-vpc \
  --address=vertex-ai-psc \
  --target-service-attachment=projects/.../serviceAttachments/...

# 3. 應用程式改用私有 IP
import vertexai
vertexai.init(
    project="my-project",
    location="asia-east1",
    api_endpoint="10.0.0.100"  # PSC 的私有 IP
)
```

---

## 七、面試回答的完整框架

```
「面對這種 Constraint-First 的設計問題，我的思路是：

第一步：分類限制
  銀行給的限制有三類：網路隔離、資料分類、審計合規。
  每類都有對應的 GCP 解法。

第二步：確認每個限制的核心技術
  網路隔離 → VPC Service Controls + Private Service Connect
  PII 保護 → Cloud DLP + Tokenization Pipeline
  審計日誌 → Cloud Audit Logs → BigQuery + SIEM 整合

第三步：畫出資料流
  我會先畫出一個資料如何從用戶瀏覽器到 LLM，
  再回來的完整路徑，確認每一跳都符合限制。

第四步：和客戶確認
  在設計完之後，我會用一張簡單的圖，
  向客戶的安全長確認：這個架構是否符合你們的安全政策？
  
  這一步很重要——FDE 不是合規顧問，
  最終的合規確認要由客戶的法務和安全團隊決定。
  我的工作是提供技術方案，讓他們可以做出有依據的決定。」
```

---

## 八、常見的銀行/金融客戶限制速查表

```
限制                           GCP 解法
────────────────────────────────────────────────────────────────
「資料不能出台灣/特定國家」     Region 鎖定（asia-east1）
                               VPC-SC Data Residency Policy

「API 不能走公網」              Private Service Connect
                               VPC Service Controls

「PII 不能給外部 AI 服務」      Cloud DLP Inspection
                               Tokenization Pipeline
                               VPC-SC（Vertex AI 在邊界內）

「每次 AI 調用要有 Audit Log」  Cloud Audit Logs（Data Access）
                               Log Sink → BigQuery / SIEM

「模型必須是我們自己的，        Vertex AI Custom Model Deploy
  不能用 Google 的 SaaS 模型」  (Gemini 可 Fine-tune + 部署)
                               或 GKE 上自建推論服務

「所有通訊必須加密」            默認 TLS 1.2+
                               CMEK（Customer Managed Encryption Keys）
                               for data at rest

「不能用任何第三方服務」        All-GCP Stack：
                               Vertex AI + BigQuery + GCS + GKE
                               不使用 Pinecone / OpenAI 等外部 SaaS
```

---

**限制是設計的輸入，不是設計的障礙。**  
**FDE 的工作是把「不能這樣」，變成「所以我們這樣做」。**
