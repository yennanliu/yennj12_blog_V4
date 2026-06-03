---
title: "FDE 面試準備指南（四）：System Design 實戰"
date: 2026-05-30T11:30:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，完整拆解兩道 FDE 高頻系統設計題：企業知識庫 Chatbot 與 Internal AI Copilot，包含 Auth、RBAC、Cache、Logging 的設計細節"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "System Design", "RAG", "RBAC", "Cache", "Logging", "BigQuery", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> System Design 是 FDE 面試最能展現工程深度的地方。  
> 答得好，你就是那個「懂技術也懂業務」的人。

---

## System Design 面試的本質

面試官在問系統設計題的時候，不是要你給出標準答案，而是想看：

1. **你有沒有釐清問題的習慣**（不假設，先問）
2. **你的 trade-off 思維**（不說「最好的方案」，說「在這個場景下我選這個，因為…」）
3. **你有沒有考慮到生產環境的現實**（Auth、Scale、Cost、Failure）

---

## 第一題：設計企業知識庫 Chatbot

這是最高頻的考題之一。

**題目**：設計一個供企業內部使用的 AI 知識庫問答系統，員工可以用自然語言查詢公司政策、產品說明和技術文件。

### 第一步：釐清需求（你要主動問）

```
你應該問的問題：

- 同時使用的用戶數量級？（100人 vs 10萬人，差很多）
- 文件量多大？（1GB vs 1TB）
- 需要支援多語言嗎？
- 回答需要引用文件來源嗎？
- 有合規要求嗎？（GDPR、SOC2）
- Latency 要求？（秒級 vs 毫秒級）
- 不同部門能看的文件不同嗎？
```

最後一個問題很關鍵，決定了你需不需要 RBAC。

### 第二步：高層架構

```
用戶
 ↓ HTTPS
API Gateway（Auth Token 驗證 + Rate Limiting）
 ↓
Chatbot Service
 ├── RBAC 權限過濾（這個用戶能看哪些文件？）
 ├── Query Processor（問題前處理）
 │    ├── 意圖分類
 │    └── 查詢改寫（Query Rewriting）
 ├── RAG Engine
 │    ├── Embedding Service
 │    ├── Vector DB（根據 RBAC 過濾結果）
 │    └── Reranker
 ├── LLM（Claude / Gemini）
 └── Response Generator（加入引用來源）
 ↓
Cache Layer（相同問題不重複查）
 ↓
Logging & Monitoring
 ↓
回應給用戶
```

### Authentication：怎麼做

企業場景通常用 **SSO + JWT**：

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt

app = FastAPI()
security = HTTPBearer()

def verify_token(credentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        return {
            "user_id": payload["sub"],
            "department": payload["dept"],
            "roles": payload["roles"]
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已過期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="無效的 Token")

@app.post("/chat")
async def chat(
    request: ChatRequest,
    user: dict = Depends(verify_token)
):
    # user 已驗證，包含部門和角色資訊
    response = await chatbot.answer(
        question=request.question,
        user_context=user
    )
    return response
```

### RBAC：按角色控制文件存取

```python
ROLE_PERMISSIONS = {
    "employee": ["public", "general"],
    "manager": ["public", "general", "internal"],
    "hr": ["public", "general", "internal", "hr_confidential"],
    "finance": ["public", "general", "internal", "finance_confidential"],
    "admin": ["public", "general", "internal", "hr_confidential", 
              "finance_confidential", "executive"]
}

class RBACFilter:
    def get_allowed_categories(self, user_roles: list[str]) -> list[str]:
        allowed = set()
        for role in user_roles:
            allowed.update(ROLE_PERMISSIONS.get(role, []))
        return list(allowed)
    
    def filter_vector_search(
        self,
        query_embedding: list[float],
        user_roles: list[str],
        n_results: int = 5
    ) -> list[dict]:
        allowed_categories = self.get_allowed_categories(user_roles)
        
        # 在向量搜尋時加入過濾條件
        results = vector_db.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={
                "category": {"$in": allowed_categories}
            }
        )
        return results
```

**重點**：RBAC 要在 Vector DB 查詢時就過濾，不能查出來後再過濾。因為那樣你可能查到 `[機密文件、公開文件、機密文件, ...]`，但因為前幾名都被過濾掉，最後給 LLM 的 context 品質會很差。

### RAG 的 Query Rewriting

直接用用戶的原始問題去查向量資料庫，效果有時候不好。

例如用戶問：「我剛入職，想知道年假怎麼算」

這個問題包含太多無關資訊。應該先改寫：

```python
async def rewrite_query(original_query: str) -> str:
    prompt = f"""
    把以下問題改寫成適合搜尋的關鍵詞查詢。
    移除個人背景資訊，保留核心問題。
    
    原始問題：{original_query}
    改寫後的搜尋查詢：
    """
    
    rewritten = await llm.generate(prompt, temperature=0.1)
    return rewritten

# 「我剛入職，想知道年假怎麼算」
# → 「年假計算方式 員工請假規定」
```

### Cache Layer：哪些東西要 Cache

```python
import hashlib
import json
from redis import Redis

redis_client = Redis(host="localhost", port=6379)

class ChatCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
    
    def _make_key(self, question: str, user_roles: list[str]) -> str:
        # 相同問題但不同角色，答案可能不同（因為 RBAC）
        cache_input = json.dumps({
            "question": question.strip().lower(),
            "roles": sorted(user_roles)
        })
        return f"chat:{hashlib.md5(cache_input.encode()).hexdigest()}"
    
    def get(self, question: str, user_roles: list[str]) -> str | None:
        key = self._make_key(question, user_roles)
        cached = redis_client.get(key)
        return cached.decode() if cached else None
    
    def set(self, question: str, user_roles: list[str], answer: str):
        key = self._make_key(question, user_roles)
        redis_client.setex(key, self.ttl, answer)
```

**Cache 的邊界**：

- ✅ 適合 Cache：「年假幾天？」「請假流程？」這類政策問題，答案穩定
- ❌ 不適合 Cache：「我的訂單狀態？」這類個人化問題，每個人答案不同
- ❌ 不適合 Cache：需要即時資料的問題（股價、庫存）

### Logging：要記錄什麼

```python
import structlog
from datetime import datetime

logger = structlog.get_logger()

async def log_chat_event(
    user_id: str,
    question: str,
    answer: str,
    retrieved_docs: list[str],
    latency_ms: float,
    cache_hit: bool,
    model_name: str,
    input_tokens: int,
    output_tokens: int
):
    logger.info(
        "chat_event",
        timestamp=datetime.utcnow().isoformat(),
        user_id=user_id,                    # 誰問的（審計用）
        question_hash=hash(question),        # 不記錄原文，保護隱私
        answer_length=len(answer),
        retrieved_doc_ids=retrieved_docs,    # 查了哪些文件（排查幻覺用）
        latency_ms=latency_ms,              # 性能監控
        cache_hit=cache_hit,                # Cache 命中率
        model_name=model_name,
        cost_usd=(input_tokens * 0.000003 + output_tokens * 0.000015)
    )
```

---

## 第二題：設計 Internal AI Copilot

**題目**：設計一個 AI 助理，員工可以用自然語言查詢公司內部數據，例如「今年 Q3 的營收比 Q2 成長了多少？」

這題比知識庫 Chatbot 更難，因為要**即時查詢結構化資料**，而不是搜尋文件。

### 為什麼難

知識庫 Chatbot：問題 → 查文件 → 回答

Internal Copilot：問題 → **理解問題的數據意圖** → 查 BigQuery / CRM / ERP → **組合多來源數據** → 回答

### 高層架構

```
員工：「今年營收比去年成長多少？」
 ↓
Intent Classifier（這是數據查詢，不是文件查詢）
 ↓
NL2SQL Agent（把問題轉成 SQL）
 ↓
Tool Router
 ├── BigQuery Tool（財務、銷售數據）
 ├── CRM Tool（客戶、訂單數據）
 ├── ERP Tool（庫存、供應鏈）
 └── HR System Tool（員工數據）
 ↓
Data Aggregator（整合多來源結果）
 ↓
LLM（把數字轉成自然語言回答）
 ↓
Response（含數據來源標示）
```

### NL2SQL：把問題轉成 SQL

```python
async def natural_language_to_sql(
    question: str,
    schema_context: str,
    user_department: str
) -> str:
    prompt = f"""
    你是一位資深的 SQL 分析師。
    根據以下資料庫 Schema，將問題轉換為 SQL 查詢。
    
    只能查詢用戶有權限的資料表（部門：{user_department}）。
    
    Schema：
    {schema_context}
    
    注意事項：
    - 只生成 SELECT 語句，絕對不能生成 INSERT / UPDATE / DELETE
    - 如果問題超出你的 Schema 範圍，請說「無法查詢此資料」
    
    問題：{question}
    
    SQL：
    """
    
    sql = await llm.generate(prompt, temperature=0.0)
    
    # 安全驗證：確保只有 SELECT
    if not is_safe_sql(sql):
        raise SecurityError("生成了不安全的 SQL")
    
    return sql

def is_safe_sql(sql: str) -> bool:
    """確保 SQL 只包含讀取操作"""
    dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER"]
    sql_upper = sql.upper()
    return not any(keyword in sql_upper for keyword in dangerous_keywords)
```

### BigQuery Tool 實作

```python
from google.cloud import bigquery
from typing import Any

class BigQueryTool:
    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)
    
    async def execute_query(
        self,
        sql: str,
        max_rows: int = 1000,
        timeout_seconds: int = 30
    ) -> dict[str, Any]:
        
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=10 * 1024 * 1024 * 1024,  # 10GB 上限
            use_query_cache=True,
        )
        
        try:
            query_job = self.client.query(
                sql,
                job_config=job_config
            )
            
            results = query_job.result(
                max_results=max_rows,
                timeout=timeout_seconds
            )
            
            rows = [dict(row) for row in results]
            
            return {
                "success": True,
                "rows": rows,
                "total_rows": results.total_rows,
                "bytes_processed": query_job.total_bytes_processed,
                "cache_hit": query_job.cache_hit
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "rows": []
            }
```

### 整合多來源資料

員工可能問：「哪個銷售員今年業績最好，他的客戶滿意度怎麼樣？」

這需要同時查 BigQuery（銷售數據）和 CRM（滿意度評分）：

```python
import asyncio

class DataAggregator:
    async def query_multiple_sources(
        self,
        queries: list[dict],
        user_context: dict
    ) -> dict:
        
        tasks = []
        for query in queries:
            source = query["source"]
            sql = query["sql"]
            
            if source == "bigquery":
                task = self.bq_tool.execute_query(sql)
            elif source == "crm":
                task = self.crm_tool.execute_query(sql)
            elif source == "erp":
                task = self.erp_tool.execute_query(sql)
            
            tasks.append(task)
        
        # 並行查詢所有來源
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            source["source"]: result
            for source, result in zip(queries, results)
        }
```

### 把數字轉成自然語言

```python
async def generate_data_response(
    question: str,
    data: dict,
    source_labels: list[str]
) -> str:
    
    data_summary = format_data_for_llm(data)
    sources_text = "、".join(source_labels)
    
    prompt = f"""
    根據以下查詢結果，用清楚易懂的中文回答問題。
    
    數據來源：{sources_text}
    
    查詢結果：
    {data_summary}
    
    問題：{question}
    
    要求：
    - 直接回答問題，不要重複問題本身
    - 如果涉及百分比，請計算並說明
    - 在回答末尾標注「數據來源：{sources_text}」
    """
    
    return await llm.generate(prompt, temperature=0.1)
```

### 成本控制：這題必須說

BigQuery 按資料掃描量計費（$5 / TB）。如果 AI 生成的 SQL 每次掃整張 table，成本會很高。

```python
class CostAwareBigQueryTool:
    MAX_BYTES_PER_QUERY = 10 * 1024 ** 3  # 10 GB
    BYTES_PER_TB = 1024 ** 4
    PRICE_PER_TB = 5.0  # USD
    
    async def execute_with_cost_estimate(self, sql: str) -> dict:
        # 先用 Dry Run 估算成本
        dry_run_config = bigquery.QueryJobConfig(dry_run=True)
        dry_run_job = self.client.query(sql, job_config=dry_run_config)
        
        estimated_bytes = dry_run_job.total_bytes_processed
        estimated_cost = (estimated_bytes / self.BYTES_PER_TB) * self.PRICE_PER_TB
        
        if estimated_bytes > self.MAX_BYTES_PER_QUERY:
            return {
                "success": False,
                "error": f"查詢預估掃描 {estimated_bytes/1e9:.1f} GB，超出限制。請縮小查詢範圍。"
            }
        
        # 成本可接受，執行查詢
        return await self.execute_query(sql)
```

---

## 兩題的對比分析

| | 知識庫 Chatbot | Internal Copilot |
|--|--|--|
| 資料來源 | 文件（非結構化） | 資料庫（結構化） |
| 核心技術 | RAG + Vector DB | NL2SQL + 多來源查詢 |
| 幻覺風險 | 中（有文件 context） | 低（直接查資料）但有 SQL 錯誤風險 |
| RBAC 難度 | 中（文件分類） | 高（資料行 / 欄 level 的控制） |
| Latency | 較低（向量搜尋快） | 較高（SQL 查詢可能慢） |
| Cache 效益 | 高（政策類問題重複率高） | 中（數據每天更新，TTL 要短） |

---

## 面試中容易被追問的細節

**Q：Cache 過期了怎麼辦？**

知識庫 Chatbot 的 Cache TTL 設多長？文件更新時要主動 invalidate cache。

```python
async def update_document(doc_id: str, new_content: str):
    # 1. 更新向量資料庫
    await vector_db.update(doc_id, new_content)
    
    # 2. 清除相關 Cache（使用 tag-based invalidation）
    await cache.delete_by_tag(f"doc:{doc_id}")
```

**Q：LLM 生成了錯誤的 SQL 怎麼辦？**

```python
async def safe_nl2sql(question: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        sql = await nl_to_sql(question)
        
        # 語法驗證
        is_valid, error = validate_sql(sql)
        if not is_valid:
            # 把錯誤告訴 LLM，讓它自我修正
            question = f"""
            之前生成的 SQL 有錯誤：{error}
            請修正後重新生成。
            原始問題：{question}
            """
            continue
        
        return sql
    
    return None  # 三次都失敗，回報無法處理
```

**Q：用戶問了 Schema 裡沒有的資料怎麼辦？**

系統要能識別這種情況並優雅地告知，而不是生成一個查不到資料的 SQL 或直接幻覺。

---

## 完整的面試回答結構

系統設計題，我建議這樣走：

```
第一分鐘：
"在開始設計之前，我想先確認幾個需求..."
（問 1-2 個關鍵問題：用戶規模、RBAC 需求、Latency 要求）

第二到五分鐘：
"好，根據這些需求，我的高層架構是這樣..."
（畫圖，解釋每個元件的職責）

第六到十五分鐘：
"我想深入說明幾個關鍵設計決策..."
（選 2-3 個最重要的部分：RBAC 實作、Cache 策略、Failure 處理）

最後幾分鐘：
"這個設計的主要 trade-off 是..."
"最可能出問題的地方是..."
```

---

## 系列總結

四篇下來，我想說的核心只有一件事：

**FDE 是橋接器，不是工具使用者。**

能說出「我會用 LangGraph 做這個」，只是入門。

能說出「在這個場景下，Multi-Agent 帶來的複雜度不值得，我會選擇 Single Agent + 多個 Tools，因為…」，才是 FDE 的水準。

面試考的是判斷力，不是背誦力。

---

## 系列文章索引

### 基礎篇

- **第一篇**：[RAG 完全解析](/posts/fde-interview-guide-part1-rag-zh/) — Embedding、Chunk 策略、幻覺改善
- **第二篇**：[Agent System Design](/posts/fde-interview-guide-part2-agent-zh/) — ReAct、Multi-Agent、MCP、失控防範
- **第三篇**：[ML 基礎知識](/posts/fde-interview-guide-part3-ml-fundamentals-zh/) — Transformer、Embedding、Fine-tuning、評估指標
- **第四篇**：[System Design 實戰](/posts/fde-interview-guide-part4-system-design-zh/) — 知識庫 Chatbot、Internal Copilot

### 深度篇

- **第五篇**：[RAG 深度技術](/posts/fde-interview-guide-part5-rag-deep-dive-zh/) — Chunking 策略、Embedding 選型、向量 DB 設計、Hybrid Search、Reranking
- **第六篇**：[RAG 進階](/posts/fde-interview-guide-part6-rag-eval-zh/) — 檢索失敗診斷、Grounding 策略、評估指標、成本控制
- **第七篇**：[Agent 深度設計](/posts/fde-interview-guide-part7-agent-design-zh/) — ReAct vs Planner、Tool Routing、Multi-Agent、Memory
- **第八篇**：[ML 基礎必備](/posts/fde-interview-guide-part8-ml-fundamentals-zh/) — 傳統 ML → Deep Learning → Transformer
- **第九篇**：[LLM 核心知識](/posts/fde-interview-guide-part9-llm-core-zh/) — Token、Prompt Engineering、Embedding

---

下一篇：[**RAG 深度技術**](/posts/fde-interview-guide-part5-rag-deep-dive-zh/) — Chunking、Embedding 選型、向量 DB、Hybrid Search。
