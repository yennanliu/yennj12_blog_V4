---
title: "State Machine & DAG：確定性圖結構與 Agent 反思迴圈收斂"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "解析為何 ReAct 自由迴圈在生產環境中危險，以及如何以有向無環圖（DAG）建構可稽核、可測試的 Agent 行為確定性邊界。涵蓋 LangGraph、ADK 2.0、反思迴圈收斂條件與並行分支狀態隔離。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "LangGraph", "ADK", "StateMachine"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：DAG 是把 Agent 的「下一步由 LLM 在執行期決定」改成「下一步由工程師在編譯期定義」，讓系統的行為空間可靜態分析、可稽核、可成本管控。**

> 大多數人把 Agent 做成 ReAct 迴圈——因為它最快能跑起來；
> 少數人在第一次工具呼叫爆炸後改成有守衛的迴圈；
> 更少人從一開始就把行為編碼成 DAG，把路由邏輯放在 Python 而非 prompt；
> 最少的人能說清楚為什麼這樣做可以把工具呼叫從 12 次壓到 4 次。

**面試情境**：「我們的 AI 文件審核系統上線後，有使用者反映處理速度極慢，有時要等 3–4 分鐘；後來發現有些 run 觸發了 25 次以上的 LLM 呼叫，導致每個 query 成本從預計的 $0.01 飆升至 $0.08。如果請你重新設計這個系統的 Agent 架構，你會怎麼做，以及如何確保這個問題不再發生？」

---

## 一、為什麼面試官問這個

面試官問這個問題，真正在測試的不是你會不會用 LangGraph API，而是你是否理解 **Agent 系統的確定性邊界問題**。當 LLM 自己決定下一步時，系統的行為空間在執行前是無界的——相同輸入在不同推論溫度下可能走不同路徑，工具呼叫次數無法預測，成本預算無從管控。在一個 LLM 呼叫每次耗費數十毫秒和若干 Token 費用的世界裡，這不是學術問題，是直接打中 P&L 的工程問題。

**面試官測試三個層次：**

- **概念層**：你能否清楚說明 ReAct 和 DAG 的本質差異，而不只是說「DAG 有節點有邊」
- **工程層**：你是否知道反思迴圈為何需要雙重收斂條件，以及 State Schema 如何防止跨節點狀態污染
- **量化層**：你能否用具體數字說明影響——工具呼叫次數、Token 成本、收斂延遲

**弱答案的特徵：**「DAG 就是有向無環圖，LangGraph 可以幫你把 Agent 畫成圖。」只描述工具特性，沒說清楚「為什麼要這樣做」和「不這樣做的具體代價」。

**強答案的結構：** 先點出 ReAct 的無界行為空間問題（且量化這個問題）→ 說明 DAG 如何在編譯期固定所有邊，把路由邏輯從 LLM prompt 移到 Python conditional edge → 說明 StateGraph 的 TypedDict schema 如何防止狀態污染 → 最後說明反思迴圈的雙重收斂條件，並給出平均工具呼叫從 12 次降到 4 次的 3× 成本數字。

---

## 二、核心原理與技術深度

### 2.1 ReAct 的結構性問題

ReAct（Reason + Act）模式讓 LLM 在執行期自己選擇下一個動作。從工程角度看，這等於把控制流（Control Flow）的決策權交給了一個機率模型：

```
P(next_action | current_observation, history, temperature)
```

這個機率分布在推論時才確定，沒有任何靜態分析工具能在執行前預測它的輸出空間。後果是多層面的：

**無窮迴圈風險**：LLM 可能反覆呼叫同一個工具，觀察到相同結果，卻因為 prompt 中沒有足夠的終止信號而無法自行跳出。這在生產環境中被觀察到的平均工具呼叫次數是 **12 次/query**，極端案例可達 30+ 次。

**成本不可預期**：DAG 約束後降至 **4 次/query**，成本差距 **3×**。以 gpt-4o-mini 計算，12 次工具呼叫大約消耗 8,000–15,000 input tokens（含每次工具呼叫的 context 累積），費用約 $0.012–0.020；4 次呼叫費用約 $0.004–0.007。在百萬 QPS 規模下，這個差距達到數千美元/天。

**無法單元測試**：相同輸入在不同推論溫度下可能走完全不同的路徑，導致測試覆蓋率形同虛設。

### 2.2 DAG 的確定性保證機制

DAG（Directed Acyclic Graph）把 Agent 的可能行為編碼在**編譯期**（Graph 定義時），所有 Node 和 Edge 在 Graph 物件建立後就固定：

```
┌───────────────────────────────────────────────────────────────────┐
│  Graph 定義期（Compile Time）                                      │
│                                                                   │
│  [fetch_node] ──▶ [evaluate_node] ──▶ {conditional_edge}         │
│                                              │                    │
│                         score > 0.8 ─────────▼────── [approve]   │
│                         score ≤ 0.8 ─────────▼────── [rewrite]   │
│                                                                   │
│  所有可能路徑在 Graph 定義時已知，可靜態分析、可視覺化、可 lint    │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  執行期（Runtime）                                                 │
│                                                                   │
│  State 流入 fetch_node → 純函數執行 → 回傳更新後的 State          │
│  State 流入 evaluate_node → 計算 score → 回傳 {score: 0.91}      │
│  Conditional Edge 讀取 state["score"] → Python lambda 判斷        │
│  路由到 approve_node，無任何 LLM 介入路由決策                      │
└───────────────────────────────────────────────────────────────────┘
```

「無環（Acyclic）」這個約束是最關鍵的：它確保圖一定有終點，不存在結構性無窮迴圈。有向性（Directed）則確保數據流方向固定，不會有雙向依賴導致的狀態不一致。

若業務需要反思迴圈（Reflection），正確做法是用**帶 MAX\_ITERATIONS 守衛的 LoopAgent**，或把反思迴圈封裝成一個 SubGraph（本身是 DAG），而非在主 DAG 內引入回邊（back edge）——回邊讓圖變成有環圖，失去終止保證。

### 2.3 LangGraph 核心原語詳解

**StateGraph 與 TypedDict Schema**

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END

class ReviewState(TypedDict):
    draft: str                          # 當前草稿文字
    score: float                        # 評估分數 0.0–1.0
    iterations: int                     # 已執行迴圈次數
    feedback: Annotated[list[str], operator.add]  # 累積式合併，非覆寫
```

`Annotated[list[str], operator.add]` 這個細節很重要：它告訴 LangGraph 在合併並行分支的結果時，用 `operator.add`（串接）而非直接覆寫。沒有這個 annotation，並行分支如果都寫入 `feedback`，只有最後一個分支的值會保留。

嚴格的 TypedDict 定義防止節點間狀態污染：節點函數的回傳值中出現 schema 未定義的 key，LangGraph 會在執行期拋出 KeyError，而不是默默把這個 key 塞進 state——這是一個刻意的設計選擇，讓 schema 成為節點間的契約。

**Node 是純函數**

```python
def evaluate_node(state: ReviewState) -> dict:
    # 只讀取需要的欄位
    score = call_llm_evaluate(state["draft"])
    # 只回傳要更新的欄位，不修改傳入的 state（immutable update）
    return {
        "score": score,
        "iterations": state["iterations"] + 1
    }
```

純函數（Pure Function）的特性讓節點可以完全獨立於 Graph 進行單元測試：

```python
def test_evaluate_node():
    result = evaluate_node({"draft": "test content", "score": 0.0, "iterations": 0, "feedback": []})
    assert "score" in result
    assert result["iterations"] == 1
```

**Conditional Edge 是路由邏輯的唯一載體**

```python
graph.add_conditional_edges(
    source="evaluate",
    path=lambda state: "approve" if state["score"] > 0.8 else "revise",
    path_map={"approve": "publish_node", "revise": "rewrite_node"}
)
```

路由條件是 Python lambda，不是 LLM prompt。這個設計讓路由行為 100% 可預測、可測試，也讓 `.get_graph().draw_mermaid()` 輸出的 Mermaid 圖能準確反映所有可能路徑——這是 Graph Visualization 作為稽核工具的前提。

### 2.4 反思迴圈收斂的數學與工程

反思迴圈（Rewrite → Evaluate → Rewrite…）的終止性依賴兩個條件：

```
┌──────────┐     ┌──────────┐     ┌──────────────────────────────────┐
│  Rewrite │────▶│ Evaluate │────▶│  Exit Condition Check            │
│  Node    │     │  Node    │     │  score > 0.8  →  END (quality)   │
└──────────┘     └──────────┘     │  iter >= 5    →  END (guard)     │
      ▲                           │  otherwise    →  loop back       │
      └───────────────────────────└──────────────────────────────────┘
```

**信心閾值（Confidence Threshold）**設為 0.8 的工程意涵：這個閾值應該由評估模型的校準曲線決定，而不是隨意選取。如果評估模型傾向給出 0.7–0.9 的分數，閾值設 0.8 意味著大約 50% 的輸入在第一次就通過，30% 需要一次反思，20% 需要兩次以上——這個分布決定平均 Token 消耗量。

**MAX\_ITERATIONS = 5 守衛**的工程意涵：當品質在 3–5 次迭代後仍未達標，通常意味著任務超出了當前 Agent 的能力邊界，繼續執行只是浪費成本。5 次是業界常見的保守值，適合多數文本品質任務；複雜推理任務可設 3 次，因為超過 3 次通常說明問題定義本身有問題。

**ADK 2.0 的原生支援**

```python
from google.adk.agents import LoopAgent, SequentialAgent, ParallelAgent

# 反思迴圈
reflection_loop = LoopAgent(
    name="reflection_loop",
    sub_agents=[rewrite_agent, evaluate_agent],
    max_iterations=5,
    should_continue_condition=lambda ctx: ctx.state["score"] < 0.8
)

# 並行執行多個獨立子任務
parallel_fetch = ParallelAgent(
    name="parallel_fetch",
    sub_agents=[fetch_web_agent, fetch_db_agent, fetch_cache_agent]
)

# 串行 Pipeline
pipeline = SequentialAgent(
    name="pipeline",
    sub_agents=[parallel_fetch, reflection_loop, publish_agent]
)
```

ADK 2.0 把這三種基本 Agent 拓撲（Sequential、Parallel、Loop）作為一等公民提供，對應 DAG 理論中的三種基本模式：鏈（Chain）、並行（Parallel）、有守衛的迴圈（Guarded Loop）。

### 2.5 Checkpoint 的持久化成本

每個 Checkpoint（LangGraph 的狀態快照）序列化整個 StateDict 到持久化儲存。欄位數量和大小直接影響系統開銷：

```
┌──────────────────────────────────────────────────────────┐
│  Checkpoint 序列化成本估算（5 輪反思迴圈）                │
│                                                          │
│  draft（2,000 字中文）：約 6 KB                          │
│  feedback（5 條回饋）：約 2 KB                           │
│  score + iterations：< 100 bytes                        │
│  每個 Checkpoint 總計：約 8–10 KB                        │
│                                                          │
│  Redis 後端讀寫延遲：2–5 ms                              │
│  Postgres 後端讀寫延遲：10–30 ms                        │
│  5 輪迴圈總 Checkpoint 開銷：10–50 ms（相對 LLM 呼叫可忽略）│
└──────────────────────────────────────────────────────────┘
```

Checkpoint 的主要價值不是效能，而是**可恢復性**：中斷的工作流可從任意節點恢復，不需重跑整個 Graph。對於長流程任務（如多步驟文件審核，總耗時 2–5 分鐘），這直接決定了網路抖動或服務重啟的使用者體驗。

### 2.6 Graph 視覺化作為稽核工具

LangGraph 的 `.get_graph().draw_mermaid()` 輸出標準 Mermaid 語法，可直接貼入 GitHub PR 描述或 Confluence 頁面：

```
graph TD
    fetch_node --> evaluate_node
    evaluate_node -->|score > 0.8| publish_node
    evaluate_node -->|score ≤ 0.8| rewrite_node
    rewrite_node --> evaluate_node
    publish_node --> END
```

這個視覺化的工程價值有三層：

**第一層（開發期）**：讓工程師在寫完 Graph 定義後立即確認路由邏輯是否符合預期，而不是等到執行時才發現邊接錯了。

**第二層（Code Review 期）**：把 Graph 圖放進 PR artifact，reviewer 不需要讀 Python code 就能理解控制流變更。如果 CI 在每次 PR 時都輸出 Graph diff，路由邏輯的靜默變更（silent change）就能在 Review 階段被捕捉。

**第三層（合規稽核期）**：在需要解釋「AI 系統做了什麼決定、為什麼」的監管情境下，帶有 Checkpoint 版本的 Graph 圖提供了決策路徑的不可否認證明（non-repudiation）——「這個 run 在第 3 個節點根據 score = 0.73 < 0.8 選擇了 rewrite，而非 approve」。

### 2.7 ReAct vs DAG 的決策矩陣

```
┌───────────────────────────────────────────────────────────────────┐
│                     ReAct vs DAG 決策矩陣                         │
├──────────────────┬────────────────────┬────────────────────────────┤
│  維度            │  ReAct             │  DAG                       │
├──────────────────┼────────────────────┼────────────────────────────┤
│  行為可預測性    │  低（執行期決定）   │  高（編譯期固定）           │
│  工具呼叫次數    │  平均 12 次/query   │  平均 4 次/query            │
│  單元測試覆蓋    │  困難（路徑不固定）  │  容易（路徑可靜態列舉）     │
│  無窮迴圈風險    │  高                │  無（結構保證）             │
│  視覺化稽核      │  無                │  Mermaid 自動生成           │
│  適用任務類型    │  開放探索型         │  流程可事前定義型            │
│  人工中斷介入    │  困難              │  原生支援（Checkpoint）      │
│  並行執行        │  無原生支援        │  ParallelAgent / Send API   │
│  Prompt Injection│  高風險（路由在 LLM）│  低風險（路由在 Python）    │
└──────────────────┴────────────────────┴────────────────────────────┘
```

一句話記憶法：**ReAct 是「LLM 當司機」，DAG 是「LLM 是乘客，工程師定義路線圖」。** 司機模式靈活但不可控；路線圖模式可預測但需要事前規劃。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標**：把現有 ReAct Agent 的核心流程固定成 DAG，消滅無窮迴圈風險，同時讓 Graph 可視覺化。

**加入的組件：**
- `StateGraph` + 嚴格的 TypedDict schema，定義所有節點間共享的狀態欄位
- 手動列舉所有節點與固定邊，包括至少一個 Conditional Edge
- 僅 `MAX_ITERATIONS` 守衛（不設信心閾值，以加快實作速度）
- CI pipeline 執行 `.get_graph().draw_mermaid()`，輸出 Mermaid 圖作為 PR artifact

**刻意省略的組件**：Checkpoint 持久化（無法恢復中斷）、並行分支、信心閾值

**成本/複雜度**：1 人天；無額外基礎設施；工具呼叫從平均 12 次降至 6–8 次（部分節省：路由固定，但節點內 LLM 呼叫次數未優化）

**解決了什麼**：無窮迴圈消失；Graph 可視覺化進 CI；每個節點可獨立單元測試；工具呼叫成本從 $0.015/query 降至 $0.009/query

**留下什麼問題**：中斷後無法恢復，長流程（> 30 秒）失敗需完整重跑，成本浪費；沒有信心閾值，即使品質已達標仍會跑滿 `max_iterations`，多消耗 40–60% Token

---

### Layer 2 — 生產就緒（Production-Ready）

**目標**：支援中斷恢復、並行執行、雙重退出條件，讓系統可以在真實流量下穩定運行。

**新增的組件：**
- **Checkpoint 持久化**：`SqliteSaver`（單機開發）或 `RedisSaver`（生產），每個節點執行後快照狀態到持久化儲存
- **雙重退出條件**：`score > 0.8` OR `iterations >= 5`，品質達標時提前退出，降低平均 Token 消耗
- **並行分支狀態隔離**：`ParallelAgent` 或 LangGraph `Send` API，每個分支收到 state 的副本，用 `Reducer` 合併結果

**並行分支的正確狀態管理：**

```
                        ┌──────────────────────┐
                        │    Dispatcher Node   │
                        └──────────┬───────────┘
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
  │  Branch A    │         │  Branch B    │         │  Branch C    │
  │ state_copy_a │         │ state_copy_b │         │ state_copy_c │
  │ (immutable)  │         │ (immutable)  │         │ (immutable)  │
  └──────┬───────┘         └──────┬───────┘         └──────┬───────┘
         └─────────────────────────┼─────────────────────────┘
                                   ▼
                         ┌──────────────────┐
                         │  Reducer Node    │  ← operator.add 合併 feedback
                         │  merge results   │  ← max() 取最高 score
                         └──────────────────┘
```

每個並行分支收到的是**狀態的不可變副本（immutable copy）**，分支內的修改只存在於該副本中，不影響其他分支。Reducer 決定如何合併各分支的輸出，這是防止 race condition 的架構保證，而非靠執行順序的僥倖。

**錯誤處理節點**：明確的 `error_handler` 節點捕捉工具呼叫失敗，記錄到 `state["errors"]`，然後路由到 `graceful_fallback` 節點，避免整個 Graph 崩潰並讓上游呼叫者收到有意義的錯誤訊息。

**成本/複雜度**：額外 3–5 人天；Redis 或 Postgres 基礎設施月費 $20–100；平均工具呼叫降至 4 次；Checkpoint 延遲增加 5–30 ms/節點

**解決了什麼**：中斷可恢復（99.5% 的失敗案例只需從失敗節點重跑，省下前面所有節點的費用）；並行任務無狀態衝突；品質與成本雙重守衛，平均 Token 消耗比 Layer 1 再省 30–40%

**留下什麼問題**：沒有完整的稽核軌跡（Checkpoint 存在 Redis，不易長期查詢）；Graph 版本沒有管控，Graph 更新後舊 run 的可重現性無保證；沒有成本告警，異常 run 可能在發現前已消耗大量 Token

---

### Layer 3 — 企業級（Enterprise-Grade）

**目標**：完整稽核軌跡、跨服務 Graph 協調、合規可視性，適合需要 SOC 2 Type II 或 ISO 27001 的場景。

**新增的組件：**
- **Checkpoint 版本控管**：每個 Checkpoint 帶 `run_id`（UUID）+ `thread_id` + `graph_version_hash`，儲存在 Cloud Spanner，支援「給我看這個 run_id 在哪個節點做了什麼決定」的時間旅行查詢
- **OpenTelemetry 分散式追蹤**：每個節點執行產生一個 Span，`run_id` 作為 Trace ID 串接到 Cloud Trace，Span attributes 記錄 input/output hash 和 Token 消耗
- **Graph 版本管理**：Graph 定義本身 hash 化（SHA-256）存入 Artifact Registry，確保同一 `run_id` 下的重跑使用相同 Graph 版本，防止「Graph 已更新但舊 run 以新版本重跑」導致的行為不一致
- **Human-in-the-loop 審批閘**：在敏感節點（如 `publish_node`、`send_email_node`）前插入 `human_approval` 節點，Graph 暫停並透過 webhook 等待外部審批；超時（預設 24 小時）自動路由到 `timeout_escalation` 節點
- **成本追蹤與告警**：每個節點執行後把 Token 消耗記錄到 BigQuery，Looker Studio 監控平均 cost/run，單次 run 超過 $0.50 觸發 Cloud Monitoring 告警

**成本/複雜度**：額外 10–15 人天；Cloud Spanner + BigQuery 月費 $200–500；適合每日執行 10 萬次以上且有合規需求的場景

**解決了什麼**：完整的決策軌跡（誰批准、哪個 Graph 版本、每步 Token 成本）；監管審計需求；多版本 Graph 並存（藍綠部署，讓 v1 和 v2 Graph 同時處理流量，按 `graph_version_hash` 追蹤效果差異）；跨團隊 Graph 重用與治理

**三層的關鍵數字對比：**

```
┌────────────────────┬──────────────┬──────────────┬──────────────┐
│  指標              │  Layer 1     │  Layer 2     │  Layer 3     │
├────────────────────┼──────────────┼──────────────┼──────────────┤
│  平均工具呼叫/query │  6–8 次      │  4 次        │  4 次        │
│  中斷恢復能力      │  無          │  節點級      │  節點級+版本  │
│  成本/百萬 query   │  ~$9,000     │  ~$5,000     │  ~$5,200*    │
│  稽核查詢支援      │  無          │  基礎日誌    │  SQL 時間旅行 │
│  部署週期          │  1 人天      │  1 週        │  1 個月       │
└────────────────────┴──────────────┴──────────────┴──────────────┘
* Layer 3 成本略高於 Layer 2 因為 Spanner + BigQuery 儲存成本，
  但比 Layer 1 仍節省 42%
```

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| DAG 內引入回邊（back edge）做反思迴圈 | 圖變成有環圖（Cyclic Graph），失去終止保證，等同於回到 ReAct 的無界問題 | 用 `LoopAgent` 或把反思迴圈封裝為帶守衛的 SubGraph，SubGraph 本身仍是 DAG |
| 並行分支直接共享同一個 state dict 物件 | Race condition：Branch A 和 B 同時寫 `state["result"]`，後寫者覆蓋前者，且問題只在高並發下出現，極難復現 | 傳入 state 的深層副本（deep copy），用帶 `operator.add` annotation 的 Reducer 合併 |
| TypedDict schema 使用 `dict` 或 `Any` 欄位 | 節點可任意附加 key，狀態污染跨越 Graph 邊界；後續節點依賴某個 key 但無法靜態保證該 key 存在 | 所有欄位使用具體類型；動態 key 用 `Annotated[dict, operator.or_]` 並明確定義合併語意 |
| 只設 `MAX_ITERATIONS` 不設信心閾值 | 品質已達標卻繼續執行，每次反思消耗 1,000–3,000 tokens，5 輪滿跑多消耗 4× tokens | 雙重退出：`score > threshold OR iter >= max`，任一觸發即退出 |
| Conditional Edge 內用 LLM 做路由判斷 | 路由本身引入不確定性，DAG 的確定性優勢消失；且路由 LLM 的失敗沒有 retry 機制 | Conditional Edge 只用純 Python 邏輯（比較數值、檢查 flag），LLM 只在 Node 內執行 |
| 沒有 Checkpoint，長流程在中間節點失敗 | 整個 Graph 從頭重跑，重複支付前面節點的 LLM 費用；對使用者意味著 2–5 分鐘等待歸零 | Layer 2 起就加 `SqliteSaver`（本地）或 `RedisSaver`（生產）；關鍵節點前強制 Checkpoint |
| `.get_graph().draw_mermaid()` 只在本地偶爾執行 | Graph 結構變更無法被 PR review 捕捉，路由邏輯悄悄改變；新加入的工程師無法理解系統行為 | 在 CI pipeline 執行 Graph 視覺化，輸出 Mermaid 圖作為 PR artifact，diff 可見 |

### 陷阱診斷鏈：從症狀到根因

面試官有時會給你一個症狀描述，要求你推導根因。以下是三個常見症狀的診斷鏈：

**症狀 A**：「監控顯示某些 run 的 LLM 呼叫次數達到 40–50 次，但大多數 run 只有 4–6 次。」

```
症狀：工具呼叫次數長尾異常
  → 懷疑：反思迴圈沒有收斂條件，或 MAX_ITERATIONS 沒有被正確觸發
  → 診斷：查 Trace，確認每次迴圈的 score 值趨勢
  → 如果 score 沒有上升：評估模型本身可能有問題（評估 prompt 不穩定）
  → 如果 score 在 0.79–0.81 之間震盪：閾值設在分布密集區，改用 0.75 或加 hysteresis
  → 根因：缺乏 MAX_ITERATIONS 守衛，或閾值設在評估模型的不確定性邊界
```

**症狀 B**：「並行執行三個 fetch 子任務後，final state 裡的 results 只有最後一個子任務的數據。」

```
症狀：並行分支結果被覆蓋
  → 懷疑：Reducer 未正確設定，三個分支都寫入同一個 key
  → 診斷：確認 StateDict 的 results 欄位是否有 Annotated + operator 設定
  → 根因：直接用裸 dict，沒有設 Annotated[list, operator.add]，後寫者覆蓋前者
  → 修復：改用 Annotated[list[dict], operator.add] 讓三個分支的結果被累積
```

**症狀 C**：「Graph 在生產環境的行為和測試環境不一樣，但代碼沒有改動。」

```
症狀：相同 Graph 定義，執行結果不同
  → 懷疑：Conditional Edge 內有 LLM 呼叫（路由本身有隨機性）
  → 或懷疑：Node 內的 LLM 呼叫 temperature 在兩個環境不同
  → 診斷：把所有 Conditional Edge 的邏輯列出，確認是否有 LLM 呼叫
  → 根因：Conditional Edge 用了 LLM 做路由判斷，DAG 的確定性被破壞
```

---

## 五、為什麼選 X 不選 Y

面試官往往用「你會怎麼選」來判斷候選人是否真的在生產環境做過決策，而不是只看過文件。以下是 State Machine & DAG 領域最常見的技術選型對比。

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Y 成為正確選擇的翻轉條件 |
|------|------------|--------------|------------------------|
| **DAG** vs ReAct 自由迴圈 | 行為空間可靜態分析；工具呼叫 3× 更少；路由可單元測試 | ReAct 靈活性高，適合探索性任務 | 任務的解法路徑事前完全無法預知（真正的 open-ended 探索），且有嚴格的成本上限寬限 |
| **LangGraph** vs 自建 State Machine | 原生 Checkpoint（可恢復）；draw\_mermaid 視覺化；社群活躍 | 自建可完全控制實作細節，無框架依賴 | 既有系統已有成熟的 workflow engine（如 Temporal、Prefect），引入 LangGraph 是第三個框架 |
| **TypedDict** vs 裸 dict | 靜態分析工具（mypy）可在 CI 捕捉 key 錯誤；欄位作為節點間的契約 | dict 更靈活，無需提前定義所有欄位 | 原型期快速迭代，欄位結構每天都在變，TypedDict 維護成本大於收益 |
| **Redis Checkpoint** vs Postgres Checkpoint | 讀寫延遲 2–5 ms，適合高頻短流程 | Postgres 提供 ACID 保證，長期儲存更可靠 | 流程總耗時 > 1 分鐘，或需要 SQL 查詢歷史 Checkpoint（如「上週所有 score < 0.5 的 run」） |
| **雙重退出條件** vs 只用 MAX\_ITERATIONS | 品質達標時提前退出，平均省 40–60% Token；避免強制發布低品質結果 | MAX\_ITERATIONS 更簡單，沒有閾值校準問題 | 評估模型本身不可靠（分數分布偏移嚴重），信心閾值反而引入假陽性，此時只用迭代守衛更穩定 |
| **Reducer 合併** vs 直接 merge 並行分支 state | 每個合併邏輯顯式定義；`operator.add` vs `operator.or_` 語意清楚 | 直接 merge 程式碼更短 | 並行分支只有一個，不存在合併衝突問題，Reducer 是過度設計 |

**關鍵翻轉洞察**：DAG 在「行為路徑可事前定義」的假設下成立。當任務的解法空間真的是開放的（如科學假設生成、創意發散），強行套 DAG 會把合理的探索路徑截斷。面試官問這個問題時，如果你能主動說出「DAG 的適用邊界」，比只說 DAG 好的候選人更有說服力。

**一句話記憶各選型的核心理由：**
- DAG vs ReAct：「我需要在上線前知道所有可能路徑」→ DAG；「我接受執行期驚喜」→ ReAct
- TypedDict vs dict：「我需要 CI 在 merge 前就捕捉錯誤」→ TypedDict；「我需要快速原型」→ dict
- Redis vs Postgres Checkpoint：「流程快但要高可用」→ Redis；「流程慢且需要長期稽核」→ Postgres
- 雙重退出 vs 單一守衛：「評估模型可靠，想提前結束」→ 雙重退出；「評估模型不穩定」→ 只用迭代守衛

---

## 六、與其他核心主題的關聯（系列連結）

**RAG Pipeline（fde-interview-guide-part1）**：RAG 的 Retrieve → Rerank → Generate 三步是 DAG 的最簡形式，三個固定節點、兩條固定邊，適合用來解釋 DAG 的入門案例。進階版的 Corrective RAG（CRAG）在 Evaluate 後加 Conditional Edge，判斷是否需要 Web Search 補充——這是把反思迴圈思維引入 RAG 的典型案例。面試時可以用「我們先把 RAG 做成 DAG，然後根據評估分數決定是否進入反思迴圈」這個結構來展開。

**Agent Debugging（fde-interview-guide-part11）**：DAG 的 Checkpoint 和 OpenTelemetry Span 是 Agent debug 的物質基礎。沒有確定性 Graph，Trace 就無法對應到固定節點，同一個問題在不同執行下走不同路徑，debug 效率下降 3–5×。DAG 讓「重放某個失敗的 run」成為可能：載入特定 `thread_id` 的 Checkpoint，從失敗節點重新執行，而不是從頭重跑整個流程。這在每次重跑成本 $0.03–0.10 的場景下是顯著節省。

**Context Management（fde-interview-guide-part10）**：State schema 的設計直接決定哪些 context 在節點間傳遞、哪些被截斷。DAG 架構強迫工程師在 schema 定義時思考 context 邊界——每個欄位代表一個 context 決策，而非在 prompt 裡隱性累積所有歷史。`feedback: Annotated[list[str], operator.add]` 這個欄位定義同時回答了「歷史回饋要保留多少」的問題。

**Prompt Injection（fde-interview-guide-part13）**：DAG 把路由邏輯從 LLM prompt 移到 Python conditional edge，消除了「攻擊者透過 prompt 操控 Agent 走到非預期分支」這整類攻擊面。攻擊者可以污染 Node 內的 LLM 輸出，但無法改變 Graph 的邊定義——這是架構層的防禦，比 prompt-level 的防禦更難繞過。具體來說：即使 `evaluate_node` 被注入讓其輸出 `score = 1.0`，conditional edge 的邏輯（`score > 0.8` → approve）仍然按照工程師定義的方式運作，無法被繞過到非預期的節點。

**Multi-Agent 協調（fde-interview-guide-part31 ADK 章節）**：單一 Agent 的 DAG 是這個系列的基礎；Multi-Agent 系統是把多個 DAG 組合成更大的 Graph，每個 Sub-Agent 本身是一個封裝好的 DAG。ADK 的 `SequentialAgent`、`ParallelAgent`、`LoopAgent` 的組合等同於用 DAG 原語拼裝出任意拓撲的 Multi-Agent 系統。

---

## 七、面試一句話（Killer Phrase）

> *「ReAct 把控制流的決策權交給 LLM，在推論時才確定下一步，讓系統的行為空間在編譯期無法靜態分析，這是成本失控和無窮迴圈的根本原因——在生產環境中我們觀察到 unconstrained ReAct 平均每個 query 觸發 12 次工具呼叫。DAG 把所有 Node 和 Edge 固定在 Graph 定義期，把路由邏輯從 LLM prompt 移到 Python conditional edge，讓每條可能路徑在上線前都可視覺化和單元測試，平均工具呼叫降到 4 次，3× 的成本差距在大規模下直接打中 P&L。反思迴圈需要雙重收斂條件：信心閾值（score > 0.8）讓品質達標時提前退出，MAX_ITERATIONS = 5 守衛確保即使品質未達標也有硬性終點。並行分支的核心陷阱是共享可變狀態導致的 race condition，正確做法是傳入 state 的不可變副本、用 Reducer 合併輸出，這是架構保證而非靠執行順序的僥倖。」*

---

---

**FDE Interview Core Topics 系列**：本系列共 25 篇，每篇聚焦一個面試高頻核心概念，以「核心定義 → 技術深度 → 三個實作層次 → 陷阱診斷 → 選型對比 → 面試一句話」的結構幫助你在 30–60 秒內展示工程判斷力。本篇是 Part 3，涵蓋 State Machine & DAG 的所有面試必考面向。

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-2-rag-retrieval-zh/) | [後一篇](/posts/fde-interview-core-topic-4-multi-agent-orchestration-zh/) →
