# B09 — ai-eng-from-scratch phases 11–14 (10 posts)

Files: `content/posts/ai-eng-from-scratch-phase{11,12,13,14}-part*-zh.md` (6,151 lines total).
Mechanical baseline (`docs/content-audit/inputs/mechanical-baseline.txt`): one entry — `phase11-part2-rag-evals-zh.md:630: warning: section 「十一」 exceeds the 十-section cap`. Re-run of `scripts/review_posts.py` on the batch: **0 errors, 1 warning** (the same one). No hard-coded baseURL; every series-nav target exists (`phase10-part3`, `phase15-part1` both present). Plan coverage (`AI_ENG_FROM_SCRATCH_PLAN.md` L138–154): the 2/2/2/4 split matches exactly, but all ten files are still listed as ⬜ Not Started.

## Batch summary

All ten posts follow the fde-interview-guide template that `AI_ENG_FROM_SCRATCH_PLAN.md` L68–75 now calls optional: a 「工程情境」 interviewer question (every file, L19–24), a 「二、三個演進階段」 ladder, six 「為什麼選 X 不選 Y」 tables and a 「九、系統效應」 before/after table. Compared with B07/B08 the batch is better hedged — every 系統效應 table carries a 示意估算 label, and 14-2 even disclaims its whole §九 up front — but the hedging is cosmetic in the two posts that get the core wrong. 11-1 states the 70B KV cache as 0.8 MB/token at L37 and 3.1 MB/token at L144, mis-multiplies its own formula (2×80×64×128×2 = 2,621,440, not 3,276,800), ignores that Llama-2-70B is GQA (0.33 MB/token), and attributes vLLM's 24× figure to TGI (the blog says 24× vs HF, 3.5× vs TGI); its cost column at L444 cannot be derived from its own throughput row and $3.09/GPU-h. 12-1 gives ViT-L/16 87.76 % to ImageNet-21k pre-training (that is the JFT-300M number; I21k is 85.30 %), quotes Flamingo's fine-tuned VQAv2 82.0 as "16-shot", prices the same A100 at $0.625, $1.25 and $0.625/h in three places, and computes 12 → 71 as +525 % (it is +492 %). The other eight are "Needs revision" for the same reason as B08: percentages labelled 實測 or 實際測試 with no experiment behind them (12-2 L345 "100 次任務實測", 13-2 L669 "實際測試數字：QPS 450 vs 95", 14-1 L350/L397/L542 "實測最佳"), one wrong API call per post (13-1 L411 `server.send_progress` does not exist in the MCP Python SDK — the real call is `ctx.report_progress(progress, total, message)`; 14-1 L377 inline `INDEX (...)` is MySQL syntax in a table labelled PostgreSQL), fictional model versions (14-4 L49/L265 `gpt-4o-2025-05`), and small arithmetic slips (14-4 L34 $350 should be $400, L454 a 0.5 token/s bucket is 30 req/min not 10). The technical cores that *do* hold are worth keeping: 13-1's OpenAI function-calling lifecycle and MCP request catalogue, 13-2's LCEL/Workflow code, 14-1's refund state machine and four-layer memory, 14-4's four-layer budget model with the `INCRBYFLOAT` race fix, and 14-2's replanner decision tree. Verdicts: 0 Ready, 8 Needs revision, 2 Not ready (11-1, 12-1).

## Per-post scorecard

Scores: A accuracy, C clarity, D depth, V visuals, S structure, F format (1–5); Overall = plain mean (no finance posts).

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| phase11-part1-inference-serving | 467 | 2 | 4 | 3 | 4 | 3 | 4 | 3.3 | **Not ready** | L144 "2 × 80 × 64 × 128 × 2 = 3,276,800 bytes ≈ 3.1 MB/token" — the product is 2,621,440; Llama-2-70B has 8 KV heads (GQA) so the real figure is 327,680 B ≈ 0.33 MB, and L37 already said 0.8 MB. L200 "對比 HuggingFace TGI 吞吐量提升 24×" — the vLLM blog says 24× vs HF Transformers and 3.5× vs TGI |
| phase11-part2-rag-evals | 717 | 3 | 4 | 4 | 4 | 3 | 3 | 3.5 | Needs revision | L210–211 "總計 P95 ~750ms（無 Re-rank）/ ~1,800ms（含 Re-rank）" — the P95 column of the table at L219–224 sums to 1,265 ms / 1,385 ms; +80 ms of re-rank cannot add 1,050 ms. Also L630 「十一」 exceeds the cap and 系列導航 (L708) is unnumbered |
| phase12-part1-vit-fusion | 539 | 2 | 4 | 3 | 4 | 3 | 4 | 3.3 | **Not ready** | L222 "ViT-L/16 在 ImageNet-21k 預訓練 … 達 87.76%" — ViT paper Table 2: ViT-L/16 I21k = 85.30 %, JFT-300M = 87.76 %; L411 "Flamingo 16-shot VQA 達 82.0%" is the *fine-tuned* VQAv2 number; L514/L524 "+525%" for 12 → 71 % recomputes to +492 % |
| phase12-part2-agents-computer-use | 525 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L345–352 "失敗率分布（100 次任務實測）" and L334 "成功率：VLM-only 82% → Hybrid 91%", L339 "6% 降至 1.5%", L243 "降低 34%" — presented as measurements, no source; the 示意估算 label at L201 covers only the chart table |
| phase13-part1-mcp-apis | 578 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L411 `await server.send_progress(progress_token=…, progress=…, total=…)` — not an API in `modelcontextprotocol/python-sdk`; progress is reported from a tool via `ctx.report_progress(progress, total, message)` (or `session.send_progress_notification`). L239 calls JSON-RPC 2.0 the "傳輸層" (it is the message format; transports are stdio / Streamable HTTP, as L310 itself says) |
| phase13-part2-orchestration | 794 | 3 | 4 | 3 | 3 | 3 | 4 | 3.3 | Needs revision | L669 "實際測試數字：相同硬體（8 core）下，非同步 RAG 管線 QPS = 450，同步版本 QPS = 95" — no experiment, no setup; L437 `ImageIndex` / `TableIndex` are not LlamaIndex classes (it ships `MultiModalVectorStoreIndex`, `PandasQueryEngine`) |
| phase14-part1-loop-memory | 625 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L377 `INDEX (user_id, created_at DESC)` inside `CREATE TABLE` is MySQL syntax; PostgreSQL (the table's stated store, L372) rejects it — needs a separate `CREATE INDEX`. L350 "K=5 實測最佳", L397 "N = 6 … 實測甜蜜點", L542 "實測 … 84% vs 79%" are unsourced |
| phase14-part2-planning | 604 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L56 "在 WebArena benchmark 上，純 ReAct 完成率約 14%；加入規劃層後可達 26–35%；加入動態重規劃後可達 40–50%" — only 14.41 % is in the paper; the other two ranges are invented, and L560 then says the post's numbers "並非 WebArena … 的原始結果". L588–592 the Plan-and-Execute failure column sums to 38 % |
| phase14-part3-frameworks | 589 | 4 | 4 | 4 | 3 | 4 | 4 | 3.8 | Needs revision | L224 "每次工具呼叫 +150–400ms overhead（HTTP to executor）" — AutoGen tool calls are in-process; no HTTP hop exists to explain the number. L332 `PostgresSaver.from_conn_string(DB_URL)` is a context manager that also needs `.setup()`; as written it does not run |
| phase14-part4-production | 713 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L49 "GPT-4o 2024-11 版本和 2025-05 版本在工具選擇上的行為差異高達 15%" and L265 `model_id: gpt-4o-2025-05` — no such snapshot exists; the 15 % is invented. L34 "$350 vs $50" — 5,000 × $0.08 = $400; L454 free-tier bucket "0.5 token/秒 → 最多 10 req/分鐘" is 30 req/min |

Theses as read:
- 11-1: LLM serving cost is a memory problem — PagedAttention + continuous batching give the big jump, quantisation and speculative decoding the rest.
- 11-2: RAG only works in production when retrieval quality (hybrid search, chunking, re-ranking) is measured by an eval pipeline that gates deploys.
- 12-1: Vision–language alignment is a training-objective problem (CLIP), and the fusion point (early/late/cross) is chosen by latency and labelling budget.
- 12-2: A computer-use agent is a perceive–understand–plan–act–verify loop whose reliability comes from verification, sandboxing and bounded action spaces.
- 13-1: Tool use needs a protocol boundary (MCP) plus idempotency, caching, RBAC and injection isolation around every side-effecting call.
- 13-2: A production LLM app is a pipeline with retries, state and observability, not a function call; pick the orchestration framework by how much state you must persist.
- 14-1: An agent is a loop plus a layered memory plus a deterministic state machine that keeps irreversible actions out of the LLM's hands.
- 14-2: Separating planning from execution (with pre/post-conditions and replanning) is what moves agents from ReAct-level completion rates to production-level ones.
- 14-3: Framework choice is a trade of control for abstraction; align the framework's execution model with your interaction pattern, and build your own only when the abstraction blocks you.
- 14-4: Agent production readiness is observability, layered budgets, guardrails and shadow/canary evaluation designed before launch.

## Patterns

### Content quality
- Cores that hold: 13-1 L170–227 OpenAI function-calling lifecycle (`finish_reason: "tool_calls"`, `role: "tool"`, `tool_call_id`) and L247–258 MCP request catalogue (`tools/list`, `tools/call`, `resources/*`, `prompts/list`, `notifications/tools/list_changed`, `notifications/progress`) are correct; 13-2 L311–352 LCEL (`with_retry`, `with_fallbacks`, `RunnableParallel`) and L400–432 LlamaIndex `Workflow` match the real APIs; 14-4 L404–420 Redis `INCRBYFLOAT` pre-debit pattern is the right fix for the race it describes; 14-1 L446–474 refund state machine with "LLM may not trigger VALIDATING→PROCESSING" is the best teaching device in the batch.
- The 2025–2026 "註記" paragraphs are accurate and useful: 13-1 L310 (Streamable HTTP replaced HTTP+SSE, OAuth 2.1, structured tool output), 14-3 L179 (Microsoft Agent Framework, Oct 2025, folds AutoGen + SK), 11-1 L349 (SGLang, vLLM V1 prefix caching), 12-1 L434 (SigLIP, projector-style connectors), 14-2 L515 (reasoning models shrink the ReAct/PaE gap).
- Quality drops wherever the template asks for a number: 11-2 L550–553 root-cause shares "40 % / 25 % / 20 % / 15 %"; 12-2 L329 "VLM 誤判率高達 8%", L213 "deskew 88 % → 96 %", L243 "錯誤率降低 34 %… 遺漏率從 3 % 上升至 12 %"; 14-4 L477–482 guardrail "準確率 91 % / 96 % / 99 % / 94 %"; 14-2 L468 "攔截 15–20 %".
- Code bugs a reader will hit: 13-1 L411 `server.send_progress` (no such method); 14-1 L377 inline `INDEX` in PostgreSQL DDL; 14-3 L332 `PostgresSaver.from_conn_string` used without `with`/`.setup()`; 13-2 L586–606 `CircuitBreaker` references `_on_success`/`_on_failure` that are never defined.

### Structure (does the house format help or pad?)
- Every post opens with a 「工程情境」 interviewer prompt (11-1 L20, 12-1 L21, 13-1 L19, 14-4 L22 …). The plan's standard structure (L58–66) has no such block and says this is not interview prep; it is the fde 面試情境 with a new label.
- Phase sections that teach: 11-1 L48–131 (HF `generate()` → vLLM → quantised dual-track routing really is how serving matures); 14-4 L62–186 (print-logging → task queue + budgets → OTel + guardrails + A/B is a genuine maturity ladder); 13-1 L46–140 (hard-coded API → tool router → MCP gateway).
- Phase sections that pad or contradict: 11-1 L57 Phase 1 runs a 70B FP16 model on "單顆 A100（或 4× A10G）" when L31 just said it needs 140 GB; L127 Phase 3 claims INT4 "量化省 50 % GPU 記憶體" (FP16→INT4 is 75 %) and L157 draws "模型權重 35GB" for an FP16 70B; 12-1 L46–170 is ResNet-concat → CLIP → cross-modal relabelled POC/MVP/Scale by DAU; 14-2 L66–150 is ReAct → PaE → ToT by tasks/day, which is a technique ladder, not a scale ladder; 13-2 L163 Phase 2 "總延遲 ~1.4s" is lower than Phase 1's 2.1 s despite adding a re-ranker, with no explanation.
- Decision tables that weigh real alternatives: 11-1 L370–392 TP vs PP and L420–432 KEDA vs fixed; 11-2 L450–470 pgvector/Pinecone/Weaviate; 13-1 L521–533 RBAC vs prompt-level limits; 14-1 L511–524 ReAct vs Plan-and-Execute; 14-4 L627–650 Redis vs Postgres budget with the dual-write flip. Tables manufactured to hit six: 13-1 L478–491 "Redis vs 記憶體快取" and 13-2 L631–643 "Redis vs PostgreSQL" (the same table in consecutive posts); 12-1 L479–491 "對比學習 vs MAE" (not a fusion-architecture decision); 14-3 L506–518 "單一框架 vs 混合使用".
- 系統效應 tables are all labelled 示意估算 (11-1 L448, 11-2 L540, 12-1 L521, 12-2 L486, 13-1 L561, 13-2 L727, 14-1 L587, 14-2 L560, 14-3 L553, 14-4 L691) — a clear improvement over B07/B08 — but four posts then compute ROI or "關鍵洞察" from the labelled numbers as if they were data (11-1 L452–455, 13-1 L563–566, 14-1 L603–611, 14-4 L695–702).

### Depth
- Sourced or recomputable: 11-1 L31 140 GB / 2 TB/s = 70 ms per token (✓), L186 vLLM block size 16 (✓), L196 "< 4 %" waste (✓ vLLM blog); 11-2 L62/L658 OpenAI and Cohere embedding prices (✓), L677 MRL 1,536 → 256 = −83 % (✓); 12-1 L199–219 ViT patch/sequence arithmetic and ViT-B/L configs (✓), L365 τ init 0.07 (✓), L384 CLIP batch 32,768 (✓), L398–400 ALIGN 1.8 B pairs / 76.4 % (✓); 14-2 L310–316 UCB1 with C ≈ 1.4 (✓); 14-4 L676–690 all 系統效應 percentages recompute from their own rows (✓).
- Invented-looking with no label: 11-2 L265–267 chunking "Recall@5 0.71 / 0.78 / 0.84, Faithfulness 0.72 / 0.80 / 0.87" and L319–321 "Hybrid Recall@5 0.83 (+12pp), 專有名詞 0.54 → 0.79"; L399 "G-Eval Pearson ~0.82（RAGAS 約 0.74）" (the G-Eval paper reports Spearman ≈ 0.5 on SummEval; nothing supports 0.82); 12-1 L323–329 fusion table and L359 "1500 萬圖文對 37.8 %"; 14-3 L224 and L387 AutoGen/LangGraph overheads.
- Flip conditions are present on every table but several are thresholds pulled from the air: 11-1 L413 "acceptance rate < 60 % 不要用投機解碼", 11-2 L463 "超過 5M vectors → Pinecone", 14-1 L525 "任務 < 8 步時滑動視窗", 14-4 L624 "資料量 < 500 spans/天 不值得 OTel".
- "When it breaks" is done well in 11-2 §十 L545–627 (Faithfulness-drop and latency-spike diagnosis chains), 12-2 L312–330 (DOM vs screenshot failure modes), 14-2 L338–345 failure classification + L349–376 replanner tree, 14-4 L341–348 alert rules with thresholds. These are the sections to keep when the template is trimmed.

### Direction
- Overlap is heavier here than in B07/B08 because the blog already has dedicated series on every Phase 11–14 topic: 11-1 vs `vllm-intro-part1..5` (five posts on PagedAttention, scheduler, quantisation, production serving), `fde-interview-guide-part51-kv-cache-memory`, `fde-core-concept-16-ttft-throughput-optimization`; 11-2 vs `fde-core-concept-4-hybrid-search-rrf`, `-5-reranking-cross-encoder`, `-20-rag-triad-metrics`, `fde-interview-guide-part1/5/6`, `rag-series-part3/4/5`, `ai-accuracy-evaluation-part2/3`; 13-1 vs `fde-interview-guide-part17-mcp-tool-oauth`, `building-mcp-servers-claude-code-part1/2`, `fde-interview-guide-part22-parallel-tool-calling`; 13-2 vs `langgraph-langchain-intro-zh`, `fde-core-concept-3-state-machine-dag`, `-13-idempotency-state-recovery`; 14-1 vs `fde-interview-guide-part14-memory-architecture`, `-part18-memory-cost-tuning`, `mem0-intro-part1..5`, `fde-core-concept-1-context-management`; 14-2 vs `fde-interview-guide-part25-self-reflection-loop`; 14-3 vs `crewai-series-part1`, the four `langgraph-ai-backend-*` posts; 14-4 vs `fde-interview-guide-part48-self-healing-agent`, `-part38-prototype-to-production`.
- None of the ten posts links to those siblings. The series could cite them and shrink (e.g. 11-1 §三–五 could point at `vllm-intro-part2/3` and spend its lines on the serving-cost model instead).
- Gaps against the plan's lesson titles: Phase 12 "Agents + Computer-Use" names SeeAct in the description (12-2 L6) but never discusses it; Phase 13 "Tools & Protocols" has no A2A / agent-to-agent protocol mention; Phase 14 "Agent Engineering" has no evaluation-harness post (OSWorld/τ-bench style agent evals get one sentence at 12-2 L203).
- Stale-by-construction: 12-2 L201–209 GPT-4V / Claude 3.5 Sonnet / LLaVA-1.6 table (flagged as 2024 generation, fine); 14-1 L42 and L390 GPT-4o input at $5/1M (the launch price; $2.50 since the 2024-08-06 snapshot); 13-2 L618 "GitHub 90K+ stars"; 14-2 L211 "不建議在 2026 年前大規模部署" in a post dated June 2026.
- Category fit: `["all", "ai", "engineering"]` is right for all ten; `tools` would also fit 13-1 and 14-3.

### Accuracy
- Hard errors: 11-1 L144 KV-cache product and L37/L144 two different per-token sizes; L200 24× attributed to TGI; L444 cost row not derivable from the throughput row; L57 70B FP16 on one A100. 12-1 L222 87.76 % mis-attributed to I21k; L411 Flamingo 82.0 "16-shot"; L514 +525 %; L404 BLIP CapFilt described as "用 CLIP 過濾" (BLIP uses its own ITM filter). 14-4 L49/L265 fictional `gpt-4o-2025-05`; L34 $350; L454 30 vs 10 req/min; L403 "FastAPI 預設 worker=4" (uvicorn defaults to 1). 14-2 L588–592 column sums to 38 %.
- API/code: 13-1 L411 `server.send_progress`; 14-1 L377 inline INDEX; 14-3 L332 `PostgresSaver`; 13-2 L437 `ImageIndex`/`TableIndex`.
- Internal inconsistencies: 12-1 L118 "$180" vs L166 "$1,200" vs L385 "$60" for A100 fine-tunes (implied $0.625 / $1.25 / $0.625 per GPU-h) and L524 "$1,200 訓練成本" vs L118; 12-2 L476 Phase 2 "$0.27/任務" with 10 calls at $0.018 = $0.18; 14-2 L86 Phase 1 "GPT-4o mini" vs L575 "$0.032" for 3,200 tokens (≈ $0.001 on 4o-mini, ≈ $0.014 on 4o); 14-4 L220–235 per-step costs follow no single price ($0.0072 for 1,200/180 tokens is neither $2.5/$10 nor $5/$15).
- Claims a reader would act on that are merely unsourced: 11-2 L388 RAGAS "$0.003/筆 … GPT-4o-mini 準確度下降 ~6 %", L493 "人與人 ~90 %" (MT-Bench reports 81 %), L460/13-2 L723/14-1 L499 "Pinecone $70/月起" (current Standard plan minimum is $50); 13-1 L231 strict mode "+50–100ms"; 12-2 L185 Textract "$0.015/頁" (that is the Tables tier; text detection is $0.0015).

### Format / front matter
- Front matter complete on all ten; `weight` 22–31 is contiguous and matches `date` order; 11-2 L716 "系列第 23 篇" agrees with `weight: 23`.
- Section numbering: nine posts run 一–十 with 十 = 系列導航 as the plan requires; 11-2 has 一–十一 + 附錄 + unnumbered 系列導航 (L630, L681, L708) — the mechanical warning.
- readTime: 467 L / 17 min (11-1), 525 L / 18 min (12-2) are on the 500 L ≈ 18 min curve; 578 L / 23 min (13-1), 539 L / 23 min (12-1), 589 L / 23 min (14-3) and 604 L / 23 min (14-2) overstate by ~3 min; 794 L / 23 min (13-2) understates by ~3 min.
- Tags: all carry `"RKK"` and `"ai-eng-from-scratch"`, none carry `"Interview"` (✓). Opening four-line contrast quote present in all ten. 12-2 L14–17 and 14-1 L14–17 use trailing double-space line breaks instead of `> *…*` italics — renders, but inconsistent with the other eight.
- ASCII diagrams exceed 80 columns in 11-2 L163–197 (≈ 84 cols), 12-2 L93–120 (≈ 86 cols) and 14-1 L160–190 (≈ 88 cols); they will wrap on phone width.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | phase11-part1:144 | "2 × 80 × 64 × 128 × 2 = 3,276,800 bytes ≈ 3.1 MB" — product is 2,621,440; and Llama-2-70B uses 8 KV heads (GQA), so the real value is 327,680 B ≈ 0.33 MB/token, 2048 tokens ≈ 0.67 GB, not 6.4 GB | Redo §三 with `2 × layers × n_kv_heads × head_dim × 2 B`, show MHA vs GQA side by side, and make L37 ("約 0.8 MB") agree |
| 2 | blocker | phase11-part1:200 | "對比 HuggingFace TGI，吞吐量提升 24×" — vLLM blog: up to 24× vs HF Transformers, up to 3.5× vs TGI | Quote both numbers with the source |
| 3 | blocker | phase11-part1:439–446 | Cost row ($0.045 / $0.011 / $0.006 / $0.004 per 1K tok) does not follow from the hardware and tok/s rows at $3.09/GPU-h (implied $0.029 / $0.0010 / $0.0003 / $0.0002) | Derive each cell from `GPUs × $/h ÷ (tok/s × 3.6)` or drop the row; same for L63 Phase 1 ($0.0034, not $0.05) |
| 4 | blocker | phase12-part1:222 | "ViT-L/16 在 ImageNet-21k 預訓練 … 87.76 %" — that is the JFT-300M run; I21k ViT-L/16 is 85.30 % (ViT paper Table 2). "ResNet-152 的 83.8 %" has no source (the paper's BiT-L comparator is 87.54 %) | Use 85.30 % for I21k or say JFT-300M; replace the ResNet baseline with the paper's BiT-L number |
| 5 | blocker | phase12-part1:411, 514, 524 | "Flamingo 16-shot VQA 達 82.0 %" is the fine-tuned VQAv2 score (few-shot is ~67 %); "+525 %" for 12 → 71 % is +492 % | Fix both; the 系統效應 table's other deltas recompute correctly |
| 6 | major | phase13-part1:411 | `await server.send_progress(progress_token=…)` — not in the MCP Python SDK; tools get a `Context` and call `ctx.report_progress(progress, total, message)` | Rewrite the snippet with `Context`; mention the client-supplied `progressToken` in `_meta` |
| 7 | major | phase14-part2:56 | "WebArena … 純 ReAct 約 14 %；Plan-and-Execute 26–35 %；動態重規劃 40–50 %" — only 14.41 % is in the paper; L560 then disclaims the post's numbers as not from WebArena | Keep 14.41 % with citation, delete the two invented ranges or attribute them to a real agent paper |
| 8 | major | phase14-part4:49, 265 | "GPT-4o 2024-11 版本和 2025-05 版本 … 差異高達 15 %", `model_id: gpt-4o-2025-05` — no such snapshot; the 15 % is invented | Use real snapshot IDs (2024-08-06 / 2024-11-20) and say "measure the drift on your own eval set" |
| 9 | major | phase11-part2:210–211 vs 219–224 | P95 "~750 ms / ~1,800 ms" vs the per-stage P95 column (18+45+2+1,200 = 1,265 ms; +120 ms re-rank = 1,385 ms) | Make the diagram totals the sums of the table, or state which percentile is being added |
| 10 | major | phase12-part2:345–352, 334, 339, 243 | "100 次任務實測" failure distribution and "82 % → 91 %", "6 % → 1.5 %", "降低 34 %" presented as measurements | Label 示意估算 like L201, or cite OSWorld/WebArena results |
| 11 | major | phase13-part2:669 | "實際測試數字：… QPS = 450，同步版本 QPS = 95" with no setup, model, or code | Remove "實際測試" or describe the benchmark |
| 12 | major | phase14-part1:377 | `INDEX (user_id, created_at DESC)` inside `CREATE TABLE` is MySQL; PostgreSQL rejects it | `CREATE INDEX episode_memory_user_ts ON episode_memory (user_id, created_at DESC);` |
| 13 | major | phase12-part1:118, 166, 385, 524 | A100 priced at $0.625, $1.25 and $0.625 per GPU-h in three places; L524 repeats the fine-tune as "$1,200" where L118 said "$180" | Fix one $/GPU-h (11-1 uses $3.09) and recompute |
| 14 | minor | phase14-part4:34, 454, 403 | 5,000 × $0.08 = $400 (text says $350); 0.5 token/s bucket = 30 req/min (text says 10, Phase 2 L140 also says 10); "FastAPI 預設 worker=4" (uvicorn default is 1) | Fix the three numbers; free tier needs 0.167 token/s |
| 15 | minor | phase11-part2:630, 708 | Section 十一 exceeds the cap; 系列導航 unnumbered | Fold §十一 (embedding selection) into §四 or §五, renumber, make 系列導航 §十 |

## Recommendations

1. **Fix the two Not-ready posts before anything else** (11-1, 12-1). WHY: the KV-cache formula and the ViT/CLIP benchmark numbers are exactly what a reader will copy into a design doc. HOW: in 11-1 rewrite §三 around `2 × L × n_kv × d_head × bytes` with MHA/GQA columns, re-derive every $/1K-token cell, and quote the vLLM blog correctly; in 12-1 replace L222/L411 with the papers' numbers and pick one A100 price.
2. **Strip "實測 / 實際測試 / 100 次任務" wording unless there is an experiment.** WHY: eight posts say 示意估算 in the 系統效應 table and then say 實測 in the body (12-2 L345, 13-2 L669, 14-1 L350/L397/L542); readers trust the body more than the footnote. HOW: `grep -n "實測\|實際測試" content/posts/ai-eng-from-scratch-phase1[1-4]*` and either cite a source or change to 示意.
3. **Run every code block that names a real library.** WHY: four snippets would fail as written (13-1 L411, 14-1 L377, 14-3 L332, 13-2 L586 CircuitBreaker). HOW: paste into a scratch venv with `mcp`, `langgraph`, `psycopg`; keep snippets ≤ 20 lines so they can be run.
4. **Drop the 工程情境 block series-wide** (10/10 posts). WHY: the plan says this is not interview prep and the block is the fde 面試情境 renamed. HOW: delete L19–24 in each file; the four-line quote already frames the post.
5. **Keep the phase ladder only in 11-1, 13-1, 14-4** and convert the rest to a "when to add X" paragraph. WHY: 12-1 and 14-2 ladders are technique histories (ResNet→CLIP→cross-modal; ReAct→PaE→ToT) with DAU labels bolted on; 13-2 L163 contradicts its own latency arithmetic. HOW: for the five posts where scale is not the axis, replace §二 with a two-paragraph "從 X 升級到 Y 的觸發條件".
6. **Cut decision tables to the ones with a real alternative** (target 3–4 per post). WHY: 13-1 L478 and 13-2 L631 are the same Redis-vs-Postgres table; 12-1 L479 (CLIP vs MAE) and 14-3 L506 (單一 vs 混合) exist to reach six. HOW: keep the tables cited under "Patterns → Structure" and merge the rest into prose.
7. **Link to the sibling series instead of re-explaining.** WHY: `vllm-intro` (5 posts), `fde-core-concept-4/5/20`, `mem0-intro`, `langgraph-*` already cover PagedAttention, RRF, re-ranking, RAG triad, memory tiers and LangGraph. HOW: one "延伸閱讀" line per section with `/posts/<slug>/` links; 11-1 §四–五 can shrink to a summary + link to `vllm-intro-part2/3`.
8. **Refresh the dated prices and versions in one pass.** WHY: GPT-4o $5/1M (14-1 L42/L390, implied in 14-4 L220–235 and L353), Pinecone $70/mo (three posts), LangChain 90K stars, FastMCP → `MCPServer` rename in SDK v2 (13-1 L307). HOW: a single "prices as of <date>" note per post, and point at the official pricing page rather than hard-coding.
9. **Fix 11-2's structure and the three over-wide diagrams.** WHY: the only mechanical warning in the batch, plus 11-2 L163, 12-2 L93 and 14-1 L160 wrap at phone width. HOW: fold §十一 into §四/§五; trim diagram boxes to ≤ 80 columns.
10. **Update `AI_ENG_FROM_SCRATCH_PLAN.md` L138–154 to ✅ with line counts** once the fixes land, so the inventory stops reporting ten published posts as Not Started.

## Verified / unverified claims

- ✅ phase11-part1:31 — 140 GB ÷ 2 TB/s = 70 ms per decode step for a 70B FP16 model on A100 (recomputed).
- ✅ phase11-part1:186, 196 — vLLM default block size 16 tokens; PagedAttention waste "under 4 %" (vLLM blog, 2023-06-20).
- ❌ phase11-part1:200 — "vs TGI 24×" — blog: 24× vs HF Transformers, 3.5× vs TGI.
- ❌ phase11-part1:144 — 2×80×64×128×2 = 2,621,440 B, not 3,276,800; Llama-2-70B GQA → 327,680 B/token (recomputed).
- ❌ phase11-part1:37 vs 144 — 0.8 MB vs 3.1 MB per token for the same model.
- ❌ phase11-part1:439–446 — $/1K-token row inconsistent with tok/s row at $3.09/GPU-h (recomputed: $0.029 / $0.0010 / $0.0003 / $0.0002).
- ❌ phase11-part1:127, 320 — INT4 from FP16 is a 4× (75 %) reduction, not "省 50 %" / "位元數減半".
- ✅ phase11-part2:62, 658–660 — text-embedding-3-small $0.02/1M, -3-large $0.13/1M, Cohere embed-v3 $0.10/1M.
- ✅ phase11-part2:677 — 1,536 → 256 dims = −83.3 % storage (recomputed).
- ✅ phase11-part2:288, 313 — RRF `1/(k+rank)`, k = 60.
- ❌ phase11-part2:210–211 — P95 totals do not equal the sum of the P95 column at L219–224 (1,265 / 1,385 ms recomputed).
- ❓ phase11-part2:399 — "G-Eval Pearson ~0.82（RAGAS 約 0.74）" — no source; the G-Eval paper reports Spearman ≈ 0.5 on SummEval.
- ❓ phase11-part2:493 — "人與人 ~90 %" — MT-Bench reports 81 % human–human, 85 % GPT-4–human.
- ❓ phase11-part2:460, phase13-part2:723, phase14-part1:499 — "Pinecone $70+/月起" — could not confirm; current Standard plan minimum appears to be $50/mo.
- ❓ phase11-part2:664 — g5.xlarge "~$1.5/hr" — on-demand us-east-1 is ≈ $1.006/hr; break-even arithmetic itself is consistent.
- ✅ phase12-part1:199–219 — 224/16 = 14, 196 patches, 16×16×3 = 768, ViT-B (12/12/768) and ViT-L (24/16/1024) configs.
- ✅ phase12-part1:365, 384, 398–400 — CLIP τ init 0.07, batch 32,768; ALIGN 1.8 B pairs, 76.4 % zero-shot.
- ❌ phase12-part1:222 — ViT-L/16 I21k = 85.30 %; 87.76 % is JFT-300M (ViT paper Table 2).
- ❌ phase12-part1:411 — Flamingo 82.0 is fine-tuned VQAv2, not 16-shot.
- ❌ phase12-part1:514, 524 — (71−12)/12 = +492 %, not +525 % (recomputed); other deltas in the table ✓.
- ❌ phase12-part1:118, 166, 385 — A100 at $0.625 / $1.25 / $0.625 per GPU-h (recomputed from the stated runs).
- ❓ phase12-part1:404 — "BLIP 用 CLIP 過濾雜訊資料" — BLIP's CapFilt uses its own ITM-trained filter.
- ✅ phase12-part2:78, 276–279, 476–484 — $0.03×15×500 = $225/day; 1,450 ms/step × 10 ≈ 15 s; 系統效應 deltas recompute from their rows.
- ❌ phase12-part2:476 — Phase 2 "$0.27/任務" with 10 calls × $0.018 = $0.18 (recomputed).
- ❓ phase12-part2:185 — Textract "$0.015/頁" is the Tables tier; plain text detection is $0.0015/page.
- ✅ phase13-part1:170–227 — OpenAI function-calling message shapes (`tool_calls`, `role: "tool"`, `tool_call_id`).
- ✅ phase13-part1:239, 247–258, 310 — MCP released Nov 2024; JSON-RPC 2.0 messages; `tools/list`, `tools/call`, `resources/*`, `prompts/list`, `notifications/progress`; Streamable HTTP replaced HTTP+SSE; OAuth 2.1; structured tool output (modelcontextprotocol.io spec pages).
- ✅ phase13-part1:278–305 — low-level `mcp.server.Server` with `@app.list_tools()` / `@app.call_tool()`, `Tool(name, description, inputSchema)`, `TextContent`.
- ❌ phase13-part1:411 — `server.send_progress(...)` does not exist; SDK docs show `ctx.report_progress(progress, total, message)` (py.sdk.modelcontextprotocol.io/handlers/progress).
- ❓ phase13-part1:307 — "FastMCP" — the SDK's current README/docs name the high-level class `MCPServer` (`from mcp.server import MCPServer`); FastMCP appears to be the v1 name.
- ❓ phase13-part1:231 — strict-mode "+50–100ms 首 token" — OpenAI documents a one-time schema-compile latency, not a per-call 50–100 ms.
- ✅ phase13-part2:311–352, 400–432 — LCEL `with_retry(...)`, `with_fallbacks([...])`, `RunnableParallel`; LlamaIndex `Workflow`/`@step`/`StartEvent`/`StopEvent`; LangChain 1.x (2025) note.
- ❌ phase13-part2:437 — `ImageIndex` / `TableIndex` are not LlamaIndex classes.
- ❓ phase13-part2:618 — "GitHub 90K+ stars" — dated (≈ 115K+ by 2025).
- ✅ phase14-part1:42, 442–444, 603–611 — 128K × $5/1M = $0.64; 12K × $5/1M = $0.06, ×25 = $1.50; ROI 886 %; $1.55M and −74 % all recompute (at the post's $5/1M assumption).
- ❓ phase14-part1:42, 390 — GPT-4o input "$5/1M" — launch price; $2.50/1M since the 2024-08-06 snapshot.
- ❌ phase14-part1:377 — inline `INDEX (...)` in `CREATE TABLE` is not PostgreSQL syntax.
- ✅ phase14-part2:56 (first number only) — WebArena best GPT-4 agent 14.41 % (arXiv 2307.13854).
- ❌ phase14-part2:56 — "26–35 %" and "40–50 %" ranges have no source; contradicted by L560.
- ❌ phase14-part2:588–592 — Plan-and-Execute failure column sums to 38 % (recomputed).
- ❌ phase14-part2:86 vs 575 — "$0.032" for 3,200 tokens is a GPT-4o price, not GPT-4o-mini (≈ $0.001).
- ✅ phase14-part2:310–316 — UCB1 formula, C ≈ √2.
- ✅ phase14-part3:179 — Microsoft Agent Framework (Oct 2025) merges AutoGen and Semantic Kernel; L475 LangGraph production users Replit/Elastic.
- ✅ phase14-part3:255–280 — CrewAI `Agent`/`Task`/`Crew`/`Process.sequential` API.
- ❌ phase14-part3:224 — AutoGen "+150–400ms (HTTP to executor)" per tool call — tool execution is in-process; no HTTP hop.
- ❓ phase14-part3:332 — `PostgresSaver.from_conn_string(DB_URL)` returns a context manager and needs `.setup()`.
- ✅ phase14-part4:404–420, 676–690, 695–702 — `INCRBYFLOAT` pre-debit pattern; all 系統效應 and cost-structure percentages recompute.
- ❌ phase14-part4:34 — 5,000 × $0.08 = $400, not $350 (monthly $9,000 only works with $350).
- ❌ phase14-part4:454 — 0.5 token/s = 30 req/min, not 10 (recomputed).
- ❌ phase14-part4:49, 265 — `gpt-4o-2025-05` is not an OpenAI snapshot; "15 %" drift invented.
- ❌ phase14-part4:403 — "FastAPI 預設 worker=4" — uvicorn default is 1 worker.
- ❓ phase14-part4:220–235 — per-step costs ($0.0072 / $0.0094 / $0.0109) match no single GPT-4o price (recomputed at $2.5/$10 and $5/$15); the sum $0.0275 is internally consistent.
- ✅ phase14-part4:353 — "gpt-4o-mini 成本降幅 97 %" holds at the post's $5/1M GPT-4o price (94 % at $2.50).
