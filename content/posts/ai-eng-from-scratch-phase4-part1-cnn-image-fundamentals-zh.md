---
title: "AI 工程從零開始｜Phase 4 Part 1：電腦視覺基礎 — 從像素到 CNN 特徵"
date: 2026-06-21T11:30:00+08:00
draft: false
weight: 6
description: "深入解析卷積神經網路的工程直覺：卷積運算、池化、ResNet/EfficientNet 架構演進、影像資料增強與遷移學習策略"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Computer Vision", "CNN", "ResNet", "Transfer Learning", "Image Classification", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師拿到影像分類任務，第一反應是直接 Fine-tune ResNet50。*
> *但面試官真正想聽的是：你為什麼選 ResNet？池化層存在的意義是什麼？*
> *當訓練資料只有 5,000 張時，Fine-tune 和 Feature Extraction 哪個對？*
> *能回答這三個問題，才算真正理解電腦視覺的工程基礎。*

---

## 面試情境

**面試官問：** 「你的團隊要為一個醫療 App 建立皮膚病灶分類模型，訓練集只有 8,000 張標注影像、7 個類別，部署目標是手機端推論延遲 < 200ms。請說明你的架構選擇、遷移學習策略，以及你會怎麼處理類別不平衡問題。」

---

## 一、核心問題：影像理解的本質挑戰

影像資料與結構化資料有三個根本差異，讓全連接網路（Fully Connected）幾乎無法直接勝任：

**1. 維度爆炸**
一張 224×224 RGB 影像 = 150,528 個像素值。若用全連接層，第一層就需要 150,528 × hidden_units 個參數。一個 512 hidden units 的層，光第一層就是 77M 參數——這還沒考慮過擬合。

**2. 空間不變性缺失**
全連接層把像素當作獨立特徵看待，完全忽略空間關係。一隻貓在左上角和右下角，對 FC 層而言是完全不同的輸入。

**3. 局部結構的重要性**
影像中有意義的特徵（邊緣、紋理、形狀）都是局部的、階層式的。邊緣 → 紋理 → 部件 → 物件，這個從低階到高階的特徵階層，正是 CNN 設計的出發點。

CNN 用三個核心機制解決上述問題：
- **局部連接（Local Connectivity）**：每個神經元只看一小塊感受野
- **參數共享（Weight Sharing）**：同一個卷積核在整張影像上滑動
- **階層式特徵提取（Hierarchical Feature Learning）**：堆疊卷積層逐步抽象

---

## 二、三個演進階段（POC / MVP / Scale）

### Phase 1 — POC（< 1 萬張訓練影像）

```
┌────────────────────────────────────────────────────┐
│  Pre-trained Backbone (凍結所有權重)                │
│  ┌──────────────────────────────────────────────┐  │
│  │  ResNet50 / MobileNetV2 (ImageNet weights)   │  │
│  └──────────────────┬─────────────────────────┘  │
│                     │ Feature Vector (2048-d)      │
│  ┌──────────────────▼─────────────────────────┐  │
│  │  Global Average Pooling                      │  │
│  └──────────────────┬─────────────────────────┘  │
│                     │                              │
│  ┌──────────────────▼─────────────────────────┐  │
│  │  Linear Classifier (新增，只訓練這層)        │  │
│  │  Dense(256) → Dropout(0.5) → Dense(N_cls)   │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
訓練時間：~30 min (GPU)    Accuracy：~75–82%
```

**接受的妥協：** Backbone 凍結代表無法適應 domain-specific 特徵（如醫療影像的特殊紋理），但在資料量不足時能有效防止過擬合。

---

### Phase 2 — MVP（1 萬–10 萬張影像）

```
┌────────────────────────────────────────────────────┐
│  Gradual Unfreeze Fine-tuning Pipeline              │
│                                                     │
│  Epoch 1–5:  凍結 backbone，只訓練 head              │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   │
│  │ Conv     │──▶│ Conv     │──▶│  Head (訓練) │   │
│  │ Block 1  │   │ Block 4  │   │              │   │
│  │ (凍結)   │   │ (凍結)   │   └──────────────┘   │
│  └──────────┘   └──────────┘                       │
│                                                     │
│  Epoch 6–20: 解凍後 2 個 block，降低 LR 10×         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   │
│  │ Conv     │──▶│ Conv     │──▶│  Head (訓練) │   │
│  │ Block 1  │   │ Block 4  │   │              │   │
│  │ (凍結)   │   │ (訓練)   │   └──────────────┘   │
│  └──────────┘   └──────────┘                       │
│                                                     │
│  + 資料增強 (Augmentation Pipeline)                 │
│  + Class-weighted Loss (處理類別不平衡)              │
└────────────────────────────────────────────────────┘
訓練時間：~3–6 hr (GPU)    Accuracy：~85–90%
```

**新增組件：** Gradual unfreezing 策略、Cosine LR Scheduler、Mixup/CutMix 增強。

---

### Phase 3 — Scale（10 萬+ 影像 / 生產部署）

```
┌─────────────────────────────────────────────────────────┐
│  Production Vision Pipeline                              │
│                                                          │
│  ┌──────────┐    ┌──────────────────────────────────┐  │
│  │ Data     │───▶│  EfficientNetV2-S / ConvNeXt-T   │  │
│  │ Loader   │    │  Full Fine-tune + SAM Optimizer   │  │
│  │ (DALI)   │    └──────────────┬───────────────────┘  │
│  └──────────┘                   │                        │
│                    ┌────────────▼────────────┐           │
│                    │  TorchScript / ONNX 導出 │           │
│                    └────────────┬────────────┘           │
│                                 │                         │
│          ┌──────────────────────┼─────────────────────┐  │
│          ▼                      ▼                       ▼  │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐│
│  │ TensorRT     │  │ CoreML (iOS)     │  │ TFLite       ││
│  │ GPU Server   │  │ < 80ms 推論      │  │ Android      ││
│  │ < 10ms       │  └──────────────────┘  └──────────────┘│
│  └──────────────┘                                         │
│                                                          │
│  監控：Accuracy drift、Prediction confidence 分布        │
└─────────────────────────────────────────────────────────┘
訓練時間：~12–24 hr (多 GPU)    Accuracy：~90–94%
```

**新增組件：** NVIDIA DALI 資料載入管線（快 3× vs PyTorch DataLoader）、多 GPU 分散訓練、模型量化（INT8）、A/B 測試部署。

---

## 三、卷積運算直覺：局部感受野與參數共享

### 卷積的本質

卷積核（Kernel）是一個小型權重矩陣（通常 3×3 或 5×5），在輸入特徵圖上滑動，計算每個位置的點積。

```
輸入影像 (5×5)          3×3 卷積核              輸出特徵圖 (3×3)
┌─────────────────┐    ┌─────────────┐         ┌───────────────┐
│ 1  2  3  0  1   │    │  1  0  -1  │         │               │
│ 4  5  6  1  0   │ ✕  │  2  0  -2  │   ─▶    │  計算 9 個位置 │
│ 7  8  9  2  1   │    │  1  0  -1  │         │  (Sobel-like)  │
│ 0  1  2  3  4   │    └─────────────┘         │               │
│ 1  0  1  2  3   │                            └───────────────┘
└─────────────────┘
Stride=1, Padding=0 → 輸出尺寸 = (5-3)/1 + 1 = 3
```

**參數共享的威力：**
- 全連接層：5×5 輸入 → 3×3 輸出 = 225 × 9 = 2,025 參數
- 卷積層：只需 3×3 = **9 個參數**（同一組權重在整張圖滑動）
- 在 224×224 影像上，一層 64 個 3×3 卷積核 = 64 × 9 × 3 = 1,728 參數（vs FC 的 ~150K × 64 = 9.6M 參數）

### 感受野（Receptive Field）的累積

```
Layer 1 (3×3 conv)    Layer 2 (3×3 conv)    Layer 3 (3×3 conv)
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  ┌─────┐      │     │  ┌─────────┐  │     │  ┌─────────┐  │
│  │ 3×3 │      │──▶  │  │   5×5   │  │──▶  │  │   7×7   │  │
│  │感受野│      │     │  │  感受野  │  │     │  │  感受野  │  │
│  └─────┘      │     │  └─────────┘  │     │  └─────────┘  │
└───────────────┘     └───────────────┘     └───────────────┘
  感受野 = 3×3          感受野 = 5×5          感受野 = 7×7
```

三層 3×3 的感受野等同於一層 7×7，但參數量：
- 三層 3×3：3 × (3×3) = **27 參數**（每個輸出 channel）
- 一層 7×7：7×7 = **49 參數**
- 效率提升 81%，且中間層多了兩次非線性（ReLU），表達能力更強

---

## 四、池化與特徵圖的空間壓縮

### Max Pooling vs Average Pooling

**Max Pooling（2×2, stride=2）：**
```
特徵圖 (4×4)              Max Pooled (2×2)
┌────────────────┐        ┌──────────┐
│  1   3   2   4 │        │          │
│  5   6   1   2 │  ──▶   │  6    4  │
│  3   1   4   2 │        │  5    7  │
│  2   5   3   7 │        │          │
└────────────────┘        └──────────┘
保留最顯著的特徵激活值，丟棄精確位置資訊
```

**設計意義：**
- **平移不變性（Translation Invariance）：** 特徵移動幾個像素，池化後結果相同
- **降維：** 2×2 池化讓 H×W 縮小 4 倍，計算量減少 75%
- **防過擬合：** 減少後續層的參數數量

**Global Average Pooling（GAP）的革命：**

ResNet 之前的架構（AlexNet、VGG）用 Flatten + FC 結尾：
```
特徵圖 7×7×512  →  Flatten  →  25,088  →  FC(4096)  →  FC(1000)
                               參數量：25,088 × 4,096 = ~103M 參數
```

GAP 將每個 channel 的特徵圖取平均，直接得到向量：
```
特徵圖 7×7×2048  →  GAP  →  2048-d 向量  →  FC(N_classes)
                             參數量：2048 × N = ~2M 參數（少 50×）
```

GAP 讓模型天然支援任意輸入解析度，也大幅降低過擬合風險。

---

## 五、CNN 架構演進：AlexNet → VGG → ResNet → EfficientNet

### 關鍵里程碑對比

| 架構 | 年份 | 參數量 | Top-1 Acc (ImageNet) | 關鍵創新 |
|------|------|--------|----------------------|----------|
| AlexNet | 2012 | 61M | 57.1% | ReLU、Dropout、GPU 訓練 |
| VGG-16 | 2014 | 138M | 71.5% | 深度堆疊 3×3 conv |
| GoogLeNet | 2014 | 7M | 74.8% | Inception module、GAP |
| ResNet-50 | 2015 | 25M | 76.1% | 殘差連接（Skip Connection） |
| EfficientNet-B0 | 2019 | 5.3M | 77.1% | 複合縮放（Compound Scaling） |
| ConvNeXt-T | 2022 | 29M | 82.1% | 現代化 CNN 設計原則 |

### 殘差連接（Residual Connection）為什麼重要

```
沒有 Skip Connection（梯度消失問題）：

Input → Conv → ReLU → Conv → ReLU → Output
                                        ↑
                              梯度流回時衰減嚴重
                              深度 > 20 層後準確率下降

有 Skip Connection（ResNet）：

        ┌────────────────────────────────────┐
        │                                    │
Input──▶│  Conv3×3 → BN → ReLU → Conv3×3   │──▶ Add ──▶ ReLU ──▶ Output
        │  (殘差路徑 F(x))                   │      ↑
        └────────────────────────────────────┘      │
                                                    x (恆等映射)

梯度可以直接流過恆等路徑，解決了梯度消失問題
允許訓練 50、101、152 甚至 1000+ 層的網路
```

**工程直覺：** ResNet 的假設是「學習殘差比學習完整映射更容易」。若最優映射是恆等映射（F(x)=0），網路只需把殘差路徑的權重推向 0 即可，而不必讓整個 block 學出恆等映射。

### EfficientNet：複合縮放的系統性思考

EfficientNet 提出同時縮放三個維度，而不是只縮放其中一個：

```
傳統縮放（各自獨立）：
寬度縮放：  增加 channel 數量     → 參數 ↑，收益遞減
深度縮放：  增加層數              → 訓練難度 ↑，梯度問題
解析度縮放：增加輸入影像尺寸      → 計算量 ↑，感受野增加有限

EfficientNet 複合縮放（聯合搜索）：
depth    d = α^φ      α = 1.2
width    w = β^φ  →   β = 1.1   φ 是複合係數（B0 → B7 φ=0~7）
resolution r = γ^φ    γ = 1.15
約束：α × β² × γ² ≈ 2
```

EfficientNet-B0（5.3M 參數）比 ResNet-50（25M 參數）準確率還高 1%，推論速度快 6.1×。

---

## 六、遷移學習策略：Freeze / Fine-tune / Feature Extraction

### 三種策略的選擇流程

```
                    ┌───────────────────────────────┐
                    │  你的任務資料 vs ImageNet 相似度 │
                    └──────────────┬────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
              ▼                    ▼                     ▼
       資料量少 (<5K)         資料量中 (5K–50K)      資料量多 (>50K)
       Domain 相似            Domain 相似或不同        任何 Domain
              │                    │                     │
              ▼                    ▼                     ▼
    ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
    │ Feature         │  │ Gradual Unfreeze  │  │ Full Fine-tune   │
    │ Extraction      │  │ Fine-tune         │  │ (from scratch    │
    │                 │  │                   │  │  if domain 差異  │
    │ 凍結全部 backbone│  │ 先凍結訓練 head,  │  │  極大)           │
    │ 只訓練新增的 head│  │ 再逐步解凍後段層  │  │                  │
    └─────────────────┘  └──────────────────┘  └──────────────────┘
         LR: 1e-3              LR: backbone 1e-5        LR: 1e-4
                                   head 1e-3
         Accuracy: ~75%        Accuracy: ~85%           Accuracy: ~90%+
         訓練時間: 30 min       訓練時間: 2–6 hr         訓練時間: 12+ hr
```

### Gradual Unfreeze 的實作細節

```python
# 典型 Gradual Unfreeze 排程
# Stage 1：只訓練分類頭（Epoch 1–5）
for param in backbone.parameters():
    param.requires_grad = False
optimizer = Adam(head.parameters(), lr=1e-3)

# Stage 2：解凍最後一個 block（Epoch 6–15）
for param in backbone.layer4.parameters():
    param.requires_grad = True
optimizer = Adam([
    {'params': backbone.layer4.parameters(), 'lr': 1e-5},
    {'params': head.parameters(), 'lr': 1e-4},
])

# Stage 3：解凍全部（Epoch 16–30）
for param in backbone.parameters():
    param.requires_grad = True
optimizer = Adam([
    {'params': backbone.parameters(), 'lr': 1e-5},
    {'params': head.parameters(), 'lr': 1e-4},
])
```

**為什麼用不同的 Learning Rate？**
Backbone 已收斂在 ImageNet 特徵，用大 LR 會破壞這些有用的特徵（稱為 catastrophic forgetting）。分類頭是隨機初始化的，需要較大 LR 才能快速收斂。

### Domain Shift 的影響

| 來源 Domain | 目標 Domain | 建議策略 |
|-------------|-------------|----------|
| ImageNet (自然影像) | 零售商品 | Gradual Unfreeze，解凍後 3 層 |
| ImageNet | 醫療影像 (X-Ray) | 解凍 50%+ 層，注意 BN 統計量 |
| ImageNet | 衛星影像 | 完整 Fine-tune，解凍所有 BN 層 |
| ImageNet | 顯微鏡影像 | 考慮從 domain-specific pretrain 開始 |

---

## 七、影像資料增強與正規化

### 增強的設計原則：不破壞語義

```
安全增強（幾乎任何任務都可用）：
┌──────────────────────────────────────────────────────────┐
│  水平翻轉 (p=0.5)          隨機裁切 + Resize              │
│  隨機旋轉 ±15°              色彩抖動 (brightness ±20%)    │
│  高斯雜訊 (σ=0.01)          隨機灰度化 (p=0.1)            │
└──────────────────────────────────────────────────────────┘

任務相關增強（需要謹慎）：
┌──────────────────────────────────────────────────────────┐
│  垂直翻轉：適合衛星/顯微鏡，不適合人臉/文字              │
│  大角度旋轉 (>45°)：適合醫療影像，不適合場景分類          │
│  強色彩增強：不適合醫療影像（色彩有診斷意義）             │
└──────────────────────────────────────────────────────────┘

進階增強（資料量少時效果顯著）：
┌──────────────────────────────────────────────────────────┐
│  Mixup：兩張影像線性混合，Label 也混合                    │
│  CutMix：隨機貼上另一張影像的裁塊                         │
│  AugMix：多種增強的混合，提升 OOD robustness              │
│  RandAugment：自動搜索最佳增強策略組合                    │
└──────────────────────────────────────────────────────────┘
```

### 正規化（Normalization）的正確做法

**永遠使用資料集的統計量，不要用 ImageNet 的：**

```python
# 錯誤做法（對醫療影像）：
transform = Normalize(mean=[0.485, 0.456, 0.406],  # ImageNet 統計量
                      std=[0.229, 0.224, 0.225])

# 正確做法：
# 先計算你的資料集統計量
dataset_mean = [0.612, 0.481, 0.498]  # 你的資料集
dataset_std  = [0.195, 0.201, 0.189]
transform = Normalize(mean=dataset_mean, std=dataset_std)
```

使用錯誤的正規化統計量會讓 Backbone 的特徵分布偏移，等效於 domain shift，可能讓 Fine-tune 收斂更慢或準確率下降 2–5%。

### 類別不平衡的處理策略

醫療影像資料集中，類別不平衡（1:10 到 1:100）是常見問題：

| 策略 | 適用場景 | 實作 | 注意事項 |
|------|----------|------|----------|
| Class Weight Loss | 不平衡比 < 1:10 | `CrossEntropy(weight=class_weights)` | 計算簡單，效果穩定 |
| Oversampling (SMOTE) | 不平衡比 < 1:20 | 增加少數類別樣本 | 注意資料洩漏（需在 Split 之後） |
| Focal Loss | 不平衡比 > 1:10 | `FL = -α(1-p)^γ log(p)` | 自動降低易分類樣本的 Loss 權重 |
| Two-stage Training | 極端不平衡 | 先訓練平衡子集，再全量 Fine-tune | 需要仔細調整訓練時間比例 |

---

## 八、為什麼選 X 不選 Y

### 決策 1：ResNet-50 vs VGG-16

| 維度 | ResNet-50 | VGG-16 |
|------|-----------|--------|
| 參數量 | 25M | 138M |
| Top-1 Acc | 76.1% | 71.5% |
| 推論速度 (224×224) | ~10ms (GPU) | ~25ms (GPU) |
| 記憶體佔用 | ~100MB | ~553MB |
| Fine-tune 難易度 | 容易，Skip Connection 保護梯度 | 較難，深層梯度消失 |

**選 ResNet-50 的理由：** 準確率更高、更快、更小、更容易訓練。VGG-16 在 2024 年幾乎沒有理由選用。

**翻轉條件：** 若需要與 5 年前的 baseline 對比或維護舊系統，才考慮 VGG-16。

---

### 決策 2：EfficientNet vs ResNet（行動裝置部署）

| 維度 | EfficientNet-B0 | ResNet-50 |
|------|-----------------|-----------|
| 參數量 | 5.3M | 25M |
| Top-1 Acc | 77.1% | 76.1% |
| FLOPs | 0.39B | 4.1B |
| CoreML 推論 (iPhone 14) | ~45ms | ~180ms |
| Fine-tune 複雜度 | 稍高（Compound Scaling） | 直覺簡單 |

**選 EfficientNet-B0 的理由：** 行動端部署時，EfficientNet-B0 推論速度快 4×，準確率還更高。

**翻轉條件：** 若伺服器端部署且 Batch size 很大，ResNet-50 的硬體利用率更好。

---

### 決策 3：Gradual Unfreeze vs 直接 Full Fine-tune

| 維度 | Gradual Unfreeze | Full Fine-tune |
|------|-----------------|----------------|
| 訓練資料需求 | 5K–50K 張 | > 50K 張 |
| Catastrophic Forgetting 風險 | 低 | 高（需搭配低 LR） |
| 收斂速度 | 快（第一階段就有好結果） | 慢（全部從頭調整） |
| 最終準確率 | ~85–90% | ~88–94%（資料夠時） |
| 工程複雜度 | 需要分階段調整 LR | 相對簡單 |

**翻轉條件：** 當你的 Domain 與 ImageNet 差異極大（如 X-Ray、衛星影像），Gradual Unfreeze 後半段等同於 Full Fine-tune，可以直接省略前期凍結階段。

---

### 決策 4：Max Pooling vs Average Pooling

| 維度 | Max Pooling | Average Pooling |
|------|-------------|-----------------|
| 特性 | 保留最強特徵，丟棄位置資訊 | 保留整體分布，平滑噪音 |
| 適合任務 | 物件偵測、紋理分類 | 場景分類、風格識別 |
| 過擬合風險 | 較高（只保留峰值） | 較低 |
| 反向傳播 | 梯度只流向最大值位置 | 梯度均勻分配 |

**工程經驗：** 中間層用 Max Pooling，最後一層用 GAP（Global Average Pooling），是 ResNet 之後的標準做法。

---

### 決策 5：Focal Loss vs Cross-Entropy（類別不平衡）

| 維度 | Focal Loss | Cross-Entropy + Class Weight |
|------|------------|------------------------------|
| 不平衡比 < 1:10 | 過殺，效果差不多 | 足夠 |
| 不平衡比 1:10 – 1:50 | 顯著提升 5–10% | 有效但不如 FL |
| 不平衡比 > 1:50 | 必要 | 效果有限 |
| 調參複雜度 | 需調 γ（通常 2.0）和 α | 只需調 class weights |
| 實作難度 | 稍高 | 內建支援 |

**翻轉條件：** 資料量足夠且可以做充分 oversampling 時，Cross-Entropy 更穩定。

---

### 決策 6：Random Augmentation vs AutoAugment

| 維度 | Random Augmentation | AutoAugment / RandAugment |
|------|---------------------|--------------------------|
| 搜索成本 | 無（人工設計） | AutoAugment 需要 GPU 小時搜索 |
| RandAugment | N, M 兩個超參數 | 效果接近 AutoAugment |
| 準確率提升 | 基準 | +0.5–2.0% (ImageNet) |
| 遷移性 | 需要針對任務設計 | RandAugment 遷移性好 |
| 建議 | POC 階段 | MVP/Scale 階段 |

**工程建議：** 直接用 `torchvision.transforms.RandAugment(num_ops=2, magnitude=9)`，幾乎無需調參，效果接近 AutoAugment。

---

## 九、系統效應（Before / After 含量化數字）

以下以「醫療皮膚病灶分類，8,000 張訓練影像，7 類別」為基準情境：

| 指標 | Baseline (VGG-16 Full Fine-tune) | Phase 1 (ResNet-50 Feature Ext.) | Phase 2 (EfficientNet-B0 Gradual Unfreeze) | Phase 3 (EfficientNet-B0 Full Pipeline) |
|------|----------------------------------|----------------------------------|---------------------------------------------|------------------------------------------|
| Top-1 Accuracy | 71.3% | 78.2% | 86.7% | 91.4% |
| F1 Score (macro) | 0.623 | 0.731 | 0.821 | 0.887 |
| 訓練時間 | 8 hr (1× V100) | 35 min (1× V100) | 3.5 hr (1× V100) | 11 hr (4× V100) |
| 模型大小 | 553 MB | 98 MB | 21 MB | 21 MB (INT8: 6 MB) |
| 推論延遲 (iPhone 14) | N/A (伺服器) | 185ms | 48ms | 42ms (CoreML) |
| 記憶體用量 (訓練) | 22 GB | 6 GB | 4 GB | 4 GB / GPU |
| 月度 GPU 費用 (AWS p3.2xl) | $240 | $18 | $105 | $330 (一次性訓練) |

**關鍵洞察：**
1. Feature Extraction（Phase 1）用 6% 的訓練時間，達到 Baseline 110% 的準確率
2. EfficientNet-B0 在行動端推論比 ResNet-50 快 3.9×，且準確率更高
3. Phase 2 的 Gradual Unfreeze 讓 F1 從 0.731 提升到 0.821，成本只增加 6 倍訓練時間
4. INT8 量化讓模型縮小 3.5×，推論速度提升 1.2×，準確率下降僅 0.3%

---

## 十、面試答題要點（RKK）

**面試官問：** 「醫療 App 皮膚病灶分類，8,000 張標注影像，7 類別，行動端 < 200ms，請說明你的架構選擇與策略。」

> *「我會選 EfficientNet-B0 作為 Backbone，它在 5.3M 參數下達到 77% ImageNet Top-1，在 iPhone 14 上推論只需約 45ms，遠低於 200ms 的要求。由於訓練資料只有 8,000 張，我採用 Gradual Unfreeze 遷移學習策略：前 5 個 Epoch 凍結 Backbone 只訓練分類頭（LR=1e-3），之後解凍後兩個 Block 並用 10 倍低的 LR（1e-5）繼續訓練，這樣能防止 ImageNet 預訓練特徵被破壞，最終 F1 可達 0.82 左右。針對類別不平衡，若不平衡比超過 1:10，我會切換 Cross-Entropy 為 Focal Loss（γ=2.0），並搭配 RandAugment 增強。部署時用 CoreML 轉換 + INT8 量化，模型縮小到 6MB，在同等推論速度下準確率只下降 0.3%。整個方案的總訓練成本約 3.5 小時 V100，是直接 Full Fine-tune 的 1/2 時間，但準確率反而更高。」*

**RKK 核心三要素：**
- **R（Reason）：** EfficientNet-B0 vs ResNet-50 的理由是行動端 FLOPs 差 10×，速度差 4×
- **K（Knowledge）：** Gradual Unfreeze 的兩階段 LR 策略，以及什麼時候需要 Focal Loss
- **K（Know-how）：** INT8 量化的準確率代價 0.3% vs 大小縮減 3.5× 的工程取捨

---

## 十一、系列導航

本文是「AI 工程從零開始」系列 Phase 4 的第一篇。

| | 文章 | 主題 |
|---|------|------|
| ← | [Phase 3：MLOps 與模型部署](/posts/ai-eng-from-scratch-phase3-mlops-zh/) | 模型監控、CI/CD、Feature Store |
| 📍 | **Phase 4 Part 1（本文）** | CNN 基礎、ResNet、EfficientNet、遷移學習 |
| → | Phase 4 Part 2（即將推出） | 目標偵測：YOLO、Faster RCNN、Anchor-free |

---

**系列完整索引：**

- **Phase 1：** ML 基礎與特徵工程
- **Phase 2：** 深度學習訓練工程（訓練穩定性、超參數搜索）
- **Phase 3：** MLOps 與模型部署
- **Phase 4 Part 1：電腦視覺基礎（本文）**
- Phase 4 Part 2：目標偵測（即將推出）
- Phase 4 Part 3：語意分割（即將推出）
- Phase 5：自然語言處理與 Transformer（即將推出）
