---
title: "CrewAI 完全指南（三）：進階技巧——Flows 事件驅動、Memory 記憶體、與生產部署"
date: 2026-05-23T09:00:00+08:00
draft: false
weight: 3
description: "CrewAI 進階篇：用 @start/@listen/@router 建立事件驅動的複雜工作流程、三種記憶體機制的實際應用、錯誤處理與成本控制，以及如何把 CrewAI Crew 包成 API 服務部署到生產環境。"
categories: ["AI", "Agent", "Engineering", "all"]
tags: ["CrewAI", "Flows", "Memory", "Multi-Agent", "Production", "FastAPI", "Python", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "35 min"
---

## 前言

前兩篇建立了 CrewAI 的基礎和實戰應用。  
這篇是進階篇，涵蓋讓 CrewAI 真正走到生產環境的關鍵技術：

1. **Flows**：當 Crew 的線性流程不夠用時
2. **Memory 記憶體**：讓 Agent 記得過去的對話和經驗
3. **錯誤處理與成本控制**：生產環境的必要設計
4. **部署**：把 CrewAI 包成 API 服務

---

## Part 1：CrewAI Flows——事件驅動的複雜工作流程

### Crew 的限制

`Process.sequential` 是線性的：任務一個接一個執行。但真實世界的工作流程往往需要：

- **條件分支**：根據分析結果走不同的路徑
- **迴圈**：重複執行直到滿足條件
- **平行執行**：多個 Crew 同時跑，最後彙整
- **狀態管理**：跨步驟保存和傳遞複雜的狀態

**CrewAI Flows** 就是為了處理這些複雜場景設計的。

### Flow 的三個核心 Decorator

```python
from crewai.flow.flow import Flow, listen, start, router
from pydantic import BaseModel

class MyFlow(Flow):

    @start()
    def step_one(self):
        """Flow 的入口點，Flow 啟動時執行"""
        return "step one result"

    @listen(step_one)
    def step_two(self, step_one_output):
        """當 step_one 完成後自動觸發，可以接收上一步的輸出"""
        return f"processed: {step_one_output}"

    @router(step_two)
    def decide_next(self, step_two_output):
        """根據 step_two 的輸出決定下一步走哪條路"""
        if "error" in step_two_output:
            return "error_path"
        return "success_path"

    @listen("success_path")
    def handle_success(self):
        return "成功！"

    @listen("error_path")
    def handle_error(self):
        return "處理錯誤..."
```

### 狀態管理：用 Pydantic 定義 Flow 的全域狀態

```python
from crewai.flow.flow import Flow, listen, start, router
from pydantic import BaseModel
from typing import Optional, List

class ContentPipelineState(BaseModel):
    """Flow 的全域狀態，所有步驟都可以讀寫"""
    topic: str = ""
    research_done: bool = False
    research_notes: str = ""
    draft: str = ""
    quality_score: float = 0.0
    revision_count: int = 0
    final_article: str = ""
    publish_ready: bool = False


class ContentPipelineFlow(Flow[ContentPipelineState]):
    """
    完整的內容生產 Flow：研究 → 撰寫 → 品質評估 → 修訂（如需要）→ 發布
    展示條件分支和迴圈的使用
    """

    @start()
    def initialize(self):
        """初始化，設定主題"""
        print(f"🚀 開始內容生產流程，主題：{self.state.topic}")

    @listen(initialize)
    def run_research_crew(self):
        """呼叫研究 Crew"""
        from crewai import Agent, Task, Crew, Process
        from crewai_tools import SerperDevTool

        researcher = Agent(
            role="研究員",
            goal="深入研究指定主題",
            backstory="經驗豐富的內容研究員",
            tools=[SerperDevTool()],
            llm="gpt-4o-mini",
        )

        research_task = Task(
            description=f"研究 {self.state.topic}，產出詳細的研究筆記",
            expected_output="詳細的研究筆記，Markdown 格式",
            agent=researcher,
        )

        crew = Crew(agents=[researcher], tasks=[research_task])
        result = crew.kickoff()

        # 把結果存到 Flow 的 state
        self.state.research_notes = result.raw
        self.state.research_done = True
        print(f"✅ 研究完成，約 {len(result.raw)} 字")

    @listen(run_research_crew)
    def run_writing_crew(self):
        """呼叫撰寫 Crew"""
        from crewai import Agent, Task, Crew

        writer = Agent(
            role="部落客",
            goal="撰寫引人入勝的文章",
            backstory="擅長技術寫作的部落客",
            llm="gpt-4o",
        )

        writing_task = Task(
            description=f"""根據以下研究筆記，撰寫一篇部落格文章：

{self.state.research_notes}

主題：{self.state.topic}
要求：1200-1800 字，Markdown 格式""",
            expected_output="完整的部落格文章，Markdown 格式",
            agent=writer,
        )

        crew = Crew(agents=[writer], tasks=[writing_task])
        result = crew.kickoff()
        self.state.draft = result.raw
        print(f"✅ 草稿撰寫完成")

    @listen(run_writing_crew)
    def evaluate_quality(self):
        """用 LLM 評估文章品質，決定是否需要修訂"""
        import openai
        import json

        client = openai.OpenAI()
        prompt = f"""請評估以下文章的品質（0-10 分），並提供評分理由。

文章：
{self.state.draft[:3000]}...

以 JSON 格式輸出：{{"score": 7.5, "reasons": ["優點1", "缺點1"], "suggestions": ["改進建議1"]}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        evaluation = json.loads(response.choices[0].message.content)
        self.state.quality_score = evaluation["score"]
        print(f"📊 品質評分：{self.state.quality_score}/10")
        return evaluation

    @router(evaluate_quality)
    def check_quality(self, evaluation):
        """根據品質分數決定下一步"""
        if self.state.quality_score >= 8.0:
            return "publish"
        elif self.state.revision_count >= 2:
            # 最多修訂 2 次，防止無限迴圈
            print("⚠️ 已達最大修訂次數，直接發布")
            return "publish"
        else:
            return "revise"

    @listen("revise")
    def run_revision(self):
        """修訂文章（迴圈：可能執行多次）"""
        self.state.revision_count += 1
        print(f"🔄 開始第 {self.state.revision_count} 次修訂...")

        import openai
        client = openai.OpenAI()

        prompt = f"""請根據以下改進建議，修訂這篇文章。

原文（前 2000 字）：
{self.state.draft[:2000]}

改進方向：品質分數 {self.state.quality_score}/10，需要提升至 8 分以上。
請大幅改善文章結構、流暢度和資訊深度。

輸出修訂後的完整文章："""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        self.state.draft = response.choices[0].message.content

        # 修訂後重新評估（回到 evaluate_quality）
        self.evaluate_quality()

    @listen("publish")
    def finalize_and_publish(self):
        """最終發布步驟"""
        self.state.final_article = self.state.draft
        self.state.publish_ready = True
        print(f"🎉 文章發布就緒！最終品質分數：{self.state.quality_score}/10")

        # 實際上可以呼叫 CMS API 或寫入資料庫
        with open(f"output_{self.state.topic[:20]}.md", "w", encoding="utf-8") as f:
            f.write(self.state.final_article)


# 執行 Flow
flow = ContentPipelineFlow()
flow.state.topic = "量子計算的商業應用"
flow.kickoff()

print(f"\n總修訂次數：{flow.state.revision_count}")
print(f"最終品質分數：{flow.state.quality_score}")
print(f"文章已就緒：{flow.state.publish_ready}")
```

### 平行執行多個 Crew

```python
class ParallelResearchFlow(Flow):
    """同時研究多個子主題，最後彙整"""

    @start()
    def begin(self):
        self.subtopics = ["技術面", "市場面", "法規面"]

    @listen(begin)
    def research_technical(self):
        """研究技術面（與其他研究平行執行）"""
        return self._run_research_crew("技術面")

    @listen(begin)
    def research_market(self):
        """與 research_technical 同時執行"""
        return self._run_research_crew("市場面")

    @listen(begin)
    def research_regulatory(self):
        """與前兩個同時執行"""
        return self._run_research_crew("法規面")

    @listen(research_technical, research_market, research_regulatory)
    def synthesize(self, tech, market, reg):
        """等所有研究完成後彙整"""
        print("所有子研究完成，開始彙整...")
        # 整合三個研究結果

    def _run_research_crew(self, aspect: str) -> str:
        # ... 實作 Crew 邏輯
        return f"{aspect} 的研究結果"
```

---

## Part 2：Memory 記憶體——讓 Agent 記得歷史

CrewAI 提供三種記憶機制，各有不同的用途：

### 記憶體類型對比

| 類型 | 作用範圍 | 持久性 | 適用場景 |
|------|---------|-------|---------|
| **Short-term Memory** | 單次 Crew 執行內 | 否 | 任務間傳遞上下文 |
| **Long-term Memory** | 跨多次執行 | 是（存 DB） | 記住用戶偏好、歷史互動 |
| **Entity Memory** | 特定實體的知識 | 是 | 記住「關於 X 公司的所有事情」 |

### 啟用完整記憶體

```python
from crewai import Crew, Process
from crewai.memory import LongTermMemory, ShortTermMemory, EntityMemory
from crewai.memory.storage.ltm_sqlite_storage import LTMSQLiteStorage

crew = Crew(
    agents=[...],
    tasks=[...],
    process=Process.sequential,

    # 啟用三種記憶體
    memory=True,

    # Long-term memory 存到本地 SQLite（也可以換成 PostgreSQL）
    long_term_memory=LongTermMemory(
        storage=LTMSQLiteStorage(db_path="./crew_memory.db")
    ),

    # Short-term memory 用向量 DB 儲存（方便語意搜尋）
    short_term_memory=ShortTermMemory(),

    # Entity memory 追蹤特定實體
    entity_memory=EntityMemory(),

    verbose=True,
)
```

### Long-term Memory 的實際效果

```python
# 第一次執行
result1 = crew.kickoff(inputs={
    "customer_id": "C001",
    "question": "我想了解你們的 Enterprise 方案"
})
# Agent 記錄：C001 對 Enterprise 方案有興趣

# 第二次執行（一週後）
result2 = crew.kickoff(inputs={
    "customer_id": "C001",
    "question": "你們的 API 有沒有限制？"
})
# Agent 自動回憶上次互動：「這位客戶上次詢問過 Enterprise 方案，
#  這次問 API 限制，可能在評估升級的可行性」
# → 回覆會更有針對性，自動帶入 Enterprise 方案的 API 限制資訊
```

### 自訂知識庫（Knowledge Sources）

除了 Memory，CrewAI 也支援靜態知識庫（公司文件、產品手冊）：

```python
from crewai import Agent, Crew
from crewai.knowledge.source.pdf_knowledge_source import PDFKnowledgeSource
from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource
from crewai.knowledge.source.string_knowledge_source import StringKnowledgeSource

# 從不同來源建立知識庫
product_manual = PDFKnowledgeSource(file_paths=["product_manual_v3.pdf"])
faq_doc = TextFileKnowledgeSource(file_paths=["faq.md", "pricing.md"])
company_info = StringKnowledgeSource(content="""
    公司名稱：TechCorp
    成立年份：2020
    主要產品：企業知識管理系統
    聯絡信箱：support@techcorp.com
    企業方案聯絡：sales@techcorp.com
""")

# 把知識庫給 Crew
support_crew = Crew(
    agents=[support_agent],
    tasks=[support_task],
    knowledge_sources=[product_manual, faq_doc, company_info],
    memory=True,
)
```

---

## Part 3：錯誤處理與成本控制

### 錯誤處理

CrewAI 的工具呼叫或 LLM 呼叫可能失敗。以下是幾個關鍵的防護設計：

```python
from crewai import Agent, Crew
from crewai.tools import tool
import time
import logging

logger = logging.getLogger(__name__)

# 工具層面的錯誤處理
@tool("外部 API 查詢")
def call_external_api(query: str) -> str:
    """呼叫外部 API 查詢資料，有自動重試機制。"""
    import requests

    for attempt in range(3):
        try:
            response = requests.get(
                "https://api.example.com/data",
                params={"q": query},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["result"]
        except requests.Timeout:
            if attempt < 2:
                wait = 2 ** attempt  # 指數退避：1s, 2s
                logger.warning(f"API timeout，{wait}s 後重試（第 {attempt+1} 次）")
                time.sleep(wait)
            else:
                return "API 查詢逾時，請稍後再試。"
        except requests.HTTPError as e:
            return f"API 錯誤：{e.response.status_code}"
        except Exception as e:
            logger.error(f"未預期的錯誤：{e}")
            return f"查詢失敗：{str(e)}"


# Crew 層面的錯誤處理
def run_crew_safely(crew: Crew, inputs: dict, max_retries: int = 2):
    """帶重試的安全 Crew 執行器"""
    for attempt in range(max_retries + 1):
        try:
            result = crew.kickoff(inputs=inputs)
            return result
        except Exception as e:
            logger.error(f"Crew 執行失敗（第 {attempt+1} 次）：{e}")
            if attempt < max_retries:
                logger.info(f"30 秒後重試...")
                time.sleep(30)
            else:
                raise RuntimeError(f"Crew 在 {max_retries+1} 次嘗試後仍失敗：{e}")
```

### 成本控制

LLM API 費用可能是生產環境最大的支出之一。以下是幾個控制策略：

```python
from crewai import Agent, Crew
import os

# 策略 1：根據任務複雜度選擇模型
fast_agent = Agent(
    role="分類員",
    goal="快速分類工單類型",
    backstory="...",
    llm="gpt-4o-mini",    # 簡單分類用輕量模型（便宜 10-30 倍）
    max_iter=5,            # 限制最大迭代次數
)

deep_agent = Agent(
    role="策略分析師",
    goal="深度分析市場情報",
    backstory="...",
    llm="gpt-4o",         # 複雜分析用強模型
    max_iter=10,
)

# 策略 2：設定 max_rpm 避免 API 頻率限制和突發費用
rate_limited_agent = Agent(
    role="批次處理員",
    goal="處理大量資料",
    backstory="...",
    llm="gpt-4o-mini",
    max_rpm=10,    # 每分鐘最多 10 個請求，避免費用衝高
)

# 策略 3：啟用工具呼叫快取（相同輸入不重複呼叫）
cached_crew = Crew(
    agents=[...],
    tasks=[...],
    cache=True,    # 對相同的工具輸入快取結果
)

# 策略 4：監控 token 用量
result = crew.kickoff(inputs={...})
usage = result.token_usage
print(f"本次執行：")
print(f"  輸入 tokens：{usage.prompt_tokens}")
print(f"  輸出 tokens：{usage.completion_tokens}")
print(f"  總計：{usage.total_tokens}")
# 假設 gpt-4o-mini: $0.15/1M input, $0.60/1M output
cost_estimate = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) / 1_000_000
print(f"  估計費用：${cost_estimate:.4f} USD")
```

### 使用 Claude 作為 LLM 後端

CrewAI 支援多種 LLM，包含 Anthropic Claude：

```python
import os
from crewai import Agent

os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-key"

# 使用 Claude Sonnet（性價比高）
analyst = Agent(
    role="資深分析師",
    goal="提供深度的市場分析",
    backstory="有豐富分析經驗的顧問",
    llm="anthropic/claude-sonnet-4-6",  # CrewAI 支援 LiteLLM 格式
)

# 使用 Claude Haiku（輕量任務）
classifier = Agent(
    role="分類員",
    goal="快速分類任務",
    backstory="...",
    llm="anthropic/claude-haiku-4-5-20251001",
)
```

---

## Part 4：部署到生產環境

### 用 FastAPI 包裝 CrewAI

把 Crew 變成一個可以被其他系統呼叫的 REST API：

```python
# main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio
import uuid
from datetime import datetime

# 你的 Crew 定義（從前面章節）
from crews.content_crew import ContentCrew
from crews.support_crew import SupportCrew

app = FastAPI(title="CrewAI API", version="1.0.0")

# 儲存任務狀態（生產環境用 Redis 或 DB）
jobs: dict[str, dict] = {}


class ContentRequest(BaseModel):
    topic: str
    language: str = "zh-TW"
    target_length: str = "medium"  # short / medium / long


class SupportRequest(BaseModel):
    customer_id: str
    ticket_content: str
    priority: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    result: Optional[dict] = None
    error: Optional[str] = None


# ---- 非同步任務執行 ----

def run_content_crew(job_id: str, request: ContentRequest):
    """在背景執行 Content Crew"""
    try:
        jobs[job_id]["status"] = "running"

        crew = ContentCrew().crew()
        result = crew.kickoff(inputs={
            "topic": request.topic,
            "language": request.language,
            "target_length": request.target_length,
        })

        jobs[job_id]["status"]   = "completed"
        jobs[job_id]["result"]   = {"content": result.raw, "tokens": result.token_usage.total_tokens}
        jobs[job_id]["finished_at"] = datetime.utcnow().isoformat()

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"]  = str(e)


def run_support_crew(job_id: str, request: SupportRequest):
    """在背景執行 Support Crew"""
    try:
        jobs[job_id]["status"] = "running"

        crew = SupportCrew().crew()
        result = crew.kickoff(inputs={
            "customer_id": request.customer_id,
            "ticket_content": request.ticket_content,
        })

        reply = result.pydantic
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "classification": reply.classification.model_dump(),
            "draft_reply":    reply.draft_reply,
            "internal_note":  reply.internal_note,
            "assignee":       reply.suggested_assignee,
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"]  = str(e)


# ---- API Endpoints ----

@app.post("/content/generate", response_model=JobResponse)
async def generate_content(
    request: ContentRequest,
    background_tasks: BackgroundTasks
):
    """提交內容生成任務（非同步，立即回傳 job_id）"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":     "queued",
        "created_at": datetime.utcnow().isoformat(),
        "type":       "content",
    }

    # 在背景執行，不阻塞 API
    background_tasks.add_task(run_content_crew, job_id, request)

    return JobResponse(
        job_id=job_id,
        status="queued",
        created_at=jobs[job_id]["created_at"],
    )


@app.post("/support/analyze", response_model=JobResponse)
async def analyze_support_ticket(
    request: SupportRequest,
    background_tasks: BackgroundTasks
):
    """提交客服工單分析任務"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":     "queued",
        "created_at": datetime.utcnow().isoformat(),
        "type":       "support",
    }
    background_tasks.add_task(run_support_crew, job_id, request)
    return JobResponse(job_id=job_id, status="queued", created_at=jobs[job_id]["created_at"])


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """查詢任務狀態和結果"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobResponse(
        job_id=job_id,
        status=job["status"],
        created_at=job["created_at"],
        result=job.get("result"),
        error=job.get("error"),
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "jobs_in_memory": len(jobs)}
```

### 啟動 API 服務

```bash
# 安裝依賴
pip install fastapi uvicorn

# 啟動（開發模式）
uvicorn main:app --reload --port 8000

# 啟動（生產模式，多 worker）
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 呼叫 API 的使用範例

```bash
# 提交內容生成任務
curl -X POST http://localhost:8000/content/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "量子計算的商業應用", "target_length": "medium"}'

# 回應：
# {"job_id": "abc123", "status": "queued", "created_at": "2026-05-23T10:00:00"}

# 查詢任務進度
curl http://localhost:8000/jobs/abc123

# 完成後回應：
# {
#   "job_id": "abc123",
#   "status": "completed",
#   "result": {"content": "...", "tokens": 3542}
# }
```

### Docker 容器化

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 設定環境變數（實際部署用 Secret Manager）
ENV OPENAI_API_KEY=""
ENV SERPER_API_KEY=""

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

```bash
# 建立 image
docker build -t crewai-service .

# 執行（注入 API key）
docker run -d \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your-key" \
  -e SERPER_API_KEY="your-key" \
  -v $(pwd)/crew_memory.db:/app/crew_memory.db \  # 持久化記憶體 DB
  crewai-service
```

---

## 完整的生產架構建議

```
用戶 / 觸發系統
    ↓
API Gateway（Nginx / AWS API Gateway）
    ↓
FastAPI 服務（CrewAI）
    ├── Redis Queue（任務佇列，防止過載）
    ├── CrewAI Flows（複雜工作流程）
    │   └── Crew 1, Crew 2, ... （各職能團隊）
    ├── LTM Database（PostgreSQL / SQLite）
    └── Vector DB（Chroma / Qdrant，用於 Short-term Memory）
    ↓
結果回調（Webhook / Slack / Email）
```

### 生產環境 Checklist

```
API 安全
  ☐ API Key 驗證（Header: X-API-Key）
  ☐ 請求頻率限制（Rate Limiting）
  ☐ 輸入驗證（Pydantic 已處理大部分）

可觀測性
  ☐ 結構化日誌（JSON 格式，送到 CloudWatch / Datadog）
  ☐ 任務執行時間追蹤
  ☐ Token 用量監控（設定每日預算告警）
  ☐ 錯誤率告警

可靠性
  ☐ 任務佇列（Redis Queue）防止 Crew 並發過高
  ☐ 失敗重試機制
  ☐ 超時設定（max_execution_time）
  ☐ Graceful shutdown

成本
  ☐ 根據任務類型選擇適合的 LLM
  ☐ 啟用工具結果快取（cache=True）
  ☐ 設定每個 Agent 的 max_iter 上限
  ☐ 月度費用預算設定（OpenAI Dashboard）
```

---

## 系列總結

CrewAI 系列三篇涵蓋了從入門到生產的完整路徑：

| 篇章 | 主題 | 關鍵技術 |
|------|------|---------|
| 第一篇 | 入門 | Agent、Task、Crew、Tool 四大元件 |
| 第二篇 | 實戰 | 競情分析、程式碼審查、客服自動化 |
| 第三篇 | 進階 | Flows（@start/@listen/@router）、Memory、FastAPI 部署 |

CrewAI 的核心價值是讓「多角色協作」這個複雜的概念，變得非常直覺。  
當你開始設計一個 Crew 時，想的不是「這段程式碼要怎麼寫」，而是「我需要什麼樣的團隊，每個人要做什麼」——這個思考方式本身就是 CrewAI 帶來的最大改變。

**推薦的學習路徑：**

1. 用第一篇的範例建立你的第一個 Crew
2. 選一個你目前在手動做的重複性工作，用第二篇的模式設計 Crew
3. 當流程需要條件分支，導入 Flows
4. 用 FastAPI 包裝，讓團隊的其他人也能使用

---

**系列導覽**

- [第一篇](/posts/crewai-series-part1-introduction-zh/)：入門與核心概念
- [第二篇](/posts/crewai-series-part2-real-world-tasks-zh/)：真實場景實戰——競情分析、程式碼審查、客服自動化
- **第三篇（本篇）**：進階技巧——Flows、Memory、結構化輸出與生產部署
