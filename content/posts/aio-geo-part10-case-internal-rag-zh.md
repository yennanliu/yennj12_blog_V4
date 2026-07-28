---
title: "AIO / GEO - Part 10 - 實戰案例：私有 Repo 與內部知識庫（把 GEO 反過來用）"
date: 2026-08-06T09:00:00+08:00
draft: false
weight: 10
description: "最後一個案例沒有搜尋引擎。一家 400 人公司把 GEO 的原則用在自己的內部 AI 助手上——私有 repo、Confluence、Slack 全接進 RAG，答案卻錯得離譜。診斷結果和公開網站一模一樣：內容不是不存在，是不可引用。"
categories: ["AI", "GEO", "Case Study", "Engineering", "RAG", "all"]
tags: ["GEO", "RAG", "內部知識庫", "Vertex AI Search", "Bedrock", "Confluence", "文件工程", "案例研究", "繁體中文"]
authors: ["yen"]
readTime: "19 min"
---

> 前九篇都在講怎麼讓外部引擎引用你。
> 這一篇反過來：你自己就是那個引擎。
>
> 有趣的地方在於——當你能看到檢索管線的每一層時，
> 會發現「內容不可引用」的原因，和公開網站一字不差。

---

## 一、情境

```
公司      B2B 金融科技，400 人（工程 180 人）
背景      2026 年初上線內部 AI 助手，接 Slack
資料源    GitHub Enterprise（86 個 private repo）、Confluence（4,200 頁）、
          Notion（部分團隊）、Slack 歷史訊息、Jira、Google Drive
技術      GCP：Vertex AI Search（as RAG 檢索層）+ Gemini/Claude 生成
          文件同步用 Cloud Run Job + Cloud Scheduler
使用者    全體員工，尖峰每日約 900 次查詢
```

**問題**：上線三個月後，工程團隊的使用率從第一週的 71% 掉到 12%。

```
內部滿意度調查（n=142）
──────────────────────────────────────────────
「答案正確」            23%
「答案有引用來源」       61%
「引用的來源是對的」     31%   ← 關鍵
「比自己搜尋快」        34%
「我已經不用了」        58%

最常見的自由填答：
  「它引用了一份 2022 年的舊 RFC，那個架構早就換掉了」
  「它把 staging 的設定當成 production 講」
  「它從一個廢棄的 repo 抓答案」
  「引用連結點進去看不到它講的那句話」
```

**「引用的來源是對的」只有 31%** ——這和 Part 6 那家製造業的「描述正確率 31%」是同一個數字，也是同一類問題。

---

## 二、關鍵洞察：內部 RAG 的失敗模式，和公開 GEO 完全同構

把 Part 2 的六階段管線套上去：

```
階段            公開 GEO 的失敗                內部 RAG 的失敗
──────────────────────────────────────────────────────────────────────
① Query        用詞和使用者不同                內部黑話 vs 文件正式用語
   fan-out                                   （「風控引擎」vs「RiskSvc」）

② Retrieval    crawler 被擋 / 未索引           權限過濾掉了 / 同步器沒接到
                                              / 二進位檔案沒解析

③ Rerank       整頁只有一段相關                Confluence 頁面 8,000 字，
                                              主題混雜，chunk 被稀釋

④ Grounding    沒有可接地的事實                文件寫「參考 XXX 的做法」，
                                              沒有具體值

⑤ Citation     被用了但沒標來源                引用到 anchor 不存在的位置

⑥ 查核         網域信任不足                    沒有「哪份文件是權威版本」
                                              的訊號 ← 內部特有、且最嚴重
```

**第六項是內部 RAG 獨有的killer**：公開網路上有 PageRank、有網域權威、有時間訊號；內部知識庫裡，一份 2022 年的過期 RFC 和一份昨天更新的架構文件，**在檢索器眼中是平等的**。

---

## 三、診斷：三個具體發現

### 發現 1：46% 的 chunk 來自「應該被刪掉的文件」

```python
# 分析：對 200 個真實查詢，記錄每次被檢索到的 top-10 chunk 來源
# 然後標註每份來源文件的狀態

來源文件狀態          被檢索到的 chunk 佔比
────────────────────────────────────────────
現行有效                        54%
已被取代但未刪除                 21%   ← 過期 RFC、舊架構文件
草稿 / 未完成                    12%
個人筆記（誤放進共享空間）         8%
已廢棄專案的 repo                5%
────────────────────────────────────────────
應該被排除的合計                 46%
```

**這不是 AI 的問題，是知識庫從來沒有人整理過。** 上線 RAG 只是讓這個長期問題第一次變得可見。

### 發現 2：Confluence 頁面的平均長度是 6,200 字，且主題混雜

```
典型的 Confluence 頁面
「支付服務 - 架構與維運」（9,400 字）
  ├─ 架構圖與元件說明
  ├─ 本地開發環境設定
  ├─ 部署流程
  ├─ 監控與告警
  ├─ 常見故障排除
  ├─ 2023 年的遷移紀錄（歷史，已不適用）
  └─ 待辦事項與 TODO

問題：任何一個具體問題（「支付服務怎麼部署？」）
      在這頁的 rerank 分數都很低——因為整頁只有 12% 相關。
      而且「2023 年遷移紀錄」那一段可能被當成現況引用。
```

### 發現 3：程式碼 repo 的 chunk 幾乎無法接地

```
被檢索到的 code chunk 的問題
──────────────────────────────────────────────
沒有檔案路徑上下文        chunk 只有函式本體，不知道在哪個 repo/服務
沒有版本 / branch 資訊    可能是三年前的 feature branch
註解稀少                 純程式碼的語意檢索效果差
測試檔案與正式碼混在一起   引用到 mock 的設定值當成真實設定
```

---

## 四、解法：把 GEO 的四層模型翻譯成內部版本

```
公開 GEO                        內部 RAG 對應
────────────────────────────────────────────────────────────────
Layer 1 技術層                  同步管線與權限
  「crawler 拿得到內容嗎」   →    「同步器接到了嗎、權限過濾對嗎」

Layer 2 結構層                  metadata 與 chunk 邊界
  「JSON-LD、標題層級」     →    「front matter、標題分節、來源標註」

Layer 3 內容層                  文件寫作規範
  「chunk 獨立、可接地」    →    完全相同的規則

Layer 4 實體層                  權威訊號
  「網域權威、sameAs」      →    「哪份是 source of truth」← 最關鍵
```

### 決策 1：建立「權威訊號」——這是內部 RAG 最重要的一件事

公開網路有 PageRank，內部沒有。**所以你必須自己造一個。**

做法：所有納入索引的文件必須有 front matter，並用它計算檢索加權。

```yaml
---
doc_id: svc-payment-arch
title: 支付服務架構
status: active          # active | deprecated | draft | historical
authority: canonical    # canonical | reference | notes
owner: team-payments
reviewed_at: 2026-06-18
review_cycle_days: 180
supersedes: [rfc-0042, svc-payment-arch-v1]
applies_to:
  env: [production]
  version: ">=3.2"
tags: [payment, architecture, backend]
---
```

同步管線依此計算 boost，並直接排除不該出現的內容：

```python
# jobs/index_sync.py —— Cloud Run Job，每 6 小時跑一次
from datetime import date, timedelta

STATUS_BOOST = {
    "active": 1.0,
    "reference": 0.6,
    "draft": 0.2,
    "deprecated": 0.0,     # 0 = 完全排除
    "historical": 0.0,
}
AUTHORITY_BOOST = {"canonical": 1.0, "reference": 0.7, "notes": 0.35}


def freshness_factor(reviewed_at: date, cycle_days: int) -> float:
    """過了 review 週期就開始衰減，兩倍週期後降到 0.3。"""
    age = (date.today() - reviewed_at).days
    if age <= cycle_days:
        return 1.0
    over = (age - cycle_days) / cycle_days
    return max(0.3, 1.0 - 0.7 * min(over, 1.0))


def compute_boost(fm: dict) -> float:
    s = STATUS_BOOST.get(fm.get("status", "draft"), 0.2)
    if s == 0.0:
        return 0.0
    a = AUTHORITY_BOOST.get(fm.get("authority", "notes"), 0.35)
    f = freshness_factor(fm["reviewed_at"], fm.get("review_cycle_days", 365))
    return round(s * a * f, 3)


def should_index(fm: dict, path: str) -> tuple[bool, str]:
    if fm.get("status") in ("deprecated", "historical"):
        return False, "status excluded"
    if not fm.get("owner"):
        return False, "no owner"          # 無主文件一律不索引
    if "/archive/" in path or "/wip/" in path:
        return False, "archived path"
    if compute_boost(fm) < 0.15:
        return False, "boost below threshold"
    return True, ""
```

**「無主文件一律不索引」這一條爭議最大，效果也最大。** 它強迫每份文件有人負責，也自動排除了個人筆記。

推到 Vertex AI Search 時把 boost 帶進 structData：

```python
from google.cloud import discoveryengine_v1 as de

def to_document(doc_id, content, fm, boost):
    return de.Document(
        id=doc_id,
        struct_data={
            "title": fm["title"],
            "status": fm["status"],
            "authority": fm["authority"],
            "owner": fm["owner"],
            "reviewed_at": fm["reviewed_at"].isoformat(),
            "boost": boost,
            "env": fm.get("applies_to", {}).get("env", []),
            "source_url": fm["source_url"],
        },
        content=de.Document.Content(raw_bytes=content.encode(), mime_type="text/plain"),
    )

# 查詢時套用 boost spec
boost_spec = de.SearchRequest.BoostSpec(
    condition_boost_specs=[
        de.SearchRequest.BoostSpec.ConditionBoostSpec(
            condition='status: ANY("active") AND authority: ANY("canonical")', boost=0.5),
        de.SearchRequest.BoostSpec.ConditionBoostSpec(
            condition='authority: ANY("notes")', boost=-0.3),
    ]
)
```

> AWS Bedrock Knowledge Bases 的等價做法：把同樣的欄位寫進 `.metadata.json` 伴隨檔，查詢時用 `retrievalConfiguration.vectorSearchConfiguration.filter` 過濾 `status`，並在 rerank 階段用 metadata 排序。概念完全相同。

### 決策 2：文件切分——把 Confluence 大頁拆成單一主題頁

和 Part 7 電商、Part 8 landing page 的結論一字不差：**主題單一的 1,000 字勝過主題混雜的 9,000 字。**

```
改前
  「支付服務 - 架構與維運」（9,400 字，7 個主題）

改後
  svc-payment/architecture.md      架構與元件（1,200 字）
  svc-payment/local-dev.md         本地開發環境怎麼設定？（800 字）
  svc-payment/deploy.md            怎麼部署支付服務？（1,100 字）
  svc-payment/monitoring.md        有哪些監控與告警？（900 字）
  svc-payment/runbook.md           常見故障怎麼排除？（1,800 字）
  archive/2023-migration.md        status: historical（不索引）
```

`runbook.md` 的寫法特別重要——它是內部 RAG 命中率最高的文件類型：

```markdown
---
doc_id: svc-payment-runbook
status: active
authority: canonical
owner: team-payments
reviewed_at: 2026-07-01
review_cycle_days: 90
---

# 支付服務故障排除

## 告警 `PaymentServiceHighLatency` 觸發時怎麼處理？

**症狀**：P99 延遲超過 800ms 持續 5 分鐘。

**最常見原因（依發生頻率）**
1. 下游銀行 API 逾時（佔歷史事件的 62%）
2. 資料庫連線池耗盡（21%）
3. 對帳批次作業與線上流量爭用（11%）

**排查順序**
1. 看 Grafana dashboard `payment-svc-overview` 的
   `downstream_bank_latency` panel。若該值同步升高 → 原因 1，
   聯絡窗口見下方。
2. 檢查 `pgbouncer_pool_waiting` 是否 > 0 → 原因 2，
   執行 `kubectl scale deploy/payment-svc --replicas=12`。
3. 確認當下是否為 02:00-04:00 的對帳窗口 → 原因 3，可等待。

**升級路徑**：15 分鐘內未緩解 → #payment-oncall → Payments TL。

**下游銀行窗口**：見 `svc-payment/contacts.md`（需 VPN）。
```

這份文件符合 Part 3 的九條規則裡的每一條——問句標題、答案前置、具體數字、明確主詞、可原句搬用。**內部文件和公開內容的「可引用性」要求是相同的。**

### 決策 3：程式碼索引要帶上下文

純程式碼 chunk 幾乎無法被有效檢索。解法是在索引前包裝上下文：

```python
# 索引 code chunk 前，前置一段自動生成的上下文標頭
def wrap_code_chunk(repo, path, symbol, code, git_meta):
    header = f"""[Repository] {repo}
[File] {path}
[Symbol] {symbol}
[Branch] {git_meta['default_branch']}
[Last modified] {git_meta['last_commit_date']} by {git_meta['last_author']}
[Service] {infer_service(repo, path)}
[Is test] {'yes' if is_test_path(path) else 'no'}
"""
    return header + "\n```" + lang_of(path) + "\n" + code + "\n```"
```

排除規則同樣重要：

```python
EXCLUDE_PATTERNS = [
    "**/node_modules/**", "**/vendor/**", "**/*.min.js",
    "**/test/fixtures/**",        # mock 設定會被當成真實設定
    "**/*.pb.go", "**/generated/**",
    "**/migrations/**",           # 歷史 migration 常誤導
]
EXCLUDE_REPOS_IF = lambda r: (
    r["archived"] or
    r["pushed_at"] < eighteen_months_ago or
    r["default_branch_commits_last_90d"] == 0
)
```

**`test/fixtures` 這一條救了很多錯誤答案**——助手原本會把測試用的假 API endpoint 當成真實設定講出來。

### 決策 4：讓答案帶出「權威等級」與「新鮮度」

這是內部 RAG 相對於公開引擎的優勢：**你可以控制答案的呈現方式**。

```
系統 prompt 中加入的規則：

「每個引用必須標註來源文件的 status、owner 與 reviewed_at。
 若最高權重的來源 reviewed_at 距今超過其 review_cycle_days，
 必須在答案開頭警告：『注意：主要來源已超過審閱週期』。
 若找不到 authority=canonical 的來源，必須明說
 『我找不到權威文件，以下答案來自參考性文件，請向 <owner> 確認』。」
```

實際輸出的樣子：

```
支付服務的部署流程是透過 ArgoCD，從 main 分支自動同步到 staging，
production 需要在 #payment-deploy 頻道由 TL 手動核准後才會 sync。

來源：
  [1] svc-payment/deploy.md  ✅ canonical · team-payments · 審閱於 2026-07-01（22 天前）
  [2] platform/argocd.md     📘 reference · team-platform · 審閱於 2026-05-14（70 天前）
```

**這個小改動讓「引用的來源是對的」這項滿意度從 31% 跳到 78%**——不是因為檢索變準，而是因為使用者能自己判斷該不該信。**降低錯誤的傷害，和降低錯誤率一樣有價值。**

### 決策 5：把文件品質變成可量測的分數

複用 Part 4 的 `geo-audit.py` 概念，改成內部版本，跑在文件 repo 的 CI 上：

```python
# ci/doc_audit.py —— 對每份文件打分，低於門檻則 PR 失敗
CHECKS = [
    ("has_front_matter",  lambda d: bool(d.fm),                          25),
    ("has_owner",         lambda d: bool(d.fm.get("owner")),             20),
    ("reviewed_recently", lambda d: d.days_since_review < d.cycle * 1.5, 15),
    ("question_headings", lambda d: d.question_heading_ratio >= 0.4,     10),
    ("single_topic",      lambda d: d.word_count < 2500,                 10),
    ("has_concrete_data", lambda d: d.number_density >= 0.5,             10),
    ("no_orphan_pronoun", lambda d: d.orphan_para_ratio < 0.25,           5),
    ("links_resolve",     lambda d: d.broken_link_count == 0,             5),
]
```

搭配一個每週自動發到各 team channel 的報表：

```
📊 team-payments 文件健康度（2026-07-22）

  文件數                 34
  平均分數               76（上週 71）
  超過審閱週期            6 份  ← 需處理
  無 owner               0 份
  被 AI 助手引用次數      412 次（全公司第 2）
  引用後被使用者標記為     4 次（1.0%，全公司平均 3.2%）
    「答案錯誤」

  ⚠️ 超過審閱週期的文件：
     svc-payment/contacts.md      逾期 41 天
     svc-payment/local-dev.md     逾期 12 天
     ...
```

**「被引用次數」讓文件維護第一次有了可見的回報**。原本沒有人想寫文件，因為看不到效果；現在工程師會為了「我的 runbook 被引用了 412 次」而主動更新。

---

## 五、結果

```
指標                          改前(2026-03)  改後(2026-08)
──────────────────────────────────────────────────────────
「答案正確」滿意度              23%           74%
「引用的來源是對的」            31%           78%
「我已經不用了」                58%           9%
每日查詢數                     110（衰退中）  1,340
工程團隊週活躍率                12%           81%

檢索品質
  來自 deprecated/draft 的 chunk  46%          3%
  平均 chunk 字數                 1,850        620
  top-5 命中率（人工標註 200 題）   34%          81%

文件側
  有 front matter 的文件          8%           94%
  有 owner 的文件                 22%          94%
  超過審閱週期的文件               71%          18%
  平均文件長度                    6,200 字      1,400 字

商業側（估算）
  平均每次查詢節省時間             —            8.5 分鐘（自陳）
  每月節省人時                    —            約 190 小時
  新人 onboarding 到第一次 PR      18 天        11 天
```

### 投入分解

```
項目                              人天
────────────────────────────────────────────
Front matter 規範 + 遷移工具        6
文件拆分（Confluence → repo）      28   ← 最大宗，各團隊分攤
Boost / 過濾邏輯                   5
Code chunk 上下文包裝              4
答案呈現改造（權威標註）             2   ← 投報率最高
doc_audit CI + 週報                6
────────────────────────────────────────────
合計                              51 人天（跨 6 個團隊，3 個月）
```

**注意「答案呈現改造」只花了 2 人天，卻貢獻了滿意度提升的最大一塊。**

---

## 六、三個 insight

### 1. 內部 RAG 的問題 95% 是文件問題，不是模型問題

```
團隊原本的假設：換更好的模型、調 chunk size、加 reranker
實際的根因：    46% 的內容根本不該被索引

投入 vs 回報
  換模型 / 調參數        投入大，回報 < 5pp
  文件治理與拆分         投入大，回報 > 40pp
  答案呈現改造           投入 2 人天，回報 > 20pp
```

**在動模型之前，先量「被檢索到的 chunk 有多少來自不該存在的文件」。** 這個數字通常會讓人震驚。

### 2. 內部知識庫沒有 PageRank，你必須自己造權威訊號

這是公開 GEO 與內部 RAG 最大的差異，也是最容易被忽略的一點。

```
公開網路的天然訊號          內部要自己造的
────────────────────────────────────────────────
外部連結數量               status（active / deprecated）
網域年齡與權威              authority（canonical / reference / notes）
更新頻率                   reviewed_at + review_cycle_days
被其他來源交叉引用           supersedes 關係鏈
搜尋點擊回饋               「答案錯誤」標記回饋
```

沒有這些，你的檢索器會平等對待一份 2022 年的廢棄 RFC 和昨天的架構文件——**而 LLM 會很有自信地引用錯的那一份**。

### 3. 「可引用性」是一種通用的內容品質，不是 SEO 技巧

這是整個系列最重要的收斂點。

```
同一組規則，在三種完全不同的場景下都成立：

  公開網站 GEO              內部 RAG                 給人讀
  ─────────────────────────────────────────────────────────
  chunk 獨立成立         →  chunk 獨立成立        →  段落自成一體
  主詞明確               →  主詞明確              →  不用讀上文
  問句式標題             →  問句式標題            →  好找
  具體數字取代形容詞      →  具體數字取代形容詞     →  可執行
  標註日期與方法          →  reviewed_at          →  知道還準不準
  單一主題               →  單一主題              →  不用滑很久
  比較表                 →  比較表                →  一眼看懂
```

**寫得好的文件，同時對人、對外部引擎、對自家 RAG 都好。** 反過來說，如果你為了 GEO 做的事會讓人類讀者變痛苦，那多半是做錯了。

---

## 七、可以直接抄的清單

```
先量這三個數字（做任何事之前）
□ 被檢索到的 chunk 中，來自 deprecated/draft/無主文件的比例
□ 平均文件長度與主題數
□ 人工標註 100-200 題的 top-5 命中率

Layer 1：管線與權限
□ 確認每個資料源真的被同步到（不要相信設定，要抽查）
□ 排除 archived repo、18 個月未推送的 repo
□ 排除 test/fixtures、generated、migrations、vendor
□ 權限過濾在檢索層做，不要在生成層做

Layer 2：metadata 與 chunk
□ 強制 front matter：doc_id / status / authority / owner /
  reviewed_at / review_cycle_days / supersedes / applies_to
□ 無 owner 的文件不索引
□ status 為 deprecated / historical 的完全排除
□ boost = status × authority × freshness
□ code chunk 前置上下文標頭（repo / path / branch / 最後修改）

Layer 3：文件寫作
□ 一份文件一個主題，目標 800-1,500 字
□ 標題用問句
□ 答案放段落第一句
□ 主詞明確（不要「這個服務」，要寫名字）
□ 數字、指令、參數具體到可以直接複製
□ runbook 用「症狀 → 最常見原因（附比例）→ 排查順序 → 升級路徑」

Layer 4：權威訊號與回饋
□ supersedes 建立取代關係鏈
□ 答案中標註 status / owner / reviewed_at
□ 找不到 canonical 來源時明說，並指出該問誰
□ 「答案錯誤」回報按鈕，回饋到文件健康度報表
□ 每週把「被引用次數」發給各 team——讓寫文件有回報

CI
□ doc_audit 分數門檻，低於則 PR 失敗
□ 超過審閱週期自動開 Jira ticket 給 owner
```

---

## 八、系列收尾

十篇走完，五個場景（企業官網、電商、Landing Page、課程平台、內部知識庫），技術堆疊從 AEM/AWS、Shopify/Vercel、Astro/Cloudflare、Django/GCP 到 Vertex AI Search，規模從 3 人到 3,000 人。

**收斂出來的東西只有三句話：**

1. **先確認內容抵達得了。** 五個案例中有四個，第一個發現的問題都是「內容根本沒被讀到」——WAF、Bot Control、CSR、付費牆、同步器漏接。這一層的修復成本通常是幾小時到幾天，效果卻是 0 到 1。

2. **以 chunk 為單位寫作。** 從 12,000 個商品頁到 4,200 頁 Confluence，同一條規則反覆勝出：主題單一的 1,000 字，勝過主題混雜的 8,000 字。

3. **可接地才會被引用。** 數字、日期、來源、明確的主詞。沒有這些，你的內容會在 grounding 階段被靜靜丟掉——而你永遠不會知道發生過。

剩下的都是這三件事在不同環境下的變形。

---

*本系列文章：*
- [Part 1：概念篇](/posts/aio-geo-part1-concepts-zh/) ｜ [Part 2：原理篇](/posts/aio-geo-part2-how-engines-work-zh/) ｜ [Part 3：方法篇](/posts/aio-geo-part3-strategies-zh/) ｜ [Part 4：實作篇](/posts/aio-geo-part4-implementation-zh/) ｜ [Part 5：量測與案例篇](/posts/aio-geo-part5-measurement-case-study-zh/)
- [Part 6：實戰案例 — 大型企業官網](/posts/aio-geo-part6-case-enterprise-site-zh/)
- [Part 7：實戰案例 — 電商網站](/posts/aio-geo-part7-case-ecommerce-zh/)
- [Part 8：實戰案例 — 單頁式產品 Landing Page](/posts/aio-geo-part8-case-landing-page-zh/)
- [Part 9：實戰案例 — 線上課程平台](/posts/aio-geo-part9-case-course-platform-zh/)
- **Part 10（本篇）：實戰案例 — 私有 Repo 與內部知識庫**
