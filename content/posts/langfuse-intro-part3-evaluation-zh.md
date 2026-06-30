---
title: "Langfuse 入門 Part 3 — LLM 評估:Score、LLM-as-a-Judge、Dataset 與 Experiment"
date: 2026-06-30T14:00:00+08:00
draft: false
description: "LLM 應用最難的問題:你怎麼知道它『答得好不好』?本篇拆解 Langfuse 的評估體系——用 Score 量化品質、用 LLM-as-a-Judge 自動評分、用人工標註校準、再用 Dataset + Experiment 在上線前做回歸測試,把『我覺得改好了』變成『數據證明改好了』。"
categories: ["engineering", "ai", "all"]
tags: ["Langfuse", "LLM", "Evaluation", "LLM-as-a-Judge", "Dataset", "Score", "Testing", "LLMOps", "AI Engineering"]
authors: ["yen"]
readTime: "16 min"
---

> 寫傳統程式,你有單元測試:斷言 `add(2,3) == 5`,綠燈就是對。
> 寫 LLM 應用,「正確答案」往往沒有唯一解——同一個問題有一百種好的回答方式。
> 那你怎麼測?怎麼知道改了 prompt 之後是變好還是變壞?這就是 LLM 評估要解的問題,也是 Langfuse 最核心的價值。

---

## 一、為什麼 LLM 評估這麼難

[Part 1](../langfuse-intro-part1-concepts-zh/) 說過,LLM 的「錯」是品質退化而非當機。這帶來一個根本困難:**品質很難測。**

```
   傳統測試                    LLM 評估
   ───────────────            ───────────────
   assert f(x) == 預期值       「這個回答好不好?」
   ✅ 確定、二元、自動          ❓ 主觀、連續、難自動
```

困難來自三點:

1. **沒有唯一正解**:「解釋一下這份財報」可以有無數種好答案。
2. **品質是多維的**:正確性、忠實度(有沒有編造)、完整性、語氣、格式……每個維度都要分開看。
3. **改一處動全身**:調了 prompt 修好了 A 問題,可能默默弄壞了 B 問題——你需要**回歸測試**。

Langfuse 的評估體系,就是把這三個困難逐一拆解。核心是一個概念:**Score(評分)**。

---

## 二、Score:把「好不好」變成一個數字

Part 1 提過,Score 是 Langfuse 評估的基石。它把主觀品質,變成可記錄、可追蹤、可比較的值,附加在 trace 或 observation 上。

最直接的用法是用 SDK 寫入。比如收到使用者按了「👍 / 👎」:

```python
from langfuse import get_client
langfuse = get_client()

# 把使用者回饋寫成一個 score
langfuse.create_score(
    name="user_feedback",
    value=1,                      # 👍=1, 👎=0
    trace_id="trace_id_here",
    data_type="BOOLEAN",
    comment="使用者覺得有幫助",
)
```

或在 trace 執行的當下評分:

```python
@observe()
def handle_request(query: str):
    answer = generate(query)
    # 程式化的確定性檢查也能當 score
    langfuse.score_current_trace(
        name="has_citation",
        value=1 if "[來源]" in answer else 0,
        data_type="BOOLEAN",
    )
    return answer
```

Score 有四種型別,對應不同評估需求:

| 型別 | 適合什麼 | 例子 |
|------|----------|------|
| **Numeric** | 連續品質分數 | faithfulness = 0.92 |
| **Categorical** | 離散分類 | tone = "professional" |
| **Boolean** | 是/否檢查 | contains_pii = false |
| **Text** | 質性評語 | 人工留的文字回饋 |

**重點:Score 的來源有三種**——程式碼/使用者回饋(剛剛示範的)、**LLM-as-a-Judge**(自動)、**人工標註**(校準)。下面分別講。

---

## 三、LLM-as-a-Judge:讓 AI 評 AI

人工評每一個生產回答不可能規模化。**LLM-as-a-Judge** 的核心想法是:用一個 LLM 當「裁判」,去評另一個 LLM 的輸出。

```
   使用者問題 ──▶ 你的 LLM ──▶ 回答
                                  │
                                  ▼
            ┌──────────────────────────────────┐
            │  裁判 LLM(judge)                  │
            │  「這個回答忠於提供的內容嗎?       │
            │    給 0~1 分,並說明理由」          │
            └──────────────┬───────────────────┘
                           ▼
                  Score: faithfulness = 0.85
```

在 Langfuse 裡,你可以**直接在 UI 設定一個 LLM-as-a-Judge evaluator**,讓它自動對「線上的生產 trace」評分,完全不用寫程式:

1. 選一個內建評估模板(faithfulness、relevance、toxicity、hallucination…)或自訂 prompt
2. 設定它要評哪些 trace(全部、或符合某條件的)
3. Langfuse 自動對符合的 trace 跑 judge,把結果寫成 score

這就是 **線上評估(online evaluation)**:在生產環境持續、自動地監測品質。

> 一個務實的提醒:judge 也是 LLM,也會出錯。LLM-as-a-Judge 給的是「趨勢信號」而非「絕對真理」——它最大的價值是**規模化地抓出退化**(faithfulness 突然從 0.9 掉到 0.6),而不是對單一回答下最終裁決。所以才需要下面的人工標註來校準。

---

## 四、人工標註:評估的「真值」校準

再強的自動評估,都需要一把「人類的尺」來校準。Langfuse 的 **Annotation(人工標註)** 讓你在 UI 上:

- 直接對 trace 打分、貼標籤、留文字評語
- 用 **Annotation Queue(標註佇列)** 把待評的 trace 排成一列,讓團隊(或領域專家)有系統地逐一標註

```
   標註的兩個用途
   ─────────────────────────────────────────
   1. 建立「黃金真值」── 校準你的 LLM judge 準不準
   2. 抽樣人工抽查    ── 補自動評估抓不到的細微問題
```

**設計重點:自動評估負責「廣度」(評所有 trace),人工標註負責「深度」(評得準)。** 兩者不是二選一,而是互補——用人工標註的小樣本去驗證 LLM judge 的可信度,再讓 judge 去規模化覆蓋全部。

---

## 五、Dataset + Experiment:上線前的回歸測試

前面講的 Score、Judge、標註,大多作用在「線上、已發生」的 trace。但最關鍵的問題是:**改動上線之前,怎麼知道它不會把事情弄壞?**

這就是 **Dataset(資料集)** 與 **Experiment(實驗)** 的舞台——也就是 **離線評估(offline evaluation)**。

### 第一步:建立 Dataset

Dataset 是一組「輸入 + 期望輸出」的固定測試案例。它的精髓在於**固定**——每次都用同一組案例測,結果才可比較。

```python
from langfuse import get_client
langfuse = get_client()

# 建立資料集
langfuse.create_dataset(
    name="finance-qa",
    description="財報問答的測試案例",
)

# 加入測試案例(可逐筆、CSV 上傳、或從生產 trace 匯入)
langfuse.create_dataset_item(
    dataset_name="finance-qa",
    input={"question": "這家公司的毛利率趨勢如何?"},
    expected_output={"answer": "毛利率連續三季上升,從 38% 到 42%"},
)
```

**最強的來源:從生產問題反向建測試集。** 當線上發現一個爛回答,把它的 input 存進 dataset——它就永遠變成你的回歸測試案例。這正是 Part 1 那個閉環的關鍵一環:**生產發現的問題,變成上線前的防線。**

### 第二步:跑 Experiment

有了 dataset,用 `run_experiment()` 把你的應用對整個資料集跑一遍,並自動評分:

```python
dataset = langfuse.get_dataset("finance-qa")

def my_app(*, item, **kwargs):
    # item.input 是 dataset 裡的輸入
    answer = my_rag_pipeline(item.input["question"])
    return {"output": answer}

result = dataset.run_experiment(
    name="prompt-v3-gpt4o",          # 給這次實驗命名
    task=my_app,
)
```

每次實驗,Langfuse 會把你的應用對每個案例的輸出記下來,並可搭配 evaluator(LLM-as-Judge 或自訂函式)自動評分。

### 第三步:並排比較

這才是重點。你可以跑多次實驗——`prompt-v2` vs `prompt-v3`、`gpt-4o` vs `gemini-2.5-flash`——然後在 Langfuse UI 裡**並排比較它們在同一個 dataset 上的分數**:

```
   Dataset: finance-qa(50 個測試案例)
   ┌──────────────┬───────────┬──────────┬─────────┐
   │ 實驗          │ faithful. │ relevance│ 成本    │
   ├──────────────┼───────────┼──────────┼─────────┤
   │ prompt-v2     │   0.81    │   0.88   │ $0.42   │
   │ prompt-v3     │   0.91 ▲  │   0.87   │ $0.45   │
   │ v3 + gemini   │   0.89    │   0.85   │ $0.08 ▲ │
   └──────────────┴───────────┴──────────┴─────────┘
```

現在「該不該上 prompt-v3」不再是辯論,而是看表:faithfulness 從 0.81 升到 0.91,relevance 沒退,成本只多一點點——上。或者「換成 gemini 省 80% 成本但品質只掉 2%」——這個取捨值不值得,數據攤在眼前。

**Dataset 還會自動版本控制**:每次新增/修改/刪除案例都產生新版本,所以你永遠知道「當時是用哪一版測試集測的」。

---

## 六、線上 vs 離線:兩種評估各司其職

Langfuse 的評估貫穿整個開發循環,但「線上」和「離線」目的不同:

```
   離線評估(Offline)              線上評估(Online)
   ────────────────────           ────────────────────
   時機:上線「之前」               時機:上線「之後」
   對象:固定 Dataset               對象:真實生產 trace
   目的:回歸測試、選型             目的:持續監測品質退化
   工具:Experiment + Judge         工具:LLM-as-Judge + 使用者回饋
        │                                │
        └──── 發現的問題存成 dataset ◀────┘
                  (閉環)
```

兩者形成閉環:**線上抓到的問題,變成離線的測試案例;離線驗證過的改動,才放心推上線。**

---

## 七、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 規模化評品質 | LLM-as-a-Judge | 不選純人工:無法覆蓋海量生產 trace |
| judge 可信度 | 用人工標註校準 | 不選盲信 judge:judge 也是 LLM,會錯 |
| 上線前驗證 | Dataset + Experiment | 不選直接上線觀察:壞了使用者先受害 |
| 測試案例來源 | 從生產問題反向建 | 不選憑空想:真實問題才測得到真實退化 |
| 選模型/prompt | 並排比較分數 | 不選憑感覺:取捨要看 faithful/成本的數字 |

**Flip condition**:案例量很小、領域極專業(如醫療、法律)時,人工標註的「深度」價值大過自動評估的「廣度」,該以人工為主、judge 為輔。

---

## 八、小結

LLM 評估的本質,是把「我覺得」換成「數據顯示」:

1. **Score 是基石**:把主觀品質量化成可比較的值,來源有程式、judge、人工三種。
2. **Judge 管廣度,人工管深度**:LLM-as-a-Judge 規模化評線上 trace,人工標註校準 judge 準不準。
3. **Dataset + Experiment 是上線前的安全網**:用固定測試集並排比較不同版本,把選型與回歸測試變成看表決策。
4. **線上與離線形成閉環**:生產問題回流成測試案例,迭代才會越來越穩。

> 一句話總結:沒有評估的 LLM 迭代,是蒙著眼睛調參;有了 Langfuse 的評估體系,每一次改動都有數據告訴你「是變好還是變壞」。

最後一篇([Part 4](../langfuse-intro-part4-monitoring-prompt-management-zh/))把這一切收進日常營運:用監控儀表板盯成本與延遲、用 Prompt 管理讓改 prompt 不必改程式、不必重新部署。

---

**系列導覽**

- [Part 1 — 核心概念與資料模型](../langfuse-intro-part1-concepts-zh/)
- [Part 2 — SDK 整合與 Tracing 實戰](../langfuse-intro-part2-tracing-sdk-zh/)
- Part 3 — LLM 評估(本篇)
- [Part 4 — 監控與 Prompt 管理](../langfuse-intro-part4-monitoring-prompt-management-zh/)

**參考連結**

- [Langfuse — Evaluation 總覽](https://langfuse.com/docs/evaluation/overview)
- [Langfuse — Datasets 與 Experiments](https://langfuse.com/docs/evaluation/dataset-runs/datasets)
