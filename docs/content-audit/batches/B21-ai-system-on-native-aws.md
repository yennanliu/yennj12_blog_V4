# B21-ai-system-on-native-aws — ai-system-on-native-aws parts 1–10 (Traditional Chinese)

Reviewed 2026-10-11. 10 posts, 4,156 lines, dated 2026-07-18 → 07-27. Mechanical baseline: `review_posts.py` 10 posts / 0 errors / 0 warnings; `check_links.py --content-only` clean. All 90 series-nav links use the `/posts/<slug>/` form and every target exists — **no `./slug.md` links** (the B20 failure mode is absent here). Verified-fact lookups below were done against AWS docs / CDK API pages on 2026-10-11.

## Batch summary

This is the best-written AWS series in the audit so far: each part has a real thesis, the house template is applied with discipline, the 「為什麼選 X 不選 Y」 tables carry flip conditions, and the recurring 「成本形狀」 motif (fixed → variable → resident → token×loops → control tax) is a genuine argument that builds across parts. Several 2025-era corrections have been patched in and check out (Fraud Detector closed to new customers 2025-11-07, Kinesis Data Analytics for SQL deleted 2026-01-27, Guardrail version pinning, per-minute SageMaker scaling metric, SCP vs inference-profile regions). The coordinator's premise is partly wrong: **none of the ten posts has a 三個演進階段 section and none labels a number 實測** — the interview-series inheritance is limited to the four-line opening quote, the 為什麼選 X 不選 Y tables and the numbered 一…七 sections, all of which help rather than pad. What drags the batch down is a cluster of **CDK code that cannot deploy as written**: two invented L1 constructs (`CfnCustomModel` P7, `CfnModelInvocationLoggingConfiguration` P5 — neither `AWS::Bedrock` resource exists), a Cedar policy that fails STRICT validation (P6 `in` on strings), a Textract `JobTag` that violates the API pattern and is unrecoverable (P2), and a Knowledge Base stack that never creates the OpenSearch vector index it references (P1). Cost tables recompute correctly in P1/P2 but P3 and P8 overstate the resident-compute rows by ~2×, and no table carries a date. Verdicts: **2 Ready (P4, P9) / 4 Needs revision (P1, P3, P8, P10) / 4 Not ready (P2, P5, P6, P7)**.

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| part1-serverless-rag-chatbot-zh | 563 | 3 | 5 | 4 | 4 | 4 | 4 | 4.0 | Needs revision | L289 `vectorIndexName: 'support-index'` is referenced but **no code creates the AOSS index** (vector/text/metadata mapping); `CfnKnowledgeBase` fails on first deploy. The 坑 list (L512-516) omits the most common deploy failure. Cost table L506-512 recomputes ✅ ($350 / $320–1,200 / $21.6 / $0.35 → $660–1,560). |
| part2-intelligent-document-processing-zh | 443 | 2 | 5 | 4 | 3 | 4 | 4 | 3.7 | **Not ready** | L176 `JobTag: base64(taskToken).slice(0,64)` — a task token is ~600+ chars, base64 emits `+ / =` which violate the `JobTag` pattern `[a-zA-Z0-9_.\-:]+`, and the 64-char slice makes it unrecoverable; L199 `resolveToken(JobId)` is undefined. The section's central mechanism (callback → task token) cannot work. L330 EventBridge passes the raw S3 event but L265-266 reads `$.bucket`/`$.key` (real path `$.detail.bucket.name`). |
| part3-realtime-recommendation-zh | 432 | 3 | 5 | 4 | 4 | 4 | 4 | 4.0 | Needs revision | L374 SageMaker row "ml.c6i.xlarge × 6 台 ~$1,500–2,000" — list price is $0.204/h → 6 × 730 × 0.204 = **$893**; row is ~2× high and the total (L380) inherits it. L272-278 per-minute `InvocationsPerInstance` reasoning ✅ correct and valuable. |
| part4-agentic-ai-with-tools-zh | 463 | 4 | 5 | 4 | 4 | 4 | 4 | 4.2 | Ready (minor) | L337 `AGENT_ALIAS_ID` is consumed but no `CfnAgentAlias` (or `autoPrepare`) is ever created; L404 "$1,200–4,000" for 1.2 B tokens is Haiku-3 ≈ $540 … Sonnet ≈ $6,500 — band is loose; L181 `PROMPT_ATTACK` output strength `NONE` ✅, L227-230 pinning a GuardrailVersion ✅, agent request/response envelope L104-125 ✅. |
| part5-production-mlops-observability-zh | 370 | 2 | 4 | 3 | 3 | 3 | 4 | 3.2 | **Not ready** | L80 `new bedrock.CfnApplicationInferenceProfile; // 實務上用 CfnModelInvocationLoggingConfiguration` — a no-op expression naming a construct that **does not exist** (no `AWS::Bedrock::ModelInvocationLoggingConfiguration`; it is an account-level API needing `AwsCustomResource`). L15/L321/L352 still frame Part 5 as "整個系列的收束 / 走完五篇 / 感謝一路讀到這裡" although Parts 6–10 exist. L122 alarms `InvocationClientErrors` for 429s; the metric is `InvocationThrottles`. |
| part6-enterprise-multi-tenant-rag-zh | 389 | 2 | 4 | 4 | 4 | 4 | 4 | 3.7 | **Not ready** | L171 `resource.department in principal.departments` — Cedar `in` is entity-hierarchy only; on Strings it is a validation error, and L139 sets `mode: 'STRICT'`, so `CfnPolicy` creation fails (`principal.departments.contains(resource.department)`). L95-99 diagram puts Verified Permissions on the <10 ms hot path; L180/L188 prose says it is *not* called per request; L190-208 code never calls it — the headline component is decorative. L190 `authorizer.jwt.claims` is the **HTTP API** event shape, but L275-281 usage plans/API keys are **REST-only**. |
| part7-foundation-model-customization-governance-zh | 379 | 2 | 5 | 4 | 4 | 4 | 4 | 3.8 | **Not ready** | L173 `new bedrock.CfnCustomModel(...)` — **no `AWS::Bedrock::CustomModel` resource exists** (CloudFormation Bedrock resource list checked 2026-10-11); fine-tuning is `CreateModelCustomizationJob` (CDK: `BedrockCreateModelCustomizationJob` Step Functions task). Props mirror the API, so a reader will paste and fail. Everything else (Model Registry L231-247, EventBridge L258-265, 回歸防護 L222-224) ✅. |
| part8-realtime-streaming-fraud-detection-zh | 372 | 3 | 5 | 4 | 4 | 4 | 4 | 4.0 | Needs revision | L315 Managed Flink "4–8 KPU ~$800–1,600" — $0.11/KPU-h → (4+1)…(8+1) KPU = **$400–720**; L316 Kinesis "5 M events/day ~$200–400" only holds at ~10 KB/event (1 KB ≈ $48). L57 "P99 < 50 ms" is never budgeted (API GW + Lambda + DynamoDB + SageMaker + Neptune in parallel; no per-hop numbers). L272 KDA-SQL and L288 Fraud Detector notes ✅ verified. |
| part9-security-compliance-data-governance-zh | 380 | 4 | 5 | 4 | 3 | 4 | 4 | 4.0 | Ready | Strongest accuracy in the batch: L231-239 SCP `StringNotEquals` + `Null:false` pattern ✅, L242 inference-profile/region caveat ✅, L270 `config.ManagedRule` needs a configuration recorder the stack never creates (minor), L323 endpoint cost ✅ ($117 + data). Only one diagram (L73-88). |
| part10-enterprise-ai-platform-engineering-zh | 365 | 4 | 4 | 3 | 3 | 4 | 4 | 3.7 | Needs revision | Conceptual by design: L153-157 usage plan is created but never bound to a stage or key; L205-222 `RagChatbot` calls six undefined helpers (`platformKmsKey`, `applyTenantIsolation`, …) — pseudo-code presented as a construct; L271 application-inference-profile paragraph is the one piece of hard, current substance. L161 29-s timeout note ✅. |

Overall = unweighted mean (no finance posts). Verdicts: 2 Ready, 4 Needs revision, 4 Not ready.

## Patterns

### Content quality
- **Every post states a thesis in the first screen and argues it.** P1 L13-16 (managed RAG vs "rent a GPU + LangChain"), P4 L13-16 (agents produce *actions*, so the risk model changes), P7 L13-16 (the problem is governance, not training), P9 L13-16 (compliance is the ticket, not decoration). This is the opposite of B20's "This comprehensive guide explores…".
- **The series has one argument, not ten topics.** The 「成本形狀」 motif is introduced at P1 L514, extended at P2 L397, P3 L383, P4 L411, consolidated at P5 L228-239, then re-derived for P6-P9 (P6 L340, P8 L325, P9 L306) and closed at P10 L313-330. Few series in this repo carry a thread this well.
- **2025-era patches are correct and honestly hedged.** "細節請見官方文件" appears 7 times (P1 ×2, P2, P4, P6, P7, P10) and each sits on a fact that genuinely moves (S3 Vectors, BDA, AgentCore, Nova on-demand custom models). P8 L272/L288 service-retirement notes verify against AWS docs.
- **The weak half is code, not prose.** All four blockers are in TypeScript blocks (P2 L176, P5 L80, P6 L171, P7 L173); the prose around each is right. The author knows the architecture better than the construct library.

### Structure (does the house format help or pad?)
- **No 三個演進階段 anywhere; no 實測 labels anywhere.** `grep` confirms 0 hits across 10 files. The coordinator's concern does not apply; what is inherited from fde-interview-guide is the 4-line 「大部分人…」 opener, 為什麼選 X 不選 Y with 翻盤條件, and 一…七 numbering.
- **The fixed 7-section template helps.** 情境 → 功能/非功能需求 → 設計 → CDK → 選型 → 成本 → 坑 is applied in 9/10 posts (P9 swaps NFRs for 控制目標 L47-57, P10 for 產品需求 L43-53 — both appropriate). The NFR table consistently feeds the architecture choice (P1 L96-101 → serverless; P3 L52-54 → resident endpoint; P8 L57-64 → Flink + rules + graph), so it is not decorative.
- **Padding that exists is series plumbing, not format.** The 10-link nav block is 20 lines × 10 = 200 lines (4.8 % of the batch); P1 L22-32 and P6 L19-30 each carry a series prospectus; P5 L313-352 and P10 L305-348 are two "series conclusions" with overlapping 三句話 (P5 L336-346 ≈ P10 L332-342).
- **The 五篇 → 十篇 extension was not reconciled.** P5 L15 "也是整個系列的收束", L232 "五個系統的成本形狀總覽", L321 "走完五篇", L352 "感謝一路讀到這裡" all predate Parts 6-10; P1 L26 patched the prospectus but P5 was not. P6 L19 then re-introduces the series.

### Depth
- **Flip conditions are real and specific** in 9/10 posts: P1 L418 (when KB cannot do it), P3 L329 ("多數團隊的務實起點其實是 Personalize" — the post argues against its own build), P6 L303-306 (<20 customers → silo), P7 L295, P10 L267 ("團隊數過了 5–10 個"). P9 §5 gives flip conditions for all four decisions.
- **"When it breaks" is handled by the 坑 lists** (P2 L411-419 async/pagination/idempotency/429/PII; P3 L393-397; P6 L367-371; P8 L349-354), and several are better than the docs: P6 L367 cache-key-without-authz as a privilege-escalation channel, P8 L351 fail-safe when the risk service times out.
- **Numbers: arithmetic recomputes, inputs are unsourced and undated.** P1 L504-512 ✅, P2 L385-390 ✅ ($32,500 / $1,250 / $15), P9 L323 ✅. But P3 L374 (SageMaker 2× high), P8 L315-316 (Flink 2× high, Kinesis assumes 10 KB events) and P4 L404 (band spans 12×) are not derived from a stated unit price. Every table says "撰文時" (P2-P10) but no table says *when* that was.
- **Latency budgets are asserted, not added up.** P3 L52 "P99 < 100 ms" and P8 L57 "P99 < 50 ms" never get a per-hop table; P8 L172-200 does three network calls in parallel plus a SageMaker invoke through API Gateway + Lambda and the post does not show how that fits in 50 ms.
- **Training-serving skew (P3 L88-91, L393) is slightly oversold.** A shared Feature Store removes *storage* skew; it does not make the Lambda's feature code identical to the offline pipeline's unless the offline set is the replayed online writes — which is in fact the design, but the post should say so (and mention point-in-time joins on `event_time`).

### Direction (overlap, gaps, stale topics, category fit)
- **RAG canonical split.** Concept-level RAG belongs to `rag-series-part1..5` / `ragflow-intro-*` (B15); **P1 is the canonical "RAG on AWS managed services" post and P6 the canonical multi-tenant/authorization RAG post** — nothing else in the repo covers Bedrock KB, metadata filters or Verified Permissions (grep: `Knowledge Base` elsewhere only in fde-interview-guide-part1/2/41 and aio-geo-part10). No contradiction with B15, but no cross-links either.
- **Agents.** P4 is canonical for Bedrock Agents/Guardrails (no other post mentions them). `fde-core-concept-6-prompt-injection-jailbreak-zh` is the canonical prompt-injection explainer and P4 §5.3 (L370-378) should link to it instead of restating.
- **AWS guides (B20).** `aws-vpc-complete-guide` is Not ready; **P9 §4.1 (L113-131) is the better VPC-endpoint reference and should be named canonical for "private connectivity to Bedrock"**. `aws-api-gateway-comprehensive-guide` and `aws-dynamodb-complete-guide` (both Not ready) are not contradicted — P3/P6/P10 use DynamoDB and usage plans only in passing.
- **kubernetes-autoscaling (B20).** No topical overlap (this series is deliberately serverless/managed). One cross-link is worth making: P3 L272-278 (target-tracking on a per-minute metric) is the same lesson as HPA target tuning in kubernetes-autoscaling part 4.
- **Other overlaps:** `building-centralized-logging-opensearch-aws-cdk` ↔ P5 §2 / P10 §4.3 (centralised logs); `fde-core-concept-10-cmek-byok-envelope-zh` ↔ P9 §4.2 / L319 XKS; `springdataplatform-flink-management-system` is unrelated to P8.
- **Category fit** `["all","ai","engineering"]` is right for P1-P8; P9 and P10 are closer to `infrastructure` (+ `architecture` for P10) than `engineering`.
- **Gap:** no post in the series (or the repo) evaluates the Bedrock-native alternatives it names — Bedrock Data Automation (P2 L345), AgentCore (P4 L361), S3 Vectors (P1 L461), application inference profiles (P10 L271). A short "what changed in 2025" follow-up would retire several hedges.

### Accuracy
- **Invented or non-existent constructs:** P5 L80 `CfnModelInvocationLoggingConfiguration`; P7 L173 `CfnCustomModel`. The `AWS::Bedrock` resource list (checked 2026-10-11) has neither. P2 L199 `resolveToken`, P10 L205-212 six helpers are undefined.
- **Code that fails validation:** P2 L176 `JobTag` (pattern + length), P6 L171 Cedar `in` on Strings under `STRICT`, P1 L289 index never created.
- **Wrong metric / mismatched API shapes:** P5 L122 `InvocationClientErrors` vs `InvocationThrottles`; P6 L190 HTTP-API JWT event vs REST usage plans; P2 L265-266 `$.bucket` vs `$.detail.bucket.name`.
- **Numbers off by ~2×:** P3 L374, P8 L315. P6 L86/L340 "固定成本 × 租戶數" ignores that AOSS collections sharing a KMS key share OCUs (docs: only collections with *unique* KMS keys instantiate their own OCU set), which also makes the L333 "$1,200" row plausible only under sharing — prose and table disagree.
- **Verified correct and worth keeping:** P1 L330 Titan v2 ARN; P4 L181/L227-250 Guardrail + Agent props; P5 L170-186 blue/green `deploymentConfig`; P7 L258-265 Model Package EventBridge event; P8 L165 `FLINK-1_20`; P9 SCP/Macie/Lake Formation props; P8 L272/L288 retirements; P10 L161 29-s timeout; P6 L199-208 KB filter operators and L229-237 `.metadata.json` shape.

### Format / front matter
- Front matter complete and uniform in 10/10; descriptions are long (P10's is 120+ Chinese characters) but sell the payoff. readTime 12-15 min for 365-563 lines matches the checker.
- 36-57 fenced lines per post exceed 80 columns (first: P1 L58, P10 L25) — the ASCII architecture diagrams and the 為什麼選 tables will scroll horizontally on phones.
- Link hygiene is clean: all internal links root-absolute `/posts/...`, no hard-coded baseURL, no relative `./` forms, all ten targets exist.
- Terminology drifts between 中文/English for the same thing within a post (P6 "共池/Pool", P8 "Managed Flink / Managed Service for Apache Flink / Kinesis Analytics") — minor.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | part7:173 | `new bedrock.CfnCustomModel(...)` — no `AWS::Bedrock::CustomModel` resource exists; the props copy `CreateModelCustomizationJob`. | Replace with `tasks.BedrockCreateModelCustomizationJob` (Step Functions) or an `AwsCustomResource` calling `createModelCustomizationJob`; say explicitly that CloudFormation has no custom-model resource. |
| 2 | blocker | part5:80 | `new bedrock.CfnApplicationInferenceProfile;` is a no-op expression and the comment names a non-existent `CfnModelInvocationLoggingConfiguration`. | Show the real pattern: `AwsCustomResource` → `bedrock:PutModelInvocationLoggingConfiguration` (region-scoped), with the IAM for it. |
| 3 | blocker | part6:171 | Cedar `resource.department in principal.departments` — `in` is entity-hierarchy only; on Strings it is a validation error and L139 is `STRICT`. | `principal.departments.contains(resource.department)`. |
| 4 | blocker | part2:176-199 | `JobTag` = base64(taskToken).slice(0,64): base64 chars `+/=` violate `[a-zA-Z0-9_.\-:]+`, 64 chars cannot hold a ~600-char token, and `resolveToken` is undefined. | Store `{JobId → taskToken}` in DynamoDB (keyed by `ClientRequestToken`/JobId) in `start-textract`, look it up in the callback; keep `JobTag` as a short document id. |
| 5 | major | part1:289 | KB references `support-index` with `vector/text/metadata` fields but nothing creates the AOSS index; `CfnKnowledgeBase` fails on first deploy. | Add an `AwsCustomResource`/Lambda that `PUT`s the k-NN index (dimension 1024 for Titan v2, `faiss` engine) after the data-access policy, and list this as 坑 #0 at L512. |
| 6 | major | part6:95-99 vs 180-208 | Diagram and cost row (L336) put Verified Permissions on the request path; prose and code never call it. | Either call `IsAuthorized` once per request to derive the filter (and keep the <10 ms claim), or redraw the diagram as "VP validates/audits policy offline" and drop the cost row. |
| 7 | major | part3:374 | SageMaker row ~$1,500–2,000 for 6 × ml.c6i.xlarge; list price $0.204/h → $893. Total at L380 inherits the error. | State the unit price and date; recompute to ~$900–1,000 and total ~$3,000–4,400. |
| 8 | major | part8:315-316 | Flink "$800–1,600" (actual ~$400–720 for 5–9 KPU at $0.11) and Kinesis "$200–400" (assumes ~10 KB events). | Show KPU count × $0.11 × 730 and event size; or label the rows "含 checkpoint 儲存與 EFO" if that is the intent. |
| 9 | major | part5:15, 232, 321, 352 | Post still calls itself the series finale ("走完五篇", "感謝一路讀到這裡") with a five-system table. | Re-title §七 "基礎篇總結", add one sentence pointing to Part 6-10, or move the farewell to P10 only. |
| 10 | major | part6:190 vs 275-281 | `event.requestContext.authorizer.jwt.claims` (HTTP API) but usage plans/API keys (REST API only). | Pick REST (`authorizer.claims`) or move quotas to a Lambda/DynamoDB token bucket. |
| 11 | major | part2:265-266, 330 | State machine input is the raw EventBridge S3 event; `StartTextract` reads `$.bucket`/`$.key` which do not exist. | Add `input: events.RuleTargetInput.fromObject({bucket: EventField.fromPath('$.detail.bucket.name'), key: …})` on the rule target. |
| 12 | minor | part5:122 | 429 alarm on `InvocationClientErrors`. | Use `AWS/Bedrock` `InvocationThrottles`. |
| 13 | minor | part4:337 | `AGENT_ALIAS_ID` consumed, never provisioned. | Add `CfnAgentAlias` (and `autoPrepare: true`) to §4.4. |
| 14 | minor | part6:86, 340 | "固定成本 × 租戶數" for Silo — AOSS collections on the same KMS key share OCUs; only unique-key collections multiply the floor. | Qualify: silo cost multiplies only when each tenant gets its own CMK (which regulated tenants often require — say so). |
| 15 | minor | all cost tables | "撰文時" without a date; P1's table has no hedge at all (L502). | Add `(2026-07 us-east-1 list price)` to each table header. |

## Recommendations

1. **Fix the four deploy-breaking code blocks before anything else (P2, P5, P6, P7).** WHY: this series' promise is "全部用 CDK 一鍵部署"; a reader who pastes L173 of P7 or L171 of P6 gets a CloudFormation error on the headline resource, which converts the strongest trait of the series (concrete IaC) into its biggest liability. HOW: findings 1-4 above; add a one-line "CloudFormation 沒有這個資源,用 custom resource" note where AWS has no L1.
2. **Add the missing AOSS index step to P1 and promote it to 坑 #1.** WHY: it is the single most common Bedrock-KB-via-CDK failure and the post's 坑 list (L512-516) claims to cover "最容易踩的三個坑". HOW: `AwsCustomResource` with `opensearchserverless`-signed HTTP PUT, or point readers at the `@cdklabs/generative-ai-cdk-constructs` `VectorCollection`/`VectorIndex` constructs.
3. **Date-stamp and derive every cost table.** WHY: P1/P2 recompute perfectly while P3/P8 are 2× off — the difference is whether a unit price is shown. HOW: header `(us-east-1 list price, 2026-07)`; one "單價 × 用量" column; link to the pricing page. Recompute P3 L374 and P8 L315-316.
4. **Reconcile P5 with the ten-part series.** WHY: P5 L15/L321/L352 tell the reader the series is over; P6 L19 then restarts it. HOW: rename §七 "基礎篇小結", trim the farewell, keep the five-system table but add a pointer to P10's ten-row table.
5. **Make Verified Permissions either real or honest in P6.** WHY: the post's thesis is "授權先於檢索" and names VP as the engine, but the hot path never calls it and the diagram says it does. HOW: show the single `IsAuthorizedWithToken` call that returns the derived dimensions (or a batch call per tenant cached in ElastiCache), and keep the filter-compilation code as the output of that call.
6. **Add a latency-budget table to P3 and P8.** WHY: "P99 < 100 ms / < 50 ms" are the NFRs that justify the whole architecture, yet neither is decomposed. HOW: a 6-row table (API GW, Lambda init/exec, DynamoDB, Feature Store/`GetRecord`, SageMaker invoke, Neptune point query) with typical p50/p99 and the sum; it will also surface why P8 probably needs Lambda provisioned concurrency or an ALB+Fargate path.
7. **Cross-link instead of restating.** WHY: P4 §5.3, P9 §4.2 and P1 §七 restate material that has a canonical post in the repo. HOW: P4 L370 → `fde-core-concept-6-prompt-injection-jailbreak-zh`; P9 L319 → `fde-core-concept-10-cmek-byok-envelope-zh`; P1 L488 → `rag-series-part3-advanced-retrieval` (hybrid/rerank); P3 L272 → kubernetes-autoscaling part 4 (target tuning).
8. **Collapse the series nav.** WHY: 200 lines of identical nav across ten posts, plus two prospectuses and two conclusions. HOW: a Hugo shortcode or partial driven by the `series` taxonomy; keep only "上一篇 / 下一篇" inline.
9. **Re-categorise P9 and P10.** WHY: they are infrastructure/platform posts, not engineering. HOW: P9 `["all","infrastructure","ai"]`; P10 `["all","architecture","infrastructure"]`.
10. **Wrap the diagrams to ≤ 80 columns.** WHY: 36-57 over-wide fenced lines per post; the ASCII architecture diagrams are the best visuals in the batch and they are the ones that overflow on phones. HOW: shorten box labels (e.g. "Bedrock KB" not "Bedrock Knowledge Base"), split 2-column 選型 tables into Markdown tables.

## Verified / unverified claims

- ✅ part1:330 — `amazon.titan-embed-text-v2:0` foundation-model ARN form.
- ✅ part1:506 — AOSS 2 OCU × $0.24 × 730 h = $350; dev/test without redundancy floors at 0.5+0.5 OCU ≈ $175 (AWS docs, 2024-06 "entry cost in half"). L512 "0.5 OCU 起跳" ✅.
- ✅ part1:504-512 — Claude Haiku 3.5 / Sonnet band $320 / $1,200; Nova Lite $21.6; API GW REST $0.35; total $660–1,560 recomputes.
- ✅ part1:418 — KB supports semantic/hierarchical/custom-Lambda chunking, FM parsing, hybrid search, rerank.
- ❓ part1:461, part6:349 — S3 Vectors "2025 年新服務" — launched preview 2025-07; GA status not checked.
- ✅ part1:513 — 2025 model-access simplification; Anthropic models still need a use-case form.
- ✅ part2:177 — `ClientRequestToken` 1-64 chars `^[a-zA-Z0-9-_]+$`, same token → same JobId (Textract API ref).
- ❌ part2:176 — `JobTag` pattern `[a-zA-Z0-9_.\-:]+`, 1-64 chars; base64 output violates it and cannot carry a task token.
- ✅ part2:385-390 — Textract Tables+Forms $0.065/page first 1 M → $32,500; Comprehend 15 M units → $1,250; Step Functions 600 k transitions → $15.
- ✅ part2:345 — Bedrock Data Automation exists (GA 2025-03).
- ❌ part3:374 — ml.c6i.xlarge is $0.204/h (us-east-1, checked 2026-10-11) → ~$893 for 6 instances, not $1,500–2,000.
- ✅ part3:272-278 — `SageMakerVariantInvocationsPerInstance` is a per-minute per-instance metric; 24,000 ≈ 400 req/s.
- ✅ part3:376-378 — HTTP API 600 M req ≈ $570; REST ≈ $2,100 (3.5×).
- ✅ part4:181 — `PROMPT_ATTACK` requires `outputStrength: NONE`; L227-230 `CfnGuardrailVersion.attrVersion` ✅; L232-250 `CfnAgent` props ✅.
- ✅ part4:104-125 — action-group Lambda event (`apiPath`, `parameters[]`) and response envelope (`messageVersion`, `response.responseBody`).
- ✅ part4:361, 387 — AgentCore (2025) and multi-agent collaboration exist.
- ❓ part4:404-406 — token-cost band and Guardrails "$100–200": content filters $0.15 / denied topics $0.15 / PII $0.10 per 1,000 text units (post-2024-12 cut) → ~$320 for 400 k evaluations of ~2 units each; depends on unit counts.
- ❌ part5:80 — no `AWS::Bedrock::ModelInvocationLoggingConfiguration` resource (CloudFormation Bedrock resource list, 2026-10-11); account/region-level `PutModelInvocationLoggingConfiguration` API only.
- ❌ part5:122 — Bedrock throttling metric is `InvocationThrottles`, not `InvocationClientErrors`.
- ✅ part5:170-186 — `CfnEndpoint.deploymentConfig.blueGreenUpdatePolicy` (CANARY, `canarySize`, `waitIntervalInSeconds`, `autoRollbackConfiguration.alarms`).
- ✅ part5:217 — SageMaker shadow variants exist.
- ❌ part6:171 — Cedar `in` on String × Set<String> is a validation error (Cedar operator docs: "Use `contains` for set membership").
- ✅ part6:139, 141-163 — `CfnPolicyStore` `validationSettings.mode: STRICT` and Cedar JSON schema shape.
- ✅ part6:199-208 — KB retrieval filter operators `andAll/orAll/equals/in/lessThanOrEquals`; L229-237 `.metadata.json` `metadataAttributes{value:{type,stringValue},includeForEmbedding}`.
- ✅ part6:253 — ElastiCache for Valkey 8.2+ vector search (`FT.SEARCH … KNN`) at no extra cost.
- ⚠ part6:86, 340 — AOSS OCUs are shared across collections that use the same KMS key; "固定成本 × 租戶數" only holds for unique-key collections.
- ✅ part6:336 — Verified Permissions $0.00015/request → $75 for 500 k.
- ❌ part7:173 — no `AWS::Bedrock::CustomModel` resource; CDK offers `BedrockCreateModelCustomizationJob` (Step Functions task) only.
- ✅ part7:175 — Nova Lite is fine-tunable; L322 custom Nova on-demand deployment (2025) ✅.
- ✅ part7:231-247, 258-265 — `CfnModelPackageGroup`/`CfnModelPackage` (`modelApprovalStatus`, `customerMetadataProperties`); EventBridge `SageMaker Model Package State Change`.
- ✅ part8:165 — Managed Flink `runtimeEnvironment: 'FLINK-1_20'`; `codeContentType: 'ZIPFILE'` for a jar.
- ⚠ part8:191 — `Time.seconds()` is deprecated in Flink ≥1.18 (use `Duration`); fine for 1.20, gone in 2.0.
- ✅ part8:272 — Kinesis Data Analytics for SQL: no new apps from 2025-10-15, deletion from 2026-01-27.
- ✅ part8:288 — Amazon Fraud Detector closed to new customers 2025-11-07; AWS recommends AutoGluon + SageMaker.
- ❌ part8:315-316 — Flink $0.11/KPU-h → $400–720; Kinesis On-Demand at 1 KB/event ≈ $48/mo.
- ❓ part8:318 — Neptune db.r6g.large ×2 ≈ $508 compute + storage/IO; "$700–1,000" plausible, unsourced.
- ✅ part9:113-131 — `InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME / BEDROCK_AGENT_RUNTIME / SAGEMAKER_RUNTIME`; S3 gateway endpoint.
- ✅ part9:158-171, 178-196 — Macie `CfnSession`/`CfnClassificationJob` and Lake Formation `CfnPrincipalPermissions.tableWithColumns.columnWildcard.excludedColumnNames` props.
- ✅ part9:231-239, 242 — SCP `StringNotEquals` + `Null:false` pattern; cross-region inference profiles route outside a two-region allow-list.
- ✅ part9:323 — 8 interface endpoints × 2 AZ × $0.01/h ≈ $117 + data processing.
- ✅ part9:309 — GDPR fines up to 4 % of global turnover.
- ✅ part10:161 — API Gateway REST default integration timeout 29 s (raisable by quota since 2024-06 — post hedges correctly).
- ✅ part10:242 — Budgets `costFilters.TagKeyValue: ['user:team$cs']` format.
- ✅ part10:271 — application inference profiles carry cost-allocation tags; AgentCore Gateway exists (2025).
- ❓ part10:292-301 — platform cost table entirely order-of-magnitude, no unit prices.
