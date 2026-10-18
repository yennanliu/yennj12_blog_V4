---
title: "AI 工程從零開始｜Phase 10 Part 1：從頭構建 LLM — Tokenization 的工程藝術"
date: 2026-06-21T18:00:00+08:00
draft: false
weight: 19
description: "深入解析 LLM Tokenization：BPE/WordPiece/SentencePiece 演算法、詞彙表大小的工程取捨、多語言 Token 效率與 Tiktoken 生產實作"
categories: ["all", "ai", "engineering"]
tags: ["AI", "LLM", "Tokenization", "BPE", "SentencePiece", "Vocabulary", "RKK", "ai-eng-from-scratch"]
authors: ["yen"]
readTime: "15 min"
series: ["ai-eng-from-scratch"]
---

> 大多數人以為 Tokenization 只是「把文字切成小段」，隨便選一個 tokenizer 接上模型就好。  
> 現實是：詞彙表大小決定了模型容量與訓練成本，token 邊界影響了推理能力，  
> 多語言效率直接決定非英語使用者的 API 費用與延遲，  
> 一個錯誤的 tokenization 決策，可以讓整個預訓練白費。

---

這篇給已經會呼叫 `tokenizer.encode()`、但沒想過詞彙表大小會改變模型容量與訓練帳單的工程師看。讀完你會能手動跑一遍 BPE 的合併步驟、分辨 BPE／WordPiece／SentencePiece／Unigram 的差異、量化 vocab_size 對 embedding 參數、lm_head 延遲與中文 token 效率的影響，並能為一個「英文、繁中、日文加 Python/SQL」的多語言預訓練模型，有依據地決定詞彙表大小、演算法與語料比例。

---

## 一、核心問題：Tokenization 為什麼是 LLM 的第一道關卡

Tokenization 是 LLM pipeline 的第一步，也是最容易被低估的一步。它做的事情看似簡單：把原始文字轉換成整數序列（token IDs），讓模型能夠處理。但這個轉換過程中埋藏了大量工程決策，每一個都有深遠影響。

**為什麼 Tokenization 很重要？**

1. **模型容量分配**：詞彙表大小直接決定 Embedding 層的參數量。vocab_size=50K、embedding_dim=4096 時，Embedding 層就佔了 50K × 4096 × 2 bytes ≈ 400MB，相當於 7B 模型參數的約 3%（50K × 4096 = 205M ÷ 7B = 2.9%；vocab 放大到 128K 則是 7.5%，見 §六的表）。

2. **序列長度放大器**：同樣一段中文，GPT-4 的 tokenizer（cl100k_base；GPT-4o 之後的 OpenAI 模型改用約 200K 詞彙的 o200k_base）平均每個漢字消耗約 1.5 tokens，而設計不良的 tokenizer 可能消耗 3–4 tokens（逐字節切割）。context window 128K tokens，有效利用率差了 2–3 倍。

3. **訓練成本乘數**：預訓練是以 token 數計算的。同樣 1TB 的 UTF-8 中文語料約 3,300 億個字（1 TB ÷ 3 bytes/字），每字 1.3 token 的 tokenizer 產生約 0.43T tokens，每字 2.9 token 的產生約 0.97T tokens，訓練計算量差 2.2 倍；以 70B 模型估算（6·N·D，A100 $2/GPU-h、MFU 45%），費用差約 $0.9M（$1.6M vs $0.7M）。

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

## 二、何時該升級：從現成 tokenizer 到客製化詞彙表的觸發條件

從現成的 tokenizer 起步——tiktoken 的 cl100k_base 或 Llama 3 的 128K 詞彙表——用 5 行程式碼就能把整條訓練 pipeline 跑通，驗證 attention、FFN、layer norm 都沒接錯。該不該訓練自己的 tokenizer，不看用戶數，看**在你的語料上實測的 tokens/字**：如果目標語言的 fertility 明顯差於英文（中文超過 1.5 tokens/字，§六的對照表），或是 `def`、`SELECT` 這類 domain 關鍵字被切成好幾個 token，就值得抽一份代表性語料（約 100GB、依目標語言比例採樣）訓練 SentencePiece BPE，並以 compression ratio 與 fertility 當驗收指標；這是 2–4 週的工程時間與幾百美元的計算，相對預訓練本身可以忽略。

第二道門檻是**詞彙表訓練完就固定了**：擴充詞彙代表新 token 的 embedding 要重新 fine-tune 才有可用表示，跨版本的 token ID 映射也不能衝突。所以 domain 覆蓋不足時先走「base + 2K–5K domain token」的擴充路線（§五的決策矩陣），只有語言比例本身改變時才全量重訓。tokenization 本身不需要獨立的服務——它跑在訓練資料管線與推理伺服器內部，要做的是版本化與 A/B 比較，而不是另一個微服務。

| 從 | 到 | 觸發訊號 |
|----|----|----------|
| 現成 tokenizer（cl100k / Llama 3 128K） | 在自己語料上訓練的 SentencePiece BPE（如 65K） | 目標語言 fertility 明顯差於英文（中文 > 1.5 tokens/字）；domain 關鍵字被切碎；訓練 token 數因此膨脹 |
| 固定 65K 詞彙表 | base + domain token 擴充（2K–5K） | 新領域（醫療／法律／特定程式語言）出現大量 UNK 或多 token 切分，但語言比例未變 |
| 單一 tokenizer 版本 | 版本化管理 + 下游任務 A/B 比較 | 多個模型世代同時服務；擴充後的 token ID 映射需要跨版本相容 |

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
(w,e): 2+6=8
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
3. **字節級 BPE**：GPT-4 使用 cl100k_base（GPT-4o 起為 o200k_base），在字節層面操作，理論上可以處理任何 Unicode 字符，不存在 OOV（Out-of-Vocabulary）問題

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

Fertility Rate = Token 數 / 原始詞數（平均每個詞被切成幾個 token）。越低代表越高效（同樣詞語用更少 token 表示），1.0 表示每個詞剛好一個 token。

| 語言 | vocab=32K | vocab=65K | vocab=128K |
|------|----------|----------|-----------|
| 英文 | 1.3      | 1.2      | 1.1       |
| 繁中 | 1.8      | 1.4      | 1.2       |
| 日文 | 2.1      | 1.6      | 1.3       |
| 代碼 | 1.5      | 1.3      | 1.1       |

**訓練效率**：

同樣 1TB 以中文為主的語料（約 3,300 億字），不同 vocab_size 產生的 token 數（示意估算）：
- vocab=32K：約 0.47T tokens
- vocab=65K：約 0.37T tokens  
- vocab=128K：約 0.30T tokens

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
| 多語言（> 10 種語言）| 100K–128K | LLaMA-3 使用 128K；Mistral 早期模型使用 32K，Mistral NeMo 起改用約 131K 的 Tekken tokenizer |
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

> 上表 token 數與每字 tokens 為示意估算（例句 16 字，「每字 tokens」欄反映一般中文文本的概略平均，並非由例句換算），非逐一實測；實際數字請用各模型的 tokenizer 對自己的語料實測。

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

## 八、為什麼選 X 不選 Y（四個核心決策）

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

### 決策 2：vocab_size=65K vs 128K（多語言模型）

| 選擇 | 選 65K 的理由 | 不選 128K 的理由 |
|------|------------|--------------|
| Embedding 大小 | 節省 ~400MB（fp16）| 額外 400MB 不影響 7B+ 模型 |
| lm_head 速度 | lm_head 快 2× | 對大模型影響 < 5% 推理時間 |
| 多語言效率 | 覆蓋英中日代碼已足夠 | 128K 對 10+ 語言才有明顯優勢 |
| 訓練簡單 | 較少稀有 token 需要覆蓋 | 需要更多語料保證稀有 token 訓練充分 |

**Flip Condition**：當目標語言超過 10 種、或包含覆蓋率低的語言（阿拉伯文、印度語系）時，128K 的效率優勢超過其成本。LLaMA-3 從 32K → 128K 的升級，使中文效率從 2.9 tokens/字降至 1.3 tokens/字。

---

### 決策 3：字節級 BPE vs 字符級 BPE

| 選擇 | 選字節級（Byte-level BPE）的理由 | 不選字符級的理由 |
|------|-------------------------------|--------------|
| OOV 問題 | 永不出現 OOV（任何輸入都可編碼）| 字符級遇到罕見字符產生 UNK |
| 詞彙表效率 | 初始詞彙表只需 256 字節 | 字符級需要覆蓋 Unicode 14 萬+ 字符 |
| 最壞情況 | 最差 1 字符 3 tokens（3 字節 UTF-8）| 最差 1 字符 1 token，但 UNK 破壞語義 |
| 相容性 | GPT 系列、LLaMA-3 採用 | 較舊的方法，BERT 部分採用 |

**Flip Condition**：當處理的語言字符集有限（例如純英文，只有 ASCII），字符級 BPE 在 token 效率上稍好，且沒有 OOV 問題（ASCII 128 字符全部覆蓋）。

---

### 決策 4：Tiktoken（OpenAI 格式） vs SentencePiece（Google/Meta 格式）

| 選擇 | 選 Tiktoken 的理由 | 選 SentencePiece 的理由 |
|------|-----------------|----------------------|
| 速度 | Rust 實作，官方 README 稱比 HF tokenizers 快 3–6× | C++ 實作，也很快 |
| 生態 | OpenAI 模型完全相容 | LLaMA、T5、PaLM 生態 |
| 格式 | .tiktoken 格式（base64 編碼） | .model + .vocab 格式 |
| 擴充性 | 不支援官方的增量詞彙擴充 | 可以 fine-tune 詞彙表 |
| 開源 | tiktoken 函式庫開源（MIT 授權） | 完全開源，商用友好 |

**Flip Condition**：若產品是 OpenAI API 的 wrapper、或需要精確計算 token 費用預算，用 Tiktoken 確保 token 數一致。若是訓練自己的模型、或需要詞彙表修改，用 SentencePiece。

---

## 九、系統效應：Token 效率 / 上下文利用率 / 訓練成本對比

### Before vs After：優化 Tokenizer 前後的系統指標

| 指標 | Before（LLaMA-2 style, 32K vocab）| After（客製化 128K vocab）| 改善幅度 |
|------|----------------------------------|--------------------------|---------|
| 中文 tokens/字 | 2.9 | 1.3 | **55% 減少** |
| 同等 context 可容納中文字數 | 32K tokens → 11K 字 | 32K tokens → 24K 字 | **2.2× 提升** |
| 1TB 中文語料（≈ 3,300 億字）產生 token 數 | 0.97T tokens | 0.43T tokens | **55% 減少** |
| 預訓練總計算量（FLOPs，∝ token 數） | 100%（基準）| 45% | **節省 55%** |
| 預訓練費用估算（70B 模型，6·N·D，A100 $2/GPU-h、MFU 45%）| ~$1.6M | ~$0.7M | **節省 ~$0.9M** |
| 推理延遲（100 字中文輸入）| 290ms | 130ms | **55% 加速** |
| API 成本（1M 中文字符）| $2.90 | $1.30 | **節省 55%** |
| lm_head 推理時間佔比 | 8%（32K）| 22%（128K）| **增加 14%** |
| 整體推理速度 | 100%（基準）| 122%（快）| **22% 加速**（token減少>lm_head增加）|

*示意估算，非實測數據*

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

*示意估算，非實測數據*

---

## 十、系列導航

← [Phase 9：強化學習基礎 — RLHF 與遊戲 AI 的根基](/posts/ai-eng-from-scratch-phase9-part1-rl-fundamentals-zh/) | [Phase 10 Part 2：LLM 預訓練 — 萬億 Token 的工程挑戰 →](/posts/ai-eng-from-scratch-phase10-part2-pretraining-zh/)

---

**延伸閱讀**：

- [Tiktoken 原始碼](https://github.com/openai/tiktoken)：理解字節級 BPE 的生產實作
- [SentencePiece 論文](https://arxiv.org/abs/1808.06226)：Kudo & Richardson, 2018
- [Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909)：原始 BPE 論文（Sennrich et al., 2016）
- Karpathy 的 minBPE：從零實作 BPE 的最佳教學資源
