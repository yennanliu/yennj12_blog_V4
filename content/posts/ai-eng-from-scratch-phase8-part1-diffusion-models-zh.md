---
title: "AI 工程從零開始｜Phase 8 Part 1：擴散模型 — 從雜訊到藝術的數學"
date: 2026-06-21T16:30:00+08:00
draft: false
weight: 16
description: "深入解析擴散模型工程原理：DDPM/DDIM 前向與反向過程、Stable Diffusion 潛在空間架構、ControlNet/LoRA 微調、生產推論優化"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Generative AI", "Diffusion Models", "Stable Diffusion", "ControlNet", "Image Generation", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人認為擴散模型「就是反覆去雜訊」。*
> *面試官想聽到的是：你能說明前向過程的閉合解、DDIM 的隱式馬可夫假設、以及為什麼潛在空間能讓 1024×1024 生成在消費級 GPU 上跑起來。*
> *差距不在知道有 Stable Diffusion，而在能精確量化每個設計決策的成本與效益。*
> *本文帶你從數學推導到生產部署，一次打通。*

---

**面試情境**：你負責為一個電商平台設計商品圖片自動生成系統，需要在 3 秒內生成 512×512 的商品展示圖，每日峰值 10 萬張，成本預算每張 $0.002。請描述你選擇的模型架構、推論優化策略，以及如何處理風格一致性問題。

---

## 一、核心問題：生成模型的本質——學習資料分佈

生成模型的核心目標是學習一個隱含的資料分佈 $p_{data}(x)$，然後從中採樣出新的樣本。這個問題有三條路：

**GAN（對抗生成）**：訓練一個生成器欺騙判別器。快、生成品質高，但訓練不穩定（模式崩潰），很難控制生成內容。

**VAE（變分自編碼器）**：學習潛在空間分佈，生成多樣但往往模糊，因為優化的是像素級 L2 loss。

**擴散模型（Diffusion Model）**：將資料生成過程建模為逐步去雜訊的馬可夫鏈。訓練穩定、生成品質極高、天然支援條件控制——但推論慢。

關鍵張力：**生成品質 vs. 推論速度 vs. 條件可控性**。三者難以同時最優。擴散模型在品質和可控性上勝出，工程挑戰集中在速度。

---

## 二、三個演進階段（POC → MVP → Scale）

### ╔══ Phase 1：POC（< 1K 日生成量）══╗

**目標**：驗證生成品質，選型，跑通 pipeline。

```
┌─────────────────────────────────────────────────────┐
│                    Phase 1 架構                      │
│                                                      │
│  使用者 Prompt ──▶ HuggingFace Diffusers API         │
│                          │                           │
│                          ▼                           │
│              Stable Diffusion v1.5                   │
│              (本機 GPU / Colab A100)                 │
│                          │                           │
│                          ▼                           │
│                   生成圖片輸出                        │
│              (DDPM 50步，約 5–8s/張)                 │
└─────────────────────────────────────────────────────┘
```

- **新增元件**：HuggingFace `diffusers`、基礎 U-Net、CLIP text encoder
- **成本**：Colab Pro $10/月，或單張 A100 約 $0.01/張
- **未解問題**：速度太慢、無條件控制、無法批量、模型版本混亂

---

### ╔══ Phase 2：MVP（1K–50K 日生成量）══╗

**目標**：生產化部署，加速推論，接入業務條件控制。

```
┌──────────────┐    ┌──────────────────────────────────────┐
│  API Gateway │───▶│           推論服務層                  │
└──────────────┘    │  ┌─────────────┐ ┌─────────────────┐ │
                    │  │  DDIM 20步  │ │  LoRA 風格適配   │ │
                    │  │  ~1s/張     │ │  (電商品牌風格)  │ │
                    │  └─────────────┘ └─────────────────┘ │
                    │           │                           │
                    │           ▼                           │
                    │    SD v2.1 + xFormers                 │
                    │    (A10G GPU, fp16)                   │
                    └──────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   物件儲存 (S3)        │
                    │   結果快取 (Redis)     │
                    └───────────────────────┘
```

- **新增元件**：DDIM 採樣器（20 步 ≈ 1s）、xFormers 注意力優化、LoRA 微調、Redis 結果快取
- **成本**：A10G 按需 $0.75/hr，吞吐約 3,600 張/hr → $0.0002/張
- **未解問題**：峰值排隊延遲、缺乏精細姿態/構圖控制

---

### ╔══ Phase 3：Scale（50K–1M+ 日生成量）══╗

**目標**：自動擴縮、成本最優、毫秒級 SLA。

```
┌────────────────────────────────────────────────────────────────┐
│                       Phase 3 架構                              │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  LB +    │    │  任務佇列     │    │   GPU Worker Pool    │  │
│  │  Rate    │───▶│  (SQS/Kafka) │───▶│  ┌────────────────┐  │  │
│  │  Limiter │    └──────────────┘    │  │ TensorRT INT8  │  │  │
│  └──────────┘                        │  │ SDXL Turbo     │  │  │
│                                      │  │ ControlNet     │  │  │
│  ┌──────────┐    ┌──────────────┐    │  └────────────────┘  │  │
│  │  Auto    │◀───│  Metrics     │    └──────────────────────┘  │
│  │  Scaler  │    │  (GPU util,  │              │                │
│  │  (K8s)   │    │   queue len) │              ▼                │
│  └──────────┘    └──────────────┘    ┌──────────────────────┐  │
│                                      │  CDN + S3 + 語義快取  │  │
│                                      └──────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

- **新增元件**：TensorRT INT8 量化（2× 加速）、語義快取（相似 prompt 複用結果）、Spot GPU 搶佔式節點、SDXL Turbo（4 步）
- **成本目標**：$0.0002/張 → 10 萬張/日 = $20/日
- **達成 SLA**：p95 < 2s，p99 < 3s

---

## 三、DDPM 前向與反向過程推導

### 前向過程（Forward Process）

DDPM 的前向過程是一個固定的馬可夫鏈，逐步向乾淨圖片 $x_0$ 加入高斯雜訊：

```
馬可夫鏈：前向過程

  x_0         x_1         x_2        ...      x_T
(原始圖)  (微雜訊)    (更多雜訊)          (純高斯雜訊)
   │            │           │                   │
   └──q(x₁|x₀)─┘ └─q(x₂|x₁)┘       └─q(xT|xT-1)┘

每步：q(xₜ|xₜ₋₁) = N(xₜ; √(1-βₜ)·xₜ₋₁, βₜ·I)

βₜ 從 β₁=0.0001 線性增長到 βT=0.02（T=1000）
```

**閉合解（重參數技巧的核心）**：不需要逐步計算，直接從 $x_0$ 採樣任意時步 $t$ 的加雜訊版本：

$$q(x_t | x_0) = \mathcal{N}(x_t; \sqrt{\bar{\alpha}_t} \cdot x_0, (1-\bar{\alpha}_t) \cdot I)$$

其中 $\bar{\alpha}_t = \prod_{s=1}^{t}(1-\beta_s)$。

這個閉合解讓訓練可以隨機取樣任意 $t$，無需真的執行 1000 步前向過程。

### 反向過程（Reverse Process）

反向過程學習去除雜訊：

$$p_\theta(x_{t-1}|x_t) = \mathcal{N}(x_{t-1}; \mu_\theta(x_t, t), \Sigma_\theta(x_t, t))$$

實務中，U-Net 學習的不是均值 $\mu$，而是**預測雜訊** $\epsilon_\theta(x_t, t)$，然後推算：

$$\mu_\theta = \frac{1}{\sqrt{\alpha_t}} \left(x_t - \frac{\beta_t}{\sqrt{1-\bar{\alpha}_t}} \epsilon_\theta(x_t, t)\right)$$

**訓練損失**（簡化版）：

$$L_{simple} = \mathbb{E}_{t, x_0, \epsilon} \left[ \| \epsilon - \epsilon_\theta(\sqrt{\bar{\alpha}_t} x_0 + \sqrt{1-\bar{\alpha}_t}\epsilon, t) \|^2 \right]$$

直覺：訓練 U-Net 預測「這張圖加了多少雜訊」。推論時反覆去雜訊 1000 步 → 在 A100 上約 **50 秒/張**（512×512）。這是後面所有加速工作的動機。

---

## 四、DDIM 加速採樣：從 1000 步到 20 步

### DDIM 的核心洞察

DDPM 的採樣是隨機的（每步加入新雜訊），DDIM（Denoising Diffusion Implicit Models）打破馬可夫假設，引入**確定性採樣**：

$$x_{t-1} = \sqrt{\bar{\alpha}_{t-1}} \underbrace{\left(\frac{x_t - \sqrt{1-\bar{\alpha}_t}\epsilon_\theta}{\sqrt{\bar{\alpha}_t}}\right)}_{\text{預測的 }x_0} + \underbrace{\sqrt{1-\bar{\alpha}_{t-1}} \cdot \epsilon_\theta}_{\text{方向項}}$$

**關鍵差異**：

| 屬性 | DDPM | DDIM |
|------|------|------|
| 採樣步數 | 1000 步 | 20–50 步 |
| 每張生成時間（A100） | ~50s | ~1s |
| 隨機性 | 每步加新雜訊 | 確定性（可設 η=0） |
| 結果可復現 | 需固定所有隨機種子 | 固定 seed 即可 |
| 訓練方式 | 重新訓練 | **無需重新訓練，直接替換採樣器** |

### 步數 vs. 品質取捨

```
FID（越低越好）vs. 推論步數（SD v1.5, 512×512）

步數   FID     時間(A100)   適用場景
────────────────────────────────────────
 5    18.2    0.25s       草稿預覽
10    10.5    0.5s        快速迭代
20     7.8    1.0s        ★ 生產甜蜜點
50     6.9    2.5s        高品質輸出
100    6.7    5.0s        幾乎無收益
1000   6.5    50s         論文基準
```

工程結論：**20 步 DDIM 是生產環境的預設選擇**。從 20→50 步只改善 FID 0.9，但成本增加 150%。

### 進階採樣器

- **DPM-Solver++**：數學上更優的 ODE 求解器，15 步達到 DDIM 20 步品質
- **LCM（Latent Consistency Model）**：4–8 步，但需要專門訓練
- **SDXL Turbo**：對抗蒸餾，1–4 步，適合即時預覽

---

## 五、Stable Diffusion 架構：VAE + U-Net + CLIP

Stable Diffusion 最重要的工程創新是**潛在擴散（Latent Diffusion）**：不在像素空間（512×512×3）做擴散，而是在 VAE 編碼的潛在空間（64×64×4）做擴散。空間壓縮比 **8×**，計算量降低 **64×**。

```
Stable Diffusion 完整資料流

   文字 Prompt                              雜訊
       │                                     │
       ▼                                     ▼
┌─────────────┐                    ┌──────────────────┐
│ CLIP Text   │                    │  隨機潛在向量     │
│ Encoder     │                    │  z_T ∈ R^{64×64×4}│
│ 77 tokens   │                    └────────┬─────────┘
│ 768-dim     │                             │
└──────┬──────┘                    ┌────────▼─────────┐
       │  cross-attention           │                  │
       │  conditioning              │   U-Net（去雜訊） │
       └──────────────────────────▶│                  │
                                   │  ┌─────────────┐ │
                                   │  │ Encoder 塊   │ │
                                   │  │ (下採樣×3)   │ │
                                   │  ├─────────────┤ │
                                   │  │ Bottleneck  │ │
                                   │  │ + Attention │ │
                                   │  ├─────────────┤ │
                                   │  │ Decoder 塊   │ │
                                   │  │ (上採樣×3)   │ │
                                   │  └─────────────┘ │
                                   │   重複 T 步       │
                                   └────────┬─────────┘
                                            │  z_0
                                            ▼
                                   ┌──────────────────┐
                                   │   VAE Decoder    │
                                   │   64×64×4        │
                                   │   → 512×512×3    │
                                   └────────┬─────────┘
                                            │
                                            ▼
                                      最終圖片輸出
```

### 三個元件深解

**VAE（變分自編碼器）**
- Encoder：512×512×3 → 64×64×4（壓縮比 1:48）
- Decoder：64×64×4 → 512×512×3（重建）
- 推論時只用 Decoder，約 **20ms**
- KL 散度係數 $\lambda=10^{-6}$，確保潛在空間平滑

**U-Net（去雜訊主幹）**
- 865M 參數（SD v1.5），佔推論時間 **90%**
- 每個 ResBlock 後接 Transformer Block（self-attention + cross-attention）
- Cross-attention：潛在特徵 query CLIP text embeddings，實現文字條件控制
- 時步嵌入（sinusoidal position encoding）告訴網路「現在是第幾步」

**CLIP Text Encoder**
- ViT-L/14，最大 77 個 token
- 輸出 768-dim 序列，透過 cross-attention 注入 U-Net 每一層
- 工程陷阱：token 數超過 77 會截斷，需要 prompt weighting 或 CLIP skip 技巧

---

## 六、條件控制：ControlNet / IP-Adapter / LoRA

### ControlNet：結構控制

```
ControlNet 架構（以姿態控制為例）

  條件圖（骨架/邊緣/深度）
          │
          ▼
┌─────────────────────┐
│  Trainable Copy of  │     ┌───────────────────────┐
│  U-Net Encoder      │────▶│   原始 U-Net（凍結）   │
│  (零卷積初始化)     │     │                       │
└─────────────────────┘     │  Encoder ──▶ Decoder  │
                             │       ▲               │
                             │       │ (residual 加法)│
                             └───────────────────────┘
```

- 零卷積（Zero Convolution）初始化：確保訓練初期不干擾原始 U-Net
- 只需訓練 ControlNet Encoder（~360M 參數），原始 U-Net 凍結
- 支援：Canny 邊緣、HED 邊緣、人體姿態（OpenPose）、深度圖、法線圖、分割圖
- 訓練資料需求：10K–50K 配對樣本

### IP-Adapter：圖像風格遷移

- 用參考圖片替代（或補充）文字 prompt
- 機制：獨立的 Image Encoder（CLIP Image Encoder）+ 解耦 cross-attention
- 參數量：22M（輕量），可疊加在任何 SD 模型上
- 效果：保留參考圖風格，用文字控制內容

### LoRA：高效微調

LoRA（Low-Rank Adaptation）在原始權重旁插入低秩矩陣：

$$W' = W + \Delta W = W + BA$$

其中 $B \in \mathbb{R}^{d \times r}$，$A \in \mathbb{R}^{r \times k}$，秩 $r \ll \min(d, k)$。

| 微調方式 | 可訓練參數量 | 儲存大小 | 訓練時間（A100） |
|---------|------------|---------|----------------|
| Full Fine-tuning | 865M | 3.4 GB | 8–24 hr |
| DreamBooth | 865M | 3.4 GB | 1–2 hr |
| LoRA (r=4) | 3.7M | 15 MB | 15–30 min |
| LoRA (r=64) | 58M | 230 MB | 1–2 hr |

**電商場景建議**：LoRA r=16，用 200–500 張品牌風格圖訓練 2000 步，**15 MB 的 LoRA 權重**即可讓生成圖與品牌視覺一致。

---

## 七、推論優化：TensorRT / xFormers / 量化

### xFormers Memory-Efficient Attention

標準 attention 記憶體複雜度 $O(n^2)$，xFormers 用 Flash Attention 降為 $O(n)$：

```python
# 啟用 xFormers（HuggingFace Diffusers）
pipe.enable_xformers_memory_efficient_attention()
```

效果：記憶體降低 **40%**，速度提升 **20–30%**，無品質損失。

### TensorRT 優化流程

```
ONNX 導出 → TensorRT 引擎編譯 → INT8/FP16 量化校準

時間線（SD v1.5, 512×512, A10G）：
──────────────────────────────────────────────
原始 PyTorch fp32    : 8.2s / 20步
PyTorch fp16         : 3.1s / 20步  (-62%)
fp16 + xFormers      : 2.3s / 20步  (-72%)
TensorRT fp16        : 1.4s / 20步  (-83%)
TensorRT INT8        : 0.9s / 20步  (-89%)
TensorRT INT8 + CUDA : 0.7s / 20步  (-91%)
```

**INT8 量化注意事項**：
- U-Net 的 time embedding 層需保留 fp32，否則步數估計錯誤
- 校準資料集需 100–200 張代表性 prompt，確保激活分佈覆蓋
- FID 損失通常 < 0.5，肉眼不可辨

### 語義快取（Semantic Cache）

相似 prompt → 複用已生成圖片：

```
策略：
1. 計算 prompt 的 CLIP embedding
2. 在向量資料庫（Faiss/Milvus）中搜尋 cosine similarity > 0.95 的歷史結果
3. 命中：直接返回（< 10ms）
4. 未命中：執行生成，存入快取

實測電商場景命中率：
  完全相同 prompt：30% 流量
  語義相似（>0.95）：額外 25% 流量
  總快取命中率：~55%
  等效成本節省：~50%
```

### 批次推論（Batching）

- 動態批次（batch size 4–8）利用 GPU 平行度
- A10G 上 batch=1 vs batch=4：吞吐 3.6× 提升，延遲只增加 1.3×
- 實務限制：batch 中每張的 step 數必須相同

---

## 八、為什麼選 X 不選 Y

### 決策 1：DDIM vs. DDPM 採樣

```
選擇        選 DDIM 的理由                  不選 DDPM 的理由
──────────────────────────────────────────────────────────────
DDIM        20步=DDPM 200步品質              1000步=50s，生產不可接受
vs DDPM     確定性採樣，結果可復現           每步引入新隨機性，難控制
            無需重新訓練，直接替換           隨機性反而造成 seed 不穩

Flip：研究多樣性採樣、探索模式多樣性時，DDPM 的隨機性是優點
```

### 決策 2：Latent Diffusion vs. Pixel Diffusion

```
選擇        選 Latent 的理由                不選 Pixel 的理由
──────────────────────────────────────────────────────────────
Latent      64×64 vs 512×512，計算量 64×   512×512 pixel diffusion A100 需 200s
Diffusion   A100 可跑 512×512              DALL-E 1 pixel space：只能做 256×256
            VAE 壓縮不損失感知品質          記憶體需求超過消費級 GPU 上限

Flip：256×256 低解析度任務，pixel diffusion 架構更簡單，無 VAE 引入的細節損失
```

### 決策 3：LoRA vs. Full Fine-tuning

```
選擇        選 LoRA 的理由                  不選 Full Fine-tuning 的理由
──────────────────────────────────────────────────────────────
LoRA        15 MB vs 3.4 GB，部署成本低     865M 參數訓練需 80GB VRAM
            多個 LoRA 可動態組合            每個風格獨立模型難以維護
            15–30 min 訓練，快速迭代        模型版本管理複雜度 O(n)

Flip：需要根本性改變模型能力（如新語言、新領域）時，Full Fine-tuning 必要
```

### 決策 4：ControlNet vs. Prompt Engineering

```
選擇        選 ControlNet 的理由            不選純 Prompt 的理由
──────────────────────────────────────────────────────────────
ControlNet  像素級結構控制（姿態/邊緣）     Prompt 無法精確控制手臂角度
            生成結果與輸入骨架嚴格對齊      電商商品需精確構圖，prompt 不夠
            可用現有圖片提取條件圖          生成品質受 prompt 措辭影響大

Flip：純創意生成（無需精確結構）時，ControlNet 增加約 30% 推論時間不值得
```

### 決策 5：INT8 量化 vs. FP16

```
選擇        選 INT8 的理由                  不選 FP32 全精度的理由
──────────────────────────────────────────────────────────────
INT8        比 fp16 再快 35%，同等 GPU      fp32：推論 8s/張，成本 4× fp16
            記憶體降低 50%，可跑更大 batch  fp32：A10G 單張 512×512 佔 10GB VRAM
            FID 損失 < 0.5，視覺無差異      

Flip：極高保真需求（醫療影像、衛星圖像）時，量化誤差不可接受，保留 fp16
```

### 決策 6：SDXL vs. SD v1.5

```
選擇        選 SDXL 的理由                  不選 SD v1.5 的理由
──────────────────────────────────────────────────────────────
SDXL        原生 1024×1024，細節更豐富      v1.5 最佳解析度 512×512
            雙 text encoder，語義理解更強   v1.5 手部、文字生成較差
            SDXL Turbo 可 4 步生成          

Flip：成本敏感場景，v1.5 模型小（865M vs 3.5B），推論快 4×，LoRA 生態更成熟
```

---

## 九、系統效應：生成品質 / 速度 / 成本的三角取捨

### 關鍵指標對比

| 配置 | 生成時間 | FID ↓ | 記憶體 | 成本/千張 | 適用場景 |
|------|---------|-------|-------|---------|---------|
| DDPM 1000步 fp32 | 50s | 6.5 | 10GB | $10.5 | 論文基準 |
| DDIM 50步 fp16 | 2.5s | 6.9 | 5GB | $0.52 | 高品質離線 |
| DDIM 20步 fp16 + xFormers | 1.0s | 7.8 | 3GB | $0.21 | ★ 生產推薦 |
| TensorRT INT8 20步 | 0.7s | 8.1 | 2.5GB | $0.15 | 高吞吐場景 |
| SDXL Turbo 4步 | 0.3s | 12.4 | 8GB | $0.06 | 即時預覽 |
| LCM 4步 | 0.3s | 11.8 | 5GB | $0.06 | 快速迭代 |

*成本基準：A10G $0.75/hr，GPU 利用率 70%，512×512*

### 電商場景需求對照

**需求**：3s SLA，10 萬張/日，$0.002/張 預算

```
預算驗算：
  目標成本：$0.002/張 × 100,000張 = $200/日
  選配：TensorRT INT8，0.7s/張
  所需 GPU-hr：100,000 × 0.7s / 3600 = 19.4 GPU-hr/日
  費用：19.4 × $0.75 = $14.6/日（基本負載）
  加上峰值 2× buffer + 語義快取 50% hit rate：
  實際費用 ≈ $14.6 × 2 × 0.5 = $14.6/日
  
  ✓ 遠低於 $200/日 預算
  ✓ 0.7s << 3s SLA 要求（有充足佇列 buffer）
```

### 成本優化漏斗

```
日成本優化路徑（10萬張/日基準）

  原始 DDPM fp32          $1,050/日
        │ DDIM 20步         ÷ 50
        ▼
  DDIM 20步 fp32           $21/日
        │ fp16              ÷ 2.5
        ▼
  DDIM 20步 fp16           $8.4/日
        │ xFormers + INT8   ÷ 1.4
        ▼
  TRT INT8                 $6/日
        │ 語義快取 55% hit  × 0.45
        ▼
  最終實際成本             ~$2.7/日  ← $0.000027/張
```

---

## 十、面試答題要點（RKK）

> *「針對電商圖片生成系統，我會選擇 Stable Diffusion XL + TensorRT INT8 量化部署，搭配品牌風格 LoRA（r=16，15MB）實現視覺一致性。推論採 DDIM 20 步，在 A10G 上 0.9s/張，遠低於 3s SLA。條件控制方面，用 ControlNet（Canny 邊緣）確保商品輪廓精確，避免純 prompt 無法控制構圖的問題。峰值處理透過 SQS 任務佇列 + K8s HPA 自動擴縮，以 GPU 佇列長度為擴縮信號，配合語義快取（CLIP embedding cosine > 0.95 命中複用），實測可降低 50% 生成請求。成本方面，10 萬張/日在 $15–20/日 以內，低於 $0.002/張 預算目標 10×，預留足夠空間應對峰值。關鍵取捨是 INT8 量化帶來 FID 損失 0.5，在電商展示圖場景視覺上可接受，但醫療或衛星影像場景需保留 fp16。」*

---

## 十一、系列導航

**← 上一篇**：[Phase 7 Part 2：RAG 系統設計——向量資料庫與混合搜尋架構](/posts/ai-eng-from-scratch-phase7-part2-rag-vector-db-zh/)

**→ 下一篇**：[Phase 8 Part 2：影像生成微調——DreamBooth、LoRA 訓練工程與評估指標](/posts/ai-eng-from-scratch-phase8-part2-finetuning-zh/)

---

*本文為「AI 工程從零開始」系列 Phase 8 第 1 篇，聚焦擴散模型工程原理與生產部署。如有問題歡迎在 GitHub 討論區留言。*
