# B15 — rag-series · vllm-intro · ragflow-intro · chatpdf-rag-optimization (18 posts)

Files: `content/posts/vllm-intro-part{1..5}-*-zh.md` (3,453 lines), `ragflow-intro-part{1..5}-*-zh.md` (3,674), `rag-series-part{1..5}-*-zh.md` (2,570), `chatpdf-rag-optimization-part{1..3}-*-zh.md` (944). 10,641 lines total, all Traditional Chinese.
Mechanical baseline (`docs/content-audit/inputs/mechanical-baseline.txt`): **no entries** for any of the 18 files. Re-run of `scripts/review_posts.py` on the batch: 0 errors, 0 warnings. No hard-coded baseURL; every series-nav link resolves. None of these series is an interview series, so the fde template is not required — the vllm and ragflow series adopt it voluntarily (三個演進階段, 為什麼選 X 不選 Y, 系統效應, 一…十).

## Batch summary

This batch splits cleanly into two halves. The two **source-code reading series** (vllm-intro, ragflow-intro) are the strongest technical writing in the audit so far: each has a real thesis ("memory is throughput — vLLM is an OS for GPU memory"; "quality in, quality out — fix data at ingestion, not at retrieval"), the house template is used as a lens rather than a quota, numbers are either derived in front of the reader (KV bytes/token, all-reduce traffic, LLM-call budgets) or explicitly labelled 量級估算, and every fast-moving fact I could check held up — `VLLM_USE_FASTOKENS`, the `vllm:kv_block_*` histograms, sha256 as the 0.11 default, `/v1/chat/completions/batch`, `structured_outputs`, `--speculative-config`, RAGFlow v0.27.1 and the Go `task executor` migration all verified. What slips is arithmetic at the edges (vllm-1 L282 claims 400–600 concurrent sequences where its own §5.2 formula gives 55; vllm-4 L546 calls `PIECEWISE` the default when the docs say `FULL_AND_PIECEWISE`; vllm-5 L335's LoRA formula yields 268 MB, not "約 1.5 GB"; ragflow-2 L519's "約 900 美元" recomputes to $1,098), a few commands that would not run as written (vllm-1 L332 `meta-llama/Llama-3.3-70B-Instruct-FP8` is not a Meta repo; vllm-4 L658–661 mixes the TP/PP multi-node flags into a DP+EP launch), and a version stamp — "2026 年 9 月，版本參考 0.19.x" — that is four months stale against the post date (0.21 shipped 2026-05-15; docs now list 0.30). The **rag-series** is the opposite case: five competent tutorials with no thesis, no numbers, and 2025-era LangChain/Qdrant imports (`langchain.retrievers.ParentDocumentRetriever`, `langchain_community.vectorstores.Chroma`, `client.search`) that LangChain 1.0 and qdrant-client have since moved or deprecated — the same author adds a careful RAGAS-0.2 migration note at rag-5 L95, so the standard is known. The **chatpdf** trilogy is honest PR narration (it says when a change was not measured) but measures nothing, mis-states sigmoid at chatpdf-3 L198, and its test counts do not reconcile across posts (128 → 165 "+30" → 235 "+11"; PR #3 and now PR #5 are missing). The four RAG series plus the five sibling posts named in the brief cover the same ground five ways and **zero of the 13 RAG posts link to any other** (grep: only `langfuse-intro-part1` links in). Verdicts: **10 Ready** (vllm 2/3/5, ragflow 1–5, chatpdf 1/2), **8 Needs revision** (vllm 1/4, rag-series 1–5, chatpdf 3), **0 Not ready**.

## Per-post scorecard

Scores: A accuracy, C clarity, D depth, V visuals, S structure, F format (1–5); Overall = plain mean (no finance posts).

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| vllm-intro-part1-architecture-overview | 619 | 4 | 5 | 4 | 4 | 4 | 4 | 4.2 | Needs revision | L282 "8192 context … 400–600 條併發序列" — the post's own §5.2 (L395–402) gives 48 GB / 128 KB = 393K tokens → **48 seqs at 8192, 196 at 2,000**; L282 also says "約 55 GB 給 KV" where the ledger at L351 says 48 GB. Also L332 `meta-llama/Llama-3.3-70B-Instruct-FP8` — no such Meta repo (FP8 builds are `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`) |
| vllm-intro-part2-paged-attention-kv-cache | 649 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L470 `vllm:kv_block_{lifetime,idle_before_evict,reuse_gap}_seconds` are real (added 0.13) but **1 %-sampled and off unless `--kv-cache-metrics-sample` is set** — the "鐵證" rule at L470/L629 silently returns no data on a default server. L119 "從 6 條併發變成 190+" — the 6 is unexplained (contiguous 8192-slot allocation of 48 GB gives 48) |
| vllm-intro-part3-scheduler-continuous-batching | 636 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L422 EAGLE row: (1−0.75⁵)/0.25 = **3.05**, speedup 3.05/1.4 = **2.2×**, not 3.2 / 2.3×; L257–260 four rounds of 8,132+8,192 = 32,588 < 32,768 (needs a 5th); L265 "需要 16 輪" is 17 at 1,988 prefill/round; L49 "17 / (4×9)" counts tokens over cells (21 cells are busy) |
| vllm-intro-part4-distributed-quantization | 733 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L546 "`PIECEWISE`（預設）" — vLLM's CUDA-graph design doc: V1 with piecewise compilation **defaults to `FULL_AND_PIECEWISE`** (PIECEWISE is the "past default"; pooling models excepted). L658–661 launches DP=16 + EP across 2 nodes with `--nnodes/--node-rank/--master-addr` (the TP/PP mp flags); the EP deployment doc uses `--data-parallel-size-local 8` + `--data-parallel-address` / headless mode — command as written is ❓ unlikely to start |
| vllm-intro-part5-production-serving | 816 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L335 formula `max_loras × rank × 層數 × hidden × 2 × 2 bytes` = 8×64×32×4096×4 = **268 MB**, not "約 1.5 GB" (the 1.5 GB needs ~7 target modules per layer, which the formula omits). L487–489 kv_block metrics need the sampling flag (same as part 2). Everything else checked ✅ (batch endpoint, FASTOKENS, `structured_outputs`, `vllm bench`, `cache_salt`, `VLLM_SERVER_DEV_MODE`) |
| ragflow-intro-part1-overview-architecture | 627 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L22 "9.0 萬顆星、1.06 萬 fork", L123 "Elasticsearch 8.11.3", L485 "Python ≥ 3.13", L627 "v0.27.1" — all ❓ (v0.27.1 image and Go executor migration ✅ confirmed; the rest unverifiable from outside the tree). 31 code-block lines exceed 80 cols (first L142) |
| ragflow-intro-part2-deepdoc-chunking | 607 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L519 "6.1M 次 × (800 in + 100 out) @ $0.15/$0.60 … 約 900 美元" recomputes to **$1,098**; L180 "0.3～1.5 美元/份" VLM cost and L468 "GraphRAG 10～50 倍" unsourced; L440 "2025-10-15 加入 orchestrable ingestion pipeline" ❓ |
| ragflow-intro-part3-embedding-indexing | 665 | 4 | 5 | 5 | 4 | 4 | 4 | 4.3 | Ready | L444 "比 ES 預設的 1s 一樣（1000ms = 1s）" — garbled sentence; L585 table "≈ 3～6 GB" vs L587 text "≈ 4～6 GB" for 1 M chunks; L400–404 engine versions (Infinity v0.7.3, OpenSearch 2.19.1, OceanBase 4.4, SereneDB 26.07) ❓ |
| ragflow-intro-part4-retrieval-rerank | 889 | 4 | 4 | 5 | 4 | 4 | 4 | 4.2 | Ready | L672 "每千次查詢成本 $1～3 / $2～5 / $20～100" and L668–669 latency rows are unsourced order-of-magnitude guesses presented in a table of otherwise code-derived constants; L290 "196 KB" is 192 KiB (fine). readTime 22 min for 889 lines (≈ 28) |
| ragflow-intro-part5-system-code-structure | 886 | 4 | 4 | 5 | 3 | 4 | 4 | 4.0 | Ready | 51 code-block lines over 80 cols (first L46 — the directory tree will wrap on phones); L627 "GitHub language 欄位顯示 Go" ❓; readTime 21 min for 886 lines (≈ 28). Content itself (entrypoint order L146, Redis Stream semantics L313–321, build-tag table L709–715) is the best systems write-up in the batch |
| rag-series-part1-foundations | 317 | 4 | 5 | 2 | 3 | 3 | 4 | 3.5 | Needs revision | **No thesis** — an intro that explains Naive RAG and lists its limits (L287–294) without a claim. Code (L139–264) is correct and current (`openai.OpenAI`, chromadb, `langchain_text_splitters`). No number anywhere in the post |
| rag-series-part2-chunking-vectordb | 507 | 3 | 4 | 3 | 3 | 3 | 4 | 3.3 | Needs revision | L140–143 `from langchain.retrievers import ParentDocumentRetriever` / `langchain_community.vectorstores.Chroma` — LangChain 1.0 (Oct 2025) moved these to `langchain_classic` / `langchain_chroma`; L297 `client.search(...)` is deprecated in qdrant-client (use `query_points`). L221 "> 百萬筆", L366 "< 500 萬筆", L373–388 decision-tree thresholds are unsourced |
| rag-series-part3-advanced-retrieval | 516 | 4 | 4 | 3 | 3 | 3 | 4 | 3.5 | Needs revision | L389 comment "中文推薦：cross-encoder/ms-marco-MiniLM-L-6-v2（英文為主）" contradicts itself; L126–131 "RRF" with α-weighting is a hybrid of RRF and weighted fusion — say so. No latency/recall number for any of the four techniques (L499–504 table is "低/中/高") |
| rag-series-part4-optimization | 574 | 3 | 4 | 3 | 3 | 3 | 4 | 3.3 | Needs revision | L459–462 `langchain.retrievers.ContextualCompressionRetriever` / `langchain.retrievers.document_compressors.LLMChainExtractor` / `langchain_community.vectorstores.Chroma` — same LangChain-1.0 move. L211 Self-RAG disclaimer is exactly right and should be the model for the rest of the series |
| rag-series-part5-production | 656 | 4 | 4 | 3 | 3 | 3 | 4 | 3.5 | Needs revision | L95 RAGAS 0.1 → 0.2 migration note ✅ (field renames correct). L446–560 LangGraph code ✅ current (`StateGraph`, `ToolNode`, `bind_tools`). L36 "四個核心指標" — RAGAS defines more; L578–582 "GPT-4.1 … 2025" example already dated for a May-2026 post |
| chatpdf-rag-optimization-part1-chunking-retrieval | 350 | 4 | 5 | 3 | 4 | 4 | 4 | 4.0 | Ready | L13 "80% 的爛答案" hook unsourced; L323 "128 測試全綠" vs part 2 L26 "165 測試,+30 新增" (128+30 = 158) — counts don't reconcile; readTime 16 min for 350 lines (≈ 11). BM25 at L178–216 is a correct Lucene-variant implementation ✅; L311 honestly notes the LRU cache does not fix the O(N) scan |
| chatpdf-rag-optimization-part2-backend-hardening | 275 | 4 | 5 | 3 | 4 | 4 | 4 | 4.0 | Ready | L244–245 "預期提升 recall,本 PR 未量測" / "效果未量測" — honest, but it means the post's two "進階 RAG" changes have no evidence; L116–130 LRU snippet shows the eviction loop but not the `move_to_end` hit path it describes |
| chatpdf-rag-optimization-part3-observability-eval | 319 | 4 | 5 | 3 | 4 | 4 | 4 | 3.8 | Needs revision | L198 "門檻預設 0.0,約等於 sigmoid(0.5)" — inverted: a logit threshold of 0.0 is **sigmoid(0) = 0.5**; L286 "後端 235 測試" vs part 2's 165 (+11 claimed here = 176) — PR #3 is never mentioned and PR #5 (different-family judge) post-dates the series |

Theses as read:
- vllm-1: Single-sequence decode is bandwidth-bound, so throughput comes from batching, batching from memory, and vLLM is the engine that treats GPU memory as an OS problem.
- vllm-2: KV cache is a malloc problem, not a memoization problem; paging, COW, hash-chained prefix caching and FP8 are the OS answers.
- vllm-3: In continuous batching "batch size" is the scheduler's per-iteration token budget; `max_num_batched_tokens` is the knob that trades TTFT/throughput against ITL.
- vllm-4: Quantise before you parallelise; TP inside the NVLink domain, PP across nodes, DP+EP for MoE; compile only once the other two walls are gone.
- vllm-5: A serving system is one you can interrogate — where is it slow, what does a GPU buy, will the number hold tomorrow — hence metrics, benchmark discipline and P/D separation.
- ragflow-1: 80 % of a RAG engine's complexity is before and after the LLM call; RAGFlow's four pillars map one-to-one onto naive RAG's four failure points.
- ragflow-2: Chunk quality is decided at parse time; vision-based layout understanding plus template-based, delimiter-first chunking is the "in" of "quality in, quality out".
- ragflow-3: Schema, similarity function and field naming are frozen at write time; RAGFlow's suffix-driven mapping and IDF-only similarity are deliberate answers for chunk-scale retrieval.
- ragflow-4: Retrieval is a six-stage pipeline whose weights are all inspectable; the post-hoc citation alignment is the design that makes citations independent of LLM compliance.
- ragflow-5: Architecture lives in process topology, queue semantics and failure handling; RAGFlow's Redis-Stream task system and incremental Go migration are the lessons.
- rag-series-1 … 5: **no thesis** (tutorial/feature tour: "here are N techniques and their pros/cons").
- chatpdf-1: RAG quality is won at chunking and retrieval, not at the LLM. chatpdf-2: Production is the worst case not blowing up — bounds, ordering and fallbacks. chatpdf-3: Without measurement the optimise-measure loop cannot turn.

## Patterns

### Content quality
- The code-reading series derive their numbers on the page and label the rest: vllm-1 L60 (140 GB / 3.35 TB/s ≈ 24 tok/s ✓), L363–367 KV bytes/token for three models (all recompute ✓), L395–402 capacity formula ✓; vllm-4 L203–209 all-reduce traffic (128 MB × 2 × 80 = 20 GB → 22 ms NVLink / 625 ms PCIe ✓); ragflow-1 L300 and ragflow-2 L508–517 LLM-call budgets ✓; ragflow-3 L587 index-size estimate ✓. Each post ends with an italic scope note (vllm-1 L619, ragflow-5 L886) saying which numbers are estimates.
- The weak spots are where a number is quoted rather than derived: vllm-1 L282 (400–600 concurrent — contradicts §5.2), L591 "<30 % → >80 %", L593 "TTFT 降 5–20×"; vllm-4 L115 "5–6.5 倍", L625 "1.3–1.8 倍"; vllm-5 L332–333 "吞吐降 5–15 %", "+20–80 ms"; ragflow-4 L668–672 latency/cost rows; ragflow-2 L180, L468.
- rag-series is clean but shallow: every technique gets 優點/缺點/最佳使用場景 (rag-3 L150–152, L248–250, L359–361, L461–463) with no measurement, no failure mode and no flip condition; rag-5 L623–631 "黃金法則" are assertions ("Reranker 幾乎總是值得加") the series never supports.
- chatpdf is candid to a fault: chatpdf-2 L244–245 says two of its headline features were not measured; chatpdf-1 L311 admits the LRU cache does not fix the O(N) scan. That honesty is the right instinct — but a three-post "optimization" series with zero before/after numbers (no Hit@k, MRR, nDCG, latency) cannot show that anything was optimised, even though chatpdf-1 L324 says the repo ships `rag_evaluation.md` with exactly those metrics.

### Structure (does the house format help or pad?)
- Phase ladders that teach: vllm-1 L265–416 (single card → K8s+FP8+TP → P/D disaggregation, with the Phase-2→3 trigger at L416 tied to real metrics); vllm-2 L72–163 (contiguous → paged+COW → prefix cache+offload is literally the history of the feature); ragflow-1 L248–341 (each phase is a `.env` combination); ragflow-5 L544–621 (compose → multi-host consumer ranges → K8s+Go).
- Phase ladders that relabel a technique list: vllm-3 L80–169 (static batch → V0 → V1 is a version history, not a scale ladder); ragflow-4 L595–673 (pure vector → hybrid+rerank → agentic). Both still carry real content, so the cost is only the ╔══╗ framing.
- 為什麼選 X 不選 Y tables are genuinely argued with flip conditions in every vllm/ragflow post (vllm-1 L516–575 six engine comparisons; vllm-2 L598–670; ragflow-3 L594–632; ragflow-5 L783–831). Two rows are filler: vllm-3 L560 "翻轉條件：無。V0 已被移除"; ragflow-4 L815–818 "翻轉點：沒有；這是好設計".
- rag-series uses none of the template and would benefit from one piece of it: a flip condition per technique. chatpdf's 為什麼選 X 不選 Y tables (chatpdf-1 L298–311, -2 L218–232, -3 L257–272) are the right size for a PR write-up.
- Section numbering is 一…十 in all ten vllm/ragflow posts with 十 = 系列導航 ✓. chatpdf-2 runs to 十一 (L252) — not a house rule for this series, but inconsistent with parts 1 and 3 (九).

### Depth
- Sourced or recomputable: vllm-1 L68/L87 (vLLM paper 60–80 % waste, 24× HF, 3.5× TGI ✓), L370 (LLaMA-13B 1.7 GB ✓); vllm-2 L350 (55 % / 2.2× ✓ paper), L384 sha256 default since 0.11 ✓, L408–412 hash-algo options ✓; vllm-3 L278–283 official `max_num_batched_tokens` guidance ✓, L404 E[tokens] formula ✓; vllm-4 L212 TP-in-node/PP-across-nodes ✓, L246 head-divisibility rule ✓, L529 `unified_attention_with_output` ✓, L567 compile-cache path ✓; vllm-5 L194 batch endpoint ✓, L245 FASTOKENS ✓, L491 removed V0 metrics ✓, L726 $64/h × 730 = $46,720 ✓; ragflow-4 L290 192 KiB ✓; ragflow-5 Go migration ✓ (v0.27.0 release notes).
- Flip conditions are present and specific throughout vllm/ragflow (vllm-2 L484–486 "concurrency > 100 → don't bother with FP8 KV; < 20 → cheapest 2×"; vllm-3 L578 "batch < 16 賺, > 64 賠"; ragflow-3 L381 `one` template → revert to BM25) — but a handful are invented thresholds: vllm-5 L643 "P99/P50 TTFT < 3", vllm-1 L416 "< 0.4 命中率 / 5× P99:P50", ragflow-4 L632 "0.3～0.4 常見".
- "When it breaks" chains are the best part of the batch: vllm-3 L507–518 symptom→cause→fix→verify table; vllm-5 L495–505 TTFT = queue + prefill decomposition and L525–536; ragflow-1 L546–554 start-up failures (incl. the 384-dim silent failure); ragflow-5 L763–776 progress-percentage → stage mapping. rag-series has one such table (rag-5 L164–169 RAGAS metric → fix) and chatpdf none.
- Rubric gap in rag-series: zero concrete numbers across 2,570 lines (no ms, $, recall, QPS). rag-2's decision tree (L373–388) hinges on "10 萬 / 500 萬筆" cut-offs with no basis.

### Direction
- **Five-way overlap on the same ground**, none of it cross-linked (grep over the 13 RAG posts finds no link to any other series; only `langfuse-intro-part1` links in):
  - Hybrid search / RRF: rag-3 L23–152, ragflow-4 L227–345, chatpdf-1 L223–293, ai-eng 11-2, fde-core-concept-4.
  - Reranking: rag-3 L365–463, ragflow-4 L348–462, chatpdf-3 L172–199, fde-core-concept-5.
  - Chunking: rag-2 L22–178, ragflow-2 L184–385, chatpdf-1 L40–145, ai-eng 11-2.
  - RAG evaluation: rag-5 L27–214, chatpdf-3 L97–169, ai-eng 11-2, fde-core-concept-20.
  - GraphRAG / agentic RAG: rag-5 L218–588, ragflow-4 L468–504 and L635–661.
- Canonical version per topic (based on scope; fde-core 4/5/20 and ai-eng 11-2 were scored in B05/B09): **hybrid search** → `fde-core-concept-4-hybrid-search-rrf` (mechanism) with `ragflow-intro-part4` §二–三 as the production reference; **reranking** → `fde-core-concept-5` with ragflow-4 §四 for the weight math; **chunking** → `ragflow-intro-part2` (mechanism, `naive_merge` contract) with `chatpdf-1` as the hands-on implementation; **evaluation** → `fde-core-concept-20` + `ai-eng-11-2` for the metrics, `chatpdf-3` for a worked pipeline; **GraphRAG/RAPTOR** → `ragflow-intro-part4` §5; **vector-DB selection** → `rag-series-part2` is the only post that covers it and should be kept, refreshed; **inference serving** → `vllm-intro` is canonical and `ai-eng-11-1` (B09, Not ready) should link to it rather than restate PagedAttention.
- rag-series is the weakest of the four and mostly superseded: parts 1, 3 and 4 could be collapsed into a single "RAG 入門 + where to go next" post that links to the canonical versions above; parts 2 (vector DB) and 5 (RAGAS/LangGraph code) retain unique value.
- Gaps: nobody in the batch covers embedding-model selection/evaluation (MTEB, dimension/MRL trade-offs, multilingual) despite ragflow-3 L239's 384-dim trap; nobody covers RAG security (prompt injection via documents) — chatpdf-3 L202–223 touches the format-string variant only.
- Category fit: all 18 are `["all","ai","engineering"]` (+`infrastructure` on vllm 1/4/5, +`architecture` on vllm-3/ragflow-5) ✓. `tools` would also fit the ragflow and vllm series.

### Accuracy
- Verified fast-moving facts (see §Verified): vLLM 0.11 sha256 default, kv_block histograms (0.13+, sampled), `VLLM_USE_FASTOKENS`, `/v1/chat/completions/batch`, `FULL_AND_PIECEWISE` default, RAGFlow v0.27.0/0.27.1 and Go executor, LangChain 1.0 `langchain-classic` move, Qdrant `search` deprecation, chatPDF PRs #1/#2/#4 exist (#3 absent, #5 newer).
- Hard errors: vllm-1 L282 capacity (contradicts own formula); vllm-4 L546 cudagraph default; vllm-5 L335 LoRA memory vs its own formula; vllm-3 L422 EAGLE row; ragflow-2 L519 $900 vs $1,098; chatpdf-3 L198 sigmoid; chatpdf test counts (1 L323 / 2 L26 / 3 L286).
- Commands/code that will not run as written: vllm-1 L332 model id; vllm-4 L658–661 DP multi-node flags; rag-2 L140–143 and rag-4 L459–462 (LangChain ≥ 1.0), rag-2 L297 (qdrant-client ≥ 1.10 warns, newer removes).
- Stale-by-date: vllm-1 L38/L619, vllm-5 L80 "0.19.x / v0.19.1" for a Sept-2026 post (0.21 was 2026-05-15; docs now carry 0.30); rag-5 L578–582 "GPT-4.1 … 2025".
- Unverifiable source-tree claims (❓, not wrong): every file size, constant and port in ragflow 1–5 (e.g. ragflow-1 L120 "93 KB", L123 "ES 8.11.3", L485 "Python ≥ 3.13"; ragflow-3 L400–404 engine versions; ragflow-5 L627 GitHub language). The series' own footnotes say they were checked against `main`; a commit hash per post would make them checkable.
- Internal inconsistencies: vllm-1 L282 55 GB vs L351 48 GB; vllm-2 L119 "6 條"; vllm-2 L560 172K vs 180K (22 GB/128 KB); ragflow-3 L585 "3～6 GB" vs L587 "4～6 GB".

### Format / front matter
- Front matter complete on all 18; `weight` 1–5 contiguous within vllm/ragflow/rag-series; chatpdf has no `weight` (fine, nav is hand-written).
- readTime vs ≈ 32 lines/min: ragflow-4 (889 L / 22 min ≈ 28), ragflow-5 (886 / 21 ≈ 28), vllm-5 (816 / 21 ≈ 26), rag-5 (656 / 15 ≈ 20) understate by 5–7 min; chatpdf-1 (350 / 16 ≈ 11) overstates by 5.
- Diagrams over 80 columns (will wrap on phones): ragflow-5 51 lines (first L46), ragflow-4 48 (L83), ragflow-3 35 (L57), ragflow-1 31 (L142), vllm-1 28 (L172), ragflow-2 25 (L32), rag-5 19 (L121). The 系統效應 ASCII tables and directory trees are the usual culprits.
- Tags: vllm/ragflow/rag-series carry `"繁體中文"`; chatpdf does not — pick one convention. `"RKK"` is absent everywhere, which is correct (not an interview series).
- Opening 4-line contrast quote present in all vllm/ragflow posts and chatpdf (3-line); rag-series has none and opens on "前言".
- Links: every series-nav link resolves; rag-series and chatpdf use `**系列導覽**` lists, vllm/ragflow use ← / → pairs — both fine.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | major | vllm-intro-part1 L282 | "80 GB 卡上還有約 55 GB 給 KV cache … 8192 context … 400–600 條併發序列" contradicts the ledger (L351: 48 GB) and the formula at L395–402 (48 GB / 128 KB / 8192 = 48 seqs; 196 at 2K avg) | Replace with "48 GB → 393K tokens → ~48 條 at full 8192 context, ~200 條 at 2K average"; keep one KV-pool figure |
| 2 | major | vllm-intro-part4 L546 | `PIECEWISE`（預設）— vLLM docs: V1 with piecewise compilation defaults to `FULL_AND_PIECEWISE` (PIECEWISE is the "past default"; pooling models still PIECEWISE) | Mark `FULL_AND_PIECEWISE` as default; move the "試 FULL_AND_PIECEWISE" advice at L556/L713 to "already on; use `--compilation-config` only to turn it off" |
| 3 | major | vllm-intro-part4 L655–662 | DP=16 + EP across 2 nodes launched with `--nnodes 2 --node-rank --master-addr` (the TP/PP mp-backend flags); the EP guide's 2-node example uses `--data-parallel-size 16 --data-parallel-size-local 8` with a headless second node | Rewrite the command from the data-parallel/expert-parallel deployment doc and say which node is headless |
| 4 | major | vllm-intro-part1 L332 | `vllm serve meta-llama/Llama-3.3-70B-Instruct-FP8` — Meta publishes no FP8 3.3-70B; the vLLM-tested build is `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic` (or quantise online with `--quantization fp8`, which part 4 L422 itself recommends) | Use the RedHatAI id or the online-FP8 flag; also drop `--enable-prefix-caching` (L337) since L291 says V1 has it on by default |
| 5 | major | rag-series-part2 L140–143, part4 L459–462, part2 L297 | `langchain.retrievers.ParentDocumentRetriever`, `ContextualCompressionRetriever`, `LLMChainExtractor` and `langchain_community.vectorstores.Chroma` moved to `langchain_classic` / `langchain_chroma` in LangChain 1.0; `qdrant_client.search` is deprecated for `query_points` | Add a version banner like rag-5 L95 (pin `langchain<1` or update imports); switch Qdrant to `client.query_points(...)` |
| 6 | major | chatpdf-rag-optimization-part3 L198 | "門檻預設 0.0,約等於 sigmoid(0.5)" — a logit threshold of 0.0 corresponds to **sigmoid(0) = 0.5**; the sentence is inverted | "logit 0.0 ⇔ sigmoid 0.5，即『相關的機率 ≥ 不相關』" |
| 7 | major | vllm-intro-part5 L335 | `max_loras × rank × 層數 × hidden × 2 × 2 bytes` = 268 MB for the stated case, not "約 1.5 GB" | Either add the per-layer module count (≈ 7 projections, which gets ~1.9 GB) to the formula or change the example to ~0.3 GB |
| 8 | major | rag-series-part1–5 (whole) | No thesis; no number in 2,570 lines; three of the five parts are fully covered by ragflow-4, fde-core-concept-4/5/20 and ai-eng 11-2 | Collapse parts 1/3/4 into one "RAG 入門與導讀" post that links to the canonical versions; keep part 2 (vector-DB selection) and part 5 (RAGAS/LangGraph code) after the import refresh |
| 9 | minor | vllm-intro-part2 L470, part5 L487–489, L516–518 | `vllm:kv_block_*` histograms are sampled (1 %) and only emitted with `--kv-cache-metrics-sample`; the PromQL rule at part5 L516 returns nothing on a default server | Add the flag and the sampling caveat next to the first mention |
| 10 | minor | vllm-intro-part3 L422, L257–265, L49 | EAGLE row 3.2 / 2.3× should be 3.05 / 2.2×; four rounds of 8,132+8,192 do not cover 32,768 (needs 5); "需要 16 輪" is 17; "17 / (4×9)" divides tokens by cells | Recompute; or state the formula once and show one worked row |
| 11 | minor | vllm-intro-part1 L38/L619, part5 L80 | "2026 年 9 月，版本參考 0.19.x" / `vllm/vllm-openai:v0.19.1` for a 2026-09-11 post — 0.21.0 shipped 2026-05-15 and docs now list ≥ 0.30 | Pin to the version actually read and give the commit; or re-check against the current release |
| 12 | minor | ragflow-intro-part2 L519 | "約 900 美元" — 6.1 M × (800 × $0.15 + 100 × $0.60)/1 M = $1,098 | "約 1,100 美元" |
| 13 | minor | chatpdf-1 L323, chatpdf-2 L26/L248, chatpdf-3 L286 | 128 → "165 (+30)" → "235 (+11)" cannot all be true; PR #3 is never covered and PR #5 (different-family judge) now exists | Reconcile counts against the PRs, mention #3 in part 2 or 3, and add a part 4 or a note for #5 |
| 14 | minor | ragflow-intro-part1/2/3/4/5 (diagrams) | 25–51 code-block lines per post exceed 80 cols (directory trees, 系統效應 ASCII tables) | Narrow the 系統效應 tables to Markdown tables; wrap tree comments |
| 15 | minor | ragflow-intro-part3 L444 | "比 ES 預設的 1s 一樣（1000ms = 1s）" — garbled | "與 ES 預設的 1s 相同" |

## Recommendations

1. **Fix the five actionable numbers/commands in vllm-intro before anything else** (findings 1–4, 7, 9–11). WHY: this is the only series in the batch a reader will copy into a shell; a capacity claim 8× too high and a launch command that will not start are the kind of error that costs a day. HOW: one pass with `python3` on every derived figure, run each `vllm serve` line against `--help` on the version named in the footnote, and replace "0.19.x" with the commit hash actually read.
2. **Make the ragflow series' footnotes checkable.** WHY: forty-odd file sizes, constants and ports per post are presented as "實際核對" but a reader cannot tell which commit; RAGFlow is mid-Go-migration and `task_executor.py` is being split. HOW: add `commit abc1234 (2026-09-xx)` to the italic footer of each part and date-stamp the star count.
3. **Collapse rag-series parts 1/3/4 and refresh 2/5.** WHY: five posts with no thesis and no numbers duplicate ground that ragflow-4, fde-core-concept-4/5/20 and ai-eng 11-2 cover with mechanism and weights. HOW: rewrite part 1 as an on-ramp whose每 section ends with "深入請看 → [canonical]"; in part 2 update to `langchain_chroma`/`query_points` and source the size thresholds; in part 5 keep the RAGAS note and LangGraph code, drop GraphRAG (point at ragflow-4 §5).
4. **Cross-link the 13 RAG posts and the three sibling posts.** WHY: zero inbound/outbound links today; the site has a canonical post for every RAG topic but readers cannot find it. HOW: add a "相關文章" block at the end of each (the ragflow 系列導航 section is the natural place); have ai-eng 11-1 link to vllm-intro-2/3 instead of restating PagedAttention.
5. **Give chatpdf one measured number per post.** WHY: an "optimization" series that says twice "本 PR 未量測" cannot show that anything improved; the repo already ships `rag_evaluation.md` (Hit@k, MRR, nDCG) and part 3 builds the eval-history table. HOW: run the eval once on a fixed PDF set for before/after each PR and put Hit@5 / MRR / p95 latency in the 系統效應 tables; fix the sigmoid sentence and the test counts while there.
6. **Put the `--kv-cache-metrics-sample` caveat where the kv_block metrics are first introduced** (vllm-2 L470). WHY: the "鐵證" rule and the alert at vllm-5 L516 are the best operational advice in the series and will silently return no data without the flag. HOW: one sentence plus the flag in the Phase-2 K8s args.
7. **Narrow the wide ASCII blocks in ragflow and vllm-1.** WHY: 25–51 lines per post beyond 80 columns wrap on phones and turn the 系統效應 tables into noise. HOW: convert 系統效應 and 為什麼選 X 不選 Y blocks to Markdown tables (the house format allows it), wrap tree comments onto their own line.
8. **Align readTime** on ragflow-4/5, vllm-5, rag-5 (understated 5–7 min) and chatpdf-1 (overstated 5). WHY/HOW: trivial, and `review_posts.py --strict` would flag it.
9. **Add the two missing topics to the roadmap**: embedding-model selection (dimension/MRL/multilingual — the 384-dim trap in ragflow-3 L239 is the hook) and document-borne prompt injection in RAG (chatpdf-3 L202–223 is the only touch). WHY: every series assumes the embedding model and ignores adversarial documents.

## Verified / unverified claims

- ✅ vllm-1 L60 — 140 GB / 3.35 TB/s ≈ 24 tok/s (23.9).
- ✅ vllm-1 L68, L87 — vLLM paper: 60–80 % KV waste, up to 24× vs HF Transformers, 3.5× vs TGI, <4 % waste.
- ✅ vllm-1 L363–367 — KV bytes/token: Llama-3-8B 128 KB, 70B 320 KB, Llama-2-13B 800 KB (recomputed).
- ✅ vllm-1 L395–402 — 48 GB / 128 KB = 393,216 tokens; /2000 ≈ 196.
- ❌ vllm-1 L282 — "400–600 條併發序列 at 8192 context" (own formula gives 48).
- ❌ vllm-1 L332 — `meta-llama/Llama-3.3-70B-Instruct-FP8` (no such Meta repo; RedHatAI/ProbablyFaiz community builds only).
- ❓ vllm-1 L22 — "9.1 萬顆星、2.2 萬 fork" (unchecked); L38/L619 "0.19.x as of 2026-09" (version exists but 0.21 shipped 2026-05-15; stale).
- ✅ vllm-1 L409 — official docs: disaggregated prefill "does not improve overall throughput".
- ✅ vllm-2 L152, L384 — sha256 default prefix-cache hash since v0.11; `sha256_cbor`, `xxhash` options.
- ✅ vllm-2 L350 — paper: parallel sampling/beam search memory −55 %, throughput up to 2.2×.
- ✅ vllm-2 L470, vllm-5 L487–489 — `vllm:kv_block_lifetime_seconds`, `_idle_before_evict_seconds`, `_reuse_gap_seconds` exist (PR #27793, docs 0.13+); ⚠ sampled, gated by `--kv-cache-metrics-sample` — not stated.
- ✅ vllm-2 L96 — Phase-1 cost 64 × 8192 × 128 KB = 64 GB.
- ❓ vllm-2 L119 — "從 6 條併發變成 190+" (6 unexplained); L560 172K (recomputes 180K).
- ✅ vllm-3 L278–283 — official tuning guidance (2048 for ITL, 8192+/">8192 on large GPUs" for TTFT/throughput).
- ✅ vllm-3 L404 — E[tokens] = (1−α^(k+1))/(1−α); rows 1,2,4,5 recompute; ❌ L422 EAGLE row (3.05 / 2.2×).
- ✅ vllm-3 L485–498 — `--speculative-config` JSON with `method`, `num_speculative_tokens`, `prompt_lookup_max/min`.
- ✅ vllm-3 L517, vllm-5 L245/L531 — `VLLM_USE_FASTOKENS` exists (fastokens BPE backend, Crusoe; patched in `get_tokenizer`).
- ❓ vllm-3 L167 — "concurrent partial prefills … 進行中" (not checked).
- ✅ vllm-4 L203–209 — 8192 × 8192 × 2 B = 128 MB; × 160 = 20 GB; 22 ms NVLink / 625 ms PCIe 4.0 x16.
- ✅ vllm-4 L212, L246 — TP intra-node / PP inter-node; PP when GPU count does not divide head count.
- ❌ vllm-4 L546 — `PIECEWISE` as default (docs: `FULL_AND_PIECEWISE` on V1 with piecewise compilation).
- ❓ vllm-4 L658–661 — DP+EP 2-node launch with `--nnodes/--node-rank` (EP doc uses `--data-parallel-size-local` + headless node); L351 `NCCL_TIMEOUT` (not a documented NCCL variable); L399–407 hardware matrix; L590 XFormers backend in V1.
- ✅ vllm-5 L194 — `/v1/chat/completions/batch` listed in vLLM "Online Serving" docs.
- ✅ vllm-5 L231, L405, L418, L423 — `structured_outputs` extra_body key, `StructuredOutputsParams`, `--structured-outputs-config.backend`.
- ✅ vllm-5 L283–290, L304 — LoRA flags and `VLLM_ALLOW_RUNTIME_LORA_UPDATING`; L491 removed V0 metrics; L666–675 `vllm bench {throughput,serve,latency}`; L726 $46,720/month.
- ❌ vllm-5 L335 — "約 1.5 GB" vs own formula (268 MB).
- ✅ ragflow-1 L627, ragflow-5 §七 — RAGFlow v0.27.0 (2026-08-20, "task executor migration to go") and v0.27.1 image exist.
- ✅ ragflow-1 L300, ragflow-2 L508–517 — 2 M chunks × 3 + 2 × 50K = 6.1 M calls.
- ❌ ragflow-2 L519 — "約 900 美元" (recomputes $1,098).
- ❓ ragflow-1 L22 stars/forks, L120 "93 KB", L123 "ES 8.11.3", L272 `MEM_LIMIT 8073741824`, L485 "Python ≥ 3.13", L485 "Docker ≥ 24.0.0 / Compose ≥ v2.26.1"; ragflow-2 L440 "2025-10-15"; ragflow-3 L400–404 engine versions; ragflow-5 L627 GitHub language = Go; all `conf/`, `rag/nlp/search.py` constants in ragflow-3/4 (0.1/0.9, 0.63×0.8→0.3, 1024/2048, 30/20/10/2 boosts, 0.001,1) — plausible, consistent across the five posts, unverifiable without the tree.
- ✅ ragflow-3 L587 — 768 × 4 B = 3 KB/chunk → 3 GB per 1 M vectors; ragflow-4 L290 — 64 × 768 × 4 B = 192 KiB.
- ✅ rag-1 L139–264 — `openai.OpenAI`, `chromadb.Client`, `langchain_text_splitters.RecursiveCharacterTextSplitter` current.
- ❌ rag-2 L140–143, rag-4 L459–462 — `langchain.retrievers.*`, `langchain_community.vectorstores.Chroma` (moved to `langchain_classic` / `langchain_chroma` in LangChain 1.0).
- ❌ rag-2 L297 — `QdrantClient.search` (deprecated; `query_points`).
- ✅ rag-2 L229–259 — Pinecone `ServerlessSpec` API current; L317–341 pgvector HNSW/`<=>` syntax correct.
- ✅ rag-3 L43 — BM25 formula; L53–63 RRF with k = 60.
- ✅ rag-5 L95 — RAGAS 0.2 renames (`user_input`, `retrieved_contexts`, `response`, `reference`; `EvaluationDataset`/`SingleTurnSample`).
- ✅ rag-5 L446–560 — LangGraph `StateGraph`/`START`/`END`/`ToolNode`/`bind_tools` current.
- ✅ chatpdf-1 L36, chatpdf-2 L20, chatpdf-3 L28 — PRs #1, #2, #4 exist with the stated titles (yennanliu/chatPDF); PR #3 absent from the list; PR #5 "grade live answers with a different-family judge" post-dates the series.
- ✅ chatpdf-1 L178–216 — BM25 (Lucene IDF variant) correct; L278–286 min-max normalisation correct.
- ❌ chatpdf-3 L198 — "0.0 約等於 sigmoid(0.5)" (sigmoid(0) = 0.5).
- ❓ chatpdf-1 L323 "128 測試", chatpdf-2 L26 "165 (+30)", chatpdf-3 L286 "235 (+11), 覆蓋率 90.9 %" — not reconcilable as stated; not checked against the repo CI.
