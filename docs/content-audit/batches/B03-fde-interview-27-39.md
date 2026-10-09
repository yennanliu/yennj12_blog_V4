# B03-fde-interview-27-39 — fde-interview-guide parts 27–39

Reviewed 2026-10-09. 13 Traditional-Chinese interview-prep posts (5,512 lines), every post read in full, derived
numbers recomputed with python3, four fast-moving product claims checked on the web (ADK session services, ADK
`require_confirmation`, Gemini cache-storage price, Google's "Role-Related Knowledge" attribute). Mechanical
baseline (`inputs/mechanical-baseline.txt` L86–142) already records: parts 27–38 are 307–671 lines with no
三個演進階段 and 0 decision tables; parts 27–33, 36, 38 mention Google; 35–39 keep a 面試答題要點 section;
34 has 0 ASCII box diagrams; 39 has a 十一 section. Those are referenced, not repeated.

**Premise correction for the coordinator.** The batch brief describes these posts as "written to the current
CLAUDE.md house format". They are not: twelve of the thirteen predate it (27–30 dated 2026-06-04 "顧問實戰",
31–38 dated 2026-06-05 "RKK 實戰", all 307–671 lines, none with a phase section or a decision table). Only
part 39 (2026-06-08, 724 lines) carries 三個演進階段 and a 為什麼選 X 不選 Y section — and `review_posts.py`
still reports it as "0 decisions" because its section is prose under `決策 N：` headings rather than the
table shape the checker greps. So the "does the format pad?" question can only be answered on part 39,
and the answer there is split (see Structure).

## Batch summary

This batch is three mini-series. Parts 27–30 are "顧問實戰" soft-skill posts (scoping, incident comms, TCO,
constraint-first design): short, readable, almost no checkable numbers except part 29, which is the batch's
numbers post and is where the arithmetic breaks. Parts 31–34 are GCP product posts and interview meta
(ADK, Vertex AI stack, how RKK is scored, six mock scenarios); they are the most Google-dependent content in
the whole series — part 31's title is literally "Google ADK" and part 33 has a scoring dimension named
"Google Cloud 產品知識" — so the "no Google" rule is unenforceable here, and the checker only flags one line per
file (30 mentions in part 32). Parts 35–39 are "production systems" briefs with a shared template
(核心問題 → layers → 系統效應 table → 面試答題要點) that is the best-built shape in the batch; part 35 (tracing)
is the only Ready post and the model for the rest. Accuracy is the weak dimension: every post that computes
something has at least one number that does not survive recomputation — the ROI headcount in 29 (10 agents ×
200/day = 2,000, not the 10,000 queries/day the model assumes), the 8-vs-10 engineer-days in 38, the
Little's-law misuse and circular ROI base in 39, the hourly-precompute call count in 34, the CI example in 36
whose baseline fails its own gate. Two posts contain commands a reader could paste with real consequences:
part 30 grants `allUsers` `roles/logging.viewer` at the organisation level as an "audit log" step, and
30/34/37 all use VPC-SC / Private Service Connect as magic words for things they do not do. Cross-post drift is
the batch-level finding: the Flash-vs-Pro saving is 40× (29), 80% (33) and 5× (34); Cloud Run cold start is
10–30 s (28), 8–12 s (38) and 8–15 s (39); part 31 says ADK has no `session:` prefix and part 34 uses it
four times. Verdicts: **1 Ready** (35), **9 Needs revision** (27, 28, 31, 32, 33, 34, 36, 37, 38),
**3 Not ready** (29, 30, 39).

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| part27-poc-scoping-zh.md | 307 | 4 | 5 | 2 | 2 | 3 | 3 | 3.2 | Needs revision | Only post with no checkable number; L229 "風險點增加了兩倍" is the one quantitative claim and it is invented; L205 "Google FDE" inside the deliverables block |
| part28-incident-communication-zh.md | 317 | 3 | 5 | 3 | 3 | 4 | 3 | 3.5 | Needs revision | L150–151 the "凌晨 2–4 點" log filter is a continuous 3-day window (18:00Z→20:00Z spans the whole period); L164 `gcloud monitoring metrics list` and the metric name could not be confirmed; L239 "$X/月" placeholder |
| part29-tco-roi-zh.md | 348 | 2 | 4 | 4 | 3 | 4 | 3 | 3.3 | Not ready | L251 10 agents × 200/day = 2,000 queries, but the model uses 10,000/day; headcount after AI (4,900 queries ÷ 200 ≈ 25 agents) cannot fall to 6 (L257) — the 335% ROI (L264, L300) rests on it |
| part30-constraint-driven-architecture-zh.md | 350 | 2 | 4 | 3 | 4 | 4 | 3 | 3.3 | Not ready | L194–198 `gcloud organizations add-iam-policy-binding … --member="allUsers" --role="roles/logging.viewer"` makes org logs public and does not enable Data Access audit logs (the `auditConfigs` at L203–208 does) |
| part31-adk-deep-dive-zh.md | 477 | 3 | 4 | 4 | 4 | 4 | 2 | 3.5 | Needs revision | L303/L340/L462 "Session State 自動持久化到 Firestore" — ADK's documented services are InMemory/Database/VertexAi; Agent Engine uses VertexAiSessionService, not Firestore; L387 "per-agent retry policy" on ParallelAgent not a documented feature |
| part32-vertex-ai-stack-zh.md | 547 | 3 | 4 | 3 | 3 | 4 | 3 | 3.3 | Needs revision | L414 "撰文時為 Gemini 2.0 Flash、Gemini 1.5 Pro" contradicts L272 "該模型已退役"; L29–56 selection matrix lists Agent Builder in two of its three rows and never uses its x-axis; L87 "快 10 倍" invented |
| part33-rkk-anatomy-zh.md | 440 | 3 | 5 | 4 | 2 | 4 | 3 | 3.5 | Needs revision | L21 "RKK（Role-based Knowledge）" — Google's published attribute is Role-Related Knowledge (RRK); the series name, every tag and the CLAUDE.md tag rule carry the mis-expansion. L89 disclaimer is good and should be copied to 34 |
| part34-mock-scenarios-zh.md | 671 | 3 | 4 | 4 | 1 | 3 | 4 | 3.2 | Needs revision | L190–192, L599 write to `session:` scope, which part 31 L311 explicitly says does not exist; L284 "院內的 Cloud DLP" sends raw PHI to a Google API in a scenario whose constraint is "原始病歷資料不能傳送到 Google 的伺服器"; 0 diagrams in 671 lines |
| part35-granular-tracing-zh.md | 322 | 5 | 5 | 4 | 5 | 4 | 4 | 4.5 | Ready | Span tree (L63–90) sums exactly (280+14,700+260 = 15,240; 14,520/15,240 = 95.3%); $17,280/day at L211 recomputes; tail-sampling caveat L226–239 is correct. Minor: L312 ">10s" vs L219 ">5s" anomaly threshold |
| part36-eval-pipeline-zh.md | 329 | 3 | 4 | 4 | 3 | 4 | 3 | 3.5 | Needs revision | L244–245 the example CI report's baseline (Faithfulness 0.87, Recall 0.83) fails the post's own gate (≥0.90, ≥0.85 at L224–225), so `main` could never have deployed; L112 "200 題（P < 0.05）" unsourced; L198 Python precedence bug |
| part37-legacy-integration-zh.md | 349 | 3 | 5 | 4 | 4 | 4 | 3 | 3.8 | Needs revision | L255–275 puts a "Private Service Connect Endpoint" between Cloud Run's VPC egress and a Cloud VPN to on-prem Oracle; PSC fronts published services/Google APIs, not a VPN route — the diagram's middle box does nothing |
| part38-prototype-to-production-zh.md | 331 | 2 | 4 | 4 | 4 | 2 | 3 | 3.2 | Needs revision | L276/L304/L323 "總計 8 個工作天" but the checklist L250–274 sums to 10 (2+2+1+2+1+2); 差距 4 錯誤處理 is promised at L44 and has no section (二/三/四/五 cover gaps 1, 2, 3, 5) |
| part39-scalability-zh.md | 724 | 2 | 4 | 3 | 4 | 3 | 4 | 3.3 | Not ready | L249–251 "10,000 並發 × 8s = 80,000 連接" is dimensionally wrong and "1,000 RPM → 17 個並發" ignores latency (16.7 rps × 8 s ≈ 133); L696 ROI computes the 55% saving on the *post-cache* $1.5M base; L678 $4.00→$2.50→$1.50 does not follow from 30%/55% hit rates (2.80/1.80) |

Overall = unweighted mean (no finance posts). Model-answer sections and the series-format warnings are scored
as minor on these pre-rule posts; verdicts turn on content findings. "Not ready" is reserved for a wrong number
or command that a reader would paste into a CFO deck (29, 39) or a terminal (30).

## Patterns

### Content quality
- Parts 35–39 share a template — 面試情境 → 核心問題 → mechanism sections → 系統效應 table → 面試答題要點 — and it
  produces the best posts in the batch when the middle is real (35 L59–130 span tree; 37 L93–192 three
  integration patterns; 36 L80–123 golden-set design). Part 35 is the model: every number in it recomputes.
- Parts 27–30 are consultant-skill posts with almost nothing to check; the one that computes (29) is where
  the batch's worst arithmetic lives (L251–264). Part 27 has no numbers, no flip conditions and no "when
  this fails" — it is a meeting agenda (L48–57) plus a scope template (L160–206).
- Part 34 is 671 lines of six scenarios with 0 diagrams; each 追問鏈 lists five questions but the 模範答案 answers
  two or three (scenario 2 Q3/Q4 at L167–169 unanswered; scenario 3 Q2–Q4 at L261–265; scenario 4 Q4 L364;
  scenario 5 Q4 L459; scenario 6 Q1/Q3 L553–557). The unanswered ones are the harder, mechanism questions.
- The 地雷題 blocks in 31 (L365–427) and 32 (L440–500) are the strongest interview content: each has a sharp
  follow-up and a mechanism-level answer with a flip condition (31 L411–427 "什麼時候放棄 ADK").
- Model-answer sections survive in every post: 面試回答完整示範 / 關鍵訊號 / 完整框架 at 27 L268, 28 L282, 29 L312,
  30 L280, 31 L433, 32 L505 (invisible to the checker, which greps only 「面試答題要點」) and 面試答題要點 at
  35 L306, 36 L315, 37 L333, 38 L317, 39 L710.

### Structure (does the house format help or pad?)
- Only part 39 has the format. Its 三個演進階段 (L61–172) is the strongest section in the post: each phase
  lists the new components, what is solved, what remains, and a cost delta — this is the format working.
- Its 為什麼選 X 不選 Y section (L586–672) is 60% duplicate: decision 2 (L609) restates 五 L325–340 word for
  word ("今天天氣如何"), decision 4 (L634) restates the token-bucket block at 六 L483–500, decision 6 (L660)
  restates 八 L510–520, decision 1 (L588) restates 三's Redis rationale. Only decision 5 (L647–656) carries a
  real flip condition (shard when the primary is write-bound, >10k WPS). The consolidated table is padding
  when the decisions were already argued in place.
- The 十 section cap bites: 39 pushes the model answer to 十一 (L710) rather than dropping it.
- The 系統效應 "有 X / 沒有 X" two-column table (35 L249, 36 L290, 37 L305, 38 L283, 39 L673) is the one piece of
  template boilerplate repeated across parts; 36's and 38's rows are prose assertions ("工程師信心 可以大膽改"),
  not numbers, and could be cut without loss.
- Part 38's structure is broken independently of the format: five gaps announced (L41–47), four sections
  (二 gap 1, 三 gap 2, 四 gap 3, 五 gap 5); gap 4 錯誤處理 exists only as checklist rows (L262–264).

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Sourced and recomputable: 29 L72–168 (every Gemini/Cloud Run/GCS unit price × volume recomputes, assumptions
  stated and date-stamped), 35 L63–90 and L207–211, 34 L578–584 (TWD budget → Flash fits). These are the
  posts that show their work.
- Invented-looking round numbers with no setup: 32 L87 "Agent Builder 比自建快 10 倍"; 38 L115 "20,000 tokens
  比 2,000 慢 5 倍"; 36 L112 "200 題（P < 0.05）"; 35 L256 "< 1% 延遲增加"; 27 L229 "風險點增加了兩倍";
  39's cache-hit rate stated five ways (40–60% L165, 30–60% L375, 30–50% L367, 50–65% L379, 55% L679).
- Cross-post drift on the same quantity: Flash-vs-Pro saving 40× (29 L184), "原來的 20%" (33 L300), "5 倍"
  (34 L410); Cloud Run cold start 10–30 s (28 L81), 8–12 s (38 L106), 8–15 s (39 L561); min-instances=2 cost
  $10–30/月 (38 L126) vs $50–150/月 (39 L567) — both defensible (idle vs always-allocated CPU) but neither
  states the assumption.
- Flip conditions exist where the author argued in prose (31 L411–427, 32 L440–452, 39 L652–656,
  36 L229–232 "為什麼法律場景用 0.90") and are absent from the comparison tables (31 L52–66, 32 L130–140,
  37 L279–296).
- "When it breaks" is strongest in 35 (L226–239 head-based sampling cannot keep anomalies) and 39 (L175–200
  stateful scale-out paradox); absent in 27, 28, 30, 33.

### Direction (overlap, gaps, stale topics, category fit)
- The insurance "並行查三個系統 → 決策" scenario is used three times: 31 L22 and L433–466, 34 L136–232, 35 L22.
  Three posts, one example.
- Context Caching is explained twice with the same SDK snippet (29 L192–230, 32 L266–318) and the same
  retired-model caveat; keep it in 32 and link from 29.
- Stale product surface: 32 L62–73 describes Agent Builder as Data Store + Playbooks (the 2024 shape); the
  product was re-scoped in 2025 and Vertex AI Search moved under "AI Applications". Marked ❓, not wrong, but
  the post's own L272 and L414 disagree about whether 1.5 Pro is current.
- Part 33 (how the interview is scored) and 34 (mock drills) are the only two posts in the whole series that
  are *about the interview* rather than about a system; they fit the series name better than most of it.
- Categories `["all","ai","engineering"]` on all 13; 30 and 37 are architecture/infrastructure posts and
  39 is a textbook `architecture` post — `engineering` is the lazy default here.

### Accuracy
- Commands a reader would paste: 30 L194–198 (public log viewer on the org); 30 L261–275 (PSC forwarding rule
  to a service attachment, then `vertexai.init(api_endpoint="10.0.0.100")` — a bare IP fails TLS/SNI; the
  Google-APIs PSC pattern uses a private DNS zone); 28 L146–159 (filter window; `entry.http_request` is a
  dict, `.latency` attribute access fails); 36 L198 (`for word in CERTAINTY_WORDS and query_type == …`
  iterates a bool).
- Network-security conflation runs through 30, 34, 37: VPC-SC is presented as the thing that keeps traffic
  off the public internet (30 L91, L245–247) and that pins data to a region (34 L97); PSC is drawn on a VPN
  path to on-prem (37 L255–275). VPC-SC is an API-perimeter control; region pinning is endpoint/org-policy;
  Google-API traffic from a VPC stays on Google's network via Private Google Access regardless.
- Internal contradictions: 31 L311 vs 34 L190–192/L599 (`session:` prefix); 32 L272 vs L414 (1.5 Pro
  retired / current); 38 L276 vs L250–274 (8 vs 10 days); 38 L197 "1 分鐘" vs L296 "< 5 分鐘" rollback;
  36 L151 target 0.92 vs L224 gate 0.90 vs L190 warn 0.88 vs L270 alert 0.85 for one metric;
  39 L140 "< 100ms" vs L357 "< 60ms" cache hit; 39 L51 $0.02/query vs L678 $1.50/50 = $0.03.
- Correct and worth keeping: 31 L305–311 state prefixes (`user:`/`app:`/`temp:`, no `session:`);
  31 L246 `require_confirmation=True` (ADK Python ≥1.14, experimental); 35 tail-based sampling; 37 L254
  Direct VPC egress vs the old connector; 38 L213–217 pin `gemini-2.0-flash-001`.

### Format/front matter
- `weight: N` is set in all 13 (not in the CLAUDE.md template; harmless, tags-list ordering relies on it).
- readTime vs ~32 lines/min: 27 (307 lines, "14 min" ≈ 10), 28 (317, "16" ≈ 10), 30 (350, "17" ≈ 11),
  38 (331, "18" ≈ 10) all over-state; 34 (671, "25" ≈ 21) and 39 (724, "25" ≈ 23) are close.
- Descriptions of 27–30, 32, 33 open with "以 Google FDE…"; 31's *title* is "Google ADK 深度設計". The checker
  flags one line per file; actual counts are 27:3, 29:3, 30:8, 31:13, 32:30, 33:9, 34:9, 38:3.
- 37 L38 uses simplified 并 (should be 並); 29 L208 and 32 L288 ship `MODEL_ID = "..."` and 29 L272 "約 X%",
  28 L239 "$X/月" placeholders in published text.
- Series-nav links all resolve (checked against `content/posts/` filenames, including part 40).

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | part30:L194–198 | `--member="allUsers" --role="roles/logging.viewer"` at org level: makes every log in the organisation world-readable, and is unrelated to enabling Data Access audit logs | Delete the binding; keep only the `auditConfigs` block (L203–208), applied with `gcloud projects set-iam-policy` after `get-iam-policy` |
| 2 | blocker | part29:L251–264 | Headcount model: 10 agents × 200/day = 2,000, model assumes 10,000/day; after AI 4,900 residual queries need ~25 agents at 200/day, not 6; the 335% ROI and 2.8-month payback (L264, L300–303) inherit the error | Either 50 agents × 200/day (then saving = 20 FTE × $50k = $1M) or 10 agents × 1,000/day; recompute ROI |
| 3 | blocker | part39:L249–251 | "10,000 並發 × 8s = 80,000 連接" mixes rate and concurrency; "1,000 RPM → 17 個並發" should be 16.7 rps × 8 s ≈ 133 concurrent | State Little's law once: concurrent = rps × latency; redo both lines |
| 4 | blocker | part39:L676–700 | $4.00→$2.50→$1.50/MAU does not follow from 30%/55% hit rates (2.80/1.80); the "$825,000 節省" is 55% of the *post-cache* $1.5M; 200× ROI inherits both | Pick a pre-cache base ($4.00 × 1M = $4M), apply the hit rate once, and let the table and L696 agree |
| 5 | major | part30:L261–275 | PSC commands target a `serviceAttachment` (the Vertex private-endpoint pattern) but the text is about the Gemini API; `api_endpoint="10.0.0.100"` will fail certificate validation | Use the Google-APIs PSC endpoint + private DNS zone for `*.googleapis.com`, or show the Vertex AI private endpoint pattern end-to-end — not half of each |
| 6 | major | part34:L190–192, L599 | `session:policy_result` etc. — part 31 L311 correctly says ADK has no `session:` prefix | Drop the prefix (unprefixed keys are session scope) |
| 7 | major | part34:L284–287 | "院內的 Cloud DLP 服務" — Cloud DLP is a Google API; calling it sends the raw PHI the scenario forbids sending | Tokenize on-prem (regex/NER in the hospital network) or state that DLP inside the perimeter is acceptable under the clarified constraint |
| 8 | major | part38:L250–276 | Checklist days sum to 10; headline, 系統效應 and model answer all say 8 | Change to 10 or drop a row; also add the missing 差距 4 section (L44 promises it) |
| 9 | major | part36:L224–245 | Example CI report shows baseline 0.87/0.83 under a 0.90/0.85 block gate: `main` would never have passed | Set baseline to ≥ gate (e.g. 0.91/0.86) or show the gate as "vs baseline Δ" only |
| 10 | major | part37:L255–275 | PSC endpoint drawn between Cloud Run egress and Cloud VPN/Interconnect to on-prem; PSC is not part of that path | Draw Cloud Run → Direct VPC egress → Cloud VPN/Interconnect → on-prem; mention PSC only for reaching Google APIs from the perimeter |
| 11 | major | part31:L303, L340, L462; part38:L167 | "Session State 自動持久化到 Firestore / ADK 內建" — documented ADK services are InMemory/Database/VertexAi; Agent Engine persists via VertexAiSessionService | Say "Agent Engine managed sessions (VertexAiSessionService)" or "DatabaseSessionService on Cloud SQL" |
| 12 | major | part33:L21 | "RKK（Role-based Knowledge）" — Google's attribute is Role-Related Knowledge (RRK) | Fix the expansion in the post; decide at series level whether the tag/series name should become RRK (CLAUDE.md mandates "RKK") |
| 13 | major | part34:L379 vs L393 | Offline stage "每小時執行一次" but the call count assumes once a day (1M/day; hourly = 24M/day, a 180× not 4,320× reduction) | Say daily, or recompute with 24M/day |
| 14 | minor | part28:L146–159 | Filter window `2026-06-01T18:00Z…06-04T20:00Z` is one continuous 3-day span, not nightly 2–4 am; `entry.http_request.latency` on a dict | Loop over three per-night windows; use `entry.http_request["latency"]` |
| 15 | minor | part32:L272 vs L414; part29:L335 vs L190 | 1.5 Pro "已退役" vs "撰文時為 … 1.5 Pro"; Flash "$1,000/月" in the model answer vs $90/月 computed in 四 | Align both to one statement |

## Recommendations

1. **Fix the three paste-able errors first (30 L194, 30 L261–275, 29 L251).** WHY: these are the only
   findings where a reader acting on the post is harmed (public logs, broken TLS, an ROI they repeat to a
   CFO). HOW: the fixes in findings 1, 2, 5 are one-block edits; no restructuring needed.
2. **Create one shared "numbers card" for the series and link to it.** WHY: Flash/Pro ratio, cold-start
   seconds, min-instance cost and cache-hit rate are each stated 3–5 different ways across 28–39, and each
   restatement looks invented because none cites the earlier one. HOW: a short table (price date, model,
   assumption) in part 29 or a `docs/` page; later posts quote it with the date.
3. **Resolve the network-security vocabulary once (30, 34, 37).** WHY: VPC-SC, PSC and region pinning are
   used as interchangeable incantations; an interviewer in this domain will catch it. HOW: one paragraph in
   part 30 §六 that says what each control does and does not do, then 34 L97 and 37 L255–275 reference it.
4. **Decide the "no Google" rule's scope at the series level.** WHY: part 31's title, part 33's scoring
   dimension, and 30 mentions in part 32 show the rule cannot apply to the product posts; the checker
   flags one line and the rest is invisible. HOW: either exempt product/vendor nouns (ADK, Gemini, Vertex
   AI, Google Cloud) and keep the ban on "Google FDE / Google 職位" framing, or rename the series; then make
   `review_posts.py` count all occurrences so the policy is visible.
5. **Stop backfilling 三個演進階段 into 27–38; backfill decision prose, not tables.** WHY: part 39 shows the
   phase section earns its place only when a concrete system is being scaled (39, maybe 30 and 37) and the
   consolidated table duplicates what was argued in place (39 L586–672). HOW: for 31/32/36/37 add a flip
   condition line to each existing comparison table; leave 27/28/33/34 without phases.
6. **Finish part 34's 追問鏈 or shorten them.** WHY: the unanswered questions (scenario 3 Q2–Q4, scenario 6
   Q1/Q3) are the mechanism questions the series is supposed to teach, and a reader practising with the post
   has no answer key. HOW: either answer all five per scenario (≈ +120 lines) or list only the three answered.
7. **Add 2–3 diagrams to part 34 and one to part 27.** WHY: 34 is 671 lines with no picture; scenarios 1, 3
   and 4 each describe a three-layer architecture in prose. HOW: reuse the box style from 30 L73–111.
8. **Strip the model-answer sections or convert them to 3-bullet summaries.** WHY: all 13 still end in one,
   under five different headings the checker does not recognise; they repeat the body at lower density.
   HOW: extend `review_posts.py` to match 面試回答完整示範 / 關鍵訊號 / 完整框架 too, then trim.
9. **Fill or remove the placeholders.** WHY: `$X/月` (28 L239), `約 X%` (29 L272), `MODEL_ID = "..."` (29 L208,
   32 L288) read as unfinished drafts. HOW: compute the min-instance cost (28), drop the retention line (29),
   name a current model id with a date (29, 32).
10. **Recalibrate readTime for 27, 28, 30, 38.** WHY: each over-states by ~60%. HOW: ~32 lines/min.

## Verified / unverified claims

- ✅ part29:L72–96 — Gemini 1.5 Pro $3.50/$10.50 per 1M (≤128k, pre-Oct-2024 Gemini API price); $70 + $52.5 =
  $122.5/day → $3,675/month recomputes; labelled as retired pricing.
- ✅ part29:L101–111 — 10,000 × 300 × $0.025/1M = $0.075/day; 50,000 × 400 × $0.025/1M = $0.50 (unit is
  per-1M-*characters* on Vertex, per-token on the post; magnitude unchanged).
- ✅ part29:L146–152 — Cloud Run $0.000024/vCPU-s and $0.0000025/GiB-s: $41.5 + $8.6 ≈ $50 recomputes.
- ✅ part29:L184–190 — Flash $0.075/$0.30: $1.5 + $1.5 = $3/day → $90/month; "約 40 倍" (46.7× / 35×) fair.
- ✅ part29:L226–230 — 1,500 × 10,000 × 30 × 0.75 × $3.5/1M = $1,181.25; the post's own caveat about the
  32,768-token minimum for 1.5-era explicit caching is correct.
- ❌ part29:L251–257 — 10 × 200 = 2,000 ≠ 10,000 queries/day; residual 4,900/day ≠ 6 agents.
- ❌ part29:L325 — "Infra 10–20% ≈ $150": 10–20% of $3,675 is $367–735; the table's infra is $158 = 4.3%.
- ❌ part29:L335 vs L190 — Flash "$1,000/月" vs $90/月.
- ❓ part29:L134–136 — Pinecone "Standard $70/month/1M vectors": Pinecone moved to serverless read/write-unit
  pricing; could not confirm a current $70 tier.
- ❓ part29:L232–236 — "1 年 CUD 節省 20–40%" for Gemini API spend: could not confirm a CUD product for
  generative-AI token usage (Provisioned Throughput commitments exist); treat as unverified.
- ❌ part30:L194–198 — `allUsers` + `roles/logging.viewer` at org level: public log access, not audit-log enablement.
- ✅ part30:L203–208 — `auditConfigs` with `aiplatform.googleapis.com` DATA_READ/DATA_WRITE is the correct mechanism.
- ❓ part30:L211–215 — "每次 Vertex AI 調用會自動記錄 Request 和 Response 的摘要": Data Access logs record the
  call metadata and request; prompt/response bodies are not in audit logs by default; could not confirm "摘要".
- ❓ part30:L261–275 — PSC forwarding rule to a `serviceAttachment` + bare-IP `api_endpoint`: appears to
  conflict with both documented PSC patterns (Google-APIs bundle with private DNS; Vertex private endpoints).
- ❌ part30:L91, L245–247; part34:L97 — VPC-SC described as private routing / region pinning; it is an API
  perimeter control.
- ✅ part31:L160–166 — 750 ms sequential vs 300 ms parallel = 60% saving.
- ✅ part31:L246 — `FunctionTool(..., require_confirmation=True)` exists (ADK Python v1.14.0, experimental).
- ✅ part31:L305–311 — state prefixes `user:` / `app:` / `temp:` and unprefixed = session; no `session:` prefix.
- ❓ part31:L303, L340, L462; part38:L167 — Firestore as ADK's built-in / Agent Engine's session store:
  official docs list InMemory, Database (SQL) and VertexAi session services; a third-party article mentions a
  FirestoreSessionService in some versions. Could not confirm; appears to conflict for Agent Engine.
- ❓ part31:L385–388 — ParallelAgent "錯誤隔離 / per-agent retry policy": not documented ADK features.
- ❓ part31:L342 — Agent Engine "內建 Rate Limiting 和 Auth": could not confirm.
- ✅ part32:L272–275 — $3.50 input / $0.875 cached (75% off) are the pre-Oct-2024 1.5 Pro ≤128k prices;
  $1.00/1M-token-hour storage matches the *reduced* storage price (original was $4.50), so the row mixes two
  price eras but no figure is fabricated.
- ✅ part32:L297–300 — 32,768-token explicit-cache minimum for 1.5-era models; newer models lower.
- ❓ part32:L62–73, L84 — Agent Builder = Data Store + Playbooks + Search: 2024 product shape; re-scoped in 2025.
- ❌ part32:L414 vs L272 — 1.5 Pro both "current" and "retired" in one post.
- ❌ part33:L21 — "RKK = Role-based Knowledge": Google's published attribute is Role-Related Knowledge (RRK),
  alongside GCA, Leadership and Googleyness.
- ✅ part33:L89 — disclaimer that the rubric is illustrative, not official.
- ✅ part34:L164–204 — parallel P95 = max(200, 800, 1500) + 1–2 s LLM ≈ 3–3.5 s; sequential 2,500 ms.
- ❌ part34:L379 vs L393 — hourly precompute = 24M calls/day, not 1M; reduction 180×, not "4,000 倍以上".
- ✅ part34:L578–584 — 22 TWD/200 turns = 0.11 TWD ≈ $0.003; Flash per turn $0.000165; 200 turns $0.033 ≈ 1 TWD.
- ❌ part34:L284 — Cloud DLP "院內" contradicts the scenario's "不能傳送到 Google 的伺服器".
- ✅ part35:L63–90 — span tree sums (15,240 = 280 + 14,700 + 260; 14,650 = 45 + 14,520 + 85); 95.3%.
- ✅ part35:L207–211 — 50,000 QPS × 20 spans × 86,400 s = 86.4B spans/day × $0.20/1M = $17,280/day; Cloud
  Trace list price is $0.20 per million spans ingested.
- ✅ part35:L226–239 — head-based `TraceIdRatioBased` cannot retain anomalies; tail sampling needs a Collector.
- ❓ part35:L92 — "vector index 過大，缺少 min-instances，每次 cold query 重新載入" as the root cause of a 14.5 s
  query: asserted, not derived.
- ❓ part36:L112 — "200 題 → P < 0.05": significance depends on effect size; unsourced.
- ❌ part36:L244–245 vs L224–225 — baseline fails its own gate.
- ❌ part36:L198 — `any(word in response for word in CERTAINTY_WORDS and query_type == "legal_advice")`
  iterates over a bool.
- ✅ part36:L290–301 — 200 × $0.002 = $0.40 per CI run; the post labels $0.002/judge-call as illustrative.
- ✅ part37:L254 — Cloud Run Direct VPC egress is current; Serverless VPC Access connector is the older path.
- ❌ part37:L255–275 — PSC endpoint on the VPN path to on-prem.
- ✅ part37:L222–232 — `bigquery.ScalarQueryParameter("date", "DATE", date)` parameterised query is correct.
- ✅ part38:L60–66 — 2,000 + 4 × 800 = 5,200; 2,000 + 14 × 800 = 13,200; $0.015 → $0.12 = 8×.
- ❌ part38:L250–276 — checklist sums to 10 days, headline says 8.
- ✅ part38:L213–217 — pinning `gemini-2.0-flash-001` vs alias `gemini-2.0-flash` is correct practice.
- ✅ part38:L238–239 — `gcloud run services update-traffic SVC --to-revisions=REV=100` is valid syntax.
- ❓ part38:L115 — "20,000 tokens 比 2,000 慢 5 倍": no measurement or model named.
- ✅ part39:L51 — 1M × 50 × $0.02 = $1M/month.
- ❌ part39:L249–251 — Little's-law misuse (see finding 3).
- ✅ part39:L250 — Cloud Run default concurrency = 80.
- ✅ part39:L475–476 — 1 token/10 ms = 100 tokens/s.
- ✅ part39:L531–536 — 100 instances × 50 = 5,000 connections vs PostgreSQL default max_connections 100.
- ✅ part39:L573 — 2 × 0.5 vCPU × $0.00002 × 86,400 × 30 ≈ $52/month recomputes (price is approximate).
- ❌ part39:L676–700 — per-MAU ladder and ROI base (see finding 4).
- ❓ part39:L165, L367, L375, L379 — semantic-cache hit rates 30–65%: no source, five different ranges.
