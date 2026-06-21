---
title: "AI 工程從零開始｜Phase 17 Part 3：AI 成本優化與規模化 — 把每美元壓榨到極限"
date: 2026-06-22T03:30:00+08:00
draft: false
weight: 38
description: "深入解析 AI 生產成本工程：Token 成本分解、快取策略（Semantic Cache/Prompt Cache）、模型路由、批次推論、Spot GPU 與 FinOps for AI"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Infrastructure", "Cost Optimization", "FinOps", "Caching", "Model Routing", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> 大多數團隊看到 AI 帳單飆升，第一反應是「換便宜的模型」。
> 但換模型只是換藥不換病：根本問題是沒有成本工程的思維。
> 正確答案是把 AI 推論視為可測量、可分解、可優化的工程系統——
> 從 Token 單位經濟學到快取命中率，每個數字都是槓桿點。

---

## 面試情境

> 你的 RAG 系統每月 AI API 費用從 $3,000 暴增到 $47,000，只花了 90 天。VP 問你：「不砍功能、不降品質，能把成本壓回 $15,000 以內嗎？」你會從哪裡下手？

---

## 一、核心問題：AI 成本為什麼是工程問題而不是採購問題

### 1.1 成本爆炸的根因

AI API 成本爆炸通常不是因為「用太多功能」，而是因為工程決策累積的結構性浪費：

- **重複計算**：相同或語義近似的 prompt 反覆打到 API，沒有任何快取層
- **模型過配**（Over-provisioning）：用旗艦大模型處理「幫我把這段文字轉成 JSON」這種任務
- **無邊界的 Context Window**：每次請求塞入整個對話歷史，Context 長度隨時間線性增長
- **同步阻塞推論**：本可批次離線的任務強行走即時路徑，佔用高單價的即時算力

### 1.2 成本的三個維度

```
成本 = Token 數量 × 單價 × 請求頻率
       ───────    ────    ────────
       工程可控    模型選擇   業務需求
```

採購談判只能影響「單價」，而且通常邊際效益有限（折扣上限約 20–30%）。
真正的槓桿在「Token 數量」和「請求頻率」——兩者都是純工程問題。

### 1.3 為什麼 FinOps 思維不夠用

傳統雲端 FinOps 的核心是「Resource Right-sizing」：把過大的 VM 換小。
但 AI 成本的結構完全不同：

| 維度 | 傳統 FinOps | AI FinOps |
|------|------------|-----------|
| 計費單位 | CPU/Memory/小時 | Token/Request |
| 主要浪費 | 閒置資源 | 重複推論、過長 Context |
| 優化手段 | Auto-scaling、RI | Cache、路由、批次 |
| 品質耦合 | 無（換小機器功能不變） | 有（換小模型品質可能下降） |
| 可觀測性 | CPU/Memory metrics | Token histogram、Cache hit rate |

AI 成本工程的核心挑戰：**在成本、延遲、品質三角之間找到可接受的 Pareto 前沿**，而不是單純壓低成本。

---

## 二、三個演進階段（POC → MVP → Scale）

### ╔══ Phase 1：POC / < 10K 用戶 ══╗

**目標**：快速驗證 AI 功能可行性，成本可接受就好。

```
┌─────────────────────────────────────────┐
│              應用層 (App)                │
└──────────────────┬──────────────────────┘
                   │ 直接 API 呼叫
                   ▼
┌─────────────────────────────────────────┐
│         AI API Provider                  │
│    (單一模型，如 claude-3-5-sonnet)       │
└─────────────────────────────────────────┘
```

**新增元件（vs 無）**：AI API 整合、基本的 Token 用量 logging

**成本/複雜度**：$500–$3,000/月，工程複雜度低

**解決的問題**：功能驗證、團隊熟悉 API

**遺留的問題**：
- 無快取，每次請求都計費
- 所有請求走同一模型（無論複雜度）
- 無 Token 用量分析，不知道哪裡在燒錢
- Context 不受控，隨功能迭代悄悄膨脹

---

### ╔══ Phase 2：MVP / 10K–200K 用戶 ══╗

**目標**：上生產、降低意外帳單、建立可觀測性基礎。

```
┌──────────────────────────────────────────────────────┐
│                    應用層 (App)                        │
└─────────────────────┬────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│              AI Gateway / Proxy 層                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Exact Cache │  │ Token Counter│  │ Rate Limiter│ │
│  │  (Redis)    │  │  + Budget 警報│  │             │ │
│  └─────────────┘  └──────────────┘  └─────────────┘ │
└──────────────┬──────────────────────────────┬────────┘
               │                              │
               ▼                              ▼
┌──────────────────────┐        ┌─────────────────────┐
│  旗艦模型             │        │  輕量模型             │
│  (複雜推理用)          │        │  (分類/摘要用)        │
└──────────────────────┘        └─────────────────────┘
```

**新增元件（vs Phase 1）**：
- AI Gateway（LiteLLM 或自建 Proxy）
- Redis Exact Cache（相同 prompt 的快取，命中率約 15–25%）
- Token 用量儀表板（按 feature / user segment 分解）
- Budget Alert（超過 $X/天觸發告警）
- 初步模型路由（規則式：簡單任務走輕量模型）

**成本/複雜度**：$3,000–$15,000/月，工程複雜度中

**解決的問題**：
- Exact Cache 命中節省 15–25% 成本
- 模型路由節省 20–35%（輕量模型成本約旗艦的 1/10）
- 可觀測性：知道哪個功能最燒錢

**遺留的問題**：
- Semantic Cache 未部署，語義相似的 prompt 仍重複計費
- 批次任務仍走即時 API
- GPU 自管成本高，缺乏 Spot 策略

---

### ╔══ Phase 3：Scale / 200K–1M+ 用戶 ══╗

**目標**：AI 成本可預測、可控制、持續自動優化。

```
┌─────────────────────────────────────────────────────────────────┐
│                         應用層 (App)                              │
└───────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    智慧 AI Gateway                                │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────┐ │
│  │ Semantic     │  │ Model Router  │  │ Prompt Cache          │ │
│  │ Cache        │  │ (ML-based)    │  │ (Provider-side)       │ │
│  │ (Vector DB)  │  │               │  │                       │ │
│  └──────────────┘  └───────────────┘  └───────────────────────┘ │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────┐ │
│  │ Batch Queue  │  │ Cost Allocator│  │ Quality Monitor       │ │
│  │ (Async路徑)  │  │ (per tenant)  │  │ (自動回退)             │ │
│  └──────────────┘  └───────────────┘  └───────────────────────┘ │
└──────────┬──────────────────┬───────────────────────────────────┘
           │                  │
     ┌─────▼──────┐    ┌──────▼──────┐
     │  即時路徑   │    │  批次路徑    │
     │  (Sync)    │    │  (Async)    │
     └──────┬─────┘    └──────┬──────┘
            │                 │
   ┌────────┼────────┐        │
   ▼        ▼        ▼        ▼
旗艦模型  中型模型  輕量模型  批次 API
 ($15/M)  ($3/M)  ($0.3/M)  (50%折扣)
```

**新增元件（vs Phase 2）**：
- Semantic Cache（Vector DB，命中率提升至 40–60%）
- ML-based Model Router（根據任務複雜度動態選模型）
- Prompt Cache（利用 Provider 的 prefix cache，重複 system prompt 節省 90% token）
- 批次推論隊列（非即時任務走 Batch API，節省 50%）
- GPU Spot 策略（訓練/fine-tuning 用 Spot，節省 60–70%）
- 多租戶成本分配（按 feature / customer 追蹤 AI 成本）

**成本/複雜度**：$8,000–$20,000/月（服務 200K–1M 用戶），工程複雜度高

**解決的問題**：
- 全棧優化後成本比 Phase 1 線性成長曲線低 60–70%
- 品質有監控，劣化時自動回退到旗艦模型
- 成本可按 tenant / feature 分配，支持 AI 功能定價決策

---

## 三、Token 成本分解：Input/Output/Cache 的單位經濟學

### 3.1 Token 定價結構

以主流模型為例（2025 年市場價格區間）：

```
┌─────────────────────────────────────────────────────────────┐
│                    Token 定價矩陣                             │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ 模型級別      │ Input        │ Output       │ Cache Read     │
├──────────────┼──────────────┼──────────────┼────────────────┤
│ 旗艦（大）    │ $15 / M tok  │ $75 / M tok  │ $1.5 / M tok   │
│ 中型         │  $3 / M tok  │ $15 / M tok  │ $0.3 / M tok   │
│ 輕量（小）    │ $0.3 / M tok │ $1.5 / M tok │ $0.03 / M tok  │
│ Batch API    │  50% 折扣    │  50% 折扣    │ 50% 折扣        │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

**關鍵洞察**：Output Token 的成本通常是 Input 的 5× 。這意味著「要求 AI 輸出更短的答案」比「壓縮 system prompt」更有效。

### 3.2 典型 RAG 請求的 Token 分解

一個典型的 RAG（Retrieval-Augmented Generation）請求成本分解：

```
一次 RAG 請求的 Token 組成：
┌────────────────────────────────────────────┐
│ System Prompt       │  800 tok  │  固定     │
│ Retrieved Chunks    │ 2,000 tok │  可快取   │
│ Conversation Hist.  │ 1,200 tok │  可壓縮   │
│ User Query          │   50 tok  │  不可壓縮 │
│ ─────────────────── │ ──────── │ ──────── │
│ Total Input         │ 4,050 tok │           │
│ ─────────────────── │ ──────── │ ──────── │
│ AI Response         │  400 tok  │  可壓縮   │
└────────────────────────────────────────────┘

未優化成本（旗艦模型）：
  Input:  4,050 × $15/M = $0.0608
  Output:   400 × $75/M = $0.0300
  Total:                  $0.0908 / request

1,000 QPS × $0.0908 × 86,400 秒 ≈ $7,845,120 / 天（不合理）
實際 10 QPS：$78,451 / 天 = $2.4M / 月（仍然驚人）
```

### 3.3 優化後的成本計算

```
優化後（Semantic Cache 60% 命中 + 中型模型路由 70%）：

40% 未命中請求走中型模型（70%）+ 旗艦（30%）：
  Cache miss × 中型：
    Input:  4,050 × 0.4 × 0.7 × $3/M  = $0.0034
    Output:   400 × 0.4 × 0.7 × $15/M = $0.0017

  Cache miss × 旗艦：
    Input:  4,050 × 0.4 × 0.3 × $15/M = $0.0073
    Output:   400 × 0.4 × 0.3 × $75/M = $0.0036

  Cache hit（幾乎零成本）: ≈ $0.0001

  Total per request: ≈ $0.0161 （降低 82%）
```

---

## 四、快取策略：Exact Cache vs Semantic Cache vs Prompt Cache

### 4.1 三種快取的比較

| 快取類型 | 命中條件 | 命中率 | 延遲節省 | 成本節省 | 實作複雜度 |
|---------|---------|--------|---------|---------|----------|
| Exact Cache | prompt 完全相同 | 5–20% | 95%（< 1ms vs 800ms） | 95% per hit | 低（Redis TTL） |
| Semantic Cache | 語義相似度 > 閾值 | 35–60% | 90%（< 5ms vs 800ms） | 90% per hit | 中（需 Vector DB） |
| Prompt Cache | system prompt prefix 相同 | 70–90% | 30–50% | 最高 90% input token | 低（Provider API flag） |

### 4.2 Semantic Cache 實作細節

Semantic Cache 的核心是「查詢向量相似度，返回先前答案」：

```python
async def semantic_cache_lookup(query: str, threshold: float = 0.92):
    # 1. 將 query embed 成向量（< 5ms）
    query_vec = await embed(query)

    # 2. 在 Vector DB 查最近鄰（< 10ms）
    results = await vector_db.search(
        vector=query_vec,
        top_k=1,
        score_threshold=threshold  # 0.92 是品質/命中率的平衡點
    )

    if results and results[0].score >= threshold:
        # 3. 命中：直接返回快取答案（< 1ms）
        return results[0].cached_response

    # 4. 未命中：打 API，並將結果存入快取
    response = await call_ai_api(query)
    await vector_db.upsert(vector=query_vec, payload={"response": response})
    return response
```

**閾值選擇的影響**：
- threshold = 0.95：精準但命中率低（約 25–35%）
- threshold = 0.92：平衡點（命中率 40–60%，誤命中率 < 2%）
- threshold = 0.88：命中率高（55–70%）但品質風險增加

### 4.3 Prompt Cache（Provider-side）

主流 AI Provider 支援 prompt prefix caching：如果多次請求共享相同的前綴（system prompt、文件內容），Provider 會快取計算結果，後續請求只計 cache read token 費用（約原費用的 10%）。

**啟用條件**：
1. Prompt prefix ≥ 1,024 tokens（太短不值得快取）
2. 相同 prefix 在短時間內重複出現（通常 5 分鐘內）
3. 使用支援此功能的模型版本

**典型節省**：system prompt 1,500 tokens × $15/M × 10 QPS × 86,400 = $19,440/天；啟用 Prompt Cache 後降至 $1,944/天，**節省 $17,496/天**。

---

## 五、智慧模型路由：根據複雜度選擇模型

### 5.1 路由架構

```
┌────────────────────────────────────────────────────────┐
│                  請求進入 Gateway                        │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│              複雜度分類器（< 20ms）                       │
│                                                        │
│  特徵：                                                  │
│  • Query 長度（< 50 words → 簡單）                       │
│  • 是否含多步推理關鍵詞（"分析"、"比較"、"推導"）           │
│  • 歷史同類 Query 的品質評分                              │
│  • 當前 Context 長度                                     │
└───────┬────────────────────┬──────────────────┬────────┘
        │                    │                  │
        ▼                    ▼                  ▼
┌──────────────┐   ┌─────────────────┐  ┌──────────────┐
│  輕量模型    │   │   中型模型       │  │  旗艦模型    │
│  複雜度 1–3  │   │  複雜度 4–7     │  │  複雜度 8–10 │
│  $0.3/M tok  │   │   $3/M tok      │  │  $15/M tok   │
│  延遲 200ms  │   │   延遲 400ms    │  │  延遲 800ms  │
│  ~50% 請求  │   │   ~35% 請求     │  │  ~15% 請求  │
└──────────────┘   └─────────────────┘  └──────────────┘
```

### 5.2 複雜度評分的實作

簡單的規則式路由（Phase 2 適用）：

```python
def classify_complexity(query: str, context_length: int) -> int:
    score = 1

    # 長度加分
    if len(query.split()) > 100:
        score += 2
    elif len(query.split()) > 50:
        score += 1

    # 推理關鍵詞加分
    complex_keywords = ["分析", "比較", "推導", "設計", "評估", "為什麼"]
    score += sum(2 for kw in complex_keywords if kw in query)

    # Context 長度加分
    if context_length > 8000:
        score += 2
    elif context_length > 4000:
        score += 1

    return min(score, 10)

def route_to_model(score: int) -> str:
    if score <= 3:
        return "lightweight-model"   # 分類、摘要、格式轉換
    elif score <= 7:
        return "mid-tier-model"      # 一般問答、RAG 回答
    else:
        return "flagship-model"      # 複雜推理、代碼生成
```

### 5.3 ML-based 路由（Phase 3）

Phase 3 的路由加入品質反饋迴路：
- 每次回應後收集用戶隱性反饋（點贊、重新生成、繼續提問）
- 將 {query 特徵, 模型選擇, 品質得分} 存入訓練集
- 每週重新訓練輕量分類器（XGBoost，< 5ms 推論）
- A/B test 新路由策略，監控品質指標不得下降超過 2%

---

## 六、批次推論：離線任務的吞吐最大化

### 6.1 即時 vs 批次的決策邊界

```
任務類型判斷樹：

需要即時回應（< 2秒）？
    ├── 是 → 走同步 API（即時路徑）
    └── 否 → 可接受 5分鐘–24小時延遲？
                ├── 5分鐘 → Mini Batch（小批次，10–100個）
                └── 數小時–24小時 → Batch API（大批次，1,000+個）
                                    ├── 節省 50% 成本
                                    └── 吞吐量 10×–100×
```

**適合批次的典型任務**：
- 文章摘要生成（SEO、內容平台）
- 用戶行為分析報告（每日/每週）
- 資料標注（訓練資料生成）
- 批量翻譯
- Embedding 生成（RAG 索引建立）

### 6.2 批次推論的吞吐計算

```
即時路徑：
  一次請求 800ms，同時 100 個並發連線
  吞吐量 = 100 / 0.8s = 125 req/s
  成本 = $0.09 / req × 125 = $11.25 / 秒 = $972,000 / 天 （不合理）

批次路徑（Batch API）：
  提交 10,000 個請求的批次任務
  完成時間：約 2 小時（Provider 在低峰期處理）
  成本 = $0.09 × 0.5 折扣 × 10,000 = $450（vs 即時 $900）
  節省 50%，且不佔用即時配額
```

### 6.3 批次隊列架構

```python
# 批次任務提交
async def submit_batch_job(tasks: list[dict]) -> str:
    batch_id = await batch_api.create_batch(
        requests=tasks,
        completion_window="24h",   # 或 "1h" 取決於 SLA
        metadata={"job_type": "content_summarization"}
    )
    # 存入 DB 追蹤狀態
    await db.insert_batch_job(batch_id, status="pending", count=len(tasks))
    return batch_id

# 非同步輪詢結果
async def poll_batch_results(batch_id: str):
    while True:
        status = await batch_api.retrieve_batch(batch_id)
        if status.status == "completed":
            results = await batch_api.list_batch_results(batch_id)
            await process_results(results)
            break
        elif status.status == "failed":
            await handle_failure(batch_id)
            break
        await asyncio.sleep(60)   # 每分鐘輪詢一次
```

---

## 七、GPU FinOps：Spot 搶佔/Reserved/On-demand 的組合策略

### 7.1 三種 GPU 採購模式

| 模式 | 單價（A100 80GB） | 搶佔風險 | 適用場景 |
|------|----------------|---------|---------|
| On-demand | $3.50 / hr | 無 | 即時推論、低延遲服務 |
| Reserved（1年） | $2.10 / hr（40% 折扣） | 無 | 穩定基線負載 |
| Spot / Preemptible | $0.70–$1.40 / hr（60–80% 折扣） | 高（隨時中斷） | 訓練、批次任務 |

### 7.2 組合策略（三層架構）

```
負載類型             建議採購模式          理由
─────────────────────────────────────────────────────────
生產推論（基線）      Reserved 1年          穩定使用率 > 70%，RI 划算
生產推論（峰值）      On-demand（自動擴充）  Peak 時間不可中斷
模型訓練             Spot（80%）+           大部分時間節省，偶爾中斷
                     On-demand（20%）       有 Checkpoint 即可恢復
Fine-tuning          Spot + Checkpoint      1–4 小時任務，中斷影響可控
Batch Embedding      Spot（100%）           冪等任務，中斷後重新提交
```

### 7.3 Spot 搶佔應對策略

Spot 實例的搶佔通知通常提前 2 分鐘（雲端廠商標準）。應對措施：

1. **Checkpoint 機制**：每 5 分鐘存儲訓練狀態到持久化存儲（S3/GCS）
2. **分散可用區**：同時在 3 個 AZ 請求 Spot，降低全部被搶佔的概率
3. **Spot Fleet + Fallback**：優先用 Spot，搶佔時自動切換到 On-demand（接受 5× 成本上升換取不中斷）
4. **冪等設計**：批次任務每個工作單元獨立，失敗後只重試失敗的部分

### 7.4 實際成本節省案例

```
場景：每月 1,000 GPU-hours 的模型訓練任務

純 On-demand：1,000 × $3.50 = $3,500 / 月
純 Reserved：  1,000 × $2.10 = $2,100 / 月（節省 40%）
Spot 組合：
  800 hr Spot（$0.70）= $560
  200 hr On-demand（$3.50）= $700（Spot 被搶佔的緩衝）
  合計 = $1,260 / 月（節省 64%）
```

---

## 七之二、成本可觀測性：看不見的成本無法優化

### 成本監控的四個層次

優化成本的前提是「量化現狀」。沒有可觀測性，所有優化都是猜測。

```
Layer 4：業務層     ROI per feature（每個 AI 功能的投資回報）
                    ↑
Layer 3：租戶層     Cost per tenant（識別高成本用戶，定價或限速）
                    ↑
Layer 2：功能層     Cost per feature（哪個產品功能最貴）
                    ↑
Layer 1：請求層     Token histogram（P50/P95/P99 的 Token 分布）
```

**Layer 1 最先實作**，因為它的資料是 Layer 2–4 的基礎。

### 成本警報閾值設計

| 警報類型 | 觸發條件 | 嚴重程度 | 自動行動 |
|---------|---------|---------|---------|
| 每日成本超標 | > 預算 × 120% | Warning | Slack 通知 |
| 請求成本異常 | 單次請求 > $1 | Warning | 記錄並分析 |
| 月費用趨勢 | 本月預測 > 預算 × 150% | Critical | 自動限速 |
| Token 暴增 | 1 分鐘 Token 量 > 5× 均值 | Critical | 觸發限流 |

### 成本分配的技術實作

每個 AI 請求必須在 metadata 中攜帶維度資訊：

```python
response = await ai_client.messages.create(
    model="claude-3-5-sonnet-20241022",
    messages=[...],
    metadata={
        "user_id": user_id,
        "tenant_id": tenant_id,
        "feature": "document_summary",    # 功能標籤
        "request_id": request_id,
    }
)

# 記錄成本到 TSDB（時序資料庫）
cost = calculate_cost(
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    model=response.model
)
await metrics.record({
    "cost_usd": cost,
    "tenant_id": tenant_id,
    "feature": "document_summary",
    "cache_hit": False,
    "model_tier": "flagship"
})
```

**成本歸因的黃金法則**：在請求發生時記錄，而不是月底從帳單反推。帳單只有總量，無法做根因分析。

---

## 八、為什麼選 X 不選 Y（6 個核心決策）

### 決策 1：Semantic Cache vs 不加快取

```
選擇          選 Semantic Cache 的理由              不選（維持現狀）的理由
──────────────────────────────────────────────────────────────────────
Semantic      命中率 40–60%，直接節省 35–55% 成本     實作需要 Vector DB，
Cache         延遲從 800ms 降到 < 10ms                複雜度上升
vs            用戶體驗顯著提升（重複問題快取答覆）      需要維護 Cache 失效邏輯
無快取         規模越大，邊際成本趨近零                  資料品質問題（過期快取）
```

**Flip Condition**：問題多樣性極高（如代碼生成，每次 query 都不同）時，Semantic Cache 命中率可能 < 5%，維護成本 > 節省，此時應跳過 Semantic Cache 直接用 Prompt Cache。

---

### 決策 2：ML 路由 vs 規則式路由

```
選擇          選 ML 路由的理由                       不選 ML 路由（用規則）的理由
──────────────────────────────────────────────────────────────────────
ML 路由       準確率高 10–15%，減少誤判                需要訓練資料（冷啟動問題）
vs            自動適應 Query 分布變化                  推論延遲多 15–20ms
規則式        可解釋性強，邊界清晰                      需要定期重訓（運維成本）
路由          有品質反饋迴路可持續優化                  錯誤難以 debug
```

**Flip Condition**：日請求量 < 10,000 時，無足夠資料訓練分類器，應先用規則式路由；超過 100,000 req/day 後，ML 路由的優勢開始顯現。

---

### 決策 3：Batch API vs 即時 API（適用可延遲任務）

```
選擇          選 Batch API 的理由                    不選 Batch API 的理由
──────────────────────────────────────────────────────────────────────
Batch API     50% 成本折扣，等價於所有 RI 折扣       延遲 5 分鐘–24 小時，
vs            不佔用即時配額，不影響生產服務            不適合互動式場景
即時 API      吞吐量無限制，適合大量離線任務            需要額外的任務隊列系統
              失敗粒度細，只需重試失敗的工作單元         結果輪詢邏輯複雜
```

**Flip Condition**：用戶在等待結果（如表單提交後需立即顯示 AI 分析），延遲 > 3 秒不可接受，一律走即時 API。

---

### 決策 4：Prompt Cache vs 縮短 System Prompt

```
選擇          選 Prompt Cache 的理由                 不選（縮短 Prompt）的理由
──────────────────────────────────────────────────────────────────────
Prompt        不需改變 Prompt 內容，零品質風險         System Prompt 需 ≥ 1,024 tok
Cache         Cache Read 費用只有原費用的 10%          Provider 支援程度不一
vs            Engineering effort 極低（加一個 flag）  短 Prompt 無法享受此優惠
縮短          任何長度都有效                           縮短 Prompt 可能影響輸出品質
Prompt        永久節省（非 TTL 依賴）                  需要多輪測試確認效果
```

**Flip Condition**：System Prompt < 1,024 tokens，Prompt Cache 無效，此時才考慮縮短 Prompt（但需要嚴格 A/B test 品質）。

---

### 決策 5：Spot GPU vs On-demand（訓練任務）

```
選擇          選 Spot 的理由                         不選 Spot 的理由
──────────────────────────────────────────────────────────────────────
Spot GPU      60–80% 成本折扣，對長期訓練效果顯著       搶佔風險：2 分鐘通知
vs            與 Checkpoint 配合可完全冪等              需要 Checkpoint 邏輯（開發成本）
On-demand     適合 > 4 小時的訓練任務                   Spot 供應不穩定（某些區域稀缺）
              可混合策略（80% Spot + 20% OD）           適合 < 1 小時的短任務
```

**Flip Condition**：Fine-tuning 任務 < 30 分鐘（Checkpoint 開銷 > 節省），或 SLA 要求訓練必須在固定時間窗完成，改用 On-demand。

---

### 決策 6：多租戶成本分配 vs 全局成本池

```
選擇          選多租戶分配的理由                      不選（全局成本池）的理由
──────────────────────────────────────────────────────────────────────
多租戶        可識別高成本 tenant，針對性限速/定價       需要在每個請求注入 tenant ID
成本分配      支援 AI 功能按使用量定價（$X/1K queries） 成本分配邏輯本身有少量 overhead
vs            快速發現異常：某 tenant 突然成本暴增       錯誤的分配可能導致計費爭議
全局池        法遵/審計需要（企業客戶合約要求）          前期實作較複雜
              為產品決策提供數據（哪個功能 ROI 高）
```

**Flip Condition**：內部工具、單一 tenant 的系統，全局成本池即可，不需要分配邏輯。

---

## 九、系統效應：優化前後的成本/延遲/品質三角

### 9.1 量化對比表

| 指標 | Phase 1（未優化） | Phase 2（基礎優化） | Phase 3（全棧優化） |
|------|----------------|------------------|------------------|
| 月費用（10 QPS） | $47,000 | $18,000 | $8,500 |
| 平均回應延遲 | 850ms | 620ms（快取 hit 降低） | 280ms（60% cache hit） |
| P99 延遲 | 2,400ms | 1,800ms | 900ms |
| 快取命中率 | 0% | 18%（Exact Cache） | 55%（Semantic Cache） |
| 模型路由效率 | 0%（全旗艦） | 45%（規則式）| 82%（ML 路由） |
| 品質評分（1–5） | 4.3 | 4.1（輕量模型偶爾降品質） | 4.2（有回退保護） |
| GPU 訓練成本/月 | $3,500（純 OD） | $2,100（RI）| $1,260（Spot 組合）|
| 可觀測性 | 無 | Token 用量儀表板 | 全棧成本分配 + 品質監控 |

### 9.2 成本節省來源分解

```
從 $47,000 → $8,500（節省 $38,500/月）的來源：

Semantic Cache（命中率 55%）：節省約 $21,000（55%）
ML 模型路由（82% 非旗艦）：節省約 $11,200（24%）
Prompt Cache（system prompt）：節省約 $3,800（8%）
Batch API（20% 任務離線化）：節省約 $1,900（4%）
其他優化（Context 壓縮等）：節省約  $600（1%）

總節省：$38,500 / 月 = 82% 成本降低
```

### 9.3 成本/品質曲線

關鍵洞察：優化並非全程「成本下降、品質也下降」。

- 0–60% 成本節省：主要來自快取和路由，品質幾乎不變（< 1% 降幅）
- 60–80% 成本節省：需要激進的模型降級，品質風險上升（需要 A/B test 把關）
- > 80% 成本節省：通常意味著嚴重的品質妥協，不建議追求

**最佳實踐目標**：70% 成本節省 + 品質評分下降 ≤ 3%。

---

## 十、面試答題要點

**面試官問題**：

> 「你的 RAG 系統每月 AI API 費用從 $3,000 暴增到 $47,000，只花了 90 天。VP 問你：不砍功能、不降品質，能把成本壓回 $15,000 以內嗎？你會從哪裡下手、用什麼順序、如何量化效果？」

**模型答案**：

> *「我會用三階段方法處理這個問題，目標是 70% 成本節省而品質下降控制在 3% 以內。第一步是快速分析 Token 用量分佈，找出高成本的 feature 和 query 模式——通常 20% 的 query 佔 80% 的成本；第二步是優先部署 Semantic Cache，因為 RAG 場景下語義相似問題比例高，命中率可達 40–60%，這一步通常能節省 35–50% 成本、延遲從 850ms 降到 < 30ms，且無品質風險；第三步是部署規則式模型路由，把分類、格式轉換等低複雜度任務（約 50% 的請求）路由到輕量模型，成本差距是 50×，可再節省 20–25%；最後啟用 Provider-side Prompt Cache，system prompt 重複讀取費用降低 90%，再省 8–10%。三步合計節省 70%+，$47,000 可壓至 $14,000，達成目標，且全程有品質監控儀表板確保用戶體驗不下降。」*

---

## 十一、系列導航

← [Phase 17 Part 2](../ai-eng-from-scratch-phase17-part2-observability-zh) | [Phase 18 Part 1 →](../ai-eng-from-scratch-phase18-part1-multimodal-zh)

---

*本文為「AI 工程從零開始」系列 Phase 17 Part 3，專注於 AI 生產成本工程的系統性方法。所有數字基於 2025–2026 年市場價格與實際生產經驗，具體費率請以各 Provider 官方定價為準。*
