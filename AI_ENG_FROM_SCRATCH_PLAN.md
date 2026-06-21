# AI Engineering from Scratch — Blog Series Plan

Reference curriculum: https://github.com/rohitg00/ai-engineering-from-scratch

---

## Series Identity

- **Series slug:** `aifs`
- **Post naming:** `ai-eng-from-scratch-phase{N}-part{M}-{slug}-zh.md`
- **Tags:** `["AI", "Machine Learning", "Engineering", "Interview", "RKK"]` + phase-specific tags
- **Category:** `["engineering", "ai", "all"]`
- **Language:** Traditional Chinese (繁體中文)
- **Authors:** `["yen"]`

---

## Coverage Strategy

19 phases × avg ~22 lessons = ~320 lessons total.
One post per phase; larger phases split into 2–4 posts.

| Phase | Title | Lessons | Posts | Split |
|---|---|---|---|---|
| 1 | Math Foundations | 22 | 2 | Linear Algebra+Calculus / Probability+Stats |
| 2 | ML Fundamentals | 18 | 2 | Classical ML / Ensemble+Optimization |
| 3 | Deep Learning Core | 13 | 1 | Full arc |
| 4 | Computer Vision | 28 | 3 | Pixels→CNN / Detection+Seg / VLMs+3D |
| 5 | NLP | 29 | 3 | Text Basics / Seq2Seq / Advanced NLP |
| 6 | Speech & Audio | 17 | 2 | ASR / TTS+Audio Models |
| 7 | Transformers Deep Dive | 14 | 2 | Architecture / Training+Variants |
| 8 | Generative AI | 14 | 2 | Diffusion / GAN+Video |
| 9 | Reinforcement Learning | 12 | 1 | RL Fundamentals |
| 10 | LLMs from Scratch | 22 | 3 | Tokenization / Pretraining / Fine-tuning |
| 11 | LLM Engineering | 17 | 2 | Inference+Serving / RAG+Evals |
| 12 | Multimodal AI | 25 | 2 | ViT+Fusion / Agents+Computer-Use |
| 13 | Tools & Protocols | 23 | 2 | MCP+APIs / Orchestration |
| 14 | Agent Engineering | 42 | 4 | Loop+Memory / Planning / Frameworks / Production |
| 15 | Autonomous Systems | 22 | 2 | Long-Horizon / Self-Improvement+Safety |
| 16 | Multi-Agent & Swarms | 25 | 2 | Coordination / Emergence+Collective |
| 17 | Infrastructure & Production | 28 | 3 | Serving / Observability / Cost+Scale |
| 18 | Ethics, Safety & Alignment | 30 | 2 | Technical Safety / Governance |
| 19 | Capstone Projects | 85 | 3 | 3 flagship showcase projects |

**Total: ~44 posts**

---

## Rollout Schedule

| Month | Phases | Posts | Focus |
|---|---|---|---|
| Month 1 | 1–4 | ~8 | Foundations (Math, ML, DL, CV) |
| Month 2 | 5–8 | ~9 | Core DL + Generative |
| Month 3 | 9–12 | ~10 | LLMs + Multimodal |
| Month 4 | 13–16 | ~10 | Agents + Infrastructure |
| Month 5 | 17–19 | ~8 | Production + Safety + Capstone |

---

## Standard Post Structure

Every post follows this section order (using Chinese numerals 一–十一):

1. **一、核心問題** — why this topic matters; what breaks without it
2. **二、三個演進階段** — beginner / practitioner / expert framing with ASCII diagrams
3. **三–七、Deep Dives** — major concepts, each with ASCII diagram + decision rationale
4. **八、為什麼選 X 不選 Y** — decision tables with flip conditions
5. **九、系統效應** — before/after numbers (accuracy, latency, cost)
6. **十、面試答題要點** — model RKK answer in blockquote
7. **Series navigation** — previous / next phase links

### Quality checklist per post

- [ ] 2–4 ASCII block diagrams
- [ ] Concrete numbers throughout (ms, %, $, QPS)
- [ ] 4–6 Why-X-not-Y decisions
- [ ] 600–900 lines
- [ ] No mention of "Google" (use "Cloud" in tags)
- [ ] Tags include `"RKK"` and `"Interview"`
- [ ] readTime calibrated: 500L≈18min, 700L≈23min, 900L≈28min
- [ ] Opening 4-line contrast quote
- [ ] Series nav links at bottom

---

## Post File Inventory

Track status: ✅ Done | 🔄 In Progress | ⬜ Not Started

### Phase 1 — Math Foundations
- ✅ `ai-eng-from-scratch-phase1-part1-linear-algebra-zh.md` (622 lines)
- ✅ `ai-eng-from-scratch-phase1-part2-probability-stats-zh.md` (682 lines)

### Phase 2 — ML Fundamentals
- ✅ `ai-eng-from-scratch-phase2-part1-classical-ml-zh.md` (734 lines)
- ✅ `ai-eng-from-scratch-phase2-part2-ensemble-optimization-zh.md` (777 lines)

### Phase 3 — Deep Learning Core
- ⬜ `ai-eng-from-scratch-phase3-part1-neural-networks-zh.md`

### Phase 4 — Computer Vision
- ⬜ `ai-eng-from-scratch-phase4-part1-cnn-image-fundamentals-zh.md`
- ⬜ `ai-eng-from-scratch-phase4-part2-detection-segmentation-zh.md`
- ⬜ `ai-eng-from-scratch-phase4-part3-vlm-3d-worldmodels-zh.md`

### Phase 5 — NLP
- ⬜ `ai-eng-from-scratch-phase5-part1-text-fundamentals-zh.md`
- ⬜ `ai-eng-from-scratch-phase5-part2-seq2seq-attention-zh.md`
- ⬜ `ai-eng-from-scratch-phase5-part3-advanced-nlp-zh.md`

### Phase 6 — Speech & Audio
- ⬜ `ai-eng-from-scratch-phase6-part1-asr-zh.md`
- ⬜ `ai-eng-from-scratch-phase6-part2-tts-audio-models-zh.md`

### Phase 7 — Transformers Deep Dive
- ⬜ `ai-eng-from-scratch-phase7-part1-transformer-architecture-zh.md`
- ⬜ `ai-eng-from-scratch-phase7-part2-training-variants-zh.md`

### Phase 8 — Generative AI
- ⬜ `ai-eng-from-scratch-phase8-part1-diffusion-models-zh.md`
- ⬜ `ai-eng-from-scratch-phase8-part2-gan-video-generation-zh.md`

### Phase 9 — Reinforcement Learning
- ⬜ `ai-eng-from-scratch-phase9-part1-rl-fundamentals-zh.md`

### Phase 10 — LLMs from Scratch
- ⬜ `ai-eng-from-scratch-phase10-part1-tokenization-zh.md`
- ⬜ `ai-eng-from-scratch-phase10-part2-pretraining-zh.md`
- ⬜ `ai-eng-from-scratch-phase10-part3-finetuning-zh.md`

### Phase 11 — LLM Engineering
- ⬜ `ai-eng-from-scratch-phase11-part1-inference-serving-zh.md`
- ⬜ `ai-eng-from-scratch-phase11-part2-rag-evals-zh.md`

### Phase 12 — Multimodal AI
- ⬜ `ai-eng-from-scratch-phase12-part1-vit-fusion-zh.md`
- ⬜ `ai-eng-from-scratch-phase12-part2-agents-computer-use-zh.md`

### Phase 13 — Tools & Protocols
- ⬜ `ai-eng-from-scratch-phase13-part1-mcp-apis-zh.md`
- ⬜ `ai-eng-from-scratch-phase13-part2-orchestration-zh.md`

### Phase 14 — Agent Engineering
- ⬜ `ai-eng-from-scratch-phase14-part1-loop-memory-zh.md`
- ⬜ `ai-eng-from-scratch-phase14-part2-planning-zh.md`
- ⬜ `ai-eng-from-scratch-phase14-part3-frameworks-zh.md`
- ⬜ `ai-eng-from-scratch-phase14-part4-production-zh.md`

### Phase 15 — Autonomous Systems
- ⬜ `ai-eng-from-scratch-phase15-part1-long-horizon-zh.md`
- ⬜ `ai-eng-from-scratch-phase15-part2-self-improvement-safety-zh.md`

### Phase 16 — Multi-Agent & Swarms
- ⬜ `ai-eng-from-scratch-phase16-part1-coordination-zh.md`
- ⬜ `ai-eng-from-scratch-phase16-part2-emergence-collective-zh.md`

### Phase 17 — Infrastructure & Production
- ⬜ `ai-eng-from-scratch-phase17-part1-serving-zh.md`
- ⬜ `ai-eng-from-scratch-phase17-part2-observability-zh.md`
- ⬜ `ai-eng-from-scratch-phase17-part3-cost-scale-zh.md`

### Phase 18 — Ethics, Safety & Alignment
- ⬜ `ai-eng-from-scratch-phase18-part1-technical-safety-zh.md`
- ⬜ `ai-eng-from-scratch-phase18-part2-governance-zh.md`

### Phase 19 — Capstone Projects
- ⬜ `ai-eng-from-scratch-phase19-part1-capstone-rag-system-zh.md`
- ⬜ `ai-eng-from-scratch-phase19-part2-capstone-agent-product-zh.md`
- ⬜ `ai-eng-from-scratch-phase19-part3-capstone-multimodal-app-zh.md`
