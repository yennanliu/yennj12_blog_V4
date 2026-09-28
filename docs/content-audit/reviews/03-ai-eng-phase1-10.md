## ai-eng-from-scratch phases 1–10 — 21 posts

### Series-level observations
- **The series nav describes a different curriculum in almost every post.** Each nav block was clearly written without knowing what the neighbouring posts are. So the dead links are wrong *topics* as well as wrong slugs. Phase 3 is linked as「MLOps 與模型部署」(phase4-part1 L522). Phase 5 Part 3 is described as「向量資料庫與 RAG」(phase6-part1 L547). Phase 6 Part 2 becomes「模型微調與 LoRA」(phase7-part1 L598). Phase 7 Part 2 becomes「RAG 系統設計」(phase8-part1 L520). Phase 8 Part 2 becomes「分散式訓練與混合精度」(phase9 L590). Phase 10 Part 2 becomes「RAG 系統設計」(phase10-part3 L501). Several posts also have a "系列索引" footer that invents its own phase list: phase6-part2 lists "Phase 3：LLM 應用與 RAG … Phase 7：推薦系統工程"; phase10-part3 lists "Phase 7–9：部署工程"; phase4-part1 lists "Phase 3：MLOps". Others point to "即將發布" parts that exist (phase1-part1 marks Part 2 as upcoming; phase8-part2 marks Phase 9 as upcoming) or were never planned (phase10-part2 lists Parts 4/5). **Fix:** throw away every nav and footer and regenerate one standard block from the real file list. That is a scripted fix across all 43 posts, not 21 hand edits.
- **The posts still read as interview prep.** Every post opens with a 面試情境 block, which the AI-eng section of CLAUDE.md does not ask for. It carries the "Interview" tag, and the body keeps addressing the interviewer: "面試官真正想聽的是" (phase4-part1 L15, phase8-part1 L15), "理解其架構選擇是面試的核心考點" (phase6-part1 L383), "能在面試中給出有數字支撐的架構決策" (phase3 L45), "這正是面試官真正在考察的能力" (phase8-part2 L508). Some footers promise "每篇均附有面試答題框架" (phase4-part2 L429) or "面試導向的決策框架" (phase2-part2 L753). **Fix:** rename 面試情境 to a neutral「本篇要解決的工程情境」, drop "Interview" from tags, and grep out the 面試 phrases in the body. The phase10-part1 scenario even leaks the template into the question: "請以三個演進階段說明" (L24).
- **The series has no working index.** Every post sets `series: ["ai-eng-from-scratch"]`, but `hugo.toml` only defines categories, tags and authors, so that field renders nothing. The nav links to `/tags/ai-eng-from-scratch/` (phase4-part2, phase7-part2) point at a tag no post carries. Two posts link to `/tags/ai/` as a stand-in, and phase9 links to a non-existent "Phase 1 總覽". **Fix:** add a `ai-eng-from-scratch` tag, or a series taxonomy with an index page, and link to that.
- **The plan's inventory is stale.** `AI_ENG_FROM_SCRATCH_PLAN.md` still marks phases 3–19 as ⬜ Not Started, although all 43 files exist. On scope, every post covers what the plan's split table promised. The drift is in overlap between posts:
  - Phase 1 Part 1 §八 and Phase 3 §八 share 4 of their 6 decisions (SGD vs Adam, BN vs LN, Xavier vs He, FP32 vs FP16).
  - Phase 2 Part 1 §4.2 pre-empts Phase 2 Part 2 (RF/XGBoost/LightGBM with its own benchmark table).
  - Flash Attention appears as a decision in both Phase 7 parts. KV cache/PagedAttention runs 37 mentions in Phase 7 Part 1, which pre-empts Phase 11 Part 1.
  - Distributed training (ZeRO/TP/PP) is covered in both Phase 7 Part 2 and Phase 10 Part 2.
  - Phase 5 Part 3 §5.3 retrievers overlaps Phase 11 Part 2 (RAG).
- **The high diagram counts are mostly fenced tables, not diagrams.** The script counts code fences with box characters. The 「為什麼選 X 不選 Y」 template in CLAUDE.md is itself fenced, so decision tables count as diagrams. Phase 2 Part 1's "20 diagrams / 0 table rows" is simply every table written as a code block.
  - **Explanatory diagrams worth keeping:** the backprop computation graph (phase3 §四), ResNet skip path (phase4-part1 §五), KV-cache prefill/decode (phase7-part1 §6.2) and the Common Crawl cleaning funnel (phase10-part2 §三).
  - **Filler:** single-column top-to-bottom box chains that are just a numbered list (phase5-part1 §6.2 FastAPI flow), ╔══╗ phase boxes that wrap a bullet list (phase1-part2 POC box), and a lopsided pseudo-histogram of the Gaussian (phase1-part2 §四).
  - **Fix:** convert data tables to Markdown tables; they render better, are searchable and read better on mobile.
- **The three-phase template is forced onto topics that do not scale with users.** Math, probability and seq2seq history are staged as "POC < 10K 用戶 / MVP 10K–200K 用戶", which means nothing for "how much linear algebra you need". In phase5-part2 the template produces bad 2026 advice: "Phase 3：Scale — LSTM + Attention" as the production end-state for machine translation. For the foundation posts (phases 1–3, 5.2), reframe the stages as learner or practitioner depth.
- **The numbers are uniformly unsourced, and several are wrong or contradict each other.** The concrete-numbers rule has produced a lot of invented precision. Examples: "2 天 vs < 30 分鐘" debugging-speed rows (phase1-part1 §九), a speech-recognition "AUC" (phase2-part1 L693), and WMT En-De BLEU of 38.1/41.0 for Transformer (phase5-part2 §九; the paper reports 27.3/28.4, and 41.0 is En-Fr). Individual errors are listed per post below. Each post needs a pass that keeps sourced numbers, adds a source for each, and labels the rest as illustrative.
- **Staleness clusters in the model-landscape posts.** This matters most in 4.3 (VLM), 6.1/6.2 (speech), 8.1/8.2 (generative), 9 (RL) and 10.x. The recurring names are all 2023–24: SD 1.5, GPT-4V, LLaVA-1.5, XTTS, cl100k, LLaMA-2 and A100/H100. Four gaps stand out: the post-DeepSeek-R1 RL stack (GRPO/RLVR), DiT/flow-matching image models, current open VLMs, and Blackwell-era hardware.

### Per-post

#### `ai-eng-from-scratch-phase1-part1-linear-algebra-zh.md`
**Verdict:** light edit
- Wrong claim in §4.1: "GPU 理論加速：4096 核心 → 有效複雜度降至 O(n²)". Parallelism does not change asymptotic complexity. Also, "CPU (i9) ~800ms" for a 1000×1000 matmul describes naive Python; BLAS does it in about 10–20 ms. Fix both, or the "2600倍加速" headline misleads.
- In §九, "batch size 8× → LR √8 倍" is labelled 線性縮放. Linear scaling is 8×, square-root scaling is √8. Pick one and name it correctly. The §九 debugging-speed rows ("~2天 → <30分鐘", "5× 更快") are invented; cut them, or present them as a qualitative contrast.
- The §8.1 flip condition, "模型 > 1B 參數且記憶體緊張時，考慮 SGD", is not what practitioners do. They reach for 8-bit Adam, Adafactor or ZeRO sharding.
- Four of the six §八 decisions reappear in Phase 3 §八. Keep the math-flavoured ones here (L1/L2 geometry, CE vs MSE gradients). Move the optimizer, normalisation and precision decisions to Phase 3.
- The nav table (L588+) lists invented parts ("Phase 1 Part 3 資訊理論", "Phase 2 Part 2 Transformer") and marks Part 2 as 即將發布.

#### `ai-eng-from-scratch-phase1-part2-probability-stats-zh.md`
**Verdict:** light edit
- A strong opening. The "三個機率錯誤" section and §七 on significance, power and calibration are the most practically useful content in the batch.
- §四: under 指數分佈 the text says "Lasso 等價於 Laplace 先驗". That is the right fact under the wrong heading; move it to a Laplace entry. The ASCII Gaussian "PDF" is asymmetric and decorative. Replace it with a one-line formula, or delete it.
- Decision 4 (KL vs PSI) calls PSI's origins unclear ("來源不明確"). PSI is in fact a symmetrised KL divergence over bins. Say so; the "flip condition" as written is weak.
- The nav points to a non-existent "Phase 1 Part 3 微積分與最佳化" (calculus is covered in Part 1). The next post should be Phase 2 Part 1.

#### `ai-eng-from-scratch-phase10-part1-tokenization-zh.md`
**Verdict:** light edit
- Stale tokenizer facts. cl100k is presented as "GPT-4 tokenizer" throughout (L36, L73, L246, L387), with no mention of o200k_base (GPT-4o and later). "Mistral 使用 32K" is out of date: Tekken, used from Mistral NeMo onward, is about 131K. Vocab comparisons should cite current Llama 3/Qwen3/o200k sizes.
- Remove "請以三個演進階段說明" from the scenario (L24); it exposes the template to the reader.
- Decision 6 (Tiktoken vs SentencePiece) gives "cl100k 詞彙表使用條款需注意" as a con. That is unsourced; tiktoken is MIT-licensed. Verify or drop.
- The nav's previous link goes to `/tags/ai/`, and the next link is an invented "Embedding 層設計" post. It should point to Phase 9 and Phase 10 Part 2 (預訓練).
- The Chinese-efficiency tables (§六) are the real value of this post for a zh-TW reader. Keep them, but say how the token counts were measured.

#### `ai-eng-from-scratch-phase10-part2-pretraining-zh.md`
**Verdict:** light edit (factual fixes, about 1–2h)
- The §三 "資料混合比例（以 LLaMA-2 為例）" table is actually LLaMA-1's published mixture scaled to 2T tokens. LLaMA-2 never disclosed its mixture. Relabel it as LLaMA-1.
- §4.2 claims "LLaMA-2 7B 的推理能力接近 Chinchilla-70B". That is false: MMLU is about 45 vs about 67. Restate it as "overtraining trades training compute for cheaper inference". The Mistral 7B row (1T tokens, 120K A100-hours) is fabricated; Mistral never published either figure.
- Stale framing: the hardware table stops at H100, with no B200/GB200. The cleaning pipeline has no model-based quality filtering (FineWeb-Edu-style classifiers, DCLM), which is now the main lever. Token budgets stop at 2–15T and should mention 15–36T-token open models.
- The "Phase 10 完整系列" table lists Parts 4/5 that were never planned. The previous link names an invented "Transformer 架構深探" part.

#### `ai-eng-from-scratch-phase10-part3-finetuning-zh.md`
**Verdict:** light edit
- "Llama-3 7B" does not exist; the model is Llama 3 8B, and the post switches between 7B and 8B (L59, L196 vs L33, L486). The §4.2 parameter math assumes 4096×4096 K/V projections, but Llama 3 uses GQA, so K/V are 4096×1024. Redo the numbers.
- L145 says "8×H100 480GB"; 8×80GB is 640GB. The Full-FT memory figure for 70B ("超過 560GB") also undercounts. AdamW states plus master weights plus gradients come to about 16 bytes/param, roughly 1.1TB.
- Missing current practice: target all linear layers (the QLoRA paper's own finding) rather than only "至少 q 和 v". Mention DoRA or rsLoRA only if you explain them. Tooling that readers actually use (TRL, Unsloth, Axolotl) is absent.
- The previous link is labelled「RAG 系統設計」; it should be 預訓練.

#### `ai-eng-from-scratch-phase2-part1-classical-ml-zh.md`
**Verdict:** restructure
- Every table is a fenced code block (the audit found 0 Markdown table rows). This is the source of the "20 diagrams". Convert them to Markdown tables. Only the bias-variance and feature-pipeline visuals are real diagrams.
- §4.2 contains a full ensemble section with its own benchmark table (RF, XGBoost, LightGBM). That pre-empts Part 2. Cut it to two sentences and a forward link.
- Several unsourced or wrong claims:
  - "傳統 ML 在生產系統中的佔比仍超過 80%" (§一) has no source.
  - "小型神經網路也需要 10–50ms（CPU）" is wrong; a 3-layer MLP runs in well under 1 ms.
  - The §九 table gives speech recognition an "AUC" of 0.985.
  - The "2024 年，ChatGPT 席捲世界" opener is dated.
- The scenario (5ms, auditable, 0.3% fraud rate) is good, but no section explicitly answers it. Add a short closing paragraph that does.

#### `ai-eng-from-scratch-phase2-part2-ensemble-optimization-zh.md`
**Verdict:** light edit
- The §4.5 claim "LightGBM 比 XGBoost 快 10–20x" dates from before XGBoost's `hist` method became the default (2.0, 2023). Today the gap is small. Update it, or date the benchmark.
- The AdaBoost date "(2001)" is wrong: Freund & Schapire published it in 1995–97.
- The §九 business-value table (AUC 0.84 → 0.88 = "+$80 萬/年") is useful as a worked method. Label it as a hypothetical model rather than presenting it as a finding.
- Delete the footer "以及面試導向的決策框架" (L753). The nav names "Phase 2 Part 1：監督學習基礎" and "Phase 3 Part 1：深度學習基礎" with wrong slugs.

#### `ai-eng-from-scratch-phase3-part1-neural-networks-zh.md`
**Verdict:** restructure
- Promise not kept. §一 promises "用純 NumPy 實作一個可訓練的兩層網路", but §四 only shows a `backward()` fragment. It has no forward pass or training loop. Its cache names are confusing: `a1, z1` are unpacked and never used, and `dW1 = x.T @ delta2` pairs layer-1 weights with the "delta2" name. Either ship a complete runnable 40-line network or drop the promise.
- The Adam formula typo `v_t = β₂·v_{t-2}` in §七 should be `v_{t-1}`. The Lion memory numbers are inconsistent: "比 Adam 少 1/3" in the text, while the table gives 1.33× vs 2× (that is half the optimizer state).
- §八 repeats four of Phase 1 Part 1's six decisions. Replace them with decisions this post uniquely owns: residual vs plain depth, GELU vs SwiGLU, cosine vs WSD schedule, AdamW vs Lion.
- The nav gives invented neighbours ("Phase 2 Part 2 特徵工程", "Phase 3 Part 2 卷積神經網路"). Phase 3 is a single post, and CNNs are Phase 4.
- The ResNet-50/ImageNet optimizer table (Lion 77.3%) has no source. Cite the Lion paper or remove the table.

#### `ai-eng-from-scratch-phase4-part1-cnn-image-fundamentals-zh.md`
**Verdict:** light edit
- Solid and well scoped; the ResNet and transfer-learning sections are good teaching.
- Misattributed number: "EfficientNet-B0 比 ResNet-50 … 推論速度快 6.1×". The paper's 6.1× is EfficientNet-B7 vs GPipe.
- Transfer learning in 2026 should at least mention ViT/DINOv2/CLIP backbones as the default feature extractor. Right now the choice looks like CNN-only.
- Remove the opening line "面試官真正想聽的是" (L15). Fix the nav: the previous post is Phase 3 (neural networks), not "MLOps". Part 2 is marked 即將推出, and the footer's invented phase index needs to go.

#### `ai-eng-from-scratch-phase4-part2-detection-segmentation-zh.md`
**Verdict:** light edit
- Stale: the YOLO table stops at v11 (2024), and there is no DETR/RT-DETR (anchor-free transformer detection). Segmentation has no SAM/SAM 2, which is now the default for mask annotation and zero-shot segmentation. Open-vocabulary detection (Grounding DINO, YOLO-World) is also missing. Verify the newer YOLO versions before listing them.
- For the factory scenario, add the licence point that matters in practice: Ultralytics YOLOv8/v11 are AGPL-3.0, so closed-source commercial use needs an enterprise licence.
- The §四 selection matrix has an unlabelled axis: "延遲要求 高" maps to the *largest* models, so "high" must mean high tolerance. Relabel it. YOLOv1's "63.4（VOC）" sits in a COCO mAP@0.5:0.95 column; move it or mark it n/a.
- This is the shortest post in the batch (418 lines) and is below the 600-line floor. The SAM section would fill the gap usefully.

#### `ai-eng-from-scratch-phase4-part3-vlm-3d-worldmodels-zh.md`
**Verdict:** restructure
- The model landscape is from 2023–24: GPT-4V and Claude 3 Vision as the API tier (L52, L65, §四 table), LLaVA-1.5/NeXT as the self-host tier, and Sora (Feb 2024) as the world model. By Sept 2026, GPT-4V is retired and the open-VLM tier is the Qwen-VL/InternVL/Gemma generation. The world-model table has no V-JEPA, Genie or Cosmos. Rewrite §四, §七 and the §九 cost table against current models.
- Trust: "Recaptioning：用 CogVLM 等模型" is attributed to Sora. That describes Open-Sora; OpenAI described DALL·E 3-style recaptioning. "最高 1080p, 60s" should be checked against the current product.
- The §九 break-even claim ("100 QPS 以下：GPT-4V API 比自架便宜") needs its assumptions stated (tokens per image, price per MTok).
- The nav's next link, "Phase 5 Part 1：語音識別、TTS", is wrong: Phase 5 is NLP.

#### `ai-eng-from-scratch-phase5-part1-text-fundamentals-zh.md`
**Verdict:** light edit
- One of the more useful posts for a zh-TW reader. The Chinese segmentation comparison (jieba/HanLP/CKIP) and the five production traps in §6.1 are not in the official docs.
- There is no "just use a sentence-embedding model" option (multilingual-e5, bge-m3, or an embeddings API). In 2026 that is the default baseline before Word2Vec. Add it to decision 1 or 3.
- §6.2's FastAPI "diagram" is a single-column chain of boxes. Replace it with a 5-item list, or add the cache-hit branch so the diagram shows a real decision.
- The trap 1 wording is muddled ("按時間切分…而非隨機切分。否則…"). State the rule plainly: split by time, because a random split leaks the future.
- The nav labels are wrong ("Phase 4 Part 3：模型監控", "Phase 5 Part 2：Transformer 與 BERT").

#### `ai-eng-from-scratch-phase5-part2-seq2seq-attention-zh.md`
**Verdict:** light edit
- Fabricated benchmark: the §九 BLEU table gives Transformer base/big 38.1/41.0 on WMT En-De. The paper reports 27.3/28.4 (41.0 is En-Fr). The LSTM+Bahdanau 28.3 row is also not an En-De number. The headline "BLEU +10" rests on these. Replace the table with the paper's own numbers.
- Reframe the post as history. The scenario asks how to build an EN→ZH MT system today, and the three-phase section answers "Phase 3：Scale — LSTM + Attention". In 2026 the right answer to that scenario is a Transformer or an LLM. Change the scenario to one of two: "explain why attention was needed", or a constrained-edge case where an RNN is still defensible.
- Decision 5's flip condition ("< 50K 樣本 → Seq2Seq") ignores fine-tuning a pretrained Transformer. That option dominates small-data MT.
- The nav's next post is "Transformer 深度解析（即將發布）"; the real next post is Phase 5 Part 3 (BERT).

#### `ai-eng-from-scratch-phase5-part3-advanced-nlp-zh.md`
**Verdict:** light edit
- The legal-QA scenario is well chosen, and the Extractive vs Generative decision is argued well.
- The §七 metrics section omits LLM-as-judge, which is the dominant evaluation method in 2026 and the natural "陷阱" follow-on to BLEU and ROUGE. The BERT family (§四) stops at DeBERTa and should mention ModernBERT (Dec 2024). "GPT-4 + RAG：最新 LLM" (L355) is stale.
- "BERT 是工程甜蜜點…適合 90% 的生產場景" (§九) is an unsupported absolute. Soften it and tie it to the latency and cost numbers already in the table.
- The §5.3 retriever comparison overlaps Phase 11 Part 2. Keep it brief and link forward.
- The nav's next link is "Phase 6 Part 1：MLOps"; Phase 6 is speech.

#### `ai-eng-from-scratch-phase6-part1-asr-zh.md`
**Verdict:** restructure
- Internal contradictions. Whisper large-v3 WER is 4.2% at L33 and 2.7% at L59/L395. The Phase 2 cost line, "GPU $0.38/h，10 並發 = $0.038/h", does not compute. "50K 並發 ≈ 50 張 GPU" implies about 1,000 concurrent Whisper-large streams per A100, which is implausible. The 96% savings headline depends on that figure.
- Whisper facts are out of date. large-v3 uses 128 mel bins, not 80, and was trained on about 5M hours, not 680K (that figure is v1/v2). large-v3-turbo, faster-whisper/CTranslate2 and current hosted STT models are all missing.
- The scenario's hardest requirement, 中英文混合 code-switching, is only listed as a remaining problem ("中英混合辨識差", L161) and never answered. The "streaming Whisper" code uses 30-second chunks, which cannot meet the scenario's < 500ms target. Either show a real streaming design (Conformer/RNN-T with partial results) or lower the target.
- Code-fenced content makes up 52% of the post. The Whisper block diagram earns its space; several phase boxes are bullet lists in frames.

#### `ai-eng-from-scratch-phase6-part2-tts-audio-models-zh.md`
**Verdict:** restructure
- The recommended stack is dated, and one piece carries legal risk. Coqui (XTTS) shut down in Jan 2024, and XTTS v2's CPML licence is non-commercial. Yet the post recommends it for a commercial audiobook product (L431). Tortoise is legacy. Current options (F5-TTS, CosyVoice 2, Fish Speech, Kokoro, commercial TTS APIs) are absent.
- The scenario has users upload 30 s of their own voice, but the post never discusses consent, speaker verification, watermarking or impersonation abuse. For a voice-cloning product that is a required section, not optional.
- The MOS figures contradict each other: Tortoise is 4.5 at L35 and 4.2 at L337. No MOS figure has a source.
- The nav's next post is "Phase 7 Part 1：推薦系統工程基礎（即將推出）", and the footer index invents phases 3–7. Phase 7 is Transformers.

#### `ai-eng-from-scratch-phase7-part1-transformer-architecture-zh.md`
**Verdict:** light edit
- The opening quote says KV cache takes "首 token 延遲從 8s 降到 400ms". KV cache speeds up decode, not time-to-first-token, which is prefill. §6.2's "Decode 計算量 O(n) → O(1) per step" is also wrong: attention over the cache is still O(t) per step, and only the projections become O(1).
- §六–七 (KV cache sizing, PagedAttention, vLLM) and the closing deployment walkthrough overlap heavily with Phase 11 Part 1 (inference serving). Keep the attention math here and move the serving configuration there.
- Stale examples: the KV-cache sizing uses LLaMA-2 7B with MHA. Use a current GQA model, and mention MLA (DeepSeek) as the next step after GQA. Flash Attention stops at v2.
- Good core: the √dₖ explanation and the KV-cache memory formula are clear and worth keeping.

#### `ai-eng-from-scratch-phase7-part2-training-variants-zh.md`
**Verdict:** light edit
- "FP8 訓练（H100 Only）" is stale. Blackwell supports FP8/MXFP8/FP4, and DeepSeek-V3 showed FP8 pretraining at scale. "ROCm FP8 支援尚未成熟（2025）" also needs re-verifying.
- The MoE section is Mixtral-only. Add fine-grained and shared experts (DeepSeekMoE) and auxiliary-loss-free load balancing, because §6.2 calls load balancing "最核心的工程問題".
- Decision 6 (Flash Attention) and the §9.3 inference table duplicate Part 1. Replace decision 6 with something training-specific, such as WSD vs cosine or μP vs manual LR sweeps. Much of the Phase 3 distributed-training box duplicates Phase 10 Part 2.
- The nav names "Phase 8 Part 1：Pre-training 與 Fine-tuning 策略"; Phase 8 is diffusion.

#### `ai-eng-from-scratch-phase8-part1-diffusion-models-zh.md`
**Verdict:** restructure
- The architecture story ends at SD 1.5/SDXL/SDXL Turbo. It has no DiT backbones (SD3, FLUX), no flow matching or rectified flow (the key conceptual shift since 2024), and no current open image models. Decision 6, "SDXL vs SD v1.5", is not a 2026 decision. Add a §五 subsection on DiT and flow matching, and redo decision 6 as "U-Net LDM vs DiT/flow model".
- The cost math contradicts itself. The same scenario comes out at "$14.6/日" in the §九 budget check and "$2.7/日" in the funnel beneath it. The funnel starts at "$1,050/日" and uses a 55% cache hit rate, while the budget check uses 50%. Decision 5 is titled "INT8 vs FP16" but its table compares against FP32.
- A "semantic cache" that returns previously generated product images for similar prompts is questionable for e-commerce product shots. Justify it or drop it.
- The DDPM/DDIM derivation (§三–四) is the strongest part; keep it.

#### `ai-eng-from-scratch-phase8-part2-gan-video-generation-zh.md`
**Verdict:** restructure
- The title promises 影片生成, but §七 covers VideoGAN/MoCoGAN (2017–18) and then a single table row for Wan 2.1. Modern video diffusion and DiT models get no architectural treatment. "影片生成在 2024 年仍以 Diffusion 為主流" is dated. Either expand §七 into a real video-DiT section (temporal attention, 3D VAE, cost per second of video) or retitle the post to GAN-focused.
- The GAN material (§三–六: WGAN, spectral norm, StyleGAN AdaIN, Pix2Pix/CycleGAN) is solid. The §九 "where GAN still wins" guide is the post's best practitioner takeaway.
- Delete "這正是面試官真正在考察的能力" (L508). The nav's next post is "Phase 9 Part 1（即將發布）", which exists.

#### `ai-eng-from-scratch-phase9-part1-rl-fundamentals-zh.md`
**Verdict:** restructure
- The biggest staleness gap in the batch. The LLM-RL story ends at PPO-RLHF plus DPO, with no GRPO or RL from verifiable rewards (RLVR). Those have been the dominant LLM RL methods since DeepSeek-R1 (Jan 2025) and underpin reasoning models. Add a §七 subsection and a decision "PPO vs GRPO". The "SFT → RM → PPO" framing in §六 then needs to become "one of several pipelines".
- The InstructGPT figure is misquoted. The paper's headline is that 1.3B InstructGPT is preferred over 175B **GPT-3**, not over a "175B SFT 模型". The ~85% win rate is 175B InstructGPT vs 175B GPT-3. The §9.1 table (有害輸出率 15% → 4.5%, TruthfulQA 40% → 57%) and the §9.2 cost-per-scale table are unsourced.
- The title promises "遊戲 AI 的根基", but game RL gets only DQN. Either trim the title to the LLM-alignment angle or add a short AlphaGo/self-play box.
- The nav's previous link is "Phase 8 Part 2：分散式訓練" and the next is an unplanned "Phase 9 Part 2"; the footer links a non-existent "Phase 1 總覽".

### Top 5 highest-impact fixes in this batch
1. **Regenerate every series nav and footer index from the real file list.** Do it with one script across all 43 posts. Today readers are sent to posts that do not exist, about topics this series does not cover (MLOps, 推薦系統, RAG in Phase 5/7). Add a real series index (an `ai-eng-from-scratch` tag or taxonomy) and fix the stale ⬜ inventory in `AI_ENG_FROM_SCRATCH_PLAN.md`.
2. **Remove the interview framing, as CLAUDE.md requires for this series.** Drop the "Interview" tag, rename 面試情境 to a neutral engineering-scenario heading, and grep out the 面試官/面試 lines and footers (phase3, 4.1, 4.2, 6.1, 8.1, 8.2, 2.2, 10.1).
3. **Correct the fabricated or misattributed numbers that carry a post's argument.** The worst: WMT BLEU (5.2 §九), InstructGPT (9 §1.2), the LLaMA-2 data mix and "7B ≈ Chinchilla-70B" (10.2), Whisper v3 specs and GPU-concurrency cost (6.1), the diffusion cost funnel (8.1), and the GQA/LoRA param math and 8×H100 memory (10.3). Then make a rule: every benchmark figure gets a citation or an "illustrative" label.
4. **Refresh the four model-landscape posts that are two years stale.** Phase 9 needs GRPO/RLVR. 8.1 needs DiT and flow matching. 4.3 needs current VLMs and world models, replacing GPT-4V, LLaVA-1.5 and Sora-2024. 6.2 needs a current TTS stack, a licence fix for XTTS, and a voice-cloning consent section.
5. **Remove the cross-post duplication and fix the foundation-post template.** Phase 1.1 and Phase 3 share four decisions. Phase 2.1 §4.2 pre-empts Phase 2.2. Flash Attention and KV cache span 7.1, 7.2 and 11.1. Distributed training spans 7.2 and 10.2. For math, probability and history posts, replace the forced "< 10K 用戶" three-phase scaffold with learner-depth stages. Convert fenced data tables to Markdown tables, and keep only the diagrams that show a mechanism.
