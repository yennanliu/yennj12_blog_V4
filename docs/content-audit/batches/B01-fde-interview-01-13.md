# B01-fde-interview-01-13 — fde-interview-guide parts 1–13

Reviewed 2026-10-09. 13 Traditional-Chinese interview-prep posts (5,274 lines). Every post was read in full;
derived numbers recomputed with python3; one fast-moving product claim (ADK `AgentTeam`) checked against the
ADK docs. Mechanical baseline (`inputs/mechanical-baseline.txt` L14–29, L53–56, L98–101, L143–146, L177–204)
already records for every post: under the 600-line target, no 三個演進階段, 0 decision tables, and for
parts 2/3/4/5/6/9/11 a "Google" mention; parts 5/8/9 have 0 and part 6 has 1 ASCII box diagram. Those are
referenced, not repeated, below.

## Batch summary

These thirteen posts are two different series wearing one name. Parts 1–9 (dated 2026-05-30/31) are the
original "面試官視角" guide: 面試情境 → numbered concept sections → 地雷題 → 面試回答完整示範, 340–490 lines,
ASCII-heavy in 1/2/4/7 and text-only in 3/5/8/9. Parts 10–13 (2026-06-03, "RKK 實戰") are tighter
system-design briefs with a 核心問題 → 系統全貌 → strategies → decision framework → 快速複習卡 shape, and
they are the best-built posts in the batch (part 10 scores 4.5). Accuracy is generally good — every cost,
latency and percentage I recomputed matches — but four claims a reader would repeat are wrong or dated:
ADK "內建 AgentTeam" (P2 L274), "Gemini 2B" as an open fine-tuning base (P3 L226), "RAG 用的 Embedding 模型
通常是 Encoder-based" (P3 L329, contradicted by P5's own E5-mistral row), and the client-communication script
that reads Faithfulness 0.85 as "15 of 100 answers hallucinate" (P12 L309). The "no Google" series rule is
broken explicitly in P2 (a whole section titled 「Google ADK 的定位」, "FDE 面試 Google 職位"), P9 L225
("Google JD") and P11 L6/L285 ("Google Doc"), while Vertex AI / GCP / Gemini / BigQuery appear in nearly every
post — the rule as enforced is cosmetic. Eight posts still carry a 面試回答完整示範 model-answer section
that the house format dropped. Overlap is heavy: the identical embedding-model table and its "2025 年撰文"
caveat appear three times (P3/P5/P9), P5 restates ~40% of P1, P8 restates P3's Transformer section.
Verdicts: **5 Ready** (1, 4, 7, 10, 13), **7 Needs revision** (2, 3, 5, 6, 9, 11, 12), **1 Not ready** (8).
On backfilling the house format: decision tables with flip conditions would add real value to 1/2/4/5/7/10/13
because the comparisons already exist and only lack the flip condition; 三個演進階段 fits only 2 and 4 (the
only posts that design a concrete system) and would be padding in the fundamentals posts 3/8/9.

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| part1-rag-zh.md | 387 | 4 | 5 | 3 | 4 | 4 | 4 | 4.0 | Ready | L111 "Fine-tuning 幻覺風險相對高" asserted with no mechanism; L292 Vertex AI product in a "no Google" post; L354 model-answer section dropped from format |
| part2-agent-zh.md | 379 | 3 | 4 | 3 | 4 | 4 | 2 | 3.3 | Needs revision | L263–288 whole section on Google ADK ("FDE 面試 Google 職位") breaks the series hard rule; L274 "內建 AgentTeam" is not an ADK primitive |
| part3-ml-fundamentals-zh.md | 387 | 3 | 4 | 3 | 2 | 4 | 3 | 3.2 | Needs revision | L226 "Gemini 2B" does not exist as a fine-tunable open model (Gemma 2B); L329 "RAG embedding 通常 Encoder-based" is stale and contradicted by P5 L120 |
| part4-system-design-zh.md | 459 | 4 | 5 | 4 | 4 | 4 | 3 | 4.0 | Ready | L321–323 NL2SQL success rates "~90% / ~60–70%" labelled 實務參考 but unsourced; L77/L117 Google Workspace |
| part5-rag-deep-dive-zh.md | 403 | 4 | 4 | 3 | 2 | 2 | 3 | 3.0 | Needs revision | L102–287 five `##` sections have no 一…十 numeral, so numbering runs 一 → 五; L57 recommends fixed-size chunking for 合約 while P1 L150 recommends Parent-Child for the same documents |
| part6-rag-eval-zh.md | 446 | 4 | 4 | 4 | 3 | 3 | 3 | 3.5 | Needs revision | L338 cost model assumes a 1,000-token *query* embedding (a query is ~20–50 tokens; the $2/day line is 20–50× too high); numbering stops after 四 (L359–416) |
| part7-agent-design-zh.md | 448 | 4 | 4 | 4 | 5 | 4 | 4 | 4.2 | Ready | L221–223 "40,000 tokens 已接近許多模型的上限" is a 2023 statement in a 2026 post; L147 "Needle-in-a-Haystack" misapplied to tool selection |
| part8-ml-fundamentals-zh.md | 485 | 4 | 4 | 2 | 1 | 2 | 4 | 2.8 | Not ready | No thesis, no 面試情境, no 地雷題, 0 diagrams, no FDE framing: a textbook cheat-sheet (L20–465) that does not belong to an interview-design series as written |
| part9-llm-core-zh.md | 483 | 4 | 4 | 3 | 2 | 3 | 2 | 3.0 | Needs revision | L225 "**Google JD** 為什麼特別點名 ReAct" — explicit rule break; L315–324 third copy of the embedding table + caveat |
| part10-context-management-zh.md | 360 | 5 | 5 | 4 | 5 | 4 | 4 | 4.5 | Ready | L19–40 the only post that states the O(n²)/TTFT nuance correctly; L348–356 still ends in a model answer |
| part11-agent-debugging-zh.md | 343 | 4 | 5 | 3 | 5 | 3 | 2 | 3.7 | Needs revision | L137–160 promises five fault modes, L162–251 diagnoses only three (Task Drift and Context Confusion get no section); L6/L285/L287 "Google Doc" |
| part12-agent-evaluation-zh.md | 343 | 3 | 5 | 4 | 5 | 4 | 4 | 4.2 | Needs revision | L309 "0.85 意思是每 100 個回答裡有約 15 個包含知識庫以外的資訊" misreads RAGAS faithfulness (mean fraction of *claims* supported, not fraction of *answers*) in the client-facing script |
| part13-prompt-injection-zh.md | 351 | 4 | 5 | 4 | 4 | 4 | 3 | 4.0 | Ready | L6 description promises "危險 10 倍"; the number never appears in the body — invented headline figure |

Overall = unweighted mean of the six (no finance posts). Model-answer sections and the series-format
warnings are scored as minor for these pre-rule posts; the verdicts above turn on content findings.

## Patterns

### Content quality
- Parts 10–13 and 7 are the model for the series: one tension stated up front (P10 L13–15 "LLM 是無狀態的，但對話是有狀態的"; P13 L13–15 "嘴巴問題 → 手腳問題"), strategies with 為什麼選 / 為什麼不選 pairs (P10 L104–226), a decision tree (P10 L228–244), and trade-off sections (P13 L301–325).
- Parts 3, 8, 9 are reference cards, not arguments. P8 has no 面試情境, no interview framing until L452, and ends on a checklist (L465–481); P3 L13 even redirects readers to P8/P9 as "更完整的深度版本", conceding it is a summary of posts that come later in the series.
- The 地雷題 sections are the strongest interview-specific content in 1–7 (P1 L319–350, P4 L376–412, P6 L372–412): a sharp follow-up question with a short, mechanism-level answer. They do what the house decision tables do, without the table.
- Eight posts end in a 面試回答完整示範 scripted answer (P1 L354, P2 L343, P3 L355, P4 L415, P5 L367, P6 L416, P7 L408, P9 L421; P10 L348 "完整範例回答" is the same thing). CLAUDE.md dropped this section; the checker only greps the old heading 「面試答題要點」 (review_posts.py L321), so these copies are invisible to CI.

### Structure (does the house format help or pad?)
- Section numbering is broken in three posts: P5 jumps 一 → (five unnumbered `##`) → 五/六 (L27, L102–287, L330, L367); P6 numbers 一–四 then drops numerals for 小結/地雷題/示範 (L359–416); P9 numbers 一–三 then stops (L377–452). P8 ends with an unnumbered `## 下一篇` heading (L483).
- 三個演進階段 would be padding for 3/8/9 (no system to evolve) and for 1/5/6 (component-level posts). It would add value in exactly two places: P2's customer-service agent (L59–126 already has a single-stage architecture and a "日均 query 量" question it never answers) and P4's two designs (L45–360), where POC→MVP→Scale would give the RBAC/cache/dry-run choices their scale thresholds.
- 「為什麼選 X 不選 Y」 tables are cheap to backfill because the comparisons already exist as prose or 2-column tables: P1 L97–106 (RAG vs FT), P2 L96–118 (function calling vs classifier), P4 L108–121 (API key vs JWT) and L131–162 (post- vs pre-filter), P5 L339–350 (HNSW vs IVF), P7 L116–132 (ReAct vs Planner), P10 L246–256, P13 L301–325. What they all lack is the flip condition — that, not the table shape, is the missing content.
- Padding to 600 lines would hurt: P10–13 at 343–360 lines are the highest-scoring posts; P8 at 485 is the lowest.

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Numbers that are derived and labelled recompute correctly: P4 L344–348 (800→500 ms = 37.5%), P4 L278 (4.2/3.8 = +10.5%), P3 L232–234 (LoRA 24,576/589,824 = 4.2%), P6 L344–348 ($2+$15+$15 = $32/day = $960/mo), P10 L34–38 (50×750 = 37,500 = 29% of 128K), P11 L116–122 (trace sums to 1,555 ms), P12 L142–152 ($0.005125 × 10K × 30 = $1,538; 40% cache ≈ $615).
- Thresholds presented as design constants are invented but mostly flagged: P2 L209 "相似度 > 90%", P3 L185 "Val Loss 上升超過 5%" called 標準做法 (P3 L379), P6 L327 "相似度 > 0.95", P11 L166/L187 0.7/0.8 (explicitly caveated at L198 — the right pattern), P10 L325–328 "建議使用上限 700K" (caveated L330).
- Unsourced empirical claims: P4 L321–323 NL2SQL success rates; P1 L249 reranker "+200–500 ms"; P10 L219 vector search "50–200 ms"; P11 L101–107 dashboard numbers (monthly $450 implies ~1,765 req/day — never stated).
- "When it breaks" is present in 10/13 (P10 L350–356 失效場景, P13 L271–299, P7 L257–290) and absent in 3/8/9.
- Stale depth: P7 L221–223 treats 40K tokens as near the ceiling; P6 L276 routes simple queries to "GPT-3.5"; P3 L63–66 presents sin/cos positional encoding as *the* mechanism (P8 L424 correctly says RoPE).

### Direction (overlap, gaps, stale topics, category fit)
- Triple duplication: embedding-model table + identical "模型清單以 2025 年撰文時為準" note in P3 L104–111, P5 L114–123, P9 L317–324; task_type table in P5 L135–143 and P9 L327–336.
- P5 restates P1: GPT-4o/BM25 example (P1 L206–211 ↔ P5 L209–215), RRF k=60 (P1 L323–330 ↔ P5 L229–238), bi-/cross-encoder (P1 L229–247 ↔ P5 L255–262), context-overflow strategies (P1 L299–316 ↔ P5 L287–326). P8 L369–460 restates P3 L29–81 (Transformer). P9 L28–60 restates P3 L249–268 (tokens).
- Cross-batch overlap the coordinator should track: P7 §五 Memory (L292–350) vs part 14 and fde-core-concept-2; P10 vs fde-core-concept-1; P11 vs part 41 and fde-core-concept-22; P12 §五 LLM-as-judge vs part 50 and fde-core-concept-19; P13 vs parts 20/45 and fde-core-concept-6/7; P5 hybrid/rerank vs fde-core-concept-4/5.
- The "no Google" rule is enforced on the word, not the vendor: P1 L292, P3 L117, P5 L171/L273, P6 L148, P10 L325, P12 L142 all name Vertex AI / GCP / Gemini products. Either the rule means "do not name the employer" (then P2 L265, P9 L225, P11 L287 are the real breaches and Vertex is fine) or it means vendor-neutral (then 7 posts fail). CLAUDE.md should say which.
- Category fit: all 13 carry `["all","ai","engineering"]`. P4, P10, P11, P13 are architecture posts (`architecture` would fit better than `engineering`); P8 is an ML primer that fits `ai` alone.
- Dates: all 13 are dated 2026-05-30 … 06-03 yet five contain "2025 年撰文時" caveats (P3 L111, P5 L123, P6 L342, P9 L82/L324, P10 L330) — the front-matter dates and the in-body dates disagree by a year.

### Accuracy
- ❌ P2 L274 "Google ADK … 內建 AgentTeam": ADK's multi-agent model is `sub_agents` + `SequentialAgent`/`ParallelAgent`/`LoopAgent`; "Agent Team" is a tutorial title, not a feature. ❓ P2 L281 "Vertex AI Agent Builder（低代碼部署）" — product naming has shifted (Agent Engine is the runtime); could not confirm the current label.
- ❌ P3 L226 "Gemini 2B → 需要數十 GB GPU RAM": Gemini has no 2B open weights; the line means Gemma 2B (L227 says Gemma 9B). The memory estimates themselves are plausible (16 B/param full FT ≈ 32 GB / 144 GB).
- ❌ P3 L326–329 "Decoder-only … 設計目標是生成，不是 Embedding … 所以 RAG 用的 Embedding 模型通常是 Encoder-based": P5 L120 itself lists `E5-mistral-7b` (decoder-based) as "開源裡效果最好之一", and the caveat at P3 L111 names `gemini-embedding-001` (Gemini-based). The 地雷 answer teaches a reader to say something an interviewer can refute.
- ❌ P12 L309: RAGAS faithfulness is the mean over answers of (supported claims / total claims); 0.85 does not mean 15% of answers contain out-of-KB content. The three-tier advice at L310–312 is fine; the gloss is wrong.
- ⚠ P6 L338/L344 "每次 query embed：~1,000 tokens" — a query is tens of tokens; the arithmetic is right, the assumption is off by >20×. Harmless to the total ($2 of $32) but it is the line an interviewer would poke.
- ⚠ P5 L215 "BM25 就是傳統的 TF-IDF 關鍵字搜尋" — BM25 is a probabilistic ranking function with saturation and length normalisation; "TF-IDF 的改良版" would be accurate. P5 L347 "HNSW 適合百萬以內" understates HNSW (the limit is RAM, not count).
- ⚠ P1 L111 / P3 L212 "Fine-tuning 幻覺風險 較高": no mechanism given; SFT on narrow data can *increase* confident errors, but the blanket row invites an interviewer's "why?".
- ⚠ P7 L147 labels tool-schema dilution "Needle-in-a-Haystack" (that term is long-context retrieval); P7 L221–223 "40,000 tokens … 接近許多模型的上限" is false for every 2025–26 frontier model (the post's own P9 L74–80 table lists 128K–1M).
- ✅ Everything else checked (see last section): RRF k=60, cross-encoder O(N), text-embedding-3-small 1536 / -large 3072 / BGE-M3 1024 / text-embedding-004 768 / E5-mistral 4096, task_type names, BigQuery dry run, Gemini 1.5 Pro $1.25/$5, 1.5 Flash $0.075/$0.30, context-window table, output/input price ratio 3–5×, `MultipleNegativesRankingLoss`, Vertex Ranking API, Transformer/attention/F1 formulas.

### Format / front matter
- Front matter is complete and valid in all 13 (categories closed-set, `authors: ["yen"]`, `weight` 1–13, tags include RKK/Interview/Cloud). No mechanical errors.
- readTime drifts high in the RKK posts: P11 17 min for 343 lines (~10), P12 15/343, P13 15/351, P10 16/360, P2 14/379, P5 15/403 — within the checker's tolerance but 40–70% over the 32-lines/min rule.
- Series nav is inconsistent: P4, P10–13 use the 「系列導航 ← | →」 footer; P1–3, P5–7 have only a 下一篇 line; P8 uses a `## 下一篇` heading; P9 ends with a 系列總結 that calls itself the last post (L452 "九篇走完") before linking part 10. All links resolve.
- Heading numerals missing in P5 (5 sections), P6 (3), P9 (3), P8 (2) — see Structure.
- P13 L6 and P11 L6 descriptions are the only ones that over-promise ("危險 10 倍"; "Google Doc 模擬情境").

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | major | part2-agent-zh.md:263–288 | Section 「六、Google ADK 的定位」+ L265 "FDE 面試 Google 職位" + L6 description: explicit, repeated breach of the series "no Google" rule | Rename to 「ADK 的定位」, drop L265, say "雲端廠商的 Agent 框架"; description → "ADK 定位" |
| 2 | major | part2-agent-zh.md:274 | "內建 AgentTeam" — not an ADK primitive | "內建 SequentialAgent / ParallelAgent / LoopAgent 與 sub_agents 委派" |
| 3 | major | part3-ml-fundamentals-zh.md:226 | "Gemini 2B" as a full-fine-tuning base | "Gemma 2B" |
| 4 | major | part3-ml-fundamentals-zh.md:326–329 | 地雷 answer claims RAG embeddings are "通常 Encoder-based"; contradicted by P5 L120 and P3 L111 | Rewrite: "歷史上以 encoder 為主；現今前段班（gemini-embedding, e5-mistral, NV-Embed, Qwen3-Embedding）多為 decoder 微調 + pooling；關鍵是對比學習目標，不是架構" |
| 5 | major | part12-agent-evaluation-zh.md:309 | Faithfulness 0.85 glossed as "每 100 個回答約 15 個" hallucinate | "平均每個回答有 15% 的陳述找不到文件依據——可能集中在少數回答，也可能散佈在多數回答，要看分佈" |
| 6 | major | part11-agent-debugging-zh.md:137–251 | 「五大故障模式」 tree lists five; only 幻覺/工具失敗/無限迴圈 get diagnosis sections | Add 故障四 (Task Drift: goal-distance check, P7 L275–279 has the material) and 故障五 (Context Confusion: session-id in every trace, isolation test) |
| 7 | major | part8-ml-fundamentals-zh.md:1–485 | No thesis, no 面試情境/地雷/系列 shape, 0 diagrams; a textbook summary in an interview-design series | Either (a) re-frame each section with the FDE question it answers and add 2 diagrams (attention flow, bias/variance curve), or (b) move it out of the numbered series as a "foundations appendix" and let P3 point to it |
| 8 | major | part5-rag-deep-dive-zh.md:102–287 | Five `##` sections unnumbered; numbering reads 一, …, 五, 六 | Number 二–六, renumber 地雷/示範 to 七/八 |
| 9 | major | part9-llm-core-zh.md:225 | "**Google JD** 為什麼特別點名 ReAct" | "JD 為什麼特別點名 ReAct" (P12 L133 and P13 L224 already use the anonymous "JD") |
| 10 | minor | part11-agent-debugging-zh.md:6, 285, 287 | "Google Doc 模擬情境" ×3 | "共享文件模擬情境" |
| 11 | minor | part6-rag-eval-zh.md:338, 344 | Query embedding assumed at 1,000 tokens | "~50 tokens"; the line becomes ~$0.10/day and the point ("embedding is noise next to generation") gets stronger |
| 12 | minor | part7-agent-design-zh.md:221–223 | "40,000 tokens … 接近許多模型的上限" | Reframe as cost/latency/lost-in-the-middle at 40K, not a hard ceiling; cite P9 L74–80 |
| 13 | minor | part13-prompt-injection-zh.md:6 | "危險 10 倍" never supported in the body | Drop the multiplier or make it the body's argument (attack surface = tools × scopes) |
| 14 | minor | part5-rag-deep-dive-zh.md:57 vs part1-rag-zh.md:150 | Contracts → fixed-size (P5) vs → Parent-Child (P1) | Align: fixed-size for tabular 財報, Parent-Child for 合約 |
| 15 | minor | parts 1,2,3,4,5,6,7,9,10 (L354/343/355/415/367/416/408/421/348) | 面試回答完整示範 model-answer sections survive under a heading the checker does not grep | Decide: delete to match CLAUDE.md, or keep and add 「面試回答完整示範」 to review_posts.py L321 so the rule is honest |

## Recommendations

1. **Fix the four factual items (findings 2–5) first.** WHY: they sit in 地雷 answers and a client script — exactly the lines a reader memorises and repeats. HOW: one-line edits in P2/P3/P12; no restructuring.
2. **Decide what "no Google" means and apply it once.** WHY: the rule currently catches "Google Workspace" (P4 L77) but not a section built around Vertex/GCP (P2 L278–288), and seven posts name Google products. HOW: if the intent is "never name the employer", keep the grep and fix P2/P9/P11 only; if it is vendor-neutral, extend the checker to Vertex/GCP/Gemini/BigQuery and rewrite those lines as "雲端廠商的託管服務". Record the choice in CLAUDE.md §6.
3. **Backfill 「為什麼選 X 不選 Y」 tables only where a comparison already exists, and add the flip condition.** WHY: P1/P2/P4/P5/P7/P10/P13 already contain 1–3 comparisons each (lines in Structure above); what they lack is "when Y becomes right". HOW: convert each to the house 3-column shape and add a 翻轉條件 row; 2–4 decisions per post, not 4–6 — do not invent decisions to hit the quota.
4. **Backfill 三個演進階段 in P2 and P4 only.** WHY: they are the only posts that design a whole system, and P2 L63 asks "日均 query 量是多少？" without ever answering it. HOW: a 60–90-line phase section per post with the thresholds the series uses elsewhere (<10K / 10K–200K / 200K–1M users); skip it for component-level and fundamentals posts, where it would be padding.
5. **De-duplicate the fundamentals trio (3/8/9).** WHY: the embedding table and caveat appear three times; Transformer twice; tokens twice. HOW: keep one embedding table in P9 (it is the embedding post), link to it from P3/P5; cut P3 §一 Transformer to a pointer to P8 §六; or merge P3 into P8+P9 and leave a redirect stub.
6. **Deal with P8 explicitly** (finding 7). WHY: it is the lowest-scoring post and the only one with no interview framing; it drags the series average while being accurate. HOW: option (b) in finding 7 is cheapest — reclassify it as the series' appendix and drop the `weight: 8` slot, or add a 面試情境 and two diagrams.
7. **Retire or legitimise the model-answer sections** (finding 15). WHY: CLAUDE.md says the section was dropped, nine posts still have it under a different heading, and CI cannot see it. HOW: either delete them (the 地雷 sections already cover the content) or add the heading to the checker and amend CLAUDE.md to say the 示範 form is allowed in parts 1–9.
8. **Fix numbering and nav mechanically** (findings 8, and Format bullets). WHY: zero-risk edits that make the series look like one series. HOW: number P5/P6/P9 headings; replace P1–3, P5–8's 下一篇 lines with the 「系列導航 ← | →」 footer used from P4 and P10 onward; adjust readTime in P2/P5/P10–13 to the 32-lines/min rule.
9. **Reconcile dates.** WHY: front matter says May–June 2026, bodies say "2025 年撰文時"; a reader cannot tell which is the as-of date for the pricing/model tables. HOW: either set `date:` to the original 2025 dates (and add `lastmod:`), or rewrite the five caveats as "本文撰寫時（2026-05）".
10. **Add "Google" to a date-stamped product-list pattern.** WHY: P6 L276 (GPT-3.5), P7 L221, P9 L74–80 and P10 L323–328 will keep going stale. HOW: keep one model/price table in P9 with an as-of line, and have P6/P10/P12 cite it instead of carrying their own.

## Verified / unverified claims

- ✅ part1-rag-zh.md:323–330 — RRF score = Σ 1/(k+rank), k=60 default (Cormack et al.); same at part5 L229–238
- ✅ part1-rag-zh.md:336–343 — cross-encoder reranking is O(N) over documents, hence two-stage retrieval
- ✅ part3-ml-fundamentals-zh.md:102–109 — dims: text-embedding-004 768, text-embedding-3-small 1536, BGE-M3 1024, bge-large-zh 1024; part5 L118 text-embedding-3-large 3072; part5 L120 e5-mistral-7b 4096
- ✅ part3-ml-fundamentals-zh.md:139–147 — P=7/10=70%, R=7/20=35%; F1 formula
- ✅ part3-ml-fundamentals-zh.md:231–234 — 768²=589,824; 2×768×16=24,576; ratio 4.17%
- ❌ part3-ml-fundamentals-zh.md:226 — "Gemini 2B" (should be Gemma 2B)
- ❌ part3-ml-fundamentals-zh.md:329 — "RAG embedding 通常 Encoder-based" (contradicted by part5 L120, part3 L111)
- ❓ part3-ml-fundamentals-zh.md:185 — "Val Loss 上升超過 5% → Early Stopping" presented as 標準做法; no source
- ✅ part4-system-design-zh.md:278 — $4.2M vs $3.8M = +10.5%
- ✅ part4-system-design-zh.md:298, 407 — BigQuery dry run returns bytes-to-be-scanned before execution
- ✅ part4-system-design-zh.md:344–348 — 800 ms → 500 ms = 37.5% saved
- ❓ part4-system-design-zh.md:321–323 — NL2SQL "~90% simple / ~60–70% multi-join" (plausible vs Spider/BIRD ranges; unsourced)
- ❌ part2-agent-zh.md:274 — ADK "內建 AgentTeam" (ADK docs: sub_agents + Sequential/Parallel/LoopAgent; no AgentTeam class)
- ❓ part2-agent-zh.md:281 — "Vertex AI Agent Builder（低代碼部署）" current product naming not confirmed
- ❓ part2-agent-zh.md:233 — "Anthropic 和 Google 都在推" MCP — Anthropic authored it; Google adopted it (true as framing, not as co-authorship)
- ✅ part5-rag-deep-dive-zh.md:135–143, part9 L327–336 — task_type values RETRIEVAL_QUERY / RETRIEVAL_DOCUMENT / SEMANTIC_SIMILARITY / CLASSIFICATION exist
- ✅ part5-rag-deep-dive-zh.md:273 — Vertex AI Ranking API exists (Discovery Engine)
- ⚠ part5-rag-deep-dive-zh.md:215 — "BM25 就是 TF-IDF" (simplification); L347 "HNSW 百萬以內" (understated)
- ✅ part6-rag-eval-zh.md:342–352 — Gemini 1.5 Flash $0.075/1M in, $0.30/1M out; $2+$15+$15=$32/day; ×30=$960; 50% cache → $480 (arithmetic correct; L338 query-size assumption unrealistic)
- ✅ part6-rag-eval-zh.md:160–166 — RAGAS metric definitions (context recall/precision, faithfulness, answer relevancy)
- ⚠ part6-rag-eval-zh.md:276 — "GPT-3.5" as the cheap-tier example is retired
- ✅ part7-agent-design-zh.md:143–144 — 10×200=2,000; 50×200=10,000 tokens
- ⚠ part7-agent-design-zh.md:221–223 — 40K "接近上限" false for current models
- ✅ part8-ml-fundamentals-zh.md:171–172 — F1(0.99, 0.01)=0.0198; L386 scaled dot-product attention; L424 RoPE in modern LLMs
- ✅ part9-llm-core-zh.md:74–80 — Gemini 1.5 Pro/Flash 1M, 2.0 Flash 1,048,576, GPT-4o 128K, Claude 3.5 Sonnet 200K (dated, caveated at L82)
- ✅ part9-llm-core-zh.md:61 — output/input price ratio 3–5× (Flash 4×, GPT-4o 4×, Claude 5×)
- ✅ part9-llm-core-zh.md:157–166 — CoT example 5+2×3=11
- ✅ part9-llm-core-zh.md:358 — `MultipleNegativesRankingLoss` is a sentence-transformers loss
- ✅ part10-context-management-zh.md:34–38 — 50×750=37,500 = 29% of 128K; 100 turns = 75,000
- ✅ part10-context-management-zh.md:19–25 — attention O(n²) affects prefill/TTFT; total latency dominated by output tokens
- ✅ part11-agent-debugging-zh.md:116–122 — 50+230+850+45+380 = 1,555 ms
- ❓ part11-agent-debugging-zh.md:101–107 — "monthly ~$450" at $0.0085/req implies ~1,765 req/day; volume never stated
- ✅ part12-agent-evaluation-zh.md:142–152 — Gemini 1.5 Pro $1.25/$5 per 1M; $0.005125/req; $51.25/day; $1,538/mo; 40% cache ≈ $615
- ✅ part12-agent-evaluation-zh.md:246 — path efficiency 3/5 = 0.60
- ❌ part12-agent-evaluation-zh.md:309 — faithfulness 0.85 ≠ "15 of 100 answers"
- ❓ part13-prompt-injection-zh.md:6 — "危險 10 倍" unsupported
- ✅ part13-prompt-injection-zh.md:45–92 — direct vs indirect injection taxonomy matches OWASP LLM01 framing; L224–245 per-user OAuth scopes as least-privilege is standard guidance
