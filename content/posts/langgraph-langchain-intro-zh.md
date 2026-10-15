---
title: "LangGraph + LangChain 完全入門指南：從基礎到生產"
date: 2026-04-11T10:00:00+08:00
lastmod: 2026-10-15T09:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "ai"]
tags: ["LangChain", "LangGraph", "AI", "Agent", "工作流", "介紹"]
description: "把 LangGraph 看成「帶 checkpointer 的狀態機」，先學會 State 與 reducer、條件邊、interrupt/Command 人工介入、持久化這四件事，就能讀懂任何 LangGraph 程式並知道何時不該用它。"
readTime: "8 min"
---

> 多數人第一次用 LangGraph，是把一條 LangChain chain 拆成幾個節點、接成一條直線，然後覺得「這跟 `|` 串起來有什麼不同？」
> 沒有不同——直線的圖不需要 LangGraph。
> 它真正解決的是 chain 做不到的三件事：**迴圈**（Agent 要重試）、**暫停**（要等人批准）、**接回來**（程序重啟後從上次的地方繼續）。
> 這三件事都建立在同一個機制上：每走一步，就把狀態存一次。

**LangGraph 是一台帶 checkpointer 的狀態機。** 圖（graph）定義狀態怎麼轉移，checkpointer 在每個節點跑完後把狀態寫下來；暫停、重試、人工介入、恢復執行，全都是「讀最後一個 checkpoint、改一改、再往下走」。看懂這一句，剩下的 API 就只是細節。

這篇是 ≤ 350 行的上手文，只講最值得先學的四件事：**State 與 reducer、條件邊、`interrupt`/`Command` 人工介入、持久化**。每一節末尾都指向寫得更深的文章；完整的客服工單後端在〈[LangGraph 客服工單後端：從狀態設計到可恢復的執行](/posts/langgraph-ai-customer-ticket-system-zh/)〉。

> 本文程式碼對照 LangGraph 1.x / LangChain 1.x 的公開 API 撰寫，為示意用途、未在本文內執行。模型 ID 一律從環境變數讀，避免寫死已退役的型號。

## 為什麼是狀態機，不是 chain

LangChain 的 chain（LCEL，`prompt | model | parser`）是一條**有向無環**的管線：資料從左流到右，不回頭。這對「摘要一段文字」夠用，對「Agent 呼叫工具、看結果、決定再呼叫一次」不夠——那是一個迴圈，而且迴圈次數在執行前不知道。

LangGraph 把程式改成一張圖：節點是普通的 Python 函式，邊決定下一個節點，**狀態**是節點之間唯一的溝通管道。下面這張圖是一個最小的工具呼叫 Agent，注意 `tools → agent` 那條回頭的邊，它就是 chain 畫不出來的東西：

```
            ┌──────────────────────────────────────────┐
            │                                          │
  START ──▶ │  agent  │ ──(有 tool_calls)──▶ │  tools  │
            │ (LLM)   │                      │(執行工具)│
            └────┬────┘                      └────┬────┘
                 │ (沒有 tool_calls)                │
                 ▼                                  │
                END   ◀──── messages 累積在 State ◀──┘
```

每個節點讀 state、回傳「要更新的欄位」；每一輪 `agent → tools → agent`，checkpointer 都會存一個版本的 state。這張圖同時也是「反思迴圈」的骨架：Agent 自評、不滿意就再來一輪，迴圈何時收斂、怎麼設上限，是圖結構的問題而不是 prompt 的問題。

**深入請看 →** 狀態機、DAG 與反思迴圈的收斂條件：[FDE core topic - State Machine & DAG](/posts/fde-core-concept-3-state-machine-dag-zh/)

## 一、State 與 reducer：節點回傳的是「差異」，不是整份狀態

**直覺**：把 state 想成一張共用的白板。每個節點不是擦掉重寫，而是遞一張便利貼說「這幾格改成這樣」；**reducer** 決定便利貼怎麼貼上去——覆蓋、還是接在後面。

**機制**：state 用 `TypedDict` 宣告。沒有標註 reducer 的欄位，新值覆蓋舊值；用 `Annotated[list, operator.add]` 標註的欄位，新值會接在舊值後面；`add_messages` 是訊息列表專用的 reducer，會依訊息 `id` 去重與更新，而不是盲目追加。

```python
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # 依 id 合併
    events: Annotated[list[str], operator.add]  # 永遠追加
    category: str                              # 覆蓋

def classify(state: State) -> dict:
    text = state["messages"][-1].content
    cat = "billing" if "發票" in text else "technical"
    return {"category": cat, "events": [f"classified:{cat}"]}  # 只回傳差異

builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_edge(START, "classify")
builder.add_edge("classify", END)
graph = builder.compile()

result = graph.invoke({"messages": [("user", "我的發票金額不對")]})
print(result["category"], result["events"])   # dict，不是物件
```

**兩個最常踩的坑**：

1. **`invoke()` 回傳的永遠是 `dict`**，不管 state 宣告成 `TypedDict`、`dataclass` 還是 Pydantic 模型。寫 `result.category` 會得到 `AttributeError`；要寫 `result["category"]`。如果你真的想要物件，就在呼叫端 `TicketState(**result)` 轉一次，並說明為什麼。
2. **節點回傳整份 state 不會報錯，但會讓 reducer 失效**：把 `events` 原封不動回傳，`operator.add` 會把它再接一次，列表長度翻倍。回傳差異是慣例，不是風格偏好。

**數字**：state 每個 checkpoint 都會完整序列化。`messages` 若不修剪，一個跑了 30 輪、每輪帶 4 KB 工具結果的 Agent，單一 thread 的 checkpoint 總量會超過 100 KB × 30 版本；用 `add_messages` 配合 `RemoveMessage` 或在節點裡截斷，是上線前就要做的事。

**深入請看 →** 工單系統的完整 state 設計（輸入／推導／控制三類欄位）：[LangGraph 客服工單後端](/posts/langgraph-ai-customer-ticket-system-zh/)

## 二、條件邊：路由邏輯是一個回傳字串的函式

**直覺**：固定邊是鐵軌，條件邊是轉轍器。轉轍器的邏輯是一個普通函式，讀 state、回傳下一站的名字。

**機制**：`add_conditional_edges(來源節點, 路由函式, 對照表)`。路由函式回傳的字串經對照表翻成節點名；對照表的值可以是 `END`。路由函式**不能更新 state**——它的回傳值只是路名，寫 `state["retry"] += 1` 不會被存起來，這是重試迴圈失控最常見的原因。

```python
from typing import Literal

def route_after_classify(state: State) -> Literal["billing", "technical"]:
    return "billing" if state["category"] == "billing" else "technical"

builder.add_conditional_edges(
    "classify",
    route_after_classify,
    {"billing": "billing_agent", "technical": "tech_agent"},
)
```

**另一種寫法：`Command`**。當「決定去哪」和「要更新什麼」是同一件事（例如：分類完直接寫入類別並跳去對應節點），讓節點回傳 `Command(goto=..., update=...)`，省掉一個路由函式。回傳型別標註 `Command[Literal[...]]` 讓 LangGraph 知道可能的目的地，畫圖與驗證都靠它：

```python
from langgraph.types import Command

def classify(state: State) -> Command[Literal["billing_agent", "tech_agent"]]:
    cat = "billing" if "發票" in state["messages"][-1].content else "technical"
    return Command(
        update={"category": cat},
        goto="billing_agent" if cat == "billing" else "tech_agent",
    )
```

**什麼時候用哪個**：路由邏輯純粹、不改 state → 條件邊，圖的拓樸一眼看得出來；路由與更新綁在一起、或要從子圖跳回父圖（`Command(graph=Command.PARENT)`）→ `Command`。兩者混用沒問題，但同一個節點不要既有條件邊又有無條件邊指向不同節點——那會讓兩個分支**同時**執行，不是二選一。

**限制**：條件邊只看目前 state，不看歷史。「連續三次路由到同一節點就升級」這類規則，要把計數器放進 state 由節點更新，路由函式只負責讀。

**深入請看 →** 可執行的 Agentic RAG：`bind_tools`、`ToolNode`、`tools_condition` 接成的完整圖：[RAG 完全指南（五）](/posts/rag-series-part5-production-zh/) 的 Part 3

## 三、人工介入：`interrupt` 暫停，`Command(resume=)` 接回

**直覺**：`interrupt()` 是在節點裡按下暫停鍵。圖把目前狀態存成 checkpoint 後**整個退出**——程序可以關掉、容器可以重啟；幾小時後人做了決定，用 `Command(resume=決定)` 再次 `invoke`，圖從同一個節點接著跑。

**機制**：

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

def escalate(state: State) -> dict:
    decision = interrupt({                      # 第一次執行到這裡：存檔、退出
        "ticket": state["messages"][-1].content,
        "question": "退款超過 5,000 元，是否核准？",
    })
    return {"events": [f"human:{decision['approve']}"]}  # 第二次執行才到這裡

# interrupt 需要 checkpointer
graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "ticket-42"}}

first = graph.invoke({"messages": [("user", "我要退 8,000 元")]}, config)
first["__interrupt__"][0].value   # → {"ticket": ..., "question": ...}

second = graph.invoke(Command(resume={"approve": True}), config)
```

**一定要知道的三件事**：

1. **恢復時整個節點會從頭重跑**，`interrupt()` 之前的程式碼會執行第二次。所以 `interrupt()` 之前不要放不可重複的副作用（寄信、扣款）；要嘛放到它之後，要嘛讓它冪等。
2. **沒有 checkpointer 就沒有 interrupt**。暫停的本質是「把 state 存起來然後退出」，沒地方存就做不到。
3. `thread_id` 是恢復的鑰匙。同一個 `thread_id` 才能接回同一條執行；換一個就是全新的工單。

下面是這個暫停／恢復循環在 checkpointer 眼中的樣子：

```
  invoke(input, thread=42)                  invoke(Command(resume=…), thread=42)
          │                                                     │
          ▼                                                     ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │ ckpt #1     │──▶│ ckpt #2     │──▶│ ckpt #3     │──▶│ ckpt #4     │
   │ after intake│   │ after       │   │ at interrupt│   │ after       │
   │             │   │ classify    │   │ next=escal. │   │ escalate    │
   └─────────────┘   └─────────────┘   └──────┬──────┘   └─────────────┘
                                              │
                          程序退出；幾小時後人做決定  ◀──────┘
                          （get_state(config).next == ("escalate",)）
```

**數字**：一次人工審核平均要等多久，決定你能不能用 `InMemorySaver`。等 30 秒內的批准、單一程序，記憶體夠用；等 4 小時、服務會重新部署，就必須是資料庫 checkpointer（下一節）。

**深入請看 →** 升級節點、審核佇列與 `/resume` API 的完整接法：[LangGraph 客服工單後端](/posts/langgraph-ai-customer-ticket-system-zh/)

## 四、持久化：從 `InMemorySaver` 到 `PostgresSaver`

**直覺**：checkpointer 是圖的存檔槽。`InMemorySaver` 存在程序記憶體裡，程序一關就沒了；`PostgresSaver` 存進資料庫，任何一台機器都能接著跑。

**機制**：兩者介面相同，差別只在建構方式。`PostgresSaver.from_conn_string()` 回傳的是一個 **context manager**，而且第一次使用前要呼叫 `.setup()` 建表——漏掉其中一個，不是連線沒開就是找不到資料表：

```python
# pip install langgraph-checkpoint-postgres
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@localhost:5432/tickets"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()                       # 建表；可重複呼叫
    graph = builder.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "ticket-42"}}
    graph.invoke({"messages": [("user", "發票開錯抬頭")]}, config)

    snapshot = graph.get_state(config)         # 最新 checkpoint
    snapshot.values["category"]                # state 內容
    snapshot.next                              # 下一個要跑的節點；() 代表已結束
    for s in graph.get_state_history(config):  # 由新到舊，每個節點一個版本
        print(s.config["configurable"]["checkpoint_id"], s.next)
```

在 FastAPI 這類長駐服務裡，`with` 區塊要包住整個應用生命週期（lifespan），而不是每個 request 開一次連線；非同步版本是 `AsyncPostgresSaver`，介面對稱。

**數字**：每個節點執行後寫一次 checkpoint，一個 6 節點的工單流程、一天 10 萬張工單，就是 60 萬筆 checkpoint 寫入；單筆 state 10–50 KB 時，一天約 6–30 GB。要嘛定期清掉已結束 thread 的歷史，要嘛只保留最後 N 個版本。

**限制**：checkpointer 存的是 LangGraph 的 state，不是你的業務資料庫。工單的最終狀態、客戶看得到的回覆，仍然要由節點明確寫進你自己的資料表；不要用 `get_state()` 當查詢 API。

**深入請看 →** checkpointer 在 FastAPI lifespan 裡的接法、`thread_id` 與工單 ID 的對應、歷史清理：[LangGraph 客服工單後端](/posts/langgraph-ai-customer-ticket-system-zh/)

## 不想自己畫圖：`create_agent`

多數「LLM + 幾個工具」的需求不需要手畫圖。LangChain 1.x 的 `create_agent` 會建好上面第一張圖（agent ⇄ tools 迴圈），回傳的就是一個編譯好的 LangGraph 圖，`invoke`、`stream`、`checkpointer`、`interrupt` 全部適用：

```python
from langchain.agents import create_agent
from langchain_core.tools import tool
import os

@tool
def lookup_order(order_id: str) -> str:
    """查詢訂單狀態。"""
    return f"{order_id}: 已出貨"

agent = create_agent(
    model=os.environ["LLM_MODEL"],             # 例如 "anthropic:<模型 ID>"
    tools=[lookup_order],
    system_prompt="你是客服助理，查不到的事不要猜。",
    checkpointer=InMemorySaver(),
)
out = agent.invoke(
    {"messages": [("user", "訂單 A123 到哪了？")]},
    {"configurable": {"thread_id": "u-1"}},
)
print(out["messages"][-1].content)
```

舊的 `langgraph.prebuilt.create_react_agent` 在 1.x 仍然可用，功能相同；新程式建議用 `create_agent`，它多了 middleware（在模型呼叫前後掛鉤子）與 `response_format` 結構化輸出。**自己畫圖的時機**是：流程有業務上固定的階段（分類 → 路由 → 解決 → 結案）、某些步驟要暫停等人、或你需要在特定節點上掛重試與監控——這些在預建 Agent 裡做得到但不順手。

**深入請看 →** LangChain、LlamaIndex、自建編排的選型與生產管線：[AI 工程從零開始｜Phase 13 Part 2：AI 工作流程編排](/posts/ai-eng-from-scratch-phase13-part2-orchestration-zh/)

## 什麼時候不該用 LangGraph

| 情況 | 用什麼 | 翻轉條件 |
|---|---|---|
| 單次呼叫、沒有分支和迴圈 | 直接呼叫模型 SDK，或一條 LCEL chain | 一出現「失敗就重試一次」的需求，就值得改成圖 |
| 固定順序的批次管線（ETL 式） | Airflow / Prefect 等排程器 | 需要在步驟之間用 LLM 決定下一步時 |
| 多個獨立 Agent 各跑各的、靠訊息佇列溝通 | 佇列 + 各自的小圖 | 需要「全局狀態可查、可回溯」時，改成一張圖加子圖 |
| 團隊只有一個人、流程兩週後就會改 | 先寫純 Python 函式 | 第一次需要「中途暫停等人」就是遷移點 |

**總體判斷**：有迴圈、要暫停、要接回來——三者有其一，LangGraph 的成本就划算；三者皆無，它只是多一層抽象。

## 總結

- LangGraph = 狀態機 + checkpointer。節點是函式，邊是轉移，state 是唯一的溝通管道，每步存檔。
- State 用 `TypedDict` + reducer 宣告；節點回傳差異；`invoke()` 回傳 `dict`，用 `result["key"]`。
- 路由是回傳字串的函式（條件邊），或讓節點回傳 `Command(goto=, update=)`；路由函式不能更新 state。
- `interrupt()` 存檔退出、`Command(resume=)` 接回；恢復時節點從頭重跑，副作用要放在 `interrupt()` 之後。
- `InMemorySaver` 開發用；上線用 `PostgresSaver`，記得 `with … as` 與 `.setup()`，並規劃 checkpoint 的清理。

## 相關文章

- [LangGraph 客服工單後端：從狀態設計到可恢復的執行](/posts/langgraph-ai-customer-ticket-system-zh/) — 本文四個概念在一個完整後端裡的接法
- [FDE core topic - State Machine & DAG：確定性圖結構與 Agent 反思迴圈收斂](/posts/fde-core-concept-3-state-machine-dag-zh/) — 圖結構與迴圈收斂的理論
- [RAG 完全指南（五）：生產級評估、GraphRAG 與 Agentic RAG](/posts/rag-series-part5-production-zh/) — 用 LangGraph 寫的 Agentic RAG
- [AI 工程從零開始｜Phase 13 Part 2：AI 工作流程編排](/posts/ai-eng-from-scratch-phase13-part2-orchestration-zh/) — 編排框架的選型
