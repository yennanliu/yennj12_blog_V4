---
title: "Auto Agent System - Part 2 - Harness 引擎:多模型容錯、自我修正與 LLM 評審"
date: 2026-07-04T10:00:00+08:00
draft: false
description: "深入 agent_auto_system 的心臟——Harness 引擎。從第一個 PR「解析被 markdown 包住的 JSON」開始,一路講到跨模型 fallback 重試(PR #3)、驗證失敗後的自我修正、獨立 LLM 評審打分,以及每次執行的 token/成本追蹤。這是把 LLM 這匹野馬套上挽具的完整工程。"
categories: ["engineering", "ai", "all"]
tags: ["CrewAI", "LLM", "Harness", "Reliability", "Retry", "LLM-as-Judge", "AI Engineering", "Fallback"]
authors: ["yen"]
readTime: "22 min"
---

> Demo 版的 AI:`json.loads(resp.content)`——今天能跑。
> 上線版的 AI:模型回了 ```` ```json {...} ``` ````、或回 429、或一本正經編造欄位——明天就炸。
> 差別不在模型多強,而在你有沒有一層「挽具」接住這些意外。
> 這一篇就是拆解 agent_auto_system 的 Harness 引擎——它如何把不可靠的 LLM,變成可預測的服務。

---

Part 1 我們鳥瞰了整個系統,並指出 `executor.py` 和 `harness/` 是心臟。這一篇我們把它剖開,順著這個專案的 merged PR 歷史,看它是如何一步步長出「可靠性」的。

Harness 層有五個元件:

```
src/automation/harness/
├── provider.py         選模型、算 fallback 順序
├── validator.py        每個任務的結果驗證規則
├── evaluator.py        獨立的 LLM 評審,0–100 打分
├── costs.py            token 用量與美元成本估算
└── langfuse_tracer.py  可觀測性(Part 4 深入)
```

我們一個一個看,並穿插它們背後的 PR。

---

## 一、最不起眼卻最致命的第一個坑:被 markdown 包住的 JSON

> 對應 **PR #1**:`fix: parse markdown-fenced JSON from LLM flow output`

任何做過 LLM 結構化輸出的人都遇過這件事。你在 prompt 裡明明白白寫「**只回 JSON**」,結果模型很貼心地回你:

````
```json
{
  "sellers": ["A", "B", "C"]
}
```
````

於是你的 `json.loads()` 直接噴 `JSONDecodeError`——因為字串開頭是 ```` ```json ````,不是 `{`。

這個問題的惡劣之處在於:**它是機率性的**。同一個 prompt,gpt-4o 可能十次有八次乖乖回純 JSON,兩次包上 code fence;換個模型比例又不一樣。你在開發時測十次都正常,上線第 50 次就爆給你看。

這個專案的第一個 PR 就是修這個。核心邏輯是一個容錯的解析器:

```python
def parse_llm_json(text: str):
    text = text.strip()
    # 1. 先剝掉 markdown code fence(```json ... ``` 或 ``` ... ```)
    if text.startswith("```"):
        # 去掉開頭的 ```lang 與結尾的 ```
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    # 2. 有些模型還會在 JSON 前後加幾句廢話,抓第一個 { 到最後一個 }
    #    (略)
    return json.loads(text.strip())
```

看起來很小,但**這是整個 Harness 哲學的縮影**:LLM 的輸出格式是不可靠的,與其祈禱模型每次都乖,不如在解析層做防禦。這個 PR 之後,所有 Flow 的 JSON 輸出都走這條統一的解析路徑,不再各自 `json.loads()`。

**為什麼放在 Harness 而不是每個 Flow 自己處理?**

| | 各 Flow 自己 parse | 統一在 Harness parse |
|---|------------------|-------------------|
| 一致性 | 11 份可能不一致的邏輯 | 一份,改一次全部生效 |
| 測試 | 要測 11 次 | 測 1 次涵蓋所有任務 |
| 新任務 | 又要重寫一遍 | 免費繼承 |

---

## 二、Provider:延後綁定的模型解析

`provider.py` 負責一件事:**把「使用者說的模型」變成「可以用的 LLM」**,而且刻意分兩步。

```
使用者輸入: "gpt4o" / "GPT-4o" / "claude-sonnet" / "gemini-flash"
                    │
                    ▼
   normalize()  ── 純字串處理,不碰網路 ──▶  ("openai", "gpt-4o")
                    │
                    ▼
   resolve()    ── 這步才真的建立 CrewAI LLM 物件 ──▶  <LLM instance>
```

**為什麼分兩步?** 因為「檢查使用者輸入合不合法」不該需要連到 OpenAI。`normalize()` 是純函式、超快、可以在 request 一進來就跑,擋掉打錯字的輸入。真正花錢建立連線的 `resolve()` 延後到 Flow 真的要 kickoff 的前一刻。

這也讓下一節的 fallback 成為可能——因為 provider 知道「同一家供應商底下有哪些 sibling 模型」。

---

## 三、跨模型 Fallback:LLM 掛掉時自動換一台重試

> 對應 **PR #3**:`feat: retry + same-provider model fallback on transient LLM outages`

這是整個 Harness 最精彩的一段。

**問題場景**:你半夜跑一個 pipeline,OpenAI 剛好在做 rolling deploy,gpt-4o 回你一連串 503。你的任務就這樣失敗了——不是因為你的邏輯錯,而是因為對方在打噴嚏。

這個 PR 引入了**兩層、正交的重試機制**,搞清楚它們的分工很重要:

```
                  ┌─────────────────────────────────────┐
                  │  第一層:Job 層自我修正重試            │
                  │  觸發條件:Validator 說「結果不合格」   │
                  │  做法:把 previous_error 塞回 payload,│
                  │       讓「同一個模型」重跑並改錯       │
                  └─────────────────────────────────────┘
                                    ┃ 正交、獨立
                  ┌─────────────────────────────────────┐
                  │  第二層:跨模型 Fallback 重試(PR #3)  │
                  │  觸發條件:transient 錯誤(503/429/    │
                  │           timeout)——不是結果爛,     │
                  │           是模型「根本沒回」          │
                  │  做法:最多 5 次,換 sibling 模型 +    │
                  │       指數退避                        │
                  └─────────────────────────────────────┘
```

第二層的重試策略長這樣:

```
嘗試 1:  gpt-4o        503 →  等 1s
嘗試 2:  gpt-4o        503 →  等 2s   (先給原模型兩次機會)
嘗試 3:  gpt-4o-mini   ✅         (走 fallback_sequence,換 sibling)
              ↑
        provider.fallback_sequence() 回傳的同供應商模型清單
```

有三個設計細節值得畫重點:

**1. 先重試原模型兩次,再換 sibling。** 因為 transient 錯誤常常是一瞬間的抖動,原模型下一秒可能就好了。硬要換模型反而可能得到品質不一致的結果。所以策略是「先原地重試,不行才換」。

**2. 指數退避(exponential backoff)。** 等待時間 1s → 2s → 4s… 遞增。如果對方真的在過載,連續猛打只會火上加油;拉開間隔給它喘息。

**3. 只有 transient 錯誤才觸發 fallback。** 這是最關鍵的判斷:

```python
if is_transient(err):        # 503 / 429 / timeout → 值得重試
    retry_with_backoff()
else:                        # 400 / 401 / prompt 太長 → 立刻 raise
    raise
```

**為什麼硬錯誤要立刻 raise 而不重試?** 因為 401(金鑰錯)、400(參數錯)、context 超長——這些**重試一百次也是一樣的結果**,只是白白燒錢燒時間。分辨「值得重試」與「重試也沒用」的能力,是可靠性工程的核心。

### 為什麼是「同供應商」的 sibling,而不是跨供應商?

這是一個刻意的取捨:

```
選擇                  這樣做的理由                   不這樣做的理由
────────────────────────────────────────────────────────────────
同供應商 sibling      認證/計費/SDK 都一樣,          跨供應商:要另一把金鑰、
(gpt-4o→gpt-4o-mini) 換模型幾乎零成本                 計費模型不同、輸出風格
                     transient 通常是模型層級         差異大,難保證一致性
                     不是帳號層級,換 sibling 就繞過
```

**什麼時候該改成跨供應商 fallback?** 當你的 SLA 要求「就算整個 OpenAI 掛了也要能跑」時。那時你會願意付出「維護多家金鑰 + 接受輸出風格差異」的代價,換取更高的可用性。這個專案目前的規模,同供應商 fallback 已經足夠——這就是「先解決 80% 的問題」的務實。

---

## 四、Validator + 自我修正:讓 LLM 自己改自己的錯

`validator.py` 為每一種任務定義「什麼叫成功」。這些規則是**確定性的、非 LLM 的**檢查:

```
任務                驗證規則(舉例)
──────────────────────────────────────────────
shopee_seller       回傳的賣家數 ≥ 使用者要求的數量?
                    每筆有 name 欄位嗎?
web_scraper         摘要長度 > 某個下限?不是空字串?
profit_health       四個 agent 都有產出?PDF 檔真的生成了?
```

當驗證失敗,就觸發第一層重試——但重點是**它不是傻傻地重跑**,而是把錯誤資訊餵回去:

```
第一次執行  →  結果:只回了 30 筆,但使用者要 100 筆
                    │
                    ▼  Validator: FAIL "only got 30, need 100"
                    │
第二次執行  →  payload 裡多了:
              previous_error = "上次只回 30 筆,請務必回滿 100 筆,
                                記得翻頁抓更多"
                    │
                    ▼  LLM 看到自己上次的錯,這次改正
```

這個模式叫 **self-correction(自我修正)**。它的威力在於:LLM 其實很會改錯,只要你**明確告訴它上次錯在哪**。與其寫一堆 if-else 去修補輸出,不如把錯誤描述清楚、讓模型自己修——這往往更 robust,也更能處理你沒預期到的失敗模式。

```
   確定性驗證 (Validator)   ──╮
                              ├──▶  這是「品質」的防線
   機率性修正 (LLM 自我修正) ──╯     驗證抓錯 → 修正補救
```

注意它和第三節的 fallback 是**互補**的:fallback 處理「模型沒回」(基礎設施問題),self-correction 處理「模型回了但不合格」(品質問題)。兩者加起來,才是完整的可靠性。

---

## 五、Evaluator:一個獨立的 LLM 評審幫你打分

驗證通過 ≠ 品質好。一個賣家清單可能格式完全正確(通過 Validator),但內容根本是模型瞎編的。怎麼辦?

`evaluator.py` 的答案是 **LLM-as-Judge**:用**另一個獨立的模型**,當裁判,幫這次輸出打 0–100 分。

```
        任務結果
           │
           ▼
   ┌──────────────────┐
   │  Evaluator        │  「這份輸出品質如何?
   │  (獨立評審模型)   │   完整性、相關性、正確性?」
   │                   │   → 分數 0–100 + 信心值
   └──────────────────┘
           │
           ├─ 有 LLM 可用  →  請評審模型打分
           └─ 沒有 LLM     →  fallback 到啟發式規則(長度、欄位齊全度…)
```

幾個關鍵設計:

**1. 評審模型是「獨立」且「可由 admin 設定」的。** 你可以讓 gpt-4o 做任務、讓 gemini 當裁判。用同一個模型自評,容易有「自我感覺良好」的偏誤;換一個模型當裁判更公正。這個「評審模型」在 admin 後台可以單獨選(Part 1 提過)。

**2. 有 fallback 到啟發式。** 如果一時沒有 LLM 可用(例如金鑰沒設),評審不會直接掛掉,而是退化成「規則式評分」——看內容長度、欄位齊不齊等等。**永遠有個保底,不讓評審本身變成單點故障。**

**3. 分數會被記錄下來、也會進 Langfuse trace。** 這讓你可以回頭問:「上禮拜哪些任務的品質分數掉下來了?」——這正是 Part 4 可觀測性的價值。

### 為什麼要多花一次 LLM 呼叫來評分?

```
選擇              評分的理由                      不評分的代價
──────────────────────────────────────────────────────────
加一個 Evaluator  能量化品質、能追蹤退化、         多一次 LLM 成本
                  能在品質太差時觸發重試            (但相對任務本身很小)
                  能事後做品質分析
不評分            省一次呼叫                       完全不知道輸出好不好
                                                  只能等使用者抱怨
```

對一個「多人用的自動化平台」來說,「不知道輸出品質」是不可接受的——你需要一個客觀信號來監控。這一次額外的呼叫,買到的是「品質可觀測性」。

---

## 六、Costs:每一次執行都知道花了多少錢

`costs.py` 追蹤每次 run 的:

- **token 用量**(prompt + completion)
- **估算美元成本**(依模型單價換算)
- 搭配 executor 記錄的**重試次數**與**評分**

```
一次 Run 的完整帳單
──────────────────────────────
model         gpt-4o
prompt tokens 3,240
output tokens 1,850
est. cost     $0.034
retries       1
eval score    82 / 100
status        success
```

這些數字會 aggregate 到 `/api/stats`,讓你在後台看到「這個月各任務總共花了多少錢、平均品質分數多少、重試率多高」。

**為什麼成本追蹤要放在 Harness 而不是各任務?** 同樣的道理:token 用量、模型單價這些是**基礎設施關注點**,和「這個任務要做什麼」無關。executor 是所有 LLM 呼叫的必經漏斗,它天然就知道用了哪個模型、多少 token——在這裡記帳最自然,也保證 11 種任務的計費口徑完全一致。

---

## 七、把五個元件串起來:Executor 的一次完整編排

現在回頭看 `executor.py`,它就是把上面五個元件編織起來的指揮中心:

```
executor.run(job):
   ①  provider.normalize()      解析 provider/model(不碰網路)
   ②  loop 最多 5 次:            ← 跨模型 fallback(§三)
        │  provider.resolve()    建立這次要用的 LLM
        │  flow.kickoff()        跑 CrewAI 流程
        │  parse_llm_json()      容錯解析輸出(§一)
        │  ├─ transient error?  → backoff、換 sibling、continue
        │  └─ ok ↓
        ▼
   ③  validator.check()          結果合格嗎?
        ├─ FAIL → 注入 previous_error,回到 ② 重跑(§四)
        └─ PASS ↓
        ▼
   ④  evaluator.score()          獨立評審打 0–100(§五)
        ▼
   ⑤  costs.record()             記 token / 成本 / 重試 / 分數(§六)
        ▼
   ⑥  langfuse.trace()           (可選)發一條 trace
        ▼
      回傳結果 + 完整 harness 指標
```

整個業務邏輯(Flow / Crew)在第 ② 步的 `flow.kickoff()` 裡——它**完全不知道**外面有重試、有 fallback、有評審、有記帳。這就是「關注點分離」最漂亮的樣子:**任務只管做事,可靠性由 Harness 包辦**。

---

## 八、系統效應:加了 Harness 之後,到底改變了什麼

| 面向 | 沒有 Harness | 有 Harness |
|------|-------------|-----------|
| LLM 回 markdown JSON | 隨機 crash | 統一容錯解析,免疫 |
| 供應商 503/429 | 任務直接失敗 | 自動換 sibling 重試,多半救回 |
| 結果格式不合格 | 回一坨爛資料給使用者 | 帶著錯誤訊息自我修正 |
| 輸出品質 | 完全未知 | 0–100 分數,可追蹤 |
| 成本 | 月底看帳單才知道 | 每次 run 即時記錄、可 aggregate |
| 新增任務 | 上述全部重寫一遍 | 免費繼承整套可靠性 |

最後這一列是重點:**當你把可靠性抽成一層,每個新任務都自動獲得它**。Part 3 我們會看到三個新任務(Shopee、Google Maps 名單、Tasker 投標)——它們的作者不需要碰任何重試/評分邏輯,只要專心把「業務」寫對,Harness 會接住其餘的一切。

---

## 九、給工程師的一段話

如果你正在把一個 AI Demo 推向生產,這一篇最值得帶走的三件事:

1. **LLM 的輸出格式與可用性,預設就是不可靠的。** 在解析層與呼叫層做防禦(容錯 parse、transient 重試),不要祈禱模型每次都乖。
2. **分辨「值得重試」與「重試也沒用」。** transient(503/429/timeout)重試、hard error(4xx)立刻放棄。這條線劃錯,不是白燒錢就是把該救的任務放生。
3. **品質要有客觀信號。** 「跑完了」不等於「跑對了」。一個獨立的評審模型,讓你能量化、追蹤、告警品質退化——而不是等使用者來罵。

---

### 系列導覽

- Part 1:系統總覽、架構、資料流
- **Part 2(本篇)**:Harness 引擎——多模型容錯、自我修正、LLM 評審、成本追蹤
- Part 3:自動化任務實戰——Shopee、Google Maps、Tasker
- Part 4:生產化之路——Langfuse、Docker、AWS、權限
- Part 5:前端體驗與 Pipeline 編排

> 對應的 PR:[#1 markdown JSON parse](https://github.com/yennanliu/agent_auto_system/pull/1)、[#3 retry + fallback](https://github.com/yennanliu/agent_auto_system/pull/3)
> 專案原始碼:[github.com/yennanliu/agent_auto_system](https://github.com/yennanliu/agent_auto_system)
