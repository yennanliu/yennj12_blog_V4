---
title: "AI 工程從零開始｜Phase 14 Part 2：Agent 規劃系統 — 從目標到行動計畫"
date: 2026-06-21T23:00:00+08:00
draft: false
weight: 29
description: "深入解析 AI Agent 規劃架構：Tree-of-Thought/Plan-and-Execute/MCTS、任務分解策略、規劃失敗診斷與動態重規劃機制"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "Planning", "Tree of Thought", "Task Decomposition", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人讓 Agent 直接呼叫工具，期待 LLM 自己想出下一步。*
> *正確答案是：把規劃與執行分開，先產出可驗證的計畫，再逐步執行並動態修正。*
> *差別不是「能不能完成任務」，而是「失敗時能不能恢復，成功時能不能解釋」。*
> *規劃層是 Agent 系統從玩具走向生產的分水嶺。*

---

**面試情境**：你的 AI Agent 需要完成一個多步驟任務：先查詢資料庫、再呼叫外部 API、最後產出報告。目前用 ReAct 架構，任務完成率只有 62%，主要失敗原因是中途走錯路、無法回頭。你的架構師問你：要如何重新設計規劃層，把完成率提升到 90% 以上？

---

## 一、核心問題：為什麼 Agent 需要明確的規劃層

### 1.1 ReAct 的天花板

ReAct（Reason + Act）是目前最普遍的 Agent 架構。模型每次都先思考（Thought），再行動（Action），再觀察（Observation），循環直到任務完成。

這個架構對簡單任務效果不錯，但在複雜任務上暴露出結構性缺陷：

**問題一：局部最優陷阱**
每一步只看到當前狀態，無法預見三步後的死路。走進死路後，大多數 ReAct 實作只會繼續往前走，而非回頭。

**問題二：無法並行**
ReAct 是嚴格序列執行：Thought → Action → Observation。即使兩個子任務完全獨立，也必須依序完成，浪費延遲。

**問題三：失敗後沒有恢復策略**
工具呼叫失敗時，模型只能靠 prompt 裡的指示決定要不要重試。沒有系統性的回滾（rollback）或替代路徑（fallback path）機制。

**問題四：無法事前驗證**
計畫執行到一半才發現前提條件不成立（例如：所需的 API key 不存在），已經消耗了大量 token 和時間。

### 1.2 規劃層解決什麼

明確的規劃層把「想清楚要做什麼」和「真正去做」分開，帶來四個核心收益：

| 問題 | 規劃層的解法 |
|------|-------------|
| 局部最優 | 先展開搜尋樹，評估多條路徑後再執行最優解 |
| 無法並行 | 計畫產出 DAG，識別可並行的子任務 |
| 無法恢復 | 計畫有版本，失敗後 replan 而非從零開始 |
| 無法事前驗證 | pre-condition 在執行前檢查，不滿足就不執行 |

**關鍵數字**：在 WebArena benchmark 上，純 ReAct 完成率約 14%；加入規劃層（Plan-and-Execute）後可達 26–35%；加入動態重規劃後可達 40–50%。複雜度越高的任務，規劃層的收益越大。

---

## 二、三個演進階段

### ╔══ Phase 1：POC（< 1K 任務/日）══╗

**架構**：ReAct + 單層 Prompt 規劃

```
┌──────────────────────────────────────────────┐
│              使用者輸入                        │
└─────────────────┬────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────┐
│         LLM（ReAct Loop）                    │
│  Thought → Action → Observation → Thought…  │
│  （規劃與執行混在同一個 prompt 裡）            │
└──────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────┐
│         工具集（Tool Calls）                  │
│   Search / Calculator / Browser / API        │
└──────────────────────────────────────────────┘
```

- **新增元件**：LLM + 工具定義
- **成本**：約 $0.02–0.05/任務（GPT-4o mini）
- **解決**：能跑通基本任務
- **未解決**：失敗後無法恢復，複雜任務完成率低（~62%）

---

### ╔══ Phase 2：MVP（1K–50K 任務/日）══╗

**架構**：Plan-and-Execute + 靜態計畫驗證

```
┌────────────────────────────────────────────────────┐
│                   使用者目標                         │
└──────────────────────┬─────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              Planner LLM                             │
│  輸入：目標 + 工具清單 + 約束條件                      │
│  輸出：有序子任務列表（Plan）                          │
│  驗證：pre-condition 靜態檢查                         │
└──────────────────────┬───────────────────────────────┘
                       │  Plan（JSON）
                       ▼
┌──────────────────────────────────────────────────────┐
│              Executor Agent                          │
│  逐步執行子任務，回報 Observation                     │
│  失敗 → 回報 Planner 重新規劃                         │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              工具集 / 外部服務                        │
└──────────────────────────────────────────────────────┘
```

- **新增元件**：獨立 Planner LLM、Plan JSON schema、pre-condition 檢查器
- **成本**：約 $0.08–0.15/任務（多一次 Planner call）
- **解決**：複雜任務完成率升至 ~82%，失敗有 replan 機制
- **未解決**：Planner 仍是線性計畫，無法搜尋替代路徑

---

### ╔══ Phase 3：Scale（50K+ 任務/日）══╗

**架構**：Tree-of-Thought Planner + 動態重規劃 + 並行執行

```
┌─────────────────────────────────────────────────────────────┐
│                        使用者目標                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   ToT Planner                               │
│   展開 3–5 條候選路徑（Beam Search）                          │
│   Evaluator 對每條路徑打分                                    │
│   選出最高分路徑作為執行計畫                                   │
└──────────┬─────────────────┬────────────────────────────────┘
           │  Plan A（主路徑） │  Plan B（備援路徑，快取備用）
           ▼                 ▼
┌────────────────────────────────────────────────────────────┐
│               DAG Executor（並行執行器）                     │
│   識別獨立子任務 → 並行呼叫工具                               │
│   子任務失敗 → 觸發 Replanner（帶 Plan B）                   │
└────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────┐
│     工具集 / 外部服務（並行）                                  │
│  Search × 3   API × 2   DB × 1   Browser × 1              │
└────────────────────────────────────────────────────────────┘
```

- **新增元件**：ToT Planner、Evaluator、DAG Executor、Replanner、Plan 快取
- **成本**：約 $0.20–0.40/任務（Planner 展開多條路徑）
- **解決**：完成率升至 ~91%，並行執行降低 P50 延遲 40–60%
- **未解決**：Planner 成本高，ToT 展開過深時 token 爆炸

---

## 三、Chain-of-Thought vs Tree-of-Thought vs Graph-of-Thought

### 3.1 三種思考結構

```
Chain-of-Thought（線性鏈）
────────────────────────────
Step1 → Step2 → Step3 → Step4 → 答案
優點：簡單，token 少
缺點：走錯就全錯，無法回頭

Tree-of-Thought（搜尋樹）
────────────────────────────
              目標
            /   |   \
          A1   A2   A3     ← 展開 3 條路徑
         / \    |   / \
        B1  B2  B3 B4  B5  ← 每條路徑再展開
        ✓   ✗   ✗  ✓   ✗  ← Evaluator 評分
        選 B1 或 B4 執行

Graph-of-Thought（知識圖）
────────────────────────────
    A ──────────▶ C
    │             │
    ▼             ▼
    B ──────────▶ D ──▶ E（答案）
    │             ▲
    └─────────────┘
    允許循環、跨路徑共享中間結果
    適合：多跳推理、知識蒸餾
```

### 3.2 應用場景對照

| 維度 | CoT | ToT | GoT |
|------|-----|-----|-----|
| 搜尋策略 | 貪婪（greedy） | BFS/DFS/Beam | 圖搜尋 |
| token 消耗 | 1× | 3–10× | 5–20× |
| 失敗恢復 | 無 | 可回溯到父節點 | 可跨路徑共享 |
| 實作複雜度 | 低 | 中 | 高 |
| 適用任務 | 線性推理 | 多步決策 | 複雜知識整合 |
| 生產穩定性 | 高 | 中 | 低（尚在研究階段）|

**建議**：MVP 階段用 ToT with Beam Width=3；Scale 階段視任務複雜度決定是否升級到 GoT。GoT 目前在生產環境的可靠性仍不足，不建議在 2026 年前大規模部署。

---

## 四、Plan-and-Execute 架構：規劃與執行分離

### 4.1 核心流程

```
┌─────────────────────────────────────────────────────────────┐
│  使用者目標：「幫我分析競爭對手 A 的最新財報，產出摘要報告」    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │      Planner          │
                │  輸入：目標 + 工具清單  │
                │  輸出：Plan JSON       │
                └───────────┬───────────┘
                            │
                   ┌────────▼────────┐
                   │  Plan Validator │  ← pre-condition 檢查
                   │  • API key 存在？│
                   │  • 工具可用？    │
                   │  • 步驟邏輯正確？│
                   └────────┬────────┘
                            │  通過 ✓
                ┌───────────▼───────────────────────────────┐
                │           Executor                        │
                │                                           │
                │  Step 1: search_web("A 公司 2025 財報")   │
                │      → Observation: [PDF URL]             │
                │                                           │
                │  Step 2: parse_pdf(url)                   │
                │      → Observation: {revenue, profit…}   │
                │                                           │
                │  Step 3: generate_summary(data)           │
                │      → Observation: 摘要文字              │
                │                                           │
                └───────────────────────────────────────────┘
                            │  所有步驟完成
                            ▼
                   最終輸出給使用者
```

### 4.2 Plan JSON 結構

```json
{
  "goal": "分析競爭對手 A 財報",
  "steps": [
    {
      "id": "step_1",
      "tool": "search_web",
      "args": {"query": "A 公司 2025 年報"},
      "depends_on": [],
      "pre_conditions": ["internet_accessible == true"],
      "post_conditions": ["result.url != null"],
      "retry_limit": 3,
      "fallback": "search_web_backup"
    },
    {
      "id": "step_2",
      "tool": "parse_pdf",
      "args": {"url": "{{step_1.result.url}}"},
      "depends_on": ["step_1"],
      "pre_conditions": ["step_1.status == success"],
      "post_conditions": ["result.revenue != null"]
    }
  ]
}
```

**關鍵設計**：
- `depends_on`：DAG 邊，讓 Executor 識別並行機會
- `pre_conditions`：執行前檢查，失敗則跳過或 replan
- `post_conditions`：執行後驗證，失敗則 retry 或 replan
- `fallback`：備援工具，不需要完整 replan

---

## 五、任務分解：MCTS/BFS/DFS 在 Agent 規劃中的應用

### 5.1 搜尋演算法比較

```
BFS（廣度優先）適合：短路徑最優解
───────────────────────────────────
Level 0:              目標
                    / | \
Level 1:          A   B   C
                 /|   |   |\
Level 2:        D E   F   G H
→ 逐層展開，找最短路徑；適合步驟數 ≤ 5 的任務

DFS（深度優先）適合：快速找到可行解
───────────────────────────────────
目標 → A → D → D1 → D2（失敗）
                   → D3（成功，立刻回傳）
→ 找到第一個可行解就停；適合有明確停止條件的任務

MCTS（蒙地卡羅樹搜尋）適合：不確定性高的長序列
───────────────────────────────────────────────
1. Selection：沿 UCB1 分數選擇子節點
2. Expansion：展開未探索的子節點
3. Simulation：快速 rollout 到終止狀態
4. Backpropagation：更新路徑上所有節點的勝率
→ 適合：步驟數 > 8、工具呼叫成本高、需要探索-利用平衡
```

### 5.2 在 Agent 規劃中的實際應用

| 場景 | 推薦演算法 | 原因 |
|------|-----------|------|
| 程式碼生成（3–5 步） | BFS（Beam=3） | 步驟少，窮舉成本可接受 |
| 網頁導航（10–20 步） | DFS + 剪枝 | 快速找到可用路徑 |
| 研究報告（20+ 步） | MCTS | 高不確定性，需要探索 |
| 資料管線（有向無環） | Topological Sort | 已知依賴關係，不需搜尋 |

**MCTS 的 UCB1 公式**：

```
UCB1(v) = wins(v)/visits(v) + C × √(ln(visits(parent)) / visits(v))

其中 C = 探索常數（通常設 1.4）
wins(v) = 此節點成功完成任務的次數
visits(v) = 此節點被訪問次數
```

在 Agent 規劃中，「wins」定義為子任務成功完成，「rollout」可以用 LLM 快速模擬（比真實執行便宜 10–100×）。

---

## 六、動態重規劃：執行失敗後的恢復策略

### 6.1 失敗分類

| 失敗類型 | 範例 | 恢復策略 |
|---------|------|---------|
| 工具暫時失敗 | API 503 | 指數退避重試（最多 3 次）|
| 工具永久失敗 | API key 無效 | 切換 fallback 工具 |
| 前提條件不成立 | 搜尋結果為空 | 重寫當前步驟的 args |
| 計畫邏輯錯誤 | 步驟順序矛盾 | 觸發完整 replan |
| 目標不可達 | 資料不存在 | 回傳錯誤給使用者 |

### 6.2 Replanner 決策樹

```
子任務失敗
    │
    ├── 重試次數 < 限制？
    │       │
    │       ├── Yes → 指數退避重試（0.5s, 1s, 2s）
    │       │
    │       └── No → 下一步
    │
    ├── 有 fallback 工具？
    │       │
    │       ├── Yes → 切換 fallback，繼續執行
    │       │
    │       └── No → 下一步
    │
    ├── 失敗影響後續步驟？
    │       │
    │       ├── No（獨立步驟）→ 跳過，繼續執行剩餘步驟
    │       │
    │       └── Yes → 觸發 Replanner
    │
    └── Replanner
            │
            ├── 輸入：原始目標 + 已完成步驟 + 失敗原因
            ├── 輸出：修訂後的 Plan（從失敗點往後重寫）
            └── 限制：最多 replan 3 次，超過則回傳失敗
```

### 6.3 Replan Prompt 設計

```
系統：你是一個任務規劃器。

已完成步驟：
- step_1: search_web → 成功，找到 3 篇文章
- step_2: parse_pdf → 失敗，錯誤：PDF 需要密碼

原始計畫的下一步（已無效）：
- step_3: extract_data(pdf_content)

請根據以上情況，重新規劃從 step_3 開始的步驟。
約束：
1. 不要重複已完成的步驟
2. 優先使用備援工具
3. 如果目標無法達成，說明原因

輸出格式：Plan JSON（只包含 step_3 之後的步驟）
```

**關鍵指標**：成功的 Replan 應在 < 2s 完成（使用較小模型），且不應讓 token 消耗翻倍。建議 Planner 用 GPT-4o，Replanner 用 GPT-4o mini。

---

## 七、規劃驗證：Pre-condition/Post-condition 檢查

### 7.1 靜態 Pre-condition（執行前）

```python
class PreconditionChecker:
    def check(self, step: PlanStep, context: AgentContext) -> CheckResult:
        violations = []

        for condition in step.pre_conditions:
            if not self._evaluate(condition, context):
                violations.append(condition)

        if violations:
            return CheckResult(
                passed=False,
                violations=violations,
                action="replan"  # or "skip" or "abort"
            )
        return CheckResult(passed=True)

    def _evaluate(self, condition: str, context: dict) -> bool:
        # 例："step_1.status == success"
        # 例："internet_accessible == true"
        # 例："result.count > 0"
        return eval_condition(condition, context)
```

**常見 Pre-condition 類型**：
- 環境條件：`internet_accessible`, `api_key_valid`
- 前序步驟：`step_N.status == success`
- 資料可用：`context.documents.count > 0`
- 資源限制：`remaining_budget_usd > 0.10`

### 7.2 動態 Post-condition（執行後）

Post-condition 驗證工具呼叫的結果是否符合預期。失敗時觸發重試或 replan：

```
步驟執行完成
      │
      ▼
Post-condition 檢查
      │
      ├── 通過 → 繼續下一步，更新 context
      │
      └── 失敗
            │
            ├── 結果部分有效？（e.g., 找到 2/3 筆資料）
            │     → 繼續，但標記為 partial_success
            │
            ├── 結果完全無效？
            │     → 重試（帶不同參數）
            │
            └── 重試後仍失敗？
                  → 觸發 Replanner
```

**數字**：在生產系統中，Post-condition 檢查平均可攔截 15–20% 的「看似成功但結果錯誤」的工具呼叫（例如：搜尋 API 回傳 200 但結果為空）。

---

## 八、為什麼選 X 不選 Y

### 決策一：Plan-and-Execute vs 純 ReAct

```
選擇              選 Plan-and-Execute 的理由        不選純 ReAct 的理由
────────────────────────────────────────────────────────────────────
Plan-and-Execute  規劃與執行分離，失敗可局部重規劃    ReAct：每步都依賴前步，
                  計畫可事前驗證，節省無效執行成本    失敗後只能從頭來
                  並行執行依賴關係明確的子任務        無法事前檢查 pre-condition

Flip condition：任務 ≤ 3 步、不需要工具呼叫時，ReAct 的 overhead 更低。
```

### 決策二：ToT vs CoT（規劃用）

```
選擇    選 ToT 的理由                      不選 CoT 的理由
────────────────────────────────────────────────────────────
ToT     展開多條路徑，Evaluator 選最優       CoT：線性推進，
        任務越複雜，ToT 優勢越大             走錯方向無法回頭
        失敗路徑可快速剪枝，不需真實執行     token 消耗 1×，但任務完成率低

Flip condition：任務步驟 ≤ 4 步、Planner 成本敏感時，CoT 足夠。
Token 消耗：CoT 1×，ToT（Beam=3）約 3–4×。
```

### 決策三：BFS vs MCTS（搜尋策略）

```
選擇    選 BFS 的理由                         不選 MCTS 的理由
──────────────────────────────────────────────────────────────────
BFS     步驟 ≤ 5 時，BFS 窮舉成本可接受       MCTS：實作複雜，
        找到最短路徑保證最優                   Exploration-exploitation 需調參
        容易實作，除錯容易                     少步驟任務 overhead 大

Flip condition：步驟數 > 8 或工具呼叫成本高（> $0.01/次）時，MCTS 的
探索效率遠優於 BFS 的窮舉。
```

### 決策四：靜態計畫 vs 動態重規劃

```
選擇        選動態重規劃的理由                不選純靜態計畫的理由
────────────────────────────────────────────────────────────────
動態重規劃  真實環境不可預測（API 掛掉、       靜態計畫：計畫一旦失敗就整體
            資料不存在、權限不足）             失敗，需人工介入
            Replan 只重寫失敗點往後的步驟      成功率在複雜任務上低 25–40%
            已完成步驟不需重複執行

Flip condition：任務可冪等重跑（idempotent）且成本極低時，靜態計畫+全部
重跑比動態 replan 更簡單。
```

### 決策五：Planner/Executor 分開的 LLM vs 同一個 LLM

```
選擇        選分開的理由                      不選合一的理由
────────────────────────────────────────────────────────────────
分開        Planner 用大模型（GPT-4o）         合一：單一模型同時規劃與執行，
            Executor 用小模型（GPT-4o mini）   context window 容易爆炸
            Replanner 用小模型快速回應         規劃錯誤和執行錯誤難以區分
            成本分配合理：規劃少、執行多       除錯困難

Flip condition：任務極簡單（< 3 步）或成本極敏感時，合一模型省去
一次 API 呼叫的 overhead（約 50–200ms）。
```

### 決策六：JSON Plan vs 自然語言 Plan

```
選擇        選 JSON Plan 的理由               不選自然語言 Plan 的理由
────────────────────────────────────────────────────────────────
JSON Plan   機器可解析，Executor 不需 LLM     自然語言：Executor 需要 LLM
            depends_on 可自動產生 DAG         解析計畫，增加延遲和成本
            版本化、diff 容易                 DAG 無法自動識別
            Pre/post-condition 可程式化       條件檢查需要 LLM 判斷

Flip condition：Planner 無法穩定輸出合法 JSON（常見於較弱的模型）時，
自然語言計畫搭配寬鬆解析器比嚴格 JSON schema 更穩定。
```

---

## 九、系統效應：ReAct vs Plan-and-Execute 數字比較

以下數字來自 WebArena、ALFWorld、HotpotQA 等公開 benchmark，以及生產環境的實測數據：

### 9.1 任務完成率

| 架構 | 簡單任務（3 步） | 中等任務（5–8 步） | 複雜任務（10+ 步） |
|------|---------------|-----------------|-----------------|
| ReAct | 85% | 62% | 34% |
| Plan-and-Execute（靜態）| 86% | 78% | 61% |
| Plan-and-Execute + Replan | 87% | 85% | 82% |
| ToT + Replan + 並行 | 88% | 91% | 91% |

### 9.2 成本與延遲

| 架構 | Token 消耗（中等任務）| P50 延遲 | P99 延遲 | 成本/任務 |
|------|-------------------|---------|---------|---------|
| ReAct | 3,200 | 8s | 35s | $0.032 |
| Plan-and-Execute | 4,800 | 11s | 28s | $0.048 |
| ToT + 並行執行 | 7,200 | 9s（並行）| 22s | $0.072 |

**核心洞察**：
- P99 延遲：Plan-and-Execute 比 ReAct **低 20%**，因為失敗後的無效嘗試減少
- ToT + 並行：雖然 token 多，但並行執行讓 P50 延遲反而**低於** ReAct
- ROI 分析：Plan-and-Execute 的額外成本（+$0.016/任務）在中等任務上帶來 +23% 完成率，CP 值極高

### 9.3 失敗模式分佈

| 失敗原因 | ReAct | Plan-and-Execute |
|---------|-------|----------------|
| 走入死路無法回頭 | 38% | 5% |
| 工具呼叫失敗後放棄 | 29% | 8% |
| 前提條件不成立（未提前驗證）| 18% | 2% |
| 計畫邏輯錯誤 | N/A | 12% |
| LLM 幻覺導致錯誤工具呼叫 | 15% | 11% |

---

## 十、面試答題要點

> *「我會把問題拆成兩層：為什麼 ReAct 失敗，以及規劃層要怎麼設計。ReAct 的核心問題是規劃與執行耦合在一起，每步只有局部視野，走錯無法回頭。我的解法是引入 Plan-and-Execute 架構：先用 Planner LLM 產出帶 pre/post-condition 的 JSON 計畫，靜態驗證後交給 Executor 執行；任何步驟失敗時，Replanner 只重寫失敗點往後的部分，已完成步驟保留。在 WebArena 上，這個架構把 10 步以上任務的完成率從 34% 提升到 82%，成本只增加 50%。如果要進一步到 90%+，我會在 Planner 層加入 Tree-of-Thought（Beam Width=3）讓 Evaluator 在執行前先篩選最優路徑，並把 DAG 裡的獨立步驟並行執行，P99 延遲反而能比純 ReAct 低 20%。關鍵決策：Planner 用 GPT-4o，Replanner 用 GPT-4o mini，讓成本和速度都最優。」*

**RKK 結構拆解**：
- **R（Requirement）**：任務完成率從 62% 提升到 90%+
- **K（Key Insight）**：規劃與執行分離，失敗後局部 replan 而非重跑
- **K（Key Design）**：JSON Plan + pre/post-condition + DAG 並行 + ToT 多路徑

---

## 十一、系列導航

← [Phase 14 Part 1：Agent 工具呼叫與 Function Calling 設計](/posts/ai-eng-from-scratch-phase14-part1-tool-calling-zh/)

→ [Phase 14 Part 3：Agent 記憶系統 — 短期/長期記憶與 RAG 整合](/posts/ai-eng-from-scratch-phase14-part3-memory-zh/)

---

*本文為「AI 工程從零開始」系列第 Phase 14 Part 2 篇，聚焦 Agent 規劃系統的架構設計與生產實踐。*
