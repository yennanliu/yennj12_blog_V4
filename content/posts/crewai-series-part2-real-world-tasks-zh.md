---
title: "CrewAI 完全指南（二）：三個真實場景實戰——競情分析、程式碼審查、客服自動化"
date: 2026-05-22T09:00:00+08:00
draft: false
weight: 2
description: "CrewAI 不只是玩具：用三個完整的生產級範例說明如何建立競爭對手情報分析系統、自動化程式碼審查流程、以及智慧客服分類與回覆系統，包含工具整合與 Hierarchical Process 實作。"
categories: ["AI", "Agent", "Engineering", "all"]
tags: ["CrewAI", "Multi-Agent", "AI Automation", "Code Review", "Customer Service", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "35 min"
---

## 前言

[上一篇](/posts/crewai-series-part1-introduction-zh/)我們建立了第一個 CrewAI 應用。

這篇直接進入**真實工作場景**，用三個完整範例展示 CrewAI 能為企業解決什麼問題。每個範例都有完整可執行的程式碼，以及設計上的關鍵決策說明。

---

## 場景一：競爭對手情報分析系統

### 業務背景

產品經理每週需要花 2-3 小時手動追蹤競爭對手動態：新功能、定價變化、媒體報導。這是一個**重複性高、但需要一定判斷力**的工作，非常適合 CrewAI 自動化。

### 系統設計

```
使用者輸入：公司名稱清單 + 分析重點
    ↓
[情報收集員] 搜尋每家公司的最新動態
    ↓
[分析師]     分析收集到的情報，找出威脅與機會
    ↓
[報告撰寫員] 產出格式化的週報，附行動建議
```

### 完整程式碼

```python
import os
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool, ScrapeWebsiteTool
from pydantic import BaseModel
from typing import List

os.environ["OPENAI_API_KEY"] = "your-api-key"
os.environ["SERPER_API_KEY"] = "your-serper-key"

search_tool  = SerperDevTool()
scrape_tool  = ScrapeWebsiteTool()

# ---- Pydantic 模型定義輸出結構 ----

class CompetitorInsight(BaseModel):
    company: str
    recent_news: List[str]
    new_features: List[str]
    pricing_changes: str
    threat_level: str   # low / medium / high
    opportunities: List[str]

class IntelligenceReport(BaseModel):
    summary: str
    competitors: List[CompetitorInsight]
    key_threats: List[str]
    recommended_actions: List[str]

# ---- 定義 Agents ----

intelligence_collector = Agent(
    role="市場情報收集員",
    goal="系統性地收集競爭對手的最新公開資訊，確保資訊的時效性和完整性",
    backstory="""你是一位專業的市場情報分析師，擅長從公開資源中找到有價值的競爭情報。
    你熟悉如何在新聞、官方部落格、社群媒體、產品更新公告中尋找關鍵訊號。
    你注重資料的來源和時效性，只引用近期（3 個月內）的資訊。""",
    tools=[search_tool, scrape_tool],
    llm="gpt-4o-mini",
    verbose=True,
    max_iter=15,
)

market_analyst = Agent(
    role="市場策略分析師",
    goal="分析競爭情報，識別對公司的威脅和市場機會，提供有深度的策略洞察",
    backstory="""你是一位有豐富經驗的市場策略分析師，曾在頂尖顧問公司工作多年。
    你擅長從零散的資訊中找出規律和趨勢，並評估其業務影響。
    你的分析既有宏觀視野，也有具體的行動建議。""",
    verbose=True,
    llm="gpt-4o",
)

report_writer = Agent(
    role="商業報告撰寫員",
    goal="將分析結果轉化為清晰、可行動的週報，讓高層能快速掌握重點",
    backstory="""你是一位資深的商業報告撰寫專家，了解高層主管的閱讀習慣：
    重點先說、數據說話、建議要具體。你的報告簡潔有力，能讓繁忙的決策者
    在 5 分鐘內掌握所有關鍵資訊。""",
    verbose=True,
    llm="gpt-4o",
)

# ---- 定義 Tasks ----

collection_task = Task(
    description="""收集以下競爭對手的最近 4 週內公開資訊：
    競爭對手清單：{competitors}
    分析重點：{focus_areas}

    對每家公司，請搜尋並整理：
    1. 重要新聞或公告（含日期）
    2. 新功能或產品更新
    3. 定價或商業模式變化
    4. 重要人事異動
    5. 融資或商業合作消息

    每個資訊請附上來源 URL 和日期。""",

    expected_output="""按公司分段整理的原始情報，每段包含：
    - 公司名稱
    - 各類別的情報條目（含來源和日期）
    格式：Markdown""",

    agent=intelligence_collector,
)

analysis_task = Task(
    description="""根據情報收集員提供的資料，進行深度市場分析。

    分析維度：
    1. 威脅評估：哪些競爭對手動作對我方業務威脅最大？為什麼？
    2. 機會識別：競爭對手的哪些弱點或空白我方可以利用？
    3. 趨勢分析：這些動態反映了什麼市場趨勢？
    4. 優先級排序：哪些動態需要我方立即回應？

    我方公司背景：{our_company_context}""",

    expected_output="""詳細分析報告，包含：
    - 每家競爭對手的威脅等級（高/中/低）及理由
    - Top 3 識別出的市場機會
    - 需要立即回應的事項（含時間緊迫性）
    - 長期策略影響評估
    格式：Markdown""",

    agent=market_analyst,
    context=[collection_task],
)

reporting_task = Task(
    description="""根據分析結果，撰寫一份適合高層閱讀的競爭情報週報。

    報告結構：
    1. 執行摘要（100 字內，本週最重要的 3 件事）
    2. 競爭對手動態概覽（每家一段）
    3. 威脅與機會矩陣
    4. 建議行動清單（按優先級排序，每項附建議時程）
    5. 下週需持續觀察的事項

    語氣：專業、簡潔、以行動為導向""",

    expected_output="""完整的競爭情報週報（Markdown 格式），
    可直接複製至 Notion 或 Confluence 等內部系統。
    同時提供一份 JSON 格式的結構化資料，供後續自動化處理。""",

    agent=report_writer,
    context=[analysis_task],
    output_pydantic=IntelligenceReport,  # 結構化輸出
)

# ---- 建立並執行 Crew ----

intelligence_crew = Crew(
    agents=[intelligence_collector, market_analyst, report_writer],
    tasks=[collection_task, analysis_task, reporting_task],
    process=Process.sequential,
    memory=True,
    verbose=True,
)

result = intelligence_crew.kickoff(inputs={
    "competitors": "Notion, Confluence, Coda",
    "focus_areas": "新功能、定價、AI 整合",
    "our_company_context": "中型 SaaS 公司，主要產品是企業知識管理系統，目標客群是 500-5000 人的科技公司",
})

# 存取結構化輸出
report: IntelligenceReport = result.pydantic
print(f"威脅摘要：{report.summary}")
print(f"關鍵威脅：{report.key_threats}")
print(f"建議行動：{report.recommended_actions}")
```

### 關鍵設計決策

**為什麼用三個 Agent 而非一個？**

一個「萬能」的 Agent 往往表現平庸：收集資料時不夠系統，分析時受資料蒐集的角度影響，撰寫時沒有針對受眾優化。分三個 Agent 讓每個步驟都能有「專業思維」。

**為什麼用 `output_pydantic`？**

結構化輸出讓你可以：
- 自動存到資料庫
- 傳給下游系統（Slack Bot、Dashboard）
- 驗證輸出的完整性

---

## 場景二：自動化程式碼審查系統

### 業務背景

工程團隊的 PR review 常常是瓶頸：資深工程師花大量時間在基本的程式碼品質問題上（命名、安全性、效能），沒時間做架構層級的討論。

### 系統設計：Hierarchical Process

這個範例展示 **Hierarchical Process**（階層式流程），由一個 Manager Agent 動態分配任務：

```
PR 內容（diff）
    ↓
[Review Manager]  分析 PR 性質，決定要召喚哪些專家
    ├── [安全性審查員]  檢查 SQL injection、XSS、密鑰洩漏等
    ├── [效能審查員]    檢查 N+1 查詢、記憶體洩漏、演算法複雜度
    └── [程式碼品質員]  檢查命名規範、重複程式碼、測試覆蓋率
    ↓
[Review Manager]  彙整結果，產出 PR review 留言
```

```python
import os
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from pydantic import BaseModel
from typing import List, Literal

os.environ["OPENAI_API_KEY"] = "your-api-key"

# ---- 自訂工具：讀取 PR Diff ----

@tool("讀取 PR Diff")
def read_pr_diff(pr_content: str) -> str:
    """讀取並格式化 PR 的 diff 內容，便於審查。輸入完整的 diff 文字。"""
    # 實際上可以呼叫 GitHub API：
    # import requests
    # response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
    #                         headers={"Authorization": f"token {GITHUB_TOKEN}",
    #                                  "Accept": "application/vnd.github.v3.diff"})
    # return response.text
    return f"PR Diff 內容：\n{pr_content}"

# ---- Pydantic 模型 ----

class ReviewComment(BaseModel):
    file: str
    line: int
    severity: Literal["blocker", "major", "minor", "suggestion"]
    category: Literal["security", "performance", "quality", "style"]
    comment: str
    suggestion: str = ""

class PRReview(BaseModel):
    overall_assessment: Literal["approve", "request_changes", "comment"]
    summary: str
    comments: List[ReviewComment]
    must_fix_before_merge: List[str]

# ---- 定義 Agents ----

security_reviewer = Agent(
    role="資安審查工程師",
    goal="找出程式碼中所有潛在的安全性漏洞，絕不放過任何風險",
    backstory="""你是一位有 CISSP 認證的資安工程師，專注於 AppSec。
    你熟悉 OWASP Top 10，能快速識別 SQL Injection、XSS、CSRF、
    不安全的密鑰管理、不安全的反序列化等問題。
    你的審查標準非常嚴格：寧可 false positive，也不放過真正的漏洞。""",
    verbose=True,
    llm="gpt-4o",
)

performance_reviewer = Agent(
    role="效能優化工程師",
    goal="識別程式碼中的效能問題，確保系統在高負載下仍能穩定運作",
    backstory="""你是一位系統效能專家，有豐富的大規模系統調優經驗。
    你特別擅長找出 N+1 查詢問題、不必要的計算複雜度、記憶體洩漏、
    阻塞式 I/O 等常見效能陷阱。你的改善建議總是附有預期的效能提升數據。""",
    verbose=True,
    llm="gpt-4o",
)

quality_reviewer = Agent(
    role="程式碼品質工程師",
    goal="確保程式碼符合最佳實踐，具有良好的可讀性、可測試性和可維護性",
    backstory="""你是一位資深工程師，深信「程式碼是寫給人看的，順便讓機器執行」。
    你特別重視命名清晰度、函式的單一職責、適當的抽象層次、測試覆蓋率，
    以及文件的完整性。你的 review 風格建設性，會附上具體的改進範例。""",
    verbose=True,
    llm="gpt-4o-mini",
)

# ---- 定義 Tasks（Hierarchical 模式下任務分配更動態）----

security_task = Task(
    description="""審查以下程式碼的安全性：

{pr_diff}

重點檢查：
1. SQL Injection / NoSQL Injection
2. XSS（跨站腳本攻擊）
3. 不安全的輸入驗證
4. 硬編碼的密鑰或憑證
5. 不安全的隨機數生成
6. 未授權的資源存取
7. 敏感資料的不當暴露""",

    expected_output="""資安審查結果，格式如下：
    每個問題：檔案名稱、行號、嚴重程度（blocker/major/minor）、說明、修復建議
    如果沒有發現安全問題，明確說明「無安全疑慮」。""",

    agent=security_reviewer,
    tools=[read_pr_diff],
)

performance_task = Task(
    description="""審查以下程式碼的效能問題：

{pr_diff}

重點檢查：
1. 資料庫查詢效率（N+1 問題、缺少 index、不必要的 JOIN）
2. 演算法複雜度（是否有 O(n²) 以上的不必要操作）
3. 記憶體使用（大量資料是否有分頁或串流處理）
4. 快取機會（哪些計算可以快取？）
5. 非同步處理（阻塞式 I/O 是否可改為非同步）""",

    expected_output="""效能審查結果，每個問題附：
    - 問題描述
    - 預估的效能影響（例如：在 10,000 筆資料下可能造成 N 次查詢）
    - 具體修改建議（附程式碼範例）""",

    agent=performance_reviewer,
    tools=[read_pr_diff],
)

quality_task = Task(
    description="""審查以下程式碼的品質問題：

{pr_diff}

重點檢查：
1. 命名清晰度（變數、函式、類別名稱是否表達意圖）
2. 函式大小和職責（單一職責原則）
3. 重複程式碼（DRY 原則）
4. 測試覆蓋（新邏輯是否有對應測試？邊界條件是否覆蓋？）
5. 錯誤處理（是否有適當的 exception handling？）
6. 文件和註解（複雜邏輯是否有說明？）""",

    expected_output="""程式碼品質審查結果，每個問題附：
    - 問題類型和位置
    - 為什麼這是個問題
    - 建議的改進方式（附重構後的程式碼片段）""",

    agent=quality_reviewer,
    tools=[read_pr_diff],
)

summary_task = Task(
    description="""整合所有審查員的結果，產出一份完整的 PR Review 留言。

    整合原則：
    1. 按嚴重程度排序（blocker → major → minor → suggestion）
    2. 去除重複或矛盾的意見
    3. 給出整體建議（Approve / Request Changes / Comment）
    4. 列出合併前必須修復的項目（blockers）
    5. 語氣要建設性，避免負面措辭

    整體評估標準：
    - 有 blocker → Request Changes
    - 只有 major，且超過 3 個 → Request Changes
    - 其他情況 → Comment（可以合併但建議修改）""",

    expected_output="""可直接貼到 GitHub PR 的 review 留言（Markdown 格式），以及結構化的 JSON 輸出。
    留言包含：整體評估、逐條問題清單、必須修復項目、鼓勵性結語。""",

    agent=quality_reviewer,  # 品質工程師負責彙整，邏輯最合適
    context=[security_task, performance_task, quality_task],
    output_pydantic=PRReview,
)

# ---- 建立 Crew（Hierarchical 模式）----

code_review_crew = Crew(
    agents=[security_reviewer, performance_reviewer, quality_reviewer],
    tasks=[security_task, performance_task, quality_task, summary_task],
    process=Process.sequential,  # 也可以改成 hierarchical 讓 manager 動態分配
    memory=True,
    verbose=True,
)

# ---- 執行 ----

sample_pr_diff = """
diff --git a/app/models/user.py b/app/models/user.py
--- a/app/models/user.py
+++ b/app/models/user.py
@@ -15,6 +15,18 @@ class UserService:
+    def get_user_by_email(self, email: str):
+        query = f"SELECT * FROM users WHERE email = '{email}'"
+        return self.db.execute(query)
+
+    def get_user_posts(self, user_id: int):
+        user = self.db.query(User).filter_by(id=user_id).first()
+        posts = []
+        for post_id in user.post_ids:
+            post = self.db.query(Post).filter_by(id=post_id).first()
+            posts.append(post)
+        return posts
+
+    def reset_password(self, user_id: int, new_password: str):
+        secret_key = "hardcoded_secret_123"
+        token = jwt.encode({"user_id": user_id}, secret_key)
+        # TODO: send email
+        return token
"""

result = code_review_crew.kickoff(inputs={"pr_diff": sample_pr_diff})

review: PRReview = result.pydantic
print(f"\n整體評估：{review.overall_assessment}")
print(f"必須修復：{review.must_fix_before_merge}")
```

**這段 `sample_pr_diff` 埋了三個明顯問題（故意的）：**
1. SQL Injection（字串拼接）
2. N+1 查詢（迴圈查資料庫）
3. 硬編碼 secret key

CrewAI 的 Security Reviewer 和 Performance Reviewer 應該都能發現。

---

## 場景三：智慧客服分類與回覆系統

### 業務背景

客服團隊每天收到大量工單，需要：
1. 判斷問題類型（技術問題、帳單、功能諮詢、投訴）
2. 評估緊急程度
3. 草擬初步回覆
4. 決定是否需要升級給人工客服

這是一個典型的**分類 + 生成**任務，非常適合 CrewAI。

```python
import os
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from pydantic import BaseModel
from typing import Literal, Optional

os.environ["OPENAI_API_KEY"] = "your-api-key"

# ---- 自訂工具 ----

@tool("查詢客戶資料")
def get_customer_info(customer_id: str) -> str:
    """根據客戶 ID 查詢客戶的訂閱方案、使用狀況和歷史工單。"""
    # 實際上會查資料庫
    mock_data = {
        "C001": {
            "name": "王小明",
            "plan": "Pro",
            "since": "2023-06",
            "open_tickets": 0,
            "mrr": 2990,
        }
    }
    info = mock_data.get(customer_id, {"name": "未知客戶"})
    return str(info)


@tool("查詢知識庫")
def search_knowledge_base(query: str) -> str:
    """搜尋客服知識庫，找出常見問題的標準解答。"""
    kb = {
        "忘記密碼": "請至登入頁面點選「忘記密碼」，系統會寄送重設連結到您的註冊信箱。",
        "升級方案": "您可以在帳號設定 → 訂閱計畫 頁面選擇升級，升級立即生效，費用按比例計算。",
        "API 限流": "免費方案每分鐘 60 次請求，Pro 方案每分鐘 1000 次。超過限制會回傳 429 錯誤。",
        "退款政策": "訂閱費用不提供退款，但可在下個計費週期前取消訂閱。",
    }
    for key, answer in kb.items():
        if key in query:
            return answer
    return "知識庫中未找到完全匹配的答案，請根據上下文判斷。"

# ---- Pydantic 模型 ----

class TicketClassification(BaseModel):
    category: Literal["technical", "billing", "feature_request", "complaint", "general"]
    urgency: Literal["critical", "high", "medium", "low"]
    sentiment: Literal["angry", "frustrated", "neutral", "satisfied"]
    needs_human: bool
    escalation_reason: Optional[str] = None

class CustomerReply(BaseModel):
    classification: TicketClassification
    draft_reply: str
    internal_note: str
    suggested_assignee: Literal["tier1", "tier2", "engineering", "billing_team", "manager"]

# ---- 定義 Agents ----

classifier = Agent(
    role="客服工單分類專家",
    goal="精確判斷每張工單的類型、緊急程度和客戶情緒，為後續處理提供準確的基礎",
    backstory="""你是一位有多年 SaaS 客服經驗的專家，能快速理解客戶的真實需求。
    你特別擅長識別客戶留言背後的情緒和意圖——有時候客戶說「有個小問題」，
    實際上可能是非常緊急的生產事故。你的分類結果直接影響後續的服務品質。""",
    tools=[get_customer_info],
    llm="gpt-4o-mini",
    verbose=True,
)

reply_drafter = Agent(
    role="客服回覆撰寫專員",
    goal="根據工單分類和客戶背景，撰寫個性化、有同理心且解決問題的回覆草稿",
    backstory="""你是一位出色的客服文案專家，懂得在專業和親切之間取得平衡。
    你的回覆永遠先表達理解，再解決問題，最後確認客戶是否滿意。
    你會根據客戶的訂閱方案調整服務態度——高付費客戶值得更個性化的關注。
    你熟悉公司所有產品功能，回覆精確且有幫助。""",
    tools=[search_knowledge_base, get_customer_info],
    llm="gpt-4o",
    verbose=True,
)

# ---- 定義 Tasks ----

classification_task = Task(
    description="""分析以下客服工單，進行精確分類：

    客戶 ID：{customer_id}
    工單內容：
    ---
    {ticket_content}
    ---

    分類維度：
    1. 問題類型（技術問題/帳單/功能請求/投訴/一般諮詢）
    2. 緊急程度（critical=生產中斷/high=功能無法使用/medium=影響工作流程/low=一般問題）
    3. 客戶情緒（生氣/沮喪/中立/滿意）
    4. 是否需要人工介入（判斷依據：問題複雜度、客戶情緒、客戶價值）

    請先查詢客戶資料，了解客戶背景再做判斷。""",

    expected_output="""工單分類結果（JSON 格式），包含：
    - category, urgency, sentiment, needs_human, escalation_reason（如需升級）""",

    agent=classifier,
    output_pydantic=TicketClassification,
)

reply_task = Task(
    description="""根據工單分類結果，撰寫客服回覆草稿。

    客戶 ID：{customer_id}
    原始工單：{ticket_content}

    回覆要求：
    1. 先查詢知識庫，找出準確的解決方案
    2. 如果是技術問題：提供清楚的解決步驟
    3. 如果是帳單問題：解釋清楚，必要時提供補償方案
    4. 如果客戶情緒激動：先同理，再解決，不要急著給解決方案
    5. 如果需要升級：告知客戶會有專人跟進，給予時間預期

    同時撰寫一份給內部團隊的備注，說明此工單的背景和建議的處理方式。
    並決定應分配給哪個團隊（tier1/tier2/engineering/billing_team/manager）。""",

    expected_output="""包含三個部分：
    1. 給客戶的回覆草稿（繁體中文，友善專業的語氣）
    2. 給客服團隊的內部備注（說明背景、建議、注意事項）
    3. 建議分配的團隊""",

    agent=reply_drafter,
    context=[classification_task],
    output_pydantic=CustomerReply,
)

# ---- 建立並執行 ----

support_crew = Crew(
    agents=[classifier, reply_drafter],
    tasks=[classification_task, reply_task],
    process=Process.sequential,
    memory=True,
    verbose=True,
)

# 測試案例 1：技術問題（情緒中立）
result = support_crew.kickoff(inputs={
    "customer_id": "C001",
    "ticket_content": """
    你好，我在用你們的 API 時一直收到 429 錯誤，
    我的應用程式每分鐘大概發送 800 個請求，請問這樣應該沒有問題吧？
    謝謝
    """,
})

reply: CustomerReply = result.pydantic
print(f"\n類型：{reply.classification.category}")
print(f"緊急程度：{reply.classification.urgency}")
print(f"需要人工：{reply.classification.needs_human}")
print(f"\n回覆草稿：\n{reply.draft_reply}")
print(f"\n內部備注：{reply.internal_note}")

# 測試案例 2：憤怒的客戶
result2 = support_crew.kickoff(inputs={
    "customer_id": "C001",
    "ticket_content": """
    這已經是這個月第三次服務中斷了！！！
    我有客戶正在等這份報告，你們的系統卻完全無法使用！
    我每個月付 2990 元，這就是你們給我的服務品質嗎？？
    我要求退款！！
    """,
})
```

---

## 最佳實踐小結

從這三個場景中，整理幾個設計原則：

### Agent 設計原則

```
✅ 每個 Agent 只做一件事，做精
✅ backstory 要描述具體的「工作習慣」，不只是「擅長什麼」
✅ 對不需要搜尋的 Agent，不要給 tools（減少不必要的工具呼叫）
✅ 對品質要求高的任務，用更強的模型（gpt-4o）；對分類等任務，用輕量模型
```

### Task 設計原則

```
✅ description 裡列出具體的 checklist，而不是模糊的方向
✅ expected_output 要說清楚格式和長度要求
✅ 善用 output_pydantic 強制結構化輸出
✅ 用 context=[task1, task2] 明確定義 Task 間的依賴
```

### 流程設計原則

```
✅ 線性流程 → Process.sequential（大多數場景）
✅ 需要動態分工 → Process.hierarchical + manager_llm
✅ 有獨立子任務可並行 → async_execution=True
✅ 一定要設 memory=True（讓 Agent 能參考過去的上下文）
```

---

## 小結

這篇用三個真實場景展示了 CrewAI 的生產級應用：

- **競情分析**：多 Agent 協作 + Pydantic 結構化輸出
- **程式碼審查**：多個專業審查員並行 + 最終彙整
- **客服自動化**：分類 + 個性化回覆 + 動態升級機制

下一篇我們進入進階技術：**CrewAI Flows（事件驅動工作流程）、Long-term Memory、以及如何把 CrewAI 部署到生產環境**。

---

**系列導覽**

- [第一篇](/posts/crewai-series-part1-introduction-zh/)：入門與核心概念
- **第二篇（本篇）**：真實場景實戰——競情分析、程式碼審查、客服自動化
- [第三篇](/posts/crewai-series-part3-advanced-flows-zh/)：進階技巧——Flows、Memory、結構化輸出與生產部署
