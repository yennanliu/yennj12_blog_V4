---
title: "AI 工程從零開始｜Phase 7 Part 1：Transformer 架構深度解析 — 改變一切的注意力"
date: 2026-06-21T15:30:00+08:00
draft: false
weight: 14
description: "從工程師視角完整解析 Transformer：Multi-Head Attention 矩陣計算、位置編碼、KV Cache、Flash Attention 與 MQA/GQA 生產優化"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Transformer", "Attention", "KV Cache", "Architecture", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "16 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人覺得 Transformer 就是「注意力機制加上前饋網路」，說完就結束了。*
> *真正的工程師知道：矩陣分塊如何影響 GPU 記憶體帶寬，KV Cache 如何讓每個 decode 步驟不必重算整段前文（首 token 延遲則由 prefill 決定），*
> *為什麼 GQA 能在保持 95% 品質的前提下省掉 75% 的快取記憶體。*
> *架構不是魔法——它是一系列在硬體限制下做出的工程取捨。*

---

這篇給已經用 Hugging Face 跑過 LLM 推理、但還沒算過一次注意力矩陣有多大的工程師看。讀完你會能手算 Self-Attention 的計算與記憶體複雜度、解釋 KV Cache 為什麼只加速 decode 步驟而不改變首 token 延遲、說明 Flash Attention 省的是 HBM 讀寫而不是 FLOPs，並能為「7B 模型、P99 首 token < 500ms、吞吐 > 200 req/s、40GB GPU 記憶體」這樣的部署目標，在 dtype、GQA 與 PagedAttention 之間做出有數字支撐的取捨。

---

## 一、核心問題：為什麼 Transformer 取代了一切

### 1.1 RNN/LSTM 的根本瓶頸

在 Transformer 出現之前，序列模型靠 RNN 與 LSTM。它們有一個無法繞開的硬傷：**序列依賴（sequential dependency）**。

```
時間步 t=1 → t=2 → t=3 → ... → t=n
每步必須等上一步完成，無法並行
```

後果：
- 訓練速度隨序列長度線性增長
- 梯度消失導致長距依賴難以學習
- GPU 大量計算資源閒置（利用率 < 30%）

### 1.2 Transformer 的核心洞見

Vaswani et al. (2017) 的 "Attention is All You Need" 提出一個激進的想法：**把序列的所有位置一次全部看完，用相似度分數決定誰影響誰**。

核心公式：

```
Attention(Q, K, V) = softmax( QKᵀ / √dₖ ) · V
```

這一行公式帶來三個工程上的革命：
1. **完全並行化**：所有位置可同時計算，GPU 利用率 > 90%
2. **直接長距建模**：token i 與 token j 的依賴關係與距離無關
3. **可微分的記憶體讀寫**：注意力分數決定「讀哪裡」，梯度可反向傳播

---

## 二、何時該升級：從 HF generate 到 vLLM 與量化部署的觸發條件

用 Hugging Face Transformers 的 `from_pretrained()` + `generate()` 在單張 GPU 上跑，足以驗證模型輸出品質——它預設就啟用 KV Cache，單一請求的 decode 速度並不差。它的限制在**並發**：請求逐一串行處理、沒有 continuous batching、KV Cache 以靜態方式預先分配。該升級到 vLLM 的訊號是 P99 延遲開始由排隊時間主導（並發 > 1 時就會發生），或是 GPU 記憶體被 padding 與預分配的 KV 區塊佔滿、批次塞不進更多請求；PagedAttention 把碎片率從 60–80% 壓到 < 4%，吞吐提升 2–4×（§六）。

第二道門檻是**記憶體而非吞吐**：7B MHA 模型在 4K 上下文下每個請求的 KV Cache 約 2.1 GB，16 路並發就是 33.6 GB（§六的計算）。此時能動的槓桿有兩個——換用 GQA 的 checkpoint（如 Llama 3 8B 的 8 個 KV heads，KV Cache ÷ 4），以及 INT8/INT4 權重量化把模型本身的 14 GB 減半。要注意 GQA 是預訓練 checkpoint 的架構屬性，不是部署時能「加上去」的優化；Llama-2 7B 是 MHA，改不了。Flash Attention 在 vLLM 中預設開啟，它的價值在長 prompt 的 prefill 階段才看得到。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| HF `generate()`，請求串行 | vLLM：continuous batching + PagedAttention | 並發 > 1 且 P99 由排隊時間主導；KV 記憶體碎片讓批次塞不滿 |
| MHA checkpoint + BF16 | GQA checkpoint（如 Llama 3 8B）+ INT8/INT4 權重量化 | 批次的 KV Cache 總量超過記憶體預算（16 路 × 2.1 GB ≈ 34 GB）；模型權重佔掉一半 VRAM |
| 短 prompt、標準 attention | Flash Attention 2（vLLM 預設） | prompt > 2K tokens 時，prefill 的 n² 記憶體與 HBM 往返成為首 token 延遲主因 |

---

## 三、Self-Attention 完整矩陣推導

### 3.1 輸入表示

給定序列長度 `n`，每個 token embedding 維度 `d_model`：

```
輸入矩陣 X ∈ ℝ^(n × d_model)

例：n=512, d_model=768 (BERT-base)
X 大小：512 × 768 = 393,216 個浮點數 ≈ 1.5 MB (FP32)
```

### 3.2 投影矩陣

三個可學習的投影矩陣，`dₖ = dᵥ = d_model / h`（h 為 head 數）：

```
Wᴼ ∈ ℝ^(d_model × dₖ)   （Query 投影）
Wᴷ ∈ ℝ^(d_model × dₖ)   （Key 投影）
Wᵛ ∈ ℝ^(d_model × dᵥ)   （Value 投影）

Q = X · Wᴼ    ∈ ℝ^(n × dₖ)
K = X · Wᴷ    ∈ ℝ^(n × dₖ)
V = X · Wᵛ    ∈ ℝ^(n × dᵥ)
```

### 3.3 注意力分數計算（含 ASCII 流程圖）

```
┌─────────────────────────────────────────────────────────┐
│  Self-Attention 矩陣計算流程                             │
│                                                         │
│  Q (n×dₖ)   K (n×dₖ)                                   │
│      │           │                                      │
│      └─────┬─────┘                                      │
│            │ 矩陣乘法 QKᵀ                               │
│            ▼                                            │
│      S = QKᵀ  (n×n)   ← O(n²) 記憶體！                │
│            │                                            │
│            │ ÷ √dₖ  （防止梯度消失）                    │
│            ▼                                            │
│      S̃ = S / √dₖ  (n×n)                                │
│            │                                            │
│            │ softmax(row-wise)                          │
│            ▼                                            │
│      A = softmax(S̃)  (n×n)   ← 注意力權重矩陣          │
│            │                                            │
│            │ 矩陣乘法 A·V                               │
│            ▼                                            │
│      Output = A · V  (n×dᵥ)                            │
└─────────────────────────────────────────────────────────┘
```

### 3.4 為什麼除以 √dₖ？

`dₖ = 64` 時，`QKᵀ` 的點積方差為 `dₖ`（假設 Q, K 各分量 N(0,1)）。

不除以 √dₖ 的後果：softmax 輸入過大 → 梯度趨近 0 → 訓練不穩定。

數值範例：`dₖ=64`，√64=8。若點積平均值為 60，除以 8 後為 7.5，softmax 仍有合理梯度。

### 3.5 計算複雜度分析

| 操作 | 時間複雜度 | 空間複雜度 |
|------|-----------|-----------|
| Q, K, V 投影 | O(n · d²) | O(n · d) |
| QKᵀ 計算 | O(n² · d) | O(n²) |
| softmax | O(n²) | O(n²) |
| A·V | O(n² · d) | O(n · d) |

**n² 的問題**：n=8192（長上下文），d=128，注意力矩陣 = 8192² × 4 bytes = **256 MB**，且這是每個 Head 每個 Layer 的開銷。

---

## 四、Multi-Head Attention：並行多視角

### 4.1 核心思想

單一注意力機制只能學習一種「相似度關係」。Multi-Head Attention 讓模型同時從多個子空間學習不同的依賴模式。

```
┌────────────────────────────────────────────────────────────────┐
│  Multi-Head Attention（h=8 heads 範例）                        │
│                                                                │
│  Input X (n × d_model)                                         │
│       │                                                        │
│  ┌────┴─────────────────────────────────────────────────┐     │
│  │  投影到 h 個子空間（並行）                             │     │
│  │                                                      │     │
│  │  head₁: Q₁K₁ᵀV₁  head₂: Q₂K₂ᵀV₂  ...  headₕ: QₕKₕᵀVₕ│     │
│  │     dₖ=96             dₖ=96                dₖ=96    │     │
│  └────┬─────────────────────────────────────────────────┘     │
│       │                                                        │
│       │  Concat([head₁, head₂, ..., headₕ])                   │
│       │  → (n × h·dᵥ) = (n × d_model)                        │
│       │                                                        │
│       │  × Wᴼ (d_model × d_model)                             │
│       ▼                                                        │
│  Output (n × d_model)                                          │
└────────────────────────────────────────────────────────────────┘

GPT-3: d_model=12288, h=96, dₖ=128
每個 head 獨立學習不同語言關係：
  head₁ → 句法依存（主詞-動詞）
  head₂ → 指代消解（代詞-先行詞）
  head₃ → 語義相似（同義詞）
  ...
```

### 4.2 工程實作重點

在 GPU 上，Multi-Head Attention 通常用 **批次矩陣乘法（BMM）** 實作：

```python
# 概念實作（非生產程式碼）
# Q, K, V shape: (batch, heads, seq_len, head_dim)
scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(head_dim)
# scores shape: (batch, heads, seq_len, seq_len)
attn = F.softmax(scores, dim=-1)
out = torch.matmul(attn, V)
# out shape: (batch, heads, seq_len, head_dim)
```

關鍵：所有 head 的矩陣乘法合併成一個大 kernel call，最大化 GPU 利用率。

---

## 五、位置編碼：Sinusoidal vs RoPE vs ALiBi

### 5.1 為什麼需要位置編碼？

Self-Attention 本身是**置換不變的（permutation invariant）**：把句子中的 token 順序打亂，輸出不變。位置編碼讓模型知道「誰在哪裡」。

### 5.2 三種方案比較

**方案一：Sinusoidal（原始 Transformer）**

```
PE(pos, 2i)   = sin(pos / 10000^(2i/d_model))
PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))
```

優點：不需學習，任意長度都能外推  
缺點：超出訓練長度後表現急劇下降（外推能力差）

**方案二：RoPE（Rotary Position Embedding）**

LLaMA、GPT-NeoX 使用。把位置資訊融入 Query 與 Key 的旋轉變換：

```
Q'ₘ = Rₘ · Qₘ
K'ₙ = Rₙ · Kₙ

Attention 計算：Q'ₘ · K'ₙᵀ = Qₘ · Rₘ₋ₙᵀ · Kₙ
→ 點積只依賴相對距離 (m-n)，天然支援相對位置
```

優點：相對位置感知、外推能力強（配合 YaRN 等頻率縮放可把 Llama 2 從 4K 延伸到 128K，即 32×）  
缺點：每層要對 Q、K 做一次旋轉，有少量額外計算（相對 attention 本身可忽略）

**方案三：ALiBi（Attention with Linear Biases）**

不修改 embedding，而是直接在注意力分數加線性偏置：

```
Score(i,j) = Qᵢ·Kⱼᵀ/√dₖ  -  m·|i-j|

m 為 head-specific 斜率（不可學習，預定義）
```

優點：訓練速度快、長序列外推最好  
缺點：表達能力略弱，不適合相對位置複雜的任務

### 5.3 選擇指南

| 場景 | 建議方案 |
|------|---------|
| 訓練新模型，預算充足 | RoPE |
| 需要極長上下文（>128K） | RoPE + 頻率縮放（YaRN / NTK-aware）；Llama 3.1、Qwen、DeepSeek 等現行長上下文模型都走這條路 |
| 微調現有 BERT/GPT-2 | 維持原 Sinusoidal / learned |
| 從頭訓練且想要零成本外推 | ALiBi（無額外旋轉計算；2023 年後新模型已少採用） |

---

## 六、KV Cache 工程：記憶體 vs 速度取捨

### 6.1 問題來源

自回歸生成（Autoregressive Generation）時，每生成一個新 token，需要與**所有歷史 token** 計算注意力：

```
生成第 t 個 token 時：
  需要 K[1..t-1] 和 V[1..t-1]

若不快取：每步重新計算前 t-1 個 token 的 K, V
→ 總計算量：O(n³)（n 為生成長度）
```

### 6.2 KV Cache 原理

```
┌──────────────────────────────────────────────────────────┐
│  KV Cache 運作流程                                        │
│                                                          │
│  Prefill 階段（處理 prompt）                              │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Input tokens: [t₁, t₂, t₃, t₄, t₅]               │ │
│  │  一次計算所有 K, V → 存入 Cache                      │ │
│  │  Cache: K=[k₁,k₂,k₃,k₄,k₅], V=[v₁,v₂,v₃,v₄,v₅]  │ │
│  └─────────────────────────────────────────────────────┘ │
│                    │                                     │
│                    ▼                                     │
│  Decode 階段（逐 token 生成）                             │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  生成 t₆：                                          │ │
│  │    Q₆ = linear(t₆)                                 │ │
│  │    K₆, V₆ = linear(t₆)  ← 只計算新 token           │ │
│  │    Cache ← append K₆, V₆                           │ │
│  │    Attn(Q₆, K[1..6], V[1..6])  ← 讀 Cache          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  效果：K/V 投影每步只算新 token（O(1)），注意力仍需讀  │
│  整個 Cache（每步 O(t)）；免去每步重算整段前文 O(t²)    │
└──────────────────────────────────────────────────────────┘
```

### 6.3 KV Cache 記憶體計算

```
KV Cache 大小 = 2 × num_layers × num_kv_heads × head_dim
              × seq_len × batch_size × bytes_per_element

以 LLaMA-2 7B (BF16) 為例：
  num_layers = 32
  num_kv_heads = 32  (MHA，無 GQA)
  head_dim = 128
  seq_len = 4096
  batch_size = 1

KV Cache = 2 × 32 × 32 × 128 × 4096 × 2 bytes
         = 2 × 32 × 32 × 128 × 4096 × 2
         ≈ 2.1 GB / request

批次 16 請求：33.6 GB！（A100 80GB 的 42%）
```

### 6.4 PagedAttention（vLLM）

vLLM 借鑒作業系統**虛擬記憶體分頁**的概念：

- KV Cache 不預先分配連續記憶體
- 分成固定大小的 Block（通常 16 tokens/block）
- Block Table 記錄邏輯 block → 實體 block 的映射
- 不同請求可以動態共享 prefix block（prefix caching）

效果：記憶體碎片從 60-80% 降至 < 4%，吞吐量提升 2-4×。

---

## 七、Flash Attention / MQA / GQA 生產優化

### 7.1 Flash Attention：IO-Aware 演算法

**問題根源**：標準注意力計算需要把 n×n 的注意力矩陣從 GPU HBM（高帶寬記憶體）寫入再讀出，這是記憶體帶寬的殺手。

A100 規格：
- HBM 帶寬：2 TB/s
- SRAM（on-chip）帶寬：19 TB/s（快 9.5×）

**Flash Attention 核心思想**：Tiling（分塊計算）

```
┌─────────────────────────────────────────────────────┐
│  Flash Attention Tiling 示意                         │
│                                                     │
│  Q 矩陣分成 Tᵣ 個 block                             │
│  K, V 矩陣分成 Tᶜ 個 block                          │
│                                                     │
│  ┌───────┬───────┬───────┐                         │
│  │ Q₁    │ Q₂    │ Q₃    │  ← 每個 Q block 在 SRAM │
│  └───────┴───────┴───────┘                         │
│       ×                                             │
│  ┌───────┬───────┬───────┐                         │
│  │ K₁V₁  │ K₂V₂  │ K₃V₃  │ ← 輪流載入 K,V block   │
│  └───────┴───────┴───────┘                         │
│                                                     │
│  每個 (Qᵢ, Kⱼ, Vⱼ) tile 在 SRAM 完成計算          │
│  只在最後把 Output 寫回 HBM 一次                     │
│                                                     │
│  HBM 讀寫次數：O(n²/M) 而非 O(n²)                  │
│  M = SRAM 大小（A100 約 20MB）                      │
└─────────────────────────────────────────────────────┘
```

**論文數字**：
- Flash Attention 1：比標準注意力快 2-4×，記憶體使用 O(n) vs O(n²)
- Flash Attention 2：進一步 2× 加速（更好的工作分配，減少 non-matmul FLOP）
- Flash Attention 3（H100）：利用 Tensor Core 非同步執行，再 1.5-2×

在 A100 上，序列長度 2K，Flash Attention 2 吞吐量：約 **180 TFLOPs/s**（理論峰值 312 TFLOPs/s 的 58%）

### 7.2 Multi-Query Attention（MQA）

**PaLM、Falcon** 使用的方案：所有 Query head 共享同一組 K, V。

```
標準 MHA（h=32 heads）：
  Q heads: 32, K heads: 32, V heads: 32
  KV Cache = 100%

MQA（1 組 KV）：
  Q heads: 32, K heads: 1, V heads: 1
  KV Cache 減少：96.9%（32× 壓縮）
  但：模型品質下降約 5-8%（過於激進）
```

### 7.3 Grouped-Query Attention（GQA）

**LLaMA 2/3、Mistral** 使用的折衷方案：

```
┌─────────────────────────────────────────────┐
│  GQA：分組共享 KV（G=8，h=32 範例）          │
│                                             │
│  Q heads:  [Q₁ Q₂ Q₃ Q₄] [Q₅ Q₆ Q₇ Q₈]  ... │
│                  │                  │         │
│            ┌─────┘            ┌─────┘         │
│            ▼                  ▼               │
│  K,V heads: [KV₁]            [KV₂]    ...    │
│             （每組 4 個 Q head 共享 1 組 KV） │
│                                             │
│  KV head 數：32 → 8（↓ 75%）                │
│  品質損失：< 2%（vs MHA 基準）               │
│  KV Cache 節省：75%                         │
└─────────────────────────────────────────────┘
```

同規模模型改用 GQA（8 個 KV heads，如 Llama 3 8B）後，同樣 A100 80GB：
（LLaMA-2 7B 本身是 MHA；DeepSeek-V2/V3 的 MLA 更進一步把 K/V 壓縮成低秩潛在向量再快取，是 GQA 之後的下一步。）

- KV Cache：2.1 GB → 0.53 GB per request
- 可服務批次：16 req → 64 req（同等記憶體下）
- 吞吐量：4× 提升，品質幾乎無損失

---

## 八、為什麼選 X 不選 Y

### 8.1 Flash Attention vs 標準 Attention

```
選擇            選 Flash Attention 的理由             不選標準 Attention 的理由
─────────────────────────────────────────────────────────────────────────────
Flash           IO-aware tiling，避免 HBM 來回寫入     O(n²) 記憶體，n=4096 時 64GB+
Attention       2-4× 速度提升，記憶體 O(n) vs O(n²)   長序列（>2K）直接 OOM
                支援 causal mask，無精度損失            每個 token 都需要讀整個矩陣

Flip condition：序列長度 < 512 且 GPU 記憶體充足時，標準 Attention kernel fusion 可能更快
```

### 8.2 GQA vs MHA vs MQA

```
選擇    優勢                                    劣勢                    適用場景
──────────────────────────────────────────────────────────────────────────────
MHA     最高模型品質，每個 head 獨立             KV Cache 最大，記憶體開銷高  離線批次推理
GQA     品質損失 <2%，KV Cache 省 75%           工程複雜度稍高              生產 API 服務
MQA     KV Cache 省 97%，速度最快               品質略有損失（視任務而定），訓練較不穩定    邊緣部署、延遲極敏感

Flip condition：模型品質是首要指標（如醫療、法律）→ 選 MHA；成本優先 → GQA；極端延遲要求 → MQA
```

### 8.3 BF16 vs FP16 vs INT8 量化

```
選擇    範圍        精度                速度（vs FP32）   適用場景
────────────────────────────────────────────────────────────────────
FP32    ±3.4×10³⁸  最高（尾數 23 bit）  1×               訓練/精度關鍵推理
BF16    ±3.4×10³⁸  範圍同 FP32，尾數 7 bit  2×          生產推理標準選擇
FP16    ±65504     尾數 10 bit，動態範圍小  2×           需要特別 loss scaling
INT8    ±127        有損 ~1-2%          2-4×             高吞吐、成本敏感

Flip condition：下游任務對細微差異敏感（如數值計算） → BF16；延遲預算 <100ms → INT8
```

浮點格式的位元配置、loss scaling 與 FP8 的完整說明見 [Phase 7 Part 2 §四](/posts/ai-eng-from-scratch-phase7-part2-training-variants-zh/)，本表只列推理端的取捨。

---

## 九、系統效應（有無優化的延遲/吞吐數字）

以 LLaMA-2 7B（N ≈ 6.7B），A100 40GB（BF16 312 TFLOPS、FP32 19.5 TFLOPS、HBM 1.55 TB/s），prompt=512 tokens，生成=256 tokens 為基準。兩個量要分開看：**首 token 延遲由 prefill 決定**（計算瓶頸：≈ 2·N·512 ≈ 6.9 TFLOP），**每個 decode 步的延遲由讀一次權重決定**（記憶體頻寬瓶頸：權重大小 ÷ HBM 頻寬），KV Cache 只影響後者。

| 配置 | 首 token 延遲（prefill） | 每 token decode 延遲（batch=1） | 吞吐量 (req/s，單卡批次化後) | KV Cache/req | GPU 記憶體 |
|------|------------------------|-------------------------------|---------------------------|-------------|-----------|
| FP32 + 標準 Attn + KV Cache | ~700 ms | ~17 ms | ~1 | 4.3 GB | 27 GB + KV |
| BF16 + 標準 Attn，無 KV Cache | ~45 ms | ~55 ms（每步重算整段前文） | ~1 | 0 | 14 GB |
| BF16 + 標準 Attn + KV Cache | ~45 ms | ~9 ms | ~5（batch 12） | 2.1 GB | 14 + 25 GB |
| BF16 + Flash Attn + KV Cache | ~40 ms | ~9 ms | ~5（batch 12） | 2.1 GB | 14 + 25 GB |
| BF16 + Flash Attn + GQA + Cache | ~40 ms | ~9 ms | ~17（batch 48） | 0.53 GB | 14 + 25 GB |
| INT8 + Flash Attn + GQA + vLLM | ~40 ms | ~5 ms | ~35（batch 64） | 0.53 GB | 7 + 33 GB |

*示意估算，非實測數據。算法：首 token = 6.9 TFLOP ÷（峰值算力 × 50% MFU）→ FP32 0.70 s、BF16 44 ms；decode 每 token = 權重大小 ÷ 1.55 TB/s → FP32 27 GB 17 ms、BF16 13.4 GB 8.6 ms、INT8 6.7 GB 4.3 ms；無 KV Cache 時每步重算 512+i 個 token，256 步合計 ≈ 14 s，平均 55 ms/token；吞吐 ≈ batch ÷（首 token + 256 × 每步延遲），batch 由剩餘記憶體 ÷ 每請求 KV Cache 決定。*

### 關鍵觀察

1. **KV Cache 改的是 decode，不是首 token**：每個 decode 步從「重算整段前文」（~55 ms）變成「讀一次權重」（~9 ms），256 個 token 從 ~14 s 降到 ~2.2 s；首 token 延遲完全不變
2. **BF16 與 INT8 才是首 token 與每步延遲的槓桿**：prefill 算力 16×（19.5 → 312 TFLOPS）、權重讀取量減半，兩者分別壓低首 token 與每步延遲
3. **Flash Attention 在 512-token prompt 幾乎看不出來**：attention 的 FLOPs 只佔 prefill 的 ~2%，它的價值在長 prompt（> 2K）的 n² 記憶體與 HBM 往返
4. **GQA 與 PagedAttention 釋放的是批次**：每請求 KV Cache 2.1 GB → 0.53 GB，同樣記憶體能塞下 4× 的並發，吞吐隨之 ~3–7×

### 對照開頭設定的部署目標（P99 < 500ms，> 200 req/s，< 40GB）

最終配置：INT8 + Flash Attention 2 + GQA + vLLM PagedAttention
- 首 token：~40 ms，加上排隊後 P99 仍遠低於 500 ms ✓
- GPU 記憶體：7 GB 權重 + 33 GB KV Cache 預算 ✓（< 40 GB）
- 吞吐量：單卡 ~35 req/s（每請求生成 256 tokens，約 9K tokens/s）；> 200 req/s 需要約 6 張卡，或把生成長度壓到 64 tokens 以內——**吞吐目標是靠橫向擴展達成的，不是靠單卡優化**

---

## 十、系列導航

← [Phase 6 Part 2：語音合成與音訊模型 — 讓機器開口說話](/posts/ai-eng-from-scratch-phase6-part2-tts-audio-models-zh/)

→ [Phase 7 Part 2：Transformer 訓練策略與架構變體](/posts/ai-eng-from-scratch-phase7-part2-training-variants-zh/)

---

*本文是「AI 工程從零開始」系列的 Phase 7 Part 1。*
*系列目標：讓軟體工程師在 6 個月內具備設計與部署生產級 AI 系統的能力。*
