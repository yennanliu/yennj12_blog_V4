---
title: "用 AI Bot 打造顧問團隊（三）：評估、維運與優化計畫"
date: 2026-04-30T11:00:00+08:00
draft: false
description: "AI 顧問 Agent 團隊上線後怎麼辦？本文從 DevOps/SRE 角度，涵蓋系統效能評估、品質驗證、監控告警、部署策略、以及持續改善的 Roadmap。"
categories: ["AI", "Agent", "DevOps", "SRE", "all"]
tags: ["AI Agent", "DevOps", "SRE", "LangSmith", "監控", "部署", "評估", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "25 min"
---

## 前言

你已經建好了 AI 顧問 Agent 團隊（[第一篇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/)、[第二篇](/posts/ai-agent-team-for-consultant-part2-implementation-zh/)），現在問題來了：

> **「這系統真的有在正常工作嗎？品質夠好嗎？出了問題怎麼辦？」**

AI Agent 系統不像傳統軟體，你不能只看 HTTP 200。你需要評估**輸出品質**、追蹤**推理過程**、並且在 LLM 開始說廢話之前就發現它。

本篇從 DevOps/SRE 的角度，完整說明如何讓 AI 顧問團隊穩定、可觀測、持續進化。

---

## 一、系統效能評估：怎麼知道 Agent 表現好不好？

### 1.1 評估的四個維度

```
品質（Quality）    → 輸出內容是否正確、有用、符合顧問標準
速度（Latency）    → 每個 Agent 節點的回應時間
成本（Cost）       → 每次顧問對話的 Token 花費
可靠性（Reliability）→ 成功完成整個流程的比率
```

### 1.2 建立評估資料集（Golden Dataset）

這是最重要的第一步。準備 20-50 個有代表性的客戶案例：

```python
# evaluation/golden_dataset.py
GOLDEN_CASES = [
    {
        "id": "case-001",
        "input": "我們是一家 50 人的電商公司，客服每天要處理 500 封郵件，想用 AI 減輕負擔。",
        "expected_intake": {
            "industry": "電商",
            "size": "50人",
            "pain_points": ["客服郵件量大"],
            "ai_type": "自動化"
        },
        "expected_strategy_keywords": ["聊天機器人", "郵件分類", "自動回覆"],
        "quality_rubric": {
            "relevance": "策略必須針對客服場景",
            "feasibility": "建議的方案在 100 萬預算內可行",
            "actionability": "至少有 3 個具體的下一步行動"
        }
    },
    # ... 更多案例
]
```

### 1.3 自動化品質評估（LLM-as-Judge）

用另一個 LLM 來評審輸出品質：

```python
# evaluation/judge.py
from anthropic import Anthropic

client = Anthropic()

JUDGE_PROMPT = """你是一位資深 AI 顧問，正在評審一份顧問報告的品質。

客戶需求：{client_input}
顧問報告：{report}

請從以下維度評分（1-10），並給出理由：
1. 相關性（Relevance）：報告是否針對客戶的具體問題？
2. 可行性（Feasibility）：建議是否實際可執行？
3. 完整性（Completeness）：是否涵蓋需求收集→分析→策略→行動計畫？
4. 清晰度（Clarity）：是否用非技術人員能理解的語言？

回覆格式：
```json
{
  "scores": {"relevance": 8, "feasibility": 7, "completeness": 9, "clarity": 8},
  "overall": 8.0,
  "strengths": ["..."],
  "weaknesses": ["..."],
  "pass": true
}
```
"""

def evaluate_report(client_input: str, report: str) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(
                client_input=client_input,
                report=report
            )
        }]
    )
    import json
    return json.loads(response.content[0].text)


# 批次評估
def run_evaluation(test_cases: list) -> dict:
    results = []
    for case in test_cases:
        # 執行 Agent 團隊
        report = run_consultant_pipeline(case["input"])
        # 評估品質
        score = evaluate_report(case["input"], report)
        results.append({
            "case_id": case["id"],
            "score": score,
            "passed": score["overall"] >= 7.0
        })

    pass_rate = sum(1 for r in results if r["passed"]) / len(results)
    avg_score = sum(r["score"]["overall"] for r in results) / len(results)

    return {
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "results": results
    }
```

### 1.4 效能基準（Benchmark）

建立並追蹤關鍵指標：

```python
# monitoring/benchmark.py
import time
from dataclasses import dataclass

@dataclass
class BenchmarkResult:
    total_latency_s: float      # 整個流程總時間
    intake_latency_s: float
    analyst_latency_s: float
    strategist_latency_s: float
    writer_latency_s: float
    total_tokens: int
    total_cost_usd: float
    quality_score: float
    success: bool

# 目標基準（SLO）
SLO = {
    "p50_latency_s": 30,        # 50% 的請求在 30 秒內完成
    "p95_latency_s": 90,        # 95% 在 90 秒內
    "quality_score_min": 7.0,   # 平均品質分數 ≥ 7
    "success_rate": 0.95,       # 成功率 ≥ 95%
    "cost_per_consultation": 0.50  # 每次諮詢成本 ≤ $0.5 USD
}
```

---

## 二、可觀測性（Observability）：看得見才能管理

### 2.1 LangSmith（路線 C 專屬）

```python
# 在 graph.py 中加入追蹤
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "ai-consultant-prod"

# 每次執行都會自動送到 LangSmith Dashboard
# 可以看到：
# - 每個 Agent 節點的輸入/輸出
# - Token 使用量與成本
# - 延遲時間
# - 錯誤堆疊
```

### 2.2 自建日誌系統（三條路線通用）

```python
# monitoring/logger.py
import structlog
import json
from datetime import datetime

log = structlog.get_logger()

class AgentLogger:
    def log_agent_call(
        self,
        agent_name: str,
        input_data: dict,
        output_data: dict,
        latency_s: float,
        tokens_used: int,
        success: bool,
        error: str = None
    ):
        log.info(
            "agent_call",
            agent=agent_name,
            latency_s=round(latency_s, 3),
            tokens=tokens_used,
            success=success,
            error=error,
            timestamp=datetime.utcnow().isoformat()
        )

    def log_consultation_complete(
        self,
        consultation_id: str,
        total_latency_s: float,
        quality_score: float
    ):
        log.info(
            "consultation_complete",
            consultation_id=consultation_id,
            total_latency_s=total_latency_s,
            quality_score=quality_score
        )
```

### 2.3 Prometheus + Grafana 監控儀表板

```yaml
# docker-compose.yml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

```python
# monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# 定義指標
consultation_total = Counter(
    "consultation_total",
    "顧問諮詢總次數",
    ["status"]  # success / failed
)

agent_latency = Histogram(
    "agent_latency_seconds",
    "Agent 回應時間",
    ["agent_name"],
    buckets=[1, 5, 10, 30, 60, 90, 120]
)

quality_score = Gauge(
    "consultation_quality_score",
    "最近一次顧問報告品質分數"
)

# 在 Agent 執行前後記錄
def track_agent(agent_name: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with agent_latency.labels(agent_name=agent_name).time():
                result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator

# 啟動 metrics server
start_http_server(8000)
```

**建議的 Grafana 儀表板面板：**

```
┌─────────────────────────────────────────────┐
│  AI 顧問團隊監控儀表板                         │
├──────────┬──────────┬──────────┬────────────┤
│ 今日諮詢數 │ 成功率   │ 平均延遲  │ 平均品質分數 │
│   42     │  97.6%  │  45s    │    7.8/10  │
├──────────┴──────────┴──────────┴────────────┤
│  延遲趨勢（過去 24 小時）                       │
│  [折線圖]                                    │
├─────────────────────────────────────────────┤
│  各 Agent 平均回應時間                         │
│  Intake: 8s | Analyst: 15s | Strategy: 22s  │
├─────────────────────────────────────────────┤
│  Token 使用量與成本（按日）                     │
│  [柱狀圖]                                    │
└─────────────────────────────────────────────┘
```

---

## 三、告警設計：出問題要第一時間知道

### 3.1 告警規則（PagerDuty / Slack）

```yaml
# alerting/rules.yml
groups:
  - name: ai_consultant_alerts
    rules:
      # 成功率低於 90%
      - alert: LowSuccessRate
        expr: |
          rate(consultation_total{status="success"}[5m]) /
          rate(consultation_total[5m]) < 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "AI 顧問成功率下降至 {{ $value | humanizePercentage }}"
          action: "檢查 LangSmith traces，確認哪個 Agent 節點失敗"

      # P95 延遲超過 2 分鐘
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, agent_latency_seconds) > 120
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "P95 延遲超過 2 分鐘"

      # 品質分數連續低於 6.5
      - alert: LowQualityScore
        expr: consultation_quality_score < 6.5
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "顧問報告品質下滑，需要檢視 Prompt"
```

### 3.2 Slack 告警整合

```python
# alerting/slack_notifier.py
import httpx
import os

async def send_alert(title: str, message: str, severity: str):
    color = {"critical": "#FF0000", "warning": "#FFA500", "info": "#0000FF"}[severity]
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{severity.upper()}] {title}",
            "text": message,
            "footer": "AI 顧問團隊監控",
        }]
    }
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=payload)
```

---

## 四、部署策略

### 4.1 架構圖

```
用戶端（網頁/LINE/Slack）
        ↓
   API Gateway（FastAPI）
        ↓
   任務佇列（Redis / Celery）
        ↓
   LangGraph Worker（多個實例）
   ┌──────────────────────────┐
   │  Intake → Analyst →      │
   │  Strategist → Writer     │
   └──────────────────────────┘
        ↓
   結果儲存（PostgreSQL）
        ↓
   通知（Webhook / Email）
```

### 4.2 FastAPI 後端

```python
# api/main.py
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uuid

app = FastAPI(title="AI 顧問 API")

class ConsultationRequest(BaseModel):
    client_message: str
    client_id: str | None = None

class ConsultationResponse(BaseModel):
    consultation_id: str
    status: str
    estimated_time_seconds: int = 60

@app.post("/consultation", response_model=ConsultationResponse)
async def start_consultation(
    request: ConsultationRequest,
    background_tasks: BackgroundTasks
):
    consultation_id = str(uuid.uuid4())

    # 異步執行，不阻塞 API
    background_tasks.add_task(
        run_consultant_pipeline_async,
        consultation_id,
        request.client_message
    )

    return ConsultationResponse(
        consultation_id=consultation_id,
        status="processing"
    )

@app.get("/consultation/{consultation_id}")
async def get_consultation_result(consultation_id: str):
    result = await db.get_consultation(consultation_id)
    if not result:
        return {"status": "processing"}
    return {"status": "done", "report": result["final_report"]}
```

### 4.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.4 Kubernetes 部署（生產環境）

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-consultant-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-consultant-worker
  template:
    spec:
      containers:
        - name: worker
          image: ai-consultant:latest
          env:
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: ai-secrets
                  key: anthropic-api-key
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
```

### 4.5 版本發布策略：金絲雀部署

當你更新 Prompt 或換模型時，**不要直接全量替換**：

```yaml
# 90% 流量走舊版本，10% 走新版本
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
spec:
  http:
    - route:
        - destination:
            host: ai-consultant
            subset: v1-stable
          weight: 90
        - destination:
            host: ai-consultant
            subset: v2-canary
          weight: 10
```

監控兩組的品質分數差異，確認新版本更好再全量切換。

---

## 五、持續改善計畫（Roadmap）

### 5.1 短期優化（上線後 1 個月）

- [ ] **Prompt 版本控制**：用 git 管理所有 Agent 的 System Prompt，每次修改要記錄理由
- [ ] **失敗案例分析**：每週檢視品質分數 < 6.5 的案例，找出 Prompt 缺陷
- [ ] **回應快取**：相似問題的中間結果可以快取，降低成本和延遲
- [ ] **Streaming 回應**：讓用戶即時看到 Agent 的思考過程，降低等待焦慮

### 5.2 中期功能（2-3 個月）

- [ ] **RAG 知識庫**：把過去的顧問案例建成向量資料庫，讓 Agent 能參考過往成功案例
- [ ] **Fine-tuning**：用高品質的顧問對話資料微調模型（尤其適合 Intake Agent）
- [ ] **多語言支援**：新增英語和日語的顧問服務
- [ ] **客戶 Portal**：讓客戶自己追蹤顧問流程進度

### 5.3 長期目標（3-6 個月）

- [ ] **自主學習迴圈**：好的顧問報告自動加入訓練資料集
- [ ] **Agent 自我評估**：每個 Agent 在輸出後自動評估自己的答案，低分時重試
- [ ] **多模態輸入**：支援客戶上傳財務報表（PDF）、組織架構圖（圖片）
- [ ] **A/B 測試框架**：系統化測試不同 Prompt 策略的效果

---

## 六、SRE 核心原則在 AI Agent 系統的應用

### 錯誤預算（Error Budget）

傳統 SRE 的錯誤預算概念同樣適用：

```
月可用分鐘數 = 30 × 24 × 60 = 43,200 分鐘
目標可用性 = 99.5%
錯誤預算 = 43,200 × 0.5% = 216 分鐘/月

用掉錯誤預算的情況：
- 每次顧問失敗 = 消耗 5 分鐘預算
- 品質分數 < 6 = 消耗 2 分鐘預算
- 延遲 > 3 分鐘 = 消耗 1 分鐘預算

當錯誤預算用完 50% → 停止新功能開發，專注穩定性
當錯誤預算用完 → 啟動事後分析（Post-mortem）
```

### 事後分析範本（Postmortem）

```markdown
## 事後分析：[日期] AI 顧問品質下滑事件

### 摘要
[時間段] 品質分數從 7.8 下滑至 5.2，影響約 XX 次諮詢。

### 根本原因
Strategist Agent 的 Prompt 在 [版本] 更新後，對製造業客戶的策略建議
過於抽象，未提供具體的 KPI 指標。

### 影響範圍
- 影響諮詢次數：XX 次
- 消耗錯誤預算：XX 分鐘

### 修復行動
1. [完成] 回滾 Strategist Prompt 至上一版本
2. [進行中] 為製造業場景加入 Few-shot 範例
3. [計畫中] 建立產業別的 Prompt 測試集

### 防止再發
- 加入 Prompt 變更的自動評估 CI/CD 步驟
- 新 Prompt 需通過 Golden Dataset 所有測試才能部署
```

---

## 總結

打造 AI 顧問 Bot 團隊的三個階段：

```
Phase 1：建立（Build）
  → 選技術路線，設計角色，完成 MVP

Phase 2：驗證（Validate）
  → Golden Dataset 評估，品質 ≥ 7/10，成功率 ≥ 95%

Phase 3：運營（Operate）
  → 監控 + 告警 + 持續優化的飛輪
```

最重要的一件事：**從第一天就開始收集失敗案例。** 每一次 Agent 搞砸的顧問報告，都是改進 Prompt 的黃金機會。

---

*本系列文章：*
- [第一篇：策略與技術路線選擇](/posts/ai-agent-team-for-consultant-part1-strategy-zh/)
- [第二篇：各路線實作步驟與範例程式碼](/posts/ai-agent-team-for-consultant-part2-implementation-zh/)
- **第三篇（本篇）：評估、維運與優化計畫**
