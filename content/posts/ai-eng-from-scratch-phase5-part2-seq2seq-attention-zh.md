---
title: "AI 工程從零開始｜Phase 5 Part 2：Seq2Seq 與注意力機制 — Transformer 前夜"
date: 2026-06-21T13:30:00+08:00
draft: false
weight: 10
description: "深入解析 RNN/LSTM/GRU 序列建模、Encoder-Decoder 架構、Bahdanau 注意力機制，理解 Transformer 取代 RNN 的工程動機"
categories: ["engineering", "ai", "all"]
tags: ["AI", "NLP", "LSTM", "Seq2Seq", "Attention", "RNN", "Encoder-Decoder", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人把 RNN 當作「處理序列的工具」，把 LSTM 當作「改良版 RNN」，就停在這裡了。*
> *真正的工程師會問：為什麼固定長度的 context vector 是瓶頸？注意力機制解決了什麼具體問題？*
> *Transformer 不是憑空出現的魔法，它是對 RNN 家族每一個痛點的系統性回應。*
> *理解這段歷史，你才能真正讀懂「Attention is All You Need」。*

---

**面試情境**：「你正在設計一個英中機器翻譯系統，句子長度最長 200 個 token。請說明你會選擇哪種架構，為什麼不直接用純 RNN，LSTM 與 GRU 在這個場景下如何選擇，以及如果引入注意力機制，架構上需要做哪些改變？」

---

## 一、核心問題：序列資料的特殊挑戰

一般的前饋神經網路（Feedforward NN）假設輸入之間互相獨立，但語言、時間序列、語音等資料天生帶有**順序依賴**：

- 「我昨天沒有**吃**飯」與「我昨天沒有**喝**飯」—— 語義完全不同，差異在第五個字
- 翻譯「The animal didn't cross the street because **it** was too tired」—— "it" 指的是 animal 還是 street？需要回顧前文
- 股票預測：今天的價格取決於過去 N 天的走勢

序列建模的三大工程挑戰：

| 挑戰 | 具體現象 | 工程代價 |
|------|---------|---------|
| 可變長度輸入 | 句子從 5 到 500 token 不等 | 固定大小向量無法直接處理 |
| 長程依賴 | 200 token 前的主語影響動詞 | 梯度消失導致無法學習 |
| 順序計算瓶頸 | t 步必須等 t-1 步完成 | 無法並行，GPU 利用率低 |

這三個問題，RNN → LSTM/GRU → Seq2Seq+Attention → Transformer，每一步都是針對前一步遺留問題的工程解法。

---

## 二、三個演進階段

### ╔══ Phase 1：POC — 純 RNN（< 10K 訓練樣本）╗

適合：情感分類、簡短序列標記、學習驗證

```
輸入序列：  x₁  x₂  x₃  x₄  x₅
            │   │   │   │   │
           [E] [E] [E] [E] [E]   ← Embedding Layer
            │   │   │   │   │
h₀ ──────▶[RNN]▶[RNN]▶[RNN]▶[RNN]▶[RNN]──▶ h₅
                                              │
                                           [Dense]
                                              │
                                           Output
```

**新增元件 vs 空白狀態：**
- Embedding Layer：token → 128-dim 向量
- RNN Cell：hidden state h_t = tanh(W_hh · h_{t-1} + W_xh · x_t + b)
- 單一輸出層

**成本/複雜度：**
- 訓練時間：< 5 分鐘（CPU 可跑）
- 程式碼：< 50 行 PyTorch
- 問題：序列 > 20 token 時梯度消失，長句精度驟降

---

### ╔══ Phase 2：MVP — LSTM + Seq2Seq（10K–500K 樣本）╗

適合：機器翻譯、文字摘要、對話系統

```
Encoder                           Decoder
────────────────────────────────────────────────────────
x₁ ──▶[LSTM]──▶                  ▶[LSTM]──▶ y₁
x₂ ──▶[LSTM]──▶                  ▶[LSTM]──▶ y₂
x₃ ──▶[LSTM]──▶                  ▶[LSTM]──▶ y₃
x₄ ──▶[LSTM]──▶                  ▶[LSTM]──▶ y₄
x₅ ──▶[LSTM]──▶ context vector ──▶[LSTM]──▶ <EOS>
              (h₅, c₅)
              ↑
         所有輸入資訊
         壓縮進此向量
         ← 瓶頸所在 →
```

**新增元件 vs Phase 1：**
- LSTM Cell（加入 forget/input/output gate）
- Encoder-Decoder 分離架構
- Teacher Forcing 訓練策略

**成本/複雜度：**
- 訓練時間：GPU 上數小時到一天
- BLEU 分數（英中 WMT）：~20–25（vs RNN ~15）
- 問題：context vector 固定 256/512 維，長句資訊遺失

---

### ╔══ Phase 3：Scale — LSTM + Attention（500K+ 樣本）╗

適合：生產級翻譯、長文摘要、語音辨識後處理

```
Encoder Hidden States
h₁  h₂  h₃  h₄  h₅
│   │   │   │   │
└───┴───┴───┴───┘
        │
   Attention Layer   ← 對每個解碼步驟，動態加權所有 encoder states
        │
   context vector_t  ← 每步不同！非固定瓶頸
        │
      [LSTM Decoder] ──▶ y_t
        │
   下一步 s_{t+1} ───▶ 重新計算 attention weights
```

**新增元件 vs Phase 2：**
- Attention Score 計算（Bahdanau / Luong）
- Dynamic Context Vector（每解碼步重新算）
- Alignment Matrix 視覺化（可解釋性）

**成本/複雜度：**
- 訓練時間：多 30–50% 計算量
- BLEU 分數：~28–32（vs Phase 2 ~25）
- 問題：RNN 仍是順序計算，無法充分並行 → Transformer 的動機

---

## 三、RNN 原理與梯度消失問題

### RNN 基本計算

```
時間步 t 的計算圖：

x_t ────────────────────────────────────────┐
                                             ▼
h_{t-1} ──▶ [W_hh] ──▶ (+) ──▶ tanh ──▶ h_t ──▶ [W_hy] ──▶ ŷ_t
                         ▲
                    [W_xh · x_t]

參數：
  W_hh ∈ ℝ^{H×H}   (hidden-to-hidden)
  W_xh ∈ ℝ^{H×D}   (input-to-hidden)
  W_hy ∈ ℝ^{V×H}   (hidden-to-output)
  所有時間步共享同一組參數 ← 關鍵！
```

### 梯度消失的數學直覺

BPTT（Backpropagation Through Time）計算 T 步前的梯度：

```
∂L/∂h₁ = ∂L/∂h_T · ∏_{t=2}^{T} (∂h_t/∂h_{t-1})

每一項 ∂h_t/∂h_{t-1} = W_hh^T · diag(tanh'(·))

若 W_hh 最大奇異值 < 1 → 連乘後指數級趨近 0 → 梯度消失
若 W_hh 最大奇異值 > 1 → 連乘後指數級爆炸 → 梯度爆炸
```

**實際觀測到的症狀：**
- 訓練損失在前 20 epoch 後停滯不降
- 梯度範數在淺層接近 0（可用 `torch.nn.utils.clip_grad_norm_` 偵測）
- 序列長度 > 30 時，BLEU 分數斷崖式下跌 ~40%

---

## 四、LSTM/GRU：門控機制的工程直覺

### LSTM 內部結構

```
                    ┌─────────────────────────────────────────┐
                    │           LSTM Cell                      │
  x_t ─────────────┤                                         │
  h_{t-1} ─────────┤   forget gate: f_t = σ(W_f·[h,x]+b_f)  │
  c_{t-1} ──────── ┤                     │                   │
                    │   c_{t-1} ──×(f_t)─┤                   │
                    │                    │                   │
                    │   input gate:      │                   │
                    │   i_t = σ(W_i·[h,x]+b_i)              │
                    │   g_t = tanh(W_g·[h,x]+b_g)           │
                    │   c_t = c_{t-1}·f_t + i_t·g_t ────── ▶ c_t
                    │                                         │
                    │   output gate:                          │
                    │   o_t = σ(W_o·[h,x]+b_o)              │
                    │   h_t = o_t · tanh(c_t) ──────────── ▶ h_t
                    └─────────────────────────────────────────┘

關鍵洞見：Cell State c_t 是「高速公路」
  - 梯度可以直接流過加法節點（gradient highway）
  - forget gate 學習「什麼時候遺忘」
  - 解決長程依賴：理論上可記住數百步前的資訊
```

### GRU 簡化版

GRU（Gated Recurrent Unit）把 LSTM 的 3 個門簡化為 2 個：

```
reset gate:  r_t = σ(W_r·[h_{t-1}, x_t])
update gate: z_t = σ(W_z·[h_{t-1}, x_t])
candidate:   h̃_t = tanh(W·[r_t ⊙ h_{t-1}, x_t])
output:      h_t = (1-z_t)·h_{t-1} + z_t·h̃_t
```

**工程取捨數字：**

| 指標 | LSTM | GRU |
|------|------|-----|
| 參數量（H=256） | 4 × (256+D) × 256 | 3 × (256+D) × 256 |
| 訓練速度 | 基準 | 快 ~20% |
| 短序列精度 | 略低 | 略高（參數少，不易過擬合） |
| 長序列精度（> 100 token） | 較高 | 持平或略低 |
| 記憶體用量 | H + H（h 和 c） | H（只有 h） |

---

## 五、Encoder-Decoder 架構：機器翻譯的誕生

### 為什麼需要兩個 RNN？

純 RNN 適合「輸入輸出長度相同」的任務（如序列標記）。但翻譯的輸入輸出長度不同：

```
輸入：「我 愛 機器 學習」（4 tokens）
輸出："I love machine learning"（4 tokens，但語序不同）

或：

輸入：「Bundesgesundheitsministerium」（1 token）
輸出："Federal Ministry of Health"（4 tokens）
```

Encoder-Decoder 的核心思想：

```
Phase 1 — Encode（理解）：
  把輸入序列壓縮成一個固定維度的「語意向量」

  x₁ → x₂ → x₃ → x₄
  [LSTM] → [LSTM] → [LSTM] → [LSTM]
                               ↓
                         (h_T, c_T) = context vector
                         代表整個輸入的語意

Phase 2 — Decode（生成）：
  從語意向量出發，逐步生成目標序列

  context vector
       ↓
  [LSTM] → y₁ = "I"
  [LSTM] → y₂ = "love"
  [LSTM] → y₃ = "machine"
  [LSTM] → y₄ = "learning"
  [LSTM] → y₅ = <EOS>
```

### Teacher Forcing vs Free Running

**Teacher Forcing**（訓練時）：
- 解碼器每步的輸入 = 真實的上一個 token（ground truth）
- 優點：訓練快，梯度穩定
- 缺點：訓練/推理不一致（Exposure Bias）

**Free Running**（推理時）：
- 解碼器每步的輸入 = 上一步自己預測的 token
- 問題：錯誤會累積（error propagation）

**排程採樣（Scheduled Sampling）**：訓練時混合兩者，從 100% Teacher Forcing 逐漸降到 50%，緩解 Exposure Bias。

### Context Vector 的瓶頸

```
輸入句子長度 → BLEU 分數（無 Attention）
  1–10 tokens：  ~38
  11–20 tokens： ~30
  21–30 tokens： ~24
  31–40 tokens： ~17
  40+ tokens：   ~11

資料來源：Bahdanau et al. 2015 論文圖表
```

問題根源：無論輸入多長，context vector 都是固定維度（512 dim）。翻譯長句時，前面的資訊被後面的覆蓋 —— 這正是注意力機制要解決的問題。

---

## 六、注意力機制：Bahdanau vs Luong

### 核心直覺

人在翻譯時不是「看一眼全句然後默背」，而是「翻譯每個詞時，眼睛重新掃描原文對應位置」。注意力機制模擬這個過程：

```
解碼第 t 步時，動態計算 encoder 每個位置的重要性：

Encoder states: h₁  h₂  h₃  h₄  h₅
                 │   │   │   │   │
                [e₁][e₂][e₃][e₄][e₅]  ← score(s_{t-1}, hᵢ)
                 │   │   │   │   │
                softmax → α₁ α₂ α₃ α₄ α₅  (sum = 1)
                 │   │   │   │   │
                 └───┴───┴───┴───┘
                         │
                    Σ αᵢ · hᵢ = context_t  ← 動態！每步不同
                         │
                   concat(context_t, s_{t-1})
                         │
                      [Dense] ──▶ s_t
```

### Bahdanau（加法）注意力

提出年份：2015，論文《Neural Machine Translation by Jointly Learning to Align and Translate》

```
分數計算：
  e_{t,i} = v_a^T · tanh(W_a · s_{t-1} + U_a · hᵢ)

  其中：
    s_{t-1} ∈ ℝ^H  (decoder 前一步 hidden state)
    hᵢ ∈ ℝ^{2H}    (bidirectional encoder 的拼接)
    v_a, W_a, U_a  (可學習參數)

注意力權重：
  α_{t,i} = softmax(e_{t,i})

Context vector：
  c_t = Σᵢ α_{t,i} · hᵢ
```

**Alignment Matrix 視覺化：**

```
Decoder output position
     y₁  y₂  y₃  y₄
x₁  0.8 0.1 0.0 0.0
x₂  0.1 0.7 0.1 0.0
x₃  0.1 0.1 0.6 0.2
x₄  0.0 0.1 0.3 0.8

對角線高亮 → 模型學到近似單調對齊
語序差異的語言（如日英）→ 矩陣呈現交叉模式
```

### Luong（乘法）注意力

提出年份：2015，論文《Effective Approaches to Attention-based Neural Machine Translation》

```
三種分數計算方式：

Dot:     e_{t,i} = s_t^T · hᵢ
General: e_{t,i} = s_t^T · W_a · hᵢ        ← 最常用
Concat:  e_{t,i} = v_a^T · tanh(W_a · [s_t; hᵢ])  ← 等同 Bahdanau
```

**Bahdanau vs Luong 工程差異：**

| 面向 | Bahdanau | Luong |
|------|----------|-------|
| 計算時機 | 用 s_{t-1}（解碼前） | 用 s_t（解碼後） |
| 計算複雜度 | 略高（需 tanh） | 略低（矩陣乘法） |
| 對齊品質 | 稍好（有額外參數） | 接近 |
| 實作難度 | 中 | 低 |
| 常見場景 | 學術基準、語音 | 快速工程實作 |

---

## 七、Beam Search 與解碼策略

Greedy Decoding（每步選機率最高的 token）在實務中常產生重複或不自然的句子。

### Beam Search

維持 k 個「候選序列」同時推進：

```
Beam size = 3 的範例（英 → 中）：

Step 0: 起始 <BOS>

Step 1（保留 top-3）：
  候選 1: "我"         log P = -0.2
  候選 2: "這"         log P = -0.8
  候選 3: "那"         log P = -1.1

Step 2（每個候選展開，保留 top-3）：
  "我 愛"              log P = -0.2 + -0.3 = -0.5  ← 保留
  "我 喜歡"            log P = -0.2 + -0.6 = -0.8  ← 保留
  "這 個"              log P = -0.8 + -0.1 = -0.9  ← 保留
  "那 是"              log P = -1.1 + -0.2 = -1.3  ← 捨棄

Step 3：繼續展開，直到所有候選產生 <EOS>

最終選擇累積對數機率最高的序列
```

**Beam Size 對品質與速度的影響：**

| Beam Size | BLEU（WMT En→De） | 推理時間（相對） | 記憶體 |
|-----------|-------------------|----------------|--------|
| 1（Greedy）| 26.1 | 1.0x | 1x |
| 4 | 28.4 | 2.1x | 4x |
| 8 | 28.9 | 3.8x | 8x |
| 16 | 29.0 | 7.2x | 16x |
| 32 | 29.0 | 14x | 32x |

實務上 beam=4 是最佳工程平衡點；beam > 8 收益邊際遞減。

### 長度懲罰

Beam Search 傾向於選擇短句（短句的累積對數機率自然較高）。解法：

```
score(Y, X) = log P(Y|X) / |Y|^α

α = 0.6 ~ 0.8 是常用值
```

### 其他解碼策略

| 策略 | 適用場景 | 特點 |
|------|---------|------|
| Greedy | 快速原型 | 速度最快，品質較低 |
| Beam Search | 翻譯、摘要 | 品質/速度平衡 |
| Top-k Sampling | 創意寫作、對話 | 多樣性高 |
| Top-p (Nucleus) | LLM 生成 | 動態詞彙集 |
| Temperature Scaling | 所有生成場景 | 控制隨機性 |

---

## 八、為什麼選 X 不選 Y

### 決策 1：LSTM vs 純 RNN

```
選擇          選 LSTM 的理由                    不選純 RNN 的理由
─────────────────────────────────────────────────────────────────
長序列任務    Cell state gradient highway        梯度消失，> 30 token 失效
             梯度穩定，可訓練 200+ 步             BPTT 計算不穩定
翻譯/摘要    遺忘門學習哪些歷史要保留             無法控制記憶衰減
             BLEU 高 5–10 分                     長句精度斷崖
```

**翻轉條件：** 序列長度 < 15 token 且訓練資料 < 5K 時，純 RNN 參數少、不易過擬合，反而可能較好。

---

### 決策 2：LSTM vs GRU

```
選擇          選 LSTM 的理由                    選 GRU 的理由
─────────────────────────────────────────────────────────────────
參數量        H=512 時參數多 ~33%               訓練資料不足時更穩定
長序列        cell state 額外記憶體提供優勢       差距不顯著（< 2% BLEU）
速度          略慢                              每步快 ~20%
實作          成熟，框架支援完整                 程式碼更簡潔
```

**翻轉條件：** 序列長度 > 100 且資源充足 → LSTM；快速迭代或 mobile 部署 → GRU。

---

### 決策 3：加注意力 vs 不加注意力

```
選擇             選 Attention 的理由              不選的理由
────────────────────────────────────────────────────────────────
精度             長句 BLEU 提升 5–10 分           短句（< 20 token）差距 < 2
可解釋性         Alignment matrix 可視覺化         增加計算量 ~30%
訓練穩定性       梯度路徑更短，收斂更快            實作複雜度增加
長文本支援       500 token 仍保持高品質            小型任務 ROI 低
```

**翻轉條件：** 句子長度始終 < 20 token 且部署環境計算受限 → 無 attention 可接受。

---

### 決策 4：Bahdanau vs Luong 注意力

```
選擇          選 Bahdanau 的理由                選 Luong 的理由
─────────────────────────────────────────────────────────────────
計算           用 s_{t-1}，可以 pipeline        用 s_t，邏輯更直觀
對齊品質       稍好（有獨立投影矩陣）             差距 < 1 BLEU
實作           略複雜                            更容易 debug
語音/ASR       Hybrid Attention 變體多           NMT 快速實驗首選
```

**翻轉條件：** 工程快速迭代 → Luong General；追求最高精度且有時間 tune → Bahdanau。

---

### 決策 5：Seq2Seq+Attention vs Transformer

```
選擇                  選 Seq2Seq+Attention            選 Transformer
────────────────────────────────────────────────────────────────────────
訓練資料量            < 100K 樣本時更穩定              需要 > 1M 樣本才收益明顯
訓練速度              順序計算，慢 3–10x              全並行，GPU 利用率 90%+
長序列（> 512）        attention 仍是 O(n²)            同樣 O(n²)，但常數更小
可解釋性              Alignment matrix 直觀            Self-attention 較難解釋
部署                  模型小，latency 低              需要 KV cache 等優化
```

**翻轉條件：** 資料量 < 50K 且資源有限 → Seq2Seq；資料充足、追求 SOTA → Transformer。

---

### 決策 6：Beam Search vs Greedy Decoding

```
選擇          選 Beam Search 的理由              選 Greedy 的理由
─────────────────────────────────────────────────────────────────
翻譯品質      BLEU 高 2–5 分                     即時系統 latency 要求 < 50ms
多樣性        多條候選序列可後處理                自動補全等低精度容忍場景
生產系統      beam=4 是業界標準配置               beam size 線性增加記憶體
批次推理      可與 batching 結合優化              更容易批次化
```

**翻轉條件：** 即時對話（需要 < 100ms）或 mobile 部署 → Greedy；離線翻譯、高品質需求 → Beam=4~8。

---

## 九、系統效應：RNN 家族 vs Transformer

### 精度對比（WMT 英德翻譯 BLEU 分數）

| 模型 | BLEU | 備註 |
|------|------|------|
| RNN（Seq2Seq 無 Attention） | 14.5 | 2014 年基準 |
| LSTM + Bahdanau Attention | 28.3 | 2015 年基準 |
| 雙向 LSTM + Attention | 30.1 | 2016 常見配置 |
| Transformer（base） | 38.1 | 2017 年 SOTA |
| Transformer（big） | 41.0 | 2017 年 SOTA |

LSTM+Attention 到 Transformer：**BLEU +10**，這不是小幅改進，是本質性突破。

### 訓練效率對比

| 指標 | LSTM（2-layer, H=512） | Transformer（base） |
|------|----------------------|-------------------|
| WMT 訓練時間（8 GPU） | ~5 天 | ~12 小時 |
| GPU 利用率 | 30–50%（順序計算瓶頸） | 85–95%（全並行） |
| 記憶體（batch=32, seq=100） | ~4 GB | ~6 GB |
| 最長可處理序列 | 200–300（精度保證） | 512–2048（視記憶體） |
| 推理 latency（單句） | ~80ms | ~45ms（有 KV cache）|

### 梯度流動對比

```
LSTM（100 步序列）的梯度路徑：
  L → h₁₀₀ → h₉₉ → h₉₈ → ... → h₁
  最短路徑：100 個乘法節點（雖有 highway，但仍有衰減）

Transformer（100 token 序列）的梯度路徑：
  L → 每個 position 直接通過 Self-Attention 連到所有其他 position
  最短路徑：O(1) — 任意兩個 position 之間只隔一個 attention 操作
  這是 Transformer 在長序列上碾壓 LSTM 的根本原因
```

### Before/After：引入 Attention 的工程效益

| 指標 | Before（無 Attention） | After（有 Attention） |
|------|----------------------|---------------------|
| 短句 BLEU（< 20 tokens） | 35.2 | 37.1（+5%） |
| 長句 BLEU（> 40 tokens） | 11.4 | 28.6（+151%） |
| 訓練收斂 epoch | ~30 | ~20（快 33%） |
| 模型可解釋性 | 低（黑盒） | 高（alignment 可視化） |
| 推理時間 | 基準 | +25%（值得） |

---

## 十、面試答題要點

**問題**：「設計英中翻譯系統，句子最長 200 token，請說明架構選擇與注意力機制引入的動機。」

> *「純 RNN 在序列長度超過 30 token 時因梯度消失導致 BLEU 斷崖下跌 40%，因此首先升級到雙向 LSTM；但固定維度的 context vector 是長句翻譯的根本瓶頸 —— 實驗數據顯示無 Attention 時 40+ token 句子的 BLEU 僅 11，引入 Bahdanau 注意力後提升到 28。在 100K 以下的訓練資料規模，我會選擇 LSTM+Attention 而非 Transformer，因為 Transformer 需要大量資料才能收斂，且 LSTM 的 alignment matrix 提供了更好的可解釋性以利除錯。解碼策略上採用 beam=4，相比 greedy 只增加 2.1x 推理時間但 BLEU 提升 2.3 分，是最佳工程平衡點。如果資料量成長到 500K+，下一步就是遷移到 Transformer —— 那是 Seq2Seq+Attention 每個痛點的系統性解法。」*

---

## 十一、系列導航

本文是「AI 工程從零開始」系列 Phase 5 的第 2 篇。

| 方向 | 連結 |
|------|------|
| ← 上一篇 | [Phase 5 Part 1：詞向量與語言模型基礎（Word2Vec / N-gram / 困惑度）](/posts/ai-eng-from-scratch-phase5-part1-word-embeddings-zh/) |
| → 下一篇 | Phase 5 Part 3：Transformer 深度解析（Multi-Head Attention / Positional Encoding / Pre-LN）（即將發布）|

---

*本文屬於「[AI 工程從零開始](/tags/ai/)」系列，從數學基礎到生產部署，系統性建立 AI 工程能力。*
