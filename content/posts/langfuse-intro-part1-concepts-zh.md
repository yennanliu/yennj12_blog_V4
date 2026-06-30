---
title: "Langfuse 入門 Part 1 — 為什麼 LLM 應用需要可觀測性?核心概念與資料模型"
date: 2026-06-30T13:00:00+08:00
draft: false
description: "LLM 應用最可怕的地方,是它「壞掉時看起來跟正常時一模一樣」。本篇用最白話的方式講清楚:為什麼傳統監控救不了 LLM、Langfuse 是什麼、以及它的核心資料模型——Trace、Observation、Span、Generation、Session、Score——彼此怎麼組合成一張可觀測的全貌。"
categories: ["engineering", "ai", "all"]
tags: ["Langfuse", "LLM", "Observability", "LLMOps", "Tracing", "Evaluation", "Monitoring", "AI Engineering"]
authors: ["yen"]
readTime: "14 min"
---

> 傳統後端壞掉:噴 500、log 一條 stack trace、監控告警響——你馬上知道。
> LLM 應用壞掉:回了一段「看起來很合理但其實是編的」答案,HTTP 200,沒有任何錯誤。
> 你的使用者知道它錯了,但你的系統不知道。這就是為什麼 LLM 需要一種全新的可觀測性。

---

## 一、傳統監控為什麼救不了 LLM 應用

先想一個問題:一個傳統 API 壞掉,你怎麼發現?

```
   傳統後端
   ─────────────────────────────
   輸入 → 確定性邏輯 → 輸出
                │
                ├─ 壞了 → throw Exception → 500 → 告警響
                └─ 對了 → 200
```

錯誤是**二元的、確定的**:不是對就是錯,壞了會噴例外。你的 APM(Datadog、Sentry)抓得到。

但 LLM 應用不是這樣:

```
   LLM 應用
   ─────────────────────────────
   輸入 → Prompt → LLM(機率性) → 輸出
                         │
                         ├─ 幻覺(編造事實)   → HTTP 200 ✅
                         ├─ 答非所問          → HTTP 200 ✅
                         ├─ 語氣不對/拒答      → HTTP 200 ✅
                         └─ 完美回答          → HTTP 200 ✅
```

**所有情況都是 HTTP 200。** 沒有例外、沒有 stack trace、沒有錯誤碼。LLM 的「錯」不是當機,而是**輸出品質的退化**——而品質是連續的、主觀的、機率性的。傳統監控的整套工具(看 error rate、看 5xx)在這裡完全失效。

更麻煩的是,一次使用者請求背後,往往不是一次 LLM 呼叫,而是一整串:

```
   使用者問:「幫我分析這份財報的風險」
        │
        ▼
   1. 改寫查詢(LLM)
   2. 檢索文件(向量搜尋)
   3. 重排序(rerank)
   4. 組 prompt
   5. 生成答案(LLM)
   6. 評估答案(LLM-as-judge)
```

當最終答案爛掉,問題出在哪一步?是檢索撈錯了、prompt 組壞了、還是模型本身的問題?**沒有可觀測性,你只能瞎猜。**

這就是 Langfuse 要解決的問題。

---

## 二、Langfuse 是什麼

[Langfuse](https://langfuse.com/) 是一個**開源的 LLM 工程平台(LLM Engineering Platform)**。一句話定義:它幫團隊**追蹤、除錯、評估、迭代** LLM 應用。

它有四大產品區塊,正好對應 LLM 開發的完整生命週期:

```
┌────────────────────────────────────────────────────────┐
│  1. Observability(可觀測性 / Tracing)                  │
│     記錄每一次 LLM 與非 LLM 呼叫,看清整條執行鏈        │
├────────────────────────────────────────────────────────┤
│  2. Evaluation(評估)                                   │
│     LLM-as-a-Judge、人工標註、Dataset 實驗、Score       │
├────────────────────────────────────────────────────────┤
│  3. Prompt Management(Prompt 管理)                     │
│     版本控制、標籤部署、與程式碼解耦                     │
├────────────────────────────────────────────────────────┤
│  4. Monitoring / Analytics(監控與分析)                 │
│     品質、成本、延遲的儀表板與趨勢                       │
└────────────────────────────────────────────────────────┘
```

幾個關鍵特性,決定了它為什麼值得用:

- **開源 + 可自架(self-host)**:資料敏感的團隊可以完全跑在自己的基礎設施上,不必把 prompt 和使用者資料送到第三方。也有 Langfuse Cloud 免費方案可直接用。
- **建立在 OpenTelemetry 標準上**:降低 vendor lock-in,跟既有的 observability 生態相容。
- **100+ 整合**:OpenAI、Anthropic、LangChain、LlamaIndex、Vercel AI SDK……幾乎所有主流框架都能接。

> 本系列前一篇講過 [chatPDF 如何整合 Langfuse 做追蹤](../chatpdf-rag-optimization-part3-observability-eval-zh/),那是「實際接上去」的視角;這個系列則從零開始,把 Langfuse 本身講清楚。

---

## 三、核心資料模型:理解這六個概念,就懂了 Langfuse

Langfuse 的所有功能,都建立在一個清晰的資料模型上。**搞懂這六個概念,你就懂了 Langfuse 的八成。**

### Trace(追蹤):一次完整請求

**Trace 是最頂層的單位,代表「一次完整的使用者互動」。** 使用者問一個問題、agent 跑完一個任務——那就是一個 trace。它是你 debug 時打開的那個「最外層的盒子」。

### Observation(觀測):trace 裡的每一個步驟

一個 trace 裡有很多步驟,每一步都是一個 **Observation**。Observation 有三種型別:

| 型別 | 代表什麼 | 例子 |
|------|----------|------|
| **Span** | 一段工作單元(非 LLM) | 檢索文件、呼叫 API、資料處理 |
| **Generation** | 一次 LLM 呼叫 | 呼叫 GPT-4o 生成答案 |
| **Event** | 一個時間點事件 | 記錄某個離散事件 |

其中 **Generation 最特別**——它專門記錄 LLM 呼叫,會自動捕捉 model、input/output messages、token 數、成本、延遲。這是 LLM 可觀測性的核心。

### 巢狀結構:Trace → Observation 的樹

Observation 可以**互相巢狀**,形成一棵樹,完美對應你程式的呼叫結構:

```
   Trace: "分析財報風險"  (使用者的一次提問)
   │
   ├─ Span: "改寫查詢"
   │   └─ Generation: LLM 呼叫 (gpt-4o-mini, 120 tokens, $0.0001, 0.3s)
   │
   ├─ Span: "檢索文件"
   │   ├─ Span: "向量搜尋"   (撈回 20 段)
   │   └─ Span: "重排序"     (篩到 5 段)
   │
   └─ Generation: "生成最終答案"
       (gpt-4o, 2,400 tokens, $0.012, 4.2s)
```

打開這個 trace,你**一眼就能看出**:總共花了多少錢、多少時間、哪一步最慢、檢索撈回了什麼、最終 prompt 長什麼樣、模型回了什麼。當答案爛掉時,你不再瞎猜——你直接看樹。

### Session(會話):把多輪對話串起來

聊天機器人是多輪的。**Session 把屬於同一段對話的多個 trace 串在一起**,讓你能回放整段對話脈絡,而不是只看孤立的一問一答。

### Score(評分):品質的量化

**Score 是 Langfuse 評估系統的基石。** 它把「這個回答好不好」這個主觀問題,變成一個可記錄、可追蹤、可比較的數字或標籤。Score 可以附加在 trace 或 observation 上,有四種型別:

- **Numeric(數值)**:如 faithfulness = 0.92
- **Categorical(類別)**:如 sentiment = "positive"
- **Boolean(布林)**:如 contains_pii = false
- **Text(文字)**:如人工留下的開放式評語

Score 從哪來?三個來源:**LLM-as-a-Judge**(自動)、**人工標註**(annotation)、**程式碼/使用者回饋**(API)。這是 Part 3 的主題。

### Dataset(資料集):系統化測試的基準

**Dataset 是一組「輸入 + 期望輸出」的測試案例集合。** 它讓你能在「上線前」用固定的測試集,反覆比較不同 prompt、不同模型、不同程式版本的表現——把「我覺得改好了」變成「數據證明改好了」。這也是 Part 3 的主題。

---

## 四、把六個概念串起來看

這六個概念不是各自獨立的,它們組成一個閉環:

```
   ┌─────────────────────────────────────────────────┐
   │                                                   │
   │   生產環境執行                                     │
   │   每次請求 ──▶ Trace(含巢狀 Observation)         │
   │                  │                                │
   │                  ├─▶ Session 串起多輪對話          │
   │                  │                                │
   │                  └─▶ Score 評分(線上/人工)        │
   │                          │                        │
   │                          ▼                        │
   │   發現問題 ──▶ 把問題案例存成 Dataset 測試案例     │
   │                          │                        │
   │                          ▼                        │
   │   開發迭代 ──▶ 用 Dataset 跑 Experiment 比較      │
   │                          │                        │
   │                          ▼                        │
   │   改好後上線 ──▶ 回到生產環境執行(循環)           │
   │                                                   │
   └─────────────────────────────────────────────────┘
```

這就是 LLM 工程的核心循環:**觀測 → 評估 → 發現問題 → 建測試集 → 迭代 → 再上線**。Langfuse 的價值,是讓這整個循環的每一環都有資料支撐,而不是憑感覺。

---

## 五、一個常見誤解:Langfuse vs 一般的 APM/Logging

| 面向 | 傳統 APM / Logging | Langfuse |
|------|-------------------|----------|
| 關注點 | 錯誤、延遲、吞吐 | 加上**品質、成本、token、prompt** |
| 錯誤模型 | 二元(對/錯) | 連續(品質分數) |
| 資料單位 | log 行、metric | Trace + Observation 樹 |
| LLM 專屬 | 無(不懂 token/model/prompt) | 原生理解 generation |
| 評估 | 無 | LLM-as-Judge、Dataset 實驗 |
| Prompt | 散在程式碼裡 | 集中版本控制 |

**重點不是「Langfuse 取代你的 APM」**——你仍然需要 Datadog 看基礎設施。重點是 LLM 應用多了一整個維度(品質、成本、prompt、評估),那個維度傳統工具看不到,而 Langfuse 專門為它而生。

---

## 六、小結

這篇沒有寫任何程式碼,因為**理解概念比照抄 API 重要得多**。記住三件事:

1. **LLM 的「錯」不是當機,而是品質退化**——HTTP 200 不代表答案是對的,傳統監控看不到這層。
2. **Langfuse 的核心是 Trace → Observation 樹**——它把一次請求背後那串看不見的步驟,變成一棵你打得開、看得懂的樹。
3. **Score 與 Dataset 把「主觀品質」變成「可量化、可比較的循環」**——這是從「憑感覺調」進化到「用數據迭代」的關鍵。

> 一句話總結:Langfuse 做的事,是把 LLM 應用從一個「黑箱」,變成一個「你看得見內部、量得出好壞、改得有依據」的系統。

下一篇([Part 2](../langfuse-intro-part2-tracing-sdk-zh/))進入實戰:用三行程式碼把你的應用接上 Langfuse,看第一個 trace 出現在儀表板上。

---

**系列導覽**

- Part 1 — 核心概念與資料模型(本篇)
- [Part 2 — SDK 整合與 Tracing 實戰](../langfuse-intro-part2-tracing-sdk-zh/)
- [Part 3 — LLM 評估:Score、LLM-as-a-Judge、Dataset](../langfuse-intro-part3-evaluation-zh/)
- [Part 4 — 監控與 Prompt 管理](../langfuse-intro-part4-monitoring-prompt-management-zh/)

**參考連結**

- [Langfuse 官網](https://langfuse.com/)
- [Langfuse Docs](https://langfuse.com/docs)
