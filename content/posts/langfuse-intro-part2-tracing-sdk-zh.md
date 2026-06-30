---
title: "Langfuse 入門 Part 2 — 三行程式碼開始追蹤:SDK 整合與 Tracing 實戰"
date: 2026-06-30T13:30:00+08:00
draft: false
description: "概念懂了,該動手了。本篇示範用 Langfuse Python SDK 把應用接上可觀測性:@observe 裝飾器、get_client 與 context manager、OpenAI 一行替換整合、LangChain callback handler,以及如何用 Session、User、Metadata 讓 trace 真正可查可比。"
categories: ["engineering", "ai", "all"]
tags: ["Langfuse", "LLM", "Observability", "Tracing", "Python", "SDK", "OpenAI", "LangChain", "LLMOps"]
authors: ["yen"]
readTime: "15 min"
---

> 可觀測性最大的阻力,從來不是「值不值得」,而是「要改多少程式碼」。
> Langfuse 的設計哲學是:讓你從「完全沒追蹤」到「完整 trace」,只需要加幾行——甚至一行。
> 這篇就帶你把第一個 trace 送上儀表板。

---

## 一、起手式:安裝與設定

[Part 1](../langfuse-intro-part1-concepts-zh/) 講完概念,這篇全是實作。先裝套件、設好金鑰。

```bash
pip install langfuse
```

到 [Langfuse Cloud](https://cloud.langfuse.com)(免費)或你自架的實例,建一個專案,拿到一組金鑰,放進環境變數:

```bash
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_BASE_URL="https://cloud.langfuse.com"   # 自架的話填你的網址
```

SDK 會自動讀這些環境變數,所以程式裡通常不必硬寫金鑰。接下來有三種接法,由淺入深。

---

## 二、接法一:`@observe` 裝飾器(最省力)

最快的方式:在你想追蹤的函式上加一個 `@observe()` 裝飾器。它會自動把這個函式變成一個 observation,捕捉輸入、輸出、執行時間。

```python
from langfuse import observe, get_client

@observe()
def retrieve_docs(query: str) -> list[str]:
    # 你的檢索邏輯
    return ["doc1", "doc2"]

@observe()
def generate_answer(query: str, docs: list[str]) -> str:
    # 你的生成邏輯
    return "答案..."

@observe()                          # 最外層 → 這會是一個 Trace
def handle_request(query: str) -> str:
    docs = retrieve_docs(query)     # 巢狀的 Observation
    answer = generate_answer(query, docs)
    return answer

handle_request("分析這份財報的風險")
```

**關鍵在於:巢狀的函式呼叫會自動形成巢狀的 observation 樹。** 你不需要手動串接 parent/child——`handle_request` 成為 trace,裡面的 `retrieve_docs` 和 `generate_answer` 自動成為它的子 observation。這正是 Part 1 講的那棵樹,而你只加了三個裝飾器。

```
   Trace: handle_request
   ├─ Observation: retrieve_docs
   └─ Observation: generate_answer
```

### 標記 LLM 呼叫為 Generation

如果某個函式是 LLM 呼叫,把它標成 `generation` 型別,Langfuse 就會用專屬的 LLM 視圖呈現它:

```python
@observe(as_type="generation")
def call_llm(prompt: str) -> str:
    ...
```

---

## 三、接法二:Context Manager(最有彈性)

當你需要更精細的控制(動態命名、更新欄位),用 context manager:

```python
from langfuse import get_client

langfuse = get_client()

with langfuse.start_as_current_observation(as_type="span", name="process-request") as span:
    span.update(input={"query": "分析財報風險"})

    # 巢狀一個 generation
    with langfuse.start_as_current_observation(
        as_type="generation", name="llm-response", model="gpt-4o"
    ) as generation:
        result = my_llm_call()
        generation.update(
            output=result,
            usage_details={"input": 1200, "output": 400},   # token 數
        )

    span.update(output="處理完成")

langfuse.flush()   # 短生命週期程式(腳本/Lambda)記得 flush
```

兩個常被忽略的細節:

1. **`langfuse.flush()`**:Langfuse 是非同步批次送資料(避免拖慢你的主流程)。短生命週期的程式(CLI 腳本、Serverless function)結束太快,資料可能還沒送出去。手動 `flush()` 確保它送完才結束。長駐服務則不必每次呼叫。
2. **`get_client()` 是 singleton**:整個程式共用同一個 client,不需要到處 new。

---

## 四、接法三:框架整合(最無痛)

如果你用的是主流框架,連裝飾器都不必加——Langfuse 有原生整合。

### OpenAI:改一行 import

把 `import openai` 換成 `from langfuse.openai import openai`,**其他程式碼一個字都不用改**,所有 OpenAI 呼叫就自動被追蹤:

```python
# 原本:from openai import OpenAI
from langfuse.openai import openai     # ← 只改這行

completion = openai.chat.completions.create(
    name="risk-analysis",              # 可選:給這次呼叫命名
    model="gpt-4o",
    messages=[{"role": "user", "content": "分析財報風險"}],
    metadata={"user_tier": "premium"}, # 可選:附加 metadata
)
```

它會自動捕捉 model、messages、token 用量、成本、延遲——零額外工作。

### LangChain:掛一個 callback handler

LangChain 用戶把 Langfuse 的 `CallbackHandler` 掛上去即可:

```python
from langfuse.langchain import CallbackHandler
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

langfuse_handler = CallbackHandler()

llm = ChatOpenAI(model_name="gpt-4o")
prompt = ChatPromptTemplate.from_template("講一個關於 {topic} 的笑話")
chain = prompt | llm

response = chain.invoke(
    {"topic": "貓"},
    config={"callbacks": [langfuse_handler]},   # ← 掛上 handler
)
```

整條 chain 的每一步(prompt 組裝、LLM 呼叫、parser)都會被自動拆成巢狀 observation。

> 同理,Anthropic、LlamaIndex、Vercel AI SDK、以及任何走 OpenTelemetry 的工具,都有對應整合。**幾乎不存在「接不上」的情況。**

---

## 五、讓 trace 真正可用:Session、User、Metadata

光把資料送進去還不夠。當你有成千上萬個 trace,**「找得到、分得開、比得了」才是關鍵**。三個維度幫你做到這點。

### Session:串起多輪對話

聊天機器人的一段對話有很多輪,每輪是一個 trace。用同一個 `session_id` 把它們串成一段可回放的對話:

```python
from langfuse import get_client
langfuse = get_client()

@observe()
def chat_turn(message: str):
    # 把這個 trace 歸到某個 session 與 user
    langfuse.update_current_trace(
        session_id="conversation-abc-123",
        user_id="user-456",
    )
    ...
```

之後在 UI 裡,你能看到「conversation-abc-123」這整段對話的完整來龍去脈,而不是一堆零散的一問一答。

### User:以使用者為單位分析

`user_id` 讓你能回答:「這個使用者花了我們多少 token?」「哪些使用者最常踩到爛回答?」——成本歸戶與問題定位都靠它。

### Metadata 與 Tags:自訂維度

附上任意 metadata(版本、環境、實驗組別)和 tags,之後就能在儀表板上**按這些維度切分、過濾、比較**:

```python
langfuse.update_current_trace(
    metadata={"prompt_version": "v3", "env": "prod", "ab_group": "B"},
    tags=["rag", "finance"],
)
```

這一步看似瑣碎,卻決定了你的可觀測性「能不能用」。**沒有 metadata 的 trace 就像沒貼標籤的箱子——存了等於沒存。**

---

## 六、為什麼選 X 不選 Y

| 情境 | 選的方案 | 為什麼 |
|------|----------|--------|
| 自己寫的函式鏈 | `@observe` 裝飾器 | 最省力,自動巢狀,一行一個 |
| 需要動態命名/更新欄位 | context manager | 彈性最高,可在執行中 update |
| 用 OpenAI SDK | `langfuse.openai` 替換 import | 零改動,自動抓 token/成本 |
| 用 LangChain | `CallbackHandler` | 自動拆解整條 chain |
| CLI / Serverless | 記得 `flush()` | 非同步送資料,短程式需手動 flush |

**Flip condition**:長駐的 web 服務不需要每次 `flush()`(背景執行緒會定期送);但 Lambda、cron 腳本這種「跑完就死」的環境,不 flush 就會掉資料。

---

## 七、小結

這篇的核心訊息只有一個:**接 Langfuse 的成本極低,低到沒有不接的理由。**

1. **三種接法,由淺入深**:`@observe` 最省力、context manager 最彈性、框架整合最無痛。
2. **巢狀自動成樹**:你照常寫程式,Langfuse 自動把呼叫結構變成可視化的 observation 樹。
3. **Session / User / Metadata 決定可用性**:送資料只是第一步,貼好標籤才能在海量 trace 裡找到、分開、比較。

> 一句話總結:可觀測性不該是「之後有空再加」的負債,用 Langfuse 它可以是「現在就加、幾乎零成本」的基礎建設。

資料進來了,下一篇([Part 3](../langfuse-intro-part3-evaluation-zh/))處理最關鍵的問題:**這些回答到底好不好?** 我們會用 Score、LLM-as-a-Judge、與 Dataset 實驗,把品質變成可量化的數字。

---

**系列導覽**

- [Part 1 — 核心概念與資料模型](../langfuse-intro-part1-concepts-zh/)
- Part 2 — SDK 整合與 Tracing 實戰(本篇)
- [Part 3 — LLM 評估:Score、LLM-as-a-Judge、Dataset](../langfuse-intro-part3-evaluation-zh/)
- [Part 4 — 監控與 Prompt 管理](../langfuse-intro-part4-monitoring-prompt-management-zh/)

**參考連結**

- [Langfuse — Observability 快速開始](https://langfuse.com/docs/observability/get-started)
- [Langfuse — 整合列表](https://langfuse.com/docs/integrations)
