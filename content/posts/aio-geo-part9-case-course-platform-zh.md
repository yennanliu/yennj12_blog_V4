---
title: "AIO / GEO - Part 9 - 實戰案例：線上課程平台（付費牆 + 影片內容）"
date: 2026-08-05T09:00:00+08:00
draft: false
weight: 9
description: "一個 8,000 名付費學員的線上課程平台，跑在 GCP Cloud Run 上。內容 90% 是影片、且全在付費牆後——這是 GEO 最困難的組合。看付費牆怎麼分層、影片怎麼變成可引用文字，以及「開放多少才不會傷害營收」的實測。"
categories: ["AI", "SEO", "GEO", "Case Study", "EdTech", "all"]
tags: ["GEO", "AIO", "線上課程", "付費牆", "Paywall", "GCP", "Cloud Run", "影片字幕", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "18 min"
---

> 「我們的內容都在付費牆後面，GEO 是不是做不了？」
>
> 這是最常見的問題，也是最常見的錯誤前提。
> 付費內容站要問的不是「開不開放」，
> 而是「開放哪一層，才能讓模型有東西引用、又不讓人不用付費」。

---

## 一、情境

```
平台      資料工程 / 後端開發線上課程，繁中為主
規模      8,000 名付費學員，18 門課，1,200 支影片，年營收約 NT$6,000 萬
內容      90% 是影片（平均 12 分鐘）+ 課後練習 + 討論區
技術      Next.js（前台）+ Django（後台）+ PostgreSQL
部署      GCP：Cloud Run（前後台）+ Cloud CDN + Cloud SQL + GCS（影片）
付費      單門課 NT$3,600-6,800，或年費 NT$14,800 全站通行
```

**業務動機**：學員來源高度依賴 FB 廣告與 KOL 合作，獲客成本連續兩年上升（CAC 從 NT$1,900 漲到 NT$3,400）。同時發現學員在課程討論區問的問題，很多人是先去問 AI——但 AI 從沒提過這個平台。

```
基線量測（35 題 × 3 引擎，2026-01）
──────────────────────────────────
提及率            6%
引用率            2%
Coverage Gap      71%
可被 crawler 讀取的內容佔全站    3%   ← 核心問題
```

---

## 二、真正的問題：內容存在，但不可見

```
內容資產盤點
─────────────────────────────────────────────────────
1,200 支影片              付費牆後，且只有影片沒有文字
1,200 份自動字幕（VTT）    存在 GCS，從未公開
      ↑ 這是被完全浪費的資產
340 篇課後練習與解答       付費牆後
2,800 則討論區問答         付費牆後   ← UGC，AI 最愛引用的類型
18 個課程介紹頁            公開，但都是行銷文案
0 篇部落格                 —

可被 AI crawler 讀到的：18 個課程介紹頁 ≈ 全站內容的 3%
```

**關鍵發現**：字幕檔已經存在了。1,200 支影片 × 平均 1,800 字 = **約 216 萬字的技術內容，躺在 GCS 上從來沒被任何人或機器讀過**。

---

## 三、核心決策：付費牆的三層設計

這是整個案例最重要的一個決定，也是所有付費內容站都要面對的問題。

```
                     ╔═══════════════════════════════════╗
                     ║  Layer A：完全公開                  ║
                     ║  目標：被引用、建立權威              ║
                     ╠═══════════════════════════════════╣
                     ║  • 課程大綱（逐單元，含學習目標）    ║
                     ║  • 每支影片的「重點摘要」（200-400 字）║
                     ║  • 每門課 1-2 支完整免費單元         ║
                     ║  • 討論區的「問題 + 第一段解答」      ║
                     ║  • 名詞解釋詞條（從字幕自動抽取）     ║
                     ║  • 課程 FAQ、先修需求、適合對象      ║
                     ╚═══════════════════════════════════╝
                                    │
                     ╔═══════════════════════════════════╗
                     ║  Layer B：預覽（可見前 30%）         ║
                     ║  目標：展示深度，製造缺口感           ║
                     ╠═══════════════════════════════════╣
                     ║  • 影片逐字稿前 30%（然後截斷）      ║
                     ║  • 練習題目（公開）＋ 解答（不公開）   ║
                     ║  • 用 isAccessibleForFree 誠實標註   ║
                     ╚═══════════════════════════════════╝
                                    │
                     ╔═══════════════════════════════════╗
                     ║  Layer C：完全封閉                  ║
                     ║  目標：保護核心價值                  ║
                     ╠═══════════════════════════════════╣
                     ║  • 影片本身                         ║
                     ║  • 完整逐字稿                       ║
                     ║  • 練習解答與程式碼                  ║
                     ║  • 作業批改、助教問答                ║
                     ║  • 證書、社群                       ║
                     ╚═══════════════════════════════════╝
```

**設計原則**：

```
開放「知道有這件事」                  →  Layer A
保留「知道怎麼做」                    →  Layer C
中間放「知道大概怎麼做但缺細節」        →  Layer B
```

一個具體判準：**如果一段內容被完整引用後，讀者就不需要買課了，那它屬於 Layer C。** 但「Kafka 的 consumer group rebalance 會造成什麼問題」這種概念說明屬於 Layer A——知道問題存在，不等於知道怎麼調參解決。

---

## 四、實作

### 決策 1：把字幕變成可引用的頁面（最大的一項）

1,200 份 VTT 字幕 → 1,200 個公開的「單元重點」頁面。

```
處理管線（一次性批次，跑在 Cloud Run Job）

  GCS: /captions/{course}/{lesson}.vtt
            │
            ▼
  ① 清洗：去時間軸、合併斷句、修正 ASR 錯字（術語字典）
            │
            ▼
  ② LLM 生成三種產出：
       a. 重點摘要（200-400 字，Layer A）
       b. 5-8 條 key takeaways（Layer A）
       c. 名詞解釋（抽取本單元出現的技術名詞，Layer A）
            │
            ▼
  ③ 逐字稿前 30% 截斷（Layer B）
            │
            ▼
  ④ 寫回 PostgreSQL，Next.js ISR 渲染
```

```python
# jobs/caption_to_page.py —— Cloud Run Job，一次性處理 1,200 份
import re, json, os
from google.cloud import storage
import anthropic

TERM_FIX = {  # ASR 常錯的技術名詞
    "卡夫卡": "Kafka", "波斯特格雷": "PostgreSQL",
    "達克": "Docker", "庫伯內特斯": "Kubernetes",
}

def clean_vtt(vtt: str) -> str:
    lines = []
    for ln in vtt.splitlines():
        if ln.startswith("WEBVTT") or "-->" in ln or ln.strip().isdigit() or not ln.strip():
            continue
        lines.append(ln.strip())
    text = " ".join(lines)
    for wrong, right in TERM_FIX.items():
        text = text.replace(wrong, right)
    return re.sub(r"\s+", " ", text)


PROMPT = """以下是一支線上課程影片的逐字稿。請產出 JSON，包含：

- "summary": 200-400 字的重點摘要。必須包含逐字稿中出現的具體技術名詞、
  數字、指令與參數。用完整句子，主詞明確（不要用「這個」「它」）。
  這段摘要會被獨立展示，讀者看不到影片，所以必須自成一體。
- "takeaways": 5-8 條 key takeaway，每條 20-40 字，各自可獨立成立。
- "terms": 本單元出現的技術名詞，每個附 30-60 字解釋。
- "questions": 這支影片能回答的 3-5 個具體問題（使用者會怎麼問）。

只輸出 JSON，不要其他文字。

【課程】{course}
【單元】{lesson}
【逐字稿】
{transcript}
"""

def process(course, lesson, transcript):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": PROMPT.format(
            course=course, lesson=lesson, transcript=transcript[:24000])}],
    )
    data = json.loads(re.search(r"\{.*\}", msg.content[0].text, re.S).group())
    # Layer B：逐字稿前 30%
    cut = int(len(transcript) * 0.3)
    data["preview"] = transcript[:cut].rsplit("。", 1)[0] + "。"
    return data
```

**成本**：1,200 支 × 約 8k input + 1.5k output token ≈ **US$78 的一次性費用**。這大概是本系列所有案例中投報率最高的一筆支出。

產出的頁面結構：

```
/courses/data-engineering/lessons/kafka-consumer-group/

  <h1>Kafka Consumer Group 與 Rebalance 機制</h1>
  <p>課程：資料工程實戰 · 第 4 章第 3 節 · 影片長度 14:22</p>

  <section id="summary">
    <h2>這個單元在講什麼？</h2>
    <p>（200-400 字重點摘要，Layer A）</p>
  </section>

  <section id="takeaways">
    <h2>重點整理</h2>
    <ul>（5-8 條，Layer A）</ul>
  </section>

  <section id="questions">
    <h2>這個單元能回答的問題</h2>
    <ul>
      <li>Consumer group rebalance 會造成什麼問題？</li>
      <li>為什麼 session.timeout.ms 設太短會頻繁 rebalance？</li>
      <li>Static membership 什麼時候該用？</li>
    </ul>
  </section>

  <section id="terms">
    <h2>本單元名詞解釋</h2>
    <dl>（Layer A）</dl>
  </section>

  <section id="transcript" class="paywalled">
    <h2>影片逐字稿</h2>
    <p>（前 30%，Layer B）</p>
    <div class="paywall-notice">
      完整逐字稿與影片需要課程權限。<a href="/courses/data-engineering">了解課程</a>
    </div>
  </section>
```

**注意 `<section id="questions">`**：明確列出「這頁能回答哪些問題」。這對 rerank 有直接幫助——它讓 chunk 與使用者查詢的語意距離大幅縮短。這是課程平台特別適合用的一招，因為課程大綱本來就是問題導向的。

### 決策 2：正確標註付費牆（不是偽裝）

```json
{
  "@context": "https://schema.org",
  "@type": ["Article", "LearningResource"],
  "headline": "Kafka Consumer Group 與 Rebalance 機制",
  "isAccessibleForFree": false,
  "hasPart": [
    {
      "@type": "WebPageElement",
      "isAccessibleForFree": true,
      "cssSelector": "#summary, #takeaways, #terms, #questions"
    },
    {
      "@type": "WebPageElement",
      "isAccessibleForFree": false,
      "cssSelector": "#transcript"
    }
  ],
  "learningResourceType": "影片單元",
  "educationalLevel": "中階",
  "teaches": ["Kafka consumer group", "rebalance 調校", "static membership"],
  "isPartOf": {
    "@type": "Course",
    "@id": "https://example.com/courses/data-engineering/#course",
    "name": "資料工程實戰"
  },
  "timeRequired": "PT14M22S"
}
```

課程層級的 Course schema：

```json
{
  "@context": "https://schema.org",
  "@type": "Course",
  "@id": "https://example.com/courses/data-engineering/#course",
  "name": "資料工程實戰：從 ETL 到 Streaming",
  "description": "18 小時、82 個單元的資料工程課程，涵蓋 Airflow、Kafka、dbt 與 Spark，以四個可上線的專案為主軸。適合有 1 年以上後端經驗的工程師。",
  "provider": { "@id": "https://example.com/#organization" },
  "inLanguage": "zh-Hant-TW",
  "teaches": ["Airflow", "Kafka", "dbt", "Spark", "資料建模"],
  "coursePrerequisites": "熟悉 Python 與 SQL；具備 1 年以上後端或資料相關經驗",
  "educationalLevel": "中階",
  "hasCourseInstance": {
    "@type": "CourseInstance",
    "courseMode": "online",
    "courseWorkload": "PT18H"
  },
  "offers": {
    "@type": "Offer",
    "price": "5800", "priceCurrency": "TWD",
    "category": "Paid",
    "availability": "https://schema.org/InStock"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.7", "reviewCount": 412
  },
  "syllabusSections": [
    { "@type": "Syllabus", "name": "第 4 章：Kafka 與串流處理",
      "description": "Kafka 架構、producer/consumer 調校、exactly-once 語意",
      "timeRequired": "PT3H10M" }
  ]
}
```

**為什麼要誠實標註而不是給 bot 看全文**：

```
偽裝的三個問題
  ① 被判定為 cloaking，全站信任度下降
  ② 模型引用了付費內容 → 使用者點進來發現要付費 → 負面體驗
  ③ 你的完整內容進了訓練語料，永久失去控制

誠實標註的收益
  ① 模型知道「這裡有更完整的內容，需要付費」
     → 實際觀察到引擎會在答案中提示「完整內容需訂閱」
  ② Layer A 內容足以被引用，不需要犧牲 Layer C
```

### 決策 3：討論區問答部分公開

2,800 則討論區問答是被低估的資產——**UGC 是 AI 引擎最偏好引用的內容類型之一**。

```
公開策略
  問題全文              ✔ 公開
  講師回答的第一段        ✔ 公開（通常是結論）
  完整回答與程式碼        ✘ 需要課程權限
  提問者身分            匿名化為「學員」
```

```
/qa/why-does-airflow-task-stuck-in-queued/

  <h2>Airflow 的 task 一直卡在 queued 狀態，可能是什麼原因？</h2>

  <p class="qa-meta">來自「資料工程實戰」課程討論區 · 2026-03-14 · 學員提問</p>

  <blockquote class="question">
    我的 DAG 排程時間到了，task 顯示 queued 但一直沒有變成 running，
    scheduler 的 log 也沒有錯誤訊息……
  </blockquote>

  <div class="answer">
    <p><strong>講師回答（節錄）：</strong></p>
    <p>
      task 卡在 queued 最常見的三個原因是：① executor 的 slot 用完了
      （檢查 parallelism 與 dag_concurrency）；② pool 的 slot 被佔滿；
      ③ worker 沒有正常連上 broker。先用
      <code>airflow celery inspect active</code> 確認 worker 狀態，
      再看 <code>airflow pools list</code>……
    </p>
    <div class="paywall-notice">完整解答與排查腳本需要課程權限。</div>
  </div>
```

**這類頁面的引用率是全站最高的**——因為它精確對上了使用者遇到問題時的提問方式。

### 決策 4：GCP 側的實作要點

```
                    ┌──────────────────┐
    Bot / 使用者 ──▶ │  Cloud Load       │
                    │  Balancer         │
                    │  + Cloud Armor    │ ← 檢查點 ①
                    └────────┬──────────┘
                             ▼
                    ┌──────────────────┐
                    │   Cloud CDN       │ ← 檢查點 ②
                    └────────┬──────────┘
                             ▼
              ┌──────────────┴──────────────┐
              ▼                             ▼
     ┌─────────────────┐          ┌─────────────────┐
     │ Cloud Run       │          │ Cloud Run       │
     │ (Next.js 前台)   │          │ (Django API)    │
     └─────────────────┘          └─────────────────┘
```

**檢查點 ①：Cloud Armor**

原本的 preconfigured WAF rule 中，`OWASP CRS` 的某條規則會對高頻的非瀏覽器 UA 打分並封鎖。加一條優先權最高的例外：

```bash
gcloud compute security-policies rules create 100 \
  --security-policy=course-platform-policy \
  --expression='request.headers["user-agent"].contains("OAI-SearchBot") ||
                request.headers["user-agent"].contains("Claude-SearchBot") ||
                request.headers["user-agent"].contains("PerplexityBot") ||
                request.headers["user-agent"].contains("Googlebot")' \
  --action=allow \
  --description="Allow AI retrieval bots"
```

**檢查點 ②：Cloud CDN 的 Vary 與 Cookie**

原本 Cloud Run 對所有回應都帶 `Set-Cookie`（session），導致 Cloud CDN 完全不快取，且部分 bot 的請求被導向登入流程。

```python
# Django middleware：對公開路徑不設 session cookie
PUBLIC_PREFIXES = ("/courses/", "/qa/", "/glossary/", "/blog/")

class NoSessionForPublicPaths:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.path.startswith(PUBLIC_PREFIXES)
                and not request.user.is_authenticated):
            response.cookies.clear()
            response["Cache-Control"] = "public, max-age=300, s-maxage=3600"
            response["Vary"] = "Accept-Encoding"   # 不要 Vary: Cookie
        return response
```

**Next.js 側**：確保 Layer A 內容走 SSG/ISR，只有 Layer B/C 的權限判斷在 request 時做。

```tsx
export const revalidate = 3600

export default async function LessonPage({ params }) {
  // Layer A：建置期就有，所有人（含 bot）都看得到
  const lesson = await getLessonPublicData(params.slug)

  return (
    <article>
      <PublicSections lesson={lesson} />
      {/* Layer B/C：client component，依權限決定顯示 */}
      <PaywalledTranscript lessonId={lesson.id} preview={lesson.preview} />
    </article>
  )
}
```

---

## 五、結果

```
指標                改前(2026-01)   改後(2026-07)   變化
──────────────────────────────────────────────────────
提及率              6%             41%            +35pp
引用率              2%             27%            +25pp
Coverage Gap        71%            18%            -53pp
可被讀取的內容佔比    3%             34%            ×11

被引用的頁面類型
  討論區 QA 頁                     38%   ← 最高
  單元重點頁                       31%
  名詞解釋詞條                     14%
  課程介紹頁                       11%
  其他                             6%

商業側
自然流量（含 AI referral）  4,200/月   19,800/月   ×4.7
試聽轉付費率               2.1%       2.4%        +0.3pp
新學員數                   210/月     385/月      +83%
CAC                       NT$3,400   NT$2,050    -40%   ← 核心成果
```

**最重要的數字是 CAC 下降 40%**。因為新增的學員大多來自自然流量而非付費廣告。

### 那個所有人都在擔心的問題：營收有沒有被吃掉？

```
擔心：公開摘要 → 使用者看完摘要就不買課了

實測（對比 6 個月的同期資料）
  現有學員的續訂率        87% → 88%    無變化
  單門課的完課率          62% → 63%    無變化
  客訴「內容外流」        0 件
  發現盜版逐字稿          0 件（Layer C 從未公開）

  「看了摘要頁後購買」的轉換率   3.8%
  「直接進課程介紹頁」的轉換率   2.4%
  → 讀過摘要頁的人反而更容易買
```

**原因很直觀**：200-400 字的摘要能證明「這門課真的講到細節」，但完全無法取代 14 分鐘的影片教學。**摘要是最好的試聽。**

### 投入分解

```
項目                        人天    費用
────────────────────────────────────────────────
字幕處理 pipeline            6      US$78（LLM 一次性）
單元頁模板 + ISR             4
討論區公開化（含匿名化）      5
Course / LearningResource   2
  schema
Cloud Armor + CDN 修正       2
名詞詞條頁自動生成            3
監測系統                    2
────────────────────────────────────────────────
合計                        24 人天 + 約 US$120
```

---

## 六、三個 insight

### 1. 付費內容站的資產通常已經存在，只是沒有被渲染

```
盤點時要問的問題
  □ 影片有字幕嗎？→ 那就是文字內容
  □ 有討論區嗎？→ 那就是 UGC
  □ 有課後練習嗎？→ 題目可以公開，解答不用
  □ 有課程大綱嗎？→ 那本來就是問題清單
```

這個案例的 216 萬字字幕，在改造前的價值是零。

### 2. 「開放摘要會吃掉營收」是錯的前提

實測的三個發現：

```
① 讀過摘要頁的訪客，購買轉換率比直接進介紹頁的高 58%
② 摘要無法取代教學——它展示深度，不傳遞技能
③ 真正該保護的是 Layer C（完整逐字稿、解答、程式碼），
   而這些從頭到尾都沒有公開
```

**判準**：一段內容如果被完整引用後讀者就不用付費了，才屬於 Layer C。多數人把這條線劃得太保守，結果是整站不可見。

### 3. 討論區 QA 是課程平台最強的 GEO 資產

```
為什麼？
  ① 問題是使用者用自己的話問的 → 天然對上檢索查詢
  ② 有具體錯誤訊息、版本號、環境 → 高度可接地
  ③ 是 UGC → AI 引擎偏好真實經驗
  ④ 量大且持續增長 → 零邊際內容成本

做法
  問題全文公開 + 回答第一段公開 + 完整解答付費
  匿名化提問者
  每則獨立成頁，標題就是問題本身
```

本案例中討論區 QA 頁佔了 38% 的引用，而它的內容成本是零——那些回答本來就寫了。

---

## 七、可以直接抄的清單

```
內容分層（先做這個決定，其餘都是執行）
□ Layer A（公開）：大綱、單元摘要、takeaways、名詞、能回答的問題、
                   1-2 支免費單元、討論區問題 + 回答首段
□ Layer B（預覽）：逐字稿前 30%、練習題目
□ Layer C（封閉）：影片、完整逐字稿、解答、程式碼、社群
□ 判準：完整引用後讀者就不用付費 → Layer C，否則往上放

字幕轉內容
□ 清洗 VTT（去時間軸 + 術語字典修正 ASR 錯字）
□ LLM 批次生成 summary / takeaways / terms / questions
□ 摘要要求「主詞明確、自成一體」（chunk 獨立性）
□ 明列「這個單元能回答的問題」
□ 成本抓 US$0.06-0.10 / 支影片

Schema
□ Course（含 syllabusSections、coursePrerequisites、offers）
□ 每單元 LearningResource + isAccessibleForFree
□ hasPart + cssSelector 明確標出付費區塊
□ 絕不給 bot 看付費內容（cloaking 的代價遠大於收益）

討論區
□ 每則 QA 獨立成頁，標題即問題
□ 問題全文 + 回答首段公開
□ 提問者匿名化
□ 標註課程來源與日期

GCP
□ Cloud Armor 加 AI bot 的 allow rule（優先權最高）
□ 公開路徑不下 session cookie，Vary 不含 Cookie
□ 公開內容走 SSG/ISR，權限判斷放在 client component
□ Cloud CDN 對公開路徑設 s-maxage

驗證
□ 用 curl -A "OAI-SearchBot" 確認：Layer A 看得到、Layer C 看不到
□ 每月抽查：模型有沒有洩漏 Layer C 內容
```

---

*本系列文章：*
- [Part 1：概念篇](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2：原理篇](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3：方法篇](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4：實作篇](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5：量測與案例篇](/posts/aio-geo-part5-measurement-case-study-zh/)
- [Part 6：實戰案例 — 大型企業官網](/posts/aio-geo-part6-case-enterprise-site-zh/)
- [Part 7：實戰案例 — 電商網站](/posts/aio-geo-part7-case-ecommerce-zh/)
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- **Part 9（本篇）：實戰案例 — 線上課程平台**
- [Part 10：實戰案例 — 私有 Repo 與內部知識庫](/posts/aio-geo-part10-case-internal-rag-zh/)
- 商業篇：[Part 11 市場](/posts/aio-geo-part11-market-landscape-zh/) ｜ [Part 12 GEO vs SEO 判斷](/posts/aio-geo-part12-geo-vs-seo-decision-zh/) ｜ [Part 13 顧問方法論](/posts/aio-geo-part13-consulting-playbook-zh/) ｜ [Part 14 產業劇本](/posts/aio-geo-part14-industry-playbooks-zh/) ｜ [Part 15 工具與技術棧](/posts/aio-geo-part15-tools-stack-zh/) ｜ [Part 16 規模化](/posts/aio-geo-part16-scaling-the-business-zh/)
