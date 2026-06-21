---
title: "AI 工程從零開始｜Phase 19 Part 2：Capstone — 生產級 AI Agent 產品端對端實作"
date: 2026-06-22T05:30:00+08:00
draft: false
weight: 42
description: "端對端構建生產級 AI Agent 產品：從架構設計到上線，涵蓋 ReAct 迴圈、工具整合、記憶系統、Guardrails、可觀測性與商業指標追蹤"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "LLM Engineering", "Production", "Capstone", "ReAct", "RKK", "Interview"]
authors: ["yen"]
readTime: "28 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人做法：把 ChatGPT API 包一層 wrapper，加幾個 if-else，叫它「AI 客服 Agent」。*
> *正確答案：ReAct 迴圈 + 工具安全閘 + 對話記憶 + Guardrails + 完整可觀測性，*
> *缺少任何一層，上線兩週後你就會收到第一封「Agent 幫客戶退了根本沒問題的訂單」的事後報告。*
> *本文是一個真實 Sprint 4 週期的工程回顧，紀錄哪些設計決策讓我們撐過了 100K sessions/day。*

---

## 面試情境

> 你的公司想把電商客服從人工轉為 AI Agent，日均客服量約 30K sessions，高峰期（雙 11）可能到 80K。客服範圍包含訂單查詢、退換貨申請、產品推薦以及升級至人工。請描述你會如何設計這個系統，從 MVP 到可以承受 80K sessions/day 的生產架構，並說明關鍵的工程決策與取捨。

---

## 一、專案目標：AI 客服 Agent 的真實產品需求

這個 Capstone 專案的原型來自一個真實的電商平台改造案。業務背景很清楚：

- **現狀**：人工客服 45 人，平均回應時間 4.2 分鐘，CSAT 3.7/5，月薪資成本 $180K USD
- **目標**：AI 處理率 ≥ 70%，平均回應時間 < 8 秒，CSAT ≥ 4.0/5，月 AI 成本 < $35K
- **風險底線**：不能有金融損失（錯誤退款、錯誤折扣），不能有個資外洩

拆解需求後，Agent 需要具備五種能力：

| 能力 | 描述 | 工具需求 |
|------|------|----------|
| 訂單查詢 | 查訂單狀態、物流追蹤 | `get_order`, `get_tracking` |
| 退換貨 | 申請退款、換貨、生成退貨標籤 | `create_return`, `issue_refund` |
| 產品知識 | 規格比較、使用說明、相容性 | `search_kb`, `get_product_spec` |
| 帳號管理 | 積分查詢、會員等級、偏好設定 | `get_account`, `update_preference` |
| 人工升級 | 情緒偵測後轉交人工坐席 | `escalate_to_human` |

這五種能力聽起來不複雜，但工程上的陷阱在於：**每一個工具都有副作用風險**。`issue_refund` 打錯參數就是真金白銀的損失；`create_return` 呼叫兩次就是重複退貨。這是整個系統設計的核心壓力點。

第一個教訓在 Sprint 1 第三天就踩到了：我們讓 LLM 直接決定「要不要退款」，沒有確認步驟。測試工程師用一句「我要退全部訂單」，Agent 乖乖去呼叫了 `issue_refund`。那天下午我們加了 Guardrails。

---

## 二、三個演進階段（Sprint 1 / Sprint 2–3 / Sprint 4）

### ╔══════════════════════════════════════╗
### ║  Phase 1：Sprint 1 / POC / < 1K sessions/day  ║
### ╚══════════════════════════════════════╝

**目標**：讓 Agent 能跑起來，能走完一個退款流程端對端。

```
┌──────────────────────────────────────────────┐
│                  Phase 1 架構                 │
│                                              │
│  用戶訊息                                    │
│     │                                        │
│     ▼                                        │
│  ┌──────────┐    ┌─────────────────────┐    │
│  │  FastAPI  │───▶│   LLM (Claude)      │    │
│  │  /chat   │    │   ReAct Prompt      │    │
│  └──────────┘    └──────────┬──────────┘    │
│                             │ tool_call      │
│                             ▼                │
│                  ┌─────────────────────┐    │
│                  │  Tool Router        │    │
│                  │  (if-else dispatch) │    │
│                  └──────┬──────────────┘    │
│                         │                   │
│          ┌──────────────┼──────────────┐    │
│          ▼              ▼              ▼    │
│    ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│    │ Order DB │  │  CRM API │  │  KB txt │ │
│    └──────────┘  └──────────┘  └─────────┘ │
│                                              │
│  對話歷史：in-memory dict（重啟即消失）       │
└──────────────────────────────────────────────┘
```

**新增元件**：FastAPI endpoint、基礎 ReAct prompt、3 個工具、SQLite 訂單 mock

**成本/複雜度**：$0.8/1K sessions，2 週可上線 demo，2 人工程師

**解決的問題**：
- 驗證 LLM 能否正確呼叫工具
- 確認 ReAct 迴圈終止條件

**遺留的問題**：
- in-memory 對話歷史，多 instance 無法共享
- 沒有任何 Guardrails，高風險工具直接可呼叫
- 沒有可觀測性，出了問題不知道 Agent 做了什麼
- 單點故障，FastAPI crash 整個服務掛掉

**Sprint 1 最大痛點**：LLM 偶爾會在 ReAct 迴圈裡無限呼叫工具，我們的停止條件是「看到 `Final Answer:`」，但 LLM 有時候不寫。後來改成 max_iterations=8 強制截斷，並把截斷結果記錄下來供後續分析。

---

### ╔══════════════════════════════════════╗
### ║  Phase 2：Sprint 2–3 / MVP / 1K–20K sessions/day  ║
### ╚══════════════════════════════════════╝

**目標**：生產安全，讓客服主管敢讓真實客戶使用。

```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 2 架構                            │
│                                                                 │
│  用戶訊息                                                       │
│     │                                                           │
│     ▼                                                           │
│  ┌──────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  API GW  │──▶│  Guardrails Layer│──▶│  Agent Orchestrator│  │
│  │  (nginx) │   │  (意圖分類 + PII │   │  (ReAct Engine)    │  │
│  └──────────┘   │   過濾)          │   └────────┬───────────┘  │
│                 └──────────────────┘            │               │
│                                                 │ tool_calls    │
│                                                 ▼               │
│                                    ┌────────────────────────┐   │
│                                    │  Tool Safety Wrapper   │   │
│                                    │  · 高風險工具確認步驟  │   │
│                                    │  · 冪等性 token        │   │
│                                    │  · rate limit per user │   │
│                                    └────────┬───────────────┘   │
│                                             │                   │
│              ┌──────────────────────────────┼───────────────┐  │
│              ▼              ▼               ▼               ▼  │
│        ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│        │ Order API│  │ CRM API  │  │ KB Vector│  │Escalate│  │
│        │ (REST)   │  │ (REST)   │  │ (pgvector│  │  API   │  │
│        └──────────┘  └──────────┘  │  + BM25) │  └────────┘  │
│                                    └──────────┘               │
│                                                                 │
│  對話歷史：Redis（TTL 24h，session key）                       │
│  可觀測性：結構化 log → Loki，Grafana dashboard                 │
└─────────────────────────────────────────────────────────────────┘
```

**新增元件**：Redis session store、Guardrails layer、Tool Safety Wrapper、pgvector 知識庫、結構化 logging

**成本/複雜度**：$2.1/1K sessions，4 週開發，4 人工程師，增加 2 台 Redis instance

**解決的問題**：
- 多 instance 共享對話歷史
- 高風險工具有確認機制
- 知識庫查詢品質提升（hybrid search）
- 可以事後審計 Agent 行為

**遺留的問題**：
- Agent Orchestrator 仍是單執行緒，高流量下 latency 飆升
- 知識庫沒有版本控制，更新文件可能影響現有 session
- 成本沒有 per-user 預算控制

**Sprint 2 最大痛點**：Redis TTL 設 24h，但客戶半夜開始的對話隔天早上繼續，context 被截斷。改為「session 最後活躍時間起算 4h」，但要處理 TTL refresh 的時間競爭條件（race condition）。最後用 Redis `EXPIRE` 在每次讀取時重設 TTL。

**Sprint 3 最大痛點**：知識庫混合搜尋的 BM25 權重調不好。Recall 高但 Precision 差，LLM 拿到不相關的文件就會「幻想」出規格。引入 cross-encoder reranker 後，Top-3 precision 從 61% 提升到 84%，但 latency 多了 120ms。在 P95 latency < 3s 的 SLA 下，這是可接受的。

---

### ╔══════════════════════════════════════╗
### ║  Phase 3：Sprint 4 / Scale / 20K–100K sessions/day  ║
### ╚══════════════════════════════════════╝

**目標**：企業級，支援雙 11 峰值 80K sessions/day，成本可預期。

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Phase 3 架構                              │
│                                                                     │
│              ┌─────────────────────────────────────┐               │
│              │         流量入口層                   │               │
│              │  CDN → API GW (rate limit + auth)   │               │
│              └────────────────┬────────────────────┘               │
│                               │                                     │
│              ┌────────────────▼────────────────────┐               │
│              │         Guardrails 服務 (獨立部署)   │               │
│              │  · 意圖分類 (fine-tuned classifier) │               │
│              │  · PII 偵測 & 遮罩                  │               │
│              │  · Jailbreak 防護                   │               │
│              └────────────────┬────────────────────┘               │
│                               │                                     │
│   ┌───────────────────────────▼─────────────────────────────────┐  │
│   │              Agent Orchestration Pool                        │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │  │
│   │  │ Worker-1 │  │ Worker-2 │  │ Worker-3 │  │ Worker-N │   │  │
│   │  │(ReAct)   │  │(ReAct)   │  │(ReAct)   │  │(ReAct)   │   │  │
│   │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │  │
│   └────────┼────────────┼─────────────┼──────────────┼─────────┘  │
│            │            │             │              │             │
│   ┌────────▼────────────▼─────────────▼──────────────▼─────────┐  │
│   │                  Tool Gateway (統一入口)                      │  │
│   │  · 冪等 token 驗證  · 配額控制  · Circuit Breaker           │  │
│   └────┬──────────┬──────────┬──────────┬──────────────────────┘  │
│        ▼          ▼          ▼          ▼                          │
│   ┌─────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐                 │
│   │Order API│ │CRM   │ │KB Service│ │Escalation│                 │
│   │(read    │ │API   │ │(pgvector │ │Queue     │                 │
│   │replica) │ │      │ │+ cache)  │ │(SQS)     │                 │
│   └─────────┘ └──────┘ └──────────┘ └──────────┘                 │
│                                                                     │
│   記憶層：Redis Cluster (3 shard × 2 replica)                     │
│   可觀測性：OpenTelemetry → Tempo (traces) + Loki (logs)           │
│   成本控制：per-user token budget，超出自動降級至 FAQ only         │
└─────────────────────────────────────────────────────────────────────┘
```

**新增元件**：Agent Worker Pool（水平擴展）、Tool Gateway（Circuit Breaker）、Redis Cluster、OpenTelemetry tracing、per-user token budget、Order DB read replica

**成本/複雜度**：$1.4/1K sessions（規模效益，批次 embedding 預計算），6 人工程師，infrastructure 複雜度顯著上升

**解決的問題**：
- 水平擴展應對峰值
- Circuit Breaker 防止下游崩潰擴散
- 成本可預期且有上限
- 完整 trace 串聯整個 Agent 執行路徑

**Sprint 4 最大痛點**：Circuit Breaker 的半開（half-open）狀態管理。當 CRM API 恢復後，Circuit Breaker 允許少量流量探測，但探測請求剛好打在還不穩定的節點，又觸發 open 狀態，來回震盪了 20 分鐘。最後設定了「連續 5 次成功才 close」的條件，震盪問題消失。

---

## 三、Agent 核心：ReAct 迴圈 + 工具集設計

ReAct（Reasoning + Acting）是整個 Agent 的心臟。核心邏輯很簡單，難的是邊界條件。

```
┌───────────────────────────────────────────────────────────┐
│                    ReAct 執行迴圈                          │
│                                                           │
│  用戶輸入                                                 │
│      │                                                    │
│      ▼                                                    │
│  ┌───────────────────────────────────┐                   │
│  │  Thought: 分析當前狀況            │                   │
│  │  （LLM 推理，不呼叫外部 API）     │                   │
│  └───────────────┬───────────────────┘                   │
│                  │                                        │
│                  ▼                                        │
│  ┌───────────────────────────────────┐                   │
│  │  Action: 決定呼叫哪個工具         │◀─────────┐        │
│  │  Action Input: 工具參數           │          │        │
│  └───────────────┬───────────────────┘          │        │
│                  │                               │        │
│                  ▼                               │        │
│  ┌───────────────────────────────────┐          │        │
│  │  Observation: 工具回傳結果        │          │        │
│  └───────────────┬───────────────────┘          │        │
│                  │                               │        │
│          ┌───────▼────────┐                     │        │
│          │ 達成目標？      │──── 否 ─────────────┘        │
│          └───────┬────────┘                              │
│                  │ 是（或 iteration ≥ 8）                │
│                  ▼                                        │
│  ┌───────────────────────────────────┐                   │
│  │  Final Answer: 回應用戶           │                   │
│  └───────────────────────────────────┘                   │
└───────────────────────────────────────────────────────────┘
```

### 工具設計原則

工具集共 12 個，分三個風險等級：

**Level 0 — 只讀，無需確認（8 個）**
```python
get_order(order_id: str) -> OrderInfo
get_tracking(order_id: str) -> TrackingInfo
get_product_spec(sku: str) -> ProductSpec
search_kb(query: str, top_k: int = 3) -> List[KBDoc]
get_account(user_id: str) -> AccountInfo
list_orders(user_id: str, limit: int = 5) -> List[OrderSummary]
check_return_eligibility(order_id: str) -> EligibilityResult
get_promotions(user_id: str) -> List[Promotion]
```

**Level 1 — 寫入，需用戶確認（3 個）**
```python
create_return(order_id: str, reason: str, items: List[str]) -> ReturnRequest
update_preference(user_id: str, pref_key: str, pref_value: str) -> bool
schedule_callback(user_id: str, preferred_time: str) -> CallbackRequest
```

**Level 2 — 金融操作，需雙重確認 + 人工審核（1 個）**
```python
issue_refund(order_id: str, amount: float, reason: str) -> RefundRequest
# 注意：此工具只「申請」退款，真正執行由人工審核系統決定
```

這個分級設計是 Phase 2 才加入的。Phase 1 所有工具平等對待，是最大的架構錯誤。

### 工具呼叫冪等性

所有 Level 1/2 工具強制要求 `idempotency_key`，由 Agent Orchestrator 在每個 session 開始時生成：

```python
idempotency_key = f"{session_id}:{tool_name}:{hash(str(tool_args))}"
```

如果相同的 key 在 24h 內再次出現，Tool Gateway 直接返回第一次的結果，不實際呼叫下游。這解決了 LLM 偶爾重複呼叫同一工具的問題。

---

## 四、工具整合：CRM/訂單系統/知識庫的安全接入

### CRM API 整合的真實挑戰

CRM 是第三方 SaaS（不是自建），有以下限制：
- Rate limit：600 requests/min per API key
- 回應時間：P50 = 180ms，P95 = 800ms，P99 = 2.3s（偶爾超時）
- 沒有 webhook，只能 polling

在 20K sessions/day（平均 14 sessions/min，但峰值 3×）的規模下，每個 session 平均呼叫 CRM 2.3 次，峰值需要約 96 calls/min。看似沒問題，但雙 11 峰值就是 288 calls/min，加上重試就可能打爆 rate limit。

**解法**：在 Tool Gateway 加了 token bucket rate limiter + 本地快取（TTL 60s for read-only operations）。CRM 讀取請求命中快取率在穩定期達到 73%，有效降低了對 CRM 的實際呼叫量。

### 訂單系統整合的問題

訂單系統是內部服務，但有一個設計缺陷：`get_order` API 每次都打 primary DB，沒有 read replica。

Phase 1/2 流量小沒感覺。Phase 3 測試時，DBA 打電話來說 primary DB CPU 飆到 85%。

**解法**：
1. 加 read replica，`get_order` 改打 replica
2. 在 Tool Gateway 加了 10s 的訂單狀態快取（對客服場景，10s 的 stale data 是可接受的）
3. 把 `list_orders` 的預設 limit 從 10 改成 5，減少 DB 掃描範圍

### 知識庫的混合搜尋

知識庫有 12,000 份文件（產品說明書、FAQ、退換貨政策）。純向量搜尋的問題是對型號、SKU、精確詞彙 recall 差；純 BM25 的問題是語意理解弱。

最終架構：
- **Vector store**：pgvector，1536-dim embeddings
- **BM25 index**：Elasticsearch（輕量部署），用於精確詞彙匹配
- **Fusion**：Reciprocal Rank Fusion (RRF)，合併兩個排名列表
- **Reranker**：cross-encoder，對 top-10 結果重新評分，取 top-3 給 LLM

這個 pipeline 的 latency budget：
- Vector search：~45ms
- BM25 search：~30ms（並行執行）
- RRF fusion：~5ms
- Reranker：~120ms
- **Total P95：~220ms**（可接受，在 Agent 整體 latency 裡不是瓶頸）

---

## 五、記憶系統：對話歷史 + 用戶偏好持久化

記憶系統解決兩個問題：**短期記憶**（同一 session 的對話上下文）和**長期記憶**（跨 session 的用戶偏好）。

```
┌──────────────────────────────────────────────────────────┐
│                     記憶系統架構                          │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  短期記憶（Session Buffer）                      │    │
│  │                                                  │    │
│  │  Redis Key: session:{session_id}:messages        │    │
│  │  TTL: 最後活躍後 4 小時                          │    │
│  │  結構: List of {role, content, timestamp, tools} │    │
│  │  大小上限: 最近 20 輪對話（約 8K tokens）        │    │
│  │                                                  │    │
│  │  溢出策略: 保留 system prompt + 最近 15 輪       │    │
│  │           + 摘要最早的 N 輪（LLM 生成摘要）      │    │
│  └─────────────────────────────────────────────────┘    │
│                           │                              │
│                           │ session 結束時               │
│                           ▼                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  長期記憶（User Profile）                        │    │
│  │                                                  │    │
│  │  PostgreSQL Table: user_profiles                 │    │
│  │  Key fields:                                     │    │
│  │    · preferred_language (zh-TW / en)             │    │
│  │    · contact_preference (chat / email / phone)   │    │
│  │    · last_issue_category (return / query / etc.) │    │
│  │    · total_sessions, avg_csat                    │    │
│  │    · vip_tier (影響工具呼叫優先級)               │    │
│  │                                                  │    │
│  │  Redis 快取 TTL: 1 小時（LRU eviction）          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  工具呼叫記憶（Idempotency Store）               │    │
│  │                                                  │    │
│  │  Redis Key: idem:{idempotency_key}               │    │
│  │  TTL: 24 小時                                    │    │
│  │  用途: 防重複工具呼叫                            │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 對話摘要的時機

當 session buffer 超過 20 輪（約 8K tokens），繼續撐大 context window 的成本指數上升。我們的策略是：

1. 偵測到超過 15 輪時，非同步呼叫 LLM 生成「前 10 輪摘要」
2. 摘要保留：用戶名稱、主要問題類型、已確認的事實（如訂單號碼）、尚未解決的問題
3. 把最早的 10 輪替換成這份摘要，節省約 4K tokens

這個機制讓長對話的 token 成本降低了約 35%，同時不影響 Agent 的上下文理解（測試中，摘要替換後的回答品質評分從 4.1 降到 3.9，在可接受範圍內）。

### 長期記憶的邊界

一個設計決策：**長期記憶不存儲對話內容，只存儲結構化偏好**。

原因：
- 隱私合規（GDPR / 台灣個資法）要求對話記錄有明確保留期限
- 對話內容是高噪音資料，直接塞給 LLM 效果差
- 結構化偏好（語言偏好、聯絡方式）可以直接影響 system prompt，效果好且成本低

---

## 六、Guardrails：意圖偵測 + 行動確認 + 成本控制

Guardrails 是整個系統最後悔沒有在 Day 1 就做的部分。

### 意圖分類器

在 Agent 執行 ReAct 迴圈之前，先跑一個輕量意圖分類器：

```
用戶輸入 → 意圖分類器 → [SAFE | RISKY | BLOCKED | ESCALATE]
                              │
         ┌────────────────────┼────────────────────────┐
         ▼                    ▼                        ▼
     SAFE: 繼續         RISKY: 加強確認         BLOCKED: 直接拒絕
   正常 ReAct          步驟 + 人工審核          + 記錄 + 告警
```

分類器用 fine-tuned BERT（90M parameters），輸入用戶訊息，輸出四類標籤：

| 標籤 | 典型輸入 | 後續處理 |
|------|----------|----------|
| SAFE | 「我的訂單到哪了？」 | 正常 ReAct，所有工具可用 |
| RISKY | 「退掉我所有訂單」、「把帳號刪掉」 | ReAct 可跑，但 Level 1/2 工具需額外確認 |
| BLOCKED | 注入攻擊、要求系統 prompt、無關話題 | 固定回覆，不進入 Agent |
| ESCALATE | 情緒激動（偵測到負面情緒詞彙）| 直接轉人工，不嘗試 AI 回覆 |

分類器的 latency P95 = 18ms（GPU 推理），幾乎不影響整體 latency。

### 行動確認機制

對於 Level 1 工具，Agent 必須在呼叫前明確獲得用戶確認：

```
Agent: 「我確認您要為訂單 #12345678 申請退換，退換商品為『無線耳機 × 1』，
       退換原因為『商品損壞』，是否確認？（回覆「確認」或「取消」）」

用戶: 「確認」

→ Agent 才呼叫 create_return(...)
```

這個流程讓退換貨誤操作率從 Phase 1 的 2.3% 降到 0.1%。

### 成本控制

每個 user 有 token budget：
- 一般用戶：每 session 最多 8,000 tokens（包含 input + output）
- VIP 用戶：每 session 最多 16,000 tokens
- 超出預算：自動降級為 FAQ-only 模式（直接搜尋知識庫，不跑 LLM），並提示用戶開新 session

Token budget 在 Tool Gateway 追蹤，每次 LLM 呼叫後更新 Redis counter。

---

## 七、可觀測性：每次 Agent 執行的完整追蹤

在 Phase 1，我們出了問題完全不知道 Agent 做了什麼決策。Phase 2 起，每次 Agent 執行都要產生一個完整的 trace。

### Trace 結構

每個 session 的 trace 包含：

```json
{
  "trace_id": "550e8400-e29b-41d4-a716",
  "session_id": "sess_abc123",
  "user_id": "usr_xyz",
  "start_time": "2026-06-01T14:23:01Z",
  "end_time": "2026-06-01T14:23:07Z",
  "total_latency_ms": 5840,
  "intent_label": "RISKY",
  "iterations": [
    {
      "iteration": 1,
      "thought": "用戶要退款，需先確認訂單是否符合退換條件",
      "action": "check_return_eligibility",
      "action_input": {"order_id": "12345678"},
      "observation": {"eligible": true, "deadline": "2026-06-08"},
      "latency_ms": 210
    },
    {
      "iteration": 2,
      "action": "CONFIRMATION_REQUESTED",
      "user_response": "確認",
      "latency_ms": 12300
    },
    {
      "iteration": 3,
      "action": "create_return",
      "idempotency_key": "sess_abc123:create_return:a3f2b1",
      "observation": {"return_id": "RET_999", "status": "pending"},
      "latency_ms": 380
    }
  ],
  "final_answer": "已為您建立退換申請 RET_999...",
  "tokens_used": {"input": 2340, "output": 187},
  "cost_usd": 0.0032,
  "csat": null
}
```

### Metrics Dashboard

Grafana 上追蹤的核心指標：

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| P95 latency (end-to-end) | < 8s | > 12s |
| Tool call success rate | > 99% | < 97% |
| Agent iteration 平均值 | < 3.5 | > 5 |
| Token 使用量/session 平均 | < 4,500 | > 7,000 |
| BLOCKED intent rate | < 2% | > 5% |
| Escalation rate | < 15% | > 25% |

### 異常偵測

設置了三個自動告警：

1. **Loop 告警**：如果任何 session 的 iteration 達到 7（接近上限 8），立即告警並標記 session 供人工審查
2. **成本告警**：如果某個 user 在 1 小時內累計成本超過 $5，觸發帳號稽查
3. **工具失敗串聯告警**：如果同一工具在 5 分鐘內失敗率超過 20%，觸發 Circuit Breaker 並告警

---

## 八、為什麼選 X 不選 Y（6 個決策表）

### 決策 1：LLM 選型

| 選擇 | 選 Claude Sonnet 的理由 | 不選其他的理由 |
|------|------------------------|---------------|
| LLM 主力 | 工具呼叫格式穩定，JSON schema 遵循率 > 99%；長 context 表現好；輸出結構化程度高 | GPT-4o 工具呼叫在高並發下偶有格式錯誤（約 0.3%）；開源模型工具呼叫 quality 落差大 |

**Flip condition**：若成本是唯一考量，且工具呼叫複雜度低（< 5 個工具），可考慮較小的開源模型部署在本地，節省約 60% 成本。

---

### 決策 2：向量資料庫

| 選擇 | 選 pgvector 的理由 | 不選 Pinecone/Weaviate 的理由 |
|------|-------------------|-------------------------------|
| 知識庫存儲 | 已有 PostgreSQL 基礎設施，運維熟悉；支援 ACID 事務，知識庫更新不會有骯髒讀；12K 文件規模不需要專門 vector DB | Pinecone：額外服務費用 $200+/月，知識庫規模不值得；Weaviate：運維複雜度高，需要額外學習 |

**Flip condition**：知識庫超過 5M 文件，或 QPS > 500 純向量搜尋，pgvector 效能開始落後，此時遷移至 Pinecone 或 Qdrant 合理。

---

### 決策 3：Session 存儲

| 選擇 | 選 Redis 的理由 | 不選 PostgreSQL/DynamoDB 的理由 |
|------|----------------|--------------------------------|
| 對話歷史 | < 1ms 讀寫延遲；原生 TTL 支援；List 資料結構完美對應對話歷史；Cluster 模式高可用 | PostgreSQL：連線開銷大，JSONB 讀取 P95 約 15ms；DynamoDB：按讀寫次數計費，高頻存取成本高 |

**Flip condition**：需要跨 90 天的長期對話分析，Redis 的 AOF 持久化不適合，應改用 PostgreSQL + Redis 雙寫架構。

---

### 決策 4：Guardrails 架構

| 選擇 | 選獨立服務的理由 | 不選內嵌 Agent 的理由 |
|------|----------------|----------------------|
| Guardrails 部署 | 獨立 scaling，意圖分類器 GPU 需求與 Agent 不同；可單獨更新 classifier 不影響 Agent；不同 Agent 共用同一 Guardrails 服務 | 內嵌：Guardrails 崩潰會拖垮 Agent；classifier 更新需要重新部署整個 Agent 服務 |

**Flip condition**：每日流量 < 1K sessions，獨立服務的 infra 成本高於收益，內嵌更簡單。

---

### 決策 5：知識庫搜尋策略

| 選擇 | 選 Hybrid (Vector + BM25) 的理由 | 不選純 Vector 的理由 |
|------|----------------------------------|---------------------|
| KB 搜尋 | 型號（AX-3200）、SKU、條款編號等精確詞彙 recall 高；RRF fusion 簡單且效果好；Top-3 Precision 84% vs 純 Vector 的 61% | 純 Vector 對「退換貨政策第 3 條」這類精確查詢 recall 差；純 BM25 對語意相近但用詞不同的查詢 recall 差 |

**Flip condition**：知識庫全部是非結構化長文（無型號/代碼），純 Vector 效果已夠好，不需維護額外的 BM25 index。

---

### 決策 6：退款工具設計

| 選擇 | 選「申請式」退款的理由 | 不選「直接執行」退款的理由 |
|------|----------------------|--------------------------|
| `issue_refund` 語意 | AI Agent 只建立退款申請，由人工審核系統最終決定；錯誤可以在審核階段攔截；合規要求（金融操作需人工授權） | 直接執行：Phase 1 曾試過，測試中就有誤退款 3 筆，總金額 $420；合規風險極高 |

**Flip condition**：退款金額 < $10 且訂單狀態明確符合退換條件（由 `check_return_eligibility` 確認），可考慮設計小額自動退款通道，減少人工審核負擔。

---

## 九、系統效應（上線後 90 天的真實指標）

上線日期：2026-03-01，以下是 90 天後（2026-05-31）的指標對比。

### 核心 KPI

| 指標 | 上線前（純人工） | 上線後（AI 處理 72%） | 變化 |
|------|-----------------|----------------------|------|
| 平均首次回應時間 | 4.2 分鐘 | 6.3 秒（AI）/ 2.8 分鐘（人工升級） | **-97% for AI sessions** |
| CSAT 評分 | 3.7 / 5 | 4.1 / 5 | **+10.8%** |
| 每月客服成本 | $180K | $42K（人工 $28K + AI $14K） | **-76.7%** |
| AI 處理率 | 0% | 72% | — |
| 退換貨誤操作率 | 0.8%（人工失誤） | 0.09% | **-88.8%** |
| 平均 session 解決率 | 91%（人工） | 78%（AI alone）/ 95%（AI + 升級） | AI 單獨略低 |

### 技術指標（90 天平均）

| 指標 | P50 | P95 | P99 |
|------|-----|-----|-----|
| Agent 端對端 latency | 3.2s | 7.8s | 14.1s |
| LLM 呼叫 latency | 1.1s | 3.4s | 6.2s |
| 工具呼叫 latency | 210ms | 780ms | 1.9s |
| Guardrails latency | 18ms | 42ms | 88ms |

### 失敗與學習

**問題 1：雙 11 前三天，Escalation rate 飆到 31%（警戒線 25%）**

根本原因：知識庫沒有更新雙 11 的特殊退換貨政策，Agent 給了舊的回答，客戶不滿意就要求轉人工。

修復：建立知識庫版本審核流程，重大活動前 72 小時必須完成知識庫更新，並用 100 個測試問題驗證 Agent 回答正確性後才上線。

**問題 2：第 45 天，發現部分 VIP 用戶的長期記憶偏好沒有正確寫入**

根本原因：session 結束時的非同步寫入 PostgreSQL 因 exception 靜默失敗（沒有 retry 機制）。

修復：加入 dead letter queue，寫入失敗的偏好資料進入 DLQ，有監控告警，人工確認後重試。

**問題 3：第 67 天，某個工具（`get_tracking`）的第三方物流 API 升級，response schema 變更，Agent 開始返回 hallucination**

根本原因：Tool 的 response parser 沒有 schema validation，舊 parser 遇到新格式靜默返回 None，Agent 收到 None 就自己「編」了一個追蹤狀態。

修復：所有工具 response 加 Pydantic model validation；validation 失敗時返回明確的錯誤訊息給 Agent（「工具暫時無法使用，建議告知用戶稍後再試」），而非 None。

### 成本分析（90 天）

| 成本項目 | 月費 |
|----------|------|
| LLM API（Claude，混合 Sonnet/Haiku） | $11,200 |
| Redis Cluster（3 shard） | $840 |
| PostgreSQL（主 + read replica） | $620 |
| Elasticsearch（BM25） | $380 |
| Guardrails GPU instance | $520 |
| 其他 infra（API GW、monitoring） | $440 |
| **AI 總成本** | **$14,000** |

Haiku 用於低複雜度任務（純查詢、格式化輸出），Sonnet 用於需要推理的任務（退換貨決策、情緒分析）。這個 routing 讓 LLM 成本降低了約 38%。

---

## 十、面試答題要點

> *「這個電商 AI 客服系統我分三個 Sprint 演進：Sprint 1 先跑通 ReAct 迴圈與 3 個工具的 E2E 流程，確認 LLM 工具呼叫可行性；Sprint 2–3 加入 Redis session 存儲、Guardrails 意圖分類、Tool Safety Wrapper（冪等 token + 高風險工具確認步驟）、hybrid search 知識庫，讓 20K sessions/day 可以安全生產運行；Sprint 4 引入 Agent Worker Pool 水平擴展、Circuit Breaker、per-user token budget、OpenTelemetry 全鏈路追蹤，支援 100K sessions/day 的峰值。關鍵決策是把 `issue_refund` 設計成「申請式」而非「直接執行」，AI 只建立申請，人工審核最終授權，這讓退換貨誤操作率從測試期的 2.3% 降到上線後的 0.09%。上線 90 天後，AI 處理率 72%，CSAT 從 3.7 提升到 4.1，月客服成本從 $180K 降到 $42K，最大教訓是 Guardrails 和工具冪等性必須在 Day 1 就做，而不是出了事故再補。」*

---

## 十一、系列導航

本文是 **AI 工程從零開始** 系列 Phase 19 的第 2 篇。

← **Phase 19 Part 1**：[Capstone — 系統設計與 Sprint 規劃](/posts/ai-eng-from-scratch-phase19-part1-capstone-design-zh/)

→ **Phase 19 Part 3**：[Capstone — 上線後優化與 A/B 測試框架](/posts/ai-eng-from-scratch-phase19-part3-capstone-optimization-zh/)

---

*本文撰寫於 2026 年 6 月，基於實際 Sprint 回顧紀錄。系統架構數字已部分模糊化以保護客戶隱私，但量級與比例關係忠實反映真實情況。*
