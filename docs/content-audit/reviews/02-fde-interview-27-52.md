## fde-interview-guide parts 27–52 — 26 posts

### Series-level observations
- **The batch is really three sub-series written in three styles.** (a) Parts 27–34 are consulting-skill and product-knowledge posts: about 300–650 lines, mostly fenced prose blocks, no phase section, no decision tables, and each ends in a scripted "面試回答…示範" answer. (b) Parts 35–42 are shorter system-design posts that close with an italicised 面試答題要點. (c) Parts 43–52 are long, generated-looking "Staff FDE" posts with markdown tables, `╔══ Phase ══╗` headers and flip-condition columns. Only (c) is close to the CLAUDE.md standard. Titles show the split too: 「FDE 面試準備指南（四十四）」, 「FDE 面試指南 Part 43」 and 「FDE Interview Guide Part 49」 all appear. Pick one title pattern and use it for all 26.
- **Series nav in 43–52 points at posts that don't exist, and the link text describes them.** Every post in 43–52 carries a `/posts/fde-interview-guide-partNN-<invented-slug>-zh/` pair with made-up titles: Part 43 says Part 42 is 「多語言向量搜尋」, Part 45 says Part 46 is 「RAG 系統的安全邊界」, Part 50's links read literally 「FDE 面試指南 Part 49」, and Part 52 links to a Part 53 that was never written. The audit's "dead-links=2" in each of these is this problem. It misleads readers, not just crawlers. Parts 35–42 and 44 use relative `../slug/` links, which work but break the `/posts/slug/` convention. Parts 35, 38 and 42 put a second `←` where the "next" link should be, and it points backwards to part 33 or 34. Parts 27–34 have no nav at all (the audit's `series-nav: True` for part 27 is a false positive; the file has none).
- **Heavy topic overlap within the batch and with parts 24–26.** 27 and 42 are both "discovery / POC scoping". 28, 35 and 41 are all "latency incident → tracing". 36 and 50 are both "eval pipeline". 30, 40 and 46 are all "bank/hospital VPC + PII + CMEK". 48 and 52 both build a Redis circuit breaker. 44 and 51 both re-derive Vertex Context Caching, with contradicting minimum sizes: 1,024 tokens in 32 vs 32,768 in 51. 47 repeats part 24 (hybrid model routing), and 48 repeats part 25 (self-reflection). Later parts do not reference the earlier ones, so a reader going in order sees the same material re-explained. Merge candidates are listed below.
- **Model names and prices are stale as of Sept 2026.** Gemini 1.5 Pro/Flash (retired in 2025) carry prices and code in 29, 32, 48, 50 and 51 (`gemini-1.5-pro-001`, `$3.50/1M`). 31, 35, 38 and 41 use `gemini-2.0-flash`. 44 uses `textembedding-gecko`, 47 uses `Gemma-2-9b`, and 48 uses `GPT-4` and `claude-3-5-sonnet` as comparison points. Part 29 labels 1.5 Pro pricing 「2026 年參考」, which is wrong on both counts. The code in 32 and 51 uses the `vertexai` generative SDK (`caching.CachedContent.create`, `model.generate_content`), which was deprecated in favour of `google-genai`; verify and update. Best fix: pull model names and prices out of prose into one dated "pricing assumptions" line per post.
- **Too many precise numbers with no source.** Examples: 「實測修復成功率 Flash 72% vs GPT-4 78%」 (48), 「RECALL@10 從 95% 跌到 70%」 (49), 「P99 延遲：>35 秒（實測爆掉）」 (44), CSAT 3.2→4.4 (47), 重複扣款率 2%→0% (43), and a first-person interviewer's "1–4 scoring" rubric (33). The CLAUDE.md standard asks for concrete numbers, but these read as measurements. Label them 「示意估算」 or give the assumption they come from. Several are also arithmetically wrong (see 39, 44, 47).
- **The 「No Google」 rule collides with what 27–38 are about.** 31 (ADK), 32 (Vertex AI stack) and 33 (interview anatomy: 「Googleyness」, 「Google 的評分…1-4 分」, 「FDE 是 Google 的角色」) cannot be written without naming Google. Removing the word would make them vague or wrong. Two options: exempt product-specific posts explicitly in CLAUDE.md, or rewrite them to say "Cloud"/GCP and state in one line at the top that the stack examples are GCP. Either way, the easy mechanical fixes stand: the `"Google"` tag (should be `"Cloud"`) in 27–38, and 「以 Google FDE 顧問視角」 in the descriptions of 27–30, 32 and 33. Also worth checking: the round is called **RRK (Role-Related Knowledge)** in Google's public hiring rubric. 「RKK（Role-based Knowledge）」 (33 line 21) looks like a typo that spread into every title and tag. CLAUDE.md mandates the `RKK` tag, so the user should decide.
- **Categories are inconsistent.** 27–42 and 44 use `["all","ai","engineering"]`, but 43 and 45–52 dropped `ai`, even though they are all LLM-system posts. Several (39, 43, 46, 49, 52) fit `architecture` better than `engineering`.
- **Traditional-Chinese slips are concentrated in the generated tail.** Part 43 uses 「并发」 five times and 「冗余」, part 44 uses 「信息」 and 「分布式」, and part 37 has one 「并」. Otherwise the text is clean.

### Per-post

#### `fde-interview-guide-part27-poc-scoping-zh.md`
**Verdict:** rewrite/merge
- Covers the same ground as part 42 (discovery → POC scope). Part 42 is longer and closer to the standard. Merge 27's strongest material into 42: the five discovery questions (三、), the Out-of-Scope section (六、) and the 45-minute time box. Then retire 27 or turn it into a short "45 分鐘會議腳本" companion that 42 links to.
- If kept: no 三個演進階段 and no Why-X-not-Y. The phase frame could be POC → pilot → rollout scope, like 42 uses.
- 八、面試回答的完整示範 is a model-answer section under another name. Cut it or turn it into a checklist.
- Description says 「以 Google FDE 顧問視角」, and tags include `Google` and `GCP`. There is no series nav.

#### `fde-interview-guide-part28-incident-communication-zh.md`
**Verdict:** restructure
- The best idea in the batch, and the most distinctive: 四、「不好的說法 vs 好的說法」 for the CTO meeting. But it has no diagrams and no decision tables. The 2–4 AM hypothesis tree (二、) would work well as a real ASCII decision tree.
- Overlaps 41 (troubleshooting) and 35 (tracing). Keep 28 as the customer-communication post and cut its technical diagnosis down to a link to 41.
- 七、面試回答的完整示範 is a model answer. Replace it with a one-paragraph takeaway.
- No series nav. The `Google` tag should be `Cloud`.

#### `fde-interview-guide-part29-tco-roi-zh.md`
**Verdict:** restructure
- Pricing is stale and mislabelled. 「Gemini 1.5 Pro 定價（2026 年參考）: $3.50 / $10.50」 is 2024 pricing for a model that has since been retired, and `text-embedding-004` is also a generation old. The whole 月成本總結 table (≈$3,833) rests on it. Redo it with current models and date the assumption.
- The Vector Search line 「$0.08 per GB per hour」 and the "1.5 GB index" need checking against current node-hour pricing. Node pricing is per machine, not per GB.
- The method is solid: three TCO layers, then ROI for the CFO. Add a Why-X-not-Y block (Pro vs Flash, Vector Search vs pgvector vs Pinecone, Cloud Run vs GKE). Section 三 already has the numbers for it.
- 建置成本 uses a `$X/週` placeholder. Give a range with its assumption.

#### `fde-interview-guide-part30-constraint-driven-architecture-zh.md`
**Verdict:** restructure
- The constraint-classification framework (一、) and the 速查表 (八、) are genuinely useful. But this post, 40 (PII) and 46 (CMEK) are three takes on "regulated bank or hospital on GCP". Make 30 the umbrella post and have 40 and 46 cite it as the deep dives.
- The 速查表 row 「模型必須是我們自己的 → Vertex AI Custom Model Deploy (Gemini 可 Fine-tune + 部署)」 is misleading. A tuned Gemini still runs on the provider's serving stack; the self-hosted option is the "GKE 上自建推論服務" branch. Say so.
- There is no phase section, although the constraints naturally map to POC → production → audited production.
- The body says 「Google Cloud 上的金融/政府客戶必備知識」, the description says 「Google FDE」, and the tags include `Google`. There is no nav.

#### `fde-interview-guide-part31-adk-deep-dive-zh.md`
**Verdict:** restructure
- Factual error in 五、: ADK state prefixes are `app:`, `user:`, `temp:`, and un-prefixed keys are session-scoped. There is no `session:` prefix. That error runs through the state design and through 地雷 3, and the placeholder flags `user:xxx`/`session:xxx`/`temp:xxx` come from this block. Verify `AgentTeam` (二、 table) and 「per-agent retry policy」 on ParallelAgent against current ADK docs as well.
- Two claims are overstated. 「ADK 對非 Gemini 模型支援有限」 ignores ADK's LiteLLM model wrapper. 「LangGraph 的 DAG」 is wrong because LangGraph graphs are cyclic by design. Both bias the ADK-vs-LangGraph verdict.
- The layer diagram in 一、 puts Agent Builder above ADK as a separate low-code product. In the current branding, Agent Builder is the umbrella that contains ADK and Agent Engine. Verify it and redraw.
- This is a product-specific post, so the no-Google rule is in real tension here (see series notes). The title 「Google ADK」 is the correct product name.
- 八、面試回答完整示範 is a model answer, and the post has no nav.

#### `fde-interview-guide-part32-vertex-ai-stack-zh.md`
**Verdict:** restructure
- Most exposed to staleness. The Context Caching block (四、特性四) uses 1.5 Pro prices, `gemini-1.5-pro-001` and the deprecated `vertexai` SDK. Its 「最小 cache 大小：1,024 tokens」 contradicts part 51's 32,768. The product names (Agent Builder, Vertex AI Search, Model Garden and its Gemma list) should be re-checked against the 2026 console.
- The Build-vs-Buy framing (一、) and 「何時不應該用」 (二、) are the valuable part. Turn them into the Why-X-not-Y table with flip conditions that the standard asks for.
- The closing line 「Google FDE 的核心價值不是說『Google 的東西最好』…」 is an honest framing for a product post. It is also exactly what the no-Google rule would delete, which is the tension to raise.
- 八、面試回答完整示範 is a model answer, and the post has no nav.

#### `fde-interview-guide-part33-rkk-anatomy-zh.md`
**Verdict:** light edit (plus a policy decision)
- This is a meta post about the interview itself. The architecture standard (phases, Why-X-not-Y, 600 lines) does not fit it, and forcing that structure in would make it worse. Exempt it explicitly.
- Trust: it is written in the first person as the interviewer (「我這個面試官在評什麼」). It states rubric details as fact (「五個維度上給 1-4 分」, the loop order with 「Googleyness / Leadership Round」 and 「Hiring Committee」) with no source. Reframe it as 「根據公開資料與經驗整理」, or cite a source.
- Verify the acronym: it says 「RKK（Role-based Knowledge）」, but the widely documented term is RRK, Role-Related Knowledge.
- The title promises 「45 分鐘」, but the 二、 timetable runs to 0:55.
- Google appears nine times, and most of those mentions are what the post is about. Add nav.

#### `fde-interview-guide-part34-mock-scenarios-zh.md`
**Verdict:** light edit
- A practice bank, and a useful one. The 客戶場景 → 隱藏限制 → 追問鏈 → 模範答案 → 失分點 template is consistent. It is exempt from the phase standard in spirit, and CLAUDE.md should say so.
- Scenario 一 lists Q1–Q5 but only answers Q1, Q3 and Q5. Q2 (data residency with Vertex) and Q4 (monthly cost) have no answers, and those are the two hardest follow-ups. Check the other five scenarios for the same gap.
- Each scenario should link to the deep-dive part that covers it: scenario 3 → 30/40, scenario 4 → 39, scenario 2 → 31, and so on. That turns the post into the hub of the consulting sub-series.
- The `Google` tag should become `Cloud`, and the post needs nav.

#### `fde-interview-guide-part35-granular-tracing-zh.md`
**Verdict:** restructure
- The span-tree design and 「一條 Trace 應該回答的五個診斷問題」 are good, practical material. But there is no phase section, and 八、Trade-off 總覽 is a four-row table with no flip conditions. Expand it to 4–6 decisions, for example Cloud Trace vs Jaeger and 1% head sampling vs tail sampling.
- The sampling advice (「1% 採樣，異常請求 100% 保留」) needs tail-based sampling (an OTel Collector), which the post never names. With head sampling you cannot keep slow requests you have already dropped. Say how it is actually implemented.
- 九、面試答題要點: cut it.
- Nav: both links use `←`, and the second (part 36) should be `→`. Also overlaps 41, so link the two.

#### `fde-interview-guide-part36-eval-pipeline-zh.md`
**Verdict:** rewrite/merge
- Part 50 covers the same "eval pipeline for model/prompt changes" problem at twice the depth, with stratified sampling, drift alerts and shadow eval. Merge 36's legal-domain specifics into 50 and retire 36, or narrow 36 to 「黃金資料集設計」 alone. Those specifics are the lawyer-built golden set, Safety as a separate hard gate and the 0.90 threshold agreed with the 法務長.
- The cost claim (「200 題 × $0.002 ≈ $0.4/次」) is plausible but depends on the judge model. Name the model and date the figure.
- No phase section and no Why-X-not-Y beyond RAGAS vs Vertex Eval. It still has 九、面試答題要點.

#### `fde-interview-guide-part37-legacy-integration-zh.md`
**Verdict:** restructure
- High reader value: the three concrete integration patterns (SAP adapter, Oracle stored-procedure layer, mainframe CSV → BigQuery) are advice that docs don't give. The patterns are also a natural Why-X-not-Y: API bridge vs direct call, SP layer vs text-to-SQL, batch vs CDC. Add flip conditions to each, for example "when does CDC/Datastream replace the nightly CSV?".
- There is no phase section. POC with direct calls → MVP with adapters and cache → Scale with CDC and an event bus would fit well.
- The 八、 answer says 「Cloud Run 透過 VPC Connector」. Direct VPC egress is now the recommended path, so verify and update.
- It still has 面試答題要點, and there is one simplified 「并」.

#### `fde-interview-guide-part38-prototype-to-production-zh.md`
**Verdict:** restructure
- The title and the list in 一、 promise five gaps, but there is no 差距 4 (錯誤處理) section. The headings go 差距 1, 2, 3, 5. Write the missing section, which is arguably the most practical of the five.
- The nav's second link is `← （三十三）` instead of `→ （三十九）`.
- 「模型版本釘選（防止 Google 更新破壞你的 Prompt）」 can say 「模型供應商」 and lose nothing, so the Google rule costs nothing here.
- No phase section and no Why-X-not-Y (prompt versioning in Git vs a prompt registry, canary vs blue-green). It still has 面試答題要點.

#### `fde-interview-guide-part39-scalability-zh.md`
**Verdict:** light edit
- The closest match to the standard in the 35–42 group: phases, six decisions, and a before/after table. It runs past 十 only because of 十一、面試答題要點, so deleting that one section fixes the numbering.
- The arithmetic in 十、 is wrong. 「$1,500,000 × 45% 省去 ≈ $825,000」 does not compute (45% of $1.5M is $675K; $825K is 55%), and the next line says 55%. The 100K-MAU line 「$82,500 × 30%」 has no stated base. Fix both, because the 「ROI 200x」 headline depends on them.
- Six decisions (九、) but only decision 5 (Read Replica vs Sharding) has a real flip condition. Add one to each, for example "Postgres sessions are fine below N QPS if you already run it".
- `"task_id": "uuid-xxx"` is fine as an illustration.

#### `fde-interview-guide-part40-pii-security-zh.md`
**Verdict:** light edit
- Factual fixes in 八、決策 2: CMEK keys live in Cloud KMS (or EKM), not 「客戶自己的 Secret Manager」. 「醫療資料（HIPAA 強制要求）」 CMEK is also wrong, since HIPAA does not mandate customer-managed keys. Encryption is "addressable", and CMEK is usually a customer or contract requirement.
- In 決策 1, both columns say 「GDPR/HIPAA 認可」. That hides the key point: under GDPR, pseudonymised data is still personal data and anonymised data is out of scope. Say it, because it is the reason to choose pseudonymisation carefully.
- Good structure otherwise (phases, PII flow, audit design). Only 面試答題要點 pushes it to 十, and it overlaps 30 and 46 (see series notes).

#### `fde-interview-guide-part41-troubleshooting-zh.md`
**Verdict:** light edit
- A solid diagnostic post (symptom matrix, decision tree, five failure modes, SLO/error budget). Make it the canonical troubleshooting post and have 28 and 35 link here.
- In 八、, decisions 1–4 all declare a winner ("OTel ✅", "P95 最佳平衡點") without saying when the other choice wins. Add flip conditions, for example "P99 when the SLA is contractual or per-tenant; vendor SDK when you are all-in on one APM and need its auto-instrumentation."
- 「xxx 系統暫時不可用」 (line 367) is user-facing copy. Use a real placeholder such as `{system_name}`.
- 十一、面試答題要點 pushes it past 十.

#### `fde-interview-guide-part42-consulting-discovery-zh.md`
**Verdict:** light edit
- The stronger of the two discovery posts: stakeholder map, scoring matrix, Value Story, objection handling. Absorb part 27 into it (see 27).
- The phase section (Discovery → Technical Assessment → POC Proposal) is a sensible adaptation for a consulting post, and the audit's "three-phases False" is expected here. Note the exemption in CLAUDE.md so it isn't "fixed" into user-count tiers.
- Nav's second link is `← （三十三）` and should be `→ （四十三）`.
- 十一、面試答題要點 pushes it past 十.

#### `fde-interview-guide-part43-async-cart-agent-zh.md`
**Verdict:** restructure
- Nav links to non-existent Part 42 and Part 44 slugs with invented titles. The 系統效應 figures are presented as measured with no basis (「重複扣款率 ~2% → 0%」, 「任務遺失率 < 0.001%」).
- The scenario is internally shaky. "200 萬個並發 Agent 在背景與供應鏈 Agent 協商折扣" during Black Friday is an unusual product requirement, and the post never questions it. A strong answer would push back on the requirement first; add one paragraph doing that.
- Simplified characters: 「并发」 appears five times and 「冗余」 once. The title format 「FDE 面試指南 Part 43」 breaks the pattern.
- It has two post-answer sections (十一、面試答題要點 and a 關鍵架構決策速查表). Keep the 速查表 and cut the model answer, which also brings the numbering back to 十.
- Categories are missing `ai`; `architecture` fits better than `engineering`.

#### `fde-interview-guide-part44-hybrid-context-rag-zh.md`
**Verdict:** restructure
- The scenario contradicts itself. 50,000 analysts × 20 queries/day is 1M/day, about 12 QPS on average, but the scenario says 「並發查詢量衝到 50,000 QPS」. The later throughput claims (500 → 50,000 並發, 「1M QPS 下節省 2000 CPU 秒/秒」) inherit the error. Fix the load model first.
- The post designs around 「TPU Load Monitor」 and 「TPU 負載 > 85% 時全量切換 RAG」. A Vertex AI Gemini customer cannot see the provider's TPU utilisation; the signals they do get are 429s, quota, latency and Provisioned Throughput usage. Rewrite the degradation trigger around signals the customer actually has.
- The cost table still shows 「動態混合」 at ≈$15M/month. The post never confronts that, even though it would be the real finding. Stale references: `textembedding-gecko` (retired), GPT-4 as the classifier comparison, 「Gemini Pro」 at $2.50/1M.
- Nav points to 「（四十五）下一篇：即將推出」 at `../fde-interview-guide-part45-zh/`, although part 45 exists. It has 十二、面試答題要點, and 「信息」/「分布式」 slip in.

#### `fde-interview-guide-part45-prompt-injection-defense-zh.md`
**Verdict:** light edit
- One of the best in the batch. It frames injection as a trust-boundary and privilege-separation problem, not a prompt problem, and the six-layer pyramid in the closing section is a clear takeaway. The residual-risk section is honest.
- Structure: after 十、面試答題要點 come two more untitled-number sections (延伸思考, 總結). Drop the model answer and fold 延伸思考 into 九, and the post ends cleanly at 十.
- Nav points to invented Part 44 and Part 46 slugs. Categories are missing `ai`.
- Add a pointer to the dual-LLM / CaMeL-style privilege-separation literature, so readers see this isn't a home-grown idea.

#### `fde-interview-guide-part46-byok-cmek-zh.md`
**Verdict:** rewrite/merge
- The core architecture is not implementable as described. The customer injects DEKs into a Confidential VM 「Memory Enclave」, which then decrypts vectors 「for Vertex AI ANN queries」. Vertex AI Vector Search is a managed service: with CMEK, the provider's envelope encryption does the key handling at rest, and no per-query KMS round trip is visible to the customer. The opening premise, 「每次都要跨海解密…延遲從 30ms 暴增到 12 秒」, is therefore a strawman. AMD SEV and Intel TDX are also whole-VM memory encryption, not enclaves. The interesting and correct parts are EKM/Key Access Justifications and the revocation blast radius. Rebuild the post around those: what breaks when the bank revokes the key, and what the SLA impact is.
- 「台灣金融監理局（FSC）」 is wrong. The regulator is 金融監督管理委員會 (金管會/FSC). 「15 分鐘內撤銷」 as a regulatory requirement needs a source.
- The `ekm_config` YAML invents fields (`auto_revoke_on_anomaly`, `anomaly_threshold_per_minute`). Mark it as illustrative pseudo-config. It also contains `GOOGLE_INITIATED_*` enum names, which are real API values; keep them in code, as the no-Google rule should not touch identifiers.
- The heading `## 系列導航` is immediately followed by `**系列導航**` (a duplicate), and the links are invented. It has 13 tags, so trim the keyword dump. Categories are missing `ai`.

#### `fde-interview-guide-part47-edge-model-routing-zh.md`
**Verdict:** restructure
- The arithmetic in 九、 is wrong. 「$0.0001 × 80% + $0.015 × 20%」 is about $0.0031, not $0.0018, so the headline 「-65%」 and $1,800/month do not follow. The scenario also requires 「90% 的查詢必須留在地端」, but the result table shows 83.5% local routing, which fails the stated requirement without comment.
- 「Vertex AI 預熱實例」 and 「按需啟動平均冷啟動 15–20s」 do not apply to the managed Gemini API, which has no customer instances to warm. The relevant lever is Provisioned Throughput. 「送出 TCP RST 中斷地端生成」 is also an odd abort mechanism when vLLM supports request cancellation.
- 九、 and 十、 are both titled 「系統效應」. Merge them, and remove 十一、面試答題要點.
- Stale: Gemma-2-9b. It overlaps part 24 (hybrid model routing), so cross-link or merge. Nav points to placeholder slugs (`part46-zh`, `part48-zh`) with text 「前一篇主題」.

#### `fde-interview-guide-part48-self-healing-agent-zh.md`
**Verdict:** light edit
- Internal inconsistency: 八、 says the chosen Critic model (gemini-1.5-flash) repairs 72% and GPT-4 78%, but 九、 and the answer claim 「78%（Critic Agent 修復成功）」. Use one number and label it as an estimate.
- The motivating failure (`DD/MM/YYYY` dates) is exactly the case where a deterministic parser beats an LLM Critic. Add a flip condition saying so: known-format drift → coercion in the validator, unknown structure → Critic. That makes the decision table honest.
- Stale models: gemini-1.5-flash, GPT-4, claude-3-5-sonnet. It overlaps part 25 (self-reflection) and part 52 (circuit breaker), so cross-link them.
- Nav points to invented 47/49 slugs, and it has 十、面試答題要點 plus a 十一 追問 section. Keep the follow-ups and drop the model answer.

#### `fde-interview-guide-part49-vector-drift-pipeline-zh.md`
**Verdict:** restructure
- The premise needs checking. Vertex AI Vector Search is built on ScaNN (tree-AH), not HNSW, yet the whole post is about 「HNSW Graph Drift」 in Vertex Vector Search. Either change the setting to an HNSW store (pgvector, AlloyDB and most open-source vector DBs), or rewrite the drift discussion for streaming updates in ScaNN-style indexes. 「RECALL@10 從 95% 跌到 70%」 needs a source or an 「示意」 label.
- The Lambda base+delta index, blue-green swap and tombstone blacklist are valuable patterns whichever index is underneath.
- 十三、系列回顧 is filler: generic claims about the series, including 「面試可直接使用的 RKK 模型答案」, which contradicts the dropped model-answer standard. Delete it, along with 十、面試答題要點, and the numbering fits under 十.
- The English title 「FDE Interview Guide Part 49」 breaks the pattern. Nav slugs are invented. Categories are missing `ai`.

#### `fde-interview-guide-part50-llm-judge-evaluation-zh.md`
**Verdict:** light edit
- A good post: sampling math, judge biases and shadow eval, with real paper references in 延伸閱讀. Make it the canonical eval post and absorb part 36 (see 36).
- The scenario's 「從 Gemini 1.5 Pro 升級至 Gemini 2.0 Flash」 and the per-1K prices in 一、 are stale. Restate them as "model N → N+1" with a dated price footnote so the post ages better.
- 「Sigma 2 警報」 on a daily judge-score mean needs the sample-size caveat from 三、 carried into 五、, because with a few hundred samples per stratum 2σ fires often. Add the expected false-alert rate.
- Nav points to invented 49/51 slugs with the text 「FDE 面試指南 Part 49」. It has 十一、面試答題要點, and categories are missing `ai`.

#### `fde-interview-guide-part51-kv-cache-memory-zh.md`
**Verdict:** rewrite/merge
- The title and body conflate two different things. The scenario pays a Vertex AI bill of $120K/month, which means managed Gemini, yet it also suffers 「GPU 顯存 OOM 崩潰率 3%」 on its own GPUs. A Vertex Gemini customer does not manage KV cache or VRAM, and the 「L1 Redis 對話槽位」 is a conversation-history cache, not a KV cache. Either set it on self-hosted vLLM (where KV-cache eviction and PagedAttention are real concerns), or retitle it as 「多輪對話上下文快取分層」 and drop the VRAM framing.
- 「以 Gemini 1.5 Pro 為例：每 1K tokens 的 KV Cache 佔用約 0.5–1 MB」 is not public information; present it as a generic transformer estimate with the formula. The Context Caching rules in 1.2 (32,768-token minimum, 「不足一小時按一小時」) are 1.5-era rules or unverified. They also contradict part 32, and newer models add implicit caching. Verify them.
- The `gemini-1.5-pro-001 → 002` example in the cache-invalidation section is stale.
- It overlaps part 44's Context Caching Registry, so consider one caching post. It has 十一、面試答題要點, a duplicate 系列導航 heading, and invented nav slugs.

#### `fde-interview-guide-part52-tool-fanout-optimization-zh.md`
**Verdict:** light edit
- A concrete and useful post: hedged requests with the "Tail at Scale" citation, `asyncio.wait` vs `gather`, a hard deadline with partial rendering, and a semaphore for backpressure. The best practitioner value in the tail.
- Modernise the code discussion. Python 3.11+ has `asyncio.TaskGroup` and `asyncio.timeout()`, which are now the idiomatic answer to "why not gather". Mention them in 3.3 and give a flip condition for when TaskGroup's cancel-all semantics are what you want.
- 延伸閱讀 says 「Martin Fowler, "Circuit Breaker" pattern — circuitbreaker.io」. Fowler's article is on martinfowler.com, so fix the attribution. The circuit-breaker design overlaps part 48, so cross-link them.
- Nav points to an invented Part 51 slug and a non-existent Part 53. It has 十一、面試答題要點, and categories are missing `ai`.

### Top 5 highest-impact fixes in this batch
1. **Rebuild the series nav for 27–52 from the real filenames.** Replace the invented `/posts/…` slugs and titles in 43–52 and the nonexistent Part 53. Fix the reversed or mis-targeted arrows in 35, 38, 42 and 44. Add nav to 27–34. Use `/posts/<slug>/` everywhere instead of `../slug/`. One script can do all of it, and it is the change most visible to readers.
2. **Fix the factually wrong architecture premises before polishing anything else:** 46 (customer DEKs in a "Memory Enclave" serving managed Vector Search), 51 (KV-cache/VRAM on managed Gemini), 49 (HNSW in Vertex Vector Search), 44 (customer-visible TPU load; 50K QPS from 12 QPS of demand), 31 (`session:` state prefix, LangGraph as a DAG). The same list covers the smaller factual fixes in 40 (CMEK in Secret Manager, "HIPAA mandates CMEK") and the regulator's name in 46.
3. **Consolidate the overlapping posts:** 27 → 42, 36 → 50, 30 as the umbrella for 40 and 46, 28 and 35 pointing to 41, and 44 and 51 sharing one caching treatment. Cross-link 47↔24 and 48↔25↔52. This removes most of the "re-explains the same basics" feel.
4. **Run one standards pass across 35–52:** delete every 面試答題要點 (this alone brings nearly all of them back under 十), add flip conditions to the decision lists in 35–42, and add a 三個演進階段 section to 28–30, 35–38. Then decide explicitly in CLAUDE.md that 33 (interview anatomy), 34 (mock bank) and 42 (consulting phases) are exempt from the user-tier phase format.
5. **Refresh models and prices, and label estimates:** replace Gemini 1.5/2.0, gecko, Gemma-2 and GPT-4 references with a dated assumptions line, and fix the broken arithmetic in 39, 44 and 47. Mark unsourced "實測" figures as 示意估算. At the same time, settle the Google/RKK policy: change the `Google` tag to `Cloud` in 27–38, decide whether ADK/Vertex/interview-anatomy posts are exempt from the no-Google rule, and confirm whether "RKK" should be "RRK".
