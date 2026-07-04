---
title: "Auto Agent System - Part 4 - 生產化之路:Langfuse 可觀測性、Docker 瘦身與 AWS 部署"
date: 2026-07-04T12:00:00+08:00
draft: false
description: "AI 系統能跑,離能上線還很遠。本篇拆解 agent_auto_system 把自己推向生產的四個關鍵決策:在 executor 這個漏斗掛上 Langfuse trace(PR #19)、用 WeasyPrint 換掉 Chromium 讓 Docker image 瘦身(PR #9)、規劃 AWS ECS Fargate 部署(PR #10),以及完整的登入與 RBAC 權限系統(PR #11)。"
categories: ["engineering", "ai", "all"]
tags: ["Langfuse", "Observability", "Docker", "AWS", "ECS", "Deployment", "RBAC", "AI Engineering", "LLMOps"]
authors: ["yen"]
readTime: "22 min"
---

> 「在我電腦上跑得起來」和「能給一群人用」之間,隔著四道牆:
> 你看得到它在做什麼嗎(可觀測性)?它打包起來多大、部署多快(image)?
> 它能自動擴縮、掛了會自己重啟嗎(部署)?誰能用、能用什麼由誰決定(權限)?
> 這一篇,就是 agent_auto_system 翻過這四道牆的過程。

---

前三篇我們把系統的「能力」講完了:架構(Part 1)、可靠性引擎(Part 2)、實戰任務(Part 3)。這一篇談的是另一個維度——**生產化(productionization)**:讓這套系統能被真實地、多人地、可維運地跑起來。四個主題,對應四個 merged PR。

---

## 一、Langfuse 可觀測性:在唯一的漏斗上掛 trace

> 對應 **PR #19**:`feat(harness): add Langfuse LLM-observability integration`

Part 2 我們反覆強調:LLM 的「錯」不是當機,而是品質退化——HTTP 200,但答案是編的。你需要一種能看見「品質」的監控,這就是 LLM 可觀測性,而 Langfuse 是這個領域的代表工具。

這個 PR 最漂亮的地方,是它的 **PR 描述本身就是一堂架構課**:

> 「CrewAI 1.x 直接呼叫各家原生 provider SDK(不走 litellm),所以要把 Langfuse 掛在 **executor**——這個已經知道 model、tokens、cost、eval score、status 的**唯一漏斗**。」

拆解這句話為什麼重要:

```
   很多人以為的 Langfuse 接法:
   在「LLM 呼叫的那一行」自動攔截(靠 litellm 之類的中介層)

   但 CrewAI 1.x 直接打原生 SDK,沒有那個中介層可攔
        │
        ▼
   聰明的做法:不在「呼叫點」攔,而在「執行點」記
        │
        ▼
   executor 是所有任務的必經之路,而且它手上早就有:
   model + tokens + cost + eval score + status
   → 在這裡發一條 trace,一次到位、還帶品質分數
```

```
┌─────────────────────────────────────────────────┐
│  executor.run()                                   │
│    ...跑完任務、算完成本、評完分...                │
│    ┌──────────────────────────────────────────┐  │
│    │  langfuse_tracer.trace(                    │  │
│    │     model, input, output,                  │  │
│    │     tokens, cost, eval_score, status)      │  │
│    │  一次 run = 一條 trace                       │  │
│    └──────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────┘
                       ▼
              ┌─────────────────┐
              │  Langfuse UI     │  搜尋、過濾、看每次
              │  Trace + Score   │  run 的品質趨勢
              └─────────────────┘
```

### 三個設計亮點

**1. Provider 無關(provider-agnostic)。** 不管這次用 OpenAI、Anthropic 還是 Gemini,trace 的發送邏輯完全一樣——因為它是在 executor 這個統一層記錄的,不在各家 SDK 裡。這就是 Part 1「把基礎設施關注點抽到共用漏斗」哲學的又一次勝利。

**2. 用環境變數控制、非阻塞。** 沒設 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 就不發 trace,系統照跑。發 trace 這件事**絕不能拖慢或搞垮主流程**——可觀測性是加值,不能變成新的故障點。

**3. trace 裡帶了 eval score。** 這是關鍵:因為 executor 早就跑過 Part 2 的 Evaluator,它手上有品質分數。於是每條 trace 不只記「用了多少 token」,還記「這次輸出幾分」。你可以在 Langfuse 裡直接問:「這週哪個任務的平均分數掉了?」

### 為什麼掛在 executor 而不是各 Flow?

```
選擇              掛在 executor 的理由              掛在各 Flow 的問題
────────────────────────────────────────────────────────────────
單一漏斗          11 種任務只需接一次;              11 個地方各接一次,
                  自動拿到 cost/score/status         漏一個就有盲區,還拿
                                                    不到 eval score
provider 無關     不管哪家 SDK 都一樣                各 Flow 要各自處理
```

這一整套接法,也正是我在 [Langfuse 入門系列](/yennj12_blog_V4/posts/langfuse-intro-part1-concepts-zh/)談的「在對的地方埋 trace」的實例。

---

## 二、Docker 瘦身:用 WeasyPrint 換掉 Chromium

> 對應 **PR #9**:`chore(docker): swap Chromium PDF for WeasyPrint to slim the image`

Part 3 埋了個伏筆:利潤健檢的 PDF 是怎麼生的?最初的做法是**用 Chromium(無頭瀏覽器)把 HTML 印成 PDF**——這是很常見的手法,渲染品質也好。

問題是:**為了印一個 PDF,你得在 Docker image 裡塞一整顆 Chromium。**

```
   之前:HTML → 無頭 Chromium 渲染 → PDF
        │
        └─ 代價:Docker image 裡要裝整個瀏覽器
                 → 幾百 MB 的體積
                 → build 慢、pull 慢、冷啟動慢

   之後:HTML → WeasyPrint(純 Python 函式庫)→ PDF
        │
        └─ 只需 Pango / Cairo 這些系統函式庫
                 → runtime image 瘦到 ~450 MB
```

### 這是一個典型的「工具過重」問題

Chromium 是為了「跑整個網頁應用」而生的巨獸。而你只是要「把一段 HTML 排版成 PDF」——這是它能力的九牛一毛。用 Chromium 印 PDF,就像**開一台聯結車去買一杯咖啡**。

```
選擇          用 WeasyPrint 的理由             不繼續用 Chromium 的理由
────────────────────────────────────────────────────────────────
WeasyPrint    純 Python,只需 Pango/Cairo;     Chromium:幾百 MB;
(純函式庫)   image 小、build 快、             build/pull/冷啟動都慢;
              冷啟動快;無瀏覽器程序管理         還要管瀏覽器程序生命週期
```

### 什麼時候 Chromium 才是對的選擇?

這個取捨有它的**翻轉條件**。如果你的 PDF 需要:

- 執行 JavaScript(例如前端動態產生的圖表)
- 複雜的現代 CSS(flexbox/grid 的刁鑽 layout、web fonts)
- 對「跟瀏覽器裡看到的一模一樣」有像素級要求

那 Chromium 的重量就是值得的。但對「報表型 PDF」(表格、數字、簡單樣式)來說,WeasyPrint 的 HTML/CSS 支援綽綽有餘,而省下的體積是每一次 build、每一次部署、每一次冷啟動都在受益的。

**這個 PR 的意義**:別因為「大家都這樣做」就扛一個過重的依賴。先問「我真正需要它的哪一部分能力?」——常常有更輕的工具剛好夠用。

---

## 三、AWS ECS Fargate 部署:先寫設計,再動手

> 對應 **PR #10**:`docs: add AWS ECS Fargate deployment design (phase 1)`

注意這是一個 **docs PR**——它先把「怎麼部署到 AWS」的設計寫清楚,標明是 **phase 1**。這種「設計先行、分階段」的紀律,本身就值得學。

### 為什麼選 ECS Fargate,而不是 EC2 或 Kubernetes?

這是容器部署最常見的三選一:

```
選項              適合                          這個專案為何(暫時)不選
────────────────────────────────────────────────────────────────
EC2 自己管         要極致調校、要 GPU、           要自己管 OS patch、
                  要省成本且流量穩定             擴縮、健康檢查——維運重
ECS Fargate ✅    「給我一個 container,         (就是選它)
                  剩下別煩我」;無伺服器、
                  按用量付費、自動擴縮
EKS/K8s           多服務、複雜編排、             對單一應用是殺雞用牛刀,
                  已有 K8s 團隊                  營運複雜度爆增
```

對一個「單一容器化應用、團隊小、想把心力放在功能而非維運」的專案,**Fargate 是幾乎不用想的選擇**:你交出一個 image,AWS 幫你跑、幫你擴縮、幫你重啟,你不碰任何一台 VM。

**翻轉條件**:當你有多個互相依賴的服務、需要精細的網路策略、或團隊已經在跑 K8s 時,EKS 才開始划算;當你需要 GPU 或流量極穩定且想壓成本時,EC2 才回到桌面。

### 這時 Part 2 的設計回收了

還記得 Part 1 提過的兩個細節嗎?它們在 Fargate 上直接變成優勢:

```
① 啟動時的 stale run 回收(startup reconciliation)
   容器被 Fargate 重啟時,把上次沒跑完、卡在 running/pending
   的紀錄標記為 failed → 不會有殭屍任務
        ↑ 這在「容器隨時可能被換掉」的雲端環境是必需品

② 豐富的 /health endpoint
   回報 DB 連線、各 provider 金鑰是否設定
        ↑ Fargate/ALB 的健康檢查靠它判斷「這個 container 活著嗎」
```

**這就是「為部署而設計」的體現**:stale run 回收和 health check 不是上線前臨時補的,而是架構裡本來就有的——因為作者一開始就假設「容器是短命的、隨時會被重啟」。

### 三個持久化 volume

Fargate 的容器本身是無狀態的,但這個應用有三種資料要留住:

```
/app/data     ── SQLite DB(或改接 RDS PostgreSQL)
/app/uploads  ── 使用者上傳的 CSV
/app/reports  ── 產出的 PDF 報告
```

上雲時,這三個通常會換成託管服務(DB → RDS、檔案 → S3/EFS),但設計上已經把「哪些是狀態、要放哪」切得很乾淨。

---

## 四、Auth 與 RBAC:多人平台的第一道門

> 對應 **PR #11**:`docs(auth): add auth & admin design plan`

同樣是 **docs 先行**的 PR——先把認證與權限的設計講清楚。一個要給多人用的平台,權限不是 nice-to-have,是**地基**。

### 三層權限模型

```
┌──────────────────────────────────────────────┐
│  ①  登入閘門(Authentication)                  │
│     整個 app 都要登入才能進;                    │
│     首次啟動 seed 預設 admin(admin/admin),     │
│     上線前必須改掉                              │
└──────────────────────┬─────────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│  ②  角色(Authorization / RBAC)                │
│     admin  vs  一般 user                        │
│     admin 能管人、管任務、管金鑰、管評審模型      │
└──────────────────────┬─────────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│  ③  細到「每人能用哪些任務」的 allowlist        │
│     admin 指派:User A 只能跑爬蟲,             │
│     User B 全開,User C 只能投標                │
└────────────────────────────────────────────────┘
```

第三層——**per-user 任務 allowlist**——是這個設計最實用的地方。因為這些任務有些會真的花錢(LLM token)、有些會真的操作外部帳號(投標、寄信)。你不會希望每個使用者都能無差別地跑所有任務。admin 能精細地控制「誰能碰什麼」。

### 一個很務實的決策:API key 存 DB(加密)

```
選擇              存加密 DB 的理由                 存環境變數的問題
────────────────────────────────────────────────────────────────
加密存 DB         admin 能在後台線上管理金鑰;      改一次要重新部署容器;
(這個專案)      多把金鑰、多環境好管理;          金鑰散落各處難盤點;
                  加密後即使 DB 外洩也有一層防護     無法做「誰改了金鑰」的稽核
純環境變數        簡單、十二要素 App 教條           運維彈性差
```

把金鑰放進(加密的)DB,讓 admin 能在 UI 上管理——這對一個「非工程師的 admin 也要能操作」的平台很合理。**翻轉條件**:在更嚴格的合規環境,你會改用專門的 secrets manager(AWS Secrets Manager、Vault),而不是自建加密欄位。但對這個規模,DB 加密欄位是「複雜度剛好」的選擇。

---

## 五、生產化前後對照

把這四個 PR 放在一起,看系統從「能跑的 Demo」變成「能上線的產品」:

| 面向 | 生產化之前 | 生產化之後 | 對應 PR |
|------|-----------|-----------|---------|
| 品質可見度 | 跑完就沒了,不知好壞 | 每次 run 一條 Langfuse trace,帶品質分數 | #19 |
| Docker image | 塞整顆 Chromium,幾百 MB | WeasyPrint,~450 MB,build/啟動更快 | #9 |
| 部署 | 「在我電腦上」 | ECS Fargate 設計:自動擴縮、健康檢查、stale run 回收 | #10 |
| 存取控制 | 無 | 登入 + RBAC + per-user 任務 allowlist | #11 |

### 一條貫穿的線索

這四件事看似無關(監控、打包、部署、權限),但它們共享同一個心態:**假設這個系統會被真實地、長期地、多人地使用**。

- Langfuse:因為你需要在**事後**回答「上週品質怎麼了」——假設有維運的一天。
- WeasyPrint:因為 image 會被**反覆** build、pull、冷啟動——假設部署是家常便飯。
- Fargate + health check + stale run 回收:因為容器**隨時會**被重啟——假設基礎設施是短命的。
- RBAC:因為使用者**不只你一個**——假設會有你不完全信任的人來用。

**Demo 為「現在能動」而寫;產品為「未來會怎樣」而設計。** 這一篇的四個 PR,全都是後者。

---

## 六、小結

生產化不是上線前一晚熬夜補的東西,而是從架構第一天就埋下的假設。這個專案示範的幾個判斷,值得任何在做 AI 產品的人收藏:

1. **可觀測性要掛在「唯一漏斗」上。** 找到那個所有請求必經、且手上資訊最全的地方(這裡是 executor),在那裡記一次,勝過在十個地方各記一次還漏東漏西。
2. **別扛過重的依賴。** 先問「我真正需要它哪部分能力」——Chromium → WeasyPrint 省下的體積,每次部署都在回收。
3. **為「短命的基礎設施」而設計。** stale run 回收、health check——這些讓系統在 Fargate 這種「容器隨時被換」的環境裡活得好。
4. **權限是地基不是裝飾。** 尤其當任務會花錢、會操作外部帳號時,「誰能用什麼」必須能被精細控制。

下一篇 **Part 5**,我們回到使用者最直接感受到的那一層——**前端與 Pipeline 編排**:那條每 0.5 秒更新的 SSE 即時進度串流是怎麼運作的、Waymo 電影感的 UI 主題(PR #15)、landing page(PR #6),以及如何用 `{{steps.N.result}}` 模板把多個任務串成一條自動化工作流。

---

### 系列導覽

- Part 1:系統總覽、架構、資料流
- Part 2:Harness 引擎——多模型容錯、自我修正、LLM 評審、成本追蹤
- Part 3:自動化任務實戰——Shopee、Google Maps、Tasker、利潤健檢
- **Part 4(本篇)**:生產化之路——Langfuse、Docker、AWS、權限
- Part 5:前端體驗與 Pipeline 編排

> 對應的 PR:[#19 Langfuse](https://github.com/yennanliu/agent_auto_system/pull/19)、[#9 Docker 瘦身](https://github.com/yennanliu/agent_auto_system/pull/9)、[#10 AWS 部署設計](https://github.com/yennanliu/agent_auto_system/pull/10)、[#11 Auth 設計](https://github.com/yennanliu/agent_auto_system/pull/11)
> 專案原始碼:[github.com/yennanliu/agent_auto_system](https://github.com/yennanliu/agent_auto_system)
