---
title: "AI 工程從零開始｜Phase 12 Part 1：Vision Transformer 與多模態融合架構"
date: 2026-06-21T20:30:00+08:00
draft: false
weight: 24
description: "深入解析 ViT 的 Patch Embedding 機制、多模態融合策略（Early/Late/Cross-Modal Fusion）、CLIP/ALIGN 對比學習與多模態生產系統設計"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Multimodal", "Vision Transformer", "ViT", "CLIP", "Fusion", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "12 min"
series: ["ai-eng-from-scratch"]
---

> *大多數工程師認為：「把 CNN 的特徵向量和 BERT 的文字向量拼在一起就是多模態了。」*
> *正確的架構師思維是：「視覺與語言的對齊是訓練目標問題，不是拼接問題；*
> *選 Early/Late/Cross-Modal Fusion 取決於任務延遲容忍度與標注成本，*
> *而 CLIP 的零樣本能力來自 4 億圖文對的對比訓練，不是模型架構的魔法。」*

---

這篇給已經用過 CLIP 或 ViT 的預訓練權重、但還沒想過「為什麼直接拼接兩個特徵向量效果不好」的工程師看。讀完你會能手算 ViT 的 patch 序列與注意力成本、解釋 CLIP 的 zero-shot 能力來自對比訓練目標而不是架構、依延遲與標注預算在 Early / Late / Cross-Modal Fusion 之間取捨，並為「以圖搜商品 + 文字精化、P99 < 200 ms」這類需求排出架構與向量索引的升級順序。

---

## 一、核心問題：視覺與語言如何在一個統一模型中對齊

人類理解世界時，視覺與語言天然交織：看到一張「紅色跑車」的圖片，腦中立刻關聯「Ferrari」「速度」「豪華」等語意概念。然而傳統深度學習把圖片分給 CNN、把文字分給 RNN/Transformer，兩條流水線各自訓練，只在最後 MLP 層做粗粒度合併。

這帶來三個核心工程痛點：

1. **語意對齊缺失（Semantic Gap）**：CNN 輸出的 2048 維特徵空間與 BERT 的 768 維文字空間沒有共同原點，直接拼接會導致模態間干擾。
2. **弱監督瓶頸**：傳統多模態需要人工對齊的圖文標注（Image Captioning 資料集），規模上限約 300 萬對；CLIP 透過網路爬取 4 億弱標注對突破此瓶頸。
3. **計算圖割裂**：Early Fusion 讓梯度可以跨模態流動但記憶體開銷 3–5×；Late Fusion 延遲低但跨模態推理能力弱。

Vision Transformer（ViT）的出現是關鍵：它把圖片當成 patch 序列，與文字 token 序列在同一個 Transformer 計算圖中處理，從根本上統一了兩個模態的計算路徑。

---

## 二、何時該升級：從特徵拼接到 CLIP 對齊、再到 Cross-Modal 的觸發條件

最省事的起點是「ResNet 特徵 + Sentence-BERT 向量拼接後接 MLP」：零標注、兩週上線，但兩個特徵空間沒有共同原點，搜尋品質的天花板很低（示意 MRR@10 約 0.3），而且對從未見過的品類沒有 zero-shot 能力。該換成 CLIP 式對齊的訊號是：新品類上架頻繁、每次都要補標注才有召回，或是圖文混合查詢的相關性明顯落後純圖搜。CLIP 的共享嵌入空間讓圖與文可以直接比對，fine-tune 只需凍結視覺端、用十幾二十萬筆商品圖文對微調文字端與投影層（§六）。

第二道門檻是**細粒度跨模態推理**。CLIP 的全局向量對「紅色、亞麻材質、排除某品牌」這種需要把文字 token 對到圖片局部 patch 的查詢仍然弱；當細粒度屬性召回成為主要客訴，而 P99 預算（例如 200 ms）還容得下約 2× 的推理延遲時，才值得上 Cross-Modal Attention（§五）。它的代價是配對圖文訓練資料、更高的 GPU 記憶體，以及任何一端更新都要重訓。向量規模逼近單機 HNSW 的記憶體上限（千萬級）時，再把索引換成分散式向量庫（§八 決策 4）。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| ResNet + BERT 特徵拼接 | CLIP 共享嵌入空間（fine-tune 文字端）| 新品類頻繁上架、每次都要補標注；圖文混合查詢的相關性明顯落後 |
| CLIP Late Fusion | Cross-Modal Attention | 細粒度屬性（顏色／材質／組合條件）召回成為主要客訴；P99 預算容得下 2× 延遲 |
| 單機 HNSW | 分散式向量索引（Milvus 等）| 向量數逼近單機記憶體上限（千萬級），或需要 HA 與即時更新 |

---

## 三、ViT 架構：Patch Embedding 到 CLS Token

Vision Transformer 的核心洞見：**圖片可以被視為一個 patch 序列**，每個 patch 相當於一個「視覺 token」，整體處理流程與 BERT 處理文字完全對稱。

```
輸入圖片 224×224×3
         │
         ▼
┌────────────────────────────────────────────────────┐
│  Patch 切割（stride = patch_size = 16）             │
│                                                    │
│  ┌──┬──┬──┬──┬──┐                                 │
│  │P1│P2│P3│..│P196│  ← 224/16 × 224/16 = 196 patch│
│  └──┴──┴──┴──┴──┘    每個 patch = 16×16×3 = 768 維 │
└────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────┐
│  Linear Projection（Patch Embedding）               │
│  768 → d_model（ViT-B: 768, ViT-L: 1024）          │
└────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────┐
│  [CLS] + 196 Patch Tokens + Position Embedding     │
│  序列長度 = 197 tokens（可學習位置編碼）             │
└────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────┐
│  L × Transformer Encoder Block                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  LayerNorm → Multi-Head Self-Attention       │   │
│  │  → Residual → LayerNorm → MLP (4× hidden)   │   │
│  └─────────────────────────────────────────────┘   │
│  ViT-B/16: L=12, heads=12, d=768                   │
│  ViT-L/16: L=24, heads=16, d=1024                  │
└────────────────────────────────────────────────────┘
         │
         ▼
  [CLS] Token 輸出
  → 圖片全局表示 (768/1024-dim)
  → 接 Classification Head 或對比學習投影層
```

**關鍵設計細節**：

- **CLS Token**：類比 BERT 的 `[CLS]`，是額外加入的可學習 token，在 Self-Attention 中與所有 patch token 互動，最終輸出作為全圖表示。
- **Position Embedding**：ViT 使用 1D 可學習位置編碼（非 2D sinusoidal），研究發現模型可以隱式學習 2D 鄰近關係。
- **計算複雜度**：Self-Attention 對序列長度 N 的複雜度為 O(N²)；197 tokens 在 ViT-B 下單張圖推理約 **8 ms**（A100，batch=1，FP16）。
- **ViT-L/16 在 ImageNet-21k 預訓練 + ImageNet-1k fine-tune 達 85.30% Top-1；改用 JFT-300M 預訓練則是 87.76%**，略高於同樣用 JFT-300M 的 BiT-L（ResNet152x4）87.54%（ViT 論文 Table 2）。差距不大，但 ViT 用的預訓練算力只有 BiT-L 的約 1/4。

---

## 四、ViT vs CNN：歸納偏差的工程取捨

**歸納偏差（Inductive Bias）**是核心差異：

CNN 內建兩項歸納偏差：
1. **局部性（Locality）**：卷積核只看 3×3 或 5×5 鄰域
2. **平移等變性（Translation Equivariance）**：同一物體平移後卷積輸出相應平移

ViT 幾乎沒有這兩項偏差：每個 patch token 從第一層就可以關注任意其他 patch（全局注意力）。這是雙面刃：

**優勢**：
- 可以學習長距離依賴（跨越畫面兩端的關係，CNN 需堆疊很多層才能做到）
- 在大規模資料（JFT-300M+）訓練後，性能超越 CNN
- 統一的序列表示便於多模態融合

**劣勢**：
- **小資料集效果差**：缺乏歸納偏差意味著需要更多資料才能學到等效的空間規律；ImageNet-1k 單獨訓練的 ViT-B 比 ResNet-50 差約 2–3%
- **計算成本**：196 tokens 的 Self-Attention 比 ResNet 的局部卷積更耗記憶體；ViT-L/16 訓練成本約為 ResNet-152 的 5–8×
- **解析度敏感**：改變輸入解析度需要插值位置編碼，性能會略降

**工程決策矩陣**：

| 場景 | 推薦選擇 | 原因 |
|------|----------|------|
| 標注資料 < 10 萬張 | ResNet/EfficientNet | CNN 歸納偏差等效資料增強 |
| 標注資料 > 100 萬張 | ViT-L/16 | 大資料時 ViT 性能上限更高 |
| 多模態融合（下游） | ViT | 序列輸出天然與文字 token 對齊 |
| 邊緣設備推理 | MobileNet/EfficientNet-Lite | ViT 模型太大 |
| 遷移學習（跨域） | ViT（JFT 預訓練） | 更強的通用特徵 |

---

## 五、多模態融合策略：Early / Late / Cross-Modal Fusion

三種融合策略的本質差異在於**梯度流動路徑**和**計算圖合併時機**。

```
              ┌────────────────────────────────────────────────┐
              │             三種融合策略示意                    │
              └────────────────────────────────────────────────┘

Early Fusion（輸入層合併）:
  ┌──────┐  ┌──────┐
  │Image │  │Text  │
  └──┬───┘  └──┬───┘
     │ raw pixels│ tokens
     └─────┬─────┘
           ▼
    ┌─────────────┐
    │ 共用 Encoder │   ← 梯度完全跨模態流動
    │（單一模型）  │      但需要配對資料
    └─────┬───────┘
          ▼ 融合表示

Late Fusion（輸出層合併）:
  ┌──────┐  ┌──────┐
  │Image │  │Text  │
  └──┬───┘  └──┬───┘
     ▼           ▼
 ┌───────┐  ┌───────┐
 │ViT    │  │BERT   │   ← 各自獨立 Encoder
 │Encoder│  │Encoder│      可非同步推理
 └──┬────┘  └──┬────┘
    │  v_img    │  v_txt
    └─────┬─────┘
          ▼
   ┌─────────────┐
   │Concat/Sum/  │   ← 簡單合併，梯度不跨模態
   │Max-pool MLP │
   └─────────────┘

Cross-Modal Fusion（中間層交叉注意力）:
  ┌──────┐  ┌──────┐
  │Image │  │Text  │
  └──┬───┘  └──┬───┘
     ▼           ▼
 ┌───────┐  ┌───────┐
 │ViT    │  │BERT   │
 │Layers │  │Layers │
 │1..6   │  │1..6   │
 └──┬────┘  └──┬────┘
    │ patch     │ tokens
    │ tokens    │
    └─────┬─────┘
          ▼
  ┌──────────────────┐
  │ Cross-Attention  │   ← Query 來自一個模態
  │ K, V 來自另一模態│      梯度跨模態流動
  │ × 6 layers       │      但計算成本高
  └────────┬─────────┘
           ▼ 融合後表示
```

**三種策略量化比較**（電商搜尋任務，500 萬商品；示意估算，非實測）：

| 指標 | Early Fusion | Late Fusion | Cross-Modal |
|------|-------------|-------------|-------------|
| MRR@10 | 0.61 | 0.58 | 0.74 |
| 推理延遲 P99 | 140 ms | 45 ms | 95 ms |
| GPU 記憶體（推理） | 18 GB | 6 GB | 12 GB |
| 標注需求 | 配對圖文（必須同時有） | 可分開標注 | 配對圖文 |
| 訓練成本（相對） | 5× | 1× | 3× |
| 新模態加入難度 | 高（重新訓練） | 低（獨立加入） | 中 |

**決策原則**：
- P99 < 100 ms 且預算有限 → **Late Fusion**
- 需要細粒度跨模態推理（如 VQA、指代消解） → **Cross-Modal**
- 訓練資料充足、允許長延遲（如離線批次推薦） → **Early Fusion**

---

## 六、CLIP 對比學習：大規模弱監督的力量

CLIP（Contrastive Language-Image Pre-Training）的核心貢獻不是模型架構，而是**訓練目標的重新設計**。

**對比學習目標**：

給定 batch 中 N 對圖文 `{(I₁, T₁), (I₂, T₂), ..., (Iₙ, Tₙ)}`，CLIP 最大化正對（同一對）的餘弦相似度，最小化負對（不同對）的相似度：

```
Loss = -1/N × Σᵢ [ log exp(sim(vᵢ, tᵢ)/τ) / Σⱼ exp(sim(vᵢ, tⱼ)/τ) ]
         圖→文方向

       -1/N × Σᵢ [ log exp(sim(tᵢ, vᵢ)/τ) / Σⱼ exp(sim(tⱼ, vᵢ)/τ) ]
         文→圖方向
```

其中 τ（temperature）是可學習參數，初始化為 0.07。

**規模效應是關鍵**：

| 訓練資料規模 | ImageNet Zero-Shot Top-1 |
|-------------|--------------------------|
| 約 1500 萬圖文對（YFCC 子集，論文消融）| 30% 多（量級示意）|
| 4 億圖文對（CLIP 正式版） | **76.2%** |
| 人工標注 ImageNet 1K（ResNet-50） | 76.1%（有監督基線） |

CLIP 用弱標注（網路爬取）的 4 億對達到了與有監督 ResNet-50 相當的 zero-shot 能力，這是多模態預訓練的里程碑。

**零樣本分類機制**：

```
推理時不需要任何標注範例：

1. 為每個類別建立 prompt：
   "a photo of a {class_name}"
   例：["a photo of a cat", "a photo of a dog", ...]

2. 計算 query 圖片的 visual embedding（ViT-B/32）

3. 計算所有 prompt 的 text embedding

4. 餘弦相似度最高的 prompt 對應的類別即為預測結果
```

**生產系統注意事項**：

- **Prompt Engineering 影響顯著**：「a photo of {class}」vs「a product image of {class}」在電商任務差距可達 3–5%
- **Domain Shift**：CLIP 在通用圖片表現佳，但在醫療影像、衛星圖等專業域需 fine-tune
- **Fine-tune 策略**：凍結 Visual Encoder，只 fine-tune Text Encoder + projection layer，可用 20 萬對資料在 A100×4 跑 1 天（4 × 24 h × $3.09/GPU-h ≈ $300）達到 3–8% 提升
- **批量大小影響**：對比學習依賴 large batch（CLIP 原版用 32768），smaller batch 需用 MoCo 等 memory bank 技巧

---

## 七、多模態預訓練：ALIGN / BLIP / Flamingo 演進

多模態預訓練在 2021–2023 年快速演進，每個系列解決了前一代的核心瓶頸：

**CLIP（2021）**：
- 核心貢獻：4 億弱標注對 + 對比學習
- 瓶頸：只有 image-text matching，無生成能力；Caption 品質依賴爬取文字

**ALIGN（2021）**：
- 核心貢獻：18 億圖文對（比 CLIP 大 4.5×），雜訊更多但規模更大
- 發現：**Noise is OK at scale** — 資料量的提升可以抵消標注雜訊的傷害
- 效果：ImageNet zero-shot 76.4%（微幅超越 CLIP 的 76.2%）

**BLIP（2022）**：
- 核心貢獻：引入 **Bootstrapping**——用自己訓練的 Captioner 補寫字幕、再用自己的 ITM（image-text matching）Filter 篩掉雜訊配對（CapFilt），迭代提升資料品質
- 新能力：同時支援 Image Captioning、VQA、Image-Text Retrieval
- 模型架構：Unified Encoder-Decoder（可做 understanding 也可做 generation）

**Flamingo（2022）**：
- 核心貢獻：**few-shot 多模態推理**，在 prompt 中插入任意張圖片
- 技術：Perceiver Resampler（把可變長度 patch tokens 壓縮為固定 64 個 visual tokens）+ Gated Cross-Attention Layer 插入 frozen LLM
- 效果：VQAv2 上 32-shot 達 67.6%（不需微調就逼近當時的微調 SOTA），全量 fine-tune 後 82.0%

**演進趨勢總結**：

```
CLIP          →  BLIP          →  Flamingo / LLaVA
對比學習         生成 + 理解       插入 LLM，多輪對話
圖文匹配         資料自舉           few-shot 推理
4 億對           弱監督清洗         凍結 LLM + 適配層
```

**工程選型建議**：
- 搜尋/排序任務 → CLIP fine-tune（推理快，embedding 可預計算）
- 圖片問答/描述生成 → BLIP-2 或 LLaVA
- 多輪多圖對話 → LLaVA 式「視覺編碼器 + projector + LLM」開源 VLM（如 Qwen-VL、InternVL 系列），或原生多模態的商用 API。Flamingo 的官方權重從未公開，它的價值在於 Perceiver Resampler + Gated Cross-Attention 的設計思路，而不是可直接部署的模型

> 2023 年之後的主流演進：視覺編碼器多改用 SigLIP（sigmoid loss 取代 CLIP 的 softmax 對比損失），連接方式從 cross-attention 收斂到較簡單的 projector，前沿商用模型則走向原生多模態。

---

## 八、為什麼選 X 不選 Y

Cross-Attention 與拼接的差異已在決策 3 與 §五的比較表中涵蓋；對比學習 vs MAE 不是融合架構的決策，留給預訓練目標的討論。這裡只留四個真正需要權衡的決策。

### 決策 1：ViT vs CNN

| 選擇 | 選 ViT 的理由 | 不選 CNN 的理由 |
|------|-------------|----------------|
| 多模態融合下游 | 序列輸出與文字 token 同構，Cross-Attention 天然適用 | CNN 特徵圖需額外展平/池化，丟失空間細節 |
| 大資料預訓練 | 無歸納偏差讓模型充分學習資料分布（JFT 300M+） | CNN 歸納偏差在大資料時成為上限 |
| 長距離依賴任務 | Self-Attention O(1) 跳數即可關注全圖 | CNN 需堆疊多層，感受野擴展慢 |

**Flip Condition**：標注資料 < 10 萬張時，EfficientNet-B4 仍優於 ViT-B；邊緣推理（< 50 ms, mobile）時 CNN 更實用。

---

### 決策 2：CLIP Zero-Shot vs 有監督 Fine-tune

| 選擇 | 選 CLIP Zero-Shot | 不選純監督 |
|------|-----------------|-----------|
| 新品類頻繁上架 | 無需重新標注，立刻有召回能力 | 每次新品類需 500+ 標注，週期 2–3 週 |
| 標注預算有限 | 4 億對預訓練已涵蓋廣泛語意 | 有監督在小資料集容易過擬合 |
| Prompt 可調整 | 改變 prompt template 即可調整分類邊界 | 改變類別定義需重新標注 |

**Flip Condition**：垂直域資料（醫療、工業缺陷）與網路圖片分布差距 > 30% 時，必須 fine-tune；CLIP zero-shot 在這些域通常比有監督基線差 15–25%。

---

### 決策 3：Early Fusion vs Late Fusion

| 選擇 | 選 Late Fusion 的理由 | 不選 Early Fusion |
|------|---------------------|-----------------|
| 推理延遲要求 < 60 ms | 兩個 Encoder 可平行跑，拼接只需 0.5 ms | Early Fusion 必須序列處理，P99 ≈ 140 ms |
| 標注資料不對齊 | 圖片和文字可以分開標注、分開更新 | Early Fusion 需要嚴格配對資料 |
| 模型更新頻率不同 | 圖片 Encoder 和文字 Encoder 可獨立版本管理 | 任何一端更新都需要重新訓練整體 |

**Flip Condition**：任務需要細粒度跨模態推理（如「找圖中紅色物體對應的說明文字」）時，Late Fusion MRR@10 比 Cross-Modal 低 16 個點，值得付出 2× 延遲代價。

---

### 決策 4：Milvus 分散式向量索引 vs 單機 FAISS

| 選擇 | 選 Milvus | 不選 FAISS 單機 |
|------|----------|---------------|
| 向量規模 > 1000 萬 | Shard 水平擴展，單 Shard 500 萬向量 | FAISS 單機 16 GB 記憶體上限約 500 萬 × 512 dim |
| 高可用需求 | 主副本自動 failover，SLA 99.9% | FAISS 無內建 HA，機器重啟索引需重建（約 20 分鐘） |
| 動態更新 | 支援實時向量插入/刪除 | FAISS 可用 `add()` 增量加入向量，但刪除與資料分佈漂移後的重新分群（IVF 需重新 train）較麻煩，通常靠批次重建 |
| 監控可觀測性 | 內建 Prometheus metrics、查詢延遲 P99 監控 | FAISS 需自行包裝監控 |

**Flip Condition**：向量數 < 500 萬且團隊 Infra 人力有限時，FAISS + Redis 快取是更簡單的選擇，維護成本低 3–5×；Milvus 叢集運維複雜度不可低估。

---

## 九、系統效應：單模態 vs 多模態的能力躍升數字

以電商「以圖搜商品 + 文字精化」場景為基準：

| 指標 | 單模態（純圖片搜尋）| Late Fusion（CLIP）| Cross-Modal Fusion | 提升（單 → 跨模態）|
|------|------------------|-------------------|-------------------|-------------------|
| MRR@10（相關性）| 0.38 | 0.58 | 0.74 | +95% |
| Recall@20（召回率）| 55% | 71% | 83% | +51% |
| 新品類 Zero-Shot Recall@20 | 12% | 71% | 75% | +492%（(75−12)/12）|
| P99 推理延遲 | 35 ms | 45 ms | 95 ms | 延遲 +171%（代價）|
| 標注成本（初始建立索引）| $8,000 | $300（fine-tune，見 §六）| $3,500 | 依策略不同 |
| 細粒度屬性識別準確率 | 48% | 63% | 79% | +65% |
| 使用者點擊率（CTR）| 3.2% | 5.1% | 6.4% | +100% |
| NDCG@10 | 0.41 | 0.62 | 0.77 | +88% |

> 以上為電商情境的示意估算，非實測數據。

**關鍵洞察**：
- **新品類 Zero-Shot** 是最大躍升點（+492%）：這代表業務可以在不補標注的情況下，CLIP 就能對新上架商品形成基本召回能力
- **P99 延遲代價**：Cross-Modal Fusion 比純圖片搜尋慢 171%，但絕對值 95 ms 仍在 200 ms SLA 內
- **標注成本**：CLIP fine-tune 僅需 20 萬對（約 $300 訓練成本），比傳統有監督標注的 $8,000 節省 95%+

---

## 十、系列導航

| | |
|---|---|
| ← 上一篇 | [Phase 11 Part 2：RAG 系統與 LLM 評估 — 生產落地的最後一哩](/posts/ai-eng-from-scratch-phase11-part2-rag-evals-zh/) |
| → 下一篇 | [Phase 12 Part 2：多模態 Agent 與電腦操作 — 跨模態推理與行動](/posts/ai-eng-from-scratch-phase12-part2-agents-computer-use-zh/) |

---

*本文為「AI 工程從零開始」系列第 12 階段第 1 篇，聚焦 Vision Transformer 基礎架構與多模態融合策略的工程決策框架。系列完整目錄請見 [ai-eng-from-scratch](/tags/ai-eng-from-scratch/)。*
