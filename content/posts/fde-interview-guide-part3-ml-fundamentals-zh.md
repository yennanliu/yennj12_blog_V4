---
title: "FDE 面試準備指南（三）：你不能忽略的 ML 基礎"
date: 2026-05-30T11:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，整理 FDE 面試中仍然高頻的傳統 ML / AI 基礎知識，包含 Transformer、Embedding、評估指標與 Fine-tuning"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Machine Learning", "Transformer", "Embedding", "Evaluation", "Fine-tuning", "Interview", "Google"]
authors: ["yen"]
readTime: "13 min"
---

> 有人覺得 FDE 只需要會包 API。  
> 這個判斷在面試中會死得很難看。  
> 基礎不紮實，一旦系統出問題，你沒有能力診斷。

> **閱讀建議：** 這篇涵蓋面試必備的 ML 基礎概要。想要更完整的版本，請參考深度篇：[第八篇（ML 完整版）](/posts/fde-interview-guide-part8-ml-fundamentals-zh/) 和 [第九篇（LLM 核心）](/posts/fde-interview-guide-part9-llm-core-zh/)。

---

## 這篇要解決什麼問題

很多準備 FDE 面試的人花大量時間看 LangChain、LangGraph，卻忘了面試官通常會先問一些「基礎確認題」。

這些題目不難，但如果你含糊其辭，面試官對你的印象就會打折扣。

這篇整理的是：**必知、不能答錯、而且在實際工作中真的用得到**的 ML 基礎。

---

## Transformer 架構：你要能解釋的程度

不需要默背整個論文，但你要能解釋清楚幾個核心概念。

### Self-Attention：為什麼重要

傳統 RNN 的問題：**遠距離依賴很難學**。

句子越長，開頭的資訊到句尾就已經被稀釋掉了。

Self-Attention 的解法：**每個 token 直接和所有其他 token 計算相關性**，不管距離。

```
句子：「這家公司的 CEO 昨天宣布了一項重大決策」

Self-Attention 讓「決策」這個詞能直接「看到」「CEO」，
不需要一步步從前面傳遞資訊。
```

數學形式（面試可能會問）：

```
Attention(Q, K, V) = softmax(QK^T / √d_k) × V

Q = Query（當前 token 在問什麼）
K = Key（其他 token 能提供什麼）
V = Value（實際要傳遞的資訊）
d_k = Key 的維度（做縮放，避免數值太大）
```

不需要手推，但要知道 Q/K/V 各自的意思。

### Positional Encoding：為什麼需要

Self-Attention 本身**沒有位置概念**。`「我愛你」`和`「你愛我」`裡的「愛」，在純 Attention 裡是一樣的。

所以要加上位置編碼，告訴模型每個 token 在句子的哪個位置。

```python
import numpy as np

def positional_encoding(seq_len, d_model):
    positions = np.arange(seq_len)[:, np.newaxis]
    dims = np.arange(d_model)[np.newaxis, :]
    
    angles = positions / np.power(10000, (2 * (dims // 2)) / d_model)
    
    # 偶數維度用 sin，奇數維度用 cos
    pe = np.where(dims % 2 == 0, np.sin(angles), np.cos(angles))
    return pe
```

### 三種 Transformer 變體

| 架構 | 代表模型 | 適合任務 |
|------|----------|----------|
| Encoder only | BERT | 文本分類、NER、相似度 |
| Decoder only | GPT, Claude, Gemini | 文本生成、對話 |
| Encoder-Decoder | T5, BART | 翻譯、摘要、問答 |

**FDE 最常用的是 Decoder only**（因為你在用的 API 幾乎都是這類）。

---

## Embedding：你要能解釋到這個層次

### 什麼是 Embedding

把高維稀疏的資料（文字、圖片、使用者 ID）映射到**低維稠密向量**，讓機器能計算「相似度」。

```
「貓」 → [0.23, -0.45, 0.87, ...]  # 768 維
「狗」 → [0.25, -0.43, 0.85, ...]  # 和「貓」很接近
「汽車」 → [-0.67, 0.12, -0.34, ...]  # 和「貓」很遠
```

### 常用 Embedding 模型

| 模型 | 維度 | 特點 |
|------|------|------|
| text-embedding-004（Google） | 768 | 多語言、生產推薦 |
| text-embedding-3-small（OpenAI） | 1536 | 成本低 |
| all-MiniLM-L6-v2（開源） | 384 | 輕量、適合本地部署 |
| multilingual-e5-large（開源） | 1024 | 多語言效果好 |

### 相似度計算

```python
import numpy as np

def cosine_similarity(vec_a, vec_b):
    return np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

# 範圍：-1 到 1
# 1  = 完全相同
# 0  = 完全無關
# -1 = 完全相反

sim = cosine_similarity(embedding_cat, embedding_dog)
# → 0.87（很相似）
```

---

## 評估指標：必須能流利解釋

這是基礎中的基礎，面試官可能隨時插進來問。

### Precision vs Recall

用搜尋引擎來理解：

```
查詢後，搜尋引擎返回 10 篇文章
  - 其中 7 篇是真正相關的（Precision = 7/10 = 70%）

資料庫裡有 20 篇相關文章
  - 搜尋引擎找到了其中 7 篇（Recall = 7/20 = 35%）
```

**Precision**：你找到的東西，有多少是對的？

**Recall**：所有對的東西，你找到了幾個？

### F1 Score

Precision 和 Recall 的調和平均：

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

當你不確定哪個更重要時，看 F1。

### RAG 場景下的特殊指標

在 RAG 系統裡，你需要另外關注：

```python
# RAGAS 框架的四個核心指標

# 1. Faithfulness（忠實度）
# 回答是否完全基於查到的文件，沒有幻覺？
# 高 = 好

# 2. Answer Relevancy（回答相關性）
# 回答是否直接回應了問題？
# 高 = 好

# 3. Context Precision（上下文精確度）
# 查到的文件，有多少是真正有用的？
# 高 = 好

# 4. Context Recall（上下文召回率）
# 回答問題需要的資訊，有多少被查出來了？
# 高 = 好
```

---

## Overfitting vs Underfitting

基本概念，但面試官喜歡問「在 LLM / RAG 場景下，這兩個問題怎麼表現？」

### 傳統 ML 的版本

```
Underfitting（欠擬合）：模型太簡單
→ 訓練集準確率低，測試集也低

Overfitting（過擬合）：模型記住訓練資料了
→ 訓練集準確率高，測試集卻低
```

### LLM / Fine-tuning 的版本

**Underfitting**：Fine-tuning 資料太少，模型沒學到特定格式或知識。

**Overfitting**：Fine-tuning 太多 epoch，模型把訓練資料背起來了，但泛化能力變差。

```python
# Fine-tuning 時監控 Validation Loss
# 如果 train_loss 持續下降但 val_loss 開始上升，就是 overfitting

for epoch in range(max_epochs):
    train_loss = train_one_epoch(model, train_data)
    val_loss = evaluate(model, val_data)
    
    print(f"Epoch {epoch}: train={train_loss:.3f}, val={val_loss:.3f}")
    
    if val_loss > best_val_loss * 1.05:  # val loss 上升 5%
        print("Early stopping!")
        break
    
    best_val_loss = min(val_loss, best_val_loss)
```

**Early Stopping** 是解決 Fine-tuning overfitting 的標準做法。

---

## Fine-tuning 核心知識

FDE 需要知道什麼時候建議客戶 Fine-tune，而不是用 RAG。

### Fine-tuning 適合的場景

1. **固定的輸出格式**：希望模型永遠以特定 JSON 格式回答
2. **特定語氣和風格**：公司品牌語調
3. **高度專業的領域知識**：法律條文解析、醫療編碼
4. **任務不需要知識更新**：文字分類、情感分析

### LoRA：現在最主流的 Fine-tuning 方法

全量 Fine-tuning 要改動所有參數，成本極高。

LoRA（Low-Rank Adaptation）的做法：**不動原始參數，只訓練一組很小的矩陣**。

```python
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM

base_model = AutoModelForCausalLM.from_pretrained("google/gemma-2-9b")

lora_config = LoraConfig(
    r=16,              # Rank：越小越省記憶體，但表達能力越弱
    lora_alpha=32,     # 縮放係數，通常設為 r 的 2 倍
    target_modules=["q_proj", "v_proj"],  # 只訓練 attention 的 Q 和 V
    lora_dropout=0.1,
    task_type="CAUSAL_LM"
)

model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()
# trainable params: 8,388,608 / 9,241,835,520 → 只有 0.09%！
```

### 面試常問的 trade-off

| | LoRA Fine-tuning | Full Fine-tuning | RAG |
|--|--|--|--|
| 記憶體需求 | 低 | 極高 | 低 |
| 訓練成本 | 中 | 高 | 無 |
| 知識可更新 | 否 | 否 | 是 |
| 推理速度 | 快 | 快 | 稍慢（查資料庫） |
| 引用來源 | 否 | 否 | 是 |

---

## Tokenization：知道這些就夠

### 為什麼 LLM 用 token 而不是字元

字元集太大（漢字就幾萬個），直接建詞表太浪費。

主流做法是 **BPE（Byte Pair Encoding）**：把常見的字元組合合併成一個 token。

```
中文例子：
「台灣」可能是一個 token
「北部」可能被切成「北」和「部」兩個 token

英文例子：
"running" → ["run", "ning"]
"tokenization" → ["token", "ization"]
```

### 重要的 token 知識

```python
import tiktoken  # OpenAI 的 tokenizer

enc = tiktoken.get_encoding("cl100k_base")

# 計算 token 數
text = "Hello, how are you?"
tokens = enc.encode(text)
print(len(tokens))  # → 5

# 中文通常 1 個字 ≈ 1.5-2 個 token
chinese_text = "今天天氣如何？"
print(len(enc.encode(chinese_text)))  # → 約 8-10
```

**為什麼要知道 token 數？**

1. API 計費按 token 計算
2. Context window 有上限（例如 Claude 200k tokens）
3. Chunk size 的設計要考慮 token，不是字元數

---

## Temperature 和 Sampling

面試官有時候會問：「什麼情況下你會調整 Temperature？」

### Temperature 的作用

```
Temperature = 0   → 完全確定性（總選機率最高的 token）
Temperature = 1   → 原始分佈（預設）
Temperature > 1   → 更隨機、更創意
```

```python
import anthropic

client = anthropic.Anthropic()

# 客服問答：需要精準，不要亂發揮
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=500,
    temperature=0.1,  # 低 temperature
    messages=[{"role": "user", "content": "我的訂單狀態是什麼？"}]
)

# 行銷文案：需要創意
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=500,
    temperature=0.9,  # 高 temperature
    messages=[{"role": "user", "content": "幫我寫一個有創意的產品標語"}]
)
```

---

## Hallucination：成因和緩解

面試一定會問，因為這是 LLM 最核心的問題之一。

### 為什麼 LLM 會幻覺

LLM 是在預測「下一個最可能的 token」，它並不真的「知道」事實，只是學到了語言模式。

當訓練資料裡沒有某個問題的答案，模型不會說「我不知道」，而是**生成一個聽起來合理但錯誤的答案**。

### 緩解方向

```
1. System Prompt 明確指示
   "如果不確定，請說『我不知道』，不要猜測"

2. RAG（最有效）
   給模型可以引用的上下文，限制它的發揮空間

3. Temperature 降低
   減少隨機性，讓模型更保守

4. Self-consistency
   同一個問題問多次，取最一致的答案

5. Citation / Grounding
   要求模型引用來源，間接迫使它更謹慎
```

---

## 面試快速自測

在去面試之前，確認你能用自己的話解釋這些：

- [ ] Self-Attention 的 Q、K、V 各是什麼意思？
- [ ] Encoder-only vs Decoder-only 有什麼差？適合什麼任務？
- [ ] Precision 和 Recall 的 trade-off 是什麼？
- [ ] 為什麼 Fine-tuning 會 overfit？怎麼偵測？
- [ ] LoRA 為什麼比 Full Fine-tuning 省記憶體？
- [ ] Temperature 什麼情況調高？什麼情況調低？
- [ ] RAG 怎麼減少幻覺？

如果有任何一題你需要想很久，那就是要補的地方。

---

## 小結

FDE 面試的 ML 基礎題，通常是用來**過濾**的，不是用來拉分的。

答不出來就直接扣分，答得好也不會讓你脫穎而出。

但這些概念在實際工作中是真的有用的：

- 你需要知道 Embedding 才能設計好 RAG
- 你需要知道 Fine-tuning trade-off 才能給客戶正確的建議
- 你需要知道評估指標才能量化系統的改善

下一篇：**System Design** — 設計企業知識庫 Chatbot 和 Internal Copilot，這是 FDE 最貼近實際工作的考題。
