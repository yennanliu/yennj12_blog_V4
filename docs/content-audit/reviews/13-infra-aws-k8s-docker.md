## Infrastructure: AWS guides, CDK project write-ups, kubernetes-autoscaling (8), kubernetes-complete-guide (3), docker (4), redis-sentinel, flink platform — 33 posts

### Series-level observations
- **The CDK project posts read as expanded project READMEs, not reusable guides.** The worst cases are url-shortener, EKS platform, superset, wordpress, bitcoin, sentiment and nyc-taxi. They share one template: "The Challenge:" → "Why X?" → "Technology Stack Deep Dive" → "Architecture Tradeoffs Analysis" → "Production Lessons Learned", closing with the same four blocks: "Why This Architecture Succeeds / Architecture Decision Framework / Real-World Performance / Beyond the MVP". The "Real-World Performance" block always holds unsourced numbers ("Sub-10ms P99", "99.99% availability", "30% cost reduction", "10x faster deployment") for what are playground repos (`cdk-playground/tree/main/...`). The reusable parts are the tradeoff tables and a few non-obvious decisions, and they are buried under scaffolding. Fix pattern: open with the one or two decisions a reader could reuse, split "what the repo actually does" from "what you would add for production", and delete every "Real-World Performance" block unless it cites a measurement.
- **The four AWS "Complete Guide" posts (API Gateway, Load Balancer, VPC, DynamoDB) share an anti-pattern.** They create infrastructure imperatively from Java SDK calls inside Spring `@Service` classes (`ApiGatewayService.createRestApi`, `ApplicationLoadBalancerService`, VPC lifecycle services). Readers should not copy that. Everywhere else this batch preaches CDK, so these posts should either show IaC or cut the provisioning code down to the 20 lines that show the API shape. They run 85–91% code, much of it DTO/POJO classes.
- **Stale AWS and K8s versions are widespread, and some stop the code working as written:**
  - EKS 1.28 (autoscaling part 3) is past the end of extended support, so the hands-on demo cannot create its cluster.
  - EKS 1.31 (EKS platform post) is in paid extended support.
  - Karpenter `v0.32.1` / `karpenter.sh/v1beta1` appears in parts 2, 6, 7 and 8. The v1 API has been GA since Aug 2024.
  - `k8s.gcr.io` (k8s guide part 3) is a frozen registry.
  - "EKS Auto Mode (Preview)" (autoscaling part 2) has been GA since Dec 2024.
  - `anthropic.claude-3-sonnet-20240229-v1:0` (bitcoin, sentiment) is a retired Bedrock model.
  - Lambda `NODEJS_18_X` (url-shortener) is deprecated. Verify `NODEJS_20_X` (cognito, cloudwatch) against the Lambda deprecation calendar.
  - "Kinesis Data Firehose" has been renamed Amazon Data Firehose.
  - `docker-compose` v1 appears throughout the Docker series. It reached EOL in 2023, and part 1 already installs `docker-compose-plugin`.
- **Tags and categories drift:**
  - The tag `"AI"` is attached to posts with no AI content: url-shortener, wordpress, EKS platform, opensearch logging, superset, nyc-taxi, flink platform.
  - The cloudwatch and cognito posts carry the `ai` category.
  - Most CDK and AWS posts use `engineering` + `architecture` and skip `infrastructure`, which is the category CLAUDE.md defines for "AWS, Kubernetes, containers, CI/CD, observability". Swap `architecture` for `infrastructure` on the CDK posts.
  - Authors are non-slugs: "YennJ12 Engineering Team", "yennj12 team", and `author:` (singular) "Yen-Nan Liu" / "Yen" on the VPC, DynamoDB and flink posts. None of these resolve to an author page. Normalise to `["yen"]`.
- **kubernetes-autoscaling: 8 parts × ~1,600 lines (~13k lines) is the wrong shape.**
  - Every part's "Series Overview" lists only Parts 1..N. Part 1 links only to Part 2, so there is no forward navigation. The `./slug.md` links are a known issue.
  - Content overlaps across parts: Part 1 already has a full VPA "Approach 5" section before Part 5 covers VPA; Spot/Karpenter appears in parts 2, 6 and 7; KEDA in 1 and 6.
  - Part 8 is mostly a generic K8s security, PCI/HIPAA/SOC2 post with autoscaling in the title.
  - Suggested 5-part shape at 800–1,000 lines each: (1) pod autoscaling concepts (HPA + KEDA + VPA overview); (2) node autoscaling (CA / Karpenter v1 / EKS Auto Mode); (3) hands-on demo + monitoring (merge 3 + 4); (4) VPA and right-sizing, including in-place resize; (5) production operations (merge 7's runbooks with the useful parts of 6 and 8). Drop the hand-rolled "Custom Multi-Cluster Autoscaler" and "Custom Scheduler" code.
- **The zh Docker and Kubernetes guides overlap with the English posts and don't link to them.** Docker part 2's "Volume 與 Bind Mount" duplicates `docker-mount-complete-guide-comparison`, and k8s guide part 3's "⚡ 自動擴展機制" duplicates the whole autoscaling series. Neither zh series has any internal links: series navs are plain text, and k8s part 3 has zero links. Both read as reference manuals (100+ table rows) that repeat `--help` and the official docs. They contain no 「為什麼選 X 不選 Y」, no failure stories and no numbers.
- **Mainland terminology is common in the zh posts:** 運行 (26× in Docker part 1; use 執行), 服務器 (use 伺服器), 集群 (use 叢集), 數據 (use 資料; 11× in the flink post).

### Per-post

#### `ai-music-generation-aws-cdk-infrastructure.md`
**Verdict:** restructure
- Half of the SageMaker-vs-Bedrock comparison is fiction. The Bedrock stack (L609 onward) says "Bedrock doesn't currently have music generation models / This is a conceptual implementation" and calls `modelId='amazon.music-gen-v1'  # Hypothetical model`. The cost table then uses "Assumed pricing: $0.08 per generation" to derive a "Break-even point: ~10,950 generations/month". Yet the Conclusion's "Choose Bedrock When…" and "Startup MVP → Bedrock" read as real advice. Replace the fictional path with a real alternative: SageMaker Serverless or Async Inference with scale-to-zero, or a third-party music API. Otherwise retitle away from "Bedrock Comparison".
- Licensing is wrong for a "production" guide. The box at L40 says "Open source (MIT license)". MusicGen's code is MIT, but the pretrained weights are CC-BY-NC 4.0 (non-commercial). All three "Production Use Cases" (streaming app, creator tool, game studio) are commercial. Add a licensing callout.
- The cost model assumes one ml.g5.xlarge running 24/7 ($857/month). It never considers async inference, auto-scaling to zero or Spot, which are the actual levers for bursty creative workloads.
- The model landscape table (Riffusion, Jukebox, MusicLM) is stale. Verify against current options before republishing.
- Front matter: no `description`. The `summary` is truncated mid-sentence ("for generating…").

#### `aws-api-gateway-comprehensive-guide-comparison.md`
**Verdict:** restructure
- The post never distinguishes REST API vs HTTP API vs WebSocket API. That is the first decision anyone makes with AWS API Gateway, and it changes price (~70% cheaper for HTTP API), features (usage plans, caching and request validation are REST-only) and authorizer types. Add it right after "⚖️ API Gateway vs Load Balancer".
- It also omits the hard limits that drive the ALB-vs-API-GW choice: the 29 s integration timeout (only raisable by quota request since 2024), the 10 MB payload limit, and per-request pricing at high RPS. "timeout" never appears in the post. The comparison table's "High-performance → Load Balancer" claim needs these numbers behind it.
- "### 5. Response Aggregation Service" (L766–1230, ~460 lines) is Spring code with a dozen nested DTOs (`UserProfile`, `Order`, `Review`, `PriceInfo` …). It is a BFF pattern, not API Gateway. Cut it to 30 lines or move it to a BFF post.
- `ApiGatewayService` creates REST APIs through the SDK at runtime (L292–495). Replace it with a short CDK/SAM snippet. `spring-cloud-starter-aws 2.4.4` is the legacy line; Spring Cloud AWS 3.x is current.
- The mermaid "Analogy" diagram (traffic cop vs concierge) adds little. Keep the table.

#### `aws-dynamodb-complete-guide-optimization.md`
**Verdict:** restructure
- A "Complete Guide" to DynamoDB that never mentions single-table design (0 hits) misses the topic practitioners actually struggle with. Add an access-pattern → key-design worked example. That is where this post could beat the docs.
- There are no hard numbers behind "Hot Partition Prevention" (L707). Add the per-partition limits (3,000 RCU / 1,000 WCU, 10 GB with an LSI), adaptive capacity, on-demand vs provisioned, and DAX. Readers need these to judge when sharding is needed at all.
- "Strategy 4: Adaptive Capacity Management" (L755) polls `DescribeTable` every 5 minutes from a `@Scheduled` Spring bean to adjust capacity. That hand-rolls Application Auto Scaling and is an anti-pattern. Replace it with auto-scaling / on-demand configuration.
- In "When to Choose DynamoDB", "Mobile applications needing offline sync capabilities" is a feature of AppSync/Amplify, not DynamoDB.
- Front matter uses `author:` (singular) and has no readTime.

#### `aws-load-balancer-complete-guide-comparison.md`
**Verdict:** light edit
- Several cells in the "🔍 Detailed Feature Matrix" (L1252) are wrong or stale:
  - "Latency ALB ~100ms / CLB ~100ms" is off by an order of magnitude; ALB adds single-digit ms.
  - NLB has supported security groups since 2023.
  - ALB cross-zone is not "Always On"; it can be disabled per target group since 2022.
  - "Static IP ALB ❌" and "For Static IPs: NLB is the only option" ignore Global Accelerator and ALB-behind-NLB.
  - "CLB Source IP Preservation ❌" ignores Proxy Protocol.
  Readers will copy this table, so fix it first.
- The Java SDK provisioning services (`ApplicationLoadBalancerService` with ~500 lines of config POJOs) could be cut to a CDK snippet per LB type.
- A heading is duplicated ("📋 Overview and Features" per section). Name each heading after its LB type for the TOC.
- Consider merging with the API Gateway post into one "Choosing an AWS entry point: ALB / NLB / API Gateway / CloudFront" decision guide. Both posts have the same date and repeat the same comparison.

#### `aws-vpc-complete-guide-enterprise-networking.md`
**Verdict:** restructure
- The title promises "Enterprise Networking Patterns", yet Transit Gateway only appears in one diagram node and one table cell. The post has no PrivateLink, no IPAM, no centralized egress / inspection VPC and no Cloud WAN. For enterprise networking in 2026, TGW and PrivateLink are the core content.
- The Conclusion's "When to Use VPC Peering" lists "Hybrid cloud integration scenarios". Peering doesn't do hybrid; that needs VPN or Direct Connect. It also lists "Multi-account architectures" without the non-transitive / mesh-explosion caveat the post itself raises at L477.
- Java code for VPC lifecycle management (L486+) is the wrong tool. Show Terraform/CDK or drop it.
- There are no diagrams for the patterns named ("Hub and Spoke", "Multi-Account"). ASCII or mermaid diagrams would explain far more than the code here.

#### `bitcoin-trading-system-aws-cdk-ml-predictions.md`
**Verdict:** rewrite/merge
- The "ML" is overstated. `predict_with_custom_model` has the docstring "Use custom LSTM/GRU model" but implements an SMA-20/50 crossover with a hard-coded `'confidence': 0.7`. The HuggingFace path calls a non-existent `bitcoin-price-predictor` endpoint. Nothing is backtested, yet the summary says "production-ready" and the takeaways claim "Ensemble approach improves accuracy". Either add a backtest with real numbers or reframe the post as "pipeline skeleton".
- Uses retired `anthropic.claude-3-sonnet-20240229-v1:0`, and asking an LLM for a price point is itself questionable; explain what the LLM is for.
- Timestream (L143–206) — Timestream for LiveAnalytics stopped onboarding new customers in 2025 (verify); readers following this may not be able to create it.
- The post shares its date, structure, "Risk Management" section and Bedrock model with `sentiment-driven-stock-trading-aws-cdk-twitter.md`. Merge them into one "event-driven trading signal pipeline on AWS" post with two signal sources.
- The "Cost Optimization" section has no numbers.

#### `building-centralized-logging-opensearch-aws-cdk.md`
**Verdict:** light edit
- The architecture skips the hardest step: how pod logs get from EKS into CloudWatch Logs (Fluent Bit DaemonSet / Container Insights). "Collection: CloudWatch Logs captures logs via subscription filters" skips the agent entirely. Add 10 lines on it.
- Stale names and versions: "Kinesis Data Firehose" is now Amazon Data Firehose, and `OPENSEARCH_2_3` is very old. It also doesn't compare OpenSearch Serverless or CloudWatch Logs Insights, the obvious "why not X" alternatives.
- "Key Takeaways: Serverless architecture reduces operational overhead" contradicts the provisioned `r6g.large.search` domain. The `"AI"` tag is irrelevant.
- It is a good length (460 lines) and a reasonable code/prose balance. This is the healthiest CDK post in the batch.

#### `building-production-kubernetes-platform-aws-eks-cdk.md`
**Verdict:** restructure
- The code contradicts the story. The "Node Group Strategy" table promises c5.xlarge / r5.large / t3 pools for Kafka, Spark and monitoring. The "Production node group configuration" is a single `t3.medium` group with min 1 / max 5. The $295/month TCO likewise can't run the Kafka + Spark + Airflow + Prometheus stack described.
- The conclusion contradicts itself with unsourced numbers: "reduces operational overhead by 70%" and "EKS over Self-Managed: 60% reduction", then "99.9% availability", "30% cost reduction", "10x faster deployment". Remove them.
- `KubernetesVersion.V1_31` is in paid extended support as of Sept 2026. The post uses Cluster Autoscaler with no mention of Karpenter or EKS Auto Mode, and has no Pod Identity / IRSA discussion.
- Two headings are duplicated ("EKS vs. Self-Managed Kubernetes", "Infrastructure as Code Benefits") because the same comparison appears twice (L29 and L453). No `description`.

#### `building-serverless-url-shortener-aws-cdk.md`
**Verdict:** light edit
- The design has an internal contradiction. The endpoint table caches `GET /{code}` redirects at the edge for 1 hour, while analytics are captured by `console.log` inside the Lambda. Cached redirects never reach Lambda, so click counts will be badly undercounted. Pick one, or move analytics to CloudFront logs. This is exactly the kind of tradeoff a URL-shortener post should teach.
- "Sub-10ms P99 latency for URL resolution" via API Gateway + Lambda isn't credible; API Gateway alone typically adds 10–30 ms. "Managed services reduce operational overhead by 90%" is unsourced.
- `NODEJS_18_X` is deprecated on Lambda. The short-code algorithm section (L236) is the most reusable content, so expand the collision-probability math there.
- No `description`. "AI" tag irrelevant.

#### `centralized-grafana-prometheus-monitoring-aws-cdk.md`
**Verdict:** restructure
- Prometheus TSDB on EFS (L120, L210 "Store in EFS-backed TSDB (30–90 days)") goes against the Prometheus docs, which state that NFS-style filesystems are unsupported and risk unrecoverable corruption. That is a correctness problem for a "production-ready" post. Use EBS (ECS on EC2) or remote_write to Amazon Managed Service for Prometheus / Mimir / Thanos. The post even lists Cortex/Thanos at L73 and then doesn't use them.
- The post never compares against Amazon Managed Prometheus and Amazon Managed Grafana. "Why self-host?" is the first question a reader will have, and the answer (cost at N series, control, plugins) is what makes it a reusable guide.
- `prom/prometheus:latest` and `grafana/grafana:latest` in a production stack; pin versions.
- It overlaps heavily with `centralized-monitoring-system-aws-cloudwatch-grafana-cdk.md`: both deploy Grafana on ECS Fargate with EFS via CDK. Merge them, or cross-link with a clear "CloudWatch-backed vs Prometheus-backed" split.
- The trailing "**Tags:** #prometheus …" line duplicates the front matter; remove it. No `description`.

#### `centralized-monitoring-system-aws-cloudwatch-grafana-cdk.md`
**Verdict:** restructure
- "⚙️ Configuration Design" runs L250–591, over 300 lines of TypeScript config objects before any stack code. It is followed by ~800 lines of stack code. Cut the config to one representative service and link the repo.
- The "CloudWatch vs Grafana" table is useful. It misses CloudWatch's per-metric / per-dashboard / Logs Insights scan pricing, which is what drives the hybrid choice. Put numbers in "💰 Cost Optimization".
- The same Grafana-on-Fargate + EFS + `grafana/grafana:latest` pattern as the Prometheus post, and no mention of Amazon Managed Grafana.
- `'arn:aws:sns:us-east-1:xxx:critical-alerts'` placeholders sit in copy-paste config. Use `${AWS::AccountId}` or CDK tokens.
- The `ai` category and "AI" tag are wrong. The Related Posts list links an Express.js post that has nothing to do with monitoring.

#### `centralized-user-access-control-aws-cognito-cdk.md`
**Verdict:** light edit
- Stale Cognito API: `advancedSecurityMode: cognito.AdvancedSecurityMode.ENFORCED` (L785) is deprecated. Since the Nov 2024 Lite / Essentials / Plus feature plans, CDK uses `featurePlan` + threat-protection settings. The post never mentions feature-plan pricing, which changes the single-vs-multiple-pool cost argument in "✅ Pros and Cons Analysis".
- The recommended multi-tenant model creates one group per tenant×role (`tenant-acme-admin`, `tenant-widget-user` …). The post doesn't discuss the per-pool group quota, ID-token size growth, or the fact that `custom:` attributes are immutable in schema. Those are the real limits that push B2B SaaS to multiple pools. Add the numbers and the flip condition.
- Strongest post of the CDK set on reusable design discussion ("Single vs Multiple User Pools"), so it's worth keeping current.
- Five categories exceed the 1–3 rule. Drop `ai` and pick `infrastructure` + `architecture`.

#### `deploying-apache-superset-production-aws-cdk-ecs-fargate.md`
**Verdict:** restructure
- The deployment has no Celery workers or beat (0 mentions of "celery"). Superset's async queries, alerts and reports, and thumbnail caching all require them. A "Production-Ready BI Platform" that runs only the web tier is missing its most operationally tricky component.
- There is a security bug in the init task (L556–575). `--password ${ADMIN_PASSWORD}` inside a TypeScript template literal is interpolated at synth time, so the admin password ends up in plain text in the CloudFormation template. The same script also runs `superset load_examples` in "production". Use a Secrets Manager secret injected as an env var and drop the examples.
- `apache/superset:latest` for both the service and the init task means a redeploy can silently run a schema-changing version. Pin a version and run `db upgrade` as a gated step.
- The closing boilerplate repeats the CDK template ("99.95% availability", "10-100x query performance improvement" from Redis). No `description`.

#### `docker-complete-guide-part1-introduction-zh.md`
**Verdict:** light edit
- A solid intro that gets the job done, but it is generic. Nothing here goes beyond the official Get Started docs. Add one concrete "why containers vs VM" comparison with numbers (startup time, image size, density) to earn the slot.
- The series nav is text only ("第二篇：Docker 指令與實務操作"). Link parts 2 and 3, and link `docker-mount-complete-guide-comparison` from the storage mention.
- 運行 ×26 should become 執行. `readTime: "50 min"` is inflated for this length.

#### `docker-complete-guide-part2-commands-zh.md`
**Verdict:** restructure
- It is a command reference: 142 table rows that restate `docker <cmd> --help`. Reader value is low unless it's reorganised around tasks ("容器起不來時怎麼查", "磁碟滿了怎麼清", "怎麼從容器拷資料出來") with the commands as answers.
- The "🎯 Docker Compose 基礎指令" section teaches `docker-compose` (v1, EOL 2023), while part 1 installs `docker-compose-plugin`. Switch to `docker compose`.
- There is no series nav (unlike parts 1 and 3). 服務器 should become 伺服器.
- The Volume/Bind Mount section duplicates the English docker-mount post; link it instead.

#### `docker-complete-guide-part3-advanced-zh.md`
**Verdict:** light edit
- Stale commands: `docker-compose` v1 throughout "Docker Compose 深入應用" (L805–844) and blue-green (L1201), and `version: "3…"` in the Compose file, which Compose v2 ignores and warns about. Mentioning BuildKit as "Docker 18.09+" is outdated framing because BuildKit has been the default builder since 23.0.
- "Docker Swarm（集群管理）" in the learning path: Swarm is a weak 2026 recommendation, and 集群 should become 叢集.
- Security section: add image scanning (Docker Scout / Trivy), SBOM/provenance and rootless mode. These are the 2026 baseline.
- 75% code with good multi-stage examples. The multi-stage build section is the most useful part of the series.

#### `docker-mount-complete-guide-comparison.md`
**Verdict:** light edit
- "Bind Mount Performance (macOS/Windows)" (L1335–1343) recommends `:delegated` / `:cached`. Current Docker Desktop, with VirtioFS as the default file sharing, ignores these flags. Replace them with VirtioFS, synchronized file shares, or "keep `node_modules` in a volume".
- The performance comparison is qualitative ("Good / Excellent / Moderate"). One measured `npm install` or file-watch benchmark on macOS bind mount vs volume would make the section trustworthy.
- `version: '3…'` in the Compose examples is obsolete.
- Otherwise a clear, well-organised post; the decision tree and comparison matrix are useful.

#### `kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md`
**Verdict:** restructure
- The series overview lists only Parts 1–2, so readers landing here can't find parts 3–8. Regenerate a complete nav for every part and place it at the bottom as well.
- "Approach 5: Vertical Pod Autoscaler (VPA)" is a full section that Part 5 then covers again at length. Keep a one-paragraph pointer here.
- The concepts are sound and the "Comparison Matrix" is useful. Tighten the length (1,700 lines) by trimming repeated "Overview and Architecture / Pros and Cons" sub-templates per approach.
- `queueURL: …/xxx/image-upload-queue` in a KEDA ScaledObject meant for copy-paste; use `<ACCOUNT_ID>`.

#### `kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md`
**Verdict:** restructure
- The Karpenter section is two major versions stale: `KARPENTER_VERSION=v0.32.1` (L572) with `apiVersion: karpenter.sh/v1beta1` NodePool (L633). v1 has been GA since Aug 2024 and v1beta1 manifests no longer apply. Rewrite this section first, since parts 6, 7 and 8 inherit the same manifests.
- "EKS Auto Mode (Preview)" (L1129) has been GA since Dec 2024. It should be a first-class option next to CA and Karpenter, with a "when to pick which" flip condition. The Cluster Autoscaler image `v1.28.2` must match the cluster minor version; say so.
- The GKE and AKS sections are broad but shallow. For an AWS-heavy blog, consider keeping them as a comparison table only.

#### `kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md`
**Verdict:** restructure
- The demo does not run as written:
  - Step 1 runs `npm install @aws-cdk/aws-eks @aws-cdk/aws-ec2 @aws-cdk/aws-iam`, which are CDK v1 packages (EOL June 2023), while the stack imports `aws-cdk-lib`.
  - `eks.KubernetesVersion.V1_28` (L167) is past EKS extended support, so the cluster cannot be created.
  - It needs a current version plus the matching `kubectlLayer`.
  For a "Hands-On" post, being runnable is the whole point.
- The full `cdk.json` with ~50 feature-flag context keys (L300–365) is generated boilerplate; delete it.
- Merge with Part 4. Both deploy the same php-apache app on EKS, and the monitoring setup belongs with the demo it measures.

#### `kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md`
**Verdict:** rewrite/merge
- The load-test commands are subtly wrong. `hey -z 5m -q 10` sets a per-worker QPS, and `hey` defaults to 50 workers (`-c 50`), so the "Light load: 10 req/s" is actually ~500 req/s. The URL is a ClusterIP (`kubectl get svc … clusterIP`), which is unreachable from the laptop where `brew install hey` runs. Run `hey` inside the cluster or port-forward.
- "Understanding the HPA Formula" is the most valuable part. Expand the tolerance (10%), stabilization window and readiness-delay effects with a worked numeric example.
- Merge into Part 3 as "demo + observe + tune". Pin the kube-prometheus-stack chart version.

#### `kubernetes-autoscaling-complete-guide-part5-vpa-resource-optimization.md`
**Verdict:** restructure
- In-place resize is stale and wrong. L453 calls in-place resource updates a "Planned feature", and the L468 example says `updateMode: "Auto"  # In-place updates without pod restart`. `Auto` currently means evict and recreate. In-place pod resize reached beta in K8s 1.33 and GA later, and VPA added an `InPlaceOrRecreate` mode (verify the exact VPA version). That changes the "VPA + HPA" advice in "Part 4: Combining VPA with HPA", which is the headline topic.
- "Part 1: Installing VPA" through "Part 9: Best Practices" use "Part N" inside a post that is itself "Part 5". The collision confuses readers; use "Step N" or plain headings.
- Related Topics lists only Parts 1–4.

#### `kubernetes-autoscaling-complete-guide-part6-advanced-patterns.md`
**Verdict:** rewrite/merge
- At 91% code, this is mostly hand-rolled controllers: "Pattern 2B: Custom Multi-Cluster Autoscaler", "Cost-Aware Scheduling with Custom Scheduler", and "Pattern 5A: Predictive Autoscaling with Machine Learning", which is a stub (`# ... (implementation details)`, empty training data). Readers shouldn't deploy these. Replace them with pointers to existing tools (Karmada / OCM for multi-cluster, KEDA cron / predictive scalers) and 20-line illustrative snippets.
- "Pattern 1A: Database Scaling with StatefulSet" needs a strong caveat. HPA-driven replica changes on a database StatefulSet don't rebalance data or replication, and naive use can cause harm.
- Karpenter `v1beta1` (L983) again.
- Merge the Spot-fallback and KEDA batch-job material into Parts 2 and 1 and drop the rest.

#### `kubernetes-autoscaling-complete-guide-part7-troubleshooting-war-stories.md`
**Verdict:** light edit
- The war stories are presented as real incidents with precise figures ("Date: November 25, 2022 … Impact: $3.2M revenue loss, 89% service degradation") but have no company, source or "composite" disclaimer. Label them as illustrative or composite scenarios; readers will otherwise quote the numbers.
- One causal step is doubtful: "08:53 UTC – API server overwhelmed by HPA queries (1000+ req/s)". The HPA controller runs a single 15 s sync loop against the metrics API. Rework the cascade so the lesson (startup time + missing node headroom + no scale-up policy) stays technically sound.
- "Debugging Workflow" and "Emergency Runbook" are the most practically useful content in the series. Keep them as the core of a merged "production operations" part.
- Karpenter `v1beta1` (L682).

#### `kubernetes-autoscaling-complete-guide-part8-security-compliance-governance.md`
**Verdict:** consider retiring
- Beyond the Gatekeeper policies for HPA/VPA limits (L403–649, genuinely autoscaling-specific and worth keeping), the post is generic K8s security: namespace isolation, HNC, and PCI-DSS / HIPAA / SOC 2 sections that map controls loosely. Keep the ~250 lines of autoscaling policy-as-code and fold them into the operations part.
- Gatekeeper-only coverage misses built-in `ValidatingAdmissionPolicy` (CEL, GA in 1.30) and Kyverno, both simpler for "max replicas" style rules.
- The Karpenter `v1beta1` example (L774) is stale.

#### `kubernetes-complete-guide-part1-introduction-zh.md`
**Verdict:** light edit
- L132–133 say "Docker 提供容器運行時 / Kubernetes 使用 Docker … 作為底層". dockershim was removed in 1.24 (2022). Correct this to containerd / CRI-O, with Docker only as the image-build tool. L209's runtime row also still lists Docker.
- The series nav is plain text with no links. Add links to parts 2–3 and to the autoscaling series.
- `readTime: "60 min"` is inflated. 運行 ×11 should become 執行.

#### `kubernetes-complete-guide-part2-resources-zh.md`
**Verdict:** light edit
- The Ingress section is built on `nginx.ingress.kubernetes.io/*` annotations with no mention of Gateway API. Kubernetes announced the ingress-nginx controller's retirement (verify date; maintenance ending ~March 2026). A 2026 resources guide should present Gateway API as the forward path.
- `nginx:1.24` examples are fine but old; pin a current tag.
- The kubectl reference tables duplicate the official cheat sheet. Focus on "which command when debugging X". No series nav.

#### `kubernetes-complete-guide-part3-advanced-zh.md`
**Verdict:** restructure
- The Cluster Autoscaler manifest uses `k8s.gcr.io/autoscaling/cluster-autoscaler:v1.27.0` (L215). k8s.gcr.io is frozen, so use `registry.k8s.io` and a version matching the cluster.
- "⚡ 自動擴展機制" re-covers HPA/VPA/CA in less depth than the 8-part English series and doesn't link to it. Replace it with a short summary and a link.
- The lang-mismatch flag is borne out: this is 79% English YAML with sparse Chinese. Add Chinese explanation of why each production setting matters (RBAC least-privilege choices, NetworkPolicy default-deny), and cut repeated YAML.
- It has zero links of any kind, not even to parts 1–2.

#### `nyc-taxi-big-data-pipeline-spark-kafka-streaming.md`
**Verdict:** rewrite/merge
- Trust problems:
  - The scale claims don't match the dataset. It says "Millions of taxi trips daily, generating terabytes of data monthly" and, in Achievements, "Successfully processed 50TB+". The public TLC trip-record files are on the order of hundreds of MB per month, and the whole history is far below 50 TB.
  - The TLC does not publish a real-time stream, so the "Real-time Taxi Events (Stream)" must be simulated. Say so.
  - "<50ms latency for 99% of streaming events", "40% reduction in processing costs" and "99.8% accuracy" have no measurement behind them.
- The versions are inconsistent: the stack lists "Apache Spark 2.4.3 / Spark Streaming 2.4.3" (2019), while the CloudFormation uses `ReleaseLabel: emr-6.3.0`, which ships Spark 3.x. The code uses Structured Streaming (`readStream`). Pick one current version (EMR 7.x / Spark 3.5).
- At 2,800 lines and 89% code, it is the longest post in the batch. The "System Performance Analysis" is a Python monitoring class, not results. Split it into batch and streaming posts, or cut it to the architecture decisions plus the Spark job core, and link the repo.
- No `description`. The "AI" tag is irrelevant. This is not a CDK post (CloudFormation), so the CDK framing elsewhere doesn't apply.

#### `redis-sentinel-high-availability-setup-guide.md`
**Verdict:** light edit
- The Docker Compose setup (L244–400) has the classic Sentinel-in-Docker trap. It sets no `sentinel announce-ip` / `replica-announce-ip`, so Sentinel hands the Spring Boot client container-internal IPs. From a host-run app, failover then "works" but the client can't connect. Add announce settings or run the app in the same network, and explain why.
- The post doesn't discuss data-loss windows: async replication, and `min-replicas-to-write` / `min-replicas-max-lag` to bound split-brain writes. That discussion separates an HA guide from a setup tutorial.
- Add a 2026 note on Redis licensing (the 7.4 RSAL/SSPL change, then AGPL in Redis 8) and Valkey as the drop-in fork used by ElastiCache. It changes which image readers should pull.
- "3. Redis Service Implementation" and "4. Caching Service" (~700 lines of generic RedisTemplate CRUD) are boilerplate; cut them to the Sentinel-specific `ReadFrom` / topology-refresh config.

#### `scalable-wordpress-ecs-fargate-architecture.md`
**Verdict:** light edit
- `define('WP_REDIS_HOST', 'localhost')` (L263) and the Dockerfile installs the Redis extension, but the architecture has no Redis/ElastiCache and there is no sidecar, so object caching silently fails. The "Session Management" challenge listed at the top is also never resolved. Add ElastiCache (Valkey) or remove the config.
- Serving PHP from EFS is the main WordPress-on-Fargate performance trap. The OPcache settings (L469) are the key mitigation (`validate_timestamps`, revalidate frequency). Say that explicitly, and consider offloading media to S3 (WP Offload Media), which "EFS vs S3" discusses without recommending.
- "Our scalable WordPress platform uses a microservices approach" mischaracterises the design; WordPress here is a monolith behind an ALB. `wordpress:6.4-php8.2-apache` is dated.
- Putting cost numbers in a TypeScript object literal (`costAnalysis = {…}`, with a `storageGost` typo) is odd. Use a table.

#### `sentiment-driven-stock-trading-aws-cdk-twitter.md`
**Verdict:** rewrite/merge
- The biggest cost and feasibility factor is missing. Real-time X.com access needs a paid X API tier: filtered stream / high read caps cost thousands of $/month (verify current pricing). Meanwhile "Cost Optimization" suggests "Consider RI for consistent Alpaca API usage", which is meaningless because you can't buy reserved instances for a third-party API. Without this, "Why X.com + AWS" is not credible.
- The example payload uses a real public figure (`"username": "elonmusk"`) with an invented quote about TSLA production numbers. Use a fictional account to avoid presenting fabricated statements as real.
- "Compliance: Meeting SEC regulations for automated trading systems" is never substantiated. Either name the rules (e.g., pattern-day-trader limits, broker API terms) or drop it. Claude 3 Sonnet on Bedrock is retired.
- Merge with the bitcoin post (same template, same date, same risk-manager design) into one signal-pipeline post.

#### `springdataplatform-flink-management-system.md`
**Verdict:** light edit
- This is a project README ("專案亮點 ✅ … 企業級架構"). It never explains why you'd build this rather than use existing Flink tooling: the Flink Web UI / SQL Gateway (1.16+), the Flink Kubernetes Operator, or Apache StreamPark. Add that comparison and the one or two problems the project actually solves.
- The stack is dated: Vue.js 2.x (EOL Dec 2023) and `flink:1.15.2` (out of support). State the versions as "at time of writing" or upgrade. Verify the status of Apache Zeppelin before recommending it.
- Language and naming: a Chinese post without the `-zh` filename suffix, and 數據 ×11 should become 資料. `author: "Yen"` (singular, non-slug) and no readTime.

### Top 5 highest-impact fixes in this batch
1. **Make the autoscaling hands-on runnable and current.** In part 3, replace the CDK v1 `npm install @aws-cdk/*` with `aws-cdk-lib` and move off `KubernetesVersion.V1_28`. Rewrite the Karpenter `v0.32.1` / `karpenter.sh/v1beta1` manifests to v1 across parts 2, 6, 7 and 8. Correct VPA in-place resize (part 5, L453/L468). Then collapse the 8 parts into ~5 with complete bidirectional nav, following the shape proposed above.
2. **Remove fabricated or implausible claims that readers will quote:**
   - ai-music's hypothetical Bedrock model and its break-even math, and the MusicGen "MIT" licensing claim (weights are CC-BY-NC)
   - nyc-taxi's "50TB+" and latency/cost figures
   - the "Real-World Performance" blocks in the CDK posts (EKS, URL shortener, Superset)
   - the war-story dollar figures presented as fact (label them composite)
3. **Fix the correctness and security bugs in "production" CDK code:**
   - Prometheus TSDB on EFS (grafana-prometheus)
   - `${ADMIN_PASSWORD}` interpolated into the CloudFormation template, plus `load_examples` (superset)
   - edge-cached redirects that bypass analytics (url-shortener)
   - `WP_REDIS_HOST=localhost` with no Redis (wordpress)
   - no Sentinel `announce-ip` (redis-sentinel)
4. **Merge the overlapping pairs:** bitcoin + sentiment trading, grafana-prometheus + cloudwatch-grafana, API Gateway + Load Balancer. In the zh Docker/K8s guides, point to the English deep dives (docker-mount, autoscaling series) instead of re-covering them. Each pair currently splits the reader and repeats the same template.
5. **Normalise front matter across the batch:** drop the `"AI"` tag and `ai` category from non-AI posts; move the CDK/AWS posts to `infrastructure`; normalise authors to `["yen"]` (replacing "YennJ12 Engineering Team", "yennj12 team" and singular `author:`); add real `description`s to the ~15 posts that only have a truncated `summary`; and update retired model IDs and runtimes (Claude 3 Sonnet, `NODEJS_18_X`, Kinesis Data Firehose naming, `k8s.gcr.io`, `docker-compose` v1).
