---
title: "AIO / GEO - Part 15 - 商業化：工具地圖與該自建的部分"
date: 2026-08-11T09:00:00+08:00
draft: false
weight: 15
description: "GEO 工具市場已經很擁擠，但九成的工具只做同一件事：給你 dashboard。本篇畫出完整工具地圖、比較商業與開源選項、給出自建 vs 買的分界線，並提醒一個 2026 年 9 月生效、會改變所有人前提的變動：Cloudflare 對新網域預設封鎖 AI 爬蟲。"
categories: ["AI", "GEO", "Business", "Engineering", "all"]
tags: ["GEO", "AIO", "工具", "開源", "Cloudflare", "監測", "技術棧", "繁體中文"]
authors: ["yen"]
readTime: "20 min"
---

> 大多數人的做法：買一個 GEO 監測工具，看著 dashboard 的數字，然後不知道要做什麼。
> 真正該做的事：先分清楚「量測工具」和「執行能力」——前者可以買，後者不能。
>
> 這個市場上九成的產品都在賣前者。
> 而客戶付錢是為了後者。

---

## 一、先講一件會改變前提的事

**2026 年 7 月 1 日，Cloudflare 宣布：從 9 月 15 日起，新註冊的網域將預設封鎖 AI 訓練與 agent 類爬蟲。** 同時所有方案（含免費版）都能在後台依類別允許或封鎖 AI 爬蟲。

這件事對 GEO 生意的三個直接影響：

```
影響                                   你該做什麼
──────────────────────────────────────────────────────────────────
① 新網域的預設值從「開放」變成「封鎖」    所有新客戶的第一步檢查
   → Part 1 §9 的 Level 0 會變成常態     變得更重要，不是更不重要

② 「檢索 bot」與「訓練 bot」的分類       學會 Cloudflare 的
   由 CDN 廠商定義，不再只看 UA          bot 類別定義，
                                       別只教客戶改 robots.txt

③ Cloudflare 推出託管 robots.txt 與      這是免費送到客戶手上的
   「內容使用層級」（Immediate /          工具。你的價值必須在
   Reference / Full）                    這之上，不是重複它
```

**對顧問的實際意義**：存取層的檢查與設定，正在從「需要專業知識」變成「後台勾選」。你不能再靠「我幫你解除 CDN 封鎖」收費太久——那一項會在 12 個月內變成常識。

**護城河要往上移**：內容層、產業縱深、基準資料（Part 11 §6）。

---

## 二、工具地圖：六個類別

```
╔═══════════════════════════════════════════════════════════════╗
║ ① 可見度監測（最擁擠，也最容易被取代）                           ║
║   問模型 → 記錄引用 → 畫趨勢圖                                 ║
║   商業：Profound / Peec / Otterly / 數十家                     ║
║   開源：Gego / OneGlanse / geo-aeo-tracker                    ║
║   自建：Part 5 §4 的 300 行 Python                            ║
╠═══════════════════════════════════════════════════════════════╣
║ ② 爬蟲存取驗證（低調但最關鍵）                                  ║
║   商業：Cloudflare AI Crawl Control（免費）、各 CDN 的 bot 報表 ║
║   自建：Part 2 §2 的 ai-crawler-check.sh                      ║
╠═══════════════════════════════════════════════════════════════╣
║ ③ 結構化資料                                                   ║
║   Schema Markup Validator、Rich Results Test、                ║
║   schema-dts（TypeScript 型別）                               ║
╠═══════════════════════════════════════════════════════════════╣
║ ④ 內容稽核                                                     ║
║   商業：多數 SEO 工具已加 GEO 分數（可信度低）                    ║
║   自建：Part 4 §7 的 geo-audit.py                             ║
╠═══════════════════════════════════════════════════════════════╣
║ ⑤ 日誌分析（AI crawler 行為）                                   ║
║   商業：Cloudflare Logpush、各 CDN analytics                   ║
║   自建：Part 5 §5 的 awk 一行式 + BigQuery                     ║
╠═══════════════════════════════════════════════════════════════╣
║ ⑥ 執行層（真正稀缺的，幾乎沒有工具）                              ║
║   改 CDN 規則、寫 SSR、部署 schema 模板、重寫內容                 ║
║   → 這是人的工作，不是工具的工作                                 ║
╚═══════════════════════════════════════════════════════════════╝
```

**九成的市場注意力在 ①，而客戶付錢的價值在 ⑥。** 這個錯配就是顧問的機會。

---

## 三、商業監測工具

以下為 2026 年 7 月的公開資訊。**價格與功能變動極快，且多數比較文章是工具商自己寫的（Part 11 §1），提案前請自行複核。**

```
工具        起價（2026-07）   引擎覆蓋   定位            適合誰
──────────────────────────────────────────────────────────────────────
Profound    US$499/月        10+       企業級，最深的    大企業內部團隊、
                                       分析層           大型 agency

Peec AI     €89/月起         8+        中型市場，       中型客戶的
                                       競品份額分析      月報主力

Otterly     US$49/月起       6         入門，簡單       小客戶、
                                       上手快           自己想試的人

（另有數十家新進者，功能高度同質化）
```

> 資料來源為多篇工具比較文章，其中部分由工具商自行發布。
> 搜尋結果中出現的「Fortune 500 市佔 68.4%」「年增 347%」這類
> 精確到小數點的市佔數字，**沒有可驗證的方法論，建議忽略**。
> 這正是 Part 11 §1 講的現象。

### 商業工具真正的價值與局限

```
值得付錢的地方                     不值得付錢的地方
────────────────────────────────────────────────────────────
AI Overview 的抓取                 「問模型並記錄答案」
  （沒有官方 API，自己做很痛）        → 這是 300 行 Python

跨客戶的 dashboard 與權限管理        競品追蹤
  （agency 場景）                   → 你自己的腳本也能做

歷史資料的長期保存與趨勢             「GEO 分數」這類黑箱指標
                                   → 演算法不透明，
                                     無法向客戶解釋

給客戶看的成品報表                   內容建議
  （美觀度有商業價值）                → 目前多數工具的建議
                                     停留在「加 FAQ」等級
```

**一個實務組合**：用商業工具處理 AI Overview 與客戶端報表，用自建腳本處理其餘的一切。

---

## 四、開源選項

搜尋可得的幾個專案（2026 年 7 月）：

```
專案                    語言/棧                  規模      授權      定位
────────────────────────────────────────────────────────────────────────────
AI2HU/gego              Go + Vue 3 +            81 stars  GPL-3.0   排程跑 prompt、
                        PostgreSQL/MongoDB                          抓引用、
                        + etcd + Docker                             品牌別名追蹤
                        引擎：OpenAI / Anthropic /
                        Gemini / Perplexity Sonar / Ollama
                        + 可插拔自訂 provider

aryamantodkar/          真實瀏覽器自動化          —         MIT       用真的瀏覽器開
  oneglanse             （非 API）                                    ChatGPT/Gemini/
                        含 AI Overview                                Perplexity/Claude，
                                                                     抓實際渲染結果

danishashko/            local-first dashboard    —         —         本機優先，
  geo-aeo-tracker       6 個模型                                      資料不外流
```

### 三者的關鍵差異：API vs 真實瀏覽器

```
                API 方式（gego、Part 5 的腳本）    瀏覽器方式（oneglanse）
──────────────────────────────────────────────────────────────────────────
量到的是         API 帶 web_search 工具的結果      使用者實際看到的畫面
與真實使用者     有落差（模型版本、系統 prompt、    一致
的一致性         個人化都不同）
AI Overview     ✘ 沒有 API                       ✔ 可以抓
穩定性          高                                低（UI 改版就壞）
被封鎖風險       無（付費 API）                     有（自動化存取）
成本            API 費用（每輪 US$8-19）            機器成本 + 維護
可規模化         ✔                                 △
合規            明確                              各家 ToS 態度不一，
                                                  需自行評估
```

**建議**：**API 方式當主軸**（穩定、可規模化、合規清楚），**AI Overview 用商業 SERP API 或人工抽查補足**（Part 5 §4.4）。瀏覽器自動化只在你需要驗證「API 結果與真實畫面的落差」時偶爾用。

> 上述開源專案為 2026 年 7 月的搜尋結果，星數與活躍度都不高，
> 屬於早期專案。採用前務必自行檢視 commit 頻率、issue 回應與
> 授權條款（gego 是 GPL-3.0，**若你要包進商業產品要特別注意**）。

---

## 五、自建 vs 買：分界線

```
                        自建                    買
──────────────────────────────────────────────────────────────
問模型並記錄引用          ✔ 300 行 Python         ✘ 沒必要付錢
                        完全掌控、可客製

AI Overview 抓取         ✘ 反爬蟲維護成本高        ✔ SERP API
                                               US$50-300/月

多客戶 dashboard         △ 值得，若客戶數 > 8      ✔ 客戶數 < 8 時買
與權限                                          比較划算

歷史資料保存             ✔ SQLite/BigQuery        △ 綁定廠商，
                        資料是你的護城河           退出時帶不走
                        （Part 11 §6 護城河 ②）

爬蟲存取驗證             ✔ 20 行 bash            ✘ 沒必要付錢
                                               （Cloudflare 免費給）

內容稽核                 ✔ Part 4 的 geo-audit   △ 商業工具的
                        規則你可以自己定義          規則是黑箱

客戶報表美化             △ 花時間                 ✔ 買，或用
                                               現成 BI 工具
```

### 判斷原則

```
會變成你的護城河的 → 自建
  · 基準資料庫（跨客戶的產業對照）← 最重要
  · 產業 prompt set
  · 內容稽核規則

只是節省時間的 → 買
  · AI Overview 抓取
  · 報表美化
  · 早期的多客戶管理

千萬不要買的
  · 「AI 內容生成 + 自動發布」——大量薄內容會傷害客戶
  · 黑箱的「GEO 分數」——你無法向客戶解釋的數字，
    不要放進報告
```

---

## 六、非監測類工具（常被忽略但更實用）

```
用途                    工具                              備註
──────────────────────────────────────────────────────────────────────
爬蟲存取驗證             自寫 bash（Part 2 §2）             20 行，最該先做
                        Cloudflare AI Crawl Control       免費，含 robots.txt
                                                          合規追蹤

Schema 驗證             Schema Markup Validator           權威來源
                        Rich Results Test
                        schema-dts（npm）                  TypeScript 型別，
                                                          寫 JSON-LD 不會拼錯

無 JS 渲染檢查           curl + 文字抽取（Part 4 §9）        最快
                        Puppeteer/Playwright 對照          需要精確比對時

站點爬取與稽核           Screaming Frog                     可自訂抽取 JSON-LD、
                        Sitebulb                          批次檢查

日誌分析                CDN 原生 analytics                 先用免費的
                        Logpush → BigQuery                量大時再上

內容稽核                geo-audit.py（Part 4 §7）          規則自己定，
                                                          可放進 CI

字幕／影片轉文字          Whisper（開源）                    Part 9 的 pipeline
                        各家 ASR API

批次內容處理             LLM API 直接呼叫                    Part 9：1,200 支
                                                          影片摘要僅 US$78
```

**`schema-dts` 值得單獨提一句**：它讓 JSON-LD 在編譯期就能檢查型別，避免最常見的錯誤（欄位拼錯、型別錯誤、@type 不存在）。對要維護數十個客戶模板的 agency 很實用。

---

## 七、一套 agency 交付工具鏈

```
                    ┌──────────────────────────┐
                    │  客戶清單 / 產業標籤        │
                    │  （Airtable / Notion）     │
                    └────────────┬─────────────┘
                                 ▼
        ┌────────────────────────────────────────────┐
        │  prompt set 庫（依產業分類，git 版控）        │
        │  → 新客戶從產業模板 fork，改 20%             │
        └────────────────────┬───────────────────────┘
                             ▼
   ┌─────────────────────────────────────────────────────┐
   │  排程 runner（GitHub Actions / Cloud Scheduler）      │
   │  每週跑：所有客戶 × prompt set × 3 引擎                │
   │  → Part 5 §4 的 geo_monitor.py，多租戶化              │
   └─────────────────────────┬───────────────────────────┘
                             ▼
        ┌────────────────────────────────────────────┐
        │  資料層（BigQuery / Postgres）               │
        │  一列 = (客戶, 日期, 引擎, 題目, 結果)         │
        │  ← 這裡就是你的護城河                        │
        └────────────────────┬───────────────────────┘
                    ┌────────┴────────┐
                    ▼                 ▼
        ┌──────────────────┐  ┌──────────────────────┐
        │ 客戶月報（自動）    │  │ 內部基準分析          │
        │ Metabase/Looker  │  │ 「這個產業中位數是多少」│
        │ Studio → PDF     │  │ → 提案的殺手鐧        │
        └──────────────────┘  └──────────────────────┘

        另外兩條獨立管線：
        ┌──────────────────────────────────────────┐
        │ 每週：geo-verify.py 跑所有客戶的關鍵頁面    │
        │ → 任何 bot 從 200 變 403 就發告警          │
        │ → 這個告警救過很多案子（客戶改了 CDN 沒說）  │
        └──────────────────────────────────────────┘
        ┌──────────────────────────────────────────┐
        │ 每次 PR：geo-audit.py 進客戶的 CI          │
        │ → 新內容不符規範就擋下                     │
        └──────────────────────────────────────────┘
```

### 建置成本與順序

```
階段            建什麼                          人天   什麼時候做
──────────────────────────────────────────────────────────────────
客戶 1-2        Part 5 的單機腳本 + Excel        2     現在
客戶 3-5        多租戶資料表 + 排程               5     第 3 個客戶時
客戶 6-10       自動月報 + crawler 告警           8     第 6 個客戶時
客戶 10+        基準分析 + prompt set 庫版控      10    第 10 個客戶時
──────────────────────────────────────────────────────────────────
合計                                            25 人天，分四次投入
```

**不要一開始就建完整系統。** 前兩個客戶用 Excel 完全沒問題，而且你會在過程中發現真正需要的欄位。

---

## 八、為什麼選 X 不選 Y

```
選擇                    選 X 的理由                    不選 Y 的理由
──────────────────────────────────────────────────────────────────────────
自建監測                 資料是護城河（Part 11 §6 ②）    純買商業工具：
+ 買 SERP API           規則透明可向客戶解釋            資料綁在廠商，
vs 純買商業工具          邊際成本趨近於零                退出時帶不走；
                                                     黑箱分數無法解釋

翻轉條件：客戶數 < 3 且沒有工程時間——先買，等有量再自建。

──────────────────────────────────────────────────────────────────────────
API 方式監測             穩定、可規模化、合規明確         瀏覽器自動化：
vs 瀏覽器自動化                                         UI 改版就壞、
                                                     ToS 風險、
                                                     難以規模化

翻轉條件：需要抓 AI Overview，或需要驗證「API 結果 vs 真實畫面」的落差時，
         用瀏覽器方式做小規模抽查。

──────────────────────────────────────────────────────────────────────────
自訂稽核規則             規則你能解釋、能依產業調整       商業工具的 GEO 分數：
（geo-audit.py）        能放進客戶的 CI                黑箱、無法客製、
vs 商業工具的分數                                      客戶問「為什麼是 62 分」
                                                     你答不出來

翻轉條件：沒有。放進客戶報告的每個數字，你都要能解釋它怎麼算的。

──────────────────────────────────────────────────────────────────────────
Cloudflare 原生工具      免費、就在客戶後台、             自己寫 CDN 管理層：
vs 自建 CDN 管理         官方維護                       重複造輪子，
                                                     且 Cloudflare 會一直加功能

翻轉條件：客戶用的不是 Cloudflare（AWS WAF、Akamai、自架 Nginx）——
         那就需要 Part 4 §2 的手工設定。

──────────────────────────────────────────────────────────────────────────
GPL 開源專案僅內部使用    可以自由改、不用開源你的修改      包進商業 SaaS 產品：
vs 包進你的產品                                        GPL-3.0 的傳染性條款
                                                     會要求你開源

翻轉條件：使用 MIT/Apache 授權的專案時沒有這個限制——採用前一定要看授權。
```

---

## 九、評估一個新 GEO 工具的六個問題

這個市場每個月都有新工具。用這六題快速篩掉九成。

```
① 它量的是什麼？用什麼方法？
   → 答不出方法論的，直接跳過
   → 特別問：是 API 還是瀏覽器？跑幾次取平均？

② 它的「分數」怎麼算？
   → 黑箱分數不要放進客戶報告

③ 資料能匯出嗎？格式是什麼？
   → 不能匯出 = 你的歷史資料被綁架

④ 它涵蓋 AI Overview 嗎？怎麼抓的？
   → 這是商業工具唯一難以自建的部分。
     如果它也沒有，那它相對於自建的優勢就很少

⑤ 它有沒有「執行」的部分，還是只有 dashboard？
   → 九成只有 dashboard

⑥ 這家公司的部落格在賣什麼？
   → 如果它的「市場數據」文章讀起來像 GEO 內容農場，
     它的產品品質通常也對應
```

---

## 十、一句話總結

```
可以買的：時間（AI Overview 抓取、報表美化、早期的多客戶管理）
不能買的：判斷（哪些題目重要、哪個產業天花板多高、
              這個客戶該不該做）
不該買的：黑箱分數、自動生成內容
必須自建的：基準資料庫 —— 它是唯一無法被複製的東西
```

**工具會一直商品化，判斷不會。** 這一篇列的所有商業工具，兩年後可能有一半消失、剩下的降價八成。而你手上那份「這個產業做過 12 家，引用率中位數 28%」的資料，兩年後只會更值錢。

---

## 資料來源

Sources:
- [Cloudflare changes AI crawler access rules — Help Net Security（2026-07-02）](https://www.helpnetsecurity.com/2026/07/02/cloudflare-ai-crawler-controls/)
- [Bot reference — Cloudflare AI Crawl Control docs](https://developers.cloudflare.com/ai-crawl-control/reference/bots/)
- [Control content use for AI training with Cloudflare's managed robots.txt — Cloudflare Blog](https://blog.cloudflare.com/control-content-use-for-ai-training/)
- [Easily manage AI crawlers with our new bot categories — Cloudflare Blog](https://blog.cloudflare.com/ai-bots/)
- [AI2HU/gego — GitHub](https://github.com/AI2HU/gego)
- [aryamantodkar/oneglanse — GitHub](https://github.com/aryamantodkar/oneglanse)
- [danishashko/geo-aeo-tracker — GitHub](https://github.com/danishashko/geo-aeo-tracker)
- [Otterly vs Profound vs Peec: GEO Tools 2026 — Georion](https://georion.app/blog/otterly-vs-profound-vs-peec-geo-tools-2026)
- [Best GEO Tools in 2026: Monitoring vs Execution, Tested — Okara](https://okara.ai/blog/best-geo-tools)

---

*本系列文章：*
- 基礎篇：[Part 1 概念](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2 原理](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3 方法](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4 實作](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5 量測](/posts/aio-geo-part5-measurement-case-study-zh/)
- 案例篇：[Part 6 企業官網](/posts/aio-geo-part6-case-enterprise-site-zh/) ｜ [Part 7 電商](/posts/aio-geo-part7-case-ecommerce-zh/) ｜ [Part 8 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/) ｜ [Part 9 課程平台](/posts/aio-geo-part9-case-course-platform-zh/) ｜ [Part 10 內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
- 商業篇：[Part 11 市場](/posts/aio-geo-part11-market-landscape-zh/) ｜ [Part 12 GEO vs SEO 判斷](/posts/aio-geo-part12-geo-vs-seo-decision-zh/) ｜ [Part 13 顧問方法論](/posts/aio-geo-part13-consulting-playbook-zh/) ｜ [Part 14 產業劇本](/posts/aio-geo-part14-industry-playbooks-zh/) ｜ **Part 15（本篇）工具與技術棧** ｜ [Part 16 規模化](/posts/aio-geo-part16-scaling-the-business-zh/)
