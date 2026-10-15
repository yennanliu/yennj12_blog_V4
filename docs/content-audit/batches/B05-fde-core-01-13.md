# B05-fde-core-01-13 — fde-core-concept parts 1–13 ("FDE Core Topics")

Reviewed 2026-10-09. 13 Traditional-Chinese interview-prep posts (5,407 lines), every post read in full, derived
numbers recomputed with python3, nine product facts checked on the web (Cloud KMS price list and default quota,
Cloud Run GPU types, ADK `LoopAgent` parameters, Gemini Flash price list, Sensitive Data Protection price list,
Spanner billing model, Elasticsearch `rrf` retriever, the `gcp.disableCloudKMSCryptoKeyVersionExternalImport`
constraint). Mechanical baseline (`inputs/mechanical-baseline.txt` L8–13): parts 3, 5, 9, 12 "mention Google" —
all four are product strings (`from google.adk.agents` 3:162, `discoveryengine.googleapis.com` 5:126,
`asia-east1-aiplatform.googleapis.com` 9:145, a comment `套件名為 google-cloud-pubsub` 12:195; only the last is
removable). The checker reports nothing else, which matters: this series does **not** use the literal
三個演進階段 heading (every post has 三、三個實作層次 with Layer 1/2/3 instead), has no 面試答題要點, and the
checker's series rules evidently do not fire on the `fde-core-concept-*` slug — so none of the format drift below
is in the baseline.

**Premise check for the coordinator.** These posts are the "mechanism" twins of the interview-guide posts B04
flagged. They are shorter (214–498 lines, none reaches the 600-line floor), carry a single 10:00 timestamp on
2026-06-08, and use a lighter template: 核心定義 → 為什麼面試官問這個 (弱答/強答) → 核心原理 → 三個實作層次 →
常見錯誤 → 關聯 → 面試一句話（Killer Phrase）. Only 7 of 13 have a 為什麼選 X 不選 Y table (1, 3, 7, 8, 9, 10, 11; 12
has an algorithm table that serves the purpose, 13 a decision tree, 2/4/5/6 nothing), and only 4 have a 系統效應
table (1, 7, 8, 11). The "Killer Phrase" block is the model-answer section under another name; 7 adds 面試常見追問與答法
and 9 scores 弱答/中答/強答 out of 10. The format is lighter than the fde-interview-guide one and the numbers are
*less* contradictory than B04's — but the same failure class is present: the deepest posts (8, 10, 11, 12) each
contain one invented cost model or misdescribed mechanism that a reader would build on.

## Batch summary

Content quality is good at the concept level in every post: each picks one real tension (FIFO loses the role
prompt, RRF fuses ranks not scores, the unprivileged scraper has no VPC path, CAS defeats split-brain, the bucket
rejects but the queue absorbs) and the 弱答/強答 contrast at the top is consistently the best paragraph. Clarity
scores 4–5 across the batch; visuals are 4–5 in ten posts. Accuracy is where it fails, in three recurring ways.
(1) **Verified-wrong product facts**: Cloud Run has no T4 GPU (6:164), Cloud KMS software key versions are $0.06
not ~$1/month (10:283), KMS ops are $0.03/10K not $0.06 (8:271), the default KMS quota is 60,000 QPM not 600
(8:450), ADK `LoopAgent` has no `should_continue_condition` (3:169), and `constraints/gcp.disableCloudKMSCryptoKeyVersionExternalImport`
does not exist (9:435). (2) **Misdescribed mechanisms**: 4 says lowering RRF's k makes "the strong modality
dominate" (it is symmetric; weighted RRF is the fix), 8's FPE diagram outputs `TKN_b8d91` for a phone number (not
format-preserving) and gives GDPR a k≥5 "safe harbor" it does not have, 9 says HIPAA forbids PHI leaving the US
(HIPAA has no localisation rule), 10 conflates KMS KEK rotation with DEK rotation and designs a customer-side DEK
cache inside managed Vertex AI inference, 13 argues `version_id` in the idempotency key should make a retry a *new*
call (the opposite of exactly-once). (3) **Numbers that do not survive recomputation**: 11's Firestore polling cost
is wrong by 10⁴ in two places that also disagree with each other ($5,000/月 at L276 vs $1,800/月 at L307; the real
figures are ~$31K and $0.18), 12's "50K req/s 總開銷 40 ms" column is dimensionless and its 15× burst drains in 6
minutes while the 系統效應 table claims P99 < 2 s, 13 bills Spanner per operation (it has no per-op charge) and
still gets its own arithmetic 10× wrong. Cross-references are systematically broken: eight posts cite "本系列 Part N"
topics from an earlier outline that does not match the published series (e.g. 1:452 "Part 2 RAG 架構設計", 5:291
"Part 3 向量資料庫", 11:397 "Part 7 LLM Serving / Part 19 Cost Engineering"), and 12:446 cites slugs
(`fde-interview-core-topic-11-…`) that do not exist. Verdicts: **0 Ready**, **6 Needs revision** (1, 2, 4, 5, 7,
13), **7 Not ready** (3, 6, 8, 9, 10, 11, 12).

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-context-management-zh.md | 467 | 3 | 5 | 4 | 4 | 4 | 4 | 4.0 | Needs revision | L124–125 worked importance scores do not follow the formula at L112–118: Turn 1 = 0.3×0.08+0.5×0.9+0.2×1.0 = 0.674, not 0.75; Turn 20 recency exp(−0.05×30) = 0.22, not 0.37. L27 強答案 budgets history 80K / reserve 28K while the body (L48–55, L459) uses 92K / 16K. L179 "32,400K". L452 cites "本系列 Part 2 RAG 架構設計" (Part 2 is Memory) |
| 2-memory-architecture-zh.md | 291 | 3 | 4 | 3 | 3 | 3 | 4 | 3.3 | Needs revision | L154–160 `Score = Importance × Recency` with Importance = LLM 1–5 × 30-day access count and Recency ≤ 1, then thresholds 0.3/0.1 — the scales are incompatible, only never-accessed items can ever fall below 0.3. L248 "100M vectors ~$1,200/月" is far below Vector Search serving-node cost for 100M×768-d. No decision table, no flip conditions; L279 "Core Topic 5 — RAG Pipeline" (5 is Reranking) |
| 3-state-machine-dag-zh.md | 448 | 2 | 4 | 4 | 4 | 4 | 4 | 3.7 | Not ready | L169 `LoopAgent(…, should_continue_condition=lambda …)` — ADK's LoopAgent takes `name/sub_agents/max_iterations`; early exit is `tool_context.actions.escalate` (adk.dev, verified). L54 "百萬 QPS … 數千美元/天": $0.01 × 10⁶/s is ~$864M/day. L430 "even if `evaluate_node` is injected to output score = 1.0 the edge cannot be bypassed" — routing to approve on an injected 1.0 *is* the bypass. L106 "KeyError on unknown keys" ❓ |
| 4-hybrid-search-rrf-zh.md | 433 | 3 | 5 | 4 | 5 | 4 | 4 | 4.2 | Needs revision | L29 / L163 / L407: "when one modality is much stronger, lower k to 10–30 to let the strong one dominate" — RRF's k is symmetric across lists; a lower k sharpens rank-1 vs rank-10 in *both* lists and cannot favour a modality (that is weighted RRF). L211/338/392 `text-ranking-gecko@003` ❓ (Vertex ranking models are `semantic-ranker-*`). L372 the two Weaviate boxes are labelled Dense/Sparse but captioned 租戶 A / 租戶 B. L419–421 cites Parts 3/5/6 as Embedding/Vector-DB/Reranking |
| 5-reranking-cross-encoder-zh.md | 306 | 3 | 4 | 3 | 4 | 3 | 4 | 3.5 | Needs revision | L139 Ranking API "$0.002 per 50 records" ❓ (third-party listings say ~$1/1,000 queries; could not read the official page). L279 "10萬文件 ~1000 秒" implies 10 ms/doc while L85 prices 50 docs at 150 ms (3 ms/doc → 300 s). L191 MiniLM-L-6 "22MB" (22M params, ~90 MB). L117 "−90% tokens → cost × 0.15". L291–293 cites Parts 3/4/6 as Vector-DB/RAG/Embedding. No decision table |
| 6-prompt-injection-jailbreak-zh.md | 214 | 2 | 4 | 2 | 3 | 2 | 4 | 2.8 | Not ready | L164 "BERT 推理需 1 個 T4 GPU（$0.35/hr on Cloud Run）" — Cloud Run offers only L4 and RTX PRO 6000 (docs.cloud.google.com, verified); "Cloud DLP API $1/1000 次掃描" — Sensitive Data Protection bills per GB ($3/GB content inspection). L27/77/110 the 94% interception rate is "示意" three times and is still the post's headline number. One diagram, no decision table, no 系統效應; L200–203 cites Parts 9/11/14 as RAG-security/Tool-calling/Observability. Near-duplicate of 7 and of fde-interview-guide 13/45 |
| 7-indirect-prompt-injection-zh.md | 435 | 4 | 5 | 4 | 4 | 4 | 3 | 4.0 | Needs revision | L107–110 and L158–159 the `INVISIBLE_CHARS` regex holds literal U+200B/U+200C/U+200D/U+FEFF/U+00AD/U+2060… in the source (6 lines carry zero-width characters) — it renders as an empty character class and breaks on copy-paste; write `​` escapes. L429 "危險十倍" unsourced. L139 "$0.00015 vs $0.0015/頁" invented per-page costs. Otherwise the best post in the batch: correct Pydantic v2, NFC claim correctly scoped to invisible chars, real flip conditions |
| 8-pii-deidentification-zh.md | 457 | 2 | 4 | 4 | 4 | 3 | 4 | 3.5 | Not ready | L62 "GDPR safe harbor 通常要求 k ≥ 5" — GDPR defines no k; "Safe Harbor" is the HIPAA §164.514(b) de-identification method (also conflated at L207, L339). L112–116 the FPE diagram turns `0912-345-678` into `TKN_b8d91`, which is not format-preserving — it contradicts the definition at L82–90. L450 KMS "預設 600 req/min" (60,000 QPM, verified); L271 KMS "$0.06/10,000 操作" ($0.03, verified). L367 p99 180 ms vs L447 trace total 235 ms. L412 section 十 comes after the 九 Killer Phrase |
| 9-data-residence-sovereign-ai-zh.md | 462 | 2 | 4 | 4 | 4 | 4 | 4 | 3.7 | Not ready | L21 "HIPAA 的「PHI 不得離開美國」" — HIPAA has no data-localisation requirement; a reader would cite this to a compliance officer. L435 `constraints/gcp.disableCloudKMSCryptoKeyVersionExternalImport` not in the Cloud KMS constraint list (searched; only `gcp.resourceLocations`, `cloudkms.allowedProtectionLevels` exist). L142 "全球端點（預設）" — Vertex AI's default endpoint is regional; L193 `BatchPredictionJob.create(dedicated_resources_machine_type=…)` ❓ (SDK name is `machine_type`); L170 `vertexai.init(client_options=…)` ❓; L178 `gemini-1.5-pro` retired. L304 "AWS CloudHSM" as an on-prem HSM. L444–450 cites Parts 5/6/11/15 as IAM/Serving/Multi-tenant/Incident-response |
| 10-cmek-byok-envelope-zh.md | 498 | 2 | 4 | 4 | 4 | 4 | 4 | 3.7 | Not ready | L268/L145 "預設 DEK 輪換政策（90 天）" conflates Cloud KMS *KEK* rotation with the DEK; L98–110 and L254/356/492 design a customer-controlled DEK cache "in the Vertex AI Inference Pod (Confidential VM)" with a 1 h TTL — managed Vertex AI exposes no such enclave or cache (same invented mechanism B04 found in part 46:452–483). L283 software KEK "~$1/密鑰版本/月" ($0.06; $1 is the HSM rate, verified). L216 KAJ JSON with `resource/operation/principalEmail` ❓ (KAJ carries a reason code). L273 "HIPAA Safe Harbor" as an audit requirement. L119/329 "AWS CloudHSM" as on-prem. Cleaner than part 46: cost figures are consistent and the 四 tables carry real flip conditions |
| 11-async-event-driven-pipeline-zh.md | 452 | 2 | 5 | 4 | 5 | 5 | 4 | 4.2 | Not ready | L276/387 "20,000 reads/s ≈ $0.06/s = $5,000/月" — at $0.06/100K reads that is $0.012/s and ~$31,100/月; L307 "10,000 users × 30 reads × $0.06/100K = $1,800/月" computes to $0.18. L226 the worker keys the job by `message.message_id` while the web server created the Firestore doc under `job_id = UUID4` (L82) and the client polls that UUID — results are written where nobody reads them; L249 writes `status: "error"` then `nack()`, so the redelivery hits `try_claim` as non-pending and is acked without retry. L427 "400× P50" (2–30 s / 50 ms = 40–600×). Best structure in the batch (六 decision table with flip column, 七 系統效應 with a Flip Point) |
| 12-backpressure-fair-share-zh.md | 460 | 2 | 4 | 4 | 4 | 3 | 3 | 3.3 | Not ready | L118–122 "50K req/s 總開銷 40 ms / 1,000 ms / 750 ms" is 50 × P99 in no unit, and L455 repeats it as "差距從 25 ms 放大到 750 ms". L222–226 burst: 45K×30 − 25K = 1,325K not "~1.1M"; draining at 3K/s takes 6–7 min, yet L431 claims "15× 突發下 P99 < 2 秒". L436 Redis "~50 MB（每桶 ~100 bytes × 500）" vs L440 "= 50 KB". L51 bucket miss = "reject(429) or enqueue" but L165 routes allowed=0 to HTTP 429 and only allowed=1 to Pub/Sub — the "Token Bucket 持續排隊" chain at L215 has no path. L446–448 cite non-existent slugs `fde-interview-core-topic-{11,3,9}`; L424 heading 四-B; L78/83 `local tokens` declared twice |
| 13-idempotency-state-recovery-zh.md | 469 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L235/L435 "Spanner read/write unit 成本 $0.003 / $0.009 per million ops … ≈ $0.18/天" — Spanner bills compute per node/PU-hour plus storage, not per operation, and 2M writes × $0.009/M would be $0.018 anyway. L197–202 argues `version_id` in the key makes a re-execution "不同 key，新的呼叫" and that dedup would be a *misjudgement* — that is a second side effect, the thing the post exists to prevent (the protocol at L117–130 only bumps version on CAS success, so the paragraph contradicts the protocol). L241 the `update_state()` subsection sits under 三、三個實作層次 before Layer 1. `update_state(config, values, as_node=…)` + `stream(None, config)` at L255–266 is the real LangGraph API — the better version of part 43's recovery |

Overall = unweighted mean (no finance posts). Killer-Phrase / 追問 blocks and the missing 600-line floor are
house-rule warnings scored as minor; verdicts turn on content. "Not ready" is reserved for a verified-wrong fact,
an invented API/constraint, a misdescribed mechanism a reader would build on, or invented data a reader would put in
a cost deck.

## Patterns

### Content quality
- The 核心定義 one-liner at the top of every post is a real thesis (1:13, 7:13, 11:13, 12:13, 13:13) and the 弱答/強答 contrast that follows is the strongest writing in each post. The problem is never "what is the idea".
- The deepest posts are the ones with the worst single error: 8 (FPE/DP/synthetic data, 457 lines) carries the GDPR-k≥5 and non-format-preserving diagram; 10 (envelope encryption, 498 lines) carries the DEK/KEK conflation; 11 (best-structured) carries the 10⁴-off Firestore numbers and a job-key bug; 12 carries a dimensionless latency column.
- 7 is the post to model: Pydantic v2 code that runs (7:244–263), `urlparse().netloc` exact-match with the `approved.com.evil.com` counter-example (7:283, 7:409), a decision table whose flip conditions are specific (7:139–145), and a symptom→diagnosis table (7:396–404). Its only serious defect is formatting (literal zero-width characters).
- 6 is the weakest: 214 lines, one diagram, "示意" attached to its own headline number three times (6:27, 6:77, 6:110), and it restates 7's indirect-injection content in one table row (6:187).

### Structure (does the house format help or pad?)
- The lighter template (no 面試情境, no phase diagrams per layer, no 延伸問題) is a better fit for "core concept" posts than the B04 format, and the 常見錯誤與陷阱 tables (every post) are consistently useful. But the template is applied unevenly: 7/13 have a 為什麼選 X 不選 Y table, 4/13 a 系統效應 table, 3/13 (7, 8, 10) a symptom→diagnosis chain. 2, 4, 5, 6 have no decision table at all, and 4 is the post where a decision (k, fusion method, reranker placement) matters most.
- The Layer 1/2/3 sections pad when the mechanism does not change: 2:166–252 (Redis single → cluster → CMEK), 6:120–166 (built-in filter → classifier → allowlist), 9:230–337 (region pin → VPC-SC → GDC) read as feature tiers rather than architectural steps. They help when each layer adds a mechanism: 7 (sanitiser → dual-model → HMAC/quarantine), 11 (queue → idempotency/DLQ/SSE → KEDA/CMEK), 13 (in-memory → Spanner CAS → multi-region + checkpointer).
- Section order drifts: 8 puts 十、症狀診斷 after 九、Killer Phrase (8:412); 12 numbers a section 四-B (12:424); 13 opens 三、三個實作層次 with a subsection about `update_state()` that belongs in 二 (13:241); 11 places 為什麼選 X 不選 Y (六) after 關聯 (五).
- Every post ends with 面試一句話（Killer Phrase）, a 150–250-word model answer; 7 adds 面試常見追問與答法 (7:415) and 9 scores answers "5 分 / 7 分 / 9–10 分" (9:25–29). CLAUDE.md dropped 面試答題要點 from the series; these are the same section renamed.

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Honest labelling is better than B04: 4:13, 5:21, 6:27, 7:122, 13:21 all mark their headline figures as "示意量級". But a "示意" label does not stop the number from being reused as fact later in the same post (4:410 "融合後 Recall 反而低於單用 Dense", 5:302, 6:110).
- Verified-wrong product numbers: 6:164 (T4 on Cloud Run; DLP per-request pricing), 8:271 (KMS $0.06/10K), 8:450 (KMS 600 req/min), 10:283 (software key $1/month). Posts 7:347 and 9:259 have the KMS op price right ($0.03/10K) — the series contradicts itself across posts on the same fact.
- Dimensionally broken numbers: 3:54 (10⁶ QPS × $0.01 = "數千美元/天"), 11:276/307 (Firestore reads), 12:118 (latency × QPS = "ms"), 13:235 (per-op Spanner), 12:224 (burst arithmetic).
- Flip conditions exist and are mostly specific where tables exist (1:414–419, 3:397–402, 7:139–145, 9:380–384, 10:391–450, 11:412–417). 11:421 adds a real "Flip Point" (< 500 ms LLM latency → stay synchronous). 2, 4, 5, 6 have none.
- "When it breaks" is covered by the 常見錯誤 tables, and 7/8/10 add symptom→diagnosis chains with the signal named (7:396–404, 8:416–451, 10:452–476). 12 and 13 promise observability metrics but give no symptom chain.

### Direction (overlap, gaps, stale topics, category fit)
- Every post in this batch has an interview-guide twin: 1↔part 10 (and 44), 2↔14/18/51, 3↔7/25, 4↔1/5, 5↔5/6, 6↔13/45, 7↔20/45, 8↔40, 9↔30/46, 10↔46, 11↔21/43, 12↔23, 13↔43/21. Which is the better version, where B04 reviewed the twin: **7 > 45** (45 is Not ready on NFC/NUL-byte grounds; 7's NFC claim is correctly scoped), **13 > 43** (13 uses the real `update_state(as_node=)` API; 43 invented two), **10 > 46** (10 has no self-contradicting cost table, but both share the invented DEK-cache mechanism), **1 > 44** (1's budget math is internally consistent bar L27; 44 has the $15M/$3.58M split), **8 ≈ 40** (different blockers: 40's ephemeral-vs-stable token, 8's GDPR/FPE). 6 is worse than both 7 and part 13 and should be folded into 7.
- Cross-references point at a series that was never published: 1:452–456, 2:279, 4:419–421, 5:291–293, 6:200–203, 8:399–402, 9:444–450, 11:397–403 cite "Part N" topics (RAG pipeline, Embedding fine-tuning, Vector DB, 資料治理, Observability, Cost Engineering, 微調資料, 安全事件回應) that do not match fde-core-concept 14–25 (speculative fan-out, vector drift, TTFT, context caching, model routing, LLM judge, RAG triad, discovery, troubleshooting, stakeholder mapping, POC scoring, value story). 12:446–448 cites slugs with a `fde-interview-core-topic-` prefix that does not exist. Only 10:479–485 and 13:420–426 cross-reference correctly.
- Stale: 1:333/414 Gemini Flash "$0.075/1M" is the Gemini 1.5 Flash price; the current price list shows 2.5 Flash at $0.30 and no 1.5 line. 9:178 `gemini-1.5-pro` is retired. 3:6/159/185 "ADK 2.0" could not be confirmed as a released major.
- Category fit: all 13 are `["all", "engineering"]`. 6, 7, 8, 9, 10 are security/compliance and 11, 12, 13 are distributed-systems; `architecture` would fit 9–13 better, and 3/13 (LangGraph/ADK) could carry `ai`.

### Accuracy
- Mechanism errors a reader would implement: 4:29/163 (lower k ≠ weight a modality), 8:112–116 (FPE output not format-preserving), 10:98–110 (DEK cache inside managed inference), 11:226 vs 11:82 (job keyed two ways), 11:249 (nack after terminal write never retries), 13:197–202 (retry as new call), 12:51 vs 12:165 (bucket rejects, does not queue), 3:430 (injected score = 1.0 *is* the bypass).
- Invented APIs / constraints: 3:169 `should_continue_condition` (verified absent), 9:435 org-policy constraint (not found), 9:193 `dedicated_resources_machine_type` ❓, 9:170 `vertexai.init(client_options=…)` ❓, 4:211 `text-ranking-gecko@003` ❓, 2:275 ADK `MemoryBankService` with `top_k`/`similarity_threshold` ❓.
- Legal/regulatory claims: 9:21 HIPAA localisation (wrong), 8:62/207/339 GDPR "safe harbor k≥5" (wrong), 10:273 "HIPAA Safe Harbor" as an audit standard (wrong usage). 8:53 attributes Sweeney's 87% to zip+age+gender; the 87% figure is for zip + full date of birth + gender.
- Internal inconsistencies within one post: 1:27 vs 1:48–55 (80K/28K vs 92K/16K), 1:124–125 (worked scores), 8:367 vs 8:447 (180 vs 235 ms), 12:436 vs 12:440 (50 MB vs 50 KB), 12:224 vs 12:431 (6-min drain vs P99 < 2 s), 11:276 vs 11:307 ($5,000 vs $1,800 for the same polling bill), 5:85 vs 5:279 (3 ms vs 10 ms per doc).

### Format / front matter
- All 13 share `date: 2026-06-08T10:00:00+08:00` — identical to interview-guide parts 40–42's 10:00 slot, so date-sorted lists interleave the two series arbitrarily. Titles use an English prefix "FDE core topic - " on Chinese posts; the series name appears as "FDE Interview Core Topics" (3:439), "FDE 面試核心主題" (11:452) and "fde-core-topic" (tags).
- Every post carries a `weight:` front-matter key (1–13) that the post templates do not use for ordering, and the tag `"Cloud"` alongside `"RKK"`/`"Interview"` as the house rule requires.
- `readTime: "18 min"` on nine posts of 306–498 lines (≈ 10–16 min at 32 lines/min); 6 says "10 min" for 214 lines (≈ 7).
- 7:43–44, 7:107–110, 7:158–159 contain literal zero-width characters (U+200B/C/D, U+FEFF, U+00AD, U+2060–2064); `file` classifies 3, 7 and 20 as "Python script text executable". 12:446–448 wraps non-existent slugs in backticks rather than links, so `check_links.py` cannot see them.
- Internal links (系列導航) are all root-absolute and resolve; 2 and 4 link to the wrong-topic "Part N" only in prose, not in hrefs, so the link checker passes.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | 11:276, 11:307, 11:387 | Firestore polling cost stated as "$0.06/s = $5,000/月" and separately "$1,800/月"; at $0.06 per 100K reads the two scenarios compute to ~$31,100/月 and $0.18 | Recompute both with the stated rate; keep one scenario (10K users × 2 reads/s) and derive the SSE saving from it |
| 2 | blocker | 11:226 vs 11:82, 11:249 | Worker keys the job by `message.message_id`; the web server and client use `job_id = UUID4` — results land in a document nobody reads. `nack()` after writing `status: "error"` means the redelivery is claimed as non-pending and acked, so nothing retries | Put `job_id` in the message payload and key on it; on failure leave status `pending` (or write `retrying`) before `nack()` |
| 3 | blocker | 3:169 | `LoopAgent(should_continue_condition=…)` is not an ADK parameter; loops exit via `max_iterations` or `tool_context.actions.escalate = True` | Replace with the escalate pattern from adk.dev; drop "ADK 2.0" unless a 2.x release is cited |
| 4 | blocker | 9:21, 9:435 | "HIPAA: PHI 不得離開美國" — HIPAA has no residency rule; `constraints/gcp.disableCloudKMSCryptoKeyVersionExternalImport` does not exist | Replace HIPAA with a real localisation regime (e.g. 金管會 outsourcing rules, GDPR Ch. V transfers); use `constraints/cloudkms.allowedProtectionLevels` / `gcp.resourceLocations` |
| 5 | blocker | 8:62, 8:112–116 | GDPR has no k≥5 "safe harbor" (that is HIPAA §164.514(b)); the FPE diagram's `TKN_b8d91` for `0912-345-678` is not format-preserving | Say "HIPAA Safe Harbor / Expert Determination; GDPR Recital 26 reasonable-means test"; show FF1 output as a 10-digit number (e.g. `0471-882-903`) |
| 6 | blocker | 10:98–110, 10:254, 10:268 | Customer-side DEK cache with 1 h TTL "in the Vertex AI Inference Pod (Confidential VM)" — managed Vertex AI exposes no enclave or DEK cache; "預設 DEK 輪換 90 天" is the Cloud KMS *KEK* rotation default | Describe CMEK on Vertex AI as `encryptionSpec.kmsKeyName` + KAJ/EKM policy; move the DEK-cache design to a self-hosted inference section and label it as such |
| 7 | blocker | 6:164 | "1 個 T4 GPU（$0.35/hr on Cloud Run）" and "Cloud DLP API $1/1000 次掃描" — Cloud Run offers L4 / RTX PRO 6000 only; Sensitive Data Protection bills per GB ($3/GB content inspection) | Use L4 pricing and per-GB DLP pricing, or drop the numbers |
| 8 | major | 4:29, 4:163, 4:407 | "Lower k to 20–30 so the stronger modality dominates" — k is applied to both lists; it cannot weight one modality | Replace with weighted RRF (`w_dense/(k+r)`) or Elasticsearch `linear`/per-retriever `weight` (9.2+) as the fix; keep k as the rank-compression knob |
| 9 | major | 12:118–122, 12:455 | "50K req/s 總開銷 40 ms / 1,000 ms / 750 ms" is P99 × 50 with no unit; the killer phrase repeats "25 ms → 750 ms" | Express the rate-limit tax as added p99 per request and as Redis/DB CPU-seconds per second (50K × 0.8 ms = 40 core-s/s), then say which one becomes the bottleneck |
| 10 | major | 12:222–226 vs 12:431 | Burst drains in 6–7 min at 3K/s (and 45K×30−25K = 1.325M, not 1.1M) while 系統效應 claims "15× 突發下 P99 < 2 秒" | Let KEDA scale in the worked example (that is its point) and report the resulting P99, or change the After cell to "no 503s; queue wait ≤ N min" |
| 11 | major | 13:197–202, 13:235 | `version_id` in the idempotency key is argued to make a re-execution a *new* call (defeats exactly-once); Spanner "$0.003/$0.009 per million ops" is not how Spanner bills (and 2M × $0.009/M = $0.018, not $0.18) | Key on `(user_id, step_id, attempt_version)` where version is fixed until CAS succeeds and say so; cost Spanner as node/PU-hours + storage |
| 12 | major | 7:107–110, 7:158–159 | Regex character class holds literal zero-width characters; renders invisibly and breaks when copied | Use `​-‏ -‮⁠-⁤﻿­` escapes |
| 13 | major | 1:124–125, 1:27 | Worked scores 0.75 / recency 0.37 do not follow the formula (0.674 / 0.22); 強答案 budget (80K/28K) differs from the body (92K/16K) | Recompute the three example rows; align L27 with L48–55 |
| 14 | major | 8:450, 8:271, 10:283 | KMS "預設 600 req/min" (60,000 QPM), "$0.06/10,000 操作" ($0.03), software key "$1/版本/月" ($0.06) — all verified against the KMS price/quota pages; 7:347 and 9:259 have the op price right | Fix the three figures; add one KMS pricing line that all five posts share |
| 15 | minor | 1:452, 2:279, 4:419, 5:291, 6:200, 8:399, 9:444, 11:397, 12:446 | "本系列 Part N" cites topics from an unpublished outline; 12 cites non-existent slugs | Re-point each to the real fde-core-concept 14–25 title or to the interview-guide twin; link them so `check_links.py --strict` guards them |

## Recommendations

1. **Fix the seven blockers before anything else** (findings 1–7). WHY: each is a number or API a reader would copy into a design doc or a cost sheet, and three (3, 6, 9's constraint) fail the moment someone runs them. HOW: the edits are local (one code block, one table row, one sentence each); none requires restructuring.
2. **Adopt a shared "GCP price card" for the series.** WHY: five posts quote Cloud KMS and three quote DLP/Firestore/Spanner with four different (and partly wrong) values; the series contradicts itself on facts that do not change by post. HOW: a short table in `docs/` (KMS $0.06/version-month software, $0.03/10K ops; SDP $3/GB content inspection; Firestore $0.06/100K reads; Spanner $0.90/node-h regional, nam6 multi-region ≈ $9/node-h) with a date stamp, and every post links or copies it verbatim.
3. **Recompute every derived number with the stated inputs** (findings 1, 9, 10, 11, 13; also 3:54, 5:279, 11:427). WHY: B04 found the same class in parts 43–52; here it is fewer per post but still present in 7 of 13. HOW: for each 系統效應 / 成本 line, keep the formula next to the result (`20,000 r/s × 2.6M s/月 × $0.06/100K = $31K`); the writer skill's self-review should include a python recompute.
4. **Decide the fate of the near-duplicate pairs.** WHY: every post here has an interview-guide twin and readers/search see two posts with the same decision table. HOW: keep the core-concept post as the mechanism (it is the better version for 1, 7, 10, 13) and reduce the interview-guide twin to 面試情境 + 三個演進階段 that links here; fold 6 into 7 (6 adds nothing 7 and part 13 do not cover).
5. **Repair the cross-reference block in every post.** WHY: eight posts point readers at "Part N" topics that were never written; 12 cites slugs that 404 if ever linked. HOW: replace prose "Part N" with real links to the published 14–25 titles (or delete the row), so `scripts/check_links.py --strict` can guard them.
6. **Bring 2, 4, 5, 6 up to the batch's own template.** WHY: they are the four posts without a 為什麼選 X 不選 Y table and the four with the lowest Depth scores; 4 in particular is a decision-heavy topic (k, fusion, reranker placement, ES vs Vertex vs Weaviate) written without a decision table. HOW: add a 4–6-row table with a flip column, as 7:139 and 11:412 already do.
7. **Rename or drop the model-answer sections.** WHY: CLAUDE.md removed 面試答題要點 from the series; 面試一句話（Killer Phrase）, 7's 面試常見追問與答法 and 9's 5/7/9-point scoring are the same thing. HOW: keep the one-paragraph summary but title it 一句話總結 and cut the "面試官會接著問" framing; if the coordinator decides the series stays interview-prep, say so in CLAUDE.md so the checker can enforce it.
8. **Decide whether this series must follow the fde-interview-guide hard rules, and make the checker see it.** WHY: `review_posts.py` reports nothing for 三個演進階段 / 600-line floor / Killer Phrase on these slugs, so the "no drift" alarm is silent. HOW: either add `fde-core-concept-*` to the series rule list (and accept 13 new warnings), or document in CLAUDE.md that core-concept posts use the lighter template (三個實作層次, 300–500 lines) so reviewers stop measuring them against the wrong bar.
9. **Fix the metadata that interleaves the two series.** WHY: thirteen posts on one timestamp that equals parts 40–42's slot; English title prefix on zh posts; unused `weight` field. HOW: stagger dates by a minute per part (or use `weight` deliberately in the tag template), choose one Chinese series name, set readTime from line count.
10. **Re-categorise 9–13.** WHY: all are `engineering`; 9/10 are compliance/security architecture and 11–13 distributed-systems architecture. HOW: add `architecture` (and `ai` for 3/13) per the closed category table in CLAUDE.md.

## Verified / unverified claims

- ✅ 1:48–56 history ceiling 128K − 8K − 12K − 16K = 92K; 1:62–65 Turn 50/100 at 43 % / 87 % of 92K; 1:139 40,000 → 24,500 = −38.75 %; 1:426 80K × $3/1M = $0.24, 28K → $0.084
- ✅ 1:414 Claude Sonnet 4 $3/1M input, $15/1M output (knowledge; price list not re-fetched)
- ❓ 1:333 / 1:414 Gemini Flash "$0.075/1M" — the current Gemini API price list shows 2.5 Flash at $0.30/1M input and no 1.5 Flash line; the figure is the retired 1.5 Flash price
- ✅ 2:118 Vertex AI Vector Search is ScaNN-based
- ❓ 2:275 ADK `MemoryBankService` with `top_k` / `similarity_threshold` — not checked against adk.dev
- ❌ 3:169 `LoopAgent(should_continue_condition=…)` — adk.dev documents only `name/sub_agents/max_iterations`; early exit is `actions.escalate` ([adk.dev](https://adk.dev/agents/workflow-agents/loop-agents/))
- ❓ 3:106 "unknown keys raise KeyError" — my reading of LangGraph's `_get_updates` is that keys outside the schema are dropped silently; could not run langgraph locally (not installed) — appears to conflict
- ✅ 3:345 "比 Layer 1 仍節省 42 %" — 1 − 5,200/9,000 = 42.2 %
- ✅ 4:118–131 RRF worked example (1/63 + 1/61 = 0.03227; 1/65 + 1/62 = 0.03151; 1/62 = 0.01613)
- ❌ 4:85 "k1 ≈ 1.2: tf 1 → 10 only ×1.5" — with k1 = 1.2 and length-normalised |D| = avgdl the ratio is 1.96
- ❓ 4:247 "ES 8.8+ 已內建 rrf retriever" — rrf arrived in 8.8 as the `rank` section; the `retriever` syntax shown is later (8.14+); docs page gives no version ([elastic.co](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers))
- ❓ 4:211 `text-ranking-gecko@003` — not a Vertex AI ranking model name I could find; Vertex's are `semantic-ranker-*`
- ❓ 4:288 Vertex AI Search "$2.5/1000 search" — official page is JS-rendered; third-party listings put Standard at $1.50 and Enterprise at $4/1,000
- ✅ 5:109 MRR@5 0.61 → 0.79 = +29.5 % (post says +30 %)
- ❓ 5:139 Ranking API "$0.002 per 50 records" — could not read the official page; a third-party aggregator lists ~$1/1,000 queries — appears to conflict ([costbench](https://costbench.com/software/rag-pipelines/vertex-ai-search/))
- ❌ 5:191 "MiniLM-L-6 22MB" — the model has 22M parameters (~90 MB fp32)
- ❌ 6:164 "T4 GPU on Cloud Run" — Cloud Run GPU page lists NVIDIA L4 and RTX PRO 6000 Blackwell only ([docs.cloud.google.com](https://docs.cloud.google.com/run/docs/configuring/services/gpu))
- ❌ 6:164 "Cloud DLP API $1/1000 次掃描" — Sensitive Data Protection bills per GB; content inspection $3/GB, >1 TB $2/GB ([cloud.google.com](https://cloud.google.com/sensitive-data-protection/pricing))
- ✅ 7:347, 9:259 Cloud KMS "$0.03/10K operations" (symmetric / RSA-2048) ([cloud.google.com](https://cloud.google.com/kms/pricing))
- ✅ 7:283 `urlparse(url).netloc` exact match defeats `approved.com.evil.com`
- ✅ 8:50–56 Sweeney 87 % — but for zip + **date of birth** + gender, not zip + age + gender (8:53, 8:207, 8:339)
- ❌ 8:62 "GDPR safe harbor 通常要求 k ≥ 5" — GDPR specifies no k; "Safe Harbor" is HIPAA §164.514(b)
- ✅ 8:269 Sensitive Data Protection "~$3/GB" content inspection
- ❌ 8:271 KMS "$0.06/10,000 操作" — $0.03/10K; $0.06 is the per-version monthly price
- ❌ 8:450 KMS "預設 600 req/min" — default cryptographic-requests quota is 60,000 QPM (software keys) ([docs.cloud.google.com](https://docs.cloud.google.com/kms/quotas))
- ✅ 8:367 Recall@10 0.89 → 0.87 = −2.2 %
- ❌ 9:21 "HIPAA: PHI 不得離開美國" — HIPAA has no data-localisation requirement
- ❌ 9:435 `constraints/gcp.disableCloudKMSCryptoKeyVersionExternalImport` — not in the Cloud KMS constraint list ([docs.cloud.google.com](https://docs.cloud.google.com/kms/docs/org-policy-constraints))
- ❓ 9:170 `vertexai.init(client_options=…)`, 9:193 `BatchPredictionJob.create(dedicated_resources_machine_type=…)`, 9:142 "global endpoint is the default" — not verified against the SDK; all three appear to conflict with the documented signatures (`api_endpoint`, `machine_type`, regional default)
- ❓ 9:79 Org Policy "傳播時間 < 60 秒"; 9:316 Assured Workloads support-personnel restriction to Taiwan — not checked
- ❌ 10:283 software-protected KEK "~$1/密鑰版本/月" — $0.06/month; $1.00 is the Cloud HSM rate ([cloud.google.com](https://cloud.google.com/kms/pricing))
- ✅ 10:242 KEK calls 24/1,000,000 = 0.0024 %; 10:348 Dedicated Interconnect 10 Gbps ≈ $1,700/month (order of magnitude)
- ❓ 10:216 KAJ justification JSON with `resource/operation/principalEmail` — KAJ sends a reason code; field names not verified
- ✅ 11:246–250 MaxOutstandingMessages floor(4 GB/400 MB)×0.7 = 7; 7/15 s = 0.47 jobs/s; ceil(100/0.47) = 213–215; 11:424 50,000/200 = 250×
- ❌ 11:276 "20,000 reads/s ≈ $0.06/s = $5,000/月" — $0.012/s, ~$31,104/月; 11:307 "$1,800/月" — $0.18
- ✅ 11:388 Pub/Sub default ack deadline 10 s, 7-day retention; 11:415 Cloud Run request timeout 60 min
- ❌ 12:224 "45K × 30 − 25K = ~1.1M" — 1,325,000; 12:436 vs 12:440 50 MB vs 50 KB
- ✅ 12:277 KEDA default polling interval 30 s; 12:306 Pub/Sub subscription filter supports `!=`
- ✅ 13:255–266 `graph.update_state(config, values, as_node=…)` then `graph.stream(None, config)` is the real LangGraph API
- ✅ 13:403 Spanner regional $0.90/node-h × 720 = $648; 13:407 nam6 $9 × 3 × 720 = $19,440 (arithmetic; nam6 rate from memory, the pricing page could not be read)
- ❌ 13:235 Spanner "$0.003 / $0.009 per million read/write ops" — Spanner bills compute, storage, backup and network, not operations; and 2M × $0.009/M = $0.018, not $0.18
- ❓ 13:387 nam6 = us-central1 + us-east1 + us-east4 (witness) — not re-checked
