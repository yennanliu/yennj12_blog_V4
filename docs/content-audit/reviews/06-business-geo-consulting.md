## aio-geo 1–16, ai-agent-team-for-consultant 1–5, career-ops-guide, mkdocs perf — 23 posts

### Series-level observations
- **aio-geo: the case studies are presented as real engagements, and later parts cite them as evidence.** Parts 5–10 give named-industry "clients" with exact baselines and month-by-month results (Part 5 §6: "該公司加了這一題之後，6 月有 17% 的 MQL 選了 AI 工具"; Part 6: 2026-02 → 2026-07 results in a post dated 2026-08-02). No part says they are composites or illustrations; `grep` finds no 虛構/化名/綜合/示意 disclaimer in 5–10. The business parts then treat them as data: Part 12 §1 cites "Part 5 案例 A：Perplexity 19%、ChatGPT 2%", and Part 14 §2 says its per-industry ceilings "來自本系列案例". So invented numbers end up as industry benchmarks. This is the most important fix in the batch. Add a one-line "情境為綜合多個專案改寫，數字為量級示意" note to Parts 5–10, and relabel Part 14's ceiling column as [推估] with no reference back to the cases.
- **AI-search traffic numbers in Parts 1–10 have no sources. Parts 11, 12 and 15 do, and that is a real improvement.** Unsourced examples: Part 1 opens with a Search Console table (CTR 8.0% → 3.7%, clicks −39%) that reads like measured data; Part 1 §3 and Part 2 §3/§10 say "85-93% 的候選在 rerank 掛掉"; Part 2 §5.2 says comparison tables get cited "2-3 倍"; Part 1 §7 gives "+30~40%" lifts. Part 1 §7 names "Aggarwal 等人 2024 年的 GEO 論文" but has no link (arXiv 2311.09735). Part 11 introduces a [可驗證]/[單一源]/[推估] labelling scheme; apply it back to Parts 1–2. The Similarweb and SparkToro/Datos figures already listed in Part 11's 資料來源 would support Part 1's opening argument.
- **Strategy (1–5) vs case studies (6–10): little overlap in topic, a lot in lessons.** Each case adds a distinct constraint: multilingual/WAF, SKU data rendering, an 800-word site, a paywall, internal RAG. That earns them their slots. But all five use the same template (情境 → 基線量測 → 決策 → 結果 → 投入分解 → 三個 insight → 清單), and four of them lead with the same lesson, "access layer first": Cloudflare in 5, WAF in 6, Cloudflare Pages in 8, the paywall in 9. The real redundancy is **Part 5, which already contains two case studies** (§6 B2B SaaS, §7 dentist). That duplicates the case block, and at 906 lines it is the longest non-implementation post. The AVS formula and metric set are also defined twice (Part 1 §6.2 and Part 5 §2.1, with slightly different position-weight definitions).
- **Cross-reference drift inside aio-geo.** Part 2 sends CSR/SSR readers to "Part 4 Step 7" (lines 48 and 454), but SSR is Part 4 Step 2 (§3); Step 7 is sitemap. Part 2 line 645 points to "Part 3 第六節" for domain authority, but that material is §5 (實體層); §6 is the priority matrix. Part 4 uses both "Step N" and "§N", which are off by one (Step 6 = §7), so it is easy to cite the wrong one. Pick one scheme. Part 10 ends with "## 八、系列收尾" and "十篇走完", but it is Part 10 of 16.
- **Staleness in aio-geo is mostly about bot names and dates.** The crawler tables in Part 2 §2 and Part 4 §2.1–2.2 (robots.txt, Cloudflare expression, nginx map) list `Claude-Web` as Anthropic's live-fetch agent. Anthropic's documented agents are `ClaudeBot` / `Claude-User` / `Claude-SearchBot`, and `Claude-Web` is legacy. Verify and swap in `Claude-User`. Part 15 §1 says "從 9 月 15 日起" new domains default-block AI crawlers. That date has now passed, so the section needs a past-tense update. Also check the year: Cloudflare's default-block announcement for new domains was on 2025-07-01, while the post places it on 2026-07-01. The linked helpnetsecurity URL is dated 2026, so this may be a real follow-up, but confirm it.
- **ai-agent-team-for-consultant: Claude Code is described inaccurately in every part that uses route A.** Skills are shown as flat `.claude/skills/intake.md` files and "slash command 腳本". Claude Code loads `.claude/skills/<name>/SKILL.md` with front matter, and subagents belong in `.claude/agents/`. `AGENTS.md` is presented as Claude Code's native team file, but Claude Code reads `CLAUDE.md`. The hook in Part 2 §4 echoes `$CLAUDE_TOOL_OUTPUT`, which does not exist (hooks receive JSON on stdin), and it sits inside single quotes anyway. Parts 1–3 navs stop at Part 3, so Parts 4–5 cannot be reached from the start of the series. All five posts use `authors: ["YennJ12 Engineering Team"]`, which matches no slug under `content/authors/` (35 posts site-wide do the same).
- **Is `business` the right category for the consultant series?** Only partly. Part 1 (route choice and role design) and Parts 4–5 (agency scenarios with ROI tables) are defensible. But the series is 60–72% code about agent tooling, and route A is literally Claude Code. `["all", "ai", "tools"]` fits Parts 1–2 better than `business`/`engineering`, and Parts 4–5 could be `["all", "ai", "business"]`. The title also promises a *consultant* team, but Parts 4–5 automate an outsourcing shop's quoting and a marketing agency's content. That is a scope drift the Part 1 intro should admit.

### Per-post

#### `ai-agent-team-for-consultant-part1-strategy-zh.md`
**Verdict:** light edit
- Route B lists "Gemini 1.5/2.0 有超長 context" and route C lists "GPT-4o". Both are stale by Sept 2026; update them or drop the version numbers. "Gemini CLI 成熟度不如 Claude Code（截至 2026 年 Q1）" needs a re-check or should be removed.
- Route A describes Skills as "可重複呼叫的 slash command 腳本" in `skills/*.md` and AGENTS.md as the native mechanism. Correct both to `.claude/skills/<name>/SKILL.md` + `.claude/agents/` + `CLAUDE.md` (see series note).
- "用 LangGraph 建立有向圖（DAG）狀態機": LangGraph graphs can cycle, and loops are a selling point listed a few lines below. Say "狀態圖".
- The series nav lists only Parts 1–3; add 4 and 5. Fix the author slug. The opening has no "why should I care" number (cost per client, hours saved). One concrete figure from Part 4/5 would anchor it.

#### `ai-agent-team-for-consultant-part2-implementation-zh.md`
**Verdict:** restructure
- The intro promises every route will include "4. 關鍵注意事項", but no route has that subsection. As written the post is setup + code; the only real prose is the generic "System Prompt 設計原則" (§ near line 624). It is mostly code, but it is not just code. What it lacks is any explanation of why each route is built the way it is. Add a short "what breaks / what we learned" section per route and cut the LangGraph listing (§3 agents.py, ~100 lines) down to one node plus the routing function.
- **Route B is not Gemini CLI.** It installs `@google/gemini-cli`, then the whole implementation uses the Python `google.generativeai` SDK with `gemini-2.0-flash`. That SDK is deprecated in favour of `google-genai`, and that model is retired/deprecated. Either show Gemini CLI actually driving Workspace (via its extensions/MCP) or rename the route to "Gemini API + Workspace" and move it to `google-genai`.
- Route A, §3–§5: `.claude/skills/intake.md` will not load as a skill; `/skills/intake` is not how a skill is invoked; `$CLAUDE_TOOL_OUTPUT` is not a hook variable; `claude auth login` needs verifying. Anyone copying this will get a silently non-working setup.
- Route C: `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` are the legacy names (now `LANGSMITH_TRACING` / `LANGSMITH_API_KEY`). There are two "### 1. 環境設定" headings; prefix them with the route (A-1, B-1, C-1).
- The category here is `engineering` while the rest of the series is `business`. `tools` fits best (see series note).

#### `ai-agent-team-for-consultant-part3-devops-zh.md`
**Verdict:** light edit
- The content is sound but generic. FastAPI + Dockerfile + K8s manifests + Prometheus (§4.2–4.4) are boilerplate that would fit any service, and they overshoot a 1–10-person consultancy running route A. Cut §4.3/§4.4 to one paragraph plus a link, and spend the space on agent-specific failure signals (judge-score drift, JSON-parse failure rate, cost per consultation).
- §1.4 sets "cost_per_consultation ≤ $0.5" and "品質 ≥ 7/10" with no rationale. State where the thresholds come from, or label them as starting defaults.
- The 總結 "Phase 1/2/3" is Build/Validate/Operate, not an architecture evolution; that is fine since this is not an interview series. The nav is missing Parts 4–5, and the author slug needs fixing.

#### `ai-agent-team-for-consultant-part4-outsourcing-zh.md`
**Verdict:** light edit
- A good concrete scenario, and it honestly labels outcomes "導入後目標" rather than results. Keep that framing.
- It repeats the flat `.claude/skills/*.md` layout (lines 78, 146–336). Fix it to `SKILL.md` directories so this "copy the directory" post actually works.
- The LINE integration imports `linebot.models` (line-bot-sdk v2), which is deprecated; v3 uses `linebot.v3.messaging`. Verify and update.
- The "漏掉需求確認的比率 ~40% → <5%" target has no basis. Either tie it to the Step 7 checklist or drop the number.

#### `ai-agent-team-for-consultant-part5-digital-marketing-zh.md`
**Verdict:** light edit
- The 效益評估 table ("月報製作 2 天 → 5 分鐘", savings of 95–99%) counts generation time only. The analyst agent runs on `mock_data` (FAQ, line 823), and the post's own advice is that everything needs human review. Restate it as "draft time" and add a review-time column, or the numbers read as marketing.
- It is the longest post in the series and the most code-heavy. Step 7 (Streamlit review UI) and Step 6 (scheduling) can be trimmed to the non-obvious parts. The Brand DNA design (Step 2) and the prompt notes (Step 8) are the valuable sections; move them up.
- `claude-sonnet-4-6` is current enough. Keep the model string in one config spot so it is easy to update.

#### `aio-geo-part1-concepts-zh.md`
**Verdict:** light edit
- The opening Search Console table (2024 Q1 vs 2026 Q2) looks like measured data but has no source or site. Label it "示意" or replace it with a sourced industry figure; Part 11 already cites Similarweb and SparkToro/Datos.
- §3 "超過 85% 的候選在這裡出局" and §7's lift table need a source or a [推估] tag. Link the Aggarwal et al. paper that §7 names.
- A strong conceptual opener otherwise. The §2 terminology table and §4 three-paths model are the best framing in the series. §6.2's AVS formula is redefined in Part 5 §2.1; keep it in one place and link to it.

#### `aio-geo-part10-case-internal-rag-zh.md`
**Verdict:** light edit
- The most original post in the series: the "internal RAG is isomorphic to public GEO" framing is something readers will not find elsewhere. Keep it.
- "## 八、系列收尾" / "十篇走完" / "前九篇" date from when the series had 10 parts. Retitle it as a close to the case block, and point to Parts 11–16.
- Categories `["all","ai","engineering","business"]`: this post has no business angle. Drop `business`. The `XXX`/`TODO` flags are quoted document text, not leftover placeholders, so no action is needed there.
- Same case-disclosure note as Parts 5–9 (the 400-person fintech and the n=142 survey).

#### `aio-geo-part11-market-landscape-zh.md`
**Verdict:** light edit
- The best-sourced post in the batch. The [可驗證]/[單一源]/[推估] tagging and the "市場資料多半是賣 GEO 的人寫的" caveat are exactly right.
- Staleness risk: the figures come from 2025 sources ("ChatGPT 每天處理 25 億則 prompt" is a mid-2025 number; the PRNewswire release is 2025-07-15). Put an as-of month next to each figure in §2, and re-check the "Google 仍佔約八成" line.
- §7's timing table ("聽過 GEO ~60%", "台灣專做 GEO 的團隊 數十家", "窗口 12-24 個月") should carry the [推估] tag, as §5's pricing does. The window claim will be judged against the post date, so add "（2026-08 判斷）".

#### `aio-geo-part12-geo-vs-seo-decision-zh.md`
**Verdict:** light edit
- §1 rests on "Google Search Central 在 2026 年的官方說明" but does not link it, and the 資料來源 list only has WordStream/Frase/Similarweb. Link the primary Search Central page, since the whole post argues against it.
- §1 layer 2 uses "Part 5 案例 A：Perplexity 19%、ChatGPT 2%" as evidence (see series note on circular sourcing).
- The 資料來源 section starts with an English "Sources:" line. Drop it or make it Chinese.

#### `aio-geo-part13-consulting-playbook-zh.md`
**Verdict:** keep as is
- A practical playbook. The §6 "自殺條款" KPI section is the high point of the business block.
- One tweak: the §2 conversion rates (~15% vs ~45%) are tagged [推估]. Say what they are estimated from (own pipeline? n?) or make them a range.

#### `aio-geo-part14-industry-playbooks-zh.md`
**Verdict:** light edit
- The §2 cross-industry table (選擇型查詢佔比, 天花板引用率, retainer) is the post's core. Its note says the ceilings "來自本系列案例與同類專案", which are the undisclosed composite cases. Re-tag the whole table as [推估] and explain the reasoning (source-preference × query-type) rather than claiming observed data.
- The ten playbooks follow one ╔══╗ template at 75% code-block ratio. Consider a single comparison table plus 3–4 fully worked playbooks instead of 10 thin ones. Medical/finance already point readers to "建議不接".

#### `aio-geo-part15-tools-stack-zh.md`
**Verdict:** light edit
- §1 opens on a Cloudflare change "從 9 月 15 日起". Today is 2026-09-28, so rewrite it in the past tense and state what actually shipped. Verify the year (see series note), and verify the "Immediate / Reference / Full" content-use tier names against Cloudflare's docs.
- §3 prices (Profound US$499, Peec €89, Otterly US$49) and §4 GitHub star counts are correctly dated "2026-07". With the fast churn it already warns about, add a "last verified" line at the top so readers know to re-check.
- Otherwise a good build-vs-buy analysis. The "API vs 真實瀏覽器" comparison and the GPL-3.0 warning are useful and not in vendor content.

#### `aio-geo-part16-scaling-the-business-zh.md`
**Verdict:** keep as is
- A solid closer. The per-client hours breakdown (17 h/month) and the "增加一個客戶 > 12 小時 → 不要擴張" rule are concrete and useful.
- The "九、六篇商業篇的收斂" summary partly duplicates Part 10's close and Part 1's map. Consider one series-level wrap-up in Part 16 that covers all 16 parts.

#### `aio-geo-part2-how-engines-work-zh.md`
**Verdict:** light edit
- §7 is titled "實測", but the body says "以下是一個可以自己重跑的小實驗設計…數字為示意量級". Retitle it "實驗設計（示意）". The "進 rerank ✔/✘" column cannot be observed for external engines, so either explain how you would infer it or drop it.
- Crawler table §2: replace/verify `Claude-Web` (→ `Claude-User`). The claim "85-93%" (§3, §10) needs a source or a [推估] tag.
- Fix the cross-refs "Part 4 Step 7" (lines 48 and 454; should be Step 2) and "Part 3 第六節" (line 645; should be §5).
- Otherwise it earns its "Checklist 會過期，機制不會" promise: the training-bot vs retrieval-bot split and the eight causes of death are the most practical content in 1–5.

#### `aio-geo-part3-strategies-zh.md`
**Verdict:** light edit
- Rule 9 and §3.4 ("FAQPage：最直接的 GEO schema") and §3.1's HowTo row do not mention that Google limited FAQ rich results to authoritative gov/health sites (2023) and dropped HowTo rich results. Say explicitly that FAQPage is kept for machine-readable Q&A structure, not rich results, because readers will run Rich Results Test (§7 week 1–4 acceptance) and see nothing.
- §8's flip conditions include three "翻轉條件：沒有。" For JSON-LD vs Microdata that is fair. For "先修 Layer 1" it is honest (it is a sequencing question, not a choice). Keep them, but the section would be stronger with one more real trade-off, such as rewrite vs new page at a given coverage-gap level.
- The 90-day roadmap acceptance line "引用率相對基線 +10 個百分點" appears without basis. Tag it [推估].

#### `aio-geo-part4-implementation-zh.md`
**Verdict:** light edit
- The robots.txt, Cloudflare expression and nginx map (lines 68, 131, 177) all allow `Claude-Web`. Update them to the current Anthropic UA set, since this is the copy-paste post.
- At 1,214 lines it is the longest post. Hugo and Next.js are implemented in parallel for JSON-LD (§4.1/§4.2) and Markdown output (§6.2/§6.3). Consider collapsing one stack into `<details>` so the main path reads in ~20 minutes.
- Numbering: "Step N" in headings is §N+1. Downstream posts cite "Part 4 §7 的 geo-audit.py", which works, but Part 2 cites "Step 7" for SSR, which does not. Put the step number and section number side by side in the headings, or drop the Step numbering.

#### `aio-geo-part5-measurement-case-study-zh.md`
**Verdict:** restructure
- Split the roles. §1–§5 + §8–§9 (metrics, prompt set, monitor code, traffic attribution, ROI, pitfalls) are the measurement post. §6 (B2B SaaS six months) and §7 (dentist) are case studies and belong with Parts 6–10, or at least need the same disclosure note. As written, the headline "六個月實戰復盤" is the least substantiated claim in the series. It includes precise outcomes ("AI referral 工作階段 310 → 2,840", "17% 的 MQL") with no sign it is illustrative, and its six months (Jan–Jun 2026) finish only weeks before the post date.
- Verify the model IDs in the monitor code (`gpt-4.1`, `claude-sonnet-5`, `sonar-pro`) and the `web_search_20250305` tool version. Put them in one config block so the 300-line script ages gracefully.
- Engine Variance is defined in §2.2 as "標準差", but case A reports it as the 21pp gap between Perplexity 19% and ChatGPT 2%, which is a range, not a standard deviation (3 engines). Align the definition with the usage.
- The §2.1 AVS formula duplicates Part 1 §6.2 with a different position-weight definition. Keep one canonical version here and have Part 1 link to it.

#### `aio-geo-part6-case-enterprise-site-zh.md`
**Verdict:** light edit
- Internal inconsistency: the opening quote says "技術部分只花了 4 人天。剩下五個月都在處理組織問題", but §4's 投入分解 shows "技術合計 14" 人天 and "實際歷時 6 個月". Pick one.
- Add the case-disclosure note (see series note). The §5.2 per-language gains (+26pp German, +31pp Vietnamese) are especially quotable and so especially need a caveat.
- Good content otherwise. The AWS WAF `CategoryAI` default-Block detail and the Accept-Language redirect trap are practitioner-grade. Verify the `AWSManagedRulesBotControlRuleSet` category name and its default action against current AWS docs.

#### `aio-geo-part7-case-ecommerce-zh.md`
**Verdict:** light edit
- The core insight, "讓資料本身變成內容" / GEO as a data-rendering problem, is strong and distinct from the other cases.
- §5.3 "價格正確率的天花板是 71%，接受它" turns a single (composite) case into a universal rule. Soften it to "在這個案例中…" plus the reasoning (cache lag vs price-change frequency).
- Add the disclosure note. Check that the Next.js/Shopify snippets do not repeat Part 4 §4.2 verbatim; link to it instead.

#### `aio-geo-part8-case-landing-page-zh.md`
**Verdict:** light edit
- The product is named "HookLab" with `https://hooklab.dev/` (line 218), and the post compares it head-to-head with ngrok (a real competitor, line 131). If the case is illustrative, use an obviously fictional domain (`example.dev`) so readers do not treat it as a real product claim, and so no real third party is attached to invented results.
- §3 decision 6 "不做的事" and the finding that llms.txt was "加了（10 分鐘），但沒抱期待" are good, honest details. Keep them.

#### `aio-geo-part9-case-course-platform-zh.md`
**Verdict:** light edit
- The three-layer paywall design (§3) is the most reusable decision framework among the cases, and Part 12/14 rightly point to it.
- The 13 tags include near-duplicates (`付費牆` + `Paywall`) and stack names (`GCP`, `Cloud Run`). Trim them to ~8.
- Decision 1 LLM-generates 1,200 lesson summaries from ASR captions. Add one line on fact-checking or human review for generated pages, since the series' own thesis is "被講錯比不被提到更致命".

#### `career-ops-guide-zh.md`
**Verdict:** rewrite/merge
- **Trust:** "最終成功：Head of Applied AI 角色 @Anthropic" (line ~719) contradicts the intro, which only says the author landed a Head of Applied AI role. Nothing supports the Anthropic claim. Verify it against the santifer/career-ops README or remove it. The same applies to "成功率：22%（18/82）", "個性化簡歷提升 3-5 倍通過率" and "節省 ~400 小時".
- **Verify the whole CLI surface.** `npm install` / `npm run discover` / `npm run evaluate` / `npm run export --format sheets` / `scripts/import_linkedin.py` / `config/profile.yml` look invented. As far as I know the upstream project is driven through Claude Code modes and slash commands. If these commands do not exist, the tutorial half of the post is wrong.
- **Language:** the post is written in mainland Chinese vocabulary, even though it uses traditional characters: 簡歷 (×49), 信息, 軟件/硬件, 磁盤, 網絡, 克隆倉庫, 配置文件, 默認, and 跟踪 (a simplified form). The sample profile uses "+86 / 北京 / 張三". Localise to TW usage (履歷, 資訊, 軟體, 設定檔…).
- No `description` (only `summary`). readTime 40 min is inflated. The generic ✓/✗ bullet lists in 總結 and 最佳實踐 add little. A ~250-line "what it is, how to run it per the README, what I learned using it" post would be worth more than the current 752 lines.

#### `mkdocs-site-size-deploy-perf-tuning-zh.md`
**Verdict:** keep as is
- An excellent first-hand post: real numbers, clear per-change before/after, a proper why-X-not-Y table with flip conditions, and a reusable "找被無限複製的單位成本" takeaway.
- Small clarifications: the final state shows "單次部署 payload 387 MB" vs "建置完成站台 503 MB". Explain the gap in one line. In §6 5a, note that `raw.githubusercontent.com` serves PDFs as a download / `octet-stream` rather than inline, if that matches what readers see. Consider adding `infrastructure` to the categories (CI/CD, GitHub Actions).

### Top 5 highest-impact fixes in this batch
1. **Add case-study disclosure to aio-geo Parts 5–10 and stop citing those cases as evidence** in Parts 12 and 14 (re-tag Part 14 §2's ceilings as [推估]). Right now invented results are presented as real, then reused as benchmarks.
2. **career-ops-guide: verify or remove the "@Anthropic" outcome and the npm CLI commands, and localise the mainland vocabulary.** As published it may state a false fact about a real person and teach commands that do not exist.
3. **Fix the Claude Code mechanics in consultant Parts 1, 2 and 4** (`.claude/skills/<name>/SKILL.md`, `.claude/agents/`, `CLAUDE.md`, a real hook payload). Also make route B actually use Gemini CLI or rename it and move off the deprecated `google.generativeai` / `gemini-2.0-flash`. These are copy-paste tutorials that currently fail without any error.
4. **Source or tag the AI-search numbers in aio-geo Parts 1–2** (opening CTR table, "85-93% rerank 淘汰", "2-3 倍" table lift, "+30~40%"). Link the Aggarwal GEO paper and reuse Part 11's [可驗證]/[推估] labels. Retitle Part 2 §7 from "實測" to an experiment design.
5. **Refresh the time-sensitive aio-geo facts and cross-refs.** Replace `Claude-Web` in the Part 2/4 bot tables and configs, update Part 15 §1's now-past "9 月 15 日" Cloudflare change (and verify its year), and fix Part 2's "Part 4 Step 7" / "Part 3 第六節" links and Part 10's "十篇走完" close. Add Parts 4–5 to the consultant series nav in Parts 1–3.
