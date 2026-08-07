---
title: "QM 深度解析（五）：Sandbox、Skills、Cron 與部署 — 讓 Agent 擁有一台持久的電腦"
date: 2026-08-07T18:00:00+08:00
draft: false
weight: 5
description: "拆解 QM 的持久化能力：三種沙箱後端與能力損失偵測、Skills 的簽章與 git pack 匯入、Cron 的 leader lease 與收件人同意、三種記憶策略的抽取 prompt，以及部署目錄與私有 fork 兩種客製路線。"
categories: ["engineering", "ai", "all"]
tags: ["QM", "AI Agent", "Sandbox", "microVM", "Agent Skills", "Cron", "Memory", "繁體中文"]
authors: ["yen"]
readTime: "29 min"
series: ["qm-deep-dive"]
---

> *大部分 Agent 的執行環境是「每次任務開一個乾淨容器」。*
> *乾淨很好，直到你發現每一次任務的前三分鐘都在 `pip install`。*
> *QM 反過來：每個 scope 一台**持久**的電腦 —— 裝過的工具還在，登入過的服務還登著。*
> *代價是：那台電腦裡有可用的憑證，而且它會一直在那裡。*

---

本篇是 [QM 深度解析系列](/yennj12_blog_V4/posts/qm-multiplayer-agent-part1-architecture-zh/)
的最後一篇，涵蓋 `src/sandbox/`（3,226 行）、`src/skills/`（1,904 行）、
`src/cron/`（699 行）、`src/memory/`（1,247 行）與部署層。

---

## 一、Agent Computer：不是容器，是電腦

### 1.1 命名本身就是設計

QM 沒有把它叫 `Container` 或 `Runtime`，而是 `AgentComputer`：

```typescript
export interface AgentComputerSpec {
  os?: string;
  runtimes?: string[];
  tools?: string[];
  notInstalled?: string[];    // ★ 「沒裝什麼」也是規格的一部分
  cpus?: number;
  memoryMb?: number;
  diskGb?: number;
  homeDir?: string;
  workdir?: string;
}

export interface AgentComputerProfile {
  backend: string;
  writablePersistence: "snapshot_to_workspace" | "resident_disk";
  processSessions: boolean;
  egressEnforcement?: "none" | "ip_port" | "domain";
  spec?: AgentComputerSpec;
}
```

`notInstalled` 這個欄位很少見。它的用途在這裡：

```typescript
export function visibleNotInstalled(notInstalled: readonly string[], extraTools: readonly string[]): string[] {
  const advertised = new Set(extraTools.map((line) => line.trim().split(/\s+/)[0]).filter(Boolean));
  return notInstalled.filter((name) => !advertised.has(name));
}
```

**明確告訴模型「這台機器上沒有 X」**，比讓它試一次 `command not found`
再自己想辦法省一輪。而且會扣掉「部署層額外裝了的」—— 避免說謊。

`visibleTools` 則是去重：

```typescript
export function visibleTools(tools: readonly string[]): string[] {
  const seen = new Set<string>();
  return tools.filter((line) => {
    const binary = line.trim().split(/\s+/)[0];
    if (!binary || seen.has(binary)) return false;
    seen.add(binary);
    return true;
  });
}
```

同一個 binary 只列一次 —— 這些字串會進 system prompt，重複就是浪費 token。

### 1.2 三種後端

```
┌──────────────┬──────────────────┬──────────────┬──────────────────┬───────┐
│ backend      │ writablePersist. │processSessions│ egressEnforcement│ 行數  │
├──────────────┼──────────────────┼──────────────┼──────────────────┼───────┤
│ local-docker │ resident_disk    │ ✓            │ none             │  497  │
│ 本機開發      │ 磁碟就在那        │              │                  │       │
├──────────────┼──────────────────┼──────────────┼──────────────────┼───────┤
│ aws-microvm  │ snapshot_to_     │ ✓            │ none             │  524  │
│ Firecracker  │ workspace        │              │                  │ +375  │
│ 類的微 VM     │ ★ 快照回工作區    │              │                  │(API)  │
├──────────────┼──────────────────┼──────────────┼──────────────────┼───────┤
│ sprites      │ resident_disk    │ ✓            │ domain           │  511  │
│ Fly.io       │                  │              │ （有 proxy 時）   │       │
└──────────────┴──────────────────┴──────────────┴──────────────────┴───────┘
```

**`sprites` 是唯一支援 domain 級 egress 強制的後端**，而且是有條件的：

```typescript
egressEnforcement: opts.egressProxyUrl ? "domain" : "none",
```

再往上還有一層條件：

```typescript
export function effectiveEgressEnforcement(
  profile: AgentComputerProfile,
  controlPlane: { signingSecret?: string; apiBaseUrl?: string },
): EgressEnforcement {
  return controlPlane.signingSecret && controlPlane.apiBaseUrl
    ? (profile.egressEnforcement ?? "none")
    : "none";
}
```

**沒有簽章密鑰與 API base URL，egress 強制就是 `none`。**
因為 proxy 需要驗證請求真的來自 core。這對應 `SECURITY.md` 的：

> **Egress enforcement is conditional.** Force-through egress depends on backend
> network enforcement, and core does not yet reject every backend that is too coarse
> for the requested policy.

### 1.3 能力損失偵測：換後端時會少什麼

這是我覺得最漂亮的一段：

```typescript
const SANDBOX_CAPABILITIES: ReadonlyArray<{ label: string; supported: (s: Sandbox) => boolean }> = [
  { label: "process sessions (background work, dev servers)", supported: supportsProcessSessions },
  { label: "home backup (publish, resident-auth capture)", supported: supportsAgentComputerBackup },
];

const ENFORCEMENT_RANK: Record<EgressEnforcement, number> = { none: 0, ip_port: 1, domain: 2 };

export function capabilitiesLostMovingTo(from: Sandbox, to: Sandbox): string[] {
  const lost = SANDBOX_CAPABILITIES.filter((c) => c.supported(from) && !c.supported(to)).map((c) => c.label);
  const fromEgress = from.profile.egressEnforcement ?? "none";
  const toEgress = to.profile.egressEnforcement ?? "none";
  if (ENFORCEMENT_RANK[toEgress] < ENFORCEMENT_RANK[fromEgress]) {
    lost.push(`egress enforcement (${fromEgress} on the source, ${toEgress} on the target)`);
  }
  return lost;
}
```

```
管理員想把沙箱從 sprites 換成 aws-microvm
       │
       ▼
capabilitiesLostMovingTo(sprites, aws)
       │
       ▼
["egress enforcement (domain on the source, none on the target)"]
       │
       ▼
遷移前的警告畫面：「這次搬遷會失去 domain 級的外連限制」
```

**遷移不是靜默降級，是一份明確的損失清單。**
`ENFORCEMENT_RANK` 讓「安全性降低」變成可以比較的數值，
而不是「不一樣」這種無法判斷的描述。

大多數系統換 backend 時只會說「已切換」。列出損失是額外的功
—— 但它防止的是「三個月後才發現外連限制早就沒了」。

### 1.4 可選能力用 type guard 表達

```typescript
export function supportsProcessSessions(sandbox: Sandbox): sandbox is ProcessSandbox {
  return (
    sandbox.profile.processSessions === true &&
    typeof sandbox.startProcess === "function" &&
    typeof sandbox.readProcess === "function" &&
    typeof sandbox.writeStdin === "function" &&
    typeof sandbox.signalProcess === "function" &&
    typeof sandbox.listProcesses === "function"
  );
}
```

注意它檢查了**六件事**：profile 宣告 + 五個方法都存在。
**宣告與實作不一致時，以實作為準。** 一個宣告 `processSessions: true`
但沒實作 `writeStdin` 的後端，會被正確判為不支援，而不是在執行時炸掉。

而回傳型別 `sandbox is ProcessSandbox` 讓 TypeScript 在 `if` 之後
自動收窄型別，呼叫端不需要 `!` 或 `as`。

不支援時的錯誤也是專用型別：

```typescript
export class CapabilityUnsupportedError extends Error {
  readonly backend: string;
  readonly capability: string;
  constructor(backend: string, capability: string) {
    super(`this computer's substrate (${backend}) does not support ${capability}`);
    ...
  }
}
```

錯誤訊息裡有 **backend 名稱**與**能力名稱** —— 模型讀到這句話
就知道「不是我用錯了，是這台機器不行」，於是會換方法而不是重試。

### 1.5 `hasParentPathSegment`：一行的路徑守衛

```typescript
export function hasParentPathSegment(path: string): boolean {
  return path.split("/").includes("..");
}
```

**用 `split("/")` + `includes("..")`，而不是 `path.includes("..")`。**
差別在於後者會誤判 `my..file.txt`（合法檔名），
而前者只在 `..` 是完整的路徑片段時才判為危險。

同樣的模式在 skills 也出現：

```typescript
export function safeSkillFilePath(path: string): string {
  const p = path.replace(/\\/g, "/").replace(/^\.\/+/, "").replace(/\/+$/, "");
  const parts = p.split("/").filter(Boolean);
  if (!parts.length || path.startsWith("/") ||
      parts.some((part) => part === "." || part === ".." || part.includes("\0"))) {
    throw new Error(`invalid skill file path: ${path}`);
  }
  return parts.join("/");
}
```

反斜線正規化（Windows）、去掉 `./` 前綴、去掉尾端斜線、
拒絕絕對路徑、拒絕 `.` / `..` 片段、拒絕 NUL 位元組。
**六道檢查，回傳正規化後的路徑而不是布林** —— 呼叫端用的一定是檢查過的版本。

---

## 二、Skills：可簽章、可授權、可從 git 匯入

### 2.1 資料形狀

```typescript
type SkillStatus = "draft" | "reviewed" | "published" | "archived";

export interface SkillManifest {
  name: string;
  description: string;
  requiredCapabilities: string[];
  body: string;
  files?: SkillFile[];
}

export interface Skill {
  id: string;
  scopeId: ScopeId;          // ★ skill 屬於某個 scope，不是全域
  manifest: SkillManifest;
  signature: string;         // ★ HMAC
  status: SkillStatus;
  createdBy: string;
  ...
}
```

四個狀態構成審核流程：

```
draft ──▶ reviewed ──▶ published ──▶ archived
  │           │            │
  │           │            └─ 全 org 可用（需管理員核准）
  │           └─ 已審核，可授權給其他 scope
  └─ 只有作者的 scope 看得到
```

README 的描述：

> Skills are **scope-owned and shareable by grant**, with **admin-gated promotion**
> to the whole org and skill packs imported from git repositories.

**skill 走的是跟檔案一樣的 ACL grant 機制**（Part 2 §6），
不是另一套權限系統。

### 2.2 簽章：內容的正規化雜湊

```typescript
function canonicalFiles(files: SkillFile[] | undefined): Array<[string, string, boolean]> {
  return [...(files ?? [])]
    .map((f): [string, string, boolean] => [f.path, f.content, f.executable === true])
    .sort((a, b) => { if (a[0] < b[0]) return -1; if (a[0] > b[0]) return 1; return 0; });
}
```

排序後才算雜湊 —— **檔案順序不同不該產生不同簽章**。
`executable === true` 的正規化也是同理（`undefined` 與 `false` 要等價）。

簽章的用途是**偵測 skill 內容在儲存後被竄改**。
考慮到 skill body 會直接進入模型的 system context，
這相當於「有人偷偷改了 Agent 的指令」—— 需要能偵測。

### 2.3 從 git 匯入 skill pack

`pack-fetcher.ts`（284 行）讓組織可以把 skill 放在 git repo 裡：

```typescript
export interface GitFetcherOptions {
  resolveAuth?: (pack: SkillPack) => Promise<GitAuth | undefined>;
  gitBin?: string;
  timeoutMs?: number;
  maxFiles?: number;          // ★ 上限
  maxTotalBytes?: number;     // ★ 上限
  allowLocalRepos?: boolean;  // ★ 預設關閉
  lookup?: (host: string) => Promise<string[]>;   // ★ DNS 解析可注入
}
```

而它 import 的東西透露了防護方向：

```typescript
import { lookup as dnsLookup } from "node:dns/promises";
import { isIP } from "node:net";
import { isPrivateNetworkIp } from "../util/network.ts";
```

**先解析 DNS，檢查是不是私有網段，才允許 clone。**
這跟一般的 SSRF 防護是同一件事 —— 一個「skill pack URL」
如果指向 `http://169.254.169.254/`，那 clone 就變成內網探測。

三道量化上限（`timeoutMs` / `maxFiles` / `maxTotalBytes`）
則是防 zip bomb 式的資源耗盡。

`allowLocalRepos` 預設關閉，只有測試會打開 —— **測試用的放寬要是明確的開關**，
不是「如果路徑看起來像本機就允許」這種隱性判斷。

### 2.4 物化：投影到沙箱，並偵測漂移

```typescript
export interface SkillMaterializer {
  materializeIndex(sandbox, handle, resolved, current?): Promise<void>;
  materializeTree(sandbox, handle, resolution, bundles?, current?): Promise<void>;
}

function materializationKey(handle: SandboxHandle): string {
  const sandboxId = createHash("sha256").update(handle.id).update("\0").update(handle.rootDir).digest("hex");
  return `skills:projection:${sandboxId}`;
}
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Skill 儲存在 Postgres（scope-owned，有 grant，有簽章）                     │
│                            │                                             │
│                            ▼  materialize（投影）                         │
│ 沙箱檔案系統：                                                            │
│   skills/                                                                │
│   ├── .index            ← 目錄：所有可用 skill 的名稱 + 描述              │
│   ├── .packs/           ← 從 git 匯入的 pack                              │
│   └── <skill-name>/                                                      │
│       ├── SKILL.md                                                       │
│       └── <bundled files>                                                │
│                                                                          │
│ ★ Agent 用 read/execute 就能用 skill —— 不需要「載入 skill」的工具        │
└──────────────────────────────────────────────────────────────────────────┘
```

**這是與 OpenWorker 明顯不同的設計。** OpenWorker 有一個
`load_skill(name)` 工具做漸進式揭露；QM 直接把 skill 投影成檔案，
只在 context 裡放 `.index`。

兩者的效果相同（context 裡只有目錄），但 QM 的做法不需要額外的工具
—— **它重用了「Agent 會讀檔案」這個既有能力**。這跟 Part 2 的
「grant 表現成 `shared/` 路徑」是同一個哲學。

`materializationKey` 用 `handle.id` + `\0` + `rootDir` 做雜湊。
那個 `\0` 分隔符是為了避免 `("ab", "c")` 與 `("a", "bc")` 撞雜湊
—— 細節，但正確。

而 `current?: () => Promise<...>` 這個可選參數是**漂移偵測**：
比對「現在沙箱裡是什麼」與「應該是什麼」，只寫差異。
持久沙箱的必要設計 —— 每次都全量重寫會很慢。

### 2.5 內建 18 個 seed skill

```
admin              browse            cloud-cli        connect-apps
dropbox            email-draft-in-voice               email-voice-profile
github-gitlab      google-drive-sheets                google-workspace
interactive-login  linear            memory           morning-digest
popular-web-designs                  publish          taste-skill
use-shared-credential
```

注意這裡面**沒有一個是「XX API 的 wrapper」** —— 它們是
「怎麼用這台電腦上已有的 CLI 完成某件事」的說明書。
`cloud-cli`、`github-gitlab`、`google-workspace` 都是這個模式。

`email-voice-profile` + `email-draft-in-voice` 這一對特別有意思：
前者從你過去寄出的信裡學出你的寫作語氣、後者用那個語氣起草
—— 對應 README 的「Learn your writing voice from past sends」。

---

## 三、Cron：多實例下的排程

### 3.1 兩層去重

```typescript
const TICK_LEASE_KEY = "cron:scheduler:tick";

export interface SchedulerDeps {
  crons: CronStore;
  deliveries: DeliveryStore;
  idempotency: IdempotencyStore;      // ★ 冪等
  identity: IdentityService;
  run: (req: TurnRequest) => Promise<TurnResult>;
  currentScopeMembers?: CurrentScopeMembers;
  maxFiresPerTick?: number;           // ★ 單次 tick 的上限
  leaderLease?: LeaderLease;          // ★ 領導者租約
  jobQueue?: CronJobQueue;            // ★ pg-boss
  sweepAsks?: (now: number) => Promise<void>;
  ...
}
```

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 防重複層一：LeaderLease                                                   │
│   多個 core 實例同時跑，只有拿到 "cron:scheduler:tick" 租約的那個會 tick  │
│   → 避免三台機器同時掃描 due 任務                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ 防重複層二：pg-boss 工作佇列                                              │
│   tick 只負責「把到期的 cron 排進佇列」，實際執行由 worker 取出            │
│   → 掃描與執行解耦；一個慢任務不阻塞掃描                                  │
├──────────────────────────────────────────────────────────────────────────┤
│ 防重複層三：IdempotencyStore                                              │
│   即使前兩層都失效，同一次觸發也只會產生一次副作用                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**三層。** 對照 OpenWorker 用一個 `_running_ids` 集合做 skip-on-overlap
—— 那是單進程的解法，多實例下完全無效。這是「durable by default」
（`AGENTS.md`）在排程層的具體體現。

`maxFiresPerTick` 是最後的護欄：一次 tick 最多排多少個，
避免「系統停機兩天後開機，一次排進 5,000 個 job」。

### 3.2 時區：拒絕無效輸入

```typescript
export const DEFAULT_CRON_TIMEZONE = "America/Los_Angeles";
const MIN_RECURRING_CRON_MS = 60_000;

function normalizeTimezone(input: string | undefined, fallback = DEFAULT_CRON_TIMEZONE): string {
  const tz = (input?.trim() || fallback).trim();
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
  } catch {
    throw new Error(`invalid IANA timezone: ${tz}`);
  }
  return tz;
}
```

**用 `Intl.DateTimeFormat` 當驗證器** —— 不需要維護一份 IANA 時區清單，
Node 內建的 ICU 資料就是最新的權威來源。

`MIN_RECURRING_CRON_MS = 60_000` —— 最短一分鐘。
沒有這條，一個 `* * * * * *`（每秒）的 cron 會把系統打爆。

還有一個 `recoverNextFireAt`：系統停機後重算下次觸發時間，
而不是照著過期的 `nextFireAt` 補跑一堆。

### 3.3 收件人同意與權限升級檢查

```typescript
import {
  assertNoEscalation,
  buildTriggerBase,
  contentPart,
  createDeduped,
  setTriggerRecipientConsent,
  type CreateTriggerInput,
} from "../triggers/trigger-store.ts";

export interface CreateCronInput extends CreateTriggerInput {
  schedule: Cron["schedule"];
  title?: string;
  action?: string;
  message?: string;
  runAs?: Cron["runAs"];       // ★ 用誰的身分跑
  members?: Principal[];
}
```

兩個機制值得注意：

**① `assertNoEscalation`**

Cron 是「未來會自動執行的動作」，所以建立它就是**授權未來的行為**
—— 正是 Part 4 講的那類決定。`assertNoEscalation` 確保
建立者不能建立一個權限超過自己的 cron。

**② `setTriggerRecipientConsent`**

```
Alice 建立一個 cron：「每天早上把 CI 摘要發給 Bob」
       │
       ▼
Bob 需要同意接收       ← ★ 沒有同意，Alice 不能用 Agent 每天騷擾 Bob
```

**排程遞送需要收件人同意。** 這在單人 Agent 裡不存在
—— 只有多人平台才會有「我可以叫 Agent 每天去煩誰」的問題。

### 3.4 `CRON_FIRE_REPLY_MAX_CHARS = 2000`

```typescript
function truncate(s: string, maxChars: number): string {
  return s.length <= maxChars ? s : `${s.slice(0, maxChars - 3)}...`;
}
```

排程觸發的回覆有 2000 字上限。一個跑歪的 cron 每天在頻道倒一萬字，
比不跑更糟。**自動化的輸出要有上限。**

---

## 四、Memory：三種策略與抽取 prompt

### 4.1 政策與策略是兩件事

```typescript
export type MemoryRecallMode = "off" | "writable" | "visible";
export type MemoryCaptureMode = "off" | "writable";

export const DEFAULT_MEMORY_POLICY: MemoryPolicy = { recall: "visible", capture: "writable" };

export function recallMemoryScopes(policy, layers, writableScopeId): ScopeId[] {
  if (policy.recall === "off") return [];
  if (policy.recall === "writable") return [writableScopeId];
  const scopes = [writableScopeId, ...layers.map((l) => l.scopeId)];
  return [...new Set(scopes)];
}
```

```
recall: "off"       → 不讀任何記憶
recall: "writable"  → 只讀「這次可寫的那個 scope」的記憶
recall: "visible"   → 讀所有掛載層的記憶（org + scope + team…）  ← 預設

capture: "off"      → 不寫
capture: "writable" → 寫到唯一可寫的那個 scope                    ← 預設
```

**寫入永遠只有一個目的地**（`writableMemoryScope` 找唯一的 rw 層），
讀取則可以跨層。這個不對稱是刻意的：讀多寫少，寫入零歧義。

三種策略（`MemoryStrategyKind`）則決定**怎麼寫**：

```
per-turn（預設）  → 每一輪（或一個 burst）結束後抽取事實
scratch-promote   → 先寫進 scratch log，累積後再「畢業」成長期記憶
agent-only        → 只有 Agent 主動呼叫 memory 工具時才寫
```

### 4.2 抽取 prompt 裡的 provenance 規則

`per-turn.ts` 的 `MEMORY_EXTRACTION_PROMPT` 是這個模組最有價值的部分：

```
You extract durable facts worth remembering about the user across FUTURE conversations.
…output ONLY a markdown bullet list (`- fact`), one concise standalone fact per line,
written in the third person (e.g. `- Prefers terse replies`, `- Owns the billing service`).
Include preferences, identifiers, ongoing projects, and how they like to work.

PROVENANCE: a preference, intent, or instruction is a valid fact ONLY when the user's own
message in these exchanges states it. Never derive one from the assistant's reply — an
assistant saying "per X's preference" or describing its own strategy ("queued silently to
avoid spam") is NOT evidence that anyone holds that preference. Likewise EXCLUDE second-hand
claims about a person who did not speak in these exchanges.

EXCLUDE secrets/credentials, one-off trivia, and anything already obvious.
EXCLUDE system mechanics you can look up when needed: API endpoints/headers, credential or
broker plumbing, state-file paths, tool invocation details, schemas. For a standing system
the user relies on (a cron, a watcher, an integration), record its EXISTENCE and purpose as
one fact — not its internals. A user-stated convention ("always via the broker, never raw
tokens") is a preference and belongs in memory; how the broker works does not.

If nothing is worth remembering, output exactly: NONE
```

三條規則，每一條都在防一個真實的失敗模式：

**① PROVENANCE：不要從 Agent 自己的回覆裡推導偏好**

```
Agent 說：「依照 Alice 的偏好，我用簡短格式回覆」
              ▼
天真的抽取器記下：「- Alice 偏好簡短回覆」
              ▼
但 Alice 從來沒說過這句話 —— 是 Agent 自己編的
              ▼
下一輪這條「記憶」變成了事實，永遠回不去
```

**這是記憶系統最危險的失敗模式：模型的幻覺被寫成持久事實，
然後在下一輪被當成前提。** 一次幻覺，永久污染。

而且它明確排除**二手陳述**（「Bob 說 Carol 喜歡…」）
—— 在多人頻道裡，這種內容遍地都是。

**② 排除可以查的系統機制**

```
✗ 「- 用 POST /api/v2/tickets，header 帶 X-Auth-Token」
✓ 「- 有一個每天早上的 CI 摘要 cron，發到 #eng」
```

**「記錄它的存在與目的，不記它的內部細節。」**
內部細節會過時，而且需要時可以查。

**③ 使用者說的慣例是偏好，實作不是**

```
✓ 「- 堅持一律走 broker，不要用原始 token」   ← 使用者說的原則
✗ 「- broker 用 HMAC 簽章，TTL 15 分鐘」      ← 實作細節
```

### 4.3 自主回合的加強規則

```typescript
export const AUTONOMOUS_EXTRACTION_ADDENDUM = [
  'These exchanges are AUTONOMOUS turns: no human spoke. The "User said" content is a system or',
  "bot trigger and the reply is the assistant working alone. Record only operational facts",
  "(state, blockers, queues, outcomes). Output NO preference/intent/instruction facts about any",
  "person; when only such facts appear, output exactly: NONE",
].join("\n");
```

**Cron 觸發的回合沒有人說話**，所以絕不能從中抽出任何「某人偏好 X」的事實。
只記操作性事實（狀態、阻塞、佇列、結果）。

沒有這條規則，一個每天跑的 cron 會日復一日地把
Agent 自己的行為模式寫成「使用者的偏好」。

### 4.4 記憶的行文法：可解析的 markdown

```typescript
export const RECALL_MAX_CHARS = 6_000;

export function isBullet(line: string): boolean {
  const t = line.trimStart();
  return t.startsWith("- ") || t.startsWith("* ");
}

export function captureDate(text: string): string | undefined {
  return /^\((\d{4}-\d\d-\d\d)\)/.exec(text)?.[1];
}

export function normalize(line: string): string {
  return line
    .replace(/^[-*]\s*/, "")
    .replace(/^\(\d{4}-\d\d-\d\d\)\s*/, "")
    .trim()
    .toLowerCase();
}

export function capTail(text: string, maxChars: number): string {
  return text.length > maxChars ? text.slice(text.length - maxChars) : text;
}
```

記憶存成 `MEMORY.md`，格式是 `- (2026-08-07) 某個事實`。

```
① 是 markdown，人可以直接讀、直接編輯
② 有 (YYYY-MM-DD) 前綴，知道何時記下的
③ normalize() 去掉符號、日期、大小寫 → 用來去重
④ capTail 保留「尾巴」   ← ★ 跟前面的 head+tail 不同
```

第 ④ 點的差異值得注意：一般截斷保留頭尾，
但 scratch log 是**時序追加**的，最新的在後面 —— 所以只留尾。
**截斷方向要看資料的語意**。

而 `LOG_RETENTION_DAYS = 14`、`LOG_RECALL_MAX_CHARS = 3_000`：
scratch log 只留兩週，超過就靠 promotion 提煉成長期記憶。

### 4.5 Promotion：重寫整份筆記本

```typescript
export const PROMOTION_PROMPT = [
  "You maintain an agent's long-term memory notebook (MEMORY.md).",
  "You are given the current notebook and a scratch log of recent automatic captures.",
  "Output the COMPLETE new notebook as markdown: keep the existing `# Memory` header style,",
  "keep every still-true long-term fact, and graduate from the scratch log only what proved",
  "durable — stable preferences, identifiers, ongoing projects, how the person likes to work.",
  "Drop one-off trivia, transient task state, and anything stale or contradicted. Drop pure",
  "system mechanics that can be looked up when needed …",
].join("\n");
```

**輸出完整的新筆記本，不是 diff。** 這讓模型可以
「合併兩條重複的、刪掉一條被推翻的、改寫一條過時的」
—— 增量式的 append-only 記憶做不到這些。

`MARKER_RE = /^<!-- captures-since-promote: (\d+) -->$/m` ——
用一個 HTML 註解在 MEMORY.md 裡記「上次 promotion 後累積了幾筆」，
達到 `consolidateAfter` 才觸發。**狀態存在檔案裡，不需要另一張表。**

---

## 五、部署：兩條客製路線

### 5.1 路線一：部署目錄（不需要 checkout）

```bash
npm exec --yes --package=@yc-software/qm@latest -- \
  qm init . --org <slug> --target <fly-or-aws>
npm install
```

```
your-org-qm-deployment/
├── package.json          → 依賴 @yc-software/qm
└── deploy/layers/<org>/
    ├── config/           → org 設定、soul、命令政策、核准的 harness
    ├── sandbox/          → 沙箱鏡像層（額外的 CLI 與工具）
    ├── skills/           → 組織自訂 skill
    ├── plugins/          → plugin 鏡像
    └── infra/            → Terraform / Fly 設定
```

**core 是 npm 依賴，升級就是 `npm update`。**

`qm init` 還會產生一份「部署 skill」給 Agent，帶著操作者走完
基礎設施、web 登入、connector 憑證、Slack 存取、部署與驗證。
**用 Agent 來部署 Agent 平台** —— 這是很自然的 dogfooding。

README 也明確說：

> Initialization **does not generate or enable deployment CI**, and this repository has
> no production deployment workflow.

不預設幫你開 CI —— 那是操作者的決定，不該由 init 腳本代勞。

### 5.2 路線二：私有 fork（整包程式碼在自己手上）

```bash
gh repo create <org>/qm-private --private

git clone --bare git@github.com:yc-software/qm qm-seed.git
git -C qm-seed.git push --mirror git@github.com:<org>/qm-private
rm -rf qm-seed.git

git clone git@github.com:<org>/qm-private
git -C qm-private remote add upstream git@github.com:yc-software/qm
```

規則在 `AGENTS.md` 裡列了五條：

```
① 不要改 core（`deploy/layers/<org>/` 以外的一切都是 core）
② 組織專屬檔案全部放 `deploy/layers/<org>/`
③ 用 `update-qm` skill 同步上游 —— merge，永不 rebase
④ 每個 gh 指令都要帶 --repo
   （否則 gh 可能透過 upstream remote 選到上游 repo，讀錯或改錯 PR）
⑤ ★ 絕不在 fork 的 PR / issue / commit message 裡用編號引用上游
   （`yc-software/qm#123`）
```

第 ⑤ 條的理由值得完整引用：

> GitHub mirrors such mentions onto the referenced upstream item as a permanent timeline
> event, so the fork's existence and the mentioning title become visible to whoever
> GitHub decides may see them. **Name upstream work in plain words instead.**

**在私有 fork 裡提到 `upstream#123`，會在上游那個 issue 留下永久的
時間軸事件，洩漏「有這個 fork」以及你的 PR 標題。**
這是很少人知道的 GitHub 行為，而它直接關係到私有 fork 的保密性。

而 `AGENTS.md` 開頭那句更關鍵：

> **Before you act, determine which repository this checkout is by running `git remote -v`.**

**先確認自己在哪個 repo，再動手。** 在一個「上游與 fork 共用同一份
AGENTS.md」的世界裡，規則本身必須先做環境偵測。

### 5.3 兩條路線的取捨

| | 部署目錄 | 私有 fork |
|---|---|---|
| core 的形式 | npm 依賴 | 完整原始碼 |
| 升級 | `npm update` | `update-qm` skill 做 merge |
| 工程師能讀 core 嗎 | 要去看 node_modules / GitHub | ✓ 同一個 repo |
| 客製範圍 | 只有 `deploy/layers/` | 理論上全部，但規則要求只改 `deploy/layers/` |
| CI | 自己建 | ★ 繼承上游的 workflow，會在你的帳號跑 |
| 適合 | 大多數組織 | 要讓 coding agent 同時讀 core 與客製的組織 |

README 對第二條路線的代價講得很白：

> it costs one thing: the clone is an ordinary repository, so upstream's CI workflows
> run live in your own account. Expect to supply the secrets those workflows need,
> or disable the ones you do not want running.

---

## 六、為什麼選 X 不選 Y

| 決策 | 選 X 的理由 | 不選 Y 的理由 | 反轉條件 |
|---|---|---|---|
| **持久沙箱**<br>vs 每次任務開新容器 | 裝過的工具還在、登入過的服務還登著；skill 可以說「先 pip install」 | 每次冷啟動 = 每次任務前三分鐘在裝環境 | 極端的隔離需求，或 scope 數量巨大時 |
| **叫 AgentComputer 不叫 Container** | 命名塑造心智模型：「一台電腦」會讓人想到持久性與規格 | Container 暗示可拋棄 | 沒有 |
| **`notInstalled` 是規格的一部分** | 明說「沒有 X」比讓模型撞一次 command not found 省一輪 | 只列有什麼 = 模型會一直試不存在的工具 | 工具清單非常長時 |
| **`capabilitiesLostMovingTo`** | 遷移不是靜默降級，是一份明確的損失清單 | 只說「已切換」= 三個月後才發現防護沒了 | 沒有 |
| **type guard 檢查宣告 + 五個方法** | 宣告與實作不一致時以實作為準，不在執行時炸 | 只信 profile 旗標 = 一個沒實作完的後端會在半夜掛掉 | 沒有 |
| **skill 物化成沙箱檔案**<br>vs `load_skill` 工具 | 重用「Agent 會讀檔案」的既有能力，不需要新工具與新心智模型 | 額外工具要教模型何時用、參數怎麼填 | 需要精確控制 skill 何時進 context 時 |
| **skill 有簽章** | body 會進 system context，等於 Agent 的指令 —— 竄改要能偵測 | 無簽章時無法區分「作者改的」與「被改的」 | 儲存層本身已不可變時 |
| **cron 三層去重**<br>（lease + queue + idempotency） | 多實例 blue-green 部署下，單進程的 `Set` 完全無效 | 少一層就會在部署當下重複觸發 | 單實例部署 |
| **`Intl.DateTimeFormat` 當時區驗證器** | Node 內建 ICU 就是最新的 IANA 權威來源 | 自維護清單會過時（時區規則每年變） | 沒有 |
| **收件人同意** | 多人平台裡「叫 Agent 每天煩某人」是真實的濫用途徑 | 沒有同意 = 排程變成騷擾工具 | 單人使用 |
| **抽取 prompt 有 PROVENANCE 規則** | 從 Agent 自己的回覆推導偏好 = 一次幻覺永久污染 | 沒有這條，記憶會慢慢長出從沒人說過的「偏好」 | 沒有 |
| **promotion 輸出完整筆記本**<br>vs diff | 能合併重複、刪除被推翻的、改寫過時的 | append-only 記憶只會膨脹與自相矛盾 | 記憶量大到重寫成本過高時 |
| **scratch log 只留尾**<br>vs 頭尾都留 | 時序追加的資料，最新的最有價值 | 留頭 = 保留兩週前的、丟掉昨天的 | 資料不是時序追加時 |
| **部署目錄 + 私有 fork 雙路線** | 兩種組織的需求真的不同（升級簡單 vs 程式碼在手） | 只給一條會逼一半的人做錯誤的取捨 | 沒有 |
| **禁止用編號引用上游** | GitHub 會把 mention 鏡射成上游的永久時間軸事件 | 一次引用就洩漏 fork 的存在與 PR 標題 | 沒有 |

---

## 七、系列總結：十個可以帶回自己專案的設計

**多租戶與權限**

1. **多租戶的鍵要是一等公民**：一個 `"kind:ref"` 字串貫穿記憶、檔案、
   憑證、排程、ACL 七個子系統。
2. **共享場景用最小公分母**：`.every()` 不是 `.some()`；
   allowed 取交集、denied 取聯集。
3. **政策合成只能收緊**：org 是 floor 不是 default，
   posture 與命令政策都遵守同一條規則。
4. **授權要表現成使用者已懂的形式**：`shared/q3-plan.md`、
   `skills/<name>/SKILL.md` —— 重用「會讀檔案」這個能力，不發明新工具。

**抽象與邊界**

5. **抽象要誠實表達差異**：`HarnessAdapterProfile` 讓
   「這個引擎不支援 thinking-level」成為可查詢的事實。
6. **把不可信元件的所有出口變成注入的 callback**：
   harness 拿不到儲存、政策、身分，就繞不過它們。
7. **對「會擴大 Agent 未來權限」的動作劃硬線**，
   並在文件裡註記「這是牆，不是缺口，別修」。

**可靠性與誠實**

8. **多實例下沒有「進程內狀態」這種東西**：
   cron 三層去重、session 租約、durable by default。
9. **降低誤報跟提高偵測一樣重要**：誤報多了人就盲按批准，
   整道閘門的價值歸零。
10. **公開列出已知限制**：12 條限制 + 「命令政策是減速帶不是邊界」
    的自我定位，讓部署方能做真正的風險評估。

---

## 八、系列導航

- [Part 1：多人協作 Agent 平台的架構全景](/yennj12_blog_V4/posts/qm-multiplayer-agent-part1-architecture-zh/)
- [Part 2：Scope 與 Resolution — 一次對話如何解析出身分、權限與工作區](/yennj12_blog_V4/posts/qm-multiplayer-agent-part2-scope-resolution-zh/)
- [Part 3：Harness 抽象 — 一套核心驅動四種 Agent 引擎](/yennj12_blog_V4/posts/qm-multiplayer-agent-part3-harness-abstraction-zh/)
- [Part 4：安全模型 — 三種 Posture、命令政策與誠實的威脅模型](/yennj12_blog_V4/posts/qm-multiplayer-agent-part4-security-model-zh/)
- **Part 5（本篇）：Sandbox、Skills、Cron 與部署 — 讓 Agent 擁有一台持久的電腦**

---

## 參考資料

- [yc-software/qm](https://github.com/yc-software/qm) — 本系列分析的主體（MIT License）
- [`SECURITY.md`](https://github.com/yc-software/qm/blob/main/SECURITY.md) — 威脅模型與 12 條已知限制
- [`AGENTS.md`](https://github.com/yc-software/qm/blob/main/AGENTS.md) — 工程規範與私有 fork 規則
- [`docs/getting-started.md`](https://github.com/yc-software/qm/blob/main/docs/getting-started.md) — 第一次啟動
- [`cli/README.md`](https://github.com/yc-software/qm/blob/main/cli/README.md) — `qm` CLI 與部署目錄契約

> 本系列分析基於 2026-08 的 `main` 分支（commit `0f0e0ad`）。專案是早期實驗性軟體，
> 程式碼細節可能已變動；引用的行號與函式名以你當下 clone 的版本為準。
> 最好的讀法是自己 `git clone` 一份，邊讀本文邊跳到對應檔案。
