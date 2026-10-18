---
title: "LangGraph 客服工單後端：從狀態設計到可恢復的執行"
date: 2026-10-15T09:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "ai", "engineering"]
tags: ["LangGraph", "LangChain", "Agent", "工作流", "FastAPI", "Backend"]
description: "用一個客服工單流程（接收 → 分類 → 路由 → 解決或升級 → 結案）走完 LangGraph 1.x 後端的關鍵決定：state 欄位分類、Command 路由、interrupt 交給人審、RetryPolicy 與有上限的重寫迴圈、PostgresSaver 持久化與串流 API。"
readTime: "17 min"
aliases: ["/posts/langgraph-ai-backend-core-code-zh/", "/posts/langgraph-ai-backend-ideas-zh/", "/posts/langgraph-ai-backend-architecture-zh/", "/posts/langgraph-ai-backend-logic-zh/"]
---

> 第一版客服工單 Agent 通常長這樣：一個 prompt 做分類、一個 prompt 寫回覆、一個 prompt 打分數，不及格就再寫一次。
> Demo 很好看；上線第三天就出現三種事故：重寫迴圈跑到 `GraphRecursionError`、退款工單被模型自己核准、Pod 重啟後 200 張處理中的工單全部從頭開始。
> 三件事故的共同點是：工單不是一次呼叫，它是一段會中斷、會等人、會跨越部署的**執行**。
> LangGraph 的價值不在「多 Agent」，在於把這段執行變成 checkpoint 上一步一步可恢復的狀態轉移。

**這篇文章的主張：客服工單後端的核心設計不是 prompt，而是「執行的生命週期」——哪些狀態要存、在哪裡暫停、失敗怎麼回頭、重啟後從哪接續。** 下面用一條流程貫穿全文：**接收（intake）→ 分類（classify）→ 路由（route）→ 解決（resolve）或升級（escalate）→ 結案（close）**，每一節解決這條流程上的一個設計決定，並說明替代方案在什麼條件下反而更對。

讀者預設是寫過後端 API、讀過〈[LangGraph + LangChain 入門](/posts/langgraph-langchain-intro-zh/)〉知道 `StateGraph`、reducer、`interrupt` 是什麼的人。本文不重講這些基礎，直接進入「後端怎麼接」。

> 程式碼對照 LangGraph 1.x / LangChain 1.x 公開 API 撰寫，為示意用途、未在本文內執行；每段 ≤ 25 行，刻意省略 import 重複與錯誤處理樣板。模型 ID 從環境變數 `LLM_MODEL` 讀取。

## 一、工單不是一次呼叫

一張工單從進來到結案，典型的時間跨度與失敗點如下（以一個 SaaS 客服為例，數字是設計假設，不是量測值）：

| 階段 | 典型耗時 | 可能失敗的方式 |
|---|---|---|
| 分類 | 1–3 秒 | 模型回傳的 JSON 壞掉；API 429 |
| 查資料、擬回覆 | 5–30 秒（2–4 次工具呼叫） | 工具逾時；模型編造訂單號 |
| 人工審核（約 15–25% 的工單） | 10 分鐘到 2 天 | 服務在等待期間重新部署 |
| 結案與通知 | < 1 秒 | 寄信成功但狀態沒寫回 → 重跑時寄第二封 |

把這張表讀成需求，就是四件事：**狀態要存**（不然重啟就丟）、**流程要能暫停**（等人兩天不能占著一個 request）、**失敗要能局部重試**（API 429 不該從分類重來）、**副作用要冪等**（重跑不能寄兩封信）。這四件事剛好對應 LangGraph 的 checkpointer、`interrupt`、節點級 `RetryPolicy`、以及「節點從頭重跑」的語意——接下來逐一接上。

## 二、整體架構

```
  客戶端 / 工單表單              人工審核後台
        │ POST /tickets                │ POST /tickets/{id}/resume
        ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI                                                     │
│   建立 thread_id = ticket_id → 丟進工作佇列 → 回 202           │
│   GET /tickets/{id}        ← graph.get_state(config)         │
│   GET /tickets/{id}/stream ← graph.stream(..., "updates")    │
└───────────────┬──────────────────────────────────────────────┘
                │ worker 取出工單、invoke / resume
                ▼
┌──────────────────────────────────────────────────────────────┐
│  LangGraph 圖（下一節）                                        │
│   intake → classify → route ─┬→ resolve ──┐                  │
│                              └→ escalate ─┴→ close           │
│   每個節點結束 → 寫一個 checkpoint                            │
└──────┬──────────────────┬───────────────────┬────────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
 ┌───────────┐     ┌──────────────┐     ┌──────────────┐
 │ Postgres  │     │ 工具          │     │ 業務資料庫     │
 │ checkpoint│     │ 知識庫檢索     │     │ tickets 表    │
 │ (圖的狀態) │     │ 訂單查詢       │     │ (客戶看到的)   │
 └───────────┘     └──────────────┘     └──────────────┘
```

三個值得先記住的邊界：

- **checkpoint 資料庫和業務資料庫是兩個東西。** 前者存圖的 state（給恢復用），後者存客戶看得到的工單狀態與回覆（給查詢用）。`close` 節點負責把結果寫進後者；不要拿 `get_state()` 當查詢 API。
- **API 程序不跑圖，worker 跑圖。** 一張工單可能卡在人工審核兩天，`invoke()` 不能住在 HTTP request 裡。
- **人工審核後台只做一件事：** 對某個 `thread_id` 送 `Command(resume=…)`。它不需要知道圖長什麼樣。

## 三、State 設計：三類欄位，兩種 reducer

工單 state 最常見的錯誤是「什麼都塞進去」——輸入、中間結果、控制旗標、日誌混在同一層，最後沒人知道哪個欄位可以被誰改。把欄位分成三類，每類給一個明確的擁有者：

| 類別 | 欄位 | 誰寫 | reducer |
|---|---|---|---|
| 輸入（不變） | `ticket_id`, `customer_id`, `subject`, `body` | `intake` 一次寫入 | 覆蓋 |
| 推導（節點產出） | `category`, `priority`, `draft_reply`, `final_reply` | 對應節點 | 覆蓋 |
| 對話與工具紀錄 | `messages` | `resolve` 的子 Agent | `add_messages` |
| 控制（流程用） | `draft_attempts`, `needs_human`, `resolution` | 寫它的節點與人工審核 | 覆蓋 |
| 稽核軌跡 | `events` | 每個節點追加一筆 | `operator.add` |

```python
import operator
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages

class TicketState(TypedDict, total=False):
    # 輸入
    ticket_id: str
    customer_id: str
    subject: str
    body: str
    # 推導
    category: Literal["billing", "technical", "account", "other"]
    priority: Literal["low", "normal", "high", "urgent"]
    draft_reply: str
    final_reply: str
    messages: Annotated[list, add_messages]
    # 控制
    draft_attempts: int
    needs_human: bool
    resolution: Literal["resolved", "escalated", "rejected"]
    # 稽核
    events: Annotated[list[str], operator.add]
```

**為什麼是 `TypedDict` 而不是 dataclass。** LangGraph 兩者都收，但 `invoke()`、`get_state().values` 回傳的一律是 `dict`。用 dataclass 宣告會誘使你寫 `result.category`，然後在上線後第一張工單上拿到 `AttributeError`。`TypedDict` 讓型別檢查器和執行期行為一致：到處都是 `state["category"]`。如果團隊堅持要物件（例如要共用 Pydantic 驗證），就在 API 邊界 `TicketState(**result)` 轉一次，並且只在那一處轉。

**`total=False` 的用意**是讓節點只回傳差異：`classify` 回傳 `{"category": ..., "events": [...]}` 就好，不必湊齊整個 dict。把整份 state 回傳不會報錯，但 `events` 會被 `operator.add` 再接一次，長度翻倍——這是 reducer 欄位的固定陷阱。

**數字**：`messages` 是 state 裡唯一會長大的欄位。子 Agent 每次工具呼叫往返約 1–4 KB；一張工單 4 次呼叫、checkpoint 存 7 個版本，單張工單的 checkpoint 總量約 50–100 KB。日處理 10 萬張就是 5–10 GB/天，所以 `resolve` 結束時要把 `messages` 截到最後一輪，`close` 之後要有清理策略（第七節）。

## 四、節點與拓樸

```
                     ┌──────────┐
   START ──────────▶ │  intake  │  寫入輸入欄位、events=["received"]
                     └────┬─────┘
                          ▼
                     ┌──────────┐  with_structured_output → category/priority
                     │ classify │  RetryPolicy(max_attempts=3) 吃掉 429
                     └────┬─────┘
                          ▼
                     ┌──────────┐  Command(goto=…)：
                     │  route   │  urgent / 退款 → escalate；其餘 → resolve
                     └──┬────┬──┘
            ┌───────────┘    └────────────┐
            ▼                             ▼
     ┌────────────┐                ┌────────────┐
     │  resolve   │                │  escalate  │  interrupt() 等人
     │ 子 Agent + │                │            │  人回 approve/reply
     │ 工具       │                └─────┬──────┘
     └─────┬──────┘                      │
           │ draft_attempts < 2 且       │
           │ 品質不過 → 回 resolve        │
           │ 2 次都不過 → escalate        │
           ▼                             ▼
     ┌─────────────────────────────────────────┐
     │  close   寫業務資料庫、寄通知（冪等）    │ ──▶ END
     └─────────────────────────────────────────┘
```

### classify：結構化輸出，不解析字串

分類節點唯一的產出是兩個枚舉值。讓模型回傳 JSON 再 `json.loads` 是上線後最常壞的地方（多一個 code fence、少一個引號就炸）；`with_structured_output` 把 schema 交給模型的 tool-calling 機制，回來的是 Pydantic 物件：

```python
import os
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

class Classification(BaseModel):
    category: Literal["billing", "technical", "account", "other"]
    priority: Literal["low", "normal", "high", "urgent"]
    reason: str = Field(description="一句話，給稽核看")

llm = init_chat_model(os.environ["LLM_MODEL"])
classifier = llm.with_structured_output(Classification)

def classify(state: TicketState) -> dict:
    out = classifier.invoke(
        f"主旨：{state['subject']}\n內容：{state['body']}\n"
        "判斷這張客服工單的類別與優先級。"
    )
    return {
        "category": out.category,
        "priority": out.priority,
        "events": [f"classified:{out.category}/{out.priority}:{out.reason}"],
    }
```

### route：`Command` 把「決定」和「記錄」綁在一起

路由只讀 state、不呼叫模型。這裡用 `Command` 而不是 `add_conditional_edges`，因為路由的同時要寫 `needs_human` 給後台顯示；條件邊的路由函式回傳值只是路名，寫 state 不會被存下來：

```python
from langgraph.types import Command

def route(state: TicketState) -> Command[Literal["resolve", "escalate"]]:
    refund_like = state["category"] == "billing" and "退" in state["body"]
    if state["priority"] == "urgent" or refund_like:
        return Command(
            goto="escalate",
            update={"needs_human": True, "events": ["route:escalate"]},
        )
    return Command(goto="resolve", update={"events": ["route:resolve"]})
```

**翻轉條件**：如果路由規則會由營運人員在後台調整（而不是改程式碼），就把規則抽成資料、讓 `route` 讀設定表；若規則需要模型判斷（例如「客戶語氣是否已經很生氣」），路由就變成一個有 `RetryPolicy` 的 LLM 節點，`Command` 的寫法不變。

### resolve：預建 Agent 當作一個節點

查知識庫、查訂單、擬回覆是標準的「LLM + 工具」迴圈，用 `create_agent`（`langchain.agents`）建一個子 Agent，在節點裡呼叫它。子 Agent 自己的 `agent ⇄ tools` 迴圈對外層圖是黑盒，外層只拿它最後一則訊息（`@tool` 來自 `langchain_core.tools`）：

```python
@tool
def search_kb(query: str) -> str:
    """搜尋內部知識庫，回傳最相關的三段。"""

@tool
def lookup_order(order_id: str) -> str:
    """以訂單編號查詢狀態；查無此單回傳 'not found'。"""

resolver = create_agent(
    model=os.environ["LLM_MODEL"],
    tools=[search_kb, lookup_order],
    system_prompt="你是客服。只根據工具結果回答；查不到就說查不到，不要猜。",
)

def resolve(state: TicketState) -> dict:
    question = f"{state['subject']}\n{state['body']}"
    out = resolver.invoke({"messages": [("user", question)]})
    attempt = state.get("draft_attempts", 0) + 1
    return {
        "draft_reply": out["messages"][-1].content,
        "draft_attempts": attempt,
        "messages": out["messages"][-2:],   # 只留最後一輪，控制 checkpoint 大小
        "events": [f"draft:{attempt}"],
    }
```

`draft_attempts` **由節點自己 +1**，路由函式只讀它。把計數放在路由函式裡遞增，是舊版本這篇文章的錯誤，也是重寫迴圈永遠不會停的原因（第六節）。

### 組圖

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

retry = RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0)

def build() -> StateGraph:
    b = StateGraph(TicketState)
    b.add_node("intake", intake)
    b.add_node("classify", classify, retry_policy=retry)
    b.add_node("route", route)
    b.add_node("resolve", resolve)
    b.add_node("escalate", escalate)
    b.add_node("close", close)
    b.add_edge(START, "intake")
    b.add_edge("intake", "classify")
    b.add_edge("classify", "route")   # route 用 Command 決定 resolve / escalate
    b.add_conditional_edges("resolve", after_resolve,
        {"close": "close", "retry": "resolve", "escalate": "escalate"})
    b.add_edge("escalate", "close")
    b.add_edge("close", END)
    return b
```

`route` 的出邊不用宣告——`Command[Literal["resolve", "escalate"]]` 的型別標註就是宣告。`after_resolve` 和 `escalate` 在接下來兩節。

## 五、升級給人：`interrupt` 不是一個 API 呼叫，是一次程序退出

**直覺**：升級節點按下暫停鍵，圖把 state 存進 checkpoint 後整個 `invoke()` 回傳；worker 可以去處理別的工單、可以被重新部署。兩天後人在後台按下核准，後台對同一個 `thread_id` 送 `Command(resume=…)`，`escalate` 節點**從頭**再跑一次，這次 `interrupt()` 直接回傳人的決定。

```python
from langgraph.types import interrupt

def escalate(state: TicketState) -> dict:
    # 注意：恢復時這個函式會從頭重跑，interrupt() 之前不要放副作用
    decision = interrupt({
        "ticket_id": state["ticket_id"],
        "category": state["category"],
        "draft_reply": state.get("draft_reply", ""),
        "ask": "核准草稿、改寫後送出、或拒絕？",
    })
    # decision 是後台送進來的 dict，例如 {"action": "edit", "reply": "..."}
    if decision["action"] == "reject":
        return {"resolution": "rejected", "events": ["human:reject"]}
    reply = decision.get("reply") or state.get("draft_reply", "")
    return {"final_reply": reply, "resolution": "resolved",
            "events": [f"human:{decision['action']}"]}
```

後台那一側只需要兩件事：讀 `interrupt` 的 payload、送回 resume 值。

```python
config = {"configurable": {"thread_id": ticket_id}}

# 讀：哪些工單在等人、各自在問什麼
snap = graph.get_state(config)
if snap.next == ("escalate",):
    payload = snap.tasks[0].interrupts[0].value   # 上面 interrupt() 丟出的 dict

# 寫：人做了決定
graph.invoke(Command(resume={"action": "approve"}), config)
```

這一來一回在 checkpointer 裡長這樣（含一次 `resolve` 的重試）：

```
 時間 ──────────────────────────────────────────────────────────────────▶

 worker A                                        worker B（兩天後，另一台機器）
 invoke(input, thread=T-1024)           invoke(Command(resume=…), thread=T-1024)
   │                                                │
   ▼                                                ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     ┌────────┐ ┌────────┐
 │ ckpt 1 │▶│ ckpt 2 │▶│ ckpt 3 │▶│ ckpt 4 │ ──▶ │ ckpt 5 │▶│ ckpt 6 │
 │ intake │ │classify│ │ route  │ │escalate│     │escalate│ │ close  │
 │        │ │(第 2 次 │ │        │ │ 停在   │     │ 完成   │ │        │
 │        │ │ 嘗試成功)│ │        │ │interrupt│     │        │ │        │
 └────────┘ └────────┘ └────────┘ └────────┘     └────────┘ └────────┘
                                   next=("escalate",)
                                   worker A 回傳；程序可結束
```

**三條硬規則**：

1. **`interrupt()` 之前不放副作用。** 恢復時節點從頭重跑，`interrupt()` 之前的程式碼會執行兩次。寄「已升級給專員」通知這類事情放在 `close` 節點，或放在 `interrupt()` 之後。
2. **resume 值要驗證。** 它來自後台表單，不是圖內部的資料；用 Pydantic 檢查 `action` 的枚舉與 `reply` 的長度，拒絕就直接讓節點拋例外（會被記錄，不會汙染 state）。
3. **同一個節點可以有多個 `interrupt()`**，但恢復時它們依呼叫順序對應 resume 值。把「問兩個問題」拆成兩個節點，比在一個節點裡放兩個 `interrupt()` 容易推理。

**翻轉條件**：審核等待通常在 30 秒內（例如主管在線上即時放行），而且 worker 是單一長駐程序——這時 `InMemorySaver` 加一個 asyncio 等待就夠，不值得為它開 Postgres。一旦等待可能跨越部署，就必須是持久化 checkpointer。

## 六、失敗處理：三層，各管一種失敗

工單流程會遇到三種性質不同的失敗，混在一起用「重試三次」處理是第一版最常見的錯誤。

| 失敗 | 例子 | 處理層 | 工具 |
|---|---|---|---|
| 瞬時錯誤 | API 429、連線重置、結構化輸出偶發壞掉 | 節點內自動重試 | `RetryPolicy` |
| 品質不足 | 草稿沒引用工具結果、語氣不對 | 圖層級的有上限迴圈 | 條件邊 + state 計數 |
| 無法自動處理 | 兩次草稿都不過、工具持續失敗 | 交給人 | `escalate` |

**第一層：`RetryPolicy`** 掛在節點上（第四節的 `classify` 已經掛了）。預設會對一般例外重試、對明顯的程式錯誤（`ValueError`、`TypeError` 等）不重試；要縮小範圍就傳 `retry_on=`。重試發生在節點內部，不會產生新的 checkpoint，也不會進 `events`——這是它只適合瞬時錯誤的原因：你不會想要「品質不過」這種需要留紀錄的事被它吃掉。

**第二層：有上限的重寫迴圈。** 品質檢查用一個便宜的模型或純規則；關鍵是上限由 state 裡的 `draft_attempts` 決定，而 `draft_attempts` 由 `resolve` 節點遞增，路由函式只讀：

```python
def after_resolve(state: TicketState) -> Literal["close", "retry", "escalate"]:
    draft = state.get("draft_reply", "")
    ok = len(draft) > 40 and "not found" not in draft and "我猜" not in draft
    if ok:
        return "close"
    if state.get("draft_attempts", 0) >= 2:
        return "escalate"            # 兩次都不過 → 交給人，不再燒 token
    return "retry"
```

迴圈上限還有第二道保險：`invoke(…, config={"recursion_limit": 20, "configurable": {...}})`。預設是 25 步；這張圖正常路徑 6 步、最多重寫一次是 8 步，設 20 表示「超過這個數一定是 bug」，撞到時拋 `GraphRecursionError`，worker 把工單標記為 `escalated` 並告警，而不是無聲地跑到 token 預算見底。

**第三層：工具失敗不等於工單失敗。** `resolve` 裡的子 Agent 工具拋例外時，`create_agent` 預設會把錯誤訊息當作 `ToolMessage` 回給模型，模型通常會改用別的工具或承認查不到。這是對的行為——但要在 `after_resolve` 的品質檢查裡抓「查不到」的措辭，讓它走 `escalate`，不要讓「很抱歉，系統暫時無法查詢」這種回覆直接寄給客戶。

**數字**：一次 `resolve` 約 3 次模型呼叫、合計 6–10K input token、600–1,000 output token。以每百萬 input token $3、output $15 的假設計價，一次草稿約 $0.03–0.05；允許重寫一次把上限壓在 $0.10/張。沒有上限的迴圈在 25 步撞 recursion limit 前會花掉約 $0.40，而且客戶什麼都沒收到。

## 七、持久化：`PostgresSaver` 住在應用的生命週期裡

開發用 `InMemorySaver`，上線換 `PostgresSaver`，介面相同；差別在它是 context manager、第一次要 `.setup()` 建表，而且**連線要活得跟程序一樣久**，不是每個 request 開一次：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

DB_URI = os.environ["CHECKPOINT_DB_URI"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()                       # 建表；重複呼叫無害
        app.state.graph = build().compile(checkpointer=checkpointer)
        yield                                  # 服務運行期間連線一直開著

app = FastAPI(lifespan=lifespan)
```

同步版本是 `langgraph.checkpoint.postgres.PostgresSaver`，用 `with` 包住 worker 的主迴圈即可。

**`thread_id` 就是工單 ID。** 這讓後台、worker、API 三方不需要另一張對照表；任何一方拿到 `ticket_id` 就能 `get_state`。代價是同一張工單不能平行跑兩條執行——這正是你要的，重複處理一張工單是事故，不是功能。

**歷史可以回溯，也可以修正。** `get_state_history(config)` 由新到舊列出每個 checkpoint；`update_state(config, values, as_node=…)` 可以「假裝某個節點寫了這些值」，用來手動修正分類後從下一步繼續，而不是整張工單重跑：

```python
# 稽核：這張工單走過哪些節點
for snap in graph.get_state_history(config):
    print(snap.config["configurable"]["checkpoint_id"], snap.next,
          snap.values.get("events", [])[-1:])

# 修正：客服主管認為分類錯了，改成 billing 後從 route 繼續
graph.update_state(config, {"category": "billing"}, as_node="classify")
graph.invoke(None, config)     # input=None：從 checkpoint 的 next 節點接著跑
```

**清理是上線前的事，不是容量告警後的事。** checkpoint 表沒有內建 TTL。做法是 `close` 節點寫業務資料庫成功後，把 `thread_id` 丟進一個「可清理」清單，由夜間工作刪除 `resolution` 已定、超過 N 天（稽核要求決定 N）的 thread；或在 Postgres 上對 checkpoint 表按 `thread_id` 分區，整批 drop。

**翻轉條件**：單一程序、工單在 30 秒內結束、沒有人工審核——`InMemorySaver` 加上「失敗就整張重跑」比 Postgres 便宜且好維護。一出現跨部署的等待或「從第三步接著跑」的需求，就換。

## 八、串流：讓後台看見工單走到哪

`graph.stream()` 和 `invoke()` 吃一樣的參數，差別是逐步吐出事件。三種 `stream_mode` 各有用途：

| `stream_mode` | 每個事件 | 用途 |
|---|---|---|
| `"updates"` | `{節點名: 該節點回傳的差異}` | 後台進度條：「分類完成 → 路由 → 擬稿中」 |
| `"messages"` | `(訊息片段, metadata)`，`metadata["langgraph_node"]` 說來自哪個節點 | 即時顯示 `resolve` 子 Agent 正在打的字 |
| `"custom"` | 節點用 `get_stream_writer()` 自己送的任何物件 | 工具進度：「已查第 2/3 個資料來源」 |

```python
from langgraph.config import get_stream_writer

def resolve(state: TicketState) -> dict:
    writer = get_stream_writer()
    writer({"stage": "searching_kb"})            # 走 "custom" 通道
    out = resolver.invoke({"messages": [("user", state["body"])]})
    writer({"stage": "draft_ready"})
    ...

# SSE 端點：把 updates 與 custom 事件合併送出
async def stream_ticket(graph, ticket_id: str):
    config = {"configurable": {"thread_id": ticket_id}}
    modes = ["updates", "custom"]
    async for mode, chunk in graph.astream(None, config, stream_mode=modes):
        if mode == "updates":
            node = next(iter(chunk))
            yield f"event: node\ndata: {node}\n\n"
        else:
            yield f"event: progress\ndata: {chunk['stage']}\n\n"
```

傳 list 給 `stream_mode` 時，每個事件是 `(模式, 內容)` 的 tuple；只傳一個字串時直接是內容。這是看 LangGraph 串流程式碼時最常讓人困惑的地方。

**限制**：串流只對「正在執行」的那次呼叫有效。工單卡在 `interrupt` 兩天，這段期間沒有東西可串——後台顯示等待中的工單，靠的是 `get_state().next`，不是 stream。

## 九、API 層與執行模型

三個端點就夠：

```python
from fastapi import HTTPException

def cfg(ticket_id: str) -> dict:
    return {"configurable": {"thread_id": ticket_id}}

@app.post("/tickets", status_code=202)
async def create_ticket(t: NewTicket):           # NewTicket: Pydantic 輸入模型
    ticket_id = new_ticket_id()                      # 例如 "T-" + ULID
    await queue.enqueue("run_ticket", ticket_id, t.model_dump())   # 交給 worker
    return {"ticket_id": ticket_id}

@app.post("/tickets/{ticket_id}/resume")
async def resume_ticket(ticket_id: str, decision: HumanDecision):
    snap = await app.state.graph.aget_state(cfg(ticket_id))
    if snap.next != ("escalate",):
        raise HTTPException(409, "ticket is not waiting for a human")
    await queue.enqueue("resume_ticket", ticket_id, decision.model_dump())
    return {"status": "resuming"}

@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    snap = await app.state.graph.aget_state(cfg(ticket_id))
    return {"next": snap.next, "resolution": snap.values.get("resolution"),
            "events": snap.values.get("events", [])}
```

**為什麼是佇列 + worker，而不是 FastAPI 的 `BackgroundTasks`。** `BackgroundTasks` 在同一個程序、同一個 event loop 裡跑，有三個問題：一次部署會殺掉所有進行中的工單（雖然 checkpoint 還在，但沒人會自動接續）；`uvicorn --workers N` 下任務只存在於接到 request 的那個程序；而且 FastAPI 0.106 之後，`yield` 型相依（典型的 DB session）會在背景任務開始**之前**就被清理，拿到的 session 已經關閉。工作佇列（`arq`、Celery、`rq`，或單純一張 Postgres `jobs` 表加 `SELECT … FOR UPDATE SKIP LOCKED`）解決的是「誰負責把有 checkpoint 的工單接著跑完」這個問題，不只是非同步。

**worker 的兩個 job**：

```python
async def run_ticket(ctx, ticket_id: str, payload: dict):
    config = {"recursion_limit": 20, "configurable": {"thread_id": ticket_id}}
    try:
        await ctx["graph"].ainvoke({"ticket_id": ticket_id, **payload}, config)
    except GraphRecursionError:
        await mark_escalated(ticket_id, reason="recursion_limit")

async def resume_ticket(ctx, ticket_id: str, decision: dict):
    config = {"configurable": {"thread_id": ticket_id}}
    await ctx["graph"].ainvoke(Command(resume=decision), config)
```

兩個 job 都是冪等的：同一張工單被排進兩次，第二次 `ainvoke` 讀到的 checkpoint 已經在 `END`（`next == ()`），什麼都不會做。這也是「`thread_id` = 工單 ID」帶來的好處。

**冪等的最後一哩在 `close`。** 寄通知、寫業務資料庫這兩件事，要嘛用 `ticket_id` 當唯一鍵做 upsert，要嘛先查「已寄」旗標；因為任何一次恢復或手動 `update_state` 後重跑，`close` 都可能再執行一次。

## 十、上線前：症狀、診斷、成本

**症狀 → 診斷**（你在 log、metrics、checkpoint 表裡會看到什麼）：

| 症狀 | 最可能的原因 | 怎麼確認 |
|---|---|---|
| `GraphRecursionError` 集中在某類工單 | 品質檢查對該類永遠不過，而重寫上限沒生效 | `get_state_history` 看 `draft_attempts` 是否每輪 +1；為 0 代表計數放錯地方 |
| 客戶收到兩封一樣的通知 | `close` 不冪等，恢復或 `update_state` 後重跑 | 業務資料庫查同一 `ticket_id` 的通知紀錄時間戳 |
| 工單「卡住」但 `next == ()` | 圖已結束，業務資料庫沒更新——`close` 寫 DB 失敗被吞掉 | 比對 checkpoint 的 `resolution` 與 tickets 表 |
| 工單 `next == ("escalate",)` 超過 SLA | 後台沒撈到它，或 resume 送到了錯的 `thread_id` | 以 `next` 欄位掃 checkpoint 表，對照後台待辦清單 |
| checkpoint 表一週長到 50 GB | `messages` 沒截斷，或清理工作沒跑 | 抽樣一個 thread 的 checkpoint 大小；看最老的已結案 thread 日期 |
| 恢復後重複寄出「已升級」通知 | 副作用放在 `interrupt()` 之前 | 看 `escalate` 的 `events` 是否出現兩次同一筆 |
| 分類正確率下滑但沒有錯誤 | 模型版本變了（`LLM_MODEL` 指向別名） | 把實際模型 ID 寫進 `events`，比對變化日期 |

**成本估算**（設計假設，請用自己的量測回填）：

```
每張工單                 token            以 $3 / $15 per M 計
  classify（含 1 次重試）  1.5K in / 0.1K out      ≈ $0.006
  resolve（3 次呼叫）       8K in / 0.8K out        ≈ $0.036
  重寫一次（25% 的工單）     +8K in / 0.8K out ×0.25 ≈ $0.009
  ───────────────────────────────────────────────────────
  模型成本                                          ≈ $0.05 / 張
  Postgres checkpoint 寫入  7 次 × ~15 KB ≈ 100 KB / 張（清理前）
  人工審核比例 20%，平均 6 分鐘                      ≈ 人力成本的主項
```

模型成本以 10 萬張/月計約 $5,000；真正的成本槓桿是人工審核比例——把 `route` 的升級規則從「所有 billing」收斂到「billing 且涉及退款」，20% 降到 8% 省下的人時，比換便宜模型多一個數量級。

**上線檢查清單**：

- [ ] `invoke()` 的回傳全部以 `result["…"]` 存取；沒有任何 `result.attr`
- [ ] 每個 reducer 欄位的節點都回傳差異，不回傳整份 state
- [ ] `draft_attempts` 由節點遞增；路由函式沒有任何賦值
- [ ] `interrupt()` 之前沒有副作用；`close` 冪等
- [ ] `PostgresSaver` 在 lifespan 裡、呼叫過 `.setup()`；worker 與 API 用同一個 `DB_URI`
- [ ] `recursion_limit` 設成「正常路徑 × 2–3」，撞到時有告警與標記
- [ ] `messages` 在 `resolve` 結束時截斷；已結案 thread 有清理工作
- [ ] 實際模型 ID 寫進 `events`，模型升級可以在稽核軌跡裡看出來

## 總結

- 客服工單後端的核心設計是**執行的生命週期**：哪些狀態要存、在哪暫停、失敗怎麼回頭、重啟後從哪接續。LangGraph 的 checkpointer、`interrupt`、`RetryPolicy` 各對應其中一件事。
- State 分三類欄位（輸入／推導／控制）加稽核軌跡；用 `TypedDict` + reducer，節點回傳差異，`invoke()` 回傳 `dict`。
- 路由要寫 state 就用 `Command(goto=, update=)`；重寫迴圈的計數由節點遞增、路由只讀，再用 `recursion_limit` 當第二道保險。
- `interrupt()` 之前不放副作用、`close` 要冪等，因為恢復就是「節點從頭重跑」。
- `PostgresSaver` 住在 lifespan 裡、`thread_id` = 工單 ID、圖由 worker 跑而不是 API 程序；checkpoint 清理在上線前規劃。

## 相關文章

- [LangGraph + LangChain 完全入門指南](/posts/langgraph-langchain-intro-zh/) — State、reducer、條件邊、`interrupt`、持久化的最小說明
- [FDE core topic - State Machine & DAG：確定性圖結構與 Agent 反思迴圈收斂](/posts/fde-core-concept-3-state-machine-dag-zh/) — 第六節重寫迴圈的收斂理論
- [RAG 完全指南（五）：生產級評估、GraphRAG 與 Agentic RAG](/posts/rag-series-part5-production-zh/) — `resolve` 子 Agent 若要接知識庫檢索，從這裡的 Agentic RAG 開始
- [AI 工程從零開始｜Phase 13 Part 2：AI 工作流程編排](/posts/ai-eng-from-scratch-phase13-part2-orchestration-zh/) — LangGraph 之外的編排選項與選型條件
