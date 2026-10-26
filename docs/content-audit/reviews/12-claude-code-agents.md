## Claude Code, MCP servers, and multi-agent guides (16 singles) — 16 posts

### Series-level observations
- **Posts that describe Claude Code features that don't exist.** Four of the Claude Code posts (`claude-code-architecture-explained-zh`, `claude-code-best-practices-zh`, `everything-claude-code-setup-best-practices`, `building-mcp-servers-…-part1`) document config and APIs that were never real: `~/.config/claude-code/settings.json`, a `claude-code` CLI binary, `@claude/skill-sdk` TypeScript skills, `.claudeignore`, `"enabled"`/`"description"`/`"timeout"` keys in `mcpServers`, a hooks schema of `{"eventType", "script", "toolNames"}`, and `/plugins search`. The real surface is `~/.claude/` and `.claude/`, the `claude` binary, `SKILL.md` folders, `.mcp.json` or `claude mcp add`, `settings.json` → `"hooks": {"PostToolUse": [{"matcher": …, "hooks": [{"type": "command", …}]}]}`, and `/plugin marketplace add` → `/plugin install`. A reader who copies any of this gets nothing that works. This is the biggest problem in the batch: it's a trust issue, not a staleness issue.
- **The Claude Code posts leave out the core features.** Across `best-practices`, `context-window`, `development-workflow` and `architecture` there are almost no mentions of `CLAUDE.md`, plan mode, `/clear`, `/compact`, `/context`, permissions, hooks, headless `claude -p`, or `.claude/agents/*.md` custom subagents. These are exactly what a practitioner needs and what makes a post worth more than generic "write clear prompts" advice.
- **The token-optimization series (pt.1–7) is one long codegen dump, and the pieces overlap.** Six parts are 92–93% code. Their scaffolding is ~120 `@dataclass`/`Enum`/`*Config`/`*Manager` classes (e.g. `SlidingWindowConfig`, `HybridCompressionManager`, `RuleBasedRouter`, `TokenBudget`), with no measured result anywhere. Every "效能比較" table is an assumed-input calculation (pt.5 L1603: `150,000 tok → 25,000 tok`; pt.6 L1357: `16,000 → 2,500`). The overlaps are concrete:
  - pt.6 策略三「模型差異化選擇」(L781) re-implements pt.4's tiering table with the same three model IDs and prices.
  - pt.7 re-derives pt.5's context passing ("只傳遞必要的摘要") and re-covers Hub-and-Spoke/Pipeline, which `orchestration-agents-claude-code-comprehensive-guide.md` already covers in English.
  - pt.1 策略六 (batching/parallelism) never gets its own part.
  
  **Recommendation: merge seven posts into four.**
  1. pt.1 as the hub, rewritten with correct numbers.
  2. Caching (pt.2, with Layers 2–4 cut to the non-obvious 30 lines).
  3. "What goes into the window" (pt.3 + pt.5).
  4. "Designing the agent team" (pt.4 + pt.6 + pt.7).
  
  Keep each code sample to the one mechanism it teaches.
- **The series disagrees with itself on model IDs, and the prices are stale.** The parts are dated two hours apart on the same day, yet:
  - pt.1–3 use `claude-sonnet-4-6` and `claude-haiku-4-5-20251001`.
  - pt.4–7 use `claude-3-5-haiku-20241022` (retired, so the API calls fail), and `claude-sonnet-4-20250514` / `claude-opus-4-20250514` (deprecated).
  
  pt.4's whole argument rests on "Opus $15/$75 vs Haiku $0.80" (L29–31, "18.75x", "節省 91%"). Current Opus is $5/$25 (Opus 5.5: $4/$20) and Haiku 4.5 is $1/$5, so the spread is about 5x, not 18.75x, and the conclusion changes. Current guidance is also to try the stronger model at lower `effort` before building a routing cascade, since routing loses the prompt cache across models. None of the posts mention `effort`, the 1M context window, server-side compaction (`compact-2026-01-12`), or context editing (`clear_tool_uses`). pt.3's hand-rolled summarizers now compete with a built-in feature they never mention.
- **The series savings double-count each other.** pt.1 says caching makes the fixed prefix cost 0.1x. pt.6 then claims 84% savings on that same fixed prefix, priced at the uncached $3/MTok. pt.1's summary table ranks five savings percentages as if they stacked. If they are ever merged, one worked example should apply caching first and then show what specialization still saves.
- **Descriptions.** Twelve posts lack `description` but do have a real `summary`, and `head.html` falls back to it. So this is low impact: copying `summary` into `description` is a two-minute batch fix, not an SEO emergency.
- **Missing series navigation.**
  - The token series only cites pt.1 by an old unlinked title (《多 Agent 系統的 Token 用量調優指南》) and has no series nav at all.
  - The four 2026-01-17 Claude Code zh posts cross-link only from `best-practices` (延伸閱讀).
  - The MCP series promises a Part 3 that was never written.

### Per-post

#### `agent-specialization-multi-agent-guide-zh.md`
**Verdict:** rewrite/merge
- Merge into a single "designing the agent team" post with pt.4 and pt.7. 策略三 (L781–959) duplicates pt.4's `ModelTier`/`MODEL_CONFIGS` wholesale.
- `MODEL_CONFIGS` hard-codes `claude-3-5-haiku-20241022` (retired), `claude-sonnet-4-20250514` and `claude-opus-4-20250514` (deprecated), plus the $0.80/$15/$75 prices. All of it is wrong today.
- The L1357 comparison ("16,000 tok vs 2,500 tok, 84%") is priced without caching, which pt.1 of the same series told readers to enable first. Show the savings after caching, or drop the table.
- Of 策略一–四 (L229–1356), roughly 1,100 lines are class scaffolding. The actual teaching point, a 2.5K-token prompt plus a 3-tool allowlist per role, fits in ~40 lines of prose and one example.
- Add series nav, and fix the intro reference to pt.1 (L12) so it's a real link.

#### `building-advanced-mcp-servers-claude-code-part2.md`
**Verdict:** restructure
- The intro promises "Real-time Processing: WebSocket connections" (L21, and in the diagram at L34/44). None is implemented; it only reappears in the "Part 3 Preview" (L2028), and Part 3 doesn't exist. Either cut the promise or cut the Part 3 teaser.
- The SQL guard (L285–299) is a `startswith('select')` check plus a substring denylist, yet the closing examples encourage "Query the user table in our **production** database" (L2003). For a post titled "production", recommend a read-only DB role or a read-only transaction instead of string filtering. Right now it teaches an unsafe pattern.
- `advanced_config.json` (L1853+) ships a literal `"password": "mcp_password"`. Use env-var references, and say why.
- 2,045 lines with no ASCII/prose explanation between blocks. The Docker, monitoring, and API-tester sections (L817–1611) are generic Python that isn't MCP-specific; cut them to the MCP-relevant parts: tool schema, result shape, error surfacing.
- The transport and SDK are dated. It's stdio-only with a low-level `Server` API, and there's no mention of Streamable HTTP or `FastMCP`. Verify against the current MCP spec revision.
- readTime says 24 min for about 57 minutes of material.

#### `building-mcp-servers-claude-code-development-part1.md`
**Verdict:** rewrite/merge
- It gets the protocol's name wrong: "**Model Control Protocol (MCP)**" (L16, also in `summary`). The correct name is Model Context Protocol, and that error alone undermines the post.
- The Claude Code wiring is wrong. The `mcpServers` block is shown in "Claude Code Settings (settings.json)" (L551) with invented keys (`description`, `enabled`, `timeout`, `cwd`), and "you should see your MCP server listed in the status bar" (L589) isn't how it works. The correct approach is `claude mcp add …` or a project `.mcp.json`, then `/mcp` to verify.
- Parts are stale: `protocolVersion="2024-11-05"` is hard-coded (L405, L943); the Python prerequisite is "3.8+" while the MCP SDK needs 3.10+ (verify); and it uses the low-level `Server` API where `FastMCP` is the idiomatic Python path now.
- "Part 3: Production deployment…" (L31) was never written.
- Consider merging parts 1 and 2 into one corrected ~600-line post: the minimal `FastMCP` server, `claude mcp add`, one real tool (read-only SQL), and the security notes.
- Remove the trailing "🏷️ Tags & Categories" section (L1109), which duplicates the front matter.

#### `claude-code-architecture-explained-zh.md`
**Verdict:** rewrite/merge
- The core model of the post is wrong.
  - It presents Plugin as "基於 MCP 協議構建的…MCP Server 的應用商店版本" (L431) sitting at L2 below Skill/Sub-agent. In Claude Code, a plugin is the **packaging/distribution unit**: it bundles commands, agents, skills, hooks and MCP servers, and is installed from a marketplace.
  - The layer table (L52–57: L4=Skill, L3=Sub-agent) also contradicts the section headings (L3 Skill, L4 Sub-agent).
- The skill material is invented.
  - The "內建 Skills" `/test`, `/build` and `/deploy` (L723–764) are not built in.
  - The custom-skill example uses a fictional `@claude/skill-sdk`, `~/.config/claude-code/skills/*.ts`, and `claude-code skill add` (L770, L842).
  - Real skills are `.claude/skills/<name>/SKILL.md` folders with YAML front matter, and the model invokes them by description. This is the most-copied section and it can't work.
- The MCP config path `~/.config/claude-code/settings.json` (L281) is wrong. Several referenced servers (`@modelcontextprotocol/server-mongodb`, and `server-github`, now archived in favour of GitHub's own server) should be verified.
- Custom subagents (`.claude/agents/*.md` with `tools:`/`model:` front matter) are never mentioned, and neither are hooks or `CLAUDE.md`. Those are the pieces an "architecture" post actually needs.
- The token comparison (L1382–1410: "15,000 vs 1,100 tokens, 93%") compares a main instance that reads every file against a subagent that greps. The main instance can grep too. The real benefit, keeping the subagent's reading out of the parent's context, is never stated.
- Worth keeping the idea: one diagram showing how MCP, skills, subagents, hooks, and plugins as packaging fit together is valuable. Rebuild it from the current docs.

#### `claude-code-best-practices-zh.md`
**Verdict:** restructure
- The 20 tips never mention `CLAUDE.md`, which is the single highest-leverage Claude Code practice. They also skip plan mode, `/clear`, permission allowlists, and hooks. Add those and cut the generic ones (#6 file structure, #7 naming, #20 documentation), which apply to any tool.
- Fictional features:
  - Tip #8 `.claudeignore` (L371) isn't a Claude Code feature; use `permissions.deny` in `.claude/settings.json`.
  - Tip #13's TypeScript skill (L641–713) uses the same invented `~/.config/claude-code/skills/*.ts` API as the architecture post.
  - Tip #14's VS Code keys `claude.autoSave` and `claude.contextFiles` (L719–728) don't exist, and there's a typo ".claueignore".
- "效率提升：5 倍以上" (L36) is unsourced. Frame it as an illustration.
- The 下一步行動 checklist (L1320s) tells readers to "建立 .claudeignore 檔案" and "建立常用 Skills" using the broken method. Fix it together with the tips.

#### `claude-code-context-window-deep-dive-zh.md`
**Verdict:** restructure
- The specs table (L80–84) is stale and partly wrong:
  - It says 200K for all models; current models have 1M, except Haiku 4.5 at 200K.
  - Its output limits of 8,192/16,384 were never right for Sonnet 4.5 or Opus 4.5.
  - It lists "Claude Haiku 3.5" (retired).
- The "自動摘要機制" block (L234–270) presents invented internals as fact: triggering at 85%, "保留最近 10 輪". The "Token usage: 45230/200000" readout (L610) is also not what the CLI shows. Replace both with the real controls: `/context` to inspect, `/compact [instructions]`, `/clear`, and auto-compact.
- The post never names `/compact` or `/clear`, which are the whole practical answer to its title.
- The strategies worth keeping are 策略 2 (selective reads) and 策略 5 (subagents to isolate context), plus the 案例 section. Tighten the post around them.
- There's overlap with the token series pt.3; consider linking to it rather than re-explaining token math (L49–75 duplicates pt.1 L20–35).

#### `claude-code-development-workflow-zh.md`
**Verdict:** restructure
- This is a generic SDLC template: requirements doc, deploy checklist, and "5 大原則" that apply to any team. There is almost nothing specific to Claude Code (no `CLAUDE.md`, plan mode, `claude -p` in CI, worktrees, `gh` PR flow, or hooks for lint/test). The only tool-specific detail is TodoWrite (L622). Rebuild each phase around the Claude Code feature that helps with it, or retire the post in favour of the best-practices post.
- Conversation transcripts are fenced as ```typescript (e.g. L601). Use `text`.
- About 2,000 lines, with the full 購物車 requirements/plan documents inlined (L175–540). Keep one short excerpt, not the whole documents.
- It shares the 無流程 vs 有流程 framing with best-practices (L14–40 there). Pick one post to own it.

#### `context-compression-summarization-guide-zh.md`
**Verdict:** rewrite/merge
- It's stale on the premise: "Claude: 200K tokens 上限" (L48), and "Context 累積的指數成長" is actually linear, as the post's own table shows (L20 vs L45). Most importantly, it never mentions server-side compaction (`compact-2026-01-12`) or context editing (`clear_tool_uses_20250919`). Hand-rolled summarizers are now the fallback, not the default. Open with "use the API's compaction; here is when you still roll your own".
- Five strategies × a full `Config` + `Manager` + `Chatbot` class each (≈19 classes) makes 1,900 lines. Merge with pt.5 into a single "what goes into the window" post, keeping sliding window + progressive summary as the two short code samples, and hierarchical/semantic as prose with a diagram.
- Duplicate `### 核心概念`/`### 完整實作` headings under every strategy produce identical anchors and a template feel. Name them after the mechanism.
- No quality evaluation of summaries is shown, even though "是否有摘要品質驗證機制？" is on the checklist. One concrete eval example would add real value.

#### `everything-claude-code-setup-best-practices.md`
**Verdict:** restructure
- The hooks examples (L216–237, L598–628) use an invented schema (`eventType`, `script`, `toolNames`, `conditions.allTestsPassed`, a standalone `~/.claude/hooks/*.json`). Real hooks live in `settings.json` as `{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "…"}]}]}}`. Check them against the repo you're describing.
- The install commands `/plugins search|install|list` (L248–254) aren't the plugin CLI. The real sequence is `/plugin marketplace add affaan-m/everything-claude-code` followed by `/plugin install <name>@<marketplace>`. Verify against the repo's README.
- "Real-World Success Stories" (L1101+) quotes an unnamed "Frontend Team Lead, Series B Startup" and "Zero security incidents", attributed vaguely to "the repository's discussions". Unless each quote links to a real issue or discussion, remove it. These read as fabricated testimonials.
- The claims "22.3k stars", "Anthropic hackathon winner" and "10+ months" (L13) are dated. Add an "as of <date>" note.
- The "200k token context window… shrink to 70k" point (L331) is worth keeping (MCP tool bloat is real). Update the window size, and mention tool search / `defer_loading` and project-scoped `.mcp.json` as the fix.
- The category is `engineering`, but this is squarely `tools`; drop `engineering`.

#### `model-tiering-cost-optimization-guide-zh.md`
**Verdict:** rewrite/merge
- The pricing premise is wrong (L22–49). Opus 4.x/5 now costs $5/$25 (Opus 5.5 $4/$20), Sonnet 4.6 $3/$15, Sonnet 5 $2/$10, and Haiku 4.5 $1/$5. With the gap shrinking from 18.75x to about 5x, "節省 91%" and "成本降低 50-90%" (L1660) no longer hold. The IDs `claude-3-5-haiku-20241022` (retired) and `claude-opus-4-20250514` (deprecated) in `MODELS` (L147–167) break the code.
- It's missing the modern alternative. Current guidance is to measure the top model at `effort: low/medium` before building a cascade, because a cascade loses cache reuse across models and needs a classifier call. Add that as the first 為什麼選 X 不選 Y decision, with a flip condition such as "very high volume of trivially classifiable traffic".
- The worked example (L46) routes 70% to Haiku and 30% to Sonnet, but the distribution chart right below (L59) says 10% "需要 Opus". Make the two consistent.
- Merge into the agent-team post with pt.6. Keep the rule-based router (≈30 lines) and the escalation-on-quality-check idea; the classifier router, hybrid router and `CostCalculator` classes (L411–1609) can go.
- The `RuleBasedRouter.__init__` references `MODELS` before it's shown in that block. Minor, but the snippets aren't self-contained, even though the post's length implies they are.

#### `multi-agent-token-optimization-claude-code-zh.md`
**Verdict:** light edit
- This is the best part of the series and should be the hub. Its prices ($3/$3.75/$0.30) and model IDs (`claude-sonnet-4-6`) are internally consistent. Update to the current default family (e.g. `claude-sonnet-5` at $2/$10) or state "Sonnet 4.6 pricing" explicitly.
- The caching trade-offs table (L165–172) is stale:
  - "需要 ≥ 1,024 tokens": the minimum is now model-dependent, 512–4096.
  - "預設 5 分鐘": a 1-hour TTL at a 2x write cost exists.
  - "只能快取前綴… 無法自訂": up to 4 breakpoints; auto-caching.
- The title and intro say "使用 Claude Code API" / "Claude Code API". This is the Claude API (Messages), not Claude Code; the `claude-code` tag is similarly misleading across the whole series.
- Add a series nav block linking pt.2–7 (or the merged successors), and make the summary table's "預期節省" explicitly non-additive.

#### `orchestration-agents-claude-code-comprehensive-guide.md`
**Verdict:** restructure
- The title says "with Claude Code", but the body is a plain Anthropic-SDK Python orchestrator. Claude Code appears only in a fictional `claude-code "Orchestrate…"` command (L1123). Either retitle it ("…with the Claude API"), or rebuild it on Claude Code's real mechanisms: `.claude/agents/*.md` subagents, or the Claude Agent SDK.
- `MODEL = "claude-sonnet-4.5"  # or claude-opus-4.5` (L189) is not a valid ID (the dotted form never existed), so the code fails on its first call.
- `crewai` and `langchain` are installed (L135), listed in requirements (L883) and in tags, but never imported. Remove them from all three places.
- The "Execute tasks in parallel" claim (L661, L1142) is backed only by a comment ("can be parallel"). The code has no async or thread pool, so either implement it (≈10 lines with `asyncio.gather`) or drop the claim.
- It overlaps the token series pt.7 (Hub-and-Spoke/Pipeline). Link the two, and let one own the pattern catalogue.

#### `prompt-caching-practical-guide-rag-vector-db-zh.md`
**Verdict:** restructure
- There's a bug in copy-pasteable code: `if self.enable_api_cache and len(system) > 1024:  # 快取需要 > 1024 tokens` (L555) compares **characters** to a token threshold, and the threshold itself is now model-dependent (512–4096). Use `count_tokens`, or just set the marker and verify with `usage.cache_read_input_tokens`.
- It's stale on TTL. The diagram says "5 分鐘自動過期" (L28), with no mention of the 1-hour TTL, the 1.25x/2x write premiums, break-even math, or `cache_read_input_tokens` as the verification signal. Those are the things practitioners get wrong.
- Layers 2–4 (LRU, RAG embedding cache, Redis, L397–1256) are generic caching code unrelated to Claude; the Redis layer stores values with `pickle` (L1131), an unsafe default worth a warning. Cut them to a short "exact-response cache vs prefix cache" comparison. The distinction matters, because a response cache changes semantics (stale answers) while a prompt cache does not.
- The effect table (L1532) lists "應用層 LRU 快取 100%" and "Redis 100%" savings. That's true only on hits; show hit-rate-weighted numbers.
- The heading grep picks up `## 你的能力`/`## 公司資訊` inside code-block prompts (L204, L1339). That's fine to render, but it shows how much of the post is embedded prompt text.

#### `selective-context-passing-multi-agent-guide-zh.md`
**Verdict:** rewrite/merge
- This is the strongest idea in the series. Its dependency map plus the "summary → key_findings → structured_data → full_output" layering (summary, L1680) is genuinely useful, but it's buried in 1,600 lines of `*Output` dataclasses and `if self.output_class == …` chains (≈24 classes). Merge with pt.3 and present the dependency graph as the headline diagram.
- Model IDs `claude-3-5-haiku-20241022` (retired) and `claude-sonnet-4-20250514` (deprecated) are used in the code.
- The benefit table (L1603–1625) is modelled rather than measured. Label it as a model, and apply caching first. Much of the "完整傳遞" cost is a repeated prefix that caching already discounts.
- Structured outputs (`output_config.format` / `strict: true` tools) would replace most of the hand-built output formatter (策略一, L289–563). Mention them.

#### `specialized-agent-orchestration-patterns-zh.md`
**Verdict:** rewrite/merge
- Nine uses of `claude-3-5-haiku-20241022` (retired) and seven of `claude-sonnet-4-20250514` (deprecated). This is the most broken code in the batch.
- It overlaps pt.5 (context passing), pt.6 (roles) and the English orchestration guide (Hub-and-Spoke/Pipeline/Parallel). The coordination-overhead model (L54–132, "確保協調成本小於專責化節省") is the one original contribution; keep it as the closing section of the merged agent-team post.
- A triple-quoted string contains markdown headings (`## 概述 / ## 安裝…`, L275–278), which shows how much of the 1,800 lines is prompt payload rather than explanation.
- "保持 80%+ Token 節省的同時" (closing, L1810) is unsupported. There's no end-to-end run shown.
- It doesn't mention the Claude Agent SDK or Managed Agents multi-agent sessions, which now provide the orchestration this post hand-builds. Add at least a "when to build vs use" note.

#### `spotifymcp2-claude-spotify-mcp-server.md`
**Verdict:** light edit
- A good, focused project write-up with real reader value: a clear tool table, the OAuth refresh story, and a test-coverage section. It's publishable.
- Setup covers only `claude_desktop_config.json` (L179). Add the one-liner for Claude Code (`claude mcp add spotify -- node /path/dist/index.js`), since the rest of this batch targets Claude Code readers.
- It lists 4 categories (`ai`, `engineering`, `tools`, plus `all`); CLAUDE.md asks for 1–3 canonical ones. Drop `engineering`.

### Top 5 highest-impact fixes in this batch
1. **Remove the fabricated Claude Code APIs** (`@claude/skill-sdk`, `~/.config/claude-code/`, the `claude-code` CLI, `.claudeignore`, invented `mcpServers` keys, the `eventType` hooks schema, `/plugins search`) from `claude-code-architecture-explained-zh`, `claude-code-best-practices-zh`, `everything-claude-code-setup-best-practices`, and the MCP part 1. Replace them with the real `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`, `.mcp.json` / `claude mcp add`, and `settings.json` hooks. These are the most-copied snippets, and none of them work.
2. **Fix the model IDs and prices in the token series pt.4–7**, where `claude-3-5-haiku-20241022` is retired, the Sonnet 4 and Opus 4 IDs are deprecated, and Opus is priced at $15/$75. Re-derive pt.4's savings claim at current prices (roughly a 5x spread, not 18.75x) and add the "stronger model at lower effort" baseline. Also fix `claude-sonnet-4.5` in the orchestration guide.
3. **Merge the seven-part token series into four posts** (hub, caching, context-in-the-window, agent-team design). Cut the ~120 scaffolding classes down to one mechanism per sample, apply caching before claiming other savings, and add the missing series nav.
4. **Add the built-in context tools to the context-window and compression posts:** `/context`, `/compact`, `/clear`, the 1M window, API compaction and context editing. Remove the invented auto-summary internals (85% trigger, "保留最近 10 輪").
5. **Fix the MCP series.** Correct "Model Control Protocol", fix the Claude Code wiring, replace the substring SQL guard with a read-only role, and drop the hard-coded password and the promised-but-missing WebSocket content and Part 3. Ideally collapse parts 1–2 into one corrected post.
