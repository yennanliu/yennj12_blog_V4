---
title: "ChatPDF RAG 優化（一）：語意切塊與混合檢索 Semantic Chunking + Hybrid Retrieval"
date: 2026-06-30T10:00:00+08:00
draft: false
description: "RAG 的成敗，八成決定在「切塊」與「檢索」這兩步。本篇拆解 chatPDF 如何從寫死的固定切塊，升級成 embedding 偵測語意轉折的 Semantic Chunking，以及如何把 dense 向量檢索與 BM25 關鍵字檢索融合成 Hybrid Retrieval——附完整 Python 實作與設計取捨。"
categories: ["engineering", "ai", "all"]
tags: ["RAG", "LLM", "ChatPDF", "Semantic Chunking", "BM25", "Hybrid Retrieval", "Embedding", "Vector Search", "Information Retrieval"]
authors: ["yen"]
readTime: "16 min"
---

> 多數 RAG 教學的做法：把文件每 1000 字切一刀，丟進向量資料庫，cosine 相似度 top-k 撈回來。
> 但實務上 80% 的爛答案，不是 LLM 不夠強，而是「切錯地方」或「撈錯段落」。
> chatPDF 這次的優化，核心就兩件事：讓切塊跟著「語意」走，讓檢索同時懂「語意」和「字面」。

---

## 一、為什麼切塊與檢索是 RAG 的命門

一個 RAG 系統的流程很單純：

```
   PDF ──▶ 切塊(Chunking) ──▶ 向量化 ──▶ 檢索(Retrieval) ──▶ LLM 生成
              ▲                              ▲
              │                              │
         決定「知識的最小單位」        決定「撈回哪些單位」
```

LLM 生成是最後一步，但它能講什麼，完全取決於前面撈回了什麼。而撈回什麼，又取決於當初怎麼切。所以這條鏈裡，**切塊與檢索才是真正的瓶頸**——它們決定了 LLM 能「看到」的內容。

chatPDF 原本的問題很典型：

1. **切塊是寫死的**:不管 `RAGConfig` 設定什麼,都用固定字數硬切。一個句子、一張表、一段論證,常常被攔腰切斷。
2. **檢索只有 dense 一種**:純向量相似度。遇到「精確關鍵字」(產品型號、縮寫、法條編號)時,語意向量反而抓不準。

[PR #1](https://github.com/yennanliu/chatPDF/pull/1) 就是針對這兩點:**Semantic Chunking** 與 **Hybrid Retrieval**。

---

## 二、固定切塊的問題:把意思切碎了

固定切塊(fixed-size chunking)是這樣的:

```
原文:
"本季營收成長 18%。主因是雲端業務擴張。│ 另一方面,匯率造成
                              切在這  ▲
3% 的逆風。展望下季,管理層預期..."
```

問題在於:它在「**字數到了**」就切,完全不管那裡是不是一個語意邊界。結果常常:

- 把一個完整論點切成兩半 → 兩個 chunk 都殘缺,檢索時誰都撈不全
- 把兩個無關主題塞進同一塊 → 向量被「平均」掉,語意模糊

```
固定切塊的失敗模式
──────────────────────────────────
chunk A: "...雲端業務擴張。另一方面,匯率"   ← 結尾被砍
chunk B: "造成 3% 的逆風。展望下季..."       ← 開頭沒頭沒尾
```

我們要的是:**在「主題轉換」的地方切,而不是在「字數到了」的地方切。**

---

## 三、Semantic Chunking:用 embedding 偵測語意轉折

### 核心想法

如果把每個句子向量化,相鄰句子的**向量距離**就反映了它們語意上的接近程度:

- 距離小 → 兩句在講同一件事 → 不該切
- 距離突然變大 → 主題轉換了 → 這裡該切

```
   句子向量距離(相鄰句之間)
   距離
    │           ╭─ 突波!主題轉換 → 切點
    │          ╱│
    │  ╲      ╱ │
    │   ╲────╯  │   ╲___
    └───────────────────▶ 句子序
       同主題    切    新主題
```

那「距離多大才算突波」?用**百分位數**動態決定:預設取第 90 百分位數當門檻——也就是「最劇烈的那 10% 轉折」才切。這樣不同文件能自動適應自己的語意節奏,不需要人工調絕對門檻。

### 實作

```python
class SemanticChunker(BaseChunker):
    """在 embedding 偵測到的語意轉折處切塊,並有字數上限保護。"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 0,
        breakpoint_percentile: int = 90,   # 取最劇烈的 10% 轉折當切點
        embedder: BaseEmbedder | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.breakpoint_percentile = breakpoint_percentile
        self._embedder = embedder

    def split(self, text: str) -> list[str]:
        # 1. 先切成句子
        sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
        if len(sentences) <= 1:
            return sentences

        import numpy as np

        # 2. 每個句子各自向量化
        vectors = [np.asarray(v, dtype=float)
                   for v in self._get_embedder().embed(sentences)]

        # 3. 計算相鄰句子的 cosine 距離(1 - cosine 相似度)
        distances = [1.0 - _cosine(vectors[i], vectors[i + 1])
                     for i in range(len(vectors) - 1)]

        # 4. 用百分位數決定「主題轉換」的門檻
        threshold = float(np.percentile(distances, self.breakpoint_percentile))

        # 5. 逐句累積,遇到突波或超過字數上限就切
        chunks: list[str] = []
        current = [sentences[0]]
        for i in range(1, len(sentences)):
            topic_shift = distances[i - 1] > threshold
            too_big = len(" ".join(current)) + 1 + len(sentences[i]) > self.chunk_size
            if topic_shift or too_big:
                chunks.append(" ".join(current))
                current = [sentences[i]]
            else:
                current.append(sentences[i])
        chunks.append(" ".join(current))
        return chunks
```

### 設計重點

1. **百分位數而非絕對值**:不同文件的語意密度差很多。技術手冊可能句句轉折,小說可能整段同調。用百分位數讓門檻**隨文件自適應**。
2. **字數上限當保險**:`too_big` 這個條件確保即使一整段都不轉折,也不會切出一個超長 chunk 撐爆 context window。**語意優先,但有上限兜底。**
3. **句子邊界為基礎**:先用 regex 切句,再以句子為最小單位累積——保證不會把一個句子切兩半。

---

## 四、純向量檢索的盲點:它讀不懂「字面」

Semantic Chunking 解決了「切」,接著是「撈」。

純 dense(向量)檢索的原理是:把 query 和每個 chunk 都向量化,算 cosine 相似度,取最近的 top-k。它很擅長**語意近似**——你問「公司賺錢嗎」,它能撈到講「營收成長」「獲利率」的段落,即使沒出現「賺錢」二字。

但它有個致命盲點:**精確字面匹配**。

```
   query: "GPT-4o 的 context window 多大?"

   dense 檢索:把整句變成一個語意向量,
              "GPT-4o" 這種專有名詞被稀釋成一般語意
              → 可能撈回一堆講「模型能力」的泛泛段落,
                卻錯過真正寫著 "GPT-4o ... 128k" 的那一行
```

對於**型號、縮寫、代碼、法條編號、人名**這類「字面就是一切」的查詢,你需要的是老派但精準的**關鍵字檢索**——這正是 BM25 的強項。

---

## 五、BM25:無依賴的關鍵字檢索

BM25(Okapi BM25)是資訊檢索界的經典演算法。直覺是:

- 一個詞在某文件出現越多次 → 該文件越相關(但有**飽和**,出現 100 次不會比 10 次強 10 倍)
- 一個詞越**罕見**(IDF 高)→ 它命中時越有鑑別力(「the」命中沒意義,「GPT-4o」命中很有意義)
- **越短**的文件命中同樣的詞 → 越相關(長度正規化)

```python
class BM25:
    """無外部依賴的 BM25 關鍵字相關度評分器。"""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1   # 詞頻飽和參數
        self.b = b     # 文件長度正規化強度
        self.N = len(corpus_tokens)
        self.doc_len = [len(d) for d in corpus_tokens]
        self.avgdl = sum(self.doc_len) / self.N if self.N else 0.0

        # 建立詞頻表(tf)與文件頻率表(df)
        self.tf, self.df = [], {}
        for doc in corpus_tokens:
            freqs = {}
            for term in doc:
                freqs[term] = freqs.get(term, 0) + 1
            self.tf.append(freqs)
            for term in freqs:
                self.df[term] = self.df.get(term, 0) + 1

    def idf(self, term: str) -> float:
        """逆文件頻率:越罕見的詞,分數越高。"""
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def scores(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        out = []
        for i in range(self.N):
            freqs, dl = self.tf[i], self.doc_len[i]
            norm = self.k1 * (1 - self.b + self.b * dl / self.avgdl) if self.avgdl else self.k1
            score = 0.0
            for term in q_terms:
                f = freqs.get(term, 0)
                if f:
                    # IDF 權重 × 飽和後的詞頻貢獻
                    score += self.idf(term) * (f * (self.k1 + 1)) / (f + norm)
            out.append(score)
        return out
```

**為什麼自己實作而不裝套件?** BM25 的核心邏輯只有幾十行,且不需要任何外部依賴。自己寫一份,部署時少一個套件、少一個版本衝突風險,對一個輕量服務來說很划算。

---

## 六、Hybrid Retrieval:把語意與字面融合

有了 dense 和 sparse(BM25)兩套分數,接下來要**融合**。直接相加不行——兩者的分數量級完全不同(cosine 在 0~1,BM25 可能是 0~20)。所以先各自**min-max 正規化到 [0,1]**,再用權重 `alpha` 加權混合。

```
   融合公式:
   fused = alpha × dense_norm + (1 - alpha) × sparse_norm

   alpha = 1.0  →  純語意(dense)
   alpha = 0.0  →  純字面(BM25)
   alpha = 0.5  →  各半(預設)
```

```python
class HybridRetriever(BaseRetriever):
    """以 min-max 正規化後的加權混合,融合 dense 向量與 BM25。"""

    def __init__(self, vs: VectorStore, alpha: float = 0.5):
        self._vs = vs
        self._alpha = alpha   # 1.0=純 dense,0.0=純 sparse

    def search(self, query: str, top_k: int, doc_ids: list[str]) -> list[dict]:
        from .sparse import BM25, tokenize

        corpus = self._vs.get_chunks(doc_ids)
        if not corpus:
            return []

        # dense:全 chunk 的向量相似度
        dense = self._vs.query(doc_ids, query, len(corpus))
        dense_by_key = {_key(d["metadata"]): d["score"] for d in dense}

        # sparse:全 chunk 的 BM25 分數
        sparse = BM25([tokenize(c["text"]) for c in corpus]).scores(query)
        sparse_by_key = {_key(corpus[i]["metadata"]): sparse[i]
                         for i in range(len(corpus))}

        # 兩套分數各自正規化到 [0,1]
        dnorm = _minmax(dense_by_key)
        snorm = _minmax(sparse_by_key)

        # 加權融合
        fused = [
            {
                "text": c["text"],
                "metadata": c["metadata"],
                "score": self._alpha * dnorm.get(_key(c["metadata"]), 0.0)
                       + (1 - self._alpha) * snorm.get(_key(c["metadata"]), 0.0),
            }
            for c in corpus
        ]
        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused[:top_k]


def _minmax(by_key: dict) -> dict:
    """把分數正規化到 [0,1]。"""
    if not by_key:
        return {}
    lo, hi = min(by_key.values()), max(by_key.values())
    rng = hi - lo
    if rng == 0:
        return {k: 0.0 for k in by_key}
    return {k: (v - lo) / rng for k, v in by_key.items()}
```

### 設計重點

1. **為什麼要 min-max 正規化?** dense 與 sparse 的分數量級天差地遠,不正規化的話,加權等於只看其中一個。正規化後兩者站在同一個 [0,1] 的起跑線,`alpha` 才真正控制得了權重。
2. **alpha 是可調參數**:不同類型的查詢適合不同 alpha。FAQ 型語意查詢調高 alpha,規格/型號查詢調低 alpha。這次也把它做進前端 UI,使用者能在「Retrieval settings」面板即時調。

---

## 七、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 切塊策略 | Semantic(語意轉折) | 不選固定字數:固定切會把論點切碎、把無關主題混塊 |
| 切點門檻 | 百分位數(自適應) | 不選絕對門檻:不同文件語意密度差太多,絕對值無法通用 |
| 切塊保險 | 語意 + 字數上限 | 不選純語意:整段不轉折時會切出撐爆 context 的超長塊 |
| 關鍵字檢索 | 自寫 BM25 | 不選裝套件:核心僅數十行,自寫省依賴、省版本風險 |
| 檢索方式 | Hybrid(dense+sparse) | 不選純 dense:精確型號/縮寫/代碼,語意向量會稀釋掉 |
| 分數融合 | min-max 正規化後加權 | 不選直接相加:兩者量級不同,直接加等於忽略其一 |

**Flip condition(什麼時候反過來選)**:

- 若文件本身就是均勻短段落(如 FAQ 條目),固定切塊反而簡單可靠,不必上 Semantic。
- 若查詢幾乎全是自然語言問句、沒有專有名詞,純 dense(alpha=1.0)就夠,BM25 是多餘成本。
- 若語料極大(百萬級 chunk),每次查詢都重算全語料 BM25 會太慢——需要預建倒排索引(這正是 PR #2 加 LRU cache 要解的問題,見下篇)。

---

## 八、系統效應:改動前 vs 改動後

| 面向 | 改動前 | 改動後 |
|------|--------|--------|
| 切塊 | 固定字數,忽略 RAGConfig | Semantic 語意轉折 + 字數上限,可配置 |
| 檢索 | 純 dense 向量 | Hybrid(dense + BM25),alpha 可調 |
| 精確關鍵字查詢 | 常被語意向量稀釋撈不準 | BM25 補上字面精準命中 |
| 可調性 | 寫死 | 前端 UI 即時調 chunker / alpha / top_k |
| 測試 | — | +16 semantic chunker + 18 hybrid retrieval 測試,128 測試全綠 |
| 評估指南 | — | 新增 `rag_tuning.md`、`rag_evaluation.md`(Hit@k、MRR、nDCG) |

---

## 九、小結

這篇的核心心法,可以濃縮成兩句:

1. **切塊要跟著「意思」走,不要跟著「字數」走**——用 embedding 偵測語意轉折,百分位數自適應門檻,字數上限兜底。
2. **檢索要同時懂「語意」與「字面」**——dense 抓近似、BM25 抓精準,正規化後用 alpha 融合,讓使用者按查詢類型調權重。

> 一句話總結:RAG 的品質不是靠更強的 LLM 堆出來的,而是靠「切對地方、撈對段落」省出來的。

下一篇([第二部分](../chatpdf-rag-optimization-part2-backend-hardening-zh/))會進入**後端強化與進階 RAG**:上傳安全驗證、資源邊界、多查詢擴展、檢索評分過濾、頁碼引用、LRU 快取——把這套 pipeline 從「能跑」變成「能上線」。

---

**系列導覽**

- 第一部分:語意切塊與混合檢索(本篇)
- [第二部分:後端強化與進階 RAG](../chatpdf-rag-optimization-part2-backend-hardening-zh/)
- [第三部分:可觀測性與評估](../chatpdf-rag-optimization-part3-observability-eval-zh/)

**參考連結**

- PR: [Feat/rag chunking optimization #1](https://github.com/yennanliu/chatPDF/pull/1)
- Repo: [yennanliu/chatPDF](https://github.com/yennanliu/chatPDF)
