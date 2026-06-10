---
title: "FDE 面試準備指南（一）：RAG 完全解析"
date: 2026-05-30T10:00:00+08:00
draft: false
weight: 1
description: "以 Google AI 工程師兼面試官的視角，解析 FDE 面試中 RAG 最高頻考題，包含核心架構、Chunk 策略、幻覺改善、Hybrid Search 與實戰建議"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "RAG", "LLM", "Vector DB", "Interview", "Google"]
authors: ["yen"]
readTime: "12 min"
---

> 我在 Google 做 AI 工程，也是面試官。  
> 這是一份寫給準備 FDE 面試的人看的系列。  
> 不是教科書，是我站在白板前問過你才懂的那種。

---

## 面試情境

> **面試官：**「解釋一下 RAG 的架構，以及你會怎麼設計一個生產可用的 RAG 系統。如果 RAG 的回答品質不好，你怎麼診斷和改善？」

這是 FDE 第一關幾乎必出的題。  
能把這題說清楚的人，比你想像中少。

---

## 一、RAG 是什麼

用一句話說完：

> **RAG = 讓 LLM 在回答前，先去查資料。**

不讓它憑空捏造，而是給它上下文，再要求它根據上下文回答。

### 完整流程，五個步驟

```
使用者問題
    ↓
① Embedding（把問題變成向量）
    ↓
② Retrieval（從向量資料庫搜尋相關文件）
    ↓
③ Context Injection（把文件塞進 Prompt）
    ↓
④ Generation（LLM 根據 Prompt 生成回答）
    ↓
回答（附來源引用）
```

---

## 二、RAG 在完整系統中的位置

面試官問系統設計，RAG 不是一個獨立存在的 Pipeline，而是整個 AI 系統的一個子系統。你要能說清楚它和誰互動、它的邊界在哪裡。

```
┌──────────────────────────────────────────────────────────────┐
│                       完整 RAG 系統架構                        │
│                                                               │
│   用戶 Query                                                  │
│        │                                                      │
│        ▼                                                      │
│   ┌─────────────┐     ┌──────────────────────────────────┐   │
│   │ Query Layer │     │         Knowledge Base           │   │
│   │             │     │                                  │   │
│   │ ├─ 意圖分類  │     │  原始文件 → Chunking → Embedding  │   │
│   │ └─ 改寫      │     │         → Vector DB Index        │   │
│   └──────┬──────┘     └──────────────────────────────────┘   │
│          │                        ↑ 離線建立                  │
│          ▼ 線上查詢                │                          │
│   ┌──────────────────────────────────────────────────┐       │
│   │              Retrieval Layer                      │       │
│   │                                                   │       │
│   │  Query Embedding → Vector DB → Top-K Candidates  │       │
│   │                            ↓                     │       │
│   │                       Reranker（可選）             │       │
│   │                            ↓                     │       │
│   │                    Final Context（3-5 chunks）    │       │
│   └──────────────────────────────────────────────────┘       │
│          │                                                    │
│          ▼                                                    │
│   ┌──────────────────────────────────────────────────┐       │
│   │              Generation Layer                     │       │
│   │                                                   │       │
│   │  System Prompt + Context + Query → LLM → 回答    │       │
│   └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、RAG vs Fine-tuning：面試必考對比題

這是我最愛問的對比題。很多人答得很模糊。

```
判斷框架：「你的知識是動態的，還是靜態的？」

如果是動態的（頻繁更新、需要引用來源）→ RAG
如果是靜態的（固定風格、格式、推理模式）→ Fine-tuning
```

| 維度 | RAG | Fine-tuning |
|------|-----|-------------|
| **知識更新** | 即時（改資料庫就好） | 需要重新訓練 |
| **成本** | 低（inference + retrieval） | 高（GPU 訓練費用） |
| **可引用來源** | 可以（查到哪篇文件） | 幾乎不行 |
| **私有資料安全** | 資料在你控制的 DB 裡 | 資料進入訓練流程，有外洩風險 |
| **幻覺風險** | 相對低（有 context 約束） | 相對高 |
| **適合場景** | 知識庫、FAQ、文件問答 | 語氣調整、特定格式輸出、領域推理 |

**面試官最想聽到：**  
不是記住這個表格，而是能說出：  
「在客戶的這個場景裡，我選 RAG 是因為 X，如果他們的需求是 Y，我才會考慮 Fine-tuning。」

---

## 四、Chunk 設計：最常被輕描淡寫的環節

Chunk Size 直接決定 Retrieval 品質。這題問的是你的 trade-off 意識。

### 三種大小的影響

```
Chunk Size 對系統的影響：

                小 (~200 tokens)   中 (~500 tokens)   大 (~1000 tokens)
──────────────────────────────────────────────────────────────────────
精確度            高                 中                  低
                 每塊聚焦，不含雜訊  折衷                 一塊帶了很多無關內容

跨段落理解         低                 中                  高
                 可能截斷語意        折衷                 上下文完整

Context 成本      低                 中                  高
                 每塊小，塞進去省錢  折衷                 塞 5 塊就很貴

適合場景          FAQ、精確查詢      大多數場景的預設選擇    長段落理解、報告
```

### 常見 Chunking 策略的選擇邏輯

```
文件類型                建議策略
──────────────────────────────────────────────────
FAQ / 問答對            固定大小，每題一塊，不需要 overlap
Markdown / 有標題結構   按標題切（## → ### 的層級邊界）
連續長文（白皮書）       語意切分（Semantic Chunking）
合約 / 法律文件         Parent-Child：小塊做搜尋，查到後帶回大塊
混合文件                Recursive Character Splitter（先 \n\n，再 \n，再空格）
```

**面試官追問最多的點：Overlap 為什麼重要？**

```
沒有 Overlap 的問題：

  [chunk_1: ...句子 A。句子 B。] [chunk_2: 句子 C。...]
                               ↑
                         如果一個完整語意跨越這個邊界，
                         兩個 chunk 各自都沒有完整語意

有 Overlap（50 tokens）：

  [chunk_1: ...句子 A。句子 B。] 
  [chunk_2: 句子 B。句子 C。...]  ← 句子 B 出現在兩個 chunk 裡
                               
  確保邊界附近的語意不會在任何一個 chunk 裡完全消失
```

---

## 五、Retrieval 品質：診斷與改善

這是「回答品質不好」的第一個排查點。

### 問題來源分類

```
RAG 回答品質差的根因：

┌─────────────────────────────────────────────────┐
│  類型 A：Retrieval 問題（查的東西不對）           │
│                                                  │
│  症狀：LLM 的回答和正確答案完全無關              │
│  診斷：看 Retrieved Chunks 裡有沒有正確資訊      │
│  方向：改善 Chunking、Embedding 模型、           │
│         加入 Hybrid Search 或 Reranker           │
├─────────────────────────────────────────────────┤
│  類型 B：Generation 問題（查的東西對，但說錯了） │
│                                                  │
│  症狀：Retrieved Chunks 有正確資訊，             │
│         但 LLM 的回答忽略了它                    │
│  診斷：Faithfulness 分數（答案 vs Context 的一致性）│
│  方向：改 Prompt、縮短 Context、加強 Grounding   │
└─────────────────────────────────────────────────┘
```

### 五個改善方向

**方向一：Hybrid Search（語意 + 關鍵字）**

```
純向量搜尋的盲點：

  搜尋「GPT-4o release date」
  → 向量搜尋找到「語言模型發布歷史」（語意相關）
  → 但你要的是明確包含「GPT-4o」關鍵字的文件

Hybrid Search 架構：

  Query
   ├── BM25（關鍵字搜尋）→ Sparse Results
   └── Vector Search（語意搜尋）→ Dense Results
                 ↓
         RRF 融合排名（Reciprocal Rank Fusion）
                 ↓
            Final Top-K
```

**方向二：Reranker（精選最後 5 筆）**

```
為什麼需要 Reranker？

  向量搜尋的 Top-K 是近似結果（ANN），不保證 Top-1 最相關。

  兩階段架構：

  Stage 1（快，近似）：
  Bi-Encoder → Query embedding + Doc embedding → 餘弦相似度
  掃全部文件，取 Top-50 候選

  Stage 2（慢，精確）：
  Cross-Encoder → (Query + Doc) 一起輸入 → 相關性分數
  只對 Top-50 跑，取最高分的 5 筆

  代價：每次 Rerank 需要額外推理時間
  適合：回答品質要求高、Latency 允許多 200-500ms 的場景
```

**方向三：Metadata Filtering**

```
在向量搜尋時加過濾條件，縮小搜尋空間：

  where = {
      "department": "engineering",
      "version": {"$gte": "2024"},
      "language": "zh-TW"
  }

  效果：避免查到無關部門或過期的文件
  注意：Filter 太嚴會讓 ANN recall 下降（搜尋空間縮小）
        → 要監控 per-filter 的 recall@k
```

**方向四：Contextual Compression**

```
Context 太長 → LLM 的 Lost-in-the-Middle 效應 → 中段資訊被忽略

解法：在送進 LLM 前，先壓縮每個 chunk，
     只保留和 Query 相關的部分

  原始 chunk（500 tokens）
       ↓ Compression Model
  壓縮後（150 tokens，只含相關部分）

  效果：同樣的 context window，塞進更多有效資訊
  代價：壓縮本身需要一次 LLM 呼叫
```

**方向五：評估 Pipeline（沒有量化就沒有改善）**

```
三個最重要的指標：

Context Recall
  「正確答案所需的資訊，有多少比例被 Retrieve 到了？」
  → 衡量 Retrieval 品質

Faithfulness
  「LLM 的回答，有多少比例忠於 Retrieved Context？」
  → 衡量幻覺程度

Answer Relevancy
  「回答和問題的相關程度」
  → 衡量整體回答品質

工具：RAGAS（開源）、Vertex AI Evaluation API
建議：每次改 Chunking / Embedding / Prompt，
     都跑一次評估再上線，不要憑感覺
```

---

## 六、Context Window 滿了怎麼辦

```
四種處理策略：

策略           做法                           適合場景
──────────────────────────────────────────────────────────────
Truncation    超過就截，最簡單                簡單問答，快速原型
Map-Reduce    每個 chunk 分別摘要，再合併摘要  需要跨多文件綜合的問題
Refine        依序處理，每次把前一個答案+新    需要累積推理的場景
              chunk 一起更新答案
Parent-Child  小塊搜尋，命中後帶回大塊上下文   答案需要完整段落語意

最根本的解法：
  如果頻繁 overflow → 回去看 Chunk Size 設計
  chunk 太大是最常見的根本原因
```

---

## 七、面試官地雷題

**地雷 1：「Hybrid Search 的 RRF 是什麼，為什麼不用加權平均？」**

```
答：RRF（Reciprocal Rank Fusion）用排名而不是原始分數融合，
    因為向量搜尋的分數（餘弦相似度）和 BM25 的分數（TF-IDF）
    量綱完全不同，直接加權平均沒有意義。
    RRF 把兩個排名都轉換成 1/(k + rank) 的分數，
    k=60 是常見預設，用來降低頭部排名的獨佔效應。
```

**地雷 2：「你說 Reranker 更準，那為什麼不一開始就用 Reranker 搜尋整個資料庫？」**

```
答：Cross-Encoder 需要把 (Query, Doc) 一起輸入模型，
    複雜度是 O(N)——有 10 萬份文件就要跑 10 萬次推理，不可行。
    Bi-Encoder 可以離線預先計算所有文件的 embedding，
    查詢時只做向量相似度計算，快很多。
    所以兩階段：Bi-Encoder 快速縮小到 Top-50，
    Cross-Encoder 精選到 Top-5。
```

**地雷 3：「RAG 的幻覺來自哪裡？加了 Context 就能完全消除嗎？」**

```
答：不能完全消除。RAG 減少的是「知識不足」造成的幻覺，
    但還有兩種幻覺 RAG 沒辦法防：
    1. LLM 忽略 Context，用自己的「記憶」回答（Faithfulness 問題）
    2. Retrieved Context 本身是錯的（資料庫有錯誤資訊）
    解法分別是：強化 Grounding Prompt 和建立資料品質審核機制。
```

---

## 八、面試回答完整示範

```
面試官期待的回答結構：

一句話定義（10 秒）：
「RAG 讓 LLM 在生成前先查外部知識庫，
 以減少幻覺並支援知識的即時更新。」

流程（30 秒）：
「整個流程是：用戶問題先做 Embedding，
 拿到向量後去 Vector DB 查最相關的 3-5 個 Chunk，
 把這些 Chunk 注入 Prompt，LLM 再根據這個 Context 回答。」

vs Fine-tuning（20 秒）：
「它跟 Fine-tuning 的核心差異是——
 RAG 適合知識需要頻繁更新、需要引用來源的場景；
 Fine-tuning 適合改變模型的推理模式或輸出格式。」

品質改善（1 分鐘）：
「如果回答品質不好，我會先診斷是 Retrieval 問題還是 Generation 問題。
 Retrieval 問題的改善方向是 Hybrid Search、Reranker、更好的 Chunking；
 Generation 問題的改善方向是 Faithfulness Prompt 和 Grounding 策略。
 改善前我會先建立評估 Pipeline，
 用 RAGAS 的 Context Recall 和 Faithfulness 作為基線指標。」
```

---

RAG 是 FDE 必考的第一題。  
面試官在意的不是你背了幾個工具名稱，  
而是你在遇到問題時，能不能系統性地定位根因，說清楚改善方向。

下一篇：[**Agent System Design**](/posts/fde-interview-guide-part2-agent-zh/) — 如何設計一個不會失控的 AI Agent 系統。
