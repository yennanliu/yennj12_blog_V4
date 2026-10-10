# B12 — Stock analysis (PL, AVAV), selling strategy, crypto quant (10 posts)

Files: `content/posts/stock-analysis-pl-planet-labs-part{1,2,3}-*-zh.md` (482/423/481 lines), `stock-analysis-avav-aerovironment-part{1,2,3}-*-zh.md` (492/422/480), `stock-selling-strategy-systematic-approach-zh.md` (1,003), `crypto-quantitative-trading-part{1,2,3}-*.md` (1,349/1,196/1,377). 7,705 lines total.
Mechanical baseline (`docs/content-audit/inputs/mechanical-baseline.txt` L5–7, L208): the three crypto posts and the selling post are flagged "finance post has no disclaimer near the top"; the six stock posts have no entries. Standard applied: finance-blog-writer non-negotiables (accuracy ×2, disclaimer in first screen, dated prices/multiples, sourced numbers with computed values labelled, bear case at full strength, no trading signals as advice). Sources used: `/Users/jliu/finance_data/10-k/AVAV/AVAV_2026_10-K.pdf` (via `pdftotext -layout`), the repo's `avav-2026-10k-deep-dive-zh.md`, AeroVironment's Q3 FY2026 release (2026-03-10), Planet's FY2026 (2026-03-19) and Q1 FY2027 (2026-06-04) releases, the `schedule` library reference, ccxt's API surface. ≥3 derived numbers per post were recomputed with python3 (`scratchpad/recompute.py`).

## Batch summary

This batch splits into two halves that fail for opposite reasons. The six **PL / AVAV stock posts** follow the finance house format well — disclaimer in the first screen (`pl-part1:19`, `avav-part1:21`), a dated price line on every post ("分析日期 2026-06-26 ｜ $28.42 / $142.35"), a probability-weighted DCF, four relative methods, a football field, a full-strength bear case and a 2026-09 "stale price" note on AVAV-1/3 and PL-3 — but the numbers underneath do not hold. Both DCF base cases cannot be reproduced from the FCF tables the posts print: PL's table (FY27–FY32, WACC 11%, g 3%, +$730.8M cash, 330M shares) yields **~$8/share, not the $17** the post builds its $18 weighted value on (`pl-part3:88–113`); AVAV's yields ~$106 vs the printed $115 (`avav-part3:88–113`), and both headings say 十年 while showing six years. PL-1 misstates FY2026 revenue growth as "~+12%" when its own figures give 308/244 = **+26%** (`pl-part1:132,136`), draws FY2026 FCF as "接近損益兩平 → FY27E 目標轉正" when Planet reported FY2026 FCF of **+$52.9M** (`pl-part1:191–204`), and treats the SPAC warrants as an ongoing quarterly noise source and dilution risk (`pl-part1:186,224`, `pl-part3:429`) although the Q1 FY2027 release the post analyses says all public warrants were redeemed and the private ones exercised. AVAV-1's backlog arithmetic is off twice in one table (`avav-part1:251,254`: 3.0 − 1.4 = 1.6 not 1.5; 4.1 − 1.4 = 2.7 not 2.6), the +77% dilution is +79% in the 10-K (28.27M → 50.61M shares), and "長期 FCF 為正" (`avav-part1:212`) contradicts the repo's own AVAV deep dive (FY2026 FCF −$140.9M). AVAV-2's Fibonacci row says a 78.6% drop from $417.86 is "~$129" — it is $89 (`avav-part2:119`). The headline company figures, by contrast, check out: AVAV Q3 revenue $408.0M and EPS $0.64; PL Q1 FY27 $94.2M (+42%), RPO $816M (+81%), backlog >$906M (+72%), $730.8M cash, FY27 guide $425–441M, FY26 adj. EBITDA $15.5M.

The **crypto series** has no disclaimer anywhere (grep confirms none in 3,922 lines), is categorised `finance`, and its code — the thing a reader would actually run — has five bugs that silently neutralise the risk and validation machinery it promises: the ADX helper divides a RangeIndex series by a DatetimeIndex series and returns NaN (`crypto-1:666`), so the ADX strategy never trades; the MA-crossover "2% risk" sizing resolves to 95% of capital (`crypto-2:421`); the daily-loss limit is computed on cash, so every buy trips it and disables stop-loss checks for the rest of the day (`crypto-2:894`, repeated for USDT in `crypto-3:660`); the Monte Carlo test shuffles trade order and compares final P&L, which is permutation-invariant, so it prints "likely due to luck" for every strategy (`crypto-3:369–382`); and `main.py` sizes at 95% against a 10% cap, so the live bot never places an order (`crypto-3:1239` vs `:617`). The slippage worked example prints 0.08% for a book that gives 0.062% (`crypto-1:129`), the order-book diagram is crossed (`crypto-1:72–78`), "Settlement: T+2" is stale (`crypto-1:31`), and no backtest result is ever reported, so there are no numbers to date or cost-check — only the engine defaults (0.1% commission, 0.05% slippage, Binance BTC/USDT 1h 2023 / 2022–2024). The **selling-strategy** post is the clearest-written piece in the batch and its worked examples all recompute, but its disclaimer is at L997 of 1,003, and its scheduler snippet calls `schedule.every(3).months` / `.month`, units the library does not have (`:924–925`).

Verdicts: **0 Ready, 5 Needs revision (AVAV-1/2/3, PL-2, selling), 5 Not ready (PL-1, PL-3, crypto-1/2/3).**

## Per-post scorecard

Scores: A accuracy (×2), C clarity, D depth, V visuals, S structure, F format (1–5); Overall = (2A + C + D + V + S + F) / 7.

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| pl-part1-fundamentals | 482 | 2 | 4 | 4 | 4 | 4 | 4 | 3.4 | **Not ready** | L132/136 "FY2026 ~+12%" — 308/244 = +26% (Planet: +26% to $307.7M); L191–204 FCF drawn as "接近損益兩平/FY27E 目標轉正" but FY26 FCF was +$52.9M; L186/224 warrant noise treated as ongoing though all warrants were redeemed/exercised in the very quarter analysed |
| pl-part2-technical | 423 | 3 | 4 | 3 | 3 | 4 | 4 | 3.4 | Needs revision | L315–316 short interest 32.19M = 9.03% implies a 356M float, but L~70 of part 3 derives ~330M shares outstanding; every MA/RSI/MACD level is "估" with no data source or as-of date (L48–66) |
| pl-part3-valuation | 481 | 2 | 4 | 4 | 4 | 4 | 4 | 3.4 | **Not ready** | L88–113 base DCF "$17" not reproducible: the six FCFs shown + TV $2.77B (✓) + $730.8M cash over 330M shares = ~$7.9; a 10-year extension at the stated margins still gives ~$10. Sensitivity grid L~150 inherits the gap. Weighted $26.2 (L283) and all multiples recompute ✓ |
| avav-part1-fundamentals | 492 | 3 | 4 | 4 | 4 | 4 | 4 | 3.7 | Needs revision | L251/254 backlog table: 3.0 − 1.4 = 1.6 (not 1.5), 1.1 + 3.0 − 1.4 = 2.7 (not 2.6); L212 "長期 FCF 為正" vs FY26 FCF −$140.9M in `avav-2026-10k-deep-dive-zh.md:429`; L64/174 "+77%" is +79% per 10-K cover (50,608,030 vs 28.27M) |
| avav-part2-technical | 422 | 3 | 4 | 3 | 3 | 4 | 4 | 3.4 | Needs revision | L119 "78.6% 跌幅 ~$129" — 417.86 × (1 − 0.786) = $89.4; L17/65 "前 52 週低 $147.75" conflicts with vendor data showing a $142.20 low already in April 2026 (❓) |
| avav-part3-valuation | 480 | 3 | 4 | 4 | 4 | 4 | 4 | 3.7 | Needs revision | L88–113 base DCF "$115" not reproducible from the six-year table (~$106 at 6 yrs, ~$124 at 10 yrs); L76 EV "市值 + 溫和淨負債 ≈ $7.3B" assumes ~$0.2B net debt, the 10-K gives ≈ −$15.5M; football/P-E/EV-Rev arithmetic ✓ |
| stock-selling-strategy | 1,003 | 3 | 5 | 3 | 3 | 4 | 4 | 3.6 | Needs revision | L997 disclaimer is the last section of a 1,003-line finance post (baseline L208); L924–925 `schedule.every(3).months` / `schedule.every().month` — `schedule` has no month unit, raises AttributeError |
| crypto-part1-fundamentals | 1,349 | 2 | 4 | 3 | 3 | 3 | 3 | 2.9 | **Not ready** | No disclaimer (baseline L5); L666 `pd.Series(plus_dm)` has a RangeIndex, `/ atr` aligns on index → all-NaN ADX; L129 "Output: Slippage: 0.08%" — the book shown gives 0.062% |
| crypto-part2-backtesting | 1,196 | 2 | 4 | 4 | 2 | 3 | 3 | 2.9 | **Not ready** | No disclaimer; L894 daily-loss limit on `engine.capital` (cash) — a 95% buy registers as a −95% "loss", halts the day and skips stop-loss/take-profit; L421 sizing `min(0.95C/p, 0.02C/(0.02p))` = 0.95C/p, the "2% risk" never binds; no backtest results reported |
| crypto-part3-production | 1,377 | 2 | 4 | 3 | 2 | 3 | 3 | 2.7 | **Not ready** | No disclaimer; L369–382 Monte Carlo shuffles trades and compares final cumulative P&L — invariant under permutation, so percentile = 0 and every strategy is "likely due to luck"; L462–467 sets `defaultType: 'future'` but points at the spot testnet; L1239 sizes 95% vs L617 10% cap → bot never trades |

Theses as read:
- PL-1: Planet has flipped from a cash-burning space story to a defence-data subscription business with positive adjusted EBITDA, 40%+ growth and a two-year backlog — the GAAP loss is warrant noise.
- PL-2: The stock is in a healthy post-run-up consolidation (low-volume pullback, broad institutional base, 9% short) sitting on the 50% Fibonacci level; wait for MA60.
- PL-3: Five-method weighted fair value ≈ $26 vs $28.42 — "合理偏小貴"; DCF alone says $18, so upside depends on the growth option.
- AVAV-1: The Switchblade franchise is intact (AS +50%, B/B 1.60); the collapse is BlueHalo/SCD execution, SCAR backlog quality and 77% dilution.
- AVAV-2: Perfect bearish MA stack and a new low, but 12% short interest + RSI 30 + the 6/29 print make it a binary squeeze set-up.
- AVAV-3: Weighted fair value ≈ $156 ($140 ex-analysts) vs $142.35 — fairly priced, not cheap; do not add before 6/29.
- Selling strategy: Decide the exit rule at purchase, by position type — opportunity cost for core holdings, trailing stop for momentum, staged profit-taking for event trades.
- Crypto-1: Crypto's 24/7, API-first markets make it the natural venue for systematic trading; here is the data/indicator toolkit.
- Crypto-2: Never trade untested; here is a cost-aware backtester, four strategies, risk controls and metrics.
- Crypto-3: Backtest ≠ live; walk-forward, Monte Carlo, a safe live wrapper, monitoring and Docker get you to production.

## Patterns

### Content quality
- The stock trilogies are thesis-driven and honest in direction: AVAV-3 refuses to call $142 cheap (L292–296: ex-analyst fair value $140 ≈ price) and PL-3 shows DCF $18 against a $28 price without flinching (L113–120). The bear cases are specific (SCAR write-down, 10-month goodwill impairment, warrant/SBC dilution, SAR substitution) rather than boilerplate.
- The quality problem is numerical, not narrative: both valuation posts print a FCF table and then a DCF value that the table does not produce (`pl-part3:88–113`, `avav-part3:88–113`). A reader who checks the arithmetic — the thing the finance skill tells them to do — loses trust in the whole football field.
- The crypto series reads as a code dump with connective prose: 80%+ of each post is Python, and the prose never reports a single result from running it. "Production-ready" (`crypto-1:12`, `crypto-2:1148`) is asserted, not shown.
- The selling post is the one piece that teaches at the reader's level: intuition → rule → worked numbers → psychology, with every example labelled 示意 (L121, L303). Its weak spot is the pretend-production code at the end (L653–730, L905–933), which it does not need.

### Structure (does the house format help or pad?)
- The three-part stock template (fundamentals / technicals / valuation) helps: readers can skip the technical middle, and each part restates price, date and the 6/29 catalyst (`avav-part1:16–17`, `avav-part2:16–17`, `avav-part3:16–17`). The repeated 系列導覽 blocks (top and bottom of all six) and the RKLB-template cross-references ("與 PL 的關鍵差異", "RKLB 範例", `avav-part2:80`, `pl-part2:76`, `pl-part3:135,290`) are scaffolding that leaks.
- The technical-analysis middle parts are the padding: every indicator is "估算" with no source (`pl-part2:48–66,118–160`; `avav-part2:48–66,120–165`), and the "成交量型態（概念示意）" charts (`pl-part2:181`, `avav-part2:183`) draw bars with no data behind them. 400+ lines each for content that reduces to "below all MAs, RSI ~30/42".
- Crypto posts have no section numbering, no diagrams beyond two ASCII tables, and conclusions that are checkbox lists (`crypto-3:1271–1300`). The house ladder (intuition → mechanism → numbers → limits) is absent: the code is the mechanism and there are no numbers.
- The selling post's `## 進階：用程式化交易輔助執行` (L653) breaks the post's register and is where its only hard errors live.

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Sourced and verified: AVAV Q3 $408.0M / $0.64; PL $94.2M / RPO $816M / backlog $906M / $730.8M / FY27 $425–441M / FY26 adj. EBITDA $15.5M; AVAV funded backlog $1.1B (10-K: $1,183.0M). The posts never say where any of these came from — no 資料來源 section in any of the six.
- Invented-looking: AVAV "分析師 16 買進 / 2 持有 / 1 賣出, 中位數 $305" (`avav-part2:263,276`) and PL "7 買進 / 1 賣出, 平均 $39.80" (`pl-part3:345–352`) — no provider, no date, then weighted at 10% into fair value. PL revenue mix "~45/30/25%" (`pl-part1:103`) and "D&I +65% YoY" (`pl-part1:103,234`) are not in Planet's release. Crypto regime frequencies "15/20/25/15/15/10%" (`crypto-1:256–290`) and "90% fail / 9% / 1%" (`crypto-3:1330`) have no source.
- Flip conditions are present and good in the stock posts (`avav-part1:217,331`; `pl-part1:226,398`; `avav-part3:325`) and absent in the crypto series — there is no discussion of when MA-crossover fails (whipsaw in ranging regimes) even though part 1 defined the regimes.
- Consensus numbers are stated as fact: AVAV "預期 $484M / $0.72" (`avav-part1:129,147`) vs a third-party tracker's $475.5M / $0.68 — consensus differs by provider and must be attributed.

### Direction (overlap, gaps, stale topics, category fit)
- AVAV-1/3 overlap the later `avav-2026-10k-deep-dive-zh.md` and already link to it (L19); the two disagree on FCF sign (`avav-part1:212` vs deep dive L429) and dilution (+77% vs +79%). The pre-earnings posts are now historical artefacts; the 2026-09 note handles that, but the contradictions should be fixed or footnoted.
- PL has no 10-K deep dive; PL-1 would be the natural seed for one and its errors (growth %, FCF, warrants) would be caught by the 10-K workflow.
- The crypto series is categorised `engineering` + `finance` and tagged neither "RKK" nor anything series-specific; it has no zh counterpart and no link from the finance category description. Its deployment half (Docker/Grafana with no datasource, `crypto-3:1131–1163`) overlaps the infrastructure cluster without adding to it.
- Selling strategy is a "concept / personal finance" post per the finance skill and fits `finance`; it is dated 2026-01-24 but its examples stop at 2024 — fine as 示意, but the "下次檢視 2026/04/01" entries (L855,866) are already past.

### Accuracy
- Reproducibility failures: PL DCF $17 (~$8), AVAV DCF $115 (~$106), AVAV 78.6% Fib $129 ($89), PL FY26 growth +12% (+26%), AVAV backlog 2.6/1.5 (2.7/1.6), crypto slippage 0.08% (0.062%).
- Stale facts: PL warrants (redeemed Q1 FY27), PL FY26 FCF (+$52.9M, not "接近兩平"), "Settlement: T+2" (US moved to T+1 in May 2024), "FY26 FCF 剛從負轉正" framing for PL in `avav-part1:214`.
- Code that does not do what the prose says: ADX NaN, risk sizing that never binds, daily-loss limit on cash, Monte Carlo invariance, testnet config mismatch, 95%-vs-10% sizing, `schedule` month units, `self.nextOrderId()` (ibapi exposes `nextValidId` as a callback; there is no such method — ❓ depends on reader scaffolding).
- Correct and recomputed: all probability weightings, football-field weights, P/S, EV/Rev and P/E implied prices, Fibonacci levels for PL, MA deviations, market-impact example, Kelly fraction, every number in the selling post's examples.

### Format / front matter
- All ten have complete front matter, valid categories and the `yen` author. The crypto posts carry a `weight:` field the other series do not use.
- readTime drift: crypto 25/21/24 min for 1,349/1,196/1,377 lines (~42/37/43 at 32 lines/min — code-heavy, but still understated); selling 21 min for 1,003 lines (~31).
- Disclaimer placement: six stock posts ✓ first screen; selling post L997 only; crypto none. The crypto posts also lack the English form the skill specifies ("Educational analysis only — not investment advice").
- ASCII blocks exceed 80 columns in several places (`avav-part1:84–96`, `pl-part1:80–92`); the PL/AVAV box-drawn dashboards are ≤ 60 and fine.
- PL-1 L267 "財報日：2026 年 6 月 5 日" — the release was June 4, 2026 (ET); say so or give the Taipei date explicitly.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | pl-part3:88–113 | Base DCF "$17" cannot be produced from the printed FCFs (13/44/83/127/172/215), WACC 11%, g 3%, TV $2.77B, +$730.8M cash, 330M shares → ~$7.9; even a 10-year extension gives ~$10. The $18 weighted value, the −37% "safety margin" and the sensitivity grid all inherit it | Print the full 10-year table (or drop 十年), show PV of FCFs, PV of TV, + cash, ÷ shares, and let the number be whatever it is; re-derive the grid |
| 2 | blocker | pl-part1:132,136 | "FY2026 $308M ~+12%" — the post's own FY25 $244M gives +26% (Planet: +26% to $307.7M). The "成長率從個位數~12% 跳升到 +42%" narrative is built on it | Change to +26% and reframe: growth stepped from 26% to 42%, not from 12% |
| 3 | blocker | pl-part1:186,224; pl-part3:429 | Warrants described as an ongoing quarterly revaluation source, a flip condition ("若認股權證大量行使…") and a dilution risk; the Q1 FY27 release the post analyses says all public warrants were redeemed ($107.8M proceeds) and private warrants exercised cashless | State that the warrant overhang ended in Q1 FY27; the $106.5M loss was its final appearance; drop warrants from the dilution risk list |
| 4 | blocker | pl-part1:191–204 | FCF chart shows FY2026 "接近損益兩平" and FY2027E "目標轉正"; Planet reported FY26 OCF $134.4M and FCF +$52.9M | Replace the conceptual bars with the reported FY24–FY26 OCF/capex/FCF and say FCF is already positive |
| 5 | blocker | crypto-1/2/3 (whole) | Three `finance`-categorised posts about live-money trading with no disclaimer at all (baseline L5–7) | Add the English disclaimer line under the lede of each part |
| 6 | blocker | crypto-3:369–382 | Monte Carlo "skill vs luck" test shuffles trade order and compares *final cumulative P&L*, which is identical for every permutation; percentile is always 0 → every strategy prints "❌ likely due to luck" | Either bootstrap (sample with replacement) or compare drawdown/path statistics; for a luck test, resample from the trade distribution and report the P&L distribution |
| 7 | blocker | crypto-1:666 | `pd.Series(plus_dm)` builds a RangeIndex series; dividing by `atr` (DatetimeIndex) aligns on index and yields all-NaN `plus_di`/`minus_di`/`adx`; `ADXTrendFollowing` (crypto-2:529) therefore never trades | `pd.Series(plus_dm, index=high.index)` (same for `minus_dm`) |
| 8 | major | crypto-2:894; crypto-3:660 | Daily-loss limit computed on cash (`engine.capital`) / USDT balance: a 95% buy registers as a −95% "loss", the day is halted (`continue`), and stop-loss/take-profit checks are skipped for the rest of that day. In the live wrapper a 10% buy trips the 2% limit and blocks the sell too | Measure daily P&L on total equity (cash + mark-to-market positions) |
| 9 | major | crypto-2:421 (and :468) | "Risk 2% per trade" sizing = `min(0.95C/p, 0.02C/(0.02p))` = 0.95C/p — the risk term equals 100% of capital and never binds; every trade is all-in | Size as `risk_per_trade / (stop_distance)` with an ATR stop, and say so |
| 10 | major | crypto-3:462–467, 1239 vs 617 | Testnet config sets `defaultType: 'future'` but overrides URLs with the *spot* testnet (`testnet.binance.vision`); ccxt has `set_sandbox_mode(True)` for this. `main.py` sizes at 95% of USDT against a 10% `max_position_size`, so every order is rejected | Use `exchange.set_sandbox_mode(True)` with spot; size `0.1 × balance` in `main.py` |
| 11 | major | avav-part3:88–113,154 | Base DCF "$115" not reproducible from the six-year table (~$106; ~$124 with 10 years); the WACC-10% sensitivity row (98/105/115/126/140) recomputes to ~95/100/106/112/120 while the 8% row matches | Same fix as #1: show all years and the PV steps |
| 12 | major | avav-part1:212,251,254; avav-part2:119 | "長期 FCF 為正" contradicts FY26 FCF −$140.9M (deep dive L429); 3.0 − 1.4 ≠ 1.5 and 4.1 − 1.4 ≠ 2.6; 78.6% retrace from $417.86 is $89 not $129 | Correct the arithmetic; cite the 10-K backlog ($1,183.0M funded / $1,457.7M unfunded at 2026-04-30) in the 2026-09 note |
| 13 | major | avav-part2:263,276; pl-part3:345–352; avav-part1:129,147 | Analyst counts/targets and consensus estimates given without provider or date, then weighted 10% into fair value; a third-party tracker gives AVAV Q3 consensus $475.5M / $0.68, not $484M / $0.72 | Name the provider and as-of date, or drop the analyst row from the weighting |
| 14 | major | stock-selling:997; :924–925; :669 | Disclaimer last in a 1,003-line finance post; `schedule.every(3).months` and `schedule.every().month` are not units the library has (seconds…weeks, weekday names only) → AttributeError; `self.nextOrderId()` is not an ibapi method | Move the disclaimer under the lede; use `schedule.every(90).days` / cron; store the id from the `nextValidId` callback |
| 15 | minor | crypto-1:31,72–78,129 | "Settlement: T+2" (US equities T+1 since 2024-05-28); order-book diagram lists asks 43,150/43,140/43,130 with 43,130 also the best bid (crossed book, and "Best Ask (Lowest Sell)" labels the highest); slippage example prints 0.08% for a book giving 0.062% | T+1; order asks ascending from 43,150 upward; fix the printed output |

## Recommendations

1. **Re-derive every DCF from a printed 10-year table and show the PV steps (PL-3, AVAV-3).** WHY: the finance skill's rule is "recompute every derived number"; today the headline DCF of both posts is unreproducible, which poisons the football field and the verdict. HOW: add rows FY33–FY36, a line "PV(FCF) + PV(TV) + 現金 − 債務 = EV; ÷ 股數 = $X", recompute the 5×5 grid from the same function, and label the result 計算值.
2. **Bring PL-1 up to the Q1 FY27 release it claims to analyse.** WHY: three of its load-bearing statements (growth %, FCF status, warrant overhang) are wrong or stale against the June 4 release. HOW: FY26 +26%, FY26 FCF +$52.9M / OCF $134.4M, warrants fully redeemed; add a 資料來源 block (FY26 8-K 2026-03-19, Q1 FY27 8-K 2026-06-04).
3. **Add the disclaimer to the crypto series and move the selling post's to the top.** WHY: rubric blocker; the crypto posts hand readers a live-trading bot. HOW: one blockquote under the lede, English form from the finance skill; in the selling post move L997–999 to after L15.
4. **Fix the five crypto code defects and run the code once.** WHY: the series' only claim is "production-ready", and the ADX, sizing, daily-loss, Monte Carlo and testnet bugs mean nothing in it works as described. HOW: apply findings #6–#10; then publish one real backtest result block per strategy with data source, period, fees, slippage and the metrics the post defines.
5. **Report numbers for the backtests or stop calling them backtests.** WHY: a reader cannot judge a strategy post with zero results; the code already prints `total_return`, `sharpe`, `max_drawdown`. HOW: a table per strategy (Binance BTC/USDT 1h, 2023-01-01→2024-01-01, 0.1% + 0.05%), plus the walk-forward summary.
6. **Source and date every market/sentiment figure in the technical parts (PL-2, AVAV-2).** WHY: 52-week lows, short interest, analyst counts and MA levels are presented as facts with "估" or nothing; a vendor shows a $142.20 AVAV low in April 2026 that contradicts "前低 $147.75". HOW: one line per block — provider, as-of date — or convert the parts to a short "what to watch" section.
7. **Reconcile the AVAV trilogy with the AVAV 10-K deep dive.** WHY: the two now disagree on FCF sign, dilution and backlog, and both link to each other. HOW: extend the 2026-09 note in AVAV-1/3 with the three corrected figures (FCF −$140.9M, +79%, backlog $1,183.0M / $1,457.7M) and keep the pre-earnings analysis as-is.
8. **Attribute or remove consensus data.** WHY: "$484M / $0.72" and "$305 中位數" drive the "墜落天使 vs 後照鏡" argument; unsourced consensus cannot be checked and differs by vendor. HOW: name the provider and date, or state only the company's own guidance.
9. **Trim the selling post's code appendix.** WHY: the post is strong as a method essay; its IBKR/yfinance/schedule code adds two errors and no insight. HOW: keep a 10-line trailing-stop pseudocode, drop the rest or link to a repo.
10. **Give the crypto series the house ladder and a series index.** WHY: no numbering, no diagrams that carry information, no "when it breaks", no zh counterpart or series nav. HOW: number sections, add a regime-vs-strategy failure table (part 1 already defines the regimes), add a 系列導覽/Series nav block in all three.

## Verified / unverified claims

- ✅ avav-part1:129 / :275 — Q3 FY2026 revenue $408M (AeroVironment release 2026-03-10: $408.0M, +143%).
- ✅ avav-part1:147 — Q3 EPS $0.64 (third-party tracker; release excerpt lacks EPS).
- ❓ avav-part1:129,147 — consensus $484M / $0.72: tracker shows $475.5M / $0.68; provider not named.
- ✅ avav-part1:249 — funded backlog "$1.1B 創高" (10-K: $1,183.0M at 2026-04-30 vs $726.6M).
- ❌ avav-part1:251,254 — "有效 unfunded ~$1.5B" / "實質 backlog 約 $2.6B": 3.0 − 1.4 = 1.6; 4.1 − 1.4 = 2.7. (10-K unfunded at 2026-04-30: $1,457.7M, i.e. post-SCAR termination.)
- ❌ avav-part1:64,174,189 — "+77% 稀釋": 50,608,030 / 28.27M = +79% (10-K cover; deep dive L36).
- ❌ avav-part1:212 — "長期 FCF 為正": FY2026 OCF −$78.4M, FCF −$140.9M (deep dive L429; 10-K).
- ✅ avav-part1:19 — FY2026 revenue $1,976.8M (10-K L3945).
- ✅ avav-part1:62 — BlueHalo closed 2025-05-01, all-stock; ❓ "$41 億" vs deep dive "$34.8 億" purchase consideration.
- ✅ avav-part2:17 — 52-week high $417.86 (multiple vendors); ❓ "前 52 週低 $147.75" — one vendor shows $142.20 as of 2026-04-24.
- ❌ avav-part2:119 — "78.6% 跌幅 ~$129": 417.86 × 0.214 = $89.4. ✅ :118 61.8% → $160.
- ✅ avav-part2:304,315 — 4.62M short / 12.09% implies a 38.2M float, consistent with ~50.6M outstanding. ❓ undated.
- ❓ avav-part2:263,276 — "16/2/1, 中位數 $305, 低 $235, 高 $450": no provider/date.
- ✅ avav-part3:113–122 — 0.30×180 + 0.45×115 + 0.25×70 = $123.25; +15.5% / −13.4% ✓.
- ❌ avav-part3:88–113 — base DCF $115: table yields ~$106 (6 yrs) / ~$124 (10 yrs); L154 WACC-10% row recomputes 95/100/106/112/120.
- ✅ avav-part3:190–198 — EV/Rev implied $114 / $161 / $232 at 2.5/3.5/5.0× with ~$0.2B net debt ✓; ❓ net debt ≈ −$15.5M per 10-K, so EV ≈ $7.19B not $7.3B (L76).
- ✅ avav-part3:213–225 — P/E 22/30/40 × $4.0/4.3/4.5 = $88/$129/$180; fwd P/E 31.6–35.6× ✓; PEG 1.68 ✓.
- ✅ avav-part3:272–280 — weighted 36.90 + 40.00 + 25.80 + 22.50 + 30.50 = $155.70; ex-analyst ≈ $139 ✓; L361–365 +19% / +86% / −30% ✓.
- ✅ pl-part1:267–280 — Q1 FY27 revenue $94.2M +42%, RPO $816M +81%, backlog >$906M +72%, net loss ($138.9M) incl. ($106.5M) warrant revaluation, cash $730.8M (Planet release 2026-06-04).
- ✅ pl-part1:135 — FY27 guide $425–441M (release) ; ✅ :160–162 adj. EBITDA FY25 ($10.6M) → FY26 $15.5M, FY27 guide $0–10M.
- ❌ pl-part1:132,136 — FY26 "~+12%": 307.7 / 244.4 = +26%.
- ❌ pl-part1:191–204 — FY26 FCF "接近損益兩平": reported +$52.9M.
- ❌ pl-part1:186,224; pl-part3:429 — warrants ongoing: all public warrants redeemed and private warrants exercised in Q1 FY27 (release).
- ❓ pl-part1:103,234 — "D&I +65% YoY", mix 45/30/25%: not in the release.
- ❓ pl-part1:267 — "財報日 6 月 5 日": release dated June 4, 2026 ET.
- ✅ pl-part2:128–134 — Fib 23.6/38.2/50/61.8% = $40.85/$34.10/$28.64/$23.18 ✓; L62–66 MA deviations −5.9/−13.9/−9.8% ✓.
- ❓ pl-part2:268–270,313–316 — 432 holders, 261.7M shares, 32.19M short = 9.03% (implies 356M float vs ~331M shares derived at pl-part3:70); no provider.
- ❌ pl-part3:88–113 — base DCF $17: ~$7.9 from the table (+cash), ~$10 extended; TV $2.77B ✓; prob-weighted $18.00 ✓ as arithmetic; +58% / −37% ✓.
- ✅ pl-part3:178–200 — P/S 21.7× fwd / 30.5× trailing; $16/$26/$37 ✓; EV $8.67B, 20.0× ✓; $15/$26/$35 ✓.
- ✅ pl-part3:272–287 — weighted 3.60 + 6.50 + 6.50 + 5.60 + 3.98 = $26.18; +8.5% ✓; L370 +2% / +62% / −44% ✓.
- ❓ pl-part3:345–352 — "7 買進 / 1 賣出, 平均 $39.80, $22–$53": no provider/date.
- ✅ selling:121–150, 303–330, 795–820 — NVDA 220→880 = 4×; PLTR 15→20.5 = +36.7%; event trade 10,000 + 7,500 + 4,000 = 21,500 (+115%), 200 × 180 = 36,000 (+260%); TSM +55.6%; PLTR 22 × 0.75 = 16.5 ✓.
- ❌ selling:924–925 — `schedule.every(3).months`, `schedule.every().month`: library units are seconds/minutes/hours/days/weeks and weekday names only (schedule reference).
- ❓ selling:669 — `self.nextOrderId()`: not an `EClient` method; ibapi delivers the id via the `nextValidId` callback.
- ✅ selling:711 — yfinance `info['targetMeanPrice']`, `['currentPrice']` are real keys.
- ✅ crypto-1:146 — market impact 0.1 × √(1e6/5e9) = 0.141% ✓; L~70 spread 20/43,140 = 0.046% ✓; row totals (0.5 × 43,150 = 21,575 …) ✓.
- ❌ crypto-1:129 — "Slippage: 0.08%": 10 BTC across the printed book = avg 43,176.9 → 0.062%.
- ❌ crypto-1:72–78 — asks listed 43,150 > 43,140 > 43,130 with "Best Ask" on 43,150 and best bid 43,130 (crossed).
- ❌ crypto-1:31 — "Settlement: T+2" for US stocks (T+1 since 2024-05-28).
- ❌ crypto-1:666 — ADX `pd.Series(plus_dm)` index misalignment → NaN (pandas aligns on index; not executed locally — pandas absent — but deterministic).
- ❓ crypto-1:443 — `datetime.fromtimestamp(orderbook['timestamp'] / 1000)`: Binance REST depth returns no timestamp; ccxt sets `None` → TypeError.
- ✅ crypto-1:318–470 — ccxt `fetch_ohlcv/fetch_order_book/fetch_trades`, `enableRateLimit`, `options.defaultType` are real; ✅ crypto-3:437–560 — `fetch_balance/fetch_ticker/create_market_order/create_limit_order/cancel_order/fetch_order` real.
- ✅ crypto-2:131–132, 474; crypto-3:323 — costs 0.1% + 0.05%, data Binance BTC/USDT 1h 2023 / 2022–2024 are stated; ❌ no backtest result (return, Sharpe, drawdown) is reported anywhere in the three posts.
- ✅ crypto-2:560 — Kelly (0.55 × 1.5 − 0.45) / 1.5 = 0.25 ✓; L280 entry commission charged to trade ✓ (good).
- ❌ crypto-2:421 — 2%-risk sizing resolves to 95% of capital; ❌ :894 daily-loss on cash; ❓ :708 pairs strategy signature differs from base class and the engine is long-only, so it cannot be backtested as written.
- ❌ crypto-3:369–382 — Monte Carlo final-P&L invariance (pure arithmetic: Σpnl is permutation-invariant).
- ❌ crypto-3:462–467 — `defaultType: 'future'` + spot testnet URL; ccxt provides `set_sandbox_mode`.
- ❌ crypto-3:1239 vs :617 — 95% sizing vs 10% cap → every live order rejected.
- ❓ crypto-3:1330 — "90% / 9% / 1%" retail quant outcomes: no source.
