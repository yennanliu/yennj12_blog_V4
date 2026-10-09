# Content audit — October 2026

A full editorial review of every post on the blog (362 posts as of 2026-10-03) against the three
project skills — `tech-blog-writer`, `finance-blog-writer` and `blog-reviewer` — plus a review of
`CLAUDE.md` and the tooling that enforces it. The goal is a prioritised, evidence-backed list of
what to improve, why, and how.

**Status: in progress.** Posts are reviewed in sequential batches; `docs/content-audit/PROGRESS.md`
shows which batches are done, and each batch's full scorecard and findings are in
`docs/content-audit/batches/`. Sections 1, 5 and 7 of this document are updated as batches land.

---

## 1. Executive summary

_Filled in as batches complete. See §4 for the config findings that are already final, and
`docs/content-audit/batches/` for finished batch reports._

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
| mechanical warnings (after this PR's checker change) | 208, 0 errors | 55 → 38 line-count, 42 decision-table, 40 phase-section, 28 leftover 面試答題要點, 29 Google-in-interview-post, 16 over the 十 cap, 5 finance posts without a disclaimer |
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

_Updated as batches complete. Each finding cites the batch report that evidences it._

### 5.1 From the batches finished so far

- **Templates generate length, not depth.** Twin scaffolds across series — the docker and
  kubernetes "complete guides" share their intro, closing checklist, FAQ table and six-stage
  learning-path diagram verbatim (DONE-k8s-docker-redis-mkdocs); the three creative streaming
  series share 22 verbatim lines, three Discord server trees and two sponsor-email templates
  (DONE-creative-streaming). "Complete guide" posts of 1,000–1,750 lines are command references
  with no thesis and no "when it breaks" section.
- **Numbers are hedged as 示意 and then used as if real.** Every market section in the creative
  series says "示意估算，非實測數據", then builds 12-month subscriber and revenue projections on
  those numbers; the Anthropic series' 系統效應 tables have one assumed number and two
  qualitative rows.
- **Stale-pin pattern: good 2026 patches on a 2023 base.** Posts were updated with correct
  recent notes (ingress-nginx retirement, VirtioFS, Redis address trap) while adjacent commands
  stayed obsolete (`docker scan`, `kubectl get componentstatuses`, `helm repo add stable`,
  `--v 6.1`, Gen-3 Alpha). Date-stamping each guide's "as of" line is cheaper than re-auditing.
- **Code that will not run as written** appears in posts readers are meant to copy: Bitnami
  env vars on the official postgres image, swapped SELinux `:z`/`:Z`, NetworkPolicy OR-vs-AND,
  Micrometer API misuse, discord.py without intents, a non-existent MoviePy effect, a Quick
  Start whose every command targets a script that no longer exists.
- **Health and science claims in publishable templates** (binaural beats "proven" for ADHD,
  "reduce cortisol by 25 %") with no source — the only blockers of their kind so far.
- **Tooling posts in the wrong category.** `finance-data-sec-edgar-toolkit` and `investskill`
  carry `finance` (and therefore fail the disclaimer and sourced-numbers bar) although they are
  tool intros.

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

_Remaining batches are appended here as they complete (see `docs/content-audit/PROGRESS.md`)._

---

## 7. Prioritised improvement plan

_Drafted after all batches complete; the config items in §4 are already actionable._
