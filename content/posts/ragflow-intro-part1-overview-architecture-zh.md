---
title: "RAGFlow Intro Part 1 — 全景架構 — 從一份 PDF 到一句帶引用的答案"
date: 2026-09-10T09:00:00+08:00
draft: false
weight: 1
description: "RAGFlow 原始碼導讀系列第一篇：用一張全景圖與兩條資料路徑，說清楚這個 9 萬星的開源 RAG 引擎由哪些子系統組成、一份 PDF 進來之後經過哪些階段、以及它在架構上做了哪些與眾不同的取捨。"
categories: ["all", "ai", "engineering"]
tags: ["RAGFlow", "RAG", "AI", "Architecture", "Open Source", "Elasticsearch", "Vector Database", "繁體中文"]
authors: ["yen"]
readTime: "24 min"
---

> *大多數人讀 RAG 開源專案的方式，是打開 README，跑 `docker compose up`，上傳一份 PDF，看到答案出來就說「我懂了」。*
> *真正的答案是：一個生產級 RAG 引擎有 80% 的複雜度不在「呼叫 LLM」那一行，而在資料怎麼被解析、怎麼被切、怎麼被編碼、怎麼被存、怎麼被取回、以及取回之後怎麼證明它沒有胡說。*
> *Demo 只需要 200 行。引擎需要一整套子系統。*
> *這個系列拆解的是後者。*

---

## 前言：這個系列要做什麼

[RAGFlow](https://github.com/infiniflow/ragflow)（InfiniFlow，Apache-2.0，2023-12-12 開源）是目前最受關注的開源 RAG 引擎之一：GitHub 上約 **9.0 萬顆星、1.06 萬 fork**，官方定位是「a leading open-source RAG engine that fuses cutting-edge RAG with Agent capabilities to create a superior context layer for LLMs」。

它值得逐層讀完，理由不是星星數，而是：**它把 RAG 每一個環節都實作成可替換的元件，而且每個選擇背後都有明確的理由。** 讀它等於讀一份「RAG 系統設計的參考答案」。

這個系列分成五篇：

| Part | 主題 | 對應原始碼 |
|---|---|---|
| **Part 1（本篇）** | 全景架構、資料的兩條路徑、部署形態 | `docker/`、`conf/`、整體 |
| Part 2 | 資料進場：DeepDoc 解析與 Chunking 策略 | `deepdoc/`、`rag/app/`、`rag/nlp/` |
| Part 3 | Encode 與 Save：向量化、索引 Schema、雙引擎抽象 | `conf/mapping.json`、`rag/utils/*_conn.py` |
| Part 4 | Decode 與檢索：混合搜尋、Rerank、GraphRAG/RAPTOR、引用 | `rag/nlp/search.py`、`rag/nlp/query.py` |
| Part 5 | 系統與程式碼結構：服務分層、Task Executor、Go 遷移 | `api/`、`rag/svr/`、`internal/` |

本篇的目標很單純：**讀完之後，你能在腦中畫出 RAGFlow 的方塊圖，並且知道每個方塊的名字對應到哪個目錄。**

---

## 一、核心問題：naive RAG 在哪裡壞掉

先講清楚 RAGFlow 存在的理由。一個「教學版 RAG」長這樣：

```
PDF ──pdfminer──▶ 純文字 ──每 512 token 切一刀──▶ embedding ──▶ 向量庫
                                                                    │
問題 ──embedding──▶ top-5 餘弦相似 ◀──────────────────────────────────┘
                        │
                        ▼
                   丟給 LLM 生成
```

這條管線在 demo 資料上可以跑，在真實企業資料上會在四個地方同時壞掉：

**壞點一：解析階段就已經失去資訊。** 掃描版 PDF 出來是空字串；有跨頁表格的財報，欄位會全部混成一行；雙欄排版的論文，左右兩欄的句子會交錯黏在一起。**後面所有環節都在處理一份已經壞掉的文字。**

**壞點二：固定長度切分無視語意邊界。** 512 token 一刀切，會把「問題」和「答案」切開，把表頭和資料列切開，把條款編號和條款內容切開。切壞的 chunk 無論用多好的 embedding 都救不回來。

**壞點三：單一向量召回沒有精確匹配能力。** 使用者查「型號 RTX-4090D 的功耗」，向量模型可能覺得「RTX-4080」也很像。**專有名詞、料號、法條編號這類查詢，需要的是關鍵字精確匹配，不是語意近似。**

**壞點四：無法證明答案的來源。** 使用者問「這個數字哪來的？」，系統答不出來。在合規、法務、財務場景，不能溯源等於不能用。

RAGFlow 的四個核心主張，正好一一對應：

| RAGFlow 主張 | 對應壞點 | 實作位置 |
|---|---|---|
| **Deep document understanding** — 用視覺模型理解版面，而不是只抽文字 | 壞點一 | `deepdoc/vision/` |
| **Template-based chunking** — 依文件類型選切分模板，且切分結果可視化、可人工介入 | 壞點二 | `rag/app/`（14 種模板） |
| **Multiple recall + fused re-ranking** — 關鍵字與向量雙路召回後融合重排 | 壞點三 | `rag/nlp/search.py` |
| **Grounded citations** — 答案的每一句話回頭對齊到來源 chunk | 壞點四 | `Dealer.insert_citations()` |

README 把前兩點總結成一句話：**"Quality in, quality out."** 這句話是整個專案的設計主軸——**與其在檢索端補救，不如在入場端就不要弄壞資料。**

---

## 二、全景圖：七個子系統

以下是 RAGFlow 的方塊圖。每個方塊我都標了對應的原始碼目錄，之後四篇會逐個拆開。

```
                          ┌──────────────────────────────┐
                          │  Web UI (React + TS + Vite)  │
                          │            web/              │
                          └───────────────┬──────────────┘
                                          │ HTTP (nginx :80/:443)
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 ▼                                 │
        │  ┌────────────────┐   ┌──────────────────┐   ┌─────────────────┐  │
        │  │  API Server    │   │  Admin Server    │   │  MCP Server     │  │
        │  │  api/  :9380   │   │  admin/  :9381   │   │  mcp/    :9382  │  │
        │  └───────┬────────┘   └──────────────────┘   └─────────────────┘  │
        │          │  ① 寫 task 到佇列                                       │
        │          ▼                                                        │
        │  ┌─────────────────────────────────────────────────────────────┐  │
        │  │  Redis Stream 佇列 "te" / group "rag_flow_svr_task_broker"  │  │
        │  └───────┬─────────────────────────────────────────────────────┘  │
        │          │  ② N 個 consumer 搶任務                                 │
        │          ▼                                                        │
        │  ┌─────────────────────────────────────────────────────────────┐  │
        │  │  Task Executor  ×N     rag/svr/task_executor.py             │  │
        │  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────┐ ┌─────────┐  │  │
        │  │  │ DeepDoc │▶│ Chunker │▶│ Embedding│▶│ Save │ │ GraphRAG│  │  │
        │  │  │deepdoc/ │ │rag/app/ │ │ rag/llm/ │ │      │ │ RAPTOR  │  │  │
        │  │  └─────────┘ └─────────┘ └──────────┘ └──────┘ └─────────┘  │  │
        │  └───────┬──────────────────────┬──────────────────────────────┘  │
        └──────────┼──────────────────────┼─────────────────────────────────┘
                   │                      │
      ┌────────────┼──────────────┬───────┴────────┬───────────────────┐
      ▼            ▼              ▼                ▼                   ▼
┌───────────┐ ┌─────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────┐
│  MySQL    │ │  MinIO  │ │  Doc Engine  │ │  Redis /     │ │  外部 LLM 供應商│
│ 中介資料  │ │ 原始檔  │ │ ES / Infinity│ │  Valkey      │ │ chat/embedding │
│           │ │ + 圖片  │ │ chunk + 向量 │ │ 快取 + 佇列  │ │ rerank/ocr/tts │
└───────────┘ └─────────┘ └──────────────┘ └──────────────┘ └────────────────┘
```

七個子系統，一句話各自的職責：

1. **API Server（`api/`）** — Quart（async Flask）寫的 REST API，處理登入、知識庫 CRUD、上傳、對話。它**不做重活**：所有解析與索引都是丟到佇列。
2. **Task Executor（`rag/svr/task_executor.py`）** — 真正幹活的 worker，93 KB 的單一檔案（是的，很大），從 Redis Stream 拉任務，跑完整條 ingestion 管線。可以水平開 N 個。
3. **DeepDoc（`deepdoc/`）** — 文件理解層，分 `vision/`（OCR、版面辨識、表格結構辨識）與 `parser/`（各格式解析器）。Part 2 主角。
4. **Chunking + Retrieval NLP（`rag/app/`、`rag/nlp/`）** — 14 種切分模板、分詞器、查詢編譯器、混合檢索與重排。Part 2 與 Part 4 主角。
5. **Doc Engine（可插拔）** — chunk 與向量的家。預設 Elasticsearch 8.11.3，可換 Infinity、OpenSearch、OceanBase、SereneDB、GaussDB。Part 3 主角。
6. **Agent / Pipeline（`agent/`、`rag/flow/`）** — 兩套 DAG 執行引擎：`agent/canvas.py` 跑對話型 agent 工作流，`rag/flow/pipeline.py` 跑可編排的 ingestion 管線。Part 5 主角。
7. **Model Layer（`rag/llm/`）** — 把 chat / embedding / rerank / vision / OCR / TTS / ASR 七類模型抽象成統一介面，背後接數十家供應商。

---

## 三、資料的兩條路徑

RAGFlow 只有兩條主要資料流。看懂這兩條，整個系統就通了。

### 3.1 Ingestion 路徑（寫入）

```
使用者上傳 report.pdf
        │
        ▼
① API Server：檔案存進 MinIO，MySQL 寫 document 列（status=UNSTART）
        │
        ▼
② API Server：往 Redis Stream "te" 推一則訊息 {id, doc_id, task_type:"dataflow", ...}
        │
        ▼
③ Task Executor：consumer group 搶到訊息，用 msg["id"] 回 MySQL 撈完整 task 列
        │
        ▼
④ DeepDoc 解析：PDF → OCR → 版面辨識（10 類）→ 表格結構辨識 → 帶版面座標的 sections
        │
        ▼
⑤ Chunking：依 parser_id 選模板（naive / paper / manual / laws / qa / table …）
   切分契約：delimiter "\n!?;。；！？" + chunk_token_num + MergeStrategy
        │
        ▼
⑥ Chunk 加值（可選、每項都是一次 LLM 呼叫）：
   keyword_extraction / question_proposal / content_tagging / auto-metadata / TOC
        │
        ▼
⑦ Embedding：vec = 0.1 × embed(檔名) + 0.9 × embed(內容)，寫進 q_{dim}_vec 欄位
        │
        ▼
⑧ 寫入 Doc Engine：索引 ragflow_{tenant_id}，圖片另存 MinIO，進度回寫 MySQL
        │
        ▼
⑨ 選配的第二階段任務（各自是獨立 task type）：
   RAPTOR 摘要樹 / GraphRAG 知識圖 / Mindmap / Wiki / Skill …
```

三個值得先記住的細節：

- **佇列裡只放 ID，不放內容。** 訊息體極小，任務狀態的唯一真實來源是 MySQL 的 `task` 表。Executor 拿到訊息第一件事是 `TaskService.get_task(msg["id"])`，並檢查 `has_canceled()`。
- **進度是一個 0.0～1.0 的浮點數 + 一段訊息字串**，由 `set_progress()` 一路回寫。Embedding 階段的進度公式寫死在程式裡：`0.7 + 0.2 × (i+1)/len(cnts)`——也就是說，UI 上看到 70%～90% 就是在做向量化。
- **RAPTOR、GraphRAG 不是 ingestion 的一部分**，它們是 KB 層級的 fan-out 任務，用一個假的 `doc_id` sentinel 標記，參與的文件放在 `task["doc_ids"]`。

### 3.2 Query 路徑（讀取）

```
使用者問：「Q3 的毛利率是多少，跟去年比？」
        │
        ▼
① 問句改寫（可選）：
   refine_multiturn → full_question()  把多輪對話壓成一個獨立問句
   cross_languages  → 跨語言擴寫
   keyword          → LLM 抽關鍵字加進查詢
        │
        ▼
② 查詢編譯：FulltextQueryer.question()
   分詞 → 停用詞移除 → term weighting → 同義詞擴展 → bigram 短語
   產出加權布林查詢，欄位 boost：important_kwd^30 > question_tks^20 > title_tks^10 > content_ltks^2
        │
        ▼
③ 雙路召回（一次請求打進 Doc Engine）
   ┌──────────────────┐        ┌──────────────────┐
   │ 全文檢索（BM25 變體）│       │ 向量 KNN         │
   │ 自訂 scripted_sim │        │ top_k 1024       │
   │                  │        │ candidates 2048  │
   └────────┬─────────┘        └─────────┬────────┘
            └──────────┬─────────────────┘
                       ▼ weighted_sum 融合
        │
        ▼
④ 本地重排：sim = 0.3 × token相似度 + 0.7 × 向量相似度 + rank_feature
   （rank_feature = tag 特徵 cosine × 10 + PageRank）
        │
        ▼
⑤ Cross-encoder rerank（可選）：對前 64 個候選做精排
        │
        ▼
⑥ 進階召回（可選）：GraphRAG 實體/關係/社群、RAPTOR 摘要層、TOC 增強、metadata 過濾
        │
        ▼
⑦ 組 prompt：kb_prompt() 用 max_tokens × 0.97 當預算，塞不下就截斷並記警告
        │
        ▼
⑧ LLM 生成（串流）
        │
        ▼
⑨ 事後引用對齊：insert_citations() 把答案切句，每句與 chunk 做混合相似度比對
   閾值從 0.63 開始，每輪 ×0.8 降到 0.3，每句最多掛 4 個 [ID:n]
```

**第 ⑨ 步是 RAGFlow 最有辨識度的設計。** 多數 RAG 系統的做法是在 prompt 裡拜託 LLM「請標註引用」，然後祈禱它照做。RAGFlow 反過來：**讓 LLM 自由生成，生成完之後用向量比對「反查」每一句話出自哪個 chunk。** 引用因此不依賴 LLM 的服從度。Part 4 會細講這個機制的代價（要對答案的每一句再做一次 embedding）。

---

### 3.3 誰存什麼：四個儲存的分工

兩條路徑會反覆碰到四個儲存。它們的分工是理解整個系統的關鍵，而且分工非常乾淨：

| 儲存 | 存什麼 | 是真實來源嗎 | 掉了會怎樣 |
|---|---|---|---|
| **MySQL** | 使用者、租戶、知識庫、文件、任務、對話、模型設定 | ✅ 是 | 系統無法運作 |
| **MinIO / S3** | 使用者上傳的原始檔、DeepDoc 切出的圖片 | ✅ 是 | 無法重新解析、UI 看不到原文 |
| **Doc Engine** | chunk 文字、向量、排序特徵、知識圖節點 | ❌ 可重建 | 檢索失效，但可從上面兩者重跑 |
| **Redis / Valkey** | 任務佇列、LLM 回應快取、同義詞表、分散式鎖、session | ⚠️ 混合 | **系統整體停擺**（不只是快取失效） |

**兩個常被誤解的點**：

第一，**doc engine 不是真實來源。** 它裡面的一切都可以從 MySQL（知道有哪些文件、用什麼參數）+ MinIO（原始檔）重新產生。這就是為什麼預設 `number_of_replicas: 0` 不算太瘋狂——代價是「重新解析一次」，不是「資料永久遺失」。備份的重點是 MySQL 和 MinIO。

第二，**Redis 不只是快取。** 它同時是佇列、快取、鎖和 session store。很多人以為 Redis 掛了只是「變慢」，但在 RAGFlow 裡，Redis 掛了等於任務系統死亡 + 登入態失效。Phase 3 一定要做 Redis 叢集。


## 四、三個演進階段

RAGFlow 的部署形態可以直接對應到三個規模階段。以下每一階段都是 `docker/.env` 裡幾個變數的組合。

### ╔══ Phase 1：POC（單機 / < 1 萬 chunk / 1～5 人） ══╗

```
┌──────────────────────────────────────────────────┐
│  單一 Docker 主機（4 core / 16 GB / 50 GB）        │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ ragflow 容器                                │  │
│  │  nginx + api_server + admin + 1×executor   │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────┐ ┌────────┐ ┌───────┐ ┌──────────┐ │
│  │ ES 8.11.3│ │ MySQL  │ │ MinIO │ │ Valkey 8 │ │
│  │  8 GB    │ │  8.0   │ │       │ │          │ │
│  └──────────┘ └────────┘ └───────┘ └──────────┘ │
└──────────────────────────────────────────────────┘
```

- `.env` 設定：`DOC_ENGINE=elasticsearch`、`DEVICE=cpu`、`METADATA_DB_PROFILE=mysql`
- Embedding 用外部 API（智譜、OpenAI、SiliconFlow…），不佔本機 GPU
- **可接受的捷徑**：單 executor（一次只解析一份文件）、ES 單節點 0 replica、MinIO 單盤
- **解決的問題**：能跑通、能上傳、能問答、能看到 chunk 長什麼樣
- **剩下的問題**：一份 300 頁掃描 PDF 會塞住整個佇列；ES 掉了就全掉；`vm.max_map_count` 沒調就啟動失敗

實務數字：ES 容器 `MEM_LIMIT` 預設 8 GB（`.env` 裡是 `8073741824`），所以 16 GB 是硬底線，不是建議值。

### ╔══ Phase 2：MVP（10 萬～百萬 chunk / 一個團隊） ══╗

```
┌───────────────┐   ┌──────────────────────────────────────┐
│ nginx / LB    │──▶│ api_server × 2（無狀態，可直接複製）  │
└───────────────┘   └───────────────────┬──────────────────┘
                                        │ Redis Stream "te"
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
┌────────────────┐            ┌────────────────┐            ┌────────────────┐
│ executor host A│            │ executor host B│            │ executor host C│
│ WORKERS=4      │            │ WORKERS=4      │            │ GPU: DEVICE=gpu│
│ (一般任務)      │            │ (一般任務)      │            │ (OCR/版面辨識) │
└────────────────┘            └────────────────┘            └────────────────┘
        └───────────────────────────────┼───────────────────────────────┘
                                        ▼
              ┌──────────────────────────────────────────────┐
              │ ES 3 節點 / MySQL 主從 / MinIO 分散式         │
              └──────────────────────────────────────────────┘
```

- 新增元件 vs Phase 1：**多台 executor 主機**（`--host-id` + `--consumer-no-beg/end` 切開 consumer 編號）、**GPU executor** 專跑 DeepDoc、**ES 叢集**
- 關鍵設定：`entrypoint.sh` 的 `WORKERS`（每台幾個 executor 進程）、`CONSUMER_NO_BEG/END`（避免多台機器的 consumer 名字撞號）
- **解決的問題**：解析吞吐可線性擴充；重文件不再堵住輕文件；ES 單點消失
- **剩下的問題**：GPU 機器成本；LLM 加值步驟（關鍵字、問題生成、標籤）的 token 帳單開始有感；ES 的 BM25 與向量融合只能用「近似」權重（Part 4 詳談）

成本感受：假設 5 萬份文件、平均 40 chunk/份 = 200 萬 chunk。**若開啟 `question_proposal` + `keyword_extraction` + `content_tagging`，那是 600 萬次 LLM 呼叫。** 這是 Phase 2 最容易失控的一筆帳，也是為什麼這三個開關預設都是關的。

### ╔══ Phase 3：Scale（多租戶 / 千萬 chunk 以上） ══╗

```
┌──────────────────────────────────────────────────────────────────┐
│                    Kubernetes（repo 內含 helm/）                  │
│                                                                  │
│  ┌────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ api (HPA)  │  │ go api server │  │ executor pool（分池）     │ │
│  │            │  │ :9384         │  │ common / gpu / graphrag   │ │
│  └────────────┘  └───────────────┘  └──────────────────────────┘ │
│         │                │                       │               │
│         └────────────────┴───────────────────────┘               │
│                          ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Doc Engine：Infinity（原生多路融合）或 ES 叢集              │  │
│  │ 索引隔離：每個 tenant 一個索引 ragflow_{tenant_id}          │  │
│  │ 過濾隔離：kb_id 作 low-cardinality secondary index          │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐ ┌────────┐ │
│  │  MySQL   │ │ MinIO/S3 │ │ Valkey  │ │ Jaeger    │ │Langfuse│ │
│  │ 或 Gauss │ │ /OSS/GCS │ │ 叢集    │ │ 分散式追蹤│ │LLM 觀測│ │
│  └──────────┘ └──────────┘ └─────────┘ └───────────┘ └────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

- 新增元件 vs Phase 2：**Go server**（`API_PROXY_SCHEME=go|hybrid`，把熱路徑換成 Go 實作，Part 5 詳談）、**Infinity** 取代 ES（原生 weighted-sum 融合，不需要第二次 KNN 回查）、**executor 分池**（`-t` 參數指定 task type，讓 GraphRAG 這種吃 LLM 的任務不擠壓一般解析）、**Jaeger + Langfuse** 觀測
- **解決的問題**：多租戶隔離、融合精度、尾延遲、成本歸屬
- **剩下的問題**：Go/Python 雙實作的一致性維護（repo 裡 `AGENTS.md` 明文要求「converge to one path」）；Infinity 的生態成熟度低於 ES

### 三階段對照

| 維度 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| chunk 量級 | < 1 萬 | 10 萬～100 萬 | 1000 萬+ |
| 進程數 | 1 容器全包 | api×2 + executor×12 | K8s，分池 HPA |
| Doc Engine | ES 單節點 | ES 3 節點 | Infinity 或 ES 叢集 |
| Metadata DB | MySQL 8.0 單機 | MySQL 主從 | MySQL / GaussDB |
| 部署複雜度 | `docker compose up` | compose + 多主機參數 | Helm chart |
| 硬體底線 | 4c / 16 GB | 3 台 + 1 GPU | 依租戶數線性 |
| 主要瓶頸 | 解析吞吐 | LLM token 成本 | 融合精度與尾延遲 |

---

## 五、關鍵設計哲學：三個「不一樣」的選擇

讀 RAGFlow 時，有三個決定會反覆出現，值得先講。

### 5.1 索引以 tenant 為單位，不是以知識庫為單位

```python
def index_name(uid):
    return f"ragflow_{uid}"   # uid = tenant_id
```

一個租戶一個索引，知識庫用 `kb_id` 欄位過濾（在 Infinity 裡明確標成 `{"type": "secondary", "cardinality": "low"}`）。

**為什麼不是一個 KB 一個索引？** 因為 ES 每個索引都有固定開銷（預設 2 shard），使用者建 500 個知識庫就會生出 1000 個 shard，叢集直接跪。以 tenant 切、以欄位濾，是在「隔離強度」與「叢集健康」之間選了後者。**代價是跨 KB 查詢很便宜，但單一 KB 的刪除是一次大範圍 delete-by-query。**

### 5.2 欄位名稱本身就是 Schema

RAGFlow 的 ES mapping（`conf/mapping.json`）幾乎沒有寫死任何欄位，全靠 19 條 dynamic template 用**後綴**決定型別：

| 後綴 | 型別 | 用途 |
|---|---|---|
| `*_tks` / `*_ltks` | text（whitespace analyzer） | 已分好詞的 token 串 |
| `*_kwd` / `*_id` / `*_ids` | keyword（boolean similarity） | 精確匹配欄位 |
| `*_int` / `*_flt` / `*_long` | 數值 | 頁碼、座標、排序 |
| `*_512_vec` … `*_1536_vec` | dense_vector（cosine） | 向量，維度寫在名字裡 |
| `*_fea` / `*_feas` | rank_feature(s) | PageRank、標籤特徵 |
| `*_with_weight` | text, index=false | 只存不索引的原文 |

所以 embedding 完之後那行 `d["q_%d_vec" % len(v)] = v`——**維度是 768 就自動變成 `q_768_vec`，命中 `*_768_vec` 模板，自動成為 768 維 cosine 向量欄位。** 換 embedding 模型不需要改 mapping。Part 3 會完整拆這張表。

### 5.3 Chunk 是給人看的，不只是給機器用的

README 的 "Visualization of text chunking to allow human intervention" 不是行銷詞。`chunk_api.py` 提供 chunk 的 CRUD，UI 可以逐一檢視、編輯、停用（`available_int`）、加關鍵字（`important_kwd`）、加問句（`questions`）。而這些人工欄位在檢索時有**極高權重**：`important_kwd^30`、`question_tks^20`，本地重排時 token 還要再乘（`important_kwd × 5`、`question_tks × 6`）。

**這是一個明確的產品判斷：與其追求全自動，不如讓人的一次修正產生 30 倍槓桿。**

---

### 5.4 每一個貴的功能都預設關閉

RAGFlow 有一長串「打開之後品質會變好」的功能：`keyword_extraction`、`question_proposal`、`content_tagging`、`gen_metadata`、`build_TOC`、RAPTOR、GraphRAG、`refine_multiturn`、`cross_languages`、`toc_enhance`、rerank 模型、web search。

**它們預設全部關閉。**

這不是保守，是一個關於「誰該決定付錢」的立場。這些功能的成本結構是：

```
一次性成本（ingestion 時）             每次查詢成本
──────────────────────────────────    ──────────────────────────────
keyword_extraction   每 chunk 一次     refine_multiturn   +1 次 LLM
question_proposal    每 chunk 一次     cross_languages    +1 次 LLM
content_tagging      每 chunk 一次     keyword            +1 次 LLM
gen_metadata         每文件一次        toc_enhance        +1 次 LLM
build_TOC            每文件一次        rerank 模型        +150~400ms
RAPTOR               分群 + 每群摘要   web search         +外部 API
GraphRAG             每 chunk 1~3 次
                     + 實體消解 + 社群報告
```

以 200 萬 chunk 的知識庫為例，開三個 chunk 級加值 = **600 萬次 LLM 呼叫**。這不是「一個優化選項」，這是一筆需要被批准的預算。

**設計原則：預設值應該是「能跑、便宜、可預測」，而不是「效果最好」。** 想要更好的效果，使用者必須明確打開開關——那時他就知道自己在買什麼。

這也是我認為 RAGFlow 值得學的一個產品判斷。很多 RAG 框架的預設值是「把所有能提升品質的東西都打開」，結果新使用者第一次上傳文件就收到一張看不懂的帳單。


## 六、為什麼選 X 不選 Y

以下六個決定會貫穿整個系列。

```
決定                選 X 的理由                          不選 Y 的理由 / Y 更好的時機
──────────────────────────────────────────────────────────────────────────────────
Elasticsearch      生態成熟、運維人力好找、dynamic         Infinity：原生 tensor + 多路融合、
（預設）            template 讓 schema 免維護、             延遲更低，但生態新、除錯資料少
vs Infinity        highlight/aggregation 現成              ▶ 翻轉點：融合精度成為瓶頸、
                                                            或 QPS 高到 ES 成本不可接受時換 Infinity

Redis Stream       已經有 Redis（快取/分散式鎖都用它），    Celery：多一組 broker + backend 要維運；
vs Celery/MQ       consumer group 天生支援多 worker 搶單、  RabbitMQ：吞吐更好但運維面積更大
                   unacked 訊息可重新投遞、訊息體只有 ID    ▶ 翻轉點：需要延遲任務、複雜路由、
                                                            或跨資料中心投遞時

MinIO / S3         chunk 要能回頭取原始檔與圖片切片，       本機磁碟：executor 一旦水平擴充就
vs 本機磁碟         物件儲存讓 executor 完全無狀態          必須共享檔案系統，NFS 又是新單點
                                                          ▶ 翻轉點：永遠單機部署時可省掉

模板化 chunking     法條、論文、履歷、表格的結構假設         純遞迴切分：實作 50 行、零設定，
vs 純遞迴切分       完全不同，一套規則不可能都對；          但在結構化文件上召回率差一截
                   14 種模板讓使用者選對假設                ▶ 翻轉點：文件同質性極高（例如全是
                                                            部落格文章）時，遞迴切分夠用

自建 DeepDoc       ONNX 模型跑在 CPU 上，成本可預測、       純 VLM 解析：品質上限更高，但每頁
（ONNX）           不依賴外部 API、單頁成本 ≈ 0；          都是一次多模態呼叫，1 萬頁的帳單
vs 全部丟 VLM       版面/表格結構是結構化輸出，不是自由文字   會嚇到人
                                                          ▶ 翻轉點：文件量小但版面極端複雜
                                                            （手寫、圖表為主）時開 VLM 增強

事後引用對齊        不依賴 LLM 服從指令、換模型不會壞、     要求 LLM 自己標引用：零額外成本，
vs prompt 要求      引用是可驗證的相似度分數                但小模型經常亂標或不標
LLM 標引用                                                ▶ 翻轉點：只用頂級模型且延遲敏感時，
                                                            prompt 方案更省一次 embedding
```

---

## 七、實際跑起來：你會用到的埠與 profile

這一段是給打算動手的人。RAGFlow 的 compose 用 **profile** 控制要起哪些服務，`.env` 裡這行是總開關：

```bash
COMPOSE_PROFILES=${DOC_ENGINE},${DEVICE},metadata-${METADATA_DB_PROFILE}
# 預設展開成：elasticsearch,cpu,metadata-mysql
```

換 doc engine 不用改 compose 檔，只要改 `DOC_ENGINE=infinity`，profile 就會起 Infinity 而不起 ES。**這是一個很乾淨的多後端切換設計**——同一份 compose 支援 6 種 doc engine、3 種 metadata DB、CPU/GPU 兩種 device。

埠位一覽（容器內埠）：

| 埠 | 服務 | 說明 |
|---|---|---|
| 80 / 443 | nginx | Web UI 與 API 入口 |
| 9380 | Python API server | `api/ragflow_server.py` |
| 9381 | Python admin server | `admin/server/admin_server.py` |
| 9382 | MCP server | 需 `--enable-mcpserver` 才啟動 |
| 9383 | Go admin server | `bin/ragflow_server --admin` |
| 9384 | Go API server | `bin/ragflow_server --api` |
| 1200 / 9200 | Elasticsearch | 主機埠 1200 → 容器 9200 |
| 1201 | OpenSearch | 替代方案 |
| 23817 / 23820 | Infinity | Thrift / HTTP |
| 3306 | MySQL | metadata |
| 9000 | MinIO | 物件儲存 |

啟動前的兩個必做動作（漏掉就啟動失敗，這是 issue 區最常見的問題）：

```bash
sysctl vm.max_map_count            # 必須 >= 262144，否則 ES 起不來
sudo sysctl -w vm.max_map_count=262144
```

環境需求：CPU ≥ 4 核、RAM ≥ 16 GB、磁碟 ≥ 50 GB、Docker ≥ 24.0.0、Docker Compose ≥ v2.26.1、Python ≥ 3.13（從原始碼跑時）。要用 code executor（agent 的沙箱）還需要 **gVisor**。

---

### 7.1 最小可跑流程

```bash
git clone https://github.com/infiniflow/ragflow.git
cd ragflow/docker

# 確認 vm.max_map_count（ES 需要）
sysctl vm.max_map_count || sudo sysctl -w vm.max_map_count=262144

# 起服務（profile 由 .env 的 DOC_ENGINE/DEVICE/METADATA_DB_PROFILE 決定）
docker compose up -d

# 看 log 直到 API server ready
docker logs -f ragflow-cpu
```

然後在 UI 上的順序是固定的，漏一步就會卡住：

```
① 設定模型：至少要一個 chat 模型 + 一個 embedding 模型
   （沒有 embedding 模型，建知識庫時會失敗）
        │
        ▼
② 建知識庫：選 embedding 模型（★ 建了就不能換）+ 選 chunk 模板
        │
        ▼
③ 上傳文件 → 按「解析」→ 看進度條
        │
        ▼
④ 檢查 chunk（★ 這一步不要跳過）
        │
        ▼
⑤ 建對話助理：綁知識庫 + 設 prompt + 調檢索參數
        │
        ▼
⑥ 提問，看引用
```

**第 ② 步的「embedding 模型不能換」是最容易後悔的決定**（原因見 Part 3：向量維度寫在欄位名裡）。**第 ④ 步是最容易被跳過但最重要的一步**——chunk 壞了，後面所有調參都是在補救。

### 7.2 從原始碼跑（開發用）

```bash
uv sync --python 3.13 --all-extras          # 依賴
uv run python3 ragflow_deps/download_deps.py # 下載 DeepDoc 的 ONNX 權重
docker compose -f docker/docker-compose-base.yml up -d   # 只起依賴服務
source .venv/bin/activate
export PYTHONPATH=$(pwd)
bash docker/launch_backend_service.sh        # 起 api + executor

cd web && npm install && npm run dev         # 前端
```

**注意 `download_deps.py`**：DeepDoc 的模型權重不在 git repo 裡，要另外下載。如果跳過這步，解析 PDF 時會失敗。中國大陸環境可以設 `export HF_ENDPOINT=https://hf-mirror.com`。

### 7.3 五個最常見的啟動問題

| 症狀 | 原因 | 處理 |
|---|---|---|
| ES 容器反覆重啟 | `vm.max_map_count` < 262144 | `sysctl -w vm.max_map_count=262144` |
| 建知識庫失敗 | 沒設 embedding 模型 | 先在模型設定裡加一個 |
| 解析卡在 0% | executor 沒起來 / Redis 連不上 | 看 executor 的 log |
| 解析卡在 70~90% | embedding provider 有問題 | 換 provider 或檢查 API key |
| 解析後檢索不到 | embedding 維度不是 512/768/1024/1536 | 換模型並重建知識庫（見 Part 3） |

最後一個特別陰險：**寫入成功、無錯誤日誌、但向量檢索永遠回傳空。** 原因是 ES 的動態 mapping 只認 512/768/1024/1536 四種維度，用 384 維模型（如 `all-MiniLM-L6-v2`、`bge-small`）時向量欄位不會被建成 KNN 索引。Part 3 會完整解釋這個機制。


## 八、程式碼地圖：從哪裡開始讀

如果你要 clone 下來自己讀，建議的閱讀順序（也就是這個系列的順序）：

```
ragflow/
├── docker/                 ← ① 從這裡開始：compose + .env + entrypoint.sh
│   ├── docker-compose.yml      看清楚有幾個進程
│   ├── docker-compose-base.yml 看清楚有幾個依賴服務
│   └── entrypoint.sh           看清楚進程怎麼被拉起來（Part 5）
├── conf/                   ← ② schema 與設定的真實來源
│   ├── mapping.json            ES dynamic template（Part 3 主角）
│   ├── infinity_mapping.json   Infinity 表結構，欄位名一目了然
│   └── service_conf.yaml       各服務連線設定
├── deepdoc/                ← ③ Part 2：文件理解
│   ├── vision/                 OCR / layout / TSR（ONNX 模型）
│   └── parser/                 pdf / docx / excel / html / markdown / mineru / docling…
├── rag/                    ← ④ Part 2/3/4：引擎核心
│   ├── app/                    14 種 chunk 模板
│   ├── nlp/                    分詞、查詢編譯、混合檢索（search.py 45 KB）
│   ├── llm/                    七類模型的統一介面
│   ├── flow/                   可編排 ingestion pipeline
│   ├── graphrag/               GraphRAG（general / light / ner 三種抽取策略）
│   ├── utils/                  各種 *_conn.py：doc engine 與物件儲存的 driver
│   └── svr/task_executor.py    ⑤ Part 5：整條 ingestion 管線的排程中心
├── api/                    ← ⑥ Part 5：服務分層
│   ├── apps/restful_apis/      29 個 API 藍圖
│   └── db/services/            33 個 service 類別
├── agent/                  ← ⑦ Part 5：Agent canvas + 20 個元件 + 27 個工具
├── internal/ + cmd/        ← ⑧ Part 5：Go 實作（新增中）
├── web/                    React + TypeScript + Vite 前端
├── mcp/  sdk/  admin/  memory/  helm/
└── AGENTS.md               專案自己給 AI coding agent 的指引，讀它可以快速了解慣例
```

**一個實用技巧**：`AGENTS.md` 與 `internal/development.md` 是這個 repo 裡資訊密度最高的兩份文件，比 `docs/` 更貼近當前程式碼。前者列出完整目錄職責與測試分層，後者是 Go 實作的開發指南（含一套 SQL 風格的 CLI，可以直接對系統下 `RETRIEVE 'AI' ON DATASETS 'test' WITH top_k 50 use_kg true;`）。

---

## 九、系統效應：RAGFlow 相對 naive RAG 改了什麼

把本篇提到的設計整理成一張對照表——這也是後面四篇要逐一驗證的清單。

| 環節 | naive RAG 做法 | RAGFlow 做法 | 效果 |
|---|---|---|---|
| 解析 | `pdfminer` 抽純文字 | OCR + 版面辨識（10 類）+ 表格結構辨識（5 類）+ 自動旋轉 | 掃描件與表格從「不可用」變「可用」 |
| 切分 | 固定 512 token | 14 種模板 + 分隔符優先 + 一次邊界溢出容忍 | 語意邊界不被硬切 |
| 人工介入 | 無 | chunk 可視化 / 可編輯 / `important_kwd`（^30）/ `questions`（^20） | 一次修正 = 30 倍檢索槓桿 |
| 編碼 | 只編碼內容 | 0.1×檔名 + 0.9×內容；有 `questions` 時優先編碼問句 | 檔名資訊不遺失 |
| 儲存 | 單一向量欄位 | 後綴驅動的動態 schema，向量維度寫在欄位名 | 換模型不改 mapping |
| 召回 | 單路向量 top-k | 全文 + 向量雙路，weighted_sum 融合，空結果自動退避 | 專名與語意查詢都能命中 |
| 重排 | 無 | 本地 0.3/0.7 混合 + rank_feature，選配 cross-encoder（前 64） | 精度與成本可調 |
| 引用 | 靠 prompt 拜託 LLM | 事後逐句反查，閾值 0.63→0.3 遞降，每句最多 4 個 | 引用可驗證、不依賴模型服從度 |
| 進階 | 無 | RAPTOR 摘要樹 / GraphRAG 圖檢索 / TOC 增強 | 全域性問題也能回答 |

---

## 十、系列導航

本篇建立了地圖，接下來四篇逐層下鑽：

- **Part 2 — 資料進場**：DeepDoc 的 OCR / 版面 / 表格三層視覺管線，14 種 chunk 模板各自的結構假設，以及 `naive_merge` 的切分契約（分隔符、token 上限、溢出策略、重疊比例）。
- **Part 3 — Encode 與 Save**：混合向量的權重從哪來、批次與截斷怎麼做、後綴驅動的動態 mapping 全表、那個把 TF 壓成 `min(freq,1)` 的自訂相似度為什麼存在。
- **Part 4 — Decode 與檢索**：查詢編譯器如何把一句人話變成加權布林查詢、ES 與 Infinity 兩種融合路徑的差異、rerank 三部曲、GraphRAG 與 RAPTOR 的成本與時機、引用對齊演算法。
- **Part 5 — 系統與程式碼結構**：進程拓撲、服務分層、Task Executor 的 13 種任務型別、Agent canvas 與 ingestion pipeline 兩套 DAG 引擎、以及正在進行的 Go 遷移。

→ [RAGFlow Intro Part 2 — 資料進場 — DeepDoc 解析、Chunking 策略與 14 種模板](../ragflow-intro-part2-deepdoc-chunking-zh)

---

*本文基於 RAGFlow `main` 分支（2026 年 9 月）原始碼撰寫，版本參考 v0.27.1。所有程式碼路徑、參數預設值與埠位皆從原始碼與設定檔實際核對。RAGFlow 仍在快速演進，細節請以你 clone 的版本為準。*
