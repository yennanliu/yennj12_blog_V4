---
title: "AI 工程從零開始｜Phase 5 Part 3：進階 NLP — BERT、問答系統與語言理解"
date: 2026-06-21T14:00:00+08:00
draft: false
weight: 11
description: "深入解析 BERT/RoBERTa/DeBERTa 預訓練策略、問答系統架構、文字摘要、機器翻譯評估與 NLP 生產系統的工程挑戰"
categories: ["engineering", "ai", "all"]
tags: ["AI", "NLP", "BERT", "Question Answering", "Text Summarization", "Machine Translation", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人以為 NLP 就是把文字丟進模型等答案；*
> *真正的工程師知道語言理解需要雙向上下文、任務特化微調、以及在延遲與準確率間反覆取捨。*
> *問題不是「用哪個模型」，而是「這個系統在 P99 500ms 內能可靠回答什麼問題」。*
> *從 BERT 到問答系統，進階 NLP 的核心是：為正確的任務選擇正確的架構。*

---

**面試情境：** 你的團隊正在為一個法律文件平台建構問答系統。文件平均 50 頁，用戶問題如「這份合約的違約金條款是什麼？」。系統需在 2 秒內回答，準確率要求 > 90%，每月處理 50 萬筆查詢。請設計整體架構，並說明為何選擇 Extractive QA 而非 Generative QA，以及如何在規模下維持品質。

---

## 一、核心問題：語言理解 vs 語言生成的本質差異

NLP 工程中最常見的誤解是把「理解」和「生成」混為一談。這兩個任務在模型架構、訓練目標、推論策略上有根本差異。

**語言理解（Understanding）的本質：**

- 任務：分類、命名實體識別、關係抽取、問答中的答案定位
- 需要：雙向上下文（左邊和右邊的詞都重要）
- 代表架構：BERT（Encoder-only Transformer）
- 輸出：分類標籤、span 位置、相似度分數

**語言生成（Generation）的本質：**

- 任務：文字摘要、機器翻譯、對話回覆、程式碼生成
- 需要：自回歸解碼（autoregressive decoding）
- 代表架構：GPT 系列（Decoder-only）、T5（Encoder-Decoder）
- 輸出：Token 序列

**為什麼這個差異在工程上很重要？**

| 面向 | 理解任務 | 生成任務 |
|------|---------|---------|
| 推論延遲 | 10–50ms（一次 forward pass） | 200ms–5s（逐 token 生成） |
| 輸出確定性 | 高（span 位置或分類） | 低（temperature 影響大） |
| 可審計性 | 高（可追蹤到原文哪句話） | 低（hallucination 風險） |
| GPU 記憶體 | BERT-base: 440MB | GPT-3.5 equivalent: 數十 GB |
| 適合情境 | 合規、法律、醫療 | 創意、摘要、對話 |

法律文件問答的核心矛盾：用戶想要「自然語言答案」，但合規要求「可追蹤到原文」。這個矛盾決定了整個系統架構。

---

## 二、三個演進階段（含 ASCII 架構圖）

### Phase 1：POC（< 1K 查詢/月，單一文件類型）

```
╔══════════════════════════════════════════════════════╗
║  Phase 1 — POC NLP Pipeline                         ║
╚══════════════════════════════════════════════════════╝

用戶問題
    │
    ▼
┌─────────────────┐
│  文字預處理      │  句子切割、小寫化、去標點
│  (spaCy / NLTK) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  TF-IDF 檢索    │  找出最相關的 top-5 段落
│  (scikit-learn) │  召回率 ~70%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  BERT QA 微調   │  deepset/roberta-base-squad2
│  (HuggingFace)  │  在 top-1 段落上找答案 span
└────────┬────────┘
         │
         ▼
    答案文字 + 信心分數
```

**新增元件：** spaCy 預處理、TF-IDF 索引、BERT QA 模型
**成本：** ~$50/月（單一 CPU 實例）
**問題：** TF-IDF 召回率不足、長文件切割策略粗糙、無快取

---

### Phase 2：MVP（10K–200K 查詢/月，多文件類型）

```
╔══════════════════════════════════════════════════════════════╗
║  Phase 2 — Production NLP System                            ║
╚══════════════════════════════════════════════════════════════╝

用戶問題
    │
    ▼
┌──────────────────────────────┐
│  Query 前處理 + 意圖分類      │  是否需要 QA 或摘要？
│  BERT classifier (2 classes)  │  延遲: ~20ms
└──────────────┬───────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
  [QA 路徑]        [摘要路徑]
       │                │
       ▼                ▼
┌─────────────┐  ┌─────────────────┐
│  Dense      │  │  Abstractive    │
│  Retrieval  │  │  Summarization  │
│  (DPR +     │  │  (BART/T5)      │
│  Faiss)     │  │  延遲: ~500ms   │
│  召回率 85% │  └─────────────────┘
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Reader Model               │
│  RoBERTa-large-squad2       │
│  答案抽取 + 信心分數         │
│  延遲: ~80ms                │
└──────────────┬──────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Answer 後處理               │
│  - 信心門檻過濾（< 0.4 拒答）│
│  - 原文引用段落回傳          │
│  - Redis 快取（TTL 1hr）    │
└──────────────────────────────┘
```

**新增元件：** DPR + Faiss 向量檢索、意圖分類器、信心門檻、Redis 快取
**成本：** ~$800/月（2x GPU 實例 + Faiss 伺服器）
**解決：** 召回率提升至 85%、快取命中率 ~40%、長文件切割改善
**遺留問題：** 跨段落推理（答案橫跨多個段落）、更新文件需重建索引

---

### Phase 3：Scale（200K–1M+ 查詢/月，企業級）

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 3 — Enterprise NLP Platform                              ║
╚══════════════════════════════════════════════════════════════════╝

                        ┌─────────────────┐
                        │   API Gateway   │
                        │  Rate Limit     │
                        │  Auth / Quota   │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │  Query Router   │  規則 + ML 混合路由
                        └──┬──────────┬───┘
                           │          │
              ┌────────────▼──┐   ┌───▼──────────────┐
              │  Real-time    │   │  Async / Batch    │
              │  QA Service   │   │  Summarization    │
              │  SLA: 500ms   │   │  SLA: 30s         │
              └──────┬────────┘   └───────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
    ┌────▼───┐  ┌────▼───┐  ┌───▼────┐
    │ Faiss  │  │ BM25   │  │ Cache  │
    │ Dense  │  │Sparse  │  │ Layer  │
    │ Recall │  │Recall  │  │ Redis  │
    │  ~87%  │  │  ~75%  │  │  Cluster│
    └────┬───┘  └────┬───┘  └────────┘
         └─────┬─────┘
               │  Hybrid Fusion (RRF)
               │  召回率: ~93%
               ▼
         ┌─────────────┐
         │  Re-ranker  │  cross-encoder 精排
         │  (ms-marco) │  Top-5 → Top-1
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Reader     │  DeBERTa-large-squad2
         │  Ensemble   │  2 模型投票
         └─────────────┘
```

**新增元件：** Hybrid Retrieval（Dense + Sparse 融合）、Re-ranker、模型 Ensemble、Async 批次處理
**成本：** ~$5,000/月（Auto-scaling GPU 叢集）
**解決：** 召回率達 93%、P99 延遲 < 500ms、模型更新 zero-downtime

---

## 三、BERT 預訓練：MLM + NSP 的直覺

BERT（Bidirectional Encoder Representations from Transformers）的突破在於預訓練目標設計。

### 3.1 Masked Language Model（MLM）

原始想法：讓模型學會「填空」。

```
輸入:  "台灣的 [MASK] 節是農曆新年"
目標:  預測 [MASK] = "傳統"

隨機遮蔽 15% 的 token：
  80% 換成 [MASK]
  10% 換成隨機 token
  10% 保持原樣（讓模型不確定哪個 token 會被測試）
```

**為什麼重要：** 迫使模型同時利用左邊和右邊的上下文（雙向），GPT 系列只能用左邊（單向）。

### 3.2 Next Sentence Prediction（NSP）

```
正例: [CLS] 台積電發布財報。[SEP] 營收創歷史新高。[SEP] → IsNext
負例: [CLS] 台積電發布財報。[SEP] 明天會下雨。[SEP]        → NotNext
```

**後來發現的問題：** NSP 任務太容易（負例選自不同文件，語義差距明顯），對模型幫助有限。RoBERTa 直接拿掉 NSP，效果反而更好。

### 3.3 BERT 的 Token 表示

```
┌──────────────────────────────────────────────────────┐
│  BERT Input Representation                           │
│                                                      │
│  [CLS] 這 份 合 約 [SEP] 違 約 金 多 少 ？ [SEP]     │
│    │   │  │  │  │   │   │  │  │  │  │  │   │        │
│    ▼   ▼  ▼  ▼  ▼   ▼   ▼  ▼  ▼  ▼  ▼  ▼   ▼        │
│  Token Embeddings（詞彙）                            │
│    +                                                 │
│  Segment Embeddings（A句 或 B句）                    │
│    +                                                 │
│  Position Embeddings（位置 0–511）                   │
│    ║                                                 │
│    ▼                                                 │
│  12 層 Transformer Encoder                          │
│    ║                                                 │
│    ▼                                                 │
│  [CLS] → 分類任務（取第一個 token 的表示）           │
│  每個 token → QA span 任務（start/end logits）       │
└──────────────────────────────────────────────────────┘
```

**關鍵數字：**
- BERT-base：12 層、768 隱藏維度、12 attention heads、110M 參數
- BERT-large：24 層、1024 隱藏維度、16 attention heads、340M 參數
- 最大序列長度：512 tokens（約 300–400 中文字）
- 預訓練資料：BooksCorpus（800M 詞）+ Wikipedia（2,500M 詞）

---

## 四、BERT 家族：RoBERTa / ALBERT / DeBERTa 演進

### 4.1 RoBERTa（2019，Facebook）

**核心改進：拿掉 NSP，更多資料，更長訓練**

| 改動 | 原始 BERT | RoBERTa |
|------|-----------|---------|
| NSP 任務 | 有 | 移除 |
| 訓練資料 | 16GB | 160GB（+CommonCrawl 等） |
| Batch size | 256 | 8,192 |
| 訓練步數 | 1M | 500K（但更大 batch） |
| 動態遮蔽 | 靜態（預先生成） | 動態（每次 epoch 不同）|
| SQuAD 2.0 F1 | 83.1 | **89.4** |

**工程結論：** 預訓練資料量和訓練穩定性比模型架構改動更重要。

### 4.2 ALBERT（2020，Google Research）

**核心改進：參數壓縮，讓大模型可實用**

兩個關鍵技術：
1. **Factorized Embedding**：詞嵌入維度（128）與隱藏層維度（768/1024/4096）分離，節省大量參數
2. **Cross-layer Parameter Sharing**：12 層 Transformer 共享同一組參數

```
BERT-large:    340M 參數，1024 hidden
ALBERT-xxlarge: 235M 參數，4096 hidden（效果更好！）
```

**代價：** 推論速度並未加快（層數相同），只是訓練時記憶體更少。

### 4.3 DeBERTa（2021–2023，Microsoft）

**核心改進：解耦位置與內容，更好的注意力機制**

- **Disentangled Attention**：內容向量和位置向量分開計算注意力，再合併
- **Enhanced Mask Decoder**：加入絕對位置資訊於解碼階段
- DeBERTa-v3-large 在多個 benchmark 超越 GPT-3（175B 參數），使用僅 304M 參數

**生產選型建議：**

| 情境 | 推薦模型 | 理由 |
|------|---------|------|
| 延遲 < 50ms | BERT-base / DistilBERT | 參數少，推論快 |
| 最高準確率 | DeBERTa-v3-large | SOTA 在多個 NLU benchmark |
| 記憶體受限 | ALBERT-base | 參數共享，記憶體友善 |
| 多語言 | XLM-RoBERTa | 100 語言預訓練 |

---

## 五、問答系統架構：Extractive vs Generative QA

### 5.1 Extractive QA（抽取式）

**核心假設：** 答案一定在原文中某段連續文字。

```
┌─────────────────────────────────────────────────────┐
│  Extractive QA 流程                                  │
│                                                     │
│  問題: "合約的違約金是多少？"                        │
│                                                     │
│  原文段落:                                           │
│  "...乙方若違約，應賠償甲方新台幣壹佰萬元整，       │
│   並於十五日內支付完畢..."                           │
│                                                     │
│  模型輸出:                                           │
│    start_logits: [0.1, 0.2, ..., 0.9(壹佰萬), ...]  │
│    end_logits:   [..., 0.1, ..., 0.8(元整), ...]    │
│                                                     │
│  答案 span: "新台幣壹佰萬元整"                       │
│  信心分數: 0.87                                     │
└─────────────────────────────────────────────────────┘
```

**優點：**
- 可追蹤到原文（合規要求可滿足）
- 推論延遲低（單次 forward pass，~80ms）
- Hallucination 風險極低

**缺點：**
- 無法回答需要推理的問題（「如果我違約三次，總共要賠多少？」）
- 答案必須在原文中明確出現
- 無法整合多段落資訊

### 5.2 Generative QA（生成式）

**核心假設：** 模型可以根據上下文生成新文字作為答案。

代表模型：
- **RAG（Retrieval-Augmented Generation）**：檢索相關段落後，用 seq2seq 模型生成答案
- **FiD（Fusion-in-Decoder）**：多段落各自 encode，在 decoder 融合
- **GPT-4 + RAG**：最新 LLM 作為 reader

**延遲比較：**
- Extractive（RoBERTa-large）：~80ms
- Generative（BART-large）：~400ms
- Generative（GPT-3.5 via API）：~1,500ms

### 5.3 Retriever 深度比較

**BM25（稀疏檢索）：**
- 基於詞頻（TF-IDF 的改進版）
- 優點：可解釋、無需 GPU、更新索引 < 1 秒
- 缺點：詞彙鴻溝問題（「違約賠償」vs「賠款條款」）

**DPR（Dense Passage Retrieval，稠密檢索）：**
- 用 BERT 將問題和段落各自編碼為 768 維向量，計算點積相似度
- 優點：語義理解，解決詞彙鴻溝
- 缺點：需要 GPU、更新索引需重新 encode（約 100ms/段落）

**Hybrid（混合檢索）：**
```
BM25 分數（歸一化） × α + DPR 分數（歸一化） × (1-α)
建議 α = 0.5，可根據任務調整
召回率: BM25 ~75%, DPR ~87%, Hybrid ~93%
```

---

## 六、文字摘要：Extractive vs Abstractive

### 6.1 Extractive 摘要

從原文選出最重要的句子，不改寫。

**演算法：TextRank**（無監督，基於圖論）

```
1. 將每個句子表示為節點
2. 計算句子間相似度（TF-IDF cosine）作為邊的權重
3. 執行 PageRank 算法
4. 選出分數最高的 Top-K 句子
```

**優點：** 保真度高、無 hallucination、可在 CPU 上毫秒級完成
**缺點：** 摘要讀起來不連貫、無法壓縮資訊

### 6.2 Abstractive 摘要

理解原文後，重新生成摘要。

**主流模型：**
- **BART**（Facebook，2019）：Denoising Autoencoder 預訓練，Encoder-Decoder 架構
- **T5**（Google Research，2020）：把所有 NLP 任務統一為 text-to-text
- **PEGASUS**（Google Research，2020）：專為摘要設計的預訓練目標（GSG）

**生產注意事項：**

| 問題 | 症狀 | 解法 |
|------|------|------|
| Hallucination | 摘要出現原文沒有的數字 | 加入 Faithfulness 分類器後處理 |
| 過長生成 | 超過 max_length 仍繼續 | 設定 length_penalty > 1.0 |
| 重複句子 | 同一意思出現兩次 | no_repeat_ngram_size = 3 |
| 摘要過短 | 只有一兩句話 | 設定 min_length |

**中文摘要特殊挑戰：**
- 繁體/簡體混用（需要正規化）
- 中文無空格，BPE tokenizer 需要特別訓練
- 推薦預訓練模型：mengzi-t5-base（繁中需要額外微調）

---

## 七、NLP 評估指標：BLEU/ROUGE/BERTScore 的陷阱

### 7.1 BLEU（機器翻譯）

計算生成文字和參考文字的 n-gram 重疊率。

```
BLEU = BP × exp(Σ wₙ × log pₙ)

pₙ = n-gram precision（修正版）
BP = Brevity Penalty（懲罰過短翻譯）
```

**陷阱：**
- 對詞序不敏感（「貓追狗」和「狗追貓」可能分數相近）
- 不考慮語義（同義詞替換會被懲罰）
- 需要多個參考翻譯才穩定（單個參考文字方差很大）
- BLEU < 10：無用翻譯；BLEU 30-50：一般商用品質；BLEU > 50：接近人類

### 7.2 ROUGE（文字摘要）

計算生成摘要和參考摘要的召回率。

- **ROUGE-1**：單詞重疊（recall of unigrams）
- **ROUGE-2**：雙詞組重疊（更嚴格）
- **ROUGE-L**：最長公共子序列（考慮順序）

```
ROUGE-1 = 重疊的單詞數 / 參考摘要的單詞總數
```

**陷阱：**
- 高 ROUGE 不代表高品質（可以複製原文片段）
- 對中文需要先斷詞，結果受斷詞工具影響
- 不捕捉語義等價（「增加」和「提升」ROUGE 會認為不同）

### 7.3 BERTScore（語義相似度）

用 BERT 的上下文化表示計算語義相似度，解決詞彙鴻溝問題。

```
Precision = 平均每個生成 token 與最接近的參考 token 的相似度
Recall    = 平均每個參考 token 與最接近的生成 token 的相似度
F1        = 兩者調和平均
```

**優點：** 捕捉語義等價、對改寫更公平
**缺點：** 計算成本高（需要 BERT forward pass）、可解釋性差

### 7.4 QA 專用指標

- **Exact Match（EM）**：生成答案是否完全等於參考答案（嚴格）
- **F1（token overlap）**：答案 token 的重疊率（寬鬆）
- **Human Evaluation**：最終還是需要人工評估（Faithfulness、Coherence、Relevance）

**實戰建議：** 自動指標用於快速迭代，每兩週做一次人工抽樣評估（100 筆），兩者數字要同步看。

---

## 八、為什麼選 X 不選 Y（6 個決策表）

### 決策 1：Extractive QA vs Generative QA

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
Extractive      可追蹤原文（合規）              Generative：hallucination 風險
QA              延遲 ~80ms（SLA 友善）          Generative：延遲 400ms–2s
                信心分數可直接作門檻             Generative：生成評估難標準化

翻轉條件：當問題需要跨段落推理、計算或整合多個來源時，改用 Generative。
```

### 決策 2：Dense Retrieval vs Sparse Retrieval（BM25）

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
Dense           解決詞彙鴻溝問題               BM25：完全依賴字面匹配
(DPR+Faiss)     語義相似度更準確               BM25：「薪資」≠「報酬」
                召回率比 BM25 高 ~12%          

翻轉條件：當文件頻繁更新（< 1 分鐘）、無法負擔 GPU 成本時，BM25 或 Hybrid 更合適。
```

### 決策 3：RoBERTa vs DeBERTa

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
RoBERTa-        推論速度快 30%                 DeBERTa：更高 SQuAD F1
large           社群支援成熟                   DeBERTa：但延遲多 ~20ms
                Hugging Face 生態完整

翻轉條件：準確率是主要瓶頸且延遲預算充足（> 200ms），改用 DeBERTa-v3-large。
```

### 決策 4：BART vs T5（生成式摘要）

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
BART            摘要任務 ROUGE 分數更高         T5：通用任務好但摘要略遜
                預訓練目標（denoising）         T5：需要 prefix 設計
                與摘要任務更匹配               T5：推論速度相近

翻轉條件：需要同時處理多個 NLP 任務（摘要、翻譯、QA）在一個系統，T5 的 text-to-text 統一介面更有利。
```

### 決策 5：BM25 vs 向量資料庫（Faiss vs Pinecone）

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
Faiss           自架，資料不出境               Pinecone：managed service
(自架)          無 per-query 費用              Pinecone：$70+/月起跳
                客製化 index 結構              BM25：語義理解弱

翻轉條件：團隊無 infra 能力、資料量 < 10M vectors，Pinecone 的 managed service 降低維運成本。
```

### 決策 6：模型微調 vs 直接使用預訓練模型

```
選擇            選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────
微調             領域詞彙對齊（法律、醫療）     預訓練：開箱即用，快速驗證
(Fine-tune)     F1 通常提升 5–15%              預訓練：無需標注資料
                推論成本相同                   預訓練：微調需 GPU + 時間

翻轉條件：標注資料 < 500 筆時，先嘗試 few-shot 或 prompt-based 方法，標注資料 > 2,000 筆再微調。
```

---

## 九、系統效應（傳統 NLP vs BERT vs LLM 全面對比）

| 指標 | 傳統 NLP（TF-IDF + 規則） | BERT 微調 | LLM（GPT-4 class） |
|------|--------------------------|-----------|---------------------|
| SQuAD 2.0 F1 | ~40% | ~90% | ~95%+ |
| 推論延遲（P99） | < 10ms | 80–200ms | 1,000–5,000ms |
| GPU 需求 | 無 | 1x T4 (16GB) | 數十 GB / API |
| 每月成本（50萬查詢） | ~$50 | ~$800 | ~$5,000–$10,000 |
| Hallucination 風險 | 無 | 低（Extractive） | 中–高 |
| 多語言支援 | 需各語言模型 | XLM-RoBERTa | 內建 |
| 領域適應 | 手動規則 | 微調（需標注資料） | 少樣本提示 |
| 可解釋性 | 高（可追蹤 token） | 中（attention 可視化） | 低 |
| 法規合規 | 高 | 高（Extractive） | 低–中 |
| 冷啟動時間 | 小時（規則撰寫） | 天（資料標注+訓練） | 分鐘（API 串接）|

**關鍵洞察：**
1. **BERT 是工程甜蜜點**：在延遲、成本、準確率、可解釋性之間取得最佳平衡，適合 90% 的生產場景
2. **LLM 適合探索階段**：快速驗證需求，但規模化成本 10x
3. **傳統 NLP 仍有價值**：在延遲極端敏感（< 10ms）或資料匱乏的情境下

---

## 十、面試答題要點

**面試官問：** 「為法律文件平台設計問答系統，月查詢 50 萬筆，2 秒 SLA，準確率 > 90%。」

> *「我會採用 Extractive QA 架構，分三個演進階段。Phase 1 用 TF-IDF + BERT-base-squad2 快速驗證，召回率約 70%，成本 $50/月。Phase 2 引入 Dense Retrieval（DPR + Faiss）解決詞彙鴻溝，搭配 RoBERTa-large reader，召回率提升至 85%，推論延遲約 80ms（遠低於 2 秒 SLA），成本約 $800/月。Phase 3 採用 Hybrid 檢索（BM25 + DPR 融合，召回率 93%）加上 Re-ranker 精排，確保 P99 < 500ms。選擇 Extractive 而非 Generative QA 的核心原因是合規：答案必須可追蹤到原文，Hallucination 在法律場景不可接受。信心分數低於 0.4 的查詢直接拒答並標記人工審核，這個設計讓準確率超過 92%，同時維持 99.5% 的可用性。*」

---

## 十一、系列導航

← 上一篇：[Phase 5 Part 2：Transformer 注意力機制與自監督學習](/posts/ai-eng-from-scratch-phase5-part2-transformer-zh/)

→ 下一篇：[Phase 6 Part 1：MLOps — 模型版本管理與 CI/CD 流水線](/posts/ai-eng-from-scratch-phase6-part1-mlops-zh/)

---

*本文為「AI 工程從零開始」系列第五階段第三篇，聚焦進階 NLP 工程實踐。如有技術問題，歡迎透過 About 頁面聯繫作者。*
