# B02-fde-interview-14-26 — content audit

Batch: `fde-interview-guide` parts 14–26 (13 posts, Traditional Chinese, interview-prep).
Mechanical baseline: `docs/content-audit/inputs/mechanical-baseline.txt` lines 30–85 — every post
carries the three house-format warnings (short, no 三個演進階段, no 為什麼選 X 不選 Y); parts
16–25 also carry the 面試答題要點 warning; parts 16, 22, 26 carry the Google warning. Those are
referenced below, not repeated. No mechanical **errors** in the batch.

## Batch summary

Parts 14–26 are the 2026-06-03/04 batch of RKK scenario posts (all stamped one hour apart) that
predate the current 600–900-line house format: they run 291–391 lines, open with a 4-line
contrast quote and (from part 16 on) a single scenario-based 面試情境, and close with a
blockquoted model answer. Technically they are sound: the handful of hard facts (Pub/Sub
600 s ack ceiling, MCP 2025 OAuth 2.1 / no token pass-through, Gemini 1.5 cache minimum,
Vertex OpenAI-compatible endpoint) are stated with explicit "撰文時/已退役" caveats, and most
derived numbers recompute. What drags the batch down is **internal consistency**: eleven of
thirteen posts state the same number or threshold twice with different values (parts 15, 17,
18, 19, 22, 23, 24, 25), one triple-counts a latency sum (part 22 L59–60), and one describes a
"Dual-LLM" that is not the privilege-separated pattern it names (part 20). The model answer
survives under other headings in part 15 (九 CAPE 「完整範例回答」 L353) and part 26 (六 CTA
script L235); parts 16–25 keep the literal heading. Backfilling 三個演進階段 would add value in
the four infra-shaped posts (15, 21, 23, 24) and be padding in 14, 16, 17, 20, 25, 26; a 4-row
decision table *with flip conditions* would help every post that already has a comparison
table without them (16, 17, 19, 22, 24). Note that parts 45, 51, 52 (and core-concept 2, 7, 12,
17, 18) already redo several of these topics in the long format, so the cheaper direction is
"fix and link" rather than "expand". Verdicts: 1 Ready (part 25), 12 Needs revision, 0 Not ready.

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| part14-memory-architecture | 372 | 4 | 5 | 3 | 4 | 3 | 4 | 3.8 | Needs revision | L48–63 defines Semantic=profile, Episodic=vector history; part 18 L94 calls the vector tier "Semantic Long-term Memory（情節記憶）" — the series contradicts itself on its own taxonomy. No 面試情境 section. |
| part15-scale-cache | 391 | 4 | 4 | 4 | 4 | 3 | 4 | 3.8 | Needs revision | L344–365 「九、面試答題框架：CAPE」+「完整範例回答」 is a model answer under another heading. L87 semantic-cache threshold 0.92 vs L134 "推薦起點 0.90". |
| part16-multiagent-state-deadlock | 342 | 4 | 4 | 3 | 4 | 3 | 3 | 3.5 | Needs revision | L21 "你在 Google Doc 看到對話日誌" (house rule) + L328 model answer; no numbers beyond `iteration_count >= 5`, no flip condition on the Redis/Firestore table L302–318. |
| part17-mcp-tool-oauth | 300 | 4 | 4 | 3 | 3 | 3 | 4 | 3.5 | Needs revision | L193 "Access Token 只存在記憶體（不寫磁碟）" contradicts L276/L281 (Secret Manager + Memorystore token cache). |
| part18-memory-cost-tuning | 303 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L205–223 computes a 76 % cache saving on an 800-token prefix that L207–208 says is below the 32,768-token minimum; 0.25× recomputes to 75 %, not 76 %. L86 Working Memory 5,000 vs L127 3,000 tokens. |
| part19-multiagent-eval-tracing | 340 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L141 "Total E2E 5,450 ms" is the serial sum (450+1,200+3,800) while L55–80 fan Legal/Finance out in parallel (→ 4,250 ms). L184 heading "Trajectory Exact Match" computes path efficiency (4/5), not exact match. |
| part20-indirect-prompt-injection | 294 | 3 | 4 | 3 | 3 | 3 | 4 | 3.3 | Needs revision | L138–160: the sanitizer's free-text summary is fed straight to the tool-bearing Main Agent — the one channel the original Dual-LLM/quarantined-LLM pattern closes. L149 is true, L159 over-promises; no source cited; zero numbers in the post. |
| part21-async-longrunning-agent | 324 | 4 | 4 | 4 | 4 | 3 | 4 | 3.8 | Needs revision | L148 "Cloud Tasks / Redis 偵測到 Worker 心跳停止" — Cloud Tasks appears nowhere else; the architecture (L47–110) is Pub/Sub + GKE. L115 ack-deadline note is the best "when it breaks" paragraph in the batch. |
| part22-parallel-tool-calling | 306 | 2 | 4 | 4 | 4 | 3 | 3 | 3.3 | Needs revision | L59–60 "5 輪 × 每輪 3 個工具 × 850 ms = 12,750 ms": 850 ms is already the 3-tool total, so 5 rounds = 4,250 / 2,000 ms, not 12,750 / 6,000. L298 model answer credits ADK with a dependency-declaring Tool Registry that L195 explicitly says ADK does not have. Google ×5 incl. description L6. |
| part23-ratelimit-fairshare | 304 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L104 Fair-Share kicks in at > 80 % global quota; L251 says 70–90 %. L72 `len(prompt) * 1.3` heuristic vs L172 exact `count_tokens`; L172 names tiktoken (OpenAI's tokenizer) for a Gemini quota. L49 4 M TPM unverified. |
| part24-hybrid-model-routing | 299 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | Gemma equivalent cost is "$0.05/1M" at L34 and L135 but derived as $0.08/1M at L225; headline "~66 %" saving at L40 never reconciled with the 49 % at L275; L269 $1,440 does not recompute (3 L4 × 720 h × $0.60 = $1,296); unrouted cost L258–262 ignores output tokens, unlike part 15. |
| part25-self-reflection-loop | 320 | 4 | 5 | 4 | 4 | 3 | 4 | 4.0 | Ready | L171 "3 次 = 3x 成本" vs L283–285 (2 reflections = 5x); L283 "沒有反思 $0.015" ignores the evaluator call that always runs once (floor is 2x). L106 Reflexion-vs-Self-Refine caveat is exemplary. |
| part26-competitive-positioning | 291 | 4 | 5 | 3 | 3 | 3 | 2 | 3.3 | Needs revision | Nine "Google" mentions incl. description L6 and the closing thesis L285; the post is premised on "Google FDE". L235 「六、面試官最想聽到的一句話」 is a model answer (CTA script) under another heading. L190 endpoint path `v1/.../endpoints/openapi` unverified (official sample used `v1beta1`). |

Scores are unweighted means (no finance posts). "Needs revision" is driven by one major each —
mostly an internal contradiction a candidate would repeat in an interview — not by the
house-format warnings, which are minor for posts of this age.

## Patterns

### Content quality
- The scenario prompts (L21 in parts 16–25) are genuinely good: specific, multi-constraint,
  judgment-requiring ("第 25 分鐘崩潰", "20 個 200K-token 請求"). They are the strongest asset
  in the batch. Parts 14 and 15 have no 面試情境 at all (L13–17 go straight to 一).
- Diagnosis chains are concrete where they exist — part 16 L112–150 (log → iteration count →
  state not advancing), part 19 L284–310 (aggregate → drill-down → ISO date vs `YYYYMM`) — and
  absent in parts 14, 17, 20, 26.
- Honest caveats are above the series average: part 22 L123 (critical path, not max), part 22
  L195 (ADK has no `depends_on`), part 25 L106 (Reflexion vs Self-Refine), part 21 L115 (ack
  deadline). Several of these caveats were clearly added after the fact and now contradict the
  untouched model answer (part 22 L195 vs L298; part 18 L207 vs L210–223).
- Every post ends with the thesis restated; opening quote and closing match in all 13.

### Structure (does the house format help or pad?)
- 三個演進階段 would add value where the topic *is* a scale cliff: part 15 (cache layers by
  QPS), part 21 (Polling→SSE→WS, 5→50 workers, L225–240), part 23 (quota tiers L213–228), part
  24 (when self-hosting Gemma pays off, L218–231). In each the raw material for Phase 1/2/3 is
  already in the post as a flat list.
- It would be padding in part 14 (taxonomy), 16 (a design-flaw post), 17 (protocol/authz), 20
  (threat model), 25 (a control loop), 26 (a sales conversation). Forcing three ASCII phase
  diagrams onto those would roughly double their length without new decisions.
- 為什麼選 X 不選 Y with flip conditions is the cheaper, higher-value backfill: five posts already
  have the comparison table and only lack the flip row — part 16 L302–318 (Redis vs Firestore),
  part 17 L249–262 (service key vs PKCE vs device flow), part 19 L264–283 (Cloud Trace vs
  LangSmith vs Phoenix), part 22 L169–189 (gather vs ThreadPool vs ADK), part 24 L52–69
  (embedding vs LLM vs rules). Part 21 L170–206 (polling/SSE/WS) already has flip conditions in
  prose.
- Model-answer sections survive under three disguises: the literal 面試答題要點 (16–25), 「面試
  答題框架：CAPE」 + 「完整範例回答」 (part 15 L344–365), and 「面試官最想聽到的一句話」 (part
  26 L235–258). Part 14 (L348 快速複習卡) is the only post that ends on a cheat sheet instead.

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Sourced/caveated and recomputing: part 15 L31–35 and L300–318 (Gemini 1.5 pricing, 68 %
  saving), part 18 L29–41 and L254–270 (98.7 %), part 23 L213–222 (3.4 M < 3.6 M TPM), part 24
  L258–275 (49 %, except the $1,440 line).
- Invented-looking (no assumption stated): part 14 L310–316 recall thresholds 0.80/0.92; part
  15 L73–94 hit rates 15 % / 35 %; part 19 L245–262 accuracies 0.91/0.73/0.88; part 24 L224
  "~2,000 tokens/sec/GPU"; part 25 L283–285 "$0.015/次查詢". They read as plausible but no
  line says "assume".
- No numbers at all: part 20 (0 ms / $ / %), part 26 (deliberately, L140–150 defers to "當期
  官方價目表"). Part 17 has one (L56 "1 小時").
- "When it breaks" is present in 21 (L244–262 edge cases), 23 (L232–266), 25 (L153–180), and
  absent as a section in 14, 16, 17, 20, 26.

### Direction (overlap, gaps, stale topics, category fit)
- Heavy overlap with later long-form parts that were written to the current standard:
  part 20 ↔ part 45 `prompt-injection-defense` (635 lines) and `fde-core-concept-7`; part 15 ↔
  part 51 `kv-cache-memory` (814) and `fde-core-concept-17`; part 22 ↔ part 52
  `tool-fanout-optimization` (674); part 19 ↔ parts 35/36; part 21 ↔ part 43; part 23 ↔
  `fde-core-concept-12`; part 24 ↔ `fde-core-concept-18`; parts 14/18 ↔ `fde-core-concept-2`.
  None of the 13 posts link forward to its long-form successor.
- Parts 14 and 18 cover the same subject (agent memory) with conflicting layer names (part 14
  L48–63 vs part 18 L94); a reader doing the series in order meets both.
- Model era is uniformly Gemini 1.5 / Gemma-7b / text-embedding-004 (parts 15, 18, 23, 24, 26);
  each carries a "已退役" caveat, which is the right fix — but the caveats sit mid-post and the
  titles/descriptions still sell the old numbers (part 24 description L6 "Gemma 與 Gemini").
- Categories `["all","ai","engineering"]` fit all 13; part 26 would also fit `business`.

### Accuracy
- Numbers stated twice with two values: part 15 L87/L134 (0.92 vs 0.90), part 17 L193/L281,
  part 18 L86/L127 (5,000 vs 3,000), part 23 L104/L251 (80 % vs 70–90 %), part 24 L34/L225
  ($0.05 vs $0.08) and L40/L275 (66 % vs 49 %), part 25 L171/L285 (3x vs 5x).
- Arithmetic that does not recompute: part 22 L59–60 (×3 double count), part 24 L269 ($1,440
  vs $1,296), part 18 L223 (76 % vs 75 %).
- Mechanism misdescribed: part 20 L138–160 (summary text crosses the trust boundary; the
  original pattern passes an opaque handle), part 19 L184 ("Exact Match" that isn't).
- Model-answer sections that contradict the body they summarise: part 22 L298 vs L195; part 19
  L334 "下降超過 5%" (body L261 uses a 14 % example and never sets 5 %); part 24 L289 "便宜約
  15 倍" (derived from the $0.08 figure the intro contradicts).

### Format / front matter
- `readTime` is 15–18 min on every post; the house formula (~32 lines/min) gives 9–12 min for
  291–391 lines. Consistent drift across all 13.
- Tags: all 13 carry `"RKK"`, `"Interview"`, `"Cloud"` — compliant. `"Gemma"`, `"Gemini"`,
  `"Vertex AI"`, `"GCP"` (parts 24, 26) are product tags and fine.
- "Google" in body/description: part 16 L21 (1), part 22 L6/L171/L185/L294/L298 (5), part 26
  L6/L62/L90/L104/L108/L114/L129/L269/L285 (9). Part 26 cannot drop them all without changing
  what the post is about (Google Workspace / Cloud Identity are product names).
- Front matter uses `weight: N` (14–26) — not in the CLAUDE.md required-field list but harmless
  and it is what makes the tag page order the series.
- Series navigation links all resolve (part 13 and part 27 exist); every diagram stays ≤ 80
  columns; no unclosed fences; no images.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | major | part22 L59–60 | "5 輪 × 每輪 3 個工具 × 850ms = 12,750ms / 6,000ms" triple-counts: 850 ms *is* the 3-tool round. | 5 × 850 = 4,250 ms vs 5 × 400 = 2,000 ms; keep the 53 % line. |
| 2 | major | part22 L298 | Model answer: "ADK 的優點：Tool Registry 可以讓工具顯式宣告依賴關係" — L195 states ADK has no `depends_on` and no dependency resolution. | Rewrite L298 to "自建 Registry + Orchestrator 包在 ADK 外層", matching L195. |
| 3 | major | part20 L138–160 | "Dual-LLM" passes the quarantined LLM's free-text summary into the privileged, tool-bearing agent. An injection that survives summarisation ("call send_email…") still reaches the tool layer; the original pattern (Willison 2023 / CaMeL) never lets quarantined text reach the privileged LLM. | Either rename to "兩段式清洗" and state the residual risk explicitly at L159, or describe the real pattern (opaque variable + output validation) and cite it. Add one number (e.g. bypass rate of pattern matching). |
| 4 | major | part19 L141 | "Total E2E: 5,450ms" is the serial sum; the span tree (L55–80) and the Router output `["legal","finance"]` show parallel fan-out → 4,250 ms. | Say "若順序執行 5,450ms；並行後 450 + max(1,200, 3,800) = 4,250ms，仍由 query_erp 決定". |
| 5 | major | part18 L205–223 | Worked Context-Cache example uses an 800-token prefix immediately after L207–208 says the 1.5-era minimum is 32,768 tokens; "節省 76%" should be 75 %. | Re-base the example on a 40K-token product manual prefix, or drop the arithmetic and keep the caveat. |
| 6 | major | part24 L34/L135 vs L225; L40 vs L275 | Gemma equivalent cost $0.05 vs $0.08 per 1M; headline 66 % vs computed 49 % — never reconciled. L269 $1,440 ≠ 3 × 720 h × $0.60 = $1,296. | Use $0.08 everywhere; replace L40 with "理論上限 ~66%，計入 GPU 常駐成本後見第七節 ~49%"; fix $1,296 or state the hourly rate that gives $1,440. |
| 7 | major | part23 L104 vs L251 | Fair-Share switch-on threshold is "> 80%" in the architecture and "70~90%" in the defence section. | Pick one ladder (70/90 or 80/90) and use it in both places and in L300 model answer. |
| 8 | major | part26 L6, L62, L90, L285 | Interview post built on "Google FDE 顧問視角" with nine Google mentions, including the description and the closing thesis. | Description → "以 Cloud FDE 顧問視角"; L62/L285 → "我們"; keep product names (Google Workspace / Cloud Identity) only where no neutral name exists, or accept a documented exception for this post. |
| 9 | major | part17 L193 vs L276/L281 | "Access Token 只存在記憶體（不寫磁碟）" vs GCP mapping that stores OAuth tokens in Secret Manager and caches them in Memorystore. | Say refresh tokens → Secret Manager, access tokens → in-process or Redis with TTL ≤ token lifetime and encryption; make L193 and L281 agree. |
| 10 | major | part14 L48–63 vs part18 L94 | Series taxonomy conflict: part 14 Semantic = structured profile, Episodic = vector history; part 18 labels the vector tier "Semantic Long-term Memory（情節記憶）". | In part 18 rename Layer 2 to "Episodic Memory（情節記憶）" and Layer 3 to "Semantic / Profile Memory"; cross-link to part 14 L48. |
| 11 | minor | part15 L344–365; part26 L235–258 | Model answer kept under other headings (CAPE 「完整範例回答」; 「面試官最想聽到的一句話」). | Convert to a 5-bullet "答題結構" or fold into the 複習卡; same treatment as 面試答題要點 in 16–25. |
| 12 | minor | part16 L21 | "你在 Google Doc 看到對話日誌". | "在共享文件 / Cloud Logging 看到對話日誌". |
| 13 | minor | part21 L148 | "Cloud Tasks / Redis 偵測到 Worker 心跳停止" — Cloud Tasks is not in the architecture. | "排程器（Redis 心跳 / Pub/Sub 重投遞）偵測到…". |
| 14 | minor | part23 L72 vs L172; L172 | `len(prompt) * 1.3` estimate vs "精確計算" two sections later; tiktoken is OpenAI's tokenizer. | Keep the heuristic only as the gateway fast path; name the Vertex `count_tokens` API / local tokenizer. |
| 15 | minor | part25 L171 vs L283–285 | "3 次 = 3x 成本" vs "2 次反思 = 5x"; baseline ignores the always-on evaluator call (floor 2x). | State: 0 reflections = 2 calls (2x), 1 = 4 calls, 2 = 6 calls; fix L314. |
| 16 | minor | all 13, front matter | `readTime` 15–18 min for 291–391 lines (formula → 9–12 min). | Recompute from line count when touching each file. |

## Recommendations

1. **Fix contradictions before any backfill.** WHY: the majors above are all one-line edits
   (findings 1, 2, 4, 5, 6, 7, 9, 10, 15) and they are what a candidate would repeat wrongly;
   adding 400 lines around a wrong number makes it worse. HOW: one PR for parts 15–25 applying
   the "suggested fix" column; run `review_posts.py` on the batch after.
2. **Backfill 三個演進階段 only in parts 15, 21, 23, 24.** WHY: those are the posts whose
   argument *is* "the right answer changes with scale", and each already holds the phase
   material as a flat list (part 21 L225–240, part 23 L213–228, part 24 L218–231). HOW: three
   `╔══╗` phases of ~40 lines each, reusing the existing numbers; target ~500 lines, not 700.
3. **Do not phase-ify parts 14, 16, 17, 20, 25, 26.** WHY: taxonomy, design-flaw, protocol,
   threat-model, control-loop and sales-conversation posts have no scale axis; the section
   would be invented. HOW: document the exemption in CLAUDE.md ("posts whose subject has no
   scale axis skip 三個演進階段 and keep a 4-row decision table instead") so the warning stops
   firing as a to-do.
4. **Add flip conditions to the five existing comparison tables** (16 L302, 17 L249, 19 L264,
   22 L169, 24 L52). WHY: this is 80 % of the 為什麼選 X 不選 Y value for 10 % of the lines.
   HOW: append one row "翻轉條件：當 … 時改選 Y" to each table; rename the section so the
   checker counts it.
5. **Retire the model answer in all three disguises.** WHY: the house format dropped it; the
   disguised versions (15 L353, 26 L235) are the ones that escape the checker. HOW: replace
   with a 4–5-bullet "答題骨架" (what to say first/second/third) that references section
   numbers rather than restating them; also extend `review_posts.py` to flag 「範例回答」 and
   「最想聽到」.
6. **Cross-link each short post to its long-form successor.** WHY: parts 45/51/52 and
   core-concept 2/7/12/17/18 already cover 20/15/22/14/20/23/15/24 at the current standard;
   today nothing tells the reader. HOW: a one-line "深入版：[Part 51]…" under the 複習卡 or
   before 系列導航; consider trimming the short post to the scenario + diagnosis + decision
   table once the link exists.
7. **Reconcile the memory taxonomy across 14, 18 and core-concept-2.** WHY: three posts, two
   naming schemes. HOW: adopt part 14's names (Working / Episodic / Semantic / Procedural) as
   canonical and edit part 18 L94–101 and L113–123.
8. **Part 20: either describe the real Dual-LLM pattern or stop calling it that.** WHY: the
   name promises an isolation guarantee the diagram does not deliver, and part 45 / core-7 now
   cover the topic properly. HOW: cite Willison's quarantined-LLM write-up or CaMeL, show the
   opaque-handle variant in the diagram, and add one quantitative claim (e.g. bypass rate of
   keyword filters) so the post is not number-free.
9. **Decide the Google rule for part 26 explicitly.** WHY: a competitive-positioning post for a
   Cloud FDE cannot avoid product names; nine substitutions would read as evasive. HOW: either
   replace the non-product uses (L6, L62, L90, L285 → "Cloud"/"我們") and whitelist product
   names in the checker, or move the post out of the interview series into `business`.
10. **Normalise `readTime` and the pricing caveats.** WHY: every post overstates reading time
    by ~50 %, and the "已退役" caveats sit mid-body while titles still name Gemini 1.5 /
    Gemma-7b. HOW: recompute readTime from line count; move each pricing caveat to directly
    under the first price table; neutralise model names in descriptions (part 24 L6).

## Verified / unverified claims

- ✅ part15 L31–35 — $0.002/1K = $2/1M; 10K × 3,000 × $0.002/1K = $60/day = $1,800/mo; "貴約 27 倍" vs $0.075 Flash (2/0.075 = 26.7). Recomputed.
- ✅ part15 L300–318 — Flash input $1,687.5 + output $1,080 = $2,767.5; L1 $415 + L2 $969 + KV $506 = $1,890 = 68.3 %; remainder $878. Recomputed.
- ✅ part15 L186–197 — Gemini 1.5 Pro $1.25/1M input (≤128K) and cached $0.3125/1M ("便宜 4 倍") match the 1.5-era price list the post dates itself to.
- ✅ part18 L29–41, L254–270 — 500 × 10 × 90 = 450,000; 450,600 × $1.25/1M = $0.563; ×10 × 100 × 30 ≈ $16,900 (post rounds to $16,800); plan B 5,900 tokens → $0.0074, $221/mo; saving 98.69 %. Recomputed.
- ❌ part18 L223 — "節省 76%": 0.25× of $0.0125 = $0.003125 → 75 %.
- ✅ part18 L207 — "新世代模型門檻較低": Gemini API caching docs list 1,024 (2.5 Flash) / 2,048–4,096 (2.5 Pro) minimums, with implicit caching default-on for 2.5+.
- ❓ part18 L207 — "Gemini 1.5 世代為 32,768 tokens": consistent with the 1.5-era docs as remembered, but the current caching page no longer lists 1.5 models; could not confirm from a live source.
- ✅ part19 L261 — 0.73 vs 0.85 baseline = 14.1 % relative drop.
- ❌ part19 L141 — 5,450 ms = serial sum; parallel fan-out (as drawn) gives 4,250 ms.
- ✅ part21 L115 — Pub/Sub ack deadline max 600 s (min 10 s; `ModifyAckDeadline` also capped at 600 s).
- ✅ part17 L264 — MCP authorization (2025 revision): OAuth 2.1 base, PKCE required, MCP server as resource server, token pass-through prohibited. Matches the spec text as published.
- ✅ part22 L53 — max(150, 400, 300) = 400 ms, 52.9 % saving; L120 1,050 → 900 ms ≈ 14 %.
- ❌ part22 L59–60 — 12,750 / 6,000 ms triple-count (should be 4,250 / 2,000).
- ✅ part22 L195 — ADK ships `SequentialAgent` / `ParallelAgent` workflow agents and model-side parallel function calling; no `depends_on` field on tool definitions. Consistent with ADK docs; unchanged as of this review.
- ✅ part23 L213–222 — 1 M × 2 + 200 K × 7 = 3.4 M < 3.6 M; L236 20 × 200 K = 4 M; L62 refill 500 K/60 = 8,333/s. Recomputed.
- ❓ part23 L49 — "Gemini 1.5 Pro 全域 TPM 4,000,000": not confirmable from the current rate-limit page (1.5 Pro no longer listed); forum reports of the paid tier range 2 M–4 M TPM. Mark as "示意" is already present.
- ✅ part24 L225, L266–268 — $0.60/(2,000 × 3,600/1M) = $0.083/1M; 4.2 B tokens / (2,000 × 86,400) = 24.3 GPU-days = 583 GPU-h = $350. Recomputed.
- ✅ (approx.) part24 L223 — L4 on GKE "$0.60/hr": Google's accelerator pricing lists g2-standard-4 (1 × L4) ≈ $0.71/h and the bare L4 SKU ≈ $0.56/h; $0.60 is a fair round number, but the g2-standard-4 rate would give $0.098/1M.
- ❓ part24 L224 — "Gemma-7b ~2,000 tokens/sec/GPU on L4": no source; plausible only as batched vLLM aggregate throughput.
- ❌ part24 L269 — "$1,440/月" for 3 L4s: 3 × 720 h × $0.60 = $1,296.
- ✅ part24 L258–275 — $7,500; $2,250; $3,790 total; 49.5 % saving. Recomputed (given the $1,440 input).
- ✅ part25 L283–285 — $0.015 × 3 = $0.045, × 5 = $0.075.
- ✅ part26 L33–34 — Gemini 1.5 Pro 2 M context; GPT-4o 128 K.
- ❓ part26 L190 — Vertex OpenAI-compatible base URL `…/v1/projects/{P}/locations/{L}/endpoints/openapi`: the path shape and `google/<model>` naming match Google's Chat Completions API docs; the official sample used `v1beta1` and third-party docs show `v1` — could not confirm which the current docs use.
- ✅ part26 L80–96 — OpenAI offers regional data-residency options and a HIPAA BAA for the API; Vertex AI offers region pinning (asia-east1) and FedRAMP for in-scope services. Stated with hedges; nothing contradicted.
- ✅ Series navigation: part 13 and part 27 targets exist; all 13 prev/next links resolve.
