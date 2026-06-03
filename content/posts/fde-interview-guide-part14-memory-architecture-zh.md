---
title: "FDE 面試準備指南（十四）：RKK 實戰——AI Agent Memory 架構設計"
date: 2026-06-03T13:00:00+08:00
draft: false
description: "以 Google AI 工程師兼面試官的視角，深度拆解 AI Agent 的 Memory 架構：四種記憶類型（Working、Episodic、Semantic、Procedural）、跨 session 記憶設計、向量記憶庫，以及企業級 Agent 的 memory 選型決策"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Memory", "Architecture", "Vector Database", "LangGraph", "RAG", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> Memory 是 Agent 從「一次性工具」變成「持續學習的助手」的關鍵。  
> 面試官想知道的不只是你知道向量資料庫，  
> 而是你知道什麼情況下該用什麼記憶，以及記憶會帶來什麼風險。

---

## 一、為什麼 Memory 架構是 RKK 必考題

沒有 memory 的 Agent，每次對話都從零開始。對企業客戶來說，這意味著：

- 客服 Agent 每次都要重新問用戶基本資訊
- 銷售 Agent 不記得上次和客戶聊了什麼
- 程式碼助手不知道專案的技術棧和偏好

面試官問法：

> *「你有一個企業客戶，他們想讓 Agent 記得每個員工的偏好和過去的互動。你怎麼設計 memory 系統？」*

---

## 二、四種記憶類型

參考認知科學的記憶分類，Agent 的 memory 也可以分成四種：

```
Agent Memory 四類型
├── Working Memory（工作記憶）    ← 當前 context（當次對話）
├── Episodic Memory（情節記憶）   ← 過去的互動歷史
├── Semantic Memory（語意記憶）   ← 結構化知識（用戶偏好、實體關係）
└── Procedural Memory（程序記憶） ← 如何完成特定任務的知識
```

### 類比 vs 系統實作

| 記憶類型 | 類比 | 系統實作 | 存活時間 |
|---------|------|---------|---------|
| Working Memory | 你現在腦子裡在想的 | LLM context window | 當次對話 |
| Episodic Memory | 你記得三個月前和朋友的對話 | 對話歷史資料庫、向量索引 | 跨 session |
| Semantic Memory | 你知道「台北」是城市 | 結構化 profile、知識圖譜 | 持久化 |
| Procedural Memory | 你騎腳踏車不需要思考 | Few-shot examples、Fine-tuning | 模型層 |

---

## 三、Working Memory：Context Window 的管理

（詳見第十篇 Context Management，這裡只做概要）

Working Memory 就是 LLM 的 context window。每次對話的臨時狀態：

```python
# Working Memory = 當前 session 的所有資訊
working_memory = {
    "system_prompt": "你是一個客服 Agent...",
    "user_profile": {...},          # 從 Semantic Memory 載入
    "conversation_history": [...],  # 當次對話
    "retrieved_context": [...],     # 從 Episodic/Semantic Memory 檢索
    "tool_results": [...],          # 工具執行結果
    "current_task_state": {...}     # 任務進行狀態
}
```

---

## 四、Episodic Memory：對話歷史的持久化

### 設計問題

面試官問：

> *「用戶和你的 Agent 對話了 6 個月，你怎麼讓 Agent 還記得 6 個月前的重要對話？」*

**方案：向量化的對話記憶庫**

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class EpisodicMemory:
    memory_id: str
    user_id: str
    session_id: str
    timestamp: datetime
    content: str          # 對話摘要或重要片段
    embedding: list       # 向量表示，用於相似度搜尋
    importance_score: float  # 0-1，重要程度
    metadata: dict        # 額外資訊：tags、entities、emotion 等

class EpisodicMemoryStore:
    def __init__(self, vector_store, llm, embedder):
        self.vector_store = vector_store
        self.llm = llm
        self.embedder = embedder
    
    def save_conversation(self, user_id: str, conversation: list[dict]) -> EpisodicMemory:
        # 1. 用 LLM 提取重要資訊
        summary_prompt = f"""
        請分析以下對話，提取最重要的資訊：
        1. 用戶達成了什麼目標（或沒達成）
        2. 用戶表達的偏好或需求
        3. 任何重要的決定或承諾
        
        對話：{self._format_conversation(conversation)}
        
        請以 JSON 格式回覆：
        {{
            "summary": "一句話摘要",
            "user_preferences": [...],
            "unresolved_issues": [...],
            "importance": 0.0 to 1.0
        }}
        """
        extracted = self.llm.generate_json(summary_prompt)
        
        # 2. 生成 embedding
        content = extracted["summary"]
        embedding = self.embedder.embed(content)
        
        # 3. 存入向量資料庫
        memory = EpisodicMemory(
            memory_id=generate_id(),
            user_id=user_id,
            session_id=generate_id(),
            timestamp=datetime.now(),
            content=content,
            embedding=embedding,
            importance_score=extracted["importance"],
            metadata={
                "user_preferences": extracted["user_preferences"],
                "unresolved_issues": extracted["unresolved_issues"]
            }
        )
        
        self.vector_store.upsert(memory)
        return memory
    
    def recall(self, user_id: str, current_context: str, top_k: int = 3) -> list[EpisodicMemory]:
        """根據當前 context 召回相關的過去記憶"""
        query_embedding = self.embedder.embed(current_context)
        
        # 只搜尋這個用戶的記憶
        results = self.vector_store.query(
            vector=query_embedding,
            filter={"user_id": user_id},
            top_k=top_k
        )
        
        # 按重要程度和時間加權排序
        def score(memory):
            recency_score = self._recency_decay(memory.timestamp)
            return memory.importance_score * 0.6 + recency_score * 0.4
        
        return sorted(results, key=score, reverse=True)
    
    def _recency_decay(self, timestamp: datetime) -> float:
        """越近期的記憶分數越高"""
        days_ago = (datetime.now() - timestamp).days
        return max(0, 1 - days_ago / 180)  # 6 個月後衰減到 0
```

---

## 五、Semantic Memory：結構化用戶知識

Episodic Memory 是「記得發生過什麼」，Semantic Memory 是「記得這個人是什麼樣的人」：

```python
@dataclass
class UserProfile:
    user_id: str
    
    # 基本資訊
    name: str
    role: str           # 職位
    department: str
    
    # 偏好（從對話中學習）
    language_preference: str     # "繁體中文" / "English"
    communication_style: str     # "簡潔" / "詳細"
    technical_level: str         # "beginner" / "intermediate" / "expert"
    
    # 常用工具和系統
    tools: list[str]             # ["Python", "BigQuery", "Looker"]
    active_projects: list[str]
    
    # 未解決的問題
    open_issues: list[dict]
    
    # 最後更新時間
    last_updated: datetime

class SemanticMemoryStore:
    def __init__(self, db):
        self.db = db
    
    def get_profile(self, user_id: str) -> UserProfile:
        return self.db.get(f"profile:{user_id}")
    
    def update_profile(self, user_id: str, updates: dict):
        """根據對話更新 profile"""
        profile = self.get_profile(user_id) or UserProfile(user_id=user_id)
        
        # 用 LLM 判斷是否需要更新哪些欄位
        # 例如：用戶說「我主要用 Python」→ 更新 tools
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.last_updated = datetime.now()
        self.db.set(f"profile:{user_id}", profile)
    
    def extract_profile_updates(self, conversation: list[dict], llm) -> dict:
        """從對話中自動提取 profile 更新"""
        extract_prompt = f"""
        分析以下對話，判斷是否有用戶偏好或資訊可以更新：
        
        對話：{conversation}
        
        JSON 格式，只包含需要更新的欄位：
        """
        return llm.generate_json(extract_prompt)
```

---

## 六、Memory 的四個工程挑戰

面試官不只想聽架構，也想聽你知道挑戰在哪：

### 挑戰一：記憶衝突

```
用戶在 1 月說：「我偏好簡短的回答」
用戶在 6 月說：「請給我詳細的說明」

→ 哪個記憶是真的？
→ 解法：記憶有 timestamp，衝突時以較新的為準；或詢問用戶確認
```

### 挑戰二：記憶過時

```python
class MemoryFreshness:
    DECAY_RULES = {
        "user_preferences": 180,  # 6 個月後可能過時
        "active_projects": 30,    # 1 個月後重新確認
        "contact_info": 365,      # 1 年後可能過時
        "technical_level": 90,    # 3 個月後可能有進步
    }
    
    def is_stale(self, memory_key: str, last_updated: datetime) -> bool:
        days_threshold = self.DECAY_RULES.get(memory_key, 90)
        days_since_update = (datetime.now() - last_updated).days
        return days_since_update > days_threshold
    
    def should_reconfirm(self, profile: UserProfile) -> list[str]:
        """判斷哪些欄位應該主動向用戶確認"""
        stale_fields = []
        for field, _ in profile.__dataclass_fields__.items():
            if self.is_stale(field, profile.last_updated):
                stale_fields.append(field)
        return stale_fields
```

### 挑戰三：隱私與資料權

```python
# 用戶有權刪除自己的 memory
class MemoryPrivacyManager:
    def delete_user_memory(self, user_id: str, memory_type: str = "all"):
        if memory_type == "all":
            self.episodic_store.delete_user(user_id)
            self.semantic_store.delete_user(user_id)
        elif memory_type == "episodic":
            self.episodic_store.delete_user(user_id)
        elif memory_type == "semantic":
            self.semantic_store.delete_user(user_id)
    
    def export_user_memory(self, user_id: str) -> dict:
        """用戶資料可攜性：讓用戶看到系統記了什麼"""
        return {
            "profile": self.semantic_store.get_profile(user_id),
            "conversation_summaries": self.episodic_store.get_all(user_id),
        }
```

### 挑戰四：記憶的精確度 vs 規模

```
精確記憶（存每個字）：
+ 不丟失細節
- 儲存量大，搜尋慢，context 很快填滿

摘要記憶（用 LLM 壓縮）：
+ 小、快、可搜尋
- 可能丟失重要細節，摘要品質依賴 LLM

→ 實務選擇：重要欄位存結構化（Semantic），
  對話存摘要（Episodic），原始對話存 archive（冷儲存）
```

---

## 七、完整的 Memory 架構圖

```
用戶請求進來
     │
     ▼
[Memory Retrieval Layer]
├── 載入 Semantic Memory（用戶 profile）
├── 召回相關 Episodic Memory（過去對話）
└── 組合成 Working Memory context
     │
     ▼
[Agent 執行]（使用 Working Memory）
     │
     ▼
[Memory Update Layer]（對話結束後非同步執行）
├── 提取重要資訊 → 更新 Semantic Memory
└── 壓縮對話摘要 → 存入 Episodic Memory
     │
     ▼
（下次對話時召回）
```

---

## 八、面試答題技巧

被問到 Memory 架構時，主動提出「你的選型邏輯」：

> *「我會先問：這個 Agent 需要幾種記憶？*
>
> *如果只需要在一次對話裡記住狀態，Working Memory 就夠了。*
>
> *如果需要跨 session 記住用戶說過的具體事情，加 Episodic Memory，用向量資料庫讓它可以搜尋。*
>
> *如果需要記住用戶的偏好和屬性，加 Semantic Memory，用結構化的 profile 儲存。*
>
> *我會特別說明挑戰：記憶衝突要以新為準、記憶會過時要定期重確認、用戶有刪除記憶的權利——這些都要在設計時考慮到。」*

---

## 九、快速複習卡

```
四種記憶類型：
├── Working Memory   → context window，當次對話
├── Episodic Memory  → 向量化的歷史對話摘要
├── Semantic Memory  → 結構化 user profile
└── Procedural Memory → few-shot / fine-tuning

四個工程挑戰：
1. 記憶衝突   → 新記憶優先
2. 記憶過時   → decay rules + 主動重確認
3. 隱私權     → 刪除 API + 資料可攜
4. 精確 vs 規模 → 重要用結構化，對話用摘要

架構流程：Retrieval → Working Memory → Agent → Update（非同步）
```

---

**系列導覽：**  
← [（十三）RKK 實戰：Prompt Injection 攻防與 Agent 安全](../fde-interview-guide-part13-prompt-injection-zh/)  
→ [（十五）RKK 實戰：Agent 規模化與 Cache 策略](../fde-interview-guide-part15-scale-cache-zh/)
