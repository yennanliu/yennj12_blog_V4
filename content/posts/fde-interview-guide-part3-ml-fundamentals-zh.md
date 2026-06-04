---
title: "FDE 面試準備指南（三）：你不能忽略的 ML 基礎"
date: 2026-05-30T11:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，整理 FDE 面試中仍然高頻的傳統 ML / AI 基礎知識，包含 Transformer、Embedding、評估指標與 Fine-tuning 的工程視角"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Machine Learning", "Transformer", "Embedding", "Evaluation", "Fine-tuning", "Interview", "Google"]
authors: ["yen"]
readTime: "13 min"
---

> 有人覺得 FDE 只需要會包 API。  
> 這個判斷在面試中會死得很難看。  
> 基礎不紮實，一旦系統出問題，你沒有能力診斷。

> **閱讀建議：** 這篇是 ML 基礎概要。想要更完整的深度版本，參考 [第八篇（ML 完整版）](/posts/fde-interview-guide-part8-ml-fundamentals-zh/) 和 [第九篇（LLM 核心）](/posts/fde-interview-guide-part9-llm-core-zh/)。

---

## 面試情境

> **面試官：**「解釋一下 Transformer 的 Self-Attention 機制。然後告訴我：Fine-tuning 和 RAG 在你的客戶場景下你怎麼選？如果 Fine-tuning 出現 Overfitting，你怎麼偵測？」

ML 基礎題通常是「過濾用的」——答不出來直接扣分，答得好不會讓你脫穎而出。但這些概念在實際工作中真的有用。

---

## 一、Transformer 架構：面試要說清楚的程度

### Self-Attention 的核心機制

傳統 RNN 的問題：句子越長，開頭的資訊到句尾就已經被稀釋了，**遠距離依賴很難學**。

Self-Attention 的解法：**每個 token 直接和所有其他 token 計算相關性，不管距離**。

```
句子：「這家公司的 CEO 昨天宣布了一項重大決策」

Self-Attention 讓「決策」直接「看到」「CEO」，
不需要一步步從前面傳遞資訊。

數學直觀（面試可能問到 Q/K/V 的意思）：

  Q（Query）：這個 token 在「問」什麼資訊？
  K（Key）：  其他 token「能提供」什麼資訊？
  V（Value）：實際要「傳遞」的內容是什麼？

  計算流程：
  Q × Kᵀ（相關性分數）→ Softmax（變成機率分布）→ × V（加權求和）

  不需要手推公式，但要知道：
  └── √d_k 是縮放因子，避免點積值過大導致梯度消失
```

### Positional Encoding：為什麼要加位置資訊

Self-Attention 本身**沒有位置概念**。

```
「我愛你」和「你愛我」裡的「愛」，
在純 Self-Attention 裡計算出來的 embedding 是相同的。

Positional Encoding 用週期函數（sin/cos）給每個位置一個唯一的「指紋」，
讓模型知道「這個 token 在句子的第幾個位置」。

面試要說的：
  └── PE 讓 Transformer 能處理位置資訊，
      沒有 PE，模型看到的是「一袋單詞」，不是「有順序的句子」
```

### 三種 Transformer 變體

| 架構 | 代表模型 | 適合任務 | FDE 場景 |
|------|----------|----------|---------|
| Encoder only | BERT | 文本分類、NER、相似度 | Embedding 模型選型 |
| Decoder only | GPT、Claude、Gemini | 文本生成、對話 | 你每天呼叫的 API |
| Encoder-Decoder | T5、BART | 翻譯、摘要 | 少見於 FDE 場景 |

**FDE 最常遇到的是 Decoder only**——你呼叫的所有對話 API 幾乎都是這類架構。

---

## 二、Embedding：解釋到工程視角

### 什麼是 Embedding（一句話）

> **把文字映射成向量，讓機器能計算語意距離。**

```
語意相似 → 向量距離近：

  「貓」  →  [0.23, -0.45, 0.87, ...]  （768 維）
  「狗」  →  [0.25, -0.43, 0.85, ...]  ← 和貓很接近（同為動物）
  「汽車」→  [-0.67, 0.12, -0.34, ...]  ← 和貓很遠（不同語意域）

相似度計算用 Cosine Similarity：
  公式：cos(θ) = (A · B) / (|A| × |B|)
  範圍：−1 到 1（1 = 完全相同方向，0 = 無關，−1 = 相反）
```

### 常用 Embedding 模型選型

| 模型 | 維度 | 特點 | FDE 推薦場景 |
|------|------|------|-------------|
| text-embedding-004（Google） | 768 | 多語言、支援 task_type | GCP 生態系首選 |
| text-embedding-3-small（OpenAI） | 1536 | 成本低 | 混合雲場景 |
| BGE-M3（開源） | 1024 | 多語言、中文強 | 中文為主的知識庫 |
| bge-large-zh（開源） | 1024 | 中文專用，效能極佳 | 純中文場景 |

**選型關鍵問題：**

```
1. 語言：中文為主 → BGE 系列；多語言 → text-embedding-004
2. 部署：必須在 GCP → Vertex AI text-embedding；可用第三方 → 看 benchmark
3. 成本：高流量 → 用小維度（384-768）+ MRL 截短
4. 評估：不要靠直覺選，用自己的資料跑 retrieval recall@k，數字說話
```

---

## 三、評估指標：必須能流利解釋

### Precision vs Recall（用搜尋引擎理解最清楚）

```
場景：搜尋引擎返回 10 篇文章，資料庫裡有 20 篇相關文章

  搜尋結果 10 篇中，7 篇是真正相關的
  → Precision = 7/10 = 70%（你找到的東西，有多少是對的）

  資料庫 20 篇相關文章中，找到了 7 篇
  → Recall = 7/20 = 35%（所有對的東西，你找到了幾個）

Trade-off：
  High Precision + Low Recall：很精準但漏了很多
  Low Precision + High Recall：找到很多但很多是無關的

  F1 = 2 × (P × R) / (P + R)  ← 兩者的調和平均，不確定哪個更重要時看這個
```

### RAG 場景的特殊指標

```
傳統 Precision/Recall 不夠用，RAG 用 RAGAS 框架：

  Context Recall
  「回答問題所需的資訊，有多少比例被 Retrieve 到了？」
  → 衡量 Retrieval 品質，低 = Retrieval 有問題

  Faithfulness（忠實度）
  「LLM 的回答，有多少比例忠於 Retrieved Context？」
  → 衡量幻覺程度，低 = LLM 在自己捏造

  Answer Relevancy
  「回答是否直接回應了問題？」
  → 衡量整體回答相關性

診斷流程：
  Context Recall 低 → Retrieval 問題（Chunking、Embedding、Hybrid Search）
  Context Recall 高但 Faithfulness 低 → Generation 問題（Prompt、Grounding）
```

---

## 四、Overfitting vs Underfitting：FDE 視角

### 傳統 ML 的理解

```
Underfitting（欠擬合）：模型太簡單
  訓練集表現差 → 測試集也差 → 模型沒有學到規律

Overfitting（過擬合）：模型太複雜，記住了訓練資料
  訓練集表現好 → 測試集表現差 → 泛化能力差
```

### LLM Fine-tuning 的版本

```
Fine-tuning Overfitting 的樣子：

  Epoch 1-5：train loss ↓，val loss ↓  ← 正常學習
  Epoch 6：  train loss ↓，val loss →  ← 開始停滯
  Epoch 7-10：train loss ↓，val loss ↑  ← Overfitting，要 Early Stop

偵測方法：
  訓練時同時監控 Train Loss 和 Validation Loss（用 held-out 資料集）
  Val Loss 開始上升超過 5% → 觸發 Early Stopping，用這個 checkpoint

FDE 的客戶場景：
  客戶 Fine-tuning 後說「模型在測試集很好，但實際客服效果變差」
  → 幾乎是 Overfitting，訓練資料太窄，沒有覆蓋真實用戶的多樣性
  → 建議：增加訓練資料多樣性，或者降低 epoch 數，或者換 RAG
```

---

## 五、Fine-tuning 核心知識：什麼時候建議客戶用

```
選擇框架：

  你的知識是動態的？    → RAG（文件改，知識就更新）
  你需要追溯來源？      → RAG（查到哪份文件）
  你要改變輸出格式？    → Fine-tuning
  你要固定語氣風格？    → Fine-tuning
  你有大量標注資料？    → Fine-tuning 更划算
```

| | RAG | Fine-tuning |
|--|-----|-------------|
| 知識更新 | 即時（改 DB） | 需要重新訓練 |
| 引用來源 | 可以 | 幾乎不行 |
| 成本 | Inference + DB | GPU 訓練 |
| 幻覺風險 | 較低 | 較高 |
| 輸出格式控制 | 靠 Prompt | 直接訓練進去 |

### LoRA：為什麼幾乎取代了 Full Fine-tuning

```
Full Fine-tuning 的問題：
  修改所有模型參數 → 需要和原模型一樣大的 GPU 記憶體
  Gemini 2B → 需要數十 GB GPU RAM
  Gemma 9B → 需要數百 GB GPU RAM → 一般企業負擔不起

LoRA 的做法：
  凍結原始模型所有參數
  在每個 Attention 層旁邊插入兩個小矩陣（A 和 B）
  只訓練這兩個小矩陣

  原始 weight matrix W（768×768 = 589,824 個參數）
  LoRA 矩陣 A（768×16）+ B（16×768）= 24,576 個參數
                                         ↑ 只有 4.2%

  推理時：W' = W + BA（合併進原始矩陣，不增加推理延遲）

LoRA 的關鍵參數：
  rank (r)：越小越省記憶體，但表達能力越弱
            通常 r=8 到 r=64，大多數場景 r=16 夠用
  target_modules：選哪些層訓練
                  通常訓練 Attention 的 Q 和 V（不是全部層）
```

---

## 六、Token 與 Context Window

### Token 的工程意涵

```
LLM 以 Token 為單位處理文字，不是字元或詞語：

  英文：1 token ≈ 0.75 個單詞（"tokenization" → ["token", "ization"]）
  中文：1 token ≈ 1 個中文字（「台灣」可能是 1 個 token 或 2 個）

  粗估：
  1,000 英文 tokens ≈ 750 個英文字
  1,000 中文 tokens ≈ 1,000 個中文字

Context Window 的設計影響：
  系統 Prompt：約 500 tokens（固定）
  RAG Context：約 1,500 tokens（每次查詢）
  對話歷史：隨輪次線性增長（最容易爆的部分）
  輸出 Reserve：約 2,000 tokens

  → Chunk Size 設計要用 tokens 計算，不是字元數
  → 超過 Context Window → 報錯，Agent 中斷
```

### Temperature 的選擇邏輯

```
Temperature 控制 LLM 輸出的隨機程度：

場景                建議 Temperature    理由
───────────────────────────────────────────────────────
客服問答、事實查詢   0.0 – 0.2          需要精準，不要亂發揮
程式碼生成          0.0 – 0.3          要正確，不要創意
文件摘要            0.3 – 0.5          保留重要資訊，允許改寫
行銷文案            0.7 – 0.9          需要創意和多樣性
頭腦風暴            0.9 – 1.0          越多樣越好

規則：
  精準性要求高 → Temperature 低
  創意和多樣性要求高 → Temperature 高
```

---

## 七、Hallucination：成因與緩解

面試幾乎必問，因為這是 LLM 最核心的工程問題。

```
為什麼 LLM 會幻覺？

LLM 的訓練目標是「預測下一個最可能的 token」，
它不是在「查找事實」，而是在「生成聽起來合理的文字」。
當訓練資料裡沒有某個問題的答案，
模型不會說「我不知道」——它會生成一個聽起來合理但可能錯的答案。

緩解方向：

方向                 效果      代價
──────────────────────────────────────────────────────
RAG（提供 Context）  最有效    需要建立 Retrieval Pipeline
Grounding Prompt    中等       需要設計 Prompt
Temperature 降低    有限       犧牲多樣性
Self-Consistency    有效       多次呼叫，成本高
引用來源要求         間接有效   LLM 更謹慎，但不能完全防止
```

---

## 八、面試官地雷題

**地雷 1：「Encoder-only 和 Decoder-only 模型的 Embedding 有什麼差別？」**

```
答：Encoder-only（如 BERT）的 Embedding 是雙向的——
    每個 token 能看到句子中所有其他 token，
    適合做語意相似度和分類任務（也是大多數 Embedding 模型的基礎架構）。
    Decoder-only（如 GPT/Gemini）的 Embedding 是單向的——
    每個 token 只能看到它之前的 token，
    設計目標是生成，不是 Embedding。
    所以 RAG 用的 Embedding 模型通常是 Encoder-based 的。
```

**地雷 2：「LoRA 的 rank 設多少？你怎麼決定？」**

```
答：rank 是 LoRA 的核心超參數，控制適應能力和參數量的 trade-off。
    一般起點是 r=16，然後在 validation set 上驗證效果。
    如果效果不夠好，加大到 r=32 或 r=64。
    如果記憶體緊張，縮小到 r=8。
    沒有通用最優值——要根據你的任務複雜度和資料量決定。
    原則：任務越複雜、資料越多，rank 可以設大一點。
```

**地雷 3：「Fine-tuning 後模型在 eval set 表現好，但生產環境效果差，為什麼？」**

```
答：最常見的三個原因：
    1. Train/Eval 分佈和生產分佈不一致——你的 eval set 不代表真實用戶的多樣性
    2. Overfitting——特別是訓練資料量小但 epoch 跑太多的情況
    3. 生產輸入有預處理差異——Tokenization、Prompt 格式等和訓練時不一致
    解法：用「真實生產流量的樣本」做 eval，不用合成資料或早期測試資料。
```

---

## 九、面試回答完整示範

```
面試官期待的回答（ML 基礎確認題）：

Self-Attention：
「Self-Attention 讓每個 token 能直接和句子中所有其他 token
 計算相關性，解決了 RNN 遠距離依賴難學的問題。
 核心是 Q、K、V 三個矩陣——
 Q 問「我需要什麼資訊」，K 說「我有什麼資訊」，
 兩者相乘得到相關性分數，再乘 V 得到加權的資訊。」

Fine-tuning vs RAG：
「我會先問客戶：你的知識需要頻繁更新嗎？需要引用文件來源嗎？
 如果是，選 RAG——改 DB 就更新知識，不需要重新訓練。
 如果客戶需要固定的輸出格式或特定語氣，
 或者有大量標注資料，才考慮 Fine-tuning。
 兩者的根本差異是：RAG 是知識外部化，Fine-tuning 是知識內化。」

Overfitting 偵測：
「Fine-tuning 時同時監控 Train Loss 和 Validation Loss。
 如果 Train Loss 持續下降但 Val Loss 開始上升，
 就是 Overfitting 的信號。
 標準做法是 Early Stopping——
 Val Loss 上升超過 5% 時停止，使用最低 Val Loss 的 checkpoint。」
```

---

ML 基礎在 FDE 面試中是「過濾題」。  
答不出來直接被扣分，答得好不是加分，是**建立你有工程判斷力的基礎印象**。

下一篇：[**System Design 實戰**](/posts/fde-interview-guide-part4-system-design-zh/) — 設計企業知識庫 Chatbot 和 Internal Copilot。
