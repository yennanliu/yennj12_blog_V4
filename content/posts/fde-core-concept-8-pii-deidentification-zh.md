---
title: "FDE core topic - PII 去識別化與格式保留加密：資料進入 AI 管線前的隱私護欄"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析 PII 去識別化光譜、格式保留加密（FPE）原理、Cloud Sensitive Data Protection 整合，以及 AI 管線中隱私護欄的三個實作層次。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Security", "PII", "DLP", "Compliance"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：PII 去識別化是在資料進入 LLM 嵌入或推論管線之前，透過抑制、偽名化或格式保留加密，將個人識別資訊轉化為不可直接識別的形式，同時保留資料在分析和 JOIN 場景中的可用性。**

---

## 一、為什麼面試官問這個

面試官問 PII 去識別化，實際上在測試三件事：

- **法規意識 vs 技術深度**：候選人能否區分「符合 GDPR 的匿名化」與「只是改欄位名稱」的差異？能否說出匿名化後為什麼不能反向推導，以及 k-匿名性、差分隱私如何提供數學保證？
- **系統設計能力**：AI 管線中 DLP 掃描要放在 embedding 之前還是之後？tokenization 要在哪一層做？Outbound LLM response 還需要反向還原嗎？如何在不破壞語意的前提下讓 LLM 仍然能有效推論？
- **取捨判斷**：anonymization 讓 JOIN 斷掉，pseudonymization 保住 JOIN 但還需要同意機制——什麼場景選哪個？DEK 洩漏後如何在技術層面執行「被遺忘權」？

**面試情境（面試官會這樣問）：**

你正在為一家醫療平台設計 AI 問診助理。用戶提問「我的電話是 0912-345-678，身分證 A123456789，最近診斷出糖尿病，應該怎麼吃？」整段文字要送進 LLM。你的架構如何在保護 PII 的前提下，讓 LLM 仍能給出有意義的醫療建議？同時這些資料未來還要做跨科別的統計分析，你如何設計？

**弱答案長什麼樣：**「就把姓名欄位刪掉，或者用星號遮住就好了。」沒有提到 quasi-identifier 重新識別風險、FPE 可逆性與密鑰管理，也不知道 DLP 掃描延遲對管線吞吐量的影響，更沒有提到 outbound 掃描。

**強答案長什麼樣：**從 PII 分類型講到偵測手段（regex + ML hybrid），再到 inbound tokenize → embed → store、outbound LLM response → reverse tokenize → return 的雙向管線，並指出 FPE 的確定性讓跨科別統計 JOIN 仍可行，最後用具體數字收尾：「Cloud DLP 掃描約 30ms/KB，FPE tokenization < 1ms/field，整體管線 p99 < 200ms 仍可達標。」

---

## 二、核心原理與技術深度

### PII 的三個類別與重新識別風險

```
┌────────────────────────────────────────────────────────────────┐
│  PII 分類光譜                                                   │
│                                                                │
│  直接識別符              準識別符               敏感屬性        │
│  (Direct Identifiers)  (Quasi-Identifiers)  (Sensitive Attr.) │
│  ──────────────────    ─────────────────    ───────────────── │
│  姓名                  郵遞區號              病歷診斷           │
│  身份證字號            年齡                  財務資料           │
│  電話號碼              性別                  宗教信仰           │
│  Email                 職業                  種族              │
│  生物特徵              IP 位址               政治傾向           │
│                                                                │
│  單一欄位即可識別        組合可識別：           本身敏感，         │
│  → 必須最高優先處理      zip+age+gender        即使無法識別身份   │
│                         → 87% 可唯一識別       也受法規保護      │
│                           美國人（Sweeney）                    │
└────────────────────────────────────────────────────────────────┘
```

Latanya Sweeney 1997 年的研究顯示，僅用郵遞區號、出生年月日、性別三個欄位，就能唯一識別美國 87% 的人口。這個數字之所以重要：即使一份資料集把姓名、電話全刪掉，留著這三個欄位，法律上仍然可能算個人資料。面試中能說出這個數字並解釋其含義的候選人非常少，卻是區分「真的懂」與「背術語」的關鍵分水嶺。

**k-匿名性（k-Anonymity）的數學意義：**
一個資料集滿足 k-匿名性，代表每一條記錄都至少和另外 k-1 條記錄的準識別符組合完全相同。當 k = 5，即使攻擊者知道某人在資料集中，也有至少 5 個候選人，無法確定是哪一個。GDPR safe harbor 通常要求 k ≥ 5，醫療資料建議 k ≥ 10。

### 去識別化光譜與技術取捨

```
高可用性 ◄──────────────────────────────────────────────► 高隱私保護
         │              │               │               │
      Suppression  Pseudonymization  Anonymization  Synthetic Data
      （抑制）      （偽名化）         （匿名化）       （合成資料）
         │              │               │               │
      刪除欄位      FPE token 替換    不可逆移除        生成統計
      最快實作      確定性可逆         k-匿名性保證      相似假資料
      損失語意      需 DEK 解密        GDPR safe-       保留統計分布
      脈絡          仍算個人資料        harbor            無原始個資
```

四種手段的核心取捨：

| 方法 | 可逆性 | JOIN 能力 | GDPR 分類 | 典型場景 | 翻轉條件 |
|------|--------|-----------|-----------|---------|---------|
| Suppression | 否 | 否 | 免於限制 | 完全不需該欄位 | 欄位有分析價值時改用偽名化 |
| Pseudonymization | 是（需 DEK） | 是（token 一致） | 仍屬個人資料 | AI 推論、跨表分析 | 需對外公開時改匿名化 |
| Anonymization | 否 | 否 | Safe harbor | 對外發布資料集、研究 | 需追蹤個人軌跡時不可用 |
| Synthetic Data | 否（原始） | 否（原始） | 不適用 | 模型訓練、測試環境 | 分佈差異過大時需重評 |

### 格式保留加密（Format-Preserving Encryption，FPE）演算法原理

標準 AES-256 加密會把 10 位電話號碼 `0912-345-678` 變成 256-bit 亂數，破壞原始格式，無法儲存回相同欄位也無法做 JOIN。FPE 採用 **FF1 演算法**（NIST SP 800-38G 規範），基於 Feistel 網路結構，在加密的同時**保留輸入的字元集、格式和長度**。

FF1 演算法核心流程：
1. 將輸入字串拆成左右兩半（L, R）
2. 使用 AES-CBC 對右半部加密，輸出映射回原始字元集（數字映射回數字，字母映射回字母）
3. 對左半部做 XOR 操作
4. 重複 10 輪 Feistel 迴圈
5. 輸出與輸入等長、等字元集的密文

關鍵特性：**確定性（Deterministic）** — 給定相同的 DEK 和 tweak（可選的上下文值），相同輸入永遠產生相同輸出。這是 FPE 與隨機 IV 加密的根本差異，也是它能支援 JOIN 的數學基礎。

```
輸入：「王小明的電話是 0912-345-678，身分證 A123456789」
        │                │                 │
        ▼                ▼                 ▼
   DLP 偵測：姓名    DLP 偵測：電話     DLP 偵測：ID
   confidence=0.98  confidence=0.99  confidence=0.97
        │                │                 │
        ▼                ▼                 ▼
   FF1(DEK, 姓名)  FF1(DEK, 電話)   FF1(DEK, 身分證)
   字元集：Unicode   字元集：數字      字元集：英數
        │                │                 │
        ▼                ▼                 ▼
   TKN_a7f2c       TKN_b8d91        TKN_c3e47
        │                │                 │
        └────────────────┴─────────────────┘
                         ▼
輸出：「TKN_a7f2c 的電話是 TKN_b8d91，身分證 TKN_c3e47」
（格式保留、確定性 — 同一人跨所有記錄永遠得到相同 token）
```

**密鑰管理三層架構：**

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: KEK（Key Encryption Key）                  │
│  儲存位置：Cloud KMS Hardware Security Module        │
│  用途：加密包裝 DEK，KEK 永遠不離開 HSM             │
└────────────────────┬────────────────────────────────┘
                     │ 包裝 / 解包裝
┌────────────────────▼────────────────────────────────┐
│  Layer 2: DEK（Data Encryption Key）                 │
│  儲存位置：Cloud KMS（加密形式）                     │
│  用途：執行 FF1 FPE tokenization / detokenization   │
│  生命週期：90 天輪換；撤銷 DEK = 全量匿名化          │
└────────────────────┬────────────────────────────────┘
                     │ 加密 / 解密
┌────────────────────▼────────────────────────────────┐
│  Layer 1: Token Map                                  │
│  儲存位置：Cloud Spanner（與密文分離）               │
│  結構：token_id → (encrypted_original, expiry, consent_status) │
│  用途：支援 JOIN、稽核、被遺忘權執行                 │
└─────────────────────────────────────────────────────┘
```

DEK 被撤銷後，Token Map 中的 encrypted_original 永久無法解密，技術上等同於 anonymization。這是實現「被遺忘權」（GDPR Article 17）的最簡潔技術路徑：不需要物理刪除分散在各系統的資料，只需撤銷對應 DEK。

### Cloud Sensitive Data Protection 偵測機制

Cloud Sensitive Data Protection（原 DLP API）採用兩層混合偵測：

**Layer A — 規則引擎（Regex + Dictionary）：**
- 100+ 內建 infoType 偵測器（PHONE_NUMBER、CREDIT_CARD、PERSON_NAME 等）
- 台灣身份證字號正則：`[A-Z][12][0-9]{8}`
- 支援自訂 regex 和敏感詞典
- 延遲：~5ms per 1KB

**Layer B — ML 模型（Contextual Understanding）：**
- 識別非結構化文字中的姓名（「請問小明在嗎？」中的「小明」）
- 透過上下文降低誤報率（「蘋果公司」的「蘋果」不是食物 PII）
- 模型基於 Transformer 架構，fine-tuned 於多語言 PII 識別
- 延遲：~25ms per 1KB（ML 推論開銷）

合計整體 DLP 掃描延遲：**~30ms per 1KB**，PII recall rate > 97%（標準 PII 類型），誤報率（FPR）< 3%。

### 差分隱私如何保護 Embedding 向量

即使 LLM prompt 已 tokenize，向量嵌入（embedding）本身也可能洩漏 PII。以文字嵌入模型為例：「王小明住在台北」和「王小美住在台北」這兩個句子的 embedding 向量在高維空間中非常接近，攻擊者透過向量相似度搜尋就能推斷「TKN_a7f2c 的姓氏可能是王」。

差分隱私（Differential Privacy）透過在 embedding 輸出層加入校準雜訊解決這個問題：

```
原始 embedding 輸出（1536 維向量）：
[0.234, -0.891, 0.445, 0.102, ...]

加入 Laplace 雜訊（ε = 1.0，sensitivity = 1/sqrt(1536)）：
[0.241, -0.885, 0.438, 0.109, ...]

攻擊者看到的向量：無法區分是原始 PII 還是雜訊造成的差異
使用者看到的相似度搜尋結果：精度降低約 3–8%（可接受的代價）
```

隱私預算 ε 的選取是核心工程決策：
- ε = 10：弱隱私保護，幾乎不影響精度；適合低敏感資料
- ε = 1.0：中等保護；醫療資料推薦值；embedding 品質損失約 3–8%
- ε = 0.1：強保護；embedding 品質損失約 15–25%；適合高度敏感場景

面試中的加分點：能說出「ε 越小隱私越強，但 embedding 品質損失越大，需要在召回率與隱私保護間做定量取捨」，並給出實際數字。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**適用時機：** 快速 PoC、內部工具、PII 風險低且不需要分析的場景。

**實作內容：**
- 手寫 regex 規則集，覆蓋最常見 PII（Email、手機號碼、身份證字號、信用卡號）
- 維護一個正則表達式配置檔，可動態更新規則不需重新部署
- 直接用 `[REDACTED_PHONE]`、`[REDACTED_NAME]` 等語意標籤進行抑制（suppression）
- 不保留 token 對應關係，操作完全不可逆
- 無需外部服務依賴，可在應用層本地執行

**解決問題：** 在最快時間內（1–2 天）阻止明文 PII 進入 LLM prompt，避免最基本的資料外洩合規風險。

**代價與限制：**
- Regex 漏掉非結構化姓名（自然語言中的人名無法用 regex 偵測）
- 漏掉準識別符組合（zip+age+gender 各自都是「正常」資料，只有組合才危險）
- 語意標籤讓 LLM 失去部分脈絡（「[REDACTED_PHONE] 的訂單 #1234」中 LLM 無法關聯同一人的多筆訂單）
- 完全無法做 JOIN 分析或事後稽核還原
- Recall 約 70–80%，遠低於 ML-based 方案

**複雜度 / 成本：** 1 工程師 × 2 天；零外部服務成本；維護成本隨業務規則增長線性上升。

### Layer 2 — 生產就緒（Production-Ready）

**適用時機：** 對外服務、含 PII 的 AI 管線、需要稽核日誌的場景。

**實作內容：**
- 接入 Cloud Sensitive Data Protection：100+ 內建偵測器，regex + ML hybrid，recall > 97%
- FPE tokenization（FF1 演算法）+ Cloud KMS 管理 DEK
- Inbound 管線：文字 → DLP 掃描 → FPE tokenize → embedding → 向量儲存
- Outbound 管線：LLM 回應 → DLP 掃描（防殘留）→ reverse tokenize → 返回用戶
- Token 對應表儲存在 Cloud Spanner（跨區域強一致，HA = 99.999%）
- 每個 token 記錄：`{token_id, pii_type, created_at, expiry, source_system}`

```
                        ┌─────────────────────────────────────────┐
                        │           INBOUND PIPELINE              │
                        │                                         │
  ┌──────────┐   文字   ┌──────────┐  偵測結果  ┌─────────────┐  │
  │  User    │─────────▶│   DLP    │──────────▶│  FPE Tok.   │  │
  │  Input   │          │  ~30ms   │            │  <1ms/field │  │
  └──────────┘          │  /KB     │            └──────┬──────┘  │
                        └──────────┘                   │         │
                                                        │ token   │
                                               ┌────────▼──────┐  │
                                               │  Token Map    │  │
                                               │  (Spanner)    │  │
                                               └────────┬──────┘  │
                                                        │         │
                                               ┌────────▼──────┐  │
                                               │  Embedding    │  │
                                               │  (tokenized)  │  │
                                               │  + Vector DB  │  │
                                               └───────────────┘  │
                        └─────────────────────────────────────────┘

                        ┌─────────────────────────────────────────┐
                        │           OUTBOUND PIPELINE             │
                        │                                         │
  ┌──────────┐  還原    ┌──────────┐  token掃  ┌─────────────┐  │
  │  User    │◀─────────│  Rev.    │◀──────────│  LLM        │  │
  │  Output  │          │  Detok.  │  描確認    │  Response   │  │
  └──────────┘          │  <1ms    │            └─────────────┘  │
                        └──────────┘                              │
                        └─────────────────────────────────────────┘
```

**為什麼 outbound 也要掃描：** LLM 可能從 RAG 檢索到含 PII 的 chunk，或者在 few-shot 範例中出現 PII。即使 inbound 已 tokenize，模型本身可能從訓練資料「記憶化」了部分 PII 格式，outbound DLP 掃描是最後一道防線。

**解決問題：** 生產流量安全、支援跨表 JOIN 分析、可稽核還原、符合 PDPA/GDPR 偽名化要求。

**代價：**
- DLP 掃描增加 ~30ms/KB 延遲（inbound + outbound 各一次，共 ~60ms for typical 1KB request）
- Spanner token map 容量：每百萬筆 token ~2GB；需要容量規劃
- DEK 輪換策略需要工程設計：輪換期間舊 DEK 仍需可用於 detokenization

**成本：**
- Cloud DLP API：~$3/GB 掃描量
- Cloud Spanner：~$0.30/node-hour（建議 3 節點以上 HA）
- Cloud KMS：~$0.06/10,000 次密鑰操作
- 中型產品（每日 10GB 掃描）每月約 $1,200–2,500

### Layer 3 — 企業級（Enterprise-Grade）

**適用時機：** 金融、醫療、政府場景；需要通過 ISO 27001 / SOC 2 / HIPAA 稽核。

**實作內容：**

**差分隱私（Differential Privacy）保護 embedding 層：**
在向量嵌入輸出層加入 Laplace 或 Gaussian 校準雜訊（隱私預算 ε = 1.0），使攻擊者即使取得向量資料庫也無法透過向量反推原始 PII 文字。代價是相似度搜尋精度降低約 3–8%（視 ε 值而定）。

**自動化 k-匿名性驗證：**
在分析資料集發布前，執行自動化掃描確認每個準識別符組合出現次數 ≥ k（k = 5 for 一般資料，k = 10 for 醫療資料）。k-匿名性測試失敗時自動阻擋發布並發送告警。

**同意管理整合（Consent Management）：**
Token 攜帶同意狀態元資料 `consent_status: {active | withdrawn | expired}`。當用戶撤回同意時（GDPR Article 17），自動觸發 DEK 撤銷流程，無需物理刪除向量資料庫中的任何記錄——DEK 消失即等同匿名化。

**跨地區合規動態路由：**
依資料主體 IP 所在國家動態套用不同偵測規則集：GDPR（歐盟）、CCPA（加州）、PDPA（台灣）的法律依據和保留期限各不相同。

**即時 PII 熱圖儀表板：**
透過 Pub/Sub → Dataflow → BigQuery 的事件流，在 Looker Studio 顯示各管線 PII 偵測率、誤報率、延遲 p50/p95/p99 分佈、DEK 使用頻率。稽核員可以按時間、資料來源、PII 類型切片查詢。

```
┌────────────────────────────────────────────────────────────────┐
│  企業級 PII 保護全景架構                                         │
│                                                                │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │ Inbound  │──▶│   DLP    │──▶│  FPE     │──▶│ Vector   │  │
│  │  Text    │   │  Scan    │   │ Tokenize │   │   DB     │  │
│  └──────────┘   └────┬─────┘   └────┬─────┘   └──────────┘  │
│                      │              │                          │
│                      ▼              ▼                          │
│               ┌──────────┐   ┌──────────┐                    │
│               │  Audit   │   │ Consent  │                    │
│               │   Log    │   │  Check   │                    │
│               │(BigQuery)│   │(Spanner) │                    │
│               └──────────┘   └────┬─────┘                    │
│                                   │ consent_status            │
│                             ┌─────▼──────┐                   │
│                             │    KMS     │                   │
│                             │  DEK Mgmt  │◀── 撤回 → 撤銷 DEK │
│                             └─────┬──────┘                   │
│                                   │                           │
│  ┌──────────┐   ┌──────────┐   ┌──┴───────┐                  │
│  │ Outbound │◀──│  Detok.  │◀──│  Token   │                  │
│  │  to User │   │  + DLP   │   │   Map    │                  │
│  └──────────┘   └──────────┘   └──────────┘                  │
└────────────────────────────────────────────────────────────────┘
```

**解決問題：** 向量資料庫被竊取也無法推導原始 PII（差分隱私保護）；全自動合規稽核（k-匿名性驗證）；支援「被遺忘權」技術實現（DEK 撤銷）；一套架構同時滿足 GDPR、CCPA、PDPA 多地區法規。

**代價：**
- 差分隱私降低 embedding 品質（ε 越小越隱私，但精度損失越大）
- k-匿名性驗證需要計算資源，資料集越大驗證越慢
- Consent management 增加每個請求的延遲（Spanner lookup ~5ms）
- 跨地區路由需要維護法規規則映射表，法規更新時需要工程變更

**成本：** 完整企業方案每月 $5,000–20,000（含 KMS、Spanner、DLP、Dataflow、BigQuery、稽核儲存）。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 只遮蔽直接識別符，忽略準識別符 | zip+age+gender 組合仍可重新識別 87% 用戶，GDPR 仍算個人資料，合規仍然失敗 | 執行準識別符風險評估，在分析資料集發布前通過 k-匿名性測試（k ≥ 5） |
| 用隨機假名化（非確定性）替換 PII | 同一個人在不同記錄有不同 token，跨表 JOIN 全部失效，分析報表數字錯誤 | 使用 FPE（FF1 演算法）確保確定性：相同輸入 + 相同 DEK → 永遠相同 token |
| tokenization 只做 inbound，忘記 outbound | LLM 回應可能從 RAG 檢索到 PII chunk，或模型記憶化訓練資料中的 PII，outbound 成為洩漏通道 | Inbound + outbound 雙向掃描，outbound 做反向還原後才返回用戶 |
| DEK 與 token map 放在同一個資料庫 | 資料庫被竊取 = 密鑰與密文同時外洩，tokenization 形同虛設，所有 token 可立即還原 | DEK 只存 Cloud KMS 的 HSM 中，token map 與密文分離儲存在不同服務 |
| 以為「刪欄位 = 匿名化」 | 仍有 quasi-identifier 重識別風險；若可從其他欄位推導，GDPR 不認定為匿名，safe harbor 不成立 | 需通過 k-匿名性測試且所有準識別符組合都達標，才能主張 GDPR safe harbor |
| DLP 掃描放在 embedding 之後 | embedding 向量已編碼 PII 的語意表示；向量資料庫被竊取等同 PII 語意外洩，且無法補救 | DLP 掃描 + FPE tokenization 必須在 embedding 之前完成，順序不可逆轉 |
| 忘記 DEK 輪換策略 | 舊 DEK 永久有效；一旦某日 DEK 洩漏，所有歷史 token 均可還原，等同全量 PII 外洩 | 每 90 天輪換 DEK；新 DEK 用於新 token；舊 DEK 保留於 KMS 僅供 detokenization，設定自動過期 |

---

## 五、為什麼選 FPE 不選其他方案

| 選擇 | 選 FPE 的理由 | 不選另一方案的理由 | 翻轉條件 |
|------|-------------|------------------|---------|
| FPE vs AES-CBC 加密 | 格式保留（可存回原欄位）、確定性（支援 JOIN）、長度不變 | AES-CBC 輸出 256-bit 亂數，破壞格式，無法存回定長欄位，不可 JOIN | 不需要 JOIN 且欄位無長度限制時 AES-CBC 安全性更強 |
| FPE vs 隨機 UUID 替換 | 確定性：相同人名永遠同一 token，跨記錄可追蹤 | UUID 是隨機的，同一個「王小明」每次產生不同 UUID，JOIN 失效 | 完全不需要 JOIN 且追求最高隱私時，隨機 UUID 更安全 |
| FPE vs Hashing（SHA-256） | FPE 可逆（有 DEK 可還原）；DEK 撤銷後變不可逆 | Hash 不可逆但可被彩虹表攻擊（PII 取值空間有限，如電話只有 10^10 種）；無法支援「被遺忘權」撤銷 | 確實不需要還原，且 PII 取值空間足夠大時 hash + salt 可用 |
| Cloud DLP vs 自建 regex | 100+ 內建 infoType，ML 偵測非結構化姓名，recall > 97%；維護成本轉移給服務供應商 | 自建 regex 只覆蓋結構化格式，對自然語言姓名、非標準格式電話 recall < 80%；維護成本隨業務成長 | 法規要求資料不出境，或成本極度敏感時考慮自建 |

---

## 六、系統效應：套用 PII 護欄前後的量化對比

| 指標 | 套用前 | 套用後（Layer 2） | 說明 |
|------|--------|-----------------|------|
| LLM prompt 中明文 PII 率 | 100% | < 0.5% | DLP recall > 97%，剩餘為 FP/FN |
| GDPR 資料外洩風險等級 | Critical | Medium | pseudonymization 仍算個人資料 |
| 跨表 JOIN 成功率 | 100% | 100% | FPE 確定性保留 JOIN 能力 |
| 端到端請求延遲（p99） | 120ms | 180ms | +60ms（inbound 30ms + outbound 30ms DLP）|
| 向量嵌入品質（Recall@10） | 0.89 | 0.87 | tokenized text 語意略有差異（-2.2%）|
| 稽核還原能力 | 無 | 完整（需 DEK） | 支援合規稽核與客訴處理 |
| 被遺忘權執行時間 | 數週（逐系統刪除） | < 1 分鐘（撤銷 DEK） | DEK 撤銷即等同全量匿名化 |

---

## 七、合成資料（Synthetic Data）的適用邊界

合成資料是去識別化光譜最右端的選項，常被誤解為「萬能解藥」。實際上它有明確的適用邊界：

**適合用合成資料的場景：**
- LLM 微調訓練資料：用真實資料的統計分佈生成假資料，模型學到分佈特徵而非記憶化個別 PII
- 開發 / 測試環境：讓工程師用「真實感」資料測試邏輯，但不接觸生產環境 PII
- 資料集對外公開研究：完全切斷與原始個人的連結

**合成資料的技術方法：**

| 方法 | 品質 | 隱私保證 | 生成速度 | 適用資料類型 |
|------|------|---------|---------|------------|
| Gaussian Copula | 中 | 高（無記憶化） | 快 | 數值型、結構化表格 |
| CTGAN（條件 GAN） | 高 | 中（GAN 可能記憶） | 慢 | 混合型表格資料 |
| LLM 生成 | 高（語意） | 低（需加差分隱私） | 中 | 非結構化文字 |
| Differential Privacy SGD | 最高 | 最高（ε 保證） | 最慢 | 所有類型（需訓練） |

**合成資料的根本限制：**
合成資料無法保證對個別記錄的隱私保護，只保護「統計分佈」。若原始資料有異常值（例如唯一一位在台灣的 1965 年出生的藏族女性），CTGAN 仍可能生成對應的合成記錄。差分隱私訓練的生成模型才能給出 ε 層級的數學保證。

---

## 八、與其他核心主題的關聯

- **向量資料庫設計（Part 6）**：向量嵌入本身可能保留 PII 語意特徵；FPE tokenization 必須在 embedding 前完成，否則向量資料庫本身成為 PII 儲存庫，即使加密儲存也有語意洩漏風險。
- **RAG 管線架構（Part 5）**：RAG 的 Retrieval 步驟從向量資料庫取回 chunk，這些 chunk 可能含有殘留 PII；送進 LLM 的 context 需要再次過 DLP 掃描，才能確保 prompt 完全乾淨。
- **資料治理與血緣（Part 11）**：PII token 的 provenance 元資料（來源系統、處理時間、法律依據、同意狀態）是資料治理血緣圖的核心節點；沒有血緣追蹤，「被遺忘權」的執行就無法自動化。
- **LLM 微調資料準備（Part 15）**：微調訓練資料集必須先通過 anonymization（而非僅 pseudonymization），否則模型可能記憶化 PII；k-匿名性驗證是訓練資料集發布的前置門檻，否則即使微調後的模型也可能成為 PII 洩漏通道。

---

## 九、面試一句話（Killer Phrase）

> *「PII 去識別化在 AI 管線中的核心取捨是三條線：suppression 最安全但斷掉分析可用性；FPE pseudonymization 透過 FF1 演算法的確定性（相同輸入 + 相同 DEK → 永遠相同 token）保留跨表 JOIN 能力，讓 LLM 可安全推論，但在 GDPR 下仍屬個人資料、需要同意機制；真正的 anonymization 需通過 k-匿名性測試（k ≥ 5）且不可逆，才能達到 GDPR safe harbor。實作上，Cloud DLP 掃描延遲約 30ms/KB、FPE tokenization < 1ms/欄位，inbound + outbound 雙向掃描合計約增加 60ms p99 延遲，整體在 200ms 預算內可行；「被遺忘權」技術實現的最優解是撤銷 DEK 而非物理刪除資料，DEK 消失即等同全量匿名化，執行時間從數週縮短至一分鐘以內。」*

---

## 十、症狀診斷：如何從 Traces / Metrics / Logs 發現 PII 洩漏

面試官有時會問：「你怎麼知道你的 PII 護欄沒有失效？」這是可觀測性問題，也是系統設計的一部分。

**Metrics（告警觸發）：**

| 指標名稱 | 正常範圍 | 告警閾值 | 可能原因 |
|---------|---------|---------|---------|
| `dlp_pii_detection_rate` | 0.5–5% per request | 突增 > 20% | 新的 PII 類型流入，規則需更新 |
| `dlp_false_positive_rate` | < 3% | > 10% | 模型對特定業務術語誤判 |
| `tokenization_latency_p99` | < 5ms | > 50ms | KMS 呼叫瓶頸，DEK 快取失效 |
| `detokenization_failure_rate` | < 0.01% | > 0.1% | DEK 已輪換但舊 token 尚未遷移 |
| `outbound_pii_detected_count` | ≈ 0 | > 0（任何一個） | LLM 回應包含明文 PII，立即告警 |

**Logs（根因分析）：**

當 `outbound_pii_detected_count > 0` 告警觸發時，查看 DLP 稽核日誌：
- 哪個 PII 類型被偵測到（PERSON_NAME? PHONE_NUMBER?）
- 對應的 RAG chunk 來源文件 ID
- 該 chunk 的入庫時間（確認是否在 tokenization 機制建立之前索引的舊資料）

最常見的根因：**存量資料問題**——在 DLP 管線建立之前索引的文件，已含明文 PII 的 embedding 進了向量資料庫。解決方式：對歷史資料執行批次重新索引（re-ingestion），通過 DLP + tokenization 管線後再次 embed。

**Traces（延遲瓶頸定位）：**

```
請求 trace 範例（正常情況）：
  ├── DLP Scan (inbound)     28ms
  ├── KMS DEK Fetch           3ms  ← 有快取時 < 0.1ms
  ├── FPE Tokenize            1ms
  ├── Embedding API          45ms
  ├── Vector Search          12ms
  ├── LLM Inference         120ms
  ├── DLP Scan (outbound)    25ms
  └── FPE Detokenize          1ms
  Total p99:                235ms

告警情況：KMS DEK Fetch 突增至 80ms
根因：KMS 配額限流（預設 600 req/min），需要申請提升或加入本地 DEK 快取
```

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-7-vector-search-optimization-zh/) | [後一篇](/posts/fde-interview-core-topic-9-rag-evaluation-metrics-zh/) →
