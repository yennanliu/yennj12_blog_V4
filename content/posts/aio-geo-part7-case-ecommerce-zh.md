---
title: "AIO / GEO - Part 7 - 實戰案例：電商網站（12,000 SKU + 價格新鮮度）"
date: 2026-08-03T09:00:00+08:00
draft: false
weight: 7
description: "一家台灣戶外用品電商，12,000 個 SKU、跑在 Vercel + Shopify Headless 上。電商 GEO 的兩個獨有難題：長尾商品頁怎麼模板化才不變成薄內容，以及價格與庫存怎麼讓模型抓到最新的。"
categories: ["AI", "SEO", "GEO", "Case Study", "E-commerce", "all"]
tags: ["GEO", "AIO", "電商", "Shopify", "Next.js", "Product Schema", "SKU", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "18 min"
---

> 電商 GEO 的核心矛盾：
> 你有 12,000 頁，但只有 40 頁值得為 GEO 手工優化。
> 剩下 11,960 頁要靠模板——而模板化內容天生就是薄內容。
>
> 解法不是「把每頁寫厚」，
> 是「讓資料本身變成內容」。

---

## 一、情境

```
公司      台灣戶外用品電商，35 人，年 GMV 約 NT$4.2 億
品項      登山、露營、單車裝備，12,000 SKU，420 個品牌
技術      Shopify（後台）+ Next.js App Router（前台，headless）
部署      Vercel（前台）、Shopify（結帳）、Algolia（站內搜尋）
內容      商品頁 12,000 / 分類頁 380 / 選購指南 64 篇
```

**業務動機**：客單價 NT$3,000-15,000 的裝備，購買前研究期長達 2-6 週。使用者開始用 AI 問「登山杖怎麼選」「XX 帳篷跟 YY 比哪個好」。

```
基線量測（45 題 × 3 引擎，2026-03）
──────────────────────────────────────
提及率            22%
引用率            9%
價格正確率        14%   ← 幾乎全錯
Page Concentration 91%  ← 引用幾乎全落在 3 篇選購指南
Coverage Gap      38%
```

`Page Concentration 91%` 是這個案例的核心訊號：**12,000 個商品頁，一個都沒被引用過**。

---

## 二、為什麼 12,000 頁一個都沒被引用

```
典型的商品頁（改前）
┌────────────────────────────────────────────┐
│  [商品大圖]                                 │
│                                            │
│  XX 品牌 超輕量登山杖 T7                     │
│  NT$3,280                                  │
│  [加入購物車]                               │
│                                            │
│  商品描述：                                 │
│  「輕巧耐用，是登山愛好者的最佳選擇。」        │  ← 全部的文字
│                                            │
│  規格：（Tab 切換，JS 載入）                  │  ← crawler 看不到
│  評價：（JS 載入，來自第三方 widget）          │  ← crawler 看不到
└────────────────────────────────────────────┘

curl 拿到的純文字：47 個字
可接地的事實：0 個（「輕巧耐用」不是事實）
```

三個死因同時發生：

```
死因                        Part 2 對應   影響
────────────────────────────────────────────────────
規格在 JS Tab 裡             死因 3       規格是商品頁唯一有價值的資訊
評價由第三方 widget 注入      死因 1       UGC 是 AI 最愛引用的內容
商品描述是廠商供稿的行銷文    —            0 個可接地事實
```

---

## 三、五個關鍵決策

### 決策 1：不要「寫」內容，要「渲染」資料

12,000 頁不可能手寫。但商品資料庫裡本來就有大量事實——它們只是沒有被渲染成 HTML。

```
Shopify 後台已有的資料            改前呈現方式        改後呈現方式
──────────────────────────────────────────────────────────────
規格 metafields（18 個欄位）       JS Tab             HTML <table>
重量、材質、尺寸、承重             同上                同上 + 單位標註
適用情境（metafield）              未使用              一段自動生成的句子
同系列 / 替代品                    「相關商品」輪播     文字化的比較表
評價（Judge.me）                  第三方 JS widget    SSR 抓取後渲染成 HTML
庫存與價格                        JS 即時查詢          SSR + Product schema
```

**這是電商 GEO 最重要的一句話：你的資料庫已經有內容了，問題只是沒有渲染出來。**

商品頁的 server component：

```tsx
// app/products/[handle]/page.tsx
import { getProduct, getReviews } from '@/lib/shopify'
import { JsonLd } from '@/components/JsonLd'
import { productSchema } from '@/lib/schema'

export const revalidate = 900   // 15 分鐘，兼顧價格新鮮度與快取效率

export async function generateStaticParams() {
  // 只預先產生 Top 2,000 熱門商品；其餘走 ISR 首次請求時生成
  const handles = await getTopProductHandles(2000)
  return handles.map((handle) => ({ handle }))
}

export default async function ProductPage({ params }) {
  // 關鍵：規格與評價都在 server 端取得，直接進 HTML
  const [product, reviews] = await Promise.all([
    getProduct(params.handle),
    getReviews(params.handle, { limit: 8 }),
  ])

  return (
    <article>
      <JsonLd data={productSchema(product, reviews)} />

      <h1>{product.title}</h1>

      {/* 事實摘要：一個完美的獨立 chunk */}
      <section id="summary" aria-labelledby="h-summary">
        <h2 id="h-summary">{product.title} 的重點規格是什麼？</h2>
        <p>{buildFactSentence(product)}</p>
      </section>

      {/* 規格表：不是 Tab，是永遠可見的 table */}
      <section id="specs" aria-labelledby="h-specs">
        <h2 id="h-specs">{product.title} 完整規格</h2>
        <table>
          <tbody>
            {product.specs.map((s) => (
              <tr key={s.key}>
                <th scope="row">{s.label}</th>
                <td>{s.value}{s.unit ? ` ${s.unit}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* 評價：SSR 渲染文字，不用第三方 widget */}
      <section id="reviews" aria-labelledby="h-reviews">
        <h2 id="h-reviews">{product.title} 的使用者評價</h2>
        <p>
          共 {reviews.count} 則評價，平均 {reviews.average} / 5。
          最常被提到的優點是{reviews.topPros.join('、')}；
          最常被提到的缺點是{reviews.topCons.join('、')}。
        </p>
        {reviews.items.map((r) => (
          <blockquote key={r.id}>
            <p>{r.body}</p>
            <footer>{r.author}，{r.date}｜{r.rating} 星</footer>
          </blockquote>
        ))}
      </section>
    </article>
  )
}
```

自動生成的事實句（取代廠商行銷文案）：

```ts
// lib/factSentence.ts
export function buildFactSentence(p: Product): string {
  const parts: string[] = []
  parts.push(`${p.title} 是 ${p.vendor} 的${p.productType}`)
  if (p.specs.weight)   parts.push(`單支重量 ${p.specs.weight} 公克`)
  if (p.specs.material) parts.push(`材質為${p.specs.material}`)
  if (p.specs.length)   parts.push(`收納長度 ${p.specs.length} 公分`)
  if (p.specs.maxLoad)  parts.push(`最大承重 ${p.specs.maxLoad} 公斤`)
  const head = parts.join('，') + '。'

  const price = `目前售價 NT$${p.price.toLocaleString()}` +
    (p.compareAtPrice ? `（原價 NT$${p.compareAtPrice.toLocaleString()}）` : '') +
    `，${p.available ? '有現貨' : '缺貨中'}。`

  const use = p.specs.useCase
    ? `適用情境：${p.specs.useCase}。` : ''

  const asOf = `（價格與庫存資訊更新於 ${new Date().toISOString().slice(0, 10)}）`

  return head + price + use + asOf
}
```

**一句話的效果**：這段自動生成的文字通常 80-120 字，含 5-8 個可接地事實，比原本 47 個字的行銷文案有效得多，而且是**零人力成本**。

### 決策 2：價格新鮮度——用 `priceValidUntil` 而不是硬扛

電商 GEO 最惡名昭彰的問題：**模型講出三個月前的價格**。

```
問題根源
  引擎的索引更新週期 ≈ 1-4 週
  你的價格變動週期 ≈ 每週（促銷檔期）
  → 結構性錯配，無法完全解決
```

務實策略是「讓模型知道這個價格何時到期」，而不是追求即時同步：

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "XX 超輕量登山杖 T7",
  "sku": "TP-T7-BLK",
  "gtin13": "4712345678901",
  "brand": { "@type": "Brand", "name": "XX" },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.6", "reviewCount": 128
  },
  "offers": {
    "@type": "Offer",
    "price": "3280",
    "priceCurrency": "TWD",
    "priceValidUntil": "2026-08-31",
    "availability": "https://schema.org/InStock",
    "url": "https://example.com/products/tp-t7",
    "seller": { "@id": "https://example.com/#organization" },
    "shippingDetails": {
      "@type": "OfferShippingDetails",
      "shippingRate": { "@type": "MonetaryAmount", "value": "0", "currency": "TWD" },
      "deliveryTime": {
        "@type": "ShippingDeliveryTime",
        "handlingTime": { "@type": "QuantitativeValue", "minValue": 1, "maxValue": 2, "unitCode": "DAY" },
        "transitTime":  { "@type": "QuantitativeValue", "minValue": 1, "maxValue": 3, "unitCode": "DAY" }
      }
    }
  }
}
```

同時在頁面可見文字中寫明：

```
「目前售價 NT$3,280，此價格有效至 2026 年 8 月 31 日。
  即時價格與庫存請見商品頁。」
```

**效果**：模型引用時會帶出「截至 X 日的價格為 Y」這樣的表述，而不是斷言一個過期價格。價格正確率從 14% 提升到 71%——剩下的 29% 是索引延遲造成的，這是產業共通的天花板。

### 決策 3：分類頁才是真正的戰場

```
                查詢量   競爭度   商品頁能贏嗎   分類/指南頁能贏嗎
────────────────────────────────────────────────────────────────
「登山杖怎麼選」   高      高       ✘             ✔  ← 主戰場
「輕量登山杖推薦」 高      高       ✘             ✔  ← 主戰場
「XX T7 好用嗎」   低      低       ✔             ✘
「300g 以下登山杖」中      中       ✘             ✔  ← 被低估
```

第四類最值得投資：**規格條件式查詢**。使用者用參數而不是品牌名來找東西，而這正是資料庫能自動回答的。

做法是把 Algolia 的 facet 組合渲染成可索引的分類頁：

```
/collections/trekking-poles/                    （主分類）
/collections/trekking-poles/under-300g/         （重量 facet）
/collections/trekking-poles/carbon/             （材質 facet）
/collections/trekking-poles/under-300g-carbon/  （雙 facet，只開熱門組合）
```

每頁自動生成一段導語 + 一張比較表：

```tsx
// 分類頁的自動導語
<section id="overview">
  <h2>300 公克以下的碳纖維登山杖有哪些選擇？</h2>
  <p>
    本頁列出 14 款單支重量 300 公克以下的碳纖維登山杖，
    價格區間為 NT$2,180 至 NT$8,900，中位數 NT$4,250。
    最輕的是 {lightest.title}（{lightest.weight} 公克），
    評價最高的是 {topRated.title}（{topRated.rating} / 5，
    {topRated.reviewCount} 則評價）。
    （資料更新於 {today}）
  </p>

  <table>
    <caption>300g 以下碳纖維登山杖比較（依重量排序）</caption>
    <thead>
      <tr><th>型號</th><th>重量</th><th>收納長</th><th>承重</th><th>價格</th><th>評分</th></tr>
    </thead>
    <tbody>{/* 由資料渲染 */}</tbody>
  </table>
</section>
```

**這種頁面被引用率極高**，因為它同時滿足：有數字、有表格、有比較、有日期、可原句搬用。

**但要控制數量**：只開「有足夠商品（≥ 8 件）且有真實搜尋需求」的 facet 組合。無節制展開會產生數萬個薄頁面，反而拖累全站。

```
本案例的規則
  單 facet：全開（約 180 頁）
  雙 facet：商品數 ≥ 8 且月搜尋量 ≥ 30 才開（約 240 頁）
  三 facet 以上：一律 noindex + canonical 指向雙 facet 版本
```

### 決策 4：評價內容要進 HTML

AI 引擎大量引用真實使用者經驗。第三方評價 widget 是最常見的浪費。

```
改前：<div id="judgeme_widget"></div>  ← crawler 看到一個空 div
改後：build/ISR 時透過 API 取回評價，SSR 成 HTML
      + AggregateRating schema
      + 「最常提到的優缺點」自動摘要
```

「最常提到的優缺點」用一次性的 LLM 批次處理即可：

```python
# 每週跑一次，把評價摘要寫回 Shopify metafield
# 12,000 SKU × 每次 ~600 token → 約 US$9/週
def summarize_reviews(product_id, reviews):
    if len(reviews) < 5:
        return None          # 樣本太少不做摘要，避免誤導
    prompt = (
        "以下是同一商品的使用者評價。請歸納最常被提到的 3 個優點與 "
        "3 個缺點，各以 6 字以內的短語表示，輸出 JSON："
        '{"pros": [...], "cons": [...]}。'
        "只根據評價內容，不要推測。\n\n"
        + "\n".join(f"- {r['rating']}星：{r['body'][:200]}" for r in reviews[:40])
    )
    ...
```

**注意 `len(reviews) < 5` 的守門**：樣本不足時生成的摘要會失真，而錯誤的摘要被引用的傷害大於沒有摘要。

### 決策 5：選購指南從「一篇長文」拆成「問題叢集」

原本 64 篇選購指南中，有 3 篇長文吃掉了 91% 的引用。問題是這 3 篇「什麼都講一點」，導致：

```
「登山杖完整選購指南」（8,200 字）
  → 涵蓋 材質 / 重量 / 鎖定機構 / 握把 / 杖尖 / 價位 / 保養 / 品牌
  → 每個主題只有 2-3 段
  → rerank 時，任何一個具體問題都只有一小段相關 → 分數被稀釋
```

拆解後：

```
/guides/trekking-pole/              （總覽，內部連結到各子頁）
/guides/trekking-pole/material/     「碳纖維和鋁合金登山杖差在哪？」
/guides/trekking-pole/weight/       「登山杖多重才算輕量？」
/guides/trekking-pole/lock-type/    「外鎖、內鎖、快扣哪種好？」
/guides/trekking-pole/price/        「登山杖預算怎麼抓？」
...共 11 個子頁，每頁 900-1,400 字，主題單一
```

```
                 改前（1 篇 8,200 字）   改後（11 篇 × 1,100 字）
─────────────────────────────────────────────────────────────
總字數            8,200                 12,100
被引用的題數       2/45                  9/45
每頁 chunk 品質    低（主題混雜）          高（單一主題）
```

**通則：主題單一的 1,000 字，勝過主題混雜的 8,000 字。** 這與傳統 SEO 的「內容越長越好」相反，是 GEO 最反直覺的一點。

---

## 四、結果

```
指標                  改前(2026-03)   改後(2026-08)   變化
────────────────────────────────────────────────────────
提及率                22%            48%            +26pp
引用率                9%             31%            +22pp
價格正確率            14%            71%            +57pp
Page Concentration    91%            43%            -48pp   ← 引用分散了
Coverage Gap          38%            12%            -26pp

被引用的頁面類型分佈
  選購指南             91%            38%
  分類 / facet 頁       0%            41%   ← 新增的主力
  商品頁                0%            18%
  其他                  9%             3%

商業側
AI referral 工作階段   180/月         2,100/月       ×11.7
AI referral 轉換率     —              3.1%          （站均 1.4%）
品牌詞搜尋            8,900/月        16,400/月     +84%
```

### 投入分解

```
項目                          人天    備註
────────────────────────────────────────────────────────
商品頁模板改造（SSR + 表格）     8      一次做完，12,000 頁受益
評價 SSR + 摘要 pipeline        6      含每週批次作業
Product schema + priceValidUntil 3
facet 分類頁生成邏輯            9      含 noindex 規則
選購指南拆分（3 → 11 + 8 新增）  16     唯一大量人力的部分
監測系統                       3
────────────────────────────────────────────────────────
合計                           45 人天（約 2.5 個月，2 人）
```

**注意投入結構**：34 人天是工程（一次性，惠及全站），只有 16 人天是內容。這和 Part 5 案例 A（B2B SaaS，內容佔 48/78 人天）完全相反。**電商 GEO 是工程密集，不是內容密集。**

---

## 五、三個 insight

### 1. 電商的 GEO 是「資料渲染問題」，不是「內容生產問題」

你的 PIM / 商品資料庫裡已經躺著幾十萬個可接地事實。它們沒被引用，只是因為藏在 JS Tab、第三方 widget 或 PDF 裡。

```
先問這三個問題，再考慮寫任何新內容：
  □ 規格表在 HTML 裡嗎？
  □ 評價文字在 HTML 裡嗎？
  □ 價格與庫存在 HTML 與 schema 裡嗎？
```

### 2. Facet 分類頁是電商獨有的優勢，但要節制

規格條件式查詢（「300g 以下的碳纖維登山杖」）是 AI 搜尋時代的新流量池——使用者不再需要自己組合篩選器，直接問就好。

而你的資料庫能自動生成這類頁面，**這是純內容站做不到的**。

但無節制展開 facet 會製造數萬個薄頁面。門檻：**商品數 ≥ 8 且有真實搜尋需求**，其餘 noindex。

### 3. 價格正確率的天花板是 71%，接受它

索引更新週期與價格變動週期的錯配是結構性的。與其追求 100%，不如：

```
□ 用 priceValidUntil 讓模型知道價格的時效
□ 頁面文字寫明「此價格有效至 X 日」
□ 促銷檔期用 ISR 縮短 revalidate（本案例檔期時降到 300 秒）
□ 接受被引用時帶出「截至 X 日」的表述——這其實比精確價格更誠實
```

---

## 六、可以直接抄的清單

```
商品頁模板（一次做完，全站受益）
□ 規格從 Tab / JS 改成永遠可見的 <table>
□ 評價從第三方 widget 改成 SSR 渲染文字
□ 自動生成「事實句」取代廠商行銷文案
□ Product schema：sku / gtin / brand / offers / aggregateRating
□ offers 加 priceValidUntil 與 shippingDetails
□ 頁面文字寫明價格有效期與資料日期
□ 熱門商品用 generateStaticParams 預渲染，長尾走 ISR

分類 / facet 頁
□ 單 facet 全開
□ 雙 facet：商品數 ≥ 8 且有搜尋需求才開
□ 三 facet 以上 noindex + canonical
□ 每頁自動生成導語（數量、價格區間、極值、最高評價）
□ 每頁一張比較表，含 caption 與資料日期

選購指南
□ 長文拆成單一主題的子頁（目標 900-1,400 字）
□ 標題用使用者真正會問的問句
□ 總覽頁保留，作為 hub 內部連結

評價 pipeline
□ 每週批次生成「最常提到的優缺點」
□ 評價數 < 5 不生成摘要
□ AggregateRating 與可見文字一致

不要做
✘ 為每個 SKU 手寫獨特描述（12,000 頁不可能，也沒必要）
✘ 無節制展開 facet 組合
✘ 追求價格 100% 即時
✘ 用 AI 大量生成商品文案（重複度高，rerank 全滅）
```

---

*本系列文章：*
- [Part 1：概念篇](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2：原理篇](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3：方法篇](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4：實作篇](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5：量測與案例篇](/posts/aio-geo-part5-measurement-case-study-zh/)
- [Part 6：實戰案例 — 大型企業官網](/posts/aio-geo-part6-case-enterprise-site-zh/)
- **Part 7（本篇）：實戰案例 — 電商網站**
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- [Part 9：實戰案例 — 線上課程平台](/posts/aio-geo-part9-case-course-platform-zh/)
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
- 商業篇：[Part 11 市場](/posts/aio-geo-part11-market-landscape-zh/) ｜ [Part 12 GEO vs SEO 判斷](/posts/aio-geo-part12-geo-vs-seo-decision-zh/) ｜ [Part 13 顧問方法論](/posts/aio-geo-part13-consulting-playbook-zh/) ｜ [Part 14 產業劇本](/posts/aio-geo-part14-industry-playbooks-zh/) ｜ [Part 15 工具與技術棧](/posts/aio-geo-part15-tools-stack-zh/) ｜ [Part 16 規模化](/posts/aio-geo-part16-scaling-the-business-zh/)
