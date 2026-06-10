---
title: "FDE 面試準備指南（十五）：RKK 實戰——AI Agent 規模化與 Cache 策略"
date: 2026-06-03T14:00:00+08:00
draft: false
weight: 15
description: "以系統設計視角拆解 AI Agent 的規模化挑戰：為什麼 LLM 系統的擴展和傳統 Web 不同、三層 Cache 各解決什麼問題、Stateful Agent 怎麼做水平擴展——含完整架構圖與成本估算框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Scale", "Cache", "KV Cache", "Semantic Cache", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> 把 Agent 從 1 個用戶擴展到 10 萬個用戶，  
> 傳統 Web 的直覺在這裡會讓你踩坑。  
> LLM 系統的瓶頸不在 CPU，而在 **token 計算成本** 和 **推理延遲**。

---

## 一、核心問題：LLM 系統的規模化為什麼不一樣

傳統 Web 服務的規模化直覺：

```
流量增加 → 多加幾台 server → 問題解決
成本模型：主要是 infra 成本，基本線性
```

LLM 系統的規模化現實：

```
流量增加 → 每個請求都要花錢叫 LLM API
成本模型：token 按量計費，和傳統 infra 的成本結構完全不同

10K req/day × avg 3,000 tokens × $0.002/1K tokens = $60/day = $1,800/month
100K req/day = $18,000/month
1M req/day  = $180,000/month   ← 沒有 cache，就是這個數字
```

**三個讓 LLM 系統難以規模化的特性：**

1. **高延遲**：每次推理 2~10 秒，無法靠多線程魔法解決
2. **成本與請求線性相關**：不像傳統服務有邊際成本遞減
3. **有狀態**：對話歷史、Session State、Memory——都是狀態，水平擴展不直接

---

## 二、規模化的核心策略：減少不必要的 LLM 呼叫

```
總請求量
    │
    ├── 能用 Cache 回答？ → Cache hit → 直接返回（0 LLM 成本）
    │
    ├── 能降低 Token 數？ → 縮短 context → 同樣呼叫，更低成本
    │
    └── 真正需要 LLM 推理 → 呼叫 LLM → 計費

目標：讓「真正需要 LLM 推理」的比例盡量低
```

---

## 三、三層 Cache 架構

```
請求進來
    │
    ▼
┌───────────────────────────────────────────────────────┐
│  L1：Application Cache（Redis）                        │
│                                                       │
│  用途：Hot queries exact match + Session State        │
│  命中條件：完全相同的查詢                               │
│  TTL：5~15 分鐘                                        │
│  預期 hit rate：~15%                                   │
│  延遲：< 5ms                                           │
└───────────────────────────┬───────────────────────────┘
                            │ miss
                            ▼
┌───────────────────────────────────────────────────────┐
│  L2：Semantic Cache（Vector DB）                       │
│                                                       │
│  用途：語意相似的問題複用答案                           │
│  命中條件：cosine similarity ≥ 0.92                   │
│  TTL：1~24 小時（依問題類型）                          │
│  預期 hit rate：~35%（FAQ 類場景可達 50%+）            │
│  延遲：50~150ms（含 embedding + 向量搜尋）             │
└───────────────────────────┬───────────────────────────┘
                            │ miss
                            ▼
┌───────────────────────────────────────────────────────┐
│  L3：KV Cache（LLM Provider 層）                       │
│                                                       │
│  用途：固定 prefix（system prompt + 知識庫）不重複計算  │
│  命中條件：LLM provider 自動處理                       │
│  成本節省：prefix token 費用降低 75%                   │
│  延遲改善：TTFT（第一個 token 的延遲）顯著降低         │
└───────────────────────────┬───────────────────────────┘
                            │ miss（真正的 LLM 推理）
                            ▼
                   ┌──────────────┐
                   │  LLM 推理    │
                   │  （計費）    │
                   └──────────────┘
                            │
                    ← 結果回寫 L1 + L2
```

---

## 四、Semantic Cache 的設計細節

### 核心問題：相同語意，不同文字，應該命中嗎

```
Query A：「Q4 銷售數字是多少？」  ← 存入 cache
Query B：「Q4 的銷售業績？」      ← 應該命中 Query A 的結果嗎？

傳統 Exact Match：不命中（文字不同）
Semantic Cache：命中（語意相似，cosine similarity = 0.94）
```

### 相似度閾值的 Trade-off

```
閾值 0.95：保守策略
  + 幾乎不會回傳錯誤的快取答案
  - Hit rate 低，省錢效果有限
  → 適合：答案精確性要求高的場景（財務數字、法規查詢）

閾值 0.90：平衡策略（推薦起點）
  + 命中大多數語意相近的查詢
  - 偶爾可能把問法相似但答案不同的問題搞混
  → 適合：企業 FAQ、知識庫問答

閾值 0.85：激進策略
  + Hit rate 最高
  - 誤命中風險明顯，需要大量測試驗證
  → 不推薦，除非問題領域非常同質化
```

### 什麼不應該被 Cache

```
適合 Cache：
  ✓ FAQ、產品規格、政策說明  ← 答案穩定，問法多樣
  ✓ 定義類問題                ← "什麼是 XYZ？"
  ✓ 歷史資料查詢              ← 上個月的數字不會變

不適合 Cache：
  ✗ 個人化回答（依賴 user profile）   ← 不同用戶答案不同
  ✗ 即時資料（庫存、股價、天氣）       ← 資料時效性要求高
  ✗ 有副作用的操作（發 email、下訂單） ← 絕對不能快取
```

---

## 五、KV Cache：LLM 推理層的加速

### 什麼是 KV Cache

```
LLM 的 Attention 計算：
  每個 token 需要知道「自己和所有前面 token 的關係」
  → 計算量 O(n²)，n = context 長度

沒有 KV Cache：
  請求 1：[System Prompt(500t)] + [Query A(50t)]
          → 所有 550 tokens 都要重新計算

  請求 2：[System Prompt(500t)] + [Query B(50t)]
          → System Prompt 的 500 tokens 又算了一遍！

有 KV Cache：
  請求 1：[System Prompt(500t)] + [Query A(50t)]
          → System Prompt 計算並快取
          → 只需算新增的 50 tokens

  請求 2：[System Prompt(500t)] + [Query B(50t)]
          → System Prompt 的計算結果從 cache 讀取 ← 節省了
          → 只需算新增的 50 tokens
```

### Gemini Context Caching 的使用時機

```
KV Cache 的成本結構（以 Gemini 1.5 Pro 為例）：

沒有 cache：
  每次請求 input cost = total_tokens × $1.25/1M

有 cache（Vertex AI Context Cache）：
  建立 cache：cached_tokens × $1.25/1M（一次性費用）
  後續請求：cached_tokens × $0.31/1M（便宜 4 倍）
             + new_tokens × $1.25/1M

划算的條件：
  同一個 prefix 被使用 2+ 次 → KV Cache 就開始省錢
  prefix 越長（50K+ tokens）、使用次數越多 → 越划算

不划算的條件：
  每個請求的 prefix 都不同（高個人化場景）
  → Cache 建了就沒人用，純額外成本
```

---

## 六、水平擴展：Stateful Agent 的挑戰

### 問題所在

```
傳統 Web 服務（Stateless）：
  User → Load Balancer → Server A
  User → Load Balancer → Server B   ← 任一台都能回答

Agent（Stateful）：
  Session 1 在 Server A 上 → 有 context
  Session 2 的請求到 Server B → B 沒有 context → 失敗！
```

### 解法：外部化所有狀態

```
錯誤設計（狀態在 instance 裡）：
┌────────────────────────────────────────────────────┐
│ Server A                                           │
│   session_store = {                                │
│     "session_001": {"history": [...], "state": {}}│  ← 這台掛了，資料就沒了
│   }                                                │
└────────────────────────────────────────────────────┘

正確設計（狀態外部化）：
┌──────────────────────────────────────────────────────────┐
│  Load Balancer                                           │
└────────────────┬─────────────────────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌────────┐
│Server A│  │Server B│  │Server C│  ← 全部無狀態
└────┬───┘  └────┬───┘  └────┬───┘
     └───────────┼────────────┘
                 │ 全部讀寫同一個外部存儲
                 ▼
┌──────────────────────────────────────────────────────────┐
│              External State Store                        │
│                                                          │
│  ┌──────────────────────────┐  ┌────────────────────┐    │
│  │  Redis                   │  │  Vector DB         │    │
│  │  Session state           │  │  Episodic Memory   │    │
│  │  Hot query cache         │  │  Semantic Cache    │    │
│  └──────────────────────────┘  └────────────────────┘    │
│  ┌──────────────────────────┐                            │
│  │  PostgreSQL / Firestore  │                            │
│  │  User profiles           │                            │
│  │  Semantic Memory         │                            │
│  └──────────────────────────┘                            │
└──────────────────────────────────────────────────────────┘
```

**好處：**
- 任意 instance 可以處理任意 session
- Instance 掛了不影響 session（狀態在外部）
- 可以根據流量自由增減 instance

---

## 七、成本估算框架（面試必備）

面試官問「你怎麼估算這個系統的成本」——用這個框架：

```
Step 1：估算請求規模
  DAU × 平均請求次數/人 = 每日總請求數

Step 2：估算每次請求的 token 數
  input_tokens = system_prompt + retrieved_context + history + query
  output_tokens = 平均回答長度

Step 3：計算無 cache 的成本
  daily_cost = requests × (input_tokens × input_price + output_tokens × output_price)

Step 4：估算 Cache 節省
  L1 hit rate × 節省比例 + L2 hit rate × 節省比例 + KV Cache 節省

Step 5：算出最終成本和 ROI
```

**範例（10 萬 DAU 的 RAG Agent）：**

```
規模估算：
  100K DAU × 3 req/人 = 300K req/day

Token 估算：
  input:  2,500 tokens/req（system 500 + RAG 1500 + history 400 + query 100）
  output:   400 tokens/req

無 cache 月成本（Gemini Flash，$0.075/1M input, $0.30/1M output）：
  input:  300K × 2500 / 1M × $0.075 × 30 = $169/month
  output: 300K × 400  / 1M × $0.300 × 30 = $1,080/month
  total:  ~$1,249/month

加入 Cache 後：
  L1 hit rate 15%:  省 $1,249 × 15% ≈ $187
  L2 hit rate 35%:  省 $1,249 × 35% ≈ $437
  KV Cache（prefix 75% 便宜）: 省 input 的 ~60% ≈ $101
  估算月節省：~$725（省 58%）
  最終月成本：~$524
```

---

## 八、Cache Invalidation：最難的問題

```
Cache Invalidation 的三種情況：

1. 知識庫更新
   └─ 產品規格改了 → Semantic Cache 裡的舊答案需要失效
   └─ 解法：更新知識庫時，按 topic 批量清除相關 cache

2. 個人化資料更新
   └─ User profile 變了 → 個人化回答的 cache 需要失效
   └─ 解法：個人化回答不進共享 cache，或以 user_id 為 key

3. 時效性資料
   └─ 庫存、股價等即時資料
   └─ 解法：這類查詢根本不應該進 cache（直接跳過 L2）
```

---

## 九、面試答題框架：CAPE

```
C → Capacity    估算請求量、token 量、無 cache 基線成本
A → Architecture 三層 cache + 外部化狀態的擴展架構
P → Performance  各層 hit rate + 成本節省估算
E → Edge Cases   cache invalidation、冷啟動、個人化問題
```

**完整範例回答：**

> *「先估算規模。10 萬 DAU，每人 3 次查詢，30 萬請求/天。Gemini Flash 每月基線成本約 $1,200，這驅動了 cache 設計的必要性。*
>
> *架構上我會做三層：L1 Redis 做 exact match 的 hot query cache（15% hit rate）；L2 Semantic Cache 用向量相似度複用語意相近的答案（35% hit rate）；L3 Vertex AI Context Cache 把固定的 system prompt 和 RAG 知識庫 prefix 快取，prefix token 成本降低 75%。*
>
> *Agent instance 本身完全無狀態，session state 和 memory 全部外部化到 Redis 和向量資料庫，可以自由水平擴展。*
>
> *三層 cache 合計月節省約 58%，從 $1,200 降到 $500 左右。*
>
> *邊界情況：知識庫更新時需要清除相關 Semantic Cache；個人化回答不進共享 cache，以 user_id 為 key 隔離。」*

---

## 十、快速複習卡

```
LLM 規模化的三個不同點：
  成本與請求線性相關 / 高延遲 / Stateful

三層 Cache：
  L1 Redis         → Exact match，< 5ms
  L2 Semantic Cache → 語意相似，50~150ms，threshold 0.90~0.92
  L3 KV Cache      → LLM prefix 共享，prefix tokens 省 75%

Stateful 的水平擴展：
  外部化所有狀態（Redis + Vector DB + PostgreSQL）
  Agent instance 本身無狀態 → 任意擴展

成本估算：規模 × token 數 × 單價 × Cache 節省率

CAPE 框架：Capacity → Architecture → Performance → Edge Cases
```

---

**系列導覽：**  
← [（十四）RKK 實戰：AI Agent Memory 架構設計](../fde-interview-guide-part14-memory-architecture-zh/)  
← [系列首篇：（一）RAG 完全攻略](../fde-interview-guide-part1-rag-zh/)
