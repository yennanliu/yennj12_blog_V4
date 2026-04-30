---
title: "用 AI Bot 打造顧問團隊（四）：小型外包公司實戰案例"
date: 2026-04-30T12:00:00+08:00
draft: false
description: "實戰案例：一家 10 人軟體外包公司如何用 AI Agent 團隊自動化需求評估、報價、專案追蹤與客戶溝通，包含完整 Prompt、Skill 設計與執行步驟。"
categories: ["AI", "Agent", "Business", "Case Study", "all"]
tags: ["AI Agent", "外包公司", "Claude Code", "LangGraph", "Multi-Agent", "繁體中文", "實戰案例"]
authors: ["YennJ12 Engineering Team"]
readTime: "28 min"
---

## 情境設定

**公司背景：** TechBridge Studio，台灣台北，10 人軟體外包公司  
**主要業務：** 承接中小企業的網站、APP、後台系統開發  
**每月詢問量：** 約 40-60 個潛在客戶詢問  
**核心痛點：**
- PM 每天要花 3-4 小時回覆詢問、估時、報價
- 需求不清楚的客戶佔 70%，常常來回溝通一週才能確定範圍
- 報價單格式不統一，常常漏掉風險評估
- 客戶問進度時 PM 要手動查詢 Jira，很耗時

**目標：** 用 AI Agent 團隊處理 80% 的初步詢問與報價流程，讓 PM 只需審核最終結果。

---

## 整體架構設計

```
客戶詢問（LINE / Email / 網頁表單）
        ↓
① Intake Agent（需求釐清師）
   → 提問 10 個標準問題，整理結構化需求
        ↓
② Scope Agent（範圍評估師）
   → 拆解功能清單，標記模糊需求，評估風險
        ↓
③ Estimator Agent（報價估算師）
   → 根據功能清單估時、報價，套用公司價目表
        ↓
④ Proposal Agent（提案撰寫師）
   → 產出正式提案文件（含時程、里程碑、付款條件）
        ↓
⑤ PM Review（人工審核）
   → PM 在 5 分鐘內審核並核可
        ↓
⑥ Follow-up Agent（追蹤師）
   → 3 天後自動詢問客戶是否有問題，追蹤成交
```

---

## 技術選型

本案例使用 **Claude Code + AGENTS.md**（路線 A）為核心，理由：
- 公司沒有全職工程師，PM 兼任技術評估
- 需求相對線性（收集→評估→報價→提案）
- 希望 1 週內上線 MVP

---

## Step 1：建立專案目錄

```bash
mkdir techbridge-ai-team && cd techbridge-ai-team

# 目錄結構
mkdir -p .claude/skills workspace/proposals workspace/logs prompts
```

最終結構：
```
techbridge-ai-team/
├── AGENTS.md                  ← 團隊架構定義
├── .claude/
│   ├── settings.json          ← 工具權限與 Hook
│   └── skills/
│       ├── intake.md          ← 需求收集
│       ├── scope.md           ← 範圍評估
│       ├── estimate.md        ← 報價估算
│       └── proposal.md        ← 提案產出
├── prompts/
│   └── price_table.md         ← 公司價目表（Agent 參考用）
└── workspace/
    ├── proposals/             ← 產出的提案文件
    └── logs/                  ← 執行日誌
```

---

## Step 2：建立 AGENTS.md

```markdown
# TechBridge AI 顧問團隊

## 公司簡介
TechBridge Studio 是一家台灣軟體外包公司，專注於中小企業數位化解決方案。
我們的服務包括：網站開發、行動 APP、後台管理系統、API 整合。

## 核心原則
1. 誠實報價：不誇大，不低報以搶案子
2. 風險透明：模糊需求一定要標注，不能假裝清楚
3. 客戶體驗：回覆要讓非技術人員看得懂

## 角色定義

### Intake Agent（需求釐清師）
職責：透過友善對話收集客戶需求，確保資訊完整。
不做：不給技術建議，不估價，不承諾任何事。
語氣：親切、專業，像在跟朋友聊天但又有條理。

### Scope Agent（範圍評估師）
職責：把客戶需求轉成功能清單，標記清楚/模糊/風險。
不做：不報價，不跟客戶直接溝通。
輸出：JSON 格式的功能清單。

### Estimator Agent（報價估算師）
職責：根據功能清單和 price_table.md 估算工時與費用。
原則：寧可多估 20% 作為 buffer，不要低報。
輸出：詳細工時表 + 報價單 JSON。

### Proposal Agent（提案撰寫師）
職責：整合所有資訊，產出正式的 Word/Markdown 提案文件。
格式：Executive Summary、範圍說明、時程、里程碑、付款條件、風險聲明。

### Follow-up Agent（追蹤師）
職責：提案送出 3 天後，發送友善的追蹤訊息。
語氣：不要有壓迫感，像朋友關心一樣。

## 協作流程
Intake → Scope → Estimator → Proposal → [PM Review] → Follow-up（3天後）

## 升級至人工的條件
以下情況必須直接轉給 PM 處理：
- 預算超過 200 萬台幣
- 涉及金融、醫療、政府標案
- 客戶明確表示「我要跟真人談」
- 需求提到整合超過 5 個外部系統
```

---

## Step 3：建立 Skills 檔案

### `.claude/skills/intake.md`

```markdown
# Skill: 需求收集（Intake）

你是 TechBridge Studio 的需求收集師。你的目標是用友善、有條理的對話
收集客戶的完整需求，讓後續的範圍評估和報價能夠準確進行。

## 對話規則
- 一次只問一個問題
- 用繁體中文，語氣輕鬆友善
- 如果答案模糊，追問一次（例如：「您說的『簡單的會員系統』，請問需要哪些功能？」）
- 全部收集完才輸出 JSON，不要中途輸出

## 必問的 10 個問題（依序提問）

1. **業務介紹**：「請簡單介紹一下您的公司/產品，以及這個系統主要是要給誰用的？」

2. **核心功能**：「您最希望這個系統做到什麼？請列出您認為最重要的 3-5 個功能。」

3. **現有系統**：「您目前有在用什麼系統嗎？新系統需要跟它們整合嗎？」

4. **用戶規模**：「預計會有多少人使用這個系統？（同時上線人數大概多少？）」

5. **裝置需求**：「需要電腦版、手機版、還是兩者都要？」

6. **設計需求**：「有沒有提供設計稿或品牌規範？還是需要我們從頭設計？」

7. **時程期望**：「希望什麼時候可以上線？有沒有硬性的 deadline？」

8. **預算範圍**：「請問預算大概在什麼範圍？（不需要精確，粗估即可，這會影響我們選用的技術和方案）」

9. **維護需求**：「上線後有沒有需要後續維護或功能更新的計劃？」

10. **其他補充**：「還有什麼特別重要的需求或限制，想讓我們知道的嗎？」

## 輸出格式（全部問完後輸出）

輸出以下 JSON，存到 `workspace/intake_{timestamp}.json`：

```json
{
  "client_name": "（如果有提到）",
  "collected_at": "2026-04-30T12:00:00",
  "business_context": "業務描述",
  "core_features": ["功能1", "功能2", "功能3"],
  "existing_systems": ["系統1"],
  "integrations_needed": true,
  "user_scale": "預估用戶數",
  "device_requirements": "web|mobile|both",
  "design_provided": true,
  "deadline": "時程描述",
  "budget_range": "預算範圍",
  "maintenance_needed": true,
  "special_notes": "特殊需求",
  "ambiguous_points": ["需要進一步確認的點1", "點2"]
}
```
```

### `.claude/skills/scope.md`

```markdown
# Skill: 範圍評估（Scope Analysis）

你是 TechBridge Studio 的範圍評估師。你會收到 Intake Agent 的 JSON 需求，
把它轉換成開發功能清單，並標記每個功能的清晰度和風險。

## 評估標準

### 功能清晰度分類
- **CLEAR**：需求明確，可以直接估算工時
- **AMBIGUOUS**：需求模糊，需要客戶進一步確認才能估算
- **RISKY**：技術上有風險（效能、整合複雜度、第三方限制）
- **OUT_OF_SCOPE**：超出一般外包範圍，需要特別討論

### 功能拆解原則
把每個功能拆成「前端 UI」、「後端 API」、「資料庫」、「第三方整合」四個部分。

## 輸出格式

```json
{
  "scope_id": "SCOPE-20260430-001",
  "features": [
    {
      "feature_name": "會員註冊/登入",
      "clarity": "CLEAR",
      "components": {
        "frontend": "登入頁、註冊頁、忘記密碼頁",
        "backend": "JWT 驗證、密碼加密",
        "database": "users 資料表",
        "third_party": "無"
      },
      "risk_notes": null
    },
    {
      "feature_name": "金流串接",
      "clarity": "AMBIGUOUS",
      "components": {
        "frontend": "結帳頁",
        "backend": "Payment webhook",
        "database": "orders 資料表",
        "third_party": "需確認使用哪家金流（綠界/藍新/Stripe）"
      },
      "risk_notes": "不同金流商的串接複雜度差異很大，需先確認"
    }
  ],
  "ambiguous_questions": [
    "金流要用哪家？",
    "會員資料需要符合哪些法規？"
  ],
  "total_features": 8,
  "clear_count": 5,
  "ambiguous_count": 2,
  "risky_count": 1,
  "scope_confidence": "medium"
}
```

輸出 JSON 後，用繁體中文簡短說明模糊點和風險。
```

### `.claude/skills/estimate.md`

```markdown
# Skill: 報價估算（Estimation）

你是 TechBridge Studio 的報價估算師。根據 Scope Agent 的功能清單，
參考 `prompts/price_table.md` 的標準工時，估算費用。

## 估算規則

1. **只估算 CLEAR 和 AMBIGUOUS 的功能**，AMBIGUOUS 的功能要加 30% buffer
2. **RISKY 的功能**要列為「待確認後另估」，不放入主報價
3. **總價加 15% 管理費**（PM 溝通、文件、上線協助）
4. **付款條件標準**：簽約付 30%、開發完付 60%、驗收完付 10%
5. **保固期**：上線後 30 天免費修 bug（不包含新功能）

## 工時換算

- 設計師時薪：1,500 TWD
- 前端工程師時薪：1,800 TWD
- 後端工程師時薪：2,000 TWD
- PM 時薪：1,500 TWD

## 輸出格式

```json
{
  "estimate_id": "EST-20260430-001",
  "scope_id": "SCOPE-20260430-001",
  "line_items": [
    {
      "feature": "會員系統",
      "design_hours": 8,
      "frontend_hours": 16,
      "backend_hours": 12,
      "subtotal_twd": 68800,
      "is_buffered": false
    },
    {
      "feature": "金流串接（AMBIGUOUS +30%）",
      "design_hours": 2,
      "frontend_hours": 10,
      "backend_hours": 20,
      "subtotal_twd": 83200,
      "is_buffered": true
    }
  ],
  "pending_items": [
    {
      "feature": "第三方 ERP 整合",
      "reason": "需確認 ERP 廠商 API 文件後另估"
    }
  ],
  "subtotal_twd": 152000,
  "management_fee_twd": 22800,
  "total_twd": 174800,
  "total_range": "17-19 萬台幣",
  "estimated_weeks": 8,
  "payment_schedule": {
    "signing": 52440,
    "delivery": 104880,
    "acceptance": 17480
  }
}
```
```

### `.claude/skills/proposal.md`

```markdown
# Skill: 提案撰寫（Proposal Writing）

你是 TechBridge Studio 的提案撰寫師。整合 Intake、Scope、Estimate 三個 Agent
的輸出，產出一份正式、專業且易讀的提案文件。

## 文件結構

1. **封面** - 提案日期、客戶名稱、提案編號
2. **Executive Summary**（一頁）- 用三句話說清楚：我們理解你的需求、我們的方案、預期效益
3. **需求確認**（來自 Intake）- 以客戶視角重述需求，讓客戶確認理解正確
4. **功能範圍**（來自 Scope）- 清楚列出包含/不包含的功能
5. **時程規劃**
   - Week 1-2：設計與確認
   - Week 3-5：前端開發
   - Week 4-6：後端開發
   - Week 7：整合測試
   - Week 8：上線與交付
6. **報價明細**（來自 Estimate）- 按功能列明細，附總價範圍
7. **付款條件** - 標準分期付款
8. **需要客戶確認的事項** - 列出 AMBIGUOUS 的問題（**這點非常重要**）
9. **風險聲明** - 範圍外需求將另行估算；需求變更超過 20% 將重新報價
10. **下一步行動** - 請客戶於 7 天內回覆是否有問題

## 語氣原則
- 繁體中文，正式但不冰冷
- 避免工程術語（如「JWT」改寫成「安全的登入機制」）
- 把風險說清楚，但不要讓客戶覺得我們在找藉口

## 輸出
產出 Markdown 格式的提案，存到 `workspace/proposals/PROPOSAL-{id}.md`
同時輸出純文字的「確認問題清單」供 PM 用 Email 發送給客戶。
```

---

## Step 4：建立價目表（Agent 參考用）

**`prompts/price_table.md`**

```markdown
# TechBridge Studio 標準工時表

## 前端功能
| 功能 | 設計(hr) | 前端(hr) | 備注 |
|------|---------|---------|------|
| 首頁（含 RWD） | 8 | 16 | 含 3 個 section |
| 登入/註冊頁 | 4 | 8 | 含忘記密碼 |
| 列表頁（含搜尋篩選） | 4 | 12 | |
| 詳細頁 | 2 | 8 | |
| 表單頁 | 2 | 6 | 基本表單 |
| 後台管理介面（CRUD）| 8 | 24 | 含分頁、搜尋 |
| 圖表/儀表板 | 4 | 16 | 使用 Chart.js |
| 購物車結帳流程 | 8 | 20 | 3 步驟結帳 |

## 後端 API
| 功能 | 後端(hr) | 備注 |
|------|---------|------|
| 會員系統（JWT） | 12 | 含 refresh token |
| 商品管理 CRUD | 8 | |
| 訂單管理 | 16 | 含狀態機 |
| 金流串接（綠界） | 20 | 含 webhook |
| 金流串接（Stripe） | 16 | |
| 第三方登入（Google） | 8 | |
| Email 通知（SendGrid） | 6 | |
| 檔案上傳（S3） | 8 | |
| 搜尋功能（Elasticsearch） | 24 | 複雜度高 |
| 推播通知（FCM） | 12 | |

## 特殊加成
- 行動 APP（Flutter）：基礎費用 × 1.5
- 需要特別高效能（萬人同時上線）：另議
- 舊系統資料遷移：按資料量另估
```

---

## Step 5：設定 `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Read(**)",
      "Write(workspace/**)",
      "Bash(date)",
      "Bash(ls:workspace/**)",
      "Bash(cat:workspace/**)",
      "Bash(cat:prompts/**)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$(date '+%Y-%m-%d %H:%M:%S') - 產出檔案: $CLAUDE_TOOL_INPUT_FILE_PATH\" >> workspace/logs/activity.log"
          }
        ]
      }
    ]
  }
}
```

---

## Step 6：實際執行流程

### 啟動方式 1：命令列直接輸入

```bash
cd techbridge-ai-team

claude "你是 TechBridge AI 顧問團隊的協調員。
有一位新客戶傳來以下訊息：

'你好，我想做一個電商網站，要有會員、購物車、金流，
還要可以讓賣家上架商品。大概什麼價錢？'

請使用 Intake skill 開始收集完整需求，
完成後依序執行 Scope → Estimate → Proposal。
所有輸出請存到 workspace/ 目錄。"
```

### 啟動方式 2：Python 腳本（LINE Bot 整合）

```python
# line_integration.py
import subprocess
import json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextMessage, TextSendMessage
import os

app = Flask(__name__)
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# 簡易狀態管理（生產環境請用 Redis）
sessions = {}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    if user_id not in sessions:
        # 新客戶，啟動 Intake Agent
        sessions[user_id] = {"phase": "intake", "history": []}
        reply = "您好！我是 TechBridge 的 AI 顧問小幫手 😊 讓我先了解一下您的需求..."

    # 把對話送給 Claude Code
    result = subprocess.run(
        ["claude", "--print", f"作為 Intake Agent，回覆以下客戶訊息：{user_message}"],
        cwd="/path/to/techbridge-ai-team",
        capture_output=True, text=True
    )
    reply = result.stdout.strip()

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )
```

---

## Step 7：考量事項與常見踩坑

### 踩坑 1：客戶說「做個簡單的」

這是外包業最危險的詞。在 Intake Skill 中要明確追問：

```markdown
# 追加規則（加到 intake.md）
當客戶說「簡單」、「基本」、「就一個小網站」這類模糊詞彙時，
必須追問：「您說的『簡單』是指...（列出 3 個選項讓客戶選）？」
```

### 踩坑 2：報價被當成承諾

在 Proposal Skill 的輸出中，一定要加免責聲明：

```
⚠️ 本報價為初估，最終金額以雙方確認需求後為準。
   未列於功能清單內的需求將另行計費。
```

### 踩坑 3：Agent 直接答應客戶要求

在 AGENTS.md 中明確說：

```markdown
## 禁止事項（所有 Agent 都適用）
- 不得承諾任何 deadline
- 不得承諾價格（只能給範圍）
- 不得說「沒問題」、「可以做」——改說「讓我先確認規格後回覆您」
```

### 踩坑 4：Estimate Agent 低報

在估算 Skill 中加入規則：
```
如果你覺得某個功能的工時「差不多」，把它乘以 1.3。
外包業的經驗是：程式寫完只是 60%，整合、測試、修 bug 佔另外 40%。
```

---

## 實際產出範例

執行完整流程後，`workspace/proposals/` 裡會產出：

```markdown
# 專案提案

**提案編號：** PROP-20260430-001
**提案日期：** 2026-04-30
**有效期限：** 2026-05-14

---

## Executive Summary

我們理解您希望建立一個支援多賣家的電商平台，包含會員管理、購物車、
及金流串接功能。我們建議採用 8 週的開發時程，預計費用範圍為 **38-42 萬台幣**，
協助您快速上線並開始接單。

---

## 功能範圍（包含）

✅ 前台：
- 首頁 + 商品列表 + 商品詳情
- 會員註冊/登入（含 Google 登入）
- 購物車 + 結帳流程
- 訂單查詢

✅ 賣家後台：
- 商品上架/下架管理
- 訂單管理（含出貨狀態更新）
- 基本銷售報表

✅ 金流：
- 綠界信用卡串接（含退款）

---

## ❓ 開始前需要您確認的事項

1. 平台是否有抽成機制？如果有，需要額外的金流分帳功能（會增加費用）
2. 賣家審核流程？（自動開放 or 人工審核）
3. 是否需要多語言（中/英）？

---

## 時程規劃

| 週次 | 工作內容 |
|------|---------|
| Week 1-2 | 設計稿製作與確認 |
| Week 3-4 | 前端開發（前台） |
| Week 4-5 | 後端 API 開發 |
| Week 5-6 | 賣家後台開發 |
| Week 7 | 金流串接與整合測試 |
| Week 8 | 系統測試、修正、上線 |

---

## 報價明細

| 功能 | 費用 |
|------|------|
| 前台介面（含 RWD） | $68,000 |
| 會員系統 | $36,000 |
| 賣家後台 | $72,000 |
| 金流串接（綠界） | $40,000 |
| 購物車 + 訂單系統 | $64,000 |
| PM + 專案管理 | $30,000 |
| **小計** | **$310,000** |
| 管理費（15%） | $46,500 |
| **總計** | **$356,500** |

*預估範圍：35-42 萬台幣（視確認需求後調整）*

---

## 付款條件

- 簽約時：30%（$106,950）
- 開發完成：60%（$213,900）
- 驗收通過：10%（$35,650）

**保固：** 上線後 30 天內，系統 bug 免費修復（功能變更不包含在內）
```

---

## 效益評估

實施 AI Agent 團隊後，TechBridge 的預期改變：

| 指標 | 導入前 | 導入後目標 |
|------|--------|----------|
| 初步回覆時間 | 1-2 天 | 15 分鐘內 |
| PM 每天花在報價的時間 | 3-4 小時 | 30-45 分鐘（只需審核）|
| 每月可處理詢問量 | 40 件 | 80+ 件 |
| 報價文件一致性 | 低（各 PM 格式不同） | 高（標準化模板） |
| 漏掉需求確認的比率 | ~40% | <5% |

---

## 下一步

1. 複製本篇的目錄結構，依照你公司的實際價目表修改 `prompts/price_table.md`
2. 用 5 個真實的過去詢問案例測試，與實際提案做比對
3. 品質評分 ≥ 7/10 後才正式上線給客戶使用

下一篇（第五篇）：數位行銷公司的 AI Agent 團隊實戰。

---

*本系列文章：*
- [第一篇：策略與技術路線選擇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/)
- [第二篇：各路線實作步驟與範例程式碼](/posts/ai-agent-team-for-consultant-part2-implementation-zh/)
- [第三篇：評估、維運與優化計畫](/posts/ai-agent-team-for-consultant-part3-devops-zh/)
- **第四篇（本篇）：小型外包公司實戰案例**
- [第五篇：數位行銷公司實戰案例](/posts/ai-agent-team-for-consultant-part5-digital-marketing-zh/)
