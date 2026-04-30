---
title: "用 AI Bot 打造顧問團隊（二）：三條路線的實作步驟與範例程式碼"
date: 2026-04-30T10:00:00+08:00
draft: false
description: "深入實作：分別用 Claude Code + AGENTS.md、Gemini CLI 與 LangGraph 建立 AI 顧問 Agent 團隊。包含完整設定步驟、System Prompt 設計、範例程式碼與關鍵注意事項。"
categories: ["AI", "Agent", "Engineering", "all"]
tags: ["AI Agent", "Claude Code", "Gemini CLI", "LangGraph", "Python", "Multi-Agent", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "30 min"
---

## 前言

[上一篇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/) 我們比較了三條技術路線的優缺點。本篇進入**動手實作**，每條路線都包含：

1. 環境設定
2. 角色（Agent）定義
3. 實際執行範例
4. 關鍵注意事項

---

## 路線 A：Claude Code + AGENTS.md + Skills

### 1. 環境設定

```bash
# 安裝 Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 確認版本
claude --version

# 登入（需要 Anthropic 帳號）
claude auth login
```

建立專案目錄：

```bash
mkdir ai-consultant-team && cd ai-consultant-team
```

### 2. 建立 AGENTS.md（團隊憲章）

`AGENTS.md` 是整個 Agent 團隊的「組織架構圖」，定義各角色的職責與協作方式。

```markdown
# AI 顧問團隊 - 組織架構

## 團隊宗旨
協助中小企業做出明智的 AI 導入決策，提供從需求診斷到執行規劃的完整顧問服務。

## 角色定義

### Coordinator（協調員）
- **職責**：接收初始需求，判斷複雜度，分派給對應 Agent
- **不做**：不直接撰寫報告，不做技術分析
- **輸出格式**：JSON，包含 task_id、assigned_agent、priority

### Intake Agent（需求收集師）
- **職責**：與客戶對話，收集結構化需求資訊
- **問題清單**：產業、公司規模、現有系統、痛點、預算範圍、時程
- **輸出格式**：Markdown 的需求摘要文件

### Analyst Agent（問題分析師）
- **職責**：根據需求摘要，診斷問題根源，評估 AI 導入可行性
- **輸出格式**：包含 feasibility_score (1-10)、risks[]、opportunities[] 的分析報告

### Strategist Agent（策略顧問）
- **職責**：設計 AI 解決方案，評估 ROI，排列優先順序
- **輸出格式**：方案比較表 + 建議路徑

### Writer Agent（報告撰寫師）
- **職責**：整合所有 Agent 的輸出，產出最終顧問報告
- **格式**：Executive Summary + 詳細分析 + 行動計畫
```

### 3. 建立各 Agent 的 Skill 檔案

```bash
mkdir -p .claude/skills
```

**`.claude/skills/intake.md`**

```markdown
# Skill: 客戶需求收集

你是 Intake Agent，AI 顧問公司的需求收集師。

## 你的任務
透過結構化問題，收集客戶的完整需求。每個問題問完後等待客戶回答，不要一次列出所有問題。

## 問題清單（依序提問）
1. 請問貴公司主要的業務是什麼？目前的規模大概多少人？
2. 您目前遇到最大的業務痛點是什麼？
3. 您對 AI 導入的期望是什麼？（降低成本、提升效率、新產品還是其他？）
4. 目前公司使用哪些主要的軟體系統？（ERP、CRM、資料庫等）
5. 預計的投資預算範圍大概是？（不需要精確，粗估即可）
6. 希望在多久內看到初步成果？

## 輸出格式
收集完畢後，產出以下格式的需求摘要：

```json
{
  "company": {
    "industry": "",
    "size": "",
    "current_systems": []
  },
  "pain_points": [],
  "ai_expectations": [],
  "budget_range": "",
  "timeline": "",
  "priority_level": "high|medium|low"
}
```
```

**`.claude/skills/diagnose.md`**

```markdown
# Skill: 問題診斷分析

你是 Analyst Agent，AI 顧問公司的問題分析師。

## 輸入
你會收到 Intake Agent 產出的 JSON 需求摘要。

## 你的任務
1. 分析客戶的痛點，找出可以用 AI 解決的核心問題
2. 評估每個問題的 AI 可行性（技術成熟度、資料可得性、ROI 潛力）
3. 識別潛在風險（資料品質、組織阻力、技術債）

## 輸出格式
```json
{
  "diagnosis": {
    "core_problems": [
      {
        "problem": "問題描述",
        "ai_solution_type": "自動化|預測|生成|分類",
        "feasibility_score": 8,
        "data_readiness": "high|medium|low",
        "estimated_roi": "高/中/低"
      }
    ],
    "risks": [
      {
        "risk": "風險描述",
        "severity": "high|medium|low",
        "mitigation": "緩解策略"
      }
    ],
    "recommended_focus": "最建議優先處理的問題"
  }
}
```
```

### 4. 設定 `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Bash(mkdir:*)",
      "Bash(cat:*)",
      "Bash(echo:*)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "echo '[LOG] Agent 產出新文件: $CLAUDE_TOOL_OUTPUT' >> workspace/activity.log"
          }
        ]
      }
    ]
  }
}
```

### 5. 實際執行

```bash
# 啟動協調員，開始顧問流程
claude "根據 AGENTS.md 的角色定義，你是 Coordinator。
有一位新客戶想要諮詢 AI 導入。請先呼叫 Intake Agent（使用 /skills/intake skill）
收集需求，再呼叫 Analyst Agent 進行診斷。"
```

---

## 路線 B：Gemini CLI + Google Workspace

### 1. 環境設定

```bash
# 安裝 Gemini CLI
npm install -g @google/gemini-cli

# 或使用 Python 版
pip install google-generativeai google-auth google-auth-oauthlib

# 設定 API Key
export GEMINI_API_KEY="your-api-key-here"

# Google Workspace 整合需要 OAuth
gcloud auth application-default login
```

### 2. 定義 Agent System Prompts

建立一個 `prompts/` 目錄存放各 Agent 的 System Prompt：

**`prompts/consultant_agent.txt`**（參考 ai_consultant repo 的設計）

```
You are a professional AI consultant with a strong blend of business acumen and technical expertise.
You approach problems with the mindset of a C-suite executive while remaining practical and grounded
like an SMB manager responsible for day-to-day execution.

You think in terms of outcomes, ROI, and competitive advantage—not just technology for its own sake.

In every response, you:
* Clarify the business objective before suggesting solutions
* Frame trade-offs (cost, speed, risk, scalability)
* Provide structured, actionable recommendations
* Anticipate implementation challenges
* Focus on measurable impact and sustainability
```

### 3. Python 整合腳本

```python
# consultant_team.py
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json
import os

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

class ConsultantAgent:
    def __init__(self, role: str, system_prompt: str):
        self.role = role
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=system_prompt
        )
        self.chat = self.model.start_chat(history=[])

    def process(self, input_text: str) -> str:
        response = self.chat.send_message(input_text)
        return response.text


class ConsultantTeam:
    def __init__(self):
        self.intake = ConsultantAgent(
            role="intake",
            system_prompt=open("prompts/intake.txt").read()
        )
        self.analyst = ConsultantAgent(
            role="analyst",
            system_prompt=open("prompts/analyst.txt").read()
        )
        self.strategist = ConsultantAgent(
            role="strategist",
            system_prompt=open("prompts/consultant_agent.txt").read()
        )

    def run_full_consultation(self, client_input: str) -> dict:
        print(f"[Intake] 收集需求...")
        intake_result = self.intake.process(client_input)

        print(f"[Analyst] 診斷問題...")
        analyst_result = self.analyst.process(
            f"請分析以下需求：\n{intake_result}"
        )

        print(f"[Strategist] 設計策略...")
        strategy_result = self.strategist.process(
            f"需求摘要：{intake_result}\n\n診斷結果：{analyst_result}\n\n請提出具體的 AI 導入策略。"
        )

        return {
            "intake": intake_result,
            "analysis": analyst_result,
            "strategy": strategy_result
        }


# 使用範例
if __name__ == "__main__":
    team = ConsultantTeam()
    result = team.run_full_consultation(
        "我們是一家 50 人的製造業公司，想要用 AI 減少品管的人力成本。"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

### 4. 寫入 Google Docs

```python
# google_docs_writer.py
from googleapiclient.discovery import build
from google.oauth2 import service_account

def write_report_to_docs(report_content: str, title: str) -> str:
    """將顧問報告寫入 Google Docs，回傳文件 URL"""
    creds = service_account.Credentials.from_service_account_file(
        "service_account.json",
        scopes=["https://www.googleapis.com/auth/documents"]
    )
    service = build("docs", "v1", credentials=creds)

    # 建立新文件
    doc = service.documents().create(
        body={"title": title}
    ).execute()
    doc_id = doc["documentId"]

    # 寫入內容
    service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": report_content
                    }
                }
            ]
        }
    ).execute()

    return f"https://docs.google.com/document/d/{doc_id}"
```

---

## 路線 C：LangGraph + LLM（完整程式碼）

### 1. 環境設定

```bash
pip install langgraph langchain langchain-anthropic langchain-openai
pip install psycopg2-binary redis  # 狀態持久化

# 設定環境變數
export ANTHROPIC_API_KEY="your-key"
export LANGCHAIN_API_KEY="your-langsmith-key"  # 可觀測性
export LANGCHAIN_TRACING_V2=true
```

### 2. 定義狀態結構

```python
# state.py
from typing import TypedDict, Annotated, List
from langgraph.graph.message import add_messages

class ConsultantState(TypedDict):
    # 對話歷史
    messages: Annotated[list, add_messages]
    # 客戶需求（結構化）
    client_requirements: dict
    # 診斷結果
    diagnosis: dict
    # 策略方案
    strategy: dict
    # 最終報告
    final_report: str
    # 當前階段
    current_phase: str
    # 錯誤訊息
    error: str | None
```

### 3. 定義各 Agent 節點

```python
# agents.py
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from state import ConsultantState
import json

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.3)

INTAKE_PROMPT = """你是 AI 顧問公司的需求收集師。
根據客戶的描述，提取並結構化以下資訊：
- 產業與公司規模
- 核心痛點（最多 3 個）
- AI 期望（自動化/預測/生成/其他）
- 現有系統
- 預算與時程

以 JSON 格式回覆，key 使用英文。"""

ANALYST_PROMPT = """你是 AI 顧問公司的問題分析師。
根據客戶需求，評估 AI 導入的可行性。
對每個痛點給出：
- feasibility_score (1-10)
- 所需資料類型
- 預估 ROI
- 主要風險

以 JSON 格式回覆。"""

STRATEGIST_PROMPT = """你是資深 AI 顧問。
根據需求診斷，設計具體的 AI 導入策略：
1. 建議的第一個 AI 專案（Quick Win）
2. 6 個月的路線圖
3. 所需資源（人力、技術、預算）
4. 成功指標（KPI）

用繁體中文，以 Markdown 格式回覆。"""


def intake_agent(state: ConsultantState) -> ConsultantState:
    """需求收集 Agent"""
    messages = [
        SystemMessage(content=INTAKE_PROMPT),
        HumanMessage(content=str(state["messages"][-1].content))
    ]
    response = llm.invoke(messages)

    try:
        requirements = json.loads(response.content)
    except json.JSONDecodeError:
        requirements = {"raw": response.content}

    return {
        "client_requirements": requirements,
        "current_phase": "analysis",
        "messages": [response]
    }


def analyst_agent(state: ConsultantState) -> ConsultantState:
    """問題診斷 Agent"""
    messages = [
        SystemMessage(content=ANALYST_PROMPT),
        HumanMessage(content=json.dumps(state["client_requirements"], ensure_ascii=False))
    ]
    response = llm.invoke(messages)

    try:
        diagnosis = json.loads(response.content)
    except json.JSONDecodeError:
        diagnosis = {"raw": response.content}

    return {
        "diagnosis": diagnosis,
        "current_phase": "strategy",
        "messages": [response]
    }


def strategist_agent(state: ConsultantState) -> ConsultantState:
    """策略設計 Agent"""
    context = f"""
客戶需求：
{json.dumps(state['client_requirements'], ensure_ascii=False, indent=2)}

診斷結果：
{json.dumps(state['diagnosis'], ensure_ascii=False, indent=2)}
"""
    messages = [
        SystemMessage(content=STRATEGIST_PROMPT),
        HumanMessage(content=context)
    ]
    response = llm.invoke(messages)

    return {
        "strategy": {"content": response.content},
        "current_phase": "report",
        "messages": [response]
    }


def writer_agent(state: ConsultantState) -> ConsultantState:
    """報告撰寫 Agent"""
    report = f"""# AI 導入顧問報告

## Executive Summary
{state['strategy'].get('content', '')}

---
*報告由 AI 顧問團隊自動生成*
*日期：{__import__('datetime').date.today()}*
"""
    return {
        "final_report": report,
        "current_phase": "done",
        "messages": []
    }
```

### 4. 組裝 Graph（核心邏輯）

```python
# graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import ConsultantState
from agents import intake_agent, analyst_agent, strategist_agent, writer_agent


def route_after_analysis(state: ConsultantState) -> str:
    """根據診斷結果決定下一步"""
    diagnosis = state.get("diagnosis", {})
    # 如果可行性分數平均低於 5，建議先做資料準備
    scores = [
        item.get("feasibility_score", 5)
        for item in diagnosis.get("core_problems", [{}])
    ]
    avg_score = sum(scores) / len(scores) if scores else 5

    if avg_score < 4:
        return "low_feasibility"  # 未來可加入特殊處理節點
    return "strategist"


def build_consultant_graph():
    graph = StateGraph(ConsultantState)

    # 加入節點
    graph.add_node("intake", intake_agent)
    graph.add_node("analyst", analyst_agent)
    graph.add_node("strategist", strategist_agent)
    graph.add_node("writer", writer_agent)

    # 定義流程
    graph.set_entry_point("intake")
    graph.add_edge("intake", "analyst")
    graph.add_conditional_edges(
        "analyst",
        route_after_analysis,
        {
            "strategist": "strategist",
            "low_feasibility": "strategist"  # 目前都走同一路
        }
    )
    graph.add_edge("strategist", "writer")
    graph.add_edge("writer", END)

    # 加入記憶體（可換成 PostgreSQL）
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# 執行
if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    app = build_consultant_graph()

    config = {"configurable": {"thread_id": "client-001"}}
    result = app.invoke(
        {
            "messages": [HumanMessage(content=(
                "我們是一家台灣的中型製造商，約 200 人。"
                "目前最大的問題是品管效率太低，每天要花 5 個工人做外觀檢測。"
                "希望能用 AI 自動化這個流程，預算大概 100-300 萬台幣。"
            ))],
            "current_phase": "intake",
            "error": None
        },
        config=config
    )

    print(result["final_report"])
```

### 5. 加入人機協作（Human-in-the-Loop）

對於高風險決策，可以加入人工審核節點：

```python
from langgraph.graph import interrupt

def human_review_node(state: ConsultantState) -> ConsultantState:
    """讓人類審核策略後再繼續"""
    # 這會暫停執行，等待人類輸入
    human_feedback = interrupt({
        "question": "請審核以下 AI 策略建議，是否同意送出給客戶？",
        "strategy": state["strategy"]
    })

    if human_feedback.get("approved"):
        return {"current_phase": "report"}
    else:
        # 根據人類反饋修正
        return {
            "strategy": {
                "content": human_feedback.get("revised_strategy", ""),
                "human_approved": True
            }
        }

# 在 graph 中加入此節點
graph.add_node("human_review", human_review_node)
graph.add_edge("strategist", "human_review")
graph.add_edge("human_review", "writer")
```

---

## 三條路線的 System Prompt 設計原則

不管選哪條路線，好的 System Prompt 是關鍵。以下是設計原則：

### 原則 1：明確角色邊界

```
✅ 好的寫法：
"你是需求收集師。你只負責提問和整理需求，
不要給建議，不要做分析，不要撰寫報告。"

❌ 不好的寫法：
"你是一個 AI 助理，幫助客戶解決 AI 問題。"
```

### 原則 2：定義輸出格式

```
✅ 好的寫法：
"回覆必須是合法的 JSON，schema 如下：
{ 'pain_points': string[], 'budget': string, 'timeline': string }"

❌ 不好的寫法：
"用結構化的方式回覆。"
```

### 原則 3：處理邊界情況

```
✅ 好的寫法：
"如果客戶的問題超出 AI 顧問範疇（例如法律、財務），
回覆：'這個問題需要專業[法律/財務]顧問，我可以協助介紹。'"
```

### 原則 4：Few-shot 範例

在 System Prompt 中加入 2-3 個好的輸入/輸出範例，能大幅提升一致性。

---

## 小結

| 路線 | 最難的部分 | 最容易踩的坑 |
|------|-----------|------------|
| A（Claude Code） | 多 Agent 狀態同步 | Skill 呼叫不穩定 |
| B（Gemini CLI） | Google OAuth 設定 | Context 太大時回應變慢 |
| C（LangGraph） | State 設計與 routing | JSON 解析失敗中斷流程 |

**通用建議：** 每個 Agent 的輸入/輸出都要有 schema 驗證，錯誤時要有 fallback，不要讓一個 Agent 的失敗癱瘓整個團隊。

下一篇（第三篇）：如何評估系統效能、監控、部署與持續改善。

---

*本系列文章：*
- [第一篇：策略與技術路線選擇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/)
- **第二篇（本篇）：各路線實作步驟與範例程式碼**
- [第三篇：評估、維運與優化計畫](/posts/ai-agent-team-for-consultant-part3-devops-zh/)
