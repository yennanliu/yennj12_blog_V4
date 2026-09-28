## fde-interview-guide parts 1–26 — 26 posts

### Series-level observations
- **None of the 26 posts meets the current CLAUDE.md standard, and they fall into three tiers.** (a) Parts 1–9 are "foundations": concept primers with a `面試情境` and a `面試回答完整示範` closer. (b) Parts 10–15 are topic essays: no scenario, and each ends in a mnemonic framework (SCOPE, DARK, CAPE) plus a 快速複習卡. (c) Parts 16–25 are scenario drills: they open with a concrete `面試情境` and close with a `面試答題要點`. No post has 三個演進階段, and only part 10 has anything close to a 為什麼選 X 不選 Y table with a flip condition. Tier (c) sits closest to the standard's shape (scenario, then deep dive, then decisions), so it is the cheapest to upgrade. Recommendation: **upgrade 16–25 to the full standard**; **keep 1–9 as a deliberately lighter "Foundations" tier**, since they are primers and padding them to 600 lines would dilute them, but fix their trust and staleness problems and merge the duplicates (3→8, 1→5/6); **fold 10–15 into their tier-(c) twins** (see the next bullet) or cut them down to short "concept" companions.
- **Parts 10–15 and 16–25 cover the same ground twice, and the two sets never link to each other.** The duplicate pairs: 13 ↔ 20 (prompt injection → indirect injection), 14 ↔ 18 (memory architecture → three-layer memory and cost), 12 ↔ 19 (agent eval → multi-agent eval and tracing), 11 ↔ 19 (tracing), 15 ↔ 18/24 (cost and cache → context caching and routing cost), 7 ↔ 16 (multi-agent), 2/7 ↔ 22 (tool calling). A reader going through 10→25 sees the same Lost-in-the-Middle, "Output Validator is the key layer" and "Redis + Firestore state" material two or three times. Each pair should become one standard-format post, or the later post should say "builds on part N" and skip the recap.
- **The "no Google" rule collides with what this series is about.** The series prepares readers for a Google Cloud FDE loop: RKK, "Googleyness" in part 33, Vertex AI, ADK, Gemini, GKE. Parts 2 (`六、Google ADK 的定位`), 22 (`五、Google ADK 的 Tool Registry 架構`) and 26 (the whole post) cannot be written without Google. Workable reading of the rule: remove the **employer and identity claims**, tag `"Cloud"` instead of `"Google"`, but keep product names (Vertex AI, ADK, Gemini) as neutral references. The worst offence is the part 1 opening, `> 我在 Google 做 AI 工程，也是面試官。`, together with the description template `以 Google AI 工程師兼面試官的視角…` used in 9 posts (1–9). That is an unverified, first-person claim about the author's employer and role as an interviewer, and it may be NDA-sensitive. Remove it first. Parts 26–27 onward use `以 Google FDE 顧問視角`, which has the same problem one level softer.
- **Model and price staleness is systemic (as of Sept 2026).** Examples: the `Gemini 1.5 Pro` / `1.5 Flash` prices ($1.25/1M, $0.075/1M) that drive every cost calculation in 15, 18, 23 and 24; `GPT-4o` at $5/1M in 26; `Claude 3.5 Sonnet` in 10 and 9; `Gemma-2b/7b` in 24; `text-embedding-004` recommended as the GCP default in 3, 5, 9, 18 and 24. Gemini 1.5 has been retired, and text-embedding-004 has been superseded by `gemini-embedding-001` (verify the shutdown date). Fix: add one dated "pricing assumptions (as of YYYY-MM)" block per post, or one shared reference post, instead of hard-coding prices inline in ASCII boxes.
- **The series navigation is broken in several places.** Part 9 ends with `*本系列已完結。*`, yet 40+ posts follow it. Part 4 has no nav at all, part 26 has none either, and part 15 links back to part 14 and to part 1 but not forward to part 16. Nav labels drift from the real titles: part 15 calls part 1 `（一）RAG 完全攻略` (the title is 完全解析), and part 16 calls part 17 `MCP 與 Tool-Calling 安全隔離`. The link style is also split. Parts 1–9 and 26 use `/posts/<slug>/`, as CLAUDE.md requires. Parts 10–25 use relative `../<slug>/`. That works today, but it goes against the house convention and does not go through `site.GetPage` in `render-link.html`. Standardise on `/posts/<slug>/`.
- **The code-ratio numbers overstate how much code there is.** Nearly all "code" here is ASCII diagrams and pseudo-config inside fenced blocks, not runnable code. The real balance problem is different: many posts are **walls of fenced plain text** holding prose, bullets and even the "model answer". Parts 16–25 regularly exceed 0.7 on this measure. Text inside fences cannot wrap on mobile and cannot be searched or styled. Move prose-like fenced blocks back into Markdown bullets and tables, and keep fences for real diagrams.
- **The "model answer" format survives under other names.** Beyond the flagged `面試答題要點` in 16–25, parts 1–9 close with `面試回答完整示範`, and 10, 11 and 15 close with SCOPE/DARK/CAPE frameworks plus a `完整範例回答`. These are the same model-answer section the standard dropped, so a mechanical upgrade that removes only `面試答題要點` will miss them.
- **The language is clean.** I found no Simplified-Chinese slips, and the terminology is mostly consistent. The one real clash is "Semantic memory": in part 14 it means the *structured profile*, while in part 18 "Semantic Long-term Memory" means the *vector summaries*, which part 14 calls "Episodic". Pick one taxonomy.

### Per-post

#### `fde-interview-guide-part1-rag-zh.md`
**Verdict:** light edit
- Remove the opening `> 我在 Google 做 AI 工程，也是面試官。` and the matching description `以 Google AI 工程師兼面試官的視角…`. It is an unverifiable employer claim and it breaks the no-Google rule. Replace it with the standard 4-line contrast quote.
- A solid primer. Keep it as the Foundations entry point, but add a forward pointer to parts 5 and 6, which re-cover 四、Chunk 設計 and 五、Retrieval 品質 in more depth.
- `八、面試回答完整示範` is a model-answer section. Turn it into a short "how to structure the answer" checklist, or drop it.
- Swap the `Google` tag for `Cloud` and add `RKK`.

#### `fde-interview-guide-part10-context-management-zh.md`
**Verdict:** restructure
- The model table in `五、關鍵考量：Lost-in-the-Middle` (`Gemini 1.5 Pro | 1M`, `Gemini 2.0 Flash`, `GPT-4o | 128K`, `Claude 3.5 Sonnet | 200K`) is stale. Replace it with current models, or make it generic ("1M-class vs 128K-class").
- `一、核心問題` says attention is O(n²) and that doubling the context makes latency "接近翻兩倍". Clarify: prefill scales super-linearly, but the latency users see is dominated by output tokens. As written, the claim reads as wrong.
- `七、面試答題框架：SCOPE` with its `完整範例回答` is a model-answer section. Fold SCOPE into a checklist.
- This is the best candidate in 10–15 for a 三個演進階段 section (sliding window at POC, summary buffer at MVP, retrieval plus structured state at scale). The strategy comparison table in `四` is already halfway there.
- The strategies here overlap heavily with 14 and 18. Merge them, or cross-link explicitly.

#### `fde-interview-guide-part11-agent-debugging-zh.md`
**Verdict:** restructure
- `六、Google Doc 模擬情境應答框架：DARK` names the interview medium, which reveals the interview format and breaks the no-Google rule. Retitle it to something like "貼 log 模擬題的應答框架".
- Section `四` has good symptom-to-diagnosis trees (the fault-1 hallucination tree in particular). But the `score < 0.7` and `Faithfulness < 0.8` thresholds are presented as universal, with no source and no "calibrate per corpus" caveat.
- It has no tables at all. `五大故障模式` would read better as a table (symptom, signal in Metrics/Traces/Logs, root cause, fix).
- It overlaps part 19's tracing material. Pick one home for the Metrics/Traces/Logs layering.

#### `fde-interview-guide-part12-agent-evaluation-zh.md`
**Verdict:** light edit
- A useful framing (performance/quality/business in `一`), and it names the LLM-as-Judge biases in `五`. Keep it.
- `LLM-as-Judge 的已知偏差` recommends a judge from a different vendor to avoid self-preference bias. Part 25 then uses the same Gemini Pro as both generator and evaluator. Add a sentence here, or in 25, that reconciles the two.
- The 13 tags read as a keyword dump (`RAG`, `RAGAS`, `LLM`, `Observability`, `System Design`). Trim to about 8.
- Add 1–2 X-vs-Y decisions: RAGAS vs a custom judge, and offline vs online eval, with flip conditions.

#### `fde-interview-guide-part13-prompt-injection-zh.md`
**Verdict:** rewrite/merge
- It is a near-duplicate of part 20. Both present the 5-layer defence and both put output/tool-call validation first. Merge them into one standard-format post: direct injection moves to a subsection, and Dual-LLM becomes the Phase 3 design.
- `Layer 4：OAuth 與最小權限原則` opens with `JD 特別提到「OAuth-based authentication」的原因`, which ties the post to one specific job posting. Reword it as a general principle.
- Layer 2 (delimiter tags as the defence) is presented as meaningful protection. Say plainly that delimiters are a weak mitigation and that Layers 3–4 carry the real weight. The post half-says this.

#### `fde-interview-guide-part14-memory-architecture-zh.md`
**Verdict:** rewrite/merge
- It overlaps part 18 almost completely. Worse, the two use conflicting terms: here "Semantic Memory" = structured profile and "Episodic" = vector store, while in part 18 "Semantic Long-term Memory" = vector summaries. Merge them into one post with one taxonomy.
- `五、四大工程挑戰` (conflict, staleness, privacy, precision vs recall) is the strongest part and should survive the merge. Add numbers to it (retrieval k, TTL, cost of an extraction pass).
- A code ratio of 0.69 with no tables: the profile JSON box in `四` is illustrative and could be half its size.

#### `fde-interview-guide-part15-scale-cache-zh.md`
**Verdict:** restructure
- The cost math contradicts itself: line ~34 uses `$0.002/1K tokens` ($2/1M), while `七、成本估算框架` uses Flash at `$0.075/1M`, a 27× gap. Both rest on Gemini 1.5-era prices. Pick one dated price sheet.
- The explicit context-cache discount in `五` (`$1.25/1M` → `$0.31/1M`) is 1.5 Pro pricing, and it ignores cache **storage** cost. Verify it against current Vertex pricing, which now includes implicit caching.
- The series nav has no forward link to part 16 and mislabels part 1 as `RAG 完全攻略`.
- Only 2 ASCII diagrams. This topic begs for the three-phase treatment: exact-match cache at POC, semantic cache at MVP, plus prefix/KV caching and routing at scale.
- `九、面試答題框架：CAPE` is a model-answer section.

#### `fde-interview-guide-part16-multiagent-state-deadlock-zh.md`
**Verdict:** restructure
- A good scenario. `四、解決策略` (boundaries, reducer, iteration cap, checkpoint) is the right skeleton. Turn `五、技術選型：各狀態存儲方案` into a proper X-vs-Y table with flip conditions (Redis vs Firestore vs Postgres checkpointer).
- The scenario text says `你在 Google Doc 看到對話日誌`. Change it to "你拿到一份對話日誌".
- `六、架構演進：從 LangGraph 的角度` is the natural place for 三個演進階段. Expand it.
- Remove `七、面試答題要點`.
- The "deadlock" here is really a livelock or cyclic delegation. Say so, because an interviewer may probe the distinction.

#### `fde-interview-guide-part17-mcp-tool-oauth-zh.md`
**Verdict:** restructure
- The MCP content does not reflect the current MCP authorization spec: OAuth 2.1, the MCP server as a protected resource, and the explicit "no token passthrough" guidance. `六、架構選型` still says `OAuth 2.0 PKCE`. The design of injecting the user's token into the tool execution context should be checked against the spec (verify the current spec version).
- `七、GCP 落地設計` is fine, but name products neutrally, and keep the post's value in the vendor-agnostic flow.
- At 288 lines this is the thinnest of 16–25, and it has no tables. The token-expiry handling in `四` needs numbers (access token TTL, refresh window, behaviour when a HITL approval times out).
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part18-memory-cost-tuning-zh.md`
**Verdict:** restructure
- **The context-cache example is technically wrong.** It caches an 800-token system prompt (`首次：建立 Cache，System Prompt + Profile (800 tokens)`), which is far below Vertex's minimum cacheable size (historically 32K tokens for explicit caching; verify the current minimum). It also leaves out storage cost. Rework it with a realistically sized prefix.
- The headline `節省：98.7%（$16,578/月）` uses a flat `$1.25/1M` rate for a 450K-token prompt. Gemini 1.5 Pro charged a higher tier above 128K, and the model is now retired. Re-derive the numbers on a current model and keep the % claim as an estimate.
- The terminology clash with part 14 is described above. Merge the two.
- `TTFT 5~20 秒` vs `0.3~0.8 秒` has no source. Label it as an estimate.
- Remove `七、面試答題要點`.

#### `fde-interview-guide-part19-multiagent-eval-tracing-zh.md`
**Verdict:** restructure
- The four-level metric set in `四` (routing accuracy → tool execution accuracy → trajectory match → cost) is the useful core. Turn it into a table with the Traces/Metrics signal for each level.
- `六、工具選型：Tracing 平台比較` should become a real X-vs-Y table with flip conditions (LangSmith vs OTel + Cloud Trace vs Langfuse/Phoenix, and when self-hosting wins).
- A code ratio of 0.75 with no tables: several fenced blocks are prose. Unfence them.
- It overlaps 11 and 12. State at the top that this builds on 12 and skip the re-intro.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part2-agent-zh.md`
**Verdict:** light edit
- Remove the `以 Google AI 工程師兼面試官的視角` description. `六、Google ADK 的定位` opens with `FDE 面試 Google 職位，ADK 可能被問到`, which states the target employer. Reframe it as "cloud-native agent frameworks (ADK) vs LangGraph".
- `五、MCP` (`Anthropic 和 Google 都在推的標準化工具協定`) is thin for 2026. MCP is now broadly adopted and has an auth spec. Either give it one paragraph, or point to part 17.
- A good Foundations post. The `四、失控防禦：四道護欄` numbers (20 steps, 60s, 90% similarity) are concrete, which is good.
- `八、面試回答完整示範` is a model answer. Convert it to a checklist.

#### `fde-interview-guide-part20-indirect-prompt-injection-zh.md`
**Verdict:** rewrite/merge
- Merge with part 13, as described there. This post's `四、Dual-LLM 防禦架構` and `五、Privilege Separation` are the parts worth keeping. Cite the origin of the pattern (Simon Willison's Dual-LLM proposal; CaMeL-style capability separation) instead of presenting it as original.
- `五` still leans on trust-level tags in the system prompt (`Trust Level: DATA ONLY`) as a defence. That contradicts the post's own argument that prompt-level rules can be bypassed. Make the prompt layer explicitly secondary.
- The scenario uses a concrete malicious address `x@mail.com`. Use a reserved example domain (`attacker.example`).
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part21-async-longrunning-agent-zh.md`
**Verdict:** restructure
- It misses the operational catch in its own design: a Pub/Sub message has a bounded ack deadline (max 600s; verify), so a 30–60 min task needs lease extension or a different primitive (Cloud Tasks, Cloud Run Jobs, Workflows). Add this as a decision table with flip conditions.
- Checkpoint resume skips steps that "已完成", but the post never discusses idempotency of **side-effecting** steps (emails, writes) on replay. Add that; it is the classic follow-up question.
- `四、進度回報的三種設計` (polling, WebSocket, SSE) is already an X-vs-Y. Add the flip conditions and it counts toward the standard.
- `七、完整的任務狀態機` is good. Keep it.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part22-parallel-tool-calling-zh.md`
**Verdict:** restructure
- The worked example undercuts the hook. The opening promises `T₁+T₂+T₃ → max(T₁,T₂,T₃)`, but the DAG example in `三` saves only 1,050 → 900ms (about 14%). Pick an example where parallelism clearly pays, or say that dependency depth caps the gain.
- In the `四` table, `ThreadPoolExecutor` is listed for `CPU 密集型`. That is wrong for Python, because the GIL serialises CPU-bound threads. Use ProcessPool for CPU-bound work and threads for blocking I/O.
- `五、Google ADK 的 Tool Registry 架構` shows a `depends_on: ["get_user_profile"]` field and an orchestrator that "自動解析依賴圖". I am not aware that ADK exposes a dependency-declaring tool registry. **Verify, or reframe as a proposed design.** As written, it presents a feature as fact.
- The post has 6 Google mentions. Recast `五` in vendor-neutral terms.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part23-ratelimit-fairshare-zh.md`
**Verdict:** restructure
- Strong topic and one of the better posts: the token-aware bucket and the switch to fair-share at >80% quota. Turn round-robin vs weighted fair queuing vs DRR into an X-vs-Y table with flip conditions (tiered SLAs make weighted the right call).
- `四、Token 估算的工程挑战`: say how output tokens are reserved and reconciled after the call (pre-debit max_tokens, refund the difference). That is the non-obvious part.
- Gemini 1.5 Pro references are stale.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part24-hybrid-model-routing-zh.md`
**Verdict:** restructure
- The model set is stale throughout: `Gemma-2b`, `Gemma-7b`, `Gemini 1.5 Pro`, `text-embedding-004`. The cost analysis in `七` ($7,500 → $3,790) rests on those prices. Update it to current models and date the assumptions.
- The opening `品質幾乎一樣，成本低 20 倍` has no source. Label it an estimate, or show the arithmetic (the L4 section later does show the arithmetic, so link the two).
- The 0.88 similarity threshold is shown as a fixed constant. Show how it is calibrated from the eval set in `五`, which is the interesting part.
- The self-hosted-vs-API decision (`六、Gemma on GKE`) needs a flip condition: below roughly N req/day, the GPU node costs more than the API savings.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part25-self-reflection-loop-zh.md`
**Verdict:** restructure
- `二、Reflexion Pattern` → `洞察 1：同一個 LLM 作為生成者和評估者`, and the answer section repeats it (`同一個 Gemini Pro`). This contradicts part 12's advice to use a judge from a different vendor to avoid self-preference bias. Either justify it (a role prompt is enough for contradiction detection) or recommend a different or smaller judge model.
- The post calls its design "Reflexion", but the Reflexion paper (Shinn et al.) is about verbal feedback across trials, backed by episodic memory. What the post describes is closer to a generator-critic/self-refine loop. Name it accurately, or cite both.
- `七、Trade-off 總覽` usefully says reflection should be opt-in. Add the numbers: added latency and cost per reflection round, and the observed fix rate.
- Remove `八、面試答題要點`.

#### `fde-interview-guide-part26-competitive-positioning-zh.md`
**Verdict:** restructure
- **The trust and staleness problems are serious here, because the post is persuasion.** The `論點 C` price table (`GPT-4o $5.00` vs `Gemini 1.5 Pro $3.50` per 1M) is out of date and contradicts the $1.25 used in parts 18 and 24. `論點 A` sets up OpenAI as a strawman: it says data goes to OpenAI's US servers and that its data-use policy needs checking. OpenAI's API does not train on API data by default, offers BAAs and has data-residency options, and Azure OpenAI offers regional deployment (verify the current details). An interviewer from the other side of this debate would take that apart.
- The SDK example in `四` points to `generativelanguage.googleapis.com` (the Gemini Developer API, not Vertex AI) with `gemini-1.5-pro`. That undercuts the post's own data-residency argument. Use the Vertex endpoint and a current model.
- `CUD… 最高 ~60% 折扣` for Gemini: Vertex model pricing uses Provisioned Throughput, not compute CUDs. Verify.
- It has no series nav at all. Add links back to 25 and forward to 27.
- This post is intrinsically about Google, so the no-Google rule cannot apply literally. Keep product names, drop the `Google` tag, and rewrite the closing `說清楚 Google 能解決什麼` as a vendor-neutral principle (for example, "說清楚這個平台能解決什麼").

#### `fde-interview-guide-part3-ml-fundamentals-zh.md`
**Verdict:** rewrite/merge
- It is a condensed duplicate of part 8, as its own `閱讀建議` admits (it points readers to 8 and 9). Merge the FDE-specific bits (`四、Overfitting…LLM Fine-tuning 的版本`, `五、Fine-tuning 核心知識`, LoRA) into part 8 and retire this slot, or keep it as a one-screen index.
- The embedding table recommends `text-embedding-004` as the GCP default, which is stale (superseded by gemini-embedding-001; verify).
- Remove the `以 Google AI 工程師兼面試官的視角` description.

#### `fde-interview-guide-part4-system-design-zh.md`
**Verdict:** light edit
- One of the best Foundations posts. `設計決策二：RBAC 過濾的位置` (pre-filter vs post-filter and its effect on Top-K) and the role-aware cache key are exactly the non-obvious insight the standard asks for. Keep it.
- It has no series nav. Add prev (3) and next (5) links.
- The `設計決策一…四` blocks are already X-vs-Y decisions. Adding a one-line flip condition to each gets this post most of the way to the standard cheaply.
- Remove the Google-interviewer description, and swap the `Google` tag for `Cloud`.

#### `fde-interview-guide-part5-rag-deep-dive-zh.md`
**Verdict:** restructure
- The heading hierarchy is broken. Sections run `一、Chunking`, then unnumbered `Embedding 模型選擇`, `向量資料庫設計`, `混合搜尋`, `Reranking`, `Context Window Overflow`, then jump to `五、面試官地雷題`. Renumber them 一 to 八.
- It has zero ASCII diagrams. Hybrid Search + RRF + rerank is the obvious place for a flow diagram.
- The model table (`text-embedding-004`, `E5-mistral-7b` as "開源裡效果最好之一") is stale as of 2026. Refresh it, or date it and point to MTEB.
- A good tables-heavy reference. It re-covers part 1's chunking material, so open with "builds on part 1" and cut the re-intro.

#### `fde-interview-guide-part6-rag-eval-zh.md`
**Verdict:** light edit
- Headings are unnumbered after `四` (`小結`, `面試官地雷題`, `面試回答完整示範`). Renumber them.
- `成本估算範例` uses 1.5 Flash-era prices (`$0.000075/1K`) and claims `成本降 40-60%` with no source. Date the prices and label the estimate.
- A good diagnostic framing (the Context Recall vs Faithfulness split). The line `路由到較便宜的模型（Flash 而不是 Pro）` is a nice bridge to part 24; link it.

#### `fde-interview-guide-part7-agent-design-zh.md`
**Verdict:** light edit
- Solid. `二、Tool Routing` (the four-layer funnel from 20 tools down to top-5) and `四、Loop 終止：四種停滯模式` are genuinely useful.
- The next-post blurb describes part 8 as `Transformer、Embedding 與評估指標的工程視角`, which matches part 3's scope, not part 8's. Fix it.
- It overlaps part 2's `三、Multi-Agent` and part 14's memory types. Point readers forward instead of re-explaining.
- Remove the Google-interviewer description.

#### `fde-interview-guide-part8-ml-fundamentals-zh.md`
**Verdict:** light edit
- A clean classical-ML refresher (XGBoost, bias-variance, L1/L2, Transformer), and the right home for the merged part 3.
- It has no `面試情境` and no diagrams. A single Transformer block diagram in `六` would replace the prose description of the architecture.
- The ending `## 下一篇` is a bare heading. Replace it with the standard series-nav block.

#### `fde-interview-guide-part9-llm-core-zh.md`
**Verdict:** light edit
- `系列總結` ends with `*本系列已完結。如有特定主題想深入，歡迎留言。*`, and 40+ posts follow. Replace it with a pointer to part 10 and to the full series index.
- The scenario asks `為什麼選 text-embedding-004 而不是 OpenAI 的 embedding？`, which is stale and bakes an outdated choice into the question. Update the model, or generalise the question.
- The model table in `一` (`Gemini 1.5 Flash/Pro`, `Claude 3.5 Sonnet`, `GPT-4o` context windows) is stale.
- The series map in `系列總結` is a useful Foundations index. Keep it, extend it to cover the later tiers, and consider moving it to the series landing page.

### Top 5 highest-impact fixes in this batch
1. **Remove the employer and interviewer identity claim**: `我在 Google 做 AI 工程，也是面試官` (part 1) and the `以 Google AI 工程師兼面試官的視角` description in parts 1–9. It is an unverifiable trust claim, possibly NDA-sensitive, and it breaks the no-Google rule in the most visible spot (card descriptions). Then swap the `Google` tag for `Cloud` across all 26 posts.
2. **Collapse the duplicate pairs** (13+20, 14+18, 12+19, 3→8) into single standard-format posts with 三個演進階段 and 4–6 X-vs-Y decisions with flip conditions. That upgrades the series and removes the "same lecture twice" experience in one pass. Fix the Semantic/Episodic memory taxonomy clash while merging 14 and 18.
3. **Re-derive every cost and price claim against one dated price sheet.** Gemini 1.5, GPT-4o at $5, and text-embedding-004 underpin the headline numbers in 15, 18, 24 and 26 ("98.7%", "49%", the competitive price table). Fix the technically wrong 800-token context-cache example in part 18 and the 27× internal price contradiction in part 15.
4. **Repair the series spine.** Delete `本系列已完結` in part 9. Add nav to parts 4 and 26, and the missing forward link in part 15. Correct the mislabelled nav titles, and convert the `../slug/` links in parts 10–25 to `/posts/slug/`.
5. **Upgrade 16–25 to the standard**, since they already have the scenario-first shape. Remove every model-answer variant (`面試答題要點`, `面試回答完整示範`, SCOPE/DARK/CAPE `完整範例回答`), add the phase section, and correct the factual slips a sharp interviewer would catch: ThreadPool for CPU-bound work (22), the ADK `depends_on` registry presented as fact (22), the Pub/Sub ack deadline for hour-long tasks (21), the same-model judge contradicting part 12 (25), and the pre-OAuth-2.1 MCP auth model (17).
