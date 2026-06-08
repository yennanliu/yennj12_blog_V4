---
title: "Data Residence & Sovereign AI：金融醫療場景的地緣合規架構"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析資料主權架構的技術控制堆疊，涵蓋 VPC Service Controls、Organization Policy、Vertex AI 區域端點及審計證據，幫助工程師在面試中精準回答金融與醫療合規場景。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Compliance", "SovereignAI", "DataResidency"]
authors: ["yen"]
readTime: "18 min"
---

**資料主權不是「把資料放在某個 bucket 就好」，而是一套覆蓋儲存、運算、網路傳輸、金鑰管理、審計稽核的完整地理邊界保證——任何一層缺口都讓合規承諾形同虛設。**

---

## 一、為什麼面試官問這個

面試官出這道題，真正測試的是三個維度的工程判斷力：

- **法規翻譯能力**：HIPAA 的「Protected Health Information 不得離開美國」、台灣個人資料保護法（PDPA）的「特種個資需要額外保護措施」、金管會對金融機構雲端使用的指引——這些法規條文候選人能否翻譯成具體技術控制？弱答是「我們用私有雲」，強答是列出五層控制並說明每層的法規對應點。
- **AI 系統特殊性理解**：傳統應用的資料主權相對直覺（資料庫在哪裡），但 LLM 系統的複雜在於：推論時的 KV cache 是暫存資料、Embedding 是資料的另一種形式、Fine-tuning 過程資料會進入梯度計算——這些「衍生資料」的地理位置同樣受合規要求限制。
- **陷阱識別與風險評估**：Batch Prediction 跨 region 執行的預設行為、VPC-SC dry-run 忘了切換 enforce、multi-region KMS key 的金鑰複製行為——這三個是最常在真實合規審計中踩到的地雷，能說出這些才代表有實戰經驗。

**典型弱答**（5 分）：「我們把 GCS bucket 設定在 asia-east1，資料就在台灣了。」只解決儲存層，完全忽略推論、金鑰、傳輸三層。

**典型中答**（7 分）：「Vertex AI 要設 region，VPC-SC 要設邊界，要簽 DPA。」方向正確但沒有深度，說不出 VPC-SC 的機制、Batch Prediction 的陷阱、延遲數字。

**強答**（9–10 分）：系統性列出五層控制，說明 VPC-SC 在控制平面層攔截的原理，主動點出 Batch Prediction 必須顯式設 region，量化 VPC-SC 執行延遲 < 5ms，並提出 GDC 作為最高主權要求的升級路徑。

---

## 二、核心原理與技術深度

### 為什麼 AI 系統的資料主權比傳統應用更難

傳統三層式 Web 應用的資料主權相對簡單：資料庫在 asia-east1，應用伺服器在 asia-east1，問題解決。LLM 系統的難點在於資料在多個地方以多種形式存在：

```
用戶請求（含敏感資料）
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  資料衍生鏈（每個節點都需要地理邊界保證）                      │
│                                                           │
│  原始 Prompt ──▶ Embedding 向量 ──▶ KV Cache（推論暫存）    │
│       │                │                  │              │
│       │          向量資料庫            GPU 顯存           │
│       │          （需 region pin）     （需 region pin）  │
│       │                                                   │
│       └──▶ Fine-tuning 梯度 ──▶ Adapter 權重              │
│                  │                      │                │
│           訓練叢集位置              模型儲存位置            │
│           （最常被忽略）            （需 region pin）      │
└───────────────────────────────────────────────────────────┘
```

每一個節點都可能在不同的地理位置，而且雲端服務商的預設行為是「就近使用最快的硬體」，這與合規要求「使用指定 region 的硬體」天然衝突。

### 五層技術控制堆疊

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 5：合約層                                                      │
│  Data Processing Agreement (DPA)                                    │
│  ├─ 保證資料不用於基礎模型訓練（關鍵！）                                │
│  ├─ 規定資料刪除期限（通常 30–90 天後）                                 │
│  └─ 稽核權：企業有權要求第三方驗證合規                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 4：稽核層                                                      │
│  Cloud Audit Logs（DATA_READ + DATA_WRITE + ADMIN_ACTIVITY）         │
│  ├─ 每筆 API 呼叫記錄：時間戳、呼叫者身份、資源位置、來源 IP             │
│  ├─ 匯出至 BigQuery，保留 30 天熱 + 90 天冷 + 3 年歸檔                 │
│  └─ SIEM 整合：Splunk / Chronicle 自動解析違規模式                     │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3：組織政策層                                                  │
│  Organization Policy                                                │
│  ├─ constraints/gcp.resourceLocations = ["asia-east1"]              │
│  ├─ 傳播時間 < 60 秒，新規則全組織生效                                  │
│  └─ 禁止 multi-region KMS key 建立                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2：網路隔離層                                                  │
│  VPC Service Controls（VPC-SC）                                     │
│  ├─ 服務邊界（Service Perimeter）包圍所有受保護資源                     │
│  ├─ Access Context Manager 評估請求合法性                             │
│  ├─ 執行延遲 < 5ms，邊界違規觸發 403 + Audit Log                       │
│  └─ 即使 GCP 自身員工也無法繞過邊界存取                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1：計算 / 儲存 / 加密層                                        │
│  Region Pinning + CMEK + Regional Endpoint                          │
│  ├─ Vertex AI API: location="asia-east1"（必須顯式）                  │
│  ├─ Cloud KMS: regional key，不啟用跨 region 複製                     │
│  ├─ GCS: ASIA-EAST1 region，uniform bucket-level access             │
│  └─ Cloud SQL / Spanner: region 設定，CMEK 加密                      │
└─────────────────────────────────────────────────────────────────────┘
```

### VPC Service Controls 的控制平面攔截原理

VPC-SC 最常被誤解的地方是：它不是網路防火牆（不看封包內容），而是在 GCP 控制平面（Control Plane）層做 API 呼叫攔截。

當一個 API 請求抵達時，執行順序如下：

```
API 請求（含 Bearer Token）
        │
        ▼
┌───────────────────────────────┐
│  Step 1: IAM 身份驗證          │
│  驗證 Token 有效性 + 角色綁定   │
│  結果：ALLOWED / DENIED        │
└───────────┬───────────────────┘
            │ ALLOWED
            ▼
┌───────────────────────────────┐
│  Step 2: VPC-SC 邊界檢查       │
│  ├─ 請求者是否在邊界內的 Project │
│  ├─ 目標資源是否在同一邊界內     │
│  ├─ Access Level 條件是否滿足  │
│  │  - 來源 IP 範圍             │
│  │  - 裝置合規狀態              │
│  │  - 地理位置（可選）          │
│  └─ 是否有 Ingress/Egress 規則  │
│                               │
│  結果：ALLOWED / VPC_SC_DENIED │
└───────────┬───────────────────┘
            │ ALLOWED
            ▼
┌───────────────────────────────┐
│  Step 3: 資料平面實際執行        │
│  Vertex AI 推論 / GCS 存取     │
└───────────────────────────────┘
```

關鍵優勢：即使攻擊者竊取了合法 Service Account 的 Token，只要發起請求的網路位置不在 Access Level 允許的 IP 範圍內，VPC-SC 仍會拒絕——這比純 IAM 架構多了一層防護。

### Vertex AI 區域端點的推論保證

Vertex AI 提供兩種 endpoint 類型：

```
全球端點（預設，不合規）        區域端點（合規）
         │                           │
         ▼                           ▼
  aiplatform.googleapis.com   asia-east1-aiplatform.googleapis.com
         │                           │
         ▼                           ▼
  ┌─────────────────┐         ┌─────────────────┐
  │ 全球負載均衡      │         │ asia-east1 只    │
  │ 可能路由至：      │         │ TPU/GPU 叢集     │
  │ - us-central1   │         │                 │
  │ - europe-west4  │         │ 推論中的 KV      │
  │ - asia-east1    │         │ Cache 留在此     │
  │ （不可預測）      │         │ region 的顯存   │
  └─────────────────┘         └─────────────────┘
       ❌ 合規風險                   ✅ 合規保證
```

使用 Python SDK 的正確設定：

```python
import vertexai
from vertexai.generative_models import GenerativeModel
from google.api_core.client_options import ClientOptions

# 不要這樣做（使用全球端點）
# vertexai.init(project=PROJECT_ID)

# 正確做法：顯式指定 region
client_options = ClientOptions(
    api_endpoint="asia-east1-aiplatform.googleapis.com"
)
vertexai.init(
    project=PROJECT_ID,
    location="asia-east1",  # 必須顯式設定
    client_options=client_options,
)
model = GenerativeModel("gemini-1.5-pro")
```

Batch Prediction 的正確設定（最常被遺忘的陷阱）：

```python
from google.cloud import aiplatform

job = aiplatform.BatchPredictionJob.create(
    job_display_name="compliance-batch-job",
    model_name=model.resource_name,
    gcs_source=f"gs://my-bucket/input/*.jsonl",
    gcs_destination_prefix=f"gs://my-bucket/output/",
    # 這兩行是合規關鍵，缺一不可
    location="asia-east1",          # 指定 Job 執行 region
    dedicated_resources_machine_type="n1-standard-4",
    # 不要使用 accelerator_type 的全球自動分配
)
```

### 加密層的地理邊界

Cloud KMS 的金鑰類型對合規的影響：

| 金鑰類型 | 儲存位置 | 加密作業執行地 | 合規等級 |
|---------|---------|-------------|---------|
| Global key | 全球分散 | 不確定 | 不合規 |
| Multi-region key（如 `asia`） | 多個 asia region | 可能跨境 | 風險 |
| Regional key（如 `asia-east1`） | 單一 region | 該 region | 合規 |
| CMEK + Cloud EKM | 客戶自有 HSM | 客戶機房 | 最高合規 |

Cloud KMS 加密呼叫在同 region 時的延遲約 0.5–2ms，幾乎不影響應用效能。相比之下，跨 region 呼叫 KMS 可能增加 20–80ms，且有合規風險。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

適用情境：POC 驗證、預算有限的新創、法規要求相對寬鬆的場景（如一般電商的用戶資料）。

**實作清單**：

1. 所有 Vertex AI API 呼叫顯式設定 `location="asia-east1"`，封裝在公司內部 SDK wrapper，防止個別工程師遺漏
2. GCS bucket 建立時設定 `--location=ASIA-EAST1`，啟用 `uniform bucket-level access` 防止 ACL 例外
3. Cloud KMS 金鑰建立在 `asia-east1`，選擇 `Regional` 而非 `Global` 或 `Multi-region`
4. 手動簽署 DPA，要求服務商承諾資料不用於模型訓練
5. 啟用 Cloud Audit Logs（至少 Admin Activity）

**可接受的妥協**：
- 無 VPC-SC（僅靠 IAM，有 token 洩漏風險）
- 無 Org Policy（管理員誤操作風險存在）
- 人工定期審查 Audit Log

**成本**：工程時間 1–2 天；無額外基礎設施費用；KMS 呼叫費用約 $0.03/10K 次。

**未解問題**：無法防止 Insider Threat；Batch Prediction 若忘記設 region 就破功；無法向嚴格監管機構提交可驗證稽核報告。

---

### Layer 2 — 生產就緒（Production-Ready）

適用情境：金融 FinTech、醫療 SaaS、有真實用戶的 B2B 產品，需要向 CTO 或法遵部門提交合規報告。

**在 Layer 1 基礎上新增**：

**Organization Policy 設定**：
```
constraints/gcp.resourceLocations:
  allowedValues:
    - "asia-east1"
    - "asia-east2"   # 容災備援（如需要）
  # 效果：嘗試在其他 region 建立資源時，API 直接回傳錯誤
  # 傳播時間：< 60 秒
```

**VPC Service Controls 部署流程**：
1. 建立服務邊界（Dry-run 模式），將 `Vertex AI`、`GCS`、`BigQuery`、`Cloud KMS`、`Cloud Build` 納入
2. 運行 dry-run 模式 **2 週**，收集 `DRYRUN_VIOLATION` 日誌
3. 分析違規模式，為合法存取建立 Access Level（企業 VPN IP 範圍、裝置合規 CertificateID）
4. 切換為 **enforced 模式**（切換後邊界執行延遲 < 5ms）
5. 設定告警：任何 `403 VPC_SC_VIOLATION` 觸發 PagerDuty P2 告警

**Audit Log 完整化**：
- 啟用 DATA_READ + DATA_WRITE（預設未啟用，需手動開啟）
- 匯出至 BigQuery dataset（region: asia-east1）
- 保留策略：30 天熱儲存（BigQuery）+ 90 天冷儲存（Cloud Storage Nearline）
- 自動化報表：每月產出「資料存取地理位置報告」供法遵部門審查

**成本/複雜度**：
- 工程時間：1–2 週（含 VPC-SC dry-run 期）
- VPC-SC 邊界本身免費；Access Context Manager 企業版 $6/用戶/月
- Audit Log 儲存：約 $50–200/月（依 API 呼叫量）
- Org Policy：免費

**解決的問題**：Insider Threat、誤配置跨 region、無法稽核、合法合規報告。

**未解問題**：雲端服務商仍持有底層硬體控制權；無法滿足「資料不離客戶機房」的政府級要求。

---

### Layer 3 — 企業級（Enterprise-Grade）

適用情境：政府機關、金控集團、醫院體系、HIPAA BAA 場景、需要向金管會或衛福部提交年度合規報告的機構。

**在 Layer 2 基礎上新增**：

**Distributed Cloud（GDC）部署**：
- Vertex AI 工作負載完全在客戶自有機房執行，雲端服務商操作人員無法存取資料
- 部署時間：硬體交付 + 設定約 8–12 週
- 初始投入：$200K–$500K（硬體 + 授權）
- 適用：中央銀行、國防部、醫療中心等最高主權要求場景

**Customer-Managed Encryption Keys（CMEK）+ External Key Manager（EKM）**：

```
應用程式加密請求
        │
        ▼
┌───────────────────────────────────┐
│  Cloud KMS（asia-east1 控制平面）  │
│  └─ 向 EKM 請求 KEK（Key Encryption Key）
└───────────────────────────────────┘
        │
        ▼（HTTPS to customer HSM）
┌───────────────────────────────────┐
│  客戶自有 HSM（Thales / AWS CloudHSM）
│  ├─ KEK 永不離開客戶機房           │
│  ├─ 雲端服務商無法解密任何資料      │
│  └─ 加密/解密操作在 HSM 內執行     │
└───────────────────────────────────┘
```

EKM 延遲額外開銷：約 10–30ms/次加密呼叫（相比 native KMS 的 0.5–2ms），需要在應用層做快取策略。

**Assured Workloads**：
- 提供 FedRAMP High、ITAR 等合規套件
- Access Approval：雲端服務商支援人員存取資料前需要客戶明確批准
- 限制支援工程師的地理位置（只允許台灣或指定國家的人員存取）

**第三方合規稽核**：
- 每年邀請 BSI、SGS 或 PricewaterhouseCoopers 進行技術控制驗證
- 產出 SOC 2 Type II 報告或 ISO 27701 認證
- 稽核範圍覆蓋：技術控制有效性 + 員工操作程序 + 事件回應能力

**成本/複雜度**：
- GDC：$200K–$500K 初始 + $50K–$100K/年維運
- CMEK + EKM：加密成本增加約 15%，需要 2–3 名 Security Engineer
- 第三方稽核：$50K–$150K/年
- 整體：只適合年營收 > $10M 或有法規強制要求的機構

---

## 四、為什麼選 X 不選 Y：關鍵技術決策

每個合規架構都有多個可選方案，以下是實際工程中最常面臨的決策點：

```
選擇                選 X 的理由                          不選 Y 的理由
────────────────────────────────────────────────────────────────────────────
VPC-SC              控制平面攔截，Token 洩漏也無法繞過      純 IAM：身份控制無法防止
vs 純 IAM           邊界違規有完整稽核日誌                 資料帶出邊界；無地理邊界概念
                    < 5ms 延遲開銷可忽略

Regional KMS        加密操作在指定 region 執行             Global KMS：加密位置不確定
vs Global KMS       金鑰物料不跨境複製                     Multi-region KMS：物料可能
                    CMEK 整合保留金鑰控制權                複製到邊界外 region

Vertex AI           推論中的 KV cache 留在指定 region      全球端點：路由不可預測，
區域端點             符合「處理地點」合規要求               KV cache 可能存在其他 region；
vs 全球端點          P99 延遲可預測（+ 8–15ms overhead）   無法向稽核機關證明推論地點

GDC on-premise      硬體在客戶機房，雲端人員無法存取        私有雲（自建 K8s）：需自行
vs 私有雲自建        仍可使用 Vertex AI 的 managed 服務     維護 ML 基礎設施，缺乏
                    符合最嚴格主權要求                     Vertex AI 的受管 SLA

Org Policy          60 秒全組織生效，防止誤配置             標籤管理（Tag-based policy）：
constraints         覆蓋所有 API（包含 IAM 建立資源）       可被有權限的工程師手動移除
vs 標籤管理          不依賴人工貼標籤流程                   標籤，執行力弱

Cloud Audit Logs    原生整合，無額外部署成本               自建 SIEM 收集：延遲高、
vs 自建 SIEM         DATA_READ/WRITE 顆粒度，含 resource    可能丟失日誌；雲端 API 的
收集                 location 欄位可直接稽核               metadata 不完整
```

**翻轉條件**（何時 Y 比 X 更合適）：

- **當監管要求超過雲端主權邊界**：VPC-SC 無法滿足「資料不離開客戶硬體」的要求時，GDC > VPC-SC
- **當成本是首要約束**：GDC 初始投入 > $200K 時，中小型醫療機構選擇 Regional Endpoint + VPC-SC 的 Layer 2 方案可在 $5K/月內解決 80% 的合規需求
- **當推論延遲是核心 SLA**：asia-east1 到終端用戶 RTT > 50ms 時，需要評估是否在鄰近 region（如 asia-northeast1 東京）建立備援端點——但這需要與法遵確認是否允許

---

## 五、稽核證據鏈的實務設計

合規架構的最終目的是讓稽核機關可以驗證「資料確實沒有離開指定地理區域」。以下是稽核證據鏈的完整設計：

```
事件發生
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloud Audit Logs（原始事件）                                 │
│  每筆記錄包含：                                               │
│  ├─ timestamp: "2026-06-08T10:23:45.123Z"                   │
│  ├─ principal: "serviceAccount:app@project.iam..."          │
│  ├─ resource.type: "aiplatform.googleapis.com/Endpoint"     │
│  ├─ resource.location: "asia-east1"  ← 稽核關鍵欄位         │
│  ├─ method: "PredictRequest"                                │
│  └─ requestMetadata.callerIp: "203.x.x.x"（VPN IP）        │
└─────────────────┬───────────────────────────────────────────┘
                  │ 匯出（Log Sink）
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  BigQuery（asia-east1 region）                               │
│  ├─ 即時查詢：任何 resource.location != "asia-east1" 的事件  │
│  ├─ 自動化報表：每日跨 region 存取為零的確認報告              │
│  └─ 30 天熱 + 90 天冷 + 3 年歸檔（Coldline）               │
└─────────────────┬───────────────────────────────────────────┘
                  │ 告警
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  監控與告警                                                   │
│  ├─ VPC_SC_VIOLATION → PagerDuty P2（5 分鐘內回應）          │
│  ├─ 跨 region API 呼叫 → PagerDuty P1（立即回應）            │
│  └─ 稽核 Log 中斷（Log Sink 失效）→ P2 告警                  │
└─────────────────────────────────────────────────────────────┘
```

**稽核報告產出**：每季向法遵部門提交 BigQuery 查詢結果，證明以下三點：
1. 所有 Vertex AI 推論請求的 `resource.location` 均為 `asia-east1`
2. 查詢期間無任何 `VPC_SC_VIOLATION` 成功繞過記錄
3. Audit Log 連續性（無日誌空洞，排除被刪除的可能性）

Cloud Audit Logs 的完整性保護：日誌一旦寫入後，即使 Project Owner 也無法刪除個別記錄（只能設定整體保留期限），這是向稽核機關證明「日誌未被竄改」的關鍵特性。

**實際稽核場景演練**：

台灣金管會要求銀行提交年度雲端使用合規報告。稽核員會問：「你的 AI 系統在去年 1 月 15 日 14:23 UTC+8 處理了客戶貸款申請資料，請證明這筆資料從未離開中華民國領土。」

強答流程：
1. 在 BigQuery 查詢該時間戳的 Audit Log 記錄，顯示 `resource.location = "asia-east1"`
2. 展示 VPC-SC 邊界設定記錄，確認當時邊界已生效（Org Policy 設定歷史）
3. 提交 Cloud KMS 的金鑰使用記錄，確認加密作業在 asia-east1 執行
4. 顯示網路流量記錄，確認所有 API 呼叫來源 IP 在核准 VPN 範圍內

這四份文件合在一起，就是完整的技術合規證據鏈。

---

## 六、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 只設 GCS bucket region，未設 Vertex AI location 參數 | LLM 推論在全球叢集執行，含敏感資料的 prompt 和 KV cache 可能存在於其他 region | 所有 Vertex AI API 呼叫顯式傳入 `location` 參數；封裝成公司內部 SDK wrapper 強制設定 |
| Batch Prediction Job 使用預設設定（未設 region） | Job 被調度到全球工作節點，資料暫存在非指定 region 的機器顯存中 | 在 `BatchPredictionJob.create()` 顯式設定 `location="asia-east1"`；加入 CI/CD 檢查 |
| VPC-SC 邊界未包含 Cloud Build / Cloud Functions / Pub/Sub | CI/CD 流水線或事件驅動架構成為資料出境的側道 | 盤點所有會接觸受保護資料的服務，全部納入服務邊界；使用 VPC-SC 的 `restricted services` 清單 |
| 使用 Multi-region KMS key（如 `asia`）而非 Regional key | 金鑰物料被複製到邊界外的 region（如東南亞），加密操作也可能在遠端執行 | 建立 `asia-east1` regional key；在 Org Policy 中加入 `constraints/gcp.disableCloudKMSCryptoKeyVersionExternalImport` 防止意外導入 |
| VPC-SC 跳過 dry-run 直接切換 enforced 模式 | 合法 API 呼叫（如 CI/CD、監控系統）被誤擋，生產服務中斷，回退需要時間 | 強制執行 2 週 dry-run 期；分析 `DRYRUN_VIOLATION` 日誌；為每類合法存取建立 Access Level 例外 |
| 只啟用 Admin Activity Audit Log，未啟用 Data Access Log | 稽核機關要求的「誰在何時存取了哪筆資料」無法提供，無法通過合規審計 | 明確啟用 `DATA_READ` 和 `DATA_WRITE`；事先估算日誌量（大型系統可達 GB/天），規劃 BigQuery 儲存成本 |
| 認為簽署 DPA 等於技術合規 | 合約保護在資料已跨境後才有效；實際資料外洩時的懲罰仍無法避免 | DPA 是必要條件，技術控制（VPC-SC + Org Policy + Region Pinning）是充分條件；兩者同時需要 |

---

## 七、與其他核心主題的關聯

- **IAM 與最小權限原則（Part 5）**：VPC-SC 是網路層圍籬，IAM 是身份層圍籬，兩者功能互補而非替代。VPC-SC 防止資料「從哪裡出去」，IAM 控制「誰能做什麼」；真實的合規架構兩層同時需要，單靠任一層都有風險。

- **LLM 推論架構與延遲優化（Part 6）**：選擇 asia-east1 區域端點時，需要評估相對台灣企業用戶的網路 RTT（約 5–15ms）是否在 SLA 預算內；如果選擇更合規但更遠的 region，推論 P99 延遲可能增加 80–120ms，影響用戶體驗，這是 Compliance vs Performance 的典型 tradeoff。

- **多租戶隔離（Part 11）**：金融機構的多行庫場景中，A 銀行的資料不能被 B 銀行的模型見到；這在 Sovereign AI 架構中需要每個租戶一個 VPC-SC 邊界 + 專屬 Vertex AI 端點，成本是單租戶架構的 N 倍，需要在商業模式層面決策。

- **安全事件回應（Part 15）**：VPC-SC 的 `403 VPC_SC_VIOLATION` 日誌是資料外洩嘗試的第一線偵測訊號；Audit Log 的保留策略（90 天熱、3 年冷）直接影響事後取證能力，也是 HIPAA Breach Notification Rule（60 天通報期）的基礎。

---

## 八、面試一句話（Killer Phrase）

> *「資料主權的核心挑戰是：LLM 推論預設在全球分散式 TPU 叢集執行，而金融醫療客戶需要的是可被稽核機關驗證的地理邊界保證，而非紙面承諾。我的做法是五層技術控制疊加：最底層的 Region Pinning 確保所有 Vertex AI API 呼叫顯式設定 location="asia-east1"——最常踩的陷阱是 Batch Prediction Job 若不設 region 欄位，預設會在全球工作節點執行，讓整套合規設計失效；第二層 VPC Service Controls 在控制平面攔截跨邊界 API 呼叫，執行延遲 < 5ms，即使持有合法 Token 的 Insider 也無法繞過；第三層 Organization Policy 的 constraints/gcp.resourceLocations 在 60 秒內全組織生效，防止誤配置；第四層 Cloud KMS regional key 搭配 CMEK 確保金鑰主權，雲端服務商無法解密；第五層 Cloud Audit Logs 的 DATA_READ/DATA_WRITE 提供帶時間戳的可驗證稽核鏈條。對於政府或金融主管機關要求「資料不離客戶機房」的場景，Distributed Cloud（GDC）是唯一讓 Vertex AI 工作負載完全在客戶自有硬體執行的方案，代價是 8–12 週部署時間和 $200K–$500K 初始投入。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-8-zh/) | [後一篇](/posts/fde-interview-core-topic-10-zh/) →
