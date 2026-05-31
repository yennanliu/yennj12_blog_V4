---
title: "FDE 面試準備指南（八）：ML 基礎必備——從傳統機器學習到 Deep Learning"
date: 2026-05-31T10:30:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，系統整理 FDE 面試不能缺的 ML 基礎：Supervised Learning、評估指標、Overfitting 處理，以及從 MLP 到 Transformer 的 Deep Learning 核心概念"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Machine Learning", "Deep Learning", "Transformer", "XGBoost", "Neural Network", "Interview", "Google"]
authors: ["yen"]
readTime: "18 min"
---

> FDE 不是 ML 研究員，你不需要推導反向傳播的數學。  
> 但你必須在面試官提到 XGBoost、Attention、Regularization 這些詞時，  
> 能夠自然地接話，而不是露出「我需要查一下」的表情。  
> 這篇整理的是「必須熟悉到反應是直覺的」那個程度。

---

## 一、傳統機器學習基礎

### Supervised Learning（監督式學習）

監督式學習的本質：從有標籤的資料中學習一個 mapping function。

```
f(X) → Y

X = 特徵（features）
Y = 標籤（labels）
```

**兩大任務類型：**
- **Regression（回歸）**：Y 是連續值（房價預測、銷售量預測）
- **Classification（分類）**：Y 是離散類別（垃圾郵件判斷、圖片分類）

---

### Linear Regression（線性回歸）

最簡單的回歸模型：

```
ŷ = w₁x₁ + w₂x₂ + ... + wₙxₙ + b
```

訓練目標：最小化 MSE（Mean Squared Error）：
```
MSE = (1/n) × Σ(yᵢ - ŷᵢ)²
```

**面試要能說的重點：**
- 假設特徵和目標之間是線性關係
- 對 outlier 敏感（因為誤差平方放大了異常值的影響）
- 多重共線性（features 之間高度相關）會讓模型不穩定

---

### Logistic Regression（邏輯回歸）

名字有 Regression，但其實是**分類**模型。

把線性組合通過 sigmoid 函數轉成機率：
```
p = sigmoid(w·x + b) = 1 / (1 + e^(-z))
```

輸出的是 P(Y=1|X)，閾值（通常 0.5）決定分類結果。

**面試要能說的重點：**
- 輸出是機率，可解釋性強
- 適合二元分類，可以推廣到 Softmax 做多分類
- 特徵工程（scaling、one-hot encoding）對效果影響大

---

### Random Forest（隨機森林）

Ensemble method：訓練多棵決策樹，用投票（分類）或平均（回歸）得出結果。

兩個核心隨機性：
1. **Bootstrap Sampling**：每棵樹的訓練資料是從原始資料有放回地抽取
2. **Feature Subsampling**：每次分裂時只考慮隨機子集的特徵

**為什麼比單棵決策樹好？**
- 單棵樹容易 overfit，多棵樹平均後方差降低
- 因為各棵樹的相關性低（因為隨機性），集成效果好

**面試要能說的重點：**
- 不需要 feature scaling
- 對缺失值相對 robust
- Feature importance 是個實用工具
- 缺點：計算量大，模型難以解釋（黑盒）

---

### XGBoost（極端梯度提升）

Gradient Boosting 的高效實作，在表格資料上幾乎是最強的模型。

核心思想：**Boosting**——串行訓練，每棵樹專注於修正前面所有樹的殘差。

```
Tree 1 → 預測結果有誤差
Tree 2 → 學習 Tree 1 的誤差
Tree 3 → 學習 Tree 1+2 的誤差
...
Final prediction = 加權所有樹的預測
```

**vs Random Forest：**
| | Random Forest | XGBoost |
|--|---------------|---------|
| 訓練方式 | 並行（各樹獨立） | 串行（逐步改進） |
| Overfitting | 較不容易 | 需要調參 |
| 速度 | 快 | 慢（但有優化） |
| 效果 | 強 | 通常更強 |

**面試要能說的重點：**
- 有正則化（L1, L2），比傳統 Gradient Boosting 不容易 overfit
- 支援缺失值處理
- 超參數多（learning_rate, max_depth, n_estimators），需要調參

---

## 二、評估指標

這部分是面試的送分題，但要答得精確。

---

### 混淆矩陣（Confusion Matrix）

```
                 Predicted Positive  Predicted Negative
Actual Positive       TP                  FN
Actual Negative       FP                  TN
```

- **TP**：真正例（模型說是，實際也是）
- **FP**：假正例（模型說是，實際不是）→ Type I Error
- **FN**：假負例（模型說不是，實際是）→ Type II Error
- **TN**：真負例

---

### Precision vs Recall

```
Precision = TP / (TP + FP)
→ 模型說「是」的，有多少比例真的是？

Recall = TP / (TP + FN)
→ 所有實際「是」的，模型抓到了多少比例？
```

**關鍵 trade-off：**

| 情境 | 重視哪個 | 原因 |
|------|---------|------|
| 垃圾郵件過濾 | Precision | FP 代價高（正常信被誤刪） |
| 癌症篩查 | Recall | FN 代價高（漏診癌症） |
| 詐騙偵測 | 兩者都要 | 都很重要 |

---

### F1 Score

Precision 和 Recall 的調和平均數：

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

**為什麼用調和平均而不是算術平均？**  
調和平均對極端值更敏感。如果 Precision=0.99, Recall=0.01，算術平均是 0.5（看起來不錯），調和平均是 0.02（揭示真實問題）。

---

### ROC-AUC

ROC 曲線：橫軸 FPR（False Positive Rate），縱軸 TPR（True Positive Rate = Recall）。  
AUC（Area Under Curve）= ROC 曲線下的面積。

```
AUC = 1.0 → 完美模型
AUC = 0.5 → 隨機猜測
AUC < 0.5 → 比隨機還差（通常是標籤反了）
```

**面試要能說的重點：**
- AUC 不受類別不平衡影響（和 Accuracy 不同）
- 類別不平衡嚴重時，建議看 PR-AUC（Precision-Recall 曲線下面積）

---

## 三、Overfitting、Bias vs Variance、Regularization

### Bias-Variance Tradeoff

```
模型誤差 = Bias² + Variance + Irreducible Noise

Bias（偏差）：模型的假設和真實規律的差距
→ High Bias = 模型太簡單（Underfitting）

Variance（方差）：模型對不同訓練集的敏感程度
→ High Variance = 模型太複雜（Overfitting）
```

**直覺理解：**
- 用一條直線擬合非線性資料 → High Bias（Underfitting）
- 用 100 次多項式擬合 100 個點 → High Variance（Overfitting），完美擬合訓練集但對新資料差

---

### Overfitting 的症狀和對策

**症狀：** 訓練集 accuracy 很高，validation/test accuracy 低

**對策：**

| 方法 | 說明 |
|------|------|
| **增加訓練資料** | 最根本的方法 |
| **Regularization** | 懲罰複雜模型（見下節） |
| **Dropout** | 神經網路用，訓練時隨機關掉部分神經元 |
| **Early Stopping** | 監控 validation loss，停在最低點 |
| **Reduce model complexity** | 用更簡單的模型 |
| **Data Augmentation** | 用現有資料生成更多訓練樣本 |

---

### Regularization（正則化）

在損失函數中加入懲罰項，限制模型複雜度：

**L2 Regularization（Ridge）：**
```
Loss = MSE + λ × Σwᵢ²
```
→ 讓權重趨近於 0，但不為 0  
→ 適合特徵很多、想保留所有特徵

**L1 Regularization（Lasso）：**
```
Loss = MSE + λ × Σ|wᵢ|
```
→ 讓不重要的特徵權重變成 0（稀疏性）  
→ 適合做特徵選擇

**面試要能說的重點：**
- `λ`（lambda）是超參數，越大懲罰越強，越容易 underfitting
- Elastic Net = L1 + L2 的組合

---

## 四、Feature Engineering

### One-Hot Encoding

把類別型特徵轉成數值：

```
顏色: [紅, 藍, 綠]
→
紅: [1, 0, 0]
藍: [0, 1, 0]
綠: [0, 0, 1]
```

**注意：** Dummy variable trap——通常要刪掉一個維度（`drop_first=True`），避免完全共線性。

---

### Feature Scaling（特徵縮放）

**為什麼需要 Scaling？**  
如果特徵的量綱差距大（年齡 0-100，收入 10000-1000000），梯度下降會非常不穩定。

| 方法 | 公式 | 適用 |
|------|------|------|
| **Min-Max Normalization** | (x - min) / (max - min) | 特徵範圍固定時 |
| **StandardScaler (Z-score)** | (x - mean) / std | 特徵接近正態分佈時 |
| **RobustScaler** | (x - median) / IQR | 有 outlier 時 |

**哪些模型需要 Scaling？**
- 需要：Logistic Regression, SVM, KNN, Neural Networks
- 不需要：Tree-based models（Decision Tree, Random Forest, XGBoost）

---

### Embedding（嵌入特徵）

把高維稀疏的類別特徵（例如用戶 ID、商品 ID）轉成低維稠密的向量。

比 One-Hot 好在：
- 維度更低
- 向量空間有語意意義（相似的東西距離近）
- 可以端對端訓練（Embedding + 下游任務一起優化）

---

## 五、Deep Learning 核心

### 神經網路基礎

**MLP（Multi-Layer Perceptron，多層感知機）：**

```
Input Layer → Hidden Layer(s) → Output Layer
```

每層：
```
z = W·x + b
a = activation(z)
```

常見 Activation Function：
- **ReLU**：`max(0, x)`，最常用，解決 vanishing gradient
- **Sigmoid**：用於二元分類輸出層
- **Softmax**：用於多類別分類輸出層

---

### CNN（Convolutional Neural Network，卷積神經網路）

為圖像設計的架構。核心思想：局部感受野 + 參數共享。

```
Image → Conv Layer（提取特徵）→ Pooling（降維）→ FC Layer（分類）
```

**卷積操作：** 用一個小的 filter 在圖像上滑動，提取局部特徵（邊緣、紋理、形狀）。

**用在 NLP 的時候：** 可以用 1D CNN 做文字分類。

---

### RNN 和 LSTM

**RNN（Recurrent Neural Network）：**

設計用來處理序列資料（文字、時間序列）。每步的隱藏狀態傳遞到下一步：

```
hₜ = f(W·xₜ + U·hₜ₋₁ + b)
```

**問題：Vanishing Gradient**  
序列很長時，梯度在反向傳播中指數衰減，早期的資訊被「遺忘」。

**LSTM（Long Short-Term Memory）：**

解決 RNN 的 vanishing gradient 問題，透過三個 gate 控制資訊流：
- **Forget Gate**：決定忘記多少過去的資訊
- **Input Gate**：決定接受多少新資訊
- **Output Gate**：決定輸出多少資訊

```
這讓 LSTM 可以記住「很久以前」的資訊。
```

**現狀：** RNN/LSTM 在 NLP 領域幾乎已被 Transformer 取代，但在時間序列預測（金融、IoT）仍有應用。

---

## 六、Transformer：最重要的架構

這是 FDE 面試中**最重要的深度學習內容**。必須能夠清楚解釋。

---

### Self-Attention（自注意力）

Transformer 的核心機制。讓每個 token 在生成表示時，能夠「關注」序列中的所有其他 token。

輸入序列中每個 token 生成三個向量：
```
Q（Query）：我想找什麼
K（Key）：我有什麼
V（Value）：我的實際內容
```

計算注意力分數：
```
Attention(Q, K, V) = softmax(Q·Kᵀ / √dₖ) · V
```

**直覺理解：**  
「The bank by the river」中，`bank` 這個詞應該關注 `river`（而不是 `money`），Self-Attention 就是讓模型學到這種關係。

**`√dₖ` 的作用：** 縮放點積，防止維度高時點積值太大導致 softmax 梯度消失。

---

### Multi-Head Attention（多頭注意力）

不只用一個 Attention，而是並行運行 H 個 Attention head：

```
MultiHead(Q, K, V) = Concat(head₁, head₂, ..., headₕ) · W^O
```

**為什麼多頭？**  
不同的 head 可以學到不同面向的關係：
- Head 1 可能學語法依賴
- Head 2 可能學語意相似性
- Head 3 可能學長距離指代

---

### Positional Encoding（位置編碼）

Self-Attention 本身沒有順序概念（集合，不是序列）。  
Positional Encoding 把位置資訊加進 embedding：

```
token_embedding + positional_embedding
```

原始 Transformer 用 sine/cosine 函數生成固定位置編碼。  
現代 LLM（如 Gemini, GPT）通常用可學習的位置編碼或 RoPE（Rotary Position Embedding）。

---

### Transformer 完整架構

```
Encoder（用於理解）：
  Input Embedding + Positional Encoding
  → Multi-Head Self-Attention
  → Add & Norm (Residual Connection)
  → Feed Forward Network
  → Add & Norm

Decoder（用於生成）：
  Output Embedding + Positional Encoding
  → Masked Multi-Head Self-Attention（遮蔽未來 token）
  → Multi-Head Cross-Attention（關注 Encoder 輸出）
  → Feed Forward Network
```

**現代 LLM（GPT, Gemini, Claude）只用 Decoder：**  
因為生成任務只需要 Decoder，Encoder 是雙向的（適合理解任務）。

---

### 面試回答層次

被問到 Transformer：

**第一層（基本）：**  
「Transformer 用 Self-Attention 讓每個 token 能關注序列中所有其他 token，解決了 RNN 的長距離依賴問題，並且可以完全並行化訓練。」

**第二層（進階）：**  
「Multi-Head Attention 讓模型從多個角度看序列關係。Positional Encoding 補充了位置資訊。Residual Connection 和 Layer Norm 讓深層網路訓練穩定。」

**第三層（FDE 視角）：**  
「在 RAG 和 Agent 系統中，Transformer 的 context window 限制直接影響了我怎麼設計 chunking 和 memory。Attention 的計算是 O(n²)，所以 long context 的效率問題是工程上要考慮的。」

---

## 快速複習清單

在面試前確認你能清楚解釋這些：

- [ ] Supervised Learning 的定義，舉例 Regression vs Classification
- [ ] Linear Regression 的目標函數，為什麼用 MSE
- [ ] Logistic Regression 用在哪，sigmoid 的輸出是什麼
- [ ] Random Forest vs XGBoost 的核心差異
- [ ] Precision, Recall, F1, ROC-AUC 各自的意義和適用場景
- [ ] Bias vs Variance 的 trade-off
- [ ] L1 vs L2 Regularization 的差異和效果
- [ ] One-Hot Encoding 和 Feature Scaling 各自什麼時候用
- [ ] Self-Attention 的 Q/K/V 概念和計算方式
- [ ] Multi-Head Attention 的直覺
- [ ] Positional Encoding 的作用

---

## 下一篇

[FDE 面試準備指南（九）：LLM 核心知識——Token、Prompt Engineering 與 Embedding](/posts/fde-interview-guide-part9-llm-core-zh/)
