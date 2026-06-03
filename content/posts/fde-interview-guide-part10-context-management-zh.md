---
title: "FDE 面試準備指南（十）：RKK 實戰——AI Agent 的 Context Management"
date: 2026-06-03T09:00:00+08:00
draft: false
description: "以系統設計視角拆解 AI Agent 的 Context Management：核心問題是什麼、有哪些策略、為什麼選這個、trade-off 怎麼算——含完整架構圖與面試答題框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Context Management", "LLM", "Context Window", "Memory", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "16 min"
---

> Context Management 的核心問題只有一個：  
> **LLM 是無狀態的，但對話是有狀態的。**  
> 怎麼在有限的 context window 裡，讓 LLM 「看到」最有用的資訊——這就是你要設計的系統。

---

## 一、核心問題：為什麼 Context 會是瓶頸

每次呼叫 LLM，你送進去的所有 token 都要過一次 attention 計算。這意味著：

- **成本**：input token 按量計費，context 越長越貴
- **延遲**：attention 複雜度是 O(n²)，context 長度翻倍、延遲接近翻兩倍
- **品質**：「Lost-in-the-Middle」效應——LLM 對中段資訊的注意力顯著弱化
- **爆炸**：超過 context window 上限就直接報錯，Agent 中斷

```
輪次  1:  750 tokens
輪次  5:  3,750 tokens
輪次 20:  15,000 tokens
輪次 50:  37,500 tokens   ← GPT-4o 128K window 的 30%
輪次100:  75,000 tokens   ← 快撐滿了
```

面試官問法：

> *「你的 multi-turn Agent 在第 50 輪對話時，會發生什麼問題？你怎麼設計解決它？」*

---

## 二、系統全貌：一個請求的 Context 組成

在設計策略前，先看清楚 context 是怎麼組成的：

```
┌─────────────────────────────────────────────┐
│              LLM Context Window             │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ System Prompt (固定，~500 tokens)   │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │ User Profile (Semantic Memory)      │    │
│  │ ~200 tokens，每輪載入               │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │ Retrieved Context (RAG chunks)      │    │
│  │ ~1,500 tokens，依查詢動態注入        │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │ Conversation History ← 這裡會爆     │    │
│  │ 隨輪次線性成長                       │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │ Current User Query (~50 tokens)     │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │ [Reserve for Output] (~2,000 tokens)│    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**問題的根源**：Conversation History 是唯一隨時間無限成長的部分。其他區塊都是可控的。

---

## 三、四種策略：你有哪些選擇

### 策略一覽

```
Context 管理策略
│
├── Sliding Window     → 只保留最近 N 輪
│                        簡單，但會丟失早期資訊
│
├── Summary Buffer     → 舊對話壓縮成摘要 + 保留近期完整歷史
│                        語意連貫，但壓縮需要額外 LLM 呼叫
│
├── Retrieval Memory   → 對話存向量 DB，每輪按相關性召回
│                        最彈性，但需要向量基礎設施
│
└── Structured State   → 不存對話，只維護結構化狀態物件
                         最穩定，但需要精心設計 schema
```

---

### 策略一：Sliding Window

```
時間軸 →
[輪1][輪2][輪3][輪4][輪5][輪6][輪7][輪8][輪9][輪10]
                          ↑
                     Window (保留最近 5 輪)
                     [輪6][輪7][輪8][輪9][輪10]
                          ↑
                     輪1~5 永久丟失
```

**核心機制：** 超過視窗大小時，移除最舊的一輪（user + assistant 各一條）。

**為什麼選它：**
- 實作最簡單，一個 deque 就能搞定
- Context 大小完全可預測（`max_turns × avg_tokens_per_turn`）
- 對話相對獨立的場景（FAQ、工單查詢），早期歷史不重要

**為什麼不選它：**
- 用戶說的「之前提到的那個需求」可能已經滾出視窗
- 長任務場景（研究、計畫）會失去上下文連貫性

---

### 策略二：Summary Buffer

```
完整對話歷史
     │
     ├── [輪 1~N-10]  →  LLM 壓縮  →  Summary (500 tokens)
     │                                  "用戶詢問了 A 問題，
     │                                   確認了 B 需求，
     │                                   遺留 C 問題待解決"
     │
     └── [輪 N-10~N]  →  完整保留（3,000 tokens）

注入 LLM 的 context：
[Summary] + [近期完整歷史] ≈ 3,500 tokens（固定上限）
```

**為什麼選它：**
- 保留語意連貫性——「三個月前的對話」仍有摘要可查
- Context 大小可控，不會隨輪次線性成長

**核心 trade-off：**
- 壓縮本身需要一次 LLM 呼叫（成本 + 延遲）
- 壓縮可能丟失細節——錯誤碼、具體數字容易被摘要丟掉
- 壓縮品質依賴壓縮 prompt 的設計

**適用場景：** 客服、顧問類 Agent——用戶期待 AI「記得」以前說過什麼。

---

### 策略三：Retrieval Memory

```
對話發生
   │
   ▼
┌──────────────────────────┐
│   Conversation Archive   │  ← 所有對話存這裡
│   (向量資料庫)            │     不限時間，不限數量
└──────────────────────────┘
          │
          │ 每輪對話開始時
          ▼
   Query: 當前用戶問題
          │
          ▼
┌──────────────────────────┐
│   Semantic Search        │  ← 用相似度找出相關的歷史片段
│   (top-k retrieval)      │
└──────────────────────────┘
          │
          ▼
   注入最相關的 3~5 條歷史記憶
   進入 LLM context
```

**為什麼選它：**
- 能「想起來」幾個月前說過的話，只要語意相關
- 沒有 window 限制，理論上可以無限對話
- 可以跨 session 保留記憶

**核心 trade-off：**
- 需要維護向量資料庫（基礎設施成本）
- 相關性搜尋可能打亂對話連貫性（撿到的片段缺乏前後文）
- 向量搜尋本身有延遲（50~200ms）

**適用場景：** 長期個人助理、跨 session 的知識型 Agent。

---

### 策略四：Structured State

```
傳統方式（存對話）：
[user]: 我要訂機票去台北，預算 5000
[ai]: 好的，請問出發日期？
[user]: 下週五
[ai]: 找到 3 個選項...
... (越來越長)

結構化方式（存狀態）：
{
  "task": "訂機票",
  "destination": "台北",
  "budget": 5000,
  "departure_date": "2026-06-07",
  "status": "showing_options",
  "options_shown": 3
}
→ 任何輪次，context 大小固定不變
```

**為什麼選它：**
- Context 大小完全穩定——第 1 輪和第 100 輪一樣大
- 資訊密度最高——沒有冗餘的對話格式
- 適合有明確工作流的 task-oriented Agent

**核心 trade-off：**
- 需要預先設計好 state schema（upfront design cost）
- 不適合開放式對話——無法捕捉用戶語氣、情緒等非結構化資訊
- State 更新本身需要 LLM 提取（多一道工序）

---

## 四、決策框架：選哪個

```
你的 Agent 是什麼類型？
         │
         ├── 任務明確、有固定流程？
         │        └─→ Structured State
         │
         ├── 長期個人助理、需要跨 session 記憶？
         │        └─→ Retrieval Memory
         │
         ├── 客服/顧問、需要「記得以前說過什麼」？
         │        └─→ Summary Buffer
         │
         └── 短對話、每輪相對獨立？
                  └─→ Sliding Window（最簡單，先上線再說）
```

### 策略比較表

| | Sliding Window | Summary Buffer | Retrieval Memory | Structured State |
|--|:-:|:-:|:-:|:-:|
| **實作難度** | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Context 可預測性** | ✅ | ✅ | ✅ | ✅✅ |
| **長期記憶能力** | ❌ | △ | ✅✅ | ❌ |
| **額外基礎設施** | 無 | 無 | 向量 DB | 無 |
| **額外 LLM 呼叫** | 無 | 有（壓縮時） | 有（embedding） | 有（state 提取） |
| **適合開放對話** | ✅ | ✅ | ✅ | ❌ |

---

## 五、關鍵考量：Lost-in-the-Middle

這是所有策略都要面對的底層問題。

```
LLM 注意力分布（長 context 時）：

注意力
  ▲
高 │██                                    ██
   │ ██                                  ██
   │   ██                              ██
低 │     ████████████████████████████
   └──────────────────────────────────────→
      開頭                              結尾
      （System Prompt）           （當前 Query）

中間區域：RAG chunks、歷史對話  ← LLM 最容易忽略
```

**工程應對：**

```
好的 Context 排列順序：

[1] System Prompt（開頭，高注意力）
    ↓
[2] User Profile（緊接著，確保被讀到）
    ↓
[3] Retrieved Context（中間，用結構化標記框住）
    <documents>...</documents>
    ↓
[4] Conversation Summary（中間）
    ↓
[5] Recent History（靠近結尾）
    ↓
[6] Current Query + 重申關鍵指令（結尾，高注意力）
    "記住以上規則，請回答：{query}"
```

---

## 六、Token 監控：防患未然

```
Token 使用監控架構：

每次請求前
    │
    ▼
┌──────────────────────────┐
│   Token Counter          │
│   (tiktoken / count_tokens API)
└──────────────────────────┘
    │
    ├── < 60% max → 正常送出
    │
    ├── 60~80% → 警告，觸發壓縮評估
    │
    └── > 80% → 強制壓縮 / 截斷 / 降低 top-k
```

**Context Window 現實數字：**

| 模型 | 上限 | 建議使用上限 | 原因 |
|------|------|------------|------|
| Gemini 1.5 Pro | 1M | 700K | 留 output 空間 + 延遲考量 |
| Gemini 2.0 Flash | 1M | 700K | 同上 |
| GPT-4o | 128K | 100K | output reserve |
| Claude 3.5 Sonnet | 200K | 150K | 同上 |

「有 1M context 所以不用管理」——這是成本陷阱，不是工程思維。

---

## 七、面試答題框架：SCOPE

被問到 context management 類題目：

```
S → Size      先估算：這個場景的 context 多快會滿？
C → Cost      context 長了對成本和延遲的量化影響
O → Options   你有哪些策略（sliding/summary/retrieval/state）
P → Pick      選哪個？說出 trade-off
E → Edge      你的策略在什麼情況下會失效？
```

**完整範例回答：**

> *「這個客服 Agent，每輪 300 tokens，100 輪就是 30K。加上 system prompt 和 RAG context，約 50K。Gemini Flash 雖然有 1M，但 50K 的每次推理成本和延遲是有感的。*
>
> *我會用 Summary Buffer + Structured State 混合：保留最近 10 輪完整對話（3K tokens），把早期對話壓縮成 case summary（500 tokens）。同時維護結構化 state 記錄關鍵欄位：product_id、error_code、resolution_status。*
>
> *失效場景：壓縮時可能丟掉關鍵的錯誤碼。所以壓縮 prompt 要明確標記「以下欄位必須保留」，並在 structured state 同步儲存關鍵數值。另外加 token 監控，超過 80% 自動觸發壓縮。」*

---

**系列導覽：**  
← [（九）LLM 核心知識](../fde-interview-guide-part9-llm-core-zh/)  
→ [（十一）RKK 實戰：Agent 線上除錯與故障排除](../fde-interview-guide-part11-agent-debugging-zh/)
