---
title: "FDE 面試指南 Part 52：百萬級 Agent Tool-Calling 的全域非同步並行優化與扇出控制"
date: 2026-06-08T09:00:00+08:00
draft: false
weight: 52
description: "深度剖析 LangGraph Agent 在高並發場景下的 Tool Fan-Out 架構設計：Speculative Execution、Circuit Breaker、Graceful Degradation 與 Partial Rendering 的工程實踐，含三個演進階段與完整 Staff 級解答。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "FDE", "Agent", "AsyncIO", "Tool-Calling", "Fan-Out", "Circuit-Breaker", "LangGraph"]
authors: ["yen"]
readTime: "26 min"
---

> 大多數工程師遇到「Agent 要並行呼叫 15 個 API」時，第一反應是 `asyncio.gather()`，然後假設「全部回來再合併」。  
> 真正的 Staff FDE 知道：**gather 是把所有雞蛋放進同一個計時炸彈**。  
> 正確答案不是「更快地等待」，而是**動態熔斷、投機複製、強制截止、局部渲染**——在 1.5 秒內交出 80% 的答案，比等 30 秒的「完美答案」更有價值。  
> 系統設計的成熟度，體現在你如何**優雅地處理你控制不了的那 20%**。

---

## 面試情境

> **面試官**：「你負責一個 AI 理財 Agent 的後端架構。用戶問：『幫我分析我持有的 15 檔美股今天的技術指標。』Agent 需要並行呼叫 15 次外部股票 Data API。請問：（1）如果單純用 asyncio.gather() 並行發起，你能預期哪些生產環境問題？（2）你會如何設計一個能應對 API 超時、Rate Limit、部分失敗的進階工具執行引擎？請從架構、程式碼模式、降級策略三個維度說明。」

---

## 一、核心問題：為什麼 gather() 在生產環境是炸彈

### 1.1 問題的表面現象

理財 Agent 接到用戶指令：「分析我持有的 AAPL、TSLA、NVDA… 等 15 檔美股的技術指標」。

Agent 的工具調用計畫很清楚：針對每一個股票代號，呼叫一次 `get_stock_indicators(ticker)` ——這是 15 次獨立的外部 HTTP 請求。

最直覺的實作是：

```python
results = await asyncio.gather(
    *[get_stock_indicators(ticker) for ticker in tickers]
)
```

**順序執行**的基準延遲：15 calls × 平均 2s per call = **30 秒**。用戶體驗直接崩潰。

**asyncio.gather() 並行**理論延遲：最慢那一個請求的時間 = 如果有一個卡住 10 秒，整體就是 10 秒。

### 1.2 gather() 在生產環境的三個致命缺陷

**缺陷一：木桶短板效應**

asyncio.gather() 預設行為：等待所有協程完成（或任一拋出異常）。若外部 API 有 3 個因 Rate Limit 卡在 15 秒逾時，整個 gather 就被這 3 個卡死。12 個已完成的結果在記憶體中空等，對用戶毫無價值。

**缺陷二：無熔斷保護**

gather() 本身不知道「某個 API 連續失敗了幾次」。一個已知死亡的 API 節點，gather 下一次調用還是會傻乎乎地等它的完整 timeout。

**缺陷三：無法局部渲染**

gather() 是全有或全無。12 個股票數據早已就緒，前端卻必須等所有 15 個才能渲染——或者一個異常就全部爆掉。

### 1.3 為什麼這個問題在百萬級場景下被放大

當每天有 10 萬次這類查詢時：
- 外部 API 的 P99 延遲通常是 P50 的 5–10 倍
- Rate Limit 觸發頻率與並發請求數成正比
- 一個 API 節點的瞬時抖動，在 gather() 架構下，會傳染給所有等待它的用戶請求

**核心張力**：我們需要並行（降低延遲），又需要防禦（不被最慢的拖垮），還需要局部可用（有啥用啥）。這三個需求在 asyncio.gather() 裡天然衝突。

---

## 二、三個演進階段

### ╔══ Phase 1（POC / < 10K 用戶）══╗

**目標**：先讓 Agent 能並行跑起來，比順序執行快即可。

```
┌────────────────────────────────────────┐
│  LangGraph Agent                       │
│  (生成 15 個 ToolCall 物件)            │
└──────────────┬─────────────────────────┘
               │  15 parallel calls
               ▼
┌────────────────────────────────────────┐
│  asyncio.gather(*tool_calls,           │
│      return_exceptions=True)           │
│                                        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │AAPL  │ │TSLA  │ │NVDA  │ │... 12│  │
│  │ API  │ │ API  │ │ API  │ │ APIs │  │
│  └──────┘ └──────┘ └──────┘ └──────┘  │
└──────────────┬─────────────────────────┘
               │  等最慢的那一個
               ▼
┌────────────────────────────────────────┐
│  彙整所有結果 → 回傳給 LLM             │
└────────────────────────────────────────┘
```

**Phase 1 實作重點**：
- 使用 `return_exceptions=True`，讓單個失敗不爆炸整個 gather
- 對每個 call 加獨立 `asyncio.wait_for(coro, timeout=5.0)`
- 失敗的直接傳回 None，LLM 提示中說明「部分數據不可用」

**成本 / 複雜度**：
- 開發成本：2 天
- 基礎設施：單台 Cloud Run 服務，無額外依賴
- 延遲改善：30s → 約 5s（最慢的 API 5 秒逾時）
- 殘留問題：沒有熔斷（已死 API 每次都等 5 秒）；沒有投機執行；前端等全部完成才渲染

---

### ╔══ Phase 2（MVP / 10K–200K 用戶）══╗

**目標**：加入 Circuit Breaker 與 asyncio.wait() 替代 gather，實現真正的部分結果回傳。

```
┌───────────────────────────────────────────────────┐
│  LangGraph Agent (Cloud Run)                      │
│  發出 15 個 ToolCall Spec                         │
└────────────────────┬──────────────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────────────┐
│  Tool Execution Engine (Cloud Run Job)            │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │  Circuit Breaker Registry                   │  │
│  │  (per-API state: CLOSED / OPEN / HALF-OPEN) │  │
│  └──────────────────┬──────────────────────────┘  │
│                     │  跳過 OPEN 狀態的 API        │
│                     ▼                             │
│  asyncio.wait(tasks, timeout=5.0,                 │
│               return_when=FIRST_EXCEPTION)        │
│                                                   │
│  ┌──────┐ ┌──────┐ ┌──────┐  ┌──────────────┐    │
│  │AAPL  │ │TSLA  │ │NVDA  │  │[OPEN: 跳過]  │    │
│  └──────┘ └──────┘ └──────┘  └──────────────┘    │
└────────────────────┬──────────────────────────────┘
                     │  done, pending = asyncio.wait(...)
                     ▼
┌───────────────────────────────────────────────────┐
│  取 done 集合的結果 + 標記 pending 為 timeout      │
│  → 組裝 PartialResult JSON → 回傳給 LLM           │
└───────────────────────────────────────────────────┘
```

**Phase 2 新增組件**：

| 組件 | 說明 | vs Phase 1 |
|------|------|-----------|
| Circuit Breaker Registry | 追蹤每個 API 的失敗次數與狀態 | Phase 1 無此概念 |
| asyncio.wait() | 可拿到 done/pending 兩個集合，靈活處理 | 替代 gather |
| PartialResult 協議 | LLM prompt 中有標準的「缺失說明」格式 | Phase 1 靠 None 混搭 |
| Structured Logging | 每個 tool call 記錄 latency、status | Phase 1 靠 print |

**成本 / 複雜度**：
- 開發成本：1 週
- 基礎設施：Cloud Memorystore Redis（Circuit Breaker 狀態共享，多副本 Cloud Run）
- 延遲：約 5s → 約 2s（Circuit Breaker 跳過已知壞節點，不再傻等）
- 殘留問題：無投機執行（抖動時還是要等 timeout）；無前端 SSE 即時推送；Fan-out 無上限

---

### ╔══ Phase 3（Scale / 200K–1M+ 用戶）══╗

**目標**：完整的防禦性扇出引擎——Speculative Execution + Hard Deadline + Partial Rendering + Fan-out 熔斷器。

```
┌──────────────────────────────────────────────────────────────────┐
│  LangGraph Agent (GKE / Cloud Run)                               │
│  解析用戶意圖 → 生成 ToolCallPlan (15 個 ToolCall Spec)          │
└──────────────────────────┬───────────────────────────────────────┘
                           │  gRPC / HTTP2
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Tool Execution Gateway (Cloud Run — 獨立微服務)                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Fan-Out Controller                                      │    │
│  │  max_concurrent=20 → 超過進 asyncio.Queue               │    │
│  │  Hard Deadline Timer: T=0 開始計時，T=1500ms 強制截止   │    │
│  └───────────────────────┬──────────────────────────────────┘    │
│                          │ 並發發起 15 個 Task                   │
│          ┌───────────────┼────────────────────┐                  │
│          ▼               ▼                    ▼                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐  │
│  │ AAPL Task    │ │ TSLA Task    │ │ NVDA Task                │  │
│  │ (回傳: 200ms)│ │ (回傳: 350ms)│ │ (T=800ms 未回 Header)   │  │
│  └──────┬───────┘ └──────┬───────┘ └────────────┬─────────────┘  │
│         │                │                      │ 觸發            │
│         │                │              ┌───────▼──────────────┐  │
│         │                │              │ Speculative Request  │  │
│         │                │              │ (備用節點 Race)      │  │
│         │                │              └───────┬──────────────┘  │
│         │                │                      │ 誰先回傳用誰    │
│         ▼                ▼                      ▼                 │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Result Aggregator                                       │    │
│  │  T=1500ms → 強制截止剩餘請求                             │    │
│  │  已完成: 12 檔  ｜  超時: TSLA, NVDA, AMD               │    │
│  └───────────────────────┬──────────────────────────────────┘    │
└──────────────────────────┼───────────────────────────────────────┘
                           │
              ┌────────────┴─────────────────┐
              ▼                              ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│  SSE Stream             │   │  LLM (Gemini / Vertex AI)       │
│  (前端即時推送          │   │  接收 PartialResult JSON:        │
│   已完成結果)           │   │  Warning: TSLA,NVDA,AMD timeout │
│                         │   │  → 仍可產出 12 檔分析報告       │
└─────────────────────────┘   └─────────────────────────────────┘
```

**Phase 3 新增組件**：

| 組件 | 說明 | vs Phase 2 |
|------|------|-----------|
| Speculative Execution | T+800ms 未收到 header → 發起複製請求賽跑 | Phase 2 靠 Circuit Breaker 跳過，但抖動仍等 |
| Hard Deadline (1500ms) | asyncio.wait(timeout=1.5)，強制截止剩餘 | Phase 2 timeout=5.0，UX 較差 |
| Fan-Out Semaphore | `asyncio.Semaphore(20)`，超過進隊列 | Phase 2 無上限，可能打爆下游 |
| SSE Partial Rendering | Cloud Run → 前端 SSE 即時推送每個完成的股票 | Phase 2 全有或全無 |
| Speculative Pool | 備用節點池，接受 Speculative Request | Phase 2 無此設計 |

**成本 / 複雜度**：
- 開發成本：3 週
- 基礎設施：Cloud Run (Gateway) + Redis (CB 狀態) + Pub/Sub (非同步回調) + SSE 推送層
- 月成本增量：約 $200–400/月（Redis + 額外 Cloud Run 費用）
- 延遲：從最差 30s（順序）→ **P50: 800ms，P99: 1.5s（硬截止）**
- 殘留問題：Speculative Execution 增加 API 呼叫成本（最多 2× 某些請求）；備用節點池需維運

---

## 三、Speculative Execution 實作深度解析

### 3.1 核心思路：用冗餘換延遲

Speculative Execution 的概念來自 CPU 分支預測與 Bigtable 論文中的「Hedged Request」。核心思路是：

**與其等一個慢節點，不如同時多問一個，誰先回答就用誰的。**

關鍵參數設定：
- **800ms 觸發點**：外部股票 API 的 P50 延遲約 300ms，P90 約 600ms。800ms 是「很可能有問題」的判斷閾值。在此之前不觸發（避免浪費 API 配額）。
- **備用節點**：可以是同一 API 的另一個 Region Endpoint，或是備用的數據供應商（如從 Provider A 切到 Provider B）。

### 3.2 Python asyncio 實作模式

```python
import asyncio
from typing import Optional

async def speculative_tool_call(
    primary_coro,
    fallback_coro_factory,
    speculative_threshold_ms: float = 800.0,
) -> dict:
    """
    在 speculative_threshold_ms 後，若 primary 未完成，
    同時發起 fallback，兩者賽跑，取先回傳者。
    """
    primary_task = asyncio.create_task(primary_coro)
    fallback_task: Optional[asyncio.Task] = None

    try:
        # 等待 primary，最多等 speculative_threshold_ms
        done, pending = await asyncio.wait(
            {primary_task},
            timeout=speculative_threshold_ms / 1000.0
        )

        if primary_task in done:
            # primary 在閾值內完成，直接返回
            return primary_task.result()

        # primary 超過閾值，發起 fallback 賽跑
        fallback_task = asyncio.create_task(fallback_coro_factory())

        race_done, race_pending = await asyncio.wait(
            {primary_task, fallback_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        winner = next(iter(race_done))
        # 取消輸家
        for loser in race_pending:
            loser.cancel()

        return winner.result()

    except asyncio.CancelledError:
        primary_task.cancel()
        if fallback_task:
            fallback_task.cancel()
        raise
```

### 3.3 為什麼用 asyncio.wait() 而非 asyncio.gather()

這是面試中高頻考點，差異如下：

| 維度 | asyncio.gather() | asyncio.wait() |
|------|-----------------|----------------|
| 異常處理 | 預設第一個異常立刻傳播，終止所有 | 異常存在 task 物件中，可選擇性處理 |
| 部分結果 | 無法在完成前取得中間結果 | done/pending 分開，隨時可取 done 的結果 |
| 取消控制 | return_exceptions=True 才不爆炸 | 天然支援對 pending 集合個別 cancel |
| 超時語意 | asyncio.wait_for(gather(...)) 超時會取消全部 | timeout 參數回傳當下 done/pending，不取消 |
| 適用場景 | 簡單的「全部成功才繼續」 | 生產級「部分成功就繼續，處理剩餘」|

**核心差異**：`asyncio.wait()` 超時後返回的 `pending` set 中的 task **仍在運行**，你可以選擇繼續等、取消、或忽略。這正是 Hard Deadline + Partial Result 的基礎。

### 3.4 成本分析

Speculative Execution 的代價是增加 API 呼叫次數：
- 觸發投機的比例：假設 P90 = 600ms，P95 = 1000ms，則約有 5% 的請求會觸發投機
- 15 個 tool calls，預期觸發投機：0.75 個（< 1 個）
- 額外 API 費用：若每次 API 呼叫 $0.001，15 calls 正常費用 $0.015，投機後約 $0.0158（+5%）

**結論**：5% 的成本增加換來 P95 延遲從 1000ms 降至 800ms，ROI 極高。

---

## 四、Circuit Breaker 狀態機設計

### 4.1 三態狀態機

```
                  連續失敗 ≥ 3 次
    ┌─────────────────────────────────────┐
    │                                     ▼
┌───┴────┐    所有請求正常          ┌──────────┐
│ CLOSED │◀─────────────────────────│ HALF-OPEN│
│(正常)  │                          │(試探)    │
└───┬────┘                          └──────┬───┘
    │                                      │
    │ 連續失敗 ≥ 3 次                       │ 單次請求失敗
    ▼                                      │
┌──────────┐   等待 30 秒後自動切換         │
│  OPEN    │──────────────────────────────▶│
│(熔斷)    │                               
└──────────┘   直接返回 fallback，不發起請求
```

### 4.2 Redis-backed Circuit Breaker（多副本共享狀態）

當 Tool Execution Gateway 有多個 Cloud Run 副本時，Circuit Breaker 狀態必須在 Redis 中共享，避免每個副本各自計算失敗次數、無法正確熔斷。

關鍵 Redis 資料結構：

```
KEY: cb:stock_api:{provider}:{ticker}
HASH:
  state: "CLOSED" | "OPEN" | "HALF_OPEN"
  failure_count: 0
  last_failure_ts: <unix_timestamp>
  open_until_ts: <unix_timestamp>  # OPEN 狀態到期時間
TTL: 300s  # 5 分鐘不活躍自動清除
```

**狀態轉換規則**：
- CLOSED → OPEN：`failure_count >= 3`（在 60 秒滑動視窗內）
- OPEN → HALF_OPEN：`current_ts > open_until_ts`（30 秒後自動）
- HALF_OPEN → CLOSED：下一次請求成功
- HALF_OPEN → OPEN：下一次請求失敗，重置 30 秒計時

### 4.3 Circuit Breaker 對延遲的影響

假設某個 API Provider 的節點發生故障：

| 狀態 | 行為 | 對用戶的延遲影響 |
|------|------|----------------|
| CLOSED（正常）| 正常發起請求 | 正常延遲 300ms |
| CLOSED（抖動中）| 等待超時 5s | 最差 5000ms |
| OPEN（熔斷後）| 立即返回 fallback，不等待 | 0ms（直接跳過）|
| HALF_OPEN（試探）| 發起一次探測請求 | 視該次請求而定 |

熔斷器在 Phase 2 將「卡住 5 秒等已知壞節點」的場景消除，這是從 5s 降到 2s 的主要貢獻。

---

## 五、Hard Deadline 與 Graceful Degradation

### 5.1 1500ms 截止線設計

Hard Deadline 是整個系統最重要的 UX 承諾：**無論發生什麼，1500ms 後用戶一定能看到回應**。

```python
async def execute_tool_fanout(
    tool_calls: list[ToolCallSpec],
    hard_deadline_ms: float = 1500.0,
    speculative_threshold_ms: float = 800.0,
    max_concurrent: int = 20,
) -> PartialResult:

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_call(spec):
        async with semaphore:
            return await speculative_tool_call(
                primary_coro=invoke_tool(spec, node="primary"),
                fallback_coro_factory=lambda: invoke_tool(spec, node="backup"),
                speculative_threshold_ms=speculative_threshold_ms,
            )

    tasks = {
        asyncio.create_task(bounded_call(spec)): spec
        for spec in tool_calls
    }

    # Hard Deadline：等待最多 1500ms
    done, pending = await asyncio.wait(
        tasks.keys(),
        timeout=hard_deadline_ms / 1000.0
    )

    # 強制取消所有未完成的請求
    timeout_specs = []
    for task in pending:
        task.cancel()
        timeout_specs.append(tasks[task])

    # 彙整已完成的結果
    completed_results = []
    error_specs = []
    for task in done:
        try:
            completed_results.append(task.result())
        except Exception:
            error_specs.append(tasks[task])

    return PartialResult(
        results=completed_results,
        timeout_tickers=[s.ticker for s in timeout_specs],
        error_tickers=[s.ticker for s in error_specs],
        total_elapsed_ms=...,
    )
```

### 5.2 PartialResult 如何傳給 LLM

將部分結果包裝成 LLM 能理解的系統提示格式：

```
[系統訊息補充]
注意：以下分析基於 12 檔股票的數據。
以下股票因 API 超時（>1500ms）無法取得數據：TSLA, NVDA, AMD。
請在分析報告中明確說明這 3 檔股票的數據暫時缺失，並根據現有 12 檔數據提供最佳分析。
```

LLM（Gemini）接收此提示後，能夠：
1. 在報告開頭說明數據缺失的股票
2. 根據 12 檔股票提供完整的技術分析
3. 建議用戶稍後重新查詢缺失的 3 檔股票

**這比「等 30 秒後回傳 0 個結果」或「等 30 秒後回傳 15 個結果」都要好得多。**

### 5.3 前端 SSE Partial Rendering

前端不需要等 1500ms 截止才能看到數據。透過 Server-Sent Events，每完成一個股票的數據就立即推送：

```
事件流時序：
T=0ms    → SSE 連線建立，前端顯示「載入中...」
T=180ms  → SSE event: {ticker: "AAPL", data: {...}} → 前端渲染 AAPL 卡片
T=250ms  → SSE event: {ticker: "MSFT", data: {...}} → 前端渲染 MSFT 卡片
T=380ms  → SSE event: {ticker: "AMZN", data: {...}} → 前端渲染 AMZN 卡片
...
T=1200ms → SSE event: {ticker: "GOOG", data: {...}} → 前端渲染第 12 張卡片
T=1500ms → SSE event: {type: "deadline", timeout: ["TSLA","NVDA","AMD"]}
T=1500ms → SSE event: {type: "complete", llm_analysis: "..."}
T=1500ms → SSE 連線關閉
```

用戶實際感知：前 200ms 就看到第一個結果出現，而非盯著空白等 30 秒。

---

## 六、Fan-Out Semaphore 與背壓控制

### 6.1 為什麼要限制並發數

即使在 asyncio 中，「並發 15 個請求」聽起來不多，但在百萬級場景下：
- 每秒 1000 個用戶發起此類查詢
- 每次查詢 15 個 tool calls
- 瞬時並發 HTTP 請求數：1000 × 15 = **15,000 個同時在飛的 HTTP 請求**

下游 API Provider 的 Rate Limit 通常以「每秒 X 個請求」計算。若每秒 15,000 個請求打向同一個 API，Rate Limit 會立刻觸發。

### 6.2 Fan-Out Semaphore 設計

```
┌─────────────────────────────────────────────┐
│  Fan-Out Controller                          │
│                                             │
│  max_concurrent = 20                        │
│  ┌───────────────────────────────────────┐  │
│  │  asyncio.Semaphore(20)               │  │
│  │                                       │  │
│  │  Running:  [1][2][3]...[20]          │  │
│  │  Waiting:  [21][22][23]...           │  │  ← asyncio.Queue
│  └───────────────────────────────────────┘  │
│                                             │
│  全域 Rate Limit: 200 req/s                 │
│  (Token Bucket in Redis)                    │
└─────────────────────────────────────────────┘
```

**兩層限流**：
1. **本地 Semaphore**（asyncio.Semaphore）：限制單個 Gateway 實例的並發 HTTP 請求數，防止連接池耗盡。建議值：20–50。
2. **全域 Rate Limit**（Redis Token Bucket）：跨多個 Gateway 實例，控制對單個外部 API Provider 的總請求率，防止觸發 Rate Limit。

### 6.3 背壓傳遞

當 Fan-Out Semaphore 滿了，新進來的 tool calls 需要排隊等待。這個等待時間要算入 Hard Deadline 的計時中：

```
T=0ms   → 15 個 ToolCall 進入 Controller
T=0ms   → 前 20 個（本例只有 15 個，全部放行）
T=800ms → TSLA Task 超時閾值 → 觸發 Speculative Request
T=1500ms → Hard Deadline → 強制截止剩餘
```

若有 25 個 ToolCall（超過 Semaphore 限制 20）：

```
T=0ms    → 前 20 個立即放行，5 個進隊列等待
T=200ms  → Task #3 完成 → Semaphore 釋放 → 隊列中的 Task #21 開始
...
T=1500ms → Hard Deadline → 不管隊列中還有幾個，全部取消
```

---

## 七、可觀測性：Traces、Metrics、Logs 的症狀鏈

### 7.1 正常運行時的可觀測性基線

每個 Tool Call 必須產生完整的 span（使用 OpenTelemetry）：

```
Trace: user_query_12345
  └── span: tool_fanout_execute (duration: 1.2s)
        ├── span: tool_call_AAPL (duration: 180ms, status: OK)
        ├── span: tool_call_TSLA (duration: 1500ms, status: TIMEOUT)
        │     └── span: speculative_request_TSLA (duration: 920ms, status: OK)
        ├── span: tool_call_NVDA (duration: 320ms, status: OK)
        └── span: circuit_breaker_check (duration: 2ms)
```

### 7.2 症狀到診斷的鏈條

| 觀測到的症狀 | Metrics 訊號 | 診斷結論 | 處置動作 |
|------------|-------------|---------|---------|
| P99 延遲突然從 1.5s 跳到 5s | tool_call_timeout_rate > 20% | 某個 API Provider 節點故障 | 確認 CB 是否正確 OPEN；檢查備用節點 |
| Speculative 觸發率 > 30% | speculative_trigger_rate = 35% | Speculative 閾值 800ms 設太低，或 API P90 變差 | 調高閾值到 1200ms，或聯繫 API Provider |
| 所有用戶的 partial_count < 10 | timeout_ticker_count > 5 per query | Hard Deadline 1500ms 設太短 | 調高到 2000ms，或優化 Speculative Pool 節點 |
| Redis 連接數爆增 | redis_connections = 95% max | Circuit Breaker 鎖爭用，連接池不足 | 增加 Redis 連接池；或改用本地 LRU 快取 CB 狀態 |

### 7.3 關鍵 Metrics 清單

```
# 必須監控的 4 個指標
tool_fanout_duration_ms{p50, p90, p99}    # 整體 Fan-Out 耗時
tool_call_timeout_rate{by_provider}        # 各 API Provider 的超時率
speculative_trigger_rate                   # 投機執行觸發率
circuit_breaker_state{provider, state}     # 各 CB 的當前狀態

# 告警閾值
tool_fanout_duration_ms p99 > 1600ms → PagerDuty (超過 Hard Deadline 緩衝)
tool_call_timeout_rate > 15% → Slack 警告
circuit_breaker_state{state="OPEN"} count > 2 → PagerDuty
```

---

## 八、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Flip Condition |
|------|------------|--------------|----------------|
| **asyncio.wait()** vs asyncio.gather() | done/pending 分開；超時後不取消 task；可取部分結果 | gather() 超時取消全部；return_exceptions 仍需等最慢的 | 若所有 API 都非常穩定（P99 < 500ms），gather 夠用，實作更簡單 |
| **Speculative Execution** vs 直接等超時 | 800ms 後自動賽跑，P99 延遲從 1500ms 降至 ~900ms；用戶感知更流暢 | 純等超時：每次 P95+ 請求都要等足 1500ms 截止線 | 若 API 費用極高（每次 $0.1+），投機複製成本不可接受，改用 Retry-only |
| **Hard Deadline 1500ms** vs 動態超時 | 給 LLM 的處理時間固定，整體 UX 可預測；易於 SLA 承諾 | 動態超時：每次回傳時間不同，前端 Loading 動畫難以設計 | 若分析結果必須完整（金融合規報告），不可截斷，需動態等待 |
| **Circuit Breaker + Redis** vs 本地狀態 | 多副本 Cloud Run 共享 CB 狀態；一個副本感知到失敗，全部副本立刻熔斷 | 本地狀態：每個副本各自計算，同一壞 API 要每個副本都失敗 3 次才熔斷 | 若只有單副本（小流量），本地 CB 實作更簡單，無需 Redis 依賴 |
| **SSE Partial Rendering** vs WebSocket | SSE 是單向串流，HTTP/1.1 即可；無狀態，Cloud Run 天然支援 | WebSocket：雙向連線，需 sticky session 或 pub/sub relay；Cloud Run 支援但複雜度高 | 若需要用戶端主動推訊息給伺服器（如「停止分析」指令），改用 WebSocket |
| **asyncio.Semaphore(20)** vs 無限並發 | 保護下游 API 不被打爆；防止連接池耗盡；Rate Limit 可預測 | 無限並發：瞬間 15,000 個請求打向 API Provider，必然觸發 Rate Limit，造成大規模超時 | 若下游 API 是自有服務（無 Rate Limit，連接池無限），可提高 Semaphore 至 100+，甚至無限 |

---

## 九、電路斷路器的 Flip 場景詳解

### 9.1 Circuit Breaker 配置的關鍵決策

三個核心參數的工程權衡：

| 參數 | 過小的代價 | 過大的代價 | 推薦值 |
|------|-----------|-----------|-------|
| failure_threshold（熔斷閾值）| 誤熔斷：一次偶發失敗就熔斷 | 反應遲鈍：壞節點要失敗很多次才熔斷 | 3 次（在 60s 視窗內）|
| open_duration（OPEN 持續時間）| 頻繁試探，壞節點未恢復就繼續熔斷 | 節點已恢復但 CB 還在 OPEN，浪費流量 | 30s |
| half_open_probe（試探請求數）| 1 次失敗就回 OPEN，恢復太慢 | 大量試探，若節點剛恢復不穩定會再次熔斷 | 1 次（保守）|

### 9.2 OPEN 狀態下的 Fallback 策略

當某個 API 的 CB 為 OPEN，有三種 Fallback：

1. **備用 Provider**：立刻切換到備用股票數據商（如 Alpha Vantage → Polygon.io），延遲稍增但不超時
2. **快取數據**：返回最近一次成功的數據（標記 `data_age: 5min`），LLM 知悉後在報告中說明
3. **直接標記缺失**：將此股票加入 timeout_tickers 列表，告知 LLM 忽略此檔股票

優先順序：備用 Provider > 快取數據 > 直接缺失標記。

---

## 十、系統效應：量化前後對比

### 10.1 延遲優化

| 場景 | 順序執行 | Phase 1 gather | Phase 2 wait+CB | Phase 3 完整引擎 |
|------|---------|----------------|-----------------|-----------------|
| 全部 API 正常（P50）| 30,000ms | 400ms | 380ms | 300ms |
| 1 個 API 抖動（P90）| 30,000ms | 5,000ms（等超時）| 1,800ms（CB 跳過）| 900ms（投機賽跑）|
| 3 個 API 故障（P99）| 30,000ms | 15,000ms | 2,000ms | 1,500ms（硬截止）|
| 全部 API 正常（P99）| 30,000ms | 2,000ms | 900ms | 800ms |

**核心改善**：從最差 30s → Phase 3 的硬截止 1.5s，**20 倍延遲改善**。

### 10.2 成本對比

| 方案 | API 呼叫次數（15 檔股票）| 月費（10萬次查詢）| 工程複雜度 |
|------|----------------------|-----------------|-----------|
| 順序執行 | 15 次（串行）| $150 | 低 |
| Phase 1 gather | 15 次（並行）| $150 | 低 |
| Phase 2 wait+CB | 15 次（並行，CB 跳過壞節點）| $135（省 10%：CB 跳過避免無效呼叫）| 中 |
| Phase 3 完整引擎 | 15–16 次（約 5% 投機複製）| $142（比 Phase 2 多 5% 投機）| 高 |

### 10.3 可靠性對比

| 指標 | 順序執行 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|---------|
| 單 API 故障時系統可用率 | 60%（1/15 失敗即卡死）| 80%（gather 等超時）| 95%（CB 快速切換）| 99%（CB + 投機）|
| P99 響應時間 | 30,000ms | 15,000ms | 2,000ms | 1,500ms |
| 部分結果可用率 | 0%（全有全無）| 0%（gather 等最慢）| 85% | 99% |
| Rate Limit 觸發率 | < 1%（串行）| 35%（瞬間爆發）| 8%（Semaphore 限流）| 2%（雙層限流）|

### 10.4 前端用戶體驗對比

| 體驗指標 | 舊版（順序）| Phase 3 |
|---------|-----------|---------|
| 首個數據可見時間 (FCP) | 30,000ms | 180ms（第一個 SSE event）|
| 全部數據可見時間 | 30,000ms | 1,500ms（硬截止）|
| 零結果率 | 10%（全部超時時）| 0.1%（幾乎總有部分結果）|
| 用戶放棄率（> 10s 無回應）| 45% | 2% |

---

## 十一、面試答題要點

**面試官問**：「asyncio.gather() 有什麼問題？你會如何設計一個生產級的 Tool Fan-Out 引擎？」

> *「asyncio.gather() 的根本問題是『木桶短板』語意：它等待所有 coroutine 完成，一個慢 API 就能拖垮全部。我的解法分三層：第一，用 asyncio.wait() 替代 gather，它的 done/pending 分離讓我能在硬截止時間（1500ms）到達時，立刻取走已完成的結果，不等剩餘的；第二，在 800ms 閾值觸發 Speculative Execution，對超時的 API 同時向備用節點發起複製請求賽跑，誰先回傳用誰，P99 延遲從 1500ms 降至 900ms；第三，Redis-backed Circuit Breaker 追蹤各 API 節點的失敗狀態，連續失敗 3 次立即熔斷 30 秒，讓後續請求不再傻等已知壞節點的超時；最後，前端用 SSE 實現 Partial Rendering，每完成一個股票立刻推送，用戶在 180ms 後就看到第一個結果，整體從用戶等 30 秒變成 1.5 秒內交出 12 檔高品質分析——20 倍的延遲改善，成本僅增加 5%。」*

---

## 延伸閱讀

- Jeff Dean & Luiz André Barroso, "The Tail at Scale" (2013) — Hedged Request 的原始論文
- Python asyncio 官方文件：`asyncio.wait()` vs `asyncio.gather()` 語意差異
- Martin Fowler, "Circuit Breaker" pattern — circuitbreaker.io
- Netflix Hystrix → Resilience4j — JVM 生態的 Circuit Breaker 參考實作
- OpenTelemetry Python SDK — 為 asyncio Tool Calls 加入 Trace Span

---

**系列導航**

← [Part 51：多模態 Agent 的 RAG 混合檢索架構設計](/posts/fde-interview-guide-part51-multimodal-rag-retrieval-zh/) | [Part 53：下一篇主題](/posts/fde-interview-guide-part53-agent-memory-architecture-zh/) →
