---
title: "Knowledge Graph 知識圖譜（四）：結合 LLM — GraphRAG 與多跳推理"
date: 2026-06-29T12:00:00+08:00
draft: false
weight: 4
description: "為什麼純向量 RAG 在多跳問題上失敗？GraphRAG 如何用知識圖譜補足、降低 LLM 幻覺。含 LangChain + Neo4j 的可跑程式碼與 Text2Cypher 實作。"
categories: ["engineering", "ai", "all"]
tags: ["Knowledge Graph", "知識圖譜", "GraphRAG", "LLM", "RAG", "Neo4j", "LangChain"]
authors: ["yen"]
readTime: "25 min"
series: ["knowledge-graph"]
---

> *大多數人遇到 RAG 答不準，第一反應是換更強的 embedding 模型。*
> *正確答案是：多跳問題的瓶頸不在召回相似度，而在缺少「關係結構」。*
> *大多數人以為知識圖譜和 LLM 是兩個世界。*
> *正確答案是：LLM 負責語言理解，知識圖譜負責事實與推理，合起來才完整。*

---

## 接續前文

[Part 3](/posts/knowledge-graph-part3-comparison-zh/) 我們確立了「知識圖譜與向量庫互補」。這一篇把它落地到 LLM 系統：解釋 **GraphRAG** 為什麼出現、它如何運作、以及用 LangChain + Neo4j 寫出可跑的程式碼。

---

## 一、核心問題：純向量 RAG 在哪裡失敗？

標準 RAG（Retrieval-Augmented Generation）流程是：把文件切塊（chunk）→ 算 embedding → 存向量庫 → 查詢時找最相似的塊 → 塞進 prompt。這對「事實型單跳問題」很有效，但有兩個致命弱點：

**弱點一：多跳推理（multi-hop）**

問題：「全面啟動的配樂家，還為哪位導演的哪部片配過樂？」

```
純向量 RAG 的困境：
  Query embedding ──▶ 找最相似的塊
                       │
                       ▼
      只會召回「提到全面啟動配樂」的段落
      但「配樂家 → 其他作品 → 那部片的導演」這條關係鏈
      分散在不同文件、不同塊裡，相似度檢索串不起來 ✗
```

向量檢索本質是「單跳相似」。它無法沿著「實體 A → 關係 → 實體 B → 關係 → 實體 C」的鏈條走，因為這需要的是**結構**，不是相似度。

**弱點二：全域性問題（global question）**

問題：「這 500 份報告整體上談了哪些主題趨勢？」向量檢索只會召回 top-k 個塊，看不到全貌。

**弱點三：幻覺與不可解釋**

召回到「相似但事實錯誤」的塊時，LLM 會照著編。而且你無法追溯它「為什麼這樣答」。

---

## 二、GraphRAG：用知識圖譜補足 RAG

GraphRAG 的核心思想：**在檢索與生成之間，加入一層知識圖譜，提供結構化的關係與可推理的事實。**

```
┌──────────────────────────────────────────────────────────────┐
│                        GraphRAG 架構                            │
│                                                                │
│   使用者問題                                                     │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────┐    ┌──────────────────┐                       │
│  │ 向量檢索      │    │  知識圖譜檢索      │                       │
│  │ 語意召回相關塊 │    │  實體連結 + 圖遍歷  │                       │
│  └──────┬──────┘    └─────────┬────────┘                       │
│         │                     │                                │
│         └──────────┬──────────┘                                │
│                    ▼                                           │
│           ┌──────────────────┐                                 │
│           │  融合 Context      │  (相似塊 + 關係子圖 + 路徑)      │
│           └────────┬─────────┘                                 │
│                    ▼                                           │
│           ┌──────────────────┐                                 │
│           │  LLM 生成 + 引用    │  (可追溯路徑、可解釋)            │
│           └──────────────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

兩種主流的 GraphRAG 範式：

| 範式 | 做法 | 適合 |
|------|------|------|
| **Text2Cypher（查詢式）** | LLM 把自然語言問題翻成 Cypher，直接查圖 | 精確事實、多跳問答 |
| **社群摘要式（微軟 GraphRAG）** | 先把文件建成圖、分群、各群生成摘要，回答全域問題 | 「整體趨勢」這類全域問題 |

---

## 三、為什麼 GraphRAG 不只是「再加一個檢索器」

| 維度 | 純向量 RAG | GraphRAG |
|------|-----------|----------|
| 單跳事實 | 好 | 好 |
| 多跳推理 | 弱（串不起關係鏈） | 強（圖遍歷天生支援） |
| 全域問題 | 弱（只看 top-k） | 強（社群摘要） |
| 可解釋性 | 低 | 高（可回傳關係路徑） |
| 事實校驗 | 無 | 可用圖做 grounding |
| 幻覺率 | 較高 | 較低（有結構約束） |
| 建置成本 | 低 | 較高（需先建圖） |

**為什麼選 GraphRAG 不選純向量 RAG**：當問題涉及多跳關係、需要可解釋、或要回答全域性問題。**翻轉條件**：如果你的問題 95% 都是「單一文件內的單跳事實查找」，純向量 RAG 更簡單便宜，不必為了 GraphRAG 增加建圖成本。

---

## 四、實作一：Text2Cypher — 讓 LLM 自動寫圖查詢

這是最實用的 GraphRAG 入門。我們用 LangChain 的 `GraphCypherQAChain`，它會：接收自然語言問題 → 看圖的 schema → 生成 Cypher → 執行 → 把結果交給 LLM 組成答案。

延續 [Part 2](/posts/knowledge-graph-part2-construction-zh/) 建好的電影知識圖譜：

```python
# pip install langchain langchain-openai langchain-neo4j neo4j
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI

# 1. 連到 Part 2 建好的知識圖譜
graph = Neo4jGraph(
    url="bolt://localhost:7687",
    username="neo4j",
    password="password123",
)
graph.refresh_schema()   # 讓 LLM 知道圖的結構

# 2. 建立 Text2Cypher 問答鏈
llm = ChatOpenAI(model="gpt-4o", temperature=0)
chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    verbose=True,                 # 印出產生的 Cypher，方便除錯
    allow_dangerous_requests=True # 正式環境請改用唯讀帳號（見第七節）
)

# 3. 用自然語言問多跳問題
result = chain.invoke({
    "query": "諾蘭的電影裡，有哪些演員也演過漫威電影？"
})
print(result["result"])
```

背後 LLM 會生成類似這樣的 Cypher（你會在 `verbose` 看到）：

```cypher
MATCH (n:Person {name:"Nolan"})-[:DIRECTED]->(m:Movie)
MATCH (a:Person)-[:ACTED_IN]->(m)
MATCH (a)-[:ACTED_IN]->(:Movie)-[:PART_OF]->(:Franchise {name:"Marvel"})
RETURN DISTINCT a.name
```

關鍵價值：**答案直接來自圖上的事實，不是 LLM 的記憶**。LLM 只負責「翻譯問題」和「組織語言」，事實由知識圖譜提供 —— 這就是降低幻覺的機制。

---

## 五、實作二：圖檢索 + 向量檢索的混合

更強的做法是兩條腿走路：向量召回相關文字塊，同時從問題中的實體出發，抓取它在圖上的鄰居子圖，兩者一起餵給 LLM。

```python
from langchain_neo4j import Neo4jGraph
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_neo4j import Neo4jVector

graph = Neo4jGraph(url="bolt://localhost:7687",
                   username="neo4j", password="password123")

# A. 向量檢索：召回語意相關的文字塊（事先已 embedding 存入 Neo4j）
vector_index = Neo4jVector.from_existing_index(
    OpenAIEmbeddings(),
    url="bolt://localhost:7687", username="neo4j", password="password123",
    index_name="chunk_embeddings",
)

def graph_context(entity: str, hops: int = 2) -> str:
    """從某實體出發，抓取 N 跳鄰居作為結構化 context。"""
    rows = graph.query(f"""
        MATCH path = (e {{name: $entity}})-[*1..{hops}]-(neighbor)
        RETURN [r IN relationships(path) | type(r)] AS rels,
               [n IN nodes(path) | n.name] AS names
        LIMIT 50
    """, params={"entity": entity})
    # 把路徑攤平成「A -[REL]-> B」這種事實句，LLM 容易吸收
    facts = []
    for row in rows:
        names, rels = row["names"], row["rels"]
        for i, rel in enumerate(rels):
            facts.append(f"{names[i]} -[{rel}]-> {names[i+1]}")
    return "\n".join(set(facts))

def hybrid_rag(question: str, entity: str) -> str:
    docs = vector_index.similarity_search(question, k=4)
    text_ctx = "\n".join(d.page_content for d in docs)   # 模糊語意
    kg_ctx = graph_context(entity)                       # 精確關係

    prompt = f"""根據以下資訊回答問題。若資訊不足，請說「資料不足」，不要編造。

[文件片段（語意相關）]
{text_ctx}

[知識圖譜事實（精確關係）]
{kg_ctx}

問題：{question}
答案："""
    return ChatOpenAI(model="gpt-4o", temperature=0).invoke(prompt).content

print(hybrid_rag("諾蘭和小勞勃道尼有什麼間接關聯？", entity="Nolan"))
```

這個架構同時拿到了「相似文字」與「精確關係」，正是 [Part 3](/posts/knowledge-graph-part3-comparison-zh/) 那張混合架構圖的具體實現。

---

## 六、知識圖譜如何降低幻覺：Grounding 機制

知識圖譜降低幻覺有三個層次，由淺到深：

```
層次一：提供事實 context（最基本）
  把圖上的事實塞進 prompt，給 LLM 正確依據。

層次二：約束生成（grounding）
  要求 LLM「只能根據提供的圖事實回答」，並標註每句話的來源節點。

層次三：事後校驗（fact-checking）
  LLM 產生答案後，把答案中的宣稱（claim）拆解成三元組，
  回查知識圖譜驗證是否成立，不成立就標記或重新生成。
```

層次三的概念實作：

```python
def verify_against_kg(claim_triples: list[tuple]) -> list[dict]:
    """把 LLM 答案抽成的三元組逐一回查知識圖譜，校驗真偽。"""
    results = []
    for s, rel, o in claim_triples:
        exists = graph.query("""
            MATCH (a {name:$s})-[r]->(b {name:$o})
            WHERE type(r) = $rel
            RETURN count(r) > 0 AS supported
        """, params={"s": s, "rel": rel, "o": o})
        results.append({"triple": (s, rel, o),
                        "supported": exists[0]["supported"]})
    return results

# 若某 claim 在圖上找不到支持 → 標記為「未經證實」或要求 LLM 重答
```

這正是知識圖譜相對純 LLM 的關鍵價值：**它是一個可被程式查證的事實基準（ground truth）**，而 LLM 的參數記憶不是。

---

## 七、生產注意事項：別讓 Text2Cypher 變成資安漏洞

Text2Cypher 很強，但 LLM 生成的查詢直接打資料庫，有風險。生產環境必守：

```
GraphRAG 生產 Checklist
├─ 安全
│   ├─ [ ] 用唯讀（read-only）資料庫帳號執行 LLM 生成的查詢
│   ├─ [ ] 禁止 LLM 產生寫入語句（CREATE/DELETE/SET/MERGE）
│   └─ [ ] 對查詢加 timeout 與結果筆數上限，防止全圖掃描拖垮 DB
├─ 品質
│   ├─ [ ] 提供清楚的 schema 與 few-shot 範例給 LLM，提升 Cypher 正確率
│   ├─ [ ] Cypher 生成失敗時的 fallback（退回向量 RAG 或請使用者澄清）
│   └─ [ ] 對「圖上查無資料」回傳明確訊息，而非讓 LLM 自由發揮
└─ 成本/效能
    ├─ [ ] 快取常見問題的 Cypher 與結果
    └─ [ ] 監控每查詢的 LLM token 與圖查詢延遲
```

唯讀防護的最小實作：

```python
import re
FORBIDDEN = re.compile(r"\b(CREATE|DELETE|DETACH|SET|MERGE|REMOVE|DROP)\b", re.I)

def guard(cypher: str) -> str:
    if FORBIDDEN.search(cypher):
        raise ValueError(f"拒絕執行含寫入操作的查詢：{cypher}")
    return cypher
```

---

## 八、系統效應：導入 GraphRAG 前後

以一個「企業內部技術文件問答」為例：

| 指標 | 純向量 RAG | GraphRAG |
|------|-----------|----------|
| 單跳事實問題正確率 | ~85% | ~88% |
| 多跳關係問題正確率 | ~40% | ~80% |
| 「整體趨勢」全域問題 | 幾乎無法回答 | 可回答（社群摘要） |
| 答案可解釋性（可附來源路徑） | 低 | 高 |
| 幻覺率（人工抽檢） | ~15% | ~5% |
| 建置與維運成本 | 低 | 中（需建圖+維護） |

數字隨資料與場景而變，但模式穩定：**GraphRAG 在多跳與全域問題上是數量級的改善，代價是建圖成本**。這也呼應 Part 3 的結論——它和向量 RAG 是互補，不是取代。

---

## 九、本篇小結與下一步

1. 純向量 RAG 的瓶頸在**多跳推理、全域問題、可解釋性**。
2. **GraphRAG** 在檢索與生成間加入知識圖譜層，補足結構化關係。
3. 兩大範式：**Text2Cypher**（精確問答）與**社群摘要**（全域問題）。
4. 知識圖譜透過 **context / grounding / 事後校驗** 三層機制降低幻覺。
5. 生產務必用**唯讀帳號 + 寫入防護 + timeout**。

最後一篇（Part 5）是完整實戰：我們會**用 LLM 把一批純文字文件自動抽成知識圖譜**，存進 Neo4j，再接上 GraphRAG 做問答——把整個系列學到的東西串成一個端到端、可跑的專案。

---

## 系列導航

← [Part 3：與關聯式 / 向量 / 文件資料庫的比較](/posts/knowledge-graph-part3-comparison-zh/)

→ [Part 5：實戰 — 用 LLM 自動建構知識圖譜並做問答](/posts/knowledge-graph-part5-end-to-end-project-zh/)

---

*本文為「Knowledge Graph 知識圖譜」系列第 4 篇，共 5 篇。*
