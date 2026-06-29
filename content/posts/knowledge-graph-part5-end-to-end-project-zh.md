---
title: "Knowledge Graph 知識圖譜（五）：實戰 — 用 LLM 自動建構知識圖譜並做問答"
date: 2026-06-29T13:00:00+08:00
draft: false
weight: 5
description: "端到端實戰：用 LLM 把純文字文件自動抽成三元組、寫入 Neo4j、再接 GraphRAG 做問答。完整可跑的 Python 程式碼與架構演進建議。"
categories: ["engineering", "ai", "all"]
tags: ["Knowledge Graph", "知識圖譜", "GraphRAG", "LLM", "Neo4j", "LangChain", "Project"]
authors: ["yen"]
readTime: "26 min"
series: ["knowledge-graph"]
---

> *大多數人學完知識圖譜，卡在「我的文件那麼多，難道要手動建圖？」*
> *正確答案是：在 LLM 時代，抽取交給模型，你只需設計好流程與驗收。*
> *大多數 demo 跑得起來，上線就垮。*
> *正確答案是：把建圖、查詢、校驗拆成可演進的三個階段（POC → MVP → Scale）。*

---

## 這是系列的最後一塊拼圖

前四篇我們學了概念（[Part 1](/posts/knowledge-graph-part1-fundamentals-zh/)）、建構管線（[Part 2](/posts/knowledge-graph-part2-construction-zh/)）、技術比較（[Part 3](/posts/knowledge-graph-part3-comparison-zh/)）、與 LLM 結合（[Part 4](/posts/knowledge-graph-part4-llm-graphrag-zh/)）。這一篇把它們串成一個**端到端、可實際執行**的專案：

> **目標**：丟進一批純文字文件 → LLM 自動抽成知識圖譜 → 存進 Neo4j → 用自然語言問答。

---

## 一、整體架構：四個階段

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│ 1. 文件載入   │─▶│ 2. LLM 抽取    │─▶│ 3. 寫入 Neo4j │─▶│ 4. GraphRAG  │
│  切塊        │  │ 三元組 + 消歧   │  │  MERGE 去重   │  │  自然語言問答  │
└─────────────┘  └──────────────┘  └─────────────┘  └──────────────┘
       Part 2          Part 2+4          Part 2          Part 4
```

我們會用：Python、LangChain、`langchain-experimental` 的 `LLMGraphTransformer`（把文件直接轉成圖文件）、Neo4j。

---

## 二、Phase 1：POC — 把 demo 跑起來（< 10 份文件）

**目標**：兩小時內驗證 LLM 抽取在你的領域是否可行。能接受的捷徑：硬編參數、不做嚴格消歧、本機 Neo4j。

### 2.1 準備文件

```python
from langchain_core.documents import Document

# 真實專案會從 PDF/網頁載入；POC 先用幾段文字
docs = [
    Document(page_content=(
        "克里斯多福·諾蘭執導了《全面啟動》與《敦克爾克大行動》。"
        "《全面啟動》由李奧納多主演，配樂由漢斯·季默操刀。"
        "漢斯·季默也為《沙丘》配樂，《沙丘》由丹尼·維勒納夫執導。"
    )),
    Document(page_content=(
        "小勞勃道尼在漫威電影《鋼鐵人》中飾演東尼·史塔克。"
        "《鋼鐵人》屬於漫威電影宇宙。"
    )),
]
```

### 2.2 用 LLM 自動抽成圖

這是整個專案的核心——`LLMGraphTransformer` 會提示 LLM 從每段文字抽出實體與關係，輸出成圖結構：

```python
# pip install langchain-experimental langchain-openai langchain-neo4j
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)

transformer = LLMGraphTransformer(
    llm=llm,
    # 限定節點/關係型別 → 大幅提升一致性，避免 LLM 自由發揮造出一堆同義關係
    allowed_nodes=["Person", "Movie", "Franchise", "Composer"],
    allowed_relationships=["DIRECTED", "ACTED_IN", "COMPOSED_FOR", "PART_OF"],
)

graph_documents = transformer.convert_to_graph_documents(docs)

for gd in graph_documents:
    print("節點：", [(n.id, n.type) for n in gd.nodes])
    print("關係：", [(r.source.id, r.type, r.target.id) for r in gd.relationships])
```

> **關鍵技巧**：`allowed_nodes` / `allowed_relationships` 就是把 [Part 1](/posts/knowledge-graph-part1-fundamentals-zh/) 講的「本體」輕量化地交給 LLM。不限定的話，LLM 可能把「執導」抽成 `DIRECTED`、`DIRECT`、`IS_DIRECTOR_OF` 三種，圖就碎了。

### 2.3 寫進 Neo4j

```python
from langchain_neo4j import Neo4jGraph

graph = Neo4jGraph(url="bolt://localhost:7687",
                   username="neo4j", password="password123")

# add_graph_documents 內部用 MERGE，天然去重（呼應 Part 2）
graph.add_graph_documents(
    graph_documents,
    baseEntityLabel=True,   # 加上共同 Label，方便跨型別查詢
    include_source=True,    # 保留來源文件，支援答案溯源
)
print("知識圖譜建構完成，打開 http://localhost:7474 看看 ✅")
```

### 2.4 問答

```python
from langchain_neo4j import GraphCypherQAChain

graph.refresh_schema()
qa = GraphCypherQAChain.from_llm(
    llm=llm, graph=graph, verbose=True, allow_dangerous_requests=True,
)

print(qa.invoke({"query": "漢斯·季默配樂的電影，分別由誰執導？"})["result"])
# 這是一個跨文件的多跳問題，純向量 RAG 很難答對（見 Part 4）
```

**POC 解決了什麼**：證明「LLM 抽取 → 圖 → 問答」這條路在你的領域走得通。**還剩什麼問題**：消歧粗糙（「諾蘭」「克里斯多福·諾蘭」可能變兩個節點）、沒有錯誤處理、沒有評估、抽取成本未控管。

---

## 三、Phase 2：MVP — 團隊能安心運維（10～200 份文件／天）

POC 的捷徑現在會反咬。Phase 2 要補上三件事：**消歧、批次處理、評估**。

```
┌────────────────────────────────────────────────────────────────┐
│                      Phase 2（MVP）架構                           │
│                                                                  │
│  文件來源 ──▶ 切塊 ──▶ LLM 抽取 ──▶ 實體消歧 ──▶ MERGE 寫入        │
│   (S3/DB)        │        │           │                          │
│                  │        │           ▼                          │
│                  │        │    ┌──────────────┐                  │
│                  │        │    │ 別名→權威ID    │ (Part 2 的對齊)  │
│                  │        │    │ 對齊表/向量比對 │                  │
│                  │        ▼    └──────────────┘                  │
│                  │   ┌──────────────┐                            │
│                  │   │ 抽取結果驗證    │ (schema 檢查、信心過濾)    │
│                  │   └──────────────┘                            │
│                  ▼                                               │
│           ┌──────────────┐        ┌──────────────────┐           │
│           │  Neo4j (持久化) │◀──────│ 評估集：抽取準確率   │           │
│           └──────────────┘        └──────────────────┘           │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 實體消歧：把別名收斂

最務實的做法是「向量相似 + 人工/規則確認」：對新抽到的實體，算它和既有節點名稱的 embedding 相似度，超過門檻就視為同一個。

```python
from langchain_openai import OpenAIEmbeddings
import numpy as np

emb = OpenAIEmbeddings()

def resolve_entity(name: str, existing: list[str], threshold=0.92) -> str:
    """回傳應該對齊到的既有實體；沒有夠相似的就回傳自己（新節點）。"""
    if not existing:
        return name
    vecs = emb.embed_documents([name] + existing)
    q, others = np.array(vecs[0]), np.array(vecs[1:])
    sims = others @ q / (np.linalg.norm(others, axis=1) * np.linalg.norm(q))
    best = int(sims.argmax())
    return existing[best] if sims[best] >= threshold else name
```

> 生產級會再加「型別必須相同」「上下文消歧」等條件。記住 [Part 2](/posts/knowledge-graph-part2-construction-zh/) 的鐵律：**消歧做不好，圖就是一團糊。**

### 3.2 抽取評估：別讓品質默默腐爛

挑 20～50 段文字手動標出「正確的三元組」當黃金集（golden set），每次調整 prompt 或換模型就跑一次，算精確率（precision）/召回率（recall）：

```python
def eval_extraction(predicted: set, gold: set) -> dict:
    tp = len(predicted & gold)
    precision = tp / len(predicted) if predicted else 0
    recall    = tp / len(gold) if gold else 0
    f1 = 2*precision*recall/(precision+recall) if (precision+recall) else 0
    return {"precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3)}

# 把它接進 CI：F1 低於門檻（例如 0.75）就擋下這次的 prompt/模型變更
```

**MVP 解決了什麼**：品質可量化、別名會收斂、團隊敢往生產推。**還剩什麼問題**：抽取成本隨文件量線性上升、大圖查詢延遲、全域性問題還沒解。

---

## 四、Phase 3：Scale — 企業級（200K+ 文件／百萬實體）

```
┌────────────────────────────────────────────────────────────────┐
│                      Phase 3（Scale）架構                         │
│                                                                  │
│  文件串流 ──▶ 佇列(Kafka) ──▶ 抽取 worker 池(可水平擴展)            │
│                                   │                              │
│        ┌──────────────────────────┼───────────────────┐         │
│        ▼                          ▼                    ▼         │
│  ┌───────────┐          ┌──────────────┐      ┌──────────────┐   │
│  │ 小模型抽取  │          │ 大模型抽取     │      │ 社群偵測+摘要  │   │
│  │ (便宜/量大) │          │ (難案例/校驗)  │      │ (全域問題)     │   │
│  └─────┬─────┘          └──────┬───────┘      └──────┬───────┘   │
│        └─────────┬─────────────┘                     │           │
│                  ▼                                   ▼           │
│        ┌──────────────────┐              ┌────────────────────┐  │
│        │ Neo4j 叢集 (分片)   │◀────────────│ 社群摘要快取(全域RAG) │  │
│        └──────────────────┘              └────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

Phase 3 的三個核心優化：

**1. 成本分層（model routing）**：大量、簡單的文件用便宜小模型抽取；只有失敗或低信心的「難案例」升級到大模型。可省下 60～80% 抽取成本。

```python
def extract_with_routing(text: str):
    cheap = extract(text, model="gpt-4o-mini")
    if cheap.confidence >= 0.8 and cheap.triples:
        return cheap                      # 多數情況走便宜路徑
    return extract(text, model="gpt-4o")  # 難案例才升級
```

**2. 社群偵測 + 摘要（解全域問題）**：用圖演算法（Leiden / Louvain）把圖分群，每群用 LLM 生成摘要。回答「整體趨勢」這類問題時，改用摘要而非單一節點——這正是 [Part 4](/posts/knowledge-graph-part4-llm-graphrag-zh/) 提到的微軟 GraphRAG 範式。

```cypher
// Neo4j GDS：跑社群偵測，把節點分群
CALL gds.leiden.write('myGraph', { writeProperty: 'community' })
YIELD communityCount, modularity;
// 之後對每個 community 的子圖，用 LLM 生成一段摘要存起來
```

**3. 圖叢集與快取**：Neo4j 叢集分片、常見查詢結果快取、增量更新（只重抽變動的文件）。

---

## 五、為什麼選 X 不選 Y（本專案的關鍵決策）

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|------|------------|--------------|---------|
| LLM 抽取 vs 規則抽取 | 零標註、跨領域、彈性高 | 規則：覆蓋率低、難維護 | 領域極窄且要 100% 精確 → 規則 |
| 限定本體 vs 開放抽取 | 圖一致、關係不發散 | 開放：同義關係碎裂 | 探索期、不知有哪些關係 → 先開放 |
| Neo4j vs RDF triplestore | 工程友善、Cypher 直覺 | RDF：學習曲線陡 | 需嚴謹 OWL 推理/跨機構 → RDF |
| GraphRAG vs 純向量 RAG | 多跳、全域、可解釋 | 純向量：建置便宜 | 95% 是單跳事實 → 純向量 |
| 小模型分層 vs 全用大模型 | 省 60-80% 成本 | 全大模型：貴 | 文件量小、預算充足 → 全大模型 |

---

## 六、系統效應：完整專案前後對比

以「企業內部 1 萬份技術文件問答」為例：

| 指標 | 傳統做法（純向量 RAG + 人工建圖） | 本專案（LLM 自動建圖 + GraphRAG） |
|------|-----------------------------------|-----------------------------------|
| 建圖時間（1 萬份文件） | 人工數月 | 自動數小時～數天 |
| 多跳問題正確率 | ~40% | ~80% |
| 全域趨勢問題 | 幾乎無法 | 可回答（社群摘要） |
| 答案可解釋（附路徑） | 低 | 高 |
| 幻覺率 | ~15% | ~5% |
| 維運：新增文件 | 需人工重建關係 | 增量自動抽取 |
| 抽取成本（分層後） | — | 可控（省 60-80%） |

---

## 七、完整最小可跑骨架（彙整）

把前面拼起來，這是一個你今天就能跑的最小完整版：

```python
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.documents import Document

# 0. 連線與模型
llm = ChatOpenAI(model="gpt-4o", temperature=0)
graph = Neo4jGraph(url="bolt://localhost:7687",
                   username="neo4j", password="password123")

# 1. 文件（實務換成你的 PDF/網頁 loader）
docs = [Document(page_content="...你的文件內容...")]

# 2. LLM 抽取 → 圖（限定本體提升一致性）
transformer = LLMGraphTransformer(
    llm=llm,
    allowed_nodes=["Person", "Movie", "Franchise", "Composer"],
    allowed_relationships=["DIRECTED", "ACTED_IN", "COMPOSED_FOR", "PART_OF"],
)
graph_documents = transformer.convert_to_graph_documents(docs)

# 3. 寫入（MERGE 去重 + 保留來源）
graph.add_graph_documents(graph_documents,
                          baseEntityLabel=True, include_source=True)

# 4. GraphRAG 問答（生產請改唯讀帳號，見 Part 4 第七節）
graph.refresh_schema()
qa = GraphCypherQAChain.from_llm(llm=llm, graph=graph,
                                 verbose=True, allow_dangerous_requests=True)
print(qa.invoke({"query": "你的多跳問題..."})["result"])
```

---

## 八、系列總結：你現在能做什麼

走完五篇，你應該已經能夠：

1. **解釋** 知識圖譜是什麼、三元組與本體、RDF 與屬性圖的差異（Part 1）。
2. **建構** 從文字經 NER、消歧、關係抽取到 Neo4j 的完整管線（Part 2）。
3. **選型** 在知識圖譜、關聯式、向量、文件資料庫之間做出有依據的判斷（Part 3）。
4. **整合** 用 GraphRAG 把知識圖譜接到 LLM，做多跳推理、降低幻覺（Part 4）。
5. **落地** 用 LLM 自動建圖，並按 POC → MVP → Scale 三階段演進（Part 5）。

知識圖譜不是要取代向量資料庫或 LLM，而是補上它們最缺的那一塊——**精確、可解釋、可推理的關係結構**。在「LLM 什麼都能答、但不保證對」的時代，這塊拼圖只會越來越重要。

動手把這個骨架跑起來，丟進你自己的文件，然後問它一個多跳問題——那一刻你會真正理解，為什麼說知識圖譜是 LLM 的最佳拍檔。

---

## 系列導航

← [Part 4：知識圖譜 + LLM — GraphRAG 與多跳推理](/posts/knowledge-graph-part4-llm-graphrag-zh/)

← [回到 Part 1：核心概念、三元組與語意網路](/posts/knowledge-graph-part1-fundamentals-zh/)

---

*本文為「Knowledge Graph 知識圖譜」系列第 5 篇（完結），共 5 篇。從核心概念到端到端實作，恭喜你走完整個系列！*
