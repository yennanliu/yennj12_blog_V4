---
title: "AIO / GEO - Part 8 - 實戰案例：單頁式 Landing Page（內容只有 800 字）"
date: 2026-08-04T09:00:00+08:00
draft: false
weight: 8
description: "一個 3 人團隊的 SaaS 產品，全站只有一頁 Landing Page 加一份文件。內容量是最小的，資源也是最少的——這反而讓「該做什麼、不該做什麼」變得極度清楚。從 0 到被引用的 8 週實錄。"
categories: ["AI", "SEO", "GEO", "Case Study", "Startup", "all"]
tags: ["GEO", "AIO", "Landing Page", "SaaS", "Startup", "Astro", "Cloudflare", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "16 min"
---

> 一頁式網站做 GEO，聽起來像沒有勝算。
> 但小團隊有一個大公司沒有的優勢：可以在一週內把整個網站重寫。
>
> 這個案例的重點不是技巧，
> 是「資源極少時，該把力氣放在哪」。

---

## 一、情境

```
產品      Webhook 除錯與重送工具（開發者工具）
團隊      3 人（2 工程 + 1 兼職行銷）
網站      Landing Page（1 頁，約 800 字）+ 文件站（12 頁）+ 部落格（3 篇）
技術      Astro（靜態）+ Cloudflare Pages
定價      Free / Pro $19 / Team $79
競品      5 家，其中 2 家是 YC 出身、內容量是他們的 50 倍
目標      被「webhook 除錯工具有哪些」這類問題引用
```

```
基線量測（30 題 × 3 引擎，2026-01）
──────────────────────────────────
提及率            0%
引用率            0%
Coverage Gap      83%
```

**乾淨的 0**。這其實是好事——任何改動的效果都會很清楚。

---

## 二、先搞清楚：小網站的三個結構性劣勢

```
劣勢                   影響                     能不能繞過
──────────────────────────────────────────────────────────
網域權威幾乎為零        同分時永遠輸              ✘ 不能，需要時間
內容量少               能命中的查詢少             ✔ 能，靠精準取代廣度
沒有第三方提及          實體不存在                ✔ 能，這是最快的一項
```

**戰略推論**：不要跟大公司比廣度。找出「他們沒有認真回答、而你能給出最好答案」的少數問題，全力攻下。

實務上就是：**放棄品類發現題（「有哪些工具」），主攻具體問題題（「怎麼在本機接收 Stripe webhook」）。**

```
題目類型                大公司優勢    小團隊勝算   本案例配置
──────────────────────────────────────────────────────────
品類發現「有哪些 X」      壓倒性        低          放棄（初期）
問題解決「怎麼做 Y」      普通          高          全力（70% 資源）
競品比較「X vs Y」        普通          中高        投入（20%）
品牌直問「X 是什麼」      —            —           基本盤（10%）
```

---

## 三、六個決策（依執行順序）

### 決策 1：把 Landing Page 拆成 8 頁（第 1 週）

一頁式的問題不是「內容少」，是「所有主題混在一個 chunk 裡」。

```
改前：/  （800 字，涵蓋 是什麼 / 特色 / 定價 / FAQ）
      → 切成 chunk 後每個主題只有 100 字左右
      → 任何具體問題都無法被完整回答

改後：
/                         產品首頁（保留，仍是 800 字）
/how-it-works             「這個工具是怎麼運作的？」
/pricing                  「定價方案與各方案差異」
/vs/ngrok                 「和 ngrok 有什麼不同？」
/vs/webhook-site          「和 webhook.site 有什麼不同？」
/use-cases/stripe         「怎麼在本機除錯 Stripe webhook？」
/use-cases/github         「怎麼除錯 GitHub webhook？」
/use-cases/shopify        「怎麼除錯 Shopify webhook？」
```

**每頁 700-1,200 字，主題單一。** 這是 Part 7 「主題單一的 1,000 字勝過主題混雜的 8,000 字」的極簡版本。

Astro 的 content collection 讓這件事幾乎零成本：

```ts
// src/content/config.ts
import { defineCollection, z } from 'astro:content'

const pages = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    question: z.string(),          // 這一頁回答的核心問題
    description: z.string(),
    tldr: z.array(z.string()).min(2).max(4),   // 強制寫 TL;DR
    updated: z.coerce.date(),
    faq: z.array(z.object({ q: z.string(), a: z.string() })).optional(),
  }),
})

export const collections = { pages }
```

`tldr` 設成必填且限制 2-4 條，是最便宜的品質控制——**schema 強制比 code review 可靠**。

### 決策 2：競品比較頁（第 2 週）

小團隊最容易忽略、投報率卻最高的一類頁面。

```
為什麼有效
  ① 「X vs Y」是高意圖查詢，且大公司通常不寫（不想提對手）
  ② 比較表是被引用率最高的格式
  ③ 你比任何人都清楚差異在哪
```

關鍵是**誠實**。寫一份偏袒自己的比較表，會在兩個地方失敗：使用者不信，而模型會拿去和其他來源交叉比對。

```markdown
## HookLab 和 ngrok 有什麼不同？

兩者解決的問題只有部分重疊。ngrok 是通用的內網穿透工具，
HookLab 專注在 webhook 的接收、檢視與重送。

| | HookLab | ngrok |
|---|---|---|
| 主要用途 | Webhook 除錯與重送 | 通用 HTTP 隧道 |
| 請求歷史保留 | 30 天（Pro） | 免費版 2 小時 |
| 重送單一請求 | ✔ 一鍵 | ✘ 需自行重打 |
| Payload 差異比對 | ✔ | ✘ |
| 非 HTTP 協定（TCP/TLS） | ✘ | ✔ |
| 固定網域 | ✔ 免費版即有 | 付費版 |
| 團隊共用 inbox | ✔ | ✘ |
| 價格（個人） | 免費 / $19 | 免費 / $10 |

**什麼時候該用 ngrok 而不是 HookLab**：如果你需要暴露的不只是
webhook 端點——例如要讓同事連進本機的完整開發伺服器、
或需要 TCP/TLS 隧道——ngrok 是更合適的工具。許多使用者
兩個都用。

（比較基準：HookLab v2.4、ngrok v3.18，2026 年 2 月）
```

**「什麼時候該用對手」這一段是關鍵**。它讓整份比較的可信度大幅提升，而模型明顯偏好引用有平衡觀點的來源。

實際結果：`/vs/ngrok` 成為全站被引用最多的頁面。

### 決策 3：文件站也是 GEO 資產（第 3 週）

開發者工具的文件通常寫得像 API reference，對 GEO 幾乎無用。

```
改前的文件標題              改後
────────────────────────────────────────────────────
Installation              怎麼安裝 HookLab CLI？
Configuration             HookLab 的設定檔有哪些選項？
Webhooks                  怎麼把 Stripe webhook 導到本機？
Troubleshooting           HookLab 連不上時怎麼排查？
API Reference             （維持不變——這類頁面本來就是查表用）
```

同時每頁加上：

```
□ 開頭一句話說明「這頁解決什麼問題」
□ 完整的可執行範例（不是片段）
□ 常見錯誤訊息與對應解法（這一項被引用率極高）
```

**「錯誤訊息 → 解法」的段落是開發者工具的隱藏金礦**：使用者遇到錯誤時會直接把錯誤訊息貼給 AI，而能精確對上錯誤字串的頁面幾乎必被引用。

```markdown
### 錯誤：`ECONNREFUSED 127.0.0.1:3000`

原因：HookLab 收到了 webhook，但轉發到本機的 3000 埠時被拒絕，
代表本機服務沒有在監聽該埠。

排查順序：
1. 確認本機服務已啟動：`curl -I http://localhost:3000/webhook`
2. 確認埠號與 `hooklab.toml` 中的 `forward_port` 一致
3. 若服務綁在 `0.0.0.0` 以外的位址，改用 `--forward-host` 指定
```

### 決策 4：開源一個小工具（第 4 週）

小團隊建立實體存在最快的方式。

```
做了什麼：把內部的 webhook payload 驗證邏輯抽成獨立套件
         `@hooklab/verify`（MIT，支援 Stripe/GitHub/Shopify/Slack
         等 9 家的簽章驗證），發到 npm 與 GitHub

投入：3 人天

八週後的效果：
  GitHub 412 stars
  npm 週下載 2,800
  README 中的 "Built by HookLab" 帶來持續的品牌提及
  → 「怎麼驗證 Stripe webhook 簽章」這題開始引用到他們
```

**這比任何內容行銷都快**。原因：開源專案天然具備第三方存在（GitHub、npm、被其他 repo 依賴），而這正是小團隊最缺的東西。

### 決策 5：Cloudflare Pages 的存取層檢查（第 1 天，30 分鐘）

```bash
$ ./ai-crawler-check.sh https://hooklab.dev/
USER-AGENT             CODE   BYTES
GPTBot/1.0             200    18422
OAI-SearchBot/1.0      200    18422
ClaudeBot/1.0          200    18422
PerplexityBot/1.0      403    0        ← 唯一的問題
Googlebot/2.1          200    18422
```

原因：Cloudflare 的 Bot Fight Mode（免費方案預設開啟）。關掉即可。

**靜態站 + Cloudflare Pages 的組合，技術層幾乎不需要做事**——這是小團隊唯一的結構性優勢，30 分鐘就能拿到大公司花 6 週才能拿到的東西（見 Part 6）。

### 決策 6：不做的事（同樣重要）

```
不做                      理由
──────────────────────────────────────────────────────────
每週發部落格文章            3 人團隊做不到，且薄文章有害
追求品類發現題              大公司的內容量差距 50 倍，初期打不贏
llms.txt / llms-full.txt   加了（10 分鐘），但沒抱期待
Core Web Vitals 調校        Astro 靜態站本來就快
多語系                     使用者主要是英文圈開發者
影片內容                   沒有人力
付費監測工具               自己寫 60 行 Python 就夠（Part 5）
```

**小團隊的 GEO 成敗，一半取決於「不做什麼」。**

---

## 四、結果（8 週）

```
指標              Week 0    Week 4    Week 8
─────────────────────────────────────────────
提及率            0%        11%       29%
引用率            0%        7%        23%
Coverage Gap      83%       41%       28%

被引用的頁面
  /vs/ngrok                          9 次   ← 最多
  /docs/troubleshooting              7 次
  /use-cases/stripe                  6 次
  GitHub: @hooklab/verify README     5 次   ← 非自家網域
  /vs/webhook-site                   4 次
  /                                  2 次
  其他                               3 次

商業側
  註冊數          40/月     95/月     210/月
  其中自陳「從 AI 得知」  —   —        31%
  Pro 轉付費      3/月      8/月      19/月
```

### 投入分解

```
項目                    人天   誰做
────────────────────────────────────
Landing Page 拆 8 頁     4     行銷 + 工程各半
競品比較頁 ×2            3     工程（他們最清楚差異）
文件站改寫               5     工程
開源 @hooklab/verify     3     工程
存取層修正               0.1   工程
監測腳本                 1     工程
────────────────────────────────────
合計                    16 人天（8 週內分散完成）
```

**16 人天，這是本系列所有案例中最低的投入**，而相對成長幅度最大（0 → 23%）。原因不是他們做得比較好，是**基期為零時任何正確的動作都有大效果**。

---

## 五、三個 insight

### 1. 小網站的優勢是「可以整站重寫」

大企業改 8 個頁面要 6 週跑簽核（Part 6）；3 人團隊改整個網站只要 4 人天。

```
資源少 ≠ 劣勢
  真正的劣勢是「權威度」和「內容廣度」——這兩項要時間
  真正的優勢是「執行速度」和「主題聚焦」——這兩項立刻可用

所以策略應該是：
  用速度換取「在少數幾個問題上做到最好」，
  而不是「在很多問題上做到普通」。
```

### 2. 競品比較頁是小團隊最被低估的武器

```
為什麼大公司不寫「X vs Y」？
  法務怕（比較性廣告的法律風險）
  品牌部怕（不想給對手曝光）
  沒有人有動機（寫這頁的 KPI 是誰的？）

為什麼小公司該寫？
  你本來就是挑戰者，提到領導者是你賺
  「X vs Y」查詢的意圖極明確，轉換率高
  比較表格式的被引用率最高
  誠實的比較（含「什麼時候該用對手」）會建立信任
```

本案例中 `/vs/ngrok` 一頁貢獻了 26% 的引用。

### 3. 開源是最快的「實體建立」手段

小團隊在 Wikidata、媒體報導、產業報告這些傳統實體來源上幾乎沒有機會。但開源不同：

```
一個有用的小套件 = 一次性的 3 人天投入
  → GitHub repo（高權威網域上的品牌提及）
  → npm 頁面（同上）
  → 被其他專案的 package.json 依賴（分散式提及）
  → README 中的作者連結（持續有效）
  → Issue / Discussion（真實使用者的 UGC 討論）
```

**不必開源核心產品**。抽出一個「有用但不構成競爭優勢」的部分就夠了——驗證邏輯、CLI、型別定義、測試工具。

---

## 六、可以直接抄的清單

```
第 1 天（30 分鐘）
□ 跑 ai-crawler-check.sh
□ 關掉 Cloudflare Bot Fight Mode（或等效設定）
□ 手動測 10 題，記下基線

第 1-2 週
□ 一頁式拆成「一頁一問題」的 6-10 頁
□ 每頁：問句標題 + TL;DR + 700-1,200 字 + 更新日期
□ 用 content collection schema 強制 TL;DR 為必填欄位
□ 寫 2-3 頁競品比較（含「什麼時候該用對手」段落）

第 3 週
□ 文件標題全部改成問句
□ 每個錯誤訊息一個獨立段落（原因 + 排查順序）
□ 範例改成完整可執行，不是片段

第 4 週
□ 抽一個小工具開源（MIT，README 寫清楚是誰做的）
□ 發 npm / PyPI / crates.io

持續
□ 每兩週跑一次監測（30 題就夠）
□ 只看兩個數字：引用率、Coverage Gap

明確不要做
✘ 追品類發現題（初期打不贏內容量 50 倍的對手）
✘ 每週發部落格（3 人團隊做不到，薄文章有害）
✘ 買 GEO 工具（自己寫 60 行 Python）
✘ 多語系（除非你的使用者真的不是英文圈）
```

---

*本系列文章：*
- [Part 1：概念篇](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2：原理篇](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3：方法篇](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4：實作篇](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5：量測與案例篇](/posts/aio-geo-part5-measurement-case-study-zh/)
- [Part 6：實戰案例 — 大型企業官網](/posts/aio-geo-part6-case-enterprise-site-zh/)
- [Part 7：實戰案例 — 電商網站](/posts/aio-geo-part7-case-ecommerce-zh/)
- **Part 8（本篇）：實戰案例 — 單頁式產品 Landing Page**
- [Part 9：實戰案例 — 線上課程平台](/posts/aio-geo-part9-case-course-platform-zh/)
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
