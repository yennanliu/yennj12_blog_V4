---
title: "CMEK / BYOK 信封加密：自主密鑰管理與零信任加密架構"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析信封加密的 DEK/KEK 機制、Cloud KMS 與外部密鑰管理器（EKM）的取捨、Confidential Computing 封存與 Vertex AI CMEK 整合，掌握企業級零信任加密的三個實作層次。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Security", "CMEK", "Encryption", "HSM"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：CMEK（Customer-Managed Encryption Keys）是客戶掌控 KEK（Key Encryption Key）的信封加密架構——雲端服務商永遠只持有被加密的 DEK，而不持有明文 DEK，更不持有 KEK；即使雲端平台遭受內部威脅或法律強制，攻擊者仍無法在缺少客戶授權的情況下解密資料。**

---

## 一、為什麼面試官問這個

面試官問 CMEK / BYOK，實際上在測試三件事：

- **安全架構縱深**：候選人能否區分「平台代管密鑰（GMEK）」、「客戶代管密鑰（CMEK）」、「客戶自攜密鑰（BYOK / EKM）」三個層次的威脅模型差異？能否說清楚為什麼信封加密中 DEK 輪換不需要重新加密全部資料，只需要重新包裹 encrypted_DEK？
- **效能與安全的取捨**：如果每次推論都呼叫 KMS 解包 DEK，延遲會增加多少？如何用 Confidential Computing enclave 的 in-memory DEK 快取解決這個問題，而不破壞「明文 DEK 不落盤」的安全保證？
- **實際整合能力**：Vertex AI Vector Search、Context Cache、GCS 訓練資料如何各自掛載 CMEK？EKM 和 Dedicated Interconnect 在 BYOK 路徑中各自扮演什麼角色，兩者缺一不可嗎？

**弱答案長什麼樣：**「就用 KMS 加密就好了。」沒有提到信封加密的雙層結構（DEK + KEK）、DEK 不持久化的核心設計意圖，以及 KEK 調用頻率與推論延遲的量化關係。這種回答把 CMEK 等同於「把密鑰存在 KMS」，完全遺漏了密鑰控制權歸屬的問題。

**強答案長什麼樣：**從信封加密的 DEK/KEK 分層講起，說明明文 DEK 只在 Confidential Computing enclave 的記憶體中存活、每小時輪換（= 24 次 KMS 呼叫 / 天），與數百萬次推論相比開銷不到 0.003%，推論 p99 延遲影響 < 50ms。再點出 BYOK 透過 Dedicated Interconnect（< 5ms）將 KEK 留在客戶 on-premise HSM，讓雲端平台完全無法接觸 KEK——即使面對法院命令也無法交出金鑰。最後說明三層密鑰階層（Root KEK → Regional KEK → DEK）如何隔離故障域，以及這個設計的代價：HSM 可用性進入了推論服務的關鍵路徑。

---

## 二、核心原理與技術深度

### 信封加密的數學直覺

信封加密（Envelope Encryption）的核心洞察是：**用對稱金鑰加密資料，再用非對稱或更高層級的金鑰加密那把對稱金鑰**，兩把鑰匙分開存放，攻擊者必須同時攻破兩層才能讀取明文。

```
資料加密層（Data Encryption Key, DEK）
  ├── 演算法：AES-256-GCM（Authenticated Encryption）
  ├── 長度：256 bits（32 bytes）
  ├── 生命週期：每 session 或每 1 小時輪換（可設定）
  ├── 存放：encrypted_DEK 欄位，與密文資料並排儲存
  └── 明文 DEK：只在 Confidential VM 記憶體中，使用後丟棄

密鑰加密層（Key Encryption Key, KEK）
  ├── 演算法：RSA-4096（非對稱）或 AES-256（CMEK 對稱包裹）
  ├── 長度：4096 bits（RSA 模式）
  ├── 位置：Cloud KMS（CMEK）或 外部 HSM（BYOK / EKM）
  ├── 功能：只做 wrap（包裹 DEK）和 unwrap（解包 DEK）兩種操作
  └── 明文 KEK：永遠不離開 KMS / HSM 安全邊界
```

### 加密流程（寫入路徑）

```
原始資料（明文）
    │
    │ ① 生成隨機 AES-256 DEK（僅在記憶體中）
    │
    ├──[DEK 加密]──▶ 密文資料 ─────────────────────────────────┐
    │                                                            │
    │ ② 呼叫 KMS/HSM：wrap(DEK, KEK_reference)                 │
    │                                                            │
    └──[KEK 包裹]──▶ encrypted_DEK ──────────────────────────── ┤
                                                                 │
                                               ③ 一起儲存到 GCS/Spanner/Bigtable
```

加密完成後，記憶體中的明文 DEK 立即清零（memset to zero），不持久化到任何儲存體。

### 解密流程（讀取路徑）

```
讀取 encrypted_DEK（從 GCS metadata / DB 欄位）
    │
    ▼
④ 呼叫 KMS/HSM：unwrap(encrypted_DEK, KEK_reference)
    │  ← unwrap 在 KMS/HSM 安全邊界內執行，明文 KEK 不出邊界
    ▼
明文 DEK（在 Confidential VM 記憶體中）
    │
    ▼
⑤ AES-256-GCM 解密密文資料 → 明文資料
    │
    ▼
⑥ 推論 / 處理完成 → 明文 DEK 丟棄（不落盤）
```

關鍵點：整個流程中，**明文 KEK 永遠不離開 KMS/HSM 邊界**，**明文 DEK 永遠不落盤**，兩個「永遠不」構成了信封加密的核心安全保證。

### CMEK vs BYOK 架構對比

```
CMEK 路徑（KEK 在 Cloud KMS）
─────────────────────────────────────────────────────────────
 客戶 VPC 內
  ┌─────────────────────────────────────────────────────┐
  │  Vertex AI Inference Pod（Confidential VM / AMD SEV）│
  │  ┌─────────────────────────────────────────────┐    │
  │  │  encrypted_DEK（從 GCS 讀取）                │    │
  │  │       │ unwrap request（HTTPS）               │    │
  │  │       ▼                                      │    │
  │  │  Cloud KMS API ◀── IAM 授權檢查              │    │
  │  │  （KEK 保存於此，雲端平台管理）                │    │
  │  │       │ plaintext DEK（記憶體返回）             │    │
  │  │       ▼                                      │    │
  │  │  AES-256 解密 → 推論 → 清零 DEK              │    │
  │  └─────────────────────────────────────────────┘    │
  └─────────────────────────────────────────────────────┘
  威脅模型弱點：平台強制 or 內鬼可讀取 KEK

BYOK / EKM 路徑（KEK 在客戶 HSM）
─────────────────────────────────────────────────────────────
 客戶資料中心                        GCP 邊界
  ┌────────────────────┐            ┌────────────────────────┐
  │  on-premise HSM    │            │  Cloud EKM（代理層）    │
  │  （KEK 永遠在此）   │◀──────────▶│  不持有 KEK，只轉發     │
  │  Thales Luna /     │  Dedicated │  unwrap 請求 / 回應     │
  │  AWS CloudHSM      │  Interconnect └──────────┬──────────┘
  └────────────────────┘  < 5 ms 延遲             │ plaintext DEK
                                                  ▼
                                  Vertex AI Confidential VM
                                  （DEK 在記憶體，1hr TTL）
  安全優勢：平台無法接觸 KEK，即使收到法院命令也無法交出
```

### 三層密鑰階層（Enterprise-Grade）

```
Root KEK（客戶 on-premise HSM，FIPS 140-2 Level 3）
    │ wraps ──────────────────────────────────────┐
    ▼                                             │ 月/季輪換
Regional KEK（Cloud KMS，per-region 隔離）         │
    │ wraps ──────────────────────────────────────┘
    ▼                                             每小時輪換
DEK（AES-256-GCM，Confidential VM 記憶體，1hr TTL）
    │ encrypts
    ▼
實際資料（GCS object / Vector Search index / Context Cache / Spanner cell）
```

三層隔離的故障域優勢：
- Root KEK 洩露需要 HSM 物理入侵，極難；即使發生，Regional KEK 仍是屏障
- Regional KEK 輪換只影響該 region 的 DEK 重新包裹，不影響其他 region 服務
- DEK 每小時輪換，洩露視窗從 90 天（預設）縮短至 1 小時

### Vertex AI 整合範圍

CMEK 支援的 Vertex AI 資源：

```
┌────────────────────────────────────────────────────────┐
│  Vertex AI CMEK 支援範圍                                │
├────────────────────┬───────────────────────────────────┤
│  資源類型          │  備註                              │
├────────────────────┼───────────────────────────────────┤
│  Vector Search     │  index 檔案存於 GCS，掛 CMEK bucket│
│  Context Cache     │  快取的 prompt/response 受 KEK 保護│
│  Training Dataset  │  GCS 訓練資料、中間 checkpoint      │
│  Model Registry    │  fine-tuned model weights           │
│  Feature Store     │  embedding 向量特徵值               │
│  Prediction logs   │  推論輸入/輸出審計日誌              │
└────────────────────┴───────────────────────────────────┘
```

注意：CMEK 是**建立時**設定，資源建立後**無法**更換 KEK（必須重新建立資源）。這是一個常見的陷阱，需要在 Infra-as-Code 中提前規劃。

### Confidential Computing 的角色

Confidential Computing（機密計算）解決的是**記憶體層面的威脅**：即使 hypervisor（虛擬化層）被入侵或被平台內部人員存取，也無法讀取 VM 記憶體中的明文資料。

AMD SEV（Secure Encrypted Virtualization）的工作原理：

```
傳統 VM 記憶體模型
─────────────────────────────────────────────
  Host（hypervisor）
  ┌──────────────────────────────────────┐
  │  Guest VM 記憶體（明文）              │  ← hypervisor 可讀取
  │  ┌──────────────────────────────┐   │
  │  │  plaintext DEK  ← 危險       │   │
  │  │  推論輸入 / 輸出              │   │
  │  └──────────────────────────────┘   │
  └──────────────────────────────────────┘

AMD SEV Confidential VM 模型
─────────────────────────────────────────────
  Host（hypervisor）
  ┌──────────────────────────────────────┐
  │  Guest VM 記憶體（AES 加密）          │  ← hypervisor 看到的是密文
  │  ┌──────────────────────────────┐   │
  │  │  加密記憶體區塊               │   │
  │  └──────────────────────────────┘   │
  └──────────────────────────────────────┘
  
  CPU 硬體（AMD SEV 晶片）
  ┌──────────────────────────────────────┐
  │  記憶體加密引擎（MEE）               │
  │  每個 VM 有獨立的加密金鑰（VEK）     │
  │  VEK 在 CPU 內部生成，不對外暴露     │  ← 即使 root 也無法讀取
  └──────────────────────────────────────┘
```

AMD SEV 對 CMEK 架構的意義：plaintext DEK 在 Confidential VM 記憶體中，hypervisor 或平台管理人員無法提取。這讓「DEK 只在記憶體中，不落盤」的安全假設在硬體層面得到保障，而不僅僅是軟體策略。

### Key Access Justifications（密鑰存取理由）

這是 BYOK / EKM 架構中讓面試官眼睛一亮的細節。當 Vertex AI 服務發出 unwrap 請求時，Cloud KMS 會在請求中附加一個結構化的「理由字串」：

```
justification 範例：
{
  "type": "CUSTOMER_INITIATED_ACCESS",
  "resource": "projects/my-project/locations/us-central1/datasets/training-v2",
  "operation": "decrypt",
  "principalEmail": "vertex-sa@my-project.iam.gserviceaccount.com"
}
```

客戶 EKM 實作可以根據這個 justification 做自動化決策：

```
HSM 端策略引擎（偽代碼）
─────────────────────────────────────────────────────────
IF justification.type NOT IN ALLOWED_TYPES:
    REJECT → return 403

IF current_time NOT IN business_hours AND
   justification.type == "CUSTOMER_INITIATED_ACCESS":
    REJECT → return 403  # 非業務時間只允許系統自動化操作

IF justification.resource MATCHES /datasets/pii-.*/:
    REQUIRE_DUAL_APPROVAL → hold request, notify security team
    
ELSE:
    ALLOW → return decrypted DEK
─────────────────────────────────────────────────────────
```

這個機制讓客戶實現**事前拒絕**（而不只是事後稽核），是 CMEK 和 BYOK 最重要的差異之一。CMEK 下客戶只能看 Audit Logs（事後），BYOK 下客戶可以寫程式即時拒絕（事前）。

### 關鍵效能數字

| 指標 | 數值 | 說明 |
|------|------|------|
| Dedicated Interconnect 延遲 | < 5 ms | EKM unwrap 往返延遲 |
| Cloud KMS API 延遲 | 10–30 ms | CMEK unwrap（公網 HTTPS） |
| DEK 輪換頻率 | 1 次 / 小時 | = 24 次 KEK 呼叫 / 天 |
| 典型推論呼叫量 | 1,000,000 次 / 天 | 企業規模 |
| KEK 呼叫佔比 | 0.0024% | 24 / 1,000,000 |
| Confidential VM AMD SEV 開銷 | 2–5% CPU overhead | 加密記憶體訪問損耗 |
| AES-256-GCM 吞吐（AES-NI） | > 2 GB/s | 現代 x86 CPU 硬體加速 |
| 推論 p99 延遲影響（DEK 快取後） | < 50 ms 額外 | 不快取則每次 +10–30ms |
| DEK 快取 TTL | 1 小時 | 與輪換頻率一致 |

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標：最快啟動，滿足基本合規，POC / 初期生產**

具體做法：
- 在 Cloud KMS 建立 Customer-Managed KEK（軟體保護，非 HSM）
- 在 GCS bucket 設定 `defaultKmsKeyName`，新物件自動套用 CMEK
- Vertex AI Dataset 和 Vector Search index 建立時指定 `encryptionSpec.kmsKeyName`
- 保留預設 DEK 輪換政策（90 天）
- 不啟用 Confidential VM（先不管記憶體加密）

**解決的問題：**
- 雲端平台員工若未持有 KMS 密鑰 IAM 權限，無法解讀原始資料
- 滿足 HIPAA Safe Harbor、SOC 2 Type II 基礎稽核要求
- 比平台預設加密（GMEK）多一層客戶控制

**遺留的問題：**
- KEK 由雲端 KMS 管理，平台理論上仍可存取
- DEK 輪換 90 天，洩露視窗長
- Confidential VM 未啟用，記憶體中的明文資料仍有被 hypervisor 讀取的風險
- 不適用「不信任雲端平台」的威脅模型

**成本 / 複雜度：**
- Cloud KMS：~$1 / 密鑰版本 / 月 + $0.03 / 10,000 操作
- 實作時間：1–2 天（主要是 Terraform / IaC 修改）
- 無額外 VM 費用

### Layer 2 — 生產就緒（Production-Ready）

**目標：真實流量安全，團隊可持續維運，適合處理 PII 或受法規約束的資料**

在 Layer 1 基礎上新增：

**密鑰管理強化：**
- DEK 輪換頻率縮短至 **1 小時**（洩露視窗從 90 天降至 1 小時）
- 設定 KMS 密鑰銷毀保護（`destroyScheduledDuration` 設為 30 天）
- 啟用 Cloud KMS 自動密鑰版本輪換，舊版本保留 90 天後自動禁用

**計算層加固：**
- 啟用 **Confidential VM（AMD SEV）**，明文 DEK 只在加密記憶體中存活
- Confidential Space 搭配 Workload Identity Federation，確保只有特定容器映像才能取得 KMS 授權

**可觀測性：**
- 所有 KMS unwrap 操作 → Cloud Audit Logs（Data Access 類型）
- 建立 Log-based Alert：偵測異常高頻的 unwrap 請求（可能代表 DEK 快取失效或被暴力使用）
- 不同服務使用**不同 DEK**（Vector Search、Context Cache、Training Data 各一把）

**解決的問題：**
- DEK 洩露視窗：90 天 → 1 小時
- 記憶體明文資料：hypervisor 無法讀取（AMD SEV 加密記憶體）
- 誤刪密鑰：有 30 天緩衝期，可恢復
- 密鑰使用全程可稽核

**遺留的問題：**
- KEK 仍在雲端 KMS，FedRAMP High 或 FIPS 140-2 Level 3 要求未達到
- 若收到政府強制令，雲端平台仍可透過 KMS 存取 KEK

**成本 / 複雜度：**
- Confidential VM：+5–10% VM 費用（AMD SEV 開銷）
- Audit Logs ingestion：$0.01 / GB（超出免費額度後）
- 實作時間：1–2 週（IAM 精調 + Confidential VM 移轉 + 監控）

### Layer 3 — 企業級（Enterprise-Grade）

**目標：完整合規（FedRAMP High / FIPS 140-2 Level 3 / 金融合規）、零信任、KEK 主權完整回歸客戶**

在 Layer 2 基礎上新增：

**密鑰主權完全轉移：**
- **Cloud EKM（External Key Manager）**：KEK 移至客戶 on-premise HSM（Thales Luna Network HSM 7 / Utimaco / AWS CloudHSM）
- Cloud EKM 只做 API 橋接，不持有任何密鑰材料
- Cloud KMS 的 `protectionLevel: EXTERNAL` 模式

**網路隔離：**
- **Dedicated Interconnect**（10 Gbps 或 100 Gbps 專用光纖）確保 EKM unwrap 請求不走公網
- Cloud Private Service Connect 讓 KMS/EKM API 呼叫走 RFC 1918 位址
- unwrap 請求 latency：< 5 ms（Dedicated Interconnect），vs 公網 ~50–100 ms

**密鑰使用策略（Key Access Justifications）：**
- 每次 unwrap 請求需附帶使用理由（justification）
- 客戶 HSM 端的 EKM 實作可根據 justification 拒絕請求
- 例：非業務時間的 unwrap 請求自動拒絕，或需要第二個審批人

**合規與稽核：**
- 定期 **Key Ceremony**（密鑰儀式）確保 Root KEK 生成過程符合 FIPS 140-2 Level 3 / SOX 規範
- HSM 稽核日誌 + Cloud Audit Logs 雙重不可篡改記錄
- 密鑰使用策略版本控制，每次政策變更需要雙人審核（Four-eyes principle）

**解決的問題：**
- 雲端平台即使面對法院命令，也無法交出 KEK（KEK 從未離開客戶 HSM）
- 達到 FedRAMP High、FIPS 140-2 Level 3、ISO 27001 Annex A.10 要求
- 客戶可即時「拔插頭」：拒絕所有 unwrap 請求 = 雲端資料立即不可存取

**新增的代價（重要取捨）：**
- HSM 可用性進入推論服務關鍵路徑：HSM 宕機 = DEK 無法解包 = 推論服務降級
- 需要 HSM HA（Active-Active 雙 HSM）+ 緊急存取程序
- DEK 快取 TTL（1 小時）提供了 1 小時的 HSM 斷線容忍視窗
- Dedicated Interconnect SLA 99.99%（需要 redundant interconnect）

**成本 / 複雜度：**
- HSM 設備：$20,000–$50,000 一次性（取決於廠牌和容量）
- Dedicated Interconnect：~$1,700–$2,000 / 月（10 Gbps 電路，依 region 不同）
- HSM 維運工程師：通常需要專職 PKI/HSM 工程師
- 實作時間：2–4 個月（包含 HSM 採購、驗收、Key Ceremony、EKM 整合）

---

## 四、為什麼選 X 不選 Y

每個非顯而易見的設計決策，都要能說清楚「翻轉條件」——什麼時候應該換另一個選擇。

### GMEK vs CMEK vs BYOK 選擇矩陣

```
選擇         適用條件                          不選的理由
──────────────────────────────────────────────────────────────────────
GMEK         開發 / 測試環境；無法規要求        平台代管 KEK，客戶無密鑰控制權
（平台代管）  成本：$0 額外費用                 稽核時無法證明「平台無法讀取」

CMEK         生產環境；HIPAA / SOC 2 要求      KEK 在雲端 KMS，平台技術上可存取
（Cloud KMS） 成本：$1/key/月 + KMS API 費用   無法達到「不信任平台」的威脅模型
             翻轉條件 → 需要 FedRAMP High 時升 BYOK

BYOK / EKM   金融 / 醫療 / 政府 / FedRAMP High KEK 永不離開客戶 HSM，但 HSM 可
（外部 HSM）  要求；不信任雲端平台的威脅模型    用性加入推論關鍵路徑
             成本：$20K+ HSM + $1700/月 Interconnect
             翻轉條件 → 若 HSM HA 複雜度超過風險收益，考慮 CMEK + Key Access Policy
```

### AES-256-GCM vs AES-256-CBC 作為 DEK 演算法

```
選擇             選 GCM 的理由                      不選 CBC 的理由
──────────────────────────────────────────────────────────────────────
AES-256-GCM      Authenticated Encryption：加密同時   CBC 只提供機密性，不提供完整性
（DEK 演算法）    提供完整性驗證（GHASH tag）          攻擊者可翻轉密文位元而不被偵測
                 無 padding：不受 Padding Oracle 攻擊  需要額外 HMAC 做完整性保護
                 硬體加速（AES-NI + CLMUL）> 2GB/s    
                 翻轉條件 → 幾乎永遠選 GCM；CBC 只在
                 遺留系統相容性要求下才出現
```

### Dedicated Interconnect vs VPN 作為 EKM 連線

```
選擇                    選 Interconnect 的理由         不選 VPN 的理由
──────────────────────────────────────────────────────────────────────
Dedicated Interconnect  < 5ms 延遲，穩定低抖動          VPN：50–150ms，高抖動
（EKM 連線方式）         99.99% SLA（redundant pair）    VPN 透過公網，流量可被 ISP 觀察
                        10/100 Gbps 頻寬，不受 ISP 影響 VPN IPSec 加解密有 CPU 開銷
                        翻轉條件 → 如果 EKM unwrap 頻率
                        < 100 次/天（非推論場景），VPN
                        延遲影響可接受，成本優先時選 VPN

Cloud VPN               較低成本（$0.04/GB + 隧道費）   unwrap 延遲 50–150ms，影響 p99
                        適合低頻 KEK 操作（如批次輪換）  不適合推論服務的實時 EKM 路徑
```

### RSA-4096 vs AES-256 作為 KEK 演算法

```
選擇          選 RSA-4096 的理由                     不選 AES-256 KEK 的理由
──────────────────────────────────────────────────────────────────────
RSA-4096      非對稱加密：公鑰可分發給多個加密者       AES KEK 需要安全通道傳遞密鑰
（KEK）       適合「多方加密，一方解密」場景            對稱密鑰分發本身是安全問題
              HSM 硬體原生支援（PKCS#11 介面）         
              翻轉條件 → 若只有單一信任方的封閉系統，
              AES-256 KEK 效能更好（wrap/unwrap < 1ms）

AES-256-GCM  wrap/unwrap 速度極快（< 0.1ms）         需要安全信道預分發 KEK；
（KEK）       適合高頻 DEK 輪換場景                    不適合多租戶或多方信任場景
```

### 症狀 → 診斷鏈

實際系統中，CMEK 問題的症狀通常是：

```
症狀：Vector Search 查詢突然返回 403 PERMISSION_DENIED
  │
  ├── 可能原因 A：Service Account 的 KMS 解密 IAM 已被撤銷
  │       診斷：Cloud Audit Logs 查 cloudkms.cryptoKeyVersions.useToDecrypt
  │             查看最近 IAM 變更記錄
  │
  ├── 可能原因 B：KEK 版本已被銷毀，但 encrypted_DEK 仍使用舊版本
  │       診斷：KMS 密鑰版本狀態 → 是否有 DESTROYED 版本？
  │             對應資源的建立時間 vs 密鑰版本銷毀時間
  │
  └── 可能原因 C：EKM（BYOK 路徑）的 HSM 不可用
          診斷：Cloud EKM 健康狀態 → EKM connection 是否 ACTIVE？
                Dedicated Interconnect 狀態 → BGP 會話是否 ESTABLISHED？
                HSM 端日誌 → 是否有 connection reset？

症狀：推論 p99 延遲從 200ms 爆增至 500ms+
  │
  └── CMEK unwrap 路徑問題：DEK 快取失效，每次推論都觸發 KMS 呼叫
          診斷：Cloud KMS API 指標 → cryptoKeyVersions.asymmetricDecrypt QPS
                若 QPS ≈ 推論 QPS，代表快取完全失效
          修復：檢查 Confidential VM 記憶體壓力（DEK 快取被 evict）；
                調整快取 TTL 或增加 VM 記憶體配額
```

---

## 五、常見錯誤與陷阱（實戰）

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 直接存放明文 DEK 到資料庫或設定檔 | DEK 洩露 = 全部加密資料被解密，信封加密意義全失 | DEK 只存在 Confidential VM 記憶體；落盤的永遠只是 encrypted_DEK |
| KEK 輪換後未重新包裹既有 encrypted_DEK | 舊版本 KEK 被禁用後，所有用舊 KEK 包裹的 DEK 無法解包，資料永久無法存取 | 輪換 KEK 前，先對所有活躍 encrypted_DEK 執行 re-wrap；或保留舊版本 KEK 至所有資料遷移完成 |
| 刪除 KMS 密鑰版本後才發現資料無法解密 | 資料永久丟失，無法恢復 | 啟用 `destroyScheduledDuration`（建議 30 天）；刪除前用 DLP 掃描確認無依賴資料 |
| 所有服務共用同一個 DEK | 一個服務洩露 DEK（例如記憶體 dump），所有服務資料全部曝光 | 按資源類型分配獨立 DEK：Context Cache 一把、Vector Search 一把、Training Data 一把 |
| 誤以為 CMEK = 雲端平台完全無法存取 | 規劃時安全假設過強，實際威脅模型仍有漏洞 | CMEK 下 KEK 在 Cloud KMS，平台技術上可存取；要達到平台無法存取，必須使用 EKM（BYOK） |
| EKM unwrap 走公網 HTTPS | 延遲不穩（50–200ms，影響 p99）；暴露 access pattern（雖不含 KEK 明文，但頻率可被觀察） | 強制使用 Dedicated Interconnect；Cloud Private Service Connect 讓路徑完全私有 |
| 資源建立後才想補設 CMEK | Vertex AI 資源的 `encryptionSpec` 建立後不可修改，必須刪除重建 | 在 Terraform 模板中將 `kmsKeyName` 設為必填參數，PR review 時強制檢查 |

---

## 六、與其他核心主題的關聯

- **Part 8（PII 去識別化）**：PII tokenization vault（token ↔ PII 映射表）本身存於資料庫，必須用 CMEK 保護這張表。若映射表洩露，整個 pseudonymization 方案失效——CMEK 是 PII 保護的最底層護欄，兩個主題必須配合設計。

- **Part 6（Prompt Injection 防禦）**：系統 prompt 若含有 API token 或密鑰片段（這是常見的開發疏失），並且這些 prompt 被快取到 Context Cache，則 Context Cache 的 CMEK 設定直接決定了這些秘密的安全邊界。CMEK 是 prompt security 的儲存層保護。

- **Part 3（State Machine / DAG）**：長期執行的 Agent workflow 的中間狀態（checkpoint）若存入 Spanner 或 GCS，未套用 CMEK 的 checkpoint 等同於對話歷史裸奔。分散式狀態管理的設計必須把加密範圍一起規劃，不能事後補掛。

- **FDE Guide Part 31（ADK 深度）**：ADK 呼叫外部工具時，工具回傳值可能含業務機密並被 Memory Store 快取；快取層的 CMEK 範圍若未在設計文件中明確標注，會在合規審計時被標記為「未知加密狀態」的資料流。ADK agent 的架構設計圖應包含 CMEK 覆蓋範圍標注。

---

## 七、面試一句話（Killer Phrase）

> *「CMEK 的核心設計意圖是把密鑰控制權和資料控制權分開：雲端平台持有加密後的 DEK（encrypted_DEK），但只有客戶的 KEK 能解開它——明文 DEK 只在 Confidential Computing enclave 的記憶體中短暫存活（TTL 1 小時），解密完畢立即清零，永不落盤。BYOK 再進一步，把 KEK 本身也移到客戶 on-premise HSM，透過 Cloud EKM 和 Dedicated Interconnect（往返延遲 < 5ms）代理 unwrap 請求，讓雲端平台即使面對法院命令也無法交出 KEK。效能上，KEK 每小時只需調用一次（= 24 次 / 天），與數百萬次推論相比開銷不到 0.003%，推論 p99 延遲幾乎不受影響。最關鍵的取捨是：EKM 把密鑰主權還給客戶，但也把 HSM 可用性加入了推論服務的關鍵路徑——HSM 宕機等於整個推論管線無法解密新 DEK，因此 HSM Active-Active HA 設計和 DEK 快取 TTL 必須一起規劃，而不是分開考量。」*

---

**系列導航**

← [前一篇：Part 9](/posts/fde-interview-core-topic-9-zh/) | [後一篇：Part 11](/posts/fde-interview-core-topic-11-zh/) →
