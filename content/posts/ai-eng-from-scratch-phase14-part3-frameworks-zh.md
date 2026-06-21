---
title: "AI 工程從零開始｜Phase 14 Part 3：Agent 框架全景 — AutoGen、CrewAI 與自建的取捨"
date: 2026-06-21T23:30:00+08:00
draft: false
weight: 30
description: "深入比較主流 Agent 框架：AutoGen/CrewAI/LangGraph/Semantic Kernel 的架構差異、適用場景與生產成熟度，以及何時應該自建框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "AutoGen", "CrewAI", "LangGraph", "Framework", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> 大多數工程師的選擇：「先裝一個框架，之後再說。」
> 有經驗的工程師的選擇：「先定義 Agent 的交互模式，再選能支撐它的框架。」
> 框架給你速度，但也給你它的限制；抽象層降低入門門檻，但隱藏了你最需要控制的細節。
> 正確的問題不是「哪個框架最好」，而是「這個框架的抽象層，跟我的問題邊界對不對齊」。

---

## 面試情境

> 你的團隊正在構建一個客服自動化系統，需要協調「意圖分類 Agent」、「知識庫查詢 Agent」、「回應生成 Agent」與「品質審核 Agent」四個角色。面試官問：「你會選 AutoGen、CrewAI 還是 LangGraph？為什麼？如果規模到每日 50 萬次對話，架構需要如何演進？」

---

## 一、核心問題：框架選型的本質是什麼

Agent 框架的選型問題，表面上是技術選擇，本質上是**控制權與抽象層的交換**。

每個框架都做了一組隱性決策：
- **執行模型**：對話驅動 vs. 圖驅動 vs. 任務佇列驅動
- **狀態管理**：記憶體內 vs. 持久化 vs. 外部化
- **Agent 通訊**：廣播 vs. 點對點 vs. 中介者模式
- **錯誤恢復**：重試策略、fallback 路徑、人工介入點

選錯框架的代價不是「換框架」這麼簡單。當你的 Agent 邏輯與框架的執行模型深度耦合後，重構成本等同於重寫。

### 框架的三個本質問題

```
問題 1：誰決定下一步由誰執行？
  ├── 框架決定 → 高度結構化，靈活性低
  ├── LLM 決定 → 靈活但不可預測
  └── 工程師的程式碼決定 → 可控但需要更多開發工作

問題 2：狀態存在哪裡？
  ├── 對話歷史 (messages list) → 簡單，但 token 成本高
  ├── 結構化狀態物件 → 可查詢，但需要 schema 設計
  └── 外部資料庫 → 持久化，但增加延遲

問題 3：出錯時怎麼辦？
  ├── 讓 LLM 自己決定 → 彈性，但不可靠
  ├── 框架的重試機制 → 簡單，但缺乏語意
  └── 工程師的顯式錯誤處理 → 精確，但需要更多程式碼
```

理解這三個問題的答案，才能判斷一個框架是否適合你的用例。

---

## 二、三個演進階段

### Phase 1（POC / < 5K 日對話）

**目標**：快速驗證 Agent 協作邏輯是否有價值。

```
┌─────────────────────────────────────────────┐
│  Phase 1：單機、記憶體內、框架直接使用       │
│                                             │
│  ┌──────────┐    ┌──────────┐               │
│  │  Agent A │───▶│  Agent B │               │
│  │ (研究)   │    │  (撰寫)  │               │
│  └──────────┘    └──────────┘               │
│        │                │                   │
│        └────────┬────────┘                  │
│                 ▼                            │
│         ┌──────────────┐                    │
│         │  In-Memory   │                    │
│         │    State     │                    │
│         └──────────────┘                    │
│                                             │
│  框架：CrewAI 或 AutoGen (預設配置)          │
│  部署：單一 Python 程序                      │
│  監控：stdout log                            │
└─────────────────────────────────────────────┘
```

**新增元件**：框架本身 + LLM API 呼叫
**成本**：開發 3–5 天，運算成本 ~$50/月
**解決的問題**：驗證 Agent 協作流程是否合理
**尚未解決**：無持久化、無可觀測性、無水平擴展

---

### Phase 2（MVP / 5K–50K 日對話）

**目標**：生產可用，能讓真實使用者使用，工程師不需要 24 小時盯著。

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 2：引入持久化狀態與可觀測性                            │
│                                                              │
│  ┌─────────┐    ┌──────────────────────────────────────┐    │
│  │  API    │───▶│  Agent Orchestrator                  │    │
│  │ Gateway │    │  ┌─────────┐  ┌─────────┐            │    │
│  └─────────┘    │  │Agent A  │  │Agent B  │            │    │
│                 │  └────┬────┘  └────┬────┘            │    │
│                 │       └─────┬──────┘                  │    │
│                 │             ▼                          │    │
│                 │      ┌────────────┐                   │    │
│                 │      │  Workflow  │                   │    │
│                 │      │   State   │                   │    │
│                 │      └─────┬──────┘                   │    │
│                 └────────────┼────────────────────────── ┘   │
│                              ▼                               │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────┐   │
│  │  Redis      │   │  PostgreSQL     │   │  LangSmith / │   │
│  │  (session)  │   │  (audit log)    │   │  Langfuse    │   │
│  └─────────────┘   └─────────────────┘   └──────────────┘   │
│                                                              │
│  框架：LangGraph (checkpointer) 或 AutoGen + 外部狀態         │
└──────────────────────────────────────────────────────────────┘
```

**新增元件**：Redis session、PostgreSQL audit log、追蹤工具
**成本**：開發 3–4 週，運算成本 ~$500/月
**解決的問題**：對話持久化、失敗可重試、有 trace 可查
**尚未解決**：無自動擴展、冷啟動延遲高、框架升級有破壞性變更風險

---

### Phase 3（Scale / 50K–500K+ 日對話）

**目標**：自動擴展、成本優化、框架的限制開始成為瓶頸。

```
┌────────────────────────────────────────────────────────────────┐
│  Phase 3：微服務化 Agent + 事件驅動協調                         │
│                                                                │
│  ┌──────────┐    ┌──────────────────────────────────────────┐  │
│  │  Load    │    │  Agent Service Pool                      │  │
│  │ Balancer │───▶│  ┌──────────┐  ┌──────────┐             │  │
│  └──────────┘    │  │Intent    │  │Knowledge │             │  │
│                  │  │Classifier│  │Retriever │  ...        │  │
│                  │  └──────────┘  └──────────┘             │  │
│                  └──────────────────────────────────────────┘  │
│                              │                                 │
│                              ▼                                 │
│  ┌────────────┐   ┌──────────────────┐   ┌────────────────┐   │
│  │  Message   │   │  Workflow Engine  │   │  Vector Store  │   │
│  │   Queue    │◀──│  (自建或精簡版)   │──▶│  (RAG memory)  │   │
│  │  (Kafka/   │   │                  │   │                │   │
│  │   Redis)   │   └──────────────────┘   └────────────────┘   │
│  └────────────┘              │                                 │
│                              ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Observability Stack                                    │   │
│  │  Traces (OpenTelemetry) + Metrics (Prometheus) +        │   │
│  │  Logs (structured JSON) + Cost tracking (per-agent)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  框架：自建薄協調層 或 LangGraph Server + 自定義 executor        │
└────────────────────────────────────────────────────────────────┘
```

**新增元件**：Message Queue、獨立 Agent Service、OpenTelemetry
**成本**：開發 2–3 個月，運算成本 $3K–$15K/月（依流量）
**解決的問題**：水平擴展、Agent 獨立部署、細粒度成本追蹤
**尚未解決**：框架升級與自建邏輯的長期維護張力

---

## 三、AutoGen：對話式多 Agent 的工程哲學

AutoGen（Microsoft Research）的核心哲學：**把 Agent 協作建模成對話**。每個 Agent 是對話參與者，協作透過訊息傳遞完成，沒有顯式的「工作流程圖」。

### 核心架構

```
┌─────────────────────────────────────────────────────────┐
│  AutoGen 對話模型                                        │
│                                                         │
│  UserProxyAgent          AssistantAgent                 │
│  ┌──────────────┐        ┌──────────────────────────┐   │
│  │ 代表人類使用 │        │ 實際執行 LLM 推理          │   │
│  │ 者的代理人   │◀──────▶│ + 工具呼叫               │   │
│  │              │        │ + 程式碼執行              │   │
│  │ 可執行程式碼 │        │                          │   │
│  │ 可代為確認   │        └──────────────────────────┘   │
│  └──────────────┘                                       │
│          │                                              │
│          ▼  (群組對話)                                  │
│  ┌────────────────────────────────────────────────┐     │
│  │  GroupChat                                     │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │     │
│  │  │ Agent A  │  │ Agent B  │  │ Agent C  │     │     │
│  │  └──────────┘  └──────────┘  └──────────┘     │     │
│  │         ▲              │                       │     │
│  │         │    GroupChat │                       │     │
│  │         │    Manager   │                       │     │
│  │         └──────────────┘                       │     │
│  │    (由 LLM 決定下一個發言者)                    │     │
│  └────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### AutoGen 的優勢場景

- **研究型任務**：需要多輪反覆辯論才能得出答案（論文分析、程式碼除錯）
- **程式碼執行循環**：AssistantAgent 寫程式碼 → UserProxyAgent 執行 → 錯誤回傳 → 修正
- **快速原型**：20 行程式碼就能跑起 2 個 Agent 的對話

### AutoGen 的工程限制

- **狀態不透明**：狀態藏在 messages list 裡，難以查詢特定欄位
- **流量控制困難**：對話輪數由 LLM 決定，難以預測 token 用量
- **生產部署複雜**：AutoGen 0.4（AgentChat）架構重寫，0.2 升 0.4 需大量重構
- **延遲數字**：每次工具呼叫 +150–400ms overhead（HTTP to executor）；GroupChat 中每輪需一次 LLM 呼叫決定下一個 speaker，增加 ~800ms–2s

**適用規模**：POC 到 MVP 早期。日對話超過 20K 後，GroupChat 的不可預測性開始造成 P99 延遲爆炸。

---

## 四、CrewAI：角色扮演協作的工程實現

CrewAI 的核心哲學：**把 Agent 協作建模成組織**。有明確角色（Role）、目標（Goal）、背景（Backstory）的 Agent，像公司員工一樣被分配任務。

### 核心設計模式

```python
# CrewAI 的典型程式碼結構（概念示意）

researcher = Agent(
    role="資深研究員",
    goal="收集競爭對手的技術架構資訊",
    backstory="你是有 10 年經驗的技術情報分析師",
    tools=[search_tool, scrape_tool],
    verbose=True
)

writer = Agent(
    role="技術文件撰寫者",
    goal="將研究結果轉成清晰的技術報告",
    backstory="你擅長將複雜技術概念轉為可執行的洞察",
    tools=[file_write_tool]
)

task1 = Task(
    description="分析 {competitor} 的 API 設計模式",
    agent=researcher,
    expected_output="結構化的技術分析報告"
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[task1, task2],
    process=Process.sequential  # 或 hierarchical
)
```

### CrewAI 的優勢場景

- **內容生成流水線**：研究 → 撰寫 → 審核的線性流程
- **結構清晰的分工**：角色定義讓非工程師也能理解 Agent 在做什麼
- **快速 Demo**：角色描述比圖節點更直觀，stakeholder presentation 效果好

### CrewAI 的工程限制

- **動態路由困難**：Process.sequential 和 Process.hierarchical 以外的流程需要繞路實現
- **錯誤處理薄弱**：Task 失敗的 fallback 邏輯需要自己包裝
- **生產監控不足**：內建可觀測性較弱，需要外掛 LangSmith 或 Langfuse
- **記憶體管理**：長對話的 context window 管理需要手動處理

**適用規模**：MVP 中期。流程固定、分工明確的批次任務表現優異；需要動態分支的即時對話系統則捉襟見肘。

---

## 五、LangGraph：有狀態圖執行的生產級設計

LangGraph 的核心哲學：**把 Agent 執行流程建模成有向圖（DAG/循環圖），狀態是一等公民**。

### 核心架構

```
┌──────────────────────────────────────────────────────────┐
│  LangGraph 圖執行模型                                     │
│                                                          │
│  State Schema（TypedDict）                               │
│  ┌─────────────────────────────────┐                     │
│  │  messages: List[BaseMessage]    │                     │
│  │  intent: str                    │                     │
│  │  retrieved_docs: List[str]      │                     │
│  │  draft_response: str            │                     │
│  │  quality_score: float           │                     │
│  └──────────────┬──────────────────┘                     │
│                 │                                        │
│                 ▼                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐   │
│  │  intent_ │─▶│retriever │─▶│generator │─▶│quality │   │
│  │classifier│  │  _node   │  │  _node   │  │_checker│   │
│  └──────────┘  └──────────┘  └──────────┘  └───┬────┘   │
│                                                 │        │
│                    ┌────────────────────────────┘        │
│                    │  條件邊 (conditional edge)            │
│                    ▼                                      │
│            quality_score < 0.8?                          │
│            ┌──────┴──────┐                               │
│           Yes             No                             │
│            │               │                             │
│            ▼               ▼                             │
│       generator_node    END                              │
│       (重新生成)                                          │
│                                                          │
│  Checkpointer：                                           │
│  SQLite（開發）→ PostgreSQL（生產）→ Redis（高頻）          │
└──────────────────────────────────────────────────────────┘
```

### LangGraph 的生產級特性

**1. Checkpointing（斷點續傳）**
```python
# 每個節點執行後自動儲存狀態
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(DB_URL)
graph = workflow.compile(checkpointer=checkpointer)

# 任何節點失敗都可以從上一個 checkpoint 重新執行
result = graph.invoke(input, config={"configurable": {"thread_id": "user-123"}})
```

**2. Human-in-the-loop**
LangGraph 原生支援在任意節點暫停，等待人工確認後繼續執行。這是 AutoGen 和 CrewAI 都難以優雅實現的功能。

**3. 流式輸出**
逐 token 串流 + 節點執行事件串流，讓前端可以顯示即時進度。

### LangGraph 的工程限制

- **學習曲線陡峭**：TypedDict state + graph 語法 + conditional edges 需要 1–2 週才能熟練
- **圖的調試困難**：循環圖的執行路徑不直觀，需要搭配 LangSmith 才能有效調試
- **LangChain 耦合**：雖然可以獨立使用，但許多工具假設你在 LangChain 生態

**適用規模**：MVP 後期到 Scale。需要持久化狀態、人工介入點、複雜分支邏輯的系統，LangGraph 是目前生產成熟度最高的選擇。

---

## 六、Semantic Kernel：企業整合的 Microsoft 路線

Semantic Kernel（SK）的核心哲學：**把 AI 能力以「插件（Plugin）」形式整合進現有企業系統**，而非建立獨立的 AI 系統。

### 適用場景

- 已有大量 .NET / C# 程式碼庫，需要整合 LLM
- 企業 Azure 環境，使用 Azure OpenAI Service
- 需要嚴格的安全審計與 RBAC 整合
- 已使用 Microsoft 365 / Teams，需要 Copilot 式整合

### SK 的工程特性

- **跨語言**：Python、C#、Java SDK 均有支援
- **Planner**：自動把使用者目標分解成 Plugin 呼叫序列
- **Memory**：內建向量記憶體抽象，接 Azure Cognitive Search 等企業級後端
- **成熟度**：Azure 生態整合最佳，但社群活躍度遠低於 LangChain/LangGraph

**適用規模**：企業 IT 系統整合。如果你的團隊不在 Microsoft 技術棧，遷移成本高，不建議採用。

---

## 七、自建框架：何時抽象層成為負擔

自建框架不是「更好」，而是「框架的抽象層已經成為你前進的障礙」。

### 自建的觸發條件

```
觸發條件 1：效能瓶頸
  症狀：框架 overhead 佔總延遲 > 30%
  數字：LangGraph 節點切換 overhead ~20–50ms/node
        AutoGen GroupChat speaker selection ~800ms–2s/turn
  決策點：當你有 < 10 個節點的確定性工作流程，自建更快

觸發條件 2：可觀測性需求
  症狀：框架的 trace 格式不符合你的監控堆疊
  決策點：需要 per-agent 成本追蹤、自定義 span 屬性

觸發條件 3：升級風險
  症狀：AutoGen 0.2 → 0.4 破壞性重構
        LangChain 頻繁的 API 變更
  決策點：框架升級的測試成本 > 維護自建程式碼的成本

觸發條件 4：特殊執行模型
  症狀：需要真正的並行 Agent（非偽並行）
        需要分散式 Agent 跨機器協作
  決策點：框架的執行模型根本上不符合你的需求
```

### 自建框架的最小核心

```python
# 自建框架的核心只需要三個東西

# 1. 狀態容器
@dataclass
class WorkflowState:
    session_id: str
    messages: list
    metadata: dict
    created_at: datetime
    updated_at: datetime

# 2. Agent 介面
class BaseAgent(ABC):
    @abstractmethod
    async def run(self, state: WorkflowState) -> WorkflowState:
        pass

# 3. 協調器
class Orchestrator:
    def __init__(self, agents: dict[str, BaseAgent], router: Callable):
        self.agents = agents
        self.router = router  # 你的業務邏輯決定下一步

    async def run(self, initial_state: WorkflowState) -> WorkflowState:
        state = initial_state
        while (next_agent := self.router(state)) is not None:
            state = await self.agents[next_agent].run(state)
            await self.save_checkpoint(state)  # 自己實現
        return state
```

這 ~30 行程式碼比任何框架都更容易加入你的 tracing、cost tracking、retry 邏輯。

**代價**：你需要自己維護、自己寫測試、自己處理邊緣情況。在團隊規模 < 5 人且 Agent 邏輯簡單時，這通常不值得。

---

## 八、為什麼選 X 不選 Y

### 決策 1：AutoGen vs. CrewAI

```
選擇          選 AutoGen 的理由              選 CrewAI 的理由
──────────────────────────────────────────────────────────────
互動模式      對話式、反覆辯論型任務         角色分工明確的批次任務
程式碼執行    原生支援 code execution loop   需要自行整合
可讀性        訊息串流，調試直觀             角色定義，stakeholder 易讀
生產成熟度    0.4 架構重寫，需謹慎升級       相對穩定但功能較少
學習曲線      中等（對話模型直觀）           低（角色隱喻易懂）
```

**Flip condition**：
- 選 AutoGen 當：任務需要多輪程式碼執行與修正循環
- 選 CrewAI 當：流程是線性的，且需要非技術人員理解 Agent 分工

---

### 決策 2：LangGraph vs. AutoGen

```
選擇          選 LangGraph 的理由            不選 AutoGen 的理由
──────────────────────────────────────────────────────────────
狀態管理      TypedDict 明確定義，可查詢      messages list 不透明
持久化        原生 checkpointer，斷點續傳     需要自行實作
條件分支      conditional edge 精確控制       GroupChat 由 LLM 決定
延遲          確定性路由，P99 可預測          Speaker selection 不穩定
生產案例      Replit、Elastic 已上線         生產案例相對較少
```

**Flip condition**：
- 選 LangGraph 當：需要持久化、人工介入、複雜分支邏輯
- 選 AutoGen 當：快速 POC、研究型任務、程式碼生成循環

---

### 決策 3：LangGraph vs. 自建

```
選擇          選 LangGraph 的理由            選自建的理由
──────────────────────────────────────────────────────────────
開發速度      Checkpointer 開箱即用           需自行實作所有基礎設施
社群支援      活躍社群，問題易找到答案        需自行解決所有問題
升級風險      LangChain 生態頻繁變更          完全自控，不依賴外部
效能          節點切換 overhead ~20–50ms      可優化到 < 5ms
可觀測性      與 LangSmith 深度整合          可接入任何 OTel 相容工具
```

**Flip condition**：
- 選 LangGraph 當：團隊 < 10 人，需要快速迭代，生產成熟度夠
- 選自建當：節點數 < 10、流程確定性高、框架 overhead 是瓶頸

---

### 決策 4：Semantic Kernel vs. LangGraph

```
選擇          選 SK 的理由                   不選 LangGraph 的理由
──────────────────────────────────────────────────────────────
技術棧        .NET / Azure 環境              Python 優先環境
企業整合      Azure AD、RBAC、Compliance     需自行處理企業安全
社群生態      Microsoft 官方支援             LangChain 社群更大
AI 功能多樣性 Planner 強，記憶體抽象好        圖執行更靈活
```

**Flip condition**：
- 選 SK 當：在 Microsoft 企業技術棧，有 Azure 合規需求
- 選 LangGraph 當：Python 優先，需要靈活的圖執行

---

### 決策 5：單一框架 vs. 混合使用

```
選擇          選單一框架的理由               選混合使用的理由
──────────────────────────────────────────────────────────────
複雜度        依賴關係簡單，升級一次搞定      各框架用在最擅長的地方
學習成本      團隊只需熟悉一種框架            需要多種框架的知識
整合難度      狀態模型一致                   狀態轉換需要手動橋接
適用規模      早期到中期                     大型系統，不同模組需求差異大
```

**Flip condition**：
- 選單一框架當：系統規模 < Phase 2，保持簡單
- 選混合當：Phase 3，確定性工作流用 LangGraph，研究型子任務用 AutoGen

---

### 決策 6：有框架 vs. 純 LLM API

```
選擇          選框架的理由                   直接用 LLM API 的理由
──────────────────────────────────────────────────────────────
開發速度      工具整合、狀態管理、重試內建    無學習成本，直接控制
抽象層        隱藏複雜性，快速迭代            避免框架 overhead
社群工具      LangSmith、Langfuse 整合        自選最適合的監控工具
彈性          受框架執行模型限制              完全自由，但需要更多程式碼
```

**Flip condition**：
- 選框架當：Agent 數量 > 2、需要工具整合、有持久化需求
- 直接用 API 當：單一 LLM 呼叫 + 簡單工具呼叫，框架只增加複雜度

---

## 九、系統效應

各框架在真實生產環境的量化比較（基於公開 benchmark 與社群回報數據）：

```
指標                   AutoGen 0.4   CrewAI      LangGraph   自建
──────────────────────────────────────────────────────────────────────
POC 開發時間           1–2 天        1–2 天      3–5 天      5–10 天
MVP 開發時間           2–3 週        2–3 週      3–4 週      6–10 週
節點切換 overhead      150–400ms     100–300ms   20–50ms     < 5ms
GroupChat latency      +800ms–2s     N/A         N/A         N/A
Checkpointing          需自行實作    需自行實作  原生支援    需自行實作
Human-in-the-loop      有（複雜）    有（有限）  原生支援    需自行實作
框架升級風險           高（0.2→0.4） 中          中          低（自控）
社群活躍度（★）        ★★★★         ★★★         ★★★★★      N/A
生產案例               中等          中等        較多        視團隊而定
Python 型別安全        中等          中等        高（TypedDict） 完全自控
成本追蹤粒度           Task 級       Task 級     Node 級     完全自控
```

**關鍵洞察**：
- LangGraph 在 **可靠性** 和 **可觀測性** 上領先，但學習成本最高
- CrewAI 在 **可讀性** 和 **快速交付** 上領先，但生產靈活性不足
- AutoGen 在 **研究型對話任務** 上最適合，但不適合高流量生產環境
- 自建框架的 overhead < 5ms 對比 LangGraph 的 20–50ms，在高 QPS 場景（> 1K QPS）節省成本可達 30–50%

---

## 十、面試答題要點

> *「針對客服自動化系統，我會選 LangGraph 作為主要框架。理由是：客服系統的狀態（意圖、查詢結果、草稿回應、品質評分）需要結構化存儲和可查詢性，LangGraph 的 TypedDict state 原生支援；品質審核可能需要循環重試，conditional edge 讓邏輯顯式可控；對話持久化和斷點續傳是生產必備，LangGraph 的 PostgreSQL checkpointer 開箱即用。AutoGen 的 GroupChat speaker selection 每輪增加 800ms–2s 不確定延遲，不適合客服的 P99 SLA 要求。當日對話量從 5K 擴展到 50 萬後，我會把四個 Agent 拆成獨立微服務，用 Message Queue 解耦，協調層改為精簡自建（< 30 行核心邏輯），把框架 overhead 從 20–50ms/node 壓到 < 5ms，同時獲得 per-agent 獨立擴展的能力，估計在 100K QPS 級別可節省約 40% 運算成本。」*

---

## 十一、系列導航

← **Phase 14 Part 2**：[Agent 記憶體架構 — 短期、長期與情節記憶的工程設計](/posts/ai-eng-from-scratch-phase14-part2-memory-zh/)

→ **Phase 14 Part 4**：[Agent 評估與可觀測性 — 如何知道你的 Agent 表現好不好](/posts/ai-eng-from-scratch-phase14-part4-eval-zh/)

---

*本文屬於「AI 工程從零開始」系列 Phase 14。如有技術討論，歡迎透過 GitHub Issues 或部落格留言區交流。*
