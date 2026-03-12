---
title: "多 Agent Token 優化系列 pt.3：Context 壓縮與摘要 — 打造可無限對話的 AI 系統"
date: 2026-03-12T16:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "context-compression", "summarization", "token-optimization", "long-conversation", "memory-management"]
summary: "多 Agent Token 優化系列 pt.3：深入探索 Context 壓縮與摘要技術，從滑動視窗、階層式摘要到語意壓縮，提供完整實作範例，幫助你打造可無限對話且成本可控的 AI 應用。"
readTime: "35 min"
---

在前一篇文章《多 Agent 系統的 Token 用量調優指南》中，我們介紹了 **Context 壓縮與摘要**作為長期對話穩定性的關鍵策略。本文將深入實作層面，探討如何在真實系統中建構完整的 Context 管理機制，從基礎的滑動視窗到進階的語意壓縮，打造可以「無限對話」的 AI 系統。

---

## Context 累積的問題

### 為什麼 Context 會爆炸？

在長對話或多輪互動的 AI 應用中，Context（上下文）會隨著對話進行而不斷累積：

```
Context 累積的指數成長模型：

單輪對話的 Token 消耗：
┌─────────────────────────────────────────────────────────────┐
│  輸入 = System Prompt + 歷史對話 + 當前輸入                  │
│  輸出 = 模型回應                                            │
│                                                             │
│  第 N 輪的輸入 tokens ≈ System + Σ(前 N-1 輪對話) + 當前    │
└─────────────────────────────────────────────────────────────┘

實際數據模擬（假設每輪平均 500 tokens）：

輪次    累積 tokens    API 成本（以 Sonnet $3/1M 計）
─────────────────────────────────────────────────────
1       500           $0.0015
5       2,500         $0.0075
10      5,000         $0.015
20      10,000        $0.03
50      25,000        $0.075
100     50,000        $0.15      ← 單次呼叫！
200     100,000       $0.30      ← 接近 Context 上限

問題：
1. 成本線性增長（每輪都重複發送歷史）
2. 延遲增加（處理更多 tokens 需要更多時間）
3. Context Window 耗盡（Claude: 200K tokens 上限）
4. 資訊稀釋（太多歷史可能干擾當前任務）
```

### Context 管理的目標

```
理想的 Context 管理系統：

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ 完整對話歷史 │ →  │ 智能壓縮引擎 │ →  │ 精簡 Context │  │
│  │ 50,000 tokens│    │              │    │ 5,000 tokens │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
│  目標：                                                     │
│  ✓ 保留關鍵資訊（決策、結論、重要數據）                    │
│  ✓ 移除冗餘內容（重複、過渡性對話、已解決問題）            │
│  ✓ 維持連貫性（確保模型理解對話脈絡）                      │
│  ✓ 成本可控（壓縮後 tokens 維持在固定範圍）                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 策略一：滑動視窗（Sliding Window）

最簡單直接的 Context 管理方式：只保留最近 N 輪對話。

### 基礎實作

```python
import anthropic
from dataclasses import dataclass, field
from typing import Optional

client = anthropic.Anthropic()

@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

@dataclass
class SlidingWindowConfig:
    """滑動視窗配置"""
    max_turns: int = 10          # 最多保留幾輪對話
    max_tokens: int = 8000       # 最大 tokens 數（估算）
    tokens_per_char: float = 0.4 # 中文約 0.5，英文約 0.25


class SlidingWindowManager:
    """
    滑動視窗 Context 管理器

    策略：只保留最近 N 輪對話，超過則丟棄最舊的

    優點：實作簡單，延遲可預測
    缺點：完全丟失早期對話資訊
    """

    def __init__(self, config: Optional[SlidingWindowConfig] = None):
        self.config = config or SlidingWindowConfig()
        self.messages: list[Message] = []
        self._stats = {
            "total_messages": 0,
            "dropped_messages": 0
        }

    def _estimate_tokens(self, text: str) -> int:
        """估算文字的 token 數量"""
        return int(len(text) * self.config.tokens_per_char)

    def _get_total_tokens(self) -> int:
        """計算當前所有訊息的 tokens"""
        return sum(self._estimate_tokens(m.content) for m in self.messages)

    def add_message(self, role: str, content: str):
        """添加新訊息"""
        self.messages.append(Message(role=role, content=content))
        self._stats["total_messages"] += 1
        self._trim_if_needed()

    def _trim_if_needed(self):
        """如果超過限制，移除最舊的訊息"""
        # 按輪數限制（一輪 = user + assistant）
        while len(self.messages) > self.config.max_turns * 2:
            self.messages.pop(0)
            self._stats["dropped_messages"] += 1

        # 按 token 數限制
        while self._get_total_tokens() > self.config.max_tokens and len(self.messages) > 2:
            self.messages.pop(0)
            self._stats["dropped_messages"] += 1

    def get_messages(self) -> list[dict]:
        """取得格式化的訊息列表"""
        return [m.to_dict() for m in self.messages]

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "current_messages": len(self.messages),
            "current_tokens": self._get_total_tokens()
        }


class SlidingWindowChatbot:
    """使用滑動視窗的聊天機器人"""

    def __init__(
        self,
        system_prompt: str,
        window_config: Optional[SlidingWindowConfig] = None
    ):
        self.system_prompt = system_prompt
        self.window = SlidingWindowManager(window_config)

    def chat(self, user_input: str) -> str:
        # 添加使用者訊息
        self.window.add_message("user", user_input)

        # 呼叫 API
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=self.window.get_messages()
        )

        assistant_response = response.content[0].text

        # 添加助手回應
        self.window.add_message("assistant", assistant_response)

        return assistant_response


# 使用範例
if __name__ == "__main__":
    bot = SlidingWindowChatbot(
        system_prompt="你是一個友善的助手。",
        window_config=SlidingWindowConfig(max_turns=5, max_tokens=4000)
    )

    # 模擬多輪對話
    conversations = [
        "你好，我叫小明",
        "我喜歡程式設計",
        "特別是 Python",
        "我正在學習機器學習",
        "你能推薦一些資源嗎？",
        "謝謝你的建議",
        "對了，你還記得我叫什麼名字嗎？"  # 測試是否記得早期資訊
    ]

    for user_msg in conversations:
        print(f"\n👤 User: {user_msg}")
        response = bot.chat(user_msg)
        print(f"🤖 Bot: {response[:200]}...")
        print(f"   [視窗狀態: {bot.window.get_stats()}]")
```

### 滑動視窗的限制

```
滑動視窗的問題：

對話歷史：
Turn 1: "我叫小明，是軟體工程師"     ← 被丟棄
Turn 2: "我在開發一個電商系統"        ← 被丟棄
Turn 3: "使用 Python 和 FastAPI"     ← 被丟棄
Turn 4: "資料庫選擇了 PostgreSQL"    ← 被丟棄
Turn 5: "現在遇到效能問題"            ← 被丟棄
─────────────────────────────────────
Turn 6: "查詢很慢"                    ← 保留（視窗內）
Turn 7: "大概 5 秒才有結果"           ← 保留
Turn 8: "該怎麼優化？"                ← 保留
Turn 9: "索引已經加了"                ← 保留
Turn 10: "還有什麼方法？"             ← 保留（當前）

問題：模型不知道：
- 使用者是誰（小明，軟體工程師）
- 專案背景（電商系統）
- 技術棧（Python, FastAPI, PostgreSQL）

這些關鍵資訊在視窗滑動時被丟棄了！
```

---

## 策略二：漸進式摘要（Progressive Summarization）

將超出視窗的歷史對話壓縮為摘要，保留關鍵資訊。

### 核心概念

```
漸進式摘要架構：

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌────────────────────────────────────────────────────────┐│
│  │                    完整歷史摘要                         ││
│  │  "使用者小明是軟體工程師，正在開發電商系統，            ││
│  │   使用 Python/FastAPI/PostgreSQL，                     ││
│  │   目前遇到查詢效能問題，已嘗試添加索引..."              ││
│  │                                 [~500 tokens]          ││
│  └────────────────────────────────────────────────────────┘│
│                           +                                 │
│  ┌────────────────────────────────────────────────────────┐│
│  │                  最近完整對話（5輪）                     ││
│  │  Turn 6-10 的完整內容                                   ││
│  │                                 [~2000 tokens]         ││
│  └────────────────────────────────────────────────────────┘│
│                           =                                 │
│           有效 Context：~2500 tokens（而非 5000+）          │
│           保留了所有關鍵資訊！                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

client = anthropic.Anthropic()


class SummarizationModel(Enum):
    """摘要使用的模型"""
    HAIKU = "claude-haiku-4-5-20251001"    # 便宜快速
    SONNET = "claude-sonnet-4-6"           # 平衡


@dataclass
class ProgressiveSummaryConfig:
    """漸進式摘要配置"""
    # 視窗設定
    recent_turns_to_keep: int = 5       # 保留最近幾輪完整對話

    # 摘要觸發條件
    summarize_threshold: int = 10        # 超過幾輪時觸發摘要

    # 摘要設定
    summary_model: SummarizationModel = SummarizationModel.HAIKU
    max_summary_tokens: int = 1000       # 摘要最大長度

    # 摘要內容指引
    summary_focus: list[str] = field(default_factory=lambda: [
        "使用者身份和背景",
        "主要任務或目標",
        "關鍵決策和結論",
        "重要的技術細節",
        "待解決的問題",
        "使用者偏好"
    ])


@dataclass
class ConversationState:
    """對話狀態"""
    summary: Optional[str] = None           # 歷史摘要
    recent_messages: list[dict] = field(default_factory=list)  # 最近的完整訊息
    total_turns: int = 0                    # 總對話輪數
    last_summary_turn: int = 0              # 上次摘要的輪數


class ProgressiveSummarizer:
    """
    漸進式摘要管理器

    核心邏輯：
    1. 保留最近 N 輪的完整對話
    2. 超過閾值時，將舊對話壓縮為摘要
    3. 摘要會隨著對話推進而更新（包含新資訊）
    """

    def __init__(self, config: Optional[ProgressiveSummaryConfig] = None):
        self.config = config or ProgressiveSummaryConfig()
        self.state = ConversationState()
        self._stats = {
            "summarization_count": 0,
            "tokens_before_summary": 0,
            "tokens_after_summary": 0
        }

    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """將訊息格式化為摘要輸入"""
        formatted = []
        for i, msg in enumerate(messages):
            role = "使用者" if msg["role"] == "user" else "助手"
            formatted.append(f"[{role}]: {msg['content']}")
        return "\n\n".join(formatted)

    def _create_summary_prompt(self, messages_text: str, existing_summary: Optional[str]) -> str:
        """建立摘要提示"""
        focus_points = "\n".join(f"- {f}" for f in self.config.summary_focus)

        if existing_summary:
            return f"""請更新以下對話摘要，整合新的對話內容。

現有摘要：
{existing_summary}

新增對話：
{messages_text}

請產生更新後的摘要，重點保留：
{focus_points}

要求：
1. 保持簡潔，控制在 {self.config.max_summary_tokens} tokens 以內
2. 使用條列式整理關鍵資訊
3. 標註重要的變化或新發現
4. 移除已解決或不再相關的資訊

更新後的摘要："""
        else:
            return f"""請為以下對話產生摘要。

對話內容：
{messages_text}

請產生摘要，重點保留：
{focus_points}

要求：
1. 保持簡潔，控制在 {self.config.max_summary_tokens} tokens 以內
2. 使用條列式整理關鍵資訊
3. 突出關鍵決策和結論

摘要："""

    def _generate_summary(self, messages: list[dict]) -> str:
        """使用 LLM 生成摘要"""
        messages_text = self._format_messages_for_summary(messages)
        prompt = self._create_summary_prompt(messages_text, self.state.summary)

        response = client.messages.create(
            model=self.config.summary_model.value,
            max_tokens=self.config.max_summary_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        self._stats["summarization_count"] += 1
        return response.content[0].text

    def add_turn(self, user_message: str, assistant_message: str):
        """添加一輪對話"""
        self.state.recent_messages.append({"role": "user", "content": user_message})
        self.state.recent_messages.append({"role": "assistant", "content": assistant_message})
        self.state.total_turns += 1

        # 檢查是否需要摘要
        self._check_and_summarize()

    def _check_and_summarize(self):
        """檢查並執行摘要（如果需要）"""
        turns_since_summary = self.state.total_turns - self.state.last_summary_turn

        if turns_since_summary >= self.config.summarize_threshold:
            self._perform_summarization()

    def _perform_summarization(self):
        """執行摘要"""
        # 計算要摘要的訊息數量
        messages_to_summarize_count = len(self.state.recent_messages) - (self.config.recent_turns_to_keep * 2)

        if messages_to_summarize_count <= 0:
            return

        # 分離要摘要的訊息和要保留的訊息
        messages_to_summarize = self.state.recent_messages[:messages_to_summarize_count]
        messages_to_keep = self.state.recent_messages[messages_to_summarize_count:]

        # 記錄壓縮前的 tokens
        before_tokens = sum(len(m["content"]) for m in self.state.recent_messages) * 0.4
        self._stats["tokens_before_summary"] += before_tokens

        # 生成摘要
        print(f"📝 正在壓縮 {len(messages_to_summarize)} 條訊息...")
        self.state.summary = self._generate_summary(messages_to_summarize)

        # 更新狀態
        self.state.recent_messages = messages_to_keep
        self.state.last_summary_turn = self.state.total_turns

        # 記錄壓縮後的 tokens
        after_tokens = (len(self.state.summary) + sum(len(m["content"]) for m in messages_to_keep)) * 0.4
        self._stats["tokens_after_summary"] += after_tokens

        print(f"✅ 壓縮完成：{int(before_tokens)} → {int(after_tokens)} tokens")

    def get_context_messages(self) -> list[dict]:
        """取得要發送給 API 的訊息"""
        messages = []

        # 如果有摘要，作為第一條訊息注入
        if self.state.summary:
            messages.append({
                "role": "user",
                "content": f"[對話歷史摘要]\n{self.state.summary}\n\n請基於以上背景繼續對話。"
            })
            messages.append({
                "role": "assistant",
                "content": "我已了解之前的對話背景，請繼續。"
            })

        # 加入最近的完整訊息
        messages.extend(self.state.recent_messages)

        return messages

    def get_stats(self) -> dict:
        """取得統計資訊"""
        compression_ratio = 0
        if self._stats["tokens_before_summary"] > 0:
            compression_ratio = (
                1 - self._stats["tokens_after_summary"] / self._stats["tokens_before_summary"]
            ) * 100

        return {
            **self._stats,
            "total_turns": self.state.total_turns,
            "has_summary": self.state.summary is not None,
            "recent_messages_count": len(self.state.recent_messages),
            "compression_ratio": f"{compression_ratio:.1f}%"
        }


class ProgressiveSummaryChatbot:
    """使用漸進式摘要的聊天機器人"""

    def __init__(
        self,
        system_prompt: str,
        summary_config: Optional[ProgressiveSummaryConfig] = None
    ):
        self.system_prompt = system_prompt
        self.summarizer = ProgressiveSummarizer(summary_config)

    def chat(self, user_input: str) -> str:
        # 取得當前 context
        messages = self.summarizer.get_context_messages()
        messages.append({"role": "user", "content": user_input})

        # 呼叫 API
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages
        )

        assistant_response = response.content[0].text

        # 更新摘要器
        self.summarizer.add_turn(user_input, assistant_response)

        return assistant_response

    def get_current_summary(self) -> Optional[str]:
        """取得當前摘要"""
        return self.summarizer.state.summary


# 使用範例
if __name__ == "__main__":
    config = ProgressiveSummaryConfig(
        recent_turns_to_keep=3,
        summarize_threshold=5,
        summary_focus=[
            "使用者的身份和角色",
            "討論的主題和目標",
            "已做出的決定",
            "關鍵的技術細節"
        ]
    )

    bot = ProgressiveSummaryChatbot(
        system_prompt="你是一個專業的技術顧問，幫助使用者解決程式問題。",
        summary_config=config
    )

    # 模擬長對話
    conversations = [
        "你好，我是小明，是一個後端工程師",
        "我在開發一個電商平台",
        "使用 Python 和 FastAPI 框架",
        "資料庫是 PostgreSQL",
        "現在遇到一個效能問題",
        "商品列表的查詢很慢",
        "大概要 5 秒才能返回",
        "我已經加了索引",
        "但還是很慢",
        "你覺得還有什麼優化方向？",
        "對了，你還記得我用的是什麼框架嗎？"  # 測試摘要是否保留資訊
    ]

    for i, user_msg in enumerate(conversations, 1):
        print(f"\n{'='*50}")
        print(f"Turn {i}")
        print(f"👤 User: {user_msg}")
        response = bot.chat(user_msg)
        print(f"🤖 Bot: {response[:300]}...")

        stats = bot.summarizer.get_stats()
        print(f"\n📊 Stats: {stats}")

        if bot.get_current_summary():
            print(f"\n📋 Current Summary:\n{bot.get_current_summary()[:500]}...")
```

---

## 策略三：階層式摘要（Hierarchical Summarization）

對於超長對話或多 Session 的場景，使用多層摘要結構。

### 架構設計

```
階層式摘要架構：

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Level 3: 長期記憶（跨 Session）                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "使用者小明，軟體工程師，偏好 Python，              │   │
│  │  主要專案是電商平台，長期目標是優化系統效能"        │   │
│  │                                    [~200 tokens]    │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│  Level 2: 中期摘要（當前 Session 早期）                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "本次討論主題：PostgreSQL 查詢優化                  │   │
│  │  已嘗試：添加索引、調整查詢語句                     │   │
│  │  待解決：N+1 問題、連線池配置"                      │   │
│  │                                    [~500 tokens]    │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│  Level 1: 最近完整對話                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Turn N-4 到 Turn N 的完整內容                       │   │
│  │                                    [~2000 tokens]   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  總 Context: ~2700 tokens（即使對話已超過 100 輪）         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from pathlib import Path

client = anthropic.Anthropic()


@dataclass
class HierarchicalSummaryConfig:
    """階層式摘要配置"""
    # Level 1: 最近完整對話
    recent_turns: int = 5

    # Level 2: Session 摘要
    session_summary_threshold: int = 10  # 幾輪觸發 Session 摘要更新
    session_summary_max_tokens: int = 800

    # Level 3: 長期記憶
    long_term_memory_file: Optional[str] = None  # 持久化檔案路徑
    long_term_summary_max_tokens: int = 300

    # 摘要模型
    summary_model: str = "claude-haiku-4-5-20251001"


@dataclass
class UserProfile:
    """使用者輪廓（長期記憶）"""
    name: Optional[str] = None
    role: Optional[str] = None
    preferences: list[str] = field(default_factory=list)
    expertise: list[str] = field(default_factory=list)
    ongoing_projects: list[str] = field(default_factory=list)
    interaction_style: Optional[str] = None
    last_updated: Optional[str] = None

    def to_summary(self) -> str:
        """轉換為摘要文字"""
        parts = []
        if self.name:
            parts.append(f"使用者：{self.name}")
        if self.role:
            parts.append(f"角色：{self.role}")
        if self.preferences:
            parts.append(f"偏好：{', '.join(self.preferences)}")
        if self.expertise:
            parts.append(f"專長：{', '.join(self.expertise)}")
        if self.ongoing_projects:
            parts.append(f"進行中專案：{', '.join(self.ongoing_projects)}")
        if self.interaction_style:
            parts.append(f"互動風格：{self.interaction_style}")
        return "\n".join(parts) if parts else "（尚無使用者資料）"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "preferences": self.preferences,
            "expertise": self.expertise,
            "ongoing_projects": self.ongoing_projects,
            "interaction_style": self.interaction_style,
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        return cls(**data)


@dataclass
class SessionState:
    """Session 狀態"""
    session_id: str
    started_at: str
    topic: Optional[str] = None
    summary: Optional[str] = None
    key_decisions: list[str] = field(default_factory=list)
    pending_issues: list[str] = field(default_factory=list)
    recent_messages: list[dict] = field(default_factory=list)
    turn_count: int = 0


class HierarchicalMemoryManager:
    """
    階層式記憶管理器

    三層結構：
    - Level 3 (Long-term): 使用者輪廓，跨 Session 持久化
    - Level 2 (Session): 當前 Session 的摘要
    - Level 1 (Recent): 最近幾輪的完整對話
    """

    def __init__(self, config: Optional[HierarchicalSummaryConfig] = None):
        self.config = config or HierarchicalSummaryConfig()

        # Level 3: 長期記憶
        self.user_profile = self._load_user_profile()

        # Level 2: Session 狀態
        self.session = SessionState(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat()
        )

        self._stats = {
            "session_summaries": 0,
            "profile_updates": 0
        }

    def _load_user_profile(self) -> UserProfile:
        """載入持久化的使用者輪廓"""
        if self.config.long_term_memory_file:
            path = Path(self.config.long_term_memory_file)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return UserProfile.from_dict(data)
        return UserProfile()

    def _save_user_profile(self):
        """儲存使用者輪廓"""
        if self.config.long_term_memory_file:
            path = Path(self.config.long_term_memory_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.user_profile.to_dict(), f, ensure_ascii=False, indent=2)

    def _update_user_profile(self, messages: list[dict]):
        """從對話中更新使用者輪廓"""
        if not messages:
            return

        messages_text = "\n".join(
            f"[{'使用者' if m['role'] == 'user' else '助手'}]: {m['content']}"
            for m in messages
        )

        current_profile = self.user_profile.to_summary()

        prompt = f"""根據以下對話，更新使用者輪廓。只提取明確提到的資訊，不要推測。

現有輪廓：
{current_profile}

最近對話：
{messages_text}

請以 JSON 格式返回更新後的輪廓，只包含有變化的欄位：
{{
    "name": "使用者名稱（如果提到）",
    "role": "職業或角色（如果提到）",
    "preferences": ["偏好1", "偏好2"],
    "expertise": ["專長1", "專長2"],
    "ongoing_projects": ["專案1", "專案2"],
    "interaction_style": "互動風格描述"
}}

如果沒有新資訊，返回空物件 {{}}"""

        response = client.messages.create(
            model=self.config.summary_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            # 嘗試解析 JSON
            response_text = response.content[0].text
            # 處理可能的 markdown 程式碼區塊
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            updates = json.loads(response_text.strip())

            if updates:
                # 更新輪廓
                for key, value in updates.items():
                    if value and hasattr(self.user_profile, key):
                        if isinstance(value, list):
                            # 合併列表，去重
                            existing = getattr(self.user_profile, key) or []
                            setattr(self.user_profile, key, list(set(existing + value)))
                        else:
                            setattr(self.user_profile, key, value)

                self.user_profile.last_updated = datetime.now().isoformat()
                self._save_user_profile()
                self._stats["profile_updates"] += 1
                print(f"✅ 已更新使用者輪廓")

        except (json.JSONDecodeError, IndexError) as e:
            print(f"⚠️ 輪廓更新解析失敗: {e}")

    def _update_session_summary(self):
        """更新 Session 摘要"""
        if not self.session.recent_messages:
            return

        messages_text = "\n".join(
            f"[{'使用者' if m['role'] == 'user' else '助手'}]: {m['content']}"
            for m in self.session.recent_messages
        )

        existing_summary = self.session.summary or "（這是新對話的開始）"

        prompt = f"""請更新對話 Session 摘要。

現有摘要：
{existing_summary}

新增對話：
{messages_text}

請產生更新後的摘要，包含：
1. 主要討論主題
2. 關鍵決策和結論
3. 待解決的問題
4. 重要的技術細節

控制在 {self.config.session_summary_max_tokens} tokens 以內。

更新後的摘要："""

        response = client.messages.create(
            model=self.config.summary_model,
            max_tokens=self.config.session_summary_max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        self.session.summary = response.content[0].text
        self._stats["session_summaries"] += 1
        print(f"✅ 已更新 Session 摘要")

    def add_turn(self, user_message: str, assistant_message: str):
        """添加一輪對話"""
        self.session.recent_messages.append({"role": "user", "content": user_message})
        self.session.recent_messages.append({"role": "assistant", "content": assistant_message})
        self.session.turn_count += 1

        # 檢查是否需要更新
        if self.session.turn_count % self.config.session_summary_threshold == 0:
            # 更新 Session 摘要
            old_messages = self.session.recent_messages[:-self.config.recent_turns * 2]
            if old_messages:
                self._update_session_summary()
                self._update_user_profile(old_messages)
                # 只保留最近的訊息
                self.session.recent_messages = self.session.recent_messages[-self.config.recent_turns * 2:]

    def get_context(self) -> str:
        """
        取得階層式 Context

        返回格式：
        [長期記憶] + [Session 摘要] + [最近對話]
        """
        context_parts = []

        # Level 3: 長期記憶
        profile_summary = self.user_profile.to_summary()
        if profile_summary != "（尚無使用者資料）":
            context_parts.append(f"[使用者背景]\n{profile_summary}")

        # Level 2: Session 摘要
        if self.session.summary:
            context_parts.append(f"[本次對話摘要]\n{self.session.summary}")

        return "\n\n".join(context_parts)

    def get_messages(self) -> list[dict]:
        """取得要發送給 API 的訊息"""
        messages = []

        context = self.get_context()
        if context:
            messages.append({
                "role": "user",
                "content": f"{context}\n\n請基於以上背景繼續對話。"
            })
            messages.append({
                "role": "assistant",
                "content": "我已了解背景資訊，請繼續。"
            })

        messages.extend(self.session.recent_messages)
        return messages

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "session_turn_count": self.session.turn_count,
            "recent_messages": len(self.session.recent_messages),
            "has_session_summary": self.session.summary is not None,
            "has_user_profile": self.user_profile.name is not None
        }


class HierarchicalMemoryChatbot:
    """使用階層式記憶的聊天機器人"""

    def __init__(
        self,
        system_prompt: str,
        config: Optional[HierarchicalSummaryConfig] = None
    ):
        self.system_prompt = system_prompt
        self.memory = HierarchicalMemoryManager(config)

    def chat(self, user_input: str) -> str:
        messages = self.memory.get_messages()
        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages
        )

        assistant_response = response.content[0].text
        self.memory.add_turn(user_input, assistant_response)

        return assistant_response

    def get_user_profile(self) -> UserProfile:
        return self.memory.user_profile

    def get_session_summary(self) -> Optional[str]:
        return self.memory.session.summary


# 使用範例
if __name__ == "__main__":
    config = HierarchicalSummaryConfig(
        recent_turns=3,
        session_summary_threshold=5,
        long_term_memory_file="./user_memory.json"
    )

    bot = HierarchicalMemoryChatbot(
        system_prompt="你是一個專業的技術顧問。",
        config=config
    )

    # 模擬多輪對話
    test_conversations = [
        "你好，我是小明",
        "我是一個 Python 開發者",
        "主要做後端開發",
        "最近在學 Rust",
        "覺得 Rust 的所有權系統很有趣",
        "想把它用在一個高效能的服務上",
        # ... 更多對話
    ]

    for msg in test_conversations:
        print(f"\n👤 User: {msg}")
        response = bot.chat(msg)
        print(f"🤖 Bot: {response[:200]}...")

    print("\n" + "="*50)
    print("使用者輪廓：")
    print(bot.get_user_profile().to_summary())

    print("\nSession 摘要：")
    print(bot.get_session_summary() or "（尚未產生）")
```

---

## 策略四：語意壓縮（Semantic Compression）

不只是摘要，而是智能地識別和保留語意重要的內容。

### 核心概念

```
語意壓縮 vs 一般摘要：

一般摘要：
"使用者詢問了 Python GIL 的問題，我解釋了 GIL 的定義和影響..."
→ 壓縮了對話，但丟失了具體細節

語意壓縮：
{
    "entities": ["Python", "GIL", "多執行緒"],
    "facts": [
        "GIL 是 Global Interpreter Lock 的縮寫",
        "GIL 確保同一時間只有一個執行緒執行 Python bytecode",
        "可透過 multiprocessing 繞過 GIL"
    ],
    "user_understanding": "基礎",
    "pending_questions": ["如何判斷何時該用多進程 vs 多執行緒？"]
}
→ 結構化保留關鍵語意單元
```

### 完整實作

```python
import anthropic
import json
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

client = anthropic.Anthropic()


class ImportanceLevel(Enum):
    CRITICAL = "critical"    # 必須保留
    HIGH = "high"           # 高度重要
    MEDIUM = "medium"       # 中等重要
    LOW = "low"             # 可以捨棄


@dataclass
class SemanticUnit:
    """語意單元"""
    content: str
    unit_type: str  # "fact", "decision", "question", "preference", "context"
    importance: ImportanceLevel
    turn_created: int
    related_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "type": self.unit_type,
            "importance": self.importance.value,
            "turn": self.turn_created,
            "entities": self.related_entities
        }


@dataclass
class SemanticCompressionConfig:
    """語意壓縮配置"""
    # 提取設定
    extraction_model: str = "claude-haiku-4-5-20251001"

    # 保留策略
    max_semantic_units: int = 50           # 最多保留幾個語意單元
    max_context_tokens: int = 3000         # 重建 context 的最大 tokens

    # 重要性衰減
    importance_decay_rate: float = 0.1     # 每輪重要性衰減率
    min_importance_to_keep: float = 0.3    # 低於此值的單元會被移除

    # 最近對話
    recent_turns: int = 3


class SemanticMemoryStore:
    """語意記憶儲存"""

    def __init__(self, config: SemanticCompressionConfig):
        self.config = config
        self.units: list[SemanticUnit] = []
        self.entity_index: dict[str, list[int]] = {}  # entity -> unit indices
        self.current_turn: int = 0

    def add_units(self, units: list[SemanticUnit]):
        """添加語意單元"""
        for unit in units:
            idx = len(self.units)
            self.units.append(unit)

            # 更新實體索引
            for entity in unit.related_entities:
                if entity not in self.entity_index:
                    self.entity_index[entity] = []
                self.entity_index[entity].append(idx)

    def decay_importance(self):
        """衰減舊單元的重要性"""
        for unit in self.units:
            age = self.current_turn - unit.turn_created
            if age > 0:
                # 根據年齡降低重要性
                decay = 1.0 - (self.config.importance_decay_rate * age)
                decay = max(decay, 0.1)  # 最低保留 10%

                # 更新重要性等級
                if unit.importance == ImportanceLevel.CRITICAL:
                    pass  # CRITICAL 不衰減
                elif decay < 0.3:
                    unit.importance = ImportanceLevel.LOW
                elif decay < 0.6:
                    unit.importance = ImportanceLevel.MEDIUM

    def prune(self):
        """移除低重要性的單元"""
        # 按重要性排序，保留最重要的
        importance_order = {
            ImportanceLevel.CRITICAL: 4,
            ImportanceLevel.HIGH: 3,
            ImportanceLevel.MEDIUM: 2,
            ImportanceLevel.LOW: 1
        }

        sorted_units = sorted(
            self.units,
            key=lambda u: (importance_order[u.importance], -u.turn_created),
            reverse=True
        )

        # 保留前 N 個
        self.units = sorted_units[:self.config.max_semantic_units]

        # 重建實體索引
        self.entity_index = {}
        for idx, unit in enumerate(self.units):
            for entity in unit.related_entities:
                if entity not in self.entity_index:
                    self.entity_index[entity] = []
                self.entity_index[entity].append(idx)

    def get_relevant_units(self, query: str, entities: list[str]) -> list[SemanticUnit]:
        """取得與查詢相關的語意單元"""
        relevant_indices = set()

        # 根據實體匹配
        for entity in entities:
            if entity in self.entity_index:
                relevant_indices.update(self.entity_index[entity])

        # 取得相關單元
        relevant_units = [self.units[i] for i in relevant_indices]

        # 加入所有 CRITICAL 單元
        for unit in self.units:
            if unit.importance == ImportanceLevel.CRITICAL and unit not in relevant_units:
                relevant_units.append(unit)

        return relevant_units

    def to_context_string(self, units: Optional[list[SemanticUnit]] = None) -> str:
        """將語意單元重建為 context 字串"""
        units = units or self.units

        if not units:
            return ""

        # 按類型分組
        grouped = {
            "fact": [],
            "decision": [],
            "question": [],
            "preference": [],
            "context": []
        }

        for unit in units:
            if unit.unit_type in grouped:
                grouped[unit.unit_type].append(unit.content)

        # 格式化輸出
        parts = []

        if grouped["context"]:
            parts.append("背景資訊：\n" + "\n".join(f"- {c}" for c in grouped["context"]))

        if grouped["fact"]:
            parts.append("已確認的事實：\n" + "\n".join(f"- {f}" for f in grouped["fact"]))

        if grouped["decision"]:
            parts.append("已做的決定：\n" + "\n".join(f"- {d}" for d in grouped["decision"]))

        if grouped["preference"]:
            parts.append("使用者偏好：\n" + "\n".join(f"- {p}" for p in grouped["preference"]))

        if grouped["question"]:
            parts.append("待解答的問題：\n" + "\n".join(f"- {q}" for q in grouped["question"]))

        return "\n\n".join(parts)


class SemanticCompressor:
    """語意壓縮器"""

    def __init__(self, config: Optional[SemanticCompressionConfig] = None):
        self.config = config or SemanticCompressionConfig()
        self.memory = SemanticMemoryStore(self.config)
        self.recent_messages: list[dict] = []

    def _extract_semantic_units(self, messages: list[dict]) -> list[SemanticUnit]:
        """從對話中提取語意單元"""
        messages_text = "\n".join(
            f"[{'使用者' if m['role'] == 'user' else '助手'}]: {m['content']}"
            for m in messages
        )

        prompt = f"""分析以下對話，提取關鍵語意單元。

對話內容：
{messages_text}

請以 JSON 格式返回提取的語意單元列表：
[
    {{
        "content": "語意內容",
        "type": "fact|decision|question|preference|context",
        "importance": "critical|high|medium|low",
        "entities": ["相關實體1", "相關實體2"]
    }}
]

類型說明：
- fact: 已確認的事實或資訊
- decision: 已做出的決定或選擇
- question: 待解答的問題
- preference: 使用者的偏好或習慣
- context: 背景資訊

重要性說明：
- critical: 核心身份、關鍵決策（必須保留）
- high: 重要技術細節、主要目標
- medium: 一般資訊
- low: 次要細節

只返回 JSON，不要其他說明。"""

        response = client.messages.create(
            model=self.config.extraction_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            response_text = response.content[0].text
            # 處理可能的 markdown 程式碼區塊
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            units_data = json.loads(response_text.strip())

            units = []
            for data in units_data:
                unit = SemanticUnit(
                    content=data["content"],
                    unit_type=data["type"],
                    importance=ImportanceLevel(data["importance"]),
                    turn_created=self.memory.current_turn,
                    related_entities=data.get("entities", [])
                )
                units.append(unit)

            return units

        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️ 語意提取解析失敗: {e}")
            return []

    def add_turn(self, user_message: str, assistant_message: str):
        """添加一輪對話"""
        self.recent_messages.append({"role": "user", "content": user_message})
        self.recent_messages.append({"role": "assistant", "content": assistant_message})
        self.memory.current_turn += 1

        # 如果最近訊息超過保留數量，進行語意提取
        if len(self.recent_messages) > self.config.recent_turns * 2:
            # 取出要壓縮的訊息
            messages_to_compress = self.recent_messages[:-self.config.recent_turns * 2]
            self.recent_messages = self.recent_messages[-self.config.recent_turns * 2:]

            # 提取語意單元
            print(f"🔍 正在提取語意單元...")
            units = self._extract_semantic_units(messages_to_compress)

            if units:
                self.memory.add_units(units)
                print(f"✅ 提取了 {len(units)} 個語意單元")

            # 衰減和修剪
            self.memory.decay_importance()
            self.memory.prune()

    def get_context(self) -> str:
        """取得語意 context"""
        return self.memory.to_context_string()

    def get_messages(self) -> list[dict]:
        """取得要發送給 API 的訊息"""
        messages = []

        context = self.get_context()
        if context:
            messages.append({
                "role": "user",
                "content": f"[對話記憶]\n{context}\n\n請基於以上背景繼續對話。"
            })
            messages.append({
                "role": "assistant",
                "content": "我已了解背景資訊，請繼續。"
            })

        messages.extend(self.recent_messages)
        return messages

    def get_stats(self) -> dict:
        return {
            "total_semantic_units": len(self.memory.units),
            "current_turn": self.memory.current_turn,
            "recent_messages": len(self.recent_messages),
            "entities_tracked": len(self.memory.entity_index)
        }


class SemanticCompressionChatbot:
    """使用語意壓縮的聊天機器人"""

    def __init__(
        self,
        system_prompt: str,
        config: Optional[SemanticCompressionConfig] = None
    ):
        self.system_prompt = system_prompt
        self.compressor = SemanticCompressor(config)

    def chat(self, user_input: str) -> str:
        messages = self.compressor.get_messages()
        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages
        )

        assistant_response = response.content[0].text
        self.compressor.add_turn(user_input, assistant_response)

        return assistant_response

    def get_memory_snapshot(self) -> list[dict]:
        """取得記憶快照"""
        return [unit.to_dict() for unit in self.compressor.memory.units]


# 使用範例
if __name__ == "__main__":
    config = SemanticCompressionConfig(
        recent_turns=2,
        max_semantic_units=30
    )

    bot = SemanticCompressionChatbot(
        system_prompt="你是一個專業的技術顧問。",
        config=config
    )

    conversations = [
        "你好，我叫小明，是後端工程師",
        "我擅長 Python 和 Go",
        "最近在開發一個即時通訊系統",
        "使用 WebSocket 進行雙向通訊",
        "遇到了連線數擴展的問題",
        "目前單機只能支撐 10000 連線",
        "想要擴展到 100000 連線",
        "你建議用什麼架構？",
        # 更多對話...
    ]

    for msg in conversations:
        print(f"\n👤 User: {msg}")
        response = bot.chat(msg)
        print(f"🤖 Bot: {response[:200]}...")

    print("\n" + "="*50)
    print("記憶快照：")
    for unit in bot.get_memory_snapshot():
        print(f"  [{unit['importance']}] ({unit['type']}) {unit['content'][:50]}...")
```

---

## 策略五：混合壓縮系統

結合多種策略的生產級系統。

### 架構設計

```
混合壓縮系統架構：

┌─────────────────────────────────────────────────────────────┐
│                    混合壓縮管理器                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  輸入：新的對話訊息                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. 即時分類                                          │   │
│  │    判斷訊息類型：事實/問題/閒聊/指令                  │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 2. 重要性評估                                        │   │
│  │    根據類型和內容判斷保留優先級                      │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 3. 儲存策略選擇                                      │   │
│  │    - CRITICAL → 長期記憶                             │   │
│  │    - HIGH     → 語意單元                             │   │
│  │    - MEDIUM   → Session 摘要                        │   │
│  │    - LOW      → 滑動視窗（可丟棄）                   │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 4. Context 重建                                      │   │
│  │    根據當前查詢動態組合相關記憶                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 完整實作

```python
import anthropic
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
import json

client = anthropic.Anthropic()


class MessageType(Enum):
    FACT = "fact"           # 事實陳述
    QUESTION = "question"   # 問題
    INSTRUCTION = "instruction"  # 指令
    CHITCHAT = "chitchat"   # 閒聊
    FEEDBACK = "feedback"   # 反饋


@dataclass
class HybridCompressionConfig:
    """混合壓縮配置"""
    # 模型設定
    classification_model: str = "claude-haiku-4-5-20251001"
    summarization_model: str = "claude-haiku-4-5-20251001"
    main_model: str = "claude-sonnet-4-6"

    # 各層容量
    recent_turns: int = 3
    session_summary_max_tokens: int = 500
    semantic_units_max: int = 20
    long_term_facts_max: int = 10

    # 壓縮觸發
    compression_interval: int = 5


@dataclass
class MemoryLayers:
    """記憶層級"""
    # Layer 1: 最近對話（完整保留）
    recent: list[dict] = field(default_factory=list)

    # Layer 2: Session 摘要
    session_summary: Optional[str] = None

    # Layer 3: 語意單元
    semantic_units: list[dict] = field(default_factory=list)

    # Layer 4: 長期事實
    long_term_facts: list[str] = field(default_factory=list)


class HybridCompressionManager:
    """
    混合壓縮管理器

    結合多種策略：
    - 滑動視窗：保留最近對話
    - 漸進摘要：壓縮 Session 歷史
    - 語意提取：保留關鍵語意單元
    - 長期記憶：持久化重要事實
    """

    def __init__(self, config: Optional[HybridCompressionConfig] = None):
        self.config = config or HybridCompressionConfig()
        self.memory = MemoryLayers()
        self.turn_count = 0
        self._pending_messages: list[dict] = []  # 待處理的訊息

        self._stats = {
            "classifications": 0,
            "summaries": 0,
            "extractions": 0,
            "total_tokens_saved": 0
        }

    def _classify_message(self, message: str) -> tuple[MessageType, float]:
        """
        分類訊息類型和重要性

        Returns:
            (類型, 重要性分數 0-1)
        """
        prompt = f"""分析以下訊息，判斷其類型和重要性。

訊息："{message}"

請以 JSON 格式回答：
{{
    "type": "fact|question|instruction|chitchat|feedback",
    "importance": 0.0-1.0,
    "reason": "簡短說明"
}}

類型說明：
- fact: 陳述事實或資訊
- question: 提問
- instruction: 給出指令或要求
- chitchat: 閒聊、寒暄
- feedback: 對之前回應的反饋

重要性判斷：
- 1.0: 核心身份、關鍵決策
- 0.7-0.9: 重要資訊、技術細節
- 0.4-0.6: 一般資訊
- 0.1-0.3: 閒聊、過渡性內容

只返回 JSON。"""

        response = client.messages.create(
            model=self.config.classification_model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        self._stats["classifications"] += 1

        try:
            result = json.loads(response.content[0].text)
            return MessageType(result["type"]), result["importance"]
        except (json.JSONDecodeError, KeyError, ValueError):
            return MessageType.CHITCHAT, 0.5

    def _update_session_summary(self):
        """更新 Session 摘要"""
        if not self._pending_messages:
            return

        messages_text = "\n".join(
            f"[{'使用者' if m['role'] == 'user' else '助手'}]: {m['content']}"
            for m in self._pending_messages
        )

        existing = self.memory.session_summary or ""

        prompt = f"""更新對話摘要。

現有摘要：
{existing if existing else "（無）"}

新對話：
{messages_text}

請產生更新後的摘要，控制在 {self.config.session_summary_max_tokens} tokens 以內。
重點保留：主題、決策、待解決問題。

更新後的摘要："""

        response = client.messages.create(
            model=self.config.summarization_model,
            max_tokens=self.config.session_summary_max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        self.memory.session_summary = response.content[0].text
        self._stats["summaries"] += 1
        self._pending_messages = []

    def _extract_semantic_units(self, messages: list[dict]) -> list[dict]:
        """提取語意單元"""
        messages_text = "\n".join(
            f"[{'使用者' if m['role'] == 'user' else '助手'}]: {m['content']}"
            for m in messages
        )

        prompt = f"""從對話中提取關鍵語意單元。

對話：
{messages_text}

請以 JSON 列表格式返回，每個單元包含：
[
    {{
        "content": "語意內容",
        "type": "fact|decision|preference",
        "importance": 0.0-1.0
    }}
]

只提取重要性 > 0.6 的單元。只返回 JSON。"""

        response = client.messages.create(
            model=self.config.summarization_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        self._stats["extractions"] += 1

        try:
            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].split("```")[0]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            return []

    def _check_long_term_fact(self, message: str, msg_type: MessageType, importance: float) -> bool:
        """檢查是否應加入長期事實"""
        # 只有高重要性的事實類訊息才加入長期記憶
        if msg_type == MessageType.FACT and importance >= 0.8:
            # 避免重複
            if not any(message in fact or fact in message for fact in self.memory.long_term_facts):
                if len(self.memory.long_term_facts) < self.config.long_term_facts_max:
                    self.memory.long_term_facts.append(message)
                    return True
        return False

    def add_turn(self, user_message: str, assistant_message: str):
        """添加一輪對話"""
        self.turn_count += 1

        # 分類使用者訊息
        msg_type, importance = self._classify_message(user_message)

        # 檢查是否加入長期事實
        self._check_long_term_fact(user_message, msg_type, importance)

        # 添加到最近對話
        self.memory.recent.append({"role": "user", "content": user_message})
        self.memory.recent.append({"role": "assistant", "content": assistant_message})

        # 添加到待處理佇列
        self._pending_messages.append({"role": "user", "content": user_message})
        self._pending_messages.append({"role": "assistant", "content": assistant_message})

        # 檢查是否需要壓縮
        if self.turn_count % self.config.compression_interval == 0:
            self._perform_compression()

    def _perform_compression(self):
        """執行壓縮"""
        # 計算壓縮前的 token 數
        before_tokens = sum(len(m["content"]) for m in self.memory.recent) * 0.4

        # 1. 更新 Session 摘要
        if self._pending_messages:
            self._update_session_summary()

        # 2. 從舊訊息提取語意單元
        if len(self.memory.recent) > self.config.recent_turns * 2:
            old_messages = self.memory.recent[:-self.config.recent_turns * 2]

            new_units = self._extract_semantic_units(old_messages)

            # 合併語意單元，保留最重要的
            self.memory.semantic_units.extend(new_units)
            self.memory.semantic_units.sort(key=lambda x: x.get("importance", 0), reverse=True)
            self.memory.semantic_units = self.memory.semantic_units[:self.config.semantic_units_max]

            # 3. 只保留最近的訊息
            self.memory.recent = self.memory.recent[-self.config.recent_turns * 2:]

        # 計算壓縮後的 token 數
        after_tokens = self._estimate_context_tokens()
        self._stats["total_tokens_saved"] += max(0, before_tokens - after_tokens)

        print(f"✅ 壓縮完成：{int(before_tokens)} → {int(after_tokens)} tokens")

    def _estimate_context_tokens(self) -> int:
        """估算當前 context 的 token 數"""
        total = 0

        # 長期事實
        total += sum(len(f) for f in self.memory.long_term_facts) * 0.4

        # 語意單元
        total += sum(len(u.get("content", "")) for u in self.memory.semantic_units) * 0.4

        # Session 摘要
        if self.memory.session_summary:
            total += len(self.memory.session_summary) * 0.4

        # 最近對話
        total += sum(len(m["content"]) for m in self.memory.recent) * 0.4

        return int(total)

    def get_context(self) -> str:
        """取得格式化的 context"""
        parts = []

        # Layer 4: 長期事實
        if self.memory.long_term_facts:
            facts = "\n".join(f"- {f}" for f in self.memory.long_term_facts)
            parts.append(f"[核心資訊]\n{facts}")

        # Layer 3: 語意單元
        if self.memory.semantic_units:
            units = "\n".join(f"- {u['content']}" for u in self.memory.semantic_units[:10])
            parts.append(f"[關鍵記憶]\n{units}")

        # Layer 2: Session 摘要
        if self.memory.session_summary:
            parts.append(f"[對話摘要]\n{self.memory.session_summary}")

        return "\n\n".join(parts)

    def get_messages(self) -> list[dict]:
        """取得要發送給 API 的訊息"""
        messages = []

        context = self.get_context()
        if context:
            messages.append({
                "role": "user",
                "content": f"{context}\n\n請基於以上背景繼續對話。"
            })
            messages.append({
                "role": "assistant",
                "content": "我已了解背景，請繼續。"
            })

        messages.extend(self.memory.recent)
        return messages

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "turn_count": self.turn_count,
            "long_term_facts": len(self.memory.long_term_facts),
            "semantic_units": len(self.memory.semantic_units),
            "has_session_summary": self.memory.session_summary is not None,
            "recent_messages": len(self.memory.recent),
            "estimated_context_tokens": self._estimate_context_tokens()
        }


class HybridCompressionChatbot:
    """使用混合壓縮的聊天機器人"""

    def __init__(
        self,
        system_prompt: str,
        config: Optional[HybridCompressionConfig] = None
    ):
        self.system_prompt = system_prompt
        self.manager = HybridCompressionManager(config)

    def chat(self, user_input: str) -> str:
        messages = self.manager.get_messages()
        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model=self.manager.config.main_model,
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages
        )

        assistant_response = response.content[0].text
        self.manager.add_turn(user_input, assistant_response)

        return assistant_response


# 使用範例與效能測試
if __name__ == "__main__":
    config = HybridCompressionConfig(
        recent_turns=2,
        compression_interval=3,
        semantic_units_max=15,
        long_term_facts_max=5
    )

    bot = HybridCompressionChatbot(
        system_prompt="你是一個專業的技術顧問。",
        config=config
    )

    # 模擬長對話
    test_messages = [
        "你好，我是小明，是資深後端工程師",  # 高重要性事實
        "我在一家電商公司工作",  # 高重要性事實
        "今天天氣真好",  # 低重要性閒聊
        "我們的系統使用微服務架構",  # 中等重要性
        "主要用 Go 和 Python",  # 高重要性技術事實
        "最近遇到一個效能問題",  # 問題
        "資料庫查詢太慢",  # 問題細節
        "你有什麼建議嗎？",  # 問題
        "我試過加索引了",  # 反饋
        "效果不太好",  # 反饋
        "還有其他方法嗎？",  # 問題
        "你還記得我用什麼語言嗎？",  # 測試記憶
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"\n{'='*60}")
        print(f"Turn {i}: {msg}")
        response = bot.chat(msg)
        print(f"Bot: {response[:150]}...")
        print(f"\n📊 Stats: {bot.manager.get_stats()}")

    print("\n" + "="*60)
    print("最終記憶狀態：")
    print(f"\n長期事實：{bot.manager.memory.long_term_facts}")
    print(f"\n語意單元數：{len(bot.manager.memory.semantic_units)}")
    print(f"\nSession 摘要：{bot.manager.memory.session_summary}")
```

---

## 效能比較與選擇指南

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Context 壓縮策略比較                              │
├──────────────────┬──────────┬──────────┬──────────┬────────────────┤
│ 策略             │ 壓縮率   │ 資訊保留 │ 實作複雜 │ 適用場景       │
├──────────────────┼──────────┼──────────┼──────────┼────────────────┤
│ 滑動視窗         │ 固定     │ ★★      │ ★        │ 短期對話       │
│ 漸進式摘要       │ 70-90%   │ ★★★★   │ ★★★     │ 長期對話       │
│ 階層式摘要       │ 80-95%   │ ★★★★★  │ ★★★★   │ 跨 Session     │
│ 語意壓縮         │ 85-95%   │ ★★★★★  │ ★★★★★  │ 知識密集型     │
│ 混合壓縮         │ 90-98%   │ ★★★★★  │ ★★★★★  │ 生產環境       │
└──────────────────┴──────────┴──────────┴──────────┴────────────────┘

選擇指南：

1. 簡單聊天機器人（< 20 輪）
   → 滑動視窗

2. 客服系統（20-100 輪）
   → 漸進式摘要

3. 個人助理（跨 Session）
   → 階層式摘要 + 持久化

4. 專業諮詢系統
   → 語意壓縮

5. 企業級應用
   → 混合壓縮系統
```

---

## 最佳實踐清單

```
Context 壓縮 Checklist：

基礎設定
□ 是否設定了合理的 Context 上限？
□ 是否有壓縮觸發機制（輪數/token 數）？
□ 是否選擇了適合場景的壓縮策略？

摘要品質
□ 摘要是否保留了關鍵資訊？
□ 摘要模型是否選擇了 cost-effective 的選項？
□ 是否有摘要品質驗證機制？

記憶管理
□ 是否區分了不同重要性的資訊？
□ 是否有資訊衰減機制？
□ 長期記憶是否有持久化？

效能監控
□ 是否追蹤壓縮率？
□ 是否監控 Context token 使用量？
□ 是否有回歸測試確保記憶品質？

特殊處理
□ 是否處理了使用者身份資訊？
□ 是否處理了關鍵決策記錄？
□ 是否處理了待解決問題追蹤？
```

---

## 總結

Context 壓縮與摘要是打造「可無限對話」AI 系統的核心技術。本文介紹的各種策略可以根據需求靈活組合：

| 需求 | 推薦策略 |
|------|----------|
| 快速上線 | 滑動視窗 |
| 長對話支援 | 漸進式摘要 |
| 使用者記憶 | 階層式摘要 |
| 知識密集場景 | 語意壓縮 |
| 生產環境 | 混合壓縮 |

關鍵原則：
1. **分層處理**：不同重要性的資訊用不同策略
2. **漸進壓縮**：避免一次性大量壓縮造成資訊損失
3. **語意優先**：保留語意完整性比保留原文更重要
4. **持續監控**：追蹤壓縮率和記憶品質

透過合理的 Context 管理，你可以打造出成本可控、體驗優良的長期對話 AI 系統。
