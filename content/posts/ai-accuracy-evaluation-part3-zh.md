---
title: "如何衡量 AI 的準確度（三）：RAG 系統的可靠性評估框架"
date: 2026-05-18T11:00:00+08:00
draft: false
weight: 3
description: "RAG 系統的評估遠不只是看回答品質，還要驗證檢索忠誠度與事實接地性。本文介紹 Faithfulness、Relevance、Context Precision 等 RAG 專屬指標，以及如何使用 RAGAS 框架自動化評估流程。"
categories: ["AI", "Engineering", "all"]
tags: ["AI", "RAG", "LLM", "RAGAS", "Faithfulness", "Hallucination", "Evaluation", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "18 min"
---

## 前言：RAG 帶來了新的評估挑戰

在[第一篇](/posts/ai-accuracy-evaluation-part1-zh/)和[第二篇](/posts/ai-accuracy-evaluation-part2-zh/)中，我們分別探討了傳統機器學習任務與 LLM 的評估方法。

現在，許多企業級 AI 應用走向了 **RAG（Retrieval-Augmented Generation）架構**：

```
用戶問題
    ↓
[檢索器] → 從知識庫取出相關文件段落（Context）
    ↓
[LLM] → 根據 Context 生成回答
    ↓
最終答案
```

RAG 的評估比純 LLM 更複雜，因為它有兩個可能出錯的環節：

1. **檢索器**：有沒有找到正確的資料？
2. **生成器（LLM）**：有沒有忠實地根據資料回答，而不是憑空幻想？

本文將系統性地介紹 RAG 的評估框架，包括核心指標、評估工具（RAGAS），以及企業實際落地時的最佳實踐。

---

## 一、RAG 評估的三個核心維度

評估一個 RAG 系統，需要從三個維度同時切入：

```
                    ┌─────────────────┐
                    │   用戶問題 (Q)   │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │         檢索器              │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      檢索到的 Context (C)    │  ← 評估維度 1：檢索品質
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │        LLM 生成             │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │        最終答案 (A)          │  ← 評估維度 2：生成品質
              └─────────────────────────────┘
                             │
                      ← 評估維度 3：端到端品質（Q→A）
```

---

## 二、核心指標詳解

### 2.1 忠誠度（Faithfulness）

**定義**：答案中的每一個聲明（claim），是否都能從提供的 Context 中找到支持？

$$\text{Faithfulness} = \frac{\text{有 Context 支持的聲明數}}{\text{答案中的聲明總數}}$$

**Faithfulness = 1.0** 意味著模型完全根據文件回答，沒有任何「幻覺（Hallucination）」。

**實際範例**：

```
Context：台灣的面積約為 36,000 平方公里，人口約 2,330 萬人。
          2023 年 GDP 約為 7,562 億美元。

問題：台灣的人口和 GDP 是多少？

答案 A（高 Faithfulness）：
  台灣人口約 2,330 萬人，2023 年 GDP 約 7,562 億美元。
  → 所有聲明均來自 Context。Faithfulness = 1.0

答案 B（低 Faithfulness）：
  台灣人口約 2,330 萬人，是亞洲科技業的重要基地，
  半導體產業佔全球市場超過 60%。
  → 後兩個聲明 Context 中沒有，屬於幻覺。Faithfulness ≈ 0.33
```

**為什麼這個指標最重要？**

在企業知識庫問答場景中，幻覺是最危險的問題。一個 Faithfulness 低的系統，等於讓 AI 拿著你的公司文件背書，卻夾雜著它自己編造的內容——在法律、醫療、金融等高風險領域，這可能造成嚴重後果。

### 2.2 答案相關性（Answer Relevance）

**定義**：生成的答案有多切題？是否精確地回應了用戶的問題？

這個指標懲罰兩種情況：
- **不相關的回答**：答非所問
- **不完整的回答**：只回答了部分問題

**計算方式（RAGAS 的方法）**：

用 LLM 根據答案「反推」出幾個問題，然後計算這些反推問題與原始問題的語意相似度。如果答案真的切題，反推出來的問題應該與原始問題非常接近。

```python
# RAGAS 計算 Answer Relevance 的概念
def calculate_answer_relevance(question, answer, llm):
    # 讓 LLM 根據答案反推問題
    reverse_questions = llm.generate(
        f"根據以下答案，生成 3 個最可能的問題：\n{answer}"
    )
    
    # 計算反推問題與原始問題的語意相似度
    similarities = [
        cosine_similarity(embed(q), embed(question))
        for q in reverse_questions
    ]
    
    return sum(similarities) / len(similarities)
```

### 2.3 Context 精確率（Context Precision）

**定義**：檢索器找到的 Context 中，有多大比例是真正有用的（相關的）？

$$\text{Context Precision} = \frac{\text{有用的 Context 段落數}}{\text{檢索到的 Context 段落總數}}$$

**問題情境**：假設你的 RAG 系統每次檢索 5 個段落，但只有 1 個段落真正和問題相關，另外 4 個是「看起來相關但實際無用」的噪音。

Context Precision 就是在衡量這個「信噪比」。精確率低意味著你把太多無關的資訊餵給 LLM，這不只浪費 token，還可能讓模型被噪音干擾，生成不準確的回答。

### 2.4 Context 召回率（Context Recall）

**定義**：要回答這個問題所需的所有資訊，有多大比例被成功檢索到了？

$$\text{Context Recall} = \frac{\text{答案中有 Context 支持的句子數}}{\text{答案的句子總數}}$$

這個指標評估的是檢索器的「完整性」——有沒有漏掉關鍵資訊？

**Context Precision vs Context Recall 的關係**：

和分類任務的 Precision/Recall 一樣，這兩個指標也存在張力：

- **提高 Precision**：只檢索最相關的段落 → 可能漏掉一些必要的背景資訊（Recall 下降）
- **提高 Recall**：廣泛檢索更多段落 → 引入更多噪音（Precision 下降）

如何找到平衡點，是 RAG 系統調優的核心問題之一。

### 2.5 校準分析（Calibration）

**定義**：模型對自己答案的「信心水準」是否與實際的「準確率」一致？

一個理想的 AI 系統應該：
- 當它說「我 90% 確定」的時候，實際上應該有約 90% 的時間是對的
- 當它說「我不太確定」的時候，確實應該更容易出錯

**校準曲線（Calibration Curve）**：

```
完美校準（對角線）:
  │          ╱
  │        ╱
準│      ╱
確│    ╱
率│  ╱
  │╱
  └──────────
    信心水準

過度自信（曲線在對角線下方）:
  │       ─ ─
  │     ─  ╱
  │   ─  ╱
  │  ╱
  │╱
  └──────────
```

**Expected Calibration Error (ECE)**：

$$ECE = \sum_{b=1}^{B}\frac{|B_b|}{n}\left|\text{acc}(B_b) - \text{conf}(B_b)\right|$$

ECE 越低，模型越「自知」——它知道自己什麼時候在說確定的事，什麼時候在猜測。對於企業應用來說，一個過度自信卻頻繁出錯的 AI 系統，比一個承認不確定性的系統危險得多。

---

## 三、RAGAS：RAG 評估的自動化框架

[RAGAS](https://github.com/explodinggradients/ragas) 是目前最流行的 RAG 評估開源框架，它把上述指標整合成一套可以自動化運行的評估管道。

### 快速上手

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

# 準備評估數據集
eval_data = {
    "question": [
        "台積電的主要業務是什麼？",
        "什麼是 HBM 記憶體？"
    ],
    "contexts": [
        [
            "台積電（TSMC）是全球最大的獨立晶圓代工廠，專注於製造高效能半導體晶片，"
            "主要客戶包括 Apple、NVIDIA、AMD 等科技巨頭。"
        ],
        [
            "HBM（High Bandwidth Memory）是一種高頻寬記憶體規格，"
            "通過在晶片上垂直堆疊 DRAM 層來實現極高的記憶體頻寬，"
            "主要用於 AI 加速器和高效能 GPU。"
        ]
    ],
    "answer": [
        "台積電的主要業務是晶圓代工，為其他公司製造半導體晶片，"
        "客戶包括 Apple 和 NVIDIA 等。",
        "HBM 是一種高頻寬記憶體，通過垂直堆疊 DRAM 實現高頻寬，"
        "廣泛用於 AI 和 GPU 應用。"
    ],
    "ground_truth": [
        "台積電是全球最大晶圓代工廠，負責為其他公司製造半導體晶片。",
        "HBM 是高頻寬記憶體，採用垂直堆疊架構，為 AI 加速器提供高速記憶體存取。"
    ]
}

dataset = Dataset.from_dict(eval_data)

# 執行評估
results = evaluate(
    dataset=dataset,
    metrics=[
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ]
)

print(results)
# 輸出範例：
# {'faithfulness': 0.97, 'answer_relevancy': 0.92,
#  'context_precision': 0.88, 'context_recall': 0.91}
```

### 使用自定義 LLM 作為評審

RAGAS 預設使用 OpenAI 的模型作為評審，但你也可以替換成 Claude 或其他模型：

```python
from ragas.llms import LangchainLLMWrapper
from langchain_anthropic import ChatAnthropic

# 使用 Claude 作為評審模型
claude = ChatAnthropic(model="claude-sonnet-4-6")
ragas_llm = LangchainLLMWrapper(claude)

results = evaluate(
    dataset=dataset,
    metrics=[faithfulness, answer_relevancy],
    llm=ragas_llm
)
```

---

## 四、端對端評估：從指標到決策

光有指標數字還不夠，關鍵是把這些數字轉化為實際的系統改善行動。

### 問題診斷矩陣

```
症狀                          可能原因           改善方向
──────────────────────────────────────────────────────────────
Faithfulness 低               LLM 幻覺嚴重       加強 system prompt 約束；
                                                 使用「只根據以下資料回答」指令

Context Precision 低          檢索器噪音多       改善 embedding 模型；
                                                 調整相似度閾值；使用重排序（reranker）

Context Recall 低             檢索器漏掉資訊     增加檢索數量（top-k）；
                                                 改善文件切分策略（chunking）

Answer Relevance 低           答非所問           檢查問題理解；
                                                 改善 prompt 設計；加入問題澄清流程

全部指標都低                  知識庫品質問題     審查文件來源；清理低品質資料
```

### 建立持續評估管道

在生產環境中，RAG 評估不應該只是部署前的一次性工作，而要建立持續監控機制：

```python
import schedule
import time

def daily_rag_evaluation():
    """每日從生產日誌隨機抽樣 100 個查詢，執行評估"""
    
    # 1. 從日誌抽樣
    samples = sample_production_logs(n=100)
    
    # 2. 執行 RAGAS 評估
    dataset = prepare_dataset(samples)
    results = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    
    # 3. 如果指標下降，觸發告警
    if results['faithfulness'] < 0.85:
        send_alert(
            f"⚠️ Faithfulness 下降至 {results['faithfulness']:.2f}，"
            f"低於閾值 0.85，請檢查知識庫更新是否引入問題。"
        )
    
    # 4. 儲存歷史趨勢
    save_metrics_to_db(results)

schedule.every().day.at("02:00").do(daily_rag_evaluation)
```

---

## 五、人工評估：永遠不可省略的最後一關

無論自動化指標多麼完善，**人工評估都應該作為最終驗證手段**，尤其在以下情況：

- 系統即將上線前的 UAT（用戶接受度測試）
- 重大功能變更後的回歸測試
- 發生用戶投訴後的根因分析

### 人工評估標準範本

```markdown
## RAG 回答品質評估表

**問題**：___________
**系統回答**：___________
**相關文件片段**：___________

請針對以下各項，評分 1-5 分（1 = 非常差，5 = 非常好）：

| 評估項目 | 分數 | 備註 |
|---|---|---|
| 事實準確性（回答內容是否正確） | /5 | |
| 忠誠度（有無超出文件範圍的聲明） | /5 | |
| 相關性（是否切題回答了問題） | /5 | |
| 完整性（重要資訊是否都涵蓋了） | /5 | |
| 語言清晰度（回答是否易讀易懂） | /5 | |

**是否存在幻覺？** □ 是（請標出具體片段）/ □ 否

**整體評分**：___/5
**改善建議**：___________
```

---

## 六、完整評估框架總覽

整合三篇文章的內容，以下是一個從傳統 ML 到 RAG 的完整評估框架：

```
AI 系統類型          核心評估指標                    工具/方法
──────────────────────────────────────────────────────────────────
分類模型             Precision / Recall / F1         sklearn.metrics
                     混淆矩陣                        混淆矩陣視覺化

回歸模型             MAE / RMSE / R²                 sklearn.metrics

純 LLM（封閉型）     BLEU / ROUGE                    sacrebleu, rouge-score
純 LLM（開放型）     BERTScore                       bert-score
                     LLM-as-a-Judge                  自建 prompt
                     Perplexity                      HuggingFace

RAG 系統             Faithfulness                    RAGAS
                     Answer Relevance                RAGAS
                     Context Precision               RAGAS
                     Context Recall                  RAGAS
                     Calibration (ECE)               自建評估

所有類型             人工評估（黃金標準）             評估表單 + 人工抽查
```

---

## 系列總結

經過三篇文章，我們從基礎指標出發，逐步深入到 LLM 和 RAG 這兩個當代最重要的 AI 應用場景：

**第一篇** 建立了評估的思維框架：沒有「萬能指標」，只有針對業務問題選擇合適的指標。

**第二篇** 揭示了文字生成評估的複雜性：從字面重疊到語意理解，再到「用 AI 評估 AI」，評估方法在不斷進化。

**第三篇（本文）** 聚焦 RAG 的可靠性：Faithfulness 是企業 AI 的生命線，而 RAGAS 提供了一套可以落地的自動化評估方案。

### 最重要的三個原則

1. **永遠從業務問題反推指標**：不要讓技術指標驅動業務決策，要讓業務需求決定你追蹤什麼指標。

2. **建立多層評估體系**：自動化指標負責速度和規模，人工評估負責深度和最終驗證。兩者缺一不可。

3. **持續監控，而不是一次性測試**：模型在部署後會因為知識庫更新、用戶行為變化等因素退化。評估是一個持續的過程，不是部署前的最後一道關卡。

---

*本系列文章索引：*
- *[第一篇：分類與回歸任務的基礎評估指標](/posts/ai-accuracy-evaluation-part1-zh/)*
- *[第二篇：大型語言模型（LLM）的評估方法](/posts/ai-accuracy-evaluation-part2-zh/)*
- *第三篇（本文）：RAG 系統的可靠性評估框架*
