---
title: "AI 工程從零開始｜Phase 7 Part 2：Transformer 訓練策略與架構變體"
date: 2026-06-21T16:00:00+08:00
draft: false
weight: 15
description: "深入解析 Transformer 訓練：學習率 Warmup/Schedule、梯度裁剪、混合精度訓練、Encoder-only/Decoder-only/Encoder-Decoder 架構選型，以及 MoE 混合專家系統"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Transformer", "Training", "MoE", "BERT", "GPT", "T5", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人認為：Transformer 就是 attention + FFN，照抄論文程式碼就能訓練起來。*
> *真實情況是：沒有 LR warmup 模型在第 100 步就 loss 爆炸；沒有梯度裁剪 NaN 讓你懷疑人生。*
> *進階工程師知道：訓練策略與架構選型決定了 90% 的成敗，程式碼只佔 10%。*
> *本文要解決的是：為什麼這些技巧存在、何時用哪個、以及三個演進階段的工程落地路徑。*

---

## 面試情境

> 面試官問：「你要為一個電商平台設計一套 NLP 系統，需要同時支援商品描述生成（生成任務）、評論情感分析（分類任務）、以及跨語言商品搜尋（語義匹配）。你會選擇哪種 Transformer 架構？訓練時的學習率策略和精度選擇是什麼？如果預算只有 $50K，怎麼做？」

---

## 一、核心問題：Transformer 訓練為什麼這麼難

Transformer 訓練困難的根源不在於架構複雜，而在於**多個不穩定因素的耦合**：

**問題 1：參數初始化 vs 梯度流**

Transformer 在初始化時，attention 層的 softmax 容易輸出接近均勻分佈（對梯度無貢獻）或接近 one-hot（梯度消失）。用過大的學習率，前幾步梯度就會爆炸；用過小的學習率，前幾千步幾乎不學習。

**問題 2：不同層的梯度尺度差異**

淺層（embedding 附近）和深層（最後幾個 block）的梯度尺度可以相差 100 倍以上。固定學習率對一部分層太大、對另一部分太小。

**問題 3：浮點精度的精度懸崖**

FP16 的最大值約 65504，一旦梯度超過就 overflow 變 NaN，整批訓練廢掉。BF16 範圍更大但精度更低，小 loss 差異可能被截斷。

**問題 4：任務與架構的阻抗失配**

用 Decoder-only 做分類：浪費計算，需要特殊 pooling；用 Encoder-only 做生成：無法自回歸，強行做需要 mask 技巧。錯誤的架構選型讓精度天花板提前到來。

**核心量化**：

| 問題 | 未處理時的後果 | 處理後的改善 |
|------|-------------|-------------|
| 無 LR Warmup | 約 40% 訓練在 step 200 前崩潰 | 崩潰率降至 < 2% |
| 無梯度裁剪 | 每 ~500 步出現一次 NaN spike | NaN spike 消失 |
| 純 FP16 無 loss scaling | 每 10 步中約 1 步 overflow | overflow < 0.1% |
| 架構選型錯誤 | 精度損失 3–8 個百分點 | 回復完整精度空間 |

---

## 二、三個演進階段（POC/MVP/Scale）

### ╔══ Phase 1：POC（< 1B token，單機實驗）══╗

**目標**：快速驗證任務可行性，不追求最優效能。

```
┌──────────────────────────────────────────────────────────┐
│  POC 訓練堆疊（單機 4×A100）                              │
│                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  資料載入    │───▶│  Model      │───▶│  Optimizer  │  │
│  │  DataLoader │    │  (HF/PyTorch│    │  AdamW      │  │
│  │  num_workers│    │   小 config)│    │  固定 LR    │  │
│  └─────────────┘    └─────────────┘    └─────────────┘  │
│                              │                           │
│                              ▼                           │
│                    ┌─────────────────┐                   │
│                    │  WandB / TBoard │                   │
│                    │  loss / grad_norm│                  │
│                    └─────────────────┘                   │
│                                                          │
│  LR: cosine decay 無 warmup（接受偶發崩潰）               │
│  精度: FP32（穩定，速度慢 ~2x）                           │
│  Batch: 32–64，gradient accumulation 關閉                │
└──────────────────────────────────────────────────────────┘
```

**成本估算**：4×A100 40GB 單次實驗約 $20–50（AWS p4d.xlarge 按需）。  
**可接受的妥協**：偶發 loss spike、訓練速度未最佳化、無分散式。  
**遺留問題**：無法處理 > 1B token 資料集；無法訓練 > 3B 參數模型。

---

### ╔══ Phase 2：MVP（1B–100B token，多機訓練）══╗

**目標**：生產可用、團隊可操作、無持續救火。

```
┌──────────────────────────────────────────────────────────────┐
│  MVP 訓練堆疊（4–16 × 8×A100 節點）                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  資料管線                                             │   │
│  │  Streaming Dataset ──▶ Tokenizer ──▶ PackedSequence  │   │
│  └───────────────────────────┬──────────────────────────┘   │
│                              │                               │
│  ┌───────────────────────────▼──────────────────────────┐   │
│  │  分散式訓練（DeepSpeed ZeRO-2 / FSDP）               │   │
│  │                                                      │   │
│  │  Node 0        Node 1        Node 2        Node 3   │   │
│  │  ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐ │   │
│  │  │8×A100  │   │8×A100  │   │8×A100  │   │8×A100  │ │   │
│  │  │DP+TP   │   │DP+TP   │   │DP+TP   │   │DP+TP   │ │   │
│  │  └────────┘   └────────┘   └────────┘   └────────┘ │   │
│  │         NVLink（節點內） / InfiniBand（節點間）       │   │
│  └───────────────────────────┬──────────────────────────┘   │
│                              │                               │
│  ┌───────────────────────────▼──────────────────────────┐   │
│  │  訓練策略                                             │   │
│  │  • LR Warmup 2000 steps + cosine decay               │   │
│  │  • Gradient clip norm = 1.0                          │   │
│  │  • BF16 混合精度（A100/H100 原生支援）                │   │
│  │  • Checkpoint 每 1000 steps                          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**成本估算**：32×A100 訓練 7B 模型 100B token，約 $40K–$60K。  
**新增組件**：ZeRO-2 分片、LR schedule、grad clip、BF16。  
**遺留問題**：單次失敗成本高；超過 70B 參數需要 Pipeline Parallelism。

---

### ╔══ Phase 3：Scale（> 100B token，超大規模）══╗

**目標**：企業級，自動化恢復，成本最佳化，支援 MoE/長序列。

```
┌────────────────────────────────────────────────────────────────┐
│  Scale 訓練堆疊（數百到數千 GPU）                               │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  三維並行（3D Parallelism）                              │  │
│  │                                                         │  │
│  │  Data Parallel (DP)                                     │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │  Pipeline 0  │  │  Pipeline 1  │  │  Pipeline 2  │  │  │
│  │  │ ┌──┐ ┌──┐   │  │ ┌──┐ ┌──┐   │  │ ┌──┐ ┌──┐   │  │  │
│  │  │ │L1│▶│L2│PP │  │ │L1│▶│L2│PP │  │ │L1│▶│L2│PP │  │  │
│  │  │ └──┘ └──┘   │  │ └──┘ └──┘   │  │ └──┘ └──┘   │  │  │
│  │  │ Tensor Parallel│  │ Tensor Parallel│  │ Tensor Parallel│  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  進階策略                                               │  │
│  │  • ZeRO-3 + Offload（優化器狀態到 CPU/NVMe）            │  │
│  │  • FP8 量化訓練（H100 Transformer Engine）              │  │
│  │  • 自動 checkpoint 恢復（Fault Tolerance）              │  │
│  │  • 動態 LR scaling（根據 batch size 線性縮放）          │  │
│  │  • MoE routing（Expert Parallelism 獨立維度）          │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**成本估算**：1000×H100 訓練 70B 模型 1T token，約 $2M–$5M。  
**關鍵新增**：三維並行、FP8 訓練、自動故障恢復、MoE Expert Parallelism。

---

## 三、訓練穩定性：LR Warmup / Gradient Clipping / Weight Decay

### 3.1 學習率 Warmup

**為什麼需要 Warmup？**

模型初始化後，attention 權重的梯度方差極大。如果一開始就用目標學習率（如 3e-4），第一個 batch 的梯度更新幅度可能讓 attention 矩陣完全混亂，後續幾乎無法恢復。

```
LR 曲線示意（Warmup 2000 steps + Cosine Decay）：

  LR
  │
  3e-4 ──────────────────╮
  │              ╱        ╲
  │           ╱            ╲
  │        ╱                ╲────────────── 1e-5（min LR）
  │     ╱
  │  ╱ Warmup
  0 ────────────────────────────────────── steps
     0    2K    10K    50K   100K
```

**Warmup 步數的選擇**：

| 模型規模 | 建議 Warmup Steps | 理由 |
|---------|-----------------|------|
| < 125M 參數 | 500–1000 | 參數少，初始化方差小 |
| 125M–1B | 1000–2000 | 標準 BERT/GPT-2 設定 |
| 1B–13B | 2000–4000 | 更深層需要更多時間穩定 |
| > 13B | 4000–8000 | 避免前期破壞深層表示 |

**Cosine Decay vs Linear Decay vs Constant**：

- **Cosine Decay**：末期 LR 平滑趨近 min_lr，避免震盪，最常用。
- **Linear Decay**：簡單，但末期下降過急，最後幾千步學習率可能過低。
- **Constant**：適合 RL fine-tuning，不適合 pre-training。
- **WSD（Warmup-Stable-Decay）**：Mistral/Llama 3 採用，穩定期 LR 不變，便於 checkpoint 繼續訓練。

### 3.2 梯度裁剪（Gradient Clipping）

**機制**：計算所有參數梯度的 L2 norm，若超過閾值 `max_norm`，等比例縮放：

```
grad_norm = sqrt(sum(g^2 for g in gradients))
if grad_norm > max_norm:
    scale = max_norm / grad_norm
    gradients = [g * scale for g in gradients]
```

**關鍵數字**：
- `max_norm = 1.0`：最通用設定，適合 AdamW + LR 1e-4 ~ 5e-4。
- `max_norm = 0.5`：更保守，用於 unstable 早期訓練或超大模型。
- `max_norm = 5.0`：RNN 時代遺留，Transformer 幾乎不用。

**診斷指標**：監控 `grad_norm`。若 > 10 的頻率 > 5%，說明 LR 過高或模型設計有問題。正常訓練中，95% 的步驟 `grad_norm` 應在 0.2–2.0。

### 3.3 Weight Decay

AdamW 將 weight decay 從梯度更新中解耦，直接作用於參數：

```
θ_t = θ_{t-1} - lr * (m_t / (sqrt(v_t) + ε)) - lr * λ * θ_{t-1}
```

- **λ = 0.01–0.1**：Transformer 標準範圍。
- **不對 bias 和 LayerNorm 參數做 decay**：這些參數的 scale 影響模型容量，decay 會傷害表現。
- **效果**：相當於 L2 正則化，但在 Adam 下語義不同——Adam 本身對梯度做了縮放，普通 L2 的實際效果被 Adam 的 adaptive step 稀釋，AdamW 修正了這個問題。

---

## 四、混合精度訓練：BF16 / FP16 / FP8 的取捨

```
浮點格式對比：

格式    符號  指數  尾數  最大值      最小正規數   適用場景
──────────────────────────────────────────────────────────────
FP32    1     8     23    ~3.4e38     ~1.2e-38    基準，POC
FP16    1     5     10    65504       ~6.1e-5     老 GPU（V100）
BF16    1     8     7     ~3.4e38     ~1.2e-38    A100/H100 首選
FP8 E4M3 1    4     3     448         ~1.95e-3    H100 前向計算
FP8 E5M2 1    5     2     57344       ~1.5e-5     H100 梯度計算
```

### 4.1 FP16 的問題與 Loss Scaling

FP16 最大值僅 65504，反向傳播的梯度（特別是 attention 層）容易超出範圍。

**解法：Dynamic Loss Scaling**
1. 初始 scale factor = 65536
2. 若連續 2000 步無 overflow：scale × 2
3. 若出現 overflow：scale / 2，跳過本步更新
4. 優化器保持 FP32 副本（master weights）

**開銷**：記憶體增加約 50%（FP16 前向 + FP32 master weights + FP16 梯度）。

### 4.2 BF16 的優勢

BF16 與 FP32 有相同的指數範圍（8 bit exponent），幾乎不會 overflow，不需要 loss scaling。精度（7 bit mantissa）比 FP16 低，但實踐中對 LLM 訓練幾乎無影響。

**A100 BF16 vs FP32 吞吐量**：BF16 理論峰值 312 TFLOPS，FP32 僅 19.5 TFLOPS，約 16× 差距（實際有記憶體頻寬瓶頸，通常 3–6×）。

### 4.3 FP8 訓練（H100 Only）

H100 的 Transformer Engine 支援 FP8 矩陣乘：

- **前向計算**：E4M3（較高精度，保留特徵細節）
- **梯度計算**：E5M2（較大範圍，容納梯度 spike）
- **優化器狀態**：BF16 或 FP32

**實測收益**：相比 BF16，FP8 訓練吞吐量提升約 30–40%，但需要 per-tensor 動態 scale 管理，工程複雜度上升。精度損失通常 < 0.1%（perplexity 差異）。

**選型建議**：

| 硬體 | 推薦精度 | 理由 |
|------|---------|------|
| V100 / T4 | FP16 + loss scaling | 無 BF16 硬體支援 |
| A100 / A6000 | BF16 | 無 overflow 風險，硬體原生支援 |
| H100 / H200 | BF16 前向 + FP8 矩陣乘 | 最大吞吐量 |
| AMD MI300X | BF16 | ROCm FP8 支援尚未成熟（2025） |

---

## 五、架構三分支：Encoder-only vs Decoder-only vs Encoder-Decoder

```
三種架構的 Attention Mask 示意：

Encoder-only（雙向）:        Decoder-only（因果）:       Encoder-Decoder:
                              
Token:  A  B  C              Token:  A  B  C              Encoder（雙向）→ Cross-Attention → Decoder（因果）
                                                          
A →  [✓][✓][✓]              A →  [✓][✗][✗]             
B →  [✓][✓][✓]              B →  [✓][✓][✗]             ┌────────────┐     ┌─────────────┐
C →  [✓][✓][✓]              C →  [✓][✓][✓]             │  Encoder   │────▶│   Decoder   │
                                                         │ (src 雙向) │     │(tgt 因果+   │
所有 token 互相可見           只看自身和之前的 token       └────────────┘     │ cross-attn) │
                                                                            └─────────────┘
代表模型：BERT, RoBERTa       代表模型：GPT, LLaMA         代表模型：T5, BART
典型任務：分類, NER, 問答      典型任務：生成, chat, code    典型任務：翻譯, 摘要, seq2seq
```

### 5.1 Encoder-only：BERT 家族

**核心優勢**：雙向 context，每個 token 都能看到完整輸入，表示品質最高。

**典型任務**：
- 文本分類（sentiment, intent detection）：BERT 在 SST-2 達到 94.9% 準確率
- NER（命名實體識別）：充分利用前後文脈絡
- 語義相似度 / 向量搜尋（Sentence-BERT）
- 抽取式問答（SQuAD）：抽取 span 而非生成

**缺點**：無法生成；MLM 預訓練任務與下游任務有 gap（預訓練看 [MASK]，fine-tune 看真實 token）。

**參數規模**：BERT-base 110M，BERT-large 340M，DeBERTa-v3-large 304M。

### 5.2 Decoder-only：GPT 家族

**核心優勢**：因果語言模型，自然支援生成；few-shot / zero-shot in-context learning；統一的 pre-training 與 inference 範式。

**典型任務**：
- 文本生成（story, code, dialogue）
- In-context learning（prompt engineering）
- Chain-of-thought reasoning
- 任何可以轉為「補全」的任務

**缺點**：分類任務需要特殊設計（cls token 或最後一個 token pooling）；對雙向 context 任務（NER、span extraction）表現不如 Encoder-only。

**參數規模**：GPT-2 117M–1.5B，LLaMA-3 8B–70B，Mistral 7B。

### 5.3 Encoder-Decoder：T5 家族

**核心優勢**：兩端分工明確——Encoder 理解輸入，Decoder 生成輸出。對「輸入完整、輸出可變長」的任務最自然。

**典型任務**：
- 機器翻譯（輸入英文，輸出中文）
- 摘要生成（長文 → 短摘）
- Data-to-text（結構化資料 → 自然語言）
- 程式碼修正（有輸入輸出對稱性的任務）

**缺點**：參數效率低於 Decoder-only（相同參數，Encoder-Decoder 對生成的品質不如同規模 Decoder-only）；推論時需要 KV cache 兩套（Encoder 的 key/value 需存入 cross-attention）。

### 5.4 架構選型決策樹

```
任務需要生成可變長輸出？
    │
    ├─ No ──▶  只需要理解/分類 ──▶  Encoder-only（BERT/RoBERTa）
    │
    └─ Yes
         │
         ├─ 輸入和輸出語言/格式差異大（翻譯/摘要）？
         │       └─ Yes ──▶  Encoder-Decoder（T5/BART）
         │
         └─ 需要 few-shot / chat / 長上下文理解？
                 └─ Yes ──▶  Decoder-only（GPT/LLaMA）
```

---

## 六、混合專家 MoE：稀疏激活的工程挑戰

### 6.1 MoE 基本原理

標準 FFN 層：每個 token 通過同一組參數（全量激活）。

MoE FFN 層：每個 token 只激活 K 個 Expert（Top-K routing），其餘 Expert 的參數在本步驟不更新。

```
MoE 層架構：

                     ┌─────────────┐
  Token Embedding ──▶│  Router     │──▶ Expert 選擇（Top-2）
                     │ (Linear +   │
                     │  Softmax)   │
                     └─────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼───┐   ┌────▼───┐   ┌────▼───┐   ... (N Experts)
         │Expert 1│   │Expert 2│   │Expert 3│
         │ FFN    │   │ FFN    │   │ FFN    │
         └────┬───┘   └────┬───┘   └────┬───┘
              │            │
              └────────────┘
                     │
              Weighted Sum ──▶ 輸出
```

**關鍵數字（Mixtral 8×7B）**：
- 8 個 Expert，每次激活 Top-2
- 參數量：46.7B（約等於 2 個 7B 模型）
- 推論時計算量：等同 12.9B dense 模型（只激活 2/8）
- 品質：接近 70B dense 模型

### 6.2 Load Balancing：最核心的工程問題

若 router 自由選擇，90% 的 token 會集中在 2–3 個 Expert，其他 Expert 幾乎不訓練（**Expert Collapse**）。

**解法：Auxiliary Loss**

```
L_aux = α × Σ_i (f_i × P_i)

f_i = 每個 Expert 處理的 token 比例（實際分配）
P_i = router 對 Expert i 的平均 softmax 機率
α = 0.01（常用值，過大會傷害主任務 loss）
```

若所有 Expert 負載均等，L_aux 最小化。若某個 Expert 過載，f_i × P_i 乘積增大，促使 router 重新分配。

**Expert Parallelism（EP）**：

規模擴大後，將不同 Expert 放在不同 GPU 上。Token 需要跨 GPU 傳送到對應 Expert（All-to-All communication），這是 MoE 的主要通訊瓶頸。

**容量因子（Capacity Factor）**：每個 Expert 在一個 batch 內最多處理 `capacity = tokens × K / N × capacity_factor` 個 token。超過容量的 token 被丟棄（token dropping）。`capacity_factor = 1.0`：無緩衝，token drop rate 高；`capacity_factor = 1.25`：推薦值，允許 25% 超額。

### 6.3 MoE 推論的工程挑戰

| 挑戰 | 問題描述 | 解法 |
|------|---------|------|
| 記憶體 | 46.7B 參數需 93GB+ 記憶體 | 多 GPU 分片；Expert Offloading |
| 延遲 | All-to-All 通訊增加 20–40% 延遲 | 節點內 NVLink（< 1μs）；Expert 本地化 |
| KV Cache | 每個 Expert 有獨立的 attention（部分架構） | 共用 attention，只分 FFN |
| Token 不均 | 推論時某些 Expert 過載 | 動態路由 + Buffer token |

---

## 七、長序列 Transformer：Sliding Window / Longformer / Mamba

標準 Transformer 的 attention 計算複雜度為 O(n²)，序列長度超過 4K 後記憶體開銷呈爆炸性增長。

**問題規模**：
- 4K context，7B 模型：KV cache 約 4GB（BF16）
- 32K context：約 32GB，一張 A100 只夠放 KV cache
- 128K context：約 128GB，需要多 GPU 分片

### 7.1 Sliding Window Attention（Mistral / Phi）

每個 token 只與前後 W 個 token 做 attention（窗口大小 W = 4096）。複雜度從 O(n²) 降到 O(n×W)。

**限制**：遠距依賴資訊需要多層傳遞，等效感受野 = W × layers。16 層 × 4096 窗口 = 65536 token 的等效感受野。

### 7.2 Flash Attention（io-aware 計算）

Flash Attention 不降低 attention 的計算複雜度，但大幅降低 HBM 讀寫次數：

- 標準 attention：需要將 Q×K^T 矩陣（n² 大小）存入 HBM
- Flash Attention：Tiling 技術，在 SRAM 中分塊計算，HBM IO 降低 5–10×
- 實際速度提升：2–4×（記憶體頻寬瓶頸下更明顯）
- Flash Attention 2 / 3 進一步最佳化 warp-level 平行度

### 7.3 Mamba（SSM 架構）

Mamba 用 Selective State Space Model 取代 attention：

- **複雜度**：O(n × d_state)，線性，vs Transformer O(n²)
- **訓練**：可並行掃描（類似 FFT），不比 Transformer 慢
- **推論**：每步只需要固定大小的狀態向量，記憶體恆定
- **缺點**：長距離準確 recall 能力弱於 attention；目前在複雜推理任務上落後 Transformer

**實際應用選型**：
- 需要精確查詢長文檔特定資訊：Transformer + Flash Attention + RoPE
- 需要處理超長流式資料（生物序列、時序）：Mamba
- 折衷：Hybrid 架構（部分層 Attention，部分層 SSM），如 Jamba

---

## 八、為什麼選 X 不選 Y

### 決策 1：BF16 vs FP16

| 維度 | BF16 | FP16 |
|------|------|------|
| Overflow 風險 | 極低（指數 8 bit，範圍同 FP32） | 高（max 65504，attention logit 易超） |
| 精度 | 尾數 7 bit，略低 | 尾數 10 bit，略高 |
| 硬體需求 | A100/H100 原生；V100 軟體模擬慢 | V100/T4 原生支援 |
| Loss Scaling | 不需要 | 必須，工程複雜度增加 |

**Flip Condition**：僅在 V100 / 老硬體上，或需要極高小數精度（科學計算）時選 FP16。否則一律 BF16。

---

### 決策 2：AdamW vs SGD with Momentum

| 維度 | AdamW | SGD + Momentum |
|------|-------|---------------|
| LR 敏感度 | 低（adaptive step） | 高，需要精細調 LR |
| 收斂速度 | 快，100K steps 內明顯 | 需要更多 steps |
| 訓練穩定性 | 高 | 較低，尤其深層 Transformer |
| 最終精度 | 略低於 SGD（有文獻） | 理論上更好但需充分訓練 |
| 記憶體 | 需存 m/v 狀態（2× 模型大小） | 只需 momentum（1× 模型大小） |

**Flip Condition**：超大規模訓練且記憶體極度受限時（如 ZeRO-3 + Offload 仍不夠），考慮 Adafactor（無 second moment 存儲）。

---

### 決策 3：Decoder-only vs Encoder-Decoder（生成任務）

| 維度 | Decoder-only | Encoder-Decoder |
|------|-------------|----------------|
| 生成品質（同等計算量） | 較高（更多 decoder 容量） | 略低 |
| In-context Learning | 天然支援 | 需要特殊設計 |
| 翻譯/摘要準確性 | 可接受但非最優 | 結構優勢明顯 |
| 推論 KV Cache | 1 套 | 2 套（Encoder + Decoder cross-attn） |
| 社群/生態 | 主流（LLaMA/Mistral/GPT） | T5/BART，逐漸式微 |

**Flip Condition**：輸入輸出有強結構差異（翻譯、化學分子 → 蛋白質序列）且有充足的平行語料時，Encoder-Decoder 仍有優勢。

---

### 決策 4：MoE vs Dense（相同推論 FLOPs）

| 維度 | MoE | Dense |
|------|-----|-------|
| 訓練效率 | 相同 FLOPs 下品質更高 | 較低 |
| 推論延遲 | 同計算量但更高記憶體頻寬需求 | 延遲更可預測 |
| 部署複雜度 | 高（Expert routing，跨 GPU） | 低 |
| 最小 GPU 數量 | 多（需要 Expert Parallelism） | 少 |
| Load Balancing | 需要 Aux Loss，訓練技巧多 | 無此問題 |

**Flip Condition**：若只有單機（< 8 GPU）或對延遲極敏感（< 10ms P99），選 Dense。MoE 適合多機、吞吐量優先的場景。

---

### 決策 5：Warmup Steps 2000 vs 500

| 維度 | 2000 Steps Warmup | 500 Steps Warmup |
|------|------------------|-----------------|
| 大模型（> 1B）穩定性 | 高 | 容易前期崩潰 |
| 小模型（< 125M）效率 | 浪費步數 | 足夠 |
| Batch Size 影響 | Global batch 大時需更多 warmup | - |
| 繼續訓練（resume） | 從 checkpoint 繼續時可縮短 | - |

**Flip Condition**：若從已訓練 checkpoint fine-tune，warmup 可縮短至 100–500 steps；若 global batch size 超過 4M token，warmup 需延長到 4000+。

---

### 決策 6：Flash Attention vs 標準 Attention

| 維度 | Flash Attention | 標準 Attention |
|------|----------------|--------------|
| 記憶體使用 | O(n)（Tiling） | O(n²)（存中間矩陣） |
| 計算複雜度 | 同為 O(n²) | O(n²) |
| 實際速度 | 2–4× 快（IO 優化） | 基準 |
| 實現複雜度 | 需要 CUDA kernel（已有開源） | 簡單 |
| 支援序列長度 | 64K+（搭配 RoPE） | 8K 以上 OOM |

**Flip Condition**：幾乎沒有不用 Flash Attention 的理由（2023 年後的框架預設開啟）。唯一例外：需要精確 attention 權重用於解釋性研究時，Tiling 計算的中間值無法直接獲取。

---

## 九、系統效應（訓練成本 / 精度 / 推論速度對比）

### 9.1 訓練配置對比（7B 模型，100B token）

| 配置 | 訓練時間 | GPU 費用 | 最終 PPL | 說明 |
|------|---------|---------|---------|------|
| FP32，無 Flash Attn | 960 hrs | $115K | 8.2 | POC 基準 |
| BF16 + Flash Attn | 240 hrs | $29K | 8.3 | -75% 成本，+0.1 PPL |
| BF16 + Flash Attn + ZeRO-2 | 180 hrs | $22K | 8.3 | 多機高效 |
| BF16 + FP8 + ZeRO-3（H100） | 80 hrs | $12K | 8.4 | H100 最佳 |
| MoE（46.7B 參數，等效 12B）| 220 hrs | $27K | 7.8 | 同預算更低 PPL |

*以 A100 80GB $3/hr，H100 $6/hr 估算。

### 9.2 架構選型對下游任務精度的影響

| 任務 | Encoder-only | Decoder-only | Encoder-Decoder |
|------|-------------|-------------|----------------|
| 情感分類（SST-2） | 96.4%（BERT-large） | 94.1%（GPT-3 few-shot） | 95.2%（T5-large） |
| NER（CoNLL-2003 F1） | 93.1（BERT） | 89.7（LLaMA few-shot） | 91.4（T5） |
| 機器翻譯（BLEU En-De） | N/A（無生成） | 26.4（GPT-4） | 31.2（T5-11B） |
| 程式碼生成（HumanEval） | N/A | 48.1%（CodeLlama-34B） | 42.3%（CodeT5+） |
| 語義搜尋（NDCG@10） | 0.794（BGE-large） | 0.741（E5-mistral） | 0.768（GTR-XXL） |

### 9.3 推論速度（7B 模型，A100 單卡，batch=1）

| 配置 | Prefill 延遲 | Decode 速度 | KV Cache（4K ctx） |
|------|------------|------------|-------------------|
| BF16 + 無 Flash Attn | 45ms | 28 tok/s | 4GB |
| BF16 + Flash Attn 2 | 18ms | 35 tok/s | 3.8GB（節省 IO） |
| INT8 量化（AWQ） | 20ms | 52 tok/s | 2.1GB |
| INT4 量化（GPTQ） | 22ms | 68 tok/s | 1.2GB |

---

## 十、面試答題要點

> *「這個電商 NLP 系統需要三種任務：生成、分類、語義匹配，我會採用兩模型策略而非一個架構強行通吃。情感分析和語義搜尋用 Encoder-only（如 BGE-large 或 DeBERTa），這兩個任務需要雙向 context，Encoder 在相同計算量下品質最高——情感分類 F1 約高 3–5 個百分點。商品描述生成用 Decoder-only（如 Mistral-7B fine-tune），因為生成任務和 in-context learning 是 Decoder 的天然優勢。訓練策略上，兩個模型都採用 BF16 + Flash Attention 2，LR 2000 步 Warmup + Cosine Decay，grad clip norm=1.0；在 A100 上不用 FP16 是因為省掉 loss scaling 工程複雜度。預算 $50K 的情況下，生成模型用 LoRA fine-tune（只訓練 0.1% 參數，費用 < $3K），Encoder 模型從 BGE 開始 fine-tune 也僅需 $1K，剩餘預算用於推論基礎設施。如果未來合併為一個模型，考慮 Decoder-only + 高品質 embedding head，用統一的 LLaMA 架構處理全部三類任務，但初期這個雙模型設計 ROI 更高。」*

---

## 十一、系列導航

← [Phase 7 Part 1：Transformer 核心機制——Self-Attention 與位置編碼](/posts/ai-eng-from-scratch-phase7-part1-transformer-core-zh/)

→ [Phase 8 Part 1：Pre-training 與 Fine-tuning 策略](/posts/ai-eng-from-scratch-phase8-part1-pretraining-finetuning-zh/)

---

*本文為「AI 工程從零開始」系列第 Phase 7 Part 2 篇，系列完整索引見 [/tags/ai-eng-from-scratch/](/tags/ai-eng-from-scratch/)。*
