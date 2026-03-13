---
title: "開源 LLM Post-Training 全攻略：從 SFT 到 RLHF，手把手帶你訓練 Qwen"
date: 2026-03-13T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "Machine Learning", "MLOps", "LLM"]
tags: ["LLM", "post-training", "fine-tuning", "Qwen", "HuggingFace", "SFT", "RLHF", "DPO", "LoRA", "PEFT", "open-source", "AI"]
summary: "全面介紹開源 LLM 的 Post-Training 方法，包含 SFT、RLHF、DPO、ORPO、持續預訓練等技術，以 Qwen 為範例，深入分析各方法的優缺點、所需資源與適用場景，幫助你選擇最合適的訓練策略。"
readTime: "35 min"
---

> **前言：** 隨著 Qwen、LLaMA、Mistral 等高品質開源模型的普及，越來越多工程師開始思考：「如何讓這些模型更符合我的業務需求？」本文將系統性地介紹各種 Post-Training 方法，讓你在選擇技術路線前有完整的全局觀。

---

## 什麼是 Post-Training？

**Post-Training**（後訓練）是指在基礎模型（Base Model）預訓練完成後，透過額外的訓練步驟，使模型具備特定能力或行為的過程。

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LLM 訓練生命週期                                   │
└─────────────────────────────────────────────────────────────────────┘

  Pre-training          Post-Training
  ─────────────         ───────────────────────────────────────
  海量語料               ┌─ SFT（監督式微調）
  自回歸語言建模    →    ├─ RLHF（人類回饋強化學習）
  學習語言結構           ├─ DPO（直接偏好優化）
                         ├─ ORPO（比率偏好優化）
                         ├─ 持續預訓練（Continued Pretraining）
                         └─ 合併/蒸餾（Merge / Distillation）
```

---

## 方法一：監督式微調（SFT — Supervised Fine-Tuning）

### 是什麼？

SFT 是最直觀的 Post-Training 方法：準備一批「輸入 → 理想輸出」的配對資料，讓模型學習模仿這些示範。

```python
# SFT 資料格式範例（指令跟隨）
{
  "messages": [
    {"role": "system", "content": "你是一位專業的台灣稅務顧問。"},
    {"role": "user",   "content": "個人綜合所得稅要怎麼申報？"},
    {"role": "assistant", "content": "台灣個人綜合所得稅申報步驟如下：\n\n1. **確認申報期間**：每年 5 月 1 日至 5 月 31 日..."}
  ]
}
```

### 使用 Qwen + HuggingFace TRL 進行 SFT

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
import torch

# 1. 載入模型（以 Qwen2.5-7B-Instruct 為例）
model_name = "Qwen/Qwen2.5-7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# 2. 準備資料集
dataset = load_dataset("json", data_files="my_sft_data.jsonl")

# 3. 設定訓練參數
config = SFTConfig(
    output_dir="./qwen-sft-output",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=2e-5,
    warmup_ratio=0.1,
    lr_scheduler_type="cosine",
    bf16=True,
    logging_steps=10,
    save_steps=500,
    max_seq_length=2048,
)

# 4. 啟動訓練
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset["train"],
    args=config,
)
trainer.train()
```

### 搭配 LoRA 節省記憶體

全參數 SFT 對 GPU 記憶體要求極高，LoRA（Low-Rank Adaptation）是最常見的解法：

```python
from peft import LoraConfig, get_peft_model, TaskType

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,                    # Rank：越高能力越強，但記憶體也越多
    lora_alpha=32,           # 縮放係數
    target_modules=[         # 對哪些層做 LoRA
        "q_proj", "k_proj", "v_proj",
        "o_proj", "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# trainable params: 83,886,080 || all params: 7,615,832,064
# trainable%: 1.10%  ← 只需訓練 1% 的參數！
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 直觀易懂；資料準備門檻低；效果穩定可預期 |
| **缺點** | 需要大量高品質標記資料；容易過擬合示範風格；無法學習「哪個更好」的概念 |
| **適用場景** | 領域知識注入、風格調整、指令遵從能力強化 |
| **資料需求** | 1,000 ~ 100,000 筆高品質配對 |
| **硬體需求** | 7B 模型：LoRA 約需 16GB VRAM；全參數約需 80GB+ |
| **訓練時長** | LoRA 7B 模型：數小時（A100 × 1）|

---

## 方法二：人類回饋強化學習（RLHF）

### 是什麼？

RLHF（Reinforcement Learning from Human Feedback）是 ChatGPT 成功背後的核心技術。訓練流程分三階段：

```
RLHF 完整流程：

Step 1: SFT（監督式微調）
  Base Model → SFT → SFT Model

Step 2: Reward Model 訓練
  人工標記偏好資料（A vs B 哪個更好？）
  → 訓練 Reward Model（RM）

Step 3: PPO 強化學習
  SFT Model + Reward Signal → PPO 優化
  → 讓模型輸出獲得更高 Reward 的回應

  ┌──────────┐    prompt    ┌─────────────┐
  │ PPO 模型 │ ──────────→ │  Response   │
  └──────────┘             └──────┬──────┘
       ↑                          │ score
  policy update                   ↓
       └──────────── Reward Model ─┘
```

### 偏好資料格式範例

```python
# Reward Model 訓練資料
{
  "prompt": "解釋量子糾纏",
  "chosen": "量子糾纏是指兩個粒子的量子態無論相距多遠都保持關聯...\n（詳細、正確的解釋）",
  "rejected": "量子糾纏就是兩個東西連在一起。\n（簡陋、不夠準確的回答）"
}
```

### 使用 TRL 的 PPO 訓練

```python
from trl import PPOTrainer, PPOConfig, AutoModelForCausalLMWithValueHead
from transformers import pipeline

# Reward function（可用現成的 reward model）
reward_model = pipeline(
    "text-classification",
    model="OpenAssistant/reward-model-deberta-v3-large-v2"
)

def compute_reward(response_texts):
    results = reward_model(response_texts)
    return [torch.tensor(r["score"]) for r in results]

# PPO 訓練設定
ppo_config = PPOConfig(
    model_name="Qwen/Qwen2.5-7B-Instruct",
    learning_rate=1.41e-5,
    batch_size=16,
    mini_batch_size=4,
    gradient_accumulation_steps=4,
    optimize_cuda_cache=True,
    early_stopping=True,
    target_kl=0.1,        # KL 散度上限，防止模型偏離太遠
)

ppo_trainer = PPOTrainer(
    config=ppo_config,
    model=model,
    ref_model=ref_model,  # 參考模型（SFT 模型的凍結副本）
    tokenizer=tokenizer,
)
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 效果上限最高；可學習細緻的人類偏好；OpenAI ChatGPT 的成功驗證 |
| **缺點** | 訓練複雜（三階段）；需要 PPO 穩定性調校；容易出現 reward hacking；基礎設施複雜 |
| **適用場景** | 追求最高對話品質；需要嚴格安全對齊；有充足工程資源的團隊 |
| **資料需求** | 偏好資料 10,000~100,000 筆 |
| **硬體需求** | 需同時運行 SFT 模型 + RM 模型，GPU 需求 2~4x SFT |
| **訓練時長** | 7B 模型：數天（A100 × 4-8）|

---

## 方法三：直接偏好優化（DPO — Direct Preference Optimization）

### 是什麼？

DPO 是 2023 年提出的革命性方法——它把 RLHF 的複雜三步驟，**化簡成一個監督學習目標**，不需要單獨的 Reward Model，也不需要 PPO。

```
RLHF vs DPO：

RLHF：Base → [SFT] → [訓練RM] → [PPO] → Final Model
                         複雜！
DPO：  Base → [SFT] → [DPO Loss] → Final Model
                      ↑
              直接用偏好資料計算 loss，跳過中間環節
```

### DPO 的數學直覺

DPO 直接優化這個目標：增加 `chosen` 回應的對數機率，同時降低 `rejected` 回應的對數機率，並用 KL 散度限制模型不要偏離參考模型太遠。

```python
from trl import DPOTrainer, DPOConfig

# DPO 資料格式（與 RLHF 偏好資料相同）
dpo_dataset = [
    {
        "prompt": "如何提升程式碼可讀性？",
        "chosen": "提升可讀性的方法包括：\n1. 使用有意義的變數名稱...",
        "rejected": "寫好一點就行了。"
    },
    # ...更多資料
]

# DPO 訓練（比 PPO 簡單很多！）
dpo_config = DPOConfig(
    output_dir="./qwen-dpo-output",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=5e-7,          # DPO 通常用更小的 LR
    beta=0.1,                    # KL 懲罰係數，越大越保守
    bf16=True,
    loss_type="sigmoid",         # 原始 DPO loss
)

dpo_trainer = DPOTrainer(
    model=model,
    ref_model=ref_model,         # 參考模型（SFT 後的凍結版）
    args=dpo_config,
    train_dataset=dpo_dataset,
    tokenizer=tokenizer,
)
dpo_trainer.train()
```

### DPO 變體一覽

```
DPO 家族：

┌─────────────────────────────────────────────────────────────────┐
│ IPO（Identity PO）   - 解決 DPO 過擬合問題                     │
│ KTO（Kahneman-Tversky）- 不需要成對資料，只需單筆偏好標記      │
│ ORPO                 - 不需要參考模型（更省記憶體）             │
│ SimPO               - 更穩定，移除 reference model 依賴        │
│ CPO（Contrastive PO）- 結合對比學習                            │
└─────────────────────────────────────────────────────────────────┘
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 比 RLHF 簡單得多；不需要獨立 RM；穩定性好；效果接近 PPO |
| **缺點** | 仍需高品質偏好資料；需要參考模型（多佔一份 VRAM）；偶爾不如 PPO |
| **適用場景** | 想做偏好對齊但工程資源有限；中小型團隊首選對齊方法 |
| **資料需求** | 偏好對（chosen/rejected）5,000~50,000 筆 |
| **硬體需求** | 7B + LoRA：約 24~40GB VRAM（需同時跑參考模型） |
| **訓練時長** | 7B 模型：4~12 小時（A100 × 1-2）|

---

## 方法四：ORPO（Odds Ratio Preference Optimization）

### 是什麼？

ORPO 是 2024 年提出的更激進簡化——它**完全不需要參考模型**，把 SFT 和偏好學習合在一個步驟完成。

```python
from trl import ORPOTrainer, ORPOConfig

# ORPO 最大優勢：不需要 ref_model！
orpo_config = ORPOConfig(
    output_dir="./qwen-orpo-output",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=8e-6,
    beta=0.1,              # ORPO 中的 λ（odds ratio 係數）
    bf16=True,
    max_length=1024,
    max_prompt_length=512,
)

orpo_trainer = ORPOTrainer(
    model=model,           # 注意：不需要 ref_model！
    args=orpo_config,
    train_dataset=dataset,
    tokenizer=tokenizer,
)
orpo_trainer.train()
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 最省記憶體的偏好訓練方法；訓練流程最簡單；效果實驗上競爭力強 |
| **缺點** | 較新，社群驗證案例相對少；部分任務不如 DPO |
| **適用場景** | GPU 資源有限；快速實驗偏好對齊 |
| **硬體需求** | 比 DPO 省 30~40% VRAM |

---

## 方法五：持續預訓練（Continued Pre-Training / Domain Adaptive Pre-Training）

### 是什麼？

持續預訓練是在 Base Model 上，用大量**未標記的領域語料**繼續以語言建模目標訓練，注入領域知識。

```
適用場景：

SFT  → 教模型「怎麼做」（行為）
CPT  → 教模型「知道什麼」（知識）

例如：
- 法律 CPT → 讓模型吸收大量判決書、法條
- 醫療 CPT → 讓模型吸收醫學文獻、病歷格式
- 金融 CPT → 讓模型吸收財報、研究報告
```

```python
from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling

# CPT 資料準備（純文本，不需要標記）
# 例：10GB 的台灣法律文件
def tokenize_function(examples):
    return tokenizer(
        examples["text"],
        truncation=True,
        max_length=2048,
        return_special_tokens_mask=True
    )

# 語言建模目標（Next Token Prediction）
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,   # Causal LM（不是 masked LM）
)

training_args = TrainingArguments(
    output_dir="./qwen-cpt-output",
    num_train_epochs=1,              # CPT 通常 epoch 較少
    per_device_train_batch_size=4,
    gradient_accumulation_steps=8,
    learning_rate=1e-5,              # 比 SFT 更小的 LR，防止遺忘
    warmup_ratio=0.05,
    bf16=True,
    dataloader_num_workers=4,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=data_collator,
)
trainer.train()
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 可注入海量領域知識；無需標記資料；提升基礎語言理解能力 |
| **缺點** | 容易導致「災難性遺忘」；需要大量語料；不直接改變行為模式 |
| **適用場景** | 垂直領域知識注入（法律、醫療、金融）；模型不熟悉的語言/方言強化 |
| **資料需求** | 數 GB ~ 數百 GB 未標記語料 |
| **硬體需求** | 全參數：80GB+ VRAM；LoRA 版本：16~24GB |
| **訓練時長** | 依語料量，可能需數天到數週 |

---

## 方法六：模型合併（Model Merging）

### 是什麼？

模型合併是一種**不需要任何訓練**的「後訓練」方式——直接在參數空間對多個微調模型進行合併，取長補短。

```python
# 使用 mergekit 進行模型合併
# pip install mergekit

# mergekit YAML 設定（SLERP 方法）
merge_config = """
models:
  - model: Qwen/Qwen2.5-7B-Instruct
    parameters:
      weight: 0.5
  - model: your-org/qwen-7b-coding-finetuned
    parameters:
      weight: 0.3
  - model: your-org/qwen-7b-chinese-finetuned
    parameters:
      weight: 0.2

merge_method: linear    # 可選：linear, slerp, ties, dare_ties

dtype: bfloat16
"""

# 執行合併
# mergekit-yaml merge_config.yaml ./merged-model --copy-tokenizer
```

### 主流合併方法比較

```
┌─────────────────────────────────────────────────────────────────┐
│ 合併方法         說明                           適用場景        │
├─────────────────────────────────────────────────────────────────┤
│ Linear Merge   線性加權平均                    快速實驗         │
│ SLERP          球面線性插值（更平滑）           兩模型合併       │
│ TIES           解決參數衝突問題                 多模型合併       │
│ DARE+TIES      隨機丟棄冗餘參數後 TIES 合併    最佳多模型合併   │
│ Task Vectors   方向性任務向量操作              能力增減控制      │
└─────────────────────────────────────────────────────────────────┘
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | **零訓練成本**；可快速實驗組合；社群有大量開源合併模型可參考 |
| **缺點** | 效果不穩定；難以預期；可能引入不一致行為；無法注入全新知識 |
| **適用場景** | 快速原型驗證；組合現有開源微調模型；資源極度有限時 |
| **硬體需求** | 只需 CPU/RAM 足以載入模型，無需 GPU |
| **時間成本** | 分鐘級（純計算，無訓練）|

---

## 方法七：知識蒸餾（Knowledge Distillation）

### 是什麼？

讓小模型（Student）學習大模型（Teacher）的輸出分佈，在保留部分能力的同時大幅壓縮模型大小。

```
知識蒸餾流程：

Teacher（大模型）：Qwen2.5-72B
    ↓ 生成 soft labels（完整機率分佈）
Student（小模型）：Qwen2.5-7B
    ↓ 同時學習 hard labels 和 soft labels

損失函數：
  L = α × CrossEntropy(y, student_output)
    + (1-α) × KL_Divergence(teacher_soft, student_soft)
```

```python
import torch.nn.functional as F

def distillation_loss(
    student_logits,
    teacher_logits,
    labels,
    temperature=4.0,
    alpha=0.7
):
    # Soft loss（學習老師的分佈）
    soft_student = F.log_softmax(student_logits / temperature, dim=-1)
    soft_teacher = F.softmax(teacher_logits / temperature, dim=-1)
    kl_loss = F.kl_div(soft_student, soft_teacher, reduction="batchmean")
    soft_loss = kl_loss * (temperature ** 2)

    # Hard loss（學習正確答案）
    hard_loss = F.cross_entropy(student_logits, labels)

    return alpha * hard_loss + (1 - alpha) * soft_loss
```

### 優缺點分析

| 面向 | 評估 |
|------|------|
| **優點** | 可壓縮模型大小；保留大模型能力；適合部署資源受限環境 |
| **缺點** | 需要訪問 Teacher 模型；實作複雜；效果仍不如 Teacher |
| **適用場景** | 生產環境需要小模型；邊緣設備部署 |
| **硬體需求** | 需同時運行 Teacher + Student，記憶體需求較高 |

---

## 全方法橫向比較

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Post-Training 方法全比較矩陣                          │
├────────────────┬──────────┬──────────┬──────────┬──────────┬────────────────┤
│ 方法           │ 資料需求 │ 算力需求 │ 實作複雜度│ 效果上限 │ 最適場景       │
├────────────────┼──────────┼──────────┼──────────┼──────────┼────────────────┤
│ SFT            │ 中（標記）│ 中       │ 低       │ 中高     │ 行為/風格調整  │
│ RLHF/PPO       │ 高（偏好）│ 高       │ 高       │ 最高     │ 頂級對話品質   │
│ DPO            │ 中（偏好）│ 中       │ 中       │ 中高     │ 對齊首選方案   │
│ ORPO           │ 中（偏好）│ 低中     │ 低       │ 中高     │ 資源有限對齊   │
│ CPT            │ 高（無標）│ 高       │ 中       │ -        │ 領域知識注入   │
│ 模型合併        │ 無        │ 極低     │ 低       │ 中       │ 快速原型/實驗  │
│ 知識蒸餾        │ 中        │ 高       │ 高       │ 中       │ 模型壓縮部署   │
└────────────────┴──────────┴──────────┴──────────┴──────────┴────────────────┘
```

---

## 如何選擇適合你的方法？

```
你的需求是什麼？
│
├── 想讓模型學習特定領域知識（不改行為）
│   └── → 持續預訓練（CPT）
│
├── 想讓模型遵循指令、改變輸出格式
│   └── → SFT（有時 + DPO 做二階段）
│
├── 想讓模型更「有禮貌」、更安全、更符合人類偏好
│   ├── 資源充足 → RLHF/PPO
│   ├── 一般資源 → DPO
│   └── 資源有限 → ORPO
│
├── 想快速驗證組合現有開源模型
│   └── → 模型合併（Model Merging）
│
└── 想把大模型能力壓縮到小模型
    └── → 知識蒸餾
```

---

## 實戰建議與避坑指南

### 1. 資料品質 >> 資料數量

```
❌ 錯誤做法：收集 100,000 筆低品質資料
✓ 正確做法：精心標記 1,000 筆高品質資料

研究顯示：5,000 筆高品質 SFT 資料
效果 > 50,000 筆品質不一的資料
```

### 2. 從 Instruct 模型開始，不從 Base 開始

```python
# 推薦：從已有指令跟隨能力的模型開始
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-7B-Instruct")

# 不建議（需更多資料才能教會指令跟隨）
# model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-7B")
```

### 3. 評估策略要提前設計

```python
# 建立評估集（與訓練集獨立）
eval_prompts = [
    "請解釋什麼是量子電腦？",
    "幫我寫一個 Python 排序函數",
    # ... 覆蓋你的主要使用場景
]

# 使用 LLM-as-Judge 評估（如 GPT-4 or Claude 打分）
# 避免完全依賴 Perplexity 這類訓練指標
```

### 4. 常見錯誤

| 錯誤 | 後果 | 解法 |
|------|------|------|
| LR 設太高 | 模型「遺忘」原有能力 | 先小 LR 實驗再調大 |
| epoch 過多 | 過擬合、回應多樣性降低 | 早停 + 驗證集監控 |
| 資料格式不一致 | 模型學到錯誤的 chat template | 嚴格統一使用模型原始 template |
| 跳過評估只看 loss | 不知道模型實際有沒有改善 | 訓練中定期做 human eval |
| 沒有設定 reference model | DPO 訓練不穩定 | 確保 ref_model 為 SFT 後的凍結版本 |

---

## 推薦工具生態

```
訓練框架：
  ├── TRL（HuggingFace）  → SFT、DPO、PPO、ORPO 一站式
  ├── LLaMA-Factory       → 中文社群最友好的微調框架
  ├── Axolotl             → 高度可設定，支援多種方法
  └── Unsloth             → 2x 速度，0.5x 記憶體，LoRA 優化

評估框架：
  ├── lm-evaluation-harness  → 標準 benchmark 跑分
  ├── MT-Bench               → 多輪對話品質評估
  └── OpenCompass            → 中文評估最完善

模型合併：
  └── mergekit               → 支援所有主流合併算法

資料處理：
  ├── Argilla                → 資料標記協作平台
  └── distilabel             → 合成資料生成
```

---

## 總結

Post-Training 不是一條路，而是一個工具箱。對大多數工程師而言：

1. **起點**：先做 SFT，資料品質是關鍵
2. **進階**：加上 DPO 提升偏好對齊，ORPO 更省資源
3. **知識注入**：需要領域知識才考慮 CPT
4. **快速驗證**：模型合併是最便宜的實驗方式
5. **生產壓縮**：部署資源受限時考慮蒸餾

最重要的是：**先明確你的目標，再選擇方法**。沒有萬能的 Post-Training 方案，適合你業務場景和資源限制的，才是最好的方案。

---

*本文所有程式碼以 HuggingFace TRL 框架為主，以 Qwen2.5 系列模型為範例，但概念同樣適用於 LLaMA、Mistral、Gemma 等其他開源模型。*
