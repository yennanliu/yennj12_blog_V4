---
title: "CrewAI 完全指南（一）：入門與核心概念——用多 Agent 協作解決複雜問題"
date: 2026-05-21T09:00:00+08:00
draft: false
description: "從零開始學 CrewAI：什麼是多 Agent 協作框架、為什麼需要它、核心四大元件（Agent、Task、Crew、Tool）的詳細說明，以及你的第一個 CrewAI 應用程式。"
categories: ["AI", "Agent", "Engineering", "all"]
tags: ["CrewAI", "Multi-Agent", "LLM", "AI Automation", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "20 min"
---

## 前言

你有沒有遇過這樣的情境？  
你想讓 AI 幫你完成一個任務，但任務太複雜，單一的 ChatGPT 對話沒辦法做好：

- 需要同時搜尋網路、分析資料、寫報告
- 不同步驟需要不同的「專業角色」
- 任務很長，單一 context window 放不下

**CrewAI** 就是為了解決這個問題而生的。它讓你可以建立一個**由多個 AI Agent 組成的團隊**，每個 Agent 有自己的角色、工具和目標，協作完成複雜任務。

---

## 什麼是 CrewAI？

CrewAI 是一個開源的 Python 框架，專門用來建立**多 Agent 協作系統**。

用一個類比來說：

```
傳統 LLM 呼叫：你問一個全才顧問所有問題
CrewAI：你僱用一個團隊——研究員、分析師、文案、專案經理——各司其職
```

CrewAI 的核心理念是**角色扮演 + 任務分工**：

- 每個 Agent 有明確的**職責（role）**、**目標（goal）**、**背景故事（backstory）**
- 任務按照依賴關係自動排序和傳遞
- Crew 負責協調整個流程

### CrewAI vs 其他 Multi-Agent 框架

| 框架 | 特點 | 學習曲線 |
|------|------|---------|
| **CrewAI** | 角色扮演導向，強調協作，設定直覺 | 低 |
| LangGraph | 圖形化流程，狀態機，彈性高 | 中高 |
| AutoGen | Microsoft 出品，對話式協作 | 中 |
| LangChain Agents | 工具豐富，但單 Agent | 中 |

CrewAI 的設計哲學：**讓非工程師也能理解 Agent 的邏輯**（因為你在描述一個「團隊」，而不是寫演算法）。

---

## 安裝與環境設定

```bash
# 建立虛擬環境
python -m venv crewai_env
source crewai_env/bin/activate  # Windows: crewai_env\Scripts\activate

# 安裝 CrewAI（含常用工具）
pip install crewai crewai-tools

# 設定 API Key（CrewAI 預設使用 OpenAI）
export OPENAI_API_KEY="your-api-key"

# 如果要用 Anthropic Claude
export ANTHROPIC_API_KEY="your-api-key"
```

建立第一個專案：

```bash
crewai create crew my_first_crew
cd my_first_crew
```

這會自動產生標準專案結構：

```
my_first_crew/
├── src/my_first_crew/
│   ├── config/
│   │   ├── agents.yaml    ← 定義 Agent
│   │   └── tasks.yaml     ← 定義 Task
│   ├── crew.py            ← 組合 Crew
│   └── main.py            ← 執行入口
└── pyproject.toml
```

---

## 核心元件詳解

### 元件 1：Agent（智能體）

Agent 是 CrewAI 的基本單位，代表一個有特定職責的 AI 角色。

**三個必要屬性：**

```python
from crewai import Agent
from crewai_tools import SerperDevTool  # Google 搜尋工具

search_tool = SerperDevTool()

researcher = Agent(
    role="資深市場研究員",           # 角色名稱（影響 LLM 的行為）
    goal="找出目標市場的最新趨勢與競爭對手動態",  # Agent 的個人目標
    backstory="""你是一位有十年經驗的市場研究專家，
    擅長從海量資訊中找出關鍵洞察。你特別注重數據的可靠性，
    只引用可信來源，並以清晰的結構呈現研究結果。""",
    tools=[search_tool],            # 這個 Agent 可以用的工具
    llm="gpt-4o",                   # 使用的 LLM 模型
    verbose=True,                   # 開發時建議開啟，顯示思考過程
    max_iter=10,                    # 最多嘗試 10 次
    memory=True,                    # 啟用記憶功能
)
```

**為什麼 backstory 很重要？**

`backstory` 不只是裝飾，它直接影響 LLM 的行為。一個有「謹慎的研究員」背景的 Agent 和一個「大膽的創業家」背景的 Agent，面對同樣的任務會給出非常不同的結果。

---

### 元件 2：Task（任務）

Task 定義了 Agent 要完成的具體工作。

```python
from crewai import Task

research_task = Task(
    description="""研究 {topic} 的市場現況。
    具體需要找出：
    1. 市場規模（如有數據請引用來源）
    2. 前三名競爭對手及其核心優勢
    3. 最近 6 個月的重要趨勢
    4. 潛在市場機會""",
    
    expected_output="""一份結構清晰的市場研究報告，包含：
    - 市場規模概述（附數據來源）
    - 競爭對手分析表格
    - 趨勢摘要（3-5 個重點）
    - 機會評估
    格式：Markdown，長度約 800-1200 字""",
    
    agent=researcher,               # 指定由哪個 Agent 負責
    # context=[previous_task],      # 可以依賴其他 Task 的輸出
    # output_file="report.md",      # 可以直接輸出到檔案
)
```

**`description` 的撰寫技巧：**
- 越具體越好，列出清單，明確說明需要什麼格式
- 使用 `{topic}` 這類佔位符，在執行時動態替換
- 把「期望輸出」寫得越詳細，LLM 越不容易跑偏

---

### 元件 3：Crew（團隊）

Crew 把 Agents 和 Tasks 組合起來，定義協作模式。

```python
from crewai import Crew, Process

crew = Crew(
    agents=[researcher, analyst, writer],  # 團隊成員
    tasks=[research_task, analysis_task, writing_task],  # 任務清單
    
    process=Process.sequential,    # 循序執行（任務一個接一個）
    # process=Process.hierarchical,  # 階層式（由 manager 分配）
    
    verbose=True,
    memory=True,                   # 讓 Crew 在任務間保留記憶
)

# 啟動執行（inputs 的值會替換 description 裡的 {佔位符}）
result = crew.kickoff(inputs={"topic": "台灣電動車市場"})
print(result.raw)
```

**兩種執行模式：**

```
Sequential（循序）：
  Task 1 → Task 2 → Task 3 → 輸出
  前一個 Task 的結果自動傳給下一個 Task

Hierarchical（階層）：
  Manager Agent 拆解目標
    ├── 分配給 Agent A
    ├── 分配給 Agent B
    └── 彙整結果
  適合更動態、需要判斷的場景
```

---

### 元件 4：Tool（工具）

Tool 是 Agent 可以呼叫的外部能力。CrewAI 內建許多工具，也可以自訂。

```python
from crewai_tools import (
    SerperDevTool,       # Google 搜尋
    FileReadTool,        # 讀取本地檔案
    FileWriterTool,      # 寫入檔案
    ScrapeWebsiteTool,   # 網頁爬取
    PDFSearchTool,       # PDF 內容搜尋
    CSVSearchTool,       # CSV 資料查詢
    CodeInterpreterTool, # 執行 Python 程式碼
)

# 自訂工具
from crewai.tools import tool

@tool("台灣股市查詢工具")
def get_stock_price(ticker: str) -> str:
    """查詢台灣股票的即時價格。輸入股票代號（例如：2330）。"""
    # 實際上會呼叫 API，這裡用 mock
    prices = {"2330": 950, "2317": 120, "0050": 185}
    price = prices.get(ticker, "找不到此股票代號")
    return f"{ticker} 的即時股價：{price} 元"


# 掛載工具給 Agent
stock_analyst = Agent(
    role="股票分析師",
    goal="分析台灣股市動態",
    backstory="有多年台股投資經驗的分析師",
    tools=[get_stock_price, SerperDevTool()],
)
```

---

## 第一個完整範例：自動內容研究與撰寫

這是一個可以直接執行的完整範例：**自動研究一個主題，並產出一篇部落格文章草稿**。

```python
import os
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool

os.environ["OPENAI_API_KEY"] = "your-api-key"
os.environ["SERPER_API_KEY"] = "your-serper-key"  # serper.dev 免費額度

search_tool = SerperDevTool()

# ---- 定義 Agents ----

researcher = Agent(
    role="內容研究員",
    goal="深入研究指定主題，收集最新、最精確的資訊",
    backstory="""你是一位經驗豐富的內容研究員，擅長快速找到高品質的資訊。
    你會從多個來源交叉驗證，確保資料的準確性。
    你的研究報告結構清晰，重點突出。""",
    tools=[search_tool],
    verbose=True,
    llm="gpt-4o-mini",
)

writer = Agent(
    role="科技部落客",
    goal="根據研究資料，撰寫吸引人且資訊豐富的部落格文章",
    backstory="""你是一位擁有五年經驗的科技部落客，
    擅長將複雜的技術概念用淺顯易懂的方式呈現。
    你的文章既有深度，又不失趣味，讀者回饋極佳。
    你會搭配具體例子，讓讀者容易理解。""",
    verbose=True,
    llm="gpt-4o",
)

editor = Agent(
    role="資深編輯",
    goal="審閱並優化文章，確保品質、準確性和可讀性",
    backstory="""你是一位嚴謹的資深編輯，有豐富的科技媒體編輯經驗。
    你會檢查事實準確性、邏輯連貫性、文字流暢度，
    並給出具體的修改建議。""",
    verbose=True,
    llm="gpt-4o",
)

# ---- 定義 Tasks ----

research_task = Task(
    description="""請深入研究以下主題：{topic}

    需要收集的資訊：
    1. 最新發展動態（最近 3 個月內）
    2. 核心技術原理（用非技術語言解釋）
    3. 主要玩家和代表性產品
    4. 實際應用案例（至少 2-3 個）
    5. 未來發展趨勢

    請附上資訊來源。""",

    expected_output="""詳細的研究筆記，包含：
    - 主題概述（200 字內）
    - 最新動態清單（3-5 條，每條附來源連結）
    - 技術原理說明（300 字內）
    - 應用案例（各 100-200 字）
    - 趨勢預測（3 點）
    格式：Markdown""",

    agent=researcher,
)

writing_task = Task(
    description="""根據研究員提供的資料，撰寫一篇關於 {topic} 的部落格文章。

    文章要求：
    - 標題要吸睛，能引起好奇心
    - 開頭要有一個引人入勝的問題或故事
    - 內容要有邏輯層次（基礎 → 進階）
    - 加入 2-3 個具體的應用案例
    - 結尾要有行動呼籲（讀者下一步可以做什麼）
    - 語氣：專業但親切，像在跟朋友解釋""",

    expected_output="""一篇完整的部落格文章：
    - 長度：1200-1800 字
    - 有清晰的段落結構和小標題
    - 格式：Markdown
    - 包含一個「延伸閱讀」區塊""",

    agent=writer,
    context=[research_task],  # 這個 Task 會收到 research_task 的輸出
)

editing_task = Task(
    description="""審閱寫作者提交的文章，並給出具體的改進建議。

    審閱重點：
    1. 事實正確性（是否與研究資料一致？）
    2. 邏輯連貫性（段落之間是否順暢？）
    3. 讀者體驗（是否容易理解？）
    4. 標題和副標題的吸引力
    5. 錯別字和語法問題

    如果文章整體良好，可以直接輸出最終版本。
    如果需要修改，請提供修改後的完整版本。""",

    expected_output="""最終版本的部落格文章（Markdown 格式），
    以及一份簡短的編輯說明（說明做了哪些調整，或為何認為不需要調整）。""",

    agent=editor,
    context=[writing_task],
)

# ---- 建立 Crew 並執行 ----

content_crew = Crew(
    agents=[researcher, writer, editor],
    tasks=[research_task, writing_task, editing_task],
    process=Process.sequential,
    verbose=True,
)

result = content_crew.kickoff(inputs={"topic": "AI Agent 在企業自動化的應用"})

print("\n" + "="*60)
print("最終輸出：")
print("="*60)
print(result.raw)
```

---

## 執行結果解讀

CrewAI 執行時，你會看到每個 Agent 的思考過程（`verbose=True`）：

```
[2024-01-15 10:00:01][DEBUG]: Working Agent: 內容研究員
[2024-01-15 10:00:01][INFO]: Starting Task: 請深入研究以下主題：AI Agent...

> Entering new CrewAgentExecutor chain...
  我需要搜尋最新的 AI Agent 企業應用資訊...
  
  Action: Search the internet
  Action Input: {"search_query": "AI Agent enterprise automation 2024"}
  
  Observation: [搜尋結果...]
  
  Thought: 找到了一些資訊，讓我再搜尋更具體的案例...
  ...

[2024-01-15 10:02:15][DEBUG]: [Task output]:
## AI Agent 企業應用研究筆記
...

[2024-01-15 10:02:15][DEBUG]: Working Agent: 科技部落客
...
```

最終輸出透過 `result` 物件取得：

```python
print(result.raw)            # 原始文字輸出
print(result.token_usage)    # token 用量統計
```

---

## 小結

這篇介紹了：

- **CrewAI 的核心概念**：用多 Agent 協作解決複雜任務
- **四大元件**：Agent（角色）、Task（任務）、Crew（團隊）、Tool（工具）
- **第一個完整範例**：自動研究 + 撰寫 + 編輯的內容生成 Crew

下一篇我們會用三個**更貼近真實工作場景的應用**：競爭對手情報分析、自動化程式碼審查、以及客服需求分類系統，展示 CrewAI 如何解決實際業務問題。

---

**系列導覽**

- **第一篇（本篇）**：入門與核心概念
- [第二篇](/posts/crewai-series-part2-real-world-tasks-zh/)：真實場景實戰——競情分析、程式碼審查、客服自動化
- [第三篇](/posts/crewai-series-part3-advanced-flows-zh/)：進階技巧——Flows、Memory、結構化輸出與生產部署
