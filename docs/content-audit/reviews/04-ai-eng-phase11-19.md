## ai-eng-from-scratch phases 11–19 — 22 posts

### Series-level observations
- **Interview framing goes well past the tag.** Every post opens with a `面試情境` block ("面試官問…"), and several say so outright in the prose: 11p1 §九 "**回答面試題**：從 $0.04 到 $0.008…", 11p2 footer "適合準備 Staff / Senior AI 工程師面試的讀者", 18p1 "這道題考的不是你背得出多少防禦技術". CLAUDE.md and the plan both say this is a curriculum, not interview prep. Dropping the `Interview` tag is not enough. Reword `面試情境` as a `實戰情境` / project brief ("你的團隊…") and remove the interviewer voice. That is a mechanical pass over 22 opening blocks plus about 5 inline sentences.
- **Series nav is dead in 21 of 22 posts, and the labels are wrong as well as the slugs.** Link targets are planned names that were later renamed (`phase11-part2-multi-model`, `phase14-part2-memory`, `phase19-part2-voice-interface`…), and the anchor text describes topics that don't exist ("Phase 12 Part 1：AI 系統可觀測性", "Phase 18 Part 2：LLM Observability", "Phase 19 Part 2：多模態 RAG"). 17p3, 18p1 and 19p1 use relative `../slug` links, which breaks the root-absolute rule in CLAUDE.md. Five posts link `/tags/ai-eng-from-scratch/`, but no post carries that tag, so the "系列完整目錄" link also 404s. Fix: add a series tag to all 44 posts (or a series landing page), then regenerate every nav block from the real filename list in one scripted pass.
- **The footer numbering contradicts itself**: "系列第 23 篇" (11p2), "第 41 篇" (19p1), "19 個 Phase、63 篇文章" (19p3). The plan says ~44. Pick one number or drop the counts.
- **The model roster is 2024-era although the posts are dated June 2026**: GPT-4o/4o-mini, GPT-4V, `claude-3-5-sonnet-20241022`, `claude-3-haiku`, `gpt-3.5-turbo`, Llama-2, LLaVA-1.6, and the $15/$75 "flagship" price tier. Reasoning models, 2025–26 frontier models and current prices never appear. Where a model name is only illustrative, say "旗艦 / 中型 / 輕量" and date the price table. Where the name is load-bearing (fallback chains, VLM accuracy tables), refresh it.
- **The same topics are taught twice, with no cross-links**, and the numbers disagree between copies: vLLM/PagedAttention (11p1 vs 17p1), RAG hybrid+rerank+RAGAS (11p2 vs 19p1, with 4 of 6 decision tables effectively duplicated), attack taxonomy + Constitutional AI + defence stack (15p2 vs 18p1), tracing/A-B (14p4 vs 17p2), voting consensus (16p1 §七 vs 16p2 §六). The only phase references outside a post's immediate neighbours are in 19p3. Each later post should open with "前置：Phase X Part Y" and link back instead of re-deriving.
- **Unsourced "internal" benchmarks are presented as measurements.** Most §九 tables are precise to 0.1% ("Prompt Injection 攔截率 99.2%", "越獄成功率 0.4%（內部 red-team 數據）", "醫療診斷 A/B 10K 查詢", "CTR 3.2%→6.4%"), and the capstones claim first-person production delivery ("我在 2025 年底實際交付", "上線後 90 天的真實指標"). Label these as illustrative scenario numbers, or cite a paper. Several contradict themselves (see per-post notes), which undermines the rest.
- **"Phase 1/2/3" means two different things.** The 三個演進階段 labels (POC/MVP/Scale) share the word "Phase" with the curriculum's Phase 1–19, so "Phase 3 智慧路由" and "Phase 3 of the series" read the same. Rename the evolution stages "階段一/二/三" or "POC/MVP/Scale" series-wide.
- **Heading and diagram hygiene.** Box-art headings (`### ╔════╗ / ### ║ Phase 1 ║ / ### ╚════╝`) turn into three junk TOC entries and duplicate anchors (14p1, 15p1, 17p2, 18p1, 19p2). Use a plain `### Phase 1：POC（…）` heading and keep the box art inside a code block, if anywhere. The 7–14 diagram counts include decision tables drawn as ASCII inside code fences (14p3 has 0 Markdown tables). Those do not reflow on mobile. Converting them to real tables would bring most posts back toward the 2–4-diagram standard without cutting content.

### Per-post

#### `ai-eng-from-scratch-phase11-part1-inference-serving-zh.md`
**Verdict:** light edit
- A strong, coherent post. The memory-bandwidth-wall arithmetic in §一 (140 GB / 2 TB/s ≈ 70 ms) is exactly the kind of first-principles number the series needs.
- The hardware is A100-only. In 2026, H100/H200/B200 and FP8 are the default, and FP8 is only mentioned as an aside in §七. Add an H100/FP8 column to the §九 table, or at least a sentence on how the ratios shift.
- The serving landscape is missing SGLang, the vLLM V1 engine and prefix caching / chunked prefill. Decision 1 compares only vLLM/TGI/TRT-LLM (TGI is now in maintenance mode — verify).
- §九 insight 4 "回答面試題" and the opening `面試情境` need rewording (see series notes). The 23-min readTime is too long for a 452-line post.

#### `ai-eng-from-scratch-phase11-part2-rag-evals-zh.md`
**Verdict:** restructure
- It runs past the 十 cap (`十、生產常見問題`, `十一、Embedding 模型選型`, `附錄`) and nav is not numbered. Fold §十一 into §四/§五, move the checklist into §十, and make nav the last numbered section.
- The embedding cost math contradicts its own advice (§十一): self-hosted BGE-M3 is "$36/day vs text-embedding-3-small $4/day" at 200K queries, yet it says "< 500K queries/day 用閉源 API 更划算；超過後自部署開始有優勢". At those rates the crossover is around 1.8M/day. Fix the numbers or the threshold.
- The footer is duplicated (lines ~703 and ~715), and the second copy carries the "準備…面試" line.
- The embedding table is stale: E5-large-v2, Cohere embed-v3 (v4 exists) and no Qwen3/Gemini-class embedders. Date the table.
- Coordinate with 19p1. That capstone should *apply* this post, not repeat its chunking / hybrid / rerank decisions.

#### `ai-eng-from-scratch-phase12-part1-vit-fusion-zh.md`
**Verdict:** restructure
- The content stops around 2022. §七 covers CLIP → ALIGN → BLIP → Flamingo and recommends "多輪多圖對話 → Flamingo 系列", but Flamingo weights were never released. There is nothing on SigLIP, LLaVA-style projector VLMs, Qwen-VL-class open models or native-multimodal frontier models, which is what a practitioner actually deploys in 2026. Rewrite §七 around "connector design: cross-attention vs projector vs native", and replace the Flamingo recommendation.
- Decision 6 claims "FAISS 增量更新需重建索引". FAISS supports `add()` on IVF/HNSW indexes; only deletion and rebalancing are awkward. Tighten the claim.
- The §九 business metrics (CTR 3.2%→6.4%, labelling cost $8,000/$1,200) have no source. Label them as an illustrative scenario.
- Check the overlap with Phase 4 Part 3 ("VLMs+3D" in the plan) and link to it instead of re-deriving ViT basics.

#### `ai-eng-from-scratch-phase12-part2-agents-computer-use-zh.md`
**Verdict:** restructure
- The description promises "SeeAct/Computer Use 系統設計", but SeeAct appears nowhere in the body. Either cover it or drop it.
- Every model reference is stale (GPT-4V, Claude 3.5 Sonnet, LLaVA-1.6 in the §四 accuracy table), and there is no reference to OSWorld / WebArena-style benchmarks. The 62%→93% completion claims need a benchmark anchor to mean anything.
- §五 is the best part: a concrete per-step latency and cost breakdown and a defined action whitelist. The "Delta Screenshot" optimisation is a genuinely non-obvious idea. Keep both.
- Phase 3 per-task VLM cost drops to $0.06 with no explanation of what changed (local model? caching?). Say what.

#### `ai-eng-from-scratch-phase13-part1-mcp-apis-zh.md`
**Verdict:** light edit
- The MCP section (§四) describes only the late-2024 surface (`tools/list`, `resources`, `prompts`). By Sept 2026 the spec has transports (stdio vs Streamable HTTP, since SSE was deprecated), an OAuth-based authorization spec, structured tool output and elicitation — verify against the current spec revision. For a post titled "AI 與真實世界的介面", authorization matters most.
- The skeleton uses the low-level `mcp.server.Server` API. The SDK's `FastMCP` decorator form is what readers will copy today.
- "正確工具選擇率從 73% 提升至 94%（內部測試，n=1000）" is presented as data. Soften it or cite.
- §五's tool authorization matrix and §七's idempotency section are good and specific. Point 19p2 back to them rather than re-teaching them.

#### `ai-eng-from-scratch-phase13-part2-orchestration-zh.md`
**Verdict:** restructure
- About 54% of the post is code, and much of it is boilerplate a library already provides: the exponential-backoff decorator (§7.2, `tenacity` does this), a Redis get/set cache (§6.2) and a generic circuit breaker (§7.4, also taught in 13p1 and 14p4). Cut these to the 5–10 non-obvious lines each and spend the space on *orchestration* decisions.
- The description promises a LangChain/LlamaIndex/**Haystack** comparison, but Haystack only appears in two table cells. Either add it or drop it from the description.
- Versions are stale: "LCEL 是 LangChain v0.2+ 的核心抽象", "LlamaIndex Workflow（v0.10+）". LangChain has since shipped 1.x with LangGraph as the agent runtime (verify). Pin versions and date them.
- LangGraph, the framework most relevant to "有狀態工作流程" (§六), is left entirely to 14p3. Add a forward link at minimum.

#### `ai-eng-from-scratch-phase14-part1-loop-memory-zh.md`
**Verdict:** light edit
- The four-layer memory diagram (§五) with concrete TTLs and stores is clear and actionable. The ReAct trace in §四 is a good worked example.
- The Reflexion numbers ("HotpotQA ReAct 58% → 71%") need a citation or a softer claim — verify against the paper.
- Decision 3 "Agent 框架" pre-empts 14p3. Replace it with a one-line pointer.
- The site has a 5-part Mem0 source-code series. Link it from §五 for readers who want a real implementation.
- Replace the box-art headings (dup anchors).

#### `ai-eng-from-scratch-phase14-part2-planning-zh.md`
**Verdict:** light edit
- The structure is good: the §六 failure taxonomy → replanner decision tree → pre/post-condition checks is a real, teachable progression.
- The biggest content gap for 2026 is reasoning models (o-series / extended-thinking-class). They internalise much of CoT/ToT planning and change the ReAct vs Plan-and-Execute tradeoff. Add a flip condition to Decisions 一 and 二: "with a reasoning model, explicit ToT rarely pays".
- The §九 completion-rate and failure-mode tables (e.g. "走入死路 38% vs 5%") are unsourced but read as benchmark results. Label them as illustrative, or cite Plan-and-Solve / LLMCompiler-style papers.
- The MCTS "rollout 用 LLM 模擬（便宜 10–100×）" claim needs a caveat: simulated rollouts are exactly where hallucinated success creeps in.

#### `ai-eng-from-scratch-phase14-part3-frameworks-zh.md`
**Verdict:** restructure
- The framework landscape is out of date. Microsoft merged AutoGen and Semantic Kernel into the Microsoft Agent Framework (announced Oct 2025 — verify current status), so §三 and §六 compare two predecessors of one product. The AutoGen diagram is the 0.2 `UserProxyAgent`/`GroupChat` model while the text talks about 0.4. The post also omits the vendor SDKs most teams now evaluate (OpenAI Agents SDK, Claude Agent SDK) and Pydantic AI.
- The §九 claim that a custom framework's "overhead < 5ms vs LangGraph 20–50ms…在 > 1K QPS 節省成本可達 30–50%" doesn't hold up: framework overhead is noise next to multi-second LLM calls. Remove it or reframe it as operational cost.
- There are zero Markdown tables; every comparison is ASCII in a code fence. Convert them for mobile readability.
- The duplicate `### 核心架構` heading appears under each framework. Make them unique (`### AutoGen 核心架構`).

#### `ai-eng-from-scratch-phase14-part4-production-zh.md`
**Verdict:** light edit
- The numbers contradict each other inside §九: the table says "無限迴圈事件 12 次（平均每次損失 $8）", and the cost breakdown directly below says "$4,500（12 次 × $375/次）". Pick one.
- The §四 fallback chain is wrong on cost and quality. It ends with "全域預算 > 95% → gpt-3.5-turbo（成本降幅 99.96%）", but gpt-3.5-turbo is both *more expensive* than gpt-4o-mini and weaker, so stepping from 4o-mini down to 3.5 saves nothing. Replace it with a current small model or a cached/static tier.
- "Prompt Injection 攔截率 99.2%" and "新版本上線風險：零風險" are overclaims. Soften them.
- Otherwise this is one of the best posts in the batch. The Redis `INCRBYFLOAT` race-condition example (§四) and the Shadow → Canary flip condition are exactly the non-obvious material this series should have.

#### `ai-eng-from-scratch-phase15-part1-long-horizon-zh.md`
**Verdict:** light edit
- The opening quote says "五十步後完成率可能跌到 5%", while §1.1 computes 0.98^50 ≈ 36%. Align them.
- §九 conflates two failure types. Checkpointing fixes *crash* recovery, not the per-step *logic* error rate, yet the table credits Checkpoint with lifting 50-step completion from 36% to 94%. Split the gain into "restart without rework" (checkpoint) vs "per-step accuracy" (verification / drift detection).
- The §七 drift-detection section is the most original material. Expand it with a concrete example of what a drift signal looks like in a trace.
- Link back to 14p1's memory layers instead of re-deriving "記憶的四個層次" in §3.1.

#### `ai-eng-from-scratch-phase15-part2-self-improvement-safety-zh.md`
**Verdict:** restructure
- The title and body don't match. The post is titled "自我改進", but the `面試情境` and half the body (§六–§七) are prompt-injection and sandbox defence, which 18p1 covers again. Refocus this post on self-improvement loops and their failure modes (reward hacking, eval contamination, drift), and move the defence stack to 18p1 with a link.
- It contains a factual error: the §1.2 table lists Jailbreak as "OWASP LLM Top 10 第一位". LLM01 is **Prompt Injection** (OWASP files jailbreaking under it). "生產事故中佔 34%" has no source.
- "每次推論都是一次微小的「學習」" is misleading: Self-Refine and constitutional prompting do not update weights. Distinguish inference-time refinement from training-time RLVR explicitly. §5.2 "RLVR 在生產 Agent 中的應用" blurs the two.
- The "內部 red-team 數據" table in §6.3 reads as fabricated. Label it as an illustrative scenario or cite published jailbreak benchmarks.

#### `ai-eng-from-scratch-phase16-part1-coordination-zh.md`
**Verdict:** light edit
- The §7.2 code is not valid Python: `("sufficient", weight=3.0)` puts a keyword argument inside a tuple. Use `("sufficient", 3.0)`.
- The phase scale mixes units: Phase 2 is "10–200 個並發任務" and Phase 3 is "200K–1M+ 任務/天". Use one unit.
- Inter-agent communication (§四) never mentions the A2A (Agent2Agent) protocol, the 2025–26 standard for exactly this problem, or how it relates to MCP from 13p1. Add a paragraph and a decision row.
- The §七 voting/veto material overlaps 16p2 §六. Keep the veto and safety-agent angle here and link to 16p2 for aggregation strategies.

#### `ai-eng-from-scratch-phase16-part2-emergence-collective-zh.md`
**Verdict:** light edit
- The MoA figures need checking. The post cites "AlpacaEval 2.0: MoA 57.6% vs GPT-4 Turbo 50%", while the paper's headline is 65.1% LC win rate for open-source-only MoA — verify and cite.
- The scenario's own target is never met. The `面試情境` demands 99.5% accuracy for medical diagnosis, and §九 tops out at 98.4% without comment. Say so explicitly, because that gap is the interesting lesson. "以下數字來自醫療診斷輔助系統的 A/B 測試（10K 查詢樣本）" is an unsupported real-world claim in a medical context. Mark it as hypothetical.
- The §九 cost column is inconsistent: 3-agent majority vote ($0.105) costs more than 7-call MoA ($0.089).
- The ACO "prompt optimizer" (§三) is really a UCB bandit dressed in pheromone vocabulary, and the "MMLU +4.3%" figure is unsourced. Either call it a bandit or cut it. Add the counter-evidence that debate often fails to beat self-consistency at equal compute, which is the honest flip condition.

#### `ai-eng-from-scratch-phase17-part1-serving-zh.md`
**Verdict:** light edit
- It re-teaches vLLM/PagedAttention (§三) with different numbers from 11p1 and never links to it. Replace the paragraph with a pointer and keep this post on the platform layer (routing, autoscaling, MIG, multi-tenancy).
- The framework choice is stale: TorchServe has been in limited-maintenance mode since 2025 (verify), so recommending it for "純 PyTorch 快速上線" needs a caveat. The 2026 LLM-serving platform layer (KServe, NVIDIA Dynamo, llm-d, KV-cache-aware routing via the Gateway API Inference Extension) is absent, and that is precisely what §四's "Least Pending Tokens" load balancing is reaching for.
- §九 "每日最大 QPS 58" mixes units (5M req/day ≈ 58 average QPS). Rename the row.
- The GPU sharing section (§六 MIG/MPS/time-slicing) is concrete and useful. Keep it.

#### `ai-eng-from-scratch-phase17-part2-observability-zh.md`
**Verdict:** light edit
- The code imports `opentelemetry.semconv.ai.SpanAttributes`. That is the third-party OpenLLMetry package, not the official OpenTelemetry GenAI semantic conventions (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`). Use the official names, since this post is the series' reference on the topic.
- The trace tree nests `tool_call:search_web` *inside* `llm_completion`. Tool execution happens after the completion returns, so it should be a sibling or child of the agent step, not of the model call.
- The decision tables compare generic infrastructure (Grafana vs Datadog, Tempo vs Zipkin) but not the LLM-native choice readers actually face: Langfuse / Phoenix / LangSmith vs rolling your own on OTel.
- The §三 "p99 正常但品質差" diagnosis chain is a good symptom → diagnosis example. The model names (`claude-3-5-sonnet`, `claude-3-haiku`) are stale.

#### `ai-eng-from-scratch-phase17-part3-cost-scale-zh.md`
**Verdict:** light edit
- There is a technical error in §3.2: "Retrieved Chunks 2,000 tok │ 可快取". Retrieved chunks change per query, so provider prompt caching can't cover them; the system prompt and stable prefix are what cache. This undermines the §3.3 optimisation math.
- The scenario and the worked example disagree. The `面試情境` is $47K/month, and §3.2 computes $2.4M/month at 10 QPS. Pick one baseline and carry it through to §九.
- The price tiers ($15/$75 flagship, "2025 年市場價格") are stale for Sept 2026. Date the table and add a sentence on how falling prices change the cache-vs-route calculus.
- The "七之二" section is a numbering workaround. Merge it into §七 or §九.

#### `ai-eng-from-scratch-phase18-part1-technical-safety-zh.md`
**Verdict:** light edit
- The audience is mismatched. Much of §六 (RLHF vs DPO vs CAI training) and §七 (SAE features, activation patching, "在 embedding 層訓練探測分類器") assumes access to weights and activations, which API-model users do not have. Add an explicit "if you use a hosted model, your levers are…" split. The §七 "今日可部署" table is a good start.
- The opening quote sits inside §一 rather than before it, and the `面試情境` block has the explicit "這道題考的不是…" interview voice.
- It overlaps 15p2 on the attack taxonomy and defence stack. Make this the canonical home and have 15p2 link here.
- The Reward Hacking / Goodhart section (§三) is well pitched for engineers. Keep it.

#### `ai-eng-from-scratch-phase18-part2-governance-zh.md`
**Verdict:** light edit
- It contains factual errors on the EU AI Act. Prohibited practices applied from **2 Feb 2025**, not "2024/2/2". The maximum fine is **€35M or 7%**, not "€30M 或全球營收 6%" (that was a draft figure). The 2 Aug 2026 high-risk date needs a note that the Digital Omnibus proposal pushed Annex III obligations back — verify the current status. GPAI-model obligations (Aug 2025), the most relevant rules for LLM builders, are absent.
- A placeholder was left in the §九 table: "EU 市場准入：$X", "$X + 20%".
- Other claims are dated or wrong: "英國、加拿大相繼推出對等框架" (Canada's AIDA died; the UK has no AI Act), and "NIST AI RMF 已成為美國聯邦採購的事實標準" — verify both against 2026 policy.
- The bias, DP and SHAP material is solid but is classical-ML credit scoring. Add an LLM-specific governance note (Article 50 transparency, content provenance) so it connects to the rest of the curriculum.

#### `ai-eng-from-scratch-phase19-part1-capstone-rag-system-zh.md`
**Verdict:** light edit
- A technical mismatch in §五: the corpus is mostly Traditional Chinese, but the reranker is `ms-marco-MiniLM-L-6-v2`, an English-only model. Use a multilingual reranker (bge-reranker-v2-m3-class) and note why.
- The latency budget doesn't add up: 8 + 45 + 120 + 1,800 ms ≈ 2.0s, then "+ 網路 ≈ 2.9s". HyDE is listed in pre-processing but its extra LLM call is not in the budget at all.
- "我在 2025 年底實際交付了一個類似規模的系統" is an unverifiable first-person production claim. Keep it only if true and give some detail; otherwise frame it as a reference design.
- As a capstone it should *tie back* to earlier posts. It cites no earlier phase: no link to 11p2 (RAG/evals), 13p2 (orchestration), 17p2/17p3 (observability, cost) or 18p2 (the L1/L2/L3 security tiers it lists but never designs). Add a "本 Capstone 用到的前置章節" box and cut the decision tables that duplicate 11p2.

#### `ai-eng-from-scratch-phase19-part2-capstone-agent-product-zh.md`
**Verdict:** light edit
- The timeline is impossible: "上線日期：2026-03-01…90 天後（2026-05-31）", yet 失敗與學習 問題 1 happens "雙 11 前三天" (November). Fix the dates or the incident.
- It is presented as a real engagement ("真實電商平台改造案", "上線後 90 天的真實指標", "撐過了 100K sessions/day") with a 30K baseline and 80K peak, and the numbers don't reconcile. Frame it as a reference design unless it is real.
- The three incident post-mortems (stale KB before a sale, silent DLQ failure, tool schema drift → hallucinated tracking) are the most valuable content in the batch. Keep them and lead with them.
- As a capstone it never links 13p1 (tool auth/idempotency), 14p1 (memory), 14p4 (budget/guardrails) or 17p2 (tracing). Each §三–§七 should open with a one-line back-reference. The refund example also repeats 14p1's ReAct trace nearly verbatim.

#### `ai-eng-from-scratch-phase19-part3-capstone-multimodal-app-zh.md`
**Verdict:** restructure
- **The series summary describes a different curriculum.** The §七 knowledge map and skills matrix list Phase 1 環境設置, 2 Python, 3 數學, 4 ML, 5 深度學習, 10 API 設計, 12 評估, 13 單一 Agent, 14 多 Agent, 15 Prompt Engineering, 16 監控, and 19 Part 1 視覺理解 / Part 2 語音整合. The real series is 1 Math, 2 ML, 3 DL, 4 CV, 5 NLP, 6 Speech, 7 Transformers, 8 GenAI, 9 RL, 10 LLMs from scratch, 11 inference+RAG, 12 multimodal, 13 MCP/orchestration, 14 agents, 15 autonomous, 16 multi-agent, 17 infra, 18 safety, 19 RAG / agent / multimodal capstones. §一 repeats the errors ("RAG（Phase 11）、Agent（Phase 13）…視覺理解（Phase 19 Part 1–2）"). Rebuild §七 from the actual filenames, with a link per phase. This is the capstone's main job and it currently fails it.
- The end nav is wrong: "19 個 Phase、63 篇文章" (the real count is about 44), the previous link points at a nonexistent `phase19-part2-voice-interface`, the "回到 Phase 1" link goes to a nonexistent `phase1-environment-setup` (the real one is `phase1-part1-linear-algebra`), and the series-list tag is dead.
- The voice section (§四) models only an ASR → LLM → TTS cascade. For a 2026 "system design" capstone, add the speech-to-speech realtime-model alternative as a flip condition, since it is the main lever on the 2.5s budget the section worries about.
- The opening and several tables still anchor on GPT-4V. The §五 modality-routing and §六 latency-budget sections are good and specific. Keep them.

### Top 5 highest-impact fixes in this batch
1. **Rebuild series navigation in one scripted pass.** Add a series tag (or landing page) to all 44 posts, regenerate every `十、系列導航` block from real filenames with root-absolute links, and fix the anchor text. Today 21/22 posts have dead prev/next links and the "完整目錄" link 404s.
2. **Rewrite 19p3 §七 (and §一) so the capstone summary matches the real 19-phase curriculum**, with a link per phase. Also add "前置章節" back-links to 19p1 and 19p2 so the capstones actually tie the series together.
3. **Strip the interview framing, not just the tag.** Convert all 22 `面試情境` blocks to project briefs and delete the inline "回答面試題 / 準備面試 / 這道題考的" lines (11p1, 11p2, 18p1).
4. **Correct the factual and internal-consistency errors that undermine trust**: EU AI Act dates, fines and the `$X` placeholder (18p2); OWASP #1 (15p2); cacheable retrieved chunks (17p3); the gpt-3.5 fallback and the $8 vs $375 loop cost (14p4); the March-to-May launch that contains 雙 11 (19p2); the English-only reranker on a Chinese corpus (19p1); the invalid Python tuple (16p1); the embedding crossover math (11p2).
5. **Refresh the 2024-era technology snapshot where it is load-bearing**: the agent frameworks (14p3: AutoGen and SK merged into the Microsoft Agent Framework, plus vendor agent SDKs), MCP transports and auth (13p1), the modern VLM lineage (12p1), the serving platform layer and TorchServe status (17p1), OTel GenAI semconv (17p2), and dated price and model tables everywhere. Merge the duplicate topic pairs (11p1↔17p1, 11p2↔19p1, 15p2↔18p1) into "canonical post + link".
