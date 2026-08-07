---
title: "OpenWorker 深度解析（一）：架構全景 — 一個能交付成果的桌面 AI 同事"
date: 2026-08-07T09:00:00+08:00
draft: false
weight: 1
description: "從零拆解 Andrew Ng 團隊的開源專案 OpenWorker：它為什麼強調「交付成果而非聊天」、三層本地優先架構如何組成、37000 行 Python 後端的目錄職責分工，以及一次任務從輸入到產出的完整生命週期。"
categories: ["engineering", "ai", "all"]
tags: ["OpenWorker", "AI Agent", "Agent Harness", "LLM", "Python", "開源專案解析", "繁體中文"]
authors: ["yen"]
readTime: "24 min"
series: ["openworker-intro"]
---

> *大多數人看到「又一個 AI Agent 專案」，會直接跳到 README 的安裝步驟。*
> *少數人會打開 `engine.py`，想知道那個 while 迴圈長什麼樣子。*
> *但真正值得學的東西，藏在「它拒絕做什麼」裡。*
> *OpenWorker 最有價值的部分，是它對「什麼時候不該讓 Agent 自己決定」的答案。*

---

本系列共五篇，逐層拆解 [andrewyng/openworker](https://github.com/andrewyng/openworker) 這個專案：
它是什麼、核心程式碼怎麼寫、Harness（安全外殼）怎麼設計、LLM 層怎麼抽象，
以及它的能力擴充體系（Tools / Skills / Personas / MCP / Connectors）長什麼樣。

本篇是第一篇：**架構全景**。我們先建立地圖，後面四篇才鑽進程式碼。

---

## 一、核心問題：為什麼「聊天」不夠

### 1.1 Chatbot 與 Coworker 的差別

絕大多數 LLM 產品的產出是**一段文字**。你問它「幫我整理這週 Jira 上的 release 狀態」，
它回你一段 Markdown，然後你複製、貼上、修正格式、再手動貼到 Slack。

OpenWorker 的定位寫在 README 第一行：

> **AI that gets your everyday tasks done** — delivers **finished work**, not just chat.

差別在於「最後一哩路」由誰走：

```
┌──────────────────────────────────────────────────────────────────┐
│  Chatbot 模式                                                     │
│                                                                  │
│   你 ──問題──▶ LLM ──文字──▶ 你 ──手動──▶ 檔案 / Slack / 行事曆   │
│                                    ▲                             │
│                                    └── 這段仍然是人在做           │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Coworker 模式                                                    │
│                                                                  │
│   你 ──目標──▶ Agent ──工具呼叫──▶ 檔案 / Slack / 行事曆          │
│                  │                      ▲                        │
│                  └──「要送出了，OK 嗎？」┘                        │
│                             │                                    │
│                             ▼                                    │
│                       你只做「批准」這一個動作                     │
└──────────────────────────────────────────────────────────────────┘
```

這個轉換帶來的**不是體驗優化，而是全新的工程問題**：

| 從 Chatbot 變成 Coworker，新增的工程負擔 |
|---|
| Agent 會**動到真實世界**（寫檔、送訊息、改行事曆）→ 需要權限模型 |
| Agent 會**跑很久**（幾十輪工具呼叫）→ 需要 context 壓縮、中斷機制 |
| Agent 會在**沒人看著時**跑（排程、Slack 觸發）→ 需要非同步的人類決策佇列 |
| Agent 讀到的網頁 / Email **可能是攻擊者寫的** → 需要 prompt injection 防線 |
| 使用者的**金鑰與資料不該離開機器** → 需要 local-first 架構 |

這五件事就是 OpenWorker 程式碼裡佔比最大的部分。**Agent Loop 本身只有 1192 行**
（`coworker/engine.py`），而整個後端有 37,000 行。剩下的 36,000 行，幾乎都在處理上面那張表。

### 1.2 這是一個「工作範例」而不是框架

README 有一句話很關鍵：

> If you want to build your own agent harness rather than use ours, start there
> ([aisuite](https://github.com/andrewyng/aisuite)); **this repo is a working reference
> for what aisuite can carry.**

所以 OpenWorker 的定位很清楚：**它不是要你 `pip install` 的框架，而是一個可以讀、可以抄的完整實作**。
這正是它值得深度解析的原因 —— 框架會隱藏決策，工作範例會暴露決策。

---

## 二、三層架構全景

README 給了一張很簡潔的圖，我們把它展開成實際的程式碼對應：

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Layer 3 · 桌面外殼 (surfaces/gui/src-tauri/, Rust ~4 檔)                  │
│  ─────────────────────────────────────────────────────────────────────    │
│  · 挑一個空閒 localhost port，以 sidecar 方式啟動 Python server            │
│  · 產生 per-launch token，在 SPA 載入前注入（不落地到磁碟）                 │
│  · 常駐系統列：關視窗 ≠ 結束（排程 / MyHelper 繼續跑）                      │
│  · 原生能力：資料夾選取、開機自啟、caffeinate 防休眠                        │
├───────────────────────────────────────────────────────────────────────────┤
│  Layer 2 · React SPA (surfaces/gui/src/, 72 tsx + 93 ts)                   │
│  ─────────────────────────────────────────────────────────────────────    │
│  · WebSocket 消費引擎事件流；REST 打控制面 API                             │
│  · 批准卡片、Progress 面板、Inbox、Settings、Connectors 設定                │
├───────────────────────────────────────────────────────────────────────────┤
│  Layer 1 · 本地 Agent Server (coworker/, 221 py / 37,211 行)               │
│  ─────────────────────────────────────────────────────────────────────    │
│                                                                           │
│    ┌────────────┐   ┌──────────────┐   ┌───────────────┐                  │
│    │ TurnEngine │──▶│ ToolRegistry │──▶│ 檔案 / Shell  │                  │
│    │ (agent 迴圈)│   │  (159+ 工具) │   │ 33 個 Connector│                 │
│    └─────┬──────┘   └──────────────┘   │ MCP servers   │                  │
│          │                              └───────────────┘                 │
│          │          ┌──────────────────┐                                  │
│          ├─────────▶│ PermissionEngine │  ← 每次工具呼叫都問一次          │
│          │          └────────┬─────────┘                                  │
│          │                   │ needs_user                                 │
│          │                   ▼                                            │
│          │          ┌──────────────────┐                                  │
│          │          │  Inbox / 批准卡  │  ← 人類決策佇列（可離線）         │
│          │          └──────────────────┘                                  │
│          │                                                                │
│          ▼                                                                │
│    ┌──────────────────────────────────────────┐                           │
│    │ ProviderRouter → OpenAI / Anthropic /    │  ← 你的金鑰、你的模型      │
│    │ Gemini / Bedrock / Vertex / Ollama / …   │                           │
│    └──────────────────────────────────────────┘                           │
└───────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                    唯一的雲端元件：OAuth 握手中繼服務
                    （connector 授權用；可完全不使用）
```

三個層次之間的邊界是**進程邊界**，不是模組邊界。這帶來幾個具體後果：

| 設計後果 | 好處 | 代價 |
|---|---|---|
| Server 是獨立進程 | UI 崩潰不影響正在跑的排程任務；瀏覽器也能當 UI | 需要處理跨進程認證（token）與 CORS |
| Server 綁 127.0.0.1 | 外網打不到 | 同機任何進程都打得到 → 需要 Origin 白名單 + rate limit |
| Tauri 只是殼 | 同一份前端程式碼跑瀏覽器與桌面 | 原生能力要走 Tauri command 橋接 |

`coworker/server/app.py` 開頭那段註解把最後一點的威脅模型講得很白：

```python
# Origins allowed to talk to the local sidecar. It binds to 127.0.0.1, but a page in the
# user's own browser can still reach loopback — so without an origin gate, any website they
# visit could read `GET /v1/sessions` (CORS was `*`) and drive a session over the WS (which
# CORS never covers) into shell/file tools.
_ALLOWED_ORIGIN_RE = re.compile(
    r"^(tauri://localhost"
    r"|https?://localhost(:\d+)?"
    r"|https?://127\.0\.0\.1(:\d+)?"
    r"|https?://tauri\.localhost)$"
)
```

**「WebSocket 不受 CORS 保護」是很多本地服務會踩的洞**，這裡明確處理了。
另外還有三道量化限制：

```python
_WS_MAX_FRAME_BYTES = 16 * 1024 * 1024      # 單一 frame 上限 16 MiB
_WS_RATE_LIMIT_COUNT = 30                   # 每連線
_WS_RATE_LIMIT_WINDOW_SECONDS = 10.0        # 每 10 秒 30 次請求
_MAX_MESSAGE_TEXT_CHARS = 200_000
_MAX_ATTACHMENTS_BYTES = 15_000_000
```

---

## 三、Repo 導覽：37,000 行放在哪裡

```
openworker/
├── coworker/                  ← Python 後端（本系列 Part 2–5 的主戰場）
│   ├── engine.py       1192   ← TurnEngine：agent 迴圈本體
│   ├── agent.py         415   ← build_engine()：把所有零件組裝成引擎
│   ├── permissions.py   238   ← 允許 / 拒絕 / 問人
│   ├── risk.py           58   ← 四種風險類別（整個權限系統的地基）
│   ├── compaction.py    561   ← Context 自動壓縮
│   ├── inbox.py         368   ← 跨 session 人類決策佇列
│   ├── events.py         42   ← 引擎 ↔ 介面的事件契約
│   ├── secrets.py       193   ← 本地金鑰儲存（0600 檔案）
│   ├── catalog.py       180   ← 平台自有的「能力」目錄
│   ├── unattended.py     44   ← 無人值守開關
│   ├── selfwake.py      185   ← Agent 自我休眠 / 喚醒
│   ├── risk / audit / conversations / sessions / …
│   │
│   ├── providers/      4507   ← 7+ 家模型供應商 + Router + 能力矩陣
│   ├── connectors/    13545   ← 33 個 SaaS 整合、159 個工具（最大的一塊）
│   ├── tools/          1428   ← 內建工具：檔案 / grep / git / shell / todo / 子代理
│   ├── server/         6000+  ← FastAPI app + SessionManager
│   ├── skills/          785   ← Anthropic SKILL.md 格式的漸進式揭露
│   ├── personas/        769   ← 可安裝的 Agent 人格（persona ⊇ skill）
│   ├── memory/          260   ← 跨 session 長期記憶（SQLite）
│   ├── mcp/             665   ← MCP client（stdio + streamable HTTP + OAuth）
│   ├── automation/      779   ← 排程器 + 任務儲存
│   ├── web/             489   ← web_search / web_fetch + SSRF 防護
│   ├── agents/          280   ← Code / Cowork / Chat / MyHelper 四種 surface
│   └── tui/             248   ← 終端機介面
│
├── surfaces/gui/              ← React + Tauri 桌面 App
├── stt/                       ← Rust 語音轉文字 sidecar
├── packaging/                 ← DMG / Windows 安裝檔、自動更新
└── tests/                     ← 後端測試
```

**這份目錄結構本身就是一個設計聲明**。注意幾件事：

1. **`connectors/` 佔 36%（13,545 行）** —— 真正的產品價值在整合的廣度，不在 agent 迴圈的巧妙。
2. **`engine.py` 只有 1,192 行** —— agent 迴圈其實不複雜；複雜的是它周圍的一切。
3. **`risk.py` 只有 58 行，卻是整個權限系統的地基** —— 好的抽象往往很小。
4. **`personas/builtin/` 只有一個 `ops.md`** —— persona 是資料（Markdown + YAML），不是程式碼。

---

## 四、一次任務的完整生命週期

這是理解整個系統最快的路徑。假設你輸入：

> 「看一下這週 GitHub 上合併了什麼，寫成摘要，貼到 #release 頻道」

```
 使用者輸入
     │
     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ① SessionManager.get_engine(session_id)                                │
│    · 從 SQLite 讀回這個 session 的歷史訊息、模型、模式                   │
│    · 引擎已快取 → 直接回傳；否則 build_engine() 重建                    │
│    · 重建時會重新掛上：memory、skills 選單、connector 過濾、             │
│      該 session 的 standing rules（自動化任務的常設允許）               │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ② TurnEngine.run(user_input)                                           │
│    · append user message（帶 ts 時間戳側車）                            │
│    · yield TURN_START 事件 → WebSocket → React UI                      │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ③ _loop() 第 1 輪                                                       │
│    a. 檢查是否該壓縮 context（_compaction_due）                          │
│    b. _outbound_messages()：剝掉顯示用側車、套用壓縮視圖、               │
│       依當前模型能力調整 PDF / 圖片、附加 <system-context> 區塊          │
│    c. provider.stream() 在 worker thread 跑，用 queue 橋回 async loop    │
│    d. 逐 chunk yield ASSISTANT_DELTA → UI 即時顯示                      │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
              模型回傳 3 個工具呼叫：
              github_list_pulls · github_list_commits · grep
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ④ _handle_tool_calls()：先全部授權，再執行                              │
│                                                                        │
│    授權階段（序列，因為批准是互動的）：                                  │
│      github_list_pulls  → risk=READ    → Decision(True, "low risk")     │
│      github_list_commits→ risk=READ    → Decision(True, "low risk")     │
│      grep               → risk=READ    → Decision(True, "low risk")     │
│                                                                        │
│    執行階段（分流）：                                                    │
│      三個都是 risk_level=low 且不需批准 → _parallel_safe = True         │
│      → asyncio.gather(to_thread(...) × 3)  併發執行                     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
                    第 2 輪：模型寫出摘要
                               ▼
                    第 3 輪：模型呼叫 send_message
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ⑤ send_message 的風險分類 = EXTERNAL（機器外的副作用）                   │
│    PermissionEngine.evaluate() → Decision(False, needs_user=True)       │
│                                                                        │
│    engine yield PERMISSION_REQUIRED，然後 await self.approver(...)      │
│                                                                        │
│    ┌─ 有人在看（attended）→ UI 彈批准卡，使用者按「允許」                │
│    └─ 沒人在看（unattended）→ 變成 Inbox 項目，session 持久化到磁碟，    │
│         引擎可以被逐出記憶體；使用者半小時後從 Slack 按批准 →            │
│         durable resume：重建引擎、續跑那個 tool_call                     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
                       訊息送出 → TURN_END
```

這條路徑上有五個值得記住的設計，我們後面幾篇會逐一展開：

| 設計 | 在哪一步 | 哪一篇展開 |
|---|---|---|
| Canonical history vs outbound view 分離 | ③b | Part 2 |
| 低風險工具併發、寫入 / shell 嚴格序列 | ④ | Part 2 |
| 批准是 out-of-band 的 async callback | ⑤ | Part 3 |
| Inbox + durable resume | ⑤ | Part 3 |
| Context 自動壓縮 | ③a | Part 4 |

---

## 五、Local-first 的三個具體含義

「本地優先」很容易變成行銷詞。OpenWorker 把它落實成三件可驗證的事：

### 5.1 金鑰：`SecretStore`

```python
"""Secret store — one canonical, file-backed store for connector/MCP credentials.

Design (from OpenClaw): secrets **never enter the model's context, prompts, or traces**.
The store holds profiles keyed by `connector[:account]`; values may be literals OR
`${ENV_VAR}` references resolved at read time from the process env / `~/.config/coworker/.env`.

v1 is a `0600` JSON file behind this interface; the interface is what callers depend on, so
a Keychain / age-encrypted backend can swap in later without touching them.
"""
```

三個關鍵點：

1. **金鑰絕不進入模型 context** —— 這是硬規則，工具拿到的是已解析好的 client，不是字串。
2. **`0600` 檔案權限**，並且 `_restrict_to_user()` 在 Windows 上也做等價處理。
3. **介面先行**：現在是 JSON 檔，之後可換 Keychain，呼叫端不用改。

State 目錄的解析順序也考慮了跨平台：

```python
def state_dir() -> Path:
    base = os.environ.get("COWORKER_STATE_DIR")   # 1. 明確覆寫（測試 / sidecar）
    if base:
        return Path(base).expanduser()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")       # 2. Windows 原生位置
        if appdata:
            return Path(appdata) / "coworker"
    return Path.home() / ".config" / "coworker"   # 3. macOS / Linux
```

### 5.2 資料：所有東西都在你的磁碟

Session 歷史、conversation、memory、audit log、inbox 項目、skills、personas
—— 全部在 `state_dir()` 下的 SQLite / JSON 檔案。沒有帳號也能用整個 App。

### 5.3 進程：唯一的雲端元件是 OAuth 中繼

要連 Slack / Jira / Notion 這類服務，OAuth 需要一個有公開 callback URL 的服務。
OpenWorker 提供了這個中繼，但你也可以完全繞過它 —— 手動建立 API key / credential 就行。

---

## 六、建立在 aisuite 之上

OpenWorker 的引擎建立在同團隊的 [aisuite](https://github.com/andrewyng/aisuite) 上，
但**只用了兩個東西**：

```python
# coworker/tools/registry.py
from aisuite.utils.tools import Tools

def _schema_for(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate one OpenAI-format tool schema via aisuite's schema generator."""
    return Tools([func]).tools(format="openai")[0]
```

1. **從 docstring + type hint 產生 JSON Schema**（不重造輪子）
2. **`ai.ToolMetadata`**：工具的分類、風險等級、是否需要批准

而 **agent 迴圈本身是自己寫的**。`providers/base.py` 的註解說明了為什麼：

```python
class ProviderClient(ABC):
    """Single-shot, provider-agnostic completion interface.

    Deliberately blocking (the turn engine wraps it in `asyncio.to_thread`) and
    deliberately without a `max_turns` loop — the runtime owns the agent loop.
    """
```

**「the runtime owns the agent loop」** 是整個專案最重要的一句設計聲明。
Provider 層被刻意設計成「單次呼叫、不含迴圈」，因為迴圈裡要塞的東西
（權限檢查、中斷、壓縮、審計、併發分流）全都是應用層的職責。

---

## 七、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **自寫 agent loop**<br>vs LangChain / AutoGen | 每次工具呼叫都要插入權限檢查、審計、中斷檢查點；框架的 `AgentExecutor` 沒有這些擴充點 | 框架把迴圈藏起來，要插一個「批准後才執行」的 await 得靠 monkey patch | 若你的 agent 不動真實世界（純 RAG 問答），框架省下的時間划算 |
| **Provider 抽象自己做**<br>vs 只用 LiteLLM | 需要 `capabilities()` 做能力降級（無 vision 模型看到佔位符）、需要 `extras` 保存 provider 私有欄位（Gemini thought signature） | 純代理層丟失能力資訊，換模型就炸 | 只支援 1–2 家供應商時，直接用 SDK 更快 |
| **本地進程 + 你的金鑰**<br>vs 雲端 SaaS | 資料不出機器；可用 Ollama 完全離線；沒有 per-seat 訂閱 | SaaS 要你信任它處理你的 Email 與 Slack | 團隊需要集中管控與稽核時，SaaS 的治理能力更強 |
| **Tauri**<br>vs Electron | Rust 外殼 ~10MB vs Electron ~150MB；系統 WebView；原生 tray / autostart | Electron 打包大、記憶體高 | 需要精確控制 Chromium 版本行為時選 Electron |
| **SQLite / JSON 檔**<br>vs Postgres | 零安裝、單使用者、本地優先的必然選擇 | 要求使用者裝 DB 就違反了「下載即用」 | 多人共享 Inbox / 集中稽核時必須換（memory 層已預留 adapter 介面） |
| **33 個 first-party connector**<br>vs 只支援 MCP | 開箱即用；每個工具有精心設計的參數與隱私過濾 | 純 MCP 要使用者自己找 server、自己配置 | 生態成熟後，first-party 只需保留最高頻的幾個 |

---

## 八、動手跑起來

```bash
git clone https://github.com/andrewyng/openworker
cd openworker

# 1. 一次性 bootstrap：建立 .venv（Windows 用 Git Bash 或 WSL）
bash packaging/setup_dev_env.sh

# 2. 啟動本地 agent server
.venv/bin/openworker-server --cwd ~/some/project --port 8765

# 3. 另開一個終端機，啟動 UI
cd surfaces/gui
npm install
npm run dev          # 瀏覽器 UI（Vite dev port）
# 或
npm run tauri dev    # 完整桌面 App（Tauri 自己管 server）
```

環境需求：**Python 3.10+、Node 20+、Rust toolchain（僅桌面殼需要）**。

認證機制有個細節值得注意：

```
standalone server → <state-dir>/sidecar-8765.token   （0600，Vite 啟動時讀取）
desktop app       → 記憶體中的 per-launch token       （從不寫入磁碟）
```

直接打 API 時把 token 放在 `X-OpenWorker-Token` header。

測試：

```bash
.venv/bin/pytest                    # 後端
cd surfaces/gui && npm test         # GUI 單元測試
cd surfaces/gui && npm run e2e      # 密封式端對端測試
```

`coworker/testing/fake_slack/server.py`（510 行）是個亮點 —— 他們寫了一個**假的 Slack server**
來做端對端測試，而不是 mock HTTP client。這讓 connector 的整個往返路徑（含 OAuth、
event callback、thread 回覆）都能在 CI 裡跑。

---

## 九、這個專案值得學的五件事

先給結論，後面四篇逐一展開：

**① 風險是工具的宣告屬性，不是 if-else**

`risk.py` 只有 58 行，定義四種風險類別（READ / WRITE_LOCAL / EXEC / EXTERNAL），
所有權限決策都從這裡出發。原本散在權限引擎裡的 `WRITE_TOOLS` 名單被抽成資料。

**② Canonical history 與 outbound view 必須分離**

持久化的訊息串帶著大量顯示用側車（`source`、`_display`、`ts`、`reasoning`、`usage`），
送給模型前一次剝乾淨。壓縮也只改 outbound view，永不動原始歷史。

**③ 人類決策是 async callback，不是 blocking prompt**

`Approver = Callable[[PermissionRequest], Awaitable[ApprovalOutcome]]`。
同一個引擎，attended 時掛「彈 UI 卡片」的實作，unattended 時掛「寫進 Inbox」的實作。
引擎完全不知道差別。

**④ 「不留孤兒 tool_call」是硬不變式**

使用者按 Stop 時，每一個 pending 的 tool_call 仍然會被塞一筆 tool-error 結果。
因為 hosted chat template 會拒絕孤兒 tool_call，而 durable resume 會把它們當成未回答而重新提問。

**⑤ 漸進式揭露是 context 管理的第一原則**

Skills 在 session 開始時只注入「名稱 + 一行描述」的目錄，完整內容由 `load_skill` 按需載入。
子代理 `explore` 在自己的 context 裡讀幾十個檔案，只把最終報告回傳給主 session。

---

## 十、系列導航

| 篇章 | 主題 | 核心內容 |
|---|---|---|
| **Part 1（本篇）** | 架構全景 | 定位、三層架構、目錄職責、任務生命週期、local-first |
| Part 2 | TurnEngine 核心解剖 | agent 迴圈逐行、串流橋接、併發分流、中斷語意、outbound view |
| Part 3 | Harness：權限與人機協作 | RiskClass、五種模式、Inbox、durable resume、SSRF 防護 |
| Part 4 | LLM 層與 Context 壓縮 | Provider 抽象、Router、能力降級、compaction 演算法 |
| Part 5 | 能力擴充體系 | Tools / Catalog / Skills / Personas / Memory / MCP / 排程 |

- [OpenWorker 深度解析（二）：TurnEngine — Agent 迴圈的完整解剖](/yennj12_blog_V4/posts/openworker-intro-part2-turnengine-deep-dive-zh/)
- [OpenWorker 深度解析（三）：Harness — 權限模型、Inbox 與人機協作](/yennj12_blog_V4/posts/openworker-intro-part3-harness-permissions-inbox-zh/)
- [OpenWorker 深度解析（四）：LLM 層 — Provider 抽象與 Context 自動壓縮](/yennj12_blog_V4/posts/openworker-intro-part4-llm-provider-compaction-zh/)
- [OpenWorker 深度解析（五）：能力擴充 — Tools、Skills、Personas、MCP 與排程](/yennj12_blog_V4/posts/openworker-intro-part5-tools-skills-mcp-automation-zh/)

---

## 參考資料

- [andrewyng/openworker](https://github.com/andrewyng/openworker) — 本文分析的主體（MIT License）
- [andrewyng/aisuite](https://github.com/andrewyng/aisuite) — 引擎底層的統一 LLM 介面
- [Model Context Protocol](https://modelcontextprotocol.io/) — OpenWorker 的第三方工具擴充協定
- [openworker.com](https://openworker.com) — 官方網站與下載

> 本文分析基於 2026-08 的 `main` 分支（commit `01b6f83`）。專案仍在 open beta，
> 程式碼細節可能已變動；行號與函式名以你當下 clone 的版本為準。
