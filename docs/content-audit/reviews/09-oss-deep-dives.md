## OSS source-code deep dives: mem0, vllm, ragflow, openworker, qm-multiplayer-agent, auto-agent-system — 30 posts

### Series-level observations
- **Two tiers of quality.** Mem0, vLLM, RAGFlow, OpenWorker and QM are strong. They quote real function names and file paths, teach mechanisms instead of restating docs, and each later intro opens with a one-paragraph hand-off from the previous part ("[Part 2] 的結論留下一個很重的包袱…", "[Part 3] 把資料放進了索引。本篇是反向操作…"). I found **no part-1 overview repeated in a later intro** in any of these five series. Auto Agent System is a lighter project retrospective organised by PR, with little code (see below).
- **Phase-box headings confirmed broken in mem0 and vLLM.** Every phase in mem0 parts 1–4 and vLLM parts 1–5 is three separate `###` lines, e.g. mem0-part1 L364–366: `### ╔═══…╗` / `### ║  Phase 1：POC …║` / `### ╚═══…╝`. That makes 9 h3 per post and two duplicate heading texts (Hugo adds `-1`/`-2` anchor suffixes), so the TOC fills with box-drawing garbage. Fix: use one `### Phase 1：POC — …` heading and move the box art into a fenced block below it. mem0 part 5 has no phase section at all. **RAGFlow uses one-line headings** (`### ╔══ Phase 1：POC（單機 / < 1 萬 chunk / 1～5 人） ══╗`, part1 L248). Those render as real headings but leave `╔══`/`══╗` glyphs in the TOC. Stripping them is cosmetic, not urgent.
- **Version pinning is uneven.** Only OpenWorker (`commit 01b6f83`) and QM (`commit 0f0e0ad`) give a SHA, and they give it in every part. Mem0 gives "main, 2026-09, 2.0.20" and vLLM "0.19.x", with no SHA. RAGFlow gives "v0.27.1" in **part 1 only**. Parts 2–5 say "`main` 分支（2026 年 9 月）" with no version, although they quote exact weights, thresholds and file sizes (`search.py` 45 KB, `__init__.py` 68 KB), which change between releases. Auto Agent System has no pin at all. PR numbers partly substitute, but they do not pin the code the prose describes. Standardise on "version + short SHA" in every part's footer.
- **Inconsistent series conventions across the batch.** There are four title formats: "X Intro Part N — A — B", "X 深度解析（一）：", "Auto Agent System - Part 1 -", and the English "Intro Part" prefix inside zh posts. Link styles also differ. vLLM and RAGFlow nav links use relative `../slug` with no trailing slash (26 occurrences). The `render-link.html` hook passes these through untouched, so they skip the `site.GetPage` resolution and the dead-target warning that CLAUDE.md relies on. Switch them to `/posts/<slug>/`. Only OpenWorker/QM carry a shared series tag (`開源專案解析`). Add it to mem0/vLLM/RAGFlow and drop the noise tags `AI` and `繁體中文`.
- **Series nav is not at the bottom in OpenWorker/QM.** Parts 2–4 put "本篇可以帶走的 N 個模式" *after* `十、系列導航`, and parts 1 and 5 put `參考資料` after it. Move the takeaway above the nav. That also brings openworker-part3 (十一), openworker-part5 (十二) and qm parts back under the 十 cap if you want batch-wide consistency. These series are not bound by the fde standard, so the cap is advisory.
- **Auto Agent System uses ASCII punctuation throughout.** Across all five posts I count 43–64 ASCII commas per post and **zero** full-width `，`. Colons and parentheses are ASCII too (`系統總覽:一個…`, `(本篇)`). Next to the rest of the blog this reads as unfinished typography. A mechanical `,`→`，` / `:`→`：` / `()`→`（）` pass outside code blocks fixes it.
- **Trust notes worth a sweep.** Unsourced star counts ("約 6.5 萬顆星", "9.1 萬", "9.0 萬") will go stale quickly. Either date them ("2026-09 時") or drop them. A few specific names should be checked against the pinned version (listed per post).

### Per-post

#### `auto-agent-system-part1-overview-zh.md`
**Verdict:** light edit
- The series nav (L320–326) is **plain text with no links** to parts 2–5. This is true in all five parts, so readers cannot move through the series. Add `/posts/<slug>/` links.
- Add a pin, "本文基於 `agent_auto_system` commit `<sha>`（2026-07）", near the top. The PR numbers in parts 2–5 help but do not pin the code.
- The examples use `gpt-4o` (L62, L229) in a July-2026 post. Swap in a current model id, or say it is an illustrative alias.
- Otherwise it is a good overview: the 11-task table and the Harness framing set up the series well.

#### `auto-agent-system-part2-harness-engine-zh.md`
**Verdict:** light edit
- This is the strongest post of the five. The transient-vs-hard-error retry split and the same-provider sibling fallback (L156) are real lessons. But there are only 2 Python blocks. Show the actual `fallback_sequence` and the Validator→self-correct loop (~20 lines each) instead of only ASCII timelines like L132–134.
- The "十次有八次…第 50 次就爆" (L52) rate is anecdotal. Label it as such, or give observed numbers from your own runs.
- `gpt-4o`/`gpt-4o-mini` throughout: same staleness note as part 1.

#### `auto-agent-system-part3-automations-zh.md`
**Verdict:** light edit
- **Add a compliance paragraph.** `email_collect` scrapes business emails from Google Maps results, probes SMTP, and feeds `email_sender`. `tasker_apply` auto-submits AI-written bids on tasker.com.tw. The Playwright table (L202–209) sells "最不易被擋" and "降低被風控的機率" as benefits. At least mention platform ToS, 個資法/anti-spam rules, and rate limits, or the post reads as an evasion how-to.
- There is no code in this post (0 language-tagged blocks). The PR-by-PR "三次進化" narrative is good. Add one real snippet: the Shopee pagination fix (PR #5) or the "real submit" verification (PR #18).
- `### PR #7 → #8` and the other PR-numbered h3 headings mean nothing to someone who has not read the repo. Lead with the lesson and put the PR number in the body.

#### `auto-agent-system-part4-production-zh.md`
**Verdict:** light edit
- The title promises "AWS 部署", but §三 covers a **docs-only design PR** ("PR #10: docs: add AWS ECS Fargate deployment design (phase 1)"). The before/after table at L241+ says only "ECS Fargate 設計". Retitle it (e.g. "AWS 部署設計"), or state plainly in the intro that nothing is deployed yet.
- The Docker row "塞整顆 Chromium,幾百 MB → WeasyPrint,~450 MB" has no real before number. Give both image sizes, or the win cannot be judged.
- At 278 lines with no code, this is the thinnest part. Consider merging it with part 5 (see the top-5 list).

#### `auto-agent-system-part5-frontend-pipeline-zh.md`
**Verdict:** light edit
- The three SSE decisions (poll DB vs pub/sub, 0.5 s interval, atomic `json_insert`) are the real value. Show the ~15-line SSE generator and the `json_insert` UPDATE rather than describing them.
- §四 (landing page + "Waymo 電影感" theme PRs) is changelog, not engineering. Cut it to two sentences, or explain one concrete design decision. The brand name in a heading also adds nothing.
- The §六 recap works as a series close. Keep it.
- **On "thin?" for the whole series:** yes, relative to the other five series. At 250–340 lines each, with 0–2 real code blocks and no version pin, most "code-ratio" is ASCII boxes. It is honest as a PR retrospective of the author's own repo, but it would read better as **3 parts**: overview+harness, automations, production+frontend. Each merged part should have real snippets and a commit pin.

#### `mem0-intro-part1-architecture-overview-zh.md`
**Verdict:** light edit
- Fix the triple-`###` phase boxes (L364–366 and the two following phases).
- Excellent opening: the `messages.append()` failure analysis and "事實三：v3 之後，OSS 版本沒有圖資料庫了" (L169) are exactly what a reader cannot get from the README.
- Date or drop "約 6.5 萬顆星、7.6 千 fork".

#### `mem0-intro-part2-add-extraction-pipeline-zh.md`
**Verdict:** light edit
- Fix the phase-box headings. Otherwise publishable.
- The "那次自我否定" narrative (v2 four-action → v3 ADD-only, with reasons why DELETE/UPDATE failed) is the best-argued section in the batch.

#### `mem0-intro-part3-hybrid-retrieval-zh.md`
**Verdict:** light edit
- Fix the phase-box headings. The `PX-xxx` placeholder flag (L68) is a false positive; it is a deliberate example.
- §七 (中文與多語言退化) is high-value for this blog's audience. Consider promoting it into the description.

#### `mem0-intro-part4-storage-backends-zh.md`
**Verdict:** light edit
- Fix the phase-box headings.
- The "25 providers, 10 lack `keyword_search`, BM25 silently zeroes" finding (L165–191) is the kind of source-reading payoff this series exists for. Name the exact file and function where `None` disables the signal, so readers can check it after upgrades.
- The `xxx.cloud.qdrant.io` placeholder (L247) is fine; it is a config example.

#### `mem0-intro-part5-production-oss-vs-platform-zh.md`
**Verdict:** light edit
- This is the only mem0 part without 三個演進階段. A short OSS→self-hosted server→Platform phase progression would fit §三 naturally.
- Trim categories to three (drop `architecture` or `infrastructure`).
- Platform-only features (Dream, Memory Decay, Temporal) come from vendor docs, not source. The footer says so. Also say it in-line in §二, since it is the one part where "read the source" does not apply.

#### `openworker-intro-part1-architecture-overview-zh.md`
**Verdict:** keep as is
- Clean map-building post with a commit pin. The only fix is structural: `參考資料` sits after `十、系列導航`. Move the nav to the very end.

#### `openworker-intro-part2-turnengine-deep-dive-zh.md`
**Verdict:** light edit
- Move "本篇可以帶走的五個模式" above `十、系列導航`.
- The "1192 行 vs 40 行教科書版" framing and the "不留孤兒 tool_call" invariant are excellent. No content changes needed.

#### `openworker-intro-part3-harness-permissions-inbox-zh.md`
**Verdict:** light edit
- Move the takeaways above the nav. This post also runs to 十一; folding §九「其他四道防線」 into §八 would bring it to 十.
- The `169.254.169.254` SSRF hook and the prefix-match allowlist trap (§四) are strong practitioner content.

#### `openworker-intro-part4-llm-provider-compaction-zh.md`
**Verdict:** light edit
- Model ids (`GPT-5.6`, `gpt-5.6-sol`, `claude-fable-5`, L17/L164/L269) are quoted from `matrix.py` at the pinned commit, and the footer disclaims them, which is good. The opening quote states "GPT-5.6 在 Chat Completions 上不准 tools 搭配 reasoning" as current fact. Hedge it ("在該 commit 的處理邏輯中").
- Move the takeaways above the nav.

#### `openworker-intro-part5-tools-skills-mcp-automation-zh.md`
**Verdict:** light edit
- It has twelve sections, with both a series summary (十一) and nav (十二) plus references. Merge 十一 into the nav section, or cut §八 (`explore` 子代理) into §二, to get back to 十.
- The `todo` placeholder flags are false positives (a tool named `todo`).

#### `qm-multiplayer-agent-part1-architecture-zh.md`
**Verdict:** light edit
- The opening quote is 11 lines. Tighten it to the 4-line contrast the other posts use.
- In the X-vs-Y table (L363), "159 個工具 schema 吃 context" is OpenWorker's number, not QM's. It is set up at L209, but the table row reads as a QM fact out of context. Write "OpenWorker 式的 159 個…".
- The CONTRIBUTING/AGENTS.md section (§七) is a genuinely distinctive angle. Keep it. The TODO/FIXME flags are false positives (quoted policy text).

#### `qm-multiplayer-agent-part2-scope-resolution-zh.md`
**Verdict:** light edit
- Move "本篇可以帶走的六個模式" above the nav. Content is excellent: the audience-floor "模型自己把資料唸出來" framing is the clearest explanation of LLM data leakage in the batch.

#### `qm-multiplayer-agent-part3-harness-abstraction-zh.md`
**Verdict:** light edit
- Same nav-ordering fix. "`HarnessTurnInput`：60 個欄位" could show the ~10 fields that matter instead of implying all 60 are important.

#### `qm-multiplayer-agent-part4-security-model-zh.md`
**Verdict:** light edit
- Same nav-ordering fix. The "12 條已知限制" section is valuable. It would be stronger with a column on which limitation a given deployment posture actually mitigates.

#### `qm-multiplayer-agent-part5-sandbox-skills-cron-zh.md`
**Verdict:** light edit
- Part 1 quotes the repo's zero-comment policy, yet the quoted code here carries `// ★ …` annotations (e.g. `notInstalled?: string[];    // ★ 「沒裝什麼」也是規格的一部分`). Add one line saying ★ comments are the author's, so readers do not think the quote is inaccurate.
- `參考資料` comes after the nav. Otherwise a strong series close.

#### `ragflow-intro-part1-overview-architecture-zh.md`
**Verdict:** light edit
- Nav links use `../ragflow-intro-part2-…` (relative, no trailing slash). Switch to `/posts/<slug>/`.
- Verify "Python ≥ 3.13" and `uv sync --python 3.13` (L485, L532) against v0.27.1's `pyproject.toml`. Earlier RAGFlow releases capped Python below 3.13.
- Otherwise it is an exemplary overview. The "三個「不一樣」的選擇" section earns its place.

#### `ragflow-intro-part2-deepdoc-chunking-zh.md`
**Verdict:** light edit
- The footer has no version. Add "v0.27.1 / commit <sha>", since the post quotes file sizes and the template count (14).
- Relative nav links, as in part 1.

#### `ragflow-intro-part3-embedding-indexing-zh.md`
**Verdict:** light edit
- Same version-pin and link fixes. The "0.1 檔名 + 0.9 內容" and `min(freq,1)` sections are strong. The `Infinity v0.7.3` reference (L400) should share the same pin date.

#### `ragflow-intro-part4-retrieval-rerank-zh.md`
**Verdict:** light edit
- Same version-pin and link fixes. At 879 lines it is the densest post. §五「五個可選機制」 (GraphRAG/RAPTOR, etc.) could lose the prose that repeats the tables.

#### `ragflow-intro-part5-system-code-structure-zh.md`
**Verdict:** light edit
- Same pin fix. The Go-migration section (§七) changes fastest, so it most needs a SHA.
- The final "series summary" table mapping each design choice to its part is a great close. Add real `/posts/` links on the "Part N" cells.

#### `vllm-intro-part1-architecture-overview-zh.md`
**Verdict:** light edit
- Fix the triple-`###` phase headings.
- Verify the `vllm/config.py` path in the part table (L30). Recent vLLM split config into a `vllm/config/` package.
- Switch the relative `../` nav links to `/posts/…/`.

#### `vllm-intro-part2-paged-attention-kv-cache-zh.md`
**Verdict:** light edit
- Fix the phase headings and the relative links. Content is excellent. The "它是 GPU 上的 malloc 問題" opening is the best hook in the batch.

#### `vllm-intro-part3-scheduler-continuous-batching-zh.md`
**Verdict:** light edit
- Fix the phase headings and the links. §八 (symptom → diagnosis → prescription table) is exactly what CLAUDE.md asks for.
- Verify `VLLM_USE_FASTOKENS=1` (L505). I cannot confirm this env var exists. If wrong, it is a copy-paste trap.

#### `vllm-intro-part4-distributed-quantization-zh.md`
**Verdict:** light edit
- **Wrong cross-reference:** the intro (L27) says "還有 Part 3 講的那些 all-reduce 通訊", but part 3 never mentions all-reduce (0 hits). It is introduced here in part 4. Change it to "下面 §三 會講的".
- "沒有 NVLink 的機器上這件事會吃掉你 40% 的時間" (opening quote) needs a source or a "量級" hedge.
- Fix the phase headings and the links.

#### `vllm-intro-part5-production-serving-zh.md`
**Verdict:** light edit
- The intro says "前四篇拆完了引擎" but links only three (memory, scheduling, parallelism). Add Part 1.
- Trim categories to three. Fix the phase headings and the relative links. The `sk-xxx` placeholder flag is a false positive.

### Top 5 highest-impact fixes in this batch
1. **Collapse the triple-`###` ╔║╚ phase headings into one `### Phase N：…` heading plus a fenced box**, in all 9 affected mem0 (parts 1–4) and vLLM (parts 1–5) posts. It is one regex pass and removes about 80 garbage TOC entries.
2. **Make Auto Agent System navigable and pinned.** Add real `/posts/` links to the plain-text series nav in all 5 parts and a commit SHA in each. Then either add 1–2 real code snippets per part or merge the five into three.
3. **Standardise version pins to "version + short SHA" in every part's footer.** RAGFlow parts 2–5 have none; mem0 and vLLM have a version but no SHA.
4. **Replace relative `../slug` nav links in vLLM and RAGFlow (26 occurrences) with `/posts/<slug>/`**, so they go through the render hook and the dead-link check. In OpenWorker/QM, move takeaway and 參考資料 sections above `系列導航`.
5. **Fix the factual and compliance slips:** vLLM part 4's false "Part 3 講的 all-reduce" reference, vLLM part 5's missing Part 1 link, the unverified `VLLM_USE_FASTOKENS` and RAGFlow "Python ≥ 3.13" claims, and a ToS/個資法/anti-spam paragraph for Auto Agent System part 3's email-scraping and auto-bidding jobs.
