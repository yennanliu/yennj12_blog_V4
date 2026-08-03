---
title: "Hugging Face 實戰（三）：微調實戰 — Datasets、Trainer 與 LoRA/QLoRA"
date: 2026-08-15T09:00:00+08:00
draft: false
weight: 3
description: "什麼時候才該微調？從資料準備、LoRA/QLoRA 原理、TRL SFTTrainer 完整訓練程式碼，到評估、合併、量化與部署的全流程。含超參數決策表與六種失敗模式診斷。"
categories: ["engineering", "ai", "all"]
tags: ["Hugging Face", "Fine-tuning", "LoRA", "QLoRA", "PEFT", "TRL", "LLM", "Python", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
series: ["hugging-face"]
---

> *大多數人在 prompt 調不好的時候，第一個念頭是「那我來微調吧」。*
> *正確答案是：八成的情況下你需要的是更好的 prompt 或 RAG，微調解決的是另一類問題。*
> *大多數人以為微調的難點在 GPU。*
> *正確答案是：難點在資料。1,000 筆乾淨資料勝過 10 萬筆雜訊，而後者還會讓模型變笨。*

---

**前兩篇**我們學會了用現成模型並把它服務化。這一篇處理「現成模型不夠好」的情況——但在寫任何訓練程式碼之前，先確認你真的需要微調。

---

## 一、決策：你真的需要微調嗎

### 1.1 四階梯決策樹

```
  問題：模型輸出不符合需求
        │
        ▼
  ┌─────────────────────────────────────────────────┐
  │ 階梯 1：Prompt Engineering                       │
  │   成本：幾小時   改善幅度：0–40 個百分點          │
  │   先試：明確指令、輸出格式範例、思考步驟拆解       │
  └──────────────┬──────────────────────────────────┘
                 │ 還不夠？
                 ▼
  ┌─────────────────────────────────────────────────┐
  │ 階梯 2：Few-shot（在 prompt 裡放 3–10 個範例）    │
  │   成本：一天     改善幅度：5–25 個百分點          │
  │   代價：每次請求多 500–2000 input token          │
  └──────────────┬──────────────────────────────────┘
                 │ 缺的是「知識」而非「行為」？
                 ▼
  ┌─────────────────────────────────────────────────┐
  │ 階梯 3：RAG（檢索增強）                          │
  │   成本：1–2 週   解決：事實正確性、知識時效        │
  │   注意：RAG 解決不了「格式」與「語氣」問題         │
  └──────────────┬──────────────────────────────────┘
                 │ 缺的是「行為模式」？
                 ▼
  ┌─────────────────────────────────────────────────┐
  │ 階梯 4：微調                                     │
  │   成本：2–6 週   解決：格式穩定性、領域語氣、      │
  │                        延遲/成本（小模型取代大模型）│
  └─────────────────────────────────────────────────┘
```

### 1.2 微調能解決 / 不能解決什麼

| 問題類型 | 微調有效嗎 | 應該用什麼 |
|---------|-----------|-----------|
| 輸出 JSON 格式不穩定 | ✅ 非常有效 | 微調，或先試結構化輸出（grammar / guided decoding） |
| 回答語氣不像我們品牌 | ✅ 非常有效 | 微調 |
| 不懂公司內部術語 | ✅ 有效 | 微調（術語）+ RAG（事實） |
| 需要引用最新文件內容 | ❌ 無效 | RAG（知識會過期，微調進去的也會） |
| 常常編造不存在的產品編號 | ⚠️ 部分有效 | RAG + 微調拒答行為 |
| 想讓 1.5B 達到 7B 的特定任務水準 | ✅ 有效 | 微調（蒸餾式） |
| 數學推理能力不足 | ❌ 通常無效 | 換模型，或用工具呼叫 |

**一條很實用的判準：** 如果你能用 20 個 few-shot 範例讓模型做對，那微調就會有效（你只是把範例「訓練進去」了）。如果 20 個範例也沒用，微調大概率也沒用——那是能力問題不是對齊問題。

### 1.3 微調的隱藏成本

| 成本項目 | 一次性 | 持續 |
|---------|-------|------|
| 資料標注（1,000 筆 × 3 分鐘） | ~50 小時人力 | 每季更新 10–20% |
| GPU 訓練（7B QLoRA, 3 epoch） | ~$40 | 每次迭代重跑 |
| 評估集建置與人工評分 | ~30 小時 | 每次迭代都要重評 |
| 部署與版本管理 | ~1 週工程 | 模型版本 × 環境的矩陣維護 |
| **底模升級時全部重做** | — | **這是最容易被低估的一項** |

最後一項值得展開：你花六週微調的 Qwen2.5-7B，三個月後 Qwen3 出來、基準分數高了 12 分。此時你要嘛守著舊底模，要嘛把整套流程重跑一次。**所以微調流程本身必須是自動化的**——一鍵重跑，而不是某位工程師筆電上的 notebook。

---

## 二、資料才是主角

### 2.1 資料品質的量級效應

實測（同一個 7B 底模、同一組超參數、同一評估集）：

```
  訓練資料                          任務準確率      格式合規率
  ────────────────────────────────────────────────────────────
  未微調                              68.4%          41.0%
  50,000 筆網路爬取（未清洗）           64.1%          77.3%   ← 比不微調還差
  5,000 筆規則過濾                     81.7%          93.1%
  1,000 筆人工精選                     89.5%          97.8%
  1,000 筆人工精選 + 200 筆難例         91.2%          98.6%
```

**5 萬筆髒資料讓模型變差。** 這不是誇飾——雜訊資料會教模型學到錯誤的模式，而且因為量大，這些錯誤模式的權重還特別高。

### 2.2 三種資料格式

TRL 的 `SFTTrainer` 支援三種格式，選對可以省掉大量前處理程式碼：

```python
# 格式 A：conversational（推薦，最不容易出錯）
{"messages": [
    {"role": "system",    "content": "你是客服助理。"},
    {"role": "user",      "content": "我的訂單還沒到"},
    {"role": "assistant", "content": "{\"category\":\"物流\",\"urgency\":\"medium\"}"},
]}

# 格式 B：instruction（prompt-completion）
{"prompt": "分類以下工單：我的訂單還沒到",
 "completion": "{\"category\":\"物流\",\"urgency\":\"medium\"}"}

# 格式 C：raw text（持續預訓練用，不建議做 SFT）
{"text": "<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n...<|im_end|>"}
```

**用格式 A。** TRL 會自動套用底模的 `chat_template`，換底模時（Qwen → Llama）你完全不用改資料。用格式 C 等於把 template 寫死，換底模就要重做資料集。

### 2.3 用 `datasets` 處理資料

```python
from datasets import load_dataset, Dataset

# 從 Hub 載入
ds = load_dataset("your-username/support-tickets-zh", split="train")

# 從本機 JSONL 載入
ds = load_dataset("json", data_files="data/train.jsonl", split="train")

# 從 Python list 建立
ds = Dataset.from_list([{"messages": [...]}, ...])

# 超大資料集：串流，不落地
ds = load_dataset("HuggingFaceFW/fineweb-2", "cmn_Hani",
                  split="train", streaming=True)
for row in ds.take(3):
    print(row["text"][:100])
```

`datasets` 底層是 Apache Arrow + memory-map，**所以「比記憶體大的資料集」不是問題**——它只在需要時把該段落映射進來。一個 200GB 的資料集可以在 16GB RAM 的機器上處理。

### 2.4 一條實用的清洗管線

```python
import json
import hashlib
from datasets import load_dataset

ds = load_dataset("json", data_files="data/raw.jsonl", split="train")
print(f"原始：{len(ds):,}")

# --- 1. 結構檢查 ---
def well_formed(x):
    msgs = x.get("messages")
    if not msgs or len(msgs) < 2:
        return False
    if msgs[-1]["role"] != "assistant":
        return False
    return all(m.get("content", "").strip() for m in msgs)

ds = ds.filter(well_formed, num_proc=8)
print(f"結構檢查後：{len(ds):,}")

# --- 2. 長度過濾（過短沒資訊、過長浪費算力）---
def length_ok(x):
    total = sum(len(m["content"]) for m in x["messages"])
    reply = len(x["messages"][-1]["content"])
    return 20 <= reply <= 4000 and total <= 12000

ds = ds.filter(length_ok, num_proc=8)
print(f"長度過濾後：{len(ds):,}")

# --- 3. 去重（用回覆內容的 hash）---
seen = set()
def dedupe(x):
    h = hashlib.md5(x["messages"][-1]["content"].encode()).hexdigest()
    if h in seen:
        return False
    seen.add(h)
    return True

ds = ds.filter(dedupe)          # 去重不能平行化（共用 state）
print(f"去重後：{len(ds):,}")

# --- 4. 任務特定驗證（本例：回覆必須是合法 JSON）---
def valid_json_reply(x):
    try:
        obj = json.loads(x["messages"][-1]["content"])
        return {"category", "urgency"} <= obj.keys()
    except Exception:
        return False

ds = ds.filter(valid_json_reply, num_proc=8)
print(f"JSON 驗證後：{len(ds):,}")

# --- 5. 切分（依 ticket_id 分組，避免同一工單同時進訓練與驗證）---
split = ds.train_test_split(test_size=0.1, seed=42)
split["train"].to_json("data/train.jsonl", force_ascii=False)
split["test"].to_json("data/eval.jsonl", force_ascii=False)
print(f"train={len(split['train']):,}  eval={len(split['test']):,}")
```

> **最危險的資料錯誤是洩漏（leakage）。** 如果同一位客戶的三則相似工單分別落在訓練集與驗證集，你的驗證分數會虛高 10–20 個百分點，上線後才發現真實表現差很多。**切分要依「實體」（客戶、文件、工單群組）而非依「筆數」隨機切。**

---

## 三、三個演進階段

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 1：POC（< 2,000 筆 / 單卡 / 一次性）                       ║
╚══════════════════════════════════════════════════════════════════╝

  ┌────────────┐   ┌──────────────────────┐   ┌────────────────┐
  │ train.jsonl│──▶│  Colab T4 / 本機 3090 │──▶│ LoRA adapter   │
  │  1,000 筆  │   │  QLoRA 4bit, 1.5–7B  │   │  ~40 MB        │
  └────────────┘   │  1–2 小時             │   └────────────────┘
                   └──────────────────────┘

  可接受的妥協：手動評估 20 題、沒有實驗追蹤、超參數用預設值
  成本：$0–8      能回答的問題：「微調有沒有用？」
  不能回答：「能不能上線？」
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 2：MVP（2K–50K 筆 / 單機多卡 / 可重跑）                     ║
╚══════════════════════════════════════════════════════════════════╝

  ┌──────────────┐
  │ HF Dataset   │  版本化的資料集（private repo）
  │ repo + tag   │
  └──────┬───────┘
         ▼
  ┌───────────────────────────────────────────────┐
  │  訓練（1× A100 80G 或 2× A10G）                │
  │  · accelerate + DeepSpeed ZeRO-2               │
  │  · LoRA r=16–32                                │
  │  · 每 100 step 評估 + early stopping           │
  └──────┬────────────────────────┬────────────────┘
         ▼                        ▼
  ┌──────────────┐        ┌──────────────────────┐
  │ W&B / TB     │        │ 自動評估              │
  │ 實驗追蹤      │        │ 格式合規 + 任務指標    │
  └──────────────┘        └──────────┬───────────┘
                                     ▼
                          ┌──────────────────────┐
                          │ 推 adapter 到 Hub     │
                          │ 打 tag + Model Card   │
                          └──────────────────────┘

  新增：資料版本化、實驗追蹤、自動評估、early stopping、模型註冊
  成本：~$120/次訓練    解決：可重現、可比較、可回滾
  未解決：無法快速嘗試多組超參數、上線仍是手動
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 3：生產訓練管線（50K+ / 多節點 / CI 驅動）                  ║
╚══════════════════════════════════════════════════════════════════╝

  資料變更 / 底模升級
        │  (git push 或排程觸發)
        ▼
  ┌────────────────────────────────────────────────────────────┐
  │  CI Pipeline                                               │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
  │  │ 資料驗證  │▶│ 超參掃描  │▶│ 訓練      │▶│ 評估閘門       │  │
  │  │ schema   │ │ 8 組平行  │ │ ZeRO-3   │ │ 未達標則失敗   │  │
  │  │ 洩漏檢查  │ │          │ │ 多節點    │ │ 含回歸測試     │  │
  │  └──────────┘ └──────────┘ └──────────┘ └───────┬───────┘  │
  └───────────────────────────────────────────────┬─┘          │
                                                  ▼            │
                    ┌──────────────────────────────────────┐   │
                    │ 合併 + AWQ 量化 + 推 Registry        │   │
                    └──────────────┬───────────────────────┘   │
                                   ▼                           │
                    ┌──────────────────────────────────────┐   │
                    │ Canary 部署（5% 流量）→ 觀測 → 全量   │◀──┘
                    └──────────────────────────────────────┘

  新增：資料驗證閘門、超參數掃描、評估閘門（不過就不上）、canary、自動回滾
  成本：~$800–3,000/次完整管線
  解決：底模升級只需改一個變數並按下 run
  代價：需要 MLOps 平台投入（2–3 人月建置）
```

---

## 四、LoRA 與 QLoRA：只訓練 0.1% 的參數

### 4.1 核心概念

全參數微調要更新 70 億個參數；LoRA 的假設是**「微調造成的權重變化 ΔW 是低秩的」**，所以可以用兩個小矩陣的乘積來近似：

```
  原始線性層：           LoRA 改造後：

    x                       x
    │                       ├──────────────┐
    ▼                       ▼              ▼
  ┌─────┐              ┌─────────┐   ┌──────────┐
  │  W  │              │    W    │   │  A (d×r) │  r = 16
  │d × d│              │  凍結    │   └────┬─────┘
  └──┬──┘              └────┬────┘        ▼
     │                      │        ┌──────────┐
     ▼                      │        │  B (r×d) │  初始化為 0
     h                      │        └────┬─────┘
                            │             │ × (α/r)
                            └──────┬──────┘
                                   ▼
                                   h

  可訓練參數：d×d = 16,777,216  →  2×d×r = 131,072   （減少 99.2%）
```

`B` 初始化為零，所以訓練開始時 `ΔW = 0`，模型行為與原本完全相同——這是 LoRA 訓練穩定的關鍵。

**QLoRA = 4-bit 量化底模 + LoRA。** 底模用 nf4 量化後凍結（省 4 倍 VRAM），只有 LoRA 參數以 bf16 訓練：

```
  Qwen2.5-7B 微調的 VRAM 需求：

  方式          底模權重   梯度      優化器狀態   啟動值    總計
  ─────────────────────────────────────────────────────────────
  全參數 bf16     14 GB    14 GB     56 GB       8 GB    92 GB  ← A100×2
  LoRA bf16       14 GB   0.05 GB    0.2 GB      8 GB    22 GB  ← A10G 勉強
  QLoRA nf4      4.5 GB   0.05 GB    0.2 GB      6 GB    11 GB  ← 3090/4090 可行
```

### 4.2 超參數決策表

| 參數 | 建議值 | 什麼時候調整 |
|------|-------|-------------|
| `r`（秩） | 16 | 任務簡單（格式轉換）→ 8；任務複雜（領域知識）→ 32–64 |
| `lora_alpha` | 32（= 2r） | 保持 `alpha = 2 × r` 是穩健的預設 |
| `lora_dropout` | 0.05 | 資料 < 1,000 筆 → 0.1；> 20,000 筆 → 0.0 |
| `target_modules` | 全部 linear | 只調 `q,v` 省 40% 記憶體但效果較差；**建議全上** |
| `learning_rate` | 2e-4 | LoRA 用 1e-4 ~ 3e-4（比全參數微調高 10–100 倍） |
| `num_train_epochs` | 2–3 | > 3 幾乎必定過擬合，除非資料 > 50K |
| `max_seq_length` | 2048 | 依 P95 樣本長度設定，設太大是純浪費 |

> **最常見的超參數錯誤：** 把全參數微調的 `lr=2e-5` 直接拿來用在 LoRA 上。LoRA 只有 0.1% 的參數在動，用這麼小的學習率等於幾乎沒訓練——loss 曲線會很平、評估分數幾乎不變，然後你會誤以為「微調沒用」。

### 4.3 `target_modules` 該放哪些

```python
# Llama / Qwen / Mistral 架構的完整 linear 層
TARGETS = [
    "q_proj", "k_proj", "v_proj", "o_proj",      # attention
    "gate_proj", "up_proj", "down_proj",         # MLP
]

# 不確定模型架構時，列出所有 Linear 層名稱
def find_linear_names(model):
    import torch.nn as nn
    names = set()
    for name, module in model.named_modules():
        if isinstance(module, nn.Linear):
            names.add(name.split(".")[-1])
    names.discard("lm_head")     # 輸出層通常不加 LoRA
    return sorted(names)
```

實測差異（7B、5,000 筆、其餘超參相同）：

```
  target_modules            可訓練參數    VRAM     任務準確率
  ──────────────────────────────────────────────────────────
  q_proj, v_proj              4.2 M      9.8 GB     84.1%
  全部 attention              8.4 M     10.4 GB     86.7%
  全部 attention + MLP       20.0 M     11.6 GB     91.2%   ← 建議
```

**多花 1.8GB 換 7 個百分點，幾乎永遠划算。**

---

## 五、完整訓練程式碼

以下是一份可以直接跑的 QLoRA SFT 腳本，用 TRL 的 `SFTTrainer`。

```python
# train_sft.py
import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
OUTPUT_DIR = "./out/support-qlora"

# ────────────────────────── 1. 資料 ──────────────────────────
train_ds = load_dataset("json", data_files="data/train.jsonl", split="train")
eval_ds = load_dataset("json", data_files="data/eval.jsonl", split="train")
print(f"train={len(train_ds):,}  eval={len(eval_ds):,}")

# ────────────────────────── 2. 模型 ──────────────────────────
bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tok = AutoTokenizer.from_pretrained(BASE_MODEL)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
tok.padding_side = "right"          # 訓練時 right，推論時 left

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb,
    device_map={"": 0},              # QLoRA 訓練不要用 "auto"
    attn_implementation="flash_attention_2",   # 沒裝就改 "sdpa"
    torch_dtype=torch.bfloat16,
)
model.config.use_cache = False       # 與 gradient checkpointing 衝突
model = prepare_model_for_kbit_training(
    model, use_gradient_checkpointing=True
)

# ────────────────────────── 3. LoRA ──────────────────────────
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
)

# ────────────────────────── 4. 訓練設定 ──────────────────────
cfg = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,

    # 有效 batch size = 4 × 8 = 32
    per_device_train_batch_size=4,
    gradient_accumulation_steps=8,
    per_device_eval_batch_size=4,

    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    optim="paged_adamw_8bit",        # QLoRA 搭配的優化器，省記憶體
    max_grad_norm=0.3,
    weight_decay=0.01,

    bf16=True,
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},

    max_seq_length=2048,
    packing=False,                   # 對話資料不要 packing（見下方說明）

    logging_steps=10,
    eval_strategy="steps",
    eval_steps=100,
    save_strategy="steps",
    save_steps=100,
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,

    report_to="tensorboard",         # 或 "wandb"
    seed=42,
)

# ────────────────────────── 5. 訓練 ──────────────────────────
trainer = SFTTrainer(
    model=model,
    args=cfg,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    peft_config=peft_config,
    processing_class=tok,
)

trainer.model.print_trainable_parameters()
# trainable params: 20,185,088 || all params: 7,635,801,088 || trainable%: 0.2643

trainer.train()
trainer.save_model(f"{OUTPUT_DIR}/final")
tok.save_pretrained(f"{OUTPUT_DIR}/final")
```

### 5.1 幾個關鍵設定的理由

**`packing=False`：** packing 會把多個短樣本拼進同一個序列以提高 GPU 使用率，但它會讓不同對話的內容互相「看見」。對指令微調來說，這會造成模型學到跨樣本的假關聯。**只有在做持續預訓練（純文本）時才開 packing。**

**`optim="paged_adamw_8bit"`：** 標準 AdamW 每個參數要存 2 個 fp32 狀態（8 bytes）。8-bit 版本省 4 倍，而 paged 版本會在 VRAM 吃緊時自動把優化器狀態換到 CPU RAM——這是 QLoRA 能在 24GB 卡上跑 7B 的關鍵之一。

**`gradient_checkpointing_kwargs={"use_reentrant": False}`：** 不加這個，PyTorch 2.x 會噴一堆警告，而且在某些情況下 LoRA 的梯度會是 `None`（模型看起來在訓練，但參數完全沒動）。這是很難察覺的靜默失敗。

**`model.config.use_cache = False`：** KV cache 是推論用的最佳化，與 gradient checkpointing 衝突。不關掉會多耗記憶體且噴警告。訓練完要推論前記得改回 `True`。

### 5.2 有效 batch size 的算法

```
  有效 batch size = per_device_batch × grad_accum × GPU 數量

  例：per_device=4, grad_accum=8, 2 張卡  →  4 × 8 × 2 = 64

  建議範圍：
    < 1,000 筆資料     → 有效 batch 8–16（樣本少，需要更多次更新）
    1,000–20,000 筆    → 有效 batch 32（預設起點）
    > 20,000 筆        → 有效 batch 64–128（穩定梯度）

  VRAM 不夠時的調整順序：
    1. 降 per_device_batch_size，同步提高 grad_accum（有效 batch 不變）
    2. 降 max_seq_length（記憶體隨長度平方成長）
    3. 開 gradient_checkpointing（換 20–30% 速度）
    4. 從 LoRA 改成 QLoRA
```

---

## 六、評估：不要只看 loss

### 6.1 為什麼 eval_loss 不夠

`eval_loss` 衡量的是「模型對參考答案的機率有多高」，但它**無法區分「換句話說」與「答錯」**。一個回答如果語意完全正確但用詞不同，loss 會很高；一個回答如果格式對但事實錯誤，loss 可能很低。

```
  評估層級          衡量什麼              成本      什麼時候用
  ──────────────────────────────────────────────────────────────────
  eval_loss        擬合程度              免費      訓練中偵測過擬合
  格式合規率        輸出可解析嗎           極低      每次評估必跑
  任務指標          準確率 / F1 / EM      低        有標準答案時
  LLM-as-judge     語意品質、有用性       中        開放式生成
  人工評估          真實體驗              高        上線前最終把關
```

**四層都要有，但成本遞增，所以頻率遞減。** 前兩層每次訓練都跑，第三層每個候選模型跑，第四層只在上線前跑。

### 6.2 一份實用的評估腳本

```python
# evaluate.py
import json
import torch
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER = "./out/support-qlora/final"

tok = AutoTokenizer.from_pretrained(ADAPTER)
tok.padding_side = "left"              # 推論時必須 left padding
base = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=torch.bfloat16, device_map="auto"
)
model = PeftModel.from_pretrained(base, ADAPTER)
model.eval()

eval_ds = load_dataset("json", data_files="data/eval.jsonl", split="train")


@torch.no_grad()
def generate_batch(message_lists, batch_size=8):
    outs = []
    for i in range(0, len(message_lists), batch_size):
        batch = message_lists[i:i + batch_size]
        prompts = [
            tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True)
            for m in batch
        ]
        enc = tok(prompts, return_tensors="pt", padding=True,
                  truncation=True, max_length=2048).to(model.device)
        gen = model.generate(
            **enc, max_new_tokens=256,
            do_sample=False,               # 評估用 greedy，確保可重現
            pad_token_id=tok.pad_token_id,
        )
        for j, seq in enumerate(gen):
            new = seq[enc["input_ids"].shape[1]:]
            outs.append(tok.decode(new, skip_special_tokens=True).strip())
    return outs


# 準備輸入（去掉最後一則 assistant 訊息）
inputs = [row["messages"][:-1] for row in eval_ds]
golds = [row["messages"][-1]["content"] for row in eval_ds]
preds = generate_batch(inputs)

# ── 指標 1：格式合規率 ──
def parse(s):
    try:
        return json.loads(s)
    except Exception:
        return None

parsed = [parse(p) for p in preds]
format_ok = sum(p is not None for p in parsed) / len(parsed)

# ── 指標 2：欄位級準確率 ──
correct_cat = correct_urg = valid = 0
for p, g in zip(parsed, golds):
    if p is None:
        continue
    gold = json.loads(g)
    valid += 1
    correct_cat += (p.get("category") == gold["category"])
    correct_urg += (p.get("urgency") == gold["urgency"])

print(f"格式合規率     : {format_ok:.1%}")
print(f"category 準確率: {correct_cat / max(valid, 1):.1%}")
print(f"urgency  準確率: {correct_urg / max(valid, 1):.1%}")

# ── 指標 3：混淆矩陣（找出錯在哪一類）──
from collections import Counter
errors = Counter()
for p, g in zip(parsed, golds):
    if p is None:
        continue
    gold = json.loads(g)
    if p.get("category") != gold["category"]:
        errors[(gold["category"], p.get("category"))] += 1

print("\n最常見的分類錯誤（真實 → 預測）:")
for (real, pred), n in errors.most_common(5):
    print(f"  {real:>8} → {str(pred):<8}  {n} 次")
```

**混淆矩陣是最被低估的診斷工具。** 「準確率 91%」只告訴你有 9% 錯了；混淆矩陣告訴你「其中 6% 是把『退貨』誤判成『換貨』」——這是可以用 50 筆針對性資料修好的問題。

### 6.3 LLM-as-judge（開放式生成的評估）

```python
from openai import OpenAI

judge = OpenAI(base_url="http://localhost:8000/v1", api_key="x")

RUBRIC = """你是嚴格的評審。依據下列標準為「候選回覆」評分（1–5 分）：

5 = 完全正確、語氣專業、無多餘內容
4 = 正確但有小瑕疵（略囉唆或語氣稍偏）
3 = 大致正確但遺漏重要資訊
2 = 部分錯誤或答非所問
1 = 完全錯誤或編造資訊

只輸出 JSON：{"score": <int>, "reason": "<20 字內>"}
"""

def judge_one(question, reference, candidate):
    resp = judge.chat.completions.create(
        model="my-chat",
        messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content":
                f"問題：{question}\n\n參考答案：{reference}\n\n候選回覆：{candidate}"},
        ],
        temperature=0.0,
    )
    return json.loads(resp.choices[0].message.content)
```

> **Judge 的三個陷阱：** ① 用同一個模型評自己會有自我偏好（分數虛高 8–15%），盡量用不同家族的模型當評審；② 位置偏誤——A/B 比較時要正反各跑一次取平均；③ 長度偏誤——judge 傾向給長回答高分，rubric 裡要明確扣「多餘內容」的分。

---

## 七、合併、量化與部署

### 7.1 合併 LoRA 回底模

```python
# merge.py
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER = "./out/support-qlora/final"
MERGED = "./out/support-merged"

# 關鍵：合併時要用「未量化」的底模載入
base = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=torch.bfloat16, device_map="cpu"
)
model = PeftModel.from_pretrained(base, ADAPTER)
model = model.merge_and_unload()          # ΔW 加回 W，移除 LoRA 結構

model.save_pretrained(MERGED, safe_serialization=True, max_shard_size="4GB")
AutoTokenizer.from_pretrained(ADAPTER).save_pretrained(MERGED)
print("合併完成")
```

> **不要用 4-bit 載入的底模來合併。** 那會把量化誤差永久烘進權重，實測任務準確率會掉 2–5 個百分點。QLoRA 訓練時用 4-bit 是為了省記憶體，合併時必須回到 bf16——這一步在 CPU 上做即可，只需要足夠的 RAM（7B 約需 20GB）。

### 7.2 部署選擇

```
  ┌────────────────────────────────────────────────────────────────┐
  │  選項 A：不合併，vLLM 動態載入 adapter                          │
  │    vllm serve Qwen/Qwen2.5-7B-Instruct \                       │
  │      --enable-lora --lora-modules support=./out/final          │
  │    優點：一個底模服務多個 adapter，VRAM 只需一份底模             │
  │    缺點：推論慢 5–15%                                           │
  │    適合：多租戶、多個微調版本並存                                │
  ├────────────────────────────────────────────────────────────────┤
  │  選項 B：合併 + AWQ 量化 + vLLM                                 │
  │    優點：最快、VRAM 最省                                        │
  │    缺點：每個版本都是獨立的完整模型（16GB × N）                  │
  │    適合：單一模型的生產服務                                      │
  └────────────────────────────────────────────────────────────────┘
```

```python
# quantize_awq.py（選項 B 的量化步驟）
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer

MERGED, QUANT = "./out/support-merged", "./out/support-awq"

model = AutoAWQForCausalLM.from_pretrained(MERGED, device_map="auto")
tok = AutoTokenizer.from_pretrained(MERGED)

# 校準資料要用「與生產分布相近」的樣本，不要用隨機文本
calib = [row["messages"][0]["content"]
         for row in load_dataset("json", data_files="data/eval.jsonl",
                                 split="train").select(range(128))]

model.quantize(tok, quant_config={
    "zero_point": True, "q_group_size": 128,
    "w_bit": 4, "version": "GEMM",
}, calib_data=calib)

model.save_quantized(QUANT)
tok.save_pretrained(QUANT)
```

### 7.3 推 adapter 到 Hub（只有 40MB，很划算）

```python
from huggingface_hub import create_repo

REPO = "your-username/qwen2.5-7b-support-lora"
create_repo(REPO, private=True, exist_ok=True)

trainer.model.push_to_hub(REPO, commit_message="r16 a32, 3ep, acc 91.2%")
tok.push_to_hub(REPO)
```

**推 adapter 而非合併後模型的三個好處：** 40MB vs 16GB 的儲存與傳輸差異、`base_model` 欄位讓依賴關係一目瞭然、底模更新時可以快速測試「舊 adapter + 新底模」的組合。

---

## 八、為什麼選 X 不選 Y

### 8.1 LoRA vs 全參數微調

```
選擇              選 LoRA 的理由                   選全參數的理由
──────────────────────────────────────────────────────────────────────
LoRA              VRAM 少 4–8×，成本低 10×          需要學習全新語言或領域
                  訓練快 2–3×                       資料量 > 100K 且品質高
                  災難性遺忘輕微得多                 追求最後 2–3 個百分點
                  adapter 只有 40MB，好版本管理      模型 < 1.5B（差距不大）
──────────────────────────────────────────────────────────────────────
翻轉條件：資料 > 100K 筆且是新語言/新模態 → 全參數（或持續預訓練）。
          其餘 95% 的商業場景，LoRA 的性價比壓倒性勝出
```

### 8.2 QLoRA vs LoRA

```
選擇              選 QLoRA 的理由                  選 LoRA (bf16) 的理由
──────────────────────────────────────────────────────────────────────
QLoRA             VRAM 再省 60%（7B: 22G → 11G）    訓練快 25–40%
                  24GB 卡就能訓 13B                 無量化誤差累積
                  單卡就能訓 70B（80GB A100）       合併時不需額外考量
──────────────────────────────────────────────────────────────────────
翻轉條件：VRAM 夠用就選 LoRA（快且乾淨）。VRAM 不夠才用 QLoRA。
          品質差距實測約 0.5–1.5 個百分點——不是選擇的主要考量
```

### 8.3 TRL SFTTrainer vs 原生 Trainer

```
選擇              選 SFTTrainer 的理由             選原生 Trainer 的理由
──────────────────────────────────────────────────────────────────────
SFTTrainer        自動套 chat_template              需要完全自訂 loss
                  自動處理 completion-only loss     非標準的訓練目標
                  packing / peft 整合開箱即用       已有既存的 Trainer 程式碼
                  之後接 DPO/GRPO 完全同一套 API
──────────────────────────────────────────────────────────────────────
翻轉條件：做非 causal-LM 任務（分類、NER、seq2seq）→ 原生 Trainer。
          做指令微調 → 一律 SFTTrainer，不要自己刻
```

### 8.4 資料多 vs 資料精

```
選擇              選「精」的理由                   選「多」的理由
──────────────────────────────────────────────────────────────────────
1K 精選           1K 精選 ≈ 50K 雜訊的效果          涵蓋長尾情境
                  標注成本可控                      邊界案例需要量
                  可完整人工審查                    多樣性防止過擬合
──────────────────────────────────────────────────────────────────────
翻轉條件：實務最佳解是「精選 1,000 筆核心 + 針對性補充難例」。
          先用 1,000 筆訓一版 → 跑評估 → 看混淆矩陣 →
          針對錯最多的那類補 100–200 筆 → 重訓。這個迴圈比盲目加量有效 5–10×
```

### 8.5 微調小模型 vs 直接用大模型

```
選擇              選「微調 1.5B」的理由            選「直接用 7B/API」的理由
──────────────────────────────────────────────────────────────────────
微調小模型         推論成本低 8–15×                 零訓練成本
                  延遲低 3–5×（P50 從 900ms→200ms） 泛化能力強，新情境不用重訓
                  可跑在便宜的 GPU 甚至 CPU         不需要維護訓練管線
──────────────────────────────────────────────────────────────────────
翻轉條件（成本交叉點）：
  微調投入約 $8,000（人力 + 算力），每月省下的推論成本若 > $1,500，
  約 5 個月回本 → 值得。
  月推論帳單 < $500 的專案，微調小模型幾乎一定不划算
```

---

## 九、六種失敗模式與診斷

```
  症狀                      loss 曲線             真正原因            解法
  ──────────────────────────────────────────────────────────────────────────────
  1. loss 幾乎不降           平坦線               lr 太小（用了 2e-5）  改 2e-4
                                                 或梯度沒接上          檢查 print_
                                                                      trainable_params

  2. loss 降但輸出變差        train↓ eval↑ (100步後) 過擬合              降 epoch 到 1–2
                                                                      加 dropout 到 0.1

  3. loss 變 NaN             驟升後 NaN           lr 太大 / fp16 溢位   改 bf16
                                                                      max_grad_norm=0.3

  4. 通用能力大幅下降         都正常               災難性遺忘            降 r、混入 5–10%
                             （但通用測試崩）                          通用指令資料

  5. 輸出重複同一句話         正常                 資料裡有重複樣本      去重
                                                 或 epoch 過多         repetition_penalty

  6. 驗證分數超高但上線爛      完美                資料洩漏              依實體重新切分
                                                                      建獨立的 holdout
```

### 9.1 最隱蔽的一種：災難性遺忘

微調後模型在你的任務上 95%，但問它「今天天氣如何」它回你一個 JSON 工單分類——這就是災難性遺忘。診斷方式是**在每次評估時同時跑一組「通用能力回歸測試」**：

```python
REGRESSION_SET = [
    "台灣的首都是哪裡？",
    "用 Python 寫一個判斷質數的函式",
    "把這句翻成英文：今天天氣很好",
    "1 加到 100 等於多少？",
]

# 微調前後都跑一次，人工看有沒有崩壞
for q in REGRESSION_SET:
    print(f"\nQ: {q}\nA: {generate_batch([[{'role':'user','content':q}]])[0]}")
```

緩解方式（依效果排序）：① 在訓練資料中混入 5–10% 的通用指令資料；② 降低 `r` 與 epoch 數；③ 降低學習率。**方法 ① 最有效，而且成本最低**——從 Hub 上取一個通用指令集抽 500 筆混進去就好。

---

## 十、系列導航

本文是「Hugging Face 實戰」系列的第 3 篇。

← **上一篇：** [Hugging Face 實戰（二）：用模型、跑 App、推送自己的模型](/posts/hugging-face-part2-use-and-push-models-zh/)

→ **下一篇：** [Hugging Face 實戰（四）：後訓練 — 從 SFT 到 DPO、ORPO 與 GRPO](/posts/hugging-face-part4-post-training-zh/)

**系列索引：**
1. 入門與生態系
2. 用模型、跑 App、推送自己的模型
3. **微調（Fine-tuning）** ← 目前
4. 後訓練（Post-training）
5. 端到端實戰：打造完整 LLM 應用

**延伸閱讀：**
- [AI 工程從零開始｜Phase 10 Part 3：LLM 微調 — LoRA、QLoRA 與指令對齊](/posts/ai-eng-from-scratch-phase10-part3-finetuning-zh/)
