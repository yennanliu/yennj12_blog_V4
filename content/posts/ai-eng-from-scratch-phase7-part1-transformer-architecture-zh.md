---
title: "AI 工程從零開始｜Phase 7 Part 1：Transformer 架構深度解析 — 改變一切的注意力"
date: 2026-06-21T15:30:00+08:00
draft: false
weight: 14
description: "從工程師視角完整解析 Transformer：Multi-Head Attention 矩陣計算、位置編碼、KV Cache、Flash Attention 與 MQA/GQA 生產優化"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Transformer", "Attention", "KV Cache", "Flash Attention", "Architecture", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人覺得 Transformer 就是「注意力機制加上前饋網路」，說完就結束了。*
> *真正的工程師知道：矩陣分塊如何影響 GPU 記憶體帶寬，KV Cache 如何讓首 token 延遲從 8s 降到 400ms，*
> *為什麼 GQA 能在保持 95% 品質的前提下省掉 75% 的快取記憶體。*
> *架構不是魔法——它是一系列在硬體限制下做出的工程取捨。*

---

**面試情境**：「你負責將一個 7B 參數的 LLM 部署到生產環境，P99 首 token 延遲必須 < 500ms，批次吞吐量 > 200 req/s，GPU 記憶體預算 40GB。請說明你會在 Transformer 架構層面做哪些優化決策，以及你如何取捨精度與速度。」

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

## 二、三個演進階段（POC / MVP / Scale）

### ╔══ Phase 1：POC — 理解架構，跑通推理（< 1K req/day）╗

目標：把預訓練模型跑起來，驗證輸出品質。

```
┌─────────────────────────────────────────────┐
│  Phase 1 架構：純 CPU / 單 GPU              │
│                                             │
│  User Request                               │
│       │                                     │
│       ▼                                     │
│  ┌─────────────┐                            │
│  │  HuggingFace│  直接 from_pretrained()    │
│  │  Transformers│  FP32 或 FP16            │
│  └──────┬──────┘                            │
│         │                                   │
│         ▼                                   │
│  ┌─────────────┐                            │
│  │  Greedy /   │  逐 token 生成             │
│  │  Sampling   │  無 KV Cache 重用          │
│  └─────────────┘                            │
└─────────────────────────────────────────────┘

新增組件：HuggingFace pipeline
問題：首 token 延遲 6–10s，無法生產用
```

成本：開發者筆電或單張 A100（$2–3/hr）

### ╔══ Phase 2：MVP — 生產就緒，KV Cache 啟用（10K–200K req/day）╗

目標：P99 < 1s，支援並發請求。

```
┌──────────────────────────────────────────────────────┐
│  Phase 2 架構：vLLM + KV Cache                       │
│                                                      │
│  Load Balancer (nginx)                               │
│       │                                              │
│       ▼                                              │
│  ┌──────────────────────────────────────┐            │
│  │  vLLM Server (OpenAI-compatible API) │            │
│  │                                      │            │
│  │  ┌────────────┐   ┌───────────────┐  │            │
│  │  │ Continuous │   │  PagedAttention│  │            │
│  │  │ Batching   │──▶│  KV Cache     │  │            │
│  │  └────────────┘   └───────────────┘  │            │
│  │                                      │            │
│  │  Model: 7B BF16 on A100 80GB         │            │
│  └──────────────────────────────────────┘            │
│                                                      │
│  新增：KV Cache、Continuous Batching                  │
│  首 token 延遲：6s → 400ms（↓93%）                   │
│  吞吐量：5 req/s → 80 req/s（↑16x）                  │
└──────────────────────────────────────────────────────┘
```

### ╔══ Phase 3：Scale — 企業級，Flash Attention + GQA（200K–1M+ req/day）╗

目標：P99 < 500ms，200+ req/s，40GB GPU 限制。

```
┌────────────────────────────────────────────────────────────┐
│  Phase 3 架構：Flash Attention + GQA + 量化                 │
│                                                            │
│  ┌─────────────┐    ┌──────────────────────────────────┐  │
│  │ API Gateway │───▶│  vLLM Cluster (4× A100 40GB)     │  │
│  └─────────────┘    │                                  │  │
│                     │  ┌─────────────────────────────┐ │  │
│                     │  │ Flash Attention 2            │ │  │
│                     │  │ (IO-aware, tiling)           │ │  │
│                     │  ├─────────────────────────────┤ │  │
│                     │  │ GQA (8 KV heads / 32 Q heads)│ │  │
│                     │  ├─────────────────────────────┤ │  │
│                     │  │ INT8 Weight Quantization     │ │  │
│                     │  ├─────────────────────────────┤ │  │
│                     │  │ Paged KV Cache              │ │  │
│                     │  └─────────────────────────────┘ │  │
│                     └──────────────────────────────────┘  │
│                                                            │
│  P99 首 token：400ms → 120ms（↓70%）                       │
│  吞吐量：80 req/s → 250 req/s（↑3.1x）                     │
│  KV Cache 記憶體：32GB → 8GB（↓75%）                       │
└────────────────────────────────────────────────────────────┘
```

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

優點：相對位置感知、外推能力強（配合 YaRN 可延伸 4-8×）  
缺點：計算額外旋轉矩陣，約增加 5-8% 計算開銷

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
| 需要極長上下文（>128K） | ALiBi 或 RoPE + YaRN |
| 微調現有 BERT/GPT-2 | 維持原 Sinusoidal |
| 推理速度優先 | ALiBi（無額外旋轉計算） |

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
│  效果：Decode 計算量 O(n) → O(1) per step               │
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

**實測數字**：
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

LLaMA-2 7B 使用 GQA 後，同樣 A100 80GB：
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
MQA     KV Cache 省 97%，速度最快               品質損失 5-8%，訓練不穩定    邊緣部署、延遲極敏感

Flip condition：模型品質是首要指標（如醫療、法律）→ 選 MHA；成本優先 → GQA；極端延遲要求 → MQA
```

### 8.3 RoPE vs ALiBi vs Sinusoidal

```
選擇          優勢                            劣勢                    適用場景
────────────────────────────────────────────────────────────────────────────
RoPE          相對位置、外推強（+YaRN 4-8×）  額外旋轉計算 +5-8%       新訓練模型首選
ALiBi         無需修改 embedding，外推最佳    表達能力略弱              超長文（>64K）
Sinusoidal    無參數，通用                    超出訓練長度急劇下降      BERT 類微調任務

Flip condition：固定長度任務且不需外推 → Sinusoidal 夠用；> 128K 上下文 → ALiBi
```

### 8.4 KV Cache vs 重新計算

```
選擇          優勢                              劣勢                   適用場景
──────────────────────────────────────────────────────────────────────────
KV Cache      Decode 步驟 O(1) per step         大量記憶體，長序列費用高  正常 API 服務
重新計算      記憶體接近零額外開銷               每步重算 O(n)，速度慢     記憶體極度受限環境

Flip condition：seq_len < 64 且批次 >> 1 時，重新計算有時更高效（cache miss > compute cost）
```

### 8.5 vLLM PagedAttention vs 靜態 KV Cache

```
選擇               優勢                              劣勢
──────────────────────────────────────────────────────────────────────────────
Paged (vLLM)       記憶體碎片 <4%，支援 prefix cache  額外 Block Table 管理複雜度
靜態 KV Cache      實作簡單，延遲更低（無分頁開銷）   碎片率 60-80%，無法 prefix share

Flip condition：單一固定長度請求，無並發 → 靜態 Cache 更快；並發 > 4 → PagedAttention 必選
```

### 8.6 BF16 vs FP16 vs INT8 量化

```
選擇    範圍        精度         速度（vs FP32）   適用場景
─────────────────────────────────────────────────────────────
FP32    ±3.4×10³⁸  最高         1×               訓練/精度關鍵推理
BF16    ±3.4×10³⁸  與 FP32 等效  2×              生產推理標準選擇
FP16    ±65504     動態範圍小    2×               需要特別 loss scaling
INT8    ±127        有損 ~1-2%   2-4×             高吞吐、成本敏感

Flip condition：下游任務對細微差異敏感（如數值計算） → BF16；延遲預算 <100ms → INT8
```

---

## 九、系統效應（有無優化的延遲/吞吐數字）

以 LLaMA-2 7B，A100 40GB，prompt=512 tokens，生成=256 tokens 為基準：

| 配置 | 首 token 延遲 (P50) | 首 token 延遲 (P99) | 吞吐量 (req/s) | KV Cache/req | GPU 記憶體使用率 |
|------|--------------------|--------------------|---------------|-------------|----------------|
| FP32 + 標準 Attn，無 Cache | 8,200 ms | 12,000 ms | 0.8 | 0 | 28 GB (模型) |
| BF16 + 標準 Attn，無 Cache | 4,100 ms | 6,500 ms | 1.6 | 0 | 14 GB |
| BF16 + 標準 Attn + KV Cache | 380 ms | 650 ms | 12 | 2.1 GB | 14 + 33.6 GB |
| BF16 + Flash Attn + KV Cache | 160 ms | 280 ms | 35 | 2.1 GB | 14 + 33.6 GB |
| BF16 + Flash Attn + GQA + Cache | 155 ms | 270 ms | 140 | 0.53 GB | 14 + 8.5 GB |
| INT8 + Flash Attn + GQA + vLLM | 120 ms | 210 ms | 250 | 0.53 GB | 7 + 8.5 GB |

### 關鍵觀察

1. **KV Cache 是最大單一增益**：延遲從 4100ms 降至 380ms（↓91%），代價是記憶體
2. **Flash Attention 是吞吐乘數**：在記憶體不變的情況下，吞吐 12 → 35 req/s（↑2.9×）
3. **GQA 釋放記憶體**：KV Cache 從 33.6 GB → 8.5 GB，讓更大批次成為可能，吞吐 35 → 140 req/s（↑4×）
4. **INT8 量化**：模型記憶體減半，延遲再降 20%，品質損失 < 1%

### 達到題目要求（P99 < 500ms，> 200 req/s，< 40GB）

最終配置：INT8 + Flash Attention 2 + GQA + vLLM PagedAttention
- P99 首 token：210 ms ✓（< 500ms）
- 吞吐量：250 req/s ✓（> 200 req/s）
- GPU 記憶體：7 + 8.5 = 15.5 GB ✓（< 40 GB，還有空間給更大批次）

---

## 十、面試答題要點

**面試官問**：「7B 模型部署，P99 < 500ms，200+ req/s，40GB GPU 限制，你怎麼做？」

> *「我會分三個層次解決這個問題。首先，啟用 KV Cache 是最大的單一優化——它把首 token 延遲從 4100ms 降至 380ms（↓91%），代價是記憶體；配合 vLLM 的 PagedAttention，記憶體碎片從 60% 降至 4%。其次，將 MHA 換成 GQA（8 個 KV head），KV Cache 從 2.1 GB/req 降至 0.53 GB/req（↓75%），在相同 40GB 預算下批次大小從 16 擴到 64，吞吐從 35 提升到 140 req/s。第三，換用 Flash Attention 2 進行 IO-aware tiling，避免 O(n²) 的 HBM 讀寫，再加 INT8 量化把模型從 14GB 壓到 7GB，最終 P99 達 210ms、吞吐 250 req/s、記憶體 15.5GB——三個指標都符合。如果未來需要進一步擴展，下一步是 Speculative Decoding 或 Tensor Parallelism 多卡部署。」*

**評分要素**：
- 每個優化有量化數字（不只說「更快」）
- 清楚說明取捨（KV Cache 省時間但費記憶體，GQA 解決記憶體但需重新訓練或選對模型）
- 說出三個演進步驟而非一次到位
- 最後提出「下一步」顯示工程判斷力

---

## 十一、系列導航

← [Phase 6 Part 2：模型微調與 LoRA 工程實踐](/posts/ai-eng-from-scratch-phase6-part2-lora-finetuning-zh/)

→ [Phase 7 Part 2：LLM 推理引擎與部署架構](/posts/ai-eng-from-scratch-phase7-part2-inference-deployment-zh/)

---

*本文是「AI 工程從零開始」系列的 Phase 7 Part 1。*
*系列目標：讓軟體工程師在 6 個月內具備設計與部署生產級 AI 系統的能力。*
