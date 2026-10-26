## fde-core-concept 1–25 + ai-fde-essential-guide 1–5 — 30 posts

### Series-level observations
- **ai-fde-essential-guide 3/4/5 publish leaked agent tool-call markup.** Each ends with a raw `<function_calls><invoke name="TodoWrite">…` block (part3 L1391, part4 L1850, part5 L2056) that shows the model's own to-do list, with \u-escaped Chinese. It is visible on the live site. Fix it before anything else. (The other repo files that match `TodoWrite`, claude-code-*-zh.md, only mention the tool by name. They are not leaks.)
- **ai-fde-essential-guide 3–5 are code dumps, not guides.** Parts 3/4/5 have 45/41/63 non-code prose lines against 69/101/72 `class`/`def` definitions. Each `##` section is a one-line intro followed by a 150–400-line class that nobody explains and that is full of `print()` stubs (`_trigger_retraining` → `print(...)`). Part 5 models *customer collaboration* as Python: keyword-weighted requirement scoring and a requirements doc stored as a string template. This is a human skill that code cannot teach. Parts 1–2 are thinner (a generic Python/TensorFlow/BERT survey, gpt-4 examples). The `cheatsheet` tag is misleading on all five. Nothing in this series is newer or better than fde-core-concept 21–25 or fde-interview-guide 26–29/42.
- **The core-concept cross-references were written against a different 25-topic plan that was never published.** The broken `fde-interview-core-topic-*` nav slugs are already known. The nav *labels* and the prose in 「與其他核心主題的關聯」 are also wrong in about 11 posts:
  - Posts with wrong references: 1, 2, 4, 5, 6, 8, 9, 11, 16, 19, 20.
  - Examples of topics that do not exist:
    - core-4 cites "向量資料庫選型（Part 5）" and "Reranking（Part 6）". Reranking is really Part 5.
    - core-20 cites "Hybrid Search（Part 18）" and "LLM-as-Judge（Part 17）". The real posts are Part 4 and Part 19.
    - core-11 cites "Part 7 LLM Serving", "Part 9 資料庫選型", "Part 14 Observability" and "Part 19 Cost Engineering".
    - core-6 cites "RAG 系統安全（Part 9）", "Agent 工具呼叫（Part 11）" and "LLM Observability（Part 14）".
  - Posts whose references are correct: 10, 12–15, 17, 18, 21–24. They can serve as the template for fixing the rest.
- **The series is orphaned.** No file in `content/` links to `/posts/fde-core-concept-*`. With the nav broken as well, each post can only be reached from tag/category pages. The series also goes by four names: title "FDE core topic -", tag `fde-core-topic`, filename `fde-core-concept`, nav slug `fde-interview-core-topic`. Pick one.
- **Almost every core-concept topic has a fde-interview-guide counterpart, usually a longer one.**
  - Matching pairs (core → guide):
    - 1 → 10, 44
    - 2 → 14, 18
    - 3 → 16, 25, 48
    - 4, 5 → 5
    - 6 → 13, 45
    - 7 → 20, 45 (guide-45's description lists the same three defenses: dual-model, Cloud Run sandbox, Pydantic)
    - 8 → 40
    - 9 → 30
    - 10 → 46
    - 11 → 21, 43
    - 12 → 23
    - 13 → 48
    - 14 → 22, 52
    - 15 → 49
    - 16, 17 → 51
    - 18 → 24, 47
    - 19 → 50, 12
    - 20 → 6, 36
    - 21 → 42
    - 22 → 41, 11
    - 23, 25 → 26
    - 24 → 27, 29
  - Guide parts 40–52 run 600–830 lines against about 440 here.
  - The core-concept format (核心定義 bolded up front → 弱答/強答 → three layers → traps → one Killer Phrase) is a genuinely distinct asset: a condensed recall card. Right now it is presented as a parallel deep dive.
  - Recommendation:
    - Reposition the series as "30-second recall cards".
    - Link each card to its guide counterpart at the top.
    - Retire or merge only where the core post is a strict subset (6, possibly 7).
- **Template drift from the house standard.** The series uses 「三個實作層次」 (Minimal/Production/Enterprise) instead of 「三個演進階段」 (POC/MVP/Scale). That is acceptable for a condensed series if the choice is documented in CLAUDE.md. Other drift: about half the posts have no 為什麼選 X 不選 Y section; heading numbering is broken in 12 (「四-B」), 24 (skips 七) and 8 (十 sits *after* the Killer Phrase). The opening 4-line quote appears only in 3.
- **Trust.** Several posts put invented production numbers in the candidate's mouth, framed as "實測" (measured) or "我們觀察到" (we observed):
  - core-3 "12 → 4 次工具呼叫"
  - core-13 "99.97%"
  - core-16 "實測效能對比"
  - core-22 "生產歸因數據 80% quota"
  - core-6 "攔截率 94%", "100%"

  Coaching candidates to present unsourced numbers as their own measurements is risky in a real interview. Relabel them as illustrative ("例如", "典型量級") or cite a source.
- **Categories.** All 25 core-concept posts are `["all","engineering"]`. Suggested changes:
  - The RAG, LLM and security topics (1–8, 15–20) belong in `ai`.
  - 9 and 10 fit `architecture` or `infrastructure`.
  - The consulting posts 21, 23, 24 and 25 belong in `business`.

### Per-post

#### `ai-fde-essential-guide-part1-zh.md`
**Verdict:** consider retiring
- The content is generic and could appear in any intro course: generators/decorators, a list of pandas/numpy, the TensorFlow/Keras/PyTorch APIs, and the BERT/GPT/T5 families (L127–150). It has no FDE angle, no numbers and nothing from 2025–26 (no mention of agents, eval or inference servers).
- The test snippet uses `time` without importing it and calls `create_test_model()`, which is never defined. Code that is meant to be copied does not run.
- If kept, cut to a one-screen skills map that links into fde-interview-guide parts 3/8/9, which cover the same fundamentals in depth.

#### `ai-fde-essential-guide-part2-zh.md`
**Verdict:** rewrite/merge
- The MCP section (L388–540) hand-rolls a dict-dispatch "MCP server" with no JSON-RPC, no transport and no SDK. It misrepresents the protocol. Replace it with the official `mcp` Python SDK / FastMCP (about 20 lines) or link to fde-interview-guide part 17.
- The "security framework" example (L740s) blocks commands with a substring blacklist (`"del"` also matches "model", and plain `rm` passes). The post teaches an anti-pattern as a security control. Delete it or replace it with an allowlist.
- `ChatOpenAI(model="gpt-4")` (L242) is stale. The CrewAI and LangGraph blocks are full orchestrator classes with no explanation of *when* to choose CrewAI or LangGraph. Core-concept 3 covers the LangGraph half better.

#### `ai-fde-essential-guide-part3-zh.md`
**Verdict:** consider retiring
- **Hotfix now:** delete the leaked `<function_calls>`/TodoWrite block at L1391–end.
- The post is 1,383 lines of classes (GCP, AWS and Azure deployers, RBAC, encryption, a vector DB wrapper, a chunker, ETL) with about 45 lines of prose. It never explains why any design choice was made. The same topics appear with reasoning in core-concept 8/9/10 and guide 30/37/40/46.
- The heading 「Google Cloud Platform (GCP) 深度整合」 (L19) is the only "Google" mention. The series is not tagged Interview, so the rule does not strictly apply, but it sits next to interview content.
- If you want to salvage it, keep one ~80-line prose section, "三雲部署的差異決策表" (a comparison of deploying on the three clouds), and drop the rest of the code.

#### `ai-fde-essential-guide-part4-zh.md`
**Verdict:** consider retiring
- **Hotfix now:** delete the leaked TodoWrite block (L1850–end).
- About 1,840 lines, 101 functions/classes and 41 prose lines. The "智能故障診斷與自動恢復" section (troubleshooting and auto-recovery, L816–1446) is 630 lines of anomaly-detector classes with no thresholds, no symptom→diagnosis chain and no traces. Core-concept 22 and guide 35/41 do this job properly.
- `@observability.track_ai_request("gpt-4", ...)` (L619) is stale. The cost section's budget loop (`await asyncio.sleep(3600)`) is a toy, not production guidance.

#### `ai-fde-essential-guide-part5-zh.md`
**Verdict:** rewrite/merge
- **Hotfix now:** delete the leaked TodoWrite block (L2056–end).
- The topic (discovery, stakeholder communication, change management, ROI) is the most valuable in the series, but it is written as about 2,000 lines of Python. Examples: requirement priority as `keyword weight - len(dependencies)*0.1`, and a requirements spec as a string template (L217–245, whose `##` headings the audit counted as real headings).
- Rewrite it as ~400 lines of prose with tables, or retire it and point readers to core-concept 21/23/24/25 and guide 27/29/42, which already cover this ground well.
- The closing "series recap" repeats the whole table of contents. Replace it with real links.

#### `fde-core-concept-1-context-management-zh.md`
**Verdict:** light edit
- The model facts are stale for Sept 2026: "Claude Sonnet 4: 200K；Gemini 1.5 Pro: 1M；GPT-4o: 128K" (L35). Update them or phrase them as "例如 128K 視窗".
- Context overflow is repeatedly called "OOM" (L60, 「對話 OOM 發生率」). It is a context-length error, not an out-of-memory error, and an interviewer will notice.
- The strong answer (L27) says the compression ratio is 13:1 (6K→500), while the Killer Phrase (L461) says 32:1 (16K→500). Pick one.
- Cross-refs: "RAG 架構設計（本系列 Part 2）" is wrong (Part 2 is Memory), and the nav label "後一篇：RAG 架構設計與向量檢索策略" is wrong too. Add a link to guide part 10/44.

#### `fde-core-concept-2-memory-architecture-zh.md`
**Verdict:** restructure
- At 281 lines, this is the thinnest technical post, and it is fully covered by guide 14 and 18 (三層記憶體). It needs either a distinct angle (such as forgetting/consolidation evaluation) or a merge into guide 14 as its recall card.
- It has no 為什麼選 X 不選 Y. Obvious candidates are Redis vs Firestore for episodic memory, Vector Search vs pgvector for semantic memory, and nightly vs streaming consolidation.
- "Gemini 1.5 Pro 為 1M tokens" (L21) and `text-embedding-004` are stale; the latter was also superseded by `-005` in core-4. Nav: "後一篇：Tool Use & Function Calling" points to a post that does not exist.

#### `fde-core-concept-3-state-machine-dag-zh.md`
**Verdict:** light edit
- This is one of the best in the batch: the opening quote, a concrete 面試情境, the ReAct vs DAG decision matrix and a symptom→root-cause chain (L362).
- 「在生產環境中我們觀察到 unconstrained ReAct 平均每個 query 觸發 12 次工具呼叫」 in the Killer Phrase is an invented number framed as a personal observation. Reword it as illustrative.
- "ADK 2.0" in the description: verify the version name. The trailing series blurb says 「本系列共 25 篇」 but has no index link. Link to an index or tag page.

#### `fde-core-concept-4-hybrid-search-rrf-zh.md`
**Verdict:** light edit
- The headline numbers (dense 72% / sparse 68% / hybrid 84% Recall@10) appear in the lead, the body and the Killer Phrase with no dataset or source. Say they come from a BEIR-style benchmark, or label them illustrative.
- Cross-refs are wrong: "Embedding 模型選型（fde-core-topics Part 3）", "向量資料庫選型（Part 5）" and "Reranking（Part 6）". Reranking is Part 5, and there is no embedding or vector-DB post. Guide part 5 (混合搜尋) is the natural link.
- It has no 為什麼選 X 不選 Y table, although the RRF vs weighted linear fusion and SPLADE vs BM25 decisions are already discussed in prose. Turning them into a table is an easy add.

#### `fde-core-concept-5-reranking-cross-encoder-zh.md`
**Verdict:** light edit
- It is short (294 lines) but focused. The skip condition (<200ms SLA → ColBERT) is the valuable bit.
- 「幻覺率降低 40%」 appears in the description and the Killer Phrase without a source. Soften it or cite one.
- All three core cross-refs point to nonexistent topics ("Part 3 向量資料庫與 HNSW", "Part 4 RAG Pipeline", "Part 6 Embedding"). Point them at core-4 (hybrid), core-15 (vector drift) and core-20 (triad).
- Verify the Vertex AI Ranking API model names and prices as of 2026.

#### `fde-core-concept-6-prompt-injection-jailbreak-zh.md`
**Verdict:** rewrite/merge
- At 204 lines, it is the thinnest post and a subset of guide 13 (five-layer defense), guide 45 and core-7. Merge its attack taxonomy table into core-7 and retire it, or cut it to a pure recall card that links to guide 13.
- Overclaims: 「XML 隔離…消除分隔符混淆攻擊 100%」 (L~88) and 「攔截率：已知注入模式 94%」. No structural defense is 100%. Say "大幅降低".
- 「DLP 必須掃描 LLM output，而不是 input」 contradicts core-8, which scans before embedding. Say "both".
- Every cross-ref (Part 9/11/14) points to a topic that does not exist. Also, "Gemini Guard" is not a product name (verify; perhaps Model Armor was meant).

#### `fde-core-concept-7-indirect-prompt-injection-zh.md`
**Verdict:** light edit
- The content is strong: the Unicode byte-level explanation, the X-vs-Y table and the symptom→diagnosis chain. But it is nearly the same design as guide 45 (dual-model privilege separation, Cloud Run without VPC, Pydantic `extra=forbid`). Diff the two posts and state at the top which one is the deep dive.
- 「從架構層面消滅 100% 網路可達攻擊面」 and 「覆蓋 98% 的隱形字元技巧」 are unsourced percentages. The section 「面試常見追問與答法」 (L415) is close to the dropped 面試答題要點 (model answer) format. Keep it short.

#### `fde-core-concept-8-pii-deidentification-zh.md`
**Verdict:** light edit
- A substantive post: the de-identification spectrum, FPE (format-preserving encryption) mechanics and the synthetic-data boundary.
- Move 「十、症狀診斷」 before 「九、面試一句話」 so the Killer Phrase closes the post, as it does everywhere else.
- Cross-refs: "向量資料庫設計（Part 6）", "RAG 管線（Part 5）", "資料治理（Part 11）" and "LLM 微調（Part 15）" do not exist. Point them at core-10 (CMEK vault), core-18 (privacy routing), core-9 and guide 40.
- The Taiwan scenario (0912 phone number, 身分證) is a nice touch. Keep it.

#### `fde-core-concept-9-data-residence-sovereign-ai-zh.md`
**Verdict:** light edit
- Strong: the translation from regulation to technical controls, and the Batch-Prediction-region and VPC-SC dry-run traps show real depth.
- Cross-refs "IAM（Part 5）", "LLM 推論（Part 6）", "多租戶（Part 11）" and "安全事件（Part 15）" are all wrong. Point them at core-10, core-8, core-12 and core-18.
- Verify 「VPC-SC 執行延遲 < 5ms」 and the current name of the GDC (Google Distributed Cloud) product. Writing it as "GDC" alone is safer under the no-Google rule.

#### `fde-core-concept-10-cmek-byok-envelope-zh.md`
**Verdict:** light edit
- A strong, well-cross-referenced post: four X-vs-Y decisions (GMEK/CMEK/BYOK, GCM vs CBC, Interconnect vs VPN, RSA vs AES KEK) and a symptom chain.
- It overlaps heavily with guide 46 (BYOK/CMEK). Add a top link and trim whatever guide 46 already covers.
- 「即使面對法院命令也無法交出金鑰」 is a legal claim. Soften it to "平台無技術能力單方解密".

#### `fde-core-concept-11-async-event-driven-pipeline-zh.md`
**Verdict:** light edit
- The description's 「改善幅度達 250 倍」 is marketing. Say what the ratio is of (connections held? throughput?).
- It overlaps internally with 12 (Pub/Sub flow control, KEDA) and 13 (「訊息重複處理的冪等性設計」, L220). Trim the idempotency section to three lines and link to core-13, and move the KEDA config to one place.
- Cross-refs Part 7/9/14/19 do not exist. Point them at core-12, 13, 14 and 22.

#### `fde-core-concept-12-backpressure-fair-share-zh.md`
**Verdict:** light edit
- The heading 「四-B、系統效應」 breaks the numbering. Renumber to 五 and shift the rest.
- The post leans on its 2.x subsections (ten of them, L33–318) before the layers. Section 2.9 is the only X-vs-Y. Add two more: Redis vs Memorystore quotas vs API Gateway quotas, and WFQ vs strict priority.
- It overlaps guide 23 (fair-share, token budget). Link it. The Redis Lua token bucket is the non-obvious code here and earns its place.

#### `fde-core-concept-13-idempotency-state-recovery-zh.md`
**Verdict:** light edit
- **Factual error:** it treats "Firestore default mode" as eventually consistent (L23, L126, L418) and says `consistency=STRONG` is 「僅 Datastore 模式支援」. Firestore Native mode is strongly consistent for document reads and queries. The argument for Spanner has to rest on something else (cross-row CAS/transactions at scale, external consistency across regions), not on Firestore being stale.
- 「實測…99.97% 的 Pod 失敗可被無重複副作用地恢復」 (the Killer Phrase) is invented. Also, "exactly-once Pub/Sub（Kafka 語意）" is muddled: Pub/Sub now has its own exactly-once delivery option. Verify and reword.
- It has no 為什麼選 X 不選 Y. Obvious candidates are Spanner vs Firestore vs Postgres advisory locks, and a checkpoint-per-step vs an outbox pattern.

#### `fde-core-concept-14-speculative-tool-fanout-zh.md`
**Verdict:** light edit (but fix the maths first; it is the post's headline)
- The latency model is internally inconsistent:
  - An exponential distribution cannot have P50=2s and P99=3s. For an exponential, P99 ≈ 6.6× P50.
  - A 1.5s hard deadline is *below* the stated P50=2s, so it would cancel more than half the calls, not "2 of 15 → 13/15" (L64–71).
  - Fix: pick P50≈800ms and P99≈3s, which is realistic for tool APIs.
- The headline 「30 秒壓到 1.5 秒（20 倍）」 compares against *sequential* calls. The honest win of hedging plus a deadline over `asyncio.gather` is 3s → 1.5s (2×). Say that. It is still a good story.
- It overlaps guide 22 and 52 (hedged requests appear in 52). Link them. The `asyncio.wait` vs `gather` point (2.3) is the non-obvious code worth keeping.

#### `fde-core-concept-15-vector-drift-blue-green-zh.md`
**Verdict:** light edit
- A good end-to-end walkthrough (L219) and monitoring section. 「Blue-Green 重建…是兼顧零停機與高精度的唯一根治手段」 (L13) overclaims. Some engines do online graph repair or periodic compaction, so say "最穩健".
- Unsourced recall numbers ("94%", "78%"): cite HNSW-deletion literature or label them illustrative.
- It is close to guide 49 (vector drift pipeline). Decide which is canonical.

#### `fde-core-concept-16-ttft-throughput-optimization-zh.md`
**Verdict:** light edit
- The 「實測效能對比（LLaMA-2 70B，A100 80GB）」 table (L~118) cannot be a measurement: FP32 70B needs 280 GB and FP16 needs 140 GB, which do not fit on one A100 80GB. Relabel it as illustrative.
- It is stale for 2026. Everything is LLaMA-2/A100 and INT8/INT4, with nothing on FP8 on H100/B200, prefix caching, prefill/decode disaggregation, SGLang/TensorRT-LLM or EAGLE-style speculative decoding. Add a short "2026 現況" paragraph.
- Cross-refs "KV Cache（Core Topic 15）" and "GPU 成本（Core Topic 17）" are wrong. Point them at core-17 and guide 51. It has no 為什麼選 X 不選 Y (vLLM vs TGI vs managed endpoint; AWQ vs GPTQ).

#### `fde-core-concept-17-context-caching-eviction-zh.md`
**Verdict:** restructure
- The Vertex context-caching facts are 2024-era:
  - The 32,768-token minimum (L105–128) applied to Gemini 1.5. Gemini 2.x lowered it to the low thousands and added **implicit caching** (automatic, with no storage fee), which undercuts the post's premise that "idle cache = cost bomb". Re-verify storage price, minimums and TTL behavior.
  - The rationale 「TPU HBM 以 32K token 為基本分配單位」 looks fabricated. Remove it.
- The post uses `google.generativeai.count_tokens()` (L126), an SDK that has been superseded by `google-genai`. It is also a literal "google" string in an interview post.
- Its L1/L2/L3 tiering duplicates core-1/core-2 and guide 51 (KV cache eviction). Once implicit caching is covered, the distinct value is the "explicit cache break-even" calculation (L101). Rebuild the post around that.

#### `fde-core-concept-18-semantic-model-routing-zh.md`
**Verdict:** light edit
- **Factual error** in the cross-refs: 「客戶管理金鑰確保雲端模型無法在 Anthropic/其他廠商端解密推理內容」. A hosted model must see plaintext to run inference, so CMEK protects data at rest, not in inference. Fix it. It is the kind of line an interviewer pounces on.
- The TCP RST vs FIN detail (L126–134, "節省 1–3 ms") is noise. The real mechanism is vLLM `abort()`. Cut it to one line.
- It overlaps guide 24 and 47 (edge routing with entropy). Verify that logprobs are available on the cloud-side models named, since several managed APIs restrict `top_logprobs`.

#### `fde-core-concept-19-llm-judge-bias-mitigation-zh.md`
**Verdict:** light edit
- A statistics slip: L21 says 「50K 樣本、95% CI、±14% 誤差範圍」. ±14% is the margin for about 50 samples per cell (L227), not 50K samples. Fix the sentence, because the post's credibility rests on the statistics.
- "GPT-4" as the judge and "Llama3" are stale model references. Cross-refs "MLOps（Part 16）" and "Context Caching（Part 17）" are half wrong (16 is TTFT). It has no X-vs-Y section (pairwise vs pointwise, single judge vs panel).
- It overlaps guide 50 and 12. Link them.

#### `fde-core-concept-20-rag-triad-metrics-zh.md`
**Verdict:** restructure
- It is thin (315 lines) and already covered by guide 6 (RAG 評估指標) and 36 (eval pipeline). The distinct angle promised in the title, "可觀測性追蹤" via OpenTelemetry/Grafana, gets only a short Layer 2. Expand that part (span attribute schema, alert thresholds, sampling cost), or merge into guide 36.
- Every cross-ref is wrong. Hybrid is Part 4 (not 18) and Judge is Part 19 (not 17); OTel (Part 12) and SLO (Part 15) do not exist. The benchmark table (0.68→0.84 and so on) is unsourced.
- It has no X-vs-Y: NLI vs LLM-judge for groundedness, and RAGAS vs TruLens vs in-house.

#### `fde-core-concept-21-discovery-to-constraints-zh.md`
**Verdict:** light edit
- The content is good, and the constraint→architecture mapping is the useful part. "SCALE 框架" is presented as if it were an established framework. Say it is the author's own mnemonic.
- 「每個 SCALE 問題削減 60–80% 的解空間」 and 「節省 5 週」 are unsourced. It overlaps guide 42 (Discovery 框架) and should link it.
- Category: `business` fits better than `engineering`.

#### `fde-core-concept-22-structured-troubleshooting-zh.md`
**Verdict:** light edit
- The 「根因分布統計（生產歸因數據）」 table (L160–175: 80% quota, 15% third-party, 4% loops, 1% gateway), "依據對多個生產 AI Agent 系統的故障後分析", is unsourced and is then recommended as the candidate's first move. Reframe it as a heuristic ordering, not data.
- It overlaps guide 41 (structured diagnostic framework) and guide 11. The opening quote (3 lines) is a line short of the standard. It has no X-vs-Y section.

#### `fde-core-concept-23-stakeholder-mapping-zh.md`
**Verdict:** light edit
- The pseudo-rigor contradicts itself. 「入度為零的節點…就是 Economic Buyer」 (L53), yet the diagram shows the CISO (a Technical Evaluator) with in-degree 0 as well. Drop the topological-sort framing; the plain influence × sentiment matrix (L171) is enough.
- The high code ratio comes from putting interview-question lists in code fences (L284–305). Convert them to tables or blockquotes for readability.
- Category: `business`. It overlaps guide 26 and 42 only lightly, so this is one of the more distinct topics.

#### `fde-core-concept-24-poc-scoring-roi-zh.md`
**Verdict:** light edit
- Section numbering skips 七 (六 → 八). The post has no X-vs-Y, though the Riskiest Assumption Test (L382) invites one: validate the riskiest assumption first vs build the happy path first.
- The ROI walkthrough (L289–352) is concrete and useful. It overlaps guide 27 (POC scoping) and 29 (TCO/ROI). Link them and trim the repeated ROI formula.
- Category: `business`.

#### `fde-core-concept-25-value-story-objection-zh.md`
**Verdict:** light edit
- **Factual error:** 「FDE（Field Delivery Engineer）」 (L19). Every other post in the batch uses Forward Deployed Engineer.
- Nav: "← 前一篇" points to 22 (Structured Troubleshooting) instead of 24. As the last post in the series it should also link back to an index.
- The five objection sections are a strong, reusable asset. Objection 4, 「被綁定在單一廠商」, overlaps guide 26 (competitive positioning). Category: `business`.

### Top 5 highest-impact fixes in this batch
1. **Delete the leaked `<function_calls><invoke name="TodoWrite">` blocks** at the end of ai-fde-essential-guide part 3 (L1391), part 4 (L1850) and part 5 (L2056). This is a five-minute fix for an embarrassing public leak.
2. **Decide the fate of ai-fde-essential-guide 1–5.** They are code dumps with a few dozen prose lines each, stale models, a hand-rolled fake MCP server and a substring-blacklist "security" example. Retire 1, 3 and 4. Fold 2 and 5 into short prose pointers to core-concept 3/21–25 and guide 17/27/42.
3. **Rebuild the core-concept cross-reference layer in one pass.** Fix the nav slugs *and* labels, rewrite the wrong 「與其他核心主題的關聯」 bullets in 1, 2, 4, 5, 6, 8, 9, 11, 16, 19 and 20, and add a reciprocal link from each fde-interview-guide counterpart so the series is no longer orphaned. Unify the four series names.
4. **Make core-concept vs fde-interview-guide an explicit pairing, not duplication.** Put a "深入版：Guide Part N" link at the top of every core post and position the series as 30-second recall cards. Merge core-6 into core-7/guide-13, and decide canonical ownership for 7↔45, 10↔46, 15↔49, 18↔47 and 20↔36.
5. **Fix the factual errors an interviewer would catch:**
   - core-13: Firestore is strongly consistent.
   - core-14: the latency distribution maths and the misleading 20× claim.
   - core-17: pre-Gemini-2 caching minimums, no mention of implicit caching, the fabricated TPU rationale and the deprecated SDK.
   - core-18: CMEK does not hide inference content from the model vendor.
   - core-16: an impossible "實測" table.
   - core-25: the wrong expansion of "FDE".

   Relabel the invented "實測/我們觀察到" numbers across 3, 6, 13 and 22 as illustrative.
