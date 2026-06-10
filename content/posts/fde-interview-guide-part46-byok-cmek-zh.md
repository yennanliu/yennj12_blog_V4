---
title: "FDE 面試指南 Part 46：高規格金融業的數據無痕化與自主密鑰管理（BYOK / CMEK in GenAI）"
date: 2026-06-08T09:00:00+08:00
draft: false
weight: 46
description: "深度剖析金融業在 Vertex AI 場景下導入 BYOK/CMEK 的完整架構：Cloud KMS + Cloud EKM 信封加密、DEK/KEK 職責分離、Dedicated Interconnect 專線優化、HSM 合規到 Memory Enclave 記憶體保護，兼顧主權資安與 <50ms 極限性能。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "Security", "BYOK", "CMEK", "Vertex AI", "HSM", "Encryption", "Compliance", "FinTech"]
authors: ["yen"]
readTime: "27 min"
---

> 大多數工程師聽到「CMEK 合規」就只想到：把 Cloud KMS 打開、勾選客戶管理密鑰就完事了。
> 真正的挑戰在於：當 Vertex AI 向量搜索每秒發起 5,000 次 ANN 查詢、每次都要跨海解密時，
> 延遲從 30ms 暴增到 12 秒——合規達成了，系統卻癱瘓了。
> Staff FDE 的答案是：用信封加密的 DEK/KEK 分層，讓地端 HSM 只做密鑰授權，
> 日常解密在 GCP Memory Enclave 裡完成，真正做到主權資安與極限性能同時成立。

---

## 面試情境

> **面試官：** 某家公營銀行的 CISO 要求所有上傳到 Vertex AI 的 Embedding 向量和 LLM Context Cache 快照，加密密鑰必須由行內地端機房的 HSM 自主控管，絕對不能讓雲端供應商持有明文密鑰。但向量搜索的 SLA 是 P99 < 50ms，Context Cache 的命中率目標是 85%。你如何設計這套系統，讓合規與性能同時成立？

---

## 一、核心問題：為什麼 CMEK 在 GenAI 場景特別難

### 1.1 金融業的監管壓力

台灣金融監理局（FSC）、PCI DSS Level 1、以及個人資料保護法（PDPA）三重框架對金融業的加密要求達到史上最嚴格水準：

- **密鑰主權**：加密密鑰的控制權必須留在金融機構手中，雲端供應商不得持有明文 KEK
- **審計可追溯**：每一次密鑰使用（加密/解密/輪轉）必須留下不可竄改的操作日誌
- **密鑰隔離**：不同業務線（個人金融、企業金融、投資銀行）的密鑰必須完全隔離
- **快速撤銷**：監管機構要求在 15 分鐘內能夠撤銷任何密鑰的使用授權

### 1.2 GenAI 場景為什麼特別難

傳統資料庫的 CMEK 方案相對成熟，但 GenAI 帶來三個新挑戰：

**挑戰一：超高頻率的密鑰使用**
```
傳統 DB 查詢：   1,000 次/秒  →  每次密鑰操作可承受 2–5ms 開銷
Vertex AI ANN：  5,000 次/秒  →  每次密鑰操作只能承受 < 0.5ms 開銷
LLM Inference：  500 Token/秒 →  每個 Token 批次解密需要 < 1ms
```

**挑戰二：向量資料的特殊性**
Embedding 向量在加密後會改變其幾何拓撲，這意味著 ANN 搜索（近似最近鄰搜索）必須在解密後的明文空間進行，無法使用同態加密（Homomorphic Encryption）繞過此限制（目前同態加密的計算開銷是明文計算的 10,000 倍以上）。

**挑戰三：Context Cache 的生命週期管理**
LLM Context Cache 的有效期可能是分鐘到小時不等，密鑰輪轉週期必須與 Cache 生命週期協調，否則會出現用新密鑰試圖解開舊密鑰加密快照的錯誤。

### 1.3 張力點：合規 vs 性能

| 維度 | 純合規路線 | 純性能路線 | 需要解決的張力 |
|------|-----------|-----------|--------------|
| 密鑰位置 | 全部在地端 HSM | 全部在 GCP 記憶體 | 密鑰在哪裡？ |
| 解密位置 | 每次跨海解密 | GCP 本地解密 | 解密在哪裡？ |
| 延遲（P99） | 12,000ms | 30ms | 如何 < 50ms？ |
| 審計完整性 | 完整 | 無 | 日誌如何不漏？ |

答案在於：**讓地端 HSM 只做一件事——授權 DEK 的生成與輪轉；日常解密則在 GCP 的受保護記憶體邊界（Memory Enclave）裡完成。**

---

## 二、三個演進階段

### ╔══ Phase 1：POC / 法規沙盒（< 10K 用戶）══╗

**目標**：在 3 個月內通過 CISO 的概念驗證，證明 CMEK 技術上可行。

```
┌──────────────────────────────────────────────────────────────────┐
│                     Phase 1：POC 架構                            │
│                                                                  │
│  ┌─────────────────────────────────┐                            │
│  │         銀行地端機房             │                            │
│  │  ┌────────────────┐             │                            │
│  │  │  HSM           │             │                            │
│  │  │  (Thales Luna) │             │                            │
│  │  │  KEK 存放於此   │             │                            │
│  │  └────────┬───────┘             │                            │
│  │           │ 手動匯出 wrapped DEK  │                            │
│  └───────────┼─────────────────────┘                            │
│              │                                                   │
│              │ HTTPS（公網）                                      │
│              │                                                   │
│  ┌───────────▼─────────────────────────────────────────────────┐│
│  │                      GCP Project（Sandbox）                  ││
│  │  ┌──────────────┐    ┌──────────────┐   ┌────────────────┐ ││
│  │  │  Cloud KMS   │    │  Vertex AI   │   │  Vector Search  │ ││
│  │  │  (wrapped    │───▶│  Embedding   │──▶│  Index (CMEK)  │ ││
│  │  │   DEK 存放)   │    │  Generation  │   │                │ ││
│  │  └──────────────┘    └──────────────┘   └────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘

密鑰流：KEK（地端 HSM）→ 手動 wrap DEK → 上傳 Cloud KMS → Vertex AI 使用
審計：Cloud KMS Audit Log（基本版）
```

**Phase 1 新增元件**
- Cloud KMS：存放 wrapped DEK（Data Encryption Key）
- Vertex AI Vector Search：啟用 CMEK 選項
- 基本 Cloud Audit Logs：記錄 KMS 操作

**Phase 1 限制與問題**
- DEK 手動上傳：每次輪轉需要人工操作，7×24 無法自動化
- 公網傳輸：密鑰材料走公網 HTTPS，理論上有中間人攻擊風險
- 延遲：每次 ANN 查詢需要向 Cloud KMS 確認密鑰有效性，P99 ≈ 800ms（不可接受）
- 缺乏 VPC Service Controls：KMS 操作可能被誤用

**成本估算**
- Cloud KMS：$0.06/10,000 次密鑰操作 × 100,000 次/月 = $0.60/月
- 工程師手動作業成本：$2,000/月（DEK 輪轉維護）
- **月費合計：≈ $2,100（POC 規模）**

---

### ╔══ Phase 2：MVP / 生產就緒（10K–200K 用戶）══╗

**目標**：自動化 DEK 輪轉、引入 Cloud EKM 與 Dedicated Interconnect，P99 < 200ms。

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Phase 2：MVP 架構                               │
│                                                                      │
│  ┌──────────────────────────────────────┐                           │
│  │           銀行地端機房                │                           │
│  │  ┌────────────────────────────────┐  │                           │
│  │  │  HSM Cluster（主 + 備）         │  │                           │
│  │  │  ┌──────────┐ ┌──────────┐    │  │                           │
│  │  │  │  HSM-1   │ │  HSM-2   │    │  │                           │
│  │  │  │ (Active) │ │(Standby) │    │  │                           │
│  │  │  └──────────┘ └──────────┘    │  │                           │
│  │  │  FIPS 140-2 Level 3            │  │                           │
│  │  └────────────────┬───────────────┘  │                           │
│  │                   │                  │                           │
│  │  ┌────────────────▼───────────────┐  │                           │
│  │  │  Cloud EKM Proxy（on-prem）    │  │                           │
│  │  │  KeyAccessJustification 驗證   │  │                           │
│  │  └────────────────────────────────┘  │                           │
│  └────────────────────┬─────────────────┘                           │
│                       │                                             │
│              Dedicated Interconnect                                 │
│              （10 Gbps，延遲 < 5ms，99.99% SLA）                    │
│                       │                                             │
│  ┌────────────────────▼─────────────────────────────────────────┐  │
│  │                   GCP Project（Production）                    │  │
│  │                                                               │  │
│  │  ┌─────────────┐      ┌──────────────────────────────────┐   │  │
│  │  │  Cloud KMS  │      │     VPC Service Controls          │   │  │
│  │  │  + EKM      │      │     (KMS 操作白名單)               │   │  │
│  │  │  整合        │      └──────────────────────────────────┘   │  │
│  │  └──────┬──────┘                                              │  │
│  │         │                                                     │  │
│  │         ▼                                                     │  │
│  │  ┌──────────────┐    ┌──────────────┐   ┌────────────────┐   │  │
│  │  │  Vertex AI   │    │ Vector Search│   │ Context Cache  │   │  │
│  │  │  Embedding   │───▶│  Index       │   │  (CMEK)        │   │  │
│  │  │  API         │    │  (CMEK)      │   │                │   │  │
│  │  └──────────────┘    └──────────────┘   └────────────────┘   │  │
│  │                                                               │  │
│  │  ┌─────────────────────────────────────────────────────────┐ │  │
│  │  │  Cloud Audit Logs → Cloud Storage（WORM bucket）         │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

密鑰流：
1. KEK 永久存放於地端 HSM
2. Cloud EKM Proxy 自動化 DEK 生成請求
3. Wrapped DEK 透過 Interconnect 傳至 Cloud KMS
4. Vertex AI 透過 Cloud KMS 取得 Wrapped DEK 並在記憶體中解包使用
```

**Phase 2 新增元件（vs Phase 1）**
- Cloud EKM（External Key Manager）：自動化 EKM Proxy 與地端 HSM 的通訊
- Dedicated Interconnect：取代公網，延遲 < 5ms，99.99% SLA
- HSM Cluster（主備）：消除地端 HSM 單點故障
- VPC Service Controls：KMS 操作只允許白名單服務帳號呼叫
- Cloud Audit Logs → WORM Storage：不可竄改的審計日誌

**Phase 2 解決的問題**
- DEK 輪轉全自動化（每小時無人值守）
- 密鑰傳輸改為專線，消除公網風險
- P99 延遲降至 ≈ 180ms（仍未達標，因為每次 ANN 還是要確認 DEK）

**Phase 2 遺留問題**
- 每次向量查詢仍需向 Cloud KMS 確認密鑰有效性，高頻查詢下 KMS 成為瓶頸
- Context Cache 密鑰輪轉與 Cache 生命週期尚未協調

**成本估算（月費）**
- Dedicated Interconnect（10G）：$1,700/月
- Cloud KMS 操作（500萬次/月）：$30/月
- HSM Cluster 維護（地端）：$3,000/月
- **月費合計：≈ $4,730**

---

### ╔══ Phase 3：Scale / 企業級（200K–1M+ 用戶）══╗

**目標**：Memory Enclave 內 DEK 暫存、P99 < 50ms、密鑰輪轉與 Cache 生命週期完整協調。

```
┌────────────────────────────────────────────────────────────────────────┐
│                       Phase 3：企業級架構                               │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    銀行地端機房（金融級資安邊界）                   │  │
│  │                                                                  │  │
│  │  ┌─────────────────────────────────────────────────────────┐   │  │
│  │  │  HSM Cluster（N+1 冗餘，FIPS 140-2 Level 3）             │   │  │
│  │  │  KEK 生成 & 永久保管                                     │   │  │
│  │  │  策略：KEK-銀行業務線A / KEK-銀行業務線B / KEK-投行        │   │  │
│  │  └───────────────────────┬─────────────────────────────────┘   │  │
│  │                          │                                     │  │
│  │  ┌───────────────────────▼─────────────────────────────────┐   │  │
│  │  │  EKM Proxy Cluster（HA）                                 │   │  │
│  │  │  - KeyAccessJustification 強制審核                       │   │  │
│  │  │  - Reason Code 白名單（CUSTOMER_INITIATED_SUPPORT 等）   │   │  │
│  │  │  - 異常存取 → 自動告警 + 自動撤銷                         │   │  │
│  │  └───────────────────────┬─────────────────────────────────┘   │  │
│  └──────────────────────────┼──────────────────────────────────────┘  │
│                             │                                         │
│                  Dedicated Interconnect（雙路備援）                    │
│                  主路：10G VLAN A / 備路：10G VLAN B                  │
│                  延遲 < 5ms，99.99% SLA，BGP 自動切換                 │
│                             │                                         │
│  ┌──────────────────────────▼───────────────────────────────────────┐ │
│  │                    GCP Project（Enterprise）                      │ │
│  │                                                                  │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │  VPC Service Controls Perimeter                          │  │ │
│  │  │  （KMS / Vertex AI / BigQuery 統一邊界管控）               │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  │                                                                  │ │
│  │  ┌────────────────┐          ┌──────────────────────────────┐   │ │
│  │  │  Cloud KMS     │          │  Confidential Computing      │   │ │
│  │  │  + EKM 整合     │          │  VM（Memory Enclave）         │   │ │
│  │  │                │──DEK──▶  │                              │   │ │
│  │  │  每小時密鑰輪轉  │  wrap    │  DEK 暫存於受保護記憶體        │   │ │
│  │  │  自動排程       │          │  Intel TDX / AMD SEV         │   │ │
│  │  └────────────────┘          └────────────────┬─────────────┘   │ │
│  │                                               │                  │ │
│  │              ┌────────────────────────────────┘                  │ │
│  │              │        日常解密在 Enclave 內完成（< 1ms）           │ │
│  │              ▼                                                   │ │
│  │  ┌─────────────────┐   ┌──────────────────┐  ┌──────────────┐   │ │
│  │  │  Vertex AI      │   │  Vector Search   │  │  Context     │   │ │
│  │  │  Embedding API  │──▶│  Index（CMEK）   │  │  Cache(CMEK) │   │ │
│  │  │  5,000 QPS      │   │  P99 ANN < 30ms  │  │  命中率 87%  │   │ │
│  │  └─────────────────┘   └──────────────────┘  └──────────────┘   │ │
│  │                                                                  │ │
│  │  ┌──────────────────────────────────────────────────────────┐   │ │
│  │  │  審計日誌管線                                              │   │ │
│  │  │  Cloud KMS Audit → Pub/Sub → Dataflow → BigQuery WORM    │   │ │
│  │  │  Cloud Armor → WAF Log → 同上管線                         │   │ │
│  │  │  保存期限：7 年（FSC 合規要求）                             │   │ │
│  │  └──────────────────────────────────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘

密鑰流（Phase 3）：
① 每小時：地端 HSM 生成新 DEK → KEK 包裹 → Interconnect → Cloud KMS 存放
② 密鑰初始化：Cloud KMS 解包 DEK → 注入 Confidential VM Memory Enclave
③ 日常查詢：Vertex AI → Enclave 內 DEK 解密（< 1ms，無跨海）
④ 密鑰撤銷：EKM Proxy 接收指令 → 15 分鐘內 Enclave 清除 DEK 記憶體
```

**Phase 3 新增元件（vs Phase 2）**
- Confidential Computing VM（Intel TDX / AMD SEV）：Memory Enclave 保護 DEK
- EKM Proxy Cluster（HA）：KeyAccessJustification 強制審核，異常自動撤銷
- 雙路 Dedicated Interconnect：消除專線單點故障（各 10G，BGP 自動切換）
- 審計日誌管線：Pub/Sub → Dataflow → BigQuery WORM，7 年保存
- 多 KEK 策略：按業務線隔離密鑰空間

**Phase 3 解決的問題**
- P99 延遲從 180ms → **< 30ms**（ANN 查詢在 Enclave 本地解密）
- 密鑰撤銷時間從「需要人工操作」→ **15 分鐘自動撤銷**
- Context Cache 密鑰輪轉與 Cache TTL 完整協調
- 審計日誌全自動化，7 年不可竄改存檔

**Phase 3 成本估算（月費）**
- Dedicated Interconnect（雙路 10G）：$3,400/月
- Confidential VM（n2d-highmem-32 × 4）：$2,800/月
- Cloud KMS 操作（5,000萬次/月）：$300/月
- EKM Proxy Cluster 維護：$1,500/月
- 審計日誌管線（Dataflow + BigQuery）：$800/月
- **月費合計：≈ $8,800**

---

## 三、信封加密（Envelope Encryption）深度解析

信封加密是整個 BYOK/CMEK 架構的核心，必須理解每一層的職責。

### 3.1 兩層密鑰架構

```
┌─────────────────────────────────────────────────────────────────┐
│              信封加密（Envelope Encryption）層次                  │
│                                                                 │
│  Layer 1：KEK（Key Encryption Key，密鑰加密密鑰）                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  位置：地端 HSM（永不離開硬體邊界）                         │  │
│  │  算法：AES-256-GCM（FIPS 140-2 Level 3 核准）             │  │
│  │  職責：只做一件事——加密/解密 DEK                            │  │
│  │  存取：只有 EKM Proxy 持有授權憑證可呼叫                    │  │
│  └───────────────────────────┬──────────────────────────────┘  │
│                              │ KEK 包裹 DEK                    │
│                              ▼                                 │
│  Layer 2：DEK（Data Encryption Key，資料加密密鑰）               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  狀態 A：Wrapped DEK（被 KEK 加密的密文）                  │  │
│  │    位置：Cloud KMS 存放（安全，因為 KEK 在地端）            │  │
│  │    傳輸：可以走任何管道（明文 DEK 永遠不傳輸）              │  │
│  │                                                           │  │
│  │  狀態 B：Unwrapped DEK（明文，用於實際資料加解密）          │  │
│  │    位置：僅存在於 Confidential VM Memory Enclave           │  │
│  │    生命週期：1 小時（密鑰輪轉後清除）                       │  │
│  │    保護：Intel TDX / AMD SEV，防止 hypervisor 存取        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  Layer 3：實際資料（Vertex AI Embeddings / Context Cache）       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  加密：DEK 加密後存入 Vector Search Index / Cache Store    │  │
│  │  解密：Enclave 內 DEK 實時解密，外部不可見明文             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 為什麼 KEK 永遠不能離開地端 HSM

HSM 提供的保護不只是軟體層面的隔離，而是物理防篡改（Tamper-Evident）保護：

| 威脅向量 | 純軟體方案 | HSM 方案 |
|---------|-----------|---------|
| 記憶體轉儲攻擊 | KEK 明文暴露 | HSM 電路銷毀 |
| Root 帳號誤用 | KEK 可被導出 | 硬體物理阻止 |
| VM 快照攻擊 | KEK 留在快照中 | 快照無法包含 HSM |
| 供應鏈攻擊 | 韌體可被篡改 | FIPS 140-2 L3 認證 |
| 監管稽查 | 難以證明密鑰未洩漏 | 硬體日誌不可竄改 |

### 3.3 DEK 生命週期管理

```
Time →
00:00  密鑰輪轉觸發
  │
  ├── 地端 HSM 生成新 DEK（明文，在 HSM 內部）
  ├── HSM 用 KEK 加密 DEK → 得到 Wrapped DEK
  ├── Wrapped DEK 透過 Interconnect 送至 Cloud KMS
  ├── Cloud KMS 儲存 Wrapped DEK（版本號 v42）
  │
00:01  新 DEK 注入 Confidential VM Enclave
  ├── Enclave 向 Cloud KMS 請求 Wrapped DEK v42
  ├── 透過 EKM 呼叫地端 HSM 解包 DEK
  ├── 明文 DEK 注入 Enclave 保護記憶體區
  ├── 舊 DEK（v41）從 Enclave 記憶體清除（secure wipe）
  │
00:01–01:00  正常運作期
  ├── 所有 ANN 查詢：Enclave 內 DEK 解密（< 1ms，無網路跨越）
  ├── Context Cache 讀寫：同上
  ├── Cloud KMS Audit Log：記錄每次密鑰使用事件
  │
01:00  下一輪密鑰輪轉
  └── 重複上述流程，版本號 v43
```

---

## 四、Confidential Computing 與 Memory Enclave 技術細節

### 4.1 為什麼需要 Memory Enclave

傳統的 VM 即使 OS 和應用被加密，Hypervisor（雲端供應商控制）仍然理論上可以存取 VM 的記憶體。Memory Enclave 透過 CPU 硬體指令，建立一個即使 Hypervisor 也無法讀取的受保護記憶體區域。

```
┌─────────────────────────────────────────────────────────────┐
│              Confidential Computing 保護層次                  │
│                                                             │
│  雲端供應商（Hypervisor 層）                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Host OS / VMM                                      │   │
│  │  ✗ 無法讀取 Enclave 記憶體                           │   │
│  │  ✗ 無法截取 Enclave 的 CPU 暫存器                    │   │
│  └────────────────────────┬────────────────────────────┘   │
│                           │                                │
│  ┌────────────────────────▼────────────────────────────┐   │
│  │  Confidential VM（Intel TDX / AMD SEV-SNP）          │   │
│  │                                                     │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  Protected Memory Region（Enclave）           │   │   │
│  │  │  ┌──────────────────────────────────────┐   │   │   │
│  │  │  │  DEK（明文，AES-256）                 │   │   │   │
│  │  │  │  解密函數（加密運算在此執行）           │   │   │   │
│  │  │  │  ✓ 銀行的 CISO 可以遠端驗證此區域的    │   │   │   │
│  │  │  │    完整性（Remote Attestation）        │   │   │   │
│  │  │  └──────────────────────────────────────┘   │   │   │
│  │  │  Memory Encryption Engine（CPU 內建）         │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Remote Attestation：讓銀行驗證 Enclave 的完整性

Remote Attestation 允許銀行的 CISO 在不信任雲端供應商的前提下，數學上驗證 Enclave 的程式碼是否被篡改。

**驗證流程：**
1. Confidential VM 啟動時，CPU 生成一個硬體簽名的 Attestation Report
2. 報告包含：Enclave 的 code hash、記憶體佈局、CPU 型號與韌體版本
3. 銀行的安全團隊可以獨立驗證這個 Attestation Report，確認 Enclave 執行的是預期的程式碼
4. 只有在驗證通過後，EKM Proxy 才授權將 DEK 注入 Enclave

### 4.3 效能數字

| 操作 | 無 Enclave | 有 Enclave | 差距 |
|------|-----------|-----------|------|
| DEK 解密單次操作 | 0.3ms | 0.8ms | +0.5ms |
| ANN 向量搜索（含解密）| 28ms | 32ms | +4ms |
| Context Cache 讀取 | 5ms | 6ms | +1ms |
| Enclave 初始化（啟動時）| N/A | 3,200ms | 一次性 |
| 記憶體容量損失 | 0% | ≈ 6% | 可接受 |

**結論：** Enclave 對日常操作的延遲影響約 4–5ms，遠低於從 180ms 優化到 32ms 的整體增益。

---

## 五、Context Cache 的密鑰生命週期協調

### 5.1 問題陳述

Vertex AI Context Cache 允許將長 System Prompt（如銀行合規手冊 50,000 tokens）快取起來，避免每次請求重複計算，節省 75% 的輸入 token 費用。但 CMEK 下的密鑰輪轉帶來了新問題：

```
時間軸：
09:00  Context Cache 建立，用 DEK v10 加密
09:45  Cache TTL = 2 小時，應在 11:00 到期
10:00  密鑰輪轉，新 DEK v11 上線，DEK v10 從 Enclave 清除
10:30  使用者請求命中 Cache，Enclave 嘗試用 DEK v11 解密...
       ✗ 失敗！Cache 是用 DEK v10 加密的！
       → Cache Miss，重新生成 Cache（費用 $0.07/1K tokens）
       → 用戶感知：延遲從 180ms → 8,000ms（重新計算長 Context）
```

### 5.2 解決方案：DEK 版本感知的 Cache 標籤

```
Cache 元數據結構：
{
  "cache_id": "cache_20260608_abc123",
  "created_at": "2026-06-08T10:00:00Z",
  "ttl_seconds": 7200,
  "dek_version": "v10",           ← 記錄加密時的 DEK 版本
  "dek_expiry": "2026-06-08T11:00:00Z",  ← DEK 的過期時間
  "content_hash": "sha256:...",
  "encrypted_payload": "..."
}
```

**策略選擇：**

| 策略 | 做法 | 優點 | 缺點 |
|------|------|------|------|
| 策略 A：延遲輪轉 | DEK 輪轉等 Cache 過期後再進行 | Cache 命中率不受影響 | 密鑰輪轉可能延遲數小時，合規風險 |
| 策略 B：Cache 重加密 | 輪轉時用新 DEK 重新加密現有 Cache | 輪轉嚴格準時 | 輪轉時 CPU/IO 開銷大，可能影響性能 |
| 策略 C：雙版本 DEK | 舊 DEK 保留在 Enclave 直到 Cache 過期 | Cache 命中率維持，輪轉準時 | Enclave 需要同時維護兩個 DEK（記憶體稍增）|
| **策略 D（推薦）** | **DEK 設計 1 小時輪轉，Cache TTL 設計 55 分鐘** | **兩者週期對齊，無衝突** | **Cache 利用率略低，每小時需重建** |

**銀行場景推薦策略 D**：將 Context Cache TTL 設為 55 分鐘（略小於密鑰輪轉週期 60 分鐘），確保每次 Cache 過期時，使用中的 DEK 版本尚未輪轉，避免版本不匹配。每小時重建一次 Cache 的成本（50,000 tokens × $0.0000125 = $0.625/小時/用戶）在銀行場景下完全可接受。

---

## 六、審計日誌與合規框架

### 6.1 審計日誌架構

```
┌──────────────────────────────────────────────────────────────────┐
│                     審計日誌完整管線                               │
│                                                                  │
│  事件來源                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Cloud KMS   │  │  EKM Proxy   │  │  VPC Service Controls│   │
│  │  Audit Logs  │  │  Access Logs │  │  Violation Logs      │   │
│  │  （每次密鑰  │  │  （每次跨海   │  │  （每次越權存取）     │   │
│  │   操作記錄） │  │   請求記錄）  │  │                      │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                     │                │
│         └─────────────────┼─────────────────────┘                │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Cloud Pub/Sub（日誌匯聚，訊息保留 7 天作為緩衝）             │  │
│  └────────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Cloud Dataflow（流式處理）                                  │  │
│  │  - 欄位加密（審計日誌本身也受 CMEK 保護）                    │  │
│  │  - PII 遮罩（客戶 ID 雜湊化）                               │  │
│  │  - 異常偵測（非白名單服務帳號呼叫 KMS → 告警）               │  │
│  └────────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  BigQuery（WORM Policy，7 年保存）                           │  │
│  │  + Cloud Storage（冷備份，Coldline，7 年）                   │  │
│  │  FSC / PCI DSS 合規存檔                                     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 關鍵合規要求對應

| 合規框架 | 具體要求 | 架構對應方案 |
|---------|---------|------------|
| **PCI DSS Level 1** | 密鑰材料分離存放 | KEK 在地端 HSM，DEK 在 GCP Enclave |
| **PCI DSS Level 1** | 密鑰輪轉 ≤ 1 年（建議每年，銀行選每小時）| Cloud KMS 自動輪轉排程 |
| **FSC 金融監理** | 加密日誌 7 年保存 | BigQuery WORM + Coldline 冷備份 |
| **FSC 金融監理** | 15 分鐘內密鑰撤銷 | EKM Proxy 自動撤銷 + Enclave 清除 |
| **PDPA 個資法** | 個人資料存取記錄 | Cloud KMS Audit + VPC SC Violation Log |
| **FIPS 140-2 L3** | 密鑰硬體保護 | 地端 Thales Luna / Entrust HSM |
| **ISO 27001** | 存取控制與最小授權 | VPC Service Controls + IAM 條件授權 |

### 6.3 KeyAccessJustification：密鑰使用原因強制申報

Cloud EKM 的 KeyAccessJustification 功能要求每次密鑰存取都必須附帶使用原因代碼：

```python
# 合法的密鑰存取請求範例
{
  "justification": {
    "reason": "CUSTOMER_INITIATED_SUPPORT",
    "detail": "ANN vector search for user query - request_id: req_20260608_abc123"
  }
}

# 以下原因代碼在銀行場景被 EKM Proxy 拒絕：
# GOOGLE_INITIATED_REVIEW     → 雲端供應商主動審查，銀行不允許
# GOOGLE_INITIATED_SERVICE    → 雲端供應商服務維護，銀行不允許
# THIRD_PARTY_DATA_REQUEST    → 第三方資料請求，需要額外人工審核
```

這意味著即使有人在雲端供應商內部試圖以服務維護名義存取密鑰，地端 EKM Proxy 也會自動拒絕並告警。

---

## 七、Dedicated Interconnect 網路優化

### 7.1 為什麼不用 VPN 或公網

| 方案 | 延遲 | 頻寬 | 合規風險 | 成本/月 |
|------|------|------|---------|--------|
| 公網 HTTPS | 15–80ms | 不穩定 | 路由無法控制 | $0 |
| Cloud VPN | 5–20ms | 最高 3 Gbps | VPN 端點暴露 | $200 |
| **Dedicated Interconnect** | **< 5ms** | **10–100 Gbps** | **私有路由，無公網** | **$1,700** |
| Partner Interconnect | 5–15ms | 50 Mbps–10 Gbps | 依賴合作夥伴 | $500 |

**FSC 要求：** 密鑰材料傳輸不得走公網，因此 Dedicated Interconnect 是唯一合規選項。

### 7.2 雙路備援設計

```
銀行資料中心 A（主）                    銀行資料中心 B（備）
┌───────────────────┐                 ┌───────────────────┐
│  Edge Router A    │                 │  Edge Router B    │
│  BGP AS 64512     │                 │  BGP AS 64512     │
└─────────┬─────────┘                 └─────────┬─────────┘
          │                                     │
          │ VLAN 1001                            │ VLAN 1002
          │ 10 Gbps                              │ 10 Gbps
          │                                     │
┌─────────▼─────────────────────────────────────▼─────────┐
│              GCP Colocation（台北 / 香港 MeetMe Room）     │
│  ┌─────────────────┐          ┌─────────────────┐       │
│  │  GCP Edge       │          │  GCP Edge       │       │
│  │  Router（主）   │          │  Router（備）   │       │
│  └─────────┬───────┘          └─────────┬───────┘       │
│            └──────────┬─────────────────┘               │
│                       │                                 │
│                       ▼                                 │
│              GCP 內部網路（asia-east1）                  │
└──────────────────────────────────────────────────────────┘

故障切換：
- 主路斷線 → BGP 收斂時間 < 10 秒 → 流量自動切至備路
- 備路最大承載：10 Gbps（足夠覆蓋日常密鑰輪轉的頻寬需求）
- 密鑰輪轉每次傳輸的資料量：DEK（256 bits）≈ 32 bytes，頻寬消耗可忽略不計
```

---

## 八、為什麼選 X 不選 Y：關鍵技術決策對比

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|------------|--------------|----------------|
| **Cloud EKM + HSM** vs 純 Cloud KMS | 銀行 CISO 要求密鑰主權，KEK 不可離開地端；符合 FSC 監理要求；Cloud EKM 提供 KeyAccessJustification 防止雲端供應商私自存取 | 純 Cloud KMS 密鑰完全由雲端託管，法務部門直接否決；CISO 無法向監管機構證明密鑰主權 | 若監管框架放寬允許雲端託管 KEK（如使用 FIPS 140-3 認證的 Cloud HSM），可改用純 Cloud KMS 降低 $3,000/月 的地端成本 |
| **Confidential VM / Memory Enclave** vs 每次跨海解密 | 跨海解密延遲 12,000ms vs Enclave 本地解密 < 1ms；Enclave 有硬體保護，安全性不低於跨海方案 | 每次 ANN 查詢跨海解密在 5,000 QPS 下會讓地端 HSM 成為極端瓶頸；延遲 SLA 完全無法達成 | 若 QPS < 100 且 SLA 只要求 < 2 秒，可以接受跨海解密，省去 Confidential VM 成本 $2,800/月 |
| **Dedicated Interconnect** vs VPN | 延遲穩定 < 5ms（VPN 最差 20ms）；私有路由符合 FSC 密鑰傳輸不走公網的要求；99.99% SLA | VPN 走公網，FSC 不認可為密鑰材料傳輸管道；加密隧道端點有暴露風險；頻寬上限 3Gbps | 若預算嚴格限制，且可以向監管機構論證 VPN 加密層級等同 Interconnect，Partner Interconnect（$500/月）是中間選項 |
| **DEK/KEK 分層** vs 單一密鑰 | 單一密鑰需要每次操作都跨海取得明文密鑰，QPS 完全不可行；分層後 KEK 只在輪轉時使用，大幅降低跨海頻率 | 單一密鑰方案密鑰輪轉等同資料重加密，每次輪轉需要讀取所有向量資料（TB 級）；成本與時間不可接受 | 數據規模 < 1 GB 且 QPS < 10 的極小場景可考慮單一密鑰，但失去了信封加密的靈活性 |
| **每小時密鑰輪轉** vs 每日 | 金融業監管期望最小化密鑰暴露視窗；每小時輪轉意味著密鑰洩漏的爆炸半徑最多 1 小時的資料 | 每日輪轉若密鑰在 08:00 洩漏，攻擊者有 16 小時視窗；對金融業合規壓力不夠 | 若 Interconnect 頻寬嚴重受限，或 HSM 處理能力不足，可降級為每 4 小時輪轉，在性能和安全之間折衷 |
| **VPC Service Controls** vs 僅 IAM | VPC SC 在 IAM 之上增加一層網路邊界，即使 IAM 憑證洩漏，KMS 操作也不能從非白名單 IP 發起；提供 DLP 層面的保護 | 純 IAM 控制對憑證洩漏的防禦力不足；一旦 Service Account JSON 洩漏，攻擊者可從任何位置呼叫 KMS API | 若整個 GCP 用量非常小（< $500/月），VPC Service Controls 的最低費用（$500/月）可能不划算，此時強化 IAM Condition + Audit Alert 作為替代 |

---

## 九、KeyAccessJustification 拒絕策略深度分析

### 9.1 EKM Proxy 拒絕邏輯

銀行應配置 EKM Proxy 拒絕以下類型的密鑰存取請求，並自動觸發告警：

```
允許通過的 Justification Reason：
✓ CUSTOMER_INITIATED_SUPPORT    → 合法的 AI 查詢
✓ CUSTOMER_INITIATED_ACCESS     → 合法的資料存取
✓ GOOGLE_RESPONSE_TO_PRODUCTION_ALERT → 允許，但需人工審核確認

自動拒絕的 Reason：
✗ GOOGLE_INITIATED_REVIEW       → 雲端供應商主動審查，直接拒絕
✗ GOOGLE_INITIATED_SERVICE      → 雲端供應商服務維護，直接拒絕
✗ REASON_UNSPECIFIED            → 未填原因，直接拒絕
✗ THIRD_PARTY_DATA_REQUEST      → 第三方請求，需 CISO 人工授權
```

### 9.2 異常偵測與自動回應

| 異常事件 | 偵測方式 | 自動回應 | 回應時間 |
|---------|---------|---------|---------|
| 非白名單服務帳號呼叫 KMS | VPC SC Violation Log | 封鎖 + PagerDuty 告警 | < 30 秒 |
| 密鑰使用頻率異常（> 10,000 次/分鐘）| Cloud Monitoring | 限流 + 告警 | < 1 分鐘 |
| EKM Proxy 拒絕率 > 1% | Dataflow 串流分析 | 告警 + CISO Email | < 5 分鐘 |
| 密鑰撤銷指令未確認 | EKM Proxy 心跳 | 再發送 + 15 分鐘 Escalation | < 15 分鐘 |
| Interconnect 鏈路中斷 | Cloud Monitoring | BGP 自動切備路 | < 10 秒 |

---

## 十、系統效應：前後對比

### 10.1 性能指標對比

| 指標 | 無 CMEK（基線）| Phase 1（初版 CMEK）| Phase 3（完整架構）| 目標 SLA |
|------|--------------|-------------------|-------------------|---------|
| ANN 搜索 P50 | 15ms | 320ms | 28ms | < 30ms |
| ANN 搜索 P99 | 28ms | 12,000ms | 48ms | < 50ms |
| Context Cache 命中延遲 | 5ms | 890ms | 8ms | < 10ms |
| Cache 命中率 | 87% | 45%（密鑰版本不匹配）| 85% | > 80% |
| 密鑰撤銷時間 | N/A | 手動（數小時）| 12 分鐘 | < 15 分鐘 |
| 系統可用性（含密鑰輪轉）| 99.99% | 97.2%（輪轉時中斷）| 99.99% | > 99.95% |

### 10.2 成本對比

| 成本項目 | 無地端 HSM 方案 | Phase 3 完整 BYOK 方案 | 差距分析 |
|---------|--------------|----------------------|---------|
| Cloud KMS 費用/月 | $30 | $300 | +$270（操作頻率增加） |
| 地端 HSM 維護/月 | $0 | $3,000 | +$3,000（合規必要成本）|
| Dedicated Interconnect/月 | $0 | $3,400 | +$3,400（合規必要成本）|
| Confidential VM/月 | $0 | $2,800 | +$2,800（性能最佳化）|
| 合規風險罰款（年化，期望值）| $50,000 | $0 | -$50,000 |
| **年度總成本** | **$600 + $50,000（罰款）** | **$115,200** | **BYOK 方案實際更便宜** |

### 10.3 安全態勢對比

| 安全維度 | 無 BYOK | 有 BYOK (Phase 3) |
|---------|--------|------------------|
| 雲端供應商能否存取向量資料 | 理論上是 | 否（KEK 在地端 HSM）|
| 密鑰洩漏的爆炸半徑 | 所有歷史資料 | 最多 1 小時的資料 |
| 監管稽查能提供的證明 | 軟體日誌（可竄改）| 硬體 HSM 日誌（不可竄改）|
| 雲端供應商私自審查能力 | 存在（無記錄）| 不存在（EKM 拒絕）|
| 密鑰洩漏後的控制能力 | 需聯絡雲端支援 | 地端 HSM 直接撤銷，< 12 分鐘 |

---

## 十一、面試答題要點

**面試官問題：** 公營銀行要引入 Vertex AI 做 RAG 系統，CISO 要求向量 Embedding 和 Context Cache 的加密密鑰必須由地端 HSM 自主控管，但向量搜索的 P99 必須 < 50ms。請描述你的架構思路。

> *「這道題的核心張力是：讓地端 HSM 控管密鑰，但日常 5,000 QPS 的 ANN 查詢不能每次跨海解密——否則延遲從 30ms 暴增到 12 秒。我的解法是用信封加密的 DEK/KEK 分層：KEK 永久存放於地端 FIPS 140-2 Level 3 HSM，只在每小時密鑰輪轉時透過 Dedicated Interconnect（延遲 < 5ms，99.99% SLA）生成新的 wrapped DEK 並傳至 Cloud KMS；日常的向量搜索和 Cache 讀寫，由 Confidential VM 的 Memory Enclave 暫存 DEK 明文，在受硬體保護的邊界內完成解密，P99 延遲維持在 48ms。KeyAccessJustification 機制確保即使雲端供應商內部試圖以服務維護名義存取密鑰，地端 EKM Proxy 也會自動拒絕並在 30 秒內告警，密鑰撤銷指令在 12 分鐘內完成 Enclave 記憶體清除，符合 FSC 要求的 15 分鐘撤銷 SLA。Context Cache 的密鑰版本問題透過將 Cache TTL 設為 55 分鐘（略小於 60 分鐘輪轉週期）來解決，Cache 命中率維持在 85%，完整審計日誌透過 Pub/Sub → Dataflow → BigQuery WORM 管線保存 7 年，同時滿足 PCI DSS Level 1、PDPA 與 FSC 金融監理三套框架。」*

**評分要點檢核：**
- ✅ 識別核心張力（密鑰主權 vs 延遲性能）
- ✅ DEK/KEK 分層的信封加密原理
- ✅ Confidential VM / Memory Enclave 的作用
- ✅ Dedicated Interconnect 而非公網或 VPN
- ✅ 具體延遲數字（12,000ms → 48ms）
- ✅ Context Cache 密鑰版本協調方案
- ✅ KeyAccessJustification 防止雲端私自存取
- ✅ 密鑰撤銷 SLA（< 15 分鐘）
- ✅ 三大合規框架（PCI DSS / PDPA / FSC）

---

## 附錄：工程師實作清單

### 啟用 Vertex AI CMEK 的必要步驟

```bash
# 1. 建立 Cloud KMS KeyRing 和 CryptoKey
gcloud kms keyrings create bank-ai-keyring \
  --location asia-east1

gcloud kms keys create vertex-ai-dek \
  --keyring bank-ai-keyring \
  --location asia-east1 \
  --purpose encryption \
  --rotation-period 3600s \
  --next-rotation-time "2026-06-08T10:00:00Z"

# 2. 授權 Vertex AI Service Account 使用此 Key
gcloud kms keys add-iam-policy-binding vertex-ai-dek \
  --keyring bank-ai-keyring \
  --location asia-east1 \
  --member "serviceAccount:service-PROJECT_NUM@gcp-sa-aiplatform.iam.gserviceaccount.com" \
  --role roles/cloudkms.cryptoKeyEncrypterDecrypter

# 3. 建立 Vector Search Index 時指定 CMEK
# （在 Vertex AI Console 或 SDK 中指定 kmsKeyName）
```

### EKM 外部密鑰管理員設定要點

```yaml
# EKM Proxy 設定（地端部署）
ekm_config:
  hsm_endpoint: "hsm.bank.internal:2223"
  allowed_justification_reasons:
    - CUSTOMER_INITIATED_SUPPORT
    - CUSTOMER_INITIATED_ACCESS
  denied_reasons:
    - GOOGLE_INITIATED_REVIEW
    - GOOGLE_INITIATED_SERVICE
    - REASON_UNSPECIFIED
  auto_revoke_on_anomaly: true
  anomaly_threshold_per_minute: 10000
  alert_webhook: "https://pagerduty.bank.internal/alerts/kms"
```

---

## 系列導航

**系列導航**

← [Part 45：大規模 RAG 系統的向量檢索優化與重排序架構](/posts/fde-interview-guide-part45-rag-vector-reranking-zh/) | [Part 47：GenAI 應用的可觀測性與 LLM 評估框架](/posts/fde-interview-guide-part47-genai-observability-llm-eval-zh/) →
