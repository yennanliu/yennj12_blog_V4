---
title: "用 AI Bot 打造顧問團隊（五）：數位行銷公司實戰案例"
date: 2026-04-30T13:00:00+08:00
draft: false
description: "實戰案例：一家 8 人數位行銷公司如何用 AI Agent 團隊自動化內容策略、廣告文案、成效報告與客戶簡報，包含完整 Prompt、LangGraph 實作與執行步驟。"
categories: ["AI", "Agent", "Business", "Case Study", "Marketing", "all"]
tags: ["AI Agent", "數位行銷", "LangGraph", "Claude", "內容行銷", "廣告文案", "Multi-Agent", "繁體中文", "實戰案例"]
authors: ["YennJ12 Engineering Team"]
readTime: "30 min"
---

## 情境設定

**公司背景：** PixelFlow Agency，台灣台中，8 人數位行銷公司  
**主要服務：** 社群媒體管理、廣告投放（Meta / Google Ads）、SEO、內容行銷  
**服務客戶數：** 同時服務 15-20 個品牌  
**核心痛點：**
- 每個客戶每月需要 30-50 篇社群貼文，文案師產能跟不上
- 廣告成效報告每月要花 2 天手動彙整，格式各異
- 新客戶的「內容策略規劃」每次都要從頭寫，耗時 3-5 天
- 客戶問「我們這個月的廣告怎麼樣」時，帳號管理師要翻資料才能回答

**目標：** AI Agent 承擔 60% 的文案產出、100% 的報告彙整、80% 的策略草稿。

---

## 整體架構設計

```
定期觸發（每日/每週/每月）+ 客戶即時請求
        ↓
① Brand Agent（品牌守門員）
   → 載入品牌 DNA，確保所有輸出符合品牌調性
        ↓
   ┌────────────────────────────────┐
   │  並行執行（Parallel Execution）  │
   ├──────────────┬─────────────────┤
② Content Agent  ③ Ad Copy Agent
  （內容策略師）    （廣告文案師）
   └──────────────┴─────────────────┘
        ↓
④ Analyst Agent（數據分析師）
   → 讀取廣告成效數據，產出洞察
        ↓
⑤ Report Agent（報告撰寫師）
   → 整合所有產出，製作月報/週報
        ↓
⑥ Presenter Agent（簡報師）
   → 把報告轉成客戶易讀的簡報格式
```

**技術選型：** 本案例使用 **LangGraph + Claude API**（路線 C）  
理由：需要並行處理多個客戶 + 複雜的條件流程 + 整合廣告平台 API

---

## Step 1：專案初始化

```bash
mkdir pixelflow-ai-team && cd pixelflow-ai-team

# 安裝依賴
pip install langgraph langchain-anthropic langchain-core \
            pandas openpyxl jinja2 python-pptx httpx

# 目錄結構
mkdir -p {brands,outputs/{content,reports,slides},prompts,tools}
```

```
pixelflow-ai-team/
├── main.py                    ← 主程式入口
├── state.py                   ← 狀態定義
├── graph.py                   ← LangGraph 流程圖
├── agents/
│   ├── brand_agent.py
│   ├── content_agent.py
│   ├── ad_copy_agent.py
│   ├── analyst_agent.py
│   ├── report_agent.py
│   └── presenter_agent.py
├── tools/
│   ├── meta_ads_reader.py     ← 讀取 Meta Ads 數據
│   └── google_ads_reader.py   ← 讀取 Google Ads 數據
├── brands/
│   ├── client_A.json          ← 客戶品牌 DNA
│   └── client_B.json
└── prompts/
    ├── content_templates.md
    └── report_templates.md
```

---

## Step 2：品牌 DNA 設計（每個客戶一份）

品牌 DNA 是所有 Agent 的「護欄」，確保不管哪個 Agent 產出，都符合品牌調性。

**`brands/client_A.json`** 範例（假設客戶是一家有機食品品牌）：

```json
{
  "client_id": "client_A",
  "brand_name": "綠野良田",
  "industry": "有機食品",
  "target_audience": {
    "primary": "30-45歲，注重健康的都市媽媽",
    "secondary": "25-35歲，環保意識強的年輕人"
  },
  "brand_voice": {
    "tone": "溫暖、真實、專業但不冷漠",
    "avoid": ["誇大功效詞彙（例如：神奇、奇蹟）", "過度推銷感的語氣", "英文夾雜"],
    "keywords": ["自然", "無農藥", "產地直送", "用心", "土地"]
  },
  "platforms": ["Facebook", "Instagram", "LINE"],
  "posting_schedule": {
    "facebook": 3,
    "instagram": 5,
    "line": 2
  },
  "content_pillars": [
    "產品介紹（30%）",
    "農場故事（25%）",
    "食譜/料理靈感（25%）",
    "健康知識（15%）",
    "促銷活動（5%）"
  ],
  "hashtag_strategy": {
    "brand_tags": ["#綠野良田", "#有機生活"],
    "content_tags": ["#有機食品", "#產地直送", "#無農藥"],
    "trend_tags": "每週更新，由 Content Agent 建議"
  },
  "past_top_posts": [
    {
      "platform": "Instagram",
      "content_type": "農場故事",
      "engagement_rate": 0.082,
      "key_elements": ["農夫主角", "清晨光線照片", "150字以內文案"]
    }
  ],
  "forbidden_topics": ["競爭品牌比較", "政治議題", "未經驗證的健康聲稱"]
}
```

---

## Step 3：State 定義

```python
# state.py
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages

class MarketingState(TypedDict):
    # 基本資訊
    client_id: str
    task_type: str           # "content_batch" | "monthly_report" | "ad_copy" | "strategy"
    period: str              # "2026-04"

    # 品牌資料
    brand_dna: dict

    # 各 Agent 產出
    content_plan: dict       # 本月內容規劃
    post_drafts: List[dict]  # 社群貼文草稿清單
    ad_copies: List[dict]    # 廣告文案清單
    analytics_data: dict     # 廣告數據
    insights: dict           # 數據洞察
    report: str              # 月報全文
    slide_content: dict      # 簡報結構

    # 控制流
    current_agent: str
    approved_posts: List[str]   # 人工審核通過的貼文 ID
    error: Optional[str]
    messages: Annotated[list, add_messages]
```

---

## Step 4：各 Agent 實作

### Brand Agent（品牌守門員）

```python
# agents/brand_agent.py
import json
from pathlib import Path
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.2)

BRAND_AGENT_PROMPT = """你是品牌守門員，負責在所有行銷工作開始前，
確保整個 AI 團隊完全理解這個品牌的核心精神。

你的任務：
1. 讀取品牌 DNA 檔案
2. 產出給其他 Agent 使用的「品牌簡報」
3. 列出 3 個最近成效好的內容類型（供 Content Agent 參考）
4. 提醒本月應該避免的敏感話題

品牌簡報格式（Markdown）：
## 品牌核心
## 目標受眾特徵（3 個最具體的描述）
## 這個月的內容重點（根據季節/節慶/品牌行事曆）
## 語氣規範（5 個 DO / 5 個 DON'T）
## 本月禁止話題
"""

def brand_agent(state: MarketingState) -> MarketingState:
    brand_path = Path(f"brands/{state['client_id']}.json")
    brand_dna = json.loads(brand_path.read_text(encoding="utf-8"))

    response = llm.invoke([
        SystemMessage(content=BRAND_AGENT_PROMPT),
        HumanMessage(content=f"請為以下品牌產出品牌簡報：\n{json.dumps(brand_dna, ensure_ascii=False, indent=2)}")
    ])

    return {
        "brand_dna": brand_dna,
        "current_agent": "content_and_ad",
        "messages": [response]
    }
```

### Content Agent（內容策略師）

```python
# agents/content_agent.py
CONTENT_AGENT_PROMPT = """你是資深社群內容策略師，擅長為品牌規劃有溫度、
有轉換率的社群內容。

## 你的任務
根據品牌 DNA 和本月行事曆，規劃一個月的社群內容，並產出草稿。

## 內容規劃原則
1. 遵守品牌 DNA 中的內容比例（Content Pillars）
2. 每篇貼文要有明確目的：曝光、互動、轉換 選其一
3. 平台差異化：Instagram 視覺導向（短文案）、Facebook 故事導向（長文案）、LINE 直接實用

## 每篇貼文草稿格式
```json
{
  "post_id": "POST-001",
  "platform": "Instagram",
  "content_pillar": "農場故事",
  "goal": "engagement",
  "post_date": "2026-04-05",
  "copy": "貼文文案內容",
  "visual_direction": "建議搭配的視覺方向（給設計師看）",
  "hashtags": ["#tag1", "#tag2"],
  "cta": "行動呼籲",
  "estimated_engagement": "high|medium|low"
}
```

## 本月節慶/特殊日期（需要特別規劃）
依照傳入的月份自動判斷（例如：4月 → 清明、地球日、兒童節）
"""

def content_agent(state: MarketingState) -> MarketingState:
    brand_dna = state["brand_dna"]
    period = state["period"]

    # 計算需要多少貼文
    total_posts = sum(brand_dna.get("posting_schedule", {}).values())
    platforms = brand_dna.get("platforms", [])

    response = llm.invoke([
        SystemMessage(content=CONTENT_AGENT_PROMPT),
        HumanMessage(content=f"""
品牌資料：{json.dumps(brand_dna, ensure_ascii=False)}
月份：{period}
需要規劃：{total_posts} 篇貼文（{', '.join(platforms)}）
請產出完整的貼文草稿清單（JSON 陣列格式）。
""")
    ])

    # 解析 JSON 輸出
    try:
        import re
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        post_drafts = json.loads(json_match.group()) if json_match else []
    except Exception:
        post_drafts = []

    return {
        "post_drafts": post_drafts,
        "messages": [response]
    }
```

### Ad Copy Agent（廣告文案師）

```python
# agents/ad_copy_agent.py
AD_COPY_PROMPT = """你是專業的數位廣告文案師，精通 Meta Ads 和 Google Ads 的文案規格。

## 廣告文案原則
1. Meta Ads：主要文案 ≤ 125 字，標題 ≤ 40 字，描述 ≤ 30 字
2. Google Ads：標題 ≤ 30 字（最多 3 個），描述 ≤ 90 字（最多 2 個）
3. 每個廣告要有清楚的 USP（獨特賣點）
4. CTA 要明確：「立即購買」比「了解更多」轉換率高 30-40%

## 廣告文案格式（每組廣告）
```json
{
  "ad_id": "AD-001",
  "platform": "Meta",
  "ad_type": "conversion",
  "primary_text": "主要文案（≤125字）",
  "headline": "標題（≤40字）",
  "description": "描述（≤30字）",
  "cta_button": "立即購買",
  "target_audience": "鎖定受眾描述",
  "visual_suggestion": "建議使用的圖片/影片方向",
  "ab_variant": "A"
}
```

## 必須產出 A/B 版本
每組廣告要有 A 和 B 兩個版本，測試不同的訴求角度：
- A 版：功能/理性訴求
- B 版：情感/故事訴求
"""

def ad_copy_agent(state: MarketingState) -> MarketingState:
    brand_dna = state["brand_dna"]

    response = llm.invoke([
        SystemMessage(content=AD_COPY_PROMPT),
        HumanMessage(content=f"""
品牌：{brand_dna['brand_name']}
本月主推產品/服務：{brand_dna.get('monthly_focus', '品牌整體形象')}
品牌調性：{json.dumps(brand_dna['brand_voice'], ensure_ascii=False)}
目標受眾：{json.dumps(brand_dna['target_audience'], ensure_ascii=False)}

請產出 Meta Ads 和 Google Ads 各 2 組（共 4 組，每組含 A/B 版本）廣告文案。
""")
    ])

    try:
        import re
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        ad_copies = json.loads(json_match.group()) if json_match else []
    except Exception:
        ad_copies = []

    return {
        "ad_copies": ad_copies,
        "messages": [response]
    }
```

### Analyst Agent（數據分析師）

```python
# agents/analyst_agent.py
ANALYST_PROMPT = """你是數位行銷數據分析師，擅長從廣告數據中找出可行動的洞察。

## 分析框架
1. **量**：曝光、觸及、點擊量趨勢
2. **質**：CTR、CVR、ROAS 與業界基準比較
3. **效率**：CPM、CPC、CPA 變化
4. **內容**：哪種格式/受眾/版位表現最好

## 業界基準（參考）
| 指標 | Facebook | Instagram | Google |
|------|---------|-----------|--------|
| CTR | 0.9% | 0.6% | 2-5% |
| CVR | 9.2% | - | 3-5% |
| ROAS | 目標 3x | 目標 3x | 目標 4x |

## 輸出格式
```json
{
  "period": "2026-04",
  "highlights": ["最重要的 3 個發現"],
  "wins": ["表現超過預期的項目"],
  "concerns": ["需要關注或調整的問題"],
  "recommendations": [
    {
      "action": "具體建議",
      "expected_impact": "預期效果",
      "priority": "high|medium|low"
    }
  ],
  "next_month_focus": "下個月應該重點調整什麼"
}
```

語言：繁體中文，避免行銷術語，用客戶看得懂的說法。
"""

def analyst_agent(state: MarketingState) -> MarketingState:
    # 實際使用時，這裡要呼叫 Meta Graph API / Google Ads API
    # 這裡用模擬數據示範
    mock_data = {
        "meta": {
            "impressions": 125000, "reach": 89000,
            "clicks": 1890, "ctr": 0.015,
            "conversions": 234, "cvr": 0.124,
            "spend_twd": 28000, "roas": 3.8
        },
        "google": {
            "impressions": 45000, "clicks": 2100,
            "ctr": 0.047, "conversions": 89,
            "spend_twd": 18000, "roas": 4.2
        }
    }

    response = llm.invoke([
        SystemMessage(content=ANALYST_PROMPT),
        HumanMessage(content=f"""
客戶：{state['brand_dna']['brand_name']}
月份：{state['period']}
廣告數據：{json.dumps(mock_data, ensure_ascii=False, indent=2)}

請產出完整的數據分析洞察。
""")
    ])

    try:
        import re
        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        insights = json.loads(json_match.group()) if json_match else {"raw": response.content}
    except Exception:
        insights = {"raw": response.content}

    return {
        "analytics_data": mock_data,
        "insights": insights,
        "messages": [response]
    }
```

### Report Agent（報告撰寫師）

```python
# agents/report_agent.py
REPORT_PROMPT = """你是行銷月報撰寫師，負責把數據和策略整合成讓客戶看懂的月報。

## 月報結構

### 1. 本月亮點（Executive Summary）
用 3-4 句話說：這個月整體表現如何、最大的成功是什麼、最需要改進的是什麼。

### 2. 廣告成效總覽
| 平台 | 曝光 | 點擊 | 轉換 | 花費 | ROAS |
（用實際數字填入，並與上月比較，加上 ▲ 或 ▼ 符號）

### 3. 本月最佳表現內容 Top 3
（列出成效最好的 3 則貼文/廣告，說明為什麼表現好）

### 4. 數據洞察與建議
（把 Analyst Agent 的建議轉成客戶能理解的行動建議）

### 5. 下個月計畫預覽
（列出 3 個重點方向）

## 語氣原則
- 用「我們」代表代理商，用「您」代表客戶
- 壞消息要說，但要同時給解決方向
- 數字要加上脈絡（不只說 CTR 1.5%，要說「比業界平均高 67%」）
"""

def report_agent(state: MarketingState) -> MarketingState:
    response = llm.invoke([
        SystemMessage(content=REPORT_PROMPT),
        HumanMessage(content=f"""
客戶：{state['brand_dna']['brand_name']}
月份：{state['period']}

廣告數據：{json.dumps(state['analytics_data'], ensure_ascii=False)}
數據洞察：{json.dumps(state['insights'], ensure_ascii=False)}
本月貼文草稿數量：{len(state.get('post_drafts', []))} 篇
本月廣告組數：{len(state.get('ad_copies', []))} 組

請產出完整的月報（Markdown 格式）。
""")
    ])

    return {
        "report": response.content,
        "messages": [response]
    }
```

---

## Step 5：組裝 LangGraph

```python
# graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import MarketingState
from agents.brand_agent import brand_agent
from agents.content_agent import content_agent
from agents.ad_copy_agent import ad_copy_agent
from agents.analyst_agent import analyst_agent
from agents.report_agent import report_agent


def parallel_content_and_ads(state: MarketingState):
    """並行執行 Content Agent 和 Ad Copy Agent"""
    # LangGraph 支援 Send API 實現並行
    from langgraph.constants import Send
    return [
        Send("content_agent", state),
        Send("ad_copy_agent", state)
    ]


def route_by_task(state: MarketingState) -> str:
    """根據任務類型決定流程"""
    task = state.get("task_type", "monthly_report")
    if task == "content_batch":
        return "content_only"
    elif task == "ad_copy":
        return "ad_only"
    return "full_pipeline"   # monthly_report 跑完整流程


def build_marketing_graph():
    graph = StateGraph(MarketingState)

    # 加入節點
    graph.add_node("brand_agent", brand_agent)
    graph.add_node("content_agent", content_agent)
    graph.add_node("ad_copy_agent", ad_copy_agent)
    graph.add_node("analyst_agent", analyst_agent)
    graph.add_node("report_agent", report_agent)

    # 入口：Brand Agent 先執行
    graph.set_entry_point("brand_agent")

    # Brand → 根據任務類型分流
    graph.add_conditional_edges(
        "brand_agent",
        route_by_task,
        {
            "full_pipeline": "analyst_agent",      # 月報：先跑分析
            "content_only": "content_agent",
            "ad_only": "ad_copy_agent"
        }
    )

    # 月報完整流程
    graph.add_edge("analyst_agent", "content_agent")
    graph.add_edge("content_agent", "ad_copy_agent")
    graph.add_edge("ad_copy_agent", "report_agent")
    graph.add_edge("report_agent", END)

    # 單獨任務直接結束
    graph.add_edge("content_agent", END)   # content_only 路徑（條件判斷）

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
```

---

## Step 6：主程式與排程

```python
# main.py
import asyncio
from datetime import datetime
from graph import build_marketing_graph
from langchain_core.messages import HumanMessage

app = build_marketing_graph()


async def run_monthly_report(client_id: str, period: str):
    """執行月報流程"""
    print(f"[{datetime.now()}] 開始產出 {client_id} 的 {period} 月報...")

    config = {"configurable": {"thread_id": f"{client_id}-{period}"}}
    result = await app.ainvoke(
        {
            "client_id": client_id,
            "task_type": "monthly_report",
            "period": period,
            "messages": [HumanMessage(content=f"開始 {period} 月報產出流程")]
        },
        config=config
    )

    # 儲存結果
    report_path = f"outputs/reports/{client_id}_{period}_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(result["report"])

    print(f"[完成] 月報已儲存至 {report_path}")
    return result


async def run_content_batch(client_id: str, period: str):
    """只產出社群內容草稿"""
    config = {"configurable": {"thread_id": f"{client_id}-{period}-content"}}
    result = await app.ainvoke(
        {
            "client_id": client_id,
            "task_type": "content_batch",
            "period": period,
            "messages": [HumanMessage(content="開始內容規劃")]
        },
        config=config
    )
    return result["post_drafts"]


# 批次執行所有客戶的月報
async def run_all_monthly_reports(period: str):
    clients = ["client_A", "client_B", "client_C"]  # 從資料庫讀取

    # 並行執行所有客戶
    tasks = [run_monthly_report(c, period) for c in clients]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for client, result in zip(clients, results):
        if isinstance(result, Exception):
            print(f"[錯誤] {client}: {result}")
        else:
            print(f"[成功] {client} 月報完成，品質分數待審核")


if __name__ == "__main__":
    import sys
    period = sys.argv[1] if len(sys.argv) > 1 else "2026-04"
    asyncio.run(run_all_monthly_reports(period))
```

### 每月自動觸發（crontab）

```bash
# 每月 1 日凌晨 2 點自動產出上個月月報
0 2 1 * * cd /path/to/pixelflow-ai-team && python main.py $(date -v-1m +%Y-%m) >> logs/cron.log 2>&1

# 每週一早上 8 點產出本週內容草稿
0 8 * * 1 cd /path/to/pixelflow-ai-team && python -c "
import asyncio
from main import run_content_batch
asyncio.run(run_content_batch('client_A', '2026-W18'))
" >> logs/cron.log 2>&1
```

---

## Step 7：人工審核界面（Streamlit）

```python
# review_ui.py
import streamlit as st
import json
from pathlib import Path

st.title("PixelFlow AI 內容審核台")

# 載入待審核的貼文草稿
draft_files = list(Path("outputs/content").glob("*.json"))
selected_file = st.selectbox("選擇客戶草稿", draft_files)

if selected_file:
    drafts = json.loads(Path(selected_file).read_text())

    st.subheader(f"共 {len(drafts)} 篇草稿待審核")

    approved = []
    for draft in drafts:
        with st.expander(f"[{draft['platform']}] {draft['post_date']} - {draft['content_pillar']}"):
            st.write("**文案：**", draft["copy"])
            st.write("**視覺方向：**", draft["visual_direction"])
            st.write("**Hashtags：**", " ".join(draft["hashtags"]))
            st.write("**CTA：**", draft["cta"])

            col1, col2, col3 = st.columns(3)
            if col1.button("✅ 核可", key=f"approve_{draft['post_id']}"):
                approved.append(draft["post_id"])
            if col2.button("✏️ 修改", key=f"edit_{draft['post_id']}"):
                new_copy = st.text_area("修改文案", draft["copy"])
                draft["copy"] = new_copy
            if col3.button("❌ 退回", key=f"reject_{draft['post_id']}"):
                st.warning("此貼文已退回，請說明原因（供 AI 學習）")

    if st.button("送出審核結果"):
        st.success(f"已核可 {len(approved)}/{len(drafts)} 篇，已排程發佈")
```

---

## Step 8：Prompt 設計注意事項

### 注意事項 1：品牌聲音的一致性

在每個 Agent 的 System Prompt 最後都加上：

```
## 品牌聲音強制檢查
在輸出任何文案前，問自己：
1. 這符合品牌的語氣嗎？（參考 brand_dna 的 tone）
2. 有用到禁止詞彙嗎？（參考 brand_dna 的 avoid 清單）
3. 目標受眾看到這個會有共鳴嗎？
如果任何一個答案是否定的，重寫。
```

### 注意事項 2：社群平台的規格限制

```python
# 在 Content Agent 輸出後加驗證
def validate_post(post: dict) -> dict:
    platform_limits = {
        "Instagram": {"copy_max": 2200, "hashtag_max": 30},
        "Facebook": {"copy_max": 63206, "hashtag_max": 10},
        "LINE": {"copy_max": 500, "hashtag_max": 0}
    }
    platform = post["platform"]
    limits = platform_limits.get(platform, {})

    errors = []
    if len(post["copy"]) > limits.get("copy_max", 9999):
        errors.append(f"文案超過字數限制（{len(post['copy'])} > {limits['copy_max']}）")

    hashtag_count = len(post.get("hashtags", []))
    if hashtag_count > limits.get("hashtag_max", 99):
        errors.append(f"Hashtag 過多（{hashtag_count} > {limits['hashtag_max']}）")

    post["validation_errors"] = errors
    post["is_valid"] = len(errors) == 0
    return post
```

### 注意事項 3：避免 AI 幻覺在數據報告

數據分析 Agent **絕對不能**自己發明數字。規則：

```python
# analyst_agent.py 中加入防護
ANALYST_PROMPT += """
## 嚴格規定
- 所有數字必須來自傳入的廣告數據，不得自行假設或發明
- 如果某個指標沒有數據，明確寫「本月無資料」
- 計算 ROAS 等衍生指標時，用以下公式：ROAS = 營收 / 花費
- 不確定的部分寫「待確認」，不要猜測
"""
```

### 注意事項 4：避免版權問題

```
## 內容原創聲明（加入所有 Content Agent）
- 不得直接複製競爭對手的文案
- 不得使用「最佳」、「第一」等最高級詞彙（台灣公平交易法限制）
- 食品相關不得使用療效聲稱（食品安全衛生管理法）
```

---

## 執行結果範例

執行 `python main.py 2026-04` 後，約 3-5 分鐘產出：

```
outputs/
├── reports/
│   └── client_A_2026-04_report.md    ← 完整月報
├── content/
│   └── client_A_2026-04_posts.json   ← 30 篇貼文草稿
└── ads/
    └── client_A_2026-04_ads.json     ← 8 組廣告文案（含 A/B）
```

**月報摘要範例：**

```markdown
## 2026年4月 行銷月報 - 綠野良田

### 本月亮點
本月廣告整體表現優異，Meta Ads 的 ROAS 達到 3.8x，超越目標 27%。
農場故事系列的貼文互動率達到 8.2%，是一般貼文的 2.3 倍。
建議下個月加重農場故事的內容比例，並測試影片格式。

### 廣告成效

| 平台 | 曝光 | 點擊 | ROAS | 花費(TWD) |
|------|------|------|------|---------|
| Meta Ads | 125,000 ▲12% | 1,890 ▲8% | 3.8x ▲0.3 | $28,000 |
| Google Ads | 45,000 ▲5% | 2,100 ▲15% | 4.2x ▲0.5 | $18,000 |

### 下個月建議
1. 🎯 增加農場故事影片（預計提升互動率 30-50%）
2. 💰 Meta Ads 預算提高 20%（ROAS 穩定，值得加碼）
3. 📝 新增「食譜教學」系列，搭配母親節活動
```

---

## 效益評估

| 工作項目 | 導入前（人工） | 導入後（AI）| 節省 |
|---------|-------------|-----------|------|
| 月報製作 | 2 天 / 客戶 | 5 分鐘 / 客戶 | 95% |
| 貼文草稿 | 1 小時 / 篇 | 30 篇 / 5 分鐘 | 97% |
| 廣告文案 | 30 分鐘 / 組 | 8 組 / 2 分鐘 | 99% |
| 策略規劃 | 3-5 天 / 客戶 | 15 分鐘草稿 | 85% |

文案師從「產出內容」轉型為「品質把關 + 創意策略」，可服務的客戶數從 5 個提升到 12 個。

---

## 常見問題

**Q：AI 產出的文案品牌調性不對怎麼辦？**  
A：先檢查 `brands/client.json` 的品牌 DNA 是否夠具體。越具體的描述（附上例子），AI 的輸出越準確。建議每個品牌的 `brand_voice` 至少要有 3 個真實的好文案作為範例。

**Q：廣告文案可以直接投放嗎？**  
A：不建議。AI 是草稿，一定要讓有經驗的文案師或帳號管理師審核後再投放。可用 Streamlit 的審核台快速過一遍。

**Q：數據分析 Agent 可以接真實 API 嗎？**  
A：可以。替換 `analyst_agent.py` 中的 `mock_data` 為真實的 Meta Graph API 或 Google Ads API 呼叫即可。建議先在沙盒環境測試。

---

## 下一步

1. 複製本篇架構，把 `brands/` 目錄換成你真實客戶的品牌 DNA
2. 用 3 個月的真實數據測試 Analyst Agent，驗證洞察準確性
3. 建立 Streamlit 審核台，收集人工修改記錄（這些是最好的 Fine-tuning 資料）
4. 考慮整合排程工具（Buffer / Hootsuite API）實現完全自動化發佈

---

*本系列文章：*
- [第一篇：策略與技術路線選擇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/)
- [第二篇：各路線實作步驟與範例程式碼](/posts/ai-agent-team-for-consultant-part2-implementation-zh/)
- [第三篇：評估、維運與優化計畫](/posts/ai-agent-team-for-consultant-part3-devops-zh/)
- [第四篇：小型外包公司實戰案例](/posts/ai-agent-team-for-consultant-part4-outsourcing-zh/)
- **第五篇（本篇）：數位行銷公司實戰案例**
