# B07 — ai-eng-from-scratch phases 1–5 (11 posts)

Reviewer brief: `docs/content-audit/inputs/REVIEW_BRIEF.md`. Mechanical baseline: `scripts/review_posts.py` reports **0 errors, 0 warnings** for all 11 files (also under `--strict`); every `/posts/...` link in the batch resolves to an existing file, and the `phase6-part1-asr-zh` forward link from phase 5 part 3 exists. Nothing below repeats the mechanical output.

## Batch summary

The eleven posts are a coherent Traditional-Chinese curriculum (math → classical ML → DL → CV → NLP) that was generated in one sitting (all dated 2026-06-21, 09:00–14:00, consecutive `weight: 1..11`) to the interview-series template: every post carries a 「三個演進階段」 block (15–24 % of its length) and a 「為什麼選 X 不選 Y」 section (3–16 %), plus a 「工程情境」 opener that in six posts still reads "技術主管問：…". Against `AI_ENG_FROM_SCRATCH_PLAN.md` coverage is complete and filenames match the inventory exactly, but the plan's status table is stale (phases 3–5 are marked ⬜ although all nine posts exist). The core teaching content is mostly sound: formulas (chain rule, BCE/MSE gradients, Adam/AdamW/Lion, LSTM/GRU, Bahdanau/Luong, BLEU) check out, and the Vaswani/YOLO/EfficientNet/CLIP/BLIP-2 reference numbers are accurate. The problems are concentrated in three places: (1) a handful of genuine factual slips a learner would absorb — forward-KL attributed to variational inference, A/B-test sample sizes ~30× too small, Faster R-CNN R50-FPN quoted at 46 mAP, a `225 × 9` parameter count, a "99 %" saving that is 94.7 %; (2) code that references real APIs but would not run or does not do what the prose says (target-encoding "fix" that still leaks, stale XGBoost `fit(early_stopping_rounds=…)`/`best_ntree_limit`, `convert_sklearn` on an XGBClassifier without registration); (3) 「系統效應」 tables of invented before/after numbers, about half of which are labelled 示意 and half presented as "實測" or "真實生產環境案例". The phase sections teach something only where "phase" coincides with the topic's own ladder (transfer-learning strategy in 4-1, representation choice in 5-1, RNN→attention in 5-2); elsewhere they are generic MLOps stacks (Feature Store, Triton, Kafka) bolted onto a maths post. Verdicts: **3 Ready** (5-1, 5-2, 5-3), **7 Needs revision**, **1 Not ready** (1-2, two factual errors that are each a one-paragraph fix).

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding (line) |
|---|---|---|---|---|---|---|---|---|---|---|
| phase1-part1-linear-algebra-zh | 613 | 4 | 4 | 3 | 3 | 3 | 4 | 3.5 | Needs revision | L263–269 batch-size table: throughput triples (9.6K→31K samples/s) while GPU utilisation moves 78→85 % — the two columns cannot both be true |
| phase1-part2-probability-stats-zh | 665 | 3 | 4 | 4 | 3 | 4 | 4 | 3.7 | **Not ready** | L397–400 says forward KL D(P‖Q) is "用於：變分推斷" — VI minimises *reverse* KL D(Q‖P) (mode-seeking); the box has the two rows swapped |
| phase2-part1-classical-ml-zh | 714 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Needs revision (major) | L458–466 prose says "正確做法是 K-Fold Target Encoding", the code shows plain `category_encoders.TargetEncoder(smoothing=10)` which is not K-fold and still leaks on the training set |
| phase2-part2-ensemble-optimization-zh | 757 | 3 | 4 | 4 | 4 | 4 | 4 | 3.7 | Needs revision | L581–584 `model.fit(..., early_stopping_rounds=50)` + `model.best_ntree_limit` are removed in XGBoost 2.x and contradict L526 and §4.4 which pass it to the constructor |
| phase3-part1-neural-networks-zh | 723 | 3 | 4 | 4 | 4 | 3 | 4 | 3.7 | Needs revision | L667 "以下數字來自真實生產環境…案例分析" introduces two tables with no source; same post labels its optimizer table 示意 — the honesty standard is inconsistent |
| phase4-part1-cnn-image-fundamentals-zh | 538 | 3 | 4 | 4 | 4 | 4 | 4 | 3.8 | Needs revision | L155 "5×5 輸入 → 3×3 輸出 = 225 × 9 = 2,025 參數" — a 5×5 input has 25 values; the FC layer is 25 × 9 = 225 parameters |
| phase4-part2-detection-segmentation-zh | 432 | 3 | 4 | 3 | 4 | 4 | 4 | 3.7 | Needs revision | L255 / L394 Faster R-CNN R50-FPN "~46 / 46.0 mAP" — detectron2 model zoo lists 40.2 (R101-FPN 42.0); also L109 "50K 張/天 ≈ 峰值 600 QPS" vs L397 "50K 張/天，即 0.58 QPS" |
| phase4-part3-vlm-3d-worldmodels-zh | 577 | 4 | 4 | 3 | 4 | 4 | 4 | 3.8 | Needs revision | L181 CLIP ViT-L/14 "Text Encoder 輸出 512 維" — both towers project to 768 (512 is ViT-B/32); L493 "吞吐量高 24x" is vLLM vs HF Transformers, not vs TGI (3.5×) |
| phase5-part1-text-fundamentals-zh | 659 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Ready | L372 "維度與詞彙量的平方根成正比… 1M → dim≈300" contradicts itself (√1M = 1000); minor |
| phase5-part2-seq2seq-attention-zh | 601 | 4 | 5 | 4 | 4 | 4 | 4 | 4.2 | Ready | L287–293 BLEU-by-length table cites Bahdanau 2015 Fig. 2 but the values (~38 for 1–10 tokens) are higher than the figure shows (❓) |
| phase5-part3-advanced-nlp-zh | 596 | 4 | 4 | 4 | 4 | 4 | 4 | 4.0 | Ready | L257 "512 tokens（約 300–400 中文字）" — Chinese BERT tokenises per character, so 512 tokens ≈ 510 characters; minor |

Theses as read: 1-1 "maths is the first debugging key for NaN/non-convergence/optimizer choice" · 1-2 "every loss and regulariser is a probabilistic assumption; know it to know when the model fails" · 2-1 "for structured data in production, tabular ML still wins on latency/explainability/cost" · 2-2 "ensembles are the bias–variance decomposition made operational; XGBoost + tuning covers 80 % of production" · 3 "understand first principles so you can diagnose, not just run" · 4-1 "pick the backbone and the transfer strategy by data size and domain gap" · 4-2 "detection is a latency/precision/labelling-cost trade; domain data beats model choice" · 4-3 "VLM, 3D reconstruction and world models each remove one limit of 2D perception" (survey; thesis is weak) · 5-1 "representation choice sets the ceiling; TF-IDF until it doesn't" · 5-2 "attention was invented to break the fixed context vector; Transformer is the systematic answer to RNN pain" · 5-3 "pick extractive vs generative by auditability and latency".

## Patterns

### Content quality
- The mechanism sections are the strong half: chain-rule/backprop derivation (3:L239–283), MLE→cross-entropy and MAP→L2/L1 (1-2:L303–337), LSTM/GRU gates with parameter counts (5-2:L187–235), Bahdanau vs Luong (5-2:L317–372), BERT MLM 80/10/10 (5-3:L215–224) are correct and well explained.
- Three posts carry a dated-context note that keeps old material honest (4-1:L296 DINOv2/SigLIP; 4-3:L250 "GPT-4V 已退役"; 5-2:L23 "2014–2017 年的歷史情境"; 5-1:L535 multilingual-e5/bge-m3; 5-3:L311 ModernBERT). This is the pattern to copy into the others.
- Opening quotes still invent statistics: 2-1:L16 "80% 初學者的第一直覺", 2-2:L16 "單棵決策樹 70%，一千棵樹 91%", 1-1:L219 "shape mismatch 是 90% 初學者錯誤的根源".
- Six 「工程情境」 blocks are interview prompts ("技術主管問：…請說明…" — 1-2:L20, 2-2:L22, 3:L21, 4-1:L22, 4-3:L22, 5-2:L21) and none is explicitly answered at the end of the post.

### Structure (does the house format help or pad?)
- Phase sections occupy 83–144 lines per post (15–24 %). They teach when the three phases *are* the topic's own progression: 4-1:L47–135 (feature-extraction → gradual-unfreeze → full fine-tune, duplicated again in §六), 5-1:L52–177 (TF-IDF → FastText → Sentence-BERT), 5-2:L47–138 (RNN → Seq2Seq → +Attention, which is the whole post's narrative). They pad when the "phase" is a generic MLOps stack unrelated to the lesson: 1-1:L52–145 (maths knowledge "by data size"), 1-2:L59–160, 3:L49–177 (Feature Store / Triton / TensorRT / "KV Cache 熱門特徵" in a first-principles NN post), 4-2:L58–140, 4-3:L42–139, 5-3:L57–200 (a RAG platform in a BERT post).
- Phase thresholds are inconsistent across the batch — "用戶" (1-2, 3, 5-1), "筆資料" (1-1, 2-1, 2-2, 4-1), "張/天" (4-2), "查詢/日" (4-3), "查詢/月" (5-3), "訓練樣本" (5-2) — evidence they were filled in to satisfy a template rather than derived from a scale cliff.
- Decision tables: useful where a real alternative exists and the flip condition is concrete (1-1:L540–565 CE vs MSE, FP16 vs BF16; 2-1:L572–660; 5-3:L488–563 extractive vs generative). Padding where the "alternative" is a straw man: 2-1:L597 "決策樹 vs SVM", 4-1:L409–420 "ResNet-50 vs VGG-16" (the post itself says there is no reason to choose VGG), 4-2:L372–384 one 13-line table that compresses six decisions into one-liners.
- 「系統效應」 tables (section 九) are the weakest section in 9 of 11 posts: before/after numbers with no source (see Depth).

### Depth (sourced vs invented-looking numbers, flip conditions, "when it breaks")
- Sourced and correct: 5-2:L541–550 WMT14 En→De BLEU from Vaswani Table 2; 4-2:L160–168 YOLO COCO mAP (v3 33.0, v5s 37.4, v8n 37.3, v8x 53.9, 11n 39.5, 11x 54.7); 4-1:L218–228 and L261–262 EfficientNet compound scaling (α·β²·γ² = 1.92 ≈ 2) and 0.39B vs 4.1B FLOPs; 4-3:L178–181 CLIP 400M pairs / batch 32,768; 4-3:L240–245 BLIP-2 65.2 / LLaVA-1.5 80.0 VQAv2; 5-3:L268–275 RoBERTa 16GB→160GB, batch 8K, 89.4 F1.
- Labelled 示意 (acceptable): 1-1:L571, 2-1:L326 and L666, 2-2:L730, 3:L525, 4-1:L500, 4-3:L540, 5-2:L383 and L577, 5-3:L569.
- Presented as measured but unsourced: 1-2:L621–645 fraud/NLP/A-B tables ("$850 → $320"); 2-2:L701–711 AUC/latency/cost ladder; 3:L355–359 "ImageNet ResNet-50 基準 ReLU 76.1 / GELU 76.9 / SiLU 77.2", L361 "自有資料集", L667 "真實生產環境"; 4-1:L432 iPhone 14 CoreML 45 ms vs 180 ms; 4-2:L406–413 data-flywheel table; 5-1:L284–291 "電商評論實驗" F1 table and L617–635 ROI table.
- Flip conditions are present in every decision table but several are circular or trivially true ("需要整合既有 XGBoost pipeline → 選 XGBoost", 2-1:L620; "SLA 寬鬆 → 不蒸餾", 2-2:L694).
- "When it breaks" is strong in 1-1:L384–404 (gradient-norm thresholds), 2-1:L450–470 (leakage), 3:L420–431 (BatchNorm traps), 5-1:L452–470 (five production traps) and absent in 4-3 and most of 4-2.

### Direction (overlap, gaps, stale topics, category fit)
- Overlap: SGD vs Adam, BN vs LN, He vs Xavier, FP32 vs FP16, CE vs MSE appear as decision tables in both 1-1 (L506–565) and 3 (L569–664) with the same conclusions; gradient-norm diagnosis code is duplicated verbatim (1-1:L390–396, 3:L285–292). XGBoost vs LightGBM is argued in 2-1:L606–620 and again in 2-2:L659–668 with different speed claims ("3–10 倍" vs "差距已大幅縮小").
- Gaps vs plan: Phase 1 plan is "Linear Algebra+Calculus / Probability+Stats" — covered; Phase 3 plan lists "CNN、RNN" in the nav (2-2:L746) but post 3 contains neither (they are in 4-1 and 5-2), so the nav blurb is wrong. 4-3 spends 577 lines on CLIP/NeRF/3DGS/Sora, which overlaps the planned Phase 12 (ViT+Fusion) and Phase 8 part 2 (video generation); worth deciding which post owns VLMs.
- Stale: 2-1:L608 LightGBM "快 3–10 倍" and "支援類別特徵原生輸入" predate XGBoost 2.0 (`hist` default, `enable_categorical`); 5-1:L542 "HanLP：Java/C++" (HanLP 2.x is PyTorch); 1-1:L552 "YOLO 系列使用 MSE 預測框座標" (v4+ use CIoU/GIoU).
- Category fit: `["all","ai","engineering"]` on every post matches the plan. Tags: plan says `["AI","Machine Learning","Engineering","RKK"]` + phase tags; only 1-1/1-2/2-x carry "Machine Learning", none carries "Engineering" — harmless but drifts from the plan.
- `AI_ENG_FROM_SCRATCH_PLAN.md` inventory marks phases 3–5 ⬜ although all nine files exist, and its Phase-1/2 line counts (622/682/734/777) no longer match (613/665/714/757).

### Accuracy
- Wrong: 1-2:L400 forward-KL ↔ VI; 1-2:L503–507 sample sizes (two-proportion test at p≈0.92, α=0.05, power 0.8 needs ≈1.16M / 46K / 11.6K per arm for Δ=0.1/0.5/1 pp, not 39K / 1.6K / 400); 2-2:L213 "T=100, e=0.3 → 集成錯誤率 ≈ 0.001" (binomial tail P(X≥50) = 2.2e-5; direction right, number 50× off); 3:L219 "節省 99% 參數" (5.28M vs 100.0M = 94.7 %); 3:L228 "減少 160 倍" ignores the 10K×64 = 640K embedding table (true ratio 5.12M/673K = 7.6×); 4-1:L155 225×9; 4-2:L255/L394 FRCNN 46 mAP; 4-2:L109 vs L397 QPS; 4-2:L305 vs L395 Mask R-CNN R101 mask AP 36.1 vs 38.8 in the same post; 4-3:L181 CLIP text dim; 4-3:L493 24× baseline; 5-1:L372 √ rule.
- Code: 2-1:L466 TargetEncoder is not K-fold (use `sklearn.preprocessing.TargetEncoder`, which cross-fits in `fit_transform`, or explicit folds); 2-2:L526 `XGBClassifier(early_stopping_rounds=50)` inside `RandomizedSearchCV` with no `eval_set` raises at fit time; 2-2:L581–584 removed-API usage; 2-2:L605 `convert_sklearn(xgb_model, …)` fails unless `update_registered_converter(XGBClassifier, …, convert_xgboost)` is called first (sklearn-onnx docs); 5-1:L203–205 全形→半形 runs *after* L200 already stripped punctuation, so it is dead code. The NumPy `TwoLayerNet` (3:L301–338) is correct by inspection (δ = out − y, dW2 = a1ᵀδ/B, δ1 = δW2ᵀ ⊙ 1[z1>0]); numpy was unavailable in the review environment so it was not executed.
- Debatable advice stated as rule: 4-1:L378–388 "永遠使用資料集的統計量，不要用 ImageNet 的" — when fine-tuning an ImageNet-pretrained backbone the usual practice is to keep the pretraining normalisation; dataset statistics are the right call for training from scratch. Present both.
- Internally inconsistent memory claims: 1-1:L513 "SGD 記憶體比 Adam 少 1/3" (param+grad+state: 3 vs 4 → 25 % less); 3:L527–532 SGD 1× / Adam 2× / Lion 1.33× while L515 says Lion state is half of Adam's (so Lion should equal SGD+momentum).

### Format / front matter
- Front matter is complete and uniform; all posts carry `weight` and `series: ["ai-eng-from-scratch"]` fields that the plan does not mention — fine, but document them in the plan.
- `readTime: "23 min"` on ten posts regardless of length (538–757 lines); by the house rule 538 L ≈ 19 min, 757 L ≈ 25 min. 4-2 (432 L) is correctly "16 min".
- Series navigation is inconsistent in shape: 1-1:L594–600 lists only Phases 1–3 as "已發布"; 2-1:L706 bare prev/next line; 4-1:L518–531 full index; 5-2:L601 links the series to `/tags/ai/` instead of `/tags/ai-eng-from-scratch/`.
- 4-2:L432 footer defines RKK as "Reasoning × Knowledge × Knowledge application" — no other post defines it; if that is the intended expansion it belongs in the plan or the about page, not one footer.
- Decision tables are mixed-format within the batch: Markdown tables (1-1, 4-1, 4-2, 4-3) vs fixed-width code blocks (1-2, 2-1, 2-2, 3, 5-x). The code-block form exceeds 80 columns in 2-1:L574–584 and 5-1:L521–533 and will scroll on mobile.

## Top findings

| # | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| 1 | blocker | phase1-part2:L397–406 | Forward KL D(P‖Q) labelled mass-covering and "用於：變分推斷"; reverse KL labelled "用於：VAE". VI (and the VAE ELBO) minimise reverse KL D(Q‖P); forward KL is what MLE/cross-entropy minimises and what EP uses | Swap the two "用於" lines: Forward → MLE / cross-entropy / expectation propagation; Reverse → variational inference, VAE ELBO |
| 2 | blocker | phase1-part2:L503–507 | Test-set sizes for Δacc = 0.1/0.5/1 pp given as 39K/1.6K/400. Two-proportion test at p≈0.92 (α 0.05, power 0.8) needs ≈1.16M / 46K / 11.6K per arm; even a paired McNemar needs far more than 400 | Recompute with the stated formula, or state the test and discordance assumption that yields the numbers |
| 3 | major | phase2-part1:L458–466 | "正確做法是 K-Fold Target Encoding" followed by `category_encoders.TargetEncoder(smoothing=10)` — plain smoothed encoding, still leaks when fit on the training frame | Show `sklearn.preprocessing.TargetEncoder` (cross-fitted `fit_transform`) or an explicit `KFold` loop |
| 4 | major | phase2-part2:L581–584 | `fit(..., early_stopping_rounds=50)` and `best_ntree_limit` — removed in XGBoost 2.0 (`ntree_limit` removal in release notes; docs now show constructor arg and `best_iteration`); contradicts L526 and §4.4 in the same post | Use `XGBClassifier(early_stopping_rounds=50)` + `model.best_iteration` |
| 5 | major | phase2-part2:L605–609 | `convert_sklearn(xgb_model, …)` fails for XGBClassifier without `update_registered_converter(..., convert_xgboost)` | Add the registration lines from the sklearn-onnx XGBoost tutorial, or use `onnxmltools.convert_xgboost` |
| 6 | major | phase4-part2:L255, L394 | Faster R-CNN R50-FPN "~46 / 46.0 mAP"; detectron2 model zoo: 40.2 (R101-FPN 42.0). L256/L394 "A100 150–200 ms" also ~4× slower than the 38 ms/img V100 figure | Use 40.2 / 42.0 and ~40 ms; keep the YOLO comparison, which still holds |
| 7 | major | phase4-part2:L109 vs L397 | "50K 張/天 ≈ 峰值 600 QPS，需 2 副本" vs "50K 張/天，即 0.58 QPS" | State average 0.58 QPS and a justified peak multiplier (e.g. 30 fps camera bursts), then size replicas from that |
| 8 | major | phase4-part1:L155 | "5×5 輸入 → 3×3 輸出 = 225 × 9 = 2,025 參數" — 25 inputs × 9 outputs = 225 | Correct to 225 vs 9; the 25× point survives |
| 9 | major | phase3:L667–690 | "以下數字來自真實生產環境…案例分析" — two before/after tables with no source, in a post whose other tables are labelled 示意 | Either cite the case or relabel 示意估算 like L525 |
| 10 | major | phase4-part1:L378–388 | "永遠使用資料集的統計量" presented as the only correct option for fine-tuning a pretrained backbone | State: pretrained backbone → keep pretraining normalisation; from scratch → dataset statistics; mention re-estimating BN stats as the middle path |
| 11 | major | phase1-part1:L263–269 | Batch-size table: utilisation 78 % → 85 % while throughput 9.6K → 31K samples/s; columns are mutually inconsistent and unsourced | Keep one column (throughput) and label it 示意, or derive utilisation from throughput |
| 12 | minor | phase3:L219, L228 | "節省 99%" (actual 94.7 %); "減少 160 倍" counts only the first dense layer and omits the 640K-param embedding table (true 7.6×) | Recompute both; the embedding point is still a win when stated honestly |
| 13 | minor | phase4-part3:L181, L493 | CLIP ViT-L/14 text tower outputs 768-d (512 is ViT-B/32); vLLM "24x" is vs HF Transformers, vs TGI it is 3.5× | Fix both numbers; the vLLM row sits in a vLLM-vs-TGI table so the 24× is misleading |
| 14 | minor | phase2-part2:L213, L526 | Binomial tail for T=100, e=0.3 is 2.2e-5 not 1e-3; `RandomizedSearchCV` over `XGBClassifier(early_stopping_rounds=50)` with no `eval_set` raises | Fix number; drop early stopping from the CV estimator or pass `eval_set` via `fit_params` |
| 15 | minor | all ×10 | `readTime: "23 min"` regardless of 538–757 lines; 5-2:L601 series link → `/tags/ai/` | Recalibrate (≈32 L/min); point to `/tags/ai-eng-from-scratch/` |

## Recommendations

1. **Fix the five factual slips first (findings 1, 2, 6, 8, 12).** WHY: they are the only errors a learner would internalise as "the rule"; everything else is polish. HOW: one PR, ~20 lines total, re-run `review_posts.py` and recompute each number in the commit message.
2. **Make every code block either runnable or clearly pseudocode.** WHY: 2-1 and 2-2 show "正確做法" code that is wrong or on removed APIs — worse than no code. HOW: pin a version in a comment (`# xgboost>=2.0`), run each snippet against the pinned library in CI (`scripts/` could gain a `check_snippets.py` that extracts ```python blocks tagged `# run`), and replace undefined helpers (`load_stopwords`, `dict_lookup`) with `...` or a one-line stub.
3. **Apply one labelling rule to all 「系統效應」 tables.** WHY: half the batch says 示意估算 and half says 實測/真實案例 for the same kind of number, so readers cannot tell which to trust. HOW: default label "示意估算，非實測數據" on every unsourced table (1-2:L621–645, 2-2:L701–711, 3:L355–359/L667, 4-1:L432, 4-2:L406–413, 5-1:L284–291/L617–635); any table without the label must cite a paper, model zoo or own benchmark.
4. **Cut or rewrite the phase section where it is an MLOps stack rather than the topic's ladder.** WHY: the plan now says the section is optional and must not be padding; in 1-1, 1-2, 3, 4-2, 4-3 and 5-3 it adds 83–144 lines of Feature Store / Triton / Kafka that belong in Phase 17. HOW: keep 4-1, 5-1, 5-2 as they are (phase = technique progression); in the other six replace the three diagrams with a single "when does this scale cliff happen" paragraph, or delete and let Phase 17 own deployment.
5. **De-duplicate 1-1 §八 and 3 §八.** WHY: the same six optimizer/normalisation/init decisions appear twice with the same flip conditions and once with a contradictory memory claim. HOW: keep the derivations in 1-1 (maths) and in 3 link back ("見 Phase 1 Part 1 §八"), keeping only the Lion/AdamW rows that are new.
6. **Convert the six "技術主管問" openers into a scenario the post answers.** WHY: the series is explicitly not interview prep (`CLAUDE.md`), and an unanswered question is the structure the plan asked to remove. HOW: keep the scenario but add 3–5 closing bullets under 九 that answer it with the post's own numbers (5-3 already nearly does this at L585–588).
7. **Add a dated-context note to the posts that lack one.** WHY: 4-1, 4-3, 5-1, 5-2, 5-3 show that one line ("2026 年的預設是…") keeps 2017–2023 material honest. HOW: 2-1 (XGBoost 2.0/categorical, LightGBM speed), 2-2 (Optuna/XGBoost API), 4-2 (YOLO11 naming, licence), 1-1 (YOLO loss) each need one sentence.
8. **Update `AI_ENG_FROM_SCRATCH_PLAN.md` inventory and conventions.** WHY: it is the series' source of truth and currently says phases 3–5 are not started, lists stale line counts, and omits the `weight`/`series` fields every post uses. HOW: tick the nine posts, drop the line counts (they rot), document `weight`/`series`, and decide whether VLMs live in 4-3 or Phase 12.
9. **Calibrate `readTime` and unify the series nav.** WHY: ten posts say 23 min for 538–757 lines; three nav formats and one wrong tag link. HOW: `lines/32` rounded; adopt the 4-1:L510–531 full-index format (prev/next + phase table) everywhere, pointing at `/tags/ai-eng-from-scratch/`.
10. **Keep decision tables only where the alternative is live.** WHY: 4-1 "ResNet-50 vs VGG-16" and 2-1 "決策樹 vs SVM" argue against options nobody picks; 4-2 compresses six decisions into 13 lines. HOW: 3–4 rows per post with a real flip condition; move retired comparisons into a one-line historical note.

## Verified / unverified claims

- ✅ phase1-part1:L265 LoRA r=8, d=4096: 16.78M → 65,536 params, 256× (recomputed)
- ✅ phase1-part1:L384 sigmoid gradient ≤ 0.25, (0.25)^20 = 9.1e-13 ≈ 1e-12 (recomputed)
- ✅ phase1-part1:L530–534 Xavier Var = 2/(n_in+n_out), He Var = 2/n_in
- ✅ phase1-part1:L556–560 FP16 max 65504; ~3 decimal digits; BF16 range = FP32
- ❌ phase1-part1:L263–269 batch-size utilisation vs throughput columns inconsistent (see finding 11)
- ❌ phase1-part1:L513 "SGD 記憶體比 Adam 少 1/3" — param+grad+state 3 vs 4 → 25 % (recomputed)
- ✅ phase1-part2:L249 Gaussian peak 1/√(2π) ≈ 0.4 at σ=1; 68 % within ±σ
- ✅ phase1-part2:L380 H([0.99,0.01]) = 0.081 bits (recomputed)
- ✅ phase1-part2:L433–437 BCE at p = 0.99/0.5/0.01 → 0.010/0.693/4.605 (recomputed)
- ✅ phase1-part2:L489 n=1000, acc 92 %: Wald CI [90.3, 93.7] ≈ post's [90.2, 93.8]; L490 n=100 Wald [86.7, 97.3] vs post [85.0, 97.0] — loose but defensible (Wilson gives [85.0, 95.9])
- ✅ phase1-part2:L591 PSI = binned symmetric KL (Jeffreys) — correct
- ❌ phase1-part2:L400 forward KL → variational inference (finding 1)
- ❌ phase1-part2:L505–507 sample sizes (finding 2; recomputed 1.16M / 46K / 11.6K per arm)
- ❓ phase1-part2:L576 "MC Dropout 延遲 <2×" — T stochastic passes (T≈20–50) cost T× unless batched; not supported
- ✅ phase2-part1:L162 c5.xlarge $0.17/h; 3 × 730 h ≈ $372 + MLflow host ≈ "$400–600"
- ✅ phase2-part1:L287 odds ratio = exp(wᵢ); L303 Gini max = 1 − 1/K; L365 SVM margin 2/‖w‖
- ✅ phase2-part1:L484 2026-06-21 is a Sunday → `day_of_week = 6` under Python's Monday=0 convention
- ✅ phase2-part1:L498–504 XGBoost importance types weight/gain/cover exist
- ❌ phase2-part1:L458–466 "K-Fold" code is not K-fold (finding 3)
- ❓ phase2-part1:L608 "LightGBM 快 3–10 倍" — true for pre-2.0 exact XGBoost; 2-2:L434 in the same batch says the gap has largely closed since `hist` became default (confirmed in XGBoost 2.0.0 release notes)
- ✅ phase2-part2:L227 OOB fraction 36.8 % (1/e); L310–316 GOSS/EFB description; L434 XGBoost 2.0 `hist` default (release notes)
- ✅ phase2-part2:L370–384 `XGBClassifier(**params, eval_metric='auc')` with `early_stopping_rounds` in the constructor — current API (xgboost docs)
- ❌ phase2-part2:L213 binomial tail 2.2e-5, not 1e-3 (recomputed)
- ❌ phase2-part2:L581–584 `fit(early_stopping_rounds=…)`, `best_ntree_limit` — removed/renamed in 2.x (release notes: `ntree_limit` removed; docs: use `best_iteration`)
- ❌ phase2-part2:L605 `convert_sklearn` on XGBClassifier without converter registration (sklearn-onnx tutorial: "The conversion fails but it is expected")
- ✅ phase2-part2:L598 5M/day = 57.9 req/s (recomputed)
- ❓ phase2-part2:L66 "2015–2023 表格競賽 top-10 解法 >75 % 用 XGBoost/LightGBM" — no source
- ✅ phase3:L239–283 backprop derivation; L301–338 NumPy net gradients correct by inspection (numpy not available to execute)
- ✅ phase3:L344–345 GELU min ≈ −0.17, SiLU min ≈ −0.28; L463–491 Adam/AdamW/Lion update rules match the papers
- ❌ phase3:L219 "99 %" → 94.7 %; L228 "160 倍" → 7.6× including the embedding table (recomputed)
- ❓ phase3:L355–359 ReLU/GELU/SiLU ImageNet 76.1/76.9/77.2 — no source; ❓ L361 "自有資料集"; ❓ L497 "BERT AdamW vs Adam 0.3–0.8 %"; ❓ L667 "真實生產環境"
- ✅ phase4-part1:L37 224×224×3 = 150,528; ×512 = 77M; L158 64×9×3 = 1,728; L201–209 VGG FC 102.8M vs GAP 2.0M (≈50×); L222–227 ResNet-50 25M/76.1 %, EfficientNet-B0 5.3M/77.1 %, ConvNeXt-T 29M/82.1 %; L256–262 α·β²·γ² = 1.92, 0.39B vs 4.1B FLOPs; L187–193 max-pool example (recomputed)
- ❌ phase4-part1:L155 225 × 9 (finding 8)
- ❓ phase4-part1:L226 GoogLeNet top-1 74.8 % (paper reports top-5 only; torchvision 69.8 %); ❓ L432 iPhone 14 CoreML 45/180 ms
- ✅ phase4-part2:L160–168 YOLO COCO mAP values (v3 33.0, v5s 37.4, v8n 37.3, v8x 53.9, 11n 39.5, 11x 54.7); L193 Ultralytics AGPL-3.0; L269 RPN IoU 0.7/0.3; L354–357 0.58 QPS
- ❌ phase4-part2:L255/L394 Faster R-CNN R50-FPN 46 mAP → 40.2 (detectron2 MODEL_ZOO); L256 A100 150–200 ms vs 38 ms/img on V100 in the same zoo
- ❌ phase4-part2:L109 vs L397 QPS contradiction; L305 vs L395 Mask R-CNN R101 36.1 vs 38.8 mask AP within the post (zoo: 38.6)
- ❌ phase4-part2:L330 IoU 0.5 ↔ "中心偏移 ≤ 25 %": for equal boxes IoU = (1−s)/(1+s) = 0.5 at s = 33 % (recomputed)
- ✅ phase4-part3:L178–179 CLIP 400M pairs, batch 32,768; L189 zero-shot 76.2 %; L240–241 BLIP-2 65.2 / LLaVA-1.5 80.0 VQAv2; L216–218 BLIP-2 Q-Former 188M, 32 queries; L282–284 256³ = 16.7M cells = 67 MB; L419 Sora 1080p/60 s; L478 PointPillars 62 Hz
- ❌ phase4-part3:L181 ViT-L/14 text tower 512-d → 768-d (HF `openai/clip-vit-large-patch14` projection_dim 768)
- ❌ phase4-part3:L493 "24x" is vs HF Transformers; vs TGI 3.5× (vLLM launch post)
- ❓ phase4-part3:L180 "592 V100 × 18 天" — that is the RN50x64 run in the CLIP paper; ViT-L/14 used fewer GPUs/days; ❓ L242 GPT-4V "~87 %" VQAv2; ❓ L546 "+24 % 轉換率"
- ✅ phase5-part1:L200 regex range 一-鿿 = U+4E00–U+9FFF; L338–348 gensim `FastText(vector_size=…, sg=…, epochs=…)` API; L380 `cc.zh.300` exists; L619–635 ROI arithmetic internally consistent (recomputed: −46 %, $2,775, 5.4 months)
- ❌ phase5-part1:L372 √ rule contradicts its own example (√1M = 1000, not 300)
- ❌ phase5-part1:L203–205 全形→半形 after punctuation already stripped (dead code)
- ❓ phase5-part1:L284–291 "電商評論實驗" F1 table; ❓ L587 "cuFAISS" (not a product name; FAISS GPU is `faiss-gpu`)
- ✅ phase5-part2:L541–550 WMT14 En→De BLEU 24.6 / 25.16 / 27.3 / 28.4 and the 41.x En→Fr note (Vaswani Table 2); L560 base model ≈12 h on 8 P100; L227–233 LSTM 4(H+D)H vs GRU 3(H+D)H; L330–372 Bahdanau/Luong score functions
- ❓ phase5-part2:L287–293 BLEU-by-length values attributed to Bahdanau Fig. 2 appear ~10 points higher than the figure's RNNenc curve; could not confirm the exact values
- ✅ phase5-part3:L220–224 MLM 15 % / 80-10-10; L254–258 BERT-base 110M, large 340M, BooksCorpus 800M + Wikipedia 2.5B words; L268–275 RoBERTa 160 GB / batch 8K / 500K steps / SQuAD2 F1 89.4 (BERT-large 83.1 with TriviaQA aug is the figure RoBERTa compares against); L286–296 ALBERT 128-d embeddings, xxlarge 235M/4096; L311 ModernBERT Dec 2024, 8K context
- ❌ phase5-part3:L257 512 tokens ≈ 300–400 中文字 (character-level tokeniser → ≈510)
- ❓ phase5-part3:L300 "DeBERTa-v3-large 超越 GPT-3（175B）" — true for some NLU benchmarks vs few-shot GPT-3, overstated as written; ❓ L380 BM25 75 / DPR 87 / Hybrid 93 recall (no source)
