---
title: "AI 工程從零開始｜Phase 8 Part 2：GAN 與影片生成 — 對抗的藝術"
date: 2026-06-21T17:00:00+08:00
draft: false
weight: 17
description: "深入解析 GAN 訓練動態、StyleGAN/CycleGAN 架構、影片生成系統設計，以及 GAN vs 擴散模型的工程選型決策"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Generative AI", "GAN", "Video Generation", "StyleGAN", "Image Synthesis", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "13 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人以為 GAN 是「讓兩個神經網路互相競爭」。*
> *正確答案是：GAN 是一個精心設計的賽局均衡問題——*
> *訓練的藝術在於讓 Generator 和 Discriminator 以恰好正確的速度成長，*
> *任何一方跑太快，整個系統就會崩潰。*

---

這篇給知道 GAN 是「兩個網路互相對抗」、但沒親手處理過一次模式崩潰的工程師看。讀完你會能從 loss 曲線與 FID 判斷訓練是震盪、崩潰還是梯度消失，解釋 WGAN-GP 與 Spectral Norm 各自修正了什麼，看懂 StyleGAN 的風格注入與 CycleGAN 的循環一致性損失，並能為一個「日處理 50 萬張、延遲 < 200ms」的商品圖風格轉換系統，在 GAN 與擴散模型之間做出有依據的選擇。

---

## 一、核心問題：對抗訓練的本質與脆弱性

GAN（Generative Adversarial Network）由 Ian Goodfellow 於 2014 年提出，核心概念極為優雅：一個 Generator（偽造者）和一個 Discriminator（鑑別者）相互對抗，在賽局均衡中收斂到完美生成能力。

**理論之美與工程之痛的落差：**

理論上，當 Generator 生成的分佈完全匹配真實資料分佈時，Discriminator 的最優策略是輸出 0.5（無法分辨）。這個均衡點在數學上可以被證明存在，且對應的 Generator 是完美的。

然而工程現實截然不同：
- **模式崩潰（Mode Collapse）**：Generator 學會只生成幾種「能騙過 Discriminator」的樣本，多樣性消失。FID（Fréchet Inception Distance）飆升至 100+ 而訓練 loss 看起來正常。
- **梯度消失（Vanishing Gradient）**：Discriminator 太強時，Generator 收到的梯度趨近於零，學習停滯。
- **訓練震盪**：兩者的 loss 呈鋸齒狀，沒有明確的收斂信號。
- **超參數敏感性**：學習率差距 10x 即可讓整個訓練崩潰。

這些不是 GAN 的「缺陷」，而是對抗訓練本質的體現——兩個玩家的賽局均衡遠比單一損失函數的最佳化複雜。

**GAN 仍值得學習的理由：**
- 推論速度：單次前向傳播，A100 上 512×512 圖片 < 15ms，Diffusion 需要 50–200 步去噪，約 1–5s
- 潛在空間可插值：StyleGAN 的風格空間允許精確控制人臉年齡、表情、髮型
- 訓練資料效率：CycleGAN 無需配對資料，只需兩個域的圖片集合即可訓練
- 特定任務 SoTA：pix2pix 在語義分割→照片轉換任務上 FID 仍優於早期 Diffusion

---

## 二、何時該升級：從 DCGAN 到 WGAN-GP 與 StyleGAN2 的觸發條件

單 GPU 上的 DCGAN 配 BCE loss、batch 64、lr 0.0002，足以驗證 Generator 學不學得到資料分佈的基本形狀；代價是沒有 EMA、沒有漸進式訓練，訓練有相當機率在 10K 步內崩潰，而且崩潰時 loss 看起來往往很正常。該換成 WGAN-GP（或 Spectral Norm）加 EMA 的訊號是 **BCE 已經不再是可用的訓練信號**：D loss 趨近 0 而 G loss 爆炸（梯度消失），或 FID 停滯甚至上升但 loss 曲線平穩（模式崩潰）。Wasserstein 距離給的是單調的收斂指標，這才是升級的真正收穫，而不是「更先進的架構」。

第二道門檻是**需求超出 DCGAN 架構本身**：要生成 512 以上解析度（從頭直接訓 1024×1024 不穩定，需要漸進式增長或 StyleGAN2 的架構），要控制屬性與插值（W 空間與 style mixing），或訓練資料少於約 1 萬張（需要 ADA 自適應增強）。部署端的門檻則是延遲 SLA：單張 < 50ms 時才值得做 TensorRT INT8 量化與 K8s 自動擴縮。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| DCGAN + BCE loss，單 GPU | WGAN-GP（或 Spectral Norm）+ EMA + 漸進式訓練 | D loss → 0 且 G loss 爆炸；FID 停滯或上升但 loss 平穩；需要能判斷「有沒有收斂」的指標 |
| WGAN-GP，≤ 256×256 | StyleGAN2 + ADA，1024×1024 | 需要 512 以上解析度；需要屬性控制／風格混合；訓練資料 < 1 萬張 |
| PyTorch FP32 推論 | TensorRT INT8 + 自動擴縮 | 單張延遲 SLA < 50ms；流量峰谷差超過一個數量級 |

---

## 三、GAN 原理：Generator vs Discriminator 賽局

### 數學基礎

GAN 的目標函數是一個 minimax 賽局：

```
min_G max_D V(D, G) = E[log D(x)] + E[log(1 - D(G(z)))]
```

直觀解釋：
- **D** 想最大化正確分類真假的能力
- **G** 想最小化 D 正確分類的能力
- 均衡點：`D(G(z)) = 0.5`，D 無法分辨真假

### 架構流程

```
                    ┌─────────────────────────────────────┐
                    │         GAN 訓練迴圈                 │
                    └─────────────────────────────────────┘

  隨機雜訊          ┌──────────────┐      生成樣本
  z ~ N(0,1) ──────▶│  Generator G │──────────────────┐
  [batch, 128]      │  (上採樣層)  │  [batch, C, H, W] │
                    └──────────────┘                   │
                                                       ▼
  真實資料                                   ┌──────────────────┐
  x ~ p_data ────────────────────────────▶  │  Discriminator D │
                                             │  (下採樣層)      │
                                             └────────┬─────────┘
                                                      │
                                                      ▼
                                              Real / Fake score
                                                      │
                    ┌─────────────────────────────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │   Loss 計算          │
          │ L_D = -E[log D(x)]  │
          │      -E[log(1-D(G))]│
          │ L_G = -E[log D(G(z))]│
          └─────────────────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
      更新 D              更新 G
   (maximize loss)    (minimize loss)
```

### 關鍵工程細節

**訓練比例（D:G steps）：**
- 標準比例：1:1（每更新 D 一次，更新 G 一次）
- WGAN 建議：5:1（D 更新 5 次，G 更新 1 次）
- 經驗法則：若 D loss 趨近 0，G 梯度消失 → 增加 G 更新頻率

**學習率設定：**
- 兩者分離設定，不共享優化器
- G lr ≈ 0.0002, D lr ≈ 0.0002（DCGAN 建議）
- WGAN-GP 建議 lr ≈ 0.0001，Adam β1=0, β2=0.9
- 一般規則：D lr 不超過 G lr 的 5 倍

---

## 四、訓練不穩定：模式崩潰/梯度消失的診斷與修復

### 症狀識別表

| 症狀 | 量化信號 | 根因 | 修復方法 |
|------|----------|------|----------|
| Mode Collapse | FID > 100，IS < 2，樣本視覺相似 | G 找到「最安全」的欺騙策略 | Minibatch discrimination, Unrolled GAN |
| Vanishing Gradient | D loss ≈ 0，G loss 爆炸 | D 太強，G 梯度消失 | WGAN-GP，降低 D 學習率，Label smoothing |
| 訓練震盪 | Loss 鋸齒，FID 不收斂 | 兩者能力不匹配 | 漸進式訓練，EMA，調整 D:G 比例 |
| 棋盤格偽影 | 高頻鋸齒紋理 | ConvTranspose 步長問題 | 改用 Resize + Conv，即 SubpixelConv |
| 訓練崩潰 | G output 全黑或全灰 | 梯度爆炸，G 陷入退化解 | Spectral Normalization，梯度裁剪 |

### Wasserstein 損失的工程優勢

標準 GAN 使用 Binary Cross-Entropy，在 D 接近完美時梯度趨近零：

```
∂L_G/∂θ_G ≈ 0  當  D(G(z)) ≈ 0
```

WGAN 改用 Wasserstein 距離（Earth Mover's Distance）：

```python
# WGAN-GP 關鍵程式碼
def compute_gradient_penalty(D, real, fake):
    alpha = torch.rand(real.size(0), 1, 1, 1).to(device)
    interpolated = alpha * real + (1 - alpha) * fake
    interpolated.requires_grad_(True)
    
    d_interp = D(interpolated)
    gradients = torch.autograd.grad(
        outputs=d_interp, inputs=interpolated,
        grad_outputs=torch.ones_like(d_interp),
        create_graph=True, retain_graph=True
    )[0]
    
    gp = ((gradients.norm(2, dim=1) - 1) ** 2).mean()
    return gp

# D 的總損失
loss_D = -real_score.mean() + fake_score.mean() + lambda_gp * gp
```

**工程效益**：WGAN-GP 的 Wasserstein 距離是有意義的收斂信號（值越低越好），而 BCELoss 接近 log(2) ≈ 0.693 時才是均衡，但這個信號噪音很大。

### Spectral Normalization

限制 D 每層的 Lipschitz 常數，比 WGAN-GP 的梯度懲罰計算更快（不需要計算二階梯度）：

```python
from torch.nn.utils import spectral_norm

# 在 D 的每個 Conv 層包一層 spectral_norm
self.conv1 = spectral_norm(nn.Conv2d(3, 64, 4, 2, 1))
```

**效能對比**：Spectral Norm 額外計算開銷 ~5%，WGAN-GP 因需要計算 Hessian 約慢 30%。

---

## 五、StyleGAN 架構：風格注入與潛在空間操控

### 核心創新：將「風格」從「內容」解耦

傳統 GAN 直接把 z 送進 Generator。StyleGAN 的革命性做法：

```
┌────────────────────────────────────────────────────────────────┐
│  StyleGAN 架構（v1 用 AdaIN；v2 改用 weight demodulation）     │
│                                                                │
│  隨機雜訊 z ──▶ [Mapping Network f: 8層MLP] ──▶ w ∈ W空間     │
│                                                      │         │
│                         ┌────────────────────────────┘         │
│                         │  w 透過 Affine 轉換注入每一層          │
│                         ▼                                      │
│  固定常數 ──▶ [Synthesis Block 4×4]                            │
│                   │ ↑ AdaIN(w)  ↑ Noise B                     │
│               [Synthesis Block 8×8]                            │
│                   │ ↑ AdaIN(w)  ↑ Noise B                     │
│               [Synthesis Block 16×16]                          │
│                   │ ...                                         │
│               [Synthesis Block 1024×1024] ──▶ 生成圖片          │
│                                                                │
│  W 空間的語義結構：                                              │
│  w[0:2]   → 粗粒度特徵（臉部結構、頭部姿態）                    │
│  w[3:7]   → 中粒度特徵（表情、眼鏡、髮型）                      │
│  w[8:17]  → 細粒度特徵（膚色、光線、微細紋理）                  │
└────────────────────────────────────────────────────────────────┘
```

### AdaIN（Adaptive Instance Normalization）

風格注入的核心機制：

```python
def adain(content_feat, style_feat):
    """
    content_feat: 合成網路中間層特徵 [B, C, H, W]
    style_feat:   從 w 透過仿射變換得到的風格向量 [B, C]
    """
    size = content_feat.size()
    style_mean = style_feat[:, :, 0:1, 0:1]  # γ（scale）
    style_std  = style_feat[:, :, 1:2, 0:1]  # β（shift）
    
    # 先正規化 content，再用 style 的統計量重縮放
    normalized = F.instance_norm(content_feat)
    return style_std * normalized + style_mean
```

### W+ 空間與風格混合

StyleGAN 的殺手級應用：**Style Mixing**

```python
# 用兩個不同的 w 向量控制不同解析度層
w1 = mapping_network(z1)  # 控制粗粒度（結構）
w2 = mapping_network(z2)  # 控制細粒度（紋理）

# 在第 8 層切換
for i, block in enumerate(synthesis_blocks):
    w = w1 if i < 8 else w2
    x = block(x, w)
```

**量化成就（StyleGAN2，FFHQ 1024×1024）：**
- FID = **2.84**（2020 年 SOTA）
- PPL（Perceptual Path Length）= 145（StyleGAN2 論文 Table 1 config F；StyleGAN1 為 212，越低代表潛在空間越平滑）
- 訓練：8× V100，約 9 天 18 小時（官方 repo 的 config F，FFHQ 1024×1024，25,000 kimg）

---

## 六、條件 GAN：Pix2Pix / CycleGAN / SPADE

### Pix2Pix：配對資料的監督式轉換

**適用場景**：語義分割圖 → 照片、輪廓 → 圖片、衛星圖 → 地圖

```
條件輸入 x ──▶ [U-Net Generator] ──▶ 輸出 y_fake
                                           │
條件輸入 x ──────────────────────────▶ [PatchGAN D]
真實目標 y ──────────────────────────▶          │
                                                 ▼
                                      real / fake (70×70 patches)
```

PatchGAN 的工程洞見：不判斷整張圖真假，而是判斷 70×70 的 patch，讓 D 專注局部紋理的真實性。這使得 G 更難「作弊」，且計算量大幅降低。

**損失函數**：`L = L_GAN + λ * L_L1`（λ=100），L1 確保大致結構正確，GAN 負責細節真實感。

### CycleGAN：無配對資料的域轉換

**核心貢獻**：循環一致性損失（Cycle Consistency Loss）

```
馬 ──▶ [G_AB] ──▶ 斑馬_fake ──▶ [G_BA] ──▶ 馬_reconstructed
│                                                     │
└─────── L_cycle = ||馬_reconstructed - 馬|| ──────────┘

斑馬 ──▶ [G_BA] ──▶ 馬_fake ──▶ [G_AB] ──▶ 斑馬_reconstructed
```

**工程限制**：
- CycleGAN 無法改變物體的幾何形狀（只能改變紋理/顏色）
- 記憶體需要：兩個 G + 兩個 D，批次大小通常只能設 1–4
- 訓練時間：NVIDIA V100 × 1，約 2–3 天

### SPADE：語義感知的歸一化

SPADE（Spatially-Adaptive Denormalization）針對語義分割 → 高解析度圖片的問題，改良 AdaIN：

不同於 AdaIN 用全局風格向量，SPADE 根據**空間位置**的語義標籤決定歸一化參數，讓天空區域和草地區域有完全不同的紋理處理。

**代表成果**：GauGAN（NVIDIA）在風景圖生成上，FID 從 pix2pix 的 81.8 降至 22.6。

---

## 七、影片生成：時間一致性的工程挑戰

### 核心難題

影片生成 ≠ 逐幀圖片生成。最大挑戰是**時間一致性**：

- 相鄰幀之間的像素級連貫性（閃爍問題）
- 物體運動的物理一致性（手臂不能突然消失）
- 長距離依賴（30 fps × 5 秒 = 150 幀的全局協調）

### VideoGAN / MoCoGAN 架構

```
┌────────────────────────────────────────────────────────────────┐
│  MoCoGAN：內容與動作的解耦                                      │
│                                                                │
│  內容向量 z_C（固定）──────────────────────────────────────┐   │
│                                                            │   │
│  動作 RNN：                                                 │   │
│  z_M(0) ──▶ [GRU] ──▶ z_M(1) ──▶ [GRU] ──▶ z_M(2) ──▶ ...│   │
│                │               │               │           │   │
│                ▼               ▼               ▼           ▼   │
│  concat(z_C + z_M(t)) ──▶ [Image Generator] ──▶ Frame(t)  │   │
│                                                            │   │
│  判別器：                                                   │   │
│  ┌────────────────┐  ┌────────────────────────────────┐   │   │
│  │ Image D（單幀）│  │ Video D（多幀時序一致性判斷）   │   │   │
│  └────────────────┘  └────────────────────────────────┘   │   │
└────────────────────────────────────────────────────────────────┘
```

### 光流一致性損失

強制相鄰幀之間符合光流估計：

```python
def temporal_consistency_loss(frames, optical_flow_net):
    """
    frames: [B, T, C, H, W]  T 個時間步的幀
    """
    total_loss = 0
    for t in range(len(frames) - 1):
        flow = optical_flow_net(frames[t], frames[t+1])
        # 根據光流 warp 第 t 幀
        warped = warp(frames[t], flow)
        # 計算 warped 幀與第 t+1 幀的差距
        total_loss += F.l1_loss(warped, frames[t+1])
    return total_loss / (len(frames) - 1)
```

### 影片生成的工程成本

| 任務 | 模型 | 解析度 | 生成時間（示意） | GPU 記憶體（示意） |
|------|------|--------|----------|------------|
| 1 秒影片（30 幀）| VideoGAN | 256×256 | ~8s | 24GB |
| 1 秒影片（30 幀）| Stable Video Diffusion | 512×512 | ~25s | 40GB |
| 5 秒影片（81 幀）| Wan 2.1（1.3B / 14B） | 480p | 數分鐘 | ~8GB / ~80GB |
| 即時影片（> 30fps）| 目前無解，需要串流 GAN | 256×256 | < 33ms/frame | 16GB |

*示意估算，非實測數據；Wan 2.1 的幀數與 1.3B 版本的 VRAM 需求取自官方 README。*

**工程結論**：現代影片生成以 Diffusion 為主流，且主力已轉向 **Video DiT**（3D VAE 把影片壓成時空 latent，再以時空注意力的 Transformer 去噪，多搭配 flow matching；Sora、Wan 系列皆屬此類）；GAN 在即時影片編輯（濾鏡、換臉）等低延遲場景仍有一席之地。

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|-------------|---------------|----------------|
| **WGAN-GP vs Vanilla GAN** | 有意義的收斂指標（W-distance↓），D 接近完美時 G 仍有梯度 | BCELoss：D 太強時 G 梯度消失，容易模式崩潰，無法知道訓練是否真正收斂 | 若 GP 的二階梯度計算成為瓶頸（每步約慢 30%），改用 Spectral Norm 限制 D 的 Lipschitz 常數 |
| **GAN vs Diffusion** | 單次前向傳播 < 15ms；TensorRT 量化後 512×512 < 50ms；特定域（臉部）FID 仍領先；資料效率高 | Diffusion：50–200 步去噪，即使 DDIM 加速仍需 1–5s；但多樣性、文字條件控制與訓練穩定性全面佔優 | 延遲 SLA > 500ms、需要文字條件或開放域生成 → Diffusion；延遲 < 100ms 或固定域風格轉換 → GAN |
| **CycleGAN vs Pix2Pix（無配對資料）** | 不需要配對資料集，兩個域的圖片各一批即可訓練 | Pix2Pix：需要嚴格配對的輸入輸出對，配對不完美時品質反而更差 | 若有充足配對資料（> 5K 對），Pix2Pix 的 L1 監督讓結構對齊更準，品質通常更好 |
| **TensorRT INT8 vs FP32 推論** | INT8 比 FP32 快 3–4×，記憶體減少 75%；A10G 上 512×512 從 60ms 降至 15ms | FP32：精度最高，量化無誤差，除錯更容易 | 若模型有 BN 層且資料分佈特殊，INT8 校準誤差可能 > 5%，需要 FP16 作為折衷 |

---

## 九、系統效應（GAN vs Diffusion 對比）

### 核心指標對比表

| 維度 | GAN（StyleGAN2）| Diffusion（SDXL）| 差距說明 |
|------|----------------|------------------|----------|
| **FID（臉部）** | 2.84 | ~4.5 | GAN 在特定域仍有優勢 |
| **FID（通用）** | ~30–50 | ~8–15 | Diffusion 通用性更好 |
| **推論延遲** | 15–50ms | 1,000–5,000ms | GAN 快 **20–100×** |
| **推論成本/張** | ~$0.00001（StyleGAN2 1024²，~40ms/張，A10G） | ~$0.0002（SD v1.5 512²，20 步 fp16，1.0s/張，A10G；與 [Phase 8 Part 1 §九](/posts/ai-eng-from-scratch-phase8-part1-diffusion-models-zh/) 同基準） | GAN 便宜 **~20×**（0.75/3600 × 秒數） |
| **模式多樣性** | 中（模式崩潰風險）| 高（無此問題）| Diffusion 佔優 |
| **文字條件控制** | 弱（需要 CLIP 額外模組）| 強（訓練時即對齊）| Diffusion 佔優 |
| **訓練穩定性** | 低（需要大量調參）| 高（可預測收斂）| Diffusion 佔優 |
| **訓練資料需求** | 10K–1M 張圖片 | 數億張圖片 | GAN 資料效率更好 |
| **風格可控性** | 高（StyleGAN W 空間）| 中（需要 ControlNet）| GAN 佔優 |
| **微調成本** | 低（DreamBooth-style 約 $5）| 低（LoRA 約 $10）| 相近 |

*示意估算，非實測數據*

### 實際業務場景選型指南

| 場景 | 建議選型 | 理由 |
|------|----------|------|
| 電商商品圖風格轉換，< 200ms SLA | **GAN（CycleGAN/pix2pix）** | 延遲達標，批次處理成本低約 20× |
| 社群媒體濾鏡（即時預覽）| **GAN（輕量 Generator）** | 手機端 < 30ms 可行 |
| 廣告創意生成（高品質優先）| **Diffusion（SDXL/FLUX）** | FID < 10，文字控制靈活 |
| 醫療影像增強（需要可解釋性）| **GAN（條件 GAN）** | 可控性高，不需要龐大算力 |
| 影片風格轉換（每幀獨立）| **GAN + 光流後處理** | 每幀 < 50ms，光流修正閃爍 |
| 通用圖片生成（無延遲限制）| **Diffusion** | 品質、多樣性、可控性全勝 |

*示意估算，非實測數據*

---

## 十、系列導航

本文是《AI 工程從零開始》Phase 8 的第二篇。

**系列文章：**

← 上一篇：[Phase 8 Part 1：擴散模型 — 從雜訊到藝術的數學](/posts/ai-eng-from-scratch-phase8-part1-diffusion-models-zh/)

→ 下一篇：[Phase 9：強化學習基礎 — RLHF 與遊戲 AI 的根基](/posts/ai-eng-from-scratch-phase9-part1-rl-fundamentals-zh/)

---

**Phase 8 小結**：生成式 AI 的工程選型從來不是「最新 = 最好」。GAN 在低延遲、特定域、資料效率等場景仍不可取代；Diffusion 在通用性、多樣性、文字控制上全面領先。優秀的 AI 工程師需要理解兩者的技術本質，根據業務約束做出正確決策——這正是 AI 工程師最核心的能力。
