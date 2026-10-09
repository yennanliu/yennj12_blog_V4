# DONE-tooling-anthropic — anthropic-financial-services-intro ×3, finance-data ×2, investskill

Reviewed 2026-10-04 (parallel pass). Sources checked: `anthropics/financial-services` README/scripts/plugins/cookbooks; `yennanliu/finance_data` README, workflows, scripts, prompts; `yennanliu/InvestSkill` README, CHANGELOG, `.claude-plugin/`, workflows; code.claude.com plugin/skills docs. 6 posts: 0 Ready / 4 Needs revision / 2 Not ready.

## Per-post scorecard

| file | lines | thesis | A | C | D | V | S | F | Overall | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| anthropic-financial-services-intro-part1-usage-zh.md | 155 | Install the official plugin, core `financial-analysis` first | 4 | 4 | 2 | 3 | 3 | 3 | 3.2 | Needs revision |
| anthropic-financial-services-intro-part2-concepts-zh.md | 198 | One source (`agents/<slug>.md` + skills) serves both Cowork and headless | 3 | 4 | 3 | 4 | 4 | 3 | 3.5 | Needs revision |
| anthropic-financial-services-intro-part3-example-zh.md | 181 | GL Reconciler automates break-finding and stops at sign-off | 3 | 4 | 3 | 3 | 4 | 3 | 3.3 | Needs revision |
| finance-data-ai-pipeline-how-it-works-zh.md | 418 | Cron time as task key + a resilience layer = a zero-human research pipeline | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision |
| finance-data-sec-edgar-toolkit.md (finance ×2) | 209 | EDGAR is the free primary source; finance_data wraps CIK/rate-limit/bulk | 2 | 4 | 2 | 1 | 3 | 3 | 2.4 | Not ready |
| investskill-claude-code-financial-analysis-plugin.md (finance ×2) | 630 | no thesis (brochure) | 3 | 3 | 2 | 1 | 2 | 2 | 2.3 | Not ready |

## Top findings
1. blocker — sec-edgar-toolkit L39–93: every Quick Start command fails against the current repo (`script/download_10k.py -n 10` → actual `scripts/download_10k_edgar.py --years`; naming `{TICKER}_{DATE}_10K.html` → actual `{TICKER}_{YEAR}_10-K.pdf`; "single Python file, one dependency" L30 → repo is the full platform with playwright). Fix: date-stamp as "repo at Feb 2026" and link the pipeline post, or rewrite for the current scripts.
2. major — investskill L278–288, L394–420: "Configuration" and "Architecture" describe paths and files that do not exist (`~/.claude/skills/us-stock-analysis/` → plugins live under `~/.claude/plugins/`; `marketplace.json` at root → `.claude-plugin/marketplace.json`; four named workflows none of which exist; SKILL.md frontmatter `title`/`version` → only `description`/`name`).
3. major — part2 L81 "9 個命名 Agent" contradicts its own list at L84–87 (10) and the repo (10 directories); L182 also says 10.
4. major — part3 L72–93, L139–143: the three-phase section presents the author's imagined architecture (per-currency subagents, confidence-based steering) as the plugin's behaviour; the cookbook's subagents are reader / orchestrator / resolver with no confidence thresholds. Mark §二 as a design proposal or rewrite around the real decomposition. L160 deploy omits the required `GL_MCP_URL` / `SUBLEDGER_MCP_URL`.
5. major — pipeline L13 "42 個機器人" vs L84 24 + 24 = 48; never reconciled (live workflow: 61 cron entries, 35 tickers). L135 default `gemini-2.5-flash` stale (live default `gemini-3.8-flash`); add an as-of date.
6. major — zero cost figures across six posts about LLM tooling (no US$/report, US$/month, token count).
7. minor — part1 L60 promises Managed Agents "留到後續系列再細講"; never delivered. Series nav in all three parts is plain text although all slugs exist.
8. minor — 5 of 6 descriptions exceed 160 chars (toolkit 275, investskill 306); 4 of 6 readTimes off ≥50 %; English pair uses emoji headers and duplicate `summary`+`description`.
9. minor — pipeline L7 tags `RAG` although there is no retrieval step.

## Patterns
- **Direction — the two finance_data posts contradict each other** about the same repo ("single file" vs "42 bots, 10 workflows, 3 providers"); neither links the other. finance_data's prompt taxonomy *is* InvestSkill's skill list, unacknowledged in either post. 15 10-K posts credit `InvestSkill 10k-digest`, but the InvestSkill post barely mentions it and no 10-K post links back — the natural missing post is "how a 10-K deep dive is produced" (docs/10K_DEEP_DIVE_WORKFLOW.md is the source).
- **Structure — house template on a 5-minute product intro.** The Anthropic series applies 三個演進階段 with the 10K/200K/1M-record thresholds (part3 L35/51/72) to reconciliation with no basis; the 系統效應 table (L164–173) has no real numbers. Part 2's Skill-vs-Command table (L94–107) with a flip condition is the exception that shows the format working when content supports it.
- **Category fit**: sec-edgar-toolkit and investskill are tooling posts carrying `finance`; recategorise to `tools`/`engineering` (which also removes the disclaimer requirement they fail).
- **Depth**: investskill L64–246 is six near-identical Purpose/Analyzes/Example blocks (~180 lines) with no real output; L368–386 pseudo-trading-signal filler in a post that disclaims signals.

## Verified / unverified claims (abridged)
✅ part1 L66–78 install commands; L86 `/comps` `/dcf` `/earnings` `/ic-memo`; L132 pitch-agent skills. ❓ L120 "12 連接器" (README says 11, lists 12). ❌ part2 L81 agent count. ✅ L39 sync scripts, L66 `.mcp.json` path, L101 skills without commands, L147 `callable_agents` preview. ✅ part3 L156–157 deploy command (missing env vars); ❌ L80–87 subagent decomposition. ❌ pipeline L13 vs L84; ✅ L89–96 window arithmetic; ❌ L135 default model stale; ❓ L137–143 env block not in workflow. ❌ toolkit L39–93 paths/flags; ✅ L26 SEC 10 req/s. ✅ investskill install commands; ❌ L281, L396, L413–418, L560–564 paths/files; ❓ L427 checksums, L434 automated tests.

## Recommendations
1. Rewrite or date-stamp the sec-edgar-toolkit Quick Start; cross-link the two finance_data posts.
2. Fix the InvestSkill configuration/architecture section against the live repo; cut the brochure sections; recategorise to tools.
3. Label part3's architecture as a proposal, or rewrite it around reader/orchestrator/resolver and add the required env vars.
4. Add one cost figure per post (per report, per month) — the number every reader of a tooling post wants.
5. Link the 10-K series ↔ InvestSkill ↔ finance_data in a short "how these fit together" paragraph in each.
