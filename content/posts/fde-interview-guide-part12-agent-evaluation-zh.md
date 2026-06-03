---
title: "FDE 面試準備指南（十二）：RKK 實戰——AI Agent 統計評估與品質量化"
date: 2026-06-03T11:00:00+08:00
draft: false
description: "以系統設計視角拆解 AI Agent 的 Evaluation Pipeline：核心問題是什麼、RAG 評估三角怎麼設計、LLM-as-Judge 的取捨、以及怎麼讓 eval 成為持續整合的一環——含完整架構圖"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Evaluation", "Metrics", "RAG", "RAGAS", "LLM", "Observability", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "15 min"
---

> 你怎麼知道 Agent 可以上線？  
> 直覺不算，「感覺還不錯」不算。  
> FDE 的工作是把感覺轉成數字，把數字轉成信心——讓客戶的工程團隊能基於證據做決定。

---

## 一、核心問題：「夠好」的標準是什麼

Agent 評估的難點不是「怎麼算分」，而是「對誰問什麼問題，要達到什麼分才算夠好」。

三個不同維度的「夠好」：

```
評估的三個維度（缺一不可）

┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  效能（Performance）│    │  品質（Quality）    │    │  業務（Business）  │
│                   │    │                   │    │                   │
│  快不快？          │    │  對不對？          │    │  有沒有用？        │
│  貴不貴？          │    │  準不準？          │    │  用戶滿不滿意？    │
│                   │    │                   │    │                   │
│  tokens/sec       │    │  Faithfulness     │    │  Task completion  │
│  p95 latency      │    │  Relevance        │    │  User retention   │
│  cost/request     │    │  Groundedness     │    │  Escalation rate  │
└───────────────────┘    └───────────────────┘    └───────────────────┘
        ↑                         ↑                        ↑
   系統層關心              工程師關心               客戶關心
```

只看品質、不看效能：上線後延遲爆炸。  
只看效能、不看業務：系統跑得很快但沒解決問題。

---

## 二、Eval Pipeline 架構

```
┌─────────────────────────────────────────────────────┐
│                   Eval Pipeline                      │
│                                                      │
│  ┌──────────────┐                                    │
│  │  Test Dataset │  ← 黃金測試集（手動標注 or 抽樣）  │
│  │  (Q, Context, │                                   │
│  │   GT Answer) │                                    │
│  └──────┬───────┘                                    │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐    ┌──────────────────────────┐    │
│  │   Agent Run  │ →  │  Response Collection     │    │
│  └──────────────┘    └──────────┬───────────────┘    │
│                                 │                    │
│                    ┌────────────┴──────────────┐     │
│                    ▼                           ▼     │
│           ┌──────────────┐         ┌──────────────┐  │
│           │ Auto Metrics │         │ LLM-as-Judge │  │
│           │ (RAGAS, NLI) │         │              │  │
│           └──────┬───────┘         └──────┬───────┘  │
│                  └──────────┬─────────────┘          │
│                             ▼                        │
│                    ┌──────────────────┐              │
│                    │  Score Aggregator│              │
│                    │  + Regression    │              │
│                    │    Detector      │              │
│                    └──────┬───────────┘              │
│                           │                          │
│              ┌────────────┴────────────┐             │
│              ▼                         ▼             │
│     ┌──────────────┐         ┌──────────────────┐    │
│     │ Pass / Fail  │         │  Regression Alert│    │
│     │ (vs baseline)│         │  (if delta > 5%) │    │
│     └──────────────┘         └──────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## 三、RAG 品質評估：三角模型

RAG Agent 的品質問題有三個獨立的來源，需要分開量化：

```
           ╔══════════════════╗
           ║   Faithfulness   ║
           ║                  ║
           ║  回答的每個聲明    ║
           ║  都能在文件中找到  ║
           ║  依據嗎？         ║
           ╚════════╤═════════╝
                    │
          ←─────────┴──────────→
         /                      \
        /                        \
╔══════╧═══════╗        ╔═════════╧══════╗
║   Context    ║        ║    Answer      ║
║   Relevance  ║        ║    Relevance   ║
║              ║        ║                ║
║ 檢索到的文件  ║        ║  回答有沒有     ║
║ 和問題有關嗎？║        ║  回答到問題？  ║
╚══════════════╝        ╚════════════════╝
```

**三個指標各自診斷不同的問題：**

| 指標低 | 代表問題在哪 | 怎麼修 |
|--------|------------|--------|
| Context Relevance 低 | Retrieval 層——找回來的文件不相關 | 換 embedding model、調 top-k、改 chunking 策略 |
| Faithfulness 低 | Generation 層——LLM 捏造了內容 | 加強 system prompt 限制、提高 retrieval 品質 |
| Answer Relevance 低 | 回答跑偏了——沒回答問題 | 調整 prompt 讓 LLM 更 focus on query |

**分數解讀範例：**
```
Context Relevance: 0.85  → 檢索還不錯
Faithfulness:      0.60  → ⚠️ LLM 有幻覺問題，優先處理
Answer Relevance:  0.88  → 回答方向正確
```

---

## 四、效能指標：LLM-native Metrics

JD 提到的「LLM-native metrics」——面試時說出來有加分：

```
成本計算模型：

每次請求成本 = (input_tokens × input_price) + (output_tokens × output_price)
                                                    ↑
                                             通常貴 3~5 倍

以 Gemini 1.5 Pro 為例（$1.25/1M input, $5.00/1M output）：
  input:  2,500 tokens → $0.003125
  output:   400 tokens → $0.002000
  per request:           $0.005125

規模推算（10K req/day）：
  daily:   $51.25
  monthly: ~$1,538
  → 這是 semantic cache hit rate 提升到 40% 後能省 $600/月的依據
```

**延遲分位數比平均值重要：**

```
延遲分佈（典型 RAG Agent）：

請求數
  ▲
  │  ████
  │  █████
  │  ██████
  │  ███████
  │  █████████
  │  ████████████
  │  ████████████████
  └──────────────────────────────→ 延遲 (ms)
     0  500 1000 2000 5000 10000

p50: 1,200ms  ← 一般用戶感受
p95: 4,500ms  ← 大多數用戶的最差體驗
p99: 9,000ms  ← SLA 通常看這個

「平均 1.5 秒」掩蓋了 5% 的用戶等了 4.5 秒以上
```

---

## 五、LLM-as-Judge：什麼時候用，什麼時候不能信

### 使用時機

```
有 Ground Truth → 用 Automatic Metrics（RAGAS, NLI）
                     精確、快速、便宜、可重現

沒有 Ground Truth → 用 LLM-as-Judge
（開放式問題、    評估主觀品質（語氣、完整性、有用性）
 創意生成）
```

### LLM-as-Judge 的已知偏差（面試必須主動提出）

```
偏差類型及緩解方法：

1. 自我偏愛（Self-preference bias）
   └─ 用同一家公司的 LLM 評估自己的輸出，分數虛高
      緩解：用不同廠商的 LLM 當評審

2. 位置偏差（Position bias）
   └─ 評估兩個回答時，傾向認為第一個更好
      緩解：A/B 互換位置，取平均

3. 冗長偏差（Verbosity bias）
   └─ 傾向認為更長的回答更好（即使沒有實質差異）
      緩解：在 judge prompt 明確說「簡潔不是缺點」

4. 隨機性
   └─ 同一個評估可能產生不同分數
      緩解：多次評估取平均（n=3 以上）
```

---

## 六、Agent 任務評估：超越 RAG

Multi-step Agent 的評估，不能只看最終答案：

```
Task Evaluation 維度：

最終結果 ←─────────────────────────────────────────┐
  └── 答對了嗎？（Correctness）                      │
  └── 完成任務了嗎？（Task Completion Rate）          │
                                                    │
執行路徑 ←──────────────────────────────────────────┤
  └── 工具呼叫順序合理嗎？（Trajectory Quality）      │
  └── 有沒有不必要的工具呼叫？（Efficiency）          │
  └── 幾步完成？（Steps to Completion）              │
                                                    │
效率 ←─────────────────────────────────────────────┘
  └── 成本（Total tokens used）
  └── 時間（End-to-end latency）
```

**Trajectory Evaluation（路徑評估）：**

```
Expected path:     search → calculate → answer
Agent actual path: search → search → calculate → calculate → answer

分析：
  ├── 多了一次 search → 可能 Retrieval 不準，Agent 在補救
  └── 多了一次 calculate → 可能計算結果不確定，Agent 在驗算

結論：路徑效率 = 3/5 = 0.60，需要優化 Retrieval 精度
```

---

## 七、建立 Eval 的核心設計決策

### 測試集怎麼來

```
測試集來源優先順序：

1. 真實用戶查詢（最有價值）
   └─ 從 production logs 抽樣 + 人工標注答案
   └─ 代表真實分布，最能預測上線效果

2. 人工設計（涵蓋邊界情況）
   └─ 刁鑽問題、多義問題、超出範圍的問題
   └─ 確保系統在邊界情況下表現正確

3. LLM 生成（快速擴充量）
   └─ 用 LLM 根據知識庫生成問答對
   └─ 便宜快速，但品質需要人工驗核
   └─ 風險：生成的問題可能不反映真實用戶需求
```

### 何時跑 Eval

```
CI/CD 整合：

代碼提交
    │
    ▼
┌──────────────────────────────┐
│  Pre-merge Eval              │
│  (快速版，100~200 個問題)    │  ← 5~10 分鐘內完成
│  確保沒有明顯 regression     │
└──────────────────────────────┘
    │ merge
    ▼
┌──────────────────────────────┐
│  Full Eval                   │
│  (完整版，1000+ 個問題)      │  ← 非同步跑，不卡 deployment
│  詳細的品質分析              │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│  Production Eval             │
│  (Shadow mode / A/B test)    │  ← 用真實流量驗證
└──────────────────────────────┘
```

---

## 八、跟客戶溝通評估結果

面試的 consulting 題型——你怎麼讓客戶理解數字並做出決定：

**客戶問：「Faithfulness 0.85 夠好嗎？」**

> *「0.85 意思是每 100 個回答裡，有大約 15 個包含了知識庫以外的資訊。夠不夠好取決於你的業務風險：*
> - *內部 IT 幫助台：0.85 可能夠，偶爾的不準確用戶可以自行驗證*
> - *客戶面的產品問答：建議 0.90+，避免給錯誤資訊影響用戶信任*
> - *法律或醫療建議：0.95+，甚至不適合用 RAG，需要更嚴格的管控*
>
> *我們先定義你的 acceptable threshold，然後我告訴你現在離目標有多遠、以及最快的改善路徑。」*

---

## 九、快速複習卡

```
評估三維度：效能（快/貴）→ 品質（對/準）→ 業務（有用）

RAG 評估三角：
  Context Relevance → Retrieval 層問題
  Faithfulness      → Generation 層問題（幻覺）
  Answer Relevance  → Prompt 設計問題

LLM-native Metrics：
  tokens/sec、TTFT p95、cost/request

LLM-as-Judge 四個偏差：
  自我偏愛 / 位置偏差 / 冗長偏差 / 隨機性
  緩解：跨廠商 + 互換位置 + 多次評估取平均

Eval Pipeline：測試集 → Agent Run → Auto Metrics + LLM Judge
              → Aggregation → Regression Detection
```

---

**系列導覽：**  
← [（十一）RKK 實戰：Agent 線上除錯與故障排除](../fde-interview-guide-part11-agent-debugging-zh/)  
→ [（十三）RKK 實戰：Prompt Injection 攻防與 Agent 安全](../fde-interview-guide-part13-prompt-injection-zh/)
