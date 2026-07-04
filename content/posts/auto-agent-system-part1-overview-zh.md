---
title: "Auto Agent System - Part 1 - 系統總覽:一個 CrewAI 多代理自動化平台如何運作"
date: 2026-07-04T09:00:00+08:00
draft: false
description: "從 0 認識 agent_auto_system:一個用 CrewAI 打造、能透過 API 與網頁介面定義並執行 AI 自動化任務的平台。本篇拆解它的整體架構、11 種任務類型、最核心的 Harness 引擎層,以及一個請求從按下按鈕到拿到結果的完整資料流。"
categories: ["engineering", "ai", "all"]
tags: ["CrewAI", "AI Agent", "Automation", "FastAPI", "LLM", "Multi-Agent", "AI Engineering", "Harness"]
authors: ["yen"]
readTime: "20 min"
---

> 大部分人寫 AI Agent:把 prompt 丟給 OpenAI SDK,拿到字串,`json.loads()`,能跑就好。
> 出事了才發現:模型偶爾回 markdown 包住的 JSON、偶爾 429、偶爾一本正經地亂編——每個任務都要各自處理一次。
> 這個專案的答案是:把「跟 LLM 打交道的所有髒活」抽成一層 Harness,讓業務邏輯乾乾淨淨。
> 這一系列會帶你從架構總覽,一路讀到它每一個 merged PR 背後的工程決策。

---

本系列以 [yennanliu/agent_auto_system](https://github.com/yennanliu/agent_auto_system) 這個開源專案為主角,一共五篇:

- **Part 1(本篇)**:系統總覽、架構、資料流
- **Part 2**:Harness 引擎——多模型容錯、自我修正、LLM 評審、成本追蹤
- **Part 3**:自動化任務實戰——Shopee 爬蟲、Google Maps 名單、Tasker 自動提案
- **Part 4**:生產化之路——Langfuse 可觀測性、Docker 瘦身、AWS 部署、權限系統
- **Part 5**:前端體驗與 Pipeline 編排——SSE 即時串流、多步驟任務鏈

---

## 一、這個系統到底在做什麼

一句話:**它是一個「AI 自動化任務的執行平台」**。你在網頁上選一個任務(例如「爬 Shopee 賣家」「從 Google Maps 收集潛在客戶名單」「自動幫我在 tasker.com.tw 投標」),填幾個欄位,選一個 LLM 供應商與模型,按下執行——系統就會在背景跑一整個 AI 代理流程,並把進度即時串流回你的畫面。

它不是一個聊天機器人,而是一個**把「重複性的知識工作」變成一鍵可執行任務**的平台。目前內建 11 種任務類型:

```
任務類型                     做什麼
──────────────────────────────────────────────────────────────
google_form_fill        AI 檢視並自動填寫/提交 Google 表單
web_scraper             抓取網址,回傳結構化摘要
google_sheet_reader     讀取公開 Google Sheet,做欄位/統計分析
shopee_seller_scraper   從熱門商品收集賣家清單(最多 100 筆)
profit_health_check     四個 agent 協作,分析 Shopee CSV,輸出 PDF 報告
x_scraper               抓取公開 X(Twitter)帳號的近期貼文
hacker_news_digest      把 HN 熱門文章整理成摘要
email_collect           Google Maps 漏斗:找商家 → 抓 email → 驗證 → 分級
tasker_apply            自動在 tasker.com.tw 投標,AI 撰寫提案文案
email_sender            透過 Gmail SMTP 寄信(非 LLM 任務)
pipeline                把上述任務串成多步驟工作流
```

這些任務背後有一個共同點:**它們都得跟 LLM 打交道,而跟 LLM 打交道本身就充滿不確定性**。這正是整個專案設計的出發點。

---

## 二、核心設計哲學:Harness Engineering

先講一個很多人踩過的坑。

當你只有一個 AI 功能時,程式碼長這樣很正常:

```python
resp = client.chat.completions.create(model="gpt-4o", messages=[...])
data = json.loads(resp.choices[0].message.content)
return data
```

但當你有 **11 種任務、3 家供應商、每個任務都需要重試/驗證/成本追蹤**時,如果每個任務都各寫一遍上面的邏輯,你會得到 11 份互相不一致、各自有 bug 的「跟 LLM 打交道」的程式碼。

這個專案的核心決策是:**把所有跟基礎設施相關的髒活,抽成一層叫 Harness 的東西**,和業務邏輯(「這個任務要做什麼」)徹底分開。

```
        ┌─────────────────────────────────────────────┐
        │            業務邏輯(Flows / Crews)          │
        │   「爬 Shopee」「投標」「分析利潤」——只管做事  │
        └───────────────────────┬─────────────────────┘
                                 │ 完全不碰以下這些
        ┌───────────────────────▼─────────────────────┐
        │                  Harness 層                   │
        │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
        │  │ Provider │ │Validator │ │  Evaluator   │  │
        │  │ 選模型    │ │ 驗證結果  │ │ LLM 評審打分  │  │
        │  └──────────┘ └──────────┘ └──────────────┘  │
        │  ┌──────────┐ ┌──────────────────────────┐   │
        │  │  Costs   │ │  Langfuse Tracer(可觀測) │   │
        │  │ 算 token  │ │  一次 run 一條 trace       │   │
        │  └──────────┘ └──────────────────────────┘   │
        └───────────────────────────────────────────────┘
```

「Harness」原意是「馬具/挽具」——套在馬身上、讓你能安全駕馭一匹力氣很大但不受控的野獸。用來形容 LLM 再貼切不過了。這個譬喻貫穿整個專案,也是我們 Part 2 會深入的重點。

---

## 三、整體架構:從瀏覽器到外部 API

先看全貌,一層一層由上往下:

```
┌───────────────────────────────────────────────────────────┐
│  瀏覽器 UI(需登入)  Vanilla JS + HTML/CSS                  │
│  選任務 → 填表單 → 選模型 → 按執行 → 看即時進度              │
└──────────────────────────┬────────────────────────────────┘
                           │  HTTP / SSE(Server-Sent Events)
┌──────────────────────────▼────────────────────────────────┐
│  FastAPI 後端                                                │
│  routers: auth / admin / jobs / runs / system / uploads    │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────┐
│  Harness Executor 層(central orchestration)               │
│  正規化 → 派發 → 驗證 → 重試 → 評分 → 記錄成本               │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────┐
│  CrewAI:Flows → Crews → Tools                              │
│  每種任務一個 Flow;每個 Crew 由若干 agent 組成              │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────┐
│  外部 API                                                    │
│  OpenAI / Anthropic / Gemini / Gmail / Maps / Playwright   │
└───────────────────────────────────────────────────────────┘
```

技術棧一覽:

| 層 | 技術 | 為什麼 |
|----|------|--------|
| 後端框架 | FastAPI | 原生 async、SSE 支援好、型別友善 |
| 資料層 | SQLModel + SQLite(或 PostgreSQL) | 開發零設定,上線可換 Postgres |
| 代理編排 | CrewAI | 多 agent 協作、內建 crew/task 抽象 |
| 瀏覽器自動化 | Playwright | 需要真的登入/點擊的任務(Shopee、Tasker) |
| PDF 產出 | WeasyPrint | 純 Python、不需要 Chromium(Part 4 會講為什麼) |
| 前端 | Vanilla JS | 無建置步驟,SSE 直接用 EventSource |

值得注意的是:**前端刻意不用 React/Vue**,而是純 Vanilla JS。對一個「內部工具型」平台來說,少一整套 build pipeline、直接用瀏覽器原生的 `EventSource` 接 SSE,反而更輕、更好維護。

---

## 四、CrewAI 的三層抽象:Flow、Crew、Tool

這個專案的業務邏輯全部建立在 CrewAI 上,理解它的三層抽象是關鍵:

```
Flow(流程)
  │  一種任務類型 = 一個 Flow 子類別
  │  掌管「這個任務分幾步、狀態怎麼走」
  ▼
Crew(團隊)
  │  一群 agent 組成的團隊,協作完成一個子目標
  │  例:profit_health_check 有「驗證/分析/建議/彙整」四個 agent
  ▼
Tool(工具)
     可重複使用的能力:web scraper、form inspector、
     email 寄送、maps 查詢……agent 呼叫 tool 去實際做事
```

用 `profit_health_check`(利潤健檢)當例子最清楚。你上傳一份 Shopee 的銷售 CSV,系統跑一個由**四個 agent** 組成的 crew:

```
   CSV 上傳
      │
      ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Agent 1    │──▶│  Agent 2    │──▶│  Agent 3    │──▶│  Agent 4    │
│  資料驗證    │   │  利潤分析    │   │  提出建議    │   │  彙整成報告  │
│ 欄位對不對?  │   │ 毛利/趨勢?  │   │ 該怎麼改善?  │   │ → HTML → PDF │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
                                                              │
                                                              ▼
                                                        PDF 報告下載
```

這裡有一個很細但很重要的工程決策:**Crews 是「純類別」,不用 CrewAI 的 `@CrewBase` 裝飾器**。

為什麼?因為 `@CrewBase` 會做一些快取,導致 LLM 實例被 stale 地快取起來——當你這次 run 想換一個模型時,它可能還在用上一次的。這個專案選擇每次 run 都**重新建一個乾淨的 crew**,把已解析好的 LLM 注入進去,徹底避開這個坑。這種「寧可多花一點建立成本,也要換來可預測性」的取捨,在整個 codebase 隨處可見。

---

## 五、一個請求的完整生命週期

現在把所有東西串起來。假設你要跑一個「爬 Shopee 賣家」的任務,從按下按鈕到看到結果,實際發生了什麼:

```
①  使用者選任務、填表單、選 provider/model,按「執行」
        │
        ▼
②  POST /api/jobs          → 建立一筆 Job 紀錄(存 DB)
    POST /api/jobs/{id}/run → 立刻回 202 Accepted
        │                     並用 asyncio.create_task 把任務丟到背景
        ▼
③  Executor 正規化 provider/model 字串(此時還不建 LLM 實例)
        │
        ▼
④  派發到對應的 Flow;Flow 建一個全新的 CrewAI crew,
    注入解析好的 LLM,開始執行 tools
        │
        ▼
⑤  Validator 檢查結果:欄位齊不齊?內容夠不夠長?
        │
        ├─ 失敗 → 把 previous_error 注入 payload,重跑讓 LLM 自我修正
        └─ 成功 ↓
        ▼
⑥  獨立的 Evaluator(LLM 評審)幫這次輸出打 0–100 分
        │
        ▼
⑦  Executor 記錄所有 harness 指標:token 數、估算美元成本、
    評分、重試次數,寫回 Run 紀錄
        │
        ▼
⑧  SSE 串流(GET /api/runs/{id}/stream)每 0.5 秒推一次最新
    狀態與 log 給 UI,直到任務進入終態
        │
        ▼
⑨  (可選)發出一條 Langfuse trace
        ▼
⑩  依任務類型匯出結果:JSON / CSV / PDF
```

這裡有幾個關鍵設計值得停下來看:

**1. 為什麼 `/run` 立刻回 202,而不是等結果?**

因為一個 AI 任務可能跑 30 秒到好幾分鐘。如果同步等待,HTTP 連線會被卡住、容易 timeout。所以採用「**立即回 202 + 背景 asyncio task + SSE 串流進度**」的非同步模式。任務被註冊在一個 `registry.py` 的 task registry 裡,這樣使用者中途按「取消」時才有辦法真的停掉它。

**2. `normalize()` 和 `resolve()` 為什麼要分兩步?**

```
normalize("gpt4o")  →  ("openai", "gpt-4o")   # 純字串處理,不呼叫 API
resolve(...)        →  建立實際的 CrewAI LLM 物件  # 這步才真的花錢/連線
```

正規化只是把使用者輸入的雜亂字串(`gpt4o`、`GPT-4O`、`gpt-4o`)整理成標準的 `(provider, model)`,**完全不碰網路**。真正建立 LLM 物件的 `resolve()` 延後到最後一刻才做。這讓「驗證輸入是否合法」變得又快又便宜。

**3. SSE 為什麼用「每 0.5 秒 poll DB」而不是用 pub/sub?**

因為進度 log 本來就寫在 DB 裡(用原子性的 SQL `json_insert` append,避免 read-modify-write 的競態)。SSE handler 只要每 0.5 秒讀一次 DB、把新的 log 推給前端就好。對這個規模的系統來說,這比架一套 Redis pub/sub 簡單太多,而且天然就有持久化——就算使用者重新整理頁面,進度也不會消失。

---

## 六、專案結構速覽

熟悉一下目錄,後面幾篇會不斷回來看這些檔案:

```
src/
├── main.py                # FastAPI app、lifespan hooks
├── database.py            # SQLModel engine、migration
├── models.py              # User / Job / Run / Setting 資料表
├── auth.py                # 登入、RBAC 權限控管
├── settings_store.py      # 任務目錄、加密 API key、評審模型設定
├── routers/               # API endpoints
└── automation/
    ├── executor.py        # ★ 中央調度:正規化/派發/驗證/重試/評分
    ├── pipeline.py        # 多步驟 pipeline,支援 {{steps.N.result}} 模板
    ├── progress.py        # 用 SQL json_insert 原子性 append log
    ├── registry.py        # 可取消任務的 asyncio task registry
    ├── report_render.py   # PDF 產出(WeasyPrint)
    ├── harness/           # ★ Provider / Validator / Evaluator / Costs / Langfuse
    ├── flows/             # 每種任務一個 Flow 子類別
    ├── crews/             # 每個任務的 crew(純類別)
    └── tools/             # 可重用工具(爬蟲、表單檢視、email、maps…)

tests/                     # 380 個單元 + 整合測試(26 unit + 10 integration 檔)
ui/                        # HTML、Vanilla JS、CSS
doc/                       # 架構、部署、開發筆記
```

打星號的 `executor.py` 和 `harness/` 是整個系統的心臟,也是 Part 2 的主角。

順帶一提:**380 個測試**對一個個人專案來說是相當高的紀律。CI 分三段——host 層 lint/test、Docker build 跑完整測試、再對 runtime image 做 smoke test。這種「基礎設施可靠度」的重視,和 Harness 的設計哲學是一脈相承的。

---

## 七、權限與管理:不是玩具,是可上線的東西

這個系統從第一天就是「登入才能用」的。第一次啟動會 seed 一個預設 admin(`admin`/`admin`,上線前必須改掉)。Admin 可以:

- 管理使用者
- 指派**每個使用者能用哪些任務**(per-user allowlist)
- 全域開關某個任務類型
- 把加密後的 API key 存在 DB 裡(而不是散落在環境變數)
- 選擇「評審用的 LLM 模型」

```
       ┌──────────┐
       │  Admin   │
       └────┬─────┘
            │ 指派
   ┌────────┼────────┐
   ▼        ▼        ▼
┌──────┐ ┌──────┐ ┌──────┐
│User A│ │User B│ │User C│
│可用: │ │可用: │ │可用: │
│爬蟲   │ │全部  │ │投標   │
│分析   │ │      │ │      │
└──────┘ └──────┘ └──────┘
```

這一整套 auth/admin 設計,我們留到 Part 4 和部署一起講。

---

## 八、小結:為什麼這個專案值得一讀

如果你只想做「一個能跑的 AI Demo」,你不需要這麼多東西。但如果你想做「一個**多人用、多任務、多模型、還要能追成本和品質**的 AI 平台」,這個專案示範了幾個關鍵的工程判斷:

| 判斷 | 這個專案的選擇 | 一般 Demo 的做法 | 差別 |
|------|--------------|----------------|------|
| LLM 打交道的髒活 | 抽成 Harness 層 | 每個功能各寫一遍 | 一致性、可測試性 |
| 任務執行 | 202 + 背景 task + SSE | 同步等待 | 不 timeout、可取消 |
| 進度串流 | poll DB + json_insert | Redis pub/sub | 更簡單、天然持久化 |
| Crew 建立 | 每次重建純類別 | @CrewBase 快取 | 避開 stale LLM |
| 模型解析 | normalize / resolve 分離 | 直接建 client | 驗證快又便宜 |

下一篇 **Part 2**,我們鑽進整個系統的心臟——**Harness 引擎**。你會看到它如何在 LLM 429 時自動換一個 sibling 模型重試、如何在結果驗證失敗時把錯誤訊息餵回去讓 LLM 自我修正、如何用一個獨立的評審模型幫每次輸出打分,以及一個看似無害卻讓無數人踩坑的問題:**LLM 回傳的 JSON 被 markdown code fence 包起來時,你該怎麼優雅地解出來**(這正是這個專案的第一個 PR)。

---

### 系列導覽

- **Part 1(本篇)**:系統總覽、架構、資料流
- Part 2:Harness 引擎——多模型容錯、自我修正、LLM 評審、成本追蹤
- Part 3:自動化任務實戰——Shopee、Google Maps、Tasker
- Part 4:生產化之路——Langfuse、Docker、AWS、權限
- Part 5:前端體驗與 Pipeline 編排

> 專案原始碼:[github.com/yennanliu/agent_auto_system](https://github.com/yennanliu/agent_auto_system)
