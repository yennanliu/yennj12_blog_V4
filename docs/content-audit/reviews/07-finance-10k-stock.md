## 10-K deep dives (14), stock-analysis AVAV/PL (6), stock-selling, finance-data (2), investskill, anthropic-financial-services (3) — 27 posts

### Series-level observations
- **The 10-K signals vary by company; the template does not.** Across the 14 posts: 3 BULLISH (AMZN, GOOGL, META), 11 NEUTRAL, 0 BEARISH. Signal-card Quality ranges from 4.0 (ONDS) to 8.5 (BRK.B, NVDA). A per-file check under `LC_ALL=C` found no body sentence repeated across posts. Only the scaffolding repeats: the 20 H2s, the table headers, the disclaimer lines, `**論點反轉條件(This thesis flips if…)**`, and the signal box. Sampled risk matrices (十二) and valuation sections (十八) for ONDS, KTOS, NVDA, PLTR, and bear cases and red flags for AMZN, TSLA and BRK.B. All were company-specific, with real numbers from the filing (ONDS P/S ~64–92x, KTOS P/E ~295x, PLTR P/S ~67x, TSLA carbon credits = 46% of operating income). The "not uniformly bullish" requirement is met. The weak spot is that nothing is ever called bearish, even ONDS (4.0/10, "HOLD / AVOID") and KTOS (4.5/10). For those two, "NEUTRAL(偏謹慎)" reads like reluctance to say sell.
- **Template sameness shows up in the 九、深度分析 sub-headings of the three mega-caps.** META, GOOGL and AMZN share `折舊的定時炸彈`, `資本效率:DuPont ROE 與 ROIC 拆解`, and `AI 資本支出的賭注與飛輪`. META and GOOGL also share `Rule of 40 壓力測試`. GOOGL's list (A–E) is essentially META's with one noun swapped, and `淨利 +X% 的真相` opens 7 of the 14 deep dives. The smaller names (ONDS, KTOS, RKLB, AVAV, NEE, BRK.B, NVDA, ORCL) have properly bespoke deep-dive angles. Rename the mega-cap sub-sections so the headline says what is different about that company.
- **Scoring inconsistency across all 14 10-K posts (highest-impact trust issue).** Each post has three numbers that look alike but mean different things:
  - 十七 `會計品質評分` X/10 (e.g. PLTR 8.0, RKLB 7.5, ONDS 6.0).
  - The signal box `Quality:` (PLTR 6.0, RKLB 5.5, ONDS 4.0).
  - The line `> 評分指引:8.0–10.0 強烈偏多 | 6.0–7.9 中度偏多 | 4.0–5.9 中性…` under the box, which maps Quality onto sentiment bands.

  Under that guide, BRK.B 8.5 and NVDA 8.5 are "強烈偏多" but carry NEUTRAL. AMD 6.5, ORCL 6.5, TSLA 6.0 and PLTR 6.0 are "中度偏多" but carry NEUTRAL. Only `brk-b` line 541 explains that Quality ≠ Sentiment. Every box also has **two `Conviction:` rows** (MEDIUM, then MODERATE). In KTOS they disagree: LOW-MEDIUM vs LOW. In RKLB: MEDIUM vs SPECULATIVE. Fix it once in the template and in all 14 posts: drop the second Conviction row, and either label the box score "綜合評分" or reuse the §十七 number. Also reword the 評分指引 line as a composite-score guide, or drop it.
- **Valuation anchors are old and not flagged as a date.** Every 十八 uses the 10-K cover market value, which is roughly June–July 2025 for calendar filers (PLTR `2025-06-30`, KTOS `2025-06-29`, NVDA `2025-07-25`). The posts were published 2026-07-19, and it is now Sept 2026. The caveats say "非目標價", but the multiples ("P/S ~67x", "~295x") read as current. Put "市值基準日:YYYY-MM-DD(約 N 個月前)" in each 十八 header. For calendar filers, note that FY2026 H1 has since been reported and that 十、情境分析(FY2026) is now partly realized.
- **No cross-linking inside the finance cluster.** The 10-K posts end with `### 系列導覽 / 延伸閱讀`, which contains only the InvestSkill GitHub link and a plain-text `相關主題:SEC EDGAR 資料抓取、財報自動化分析 pipeline`. Posts on both topics exist in this batch (`finance-data-sec-edgar-toolkit`, `finance-data-ai-pipeline-how-it-works-zh`). None of the 14 links to another 10-K post, and `avav-2026-10k` does not link the AVAV three-part stock analysis (or the reverse). Add a real nav block: the other 13 deep dives grouped by sector, plus the two finance_data posts and the stock-analysis series where the ticker overlaps.
- **The workflow doc has drifted from the taxonomy.** `docs/10K_DEEP_DIVE_WORKFLOW.md` §4 prescribes `categories: ["finance", "investing", "all"]`. `investing` is not a canonical category, and "all" should come first. The posts correctly use `["all","finance"]`, so fix the doc before the next batch copies it.
- **Stock-analysis series (AVAV, PL):** both verdict posts date their price references properly (`分析日期：2026 年 6 月 26 日｜股價…`) and carry disclaimers at the top and bottom. The verdict boxes, however, give concrete entry, add and stop-loss levels (AVAV: `左側佈局：$120–130 可小量試單…停損參考：跌破 $100`; PL: `新資金分批布局 $24–26…停損參考：跌破 $22`). That is trading instruction, whatever the disclaimer says. Parts 1 and 2 of both series have unlinked series nav. Part 3 uses relative `../slug/` links, where the CLAUDE.md convention is `/posts/slug/`.
- **Anthropic financial-services (3 parts, 143–188 lines):** yes, too thin as a three-part series. Part 1 is a README paraphrase, and Part 3 promises "實戰:跑一次" but shows only an illustrative output (`輸出報告的骨架大致長這樣(示意,非真實輸出格式)`). Together they would make one solid ~450-line post.

### Per-post

#### `amd-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- Strong, specific thesis: the two-way GAAP distortion (Xilinx amortization pulls earnings down, the $853M one-time tax benefit pushes them up), and 33% of assets in goodwill. Honest NEUTRAL call.
- Signal box: Quality 6.5 falls in the guide's "中度偏多" band next to NEUTRAL, and there are two Conviction rows. Apply the template fix.
- The 十八 valuation uses the cover value of `$2,323 億 (2025-06-28)` while the summary says "近 2,000 億美元市值". Reconcile the two figures and state the as-of date.

#### `amzn-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- BULLISH is earned, and the bear case is fully stated (FCF −70.7% to $11.2B, AWS margin 37.0%→35.4%, about half of net-income growth from the Anthropic mark-up). Good.
- 九 sub-headings B/C/E duplicate META and GOOGL (`折舊的定時炸彈`, `DuPont ROE 與 ROIC 拆解`, `AI 資本支出的賭注與飛輪`). Retitle them around what is Amazon-specific: shorter useful lives, and the FCF collapse.
- The first flip condition (`申報下一份 10-K/10-K/A 修正版,或重大 8-K…`) is boilerplate shared by 10 posts. Replace it with a company-specific trigger.

#### `anthropic-financial-services-intro-part1-usage-zh.md`
**Verdict:** rewrite/merge
- Mostly a translation of the repo README: install commands, plugin list, role table. Little here a reader couldn't get from the source repo. Merge it with Part 2 into one "what it is and how it is built" post.
- §五 and §七 say "全部 11 個資料連接器", but §七 then lists 12 names (Daloopa, Morningstar, S&P Global, FactSet, Moody's, PitchBook, Chronograph, Egnyte, Box, LSEG, Aiera, MT Newswires). Verify against `.mcp.json` and fix the number.
- The plugin names and the `@claude-for-financial-services` marketplace id change quickly. Add an "as of 2026-07" note and a commit hash.
- The series nav at the bottom is plain text with no links. Categories are `ai, engineering`; `tools` (Claude Code plugin) and `finance` fit better.

#### `anthropic-financial-services-intro-part2-concepts-zh.md`
**Verdict:** rewrite/merge
- The best of the three. The single system prompt feeding both Cowork and Managed Agents, and the Skill-vs-Command decision with its flip condition (§四), are real insight. Keep it as the core of the merged post.
- The §五 "11 個資料源" table has the same count problem (Egnyte and Box share one row).
- `callable_agents` is described as "Research Preview". That status is time-sensitive as of Sept 2026; verify it and date it.
- §八 系統效應 has no numbers. Either drop it or add concrete ones (for example, the number of agents that share one skill file).

#### `anthropic-financial-services-intro-part3-example-zh.md`
**Verdict:** restructure
- The title promises `實戰:用 GL Reconciler 跑一次對帳流程`, but no run happens. §三 shows a prompt and a hand-written output skeleton labelled `示意,非真實輸出格式`. Either run it on a small synthetic GL/fund-admin CSV pair and show the real output, or retitle it as a walkthrough.
- §六 `月底對帳耗時 2–3 個工作天 → 當天出報告` is unsourced. Label it as an assumption or remove it.
- The 三個演進階段 structure (§二) is borrowed from the interview-series standard and feels bolted on for a product intro. The 10K/200K/1M 筆 tiers are not tied to anything the repo documents.

#### `avav-2026-10k-deep-dive-zh.md`
**Verdict:** light edit
- Among the most honest posts in the batch: goodwill impairment ten months after the acquisition, a material weakness in internal controls, and a quarterly restatement, scored at 4.5/10 accounting quality. §十四 contrasts it well with Meta ("只驗證了「敢賭、且敢認錯」,還沒驗證「賭對」").
- Link the AVAV three-part stock analysis (dated 2026-06-26, before the Q4 print). This 10-K is the post-earnings reality check that series was waiting for. Its FY2026E revenue of ~$1.99B vs the reported $1,976.8M is a nice validation to mention.
- Template fix for the signal box (Quality 5.0 vs 十七 4.5).

#### `brk-b-2025-10k-deep-dive-zh.md`
**Verdict:** keep as is
- The deep dive is genuinely adapted to the business model: float, a GAAP→operating-earnings bridge, $87B of deferred tax as a "second float", and the Abel succession. It is also the only post that explains Quality vs Sentiment (line 541). Use its wording as the template fix for the other 13.

#### `finance-data-ai-pipeline-how-it-works-zh.md`
**Verdict:** light edit
- Counts are inconsistent: `42 個機器人` in the opening, `覆蓋 30+ 家公司` in §一, and `24 支股票每 10 分鐘一支` in §八. Pick the real numbers.
- There is a trust gap in a fully automated investment-report pipeline. It covers retries for truncation and refusals, but nothing on validating the numbers the LLM writes, hallucination checks, or human review before publishing. Add a "品質把關的缺口" paragraph.
- The refusal-bypass pattern (§四: raise the temperature, add an override prefix, retry up to 5 times) is presented as a design win. At minimum, note that it works against the model's safety behaviour, and that a disclaimer-first prompt is the more robust fix.
- Staleness: the defaults `gemini-2.5-flash` and `gpt-4o` should be verified as current. Scraping Finviz, StockAnalysis and Roic.ai deserves a ToS caveat. The `RAG` tag is inaccurate (this is context stuffing). `ai_gen_report/stock/<ticker>/xxx.md` should read `<date>-<type>.md`.

#### `finance-data-sec-edgar-toolkit.md`
**Verdict:** light edit
- It never mentions the SEC's required declared `User-Agent` header, the most common reason EDGAR scripts get 403s, which is more important than the 10 req/s limit covered in Step 5. Add it.
- Step 1 resolves ticker→CIK through `efts.sec.gov/LATEST/search-index` (full-text search). The canonical source is `https://www.sec.gov/files/company_tickers.json`. Verify what the script actually does.
- "What's next: structured parsing" skips `data.sec.gov/api/xbrl/companyfacts`, which already gives structured financials for free. There is also no comparison with the existing libraries (`sec-edgar-downloader`, `edgartools`). Readers will ask why this tool instead.
- The conclusion says "zero-dependency" and the next line is `pip install requests`. `13-F` should be `13F`. Categories have 3 canonical values, and `tools` (reserved for Claude Code/MCP) doesn't fit. Link the 10-K deep dives, which are built from these PDFs.

#### `googl-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- The content is solid, but 九 A–E mirrors META almost exactly (`淨利 +32% 的真相`, `折舊的定時炸彈`, `DuPont ROE 與 ROIC 拆解`, `Rule of 40 壓力測試`, `AI 資本支出的賭注與飛輪`). Readers of both will notice. Retitle and lead with what is Alphabet-specific (for example, the equity-gain inflation and the Cloud margin inflection).
- BULLISH next to a 7.5 Quality score. Fine, once the scoring legend is fixed.

#### `investskill-claude-code-financial-analysis-plugin.md`
**Verdict:** restructure
- Stale. The post (Feb 2026) describes "six pillars" and a six-skill tree. The plugin now ships ~20+ skills (dcf-valuation, insider-trading, institutional-ownership, short-interest, options-analysis, full-report, result-validator, etc.) plus `10k-digest` and `industry-map`, all of which this blog's own 10-K and stock-analysis posts rely on. The roadmap's "Short-Term (Next 3 Months)" (Options Analysis, Real-Time Data via MCP…) is either past due or already shipped.
- It never says where the data comes from: web search, user paste, or MCP. That is the first question a practitioner has about an LLM stock analyst.
- Scenario 4 puts slash commands inside a Python function as comments, next to an `if rsi < 30 and gdp_growth > 2.0` rule. It teaches nothing; cut it.
- Marketing tone, and emoji on every H2. The `MCP` tag is unjustified (no MCP in the current design). Link the 10-K deep dives and the AVAV/PL series as real output examples.

#### `ktos-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- Honest and pointed. SBC = 139% of operating income, FCF −$137M, and P/E ~295x are clearly argued, and §十八 calls it a "故事股 / 主題股" valuation.
- Given that analysis and 4.5/10, "NEUTRAL(偏謹慎)" plus "HOLD" undersells the conclusion. Either justify why it is not bearish or use the scale's lower band.
- The Conviction rows contradict each other (LOW-MEDIUM / LOW).

#### `meta-2025-10k-deep-dive-zh.md`
**Verdict:** keep as is
- The reference post. The rest of the batch has since become as good or better, but its generic 九 sub-headings (`折舊的定時炸彈`, `DuPont`, `Rule of 40`, `AI 資本支出的賭注與飛輪`) are where the mega-cap sameness came from. When editing GOOGL and AMZN, leave META's as the original.

#### `nee-2025-10k-deep-dive-zh.md`
**Verdict:** keep as is
- Well adapted to a utility: rate base and allowed ROE, the negative effective tax rate and OBBBA risk, and interest-rate sensitivity as the weakest joint. The only fix is the shared signal-box template (7.5 vs NEUTRAL vs the 評分指引).

#### `nvda-2026-10k-deep-dive-zh.md`
**Verdict:** light edit
- Fiscal year handled correctly: the title says FY2026, the body has `截至 2026-01-25`, and scenarios are for FY2027. The bespoke deep dive (circular-financing concern, $95.2B of purchase commitments, gross-margin headwind) is excellent and does not read as a cheerleader piece.
- Line 411 has mixed text: `系統化business model 拉低毛利含量`. Write it as `系統化商業模式`.
- An 8.5 Quality score with NEUTRAL is fine, but under the current 評分指引 it reads as "強烈偏多". Template fix.

#### `onds-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- The candour stands out: shares up 309% in a year, warrant liability larger than equity, two customers = 66% of revenue, and a "數量級" valuation table built on assumed share prices because the cover value is stale. This post shows the template's honesty working best.
- The Accounting score of 6.0/10 (§十七) looks generous against its own red flags: a small audit firm, no 404(b) internal-control attestation, and a prior impairment. Either justify it or lower it.
- "NEUTRAL" with "HOLD / AVOID" is hedged. The analysis supports a cautious/bearish label outright.

#### `orcl-2026-10k-deep-dive-zh.md`
**Verdict:** keep as is
- Fiscal year handled correctly (FY2026 ending 2026-05-31, scenarios FY2027). The RPO $638B concentration angle and "ROE 53% 是陷阱,ROIC 12% 才是真相" are the right non-obvious stories. Signal-box template fix only.

#### `pltr-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- The core tension ("好公司 ≠ 好股票(在此價位)", P/S ~67x, P/E ~184x, tax-normalized ~229x) is argued well.
- The largest gap in the batch between the two scores: Accounting 8.0 (§十七) vs signal-box Quality 6.0. Readers will ask which one is the "quality".
- The multiples rest on the `2025-06-30` cover value, and the text only says "現價更高". Give the as-of date prominently, or add a current-price sensitivity line like ONDS's table.

#### `rklb-2025-10k-deep-dive-zh.md`
**Verdict:** light edit
- Good specifics: the Neutron tank rupture in Jan 2026, the securities litigation over Neutron timelines, and 21 vs 16 launches.
- The signal box has `Conviction: MEDIUM` and `Conviction: SPECULATIVE` together. The second is a horizon or risk label, not a conviction level.
- Only 4 deep-dive sub-parts. That is fine, but the backlog section (D) could quantify how much of the backlog is Neutron-dependent.

#### `stock-analysis-avav-aerovironment-part1-fundamentals-zh.md`
**Verdict:** light edit
- The header's `52 週區間：$147.75 – $417.86` sits next to a current price of $142.35, which is below the stated low. Part 2 explains that $147.75 is the prior low (`破前低`), but the header reads as an error. Update the range or label it `前 52 週低`.
- The analysis is pinned to the pre-earnings date (6/29 Q4). Add a top banner linking `avav-2026-10k-deep-dive-zh` for the actual FY2026 results. The FY2026E ~$1.99B held up against the reported $1.977B, which is worth saying.
- The series nav is unlinked text.

#### `stock-analysis-avav-aerovironment-part2-technical-sentiment-zh.md`
**Verdict:** light edit
- The moving averages the technical analysis rests on are marked estimated (`MA200: ~$255(估)`, `MA60: ~$185(估)`). Technical analysis on guessed moving averages is weak. Use actual closing-price data, or say plainly that the chart is schematic.
- The short-interest (12%), institutional-holding and insider numbers have no source or as-of date. Add one line of sourcing per table.
- The series nav is unlinked text.

#### `stock-analysis-avav-aerovironment-part3-valuation-verdict-zh.md`
**Verdict:** light edit
- The verdict box gives trade instructions (`左側佈局：$120–130 可小量試單`, `加碼參考…MA60(~$185)再加`, `停損參考：跌破 $100`). Beside a "不構成投資建議" disclaimer this contradicts itself. Recast these as "估值參考區間" without entry or stop language.
- The whole verdict hinges on the 6/29 print, which has already happened. Add an "事後更新(2026-07)" block, or link the AVAV 10-K post that covers the result.
- The DCF is honest: probability-weighted $123 vs price $142, "現價略貴", and a 5×5 sensitivity table. Good. The nav uses relative `../slug/` links; switch to `/posts/slug/`.

#### `stock-analysis-pl-planet-labs-part1-fundamentals-zh.md`
**Verdict:** light edit
- Fiscal year labels are consistent with PL's January year-end (`Q1 FY2027 財報電話會議分析`). Say that explicitly once, since readers will otherwise think it's a typo.
- The series nav is unlinked text. Otherwise the structure is clean and the whyXnotY framing (3 hits) is used sensibly.

#### `stock-analysis-pl-planet-labs-part2-technical-sentiment-zh.md`
**Verdict:** light edit
- Same sourcing gap as AVAV part 2: indicator values and short-interest/13F data have no source or as-of date.
- The series nav is unlinked text.

#### `stock-analysis-pl-planet-labs-part3-valuation-verdict-zh.md`
**Verdict:** light edit
- The verdict box `建議：…新資金分批布局 $24–26 區間…停損參考：跌破 $22` has the same problem as AVAV: concrete buy and stop levels. Reword them as valuation reference ranges.
- The price, date and 52-week range are clearly stated. The three-model spread ($18 DCF / $30 relative / $39.80 analyst) is presented honestly. Good.
- As of Sept 2026 the $28.42 reference is three months old. Add a "價格已過時" note or refresh it after the next quarterly print.

#### `stock-selling-strategy-systematic-approach-zh.md`
**Verdict:** restructure
- The title `心靈 Lesson 2` implies a series, but no Lesson 1 exists in `content/posts/`. Retitle it, or write and link Lesson 1.
- The personal "實際案例" read as real trades but need checking. The PLTR walkthrough has PLTR at `$25` in Jan 2024, when it traded around $16–17; the jump came after the Feb 2024 earnings. The NVDA "$220 → $880" is a pre-split mix. PLTR then went roughly 5x+ after the May 2024 trailing-stop exit. That is the most instructive part of the example and the post does not mention it. Either verify and discuss it, or label the cases "示意".
- The code does not run as written. The IBKR sample calls `self.nextOrderId()`, which is not an `EClient` method (the id arrives through the `nextValidId` callback), and it never starts `app.run()`. `analyze_opportunity_cost` annualizes a 12-month analyst target over `years=3`. Fix both or cut them to pseudocode. They make up much of the 65% code ratio.
- Heading hierarchy: `## 情境 A/B/C` sit under `### 事件型標的的進階策略` as H2s. Demote them to `####`.

#### `tsla-2025-10k-deep-dive-zh.md`
**Verdict:** keep as is
- The most balanced verdict in the batch. It leads with the bear case (`1. **空方論點**`), and flip conditions are tagged `(偏多反轉)` / `(偏空強化)`. Other posts should copy this format. Signal-box template fix only.

### Top 5 highest-impact fixes in this batch
1. **Fix the INVESTMENT SIGNAL template in all 14 10-K posts.** Remove the duplicated `Conviction:` row, reconcile the box `Quality` with the §十七 `會計品質評分` (PLTR 8.0 vs 6.0, RKLB 7.5 vs 5.5, ONDS 6.0 vs 4.0), and replace the `評分指引` line that maps quality scores onto 偏多/偏空 bands. BRK.B line 541 already has the right explanation. Update `docs/10K_DEEP_DIVE_WORKFLOW.md` §5 item 20 and §4 categories (`investing` is non-canonical) at the same time.
2. **Strip trade instructions from the AVAV and PL verdict boxes** (entry zones, "加碼", "停損"), and add a post-event update to AVAV. Its thesis hinged on the 6/29 print, which the blog's own `avav-2026-10k-deep-dive-zh` now covers.
3. **Build real cross-links across the finance cluster.** 10-K posts ↔ each other, ↔ `finance-data-sec-edgar-toolkit` and `finance-data-ai-pipeline`, ↔ the AVAV stock series, and the InvestSkill post → its real outputs. Link every stock-analysis part-1/part-2 series nav (currently plain text), using `/posts/slug/` form.
4. **Merge the three Anthropic financial-services posts into one or two.** Keep Part 2's architecture analysis, compress Part 1's install steps, and either run GL Reconciler on synthetic data for real or drop the word "實戰". Fix the "11 connectors" count (12 are listed).
5. **Update `investskill-claude-code-financial-analysis-plugin.md`**, which describes six skills when the plugin now has 20+. Retire the expired roadmap and explain where the data comes from. Separately, date-stamp the valuation anchor (cover market-value date) in each 10-K §十八, and retitle the copy-paste META/GOOGL/AMZN deep-dive sub-headings.
