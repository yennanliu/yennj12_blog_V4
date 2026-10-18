---
title: "AI 工程從零開始｜Phase 18 Part 2：AI 治理與倫理 — 工程師的責任邊界"
date: 2026-06-22T04:30:00+08:00
draft: false
weight: 40
description: "深入解析 AI 治理工程：EU AI Act/NIST AI RMF 合規架構、偏見偵測與緩解技術、資料隱私工程（差分隱私/聯邦學習）與 AI 稽核框架"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Safety", "Governance", "Ethics", "Bias", "Privacy", "Compliance", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "15 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師把 AI 治理當成法務部門的事，等監管機關發函才開始補文件；*
> *正確答案是：治理是系統設計的一等公民，在模型進 production 的第一天就必須量測公平性、記錄資料來源、控制隱私洩露量。*
> *不做治理不是「省力」，是把合規風險、偏見訴訟、資料外洩的成本推遲到最貴的時間點——上線之後。*
> *工程師不需要成為法律專家，但必須懂得把監管義務翻譯成系統元件和可量測的指標。*

---

這篇給被 PM 一句「先上線再合規」推上火線的工程師看。全文用一個貫穿的例子：要在 EU 市場推出的信用評分 AI 系統，資料集裡有性別與種族的代理變數，CTO 問最低限度要做哪些治理元件才能在 EU AI Act 下合法營運。讀完你會能把監管義務翻譯成系統元件與可量測指標：挑對公平性指標並在 CI 裡擋住不合格的模型、用差分隱私與聯邦學習處理 GDPR 的資料限制、用 SHAP 產出監管接受的解釋，並讓 Model Card 與影響評估從 pipeline 自動生成。

---

## 一、核心問題：AI 治理為什麼是工程師的問題

AI 治理在過去五年從「道德宣示」進化為「法律義務」。EU AI Act 在 2024 年 8 月正式生效，禁止條款自 2025 年 2 月起適用、通用目的 AI（GPAI）模型義務自 2025 年 8 月起適用，高風險系統原定 2026 年 8 月進入強制合規期；NIST AI RMF 則是美國最常被引用的自願性風險框架。其他地區路線不一：中國已推出生成式 AI 管理辦法，英國採取由既有監管機關執行的原則式路線、沒有專門的 AI 法，加拿大的 AIDA 法案則隨 C-27 法案於 2025 年初失效。

**工程師為什麼不能把這件事推給法務？**

1. **合規義務落在系統層**：EU AI Act Article 9 要求「risk management system」必須以技術文件佐證，不是 policy PDF，是可追溯的程式碼和日誌
2. **偏見來自資料 pipeline**：統計公平性的破壞點在特徵工程、訓練集採樣、評估集分割——法務無法在那裡插手
3. **隱私洩露是技術問題**：差分隱私的 epsilon 預算、聯邦學習的梯度聚合——這些是數學和工程，不是合約條款
4. **稽核需要系統支撐**：監管機關要看 model card、訓練資料來源、版本歷史、A/B 決策記錄——這些必須在 CI/CD 裡自動生成

**信用評分這個域的具體風險：**
- EU AI Act 分類：高風險（Annex III, 5b — access to essential private services）
- GDPR Article 22：禁止純自動化決策影響個人法律地位，除非有明確告知和申訴機制
- 美國 FCRA/ECOA：對抵押貸款、信用卡的公平貸款義務，違規罰款可達 $1M/天
- 偏見訴訟：美國近年已有多起 AI 信用歧視集體訴訟，和解金可達數千萬美元（示意量級）

---

## 二、何時該升級：從手寫文件到自動化合規、再到聯邦與即時監控的觸發條件

最省事的起點是三份文件加一條日誌：訓練資料的資料卡（來源、日期、授權、人口統計分佈）、手寫的 Model Card（評估資料集、已知限制）、推論服務的基本決策日誌（input hash、output、timestamp、user_id），公平性每季人工評估一次。這能回答「這個決策從哪來」，足夠做受控測試。該升級的訊號很明確：系統落入 EU AI Act Annex III 的高風險類別並開始對真實申請者做決策、GDPR Article 22 的解釋權與申訴義務開始適用、或是第一次要面對第三方稽核。這時把公平性評估接進訓練 pipeline（Fairlearn 約束 + Demographic Parity / Equalized Odds 自動量測，§四）、訓練改用差分隱私（§五）、推論端加上 SHAP 解釋與申訴 API（§六）、決策日誌全量保存 5 年，Model Card 改由 CI 自動生成（§七）。Article 9 要的「持續風險監控」，手動季報是做不到的。

第二道門檻是**資料與市場的邊界**：當訓練資料分散在多家機構、因資料主權或跨境傳輸限制不能集中，就需要聯邦學習加安全聚合與 DP（§五）；當偏見不再是訓練時的一次量測、而會隨申請人口變化漂移，就需要把 DP gap 與群體 AUC 落差接上即時告警；當同時面對 EU、US 等多套法規，就值得讓技術文件、System Card 與影響評估由監管報告生成器自動產出。這一層的成本在 §九 的表裡約是前一層的 6 倍，值不值得取決於罰款上限與市場准入，不取決於用戶數。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| 資料卡 + 手寫 Model Card + 基本決策日誌 | Pipeline 內公平性約束 + DP 訓練 + SHAP 解釋 + 申訴 API + CI 生成 Model Card | 落入 Annex III 高風險並對真實申請者決策；GDPR Art. 22 解釋權適用；面臨第三方稽核 |
| 集中式訓練 | 聯邦學習 + 安全聚合 + DP 預算追蹤 | 資料分散在多家機構且不能集中（資料主權、跨境傳輸限制） |
| 季度人工公平性報告 | 即時公平性監控 + 自動監管報告 | 偏見隨申請人口漂移；同時面對多套法規；Article 11 技術文件需每次部署更新 |

---

## 三、監管框架：EU AI Act / NIST AI RMF 的工程義務

### EU AI Act 風險分層

```
┌──────────────────────────────────────────────────────────────────┐
│  EU AI Act 風險金字塔                                            │
│                                                                  │
│              ┌─────────────────┐                                │
│              │  不可接受風險   │ ← 禁止：社會評分、即時生物辨識│
│              │  Unacceptable   │   強制執行：2025/2/2 生效      │
│              └────────┬────────┘                                │
│         ┌─────────────┴──────────────┐                         │
│         │      高風險（Annex III）    │ ← 信用評分、就業篩選   │
│         │      High Risk             │   醫療診斷、教育評估    │
│         │  義務：技術文件、人工監督  │   強制執行：2026/8/2*  │
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

\* 2025 年 11 月歐盟執委會提出的 Digital Omnibus 方案，擬將 Annex III 高風險義務延後（最晚至 2027 年底）。實際適用日期請以最新立法進度與歐盟官方公報為準。

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

**這些指標無法同時滿足**：Chouldechova（2017）與 Kleinberg et al.（2016）證明，只要各群體的基礎率不同，校準（Calibration）與錯誤率平衡（Equalized Odds）就不可能同時成立；工程師必須根據應用場景選擇。

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

    # 判斷是否觸發告警（0.1 是業界常用的經驗門檻，並非 EU AI Act 規定的數值）
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
│  - 梯度注入 DP 噪音（每輪 ε≈0.05；高斯機制在 RDP 下約按 √k │
│    合成，100 輪後總 ε≈0.5，才對得上 ε=0.5 的全域預算）     │
│  - Moments Accountant 追蹤累積 ε 預算                       │
│                                                              │
│  GDPR 合規點：                                               │
│  - Article 44（跨境傳輸）：梯度可被反推出訓練資料，不能當作 │
│    非個人資料；靠安全聚合 + DP 才站得住跨境傳輸             │
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
    dp_gap_ethnicity: 0.071         # 族裔（已觸發緩解流程）
  performance_by_group:
    male_auc: 0.851
    female_auc: 0.838  # 差距 1.3%，在可接受範圍

limitations:
  - "對申請資料少於 6 個月的新用戶準確度下降 12%"
  - "族裔 DP gap 0.071 已超過內部閾值 0.05，正在進行緩解"

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

兩個選擇用文字交代。偏見緩解的時機：§四 的三層表已經給了取捨——前處理（Reweighing、Disparate Impact Remover）不改模型、任何模型可用、處理後的資料集本身就能向稽核者解釋，是預設起點；只有資料集太小（< 10K，重採樣會過擬合）或保護屬性在資料層不可得、只有代理變數時，才必須在訓練中處理（Fairlearn Reduction、對抗解偏），代價是訓練時間 2–3x 與更難控制的公平性–準確度 tradeoff。聯邦學習框架：Flower 生產就緒、節點異質性支援好、gRPC 通訊、內建 DP（透過 Opacus）；PySyft 適合需要 MPC / HE 這類更靈活密碼協定的研究場景，API 穩定度與文件完整度都還不適合直接上生產。下面四個決策才真的需要權衡。

### 決策 1：公平性約束 — Fairlearn Reduction vs 後處理閾值調整

| 選擇 | 選 Fairlearn Reduction 的理由 | 不選後處理閾值的理由 |
|------|------------------------------|---------------------|
| 修正位置 | 訓練時同時優化準確度和公平性，產出 Pareto 最優解集合 | 只修改輸出，不修正模型內部的偏見來源 |
| 推論需求 | 不需要保護屬性在推論時可用 | 閾值按群體不同，推論時必須拿到保護屬性，GDPR 限制多 |
| 效果 | EO gap 降幅更大（~50% vs ~30%） | 降幅較小 |

**flip condition**：如果模型已上線且重訓成本極高（> $50K），或監管要求立即修正，後處理閾值調整可作為緊急措施，重訓後替換。

---

### 決策 2：隱私預算 — ε=1.0 vs ε=0.1

| 選擇 | 選 ε=1.0 的理由 | 不選 ε=0.1 的理由 |
|------|----------------|------------------|
| 可用性 | 業界金融場景常用值；AUC 損失可控（~0.5–1%）；梯度統計仍有意義 | 噪音過大：10K 樣本下 DP gap 測量誤差 > 10% |
| 訓練成本 | 收斂正常 | 模型收斂速度慢 3–5x |
| 保護強度 | 公開 ML 競賽資料可接受 | 實際提供的隱私保護比直覺好得多（攻擊成本提高 e^0.9） |

**flip condition**：醫療記錄或敏感政治資料，ε ≤ 0.5；敏感度分析顯示模型對個別記錄的敏感度高時，降低 ε。

---

### 決策 3：解釋方法 — TreeSHAP vs LIME

| 選擇 | 選 TreeSHAP 的理由 | 不選 LIME 的理由 |
|------|-------------------|-----------------|
| 一致性 | 有唯一的數學解（Shapley 值），可重現，audit trail 完整 | 每次解釋可能不一致（同一筆記錄解釋可能不同），採樣依賴，邊界案例不穩定 |
| 速度 | < 10ms/樣本 | ~50ms/樣本 |
| 監管接受度 | 全局和局部解釋統一框架，已在多個 EU 監管案例被接受 | 監管機關質疑不可重現的解釋 |

**flip condition**：模型是 LLM 或 neural network 且沒有樹狀結構，用 KernelSHAP 或 DeepSHAP；解釋速度要求 < 1ms（即時系統），考慮預先批次計算 SHAP。

---

### 決策 4：稽核日誌儲存 — 不可變物件儲存 vs 關聯式資料庫

| 選擇 | 選不可變物件儲存的理由 | 不選 RDBMS 的理由 |
|------|----------------------|------------------|
| 不可變性 | S3 Object Lock 的 WORM 原生合規（SEC 17a-4 標準） | UPDATE/DELETE 會破壞不可變性，EU AI Act 要求日誌不可篡改 |
| 成本 | $0.023/GB vs $0.10/GB；Parquet 壓縮再省 70% | 5 年保存期：100GB/月 × 60 個月 = 6TB，RDBMS 費用高 |
| 存取模式 | 並發寫入無鎖爭用；稽核查詢是批次掃描 | OLTP 能力在這裡用不到 |

**flip condition**：如果監管要求即時查詢個別決策（申訴場景），在不可變儲存之外加一個 DynamoDB 索引（存 decision_id + S3 pointer）即可，不需要把全量日誌放 RDBMS。

---

## 九、系統效應

### 無治理 vs 合規架構的量化比較

| 指標 | 無治理 | 合規架構（DP + 公平性 + 申訴） | 企業級（聯邦 + 即時監控） |
|------|--------|-----------------|---------------|
| **監管罰款風險** | EU AI Act：禁止行為最高 €35M 或全球營收 7%；違反高風險義務最高 €15M 或 3% | 大幅降低，有技術文件佐證 | 近零（持續合規） |
| **GDPR 違規風險** | 高（集中式訓練，PII 無保護） | 中（DP 保護，但仍集中） | 低（聯邦學習 + DP） |
| **偏見訴訟成本** | 集體訴訟平均 $15M–$98M 和解 | 有文件記錄，訴訟風險 -70% | 即時監控，事前干預 |
| **Demographic Parity gap** | 通常 0.10–0.25（未量測）| 0.04–0.08（有緩解）| < 0.05（持續監控） |
| **監管准入** | EU 高風險市場：禁止部署 | 可部署（基本義務滿足） | 可進入 US Federal 採購 |
| **技術文件完整度** | 0%（無文件） | 80%（自動 + 手動）| 99%（全自動 CI 生成） |
| **決策可追溯性** | 無（或不完整） | 100%（5 年保存）| 100% + 即時查詢（< 50ms） |
| **申訴處理時間** | 無機制（法規要求 30 天內）| 手動 5–10 天 | 自動化 < 24 小時 |
| **信任指標（用戶調查）** | 基準：42% 信任 AI 決策 | +18%（有解釋）| +35%（透明 + 申訴機制）|
| **工程成本/月** | $0 治理成本（但隱藏風險） | $2,500 | $15,000 |
| **市場准入價值** | EU 市場：$0（不合法）| 可進入 EU 高風險市場（金額依業務而定） | EU + US Federal 採購（金額依業務而定） |

> *除罰款上限引自 EU AI Act 條文外，表中其餘數字為示意估算，非實測數據。*

**關鍵洞察**：合規架構的 $2,500/月治理成本，相對於 EU AI Act 罰款（違反高風險義務最高可達 €15M 或全球營收 3%）的風險，ROI 無庸置疑。企業級的 $15,000/月適用於年收入超過 $5M 的高風險 AI 服務。

---

## 十、系列導航

| | |
|---|---|
| ← 上一篇 | [Phase 18 Part 1：AI 技術安全 — 讓模型行為符合人類意圖](/posts/ai-eng-from-scratch-phase18-part1-technical-safety-zh/) |
| → 下一篇 | [Phase 19 Part 1：Capstone — 企業級 RAG 知識庫系統端對端實作](/posts/ai-eng-from-scratch-phase19-part1-capstone-rag-system-zh/) |

---

*本文為「AI 工程從零開始」系列 Phase 18 Part 2。所有監管引用以 2026 年 6 月為準，EU AI Act 強制合規時程以歐盟官方公報為準。系列總覽：[AI 工程從零開始](/tags/ai-eng-from-scratch/)。*
