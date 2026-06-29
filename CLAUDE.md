# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Local development with draft posts visible
hugo server --buildDrafts

# Production-like preview (drafts hidden)
hugo server

# Production build
hugo --minify

# Build with explicit base URL
hugo --minify --baseURL https://yennanliu.github.io/yennj12_blog_V4/

# Create a new post from archetype
hugo new content/posts/your-post-title.md
```

Requires Hugo Extended v0.118.0+. There is no Node/npm or test suite.

## Architecture

This is a **Hugo static site** using a custom theme called `uber-style` (in `themes/uber-style/`). Content is written in Markdown and the site is deployed to GitHub Pages via Actions.

### Key directories

- `content/posts/` — Blog articles (Markdown). Filenames ending in `-zh` are Traditional Chinese posts.
- `content/authors/<slug>/_index.md` — Author profiles. The slug must match the `authors:` field in post front matter.
- `content/about/`, `content/categories/`, `content/tags/` — Static and taxonomy pages.
- `themes/uber-style/` — Custom theme. Layouts live in `layouts/`, styles in `assets/scss/`.
- `themes/uber-style/assets/scss/_variables.scss` — Design tokens (colors, typography, spacing).
- `static/` — Unprocessed assets (favicon, author avatars at `static/images/authors/`).
- `scripts/generate_nvidia_blog.py` — Python script that fetches NVIDIA Developer Blog via RSS, translates to Traditional Chinese using GPT-4, and writes a new post. Requires `OPENAI_API_KEY` and `feedparser`/`requests` packages.
- `.github/workflows/` — Three Hugo build/deploy workflows (`hugo-latest.yml` is the recommended one).

### Post front matter

Every post must include these fields:

```yaml
---
title: "Post Title"
date: 2026-01-01T09:00:00+08:00
draft: false
description: "Used for SEO and post cards"
categories: ["engineering"]   # maps to /categories/ URLs; include "all" for full listing
tags: ["tag1", "tag2"]
authors: ["yen"]              # must match a slug under content/authors/
readTime: "10 min"
---
```

### Theme layout flow

`baseof.html` → `single.html` / `list.html` / `posts-list.html`. Partials in `themes/uber-style/layouts/partials/` are: `head.html`, `header.html`, `footer.html`, `scripts.html`, `share.html`.

### Deployment

Pushing to `main` triggers `.github/workflows/hugo-latest.yml`, which builds with Hugo Extended 0.121.1 and deploys to GitHub Pages. The live site is at `https://yennj12.js.org/yennj12_blog_V4`. The `baseURL` in `hugo.toml` must match the deployment URL or relative links will break.

### Content naming convention

Chinese-language posts use the suffix `-zh.md`. Posts that are part of a series use a numbered suffix (e.g., `-part1-`, `-part2-`).

---

## fde-interview-guide post generation standards

When generating new `fde-interview-guide-part{N}-xxx-zh.md` posts, apply the following enhanced style. These rules override the generic post guidelines above.

### 1. Architecture diagrams

Include **2–4 ASCII block diagrams** per post. Each major concept gets its own diagram; flow diagrams show data moving through the system. Use box-drawing characters consistently:

```
┌─────────────────┐       ┌─────────────────┐
│  Component A    │──────▶│  Component B    │
└────────┬────────┘       └────────┬────────┘
         │                         │
         ▼                         ▼
┌─────────────────────────────────────────────┐
│  Shared Layer                               │
└─────────────────────────────────────────────┘
```

### 2. Phase-based architecture discussion

Every post must have a **「三個演進階段」section** that presents the central architecture in three evolutionary phases using `╔══╗` headers:

- **Phase 1（POC / < 10K 用戶）**: minimal viable, acceptable shortcuts, fast to build
- **Phase 2（MVP / 10K–200K）**: production-safe, team can operate without constant firefighting
- **Phase 3（Scale / 200K–1M+）**: enterprise-grade, auto-scaling, cost-optimised

For each phase show: ASCII architecture diagram, new components added vs previous phase, cost/complexity delta, what problems are solved and what problems remain.

### 3. Why X not Y

For every non-obvious design decision, include an explicit **「為什麼選 X 不選 Y」comparison table**. Cover at least 4–6 decisions per post. Standard format:

```
選擇        選 X 的理由                   不選 Y 的理由
──────────────────────────────────────────────────────
Redis       < 1ms 延遲，原生 TTL 支援      DB：連接開銷大，無原生 TTL
vs DB       Cluster 模式高可用             Memcached：無持久化，資料結構少
```

Always include the "flip condition": when does Y become the right choice instead?

### 4. Content depth and completeness

- **Concrete numbers throughout**: latency in ms, cost in $, error rates in %, scale in QPS/MAU/users
- **Annotate every tradeoff**: state explicitly when a design decision changes (e.g., "below 100 QPS, X is fine; above that, Y is necessary")
- **Code snippets**: only for non-obvious implementations; never boilerplate
- **Symptom-to-diagnosis chains**: show what signal you'd see in Traces/Metrics/Logs, not just theory
- **Minimum 600 lines per post; target 700–900**
- Section numbering: use 一, 二, 三 … 十, 十一 (Chinese numerals); do not exceed 12 sections

### 5. Standard section order

1. 一、核心問題/為什麼（establish the tension)
2. 二、三個演進階段（phase-based architecture with diagrams)
3. 三–七、Deep dives on each major design area
4. 八 or 九、為什麼選 X 不選 Y（consolidated decision table)
5. 十、系統效應（before/after comparison table with numbers)
6. 十一、面試答題要點（model RKK answer in blockquote)
7. Series navigation links

### 6. Style rules

- **No mention of "Google"** anywhere in the generated content or tags. **This rule applies ONLY to interview-related posts** (`fde-interview-guide-*` and other interview-prep series). Non-interview posts (general tech tutorials, stock analysis, etc.) may freely mention Google and its products.
- Tags: use `"Cloud"` instead of `"Google"`; always include `"RKK"` and `"Interview"`
- readTime: set based on line count — 500 lines ≈ 18 min, 700 lines ≈ 23 min, 900 lines ≈ 28 min
- Opening quote: 4-line contrast (what most people do vs what the right answer is)
- 面試情境: a single interviewer question that is specific, scenario-based, and requires architecture judgment
- 面試答題要點: a model answer in `> *「...」*` blockquote format, 4–6 sentences, hits the phase structure + key Why-X-not-Y decisions + a concrete number
