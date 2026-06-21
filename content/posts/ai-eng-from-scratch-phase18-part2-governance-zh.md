---
title: "AI 工程從零開始｜Phase 18 Part 2：AI 治理與倫理 — 工程師的責任邊界"
date: 2026-06-22T04:30:00+08:00
draft: false
weight: 40
description: "深入解析 AI 治理工程：EU AI Act/NIST AI RMF 合規架構、偏見偵測與緩解技術、資料隱私工程（差分隱私/聯邦學習）與 AI 稽核框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Safety", "Governance", "Ethics", "Bias", "Privacy", "Compliance", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> 大多數工程師把 AI 治理當成法務部門的事，等監管機關發函才開始補文件；
> 正確答案是：治理是系統設計的一等公民，在模型進 production 的第一天就必須量測公平性、記錄資料來源、控制隱私洩露量。
> 不做治理不是「省力」，是把合規風險、偏見訴訟、資料外洩的成本推遲到最貴的時間點——上線之後。
> 工程師不需要成為法律專家，但必須懂得把監管義務翻譯成系統元件和可量測的指標。

---

## 面試情境

> 你的團隊正要在 EU 市場推出一個信用評分 AI 系統，PM 說「先上線再合規」，CTO 問你：從工程架構角度，最低限度需要做哪些治理元件才能在 EU AI Act 生效後合法營運？如果資料集中有性別和種族代理變數，你打算怎麼處理偏見？隱私工程用什麼機制確保 GDPR 合規？

---

## 一、核心問題：AI 治理為什麼是工程師的問題

AI 治理在過去五年從「道德宣示」進化為「法律義務」。EU AI Act 在 2024 年正式生效，預計 2026 年高風險系統進入強制合規期；NIST AI RMF 已成為美國聯邦採購的事實標準；中國、英國、加拿大相繼推出對等框架。

**工程師為什麼不能把這件事推給法務？**

1. **合規義務落在系統層**：EU AI Act Article 9 要求「risk management system」必須以技術文件佐證，不是 policy PDF，是可追溯的程式碼和日誌
2. **偏見來自資料 pipeline**：統計公平性的破壞點在特徵工程、訓練集採樣、評估集分割——法務無法在那裡插手
3. **隱私洩露是技術問題**：差分隱私的 epsilon 預算、聯邦學習的梯度聚合——這些是數學和工程，不是合約條款
4. **稽核需要系統支撐**：監管機關要看 model card、訓練資料來源、版本歷史、A/B 決策記錄——這些必須在 CI/CD 裡自動生成

**信用評分這個域的具體風險：**
- EU AI Act 分類：高風險（Annex III, 5b — access to essential private services）
- GDPR Article 22：禁止純自動化決策影響個人法律地位，除非有明確告知和申訴機制
- 美國 FCRA/ECOA：對抵押貸款、信用卡的公平貸款義務，違規罰款可達 $1M/天
- 偏見訴訟：2021 年美國有 12 件 AI 信用歧視集體訴訟，和解金從 $2M 到 $98M

---

## 二、三個演進階段（POC → MVP → Scale）

### ╔══ Phase 1：POC / < 5K 用戶 ══╗

**目標**：最低限度治理，讓系統能合法上線做受控測試

```
┌──────────────────────────────────────────────────────┐
│  Phase 1 治理架構                                    │
│                                                      │
│  ┌─────────────┐    ┌──────────────────────────┐    │
│  │  訓練資料   │───▶│  資料卡（Data Card）     │    │
│  │  Lineage    │    │  - 來源、日期、授權       │    │
│  └─────────────┘    │  - 人口統計分佈摘要       │    │
│                     └──────────────────────────┘    │
│  ┌─────────────┐    ┌──────────────────────────┐    │
│  │  模型訓練   │───▶│  Model Card（手動）      │    │
│  │  Notebook   │    │  - 評估資料集             │    │
│  └─────────────┘    │  - 已知限制               │    │
│                     └──────────────────────────┘    │
│  ┌─────────────┐    ┌──────────────────────────┐    │
│  │  推論服務   │───▶│  決策日誌（基本）        │    │
│  │             │    │  - input hash, output,    │    │
│  └─────────────┘    │    timestamp, user_id     │    │
│                     └──────────────────────────┘    │
│                                                      │
│  成本：~$200/月（日誌儲存 + 手動文件工時 8h/月）    │
│  缺口：無自動公平性量測、無差分隱私、無申訴機制     │
└──────────────────────────────────────────────────────┘
```

新增元件：資料卡、手寫 Model Card、基本決策日誌
可接受的捷徑：手動公平性評估（每季一次）、無自動化稽核
解決問題：有基本可追溯性，能回答「這個決策從哪來」
遺留問題：無法應對 EU AI Act Article 9 的持續風險監控要求

---

### ╔══ Phase 2：MVP / 10K–200K 用戶 ══╗

**目標**：生產安全，能通過第三方稽核，滿足 EU AI Act 高風險系統基本義務

```
┌────────────────────────────────────────────────────────────────┐
│  Phase 2 治理架構                                              │
│                                                                │
│  資料層                        模型層                          │
│  ┌──────────────┐              ┌──────────────────────────┐   │
│  │ 特徵商店     │──保護欄位──▶ │ 訓練 Pipeline            │   │
│  │ (PII 標記)   │   移除       │ + 公平性約束 (Fairlearn) │   │
│  └──────────────┘              └────────────┬─────────────┘   │
│                                             │                  │
│  隱私層                                     ▼                  │
│  ┌──────────────┐              ┌──────────────────────────┐   │
│  │ 差分隱私     │◀─梯度─────── │ 評估：Demographic Parity │   │
│  │ ε=1.0 預算   │              │ Equalized Odds, AUC/group│   │
│  └──────────────┘              └────────────┬─────────────┘   │
│                                             │                  │
│  推論層                                     ▼                  │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ 推論服務                                              │     │
│  │  ├─ 決策解釋（SHAP top-3 features）                  │     │
│  │  ├─ 申訴 API（POST /decisions/{id}/appeal）           │     │
│  │  └─ 決策日誌（全量，保存 5 年）                       │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  稽核層                                                        │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  自動 Model Card 生成 (CI/CD)  │  季度公平性報告      │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  成本：~$2,500/月（DP 計算 + SHAP + 日誌 + 稽核工時）         │
└────────────────────────────────────────────────────────────────┘
```

新增元件：差分隱私訓練、公平性評估自動化、SHAP 解釋、申訴 API、自動 Model Card
解決問題：能應對正式稽核，滿足 GDPR Article 22 的解釋權
遺留問題：無即時偏見監控、無聯邦學習（仍集中式訓練）

---

### ╔══ Phase 3：Scale / 200K–1M+ 用戶 ══╗

**目標**：企業級合規，滿足 EU AI Act 嚴格稽核、多市場法規、即時偏見警報

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3 治理架構                                               │
│                                                                 │
│  資料層（去中心化）                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │ 銀行 A   │  │ 銀行 B   │  │ 銀行 C   │  ← 聯邦學習節點    │
│  │ 本地訓練 │  │ 本地訓練 │  │ 本地訓練 │                     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                     │
│       │              │              │                           │
│       └──────────────┼──────────────┘                          │
│                      ▼ 梯度聚合（安全聚合 + DP）               │
│  ┌─────────────────────────────────────────┐                   │
│  │  聯邦協調器（Flower / PySyft）          │                   │
│  │  ε=0.5 全域預算，δ=1e-5                 │                   │
│  └──────────────────┬──────────────────────┘                   │
│                     │                                           │
│                     ▼                                           │
│  ┌─────────────────────────────────────────┐                   │
│  │  全域模型倉庫（含版本、偏見指標快照）   │                   │
│  └──────────────────┬──────────────────────┘                   │
│                     │                                           │
│                     ▼                                           │
│  ┌─────────────────────────────────────────┐                   │
│  │  即時公平性監控（Grafana + 自定義指標） │                   │
│  │  - DP gap > 5%：自動 PagerDuty 告警     │                   │
│  │  - 群體 AUC 落差 > 3%：觸發 re-eval    │                   │
│  └──────────────────┬──────────────────────┘                   │
│                     │                                           │
│                     ▼                                           │
│  ┌─────────────────────────────────────────┐                   │
│  │  監管報告生成器                         │                   │
│  │  - 自動產出 EU AI Act Article 11 技術文件│                  │
│  │  - System Card（季度更新）              │                   │
│  │  - 影響評估（DPIA + AI IA）             │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
│  成本：~$15,000/月（聯邦學習基礎設施 + 即時監控 + 法遵工程師） │
└─────────────────────────────────────────────────────────────────┘
```

新增元件：聯邦學習架構、即時公平性監控、自動監管報告、全球多框架合規層
成本/複雜度增量：比 Phase 2 成本 6x，但規避的監管罰款可達 €30M 或全球營收 6%

---

## 三、監管框架：EU AI Act / NIST AI RMF 的工程義務

### EU AI Act 風險分層

```
┌──────────────────────────────────────────────────────────────────┐
│  EU AI Act 風險金字塔                                            │
│                                                                  │
│              ┌─────────────────┐                                │
│              │  不可接受風險   │ ← 禁止：社會評分、即時生物辨識│
│              │  Unacceptable   │   強制執行：2024/2/2 生效      │
│              └────────┬────────┘                                │
│         ┌─────────────┴──────────────┐                         │
│         │      高風險（Annex III）    │ ← 信用評分、就業篩選   │
│         │      High Risk             │   醫療診斷、教育評估    │
│         │  義務：技術文件、人工監督  │   強制執行：2026/8/2   │
│         │  風險管理、資料治理        │                         │
│         └─────────────┬──────────────┘                         │
│    ┌────────────────────┴───────────────────┐                   │
│    │  限定風險（Limited Risk）              │ ← 聊天機器人      │
│    │  義務：透明度告知（你在和 AI 互動）   │                   │
│    └────────────────────┬───────────────────┘                   │
│ ┌──────────────────────────────────────────────────────────┐   │
│ │  最低風險（Minimal Risk）                                │   │
│ │  垃圾郵件過濾、遊戲 AI — 無強制義務                     │   │
│ └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**高風險系統的工程義務清單（Article 9-17）：**

| 義務條款 | 工程實作 | 驗證方式 |
|----------|----------|----------|
| Article 9 風險管理系統 | 持續監控 pipeline + 告警閾值 | 季度稽核報告 |
| Article 10 資料治理 | 訓練資料 lineage、偏見掃描 | Data Card + 自動報告 |
| Article 11 技術文件 | 自動 Model Card 生成（CI） | 每次部署更新 |
| Article 12 日誌記錄 | 全量決策日誌，保存 5–10 年 | Log immutability check |
| Article 13 透明度 | 使用者告知 + 能力邊界聲明 | UI 稽核截圖 |
| Article 14 人工監督 | Human-in-the-loop for edge cases | 覆核率監控 |
| Article 17 品質管理 | CI/CD gate：公平性指標失敗擋部署 | PR check 強制通過 |

### NIST AI RMF 的四個功能

NIST AI RMF（2023）定義四個功能，對應工程實作：

- **Govern（治理）**：建立組織層級的 AI 政策、角色責任矩陣（RACI）、風險偏好聲明
- **Map（映射）**：識別 AI 系統的使用場景、利害關係人、潛在危害；產出 AI Impact Assessment
- **Measure（量測）**：量化風險指標（公平性、可靠性、可解釋性）；建立評估資料集和基準
- **Manage（管理）**：實作緩解措施（偏見緩解、隱私工程）；監控生產環境指標；應對事故

工程師的主要工作落在 **Measure** 和 **Manage** 功能。

---

## 四、偏見偵測：統計公平性指標與工程緩解策略

### 四大公平性指標定義

設 A 為保護屬性（如性別、種族），Y 為真實標籤，Ŷ 為模型輸出：

**1. Demographic Parity（統計平等）**
```
P(Ŷ=1 | A=0) = P(Ŷ=1 | A=1)
```
信用核准率在所有群體相同。容易量測但忽略真實資格差異。

**2. Equalized Odds（均等機會）**
```
P(Ŷ=1 | A=0, Y=y) = P(Ŷ=1 | A=1, Y=y)  for y ∈ {0,1}
```
真陽性率（核准有資格者）和假陽性率（核准無資格者）在群體間相等。
比 Demographic Parity 更嚴格，同時控制兩種錯誤。

**3. Calibration（校準）**
```
P(Y=1 | Ŷ=p, A=a) = p  for all a
```
輸出的信心分數在不同群體具有相同的校準品質。對信用評分尤為重要。

**4. Individual Fairness**
相似的個人應獲得相似的結果：`d(x_i, x_j) < ε → |f(x_i) - f(x_j)| < δ`

**這四者無法同時滿足（Impossibility Theorem）**，工程師必須根據應用場景選擇。

### 公平性量測程式碼片段

```python
from sklearn.metrics import confusion_matrix
import numpy as np

def compute_fairness_metrics(y_true, y_pred, sensitive_attr):
    """
    非顯而易見實作：同時計算 DP gap 和 Equalized Odds gap
    回傳 dict，可直接送 Prometheus metrics
    """
    groups = np.unique(sensitive_attr)
    results = {}

    group_stats = {}
    for g in groups:
        mask = sensitive_attr == g
        tn, fp, fn, tp = confusion_matrix(
            y_true[mask], y_pred[mask], labels=[0, 1]
        ).ravel()
        group_stats[g] = {
            "approval_rate": (tp + fp) / mask.sum(),
            "tpr": tp / (tp + fn) if (tp + fn) > 0 else 0,  # True Positive Rate
            "fpr": fp / (fp + tn) if (fp + tn) > 0 else 0,  # False Positive Rate
        }

    # Demographic Parity gap（最大 - 最小核准率）
    approval_rates = [s["approval_rate"] for s in group_stats.values()]
    results["dp_gap"] = max(approval_rates) - min(approval_rates)

    # Equalized Odds gap（TPR 差距 + FPR 差距的加權和）
    tprs = [s["tpr"] for s in group_stats.values()]
    fprs = [s["fpr"] for s in group_stats.values()]
    results["eo_gap"] = (max(tprs) - min(tprs)) + (max(fprs) - min(fprs))

    # 判斷是否觸發告警（EU AI Act 建議 DP gap < 0.1）
    results["dp_alert"] = results["dp_gap"] > 0.1
    results["eo_alert"] = results["eo_gap"] > 0.1

    return results
```

### 偏見緩解三層策略

| 層次 | 技術 | 效果 | 代價 |
|------|------|------|------|
| 前處理（Pre-processing） | 重採樣、Reweighing、Disparate Impact Remover | DP gap 可降 40–60% | 訓練資料量損失 10–15% |
| 訓練中（In-processing） | Fairlearn Reduction、對抗解偏（Adversarial Debiasing） | Equalized Odds gap 降 30–50% | 訓練時間增加 2–3x，整體 AUC 損失 1–3% |
| 後處理（Post-processing） | Threshold Optimizer（群體差異化閾值） | 快速部署，不需重訓 | 需要保護屬性在推論時可用 |

**關鍵數字**：信用評分中，完全消除 DP gap 通常導致整體 AUC 下降 2–5%，這是商業和倫理之間的真實張力，工程師需要明確記錄這個 tradeoff。

---

## 五、資料隱私工程：差分隱私 / 聯邦學習 / GDPR 合規

### 差分隱私（Differential Privacy）

差分隱私的數學保證：無論攻擊者知道資料集中其他所有人的資訊，都無法確定某個特定個人是否出現在訓練集中。

**ε-δ 差分隱私定義：**
```
P[M(D) ∈ S] ≤ e^ε × P[M(D') ∈ S] + δ
```
其中 D 和 D' 只差一筆記錄。ε 越小，隱私保護越強；δ 是隱私失效的概率上界。

**實作：高斯機制（Gaussian Mechanism）**

```python
import numpy as np

def dp_gaussian_mechanism(true_value, sensitivity, epsilon, delta):
    """
    差分隱私高斯機制
    sensitivity: 函數的 L2 敏感度（單筆記錄的最大影響）
    epsilon, delta: 隱私預算參數
    
    信用評分場景：計算群體平均分數時，sensitivity = max_score / n
    """
    # 計算高斯噪音標準差
    # Calibrated to (epsilon, delta)-DP via analytic Gaussian mechanism
    sigma = sensitivity * np.sqrt(2 * np.log(1.25 / delta)) / epsilon

    noise = np.random.normal(0, sigma)
    return true_value + noise

# 使用範例：差分隱私統計群體平均信用分數
# epsilon=1.0（業界常用值）, delta=1e-5（金融場景建議）
n_users = 10000
max_score = 850
sensitivity = max_score / n_users  # 移除一筆記錄的最大影響

true_mean = 720.5
dp_mean = dp_gaussian_mechanism(true_mean, sensitivity, epsilon=1.0, delta=1e-5)
# 典型噪音：±0.3 分，對群體統計幾乎無影響，但對個人隱私有強保護
```

**ε 值選擇指南：**
| ε 值 | 隱私保護程度 | 資料可用性 | 適用場景 |
|------|-------------|-----------|----------|
| ε ≤ 0.1 | 極強 | 低（誤差大） | 高敏感醫療資料 |
| ε = 1.0 | 強 | 中 | 金融信用（推薦） |
| ε = 10.0 | 弱 | 高 | 低敏感統計 |
| ε > 100 | 幾乎無保護 | 極高 | 不建議稱為 DP |

### 聯邦學習架構

聯邦學習解決「資料不能集中」的合規問題（GDPR 跨境傳輸限制、銀行業資料主權）：

```
┌──────────────────────────────────────────────────────────────┐
│  聯邦學習訓練流程                                            │
│                                                              │
│  Round t                                                     │
│  ┌─────────────┐                                            │
│  │  協調器     │ ─── 廣播全域模型 w_t ──────────────────▶  │
│  │ Aggregator  │                                            │
│  └──────┬──────┘                                            │
│         │                                                    │
│         │ ◀─── 本地梯度 Δw_k（加 DP 噪音）─────────────── │
│         │                                                    │
│  ┌──────▼──────────────────────────────────────────────┐    │
│  │  安全聚合（Secure Aggregation）                      │    │
│  │  w_{t+1} = w_t + η × Σ_k (n_k/n) × Δw_k           │    │
│  │  + 裁剪（Gradient Clipping, norm ≤ C=1.0）          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  隱私保證：                                                  │
│  - 本地資料永遠不離開節點                                    │
│  - 梯度注入 DP 噪音（ε=0.5/round，100 rounds → ε=50 累積） │
│  - Moments Accountant 追蹤累積 ε 預算                       │
│                                                              │
│  GDPR 合規點：                                               │
│  - Article 44（跨境傳輸）：梯度非個人資料，合法傳輸         │
│  - Article 5（資料最小化）：原始資料不流出                   │
└──────────────────────────────────────────────────────────────┘
```

**聯邦學習的實際挑戰：**
- Non-IID 資料分佈：銀行 A 的用戶組成與銀行 B 不同，導致全域模型偏向大數據節點
- 通訊成本：100 輪 × 10 個節點 × 1GB 梯度 = 1TB 傳輸，需要梯度壓縮（量化到 4-bit，減少 8x）
- 系統異質性：節點算力差異大，需要 FedAsync 非同步聚合

---

## 六、AI 可解釋性需求：LIME/SHAP 的監管意義

### 監管要求的可解釋性

GDPR Article 22(3) 要求能向被決策者提供「有意義的資訊，說明其中涉及的邏輯」（meaningful information about the logic involved）。EU AI Act Article 13 要求「可解釋的輸出」。這不是工程可選項，是法律義務。

### SHAP（SHapley Additive exPlanations）

SHAP 基於博弈論的 Shapley 值，為每個特徵計算對預測的邊際貢獻：

```
f(x) = φ_0 + Σ_i φ_i
```
其中 φ_0 是基準預測（訓練集均值），φ_i 是特徵 i 的 Shapley 值。

**監管義務實作：**
```python
import shap

explainer = shap.TreeExplainer(credit_model)
shap_values = explainer.shap_values(X_test)

def generate_adverse_action_notice(shap_values_single, feature_names, threshold=0):
    """
    FCRA / ECOA 要求的不利行動通知：說明拒絕原因
    美國法規要求列出最多 4 個最重要的負向因素
    """
    # 負向 SHAP 值 = 降低核准機率的因素
    negative_factors = [
        (feature_names[i], shap_values_single[i])
        for i in range(len(shap_values_single))
        if shap_values_single[i] < 0
    ]
    negative_factors.sort(key=lambda x: x[1])  # 最負的排前面

    # 返回前 4 個不利因素（FCRA 要求）
    return negative_factors[:4]
```

### LIME vs SHAP 選擇

| 面向 | LIME | SHAP |
|------|------|------|
| 一致性 | 每次解釋可能不同（隨機採樣） | 一致（Shapley 值有唯一解） |
| 計算速度 | 快（~50ms/樣本） | 慢（~500ms/樣本，TreeSHAP 除外） |
| 全局解釋 | 需手動聚合 | 原生支援 global importance |
| 監管可接受度 | 較低（不穩定） | 高（可重現，有數學基礎） |
| 適用模型 | 任何 black-box | 樹模型最快，其他模型慢 |

**監管場景推薦**：用 TreeSHAP（梯度提升/隨機森林模型）— 速度快（< 10ms/樣本），結果可重現，符合監管可接受度。

---

## 七、AI 稽核框架：模型卡 / 系統卡 / 影響評估

### Model Card（模型卡）

Model Card 由 Google Research（2018）提出，已成為 EU AI Act Article 11 技術文件的事實標準結構。

**必要欄位（高風險系統）：**
```yaml
# model_card.yaml（自動從 CI 生成）
model_details:
  name: "credit-scoring-v2.3.1"
  type: "XGBoost 二元分類"
  version: "2.3.1"
  date: "2026-06-22"
  license: "Proprietary"

intended_use:
  primary_use: "消費者信用申請初步篩選"
  out_of_scope: "房貸決策（需額外人工審核）、法律意義上的最終決策"

training_data:
  source: "內部歷史申請資料 2018–2024"
  size: "2.3M 筆記錄"
  known_biases: "2018–2020 女性申請者比例偏低（32%），可能導致女性群體訓練資料不足"

evaluation:
  overall_auc: 0.847
  fairness:
    demographic_parity_gap: 0.043  # 性別
    equalized_odds_gap: 0.031       # 性別
    dp_gap_ethnicity: 0.071         # 族裔（已觸發 Phase 2 緩解）
  performance_by_group:
    male_auc: 0.851
    female_auc: 0.838  # 差距 1.3%，在可接受範圍

limitations:
  - "對申請資料少於 6 個月的新用戶準確度下降 12%"
  - "族裔 DP gap 0.071 已超過內部閾值 0.05，正在進行 Phase 3 緩解"

ethical_considerations:
  - "不使用種族、性別、宗教作為直接特徵"
  - "郵遞區號作為代理變數的影響已透過 Disparate Impact Remover 處理"
```

### AI Impact Assessment（AI 影響評估）

EU AI Act Article 9 和 GDPR DPIA（Data Protection Impact Assessment）要求在部署前進行影響評估，包含：

1. **系統描述**：目的、範圍、利害關係人
2. **風險識別**：對個人、群體、社會的潛在危害（列出至少 10 個風險場景）
3. **現有緩解措施**：對每個風險的工程控制
4. **殘餘風險評估**：緩解後的剩餘風險是否在可接受範圍
5. **監督機制**：誰負責持續監控，多久一次
6. **申訴機制**：被影響者如何質疑決策

---

## 八、為什麼選 X 不選 Y

### 決策 1：公平性約束 — Fairlearn Reduction vs 後處理閾值調整

```
選擇              選 Fairlearn Reduction 的理由    不選後處理閾值的理由
────────────────────────────────────────────────────────────────────────
Fairlearn         - 訓練時同時優化準確度和公平性   - 後處理只修改輸出，不修正
Reduction         - 產出 Pareto 最優解集合          模型內部的偏見來源
vs                - 不需要保護屬性在推論時可用      - 閾值調整在不同群體之間需要
後處理閾值        - EO gap 降幅更大（~50% vs ~30%）  保護屬性存在，GDPR 限制多
```

**flip condition**：如果模型已上線且重訓成本極高（> $50K），或監管要求立即修正，後處理閾值調整可作為緊急措施，重訓後替換。

---

### 決策 2：隱私預算 — ε=1.0 vs ε=0.1

```
選擇      選 ε=1.0 的理由                不選 ε=0.1 的理由
────────────────────────────────────────────────────────────────
ε=1.0     - 業界金融場景常用值           - ε=0.1 噪音過大：10K 樣本
vs        - AUC 損失可控（~0.5–1%）       下 DP gap 測量誤差 > 10%
ε=0.1     - 梯度統計仍有意義             - 模型收斂速度慢 3–5x
          - 公開 ML 競賽資料可接受        - 實際提供的隱私保護比直覺好
                                           得多（ε=0.1 攻擊成本提高 e^0.9）
```

**flip condition**：醫療記錄或敏感政治資料，ε ≤ 0.5；敏感度分析顯示模型對個別記錄的敏感度高時，降低 ε。

---

### 決策 3：解釋方法 — TreeSHAP vs LIME

```
選擇        選 TreeSHAP 的理由              不選 LIME 的理由
────────────────────────────────────────────────────────────
TreeSHAP   - 計算速度：< 10ms/樣本         - LIME 每次解釋不一致
vs         - 全局和局部解釋統一框架         （同一筆記錄解釋可能不同）
LIME       - 有唯一的數學解（Shapley 值）  - 監管機關質疑不可重現的解釋
           - 可重現，audit trail 完整       - 採樣依賴，對邊界案例不穩定
           - 已在多個 EU 監管案例被接受
```

**flip condition**：模型是 LLM 或 neural network 且沒有樹狀結構，用 KernelSHAP 或 DeepSHAP；解釋速度要求 < 1ms（即時系統），考慮預算計算批次 SHAP。

---

### 決策 4：聯邦學習框架 — Flower vs PySyft

```
選擇      選 Flower 的理由                不選 PySyft 的理由
────────────────────────────────────────────────────────────────
Flower    - 生產就緒，Amazon / Samsung     - PySyft 0.x API 不穩定，
vs        已部署                            0.5 到 0.6 有破壞性變更
PySyft    - 節點異質性支援好（CPU/GPU/     - 文件不完整，社群相對小
           Mobile 混合）                  - 安全聚合實作複雜度高
          - gRPC 通訊，低延遲             - 適合研究，不適合直接生產
          - 內建 DP（使用 Opacus）
```

**flip condition**：研究場景需要更靈活的 crypto protocol（如 MPC/HE），PySyft 的 syft-crypto 更合適；如果已有 Ray 基礎設施，考慮 Ray Federated。

---

### 決策 5：偏見緩解時機 — 前處理 vs 訓練中

```
選擇      選前處理（Pre-processing）的理由    不選訓練中的理由
────────────────────────────────────────────────────────────────
前處理    - 可解釋：資料集本身已公平         - Adversarial Debiasing 訓練
Reweight  - 不改變模型架構，任何模型可用      不穩定，需調整 adversary
vs        - 快速驗證：處理後直接用標準評估    learning rate（易爆梯度）
訓練中    - 歷史偏見問題在資料層修正          - 訓練時間增加 2–3x
          - 技術文件容易解釋給非技術稽核者   - 公平性和準確度 tradeoff
                                               在訓練時更難控制
```

**flip condition**：資料集太小（< 10K）重採樣會導致過擬合；保護屬性在資料層不可得（只有代理變數），必須在模型層處理。

---

### 決策 6：稽核日誌儲存 — 不可變物件儲存 vs 關聯式資料庫

```
選擇          選不可變物件儲存的理由           不選 RDBMS 的理由
────────────────────────────────────────────────────────────────
S3 Object     - 成本：$0.023/GB vs $0.10/GB    - RDBMS UPDATE/DELETE 會破壞
Lock + Glacier  稽核日誌通常 100GB+/月           不可變性，EU AI Act 要求
vs            - WORM（Write Once Read Many）     日誌不可篡改
RDBMS           原生合規（SEC 17a-4 標準）      - 5 年保存期：100GB/月 × 60
              - 並發寫入無鎖爭用               個月 = 6TB，RDBMS 費用高
              - 壓縮：Parquet 格式節省 70%     - 稽核查詢通常是批次掃描，
                                                不需要 OLTP 能力
```

**flip condition**：如果監管要求即時查詢個別決策（申訴場景），在不可變儲存之外加一個 DynamoDB 索引（存 decision_id + S3 pointer）即可，不需要把全量日誌放 RDBMS。

---

## 九、系統效應

### 無治理 vs 合規架構的量化比較

| 指標 | 無治理 | Phase 2 合規架構 | Phase 3 企業級 |
|------|--------|-----------------|---------------|
| **監管罰款風險** | EU AI Act：最高 €30M 或全球營收 6% | 大幅降低，有技術文件佐證 | 近零（持續合規） |
| **GDPR 違規風險** | 高（集中式訓練，PII 無保護） | 中（DP 保護，但仍集中） | 低（聯邦學習 + DP） |
| **偏見訴訟成本** | 集體訴訟平均 $15M–$98M 和解 | 有文件記錄，訴訟風險 -70% | 即時監控，事前干預 |
| **Demographic Parity gap** | 通常 0.10–0.25（未量測）| 0.04–0.08（有緩解）| < 0.05（持續監控） |
| **監管准入** | EU 高風險市場：禁止部署 | 可部署（基本義務滿足） | 可進入 US Federal 採購 |
| **技術文件完整度** | 0%（無文件） | 80%（自動 + 手動）| 99%（全自動 CI 生成） |
| **決策可追溯性** | 無（或不完整） | 100%（5 年保存）| 100% + 即時查詢（< 50ms） |
| **申訴處理時間** | 無機制（法規要求 30 天內）| 手動 5–10 天 | 自動化 < 24 小時 |
| **信任指標（用戶調查）** | 基準：42% 信任 AI 決策 | +18%（有解釋）| +35%（透明 + 申訴機制）|
| **工程成本/月** | $0 治理成本（但隱藏風險） | $2,500 | $15,000 |
| **市場准入價值** | EU 市場：$0（不合法）| EU 市場准入：$X | EU + US Federal：$X + 20% |

**關鍵 insight**：Phase 2 的 $2,500/月治理成本，相對於 EU AI Act 罰款（最低起跳 €7.5M）的風險，ROI 無庸置疑。Phase 3 的 $15,000/月適用於年收入超過 $5M 的高風險 AI 服務。

---

## 十、面試答題要點

**面試情境回應模型（RKK 架構）**

> *「我會把這個問題拆成三個層次：監管義務、偏見工程、隱私架構。EU AI Act 把信用評分列為高風險系統（Annex III），代表你在 2026 年 8 月前必須有技術文件（Article 11）、持續風險監控（Article 9）、人工監督機制（Article 14）三件事才能合法營運——這些必須在 CI/CD 裡自動生成，不是法務寫 PDF。偏見方面，我不會直接移除性別欄位了事，而是量測 Demographic Parity gap 和 Equalized Odds gap 基準，用 Fairlearn Reduction 在訓練時加公平性約束，目標把 DP gap 壓到 < 0.05，同時在推論時用 TreeSHAP 生成不利行動通知（這是 FCRA 要求的四個拒絕理由）。隱私工程上，如果跨境資料傳輸是合規風險點，Phase 3 我會轉向聯邦學習架構（Flower + Opacus DP，ε=1.0），讓原始資料不離開各機構；如果還是集中訓練，最低限度要用 ε=1.0 差分隱私保護聚合統計，並把決策日誌存到 S3 Object Lock（WORM）保存五年。對 PM 的『先上線再合規』，我的答案是 Phase 1 可以接受手動 Model Card 和基本日誌，但公平性評估和申訴 API 在第一天就必須上線，否則一旦收到監管查詢，補不回來的是舉證責任，不是技術文件。」*

---

## 十一、系列導航

← [Phase 18 Part 1：AI 安全工程 — 對抗攻擊與模型強固化](/posts/ai-eng-from-scratch-phase18-part1-security-zh/)

→ [Phase 19 Part 1：AI 系統評估與 LLM 可靠性工程](/posts/ai-eng-from-scratch-phase19-part1-evaluation-zh/)

---

*本文為「AI 工程從零開始」系列第 18 階段第 2 部分，涵蓋 AI 治理與倫理的工程實作層面。所有監管引用以 2026 年 6 月為準，EU AI Act 強制合規時程以歐盟官方公報為準。*
