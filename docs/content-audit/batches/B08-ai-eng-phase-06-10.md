# B08 — ai-eng-from-scratch phases 6–10 (10 posts)

Files: `content/posts/ai-eng-from-scratch-phase{6,7,8,9,10}-part*-zh.md` (5,615 lines total).
Mechanical baseline (`docs/content-audit/inputs/mechanical-baseline.txt`): none of the 10 files appear; re-run of `scripts/review_posts.py` on the batch confirms **0 errors, 0 warnings**. No hard-coded baseURL; every series-nav link target exists (including `phase5-part3` and `phase11-part1`).

## Batch summary

All ten posts were generated to the fde-interview-guide template — a 「工程情境」 interviewer question at the top (every file, L19–23), a 「二、三個演進階段」 POC/MVP/Scale section, six 「為什麼選 X 不選 Y」 tables and a 「九、系統效應」 before/after table — and the template is where most of the damage is. The textbook cores are generally sound: the DDPM/DDIM derivations, the PPO/DPO objectives, the LoRA parameter arithmetic, the LLaMA-1 data mix, the Chinchilla D/N table and the checkpoint-size math all recompute. The invented numbers cluster in the 系統效應 tables and the decision-table cells, where percentages such as "訓練穩定性 +60%", "召回品質提升 15–25%" or "WinRate +35%" appear with no source. Four posts contain a factual error in their headline table that a reader would act on: 7-1's claim that KV cache cuts first-token latency 4,100 → 380 ms (it does not touch prefill, and the post's own opening line says so), 7-2's KV-cache column that shrinks with weight quantisation plus an invented benchmark table, 8-2's StyleGAN2 facts (25-day training, PPL 3.96, AdaIN in a "StyleGAN2" diagram) and a diffusion cost 50× off its sibling post, and 10-1's token-count arithmetic that treats 1 TB of UTF-8 Chinese as 1 T characters and feeds a "$8M → $4.2M" savings table. Coverage matches `AI_ENG_FROM_SCRATCH_PLAN.md` exactly (2/2/2/1/3 split), but the plan's inventory still lists every one of these files as ⬜ Not Started. The phase sections teach something in 10-2 (data/model/cluster scale really is the axis) and 6-1 (API → self-host cost cliff) and are padding or self-contradictory in 7-1, 10-1, 10-3 and 8-2. Verdicts: **0 Ready, 6 Needs revision, 4 Not ready**.

## Per-post scorecard

Scores: A accuracy, C clarity, D depth, V visuals, S structure, F format (1–5); Overall = plain mean (no finance posts).

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| phase6-part1-asr | 557 | 3 | 4 | 3 | 4 | 4 | 4 | 3.7 | Needs revision | L283 Whisper stem "2 × Conv1D (stride=2, 下採樣 4×)" while the same box outputs 1500 frames from 3000 — stride is 1 then 2, i.e. 2× (also L238 Mel(2000 Hz)=1474, recomputes to 1521; L218 "75% 重疊" is 60%) |
| phase6-part2-tts-audio-models | 496 | 3 | 4 | 3 | 4 | 4 | 4 | 3.7 | Needs revision | L457 "月成本增加 4×，日活增加 20×，單位成本下降 50%" — 4/20 = 0.2, an 80% drop, and the table above it (L451) shows $0.008 → $0.004 (50%) from a different base |
| phase7-part1-transformer-architecture | 608 | 2 | 4 | 4 | 4 | 4 | 4 | 3.7 | **Not ready** | L566–579 系統效應 table: "首 token 延遲" 4,100 → 380 ms attributed to KV cache; KV cache does not change prefill (the opening quote L16 says exactly this). FP32 prefill of 512 tokens on an A100 is ~0.4 s, not 8.2 s |
| phase7-part2-training-variants | 607 | 2 | 4 | 4 | 3 | 3 | 4 | 3.3 | **Not ready** | L593–600 inference table: KV cache "4 GB → 2.1 GB (INT8 AWQ) → 1.2 GB (INT4)" — weight quantisation does not shrink the KV cache, and AWQ is a 4-bit method; L583–589 benchmark table (BGE-large NDCG 0.794, CodeT5+ 42.3 %, GPT-4 BLEU 26.4) has no source and several values do not match the papers |
| phase8-part1-diffusion-models | 529 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L350–356 vs L488 vs L430: fp16+xFormers 20-step time is 2.3 s on A10G in §七, 1.0 s in §九 and §二, and INT8 is 0.9 s / 0.7 s / "0.7s vs 1.0s" depending on section |
| phase8-part2-gan-video-generation | 508 | 2 | 4 | 3 | 4 | 4 | 4 | 3.5 | **Not ready** | L330 "訓練：8× V100，25 天" — official StyleGAN2 repo: 9 d 18 h on 8 V100 for 25,000 kimg; L329 "PPL = 3.96" is not the paper's number; L254 diagram labels AdaIN as "StyleGAN2 架構" (StyleGAN2 replaced AdaIN with weight demodulation) |
| phase9-part1-rl-fundamentals | 601 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L392 "β = 0.05：InstructGPT 論文推薦值" — the paper's default KL coefficient is 0.02 (L124, L370 repeat 0.05); L114 "6B DeBERTa" reward model does not exist (InstructGPT's RM was a 6B GPT-3) |
| phase10-part1-tokenization | 650 | 2 | 4 | 3 | 3 | 3 | 4 | 3.2 | **Not ready** | L540–546 系統效應: "1TB 中文語料 → 2.9T / 1.3T tokens … $8M → $4.2M". 1 TB of UTF-8 Chinese is ~333 G characters, so 0.97 T / 0.43 T tokens — 3× off, and the same error is stated as 500 B / 1.5 T at L36. L339 defines fertility as 詞數/Token 數 and says lower is better — inverted |
| phase10-part2-pretraining | 542 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L483–486 "MFU 45 % → 380K tok/s on 256 A100" recomputes to ~20 % MFU (6·7B FLOP/token ÷ 256·312 TF); the $230K line implies $1.25/GPU-h while L421 uses $8/GPU-h |
| phase10-part3-finetuning | 517 | 3 | 4 | 4 | 3 | 3 | 4 | 3.5 | Needs revision | L62–118 phase ladder moves from BF16 LoRA on one A10G (Phase 1) to QLoRA on 2× A100 (Phase 2) — the post's own §5.3 (L297) says to prefer BF16 LoRA when memory allows; Phase 3 pairs "FSDP + ZeRO-3" (the same thing) for a LoRA run that needs neither |

Theses as read:
- 6-1: Streaming ASR is a latency/accuracy/cost triangle decided by the feature front-end and the CTC-vs-attention decoder choice.
- 6-2: TTS quality and latency come from the acoustic-model/vocoder split; non-autoregressive model + GAN vocoder is the production default.
- 7-1: Transformer "architecture" is a set of hardware trade-offs — KV cache, Flash Attention and GQA are the three that decide serving cost.
- 7-2: Training stability (warmup, clipping, precision) and architecture family choice matter more than the model code.
- 8-1: Diffusion wins on quality and control, so the engineering is all about speed: latent space, few-step samplers, quantisation.
- 8-2: GAN is a game-equilibrium problem; it still wins when latency, domain specificity or data efficiency dominate.
- 9: RLHF lets a model learn the *direction* of human preference beyond demonstrations; PPO clipping and the KL term are the control knobs.
- 10-1: Tokenizer choices fix model capacity, training cost and multilingual fairness before training starts.
- 10-2: Pretraining is the most expensive and fragile step; data pipeline, scaling laws, 3D parallelism and spike recovery are the levers.
- 10-3: Choose the fine-tuning method by memory and data size — LoRA by default, QLoRA when memory-bound — and quality beats quantity.

## Patterns

### Content quality
- Textbook cores recompute and read well: DDPM closed form / μ_θ / L_simple / DDIM step (8-1 L169–215), PPO clip and DPO loss (9 L296–392), LoRA parameter count (10-3 L160–180: 425,984/layer, 13.6 M over 32 layers, 99.83 % — all verified), LLaMA-1 data mix (10-2 L221–229 matches the paper), checkpoint sizing (10-2 L393–400).
- The 2024–2026 "補充" paragraphs are the best-written content in the batch and are accurate: DiT/flow-matching note (8-1 L444), Video DiT (8-2 L380), GRPO/RLVR (9 L419), DeepSeek aux-loss-free MoE (7-2 L339), Coqui/CPML licence warning (6-2 L297).
- Quality drops wherever the template demands a number it does not have: 7-2 L37–43 "約 40 % 訓練在 step 200 前崩潰 / 每 ~500 步一次 NaN", 8-2 L401–404 "訓練穩定性 +60 % / 模式崩潰率 ~40 % / 節省 80 % 人力", 10-1 L570–573 "召回品質提升 15–25 % / Bug 率下降 20 %".
- Code is mostly real-API pseudocode: `spm.SentencePieceTrainer.train(...)` (10-1 L300), `pipe.enable_xformers_memory_efficient_attention()` (8-1 L343), `torch.distributed.checkpoint` usage (10-2 L406). Three snippets have bugs: 6-1 L331 `whisper.transcribe(chunk)` (module function needs a model; `model.transcribe(audio)` is the API), 8-2 L269–279 AdaIN indexes a `[B, C]` tensor with four dims and swaps γ/β, 8-2 L213 `gradients.norm(2, dim=1)` on a 4-D tensor without flattening.

### Structure (does the house format help or pad?)
- Every post opens with a 「工程情境」 interviewer question (6-1 L21, 7-1 L19, 9 L19, 10-3 L19 …). The plan's standard structure has no such block and the series is "NOT interview prep"; it is the fde 面試情境 renamed.
- Phase sections that teach: 10-2 L46–168 (model size × tokens × cluster size really is a scale ladder; DDP → ZeRO-2 → 3D parallel is the right progression), 6-1 L50–180 (API → self-hosted → routed models with the cost cliff computed).
- Phase sections that pad or contradict: 7-1 L37–115 "adds GQA" at Phase 3 to a deployed 7B (an architecture property of the pretrained checkpoint — the post admits Llama-2 7B is MHA at L486) and claims HF Transformers runs "無 KV Cache 重用" at Phase 1 (HF `generate` has used the cache by default for years); 10-1 L112–160 Phase 3 is a 50K-QPS gRPC "Tokenizer 服務", which nobody deploys separately from the model; 10-3 L62–118 contradicts §5.3; 8-2 L46–124 is GAN history (DCGAN → WGAN-GP → StyleGAN2) relabelled as POC/MVP/Scale by "樣本數".
- Decision tables that weigh real alternatives: BF16/FP16/INT8 (7-1 L536, 7-2 L449), GQA/MHA/MQA (7-1 L500), DDIM vs DDPM and latent vs pixel (8-1 L386–408), LoRA vs full / QLoRA vs LoRA (10-3 L352–380), PPO vs DPO (9 L460). Tables manufactured to hit six: 10-1 L489 "30 % 中文 vs 50 % 中文", 10-3 L404 "單機 vs 多機" for a 7B LoRA, 7-2 L500 "Warmup 2000 vs 500", 10-2 L466 "AdamW vs SGD" repeated from 7-2 L472.
- The 系統效應 tables are where the fabricated numbers live (see Depth); only 7-2 L577, 9 L512, 10-2 L507 and 6-1 L190 label them 示意估算.

### Depth
- Sourced or recomputable: Whisper sizes/VRAM (6-1 L250–256), Mixtral 46.7B / 12.9B active (7-2 L302), InstructGPT 85 % win rate (9 L54), Chinchilla table (10-2 L246–252), QLoRA 0.37 bit/param and 48 GB (10-3 L212, L230), A100/H100 TFLOPS and NVLink figures (10-2 L492–497).
- Invented-looking with no label: 7-1 L566 latency table, 7-2 L583 benchmark table and L593 inference table, 8-1 L229 FID-vs-steps table and L470 SDXL-Turbo/LCM FIDs, 8-2 L360 video-generation cost table ("Wan 2.1 480p 120 幀 80 GB" — Wan 2.1 outputs 81 frames and the 1.3B model runs in ~8 GB), 10-3 L446 medical case study ("SOAP 格式遵從率 23 % → 89 %").
- Flip conditions exist on every table, but many are invented thresholds rather than reasoning: 7-1 L532 "並發 > 4 → PagedAttention 必選", 7-1 L524 "seq_len < 64 且批次 >> 1 時重新計算更高效", 10-2 L466 "超大 batch (> 64M token) 時 SGD 可能更穩定".
- "When it breaks" is done well in 9 L530 (RLHF failure modes), 10-2 L330 (loss-spike diagnosis), 10-3 L300 (QLoRA costs), 6-1 L288 (Whisper limits) — these sections are the model for the rest.

### Direction
- Overlap inside the batch: Flash Attention is explained three times (7-1 L389–430, 7-2 L389–396, 10-2 L469); 3D parallelism twice (7-2 L92–135, 10-2 L278–323); BF16 vs FP16 three times (7-1 L536, 7-2 L449, 10-2 L468); DPO twice (9 L397, 10-3 L372). Each repeat is shorter and less accurate than the first.
- Stale advice: 7-1 L246 and L497 recommend ALiBi for > 128K context — every current long-context open model (Llama 3.1, Qwen2.5/3, DeepSeek) uses RoPE with scaling; 7-2 L204 attributes WSD to "Mistral/Llama 3" (Llama 3 used cosine; WSD is MiniCPM/DeepSeek lineage). 8-1 and 6-2 handle their staleness honestly with dated caveats.
- Plan drift: `AI_ENG_FROM_SCRATCH_PLAN.md` L116–136 marks all ten files ⬜ Not Started; the splits and slugs match exactly, so this is bookkeeping, not a content gap.
- Category fit is right (`ai`, `engineering`); tags include `RKK`, no `Interview`. 10-3's series index (L512) and 6-2's (L484) hand-list all 19 phases — a maintenance liability now that the tag page exists.

### Accuracy
- Mechanism errors: 7-1 L566 (KV cache ↔ TTFT), 7-1 L58 (HF without KV cache), 7-1 L541 (BF16 "精度與 FP32 等效" — same range, 7-bit mantissa), 7-2 L598 (quantisation ↔ KV cache), 6-1 L283 (Whisper 4× downsample), 8-1 L402 ("DALL-E 1 pixel space 256×256" — DALL-E 1 is a dVAE + transformer, not pixel diffusion), 8-2 L254 (AdaIN in StyleGAN2), 10-1 L339 (fertility inverted).
- Arithmetic errors: 6-1 L238 Mel(2000) = 1521 not 1474; 6-1 L218 overlap 60 % not 75 %; 6-2 L457 unit cost; 10-1 L36/L540 token counts; 10-1 L36 "5–10 %" vs its own table L331 "2.9 %"; 10-1 L234 "(e,w): 2+6=8" — the pair in `lower` is (w,e), count is 6; 10-2 L484 throughput vs MFU; 10-3 L331 "比預訓練小 100 倍" (3e-4 → 1e-5 is 30×).
- Cross-post contradictions: KV cache for 7B at 4K context is 2.1 GB in 7-1 L364 and 4 GB in 7-2 L375; diffusion cost per image is $0.00015–0.0002 in 8-1 L470/L488 and $0.008 in 8-2 L425; SST-2 BERT-large is 94.9 % at 7-2 L246 and 96.4 % at 7-2 L585.
- Misattributions: 9 L392 β = 0.05 "InstructGPT 推薦" (paper: 0.02); 7-2 L68 "AWS p4d.xlarge" (only p4d.24xlarge exists, 8 GPUs); 6-2 L240 HiFi-GAN V2 "250× 即時, MOS 4.1" (paper: V2 MOS 4.23, V3 1,186×); 10-3 L220 "LoRA (BF16 base) 65B = 640 GB" (that is 8×80 GB, not a measurement; bf16 weights alone are 130 GB).

### Format / front matter
- All front matter complete and in the closed category set; `weight:` and `series:` fields are consistent across the batch; `description` fields are keyword lists rather than payoffs (6-1 L6, 7-2 L6, 10-1 L6).
- readTime overstates on 8/10 posts by the 32-lines/min rule: 6-2 says 20 min for 496 lines (~16), 10-2 says 23 for 542 (~17), 7-1/7-2/9 say 23 for ~605 (~19). Within the checker's tolerance, so no warning.
- 10-1's opening quote (L14–17) is the only one without italics and uses trailing double-space line breaks; the other nine use `> *…*`.
- Diagrams stay ≤ 80 columns except 6-2 L135–180 (Phase 3 box is 71 cols — fine) and 10-1 L112–160 (~69). No rendering problems found; no Mermaid used anywhere in the batch (ASCII only), which is acceptable.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | phase7-part1:566–579 | 系統效應 table attributes a 4,100 → 380 ms first-token drop to KV cache; KV cache only affects decode steps, and the opening quote (L16) says so. FP32 prefill of 512 tokens on A100 ≈ 0.4 s, not 8.2 s | Split the table into TTFT (prefill: dtype, Flash Attention) and per-token decode latency / throughput (KV cache, GQA, PagedAttention); recompute from FLOPs and bandwidth |
| 2 | blocker | phase7-part2:593–600 | "KV Cache (4K ctx)" column shrinks with INT8 "AWQ" (4 GB → 2.1 → 1.2 GB). Weight quantisation leaves the KV cache unchanged; AWQ is W4A16; "3.8 GB (節省 IO)" for Flash Attention is also meaningless | Hold KV cache constant across rows (or add a separate KV-cache-quantisation row); rename AWQ → INT4, GPTQ → INT4, add a true INT8 row (e.g. SmoothQuant/W8A8) |
| 3 | blocker | phase10-part1:36, 540–546 | 1 TB corpus → "2.9 T / 1.3 T tokens", "$8M → $4.2M" treats 1 TB as 1 T characters; UTF-8 Chinese is ~333 G chars → 0.97 T / 0.43 T. L36 states a third set (500 B / 1.5 T) | Restate in characters or tokens, not bytes; recompute the 系統效應 rows; also fix "計算量 52 %" (1.3/2.9 = 45 %, i.e. 55 % saving, matching the row above it) |
| 4 | blocker | phase7-part2:583–589 | Benchmark table (SST-2 96.4 vs L246's 94.9; BGE-large NDCG@10 0.794; E5-mistral 0.741 below BGE; CodeT5+ 42.3 % HumanEval; GPT-4 En-De BLEU 26.4) is unsourced and several cells conflict with the papers | Keep only numbers with a citation (BERT-large SST-2 94.9, CoNLL F1 ~92.8, T5-11B WMT14 En-De 32.1, Code Llama-34B 48.8), or label the table 示意 and drop model names |
| 5 | blocker | phase8-part2:254, 329–330 | "StyleGAN2 架構" diagram built on AdaIN (StyleGAN2 replaced it with weight demodulation); "PPL = 3.96" is not the paper's metric value; "8× V100，25 天" vs official repo 9 d 18 h | Relabel the diagram StyleGAN (v1) or redraw with modulated conv; cite Table 1 of the StyleGAN2 paper for FID/PPL; use the repo's training-time table |
| 6 | major | phase8-part2:425 vs phase8-part1:470 | Diffusion inference cost is $0.008/張 here and $0.00015–0.0002/張 one post earlier; the "GAN 便宜 40×" conclusion rests on it | Pick one basis (e.g. SDXL fp16 on A10G, 20 steps) and reuse the 8-1 number; the real GAN advantage is latency, say so |
| 7 | major | phase10-part1:339–346 | Fertility defined as 詞數/Token 數 with "越低越高效" — inverted; the table values (1.3, 1.8 …) are tokens/word | Define fertility = tokens per word, higher = worse |
| 8 | major | phase6-part1:283 | Whisper stem "stride=2, 下採樣 4×" contradicts the 1500-frame output two lines below (conv1 stride 1, conv2 stride 2 → 2×) | Change to "第二層 stride=2，下採樣 2×：3000 → 1500" |
| 9 | major | phase10-part3:62–118 vs 297 | Phase ladder goes LoRA (1× A10G) → QLoRA (2× A100) → LoRA r=64 (8× H100 "FSDP + ZeRO-3"); §5.3 says use BF16 LoRA when memory allows; FSDP and ZeRO-3 are the same technique | Make Phase 2 BF16 LoRA on 2× A100 and reserve QLoRA for the memory-bound branch; drop "ZeRO-3" or "FSDP" |
| 10 | major | phase9-part1:124, 370, 392 | KL coefficient "β = 0.05 InstructGPT 論文推薦值" — the paper's default is 0.02; "6B DeBERTa" RM (L114) does not exist | Cite 0.02 and say 0.02–0.1 is the practical range; make the RM "6B GPT-style" or "DeBERTa-v3-large (304M)" |
| 11 | major | phase10-part2:421, 483–486 | $8/GPU-h in §六 vs $1.25/GPU-h implied by "$230K for 1 T tokens"; "380K tok/s at 45 % MFU on 256 A100" recomputes to ~20 % MFU (45 % ≈ 856K tok/s) | Fix one GPU price for the post; recompute throughput from 6·N·MFU·peak |
| 12 | major | phase8-part1:350–356, 430, 488 | Three different timings for the same config (fp16+xFormers: 2.3 s / 1.0 s; INT8: 0.9 s / 0.7 s) | Reconcile §七's TensorRT ladder with §二, §八 and §九; note which is A10G vs A100 |
| 13 | major | phase7-part1:58, 246, 497, 541 | HF Transformers "無 KV Cache 重用" (default `use_cache=True`); ALiBi recommended for > 128K context (current long-context models use scaled RoPE); BF16 "精度與 FP32 等效" | Phase 1 = "HF generate, no batching"; replace the ALiBi row with RoPE + YaRN/NTK scaling; BF16 row: same range, 7-bit mantissa |
| 14 | major | phase6-part2:240, 457 | HiFi-GAN V2 "250× 即時, MOS 4.1" vs paper (V2 MOS 4.23, V3 1,186× on V100); unit-cost sentence 50 % vs the 80 % implied by 4× cost / 20× users | Quote Table 1 of the HiFi-GAN paper; recompute the 關鍵洞察 sentence |
| 15 | minor | phase6-part1:218, 238, 331 | "75 % 重疊" (60 %); Mel(2000 Hz) 1474 (1521); `whisper.transcribe(chunk)` is not the API | 15/25 = 60 %; recompute with 2595·log10(1+f/700); use `model.transcribe(audio)` |

## Recommendations

1. **Strip the interview scaffolding from this series** (all 10 files, L19–23 工程情境). WHY: CLAUDE.md and the plan say this is not interview prep and the 面試答題要點 was already removed; the interviewer prompt is the same device under another name and shapes every post into an "answer". HOW: replace with a one-paragraph reader/goal statement ("你會學到…"), keep the 4-line contrast quote.
2. **Keep the phase section only where scale is the axis** (10-2, 6-1, arguably 8-1); delete or shrink it in 7-1, 10-1, 10-3, 8-2. WHY: those four either contradict the body or invent an architecture (gRPC tokenizer service) to fill the slot. HOW: fold the useful residue (e.g. 7-1's "HF → vLLM" jump) into a two-row table in the relevant deep-dive section.
3. **Cut decision tables to the ones with a real alternative** (3–4 per post, not 6). WHY: the manufactured rows (10-1 決策5, 10-3 決策5, 7-2 決策5) carry invented flip thresholds that readers will quote. HOW: delete rows whose "flip condition" has no mechanism behind it; keep dtype, GQA, LoRA/QLoRA, DDIM/DDPM, PPO/DPO.
4. **Label or source every 系統效應 number.** WHY: 9, 10-2 §9.3 and 7-2 §9.1 already do this and read as honest; 7-1 §九, 7-2 §9.2/9.3, 8-2 §九 and 10-3 §9.3 present the same kind of estimate as measurement. HOW: add the one-line 「示意估算，非實測」 note the other posts use, or replace with a cited figure.
5. **Fix the four blocker tables before anything else** (findings 1–5). WHY: each sits in the section a skimming reader goes to first. HOW: recompute from first principles (FLOPs/bandwidth for 7-1; characters not bytes for 10-1; paper tables for 7-2/8-2) — the arithmetic in this report is in the scorecard.
6. **De-duplicate Flash Attention, 3D parallelism, BF16/FP16 and DPO across 7-1 / 7-2 / 10-2 / 9 / 10-3.** WHY: the second and third copies are shorter and introduce the contradictions (KV cache 2.1 vs 4 GB). HOW: keep the first full treatment, replace later ones with a two-sentence recap plus an internal link.
7. **Reconcile cross-post numbers with a shared assumptions block.** WHY: 7-1/7-2 disagree on KV-cache size, 8-1/8-2 on $/image, by 2× and 50×. HOW: one line of assumptions per series phase (GPU, $/h, dtype, context) reused verbatim; `grep` the batch for "KV Cache" and "/張" when editing.
8. **Refresh the three stale recommendations with the dated caveat style 8-1 and 6-2 already use** (ALiBi for long context, WSD attribution, Whisper small/medium as production default vs large-v3-turbo + faster-whisper). WHY: the series is dated 2026 and already carries 2025–26 notes elsewhere. HOW: a `> **2026 補充**` blockquote per section, as in 8-1 L444.
9. **Fix the code bugs** (6-1 L331, 8-2 L213/L269–279). WHY: readers copy snippets. HOW: `model.transcribe`, flatten before `.norm`, index AdaIN style as `[B, C, 1, 1]` γ/β pairs.
10. **Update `AI_ENG_FROM_SCRATCH_PLAN.md`** inventory for phases 6–10 (✅ with line counts) and recalibrate readTime (32 lines/min) on 6-2, 10-2, 7-1, 7-2, 9. WHY: the plan is the coverage tracker and currently says nothing from phase 3 onward exists. HOW: mechanical edit.

## Verified / unverified claims

- ✅ phase6-part1:238 — Mel(f) = 2595·log10(1+f/700): 100→150, 500→607, 1000→1000, 4000→2146, 8000→2840 recompute; ❌ 2000→1474 (recomputes to 1521)
- ❌ phase6-part1:218 — 25 ms / 10 ms hop "75 % 重疊" → 60 %
- ✅ phase6-part1:216–222, 243 — 400 samples / 160 hop / 201 FFT bins / 80×3000 mel / 1500 encoder positions match the Whisper code; ❌ L283 "下採樣 4×" (conv1 stride 1, conv2 stride 2)
- ✅ phase6-part1:244, 262 — Whisper tiny/base/small/medium/large = 39M/74M/244M/769M/1550M, VRAM ~1/1/2/5/10 GB (OpenAI README); large-v3 128 mel bins; v3 data 1 M h weak + 4 M h pseudo-labelled; turbo 4 decoder layers / 809M
- ❓ phase6-part1:28, 250–256 — LibriSpeech test-clean WER 2.7 % is the paper's large-v2 figure; per-size WERs (8.7/6.4/4.8/3.8) and CPU timings have no source
- ✅ phase6-part1:150–162, 180 — Phase 3 cost chain ($1.44/h × 1,000–5,000 GPUs → $35K–$173K/日; API $432K/日; 60–92 % saving) recomputes; ✅ L190 Phase 2 $45,600 = 5,000 × $0.38 × 24
- ✅ phase6-part2:38–45 — latency budget sums to 215 ms
- ✅ phase6-part2:240, 297 — HiFi-GAN V1 167.9× real-time on V100, 13.92M params; Coqui shutdown and CPML non-commercial licence; XTTS v2 6 s reference / 17 languages
- ❌ phase6-part2:240–241 — HiFi-GAN V2 "250×, MOS 4.1" (paper: V2 MOS 4.23, V3 1,186×); ❓ Vocos "200× 即時"; ✅ Vocos 13.5M params
- ❌ phase6-part2:160 — "chunk 256 frames ≈ 50 ms" (256 mel frames at 256-sample hop / 22.05 kHz ≈ 3 s; 256 samples ≈ 11.6 ms)
- ❌ phase6-part2:457 — 4× cost / 20× users = 80 % unit-cost drop, not 50 %
- ❓ phase6-part2:124, 227, 231 — MOS values (VITS 4.36, VITS2 4.42, Tortoise 4.2, XTTS 3.8) — post itself says they are not comparable (L299)
- ✅ phase7-part1:136, 180, 364–370 — 512×768 = 393,216 floats ≈ 1.5 MB; 8192² × 4 B = 256 MB; Llama-2-7B KV cache 2×32×32×128×4096×2 B = 2.15 GB, ×16 ≈ 34 GB; GQA ÷4 → 0.53 GB
- ✅ phase7-part1:393–395, 412 — A100 HBM 2 TB/s, SRAM ~19 TB/s / ~20 MB (FlashAttention paper); FA3 1.5–2× over FA2; vLLM waste 60–80 % → < 4 %, 2–4× throughput
- ❌ phase7-part1:566–579 — TTFT column (see finding 1); FP32 7B prefill of 512 tokens ≈ 7.2 TFLOP ≈ 0.37 s at 19.5 TFLOPS
- ❌ phase7-part1:58 — HF Transformers without KV cache; ❌ L541 BF16 precision "與 FP32 等效"
- ❓ phase7-part1:234, 432, 455 — YaRN "4–8×" (YaRN paper extends Llama 2 to 128K = 32×); RoPE "+5–8 % 計算開銷"; MQA "品質下降 5–8 %" — no source
- ✅ phase7-part2:159–167, 213, 302–304, 324 — FP16/BF16/FP8 format bits and max values; A100 312 vs 19.5 TFLOPS; Mixtral 46.7B total / 12.9B active; capacity factor 1.25
- ✅ phase7-part2:246, 254 — BERT-large SST-2 94.9; BERT-base/large 110M/340M; ❌ L585 SST-2 96.4 contradicts L246
- ❌ phase7-part2:68 — "AWS p4d.xlarge" does not exist (p4d.24xlarge, 8× A100 40GB)
- ❓ phase7-part2:204 — WSD "Mistral/Llama 3 採用" — Llama 3 paper uses cosine with 8K-step warmup; could not confirm Mistral
- ❌ phase7-part2:593–600 — KV-cache column vs quantisation (finding 2); ❌ L375 "4K context, 7B: KV cache 約 4 GB" contradicts 7-1's 2.1 GB
- ✅ phase8-part1:169–215 — DDPM β schedule 1e-4 → 0.02, closed-form q(x_t|x_0), μ_θ, L_simple, DDIM η=0 step all match Ho et al. / Song et al.
- ✅ phase8-part1:284–302 — 512×512×3 / 64×64×4 = 48:1; U-Net ~865M; CLIP ViT-L/14, 77 tokens, 768-d; KL weight 1e-6; ControlNet ~361M; IP-Adapter 22M
- ✅ phase8-part1:466–472, 482–486, 497–510 — cost rows ($10.4 / $0.52 / $0.21 / $0.15 / $0.06 per 1,000 at $0.75/h) and the $14.6/日 budget chain recompute **without** the stated 70 % utilisation (footnote not applied)
- ❌ phase8-part1:402 — "DALL-E 1 pixel space 256×256" (DALL-E 1 = dVAE + autoregressive transformer)
- ❌ phase8-part1:327 vs 321 — LoRA r=16 "15 MB" (table: r=4 → 15 MB fp32, r=64 → 230 MB; r=16 ≈ 60 MB)
- ❓ phase8-part1:229–238, 470 — FID vs steps table for SD v1.5 and SDXL-Turbo/LCM FIDs — no source
- ✅ phase8-part2:124, 331, 358 — StyleGAN2 FFHQ FID 2.84; ProGAN FFHQ FID 8.04; SPADE COCO-Stuff FID 22.6; pix2pix λ=100, PatchGAN 70×70; WGAN-GP Adam β=(0, 0.9), 5:1
- ❌ phase8-part2:330 — "8× V100, 25 天" (official repo: 9 d 18 h for 25,000 kimg on 8 V100); ❌ L329 PPL 3.96; ❌ L254 AdaIN labelled StyleGAN2
- ❓ phase8-part2:360–366 — video table (SVD "512×512 40 GB", "Wan 2.1 480p 120 幀 80 GB") — Wan 2.1 outputs 81 frames; 1.3B variant runs in ~8 GB; no source
- ❌ phase8-part2:425 vs phase8-part1:470 — Diffusion $0.008/張 vs $0.00015–0.0002/張
- ✅ phase9-part1:52–56, 159–163, 252–256, 306–316, 350–362, 397–412 — InstructGPT 1.3B > 175B GPT-3 and 85 % win rate; GPT-2 vocab 50,257; DQN 1M replay / 10K target sync; PPO ε=0.2, c1=0.5, c2=0.01; Bradley-Terry RM loss; DPO loss
- ❌ phase9-part1:124, 370, 392 — β = 0.05 attributed to InstructGPT (paper default 0.02); ❌ L114 "6B DeBERTa"
- ❓ phase9-part1:444, 455 — "PPO 快 3–10× (OpenAI Atari)", "WinRate +35 % (InstructGPT)", "500 偏好對 > 10K 示範" — no source
- ✅ phase9-part1:419–421 — GRPO / RLVR description matches DeepSeek-R1
- ✅ phase10-part1:85, 331–337, 297–305, 388–398, 462 — cl100k 100,277 tokens; embedding table (131M/205M/268M/410M/524M, 1.9–7.5 % of 7B); SentencePiece trainer signature; Llama 3 chat template tokens; Mistral NeMo Tekken ~131K; Llama 3 128K vocab
- ❌ phase10-part1:36 — "5–10 % of model" vs the post's own 2.9 % (L331); ❌ L234 "(e,w): 2+6=8" (count is 6); ❌ L339 fertility inverted; ❌ L36/L540–546 token counts from 1 TB (3× off)
- ✅ phase10-part1:551–560 — 128K ÷ 1.3 ≈ 98K, ÷ 2.9 ≈ 44K; 32K ÷ 2.9 ≈ 11K, ÷ 1.3 ≈ 24.6K
- ❓ phase10-part1:368–372 — per-tokenizer Chinese token counts (post labels them 示意 at L375 — good); ❓ L508 "Tiktoken 比 HF tokenizers 快 5–10×" (tiktoken README: 3–6×; HF tokenizers is Rust too)
- ✅ phase10-part2:28–30, 221–229, 246–252, 258–264, 272–276, 289–295, 393–400, 492–497 — LLaMA-2 184K / 1.72M A100-h; LLaMA-1 data mix; Chinchilla D/N ratios; LLaMA-2 7B MMLU ~45 vs Chinchilla ~67; GPipe bubble formula; 70B fp16 140 GB + Adam 840 GB; A100/H100 peak TFLOPS, NVLink 600/900 GB/s, TFLOPS/$ column
- ❓ phase10-part2:27 — GPT-3 "~3.5M A100 小時" (3.14e23 FLOP at 40 % MFU ≈ 0.7M A100-h; the $4.6M figure is Lambda's V100 estimate)
- ❓ phase10-part2:238–243 — Chinchilla constants N ≈ C^0.5/8.7, D ≈ 1.75·C^0.5 imply D/N ≈ 15, not the stated 20; not from the paper
- ❌ phase10-part2:483–486 — 380K tok/s ≠ 45 % MFU on 256 A100 (≈ 20 %); $230K implies $1.25/GPU-h vs $8/GPU-h at L421
- ❌ phase10-part2:468 — "H100 以前的硬體（V100）僅支援 FP16" (A100 supports BF16)
- ✅ phase10-part3:144, 160–180, 212–216, 230, 258, 400–404 — 70B full FT ≈ 16 B/param ≈ 1.1 TB; LoRA per-layer and r=4/16/32/64 q/v-only counts (1.7/6.8/13.6/27.3M) recompute; QLoRA 0.37 bit/param double-quant, 48 GB for 65B; LIMA 1,000 vs Alpaca 52K on 65B; lr 2e-4 LoRA / 1e-5–5e-5 full FT
- ❌ phase10-part3:220 — "LoRA (BF16 base) 65B 640 GB"; ❌ L150 "7B LoRA ≈ 16 GB" vs L422 "BF16 LoRA ~28 GB"; ❌ L331 "小 100 倍" (≈ 30×)
- ❓ phase10-part3:34 — Llama-3 8B MedQA "58 % → 78–82 % after fine-tuning" — 8B fine-tunes in the literature land in the 60s; no source
- ❓ phase10-part3:446–452 — medical case-study table — unlabeled estimate
