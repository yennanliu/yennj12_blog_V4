---
title: "OpenWorker 深度解析（二）：TurnEngine — Agent 迴圈的完整解剖"
date: 2026-08-07T10:00:00+08:00
draft: false
weight: 2
description: "逐行拆解 OpenWorker 的 1192 行 agent 迴圈：訊息的真實形狀、blocking provider 如何橋接到 async loop、工具呼叫的授權與併發分流、四種中斷狀態下的「不留孤兒 tool_call」不變式，以及 canonical history 與 outbound view 的分離設計。"
categories: ["engineering", "ai", "all"]
tags: ["OpenWorker", "AI Agent", "Agent Loop", "asyncio", "LLM", "Python", "開源專案解析", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
series: ["openworker-intro"]
---

> *大多數人以為 agent loop 就是「while 迴圈裡呼叫 LLM，有 tool_calls 就執行」。*
> *那份實作大概 40 行，在 demo 裡跑得很好。*
> *真實系統裡它是 1192 行，而多出來的 1152 行不是為了功能，是為了「壞掉的時候別壞得太難看」。*
> *這篇要讀的，就是那 1152 行。*

---

本篇是 [OpenWorker 深度解析系列](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
的第二篇，主角只有一個檔案：`coworker/engine.py`。

---

## 一、Agent Loop 的本質，以及它的三個謊言

### 1.1 教科書版本

```python
# 你在每一篇 tutorial 裡看到的版本
messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_input}]
while True:
    resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    msg = resp.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
    for tc in msg.tool_calls:
        result = TOOL_FUNCS[tc.function.name](**json.loads(tc.function.arguments))
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
```

這 12 行沒有錯，但它有三個隱含的謊言：

| 謊言 | 現實 |
|---|---|
| 「`messages` 就是送給模型的東西」 | 你需要持久化額外欄位（時間戳、來源、思考文字、token 用量），但這些欄位會讓 provider 400 |
| 「工具執行完就 append」 | 有些工具需要人類批准，那是一個可能等 30 分鐘的 await |
| 「迴圈自然會結束」 | 使用者會按 Stop、provider 會 timeout、context 會爆掉 |

TurnEngine 的 1192 行，本質上就是把這三個謊言一個一個拆掉。

### 1.2 檔案開頭的設計聲明

```python
"""TurnEngine — the owned agent loop.

Async, but with blocking provider/tool calls wrapped in `asyncio.to_thread` so the loop
(and any UI consuming its events) stays responsive. One user turn spans many model↔tool
iterations until the model stops requesting tools, a rail trips, or it's interrupted.
When the model requests several tool calls in one turn, low-risk ones (reads, searches)
execute concurrently; writes/shell stay strictly ordered.

Approvals are handled out-of-band via an injected async `approver`: when the permission
engine says `needs_user`, the engine emits `PERMISSION_REQUIRED` and awaits the approver.
"""
```

四個關鍵詞，就是本篇的四個章節：
**async / to_thread**（第三、四章）、**低風險併發**（第五章）、
**out-of-band approver**（第五章）、**interrupted**（第六章）。

---

## 二、訊息的真實形狀

在讀迴圈之前，必須先知道 `self.messages` 裡到底裝了什麼。這是理解整個引擎的前提。

### 2.1 五種 role

OpenAI 格式只有四種 role（system / user / assistant / tool），OpenWorker 加了第五種：

```
role: "system"     → 系統提示（persona prompt + AGENTS.md + memory + narration 規則）
role: "user"       → 使用者輸入，可能是 str 或 content-parts（文字 + 圖片 + PDF）
role: "assistant"  → 模型回應，可能帶 tool_calls
role: "tool"       → 工具結果，用 tool_call_id 對應
role: "notice"     → ★ 顯示專用標記：error / interrupted / model_switch / compacted
```

`notice` 是 OpenWorker 自創的。它讓「這一輪因為 provider 錯誤而中斷」這件事
**能跟著 transcript 一起持久化、重載後還看得到**，但送給模型時整個丟掉：

```python
def _append_notice(self, kind: str, text: Optional[str] = None) -> None:
    """Persist a turn-ending marker (error/interrupted) as a display-only `notice`
    message: it survives reload like the transcript does, but `_outbound_messages`
    drops the role so no provider ever sees it."""
    notice: dict[str, Any] = {"role": "notice", "kind": kind, "ts": time.time()}
    if text:
        notice["text"] = text
    self.messages.append(notice)
```

### 2.2 五種側車（sidecar）

除了 role 之外，訊息上還掛了五個「provider 看不到」的欄位：

```
┌─────────────┬──────────────────────────────────────────────────────────────┐
│ 側車欄位     │ 用途                                                          │
├─────────────┼──────────────────────────────────────────────────────────────┤
│ ts          │ append 當下的 unix 時間戳                                     │
│ source      │ Connector 來源（Slack 訊息的頻道、發送者）→ GUI 畫成卡片      │
│ _display    │ 使用者可見、模型不可見的中繼資料                              │
│             │  例：「隱私過濾器藏了 3 筆 Gmail 結果」                        │
│             │  ★ 模型絕不能看到這個數字，否則它會試著繞過過濾器             │
│ reasoning   │ 模型的思考文字（DeepSeek reasoning_content、Gemini thought）  │
│             │  ★ 顯示用，從不 replay 回 provider                            │
│ usage       │ 這一輪的 token 計數，標記產生它的模型（跨模型切換仍可彙總）    │
└─────────────┴──────────────────────────────────────────────────────────────┘
```

`_display` 的設計動機在 `_record_result` 的註解裡寫得很清楚：

```python
# A `_display` key on a tool result is user-facing metadata the AGENT must
# never see (e.g. how many gmail hits the privacy filters hid — a count
# the model could probe around).
```

**「a count the model could probe around」** —— 如果模型知道有 3 筆結果被隱藏，
它可以用二分搜尋式的查詢逐步推斷出被隱藏的內容。所以這個數字只能給人看。

### 2.3 還有一種：provider 私有 extras

```python
if turn.extras:
    # Provider-private sidecars (e.g. `_gemini` thought signatures) persist with the
    # message; the owning provider reattaches them, the rest strip them (base.py).
    message.update(turn.extras)
```

Gemini 的 thought signature 必須原樣送回去才能維持思考鏈，但其他 provider 看到會報錯。
契約是：**底線開頭的 key，只有擁有它的 provider 會消費，其他一律剝掉**。

---

## 三、主迴圈：`_loop()` 逐段解析

```
┌─────────────────────────────────────────────────────────────────────────┐
│  while True:                                                            │
│                                                                         │
│   ① if iterations >= max_iterations:  → TURN_END(max_iterations_exceeded)│
│                                                                         │
│   ② 壓縮檢查點                                                           │
│      if _compaction_due():                                              │
│          yield COMPACTING          ← 先發訊號，因為摘要要跑好幾秒         │
│          notice = await _compact_now()                                  │
│          yield COMPACTED                                                │
│                                                                         │
│   ③ 串流模型回應                                                         │
│      async for chunk in self._astream():                                │
│          yield REASONING_DELTA / ASSISTANT_DELTA                        │
│      ┌─ except провider error:                                          │
│      │    is_context_overflow? → 強制壓縮後 continue（有進度保證）        │
│      │    否則 → 保住已串流的部分 + notice("error") + yield ERROR → return│
│      └─                                                                 │
│                                                                         │
│   ④ if 使用者按了 Stop 且 turn is None:                                  │
│          持久化「使用者看到的那一段」+ notice("interrupted") → return     │
│                                                                         │
│   ⑤ append assistant message，yield ASSISTANT_MESSAGE                    │
│                                                                         │
│   ⑥ if not turn.tool_calls:                                             │
│          有 steering 訊息 → 注入後 continue                              │
│          否則 → TURN_END(completed) → return                            │
│                                                                         │
│   ⑦ async for event in _handle_tool_calls(turn.tool_calls): yield event │
│      yield ITERATION_END                                                │
│                                                                         │
│   ⑧ 再檢查一次 cancel / steering                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.1 檢查點的位置是刻意的

注意 `_cancel` 被檢查了幾次：串流中（producer thread 每個 chunk）、
串流後（④）、每個工具呼叫前（`_handle_tool_calls` 迴圈內）、
每一輪結束（⑧），還有所有 await 的地方（`_interruptible`）。

**這不是防禦性冗餘，是因為「按 Stop」可能發生在任何狀態**。第六章會詳細討論。

### 3.2 max_iterations 是護欄，不是配置

```python
max_iterations: int = 12,
```

預設 12 輪。這不是「模型最多想 12 次」，而是「一個 user turn 內最多 12 次
模型↔工具往返」。配置從 `config.max_iterations` 讀，但預設值刻意保守
—— 大部分無限迴圈的 bug 都是模型反覆呼叫同一個失敗的工具。

### 3.3 Context overflow 的自我修復路徑

```python
except Exception as exc:  # provider failure
    # A raw context-overflow 400 (compaction mispredicted, e.g. the estimate
    # path) routes into the compaction policy instead of surfacing. The retry
    # is progress-guarded: each pass moves the boundary forward or gives up,
    # so a model that keeps overflowing still terminates in the error path.
    if _compaction.is_context_overflow(exc) and not self._cancel.is_set():
        yield Event(EventType.COMPACTING, {})
        notice = await self._compact_now(force=True)
        if notice:
            self._append_notice("compacted", notice)
            yield Event(EventType.COMPACTED, {"text": notice})
            continue
```

這段做對了兩件事：

1. **不把 context overflow 當成錯誤呈現給使用者** —— 這是系統該自己處理的內務。
2. **「progress-guarded」** —— `_compact_now(force=True)` 每次都會把 boundary 往前推，
   推不動就回傳 `None`，於是落到下面的錯誤路徑。**不會無限重試。**

還有一個容易漏掉的細節：

```python
# Same contract as the stop path below: the partial the user watched
# arrive survives the failure.
if streamed or streamed_reasoning:
    self.messages.append(_assistant_message(_partial_turn()))
```

**使用者已經看到的文字，不能因為後面炸了就消失。** 這是一致的契約
—— 錯誤路徑和中斷路徑都遵守。

而 `_partial_turn()` 刻意**不包含 tool_calls**：

```python
def _partial_turn() -> AssistantTurn:
    # What the user watched arrive — text and thinking, NO tool calls (any
    # half-formed calls would either orphan or execute against the stop).
    return AssistantTurn(
        text="".join(streamed) or None,
        reasoning="".join(streamed_reasoning) or None,
    )
```

半成形的 tool_call 要嘛變成孤兒、要嘛在使用者已經按下 Stop 之後還被執行。兩個都不行。

---

## 四、串流橋接：blocking → async

這是整個檔案裡最值得抄的一段工程模式。

### 4.1 問題

Provider SDK 的 `stream()` 是**同步 generator**（`for chunk in provider.stream(...)`）。
但引擎是 async 的，UI 靠 async event stream 更新。直接在 event loop 裡跑同步 generator
會把整個 loop 卡死 —— UI 凍結、Stop 按鈕沒反應。

### 4.2 解法

```
┌──────────────────────────────────────────────────────────────────────┐
│  Event Loop（主執行緒）                Worker Thread                  │
│                                                                      │
│   _astream()                          produce()                      │
│      │                                   │                           │
│      │  run_in_executor(None, produce)   │                           │
│      ├──────────────────────────────────▶│                           │
│      │                                   │ for chunk in              │
│      │                                   │   provider.stream(...):   │
│      │                                   │                           │
│      │                                   │   if _cancel.is_set():    │
│      │                                   │       break  ← 兩個 chunk  │
│      │                                   │              間丟棄串流    │
│      │                                   │                           │
│      │      call_soon_threadsafe         │                           │
│      │◀──── queue.put_nowait(chunk) ─────┤                           │
│      │                                   │                           │
│   ┌──┴─────────────────────────────┐     │                           │
│   │ asyncio.wait({                 │     │                           │
│   │   queue.get(),                 │     │                           │
│   │   _cancel.wait()               │     │  ★ 用 race 而不是 await   │
│   │ }, FIRST_COMPLETED)            │     │    queue.get()，因為串流   │
│   └────────────────────────────────┘     │    可能「卡住不吐 chunk」  │
│      │                                   │                           │
│      ▼ yield chunk                       ▼                           │
└──────────────────────────────────────────────────────────────────────┘
```

程式碼：

```python
async def _astream(self):
    """Bridge the provider's blocking stream generator to the async loop via a
    thread + queue, so text deltas surface live without blocking the event loop."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    tools = self.registry.schemas() or None
    model, messages, settings = (
        self.model, self._outbound_messages(), self.model_settings,
    )
    provider = self.provider

    def produce():
        try:
            for chunk in provider.stream(model=model, messages=messages,
                                         tools=tools, **settings):
                # User pressed Stop: drop the stream between chunks (reading the
                # asyncio.Event's flag from a thread is safe; we only read).
                if self._cancel.is_set():
                    break
                loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    loop.run_in_executor(None, produce)
    while True:
        # Race the queue against Stop so a stalled stream (no chunks arriving —
        # the pre-first-token wait, a wedged connection) can't hold the turn.
        get_task = asyncio.ensure_future(queue.get())
        cancel_task = asyncio.ensure_future(self._cancel.wait())
        done, _ = await asyncio.wait({get_task, cancel_task},
                                     return_when=asyncio.FIRST_COMPLETED)
        cancel_task.cancel()
        if get_task not in done:
            get_task.cancel()
            return  # interrupted — the producer exits on its own next chunk
        kind, payload = get_task.result()
        if kind == "chunk":
            yield payload
        elif kind == "error":
            raise payload
        else:
            return
```

三個值得記住的細節：

| 細節 | 為什麼 |
|---|---|
| producer 在 thread 裡讀 `self._cancel.is_set()` | `asyncio.Event` 的 flag 讀取是安全的（只讀不寫）；不需要額外的 threading.Event |
| 用 `("chunk"/"error"/"done", payload)` tuple 而非 sentinel | 例外要跨執行緒傳回並在 consumer 端 `raise`，才能被 `_loop` 的 except 抓到 |
| consumer 端 race `queue.get()` vs `_cancel.wait()` | 串流「卡住不吐 chunk」時（等第一個 token、連線 wedge），producer 的 break 檢查永遠不會執行 |

第三點是最容易漏的：**producer 的 cancel 檢查只在收到 chunk 時才會跑**。
如果 provider 一個 chunk 都不吐，那個 `break` 永遠等不到。所以 consumer 端必須自己 race。

### 4.3 對比：如果用 `asyncio.to_thread` 包整個串流

```
方案 A：to_thread(lambda: list(provider.stream(...)))
  ✗ 沒有即時 delta，使用者盯著空白畫面 20 秒
  ✗ 無法中途中斷

方案 B：本文的 thread + queue + race
  ✓ 即時 delta
  ✓ 任何狀態可中斷
  ✗ 程式碼多 30 行

方案 C：用 provider 的 async SDK
  ✗ 要求所有 7 家 provider 都有 async 實作且行為一致
  ✗ Ollama / 各種 compat server 的 async 支援參差
```

OpenWorker 選 B，並且把 `ProviderClient` 明確定義成同步介面 —— **統一在一個地方處理
非同步橋接，比要求 7 個 provider 實作都正確處理 async 更可靠**。

---

## 五、工具呼叫：授權、分流、執行

### 5.1 兩階段：先全部授權，再執行

```python
async def _handle_tool_calls(self, tool_calls: list[ToolCall]) -> AsyncIterator[Event]:
    """Run one assistant turn's tool calls: authorize all of them first (sequentially —
    approval prompts are interactive), then execute. Low-risk calls (reads, searches)
    run concurrently; everything else runs one at a time in call order."""
```

**為什麼要先全部授權？** 因為批准是互動的。如果邊授權邊執行，
使用者會看到「批准 → 跑 → 批准 → 跑」的鋸齒體驗；先全部問完，
使用者可以一次看清楚這一輪要做哪些事。

```
        模型回傳 4 個 tool_calls
                 │
      ┌──────────┴───────────┐
      ▼  階段一：授權（序列） ▼
 ┌─────────────────────────────────────────────────────────┐
 │ grep              → READ      → 自動允許                 │
 │ read_file         → READ      → 自動允許                 │
 │ write_file        → WRITE     → 路徑檢查 → 需批准 → 等人  │
 │ send_message      → EXTERNAL  → 需批准 → 等人             │
 └─────────────────────────────────────────────────────────┘
                 │
      ┌──────────┴───────────┐
      ▼  階段二：執行（分流） ▼
 ┌───────────────────────────┐   ┌──────────────────────────┐
 │ 併發組（_parallel_safe）  │   │ 序列組                    │
 │ ─────────────────────     │   │ ─────────────────        │
 │ grep      ┐               │   │ write_file               │
 │ read_file ┘ gather()      │   │      ↓                   │
 │                           │   │ send_message             │
 └───────────────────────────┘   └──────────────────────────┘
```

### 5.2 `_parallel_safe` 的判準只有兩條

```python
def _parallel_safe(self, tool_call: ToolCall) -> bool:
    # Only metadata-declared low-risk tools (reads, searches, git queries) run
    # concurrently; writes, shell, and anything unannotated stay strictly ordered.
    spec = self.registry.get(tool_call.name)
    metadata = spec.metadata if spec else None
    return getattr(metadata, "risk_level", "") == "low" and not getattr(
        metadata, "requires_approval", False
    )
```

注意 **「anything unannotated stay strictly ordered」** —— 沒有宣告 metadata 的工具
預設是序列的。這是正確的 fail-safe 方向：**未知 = 保守**。

實測影響：一個典型的「探索程式碼」turn 會產生 3–6 個 grep/read，
併發後從 ~4.5 秒降到 ~1.2 秒。

### 5.3 三個「繞過權限系統」的特殊工具

```python
# `request_directory` and `propose_plan` are interactive: the user decides
# out-of-band and that decision IS the consent, so they skip the
# permission/registry path.
if tool_call.name == "request_directory": ...
if tool_call.name == "propose_plan": ...
if tool_call.name == "ask_user": ...
```

這三個工具**由引擎直接攔截，不進 registry、不進權限引擎**。理由很漂亮：
它們的執行結果就是「問使用者一個問題」，而**使用者的回答本身就是同意**。
再套一層「你要允許 agent 問你問題嗎？」是荒謬的。

### 5.4 Out-of-band 批准的型別簽章

```python
class ApprovalOutcome(str, Enum):
    ONCE = "once"
    ALWAYS_TOOL = "always_tool"
    ALWAYS_COMMAND = "always_command"
    DENY = "deny"

@dataclass
class PermissionRequest:
    tool_name: str
    arguments: dict[str, Any]
    metadata: Any
    reason: str
    tool_call_id: Optional[str] = None  # for durable resume (idempotent inbox item)

Approver = Callable[[PermissionRequest], Awaitable[ApprovalOutcome]]

async def _deny_all(_request: PermissionRequest) -> ApprovalOutcome:
    return ApprovalOutcome.DENY
```

**預設是 `_deny_all`。** 沒注入 approver 的引擎（例如子代理）不會誤放行任何需批准的操作。

而 `tool_call_id` 這個欄位是整個 durable resume 機制的錨點 —— Part 3 會詳談。

---

## 六、中斷：四種狀態與一個不變式

這是我認為整個檔案裡最見功力的部分。

### 6.1 「按 Stop」可能發生在哪些狀態

```python
def request_interrupt(self) -> None:
    """Stop the turn as soon as possible, from ANY state: mid-stream (the producer
    thread drops the stream between chunks), mid-tool (interrupt hooks kill the
    running command), awaiting an approval/question/plan (the await resolves as
    interrupted), or between iterations (the loop checkpoint). Every pending
    tool_call still gets a tool-error result so the history never carries orphans
    (hosted templates reject them, and durable-resume would re-prompt them)."""
    self._cancel.set()
    for hook in self._interrupt_hooks:
        try:
            hook()
        except Exception:
            pass  # best-effort: a dead executor must not block the stop
```

```
┌────────────────────────────────────────────────────────────────────────┐
│  狀態 A：串流中                                                          │
│    → producer thread 在下一個 chunk 之間 break                          │
│    → consumer 的 race 立刻返回                                          │
│    → 保住已串流的文字，append notice("interrupted")                     │
├────────────────────────────────────────────────────────────────────────┤
│  狀態 B：工具執行中（shell 指令跑到一半）                                │
│    → interrupt_hooks 呼叫 executor.interrupt_now()                      │
│    → POSIX: SIGINT 給前景子程序 / Windows: Ctrl-Break 給程序群組         │
│    → ★ shell 本身活著，session 狀態（cwd、env）保留                     │
├────────────────────────────────────────────────────────────────────────┤
│  狀態 C：等待批准 / 提問 / 計畫審核                                       │
│    → _interruptible() 的 race 讓 await 提早以 interrupted 解決           │
│    → 原本的 task 被 cancel，所以「稍後才回答的 Inbox 卡片」變成 no-op    │
├────────────────────────────────────────────────────────────────────────┤
│  狀態 D：迴圈輪次之間                                                    │
│    → ⑧ 的檢查點                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

`_interruptible` 的實作：

```python
async def _interruptible(self, coro: Any, interrupted: Any) -> Any:
    """Await `coro`, but resolve early with `interrupted` if the user stops the
    turn. The pending task is cancelled so an answered-later Inbox card no-ops."""
    task = asyncio.ensure_future(coro)
    cancel_wait = asyncio.ensure_future(self._cancel.wait())
    try:
        done, _ = await asyncio.wait({task, cancel_wait},
                                     return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return task.result()
        task.cancel()
        return interrupted
    finally:
        cancel_wait.cancel()
```

注意 `finally: cancel_wait.cancel()` —— 不取消的話，每次呼叫都會在 `_cancel` 上
留一個 waiter，長 session 會累積成記憶體洩漏。

### 6.2 不變式：歷史裡不能有孤兒 tool_call

```python
def _interrupted_tool(self, tool_call: ToolCall) -> Event:
    """The stop-path answer for a call that will not run: a tool-error result in the
    history (hosted chat templates reject orphaned tool_calls, and durable-resume
    would otherwise re-prompt it) + the finished event for the tool card."""
    self.messages.append(_tool_error_message(tool_call, "interrupted by user"))
    ...
```

**為什麼這麼重要？** 兩個具體後果：

1. **Hosted chat template 會直接拒絕**：像 Together / Fireworks 上的開源模型，
   chat template 會檢查每個 `tool_calls` 都有對應的 `tool` 訊息，缺一個就 400。
2. **Durable resume 會重複提問**：`_unanswered_trailing_tool_calls()` 靠
   「有 tool_calls 但沒有 tool 結果」來判斷「這一輪停在哪」。留孤兒 = 重啟後
   會重新問使用者一次已經取消的批准。

```python
def _unanswered_trailing_tool_calls(self) -> list[ToolCall]:
    """The tool-calls of the last assistant message that don't yet have a tool result —
    i.e. the prompt we suspended on (+ any after it). Reconstructed from the persisted thread."""
    answered = {m.get("tool_call_id") for m in self.messages if m.get("role") == "tool"}
    for msg in reversed(self.messages):
        if msg.get("role") == "user":
            return []
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            out: list[ToolCall] = []
            for tc in msg["tool_calls"]:
                if tc.get("id") in answered:
                    continue
                ...
```

**整個 durable resume 機制，是純粹從持久化的訊息串重建出來的。**
沒有額外的 state machine、沒有 checkpoint 檔案。訊息串就是狀態。這個設計非常乾淨。

---

## 七、`_outbound_messages()`：canonical vs outbound

### 7.1 這是唯一的 provider 餵送路徑

```python
def _outbound_messages(self) -> list[dict[str, Any]]:
    """`self.messages` prepared for the provider. The SOLE provider feed (see `_astream`)."""
```

「THE SOLE provider feed」—— 只有一個出口，所有轉換集中在這裡。這是很重要的紀律：
如果有兩個地方會組裝送給 provider 的訊息，遲早會有一個忘記剝側車。

### 7.2 五道轉換，依序執行

```
self.messages（canonical，永不被修改）
        │
        ▼
① compaction.apply_to_outbound(messages, compaction_state)
   boundary 之前的訊息 → 一個 <compacted-history> 區塊
        │
        ▼
② 丟掉所有 role == "notice" 的訊息
   剝掉 source / _display / ts / reasoning / usage 側車
   （只複製有側車的訊息，避免不必要的 dict 複製）
        │
        ▼
③ PDF 適配：if 當前模型不支援原生 PDF
   → pdf_support.adapt_content()：本地文字抽取 / 頁面圖片
        │
        ▼
④ 圖片適配：if 當前模型無 vision
   → 換成 "[image attachment — not viewable by this model]" 佔位符
        │
        ▼
⑤ 附加 <system-context> 到「最後一則 user 訊息」
   內容 = plan/discuss 模式提醒 + 目前資料夾清單 + 即時 skill 選單
        │
        ▼
   送給 provider（self.messages 完全沒被動到）
```

### 7.3 為什麼 ③④ 要「每次呼叫都重新決定」

```python
# PDF attachments (stored as `file` parts) are adapted to the ACTIVE model right
# here — never in the persisted history — so a mid-session model switch always
# re-decides: native PDF models get the real document, the rest get the local
# text-extract/page-image fallback (pdf_support.py).
```

使用者可以在 session 中途換模型（`switch_model`）。如果 PDF 在存入歷史時就被
降級成文字，之後換到支援 PDF 的模型也拿不回原檔了。**降級必須是 outbound-only 的。**

### 7.4 為什麼 `<system-context>` 掛在 user 訊息上

```python
# Returns an ephemeral `<system-context>` block appended to the LAST user message at
# send-time only (never persisted). We can't reliably inject system messages mid-thread
# across providers, so dynamic per-turn context (e.g. the live directory list) rides on
# the latest user turn. Returns "" when there's nothing to add.
```

**「We can't reliably inject system messages mid-thread across providers」**
—— Anthropic 的 API 根本沒有 mid-thread system message；OpenAI 有但行為不穩；
Gemini 又是另一套。所以動態 context 一律掛在最後一則 user 訊息尾巴。

這個 context 每一輪都重算，所以：

- 中途切換到 plan mode → 下一則訊息就開始出現 plan mode 提醒
- 使用者中途授權新資料夾 → 下一則訊息模型就知道
- 使用者在 Settings 裡停用某個 skill → 下一則訊息選單就少一項

而「停用」還有一個很細膩的處理：

```python
# Disable countermand (§3): instructions already loaded into this conversation keep
# steering the model even after the skill is turned off/deleted — history can't be
# un-read. So a loaded-but-no-longer-available skill gets an explicit stop note,
# recomputed fresh each turn (re-enable → the note disappears; never persisted).
for name in sorted(_loaded_skill_names(eng.messages) - available):
    parts.append(
        f'Note: the skill "{name}" has been disabled by the user — stop '
        "following its instructions from here on."
    )
```

**「history can't be un-read」** —— 已經載入 context 的 skill 指令，
把選單項目拿掉是沒用的，必須明確下一道反命令。這是很少人想到的細節。

---

## 八、其他四個入口：retry / resume / steering / switch_model

### 8.1 `retry()` — provider 錯誤後重跑

```python
async def retry(self) -> AsyncIterator[Event]:
    """Re-run the model loop after a provider error — no new user message; the failed
    turn's input is already the tail of history. Guarded on the tail being an error
    notice so a stray retry frame can't re-answer a completed turn. Trailing
    model_switch notices don't break the guard — switching models and THEN retrying
    is the intended recovery path (owner-hit 2026-07-23)."""
    if not self._tail_is_retriable_error():
        return
```

守衛邏輯：

```python
def _tail_is_retriable_error(self) -> bool:
    """True when the history tail is an error notice, looking through any model_switch
    notices appended after it (a switch must not consume the retry)."""
    for message in reversed(self.messages):
        if message.get("role") != "notice":
            return False
        if message.get("kind") == "model_switch":
            continue
        return message.get("kind") == "error"
    return False
```

註解裡的 `(owner-hit 2026-07-23)` 表示這是真實遇到的 bug：
使用者遇到 GPT 額度用盡 → 切換到 Claude → 按 retry，結果 retry 被
中間插入的 `model_switch` notice 擋掉了。修法是「看穿」model_switch。

### 8.2 `resume()` — 跨進程重啟後續跑

```python
async def resume(self) -> AsyncIterator[Event]:
    """Continue a turn that was suspended at a prompt and persisted — durable resume after a
    restart (or engine eviction). Re-process the trailing assistant message's UNANSWERED
    tool-calls (the prompt callbacks find the already-resolved Inbox item and return without
    re-prompting; answered calls are skipped, so nothing double-executes), then run the model
    loop to finish the turn."""
```

關鍵在於**冪等性**：重跑那些未回答的 tool_call 時，
`inbox_approver` 會發現「這個 `(session_id, tool_call_id)` 的 Inbox 項目已經存在且已解決」，
於是直接回傳答案，不會再問一次人。

### 8.3 `queue_steering()` — 邊跑邊插話

```python
def queue_steering(self, text: str, source: Optional[dict] = None) -> None:
    self._steering.append((text, source))
```

使用者在 agent 跑到一半輸入「等等，不要動 config 檔」，不會打斷當前輪次，
而是排隊；在下一個安全點（工具執行完 / 模型停止呼叫工具時）注入為 user 訊息。

注意 ⑥ 的邏輯：**模型不再呼叫工具時，如果有 steering，就 `continue` 而不是結束**。
這讓「插話」不會被誤判成新的一輪對話。

### 8.4 `switch_model()` — 中途換模型

```python
def switch_model(self, model: str) -> Optional[str]:
    """Rebind the session's model mid-conversation (roadmap item 3). History is
    canonical OpenAI shape and every provider converts per call, so the switch is just
    the field write — plus a persisted notice marking WHERE it happened, with a
    degradation warning when history carries images the new model can't see."""
```

**「the switch is just the field write」** —— 這是把歷史保持在
canonical OpenAI 形狀所換來的好處。每個 provider 在自己的 `complete()` 裡轉換，
所以換模型不需要重寫歷史。

---

## 九、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **AsyncIterator[Event]**<br>vs callback / 回傳值 | 一個 turn 有 10+ 種進度訊號要即時送到 UI；async generator 天然是背壓正確的 | callback 難以中斷、難以測試；回傳值等到最後才有東西 | 純 batch 場景（無 UI）用回傳值更簡單 |
| **同步 ProviderClient**<br>vs async provider | 只需在一處（`_astream`）正確處理執行緒橋接；7 家 provider 的 async 支援參差不齊 | 要求每個 provider 實作都正確處理 async 取消語意，錯誤面積大 | 只支援 1–2 家有成熟 async SDK 的 provider 時 |
| **低風險工具併發**<br>vs 全部序列 | 探索型 turn 常有 3–6 個 grep/read，併發後從 4.5s → 1.2s | 寫入併發會產生 race，shell 併發會破壞 cwd 狀態 | 工具全部無副作用時可全併發 |
| **notice role**<br>vs 存在別的表 | 錯誤 / 中斷標記跟 transcript 天然同生命週期；重載自動還原順序 | 另開一張表要自己維護「這個錯誤發生在第幾則訊息之後」 | 需要對錯誤做結構化查詢統計時 |
| **從訊息串重建 resume 狀態**<br>vs checkpoint 檔 | 訊息串本來就要持久化；沒有第二份狀態可以不同步 | checkpoint 與訊息串可能不一致，且要處理版本遷移 | 恢復點需要包含非訊息狀態（如外部交易 ID）時 |
| **max_iterations = 12**<br>vs 無限 | 模型卡在失敗工具上反覆重試是最常見的失控模式 | 無限迴圈會燒完額度且使用者無感 | 長時間 agentic 任務可調高，但應搭配成本上限 |

---

## 十、系列導航

- [Part 1：架構全景 — 一個能交付成果的桌面 AI 同事](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
- **Part 2（本篇）：TurnEngine — Agent 迴圈的完整解剖**
- [Part 3：Harness — 權限模型、Inbox 與人機協作](/yennj12_blog_V4/posts/openworker-intro-part3-harness-permissions-inbox-zh/)
- [Part 4：LLM 層 — Provider 抽象與 Context 自動壓縮](/yennj12_blog_V4/posts/openworker-intro-part4-llm-provider-compaction-zh/)
- [Part 5：能力擴充 — Tools、Skills、Personas、MCP 與排程](/yennj12_blog_V4/posts/openworker-intro-part5-tools-skills-mcp-automation-zh/)

---

## 本篇可以帶走的五個模式

1. **Canonical history ≠ outbound view**：持久化的訊息可以帶任意側車，
   但送給 provider 前必須經過**唯一一個**剝除函式。
2. **Blocking → async 橋接要 race 兩端**：producer 檢查 cancel 只在有資料時執行，
   consumer 也必須 race，否則「卡住不吐資料」的串流會鎖死 turn。
3. **不留孤兒 tool_call**：任何提早結束的路徑，都要為每個 pending tool_call 補一筆錯誤結果。
4. **降級決策要 per-call，不要寫進歷史**：模型可以中途切換，
   歷史必須保留最高保真度的原始資料。
5. **未知 = 保守**：`_parallel_safe` 對沒有 metadata 的工具回傳 False，
   `approver` 預設 `_deny_all`。fail-safe 的方向要一致。

> 本文分析基於 2026-08 的 `main` 分支（commit `01b6f83`）。
