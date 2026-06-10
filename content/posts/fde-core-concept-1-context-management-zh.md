---
title: "FDE core topic - Context Management：Token 預算管理與上下文修剪策略"
date: 2026-06-08T10:00:00+08:00
draft: false
weight: 1
description: "深入解析 LLM 有限上下文視窗的管理策略，涵蓋 Token 預算分配、滑動視窗截斷、階層式摘要壓縮與工具輸出修剪，幫助你在面試中展現生產級 AI 系統設計能力。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "LLM", "RAG", "TokenBudget"]
authors: ["yen"]
readTime: "18 min"
---

**Context Management 的本質是：在有限的 Token 預算內，決定哪些資訊值得保留、哪些必須壓縮或捨棄——這是所有長對話 AI 系統的核心資源排程問題。**

---

## 一、為什麼面試官問這個

面試官測試的核心能力：

- **系統資源意識**：你是否理解 LLM 的上下文視窗是有限的硬性限制，而非軟性建議？能否量化每個元件的 Token 消耗？Token waterfall 問題若不主動管理，100 輪對話後必然觸發截斷或 OOM。
- **Trade-off 判斷力**：截斷策略的選擇（FIFO vs. 重要性加權 vs. 摘要壓縮）直接影響對話品質，面試官想看你能否說清楚「何時選哪種、代價是什麼」，而不是背誦一個萬用答案。
- **生產可操作性**：理論上知道「要做 context trimming」很容易，但能否描述 LangGraph MemorySaver 的週期摘要節點、如何做 tenant-level 成本歸因，才是資深工程師的標誌。

**弱答案長這樣**：「我們用滑動視窗，把最舊的訊息刪掉就好。」——沒有量化 Token 預算、沒有解釋為什麼 FIFO 在長對話中會丟失關鍵系統指令。

**強答案長這樣**：「128K context 視窗中，system prompt 佔 8K、tools schema 佔 12K，剩餘 108K 給 history + answer。我們設 history ceiling 為 80K、answer reserve 為 28K。超過 history ceiling 時觸發階層式摘要：先壓縮最舊的 20 輪，~6K tokens 壓成 ~500 tokens，然後再做 FIFO。這樣能維持對話連貫性同時控制成本。壓縮比約 13:1，每次摘要呼叫用 Gemini Flash，成本不到主對話的 5%。」

---

## 二、核心原理與技術深度

### Token 預算分配公式

LLM 的上下文視窗 $C$ 是固定上限（以 Claude Sonnet 4 為例：200K tokens；Gemini 1.5 Pro：1M tokens；GPT-4o：128K tokens）。每次推理呼叫的 Token 組成：

```
C = P_system + P_tools + P_history + P_answer_reserve

其中：
  P_system        = system prompt tokens（通常 4K–16K）
  P_tools         = tools/function schema tokens（每個工具約 200–800 tokens）
  P_history       = 對話歷史 tokens（動態增長，主要管理目標）
  P_answer_reserve= 輸出保留空間（通常 4K–32K）
```

以具體數字為例（128K context 視窗）：

```
C          = 128,000 tokens
P_system   =   8,000 tokens  (system prompt)
P_tools    =  12,000 tokens  (15 個工具 × 平均 800 tokens)
P_reserve  =  16,000 tokens  (answer reserve)
─────────────────────────────
P_history  ≤  92,000 tokens  (history ceiling)
```

**Token Waterfall 問題**：若不主動管理，每輪對話累積 ~800 tokens（user + assistant 各 ~400），成長曲線：

```
Turn 10  →   8,000 tokens   (9% history ceiling)   安全
Turn 50  →  40,000 tokens   (43% history ceiling)  警戒
Turn 100 →  80,000 tokens   (87% history ceiling)  危險
Turn 115 →  92,000 tokens   觸發 OOM 或強制截斷    ← 問題發生點
```

### 上下文視窗的記憶體布局

```
┌───────────────────────────────────────────────────────────────┐
│  CONTEXT WINDOW  (128K tokens = 100%)                         │
├──────────────┬─────────────────┬─────────────────────────────┤
│ System Prompt│  Tools Schema   │  History Budget             │
│   8K ( 6%)   │   12K ( 9%)     │   92K (72%)                 │
│   [靜態]     │   [半靜態]      │   [動態，需主動管理]        │
│              │  啟動時一次計算  │  每輪 +800 tokens，需修剪  │
└──────────────┴─────────────────┴──────────────┬──────────────┘
                                                │ Answer Reserve
                                                │ 16K (13%)
                                     ┌──────────▼──────────────┐
                                     │  [輸出空間，不可壓縮]   │
                                     │  設太小 → 輸出被截斷    │
                                     │  設太大 → history 空間少│
                                     └─────────────────────────┘
```

### 三種截斷策略的機制圖

**策略一：FIFO（先進先出截斷）**

最簡單，直接丟棄最舊的訊息。問題：若第一輪定義了「角色設定」或「任務目標」，FIFO 會把最重要的上下文刪掉。

```
FIFO 截斷前：                    FIFO 截斷後（超出 ceiling）：
┌─────────────────────┐          ┌─────────────────────┐
│ Turn  1: [角色定義] │ ← 刪除   │ Turn 21: 普通問答   │
│ Turn  2: [任務目標] │ ← 刪除   │ Turn 22: 普通問答   │
│ Turn  3: [重要約束] │ ← 刪除   │ ...                 │
│ ...                 │          │ Turn 49: 當前話題   │
│ Turn 20: 普通問答   │ ← 刪除   │ Turn 50: 最新輸入   │
│ Turn 21: 普通問答   │ ← 保留   └─────────────────────┘
│ ...                 │          問題：角色設定消失，
│ Turn 50: 最新輸入   │ ← 保留   模型行為改變
└─────────────────────┘
```

**策略二：重要性加權截斷（Importance-Weighted）**

為每個 turn 計算重要性分數，優先保留高分 turn。

```
重要性分數計算：
  score(turn_i) = α × recency_score(i)
                + β × semantic_relevance(turn_i, current_query)
                + γ × explicit_marker_score(turn_i)

其中：
  recency_score  = exp(-λ × age)          (λ ≈ 0.05，衰減因子)
  semantic_score = cosine_sim(embed(turn), embed(query))
  marker_score   = 1.0 if contains("記住", "重要", "必須") else 0.0
  α=0.3, β=0.5, γ=0.2

典型分數範例：
  Turn  1 [角色定義]   → recency=0.08, semantic=0.9, marker=1.0 → score=0.75  ← 高，保留
  Turn 20 [普通問答]   → recency=0.37, semantic=0.2, marker=0.0 → score=0.21  ← 低，可刪
  Turn 49 [相關討論]   → recency=0.90, semantic=0.8, marker=0.0 → score=0.67  ← 高，保留
```

代價：每次截斷需要做 embedding 計算，約 +5–10ms latency（可用 cache 優化到 <1ms）。

**策略三：階層式摘要壓縮（Hierarchical Summarization）**

```
觸發前（history > 80% ceiling）：
┌────────────────────────────────────────────┐
│  Turn 1–20  ≈ 16,000 tokens  [待壓縮]      │
│  Turn 21–50 ≈ 24,000 tokens  [保留完整]    │
│  Total      ≈ 40,000 tokens                │
└───────────────────┬────────────────────────┘
                    │  呼叫輕量摘要模型
                    ▼
┌────────────────────────────────────────────┐
│  摘要節點（Gemini Flash / Claude Haiku）   │
│  Prompt: "壓縮為 500 tokens，保留：        │
│    - 使用者目標與角色設定                  │
│    - 已確認的事實與決策                    │
│    - 尚未解決的問題                        │
│  省略：重複問答、格式說明、中間推理"       │
└───────────────────┬────────────────────────┘
                    │  輸出 ≈ 500 tokens
                    ▼
觸發後：
┌────────────────────────────────────────────┐
│  [SUMMARY] Turn 1–20 摘要  ≈    500 tokens │
│  [LIVE]    Turn 21–50      ≈ 24,000 tokens │
│  Total                     ≈ 24,500 tokens │
│  節省：40,000 → 24,500（-38.75%）          │
└────────────────────────────────────────────┘
```

**壓縮效果量化**：

| 策略 | 50 輪後 tokens | 100 輪後 tokens | 對話品質 | 延遲開銷 |
|------|--------------|----------------|---------|---------|
| 無管理 | 40K | 80K（接近 OOM）| 高（直到爆掉）| 0ms |
| FIFO | 40K（固定上限）| 40K | 中（失憶風險）| <1ms |
| 重要性加權 | 40K（固定上限）| 40K | 高 | +5–10ms |
| 階層式摘要 | 24.5K | 24.5K（持續壓縮）| 最高 | +500–1000ms（每 20 輪一次）|

### 工具輸出修剪（Tool Output Trimming）

工具呼叫回傳的 JSON 往往是 token 最大的浪費來源。一次搜尋工具可能回傳 20 筆結果，每筆含長文本與大量 metadata，輕易超過 2,000 tokens。

```
工具呼叫前後的 Context 占用：

呼叫前  ──────── 工具呼叫（搜尋 20 筆結果）──────── 呼叫後（未修剪）
history=30K                                           history=30K + 工具輸出
                                                      = 30K + 2,400 = 32,400K

若連續 10 次工具呼叫，未修剪：
  history = 30K + (10 × 2,400) = 54,000 tokens  ← 工具輸出佔 55%
  
若每次工具輸出修剪至 180 tokens：
  history = 30K + (10 × 180)   = 31,800 tokens  ← 工具輸出只佔 6%
```

修剪後的 JSON 結構（以搜尋工具為例）：

```python
def trim_tool_output(raw: dict, tool_name: str) -> dict:
    """標準化工具輸出修剪"""
    config = TRIM_CONFIG[tool_name]  # per-tool 設定
    result = {}

    # 1. 陣列截斷：只保留 top-N
    if "results" in raw:
        result["results"] = [
            _trim_item(item, config.keep_fields, config.max_content_chars)
            for item in raw["results"][:config.top_n]  # top_n = 3–5
        ]

    # 2. 保留關鍵計數欄位（用於後續推理）
    for key in config.keep_scalar_keys:   # ["total_count", "status"]
        if key in raw and raw[key] is not None:
            result[key] = raw[key]

    # 3. 隱式：忽略 debug_info, trace_id, null 欄位
    return result

def _trim_item(item: dict, keep_fields: list, max_chars: int) -> dict:
    trimmed = {k: v for k, v in item.items() if k in keep_fields and v is not None}
    if "content" in trimmed and len(trimmed["content"]) > max_chars:
        trimmed["content"] = trimmed["content"][:max_chars] + "...[truncated]"
    return trimmed
```

修剪規則優先順序：
1. 陣列截斷：只保留 top-N（通常 N=3–5，視 LLM 推理需求而定）
2. 移除 null 值欄位（直接節省 JSON key 空間）
3. 長文字截斷：content > 200 字元時截斷並加 `...[truncated]`
4. 移除純除錯欄位（`debug_info`, `trace_id`, `checksum`, `query_time_ms`）
5. 只保留推理所需欄位（whitelist 模式優於 blacklist）

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**實作方式**：純 FIFO 截斷 + 固定 Token 計數 + 靜態工具輸出截斷

```python
def trim_history_fifo(messages: list, max_tokens: int) -> list:
    """從最新訊息往前保留，直到 token 預算用完"""
    total = 0
    result = []
    for msg in reversed(messages):  # 從最新開始保留
        t = count_tokens(msg)
        if total + t > max_tokens:
            break
        result.insert(0, msg)
        total += t
    return result

# 呼叫前：計算 static overhead
STATIC_TOKENS = count_tokens(SYSTEM_PROMPT) + count_tokens(TOOLS_SCHEMA)
HISTORY_CEILING = CONTEXT_WINDOW - STATIC_TOKENS - ANSWER_RESERVE
# 128K - 8K - 12K - 16K = 92K

# 每輪呼叫前執行
messages = trim_history_fifo(messages, HISTORY_CEILING)
```

**解決的問題**：防止 context OOM，成本可控，對話不會因 API 報錯而中斷。
**剩下的問題**：FIFO 可能丟失關鍵早期上下文（角色設定、任務目標），對話可能突然「失憶」。工具輸出若未 trim，幾輪後仍快速耗盡 budget。
**複雜度**：1 天實作，token counting 用 `tiktoken` 或模型 API 的 `count_tokens` 端點，零額外 API 成本。
**適用場景**：POC 驗證、單輪 Q&A bot、< 20 輪的短對話場景、對話連貫性要求不高的場景。

---

### Layer 2 — 生產就緒（Production-Ready）

**實作方式**：LangGraph MemorySaver + 週期摘要節點 + Pin 機制保護早期 turns

架構：每 20 輪觸發一次摘要節點，使用輕量模型（Gemini Flash 或 Claude Haiku）壓縮最舊的 N 輪。前 3 輪（通常含角色設定）標記為 pinned，不參與任何截斷。

```
LangGraph 圖結構：

┌──────────┐    ┌──────────────┐    ┌───────────────────┐
│  User    │───▶│  Agent Node  │───▶│  Tool Exec Node   │
│  Input   │    │  (主推理)    │    │  + Output Trimmer │
└──────────┘    └──────┬───────┘    └─────────┬─────────┘
                       │                       │
                       ▼                       │
              ┌────────────────┐               │
              │ should_        │◀──────────────┘
              │ summarize()?   │  每輪結束後檢查
              └───────┬────────┘
                  YES │     NO
                      ▼      ▼
              ┌──────────┐  繼續
              │ Summarize│
              │  Node    │  (Gemini Flash)
              └──────────┘
```

```python
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage

PINNED_TURNS = 3          # 前 N 輪不參與截斷
SUMMARY_EVERY_N = 20      # 每 N 輪觸發摘要
SUMMARY_TARGET_TOKENS = 500

def should_summarize(state: AgentState) -> bool:
    """每 20 輪觸發，或 history token > 70% ceiling"""
    live_messages = state["messages"][PINNED_TURNS * 2:]  # 跳過 pinned turns
    turn_count = len(live_messages) // 2
    history_tokens = count_tokens(live_messages)
    return (turn_count > 0 and turn_count % SUMMARY_EVERY_N == 0) \
        or history_tokens > int(HISTORY_CEILING * 0.70)

async def summarize_node(state: AgentState) -> AgentState:
    pinned = state["messages"][:PINNED_TURNS * 2]      # 永不壓縮
    live = state["messages"][PINNED_TURNS * 2:]         # 可壓縮部分
    oldest = live[:SUMMARY_EVERY_N * 2]                 # 最舊 N 輪
    remaining = live[SUMMARY_EVERY_N * 2:]              # 保留的 live 部分

    summary_prompt = f"""將以下對話壓縮為繁體中文摘要，不超過 {SUMMARY_TARGET_TOKENS} tokens。
保留：使用者目標、角色設定、重要決策、已確認事實、未解決問題。
省略：重複問答、格式說明、中間推理過程、過時的臨時資料。

{format_messages(oldest)}"""

    summary = await gemini_flash.ainvoke(summary_prompt)

    # 驗證摘要 token 數（LLM 輸出長度不穩定）
    summary_tokens = count_tokens(summary.content)
    if summary_tokens > SUMMARY_TARGET_TOKENS * 1.5:
        # 遞迴再壓縮（通常不需要，但要有防護）
        summary = await compress_further(summary.content, SUMMARY_TARGET_TOKENS)

    summary_msg = SystemMessage(
        content=f"[對話摘要 Turn {PINNED_TURNS+1}–{PINNED_TURNS+SUMMARY_EVERY_N}]\n{summary.content}"
    )
    return {"messages": pinned + [summary_msg] + remaining}
```

**新增元件**：Pin 機制、摘要觸發邏輯、輕量摘要模型呼叫、摘要 token 驗證。
**解決的問題**：大幅延長可用對話輪數（理論上無限輪）、保護早期關鍵上下文、維持對話語意連貫性。
**代價**：每次摘要 ~0.5–1 秒額外 latency（異步不阻塞主流程），摘要模型 API 成本（Gemini Flash 輸入 $0.075/1M tokens，20 輪對話 ~16K tokens ≈ $0.0012，成本極低）。
**適用場景**：生產 chatbot、客服系統、法律/醫療助理（需要長期記憶）、10K–200K DAU。

---

### Layer 3 — 企業級（Enterprise-Grade）

**實作方式**：分級 Token 預算 + 成本歸因 + 即時監控 + 配額執法

```
Tenant 分級預算配置（範例）：

┌────────────────┬──────────────────┬──────────────┬────────────┬───────────────┐
│  Tenant Class  │  Context Budget  │ Summary Freq │ Tool Top-N │ 月 Token 配額 │
├────────────────┼──────────────────┼──────────────┼────────────┼───────────────┤
│  Free          │   32K tokens     │  每 10 輪    │    2 筆    │  10M tokens   │
│  Pro           │   92K tokens     │  每 20 輪    │    5 筆    │ 100M tokens   │
│  Enterprise    │  180K tokens     │  每 40 輪    │   10 筆    │   unlimited   │
└────────────────┴──────────────────┴──────────────┴────────────┴───────────────┘
```

**成本歸因追蹤**：

```python
@dataclass
class ContextCostAttribution:
    tenant_id: str
    session_id: str
    turn_id: int
    system_tokens: int          # 靜態，通常可用 prompt cache 降低成本
    tools_tokens: int           # schema 靜態 + 輸出動態
    history_tokens: int         # 主要管理目標
    answer_tokens: int          # 輸出 tokens（成本通常高 3–5 倍）
    total_tokens: int
    summary_invocations: int    # 本次 session 觸發摘要次數
    estimated_cost_usd: float   # (input_tokens × $3/1M) + (output_tokens × $15/1M)
    # Claude Sonnet 4 定價，Enterprise tier 可能有折扣

# 每輪寫入 BigQuery / Cloud Spanner 供帳單稽核
# 可觸發配額告警：月用量 > 80% → 降速；> 100% → 拒絕服務
```

**可觀測性指標**（Prometheus / Cloud Monitoring）：

```
# 即時監控
context_utilization_ratio{tenant_id, session_id}
  = history_tokens / history_ceiling
  # 告警閾值：> 0.80

# 壓縮效率
summary_compression_ratio{tenant_class}
  = tokens_before_summary / tokens_after_summary
  # 健康值：> 10x；< 5x 代表摘要 prompt 需要優化

# 工具成本節省
tool_trim_savings_tokens_total{tool_name}
  = raw_output_tokens - trimmed_output_tokens
  # 追蹤哪些工具最「浪費」context

# 異常事件
context_oom_events_total{tenant_class}
  # 應接近 0；若不為 0，代表 ceiling 設定或監控有問題
  
# 摘要延遲
summary_latency_seconds{p50, p95, p99}
  # p95 應 < 2s；超過代表摘要模型過載
```

**新增元件**：Tenant 配置服務（動態載入，無需重部署）、成本歸因 pipeline（寫入資料倉儲）、即時預算監控 dashboard（Grafana / Looker Studio）、配額執法中間件（超限降速或拒絕）。
**解決的問題**：多租戶公平性（免費用戶不影響付費用戶）、成本可見性（知道每個 session 花多少錢）、合規審計（誰在什麼時間用了多少 token）。
**代價**：額外工程複雜度約 2–3 週，監控基建成本 ~$50–200/月（相對 API 成本微不足道）。
**適用場景**：SaaS 平台、企業內部 AI gateway、200K+ MAU、需要成本分攤的多部門部署。

---

## 四、為什麼選 X 不選 Y

| 決策 | 選擇 X | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件（何時選 Y）|
|------|--------|------------|--------------|-------------------|
| 截斷策略 | 階層式摘要 | 保留語意，對話可無限延伸，13:1 壓縮比 | FIFO：刪掉早期關鍵 turns，對話失憶 | 對話 < 20 輪、角色設定不重要時選 FIFO |
| 摘要模型 | Gemini Flash | 成本 $0.075/1M tokens，延遲 ~300ms | 主模型（Claude Sonnet 4 $3/1M）：摘要成本佔主對話 40 倍 | 摘要品質極為關鍵（法律/醫療）時才考慮主模型 |
| 觸發機制 | 每 N 輪 + Token 閾值 雙觸發 | 兼顧固定節奏與動態保護 | 僅每 N 輪：工具呼叫密集時可能在 N 輪內就 OOM | 對話輪次與 token 消耗高度相關時單觸發即可 |
| 工具輸出 | Whitelist 欄位保留 | 只留推理所需欄位，安全可控 | Blacklist 欄位刪除：新工具欄位容易遺漏，token 膨脹難發現 | 工具輸出結構極不穩定時用 blacklist 作為補充 |
| Pinning 策略 | 前 N 輪固定保護 | 角色設定/任務目標通常在開頭，永不丟失 | 依重要性分數決定：計算複雜，且初始 turns 在早期可能分數不高 | 對話中途才有關鍵設定時改用重要性加權 |
| Budget 配置 | 分級 tenant class | 資源隔離，付費用戶不受免費用戶影響 | 全局統一 budget：免費用戶長對話會耗盡資源池，拖累付費用戶 | 單一租戶系統（內部工具）時無需分級 |

---

## 五、系統效應：導入 Context Management 前後

| 指標 | 導入前（無管理）| 導入後（Layer 2）| 改善幅度 |
|------|--------------|----------------|---------|
| 最大可用對話輪數 | ~115 輪（128K 窗格爆滿）| 理論無限（週期摘要）| ∞ |
| 100 輪對話 token 消耗 | 80,000 tokens | ~28,000 tokens（摘要+trim）| -65% |
| 100 輪對話估算成本 | $0.24（輸入）| $0.084（輸入）| -65% |
| 工具輸出 token 占比 | ~55%（10 次工具呼叫）| ~6%（修剪後）| -90% |
| 對話 OOM 發生率 | ~100 輪後必發 | ~0（有監控+提前觸發）| -100% |
| 摘要觸發延遲（p95） | N/A | ~800ms（Gemini Flash）| 每 20 輪一次，可接受 |
| 對話品質（長對話）| 100 輪後急降（上下文丟失）| 穩定（摘要保留關鍵語意）| 主觀 +40% |

---

## 六、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 把完整工具 JSON 回應放進 context | 單次工具呼叫消耗 2K–10K tokens，10 次工具後 budget 耗盡 | 呼叫後立即 trim：whitelist 欄位、截斷陣列至 top-N、移除 null |
| 純 FIFO 不保護早期 turns | 角色設定、使用者目標被刪除，對話「失憶」，品質崩潰 | 前 3 輪標記為 pinned，永不參與 FIFO 截斷 |
| 沒有 budget 監控，等 API 報錯才知道超限 | 線上 OOM 導致對話中斷，用戶看到錯誤訊息 | 設 80% ceiling 告警，提前觸發摘要，勿等到 100% |
| 摘要節點用跟主模型相同的大模型 | 摘要成本 ≈ 主對話成本，吃掉所有成本節省（40 倍差距）| 摘要用 Gemini Flash / Claude Haiku，成本低 10–40 倍 |
| 忽略 tools schema 的靜態 Token 消耗 | 誤以為 history budget 有 108K，實際被 tools 佔走 12K | 啟動時計算 static overhead，動態調整 history ceiling |
| 對所有 tenant 用相同 context 策略 | 免費用戶消耗企業級 Token 預算，SaaS 平台成本失控 | 依 tenant class 設定差異化 budget、summary frequency、trim 策略 |
| 摘要後不驗證壓縮後 token 數 | LLM 輸出長度不穩定，摘要可能超過目標 500 tokens 的 2–3 倍 | 對摘要結果做 token 計數斷言，超上限時遞迴再壓縮一次 |

---

## 七、與其他核心主題的關聯

- **RAG 架構設計**（本系列 Part 2）：RAG 的 retrieved chunks 是 context 最大的動態消耗來源之一；chunk size 策略（256 vs 512 tokens）與 top-K 設定直接影響 context budget 分配。Context management 的 budget 計算必須為 RAG chunks 預留空間。
- **工具呼叫（Tool Use / Function Calling）**（fde-interview-guide Part 31，ADK 深度解析）：每個工具的 schema 定義消耗靜態 Token（12K for 15 tools），工具回傳結果消耗動態 Token；Tool Output Trimming 是 context management 的必要子策略，兩者緊密耦合。
- **Agent 記憶體架構（Memory Architecture）**（本系列後續 Part）：長期記憶（episodic memory store / vector DB）與短期 context window 的分工——什麼存 Vertex AI Vector Search、什麼留在 context，是 context management 的上游架構決策。若記憶體分層設計正確，context 壓力可大幅降低。
- **成本最佳化（Cost Optimization）**（fde-interview-guide Part 35–38）：Token 預算管理直接等於成本控制。Prompt caching（系統提示快取，Claude / Gemini 均支援）可讓靜態 system prompt 的 Token 成本降低 90%，是 context management 的重要補充策略。

---

## 八、面試一句話（Killer Phrase）

> *「Context management 是 LLM 系統的記憶體排程問題：在固定的 Token 預算內（例如 128K 視窗中，system 8K + tools 12K + reserve 16K，history ceiling 約 92K），決定哪些資訊值得保留。純 FIFO 最簡單但會刪掉關鍵早期上下文，所以生產系統應採用 Pin 機制保護前 3 輪 + 階層式摘要壓縮——每 20 輪用 Gemini Flash 把最舊的 20 輪（約 16K tokens）壓縮到 500 tokens，實現 32:1 壓縮比，讓對話無限延伸而不失憶。工具輸出修剪同樣關鍵：用 whitelist 欄位保留策略把完整 JSON 回應從 2,400 tokens 降至 180 tokens，節省 92%，十次工具呼叫就能省下 22K tokens 的 budget。企業級再加上 tenant 分級預算與 Token 成本歸因，才能在 SaaS 場景下做到公平的多租戶資源管理，避免免費用戶壓垮付費用戶的 context 配額。」*

---

**系列導航**

← 前一篇（本系列第一篇） | [後一篇：RAG 架構設計與向量檢索策略](/posts/fde-interview-core-topic-2-rag-architecture-zh/) →
