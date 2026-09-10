---
title: "RAGFlow Intro Part 3 — Encode 與 Save — 向量化、索引 Schema 與雙引擎抽象"
date: 2026-09-10T11:00:00+08:00
draft: false
weight: 3
description: "RAGFlow 原始碼導讀系列第三篇：拆解混合向量（0.1 檔名 + 0.9 內容）的設計理由、批次與截斷策略、以後綴驅動的動態 ES mapping、把 TF 壓成 min(freq,1) 的自訂相似度，以及支撐六種 doc engine 的儲存抽象層。"
categories: ["all", "ai", "engineering"]
tags: ["RAGFlow", "RAG", "AI", "Embedding", "Elasticsearch", "Vector Database", "Infinity", "繁體中文"]
authors: ["yen"]
readTime: "25 min"
---

> *大多數人處理 RAG 的儲存，是 `collection.add(documents=chunks, embeddings=vecs)`，然後就不再想這件事。*
> *真正的答案是：索引的 schema 決定了你三個月後能做什麼查詢；相似度函式決定了你的關鍵字檢索是有效還是裝飾；欄位命名決定了你換 embedding 模型要不要重建整個索引。*
> *這些決定在寫入的那一刻就凍結了。*
> *這篇文章拆的是 RAGFlow 在那一刻做的每一個選擇。*

---

## 前言

[Part 2](../ragflow-intro-part2-deepdoc-chunking-zh) 結束時，我們手上有一組 chunk：純文字、可能帶版面座標、可能帶人工或 LLM 產生的關鍵字與問句。

本篇處理接下來兩步：

```
chunks ──▶ ① Encode（向量化）  ──▶ ② Save（寫進 doc engine + 物件儲存）
           rag/svr/task_executor.py    conf/mapping.json
           rag/llm/embedding_model.py  rag/utils/*_conn.py
```

這兩步看起來機械，實際上藏了 RAGFlow 最有辨識度的幾個設計。我們從最反直覺的一個開始。

---

## 一、Encode：為什麼向量是「檔名 × 0.1 + 內容 × 0.9」

`task_executor.py` 的 `embedding()` 函式，核心只有幾行：

```python
async def embedding(docs, mdl, parser_config=None, callback=None):
    tts, cnts = [], []
    for d in docs:
        tts.append(d.get("docnm_kwd", "Title"))          # ① 檔名
        c = "\n".join(d.get("question_kwd", []))          # ② 有問句就用問句
        if not c:
            c = d["content_with_weight"]                  #    沒有才用內容
        c = re.sub(r"</?(table|td|caption|tr|th)( [^<>]{0,12})?>", " ", c)
        cnts.append(c)

    # 檔名只編碼一次，然後複製到所有 chunk
    vts, c = await thread_pool_exec(mdl.encode, tts[0:1])
    tts = np.tile(vts[0], (len(cnts), 1))

    # 內容分批編碼
    for i in range(0, len(cnts), settings.EMBEDDING_BATCH_SIZE):
        vts, c = await thread_pool_exec(batch_encode, cnts[i:i + settings.EMBEDDING_BATCH_SIZE])
        ...

    title_w = float(parser_config.get("filename_embd_weight", 0.1) or 0.1)
    vects = title_w * tts + (1 - title_w) * cnts          # ③ 加權混合

    for i, d in enumerate(docs):
        v = vects[i].tolist()
        d["q_%d_vec" % len(v)] = v                        # ④ 欄位名帶維度
    return tk_count, vector_size
```

四個決定，每一個都值得單獨講。

### 1.1 檔名混進向量：解決「文件層級語意遺失」

考慮一個真實情境：一個知識庫裡有 200 份文件，其中一份叫 `2025-Q3-財報-台灣區.pdf`。裡面有一個 chunk 寫著：

> 「本季營收較上季成長 12%，主要來自通路擴張。」

使用者查詢：**「台灣區 Q3 的營收成長」**。

這個 chunk 的內容裡完全沒有「台灣」和「Q3」——它們在**檔名**裡。純內容向量會讓這個 chunk 排在後面，因為它跟「台灣區 Q3」的語意距離不近。

`filename_embd_weight = 0.1` 的作用就是：**把文件層級的語意，以 10% 的權重摻進每一個 chunk 的向量裡。** 同一份文件的所有 chunk 因此共享一個微小的「文件身分」偏移。

**為什麼是 0.1 而不是 0.3？** 因為權重太高會讓同一份文件的所有 chunk 彼此變得過於相似——你查任何東西，都會召回同一份文件的一堆 chunk，多樣性崩掉。0.1 是「足以在文件間區分，不足以壓過內容差異」的量級。

實作上還有一個小優化：**檔名只 encode 一次，然後 `np.tile` 複製到所有 chunk。** 一份 200 chunk 的文件，檔名向量只算一次，省下 199 次呼叫。

### 1.2 有 `questions` 時，編碼問句而不是內容

```python
c = "\n".join(d.get("question_kwd", []))
if not c:
    c = d["content_with_weight"]
```

這行的行為很激烈：**如果 chunk 有 `question_kwd`（來自 `qa` 模板或 `question_proposal` 加值），就完全用問句取代內容去做 embedding。**

理由是 embedding 的**對稱性問題**。使用者輸入的是問句，chunk 存的是陳述句。「Q3 毛利率是多少？」和「本季毛利率為 39.8%」在向量空間裡的距離，通常大於「Q3 毛利率是多少？」和「本季毛利率是多少？」之間的距離。

**把 chunk 的向量換成「這個 chunk 能回答的問題」，就把問題—答案的非對稱匹配，轉成問題—問題的對稱匹配。** 這就是 HyDE 的鏡像版本：HyDE 是在查詢端生成假答案，這裡是在文件端生成假問題。

代價很明確：**如果生成的問句品質差，整個 chunk 的向量就毀了。** 這也是 `question_proposal` 預設關閉的原因之一。內容本身還是完整保留在 `content_with_weight` 欄位，全文檢索仍然打得到，所以最壞情況是向量路失效、關鍵字路還在——**混合檢索在這裡提供了容錯。**

### 1.3 移除表格標籤：一個小但重要的清理

```python
c = re.sub(r"</?(table|td|caption|tr|th)( [^<>]{0,12})?>", " ", c)
```

Part 2 提到 TSR 會把表格轉成 HTML 保留結構。但**HTML 標籤不該進 embedding**：`<td>` 對語意沒有貢獻，卻會佔掉 token 額度、稀釋真實內容的訊號。

所以寫入 doc engine 的 `content_with_weight` 保留 HTML（給 LLM 看，結構有用），送去 embedding 的版本剝掉標籤（給向量模型看，標籤是雜訊）。**同一份內容，兩個消費者，兩種預處理。**

### 1.4 欄位名帶維度：`q_768_vec`

```python
d["q_%d_vec" % len(v)] = v
```

768 維就寫成 `q_768_vec`，1024 維就是 `q_1024_vec`。這不是隨手命名——它跟下一節的動態 mapping 是一組設計。先記住這個欄位名，第三節會揭曉。

---

## 二、批次、截斷與限流：三個保護機制

`embedding()` 裡有三層保護，都是被生產環境教出來的。

```
┌─────────────────────────────────────────────────────────────────┐
│  chunks（可能有 5000 個）                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
        ┌───────────────────────────────────────────┐
        │ ① 分批：EMBEDDING_BATCH_SIZE               │
        │    for i in range(0, len(cnts), BATCH):   │
        │    避免單次請求體過大 / provider 拒收      │
        └───────────────────┬───────────────────────┘
                            ▼
        ┌───────────────────────────────────────────┐
        │ ② 截斷：truncate(c, mdl.max_length - 10)  │
        │    留 10 token 餘裕，避免邊界 off-by-one   │
        │    （這是 Part 2「不做原子切分」的下游承接）│
        └───────────────────┬───────────────────────┘
                            ▼
        ┌───────────────────────────────────────────┐
        │ ③ 限流：async with embed_limiter          │
        │    + @timeout(60) 裝在 batch_encode 上    │
        │    避免打爆 provider rate limit / 卡死    │
        └───────────────────┬───────────────────────┘
                            ▼
        ┌───────────────────────────────────────────┐
        │ ④ 進度回寫：                              │
        │    prog = 0.7 + 0.2 × (i+1)/len(cnts)    │
        └───────────────────────────────────────────┘
```

幾個細節：

**`mdl.max_length - 10` 的那個 10。** 不同 provider 的 tokenizer 與 RAGFlow 本地的 `num_tokens_from_string()` 不會完全一致，留 10 token 餘裕比每次都撞 400 錯誤便宜得多。**這是一行沒有註解但意圖明確的防禦性程式碼。**

**進度公式寫死了 0.7 → 0.9。** 也就是 UI 上 70%～90% 這段必然是在做 embedding。這對排錯很有用：**卡在 72% 不動，就是 embedding provider 有問題，不是解析有問題。**

**`@timeout(60)` 在單一批次上。** 一批（通常 16～64 個 chunk）給 60 秒。超時就整個任務失敗重試。這裡的隱含假設是「embedding 應該很快」——如果你用的是自架的慢速模型，這個值需要調。

### 2.1 一個常見誤解：向量維度不是你選的

RAGFlow 的知識庫在建立時就綁定 embedding 模型（`list datasets` 的輸出裡有 `embedding_model` 欄位），而且**綁定之後不能換**。原因很簡單：索引裡已經有 768 維的 `q_768_vec`，你換成 1024 維的模型，新 chunk 會寫進 `q_1024_vec`，兩批向量根本不在同一個欄位，檢索時只會看到其中一半。

**要換模型 = 重建知識庫。** 這不是 RAGFlow 的限制，是所有向量檢索系統的共同物理約束。RAGFlow 只是把它顯式化了：欄位名裡就寫著維度，你一看就知道換模型代表什麼。

---

## 三、Save：欄位名稱本身就是 Schema

打開 `conf/mapping.json`，你會看到一個很反常的 ES mapping：**`properties` 只有一個欄位**（`lat_lon`），但 `dynamic_templates` 有 **19 條**。

```json
{
  "settings": {
    "index": { "number_of_shards": 2, "number_of_replicas": 0, "refresh_interval": "1000ms" },
    "similarity": { "scripted_sim": { ... } }
  },
  "mappings": {
    "dynamic_templates": [
      { "int":  { "match": "*_int",  "mapping": { "type": "integer", "store": "true" } } },
      { "tks":  { "match": "*_tks",  "mapping": { "type": "text", "similarity": "scripted_sim",
                                                   "analyzer": "whitespace", "store": true } } },
      ...
    ],
    "properties": { "lat_lon": { "type": "geo_point" } }
  }
}
```

**沒有任何 chunk 欄位是預先宣告的。** 欄位的型別完全由它的**名稱後綴**決定。

### 3.1 19 條動態模板全表

| 後綴 / 模式 | ES 型別 | 關鍵設定 | 實際欄位範例 |
|---|---|---|---|
| `*_int` | integer | store | `page_num_int`、`top_int`、`chunk_order_int` |
| `*_ulong` | unsigned_long | store | — |
| `*_long` | long | store | — |
| `*_short` | short | store | — |
| `*_flt` | float | store | `create_timestamp_flt`、`weight_flt` |
| `*_tks` | text | **similarity: scripted_sim**, analyzer: whitespace | `title_tks`、`important_tks`、`question_tks` |
| `*_ltks` | text | analyzer: whitespace | `content_ltks`、`content_sm_ltks` |
| `^(.*_(kwd\|id\|ids\|uid\|uids)\|uid\|id)$` | keyword | **similarity: boolean** | `docnm_kwd`、`important_kwd`、`doc_id`、`kb_id` |
| `^.*(_dt\|_time\|_at)$` | date | 三種格式 | — |
| `*_nst` | nested | — | — |
| `*_obj` | object（dynamic） | — | — |
| `^.*_(with_weight\|list)$` | text, **index: false** | 只存不索引 | `content_with_weight`、`n_hop_with_weight` |
| `*_fea` | **rank_feature** | — | `pagerank_fea` |
| `*_feas` | **rank_features** | — | `tag_feas` |
| `*_512_vec` | dense_vector(512), cosine | index: true | `q_512_vec` |
| `*_768_vec` | dense_vector(768), cosine | index: true | `q_768_vec` |
| `*_1024_vec` | dense_vector(1024), cosine | index: true | `q_1024_vec` |
| `*_1536_vec` | dense_vector(1536), cosine | index: true | `q_1536_vec` |
| `*_bin` | binary | — | — |

現在回頭看 Part 1 提過的那行：

```python
d["q_%d_vec" % len(v)] = v
```

**768 維向量自動命中 `*_768_vec` 模板，自動成為 768 維 cosine 向量欄位。零 schema 變更。** 這是整個設計最漂亮的地方：換 embedding 模型不需要改 mapping、不需要 migration、不需要重啟。

### 3.2 這個設計的代價

好處清楚，代價也清楚：

| 好處 | 代價 |
|---|---|
| 新增欄位零 schema 變更 | **欄位名打錯不會報錯**，只會靜默變成 ES 預設型別 |
| 換 embedding 模型不用 migration | 只支援 512/768/1024/1536 四種維度，**用 384 維模型（如 all-MiniLM）向量欄位不會被索引** |
| 一份 mapping 支撐所有文件型別 | 讀程式碼時要先知道命名規則才看得懂欄位含義 |
| 欄位語意自我文件化 | 重新命名欄位 = 破壞性變更 |

**那個 384 維的坑值得記住。** `bge-small`、`all-MiniLM-L6-v2` 這類輕量模型是 384 維，寫進去會是 `q_384_vec`，**沒有任何模板匹配它**，ES 會用預設行為處理（float 陣列，不建 KNN 索引）。結果是「寫入成功，向量檢索永遠回傳空」——一個非常難查的靜默失敗。實務上請用 512/768/1024/1536 維的模型。

### 3.3 Infinity 的對應：顯式 schema，相同命名

有趣的是，`conf/infinity_mapping.json` 用的是**完全顯式的 schema**（因為 Infinity 是強型別的），但**欄位名跟 ES 完全一致**：

```json
{
  "id":       {"type": "varchar", "default": ""},
  "doc_id":   {"type": "varchar", "default": ""},
  "kb_id":    {"type": "varchar", "default": "",
               "index_type": {"type": "secondary", "cardinality": "low"}},
  "content":  {"type": "varchar", "default": "", "analyzer": ["rag-coarse", "rag-fine"],
               "comment": "content_with_weight, content_ltks, content_sm_ltks"},
  "docnm":    {"type": "varchar", "default": "", "analyzer": ["rag-coarse", "rag-fine"],
               "comment": "docnm_kwd, title_tks, title_sm_tks"},
  "questions":{"type": "varchar", "default": "", "analyzer": ["rag-coarse", "rag-fine"],
               "comment": "question_kwd, question_tks"},
  "tag_feas": {"type": "varchar", "default": "", "analyzer": "rankfeatures"},
  "pagerank_fea": {"type": "integer", "default": 0},
  "available_int": {"type": "integer", "default": 1,
                    "index_type": {"type": "secondary", "cardinality": "low"}},
  ...
}
```

注意那些 `comment` 欄位：**Infinity 用一個欄位（`content`）加多個 analyzer（`rag-coarse` 粗分詞、`rag-fine` 細分詞），取代 ES 裡的三個欄位（`content_with_weight` + `content_ltks` + `content_sm_ltks`）。** 這是 Infinity 為 RAG 場景做的原生設計：一份原文，多種分詞，在引擎內部處理，不需要應用層存三份。

這也解釋了 `rag_tokenizer.py` 那段看起來很奇怪的程式碼：

```python
class RagTokenizer(infinity.rag_tokenizer.RagTokenizer):
    def tokenize(self, line: str) -> str:
        if settings.DOC_ENGINE_INFINITY:
            return line          # Infinity 自己分詞，應用層原樣傳
        else:
            return super().tokenize(line)   # ES 需要應用層預先分好詞
```

**用 ES 時，應用層負責分詞（因為 analyzer 是 `whitespace`，ES 不做中文分詞）；用 Infinity 時，引擎自己分詞。** 同一個介面，兩種責任劃分。

而且 RAGFlow 的分詞器本身就來自 Infinity 套件（`import infinity.rag_tokenizer`）——**這兩個專案是同一個團隊（InfiniFlow）的產品，分詞邏輯共用一份實作。**

### 3.4 Chunk 的完整欄位地圖

把 `infinity_mapping.json` 按用途分類，就是一張 chunk 的解剖圖：

```
┌─────────────────────────────────────────────────────────────────────┐
│  身分與歸屬                                                         │
│  id / doc_id / kb_id / mom_id（父 chunk）/ create_time              │
├─────────────────────────────────────────────────────────────────────┤
│  可檢索內容（多欄位 boost 的來源，Part 4 會用到）                    │
│  content（content_with_weight + content_ltks + content_sm_ltks）    │
│  docnm（docnm_kwd + title_tks + title_sm_tks）                      │
│  important_keywords（important_kwd + important_tks）  ← 人工介入 ^30 │
│  questions（question_kwd + question_tks）             ← 假問句   ^20 │
│  authors（authors_tks + authors_sm_tks）                            │
├─────────────────────────────────────────────────────────────────────┤
│  向量                                                               │
│  q_{512|768|1024|1536}_vec                                          │
├─────────────────────────────────────────────────────────────────────┤
│  排序特徵（加法項，不是乘法項）                                      │
│  pagerank_fea（文件級權重）/ tag_feas（標籤特徵，cosine × 10）       │
│  weight_int / weight_flt / rank_int / rank_flt                      │
├─────────────────────────────────────────────────────────────────────┤
│  版面定位（給 UI 高亮與 PDF 跳頁用）                                 │
│  page_num_int / top_int / position_int / img_id                     │
├─────────────────────────────────────────────────────────────────────┤
│  知識圖（GraphRAG 寫入，Part 4 會用到）                              │
│  knowledge_graph_kwd / entity_kwd / entity_type_kwd                 │
│  from_entity_kwd / to_entity_kwd / n_hop_with_weight / source_id    │
├─────────────────────────────────────────────────────────────────────┤
│  RAPTOR 摘要樹                                                      │
│  raptor_kwd / raptor_layer_int                                      │
├─────────────────────────────────────────────────────────────────────┤
│  結構與導航                                                          │
│  toc_kwd / children_kwd / parent_kwd / depth_int / doc_type_kwd     │
├─────────────────────────────────────────────────────────────────────┤
│  生命週期                                                            │
│  available_int（0 = 人工停用）/ removed_kwd / deleted_doc_id        │
│  chunk_hash_kwd / input_hash_kwd（冪等性，避免重複寫入）             │
└─────────────────────────────────────────────────────────────────────┘
```

**這張表就是 RAGFlow 所有功能的物理基礎。** 之後 Part 4 講的每一個檢索特性，都對應到這裡的某幾個欄位。

---

## 四、`scripted_sim`：把 TF 壓成 `min(freq, 1)` 的自訂相似度

`mapping.json` 的 `settings` 裡藏了整個索引設計最有主張的一段：

```json
"similarity": {
  "scripted_sim": {
    "type": "scripted",
    "script": {
      "source": "double idf = Math.log(1+(field.docCount-term.docFreq+0.5)/(term.docFreq + 0.5))
                              / Math.log(1+((field.docCount-0.5)/1.5));
                 return query.boost * idf * Math.min(doc.freq, 1);"
    }
  }
}
```

翻譯成人話：

```
score = query.boost × 正規化 IDF × min(詞頻, 1)
                                    └──────┬──────┘
                                    詞出現 1 次和 50 次，得分完全一樣
```

這是一個**刻意閹割 BM25 的相似度**。標準 BM25 的公式是：

```
BM25 = IDF × (tf × (k1+1)) / (tf + k1 × (1 - b + b × dl/avgdl))
              └────────────┬───────────┘   └────────┬────────┘
                    詞頻飽和曲線                文件長度正規化
```

RAGFlow 把 `tf` 直接壓成 0 或 1，**同時也就消掉了文件長度正規化**（因為長度正規化存在的意義就是修正 tf 的長度偏差）。

### 4.1 為什麼要這樣做

三個理由，都跟「chunk 不是文件」有關：

**理由一：chunk 太短，詞頻沒有訊息量。** 一個 128 token 的 chunk 裡，「毛利率」出現 1 次和 3 次，在語意上幾乎沒有差別——它就是在講毛利率。標準 BM25 的 tf 曲線是為「幾千字的網頁」設計的，套在 128 token 的片段上，放大的是噪音。

**理由二：避免關鍵字堆疊。** 表格類 chunk 特別容易出現同一個詞重複幾十次（例如每一列都有「營收」）。用標準 BM25，這種 chunk 會在任何含「營收」的查詢裡衝到第一，即使它只是一張欄位標題重複的表。**壓成 min(freq,1) 之後，「有沒有提到」比「提到幾次」重要。**

**理由三：讓分數可加。** 因為 tf 被壓成二元，`*_tks` 欄位的得分基本上退化成「命中詞的 IDF 加權和」。這讓多欄位 boost（`important_kwd^30`）的行為變得**可預測**——boost 30 就真的是 30 倍，不會被某個欄位裡異常的詞頻扭曲。這對 Part 4 的融合公式很關鍵。

### 4.2 這個決定的代價

| 好處 | 代價 |
|---|---|
| chunk 尺度下更穩定的排序 | 失去「這篇文章大量討論某主題」的訊號 |
| 對關鍵字堆疊有免疫力 | 長 chunk 與短 chunk 得分不再區分（無長度正規化） |
| 分數可加、boost 可預測 | 與標準 ES 行為不同，**你不能拿 BM25 的直覺來調參** |

**翻轉點**：如果你把 RAGFlow 拿來索引**長文件**（例如 `one` 模板，整份文件一個 chunk），這個相似度就不合適了——此時詞頻是真訊號。標準的做法是改用預設的 BM25 similarity，但這需要改 `mapping.json` 並重建索引。

還要注意：這個 similarity **只掛在 `*_tks` 欄位上**。`*_ltks`（如 `content_ltks`）用的是 ES 預設 BM25，而 `*_kwd` 用的是 `boolean`（命中就是 1，不命中就是 0）。**三種欄位，三種評分哲學：**

```
*_kwd  → boolean similarity     「有或沒有」          精確匹配欄位
*_tks  → scripted_sim（IDF-only）「有沒有，看詞多罕見」 標題/關鍵字/問句
*_ltks → 預設 BM25               「標準全文檢索」      正文
```

---

## 五、雙引擎抽象：一個介面，六種後端

RAGFlow 支援六種 doc engine。抽象層是 `DocStoreConnection`，各後端的實作在 `rag/utils/`：

| 檔案 | 後端 | 定位 |
|---|---|---|
| `es_conn.py` | Elasticsearch 8.11.3 | **預設**，生態成熟 |
| `infinity_conn.py` | Infinity v0.7.3 | 同團隊自研，RAG 原生 |
| `opensearch_conn.py` | OpenSearch 2.19.1 | ES 分支，含 hybrid pipeline |
| `ob_conn.py` | OceanBase 4.4 | 分散式 HTAP |
| `serenedb_conn.py` | SereneDB 26.07 | — |
| `gaussdb_conn.py` | GaussDB | 華為，含 text-to-SQL |

切換完全靠環境變數：

```bash
DOC_ENGINE=elasticsearch        # 或 infinity / opensearch / oceanbase / serenedb
COMPOSE_PROFILES=${DOC_ENGINE},${DEVICE},metadata-${METADATA_DB_PROFILE}
```

**同一份 compose 檔，profile 決定起哪些容器。** 換引擎不改 YAML。

### 5.1 索引命名與隔離策略

```python
def index_name(uid):
    return f"ragflow_{uid}"       # uid = tenant_id
```

```
┌────────────────────────────────────────────────────────────────┐
│  索引 ragflow_{tenant_A}                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ kb_id = kb_1  │ kb_id = kb_2  │ kb_id = kb_3  │  ...      │  │
│  │ （合約庫）     │ （產品手冊）   │ （FAQ）       │           │  │
│  └──────────────────────────────────────────────────────────┘  │
│  2 shards / 0 replicas / refresh_interval 1000ms               │
└────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────┐
│  索引 ragflow_{tenant_B}   ← 完全獨立的索引                     │
└────────────────────────────────────────────────────────────────┘
```

**租戶級隔離（索引），知識庫級過濾（欄位）。**

Infinity 的 schema 把這個意圖寫得更明白：`kb_id` 標記為 `{"type": "secondary", "cardinality": "low"}`——低基數的二級索引，正是「用來過濾、不是用來查找」的欄位。`available_int` 也是同樣的標記（0/1 兩種值）。

三個預設值的含義：

- **`number_of_shards: 2`** — 不是 1，因為單 shard 無法平行；不是 5，因為多數租戶的資料量不需要。這是「小租戶不浪費、中租戶夠用」的折衷。**超大租戶需要手動調。**
- **`number_of_replicas: 0`** — 預設**沒有副本**。這是單機部署的預設值，意思是**ES 節點掛了資料就沒了**。上生產必須改。
- **`refresh_interval: 1000ms`** — 比 ES 預設的 1s 一樣（1000ms = 1s），寫入後 1 秒內可搜。這是「使用者上傳完馬上想搜到」與「寫入吞吐」之間的取捨；批量匯入時可以調大到 30s 換吞吐。

### 5.2 額外的索引：metadata 與 skill

除了主 chunk 索引，`conf/` 裡還有幾份小 schema：

```
doc_meta_es_mapping.json / doc_meta_infinity_mapping.json
  → {id, kb_id, meta_fields: json}
  → 文件層級的 metadata store，支撐檢索時的 metadata 過濾

skill_es_mapping.json / skill_infinity_mapping.json
  → agent skill 的索引

message_infinity_mapping.json
  → 對話訊息（memory 功能用）
```

`meta_fields` 是一個 JSON 欄位，存使用者自訂的 metadata（`{"author": ["John","Tom"], "category": "tech"}`）。檢索時可以下條件過濾：

```
RETRIEVE 'AI' ON DATASETS 'test'
  WITH meta_data_filter '{"method":"manual",
                          "conditions":[{"key":"author","op":"eq","value":"Luo"}]}';
```

還有 `"method":"auto"` 模式——**讓 LLM 自己從問句推斷該套哪些 metadata 條件。** 這是 Part 4 的內容。

---

## 六、物件儲存：原始檔與圖片切片

向量與文字進 doc engine，二進位進物件儲存。`rag/utils/` 裡有一整排 driver：

```
minio_conn.py       MinIO（預設，compose 裡是 pgsty/silo 這個 S3 相容映像）
s3_conn.py          AWS S3
oss_conn.py         阿里雲 OSS
gcs_conn.py         Google Cloud Storage
azure_sas_conn.py   Azure（SAS token）
azure_spn_conn.py   Azure（Service Principal）
opendal_conn.py     OpenDAL（一個介面接數十種後端）
encrypted_storage.py 加密層（包在任一後端外面）
```

透過 `storage_factory.py` 選型，統一以 `settings.STORAGE_IMPL` 提供給上層。

存兩類東西：

**① 原始檔案。** 使用者上傳的 PDF/DOCX 原檔。用途是：重新解析（改了 chunk 參數要重跑）、UI 上的原文預覽與高亮定位。

**② 圖片切片。** DeepDoc 在解析 PDF 時會把圖片區塊、表格區塊切出來存成圖片。`image2id()` 負責這件事：

```python
async def image2id(d: dict, storage_put_func: partial, objname: str,
                   bucket: str = "imagetemps"):
```

chunk 上只留一個 `img_id` 欄位（指向物件儲存的 key），圖片本身不進 doc engine。**這個分離很重要**：把 base64 圖片塞進 ES 文件會讓索引體積爆炸、highlight 變慢、備份變貴。

```
┌──────────────┐        ┌─────────────────┐        ┌──────────────┐
│  Doc Engine  │        │  Object Storage │        │    MySQL     │
│              │        │                 │        │              │
│ chunk 文字    │        │ 原始 PDF        │        │ document 列  │
│ 向量          │──img_id▶│ 圖片切片        │        │ task 列      │
│ 排序特徵      │        │ (bucket per kb) │        │ 進度 / 狀態  │
│ img_id 參照   │        │                 │        │              │
└──────────────┘        └─────────────────┘        └──────────────┘
      可重建                   真實來源                  真實來源
```

**一個實用的心智模型：doc engine 裡的資料全部可以從物件儲存 + MySQL 重建。** 這就是為什麼 `number_of_replicas: 0` 的預設值不算太瘋狂——最壞情況是重新解析一次，不是資料永久遺失（前提是你確實備份了 MinIO 和 MySQL）。

---

## 七、三個演進階段：儲存層

### ╔══ Phase 1：ES 單節點（< 100 萬 chunk） ══╗

```
┌────────────────────────────────────────────┐
│ ES 單節點  MEM_LIMIT=8GB                    │
│  ragflow_{tenant}  2 shards / 0 replicas   │
└────────────────────────────────────────────┘
┌──────────┐  ┌───────────┐
│ MySQL 8  │  │ MinIO 單盤│
└──────────┘  └───────────┘
```

- 可接受的捷徑：0 replica、單盤 MinIO、`refresh_interval` 用預設
- 解決：功能完整可用
- 剩下：任一元件掉線即全掉；1000 萬 chunk 時單節點記憶體不足

### ╔══ Phase 2：ES 叢集 + 分離儲存（百萬～千萬） ══╗

```
┌─────────────────────────────────────────────────────────┐
│ ES 3 節點   replicas=1   每租戶索引獨立                  │
│ 批量匯入時 refresh_interval 調到 30s，完成後調回          │
└─────────────────────────────────────────────────────────┘
┌────────────────┐  ┌─────────────────┐  ┌──────────────┐
│ MySQL 主從     │  │ MinIO 分散式    │  │ Valkey 叢集  │
│ max_conn 900   │  │ 或直接用 S3     │  │              │
└────────────────┘  └─────────────────┘  └──────────────┘
```

- 新增元件：ES replica、MySQL 從庫、S3/分散式 MinIO
- 關鍵設定：`service_conf.yaml` 的 `mysql.max_connections: 900`、`stale_timeout: 300`
- 解決：單點故障、寫入吞吐
- 剩下：ES 的混合檢索融合只能做「近似」（Part 4 詳談的 `"0.001,1"` 權重與第二次 KNN 回查）

### ╔══ Phase 3：Infinity 或分散式 HTAP（千萬以上） ══╗

```
┌──────────────────────────────────────────────────────────────┐
│ Infinity：原生 weighted_sum 融合                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│   │ 全文（rag-   │  │ 向量          │  │ FusionExpr        │  │
│   │ coarse/fine）│  │              │  │ weighted_sum      │  │
│   └──────┬───────┘  └──────┬───────┘  │ weights "0.7,0.3" │  │
│          └─────────────────┴──────────▶└──────────────────┘  │
│   一次請求完成融合，不需要把向量傳回應用層                      │
└──────────────────────────────────────────────────────────────┘
    或 OceanBase / GaussDB（把 metadata 與 chunk 放同一套 HTAP）
```

- 新增元件：Infinity（或 HTAP 資料庫）、doc metadata store 分離
- 解決：融合精度（真正的加權融合，不是近似）、延遲、應用層不再搬向量
- 剩下：Infinity 生態新、除錯資料少；HTAP 方案的運維門檻高

### 三階段對照

| 維度 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| chunk 量級 | < 100 萬 | 100 萬～1000 萬 | 1000 萬+ |
| Doc engine | ES 單節點 | ES 3 節點 replica=1 | Infinity / OceanBase |
| replica | 0 | 1 | 依引擎 |
| 融合方式 | ES 近似 + 本地重排 | 同左 | 引擎原生加權融合 |
| 向量是否回傳應用層 | 否（第二次 KNN 取分數） | 否 | 否（引擎內完成） |
| 物件儲存 | MinIO 單盤 | MinIO 分散式 / S3 | S3 / OSS + 加密層 |
| 每 100 萬 chunk 索引體積 | ≈ 3～6 GB（768 維） | 同左 × replica | 依引擎壓縮策略 |

**索引體積的估算方式**：768 維 float32 = 3 KB/chunk，加上文字與倒排索引大約再 1～3 KB，所以 **100 萬 chunk ≈ 4～6 GB**。乘上 replica 數。這是規劃磁碟的基準線。

---

## 八、為什麼選 X 不選 Y

```
決定                    選 X 的理由                        不選 Y 的理由 / Y 更好的時機
──────────────────────────────────────────────────────────────────────────────────────
後綴驅動動態 mapping     換 embedding 模型零 schema 變更；   固定 mapping：型別安全、
vs 固定 mapping         新功能加欄位不用 migration；        欄位打錯會報錯，但每次加欄位
                       欄位名自我文件化                     都要 migration
                                                          ▶ 翻轉點：團隊需要強型別保證、
                                                            或維度不在 512/768/1024/1536

IDF-only（min(tf,1)）   chunk 太短，詞頻是噪音；            標準 BM25：長文件的正確選擇；
vs 標準 BM25            對關鍵字堆疊免疫；                  詞頻確實有訊息量
                       分數可加，多欄位 boost 可預測        ▶ 翻轉點：用 `one` 模板索引
                                                            長文件時，改回 BM25

0.1 檔名 + 0.9 內容     文件層級語意不遺失；                純內容向量：chunk 之間差異最大化，
vs 純內容向量           檔名只 encode 一次，成本可忽略       但檔名裡的關鍵資訊查不到
                                                          ▶ 翻轉點：檔名是無意義亂碼
                                                            （如 UUID）時設為 0

有問句就編碼問句        把非對稱匹配（問句 vs 陳述句）       一律編碼內容：穩定、不依賴生成品質
vs 一律編碼內容         轉成對稱匹配；FAQ 場景提升最大       ▶ 翻轉點：問句生成品質不穩時
                                                            關掉 question_proposal

租戶級索引 + kb_id 過濾  避免 shard 爆炸（500 個 KB          KB 級索引：隔離最強、刪除最快，
vs 知識庫級索引         = 1000 個 shard）；跨 KB 查詢便宜    但 shard 數失控
                                                          ▶ 翻轉點：單一 KB 資料量極大
                                                            （> 1 億 chunk）時該獨立索引

圖片存物件儲存 + img_id  索引體積不爆炸；highlight 不變慢；   base64 塞進文件：查詢時一次拿到，
vs 內嵌 base64          備份便宜                            但索引大 10 倍、備份與快照極慢
                                                          ▶ 翻轉點：幾乎沒有

replicas 預設 0         單機開發不浪費資源；資料可從         預設 1：開箱即高可用，
vs 預設 1               MinIO + MySQL 重建                  但 16 GB 單機跑不動
                                                          ▶ 翻轉點：上生產第一件事就是改成 1

六種 doc engine 抽象     不同客戶有不同基礎設施約束          只支援一種：程式碼簡單、
vs 只支援 ES            （國企要信創、雲廠要自家服務）；     優化到底，但市場被鎖死
                       profile 切換零改檔                   ▶ 翻轉點：自用系統只需要一種
```

---

## 九、系統效應：儲存層設計帶來什麼

| 能力 | 靠哪個設計實現 | 沒有它會怎樣 |
|---|---|---|
| 換 embedding 模型不改程式 | 後綴驅動 mapping + `q_{dim}_vec` | 每次換模型要改 mapping + migration |
| 換 doc engine 不改程式 | `DocStoreConnection` 抽象 + profile | 綁死一家，客戶談不下來 |
| 人工加關鍵字有 30 倍效果 | `*_kwd` = boolean similarity + `^30` boost | 人工修正被詞頻噪音淹沒 |
| 表格類 chunk 不會霸榜 | `min(doc.freq, 1)` | 欄位標題重複的表格衝到第一 |
| 標籤先驗可注入排序 | `tag_feas` = rank_features + cosine × 10 | 只能靠微調 embedding 模型 |
| 文件級權重可調 | `pagerank_fea` = rank_feature | 所有文件一律平等 |
| UI 能在 PDF 上高亮定位 | `page_num_int` / `top_int` / `position_int` | 引用只能給文字，不能跳頁 |
| 索引可從備份重建 | 原檔在物件儲存、狀態在 MySQL | doc engine 掉了就永久遺失 |
| 人工停用雜訊 chunk | `available_int` + low-cardinality 二級索引 | 只能刪除，無法可逆停用 |
| metadata 條件過濾 | 獨立的 `doc_meta_*` 索引 | 過濾條件要跟 chunk 一起重建 |

---

## 十、系列導航

資料現在躺在索引裡了：文字、向量、排序特徵、版面座標、知識圖節點，全部按名稱後綴各就各位。

下一篇是把它們取回來——也是整個系列技術密度最高的一篇：查詢編譯器如何把一句人話變成加權布林查詢、ES 與 Infinity 兩種融合路徑為什麼不一樣、三層重排的公式、GraphRAG 與 RAPTOR 什麼時候值得開、以及那個不依賴 LLM 服從度的引用對齊演算法。

- **Part 4 — Decode 與檢索**：混合搜尋、Rerank、GraphRAG / RAPTOR 與引用

← [Part 2 — 資料進場 — DeepDoc 解析、Chunking 策略與 14 種模板](../ragflow-intro-part2-deepdoc-chunking-zh) | [Part 4 — Decode 與檢索 — 混合搜尋、Rerank、GraphRAG/RAPTOR 與引用 →](../ragflow-intro-part4-retrieval-rerank-zh)

---

*本文基於 RAGFlow `main` 分支（2026 年 9 月）原始碼撰寫。所有 mapping、相似度腳本、欄位命名與預設值皆從 `conf/mapping.json`、`conf/infinity_mapping.json` 與 `rag/svr/task_executor.py` 實際核對。索引體積為量級估算。*
