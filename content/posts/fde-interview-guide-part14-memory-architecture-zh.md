---
title: "FDE 面試準備指南（十四）：RKK 實戰——AI Agent Memory 架構設計"
date: 2026-06-03T13:00:00+08:00
draft: false
description: "以系統設計視角拆解 AI Agent 的 Memory 架構：為什麼需要四種記憶、每種記憶解決什麼問題、怎麼組合、以及記憶帶來的工程挑戰——含完整架構圖與選型決策框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Memory", "Architecture", "Vector Database", "LangGraph", "RAG", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> LLM 是無狀態的，但用戶是有狀態的。  
> Memory 系統要解決的問題只有一個：  
> **讓無狀態的 LLM 表現得像是「記得你」。**  
> 怎麼設計這個橋樑，以及這個橋樑的代價——是這篇的核心。

---

## 一、核心問題：為什麼需要不同類型的 Memory

沒有 Memory 的 Agent 每次對話從零開始：

```
Session 1：
  User: "我主要用 Python，偏好簡短的回答"
  Agent: "好的！" （記不住）

Session 2（三天後）：
  User: "幫我寫一個排序函數"
  Agent: "您好！請問您用哪種程式語言？"
         ↑
    明明說過了，還在問
```

但「把所有對話都記住」也不可行：

```
問題 1：儲存量
  10K 用戶 × 每天 10 輪 × 365 天 = 3,650 萬條對話記錄

問題 2：Context 限制
  把所有歷史塞進 LLM context → 超過 context window

問題 3：相關性
  3 年前討論的內容，現在可能完全不相關
```

**結論：需要多種記憶類型，各自解決不同的問題。**

---

## 二、四種記憶類型：各解決什麼問題

```
問題                          解決方案
─────────────────────────────────────────────────────
當前對話的臨時狀態？    →    Working Memory（工作記憶）
                             LLM context window
                             生命週期：當次對話

記得過去發生過什麼？    →    Episodic Memory（情節記憶）
                             向量化的對話歷史
                             生命週期：跨 session，可衰減

記得這個人是什麼樣的人？→    Semantic Memory（語意記憶）
                             結構化的 user profile
                             生命週期：持久化，主動更新

知道怎麼做某件事？      →    Procedural Memory（程序記憶）
                             Few-shot examples / Fine-tuning
                             生命週期：模型層，最持久
```

---

## 三、完整 Memory 架構圖

```
用戶請求
    │
    ▼
┌──────────────────────────────────────────────┐
│            Memory Retrieval Layer            │
│                                              │
│  ┌──────────────────────┐                    │
│  │  Semantic Memory     │ ← 用戶偏好、profile │
│  │  (Structured DB)     │   每次對話都載入    │
│  └──────────────────────┘                    │
│              +                               │
│  ┌──────────────────────┐                    │
│  │  Episodic Memory     │ ← 相關歷史片段      │
│  │  (Vector DB)         │   按語意相似度召回  │
│  └──────────────────────┘                    │
└──────────────────┬───────────────────────────┘
                   │ 組合成 Working Memory
                   ▼
┌──────────────────────────────────────────────┐
│             Working Memory                   │
│             (LLM Context Window)             │
│                                              │
│  [System Prompt]                             │
│  [User Profile from Semantic Memory]         │
│  [Relevant History from Episodic Memory]     │
│  [Current Conversation]                      │
│  [Current Query]                             │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
                  LLM
                   │
                   ▼
                回應
                   │
         （對話結束後，非同步）
                   ▼
┌──────────────────────────────────────────────┐
│            Memory Update Layer               │
│                                              │
│  ┌────────────────────────────┐              │
│  │ 提取重要資訊               │              │
│  │ → 更新 Semantic Memory     │ ← 偏好、事實 │
│  └────────────────────────────┘              │
│  ┌────────────────────────────┐              │
│  │ 壓縮對話摘要               │              │
│  │ → 存入 Episodic Memory     │ ← 做了什麼  │
│  └────────────────────────────┘              │
└──────────────────────────────────────────────┘
```

**關鍵設計決策：Memory Update 是非同步的**  
不在請求路徑上——避免增加用戶感知延遲。

---

## 四、各類型記憶的設計細節

### Working Memory：Context 組裝策略

```
Context 組裝優先順序（有限空間的分配）：

總預算：128K tokens（以 GPT-4o 為例）

┌──────────────────────┬───────────────┐
│ 區塊                 │ Token 預算    │
├──────────────────────┼───────────────┤
│ System Prompt        │ ~500 (固定)   │
│ User Profile         │ ~300 (固定)   │
│ Procedural Examples  │ ~1,000 (固定) │
│ Episodic Recall      │ ~2,000 (彈性) │
│ Current Conversation │ ~剩餘        │
│ Output Reserve       │ ~4,000 (保留) │
└──────────────────────┴───────────────┘

當 Conversation 過長時 → 壓縮或截斷，但優先保留固定區塊
```

---

### Episodic Memory：向量化存取

```
對話發生
    │
    ▼
[對話摘要提取]          ← LLM 非同步提取關鍵資訊
    │
    ▼
[Embedding 生成]        ← 轉換為向量表示
    │
    ▼
┌────────────────────────────────┐
│  Vector Database               │
│                                │
│  memory_id: m_001              │
│  user_id:   u_123              │
│  vector:    [0.12, -0.34, ...] │
│  content:   "用戶詢問 Q4 銷售  │
│              數字，發現資料庫   │
│              有延遲問題"        │
│  importance: 0.72              │
│  timestamp:  2026-03-15        │
└────────────────────────────────┘
          │
          │ 下次對話時
          ▼
[Query Embedding]  ← 當前問題轉向量
          │
          ▼
[Similarity Search] → 召回最相關的 top-k 記憶
```

**重要設計：Importance Score**

不是所有記憶都值得保留，用 LLM 判斷重要性：

```
高重要性（0.8+）：
  ├── 用戶明確表達的偏好（"我不喜歡..."）
  ├── 未解決的問題（"下次要繼續處理..."）
  └── 重要的決定（"確認採用方案 B"）

低重要性（< 0.3）：
  ├── 閒聊（"謝謝"、"好的"）
  ├── 可以從公開資訊取得的問題（不需要記住回答了什麼）
  └── 重複性的例行查詢
```

---

### Semantic Memory：結構化 Profile

```
User Profile 結構：

┌─────────────────────────────────────────────────────┐
│  user_id: u_123                                     │
│                                                     │
│  Identity                                           │
│  ├── name: "Alice"                                  │
│  ├── role: "Data Engineer"                          │
│  └── department: "Analytics"                        │
│                                                     │
│  Preferences（從對話中學習）                          │
│  ├── language: "繁體中文"                            │
│  ├── response_style: "簡潔，要有範例"               │
│  └── technical_level: "intermediate"               │
│                                                     │
│  Context                                            │
│  ├── tools: ["Python", "dbt", "BigQuery"]           │
│  ├── active_projects: ["data-pipeline-v2"]          │
│  └── open_issues: [                                 │
│        {issue: "dbt 模型跑太慢", since: "2026-05"} │
│      ]                                              │
│                                                     │
│  Meta                                               │
│  └── last_updated: "2026-06-01"                    │
└─────────────────────────────────────────────────────┘
```

---

## 五、四大工程挑戰與對應設計

### 挑戰一：記憶衝突

```
問題情境：
  2026-01：User profile 記載 "技術等級：初學者"
  2026-06：用戶已經成長為中級工程師

如果不更新 → Agent 一直給太基礎的解釋 → 用戶沮喪

解決策略：
  ├── 新記憶優先（衝突時以最新記錄為準）
  ├── Confidence score（多次確認才更新 profile）
  └── 主動重確認（6 個月未更新的欄位，主動詢問）
```

### 挑戰二：記憶過時（Staleness）

```
不同記憶欄位的「半衰期」不同：

欄位               建議更新週期    觸發條件
─────────────────────────────────────────────
技術偏好           90 天          對話中有新工具提及
活躍專案           30 天          專案名稱長時間不出現
聯絡資訊           365 天         用戶主動更新
open_issues        自動關閉       問題被標記為解決

設計：為每個欄位設 decay rule，過期後主動重確認
      而不是等到用戶抱怨
```

### 挑戰三：隱私權

```
用戶的記憶控制權：

┌─────────────────────────────────────────────┐
│  Memory Privacy API                         │
│                                             │
│  GET  /memory/{user_id}                     │
│       → 讓用戶看到 Agent 記了什麼           │
│                                             │
│  DELETE /memory/{user_id}                   │
│       → 全部刪除（GDPR right to erasure）   │
│                                             │
│  DELETE /memory/{user_id}/episodic          │
│       → 只刪對話歷史，保留 profile          │
│                                             │
│  PUT /memory/{user_id}/profile              │
│       → 用戶直接修改自己的 profile          │
└─────────────────────────────────────────────┘
```

### 挑戰四：記憶召回的精確性 vs 完整性

```
Precision vs Recall 的 trade-off：

相似度 threshold = 0.95（高精確）：
  + 召回的記憶高度相關
  - 可能漏掉有用但相似度稍低的記憶
  → 適合：用戶不想看到不相關的「舊事」

相似度 threshold = 0.80（高召回）：
  + 相關的記憶幾乎都能找到
  - 召回太多不相關記憶，污染 context
  → 適合：確保重要記憶不會被遺漏

實務建議：
  重要記憶（importance > 0.8）→ threshold 0.80，寧可多召回
  一般記憶（importance < 0.5）→ threshold 0.92，只召回高相關
```

---

## 六、選型決策：什麼場景用什麼記憶

```
你的 Agent 需要什麼？
        │
        ├── 記住當前對話的狀態？
        │       → Working Memory only（默認已有）
        │
        ├── 記住用戶是誰、偏好什麼？
        │       → + Semantic Memory
        │         用 PostgreSQL / Firestore 存 profile
        │
        ├── 記住「幾個月前說過什麼」？
        │       → + Episodic Memory
        │         用 Pinecone / Weaviate / pgvector 存向量
        │
        ├── 需要跨用戶共享的知識（最佳實踐、FAQ）？
        │       → + Procedural Memory（Few-shot in prompt）
        │         或 Fine-tuning（更持久）
        │
        └── 全部都要？
                → 混合架構
                  注意：複雜度線性上升，從最小可行的開始
```

---

## 七、快速複習卡

```
四種記憶類型：
  Working Memory   → Context window，當次對話，無需額外設計
  Episodic Memory  → 向量 DB，跨 session 歷史，按相似度召回
  Semantic Memory  → 結構化 DB，user profile，每次對話載入
  Procedural Memory → Few-shot / Fine-tuning，模型層，最持久

四大工程挑戰：
  衝突 → 新記憶優先 + confidence score
  過時 → decay rule + 主動重確認
  隱私 → Memory API（查看、刪除、修改）
  精確性 → 依 importance 調整 recall threshold

架構流程：
  請求 → 載入 Semantic + 召回 Episodic → Working Memory → LLM
       → 對話結束後非同步更新 Semantic + Episodic
```

---

**系列導覽：**  
← [（十三）RKK 實戰：Prompt Injection 攻防與 Agent 安全](../fde-interview-guide-part13-prompt-injection-zh/)  
→ [（十五）RKK 實戰：Agent 規模化與 Cache 策略](../fde-interview-guide-part15-scale-cache-zh/)
