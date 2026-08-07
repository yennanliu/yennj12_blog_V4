---
title: "QM 深度解析（三）：Harness 抽象 — 一套核心驅動四種 Agent 引擎"
date: 2026-08-07T16:00:00+08:00
draft: false
weight: 3
description: "拆解 QM 如何讓 Pi、OpenCode、Codex、Claude Code 四種完全不同的 Agent 引擎驅動同一個核心：Harness 契約的三軸能力宣告、60 欄位的 HarnessTurnInput 依賴注入、Entries 與 Tape 雙軌重放、context 壓縮的 throughSeq 錨點，以及 runtime 選擇的三層繼承。"
categories: ["engineering", "ai", "all"]
tags: ["QM", "AI Agent", "Agent Harness", "Abstraction", "TypeScript", "LLM", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
series: ["qm-deep-dive"]
---

> *「支援多種 Agent 引擎」聽起來像是寫幾個 adapter。*
> *但 Pi 跑在同進程裡、OpenCode 是一個 HTTP sidecar、*
> *Codex 講 JSON-RPC、Claude Code 用 SDK 加 in-process MCP。*
> *它們的工具怎麼註冊、怎麼中斷、能不能收圖片，四家四個答案。*
> *抽象的難點不是「共同介面」，是「差異怎麼被誠實地表達出來」。*

---

本篇是 [QM 深度解析系列](/yennj12_blog_V4/posts/qm-multiplayer-agent-part1-architecture-zh/)
的第三篇，主角是 `src/harness/`（10,022 行）與 `src/core/orchestrator.ts`（2,863 行）。

---

## 一、四個引擎，四種完全不同的接法

先看結論。`defineHarness()` 的第一個參數就是各引擎的自我宣告：

```typescript
// pi-harness.ts
{ id: "pi",       controlTransport: "in-process", toolTransport: "in-process",
  transcriptFormat: "pi",
  capabilities: new Set(["abort","steer","images","thinking-level","fast-mode","provider-sessions"]) }

// claude-harness.ts
{ id: "claude",   controlTransport: "sdk",        toolTransport: "in-process-mcp",
  transcriptFormat: "claude-agent-sdk",
  capabilities: new Set(["abort","steer","images","thinking-level","fast-mode"]) }

// opencode-harness.ts
{ id: "opencode", controlTransport: "http",       toolTransport: "plugin",
  transcriptFormat: "opencode",
  capabilities: new Set(["abort","steer","images","provider-sessions"]) }

// codex-harness.ts
{ id: "codex",    controlTransport: "json-rpc",   toolTransport: "dynamic",
  transcriptFormat: "responses-api",
  capabilities: new Set(["abort","steer","images","provider-sessions"]) }

// mock-harness.ts
{ id: "mock",     controlTransport: "mock",       toolTransport: "mock",
  transcriptFormat: "qm",
  capabilities: new Set() }
```

### 1.1 三軸差異一覽

```
┌──────────┬───────────────┬─────────────────┬──────────────────┬────────┐
│ 引擎      │ controlTransport│ toolTransport  │ transcriptFormat │ 行數    │
├──────────┼───────────────┼─────────────────┼──────────────────┼────────┤
│ pi       │ in-process    │ in-process      │ pi               │ 2,070  │
│          │ 同進程直接呼叫  │ 直接註冊函式     │                  │ +2,483 │
│          │               │                 │                  │(工具)  │
├──────────┼───────────────┼─────────────────┼──────────────────┼────────┤
│ claude   │ sdk           │ in-process-mcp  │ claude-agent-sdk │   926  │
│          │ Agent SDK     │ 同進程 MCP server│                  │        │
├──────────┼───────────────┼─────────────────┼──────────────────┼────────┤
│ opencode │ http          │ plugin          │ opencode         │ 1,163  │
│          │ HTTP sidecar  │ OpenCode plugin  │                  │  +286  │
│          │               │ 機制             │                  │(plugin)│
├──────────┼───────────────┼─────────────────┼──────────────────┼────────┤
│ codex    │ json-rpc      │ dynamic         │ responses-api    │   942  │
│          │ JSON-RPC 伺服器│ 動態註冊        │                  │        │
├──────────┼───────────────┼─────────────────┼──────────────────┼────────┤
│ mock     │ mock          │ mock            │ qm               │   770  │
└──────────┴───────────────┴─────────────────┴──────────────────┴────────┘
```

### 1.2 六種能力，各家支援不同

```
capability          pi    claude  opencode  codex   意義
─────────────────────────────────────────────────────────────────────────
abort               ✓      ✓        ✓        ✓     可中斷進行中的回合
steer               ✓      ✓        ✓        ✓     可在跑的途中插話
images              ✓      ✓        ✓        ✓     接受圖片輸入
thinking-level      ✓      ✓        ✗        ✗     可調整思考深度
fast-mode           ✓      ✓        ✗        ✗     快速模式
provider-sessions   ✓      ✗        ✓        ✓     引擎自己維護 provider session
```

**這張表不是文件，是執行時可查詢的資料。** UI 據此決定要不要顯示
thinking-level 選單；orchestrator 據此決定 context 要自己重建還是交給引擎。

`provider-sessions` 那一欄特別值得注意：pi、opencode、codex 有，claude 沒有。
意思是 Claude harness 每一輪都要由 QM 重新餵完整歷史，
而另外三個引擎自己記得 session 狀態。**這直接影響 tape 的用法**（第四節）。

---

## 二、Harness 契約：一個介面，四種實作

### 2.1 三個子介面

```typescript
export interface Harness {
  profile: HarnessAdapterProfile;   // 自我宣告
  turns: HarnessTurnController;     // 跑回合
  models: HarnessModelUtilities;    // 借用模型做雜事
  tools: HarnessToolPresentation;   // 工具改名
}
```

**`turns` 是必須的，`models` 幾乎全部可選。**

```typescript
interface HarnessTurnController {
  runTurn(input: HarnessTurnInput): Promise<HarnessTurnResult>;   // 必須
  close?(): Promise<void> | void;
  resetSession?(sessionId: string): Promise<void> | void;
}

export interface HarnessModelUtilities {
  shouldRespond?(input: HarnessDetectInput): Promise<HarnessDetectResult>;
  compactHistory?(input: HarnessCompactInput): Promise<string>;
  contextTokenBudget?(scopeLabel?: string, model?: string): number | undefined;
  oneShot?(systemPrompt: string, prompt: string): Promise<string | undefined>;
  judge?(systemPrompt: string, prompt: string): Promise<string | undefined>;
  screenSecurity?(input: HarnessSecurityScreenInput): Promise<SecurityScreenVerdict | undefined>;
  pickAckEmoji?(text: string, candidates: readonly string[]): Promise<string | undefined>;
  generateTitle?(transcript: string): Promise<string | undefined>;
  summarizeApproval?(command: string, reason: string, purpose?: string): Promise<string | undefined>;
}
```

`models` 這一組是「借用這個引擎背後的模型做一件小事」。九個方法，
每一個都對應一個真實的產品需求：

| 方法 | 做什麼 | 在哪裡用 |
|---|---|---|
| `shouldRespond` | 頻道裡這句話需要我回嗎？ | Slack ambient judge |
| `compactHistory` | 把歷史壓成摘要 | context 超限時 |
| `contextTokenBudget` | 這個模型能吃多少 | 決定何時壓縮 |
| `oneShot` | 一次性問答 | 各種內部小任務 |
| `judge` | 判斷題 | 分類、評估 |
| `screenSecurity` | 內容安全篩檢 | Auto posture |
| `pickAckEmoji` | 挑一個貼切的 emoji 回應 | Slack 已讀反應 |
| `generateTitle` | 給對話取標題 | session 列表 |
| `summarizeApproval` | 把一條 shell 指令講成人話 | 批准卡片 |

最後一個很有意思：**批准卡上顯示的不是原始指令，而是模型翻譯過的說明**。
人類批准的前提是看得懂。

### 2.2 `defineHarness` 的存在意義

```typescript
export function defineHarness(
  profile: HarnessAdapterProfile,
  implementation: HarnessImplementation,
  tools: HarnessToolPresentation = { name: (coreName) => coreName },
): Harness {
  const turns: HarnessTurnController = {
    runTurn: implementation.runTurn.bind(implementation),
    ...(implementation.close ? { close: implementation.close.bind(implementation) } : {}),
    ...(implementation.resetSession ? { resetSession: implementation.resetSession.bind(implementation) } : {}),
  };
  const models: HarnessModelUtilities = {
    ...(implementation.shouldRespond ? { shouldRespond: implementation.shouldRespond.bind(implementation) } : {}),
    ...(implementation.compactHistory ? { compactHistory: implementation.compactHistory.bind(implementation) } : {}),
    ...
  };
  return { profile, turns, models, tools };
}
```

它做兩件事：

1. **把扁平的實作切成三個子介面**，讓呼叫端只能拿到它該用的部分
   —— UI 拿 `profile`、orchestrator 拿 `turns`、內部小任務拿 `models`。
2. **只轉發「真的有實作」的方法**（`...(x ? {x} : {})`）。
   所以 `harness.models.pickAckEmoji` 是 `undefined` 而不是一個會拋錯的存根。
   呼叫端用 `if (harness.models.pickAckEmoji)` 就能安全降級。

**這是「可選能力」的正確表達法**：用「存在與否」而不是「呼叫後回傳 null」。

### 2.3 `tools.name`：工具改名

```typescript
export interface HarnessToolPresentation {
  name(coreName: string): string;
}
```

預設是恆等函式。存在的原因是各引擎對工具名有自己的慣例
（有些前綴 `mcp__`，有些有長度限制）。**core 用自己的名字思考，
呈現給模型時交給 harness 翻譯。**

---

## 三、`HarnessTurnInput`：60 個欄位的依賴注入

這是整個抽象的核心，也是最違反直覺的部分 ——
它有將近 60 個欄位。但每一個都是「core 要交給引擎的東西」。

### 3.1 分組看

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 身分與 scope                                                                │
│   session · scopeLabel · orgScopeId · runId · environment                  │
├────────────────────────────────────────────────────────────────────────────┤
│ 輸入                                                                        │
│   input · triggerTs · entryTs · attachments · images ·                     │
│   priorTurns · overheard          ← ★ overheard：頻道裡「聽到但沒被叫」的訊息│
├────────────────────────────────────────────────────────────────────────────┤
│ 模型與行為                                                                   │
│   model · harness · thinkingLevel · fastMode · readOnly ·                  │
│   turnWallClockMs · pollFire                                               │
├────────────────────────────────────────────────────────────────────────────┤
│ Context                                                                     │
│   systemPrompt · systemCacheBoundary   ← ★ 明確告知快取邊界在哪             │
│   history: SessionEntry[]                                                  │
├────────────────────────────────────────────────────────────────────────────┤
│ 工具                                                                        │
│   tools: ToolContext · surfaceTools · surfaceName                          │
├────────────────────────────────────────────────────────────────────────────┤
│ 安全（★ 全部是注入的 callback，引擎自己不做決定）                             │
│   screenExternalContent(...)  → 外部內容進來前篩檢                          │
│   screenToolResult(...)       → 工具結果回來後篩檢                          │
│   toolApprovalGate(tool)      → 這個工具要不要人批准                         │
├────────────────────────────────────────────────────────────────────────────┤
│ 持久化（★ 也是注入的，引擎不碰資料庫）                                        │
│   emit(entry)   → 寫一筆 SessionEntry                                       │
│   tape(rec)     → 寫一筆 TapeRecord                                         │
│   tapeRows · tapeMode("shadow"|"serve") · tapeFold                         │
├────────────────────────────────────────────────────────────────────────────┤
│ 觀測                                                                        │
│   recordModelCall(...) · recordLlmRequest(...) ·                           │
│   onProgress(...) · onGapWork(...) · onDelta(...) · onTextBlockStart()     │
├────────────────────────────────────────────────────────────────────────────┤
│ 控制                                                                        │
│   cancel: AbortSignal                                                      │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 這個設計的核心主張

**引擎不擁有任何狀態，也不做任何決策。**

```
                       ┌─────────────────────────────────┐
                       │          Orchestrator           │
                       │  （擁有身分、政策、儲存、觀測）    │
                       └───────────────┬─────────────────┘
                                       │ 注入
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  screenExternalContent()        emit() / tape()              toolApprovalGate()
  「這段外部內容安全嗎」          「把這件事記下來」            「這個工具要批准嗎」
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       ▼
                       ┌─────────────────────────────────┐
                       │        Harness（純執行）         │
                       │  只負責：跟模型講話、呼叫工具     │
                       └─────────────────────────────────┘
```

這對應 `SECURITY.md` 的一句話：

> The agent and software it runs in a sandbox are **not trusted to make authorization
> decisions**. Core is intended to enforce identity, scope, grants, delivery, and
> deterministic effect gates around them.

**Harness 是 agent 的一部分，所以它也不被信任做授權決定。**
一個第三方 harness adapter 即使有 bug 或惡意，也拿不到繞過權限的路徑
—— 因為它手上只有 core 給的 callback。

### 3.3 `overheard`：只有多人場景才有的欄位

```typescript
priorTurns?: ConversationTurn[];
overheard?: OverheardEntryPayload[];
```

```
#eng 頻道：
  10:01  Alice: 「今天 deploy 排在幾點？」
  10:02  Bob:   「三點，但 CI 還在跑」
  10:05  Carol: 「@qm 幫我看一下 CI 現在什麼狀況」
                 ▲
                 └─ 這是 input
                    10:01 和 10:02 是 overheard —— Agent 沒被叫，但需要知道
```

沒有 `overheard`，Agent 會問「哪個 CI？」。有了它，Agent 知道在講今天三點的 deploy。

但 `overheard` 也是最典型的 prompt injection 入口 ——
任何頻道成員都能寫。所以它在安全篩檢裡有專屬的來源標籤：

```typescript
for (const message of input.overheard ?? []) {
  if (message.role === "user" && message.text.trim()) {
    payloads.push({ source: `overheard:${message.name ?? "participant"}`, content: message.text });
  }
}
```

### 3.4 `systemCacheBoundary`：明確告訴引擎快取切在哪

```typescript
systemPrompt: string;
systemCacheBoundary?: number;
```

System prompt 由 org soul + scope soul + 環境事實 + 安全政策等多段組成，
其中前面幾段是穩定的、後面幾段是每輪變動的。
**`systemCacheBoundary` 是一個字元索引，告訴引擎「這個位置之前可以做 prompt cache」。**

Core 知道哪些段落穩定（它自己組的），引擎知道怎麼下 cache marker
（各家 API 不同）。**知識分工，各出一半。**

---

## 四、Entries 與 Tape：兩種歷史，兩種用途

### 4.1 為什麼需要兩份

Part 2 提過三軌記錄，這裡看它在 harness 層怎麼用：

```
Entries（SessionEntry[]）              Tape（TapeRecord[]）
─────────────────────────────────────────────────────────────────────
產品視角                                模型視角
type: user/assistant/thinking/text/    kind: message/…
      tool_call/tool_result/soul/       payload: harness 原生格式
      system/delivery/approval_*
帶 scopeLabel（可依受眾過濾）           帶 scopeLabel + harness + coversEntrySeq
給 UI 渲染、給人看                      原樣餵回模型
可以刪減                                ★ 刪減會破壞 tool_call 配對
```

`tapeMode` 有兩種：

```typescript
tapeMode?: "shadow" | "serve";
```

- **shadow** — 照錄，但不使用。用來累積覆蓋率、驗證錄製正確性。
- **serve** — 真的拿 tape 重建模型 context。

**先 shadow 一段時間、確認覆蓋率夠了再切 serve** —— 這是很成熟的漸進式上線做法。
`SessionStore.tapeCoverage(sessionId)` 就是那個判斷依據。

### 4.2 `forModelContext`：從 entries 重建模型視角

```typescript
export function forModelContext(
  entries: SessionEntry[],
  opts: { includeSecurityTainted?: boolean } = {},
): SessionEntry[] {
  const replayable = entries.filter(
    (e) =>
      e.type !== "thinking" &&        // 思考文字不重放
      e.type !== "text" &&            // 串流片段不重放
      e.type !== "soul" &&            // soul 走 systemPrompt，不在歷史裡
      (e.payload as { kind?: unknown } | null)?.kind !== "turn_failure",
  );
  const latest = replayable.findLast((e) => contextSummaryPayload(e));
  const visible = replayable.filter((e) => {
    const securityTainted = (e.payload as { securityTainted?: unknown } | null)?.securityTainted === true;
    return opts.includeSecurityTainted || !securityTainted;
  });
  if (!latest) return visible;
  const throughSeq = contextSummaryPayload(latest)!.throughSeq;
  return [
    ...(visible.includes(latest) ? [latest] : []),
    ...visible.filter((e) => !contextSummaryPayload(e) && e.seq > throughSeq),
  ];
}
```

三段邏輯：

```
① 過濾不可重放的類型
   thinking / text / soul / turn_failure

② 過濾被安全篩檢標記為污染的條目（securityTainted）
   ★ 預設排除；只有明確要求時才含入
   → 被判定為 injection 的內容不會回到模型 context

③ 套用最近一次 context summary
   找到最後一筆 context_summary，取它的 throughSeq
   → 輸出 = [summary 本身] + [seq > throughSeq 的條目]
```

### 4.3 `throughSeq`：壓縮的錨點

```typescript
export interface ContextSummaryPayload {
  kind: "context_summary";
  throughSeq: number;   // ← 這份摘要涵蓋到第幾筆
  text: string;
}
```

```
entries:  1  2  3  4  5  6  7  8  9  10  11  12
                              ▲
                    context_summary(throughSeq=7) 存在 seq=8

模型看到的：  [summary(涵蓋 1–7)]  9  10  11  12
                    ▲
             seq=8 本身也是 summary，會被納入
```

**摘要本身就是一筆 SessionEntry（`type: "system"`）**，
不是存在別的地方的 metadata。這帶來三個好處：

1. 它自然被租約保護、自然有 `seq`、自然持久化
2. `findLast` 就能找到最新的一份 —— 不需要額外索引
3. 重複壓縮時，新摘要的 `throughSeq` 更大，舊摘要自動失效

跟 OpenWorker 用一個獨立的 `CompactionState` 物件相比，
**QM 把壓縮點內嵌進訊息串本身**。兩種都合理，QM 這種在多實例環境下少一份要同步的狀態。

### 4.4 `capCompactLine`：頭尾都留

```typescript
const MAX_COMPACT_ENTRY_CHARS = 16_000;
const COMPACT_ENTRY_TAIL_CHARS = 2_000;

function capCompactLine(s: string): string {
  if (s.length <= MAX_COMPACT_ENTRY_CHARS) return s;
  const notice = `…[truncated — ${s.length} chars]…`;
  return (
    headSlice(s, MAX_COMPACT_ENTRY_CHARS - COMPACT_ENTRY_TAIL_CHARS - notice.length) +
    notice +
    tailSlice(s, COMPACT_ENTRY_TAIL_CHARS)
  );
}
```

**保留開頭 14K + 結尾 2K，中間標註被截了多少。**
理由很實務：一個超長的指令輸出，開頭通常是它在做什麼、
結尾通常是結果或錯誤訊息，中間是重複的進度條。

### 4.5 `INTERRUPTED_TOOL_RESULT`：一句話講清楚三件事

```typescript
export const INTERRUPTED_TOOL_RESULT =
  "[interrupted — the platform restarted while this tool call was running and its outcome was not recorded. Check what actually happened before redoing anything with side effects.]";
```

這個常數同時被兩個地方使用：**平台重啟**（context-compaction）
與**受眾過濾**（replay.ts，見 Part 2）。它告訴模型三件事：

1. **這個工具呼叫被中斷了**
2. **它的結果沒有被記錄** —— 所以不知道成功還失敗
3. **重做之前先查實際發生了什麼** —— 特別是有副作用的操作

第三句是關鍵。沒有它，模型看到「中斷」的直覺反應是重試 ——
如果那是「已經寄出的信」，重試就是寄第二封。

---

## 五、Runtime 選擇：三層繼承 + 組織核准清單

`harness-router.ts` 只有 116 行，但解決了一個治理問題：
**誰決定用哪個引擎與模型？**

```typescript
export function resolveRuntimeChoice(
  config, orgScopeId, scope, fallback, requested?,
): RuntimeChoice {
  const approved = config.getApprovedHarnesses() ?? [fallback.harnessId];
  ...
}
```

### 5.1 解析順序

```
┌────────────────────────────────────────────────────────────────────────┐
│ ① approved = 組織核准的 harness 清單                                    │
│    ★ 這是硬性上限，後面每一步都要通過它                                  │
├────────────────────────────────────────────────────────────────────────┤
│ ② safeFallback                                                         │
│    如果傳進來的 fallback 不在核准清單裡（或模型不被該引擎支援）           │
│    → 換成第一個核准的 harness + 它的預設模型                            │
├────────────────────────────────────────────────────────────────────────┤
│ ③ org 層設定 → 驗證 → 不通過就退回 safeFallback                         │
├────────────────────────────────────────────────────────────────────────┤
│ ④ scope 層設定（若有）覆蓋 org                                          │
├────────────────────────────────────────────────────────────────────────┤
│ ⑤ requested（這一輪明確指定的）覆蓋 scope                                │
├────────────────────────────────────────────────────────────────────────┤
│ ⑥ 最終驗證                                                             │
│    if (!approved.includes(choice.harnessId) ||                         │
│        !modelSupportedByHarness(choice.modelId, choice.harnessId)) {    │
│      if (requested?.harnessId || requested?.modelId)                   │
│        throw new NonRetryableTurnError(`runtime … is not approved`);    │
│      ...  ← 沒明確指定的話，靜默退回                                     │
│    }                                                                   │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 兩個值得學的細節

**① 每一層都重新驗證，不是只驗最後一次**

org 設定過期（那個引擎被下架了）時，不會拖著整個 scope 一起壞
—— 它在第 ③ 步就退回 safeFallback。

**② 明確要求 vs 繼承而來，失敗處理不同**

```
使用者明確指定 "用 codex" 但 codex 未核准
   → throw NonRetryableTurnError  ★ 大聲失敗，因為這是使用者的意圖

繼承來的設定不合法（org 設了但引擎被下架）
   → 靜默退回合法選項        ★ 不該讓使用者為管理員的過期設定買單
```

**「明確要求要大聲失敗，繼承的可以靜默降級」** ——
這條原則適用於任何有繼承鏈的設定系統。

`NonRetryableTurnError` 這個型別本身也值得注意：
它告訴上層的重試機制「這個錯誤重試沒用」。
配置錯誤重試一百次還是配置錯誤。

---

## 六、`HarnessTurnResult`：回合怎麼結束

```typescript
export interface HarnessTurnResult {
  reply: string;
  silent?: boolean;                 // stay_silent / finish_silently
  stopped?: true;                   // 被中斷
  pendingApprovals?: Array<{        // 停在批准上
    command: string;
    reason: string;
    kind?: "approval";
    matched?: string;               // 命中哪條規則
    purpose?: string;
    approvalKey?: string;           // 冪等鍵
  }>;
  pausedOnApproval?: boolean;
  modelCalls?: number;
  cacheUsage?: { cacheRead: number; cacheWrite: number; uncachedInput: number };
  compileMs?: number;
  tapeWriteFailed?: boolean;        // ★ tape 寫失敗了，但回合本身成功
}
```

兩個欄位值得單獨講：

### 6.1 `matched`：批准卡要顯示「命中哪條規則」

```
┌────────────────────────────────────────────────────────────────┐
│  需要你批准                                                     │
│                                                                │
│  指令：  rm -rf ./build/cache                                   │
│  原因：  recursive delete            ← reason                   │
│  規則：  \brm\b[^\n]*(?:-[a-zA-Z]*r|--recursive)  ← matched     │
│  用途：  清掉舊的建置快取以重跑測試   ← purpose（模型自述）        │
│                                                                │
│                             [ 拒絕 ]  [ 這次 ]  [ 一直允許 ]     │
└────────────────────────────────────────────────────────────────┘
```

**顯示 `matched` 讓管理員知道「是哪條規則太寬或太嚴」**，
而不是只能猜。這對調整命令政策非常關鍵。

### 6.2 `tapeWriteFailed`：部分失敗要能被表達

Tape 是輔助記錄。它寫失敗不該讓整個回合失敗
—— 但也不能靜默吞掉，否則覆蓋率統計會騙人。

**回傳一個布林讓上層決定怎麼處理。** 這是「部分失敗」的正確表達：
不是拋例外，也不是當作沒事。

---

## 七、OpenCode adapter：一個具體的接法

看一段 OpenCode harness 怎麼把 QM 的模型套進去，能理解抽象的實際代價：

```typescript
tools: {
  ...enabledTools,
  task: true,
  read: false,       // ← 關掉 OpenCode 自己的 read
  write: false,      // ← 關掉 OpenCode 自己的 write
  bash: false,       // ← 關掉 OpenCode 自己的 bash
},
```

```typescript
agent: {
  qm: { mode: "primary", prompt: "", tools: { ...enabledTools, task: true } },
  research: {
    mode: "subagent",
    description: "Research a bounded question and report evidence.",
    prompt: "Complete only the delegated research task.",
    tools: { ...enabledTools, task: false },
  },
  code: {
    mode: "subagent",
    description: "Implement or inspect a bounded code task.",
    prompt: "Complete only the delegated code task.",
    ...
  },
}
```

兩個關鍵動作：

**① 關掉引擎自帶的檔案 / shell 工具**

OpenCode 本來就有 `read` / `write` / `bash`，但那些工具會直接碰
**跑 OpenCode 那台機器**的檔案系統 —— 不是那個 scope 的沙箱。
所以全部關掉，換成 QM 的工具。

**② 子代理也要繼承工具限制**

`research` 與 `code` 兩個 subagent 拿到的是同一組 `enabledTools`，
而且 `task: false`（不能再開子代理）。
**如果只限制主 agent 而放過 subagent，那道限制等於不存在。**

這就是 harness abstraction 的實際代價：
**每接一個引擎，都要盤點它自帶了什麼、哪些必須關掉。**

---

## 八、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **profile 自報三軸能力**<br>vs 假設所有引擎一樣 | UI 與 orchestrator 需要執行時知道「這個引擎能不能中斷 / 收圖片」 | 假設一致會讓不支援的能力在使用者按下去才炸 | 只接一個引擎時 |
| **能力用「方法存在與否」**<br>vs 回傳 null 的存根 | `if (harness.models.pickAckEmoji)` 一行就能安全降級 | 存根會讓「不支援」與「執行失敗」無法區分 | 沒有 |
| **60 欄位的注入式 TurnInput**<br>vs 讓 harness 自己拿 | 引擎拿不到 DB、政策、身分 → 一個惡意 adapter 也繞不過權限 | 讓引擎自己查儲存 = 每個 adapter 都要重新實作權限檢查 | 全部 adapter 都是自己寫且可信時 |
| **Entries / Tape 雙軌**<br>vs 只存一份 | 過濾規則相衝：給人看的要能刪減，給模型的刪了就壞 | 單軌時受眾過濾會製造孤兒 tool_call | 沒有受眾過濾需求時 |
| **tape 先 shadow 再 serve** | 用 `tapeCoverage` 量化「錄得夠不夠」再切換 | 直接 serve 會讓舊 session 拿到不完整的 context | 沒有既有資料要遷移時 |
| **摘要是一筆 SessionEntry**<br>vs 獨立的壓縮狀態物件 | 自然被租約保護、自然有 seq、多實例下少一份要同步的狀態 | 獨立物件要處理與訊息串的一致性 | 需要對摘要做結構化查詢時 |
| **截斷保留頭 + 尾**<br>vs 只留頭 | 開頭是「在做什麼」，結尾是結果 / 錯誤，中間常是進度條 | 只留頭會丟掉最重要的結論 | 內容是純追加日誌時 |
| **明確要求 throw、繼承的靜默降級** | 使用者的意圖失敗要看得見；管理員的過期設定不該擋住使用者 | 兩者都 throw = 管理員一改壞設定全公司卡住 | 沒有 |
| **`NonRetryableTurnError` 獨立型別** | 配置錯誤重試一百次還是配置錯誤 | 統一 Error 會讓重試邏輯浪費額度 | 沒有 |
| **接引擎時關掉它自帶的工具** | 引擎自帶的 bash 碰的是宿主機，不是 scope 沙箱 | 不關 = 整個 scope 隔離失效 | 引擎本來就跑在沙箱裡時 |

---

## 九、系列導航

- [Part 1：多人協作 Agent 平台的架構全景](/yennj12_blog_V4/posts/qm-multiplayer-agent-part1-architecture-zh/)
- [Part 2：Scope 與 Resolution — 一次對話如何解析出身分、權限與工作區](/yennj12_blog_V4/posts/qm-multiplayer-agent-part2-scope-resolution-zh/)
- **Part 3（本篇）：Harness 抽象 — 一套核心驅動四種 Agent 引擎**
- [Part 4：安全模型 — 三種 Posture、命令政策與誠實的威脅模型](/yennj12_blog_V4/posts/qm-multiplayer-agent-part4-security-model-zh/)
- [Part 5：Sandbox、Skills、Cron 與部署 — 讓 Agent 擁有一台持久的電腦](/yennj12_blog_V4/posts/qm-multiplayer-agent-part5-sandbox-skills-cron-zh/)

---

## 本篇可以帶走的六個模式

1. **抽象的價值在於誠實表達差異**，不是抹平差異。
   `profile` 讓「這個引擎不支援 thinking-level」成為可查詢的事實。
2. **可選能力用「方法存在與否」表達**，不要用回傳 null 的存根
   —— 呼叫端才分得清「不支援」與「失敗」。
3. **把不可信元件的所有出口都變成注入的 callback**：
   它拿不到儲存、政策與身分，就繞不過它們。
4. **兩種讀者就要兩份記錄**：給人看的可以刪減，給模型的刪了就壞。
5. **漸進式上線要有量化門檻**：`tapeCoverage` 決定何時從 shadow 切 serve。
6. **繼承鏈上的失敗要分兩種**：明確要求大聲失敗，繼承而來靜默降級。

> 本文分析基於 2026-08 的 `main` 分支（commit `0f0e0ad`）。
