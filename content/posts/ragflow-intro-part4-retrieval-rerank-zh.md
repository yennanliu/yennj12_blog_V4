---
title: "RAGFlow Intro Part 4 — Decode 與檢索 — 混合搜尋、Rerank、GraphRAG/RAPTOR 與引用"
date: 2026-09-10T12:00:00+08:00
draft: false
weight: 4
description: "RAGFlow 原始碼導讀系列第四篇：逐行拆解查詢編譯器如何把一句人話變成加權布林查詢、ES 與 Infinity 兩條融合路徑的差異、三層重排的權重公式、GraphRAG 與 RAPTOR 的成本與時機，以及不依賴 LLM 服從度的引用對齊演算法。"
categories: ["all", "ai", "engineering"]
tags: ["RAGFlow", "RAG", "AI", "Hybrid Search", "Reranking", "GraphRAG", "RAPTOR", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
---

> *大多數人談 RAG 的檢索，是「向量搜尋 top-5，然後塞進 prompt」。*
> *真正的答案是：檢索是一條有六個階段的管線——問句改寫、查詢編譯、雙路召回、融合、重排、上下文擴展——而每個階段都有自己的失敗模式和自己的權重。*
> *向量相似度只是其中一個訊號，而且通常不是最重要的那個。*
> *這篇文章把 RAGFlow 的每一個權重、每一個閾值、每一個退避策略都攤開來。*

---

## 前言

[Part 3](../ragflow-intro-part3-embedding-indexing-zh) 把資料放進了索引。本篇是反向操作：**一句人話進來，一組帶引用的答案出去。**

主戰場是兩個檔案：

```
rag/nlp/query.py    （9.5 KB）  查詢編譯器：人話 → 加權布林查詢
rag/nlp/search.py   （45 KB）   召回、融合、重排、引用對齊
```

加上兩個進階模組：

```
rag/graphrag/       GraphRAG（general / light / ner 三種抽取策略 + 社群報告）
rag/svr/task_executor_refactor/raptor_service.py    RAPTOR 摘要樹
```

以及生成端：

```
api/db/services/dialog_service.py   對話編排（2200+ 行）
rag/prompts/generator.py            prompt 組裝與 token 預算
```

完整管線長這樣：

```
問句
 │
 ├─① 問句改寫（3 種，都是 LLM 呼叫，都可關）
 │
 ├─② 查詢編譯（純規則，零 LLM）
 │
 ├─③ 雙路召回（一次請求）─────────┐
 │                                │
 ├─④ 融合（引擎相關）              │  這三步在
 │                                │  doc engine
 ├─⑤ 本地重排（應用層）           │  和應用層
 │                                │  之間反覆
 ├─⑥ Cross-encoder rerank（可選）─┘
 │
 ├─⑦ 上下文擴展（TOC / children / 表格圖片上下文）
 │
 ├─⑧ 進階召回（GraphRAG / RAPTOR / web search）
 │
 ├─⑨ Prompt 組裝（token 預算）
 │
 └─⑩ 生成 + 事後引用對齊
```

---

## 一、問句改寫：三個可選的 LLM 前置步驟

`dialog_service.py` 的 `async_chat()` 裡，檢索之前有三個開關：

```python
if len(questions) > 1 and prompt_config.get("refine_multiturn"):
    questions = [await full_question(dialog.tenant_id, dialog.llm_id, messages)]

if prompt_config.get("cross_languages"):
    questions = [await cross_languages(dialog.tenant_id, dialog.llm_id,
                                       questions[0], prompt_config["cross_languages"])]

if prompt_config.get("keyword", False):
    questions[-1] += await keyword_extraction(chat_mdl, questions[-1])
```

| 開關 | 做什麼 | 解決的問題 | 代價 |
|---|---|---|---|
| `refine_multiturn` | 把多輪對話壓成一個獨立問句 | 「那它去年呢？」這種指代查不到東西 | +1 次 LLM 呼叫（約 0.3～1s） |
| `cross_languages` | 把問句翻譯/擴寫成指定語言 | 中文問句查英文文件 | +1 次 LLM 呼叫 |
| `keyword` | LLM 抽關鍵字附加到問句後 | 口語化長問句的關鍵訊號被稀釋 | +1 次 LLM 呼叫 |

**這三個是延遲殺手。** 全開就是 3 次序列 LLM 呼叫，首字延遲直接加 1～3 秒。實務建議：

- **`refine_multiturn` 幾乎必開**——多輪對話是主要使用場景，指代解析沒有替代方案
- **`cross_languages` 只在真的跨語言時開**——它翻譯的是問句，不是文件，效果依 embedding 模型的多語言能力而定
- **`keyword` 通常不必開**——下一節的查詢編譯器已經在做 term weighting 了，這一步的邊際效益低

程式碼裡有一段計時，直接把這件事量化出來：

```python
refine_question_time_cost = (refine_question_ts - bind_models_ts) * 1000
retrieval_time_cost = (retrieval_ts - refine_question_ts) * 1000
...
f"  - Query refinement(LLM): {refine_question_time_cost:.1f}ms\n"
```

**RAGFlow 自己就把「問句改寫」和「檢索」的耗時分開記錄**——這是設計者知道這一步很貴的證據。

---

## 二、查詢編譯：把一句人話變成加權布林查詢

這是 RAGFlow 最被低估的一段程式碼。`FulltextQueryer.question()` 沒有任何 LLM 呼叫，純規則，但輸出的查詢複雜度遠超一般實作。

### 2.1 欄位 boost 表

```python
self.query_fields = [
    "title_tks^10",
    "title_sm_tks^5",
    "important_kwd^30",
    "important_tks^20",
    "question_tks^20",
    "content_ltks^2",
    "content_sm_ltks",       # ^1
]
```

視覺化一下權重階梯：

```
important_kwd    ████████████████████████████████  ^30   人工/LLM 標的關鍵字
important_tks    ████████████████████            ^20   關鍵字的分詞版
question_tks     ████████████████████            ^20   假問句
title_tks        ██████████                      ^10   檔名/標題
title_sm_tks     █████                           ^5    標題細分詞
content_ltks     ██                              ^2    正文
content_sm_ltks  █                               ^1    正文細分詞
```

**正文的權重是最低的。** 這與直覺相反，但邏輯很清楚：正文長、詞多、噪音多；`important_kwd` 短、精準、通常是人挑的。**在 RAGFlow 的世界觀裡，「有人告訴我這個 chunk 講什麼」比「這個 chunk 裡出現過這個詞」重要 15 倍。**

`_sm_` 後綴是「細分詞（small / fine-grained）」版本。中文分詞有粗細之分：「知識圖譜」粗分是一個詞，細分是「知識」+「圖譜」。粗分保精確、細分保召回，兩個都索引、都查、粗分權重高一倍。

### 2.2 中英文兩條不同的編譯路徑

```python
if not self.is_chinese(txt):
    # 英文路徑
else:
    # 中文路徑
```

**英文路徑**（較簡單）：

```
"how to configure retrieval weight"
      │
      ├─ rmWWW()：移除 how/to/what 這類疑問詞與停用詞
      ├─ tokenize → ["configure", "retrieval", "weight"]
      ├─ term weighting → [("configure", 0.8), ("retrieval", 1.2), ("weight", 0.9)]
      ├─ 同義詞查詢（WordNet）→ 每個詞的同義詞，權重 w/4
      └─ 相鄰 bigram 短語 → "retrieval weight"^(max(1.2,0.9)×2)
      │
      ▼
(configure^0.8000 "configuration"^0.2000) (retrieval^1.2000 ...) ...
"configure retrieval"^2.4000 "retrieval weight"^2.4000
```

**中文路徑**（複雜得多）：

```
"檢索權重要怎麼設定"
      │
      ├─ 繁簡轉換 + 全角轉半角 + 小寫化
      ├─ rmWWW()：移除「怎麼」「要」這類詞
      ├─ term weighting split → ["檢索權重", "設定"]
      │
      └─ 對每個 term：
           ├─ 粗分詞 + 權重
           ├─ need_fine_grained_tokenize()？（長度 >= 3 且非純英數）
           │     → 細分詞 ["檢索", "權重"]
           │     → 加上 `OR "檢索 權重" OR ("檢索 權重"~2)^0.5`   （proximity 查詢）
           ├─ 同義詞 → `(term OR (syn1 syn2)^0.2)`
           └─ 多 term 時加整體短語 → `("檢索權重"~2)^1.5`
      │
      ▼
((檢索權重)^1.2 OR "檢索 權重" OR ("檢索 權重"~2)^0.5)^5 OR (同義詞)^0.7 ...
minimum_should_match: 0.6
```

`~2` 是 proximity（詞距 2 以內），`^0.5` 是它的權重折扣。**細分詞的 proximity 查詢是中文檢索的關鍵補償**：使用者打「檢索權重」，文件裡寫「檢索的權重」，粗分詞匹配不到，但 `"檢索 權重"~2` 可以。

### 2.3 幾個寫在程式碼裡的細節

**關鍵字上限 32、term 上限 256。**

```python
for tt in self.tw.split(txt)[:256]:      # 最多處理 256 個 term
    ...
    if len(keywords) < 32:               # keywords 最多 32 個
        keywords.append(...)
```

為什麼要設限？因為使用者可能貼一整段 500 字進來當「問句」。不設限的話，展開同義詞與 bigram 之後會產生數千個子句，ES 查詢直接超時。**32 是一個「足夠表達一個問題，不足以拖垮引擎」的經驗值。**

**`minimum_should_match: 0.6`。** 布林查詢預設要命中 60% 的子句才算匹配。這是精確度優先的設定。

**特殊字元的雙重清理。** 有兩處註解解釋為什麼：

```python
# Infinity's search_lexer.l defines ESCAPABLE characters [\x20()^"'~*?:\\]
txt = re.sub(r"[ :|\r\n\t,，。？?/`!！&^%%()\[\]{}<>*~'\"\\]+", " ", ...)

# Strip single quotes from synonym terms to avoid Infinity lexer TokenError
# (e.g. WordNet returns "cat-o'-nine-tails" for "cat")
syn = [rag_tokenizer.tokenize(s).replace("'", "") for s in self.syn.lookup(tk)]
```

第二個註解特別有喜感：**WordNet 查「cat」的同義詞會回傳「cat-o'-nine-tails」（九尾鞭），那個撇號會讓 Infinity 的 lexer 爆掉。** 這種 bug 只有在生產環境跑過才會遇到。

---

## 三、雙路召回與融合：兩條完全不同的路徑

編譯好的查詢送進 doc engine。這裡 ES 和 Infinity 的行為**根本不同**，值得並排看。

### 3.1 Infinity 路徑：引擎原生融合

```python
if settings.DOC_ENGINE_INFINITY:
    vector_similarity_weight = float(req.get("vector_similarity_weight", 0.3))
    fusionExpr = build_fusion_expr(knn_top_k, vector_similarity_weight)

def build_fusion_expr(topn, vector_similarity_weight=0.3):
    term_similarity_weight = 1 - vector_similarity_weight
    return FusionExpr("weighted_sum", topn,
                      {"weights": f"{term_similarity_weight:g},{vector_similarity_weight:g}"})
```

```
     編譯後的布林查詢 ────┐
                         ├──▶ Infinity ──▶ weighted_sum(0.7, 0.3) ──▶ 已融合的結果
     查詢向量 ────────────┘         引擎內部完成，一次請求
```

**權重就是使用者設定的權重。** `vector_similarity_weight=0.3` 意思就是「文字路 70%、向量路 30%」，引擎照做。乾淨、可預測。

### 3.2 ES 路徑：一個看起來很奇怪的權重

```python
else:   # Elasticsearch
    fusionExpr = FusionExpr("weighted_sum", knn_top_k, {"weights": "0.001,1"})
```

**`0.001, 1`。** 文字路的權重是 0.001，幾乎為零。這看起來像 bug，但不是。

原因是 ES 的 BM25 分數與 KNN 分數**不在同一個尺度上**，而且 ES 沒有提供 RAGFlow 需要的加權融合原語。所以 RAGFlow 的策略是：

```
┌──────────────────────────────────────────────────────────────────────┐
│ 第一次請求（召回）：                                                  │
│   文字查詢（決定候選集合）+ KNN（決定候選集合）                       │
│   權重 "0.001,1" → 實質上讓 KNN 主導排序，文字查詢主要用來「加入候選」 │
│   → 拿到 candidate ids + 各種欄位                                    │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 第二次請求（_knn_scores，KNN-only）：                                │
│   只對上一步的候選 id 做純 KNN                                        │
│   → 拿到「乾淨的 cosine 相似度」，不被 BM25 分數污染                  │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 應用層融合（rerank_with_knn）：                                       │
│   sim = tkweight × 本地算的 token 相似度                              │
│       + vtweight × 第二次拿到的 cosine                                │
│       + rank_feature                                                  │
│   → 這裡才是「真正的」加權融合                                        │
└──────────────────────────────────────────────────────────────────────┘
```

程式碼裡的註解把這個設計說得很清楚：

> ES path no longer fetches chunk vectors here. The clean cosine score is recovered later via a second KNN-only call in `retrieval()`; chunk vectors are fetched on demand for citations.

**這是一個重要的演進**：舊版做法是把候選 chunk 的向量整個傳回應用層，然後在 Python 裡算 cosine。那意味著 64 個候選 × 768 維 × 4 byte = 196 KB 的網路傳輸，每次查詢。改成第二次 KNN-only 請求之後，**ES 算 cosine（它本來就會），應用層只拿回一個浮點數**。

而 OceanBase / SereneDB 還在用舊路徑：

```python
if settings.DOC_ENGINE_OCEANBASE or settings.DOC_ENGINE_SERENEDB:
    src.append(f"q_{len(q_vec)}_vec")     # 還是要把向量搬回來
```

**這就是「六種 doc engine 抽象」的真實成本**：抽象存在，但每個後端的最優路徑不同，程式碼裡必然有 `if engine == X` 的分支。

### 3.3 KNN 參數：1024 / 2048

```python
knn_top_k = int(req.get("knn_top_k", 1024))
knn_num_candidates = int(req.get("knn_num_candidates", 2048))
```

要回 top-10 的結果，KNN 卻取 1024 個候選、掃 2048 個。**為什麼要這麼多？**

因為 KNN 的結果會被後面的過濾與重排大幅削減：

```
KNN 1024 個候選
   │
   ├─ filters（kb_id、doc_id、available_int、metadata 條件）→ 可能刷掉 90%
   ├─ _prune_deleted_chunks（比對 MySQL，刷掉已刪文件的殘留 chunk）
   ├─ 本地重排 + similarity_threshold（預設 0.2）→ 再刷一批
   └─ rerank_candidates_count（64）→ 進 cross-encoder
   │
   ▼
最終 top-10
```

**如果 KNN 只取 20 個，套上 kb_id 過濾之後可能只剩 2 個。** 過濾後召回不足是向量檢索最常見的失敗模式，1024 是為此買的保險。代價是 ES 的 KNN 計算量變大（`num_candidates=2048` 是 HNSW 的搜索寬度）。

### 3.4 空結果退避：一個很務實的設計

```python
if total == 0:
    if filters.get("doc_id"):
        # 指定文件的查詢：直接不帶查詢條件撈該文件的 chunk
        res = search(src, [], filters, [], ...)
    else:
        # 放寬條件重試
        matchText, _ = self.qryr.question(qst, min_match=0.1)   # 0.3 → 0.1
        matchDense.extra_options["similarity"] = 0.17            # 0.1 → 0.17
        res = search(...)
```

第一次查詢用 `min_match=0.3`（要命中 30% 的查詢子句）。**如果一個結果都沒有，就降到 0.1 重試一次。**

有趣的是向量的相似度門檻是**升高**的（0.1 → 0.17）。這看起來矛盾，但合理：既然文字條件已經放到很寬，就得靠向量門檻擋住完全不相關的東西，否則放寬之後回來的是一堆噪音。

**這種「先嚴後寬」的兩段式查詢，是搜尋系統的標準做法**，但很多 RAG 實作沒有——它們的失敗模式是「查不到就回答不知道」，而使用者明明知道文件裡有。

---

## 四、三層重排：公式全解

召回之後，RAGFlow 有三種重排路徑。全部都是同一個公式的變體：

```
sim = tkweight × token相似度 + vtweight × 向量相似度 + rank_feature
      └───┬───┘                 └───┬───┘              └────┬────┘
       預設 0.3                  預設 0.7            加法項，不是乘法項
```

三種路徑的差別只在「向量相似度」從哪來：

| 方法 | 向量相似度來源 | 用於 |
|---|---|---|
| `rerank()` | 應用層自己算 cosine（需要 chunk 向量） | OceanBase / SereneDB |
| `rerank_with_knn()` | 第二次 KNN 請求回傳的分數 | **ES 主路徑** |
| `rerank_by_model()` | Cross-encoder 模型打分 | 開了 rerank 模型時 |

### 4.1 Token 相似度：不是 BM25，是加權集合重疊

`token_similarity()` 的實作很特別：

```python
def to_dict(tks):
    d = defaultdict(int)
    wts = self.tw.weights(tks, preprocess=False)
    for i, (t, c) in enumerate(wts):
        d[t] += c * 0.4                              # unigram 權重 0.4
        if i + 1 < len(wts):
            _t, _c = wts[i + 1]
            d[t + _t] += max(c, _c) * 0.6            # bigram 權重 0.6
    return d
```

**bigram 的權重（0.6）比 unigram（0.4）高。** 也就是說，「檢索」+「權重」兩個詞分別命中，得分低於「檢索權重」這個組合命中。

這是對「詞序」的補償。向量模型天生對詞序不敏感（bag-of-embeddings 的傾向），BM25 也完全忽略詞序。**用 bigram 加權補上這個維度，是一個成本極低的精度提升**——不需要模型，只需要一次字串拼接。

### 4.2 Chunk 側的 token 加倍：又一次人工介入放大

```python
tks = content_ltks + title_tks * 2 + important_kwd * 5 + question_tks * 6
```

**這行是把 list 重複 N 次**（Python 的 `list * n`），也就是同一個 token 在集合裡出現多次，權重就是 N 倍：

```
question_tks     ██████  ×6    假問句
important_kwd    █████   ×5    人工/LLM 關鍵字
title_tks        ██      ×2    標題
content_ltks     █       ×1    正文
```

配上第二節的欄位 boost（`important_kwd^30`），**人工加的一個關鍵字在整條管線上被放大了兩次**：召回階段 30 倍，重排階段 5 倍。這就是 Part 2 說「20 個 chunk 手動加關鍵字勝過換 embedding 模型」的量化依據。

注意 `rerank_by_model()` 裡刻意**不**加倍：

```python
# Unlike rerank()/rerank_with_knn(), the fields are not repeated here:
# these tokens are joined back into `docs` for a cross-encoder, where
# duplicating a field would distort the model's own scoring.
tks = content_ltks + title_tks + important_kwd + question_tks
```

因為 cross-encoder 讀的是自然語言文本，把同一個詞重複 6 次會讓模型看到一段病態文字。**同一個資料結構，餵給不同消費者要有不同的預處理**——這跟 Part 3 的「HTML 標籤進 LLM 不進 embedding」是同一個原則。

### 4.3 `rank_feature`：加法項的兩個來源

```python
def _rank_feature_scores(self, query_rfea, search_res):
    pageranks = np.array([field[id].get(PAGERANK_FLD, 0) for id in ids])
    return self._tag_feature_scores(query_rfea, search_res) + pageranks
```

**① PageRank（`pagerank_fea`）** — 文件級權重，直接相加。預設值在 `retrieval()` 的簽名裡：

```python
rank_feature: dict | None = {PAGERANK_FLD: 10}
```

**② 標籤特徵（`tag_feas`）** — 查詢的標籤分布與 chunk 的標籤分布做 cosine，**乘以 10**：

```python
return np.array(rank_fea, dtype=float) * 10.0
```

為什麼是加法而不是乘法？因為**加法讓特徵成為「保底分」而不是「放大器」**。一個 PageRank 很高但完全不相關的 chunk，加 10 分不會讓它衝到第一（因為相關 chunk 的 sim 本身可以到 0.8+ 再加上自己的特徵分）；但如果是乘法，一個 10 倍的乘數會讓不相關的東西直接霸榜。

**這個選擇的代價是尺度耦合**：`tkweight × tksim + vtweight × vtsim` 的範圍大致在 0～1，而 rank_feature 可以是 10、20。**PageRank 設太大會壓過相關性訊號。** 這是調參時最容易搞砸的地方——它的合理範圍是個位數，不是幾百。

### 4.4 Cross-encoder rerank 與分頁的衝突

`retrieval()` 的 docstring 花了一整段解釋一件事：**開了 rerank 就不該分頁。**

```python
page,       # MUST be 1 when rerank_mdl is specified
page_size,  # it is topn when rerank_mdl is specified
rerank_candidates_count=64,
```

```python
if page * page_size > rerank_candidates_count:
    raise Exception(f"rerank_candidates_count({rerank_candidates_count}) must be "
                    f"greater than page * page_size({page * page_size})")
```

理由是：

> When requesting page 2, the system must still process all candidates needed for page 1, resulting in a significant waste of time and computational resources. Moreover, when `rerank_candidates_count` expands into the next retrieval window, new records are added to the candidate set and the entire set is reranked. That meant the previous returned pages might not be the same as the current returned pages, which is not acceptable for pagination.

**兩個問題：浪費，以及不穩定。** 第 2 頁必須重算第 1 頁的所有候選（浪費），而且候選集合擴大之後整個重排，第 1 頁的內容會變（不穩定）。

RAGFlow 的解法是**直接把它變成錯誤**，而不是靜默地給出錯誤結果。這是我很欣賞的一種 API 設計態度：**當一個組合在語意上是壞的，就不要讓它能被表達。**

---

## 五、進階召回：五個可選機制

基本管線之上，RAGFlow 有五個進階召回機制。它們的共通點是：**都很貴，都預設關閉，都在特定問題上有質變效果。**

### 5.1 GraphRAG：回答「全局性」問題

```
文件 chunks
    │
    ▼ ① 實體與關係抽取（每個 chunk 一次 LLM 呼叫）
┌─────────────────────────────────────────────────────────┐
│  三種抽取策略（rag/graphrag/）                            │
│  · general/  完整版：實體 + 關係 + 描述（貴，品質高）      │
│  · light/    輕量版：LightRAG 風格（快，較省）            │
│  · ner/      NER 版：命名實體識別 + 依存關係（最省）      │
└─────────────────────────────┬───────────────────────────┘
                              ▼ ② 實體消解（entity_resolution.py）
                    「台積電」「TSMC」「台灣積體電路」→ 同一個節點
                              ▼ ③ 社群偵測（leiden.py）
                    Leiden 演算法把圖切成社群
                              ▼ ④ 社群報告（community_reports_extractor.py）
                    每個社群生成一份摘要（又是 LLM 呼叫）
                              ▼
        寫回索引：entity_kwd / from_entity_kwd / to_entity_kwd /
                  entity_type_kwd / n_hop_with_weight / knowledge_graph_kwd
```

檢索時走 `KGSearch`（`rag/graphrag/search.py`）：

```python
async def query_rewrite(self, llm, question, idxnms, kb_ids):   # LLM 改寫成圖查詢
async def get_relevant_ents_by_keywords(...)      # 關鍵字 → 實體（sim_thr=0.3）
async def get_relevant_relations_by_txt(...)      # 文字 → 關係
def _community_retrieval_(self, entities, ...)    # 實體 → 所屬社群報告
```

**GraphRAG 解決什麼問題？** 「這批合約裡有哪些共同的風險條款？」——這種問題的答案不在任何單一 chunk 裡，它需要跨文件聚合。向量檢索對此無能為力（沒有一個 chunk 跟這個問題相似）。

**代價**：抽取階段是 `chunk 數 × 1～3 次 LLM 呼叫`，加上社群報告。200 萬 chunk 開 GraphRAG，是 200～600 萬次呼叫，外加實體消解的呼叫。**這是 ingestion 成本的 10～50 倍。**

實務建議：**GraphRAG 只用在「小而貴」的知識庫上。** 100 份核心合約、500 份 SOP，值得；5 萬份雜文件，不值得。而且優先試 `light` 或 `ner` 策略。

### 5.2 RAPTOR：摘要樹

```
        ┌──────────────────────────────────────────┐
        │ Layer 2   [整份文件的摘要]                │  raptor_layer_int = 2
        └──────────────┬───────────────────────────┘
              ┌────────┴────────┐
        ┌─────▼─────┐     ┌─────▼─────┐
        │ Layer 1   │     │ Layer 1   │              raptor_layer_int = 1
        │ 群組摘要  │     │ 群組摘要  │
        └─────┬─────┘     └─────┬─────┘
         ┌────┴────┐        ┌───┴────┐
      ┌──▼──┐ ┌──▼──┐   ┌──▼──┐ ┌──▼──┐
      │chunk│ │chunk│   │chunk│ │chunk│              原始 chunk（layer 0）
      └─────┘ └─────┘   └─────┘ └─────┘
```

作法是：把 chunk 的向量做分群 → 每群餵給 LLM 生成摘要 → 摘要再向量化 → 遞迴往上，直到收斂。**摘要本身也是可檢索的 chunk**（`raptor_kwd` 標記），所以一個「這份文件在講什麼」的問題可以直接命中 Layer 2 的摘要，而不是命中某一段細節。

`raptor_service.py` 的設定參數：

```python
raptor_config.get("max_cluster", 64)                        # 每層最多幾群
raptor_config["max_token"]                                  # 摘要長度上限
raptor_config.get("clustering_threshold", 0.3)              # 分群閾值
raptor_config["random_seed"]                                # 可重現性
```

而且有兩種粒度：

| 模式 | 方法 | 適用 |
|---|---|---|
| `_run_file_level_raptor()` | 每份文件各自建樹 | 文件之間主題獨立 |
| `_run_dataset_level_raptor()` | 整個知識庫一起建樹 | 需要跨文件的主題摘要 |

**一個貼心的設計：自動跳過不該做 RAPTOR 的檔案。**

```python
def should_skip_raptor(file_type=None, parser_id="", parser_config=None, raptor_config=None)
def is_structured_file_type(file_type)      # Excel/CSV 這類
def is_tabular_pdf(parser_id, parser_config) # 表格型 PDF
def get_skip_reason(...)                     # 而且會告訴你為什麼跳過
```

**對一張 Excel 的每一列做摘要是沒有意義的**——列與列之間沒有敘事關係，摘要出來是垃圾。RAGFlow 主動偵測並跳過，還會回報原因。這種「知道自己的功能不適用於什麼」的實作，比功能本身更能反映成熟度。

### 5.3 TOC 增強

```python
if prompt_config.get("toc_enhance"):
    cks = await retriever.retrieval_by_toc(" ".join(questions),
                                           kbinfos["chunks"], tenant_ids,
                                           chat_mdl, dialog.top_n)
```

用文件的目錄結構（ingestion 時由 `build_TOC()` 抽出，存在 `toc_kwd`）輔助定位。**適用於厚重的結構化文件**：一份 500 頁的規範，問「第 7 章講什麼」，靠目錄比靠向量準。

代價是又一次 LLM 呼叫（要用 `chat_mdl` 判斷該取哪些章節）。

### 5.4 父子 chunk 與上下文擴展

```python
def retrieval_by_children(self, chunks, tenant_ids):
```

配合 Part 2 的 `hierarchy_chunker` 與 `mom_id` / `children_kwd` / `parent_kwd` 欄位：**用小 chunk 命中，回傳大 chunk。**

這解決了 Part 2 提到的「128 token 太小」問題：檢索精度需要小 chunk（訊號集中），生成品質需要大上下文（資訊完整）。**父子結構讓兩者可以兼得。**

同類機制還有 `table_context_size` 與 `image_context_size`（Part 2 提過）——表格或圖片 chunk 回傳時，附帶前後 N 個 chunk 當上下文。

### 5.5 Metadata 過濾與 Web 搜尋

Metadata 過濾有兩種模式：

```
WITH meta_data_filter '{"method":"manual",
                        "conditions":[{"key":"author","op":"eq","value":"Luo"}]}'
WITH meta_data_filter '{"method":"auto"}'      ← LLM 自己從問句推斷條件
```

`auto` 模式很有意思：**使用者問「去年張三寫的報告怎麼說」，LLM 推斷出 `{author: "張三", year: 2025}` 兩個過濾條件。** 這把自然語言查詢的一部分下推到結構化過濾，而不是全靠語意相似度。

Web 搜尋則是把外部結果併進候選集：`rag/utils/` 裡有 `tavily_conn.py`、`serply_conn.py`、`youcom_conn.py`、`web_search_conn.py`。

---

## 六、三個演進階段：檢索策略

### ╔══ Phase 1：純向量 top-k（POC） ══╗

```
問句 ──embedding──▶ KNN top-10 ──▶ prompt ──▶ LLM
```

- 設定：`vector_similarity_weight=1.0`（或關掉關鍵字路）、不開 rerank、不開問句改寫
- 延遲：embedding 50ms + KNN 30ms + LLM ≈ 1.5～3s
- 解決：能跑、能答
- 剩下：專有名詞查不到（「RTX-4090D」召回「RTX-4080」）；多輪對話的指代失效

### ╔══ Phase 2：混合檢索 + 重排（MVP） ══╗

```
問句
  │
  ├─ refine_multiturn（+0.5s）
  │
  ├─ 查詢編譯（+5ms，純規則）
  │
  ├─ 雙路召回 knn_top_k=1024（+50ms）
  │
  ├─ 本地重排 0.3/0.7 + rank_feature（+20ms）
  │
  ├─ Cross-encoder rerank top-64（+150～400ms）
  │
  └─ prompt + LLM
```

- 新增元件 vs Phase 1：`refine_multiturn`、混合檢索（`vector_similarity_weight=0.3`）、rerank 模型、`similarity_threshold=0.2`
- 延遲增量：約 +0.7～1s
- 解決：專名精確匹配、多輪指代、排序精度
- 剩下：全局性問題（「這批文件的共同點」）；跨文件多跳推理

**這一階段的調參順序建議**：
1. 先固定 `vector_similarity_weight=0.3`（文字 70%）試——**多數企業知識庫的最佳點偏向文字路**，因為專名和數字很多
2. 開 rerank 模型（收益/成本比最高的單一改動）
3. 調 `similarity_threshold`：太低回噪音，太高回不知道。0.2 是保守值，實務上 0.3～0.4 常見
4. **最後**才調 `rank_feature`（PageRank），而且從個位數開始

### ╔══ Phase 3：Agentic + 圖檢索（Scale） ══╗

```
問句
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│  Agentic RAG（rag/advanced_rag/agentic_rag.py）               │
│  LLM 決定：要查幾次？查什麼？要不要用圖？要不要上網？          │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 混合檢索 │ │ GraphRAG │ │ RAPTOR   │ │ Web / SQL /    │  │
│  │          │ │ 實體+社群│ │ 摘要層   │ │ 27 個工具      │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│                        │                                     │
│                        ▼ 多輪迭代                             │
│              夠了嗎？──否──▶ 再查                             │
│                        │是                                    │
└────────────────────────┼─────────────────────────────────────┘
                         ▼
                    生成 + 引用
```

- 新增元件：agentic 迴圈、GraphRAG、RAPTOR、metadata auto filter、cross-language、TOC 增強、web search
- 延遲：3～30s（多輪 LLM）
- 解決：全局問題、多跳推理、需要外部資訊的問題
- 剩下：成本與延遲；agentic 迴圈的不可預測性（同一個問題兩次跑可能查不同東西）

### 三階段對照

| 維度 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| LLM 呼叫數/查詢 | 1 | 2（+改寫） | 3～15（agentic） |
| 檢索延遲 | ~80ms | ~250ms | 1～10s |
| 端對端 P95 | 2～3s | 3～4s | 10～30s |
| 專名查詢 | 差 | 好 | 好 |
| 全局問題 | 無法 | 無法 | 可以 |
| 每千次查詢成本 | $1～3 | $2～5 | $20～100 |
| 可預測性 | 高 | 高 | 中（agentic 有隨機性） |

---

## 七、生成與引用：兩個 token 預算與一個反查演算法

### 7.1 兩層 token 預算

```python
knowledges = kb_prompt(kbinfos, max_tokens)       # ① 0.97
...
used_token_count, msg = message_fit_in(msg, int(max_tokens * 0.95))   # ② 0.95
if "max_tokens" in gen_conf:
    gen_conf["max_tokens"] = min(gen_conf["max_tokens"], max_tokens - used_token_count)
```

**第一層（`kb_prompt`，0.97）**：把召回的 chunk 逐個加入，直到 `max_tokens × 0.97`：

```python
for ck, c in zip(chunks, knowledges):
    chunk_tokens = num_tokens_from_string(c)
    if max_tokens * 0.97 < used_token_count + chunk_tokens:
        logging.warning(f"Not all the retrieval into prompt: {len(selected_chunks)}/{kwlg_len}")
        break
```

**注意那行 warning。** 如果你在 log 裡看到 `Not all the retrieval into prompt: 8/30`，意思是**召回了 30 個 chunk，只有 8 個進了 prompt**。這是一個非常重要的訊號：你的 `top_n` 設得比模型上下文能容納的還多，多召回的部分是純浪費（付了檢索與 rerank 的錢，沒進 prompt）。

**第二層（`message_fit_in`，0.95）**：整個 message 陣列（system + history + 當前問題）超過 95% 時，**丟掉中間的歷史對話，只留 system 和最後一條**：

```python
msg_ = [m for m in msg if m["role"] == "system"]
if len(msg) > 1:
    msg_.append(msg[-1])
```

**取捨很直白：知識比對話歷史重要。** 上下文不夠時砍歷史，不砍知識。

### 7.2 Chunk 在 prompt 裡的格式

```python
cnt = "\nID: {}".format(i)
cnt += draw_node("Title", ck.get("docnm_kwd"))
cnt += draw_node("URL", ck.get("url", ""))
for k, v in (ck.get("document_metadata") or {}).items():
    cnt += draw_node(k, v)
cnt += "\n└── Content:\n"
cnt += ck.get("content_with_weight")
```

實際長這樣：

```
ID: 3
├── Title: 2025-Q3-財報-台灣區.pdf
├── URL: https://...
├── author: 財務部
├── category: 財報
└── Content:
本季營收較上季成長 12%，主要來自通路擴張...
```

**用 ASCII 樹狀結構呈現 metadata。** 這比 JSON 省 token，也比純文字更容易讓模型分辨「這是 metadata，這是內容」。而 `ID: 3` 就是下一節引用要用的編號。

### 7.3 引用對齊：不依賴 LLM 服從度

這是 RAGFlow 最有辨識度的演算法。`insert_citations()`：

```python
def insert_citations(self, answer, chunks, chunk_v, embd_mdl,
                     tkweight=0.1, vtweight=0.9):
```

```
LLM 生成的答案（沒有任何引用標記）
        │
        ▼ ① 切句：正則切分，含中英與阿拉伯文標點
        │    ([^\|][；。？!！،؛؟۔\n]|[a-z؀-ۿ][.?;!،؛؟][ \n])
        │    程式碼區塊（```...```）整塊保留不切
        │
        ▼ ② 過濾：長度 < 5 的片段丟掉（標點碎片）
        │
        ▼ ③ 對每一句做 embedding（ans_v = embd_mdl.encode(pieces_)）
        │
        ▼ ④ 每一句 vs 每一個 chunk 算混合相似度
        │    sim = 0.1 × token相似度 + 0.9 × 向量相似度
        │           └─ 注意：這裡的權重跟檢索時（0.3/0.7）不一樣
        │
        ▼ ⑤ 閾值遞降迴圈
        │    thr = 0.63
        │    while thr > 0.3 and 還沒找到任何引用:
        │        每句取 sim > max(sim)×0.99 的 chunk，最多 4 個
        │        thr *= 0.8            # 0.63 → 0.504 → 0.403 → 0.323
        │
        ▼ ⑥ 在句尾插入 [ID:n]（同一個 chunk 只標第一次）
        │
        ▼
帶引用的答案：「本季營收成長 12%。 [ID:3] 主因是通路擴張。 [ID:3][ID:7]」
```

四個設計決定：

**① 為什麼權重是 0.1/0.9（而非檢索時的 0.3/0.7）？** 因為這裡比對的是「LLM 生成的句子」vs「原文 chunk」。LLM 會改寫、會摘要、會換詞，**字面重疊不可靠，語意相似才可靠**。所以向量權重拉到 0.9。

**② 為什麼閾值要遞降？** 因為一個固定閾值必然在某些答案上找不到任何引用（LLM 改寫太多）。**0.63 起跳、每輪 × 0.8、下限 0.3**——最多 5 輪。設計目標是「盡量給出引用，而不是寧缺勿濫」。

**③ 為什麼是 `sim > max(sim) × 0.99`？** 不是取 top-k，而是取「跟最高分幾乎一樣高的所有 chunk」。這處理的是「同一段內容出現在多個 chunk」的情況——如果有三個 chunk 都同樣支持這句話，就三個都標。上限 4 個。

**④ 成本。** 這一步要對答案的**每一句**做 embedding。一個 10 句的回答 = 10 個 embedding + 10 × N 次相似度計算。在串流輸出的場景，這是在生成完之後才能做，所以它是**加在回應尾端的延遲**（通常 100～300ms）。

還有一個修補函式 `repair_bad_citation_formats(answer, kbinfos, idx)`——處理 LLM 自己亂標引用格式的情況（因為 prompt 裡也有 `citation_prompt()` 教它標）。**兩套機制並行：讓 LLM 標，同時自己反查。** 這是務實的冗餘設計。

---

## 八、為什麼選 X 不選 Y

```
決定                      選 X 的理由                      不選 Y 的理由 / Y 更好的時機
────────────────────────────────────────────────────────────────────────────────────────
加權和融合                 權重可解釋、可調（使用者直接      RRF（Reciprocal Rank Fusion）：
（weighted_sum）           設 vector_similarity_weight）；   不需要分數尺度對齊、更穩健，
vs RRF                    分數尺度已經被 scripted_sim       但權重不可調、無法表達「文字比
                          和 min-max 處理過                  向量重要 2 倍」
                                                            ▶ 翻轉點：接入分數尺度不可控的
                                                              第三方引擎時，RRF 更安全

ES 第二次 KNN-only 請求    候選 64 個向量 × 768 維 × 4B      把向量傳回應用層：一次請求，
vs 傳回 chunk 向量         = 196 KB/查詢的網路傳輸消失；     但傳輸量大、Python 算 cosine 慢
                          ES 算 cosine 是它的本業            ▶ 翻轉點：引擎不支援 KNN-only
                                                              過濾查詢時（OceanBase 就是）

規則式查詢編譯             零 LLM 呼叫、~5ms、完全可預測；    LLM 改寫查詢：語意理解更好，
vs LLM 查詢改寫            同義詞 + bigram + proximity 已    但每次查詢 +300～800ms、
                          覆蓋多數需求                       結果不可重現
                                                            ▶ 翻轉點：查詢極度口語化、
                                                              或需要跨領域術語映射時

rank_feature 用加法        高 PageRank 的不相關 chunk 不會    乘法：讓權威文件全面上升，
vs 乘法                    霸榜；相關性仍是主導訊號           但不相關的權威文件也會霸榜
                                                            ▶ 翻轉點：幾乎沒有；真要放大
                                                              權威性，該調 boost 不是改乘法

分頁 + rerank 直接報錯     浪費算力 + 分頁結果不穩定，        允許但盡力而為：API 更寬容，
vs 允許並盡力              是語意上壞掉的組合                 但使用者會拿到「第 1 頁翻兩次
                                                            內容不同」的 bug 回報
                                                            ▶ 翻轉點：沒有；這是好設計

事後引用反查               不依賴 LLM 服從度、換模型不會壞、  prompt 要求 LLM 標：零額外成本、
（0.1/0.9，0.63→0.3）      引用是可驗證的相似度              零延遲，但小模型經常亂標
vs 只靠 prompt                                              ▶ 翻轉點：只用旗艦模型且延遲
                                                              極度敏感時（RAGFlow 兩者都做）

引用閾值遞降               「盡量給引用」比「寧缺勿濫」更符    固定閾值：行為一致、可預測，
vs 固定閾值                合使用者期待；使用者看不到引用會    但改寫多的答案會完全沒有引用
                          懷疑整個系統                        ▶ 翻轉點：合規場景要求「沒有
                                                              高信心就不標」時

knn_top_k=1024             過濾後召回不足是向量檢索最常見     top_k=20：計算量小、延遲低，
vs top_k=20                的失敗模式；1024 是保險           但套上 kb_id 過濾後可能只剩 2 個
                                                            ▶ 翻轉點：知識庫只有一個
                                                              且不做任何過濾時

GraphRAG 預設關閉          抽取成本是一般 ingestion 的       預設開啟：全局問題直接能答，
vs 預設開啟                10～50 倍                          但新使用者的第一份文件就收到帳單
                                                            ▶ 翻轉點：小而貴的知識庫
                                                              （< 1000 份核心文件）值得全開
```

---

## 九、系統效應：把所有權重放在一張表上

RAGFlow 檢索管線裡所有可調的數字，以及它們的預設值與影響：

| 參數 | 預設 | 在哪一階段 | 調高的後果 | 調低的後果 |
|---|---|---|---|---|
| `important_kwd` boost | 30 | 召回 | 人工關鍵字主導排序 | 人工介入失效 |
| `question_tks` boost | 20 | 召回 | 假問句主導 | FAQ 型查詢變差 |
| `content_ltks` boost | 2 | 召回 | 正文比重上升 | 幾乎全靠關鍵字 |
| `minimum_should_match` | 0.6 → 0.3 → 0.1 | 召回 | 精確度高、召回低 | 噪音多 |
| `knn_top_k` | 1024 | 召回 | ES 計算量大 | 過濾後召回不足 |
| `knn_num_candidates` | 2048 | 召回 | HNSW 搜得更廣、更慢 | 近似誤差變大 |
| `vector_similarity_weight` | 0.3 | 融合 | 偏語意 | 偏字面 |
| `tkweight / vtweight` | 0.3 / 0.7 | 重排 | 同上 | 同上 |
| chunk token 加倍 | title×2, kwd×5, q×6 | 重排 | 人工欄位主導 | 全靠正文 |
| bigram 權重 | 0.6（unigram 0.4） | 重排 | 詞序敏感 | 退化成詞袋 |
| `tag_feas` 乘數 | 10 | 重排 | 標籤先驗主導 | 標籤無效 |
| `PAGERANK_FLD` | 10 | 重排 | 權威文件霸榜 | 文件一律平等 |
| `similarity_threshold` | 0.2 | 過濾 | 常回「不知道」 | 噪音進 prompt |
| `rerank_candidates_count` | 64 | rerank | 精度高、延遲高 | 精度低 |
| `kb_prompt` 預算 | max_tokens × 0.97 | prompt | 塞更多知識 | 更多 chunk 被丟棄 |
| `message_fit_in` 預算 | max_tokens × 0.95 | prompt | 保留更多歷史 | 歷史被砍更多 |
| 引用起始閾值 | 0.63（×0.8 至 0.3） | 引用 | 引用少但準 | 引用多但可能錯 |
| 引用權重 | 0.1 / 0.9 | 引用 | — | — |
| 每句最多引用 | 4 | 引用 | 標記雜亂 | 漏標支持來源 |

**如果只能調三個，我會調這三個**：

1. **`vector_similarity_weight`**（0.3）— 企業知識庫通常該更偏文字（0.2～0.3），閒聊型知識庫該更偏語意（0.5～0.7）
2. **`similarity_threshold`**（0.2）— 這是「寧可說不知道」與「寧可猜」的旋鈕，直接決定使用者對系統可信度的觀感
3. **`top_n`**（配合 log 裡的 `Not all the retrieval into prompt` 警告調整）— 超過 prompt 容量的召回是純浪費

---

## 十、系列導航

檢索與生成講完了。到這裡，資料的完整生命週期——進場、編碼、儲存、取回、生成、引用——都拆過一遍。

最後一篇回到工程層面：這一切是怎麼被組織成一個可以運行、可以擴充、可以維護的系統的。進程拓撲、服務分層、13 種非同步任務型別、兩套 DAG 執行引擎，以及那個正在進行中、把熱路徑改寫成 Go 的遷移。

- **Part 5 — 系統與程式碼結構**：服務分層、Task Executor、Agent Canvas 與 Go 遷移

← [Part 3 — Encode 與 Save — 向量化、索引 Schema 與雙引擎抽象](../ragflow-intro-part3-embedding-indexing-zh) | [Part 5 — 系統與程式碼結構 — 服務分層、Task Executor 與 Go 遷移 →](../ragflow-intro-part5-system-code-structure-zh)

---

*本文基於 RAGFlow `main` 分支（2026 年 9 月）原始碼撰寫。所有權重、閾值與公式皆從 `rag/nlp/query.py`、`rag/nlp/search.py`、`api/db/services/dialog_service.py`、`rag/prompts/generator.py` 實際核對。延遲與成本數字為量級估算。*
