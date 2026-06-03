---
title: "FDE 面試準備指南（十八）：RKK 實戰——三層記憶體架構與 LLM 成本調優"
date: 2026-06-04T11:00:00+08:00
draft: false
description: "以系統設計視角拆解企業級 Agent 的三層記憶體設計：Working Memory 成本控制、Semantic Long-term Memory 的異步壓縮流程、Profile Memory 的結構化提取——以及每個設計決策背後的成本與延遲 trade-off"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Memory", "Cost Optimization", "Context Cache", "LLM", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> 「把所有歷史對話塞進 Context 再問 LLM」  
> ——這個方案在 demo 時可以，在生產環境裡三個月後會讓你的帳單嚇一跳。  
> 三層記憶體設計的核心不是「記更多」，而是「用最低的 token 成本，讓 Agent 感覺上記得一切」。

---

## 面試情境

> **面試官：** 「這個 Agent 需要維護與大客戶長達三個月的商務對話。如果把所有歷史對話和工具調用結果全部當 Context 塞給 Gemini，Cost-per-request 會暴增，Tokens/sec 吞吐量大幅下滑。請設計一個三層記憶體架構平衡成本與延遲。」

---

## 一、核心問題：Context 成本為什麼會失控

先量化問題的規模：

```
典型企業客戶的對話規模估算：

  每輪對話約 500 tokens（user + assistant + tool calls）
  每天溝通 10 輪
  三個月（90 天）= 900 輪 = 450,000 tokens 的歷史對話

如果全部塞入 Context：

  每次請求的 input tokens：
  ├── System Prompt:      500 tokens
  ├── 三個月歷史對話: 450,000 tokens
  ├── 當次查詢:          100 tokens
  └── 總計:          ~450,600 tokens

  成本（Gemini 1.5 Pro，$1.25/1M）：
  └── 每次請求 $0.56，一天 10 次 = $5.6/天/客戶

  100 個客戶 × $5.6 = $560/天 = $16,800/月
  ↑ 這還不算 output token
```

**三個連帶問題：**

```
問題 1：成本（已如上計算）

問題 2：延遲
  Attention 複雜度是 O(n²)，n = context 長度
  450K tokens 的推理時間 vs 5K tokens：慢 ~10-50x
  TTFT（Time to First Token）從 0.5 秒變成 5-20 秒

問題 3：品質下降（Lost-in-the-Middle）
  LLM 對 Context 中間部分的注意力顯著弱化
  450K tokens 的 Context → 三個月前的重要決策被「忽略」
  → 用更少、更精準的 Context 反而效果更好
```

---

## 二、三層記憶體架構設計

```
┌──────────────────────────────────────────────────────────────┐
│                    用戶請求                                   │
│                    User Query                                │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Layer 1：Working Memory（工作記憶）              │
│                                                              │
│  最近 5~10 輪的完整對話                                       │
│  ├── 直接存在 Redis（Session Cache）                          │
│  ├── 利用 Vertex AI Context Caching 降低重複計算成本           │
│  └── Token 上限：~5,000 tokens（可控、快速）                  │
│                                                              │
│  TTL：當次 Session（幾分鐘~幾小時）                           │
└──────────────────────────┬───────────────────────────────────┘
                           │ Context hit → 直接注入
                           │ Context miss → 向下查詢
                           ▼
┌──────────────────────────────────────────────────────────────┐
│          Layer 2：Semantic Long-term Memory（情節記憶）        │
│                                                              │
│  向量化的歷史對話摘要                                          │
│  ├── 異步壓縮管線：舊對話 → LLM 摘要 → Embedding → 向量 DB   │
│  ├── 按語意相似度召回：top-k 相關摘要                          │
│  └── Token 上限：~2,000 tokens（精選的相關記憶）              │
│                                                              │
│  存儲：Vertex AI Vector Search / Firestore + pgvector        │
│  TTL：長期（可設 180 天 decay）                               │
└──────────────────────────┬───────────────────────────────────┘
                           │ 用當前 Query 做 Semantic Search
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             Layer 3：Profile Memory（實體記憶）               │
│                                                              │
│  結構化的 Key-Value 用戶資訊                                  │
│  ├── 由 Extraction Agent 定時從對話中提煉                     │
│  ├── 例：{ "preferred_shipping": "DHL",                      │
│  │         "budget_limit": 50000,                            │
│  │         "decision_maker": "Alice Chen" }                  │
│  └── 每次請求固定帶入（幾百 tokens，固定成本）                  │
│                                                              │
│  存儲：Firestore（結構化，可直接查詢）                         │
│  更新：非同步，每次對話結束後觸發提取                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  組合後的 Working Context                     │
│                                                              │
│  [System Prompt]            ~500 tokens  （固定）            │
│  [Profile Memory]           ~300 tokens  （固定）            │
│  [Semantic Memory Recall]  ~2,000 tokens （按需）            │
│  [Working Memory]          ~3,000 tokens （滾動）            │
│  [Current Query]            ~100 tokens  （即時）            │
│  ───────────────────────────────────────                    │
│  Total:                    ~5,900 tokens  ← 三個月都這樣！   │
└──────────────────────────────────────────────────────────────┘

對比：5,900 tokens vs 450,000 tokens
成本降低：~98.7%
```

---

## 三、Layer 2 的核心機制：異步壓縮管線

```
對話結束後，非同步觸發：

最近的對話歷史
      │
      ▼ （Cloud Pub/Sub 觸發異步任務）
┌───────────────────────────────────────────────────────┐
│               Summarization Pipeline                  │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Summarization LLM（Gemini Flash，低成本）       │  │
│  │                                                 │  │
│  │  Prompt：「請從以下對話中提取：                  │  │
│  │  1. 達成的決策和承諾                             │  │
│  │  2. 未解決的問題                                 │  │
│  │  3. 重要的數字和事實（金額、日期、產品）          │  │
│  │  4. 客戶表達的偏好和限制」                       │  │
│  └─────────────────────────────────────────────────┘  │
│                        │                              │
│                        ▼                              │
│  摘要文本（~200 tokens，壓縮自 3,000 tokens）           │
│                        │                              │
│                        ▼                              │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Embedding Model（text-embedding-004）           │  │
│  │  → 轉換為向量                                    │  │
│  └─────────────────────────────────────────────────┘  │
│                        │                              │
│                        ▼                              │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Vector Database（Vertex AI Vector Search）      │  │
│  │  → 存入，附帶 metadata：                         │  │
│  │     { user_id, session_id, timestamp,            │  │
│  │       importance_score, topics: [...] }          │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

**為什麼用異步而不是同步？**

```
同步壓縮的問題：
  用戶發出請求 → 等待對話壓縮 → 等待 Embedding → 才能回應
  增加了 300~800ms 的延遲，用戶感知明顯

異步壓縮的設計：
  用戶發出請求 → 立即從現有 Cache 組裝 Context → 立即回應
  對話結束後（或背景觸發）→ 壓縮任務進入 Queue → 不影響用戶
```

---

## 四、Vertex AI Context Caching：降低 Working Memory 成本

```
沒有 Context Cache 的情況：

  Request 1: [System(500)] + [History(3000)] + [Query(100)] = 3,600 tokens 計費
  Request 2: [System(500)] + [History(3100)] + [Query(100)] = 3,700 tokens 計費
  Request 3: [System(500)] + [History(3200)] + [Query(100)] = 3,800 tokens 計費
                                                                    ↑
                                                         System Prompt 每次都重複計費！

有 Context Cache 的情況：

  首次：建立 Cache，System Prompt + Profile (800 tokens)
        費用：$0.001（建立 cache 的一次性費用）

  Request 1: [Cached(800)] + [History(2200)] + [Query(100)] = 3,100 tokens
             但 Cached 部分 費率是正常的 1/4
             → 800 × 0.25 + 2,300 × 1.0 = 2,500 effective tokens

  Request 2,3,...: 每次都享受 Cache 折扣

成本節省估算（System Prompt 500 tokens，每天 20 次請求）：
  無 Cache：500 × 20 = 10,000 tokens/天 × $1.25/1M = $0.0125/天
  有 Cache：500 × 20 × 0.25 = 2,500 tokens/天 × $1.25/1M = $0.003/天
  節省 76%（在這個部分）
```

---

## 五、Layer 3 的設計：Extraction Agent

```
Extraction Agent 的工作流程：

觸發條件：
  ├── 每次對話結束後（非同步）
  ├── 對話輪次達到 N 輪時
  └── 用戶明確提到新的偏好時（實時觸發）

Extraction Agent 的 Prompt 設計：

「請從以下對話中，提取可能對未來對話有用的結構化資訊。
 只提取明確陳述的事實，不要推測。
 
 對話內容：{recent_conversation}
 
 請以 JSON 格式輸出（只輸出有新資訊的欄位）：
 {
   "shipping_preference": null or "DHL/FedEx/...",
   "budget_limit": null or number,
   "decision_makers": null or [names],
   "pain_points": null or [strings],
   "product_interests": null or [strings]
 }」

Profile Update 邏輯：
  ├── 新提取的欄位 → 更新 Firestore
  ├── 衝突（新舊不同）→ 新值優先 + 記錄歷史
  └── 空值（null）→ 不更新，保留舊值
```

---

## 六、成本對比總結

```
架構方案成本比較（100 企業客戶 × 3 個月歷史）：

方案 A：Full Context（把所有歷史塞進去）
  每次 input：~450,000 tokens
  成本/請求：$0.56
  每月（100 客戶 × 10 請求/天）：$16,800

方案 B：三層記憶體架構
  每次 input：~5,900 tokens
  成本/請求：$0.0074
  每月（100 客戶 × 10 請求/天）：$222

節省：98.7%（$16,578/月）
品質：因 Lost-in-the-Middle 效應減少，實際上可能更好

TTFT 改善：
  方案 A：5~20 秒（450K tokens 的 attention 計算）
  方案 B：0.3~0.8 秒（5.9K tokens）
```

---

## 七、面試答題要點

> *「這個問題的核心是：用最少的 token 讓 LLM 感覺上記得三個月的對話。我的設計是三層記憶體：*
>
> *Layer 1，Working Memory：最近 5~10 輪完整對話存在 Redis，利用 Vertex AI Context Caching 讓 System Prompt 的 token 費用降低 75%。*
>
> *Layer 2，Semantic Long-term Memory：對話結束後，異步用 Gemini Flash 壓縮成摘要、向量化後存入 Vertex AI Vector Search。下次對話時，用當前 Query 做語意搜尋，召回最相關的 3~5 條歷史摘要（約 2,000 tokens）。*
>
> *Layer 3，Profile Memory：Extraction Agent 從對話中提煉結構化的 Key-Value 客戶資訊，存入 Firestore，每次對話固定帶入（約 300 tokens，成本完全可預測）。*
>
> *三層合計約 5,900 tokens，對比全部塞入的 450,000 tokens，成本降低 98.7%，TTFT 從 5~20 秒降到 0.3~0.8 秒。」*

---

**系列導覽：**  
← [（十七）RKK 實戰：MCP 伺服器、Tool-Calling 安全與 OAuth 授權](../fde-interview-guide-part17-mcp-tool-oauth-zh/)  
→ [（十九）RKK 實戰：Multi-Agent 的統計評估與細粒度追蹤](../fde-interview-guide-part19-multiagent-eval-tracing-zh/)
