---
title: "多 Agent Token 優化系列 pt.2：Prompt Caching 實戰 — 從記憶體快取到 RAG 系統"
date: 2026-03-12T14:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "prompt-caching", "RAG", "vector-database", "cost-optimization", "API", "LLM-optimization"]
summary: "多 Agent Token 優化系列 pt.2：深入探索 Prompt Caching 的實際應用，從 Claude API 原生快取、應用層記憶體快取、到 RAG 系統整合，提供完整程式碼範例，幫助你打造高效低成本的 AI 應用。"
readTime: "30 min"
---

在前一篇文章《多 Agent 系統的 Token 用量調優指南》中，我們介紹了 **Prompt Caching** 作為 Token 優化的首選策略。本文將深入實作層面，探討如何在真實系統中建構完整的快取架構，涵蓋從 Claude API 原生快取到應用層快取、再到 RAG 系統整合的完整解決方案。

---

## 快取架構總覽

在生產環境中，一個完整的 AI 應用快取策略通常包含多個層次：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    多層快取架構                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: Claude API Prompt Caching                                │
│  ├── 快取 System Prompt、工具定義等固定前綴                          │
│  ├── 由 Anthropic 伺服器管理                                        │
│  └── 5 分鐘自動過期                                                 │
│                                                                     │
│  Layer 2: 應用層記憶體快取 (In-Memory Cache)                        │
│  ├── 快取完整 API 回應                                              │
│  ├── 相同輸入直接返回，完全跳過 API 呼叫                            │
│  └── 適用於重複性高的查詢                                           │
│                                                                     │
│  Layer 3: RAG / 向量資料庫快取                                      │
│  ├── 快取文件 Embeddings                                            │
│  ├── 快取 Context 檢索結果                                          │
│  └── 減少重複的 Embedding 計算和相似度搜尋                          │
│                                                                     │
│  Layer 4: 分散式快取 (Redis/Memcached)                              │
│  ├── 跨實例共享快取                                                 │
│  ├── 適用於微服務架構                                               │
│  └── 支援快取失效策略                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1：Claude API 原生 Prompt Caching

### 基本概念

Claude API 的 Prompt Caching 功能允許你快取**訊息前綴**，避免每次 API 呼叫都重新處理相同的內容。這對於包含大量固定內容（如 System Prompt、工具定義、背景知識）的應用特別有效。

```
API 呼叫結構：

┌──────────────────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────┐                  │
│  │ 可快取區域（固定前綴）                  │ ← cache_control │
│  │ • System Prompt                        │                  │
│  │ • 工具定義                             │                  │
│  │ • 背景知識文件                         │                  │
│  │ • Few-shot 範例                        │                  │
│  └────────────────────────────────────────┘                  │
│  ┌────────────────────────────────────────┐                  │
│  │ 動態區域（每次變化）                    │ ← 不快取        │
│  │ • 使用者當前輸入                        │                  │
│  │ • 對話歷史（最近幾輪）                  │                  │
│  └────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

### 基礎實作

```python
import anthropic
from typing import Optional

client = anthropic.Anthropic()

class PromptCacheManager:
    """Claude API Prompt Caching 管理器"""

    def __init__(self, base_system_prompt: str, tools: Optional[list] = None):
        """
        初始化快取管理器

        Args:
            base_system_prompt: 基礎 System Prompt（將被快取）
            tools: 工具定義列表（將被快取）
        """
        self.base_system_prompt = base_system_prompt
        self.tools = tools or []
        self._cache_stats = {
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "total_calls": 0
        }

    def _build_cached_system(self) -> list:
        """構建帶快取控制的 System Content"""
        return [{
            "type": "text",
            "text": self.base_system_prompt,
            "cache_control": {"type": "ephemeral"}
        }]

    def _build_cached_tools(self) -> list:
        """為工具定義添加快取控制"""
        if not self.tools:
            return []

        # 在最後一個工具上添加快取控制點
        cached_tools = self.tools.copy()
        if cached_tools:
            cached_tools[-1] = {
                **cached_tools[-1],
                "cache_control": {"type": "ephemeral"}
            }
        return cached_tools

    def call_with_cache(
        self,
        messages: list,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        additional_system: Optional[str] = None
    ) -> anthropic.types.Message:
        """
        使用 Prompt Caching 進行 API 呼叫

        Args:
            messages: 對話訊息列表
            model: 模型名稱
            max_tokens: 最大輸出 tokens
            additional_system: 額外的動態 System 內容（不快取）

        Returns:
            API 回應
        """
        system_content = self._build_cached_system()

        # 如果有額外的動態內容，追加但不快取
        if additional_system:
            system_content.append({
                "type": "text",
                "text": additional_system
            })

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_content,
            "messages": messages
        }

        # 添加快取的工具定義
        if self.tools:
            kwargs["tools"] = self._build_cached_tools()

        response = client.messages.create(**kwargs)

        # 記錄快取統計
        self._update_stats(response.usage)
        self._cache_stats["total_calls"] += 1

        return response

    def _update_stats(self, usage):
        """更新快取統計資訊"""
        self._cache_stats["cache_creation_tokens"] += getattr(
            usage, "cache_creation_input_tokens", 0
        )
        self._cache_stats["cache_read_tokens"] += getattr(
            usage, "cache_read_input_tokens", 0
        )

    def get_cache_stats(self) -> dict:
        """取得快取統計報告"""
        stats = self._cache_stats.copy()

        if stats["total_calls"] > 1:
            # 計算快取效益
            total_cached = stats["cache_creation_tokens"] + stats["cache_read_tokens"]
            if total_cached > 0:
                stats["cache_hit_rate"] = (
                    stats["cache_read_tokens"] / total_cached * 100
                )
                # 假設快取讀取節省 90% 成本
                stats["estimated_savings_pct"] = (
                    stats["cache_read_tokens"] * 0.9 / total_cached * 100
                )

        return stats


# 使用範例
if __name__ == "__main__":
    # 定義大型 System Prompt（適合快取）
    SYSTEM_PROMPT = """你是一個專業的程式碼助手。

## 你的能力
- 程式碼生成：Python、TypeScript、Go、Rust
- 程式碼審查：安全性、效能、可讀性
- 架構設計：微服務、事件驅動、CQRS

## 輸出格式
所有程式碼回應必須包含：
1. 完整可執行的程式碼
2. 簡要說明
3. 使用範例

## 程式碼風格指南
- 使用有意義的變數名稱
- 保持函數簡短（< 30 行）
- 加入必要的錯誤處理
- 遵循各語言的官方風格指南

[此處可包含更多詳細的背景知識、範例程式碼等...]
"""

    # 定義工具
    TOOLS = [
        {
            "name": "read_file",
            "description": "讀取檔案內容",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "檔案路徑"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "write_file",
            "description": "寫入檔案",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    ]

    # 建立快取管理器
    cache_manager = PromptCacheManager(SYSTEM_PROMPT, TOOLS)

    # 模擬多次呼叫
    queries = [
        "請用 Python 實作一個 LRU Cache",
        "請用 TypeScript 實作一個 Event Emitter",
        "請審查這段程式碼的效能問題"
    ]

    for query in queries:
        response = cache_manager.call_with_cache(
            messages=[{"role": "user", "content": query}]
        )
        print(f"\n查詢：{query[:30]}...")
        print(f"回應長度：{len(response.content[0].text)} 字元")

    # 輸出快取統計
    stats = cache_manager.get_cache_stats()
    print("\n" + "="*50)
    print("快取統計：")
    print(f"  總呼叫次數：{stats['total_calls']}")
    print(f"  快取建立 tokens：{stats['cache_creation_tokens']:,}")
    print(f"  快取讀取 tokens：{stats['cache_read_tokens']:,}")
    if "cache_hit_rate" in stats:
        print(f"  快取命中率：{stats['cache_hit_rate']:.1f}%")
        print(f"  估計節省成本：{stats['estimated_savings_pct']:.1f}%")
```

### 進階：多 Breakpoint 快取策略

對於複雜的 prompt 結構，可以設置多個快取斷點，讓不同頻率變化的內容分別快取：

```python
class MultiBreakpointCacheManager:
    """
    多斷點快取管理器

    支援將 System Prompt 分成多個區塊，每個區塊獨立快取。
    適用於部分內容需要較頻繁更新的場景。
    """

    def __init__(self):
        self.static_context = ""      # 完全靜態（年為單位更新）
        self.semi_static_context = "" # 半靜態（天為單位更新）
        self.session_context = ""     # Session 層級（小時為單位更新）

    def set_static_context(self, content: str):
        """設定完全靜態的背景知識"""
        self.static_context = content

    def set_semi_static_context(self, content: str):
        """設定半靜態的內容（如每日更新的資料摘要）"""
        self.semi_static_context = content

    def set_session_context(self, content: str):
        """設定 Session 層級的 context"""
        self.session_context = content

    def build_system_content(self) -> list:
        """
        構建多斷點快取的 System Content

        結構：
        ┌────────────────────────────┐
        │ 靜態區塊 + cache_control   │ ← 長期快取
        ├────────────────────────────┤
        │ 半靜態區塊 + cache_control │ ← 中期快取
        ├────────────────────────────┤
        │ Session 區塊               │ ← 不快取（每次變化）
        └────────────────────────────┘
        """
        content = []

        # 區塊 1：完全靜態（設置快取斷點）
        if self.static_context:
            content.append({
                "type": "text",
                "text": f"[背景知識]\n{self.static_context}",
                "cache_control": {"type": "ephemeral"}
            })

        # 區塊 2：半靜態（設置第二個快取斷點）
        if self.semi_static_context:
            content.append({
                "type": "text",
                "text": f"[當前狀態]\n{self.semi_static_context}",
                "cache_control": {"type": "ephemeral"}
            })

        # 區塊 3：Session 動態內容（不快取）
        if self.session_context:
            content.append({
                "type": "text",
                "text": f"[Session 資訊]\n{self.session_context}"
            })

        return content

    def call(self, messages: list, **kwargs) -> anthropic.types.Message:
        return client.messages.create(
            model=kwargs.get("model", "claude-sonnet-4-6"),
            max_tokens=kwargs.get("max_tokens", 4096),
            system=self.build_system_content(),
            messages=messages
        )


# 使用範例
cache = MultiBreakpointCacheManager()

# 設定長期不變的背景知識（例如公司政策、產品說明）
cache.set_static_context("""
公司產品線：
- ProductA：企業級資料分析平台
- ProductB：即時監控解決方案
- ProductC：自動化報告系統

技術棧規範：
- 後端：Python 3.11+, FastAPI, PostgreSQL
- 前端：React 18, TypeScript 5
- 基礎設施：AWS, Kubernetes, Terraform
""")

# 設定每日更新的內容（例如今日重點、系統狀態）
cache.set_semi_static_context("""
今日系統狀態：
- ProductA：正常運作
- ProductB：維護中（預計 18:00 恢復）
- ProductC：正常運作

本週重點：
- 正在進行 Q2 效能優化專案
- 禁止部署到生產環境（程式碼凍結期）
""")

# 設定 Session 動態內容
cache.set_session_context("""
當前使用者：工程師 Jerry
角色：Backend Developer
目前任務：修復 API-1234 效能問題
""")
```

---

## Layer 2：應用層記憶體快取

Claude API 的 Prompt Caching 只能減少重複前綴的處理成本，但如果**完全相同的請求**重複出現，我們可以在應用層直接快取整個回應，完全跳過 API 呼叫。

### 基於 LRU Cache 的實作

```python
import hashlib
import json
import time
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import OrderedDict
import threading

@dataclass
class CacheEntry:
    """快取條目"""
    response: Any
    created_at: float
    hit_count: int = 0
    last_accessed: float = field(default_factory=time.time)

class InMemoryResponseCache:
    """
    應用層 LRU 回應快取

    特點：
    - 完全相同的請求直接返回快取結果
    - 支援 TTL（存活時間）
    - 支援最大容量限制（LRU 淘汰）
    - 執行緒安全
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,  # 預設 1 小時
        enable_stats: bool = True
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.enable_stats = enable_stats

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0
        }

    def _compute_cache_key(
        self,
        messages: list,
        system: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        **kwargs
    ) -> str:
        """
        計算快取鍵值

        將所有影響回應的參數序列化後計算 hash
        """
        key_data = {
            "messages": messages,
            "system": system,
            "model": model,
            "max_tokens": kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature", 1.0)
        }
        key_string = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """檢查條目是否過期"""
        return time.time() - entry.created_at > self.ttl_seconds

    def _evict_if_needed(self):
        """如果超過容量限制，淘汰最舊的條目"""
        while len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._stats["evictions"] += 1

    def get(self, cache_key: str) -> Optional[Any]:
        """取得快取的回應"""
        with self._lock:
            if cache_key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[cache_key]

            # 檢查是否過期
            if self._is_expired(entry):
                del self._cache[cache_key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # 更新 LRU 順序（移到最後）
            self._cache.move_to_end(cache_key)
            entry.hit_count += 1
            entry.last_accessed = time.time()

            self._stats["hits"] += 1
            return entry.response

    def set(self, cache_key: str, response: Any):
        """設定快取"""
        with self._lock:
            self._evict_if_needed()
            self._cache[cache_key] = CacheEntry(
                response=response,
                created_at=time.time()
            )

    def get_stats(self) -> dict:
        """取得快取統計"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total * 100 if total > 0 else 0

            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": f"{hit_rate:.1f}%"
            }

    def clear(self):
        """清空快取"""
        with self._lock:
            self._cache.clear()


class CachedClaudeClient:
    """
    帶應用層快取的 Claude Client

    結合 Claude API 的 Prompt Caching 和應用層回應快取
    """

    def __init__(
        self,
        response_cache: Optional[InMemoryResponseCache] = None,
        enable_api_cache: bool = True
    ):
        self.client = anthropic.Anthropic()
        self.response_cache = response_cache or InMemoryResponseCache()
        self.enable_api_cache = enable_api_cache

    def _build_system_with_cache(self, system: str) -> list:
        """構建帶 API 快取的 system content"""
        if self.enable_api_cache and len(system) > 1024:  # 快取需要 > 1024 tokens
            return [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"}
            }]
        return system

    def create_message(
        self,
        messages: list,
        system: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        use_response_cache: bool = True,
        **kwargs
    ) -> anthropic.types.Message:
        """
        建立訊息（帶雙層快取）

        Args:
            messages: 對話訊息
            system: System prompt
            model: 模型名稱
            use_response_cache: 是否使用應用層回應快取
            **kwargs: 其他 API 參數

        Returns:
            API 回應
        """
        # Layer 2：檢查應用層快取
        if use_response_cache:
            cache_key = self.response_cache._compute_cache_key(
                messages=messages,
                system=system,
                model=model,
                **kwargs
            )

            cached_response = self.response_cache.get(cache_key)
            if cached_response is not None:
                print("[Cache HIT] 返回快取的回應")
                return cached_response

        # Layer 1：使用 API 快取發送請求
        api_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": messages
        }

        if system:
            api_kwargs["system"] = self._build_system_with_cache(system)

        if "temperature" in kwargs:
            api_kwargs["temperature"] = kwargs["temperature"]

        response = self.client.messages.create(**api_kwargs)

        # 儲存到應用層快取
        if use_response_cache:
            self.response_cache.set(cache_key, response)
            print("[Cache MISS] 已儲存回應到快取")

        return response


# 使用範例
if __name__ == "__main__":
    # 建立帶快取的 client
    cached_client = CachedClaudeClient(
        response_cache=InMemoryResponseCache(
            max_size=500,
            ttl_seconds=1800  # 30 分鐘
        )
    )

    SYSTEM = "你是一個專業的程式助手，專長是 Python 開發。"

    # 第一次呼叫（快取未命中）
    response1 = cached_client.create_message(
        messages=[{"role": "user", "content": "什麼是 Python 的 GIL？"}],
        system=SYSTEM
    )
    print(f"回應 1：{response1.content[0].text[:100]}...")

    # 第二次相同呼叫（快取命中）
    response2 = cached_client.create_message(
        messages=[{"role": "user", "content": "什麼是 Python 的 GIL？"}],
        system=SYSTEM
    )
    print(f"回應 2：{response2.content[0].text[:100]}...")

    # 輸出統計
    print("\n快取統計：")
    print(cached_client.response_cache.get_stats())
```

### 快取策略考量

```
何時使用應用層快取：

✅ 適合快取的情況：
├── 相同問題的重複查詢（FAQ、常見問題）
├── 確定性輸出（temperature=0）
├── 資料查詢型任務（不需要創意性回應）
└── 高頻重複請求（例如 API 閘道）

❌ 不適合快取的情況：
├── 需要隨機性的創意任務（temperature > 0）
├── 時效性敏感的資訊（即時數據）
├── 個人化回應（每個使用者不同）
└── 需要最新知識的查詢
```

---

## Layer 3：RAG 系統快取整合

在 Retrieval-Augmented Generation (RAG) 系統中，快取策略可以應用在多個層面，顯著提升效能和降低成本。

### RAG 系統架構與快取點

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RAG 系統快取架構                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  使用者查詢                                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Query Embedding Cache                                        │   │
│  │ ├── 快取 Query → Embedding 的映射                            │   │
│  │ └── 避免重複的 Embedding API 呼叫                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Retrieval Result Cache                                       │   │
│  │ ├── 快取 Query → 檢索結果的映射                              │   │
│  │ └── 避免重複的向量搜尋                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Document Embedding Cache (持久化)                            │   │
│  │ ├── 文件 → Embedding 存入向量資料庫                          │   │
│  │ └── 只在文件變更時重新計算                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ LLM Response Cache                                           │   │
│  │ ├── 快取 (Query + Context) → Response                        │   │
│  │ └── 相同輸入直接返回                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 完整 RAG 快取系統實作

```python
import hashlib
import json
import numpy as np
from dataclasses import dataclass
from typing import Optional, Any
from abc import ABC, abstractmethod

# 向量資料庫抽象（可替換為 Pinecone、Weaviate、Qdrant 等）
class VectorStore(ABC):
    @abstractmethod
    def upsert(self, id: str, embedding: list[float], metadata: dict): pass

    @abstractmethod
    def query(self, embedding: list[float], top_k: int) -> list[dict]: pass


# 簡易記憶體向量資料庫（示範用）
class InMemoryVectorStore(VectorStore):
    def __init__(self):
        self.vectors: dict[str, dict] = {}

    def upsert(self, id: str, embedding: list[float], metadata: dict):
        self.vectors[id] = {
            "embedding": np.array(embedding),
            "metadata": metadata
        }

    def query(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        query_vec = np.array(embedding)
        scores = []

        for id, data in self.vectors.items():
            # 餘弦相似度
            similarity = np.dot(query_vec, data["embedding"]) / (
                np.linalg.norm(query_vec) * np.linalg.norm(data["embedding"])
            )
            scores.append({
                "id": id,
                "score": float(similarity),
                "metadata": data["metadata"]
            })

        # 排序並返回 top_k
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]


@dataclass
class RAGConfig:
    """RAG 系統配置"""
    embedding_model: str = "text-embedding-3-small"  # OpenAI embedding
    llm_model: str = "claude-sonnet-4-6"
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    cache_ttl: int = 3600


class CachedRAGSystem:
    """
    帶多層快取的 RAG 系統

    快取層：
    1. Query Embedding Cache：避免重複計算 query embedding
    2. Retrieval Cache：避免重複的向量搜尋
    3. Response Cache：避免重複的 LLM 呼叫
    4. Document Embedding：持久化在向量資料庫
    """

    def __init__(
        self,
        vector_store: VectorStore,
        config: Optional[RAGConfig] = None
    ):
        self.vector_store = vector_store
        self.config = config or RAGConfig()
        self.claude_client = anthropic.Anthropic()

        # 快取層
        self._embedding_cache: dict[str, list[float]] = {}  # query -> embedding
        self._retrieval_cache: dict[str, list[dict]] = {}   # query -> results
        self._response_cache: dict[str, str] = {}           # (query+context) -> response

        # 統計
        self._stats = {
            "embedding_cache_hits": 0,
            "embedding_cache_misses": 0,
            "retrieval_cache_hits": 0,
            "retrieval_cache_misses": 0,
            "response_cache_hits": 0,
            "response_cache_misses": 0
        }

    def _compute_embedding(self, text: str) -> list[float]:
        """
        計算文字的 embedding（帶快取）

        注意：這裡使用 OpenAI 的 embedding API
        實際使用時可替換為其他 embedding 服務
        """
        cache_key = hashlib.md5(text.encode()).hexdigest()

        if cache_key in self._embedding_cache:
            self._stats["embedding_cache_hits"] += 1
            return self._embedding_cache[cache_key]

        self._stats["embedding_cache_misses"] += 1

        # 呼叫 embedding API（這裡使用假資料示範）
        # 實際使用：response = openai.embeddings.create(input=text, model=self.config.embedding_model)
        # embedding = response.data[0].embedding

        # 示範用：生成隨機 embedding
        np.random.seed(hash(text) % (2**32))
        embedding = np.random.randn(1536).tolist()

        self._embedding_cache[cache_key] = embedding
        return embedding

    def _retrieve_context(self, query: str, top_k: Optional[int] = None) -> list[dict]:
        """
        檢索相關文件（帶快取）
        """
        cache_key = hashlib.md5(query.encode()).hexdigest()
        top_k = top_k or self.config.top_k

        if cache_key in self._retrieval_cache:
            self._stats["retrieval_cache_hits"] += 1
            return self._retrieval_cache[cache_key][:top_k]

        self._stats["retrieval_cache_misses"] += 1

        # 計算 query embedding
        query_embedding = self._compute_embedding(query)

        # 向量搜尋
        results = self.vector_store.query(query_embedding, top_k=top_k)

        self._retrieval_cache[cache_key] = results
        return results

    def _build_context_string(self, retrieved_docs: list[dict]) -> str:
        """將檢索結果格式化為 context 字串"""
        context_parts = []
        for i, doc in enumerate(retrieved_docs, 1):
            content = doc["metadata"].get("content", "")
            source = doc["metadata"].get("source", "unknown")
            context_parts.append(f"[文件 {i}] (來源: {source})\n{content}")
        return "\n\n---\n\n".join(context_parts)

    def _compute_response_cache_key(self, query: str, context: str) -> str:
        """計算回應快取鍵值"""
        combined = f"{query}|||{context}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def query(
        self,
        question: str,
        use_cache: bool = True,
        additional_context: Optional[str] = None
    ) -> dict:
        """
        執行 RAG 查詢

        Args:
            question: 使用者問題
            use_cache: 是否使用快取
            additional_context: 額外的 context（不經過檢索）

        Returns:
            包含回應和元資料的字典
        """
        # Step 1: 檢索相關文件
        retrieved_docs = self._retrieve_context(question)
        context = self._build_context_string(retrieved_docs)

        if additional_context:
            context = f"{additional_context}\n\n{context}"

        # Step 2: 檢查回應快取
        if use_cache:
            cache_key = self._compute_response_cache_key(question, context)
            if cache_key in self._response_cache:
                self._stats["response_cache_hits"] += 1
                return {
                    "answer": self._response_cache[cache_key],
                    "sources": retrieved_docs,
                    "cached": True
                }
            self._stats["response_cache_misses"] += 1

        # Step 3: 呼叫 LLM（使用 Prompt Caching）
        system_prompt = """你是一個專業的知識助手。根據提供的參考文件回答問題。

規則：
1. 只根據提供的文件內容回答
2. 如果文件中沒有相關資訊，明確說明
3. 引用資訊時標註來源文件編號
4. 保持回答簡潔準確"""

        user_message = f"""參考文件：
{context}

問題：{question}

請根據上述文件回答問題。"""

        response = self.claude_client.messages.create(
            model=self.config.llm_model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}  # API Prompt Caching
            }],
            messages=[{"role": "user", "content": user_message}]
        )

        answer = response.content[0].text

        # 儲存到回應快取
        if use_cache:
            self._response_cache[cache_key] = answer

        return {
            "answer": answer,
            "sources": retrieved_docs,
            "cached": False,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
                "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0)
            }
        }

    def add_documents(self, documents: list[dict]):
        """
        添加文件到向量資料庫

        Args:
            documents: 文件列表，每個文件包含 id, content, metadata
        """
        for doc in documents:
            embedding = self._compute_embedding(doc["content"])
            self.vector_store.upsert(
                id=doc["id"],
                embedding=embedding,
                metadata={
                    "content": doc["content"],
                    **doc.get("metadata", {})
                }
            )
        print(f"已添加 {len(documents)} 份文件")

    def get_stats(self) -> dict:
        """取得快取統計"""
        return {
            **self._stats,
            "embedding_cache_size": len(self._embedding_cache),
            "retrieval_cache_size": len(self._retrieval_cache),
            "response_cache_size": len(self._response_cache)
        }


# 使用範例
if __name__ == "__main__":
    # 建立向量資料庫和 RAG 系統
    vector_store = InMemoryVectorStore()
    rag = CachedRAGSystem(vector_store)

    # 添加示範文件
    documents = [
        {
            "id": "doc1",
            "content": "Python 的 GIL（Global Interpreter Lock）是一個互斥鎖，確保同一時間只有一個執行緒執行 Python bytecode。這是 CPython 實作的特性，用於簡化記憶體管理。",
            "metadata": {"source": "python-docs.md"}
        },
        {
            "id": "doc2",
            "content": "要繞過 GIL 的限制，可以使用 multiprocessing 模組進行多進程處理，或使用 C 擴展釋放 GIL。對於 I/O 密集型任務，asyncio 是更好的選擇。",
            "metadata": {"source": "python-best-practices.md"}
        },
        {
            "id": "doc3",
            "content": "FastAPI 是一個現代的 Python Web 框架，基於 Starlette 和 Pydantic 構建。它支援異步處理，效能接近 NodeJS 和 Go。",
            "metadata": {"source": "fastapi-intro.md"}
        }
    ]

    rag.add_documents(documents)

    # 查詢測試
    print("\n" + "="*50)
    print("第一次查詢（快取未命中）")
    print("="*50)
    result1 = rag.query("什麼是 Python 的 GIL？")
    print(f"回答：{result1['answer'][:200]}...")
    print(f"快取：{result1['cached']}")

    print("\n" + "="*50)
    print("第二次相同查詢（快取命中）")
    print("="*50)
    result2 = rag.query("什麼是 Python 的 GIL？")
    print(f"回答：{result2['answer'][:200]}...")
    print(f"快取：{result2['cached']}")

    print("\n" + "="*50)
    print("快取統計")
    print("="*50)
    stats = rag.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
```

---

## Layer 4：分散式快取整合

對於生產環境的多實例部署，需要使用分散式快取（如 Redis）來共享快取資料。

### Redis 快取整合

```python
import redis
import json
import hashlib
from typing import Optional, Any
from dataclasses import dataclass
import pickle

@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    default_ttl: int = 3600  # 1 小時


class DistributedResponseCache:
    """
    基於 Redis 的分散式回應快取

    特點：
    - 跨實例共享快取
    - 支援 TTL 自動過期
    - 支援快取標籤（用於批次失效）
    """

    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig()
        self.redis = redis.Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            decode_responses=False  # 支援 binary 資料
        )
        self._prefix = "llm_cache:"

    def _make_key(self, cache_key: str) -> str:
        return f"{self._prefix}{cache_key}"

    def _compute_cache_key(
        self,
        messages: list,
        system: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        **kwargs
    ) -> str:
        key_data = {
            "messages": messages,
            "system": system,
            "model": model,
            "temperature": kwargs.get("temperature", 1.0)
        }
        key_string = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(self, cache_key: str) -> Optional[Any]:
        """取得快取"""
        try:
            data = self.redis.get(self._make_key(cache_key))
            if data:
                return pickle.loads(data)
            return None
        except Exception as e:
            print(f"Redis get error: {e}")
            return None

    def set(
        self,
        cache_key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[list[str]] = None
    ):
        """
        設定快取

        Args:
            cache_key: 快取鍵
            value: 快取值
            ttl: 存活時間（秒）
            tags: 快取標籤（用於批次失效）
        """
        try:
            key = self._make_key(cache_key)
            ttl = ttl or self.config.default_ttl

            # 存入資料
            self.redis.setex(key, ttl, pickle.dumps(value))

            # 如果有標籤，添加到標籤集合
            if tags:
                for tag in tags:
                    self.redis.sadd(f"{self._prefix}tag:{tag}", cache_key)
                    self.redis.expire(f"{self._prefix}tag:{tag}", ttl)

        except Exception as e:
            print(f"Redis set error: {e}")

    def invalidate_by_tag(self, tag: str):
        """根據標籤批次失效快取"""
        try:
            tag_key = f"{self._prefix}tag:{tag}"
            cache_keys = self.redis.smembers(tag_key)

            if cache_keys:
                # 刪除所有相關快取
                keys_to_delete = [self._make_key(k.decode()) for k in cache_keys]
                self.redis.delete(*keys_to_delete)
                self.redis.delete(tag_key)

                print(f"已失效 {len(cache_keys)} 個快取（標籤：{tag}）")
        except Exception as e:
            print(f"Redis invalidate error: {e}")

    def get_stats(self) -> dict:
        """取得 Redis 快取統計"""
        try:
            info = self.redis.info("stats")
            keys_count = self.redis.dbsize()
            return {
                "total_keys": keys_count,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": f"{info.get('keyspace_hits', 0) / max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1) * 100:.1f}%"
            }
        except Exception as e:
            return {"error": str(e)}


class ProductionCachedClient:
    """
    生產級帶快取的 Claude Client

    整合：
    - Claude API Prompt Caching
    - 本地 LRU 快取（L1）
    - Redis 分散式快取（L2）
    """

    def __init__(
        self,
        redis_config: Optional[RedisConfig] = None,
        local_cache_size: int = 100
    ):
        self.client = anthropic.Anthropic()
        self.local_cache = InMemoryResponseCache(max_size=local_cache_size)
        self.redis_cache = DistributedResponseCache(redis_config)

    def create_message(
        self,
        messages: list,
        system: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        cache_tags: Optional[list[str]] = None,
        **kwargs
    ):
        """
        建立訊息（三層快取）

        快取檢查順序：
        1. 本地 LRU 快取（最快）
        2. Redis 分散式快取
        3. Claude API（帶 Prompt Caching）
        """
        cache_key = self.redis_cache._compute_cache_key(
            messages=messages, system=system, model=model, **kwargs
        )

        # L1: 本地快取
        local_result = self.local_cache.get(cache_key)
        if local_result:
            print("[L1 HIT] 本地快取命中")
            return local_result

        # L2: Redis 快取
        redis_result = self.redis_cache.get(cache_key)
        if redis_result:
            print("[L2 HIT] Redis 快取命中")
            # 回填本地快取
            self.local_cache.set(cache_key, redis_result)
            return redis_result

        # L3: API 呼叫（帶 Prompt Caching）
        print("[MISS] 呼叫 API")

        api_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": messages
        }

        if system:
            # 使用 Prompt Caching
            if len(system) > 500:
                api_kwargs["system"] = [{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"}
                }]
            else:
                api_kwargs["system"] = system

        response = self.client.messages.create(**api_kwargs)

        # 回填快取
        self.local_cache.set(cache_key, response)
        self.redis_cache.set(cache_key, response, tags=cache_tags)

        return response
```

---

## 實戰案例：智能客服系統

整合所有快取策略的完整智能客服系統實作：

```python
"""
智能客服系統 - 整合多層快取的完整實作

架構：
- FAQ 快取：常見問題直接返回預設答案
- RAG 快取：知識庫檢索結果快取
- 回應快取：LLM 回應快取
- Prompt Caching：System Prompt 快取
"""

import anthropic
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import hashlib
import json

client = anthropic.Anthropic()


class QueryType(Enum):
    FAQ = "faq"           # 常見問題
    KNOWLEDGE = "knowledge"  # 知識庫查詢
    GENERAL = "general"     # 一般對話


@dataclass
class CustomerServiceConfig:
    company_name: str = "TechCorp"
    support_email: str = "support@techcorp.com"
    business_hours: str = "週一至週五 09:00-18:00"


class SmartCustomerService:
    """
    智能客服系統

    快取策略：
    1. FAQ 完全匹配：直接返回預設答案（零 API 呼叫）
    2. FAQ 模糊匹配：使用快取的分類結果
    3. 知識庫查詢：RAG + 回應快取
    4. 一般對話：Prompt Caching
    """

    def __init__(self, config: Optional[CustomerServiceConfig] = None):
        self.config = config or CustomerServiceConfig()

        # FAQ 資料庫（完全匹配，零 API 成本）
        self.faq_exact_match: dict[str, str] = {
            "營業時間": f"我們的營業時間是{self.config.business_hours}。",
            "客服電話": f"請聯繫 {self.config.support_email} 或致電客服專線。",
            "退貨政策": "商品可在購買後 7 天內申請退貨，請保持商品完整。",
        }

        # FAQ 模糊匹配關鍵字
        self.faq_keywords: dict[str, str] = {
            "退貨|退款|換貨": "退貨政策",
            "營業|開門|上班": "營業時間",
            "電話|聯繫|客服": "客服電話",
        }

        # 知識庫（實際使用時接入向量資料庫）
        self.knowledge_base: list[dict] = [
            {
                "id": "kb1",
                "content": "我們的旗艦產品 ProductX 支援 iOS 和 Android 平台...",
                "category": "product"
            },
            # ... 更多知識條目
        ]

        # 回應快取
        self._response_cache: dict[str, str] = {}

        # System Prompt（將被快取）
        self._system_prompt = f"""你是 {self.config.company_name} 的智能客服助手。

## 你的職責
- 專業且友善地回答客戶問題
- 提供準確的產品和服務資訊
- 無法回答時，引導客戶聯繫人工客服

## 公司資訊
- 公司名稱：{self.config.company_name}
- 客服郵箱：{self.config.support_email}
- 營業時間：{self.config.business_hours}

## 回應原則
1. 保持簡潔，直接回答問題
2. 使用繁體中文
3. 語氣專業但親切
4. 不確定的資訊要明確說明"""

        # 統計
        self._stats = {
            "faq_exact_hits": 0,
            "faq_keyword_hits": 0,
            "cache_hits": 0,
            "api_calls": 0
        }

    def _classify_query(self, query: str) -> QueryType:
        """分類查詢類型"""
        import re

        # 檢查 FAQ 完全匹配
        if query in self.faq_exact_match:
            return QueryType.FAQ

        # 檢查 FAQ 關鍵字匹配
        for pattern in self.faq_keywords:
            if re.search(pattern, query):
                return QueryType.FAQ

        # 檢查是否需要知識庫
        knowledge_keywords = ["產品", "功能", "如何使用", "規格", "價格"]
        if any(kw in query for kw in knowledge_keywords):
            return QueryType.KNOWLEDGE

        return QueryType.GENERAL

    def _get_faq_answer(self, query: str) -> Optional[str]:
        """取得 FAQ 答案"""
        import re

        # 完全匹配
        if query in self.faq_exact_match:
            self._stats["faq_exact_hits"] += 1
            return self.faq_exact_match[query]

        # 關鍵字匹配
        for pattern, faq_key in self.faq_keywords.items():
            if re.search(pattern, query):
                self._stats["faq_keyword_hits"] += 1
                return self.faq_exact_match.get(faq_key)

        return None

    def _compute_cache_key(self, query: str, context: str = "") -> str:
        combined = f"{query}|{context}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _call_llm(self, query: str, context: str = "") -> str:
        """呼叫 LLM（帶 Prompt Caching）"""
        user_content = query
        if context:
            user_content = f"參考資訊：\n{context}\n\n客戶問題：{query}"

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral"}  # Prompt Caching
            }],
            messages=[{"role": "user", "content": user_content}]
        )

        self._stats["api_calls"] += 1
        return response.content[0].text

    def respond(self, query: str) -> dict:
        """
        處理客戶查詢

        Returns:
            包含回應和元資料的字典
        """
        query_type = self._classify_query(query)

        # 路徑 1：FAQ 直接返回
        if query_type == QueryType.FAQ:
            answer = self._get_faq_answer(query)
            if answer:
                return {
                    "answer": answer,
                    "source": "faq",
                    "cached": True,
                    "api_called": False
                }

        # 路徑 2：檢查回應快取
        cache_key = self._compute_cache_key(query)
        if cache_key in self._response_cache:
            self._stats["cache_hits"] += 1
            return {
                "answer": self._response_cache[cache_key],
                "source": "cache",
                "cached": True,
                "api_called": False
            }

        # 路徑 3：知識庫查詢 + LLM
        context = ""
        if query_type == QueryType.KNOWLEDGE:
            # 這裡簡化處理，實際應使用向量搜尋
            context = self.knowledge_base[0]["content"] if self.knowledge_base else ""

        # 路徑 4：呼叫 LLM
        answer = self._call_llm(query, context)

        # 儲存到快取
        self._response_cache[cache_key] = answer

        return {
            "answer": answer,
            "source": "llm" if query_type == QueryType.GENERAL else "rag",
            "cached": False,
            "api_called": True
        }

    def get_stats(self) -> dict:
        """取得系統統計"""
        total_requests = (
            self._stats["faq_exact_hits"] +
            self._stats["faq_keyword_hits"] +
            self._stats["cache_hits"] +
            self._stats["api_calls"]
        )

        return {
            **self._stats,
            "total_requests": total_requests,
            "cache_hit_rate": f"{(self._stats['faq_exact_hits'] + self._stats['faq_keyword_hits'] + self._stats['cache_hits']) / max(total_requests, 1) * 100:.1f}%",
            "response_cache_size": len(self._response_cache)
        }


# 使用範例
if __name__ == "__main__":
    service = SmartCustomerService()

    queries = [
        "營業時間",              # FAQ 完全匹配
        "請問你們幾點開門？",     # FAQ 關鍵字匹配
        "退貨政策",              # FAQ 完全匹配
        "我想了解你們的產品功能",  # 知識庫查詢
        "今天天氣如何？",         # 一般對話
        "今天天氣如何？",         # 快取命中
    ]

    print("="*60)
    print("智能客服系統測試")
    print("="*60)

    for query in queries:
        result = service.respond(query)
        print(f"\n問：{query}")
        print(f"答：{result['answer'][:100]}...")
        print(f"來源：{result['source']}，快取：{result['cached']}，API：{result['api_called']}")

    print("\n" + "="*60)
    print("系統統計")
    print("="*60)
    stats = service.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
```

---

## 快取效益總覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                    快取策略效益比較                                  │
├──────────────────────┬──────────┬──────────┬──────────┬────────────┤
│ 快取層               │ 成本節省 │ 延遲降低 │ 實作複雜度│ 適用場景   │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┤
│ Claude Prompt Cache  │ 90%      │ 顯著     │ 極低     │ 固定前綴   │
│ 應用層 LRU 快取      │ 100%     │ 極大     │ 低       │ 重複查詢   │
│ RAG Embedding 快取   │ 50-80%   │ 中等     │ 中       │ 文件檢索   │
│ Redis 分散式快取     │ 100%     │ 極大     │ 中       │ 多實例     │
└──────────────────────┴──────────┴──────────┴──────────┴────────────┘

建議實施順序：
1. Claude Prompt Caching（最簡單，立即見效）
2. 應用層 LRU 快取（重複查詢場景）
3. RAG 快取整合（知識庫應用）
4. Redis 分散式快取（生產環境擴展）
```

---

## 最佳實踐清單

```
快取實作 Checklist：

基礎設定
□ System Prompt 是否超過 1,024 tokens？若是，啟用 Prompt Caching
□ 是否定義了明確的快取鍵計算邏輯？
□ 是否設定了合適的 TTL（存活時間）？

快取設計
□ 是否識別出高頻重複查詢並優先快取？
□ 是否區分可快取和不可快取的請求？
□ 是否設計了快取失效策略（基於時間/事件）？

RAG 整合
□ 是否快取 Embedding 計算結果？
□ 是否快取向量搜尋結果？
□ 是否在文件更新時正確失效相關快取？

監控
□ 是否追蹤快取命中率？
□ 是否監控快取大小和記憶體使用？
□ 是否設定了快取效能警報？
```

---

## 總結

Prompt Caching 和應用層快取是優化 AI 應用成本和效能的關鍵技術。本文介紹的多層快取架構可以根據實際需求靈活組合：

| 場景 | 推薦快取策略 |
|------|-------------|
| 單實例簡單應用 | Claude Prompt Cache + LRU |
| 高頻重複查詢 | Claude Prompt Cache + LRU + FAQ |
| 知識庫問答 | Claude Prompt Cache + RAG 全層快取 |
| 多實例生產環境 | 全部層級 + Redis |

快取不是一勞永逸的解決方案，需要根據實際使用模式持續調整。建立完善的監控和分析機制，讓數據驅動快取策略的優化，才能持續提升系統效能並控制成本。
