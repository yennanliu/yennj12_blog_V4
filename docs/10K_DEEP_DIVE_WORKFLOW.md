# 10-K Deep-Dive Post Workflow

How to generate Traditional-Chinese, institutional-grade **`<公司> (<TICKER>) <FY> 10-K 深度解析`**
blog posts from SEC 10-K filings — the process used to produce the META post and the 13-company
batch (AMD, AMZN, AVAV, BRK.B, GOOGL, KTOS, NEE, NVDA, ONDS, ORCL, PLTR, RKLB, TSLA).

The gold-standard reference post is `content/posts/meta-2025-10k-deep-dive-zh.md`. When in doubt,
open it and mirror its structure, depth, tone, and ASCII charts.

---

## 1. When to use

The user points at one or more 10-K PDFs and asks for a deep-dive post "the same way". Each post is
a structured digest for **comprehension**, not a trading signal, and always carries a non-advice
disclaimer.

## 2. Prerequisites

- **Skill**: InvestSkill `10k-digest`, installed at `.claude/skills/10k-digest/SKILL.md`
  (from <https://github.com/yennanliu/InvestSkill>). Its `SKILL.md` defines the digest output
  contract; this workflow extends it to a full ~20-section blog post.
- **Filings**: local PDFs at `../finance_data/10-k/<TICKER>/<TICKER>_<FILINGYEAR>_10-K.pdf`.
  - ⚠️ The number in the filename is the **filing year**, NOT the fiscal year. `META_2026_10-K.pdf`
    is the FY2025 report filed in early 2026. Always read the real fiscal year off the cover
    ("For the fiscal year ended <MONTH DAY, YEAR>"). Non-calendar filers differ:
    NVDA ≈ Jan-end → FY2026; ORCL ≈ May-end → FY2026; AVAV ≈ Apr-end → FY2026; calendar filers → FY2025.
- **Tools** (already available on this machine): `pdftotext -layout` (poppler), `python3` with
  `pymupdf` (`fitz`) for page counts and verifying derived numbers. No OpenAI key needed — this is
  done directly by Claude, unlike `scripts/generate_nvidia_blog.py`.

## 3. Single-company procedure

1. **Extract text**
   ```bash
   pdftotext -layout "../finance_data/10-k/<TICKER>/<TICKER>_<Y>_10-K.pdf" "<scratchpad>/<TICKER>.txt"
   python3 -c "import fitz; print(len(fitz.open('<pdf>')))"   # page count
   ```
2. **Grep the statements** — anchors vary by company:
   `CONSOLIDATED STATEMENTS OF (INCOME|OPERATIONS)`, `CONSOLIDATED BALANCE SHEET`,
   `CONSOLIDATED STATEMENTS OF CASH FLOWS`, `Segment`, `per share`, `Total assets`,
   `long-term debt`, `Item 1A`, `Item 7`, plus company-specific terms (float, rate base, RPO,
   backlog, regulatory credits…).
3. **Build history** — the primary 10-K's income & cash-flow statements already show 3 fiscal
   years. Pull 2 more from the `_<Y-2>_` (or `_<Y-3>_`) filing for a 5-year table. A solid 3-year
   table is acceptable if older filings are missing.
4. **Verify every derived number** (`python3`): YoY %, margins, FCF, ROE/ROIC, per-share, Rule of 40.
   Use ONLY figures from the filing; never invent one and present it as reported. Label computed ratios.
5. **Write** to `content/posts/<slug>-<FY>-10k-deep-dive-zh.md`
   (`<slug>` = lowercase ticker, dots→hyphens, e.g. `brk-b`; `<FY>` = fiscal year from the cover).
6. **Self-validate the build** (see §6). Fix front-matter/markdown until the post's `index.html` renders.

## 4. Front matter

```yaml
---
title: "<CompanyName> (<TICKER>) <FY> 10-K 深度解析"
date: 2026-07-19T09:00:00+08:00
draft: false
description: "一句話,說明用 10k-digest 方法拆解 <公司> FY<FY> 年報,涵蓋五年財務軌跡、事業體/地區、關鍵獲利品質議題、資本配置、風險與投資訊號。"
categories: ["finance", "investing", "all"]
tags: ["<TICKER>", "<Company EN>", "10-K", "SEC", "財報分析", "價值投資", "美股", "InvestSkill"]  # + 1-3 topical tags
authors: ["yen"]
readTime: "~28-32 min"
---
```

These are **finance posts, not interview posts** — the CLAUDE.md "no Google" rule does NOT apply;
name any competitor (Alphabet, TikTok, etc.) freely.

## 5. Required section structure

Chinese numerals 一、二、三…; include ASCII bar charts and box diagrams; target **450–600 lines**.
Adapt/rename sections to the business model, but keep the depth.

1. Opening: 4-line contrast quote (common misread vs the real story) + a ⚠️ 免責聲明 block.
2. 一、執行摘要 — one-sentence thesis + small signal table.
3. 二、財務健檢儀表板 — metric : value : YoY-trend scorecard (ASCII).
4. 三、文件定位 — filing type, FY, auditor, opinion, restatements, segment changes, share count,
   cover market value, governance notes.
5. 四、五年(或三年)財務軌跡 — multi-year table + ASCII revenue/margin charts + 2–3 turning points.
6. 五、損益表分析 — 3–5yr line items, margins, R&D/SG&A intensity, operating leverage; ⚠️-flag oddities.
7. 六、事業體與地區拆解 — segment + geography tables. Adapt: BRK→insurance float/segments;
   NEE→regulated rate base vs NEER; PLTR→Government vs Commercial; TSLA→Automotive vs Energy;
   NVDA→Compute & Networking vs Graphics; AMZN/GOOGL/ORCL→cloud segments.
8. 七、資產負債表分析 — cash, debt, goodwill %, business-specific items, net cash/debt, leverage.
9. 八、現金流與資本配置 — OCF/capex/FCF, capex intensity, buybacks/dividends, ASCII cash-flow map.
10. 九、深度分析 (3–5 sub-parts) — the NON-OBVIOUS stories for THIS company. Show GAAP→normalized
    bridges. Recurring patterns worth hunting: one-time tax items, acquisition amortization,
    unrealized equity-investment gains, useful-life changes, SBC dilution, DuPont ROE/ROIC,
    Rule of 40, customer concentration, the central strategic bet + its flywheel.
11. 十、情境分析 (FY+1) — 悲觀/基準/樂觀 table, clearly labelled 說明性質 (illustrative).
12. 十一、競爭格局 — named competitors + moat assessment.
13. 十二、風險矩陣 — severity-coded (🔴 高 / 🟠 中高 / 🟡 中) table from Item 1A.
14. 十三、會計品質與註記 — audit opinion, CAM/critical audit matters, one-time items, contingencies.
15. 十四、管理層可信度與語氣 — tone/transparency assessment with specifics.
16. 十五、領先指標監控清單 — table: metric | current | watch signal | deterioration signal.
17. 十六、正面因素與紅旗 — ✅ positives / 🔴🟠🟡 red flags checklists.
18. 十七、會計品質評分 — X/10 scorecard with deduction rationale.
19. 十八、估值脈絡 — illustrative only; use cover market value; P/E, EV/FCF, net cash; STRONG caveat.
20. 十九、最終判斷、論點反轉與投資訊號 — recommendation + 論點反轉條件 list + a boxed
    INVESTMENT SIGNAL card (Sentiment / Conviction / Horizon / Quality X.0/10 / Action) in ╔═╗ style.
21. 二十、參考來源 — SEC EDGAR filing, items used, `10k-digest` link, and the report-structure
    reference <https://yennj12.js.org/InvestSkill/full-demo-amd.html>.
22. Closing: 系列導覽/延伸閱讀 + a repeated non-advice reminder.

**Be honest per company.** Score on the actual filing — unprofitable / expensive / high-risk names
get lower quality scores and NEUTRAL/cautious signals. Do not make everything bullish. (In the
batch, only AMZN and GOOGL earned BULLISH; ONDS/KTOS/AVAV landed at 4.0–5.0/10.)

## 6. Build & validation

Hugo **exits 1** on this repo due to a pre-existing site-wide `paginate` config deprecation — this
is unrelated to any post and the Hugo 0.121.1 CI deploy is unaffected (see the project memory note).
So verify by the rendered output, not the exit code:

```bash
hugo --minify                                   # ignore the paginate error line
ls public/posts/<slug>-<FY>-10k-deep-dive-zh/index.html   # must exist
```

For parallel work, build each agent to a unique dir to avoid `public/` races:
`hugo --minify -d <scratchpad>/build_<TICKER> --quiet`.

## 7. Batch / multi-company orchestration

For many companies at once (as in the 13-company run):

1. List targets: `find ../finance_data/10-k -iname "*_2026_10-K.pdf"`.
2. **Dedupe share classes**: GOOG and GOOGL are Alphabet's single combined 10-K — produce ONE
   Alphabet post (use GOOGL) and skip GOOG.
3. Write a shared build spec once (the content of §3–§6 above) and dispatch **one general-purpose
   subagent per company** in parallel (`Agent` tool, background). Each agent gets: the spec path, the
   company name/ticker/PDF path, extra topical tags, business-model adaptation notes, and a scratchpad
   dir. Agents **self-validate but do NOT run git**.
4. The orchestrator waits for all agents, then does ONE authoritative `hugo --minify`, verifies every
   `public/posts/<slug>/index.html` exists, and makes a **single commit** for the whole batch.

## 8. Git conventions

- Commit the post `.md` files (and, once, the `.claude/skills/10k-digest/SKILL.md` skill).
- `public/` and `resources/` are gitignored (Hugo output). `.claude/settings.local.json` is
  gitignored (personal permissions) — the skill dir itself is tracked.
- Commit/push only when the user asks. These posts go straight to `main` (the deploy branch).
