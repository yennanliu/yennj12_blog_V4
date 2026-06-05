---
title: "FDE 面試準備指南（三十六）：RKK 實戰——生產級 AI Evaluation Pipeline：從黃金資料集到 CI/CD 品質閘門"
date: 2026-06-05T14:00:00+08:00
draft: false
description: "以 Google FDE 視角完整設計生產級 AI 評估管線：黃金資料集的建立與維護、離線評估架構（RAGAS + Vertex AI Evaluation Service）、CI/CD 品質閘門設計、線上評估的抽樣策略、Safety 評估的獨立維度，以及如何在客戶端建立一個能自動偵測品質退化的系統"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Evaluation", "RAGAS", "Vertex AI", "CI/CD", "Safety", "Pipeline", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "22 min"
---

> 面試官說：「你的 AI 系統上線了。你怎麼知道它今天的回答品質，  
> 比上週沒有退化？」  
> 這個問題，不是問你「你用了哪個 Eval 指標」，  
> 是問你「你建立了什麼系統，讓品質退化在影響用戶之前就被你發現」。  
> 這是 Production Eval Pipeline 的核心問題。

---

## 面試情境

> **面試官：**「客戶是一家法律事務所，他們剛上線了一個合約審查 AI 系統。上線當天品質很好，但他們擔心：以後每次我們更新 Prompt 或換模型版本，品質會不會退化？他們的法務長說，如果 AI 漏掉一個合約風險條款，損失可能是千萬。請設計一個讓客戶可以信任的 Eval Pipeline。」

---

## 一、為什麼需要 Eval Pipeline，而不只是 Eval

```
Eval（評估）和 Eval Pipeline（評估管線）的差別：

  Eval：
    你跑一次評估，拿到一個分數。
    知道「現在的品質是 X」。

  Eval Pipeline：
    每次系統變更（Prompt 更新、模型升級、資料更新）後，
    自動跑評估，自動比較和上一版的差距，
    自動決定「這個變更可以部署」還是「這個變更讓品質退化了，擋住」。

Pipeline 的價值：
  不是靠人記得「要去跑評估」，而是系統自動把關。
  這是從 POC（偶爾手動評估）到 Production（持續自動評估）的核心差距。

  法律場景的代價：
    漏掉一個風險條款 = 可能的千萬損失
    → 你不能靠人工 review 每一個 AI 回答
    → 你需要一個自動化的品質安全網
```

---

## 二、Eval Pipeline 的四層架構

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1：黃金資料集（Ground Truth）                               │
│  建立和維護「正確答案的標準」                                        │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2：離線評估（Offline Eval）                                 │
│  每次部署前，自動跑評估，產出指標報告                                 │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3：CI/CD 品質閘門（Quality Gate）                           │
│  評估分數低於閾值 → 自動擋住部署                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4：線上評估（Online Eval）                                  │
│  生產流量的持續品質監控，偵測 data drift 和 performance drift        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、Layer 1：黃金資料集

這是整個 Pipeline 的基礎，也是最常被忽略的部分。

```
黃金資料集的結構：

  每一筆記錄：
  {
    "id": "Q001",
    "query": "這份合約的違約金條款是否符合台灣民法第 250 條的規定？",
    "context": [附上相關合約段落],
    "reference_answer": "根據民法第 250 條...[正確的法律分析]",
    "metadata": {
      "category": "penalty_clause",
      "difficulty": "hard",
      "created_by": "senior_lawyer_A",
      "created_date": "2026-01-15",
      "last_verified": "2026-05-01"
    }
  }

建立黃金資料集的四個步驟：

  Step 1：選題（覆蓋重要的 query 類型）
    不能只選「AI 答得好的題目」——這會讓評估沒有鑑別力。
    要選：
    ├── 典型題（系統大部分時間要面對的問題）
    ├── 困難題（法規解釋有模糊地帶）
    ├── 邊界題（超出範圍、應該拒絕回答的問題）
    └── 歷史錯誤題（曾經出過問題的 query）

  Step 2：建立參考答案（必須由領域專家做，不能讓 AI 自己生）
    法律場景：由資深律師審核每一個參考答案
    → 這是最貴、最慢的步驟，但也是最重要的
    → 參考答案的品質決定了整個 Eval 系統的上限

  Step 3：版本控制（用 Git 管理黃金資料集）
    → 和代碼一樣，用 git blame 知道誰改了什麼答案
    → 每次更新要有 review 流程

  Step 4：定期更新（法規改變時，參考答案要跟著更新）
    → 建立「法規更新 → 觸發黃金資料集 review」的流程
    → 否則你的 Eval 是在評估「對舊法規的準確率」

資料集規模建議：
  最低起點：50-100 題（能區分系統性問題）
  實用規模：200-500 題（有足夠的統計意義）
  成熟系統：1,000+ 題（分 category 分析）
  
  不要為了有大資料集而降低參考答案品質。
  100 題高品質遠勝 1,000 題低品質。
```

---

## 四、Layer 2：離線評估

### 準確率和相關性評估（RAGAS）

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,         # 答案有沒有幻覺（只說文件裡有的）
    answer_relevancy,     # 答案有沒有回應問題
    context_recall,       # 相關文件有沒有被找到
    context_precision,    # 找到的文件有沒有噪音
)
from ragas.llms import LangchainLLMWrapper
from langchain_google_vertexai import ChatVertexAI

# 使用 Gemini 作為評估的 Judge LLM
judge_llm = LangchainLLMWrapper(
    ChatVertexAI(model_name="gemini-2.0-flash")
)

# 跑評估
results = evaluate(
    dataset=golden_dataset,
    metrics=[faithfulness, answer_relevancy,
             context_recall, context_precision],
    llm=judge_llm,
)

print(results)
# faithfulness: 0.87, answer_relevancy: 0.91,
# context_recall: 0.83, context_precision: 0.79
```

### 安全評估（Safety）——獨立維度

```
Safety 評估和準確率評估是完全獨立的維度。
一個答案可以準確但不安全，也可以安全但不準確。

法律場景的 Safety 評估維度：

  維度 1：越界（Out-of-Scope）
    AI 有沒有回答超出它授權範圍的問題？
    例：「你建議我起訴對方嗎？」
    → 正確：「我只能分析合約條款，不能提供訴訟建議，請諮詢律師。」
    → 違規：「根據情況，你應該考慮起訴...」

  維度 2：確定性偽裝（Fabricated Certainty）
    AI 有沒有對不確定的法律問題給出確定的答案？
    例：「這個條款有效嗎？」（需要法院判決才能確定）
    → 正確：「根據現行法規，這個條款存在被挑戰的風險，建議諮詢律師。」
    → 違規：「這個條款無效。」（沒有依據的確定性）

  維度 3：敏感資訊洩漏
    AI 有沒有在回答中引用了不應該出現的其他客戶資料？

Safety 的評估方式：
  不能只用 LLM-as-judge（Safety 的判斷標準需要明確規則）
  建議：
  ├── 規則式：用 regex / classifier 偵測「確定性語言」（應該 / 一定 / 保證）
  ├── LLM Judge：用另一個 LLM 評估是否越界（附上明確的評估 rubric）
  └── 人工抽查：對 Safety 相關的 query，每週人工 review 樣本

Safety 評估的閾值通常比準確率更嚴格：
  準確率 Faithfulness < 0.80 → warn
  Safety 越界 > 0% → block（任何比例的越界都是問題）
```

### Vertex AI Evaluation Service

```python
# 使用 Vertex AI 內建評估服務（不需要自己管 Judge LLM）

from vertexai.preview.evaluation import EvalTask, MetricPromptTemplateExamples

eval_task = EvalTask(
    dataset=eval_dataset,          # 你的黃金資料集
    metrics=[
        "fluency",
        "coherence",
        "groundedness",            # 等同 Faithfulness
        "question_answering_quality",
    ],
    experiment="legal-contract-review",
    experiment_run_name=f"v{version}-{date}",
)

eval_result = eval_task.evaluate(
    model="gemini-2.0-flash",
    prompt_template=your_prompt_template,
)

# 結果自動存入 Vertex AI Experiments，可以跨版本比較
```

---

## 五、Layer 3：CI/CD 品質閘門

```
這是讓評估真正有力量的部分：
不只是「看分數」，而是「分數不夠就不能上線」。

CI/CD 整合流程（以 GitHub Actions 為例）：

  name: AI Quality Gate

  on:
    pull_request:
      paths:
        - 'prompts/**'      # Prompt 變更觸發評估
        - 'agents/**'       # Agent 代碼變更觸發評估
        - 'config/**'       # 配置變更觸發評估

  jobs:
    eval:
      steps:
        - name: Run Offline Eval
          run: python scripts/run_eval.py --version $PR_VERSION

        - name: Compare with baseline
          run: python scripts/compare_eval.py
               --current $PR_VERSION
               --baseline main

        - name: Quality Gate Check
          run: python scripts/quality_gate.py

品質閘門的閾值設計：

  指標                      閾值               行動
  ─────────────────────────────────────────────────────────
  Faithfulness              >= 0.85            低於 → Block
  Answer Relevancy          >= 0.88            低於 → Block
  Context Recall            >= 0.80            低於 → Warn
  Safety Out-of-Scope Rate  == 0.00            > 0 → Block
  Avg Latency (P95)         <= 5000ms          超過 → Warn
  Regression vs baseline    delta <= -0.05     超過 → Block

  # quality_gate.py 的核心邏輯
  def check_quality_gate(current_metrics, baseline_metrics, thresholds):
      failures = []

      # 絕對閾值檢查
      if current_metrics["faithfulness"] < thresholds["faithfulness_min"]:
          failures.append(f"Faithfulness {current_metrics['faithfulness']:.2f}"
                          f" < {thresholds['faithfulness_min']}")

      # 退化檢查（相對 baseline）
      regression = (baseline_metrics["faithfulness"]
                    - current_metrics["faithfulness"])
      if regression > thresholds["max_regression"]:
          failures.append(f"Faithfulness regression: -{regression:.2f}")

      if failures:
          print("❌ Quality Gate FAILED:")
          for f in failures:
              print(f"  - {f}")
          sys.exit(1)  # 讓 CI 失敗，擋住部署
      else:
          print("✅ Quality Gate PASSED")

重要設計原則：
  閾值要由業務決策而不是工程決策：
  「Faithfulness 0.85 夠不夠？」
  法律場景：不夠，要 0.95。
  客服 FAQ：可能夠，取決於風險承受度。
  FDE 的工作是幫客戶把「業務風險容忍度」轉換成「數字閾值」。
```

---

## 六、Layer 4：線上評估（Online Eval）

```
線上評估解決的問題：
  「黃金資料集是靜態的，但生產流量是動態的。
   如果用戶開始問以前沒見過的問題類型，你怎麼知道系統還表現得好？」

線上評估的三種策略：

策略 1：影子評分（Shadow Scoring）
  每個生產回答，在背景異步跑一個輕量評估：
  ├── Faithfulness：回答有沒有幻覺（用 LLM Judge）
  ├── Relevance：回答有沒有回應問題（用 embedding similarity）
  └── Off-topic：回答有沒有越界（用 classifier）
  
  成本控制：不是每個請求都評，用 1-5% 抽樣

策略 2：用戶信號（Implicit Feedback）
  ├── Thumbs up / down（明確反饋）
  ├── 用戶在 AI 回答後有沒有繼續追問（隱式「不滿意」信號）
  ├── 用戶有沒有要求「重新回答」（隱式「不夠好」信號）
  └── 用戶有沒有轉到人工客服（隱式「AI 無法解決」信號）
  
  這些信號不需要額外工程成本，但需要在 UI 層收集

策略 3：定期人工抽查（Human-in-the-loop Labeling）
  每週從生產流量中隨機抽 50-100 筆，
  由領域專家評分，結果加入黃金資料集（持續擴充）
  → 這是唯一能偵測「系統輸出看起來流暢但法律上是錯的」的方法

線上評估的 Alert 設計：
  指標                      Alert 條件
  ───────────────────────────────────────────────
  Shadow Faithfulness 7日MA  < 0.82 → Slack Alert
  Thumbs Down Rate 日均      > 10% → Slack Alert
  Human-to-AI Escalation Rate > 20% → PagerDuty
  Off-topic Rate（classifier） > 2% → PagerDuty
```

---

## 七、面試官地雷題

**地雷 1：「你說用 LLM 來評估 LLM 的回答（LLM-as-Judge），
這不會有偏見嗎？」**

```
答：這是很合理的顧慮，有三個緩解策略：
    
    1. 用比被評估模型更強的 Judge（例如：被評估模型是 Gemini Flash，
       Judge 用 Gemini Pro）
    
    2. 用明確的評估 rubric，而不是讓 Judge 自由發揮：
       不說「評估這個答案是否準確」，
       說「根據以下文件，找出答案中任何一個不在文件中出現的事實聲明，
           有則輸出 NOT FAITHFUL，否則輸出 FAITHFUL」
    
    3. Safety 類的評估不依賴 LLM Judge，改用規則式或分類模型：
       「有沒有越界」不應該由 LLM 決定，
       LLM 可能因為 prompt 措辭而給出不一致的判斷。
    
    完全避免 LLM-as-Judge 是不現實的，
    但不能把所有評估都交給它，
    要根據評估維度選擇最合適的評估方法。
```

**地雷 2：「CI/CD 品質閘門如果太嚴，會不會讓每次 Prompt 更新
都很難通過，讓工程師不敢改東西？」**

```
答：是的，這是實際會發生的問題，有幾個設計原則：

    1. 分層閾值：
       Hard Block（Faithfulness 大幅退化 > 5%）→ 一定擋
       Soft Warn（輕微退化 1-3%）→ 提醒但不擋，需要人工確認
       這樣避免每個小更新都觸發 Block

    2. 閾值要根據變更範圍調整：
       改了 System Prompt → 跑完整 Eval
       只改了 UI 文字 → 不觸發 Eval（用 path filter 控制）

    3. 讓工程師看到「改善了什麼」，不只看「有沒有通過」：
       CI 報告要顯示：「這次 PR 讓 Faithfulness 從 0.83 → 0.87，
       Answer Relevancy 從 0.90 → 0.88（輕微退化）。」
       看到具體的變化，比看到「PASS / FAIL」更有指導意義。

    4. Eval Dataset 要夠有代表性：
       如果黃金資料集只有 20 題，一個不相關的隨機波動就能讓 Eval 失敗。
       資料集夠大，評估結果才有統計意義。
```

**地雷 3：「客戶問：我的 AI 系統的準確率是多少？你給他一個數字。」**

```
答：這個問題的正確回答不是一個數字，是一個框架：

    「準確率取決於你問的是什麼類型的問題，以及你的評估標準是什麼。
     我們目前的評估結果是：
     對於標準合約條款分析（佔 70% 的用量），Faithfulness 是 0.91。
     對於涉及多個法規交叉的複雜問題（佔 30%），Faithfulness 是 0.79。
     Safety 指標：越界率為 0%（系統正確拒絕了所有超範圍問題）。」

    給一個「整體準確率 X%」是危險的——
    它掩蓋了不同類型問題之間的差距，
    而且讓客戶對一個數字產生不切實際的期待。

    FDE 的工作是讓客戶理解 AI 的能力邊界，
    而不是讓他們覺得系統「應該 100% 正確」。
```

---

## 八、面試回答完整示範

```
面試官問：「設計一個讓法律客戶可以信任的 Eval Pipeline。」

框架先行（30 秒）：
「我的設計有四層：
 黃金資料集建立品質標準，
 離線評估在每次部署前自動把關，
 CI/CD 品質閘門把低品質的變更擋住，
 線上評估監控生產流量的持續品質。
 對法律場景，我特別把 Safety 評估作為獨立維度，
 因為法律建議的越界風險不亞於準確率問題。」

黃金資料集（1 分鐘）：
「由資深律師建立 200 題的黃金資料集，
 覆蓋四個類型：典型題、困難題、邊界題、歷史錯誤題。
 用 Git 管理，法規更新時觸發 review 流程。」

離線評估和品質閘門（1 分鐘）：
「每次 Prompt 或模型版本更新觸發 CI 評估，
 用 RAGAS 跑 Faithfulness、Answer Relevancy、Context Recall，
 同時用規則式分類器評估 Safety 越界率。
 Faithfulness < 0.90 或任何 Safety 越界 → Block 部署。
 我把 0.90 而不是 0.85 作為法律場景的閾值，
 因為這個客戶的錯誤代價是千萬級的。」

線上評估（30 秒）：
「生產環境每天對 3% 的流量做影子評分，
 每週人工抽查 50 筆，結果加入黃金資料集。
 Shadow Faithfulness 7 日移動平均低於 0.85 → Slack Alert。
 人工轉接率超過 20% → PagerDuty。」
```

---

**Eval Pipeline 不是「有就好」，而是「Pipeline 的設計決定了你能相信什麼」。**  
**閾值、資料集品質、自動化的層次——每個決策都在回答：你願意為什麼類型的錯誤負責。**
