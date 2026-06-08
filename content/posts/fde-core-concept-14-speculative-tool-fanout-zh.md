---
title: "FDE core topic - Speculative Tool Execution：大扇出控制與投機雙發防禦"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入剖析 Agent 並行 15 個工具呼叫時如何以投機雙發（Hedged Request）壓制 P99 尾部延遲、用硬截止時間搭配優雅降級回傳部分結果，將整體等待從 30 秒壓到 1.5 秒（20 倍改善）。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "Performance", "FanOut", "SpeculativeExecution"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Speculative Tool Execution（投機工具執行）是在 Agent 大扇出場景下，透過「投機雙發」消滅慢尾端呼叫、「硬截止時間 + 部分結果標注」防止最慢的單一 API 拖垮整體回應，讓 N 個並行工具呼叫的完成時間趨近第 50 百分位而非第 99 百分位延遲。**

---

## 一、為什麼面試官問這個

面試官真正在測試的是你對**尾部延遲（Tail Latency）的工程直覺**，以及你能否在「並行 = 快」的表面認知背後，看見「任一慢者拖垮全局」這個隱藏陷阱。這題在 FDE 面試、平台工程師面試中高頻出現，因為 LLM Agent 架構幾乎都有大扇出需求——爬多個資料源、同時呼叫多個外部 API、並行執行多個查詢工具——而大多數候選人對這個問題的認識停留在「用 asyncio 並行就好」。

**測試點一：尾部延遲量化能力。**
你能否當場說清楚：15 個呼叫各有 P50=2s、P99=3s 的延遲分佈，`asyncio.gather` 的完成時間趨近所有呼叫延遲的最大值，而非平均值。數學上，15 個獨立隨機變數的最大值期望值遠大於單一變數期望值。面試官想看到工程師對資源等待的量化直覺，而不是模糊的「並行比序列快」。

**測試點二：降級設計思維。**
你能否清楚說明「不需要所有資料才能給出有用回應」，並設計出讓 LLM 在缺少部分資料時仍能產出帶標注的分析，而不是直接報錯或讓使用者白等到逾時。弱候選人把「部分成功」當例外狀況處理；強候選人把部分成功當主路徑設計，並知道如何在 System Prompt 中預先教會模型處理缺失欄位。

**測試點三：熔斷與防護層設計。**
能否描述 Circuit Breaker 的三個狀態（Closed / Open / Half-Open）、觸發條件（連續失敗 5 次 → 開路 30 秒）、以及如何與投機雙發機制協同而不互相衝突（例如：熔斷開路時不應再觸發 hedge，應直接走備援路徑）。

**弱答案典型樣貌：** 「我用 `asyncio.gather` 並行呼叫，然後設一個 timeout 參數。」無法量化改善幅度、未討論部分結果標注、不知道 `gather` 與 `wait` 的差異、沒有熔斷機制設計、沒說清楚 SSE 與輪詢的取捨。

**強答案典型樣貌：** 從尾部延遲的數學切入（「15 個呼叫的 P99 等於 max()，趨近最慢者」），說明投機雙發在 T+800ms 觸發的條件與取消邏輯，描述 T+1500ms 硬截止 + 13/15 partial 標注的 graceful degradation，點出 Circuit Breaker 的狀態機，最後給出 30s → 1.5s（20 倍）的具體改善數字，並提到 SSE 漸進推送讓主觀等待感進一步下降。

---

## 二、核心原理與技術深度

### 2.1 扇出的尾部延遲問題：數學根源

當 Agent 並行發出 N 個工具呼叫，整體完成時間 T_total 是 N 個獨立延遲的最大值：

```
T_total = max(X₁, X₂, ..., Xₙ)
```

若每個呼叫 Xᵢ 服從指數分佈（P50=2s, P99=3s），當 N=15 時：

```
P(T_total > 3s) = 1 - P(所有 Xᵢ < 3s)¹⁵
               ≈ 1 - 0.99¹⁵
               ≈ 14%   ← 不可忽略的高概率
```

換言之，即使每個單一呼叫的 P99 = 3s，15 個並行呼叫的整體延遲超過 3s 的機率高達 **14%**。這是純數學問題，不是 bug。

```
呼叫延遲分佈示意（15 個並行呼叫，無防護）

延遲(ms) │
3000     │                          ●  ← 此呼叫決定 gather 完成時間
2800     │                    ●
2500     │              ●  ●
2200     │        ●  ●
2000     │  ● ●● ●●●●
1800     │●
1500     │──────────────────────────────── ← 硬截止線（T+1500ms）
1000     │
   0     └──────────────────────────────────▶ 呼叫序號
          1  2  3  4  5  6  7  8  9 10 11 12 13 14 15

gather 在 3000ms 才完成（被 #15 拖住）
硬截止在 1500ms 取消 #14, #15，損失 2 個結果，得到 13/15
```

### 2.2 投機雙發（Hedged Request）機制

投機雙發借鑑自 Bigtable 的 Hedged Reads 設計（Jeff Dean, "The Tail at Scale", 2013）：**不等慢者超時，而是在預定閾值後主動發第二個請求到備援端點，接受最先回應者，取消另一個。**

```
時間軸：投機雙發完整流程

T+0ms    ┌──────────────────────────────────────────────────┐
         │  發出請求 Primary → API-A（主端點）               │
         └──────────────────────────────────────────────────┘

T+800ms  ┌──────────────────────────────────────────────────┐
         │  監測：API-A 尚無 response header（頭部未到）？   │
         │  是 → 投機發出副本 Hedge → API-A'（備援端點）     │
         │  否 → 繼續等 API-A，不觸發 hedge                 │
         └──────────────────────────────────────────────────┘

T+950ms  ┌────────────────────────┐
         │ API-A' 先回應（200 OK）│  ← 接受此結果
         └────────────────────────┘
         → asyncio.cancel(API-A task)
         → 回傳 API-A' 結果給 aggregator

T+1100ms（假設 API-A 這時才回應）→ 已被 cancel，忽略

╔═══════════════════════════════════════════════════════════╗
║  投機雙發效果：P99 尾部延遲降低約 40%                      ║
║  代價：在慢尾端場景增加 ~1 次 API 呼叫費用                  ║
║  適用前提：工具呼叫必須是冪等操作（只讀，或具備冪等鍵）       ║
╚═══════════════════════════════════════════════════════════╝
```

Hedge 觸發閾值選擇原則：
- 固定閾值：設為 API 的 P75 延遲（例如 800ms = API P75）
- 自適應閾值（企業級）：滾動計算每個端點的 P75，動態調整 hedge 時機
- 永遠不要設為 P99（那樣投機雙發幾乎沒有效果）

### 2.3 asyncio.wait() vs asyncio.gather() 的關鍵差異

這是面試官常問的低層細節，候選人常答錯：

| 特性 | `asyncio.gather()` | `asyncio.wait()` |
|------|-------------------|-----------------|
| 錯誤傳播 | 預設任一失敗即全部拋出 Exception | 失敗任務進入 done set，可逐一檢查 |
| 提前返回 | 不支援 | 支援 `FIRST_COMPLETED` / `FIRST_EXCEPTION` |
| 取得部分結果 | 不安全（例外中途無法取得） | 天然支援（done set 有所有已完成任務） |
| 取消 pending 任務 | 粗粒度（cancel all or none） | 可逐一 cancel pending 集合 |
| 回傳值型別 | `list[result]`，順序對應輸入 | `tuple[done_set, pending_set]` |
| 適合場景 | 所有結果都必要、任一失敗整體失敗 | 延遲敏感大扇出、需要部分成功語義 |

**結論：大扇出場景必須使用 `asyncio.wait()`，禁止在延遲敏感路徑使用 `asyncio.gather()`。**

### 2.4 熔斷器（Circuit Breaker）狀態機

```
                連續失敗 ≥ 5 次
  Closed ───────────────────────────▶ Open
(正常路由)                          (開路 30s)
    ▲                                    │
    │    探測請求成功                      │ 等待 30 秒後
    │                                    ▼
    └──────────────────────────────── Half-Open
                                   (放行 1 個探測請求)
                                   探測請求失敗 → 重設 Open 計時
```

**Closed 狀態（正常）：** 所有請求正常路由至主端點，記錄成功/失敗計數。  
**Open 狀態（熔斷中）：** 所有請求立即走備援路徑或回傳快取值，不嘗試主端點。持續 30 秒。  
**Half-Open 狀態（探測中）：** 放行 1 個請求試探主端點是否恢復。成功 → 回 Closed；失敗 → 重設 30 秒 Open 計時。

熔斷器狀態必須存於 Redis（非記憶體），否則多 Pod 環境下每個 Pod 各自計算失敗次數，無法協同觸發熔斷，在高並行下會讓問題 API 繼續被打爆。

### 2.5 Server-Sent Events（SSE）漸進推送

不等所有 15 個工具完成後一次回傳，而是每完成一個就立即透過 SSE 推送到前端：

```
T+200ms  → Tool #3 完成 → SSE: {"tool": "AAPL", "price": 189.2}
T+350ms  → Tool #7 完成 → SSE: {"tool": "MSFT", "price": 421.5}
T+600ms  → Tool #1 完成 → SSE: {"tool": "META", "price": 512.3}
...（陸續推送）
T+1500ms → 截止，cancel #14, #15
           → SSE: {"warning": "TSLA, NVDA unavailable. 13/15 sources."}
           → SSE: [DONE]
```

使用者在 T+200ms 就看到第一個結果出現在畫面上，主觀等待感遠低於「等 1.5 秒後一次出現 13 個結果」。這是效能感知（Perceived Performance）工程的重要手法。

SSE 的基礎設施需求：反向代理不能緩衝回應（Nginx 需設 `X-Accel-Buffering: no`）；無法使用傳統無狀態 Lambda（需要持久連線）；適合使用 Cloud Run 或容器化服務。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**做什麼：** `asyncio.gather()` 加上統一 timeout，無降級邏輯，快速上線。

```python
async def fan_out_minimal(tools: list[ToolCall]) -> list[Any]:
    # 快：比序列快 N 倍
    # 問題：任一失敗 → 全部 raise；超時後無部分結果
    return await asyncio.wait_for(
        asyncio.gather(*[call_tool(t) for t in tools]),
        timeout=3.0
    )
```

**解決了什麼：** 比順序呼叫快 N 倍（15 × 2s = 30s → 約 2–3s），有基本超時保護，工程師一小時內可完成。  
**留下什麼問題：** 任一工具失敗整體失敗；超時後使用者得到錯誤頁而非部分結果；P99 仍由最慢者決定；無防護擋不住下游 rate limit 雪崩。  
**成本/複雜度：** 開發 0.5 天；無額外基礎設施；但使用者體驗在尾部場景下很差。  
**何時夠用：** 工具數量 ≤ 3、所有 API 都在 VPC 內且極少超時、原型驗證階段。

---

### Layer 2 — 生產就緒（Production-Ready）

**做什麼：** 改用 `asyncio.wait()` + 硬截止時間 + 部分結果標注 + Circuit Breaker（Redis 狀態）+ 並行數上限。

```python
MAX_CONCURRENT = 20   # 每次 Agent 呼叫最多 20 個並行

async def fan_out_production(
    tool_calls: list[ToolCall],
    deadline_ms: int = 1500,
) -> FanOutResult:

    # 超過上限的分批執行，避免打爆下游 rate limit
    batch = tool_calls[:MAX_CONCURRENT]
    overflow = tool_calls[MAX_CONCURRENT:]

    tasks: dict[asyncio.Task, ToolCall] = {
        asyncio.create_task(call_tool_with_circuit_breaker(tc)): tc
        for tc in batch
    }

    done, pending = await asyncio.wait(
        tasks.keys(),
        timeout=deadline_ms / 1000,
    )

    # 取消所有未完成任務
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    # 收集結果與缺失清單
    results: dict[str, Any] = {}
    missing: list[str] = []

    for task, tc in tasks.items():
        if task in done:
            exc = task.exception()
            if exc is None:
                results[tc.name] = task.result()
            else:
                missing.append(tc.name)   # 失敗任務視為缺失
        else:
            missing.append(tc.name)       # 超時取消視為缺失

    warning = None
    if missing:
        warning = (
            f"Warning: {', '.join(missing)} data unavailable. "
            f"Analysis based on {len(results)}/{len(batch)} sources."
        )

    return FanOutResult(results=results, missing=missing, warning=warning)
```

**Circuit Breaker 整合（Redis 狀態）：**

```python
async def call_tool_with_circuit_breaker(tc: ToolCall) -> Any:
    state = await redis.get(f"cb:{tc.endpoint}")

    if state == "open":
        # 熔斷中：走快取或備援
        cached = await redis.get(f"cache:{tc.name}")
        if cached:
            return json.loads(cached)
        raise CircuitOpenError(f"{tc.endpoint} circuit open")

    try:
        result = await call_tool(tc)
        await redis.delete(f"cb_failures:{tc.endpoint}")  # 重設失敗計數
        await redis.setex(f"cache:{tc.name}", 300, json.dumps(result))
        return result
    except Exception:
        count = await redis.incr(f"cb_failures:{tc.endpoint}")
        if count >= 5:
            await redis.setex(f"cb:{tc.endpoint}", 30, "open")  # 開路 30s
        raise
```

**System Prompt 關鍵段落（讓 LLM 正確處理缺失資料）：**

```
若工具回傳資料標記為 unavailable 或包含 Warning 標注，
請在回應中明確說明哪些資料來源缺失，
並依據現有可用資料給出最佳分析。
不要因為資料不完整而拒絕回答或補充你自己的估計數字。
```

**解決了什麼：** 硬截止保證使用者等待上限 ≤ 1.5s；部分結果讓 LLM 仍能給出有用回應；Circuit Breaker 防止雪崩效應；並行數上限防止下游被打爆。  
**留下什麼問題：** 尚未實作投機雙發；無 SSE 漸進推送（使用者仍一次等到截止）；Hedge 閾值是固定值不夠自適應。  
**成本/複雜度：** 開發 2–3 天；需要 Redis（Circuit Breaker 狀態）；月費約 $30–50（Redis Memorystore Basic 實例）。

---

### Layer 3 — 企業級（Enterprise-Grade）

**做什麼：** 投機雙發（Hedged Request）+ SSE 漸進推送 + 自適應 Hedge 閾值 + 全鏈路可觀測性（Traces / Metrics / Logs）。

```
                   ┌─────────────────────────────────────────────┐
                   │         Agent Orchestrator                   │
                   │  （接收 LLM tool_calls，分派扇出任務）         │
                   └──────────────┬──────────────────────────────┘
                                  │ 最多 20 個並行 task
         ┌────────────────────────┼──────────────────┐
         ▼                        ▼                  ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  HedgedCaller    │   │  HedgedCaller    │   │  HedgedCaller    │
│  Tool: AAPL      │   │  Tool: MSFT      │   │  Tool: TSLA      │
│  Primary: API-A  │   │  Primary: API-B  │   │  Primary: API-C  │
│  Backup:  API-A' │   │  Backup: API-B'  │   │  Backup: API-C'  │
│  HedgeAt: P75ms  │   │  HedgeAt: P75ms  │   │  HedgeAt: P75ms  │
└────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
         │ result                │ result                │ result / timeout
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Result Aggregator                                               │
│  ・每完成一個 → SSE push {"ticker": "AAPL", "price": 189.2}     │
│  ・T+1500ms  → cancel pending, emit warning + [DONE]            │
│  ・記錄各工具 p50/p99 → 更新 Redis 中的自適應 hedge 閾值         │
└────────────────────────────┬────────────────────────────────────┘
                             │ SSE stream (Content-Type: text/event-stream)
                             ▼
                   ┌─────────────────────┐
                   │  Browser / Client   │
                   │  漸進式渲染           │
                   │  200ms → 首個結果    │
                   │  350ms → 第二個結果  │
                   │  ...                │
                   │  1500ms → DONE      │
                   └─────────────────────┘
```

**自適應 Hedge 閾值實作：**

```python
async def get_hedge_threshold(endpoint: str) -> float:
    """從 Redis 取得該端點的滾動 P75 延遲作為 hedge 閾值"""
    p75_ms = await redis.get(f"latency_p75:{endpoint}")
    if p75_ms is None:
        return 800.0   # 預設 800ms
    return min(float(p75_ms), 1200.0)  # 最大不超過 1200ms

async def record_latency(endpoint: str, latency_ms: float):
    """記錄延遲到 Redis sorted set，定期計算 P75"""
    key = f"latency_samples:{endpoint}"
    await redis.zadd(key, {time.time(): latency_ms})
    await redis.zremrangebyscore(key, 0, time.time() - 3600)  # 保留 1 小時
    # 非同步計算 P75（避免阻塞主路徑）
    asyncio.create_task(update_p75(endpoint))
```

**可觀測性指標（應接入 Cloud Monitoring）：**

| 指標名稱 | 說明 | 告警閾值 |
|---------|------|---------|
| `fan_out.p50_latency_ms` | 扇出整體 P50 延遲 | > 800ms 警告 |
| `fan_out.p99_latency_ms` | 扇出整體 P99 延遲 | > 2000ms 告警 |
| `fan_out.hedge_fired_rate` | 每分鐘投機雙發觸發次數 | > 20% 工具觸發 hedge 須調查 |
| `fan_out.partial_results_ratio` | 部分結果回傳比例 | > 5% 須告警（資料來源不穩定） |
| `circuit_breaker.open_count` | 熔斷開路次數（每小時） | > 3 次須告警 |
| `circuit_breaker.open_duration_s` | 熔斷持續時間 | > 60s 須 page on-call |

**SSE 基礎設施注意事項：**
- Nginx：需設 `X-Accel-Buffering: no` 停用緩衝，否則 SSE 事件會累積到緩衝區滿才一次推送
- Cloud Run：`--max-instances` 需考慮 SSE 長連線佔用的並行配額（每個連線在整個扇出期間都是活躍的）
- 費用：SSE 連線比 REST 輪詢省約 70% 的請求費用（無需客戶端重複輪詢）

**解決了什麼：** P99 尾部延遲降低 40%（投機雙發）；主觀等待感大幅下降（SSE 漸進推送）；Hedge 閾值自動適應端點健康狀態；全鏈路 Trace 讓每個工具呼叫的延遲分佈可見。  
**成本/複雜度：** 開發 1–2 週；需要 Redis + SSE 相容的反向代理 + Cloud Monitoring 自訂指標；月費約 $150–300（依流量規模）。

---

## 四、系統效應：前後對比

以下以一個真實場景為基準：金融分析 Agent 並行呼叫 15 個股票報價 API，每個 API P50=2s、P99=3s，QPS=10（即每秒有 10 個使用者觸發此扇出）。

| 維度 | 無防護（asyncio.gather）| 有防護（Layer 2）| 有防護（Layer 3）|
|-----|----------------------|----------------|----------------|
| 整體 P50 延遲 | 2.5s（max 分佈）| 1.5s（硬截止）| 1.5s（硬截止）|
| 整體 P99 延遲 | 3.2s（max 分佈）| 1.5s（硬截止）| 1.0s（hedge 介入）|
| 任一 API 失敗後果 | 整體 500 Error | 部分結果 + Warning | 部分結果 + Warning |
| 使用者看到第一個結果 | 2.5s 後一次全部 | 1.5s 後一次全部 | 200ms 後漸進推送 |
| 下游 API 保護 | 無（N=50 可能打爆）| MAX=20 + Circuit Breaker | MAX=20 + Hedge + CB |
| 每次扇出 API 費用 | 15 次呼叫 | 13–15 次呼叫（降級後省）| 13–17 次呼叫（hedge 多 1–2 次）|
| 開發複雜度 | 低（0.5 天）| 中（2–3 天）| 高（1–2 週）|
| 月額外基礎設施費用 | $0 | $30–50（Redis）| $150–300（Redis + 監控）|

**關鍵數字總結：**
- 順序執行：15 × 2s = **30 秒**
- 並行無防護：趨近 P99 = **3 秒**（10 倍改善，但尾部問題未解）
- 並行 + 硬截止 1.5s：**1.5 秒**（20 倍改善）
- 並行 + 硬截止 + 投機雙發：P99 降至 **~1.0 秒**（30 倍改善）
- SSE 主觀感知：使用者在 **200ms** 內看到第一批結果

### 症狀-診斷-根因鏈（Symptom → Diagnosis）

工程師在 Production 上看到的訊號，以及如何對應到本篇的哪個防護機制失效：

```
症狀：Trace 顯示 fan-out span 的 P99 = 3.2s，但每個子 span P99 各自只有 1.0s
診斷：asyncio.gather 把最慢子 span 的延遲放大到整體層面
根因：max(X₁...Xₙ) 效應；應換用 asyncio.wait + 硬截止
```

```
症狀：每小時約 3% 的 fan-out 請求返回 500，日誌顯示 "All tasks failed"
診斷：某一個下游 API 偶爾 502，gather 的 return_exceptions=False 讓整體拋出
根因：gather 的錯誤傳播語義；應改 wait + 逐一檢查 task.exception()
```

```
症狀：Circuit Breaker 在 A Pod 開路，但 B Pod 繼續打問題 API
診斷：熔斷狀態存於各 Pod 記憶體，無法跨 Pod 同步
根因：需要 Redis 共享狀態；所有 Pod 讀寫同一個 cb:{endpoint} 鍵
```

```
症狀：LLM 回應中出現明顯幻覺數字（例如 TSLA 的均值計算包含了 TSLA 自身）
診斷：部分結果缺少 Warning 標注，LLM 以為收到完整 15 筆資料
根因：硬截止後未注入缺失標注到 prompt；或 System Prompt 未教模型處理缺失資料
```

---

## 五、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 用 `asyncio.gather` 做延遲敏感扇出 | 任一失敗 → 全部拋出 Exception；無法安全取得部分結果 | 改用 `asyncio.wait()` 配合手動 cancel pending 集合 |
| 扇出數量無上限（N=50+） | 瞬間觸發下游 API Rate Limit，引發 429 雪崩，Circuit Breaker 全部開路 | 硬性限制 `MAX_CONCURRENT=20`，超出部分分批順序執行 |
| Hedge 請求不取消原始請求 | 兩個請求都完成：浪費 API 費用；若工具有副作用則可能執行兩次（例如寫入資料） | 接受第一個回應後立即 `task.cancel()`；投機雙發**僅適用冪等操作** |
| 硬截止後不標注缺失資料 | LLM 以為資料完整，用錯誤前提產出分析（幻覺加劇，例如用 13 筆資料計算「全部 15 筆的均值」） | 明確在 prompt 注入 `"Warning: TSLA, NVDA unavailable (13/15 sources)"` |
| System Prompt 未教 LLM 處理缺失欄位 | LLM 遇到不完整資料時拒絕回答，或自行補充虛構數字 | System Prompt 明確指示：「缺失資料請標注後繼續分析，不要補充估計值」 |
| Circuit Breaker 狀態存於記憶體 | 多 Pod 環境下各 Pod 各自計算失敗次數，無法協同熔斷；問題 API 繼續被打爆 | 熔斷狀態與失敗計數存 Redis，所有 Pod 共享同一狀態 |
| Hedge 閾值設為固定 P99 | Hedge 幾乎從不觸發（因為 P99 已是最慢的 1%）；投機雙發形同虛設 | 閾值設為 P75，讓 25% 的慢尾端請求都能獲得 hedge 保護 |

---

## 六、與其他核心主題的關聯

**Core Topic 11（Async Event-Driven Pipeline）**：扇出的每個工具呼叫本質上是一個 async task；當單一工具耗時超過 2 秒且屬於非阻塞查詢時，可考慮 Pub/Sub 化，讓 Worker 非同步執行並透過 SSE 回傳結果，進一步解耦 Web Server 與工具執行時間。大扇出與 async pipeline 的邊界判斷：< 2s 工具用本篇的 asyncio.wait + 截止；> 5s 工具用 Pub/Sub + Worker 模式。

**Core Topic 3（State Machine / DAG）**：複雜 Agent 的工具呼叫並非全部可並行——DAG 拓撲決定哪些節點可同層扇出（無依賴邊）、哪些必須等待前驅完成（有依賴邊）。本篇的扇出控制只適用於 DAG 同一層的無依賴節點。多層 DAG 中，每層可獨立應用本篇的 hedge + 截止策略。

**Core Topic 1（Context Management）**：部分結果的 Warning 標注文字會消耗 tokens（「TSLA, NVDA, AMZN data unavailable. Analysis based on 12/15 sources.」約 20 tokens）；在 context window 已近上限時，需確保警告文字優先不被截斷，否則 LLM 會以為資料完整。建議把 Warning 注入 system prompt 開頭而非 user message 末尾。

**Core Topic 6 / 7（Prompt Injection）**：投機雙發從備援端點取回的資料同樣可能攜帶 Indirect Prompt Injection 攻擊（惡意網頁在抓取結果中注入指令）；備援端點不代表安全，仍需同樣的 input sanitisation 流程。

**fde-interview-guide Part 35–38（生產工程缺口）**：P99 監控與 SLO 定義章節直接呼應本篇的可觀測性設計；Circuit Breaker 的 Open 持續時間超過 60 秒時應觸發 SLO burn rate alert，提醒 on-call 工程師下游 API 健康狀況惡化。本篇的 `fan_out.partial_results_ratio > 5%` 告警應納入 Error Budget 消耗計算。

---

## 七、面試一句話（Killer Phrase）

> *「大扇出的核心陷阱是尾部延遲由最慢者決定：15 個並行呼叫的完成時間在數學上等同於取所有延遲的最大值，任一呼叫的 P99 問題都會變成整體的 P0 問題。我的防禦策略分三層：第一，投機雙發（Hedged Request）—在 T+800ms 若工具呼叫未收到 response header，立即對備援端點發第二個請求，接受先回應者並 cancel 另一個，實測 P99 尾部延遲降低 40%；第二，T+1500ms 硬截止—用 asyncio.wait() 而非 gather 取得已完成的 13/15 筆資料，在 System Prompt 注入缺失標注讓 LLM 明確知道資料不完整仍繼續分析；第三，Circuit Breaker—失敗 5 次開路 30 秒，狀態存 Redis 讓所有 Pod 協同熔斷。整體效果：30 秒順序執行壓到 1.5 秒（20 倍改善），加上 SSE 漸進推送讓用戶在 200ms 內就看到第一批結果，主觀等待感接近即時。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-13-rate-limiting-token-bucket-zh/) | [後一篇](/posts/fde-interview-core-topic-15-vector-index-hnsw-zh/) →
