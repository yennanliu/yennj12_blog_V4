# Content audit — October 2026

A full editorial review of every post on the blog (362 posts as of 2026-10-03) against the three
project skills — `tech-blog-writer`, `finance-blog-writer` and `blog-reviewer` — plus a review of
`CLAUDE.md` and the tooling that enforces it. The goal is a prioritised, evidence-backed list of
what to improve, why, and how.

**Status: complete (2026-10-15).** Every post was reviewed in one of 27 sequential batches;
`docs/content-audit/PROGRESS.md` lists them and each batch's full per-post scorecard, verified
claims and file-level recommendations are in `docs/content-audit/batches/`.

---

## 1. Executive summary

**All 362 posts reviewed in full.** Verdicts:
**83 Ready (23 %) · 159 Needs revision (44 %) · 120 Not ready (33 %).** The site's problem is not
writing quality — clarity and visuals score 4–5 in most batches — it is **trust**: numbers that
look sourced are not, code that looks runnable is not, and product facts that look current are
not. Every "Not ready" verdict traces to one of those three.

What the audit found, in order of how much it matters:

1. **Code a reader would copy does not run.** Across the CDK projects (14/14 Not ready), the Java
   and Spring posts (12/14), the six English backend "comprehensive guides" (6/6 — non-existent
   `sql.Config`, a per-request `setDataSource` on a singleton `JdbcTemplate`, a Stripe webhook
   cast that rejects every real payload), the LangGraph cluster (6/6), both MCP tutorials, the crypto trading
   bot, the consultant agent series and a dozen single posts, reviewers found invented SDK
   constructs and props, non-existent property keys and CLI flags, wrong imports, missing
   imports, async methods called synchronously, and configs whose comment says the opposite of
   what the YAML does. The posts present these as production patterns. This is the single
   largest source of blockers and the easiest to prevent mechanically (compile or run every
   fence before publishing — §7, item 1).
2. **Numbers are invented, hedged once, then used as data.** The interview-prep format's
   「系統效應」 before/after tables and the 三個演進階段 cost ladders are filled with round
   percentages that no experiment produced. The better posts label them 示意估算 once, in a
   footnote, and then the body says 實測 / 實際測試 / 我們跑了 / 生產環境 3 個月平均 (B09, B10, B13,
   B19). Eleven of the thirteen late fde-interview parts state the same cost two or three ways
   and disagree with themselves (B04). The 10-K series (B11) and the semiconductor map (B14) show
   the alternative works: every figure traced, labelled or derived in front of the reader.
3. **Product facts are stated from memory and go stale in place.** Verified-wrong facts a
   reader would act on: Cloud Run GPUs, KMS pricing and quotas ×10–100, Pub/Sub ack deadline,
   AutoAWQ bit-width, Claude Code features that do not exist (a "Bash Agent", zero-token skills,
   `/agent`), `docker scan`, `kubectl get componentstatuses`, Titan Text Express fine-tuning,
   Timestream after closure, Gemini-vs-Gemma. The pattern is "good 2026 patch next to a 2023
   sentence": someone corrected one line and left the surrounding stale content.
4. **The interview-prep format was applied where it does not fit.** The curriculum
   (ai-eng-from-scratch, 43 posts) was generated with an interviewer question, a POC/MVP/Scale
   ladder with user-count thresholds, six decision tables and a 系統效應 table per post; reviewers
   found the phase section teaches only where scale is actually the axis (~6 of 43 posts) and
   that the manufactured decision rows carry invented flip thresholds readers will quote. This
   PR scopes the format to interview posts (§4.1); the content still needs the scaffolding
   removed.
5. **Duplication without links.** The same topic exists two to four times (fde-interview ↔
   fde-core-concept twins; four multi-agent orchestration posts; thirteen RAG posts; six
   LangGraph posts; two Kubernetes series; three creative streaming series sharing templates)
   with zero cross-links among them. Every batch report names the canonical version per topic.
6. **Identity and navigation.** The About page and author bio are the theme's placeholder copy;
   the Series menu pointed at the wrong tag (fixed); 1,067 tags with 713 singletons; the
   kubernetes-autoscaling series' 70 cross-links are written as `./slug.md` and 404 in
   production (B20) — a form neither checker catches.

What is good and should be protected: the 10-K deep dives (12/14 Ready, all 28 spot-checked
figures match the filings), the semiconductor industry map (12/15 Ready), the ollama-on-mac,
vllm-intro, ragflow-intro and mem0 source-reading series, the QM and OpenWorker showcase series,
the Cloudflare security-audit trilogy, ai-system-on-native-aws's prose, and aio-geo's sourcing
discipline. These are the house style the writer skills should be pointed at as exemplars.

The prioritised plan is in §7. The first four items are mechanical guards that stop the three
trust failures from recurring; everything after is content work, ordered by reader harm.
---

## 2. Method

- **Mechanical pass** — `scripts/review_posts.py` on all posts (front matter, closed category
  set, author slugs, fences, images, series rules) and `scripts/check_links.py --strict`, plus a
  per-post statistics pass (lines, diagrams, links, readTime, description length, language).
  Output: `docs/content-audit/inputs/mechanical-baseline.txt`.
- **Editorial pass** — every post read in full by a reviewer applying the `blog-reviewer`
  rubric: thesis stated in one sentence; Accuracy / Clarity / Depth / Visuals / Structure /
  Format scored 1–5 (finance posts weight Accuracy ×2); the 3–5 claims a reader would act on
  checked by recomputation, internal consistency or a primary source; one top finding per post
  with a line number; then batch-level patterns under six headings. Posts are grouped into
  27 batches by series (`docs/content-audit/inputs/batches.txt`) and reviewed one batch at a
  time so that each report is committed before the next starts.
- **Verdicts** follow the rubric: **Ready** ≥ 4.0 with no blocker; **Needs revision** 3.0–3.9 or
  any major finding; **Not ready** < 3.0 or any blocker (factual error, invented data, broken
  code a reader would copy, missing finance disclaimer).
- **Config pass** — `CLAUDE.md`, the three skills, `scripts/review_posts.py`, the archetype,
  `hugo.toml`, workflows and supporting docs checked for scope errors, contradictions and
  stale statements (§4).

Limits: external facts about fast-moving products were verified where a reviewer could reach a
primary source; otherwise they are marked ❓ unverified rather than wrong. Scores are one
editor's judgement and are most useful relative to each other.

---

## 3. Site-wide numbers (2026-10-03)

| measure | value | why it matters |
|---|---|---|
| posts | 362 (306 zh-TW, 56 en) | the site is a Traditional-Chinese blog with an English shell (`languageCode = en-us`, team-voice About page) |
| publish dates | 2024-12 → 2026-09; 134 posts dated June 2026 | a third of the archive landed in one month, i.e. generated in bulk to a template |
| posts with no diagram (ASCII or Mermaid) | 101 | the tech skill's "2–4 diagrams that carry information" is unmet by 28 % of posts |
| posts with zero external links | 262 (72 %) | almost no post cites a source; every number is on the author's word |
| posts with zero internal links | 99 | series and related posts don't reinforce each other |
| descriptions > 160 chars | 92 | SEO snippet and card text truncated |
| readTime off by > 50 % vs. ~32 lines/min | 26 | five posts under 200 lines claim 12–13 min |
| mechanical warnings (after this PR's checker change) | 208, 0 errors | 42 decision-table + 40 phase-section + 38 line-count (was 55) + 29 Google-in-interview-post + 28 leftover 面試答題要點 + 16 over the 十 cap + 5 fewer than 2 diagrams + 5 finance posts without a disclaimer + 2 readTime drift + 1 placeholder text + 1 H1 in body + 1 over-long description = 208 |
| unique tags / used once | 1,067 / 713 (67 %) | the tag cloud that the "Series" menu points at is unusable at this size; `繁體中文` is a tag on 70 posts |
| category spread | engineering 277 · ai 223 · finance 41 · infrastructure 36 · architecture 32 · business 28 · tools 19 · creative 9 | `engineering` on 77 % of posts is not a filter |

---

## 4. CLAUDE.md, skills and tooling review

This section is final. Items marked **[fixed in this PR]** are already changed; the rest are
recommendations with the reasoning.

### 4.1 The interview-prep format had leaked into everything — [fixed in this PR]

**What.** `CLAUDE.md`'s fde-interview-guide section defines a house format for interview answers:
「三個演進階段」 (POC → MVP → Scale with user-count thresholds), 4–6 「為什麼選 X 不選 Y」 decision
tables with flip conditions, 600–900 lines, ten numbered sections. Three places then extended it
beyond interview prep:

| where | what it said | effect |
|---|---|---|
| `CLAUDE.md` ai-eng-from-scratch section | "Otherwise the fde-interview-guide formatting conventions above still apply: … 「三個演進階段」, 4–6 「為什麼選 X 不選 Y」 … 600–900 lines" | a teaching curriculum graded as interview answers |
| `AI_ENG_FROM_SCRATCH_PLAN.md` §Standard Post Structure | section 二 = 三個演進階段, section 八 = 為什麼選 X 不選 Y, checklist "4–6 Why-X-not-Y decisions", "600–900 lines", "No mention of Google" | same, plus a no-Google rule CLAUDE.md says is interview-only |
| `tech-blog-writer` skill, "Post structure" step 4 | every standalone post gets a 「為什麼選 X 不選 Y」 / "Why X over Y" table | the format recommended for all tech posts |
| `scripts/review_posts.py` `check_series` | `house_rules(600, 900)` applied to ai-eng-from-scratch | 42 decision-table + 40 phase-section + most of the 55 line-count warnings were against the curriculum |

**Evidence that it hurt.** 「為什麼選」 appears in 80 posts outside the two series and
「三個演進階段」 in 20 (ai-system-on-native-aws, aio-geo, ai-ocean-space, adhd-focus,
cloudflare-security-audit, auto-agent-system, anthropic-financial-services…). The
tooling/Anthropic batch found the 10K / 200K / 1M-user phase thresholds transplanted onto a
GL-reconciliation product intro with no basis (`anthropic-financial-services-intro-part3`
L35/51/72) and a 系統效應 "before/after numbers" table with no numbers. Where a post has a real
scale cliff the phases work; where it does not, they generate three near-identical diagrams
and a decision table whose rows are filler.

**Fix applied.** CLAUDE.md now states the two devices are the interview-prep house format only
(`fde-interview-guide-*`, `fde-core-concept-*`); the ai-eng-from-scratch section and the plan
file make them optional ("only when the topic has a scale cliff / a real alternative; never to
hit a count") and replace the 600–900 floor with "length follows the lesson (~400–900)"; the
writer skill's step 4 asks for the alternative, why it lost and the flip condition in whatever
form fits; and `review_posts.py` applies the phase / decision-table / line-floor checks to
`fde-interview-guide` only (diagrams, the 十 cap and the leftover-面試答題要點 check still apply
to both series). Warnings: 219 → 208; none of the removed ones were about reader-facing quality.

**Not changed, needs a decision.** The 55 fde-interview parts written before the format (parts
1–26, 283–486 lines, no phases, no tables) are still flagged. Backfilling them to the format is
a content decision, not a lint fix — see the B01/B02 batch reports for whether the format would
add value per post.

### 4.2 The "no Google" rule was enforced on a narrower set than it claims — [fixed in this PR]

CLAUDE.md says the rule covers `fde-interview-guide-*` "and other interview-prep series".
`fde-core-concept-1…25` are tagged `RKK` + `Interview` + `fde-core-topic`, i.e. interview prep,
and six of them mention Google (parts 3, 5, 9, 12, 17, 22) — but the checker only looked at the
`fde-interview-guide` prefix. The checker now keys on the file prefix **or** the `Interview`
tag, and CLAUDE.md names `fde-core-concept-*` explicitly. 23 fde-interview-guide posts also
still mention Google (warnings only).

Open question: the rule matches the string "google" but the tag `Vertex AI` appears on 17
interview posts. Decide whether the rule is about the brand name only (current behaviour) or
about vendor neutrality (then `Vertex AI`, `GCP`, `BigQuery` need the same treatment).
`ai-fde-essential-guide` parts 1 and 3 mention Google and carry an `FDE` tag but not
`Interview`; they are "cheatsheet" posts — tag them `Interview` if they are prep material.

### 4.3 Stale or wrong statements in CLAUDE.md — [fixed in this PR]

| statement | reality | fix |
|---|---|---|
| "`.github/workflows/` — Three Hugo build/deploy workflows" | five workflows; only `hugo-latest.yml` deploys on push; `hugo.yml` and `deploy-alternative.yml` are `workflow_dispatch` only; `link-check.yml` and `post-review.yml` run on PRs | reworded |
| "Hugo exits 1 on the known `paginate` deprecation — verify via `public/`" | on Hugo 0.164 the build exits 0 and `paginate = 25` is **silently ignored** (categories/all paginates at 10 locally, 37 pages) while CI on 0.124.1 honours 25; the only deprecation warning is `languageCode` → `locale` | reworded to describe the actual local-vs-CI pagination difference |
| "Most existing posts only set `summary`, which is why the fallback matters" | all 362 posts set `description` (the checker requires it); 69 also set `summary` | reworded |
| `archetypes/default.md` | emitted `summary:`, `draft: true`, `categories: [""]`, `authors: [""]` — a `hugo new` post failed `review_posts.py` on three counts | archetype now matches the required front matter |

### 4.4 Navigation and taxonomy

- **Series menu pointed at the wrong series — [fixed in this PR].** `hugo.toml`'s "AI
  Engineering · From zero to production AI systems" entry linked `/tags/ai-engineering/`, which
  is the `AI Engineering` tag: 25 posts from ai-system-on-native-aws, auto-agent-system,
  ollama-on-mac, langfuse and anthropic-financial-services, and **zero** ai-eng-from-scratch
  posts (they use the `ai-eng-from-scratch` tag, 43 posts). Now points at the series tag.
- **"FDE Interview Guide" → `/tags/fde/`** mixes the 52 interview parts with
  ai-fde-essential-guide (5) and career-ops-guide. Recommend a dedicated `fde-interview-guide`
  tag on the 52 parts and pointing the menu at it.
- **Tag sprawl.** 1,067 tags, 713 used once. `繁體中文` is a tag on 70 posts although language is
  encoded in the filename; zh and en variants of the same concept coexist (`半導體` /
  `Semiconductor`, `美股` / `investing`). Recommend: a curated set of ~60 tags, series tags that
  match the Series menu, and a one-off normalisation script (the `tags/list.html` template
  already orders by `weight`, so series order is preserved).
- **Weight ordering is half-applied.** 221 of 362 posts set `weight`; on a shared tag such as
  `RKK` (120 posts) the weighted series parts sort first and the rest fall back to date, so the
  page reads as two lists. Either weight every series or scope weight-ordered tags to series tags.

### 4.5 Site identity is still the theme's placeholder copy

- `content/authors/yen/_index.md` lists "Current Company (2021-present)", "Previous Tech Co
  (2018-2021)", "Startup Inc (2016-2018)" — the theme's sample CV, rendered on every post's
  author card.
- `content/about/_index.md` (dated 2024-08-10) speaks as "our internal engineering team", gives
  `engineering-blog@yennj12.com`, invites readers to "the comments section" (there is none), and
  lists topics the blog does not write about (engineering culture, post-mortems, team scaling)
  while omitting what it actually is: interview prep, an AI-engineering curriculum, 10-K digests,
  GEO/SEO, creative streaming.
- `hugo.toml`: `author = 'YennJ12 Engineering Team'`, `languageCode = 'en-us'`, description
  "Engineering insights, architecture deep dives, and technical solutions" — for a site that is
  85 % Traditional Chinese and 40 % non-engineering.

Recommend: a one-paragraph About in zh-TW and en that names the five series, a real author
bio, `locale = 'zh-TW'` (and the Open Graph locale to match), and a site description that
mentions finance and AI.

### 4.6 Supporting docs and workflows

- `docs/NVIDIA_BLOG_AUTOMATION.md` and `docs/NVIDIA_SETUP_QUICK_START.md` (502 lines) document a
  daily workflow that was removed because its output was fabricated; `scripts/generate_nvidia_blog.py`
  remains. Recommend moving both docs and the script to an `archive/` folder or deleting them, and
  shortening the CLAUDE.md note to one line.
- `README.md` and `DEPLOYMENT_GUIDE.md` still describe `hugo.yml` as the main workflow with Hugo
  0.121.1 and claim `hugo-latest.yml` uses `peaceiris/actions-hugo` (it downloads the tarball).
  CI actually pins 0.124.1 in `hugo-latest.yml` / `link-check.yml` and 0.121.1 in the two manual
  workflows. Recommend one pinned version everywhere, stated once in README, and deleting the
  two manual deploy workflows (they duplicate `hugo-latest.yml` with an older Hugo).
- `hugo.toml` should migrate `paginate = 25` → `[pagination] pagerSize = 25` and `languageCode`
  → `locale` **together with** bumping CI to a Hugo that understands them (≥ 0.128); until then
  local preview paginates differently from production.
- `readTime` calibration disagrees with itself: CLAUDE.md's fde rule (500 ≈ 18, 700 ≈ 23,
  900 ≈ 28 min ⇒ 28–32 lines/min), the tech skill ("~32 lines/min: 500 lines ≈ 18 min" — 500/32
  is 15.6) and the checker (32 lines/min, ±2× tolerance). Pick one formula and have the checker
  warn at ±50 %.
- 10-K length rule: CLAUDE.md says 450–600 lines, the checker warns outside 400–700. Say so in
  CLAUDE.md or tighten the checker.

### 4.7 Blog-reviewer in CI

`post-review.yml` runs the skill only when `ANTHROPIC_API_KEY` is set and is advisory. Two
improvements once the backlog in this audit is worked down: promote the house-style warnings to
errors for **new** posts (`--strict --changed-from origin/main`), and have the reviewer's
output include the per-post score table so the PR history becomes a quality time series.

---

## 5. Cross-cutting findings

Each finding names the batch reports that evidence it; the line-level detail is in those reports.

### 5.1 Content quality

- **Thesis is the dividing line.** Posts that open with a claim (ollama, vllm, ragflow, mem0, QM,
  OpenWorker, Cloudflare, 10-K, semiconductor, ai-system-on-native-aws) score 4+ on structure and
  depth; posts that open with "This comprehensive guide explores…" / "本文將深入探討…" (all 14 CDK
  projects, 12 of 14 Java posts, the docker/k8s complete guides, rag-series, the AWS quartet) have
  no argument to be wrong about and stay at feature lists. (B22, B23, B20, B15, DONE-k8s)
- **Generation templates are visible to the reader.** Two CDK families share intro, section
  order, closing and hashtag line to the hour of their `date`; the docker and k8s guides share
  their 前言, FAQ table, checklist and 🎉 結語; the three creative series share Discord trees,
  OBS settings and sponsor emails verbatim; the fde-core series ends every post with a "Killer
  Phrase" block that is the banned model answer renamed. (B22, DONE-k8s, DONE-creative, B05, B06)
- **Register slips.** Simplified-Chinese vocabulary in 繁體 posts (k8s p2), English posts with
  CJK (springdataplatform-flink), motivational closers ("祝您…不斷進步！🚀"), emoji on every H2 in
  the older English posts. (DONE-k8s, B23, B22)
- **Where the writing is excellent**: the 弱答/強答 contrast paragraphs in fde-core (B05), the
  cost-shape argument that builds across ai-system-on-native-aws (B21), ollama-on-mac's decision
  tables with real flip conditions (B17), the 10-K bridge tables (B11).

### 5.2 Structure and the house format

- **The interview format earns its place in roughly a quarter of the posts that carry it.**
  三個演進階段 teaches where the subject is a system being scaled (fde-interview 2, 4, 15, 21, 23,
  24, 39; ai-eng 4-1, 5-1, 5-2, 6-1, 10-2, 11-1, 13-1, 14-4) and pads or self-contradicts
  elsewhere (taxonomy, protocol, threat-model and fundamentals posts; the GL-reconciliation
  product intro with 10K/200K/1M-user thresholds). (B01–B04, B07–B10, DONE-tooling)
- **Decision tables are good when the comparison already existed and bad when manufactured.**
  Reviewers recommend converting existing comparisons to the 3-column shape with a 翻轉條件 row
  (B01, B02) and deleting rows whose flip condition has no mechanism (B08, B09, B19 found ~30 %
  of rows with "反轉條件: 沒有"; B03 found a 為什麼選 section that is 60 % verbatim restatement).
- **The 工程情境 / 面試情境 interviewer question survives in every ai-eng post** (53/53 incl.
  phase 1–5) although the series is not interview prep; 18-1 literally says 「這道題考的不是…」.
  (B07–B10)
- **Model answers survive under other headings** (完整範例回答, CTA script, Killer Phrase,
  快速複習卡) that the checker does not see; 28 posts still carry the literal heading. (B02, B05)
- **Sections past 十** in 16 posts are almost always the banned model answer plus 延伸問題; cap by
  deleting, not renumbering. (B04)
- **Series navigation** is plain text where links exist (Anthropic trilogy, synthwave 1–3),
  points at "Part N" topics never written (8 fde-core posts), says "8K" for a 4K post (ocean),
  and in kubernetes-autoscaling is written as `./slug.md` (70 links, all 404). (DONE-tooling,
  DONE-creative, B05, B20)

### 5.3 Depth and numbers

- **One number, three values.** The same quantity appears in the Phase section, the 系統效應
  table and the model answer from three drafts and disagrees in 11/13 late fde-interview parts,
  8/13 of parts 14–26, and 4+ ai-eng posts (B04, B02, B10). Cross-post drift too: Flash-vs-Pro
  saving is 40× / 80 % / 5× across three posts; cold start 10–30 s / 8–12 s / 8–15 s (B03);
  mem0 benchmarks differ between parts (B16); 15-2 and 18-1 give different jailbreak baselines
  for the same architecture (B10).
- **示意 in the footnote, 實測 in the body.** Nine of twelve ai-eng 15–19 tables are labelled
  示意估算 while the prose says 實測 / 我們跑了 / 生產環境 3 個月平均; aio-geo Part 14 tells
  consultants to quote Part 9's invented case to clients; HF3/HF5 label the same kind of table
  實測 that HF4 labels 示意. (B10, B13, B16, B09)
- **Arithmetic that does not survive recomputation** in posts whose point is the number: both
  stock DCF base cases (PL $17 → ~$8; AVAV $115 → ~$106), ROI headcount in fde-29, Little's law
  in fde-39, KV-cache bytes/token in ai-eng 11-1 (and GQA ignored), 1 TB-as-1 T-characters in
  10-1, Firestore cost off by 10⁴ in fde-core-11, cost tables 2× high in ai-system-aws P3/P8
  and 2–4× off in three CDK posts, GOOGL's net debt issuance stated two ways. (B12, B03, B09,
  B08, B05, B21, B22, B11)
- **Zero cost figures where the reader most wants one**: six LLM-tooling posts with no $/report
  or $/month; "complete guides" with no pricing or limits; backtests with no results. (DONE-tooling,
  B20, B12)
- **Where numbers are done right**: 10-K (every derived figure labelled 計算值 and recomputable),
  semiconductor (every share bar set sums to 100; weak only on citation), vllm (KV bytes/token
  derived in front of the reader), 16-2 (MoA numbers sourced to the paper), fde-core-14
  (tail-latency maths recomputes). (B11, B14, B15, B10, B06)

### 5.4 Direction: overlap, gaps, fit

- **Twins and clusters** (canonical version in brackets, per the batch reports): fde-interview
  40–52 ↔ fde-core 1–25 [core for 1, 7, 10, 13, 14, 15, 17, 18, 19, 21, 23, 24, 25; fold core-6
  into 7]; four multi-agent posts + ai-eng 16-1 + fde-16 [pt.1 overview, pt.5 context, pt.6
  specialization, fde-16 state, ai-eng 16-1 topologies]; thirteen RAG posts [ragflow-4,
  fde-core-4/5/20, ai-eng 11-2]; six LangGraph posts [collapse to two; fde-core-3 owns the
  concept]; two Kubernetes series [autoscaling series owns scaling; complete-guide p3 links];
  three creative series [one shared infrastructure post]; Flash Attention / 3D parallelism /
  BF16 / DPO explained in five ai-eng posts; ai-fde-essential-guide 1–5 [retire; every topic has
  a better fde-core post]; google-gemini-local-mac and harness-engineering [retire; superseded].
  (B04–B06, B18, B15, B17, DONE-k8s, DONE-creative, B08)
- **Gaps readers would expect**: a "how a 10-K deep dive is produced" post linking the series,
  InvestSkill and finance_data (none link each other); a real post-mortem with actual YouTube
  Studio data for the streaming series; AI-music copyright / Content ID; one measured token-usage
  run for the multi-agent cluster; backtest results for the crypto series; a platform-limits /
  price card the interview series can cite instead of restating (five posts quote four different
  KMS prices). (DONE-tooling, DONE-creative, B18, B12, B05, B03)
- **Category fit**: sec-edgar-toolkit and investskill are tools posts carrying `finance`;
  springdataplatform-flink is zh in an English-named file; synth-p4 lacks `business`;
  `engineering` on 77 % of posts is not a filter. (DONE-tooling, B23, DONE-creative, §3)
- **Stale topic pins**: `--v 6.1` / Gen-3 Alpha prompts, LangChain pre-1.0 imports, Spring
  Boot 2 property keys, 2023 chart versions beside 2026 notes, `claude-3-*` pricing, "0.19.x"
  four months behind the post date. (DONE-creative, B15, B23, B20, B18)

### 5.5 Accuracy

The blockers by class, with counts from the batch reports:

| class | examples | batches |
|---|---|---|
| Code that cannot run or deploy | invented CDK constructs/props/methods (≥ 8), backend guides' `sql.Config` / `JdbcTemplate.setDataSource` per request / `LinkedHashMap`→`PaymentIntent` cast / invalid PromQL (B24), `AWS::Bedrock` L1s that do not exist (2), MCP `InitializeResult`, `ThreadPoolTaskExecutor` as `ExecutorService`, `Counter.increment(Tags)` ×14, `GRPOTrainer(reward_weights)`, `langgraph.graph import interrupt`, `invoke()` dict read as attributes (6 posts), discord.py without intents, Bitnami env vars on official postgres, crypto bot's five neutralised safeguards | B22, B21, B18, B23, DONE-k8s, B16, B19, B17, DONE-creative, B12 |
| Config whose comment says the opposite | CA priority expander inverted, NetworkPolicy OR-vs-AND, SELinux `:z`/`:Z` swapped, `rate()` on gauges, HPA on replication lag, `allUsers` org-wide log viewer as "audit" | B20, DONE-k8s, B03 |
| Verified-wrong product facts | Cloud Run T4, KMS price/quota, Pub/Sub ack ceiling, AutoAWQ INT8, cache TTL max, Claude Code "Bash Agent"/`/agent`/zero-token skills, Titan Express fine-tuning, Timestream, Gemma as Gemini, `docker scan`, `componentstatuses`, Patreon/Brain.fm/Gumroad prices, r/outrun size | B05, B06, B04, B18, B17, B22, DONE-k8s, DONE-creative |
| Misdescribed mechanism | RRF k "weights a modality", non-format-preserving FPE, HIPAA localisation, KEK/DEK conflation, KV cache "cuts first-token latency", NFC vs NFKC, entropy threshold unreachable with top-5 logprobs, `OptimisticLockException` caught inside the transaction, saga log rolled back by its own `@Transactional`, quorum vs majority in Sentinel, "Dual-LLM" that is not privilege-separated | B05, B08, B04, B23, DONE-k8s, B02 |
| Invented research, incidents or company data | "RLHF sycophancy 12 % → 34 %", "2026 production incident $120K", Gartner forecast as citation example, real YouTube channels with invented stats, SpringPlayground "95 % adoption / $49K savings", NYC-taxi benchmarks hard-coded in code | B10, B13, DONE-creative, B23, B22 |
| Health/science claims in publishable templates | "40 Hz binaural beats proven for ADHD", "reduce cortisol by 25 %" | DONE-creative |
| Finance-rule failures | unreproducible DCFs, FY26 growth +12 % vs +26 %, redeemed warrants treated as overhang, crypto series with no disclaimer, selling-strategy disclaimer at L997, unsourced semiconductor shares (stale by 5–10 pts) | B12, B14 |

Verified correct and worth noting: all 28 10-K headline figures; the semiconductor headline
figures (HBM share, WFE, EUV prices, capex); mem0 v3 defaults; vLLM flags and metrics; RAGFlow
v0.27; Ollama CLI/API surface; Karpenter v1 / EKS Auto Mode / in-place resize; EU AI Act
timeline; OTel GenAI attributes; MoA numbers; Anthropic crawler UAs; Cloudflare 15 Sept 2026
change; YPP thresholds; Suno/Midjourney/Runway pricing. (B11, B14, B16, B15, B17, B20, B10, B13,
DONE-creative)

### 5.6 Format and front matter

- `description` describes the topic, not the payoff, in most series; 92 exceed 160 chars (8 of
  14 10-K posts, 5 of 6 tooling posts). `summary` duplicates `description` in the older posts.
- `readTime` is understated ~2× on long posts (adhd 39 vs ~78 min; redis 29 vs ~55) and overstated
  on short ones (five 150–190-line posts at 12–13 min); three calibration formulas disagree (§4.6).
- Fake "**標籤**: #…" hashtag lines and emoji H2s in the 2025 English posts; `$$` formulas render
  raw because KaTeX is not loaded (ai-accuracy); ASCII blocks > 80 cols wrap on mobile (9 in the
  10-K series); three 10-K bar charts are non-proportional.
- The "no Google" rule is cosmetic as enforced: it catches "Google Workspace" but not a section
  built on Vertex/GCP, and parts 31–33 are GCP product posts by title. Needs the decision in §4.2.
- Both mechanical warnings in B19 and several in B01 are false positives (a section heading that
  contains the banned phrase in prose); worth tightening the checker's heading match.
---

## 6. Batch reports

| batch | posts | Ready / Needs revision / Not ready | report |
|---|---|---|---|
| DONE-k8s-docker-redis-mkdocs | 9 | 1 / 5 / 3 | `docs/content-audit/batches/DONE-k8s-docker-redis-mkdocs.md` |
| DONE-creative-streaming | 9 | 0 / 4 / 5 | `docs/content-audit/batches/DONE-creative-streaming.md` |
| DONE-tooling-anthropic | 6 | 0 / 4 / 2 | `docs/content-audit/batches/DONE-tooling-anthropic.md` |
| B01-fde-interview-01-13 | 13 | 5 / 7 / 1 | `docs/content-audit/batches/B01-fde-interview-01-13.md` |
| B02-fde-interview-14-26 | 13 | 1 / 12 / 0 | `docs/content-audit/batches/B02-fde-interview-14-26.md` |
| B03-fde-interview-27-39 | 13 | 1 / 9 / 3 | `docs/content-audit/batches/B03-fde-interview-27-39.md` |
| B04-fde-interview-40-52 | 13 | 0 / 7 / 6 | `docs/content-audit/batches/B04-fde-interview-40-52.md` |
| B05-fde-core-01-13 | 13 | 0 / 6 / 7 | `docs/content-audit/batches/B05-fde-core-01-13.md` |
| B06-fde-core-14-25-fde-essential-career | 18 | 3 / 6 / 9 | `docs/content-audit/batches/B06-fde-core-14-25-fde-essential-career.md` |
| B07-ai-eng-phase-01-05 | 11 | 3 / 7 / 1 | `docs/content-audit/batches/B07-ai-eng-phase-01-05.md` |
| B08-ai-eng-phase-06-10 | 10 | 0 / 6 / 4 | `docs/content-audit/batches/B08-ai-eng-phase-06-10.md` |
| B09-ai-eng-phase-11-14 | 10 | 0 / 8 / 2 | `docs/content-audit/batches/B09-ai-eng-phase-11-14.md` |
| B10-ai-eng-phase-15-19 | 12 | 0 / 7 / 5 | `docs/content-audit/batches/B10-ai-eng-phase-15-19.md` |
| B11-10k-deep-dives | 14 | 12 / 2 / 0 | `docs/content-audit/batches/B11-10k-deep-dives.md` |
| B12-stock-crypto-selling | 10 | 0 / 5 / 5 | `docs/content-audit/batches/B12-stock-crypto-selling.md` |
| B13-aio-geo | 16 | 8 / 8 / 0 | `docs/content-audit/batches/B13-aio-geo.md` |
| B14-industry-map-semiconductor | 15 | 12 / 3 / 0 | `docs/content-audit/batches/B14-industry-map-semiconductor.md` |
| B15-rag-vllm-ragflow-chatpdf | 18 | 10 / 8 / 0 | `docs/content-audit/batches/B15-rag-vllm-ragflow-chatpdf.md` |
| B16-mem0-kg-hf-eval-singles | 21 | 6 / 10 / 5 | `docs/content-audit/batches/B16-mem0-kg-hf-eval-singles.md` |
| B17-ollama-langfuse-crewai-langgraph | 23 | 4 / 7 / 12 | `docs/content-audit/batches/B17-ollama-langfuse-crewai-langgraph.md` |
| B18-claude-code-mcp-orchestration | 16 | 2 / 8 / 6 | `docs/content-audit/batches/B18-claude-code-mcp-orchestration.md` |
| B19-agent-showcase-series | 20 | 13 / 7 / 0 | `docs/content-audit/batches/B19-agent-showcase-series.md` |
| B20-k8s-autoscaling-aws-guides | 12 | 0 / 5 / 7 | `docs/content-audit/batches/B20-k8s-autoscaling-aws-guides.md` |
| B21-ai-system-on-native-aws | 10 | 2 / 4 / 4 | `docs/content-audit/batches/B21-ai-system-on-native-aws.md` |
| B22-aws-cdk-projects | 14 | 0 / 0 / 14 | `docs/content-audit/batches/B22-aws-cdk-projects.md` |
| B23-java-spring | 14 | 0 / 2 / 12 | `docs/content-audit/batches/B23-java-spring.md` |
| B24-backend-misc | 9 | 0 / 2 / 7 | `docs/content-audit/batches/B24-backend-misc.md` |
| **Total** | **362** | **83 / 159 / 120** | |


---

## 7. Prioritised improvement plan

Ordered by reader harm prevented per hour of work. Items 1–4 are guards that stop the three
trust failures from recurring and should land before any content is rewritten; items 5–9 are
content fixes in harm order; items 10–14 are structure and direction.

| # | action | why | how |
|---|---|---|---|
| 1 | **Compile or run every code fence before publish** | the largest blocker class (≥ 40 posts); invented SDK APIs, wrong imports, async-called-sync | `scripts/check_snippets.py`: extract ```python / ```typescript / ```java fences tagged `# run`, `py_compile` / `tsc --noEmit` against pinned `aws-cdk-lib` / `mcp` / `langgraph`, `promtool check rules` for alert YAML; wire into `post-review.yml` advisory, then gate for new posts; writer-skill rule "snippet ≤ 25 lines, executed, or marked `# 示意，未執行`" |
| 2 | **Label every number at point of use** | 示意 footnotes lose to 實測 bodies; 11/13 posts disagree with themselves | three-glyph convention in both writer skills (📎 sourced + link · ∑ computed from stated inputs, formula kept beside the result · ≈ illustrative); `review_posts.py` warns on `實測|實際測試|我們跑了|生產環境.*平均` without a source line, and on the same `$`/`ms`/`%` label with ≥ 2 distinct values in one file |
| 3 | **Date-stamp product facts and verify against docs at publish** | "good 2026 patch beside a 2023 sentence"; eight invented Claude Code surfaces; stale prices | a "驗證於 <product> vX.Y, YYYY-MM" line under the front matter for any post tagged with a fast-moving product; reviewer skill WebFetches the vendor page for 3–5 claims; a `docs/platform-limits.md` price/limit card (KMS, Pub/Sub, Spanner, Bedrock, Claude pricing) that interview and ai-eng posts cite instead of restating |
| 4 | **Fix the link-shape gap** | 70 `./slug.md` links 404 in production and pass both checkers | `check_links.py --content-only` fails on `](./` and `.md)` targets; one perl pass on the 8 kubernetes-autoscaling files (B20 gives the command) |
| 5 | **Fix the paste-with-consequences blockers** (one PR per batch, ~1 day total) | readers are harmed on first use | B03 (org-wide `allUsers` log viewer, broken TLS), DONE-creative (health claims in publishable templates), B12 (crypto bot safeguards; add disclaimers), DONE-k8s (NetworkPolicy, Bitnami vars, SELinux, Sentinel quorum, Spring Boot 3 keys), B20 (five "opposite of the comment" configs), B21/B22 (deploy-breaking CDK), B18 (MCP servers that cannot start) — each report's Top findings table is the checklist |
| 6 | **Fix the wrong facts and arithmetic in the series readers trust most** | fde-core and fde-interview are the site's interview product; 10-K is its finance product | B05/B06 nine+seven blockers (KMS, Cloud Run, AutoAWQ, FPE, HIPAA, KEK/DEK…); B04 "one number, one place" rewrite of 43–52; B11 GOOGL's four mismatches, ORCL multiples, five unit slips; B12 re-derive both DCFs with a printed 10-year table |
| 7 | **Strip interview scaffolding from the curriculum** | 53/53 ai-eng posts still open with an interviewer question; phase ladders contradict bodies in ~10 posts | delete 工程情境 blocks series-wide; keep 三個演進階段 only in the ~8 posts where scale is the axis (lists in B07–B10); cut decision tables to 3–4 rows with real alternatives; one labelling rule for all 系統效應 tables; update the plan's stale ⬜ inventory |
| 8 | **Retire or collapse the posts that cannot be salvaged** | they drag the quality floor and rank for the same queries as better posts | ai-fde-essential-guide 1–5 → one 300-line skill map; four SpringPlayground showcases → rebuild from the READMEs or retire; LangGraph six → two; google-gemini-local-mac, harness-engineering, orchestration-agents (EN) → retire; rag-series 1/3/4 → on-ramp pointing at canon; creative streaming → one shared infra post + trimmed series |
| 9 | **Rebuild the 14 CDK posts and the AWS quartet around one deployed run each** | 14/14 and 4/4 Not ready; the promise is "cdk deploy and it works" | compile (item 1), fix the five deploy-breaking mechanisms, derive and date every cost table (unit price × qty × 730 h, NAT, Multi-AZ), replace "Illustrative, Not Measured" tables with one real `cdk deploy` + CloudWatch screenshot or delete them; give each post a thesis sentence or merge into ai-system-on-native-aws |
| 10 | **Cross-link every twin and cluster; name the canonical** | zero links among 13 RAG posts, 6 LangGraph posts, 4 multi-agent posts, 25 fde-core/interview twins | a 相關文章 block per post from the canonical map in §5.4; reduce the interview twin of each fde-core post to 面試情境 + phases + link; "how these fit together" paragraph linking 10-K ↔ InvestSkill ↔ finance_data |
| 11 | **Decide the "no Google" rule once** | cosmetic as enforced; parts 31–33 are GCP product posts; 17 posts tag Vertex AI | either brand-name only (keep the grep, fix P2/P9/P11, exempt product nouns) or vendor-neutral (extend checker to Vertex/GCP/Gemini/BigQuery, rewrite as 「雲端廠商的託管服務」); record in CLAUDE.md §6; count all occurrences, not the first |
| 12 | **Retire model answers in all disguises; cap at 十 by deleting** | 28 literal + ~10 disguised headings; sections past 十 are the model answer | extend the checker to 範例回答 / 最想聽到 / Killer Phrase / 快速複習卡; replace with a 4-bullet 答題骨架 that references section numbers |
| 13 | **Fix identity, taxonomy and front matter in one sweep** | placeholder About/bio; 713 singleton tags; 92 long descriptions; readTime ×2 drift | real About (zh + en) naming the five series; author bio; `locale = zh-TW`; curated ~60-tag set + series tags matching the Series menu + a dedicated `fde-interview-guide` tag; one readTime formula in checker and both skills; descriptions rewritten to the payoff (≤ 160 chars); drop pseudo-hashtag lines and duplicate `summary` |
| 14 | **Point the writer skills at exemplars** | the house style exists; the skills describe it abstractly | add to `tech-blog-writer`: "model on ollama-on-mac-2, vllm-intro-3, qm-multiplayer-agent-1, ai-system-on-native-aws-4"; to `finance-blog-writer`: "model on meta-2025-10k-deep-dive-zh, industry-map-semiconductor-part6"; both skills' self-review step runs items 1–3's checks |

Effort guide: items 1–4 are one to two days of tooling; item 5 is one day of targeted edits;
items 6–7 are a week each; items 8–10 are the large content programme (a quarter at one post a
day); items 11–14 are a day each.

Per-batch "Recommendations" sections contain the file-level work orders behind every row above.