---
title: "Langfuse 入門 Part 4 — 監控與 Prompt 管理:把實驗成果變成生產循環"
date: 2026-06-30T14:30:00+08:00
draft: false
description: "系列最終篇。把前三篇的追蹤與評估收進日常營運:用監控儀表板盯緊成本、延遲、品質的趨勢與異常;用 Prompt 管理把 prompt 從程式碼裡抽出來做版本控制,讓你改 prompt 不必改程式、不必重新部署——並把整個 LLM 工程循環完整串起來。"
categories: ["engineering", "ai", "all"]
tags: ["Langfuse", "LLM", "Monitoring", "Prompt Management", "Observability", "Analytics", "LLMOps", "AI Engineering"]
authors: ["yen"]
readTime: "15 min"
---

> 很多團隊把 prompt 當成「寫死在程式裡的字串」,改一個字就要改程式、跑 CI、重新部署。
> 也有很多團隊上線後從不看成本,直到月底收到一張嚇人的 API 帳單。
> 這篇講的就是讓 LLM 應用「可營運」的最後兩塊拼圖:看得見的監控,與管得動的 prompt。

---

## 一、從「會用」到「營運得起來」

[Part 2](../langfuse-intro-part2-tracing-sdk-zh/) 讓資料進來、[Part 3](../langfuse-intro-part3-evaluation-zh/) 讓品質可評,這最後一篇處理的是**長期營運**:當你的 LLM 應用每天服務真實使用者,你需要兩件事——

```
   ┌─────────────────────────────────────────────┐
   │  監控(Monitoring)                           │
   │  「現在花多少錢?多慢?品質有沒有退化?」     │
   ├─────────────────────────────────────────────┤
   │  Prompt 管理(Prompt Management)            │
   │  「改 prompt 不必改程式、不必重新部署」       │
   └─────────────────────────────────────────────┘
```

---

## 二、監控:LLM 應用要盯的三個維度

傳統服務盯 error rate、latency、throughput。LLM 應用在這之上,多了一個你絕不能忽略的維度:**成本**。Langfuse 的儀表板原生圍繞三個維度:

```
   ┌──────────┬──────────────────────────────────────┐
   │ 維度      │ 為什麼要盯                            │
   ├──────────┼──────────────────────────────────────┤
   │ 成本 Cost │ token 用量直接換算成 $$;一個爛 prompt│
   │          │ 可能讓成本翻數倍而你毫無感覺          │
   │ 延遲 Lat. │ LLM 呼叫是秒級的;哪一步拖慢、p95 多少│
   │ 品質 Qual.│ 來自 Part 3 的 score 趨勢:有沒有退化 │
   └──────────┴──────────────────────────────────────┘
```

### 成本:LLM 特有的、最容易失控的維度

因為 Langfuse 的 Generation 自動捕捉了每次呼叫的 token 數與 model,它能**自動換算成本**並彙總。你可以看到:

- 整體每日花費趨勢
- 按 model 拆分(gpt-4o 花了多少、gemini 花了多少)
- 按 user 拆分(哪個使用者最燒錢)
- 按 trace 類型拆分(哪種功能最貴)

**一個真實場景**:你發現某功能成本突然翻倍。打開儀表板按 model 拆分 → 發現有人不小心把預設模型從 `gpt-4o-mini` 改成 `gpt-4o`。沒有成本可觀測性,這種事你只會在帳單上發現,而且找不到原因。

### 延遲:找出鏈條裡最慢的那一環

Part 1 那棵 observation 樹,在這裡發揮威力:當整體回應變慢,你打開 trace,**每個 observation 的耗時一目了然**——是檢索慢、rerank 慢、還是 LLM 本身慢?p50/p95/p99 延遲也都能在儀表板追蹤。

### 品質:把 Score 趨勢畫成線

Part 3 累積的 score(faithfulness、relevance、使用者回饋),在儀表板上變成**時間趨勢線**。這是線上評估的回報:

```
   faithfulness 趨勢
    │
   0.9│●──●──●──●        ●──●
      │            ╲    ╱
   0.6│             ●──●          ← 這裡發生了什麼?
      └────────────────────────▶ 時間
                    ▲
              某次 prompt 改動上線後品質掉了
              → 立刻回滾,而不是等使用者抱怨
```

**監控的價值不是「看數字」,而是「在使用者之前發現問題」。** faithfulness 掉了、成本飆了、延遲爆了——你在儀表板上先看到,而不是等客訴。

### 自訂儀表板與告警

Langfuse 支援自訂儀表板(把你最在意的指標組合在一頁),也能依 metadata/tags 切分(用上 [Part 2](../langfuse-intro-part2-tracing-sdk-zh/) 貼的標籤)。配合告警,異常時主動通知。

---

## 三、Prompt 管理:把 prompt 從程式碼裡解放出來

### 問題:prompt 寫死在程式裡的三宗罪

大多數人一開始是這樣寫的:

```python
prompt = f"你是一個{level}影評人,你喜歡{movie}嗎?"   # 寫死在程式裡
```

這會帶來三個痛點:

```
   prompt 寫死的三宗罪
   ──────────────────────────────────────────
   1. 改個字 = 改程式 + 跑 CI + 重新部署(慢)
   2. 沒有版本歷史(改壞了不知道改了什麼)
   3. 非工程師(PM、領域專家)無法調 prompt
```

### 解法:prompt 集中管理、版本控制、與程式碼解耦

Langfuse 的 Prompt Management 把 prompt 抽出來,存在平台上,程式只負責「取用」。

**建立 prompt**(可用 UI 或 SDK),用 `{{變數}}` 標記插值位置:

```python
from langfuse import get_client
langfuse = get_client()

langfuse.create_prompt(
    name="movie-critic",
    type="text",
    prompt="你是一個 {{criticlevel}} 影評人,你喜歡 {{movie}} 嗎?",
    labels=["production"],        # 標記為生產版本
)
```

**程式裡取用**:用 `get_prompt()` 抓回來,`compile()` 把變數填進去:

```python
prompt_obj = langfuse.get_prompt("movie-critic")   # 預設抓 production 標籤的版本

compiled = prompt_obj.compile(criticlevel="資深", movie="沙丘 2")
# → "你是一個 資深 影評人,你喜歡 沙丘 2 嗎?"

# 把它送進 LLM
answer = call_llm(compiled)
```

### 關鍵機制:版本與標籤(Label)

每次用同名建立 prompt,就產生**一個新版本**。而 **Label** 決定「程式實際抓哪一版」:

```
   prompt: movie-critic
   ├─ v1  ────────────── (舊)
   ├─ v2  ── label: production  ◀── 程式抓的是這版
   └─ v3  ── label: latest      ◀── 還在測試的新版
```

這帶來幾個強大的能力:

1. **改 prompt 不必動程式**:在 UI 改好 v3,測過後把 `production` 標籤移到 v3,**程式下次 `get_prompt()` 自動拿到新版,零部署**。
2. **安全回滾**:新版出包?把 `production` 標籤移回 v2,瞬間回滾。
3. **非工程師也能改**:PM、領域專家直接在 UI 調 prompt,不必碰程式碼。
4. **A/B 測試**:用標籤指向不同版本給不同流量。

### 把 prompt 連結到 Generation:閉環的最後一塊

最關鍵的整合:**把取用的 prompt 連結到它產生的 generation**。這樣 Langfuse 就能告訴你「哪一版 prompt 的品質/成本表現最好」——直接呼應 [Part 3](../langfuse-intro-part3-evaluation-zh/) 的評估。

```
   Prompt v2 ──產生──▶ Generations ──評分──▶ faithfulness 0.81
   Prompt v3 ──產生──▶ Generations ──評分──▶ faithfulness 0.91 ▲
                                              │
                          「v3 比較好」有了數據依據
```

於是「改 prompt」不再是憑感覺的文字遊戲,而是**可量測、可比較、可回滾**的工程行為。

---

## 四、完整循環:四篇串成一個飛輪

走完四篇,Langfuse 的全貌就是一個自我強化的飛輪:

```
        ┌──────────────────────────────────────────┐
        │                                            │
        ▼                                            │
   [Part 2] Tracing                                  │
   把每次請求記成 Trace/Observation 樹                │
        │                                            │
        ▼                                            │
   [Part 4] Monitoring                               │
   盯成本/延遲/品質趨勢,在使用者之前發現問題          │
        │                                            │
        ▼                                            │
   [Part 3] Evaluation                               │
   線上 Judge 評分 → 抓到退化 → 存成 Dataset          │
        │                                            │
        ▼                                            │
   [Part 3] Experiment + [Part 4] Prompt Mgmt        │
   改 prompt、跑實驗、並排比較、選出最佳版本           │
        │                                            │
        ▼                                            │
   標籤一移,新版上線(零部署)──────────────────────┘
```

每轉一圈,你的應用就更穩、更便宜、更好。**這就是 LLM 工程(AI Engineering)的本質——不是一次把 prompt 調對,而是建立一個能持續變好的循環。**

---

## 五、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 成本控管 | 原生成本儀表板 | 不選看 API 帳單:帳單太晚、無法歸因 |
| 找慢的環節 | 看 observation 樹耗時 | 不選整體計時:看不出是哪一步慢 |
| prompt 存放 | Langfuse 集中管理 | 不選寫死程式:改字要部署、無版本、PM 碰不到 |
| prompt 上線 | 移動 label | 不選改程式重部署:慢且風險高 |
| prompt 出包 | 標籤回滾 | 不選緊急 hotfix:回滾是秒級的 |
| 選最佳 prompt | 連結 generation 看分數 | 不選憑感覺:要有品質/成本數據 |

**Flip condition**:極簡、prompt 幾乎不變的應用,寫死在程式裡也無妨;但只要 prompt 會反覆迭代、或需要非工程師參與,集中管理的價值就立刻浮現。

---

## 六、系列總結

四篇走下來,我們把 LLM 應用從「黑箱」變成了「可營運的工程系統」:

1. **[Part 1] 概念**:LLM 的錯是品質退化而非當機;核心是 Trace→Observation 樹、Score、Dataset。
2. **[Part 2] 追蹤**:用 `@observe`、context manager、框架整合,幾乎零成本把資料送進來。
3. **[Part 3] 評估**:用 Score 量化、Judge 規模化、人工校準、Dataset 實驗做上線前回歸。
4. **[Part 4] 營運**:用儀表板盯成本/延遲/品質,用 Prompt 管理讓迭代零部署、可回滾。

貫穿全系列的一個信念:**LLM 應用的競爭力,不在於某一次把 prompt 調得多神,而在於你有沒有一個能持續觀測、評估、迭代的循環。** Langfuse 就是把這個循環工具化的開源平台。

> 一句話總結:把 LLM 應用當成「需要持續經營的系統」而非「一次性的 prompt 魔法」——可觀測、可評估、可迭代,才是它真正可靠的開始。

---

**系列導覽**

- [Part 1 — 核心概念與資料模型](../langfuse-intro-part1-concepts-zh/)
- [Part 2 — SDK 整合與 Tracing 實戰](../langfuse-intro-part2-tracing-sdk-zh/)
- [Part 3 — LLM 評估:Score、LLM-as-a-Judge、Dataset](../langfuse-intro-part3-evaluation-zh/)
- Part 4 — 監控與 Prompt 管理(本篇)

**參考連結**

- [Langfuse — Prompt Management](https://langfuse.com/docs/prompt-management/get-started)
- [Langfuse — Custom Scores](https://langfuse.com/docs/scores/custom)
- [Langfuse 官網](https://langfuse.com/)
