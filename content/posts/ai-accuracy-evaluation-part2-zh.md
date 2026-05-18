---
title: "如何衡量 AI 的準確度（二）：大型語言模型（LLM）的評估方法"
date: 2026-05-18T10:00:00+08:00
draft: false
description: "LLM 的輸出沒有唯一標準答案，該怎麼客觀評估？本文介紹 BLEU、ROUGE、Perplexity、BERTScore 及 LLM-as-a-Judge 等方法，幫助你從多個維度評估語言模型的真實能力。"
categories: ["AI", "Engineering", "all"]
tags: ["AI", "LLM", "NLP", "BLEU", "ROUGE", "BERTScore", "LLM-as-a-Judge", "Evaluation", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "15 min"
---

## 前言：文字回答沒有「標準答案」

在[第一篇文章](/posts/ai-accuracy-evaluation-part1-zh/)中，我們討論了分類與回歸任務的評估——這些任務都有明確的真值（ground truth）可以比對。

但大型語言模型（LLM）面對的是一個根本不同的問題：

> 「請幫我摘要這篇報告。」

這個問題沒有唯一的正確答案。一個好的摘要可以有很多種寫法，每種都合理。那我們怎麼知道模型給出的摘要是「好」還是「差」的？

這正是 LLM 評估最困難的地方，也是這個領域近幾年最活躍的研究方向之一。

本文將介紹四種主要的評估方法：

1. **字面重疊指標**：BLEU、ROUGE
2. **困惑度**：Perplexity
3. **語意相似度**：BERTScore
4. **以 AI 評估 AI**：LLM-as-a-Judge

---

## 一、字面重疊指標：BLEU 與 ROUGE

這是最早用於評估文字生成品質的方法，核心思路是：**把 AI 的輸出與人類寫的「參考答案」做字詞重疊比較**。

### BLEU（Bilingual Evaluation Understudy）

BLEU 最早設計用於機器翻譯評估，衡量模型輸出的 n-gram（連續 n 個字的片段）有多大比例出現在參考答案中。

**計算邏輯（簡化版）**：

```
模型輸出：The cat is sitting on the mat.
參考答案：The cat sat on the mat.

1-gram 重疊：The, cat, on, the, mat → 5/7 ≈ 71%
2-gram 重疊：The cat, on the, the mat → 3/6 = 50%
```

BLEU 分數是多個 n-gram precision 的幾何平均，加上一個「簡短懲罰」（防止模型生成很短但精確率高的回答）。

**BLEU 的優點**：
- 計算快速，可自動化大規模評估
- 在機器翻譯任務上與人類判斷有一定相關性

**BLEU 的局限**：
- 只看字面，不懂語意（「車輛」和「汽車」意思相同但 BLEU 不認識）
- 需要高品質的人工參考答案
- 對於開放式生成任務（如聊天、創意寫作）相關性很差

### ROUGE（Recall-Oriented Understudy for Gisting Evaluation）

ROUGE 常用於**摘要任務**，與 BLEU 相反，它更偏重召回率（參考答案中有多少 n-gram 出現在模型輸出中）。

常見的變體：

| 變體 | 計算方式 |
|---|---|
| ROUGE-1 | 單字重疊的召回率 |
| ROUGE-2 | 二元字組（bigram）重疊的召回率 |
| ROUGE-L | 最長公共子序列（LCS）的重疊 |

**何時使用 BLEU vs ROUGE？**

```
任務類型            建議指標
──────────────────────────────────────
機器翻譯            → BLEU（精確率導向）
文件摘要            → ROUGE-1/2/L（召回率導向）
問答（封閉型）      → ROUGE-L（序列匹配）
```

### 字面重疊指標的根本問題

無論是 BLEU 還是 ROUGE，它們都有一個共同的根本缺陷：**只比對字面，不理解語意**。

```
參考答案：這部電影非常精彩，強烈推薦。
模型輸出 A：這部影片相當出色，值得一看。  ← 語意接近，但 BLEU 分數低
模型輸出 B：精彩推薦電影這部非常。        ← 字詞大量重疊，但語句錯誤，BLEU 分數高
```

這正是為什麼我們需要更進階的方法。

---

## 二、困惑度（Perplexity）

困惑度衡量的是模型對文字的「不確定性」——直觀理解就是：**模型在預測下一個字時，平均有幾個字需要考慮？**

$$\text{Perplexity} = \exp\left(-\frac{1}{N}\sum_{i=1}^{N}\log P(w_i | w_1, ..., w_{i-1})\right)$$

- **Perplexity = 10**：模型每次預測下一個字時，平均在約 10 個候選詞之間猶豫。
- **Perplexity = 1**：模型完全確定下一個字是什麼（完美預測）。
- **Perplexity 越低**：模型對語言的掌握越穩定、越確定。

### Perplexity 的使用場景

**模型比較**：在相同測試集上，Perplexity 較低的模型通常表現更好。

```python
# 使用 HuggingFace 計算 Perplexity 的簡化範例
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_name = "gpt2"
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

text = "人工智慧正在改變世界的運作方式。"
inputs = tokenizer(text, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs, labels=inputs["input_ids"])
    loss = outputs.loss
    perplexity = torch.exp(loss)

print(f"Perplexity: {perplexity.item():.2f}")
```

**版本追蹤**：在模型微調（fine-tuning）過程中，監控 Perplexity 的變化，確保模型沒有出現退化。

### Perplexity 的局限

Perplexity 只衡量語言流暢性，**不衡量事實正確性**。一個模型可以用非常流暢、自信的語氣，說出完全錯誤的事情——Perplexity 照樣可以很低。

---

## 三、語意相似度：BERTScore

BERTScore 是 2019 年由 Zhang et al. 提出的方法，它解決了字面重疊指標的核心問題：**用向量（Embedding）計算語意相似度，而不是字詞表面的匹配**。

### 計算原理

1. 把模型輸出和參考答案分別送入預訓練的 BERT 模型，得到每個字的向量表示。
2. 計算輸出中每個字與參考答案中所有字的餘弦相似度，取最大值。
3. 對所有字的最大相似度取加權平均，分別計算 Precision、Recall、F1。

```
模型輸出：這部影片相當出色，值得一看。
參考答案：這部電影非常精彩，強烈推薦。

BERTScore 會識別出：
  「影片」≈「電影」（語意相似）
  「出色」≈「精彩」（語意相似）
  「值得一看」≈「強烈推薦」（語意接近）
→ 給出較高分數
```

### 實際使用範例

```python
from bert_score import score

candidates = ["這部影片相當出色，值得一看。"]
references = ["這部電影非常精彩，強烈推薦。"]

P, R, F1 = score(candidates, references, lang="zh", verbose=True)
print(f"BERTScore F1: {F1.mean():.4f}")
```

### BERTScore 的優點

- **語意感知**：能識別同義詞、近義詞和語意相近的表達
- **無需完全一致**：允許合理的改寫（paraphrase）
- **與人類判斷相關性高**：在多個 NLG（自然語言生成）任務上，與人工評分的相關性優於 BLEU/ROUGE

### BERTScore 的局限

- **計算成本較高**：需要運行 BERT 模型，無法像 BLEU 那樣超快速
- **仍需參考答案**：和 BLEU/ROUGE 一樣，依然需要人工標注的黃金答案
- **語言模型偏差**：如果底層 BERT 模型對某種語言或領域訓練不足，評估品質會下降

---

## 四、LLM-as-a-Judge：用 AI 評估 AI

這是近兩年最受關注的 LLM 評估方法。核心思路是：**讓一個更強大的 LLM（如 GPT-4、Claude）扮演評審，對另一個模型的回答打分**。

### 為什麼需要這個方法？

當任務是開放式的、沒有唯一標準答案時（聊天、創意寫作、複雜推理），字面重疊指標完全失效，BERTScore 也力不從心。而人工評估雖然最準確，但成本極高、速度極慢。

LLM-as-a-Judge 提供了一個折中方案：讓強力模型以結構化的方式評估輸出品質。

### 常見的評估框架

**方式一：絕對打分（Likert Scale）**

```
你是一位嚴格的 AI 評審。請根據以下標準，對下面的回答打 1-5 分：
- 相關性（回答是否切題）
- 事實正確性（回答是否準確）
- 完整性（是否涵蓋了問題的所有關鍵面向）
- 流暢性（語言是否自然清晰）

問題：什麼是 Transformer 架構？
回答：[model_output]

請以 JSON 格式輸出分數和理由。
```

**方式二：成對比較（Pairwise Comparison）**

讓評審模型比較兩個模型的輸出，判斷哪個更好。這通常比絕對打分更可靠，因為相對判斷更容易做到一致。

```python
# 使用 OpenAI API 進行 LLM-as-a-Judge 的簡化範例
import openai

def judge_response(question, response_a, response_b):
    prompt = f"""
    你是一位公正的 AI 評審。請比較以下兩個回答，判斷哪個更好。

    問題：{question}
    
    回答 A：{response_a}
    回答 B：{response_b}
    
    請從相關性、準確性、完整性三個維度評估，
    輸出格式：{{"winner": "A" 或 "B" 或 "tie", "reason": "理由"}}
    """
    
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content
```

### 知名的 LLM 評估基準

| 基準 | 評估方式 | 主要衡量面向 |
|---|---|---|
| **MT-Bench** | GPT-4 打分 | 多輪對話品質 |
| **Chatbot Arena** | 人類成對投票 | 整體用戶偏好 |
| **MMLU** | 選擇題準確率 | 知識廣度 |
| **HumanEval** | 程式碼執行正確率 | 程式生成能力 |
| **TruthfulQA** | 事實性檢查 | 減少幻覺能力 |

### LLM-as-a-Judge 的注意事項

使用這個方法時，有幾個常見的陷阱需要避免：

**位置偏見（Position Bias）**：評審模型傾向於認為「先出現的回答」或「較長的回答」更好，與內容無關。
- 解決方案：交換 A/B 的順序重複評估，取平均。

**自我偏好（Self-Preference）**：模型傾向於給自己生成的回答打高分。
- 解決方案：使用與被評估模型不同家族的模型作為評審。

**評分漂移（Score Drift）**：同樣的輸出，在不同對話上下文中評分可能不一致。
- 解決方案：使用詳細的評分標準（rubric），減少主觀判斷空間。

---

## 五、如何組合這些指標？

在實際的 LLM 評估工作中，單一指標通常不夠。推薦的做法是建立一個**多層評估框架**：

```
評估層級              方法               適用場景
────────────────────────────────────────────────────
快速篩選              BLEU / ROUGE        翻譯、摘要的初步比較
語意品質              BERTScore           需要語意感知的生成任務
語言流暢性            Perplexity          模型訓練過程監控
複雜任務品質          LLM-as-a-Judge      聊天、推理、創意任務
最終驗證              人工評估            高風險決策，作為黃金標準
```

### 評估管道範例

```python
def evaluate_llm_output(question, model_output, reference=None):
    results = {}
    
    # 1. 如果有參考答案：計算 ROUGE 和 BERTScore
    if reference:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'])
        results['rouge'] = scorer.score(reference, model_output)
        
        from bert_score import score as bert_score
        P, R, F1 = bert_score([model_output], [reference], lang="zh")
        results['bert_score_f1'] = F1.mean().item()
    
    # 2. 使用 LLM-as-a-Judge 評估（無需參考答案）
    results['llm_judge'] = judge_response_quality(question, model_output)
    
    return results
```

---

## 本文小結

| 方法 | 需要參考答案 | 速度 | 語意理解 | 適用任務 |
|---|---|---|---|---|
| BLEU | ✅ 是 | 快 | ❌ 無 | 翻譯 |
| ROUGE | ✅ 是 | 快 | ❌ 無 | 摘要 |
| Perplexity | ❌ 否 | 中 | ❌ 無 | 語言流暢性監控 |
| BERTScore | ✅ 是 | 慢 | ✅ 有 | 生成任務（語意） |
| LLM-as-a-Judge | ❌ 否 | 中 | ✅ 有 | 開放式任務 |
| 人工評估 | ❌ 否 | 最慢 | ✅ 最高 | 黃金標準驗證 |

LLM 的評估是一個活躍的研究領域，目前沒有任何單一方法可以完美替代人工判斷。最佳實踐是**根據任務特性選擇合適的組合**，並保持定期的人工抽查作為校準基準。

然而，當 LLM 被整合進 RAG（檢索增強生成）系統時，評估的重點又會發生轉移——我們不只是在評估語言品質，更要評估**事實忠誠度**和**資訊可靠性**。

**下一篇（第三篇）**，我們將深入 RAG 系統的評估框架，介紹 Faithfulness、Relevance、Context Precision 等針對 RAG 架構的專屬指標，以及如何使用 RAGAS 等工具自動化評估流程。
