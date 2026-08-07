---
title: "OpenWorker 深度解析（四）：LLM 層 — Provider 抽象、能力降級與 Context 自動壓縮"
date: 2026-08-07T12:00:00+08:00
draft: false
weight: 4
description: "拆解 OpenWorker 如何同時支援 OpenAI、Anthropic、Gemini、Bedrock、Vertex、Ollama 與多家轉售商：ProviderClient 契約為何刻意同步且無迴圈、能力矩陣如何驅動 vision/PDF 降級、TokenUsage 的快取拆分，以及 561 行 compaction.py 的完整壓縮演算法。"
categories: ["engineering", "ai", "all"]
tags: ["OpenWorker", "LLM", "Provider Abstraction", "Context Window", "Prompt Caching", "Token", "Python", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
series: ["openworker-intro"]
---

> *「支援多家 LLM」聽起來像是一個 adapter pattern 練習題。*
> *直到你發現：Anthropic 沒有 mid-thread system message、*
> *Gemini 的 thought signature 必須原樣送回、*
> *OpenAI 的 GPT-5.6 在 Chat Completions 上不准 tools 搭配 reasoning、*
> *而使用者可以在對話中途從 Claude 換到 Ollama 上的 Llama。*

---

本篇是 [OpenWorker 深度解析系列](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
的第四篇，處理 `coworker/providers/`（4,507 行）與 `coworker/compaction.py`（561 行）。

---

## 一、為什麼不能只用 LiteLLM

多 provider 抽象的市場已經很成熟（LiteLLM、aisuite 自己、OpenRouter）。
OpenWorker 仍然自己寫了一層，理由可以歸納成四點：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ① 需要「能力查詢」而不只是「呼叫代理」                                     │
│    provider.capabilities(model) → tools / vision / pdf /                 │
│                                   parallel_tool_calls / streaming        │
│    → 使用者上傳 PDF，模型不支援時要在本地抽文字，而不是直接 400           │
├──────────────────────────────────────────────────────────────────────────┤
│ ② 需要保存「provider 私有欄位」跨輪次                                     │
│    Gemini thought signature、OpenAI Responses 的 encrypted reasoning      │
│    → 純代理層會把這些欄位丟掉，導致思考鏈中斷                             │
├──────────────────────────────────────────────────────────────────────────┤
│ ③ 需要正規化的 token 計數（含快取拆分）                                   │
│    input / output / cache_read / cache_write                             │
│    → 這是 context 壓縮的觸發訊號，也是成本顯示的來源                      │
├──────────────────────────────────────────────────────────────────────────┤
│ ④ 需要「單次呼叫、不含迴圈」的契約                                        │
│    因為迴圈裡要塞權限檢查、中斷、審計 — 那是 runtime 的職責               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、`ProviderClient`：一個刻意樸素的契約

```python
class ProviderClient(ABC):
    """Single-shot, provider-agnostic completion interface.

    Deliberately blocking (the turn engine wraps it in `asyncio.to_thread`) and
    deliberately without a `max_turns` loop — the runtime owns the agent loop.
    """

    @abstractmethod
    def complete(self, *, model, messages, tools=None, **settings) -> AssistantTurn: ...

    @abstractmethod
    def capabilities(self, model: str) -> ModelCapabilities: ...

    def stream(self, *, model, messages, tools=None, **settings):
        """Yield StreamChunks. Default: no token streaming — one final chunk with the
        full turn. Providers that support streaming (OpenAIProvider) override this."""
        yield StreamChunk(
            turn=self.complete(model=model, messages=messages, tools=tools, **settings)
        )
```

三個設計決定：

| 決定 | 理由 |
|---|---|
| **同步（blocking）** | 非同步橋接集中在 `TurnEngine._astream()` 一處處理，不要求 7 家 provider 都正確實作 async 取消語意 |
| **沒有 `max_turns`** | 迴圈是 runtime 的職責。Provider 只負責「一次往返」 |
| **`stream()` 有預設實作** | 不支援串流的 provider（或不想實作的）自動退化成「一次吐完」，不會壞掉 |

### 2.1 `AssistantTurn`：一次回應的完整形狀

```python
@dataclass
class AssistantTurn:
    text: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    raw: Any = field(default=None, repr=False, compare=False)
    # 模型的思考文字（DeepSeek reasoning_content、Gemini thought summaries…）
    # 顯示專用：存在 assistant 訊息的 `reasoning` 側車，但送 provider 前一律剝掉
    reasoning: Optional[str] = None
    # Provider 私有側車（底線開頭 key，例如 `_gemini` thought signature）
    # 契約：擁有它的 provider 會重新附加，其他 provider 必須剝掉或忽略
    extras: dict[str, Any] = field(default_factory=dict)
    # 正規化的 token 計數。provider 沒回報時是 None — 絕不猜測
    usage: Optional[TokenUsage] = None
```

**「never guessed」** 是重要的紀律：如果 provider 沒回報 usage，
就讓它是 `None`，由上層決定用估算值。**不要在資料層填假數字。**

### 2.2 `TokenUsage`：把快取拆出來

```python
@dataclass
class TokenUsage:
    """Normalized token counts for one model round-trip.

    `input` counts only fresh (uncached) prompt tokens; cached prompt tokens are
    split into `cache_read`/`cache_write`. Providers that don't report a cache
    split (Ollama, most compat vendors) leave the cache fields at 0. `output`
    includes thinking tokens where the vendor bills them as output (Gemini).
    """
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def context_tokens(self) -> int:
        """Prompt-side total — what actually occupied the context window."""
        return self.input + self.cache_read + self.cache_write
```

`context_tokens` 這個 property 是關鍵：**壓縮觸發要看的是「佔了多少 context」，
而不是「花了多少錢」**。快取讀取的 token 只收 ~0.1 倍費用，
但它們**照樣佔滿 context window**。

Anthropic 的映射：

```python
return TokenUsage(
    input=int(getattr(usage, "input_tokens", 0) or 0),          # 不含快取
    output=int(getattr(usage, "output_tokens", 0) or 0),
    cache_read=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
    cache_write=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
)
```

---

## 三、ProviderRouter：一行前綴決定一切

```python
"""ProviderRouter — one `ProviderClient` that dispatches by the `provider:` prefix of a model
string to a per-provider client, built lazily from its SecretStore profile and cached.

This is the single provider the `SessionManager` hands to every engine, so `complete()/stream()`
(which already receive the full model string per-call) route themselves: `ollama:llama3.3` →
the Ollama client (Ollama's OpenAI-compatible `/v1`), bare `gpt-5.5` → the default (OpenAI).
"""
```

```
model 字串                     路由結果
────────────────────────────────────────────────────────────────
"gpt-5.6-sol"              →  預設 provider（openai）
"anthropic:claude-fable-5" →  Anthropic 原生 client
"ollama:llama3.3"          →  Ollama（OpenAI 相容 /v1）
"together:zai-org/GLM-5.2" →  Together 轉售
"qwen2.5-coder:32b"        →  ★ 預設 provider — `qwen2.5-coder` 不是已知
                              provider 名稱，這個冒號是版本標籤
```

最後一列是這段程式碼裡最容易被忽略的細節：

```python
@staticmethod
def _bare(model: str) -> str:
    """Strip a KNOWN provider prefix; the underlying SDK wants the bare model name. A model
    whose first segment isn't a provider (e.g. `qwen2.5-coder:32b` — a version tag, not a
    prefix) is returned unchanged, so the colon isn't mistaken for a provider separator."""
    if ":" in model:
        prefix, rest = model.split(":", 1)
        if get_descriptor(prefix) is not None:      # ← 必須是「已註冊的 provider」
            return rest
    return model
```

**用 `":" in model` 當判準會炸掉所有 Ollama 的 tag 語法。**
判準必須是「前綴是不是已註冊的 provider 名稱」。

### 3.1 Lazy build + invalidate

```python
def _client_for(self, model: str) -> ProviderClient:
    name = self._provider_name(model)
    with self._lock:
        client = self._clients.get(name)
        if client is None:
            profile = {}
            if self._secrets is not None:
                profile = self._secrets.get(f"provider:{name}") or {}
            client = build_provider_client(name, profile, self._secrets)
            self._clients[name] = client
        return client

def invalidate(self, name: Optional[str] = None) -> None:
    """Drop cached client(s) so the next call rebuilds with fresh config."""
```

使用者在 Settings 換金鑰、改 Ollama URL → 呼叫 `invalidate()` →
**既有的引擎不用重建就能拿到新設定**。這跟 Part 3 提到的
「roots 持有參照」是同一個模式：**共享可變狀態，每次讀取。**

### 3.2 六個註冊的 provider descriptor

```
openai · anthropic · gemini · bedrock · vertex · ollama
```

看起來只有六個，但實際支援的模型來源遠不止：`openai` descriptor
在**沒有自訂 base_url** 時建 `OpenAIResponsesProvider`，
有自訂 base_url 時建 Chat Completions 版的 `OpenAIProvider`
—— 於是 Azure、vLLM、以及所有 OpenAI 相容的廠商（DeepSeek、Kimi、Qwen、MiniMax、
Mistral、Grok、GLM、Together、Fireworks、OpenRouter）全部走這條路。

```
                     ┌──────────────────────────────┐
   provider="openai" │ 有 custom base_url？          │
        ──────────▶  │   否 → OpenAIResponsesProvider│ /v1/responses
                     │   是 → OpenAIProvider         │ /v1/chat/completions
                     └──────────────────────────────┘
                                    ▲
                     所有 OpenAI 相容廠商都從這裡進來
```

為什麼要分兩條？`openai_responses.py` 的註解說明了：

```python
"""OpenAI Responses provider — native OpenAI models via `/v1/responses`.

Chat Completions rejects function tools combined with any `reasoning_effort` other than
`none` on GPT-5.6+ ("use /v1/responses"), which had reasoning pinned OFF for native OpenAI
models. This provider is the Responses path: reasoning + tools at real effort levels,
streamed reasoning summaries, and chain-of-thought continuity across tool round-trips via
`store: false` + `include: ["reasoning.encrypted_content"]` — nothing retained server-side.
"""
```

**`store: false` + `encrypted_content`** 這個組合很符合 local-first 的哲學：
拿到加密的推理內容自己保管、下一輪原樣送回，**伺服器端不留任何東西**。

---

## 四、能力矩陣與優雅降級

### 4.1 兩層查詢

```python
def capabilities_for(model: str) -> ModelCapabilities:
    # Curated models answer from the matrix (exact full-id match — including reseller ids
    # like `together:zai-org/GLM-5.2`, whose names defeat the prefix heuristics below).
    # Custom user-added models fall through to the heuristics, at their own risk.
    entry = entry_for(model)
    if entry is not None:
        return entry.caps
    ...  # 啟發式判斷
```

```
① 精選矩陣（matrix.py）— 完整 id 精確匹配
   "gpt-5.6-sol": ModelEntry("GPT-5.6 Sol · OpenAI", _AGENTIC_VISION, 400_000)
                   └ UI 標籤        └ 能力          └ context window

② 啟發式（capabilities.py）— 依 provider 前綴保守推測
   ollama:*         → tools=True, vision=False, parallel_tool_calls=False
   bedrock:claude/* → 全開
   bedrock:其他     → 保守
   anthropic/gemini → tools+vision+pdf+parallel
```

矩陣的定位寫得很清楚：

```python
"""The curated model matrix — the only models we actively suggest, label, and vouch for.

Deliberately SMALL (owner call, 2026-07-04): current-generation, agent-capable (tool-calling)
models only. It is not user-editable — users can still add any custom model string, which
falls back to the conservative heuristics in ``capabilities.py`` at their own risk of
degraded results.
"""
```

**「Deliberately SMALL」+「not user-editable」+「at their own risk」**
—— 這是很成熟的產品判斷。精選清單代表「我們驗證過」，
自訂模型代表「你自己負責」。中間沒有模糊地帶。

`context_window` 欄位有個誠實的處理：

```python
# Entries where the vendor spec wasn't re-checked stay ``None`` — the meter simply hides
# rather than showing a made-up denominator.
```

**沒驗證過就顯示 None，UI 直接隱藏進度條，不編一個分母出來。**

### 4.2 降級發生在 outbound 轉換，不在歷史裡

回顧 Part 2 的 `_outbound_messages()`：

```python
# PDF attachments (stored as `file` parts) are adapted to the ACTIVE model right
# here — never in the persisted history — so a mid-session model switch always
# re-decides.
if any(p.get("type") == "file" for msg in out ... ):
    caps = self.provider.capabilities(self.model)
    if not getattr(caps, "pdf", False):
        from . import pdf_support
        out = [{**msg, "content": pdf_support.adapt_content(msg["content"], caps)} ...]

# 圖片同理
if any(p.get("type") == "image_url" for msg in out ...):
    caps = self.provider.capabilities(self.model)
    if not getattr(caps, "vision", False):
        placeholder = {"type": "text",
                       "text": "[image attachment — not viewable by this model]"}
```

```
      持久化歷史（canonical）
      ┌──────────────────────────┐
      │ user: [text, file(PDF)]  │  ← 永遠保留原始 PDF
      └────────────┬─────────────┘
                   │
     ┌─────────────┴──────────────┐
     ▼                            ▼
 模型 A（pdf=True）           模型 B（pdf=False）
 ┌────────────────┐          ┌───────────────────────────┐
 │ 原檔直送        │          │ pdf_support.adapt_content │
 │                │          │  → 文字抽取 或 頁面圖片    │
 └────────────────┘          └───────────────────────────┘

 ★ 中途從 B 切回 A → 又拿到原檔。因為歷史從未被改寫。
```

而 `switch_model()` 會在切換時給出誠實的警告：

```python
if caps is not None and not getattr(caps, "vision", False) and self._history_has_images():
    text += " — earlier images can't be read by this model"
```

### 4.3 錯誤訊息也是產品的一部分

`providers/errors.py` 只有 57 行，但很值得學：

```python
"""Friendly translation of model access + quota failures.

Matching is on the error BODY text (error codes/types), not just HTTP status — a 404 also
means "wrong base_url" and a 429 also means "slow down", and neither of those should be
dressed up as an access problem.
"""

_NO_ACCESS = ("model_not_found", "does not exist or you do not have access",
              "does not have access to model", "permission_error", "permission denied")
_NO_QUOTA = ("insufficient_quota", "exceeded your current quota",
             "credit balance is too low", "billing hard limit")
```

**「Matching is on the error BODY text, not just HTTP status」** —— 用狀態碼判斷會誤傷：
404 也可能是 base_url 打錯，429 也可能只是要你慢一點。**不確定就回 `None`，
讓原始錯誤原樣呈現。**

Anthropic 的 404 還要求兩個條件同時成立：

```python
# Anthropic's 404 body is just "model: <id>" under type not_found_error; require both
# halves so unrelated 404s (bad base_url, deleted resource) keep their raw message.
if "not_found_error" in text and f"model: {model.split(':')[-1].lower()}" in text:
    return no_access
```

---

## 五、Prompt caching：兩個斷點的標準 agent-loop 形狀

```python
def _add_cache_breakpoints(kwargs: dict[str, Any]) -> None:
    """Opt the request into prompt caching (5-minute ephemeral, prefix-matched).

    Two breakpoints, the standard agent-loop shape:
    - last system block — caches tools + system together (tools render first);
    - last content block of the final message — caches the whole conversation
      prefix, so each request re-reads the previous turns' cache and writes only
      the new tail (append-only history keeps the prefix byte-identical).

    Outbound-only: the canonical history never carries `cache_control`.
    Prefixes under the model's cacheable minimum silently don't cache; reads bill
    ~0.1x and show up as `cache_read_input_tokens` (the metering's cache_read).
    """
    marker = {"type": "ephemeral"}
    system = kwargs.get("system")
    if isinstance(system, str) and system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": marker}]
    messages = kwargs.get("messages") or []
    if messages:
        content = messages[-1].get("content")
        if isinstance(content, list) and content:
            content[-1] = {**content[-1], "cache_control": marker}
```

```
第 N 輪請求：
┌──────────────────────────────────────────────────────────────────┐
│ [tools 定義] [system prompt]                    ◀── 斷點 ①       │
│ user_1 / assistant_1 / tool_1 / assistant_2 / … / tool_{N-1}     │
│ assistant_N                                     ◀── 斷點 ②       │
└──────────────────────────────────────────────────────────────────┘
                          │
第 N+1 輪：前綴完全 byte-identical → cache_read
           只有新增的尾巴 → cache_write
```

**這個模式能成立的前提是「歷史是 append-only 的」**。而這正是為什麼
Part 4 下半部要講的 compaction 必須格外小心 —— 壓縮會改寫前綴，
一改就會使快取全部失效。

---

## 六、Context 自動壓縮：561 行的完整演算法

### 6.1 設計聲明

```python
"""Auto-compaction of long session histories (OPE-27).

When the outbound history approaches the model's context limit, the older portion of the
*outbound* view is replaced with (a) an LLM-written structured summary and (b) mechanically
extracted state — the recent turns and all user messages survive. The persisted transcript
is never modified; only what is sent to the model.

This module is pure functions + one dataclass; the engine owns *when* (its run loop) and
*with what* (its provider/model), both injected here. That split keeps the engine.py
footprint to a few lines and makes every policy testable without a provider.
"""
```

**「pure functions + one dataclass」** —— 整個壓縮策略不依賴 provider，
所以每一條規則都能單元測試。引擎只負責決定「何時」與「用哪個模型」。

### 6.2 觸發：兩個上限取小

```python
DEFAULT_THRESHOLD_PCT = 0.8
DEFAULT_CAP_TOKENS = 250_000
DEFAULT_CONTEXT_WINDOW = 128_000   # 矩陣裡沒有 context_window 時的預設
KEEP_RECENT_FRACTION = 0.25
SUMMARY_MAX_TOKENS = 3_000

def trigger_tokens(context_window, *, threshold_pct=0.8, cap_tokens=250_000) -> int:
    window = context_window or DEFAULT_CONTEXT_WINDOW
    return min(int(threshold_pct * window), int(cap_tokens))
```

註解說明了 cap 存在的理由：

```python
# Trigger: min(threshold_pct × context_window, cap_tokens). The cap exists so 1M-context
# models compact early — quality and latency degrade well before the nominal limit.
```

**「quality and latency degrade well before the nominal limit」** —— 這是實務經驗。
1M context 的模型不代表你該塞 800K 進去；找出中間某個事實的準確率會明顯下降，
而且 TTFT 會爆炸。

實際數字：

| 模型 context window | 80% 門檻 | 實際觸發點（取 min） |
|---|---|---|
| 128,000 | 102,400 | **102,400** |
| 200,000 | 160,000 | **160,000** |
| 400,000（GPT-5.6） | 320,000 | **250,000**（cap 生效） |
| 1,000,000 | 800,000 | **250,000**（cap 生效） |

保留的近期片段預算 = `0.25 × trigger_tokens`。以 400K 模型為例：
觸發於 250K，保留最近 62,500 tokens 逐字。

### 6.3 訊號：實測優先，估算墊底

```python
def _compaction_due(self) -> bool:
    cfg = self._compaction_config()
    if cfg.get("enabled") is False:
        return False
    signal = self._last_context_tokens or _compaction.estimate_tokens(
        self._outbound_messages()
    )
    return _compaction.should_compact(signal, cfg.get("context_window"), ...)
```

```python
def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """chars/4 over the serialized messages — the fallback signal for providers that
    never report usage (documented in the metering code)."""
```

`_last_context_tokens` 來自上一輪的 `turn.usage.context_tokens`（真實值）。
只有在 provider 不回報 usage 時才用 `chars/4` 估算。**估算不準會導致
真的 overflow，所以第三章講的 `is_context_overflow` 回退路徑是必要的配套。**

### 6.4 邊界選擇：合法的後綴頭

這是壓縮裡最容易寫錯的部分。

```python
def pick_boundary(messages, *, keep_tokens: int) -> Optional[int]:
    """The canonical index where the verbatim tail begins: the earliest turn start whose
    suffix fits the keep budget. Prefers user-message boundaries; falls back to iteration
    (assistant) boundaries when the newest turn alone exceeds the budget (a giant tool
    loop). None when there is nothing meaningful to summarize."""
```

```
┌───────────────────────────────────────────────────────────────────────────┐
│ 規則一：boundary 之後的第一則訊息，必須是 user 或 assistant               │
│         ★ 絕不能是 tool —— 孤兒 tool 結果會被 provider 拒絕               │
│                                                                           │
│ 規則二：優先選 user 訊息（＝一整輪對話的起點）                             │
│                                                                           │
│ 規則三：從「最早」開始找 —— 保留越多逐字內容越好                           │
│         for i in candidates:  # earliest-first                            │
│             if estimate_tokens(messages[i:]) <= keep_tokens: return i     │
│                                                                           │
│ 規則四：若「最新一輪 user turn」自己就超過預算（巨大的工具迴圈）           │
│         → 退而求其次，在該輪內部的 assistant 邊界切                        │
│         → 至少保留最近一個 assistant 步驟                                 │
└───────────────────────────────────────────────────────────────────────────┘
```

```python
def _fit(candidates: list[int]) -> Optional[int]:
    for i in candidates:  # earliest-first: keep as much verbatim as fits
        if estimate_tokens(messages[i:]) <= keep_tokens:
            return i
    return None

boundary = _fit(users)
if boundary is None and users:
    # The newest user turn alone blows the budget — cut inside it at an iteration
    # boundary, keeping at least the most recent assistant step.
    inside = [i for i in assistants if i > users[-1]]
    boundary = _fit(inside)
    if boundary is None:
        boundary = inside[-1] if inside else users[-1]
```

### 6.5 摘要 = LLM 產出 + 機械抽取

這是整個設計最聰明的地方：**不把所有東西都交給 LLM**。

```
┌────────────────────────────────────────────────────────────────────────┐
│  <compacted-history>                                                   │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ A. LLM 摘要（8 個固定小節）                                    │     │
│  │    1. Primary request and intent                              │     │
│  │    2. Key concepts and decisions（含 WHY）                    │     │
│  │    3. Artifacts and files                                     │     │
│  │    4. Errors and fixes（含使用者的糾正）                       │     │
│  │    5. All user messages                                       │     │
│  │    6. Pending tasks                                           │     │
│  │    7. Current work                                            │     │
│  │    8. Next step                                               │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ B. 機械抽取（零幻覺風險 — 直接讀 tool_call 紀錄）              │     │
│  │    · 寫過 / 編輯過的檔案（去重，最近 20 個）                   │     │
│  │    · 最近 10 條 shell 指令 + exit status                      │     │
│  │    · 產生的 artifact（最近 10 個）                            │     │
│  │    · 這段用過的所有工具名稱                                    │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ C. 使用者訊息逐字保留（最多 40 則，每則 600 字）               │     │
│  │    ★「user words are the ground truth of intent and must      │     │
│  │       not depend on an LLM remembering to include them」      │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  D. CONTINUATION_CONTRACT（接續契約）                                  │
│  </compacted-history>                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

**B 和 C 是「防止 LLM 摘要出錯」的保險**。摘要模型可能忘記提某個檔案、
可能改寫使用者的原話 —— 但 tool_call 紀錄和 user message 是可以機械抽取的事實。

### 6.6 摘要 prompt 裡的四條規則

```python
SUMMARY_SYSTEM_PROMPT = """You are compacting an AI coworker's session history so the coworker
can continue working in a smaller context. Write a structured summary of the conversation below.
It is the coworker's ONLY memory of these turns, so preserve everything load-bearing.
...
1. **Primary request and intent** — … including standing constraints stated at any point
   (e.g. "never send without my approval"). Constraints outlive the turns they were stated in.
2. **Key concepts and decisions** — … Include the WHY, not just the what — a decision without
   its reason gets relitigated.
...
Rules:
- Do NOT carry full file contents as truth. Note THAT a file was read/edited; the coworker
  re-reads if it needs the content again. Stale memory of a file is worse than no memory.
- Be concrete: paths, names, commands, ids — not vague references.
- Output only the summary sections, no preamble."""
```

三句話值得單獨抄下來：

> **「Constraints outlive the turns they were stated in.」**
> 使用者在第 3 輪說「沒有我批准不要發訊息」，這條限制到第 80 輪還有效。
> 摘要漏掉它 = 安全事故。

> **「a decision without its reason gets relitigated」**
> 只寫「我們決定用 Redis」，模型在後面會重新提議用 Postgres。
> 必須寫「用 Redis，因為需要原生 TTL」。

> **「Stale memory of a file is worse than no memory.」**
> 摘要裡不要塞完整檔案內容 —— 檔案會變，過時的記憶比沒有記憶更糟。
> 只記「讀過 / 改過這個檔案」，需要時重讀。

接續契約：

```python
CONTINUATION_CONTRACT = (
    "Continue where you left off: pick up the current work and next step exactly as "
    "described. Do not re-ask answered questions, do not recap, do not mention that the "
    "context was compacted. If you need the contents of a file noted above, re-read it."
)
```

**「do not mention that the context was compacted」** —— 這是 UX 細節：
使用者不需要聽 agent 說「我剛剛壓縮了記憶」。

### 6.7 送給摘要模型的輸入也要控制

```python
_SPAN_TOOL_RESULT_CLIP = 400      # 每則工具結果最多 400 字
_SPAN_BUDGET_CHARS = 400_000      # 整段 render 的上限

def _render_span(span, *, budget_chars=_SPAN_BUDGET_CHARS) -> str:
    """The summarized span as compact text for the summarizer. Tool results are clipped
    hard (first casualty); if the whole render still exceeds the budget, oldest lines are
    dropped — the newest context is the most load-bearing."""
```

**「Tool results are clipped hard (first casualty)」** —— 40 輪前讀的檔案內容，
壓縮時不需要完整保留，因為摘要規則已經說了「需要就重讀」。

重複壓縮時，前一次的摘要會成為新 span 的第 0 則訊息：

```python
def summarizer_messages(span, *, prior_summary: str = "") -> list[dict]:
    """On repeated compaction the previous summary is message zero of the new span —
    summarized along with the turns since."""
    body = _render_span(span)
    if prior_summary:
        body = ("[previous compaction summary — fold its still-relevant content into the new "
                "summary]\n" + prior_summary + "\n\n[conversation since]\n" + body)
```

### 6.8 使用者訊息清單的上限問題

```python
_USER_MESSAGE_CLIP = 600
_USER_MESSAGES_MAX = 40
# User messages preserved mechanically in the compacted block ("trimmed of pasted bulk").
# The list is capped to the newest N across repeated compactions — otherwise it appends
# forever and the block slowly reclaims the window it freed. Dropped ones stay counted
# (their intent lives in the summary, which is asked to list user messages too).
```

這是一個很細膩的 bug 預防：**逐字保留使用者訊息聽起來很好，
但反覆壓縮下它會無限增長，最後把壓縮省下的空間又吃回去。**
所以上限 40 則，被丟掉的計數保留：

```python
if state.user_messages_dropped:
    parts += [f"({state.user_messages_dropped} earlier user messages omitted — "
              "their intent is covered by the summary above)"]
```

### 6.9 失敗策略：兩次重試 → 分模式處理

```
_compact_now()
      │
      ├─ 嘗試 build_state()（第一次 + 無條件重試一次）
      │        │
      │        ├─ 成功 → 更新 compaction_state，回傳 notice
      │        │
      │        └─ 失敗
      │              │
      │              ├─ attended（有人在）→ 問使用者：
      │              │     「Retry」or「Trim oldest 10%」
      │              │     選 Retry → 再試，可以無限循環
      │              │
      │              └─ unattended（沒人在）→ 直接 auto-trim
      │                    ★「never park a background run on internal bookkeeping」
      │
      └─ trim_state()：無 LLM 的降級路徑
            · 把 boundary 往前推 ~10%
            · 沒有摘要，但機械抽取 + 使用者訊息清單照樣免費
            · summary_text = "(Older turns were trimmed to fit the context window;
                              no summary is available for them. Re-read files and
                              re-run commands if earlier results are needed.)"
```

**「never park a background run on internal bookkeeping」** —— 半夜跑的排程任務，
不該因為「摘要模型 API 掛了」就停下來等人回答一個技術性問題。降級後繼續跑。

### 6.10 套用到 outbound：三段式

```python
def apply_to_outbound(messages, state) -> list[dict]:
    """The outbound view: [system?] + the compacted block (as a user message) + the
    verbatim tail. Canonical history is untouched; provider-private sidecars in the
    summarized span vanish with it (replay chains legally restart after a compaction
    point). No-op when state is absent or stale."""
    if state is None:
        return messages
    boundary = state.boundary_index
    if boundary <= 0 or boundary >= len(messages):
        return messages
    head = []
    if messages and messages[0].get("role") == "system":
        head.append(messages[0])
    head.append({"role": "user", "content": compacted_block(state)})
    return head + messages[boundary:]
```

```
canonical:  [system][u1][a1][t1][a2][u2][a3][t2][a4][u3][a5]...
                                            ▲
                                     boundary_index

outbound:   [system][user: <compacted-history>...][a4][u3][a5]...
                     └─ 一則 user 訊息 ─┘         └─ 逐字尾巴 ─┘
```

註解裡有一句容易漏掉但很重要的：

> **「provider-private sidecars in the summarized span vanish with it
> (replay chains legally restart after a compaction point)」**

Gemini thought signature、OpenAI encrypted reasoning 這些 replay 鏈，
在壓縮邊界處**合法地重新開始**。不需要特別處理。

### 6.11 壓縮與 prompt cache 的關係

```python
# Auto-compaction (OPE-27): everything before the boundary is represented by the
# compacted block. Outbound-only — the canonical history stays intact — and the
# block+tail are byte-stable between turns, so prompt caching keeps working.
```

**「the block+tail are byte-stable between turns」** —— 壓縮之後，
新的前綴（system + compacted block）在後續每一輪都是**位元組相同**的，
所以 prompt cache 在第二輪就重新命中。

代價是壓縮發生的**那一輪**會 cache miss 一次（整個前綴變了）。這是必然的。

---

## 七、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **自寫 provider 層**<br>vs 純 LiteLLM | 需要 `capabilities()` 驅動降級、需要 `extras` 保存 provider 私有欄位 | 純代理層會丟失能力資訊與 provider 私有欄位，中途換模型就壞 | 只支援 1–2 家且不做降級時 |
| **前綴路由（`provider:model`）**<br>vs 顯式 provider 參數 | 一個字串就能完整描述路由；session 只要存一個欄位 | 兩個欄位要同步，換模型時容易漏改一個 | 需要同一模型走不同端點時（要加 endpoint 維度） |
| **精選矩陣 + 保守啟發式**<br>vs 全靠啟發式 / 全靠使用者填 | 精選代表「我們驗證過」；自訂代表「你自己負責」 | 全靠啟發式會誤判（reseller 的 ugly name）；全靠使用者填則體驗差 | 有可靠的 capability discovery API 時 |
| **壓縮上限 250K**<br>vs 只用 80% 門檻 | 1M context 模型在 250K 之後品質與延遲都明顯劣化 | 塞到 800K 會讓「找出中間某個事實」的準確率崩掉 | 模型的 long-context 表現有實測改善時可調高 |
| **摘要 + 機械抽取雙軌**<br>vs 只用 LLM 摘要 | tool_call 紀錄與 user message 是可機械抽取的事實，不該讓 LLM 記 | LLM 會漏檔案、會改寫使用者原話 | 沒有結構化的 tool_call 紀錄時 |
| **只改 outbound view**<br>vs 改寫真實歷史 | 使用者仍能翻閱完整 transcript；壓縮出錯可以清掉 state 重來 | 改寫歷史 = 不可逆，且會破壞 durable resume 的 tool_call 對應 | 儲存空間極度受限時 |
| **unattended 壓縮失敗直接 trim**<br>vs 問人 | 背景任務不該卡在內務問題上 | 半夜的排程停下來等人回答技術問題 = 任務失敗 | 沒有 |
| **usage 沒回報就是 None**<br>vs 填估算值 | 資料層不猜測；上層自己決定要不要估 | 假數字會流進成本統計與壓縮觸發，且無法區分「真的 0」 | 沒有 |

---

## 八、系列導航

- [Part 1：架構全景 — 一個能交付成果的桌面 AI 同事](/yennj12_blog_V4/posts/openworker-intro-part1-architecture-overview-zh/)
- [Part 2：TurnEngine — Agent 迴圈的完整解剖](/yennj12_blog_V4/posts/openworker-intro-part2-turnengine-deep-dive-zh/)
- [Part 3：Harness — 權限模型、Inbox 與人機協作](/yennj12_blog_V4/posts/openworker-intro-part3-harness-permissions-inbox-zh/)
- **Part 4（本篇）：LLM 層 — Provider 抽象、能力降級與 Context 自動壓縮**
- [Part 5：能力擴充 — Tools、Skills、Personas、MCP 與排程](/yennj12_blog_V4/posts/openworker-intro-part5-tools-skills-mcp-automation-zh/)

---

## 本篇可以帶走的七個模式

1. **Provider 抽象要包含「能力查詢」**，不能只有「呼叫代理」——
   否則無法做 vision / PDF 降級。
2. **降級是 outbound-only 的**：歷史保留最高保真度，每次呼叫依當前模型重新決定。
3. **前綴路由的判準是「已註冊的 provider 名稱」**，不是「有沒有冒號」。
4. **token 計數要拆出 cache_read/write**：佔 context 的是總量，計費的是拆分後的量。
5. **壓縮要有絕對上限**，不能只看 context window 的百分比。
6. **摘要不要全交給 LLM**：能機械抽取的事實（檔案清單、指令、使用者原話）就機械抽取。
7. **失敗路徑要分 attended / unattended**：背景任務永遠不該卡在內務問題上。

> 本文分析基於 2026-08 的 `main` 分支（commit `01b6f83`）。文中出現的模型 id
> 來自該版本的 `matrix.py`，僅作為程式碼引用，不代表模型的實際可用性。
