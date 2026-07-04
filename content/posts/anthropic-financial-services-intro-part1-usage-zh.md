---
title: "Anthropic Financial Services 入門 Part 1 — 怎麼安裝、怎麼用"
date: 2026-07-04T09:00:00+08:00
draft: false
description: "Anthropic 官方開源的 financial-services 套件,把投資銀行、股票研究、私募股權、財富管理最常見的工作流程,包成 Claude 的 Agent 和 Skill。本篇講清楚怎麼在 Cowork 和 Claude Code 裡安裝它、怎麼選你需要的 Agent 或 Vertical Plugin,以及裝完之後第一次該怎麼用。"
categories: ["engineering", "ai", "all"]
tags: ["Anthropic", "Claude", "Financial Services", "Claude Code", "Cowork", "Agent", "MCP", "AI Engineering"]
authors: ["yen"]
readTime: "12 min"
---

> 大部分團隊想用 LLM 做財務分析,第一步是自己從零寫 prompt、兜資料源、堆流程。
> 正確的起手式是:先看有沒有人已經把這套流程做成可重複使用的 Agent。
> [anthropics/financial-services](https://github.com/anthropics/financial-services) 就是 Anthropic 官方把「投銀、研究、私募、財管」最常見工作流程包好的參考實作。
> 裝上去、調參數,比從空白 prompt 開始快得多。

---

## 一、這個套件解決什麼問題

金融業的分析工作有一個共通結構:**輸入一堆非結構化資料(財報、CIM、GP 報告、KYC 文件),經過固定的分析步驟,產出一份要給人審核的工作成果(模型、備忘錄、對帳表)**。

```
   典型金融分析工作流程
   ─────────────────────────────────────────
   財報 / 文件 / 資料源
        │
        ▼
   固定分析步驟(comps、DCF、對帳、KYC 規則)
        │
        ▼
   工作成果草稿(memo / model / deck)
        │
        ▼
   人工審核與簽核 ← 必要,不可跳過
```

這個流程本身重複性很高,但每個環節都需要領域知識(怎麼抓可比公司、怎麼算 WACC、怎麼追帳目斷點)。`financial-services` 這個 repo 就是把這些領域知識寫成 Claude 的 Skill 和 Slash Command,再包成 Agent。

> [!IMPORTANT]
> 這些 Agent 產出的是**分析師工作草稿**——模型、備忘錄、對帳結果——供合格專業人員審核。它們不做投資建議、不執行交易、不核准開戶,每一份輸出都停在「待人工簽核」這一步。

## 二、兩種部署方式,同一套系統

這是這個 repo 最重要的設計決定:**同一份 system prompt、同一組 skill,可以用兩種方式跑**。

```
┌─────────────────────────┐         ┌─────────────────────────┐
│   Claude Cowork          │         │  Claude Managed Agents   │
│   (互動式,人在迴圈中)    │         │  API(headless,接你自己  │
│                          │         │  的工作流引擎)            │
└────────────┬─────────────┘         └────────────┬─────────────┘
             │                                      │
             └──────────────┬───────────────────────┘
                             ▼
              plugins/agent-plugins/<slug>/
              同一份 agents/<slug>.md + skills/
```

選 Cowork,適合你想要一個人坐在旁邊互動、隨時打斷、調整方向的場景(例如做 pitch deck)。選 Managed Agents API,適合你要把它塞進既有的批次工作流(例如每天自動跑 GL 對帳)。這篇先講 Cowork 和 Claude Code 這兩種最常見的安裝路徑,Managed Agents 部署留到後續系列再細講。

## 三、安裝:Claude Code

```bash
# 第一步:加入 marketplace
claude plugin marketplace add anthropics/financial-services

# 第二步:先裝核心 skill + 資料連接器(其他 vertical 都依賴它)
claude plugin install financial-analysis@claude-for-financial-services

# 第三步:挑你要的「命名 Agent」
claude plugin install pitch-agent@claude-for-financial-services
claude plugin install gl-reconciler@claude-for-financial-services
claude plugin install market-researcher@claude-for-financial-services

# 或者只裝某個垂直領域的 skill 組合(不含完整 Agent)
claude plugin install investment-banking@claude-for-financial-services
claude plugin install equity-research@claude-for-financial-services
```

裝完之後:
- Agent 會出現在 Cowork 的 dispatch 選單裡(如果你也開了 Cowork)
- Skill 會在相關情境下**自動觸發**,不用手動呼叫
- Slash Command 會直接出現在你的 session,例如 `/comps`、`/dcf`、`/earnings`、`/ic-memo`

## 四、安裝:Cowork

在 Cowork 裡開 **Settings → Plugins → Add plugin**,有兩種裝法:

1. **貼 repo URL**:`https://github.com/anthropics/financial-services`,然後從 marketplace 清單裡挑你要的 Agent 和 Vertical
2. **上傳 zip**:把 `plugins/` 底下任一個目錄打包成 zip 上傳,例如只想要 Pitch Agent,就打包 `plugins/agent-plugins/pitch-agent/`

## 五、先裝哪些?依角色給的起手式

```
角色              先裝 vertical              再挑 Agent
──────────────────────────────────────────────────────────
投銀 Analyst      financial-analysis         pitch-agent
                  + investment-banking       meeting-prep-agent

股票研究員         financial-analysis         market-researcher
                  + equity-research          earnings-reviewer

PE Associate      financial-analysis         valuation-reviewer
                  + private-equity

財管顧問           financial-analysis         (多半直接用 vertical
                  + wealth-management         的 slash command)

Fund Admin        financial-analysis         gl-reconciler
                  + fund-admin                month-end-closer
                                              statement-auditor

Ops / 合規         financial-analysis         kyc-screener
                  + operations
```

**永遠先裝 `financial-analysis`**——它是核心,帶著 comps、DCF、LBO、3-statement 這些共用建模 skill,以及全部 11 個資料連接器(Daloopa、FactSet、Moody's、PitchBook 等)。其他 vertical 和 Agent 都假設這個核心已經在。

## 六、裝完第一次怎麼用

以 Pitch Agent 為例,裝好之後在 Cowork 或 Claude Code 裡直接用自然語言描述任務:

```
幫我針對 XYZ 公司做一份初步 pitch,
包含可比公司分析、precedent transactions、簡單 LBO,
輸出成 deck。
```

Claude 會依照 `pitch-agent` 底下打包好的 skill(comps-analysis、lbo-model、pptx-author 等)依序執行,中途你可以隨時插話調整假設(例如換 WACC、換可比公司池)。如果你只想跑單一步驟,直接用 slash command 更快:

```
/comps XYZ  →  只做可比公司分析,不跑完整 pitch 流程
/dcf XYZ    →  只做 DCF 估值
```

## 七、資料連接器需要什麼

`financial-analysis` 核心 plugin 集中管理所有 MCP 連接器,寫在 `.mcp.json` 裡,包括 Daloopa、Morningstar、S&P Global、FactSet、Moody's、PitchBook、Chronograph、Egnyte、Box、LSEG、Aiera、MT Newswires 共 11 個。

> 大部分連接器需要你自己有該資料商的訂閱或 API Key——這個 repo 只負責把 Claude 接上去,不附贈資料授權。沒有訂閱的連接器,對應的 skill 一樣能用,只是缺少即時資料查詢能力,得靠你手動貼資料進去。

## 八、下一步

裝好之後,你已經可以跑第一個 Agent 或 slash command 了。但要真的用得順手,得先搞懂這個 repo 裡 **Agent / Skill / Command / Connector** 這四層是怎麼分工、怎麼組合的——這是 Part 2 的主題。

---

**系列導覽:**
- Part 1:怎麼安裝、怎麼用(本篇)
- Part 2:核心概念——Agent、Skill、Command、Connector 怎麼組成一個系統
- Part 3:實戰案例——用 GL Reconciler 跑一次真實對帳流程
