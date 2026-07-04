---
title: "Anthropic Financial Services 入門 Part 2 — Agent、Skill、Command、Connector 是怎麼組成一個系統的"
date: 2026-07-04T10:00:00+08:00
draft: false
description: "同一個目錄結構要同時餵給 Cowork 和 Claude Managed Agents API,Anthropic 是怎麼設計的?本篇拆解 financial-services 套件裡 Agent、Skill、Command、Connector、Managed-agent wrapper 五層的分工與依賴關係,以及為什麼所有東西都是純 markdown/JSON、沒有 build step。"
categories: ["engineering", "ai", "all"]
tags: ["Anthropic", "Claude", "Financial Services", "MCP", "Agent Architecture", "Claude Skills", "AI Engineering"]
authors: ["yen"]
readTime: "13 min"
---

> 大部分「AI Agent 框架」的第一個問題是:互動模式(chat)和自動化模式(headless)得寫兩套邏輯。
> financial-services 的做法是:同一份 system prompt、同一組 skill,兩邊共用,只是包裝層不同。
> 這篇講清楚它是怎麼切出 Agent / Skill / Command / Connector 四層,讓這件事成立的。

---

## 一、核心問題:一份系統提示,兩種跑法

Claude Cowork 是互動式的,人全程在迴圈裡,隨時可以插話。Claude Managed Agents API 是 headless 的,接到你自己的批次工作流引擎裡跑,沒有人盯著。

如果這兩種模式各寫一套 prompt 和邏輯,維護成本會隨 Agent 數量線性爆炸——改一個 skill,要同步改兩個地方,遲早會漂移。

```
   錯誤做法(兩套維護)
   ─────────────────────────────
   Cowork prompt.md  ──╮
                        ├─ 各自維護,容易漂移
   Managed prompt.md ──╯

   financial-services 做法(一份來源)
   ─────────────────────────────
   agents/<slug>.md + skills/
        │
        ├──▶ Cowork 直接讀這個目錄
        └──▶ managed-agent-cookbooks/<slug>/ 引用同一份檔案
```

`scripts/sync-agent-skills.py` 和 `scripts/check.py` 的存在就是為了守住這個「單一事實來源」——後者會在 CI 檢查任何 Agent 綁定的 skill 有沒有跟 vertical 裡的原始版本「漂移」。

## 二、五層架構總覽

```
┌───────────────────────────────────────────────────────────┐
│  Agents(命名的端到端工作流,如 Pitch Agent、GL Reconciler)│
│  plugins/agent-plugins/<slug>/                             │
│  ── 自包含:把它用到的 skill 都打包進來                     │
└───────────────────┬───────────────────────────────────────┘
                     │ 綁定/呼叫
                     ▼
┌───────────────────────────────────────────────────────────┐
│  Skills(領域知識與步驟方法,Claude 自動判斷何時使用)        │
│  plugins/vertical-plugins/<vertical>/skills/  ← 原始來源    │
│  plugins/agent-plugins/<slug>/skills/         ← 同步副本    │
└───────────────────┬───────────────────────────────────────┘
                     │ 部分 skill 對應
                     ▼
┌───────────────────────────────────────────────────────────┐
│  Commands(手動觸發的 slash action,如 /comps、/dcf)         │
│  plugins/vertical-plugins/<vertical>/commands/              │
└───────────────────┬───────────────────────────────────────┘
                     │ 讀寫外部資料
                     ▼
┌───────────────────────────────────────────────────────────┐
│  Connectors(MCP Server,接資料商:FactSet、Moody's...)      │
│  plugins/vertical-plugins/financial-analysis/.mcp.json      │
└───────────────────────────────────────────────────────────┘

              (以上四層 = Cowork 看到的東西)
              (額外一層,只給 headless 部署用 ↓)

┌───────────────────────────────────────────────────────────┐
│  Managed-agent wrappers(agent.yaml + 深度 1 子 Agent +      │
│  steering 範例,給 headless 部署用)                          │
│  managed-agent-cookbooks/<slug>/                            │
└───────────────────────────────────────────────────────────┘
```

## 三、Agent:自包含的端到端工作流

repo 裡目前有 9 個命名 Agent,按功能分組:

```
Coverage & advisory      Pitch Agent、Meeting Prep Agent
Research & modeling      Market Researcher、Earnings Reviewer、Model Builder
Fund admin & finance ops Valuation Reviewer、GL Reconciler、Month-End Closer、Statement Auditor
Operations & onboarding  KYC Screener
```

每個 Agent 目錄下有 `agents/<slug>.md`(system prompt,定義這個 Agent 的角色、範圍、審核邊界)和 `skills/`(打包進來的技能副本)。**自包含**意味著裝一個 Agent plugin,不用再手動去裝它依賴的 skill——這是跟單獨裝 vertical plugin 的差異。

## 四、Skill:自動觸發 vs Command:手動觸發

這是最容易搞混的一組概念。兩者都是「教 Claude 怎麼做一件事」的知識,差別在**觸發方式**:

```
選擇              Skill(自動)                    Command(手動 /command)
──────────────────────────────────────────────────────────────────────
觸發時機          Claude 判斷情境相關就自動用        你明確打 /comps 才執行
適合場景          背景知識、格式規範、通用方法        邊界清楚、參數明確的單一動作
範例              audit-xls、clean-data-xls         /comps、/dcf、/lbo、/earnings
                 (沒有對應 slash command)
```

不選 Command 而全部做成自動 Skill 的理由:有些技能(像 `audit-xls` 表格稽核)沒有明確的「使用者輸入」形狀,更適合讓 Claude 自己判斷什麼時候該檢查。反過來,`/dcf` 這種有清楚輸入(公司代號)、清楚輸出(一份 DCF)的動作,做成 Command 更符合使用者的心智模型——你想要的時候才觸發,而不是每次提到「估值」就自動跑一次完整 DCF。

**翻轉條件**:如果一個 Command 的參數逐漸變得可以被上下文自動推斷(例如聊天裡已經提過公司名稱、時間範圍),它就有機會被重新設計成 Skill,降低使用者手動打字的負擔。

## 五、Connector:11 個資料源,只在核心 plugin 定義一次

所有 MCP 連接器集中寫在 `financial-analysis` plugin 的 `.mcp.json`,其他 vertical 共用,不重複宣告:

```
Provider        典型用途
─────────────────────────────────────
Daloopa         財報結構化資料
Morningstar     基金 / 股票研究資料
S&P Global      Capital IQ 資料(kfinance)
FactSet         市場與財務資料終端
Moody's         信評與風險資料
PitchBook       私募/創投交易資料
LSEG            債券、利率曲線、FX
Chronograph     PE 基金組合監控
Egnyte / Box    文件儲存(CIM、GP 報告來源)
Aiera           法說會逐字稿
MT Newswires    新聞快訊
```

為什麼選「集中在核心 plugin」不選「每個 vertical 各自宣告自己要用的連接器」:

```
選擇                    理由                              不選的理由
────────────────────────────────────────────────────────────────────
集中在                  一個 API Key 設定一次,          分散宣告:同一個 FactSet
financial-analysis      所有 vertical 都能用             連接可能在 5 個 vertical
                       減少重複設定與版本漂移            裡各設一次,難以維護

MCP(而非直接             資料商可以獨立於 Anthropic       自建 REST wrapper:等於
寫 API wrapper)         更新自己的 server,不用           每個資料商都要重寫一次
                       repo 這邊跟著改                   整合邏輯
```

## 六、Managed-agent wrapper:多的那一層,只給 headless 用

Cowork 是互動的,人可以隨時打斷、補充資訊。Headless 部署沒有這個機制,所以 Managed Agents API 多了兩個東西:

- **`callable_agents`(子 Agent 委派)**:目前是 Research Preview 功能,讓主 Agent 在遇到超出自己範圍的子任務時,呼叫深度 1 的 leaf-worker 子 Agent,而不是卡住等人。
- **Steering events**:因為沒有人即時盯著,`agent.yaml` 裡會定義好在特定訊號出現時該怎麼處理(例如置信度過低時停下來排入人工佇列,而不是硬產出結果)。

```
選擇                理由                        不選的理由
──────────────────────────────────────────────────────
子 Agent委派         headless 沒有人可以即時       單一大 prompt 硬撐:
(callable_agents)   補充資訊,委派專責子任務       遇到超出範圍的子任務,
                    比讓主 Agent 硬猜更可靠         容易產出低品質或錯誤結果
```

**翻轉條件**:如果你的工作流本來就有人全程盯著(例如互動式 pitch 準備),用 Cowork 的互動模式就夠了,不需要 Managed Agent 那層委派與 steering 的複雜度——那是為了補償「沒有人在場」而存在的機制。

## 七、為什麼整個 repo 沒有 build step

所有東西都是 markdown 和 JSON:system prompt 是 `.md`,skill 是帶 frontmatter 的 `.md`,連接器設定是 `.mcp.json`,Managed Agent 定義是 `agent.yaml`。

```
選擇                        理由                          不選的理由
────────────────────────────────────────────────────────────────────
純文字檔(md/json/yaml)     Claude 原生讀懂,不需要         自訂 DSL + 編譯器:
無 build step               編譯/解析器;PR diff           每次改一個 skill 都要
                           就是最終產物,審閱直觀           重新編譯,增加維護成本
                                                          與新手上手門檻
```

這也是為什麼 `check.py` 能做到「檢查所有 manifest、驗證跨檔案引用都能解析、確認 bundled skill 沒有跟來源漂移」——因為一切都是可以直接用文字工具 diff、grep、lint 的東西,不需要先跑一輪編譯才能檢查正確性。

## 八、系統效應:裝了 vs 沒裝的差異

```
                          沒有這套系統              裝了 financial-services
────────────────────────────────────────────────────────────────────
新 Analyst 上手 DCF        自己寫 prompt,          直接 /dcf,套用團隊
                          品質因人而異               已驗證過的建模邏輯
維護 10 個 Agent 的        改一處要同步改多份         改 vertical 裡的 skill,
系統提示更新                容易漏改、產生漂移         跑 sync 腳本自動同步
Cowork ↔ Managed 切換      要重寫一套 headless        同一份 agent.yaml 引用
部署方式                    prompt 和邏輯              同一份 system prompt
```

## 九、下一步

概念搞清楚之後,Part 3 會挑一個實際的 Agent——GL Reconciler——走一次完整流程,看它怎麼從一堆帳目資料,產出一份待簽核的對帳報告。

---

**系列導覽:**
- Part 1:怎麼安裝、怎麼用
- Part 2:核心概念——Agent、Skill、Command、Connector 怎麼組成一個系統(本篇)
- Part 3:實戰案例——用 GL Reconciler 跑一次真實對帳流程
