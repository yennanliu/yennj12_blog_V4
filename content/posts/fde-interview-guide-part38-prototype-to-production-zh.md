---
title: "FDE 面試準備指南（三十八）：RKK 實戰——從 POC 到 Production：AI 系統的五個生產化差距與 Rollback 設計"
date: 2026-06-05T16:00:00+08:00
draft: false
weight: 38
description: "以系統設計視角拆解 AI 系統從 POC 到生產最容易失敗的五個差距：Token Budget 失控、延遲 SLA 差距、Session State 消失、錯誤處理不完整、Rollback 機制缺席；包含生產化 Go-Live 清單、Prompt 版本控制、模型版本釘選、Canary 部署設計，以及每個差距對系統效能和穩定性的量化影響"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Production", "POC", "Deployment", "Rollback", "SLA", "Token Budget", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "18 min"
---

> 同一個 Agent，Demo 時跑得很好。  
> 上了生產後成本是預估的 8 倍、偶爾 15 秒、有時候對話記憶消失。  
> 「能 Demo」和「可以讓 1,000 個用戶每天用」之間的距離，  
> 就是生產化工程的價值。

---

## 面試情境

> **面試官：**「你幫客戶做了一個 3 週的 RAG + Agent POC，Demo 很成功。客戶的 CTO 說：太好了，下個月上線。你說：先等一下，我們需要做幾件事。你會說什麼？」

---

## 一、POC 和 Production 的假設差距

```
POC 的隱性假設：

  假設 1：只有你在用（實際：100 個並發）
  假設 2：測試資料乾淨（實際：用戶會貼整份合約進來）
  假設 3：成本不計較（實際：月底看帳單）
  假設 4：出錯了就 debug（實際：1 小時內要給客戶答覆）
  假設 5：你挑了最好的 Demo 例子（實際：Murphy's Law）

五個 POC 到 Production 的差距：

  差距 1：Token Budget → 成本是預估的 8 倍
  差距 2：延遲 SLA → Cold Start 讓 P95 超過 SLA
  差距 3：Session State → 重啟後對話記憶消失
  差距 4：錯誤處理 → 外部 API Timeout 讓 Agent crash
  差距 5：Rollback → Prompt 改錯了沒辦法快速回頭

以下逐一拆解每個差距的成因和設計。
```

---

## 二、差距 1：Token Budget 失控

```
失控路徑：

  POC 測試：平均 2,000 input tokens，成本可接受。
         ↓
  Production 現實：

  情況 A：用戶貼了整份合約
  input_tokens = 20,000（是預估的 10 倍）

  情況 B：Multi-turn 對話 history 累積
  第 1 輪：2,000 tokens
  第 5 輪：2,000 + (4輪 × 800) = 5,200 tokens
  第 15 輪：2,000 + (14輪 × 800) = 13,200 tokens

  情況 C：ReAct loop 多跑幾輪
  正常：2 輪 Tool Call = 2,000 × 2 = 4,000 tokens
  異常：6 輪 Tool Call（遇到困難問題）= 2,000 × 6 = 12,000 tokens

Token Budget 設計：

  ┌─────────────────────────────────────────────────────────────┐
  │  總 Budget：8,000 tokens（可配置）                            │
  │                                                              │
  │  ├── System Prompt（固定）：-1,200 tokens                    │
  │  │   （如果 > 1,000 tokens，考慮 Context Caching）            │
  │  │                                                           │
  │  ├── User Query：-actual tokens（優先保留）                   │
  │  │                                                           │
  │  ├── Conversation History（最多 30% 剩餘 budget）            │
  │  │   超過部分：從最舊的輪次開始截斷                            │
  │  │   如果整體 > 10 輪：先壓縮成 Summary                      │
  │  │                                                           │
  │  └── Retrieved Context（剩餘 budget）                        │
  │      按相關性排序，直到 budget 用完                           │
  └─────────────────────────────────────────────────────────────┘

成本效益：
  無 Budget 管理：預估 $0.015/query，實際 $0.12/query（8倍）
  有 Budget 管理：$0.015-0.025/query（可預測，可定價）
```

---

## 三、差距 2：延遲 SLA

```
SLA 失效路徑：

  POC 測試：10 個問題，平均 3 秒。「還可以。」
         ↓
  Production 問題：

  問題 A：Cloud Run Cold Start
  Auto-Scale Scale-Out 後，新實例啟動需要 8-12 秒
  第一個打到新實例的用戶：等了 12 秒

  問題 B：外部 API Spike
  SAP API 在月結日前壓力大，P99 從 200ms 變成 8 秒
  整個 Agent 的 P99 跟著變成 11 秒

  問題 C：Token 超長的請求
  LLM 推論時間和 input_tokens 正相關
  20,000 input tokens 的請求比 2,000 的慢 5 倍

SLA 設計：

  ┌──────────────────────────────────────────────────────────────┐
  │                延遲 SLA 設計                                   │
  │                                                              │
  │  目標：P50 < 2s  P95 < 5s  P99 < 10s                        │
  │                                                              │
  │  Cold Start 解法：                                            │
  │  Cloud Run min-instances = 2（高峰期可調高）                   │
  │  代價：持續計費，即使沒有流量（$10-30/月）                      │
  │  判斷：P95 SLA 要求 < 5s → min-instances 是必要成本           │
  │                                                              │
  │  Tool Timeout 設計：                                          │
  │  每個 Tool 呼叫設定 timeout（SAP=5s, Oracle=3s, External=8s）│
  │  Timeout 後 → Graceful Fallback，不讓整個 Agent 卡住          │
  │                                                              │
  │  Streaming 回應（改善感知延遲）：                               │
  │  實際延遲：8 秒（完整回答）                                     │
  │  感知延遲：1 秒看到第一個字，用戶知道系統在回應                  │
  │  適合：長回答（法律分析、報告生成）                              │
  └──────────────────────────────────────────────────────────────┘
```

---

## 四、差距 3：Session State 消失

```
消失路徑：

  POC：Conversation History 存在 Python dict（記憶體）。
       重啟就清空，測試時沒注意。
         ↓
  Production 問題：

  問題 A：Cloud Run Scale-Down
  閒置 15 分鐘後實例被回收
  → 記憶體清空 → 用戶下次請求找不到對話歷史

  問題 B：多實例
  Cloud Run Scale-Out 到 3 個實例
  用戶的第 1 個請求打到 Instance A（History 在 A）
  用戶的第 2 個請求打到 Instance B（History 不在 B）
  → 對話斷掉，Agent 不記得前面說了什麼

Session State 持久化方案對比：

  方案            延遲      成本      複雜度      適合場景
  ──────────────────────────────────────────────────────────────
  Firestore       10-50ms   低        低          ADK 原生整合，推薦預設
  （ADK 內建）                                     大多數企業 Agent
  ──────────────────────────────────────────────────────────────
  Cloud           < 5ms     中        中          高頻讀寫，
  Memorystore                                      對 Session 延遲敏感
  （Redis）
  ──────────────────────────────────────────────────────────────
  記憶體（dict）   < 1ms     零        零          只用於 Dev/POC，
                                                   不用於 Production
  ──────────────────────────────────────────────────────────────

Session State 的設計原則：
  ├── TTL（Session 過期時間）：24 小時（不能永久存）
  ├── 大小上限：每個 Session 最多 100KB（防止無限增長）
  └── PII：不存原始 PII（用 anonymized_id 代替 user_id）
```

---

## 五、差距 5：Rollback 機制設計

```
失效路徑：

  新版 Prompt 讓系統開始給出奇怪的答案。
  沒有 Rollback 機制：需要改代碼 → 跑 CI → 重新部署 → 30-60 分鐘
  30-60 分鐘內，所有用戶都在受影響。

  Rollback 三層設計：

  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 1：Prompt 版本控制（1 分鐘內 Rollback）                │
  │                                                              │
  │  PROMPT_REGISTRY = {                                         │
  │    "v2": "你是法務助理...",        ← 當前 stable             │
  │    "v3": "你是嚴謹的法律審查員...",← 剛上的新版              │
  │  }                                                           │
  │                                                              │
  │  ACTIVE_PROMPT = os.getenv("ACTIVE_PROMPT", "v2")           │
  │                                                              │
  │  Rollback：只需要改環境變數 → 重啟 Cloud Run，不需要改代碼    │
  └──────────────────────────────────────────────────────────────┘
                               ↓
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 2：模型版本釘選（防止 Google 更新破壞你的 Prompt）       │
  │                                                              │
  │  ❌ 不要用：model = "gemini-2.0-flash"                        │
  │             （Google 更新這個 model，你的行為悄悄改變）         │
  │                                                              │
  │  ✅ 要用：model = "gemini-2.0-flash-001"（具體版本號）         │
  │                                                              │
  │  升級流程：                                                   │
  │  新版本發布 → Staging 環境切換 → 跑 Eval Pipeline → 通過      │
  │  → 更新環境變數 → Canary 部署 → 全量                          │
  └──────────────────────────────────────────────────────────────┘
                               ↓
  ┌──────────────────────────────────────────────────────────────┐
  │  Layer 3：Canary 部署（Traffic Splitting）                     │
  │                                                              │
  │  不做全量切換，先 Canary：                                     │
  │                                                              │
  │  Day 1：v3（新版）10% + v2（穩定版）90%                       │
  │  Day 2：v3 25% + v2 75%（如果指標正常）                       │
  │  Day 3：v3 100%（全量）                                       │
  │                                                              │
  │  監控 Canary 的指標（每小時看一次）：                           │
  │  ├── Error Rate：新版有沒有增加錯誤？                          │
  │  ├── P95 Latency：新版有沒有變慢？                             │
  │  └── Shadow Eval Faithfulness：品質有沒有退化？                │
  │                                                              │
  │  任何指標異常 → 立刻把 Canary 流量改回 0%（5 秒內完成）         │
  │                                                              │
  │  gcloud run services update-traffic agent \                  │
  │    --to-revisions=STABLE=100                                 │
  └──────────────────────────────────────────────────────────────┘
```

---

## 六、生產化 Go-Live 清單

```
五個差距對應的 Go-Live 檢查項目：

  差距            檢查項目                          完成時間
  ──────────────────────────────────────────────────────────────
  Token Budget   □ 每個 LLM 呼叫有 Token 上限        2 天
                 □ Conversation History 有截斷策略
                 □ Cost Alert 已設定（月費 > $X → 通知）
  ──────────────────────────────────────────────────────────────
  延遲 SLA       □ P50/P95/P99 SLA 已定義（不只平均值）2 天
                 □ min-instances > 0（消除 Cold Start）
                 □ 每個 Tool 有 timeout 設定
  ──────────────────────────────────────────────────────────────
  Session State  □ Session State 不存在記憶體          1 天
                 □ 已遷移到 Firestore 或 Redis
                 □ Session TTL 已設定
  ──────────────────────────────────────────────────────────────
  錯誤處理       □ 所有 Tool 有 Graceful Fallback      2 天
                 □ 全域 Exception Handler（不暴露 stack trace）
                 □ 結構化錯誤訊息（Agent 能理解，用戶看到友好訊息）
  ──────────────────────────────────────────────────────────────
  Rollback       □ Prompt 版本控制（環境變數切換）      1 天
                 □ 模型版本已釘選（具體版本號）
                 □ Canary 部署流程已建立
  ──────────────────────────────────────────────────────────────
  可觀測性       □ Cloud Trace 已整合（見 Part 35）     2 天
  （前提）       □ Error Rate / 延遲 Alert 已設定
  ──────────────────────────────────────────────────────────────

  總計：8 個工作天，一個工程師可以完成。
  如果超過 5 個項目未完成 → 建議先 Internal Pilot（50 個內部用戶），
  不要直接開放給全部用戶。
```

---

## 七、系統效應：生產化設計對系統的量化影響

```
維度          有生產化設計              沒有生產化設計
──────────────────────────────────────────────────────────────────
Token 成本    可預測（$0.02-0.025/req）  暴跌（最差 $0.12/req，8 倍）
──────────────────────────────────────────────────────────────────
P95 延遲      < 5s（有 min-instances）   8-12s（Cold Start）
             < 8s（有 Tool Timeout）    可能無限等待（無 Timeout）
──────────────────────────────────────────────────────────────────
Session 穩定  用戶感知到的連續對話        每 15 分鐘對話重置
             （Scale-Down 不影響）       （記憶體被回收）
──────────────────────────────────────────────────────────────────
Rollback 時間 < 5 分鐘（環境變數切換）    30-60 分鐘（改代碼重部署）
             生產問題影響窗口最小化
──────────────────────────────────────────────────────────────────
上線信心      有清單可以核對              靠感覺，不知道還漏了什麼
──────────────────────────────────────────────────────────────────

生產化工程成本 vs 收益：

  成本：8 個工作天（一個工程師）
  收益：
    ├── 防止帳單爆炸（Token Budget）
    ├── SLA 達標（Cold Start 消除）
    ├── 用戶體驗穩定（Session 不消失）
    └── 出問題可以 5 分鐘內修好（Rollback）

  任何一個未處理的差距，在用戶規模放大後都會變成嚴重事故。
  生產化工程不是「優化」，是「基本門檻」。
```

---

## 八、面試答題要點

> *「這道題考的是：知道 POC 和 Production 之間有哪些具體差距，以及如何系統性地填補它們——而不只是說『還需要測試』。*
>
> *五個差距：Token Budget 失控（需要截斷策略和 Cost Alert）；延遲 SLA 差距（需要 min-instances 和 Tool Timeout）；Session State 消失（需要 Firestore 持久化）；錯誤處理不完整（需要 Graceful Fallback 和全域 Exception Handler）；Rollback 機制缺席（需要 Prompt 版本控制、模型版本釘選、Canary 部署）。*
>
> *和客戶 CTO 的溝通方式：不說「還沒準備好」，說「下個月上線可以，但建議先做 2 週 Internal Pilot，同時並行處理這 5 件事，8 個工作天可以完成。Pilot 讓我們在真實流量下驗證，把影響範圍控制在 50 個內部用戶，而不是第一天就開放給所有用戶出問題。」*
>
> *Rollback 的設計邏輯：Prompt 版本控制讓我在 1 分鐘內 Rollback，不需要改代碼重新部署。模型版本釘選防止 Google 的更新悄悄改變系統行為。Canary 部署讓我在 10% 流量上驗證 24 小時，確認沒問題再全量。」*

---

**系列導覽：**  
← [（三十七）企業 AI 的連接組織：Legacy 系統整合](../fde-interview-guide-part37-legacy-integration-zh/)  
← [（三十三）RKK 面試解剖：面試官怎麼評分](../fde-interview-guide-part33-rkk-anatomy-zh/)
