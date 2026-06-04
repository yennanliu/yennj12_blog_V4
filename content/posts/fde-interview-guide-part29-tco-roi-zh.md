---
title: "FDE 面試準備指南（二十九）：顧問實戰——AI 系統 TCO 估算與 ROI 說服框架"
date: 2026-06-04T20:30:00+08:00
draft: false
description: "以 Google FDE 顧問視角拆解 AI 系統的總持有成本（TCO）估算方法：Token 成本、Infra 成本、人力成本的計算框架、如何用 ROI 語言說服財務決策者，以及 Vertex AI 定價模型的實際試算"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Consultant", "TCO", "ROI", "Pricing", "Vertex AI", "GCP", "Cost Optimization", "Interview", "Google", "RKK"]
authors: ["yen"]
readTime: "15 min"
---

> 工程師說：「這個架構非常優雅。」  
> 財務長說：「一個月要多少錢？」  
> FDE 說：「我來幫你們算。如果這個系統每個月省下 X 小時的人力，  
> 以你們現在的薪資結構，大概幾個月可以回收建置成本。」  
> 這個對話，決定了 POC 之後有沒有預算繼續做。

---

## 面試情境

> **面試官：**「客戶問你：我們要在 Vertex AI 上部署一個 RAG-based 客服 Agent，每天大概 10,000 個 query，一個 query 平均 2,000 input token 和 500 output token。一個月的 API 成本是多少？如果我們加了一個 Embedding 服務和向量資料庫，總體的 TCO 是什麼？我要拿這個數字去說服 CFO。」

---

## 一、為什麼 FDE 必須會算成本

```
技術架構決定成本結構：

你選 Gemini 1.5 Pro vs Gemini 1.5 Flash → 成本差 5 倍
你選 Vertex AI Vector Search vs pgvector → 成本和維護方式不同
你選 Cloud Run vs GKE → Infra 成本和工程複雜度不同

如果 FDE 說不出成本，客戶只能靠自己估算。
自己估出來的數字通常是錯的（太高或太低），
都可能導致預算批不下來，或者上線後超支被投訴。

FDE 的價值之一，就是幫客戶算出一個可信的數字，
並且告訴他怎麼優化。
```

---

## 二、AI 系統的 TCO 三個層次

```
Layer 1：LLM API 成本（最容易算）
  ├── Input token 成本
  ├── Output token 成本
  └── Embedding token 成本

Layer 2：Infra 成本（第二容易算）
  ├── Vector Database（託管服務 or 自建）
  ├── Compute（Cloud Run / GKE for orchestration）
  ├── Storage（GCS for documents）
  └── Network（Egress fees）

Layer 3：人力成本（最容易被忽略）
  ├── 建置成本（Engineer 時間）
  ├── 維護成本（每月運維時間）
  └── Prompt 維護成本（調整和迭代）
```

---

## 三、實際試算：10,000 queries/day RAG Agent

### Step 1：LLM API 成本

```
Gemini 1.5 Pro 定價（2026 年參考）：
  Input：$3.50 per 1M tokens
  Output：$10.50 per 1M tokens

每個 Query 的 Token 分解：
  System Prompt：500 tokens
  Retrieved Context（3 個 Chunk × 400 tokens）：1,200 tokens
  User Query：300 tokens
  Input 合計：2,000 tokens

  Answer 生成：500 tokens（output）

每日成本計算：
  Input cost：10,000 queries × 2,000 tokens × $3.50/1M
           = 10,000 × 0.002 × $3.50 = $70/day

  Output cost：10,000 queries × 500 tokens × $10.50/1M
            = 10,000 × 0.0005 × $10.50 = $52.5/day

  每日 LLM 成本：$122.5/day
  每月 LLM 成本：$122.5 × 30 ≈ $3,675/month
```

### Step 2：Embedding 成本

```
每個 Query 需要 Embedding 1 次（把 query 轉成向量）：
  text-embedding-004 定價：$0.025 per 1M tokens

  每日 Embedding：10,000 × 300 tokens × $0.025/1M
               = 10,000 × 0.0003 × $0.025 ≈ $0.075/day

  每月 Embedding：$0.075 × 30 ≈ $2.25/month（可忽略）

另外：文件 Indexing（一次性成本）
  假設 50,000 個 Chunk，每個 400 tokens：
  50,000 × 400 × $0.025/1M = $0.50（一次性）
```

### Step 3：Vector Database 成本

```
選項 A：Vertex AI Vector Search（全託管）
  費用結構：
  ├── Index size：$0.08 per GB per hour（Node 費用）
  ├── Query：$0.30 per 1M queries
  └── 假設 1M 個向量（384 維），約 1.5GB 索引

  估算：
  Node 費用：1.5GB × $0.08 × 720小時 ≈ $86/month
  Query 費用：10,000 × 30 / 1M × $0.30 ≈ $0.09/month
  小計：約 $86/month

選項 B：pgvector on Cloud SQL（更便宜，但需要自己管）
  Cloud SQL db-standard-1（1 vCPU, 3.75GB RAM）：
  ≈ $50/month（us-central1）
  需要工程師維護備份、Index 最佳化等

選項 C：Pinecone（第三方，不在 GCP）
  Starter（100K vectors free）→ Standard $70/month/1M vectors
  注意：資料出 GCP 有 egress 費用
```

### Step 4：Orchestration Infra 成本

```
Cloud Run（RAG Orchestration Service）：
  假設平均 2 個 CPU instances 跑 8 小時（白天）：
  CPU：2 × 1 vCPU × 8hr × 30days × $0.00002400/vCPU-second
     = 2 × 28,800s × 30 × $0.000024 ≈ $41.5/month
  Memory：2 × 2GB × $0.00000250/GB-second
        ≈ $8.6/month
  Cloud Run 小計：≈ $50/month

GCS（文件儲存）：
  假設 5GB 文件：5 × $0.020 = $0.10/month（可忽略）

Egress（如果 Pinecone 在 GCP 外）：
  假設每個 Embedding 200 bytes × 10,000 × 30 = 60MB
  GCP Egress：60MB × $0.12/GB ≈ $0.007/month（可忽略）
```

### 月成本總結

```
┌────────────────────────────────────────────────────────┐
│  成本項目                            月費用              │
├────────────────────────────────────────────────────────┤
│  Gemini 1.5 Pro（LLM）               $3,675            │
│  Embedding（text-embedding-004）     $2               │
│  Vertex AI Vector Search             $86              │
│  Cloud Run（Orchestration）          $50              │
│  其他（GCS、Logging、Monitoring）    $20              │
├────────────────────────────────────────────────────────┤
│  合計                                $3,833/month      │
└────────────────────────────────────────────────────────┘

建置成本（一次性）：
  工程師 2 人 × 3 週 × $X/週（依客戶情況）
  ≈ 約 $20,000-$40,000（視市場行情）
```

---

## 四、成本優化選項（給客戶看的）

```
優化方向 1：改用 Gemini 1.5 Flash（成本降低 5 倍）
  Flash 定價：Input $0.075/1M, Output $0.30/1M
  月 LLM 成本：約 $735/month
  
  什麼時候適合：
  ├── FAQ 問答（答案較固定）
  ├── 簡單的文件摘要
  └── 不需要複雜推理的場景
  
  代價：回答品質略低，複雜問題可能需要更多 context

優化方向 2：Prompt Caching
  Google Vertex AI 支援 Context Caching：
  如果 System Prompt + FAQ 文件（固定部分）可以 Cache，
  Cache hit 後 Input token 成本降低 75%
  
  # 使用 Vertex AI Caching API
  from vertexai.preview import caching
  
  cached_content = caching.CachedContent.create(
      model_name="gemini-1.5-pro-001",
      system_instruction=SYSTEM_PROMPT,
      contents=[fixed_context],  # 固定的 FAQ context
      ttl=datetime.timedelta(hours=24),
  )
  
  # 後續 request 引用 cache
  response = model.generate_content(
      user_query,
      cached_content=cached_content,
  )
  
  潛在節省：如果 1,500 tokens 是固定 context，
  每月節省：1,500 × 10,000 × 30 × 75% × $3.5/1M
          ≈ $1,181/month

優化方向 3：Committed Use Discount（CUD）
  如果月用量穩定，可以簽 1 年 CUD：
  通常節省 20-40%
  LLM 成本從 $3,675 降到約 $2,200-2,940/month
```

---

## 五、ROI 框架：用業務語言說服 CFO

成本算出來了，但 CFO 問的是：**這個投資值得嗎？**

```
ROI 計算的三個面向：

面向 1：人力成本節省（最容易量化）

現況：
  10 位客服人員 × $50,000 年薪 = $500,000/年人力成本
  每天 10,000 個 query，每位客服每天處理 200 個
  其中 60% 是可以自動化的 FAQ 類問題（6,000 queries/day）

導入 AI Agent 後：
  AI 自動處理 6,000 個 FAQ queries（準確率 85%）
  剩餘 4,000 個複雜問題 + AI 無法處理的 → 人工處理
  人力需求從 10 人降至 6 人（保守估計）
  
  節省人力成本：4 人 × $50,000 = $200,000/年

AI 系統成本：$3,833/month × 12 = $46,000/年

淨節省：$200,000 - $46,000 = $154,000/年
ROI：154,000 / 46,000 = 335%（年化）
回收期：46,000 / (200,000/12) ≈ 2.8 個月

面向 2：回應速度改善（間接影響客戶滿意度）

現況：人工回應平均 4 小時（含排隊等待）
導入後：AI 即時回應（< 1 秒），人工處理降到平均 30 分鐘
可量化：每提升 1% 的客戶滿意度，
        依行業研究，對應約 X% 的續約率提升

面向 3：擴展能力（人力無法做到的）

現況：夜間無客服（晚上 10 點到早上 9 點）
導入後：24/7 自動回應
量化：夜間時段佔每日查詢量 15%（1,500 queries）
      這 1,500 個問題之前完全沒有回應
```

---

## 六、給 CFO 的一頁式說法

```
不要給 CFO 看 token 計費表。給他看這個：

──────────────────────────────────────
  AI 客服 Agent 投資分析（摘要）

  每月運營成本：$3,833
  預估年化成本：$46,000
  
  主要節省來源：
  ├── 人力優化：$200,000/年（節省 4 個 FTE）
  ├── 24/7 服務能力：夜間 1,500 queries 獲得即時回應
  └── 一致性改善：自動化 FAQ 回答誤差率 < 5%
  
  淨年化 ROI：335%
  預估回收期：3 個月
  
  建議：
  三週 POC 驗證準確率目標（≥85%），
  POC 成本約 $5,000（含建置和測試）。
  POC 成功後啟動全量部署。
──────────────────────────────────────
```

---

## 七、面試回答的關鍵訊號

```
面試官想聽到的不是精確數字，而是你的計算思路：

「我會分三個層次估算：

第一層是 LLM API 成本，這個最容易算——
每個 query 的 token 數乘以定價，乘以 query 量。
10,000 queries × 2,500 tokens × Gemini 1.5 Pro 的定價，
大約是每月 $3,700 左右。

第二層是 Infra 成本——Vector DB、Compute、Storage——
這部分通常是 LLM 成本的 10-20%，大約 $150/month。

第三層是人力成本——這個是最容易被忽略但最重要的——
包含建置的工程師時間和後續維護。

加總起來，月運營成本大概 $4,000。
然後我會拿這個數字對比客戶現在的人力成本，
算出 ROI 和回收期，這才是 CFO 需要看的數字。

另外我會建議他們先試試 Gemini Flash 版本，
成本可以降到 $1,000/月，先驗證業務價值再決定要不要升級到 Pro。」
```

---

**成本估算不是財務分析師的工作。**  
**它是 FDE 幫助客戶做決策的工具。**  
**會算，才能推進。**
