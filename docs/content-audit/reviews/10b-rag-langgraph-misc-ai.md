## rag-series (5), chatpdf-rag (3), ai-accuracy-evaluation (3), cloudflare-security-audit (3), langgraph (6), llm-post-training, google-gemini-local-mac, hermes-agent, harness-engineering, nvidia translations (2) — 26 posts

### Series-level observations
- **Two groups of different quality.** The May–June series (rag-series, ai-accuracy-evaluation, chatpdf-rag, cloudflare) are coherent, cross-linked and mostly accurate. Ten posts all dated `2026-04-11T10:00:00+08:00` (the six langgraph posts, gemini, hermes, harness), plus the two nvidia posts, share one generated template: English-style `summary` in place of `description`, star and rocket emoji ratings (⭐⭐⭐⭐ / 🚀🚀), unsourced "目標值" performance tables, a closing line like 「現在就開始…吧！」, and mainland terms written in traditional characters (`數據`, `代碼`, `信息`, `質量`, `內存`, `默認`, up to about 20 per post) where the rest of the blog uses 資料 / 程式碼 / 品質 / 記憶體. Most of the batch's reader-trust problems are in this group.
- **API rot is concentrated in the April batch.** It uses `claude-3-5-sonnet-20241022` (retired), `langchain.memory.ConversationBufferMemory` and `LLMChain` (both moved to `langchain-classic` in LangChain 1.0), `from langgraph.checkpoint import MemorySaver` (wrong path, should be `langgraph.checkpoint.memory`), TRL `tokenizer=` / old `PPOConfig(model_name=…)`, and `bitsandbytes` `load_in_4bit` on a Mac. Readers who copy and paste will hit errors, not just old versions.
- **What makes rag-series distinctive.** `fde-interview-guide-part1-rag`, `part5-rag-deep-dive`, `part6-rag-eval` and `ai-eng-from-scratch-phase11-part2-rag-evals` have **zero Python blocks**. They cover architecture and tradeoffs (RRF, RAGAS, cost). rag-series is the only **runnable, single-stack (OpenAI + Chroma) code walkthrough** on the blog, and the only place that implements HyDE, Step-Back, Query Decomposition, Self-RAG, GraphRAG and Agentic RAG. That is its niche, so keep it. But it should say so in part 1 and link out to the fde / ai-eng posts for the "why" and to chatpdf for a real-project case study. Today none of the four RAG series references another.
- **Internal overlap to resolve.**
  - `rag-series-part5` "Part 1：RAG 評估——RAGAS 框架" and `ai-accuracy-evaluation-part3` "三、RAGAS" were published two days apart. They use the same four metrics, the same legacy `ragas.metrics` imports and the same `Dataset.from_dict` code.
  - `rag-series-part3` Multi-Query / Hybrid overlaps `chatpdf-part1` §六 and `chatpdf-part2` §五.
  - They also fuse differently: rag-series uses RRF, chatpdf uses min-max + alpha. Neither explains why. That comparison is the missing paragraph that would make each series cite the other.
- **RAGAS code is stale in three posts** (`ai-accuracy-evaluation-part3`, `rag-series-part5`, and conceptually `chatpdf-part3`). They use the 0.1-era `question/answer/contexts/ground_truth` + `datasets.Dataset` shape. Current RAGAS uses `EvaluationDataset` / `SingleTurnSample` with `user_input/response/retrieved_contexts/reference`. Verify against the installed version and update once for all three.
- **Front-matter hygiene.**
  - Posts by `authors: ["YennJ12 Engineering Team"]` (rag-series, ai-accuracy) all carry a `繁體中文` tag, which is a language marker, not a topic.
  - The April batch uses `summary:` only. The fallback in `head.html` covers SEO, but these posts should get a real `description`.
  - The chatpdf series uses relative `../slug/` links instead of the house `/posts/slug/` form.

### Per-post

#### `ai-accuracy-evaluation-part1-zh.md`
**Verdict:** keep as is
- A clear, well-paced primer. The 97.5% accuracy / 62% precision fraud example is the right hook.
- Optional: add a PR-curve / threshold paragraph. The post implies precision and recall are fixed, but in practice you move the threshold. One diagram of threshold vs P/R would add the actionable piece.

#### `ai-accuracy-evaluation-part2-zh.md`
**Verdict:** light edit
- The "知名的 LLM 評估基準" table (MT-Bench, MMLU, HumanEval, TruthfulQA) is 2023-era and mostly saturated or contaminated by 2026. Say so, or name what practitioners actually track now (verify: SWE-bench Verified, GPQA, LiveBench, Arena).
- The "四、LLM-as-a-Judge" pitfalls list position bias, self-preference and score drift, but give no numbers. The standard advice (swap order, ≥2 judges, calibrate against ~100 human labels, report agreement %) would give the section a concrete target.
- The `judge_response` code uses `gpt-4o`. That is fine as an example, but pin it as "e.g." rather than as a recommendation.

#### `ai-accuracy-evaluation-part3-zh.md`
**Verdict:** light edit
- Update the RAGAS snippet (§三「快速上手」) to the current `EvaluationDataset` API. The printed output `{'faithfulness': 0.97, …}` is presented as "輸出範例" with no run behind it, so label it illustrative.
- `claude-sonnet-4-6` in §「使用自定義 LLM 作為評審」: verify it is a current model ID. `LangchainLLMWrapper` may also be superseded by `llm_factory` in newer RAGAS.
- Deduplicate against `rag-series-part5` Part 1: keep the deeper treatment here (calibration, diagnosis matrix, human rubric are unique) and have rag-series link here.

#### `chatpdf-rag-optimization-part1-chunking-retrieval-zh.md`
**Verdict:** light edit
- The strongest RAG content in the batch: real PR, real code, a decision table with flip conditions. But §八 "系統效應" reports only test counts. The post says it added `rag_evaluation.md` (Hit@k, MRR, nDCG), yet shows no before/after retrieval numbers. One row of "Hit@5: x → y on N questions" would turn a claim into evidence.
- `HybridRetriever.search` scores the **entire corpus** with both dense and BM25 on every query (`self._vs.query(doc_ids, query, len(corpus))`). The flip condition mentions this, but it says the LRU cache in PR #2 fixes it. That cache stores BM25 objects; it does not add an inverted index. Correct the claim.
- Mixed half-width punctuation in headings (`二、固定切塊的問題:把意思切碎了`). Normalise to full-width ：，().
- Change `../chatpdf-rag-optimization-part2-…/` links to `/posts/…/`.

#### `chatpdf-rag-optimization-part2-backend-hardening-zh.md`
**Verdict:** light edit
- Test counts contradict each other: the intro box says "165 測試,+30 新增", §十 says "後端 195 測試全綠", and part 1 said 128. Reconcile.
- §十 row "檢索召回 | 單一查詢 → 多查詢擴展,recall 提升" has no number, and the same goes for min_score. The series standard is numbers; give recall@k or say "not measured".
- Eleven sections (十一、小結). Fold 小結 into 十 or merge §五–§八 ("進階 RAG 之一…之四") into one section with four subsections.

#### `chatpdf-rag-optimization-part3-observability-eval-zh.md`
**Verdict:** keep as is
- Good. The judge-prompt brace-escaping bug (§六) and "relevance gate never empties" (§五) are practitioner-grade details you won't find in docs.
- Minor: link `ai-accuracy-evaluation-part3` for the metric definitions instead of re-explaining faithfulness/relevance.

#### `cloudflare-security-audit-skill-part1-pipeline-zh.md`
**Verdict:** light edit
- Line 20: "Cloudflare 在 2024 年開源了 security-audit-skill". The "skill" packaging format postdates 2024. Verify the date and repo URL. This is the post's anchor fact.
- There is no quote or link to specific files in the repo (SKILL.md, prompts, schema). Everything is paraphrase, so readers can't tell the repo's design from the author's interpretation. Link 3–4 exact files and quote one prompt line per phase.
- §三 "Sub-Agent Spawning", §四 "五個驗證測試 / 去重" and §五 schema are all repeated in more depth in part 2. Trim these to a one-paragraph teaser plus a link, so part 1 stays the map.

#### `cloudflare-security-audit-skill-part2-agent-design-zh.md`
**Verdict:** restructure
- Roughly half of this post re-explains part 1 (Agent 數量決策矩陣, Sub-Agent Spawning, 五個 Validation 測試, 去重, findings.json). Keep the parts only this post has, the §三 attacker-reading table and §五 adversarial validation, and cut or shorten the rest.
- §八 has a real tradeoff table ("代價" column + 翻轉條件), which is good. The "單次 run ~50% 覆蓋率" figure needs a source (repo README?) or should be removed.

#### `cloudflare-security-audit-skill-part3-llm-security-zh.md`
**Verdict:** keep as is
- The most original post of the three. The ten anti-patterns generalise beyond this repo and read well.
- Optional: §八 "給工程師的實踐建議" could end with a copy-pasteable checklist or prompt snippet. That is the one takeaway readers will want to keep.

#### `google-gemini-local-mac-zh.md`
**Verdict:** rewrite/merge
- The title promises "Google Gemini 4 模型" but Gemini is not open-weight. The body is about Gemma, and specifically **Gemma 1** (`gemma:7b`, `google/gemma-7b-it`). "Gemini Flash（非官方蒸餾）" and "Nous Hermes / Mistral / Phi-3 as 第三方蒸餾版本" of Gemini are fabricated framings. Retitle to "在 Mac 本地運行 Gemma" and update to the current Gemma generation (verify: Gemma 3 / 3n or later).
- There are several factual errors a Mac user will hit:
  - "Mac mini M1/M2 2GB RAM" does not exist; the minimum is 8GB.
  - "Gemma-27B …需要 GPU" makes no sense on unified memory.
  - `load_in_8bit` / `load_in_4bit` rely on bitsandbytes, which is CUDA-only.
  - `LLAMA_METAL=1 make` and `./main` are obsolete (llama.cpp now uses CMake, Metal is on by default, and the binary is `llama-cli`).
  - "Q8_K" should be `Q8_0`.
  - The "生產部署" section uses `systemctl` on macOS.
  - `ollama.ai` should be `ollama.com`.
- "零延遲和成本 / 無限制使用" in 總結 is marketing copy. Replace it with measured tokens/s on a named Mac.
- If kept, tag it `tools` rather than just `ai`.

#### `harness-engineering-intro-ai-zh.md`
**Verdict:** consider retiring
- Slug and title collide with "harness engineering", the 2026 term for designing **agent harnesses** (the Claude Code / Codex sense). The post is about the Harness.io CD vendor. Readers arriving from search get the wrong topic.
- The pipeline YAML is not Harness's real schema (real pipelines use `identifier`, `type: CI/Deployment`, `spec.execution.steps`, `type: Run`), so none of it can be imported.
- Value-claim tables ("部署時間縮短 50-75%", "灰度部署降低故障率 90%", "<2 分鐘") have no source.
- If a Harness.io post is wanted, rewrite it against real docs under a `harness-io-…` slug, and consider writing the agent-harness post under this slug.

#### `hermes-agent-intro-installation-zh.md`
**Verdict:** rewrite/merge
- The "區別於其他系統" table marks Claude and ChatGPT ❌ for 長期記憶, 自動化任務 and 創建技能, and marks Hermes ✅ for 本地運行 even though its own config calls OpenRouter. All of this is false or misleading in 2026. Delete the table or make it fair.
- The install steps (`npm install` + `pip install -r requirements.txt`, `hermes start`, `hermes reset --skills`) and the `hermes setup` wizard contents look invented. Verify every command against the NousResearch repo before republishing.
- Models are Hermes-3 / Mixtral-8x7B / "GPT-4". Update to the current Hermes generation (verify: Hermes 4).
- "Q: 數據安全嗎？ A: 完全安全" is an unqualified claim. Prompts go to whichever API provider is configured.

#### `langgraph-ai-backend-architecture-zh.md`
**Verdict:** restructure
- Missing opening: it starts straight at `## 單體應用架構` with no reason to care, and has no `description`.
- The four topologies (線性/並行/循環/樹形) are the real content, but each is generic code without numbers on when a topology is worth its cost. The "架構選擇指南" table ("高流量 → 微服務") has no QPS thresholds.
- Much of the persistence, retry and monitoring code repeats `core-code` and `customer-ticket-system`. Cross-link instead of re-pasting it.
- readTime is roughly double what it should be (40 min for 548 lines).

#### `langgraph-ai-backend-core-code-zh.md`
**Verdict:** rewrite/merge
- About 90% code. It is a full project dump (schemas, config, SQLAlchemy, docker-compose with `prom/prometheus:latest`) for the **same ticket system** as `langgraph-ai-customer-ticket-system-zh`. Merge the two, and keep only the non-obvious pieces (state reducer, checkpointer wiring, error edges).
- The code does `json.loads(response)` on raw LLM text, and the prompt's example JSON (`"confidence": 0.0-1.0`) is not even valid JSON. "生產級" code should use `with_structured_output`.
- Uses `claude-3-5-sonnet-20241022` (retired). The closing line "現在你可以直接基於這個範本快速構建" is not supported by the code.

#### `langgraph-ai-backend-ideas-zh.md`
**Verdict:** consider retiring
- Ten "生產級案例" share one template (`### 應用場景 / ### 工作流設計 / ### 核心實現`) with dataclass boilerplate. None has numbers, a real deployment or a reason why LangGraph beats a plain queue + LLM call. "LangGraph" appears only 9 times in 994 lines.
- `from langchain.chains import LLMChain` has been removed in LangChain 1.0.
- If kept, cut it to a one-screen table (use case → graph shape → key node) and link out to the architecture post.

#### `langgraph-ai-backend-logic-zh.md`
**Verdict:** restructure
- The best idea in this group is §「決策邏輯的可測試性」 (unit-testing router functions). Lead with that.
- The "邏輯複雜度分析" table assigns Big-O to routing styles ("AI 輔助決策 O(1)", "複雜並行 O(n²)"), which is not meaningful. Replace it with latency and cost per decision type (for example, an LLM router adds ~300–800 ms and $x per call; a rule router adds ~0 ms).
- No opening hook and no description. It overlaps `architecture` §Agent 拓撲 and the intro's routing section.

#### `langgraph-ai-customer-ticket-system-zh.md`
**Verdict:** restructure
- Should become the single canonical LangGraph walkthrough, absorbing `core-code`.
- The "性能指標" table (分類準確率 >95%, 首次解決率 >70%, <$0.1/工單) is labelled 目標值 but reads like results. Either show how you measured it or say these are targets.
- Uses `claude-3-5-sonnet-20241022` (retired), and 「質量」 appears 12 times where the house term is 品質.

#### `langgraph-langchain-intro-zh.md`
**Verdict:** rewrite/merge
- The API is pre-LangChain-1.0 and will break when copied:
  - `ConversationBufferMemory` / `ConversationSummaryMemory` (§Memory)
  - `from langgraph.checkpoint import MemorySaver` (wrong module)
  - `ChatAnthropic()` with no model
  - `claude-3-5-sonnet-20241022` / `gpt-4-turbo`
  
  Rewrite it against LangChain/LangGraph 1.x (`create_agent`, `langgraph.checkpoint.memory.InMemorySaver`, messages-state memory).
- The summary table says LangGraph's 結構 is "DAG 圖結構". LangGraph's reason to exist is **cycles** (agent loops), so that is the one concept a newcomer must get right.
- There are two closing sections (`## 總結` then `## 何時使用`). Merge them, and add an opening that explains why to read this rather than the official quickstart.
- This should be part 0 of the langgraph set. Add a series nav across all six posts, which currently have none.

#### `llm-post-training-approaches-open-source-zh.md`
**Verdict:** restructure
- There is no GRPO / RLVR section. Since 2025 (the DeepSeek-R1 era) that is the most-used open-source RL post-training method, and the title's "從 SFT 到 RLHF" arc is incomplete without it. Add a 方法 section and a row in 全方法橫向比較.
- The TRL code is out of date: `tokenizer=` is now `processing_class=`, and `PPOConfig(model_name=…, optimize_cuda_cache=…, early_stopping=…, target_kl=…)` with `AutoModelForCausalLMWithValueHead` is the removed v1 API. Update the code, or state the pinned TRL version.
- Examples use Qwen2.5. Update to the current Qwen generation (verify: Qwen3).
- The comparison matrix is all qualitative (中/高). Add GPU-memory and wall-clock numbers for a 7B model (e.g. LoRA SFT on 1×24GB, full DPO on 8×80GB).
- 14 tags is a keyword dump. Cut to about 6.
- The summary says "手把手帶你訓練 Qwen", but there is no end-to-end run or eval result.

#### `nvidia-minimax-m27 advances scalable-agentic-workflows-on-zh.md`
**Verdict:** consider retiring
- This is not a translation but a hallucinated summary. "NVIDIA 最近發布的 MiniMax M2.7" gets the vendor wrong (MiniMax is the model developer). `from minimax import MiniMaxModel` / `model.initialize(use_nemoclaw=True)` is invented code. The NemoClaw description is generic filler. Every section (導論/核心概念/…/常見問題) is template padding, e.g. "Q: 如何解決數據不足？A: 使用 Generative AI 生成更多的訓練數據".
- `authors: ["Anu Srivastava"]` credits a real NVIDIA author with text they did not write. That author slug doesn't exist here, and the misattribution is a trust problem.
- The filename contains U+00A0 non-breaking spaces, which produce a `%C2%A0` URL.
- Delete the post. If the RSS pipeline continues, `generate_nvidia_blog.py` needs to translate the article body, not generate from the title.

#### `nvidia-running-large-scale-gpu-workloads-on-kubernetes-wi-zh.md`
**Verdict:** consider retiring
- Same failure. It never mentions the actual subject of the source article (Slurm-on-Kubernetes operator; verify: Slinky).
- The code is wrong: a `kind: Node` manifest with `spec.resources.limits` is not valid Kubernetes, and Slurm `slurm.conf` lines appear in a ```yaml fence.
- `authors: ["nvidia-auto"]` and readTime "25-30 min" for 79 lines.
- It adds nothing beyond the linked source. Delete it.

#### `rag-series-part1-foundations-zh.md`
**Verdict:** light edit
- A solid, runnable entry point. Add a paragraph saying what this series is: hands-on code on a single OpenAI + Chroma stack. Link to `fde-interview-guide-part1-rag-zh` / `ai-eng-from-scratch-phase11-part2-rag-evals-zh` for architecture, and to `chatpdf-rag-optimization-part1` for a real-project case.
- Part 5's own 黄金法則 #1 is "先建立評估，再優化", yet evaluation arrives last. Add a 10-line "measure hit@k on 20 questions" step here so every later part can show before/after numbers.
- `gpt-4o-mini` / `text-embedding-3-small` are fine but aging. Centralise model names in one constant and note the date.

#### `rag-series-part2-chunking-vectordb-zh.md`
**Verdict:** light edit
- The description promises "主流向量 DB 的實測比較", but the body has feature descriptions and pricing, not measurements. Either run a small benchmark (latency and recall at 100K vectors) or reword the description.
- The strategy comparison table lacks numbers (recommended chunk size, overlap %, when semantic chunking pays off). `chatpdf-part1` has the percentile-threshold detail; link it.
- Check Pinecone pricing and `ServerlessSpec` region claims for staleness (verify).

#### `rag-series-part3-advanced-retrieval-zh.md`
**Verdict:** light edit
- Uses RRF for hybrid fusion, while `chatpdf-part1` uses min-max + alpha. Add a 3-line "RRF vs weighted fusion, and when each wins" note (the flip condition is: RRF when score scales are unknown or unstable; weighted when you want a tunable knob).
- The 小結 table's "延遲增加：低/中/中高" should be ms (e.g. a cross-encoder at 20 docs ≈ 50–200 ms on CPU).
- The GPT-4o "128K context window" example is fine as illustration but dated. Consider a neutral model name.

#### `rag-series-part4-optimization-zh.md`
**Verdict:** light edit
- The "Self-RAG" here is a prompt-based approximation. The original Self-RAG is a fine-tuned model with reflection tokens. Say so in §「簡化版 Self-RAG 實作」 so readers don't think this is the paper's method.
- The series nav names this post "查詢優化與 Context 壓縮", but the title is "查詢轉換、Self-RAG 與 Context 壓縮". Align them in all five navs, and add GraphRAG to part 5's nav label.
- 77% code. §「組合使用：完整的進階 RAG Pipeline」 re-pastes earlier functions; replace that with a call-sequence diagram and latency/cost per stage.

#### `rag-series-part5-production-zh.md`
**Verdict:** restructure
- The RAGAS section duplicates `ai-accuracy-evaluation-part3`, with the same stale API. Shrink it to a summary plus a link and spend the space on what's unique here: GraphRAG and Agentic RAG.
- GraphRAG is a hand-rolled toy (entity extraction via prompt). Name the real options (Microsoft GraphRAG, LightRAG, Neo4j) and give their indexing cost (LLM calls per chunk), since cost is the main reason GraphRAG gets rejected.
- The Agentic RAG LangGraph code should use current `create_agent` / prebuilt patterns and link the langgraph posts once those are fixed.
- The mechanical audit flagged series-nav missing, but a nav exists at the bottom. The problem is the label mismatch noted in part 4.

### Top 5 highest-impact fixes in this batch
1. **Delete the two `nvidia-*` posts.** They are hallucinated content attributed to real NVIDIA authors, contain fake code, and one has an NBSP filename. Also fix `scripts/generate_nvidia_blog.py` so it translates the article body, or stop publishing its output.
2. **Collapse the six April langgraph posts into a numbered 3-post series.** Suggested: intro (rewritten for LangChain/LangGraph 1.x), ticket-system walkthrough (absorbing `core-code`), and architecture + logic patterns. Retire `ideas`. Add real descriptions, correct readTimes, a series nav and house terminology (資料/程式碼/品質).
3. **Fix the factually wrong Mac/Gemini and Hermes posts, or retire them.**
   - Gemini → retitle as Gemma and correct the Mac-specific errors (2GB M1, bitsandbytes, systemd, llama.cpp flags).
   - Hermes → delete the false ChatGPT/Claude comparison and verify every install command.
   - Harness → retire, or rename away from the "harness engineering" slug collision.
4. **Deduplicate and cross-link the four RAG series.**
   - rag-series is the code track, fde / ai-eng is the architecture track, chatpdf is the case study, ai-accuracy-part3 is the canonical RAGAS reference.
   - Update the RAGAS snippets once to the current `EvaluationDataset` API.
   - Add the RRF vs min-max fusion note to both rag-series-part3 and chatpdf-part1.
5. **Add GRPO/RLVR and current TRL APIs to `llm-post-training-approaches-open-source-zh`.** It is the only post-training overview on the blog and is missing the dominant 2025–26 method. Its PPO code targets a removed API.
