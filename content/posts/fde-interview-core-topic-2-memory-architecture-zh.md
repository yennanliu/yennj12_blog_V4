---
title: "Memory Architecture：Agent 階層式記憶體設計"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析 Agent 三層記憶體架構（Episodic / Semantic / Procedural），涵蓋寫入模式、ANN 檢索、遺忘機制與企業級 RBAC 設計。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topics", "Cloud", "Agent", "Memory", "VectorDB"]
authors: ["yen"]
readTime: "18 min"
---

**Agent 的記憶體不是一個 buffer，是三層具有不同時效、不同存取模式、不同成本結構的資料系統——設計錯了，對話脈絡在 context window 之外全數消失。**

---

## 一、為什麼面試官問這個

FDE 面試官問 Memory Architecture，實際測的是三件事：

- **你是否理解 context window 的硬限制**：LLM 的 context window 有限（Gemini 1.5 Pro 為 1M tokens，但實際可用的 coherent window 遠小於此），無法把整個對話歷史塞進 prompt。候選人必須說明如何在 window 之外持久化並選擇性地召回記憶。
- **你是否知道三類記憶體的技術差異**：Episodic（短期、高寫入頻率）、Semantic（長期、需壓縮）、Procedural（靜態、系統層）三者的存儲介質、延遲要求和失效策略截然不同。只會說「存到資料庫」的候選人會被立刻追問「什麼資料庫？TTL 怎麼設？」。
- **你是否考慮到企業級需求**：多租戶隔離、RBAC、CMEK 加密。在 B2B SaaS 場景下，記憶體洩漏到其他租戶是 P0 事故。

**弱答**：「把對話存到 Redis，要用的時候再取回來。」

**強答**：分層說明三類記憶體的存取模式與延遲 SLA，描述 write-through 非同步寫入與 nightly consolidation job 的架構，並主動提出 forgetting 機制避免無限增長。

---

## 二、核心原理與技術深度

### 三層記憶體模型

Agent 記憶體借鑒認知科學的 Atkinson-Shiffrin 模型，對應到工程實作：

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Memory Stack                     │
├─────────────────────────────────────────────────────────────┤
│  Procedural Memory（程序性記憶）                             │
│  System Prompt + Tool Definitions                           │
│  存儲：Config 管理系統 / Firestore                           │
│  更新頻率：極低（版本升級才改）                               │
│  大小：4KB–32KB                                             │
├─────────────────────────────────────────────────────────────┤
│  Semantic Memory（語意記憶）                                 │
│  壓縮後的事實、偏好、歷史知識                                 │
│  存儲：Vertex AI Vector Search（ANN 索引）                   │
│  更新頻率：每日 consolidation job                            │
│  大小：每個 User 數百至數千個 embedding                      │
├─────────────────────────────────────────────────────────────┤
│  Episodic Memory（情節記憶）                                 │
│  當前 session 的對話輪次                                     │
│  存儲：Redis Cluster，TTL = 2h                              │
│  更新頻率：每個對話 turn                                     │
│  大小：每 turn 約 1–4KB                                     │
└─────────────────────────────────────────────────────────────┘
```

### 寫入路徑（Write-Through Pattern）

每個對話 turn 結束後，系統執行非同步寫入，避免阻塞主要回應路徑：

```
User Turn N 完成
       │
       ├──▶ 同步：回傳 Response 給 User
       │
       └──▶ 非同步 Worker（< 100ms，不在 critical path）
                 │
                 ├──▶ 寫入 Episodic Memory（Redis）
                 │    Key: session:{session_id}:turns
                 │    Value: LPUSH JSON turn object
                 │    TTL: 2 小時（EXPIRE 重置）
                 │
                 └──▶ 關鍵事實萃取（輕量 LLM 呼叫）
                      若本輪含重要事實（偵測到 entity / preference）
                      → 暫存至 staging queue（Pub/Sub）
                      → 等待 nightly consolidation 處理
```

### 讀取路徑（Read Pattern at Conversation Start）

```
新對話開始
    │
    ▼
┌──────────────────────┐
│  1. 讀取 Procedural  │  從 Config 讀 System Prompt + Tools
│     Memory           │  延遲：< 5ms（記憶體快取）
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  2. Episodic Memory  │  Redis GET session:{session_id}:turns
│     （若 session     │  延遲：< 2ms
│      仍存活）        │  取最近 N 輪（預設 20 輪）
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  3. Semantic Memory  │  將 User 最新訊息 embed（text-embedding-004）
│     ANN 檢索         │  在 Vertex AI Vector Search 做 top-K ANN 查詢
└──────────┬───────────┘  延遲：< 15ms（p99）
           │              K = 5（預設），distance metric = cosine
           ▼
┌──────────────────────┐
│  4. Context 組裝     │  Procedural + Semantic（作為 prefix）
│                      │  + Episodic（作為近期對話）
│                      │  + 新 User Message
└──────────────────────┘
  最終 context 送入 LLM 推理
```

### ANN 索引技術細節

Vertex AI Vector Search 使用 **ScaNN（Scalable Nearest Neighbors）** 演算法，核心是兩步驟：

1. **量化（Quantization）**：將 float32 embedding 壓縮為 int8，降低記憶體 4× 但召回率損失 < 1%。
2. **分割（Partitioning）**：用 k-means 把向量空間切成 N 個分區，查詢時只掃描最近的幾個分區（beam_size 控制）。

**關鍵參數**：
- Embedding 維度：768（text-embedding-004）
- 每個 User 上限：5,000 個 semantic memories（超過觸發月度 eviction）
- ANN 查詢延遲：< 15ms（p99），< 8ms（p50）
- 精確度（recall@10）：> 0.95

### Nightly Consolidation Job

每日凌晨 2:00（低峰時段）執行批次壓縮：

```
Pub/Sub staging queue
       │
       ▼
Cloud Run Job（Gemini Flash 驅動）
  批次大小：1,000 turns / run
  每個 turn 的處理：
    1. 萃取關鍵事實（Fact Extraction prompt）
    2. 去重（dedup 已存在的 semantic memories，cosine > 0.92 視為重複）
    3. 產生 embedding（text-embedding-004）
    4. Upsert 至 Vertex AI Vector Search
  平均處理速率：~500 turns/min
  每日費用估計：~$2–5（依 user 活躍數）
```

### 遺忘機制（Forgetting / Memory Decay）

無限累積記憶會導致 ANN 索引膨脹、召回品質下降（hub problem：高頻向量成為所有查詢的最近鄰）。月度 eviction job 用以下公式評分：

```
Score(m) = Importance(m) × Recency(m)

Importance(m) = LLM 評分（1–5）× 存取頻率（最近 30 天被召回次數）
Recency(m)    = exp(-λ × days_since_last_access)  λ = 0.05

Score < 0.3 → 標記為候選刪除
Score < 0.1 → 直接 evict（hard delete from Vector Search）
```

每個 User 的 semantic memory 上限為 5,000 筆；超過上限時，從最低 Score 開始刪除直到降至 4,500 筆（留有 10% buffer 避免 eviction 過於頻繁）。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**實作內容**：
- 只有 Episodic Memory：Redis 單節點，TTL = 2h，存完整對話 JSON
- System Prompt 硬編碼，無 Procedural 管理層
- 無 Semantic Memory：每次對話從零開始

**適用情境**：PoC、單一用戶的 demo、預計 < 1,000 active sessions

**成本**：Redis Memorystore Basic 1GB ≈ $30/月

**尚未解決的問題**：
- 跨 session 記憶完全消失（2h TTL 到期後用戶資訊全失）
- Redis 單點故障，session 全數清空
- System Prompt 改版需要 redeploy

**複雜度**：低（1 週實作）

---

### Layer 2 — 生產就緒（Production-Ready）

**在 Layer 1 基礎上新增**：
- **Redis Cluster**（3 shard × 2 replica）：HA，無單點故障
- **Semantic Memory**：Vertex AI Vector Search + text-embedding-004
- **Write-through 非同步寫入**：用 Cloud Tasks 在 turn 結束後 async 觸發 fact extraction
- **Consolidation Job**：Cloud Run Job，每日執行，Gemini Flash 處理
- **Procedural Memory**：System Prompt 存入 Firestore，版本化管理，熱更新不需 redeploy

**能解決的問題**：
- 跨 session 知識保留
- System Prompt 動態更新
- 單一 Redis 節點故障不影響服務

**延遲 SLA**：
- Episodic 讀取：< 2ms
- Semantic 檢索：< 15ms（p99）
- 整體 context 組裝：< 25ms

**成本（1 萬 DAU 估計）**：
- Redis Cluster：~$150/月
- Vertex AI Vector Search：~$100/月
- Consolidation Job（Gemini Flash）：~$50/月
- 合計：~$300/月

**複雜度**：中（3–4 週實作）

---

### Layer 3 — 企業級（Enterprise-Grade）

**在 Layer 2 基礎上新增**：

**多租戶隔離**：
- Vertex AI Vector Search 按 tenant_id 使用獨立 index 或 namespace filter
- Redis key 前綴：`tenant:{tenant_id}:session:{session_id}:turns`
- Consolidation Job 按 tenant 分批，避免跨租戶資料混用

**RBAC on Memory Read**：
- 每個 semantic memory entry 帶有 `visibility` 欄位：`private` / `team` / `org`
- 查詢時附加 ACL filter（Vertex AI Vector Search 支援 restricts 欄位過濾）
- 服務帳號驗證：只有 Agent Service Account 有 Vertex AI Index 的 `roles/aiplatform.user`

**CMEK 加密**：
- Redis Memorystore：啟用 Cloud KMS CMEK，每個租戶獨立 key ring
- Vertex AI Vector Search：data at rest 使用 Cloud KMS 管理的 CMEK
- Key rotation：每 90 天自動輪轉

**觀測性（Observability）**：
- 每個 memory read / write 寫入 Cloud Trace（span: `memory.episodic.read`, `memory.semantic.retrieve`）
- Consolidation Job 成功率、batch 大小、失敗 turn 數 → Cloud Monitoring dashboard
- ANN 召回品質（top-K cosine score 分布）每週計算，設 alert：p50 cosine < 0.7 觸發警報

**合規（Compliance）**：
- GDPR「被遺忘權」：提供 `/users/{id}/memories DELETE` API，觸發 hard delete pipeline
- 資料留存政策：Episodic 2h TTL，Semantic 依合約設定（預設 12 個月）
- 稽核日誌：所有 memory 讀寫操作寫入 Cloud Audit Logs

**成本（10 萬 DAU 估計）**：
- Redis Cluster（10 shard）：~$800/月
- Vertex AI Vector Search（100M vectors）：~$1,200/月
- Consolidation + Embedding：~$400/月
- CMEK + Audit Logging：~$200/月
- 合計：~$2,600/月（$0.026/DAU/月）

**複雜度**：高（6–10 週實作，需安全審核）

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 把完整對話歷史丟進 context window | Token 用量爆炸，推理延遲從 2s 升到 10s+；超過 context limit 後強制截斷，截掉的是最早的（最重要的）上下文 | Episodic 只取最近 N 輪（20 輪），Semantic 用 ANN 選最相關的 K 筆，總 token 預算設上限 |
| Redis 不設 TTL | Session 無限累積，記憶體耗盡後 OOM evict 整個 cache，所有 session 同時失效（驚群） | 每次 turn 寫入後重置 TTL（EXPIRE key 7200），session 結束時主動 DEL |
| Semantic Memory 無去重 | 同一事實重複儲存數十次，ANN 結果被重複向量主導（diversity 下降），召回品質惡化 | Consolidation 前計算 cosine similarity，> 0.92 的視為重複，只保留最新版本 |
| 單一 Vector Search index 存所有租戶 | 一個租戶的記憶被另一個租戶的查詢檢索到（資料洩漏），違反 SOC 2 要求 | 每個租戶獨立 namespace，或用 restricts filter 嚴格隔離，並在 CI 加入跨租戶洩漏測試 |
| Consolidation Job 在白天執行 | 與線上推理搶 Gemini Flash quota，導致線上 Agent 回應延遲；embedding 服務出現 429 | 排程在凌晨 2:00–5:00，設 quota limit，與線上路由使用不同的 API key / project |
| 遺忘機制缺失 | 每個 User 的 Vector Search index 無限增長，6 個月後 ANN 延遲從 15ms 升至 80ms+，還會遇到 hub problem | 月度 eviction job，評分 = Importance × Recency，低於閾值的 memory 硬刪除 |
| 未加密 Semantic Memory | 用戶的個資、偏好、行為模式以明文存於 Vector Search，違反 GDPR / HIPAA | 啟用 CMEK，每個租戶獨立 key，key rotation 設定 90 天週期 |

---

## 五、與其他核心主題的關聯

- **Core Topic 1 — Context Window Management**：Memory Architecture 是 context window 管理的下游；如何從三層記憶體中選出最相關的內容填入有限的 context window，是兩者的接口。決策原則：Procedural 永遠在、Episodic 最近 N 輪、Semantic 用 ANN 填剩餘空間。

- **fde-interview-guide Part 31–32（ADK + Vertex AI）**：ADK 的 `MemoryBankService` 介面是 Semantic Memory 的抽象層，底層接 Vertex AI Vector Search；理解本文的 ANN 讀寫路徑，才能正確配置 ADK memory bank 的 `top_k` 與 `similarity_threshold` 參數。

- **fde-interview-guide Part 35–38（Production Engineering）**：Consolidation Job 的 Cloud Run Job 設計、Redis Cluster 的 HA 配置、CMEK key rotation 的 Terraform 實作，都在 Part 35–38 的生產工程章節有完整的 runbook。

- **Core Topic 5 — RAG Pipeline**（後續篇）：RAG 是 Semantic Memory 的延伸——RAG 存的是外部知識庫，Semantic Memory 存的是 per-user 個人化知識；兩者共用 embedding + ANN 的基礎設施，但索引隔離、TTL 策略、更新頻率截然不同。

---

## 六、面試一句話（Killer Phrase）

> *「Agent 的記憶體需要三層設計：Episodic 存當前 session 的對話輪次，用 Redis TTL = 2h 管理，讀取延遲 < 2ms；Semantic 存壓縮後的長期知識，用 Vertex AI Vector Search 做 ANN 檢索，p99 延遲 < 15ms；Procedural 存 System Prompt 和 Tool 定義，幾乎靜態。每個 turn 結束後非同步 write-through 到 Episodic，nightly consolidation job 用 Gemini Flash 從 Episodic 萃取事實、去重後 upsert 到 Semantic；月度 eviction 用 Importance × Recency 衰減評分來控制 index 大小，避免 hub problem。企業級場景還需要 per-tenant namespace 隔離、RBAC filter 和 CMEK 加密，否則記憶體洩漏就是 P0 資安事故。」*

---

**系列導航**

← [前一篇：Context Window Management](/posts/fde-interview-core-topic-1-context-window-zh/) | [後一篇：Tool Use & Function Calling](/posts/fde-interview-core-topic-3-tool-use-zh/) →
