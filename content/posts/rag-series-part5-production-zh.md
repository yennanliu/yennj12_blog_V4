---
title: "RAG 完全指南（五）：生產級評估、GraphRAG 與 Agentic RAG"
date: 2026-05-20T09:00:00+08:00
draft: false
weight: 5
description: "RAG 系列終章：如何用 RAGAS 框架量化評估 RAG 品質、GraphRAG 如何用知識圖譜突破向量搜尋的限制，以及 Agentic RAG 如何讓 AI Agent 主動決策何時搜尋、搜尋什麼。"
categories: ["AI", "Engineering", "all"]
tags: ["RAG", "RAGAS", "GraphRAG", "Agentic RAG", "LangGraph", "Evaluation", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "35 min"
---

## 前言

你的 RAG 系統「感覺」不錯，但你能量化它有多好嗎？

這是生產環境中最常見的盲區：工程師花大量時間優化 Chunking、調整 Reranker，卻沒有客觀的指標來驗證改動是否真的有效。

這篇是系列的最後一篇，涵蓋三個主題：

1. **RAG 評估（RAGAS）**：如何量化 RAG 品質
2. **GraphRAG**：當向量搜尋不夠用時的替代方案
3. **Agentic RAG**：RAG + Agent，讓 AI 自己決定如何搜尋

---

## Part 1：RAG 評估——RAGAS 框架

### 為什麼評估很難？

RAG 的輸出是自然語言，沒有標準答案可以直接比對。  
「這個答案好不好」，需要從多個維度判斷。

### RAGAS 的四個核心指標

**RAGAS（RAG Assessment）** 是目前最流行的 RAG 評估框架，定義了四個指標：

#### 1. Faithfulness（忠實度）

> 答案是否只根據 context，沒有幻覺？

```
計算方式：
Step 1: 把答案分解成一組陳述句（claims）
Step 2: 對每個陳述，判斷 context 是否支持它
Step 3: Faithfulness = 有 context 支持的陳述數 / 總陳述數

理想值：接近 1.0
```

#### 2. Answer Relevancy（答案相關性）

> 答案是否真的回答了問題？

```
計算方式：
Step 1: 讓 LLM 根據答案生成 N 個「可能的問題」
Step 2: 計算這些問題與原始問題的向量相似度
Step 3: Answer Relevancy = 平均相似度

理想值：接近 1.0
特別之處：如果答案跑題（回答了別的問題），分數會很低
```

#### 3. Context Precision（上下文精準度）

> 檢索到的 context 中，有多少比例是真的相關的？

```
計算方式：
對每個 context chunk，判斷它是否對生成答案有貢獻
Context Precision = 有貢獻的 chunk 數 / 總 chunk 數

理想值：接近 1.0
代表意義：如果你取回 10 個 chunk，只有 3 個有用，分數就是 0.3
```

#### 4. Context Recall（上下文召回率）

> 知識庫中的相關資訊，有多少被成功召回？

```
需要 ground truth answer（標準答案）
計算方式：
Step 1: 把 ground truth 分解成陳述句
Step 2: 對每個陳述，判斷 context 中是否有支持
Step 3: Context Recall = 有支持的陳述數 / 總陳述數

理想值：接近 1.0
代表意義：如果標準答案有 5 個重點，context 只包含 3 個，分數是 0.6
```

### 用 RAGAS 評估你的 RAG

```python
# pip install ragas langchain-openai
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from datasets import Dataset

# 準備評估資料集
# 格式：問題、生成答案、檢索到的 context、標準答案（optional）
eval_data = {
    "question": [
        "Python 的 GIL 是什麼？",
        "asyncio 的事件迴圈如何工作？",
        "如何選擇向量資料庫？",
    ],
    "answer": [
        # 你的 RAG 系統生成的答案
        "GIL（全域解釋鎖）是 Python 的一個機制，確保同一時間只有一個執行緒執行 Python 位元組碼...",
        "asyncio 的事件迴圈是一個單執行緒的調度器，透過 selector 監控 I/O 事件...",
        "選擇向量資料庫需要考慮資料規模、是否需要自託管、Filter 功能需求...",
    ],
    "contexts": [
        # 對應的 retrieved chunks（list of list）
        ["Python GIL 全域解釋鎖，限制多執行緒...", "CPython 實作中 GIL 的影響..."],
        ["asyncio 事件迴圈透過 selector 監控..."],
        ["ChromaDB 適合開發環境...", "Pinecone 是雲端託管的向量 DB...", "Qdrant 支援自託管..."],
    ],
    "ground_truth": [
        # 標準答案（用於 context_recall）
        "GIL 是 Python 的全域解釋鎖，同時間只有一個執行緒可以執行 Python 位元組碼，影響多執行緒 CPU 密集型任務。",
        "asyncio 事件迴圈是單執行緒的異步調度器，使用 selector 監控 I/O 事件，調度 coroutine 執行。",
        "向量資料庫選型需考慮：資料規模、自託管需求、Filter 複雜度、成本。小規模用 Chroma，生產環境用 Qdrant 或 Pinecone。",
    ],
}

dataset = Dataset.from_dict(eval_data)

# 設定 LLM 和 Embedding（RAGAS 用它們來做評估）
llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", temperature=0))
emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model="text-embedding-3-small"))

# 執行評估
result = evaluate(
    dataset=dataset,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    llm=llm,
    embeddings=emb,
)

# 輸出結果
print(result.to_pandas()[["faithfulness", "answer_relevancy", "context_precision", "context_recall"]])
print(f"\n平均分數：")
print(f"  Faithfulness:      {result['faithfulness']:.3f}")
print(f"  Answer Relevancy:  {result['answer_relevancy']:.3f}")
print(f"  Context Precision: {result['context_precision']:.3f}")
print(f"  Context Recall:    {result['context_recall']:.3f}")
```

### 用指標診斷問題

```
Faithfulness 低  → LLM 有幻覺 → 加強 System Prompt、用 Self-RAG
Answer Relevancy 低 → 答案跑題 → 改善 Prompt 設計、問題分解
Context Precision 低 → 取回太多不相關的 chunk → 加 Reranker、調高相似度閾值
Context Recall 低 → 相關資訊沒被找到 → 改善 Chunking、加 Hybrid Search
```

### 建立自動化評估流程

```python
import json
from datetime import datetime
from pathlib import Path


def evaluate_and_log(rag_pipeline, test_cases: list[dict], output_dir: str = "./eval_logs"):
    """對 RAG pipeline 做自動評估並記錄結果"""
    Path(output_dir).mkdir(exist_ok=True)

    results = []
    for case in test_cases:
        question    = case["question"]
        ground_truth = case.get("ground_truth", "")

        # 執行 RAG
        output  = rag_pipeline(question)
        answer   = output["answer"]
        contexts = output["contexts"]

        results.append({
            "question":     question,
            "answer":       answer,
            "contexts":     contexts,
            "ground_truth": ground_truth,
        })

    # 用 RAGAS 評估
    dataset = Dataset.from_list(results)
    scores  = evaluate(dataset=dataset, metrics=[faithfulness, answer_relevancy])

    # 記錄到檔案（版本追蹤）
    log = {
        "timestamp":  datetime.now().isoformat(),
        "scores":     scores.to_pandas().to_dict(),
        "num_cases":  len(test_cases),
    }
    log_path = Path(output_dir) / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    print(f"📊 評估完成，結果存至 {log_path}")
    return scores
```

---

## Part 2：GraphRAG

### 向量搜尋的根本限制

向量搜尋擅長找「語意相似的文件」，但對需要**跨文件推理**的問題很弱：

```
問題：「A 公司的 CEO 和 B 公司的 CTO 有什麼共同的工作經歷？」

向量搜尋：
→ 找到關於 A 公司 CEO 的文章
→ 找到關於 B 公司 CTO 的文章
→ 但無法連接兩者之間的關係

GraphRAG：
→ 知識圖譜中有：
  [A CEO] --曾任職於--> [Google]
  [B CTO] --曾任職於--> [Google]
→ 直接推導：兩人都在 Google 工作過
```

### GraphRAG 的核心架構

```
文件
 ↓
[實體提取] → 找出文件中的實體（人、公司、概念）
 ↓
[關係提取] → 找出實體間的關係（任職、合作、隸屬）
 ↓
[建立知識圖譜] → 儲存在圖資料庫（Neo4j、NetworkX）
 ↓
查詢時：
  向量搜尋（找相關節點） + 圖遍歷（沿關係推理）
```

### 用 Python 建立簡易 GraphRAG

```python
# pip install networkx openai
import networkx as nx
import openai
import json

client = openai.OpenAI(api_key="your-api-key")


def extract_entities_and_relations(text: str) -> dict:
    """用 LLM 從文字中提取實體和關係"""
    prompt = f"""從以下文字中提取實體和關係，以 JSON 格式輸出。

格式範例：
{{
  "entities": ["Alice", "Google", "Bob"],
  "relations": [
    {{"from": "Alice", "relation": "任職於", "to": "Google"}},
    {{"from": "Bob",   "relation": "任職於", "to": "Google"}}
  ]
}}

文字：{text}

JSON（只輸出 JSON，不要其他內容）："""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


class SimpleGraphRAG:
    def __init__(self):
        self.graph   = nx.DiGraph()
        self.doc_map : dict[str, str] = {}  # entity → 原始文字片段

    def add_document(self, text: str) -> None:
        """從文字中提取實體關係，加入知識圖譜"""
        extracted = extract_entities_and_relations(text)

        for entity in extracted.get("entities", []):
            self.graph.add_node(entity)
            self.doc_map[entity] = text  # 記錄來源文字

        for rel in extracted.get("relations", []):
            self.graph.add_edge(
                rel["from"], rel["to"],
                relation=rel["relation"],
            )
        print(f"  ✅ 加入 {len(extracted['entities'])} 個實體，{len(extracted['relations'])} 條關係")

    def find_connected_entities(self, entity: str, hops: int = 2) -> list[str]:
        """找出距離 entity N hop 以內的所有相關實體"""
        if entity not in self.graph:
            return []
        neighbors = set()
        frontier  = {entity}
        for _ in range(hops):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(self.graph.successors(node))
                next_frontier.update(self.graph.predecessors(node))
            neighbors.update(next_frontier)
            frontier = next_frontier
        return list(neighbors - {entity})

    def query(self, question: str) -> str:
        """GraphRAG 查詢：找實體 → 圖遍歷 → 收集 context → LLM 生成"""
        # Step 1: 從問題中找出實體
        extract_prompt = f"""從以下問題中提取所有實體名稱（人名、公司名、產品名等）。
以 JSON 陣列格式輸出，例如：["Alice", "Google"]

問題：{question}
實體 JSON："""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0,
        )
        try:
            query_entities = json.loads(resp.choices[0].message.content)
        except Exception:
            query_entities = []

        # Step 2: 圖遍歷，收集相關實體的文字
        relevant_texts = set()
        for entity in query_entities:
            if entity in self.doc_map:
                relevant_texts.add(self.doc_map[entity])
            for connected in self.find_connected_entities(entity, hops=2):
                if connected in self.doc_map:
                    relevant_texts.add(self.doc_map[connected])

        # Step 3: 也加入圖譜中的關係路徑
        graph_facts = []
        for u, v, data in self.graph.edges(data=True):
            for entity in query_entities:
                if entity in [u, v]:
                    graph_facts.append(f"{u} --[{data['relation']}]--> {v}")

        context_parts = list(relevant_texts)
        if graph_facts:
            context_parts.append("【知識圖譜關係】\n" + "\n".join(graph_facts))

        if not context_parts:
            return "知識庫中找不到相關資訊。"

        context = "\n\n---\n\n".join(context_parts)

        prompt = f"""根據以下知識庫資料（包含文件和關係圖）回答問題。

{context}

問題：{question}"""

        return client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        ).choices[0].message.content


# 使用範例
graph_rag = SimpleGraphRAG()

documents = [
    "Alice 是 OpenAI 的首席研究員，曾在 Google Brain 擔任 AI 研究員，專注於語言模型研究。",
    "Bob 是 Anthropic 的 CTO，在創辦 Anthropic 之前曾在 Google Brain 擔任資深工程師。",
    "Charlie 是 DeepMind 的研究總監，與 Alice 共同發表過多篇關於 Transformer 架構的論文。",
]

for doc in documents:
    graph_rag.add_document(doc)

answer = graph_rag.query("Alice 和 Bob 有什麼共同的工作背景？")
print(answer)
```

**GraphRAG vs 向量 RAG 適用場景對比：**

| 問題類型 | 向量 RAG | GraphRAG |
|---------|---------|---------|
| 「X 是什麼？」 | ✅ 直接查詢 | ✅ |
| 「A 和 B 的關係？」 | ❌ 難以跨文件 | ✅ 圖遍歷 |
| 「誰跟 X 有關聯？」 | ❌ | ✅ 鄰居搜尋 |
| 「推理鏈：A → B → C」 | ❌ | ✅ 路徑搜尋 |
| 大規模非結構化文字 | ✅ | 需要額外抽取 |

**最佳使用場景**：組織架構分析、藥物交互作用、學術引用網路、知識密集型問答

---

## Part 3：Agentic RAG

### 從被動到主動

傳統 RAG 是**被動的**：接到問題 → 搜尋一次 → 生成答案。

**Agentic RAG** 讓 AI Agent 自主決策：

- 是否需要搜尋？
- 要搜尋什麼？
- 搜尋結果夠了嗎？還是要再搜一次？
- 要不要對答案做驗證？

```
使用者問題
    ↓
Agent 思考：「這個問題需要什麼資訊？」
    ↓
Agent 決定：「先搜尋 X」
    ↓
[工具呼叫] search(X) → 結果 1
    ↓
Agent 思考：「結果不夠完整，還需要 Y」
    ↓
[工具呼叫] search(Y) → 結果 2
    ↓
Agent 思考：「資料足夠了，可以回答」
    ↓
生成最終答案
```

### 用 LangGraph 實作 Agentic RAG

```python
# pip install langgraph langchain-openai
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import operator

# 定義 State
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    search_count: int  # 追蹤搜尋次數，防止無限迴圈


# 定義工具（Agent 可以呼叫的函式）
@tool
def search_knowledge_base(query: str) -> str:
    """搜尋公司知識庫，找出與 query 相關的資訊"""
    # 實際上你會呼叫你的 RAG retriever
    # 這裡用 mock 資料示意
    mock_results = {
        "Python asyncio": "asyncio 是 Python 的標準非同步框架，使用事件迴圈調度協程。",
        "API 延遲優化": "使用連線池、非同步 I/O、快取等方式可以降低 API 延遲。",
        "Redis": "Redis 是記憶體內的 key-value 資料庫，常用於快取和訊息佇列。",
    }
    for key, value in mock_results.items():
        if key.lower() in query.lower():
            return value
    return f"找不到關於「{query}」的相關資訊。"


@tool
def search_web(query: str) -> str:
    """搜尋網路上的最新資訊（當知識庫沒有答案時使用）"""
    # 實際上會呼叫搜尋 API（如 Tavily、Serper）
    return f"（網路搜尋結果）關於 {query} 的最新資訊：..."


tools = [search_knowledge_base, search_web]
tool_node = ToolNode(tools)

# 設定 LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0).bind_tools(tools)


def agent_node(state: AgentState) -> dict:
    """Agent 決策節點：思考下一步要做什麼"""
    messages = state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """決定是否繼續搜尋或結束"""
    last_message = state["messages"][-1]

    # 如果 LLM 決定呼叫工具，繼續
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if state["search_count"] >= 5:  # 最多 5 次工具呼叫
            return "end"
        return "tools"

    # LLM 沒有呼叫工具，表示它準備好回答了
    return "end"


def increment_search_count(state: AgentState) -> dict:
    """工具呼叫後增加計數"""
    return {"search_count": state["search_count"] + 1}


# 建立 Graph
graph = StateGraph(AgentState)

graph.add_node("agent",   agent_node)
graph.add_node("tools",   tool_node)
graph.add_node("counter", increment_search_count)

graph.add_edge(START,     "agent")
graph.add_edge("tools",   "counter")
graph.add_edge("counter", "agent")

graph.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "end": END},
)

agentic_rag = graph.compile()


def run_agentic_rag(question: str) -> str:
    """執行 Agentic RAG"""
    system_prompt = """你是一個知識庫問答助手。
回答問題時，先使用 search_knowledge_base 搜尋內部知識庫。
如果內部知識庫沒有足夠資訊，再使用 search_web 搜尋網路。
確認有足夠資訊後，才提供完整的回答。"""

    initial_state: AgentState = {
        "messages": [
            HumanMessage(content=system_prompt + f"\n\n問題：{question}"),
        ],
        "search_count": 0,
    }

    final_state = agentic_rag.invoke(initial_state)
    return final_state["messages"][-1].content


# 使用範例
answer = run_agentic_rag("如何用 Python asyncio 搭配 Redis 做高效能的非同步快取？")
print(answer)
```

### Agentic RAG 的核心優勢

```
場景 1：知識庫夠用
  使用者：「Python 的 GIL 是什麼？」
  Agent：search_knowledge_base("Python GIL") → 找到答案 → 直接回答

場景 2：需要多次搜尋
  使用者：「比較 Redis 和 Memcached，哪個適合用在 asyncio 程式？」
  Agent：
    1. search_knowledge_base("Redis") → 找到 Redis 資訊
    2. search_knowledge_base("Memcached") → 找到 Memcached 資訊
    3. search_knowledge_base("asyncio 快取") → 找到整合建議
    4. 綜合三次結果回答

場景 3：知識庫沒有，轉向網路
  使用者：「GPT-4.1 有哪些新功能？」（知識庫太舊）
  Agent：
    1. search_knowledge_base("GPT-4.1") → 無結果
    2. search_web("GPT-4.1 features 2025") → 找到最新資訊
    3. 根據網路搜尋結果回答
```

**優點**：靈活應對各種問題類型；可以多輪搜尋直到資訊充足；容易擴充新工具  
**缺點**：延遲不可預測（可能多次迭代）；成本隨迭代次數增加；需要設計防止無限迴圈  
**最佳使用場景**：複雜研究性問題、需要整合多個資料源、問題類型多樣的生產系統

---

## 完整技術選型路線圖

```
你的 RAG 問題是什麼？
│
├── 搜尋找不到正確文件
│   ├── 術語/關鍵字問題 → Hybrid Search (BM25 + 向量)
│   ├── 問題措辭問題    → HyDE 或 Multi-Query
│   └── 跨文件推理問題  → GraphRAG
│
├── 找到了但排名不對
│   └── 加 Cross-Encoder Reranker
│
├── 找到了但 context 有噪音
│   └── Context Compression
│
├── 問題本身難以直接搜尋
│   ├── 具體問題 → Step-Back Prompting
│   └── 複雜多跳問題 → Query Decomposition
│
├── 答案有幻覺
│   └── Self-RAG（自我反思）
│
├── 需要處理多樣化的複雜問題
│   └── Agentic RAG（LangGraph）
│
└── 不知道哪裡出問題
    └── 先用 RAGAS 評估，找出指標最差的環節
```

---

## RAG 系統設計的黃金法則

在五篇文章的最後，整理幾個核心原則：

1. **先建立評估，再優化**：沒有 RAGAS 評分，你不知道優化有沒有效果
2. **Chunking 策略比模型更重要**：在換更強的 LLM 之前，先把 Chunking 做好
3. **Reranker 幾乎總是值得加**：成本低（用本地模型）、效果顯著
4. **不要過度工程化**：Naive RAG + 好的 Chunking 在很多場景已經夠用
5. **GraphRAG 和 Agentic RAG 是進階武器**：需要清楚的問題驅動，不要為了用而用

---

## 系列總結

| 篇章 | 核心主題 | 關鍵技術 |
|------|---------|---------|
| 第一篇 | RAG 基礎 | Embedding、向量搜尋、Naive RAG |
| 第二篇 | 資料基礎建設 | Chunking 策略、向量 DB 選型 |
| 第三篇 | 進階搜尋 | Hybrid Search、HyDE、Multi-Query、Reranker |
| 第四篇 | 查詢與壓縮 | Step-Back、Self-RAG、Context Compression |
| 第五篇 | 生產與前沿 | RAGAS 評估、GraphRAG、Agentic RAG |

希望這個系列能幫助你從零建立、優化並評估自己的 RAG 系統。  
RAG 的技術仍在快速演進，但這五篇涵蓋的核心原理和思路，在可見的未來都會持續適用。

---

**系列導覽**

- [第一篇](/posts/rag-series-part1-foundations-zh/)：基礎概念與第一個 RAG 系統
- [第二篇](/posts/rag-series-part2-chunking-vectordb-zh/)：Chunking 策略與向量資料庫選型
- [第三篇](/posts/rag-series-part3-advanced-retrieval-zh/)：進階檢索技術（混合搜尋、HyDE、Multi-Query、Reranker）
- [第四篇](/posts/rag-series-part4-optimization-zh/)：查詢優化與 Context 壓縮
- **第五篇（本篇）**：生產級 RAG 評估與 Agentic RAG
