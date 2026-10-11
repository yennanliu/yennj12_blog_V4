# B14-industry-map-semiconductor — overview + 14-part semiconductor industry map

Reviewed 2026-10-11. 15 Traditional-Chinese finance posts (5,033 lines), all dated 2026-07-19 with
2026-09 editorial notes in Parts 5/6/7/8. Every post was read in full; every bottleneck-score average,
market-share bar set and value-capture chart was recomputed; headline figures were checked against
TrendForce, SEMI, WSTS, Synergy, SIA, NVIDIA's 8-K and TSMC's Q4-2025 results via WebSearch.
Mechanical baseline (`inputs/mechanical-baseline.txt`) has **no entries** for these files;
`review_posts.py` on the 15 files returns 0 errors / 0 warnings and `check_links.py --content-only` is
clean. All six 10-K cross-links (AMZN/GOOGL/ORCL/META/NVDA/AMD) resolve to existing posts.

## Batch summary

This is the most consistent batch I have seen in the audit: one template (位置 → 做什麼 → 玩家 →
瓶頸分數 → 利潤池 → 上下游 → 風險 → 價值遷移 → 投資點子 → 反轉條件 → SIGNAL box) executed 14
times with real content behind every section, a disclaimer in the first screen of all 15, a genuine
bear/risk section and thesis-invalidation list in every post, and value-capture charts that match
the overview exactly wherever they are repeated (Parts 1, 6, 13, 14). The `industry-map` skill
contract (chain map, chokepoint scoring, margin pools, value migration, concentration risk,
layer-ranked ideas with a named "非顯性節點" second-order pick) is honoured in every part. The
batch's weakness is sourcing: not one figure is cited to SIA/WSTS/SEMI/TrendForce or a filing —
every number carries the blanket label「公開產業常識的概估值(截至 2026 年初)」, including figures
that are published exactly (TrendForce foundry share, SEMI WFE, company gross margins). Where that
label hides stale data it bites: Part 5's foundry share table (TSMC ~60–65%, Samsung ~10–13%,
L82–83) is 2023-vintage against TrendForce's FY2025 69.9% / 7.2%; Part 13's cloud share has Azure
at 22–25% vs Synergy's 20–21%; Part 14 relabels SIA's "PC/Computer" and "Communications" buckets as
「資料中心/企業 AI」and「手機/PC」(L83–84), which is the premise of its "all growth comes from one
segment" claim. A second pattern is arithmetic nudging: five of the fourteen bottleneck averages are
reported ~0.25 away from the mean of the four factors shown (Parts 1, 4, 11, 12, 13), and every
"加權" layer score (Parts 2, 3, 7, 10) uses a weight that is never stated. Verdicts: **12 Ready**
(overview, Parts 1–4, 6–12), **3 Needs revision** (Parts 5, 13, 14), 0 Not ready.

## Per-post scorecard

Finance weighting: Overall = (2A + C + D + V + S + F) / 7.

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| value-chain-zh.md (overview) | 357 | 4 | 5 | 4 | 5 | 5 | 4 | 4.4 | Ready | L209 HBM bottleneck 7 vs Part 8's 8.25; revision note L218 lists Parts 2/11/10/4 but not Part 8 |
| part1-silicon-wafer-zh.md | 326 | 4 | 5 | 4 | 4 | 4 | 4 | 4.1 | Ready | L137 "≈ 6.0" — the four factors shown (6,5,6,8) average 6.25 |
| part2-chemicals-photoresist-zh.md | 323 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Ready | L142 "加權概估 6.5" from 8.75/4.5 sub-scores with no weight stated; L117 DuPont ">80% 墊市佔" unsourced |
| part3-eda-ip-zh.md | 320 | 4 | 5 | 4 | 4 | 4 | 4 | 4.1 | Ready | L128 "加權平均 約 8.0" from 8.5/7.0 (simple mean 7.75), weight unstated; L112 semis "約 7,000 億 (2025)" vs WSTS $772B |
| part4-fab-equipment-zh.md | 340 | 4 | 5 | 5 | 5 | 4 | 4 | 4.4 | Ready | L143 "綜合 ≈ 9.3" from 9.8/8.5 (mean 9.125); L84 WFE "~1,000 億" vs SEMI 2025 $110.8B (acceptable) |
| part5-foundry-zh.md | 338 | 3 | 5 | 4 | 4 | 4 | 4 | 3.9 | Needs revision | L82–83 TSMC ~60–65% / Samsung ~10–13% total-foundry share is stale: TrendForce FY2025 69.9% / 7.2%; L175 GM "55–59% (2024–25)" vs FY2025 59.9%, Q4 62.3%; L189 "400 億 capex 2024–25" (2024 was $29.8B) |
| part6-gpu-design-zh.md | 335 | 4 | 5 | 4 | 4 | 4 | 4 | 4.1 | Ready | L84 NVDA GM "~73–75%" — FY2026 GAAP 71.1% (FY2025 75.0%, Q4 FY26 75.0%); L84 "AI 訓練 ~90%" unsourced |
| part7-ic-design-zh.md | 330 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Ready | L155 "加權 ≈ 6.5" from 7.75/5.75 (mean 6.75); L106 AVGO custom-ASIC "~65–70%" unsourced; 13 full-width commas mixed with half-width |
| part8-memory-zh.md | 324 | 4 | 5 | 4 | 4 | 4 | 4 | 4.1 | Ready | L86–87 DRAM chart (Samsung 40% > Hynix 35%, "2026 初") sits under the L21 note saying Hynix overtook Samsung in DRAM revenue in 2025 — chart not updated with the note |
| part9-idm-analog-zh.md | 348 | 4 | 5 | 4 | 4 | 4 | 4 | 4.1 | Ready | L99 TI analog "約 19%" / ADI 12–13% are IC Insights **2021** figures presented as 截至 2026 年初 |
| part10-osat-zh.md | 347 | 4 | 5 | 4 | 4 | 4 | 3 | 4.0 | Ready | L155 "整層綜合(加權後)≈ 5.5" from 3.75/8.75 (mean 6.25), weight unstated; L313–315 duplicated 系列導覽 heading (H2 then H3) |
| part11-networking-zh.md | 323 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Ready | L144 "6.5" — factors (6,6,7,8) average 6.75; the overview's revision note (L218) then propagates 6.5 |
| part12-system-oem-zh.md | 332 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L130 "(2+2+3+4)/4 ≈ 2.5" is 2.75; overview L214 says 2, SIGNAL box says 2.5 — three values for one score |
| part13-cloud-csp-zh.md | 324 | 3 | 4 | 4 | 4 | 4 | 4 | 3.7 | Needs revision | L75/L84 Azure "~22–25%" and L85 Google Cloud "~11–12%" vs Synergy Q3-25 29/20/13 and Q4-25 28/21/14; L112 "平均 = 6.25 → 瓶頸分數 6.0" rounds down with no reason; 102 full-width commas (only post in series using them) |
| part14-end-demand-zh.md | 366 | 3 | 4 | 4 | 4 | 5 | 4 | 3.9 | Needs revision | L83–84 end-use split labels SIA's PC/Computer (34.9%) as「資料中心/企業 AI」and Communications (33%) as「手機/PC」; consumer (9.9%) and industrial (8.4%) collapsed into "三個 12%"; L78 semis "約 7,000 億" vs WSTS Autumn-2025 $772B |

## Patterns

### Content quality
- Every post states a real thesis in its 4-line opening quote and a「一句話定位」that names the direction of pricing power (e.g. part5 L46, part12 L46, part13 L40). None of the 15 is thesis-less.
- The teaching is strong where it explains a mechanism rather than a ranking: part12 L160–185 (營收 ≠ 利潤, GPU pass-through worked example), part8 L48–56 (why HBM is "準客製" and eats 3× the wafers), part9 L186–200 (TI's 300mm bet with the 2.3×/40% arithmetic), part4 L147–152 (排隊/綁定/進步稅).
- Honesty is above the site's finance average: part8 L21 upfront note that the post's own premise is outdated; part14 L232 "AI 是真的,泡沫也是真的"; part10 L267 "別把整個封測業當 AI 股買"; part1 L185–187 the layer is explicitly "沒有收費站".
- Weakest prose is the shared boilerplate: the 評分指引 line, SIGNAL box and 參考來源 block are identical across 15 posts and add nothing after the first reading.

### Structure
- The nine-section template fits layers with a supply side (Parts 1–12) well; Part 14 correctly swaps 玩家 for a demand-segment table and 瓶頸分數 for a 韌性分數 (L109–117, all four averages recompute), which shows the author adapting rather than padding.
- Boilerplate is ~45 lines per post (系列導覽 ~25 + 參考來源 ~8 + SIGNAL + 評分指引 + closing reminder), ≈14% of each part. The nav block is also duplicated in the overview (L34–56) which already links every part.
- Heading levels for the nav drift: `###` in most parts, `##` in part4 L312, and both `##` and `###` stacked in part10 L313–315.
- Parts 7 and 11 explicitly reconcile their overlap (Broadcom/Marvell) with a 分工說明 (part7 L48, part11 L110–120) — a good pattern the other repeated topics (CoWoS in Parts 5/6/8/10, CSP capex in 13/14) do not use.

### Depth
- Flip conditions are real and specific in every post (part2 L150 "若某家 fab 成功扶植第二供應商…"; part6 L240 "NVIDIA 資料中心毛利跌破 ~70% 且回不去"; part12 L280 "液冷方案標準化、大家都會做,毛利又會被打回原形").
- Numbers are plentiful but almost entirely unsourced: 0 of 15 posts cites SIA/WSTS/SEMI/TrendForce/Counterpoint/Synergy or a filing page; the only named data series are SEMI MSI (part1 L75) and "WSTS 口徑" (part14 L78). The 概估 label is applied uniformly to invented-looking and published figures alike, so a reader cannot tell which is which.
- Weights behind "加權" scores are never shown (part2 L142, part3 L128, part7 L155, part10 L155), and plain averages are nudged by ±0.25 in five posts (part1 L137, part4 L143, part11 L144, part12 L130, part13 L112). Each is minor; together they make the 0–10 scores look tuned rather than computed.
- Market-share bars are internally consistent: every bar set recomputes to 100 ± 2 (part1 L92–97, part2 L97–102, part3 L83–86, part4 L102–107, part7 L117–120, part8 L86–89).

### Direction
- Category fit is exact: all 15 are `["all","finance"]`, tagged InvestSkill/investing; "finance/business" split is not needed.
- The series is the site's best "sector map" asset and the right companion to the 10-K posts it links; the only gap in the chain is **power/cooling/electricity**, which the overview (L256–262), part9 (L229–237), part12 (L288) and part14 (L256) all name as "the next scarcity" but no part owns.
- Stale-data risk is structural: posts are dated 2026-07-19, figures stamped 截至 2026 年初, and 2026-09 notes patch Parts 5/6/7/8 — so three vintages coexist. Parts 13/14's "2026 capex 上看 5,000 億+" (part13 L200, part14 L204) is already superseded by their own parenthetical ("各家財測合計已明顯超過此數"); FT's running tally is ~$725B.
- The 4-CSP capex paragraph is pasted near-verbatim in part13 L200 and part14 L204; the HBM/CoWoS "二階瓶頸" point appears in six posts.

### Accuracy
- Verified correct: EUV >$150M / High-NA >$350M (overview L127, part4 L76); SK hynix HBM ~50%+ (part8 L94; TrendForce 2025 52.3%); WFE ~$100B (part4 L84; SEMI $110.8B); TSMC 2026 capex "指引更高" (part5 L189; $52–56B); Meta 2026 capex $115–135B (part13 L200); Wolfspeed Chapter 11 2025 (part1 L254); JIC/JSR ~$6.4B (part2 L124); OpenAI–AMD 6 GW and OpenAI–Broadcom 10 GW notes (part6 L107, part7 L126); US ~10% and NVIDIA $5B Intel stakes, Samsung–Tesla $16.5B (part5 L131); 4-CSP 2025 capex $350–400B (FT tally ~$410B).
- Stale or mis-stated: part5 L82–83 foundry share (see scorecard); part5 L175 GM range; part13 L84–85 cloud share; part14 L78 market size; part9 L99 TI/ADI share vintage; part6 L84 NVDA GM range vs FY2026 71.1%.
- Mislabelled taxonomy: part14 L83–84 — SIA's 2024 end-use buckets are PC/Computer 34.9%, Communications 33%, Automotive 12.7%, Consumer 9.9%, Industrial 8.4%, Government 1%. The post's "資料中心/企業 AI 34%" is the PC/Computer bucket (which contains PCs) and "手機/PC 30%" is Communications (which contains no PCs). The "成長全部來自一個板塊" conclusion (L103) survives in spirit but the labels are wrong.
- Internal consistency across the 15 is good for the headline figures (TSMC GM 55–59% in overview/part3/part5/part10; NVDA 70–75% in overview/5/6/9; OSAT 15–25% and OEM 10–15% everywhere; EUV price in overview/part4). Drift: TSMC GM "~55%" in part4 L174, part7 L182, part9 L182 vs "~57%" part5 L14 vs "55–59%" elsewhere; OEM bottleneck 2 / 2.5 / 2.75 (overview L214, part12 SIGNAL, part12 L130).

### Format / front matter
- Front matter complete on all 15; descriptions 90–148 chars, all within 50–160.
- `readTime: "16 min"` on all 14 parts and 13 on the overview against ~10–11 min of content at 32 lines/min (checker threshold not tripped, but every post overstates by ~50%).
- part13 is written with full-width punctuation (，、（）— 102 full-width commas) while the other 14 use half-width; part7 mixes 13 full-width commas into half-width prose.
- Internal links are root-absolute without the sub-path everywhere; no hard-coded baseURL; Mermaid blocks render (one per post, plus the overview's two).
- The 2026-09 notes (part5 L131, part6 L107, part7 L126, part8 L21) are dated after the posts' 2026-07-19 `date`, which is fine, but the figures stamp "截至 2026 年初" predates the post date by six months — a reader has no single "as-of" to trust.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | major | part5-foundry-zh.md:82–83 | TSMC "~60–65%" / Samsung "~10–13%" total-foundry share is 2023-vintage; TrendForce FY2025: TSMC 69.9%, Samsung 7.2% (Q3-25 71.0%, Q4-25 70.4%) | Replace with TrendForce FY2025 figures and cite "TrendForce, 2026-03"; part10 L113 "台積電一家 >60%" can stay |
| 2 | major | part14-end-demand-zh.md:83–84, 91 | End-use split relabels SIA's PC/Computer (34.9%) as 資料中心/企業 AI and Communications (33%) as 手機/PC; consumer 9.9% + industrial 8.4% + government 1% become "三個 12%" | Use SIA 2025 Factbook categories as-is (PC/Computer, Communications, Auto, Consumer, Industrial, Gov) with their 2024 shares, then explain that data-centre AI sits inside PC/Computer and smartphones inside Communications |
| 3 | major | all 15 (e.g. overview:19, part5:19, part13:19) | No figure in the series is cited to a named source; "公開產業常識的概估值" is applied equally to published numbers (TrendForce share, SEMI WFE, company GMs) and to the author's own 0–10 scores | Add a 資料來源 list per post naming SIA/WSTS, SEMI, TrendForce, Counterpoint, Synergy and the relevant 10-K pages; keep 概估 only for the author's scores and cost splits |
| 4 | major | part13-cloud-csp-zh.md:75, 84–85 | Azure "~22–25%" and Google Cloud "~11–12%" vs Synergy Q3-2025 AWS 29 / Azure 20 / GCP 13 (Q4-25: 28/21/14) | Use Synergy Q4-2025 shares, date-stamp them, and drop the Azure range that no 2025 quarter supports |
| 5 | minor | part5-foundry-zh.md:14, 175, 189 | GM "~57%" / "55–59% (2024–25)" vs TSMC FY2025 59.9% and Q4-25 62.3%; capex "400 億美元級別 (2024–25)" — 2024 was $29.8B, 2025 $40.9B | State FY2024 56.1% / FY2025 59.9% and capex $29.8B / $40.9B / 2026 guide $52–56B explicitly |
| 6 | minor | part1:137, part4:143, part11:144, part12:130, part13:112 | Reported bottleneck averages differ from the mean of the four factors shown (6.25→6.0, 9.125→9.3, 6.75→6.5, 2.75→2.5, 6.25→6.0) | Print the computed mean to two decimals, or change a factor so the stated score is the real average |
| 7 | minor | part2:142, part3:128, part7:155, part10:155 | "加權" layer scores with no weight stated (e.g. 3.75 and 8.75 → 5.5 implies ~65/35 traditional/advanced) | State the weight and what it represents (revenue share of the sub-segment) |
| 8 | minor | value-chain-zh.md:209, 218 | Overview HBM bottleneck 7 vs part8 L138 8.25; the L218 revision note reconciles Parts 2/4/10/11 but omits Part 8 (and Parts 7, 9, 13, which are absent from the chart) | Extend the note to HBM 8.25 (Part 8) and add rows for IC 設計-其他 6.5, IDM 6.0, CSP 6.0 so the chart covers all 14 layers |
| 9 | minor | part8-memory-zh.md:84–89 vs 21 | DRAM chart (Samsung ~40% > Hynix ~35%, "2026 初") is contradicted by the post's own 2026-09 note that Hynix overtook Samsung in DRAM revenue in 2025 | Either relabel the chart "2024, by bit" or update it to 2025 revenue share and say which basis |
| 10 | minor | part9-idm-analog-zh.md:99 | TI "約 19%" / ADI "12–13%" analog share are IC Insights 2021 numbers under a 截至 2026 年初 stamp | Cite "IC Insights, 2021 analog ranking" or find a 2024 figure |
| 11 | minor | part6-gpu-design-zh.md:84 | NVDA GM "~73–75%": FY2025 GAAP 75.0%, FY2026 GAAP 71.1% (H20 charge), Q4-FY26 75.0% | "FY2025 75.0% / FY2026 71.1%(含 H20 減損)" from the 10-K/8-K |
| 12 | minor | part3:112, part14:78 | Semis market "約 7,000 億 (2025)"; WSTS Autumn-2025 forecast is $772B (2024 actual $630.5B ✓) | "WSTS 2025-12 預估 2025 年 7,720 億美元" |
| 13 | minor | part13 (whole), part7 (13 places) | Full-width punctuation in part13 (102 full-width commas) and mixed in part7; the other 13 posts use half-width | Normalise to half-width to match the series |
| 14 | minor | part10-osat-zh.md:313–315; part4:312 | Duplicate 系列導覽 heading (H2 then H3); part4 uses H2 where the others use H3 | One `###` heading, consistent across parts |
| 15 | minor | all 15, front matter | readTime 16 min on ~10–11 min of content (13 vs 11 for the overview) | Set 10–11 min |

## Recommendations

1. **Add a 資料來源 block per post and cite inline where a published number exists.** WHY: the finance rubric weights accuracy double and rule 1 is "sourced numbers only"; today a reader cannot distinguish TrendForce's 69.9% from the author's 9/10 score. HOW: one bullet per external figure — "TrendForce 2025 foundry ranking (2026-03)", "SEMI mid-year 2025 WFE forecast", "WSTS Autumn 2025", "Synergy Q4-2025", "SIA 2025 Factbook", "NVDA FY2026 8-K", "TSMC 4Q25 results" — and move 概估 to the scores and illustrative cost stacks only.
2. **Refresh the three stale tables in one pass (Parts 5, 13, 14).** WHY: these are the figures a reader would quote, and they are off by 5–10 points of share or mislabelled. HOW: Part 5 L82–83 → TrendForce FY2025; Part 13 L83–85 → Synergy Q4-2025; Part 14 L82–90 → SIA 2024 end-use with the real category names; stamp each table with the data date.
3. **Make the 0–10 arithmetic exact and the weights visible.** WHY: five nudged averages and four unstated weights undermine the series' strongest device (the comparable score across 14 layers). HOW: print two-decimal means; for weighted layers state "以子市場營收比重 65/35 加權"; recompute the overview chart (L200–216) from the parts.
4. **Give the series one "as-of" date and one changelog.** WHY: 2026-07 posts, 2026-初 figures and 2026-09 notes coexist, and the capex paragraph in 13/14 is already superseded by its own parenthetical. HOW: a single "數據截至 YYYY-MM" line under each disclaimer, and update the body figure when a 2026-09 note changes it (Part 8 DRAM chart, Parts 13/14 capex).
5. **Extend the overview's chokepoint chart to all 14 layers and reconcile it with the parts.** WHY: the overview is the entry point and currently omits IC 設計-其他, IDM, CSP and carries an un-noted HBM 7 vs 8.25. HOW: regenerate L200–218 from the parts' final scores; delete the "以分篇為準" caveat once they agree.
6. **Write the missing Part 15: 電力 / 散熱 / 資料中心基礎設施.** WHY: four posts name power/cooling as "the next scarcity" and the 二階 idea in Parts 9/12/14, but no part maps that layer (utilities, transformers, liquid cooling, Vertiv/台達/MPWR). HOW: same template; it also gives the "value migrates upstream to new scarcity" thesis a concrete node.
7. **Trim boilerplate to a partial or a shorter block.** WHY: ~45 lines/post (14%) is nav + references + 評分指引 repeated verbatim, which pads readTime and the series. HOW: keep the SIGNAL box; replace the 25-line nav with a 3-line "上一篇 / 總覽 / 下一篇" and a link to the overview's full index; drop the 評分指引 line after the overview.
8. **Normalise typography and headings.** WHY: Part 13's full-width punctuation and Part 10's double heading are the only visible format slips in an otherwise uniform series. HOW: half-width punctuation in 13 and 7; one `###` nav heading; readTime 10–11 min.

## Verified / unverified claims

- ✅ value-chain-zh.md:127, part4:76 — EUV "逾 1.5 億美元", High-NA "逾 3.5 億美元" (press: NXE:3800E ~$180M; EXE:5000 ~€350M/$380M)
- ✅ part8-memory-zh.md:94 — SK hynix HBM "領先 ~50%+" (TrendForce 2025 projection 52.3% / Samsung 28.7% / Micron 19%)
- ✅ part4-fab-equipment-zh.md:84 — WFE "~1,000 億美元 (2025)" (SEMI mid-2025: $110.8B; acceptable as 概估)
- ✅ part5-foundry-zh.md:189 — TSMC 2026 capex "指引更高" ($52–56B vs $40.9B in 2025)
- ✅ part5-foundry-zh.md:131 — US ~10% (2025-08) and NVIDIA $5B (2025-09) Intel stakes; Samsung–Tesla AI6 ~$16.5B (2025-07)
- ✅ part6-gpu-design-zh.md:107 — OpenAI–AMD ~6 GW multi-generation deal (2025-10)
- ✅ part7-ic-design-zh.md:126 — OpenAI–Broadcom ~10 GW custom accelerators (2025-10)
- ✅ part13-cloud-csp-zh.md:200 — Meta 2026 capex guide $115–135B; 4-CSP 2025 capex "3,500–4,000 億" (FT tally ~$410B)
- ✅ part14-end-demand-zh.md:78, 103 — 2024 semis ~$630B (WSTS $630.5B); "1 兆美元 2026–2027" consistent with WSTS 2026 forecast $975B
- ✅ part1-silicon-wafer-zh.md:254 — Wolfspeed Chapter 11 in 2025
- ✅ part2-chemicals-photoresist-zh.md:124 — JIC took JSR private for ~$6.4B (2023–24)
- ✅ part7-ic-design-zh.md:117–120 — AP-SoC share MTK ~34 / QCOM ~24 / Apple ~18 (Counterpoint Q1-25 36/28/17, Q4-25 30/22/23 — within the 2025 range)
- ✅ arithmetic — all market-share bar sets sum to 100 ± 2; value-capture charts in parts 1/6/13/14 match the overview; 韌性分數 (part14 L109–117) and sub-layer averages in parts 2/3/5/6/7/8/9/10 recompute exactly
- ❌ part5-foundry-zh.md:82–83 — TSMC "~60–65%" / Samsung "~10–13%" foundry share (TrendForce FY2025: 69.9% / 7.2%)
- ❌ part14-end-demand-zh.md:83–84 — "資料中心/企業 AI 34%" and "手機/PC 30%" are SIA's PC/Computer (34.9%) and Communications (33%) buckets, mislabelled
- ❌ part13-cloud-csp-zh.md:75, 84 — Azure "~22–25%" (Synergy Q3-25 20%, Q4-25 21%); L85 Google Cloud "~11–12%" (13–14%)
- ❌ part5-foundry-zh.md:189 — TSMC capex "400 億美元級別 (2024–25)": 2024 was $29.8B
- ⚠️ part5:175, overview:163, part3:163, part10:100 — TSMC GM "55–59%" (FY2024 56.1% ✓, FY2025 59.9%, Q4-25 62.3% — edge of range, stale for 截至 2026 年初)
- ⚠️ part6-gpu-design-zh.md:84 — NVDA GM "~73–75%" (FY2026 GAAP 71.1%; FY2025 75.0%)
- ⚠️ part3:112, part14:78 — semis "約 7,000 億 (2025)" (WSTS Autumn-2025: $772B)
- ⚠️ part9-idm-analog-zh.md:99 — TI ~19% / ADI 12–13% analog share are 2021 IC Insights figures
- ⚠️ part1:137, part4:143, part11:144, part12:130, part13:112 — stated bottleneck averages differ from the computed mean by 0.2–0.25
- ❓ part6-gpu-design-zh.md:84 — NVIDIA "AI 訓練市場 ~90%" — no named source found
- ❓ part7-ic-design-zh.md:106 — Broadcom custom-ASIC "~65–70%" share — analyst estimates vary 55–70%, none authoritative
- ❓ part2-chemicals-photoresist-zh.md:97–102, 117 — photoresist shares (JSR 26 / TOK 24 / Shin-Etsu 21 / Fujifilm 16 / Sumitomo 9) and DuPont ">80%" CMP-pad share — could not confirm
- ❓ part2-chemicals-photoresist-zh.md:237 — Lam "Aether" dry-resist product name — could not confirm from Lam's site
- ❓ part10-osat-zh.md:92, 96 — OSAT market $40–45B; ASE 28–30% / Amkor 14–16% / JCET 10–12% — plausible, no source checked
- ❓ part12-system-oem-zh.md:92–93 — Dell "~21% 毛利 / 營益率 5–6%", SMCI "11–14%" — not checked against FY2026 filings
- ❓ part13-cloud-csp-zh.md:142 — AWS operating margin "~35%" — not checked
- ❓ part9-idm-analog-zh.md:192–194 — TI 300mm "未封裝成本低約 40%", capex "約 50 億美元/年" — matches TI's own claims from memory, not re-verified
