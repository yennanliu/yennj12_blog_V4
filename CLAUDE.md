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
