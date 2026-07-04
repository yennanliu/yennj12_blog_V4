---
title: "Anthropic Financial Services 入門 Part 3 — 實戰:用 GL Reconciler 跑一次對帳流程"
date: 2026-07-04T11:00:00+08:00
draft: false
description: "從安裝到真的跑出一份待簽核的對帳報告——本篇挑 financial-services 套件裡的 GL Reconciler Agent,走一次完整流程:找斷點、追根因、標記待人工簽核,並比較 Cowork 互動模式和 Managed Agents headless 部署兩種跑法的差異。"
categories: ["engineering", "ai", "all"]
tags: ["Anthropic", "Claude", "Financial Services", "GL Reconciliation", "Fund Admin", "Managed Agents", "AI Engineering"]
authors: ["yen"]
readTime: "13 min"
---

> 講概念很容易流於空泛,所以這篇只做一件事:挑一個 Agent,走一次真實流程。
> GL Reconciler 是 fund-admin 這條線裡最具代表性的 Agent——輸入是總帳(GL)和對帳來源,
> 輸出是「哪裡斷了、為什麼斷、該找誰簽核」,而不是一個自動幫你改帳的黑盒子。

---

## 一、核心問題:對帳為什麼還需要人做

GL 對帳的痛點不是「不會算」,是**斷點的根因五花八門**——可能是時間差(trade date vs settlement date)、可能是手續費分類錯誤、也可能真的是資料輸入錯誤。傳統做法是資淺 Analyst 一筆一筆比對兩份表,慢且容易漏看模式。

```
   傳統對帳流程
   ─────────────────────────────
   GL 匯出 ──┐
             ├─ 人工逐筆比對 ──▶ 找到斷點 ──▶ 憑經驗猜根因 ──▶ 簽核
   對帳來源 ──┘        │
                      耗時、容易漏看跨期模式
```

GL Reconciler 要解決的,不是取代這個判斷,而是把「找斷點」和「聚類根因」這兩步自動化,把人力集中在真正需要判斷力的「這筆該怎麼調整」上。

## 二、三個演進階段

### Phase 1(POC / 單一基金,< 10K 筆交易月對帳量)

```
┌─────────────────────────────────────┐
│  Claude Code + gl-reconciler plugin  │
│  手動貼上 GL 匯出 + 對帳來源 CSV       │
└──────────────┬────────────────────────┘
               ▼
     Claude 讀兩份表,找斷點,輸出 markdown 報告
```

- 新增元件:僅 `financial-analysis` 核心 + `gl-reconciler` plugin,無連接器
- 成本/複雜度:幾乎零,一個 Analyst 手動貼資料跑
- 解決的問題:比人工逐筆比對快,能聚類出「同一根因造成的一批斷點」
- 未解決的問題:資料要手動匯出貼進去,無法排程,無歷史對照

### Phase 2(MVP / 多基金,10K–200K 筆/月)

```
┌───────────────┐     ┌───────────────┐
│  Fund Admin    │────▶│  Egnyte/Box    │
│  系統匯出       │     │  (GP 報告來源) │
└───────────────┘     └───────┬────────┘
                                ▼
                    ┌─────────────────────┐
                    │  gl-reconciler Agent │
                    │  (Cowork,人在迴圈)   │
                    └───────┬─────────────┘
                             ▼
                  斷點清單 + 根因分類 + 待簽核佇列
```

- 新增元件:接上 Egnyte/Box 連接器自動抓 GP 報告,Cowork dispatch 讓多個基金的對帳可以並行跑
- 成本/複雜度:需要文件儲存連接器的訂閱/權限設定,人力成本從「逐筆比對」降到「審核聚類結果」
- 解決的問題:多基金並行處理,斷點根因有分類而非逐筆羅列
- 未解決的問題:仍然是互動觸發,沒有排程,月底集中跑時人力仍是瓶頸

### Phase 3(Scale / 機構級,200K–1M+ 筆/月,多基金多幣別)

```
┌──────────────┐
│  排程觸發      │ (每日/每週跑增量對帳,而非月底一次性)
└──────┬────────┘
       ▼
┌─────────────────────────────┐      ┌──────────────────┐
│  Managed Agent               │─────▶│ callable_agents   │
│  (agent.yaml + headless)     │      │ 深度1 子Agent:    │
│                               │      │ 按幣別/按基金拆分  │
└──────┬────────────────────────┘      └──────────────────┘
       ▼
   斷點路由到對應 Fund Controller ── steering event 決定
   置信度夠高 → 自動排入簽核佇列
   置信度不足 → 標記需人工複核根因
```

- 新增元件:Managed Agents API 部署、`agent.yaml` 定義的子 Agent 委派、steering event 做置信度分流
- 成本/複雜度:需要自建或串接工作流引擎去消費 `handoff_request` 事件(見 `scripts/orchestrate.py` 參考實作),維運成本上升但單筆處理成本大幅下降
- 解決的問題:可排程、可依幣別/基金水平擴展、低置信度案例自動分流不會被吃案
- 仍未解決:置信度閾值需要持續調校,調太鬆會漏掉真正的異常,調太緊人工佇列會塞爆

## 三、跑一次 Phase 1/2 流程長什麼樣

裝好 Agent 後(參見 Part 1),在 Cowork 或 Claude Code 裡這樣起頭:

```
把這個月的 GL 匯出和 fund admin 對帳來源給你,
幫我找出所有斷點,依根因分類,
標出哪些可以直接簽核、哪些需要我再看一次。
```

GL Reconciler 內部大致依序做這幾件事(對應打包進來的 skill):

```
1. 解析兩份來源的欄位對應(帳戶、日期、金額、幣別)
2. 逐筆比對,找出金額或存在性不一致的項目
3. 對斷點做模式聚類(例如「同一天同一筆交易,金額差在手續費」)
4. 每個聚類標註根因假設 + 置信度
5. 輸出報告:高置信度直接建議調整分錄,低置信度標記待複核
```

輸出報告的骨架大致長這樣(示意,非真實輸出格式):

```
斷點聚類 #1(置信度:高)
  根因假設:結算日 vs 交易日時間差
  影響筆數:14
  建議動作:調整為交易日入帳,待財務簽核

斷點聚類 #2(置信度:低)
  根因假設:手續費分類科目不一致
  影響筆數:3
  建議動作:標記待人工複核,無法確認是否為系統性問題
```

**這一步不會自動過帳。** 無論置信度多高,repo 的設計原則是所有輸出都停在「待簽核」——這點在 README 的免責聲明裡明確寫出來,GL Reconciler 的角色是「找斷點、追根因、路由給人簽核」,不是「執行分錄」。

## 四、Cowork 互動模式 vs Managed Agents Headless

```
選擇                Cowork(互動)                    Managed Agents(headless)
────────────────────────────────────────────────────────────────────────
適合場景            月底集中對帳,有人盯著             日常增量對帳,排程觸發
                   隨時可以插話調整假設               無人值守

低置信度處理          Claude 直接問你怎麼判斷            steering event 決定路由到
                                                     人工佇列或子 Agent 複核

跨基金/跨幣別擴展     人工依序切換基金跑                 callable_agents 委派給
                                                     子 Agent 平行處理

部署複雜度            plugin install 即可用             需要 agent.yaml + 自建
                                                     或串接工作流引擎消費事件
```

**翻轉條件**:如果對帳量小、頻率低(例如小型基金月對帳量 < 1 萬筆),Cowork 互動模式就夠用,不需要上 Managed Agents 那層委派和排程的複雜度——那是為了應付「量大到不可能每次都有人盯著跑」才需要的機制。反過來,一旦你的對帳需要每日跑、需要在半夜排程完成、需要按幣別水平擴展,Managed Agents 的 headless 部署就變成必要,而不是可選項。

## 五、部署 Managed Agent 版本的實際指令

如果要把 GL Reconciler 部署成 headless 版本:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
scripts/deploy-managed-agent.sh gl-reconciler
```

這個腳本會解析 `managed-agent-cookbooks/gl-reconciler/` 底下的檔案引用、上傳 skill、建立 leaf-worker 子 Agent,再把整個 orchestrator POST 到 `/v1/agents`。子 Agent 委派(`callable_agents`)目前是 Research Preview 功能,`scripts/orchestrate.py` 提供了一個參考事件迴圈,示範怎麼把 Agent 之間的 `handoff_request` 事件路由到你自己的工作流引擎——這一段是需要你自己接的部分,repo 不會幫你跑起一個完整的排程系統。

## 六、系統效應:上線前後對照

```
                     上線前(人工/半自動)         上線後(GL Reconciler)
─────────────────────────────────────────────────────────────────
月底對帳耗時          2–3 個工作天                  高置信度斷點當天出報告,
                                                  人力集中在低置信度複核
根因追溯               憑經驗猜,容易漏看跨期模式      聚類展示,根因假設附
                                                  置信度分數
擴展到多基金           線性增加人力                   Managed Agents 階段可
                                                  水平擴展,人力增量趨緩
```

---

**系列導覽:**
- Part 1:怎麼安裝、怎麼用
- Part 2:核心概念——Agent、Skill、Command、Connector 怎麼組成一個系統
- Part 3:實戰案例——用 GL Reconciler 跑一次真實對帳流程(本篇)
