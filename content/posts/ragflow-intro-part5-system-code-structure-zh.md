---
title: "RAGFlow Intro Part 5 — 系統與程式碼結構 — 服務分層、Task Executor 與 Go 遷移"
date: 2026-09-10T13:00:00+08:00
draft: false
weight: 5
description: "RAGFlow 原始碼導讀系列最終篇：拆解進程拓撲與水平擴充參數、四層服務分層、Redis Stream 任務系統的 13 種任務型別、Agent Canvas 與 ingestion Pipeline 兩套 DAG 引擎，以及正在進行中的 Python → Go 遷移。"
categories: ["all", "ai", "engineering", "architecture"]
tags: ["RAGFlow", "RAG", "AI", "System Design", "Redis Stream", "Go", "Architecture", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
---

> *大多數人讀開源專案的原始碼，是從 README 跳到 `main()`，看幾個函式，然後說「架構我懂了」。*
> *真正的答案是：一個系統的架構不在程式碼裡，在進程拓撲、佇列語意、失敗處理與擴充邊界裡。*
> *哪些東西是無狀態的？任務失敗會怎樣？要加一倍吞吐要改什麼？這三個問題答得出來，才算讀懂。*
> *這篇文章回答的就是這三個問題。*

---

## 前言

[Part 1](../ragflow-intro-part1-overview-architecture-zh) 到 [Part 4](../ragflow-intro-part4-retrieval-rerank-zh) 拆完了資料的完整生命週期。本篇回到工程層：**這些邏輯是怎麼被組織成一個能跑、能擴、能維護的系統的。**

要處理的問題：

```
① 有幾個進程？誰是無狀態的？擴充要改哪個參數？
② 一個 HTTP 請求從 nginx 到資料庫，經過幾層？
③ 非同步任務系統的語意：投遞、消費、確認、取消、重試、超時
④ 兩套 DAG 引擎（Agent Canvas / Ingestion Pipeline）為什麼要兩套？
⑤ 為什麼一個 Python 專案的 GitHub 主要語言標成 Go？
```

---

## 一、程式碼地圖

先給一張完整的目錄職責表。這張表的來源是 repo 自帶的 `AGENTS.md`（專案給 AI coding agent 的操作指引），它比 `docs/` 更貼近當前程式碼。

```
ragflow/
│
├── api/                    Python API server（Quart + Peewee）
│   ├── ragflow_server.py       進程入口（6.5 KB）
│   ├── apps/
│   │   ├── restful_apis/       29 個 API 藍圖（dataset / document / chunk / chat …）
│   │   ├── services/           API 層的服務（薄，做參數轉換與編排）
│   │   └── auth/               認證
│   ├── db/
│   │   ├── db_models.py        Peewee ORM 模型（唯一的表定義來源）
│   │   ├── services/           33 個業務服務（厚，真正的業務邏輯）
│   │   ├── joint_services/     跨服務的編排
│   │   └── init_data/          初始資料（模型供應商清單等）
│   └── validation.py           請求驗證
│
├── rag/                    引擎核心
│   ├── app/                    14 種 chunk 模板（Part 2）
│   ├── nlp/                    分詞、查詢編譯、混合檢索（Part 4）
│   ├── llm/                    七類模型的統一介面
│   ├── flow/                   可編排 ingestion pipeline（DAG）
│   ├── graphrag/               GraphRAG（general / light / ner）
│   ├── advanced_rag/           Agentic RAG、knowledge compile、harness
│   ├── prompts/                prompt 模板與組裝
│   ├── utils/                  doc engine / 物件儲存 / 外部服務的 driver
│   ├── res/                    DeepDoc 的 ONNX / ORT 權重
│   └── svr/                    ★ 背景 worker
│       ├── task_executor.py            主 worker（93 KB）
│       ├── task_executor_refactor/     正在拆解中的模組（21 個檔案）
│       ├── task_executor_limiter.py    並發限流
│       ├── sync_data_source.py         外部資料源同步（96 KB）
│       └── cache_file_svr.py           檔案快取
│
├── deepdoc/                文件理解（Part 2）
│   ├── vision/                 OCR / layout / TSR
│   ├── parser/                 19 個格式解析器
│   └── server/                 解析服務化的入口
│
├── agent/                  Agent 工作流引擎
│   ├── canvas.py               DAG 執行器（50 KB）
│   ├── component/              20 個流程元件
│   ├── tools/                  27 個工具
│   ├── templates/              預建 agent 範本
│   ├── sandbox/                程式碼執行沙箱（gVisor）
│   └── dsl_migration.py        DSL 版本遷移
│
├── common/                 跨模組共用（constants / settings / token_utils …）
├── memory/                 Agent 記憶（2025-12 新增）
├── mcp/                    MCP server
├── admin/                  管理服務（:9381）
├── sdk/                    Python / JS SDK
│
├── cmd/                    ★ Go 進程入口
│   ├── ragflow_server.go       44 KB，三種角色：--api / --admin / --ingestor
│   └── ragflow-cli.go          SQL 風格 CLI
├── internal/               ★ Go 主體實作（22 個子套件）
├── ragflow_deps/           原生依賴下載腳本
│
├── web/                    React + TypeScript + Vite
├── docker/                 compose / .env / entrypoint.sh / nginx 設定
├── helm/                   Kubernetes chart
├── conf/                   schema 與服務設定（Part 3）
└── AGENTS.md               ★ 專案慣例與測試分層，資訊密度最高的一份文件
```

**兩個「大到不合理」的檔案值得注意**：`rag/svr/task_executor.py`（93 KB）和 `rag/svr/sync_data_source.py`（96 KB）。前者是整條 ingestion 管線的排程中心，後者處理外部資料源同步（Confluence、S3、Notion、Discord、Google Drive 等）。`task_executor_refactor/` 目錄的存在說明團隊自己也在拆——裡面已經分出了 `chunk_service`、`embedding_service`、`raptor_service`、`task_manager` 等模組，還有一份 `task_executor_refactoring_plan.md`。

---

## 二、進程拓撲：誰在跑，怎麼擴

### 2.1 一個容器裡有幾個進程

`docker/entrypoint.sh` 是答案。它不是「起一個服務」，而是**起一組進程**：

```
docker run infiniflow/ragflow
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ entrypoint.sh                                                    │
│                                                                  │
│  ① 依 API_PROXY_SCHEME 選 nginx 設定                             │
│     python → ragflow.conf.python                                 │
│     hybrid → ragflow.conf.hybrid                                 │
│     go     → ragflow.conf.golang                                 │
│                                                                  │
│  ② 起 admin server（必須先起，否則 api server 的心跳會失敗）      │
│     python: admin/server/admin_server.py    :9381                │
│     go:     bin/ragflow_server --admin      :9383                │
│                                                                  │
│  ③ 起 nginx                                     :80 / :443       │
│                                                                  │
│  ④ 起 API server                                                 │
│     python: api/ragflow_server.py           :9380                │
│     go:     bin/ragflow_server --api        :9384                │
│                                                                  │
│  ⑤ 起 N 個 task executor                                         │
│     for i in 0..WORKERS:                                         │
│       python3 rag/svr/task_executor.py -i "${host_id}_${i}" -t common &
│     go: bin/ragflow_server --ingestor &                          │
│                                                                  │
│  每個進程都包在 run_with_restart 裡（掛了自動重啟）               │
└──────────────────────────────────────────────────────────────────┘
```

**「admin server 必須先起」這個順序依賴，是 `internal/development.md` 明文警告的**：

> Note: admin server must be started first; otherwise, api server will encounter errors when sending heartbeats.

心跳間隔在 `service_conf.yaml` 裡：`general.heartbeat_interval: 3s`。

### 2.2 水平擴充的三個參數

`entrypoint.sh` 提供三組參數，對應三種擴充需求：

| 參數 | 作用 | 使用時機 |
|---|---|---|
| `WORKERS` | 本機起幾個 executor 進程 | 單機吃滿 CPU |
| `--consumer-no-beg` / `--consumer-no-end` | consumer 編號範圍 | **多台機器**，避免 consumer 名稱撞號 |
| `--host-id` | 本機識別碼（預設 `hostname`） | 多台機器的日誌與心跳區分 |
| `-t <task_type>` | 這批 executor 只處理某類任務 | **任務分池** |
| `--disable-webserver` | 只跑 executor，不起 nginx/api | 專用 worker 機 |

**多機部署的正確做法**：

```bash
# 機器 A：web + api + executor 0~3
docker run ... -e WORKERS=4 --host-id=host-a

# 機器 B：純 worker，executor 4~7
docker run ... --disable-webserver --consumer-no-beg=4 --consumer-no-end=8 --host-id=host-b

# 機器 C：GPU worker，只跑 graphrag（吃 LLM 不吃 CPU）
docker run ... --disable-webserver --consumer-no-beg=8 --consumer-no-end=10 \
               --host-id=host-c-gpu -e DEVICE=gpu
```

**為什麼 consumer 編號不能重複？** 因為 Redis Stream 的 consumer group 用 consumer name 追蹤「這個 consumer 有哪些未確認的訊息」。兩台機器用同一個名字，會互相搶對方的 pending 訊息，導致同一個任務被處理兩次或永遠不被處理。

### 2.3 無狀態邊界

```
┌──────────────────────────────────────────────────────────────────┐
│  無狀態（可任意複製、可隨時殺）                                   │
│  · nginx                                                         │
│  · API server（session 在 Redis，不在記憶體）                     │
│  · Task Executor（所有狀態在 MySQL + Redis + MinIO）              │
│  · Go ingestor                                                   │
├──────────────────────────────────────────────────────────────────┤
│  有狀態（必須做 HA、必須備份）                                    │
│  · MySQL          文件/任務/使用者/租戶/對話  ← 真實來源           │
│  · MinIO / S3     原始檔 + 圖片切片          ← 真實來源           │
│  · Redis/Valkey   佇列 + 快取 + 分散式鎖 + session                │
│  · Doc engine     chunk + 向量               ← 可從上面兩者重建   │
└──────────────────────────────────────────────────────────────────┘
```

**Redis 的角色比想像中重**：它同時是佇列（Stream）、快取（LLM 回應快取、同義詞表、標籤表）、分散式鎖（`RedisDistributedLock`）與 session store。**Redis 掉了，系統整體停擺**，不只是「快取失效」。這是一個單點，Phase 3 一定要做叢集。

---

## 三、服務分層：一個請求走過幾層

以「上傳文件」為例，看完整的呼叫鏈：

```
POST /v1/document/upload
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ ① nginx                    反向代理，依 API_PROXY_SCHEME 決定後端  │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────┐
│ ② api/apps/restful_apis/document_api.py                          │
│    Quart blueprint：解析請求、認證、呼叫下一層                     │
│    職責邊界：不寫業務邏輯，只做 HTTP 的事                          │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────┐
│ ③ api/apps/services/document_api_service.py                      │
│    API 層服務：參數正規化、權限檢查、多步編排                      │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────┐
│ ④ api/db/services/document_service.py（+ file_service、task_service）│
│    業務服務：真正的邏輯                                            │
│    · 存檔到 STORAGE_IMPL（MinIO/S3/…）                            │
│    · 寫 MySQL 的 document 列                                      │
│    · 建 task 列 + 推 Redis Stream                                 │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────┐
│ ⑤ 三個基礎設施抽象                                                │
│    api/db/db_models.py     Peewee ORM → MySQL/PostgreSQL/GaussDB │
│    settings.docStoreConn   → ES / Infinity / OpenSearch / …       │
│    settings.STORAGE_IMPL   → MinIO / S3 / OSS / GCS / Azure / …   │
└───────────────────────────────────────────────────────────────────┘
```

`api/db/services/` 的 33 個服務類別就是這個系統的業務詞彙表：

```
知識與內容    knowledgebase_service   document_service      file_service
             chunk_feedback_service   doc_metadata_service  file2document_service
             file_commit_service      document_counter_service
對話          dialog_service（2200 行，Part 4 的主角）  conversation_service
             chat_channel_service     search_service
任務          task_service             pipeline_operation_log_service
Agent        canvas_service           user_canvas_version   memory_service
模型          llm_service              tenant_llm_service    tenant_model_service
             tenant_model_instance_service   tenant_model_provider_service
             tenant_model_group_service      tenant_model_group_mapping_service
使用者/系統   user_service             api_service           system_settings_service
整合          connector_service        mcp_server_service    langfuse_service
編譯模板      compilation_template_service    compilation_template_group_service
共用          common_service（CRUD 基底類）
```

**`tenant_model_*` 有五個服務**，這是多租戶模型管理的複雜度：每個租戶可以加多個供應商、每個供應商可以有多個 instance（不同 API key）、每個 instance 有多個 model、還要設每種型別的預設模型。Part 1 提到的 CLI 就是操作這一層：

```
RAGFlow(api/default)> create provider 'openai' instance 'prod' key 'sk-...';
RAGFlow(api/default)> set default chat model 'glm-4.5-flash@test@zhipu-ai';
RAGFlow(api/default)> list default models;
```

**模型的完整識別碼是 `模型名@instance名@供應商`**——三段式。這個設計讓「同一個模型、兩個 API key（一個測試一個生產）」成為一等公民。

---

## 四、任務系統：Redis Stream 的完整語意

這是整個系統最核心的機制。Part 1 給了輪廓，這裡給細節。

### 4.1 投遞與消費

```
常數（common/constants.py）：
    SVR_QUEUE_NAME = "te"
    SVR_CONSUMER_GROUP_NAME = "rag_flow_svr_task_broker"
```

```
API server                         Task Executor
    │                                    │
    │ ① 寫 MySQL task 列                  │
    │   （status=UNSTART，含完整參數）      │
    │                                    │
    │ ② XADD te {id, doc_id,              │
    │        task_type, tenant_id, ...}   │
    │   ← 訊息體只有 ID 與少數欄位          │
    │                                    │
    └────────────────────────────────────▶│
                                         │ ③ 先處理 unacked（get_unacked_iterator）
                                         │    ← 上次沒 ack 完的訊息優先
                                         │
                                         │ ④ StopIteration 後才 XREADGROUP 新訊息
                                         │    for queue in svr_queue_names:
                                         │        queue_consumer(queue, group, consumer)
                                         │
                                         │ ⑤ TaskService.get_task(msg["id"])
                                         │    ← 回 MySQL 撈完整任務
                                         │
                                         │ ⑥ has_canceled(task["id"])？
                                         │    → 是：ack 並丟棄
                                         │
                                         │ ⑦ 執行（@timeout(60*80) = 80 分鐘上限）
                                         │
                                         │ ⑧ ack + 更新 MySQL 進度/狀態
```

四個設計決定：

**① 訊息只放 ID，不放內容。** 訊息體極小（幾百 bytes），Redis 記憶體壓力小。任務參數的真實來源永遠是 MySQL，所以**任務可以在投遞後被修改或取消**——這是「訊息含完整參數」做不到的。

**② unacked 優先。** `get_unacked_iterator()` 先跑完所有未確認的訊息，才去讀新訊息。這保證了 executor 重啟後**不會漏掉正在處理中被中斷的任務**。

**③ 取消是一次資料庫查詢，不是訊息。** `has_canceled(task_id)` 查 MySQL 的狀態欄位。使用者按「取消」時，API 只需要改一個欄位，不需要試圖從佇列裡撈出訊息刪掉（那在 Redis Stream 裡很難做）。而且 executor 在執行過程中會**反覆檢查**這個標記，所以取消可以中斷進行中的任務。

**④ 80 分鐘超時。** `@timeout(60 * 80, 1)` 裝在任務處理函式上。這是一個很長的上限，反映 ingestion 任務的真實特性（一份 500 頁的掃描 PDF 加上 LLM 加值，確實可能跑 1 小時）。**代價是壞掉的任務要卡 80 分鐘才會釋放 slot。**

### 4.2 13 種任務型別

`task_executor.py` 的映射表就是整個系統的非同步能力清單：

```python
TASK_TYPE_TO_PIPELINE_TASK_TYPE = {
    "dataflow":          PipelineTaskType.PARSE,              # 解析 + 切分 + 索引
    "raptor":            PipelineTaskType.RAPTOR,             # 摘要樹
    "graphrag":          PipelineTaskType.GRAPH_RAG,          # 知識圖
    "mindmap":           PipelineTaskType.MINDMAP,            # 心智圖
    "memory":            PipelineTaskType.MEMORY,             # Agent 記憶
    "wiki":              PipelineTaskType.ARTIFACT,           # Wiki 生成
    "skill":             PipelineTaskType.SKILL,              # Agent skill
    "structure_graph":   PipelineTaskType.STRUCTURE_GRAPH,
    "structure_mindmap": PipelineTaskType.STRUCTURE_MINDMAP,
    "timeline":          PipelineTaskType.TIMELINE,
    "session_graph":     PipelineTaskType.SESSION_GRAPH,
    "session_essence":   PipelineTaskType.SESSION_ESSENCE,
    "structure":         PipelineTaskType.STRUCTURE,
}
```

**11 種是「KB 層級的 fan-out 任務」**：

```python
_KB_FANOUT_TASK_TYPES = [
    "graphrag", "raptor", "mindmap", "wiki", "skill",
    "structure_graph", "structure_mindmap", "timeline",
    "session_graph", "session_essence", "structure",
]
# KB-wide fan-out task types: their task row's ``doc_id`` is a fake sentinel
# and the participating documents live in ``task["doc_ids"]``.
```

也就是這些任務不屬於任何單一文件，它們的 `doc_id` 是一個 sentinel 常數（`GRAPH_RAPTOR_FAKE_DOC_ID`），實際參與的文件放在 `doc_ids` 陣列。

**這個 hack 揭露了一個 schema 演進的痕跡**：`task` 表最初的設計是「一個任務對一份文件」，後來需要 KB 層級任務，但改 schema 成本高，於是用一個假 doc_id 繞過。程式碼裡有一段註解在解釋為什麼要在兩個分支都做同樣的欄位複製：

> The KB-scoped branch above already does this for FAKE doc tasks; mirror here so `ctx.doc_ids` is populated for the per-doc path too.

**還有一個 `CANVAS_DEBUG_DOC_ID`**——專門用來 debug ingestion pipeline 的假文件 id。走這個 id 的任務不寫索引，只把結果記錄下來給開發者看：

```python
if doc_id == CANVAS_DEBUG_DOC_ID:
    get_recording_context().record("dataflow_debug_result", "canvas_debug_mode")
    get_recording_context().record("dataflow_chunks", chunks)
    return
```

### 4.3 進度回寫與可觀測性

```python
def set_progress(task_id, from_page=0, to_page=-1, prog=None, msg="Processing..."):
```

進度是「一個 0～1 的浮點數 + 一段人看的訊息」，直接寫 MySQL。UI 輪詢這個欄位。

Executor 自己維護的指標：

```python
PENDING_TASKS = 0      # 佇列裡待處理
LAG_TASKS = 0          # consumer group 的 lag
DONE_TASKS = 0
FAILED_TASKS = 0
CURRENT_TASKS = {}     # 正在處理的任務（會進心跳）
BOOT_AT = datetime.now().astimezone().isoformat(timespec="milliseconds")
```

這些會隨心跳送給 admin server。**`LAG_TASKS` 是最重要的營運指標**：它是「積壓」的直接量測，決定要不要加 worker。

還有一個細節很專業：

```python
def _redact_task_user(task: dict) -> dict:
    """Copy a task dict for logs/heartbeat without the raw end-user identifier."""
```

**寫日誌與心跳之前，先把終端使用者識別碼脫敏。** 這是 GDPR 級別的細節，多數開源專案不會做。

---

## 五、兩套 DAG 引擎

RAGFlow 有兩個 DAG 執行器。這不是重複，是兩種不同的執行語意。

### 5.1 Agent Canvas：對話型工作流

```
agent/canvas.py
├── class Graph          基礎 DAG（load / run / path / 變數解析）
└── class Canvas(Graph)  加上對話狀態（history / memory / globals / retrieval）
```

DSL 是一份 JSON：

```json
{
  "components": {
    "begin":      { "obj": {...}, "downstream": ["categorize:0"], "upstream": [] },
    "categorize:0": { "obj": {...}, "downstream": ["retrieval:0", "llm:0"] },
    "retrieval:0":  { "obj": {...}, "downstream": ["llm:0"] },
    "llm:0":        { "obj": {...}, "downstream": ["message:0"] }
  },
  "path": ["begin", "categorize:0"],
  "history": [...],
  "globals": {...},
  "variables": {...},
  "retrieval": [...],
  "memory": {...}
}
```

**`path` 是執行軌跡，而且會被序列化回 DSL。** `__str__()` 會把 `path` 和 `task_id` 寫回去：

```python
def __str__(self):
    self.dsl["path"] = self.path
    self.dsl["task_id"] = self.task_id
```

這讓一次執行可以**中斷後續跑**——狀態不在記憶體裡，在 DSL 裡。這對「等使用者填表」（`fillup` 元件）這種需要人在迴圈裡的流程是必要的。程式碼裡就有這個特例：

```python
if self.path[0].lower().find("userfillup") >= 0:
```

**20 個元件**（`agent/component/`）：

| 分類 | 元件 |
|---|---|
| 流程控制 | `begin`、`switch`、`categorize`、`iteration`、`iterationitem`、`loop`、`loopitem`、`exit_loop` |
| LLM | `llm`、`agent_with_tools` |
| 變數 | `variable_aggregator`、`variable_assigner`、`string_transform` |
| 資料 | `data_operations`、`list_operations`、`excel_processor` |
| I/O | `message`、`fillup`、`invoke`、`browser`、`docs_generator` |

**27 個工具**（`agent/tools/`）：`retrieval`（查自己的知識庫）、`code_exec`（沙箱執行程式碼）、`exesql`、`crawler`、`email`、`tavily`、`duckduckgo`、`searxng`、`arxiv`、`pubmed`、`wikipedia`、`github`、`googlescholar`、`yahoofinance`、`akshare`、`tushare`、`wencai`、`jin10`、`qweather`、`deepl` 等。

**元件註冊是動態的**（`agent/component/__init__.py`）：

```python
for filename in os.listdir(...):
    if filename.startswith("__") or not filename.endswith(".py") or filename.startswith("base"):
        continue
    module = importlib.import_module(f".{module_name}", package=__name__)
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and obj.__module__ == module.__name__ and not name.startswith("_"):
            __all_classes[name] = obj
```

**丟一個檔案進 `agent/component/`，裡面定義一個類別，它就自動成為可用元件。** 而且解析類別名稱時會跨三個套件找：

```python
for module_name in ["agent.component", "agent.tools", "rag.flow"]:
```

**注意第三個：`rag.flow`。** Ingestion pipeline 的節點也在同一個註冊表裡——這解釋了下一節。

### 5.2 Ingestion Pipeline：資料處理工作流

```
rag/flow/
├── pipeline.py       class Pipeline(Graph)    ← 繼承同一個 Graph 基底
├── base.py           class ProcessBase(ComponentBase)
├── file.py           檔案來源節點
├── parser/           解析節點（+ pdf_chunk_metadata.py）
├── chunker/
│   ├── token_chunker.py
│   ├── _sentence_boundary.py
│   └── title_chunker/
│       ├── hierarchy_chunker.py   依標題層級建父子結構
│       ├── group_chunker.py
│       └── title_chunker.py
├── tokenizer/        分詞節點
├── extractor/        抽取節點
└── compiler/         編譯節點
```

節點介面極簡：

```python
class ProcessBase(ComponentBase):
    async def invoke(self, **kwargs) -> dict[str, Any]:
    async def _invoke(self, **kwargs):
```

**兩套引擎共用 `Graph` 基底與元件註冊表，但語意不同**：

| | Agent Canvas | Ingestion Pipeline |
|---|---|---|
| 觸發 | 使用者訊息 | 文件上傳 |
| 狀態 | 對話歷史 + memory + globals | 單次執行，無跨次狀態 |
| 中斷續跑 | 需要（等使用者填表） | 需要（checkpoint / resume） |
| 輸出 | 訊息串流 | chunk 陣列 |
| 執行者 | API server（同步回應）| Task Executor（背景） |
| 除錯 | UI 上逐節點檢視 | `CANVAS_DEBUG_DOC_ID` |

Go 側的對應實作在 `internal/ingestion/`：

```
internal/ingestion/
├── component/         階段實作
│   ├── file.go  parser.go  parser_dispatch.go
│   ├── chunker/  tokenizer.go  extractor.go
│   ├── document_storage.go  image_uploader.go
│   ├── idempotency.go            ← 冪等性（避免重複寫入）
│   ├── pdf_vision_dispatch.go    ← CGO / non-CGO 兩份實作
│   └── vision_enhancement.go
└── pipeline/          DSL 翻譯、canvas 驅動執行、checkpoint、resume/run
```

`AGENTS.md` 對這幾個目錄有特別交代：

> Treat `internal/ingestion`, `internal/parser`, and `internal/deepdoc` as actively refactored code. Prefer collapsing duplicate paths over preserving transitional wrappers.

**「正在重構中，遇到重複路徑請合併而不是保留過渡包裝」**——這是一份給協作者（含 AI）的明確授權。

---

## 六、三個演進階段：部署與運維

### ╔══ Phase 1：單容器全包（POC） ══╗

```
docker compose up -d
        │
        ▼
┌──────────────────────────────────────────────┐
│ ragflow 容器                                  │
│  nginx + admin + api + 1×executor            │
│  全部包在 run_with_restart 裡                 │
└──────────────────────────────────────────────┘
+ es01 / mysql / minio / redis
```

- 設定：`WORKERS` 不設（預設 1）、`API_PROXY_SCHEME` 不設（走 python）
- 運維：看 `./ragflow-logs/` 裡的日誌
- 解決：能跑
- 剩下：一份重文件堵住整個佇列；沒有指標；沒有 replica

### ╔══ Phase 2：拆 executor + 多機（MVP） ══╗

```
┌────────────────────┐   ┌──────────────────────┐   ┌────────────────────┐
│ host-a             │   │ host-b               │   │ host-c (GPU)       │
│ web+api+exec 0-3   │   │ --disable-webserver  │   │ --disable-webserver│
│ WORKERS=4          │   │ consumer 4-7         │   │ consumer 8-9       │
│ --host-id=host-a   │   │ --host-id=host-b     │   │ -t graphrag        │
└─────────┬──────────┘   └──────────┬───────────┘   └─────────┬──────────┘
          └─────────────────────────┴─────────────────────────┘
                                    ▼
              Redis Stream "te" / group rag_flow_svr_task_broker
                                    │
                    ES 3 節點 / MySQL 主從 / MinIO 分散式
```

- 新增元件 vs Phase 1：多主機、consumer 編號劃分、任務分池（`-t`）、ES replica
- 運維增量：需要監控 `LAG_TASKS`；需要集中日誌
- 解決：吞吐線性擴充；重任務不擠壓輕任務
- 剩下：Python 的 GIL 讓單進程吞吐有天花板；沒有分散式追蹤

**任務分池是這一階段最值得做的事。** GraphRAG 任務會佔用 executor 幾十分鐘（全在等 LLM），如果和一般解析共用池子，使用者上傳一份小 PDF 要排隊等 GraphRAG 跑完。`-t` 參數把它們分開，是一行參數換來的體驗改善。

### ╔══ Phase 3：K8s + Go 熱路徑（Scale） ══╗

```
┌─────────────────────────────────────────────────────────────────────┐
│  Kubernetes（helm/）                                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ api (HPA)    │  │ go api :9384 │  │ executor pool（按 -t 分池）│ │
│  │ python :9380 │  │ go ingestor  │  │ common / gpu / graphrag   │ │
│  └──────────────┘  └──────────────┘  └───────────────────────────┘ │
│         API_PROXY_SCHEME=hybrid（nginx 依路由分流）                  │
│                              │                                      │
│  ┌───────────────────────────┴──────────────────────────────────┐   │
│  │ Jaeger 2.19（分散式追蹤）+ Langfuse（LLM 觀測）+ 集中日誌     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

- 新增元件：Helm chart、HPA、Go server、Jaeger、Langfuse、sandbox-executor-manager（gVisor）
- 運維增量：雙實作的一致性驗證
- 解決：吞吐、尾延遲、成本歸屬、可觀測性
- 剩下：Go/Python 行為差異的除錯成本

**`docker-compose-base.yml` 裡已經有 Jaeger 的 profile**（`jaegertracing/jaeger:2.19.0`），和 sandbox executor（`infiniflow/sandbox-executor-manager`，帶 `no-new-privileges:true` 這個 security opt）。這些都是「開箱即用的生產設施」。

### 三階段對照

| 維度 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 主機數 | 1 | 3～5 | K8s 節點池 |
| executor 進程 | 1 | 8～12 | 依 HPA |
| 任務分池 | 無 | 2～3 池 | 3+ 池 |
| API 後端 | Python | Python | Go / hybrid |
| 可觀測性 | 檔案日誌 | 集中日誌 + LAG 監控 | Jaeger + Langfuse |
| 部署方式 | compose | compose + 參數 | Helm |
| 高可用 | 無 | ES/MySQL replica | 全鏈路 |

---

## 七、Go 遷移：為什麼一個 Python 專案的主要語言是 Go

打開 GitHub 頁面，RAGFlow 的 `language` 欄位顯示 **Go**。這不是統計錯誤——`internal/` 已經有 22 個子套件，`cmd/ragflow_server.go` 有 44 KB。

### 7.1 遷移的形態：一個二進位，三種角色

```bash
./bin/ragflow_server --admin      # admin server，:9383
./bin/ragflow_server --api        # API server，:9384
./bin/ragflow_server --ingestor   # 對應 Python 的 task_executor
./bin/ragflow-cli                 # CLI（API 模式）
./bin/ragflow-cli --admin         # CLI（admin 模式）
```

**同一個二進位用旗標選角色**，跟 Python 側的三個獨立腳本形成對比。

### 7.2 三段式切換：`API_PROXY_SCHEME`

| 值 | 行為 |
|---|---|
| `python` | 前端所有 API 請求路由到 Python server |
| `hybrid` | **部分**路由到 Go、部分到 Python |
| `go` | 全部路由到 Go |

nginx 有三份對應設定（`ragflow.conf.python` / `.hybrid` / `.golang`），`entrypoint.sh` 依變數複製其中一份。前端的 `web/vite.config.ts` 有 `proxySchemes` 對應開發環境。

**這是一個教科書級的漸進式遷移設計**：不是「大爆炸重寫」，而是**逐 endpoint 搬遷**，每搬一個就在 hybrid 設定裡改一條路由。`internal/development.md` 的規定是：

> After updating or implementing an API, update the frontend development environment routes in `web/vite.config.ts` under `proxySchemes`.

### 7.3 最技術性的部分：in-process DeepDoc

Go 側最有價值的改動是**把 DeepDoc 做成 in-process**——不再走 Python 進程，而是把 ONNX Runtime **靜態連結**進 Go 二進位：

```
Go 二進位
├── libonnxruntime.a      （靜態連結，ONNX Runtime）
├── liboffice_oxide.a     （Office 格式解析，Rust）
├── libpdfium.a           （PDF 渲染，Chromium 的 PDF 引擎）
└── libpdf_oxide.a        （PDF 解析，Rust）
     全部靜態連結 — 不需要 LD_LIBRARY_PATH 或 rpath
```

連結方式有一段很精巧的處理：

```bash
-Wl,--undefined=OrtGetApiBase -Wl,--dynamic-list=.cache/ort_dynamic_list.txt
```

`internal/development.md` 解釋了為什麼：

> The binding reaches ORT with `dlopen(NULL)+dlsym("OrtGetApiBase")`, so `OrtGetApiBase` is the only symbol that must be visible process-wide. Export just it — not via a `local: *` version script, which hides Go's runtime type symbols and breaks PIE absolute relocations. There is deliberately no `--whole-archive`, so unreferenced kernels are dropped.

翻譯：**只導出一個符號（`OrtGetApiBase`），因為 binding 是用 `dlopen(NULL)` 在自己的進程裡找它。** 不用 `--whole-archive`，讓連結器把用不到的 ONNX kernel 丟掉（否則二進位會非常大）。而且不能用 `local: *` 版本腳本，因為那會連 Go runtime 的型別符號一起藏起來，破壞 PIE 重定位。

**這種細節是 CGO 專案的真實成本。** 而且 `build.sh` 現在會 fail fast：

```
Error: ONNX Runtime static libraries are not linked
```

**「編譯期失敗優於執行期失敗」**——因為沒連 ORT 的二進位可以編譯成功，但啟動時會死在：

```
Error looking up OrtGetApiBase in statically-linked ONNX Runtime
→ fatal: no in-process DeepDoc backend serving
```

### 7.4 一個容易踩的坑

Go 後端不會自動啟動：

> The container entrypoint only starts the Go server when `API_PROXY_SCHEME` is `go` or `hybrid`. With the variable unset (or `python`) the Go server does NOT start, so the in-process backend is absent and **the image looks like a Python-only build.**

```bash
docker run -e API_PROXY_SCHEME=go infiniflow/ragflow:go-test-1
```

還有 Part 2 提過的模型權重問題：Go 要 `.ort`，Python 要 `.onnx`，目錄裡只有 `.onnx` 時 Go 後端會 fatal——**目錄看起來是滿的，但缺的是 Go 要的那半。**

### 7.5 測試分層：Go 側的四層 build tag

`AGENTS.md` 定義了一套很乾淨的測試分層：

| 層級 | Build tag | 預設跑？ | 需要什麼 |
|---|---|---|---|
| Unit | （無） | ✅ `go test ./...` | 只需 CGO 靜態庫；用 in-memory SQLite / miniredis / httptest |
| Integration | `integration` | ❌ | 真實服務（MySQL/MinIO/ES/Infinity/LLM），單元件 |
| E2E | `e2e` | ❌ | 全鏈路（ingest → index → retrieve） |
| Manual | `manual` | ❌ | 極慢極貴（deepdoc render/parity/bench）**只能本機手動跑，永不進 CI** |
| Native | `cgo` / `!cgo` | 正交維度 | 原生靜態庫；可組合如 `//go:build cgo && integration` |

規則寫得很硬：

> New tests that touch a real external service MUST carry `integration`/`e2e`/`manual` — do not rely on `t.Skip` + env vars to soft-isolate them in the default unit run.

**「不要用 `t.Skip` + 環境變數來『軟隔離』」**——這是被靜默跳過的測試坑過才會寫出來的規定。用 build tag 隔離，測試就是**編譯不進去**，不可能靜默通過。

### 7.6 一個有主張的專案文化

`AGENTS.md` 的 "Core Stance" 值得原文引用：

```
· Treat legacy code as liability, not as a compatibility target.
· Prefer deletion over shims, deprecated branches, wrapper APIs,
  and dual-track migration notes.
· If old and new implementations coexist, converge to one path
  unless an external contract forces compatibility.
· Remove dead tests, commented-out code, stale docs, and
  "move later" notes instead of preserving them.
· Reduce public surface area when a helper can be made private or internal.
```

**「把遺留程式碼當負債，不當相容性目標」**——對一個正在做 Python → Go 遷移的專案，這是一個很勇敢也很清醒的立場。它也解釋了為什麼 `task_executor.py` 有 93 KB：因為他們不做「加一層包裝然後慢慢搬」，而是**先讓一個檔案膨脹，然後整體重構**（`task_executor_refactor/` 就是這個重構的現場）。

---

## 八、可觀測性與運維

| 面向 | 機制 | 位置 |
|---|---|---|
| 應用日誌 | 檔案日誌，掛載 `./ragflow-logs` | `common/log_utils.py` |
| 進程存活 | `run_with_restart` 包住每個進程 | `entrypoint.sh` |
| 心跳 | 每 3 秒回報 admin server，含 `CURRENT_TASKS` | `service_conf.yaml` |
| 佇列積壓 | `PENDING_TASKS` / `LAG_TASKS` | `task_executor.py` |
| 任務進度 | `set_progress()` 寫 MySQL，UI 輪詢 | `task_service.py` |
| 任務歷史 | `pipeline_operation_log_service` | `api/db/services/` |
| 分散式追蹤 | Jaeger 2.19（compose profile） | `docker-compose-base.yml` |
| LLM 觀測 | Langfuse 整合 | `langfuse_service.py` |
| 記憶體診斷 | `start_tracemalloc_and_snapshot()`，signal 觸發 | `common/signal_utils.py` |
| 崩潰診斷 | `faulthandler` | `task_executor.py` |
| PII 保護 | 日誌與心跳前 `_redact_task_user()` | `task_executor.py` |
| 管理介面 | admin server :9381/:9383 + CLI | `admin/`、`cmd/ragflow-cli.go` |

**`faulthandler` + signal 觸發的 tracemalloc 是很實用的組合**：executor 卡住時，發一個 signal 就能拿到當下的 Python 堆疊與記憶體快照，不需要重啟或裝額外工具。這是「跑過長時間任務」的人才會加的東西。

**排錯的標準順序**（依我讀完程式碼的理解）：

```
① 任務卡住不動？
   → 看進度百分比：0.7~0.9 = embedding 問題；< 0.3 = 解析問題
② 任務反覆失敗？
   → 找 @timeout(60*80) 超時，通常是 LLM 加值步驟太多
③ 佇列積壓？
   → 看 LAG_TASKS；加 executor 或做任務分池（-t）
④ 檢索回不到東西？
   → 看 log 有沒有 "Dealer.search 2 TOTAL"（表示走了退避路徑）
⑤ 答案品質差？
   → 看 log 有沒有 "Not all the retrieval into prompt: N/M"
⑥ Go 後端沒生效？
   → 確認 API_PROXY_SCHEME 和 .ort 權重
```

---

## 九、為什麼選 X 不選 Y

```
決定                      選 X 的理由                      不選 Y 的理由 / Y 更好的時機
────────────────────────────────────────────────────────────────────────────────────────
Redis Stream               已經有 Redis（快取/鎖/session）；  Celery：功能完整（重試、路由、
vs Celery / RabbitMQ       consumer group 原生多 worker；    定時），但要多維護 broker+backend；
                           unacked 可重投；訊息只放 ID       RabbitMQ：吞吐更好但運維面積大
                                                            ▶ 翻轉點：需要延遲任務、複雜路由、
                                                              或跨資料中心投遞

訊息只放 ID                投遞後仍可修改/取消任務；          訊息含完整參數：executor 不用查 DB、
vs 訊息含完整參數          Redis 記憶體壓力小                少一次往返，但任務不可變、取消很難
                                                            ▶ 翻轉點：MySQL 是瓶頸時

取消 = 查 DB 欄位          可中斷進行中的任務；               從佇列刪訊息：不用查 DB，
vs 從佇列移除訊息          不需要在 Stream 裡找訊息           但 Redis Stream 刪特定訊息很難、
                                                              且無法中斷已開始的任務
                                                            ▶ 翻轉點：沒有

Peewee ORM                 輕量、啟動快、SQL 貼近手寫；      SQLAlchemy：生態大、migration 工具
vs SQLAlchemy              多後端支援夠用（MySQL/PG/Gauss）  完整，但複雜度與學習曲線高
                                                            ▶ 翻轉點：需要複雜關聯查詢
                                                              或 Alembic 級 migration 時

一個 93 KB 的 executor     所有 ingestion 邏輯在一處，       一開始就拆成微服務：邊界清楚，
vs 一開始就拆微服務        改流程不用跨檔案；先長大再重構     但早期邊界必然畫錯、重畫成本高
                          （task_executor_refactor/）        ▶ 翻轉點：已經長到 93 KB 時
                                                              （就是現在，他們正在拆）

兩套 DAG 引擎              對話工作流與資料管線的執行語意     一套通用引擎：程式碼少，
（Canvas + Pipeline）      不同（中斷續跑 vs checkpoint、    但要在一個抽象裡同時滿足兩種語意，
vs 一套通用引擎            串流輸出 vs 批次陣列）；           結果是兩邊都不好用
                          但共用 Graph 基底與元件註冊表      ▶ 翻轉點：兩種語意收斂時

漸進式 Go 遷移             hybrid 模式讓每個 endpoint 可以    大爆炸重寫：一次到位、無雙實作
（API_PROXY_SCHEME）       獨立搬遷、獨立回退；               維護成本，但風險極高、期間無法發版
vs 大爆炸重寫              風險可控                           ▶ 翻轉點：專案還很小的時候

DeepDoc in-process         省掉一個進程與 IPC；               獨立解析微服務：可獨立擴充、
（靜態連結 ORT）           延遲降低；部署單一二進位            語言無關，但多一跳網路、多一組部署
vs 獨立解析服務                                              ▶ 翻轉點：解析需要獨立於 API
                                                              擴充時（GPU 池就是這個情況）

build tag 隔離測試         測試「編譯不進去」，不可能靜默     t.Skip + 環境變數：改動小，
vs t.Skip + env            通過；CI 行為完全確定               但被跳過的測試會靜默腐爛
                                                            ▶ 翻轉點：沒有；這是好設計

compose profile 多後端     一份 YAML 支援 6 種 doc engine    每種組合一份 compose：檔案直白，
vs 多份 compose            × 3 種 metadata DB × CPU/GPU      但 N×M×2 份檔案無法維護
                                                            ▶ 翻轉點：只支援一種組合時
```

---

## 十、系列總結與導航

五篇走完，把 RAGFlow 的完整設計整理成一張表——**每一列都是一個「如果沒有它會怎樣」的答案**：

| 層次 | 關鍵設計 | 沒有它的後果 | 篇章 |
|---|---|---|---|
| 解析 | OCR + Layout(10類) + TSR(5類) | 掃描件與表格不可用 | Part 2 |
| 解析 | 五條解析後端 + 8 個第三方解析器接入 | 綁死一種解析品質 | Part 2 |
| 切分 | 14 種模板 + 分隔符優先 + 允許一次溢出 | chunk 半句話、表頭分家 | Part 2 |
| 切分 | 不做原子切分，交下游截斷 | 段落被切在句中 | Part 2 |
| 人工 | chunk 可視化 + `important_kwd`(^30 ×5) | 人的修正無法產生槓桿 | Part 2/4 |
| 編碼 | 0.1 檔名 + 0.9 內容 | 檔名裡的關鍵資訊查不到 | Part 3 |
| 編碼 | 有問句就編碼問句 | 問句 vs 陳述句的非對稱匹配 | Part 3 |
| 儲存 | 後綴驅動動態 mapping | 換 embedding 模型要 migration | Part 3 |
| 儲存 | `min(tf,1)` 的 IDF-only 相似度 | 關鍵字堆疊的 chunk 霸榜 | Part 3 |
| 儲存 | 租戶級索引 + kb_id 過濾 | 500 個 KB = 1000 個 shard | Part 3 |
| 儲存 | 圖片存物件儲存 + `img_id` | 索引體積大 10 倍 | Part 3 |
| 檢索 | 規則式查詢編譯（同義詞+bigram+proximity） | 每次查詢多 500ms LLM | Part 4 |
| 檢索 | 雙路召回 + 加權融合 | 專名查詢靠向量猜 | Part 4 |
| 檢索 | ES 第二次 KNN-only 取分數 | 每次查詢搬 196 KB 向量 | Part 4 |
| 檢索 | 空結果退避（0.3→0.1，0.1→0.17） | 「文件裡明明有卻查不到」 | Part 4 |
| 檢索 | rank_feature 用加法不用乘法 | 權威但不相關的文件霸榜 | Part 4 |
| 檢索 | 分頁 + rerank 直接報錯 | 「第 1 頁翻兩次內容不同」 | Part 4 |
| 生成 | 兩層 token 預算（0.97 / 0.95） | 知識被歷史對話擠掉 | Part 4 |
| 引用 | 事後反查（0.1/0.9，0.63→0.3，上限 4） | 引用依賴 LLM 服從度 | Part 4 |
| 系統 | 訊息只放 ID + 取消查 DB | 任務投遞後不可取消 | Part 5 |
| 系統 | unacked 優先消費 | executor 重啟漏任務 | Part 5 |
| 系統 | 任務分池（`-t`） | GraphRAG 堵住一般解析 | Part 5 |
| 系統 | 無狀態 executor + 物件儲存 | 無法水平擴充 | Part 5 |
| 系統 | 漸進式 Go 遷移（hybrid） | 大爆炸重寫的風險 | Part 5 |
| 系統 | build tag 測試分層 | 被跳過的測試靜默腐爛 | Part 5 |

### 讀完之後可以做什麼

1. **調參有依據了**：Part 4 的權重總表就是一份調參手冊，而且你現在知道每個數字在管線的哪一層。
2. **排錯有路徑了**：進度百分比對應階段、log 關鍵字對應失敗模式。
3. **擴充有方向了**：加一個 chunk 模板就是在 `rag/app/` 加一個檔案 + `FACTORY` 加一行；加一個 agent 工具就是在 `agent/tools/` 丟一個檔案（動態註冊）；加一個 doc engine 就是實作 `DocStoreConnection`。
4. **借設計有素材了**：後綴驅動 schema、事後引用反查、rank_feature 用加法、build tag 測試分層——這四個設計可以直接搬進你自己的系統。

### 系列全篇

- [Part 1 — 全景架構 — 從一份 PDF 到一句帶引用的答案](../ragflow-intro-part1-overview-architecture-zh)
- [Part 2 — 資料進場 — DeepDoc 解析、Chunking 策略與 14 種模板](../ragflow-intro-part2-deepdoc-chunking-zh)
- [Part 3 — Encode 與 Save — 向量化、索引 Schema 與雙引擎抽象](../ragflow-intro-part3-embedding-indexing-zh)
- [Part 4 — Decode 與檢索 — 混合搜尋、Rerank、GraphRAG/RAPTOR 與引用](../ragflow-intro-part4-retrieval-rerank-zh)
- **Part 5（本篇）— 系統與程式碼結構 — 服務分層、Task Executor 與 Go 遷移**

← [Part 4 — Decode 與檢索 — 混合搜尋、Rerank、GraphRAG/RAPTOR 與引用](../ragflow-intro-part4-retrieval-rerank-zh)

---

*本文基於 RAGFlow `main` 分支（2026 年 9 月）原始碼撰寫。所有目錄結構、常數、參數與連結旗標皆從 `AGENTS.md`、`internal/development.md`、`docker/entrypoint.sh`、`rag/svr/task_executor.py`、`common/constants.py` 實際核對。RAGFlow 的 Go 遷移仍在進行中，該部分細節變動最快，請以你 clone 的版本為準。*
