# Content-audit brief (shared by every batch reviewer)

Repo: this worktree (Hugo blog, 362 posts under `content/posts/`). Do NOT edit any post or config file; write only your batch report under `docs/content-audit/batches/`.

## Read first
1. `.claude/skills/blog-reviewer/SKILL.md` — the rubric (6 dimensions 1–5, severity, finance accuracy ×2)
2. `.claude/skills/tech-blog-writer/SKILL.md` and `.claude/skills/finance-blog-writer/SKILL.md` — what a good post looks like
3. `CLAUDE.md` — house rules and series rules (fde-interview-guide, ai-eng-from-scratch, 10-K)
4. `docs/content-audit/inputs/mechanical-baseline.txt` — `scripts/review_posts.py` output for all posts (grep your files; do not repeat these, reference them)
5. `docs/content-audit/inputs/batches.txt` — your batch's file list

## Per post
Read the whole post. State its thesis in one sentence (or "no thesis"). Score A/C/D/V/S/F, compute Overall (finance: accuracy double weight) and Verdict (Ready ≥4.0 / Needs revision 3.0–3.9 or any major / Not ready <3.0 or any blocker). Pick the 3–5 claims a reader would act on and check them: internal consistency, recomputed numbers (python3), API/version/product facts (WebSearch/WebFetch when the fact moves fast; otherwise mark ❓ unverified — never call a recent release wrong from memory). Note the single most important finding with a line number.

## Per batch
Cluster-level patterns with file:line evidence under six headings: Content quality · Structure (does the house format help or pad?) · Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks") · Direction (overlap, gaps, stale topics, category fit) · Accuracy · Format/front matter.

## Output — write `docs/content-audit/batches/<BATCH-ID>.md` with exactly these sections
1. `## Batch summary` (5–10 sentences, verdict distribution)
2. `## Per-post scorecard` — table: file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (with line)
3. `## Patterns` — the six headings, 2–6 evidence bullets each
4. `## Top findings` — 10–15 ranked: severity | file:line | finding | suggested fix
5. `## Recommendations` — 5–10, each with WHY and HOW
6. `## Verified / unverified claims` — ✅ / ❌ / ❓ with file:line
Keep the report under ~400 lines. Reply to the coordinator with a ≤150-word summary when done.
