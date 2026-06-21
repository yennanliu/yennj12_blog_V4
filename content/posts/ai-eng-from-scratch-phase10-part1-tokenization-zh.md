---
title: "AI 工程從零開始｜Phase 10 Part 1：從頭構建 LLM — Tokenization 的工程藝術"
date: 2026-06-21T18:00:00+08:00
draft: false
weight: 19
description: "深入解析 LLM Tokenization：BPE/WordPiece/SentencePiece 演算法、詞彙表大小的工程取捨、多語言 Token 效率與 Tiktoken 生產實作"
categories: ["engineering", "ai", "all"]
tags: ["AI", "LLM", "Tokenization", "BPE", "SentencePiece", "Vocabulary", "RKK", "Interview"]
authors: ["yen"]
readTime: "20 min"
series: ["ai-eng-from-scratch"]
---

> 大多數人以為 Tokenization 只是「把文字切成小段」，隨便選一個 tokenizer 接上模型就好。  
> 現實是：詞彙表大小決定了模型容量與訓練成本，token 邊界影響了推理能力，  
> 多語言效率直接決定非英語使用者的 API 費用與延遲，  
> 一個錯誤的 tokenization 決策，可以讓整個預訓練白費。

---

## 面試情境

> 你的團隊正在從零預訓練一個 30B 參數的多語言 LLM，目標語言包含英文、繁體中文、日文與 Python/SQL 代碼。  
> 面試官問：「你會如何設計這個模型的 tokenizer？詞彙表要多大？選哪種演算法？中文效率問題怎麼處理？請以三個演進階段說明。」

---

## 一、核心問題：Tokenization 為什麼是 LLM 的第一道關卡

Tokenization 是 LLM pipeline 的第一步，也是最容易被低估的一步。它做的事情看似簡單：把原始文字轉換成整數序列（token IDs），讓模型能夠處理。但這個轉換過程中埋藏了大量工程決策，每一個都有深遠影響。

**為什麼 Tokenization 很重要？**

1. **模型容量分配**：詞彙表大小直接決定 Embedding 層的參數量。vocab_size=50K、embedding_dim=4096 時，Embedding 層就佔了 50K × 4096 × 2 bytes ≈ 400MB，相當於整個模型參數的 5–10%。

2. **序列長度放大器**：同樣一段中文，GPT-4 tokenizer（cl100k_base）平均每個漢字消耗 1.5 tokens，而設計不良的 tokenizer 可能消耗 3–4 tokens（逐字節切割）。context window 128K tokens，有效利用率差了 2–3 倍。

3. **訓練成本乘數**：預訓練是以 token 數計算的。用同樣 1TB 的中文語料，高效 tokenizer 產生 500B tokens，低效 tokenizer 產生 1.5T tokens，訓練時間差了 3 倍，費用差了 $2M–$6M。

4. **推理能力邊界**：某些數學推理任務中，把數字切成單獨 digit tokens（"123" → ["1","2","3"]）比切成整體 token 有更好的算術表現，因為模型能看到每一位的結構。

5. **跨語言公平性**：英文 1 個 word ≈ 1.3 tokens；同等資訊量的中文可能需要 2–4 倍 tokens。這意味著多語言模型在處理中文時，API 費用更高、速度更慢、context 利用率更低。

```
┌────────────────────────────────────────────────────────────────┐
│                    Tokenization 的影響鏈                        │
│                                                                │
│  原始文字                                                       │
│     │                                                          │
│     ▼                                                          │
│  ┌──────────────┐    詞彙表大小 → Embedding 參數量              │
│  │  Tokenizer   │    Token 邊界 → 推理能力                      │
│  └──────┬───────┘    序列長度  → Context 利用率                 │
│         │            Token 效率→ 訓練/推理成本                  │
│         ▼                                                      │
│  Token ID 序列  →  Embedding  →  Transformer  →  Output       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 二、三個演進階段（POC / MVP / Scale）

### Phase 1：POC — 用現成 Tokenizer 快速驗證（< 10K 用戶 / 實驗階段）

**目標**：最快速驗證模型架構，不投入 tokenizer 客製化成本。

```
┌─────────────────────────────────────────────────────────────┐
│                   Phase 1 架構：借用現成方案                   │
│                                                             │
│  原始文字  ──▶  tiktoken (cl100k_base)  ──▶  Token IDs      │
│                      │                                      │
│                 vocab_size=100,277                           │
│                 現成 BPE 詞彙表                              │
│                 支援多語言（但中文效率未最佳化）                │
│                                                             │
│  模型架構：GPT-2 style（驗證用，< 1B 參數）                    │
│  訓練資料：< 50B tokens（English-heavy）                     │
└─────────────────────────────────────────────────────────────┘
```

**新增元件 vs 前一階段**：無前一階段，直接從零開始。使用 tiktoken 或 HuggingFace tokenizers 函式庫，5 行程式碼完成。

**成本/複雜度**：工程時間 < 1 天，幾乎零成本。

**解決的問題**：
- 快速跑通整個訓練 pipeline
- 驗證模型架構（attention、FFN、layer norm）是否正確

**遺留的問題**：
- 中文 tokenization 效率低：1 個漢字平均消耗 1.5 tokens（GPT-4 tokenizer 對中文已優化），舊版可能 3–4 tokens
- 詞彙表是為英文優化的，中文字符在 embedding 空間沒有足夠容量
- 特殊 domain token（程式碼關鍵字、數學符號）沒有專門優化

---

### Phase 2：MVP — 訓練客製化 Tokenizer（10K–200K 用戶 / 生產上線）

**目標**：針對目標語言和 domain 訓練專屬 tokenizer，確保 token 效率和詞彙表品質。

```
┌─────────────────────────────────────────────────────────────────┐
│                  Phase 2 架構：客製化 BPE Tokenizer              │
│                                                                 │
│  語料庫                                                         │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐               │
│  │ 繁中文  │  │  英文  │  │  日文  │  │  代碼  │               │
│  │  30%   │  │  40%   │  │  10%   │  │  20%   │               │
│  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘               │
│      └───────────┴───────────┴───────────┘                     │
│                              │                                  │
│                              ▼                                  │
│                 ┌────────────────────────┐                      │
│                 │   SentencePiece BPE    │                      │
│                 │  訓練語料: ~100GB       │                      │
│                 │  vocab_size: 65,536    │                      │
│                 └────────────┬───────────┘                      │
│                              │                                  │
│                              ▼                                  │
│                    客製化詞彙表 + 模型檔案                        │
│                    (.model / .vocab)                            │
└─────────────────────────────────────────────────────────────────┘
```

**新增元件 vs Phase 1**：
- SentencePiece 訓練 pipeline（需要 100GB+ 代表性語料）
- 語料清洗與採樣腳本（確保語言比例正確）
- Tokenizer 品質評估套件（compression ratio、fertility rate）

**成本/複雜度**：
- 工程時間：2–4 週（語料準備 + 訓練 + 驗證）
- 計算成本：~$200–$500（100GB 語料在 32-core 機器上訓練約 4–8 小時）
- 複雜度中等：需要語料代表性保證，避免 OOV 問題

**解決的問題**：
- 中文 token 效率提升至 1.0–1.2 tokens/字（vs Phase 1 的 1.5–3.0）
- 代碼關鍵字（`def`, `class`, `import`, `SELECT`）成為單一 token
- 詞彙表與訓練語料分布一致

**遺留的問題**：
- 詞彙表大小是固定的（65K），後續擴充需要重新訓練
- 稀有語言（越南文、泰文）覆蓋率可能不足
- 特殊符號（數學公式、emoji）處理仍需人工驗證

---

### Phase 3：Scale — 企業級 Tokenizer 工程（200K–1M+ 用戶）

**目標**：生產化 tokenizer 服務，支援增量詞彙擴充、多版本管理、高吞吐量處理。

```
┌───────────────────────────────────────────────────────────────────┐
│                   Phase 3 架構：企業級 Tokenizer 系統              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                      語料管理層                              │  │
│  │  Data Lake  ──▶  Dedup  ──▶  Quality Filter  ──▶  Sampler  │  │
│  └───────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Tokenizer 訓練叢集                         │  │
│  │  Base Vocab ──▶  BPE Trainer  ──▶  Vocab Merger             │  │
│  │  (32K 字符)      (分散式)          (合併域特定詞彙)            │  │
│  └───────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  v1 Tokenizer│  │  v2 Tokenizer   │  │  v3 Tokenizer       │  │
│  │  vocab=65K   │  │  vocab=128K     │  │  vocab=128K+domain  │  │
│  └──────┬───────┘  └────────┬────────┘  └──────────┬──────────┘  │
│         └──────────────────┬┘                      │             │
│                            ▼                       │             │
│                ┌───────────────────┐               │             │
│                │  Tokenizer 服務   │◀──────────────┘             │
│                │  (gRPC / REST)    │                             │
│                │  50K QPS          │                             │
│                └───────────────────┘                             │
└───────────────────────────────────────────────────────────────────┘
```

**新增元件 vs Phase 2**：
- 版本化 tokenizer 管理（多個 checkpoint 同時服務）
- 分散式 BPE 訓練（TB 級語料，多節點並行）
- Tokenizer 服務化（gRPC 服務，50K+ QPS）
- 詞彙擴充工具（domain adaptation，新增 token 不重新訓練）
- A/B 測試框架（比較不同 tokenizer 版本對下游任務的影響）

**成本/複雜度**：
- 工程時間：1–3 個月（完整基礎設施）
- 計算成本：$5K–$20K（TB 級語料 + 分散式訓練）
- 基礎設施：Kubernetes 部署，自動擴縮，SLA 99.9%

**解決的問題**：
- 支援多版本並存（舊模型 + 新模型同時服務）
- 詞彙擴充不需要全量重新訓練
- 服務化後，tokenization 延遲穩定在 < 1ms/request

**遺留的問題**：
- 詞彙擴充後，新 token 的 embedding 需要 fine-tuning 才能有好的表示
- 跨版本相容性需要仔細管理（token ID mapping 不能衝突）

---

## 三、BPE 演算法：逐步合併的直覺

BPE（Byte Pair Encoding）源自資料壓縮演算法，核心思想是：**反覆找最常出現的相鄰符號對，合併為新符號，直到達到目標詞彙表大小**。

### BPE 訓練步驟圖

```
初始狀態（字符級別）：
語料："low low lower newest widest"
詞頻：low:5, lower:2, newest:6, widest:3

步驟 0 - 字符切分：
l-o-w (5), l-o-w-e-r (2), n-e-w-e-s-t (6), w-i-d-e-s-t (3)
         ↓
計算相鄰對頻率：
(e,s): 6+3=9  ← 最高頻
(e,w): 2+6=8
(l,o): 5+2=7
...

步驟 1 - 合併 (e,s) → es：
l-o-w (5), l-o-w-e-r (2), n-e-w-es-t (6), w-i-d-es-t (3)
         ↓
步驟 2 - 合併 (es,t) → est：
l-o-w (5), l-o-w-e-r (2), n-e-w-est (6), w-i-d-est (3)
         ↓
步驟 3 - 合併 (l,o) → lo：
lo-w (5), lo-w-e-r (2), n-e-w-est (6), w-i-d-est (3)
         ↓
步驟 4 - 合併 (lo,w) → low：
low (5), low-e-r (2), n-e-w-est (6), w-i-d-est (3)

最終詞彙表包含：l,o,w,e,r,n,s,t,i,d, lo,es,est,low,new,...
```

**BPE 的關鍵性質**：

1. **確定性**：給定相同語料和相同 vocab_size，訓練結果完全可重現
2. **貪婪合併**：每步只合併當前最高頻的對，是局部最優而非全局最優
3. **字節級 BPE**：GPT-4 使用 cl100k_base，在字節層面操作，理論上可以處理任何 Unicode 字符，不存在 OOV（Out-of-Vocabulary）問題

**BPE 推理（Encoding）**：

```python
# 偽代碼：BPE encoding
def encode(text, merge_rules):
    tokens = list(text.encode('utf-8'))  # 字節級初始化
    while True:
        pairs = get_pairs(tokens)
        # 找出在 merge_rules 中優先級最高的對
        best = min(pairs, key=lambda p: merge_rules.get(p, float('inf')))
        if best not in merge_rules:
            break
        tokens = merge(tokens, best)
    return tokens
```

時間複雜度：O(n × |merge_rules|)，實際上因為大部分 token 都是常見子詞，平均接近 O(n log n)。

---

## 四、WordPiece vs SentencePiece vs Unigram LM

### 三種主流演算法比較

**WordPiece**（BERT 系列使用）：

與 BPE 類似，但合併標準不同。BPE 最大化相鄰對的頻率，WordPiece 最大化的是語言模型的 log likelihood：

```
score(A, B) = freq(AB) / (freq(A) × freq(B))
```

這讓 WordPiece 傾向於合併「一起出現比各自出現更有意義」的符號對。BERT 的詞彙表 30,522 tokens，使用 `##` 前綴標記子詞（`playing` → `play`, `##ing`）。

**SentencePiece**（T5、LLaMA 使用）：

SentencePiece 的關鍵差異：
1. **語言無關**：不假設空格是詞邊界，直接從原始文字（含空格）訓練。空格被轉換為特殊符號 `▁`。
2. **可以使用 BPE 或 Unigram LM 作為底層演算法**
3. **完全可重現**：訓練和推理都是確定性的
4. **適合中日韓文**：不依賴空格分詞

```python
import sentencepiece as spm
# 訓練
spm.SentencePieceTrainer.train(
    input='corpus.txt',
    model_prefix='tokenizer',
    vocab_size=65536,
    character_coverage=0.9995,  # 覆蓋語料中 99.95% 的字符
    model_type='bpe',           # 或 'unigram'
    pad_id=0, unk_id=1, bos_id=2, eos_id=3
)
```

**Unigram Language Model**：

Unigram LM 從一個「足夠大」的候選詞彙表開始（通常是 BPE 訓練結果的 2–3 倍），然後反覆**移除**對整體語言模型 likelihood 影響最小的 token，直到達到目標大小。

優點：可以計算每個 token 序列的機率，支援採樣（sampling）——同一個詞可以有多種合法的切分方式，訓練時隨機採樣增加 regularization。  
缺點：訓練速度比 BPE 慢 3–5 倍。

### 演算法選型速查

| 演算法 | 代表模型 | 訓練速度 | 推理確定性 | 多語言支援 | 建議場景 |
|--------|---------|---------|-----------|-----------|---------|
| BPE | GPT 系列, RoBERTa | 快 | 是 | 中 | 英語為主，速度優先 |
| WordPiece | BERT, DistilBERT | 中 | 是 | 中 | 理解任務（分類、NER）|
| SentencePiece BPE | T5, LLaMA | 快 | 是 | 高 | 多語言生成任務 |
| Unigram LM | XLNet, mBART | 慢 | 否（採樣） | 高 | 需要機率估計的場景 |

---

## 五、詞彙表大小：32K vs 50K vs 100K 的工程取捨

詞彙表大小是 tokenizer 設計中最關鍵的超參數，牽動模型容量、訓練效率、推理速度的多重取捨。

### 詞彙表大小的影響

**Embedding 層參數量**（embedding_dim = 4096）：

| vocab_size | Embedding 參數 | 佔比（7B 模型） | 記憶體（fp16） |
|-----------|--------------|--------------|--------------|
| 32,000    | 131M         | 1.9%         | 256 MB       |
| 50,000    | 205M         | 2.9%         | 400 MB       |
| 65,536    | 268M         | 3.8%         | 524 MB       |
| 100,000   | 410M         | 5.9%         | 800 MB       |
| 128,000   | 524M         | 7.5%         | 1 GB         |

**Token 效率（Fertility Rate）**：

Fertility Rate = 原始詞數 / Token 數。越低代表越高效（同樣詞語用更少 token 表示）。

| 語言 | vocab=32K | vocab=65K | vocab=128K |
|------|----------|----------|-----------|
| 英文 | 1.3      | 1.2      | 1.1       |
| 繁中 | 1.8      | 1.4      | 1.2       |
| 日文 | 2.1      | 1.6      | 1.3       |
| 代碼 | 1.5      | 1.3      | 1.1       |

**訓練效率**：

同樣 1TB 語料，不同 vocab_size 產生的 token 數：
- vocab=32K：約 1.4T tokens
- vocab=65K：約 1.1T tokens  
- vocab=128K：約 0.9T tokens

Token 數減少 → 訓練 step 數減少 → 訓練時間縮短。128K vs 32K 可節省約 35% 訓練計算量，但 Embedding 層增大 4× 可能增加通訊開銷。

**推理延遲**：

最後一層 Linear（lm_head）的計算量與 vocab_size 成正比：
- vocab=32K：lm_head FLOPS ≈ seq_len × hidden_dim × 32K
- vocab=128K：lm_head FLOPS ≈ seq_len × hidden_dim × 128K（慢 4×）

對於長序列生成，lm_head 可以佔總推理時間的 20–40%。

### 工程決策矩陣

| 場景 | 建議 vocab_size | 理由 |
|------|---------------|------|
| 純英語模型 | 32K–50K | 英語詞彙空間覆蓋充足，再大邊際效益低 |
| 英語+代碼 | 50K–65K | 代碼有大量特殊 token，需要更多空間 |
| 多語言（< 5 種語言）| 65K–100K | 平衡各語言的 fertility rate |
| 多語言（> 10 種語言）| 100K–128K | LLaMA-3 使用 128K，Mistral 使用 32K（英語偏重） |
| 醫療/法律 domain | base + 2K–5K | 在基礎詞彙表上擴充 domain 特定 token |

---

## 六、多語言 Tokenization：中文/日文/代碼的挑戰

### 中文的特殊性

中文沒有空格作為天然詞邊界。BPE 在字節層面操作時，一個漢字佔 3 個 UTF-8 字節（0xE4 0xB8 0x00 範圍），字節級 BPE 會先把這 3 個字節合併為一個 token，再進一步合併常見字序列。

**效率對比（繁體中文，2026 年主流 tokenizer）**：

| Tokenizer | 示例句子 | Token 數 | 每字 tokens | 備注 |
|-----------|---------|---------|-----------|------|
| cl100k (GPT-4) | 深度學習模型訓練需要大量計算資源 | 18 | 1.5 | 優化過中文 |
| LLaMA-2 (32K) | 深度學習模型訓練需要大量計算資源 | 35 | 2.9 | 中文支援差 |
| LLaMA-3 (128K) | 深度學習模型訓練需要大量計算資源 | 16 | 1.3 | 大幅改善 |
| Qwen tokenizer | 深度學習模型訓練需要大量計算資源 | 13 | 1.1 | 中文最佳化 |
| 字節級（無 BPE）| 深度學習模型訓練需要大量計算資源 | 36 | 3.0 | 最差效率 |

**實際影響計算（GPT-4 API 費用對比）**：

- 1M 個漢字的文件
- cl100k：≈ 1.5M tokens，費用 $1.5（$1/1M tokens）
- LLaMA-2 style：≈ 3M tokens，費用 $3（貴 2×）
- Qwen style：≈ 1.1M tokens，費用 $1.1（最便宜）

### 日文的複雜性

日文混用三種書寫系統：平假名（ひらがな）、片假名（カタカナ）、漢字（かんじ）。設計良好的 tokenizer 應該：
- 把常見假名序列合並（「です」「ます」作為整體 token）
- 把高頻漢字詞彙合並（「日本語」作為單一 token）
- 處理外來語片假名（「コンピューター」）

### 代碼的特殊挑戰

```
Python 代碼 token 效率分析：

def calculate_loss(logits, labels, ignore_index=-100):
    return F.cross_entropy(logits.view(-1, logits.size(-1)),
                           labels.view(-1),
                           ignore_index=ignore_index)

代碼特點：
- 縮排（空格）消耗 token：4 個空格 = 1–2 tokens
- 底線命名法：calculate_loss 可能是 1 token（常見函數）
                              也可能是 3 tokens（calculate, _, loss）
- 括號、逗號：各消耗 1 token
- 數字：每個 digit 可能是 1 token（影響算術能力）

代碼優化的 tokenizer 特點：
- 縮排保留完整（4 spaces → 1 token）
- 常見函數名/關鍵字作為整體 token
- 數字處理：1–3 位數字通常是整體 token
```

### 多語言 Token 效率總結表

| 內容類型 | 高效 tokenizer | 低效 tokenizer | 差距 |
|---------|--------------|--------------|------|
| 英文散文 | 1.1–1.3 tokens/word | 1.3–1.5 tokens/word | 1.2× |
| 繁體中文 | 1.0–1.3 tokens/字 | 2.0–3.5 tokens/字 | 2.5× |
| 日文混合 | 1.2–1.5 tokens/字 | 2.5–4.0 tokens/字 | 2.5× |
| Python 代碼 | 3–4 chars/token | 2–3 chars/token | 1.3× |
| 數學公式 | 1.5–2 tokens/符號 | 3–5 tokens/符號 | 2× |

---

## 七、特殊 Token 設計：[BOS]/[EOS]/[PAD] 的工程意義

特殊 token 是 tokenizer 的「控制訊號」，它們不代表自然語言內容，而是告訴模型當前的語境邊界和任務類型。

### 核心特殊 Token

**[BOS]（Beginning of Sequence）**：
- Token ID 通常為 1 或 2（低 ID 便於識別）
- 作用：告訴模型「新的序列從這裡開始」
- 在 decoder-only 模型中，BOS 是生成的起點（cold start prompt）
- LLaMA 系列使用 `<s>`（ID=1）

**[EOS]（End of Sequence）**：
- 作用：告訴模型「序列到這裡結束，停止生成」
- 訓練時：每個訓練樣本末尾都加 EOS，教模型學會何時停止
- 推理時：生成到 EOS 即終止
- LLaMA 使用 `</s>`（ID=2）；GPT 系列使用 `<|endoftext|>`

**[PAD]（Padding）**：
- 作用：把不同長度的序列填充到相同長度，使 batch 計算成為可能
- 工程細節：PAD token 對應的 attention mask = 0，模型不計算 PAD 位置的 loss
- 位置：通常是右填充（right-padding），但某些場景（KV cache 預填充）需要左填充
- 常見錯誤：忘記設置 attention mask，導致模型把 PAD 當成真實 token 計算

**[UNK]（Unknown）**：
- 字節級 BPE 理論上不需要 UNK（任何字符都可以用字節表示）
- SentencePiece 需要 UNK 處理 character_coverage 之外的罕見字符
- 出現大量 UNK 是 tokenizer 與語料不匹配的警告訊號

### Chat/Instruction 模型的特殊 Token

現代 instruction-tuned 模型需要更多特殊 token 來區分對話角色：

```
LLaMA-3 / LLaMA-3.1 格式：
<|begin_of_text|>                    ← BOS
<|start_header_id|>system<|end_header_id|>
You are a helpful assistant.
<|eot_id|>                           ← End of Turn
<|start_header_id|>user<|end_header_id|>
What is tokenization?
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
Tokenization is...
<|eot_id|>
<|end_of_text|>                      ← EOS
```

**工程注意事項**：

1. 特殊 token 在訓練語料中必須**不出現在正常文字裡**，否則模型無法區分「控制訊號」和「內容」
2. 特殊 token 的 embedding 需要**特別初始化**（不能用隨機初始化，通常從相鄰 token 的 embedding 均值初始化）
3. `tokenizer.chat_template` 格式必須與訓練時完全一致，否則推理時角色邊界混亂

### Token ID 分配策略

```
ID 0    : [PAD]      ← 0 是預設的「空值」，方便 mask
ID 1    : [BOS]/<s>  ← 序列起始
ID 2    : [EOS]/</s> ← 序列終止
ID 3    : [UNK]      ← 未知字符
ID 4–N  : 特殊控制 token（<system>, <user>, <assistant>...）
ID N+1– : 正常詞彙 token（按頻率或合併順序排列）
```

---

## 八、為什麼選 X 不選 Y（六個核心決策）

### 決策 1：BPE vs WordPiece

| 選擇 | 選 BPE 的理由 | 不選 WordPiece 的理由 |
|------|------------|-------------------|
| 合併標準 | 頻率最高的對，直覺簡單，訓練快 | 需要計算 likelihood，訓練慢 30% |
| 確定性 | 完全確定性 | 也是確定性，但需要 vocab 初始化步驟 |
| 工具支援 | tiktoken、sentencepiece 均支援 | 主要是 HuggingFace tokenizers |
| 生態 | GPT 系列、LLaMA 系列廣泛使用 | 主要是 BERT 系列（理解任務） |
| 可解釋性 | 合併規則可直接查看 | 相同 |

**Flip Condition**：當目標是訓練 BERT-style encoder（MLM 任務），或需要與 HuggingFace BERT 生態深度整合時，選 WordPiece。

---

### 決策 2：SentencePiece vs 自行實作 BPE

| 選擇 | 選 SentencePiece 的理由 | 不選自行實作的理由 |
|------|----------------------|----------------|
| 多語言 | 語言無關，空格作為字符處理 | 自行實作需要額外處理 CJK |
| 可靠性 | 成熟函式庫，Google Brain 維護多年 | 自行實作 BPE 有很多邊界情況 |
| 訓練速度 | C++ 核心，TB 級語料數小時完成 | Python 實作比 C++ 慢 20–50× |
| 可重現 | 給定相同語料完全可重現 | 需要自行保證 |
| 特殊 token | 內建支援，API 清晰 | 需要自行設計 |

**Flip Condition**：當需要超細粒度控制 token 邊界（例如醫療影像報告的特殊格式）、或需要與既有系統深度整合時，自行實作提供最大靈活性。代價是 3–6 個月工程時間。

---

### 決策 3：vocab_size=65K vs 128K（多語言模型）

| 選擇 | 選 65K 的理由 | 不選 128K 的理由 |
|------|------------|--------------|
| Embedding 大小 | 節省 ~400MB（fp16）| 額外 400MB 不影響 7B+ 模型 |
| lm_head 速度 | lm_head 快 2× | 對大模型影響 < 5% 推理時間 |
| 多語言效率 | 覆蓋英中日代碼已足夠 | 128K 對 10+ 語言才有明顯優勢 |
| 訓練簡單 | 較少稀有 token 需要覆蓋 | 需要更多語料保證稀有 token 訓練充分 |

**Flip Condition**：當目標語言超過 10 種、或包含覆蓋率低的語言（阿拉伯文、印度語系）時，128K 的效率優勢超過其成本。LLaMA-3 從 32K → 128K 的升級，使中文效率從 2.9 tokens/字降至 1.3 tokens/字。

---

### 決策 4：字節級 BPE vs 字符級 BPE

| 選擇 | 選字節級（Byte-level BPE）的理由 | 不選字符級的理由 |
|------|-------------------------------|--------------|
| OOV 問題 | 永不出現 OOV（任何輸入都可編碼）| 字符級遇到罕見字符產生 UNK |
| 詞彙表效率 | 初始詞彙表只需 256 字節 | 字符級需要覆蓋 Unicode 14 萬+ 字符 |
| 最壞情況 | 最差 1 字符 3 tokens（3 字節 UTF-8）| 最差 1 字符 1 token，但 UNK 破壞語義 |
| 相容性 | GPT 系列、LLaMA-3 採用 | 較舊的方法，BERT 部分採用 |

**Flip Condition**：當處理的語言字符集有限（例如純英文，只有 ASCII），字符級 BPE 在 token 效率上稍好，且沒有 OOV 問題（ASCII 128 字符全部覆蓋）。

---

### 決策 5：訓練語料中語言比例 30%中文 vs 50%中文

| 選擇 | 選 30% 中文 / 40% 英文的理由 | 50%+ 中文的問題 |
|------|--------------------------|--------------|
| 詞彙分配 | 英文詞彙獲得充分的 BPE 合併機會 | 英文常見詞彙合並機會減少，英文效率下降 |
| 語言平衡 | 符合多語言模型的訓練目標 | 模型可能偏向中文，英文推理能力弱化 |
| 遷移學習 | 英文預訓練知識豐富，作為橋梁語言 | 英文比例過低損失大量世界知識 |
| 代碼 | 20% 代碼確保 tokenizer 對代碼友好 | 代碼比例不足，代碼任務效能下降 |

**Flip Condition**：當模型目標是**中文為主的專用模型**（例如繁中客服機器人、中文法律 AI），中文比例可以提高到 60–70%，英文降到 20–30%。Qwen、ERNIE 系列的中文比例通常在 50%+。

---

### 決策 6：Tiktoken（OpenAI 格式） vs SentencePiece（Google/Meta 格式）

| 選擇 | 選 Tiktoken 的理由 | 選 SentencePiece 的理由 |
|------|-----------------|----------------------|
| 速度 | Rust 實作，比 Python HF tokenizers 快 5–10× | C++ 實作，也很快 |
| 生態 | OpenAI 模型完全相容 | LLaMA、T5、PaLM 生態 |
| 格式 | .tiktoken 格式（base64 編碼） | .model + .vocab 格式 |
| 擴充性 | 不支援官方的增量詞彙擴充 | 可以 fine-tune 詞彙表 |
| 開源 | tiktoken 函式庫開源，但 cl100k 詞彙表使用條款需注意 | 完全開源，商用友好 |

**Flip Condition**：若產品是 OpenAI API 的 wrapper、或需要精確計算 token 費用預算，用 Tiktoken 確保 token 數一致。若是訓練自己的模型、或需要詞彙表修改，用 SentencePiece。

---

## 九、系統效應：Token 效率 / 上下文利用率 / 訓練成本對比

### Before vs After：優化 Tokenizer 前後的系統指標

| 指標 | Before（LLaMA-2 style, 32K vocab）| After（客製化 128K vocab）| 改善幅度 |
|------|----------------------------------|--------------------------|---------|
| 中文 tokens/字 | 2.9 | 1.3 | **55% 減少** |
| 同等 context 可容納中文字數 | 32K tokens → 11K 字 | 32K tokens → 24K 字 | **2.2× 提升** |
| 1TB 中文語料產生 token 數 | 2.9T tokens | 1.3T tokens | **55% 減少** |
| 預訓練總計算量（FLOPs） | 100%（基準）| 52% | **節省 48%** |
| 預訓練費用估算（A100 集群）| $8M | $4.2M | **節省 $3.8M** |
| 推理延遲（100 字中文輸入）| 290ms | 130ms | **55% 加速** |
| API 成本（1M 中文字符）| $2.90 | $1.30 | **節省 55%** |
| lm_head 推理時間佔比 | 8%（32K）| 22%（128K）| **增加 14%** |
| 整體推理速度 | 100%（基準）| 122%（快）| **22% 加速**（token減少>lm_head增加）|

### Context Window 利用率

```
GPT-4 style (128K context window) 可以容納：

英文小說：
  128K tokens ÷ 1.3 tokens/word ≈ 98,000 words ≈ 350 頁

繁體中文（低效 tokenizer）：
  128K tokens ÷ 2.9 tokens/字 ≈ 44,000 字 ≈ 中篇小說一半

繁體中文（高效 tokenizer）：
  128K tokens ÷ 1.3 tokens/字 ≈ 98,000 字 ≈ 完整中篇小說

Python 代碼庫：
  128K tokens × 3.5 chars/token ≈ 448,000 字符 ≈ ~12,000 行代碼
```

### Tokenizer 版本升級的業務影響

| 場景 | 改善前痛點 | 改善後效果 | 具體數字 |
|------|----------|----------|---------|
| 長文摘要 | 中文文件因 token 過多被截斷 | 完整處理長文件 | 可處理文件長度 2.2× |
| RAG 系統 | 每個 chunk 可容納的中文字數少 | chunk 包含更多上下文 | 召回品質提升 15–25% |
| 多輪對話 | 歷史對話快速消耗 context | 更長的對話歷史 | 可保留對話輪數 2× |
| 代碼生成 | 長函數被截斷 | 完整函數在 context 內 | Bug 率下降 20% |

---

## 十、面試答題要點

**面試官問**：「你的團隊正在從零預訓練一個 30B 多語言 LLM，目標包含英中日文和代碼。請說明你會如何設計 tokenizer，詞彙表要多大？選哪種演算法？分三個階段說明。」

> *「我會以三個階段遞進。Phase 1 POC 階段，直接用 tiktoken cl100k_base，1 天內跑通訓練 pipeline，先驗證模型架構正確性，這時候 tokenizer 品質不是瓶頸。Phase 2 MVP 階段，用 SentencePiece 訓練客製化 BPE tokenizer：語料比例設為 40% 英文、30% 繁中、10% 日文、20% 代碼，vocab_size 選 128K — 因為四種語言的 fertility rate 差異大，128K 能讓中文從 2.9 tokens/字降到 1.3 tokens/字，同樣 context window 可容納的中文字數多 2.2 倍，預訓練費用節省約 $3.8M。Phase 3 Scale 階段，把 tokenizer 服務化，支援 50K QPS 的 gRPC 服務，同時建立版本管理機制，讓不同版本模型可以並存服務。關鍵決策是選 SentencePiece BPE 而非字符級，因為字節級 BPE 永不出現 OOV，任何 Unicode 輸入都能處理；選 128K 而非 32K，因為多語言場景下 token 效率收益超過 lm_head 增大的推理成本（整體推理仍快 22%）。」*

---

## 十一、系列導航

← [Phase 9 系列 — AI 工程從零開始](/tags/ai/) | [Phase 10 Part 2：Embedding 層設計 →](/posts/ai-eng-from-scratch-phase10-part2-embedding-zh/)

---

**延伸閱讀**：

- [Tiktoken 原始碼](https://github.com/openai/tiktoken)：理解字節級 BPE 的生產實作
- [SentencePiece 論文](https://arxiv.org/abs/1808.06226)：Kudo & Richardson, 2018
- [Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909)：原始 BPE 論文（Sennrich et al., 2016）
- Karpathy 的 minBPE：從零實作 BPE 的最佳教學資源
