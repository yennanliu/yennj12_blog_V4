---
title: "FDE 面試準備指南（三十二）：RKK 實戰——Vertex AI 產品棧全解析：Agent Builder、Vertex AI Search、Gemini API 與部署架構"
date: 2026-06-05T10:00:00+08:00
draft: false
weight: 32
description: "以 Google FDE 視角完整拆解 Vertex AI AI 產品棧：何時選 Agent Builder vs 自建、Vertex AI Search 和 DIY RAG 的根本差異、Gemini API 四個關鍵特性（system instruction、tool use、grounding、context caching），以及企業 AI 系統的 GCP 部署架構"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Vertex AI", "Gemini", "Agent Builder", "GCP", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "19 min"
---

> FDE 的面試不是考「你知不知道 Vertex AI 有哪些產品」。  
> 是考「當客戶描述一個場景，你能不能說清楚——  
> 在 Google 的產品棧裡，他應該用哪個，不應該用哪個，以及為什麼。」  
> 這個判斷能力，才是 Google FDE 和一般 AI 工程師的差距。

---

## 面試情境

> **面試官：**「客戶想部署一個企業內部知識庫問答系統。他們的 IT 主管問：Google 有 Agent Builder，也有 Vertex AI Search，我自己也可以用 Gemini API 搭 RAG。這三條路有什麼差別？我應該選哪個？如果要上 Production，我的架構應該長什麼樣子？」

---

## 一、產品棧的 Build vs Buy 決策框架

先建立一個選擇框架，而不是直接說「選這個」：

```
┌────────────────────────────────────────────────────────────────────┐
│                    Vertex AI AI 產品選擇矩陣                         │
│                                                                     │
│  高     ┌─────────────────────────────────────────┐                │
│  客     │                                         │                │
│  製     │       自建（Gemini API + ADK）            │                │
│  化     │       完全控制，最大彈性                  │                │
│  需     │       需要 AI 工程師維護                  │                │
│  求     └─────────────────────────────────────────┘                │
│         ┌─────────────────────────────────────────┐                │
│         │                                         │                │
│  中     │    Vertex AI Search / Agent Builder      │                │
│         │    Google 管 Infra，你管業務邏輯          │                │
│         │    需要懂 API 和配置                      │                │
│         └─────────────────────────────────────────┘                │
│         ┌─────────────────────────────────────────┐                │
│  低     │                                         │                │
│         │    Vertex AI Agent Builder（低代碼）     │                │
│         │    UI 配置，最快上線                      │                │
│         │    彈性最低                              │                │
│         └─────────────────────────────────────────┘                │
│              低                 →                高                │
│                         規模 / 複雜度                               │
└────────────────────────────────────────────────────────────────────┘
```

**面試的正確回答方向：** 不說哪個最好，說「在什麼條件下選哪個」。

---

## 二、Vertex AI Agent Builder：何時用，何時不用

### 它是什麼

```
Vertex AI Agent Builder = 低代碼的 AI Agent 和 RAG 建構平台

主要功能：
  ├── 資料儲存（Data Store）：上傳文件、網頁、結構化資料
  ├── 搜尋（Search）：Google 等級的企業搜尋，自動建索引
  ├── 對話流程（Playbooks）：設計多輪對話邏輯，不需要寫程式
  └── Agent 整合：連接外部 Tool、API、資料庫
```

### 何時應該用

```
✅ 適合用 Agent Builder 的場景：

  場景 1：IT 部門想要快速上線內部知識庫問答
    → 上傳文件到 Data Store，30 分鐘內有可 Demo 的 Chatbot

  場景 2：客服 FAQ Bot，邏輯不複雜
    → Playbooks 設計對話流，業務人員可以自己維護

  場景 3：客戶要 POC 但工期只有兩週
    → Agent Builder 比自建快 10 倍

  場景 4：客戶沒有 AI 工程師
    → Agent Builder 不需要維護 Embedding Pipeline、Vector DB、Prompt 工程
```

### 何時不應該用（更重要）

```
❌ Agent Builder 的天花板：

  限制 1：Retrieval 邏輯不可自定義
    你不能換 Embedding 模型、調整 Chunking 策略、加自己的 Reranker
    → 如果 Retrieval 品質不夠，你沒有辦法深度優化

  限制 2：複雜的 Multi-Agent 工作流支援有限
    Agent Builder 適合單 Agent + 工具，
    複雜的 Sequential/Parallel 多 Agent 協調要自己搭

  限制 3：自定義 Auth 和 RBAC 有限
    如果客戶需要「不同部門看不同文件」的細粒度控制，
    Agent Builder 的 ACL 功能可能不夠

  限制 4：Output 格式不完全可控
    如果客戶需要特定 JSON 格式的結構化輸出，
    Agent Builder 的自定義程度有限

FDE 的表達方式：
「Agent Builder 讓你快速驗證 AI 能不能解決這個問題。
 如果 POC 成功，我們再評估是否需要遷移到 ADK 自建，
 以獲得更精確的 Retrieval 控制和更複雜的工作流能力。」
```

---

## 三、Vertex AI Search vs DIY RAG：根本差異

### Vertex AI Search 是什麼

```
Vertex AI Search（前身 Enterprise Search）=
Google 把自家搜尋技術打包成企業 API 服務

特點：
  ├── Unstructured Data（文件、網頁、PDF）
  ├── Structured Data（BigQuery 資料表、數據集）
  ├── Website Search（對公開網頁建索引）
  └── Blended Search（混合上述三種）

和 DIY RAG 的根本差異：

  Vertex AI Search                DIY RAG Pipeline
  ──────────────────────────────────────────────────────
  Google 管 Embedding 模型         你選 Embedding 模型
  Google 管 Vector Index           你管 Vector DB（Pinecone/pgvector）
  Google 管 Chunk 策略             你設計 Chunk 策略
  Google 管 Hybrid Search          你實作 BM25 + Vector 融合
  Google 管 Reranking              你選 Reranker 模型
  你不知道內部怎麼運作              你完全掌握每個環節
  準確率「夠好」但不可深度調整      準確率可以不斷迭代優化
```

### 哪些場景選 Vertex AI Search

```
✅ 選 Vertex AI Search 的條件：

  條件 1：搜尋品質「夠好」就行，不需要極致優化
  條件 2：資料量大（百萬文件級別），不想自己管索引
  條件 3：有 BigQuery 資料需要和文件搜尋一起做
  條件 4：需要快速上線，沒有時間建 Pipeline
  條件 5：客戶沒有 AI 工程師維護 Vector DB

❌ 選 DIY RAG 的條件：

  條件 1：需要特定 domain 的 Embedding 模型（例如法律、醫療）
  條件 2：Retrieval 準確率不達標，需要自己 debug 和優化
  條件 3：需要自定義 Reranker 或 Hybrid Search 權重
  條件 4：需要細粒度的 RBAC（文件行 / 欄位層級）
  條件 5：資料來源非常客製化（例如：即時串流資料）
```

---

## 四、Gemini API 的四個關鍵特性

這是面試中最常被忽略但最重要的 Gemini 工程知識。

### 特性一：system_instruction

```
用途：設定 LLM 的角色、行為規則、輸出格式——在所有 user turn 之前執行

和 system prompt 的差別：
  傳統 system prompt 放在 messages[0] 裡（role: system）
  Gemini 的 system_instruction 是獨立的參數，不佔 context window 的 message slot

設計原則：
  ├── 角色定義（「你是一位保險理賠助理」）
  ├── 行為規則（「只根據查到的文件回答，不確定時說不知道」）
  ├── 輸出格式（「回答要包含：結論、依據、建議下一步」）
  └── 安全規範（「不討論競品，不提供個人財務建議」）

工程注意事項：
  system_instruction 支援 Context Caching（見特性四），
  如果 instruction 很長（1000+ tokens），建議 cache 以節省成本
```

### 特性二：原生 Function Calling（Tool Use）

```
Gemini 的 Function Calling 宣告方式：

  Tool 宣告 = JSON Schema 描述函數的名稱、說明、參數

  function_declarations: [
    {
      name: "query_policy_database",
      description: "查詢保險保單詳細資訊，包含保障範圍和理賠限額。
                    當用戶詢問保單內容時使用。",
      parameters: {
        type: "object",
        properties: {
          policy_id: {
            type: "string",
            description: "保單號碼，格式：POL-XXXXXX"
          },
          query_type: {
            type: "string",
            enum: ["coverage", "limit", "exclusion"],
            description: "查詢類型"
          }
        },
        required: ["policy_id"]
      }
    }
  ]

Tool Choice 控制（重要設計細節）：
  AUTO   → Gemini 自己決定要不要呼叫 Tool（預設）
  ANY    → 強制呼叫某個 Tool（適合：每次都要查資料庫的場景）
  NONE   → 不允許呼叫 Tool（適合：只要文字回答的場景）

Parallel Function Calling：
  Gemini 支援在一次回應中同時宣告多個 Tool Call
  → 實現 Fan-out 查詢，不需要等前一個完成才能宣告下一個
  → 大幅降低 Multi-Tool 場景的延遲
```

### 特性三：Grounding（外部知識錨定）

```
兩種 Grounding 方式：

Grounding with Google Search（即時網路資訊）：
  LLM 回答時自動搜尋 Google，把搜尋結果作為 context
  → 適合：需要即時資訊（新聞、最新文件、即時股價）
  → 回應包含 grounding_metadata（引用了哪些網頁）
  → 代價：增加 latency（網路搜尋時間）

Grounding with Vertex AI Search（企業內部知識庫）：
  LLM 回答時自動查詢你的 Vertex AI Search Data Store
  → 適合：企業知識庫問答（不想自建 RAG Pipeline 但要引用內部文件）
  → 和 Vertex AI Search 深度整合，不需要額外 Retrieval 代碼

兩者的根本差異：
  Google Search Grounding → 查公開網路，用於即時/外部知識
  Vertex AI Search Grounding → 查你自己的文件，用於企業內部知識

面試回答：
「Grounding 是 Gemini 的原生 RAG 機制。
 對於需要即時資訊的場景，用 Google Search Grounding；
 對於企業內部文件，用 Vertex AI Search Grounding。
 相比自建 RAG Pipeline，Grounding 讓你不需要管 Embedding 和 Retrieval，
 但代價是對 Retrieval 邏輯的控制程度較低。」
```

### 特性四：Context Caching（成本優化的關鍵）

```
原理：
  把不常改變的「固定 context」（System Prompt、長文件、FAQ）
  預先送給 Gemini 處理並快取
  後續 request 引用 cache，只需支付 cache storage 費用（比正常 input token 便宜）

費用對比（參考）：
  正常 input token：$3.50 / 1M tokens（Gemini 1.5 Pro）
  Cache storage：  $1.00 / 1M tokens / hour
  Cache hit read： $0.875 / 1M tokens（75% 折扣）

適合 Cache 的內容：
  ├── System Instruction（如果超過 1,000 tokens）
  ├── 固定的 FAQ 文件（不常更新的知識庫）
  ├── 長的 few-shot examples
  └── 大型 PDF 或合約文件（先 cache，多次問答）

Cache 的設計限制：
  ├── 最小 cache 大小：1,024 tokens（小於這個用正常 token 更便宜）
  ├── Cache 有 TTL（存活時間），到期自動刪除
  └── Cache 不跨 model 版本共享（換模型版本需要重新建 cache）

工程設計示意：

  建立 Cache（一次性）：
  cached_content = caching.CachedContent.create(
      model="gemini-1.5-pro-001",
      contents=[system_prompt + faq_documents],
      ttl=timedelta(hours=24)
  )

  後續 request 引用（重複使用）：
  response = model.generate_content(
      user_question,
      cached_content=cached_content
  )
```

---

## 五、企業 AI 系統的 GCP 部署架構

這是面試最容易被忽略但 FDE 必須能說清楚的部分。

### 完整生產架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                   企業 AI 系統 GCP 部署架構                           │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  用戶層                                                       │    │
│  │  Browser / Mobile / Slack / Internal Portal                  │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │ HTTPS                              │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  入口層                                                       │    │
│  │  Cloud Load Balancing → Cloud Armor（WAF + DDoS 防護）        │    │
│  │  → API Gateway / Apigee（Auth、Rate Limiting、API 版本管理）   │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  Agent 執行層                                                  │    │
│  │                                                               │    │
│  │  選項 A：Cloud Run（Serverless）                               │    │
│  │    ├── ADK Agent 包成 Container + FastAPI                     │    │
│  │    ├── Auto Scale 0 to N（流量低時不計費）                     │    │
│  │    └── 適合：週期性、突發流量的 Agent 服務                     │    │
│  │                                                               │    │
│  │  選項 B：GKE（Kubernetes）                                     │    │
│  │    ├── 複雜的 Agent 工作流，需要 persistent workers            │    │
│  │    ├── 支援 GPU workloads（自建模型推論）                       │    │
│  │    └── 適合：高流量、需要 Fine-grained Scaling 的場景          │    │
│  │                                                               │    │
│  │  選項 C：Vertex AI Agent Engine（全託管）                      │    │
│  │    ├── ADK Agent 直接部署，不需要管 Container                  │    │
│  │    └── 適合：標準 ADK Agent，想要最少維護成本                  │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  AI 服務層                                                    │    │
│  │  Vertex AI Gemini API（LLM）                                  │    │
│  │  Vertex AI Embedding（text-embedding-004）                    │    │
│  │  Vertex AI Vector Search（或 AlloyDB pgvector）               │    │
│  │  Vertex AI Search（企業知識庫）                               │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  資料層                                                        │    │
│  │  Cloud Storage（文件、圖片）                                   │    │
│  │  Cloud SQL / AlloyDB（結構化資料）                             │    │
│  │  BigQuery（分析、日誌、評估資料集）                             │    │
│  │  Firestore（Agent Session State）                             │    │
│  │  Secret Manager（API Keys、憑證）                             │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  可觀測性層                                                    │    │
│  │  Cloud Logging（所有服務日誌集中）                             │    │
│  │  Cloud Monitoring（Metrics、Alerting）                        │    │
│  │  Cloud Trace（分散式追蹤，找延遲瓶頸）                        │    │
│  │  Cloud Audit Logs（誰呼叫了什麼 AI API，合規用）              │    │
│  └──────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 各 GCP 服務的選型邏輯

```
服務選型問題              推薦服務              原因
────────────────────────────────────────────────────────────────────
Agent 執行環境            Cloud Run             Serverless，Auto Scale，
（無 GPU 需求）                                  最適合 ADK Agent
Agent 執行環境            GKE                   需要 persistent state、
（複雜 Infra）                                   GPU、複雜 Scaling
向量資料庫                Vertex AI Vector      GCP 原生，Gemini 直接整合
（大規模）                Search
向量資料庫                AlloyDB pgvector      已有 PostgreSQL、成本敏感、
（中小規模）                                     需要 SQL 結合 vector
企業文件搜尋              Vertex AI Search      不想建 RAG Pipeline，
                                               內容更新不頻繁
Session 狀態             Firestore             ADK 原生支援，自動持久化
API 管理                 Apigee                企業級 API Gateway，
                                               支援 OAuth、Quota、Analytics
安全敏感資料              Secret Manager        API Keys、Service Account Keys
Container 存放           Artifact Registry     GCP 原生，整合 Cloud Build
```

---

## 六、Model Garden：FDE 需要知道的部分

```
Model Garden 是 Vertex AI 的模型中心，包含三類模型：

類型 1：Google 模型
  Gemini 系列（Gemini 2.0 Flash、Gemini 1.5 Pro）
  Gemma 系列（開源，可自行部署和微調）
  Imagen（圖像生成）

類型 2：第三方模型
  Llama（Meta）、Mistral、Claude（Anthropic）等
  可以在 Vertex AI 上直接呼叫，不需要自己管 Infra

類型 3：Fine-tuned 模型
  你自己的 Fine-tuned Gemma 或 Llama，部署到 Vertex AI Endpoints

FDE 常被問的問題：

Q：客戶說他們要用開源模型（不用 Gemini），你怎麼回應？
A：Vertex AI 上可以部署 Llama / Mistral 等開源模型。
   Google 的 Gemma 是完全開源且 Google 支援，
   可以在 Vertex AI 上管理和部署，
   同時保留完整的控制權和資料隱私。

Q：Fine-tuning 在哪裡做？
A：Vertex AI 提供 Supervised Fine-Tuning（SFT）服務，
   支援 Gemini 和 Gemma 的 fine-tuning。
   訓練在 Google 的基礎設施上，你提供訓練資料（JSONL 格式），
   Google 管 GPU cluster 和訓練流程。
   Fine-tuned 模型部署到 Vertex AI Endpoints，
   和 Gemini API 用同樣的方式呼叫。
```

---

## 七、面試官地雷題

**地雷 1：「Vertex AI Search 和自建 RAG 的 Retrieval 品質哪個好？」**

```
答：不能一概而論。
    Vertex AI Search 用的是 Google 的搜尋技術，
    對通用文件搜尋效果很好（Google 自己每天在優化）。
    但它是 black box——你不知道 Embedding 模型、Chunk 策略、Reranking 算法。
    如果你的 domain 很特殊（法律條文、醫療術語、高度技術性文件），
    domain-specific embedding + 客製化 chunking 的 DIY RAG
    通常可以通過調優超過 Vertex AI Search。
    推薦流程：先用 Vertex AI Search 快速驗證，
    如果 Retrieval 準確率不達標，再考慮遷移到 DIY RAG。
```

**地雷 2：「Context Caching 有什麼限制？不是越多 cache 越好嗎？」**

```
答：三個主要限制：
    1. 最小 cache 大小 1,024 tokens——小於這個，cache storage 費用
       比直接打 input token 還貴
    2. Cache 有 TTL，到期要重建——動態內容頻繁更新的場景，
       cache 維護成本反而高
    3. Cache 不跨模型版本——如果你從 gemini-1.5-pro-001 升級到 002，
       所有 cache 要重建
    適合 cache 的：長且穩定的 system prompt、不常更新的 FAQ 文件
    不適合 cache 的：每次 request 都會變化的 context
```

**地雷 3：「Gemini 的 Grounding with Google Search 和 RAG 有什麼本質差別？」**

```
答：架構層次不同。
    RAG 是你自己設計的系統：你管 Embedding、Vector DB、Retrieval、Context Injection。
    Grounding 是 Gemini 原生的機制：LLM 在生成時自動觸發搜尋，搜尋結果直接進入推理。
    關鍵差異：
    RAG 用你自己的 Vector DB（私有知識），可以控制 Retrieval 的每個細節。
    Google Search Grounding 查公開網路，你無法控制搜尋結果的來源和排序。
    Vertex AI Search Grounding 查你的 Data Store（私有），但搜尋邏輯是 black box。
    實務選擇：需要精確控制 Retrieval 的場景 → 自建 RAG；
    快速整合即時網路資訊 → Google Search Grounding；
    快速整合企業文件但不需要深度優化 → Vertex AI Search Grounding。
```

**地雷 4：「Cloud Run 和 GKE 部署 Agent，你怎麼選？」**

```
答：看兩個維度：
    流量模式：
      突發、週期性、低底線流量 → Cloud Run（Scale to Zero，省成本）
      穩定高流量、需要 warm 實例 → GKE（Deployment with HPA）
    系統複雜度：
      標準 HTTP 服務，stateless → Cloud Run
      需要 Persistent Workers（例如：長時間執行的 Agent）、
      GPU workloads、複雜的服務間通信 → GKE
    對大多數 FDE 場景（API-based Agent，週期性使用）→ Cloud Run 是預設選擇。
```

---

## 八、面試回答完整示範

```
面試官問：「Agent Builder、Vertex AI Search、自建 RAG——三條路怎麼選？」

框架先行（30 秒）：
「這不是三選一的問題，而是根據客戶的需求和能力選的。
 我的框架是：要多快上線？要多高的 Retrieval 準確率？
 客戶有沒有 AI 工程師維護？」

三條路的條件（2 分鐘）：
「Agent Builder：最快，2 週可以上線，
 但 Retrieval 邏輯是 black box，品質不能深度調整。
 適合：沒有 AI 工程師、先驗證業務價值的 POC。

 Vertex AI Search + Gemini Grounding：中間路線，
 不需要管 Embedding 和 Vector DB，但搜尋邏輯還是 black box。
 適合：資料量大、不需要特殊 domain 優化、
 客戶願意接受 Google 的搜尋品質標準。

 自建 RAG（ADK + Vertex AI Embedding + pgvector）：最慢，
 但每個環節都可以優化——Embedding 選型、Chunking 策略、Hybrid Search、Reranker。
 適合：Retrieval 準確率要求高、domain 特殊（法律/醫療/金融）、
 有 AI 工程師維護的長期系統。」

建議路徑（30 秒）：
「我的建議是：先用 Agent Builder 做 POC，
 2 週內驗證業務價值。
 如果客戶對品質滿意，就繼續在 Agent Builder 上擴展。
 如果 Retrieval 品質不達標，再遷移到 Vertex AI Search 或自建 RAG，
 那時候我們也有了真實的測試資料，遷移有具體的優化方向。」
```

---

**Google FDE 的核心價值不是說「Google 的東西最好」，**  
**而是說「在你的場景下，Google 的哪個選項給你最好的 ROI，以及為什麼。」**
