---
title: "AIO / GEO - Part 6 - 實戰案例：大型企業官網（多語系 + AWS + 法遵）"
date: 2026-08-02T09:00:00+08:00
draft: false
weight: 6
description: "一家 3,000 人製造業集團的六語系官網，跑在 AWS CloudFront + WAF 上。看 GEO 在大企業環境的真正瓶頸：不是技術，是治理。附 WAF 規則、hreflang 與實體一致性的實作。"
categories: ["AI", "SEO", "GEO", "Case Study", "Engineering", "all"]
tags: ["GEO", "AIO", "企業官網", "AWS", "CloudFront", "WAF", "多語系", "hreflang", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "18 min"
---

> 大企業做 GEO 的難點從來不是「不知道怎麼做」。
> 是「知道怎麼做，但要跑六個部門的簽核」。
>
> 這個案例的技術部分只花了 4 人天。
> 剩下五個月都在處理組織問題。

---

## 一、情境

```
公司      台灣製造業集團，3,000 人，年營收約 NT$210 億
產品      工業自動化零組件（B2B，客戶為系統整合商與 OEM）
網站      6 語系（繁中/簡中/英/日/德/越），約 1,800 頁
CMS       Adobe Experience Manager（AEM）
部署      AWS：S3 + CloudFront + WAF，Route 53 多區域
團隊      IT 部門（不含前端）、行銷部（不懂技術）、法務（很有意見）
```

**業務動機很具體**：海外客戶的採購工程師開始用 ChatGPT 做初步選型。業務回報「客戶說 AI 推薦了三家，沒有我們」。

```
基線量測（40 題 × 3 引擎，2026-02）
────────────────────────────────────
提及率           9%
引用率           2%
描述正確率       31%   ← 模型講的是 2019 年被併購前的舊公司名
Engine Variance  3pp   ← 各引擎一樣糟，所以不是單一引擎的技術問題
Coverage Gap     67%
```

**注意 Engine Variance 只有 3pp**：各引擎表現一致地差，代表不是 CDN 擋人這種局部問題，而是內容本身就不存在或不可用。這和 Part 5 案例 A 完全相反。

---

## 二、部署架構與問題點

```
                    ┌──────────────┐
   使用者 / Bot ───▶ │  Route 53    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  CloudFront  │  ← 問題 ①：地區封鎖
                    │   + AWS WAF  │  ← 問題 ②：Bot Control 全開
                    └──────┬───────┘
                           ▼
              ┌────────────┴────────────┐
              ▼                         ▼
      ┌──────────────┐          ┌──────────────┐
      │  S3（靜態）   │          │  ALB → EC2   │
      │  圖片/PDF     │          │  AEM Publish │  ← 問題 ③：語系用
      └──────────────┘          └──────────────┘     Cookie 判斷
```

三個問題各自的診斷：

### 問題 ①：CloudFront 地區封鎖

公司為了「避免非目標市場的無效流量」，在 CloudFront 的 Geo Restriction 只允許 12 個國家。

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" -A "OAI-SearchBot/1.0" https://example.com/en/
403
```

多數 AI crawler 的出口 IP 集中在美國少數幾個 AS，但也會有其他區域。**Geo Restriction 是一個對 AI crawler 極不友善的設定**，而它通常是行銷部要求、IT 部門執行、沒人記得的。

### 問題 ②：AWS WAF Bot Control

`AWSManagedRulesBotControlRuleSet` 的 `CategoryAI` 規則群組預設 Block。這個規則群組在 2024 年後新增，很多人是在例行更新 managed rule 版本時「自動」被開啟的。

### 問題 ③：語系靠 Cookie / Accept-Language 判斷

```
GET /  →  302 → /zh-tw/  （依 Accept-Language）
Bot 沒有 Accept-Language → 全部被導到 /zh-tw/
→ 英文、日文、德文內容從未被任何 AI crawler 看過
```

**這一個問題就吃掉了 5/6 的內容。**

---

## 三、五個關鍵決策

### 決策 1：Geo Restriction 改成「WAF 條件式」而非 CloudFront 全域

```
不做：直接關閉 Geo Restriction
      → 法遵部門不同意（有出口管制考量）

做：  CloudFront Geo Restriction 關閉，改在 WAF 用 rule 實作，
      並在最高優先權加一條 AI bot 的 Allow
```

WAF 規則順序（Priority 由小到大執行）：

```json
[
  {
    "Name": "AllowVerifiedAIBots",
    "Priority": 0,
    "Action": { "Allow": {} },
    "Statement": {
      "OrStatement": { "Statements": [
        { "ByteMatchStatement": {
            "SearchString": "OAI-SearchBot",
            "FieldToMatch": { "SingleHeader": { "Name": "user-agent" } },
            "PositionalConstraint": "CONTAINS",
            "TextTransformations": [{ "Priority": 0, "Type": "NONE" }] } },
        { "ByteMatchStatement": {
            "SearchString": "Claude-SearchBot",
            "FieldToMatch": { "SingleHeader": { "Name": "user-agent" } },
            "PositionalConstraint": "CONTAINS",
            "TextTransformations": [{ "Priority": 0, "Type": "NONE" }] } },
        { "ByteMatchStatement": {
            "SearchString": "PerplexityBot",
            "FieldToMatch": { "SingleHeader": { "Name": "user-agent" } },
            "PositionalConstraint": "CONTAINS",
            "TextTransformations": [{ "Priority": 0, "Type": "NONE" }] } }
      ]}
    }
  },
  {
    "Name": "GeoBlockNonTargetMarkets",
    "Priority": 10,
    "Action": { "Block": {} },
    "Statement": { "NotStatement": { "Statement": {
      "GeoMatchStatement": { "CountryCodes": ["TW","US","JP","DE","VN","CN","KR","SG","MY","TH","NL","MX"] }
    }}}
  },
  {
    "Name": "AWS-BotControl",
    "Priority": 20,
    "OverrideAction": { "None": {} },
    "Statement": { "ManagedRuleGroupStatement": {
      "VendorName": "AWS", "Name": "AWSManagedRulesBotControlRuleSet",
      "RuleActionOverrides": [
        { "Name": "CategoryAI", "ActionToUse": { "Count": {} } }
      ]
    }}
  }
]
```

三個要點：

- `AllowVerifiedAIBots` 在 Priority 0，**Allow 動作會終止規則評估**，所以 AI bot 完全繞過後面的 Geo 與 Bot Control。
- `CategoryAI` 用 `Count` 而非移除規則——這樣仍能在 CloudWatch 看到流量，但不阻擋。
- 只放**檢索 bot**。訓練 bot（GPTBot / ClaudeBot）由法務決定，最後決議是 robots.txt 允許但不進 WAF 白名單（讓它們走一般路徑，被 rate limit 是可接受的）。

> **UA 偽造的風險**：以上是純 UA 比對，任何人都能偽造。若擔心被濫用，補一層反解驗證（reverse DNS + forward confirm），或用各家公布的 IP 段建 IP set。這個案例評估後認為「假冒 bot 也只是讀到公開內容」，風險可接受。

### 決策 2：語系用路徑，不用 Cookie

```
改前：  /  → 302（依 Accept-Language / Cookie）→ /zh-tw/
改後：  /  → 200，一個真正的語言選擇頁（有內容，不是跳板）
        各語系永遠可直接存取 /en/、/ja/、/de/…
        不對 bot 做任何自動導向
```

搭配完整的 hreflang（AEM 的 page properties 產生）：

```html
<link rel="alternate" hreflang="zh-Hant" href="https://example.com/zh-tw/products/servo/">
<link rel="alternate" hreflang="zh-Hans" href="https://example.com/zh-cn/products/servo/">
<link rel="alternate" hreflang="en"      href="https://example.com/en/products/servo/">
<link rel="alternate" hreflang="ja"      href="https://example.com/ja/products/servo/">
<link rel="alternate" hreflang="de"      href="https://example.com/de/products/servo/">
<link rel="alternate" hreflang="vi"      href="https://example.com/vi/products/servo/">
<link rel="alternate" hreflang="x-default" href="https://example.com/en/products/servo/">
<link rel="canonical" href="https://example.com/zh-tw/products/servo/">
```

**`x-default` 指向英文版**，因為 AI 引擎在處理跨語言查詢時傾向落到英文。

**多語系 GEO 的一個非直覺發現**：改完之後，德文與越南文的引用率成長幅度**遠高於**繁中。原因是這兩個語言的競爭內容少，模型「沒得選」。

```
語系      改前引用率   改後引用率   變化
────────────────────────────────────────
繁中      4%          11%         +7pp
英文      3%          19%         +16pp
日文      1%          14%         +13pp
德文      0%          26%         +26pp   ← 最大
越南文    0%          31%         +31pp   ← 最大
簡中      2%          8%          +6pp
```

**推論**：如果你有小語系市場，那是 GEO 投報率最高的地方。多數競爭者只顧英文。

### 決策 3：實體一致性——先修「公司叫什麼名字」

描述正確率只有 31%，根因是併購後的品牌整併沒有做完：

```
同一家公司，在網路上有五種說法
──────────────────────────────────────────
官網首頁          「XX 精密工業股份有限公司」
英文站            「XX Precision Industrial Co., Ltd.」
LinkedIn          舊名「YY Automation」（併購前）
Crunchbase        舊名 + 舊描述
Wikipedia（英）    停留在 2019 年，寫的是被併購「前」的狀態
公開新聞稿         有時用集團名，有時用子公司名
```

修法（成本低，效果最大的一項）：

```
□ 寫一份 40 字官方定義句，中英日德越簡六版，法務一次審完
□ 更新所有官方帳號的簡介（LinkedIn / Crunchbase / 產業資料庫）
□ Wikidata 條目更新（比 Wikipedia 容易，且 AI 大量使用）
□ 全站 Organization JSON-LD 的 sameAs 串起所有官方存在
□ 新聞稿樣板的 boilerplate 段落統一
```

Organization schema（每個語系各一份，`name` 用當地語言、`@id` 共用）：

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://example.com/#organization",
  "name": "XX 精密工業股份有限公司",
  "alternateName": [
    "XX Precision Industrial", "XX Precision", "XX精密",
    "YY Automation（前身，2019 年併入）"
  ],
  "url": "https://example.com/",
  "description": "XX 精密工業是台灣的工業自動化零組件製造商，生產伺服馬達、線性滑軌與精密減速機，供應系統整合商與 OEM 客戶。成立於 1987 年，2019 年併購 YY Automation，2026 年員工約 3,000 人。",
  "foundingDate": "1987-05-01",
  "sameAs": [
    "https://www.wikidata.org/wiki/Q000000",
    "https://www.linkedin.com/company/xx-precision",
    "https://www.crunchbase.com/organization/xx-precision"
  ],
  "knowsAbout": ["伺服馬達", "線性滑軌", "精密減速機", "工業自動化", "servo motor", "linear guideway"],
  "parentOrganization": { "@type": "Organization", "name": "XX 控股" }
}
```

`alternateName` 裡明確寫出「前身」，是為了讓模型能把舊名的既有知識連到新實體上——這比單純忽略舊名有效得多。

### 決策 4：規格表從 PDF 搬到 HTML

B2B 製造業的通病：**所有有價值的資訊都在 PDF 型錄裡**。

```
改前：/products/servo/ → 一段行銷文字 + 「下載型錄 PDF」按鈕
      → 規格、尺寸、扭矩曲線、料號全在 PDF 中
      → AI crawler 讀得到 PDF，但優先級低於 HTML，且解析品質不穩

改後：HTML 規格表（完整料號 × 參數矩陣）+ PDF 保留供下載
```

```html
<section id="specs" aria-labelledby="h-specs">
  <h2 id="h-specs">XS-400 系列伺服馬達的規格參數是什麼？</h2>
  <table>
    <caption>XS-400 系列規格表（2026 年 3 月版）</caption>
    <thead>
      <tr><th>料號</th><th>額定功率</th><th>額定扭矩</th><th>最高轉速</th><th>編碼器</th><th>防護等級</th></tr>
    </thead>
    <tbody>
      <tr><td>XS-400-A05</td><td>0.5 kW</td><td>1.59 N·m</td><td>3,000 rpm</td><td>23-bit 絕對式</td><td>IP67</td></tr>
      <tr><td>XS-400-A10</td><td>1.0 kW</td><td>3.18 N·m</td><td>3,000 rpm</td><td>23-bit 絕對式</td><td>IP67</td></tr>
      <tr><td>XS-400-A20</td><td>2.0 kW</td><td>6.37 N·m</td><td>2,500 rpm</td><td>23-bit 絕對式</td><td>IP67</td></tr>
    </tbody>
  </table>
  <p class="source">資料來源：XS-400 系列技術手冊 Rev. 4.2（2026-03）。
     完整扭矩曲線與機械圖請見 <a href="/downloads/xs-400-catalog.pdf">PDF 型錄</a>。</p>
</section>
```

搭配 Product schema，讓每個料號成為可被查詢的實體：

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "XS-400-A10 伺服馬達",
  "sku": "XS-400-A10",
  "brand": { "@id": "https://example.com/#organization" },
  "category": "工業自動化 > 伺服馬達",
  "additionalProperty": [
    { "@type": "PropertyValue", "name": "額定功率", "value": "1.0", "unitCode": "KWT" },
    { "@type": "PropertyValue", "name": "額定扭矩", "value": "3.18", "unitText": "N·m" },
    { "@type": "PropertyValue", "name": "防護等級", "value": "IP67" }
  ]
}
```

**這一項貢獻了最大的單筆成長**：長尾料號查詢（「1kW IP67 絕對式編碼器伺服馬達」）從 0 引用變成該類查詢的主要來源。

### 決策 5：法務參與方式——從「審核」改成「預先定義」

這是組織層面最關鍵的一個決定。

```
原本的流程（三個月只改了 4 頁）
  內容部門寫 → 送法務審 → 法務逐字改 → 退回 → 再送 → …

改後的流程（一個月改了 60 頁）
  法務一次性定義：
    ① 可公開揭露的規格欄位白名單（14 個欄位）
    ② 可公開的數字類型（規格 ✔ / 良率 ✘ / 客戶名 ✘ / 產能 ✘）
    ③ 禁止字眼清單（「最佳」「第一」「唯一」等絕對化用語）
    ④ 競品比較的中立框架（不指名，只列選型因素）
  → 內容部門在框架內自由發揮，只有踩線才送審
```

**通則**：在大企業裡，GEO 的瓶頸幾乎一定是流程而非技術。把法務從「每次審核」轉成「一次定義規則」，是解鎖速度的唯一辦法。

---

## 四、結果

```
指標                改前(2026-02)   改後(2026-07)    變化
──────────────────────────────────────────────────────────
提及率              9%             34%             +25pp
引用率              2%             21%             +19pp
描述正確率          31%            89%             +58pp   ← 最大改善
Coverage Gap        67%            24%             -43pp
六語系平均引用率     1.7%           18.2%           ×10.7

商業側
海外詢價表單         41/月          97/月           +137%
其中德/越語系        3/月           28/月           ×9.3
業務回報「客戶說 AI  —              8 次（六個月）   從 0 到有
提到我們」
```

### 投入分解

```
項目                      人天    誰做              備註
──────────────────────────────────────────────────────────────
WAF / CloudFront 調整      2      IT               技術上最簡單
語系路徑改造               6      IT + AEM 廠商     AEM 設定為主
實體一致性（六語系）        4      行銷 + 法務       效果最大
規格表 HTML 化（120 個系列） 22     產品部 + 內容     最耗時
JSON-LD 模板               3      AEM 廠商
監測系統                   3      IT
──────────────────────────────────────────────────────────────
技術合計                   14
內容合計                   26
實際歷時                   6 個月（其中 4.5 個月在等簽核）
```

---

## 五、這個案例的三個 insight

### 1. 大企業的 GEO 分數低，通常是「防禦設定的副作用」

WAF、Geo Restriction、Bot Control、rate limiting——這些設定各自都有正當理由，而且都是不同時間、不同部門加上去的。**沒有任何一個人知道全部**。

```
實務做法：做一次「存取層考古」
  □ 列出所有可能攔截請求的層（DNS / CDN / WAF / LB / App / CMS）
  □ 每一層問：這裡有 UA 或 IP 或地區的判斷嗎？
  □ 每一層問：這個規則是誰、什麼時候、為什麼加的？
  □ 用 curl 逐層驗證，不要看設定檔就下結論
```

### 2. 小語系是被嚴重低估的機會

```
                  競爭密度      GEO 難度     這個案例的成果
─────────────────────────────────────────────────────────
英文              極高          高           +16pp
繁中/簡中          高            中           +6~7pp
日文              中            中           +13pp
德文              中低          低           +26pp
越南文            低            極低         +31pp
```

如果你有小語系市場但只做了機器翻譯、或者根本沒讓 crawler 看到，那是最快的一筆收益。

### 3. 「描述正確率」對 B2B 的重要性高於「引用率」

這家公司的引用率只到 21%（不算高），但描述正確率從 31% 拉到 89%——**業務端的感受主要來自後者**。

```
客戶問 AI「XX 精密的伺服馬達最大扭矩多少？」
  改前：模型講出併購前另一家公司的規格 → 客戶認為產品不符需求，直接排除
  改後：模型講出正確料號與參數 → 客戶進入詢價
```

**在 B2B 領域，被講錯比不被提到更致命**。因為不被提到只是沒機會，被講錯是主動被淘汰。

---

## 六、可以直接抄的清單

```
存取層（AWS）
□ CloudFront Geo Restriction 關閉，改用 WAF 條件式
□ WAF Priority 0 加 AI 檢索 bot 的 Allow rule
□ BotControl 的 CategoryAI 設為 Count 而非 Block
□ CloudWatch 建 AI bot 的 request 指標與告警
□ 用 curl 逐一驗證，不要相信設定檔

多語系
□ 語系用路徑（/en/、/ja/），不要用 Cookie 或 Accept-Language 導向
□ 根路徑要有真實內容，不要是純跳板
□ 完整 hreflang + x-default 指向英文
□ 每個語系有獨立的 Organization schema（共用 @id）
□ 檢查小語系的 crawler 存取——常常只有主語系被測過

實體
□ 一句話定義，各語系一版，法務一次審完
□ 併購/改名的舊名放進 alternateName，並註明關係
□ Wikidata 條目（比 Wikipedia 好推進）
□ 全部官方帳號簡介同步

內容（B2B 製造業特化）
□ 規格表從 PDF 搬到 HTML（PDF 保留供下載）
□ 每個料號一個 Product schema，參數用 additionalProperty
□ 標題改成採購工程師會問的問句
□ 每張表加 caption 與版本日期

組織
□ 法務從「逐案審核」改成「一次定義白名單與禁區」
□ 存取層考古：列出每一層的攔截規則與其來源
□ 監測報表每月進行銷例會，讓 AVS 變成有人負責的數字
```

---

*本系列文章：*
- [Part 1：概念篇](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2：原理篇](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3：方法篇](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4：實作篇](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5：量測與案例篇](/posts/aio-geo-part5-measurement-case-study-zh/)
- **Part 6（本篇）：實戰案例 — 大型企業官網**
- [Part 7：實戰案例 — 電商網站](/posts/aio-geo-part7-case-ecommerce-zh/)
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- [Part 9：實戰案例 — 線上課程平台](/posts/aio-geo-part9-case-course-platform-zh/)
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
