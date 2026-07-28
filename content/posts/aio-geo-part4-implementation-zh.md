---
title: "AIO / GEO - Part 4 - 實作篇：把一個網站改造成 AI 可引用"
date: 2026-07-31T09:00:00+08:00
draft: false
weight: 4
description: "八個步驟的完整實作：AI crawler 存取層與 CDN 白名單、llms.txt 產生器、JSON-LD 自動注入、chunk 邊界工程、Markdown 雙軌輸出、SSR 決策樹，附 Hugo / Next.js 可直接複製的程式碼與可放進 CI 的自動化驗收腳本。"
categories: ["AI", "SEO", "GEO", "Engineering", "all"]
tags: ["GEO", "AIO", "Hugo", "Next.js", "llms.txt", "JSON-LD", "SSR", "CI", "繁體中文"]
authors: ["yen"]
readTime: "29 min"
---

> 大多數人的做法：讀完方法論，開一份 Notion 待辦，然後三個月後還在第一項。
> 真正該做的事：照著步驟做，每一步都有可執行的驗收指令。
>
> 這一篇不談概念。
> 全部是可以複製貼上的東西。

---

## 一、實作目標與驗收標準

我們要把一個典型網站從 Level 0/1 推到 Level 2（Part 1 §9 的成熟度模型）。

```
                改造前                        改造後
──────────────────────────────────────────────────────────────
AI crawler      部分 403 / 內容不完整          8 個 bot 全 200，內容完整
無 JS 內容量     瀏覽器的 20%（CSR）           瀏覽器的 98%
結構化資料       無 / 只有基本 Article         Organization + Article +
                                             FAQPage + Breadcrumb，互相 @id 引用
chunk 邊界      靠段落換行                     H2/H3 分節 + section id + 錨點
機器可讀版本     只有 HTML                      HTML + .md + llms.txt
可驗收           靠人工檢查                     CI 自動化，PR 階段擋下退步
```

**驗收腳本會在 §9 給出**，可以直接放進 CI。建議先跳到 §9 跑一次，拿到基線，再回來逐步修。

---

## 二、Step 1：AI Crawler 存取層

這是唯一「0/1」的一步。做不完，後面七步全部無效。

### 2.1 robots.txt

```
# https://example.com/robots.txt

# ── 一般搜尋引擎（AI Overview 的前提）──────────────
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

# ── AI 檢索 bot：一律開放 ──────────────────────────
# 這些 bot 決定你在「今天」的 AI 回答中存不存在
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Perplexity-User
Allow: /

User-agent: Applebot
Allow: /

# ── AI 訓練 bot：依商業立場決定 ─────────────────────
# 開放 = 有機會進入未來模型的內在知識
# 封鎖 = 保護內容資產，但放棄長期 LLMO
User-agent: GPTBot
Allow: /
Disallow: /pricing/quote/
Disallow: /customer-portal/

User-agent: ClaudeBot
Allow: /
Disallow: /pricing/quote/
Disallow: /customer-portal/

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

# 公開資料集：多數公司選擇封鎖（無法控制下游用途）
User-agent: CCBot
Disallow: /

# ── 全域預設 ────────────────────────────────────
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /*?utm_
Disallow: /search?

Sitemap: https://example.com/sitemap.xml
```

### 2.2 CDN / WAF：真正的兇手

`robots.txt` 是禮貌性協議，CDN 才是實際的閘門。**超過一半的「AI 看不到我」案例出在這裡**。

**Cloudflare**

```
1. Security → Bots → 確認「Block AI Scrapers and Crawlers」為 OFF
   （若因版權考量要開，改用下方的 WAF 規則做精細控制）

2. Security → WAF → Custom rules，新增一條 Skip 規則置頂：

   規則名稱：Allow AI retrieval bots
   運算式：
     (http.user_agent contains "OAI-SearchBot") or
     (http.user_agent contains "ChatGPT-User") or
     (http.user_agent contains "Claude-SearchBot") or
     (http.user_agent contains "Claude-Web") or
     (http.user_agent contains "PerplexityBot") or
     (http.user_agent contains "Applebot")
   動作：Skip → 勾選 All remaining custom rules、Rate limiting、
                 Bot Fight Mode、Managed rules

3. Security → Settings → Security Level 若為 High，
   對 /blog/* 等內容路徑降為 Medium
```

**注意 rate limiting**：AI crawler 的抓取速度通常遠高於一般爬蟲（Perplexity 尤其明顯）。常見的「每 IP 每分鐘 60 次」設定會直接讓它們吃到 429。針對這些 UA 放寬到 300/min 是合理的。

**AWS CloudFront + WAF**

```json
{
  "Name": "AllowAIRetrievalBots",
  "Priority": 0,
  "Action": { "Allow": {} },
  "Statement": {
    "ByteMatchStatement": {
      "SearchString": "SearchBot",
      "FieldToMatch": { "SingleHeader": { "Name": "user-agent" } },
      "TextTransformations": [{ "Priority": 0, "Type": "NONE" }],
      "PositionalConstraint": "CONTAINS"
    }
  },
  "VisibilityConfig": {
    "SampledRequestsEnabled": true,
    "CloudWatchMetricsEnabled": true,
    "MetricName": "AllowAIRetrievalBots"
  }
}
```

**Nginx（自架）**

```nginx
# 定義 AI bot
map $http_user_agent $is_ai_bot {
    default                 0;
    "~*OAI-SearchBot"       1;
    "~*ChatGPT-User"        1;
    "~*GPTBot"              1;
    "~*ClaudeBot"           1;
    "~*Claude-SearchBot"    1;
    "~*Claude-Web"          1;
    "~*PerplexityBot"       1;
    "~*Applebot"            1;
    "~*Googlebot"           1;
    "~*bingbot"             1;
}

# 給 AI bot 較寬鬆的 rate limit
limit_req_zone $binary_remote_addr zone=general:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=aibots:10m  rate=300r/m;

server {
    location / {
        # 不要對 AI bot 做 JS challenge / cookie 檢查
        if ($is_ai_bot) {
            set $skip_challenge 1;
        }
        limit_req zone=general burst=20 nodelay;
        # …
    }

    # 記錄 AI bot 存取，供 Part 5 的流量分析使用
    access_log /var/log/nginx/ai-bots.log combined if=$is_ai_bot;
}
```

### 2.3 分區策略：不是全開就是全關

對付費內容站 / 媒體，正確做法是分層。

```
路徑                    檢索 bot    訓練 bot    理由
──────────────────────────────────────────────────────────
/                       ✔          ✔          首頁與品牌頁全開
/blog/*                 ✔          ✔          內容行銷，被引用是目的
/docs/*                 ✔          ✔          文件被引用等於免費支援
/pricing                ✔          ✔          交易意圖，一定要被看到
/research/*（付費）      摘要層      ✘          給前 30%，標註 paywall
/members/*              ✘          ✘          會員專屬
/api/*, /admin/*        ✘          ✘          非內容
```

付費內容的誠實標註方式（比偽裝安全得多）：

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "2026 台灣電商產業深度報告",
  "isAccessibleForFree": false,
  "hasPart": {
    "@type": "WebPageElement",
    "isAccessibleForFree": false,
    "cssSelector": ".paywalled-content"
  }
}
</script>

<article>
  <div class="free-preview">
    <!-- 前 30%：完整、可引用、有數據 -->
  </div>
  <div class="paywalled-content">
    <!-- 剩下 70% -->
  </div>
</article>
```

### 2.4 驗收

```bash
./ai-crawler-check.sh https://example.com/blog/your-best-post/
# 期望：所有列 200，bytes 差異 < 5%
```

---

## 三、Step 2：SSR / 預渲染決策

```
                你的網站是什麼？
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
   靜態內容為主                     大量動態 / 個人化
   (部落格、文件、行銷站)            (SaaS 儀表板、電商後台)
        │                               │
        ▼                               ▼
   ┌─────────┐              ┌───────────────────────┐
   │  SSG    │              │  這些頁本來就不該被引用  │
   │ Hugo /  │              │  但你的「公開內容區」    │
   │ Astro / │              │  必須獨立出來做 SSG/SSR │
   │ Next.js │              └───────────────────────┘
   │ (SSG)   │
   └─────────┘
        │
   已經是 CSR SPA？三個選項：
   ┌────────────────────────────────────────────────────┐
   │ A. 遷移到 Next.js/Nuxt 的 SSR/SSG    最佳，成本最高  │
   │ B. 對內容路由做建置期預渲染           折衷，推薦      │
   │    (react-snap / prerender build)                  │
   │ C. 邊緣預渲染服務（Prerender.io 等）  最快，但是      │
   │    給 bot 不同來源 → 需嚴格保持一致，有 cloaking 風險 │
   └────────────────────────────────────────────────────┘
```

**強烈建議 A 或 B**。選項 C 雖然一天就能上線，但你等於維護兩套內容，長期一定會不同步。

Next.js App Router 的最小正確設定：

```tsx
// app/blog/[slug]/page.tsx
import { notFound } from 'next/navigation'
import { getPost, getAllSlugs } from '@/lib/posts'

// 建置期產生所有路徑 → 純靜態 HTML，AI crawler 100% 拿得到
export async function generateStaticParams() {
  const slugs = await getAllSlugs()
  return slugs.map((slug) => ({ slug }))
}

// 每 1 小時重新驗證，兼顧新鮮度與靜態化
export const revalidate = 3600
export const dynamic = 'force-static'

export async function generateMetadata({ params }) {
  const post = await getPost(params.slug)
  if (!post) return {}
  return {
    title: post.title,
    description: post.description,
    alternates: {
      canonical: `https://example.com/blog/${params.slug}`,
      types: { 'text/markdown': `https://example.com/blog/${params.slug}.md` },
    },
    openGraph: {
      type: 'article',
      publishedTime: post.datePublished,
      modifiedTime: post.dateModified,
      authors: [post.author.url],
    },
  }
}

export default async function Page({ params }) {
  const post = await getPost(params.slug)
  if (!post) notFound()
  // 內容一律在伺服器端渲染成 HTML，不靠 client component
  return <ArticleLayout post={post} />
}
```

**檢查點**：任何包裹主要內容的 `'use client'` 元件都是紅旗。互動性放在葉節點（按鈕、表單），內容放在伺服器元件。

---

## 四、Step 3：JSON-LD 自動注入

手寫 JSON-LD 一定會漏。做成模板。

### 4.1 Hugo 實作

建立 `layouts/partials/schema.html`：

```go-html-template
{{/* ---------- Organization（全站，只在首頁輸出完整版）---------- */}}
{{ if .IsHome }}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "{{ .Site.BaseURL }}#organization",
  "name": {{ .Site.Params.orgName | jsonify }},
  "alternateName": {{ .Site.Params.orgAltNames | jsonify }},
  "url": "{{ .Site.BaseURL }}",
  "logo": {
    "@type": "ImageObject",
    "url": "{{ .Site.BaseURL }}images/logo.png",
    "width": 512, "height": 512
  },
  "description": {{ .Site.Params.orgDescription | jsonify }},
  "foundingDate": {{ .Site.Params.foundingDate | jsonify }},
  "sameAs": {{ .Site.Params.sameAs | jsonify }},
  "knowsAbout": {{ .Site.Params.knowsAbout | jsonify }}
}
</script>
{{ end }}

{{/* ---------- Article ---------- */}}
{{ if eq .Type "posts" }}
{{ $author := index .Site.Data.authors (index .Params.authors 0) }}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "@id": "{{ .Permalink }}#article",
  "headline": {{ .Title | jsonify }},
  "description": {{ .Description | jsonify }},
  "datePublished": {{ .Date.Format "2006-01-02T15:04:05-07:00" | jsonify }},
  "dateModified": {{ (default .Date .Lastmod).Format "2006-01-02T15:04:05-07:00" | jsonify }},
  "author": {
    "@type": "Person",
    "@id": "{{ .Site.BaseURL }}authors/{{ index .Params.authors 0 }}/#person",
    "name": {{ $author.name | jsonify }},
    "jobTitle": {{ $author.jobTitle | jsonify }},
    "url": "{{ .Site.BaseURL }}authors/{{ index .Params.authors 0 }}/",
    "sameAs": {{ $author.sameAs | jsonify }},
    "worksFor": { "@id": "{{ .Site.BaseURL }}#organization" }
  },
  "publisher": { "@id": "{{ .Site.BaseURL }}#organization" },
  "mainEntityOfPage": "{{ .Permalink }}",
  "articleSection": {{ (index .Params.categories 0) | jsonify }},
  "keywords": {{ delimit .Params.tags ", " | jsonify }},
  "wordCount": {{ .WordCount }},
  "inLanguage": "{{ .Site.LanguageCode }}"
}
</script>
{{ end }}

{{/* ---------- FAQPage（從 front matter 的 faq 陣列產生）---------- */}}
{{ with .Params.faq }}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{ range $i, $item := . }}{{ if $i }},{{ end }}
    {
      "@type": "Question",
      "name": {{ $item.q | jsonify }},
      "acceptedAnswer": { "@type": "Answer", "text": {{ $item.a | jsonify }} }
    }
    {{ end }}
  ]
}
</script>
{{ end }}

{{/* ---------- BreadcrumbList ---------- */}}
{{ if .Parent }}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{ range $i, $p := .Ancestors.Reverse }}
    { "@type": "ListItem", "position": {{ add $i 1 }},
      "name": {{ $p.Title | jsonify }}, "item": "{{ $p.Permalink }}" },
    {{ end }}
    { "@type": "ListItem", "position": {{ add (len .Ancestors) 1 }},
      "name": {{ .Title | jsonify }}, "item": "{{ .Permalink }}" }
  ]
}
</script>
{{ end }}
```

在 `layouts/partials/head.html` 末尾加上：

```go-html-template
{{ partial "schema.html" . }}
```

搭配的 front matter：

```yaml
---
title: "OMS 導入成本完整拆解：2026 台灣市場實價"
date: 2026-06-14T09:00:00+08:00
lastmod: 2026-07-22T11:30:00+08:00
description: "拆解 OMS 導入的五類成本，附 12 家供應商實際報價區間。"
authors: ["chen-yiting"]
faq:
  - q: "OMS 導入的總成本大約是多少？"
    a: "以 20-50 人的零售企業為例，第一年總成本落在 NT$45 萬到 NT$180 萬之間，中位數約 NT$92 萬。其中軟體授權佔 40-55%、導入服務佔 30-40%、內部人力佔 10-20%。"
  - q: "導入需要多久？"
    a: "標準導入為 6-10 週：需求訪談 2-3 週、系統設定與客製 3-5 週、資料移轉 1-2 週、UAT 與教育訓練 1-2 週。若涉及 ERP 雙向整合，通常再加 4-6 週。"
---
```

**`lastmod` 的紀律**：Hugo 的 `Lastmod` 預設可以取 Git commit time（`enableGitInfo = true`）。這比手動維護可靠，但要小心「只改錯字也算更新」。建議用 front matter 手動控制重要頁面。

### 4.2 Next.js 實作

```tsx
// components/JsonLd.tsx
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      // JSON.stringify 已足以逸出，但額外處理 </script> 邊界情況
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(data).replace(/</g, '\\u003c'),
      }}
    />
  )
}

// lib/schema.ts
const SITE = 'https://example.com'

export const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': `${SITE}/#organization`,
  name: 'OrderFlow',
  alternateName: ['OrderFlow 訂單流'],
  url: SITE,
  description:
    'OrderFlow 是台灣的多通路電商訂單管理系統（OMS），提供跨平台訂單同步、庫存整合與出貨自動化。',
  sameAs: [
    'https://www.linkedin.com/company/orderflow-tw',
    'https://github.com/orderflow',
    'https://www.wikidata.org/wiki/Q123456789',
  ],
  knowsAbout: ['訂單管理系統', '多通路電商', '庫存同步', 'OMS'],
}

export function articleSchema(post: Post) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    '@id': `${SITE}/blog/${post.slug}/#article`,
    headline: post.title,
    description: post.description,
    datePublished: post.datePublished,
    dateModified: post.dateModified ?? post.datePublished,
    author: {
      '@type': 'Person',
      '@id': `${SITE}/authors/${post.author.slug}/#person`,
      name: post.author.name,
      jobTitle: post.author.jobTitle,
      url: `${SITE}/authors/${post.author.slug}/`,
      sameAs: post.author.sameAs,
      worksFor: { '@id': `${SITE}/#organization` },
    },
    publisher: { '@id': `${SITE}/#organization` },
    mainEntityOfPage: `${SITE}/blog/${post.slug}/`,
    wordCount: post.wordCount,
    inLanguage: 'zh-Hant-TW',
  }
}

export function faqSchema(faq: { q: string; a: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faq.map(({ q, a }) => ({
      '@type': 'Question',
      name: q,
      acceptedAnswer: { '@type': 'Answer', text: a },
    })),
  }
}
```

---

## 五、Step 4：Chunk 邊界工程

把 Part 2 §4 的理論變成 HTML 結構。

### 5.1 目標 DOM 形狀

```html
<article itemscope itemtype="https://schema.org/BlogPosting">
  <header>
    <h1>OMS 導入成本完整拆解：2026 台灣市場實價</h1>
    <p class="meta">
      <time datetime="2026-07-22T11:30:00+08:00">更新於 2026 年 7 月 22 日</time>
      ·
      <a rel="author" href="/authors/chen-yiting/">陳怡婷</a>，解決方案架構師
    </p>
  </header>

  <!-- TL;DR：一個完美的獨立 chunk -->
  <aside class="tldr" aria-label="重點摘要">
    <h2>重點摘要</h2>
    <ul>
      <li>20-50 人零售企業導入 OMS 的第一年總成本中位數為 NT$92 萬。</li>
      <li>成本結構：軟體授權 40-55%、導入服務 30-40%、內部人力 10-20%。</li>
      <li>標準導入時程 6-10 週；含 ERP 雙向整合再加 4-6 週。</li>
    </ul>
  </aside>

  <!-- 每個 section = 一個 chunk，有 id、有問句標題、可獨立成立 -->
  <section id="cost-items" aria-labelledby="h-cost-items">
    <h2 id="h-cost-items">OMS 導入成本包含哪五類項目？</h2>
    <p>
      OMS（訂單管理系統）的導入成本可拆為五類：軟體授權費、
      導入服務費、客製開發費、資料移轉費與內部人力成本……
    </p>
    <table>…</table>
    <p class="source">
      資料來源：本文彙整 2026 年 1-6 月 12 家台灣 OMS 供應商的實際報價，
      樣本為 20-50 人規模的零售企業。
    </p>
  </section>

  <section id="timeline" aria-labelledby="h-timeline">
    <h2 id="h-timeline">OMS 導入需要多久時間？</h2>
    <p>OMS 導入的標準時程為 6-10 週……</p>
  </section>

  <section id="faq" aria-labelledby="h-faq">
    <h2 id="h-faq">常見問題</h2>
    <details open>
      <summary>中小企業有沒有更便宜的方案？</summary>
      <p>有。SaaS 訂閱制方案的第一年成本可壓到 NT$12-30 萬……</p>
    </details>
  </section>
</article>
```

四個關鍵設計：

```
設計                        作用
──────────────────────────────────────────────────────────────
<section id="...">          給引擎一個可引用的深層錨點
                            → /page#cost-items 的點擊率高於頁面級引用

<h2> 用完整問句              直接命中 query fan-out 產生的檢索查詢

<details open>              FAQ 預設展開，內容確實在 HTML 中
                            → 若用 JS accordion，內容可能不存在

<p class="source">          每個 section 自帶來源與方法論
                            → grounding 階段的存活關鍵
```

### 5.2 `<details>` 而非 JS accordion

```html
<!-- ❌ 內容由 JS 注入，AI crawler 看不到 -->
<div class="accordion" data-content-url="/api/faq/1">
  <div class="accordion-header">導入需要多久？</div>
</div>

<!-- ⚠ 內容在 HTML 但用 display:none —— 多數引擎仍可讀，但權重可能降低 -->
<div class="accordion">
  <div class="header">導入需要多久？</div>
  <div class="body" style="display:none">標準導入為 6-10 週……</div>
</div>

<!-- ✔ 原生元素，語意明確，內容一定在 HTML 中 -->
<details open>
  <summary>導入需要多久？</summary>
  <p>標準導入為 6-10 週……</p>
</details>
```

### 5.3 Hugo 的 heading anchor 與 section 自動包裹

Hugo 的 `render-heading.html` hook 可以自動加 id：

```go-html-template
{{/* layouts/_default/_markup/render-heading.html */}}
<h{{ .Level }} id="{{ .Anchor }}">
  {{ .Text | safeHTML }}
  <a class="anchor" href="#{{ .Anchor }}" aria-label="連結到此段落">#</a>
</h{{ .Level }}>
```

表格加上 `overflow-x` 容器，避免行動裝置版面破掉（同時不影響機器解析）：

```go-html-template
{{/* layouts/_default/_markup/render-table.html */}}
<div class="table-wrap" style="overflow-x:auto">
  <table>
    <thead>
      {{ range .THead }}<tr>
        {{ range . }}<th style="text-align:{{ .Alignment }}">{{ .Text | safeHTML }}</th>{{ end }}
      </tr>{{ end }}
    </thead>
    <tbody>
      {{ range .TBody }}<tr>
        {{ range . }}<td style="text-align:{{ .Alignment }}">{{ .Text | safeHTML }}</td>{{ end }}
      </tr>{{ end }}
    </tbody>
  </table>
</div>
```

---

## 六、Step 5：llms.txt 與 Markdown 雙軌輸出

### 6.1 定位先講清楚

`llms.txt` 目前**沒有任何主流引擎承諾支援**。做它的理由是：

- 成本 30 分鐘，未來若成標準已就位
- 對自家 RAG、內部 agent、客戶的 AI 工具立即有用
- `.md` 版本的價值明確高於 `llms.txt` 本身

**不要把它當成 GEO 的核心策略。** 它是象限③（順手做）的事。

### 6.2 Hugo 產生 llms.txt

在 `hugo.toml` 加輸出格式：

```toml
[outputFormats.LLMS]
  mediaType = "text/plain"
  baseName = "llms"
  isPlainText = true
  notAlternative = true

[outputFormats.LLMSFULL]
  mediaType = "text/plain"
  baseName = "llms-full"
  isPlainText = true
  notAlternative = true

[outputFormats.MARKDOWN]
  mediaType = "text/markdown"
  suffix = "md"
  isPlainText = true
  notAlternative = true

[outputs]
  home = ["HTML", "RSS", "LLMS", "LLMSFULL"]
  page = ["HTML", "MARKDOWN"]

[mediaTypes."text/markdown"]
  suffixes = ["md"]
```

`layouts/index.llms.txt`：

```go-html-template
# {{ .Site.Title }}

> {{ .Site.Params.orgDescription }}

本檔案為 LLM 友善的網站索引。每個連結後方的 .md 版本為純 Markdown 全文。

## 關於

- [關於我們]({{ .Site.BaseURL }}about/): {{ .Site.Params.orgDescription }}
- [產品]({{ .Site.BaseURL }}product/): 產品功能與定價
{{ with .Site.Params.contactEmail }}- 聯絡：{{ . }}{{ end }}

## 文章
{{ range where (where .Site.RegularPages "Type" "posts") "Params.draft" "!=" true }}
- [{{ .Title }}]({{ .Permalink }}) ([md]({{ .Permalink }}index.md)): {{ .Description }}
{{- end }}

## 分類
{{ range .Site.Taxonomies.categories }}
- {{ .Page.Title }} （{{ len .Pages }} 篇）: {{ .Page.Permalink }}
{{- end }}
```

`layouts/index.llmsfull.txt`（全文串接版）：

```go-html-template
# {{ .Site.Title }} — 全文

> {{ .Site.Params.orgDescription }}
> 產生時間：{{ now.Format "2006-01-02" }}

{{ range where (where .Site.RegularPages "Type" "posts") "Params.draft" "!=" true }}
{{ "\n\n---\n\n" }}
# {{ .Title }}

URL: {{ .Permalink }}
發佈：{{ .Date.Format "2006-01-02" }} ｜ 更新：{{ (default .Date .Lastmod).Format "2006-01-02" }}
作者：{{ delimit .Params.authors ", " }}

{{ .RawContent }}
{{ end }}
```

`layouts/_default/single.md`（每篇的 Markdown 版）：

```go-html-template
# {{ .Title }}

URL: {{ .Permalink }}
發佈：{{ .Date.Format "2006-01-02" }}
更新：{{ (default .Date .Lastmod).Format "2006-01-02" }}
作者：{{ delimit .Params.authors ", " }}
分類：{{ delimit .Params.categories ", " }}

> {{ .Description }}

{{ .RawContent }}
```

然後在 `head.html` 宣告 Markdown 替代版本：

```go-html-template
{{ if eq .Type "posts" }}
<link rel="alternate" type="text/markdown" href="{{ .Permalink }}index.md" title="Markdown 版本">
{{ end }}
```

### 6.3 Next.js 的 .md route

```ts
// app/blog/[slug]/[...md]/route.ts  或直接用 app/blog/[slug].md/route.ts
import { NextResponse } from 'next/server'
import { getPost, getAllSlugs } from '@/lib/posts'

export async function generateStaticParams() {
  return (await getAllSlugs()).map((slug) => ({ slug }))
}

export async function GET(_req: Request, { params }: { params: { slug: string } }) {
  const post = await getPost(params.slug)
  if (!post) return new NextResponse('Not found', { status: 404 })

  const body = [
    `# ${post.title}`,
    '',
    `URL: https://example.com/blog/${post.slug}/`,
    `發佈：${post.datePublished.slice(0, 10)}`,
    `更新：${(post.dateModified ?? post.datePublished).slice(0, 10)}`,
    `作者：${post.author.name}（${post.author.jobTitle}）`,
    '',
    `> ${post.description}`,
    '',
    post.markdown,
  ].join('\n')

  return new NextResponse(body, {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=86400',
    },
  })
}
```

---

## 七、Step 6：內容遷移腳本

改造 20 篇既有文章，手動做會很痛。這支腳本產出「每篇缺什麼」的清單。

```python
#!/usr/bin/env python3
"""geo-audit.py —— 掃描 content/posts/*.md，列出各篇的 GEO 缺口。

用法：python3 geo-audit.py content/posts/ --entity "OrderFlow"
"""
import argparse, re, sys, pathlib, json

NUM = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|％|ms|秒|分鐘|小時|天|週|個月|年|元|萬|億|USD|NT\$|\$|QPS|GB|TB)")
DATE = re.compile(r"20\d{2}\s*[-/年]\s*\d{1,2}")
PRONOUN_HEAD = re.compile(r"^(它|他們|這個|該|本|上述|如前所述|此)")
QUESTION_H = re.compile(r"[?？]|如何|怎麼|多少|為什麼|哪些|是什麼|要不要|該不該")


def split_front_matter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end], text[end + 4 :]
    return "", text


def audit(path: pathlib.Path, entity: str):
    raw = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(raw)

    headings = re.findall(r"^(#{2,3})\s+(.+)$", body, flags=re.M)
    paras = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 60 and not p.strip().startswith(("```", "|", "!["))]

    issues = []

    # 1. 標題是否為問句
    q_ratio = sum(1 for _, h in headings if QUESTION_H.search(h)) / max(len(headings), 1)
    if q_ratio < 0.5:
        issues.append(f"問句式標題僅 {q_ratio:.0%}（目標 ≥ 50%）")

    # 2. TL;DR
    if not re.search(r"(重點摘要|TL;DR|一句話總結|tldr)", body[:1500], flags=re.I):
        issues.append("缺少開頭 TL;DR 摘要區塊")

    # 3. 數據密度
    nums = len(NUM.findall(body))
    density = nums / max(len(paras), 1)
    if density < 0.8:
        issues.append(f"數據密度過低：{nums} 個帶單位數字 / {len(paras)} 段（目標 ≥ 0.8/段）")

    # 4. 日期標註
    if not DATE.search(body):
        issues.append("內文沒有任何年月標註（時效性題目會失分）")
    if "lastmod" not in fm and "dateModified" not in fm:
        issues.append("front matter 缺少 lastmod")

    # 5. 表格
    if body.count("\n|") < 3:
        issues.append("沒有 Markdown 表格（表格被引用率為散文的 2-3 倍）")

    # 6. FAQ
    if "faq:" not in fm and not re.search(r"##\s*(常見問題|FAQ)", body):
        issues.append("沒有 FAQ 區塊 / faq front matter")

    # 7. 外部具名引用
    ext_links = re.findall(r"\[([^\]]+)\]\(https?://(?!example\.com)[^)]+\)", body)
    if len(ext_links) < 2:
        issues.append(f"外部具名引用只有 {len(ext_links)} 個（目標 ≥ 3）")

    # 8. chunk 主詞獨立性
    orphan = [p for p in paras if entity not in p and PRONOUN_HEAD.match(p)]
    if len(orphan) > len(paras) * 0.25:
        issues.append(f"{len(orphan)}/{len(paras)} 段以代詞開頭且無主詞（chunk 無法獨立）")

    # 9. 過短段落（切出來的 chunk 資訊量不足）
    short = [p for p in paras if len(p) < 80]
    if len(short) > len(paras) * 0.4:
        issues.append(f"{len(short)}/{len(paras)} 段少於 80 字（chunk 資訊密度不足）")

    score = max(0, 100 - len(issues) * 11)
    return {"file": str(path), "score": score, "issues": issues}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--entity", default="")
    ap.add_argument("--min-score", type=int, default=0, help="低於此分數則 exit 1（供 CI 使用）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    files = sorted(pathlib.Path(a.path).rglob("*.md"))
    results = [audit(f, a.entity) for f in files]
    results.sort(key=lambda r: r["score"])

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"\n{r['score']:3d}  {r['file']}")
            for i in r["issues"]:
                print(f"      · {i}")
        avg = sum(r["score"] for r in results) / max(len(results), 1)
        print(f"\n平均分數：{avg:.1f}　檔案數：{len(results)}")

    if a.min_score and any(r["score"] < a.min_score for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
```

用法：

```bash
# 先掃全站，拿到基線與優先清單
python3 geo-audit.py content/posts/ --entity "OrderFlow"

# 放進 CI，擋下低於 70 分的新文章
python3 geo-audit.py content/posts/ --entity "OrderFlow" --min-score 70
```

---

## 八、Step 7：sitemap 與新鮮度訊號

```go-html-template
{{/* layouts/sitemap.xml —— 覆寫 Hugo 預設，加上正確的 lastmod 與優先權 */}}
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  {{ range .Data.Pages }}
  {{ if and (not .Params.draft) (not .Params.noindex) }}
  <url>
    <loc>{{ .Permalink }}</loc>
    <lastmod>{{ (default .Date .Lastmod).Format "2006-01-02T15:04:05-07:00" }}</lastmod>
    <changefreq>{{ if .IsHome }}daily{{ else if eq .Type "posts" }}monthly{{ else }}yearly{{ end }}</changefreq>
    <priority>{{ if .IsHome }}1.0{{ else if eq .Type "posts" }}0.8{{ else }}0.5{{ end }}</priority>
  </url>
  {{ end }}
  {{ end }}
</urlset>
```

**新鮮度的三個訊號要一致**，任一不一致都會削弱效果：

```
訊號                    來源                    常見錯誤
──────────────────────────────────────────────────────────────
sitemap 的 lastmod      建置期產生               設成 build time → 全站每天都「更新」
JSON-LD dateModified    front matter            忘記加，只有 datePublished
頁面上可見的日期文字      模板                    只顯示發佈日，不顯示更新日
HTTP Last-Modified      伺服器                   靜態主機常給檔案 mtime → 每次部署都變
```

修正 HTTP 標頭（Netlify / Vercel 類似）：

```
# netlify.toml
[[headers]]
  for = "/blog/*"
  [headers.values]
    Cache-Control = "public, max-age=0, must-revalidate, s-maxage=86400"
```

---

## 九、Step 8：自動化驗收（可放進 CI）

```python
#!/usr/bin/env python3
"""geo-verify.py —— 對線上頁面做端到端 GEO 驗收。

用法：python3 geo-verify.py https://example.com/blog/post/ [more urls...]
"""
import json, re, sys, urllib.request, urllib.error

BOTS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ClaudeBot/1.0",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; PerplexityBot/1.0",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Browser": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
}

def fetch(url, ua, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, f"ERR {e}"

def text_len(html):
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
    return len(re.sub(r"<[^>]+>", " ", h).split())

def jsonld_blocks(html):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, flags=re.S | re.I):
        try:
            out.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            out.append({"__parse_error__": True})
    return out

def check(url):
    print(f"\n{'='*72}\n{url}\n{'='*72}")
    ok = True

    # 1. 各 bot 存取
    _, browser_html = fetch(url, BOTS["Browser"])
    base_words = text_len(browser_html)
    print(f"\n[1] Crawler 存取（瀏覽器基準 {base_words} 字）")
    for name, ua in BOTS.items():
        if name == "Browser":
            continue
        code, html = fetch(url, ua)
        w = text_len(html) if code == 200 else 0
        ratio = w / base_words if base_words else 0
        flag = "OK " if code == 200 and ratio > 0.9 else "FAIL"
        if flag == "FAIL":
            ok = False
        print(f"    {flag}  {name:<16} {code}  {w:>6} 字  ({ratio:.0%})")

    html = browser_html

    # 2. JSON-LD
    blocks = jsonld_blocks(html)
    types = []
    for b in blocks:
        items = b if isinstance(b, list) else [b]
        for it in items:
            if isinstance(it, dict):
                types.append(it.get("@type", "?"))
    print(f"\n[2] JSON-LD：{len(blocks)} 個區塊，型別 {types or '無'}")
    for req in ("Organization", "BlogPosting", "Article"):
        pass
    if not any(t in types for t in ("BlogPosting", "Article", "WebPage")):
        print("    FAIL  缺少 Article / BlogPosting"); ok = False
    if any(b.get("__parse_error__") for b in blocks if isinstance(b, dict)):
        print("    FAIL  有 JSON-LD 解析錯誤"); ok = False

    # 3. 日期
    has_mod = "dateModified" in html
    has_time = bool(re.search(r'<time[^>]+datetime=', html))
    print(f"\n[3] 新鮮度：dateModified={has_mod}  <time datetime>={has_time}")
    if not (has_mod and has_time):
        ok = False

    # 4. 結構
    h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", html, flags=re.S | re.I)
    h2_text = [re.sub(r"<[^>]+>", "", h).strip() for h in h2]
    q = sum(1 for t in h2_text if re.search(r"[?？]|如何|多少|為什麼|哪些|是什麼|怎麼", t))
    sect = len(re.findall(r'<section[^>]+id=', html))
    tables = len(re.findall(r"<table", html, flags=re.I))
    print(f"\n[4] 結構：H2 {len(h2)} 個（問句式 {q}）｜section[id] {sect} 個｜table {tables} 個")
    if len(h2) and q / len(h2) < 0.4:
        print("    WARN  問句式標題比例偏低")
    if tables == 0:
        print("    WARN  沒有表格")

    # 5. Markdown 替代版本
    md = re.search(r'<link[^>]+type="text/markdown"[^>]+href="([^"]+)"', html)
    print(f"\n[5] Markdown 版本：{md.group(1) if md else '無（非必要，但建議）'}")

    # 6. canonical
    can = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', html)
    print(f"[6] canonical：{can.group(1) if can else 'FAIL 無'}")
    if not can:
        ok = False

    print(f"\n結果：{'PASS' if ok else 'FAIL'}")
    return ok

if __name__ == "__main__":
    urls = sys.argv[1:]
    if not urls:
        print(__doc__); sys.exit(2)
    sys.exit(0 if all(check(u) for u in urls) else 1)
```

放進 GitHub Actions：

```yaml
# .github/workflows/geo-check.yml
name: GEO check
on:
  pull_request:
    paths: ['content/**', 'layouts/**', 'static/robots.txt']
  schedule:
    - cron: '0 2 * * 1'   # 每週一 02:00 UTC 對正式站做健檢

jobs:
  content-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Audit content
        run: python3 scripts/geo-audit.py content/posts/ --entity "OrderFlow" --min-score 65

  live-verify:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Verify production pages
        run: |
          python3 scripts/geo-verify.py \
            https://example.com/ \
            https://example.com/pricing/ \
            https://example.com/blog/oms-cost/
```

---

## 十、常見坑與排查

```
坑                              症狀                        解法
──────────────────────────────────────────────────────────────────────────
改完 CDN 規則沒生效              仍然 403                    CDN 有快取層；
                                                            purge 後再測，
                                                            並確認規則優先權在最前面

geo-verify 顯示 bot 字數正常     實際還是沒被引用             這是 Level 1→2 的問題，
但引用率沒動                                                內容層才是瓶頸（Part 3 §2）

加了 FAQPage schema             schema 與可見內容不一致       acceptedAnswer.text 必須
但沒效果                                                    與頁面文字相同

Hugo 的 .md 輸出把 shortcode    Markdown 版有 {{ }} 殘留     用 .Plain 或先 render
原樣輸出                                                    再轉 Markdown；
                                                            或避免在核心內容用 shortcode

Next.js 頁面 curl 有內容        內容在 useEffect 裡才補完整   把資料抓取移到 server
但關鍵段落缺失                                              component / generateStaticParams

dateModified 每天變             Git commit time 太敏感        用 front matter 手動控制
                                                            重要頁面的 lastmod

llms-full.txt 太大              超過 5MB，抓取逾時            分檔（依 category），
                                                            或只放摘要不放全文

section id 撞名                 錨點跳錯位置                  用 Hugo 的 .Anchor
                                                            （已自動去重）

表格用 CSS grid 排版            解析器抓不到欄位關係          一定要用 <table>

改版後 GEO 分數掉了              沒人發現                     把 geo-audit 放進 CI，
                                                            設 min-score 門檻
```

### 收尾檢查清單

```
Layer 1（技術）
□ ai-crawler-check.sh 全部 200，字數比 > 90%
□ CDN/WAF 有 AI bot skip 規則且在最前面
□ robots.txt 區分檢索 bot 與訓練 bot
□ 核心內容全部 SSR/SSG，無 JS 也完整
□ sitemap lastmod 正確（不是 build time）

Layer 2（結構）
□ Organization JSON-LD（sameAs 填滿）
□ 每篇 Article JSON-LD（含 author 的 Person）
□ 有 FAQ 的頁面有 FAQPage schema，且與可見文字一致
□ 語意化 HTML：article / section[id] / h2[id] / time[datetime]
□ 表格是 <table>，不是圖片、不是 div

Layer 3（內容，用 geo-audit.py 驗）
□ 問句式 H2 比例 ≥ 50%
□ 每篇有 TL;DR
□ 數據密度 ≥ 0.8 個帶單位數字／段
□ 每篇至少一張表
□ 外部具名引用 ≥ 3
□ 無「代詞開頭且無主詞」的孤兒段落

流程
□ geo-audit 進 CI，設 min-score
□ geo-verify 排程每週跑正式站
□ 新文章模板內建 TL;DR / FAQ / 來源標註欄位
```

做完這一份清單，你就在 Level 2 了。下一篇要解決最後一個問題：**你怎麼證明這些有效？**

---

*本系列文章：*
- [Part 1：概念篇 — 當搜尋結果不再是十條藍色連結](/posts/aio-geo-part1-concepts-zh/)
- [Part 2：原理篇 — AI 引擎如何檢索、選擇與引用你的內容](/posts/aio-geo-part2-how-engines-work-zh/)
- [Part 3：方法篇 — 內容、結構、技術三層優化策略](/posts/aio-geo-part3-strategies-zh/)
- **Part 4（本篇）：實作篇 — 把一個網站改造成 AI 可引用**
- [Part 5：量測與案例篇 — 建立 GEO 監測系統與實戰復盤](/posts/aio-geo-part5-measurement-case-study-zh/)
- [Part 6：實戰案例 — 大型企業官網（多語系 + AWS + 法遵）](/posts/aio-geo-part6-case-enterprise-site-zh/)
- [Part 7：實戰案例 — 電商網站（12,000 SKU + 價格新鮮度）](/posts/aio-geo-part7-case-ecommerce-zh/)
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- [Part 9：實戰案例 — 線上課程平台（付費牆 + 影片）](/posts/aio-geo-part9-case-course-platform-zh/)
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
- 商業篇：[Part 11 市場](/posts/aio-geo-part11-market-landscape-zh/) ｜ [Part 12 GEO vs SEO 判斷](/posts/aio-geo-part12-geo-vs-seo-decision-zh/) ｜ [Part 13 顧問方法論](/posts/aio-geo-part13-consulting-playbook-zh/) ｜ [Part 14 產業劇本](/posts/aio-geo-part14-industry-playbooks-zh/) ｜ [Part 15 工具與技術棧](/posts/aio-geo-part15-tools-stack-zh/) ｜ [Part 16 規模化](/posts/aio-geo-part16-scaling-the-business-zh/)
