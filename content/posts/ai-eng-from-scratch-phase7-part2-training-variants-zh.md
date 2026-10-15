---
title: "AI 工程從零開始｜Phase 7 Part 2：Transformer 訓練策略與架構變體"
date: 2026-06-21T16:00:00+08:00
draft: false
weight: 15
description: "深入解析 Transformer 訓練：學習率 Warmup/Schedule、梯度裁剪、混合精度訓練、Encoder-only/Decoder-only/Encoder-Decoder 架構選型，以及 MoE 混合專家系統"
categories: ["all", "ai", "engineering"]
tags: ["AI", "Transformer", "Training", "MoE", "BERT", "GPT", "T5", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "15 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人認為：Transformer 就是 attention + FFN，照抄論文程式碼就能訓練起來。*
> *真實情況是：沒有 LR warmup 模型在第 100 步就 loss 爆炸；沒有梯度裁剪 NaN 讓你懷疑人生。*
> *進階工程師知道：訓練策略與架構選型決定了 90% 的成敗，程式碼只佔 10%。*
> *本文要解決的是：為什麼這些技巧存在、何時用哪個、以及什麼訊號告訴你該從單機實驗升級到多機訓練。*

---

這篇給已經能把 Transformer 跑起來、但 loss 一爆炸就只能重跑的工程師看。讀完你會能解釋 LR warmup、梯度裁剪與 BF16 各自擋住哪一種訓練崩潰，為 BERT 式、GPT 式與 T5 式架構各找到正確的任務，看懂 MoE 的 load balancing 為什麼是工程問題而非數學問題，並能為一個同時要做生成、分類與跨語言檢索的 NLP 系統，在 $50K 預算內選出架構與訓練配方。

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

## 二、何時該升級：從單機實驗到多機與 3D 平行的觸發條件

單機 4–8 張 A100、DDP、固定學習率、FP32 或 BF16，足以驗證任務可行性：模型在 1–3B 參數、資料在 1B token 以內時，偶發的 loss spike 重跑一次就好。該把 warmup、梯度裁剪、BF16 與 ZeRO-2/FSDP 全部補上的訊號有兩個——**參數加上 Adam 狀態（約 16 bytes/param）放不進單卡**，以及**一次實驗貴到不能接受偶發崩潰**：當一次訓練要燒掉數萬美元，「40% 的 run 在 step 200 前崩潰」就從可忍受的實驗噪音變成不可接受的成本，穩定性技巧也從選配變成必備。

第二道門檻是資料平行本身不夠用：ZeRO-2 仍要求每張卡放得下完整的前向啟動值與一層的權重。當模型大到單卡連一層都放不下（約 13–20B 起），就要在節點內切 Tensor Parallel；當模型超過整個節點的記憶體（70B 以上），再跨節點切 Pipeline Parallel，組成 3D 平行。DP／TP／PP／ZeRO 各切什麼、通訊拓撲怎麼擺，完整說明見 [Phase 10 Part 2 §五](/posts/ai-eng-from-scratch-phase10-part2-pretraining-zh/)。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| 單機 DDP，固定 LR，FP32 | ZeRO-2/FSDP + warmup + 梯度裁剪 + BF16 | 參數 + 優化器狀態（約 16 bytes/param）放不進單卡；單次實驗費用高到不能接受偶發崩潰 |
| ZeRO-2 資料平行 | TP（節點內）+ PP（跨節點）的 3D 平行 | 單卡放不下一層的權重與啟動值；模型超過單節點記憶體（> 70B） |
| BF16 | FP8（H100 Transformer Engine） | 矩陣乘吞吐成為成本主因且硬體支援；願意承擔 per-tensor scale 的工程複雜度 |

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

### 4.3 FP8 訓練（Hopper 世代起）

H100 的 Transformer Engine 支援 FP8 矩陣乘（Blackwell 世代的 B200/GB200 進一步支援 MXFP8 與 FP4；DeepSeek-V3 已示範在大規模預訓練中使用 FP8）：

- **前向計算**：E4M3（較高精度，保留特徵細節）
- **梯度計算**：E5M2（較大範圍，容納梯度 spike）
- **優化器狀態**：BF16 或 FP32

**典型收益（概略值，依模型與框架而異）**：相比 BF16，FP8 訓練吞吐量提升約 30–40%，但需要 per-tensor 動態 scale 管理，工程複雜度上升。精度損失通常 < 0.1%（perplexity 差異）。

**選型建議**：

| 硬體 | 推薦精度 | 理由 |
|------|---------|------|
| V100 / T4 | FP16 + loss scaling | 無 BF16 硬體支援 |
| A100 / A6000 | BF16 | 無 overflow 風險，硬體原生支援 |
| H100 / H200 / B200 | BF16 前向 + FP8 矩陣乘（Blackwell 可評估 MXFP8） | 最大吞吐量 |
| AMD MI300X | BF16 | 硬體支援 FP8，但需先確認所用框架/ROCm 版本的 FP8 訓練支援度 |

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

> Mixtral 式的「少量大 Expert + auxiliary loss」已不是唯一做法：DeepSeekMoE 改用細粒度 Expert（切得更小、每 token 啟用更多個）加上常駐的 shared expert；DeepSeek-V3 更採用 auxiliary-loss-free 負載平衡（對每個 Expert 的 routing 分數加上動態調整的 bias），避免 aux loss 干擾主任務。

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

> Tiling 的完整推導、HBM/SRAM 頻寬數字與 FA1/2/3 的差異見 [Phase 7 Part 1 §七](/posts/ai-eng-from-scratch-phase7-part1-transformer-architecture-zh/)，此處只做摘要。

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

### 決策 2：Decoder-only vs Encoder-Decoder（生成任務）

| 維度 | Decoder-only | Encoder-Decoder |
|------|-------------|----------------|
| 生成品質（同等計算量） | 較高（更多 decoder 容量） | 略低 |
| In-context Learning | 天然支援 | 需要特殊設計 |
| 翻譯/摘要準確性 | 可接受但非最優 | 結構優勢明顯 |
| 推論 KV Cache | 1 套 | 2 套（Encoder + Decoder cross-attn） |
| 社群/生態 | 主流（LLaMA/Mistral/GPT） | T5/BART，逐漸式微 |

**Flip Condition**：輸入輸出有強結構差異（翻譯、化學分子 → 蛋白質序列）且有充足的平行語料時，Encoder-Decoder 仍有優勢。

---

### 決策 3：MoE vs Dense（相同推論 FLOPs）

| 維度 | MoE | Dense |
|------|-----|-------|
| 訓練效率 | 相同 FLOPs 下品質更高 | 較低 |
| 推論延遲 | 同計算量但更高記憶體頻寬需求 | 延遲更可預測 |
| 部署複雜度 | 高（Expert routing，跨 GPU） | 低 |
| 最小 GPU 數量 | 多（需要 Expert Parallelism） | 少 |
| Load Balancing | 需要 Aux Loss，訓練技巧多 | 無此問題 |

**Flip Condition**：若只有單機（< 8 GPU）或對延遲極敏感（< 10ms P99），選 Dense。MoE 適合多機、吞吐量優先的場景。

---

Flash Attention vs 標準 Attention 的取捨見 [Phase 7 Part 1 §八](/posts/ai-eng-from-scratch-phase7-part1-transformer-architecture-zh/)；2023 年後的訓練框架預設開啟，唯一要關掉它的理由是解釋性研究需要讀出完整的 attention 權重矩陣。

---

## 九、系統效應（訓練成本 / 精度 / 推論速度對比）

### 9.1 訓練配置對比（7B 模型，100B token）

| 配置 | 訓練時間 | GPU 費用 | 最終 PPL | 說明 |
|------|---------|---------|---------|------|
| FP32，無 Flash Attn | 960 hrs | $115K | 8.2 | FP32 基準 |
| BF16 + Flash Attn | 240 hrs | $29K | 8.3 | -75% 成本，+0.1 PPL |
| BF16 + Flash Attn + ZeRO-2 | 180 hrs | $22K | 8.3 | 多機高效 |
| BF16 + FP8 + ZeRO-3（H100） | 80 hrs | $12K | 8.4 | H100 最佳 |
| MoE（46.7B 參數，等效 12B）| 220 hrs | $27K | 7.8 | 同預算更低 PPL |

*以 A100 80GB $3/hr，H100 $6/hr 估算；本表為示意估算，非實測數據。

### 9.2 架構選型對下游任務精度的影響

| 任務 | Encoder-only | Decoder-only | Encoder-Decoder |
|------|-------------|-------------|----------------|
| 情感分類（SST-2） | 96.4%（BERT-large） | 94.1%（GPT-3 few-shot） | 95.2%（T5-large） |
| NER（CoNLL-2003 F1） | 93.1（BERT） | 89.7（LLaMA few-shot） | 91.4（T5） |
| 機器翻譯（BLEU En-De） | N/A（無生成） | 26.4（GPT-4） | 31.2（T5-11B） |
| 程式碼生成（HumanEval） | N/A | 48.1%（CodeLlama-34B） | 42.3%（CodeT5+） |
| 語義搜尋（NDCG@10） | 0.794（BGE-large） | 0.741（E5-mistral） | 0.768（GTR-XXL） |

*示意估算，非實測數據*

### 9.3 推論速度（7B 模型，A100 單卡，batch=1）

| 配置 | Prefill 延遲 | Decode 速度 | KV Cache（4K ctx） |
|------|------------|------------|-------------------|
| BF16 + 無 Flash Attn | 45ms | 28 tok/s | 4GB |
| BF16 + Flash Attn 2 | 18ms | 35 tok/s | 3.8GB（節省 IO） |
| INT8 量化（AWQ） | 20ms | 52 tok/s | 2.1GB |
| INT4 量化（GPTQ） | 22ms | 68 tok/s | 1.2GB |

*示意估算，非實測數據*

---

## 十、系列導航

← [Phase 7 Part 1：Transformer 架構深度解析 — 改變一切的注意力](/posts/ai-eng-from-scratch-phase7-part1-transformer-architecture-zh/)

→ [Phase 8 Part 1：擴散模型 — 從雜訊到藝術的數學](/posts/ai-eng-from-scratch-phase8-part1-diffusion-models-zh/)

---

*本文為「AI 工程從零開始」系列第 Phase 7 Part 2 篇，系列完整索引見 [/tags/ai-eng-from-scratch/](/tags/ai-eng-from-scratch/)。*
