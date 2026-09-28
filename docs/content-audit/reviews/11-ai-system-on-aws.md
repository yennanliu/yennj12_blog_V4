## ai-system-on-native-aws 1–10, deploying-huggingface-models-aws-cdk-sagemaker, llm-fine-tuning-aws-bedrock — 12 posts

### Series-level observations
- **The series nav has no links in any of the 10 parts.** Every `## 系列導覽` block is plain bold text ("**Part 2**:智慧文件處理(IDP)管線"). Nobody can click from one part to the next. Parts 1–5 list only 1–5, so a reader who finishes Part 5 never learns Parts 6–10 exist. Parts 6–9 show 1–5 as a single unlinked line ("基礎篇回顧"). Fix all ten navs to a linked 1–10 list using `/posts/<slug>/` paths. This is the highest-impact fix in the batch.
- **Model IDs are stale and hard-coded in the part that argues against hard-coding them.** `anthropic.claude-3-5-sonnet-20241022-v2:0` appears in Part 2 L242, Part 4 L262/L268 and Part 5 L196. Claude 3.5 Sonnet was retired on Anthropic's API on 2025-10-28, and Bedrock has also moved it to legacy/EOL (verify the exact Bedrock date). Current Claude models on Bedrock are called through inference-profile IDs (`us.`/`global.` prefixes). An IAM policy scoped to `foundation-model/<id>` only, as in Part 4 L262, will not authorise a cross-region profile call. Replace the IDs with one current Sonnet profile ID taken from the console, and put it in the SSM parameter that Part 5 §3.3 already recommends. Part 1 L349 is the only place that gets this right ("推論 profile ARN").
- **AWS services launched in 2025 are missing, so several "why X not Y" tables lack the option AWS itself now recommends.** Part 2 (IDP) never mentions **Bedrock Data Automation**. Part 4 (agents) and Part 10 (platform) never mention **Bedrock AgentCore** (runtime, gateway/MCP, memory, identity). Part 1 and Part 6 omit **S3 Vectors** as the low-cost KB vector store, which matters because Part 1's whole cost argument rests on the OpenSearch Serverless OCU floor. Part 10 skips **application inference profiles** for per-team cost tags. These are all "verify the current status" items, but readers in Sept 2026 will notice each absence.
- **Every part has a real architecture diagram and a real cost table, except Part 5.** Part 5 has a three-layer observability stack and a "成本形狀" comparison table, but no pipeline diagram (invocation logs → S3/CloudWatch → metric filters → alarms → rollback) and no dollar estimate. Part 7's largest line item is "~$數千 / 月起", which is not a number.
- **Parts 6–10 do differ from 1–5 in substance** (multi-tenancy, model governance, stateful streaming, compliance controls, platform). The template does not change, though: all ten use the same 情境 → 目的 → 架構 → CDK → 選型 → 成本 → 坑 → 小結 skeleton. The closing "三句話" in Part 10 §七 repeats Part 5 §七 almost word for word ("能外包給 managed service 的,就別自己 host" and the rest). Part 5 ends with "感謝一路讀到這裡", which reads as a series finale although five more parts follow. Reword Part 5 as "基礎篇完結" and point it at Part 6.
- **The dollar figures are presented as fact with no source or date.** Some are inconsistent with the stated load (see Parts 2 and 3). Add one line per cost table such as "us-east-1 list price as of <month year>, excluding free tier" and recheck the outliers. Part 1 already has a similar caveat ("概略單價,實際以帳單為準"). The others do not.
- readTime is overstated in every part (the audit already flags it, e.g. 27–28 min for about 350 lines). Fix it in one pass. Parts 9 and 10 would sit better under `infrastructure`/`architecture` than under `engineering`.
- The two English posts (Hugging Face deploy, Bedrock fine-tuning) are older, code-heavy (81–84% code) and overlap with Parts 3/5 and Part 7. They are not linked to the series in either direction.

### Per-post

#### `ai-system-on-native-aws-part1-serverless-rag-chatbot-zh.md`
**Verdict:** light edit
- The flip condition in §5.1 (L452) is stale. It says to build your own pipeline when you need "語意切塊 / 版面感知切塊等 KB 不支援的策略" or "檢索後自訂 rerank". Bedrock KB has offered semantic and hierarchical chunking, custom Lambda chunking, FM-based parsing, hybrid search and a Rerank API since 2024. The flip should move to what KB genuinely cannot do (cross-source joins, a custom multi-stage retriever).
- §5.3 lists "Titan Text" as the budget generator. Titan Text has been superseded by Amazon Nova (Micro/Lite), so the budget option should be Nova. Claude is described as "拒絕幻覺" with no source for the claim, so soften that wording.
- Pitfall 2 (L535, "模型要先在 Bedrock console 開啟存取 … Model access 頁面") is likely out of date. AWS simplified model access in 2025 and most models are now enabled by default, though Anthropic models still need a first-use form. Verify and reword.
- §六 fixes the vector-store floor at 2 OCU, about $350. Mention the 0.5-OCU dev/test (no redundancy) configuration and S3 Vectors as the true low-traffic answer (verify). Also drop "把向量存進 DynamoDB 自己算相似度" as a cost tip, because it does not scale and nobody should copy it.
- The series-introduction block (L19–33) says "我們會用五篇" and lists five parts. Update it to ten, or link forward to the Part 6 intro.

#### `ai-system-on-native-aws-part10-enterprise-ai-platform-engineering-zh.md`
**Verdict:** light edit
- §5.1 (collect in a gateway vs call Bedrock directly) skips Bedrock-native options that remove much of the gateway's job. Application inference profiles give per-team cost tags without a proxy. Per-profile quotas and Bedrock API keys cover part of the key management. AgentCore Gateway is the AWS-native MCP/tool gateway. The flip condition should say which gateway duties still need custom code once those exist.
- The §4.1 gateway is API Gateway REST plus a 60 s Lambda. That design cannot stream tokens back to the caller, and it hits API Gateway's default 29 s integration timeout, which is a real limitation for a company-wide LLM front door. Mention streaming (Lambda response streaming or a Fargate/ALB variant) and the timeout (verify current API Gateway streaming support).
- The platform cost table (L291–295) is plausible, but the "value" side has no numbers. One worked example, such as "10 teams × 30% shared cache hit rate × $X of tokens", would back up "投報率最高的單一投資".
- §七 duplicates Part 5's closing three sentences. Keep one version, preferably this one, and have Part 5 hand off to Part 6 instead.

#### `ai-system-on-native-aws-part2-intelligent-document-processing-zh.md`
**Verdict:** light edit
- The biggest gap is **Bedrock Data Automation**, AWS's own managed IDP service (GA 2025) that bundles classification, extraction and normalisation. It needs a row in §五 ("Textract+Comprehend+Bedrock 自組 vs BDA") with a flip condition. Without it the post reads as pre-2025.
- The Comprehend line in §六 looks understated. Comprehend bills per 100-character unit, so 500K pages at roughly 3K characters each comes to tens of millions of units, not "50 萬份單位 ~$500–1,000". Recompute or state the assumption.
- In §4.4 the LLM rates its own confidence (`confidence 為 0~1`), and that number is the §3.1 ⑤ routing gate to human review. Self-reported LLM confidence is poorly calibrated. Either say so and combine it with Textract's per-field confidence, or use a validation-based gate (schema checks, `totalAmount == Σ lineItems`).
- Two lines in the code are fragile enough to fail silently if copied: `.slice(0, 15000)` truncates input without warning (L231), and `JSON.parse(body.content[0].text)` (L250) assumes the model returns bare JSON. Add one sentence recommending the Converse API with a tool or JSON schema.
- Update the model ID (series-level).

#### `ai-system-on-native-aws-part3-realtime-recommendation-zh.md`
**Verdict:** light edit
- The scaling numbers contradict each other. `SAGEMAKER_VARIANT_INVOCATIONS_PER_INSTANCE` is a **per-minute** metric, so `targetValue: 750` means about 12.5 requests/s per instance. The stated peak of 10K QPS (§六) would need about 800 instances, but `maxCapacity: 20` and the cost table assumes "平均 6 台". Either the QPS or the scaling target is wrong. Fix it and say which one.
- The API Gateway plus Lambda line of "~$500" at 1M DAU and 10K QPS peak also looks low. API Gateway REST at around $3.50/M requests already exceeds that at a few hundred million requests per month. State the request volume behind the figure.
- Lambda sits in the P99 < 100ms path with no mention of cold starts or provisioned concurrency. That belongs among pitfalls 1–5.
- The Personalize recommendation (§5.1) is good, and the "多數團隊的務實起點其實是 Personalize" line is exactly the kind of honest guidance the series needs. Keep it.

#### `ai-system-on-native-aws-part4-agentic-ai-with-tools-zh.md`
**Verdict:** restructure
- The post is built entirely on Bedrock Agents and never mentions **Bedrock AgentCore** or Strands Agents, which have been AWS's main agent story since late 2025. §五 needs a "Bedrock Agents vs AgentCore Runtime (+ your own framework) vs Converse tool loop" decision with flip conditions, and §七 should mention MCP tools via AgentCore Gateway. As written, the headline decision is a year old.
- `guardrailVersion: 'DRAFT'` (L276) in the stack for a "production" agent is a copy-paste risk. Pin a numbered guardrail version and say why.
- The IAM policy is scoped to a single retired foundation-model ARN (L262). See the series-level note. The agent will fail on current Claude models, which run through inference profiles.
- The risk-tier table and "永遠不要讓 LLM 的一次推理直接觸發不可逆的副作用" (§3.3) are the most useful part of the post. Add a short Return-of-Control code path, because the text names it but never shows it.

#### `ai-system-on-native-aws-part5-production-mlops-observability-zh.md`
**Verdict:** restructure
- This is the only part with no architecture diagram of its own system and no dollar cost estimate. Add a diagram of the observability and rollback loop (invocation logs → S3/CloudWatch → metric filter → alarm → SageMaker auto-rollback / alias revert), and a cost table for log ingestion, storage and dashboards at the Part 1–4 volumes.
- It is written as a series finale. §七 is titled "五個系統,一套心法" and the post ends with "感謝一路讀到這裡"; the nav lists 1–5 only. Rewrite the ending as a hand-off to Part 6 and move the grand summary to Part 10 only.
- §3.3 recommends taking model IDs out of code and then hard-codes a retired ID in the example (L196). Use a current inference-profile ID so the example shows the practice it recommends.
- §4.3 mentions Provisioned Throughput, prompt caching and Budgets in one bullet each. Bedrock Intelligent Prompt Routing and batch inference (about 50% off) are both concrete cost levers that belong here.

#### `ai-system-on-native-aws-part6-enterprise-multi-tenant-rag-zh.md`
**Verdict:** light edit
- This is the strongest of the advanced parts. Silo/Pool/Bridge, filter-before-retrieval and the cache-key authorisation pitfall are all practitioner-grade material.
- There is a logic gap in the authorisation story. §4.2 says the hot path builds the filter straight from JWT claims and that Verified Permissions is used only "驗證政策邏輯與稽核", yet §3.2 draws AVP as step ① on every request and §七 promises an audit report built from AVP evaluation logs. If AVP is not called online, those logs do not exist. Pick one design: call AVP once per session to derive the dimensions, or compile Cedar policies into filters. Then make the diagram, the code and the audit claim agree.
- The semantic cache uses `FT.SEARCH` on "ElastiCache for Redis(啟用向量搜尋)". Vector search on ElastiCache arrived through Valkey. Verify the engine and version, or name MemoryDB, which has had vector search since 2024.
- The 0.95 cosine threshold and the 30% hit rate are stated as facts with no source. Label them as assumptions to tune against an eval set.

#### `ai-system-on-native-aws-part7-foundation-model-customization-governance-zh.md`
**Verdict:** light edit
- The central cost claim in §六 is probably stale: "Bedrock 客製模型必須用 Provisioned Throughput 託管(不能用 on-demand)" and pitfall 5. Bedrock added on-demand deployment for custom Amazon Nova models in 2025. Verify, then rewrite the break-even argument. It still holds for PT-only models, but the default answer for Nova changes.
- `new bedrock.CfnCustomModel` (L173) with a `/* 或用 CustomModelJob API 觸發 */` comment suggests the author wasn't sure it exists. Confirm whether CloudFormation actually supports this resource. If it does not, show the `CreateModelCustomizationJob` call from Step Functions instead, since readers will try to `cdk deploy` it.
- Reinforcement fine-tuning (Dec 2025) and Nova 2 are missing from the decision tree in §3.1. RFT is the relevant option for the "行為對齊" branch. Verify availability.
- The biggest cost line is "~$數千 / 月起". Give a model-unit hourly figure or a range.
- The RAG-vs-fine-tune framing in §一 and §5.1 is excellent, and the older English fine-tuning post should link here (see below).

#### `ai-system-on-native-aws-part8-realtime-streaming-fraud-detection-zh.md`
**Verdict:** light edit
- Two of the alternatives are dead or closing, and I am fairly confident of both. **Amazon Fraud Detector** stopped accepting new customers in late 2025, yet §5.2 recommends it as "許多團隊的務實起點". **Kinesis Data Analytics for SQL** was discontinued in early 2026, and it appears as "Kinesis SQL(舊)" in §5.1. Rewrite §5.2's alternative (for example, SageMaker AutoML/Canvas, or a partner service) and drop the SQL row or mark it as retired.
- The §3.1 diagram draws the synchronous < 50ms decision path as a **consumer of the Kinesis stream** ("②同步評分路徑" branching off Kinesis). A payment authorisation path is a synchronous API call. Only the feature path should hang off the stream. Redraw it, because the diagram currently contradicts §3.2 ②.
- A Lambda with a P99 of 50ms on a card-authorisation path needs provisioned concurrency and SnapStart-style caveats, and the fail-safe ("保守 fallback", pitfall 3) needs a concrete timeout budget per dependency (for example, rules 5ms, ML 20ms, graph 15ms).
- `FLINK-1_20` is fine, but check whether a newer Managed Flink runtime is current.

#### `ai-system-on-native-aws-part9-security-compliance-data-governance-zh.md`
**Verdict:** light edit
- The `DenyUnencryptedS3` SCP (§4.5, L230) will break things if copied. It denies any `PutObject` without an explicit `x-amz-server-side-encryption: aws:kms` header. That includes writes that rely on bucket-default SSE-KMS and AWS service writes such as CloudTrail and Config delivery. Add a `Null` condition guard, or recommend bucket-default encryption plus a bucket policy, and mention the service-principal exemptions.
- `DenyBedrockOutsideApprovedRegions` interacts with cross-region and global inference profiles. Explain that EU-scoped profiles are compatible and global profiles are not. Otherwise readers will deny themselves every current Claude model.
- §3.2 says public-endpoint traffic "即使加密,合規上仍是「觸網」". This overstates things, because traffic from AWS to AWS public endpoints already stays on the AWS backbone. PrivateLink's real value is network-level control and no IGW/NAT. Reword it so auditors are not misled.
- Otherwise this is a solid defence-in-depth structure, and the preventive-vs-detective framing in §5.3 and §5.4 is well done.

#### `deploying-huggingface-models-aws-cdk-sagemaker.md`
**Verdict:** rewrite/merge
- **As written, the container cannot start.** `inference.py` defines SageMaker-toolkit handlers (`model_fn`/`input_fn`/`predict_fn`/`output_fn`). The Dockerfile, though, is a plain `pytorch/pytorch:2.1.0` image with `ENTRYPOINT ["python", "inference.py"]`, so nothing serves `/ping` or `/invocations` on port 8080 and the health check fails. Either use the Hugging Face / PyTorch inference DLC, or add a real server.
- **The endpoint config contradicts the client code.** `asyncInferenceConfig` (L588) makes the endpoint asynchronous, but the Lambda calls synchronous `InvokeEndpointCommand` (L992), which asynchronous endpoints reject. The async output bucket `${ACCOUNT_ID}-ml-inference-output` is never created, and at L1226 the stack creates a bucket with `new s3.Bucket(app, ...)`, scoped to the app rather than to a stack.
- The title promises "Hugging Face Models", but the post only deploys SDXL through `diffusers`. It uses neither the HF DLC nor TGI/LMI, nor SageMaker JumpStart, which are the standard ways to deploy HF models in 2026. The pins (torch 2.1, diffusers 0.24, CUDA 11.8) date from late 2023.
- The "Production-ready security" claim clashes with the `AmazonSageMakerFullAccess` execution role. The cost section has no numbers. "Enable managed spot training" for a real-time endpoint is wrong, because spot does not apply to endpoints. The Lambda in-memory `Map` cache is presented as an optimisation, although each Lambda instance keeps its own copy of the cache.
- `authors: ["YennJ12 Engineering Team"]` does not match any author slug (`yen`, `alex-rodriguez`, …). The code-to-prose ratio is 84%. Cut the scaffolding (project tree, full stacks, CRUD Lambdas) down to the non-obvious parts, or retire the post in favour of Parts 3/5 plus a short "self-hosting an HF model" appendix.

#### `llm-fine-tuning-aws-bedrock-complete-guide.md`
**Verdict:** restructure
- The title and summary promise reinforcement fine-tuning, but no RFT job code exists. The RFT data format shown (L173–181, `responses` with `score`) does not look like Bedrock's actual RFT input, which uses prompts plus a reward function or grader. Verify it against the docs and either implement RFT properly or remove the claim.
- Every runnable example targets `amazon.titan-text-express-v1` with the Titan `inputText` request body (L1026). Titan Text has been superseded by Nova, so switch the examples to a fine-tunable Nova model and its request format. The `Claude` tag is misleading: the only Claude model Bedrock could fine-tune was Claude 3 Haiku, which is now deprecated. Drop the tag.
- The introduction lists "Reduce hallucinations by grounding responses in your data" as a fine-tuning benefit. That is the exact misconception Part 7 §一 of the series warns against. Remove it and link to Part 7 for the RAG-vs-fine-tune decision.
- There are no cost figures (training per token or hour, PT model units, on-demand custom deployment), and the `description` front matter is missing (only `summary`). The "Aggressive" hyperparameter preset uses *fewer* epochs than "Conservative", which is backwards as an overfitting guide.
- The code share is 81%. Collapse the data-prep and CLI wrappers into short excerpts, and put the explanation into when to choose SFT, CPT or RFT.

### Top 5 highest-impact fixes in this batch
1. **Link the series nav in all 10 parts** and make every part list 1–10. Today no part links to any other, and Parts 1–5 hide 6–10.
2. **Replace the retired `anthropic.claude-3-5-sonnet-20241022-v2:0`** (Parts 2, 4, 5) with a current inference-profile ID held in SSM, and widen Part 4's IAM resource to cover inference profiles.
3. **Fix the broken Hugging Face deploy post**: add a model server or use the DLC, and resolve the async-config vs sync-invoke clash. Otherwise retire or merge it, because it cannot be deployed as written.
4. **Add the 2025 AWS services the decision tables now need**: AgentCore (Part 4/10), Bedrock Data Automation (Part 2), S3 Vectors (Part 1/6), application inference profiles (Part 10). Remove or mark the closed alternatives: Fraud Detector and KDA SQL (Part 8), and Titan Text (Part 1 and the fine-tuning post).
5. **Correct the numeric inconsistencies**: Part 3's per-minute scaling target vs 10K QPS vs max 20 instances, Part 2's Comprehend units, Part 7's "PT only" claim and "~$數千" line. Give Part 5 a real cost estimate and a pipeline diagram.
