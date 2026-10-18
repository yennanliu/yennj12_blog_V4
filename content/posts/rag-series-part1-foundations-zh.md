---
title: "RAG 完全指南（一）：入門與導讀 — 每個主題該去哪裡深入"
date: 2026-05-16T09:00:00+08:00
draft: false
weight: 1
description: "RAG 壞掉時多半是檢索壞掉。本篇把 RAG 管線拆成切塊、檢索、重排、評估四個決策，附最小可跑範例，並替每個主題指向站內最深入的那篇文章。"
categories: ["all", "ai", "engineering"]
tags: ["RAG", "LLM", "Vector Database", "Embeddings", "Python"]
authors: ["yen"]
readTime: "8 min"
aliases: ["/posts/rag-series-part3-advanced-retrieval-zh/", "/posts/rag-series-part4-optimization-zh/"]
---

> 大多數人的第一個 RAG 壞掉時，先改的是 prompt：「請根據以下資料回答，不要編造」。
> 改了三輪，答案還是錯——因為送進去的資料本來就不對。
> 真正該先問的是：正確的那段文字，有沒有出現在 top-k 裡？
> 沒有的話，再好的 prompt 也只是在請 LLM 從錯的資料裡掰出對的答案。

**這篇的主張只有一句：RAG 的失敗多半是檢索失敗，所以在動 prompt 之前，先把管線學成四個決策——怎麼切（chunking）、怎麼找（retrieval）、怎麼排（reranking）、怎麼量（evaluation）。**

這是系列的入門與導讀。站上已經有一批比本系列更深入的 RAG 文章（RAGFlow 原始碼導讀、FDE 核心主題、ChatPDF 優化實錄、AI 工程從零開始），每一節最後都有一行「深入請看 →」把你送到該主題最完整的那篇。原本的第三篇（進階檢索）與第四篇（查詢優化與 Context 壓縮）已併入這篇導讀，舊網址會自動轉到這裡。

---

## 一、為什麼 LLM 需要 RAG

LLM 的知識是**訓練時凍結的**：不知道截止日之後的事，不知道你公司的內部文件，而且對不確定的問題會編出聽起來合理的答案（幻覺）。

兩種補救方式：

| 方案 | 做什麼 | 適合 | 不適合 |
|------|--------|------|--------|
| Fine-tuning | 用你的資料再訓練一次模型 | 改變模型的語氣、格式、推理習慣 | 注入大量、會變動的事實知識 |
| RAG | 回答前先去外部知識庫查資料，把查到的片段放進 prompt | 知識常更新、需要引用來源、資料量大 | 需要改變模型「怎麼想」的場景 |

對多數企業應用，RAG 是起點。它的代價是：**答案品質上限由檢索品質決定**——這也是整篇的主軸。

---

## 二、把 RAG 管線看成四個決策

一個標準 RAG 系統分成離線的索引流程和即時的查詢流程。下圖標出四個決策點，之後的每一節對應一個：

```
離線：索引流程
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐
│ 原始文件 │──▶│ 文字擷取 │──▶│ ① 切塊       │──▶│ Embedding    │
│ PDF/網頁 │   │          │   │   chunking   │   │ → 向量資料庫 │
└──────────┘   └──────────┘   └──────────────┘   └──────┬───────┘
                                                        │
即時：查詢流程                                          │
┌──────────┐   ┌──────────────┐   ┌──────────────┐      │
│ 使用者   │──▶│ ② 檢索       │◀──│ 向量資料庫   │◀─────┘
│ 問題     │   │   top-k 候選 │   │ (+ BM25 索引)│
└──────────┘   └──────┬───────┘   └──────────────┘
                      ▼
               ┌──────────────┐   ┌──────────────┐   ┌──────────┐
               │ ③ 重排       │──▶│ 組 prompt    │──▶│ LLM 生成 │
               │   reranking  │   │ context+問題 │   │          │
               └──────────────┘   └──────────────┘   └────┬─────┘
                                                          ▼
                                                   ┌──────────────┐
                                                   │ ④ 評估       │
                                                   │   三個指標   │
                                                   └──────────────┘
```

注意生成（LLM）只佔一格。只有在 ②③ 把對的片段送進 prompt 之後，prompt 工程才有用武之地；④ 則是回頭告訴你 ①②③ 哪一個壞掉。

把它們當成「決策」而不是「步驟」，是因為每一個都有不只一種做法，而且換做法的時機取決於你的資料和查詢型態，不是看哪個技術比較新。

---

## 三、決策一：怎麼切（Chunking）

**直覺**：Embedding 把一段文字壓成一個向量。段落越長，向量就越「平均」，越難和任何一個具體問題對得上；段落太短，又會把一個完整的句意切成兩半，哪一半都答不了問題。

**機制**：切塊策略從簡到繁依序是固定長度 → 遞迴字元（先按段落、再按句子、最後按字元）→ 依文件結構（標題、表格、條列）→ 語意切塊（用 embedding 偵測話題轉折）→ 父子切塊（用小塊檢索、用大塊生成）。

**例子**：一份財報 PDF 裡的表格，用固定 500 字元切塊會把表頭和數字切到不同塊；依文件結構切塊會把整張表視為一個單位，表頭留在數字旁邊。

**何時會壞**：切塊的失敗在索引時就發生了，查詢時只會看到「找不到」或「找到一半」；因此它是四個決策裡最早該定、最晚才會被發現的一個。

深入請看 → [RAGFlow Part 2：DeepDoc 解析、Chunking 策略與 14 種模板](/posts/ragflow-intro-part2-deepdoc-chunking-zh/)（§五 `naive_merge` 切分契約）；動手版請看 [ChatPDF RAG 優化（一）：語意切塊與混合檢索](/posts/chatpdf-rag-optimization-part1-chunking-retrieval-zh/)。

---

## 四、向量資料庫怎麼選

切好的塊要存在能做近似最近鄰（ANN）搜尋的地方。選型的三個問題依序是：資料量多大（記憶體內就夠，還是需要分散式）、要不要 metadata 過濾（依租戶、日期、文件類型縮小搜尋範圍）、以及是否要自己維運。小型專案用嵌入式資料庫（如 Chroma）就能開始，換資料庫的成本主要在重新索引，而不是程式碼。

深入請看 → [RAG 完全指南（二）：Chunking 策略與向量資料庫選型](/posts/rag-series-part2-chunking-vectordb-zh/)，是站內唯一完整比較主流向量資料庫特性與選型決策樹的一篇。

---

## 五、決策二：怎麼找（Retrieval）

### 5.1 混合搜尋：語意加關鍵字

**直覺**：向量搜尋找的是「意思相近」，對「字面必須一樣」的查詢反而弱——產品型號、錯誤代碼、人名、法條編號。BM25 這類關鍵字檢索正好相反。

**機制**：兩條路各自取 top-k，再用 Reciprocal Rank Fusion（RRF）把兩份排名合併：每個文件的分數是它在各份排名裡 `1 / (k + rank)` 的總和，常見的 k 取 60。RRF 只看名次不看原始分數，所以不必先把餘弦相似度和 BM25 分數對齊到同一個尺度。

**何時會壞**：資料裡沒有太多專有名詞時，混合搜尋多出來的 BM25 路徑只增加延遲；反之，當使用者會貼錯誤訊息或型號來查，純向量搜尋的召回會明顯漏掉。

深入請看 → [FDE core topic：Hybrid Search & RRF](/posts/fde-core-concept-4-hybrid-search-rrf-zh/)（機制與實作層次）；生產環境的權重與查詢編譯請看 [RAGFlow Part 4：混合搜尋、Rerank、GraphRAG/RAPTOR 與引用](/posts/ragflow-intro-part4-retrieval-rerank-zh/) §二–三。

### 5.2 問題本身不好搜：查詢改寫、Self-RAG、Context 壓縮

有時候檢索失敗不是索引的錯，而是問題的形狀不適合直接搜：

- **查詢改寫（Multi-Query、HyDE、Step-Back）**：把一個問題改寫成多個版本、或先讓 LLM 寫一段「假設性答案」再拿去搜，提高命中的機會。代價是每次查詢多幾次 LLM 呼叫。
- **Self-RAG**：讓模型自己判斷「這題需要檢索嗎」「檢索到的東西有用嗎」「我的答案有被資料支持嗎」。這需要經過訓練的模型或對應的 judge prompt，不是接上去就有的功能。
- **Context 壓縮**：取回的 chunk 進 prompt 之前先刪掉無關的句子，避免「塞太多反而混淆模型」。

這三個都是在 ① ② 做對之後才值得加的；它們無法補救切錯的塊。

深入請看 → [AI 工程從零開始｜Phase 11 Part 2：RAG 系統與 LLM 評估](/posts/ai-eng-from-scratch-phase11-part2-rag-evals-zh/)（§二 何時該升級、§十 診斷流程）；壓縮策略的完整比較請看 [Context 壓縮與摘要 — 打造可無限對話的 AI 系統](/posts/context-compression-summarization-guide-zh/)。

---

## 六、決策三：怎麼排（Reranking）

**直覺**：向量搜尋用的是 bi-encoder——問題和文件各自編碼成向量，再比距離；它快，但「各自編碼」意味著它從未真正讀過問題和文件放在一起的樣子。Cross-encoder 把問題和文件串成一段輸入一起讀，判斷精準得多，但每一對都要跑一次模型，無法事先算好。

**機制**：先用便宜的向量／混合搜尋取 top-k（例如 50），再用 cross-encoder 對這 k 筆逐一打分，取前幾筆進 prompt。重排是「粗召回之後的精排」，不是取代召回；召回沒找到的東西，重排也救不回來。

**何時會壞**：延遲預算緊、且召回結果本來就只有幾筆時，重排只是多跑一次模型。候選一多（k 大）、或問題和文件用詞差距大時，它的價值才會顯現。

深入請看 → [FDE core topic：Re-ranking & Cross-Encoder](/posts/fde-core-concept-5-reranking-cross-encoder-zh/)；RAGFlow 三層重排的權重公式請看 [RAGFlow Part 4](/posts/ragflow-intro-part4-retrieval-rerank-zh/) §四。

---

## 七、決策四：怎麼量（Evaluation）

沒有量測，前三個決策就只能靠感覺調。RAG 評估的核心是把「答案好不好」拆成三段，每段對應管線的一個位置：

```
                 ┌─────────────────────────────────────┐
                 │  測試集：(問題, 標準答案或標準片段)  │
                 └───────────────┬─────────────────────┘
                                 ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ 問題     │──▶│ 檢索     │──▶│ 生成     │──▶ 答案
   └──────────┘   └────┬─────┘   └────┬─────┘      │
                       │              │            │
          Context 相關度│    忠實度    │   答案相關度│
          (取回的片段  │  (答案是否   │  (答案有沒有│
           和問題有關?)│   被片段支持)│   回到問題?)│
                       ▼              ▼            ▼
                 ┌─────────────────────────────────────┐
                 │  指標最差的那一段 → 回去改對應決策  │
                 │  Context 相關度低 → 改 ①②③          │
                 │  忠實度低        → 改 prompt / 模型 │
                 │  答案相關度低    → 改 prompt / 改寫 │
                 └─────────────────────────────────────┘
```

這張圖也是整篇主張的來源：三個指標裡只有一個（忠實度）主要靠 prompt 和模型處理，另外兩個的根因多半在檢索側。先看 context 相關度，再決定要不要碰 prompt。

RAGAS 之類的框架把這三個指標用 LLM-as-judge 自動化；也可以用傳統的 Hit@k、MRR、nDCG 單獨量檢索段，這部分不需要 LLM，便宜而且穩定。

深入請看 → [FDE core topic：RAG Triad Metrics](/posts/fde-core-concept-20-rag-triad-metrics-zh/)（三個指標的定義與可觀測性）；評估框架比較請看 [AI 工程從零開始｜Phase 11 Part 2](/posts/ai-eng-from-scratch-phase11-part2-rag-evals-zh/) §七；一條真的跑起來的評估管線請看 [ChatPDF RAG 優化（三）：可觀測性與評估](/posts/chatpdf-rag-optimization-part3-observability-eval-zh/)。RAGAS 的實際程式碼在本系列[第五篇](/posts/rag-series-part5-production-zh/)。

---

## 八、最小可跑的 RAG

下面是四個決策都取最簡單選項的版本：遞迴切塊、純向量檢索、不重排、不評估。它的用途是讓你看清四個決策各自在程式碼的哪一行，之後要換掉哪一個都知道從哪下手。範例僅示意，未在本文中實際執行。

```bash
pip install openai chromadb langchain-text-splitters
```

```python
import openai
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

client = openai.OpenAI()                      # 讀 OPENAI_API_KEY 環境變數
collection = chromadb.Client().create_collection("docs")
EMBED, CHAT = "text-embedding-3-small", "gpt-4o-mini"


def embed(text: str) -> list[float]:
    return client.embeddings.create(input=text, model=EMBED).data[0].embedding


def index(docs: list[str]) -> None:
    # 決策 ①：怎麼切。這裡用遞迴字元切塊，500 字元、重疊 50
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = [c for d in docs for c in splitter.split_text(d)]
    collection.add(
        documents=chunks,
        embeddings=[embed(c) for c in chunks],
        ids=[f"chunk_{i}" for i in range(len(chunks))],
    )


def retrieve(query: str, top_k: int = 3) -> list[str]:
    # 決策 ②：怎麼找。這裡只有向量搜尋；混合搜尋會在這裡多一條 BM25 路徑
    res = collection.query(query_embeddings=[embed(query)], n_results=top_k)
    return res["documents"][0]
    # 決策 ③：怎麼排。這裡沒有重排；cross-encoder 會插在 return 之前


def answer(query: str) -> str:
    context = "\n\n---\n\n".join(retrieve(query))
    prompt = (
        "請只根據【參考資料】回答【問題】；資料不足就說「無法回答」。\n\n"
        f"【參考資料】\n{context}\n\n【問題】\n{query}"
    )
    res = client.chat.completions.create(
        model=CHAT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return res.choices[0].message.content
    # 決策 ④：怎麼量。這裡沒有；評估會在 retrieve() 和 answer() 各掛一個指標
```

當它答錯時，先印出 `retrieve(query)` 的結果看對的片段在不在裡面——這一步就是整篇主張的實作版本。在就改 prompt；不在就回到 ① ② ③。

---

## 九、再往前：GraphRAG 與生產環境

**GraphRAG**：向量搜尋擅長「找一段和問題相似的文字」，不擅長「A 和 B 有什麼共同點」這種要跨多份文件串連的問題。GraphRAG 先從文件抽出實體和關係建成圖，查詢時沿著圖走；代價是建圖階段的 LLM 呼叫量和維護成本都遠高於一般索引，所以它是問題驅動的加法，不是預設選項。

深入請看 → [RAGFlow Part 4](/posts/ragflow-intro-part4-retrieval-rerank-zh/) §5.1 GraphRAG 與 §5.2 RAPTOR。

**生產環境與 Agentic RAG**：把評估變成自動化流程、讓 Agent 決定何時檢索、檢索什麼、要不要再查一次。

深入請看 → [RAG 完全指南（五）：生產級評估、GraphRAG 與 Agentic RAG](/posts/rag-series-part5-production-zh/)（RAGAS 與 LangGraph 的完整程式碼）。

---

## 十、小結

- RAG 答錯時，先檢查 top-k 裡有沒有正確片段；沒有的話問題不在 prompt。
- 把管線當四個決策學：怎麼切、怎麼找、怎麼排、怎麼量。每一個都有便宜版和精準版，換版本的時機取決於資料和查詢型態。
- 切塊的錯誤在索引時就定了，是最早該決定、最晚才會被發現的一個。
- 重排是召回之後的精排，救不回沒被召回的東西；查詢改寫與壓縮也一樣，都是 ①② 做對之後的加法。
- 評估的三個指標各對應管線一段；指標最差的那段，才是該動的地方。

### 相關文章

站內 RAG 主題的深入版本，依管線順序：

- 切塊與文件解析：[RAGFlow Part 2 — DeepDoc 解析與 Chunking](/posts/ragflow-intro-part2-deepdoc-chunking-zh/)、[ChatPDF RAG 優化（一）](/posts/chatpdf-rag-optimization-part1-chunking-retrieval-zh/)
- 向量資料庫選型：[RAG 完全指南（二）](/posts/rag-series-part2-chunking-vectordb-zh/)
- 混合搜尋與 RRF：[FDE core topic — Hybrid Search & RRF](/posts/fde-core-concept-4-hybrid-search-rrf-zh/)、[RAGFlow Part 4](/posts/ragflow-intro-part4-retrieval-rerank-zh/)
- 查詢改寫、Self-RAG、Context 壓縮：[AI 工程從零開始 Phase 11 Part 2](/posts/ai-eng-from-scratch-phase11-part2-rag-evals-zh/)、[Context 壓縮與摘要](/posts/context-compression-summarization-guide-zh/)
- 重排：[FDE core topic — Re-ranking & Cross-Encoder](/posts/fde-core-concept-5-reranking-cross-encoder-zh/)
- 評估：[FDE core topic — RAG Triad Metrics](/posts/fde-core-concept-20-rag-triad-metrics-zh/)、[ChatPDF RAG 優化（三）](/posts/chatpdf-rag-optimization-part3-observability-eval-zh/)
- GraphRAG / RAPTOR：[RAGFlow Part 4](/posts/ragflow-intro-part4-retrieval-rerank-zh/) §五
- 生產與 Agentic RAG：[RAG 完全指南（五）](/posts/rag-series-part5-production-zh/)
- 完整開源實作的全景（RAGFlow 系列總覽）：[RAGFlow Intro Part 1 — 全景架構](/posts/ragflow-intro-part1-overview-architecture-zh/)

---

**系列導覽**

- **第一篇（本篇）**：入門與導讀
- [第二篇](/posts/rag-series-part2-chunking-vectordb-zh/)：Chunking 策略與向量資料庫選型
- 第三、四篇（進階檢索、查詢優化與 Context 壓縮）已併入本篇導讀；深入請看上方「相關文章」
- [第五篇](/posts/rag-series-part5-production-zh/)：生產級 RAG 評估與 Agentic RAG
