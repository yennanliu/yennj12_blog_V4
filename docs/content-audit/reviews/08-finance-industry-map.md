## industry-map-semiconductor (value-chain overview + parts 1–14) — 15 posts

### Series-level observations
- **The template is rigid, but the analysis inside it is genuinely per-node. This is not reshuffled filler.** Each part has its own chokepoint logic and its own named numbers. Part 1 uses the Spruce Pine HPQ single point and the "<5% of finished-wafer cost" ceiling. Part 2 uses the 2019 Japan→Korea export curbs and JSR's ~$6.4B JIC buyout. Part 4 splits WFE by process step, with KLA at ~60% GM. Part 5 separates advanced (9.0) from mature (5.0) nodes. Part 9 is the "mirror of GPU" framing plus TI's 300mm bet. Part 12's pass-through revenue trap is a worked table. Part 14 uses sell-in vs sell-through. Several parts also score their sub-segments separately (2, 4, 5, 8, 10), which is the right move. Signals are honestly varied: Part 12 is BEARISH at 2.5 and Part 1 is NEUTRAL at 5.5. The series is not uniformly bullish.
- **What does repeat is the closing boilerplate.** The "最該注意的「非顯性節點」" paragraph appears in 11 of 15 posts. Its stock sentence "它不是純 AI 題材股,卻實實在在卡住…" appears near-verbatim in the overview and in Parts 1, 4, 5, 11 and 14. The "CoWoS is the real hidden bottleneck" point is made as the *hidden* insight in the overview and in Parts 5, 6, 8 and 10. By Part 10 it is no longer hidden. Rotate the closing device, and let Part 10 own CoWoS while the others link to it.
- **The "二階 picks-and-shovels" rows usually name a category instead of companies.** This is exactly where the reader wants tickers. Examples: Part 8 "供 HBM 的先進封裝/TSV、測試、設備" (Hanmi, BESI, Advantest, Disco are never named); Part 11 "光模組 / CPO / 雷射 / 光學元件供應鏈" (no Coherent, Lumentum, InnoLight, Credo, Astera Labs); Part 12 "液冷 / 電源 / 機構" (only 台達/Vertiv, in passing). The one layer the series calls "most undervalued" is the one where it names nobody.
- **Trust: every figure rests on one blanket disclaimer.** The line "公開產業常識的概估值(截至 2026 年初)" stands in for sourcing across all 15 References sections. Apart from one WSTS mention in Part 14, there is no TrendForce, SEMI, Yole, IDC, Synergy or company-filing citation anywhere. Share tables such as Part 2's EUV resist split (26/24/21/16/9), Part 3's EDA split (32/30/15), Part 4's per-vendor WFE shares and Part 14's end-market split (34/30/12/12/12, three identical 12s) read as precise but carry no source and no year. Add one source line per table, e.g. "TrendForce 2025Q4" or "company 10-K FY2025".
- **Staleness: "as of early 2026" figures are already out of date on hyperscaler capex, memory and Intel.** Hyperscaler capex is given as "2026 上看 5,000 億+" in Parts 13 and 14 (the post-Q4-2025 guidance was materially higher — verify). Part 8's premise is that commodity DRAM is still in a price war, but the 2025–26 memory upcycle contradicts it. Part 5 says Intel 18A is "尚在證明量產能力" (verify against the Panther Lake ramp). Deals that change the thesis rows are missing: OpenAI–AMD, OpenAI–Broadcom, Samsung–Tesla, the US government and NVIDIA stakes in Intel. Neoclouds (CoreWeave, Nebius) are absent from Part 13.
- **Series navigation is complete in every part but inconsistent in form.** All 14 parts link to all 14 parts plus the overview. However, the block sits *above* References rather than at the bottom. It is an H3 in most parts, an H2 in Part 4, and both an H2 and an H3 in Part 10. Part 4 has no "本篇" marker. Part 12 renders the current part unlinked while the others self-link. The 本篇 marker style varies (`（本篇）`, `← 本篇`, `◄ 本篇`). Standardise it with one snippet.
- **The overview does not link to any of the 14 parts.** It has zero internal links, so it is a dead-end hub (details below).
- **The front-matter title prefix "industry-map - " is a tool name.** It costs about 15 card characters and reads as internal jargon. Suggested form: "半導體產業鏈 Part 5:晶圓代工(中游)". Most posts also carry the tag "美股", which does not fit posts centred on Shin-Etsu, JSR, TEL or ASE. Mixed half-width `,` and full-width `，` punctuation also drifts: Parts 7 and 13 use full-width, the rest mostly ASCII inside Chinese prose.

### Per-post

#### `industry-map-semiconductor-part1-silicon-wafer-zh.md`
**Verdict:** light edit
- This is one of the strongest parts. The "<5% of cost → moat but no toll booth" argument (§四–五) and the Spruce Pine HPQ single point (§六) are real insight that the official data does not give you.
- §九 lists Wolfspeed as a SiC "投機性選擇權" with no mention of its 2025 Chapter 11. Add it, or swap the name.
- The share bars (信越 ~30%, SUMCO ~23%, …) need a source and year. Tie the "2023–2024 MSI 下滑" to a SEMI citation.

#### `industry-map-semiconductor-part10-osat-zh.md`
**Verdict:** light edit
- The "one layer, two fates" split, commodity 3.75 vs advanced packaging 8.75 (§四), is well argued, and the "上游向前整合比下游向後整合更嚴重" insight (§六) is distinctive.
- Name the picks-and-shovels. Advantest, Disco, BESI (hybrid bonding) and ASMPT are the obvious AI-packaging beneficiaries, but only 愛德萬 appears, in a one-line input list.
- Add CoWoS-L / CoPoS panel-level status and ASE's own advanced-packaging revenue figures so the "second-wave spillover" trigger in §八 can be measured.
- Remove the duplicate nav heading: `## 系列導覽` directly followed by `### 📚 系列導覽`.

#### `industry-map-semiconductor-part11-networking-zh.md`
**Verdict:** light edit
- The scale-up vs scale-out box (§二) and the "⚠️ 與 Part 7 的分工說明" section are exactly the kind of cross-part hygiene the rest of the series should copy.
- The optical/interconnect sub-layer has no names at all. Add Coherent, Lumentum, InnoLight (中際旭創), Eoptolink, Fabrinet, and Credo/Astera Labs (AECs, retimers). The CPO "最被低估" claim needs companies attached.
- Cisco appears only as "Silicon One" in a chart label. Also verify NVIDIA Spectrum-X's 2026 data-centre Ethernet share, because §七 frames it as a threat that is still arriving.

#### `industry-map-semiconductor-part12-system-oem-zh.md`
**Verdict:** light edit
- This is the most honest post in the batch: a BEARISH 2.5 call, plus the pass-through revenue table (營收 100→350, 毛利率 18%→12%), which is the post's key lesson and is well taught.
- §九 tells readers to "往上看一格" to liquid-cooling and power suppliers but names none beyond 台達/Vertiv in an earlier table. Add Vertiv, 奇鋐 AVC, 雙鴻 Auras, nVent and Vicor, with one line on each.
- Verify the SMCI "~11–14%" gross-margin band against its latest quarters, and state which fiscal year each margin in the table refers to.

#### `industry-map-semiconductor-part13-cloud-csp-zh.md`
**Verdict:** light edit
- The IaaS→PaaS→SaaS value ladder and the choice of "RPO/資本支出比" as the key gauge are useful, and the 10-K cross-links are good. All five targets exist.
- Neoclouds are missing: CoreWeave, Nebius and Lambda are now a real CSP tier, and the post dismisses them as "純轉售 GPU 的小型雲 → 迴避" without naming them.
- Update the capex figures (2025 "3,500–4,000 億", 2026 "5,000 億+") against actual 2026 guidance. Part 14 gives 2025 as "3,000–4,000 億", so the two parts disagree with each other as well.
- The full-width punctuation differs from the rest of the series. Normalise one way or the other.

#### `industry-map-semiconductor-part14-end-demand-zh.md`
**Verdict:** light edit
- This is a good finale. The "韌性分數" replacement for the bottleneck score (§四) is a smart adaptation, and the bull/bear bubble table (§七) is balanced.
- §三's split (34/30/12/12/12) looks invented, with three identical 12% buckets. Cite WSTS, Gartner or IDC by year, or give ranges.
- "2030 年上看 1 兆美元" is probably stale: industry forecasts had the market near $1T around 2026. Verify and restate the timeline.
- §十 largely repeats the overview's executive summary. It could instead say what changed across the 14 parts, e.g. which overview scores were revised.

#### `industry-map-semiconductor-part2-chemicals-photoresist-zh.md`
**Verdict:** light edit
- The opening hook (the 2019 Korea export curbs) and the two-column scoring (EUV resist 8.75 vs generic wet chemicals 4.5) are strong. The flip condition in §四 is explicit.
- Dry resist is flagged as "本層最需要盯的長線變數" (§八) but the vendor behind it, Lam Research, is never named. Name it, and link Part 4.
- The DuPont ">80% 墊市佔" pad share and the resist share split need a source and year.
- The heading `論點反轉條件(Thesis Invalidation）` has mismatched half-width and full-width parentheses. The References heading has the same mismatch.

#### `industry-map-semiconductor-part3-eda-ip-zh.md`
**Verdict:** light edit
- "小市場、大槓桿" and "客戶與產品雙重受惠" (AI-EDA) are clear framings, and the Arm royalty mechanics are well explained.
- The "全球逾 6,000 億美元半導體產業" figure has no year and is at least one year stale (Part 14 itself says 2025 passed 7,000 億). Align it.
- Missing 2025 facts: the Ansys close and the ARC processor-IP sale, the May–July 2025 US EDA-to-China export halt and its reversal (a live test of the 🔴 risk), and Arm's move toward its own silicon (§六 only says "曾嘗試"). Verify each.

#### `industry-map-semiconductor-part4-fab-equipment-zh.md`
**Verdict:** light edit
- The per-step WFE map (§二) and the "五個各自的獨占市場" insight are the best explanation of equipment structure in the series.
- Chinese domestic tool vendors (NAURA, AMEC, SMEE) are entirely absent, yet China localisation is the biggest 2025–26 swing factor for AMAT, Lam and TEL. The "其他 ~26%" bucket also mislabels this share as "Nikon/Canon 等".
- §四 includes "論點反轉條件(何時 Y 反而對?)". That is a leak from the interview "why X not Y" template; there is no Y here.
- The WFE "~1,000 億美元" figure needs a year. Its nav block is an H2 with no 本篇 marker.

#### `industry-map-semiconductor-part5-foundry-zh.md`
**Verdict:** light edit
- The IDM vs pure-play contrast, the flywheel diagram and "夾在兩個咽喉之間、但自己也是咽喉" make this a solid core post.
- The Intel and Samsung sections predate the US government and NVIDIA equity stakes in Intel (2025), the 18A product ramp, and Samsung's Tesla AI6 foundry contract. Each weakens the "三星/Intel 追不上" certainty in §三. Verify and update.
- The TSMC GM "~55–59%" and capex "400 億美元級別" are 2024–25 levels. Refresh them to 2025 actuals and 2026 guidance with a year label.

#### `industry-map-semiconductor-part6-gpu-design-zh.md`
**Verdict:** light edit
- The "護城河材質" comparison (physics / capital / software) is the series' clearest single insight, and the "express the bear case by buying AVGO/MRVL" idea is non-obvious.
- §五 re-prints the overview's value-capture bar chart almost unchanged. Replace it with GPU-specific data, e.g. data-centre revenue mix or GM trend by generation.
- The AMD row should reflect the OpenAI–AMD multi-GW deal. The trigger "推論佔總 AI 算力 > 訓練" has arguably already fired by 2026, so restate it as a measurable threshold.

#### `industry-map-semiconductor-part7-ic-design-zh.md`
**Verdict:** light edit
- The "同一層,一格漲潮、一格退潮" split (custom ASIC vs baseband) and the cross-reference box to Parts 6 and 11 are good.
- Missing: the OpenAI–Broadcom custom-accelerator deal, and MediaTek's entry into TPU co-design. The latter contradicts the post's framing of 聯發科 as mobile-only. Alchip and GUC get one chart label but no analysis, although they are the real #3 in ASIC services.
- The custom-ASIC share ("博通 ~65–70%") needs a source and year.

#### `industry-map-semiconductor-part8-memory-zh.md`
**Verdict:** restructure
- The central premise is stale. The opening quote says "commodity DRAM 卻還在跟客戶砍每一分錢", and §三 has Samsung leading DRAM at ~40%. Through 2025–26, commodity DRAM and NAND went into shortage with sharp contract-price increases. SK hynix overtook Samsung in DRAM revenue, and Samsung qualified HBM3E/HBM4 with NVIDIA. The "HBM vs commodity crack" thesis needs re-framing around "HBM crowd-out tightened everything". §八 already hints at this but treats it as secondary.
- Name the second-order picks (Hanmi, Hanwha, BESI, Advantest, 京元電) instead of "供 HBM 的先進封裝/TSV、測試、設備".
- The HBM share "~50%+" and the DRAM bit shares need a TrendForce/Omdia source and a quarter.

#### `industry-map-semiconductor-part9-idm-analog-zh.md`
**Verdict:** light edit
- This is one of the best posts. The GPU-mirror table, the TI 300mm economics and the "AI 餵電" angle (MPWR) are all differentiated.
- §六 says SiC substrate supply is "仍偏緊". The 2024–25 SiC glut (Chinese substrate price collapse, Wolfspeed Chapter 11) says the opposite. Fix this and the Wolfspeed node in the mermaid diagram.
- §七 "本層此刻處在週期軟階段(當前正在發生)" describes 2024–25 destocking. Verify whether the analog recovery has already started by 2026 and date the claim.

#### `industry-map-semiconductor-value-chain-zh.md`
**Verdict:** restructure
- The hub has **no links to any of the 14 parts** (zero internal links in the file). Add a series-nav block at the top or bottom, and make each row of the 鏈圖總表 link to its part. Right now a reader landing here cannot navigate the series.
- §十 and References promise "本站的 NVDA / AMD / TSM 10-K 深度解析", but no TSM 10-K post exists. Link the NVDA and AMD posts by slug and drop TSM, or write it.
- The scores have drifted from the parts. The overview has 特用材料/光阻 at 7 (Part 2 says 6.5), 網通 at 6 (Part 11 says 6.5) and OSAT at 3 (Part 10 splits it 3.75 / 8.75). EUV is 10 here and 9.3 as a layer in Part 4. Either reconcile the numbers or add a "各篇修正後分數" column.
- readTime "28 min" is wrong for about 320 lines (the audit expects ~14).

### Top 5 highest-impact fixes in this batch
1. **Turn the overview into a real hub.** Add links to all 14 parts, link each 鏈圖總表 row, fix the dead TSM 10-K reference, reconcile its scores with the parts, and correct readTime.
2. **Restructure Part 8 (memory) for the 2025–26 upcycle.** The "commodity still in a price war / Samsung #1" framing is the most visibly stale claim in the series.
3. **Give every share or market-size table a source and year.** Even one line such as "TrendForce 2025Q4" or "company 10-K FY2025" helps. The blanket "公開產業常識的概估值" disclaimer is doing too much work.
4. **Name the companies in the "二階 picks-and-shovels" rows** of Parts 8, 10, 11 and 12 (HBM/packaging tools, optics and AECs, liquid cooling). These are the posts' own headline "most undervalued" ideas.
5. **Run a 2026 fact sweep across the thesis rows.** Cover hyperscaler capex (Parts 13/14), Intel and Samsung foundry (Part 5), OpenAI–AMD/Broadcom (Parts 6/7), neoclouds (Part 13), China tool vendors (Part 4), and SiC and Wolfspeed (Parts 1/9). Standardise the series-nav snippet (heading level, 本篇 marker, placement at the very bottom) at the same time.
