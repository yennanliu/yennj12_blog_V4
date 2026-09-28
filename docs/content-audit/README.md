# Content audit — September 2026

A review of all 364 posts in `content/posts/` against the standards in `CLAUDE.md`, plus a
qualitative read of each post for correctness, staleness, duplication and structure.
**No post was edited.** This folder is a work list, not a change.

| File | What it is |
|---|---|
| `README.md` | This summary: cross-cutting problems, priorities, and decisions the owner needs to make |
| `per-post-checklist.md` | One row per post with every rule-level problem a script can detect. Generated — do not hand-edit |
| `reviews/NN-*.md` | Qualitative per-post review, one file per batch of related series. Each post gets a verdict and specific, line-referenced fixes; each file ends with its batch's top 5 fixes |

Regenerate the mechanical half at any time (needs PyYAML):

```bash
python3 scripts/audit_content.py            # rewrites docs/content-audit/per-post-checklist.md
                                            # and writes .content-audit/{audit.json,audit.tsv,summary.txt}
```

The qualitative reviews were written by reading each post. Claims marked "verify" in them are
suspected but unconfirmed (usually current vendor limits or API shapes); check before acting.

---

## 1. Verdicts at a glance

| Verdict | Posts | Meaning |
|---|---:|---|
| keep as is | 13 | Nothing worth changing |
| light edit | 205 | Fix specific lines; structure is sound |
| restructure | 102 | Content is worth keeping but sections need reordering, adding or cutting |
| rewrite / merge | 34 | Overlaps another post heavily, or is wrong enough to redo |
| consider retiring | 10 | Wrong, hallucinated or superseded; deleting beats fixing |

Only **78 of 364** posts pass every mechanical check.

| Batch (`reviews/`) | Posts | Headline problem |
|---|---:|---|
| `01` fde-interview-guide 1–26 | 26 | First-person "我在 Google 做 AI 工程，也是面試官" claim; duplicate topic pairs; stale Gemini 1.5 pricing drives headline savings |
| `02` fde-interview-guide 27–52 | 26 | Series nav in 43–52 links to invented slugs and a nonexistent Part 53; several posts rest on a wrong architecture premise (46, 49, 51, 44, 31) |
| `03` ai-eng-from-scratch phases 1–10 | 21 | Nav points to posts/topics that do not exist; interview framing left in; misattributed numbers carry arguments |
| `04` ai-eng-from-scratch phases 11–19 | 22 | 21/22 posts have dead prev/next links; Phase 19 capstone map describes a different curriculum |
| `05` fde-core-concept + ai-fde-essential-guide | 30 | **Raw `<function_calls>`/TodoWrite markup published** at the end of essential-guide parts 3–5; factual errors (Firestore consistency, CMEK) |
| `06` aio-geo, consultant, career-ops | 23 | Invented case-study results presented as real and then cited as evidence; unverified claim about a real person |
| `07` 10-K, stock analysis, finance | 27 | INVESTMENT SIGNAL box duplicates `Conviction` and contradicts the post's own quality score (all 14 10-Ks); trade instructions in verdicts |
| `08` semiconductor industry map | 15 | Overview links to none of its 14 parts; figures lack source/year; Part 8 (memory) framing is stale |
| `09` OSS source-code deep dives | 30 | ╔║╚ boxes written as `###` headings pollute the TOC; inconsistent version/commit pins |
| `10a` HF, Ollama, KG, CrewAI, Langfuse | 22 | Copy-paste code that no longer runs; "實測" numbers with no source |
| `10b` RAG, LangGraph, misc AI | 26 | Two `nvidia-*` posts are hallucinated summaries credited to real NVIDIA authors; six LangGraph posts use dead APIs |
| `11` AI systems on native AWS | 12 | Series nav has no links; retired Claude 3.5 model ID hard-coded; 2025 AWS services missing from decision tables |
| `12` Claude Code, MCP, agent guides | 16 | Fabricated Claude Code APIs/paths (`@claude/skill-sdk`, `.claudeignore`, …); retired model IDs and prices |
| `13` infra, AWS, K8s, Docker | 33 | Autoscaling hands-on does not run (CDK v1, Karpenter v1beta1); "Real-World Performance" blocks are unsourced; security bugs in "production" CDK |
| `14` Java / backend | 26 | Copy-paste bugs (`@Transactional` self-invocation, WebSocket double delivery); invented ROI/benchmark numbers |
| `15` creative / streaming | 9 | Invented 40 Hz ADHD studies; no YouTube monetisation-policy coverage; three series repeat one playbook |

---

## 2. Cross-cutting problems

These recur across many batches, so they are best fixed as one scripted or templated pass each
rather than post by post.

### 2.1 Broken series navigation (highest reader impact)

The most common finding in every batch. `check_links.py` reports the dead ones as warnings; the
script here finds **210 dead internal links in 85 posts (143 distinct targets)**, and the reviews
find more that are live but *wrong* (link text naming a topic the target does not cover).

- **Invented targets** — fde-interview-guide 43–52, ai-eng-from-scratch (37 of 43 posts),
  fde-core-concept (labels follow a 25-topic plan that was never published).
- **Plain-text navs with no links at all** — ai-system-on-native-aws 1–10, auto-agent-system,
  stock-analysis, creative series.
- **Relative `./x.md` and `../slug/` links** that bypass the render hook — the whole
  kubernetes-autoscaling series (70 dead links, the single largest source), vLLM, RAGFlow,
  Ollama, Langfuse, fde-interview-guide 10–25.
- **Finale language in the middle of a series** — fde-interview-guide part 9 "本系列已完結",
  ai-system-on-native-aws part 5 "感謝一路讀到這裡".

**Suggested fix:** one script that regenerates every `系列導航` block from the real filenames
(ordered by part/phase number) using `/posts/<slug>/` links, then
`python3 scripts/check_links.py --strict` to confirm zero dead targets.

### 2.2 Front matter out of spec

| Problem | Posts | Fix |
|---|---:|---|
| No `description` (falls back to `summary`, but CLAUDE.md requires it) | 60 | Mostly Aug 2025 – Apr 2026 English/CDK and LangGraph posts |
| `authors` value with no profile — `YennJ12 Engineering Team` (35), `yennj12 team` (16), `Yen-Nan Liu` (2), `Yen`, `Anu Srivastava`, `nvidia-auto` | 56 | Normalise to `["yen"]`; one post has no author at all, two use singular `author:` |
| `readTime` off by ≥ 8 min from the line-count rule (65 over, 43 under) | 108 | Recompute from the CLAUDE.md calibration |
| No `readTime` | 6 | |
| More than 3 canonical categories | 3 | `centralized-user-access-control-aws-cognito-cdk`, `mem0-intro-part5`, `vllm-intro-part5` |
| More than 12 tags | 23 | |
| `ai` category / `AI` tag on non-AI posts | many | Java, CDK and Docker posts inflate `ai` to 234 of 364 posts |
| No custom `image` (social card) | 364 | Every post uses the site default card |

**Tags:** 1,200 distinct tags, 827 of them used once, and about 90 case or spelling
near-duplicates (`AWS`/`aws`, `Auto Scaling`/`AutoScaling`/`Autoscaling`,
`Cost Optimization`/`CostOptimization`/`cost-optimization`, …). The full list is in
`.content-audit/summary.txt` after a run. A one-off canonicalisation map would collapse most of
them.

### 2.3 Fabricated or unsourced numbers

The most serious quality problem after navigation, found in 13 of the 16 batches: benchmark
tables, ROI figures, "實測" results and case-study outcomes that could not have been measured as
described. Examples: employee-management "3,700% ROI", WebSocket "10,000+ connections / <50ms",
aio-geo case-study results reused as benchmarks, nyc-taxi "50TB+", 40 Hz ADHD "Harvard and
Stanford" studies, "Real-World Performance" blocks in the CDK posts.

**Suggested rule:** a number is either sourced (link + date) or labelled 示意估算 / illustrative.
aio-geo part 11's `[可驗證]` / `[推估]` labels are a good house convention to adopt site-wide.

### 2.4 Stale models, prices and APIs

Most AI posts freeze a 2024–early-2025 snapshot: Gemini 1.5 prices, GPT-4o, Claude 3.5 model IDs
(retired), Titan Text, TGI, Karpenter v1beta1, CDK v1, TRL `max_seq_length`, the deprecated
`google.generativeai` SDK, pre-1.x LangChain/LangGraph. Where the stale value is *load-bearing*
(a headline savings %, an IAM policy scoped to one model ID, a decision table missing the option
the vendor now recommends) the post is wrong, not just dated.

**Suggested rule:** each post that quotes prices or model IDs carries one line such as
"價格與模型以 2026-09 為準", and model IDs live in one place per series.

### 2.5 Code that does not run as written

Posts written as copy-paste tutorials contain code readers will hit errors with: the autoscaling
hands-on, the Hugging Face SageMaker deploy (no health-check server; async config with sync
invoke), `@Transactional` self-invocation presented as the "correct design", the WebSocket chat's
double delivery, the Superset admin password interpolated into CloudFormation, fabricated Claude
Code SDK packages and paths. Each is listed with line numbers in its batch file.

### 2.6 Rendering and markup defects

- **Leaked tool-call markup** — `ai-fde-essential-guide-part3/4/5-zh.md` end with a raw
  `<function_calls><invoke name="TodoWrite">` block (L1391 / L1850 / L2056). Visible on the live
  site; delete first.
- **╔══╗ boxes written as `###` headings** — 13 posts (mem0 1–4, vLLM 1–5, several
  ai-eng-from-scratch), about 80 junk TOC entries. One regex pass.
- **Nested code fences** that break layout — ADHD, ocean parts 2–3, synthwave part 3.
- **H1 inside the body** — 3 posts. **Language mismatch** — 4 `-zh` posts that are mostly English
  and one non-`-zh` post that is mostly Chinese.
- **Non-breaking spaces in a filename** — `nvidia-minimax-m27 advances …-zh.md`.

### 2.7 Duplication across series

The same topic is often taught two or three times without cross-links: RAG (rag-series,
fde-interview-guide, ai-eng-from-scratch, chatpdf), memory and caching in fde-interview-guide
(13↔20, 14↔18, 12↔19), fde-core-concept vs fde-interview-guide (almost every core topic has a
longer guide counterpart), the three streaming series, the token-optimisation series, and several
CDK post pairs. Each batch file proposes a specific merge or "canonical owner + link" plan.

---

## 3. Series standards compliance (CLAUDE.md)

### fde-interview-guide (52 posts)

| Rule | Failing |
|---|---:|
| ≥ 600 lines | 39 |
| Has 「三個演進階段」 | 39 missing |
| ≥ 4 「為什麼選 X 不選 Y」 | 48 below |
| Sections capped at 十 | 12 over (most only because of the dropped section below) |
| No 面試答題要點 section | 28 still have it (parts 16–25, 35–52) |
| Model-answer variants under other names | parts 1–9 `面試回答完整示範`, 10/11/15 SCOPE/DARK/CAPE `完整範例回答` |
| Tag `RKK` | 9 missing (parts 1–9) |
| No `Google` tag | 38 carry it (parts 1–38) |

Parts 1–38 predate the current standard. The reviews recommend **not** padding them all to 600
lines: keep 1–9 as a lighter "Foundations" tier, merge 10–15 into their later counterparts, and
upgrade 16–25 (already scenario-first) to the full standard.

### ai-eng-from-scratch (43 posts)

| Rule | Failing |
|---|---:|
| No `Interview` tag | **all 43 carry it** — CLAUDE.md says to drop it |
| No interview framing in body | every post still opens with a 面試情境 block; 11p1, 11p2, 18p1 say "準備面試" inline |
| ≥ 600 lines | 25 |
| ≥ 4 「為什麼選 X 不選 Y」 | 25 below |
| Dead series-nav links | 37 |

For the math/probability/history foundation posts the forced "< 10K 用戶" three-phase framing
fits poorly; the review suggests a variant of the template for them.

### 10-K deep dives (14 posts)

All within 550–606 lines, 20 sections, correct fiscal years, `finance` category and 10-K tag.
Calls are honestly mixed (3 bullish, 11 neutral). The shared INVESTMENT SIGNAL template bug
(section 1 table, batch `07`) is the only systemic issue; fix it in
`docs/10K_DEEP_DIVE_WORKFLOW.md` too so new posts do not inherit it.

---

## 4. Decisions for the owner

These came up in several batches and cannot be settled by editing posts; each needs a call, and
probably a line in `CLAUDE.md`.

1. **The "no Google" rule vs Google-centric interview posts.** fde-interview-guide 31–33 and
   parts 2, 22, 26 are *about* Google Cloud products (ADK, Vertex AI) or Google's interview
   loop, so the rule cannot apply literally. Reviewers suggest: drop identity claims and the
   `Google` tag, keep product names. Separately, remove the first-person employer claim in
   part 1 and the parts 1–9 descriptions regardless — it is unverifiable and possibly
   NDA-sensitive.
2. **`RKK` vs `RRK`.** The commonly documented term is Role-Related Knowledge (**RRK**).
   CLAUDE.md mandates the tag `RKK`. Confirm which is intended before a tag sweep.
3. **Which posts are exempt from the fde standard.** Part 33 (interview anatomy), 34 (mock
   bank) and 42 (consulting phases) are not architecture posts; forcing 三個演進階段 onto them
   adds noise.
4. **Retire vs fix.** The 10 "consider retiring" posts include the two `nvidia-*` posts
   (hallucinated, credited to real authors — the generator in
   `scripts/generate_nvidia_blog.py` should also stop publishing unreviewed output),
   ai-fde-essential-guide 1/3/4, `harness-engineering-intro-ai-zh`,
   `langgraph-ai-backend-ideas-zh`, kubernetes-autoscaling part 8,
   `microservices-architecture-patterns` and `spotify-playlist-full-stack-application`. Deleting a post breaks inbound
   links; add Hugo `aliases` on the surviving post when merging.
5. **Trade instructions in stock posts.** AVAV / PL verdicts give entry zones and stop-losses.
   Decide whether the blog gives signals or only analysis, and add it to the 10-K workflow doc.

---

## 5. Suggested order of work

| # | Change | Effort | Why first |
|---|---|---|---|
| 1 | Delete the leaked `<function_calls>` blocks (essential-guide 3–5) and the two `nvidia-*` posts | minutes | Publicly visible, embarrassing, attributed to real people |
| 2 | Remove the Google-employee claim (fde part 1 + descriptions 1–9) | minutes | Trust / NDA exposure |
| 3 | Scripted series-nav rebuild + `check_links.py --strict` to zero | ~1 day | Largest reader-facing defect; touches ~200 posts in one reviewable diff |
| 4 | Front-matter sweep: authors → `yen`, add 60 descriptions, recompute readTime, drop `Interview` from ai-eng, fix the 10-K signal template, tag canonicalisation map | ~1 day | Mechanical, verifiable by re-running `audit_content.py` |
| 5 | Collapse `###` ╔║╚ headings, fix nested fences, H1s | hours | One regex pass each |
| 6 | Fix copy-paste code bugs and fabricated APIs (batches 10a, 11, 12, 13, 14) | days | Readers lose time on them |
| 7 | Source-or-label pass on numbers; dated assumptions line on price/model posts | ongoing | Do it series by series, alongside merges |
| 8 | Merges and restructures (duplicate pairs, token series, streaming, LangGraph, autoscaling 8→5) | weeks | Largest effort; needs the decisions in section 4 first |

After steps 3–5, re-run `python3 scripts/audit_content.py` — the clean-post count (78 today) is a
reasonable progress metric.
