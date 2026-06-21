---
title: "AI 工程從零開始｜Phase 2 Part 2：集成學習與最佳化 — 超越單一模型的上限"
date: 2026-06-21T10:30:00+08:00
draft: false
weight: 4
description: "深入解析 Random Forest、Gradient Boosting、XGBoost、超參數調優與 AutoML，理解集成方法為何在表格資料競賽與生產系統持續稱霸"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Machine Learning", "XGBoost", "Random Forest", "Gradient Boosting", "Optimization", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師遇到瓶頸時，會去換一個更複雜的模型。*
> *真正的做法是：把多個「夠好的模型」組合起來。*
> *單棵決策樹 Accuracy 70%，一千棵樹投票後達到 91%。*
> *集成不是魔法，而是偏差–變異數分解的數學必然。*

---

## 面試情境

> **面試官：** 你們公司的信用風險模型已上線，目前用單一 XGBoost，AUC 0.84。產品希望 AUC 提升到 0.88 以上，但訓練資料不能增加、特徵工程已飽和。請說明你會採取哪些策略，並解釋為什麼選擇這些方法而非其他替代方案？推論延遲需維持在 50ms 以內，每日預測量約 500 萬次。

---

## 一、核心問題：單一模型的天花板與集成的突破

### 1.1 偏差–變異數困境

機器學習的核心矛盾可以用一個公式描述：

```
期望錯誤 = Bias² + Variance + 不可減少的噪音
```

**高偏差（High Bias）**：模型太簡單，欠擬合。線性回歸在非線性問題上的典型症狀。
**高變異數（High Variance）**：模型太複雜，過擬合。深度決策樹在小資料集的典型症狀。

單一模型在這條光譜上只能找到一個平衡點。你無法同時大幅降低偏差和變異數——除非你使用集成方法。

### 1.2 為什麼集成能突破天花板

**Bagging（自助聚合）** 降低變異數：
- 對同一資料集做多次 bootstrap 取樣
- 每個子模型看到不同的資料子集，學到不同的模式
- N 個獨立模型的平均值，變異數是單模型的 1/N（若模型間相關性為 0）

**Boosting（提升法）** 降低偏差：
- 序列訓練，每個新模型專注修正前一個模型的錯誤
- 把 N 個「弱學習器（Weak Learner）」串聯，逼近任意複雜的函數

**Stacking（堆疊）** 同時降低偏差與變異數：
- 不同類型的模型抓到不同的資料模式
- Meta-learner 學習如何最佳組合這些互補的預測

### 1.3 實際數字

| 方法 | 典型 AUC 提升幅度 | 訓練時間倍增 | 推論時間倍增 |
|------|-------------------|--------------|--------------|
| 單一決策樹 → Random Forest | +0.05 ~ +0.12 | 50–200x | 50–200x |
| 單一 GBM → XGBoost | +0.02 ~ +0.06 | 基準 | 基準 |
| XGBoost → Stacking | +0.01 ~ +0.04 | +30% | +50–100% |
| 加入 AutoML 搜索 | +0.01 ~ +0.03 | +5–20x | 不變 |

Kaggle 競賽統計：從 2015 到 2023 年，表格資料競賽中 XGBoost 或 LightGBM 出現在前 10 名解法的比例超過 75%。

---

## 二、三個演進階段：集成方法的複雜度演進

### ╔══ Phase 1：POC / < 10K 訓練樣本 ══╗

**目標：** 快速驗證特徵工程有效，建立基準分數。

```
┌──────────────────────────────────────────────────────┐
│  Phase 1 架構：單一強模型 + 基本調參                  │
│                                                      │
│  原始特徵                                            │
│      │                                               │
│      ▼                                               │
│  ┌──────────┐    sklearn                             │
│  │ RandomForest│  n_estimators=100                   │
│  │ (預設參數) │  預設參數即可                         │
│  └──────────┘                                        │
│      │                                               │
│      ▼                                               │
│  預測結果 + feature_importances_                     │
│                                                      │
│  接受的捷徑：不做 CV、不調參、不做 Stacking           │
│  快速交付：1–2 天可出結果                             │
└──────────────────────────────────────────────────────┘
```

**新增元件：** sklearn RandomForest、基本 train/test split
**成本：** 幾乎為零，筆電即可跑完
**解決的問題：** 確認特徵有訊號，提供特徵重要性排名
**尚存的問題：** 過擬合風險高，無法估計泛化誤差

---

### ╔══ Phase 2：MVP / 10K–500K 樣本 ══╗

**目標：** 生產可用的模型，可以安全部署、監控、再訓練。

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 2 架構：XGBoost + K-Fold CV + Bayesian 調參            │
│                                                              │
│  特徵工程管線                                                 │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────────────┐                │
│  │  Stratified K-Fold CV (K=5)             │                │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │                │
│  │  │Fold1 │ │Fold2 │ │Fold3 │ │Fold4 │  │                │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘  │                │
│  └─────┼────────┼────────┼────────┼───────┘                │
│        │        │        │        │                         │
│        ▼        ▼        ▼        ▼                         │
│  ┌──────────────────────────────────────┐                   │
│  │  XGBoost (Bayesian HPO via Optuna)   │                   │
│  │  n_trials=50, 目標：AUC CV mean      │                   │
│  └──────────────────────────────────────┘                   │
│        │                                                    │
│        ▼                                                    │
│  SHAP 解釋 + MLflow 追蹤                                    │
│                                                              │
│  新增：Optuna、SHAP、MLflow、早停（early_stopping_rounds）   │
│  成本：單台 GPU/CPU，訓練幾小時                              │
└──────────────────────────────────────────────────────────────┘
```

**新增元件：** Optuna HPO、SHAP 解釋、MLflow 實驗追蹤、早停機制
**成本：** 單台 8-core 機器，訓練成本 < $5
**解決的問題：** 過擬合受控，有可重現的實驗，可解釋性滿足監管需求
**尚存的問題：** 單模型仍有天花板，無法平行化大規模搜索

---

### ╔══ Phase 3：Scale / 500K–10M+ 樣本 ══╗

**目標：** 多模型集成、分散式訓練、自動化 ML 管線、推論優化。

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3 架構：Stacking Ensemble + 分散式訓練 + 推論快取         │
│                                                                 │
│  資料管線（Spark / Dask）                                        │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 0：Base Learners（並行訓練）                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │   │
│  │  │ XGBoost  │  │LightGBM  │  │CatBoost  │              │   │
│  │  │ (OOF pred│  │(OOF pred)│  │(OOF pred)│              │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘              │   │
│  │       └─────────────┼─────────────┘                     │   │
│  │                     ▼                                   │   │
│  │  ┌──────────────────────────────┐                       │   │
│  │  │  Layer 1：Meta-Learner        │                       │   │
│  │  │  Logistic Regression / Ridge  │                       │   │
│  │  │  (在 OOF 預測上訓練)          │                       │   │
│  │  └──────────────────────────────┘                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌───────────────────────────────┐                             │
│  │  推論服務                      │                             │
│  │  ┌─────────────────────────┐  │                             │
│  │  │  模型壓縮（ONNX export）  │  │                             │
│  │  │  特徵快取（Redis 5ms）   │  │                             │
│  │  │  推論快取（Bloom filter） │  │                             │
│  │  └─────────────────────────┘  │                             │
│  └───────────────────────────────┘                             │
│                                                                 │
│  新增：Ray/Dask 分散式訓練、ONNX 模型壓縮、推論快取              │
│  成本：$50–$500/訓練週期，推論 < $0.001 / 千次                  │
└─────────────────────────────────────────────────────────────────┘
```

**新增元件：** Ray Tune 分散式 HPO、ONNX Runtime、Redis 特徵快取、模型監控
**成本：** 訓練：$50–$500/週期；推論：< $0.001/千次預測
**解決的問題：** 突破單模型天花板，達到接近理論上限的精度
**尚存的問題：** 維護複雜度高，需要 ML Platform 支撐

---

## 三、Bagging 與 Random Forest

### 3.1 Bootstrap Aggregating 原理

Bagging 的核心想法：如果一個模型在不同的訓練資料子集上有不同的預測，我們可以透過平均（回歸）或投票（分類）來降低這個不穩定性。

```
完整訓練集（N 筆）
        │
        ├──▶ Bootstrap 樣本 1（N 筆，有重複取樣）──▶ 樹 1
        ├──▶ Bootstrap 樣本 2（N 筆，有重複取樣）──▶ 樹 2
        ├──▶ Bootstrap 樣本 3（N 筆，有重複取樣）──▶ 樹 3
        │                  ...
        └──▶ Bootstrap 樣本 T（N 筆，有重複取樣）──▶ 樹 T
                                                      │
                                                      ▼
                                              多數投票 / 平均
                                                      │
                                                      ▼
                                                 最終預測
```

**數學保證：** 若 T 個模型的錯誤率均為 e < 0.5，且模型間獨立，集成錯誤率遠低於 e。  
當 T=100，e=0.3 時，集成錯誤率 ≈ 0.001（二項分布尾端概率）。

### 3.2 Random Forest 的關鍵改進：特徵隨機性

Random Forest 在 Bagging 的基礎上加了一個關鍵操作：**每個節點分裂時，只從隨機選取的 m 個特徵中找最佳分裂點**（m ≈ √p，p 為總特徵數）。

這樣做的效果：
- 強制降低樹與樹之間的相關性（相關性越低，集成效益越大）
- 即使有少數非常強的特徵，每棵樹也會被迫使用其他特徵
- 自動起到正則化效果

### 3.3 Out-of-Bag (OOB) 誤差

Bootstrap 取樣時，平均約有 36.8% 的資料不被選中（即 OOB 樣本）。Random Forest 可以用這些樣本做免費的驗證集，不需要額外切分。

```python
from sklearn.ensemble import RandomForestClassifier

rf = RandomForestClassifier(
    n_estimators=500,      # 樹的數量，越多越好但邊際效益遞減
    max_features='sqrt',   # 每個節點隨機選取的特徵數
    max_depth=None,        # 讓樹充分生長（Bagging 需要低偏差的基學習器）
    min_samples_leaf=1,
    oob_score=True,        # 啟用 OOB 估計
    n_jobs=-1,             # 並行所有 CPU 核心
    random_state=42
)
rf.fit(X_train, y_train)
print(f"OOB Score: {rf.oob_score_:.4f}")  # 接近 CV Score
```

### 3.4 Random Forest 調參的優先順序

1. **n_estimators**：更多通常更好，但超過 500 棵邊際效益極低。訓練時間線性增加。
2. **max_features**：分類問題用 `sqrt`，回歸問題用 `1/3`。這是最重要的超參數。
3. **max_depth / min_samples_leaf**：控制每棵樹的複雜度。小資料集可以加限制防過擬合。
4. **class_weight**：類別不平衡時設為 `balanced`，效果顯著。

**關鍵洞見：** Random Forest 對超參數相對不敏感，預設值通常能達到 80% 的最佳效果。XGBoost 則對超參數非常敏感，必須認真調參。

---

## 四、Boosting 家族：AdaBoost → GBM → XGBoost → LightGBM

### 4.1 Boosting 的核心思想

Boosting 是序列集成：每個新模型專注於前面模型犯錯的樣本。

```
輪次 1：訓練模型 M1（所有樣本等權重）
        ↓
        計算錯誤樣本，給予更高權重
        ↓
輪次 2：訓練模型 M2（錯誤樣本權重更高）
        ↓
        再次計算，調整權重
        ↓
輪次 T：訓練模型 MT（聚焦於最難分類的樣本）
        ↓
最終預測 = 加權投票（M1, M2, ... MT）
```

### 4.2 AdaBoost（2001）

**核心機制：** 調整樣本權重，讓後續模型專注困難樣本。
**優點：** 理論優美，可以證明訓練誤差指數衰減。
**缺點：** 對噪音和異常值極敏感（異常值會獲得極高權重）；只能用淺樹（深度 1–3）。
**現狀：** 已基本被 GBM 系列取代，但仍有教學價值。

### 4.3 Gradient Boosting Machine（GBM）

Friedman（2001）的突破：把 Boosting 轉化為數值最佳化問題。

**核心思想：**
1. 定義一個損失函數 L(y, F(x))
2. 每個新的樹擬合**當前損失函數對預測值的負梯度**（偽殘差）
3. 沿梯度方向更新模型

```
F_0(x) = argmin_γ Σ L(y_i, γ)    # 初始化（如均值）

For m = 1 to M:
    r_im = -[∂L(y_i, F(x_i))/∂F(x_i)]  # 計算偽殘差（負梯度）
    訓練決策樹 h_m 擬合 {(x_i, r_im)}    # 樹擬合殘差
    F_m(x) = F_{m-1}(x) + η * h_m(x)    # 更新（η 為學習率）
```

**關鍵優點：** 可以使用任意可微的損失函數（MAE、Huber、log loss、自定義損失）。

### 4.4 XGBoost（2016）：工程最佳化的里程碑

XGBoost 在 GBM 的理論基礎上做了大量工程改進，使其成為 Kaggle 競賽最常見的勝利模型。

**關鍵改進：**

| 改進項目 | 細節 | 效果 |
|---------|------|------|
| 正則化項 | 目標函數加入 L1/L2 正則化葉子權重 | 減少過擬合 |
| 二階泰勒展開 | 使用梯度和 Hessian（二階導數） | 收斂更快、更精確 |
| 列塊（Column Block）| 特徵預排序並快取 | 訓練速度提升 5–10x |
| 稀疏感知 | 自動處理缺失值 | 無需手動填補 |
| 並行化 | 特徵分裂點搜索並行 | GPU 加速支援 |

**關鍵超參數：**

```python
import xgboost as xgb

params = {
    'n_estimators': 1000,        # 樹的數量（配合早停使用）
    'learning_rate': 0.05,       # 學習率，越小越好但需要更多樹
    'max_depth': 6,              # 單棵樹深度，典型範圍 3–10
    'subsample': 0.8,            # 行取樣比例（Stochastic GB）
    'colsample_bytree': 0.8,     # 列取樣比例
    'min_child_weight': 1,       # 最小葉子樣本權重和
    'gamma': 0,                  # 分裂最小損失減少量
    'reg_alpha': 0,              # L1 正則化
    'reg_lambda': 1,             # L2 正則化
    'early_stopping_rounds': 50  # 連續 50 輪無改善則停止
}

model = xgb.XGBClassifier(**params, eval_metric='auc')
model.fit(X_train, y_train,
          eval_set=[(X_val, y_val)],
          verbose=100)
```

### 4.5 LightGBM（2017）：速度優先

微軟研究院提出兩個關鍵演算法：

**GOSS（Gradient-based One-Side Sampling）：**
- 保留所有高梯度樣本（難以擬合的）
- 只取樣低梯度樣本的一個小子集
- 效果：在精度幾乎不變的情況下，資料量減少 80%

**EFB（Exclusive Feature Bundling）：**
- 把互斥的稀疏特徵（同時非零的機率低）捆綁在一起
- 效果：特徵數量從 M 降到 O(M/k)，k 為平均互斥組大小

**實測數字：**
- 在 1000 萬筆資料上，LightGBM 訓練速度比 XGBoost 快 **10–20x**
- 記憶體使用量約為 XGBoost 的 **40–60%**
- AUC 差異通常在 0.001–0.003 之間（可忽略）

### 4.6 CatBoost（2018）：類別特徵的解決方案

Yandex 針對類別特徵設計的 Boosting：
- 原生支援類別特徵，無需 One-Hot Encoding
- 使用 Ordered Boosting 解決 Target Leakage 問題
- 在類別特徵多的資料集（如廣告點擊率預測），通常優於 XGBoost/LightGBM 2–5%

---

## 五、Stacking 與 Blending 架構

### 5.1 Stacking 原理

Stacking 的核心思想：用模型的預測作為另一個模型的特徵。

```
┌─────────────────────────────────────────────────────────────┐
│  Stacking 架構詳解                                           │
│                                                             │
│  訓練資料（N 筆）                                            │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  K-Fold Cross-Validation 生成 Out-of-Fold 預測        │   │
│  │                                                      │   │
│  │  Fold 1,2,3,4 → 訓練 Base Model 1 → OOF Pred on 5  │   │
│  │  Fold 1,2,3,5 → 訓練 Base Model 1 → OOF Pred on 4  │   │
│  │  ...（重複 K 次）                                    │   │
│  │                                                      │   │
│  │  結果：N 筆 OOF 預測（無資料洩漏！）                  │   │
│  └──────────────────────────────────────────────────────┘   │
│         │         │         │                               │
│    Model 1    Model 2    Model 3                            │
│    (XGBoost) (LightGBM) (RandomForest)                     │
│    OOF Pred  OOF Pred   OOF Pred                           │
│         │         │         │                               │
│         └─────────┴─────────┘                               │
│                   │                                         │
│                   ▼                                         │
│         ┌─────────────────┐                                 │
│         │  Meta-Learner   │  輸入：[P1, P2, P3, 原始特徵]  │
│         │  (LogisticReg / │                                 │
│         │   Ridge / NN)   │                                 │
│         └─────────────────┘                                 │
│                   │                                         │
│                   ▼                                         │
│             最終預測                                         │
└─────────────────────────────────────────────────────────────┘
```

**防止資料洩漏的關鍵：** 必須使用 OOF（Out-of-Fold）預測訓練 Meta-Learner，不能直接用訓練集預測。若直接用訓練集，Meta-Learner 看到的是「幾乎完美」的預測，學到的是無效的映射。

### 5.2 Blending vs Stacking

**Blending（更簡單）：**
- 留出一個 Holdout 集（通常 20%）
- 在剩餘 80% 訓練 Base Learners
- 用 Holdout 集的預測訓練 Meta-Learner
- 優點：實作簡單，訓練快
- 缺點：浪費 20% 訓練資料，穩定性不如 OOF

**Stacking（更穩健）：**
- 使用完整訓練集（通過 K-Fold）
- OOF 預測覆蓋全部訓練資料
- 優點：資料利用率高，估計更準確
- 缺點：訓練時間是 K 倍

### 5.3 Stacking 的實作要點

```python
from sklearn.model_selection import cross_val_predict
from sklearn.linear_model import LogisticRegression
import numpy as np

# Base Learners
base_models = [xgb_model, lgbm_model, rf_model]

# 生成 OOF 預測（Layer 0 輸出）
oof_predictions = np.column_stack([
    cross_val_predict(model, X_train, y_train,
                      cv=5, method='predict_proba')[:, 1]
    for model in base_models
])

# 也需要在測試集上的預測（用完整訓練集 refit）
test_predictions = np.column_stack([
    model.fit(X_train, y_train).predict_proba(X_test)[:, 1]
    for model in base_models
])

# Meta-Learner（保持簡單，避免過擬合）
meta_learner = LogisticRegression(C=0.1)  # L2 正則化
meta_learner.fit(oof_predictions, y_train)

# 最終預測
final_pred = meta_learner.predict_proba(test_predictions)[:, 1]
```

**Meta-Learner 的選擇原則：** 保持簡單（Logistic Regression、Ridge、小型 MLP），不要用複雜模型，否則 Meta-Learner 本身會過擬合。

---

## 六、超參數調優：Grid / Random / Bayesian 搜索

### 6.1 三種搜索策略的比較

```
搜索空間（二維示意）

        參數 B
         ▲
         │  . . . . .    ← Grid Search：均勻覆蓋
         │  . . . . .       每個點都測試
         │  . . . . .       10 個值 × 10 個值 = 100 次
         │
         │  * *   *         ← Random Search：隨機取樣
         │    * *  *           同樣 100 次，但覆蓋範圍更廣
         │  *   *  *           對「只有部分參數重要」的問題更優
         │
         │  ●→●→●             ← Bayesian Search：序列決策
         │       ↘●              每次利用歷史結果決定下一個點
         │         ●             在重要區域加密探索
         └────────────────▶
                        參數 A
```

### 6.2 Grid Search：當搜索空間小且每個參數都重要

```python
from sklearn.model_selection import GridSearchCV

param_grid = {
    'max_depth': [3, 5, 7],
    'learning_rate': [0.01, 0.05, 0.1],
    'n_estimators': [100, 300, 500]
}
# 27 組組合 × 5-fold CV = 135 次訓練

grid_search = GridSearchCV(
    xgb.XGBClassifier(),
    param_grid,
    cv=5,
    scoring='roc_auc',
    n_jobs=-1
)
```

**適用場景：** 參數少（< 4 個），每個參數的重要性已知，搜索空間小於 200 組。

### 6.3 Random Search：第一次搜索的首選

Bergstra & Bengio（2012）證明：若只有少數參數真正重要，Random Search 用相同次數能找到更好的解。

```python
from sklearn.model_selection import RandomizedSearchCV
from scipy.stats import uniform, randint

param_dist = {
    'max_depth': randint(3, 12),
    'learning_rate': uniform(0.01, 0.19),
    'n_estimators': randint(100, 1000),
    'subsample': uniform(0.6, 0.4),
    'colsample_bytree': uniform(0.6, 0.4),
    'min_child_weight': randint(1, 10),
    'gamma': uniform(0, 0.5)
}

random_search = RandomizedSearchCV(
    xgb.XGBClassifier(early_stopping_rounds=50),
    param_distributions=param_dist,
    n_iter=50,          # 50 次隨機組合（比 Grid 的 10,000+ 次少得多）
    cv=5,
    scoring='roc_auc',
    n_jobs=-1
)
```

### 6.4 Bayesian Optimization（Optuna）：生產推薦

Optuna 使用 Tree-structured Parzen Estimator（TPE）演算法，維護一個「哪些超參數組合有前途」的概率模型，逐步在好的區域加密搜索。

```python
import optuna
from sklearn.model_selection import cross_val_score

def objective(trial):
    params = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
        'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 1.0, log=True),
        'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 1.0, log=True),
    }
    model = xgb.XGBClassifier(**params, eval_metric='auc')
    score = cross_val_score(model, X_train, y_train, cv=5, scoring='roc_auc')
    return score.mean()

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100, timeout=3600)  # 100 次試驗或 1 小時

print(f"Best AUC: {study.best_value:.4f}")
print(f"Best params: {study.best_params}")
```

**Optuna 相比手動調參的實測效益：**
- 50 次 Bayesian 試驗通常優於 200 次 Grid Search
- 自動剪枝（Pruning）：表現差的試驗提前終止，節省 30–50% 計算時間
- 可並行化：`n_jobs=-1` 或透過 Ray Tune 橫向擴展

### 6.5 調參的實用技巧

**學習率與樹的數量的關係：** 先用大學習率（0.1）找大概範圍，確定其他參數後，降低學習率（0.01–0.05）並增加 n_estimators，通常能再提升 AUC 0.003–0.008。

**Early Stopping 必用：** 避免過擬合，同時自動找到最佳 n_estimators。

```python
# 正確使用 Early Stopping 的方式
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    early_stopping_rounds=50,    # 50 輪無改善則停
    verbose=False
)
best_n = model.best_ntree_limit  # 記錄最佳輪次
```

---

## 七、模型壓縮與部署考量

### 7.1 集成模型的推論挑戰

一個包含 3 個 Base Learners（各 500 棵樹）+ Meta-Learner 的 Stacking 模型：
- 模型文件大小：50–200 MB
- 單次推論時間：CPU 上 5–50ms（取決於樹的深度）
- 500 萬次/日 = 58 次/秒，需要 p99 < 50ms

### 7.2 ONNX 導出加速

```python
# XGBoost → ONNX
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

onnx_model = convert_sklearn(
    xgb_model,
    initial_types=[('float_input', FloatTensorType([None, n_features]))]
)

# ONNX Runtime 推論（比原生 Python 快 2–5x）
import onnxruntime as rt
sess = rt.InferenceSession(onnx_model.SerializeToString())
pred = sess.run(['probabilities'], {'float_input': X_test.astype(np.float32)})
```

### 7.3 模型蒸餾（Knowledge Distillation）

當集成模型太大、推論太慢時，用集成模型作為「教師」訓練一個小模型「學生」：

```
集成模型（教師）：AUC 0.88，推論 25ms
       │
       │ 生成軟標籤（Soft Labels）：P(y=1) = 0.73
       ▼
單一 XGBoost（學生）：AUC 0.865，推論 8ms
```

損失函數：`L = α * CrossEntropy(硬標籤) + (1-α) * KL_Divergence(教師軟標籤)`

**實測效果：** 精度損失 1–2%，速度提升 3–5x，適合延遲要求嚴格的場景。

### 7.4 特徵快取策略

對於高頻預測（每秒 > 1000 次），特徵計算往往比模型推論更慢：

```
請求進入
   │
   ▼
Redis 特徵快取（TTL=5分鐘）──命中──▶ 直接推論（< 2ms）
   │ 未命中
   ▼
特徵計算（查資料庫、做聚合）（20–100ms）
   │
   ▼
寫入 Redis 快取
   │
   ▼
模型推論（5–15ms）
```

**效果：** 快取命中率通常 60–80%，整體 p99 延遲從 120ms 降至 20ms。

---

## 八、為什麼選 X 不選 Y

### 決策矩陣

```
選擇              選 X 的理由                  不選 Y 的理由
──────────────────────────────────────────────────────────────
XGBoost          文件成熟，社群龐大              LightGBM：
vs LightGBM      中小資料集（<100萬筆）穩定      數據 < 50 萬筆時速度差距不顯著
                 GPU 加速更成熟                  記憶體效率優勢小資料集不明顯

LightGBM         10M+ 筆資料時快 10–20x          XGBoost：
vs XGBoost       記憶體用量少 40–60%              大資料集訓練瓶頸在 I/O，不在計算
                 類別特徵 native 支援             調參範圍較廣、社群資源較少

Bayesian HPO     50 次試驗 > 200 次 Grid Search  Grid Search：
vs Grid Search   自動剪枝節省 30–50% 計算         搜索空間小（<30 組）時差異不大
                 可加入先驗知識約束搜索範圍        Bayesian 需要安裝額外套件

Stacking         通常 AUC 提升 0.01–0.04         Blending：
vs Blending      OOF 確保無資料洩漏               浪費 20% 訓練資料
                 充分利用所有訓練資料              小資料集（<1萬筆）差距不顯著

ONNX Runtime     推論速度快 2–5x                 原生 Python：
vs 原生推論       跨語言部署（Java/C++ 服務）       開發環境調試更方便
                 記憶體用量更小                   生產環境必須換用 ONNX

模型蒸餾          推論延遲降至 1/3–1/5             直接部署集成：
vs 直接部署       模型文件從 200MB 降至 20MB        精度損失 1–2%（有時不可接受）
集成模型          滿足嚴格 SLA（< 10ms）            蒸餾訓練需要額外工作量
```

**翻轉條件（Flip Condition）：**

- **LightGBM 優於 XGBoost 的條件：** 資料超過 100 萬筆，記憶體有限，或需要快速迭代實驗。
- **Grid Search 優於 Bayesian 的條件：** 只有 2–3 個超參數，且每次訓練不超過 5 分鐘。
- **Blending 優於 Stacking 的條件：** 資料超過 500 萬筆，Stacking 的 K-Fold 訓練時間無法承受。
- **不做蒸餾直接部署的條件：** SLA 寬鬆（> 100ms），或精度要求極高不允許任何損失。

---

## 九、系統效應：單模型 vs 集成的精度/訓練時間/推論成本對比

### 量化比較

| 方案 | AUC | 訓練時間 | 推論延遲（p99）| 推論成本（/百萬次）| 維護複雜度 |
|------|-----|----------|----------------|-------------------|-----------|
| 單一決策樹 | 0.76 | 30 秒 | 2ms | $0.05 | 極低 |
| Random Forest（500棵）| 0.83 | 15 分鐘 | 20ms | $0.80 | 低 |
| 單一 XGBoost（調參後）| 0.86 | 45 分鐘 | 8ms | $0.30 | 低 |
| LightGBM（大資料集）| 0.86 | 5 分鐘 | 6ms | $0.25 | 低 |
| XGBoost + 手動調參 | 0.87 | 3 小時 | 8ms | $0.30 | 中 |
| Stacking（3 個模型）| 0.89 | 8 小時 | 25ms | $1.20 | 高 |
| Stacking + 蒸餾 | 0.875 | 10 小時 | 8ms | $0.30 | 高 |
| AutoML（48 小時）| 0.90 | 48 小時 | 25ms | $1.20 | 極高 |

**決策樹：**
- 推論延遲：2ms → 8ms（+6ms）
- AUC：0.76 → 0.86（+0.10）
- 結論：**幾乎每個生產場景都應該使用 XGBoost，而非裸決策樹**

**XGBoost vs Stacking：**
- AUC：0.86 → 0.89（+0.03）
- 推論延遲：8ms → 25ms（+17ms）
- 成本：$0.30 → $1.20（4x）
- 結論：**只有當 AUC 0.03 差距有實際業務價值（如信用風險、醫療診斷）時才值得**

**Kaggle 競賽 vs 生產系統：**
競賽追求最高精度，Stacking 幾乎必用。生產系統需要平衡精度、延遲、成本、維護。80% 的生產場景，認真調參的單一 XGBoost 已經足夠。

### AUC 提升的業務轉化

以信用風險預測為例（100 萬件申請/年，平均貸款 $5,000，壞帳率 3%）：

| AUC | 每年避免損失 | 差額（vs 0.84 基準）|
|-----|------------|-------------------|
| 0.84（基準）| $600 萬 | — |
| 0.86 | $640 萬 | +$40 萬/年 |
| 0.88 | $680 萬 | +$80 萬/年 |
| 0.90 | $720 萬 | +$120 萬/年 |

**結論：** 從 AUC 0.84 提升到 0.88 在此場景每年多避免 $80 萬損失，支撐一個 ML 工程師的人力成本。

---

## 十、面試答題要點（RKK Model Answer）

### 面試情境回顧

> **問：** 信用風險模型，目前 XGBoost AUC 0.84，目標 0.88+。訓練資料不能增加、特徵工程已飽和。推論延遲 < 50ms，每日 500 萬次預測。

### 模型答案

> *「我會分三步走。第一步，在 48 小時內用 Optuna 做 Bayesian 超參數搜索，100 次試驗通常能讓 AUC 從 0.84 提升到 0.86–0.87，幾乎零成本。第二步，建立 3 個 Base Learners 的 Stacking：XGBoost、LightGBM、CatBoost，用 5-Fold OOF 防止資料洩漏，Meta-Learner 用 Logistic Regression，預期 AUC 再提升 0.01–0.02，達到 0.88 目標。第三步，推論延遲方面，三個模型並行推論後 Meta-Learner 只是一個矩陣乘法，配合 ONNX Runtime 導出和 Redis 特徵快取，p99 應控制在 20–30ms，遠低於 50ms SLA。選 LightGBM 而非第三棵 XGBoost，是因為兩者相關性低、多樣性高，Stacking 效益更大；選 Logistic Regression 作為 Meta-Learner，是因為 Base Learner 輸出的 OOF 預測數量只有 3 列，複雜 Meta-Learner 會過擬合。如果上述步驟後 AUC 仍未達標，我會考慮模型蒸餾：用 Stacking 集成生成軟標籤，訓練單一 XGBoost，精度損失 0.5–1%，但推論延遲降至 8ms，為進一步優化留出空間。」*

### 加分項目

- 提到 **OOF（Out-of-Fold）** 和為何不能直接用訓練集預測作為 Meta-Learner 輸入
- 強調 Base Learners 的**多樣性**（不同演算法 > 同一演算法不同參數）
- 給出**具體數字**：50 次 Bayesian 試驗、5-Fold CV、AUC 提升幅度
- 考慮**業務影響**：AUC 每提升 0.01 對業務有多少實際價值
- 提出**降級方案**：若集成推論太慢，可用蒸餾壓縮到 SLA 要求內

---

## 十一、系列導航

本文是 **AI 工程從零開始** 系列的 Phase 2 Part 2。

| | 文章 | 主題 |
|--|------|------|
| ← 上一篇 | [Phase 2 Part 1：監督學習基礎](/posts/ai-eng-from-scratch-phase2-part1-supervised-learning-zh/) | 線性回歸、決策樹、SVM、模型評估 |
| 本篇 | **Phase 2 Part 2：集成學習與最佳化** | Random Forest、XGBoost、Stacking、Bayesian HPO |
| → 下一篇 | [Phase 3 Part 1：深度學習基礎](/posts/ai-eng-from-scratch-phase3-part1-deep-learning-zh/) | 神經網路、反向傳播、CNN、RNN |

---

> **系列說明：** 本系列基於 [AI Engineering from Scratch](https://github.com/rohitg00/ai-engineering-from-scratch) 課程架構，以繁體中文撰寫，針對每個主題加入生產系統的工程視角、具體數字、以及面試導向的決策框架。

---

*作者：Yen ｜ 發布：2026-06-21 ｜ 閱讀時間：約 23 分鐘*
