## hugging-face (5), ollama-on-mac (5), knowledge-graph (5), crewai (3), langfuse (4) — 22 posts

### Series-level observations
- **Staleness is concentrated in model names and library signatures, not in concepts.** HF, KG and CrewAI all hard-code 2024-era defaults (`gpt-4o` / `gpt-4o-mini`, `Qwen2.5-*`, `Llama-3.1`, `torch_dtype=`, `cu121`). The HF series even labels its model table "（2026 年中）" (part2 §1.2) and still recommends Qwen2.5. None of this is wrong in principle, but a reader in Sept 2026 notices it on the first screen. The cheapest fix is one "版本基準" line per series (e.g. "tested with transformers x.y / TRL x.y / crewai x.y, 2026-0x") plus a find-and-replace of the default model IDs.
- **Numbers labelled "實測" have no source.** HF part2 §七 ("三種架構的實測對比"), part4 §4.4 / §5.4 / §九, and KG part3 §八 / part4 §八 / part5 §六 give precise latency, win-rate, cost and hallucination figures with no hardware, dataset, judge or date. Some are internally inconsistent (see HF part4). KG part5 §六 reuses part4's "~40%→~80%" and "~15%→~5%" row for row. Either add a one-line method note ("單張 A10G, 50 題自建測試集, GPT-judge, 2026-08") or relabel them "示意/估算".
- **Internal links break the house rule in two series.** Every langfuse and ollama post links siblings as `../<slug>/` (4–8 per post). CLAUDE.md requires root-absolute `/posts/<slug>/` so the render hook can resolve the page. It works today by accident of the URL shape, but it bypasses the `site.GetPage` check and will not survive a permalink change.
- **Punctuation and front matter are inconsistent within series.** ollama parts 1–4 and all four langfuse posts use half-width `,` `:` `?` inside Chinese prose (75–125 instances per post). ollama part5 uses full-width `，：` throughout. Neither ollama nor langfuse sets `series:` or `weight:`, while HF, KG and CrewAI do, so the tag and series pages cannot order them.
- **CrewAI is the outlier on quality.** It reads as older, generic, code-first tutorial content (63–82% code, no ASCII architecture, no decision tables). It uses `authors: ["YennJ12 Engineering Team"]`, which has no `content/authors/` slug (only `yen`, `sarah-chen`, `john-smith`, `alex-rodriguez` exist). It also contains two API-level errors a reader will hit (see per-post).
- **KG and langfuse are thin but coherent.** KG (238–323 lines) is a good conceptual primer whose code does not quite connect across parts. Langfuse (221–255 lines) uses the current v3 OTel SDK surface, which is correct, but stops exactly where production questions start: prompt caching and fallback, sampling and masking, self-host sizing, and how to wire evaluators into `run_experiment`. Neither series needs to hit 600 lines (no series standard applies), but each post has one missing section that a practitioner would expect.
- **HF and ollama are the strongest.** They are well-structured, full of concrete numbers, and have real decision tables and troubleshooting tables. What they need is maintenance, not rework.

### Per-post

#### `crewai-series-part1-introduction-zh.md`
**Verdict:** light edit
- Front matter: `authors: ["YennJ12 Engineering Team"]` has no matching `content/authors/` slug, so the author card is broken. Switch to `yen` (same for parts 2 and 3).
- The comparison table under "CrewAI vs 其他 Multi-Agent 框架" is stale. "LangChain Agents … 但單 Agent" ignores LangGraph, and the table has no OpenAI Agents SDK or Claude Agent SDK, which were the obvious 2026 alternatives. Add those and a "when not to use CrewAI" line.
- "執行結果解讀" shows a verbose log stamped `[2024-01-15 …]`. That dates the post to 2024 even though it is published in 2026. Regenerate the log with a current CrewAI version, or drop the timestamps.
- `llm="gpt-4o"` is the default everywhere. Pick a current default model once and mention the LiteLLM `provider/model` string format here rather than first in part3.
- The series nav promises part3 covers "結構化輸出", but that topic is actually in part2 (`output_pydantic`). Fix the nav text in all three posts.

#### `crewai-series-part2-real-world-tasks-zh.md`
**Verdict:** restructure
- **Title/code mismatch.** "場景二" is headed "系統設計：Hierarchical Process" and the diagram shows a Review Manager routing to reviewers, but the crew is built with `process=Process.sequential,  # 也可以改成 hierarchical…`. The 小結 then claims "多個專業審查員並行", yet there is no `async_execution` and no hierarchical mode. Either make it hierarchical (`manager_llm`, no `agent=` on tasks) or retitle it and drop the "並行" claim.
- At 82% code, each scenario repeats the same imports, `os.environ["OPENAI_API_KEY"] = "your-api-key"`, and Pydantic and Agent boilerplate. Keep one full listing (scenario 1) and show only the Agent/Task deltas plus the design decision for scenarios 2 and 3. That roughly halves the length and matches the 35 min → ~20 min readTime problem.
- "關鍵設計決策" only exists for scenario 1. Scenarios 2 and 3 have none. Add the cost and latency of a 3-agent run (tokens, $, seconds) so "生產級" in the description is backed by numbers.
- The best-practice line "一定要設 memory=True" is too strong. Memory adds embedding calls and cost, and it is not needed for stateless classification (scenario 3). Qualify it.
- The `# TODO: send email` at line ~423 is intentional (it is inside the sample diff). Keep it, and optionally note that it is part of the bait.

#### `crewai-series-part3-advanced-flows-zh.md`
**Verdict:** restructure
- **Likely broken API.** In "平行執行多個 Crew", `@listen(research_technical, research_market, research_regulatory)` with `def synthesize(self, tech, market, reg)` does not match CrewAI's Flow API. Joining on multiple methods uses `and_(...)`, and the listener receives a single output, reading the rest from `self.state`. Also check whether the three `@listen(begin)` methods actually run concurrently without being `async`. Verify all of this against the current docs and fix it; it is the section readers will copy.
- The Memory section imports `LongTermMemory, ShortTermMemory, EntityMemory` and `LTMSQLiteStorage` from internal paths. CrewAI's memory API has been reworked since early 2025. Verify it against the current release, and state the version tested.
- The FastAPI section (~150 lines of job-store and route boilerplate) buries the only non-obvious points: Crew `kickoff` is blocking, so use a worker or queue rather than `BackgroundTasks` at scale, and the in-memory `jobs` dict is lost on restart. Cut it to about 30 lines plus those two warnings.
- The cost section's `gpt-4o-mini: $0.15/1M input, $0.60/1M output` should be dated or replaced with a current model. `claude-sonnet-4-6` / `claude-haiku-4-5-20251001` are fine; verify they are still current.
- The series nav is present at the bottom despite the audit flag. The "系列總結" table is a nice close.

#### `hugging-face-part1-getting-started-zh.md`
**Verdict:** light edit
- A strong opener: the three-roles table, the VRAM formula and the six pitfalls are genuinely useful.
- **Version drift in 3.2.** `pip install "transformers>=4.44"` and the `cu121` wheel index are 2024-era. transformers v5 has shipped and deprecates `torch_dtype=` in favour of `dtype=` (used in §5.4). Verify, then update the pins and the kwarg across all five posts.
- The §3.3 statement that `huggingface-cli` "仍可使用但已標記為過渡" should be re-checked. Recent `huggingface_hub` releases print deprecation warnings and may have removed it; verify.
- §7.3's cost crossover ("A10G ≈ $750/月", "Serverless $0.2–0.6/1M") is exactly the kind of number that goes stale. Add "（2026-08 價格）" and a link to the Inference Providers pricing page.
- The cache-size table (Llama-3.1 / Qwen2.5 / Flux.1) could use current model names. The point stands either way.

#### `hugging-face-part2-use-and-push-models-zh.md`
**Verdict:** light edit
- **TGI status.** Hugging Face moved TGI into maintenance mode in late 2025 and points users to vLLM/SGLang (verify). §6.2 "vLLM vs TGI … 兩者差距在 2026 年已經不大，選團隊熟悉的那個" and the TGI Docker quick-start should say so. Otherwise readers pick a maintenance-only server.
- §1.2 "中文場景的實務建議（2026 年中）" lists Qwen2.5-7B/1.5B as the default pick. By mid-2026 the Qwen3 family, and likely its successors, are the obvious starting point. Update the IDs, or drop the date from the heading.
- The vLLM launch uses `python -m vllm.entrypoints.openai.api_server`. `vllm serve <model>` has been the documented entrypoint for a while, so switch to it.
- §七 "三種架構的實測對比" (P50 4,200 → 980 → 340 ms, $18.4 → $2.1 → $1.3) needs a method line. The "+ 語意快取 + 路由" column refers to components never built in this post (they appear only in the phase-3 diagram).

#### `hugging-face-part3-fine-tuning-zh.md`
**Verdict:** light edit
- **Copy-paste breaker.** In §五, `SFTConfig(max_seq_length=2048, …)` fails on current TRL, where the argument was renamed to `max_length` in 2025. The same name also appears in the §4.2 table and in the §5.2 OOM advice. Verify against the TRL version you pin, and pin it.
- §5.2 "降 max_seq_length（記憶體隨長度平方成長）" is wrong with the `flash_attention_2`/SDPA the same script enables, where activation memory grows roughly linearly. Reword it.
- The decision tree in §一 ("你真的需要微調嗎") and the catastrophic-forgetting regression set in §9.1 are the best parts of the series. Keep them.
- The printed `trainable params: 20,185,088 … 0.2643%` looks like a real output. That is good, but state the model and version it came from.

#### `hugging-face-part4-post-training-zh.md`
**Verdict:** light edit
- **Internal contradiction in §4.4.** The text says "β=0.01 的勝率最高（71%）", but the table shows β=0.05 at 74% (and β=0.1 at 72%). Fix the table or the sentence. This one undermines trust in all the "實測" tables.
- §5.4 and §九 present precise measured results (hours, GB, win rates, $1,900 → $4,100) with no methodology. Add a method note or mark them illustrative.
- The GRPO advice "KL 懲罰不要關。`beta=0.04`" goes against TRL's current default, which moved to `beta=0.0` following DAPO/Dr.GRPO findings (verify). Acknowledge the debate rather than calling it "最後一道保險".
- ORPO, KTO and CPO trainers have been moved or relabelled in recent TRL releases (verify that the import paths still work), and `max_prompt_length` has been dropped from some configs. Pin the TRL version at the top.

#### `hugging-face-part5-e2e-llm-app-zh.md`
**Verdict:** light edit
- A good capstone. The chunking → hybrid → rerank → refusal-gate progression is well argued, and §5.1's per-stage contribution table is the right shape. Just add its method.
- At 78% code, the FastAPI, Gradio and Docker Compose listings (§7.1–7.3) are mostly boilerplate. Collapse them into a repo link or a `<details>` block and keep the `--gpu-memory-utilization 0.75` warning, which is the non-obvious bit.
- `pickle.load` for the BM25 index is fine locally. Add a one-line warning to never load an index pickle from an untrusted source.
- The structure has an unnumbered "系列導航" after "十、系統效應與系列總結". That is fine, but mirror the other four posts' "十、系列導航" pattern or fold it in.

#### `knowledge-graph-part1-fundamentals-zh.md`
**Verdict:** light edit
- A clear primer; the triple, RDF vs property graph, and ontology flow works.
- The SQL example says "SQL 需要七次 JOIN" (repeated in part2 as "七重 JOIN"), but the query has six. Fix it in both posts.
- The history table lists "2007 Freebase" with no note that Freebase shut down in 2016. The "搜尋引擎知識面板… 5 億以上實體" claim is an old figure with no source.
- "八、面試／實務常被問到的觀念釐清" frames a non-interview series as interview prep. Rename it to "常見觀念釐清".
- readTime 20 min for 262 lines is inflated; about 12 min is right (applies to all five KG posts).

#### `knowledge-graph-part2-construction-zh.md`
**Verdict:** restructure
- **The demo pipeline does not connect.** NER (§三) and the rule-based extractor produce Chinese mentions (`諾蘭`, `全面啟動`). `canonicalize()` maps them to Wikidata QIDs, but the Neo4j loader (§六) ignores both and inserts hand-typed English names (`Nolan`, `Inception`). And with the five sample triples, the §七 Cypher answer to "諾蘭的電影裡有哪些演員也演過漫威" returns zero rows: DiCaprio has no Marvel film and RDJ has no Nolan film in the data. Add one triple (e.g. RDJ ACTED_IN Oppenheimer) and feed `canonicalize()` output into `MERGE ... {id: $qid}`.
- `spacy.load("zh_core_web_trf")` is trained on Simplified-Chinese OntoNotes. Say that Traditional-Chinese text degrades NER (or convert with OpenCC first). The printed output is marked "（示意）", so readers cannot tell what really happens.
- The loader builds labels and relation types with an f-string (`MERGE (s:{s_type} …)-[:{rel}]->`). That is fine for fixed data, but it is the same injection surface part4 §七 warns about. Add a whitelist check.
- The QA query `MATCH (a), (b) WHERE a.name CONTAINS b.name AND id(a) <> id(b)` is a full cartesian product and uses the deprecated `id()`. Use `elementId()` and scope the query by label.
- "這也是為什麼 Part 5 的消歧那麼重要" is misdirected: disambiguation is §四 of this post. Rephrase it.

#### `knowledge-graph-part3-comparison-zh.md`
**Verdict:** light edit
- The weakest-evidenced post in the series. §八's "四層股權穿透 8～30 秒 vs < 200ms" has no source, and "數量級的差異" is asserted.
- It is missing the most practical flip condition: when is Postgres enough? Recursive CTEs, Apache AGE, or pgvector plus a graph extension in one database. Also missing are multi-model options (Neo4j's own vector index, which part4 uses via `Neo4jVector`). Without these, the "四選一" framing oversells separation.
- The graph DB table (§六) omits FalkorDB and other 2025–26 entrants, and might note Kùzu's status (verify). Add a "last reviewed" date.
- "和四種常見的資料儲存技術正面比較" should say three: KG versus RDBMS, vector and document.

#### `knowledge-graph-part4-llm-graphrag-zh.md`
**Verdict:** light edit
- A good structure (failure mode → two paradigms → two implementations → grounding → security).
- **The §七 guard gives false confidence.** The regex blocks `CREATE|DELETE|…` but not `CALL apoc.*` write procedures, `LOAD CSV`, or `CALL {…} IN TRANSACTIONS`, and it rejects harmless string literals containing "set". Say plainly that the real control is a read-only role or a `READ`-mode session plus a timeout, and that the regex is only a speed bump.
- Name the current ecosystem: Microsoft GraphRAG's indexing cost, LightRAG, and Neo4j's `neo4j-graphrag` package as an alternative to LangChain chains. Readers in 2026 will have seen these.
- §八's table (~40% → ~80% multi-hop, 15% → 5% hallucination) is unsourced, and "數量級的改善" overstates a 2× gain.
- `ChatOpenAI(model="gpt-4o")` is dated; update it together with part5.

#### `knowledge-graph-part5-end-to-end-project-zh.md`
**Verdict:** light edit
- **Overclaim.** §六 lists "全域趨勢問題：可回答（社群摘要）" as a result of "本專案", but this project never implements community summarisation; it only uses Text2Cypher. Remove the row or add the missing step.
- The §六 figures duplicate part4 §八's. Differentiate them, or reference part4 instead of re-asserting.
- `LLMGraphTransformer` lives in `langchain_experimental`. Verify it is still maintained there in 2026, and mention `neo4j-graphrag`'s `SimpleKGPipeline` as the first-party path.
- The final skeleton (§七) keeps `allow_dangerous_requests=True` with only a comment. Show the read-only `Neo4jGraph` connection inline, since this is the "今天就能跑" copy.

#### `langfuse-intro-part1-concepts-zh.md`
**Verdict:** light edit
- The opening ("HTTP 200 but wrong") is a strong hook, and the data-model explanation is clear.
- Langfuse's observation model has grown beyond span, generation and event: newer SDKs add typed observations such as agent, tool, retriever, embedding and guardrail (verify). Mention that the "六個概念" are the core, not the whole list.
- Add one sentence on company and licensing status as of 2026 (ownership, MIT core versus enterprise features; verify), since the post leans on "開源 + 可自架".
- Fix the `../` links, add `series`/`weight`, and switch to full-width punctuation (applies to all four posts).

#### `langfuse-intro-part2-tracing-sdk-zh.md`
**Verdict:** light edit
- The code uses the current v3 surface (`from langfuse import observe, get_client`, `start_as_current_observation`, `langfuse.langchain.CallbackHandler`), which is good. State "Python SDK v3.x" explicitly, since most blog posts online still show v2 `langfuse.decorators`.
- Check the env var: v3 docs used `LANGFUSE_HOST`, and `LANGFUSE_BASE_URL` may be newer (verify which one the pinned SDK reads).
- The thin spot: there is no "trace 沒出現怎麼辦" troubleshooting (missing flush, wrong region host, OTel exporter conflicts with an existing tracer provider) and nothing on sampling or masking PII before it leaves the process. One short section on each would make this more than the quick-start docs.
- §六's "為什麼選 X 不選 Y" is really a "which integration for which situation" table. Fine, but rename it.

#### `langfuse-intro-part3-evaluation-zh.md`
**Verdict:** light edit
- **Missing key code.** §五 runs `dataset.run_experiment(name=…, task=my_app)` with no evaluators. The side-by-side table that follows (faithfulness 0.81 → 0.91) cannot be produced from the code shown. Add the `evaluators=[...]` function signature and one example evaluator.
- The LLM-as-a-Judge section is UI-only. Add the judge's cost ($ per 1K traces at a given model) and a sampling-rate recommendation, which is the real decision teams face.
- The "gpt-4o vs gemini-2.5-flash" example names should be updated or kept generic.

#### `langfuse-intro-part4-monitoring-prompt-management-zh.md`
**Verdict:** light edit
- **Missing production behaviour for prompt management.** It covers no client-side caching or TTL, no `fallback=` when Langfuse is unreachable, and no latency cost of `get_prompt()` on the hot path. That is the first question any reviewer asks before moving prompts out of code.
- "把 prompt 連結到 Generation：閉環的最後一塊" is called "最關鍵的整合" but shows no code. Add the one-liner that attaches `prompt_obj` to the generation (verify the v3 parameter name).
- "配合告警，異常時主動通知" — verify what alerting Langfuse offers natively versus via webhooks/exports. Don't imply a feature the platform may not have.
- The closing flywheel is a good series wrap. Add a "下一步" pointer to self-hosting or the HF/ollama posts for cross-series flow.

#### `ollama-on-mac-part1-installation-zh.md`
**Verdict:** light edit
- The cost comparison in §一 prices "GPT-4 級別" at $10/1M tokens, arriving at "$200+/月, 一年省下的錢遠超過一台 Mac". In 2026 a mini-class API model costs a few dollars a month for the same 22.5M tokens, so the argument is misleading. Compare against a mini-class price, or make the argument about privacy and offline use rather than cost.
- "第一個 token 通常在幾十毫秒內" is only true for tiny prompts. A 1,500-token prompt on an 8B model takes over a second of prompt eval on most Macs. Qualify it.
- `ollama version is 0.5.7` dates the post to early 2025. The macOS app has since gained its own chat window and settings (network exposure, context length), and the post describes it only as a menu-bar server. Refresh §三/§四 against the current app (verify).
- `llama3.2` as the first model is fine for speed, but part2 recommends `qwen3:8b` for Chinese readers. Mention it here too.
- The title "ollama on mac - part 1 - …" is lowercase with hyphens, unlike every other series. Consider "Ollama on Mac（一）：安裝與第一個本地模型".

#### `ollama-on-mac-part2-public-models-zh.md`
**Verdict:** light edit
- "截至 2026 年中… 六大主流開源家族" omits OpenAI's `gpt-oss` (20B fits 16GB Macs), which is one of the most-pulled Ollama models since Aug 2025. It also misses the newer Qwen3 variants (qwen3-coder, qwen3-vl) and Gemma 3n. The coding row still recommends `qwen2.5-coder` and `deepseek-r1:7b` (a reasoning distill, weak at code). Refresh the §二 and §六 tables.
- The Mistral row shows vision ❌, but Mistral Small 3.x has vision. Verify the capability columns.
- The decision tree, the RAM table and "Q4 大一號 > Q8 小一號" are excellent. Keep them.

#### `ollama-on-mac-part3-api-modelfile-zh.md`
**Verdict:** light edit
- **Possible copy-paste error.** `"keep_alive": "-1"` (string) in §8.1: Ollama parses string values as Go durations, and "-1" has no unit. Use the number `-1` or `"-1m"` (verify).
- The §5.1 note that the `num_ctx` default is "常為 2048/4096" should be re-checked. Ollama's default context has changed across 2025 releases and the app now exposes a context slider (verify).
- §九 (Modelfile) is the most distinctive part. The Taiwanese persona example is good local flavour.
- This post has no decision table while its siblings do. Add a small "generate vs chat vs OpenAI-compat" or "format:json vs JSON Schema" X-vs-Y with a flip condition.

#### `ollama-on-mac-part4-app-integration-zh.md`
**Verdict:** light edit
- The "OpenAI 相容層" section and the env-var switch between cloud and local are the most practical content in the series.
- The embedding default `nomic-embed-text` is dated. Mention the newer `qwen3-embedding` / `embeddinggemma` and their dimensions, since the RAG section hard-codes 768.
- "LM Studio 風格的客戶端" is vague. Name one or two clients or drop the bullet. Also check that Enchanted is still maintained (verify).
- The Continue config JSON format has changed (YAML config in newer versions; verify). Add a version note.

#### `ollama-on-mac-part5-advanced-zh.md`
**Verdict:** keep as is
- The best post in the series: the "模型不執行工具" framing, the agent loop with `max_steps`, the security table for `0.0.0.0`, and the symptom → cause → knob table are all practitioner-grade.
- Minor: `launchctl setenv` does not survive a reboot, so mention the app's settings UI or a LaunchAgent plist. It is also the only post in the series with full-width punctuation, so align the other four to it rather than the reverse.

### Top 5 highest-impact fixes in this batch
1. **Fix the copy-paste breakers.** These are TRL `SFTConfig(max_seq_length=…)` (HF part3), CrewAI `@listen(a, b, c)` with a three-argument listener (CrewAI part3), Ollama `"keep_alive": "-1"` as a string (ollama part3), and the KG part2 demo whose Cypher returns zero rows and never uses the canonical IDs it computes. These are what readers actually run.
2. **Source or relabel every "實測" table.** Covers HF part2 §七, part4 §4.4/§5.4/§九, and KG parts 3–5 §八/§六. Start with the HF part4 §4.4 contradiction (text says β=0.01 has the top win rate, the table says β=0.05) and the KG part5 claim of community-summary results that the project never builds.
3. **Do a staleness pass on defaults.** Replace `gpt-4o`, Qwen2.5 and Llama-3.1 defaults. Note TGI's maintenance status in HF part2 and add `gpt-oss` and the newer Qwen3 variants to ollama part2. Update the transformers `torch_dtype` → `dtype` kwarg. Add one "tested with version X, date" line per series.
4. **Rework CrewAI part2/part3.** Make the "Hierarchical Process" scenario actually hierarchical (or retitle it), cut the repeated boilerplate by about half, verify the Memory imports against the current release, and fix `authors:` to `yen` in all three posts.
5. **Tidy links and front matter for ollama and langfuse.** Replace `../slug/` links with `/posts/slug/`, add `series:`/`weight:`, and standardise on full-width punctuation. In the same pass, add the one missing production section to langfuse (prompt caching/fallback in part4, evaluators in part3 `run_experiment`).
