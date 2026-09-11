---
title: "Mem0 Intro Part 4 — 儲存層與後端選型 — 三個 store、25 種向量庫與那個關鍵能力差異"
date: 2026-09-11T17:00:00+08:00
draft: false
weight: 4
description: "Mem0 原始碼導讀系列第四篇：拆解向量庫／實體庫／SQL 三個儲存層的實際 schema、25 種向量庫裡哪 15 種真的支援 BM25、配置系統的組裝方式、LLM 與 embedder 的選型判準，以及自架 server 的部署與多租戶隔離。"
categories: ["all", "ai", "engineering", "infrastructure"]
tags: ["Mem0", "Vector Database", "pgvector", "Qdrant", "Storage", "AI Agent", "Memory", "繁體中文"]
authors: ["yen"]
readTime: "26 min"
---

> *大多數人選向量庫的方式，是看 benchmark 的 QPS 數字，或者「團隊已經在用 Postgres 了就用 pgvector」。*
> *真正的答案是：在 Mem0 這套架構下，向量庫的選擇會直接決定你的三訊號檢索能不能運作——25 個支援的後端裡，有 10 個根本沒實作關鍵字檢索，選到它們，你的 BM25 訊號會靜默歸零。*
> *這不是效能差異，是功能差異。*
> *而它不會有任何錯誤訊息。*

---

## 前言

[Part 2](/posts/mem0-intro-part2-add-extraction-pipeline-zh/) 拆了寫入、[Part 3](/posts/mem0-intro-part3-hybrid-retrieval-zh/) 拆了讀取。兩條路徑上的每一次 `insert`、`search`、`keyword_search` 都委託給後端——**Mem0 自己不存任何東西**。

這一篇下到那一層：三個 store 各自存什麼、schema 長什麼樣、25 種向量庫的能力矩陣、以及那個影響最大卻最少被討論的差異——**誰有 `keyword_search`，誰沒有**。

本篇的目標：**讀完之後，你能對著自己的規模、語言、與已有基礎設施，選出一組後端，並說得出每個選擇放棄了什麼。**

---

## 一、核心問題：一份記憶被拆成三個地方存

### 1.1 為什麼不能只用一個資料庫

Part 1 給過結論，這裡補上原因。一條記憶要支援的查詢有五種，而它們對索引結構的要求互相衝突：

```
一條記憶：「Alice 推薦了中山區那家拉麵店」

查詢類型                需要的索引            衝突點
──────────────────────────────────────────────────────────────
「他喜歡什麼食物」      HNSW / IVF 向量索引   近似最近鄰，不保證精確
「拉麵」                倒排索引 + 分詞       需要詞彙統計（IDF）
「關於 Alice」          實體 → 記憶 反向索引  Alice 不在這條記憶的文字裡
「按時間列出」          B-tree on created_at  向量庫的排序能力普遍很弱
「這條哪來的」          稽核日誌              需要 append-only 的事件表
```

第三行是關鍵：**「Alice」這個詞完全沒有出現在記憶文字裡**，所以無論向量索引還是倒排索引都撈不到它。只有一個從實體指回記憶的反向索引能解決。

Mem0 的分法：

```
┌─────────────────────────────────────────────────────────────────┐
│  ① 向量資料庫 —— 記憶的主儲存                                     │
│     collection: "mem0"（預設）                                    │
│     一列 = 一條記憶                                               │
│     · vector：記憶文字的嵌入                                       │
│     · payload：data（記憶文字本身！）、hash、text_lemmatized、     │
│               created_at、updated_at、user_id/agent_id/run_id、   │
│               actor_id、role、attributed_to、expiration_date、    │
│               以及你傳的任意 metadata                             │
│     支援：向量檢索 + （若後端有能力）BM25 關鍵字檢索               │
├─────────────────────────────────────────────────────────────────┤
│  ② 實體儲存 —— 反向索引                                           │
│     collection: "mem0_entities"                                   │
│     （s3_vectors 用 "-" 分隔：_entity_collection_name()）         │
│     一列 = 一個實體                                               │
│     · vector：實體文字的嵌入（所以可以語意匹配 Alice↔Alice Chen） │
│     · payload：data（實體文字）、entity_type、                    │
│               linked_memory_ids（陣列，反指回記憶）、             │
│               user_id/agent_id/run_id                             │
├─────────────────────────────────────────────────────────────────┤
│  ③ SQL 資料庫 —— 稽核與情境                                       │
│     預設 SQLite：~/.mem0/history.db（可用 MEM0_DIR 改）           │
│     兩張表：history、messages                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 三個反直覺的設計

**反直覺一：記憶文字存在向量庫的 payload 裡，不在 SQL 裡。** 向量庫是**主儲存**（source of truth），不是快取。這代表：向量庫掛了 = 記憶全掉；備份策略要以向量庫為中心；換向量庫等於資料遷移，不是重建索引。

**反直覺二：實體庫不是一個獨立的資料庫。** 它是**同一個向量庫實例裡的另一個 collection**，用 `_entity_collection_name(provider, collection_name)` 產生名稱。優點是少一套維運；代價是實體查詢和記憶查詢搶同一份資源。

**反直覺三：SQL 那份是可以丟的。** `history` 表只是稽核日誌，`messages` 表只是萃取用的滾動情境——**兩者都不影響檢索**。SQLite 檔案刪掉，你會失去「這條記憶哪來的」的追溯能力，以及短期去重的品質，但記憶本身完好。這解釋了為什麼預設用 SQLite 這種看起來「太簡陋」的東西。

---

## 二、SQL 層：兩張表

`mem0/memory/storage.py`，347 行，只有兩張表。

### 2.1 `history` 表

```sql
CREATE TABLE IF NOT EXISTS history (
    id           TEXT PRIMARY KEY,
    memory_id    TEXT,
    old_memory   TEXT,
    new_memory   TEXT,
    event        TEXT,          -- v3 實際上永遠是 "ADD"
    created_at   DATETIME,
    updated_at   DATETIME,
    is_deleted   INTEGER,
    actor_id     TEXT,
    role         TEXT
)
```

**注意 `old_memory` 與 `event` 這兩欄的現狀**：`old_memory` 在 v3 的萃取路徑上永遠是 `None`（見 Part 2 Phase 6 的 `batch_add_history`），`event` 永遠是 `"ADD"`。這兩欄是 v2 四動作模型的遺留——**schema 還在，但萃取管線不再產生 UPDATE / DELETE 事件**。

你自己呼叫 `update()` 或 `delete()` 時，它們會正確寫入。但如果你依賴這張表做「記憶演變」的分析，要知道**自動萃取只會留下 ADD 軌跡**。

`_migrate_history_table()` 用的是經典的 SQLite schema 遷移手法：`ALTER TABLE history RENAME TO history_old` → 建新表 → 搬資料。這代表**升級版本時這張表會被重建**，大表上要留意時間。

### 2.2 `messages` 表

```sql
CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,
    session_scope TEXT,      -- 由 _build_session_scope(filters) 產生
    role          TEXT,
    content       TEXT,
    name          TEXT,
    created_at    DATETIME
)
```

這張表只服務一個目的：Part 2 的 Phase 0，`get_last_messages(session_scope, limit=10)`。

**`session_scope` 是怎麼組的**：`_build_session_scope()` 把 `user_id` / `agent_id` / `run_id` 組成一個字串鍵，值會經過 `_escape_scope_value()` 轉義——防止一個帶特殊字元的 ID 撞進別人的 scope。

**一個容易忽略的事實**：這張表會無限成長。它存的是**原始對話逐字稿**，而且沒有內建的清理機制。長期運作要自己加清理作業：

```sql
DELETE FROM messages
WHERE created_at < datetime('now', '-30 days');
```

**而且它存的是原始訊息**——如果你的對話含個資，這張表就是一份未經萃取的個資副本。GDPR 的刪除請求必須涵蓋它，Part 5 會詳述。

### 2.3 換掉 SQLite

`MemoryConfig.history_db_path` 只接受一個路徑，所以 OSS 的 `Memory` 類別**只支援 SQLite**。要用 Postgres，路徑是走 `server/`（它用 Alembic + SQLAlchemy 管自己的表）。

```
選擇             選 SQLite 的理由                  不選的理由 / 翻轉條件
────────────────────────────────────────────────────────────────────────
SQLite（預設）   零設定、零維運、單檔可備份         單進程寫入（有鎖但仍受限）
                 讀取極快                           多副本部署時各自一份 → 
                 這兩張表本來就是可丟的              去重情境與稽核都會分裂
                 ──────────────────────────────────────────────────────
翻轉條件：一旦你跑多個 Mem0 進程（web + worker + 排程），SQLite 的
per-process 檔案就會讓 messages 滾動窗失去意義——worker 看不到 web 剛存的
訊息，去重品質下降。此時改用 server/ 的 Postgres 版本，或把 history_db_path
指到共用磁碟（不建議：SQLite over NFS 是經典的資料損毀來源）。
```

---

## 三、向量庫：那個決定功能的選擇

### 3.1 能力矩陣

Mem0 註冊了 **25 個向量庫 provider**（`mem0/vector_stores/configs.py` 的 `_provider_configs`）。但它們的能力**不對等**，最關鍵的差異是有沒有實作 `keyword_search()`。

`VectorStoreBase.keyword_search()` 的預設實作回傳 `None`，而 `_search_vector_store()` 收到 `None` 就**整條 BM25 訊號停用**——沒有警告、沒有日誌、沒有例外。

```
支援 keyword_search（15 個）        未實作（10 個）
────────────────────────────────────────────────────────
azure_ai_search                     chroma
azure_mysql                         cassandra
baidu                               faiss          ← 常見的本機選擇
databricks                          langchain
elasticsearch                       neptune
milvus                              oracledb
mongodb                             s3_vectors
opensearch                          supabase       ← 很多人用
pgvector        ← 自架首選           turbopuffer
pinecone                            valkey
qdrant          ← 預設
redis
upstash_vector
vertex_ai_vector_search
weaviate
```

**兩個最容易踩的**：

- **FAISS** — 很多人拿它做本機開發，因為不用起服務。但它沒有 `keyword_search`，所以**你在本機測出來的檢索品質，會比上線後用 Qdrant 的差**（或反過來：本機調好的 threshold 上線後不適用）。
- **Supabase / Chroma** — 都是很受歡迎的入門選擇，都沒有實作。

**怎麼確認你的後端真的在做 BM25**：用 Part 3 的 `explain=True`，看 `max_possible_score`。如果它是 1.0 或 1.5 而不是 2.0 或 2.5，BM25 沒在跑。

### 3.2 四個真實配置

**(a) 本機開發 / POC**

```python
from mem0 import Memory
m = Memory()      # 預設 Qdrant
```

預設就是 Qdrant，且支援 BM25。如果你想完全不起服務，Qdrant 的 Python client 支援記憶體內模式與本機檔案模式——**比換成 FAISS 好**，因為能力一致。

**(b) 已經在用 Postgres 的團隊**

```python
m = Memory.from_config({
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": "localhost", "port": 5432,
            "user": "postgres", "password": "...",
            "dbname": "mem0", "collection_name": "memories",
        }
    }
})
```

**這是自架的最佳解**，理由有三：支援 `keyword_search`；一個資料庫同時當向量庫、實體庫（另一張表）與應用資料庫，少一套維運；官方 `server/docker-compose.yaml` 就是用 `pgvector/pgvector:pg17`，是最多人走過的路。

**代價**：pgvector 在千萬級向量上的檢索效能不如專用向量庫。但**記憶場景的資料量通常遠低於這個級別**——一個使用者累積一年也就幾千條，十萬使用者才幾百萬條。在撞到這個牆之前，簡單性的價值高得多。

**(c) 中文 / 多語言場景**

```python
m = Memory.from_config({
    "vector_store": {
        "provider": "elasticsearch",
        "config": {"host": "...", "port": 9200, "collection_name": "mem0"}
    }
})
```

Part 3 第七節講過：中文的 BM25 需要分詞器。Elasticsearch / OpenSearch 可以配 IK 或 jieba 分詞器，**讓 `keyword_search` 在中文上真的運作**——這是唯一能救回 BM25 訊號的後端路線。

**注意**：分詞器要在 ES 的索引 mapping 層面配置，Mem0 不會幫你做。你需要先手動建好 index template，再讓 Mem0 用那個 collection。

**(d) 不想維運任何東西**

```python
m = Memory.from_config({
    "vector_store": {
        "provider": "qdrant",
        "config": {"url": "https://xxx.cloud.qdrant.io", "api_key": "..."}
    }
})
```

受管的 Qdrant Cloud / Pinecone。能力完整，成本隨向量數成長。

### 3.3 選型決策樹

```
                    你已經有向量庫或資料庫嗎？
                              │
        ┌─────────────────────┴─────────────────────┐
       有                                          沒有
        │                                           │
   它在支援清單裡嗎？                        主要語言是什麼？
        │                                           │
  ┌─────┴─────┐                          ┌──────────┴──────────┐
 是          否                         英文                 中文/多語
  │           │                          │                     │
  ▼           ▼                          ▼                     ▼
它支援    換一個，或    ┌──────────────────────┐  ┌──────────────────────┐
keyword_  接受單訊號    │ 有 Postgres 團隊？    │  │ Elasticsearch /      │
search？  檢索          │  是 → pgvector       │  │ OpenSearch + 中文分詞│
  │                     │  否 → qdrant（預設） │  │ ← 唯一能讓 BM25      │
┌─┴──┐                  └──────────────────────┘  │    在中文運作的路線  │
是   否                                            │ 或：接受 BM25 失效， │
│    │                                             │ 改用多語言 reranker  │
▼    ▼                                             └──────────────────────┘
用它  用它但知道 BM25 失效
      → 一定要開 reranker 補償
```

---

## 四、LLM 與 Embedder 選型

### 4.1 LLM：只在寫入路徑用

Mem0 支援 **18 個 LLM provider**（`mem0/llms/`）：OpenAI（含 structured 變體）、Anthropic、Azure OpenAI、AWS Bedrock、Gemini、Groq、DeepSeek、MiniMax、xAI、Sarvam、Together、Ollama、LM Studio、LiteLLM、vLLM、LangChain 等。

**選型的三個判準**（按重要性排序）：

**判準一：JSON 模式的可靠性。** 萃取階段用 `response_format={"type": "json_object"}`。原始碼有多層 fallback（`remove_code_blocks` → `json.loads` → `extract_json`），但**每一次 fallback 都是一次可能的資訊遺失**。選一個 JSON 輸出穩定的模型，比選一個「更聰明」的模型重要。

**判準二：成本。** 萃取是一個高頻操作。Part 2 算過：每次 `add()` 約 $0.002–0.02。乘上你的日均對話量，這通常是整個記憶層最大的單一成本項。

**判準三：長 prompt 的指令遵循能力。** `ADDITIVE_EXTRACTION_PROMPT` 有近 500 行，裡面有大量「不要做 X」的負面指令。小模型在長負面指令上的遵循度顯著較差——**最常見的失敗是把既有記憶當成新事實再輸出一遍**，導致記憶庫每次 `add()` 都膨脹。

```
選擇              選 X 的理由                      不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────
雲端小模型        JSON 模式穩定、指令遵循好         成本隨對話量線性成長
（如 GPT-5-mini） 萃取品質與大模型差距不大          資料要出境
vs 雲端大模型     成本低一個量級                    ────────────────────────
                  ────────────────────────────────────────────────────────
                  翻轉條件：你的對話極度專業（醫療、法律）且萃取錯誤代價高 →
                  用大模型。否則萃取是一個結構化抽取任務，小模型夠用。
                  **但務必先用自己的語料比一次萃取結果再換。**

本機模型          資料完全不出境                    JSON 模式支援參差
（Ollama/vLLM）   零 API 成本                       長 prompt 遵循度較弱
vs 雲端           延遲可控（本機 GPU）              需要維運推論服務
                  ────────────────────────────────────────────────────────
                  翻轉條件：合規要求資料不出境 → 沒得選，只能本機。
                  此時建議把 ADDITIVE_EXTRACTION_PROMPT 精簡過再用，
                  並且一定要做萃取品質的抽樣檢查。

LiteLLM           一個介面接所有供應商              多一層抽象、多一個依賴
vs 直接用         方便做 A/B 與 failover            ────────────────────────
   原生 provider  ────────────────────────────────────────────────────────
                  翻轉條件：你需要在多個供應商間做容錯或成本路由 → LiteLLM。
                  只用一家 → 直接用原生 client，少一層。
```

### 4.2 Embedder：寫入與讀取都用

支援 **12 個 provider**。預設 `text-embedding-3-small`（1536 維）。

**三個選型要點**：

**要點一：維度直接決定儲存成本。** 1536 維 × 4 bytes = 6 KB/向量。十萬條記憶 + 十萬個實體 = 1.2 GB 的純向量。降到 768 維直接省一半。

**要點二：換模型 = 全部重建。** 向量之間不可比。換 embedder 意味著要把所有記憶與所有實體重新嵌入一遍——**這是一個以小時計的離線作業**，而且期間檢索品質會不一致。**在 POC 階段就決定好。**

**要點三：`embed(text, "add")` 與 `embed(text, "search")` 的第二個參數。** 部分模型（尤其是為檢索優化的開源模型）對查詢與文件用不同的前綴。Mem0 把這個語意傳給了 embedder 實作——如果你自訂 embedder，要正確處理它，否則檢索品質會有系統性偏差。

**要點四（中文場景）**：`text-embedding-3-small` 的中文表現尚可但不是最佳。官方 README 提到「recommends Qwen or comparable models for hybrid search」。考慮到 Part 3 說的 BM25 與實體訊號在中文上會失效，**中文場景下 embedder 的品質權重更高**——它幾乎是唯一的訊號。

---

## 五、配置系統：怎麼組起來

### 5.1 `MemoryConfig` 的完整結構

```python
class MemoryConfig(BaseModel):
    vector_store:        VectorStoreConfig   # 預設 qdrant
    llm:                 LlmConfig           # 預設 openai
    embedder:            EmbedderConfig      # 預設 text-embedding-3-small
    history_db_path:     str                 # 預設 ~/.mem0/history.db
    reranker:            Optional[RerankerConfig] = None
    version:             str = "v1.1"
    custom_instructions: Optional[str] = None
```

七個欄位，就是全部。用 `from_config` 組裝：

```python
from mem0 import Memory

m = Memory.from_config({
    "vector_store": {
        "provider": "pgvector",
        "config": {"host": "...", "dbname": "mem0", "collection_name": "memories"},
    },
    "llm": {
        "provider": "openai",
        "config": {"model": "gpt-5-mini", "temperature": 0.0},
    },
    "embedder": {
        "provider": "openai",
        "config": {"model": "text-embedding-3-small"},
    },
    "reranker": {
        "provider": "cohere",
        "config": {"model": "rerank-multilingual-v3.0", "top_n": 10},
    },
    "history_db_path": "/var/lib/mem0/history.db",
    "custom_instructions": "只萃取與醫療照護相關的事實，忽略閒聊。",
})
```

每個 `provider` 的合法值與對應的 config 類別，都寫在各自的 `configs.py` 的 `_provider_configs` 字典裡，用 pydantic 的 `model_validator` 在建構時驗證——**打錯 provider 名稱會在啟動時就炸，不會等到執行期**。

### 5.2 `custom_instructions` 的正確用法

這是 v3 把 `custom_fact_extraction_prompt` 改名來的（`custom_update_memory_prompt` 則直接廢棄）。它被附加進萃取的 user prompt。

```
✅ 適合寫進 custom_instructions 的：
   · 萃取範圍：「只記與專案管理相關的事實」
   · 領域詞彙：「把 'PR' 理解為 pull request 而非公關」
   · 輸出風格：「記憶文字要包含對話日期」（Part 3 第八節的時序補法）
   · 排除規則：「忽略關於天氣與問候的內容」

❌ 不適合的：
   · 「如果發現矛盾就不要萃取」
     → 這是把 UPDATE 的判斷偷渡回 LLM，而它只看得到 top-10 既有記憶
   · 「刪除過時的記憶」
     → 萃取階段根本沒有 DELETE 這個動作可用，寫了也不會發生
   · 超長的規則清單
     → ADDITIVE_EXTRACTION_PROMPT 本身已經近 500 行，
       再疊上去會稀釋掉原本的指令
```

也可以在單次呼叫時覆寫：`m.add(messages, user_id=u, prompt="...")`——原始碼裡 `custom_instr = prompt or self.custom_instructions`，**單次的 prompt 參數會完全取代全域設定，不是附加**。

---

## 六、三個演進階段

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：全部在本機 —— 一個進程一份資料            ║
### ╚═══════════════════════════════════════════════════╝

```
┌──────────────────────────────────────────────┐
│  你的 Python 進程                             │
│  ┌────────────────────────────────────────┐  │
│  │ Memory()                                │  │
│  │  ├─ Qdrant（本機 / 記憶體內）            │  │
│  │  └─ SQLite ~/.mem0/history.db           │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

- **可接受的捷徑**：無備份、單進程、資料在開發者的筆電上。
- **成本**：$0（除了 LLM 與 embedding API）。
- **解決了什麼**：能跑、能驗證產品假設。
- **還沒解決什麼**：進程重啟就沒了（除非 Qdrant 指到持久化路徑）；多進程會各自一份 SQLite；沒有任何備份。
- **必做的一件事**：`pip install "mem0ai[nlp]"` + `python -m spacy download en_core_web_sm`。不做的話實體訊號靜默失效（Part 1 第五節）。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：共用後端 —— pgvector 一庫三用             ║
### ╚═══════════════════════════════════════════════════╝

```
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Web 進程 │  │ Worker   │  │ 排程任務  │
   │ search() │  │ add()    │  │ 清理/合併 │
   └─────┬────┘  └─────┬────┘  └─────┬────┘
         └─────────────┼─────────────┘
                       ▼
   ┌───────────────────────────────────────────┐
   │  PostgreSQL 17 + pgvector                  │
   │  ┌─────────────┐ ┌──────────────────────┐ │
   │  │ memories    │ │ memories_entities    │ │
   │  │ (向量+payload)│ │ (實體+linked_ids)   │ │
   │  └─────────────┘ └──────────────────────┘ │
   │  ＋ server/ 的 history / messages 表        │
   └───────────────────────────────────────────┘
```

**相對 Phase 1 新增的元件**：

| 新增 | 為什麼 |
|---|---|
| PostgreSQL + pgvector | 多進程共用同一份記憶；SQLite 在多進程下會分裂 |
| 讀寫分離（search 在 web、add 在 worker） | `add()` 要 1–1.8 秒，不能擋請求 |
| 佇列（Celery / SQS / Kafka） | 削 LLM rate limit 的峰 |
| 備份策略 | **向量庫是主儲存**，掛了記憶全失 |
| 定期清理 `messages` 表 | 它會無限成長，且存的是原始逐字稿 |
| 合併作業 | ADD-only 的補償（Part 2 第七節） |

- **成本 delta**：一台 Postgres（$50–200/月）+ 佇列基礎設施。**LLM 成本仍是大頭。**
- **複雜度 delta**：從「一個 import」變成「一個資料庫 + 一組 worker + 一份備份 runbook」。
- **解決了什麼**：多進程、持久化、可備份。
- **還沒解決什麼**：多租戶隔離、合規刪除、以及規模。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：多租戶與治理                              ║
### ╚═══════════════════════════════════════════════════╝

```
        ┌───────────────────────────────────────────┐
        │  應用層：租戶認證、配額、稽核               │
        └──────────────────┬────────────────────────┘
                           │
        ┌──────────────────┼───────────────────────┐
        ▼                  ▼                       ▼
┌───────────────┐ ┌────────────────┐ ┌──────────────────────┐
│ 隔離策略 A     │ │ 隔離策略 B      │ │ 治理作業              │
│ 同一 collection│ │ 每租戶一個      │ │ · 週期合併去重        │
│ 用 filter 隔離 │ │ collection      │ │ · messages 表清理     │
│                │ │                 │ │ · PII 掃描            │
│ 便宜、共用索引 │ │ 貴、完全隔離    │ │ · 刪除權執行          │
│ 靠 user_id     │ │ 靠 collection   │ │ · 品質抽樣            │
│ 過濾（有風險） │ │ 名稱（硬隔離）  │ │                      │
└───────────────┘ └────────────────┘ └──────────────────────┘
```

**相對 Phase 2 新增的元件**：

| 新增 | 為什麼 |
|---|---|
| 租戶隔離策略（二選一，見 6.1） | 一個 filter 寫錯 = 把 A 的記憶給 B |
| 三處貫通的刪除流程 | 刪一個使用者要同時清向量庫、實體庫、SQL 兩張表 |
| PII 偵測 | 記憶層是個資的集中地，而萃取會把口語轉成結構化事實——**反而更敏感** |
| 品質評測迴圈 | 換模型、改提示詞之後要能驗證召回沒退化 |
| 成本歸因 | 哪個租戶吃掉了你的 LLM 預算 |

- **複雜度 delta**：質變。你在維運一個存個資、有狀態、且品質無法用單元測試驗證的系統。
- **什麼時候該改用 Platform**：當你發現自己在寫「哪條記憶才是最新」的邏輯、在做背景去重、在補時序推理——**你正在重造 Platform 的功能**。Part 5 有完整對照。

### 6.1 兩種租戶隔離策略

```
選擇                選 X 的理由                     不選 Y 的理由 / 翻轉條件
────────────────────────────────────────────────────────────────────────────
filter 隔離         一個 collection，維運簡單        隔離靠程式碼正確性：
（用 user_id）      索引共用，成本低                 一次漏傳 filter = 資料洩漏
                    新租戶零成本                     刪除是 DELETE WHERE，
                    ─────────────────────────────────────────────────────  大租戶會很慢
collection 隔離     硬隔離，程式錯誤也洩不了         每個 collection 有固定開銷
（每租戶一個）      刪租戶 = drop collection，秒殺   租戶數上千時管理複雜
                    可依租戶分級配資源               跨租戶查詢做不到
                    ─────────────────────────────────────────────────────
翻轉條件：
· B2C、租戶數多、單租戶資料量小 → filter 隔離，但務必在應用層強制注入
  user_id（用一個 wrapper，不讓業務程式碼直接呼叫 Mem0）
· B2B、租戶數少（< 500）、有合規隔離要求 → collection 隔離
· 混合：大客戶獨立 collection，小客戶共用 —— 這是多數 SaaS 的最終形態
```

**filter 隔離的強制做法**（值得抄）：

```python
class ScopedMemory:
    """不讓業務程式碼直接碰 Mem0，強制注入 user_id。"""
    def __init__(self, memory: Memory, user_id: str):
        if not user_id or not user_id.strip():
            raise ValueError("user_id required")
        self._m, self._uid = memory, user_id

    def add(self, messages, **kw):
        kw.pop("user_id", None)                       # 不讓呼叫端覆寫
        return self._m.add(messages, user_id=self._uid, **kw)

    def search(self, query, *, filters=None, **kw):
        filters = {**(filters or {}), "user_id": self._uid}   # 永遠覆蓋
        return self._m.search(query, filters=filters, **kw)
```

---

## 七、自架 server

`server/` 目錄是一個獨立的 FastAPI 應用，不是 `mem0` 套件的一部分。

```
server/
├── main.py           FastAPI app
├── routers/          REST 端點
├── auth.py           JWT 認證
├── rate_limit.py     限流
├── db.py, models.py  SQLAlchemy（history / messages 搬到 Postgres）
├── alembic/          schema 遷移
├── dashboard/        Web UI
└── docker-compose.yaml
```

```bash
cd server
cp .env.example .env        # 填 OPENAI_API_KEY、POSTGRES_PASSWORD、JWT_SECRET
docker compose up -d
# Mem0 server: http://localhost:8888
# Postgres:    localhost:8432
```

`docker-compose.yaml` 用 `pgvector/pgvector:pg17`，啟動時跑 `alembic upgrade head` 再起 uvicorn。

**三個部署注意事項**：

1. **`AUTH_DISABLED` 預設是 `false`**，這是對的。但很多人為了本機測試設成 `true` 之後忘了改回來——**檢查你的生產環境變數**。
2. **Alembic 遷移在容器啟動時跑**。多副本部署時會有多個容器同時跑 `alembic upgrade head`——要嘛用 init container 只跑一次，要嘛確認你的 Alembic 版本有鎖。
3. **`server/` 的版本節奏與 `mem0` 套件不同步**。`docker-compose.yaml` 裡的 dev 設定會 `pip install --force-reinstall mem0ai`——生產環境要鎖定版本，不要讓它每次重啟都拉最新的。

```
選擇              選 server/ 的理由                不選的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────
自架 server/      多語言客戶端（不只 Python）       多一個要部署的服務
vs 直接 import    集中認證與限流                    多一跳網路延遲
   mem0 套件      history/messages 在 Postgres      dashboard 是額外的攻擊面
                  有 dashboard 可視化               ────────────────────
                  ──────────────────────────────────────────────────────
                  翻轉條件：只有 Python 應用、且只有一兩個進程 → 直接 import
                  套件，指向共用的 pgvector 就好，不需要多一層 HTTP。
                  有 Node/Go 服務要用，或需要集中管控 → 用 server/。
```

---

## 八、備份、遷移與災難復原

這一節是官方文件完全沒講、但生產環境一定會遇到的。

### 8.1 備份什麼

```
必備份（丟了記憶就沒了）：
  ① 向量庫的 memories collection     ← 記憶文字在 payload 裡
  ② 向量庫的 entities collection     ← 丟了實體訊號失效，但可重建

可選備份（丟了不影響檢索）：
  ③ SQL 的 history 表                ← 稽核軌跡
  ④ SQL 的 messages 表               ← 短期去重情境，一週就自然過期

不需要備份：
  · 向量本身可以從 payload.data 重新嵌入（但要花錢與時間）
  · spaCy 模型、設定檔（放版控）
```

**② 的重建方式**：跑一次全量 `get_all()`，對每條記憶重新做 `extract_entities()` 與連結。這是一個可以寫成腳本的離線作業，值得先寫好放著。

### 8.2 換 embedder 的遷移流程

這是最痛的一種遷移，因為**向量之間不可比**。

```
1. 建一個新的 collection（不要就地改）
2. 全量 get_all() 撈出記憶文字與 metadata
3. 用新 embedder 重新嵌入，寫進新 collection
4. 實體庫同樣重建
5. 雙寫期：新的 add() 同時寫兩邊
6. 切換讀取到新 collection，觀察召回指標
7. 確認無誤後停止雙寫，刪舊 collection
```

**第 6 步的「觀察召回指標」需要 Part 3 第五節的標註集。** 沒有標註集，你只能靠感覺判斷新模型是不是更好——而感覺在這件事上非常不可靠。

### 8.3 GDPR 刪除：三處都要清

```python
def hard_delete_user(m: Memory, user_id: str):
    # ① 記憶（Mem0 提供）
    m.delete_all(user_id=user_id)

    # ② 實體庫 —— delete_all 是否連動清實體，依版本而異，
    #    務必自己驗證一次：刪完之後查實體庫還有沒有殘留的
    #    linked_memory_ids 指向已刪的記憶
    #    （孤兒實體不會造成錯誤答案，但會造成無效的加權計算）

    # ③ SQL 的 messages 表 —— 存的是原始對話逐字稿！
    #    Mem0 沒有提供 API，要自己下 SQL
    #    DELETE FROM messages WHERE session_scope LIKE '%user_id%'

    # ④ SQL 的 history 表
    #    DELETE FROM history WHERE memory_id IN (...)
```

**③ 是最容易漏的**，也是合規風險最高的——**它存的是未經萃取的原始對話**。上線前一定要實際跑一次刪除，然後去資料庫裡確認每一處都乾淨了。

---

## 九、為什麼選 X 不選 Y（彙整）

```
選擇                 選 X 的理由                       不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────────
支援 keyword_search  三訊號檢索完整運作                 不支援的後端：可能你
的後端               BM25 解決專有名詞與 ID 查詢         已經在用、或部署更簡單
vs 不支援的           ──────────────────────────────────────────────────────────
                     翻轉條件：純中文場景且沒配分詞器——此時 BM25 本來就失效，
                     支不支援沒差別，該投資的是多語言 reranker。

pgvector             一庫三用，少一套維運               專用向量庫：千萬級
vs 專用向量庫        支援 keyword_search                向量的檢索效能更好
                     交易一致性（記憶與業務資料同庫）   ──────────────────────
                     ──────────────────────────────────────────────────────────
                     翻轉條件：向量數超過千萬、或你需要進階的向量索引調校 →
                     換 Qdrant / Milvus。記憶場景通常撞不到這個牆。

Qdrant（預設）       開箱即用、能力完整                 pgvector：如果你本來
vs pgvector          有記憶體內模式方便測試             就有 Postgres，多一個
                     ──────────────────────────────────────────────────────────  系統不划算
                     翻轉條件：純粹看你有沒有既有的 Postgres。兩者能力對等。

實體庫共用向量庫     少一套維運、設定簡單               獨立實例：實體查詢
vs 獨立實例          ──────────────────────────────────────────────────────────  不跟記憶查詢搶資源
                     翻轉條件：Mem0 沒有提供分開配置的選項——`_entity_collection_
                     name()` 直接從主 collection 名稱衍生。要分開只能自己改碼。

SQLite 存 history    零維運、這兩張表本來就可丟         Postgres：多進程共用
vs Postgres          ──────────────────────────────────────────────────────────
                     翻轉條件：一旦多進程，SQLite 的 messages 滾動窗會分裂，
                     去重品質下降。此時走 server/ 的 Postgres 版本。

雲端小模型萃取       成本低一個量級、JSON 穩定          本機模型：資料不出境
vs 本機模型          ──────────────────────────────────────────────────────────
                     翻轉條件：合規要求。此時要接受萃取品質下降，並加強抽查。

filter 租戶隔離      維運簡單、新租戶零成本             collection 隔離：
vs collection 隔離   ──────────────────────────────────────────────────────────  硬隔離、刪除快
                     翻轉條件：見 6.1。B2C 用 filter + wrapper 強制注入，
                     B2B 且租戶少用 collection。

server/ 自架服務     多語言客戶端、集中管控             直接 import 套件：
vs 直接 import       ──────────────────────────────────────────────────────────  少一跳、少一個服務
                     翻轉條件：只有 Python 且進程少 → import。有其他語言 → server。
```

---

## 十、系列導航

本篇下到了儲存層：三個 store 的 schema、25 個後端的能力矩陣、以及那個最該先確認的問題——**你的向量庫有沒有 `keyword_search`**。

三件事值得帶走：

1. **向量庫是主儲存，不是快取。** 記憶文字存在 payload 裡。備份、遷移、災難復原都要以它為中心。
2. **後端選擇決定功能，不只是效能。** 25 個 provider 裡 10 個沒有 BM25，選到它們你的三訊號檢索就變成單訊號——而且沒有任何警告。用 `explain=True` 的 `max_possible_score` 自己確認。
3. **`messages` 表是一份未經萃取的原始對話副本。** 它會無限成長，且是合規刪除最容易漏掉的地方。

到這裡，OSS 版本的全貌已經拆完：寫入、讀取、儲存。但一路上有太多地方指向同一個方向——**「這個在 Platform 有，OSS 沒有」**：圖記憶、時序推理、記憶衰減、背景整合、自訂分類、webhook。

最後一篇把這條線收起來：OSS 與 Platform 的完整差異、四個 Platform 專屬能力各自解決什麼問題（以及你在 OSS 要怎麼自己補）、v2→v3 的破壞性變更遷移清單、怎麼用官方開源的評測框架測自己的資料、以及一份生產檢查清單。

- **Part 5 — 生產部署**：OSS vs Platform、進階能力、遷移與評測

← [Part 3 — 讀取路徑 — 語意、關鍵字與實體的三訊號融合](/posts/mem0-intro-part3-hybrid-retrieval-zh/) | [Part 5 — 生產部署 — OSS 與 Platform 的分界線在哪裡 →](/posts/mem0-intro-part5-production-oss-vs-platform-zh/)

---

*本文基於 mem0 `main` 分支（2026 年 9 月，版本 2.0.20）原始碼撰寫。provider 清單與能力矩陣由 `mem0/vector_stores/configs.py` 的註冊表與各實作檔案的 `keyword_search` 定義實際掃描而得；schema 對照 `mem0/memory/storage.py`；部署設定對照 `server/docker-compose.yaml`。成本數字為量級估算。*
