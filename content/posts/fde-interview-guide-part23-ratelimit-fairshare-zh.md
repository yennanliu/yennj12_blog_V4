---
title: "FDE 面試準備指南（二十三）：RKK 實戰——多租戶 Agent 的限流、Fair-Share 與 Token 預算控制"
date: 2026-06-04T16:00:00+08:00
draft: false
weight: 23
description: "以系統設計視角拆解多租戶 AI Agent 系統的資源隔離問題：為什麼傳統 RPM 限流不夠、Token-Aware Rate Limiting 的設計原理、分散式令牌桶架構，以及如何防止 Noisy Neighbor Effect 影響其他租戶"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Rate Limiting", "Multi-tenant", "Token Budget", "Fair-Share", "Redis", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> 傳統 SaaS 的限流是「每分鐘最多 1,000 個請求」。  
> AI SaaS 的限流問題是「每分鐘最多 100 萬個 Token，但一個用戶的一個請求就可能用掉 50 萬 Token」。  
> 請求次數限流，在 AI 系統裡完全失效。

---

## 面試情境

> **面試官：** 「你的 B2B SaaS 將 Agent 系統開放給上千家企業使用。Gemini API 有嚴格的 TPM/RPM 限制。如果某個大客戶突然發起高頻查詢，把整個 GCP 專案的 Quota 耗盡，導致其他客戶全部收到 429 Too Many Requests。你如何在架構端設計 Fair-Share 與 Token 預算控制系統？」

---

## 一、核心問題：為什麼 AI 限流和傳統 API 限流完全不同

```
傳統 API 的資源消耗模型：

  每個請求的成本大致相同
  GET /users/123 ≈ GET /orders/456 ≈ 相同的計算資源
  → 限制「請求次數（RPM/RPS）」就夠了

AI API 的資源消耗模型：

  請求 A：「你好！」
    → input: 50 tokens, output: 30 tokens = 80 tokens

  請求 B：「請分析這份 200 頁的合約並翻譯成英文」
    → input: 150,000 tokens, output: 50,000 tokens = 200,000 tokens

  請求 B 消耗的資源是請求 A 的 2,500 倍！
  如果只限制請求次數（RPM）：
  → 請求 B 讓整個系統的 Token Quota 瞬間耗盡
  → 其他 99 個正常用戶全部 429

問題量化（Gemini 1.5 Pro 的 GCP 預設限制）：
  └── 全域 TPM：4,000,000 tokens/min（整個 GCP 專案）
  └── 一個「分析 200 頁合約」的請求 = 200,000 tokens
  └── 20 個這樣的並發請求 = 全部 Quota 耗盡
  └── 其他 1,000 個租戶的正常請求：全部 429
```

---

## 二、系統架構設計：Token-Aware 多層限流

```
┌──────────────────────────────────────────────────────────────┐
│                      用戶請求                                 │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             Layer 1：入口閘道（Apigee / Envoy）               │
│                                                              │
│  ├── 身份識別：從 JWT 取得 tenant_id                          │
│  ├── Token 估算：根據 request body 估算本次請求的 token 數    │
│  └── 快速通過 / 立即拒絕（不排隊，直接 429）                  │
│                                                              │
│  估算公式：estimated_tokens = len(prompt) * 1.3 + max_output │
└──────────────────────────┬───────────────────────────────────┘
                           │ 估算 token 數
                           ▼
┌──────────────────────────────────────────────────────────────┐
│         Layer 2：Token-Aware Rate Limiter                    │
│                   （Redis Distributed Token Bucket）          │
│                                                              │
│  每個 tenant_id 有獨立的令牌桶：                              │
│                                                              │
│  Tenant A（標準方案）：                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  bucket_key: "rl:tenant_A:tokens"                   │    │
│  │  capacity: 500,000 tokens/min                       │    │
│  │  current: 423,000 tokens（還有 77,000 可用）         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Tenant B（企業方案）：                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  bucket_key: "rl:tenant_B:tokens"                   │    │
│  │  capacity: 2,000,000 tokens/min                     │    │
│  │  current: 1,800,000 tokens                          │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │ 令牌足夠 → 扣除並放行
                           │ 令牌不足 → 進入佇列
                           ▼
┌──────────────────────────────────────────────────────────────┐
│         Layer 3：Fair-Share Queue（當全域接近滿載時）          │
│                                                              │
│  正常時：請求直接放行                                         │
│                                                              │
│  全域 Quota 使用率 > 80% → 切換為 Fair-Share 模式：          │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  Tenant A 佇列 │  │  Tenant B 佇列 │  │  Tenant C 佇列 │ │
│  │  [req, req, ..]│  │  [req, req, ..]│  │  [req, req, ..]│ │
│  └────────────────┘  └────────────────┘  └────────────────┘ │
│                                                              │
│  Round-Robin 調度：每個租戶的佇列輪流取出一個請求執行         │
│  → 每個租戶都有相等的執行機會，不讓任何一個餓死              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                      Gemini API
```

---

## 三、分散式令牌桶設計

```
Redis 令牌桶的工作原理：

  令牌桶有兩個參數：
  ├── capacity: 桶的最大容量（每分鐘的 token 上限）
  └── refill_rate: 補充速率（每秒補充多少 token）

  例：capacity = 500,000 tokens/min
      refill_rate = 500,000 / 60 = 8,333 tokens/sec

  請求進來時：

  ┌──────────────────────────────────────────────────────┐
  │  ATOMIC OPERATION（Redis 原子操作，防 Race Condition）│
  │                                                      │
  │  1. 計算自上次請求以來補充的 token：                  │
  │     added = (now - last_refill) × refill_rate        │
  │     current_tokens = min(capacity, stored + added)   │
  │                                                      │
  │  2. 判斷是否有足夠 token：                            │
  │     if current_tokens >= requested_tokens:           │
  │         current_tokens -= requested_tokens           │
  │         → 放行                                       │
  │     else:                                            │
  │         → 拒絕或排隊                                 │
  │                                                      │
  │  3. 更新 Redis：                                     │
  │     SET rl:{tenant_id}:tokens {current_tokens}       │
  │     SET rl:{tenant_id}:last_refill {now}            │
  └──────────────────────────────────────────────────────┘

  為什麼用 Redis（而不是應用內存）：
  └── 多個 API Gateway 節點共享同一個 token 桶狀態
  └── 水平擴展後，限流依然準確
  └── Redis 的原子操作（EVAL Lua Script）確保並發安全
```

---

## 四、Token 估算的工程挑戰

```
困難點：請求到達 Rate Limiter 時，還沒呼叫 LLM，
        不知道實際會用多少 token。

解法：事前估算 + 事後校正

事前估算（請求進來時）：

  estimated_input = count_tokens(prompt)  ← 可以精確計算（tiktoken 或 count_tokens API）
  estimated_output = max_output_tokens    ← 使用請求中設定的上限

  estimated_total = estimated_input + estimated_output
  → 在令牌桶中扣除 estimated_total

事後校正（LLM 回應後）：

  actual_total = usage.input_tokens + usage.output_tokens
  difference = estimated_total - actual_total

  if difference > 0:
    → 退回多扣的 token（put back to bucket）
  else:
    → 記錄低估情況（不追補，避免系統複雜化）

設計考量：
  └── 故意略為高估（×1.1~1.2 的安全係數）
  └── 寧可多扣一點，不要讓全域 Quota 超標
  └── 高估導致的額外保守是可接受的 trade-off
```

---

## 五、多層配額設計

```
三層配額體系：

Layer 1：用戶級別（最細粒度）
  └── 每個 user_id 每分鐘的 token 限制
  └── 防止單個用戶在一個租戶內搗亂

Layer 2：租戶級別（核心）
  └── 每個 tenant_id 的月/日/分鐘 token 配額
  └── 對應到客戶的訂閱方案

Layer 3：系統全域（最粗粒度）
  └── 整個 GCP 專案的 Gemini API Quota
  └── 分給各租戶的總和不能超過這個上限

配額層次圖：

  GCP 全域 Quota: 4,000,000 TPM
  ├── 保留緩衝（10%）: 400,000 TPM
  └── 可分配: 3,600,000 TPM
       ├── 企業方案（每個）: 1,000,000 TPM × 2 = 2,000,000
       ├── 標準方案（每個）: 200,000 TPM × 7 = 1,400,000
       └── 小計: 3,400,000 TPM < 3,600,000 ✓

  保留 10% 作為緩衝：
  └── 防止估算誤差導致真正的 429
  └── 緊急情況可以手動釋放給特定租戶
```

---

## 六、Noisy Neighbor Effect 的完整防禦

```
Noisy Neighbor 的攻擊場景：

  Tenant A（惡意或濫用）：
  └── 在 30 秒內發送 20 個「分析 200 頁合約」的請求
  └── 每個請求 200,000 tokens × 20 = 4,000,000 tokens
  └── 等於把整個 GCP 專案的每分鐘 Quota 全耗盡

  Tenant B、C、D（無辜用戶）：
  └── 全部收到 429，業務中斷

防禦機制：

  機制 1：租戶級令牌桶（最關鍵）
  └── Tenant A 自己的 quota 先耗盡（200,000 TPM 標準方案）
  └── 不影響其他租戶的 quota

  機制 2：全域 Quota 使用率監控
  ┌────────────────────────────────────────────────────────┐
  │  使用率 < 70%：正常放行所有請求                         │
  │  使用率 70~90%：啟動 Fair-Share 佇列，每個租戶輪流      │
  │  使用率 > 90%：暫停新請求入隊，等候全域 Quota 恢復      │
  └────────────────────────────────────────────────────────┘

  機制 3：請求大小限制
  └── 單次請求的 estimated_tokens 不得超過租戶配額的 10%
  └── 超大請求強制拆分（由 Agent 框架處理）或拒絕

  機制 4：用戶級 Burst 限制
  └── 單個 user_id 在 10 秒內的請求不得超過 N 個
  └── 防止同一用戶的程序 bug 造成意外的高頻呼叫
```

---

## 七、可觀測性與告警設計

```
監控 Dashboard 核心指標：

  Per-Tenant 視圖：
  ├── Token 消耗速率（TPM）：即時趨勢圖
  ├── 配額使用百分比：離閾值多遠？
  ├── 被限流的請求數（429 rate）：是否有用戶受影響？
  └── 佇列等待時間：Fair-Share 佇列有多長？

  全域視圖：
  ├── GCP API 配額使用率
  ├── Top 10 Token 消耗租戶
  └── 系統整體 p95 延遲趨勢

告警規則：
  ├── 任何租戶的 429 rate > 5% → 通知客戶成功團隊
  ├── 全域 Quota 使用率持續 > 85% → 工程師告警（可能需要升級配額）
  └── 單一租戶 10 分鐘內消耗超過每日配額的 30% → 異常使用告警
```

---

## 八、面試答題要點

> *「這個問題的根本是：AI 系統的資源消耗由 Token 數而非請求次數決定，傳統 RPM 限流完全失效。*
>
> *架構設計三層：入口閘道做 Token 估算（請求進來時估算 input + max_output），每個租戶有獨立的分散式令牌桶（Redis Token Bucket），全域 Quota 接近滿載時切換為 Fair-Share 佇列（Round-Robin 跨租戶調度）。*
>
> *關鍵設計細節：Redis 的 Lua Script 確保令牌桶操作的原子性；事前高估 token（×1.1 安全係數）、事後退回多扣的 token；租戶配額分配時保留 10% 全域緩衝。*
>
> *Noisy Neighbor 防禦：租戶級令牌桶確保 Tenant A 的濫用不佔用其他租戶的 Quota；全域使用率超過 90% 時暫停新請求入隊；加上單次請求大小上限。」*

---

**系列導覽：**  
← [（二十二）RKK 實戰：動態並行 Tool-Calling 與依賴解析引擎](../fde-interview-guide-part22-parallel-tool-calling-zh/)  
→ [（二十四）RKK 實戰：混合模型路由與語意路由器設計](../fde-interview-guide-part24-hybrid-model-routing-zh/)
