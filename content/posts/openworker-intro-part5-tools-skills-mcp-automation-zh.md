---
title: "OpenWorker 深度解析（五）：能力擴充 — Tools、Skills、Personas、MCP 與排程"
date: 2026-08-07T13:00:00+08:00
draft: false
weight: 5
description: "拆解 OpenWorker 的五層能力擴充體系：ToolRegistry 與封閉式 Capability 目錄、Persona 作為資料而非程式碼、Skills 的漸進式揭露、explore 子代理的 context 隔離、MCP 客戶端的單任務生命週期，以及排程器的 catch-up 與 skip-on-overlap 策略。"
categories: ["engineering", "ai", "all"]
tags: ["OpenWorker", "AI Agent", "MCP", "Agent Skills", "Tool Use", "Multi-Agent", "Python", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
series: ["openworker-intro"]
---

> *「加一個工具」聽起來是最簡單的事。*
> *但如果任何人都能加，權限模型就沒有意義；*
> *如果每個工具都塞進 system prompt，200 個工具會吃掉半個 context window；*
> *如果工具的定義只能寫在程式碼裡，非工程師就永遠無法擴充這個系統。*
> *OpenWorker 對這三個問題給了三個不同層次的答案。*

---

本篇是 [OpenWorker 深度解析系列](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
的最後一篇。前四篇拆完了迴圈、外殼與 LLM 層，這一篇處理「這個系統怎麼長大」。

---

## 一、五層能力模型

OpenWorker 的能力擴充不是一個機制，是**五個層次不同的機制**，
彼此的信任邊界與擴充者身分都不一樣：

```
┌───────────────────────────────────────────────────────────────────────────┐
│ L5 · Automation（排程 / 自我喚醒）        擴充者：使用者（GUI 或 agent 自己）│
│      「什麼時候跑」                        信任：綁定 standing rules        │
├───────────────────────────────────────────────────────────────────────────┤
│ L4 · Skills（SKILL.md）                   擴充者：任何人（含 agent 自己）    │
│      「怎麼做這件事」= 純指令              信任：無新工具，只有 prompt      │
├───────────────────────────────────────────────────────────────────────────┤
│ L3 · Personas（Markdown + YAML）          擴充者：第三方（可安裝）          │
│      「我是誰、我用哪些能力」              信任：只能引用既有 capability     │
├───────────────────────────────────────────────────────────────────────────┤
│ L2 · MCP / Connectors                     擴充者：使用者接上 / 平台維護     │
│      「我能碰哪些外部系統」                信任：MCP 預設保守；connector 精選│
├───────────────────────────────────────────────────────────────────────────┤
│ L1 · Capability Catalog（catalog.py）     擴充者：★ 只有平台               │
│      「有哪些原生能力」                    信任：封閉，不接受第三方新增      │
└───────────────────────────────────────────────────────────────────────────┘
```

`catalog.py` 的註解把這條界線劃得很明白：

```python
"""The catalog is **platform-owned and closed**: third parties get breadth from us adding
vetted capabilities here and from MCP, never by adding entries. MCP tools are *not* in the
catalog (see ``PERMISSIONS-AND-INBOX.md``)."""
```

**「platform-owned and closed」** —— 這是刻意的。如果第三方 persona 能往目錄裡塞
capability，那 persona 的安裝同意畫面（列出「這個 persona 會用到 shell」）就形同虛設。

---

## 二、L1：ToolRegistry 與 Capability 目錄

### 2.1 ToolRegistry：71 行

```python
@dataclass
class ToolSpec:
    name: str
    schema: dict[str, Any]      # OpenAI 格式的 function tool schema
    func: Callable[..., Any]
    metadata: Any = None        # aisuite ToolMetadata or None

class ToolRegistry:
    def register(self, func, *, metadata=None, schema=None) -> ToolSpec:
        name = getattr(func, "__name__", None)
        if not name:
            raise ValueError("Tool function must have a __name__.")
        meta = metadata or getattr(func, "__aisuite_tool_metadata__", None)
        # Allow an explicit schema override (param or a `__coworker_schema__` attribute)
        # for tools whose signature can't be auto-converted to a valid JSON schema.
        resolved_schema = (
            schema or getattr(func, "__coworker_schema__", None) or _schema_for(func)
        )
        ...
```

三層 schema 解析：**明確傳入 > `__coworker_schema__` 屬性 > 從 docstring/type hint 自動產生**。

第二層存在的理由是 MCP：MCP 工具的 Python wrapper 是 `def _invoke(**kwargs)`，
自動產生的 schema 會是空的。所以要用 MCP server 回報的 `inputSchema` 覆蓋。

註解也明確劃了職責邊界：

```python
"""Permission checks live in the PermissionEngine and are applied by the turn engine,
not here."""
```

**Registry 只管「有哪些工具、怎麼呼叫」，不管「能不能呼叫」。** 這個切分讓
權限邏輯只有一個地方，不會散在工具實作裡。

### 2.2 Capability：id → 一組工具 + context 需求 + 風險

```python
@dataclass(frozen=True)
class Capability:
    id: str
    name: str                    # 人類可讀標籤（安裝同意畫面用）
    description: str
    build: Callable[[AgentContext], list]
    requires: tuple[str, ...] = ()          # "workspace" / "executor" / "todo"
    risk: tuple[RiskClass, ...] = (RiskClass.READ,)

    def available(self, context: AgentContext) -> bool:
        return all(_REQUIREMENTS[r](context) for r in self.requires)
```

目前六個 capability：

| id | 內容 | requires | risk |
|---|---|---|---|
| `code_files` | 單 root、行號化讀取的檔案工具 | workspace | READ, WRITE_LOCAL |
| `files` | 多 root 的檔案工具 | workspace | READ, WRITE_LOCAL |
| `git` | git_status / git_diff / git_log | workspace | READ |
| `search` | grep（ripgrep，尊重 .gitignore） | workspace | READ |
| `shell` | run_shell + 背景任務工具 | executor | EXEC |
| `todo` | todo_write（驅動 Progress 面板） | todo | READ |

`expand()` 的降級行為很優雅：

```python
def expand(ids: list[str], context: AgentContext) -> list:
    """Expand a persona's ``tools:`` id list into concrete tool callables for this context.
    Capabilities whose context prerequisites aren't met are skipped (no shell without an
    executor, no files without a workspace)."""
    tools: list = []
    for cap_id in ids:
        cap = capability(cap_id)
        if cap.available(context):
            tools.extend(cap.build(context))
    return tools
```

**沒有 executor 就自動跳過 shell，不報錯。** 這讓同一個 persona 定義能在
不同 context 下運作（有 workspace / 沒 workspace）。

`risk_summary()` 則是安裝同意畫面的資料來源：

```python
def risk_summary(ids: list[str]) -> set[RiskClass]:
    """The union of risk classes a tool list can produce — for the install-consent screen."""
```

安裝一個宣告 `tools: [files, search, shell, todo]` 的 persona，
畫面會告訴你：**這個 persona 可以讀寫檔案，並且可以執行 shell 指令。**

### 2.3 `code_files` vs `files`：一個小而重要的差別

```python
def _code_files(context):
    """Repo-oriented files: single-root, line-numbered/windowed `read_file`. Our `grep` and
    windowed `read_file` replace aisuite's slower `search_files` / `read_file`/`read_file_lines`."""

def _files(context):
    """Knowledge-work files: multi-root aware (reads/writes across the session's roots), keeps
    aisuite's `read_file`/`read_file_lines`. Only our `grep` replaces the slow `search_files`."""
```

寫程式時需要**行號**（因為要引用 `path:line`、要做精確替換）；
做知識工作時需要**多資料夾**（讀 Downloads 的 PDF，寫到 Desktop 的報告）。
兩種需求做成兩個 capability，而不是一個帶 flag 的工具。

---

## 三、L3：Persona 是資料，不是程式碼

### 3.1 一個 persona 的完整長相

`coworker/personas/builtin/ops.md`：

```yaml
---
id: ops
name: Ops Coworker
icon: wrench
tagline: Operate and investigate — runbooks, logs, infrastructure
family: knowledge
tools: [files, search, shell, todo]          # ← 只能引用 catalog 裡的 id
messaging: true
connectors: true
recommended_models: [anthropic:claude-opus-4-8, openai:gpt-5.5]
default_permission_mode: interactive
description: An operations-focused coworker for investigating incidents…
recommends:
  - connector: github
    reason: confirm deploys and inspect the PRs behind a change
    tier: core
  - connector: slack
    reason: receive alerts and reply to the team in-channel
    tier: core
  - mcp: filesystem
    reason: read runbooks and postmortems from a local folder
    tier: optional
---
You are the Ops Coworker — a careful, methodical operations engineer. …
（以下是完整的 system prompt）
```

**格式是「YAML frontmatter + Markdown body」，跟 SKILL.md 完全一樣。**
`manifest.py` 的註解說得很清楚：

```python
"""Format: YAML frontmatter (identity + capability declaration) followed by a markdown body that
is the system prompt. `persona ⊇ skill` — the same frontmatter-markdown shape as SKILL.md, with
more structured fields."""
```

`persona ⊇ skill` 這個關係很漂亮：**同一種檔案格式，不同的欄位豐富度。**
學會寫 skill 的人，自然就會寫 persona。

### 3.2 嚴格解析，失敗要大聲

```python
"""Parsing is strict: an invalid manifest raises ``ManifestError`` rather than silently
producing a broken persona (a third-party persona must fail loudly)."""

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VALID_FAMILIES = {"code", "knowledge"}
VALID_WORKSPACES = {"git", "project", "deliverable", "none"}
VALID_MODES = {"discuss", "plan", "interactive", "custom", "auto"}
```

id 的正規表達式帶著跨平台的考量：

```python
# Persona ids become directory names under the managed install area (and registry keys), so
# they are restricted to a filesystem-safe slug on every OS: no path separators or `..`
# (traversal), no `:*?"<>|` (invalid on Windows), bounded length.
```

### 3.3 生命週期：installed → enabled → surfaced

```python
"""A session is born from exactly one persona (recorded as ``SessionRecord.agent``); resolving an
id always returns its Agent even if the persona was later disabled, so live sessions keep
working. Disable/surface only affect what the *new-session* picker offers."""
```

**「resolving an id always returns its Agent even if the persona was later disabled」**
—— 停用一個 persona 不會讓正在跑的 session 崩掉，只是新對話的選單裡不再出現。
這是很重要的向後相容保證。

### 3.4 `recommends` 不做驗證

```python
@dataclass
class Recommendation:
    """A connection a persona recommends, surfaced in the per-session connections drawer. ``ref`` is a
    connector id or an MCP server name; ``reason`` is the value it unlocks; ``tier`` ranks it. Not
    validated against shipped connectors — a persona may recommend one we don't ship yet."""
```

**「a persona may recommend one we don't ship yet」** —— 這是刻意留白：
第三方 persona 可以推薦 `datadog`、`pagerduty` 這些平台還沒做的 connector，
形成一份「使用者想要什麼」的需求訊號，而不是安裝時直接報錯。

---

## 四、L4：Skills 的漸進式揭露

### 4.1 核心問題

假設你有 30 個 skill，每個 skill 的完整指令平均 2,000 tokens。
全部塞進 system prompt = 60,000 tokens，**在對話開始前就吃掉半個 context**。

而其中 29 個跟當前任務無關。

### 4.2 兩階段揭露

```python
"""Progressive disclosure: at session start only the catalog (name + description) is injected
into the agent's context; the full body is loaded on demand via the `load_skill` tool."""
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 階段一：目錄注入（每一輪都重算，透過 context_provider）                    │
│                                                                          │
│  Available skills — call load_skill(name) to load one's full             │
│  instructions when it's relevant to the task:                            │
│  - 10k-digest: Deep-read a 10-K annual report and output a digest…       │
│  - incident-report: Write a postmortem from an incident timeline…        │
│  - … （30 個 × 約 30 tokens = 900 tokens）                                │
├──────────────────────────────────────────────────────────────────────────┤
│ 階段二：按需載入                                                          │
│                                                                          │
│  模型呼叫 load_skill("10k-digest")                                        │
│    → {"name": …, "instructions": <完整 2000 tokens>,                     │
│       "resources_path": "/…/skills/10k-digest"}                          │
│                                                                          │
│  ★ resources_path 讓 skill 可以附帶腳本與範本，模型用檔案工具去讀         │
└──────────────────────────────────────────────────────────────────────────┘
```

**60,000 → 900 tokens（載入一個後 2,900）。**

### 4.3 Skill 的儲存：資料夾即真理

```python
"""Scope = folder location (folder-is-truth): global skills live in ``state_dir()/skills``,
project skills in ``<workspace>/.coworker/skills``. There is no database; every operation
is a folder + ``SKILL.md`` operation, which keeps project skills shareable via git for free."""
```

**「keeps project skills shareable via git for free」** —— 專案 skill 放在
repo 裡的 `.coworker/skills/`，`git clone` 就自動帶著走。零額外機制。

但「停用」狀態刻意不放在資料夾裡：

```python
"""Disable state is deliberately NOT a marker inside the skill folder: project folders travel
with the repo and one user's disable must not be committed to teammates. It lives in the
personal ``state_dir()/skills-settings.json`` instead."""
```

**「one user's disable must not be committed to teammates」** —— 這是很細膩的
多人協作考量。你嫌某個 skill 吵把它關掉，不該影響同事。

### 4.4 三個運行時細節

**① 每一輪都 rescan，所以「即時生效」**

```python
skill_loader.rescan()
allowed = skill_filter() if callable(skill_filter) else skill_filter
skills_ctx = skill_catalog_text(skill_loader, allowed=allowed)
```

註解：

```python
# Live skill menu (SKILLS-SPEC §4.1): recomputed every turn like the roots list, so
# a skill installed/enabled/disabled mid-session applies from the NEXT MESSAGE —
# no new session, no lost context.
```

**② `skill_filter` 是 callable 而非 set**

```python
"""`allowed` gates load_skill: a set is a build-time snapshot; a CALLABLE is consulted
on every call — the manager passes one so Settings disables apply to live sessions
immediately, and skills created after the engine was built are still loadable
(loader rescans on a miss)."""
```

**③ 停用的反命令（Part 2 提過，這裡是完整脈絡）**

```python
def load_skill(name: str) -> dict:
    skill = loader.get(name)
    if skill is None:
        loader.rescan()   # created after this session started? pick it up now
        skill = loader.get(name)
```

而已經載入的 skill 被停用時：

```
Note: the skill "10k-digest" has been disabled by the user — stop
following its instructions from here on.
```

**「history can't be un-read」** —— 這句話值得所有做 agent 的人記住。

### 4.5 `save_skill`：讓 agent 自己寫 skill

```python
"""Build the `save_skill` tool (SKILLS-SPEC §5.2). `requires_approval=True` routes every
call through the standard approval card — the tool's ARGUMENTS are the review surface,
which is why the schema carries the full instructions and file list. Bundled files may
only be read from `allowed_dirs` (the session's roots): the worker must never bundle
arbitrary machine paths into a skill."""
```

兩個設計亮點：

1. **「the tool's ARGUMENTS are the review surface」** —— 不需要另外做一個
   「skill 審查介面」。因為 `save_skill` 需要批准，而批准卡本來就會顯示完整參數，
   所以使用者自動看到完整的 skill 內容。**用既有機制解決新需求。**
2. **`allowed_dirs` 限制打包來源** —— agent 不能把 `~/.ssh/id_rsa` 打包進 skill 再匯出。

---

## 五、Memory：可修訂的長期記憶

### 5.1 三個工具，一個關鍵設計

```python
"""Memory tools — the agent's explicit write paths into memory.

`remember` saves a new fact; `memory_update` / `memory_forget` revise or retire one by
the [#id] shown in the known-memories block, so corrections replace stale facts instead
of piling up next to them."""
```

```python
def format_memories(items: list[MemoryItem]) -> str:
    """Render memories for injection into the system prompt. Ids are shown so the agent
    can revise a memory (`memory_update`) or retire it (`memory_forget`)."""
    lines = [f"- [#{item.id}] {item.content}" for item in items]
    return "Known memories (from earlier sessions):\n" + "\n".join(lines)
```

**注入時帶上 `[#id]`，是為了讓修訂可定址。** 這是很多 memory 實作漏掉的一步
—— 只能新增不能修改的記憶，最後會變成一堆互相矛盾的陳述。

### 5.2 何時該記，寫在 prompt 裡

```python
_MEMORY_GUIDANCE = """\
Memory:
- You have persistent memory across sessions. Use `remember` for durable facts: the user's \
corrections and stated preferences (include the why), and project context you couldn't \
rederive from the code. Don't save what the repo already records (code structure, git \
history, AGENTS.md) or details that only matter to the current task. Use absolute dates, \
never "yesterday".
- Before saving, check the known-memories list: if an entry already covers it, revise that \
entry with `memory_update` instead of adding a near-duplicate; retire wrong or obsolete \
entries with `memory_forget`.
- Memories reflect when they were written. If one names a file, flag, or URL, verify it \
still exists before relying on it."""
```

四條規則，每一條都對應一個真實的失敗模式：

| 規則 | 防止的失敗 |
|---|---|
| 「不要記 repo 已經記錄的東西」 | memory 變成 codebase 摘要，佔空間又會過時 |
| 「用絕對日期，不要用『昨天』」 | 三個月後讀到「昨天決定的」完全沒有資訊量 |
| 「先查清單，重複就用 update」 | 同一個偏好被記 5 次，措辭略有不同 |
| 「記憶反映寫入當下；引用檔案前先確認還在」 | 依據過時的記憶去改一個已被刪除的檔案 |

而註解裡的一句話說明了為什麼這段指引必須存在：

```python
# When-to-remember rules, injected only when a memory store is wired. Without these,
# models either never call `remember` or save noise the repo already records.
```

**「either never call it or save noise」** —— 沒有明確指引時，模型會走向兩個極端。

---

## 六、L2a：MCP client 的兩個工程難點

### 6.1 難點一：anyio cancel scope 的任務綁定

```python
"""MCPManager — our own thin async MCP client over the official `mcp` SDK.

Async-native (no `nest_asyncio`, no second event loop): each server runs in a dedicated
asyncio task that opens the transport + `ClientSession`, keeps them alive until shutdown,
then closes them in the *same* task — required because the SDK's transports use anyio cancel
scopes that must be entered and exited on one task. Tool calls are awaited from any task on
the same loop, which is safe."""
```

這是實務上很容易踩到的坑：**anyio 的 cancel scope 必須在同一個 task 裡進入與離開**，
否則會拋 `RuntimeError: Attempted to exit cancel scope in a different task`。

解法是「每個 server 一個常駐 task」：

```python
async def _serve(self, server, ready: asyncio.Future, *, interactive=False) -> None:
    try:
        async with AsyncExitStack() as stack:
            ...
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            conn = _Conn(session, list(listed.tools))
            if not ready.done():
                ready.set_result(conn)      # ← 用 Future 把連線交給呼叫者
            await conn.shutdown.wait()      # ← task 停在這裡，直到關閉訊號
    except Exception as exc:
        if not ready.done():
            ready.set_exception(exc)        # ← 連線失敗也要傳播出去
    finally:
        self._conns.pop(server.name, None)
        self._tasks.pop(server.name, None)
```

```
┌─────────────────────────────────────────────────────────────────────┐
│  呼叫端 task                     專屬的 _serve task                  │
│                                                                     │
│  ensure(server)                                                     │
│      │  create_task(_serve(...))                                    │
│      ├────────────────────────────▶  進入 AsyncExitStack             │
│      │                               開 transport + ClientSession    │
│      │        ready.set_result(conn) │                              │
│      │◀─────────────────────────────┤                              │
│  conn ◀                              await conn.shutdown.wait()      │
│                                      （task 保持存活）                │
│  call(...)  ──────────────────────▶  session.call_tool()             │
│                                      （從別的 task await 是安全的）   │
│                                                                     │
│  aclose()   conn.shutdown.set() ──▶  離開 AsyncExitStack             │
│                                      ★ 與進入是同一個 task           │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 難點二：同步 registry ↔ 非同步 session

```python
def _invoke(_remote: str = remote, **kwargs: Any) -> Any:
    future = asyncio.run_coroutine_threadsafe(call_async(_remote, kwargs), loop)
    return future.result(timeout)
```

`ToolRegistry.execute()` 是同步的（引擎在 worker thread 裡呼叫它），
但 MCP session 活在 server 的 event loop 上。`run_coroutine_threadsafe` 是唯一正確的橋。

### 6.3 名稱 sanitize 與 schema 直通

```python
_NAME_OK = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME = 64  # OpenAI function-name limit

def tool_name(server: str, tool: str) -> str:
    """`mcp__<server>__<tool>`, sanitized to OpenAI's `[A-Za-z0-9_-]{1,64}` rule."""
    base = f"mcp__{_NAME_OK.sub('_', server)}__{_NAME_OK.sub('_', tool)}"
    if len(base) > _MAX_NAME:
        base = base[:_MAX_NAME]
    return base
```

```python
# We attach the schema + metadata explicitly (rather than via `ai.tool`, which would
# try to derive a schema from this `**kwargs` wrapper): the registry reads both attrs.
_invoke.__aisuite_tool_metadata__ = ai.ToolMetadata(
    name=name, category="mcp", risk_level="medium",
    capabilities=[server.name], requires_approval=server.requires_approval,
)
_invoke.__coworker_schema__ = _openai_schema(name, mcp_tool)
```

MCP 工具的預設 `risk_level="medium"`，而 `requires_approval` 依 server 設定
—— 這就是 Part 3 提到的「保守預設」，使用者可以用 `risk_overrides.json` 放寬。

### 6.4 OAuth 的互動保護

```python
async def ensure(self, server, *, interactive: bool = False) -> _Conn:
    """`interactive=True` (explicit connect actions only) lets an OAuth server run
    the browser sign-in flow; the default refuses it — stored tokens and silent
    refresh still work, but a server that insists on re-authorization raises
    InteractiveAuthRequired instead of hijacking the user's browser."""
```

**「instead of hijacking the user's browser」** —— 半夜的排程任務不該
突然在你的瀏覽器彈出一個 OAuth 授權頁。只有使用者明確按「連線」時才允許。

---

## 七、L2b：Connectors — 33 個整合、159 個工具

### 7.1 規模與分布

```
asana 13 · browser 11 · jira 11 · monday 9 · clickup 8 · github 8 · outlook 7
close 6 · hubspot 6 · email 5 · google_calendar 5 · attio 4 · canva 4
docusign 4 · figma 4 · gitlab 4 · linear 4 · notion 4 · quickbooks 4
apollo 3 · box 3 · confluence 3 · discord 3 · dropbox 3 · gmail 3
google_drive 3 · hunter 3 · stripe 3 · zendesk 3
amplitude 2 · mixpanel 2 · posthog 2 · whatsapp 2
──────────────────────────────────────────────────────────────
33 個 connector · 159 個工具 · 13,545 行程式碼（佔後端 36%）
```

### 7.2 三個貫穿的設計

**① 憑證在執行當下讀取，絕不進 prompt**

```python
"""These tools are intentionally local-first: credentials are read from the SecretStore at
execution time and never enter prompts. OAuth-managed setup can later replace the manual
access-token fields without changing the tool surface."""
```

**② 手寫 schema 而非自動產生**

```python
def _schema(name, description, properties, required) -> dict:
    return {"type": "function", "function": {...}}
```

159 個工具全部手寫 schema。看起來很累，但這讓每個參數的描述都能針對 LLM 調校
—— 「這個欄位要填 channel ID 還是 channel name」這種歧義，自動產生的 schema 處理不了。

**③ 風險等級由 `approval` 決定**

```python
def _meta(name, *, approval: bool = False, capabilities=None):
    return ai.ToolMetadata(
        name=name,
        category="connector",
        risk_level="medium" if approval else "low",
        capabilities=capabilities or ["integration"],
        requires_approval=approval,
    )
```

`requires_approval=True` → `classify()` 判為 `EXTERNAL` → 需批准 +
**可以設 standing rule**（前提是宣告了 `target_arg`）。

### 7.3 三層開關

```
① Connector 層：已連線（有憑證）且已啟用
② Tool 層：該 connector 下的個別工具開關（tool_enabled）
③ Session 層：per-session 的 connector 過濾（connector_filter）
```

```python
def _enabled_connector_tools(secrets: SecretStore) -> tuple[set[str], set[str]]:
    connectors = {c["name"]: c for c in connector_list(secrets)}
    enabled_connectors = {
        name for name, c in connectors.items()
        if c.get("connected") and c.get("enabled")
    }
    enabled_tools = {
        tool["name"]
        for c in connectors.values()
        if c.get("name") in enabled_connectors
        for tool in c.get("tools", [])
        if tool.get("enabled")
    }
    return enabled_connectors, enabled_tools
```

**你可以連上 Gmail 但只開「讀信」不開「寄信」，而且只在某些 session 開。**

---

## 八、`explore` 子代理：context 隔離的最小實作

### 8.1 問題

「這個 codebase 裡重試邏輯在哪裡處理？」這種問題需要讀 20 個檔案，
但答案只有 3 段話。如果在主 session 裡做，20 個檔案的內容會永久佔據 context。

### 8.2 解法：一個 138 行的子代理

```python
"""The `explore` tool — a read-only research subagent with its own context window.

Broad questions ("where is retry logic handled?") burn the main session's context on
dozens of file reads. `explore` spawns a child TurnEngine over the same workspace with
read-only tools and a fresh context; only its final report returns to the caller.

The child runs in plan mode — the PermissionEngine hard-blocks writes/shell no matter
what the child decides — with no approver, so it never needs an approval round-trip.
That's what lets `explore` carry low-risk metadata, which in turn makes several explores
in one assistant turn eligible for the engine's parallel execution. No recursion: the
child registry has no `explore` tool."""
```

這段註解裡有一條漂亮的推理鏈：

```
子代理跑在 plan mode（權限引擎硬性阻擋寫入 / shell）
        ↓
所以它永遠不需要批准往返
        ↓
所以 explore 工具可以標記為 risk_level="low"
        ↓
所以引擎的 _parallel_safe 判定為 True
        ↓
所以「同時發起 3 個 explore」會併發執行
```

**安全性的設計反過來換來了效能。** 這是很少見的正向耦合。

### 8.3 三道限制

```python
permissions = PermissionEngine(workspace_root=Path(ws), mode=Mode.PLAN)   # ① 硬性唯讀
_CHILD_MAX_ITERATIONS = 10                                                # ② 迭代上限
# 子代理的 registry 只註冊 file/git/search 工具 —— 沒有 explore              # ③ 不遞迴
```

第 ③ 點：**子代理的 registry 裡沒有 `explore`，所以不會遞迴生成子代理。**
這是防止 fork bomb 的最簡單方法。

### 8.4 報告契約寫在 system prompt 裡

```python
EXPLORER_INSTRUCTIONS = """You are a read-only code explorer working inside the user's workspace. \
Answer the research task you're given by searching and reading the code (`grep`, `read_file`, \
`list_files`, `git_log`, `git_status`, `git_diff`). You cannot write files or run commands.

Your final message is your report — it goes back to the agent that spawned you, not to the \
user. Make it self-contained: answer the task directly, reference code as path:line, quote the \
key snippets, and note anything surprising you found along the way. If you couldn't find \
something, say what you searched so the caller doesn't repeat the same searches."""
```

**「say what you searched so the caller doesn't repeat the same searches」**
—— 失敗的搜尋也是有價值的資訊。這句話避免了主 agent 重跑一模一樣的查詢。

### 8.5 同步工具裡跑 async 引擎

```python
# Tools execute in a worker thread (no running loop), so asyncio.run is safe.
report, status = asyncio.run(_run())
```

因為 `ToolRegistry.execute()` 被 `asyncio.to_thread` 包著，那個 thread 裡沒有
running loop，所以 `asyncio.run` 可以安全使用。**這種細節如果搞錯就會 deadlock。**

---

## 九、L5：Automation — 排程與自我喚醒

### 9.1 兩條策略

```python
"""The scheduler loop — runs in the always-on server.

Policy (agreed): **run-once-catch-up** for runs missed while down (due tasks fire once on
startup, then resume), and **skip-on-overlap** (don't stack a run if the previous is still
going). The actual execution is injected as `runner(task, trigger) -> TaskRun` so this stays
independent of the engine/manager."""
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  run-once-catch-up                                                      │
│                                                                         │
│  電腦關機三天，每天 9:00 的任務錯過了 3 次                                │
│    ✗ 不做：開機時連跑 3 次（3 份重複的晨報）                             │
│    ✓ 做：開機時跑「一次」，然後回到正常排程                              │
│                                                                         │
│  實作：_loop() 的第一次呼叫用 trigger="catchup"                          │
├─────────────────────────────────────────────────────────────────────────┤
│  skip-on-overlap                                                        │
│                                                                         │
│  每 5 分鐘的任務，某次跑了 12 分鐘                                       │
│    ✗ 不做：堆疊 2 個並行的執行                                          │
│    ✓ 做：跳過，記 log                                                   │
│                                                                         │
│  實作：self._running_ids 集合                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.2 spawn 而非 await：一個被批准卡阻塞的任務不能卡住排程器

```python
async def _tick(self, *, trigger: str) -> None:
    for task in self.store.due():
        # Spawn, don't await: a run can suspend on a parked approval (standing
        # scoped approvals, §25) and one blocked automation must never stall the
        # scheduler loop, other due tasks, or self-wake resumption. Overlap is
        # still guarded inside run_task via _running_ids.
        spawned = asyncio.create_task(self.run_task(task, trigger=trigger))
        self._spawned.add(spawned)
        spawned.add_done_callback(self._spawned.discard)
```

這是 Part 3 的 Inbox 機制在排程層的直接後果：**一個排程任務可能懸在批准上好幾小時**。
如果排程器 `await` 它，其他所有任務都停擺。

注意 `self._spawned` 集合的用途：**保持 task 的強參照**。
`asyncio.create_task` 回傳的 task 如果沒人持有，可能被 GC 回收導致執行中斷。
這是 asyncio 的經典陷阱。

### 9.3 Self-wake：把常駐 agent 變成事件驅動

```python
"""Self-wake — tools that let a long-running agent suspend and be re-invoked on a trigger.

Converts an always-on agent into suspend/resume (event-driven, ~zero idle cost): the session
sleeps and the runtime re-invokes it when a wake is due. Two triggers here: a **timer**
(`sleep_for` / `sleep_until`) and **on-completion** (`wake_on` a backgrounded job)."""
```

```
傳統做法：agent 每 30 秒醒來檢查一次
  → 一天 2,880 次 LLM 呼叫，其中 2,879 次是「沒事，繼續睡」

Self-wake：agent 呼叫 sleep_until("09:00")
  → session 掛起（零成本）
  → 排程器的 tick 發現 wake 到期 → resume 該 session
  → 一天 1 次 LLM 呼叫
```

`wake_on`（on-completion）搭配 `run_shell(run_in_background=True)` 特別有用：
啟動一個 30 分鐘的建置，掛起，建置完成時自動醒來看結果。

排程器透過 `extra_tick` 掛鉤：

```python
if self.extra_tick is not None:
    try:
        await self.extra_tick()
    except Exception:
        logger.exception("scheduler extra_tick (wake resume) failed")
```

**排程與自我喚醒共用同一個 tick 迴圈**，沒有第二個計時器。

### 9.4 授權的 fail-closed 驗證

```python
def grant_entries(permissions: Any) -> list[str]:
    """Validate a proposed `permissions` list (from the create-tool schema or the GUI
    create payload) down to the entries actually grantable. Only `access: "write"` items
    become grants; the tool must declare a target argument (which excludes exec/destructive
    tools by construction) and the target must be non-empty. Reads are disclosure-only —
    rendered on the consent card, never stored. Anything else is dropped, fail-closed."""
```

**「which excludes exec/destructive tools by construction」** —— 這是 Part 3
講的 `target_arg` 設計的回報：因為 `run_shell` 沒有 `target_arg`，
它**在結構上就不可能**進入 standing rule。不需要額外的黑名單。

**「Reads are disclosure-only — rendered on the consent card, never stored」**
—— 同意畫面會告訴你「這個自動化會讀取你的 GitHub」，但不會為讀取建立規則
（因為讀取本來就不需要批准）。**揭露 ≠ 授權。**

---

## 十、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **Capability 目錄封閉**<br>vs 開放註冊 | 安裝同意畫面（「這個 persona 會用 shell」）只有在目錄封閉時才可信 | 第三方能塞 capability = 同意畫面失去意義 | 有沙箱化執行環境時可放寬 |
| **Persona 是 Markdown**<br>vs Python 類別 | 非工程師可寫可審；可以用 git 分享；解析失敗大聲報錯 | Python 定義的 persona 等於任意程式碼執行 | 需要動態邏輯（依時間切換 prompt）時 |
| **Skills 漸進式揭露**<br>vs 全部注入 | 30 個 skill 從 60,000 tokens 降到 900 | 全注入吃掉半個 context，且 29 個無關 | skill 數量 < 5 且都很短時 |
| **資料夾即真理**<br>vs skill 資料庫 | 專案 skill 隨 repo 走，零額外機制 | DB 要處理同步、匯入匯出、衝突 | 需要跨機器同步個人 skill 時 |
| **停用狀態放個人設定檔**<br>vs 放 skill 資料夾 | 一個人的停用不該 commit 給同事 | 放資料夾裡會污染 repo 並影響全隊 | 團隊需要統一停用某 skill 時（應另設機制） |
| **explore 跑 plan mode**<br>vs 給它 approver | 硬性唯讀 → 不需批准 → 可標低風險 → 可併發 | 給 approver 會讓子代理彈批准卡，UX 混亂且無法併發 | 子代理需要寫入時（應改成明確的 worker 概念） |
| **MCP 每 server 一個常駐 task** | anyio cancel scope 必須同 task 進出 | 用 `nest_asyncio` 或第二個 loop 會產生難以除錯的 bug | SDK 改成 task-agnostic 時 |
| **MCP 預設 medium 風險**<br>vs 依 server 自報 | 第三方 server 自報「我很安全」不可信 | 自報風險等於沒有風險模型 | 有簽章 / 審核過的 MCP registry 時 |
| **catch-up 只跑一次**<br>vs 補跑全部 | 錯過 3 天的晨報，你要的是「今天的」不是 3 份 | 補跑會產生垃圾與重複的外部副作用 | 任務是累積型（如資料同步）時應補全 |
| **排程 spawn 不 await** | 一個懸在批准上的任務不能卡住整個排程器 | await 會讓所有其他任務停擺數小時 | 任務保證不會阻塞時 |

---

## 十一、系列總結：十個可以帶回自己專案的設計

走完五篇，把整個系列的核心收斂成十條：

**架構層**

1. **Runtime 擁有 agent 迴圈，provider 只做單次呼叫**。
   權限、中斷、審計、壓縮都是應用層的職責，不該塞進 provider 抽象。
2. **Canonical history 與 outbound view 必須分離**，且 outbound 只有一個出口。
   側車剝除、壓縮套用、能力降級全部集中在那一個函式裡。

**安全層**

3. **風險是工具的宣告屬性**（4 種類別，58 行），不是權限引擎裡的 if-else。
4. **自動放行必須綁定精確目標**。`tool → target` 安全，`tool → *` 不安全，
   而沒有結構化目標的工具（shell）永遠要問。
5. **「自主權上限」與「找誰批准」是正交的兩個維度**，混在一起使用者就無法推理系統行為。
6. **爆炸半徑控制 > prompt injection 偵測**。與其猜哪段文字是攻擊，
   不如讓「即使被說服也做不了壞事」。

**可靠性層**

7. **人類決策要能離線、跨進程、冪等重放**。`(session_id, tool_call_id)`
   是最小的錨點，而狀態就是持久化的訊息串本身。
8. **不留孤兒 tool_call**。任何提早結束的路徑都要為每個 pending 呼叫補一筆結果。
9. **失敗路徑要分 attended / unattended**。背景任務永遠不該卡在內務問題上。

**context 層**

10. **漸進式揭露是預設策略**。目錄先行、內容按需；廣泛研究交給有獨立 context
    的子代理，只回收結論。

---

## 十二、系列導航

- [Part 1：架構全景 — 一個能交付成果的桌面 AI 同事](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
- [Part 2：TurnEngine — Agent 迴圈的完整解剖](/yennj12_blog_V4/posts/openworker-intro-part2-turnengine-deep-dive-zh/)
- [Part 3：Harness — 權限模型、Inbox 與人機協作](/yennj12_blog_V4/posts/openworker-intro-part3-harness-permissions-inbox-zh/)
- [Part 4：LLM 層 — Provider 抽象、能力降級與 Context 自動壓縮](/yennj12_blog_V4/posts/openworker-intro-part4-llm-provider-compaction-zh/)
- **Part 5（本篇）：能力擴充 — Tools、Skills、Personas、MCP 與排程**

---

## 參考資料

- [andrewyng/openworker](https://github.com/andrewyng/openworker) — 本系列分析的主體（MIT License）
- [andrewyng/aisuite](https://github.com/andrewyng/aisuite) — 引擎底層的統一 LLM 介面
- [Model Context Protocol](https://modelcontextprotocol.io/) — 第三方工具擴充協定
- [Agent Skills（SKILL.md 格式）](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

> 本系列分析基於 2026-08 的 `main` 分支（commit `01b6f83`）。專案仍在 open beta，
> 程式碼細節可能已變動；引用的行號與函式名以你當下 clone 的版本為準。
> 最好的閱讀方式是自己 `git clone` 一份，邊讀本文邊跳到對應檔案。
