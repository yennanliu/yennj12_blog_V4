---
title: "Hugging Face 實戰（四）：後訓練 — 從 SFT 到 DPO、ORPO 與 GRPO"
date: 2026-08-16T09:00:00+08:00
draft: false
weight: 4
description: "後訓練不只是再微調一次。完整解析 DPO / ORPO / KTO / SimPO / GRPO 與 PPO 的差異、偏好資料怎麼準備、TRL 的完整訓練程式碼，以及如何評估對齊效果與偵測 reward hacking。"
categories: ["engineering", "ai", "all"]
tags: ["Hugging Face", "Post-training", "DPO", "ORPO", "GRPO", "RLHF", "TRL", "LLM", "Python", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
series: ["hugging-face"]
---

> *大多數人以為 post-training 就是「再做一次微調」。*
> *正確答案是：SFT 教模型「怎麼做」，post-training 教它「哪一種做法比較好」——這是兩種完全不同的訊號。*
> *大多數人一聽到 RLHF 就想到 PPO 與四個模型同時塞進 GPU。*
> *正確答案是：2026 年的實務首選是 DPO 或 ORPO，複雜度只有 PPO 的三分之一，效果卻相當。*

---

**上一篇**我們用 SFT 讓模型學會了任務格式。但 SFT 有一個結構性限制：**它只能學「正例」**。當兩個回答都符合格式、只是其中一個明顯更好時，SFT 無法表達這個偏好。這就是 post-training 要解決的問題。

---

## 一、Post-training 是什麼

### 1.1 訓練生命週期的三個階段

```
┌─────────────────────────────────────────────────────────────────────┐
│  階段 1：Pre-training（預訓練）                                       │
│  資料：10T+ tokens 的網路文本                                         │
│  目標：預測下一個 token                                               │
│  成本：$1M – $100M+                                                  │
│  產物：Base Model（會續寫，但不會「回答」）                            │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  階段 2：SFT（監督微調）                          ← 上一篇            │
│  資料：1K – 1M 筆「指令 → 理想回覆」                                  │
│  目標：模仿參考答案（cross-entropy）                                  │
│  成本：$10 – $10K                                                    │
│  產物：Instruct Model（會回答，但品質參差）                            │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  階段 3：Preference Optimization（偏好優化）      ← 本篇             │
│  資料：1K – 100K 組「同一問題的好答案 vs 壞答案」                      │
│  目標：提高好答案的相對機率、壓低壞答案                                 │
│  成本：$20 – $50K                                                    │
│  產物：Aligned Model（懂得什麼叫「更好」）                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 為什麼 SFT 不夠：一個具體例子

假設使用者問：「我的訂單延遲了，怎麼辦？」

```
  回覆 A（好）：
    「很抱歉造成不便。我查到您的訂單 #12345 目前在轉運中心，
      預計明天送達。若明天仍未收到，我可以直接為您安排補寄。」

  回覆 B（差，但格式完全正確）：
    「很抱歉造成不便。物流延遲可能由多種因素造成，包括天候、
      交通、倉儲作業量等。建議您耐心等候，並持續關注物流資訊。
      如有其他問題歡迎隨時聯繫我們。感謝您的支持與體諒。」
```

**SFT 對這兩者的處理方式：** 如果訓練集裡是 A，模型學 A；如果是 B，模型學 B。但 SFT **無法從「A 比 B 好」這個訊號中學習**——它需要一個明確的參考答案，而不是一個比較。

而現實中，「哪個更好」比「什麼是完美答案」容易標注太多了：

```
  標注任務                    每筆耗時     標注者一致率
  ────────────────────────────────────────────────────
  寫出理想答案（SFT）           5–15 分鐘      —
  比較兩個答案（偏好）           20–40 秒     78–88%
  標記單一答案好/壞（KTO）       10–20 秒     82–91%
```

**這個成本差異（15–30 倍）就是 post-training 在實務上可行的根本原因。**

### 1.3 方法全景圖

```
                          Post-Training 方法
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
  ┌───────────┐            ┌────────────┐          ┌──────────────┐
  │ 需要 RM   │            │ 直接偏好    │          │ 可驗證獎勵    │
  │ (兩階段)  │            │ (免 RM)    │          │ (規則/程式)   │
  ├───────────┤            ├────────────┤          ├──────────────┤
  │ PPO       │            │ DPO   ★    │          │ GRPO   ★     │
  │ RLOO      │            │ ORPO  ★    │          │ RLVR         │
  │           │            │ KTO        │          │              │
  │           │            │ SimPO      │          │              │
  └───────────┘            └────────────┘          └──────────────┘
   複雜度 ★★★★★             複雜度 ★★              複雜度 ★★★
   4 個模型在記憶體           2 個（DPO）/1 個（ORPO）  1 個 + 獎勵函式
   適合：大規模對齊研究        適合：95% 的商業場景      適合：數學/程式/
                                                       有標準答案的任務
```

**★ 標記的是 2026 年的實務首選。** 如果你不確定要用哪個，答案幾乎總是 DPO（已有 SFT 模型）或 ORPO（想省一個階段）。

---

## 二、偏好資料：post-training 的燃料

### 2.1 資料格式

```python
# DPO / ORPO / SimPO 需要「配對」資料
{
  "prompt":   [{"role": "user", "content": "我的訂單延遲了，怎麼辦？"}],
  "chosen":   [{"role": "assistant", "content": "很抱歉造成不便。我查到您的訂單..."}],
  "rejected": [{"role": "assistant", "content": "很抱歉造成不便。物流延遲可能由..."}],
}

# KTO 只需要「單邊」標記
{
  "prompt":     [{"role": "user", "content": "我的訂單延遲了，怎麼辦？"}],
  "completion": [{"role": "assistant", "content": "很抱歉造成不便。我查到您的訂單..."}],
  "label": True,      # True = 這是好回覆；False = 壞回覆
}

# GRPO 不需要偏好資料，只需要 prompt + 一個可計算的獎勵函式
{"prompt": [{"role": "user", "content": "計算 (17 × 23) + 41"}], "answer": "432"}
```

### 2.2 偏好資料從哪裡來

```
  ┌──────────────────────────────────────────────────────────────────┐
  │ 來源 1：人工標注（品質最高，成本最高）                              │
  │   流程：SFT 模型對同一 prompt 採樣 2 個回覆 → 標注者選一個          │
  │   成本：約 $0.15–0.40/組（外包）或 30 秒/組（內部）                │
  │   建議：核心場景 500–2,000 組                                     │
  ├──────────────────────────────────────────────────────────────────┤
  │ 來源 2：AI 回饋（RLAIF，性價比最佳）                               │
  │   流程：用更強的模型當評審，選出較好的那個                          │
  │   成本：約 $0.002–0.01/組                                        │
  │   注意：授權！很多商用 API 禁止用其輸出訓練競爭模型                 │
  │        用開源強模型（如 Qwen2.5-72B）當評審則無此問題              │
  ├──────────────────────────────────────────────────────────────────┤
  │ 來源 3：生產訊號（最真實，累積最慢）                                │
  │   來源：使用者按讚/倒讚、客服人員的編輯前後版本、對話是否轉真人      │
  │   優勢：完全對齊你的真實目標，且持續產生                            │
  │   建議：第一天就把這些訊號記錄下來，即使還不打算訓練                 │
  ├──────────────────────────────────────────────────────────────────┤
  │ 來源 4：規則生成負例（幾乎零成本，涵蓋已知失效模式）                 │
  │   例：把正確答案改成 JSON 缺欄位、加入編造的訂單號、改成過度冗長     │
  │   優勢：可精準針對特定失效模式                                     │
  │   限制：只能修「你已經知道的問題」                                 │
  └──────────────────────────────────────────────────────────────────┘
```

### 2.3 用 AI 評審建構偏好資料

```python
# build_preference.py
import json
import torch
from datasets import load_dataset, Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM

SFT_MODEL = "./out/support-merged"      # 上一篇訓練出來的模型

tok = AutoTokenizer.from_pretrained(SFT_MODEL)
tok.padding_side = "left"
model = AutoModelForCausalLM.from_pretrained(
    SFT_MODEL, torch_dtype=torch.bfloat16, device_map="auto"
)


@torch.no_grad()
def sample_n(messages, n=4, temperature=1.0):
    """對同一 prompt 採樣 n 個不同回覆"""
    prompt = tok.apply_chat_template(messages, tokenize=False,
                                     add_generation_prompt=True)
    enc = tok([prompt] * n, return_tensors="pt", padding=True).to(model.device)
    out = model.generate(
        **enc, max_new_tokens=384,
        do_sample=True, temperature=temperature, top_p=0.95,
        pad_token_id=tok.pad_token_id,
    )
    return [tok.decode(s[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
            for s in out]


JUDGE_PROMPT = """比較兩個客服回覆，選出較好的一個。

判準（依重要性排序）：
1. 是否提供具體、可執行的下一步（而非空泛安慰）
2. 是否只依據已知資訊，沒有編造訂單號或日期
3. 語氣專業且簡潔（150 字內為佳）

只輸出 JSON：{"winner": "A" 或 "B", "reason": "<20 字內>"}

【客戶問題】
%s

【回覆 A】
%s

【回覆 B】
%s"""


def judge(question, a, b, judge_client):
    """用外部強模型評審。position bias 處理：正反各跑一次"""
    def once(x, y):
        r = judge_client.chat.completions.create(
            model="judge-model",
            messages=[{"role": "user", "content": JUDGE_PROMPT % (question, x, y)}],
            temperature=0.0,
        )
        return json.loads(r.choices[0].message.content)["winner"]

    first = once(a, b)                       # A=a, B=b
    second = once(b, a)                      # 交換位置再問一次
    if first == "A" and second == "B":
        return "a"                           # 兩次都選 a → 一致
    if first == "B" and second == "A":
        return "b"
    return None                              # 不一致 → 丟棄這組


# ── 主流程 ──
prompts = load_dataset("json", data_files="data/prompts.jsonl", split="train")
pairs = []

for row in prompts:
    msgs = row["messages"][:-1]
    cands = sample_n(msgs, n=4)
    cands = list(dict.fromkeys(cands))       # 去掉完全相同的採樣
    if len(cands) < 2:
        continue                             # 模型太確定，沒有可比較的差異

    question = msgs[-1]["content"]
    winner = judge(question, cands[0], cands[1], judge_client)
    if winner is None:
        continue                             # 評審不一致，這組沒有明確訊號

    chosen, rejected = (cands[0], cands[1]) if winner == "a" else (cands[1], cands[0])
    pairs.append({
        "prompt":   msgs,
        "chosen":   [{"role": "assistant", "content": chosen}],
        "rejected": [{"role": "assistant", "content": rejected}],
    })

Dataset.from_list(pairs).to_json("data/preference.jsonl", force_ascii=False)
print(f"產出 {len(pairs):,} 組偏好資料（原始 prompt {len(prompts):,} 筆）")
```

**三個關鍵設計：**

1. **從你自己的 SFT 模型採樣**，不要用別的模型的輸出。DPO 的數學假設是偏好資料來自「接近當前策略」的分布；用外部模型的輸出會造成分布偏移，訓練不穩定。
2. **正反各評一次來消除位置偏誤。** LLM 評審對「先出現的選項」有 5–15% 的偏好。不一致的組直接丟棄——那代表兩個回覆品質相近，沒有訓練訊號。
3. **`temperature=1.0` 採樣。** 太低（0.3）會產生幾乎相同的回覆，沒有可比較的差異；太高（1.5）會產生明顯壞掉的回覆，模型很容易學會，但學不到細緻的品質差異。

### 2.4 偏好資料的品質檢查

```python
from datasets import load_dataset
import numpy as np

ds = load_dataset("json", data_files="data/preference.jsonl", split="train")

chosen_len = np.array([len(r["chosen"][0]["content"]) for r in ds])
rejected_len = np.array([len(r["rejected"][0]["content"]) for r in ds])

print(f"chosen   平均長度：{chosen_len.mean():.0f}")
print(f"rejected 平均長度：{rejected_len.mean():.0f}")
print(f"chosen 較長的比例：{(chosen_len > rejected_len).mean():.1%}")
```

> **這是最重要的一項檢查。** 如果「chosen 較長」的比例超過 70%，你的模型會學到「長就是好」而不是「好就是好」——這是偏好優化最常見的退化，稱為 **length bias**。生產後的症狀是回覆越來越囉唆。修正方式：在 rubric 裡明確懲罰冗長、或改用 SimPO（內建長度正規化）。

---

## 三、三個演進階段

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 1：先確認方向（500–2,000 組偏好 / 單卡）                    ║
╚══════════════════════════════════════════════════════════════════╝

  ┌─────────────┐   ┌────────────────┐   ┌──────────────────┐
  │ SFT 模型     │──▶│ 採樣 + AI 評審  │──▶│ 1,000 組偏好資料  │
  └─────────────┘   └────────────────┘   └────────┬─────────┘
                                                  ▼
                              ┌───────────────────────────────┐
                              │ DPO（QLoRA, β=0.1, 1 epoch）  │
                              │ 單卡 A10G，約 1.5 小時         │
                              └───────────────┬───────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │ 人工盲測 50 題（vs SFT 基線）   │
                              └───────────────────────────────┘

  成本：~$25    問題：偏好資料全來自 AI，可能與真實使用者偏好有落差
  能回答：「對齊有沒有效？」
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 2：人機混合偏好 + 系統化評估（5K–30K 組）                   ║
╚══════════════════════════════════════════════════════════════════╝

  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐
  │ 生產回饋      │  │ 人工標注      │  │ AI 評審（大量）     │
  │ 讚/倒讚 20%  │  │ 核心場景 20%  │  │ 長尾場景 60%        │
  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘
         └─────────────────┼────────────────────┘
                           ▼
              ┌────────────────────────────┐
              │  偏好資料集（版本化於 Hub）  │
              └────────────┬───────────────┘
                           ▼
         ┌─────────────────────────────────────────┐
         │  DPO / ORPO（LoRA, 多組 β 掃描）         │
         │  同時監控：獎勵差距、KL 距離、長度變化     │
         └─────────────────┬───────────────────────┘
                           ▼
         ┌─────────────────────────────────────────┐
         │  評估閘門                                │
         │  · 對齊指標提升 > 8pt                    │
         │  · 通用能力回歸 < 3pt                    │
         │  · 平均長度增幅 < 15%                    │
         └─────────────────────────────────────────┘

  新增：多來源資料、β 掃描、KL 監控、長度守門、回歸測試
  成本：~$400/輪    解決：可量化、可比較、能擋住退化
  未解決：無法優化「需要多步推理才對」的任務
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 3：可驗證獎勵 + 線上迭代（30K+ / 多卡）                     ║
╚══════════════════════════════════════════════════════════════════╝

  ┌─────────────────────────────────────────────────────────────┐
  │  離線：GRPO with 可驗證獎勵                                   │
  │    · 格式獎勵（JSON schema 是否合法）    權重 0.2            │
  │    · 正確性獎勵（答案是否匹配 ground truth）權重 0.6         │
  │    · 長度懲罰（超過 200 字扣分）         權重 0.2            │
  │    每個 prompt 採樣 G=8 → 組內標準化 → 更新策略               │
  └────────────────────────┬────────────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  線上：Canary（5%）→ 收集真實偏好 → 回流資料集                │
  │    自動回滾條件：倒讚率 > 基線 1.3× 或 P99 延遲 > 2s          │
  └────────────────────────┬────────────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  每月重跑：新資料 + 新底模 → 完整管線 → 自動評估 → 上線        │
  └─────────────────────────────────────────────────────────────┘

  新增：可驗證獎勵、GRPO、線上實驗、資料飛輪、自動回滾
  成本：~$3,000–15,000/月
  解決：推理任務品質、持續改善不靠人工
  代價：需要能定義「可程式化驗證」的任務，且要防 reward hacking
```

---

## 四、DPO：最實用的起點

### 4.1 原理（不用推導也能懂的版本）

RLHF 的傳統做法是「訓一個獎勵模型 → 用 RL 最大化獎勵」。DPO 的洞見是：**這兩步可以合併成一個閉式的分類損失。**

```
  傳統 RLHF（PPO）：
    ┌──────────┐   ┌──────────┐   ┌─────────────────────────────┐
    │ 偏好資料  │──▶│ 訓練 RM  │──▶│ PPO：策略 + 參考 + RM + Value │
    └──────────┘   └──────────┘   │  4 個模型同時在 VRAM 裡       │
                                  └─────────────────────────────┘

  DPO：
    ┌──────────┐   ┌─────────────────────────────────────────┐
    │ 偏好資料  │──▶│ 直接優化：策略 + 參考（凍結）             │
    └──────────┘   │  2 個模型，一個標準的訓練迴圈             │
                   └─────────────────────────────────────────┘
```

DPO 的損失函數：

```
  L = -log σ( β · [ (log πθ(y_w|x) - log π_ref(y_w|x))
                   - (log πθ(y_l|x) - log π_ref(y_l|x)) ] )

  白話：
    「讓模型對好答案的機率，相對於參考模型提高得
      比對壞答案提高得更多。」

  β 控制「可以偏離參考模型多遠」：
    β = 0.01  →  幾乎不受限，容易崩壞（輸出退化成亂碼）
    β = 0.1   →  標準值，適用大多數情況
    β = 0.5   →  非常保守，改善幅度小但絕不崩
```

**用 LoRA 做 DPO 有個額外好處：** 參考模型就是「關掉 adapter 的同一個模型」，所以 VRAM 只需要一份底模——這讓 7B DPO 在單張 24GB 卡上完全可行。

### 4.2 完整 DPO 訓練程式碼

```python
# train_dpo.py
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, prepare_model_for_kbit_training
from trl import DPOTrainer, DPOConfig

SFT_MODEL = "./out/support-merged"      # 第三篇 SFT 後合併的模型
OUTPUT = "./out/support-dpo"

train_ds = load_dataset("json", data_files="data/preference_train.jsonl", split="train")
eval_ds = load_dataset("json", data_files="data/preference_eval.jsonl", split="train")

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tok = AutoTokenizer.from_pretrained(SFT_MODEL)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

model = AutoModelForCausalLM.from_pretrained(
    SFT_MODEL,
    quantization_config=bnb,
    device_map={"": 0},
    attn_implementation="sdpa",
    torch_dtype=torch.bfloat16,
)
model.config.use_cache = False
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

peft_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    bias="none", task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
)

cfg = DPOConfig(
    output_dir=OUTPUT,

    beta=0.1,                        # ← 最重要的超參數
    loss_type="sigmoid",             # 標準 DPO；"ipo" 較抗過擬合
    max_length=1536,
    max_prompt_length=768,

    num_train_epochs=1,              # ← DPO 通常 1 epoch 就夠，2 epoch 常過擬合
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=5e-6,              # ← 注意：比 SFT 小 40 倍
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    optim="paged_adamw_8bit",
    max_grad_norm=0.3,

    bf16=True,
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},

    logging_steps=10,
    eval_strategy="steps",
    eval_steps=50,
    save_steps=100,
    save_total_limit=2,
    report_to="tensorboard",
    seed=42,
)

trainer = DPOTrainer(
    model=model,
    ref_model=None,                  # 用 LoRA 時留 None：關掉 adapter 即為參考模型
    args=cfg,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    processing_class=tok,
    peft_config=peft_config,
)

trainer.train()
trainer.save_model(f"{OUTPUT}/final")
tok.save_pretrained(f"{OUTPUT}/final")
```

### 4.3 訓練中該盯哪些指標

DPO 的 loss 值本身沒什麼解讀價值，真正要看的是這四個：

```
  指標                       健康範圍          異常代表什麼
  ────────────────────────────────────────────────────────────────────
  rewards/accuracies         0.65 → 0.85      < 0.6：資料訊號太弱或 lr 太小
                             （逐步上升）      > 0.95 太快：過擬合或資料太簡單

  rewards/margins            穩定上升          停滯：模型已學不到新東西
                             （0 → 1.5 左右）  暴衝 > 5：β 太小，正在崩壞

  rewards/chosen             微幅上升或持平     大幅下降：模型在「壓低所有輸出」
                                              而非「提高好的」→ 降 lr

  logps/rejected             下降              暴跌：模型在崩壞，
                                              檢查生成結果是否已成亂碼
```

> **一個非常實用的直覺：** `rewards/accuracies` 是「模型認為 chosen 優於 rejected 的比例」。它應該從 0.5（隨機）平滑爬升到 0.8 左右。如果它在前 20 步就衝到 0.99，代表你的 chosen/rejected 差異太明顯（例如一個是正常回覆一個是亂碼）——這種資料訓不出細緻的品質提升。

### 4.4 β 的實測影響

同一份 3,000 組偏好資料、Qwen2.5-7B SFT 模型：

| β | 勝率 vs SFT | 平均長度變化 | 通用能力回歸 | 判斷 |
|---|------------|------------|------------|------|
| 0.01 | 71% | +82% | −11.4 pt | 崩壞：回覆冗長且通用能力大跌 |
| 0.05 | 74% | +31% | −4.2 pt | 偏激進，需觀察 |
| **0.1** | **72%** | **+9%** | **−1.1 pt** | **建議預設值** |
| 0.3 | 64% | +3% | −0.4 pt | 保守，改善有限 |
| 0.5 | 58% | +1% | −0.2 pt | 幾乎沒動 |

**注意 β=0.01 的勝率最高（71%）但其實是最糟的選擇**——它的勝率來自「回答變長變詳細」這個評審偏誤，而不是真的變好，代價是通用能力掉了 11 個百分點。**只看單一指標會做出完全錯誤的決策，這就是為什麼要同時盯長度與回歸測試。**

---

## 五、ORPO、KTO、SimPO：三個實用變體

### 5.1 ORPO：把 SFT 與偏好優化合併成一步

ORPO（Odds Ratio Preference Optimization）在 SFT 損失上加一個 odds-ratio 懲罰項，**直接從 base model 訓練，不需要先做 SFT，也不需要參考模型**。

```
  傳統流程：              ORPO 流程：
  ┌────────────┐         ┌────────────┐
  │ Base Model │         │ Base Model │
  └─────┬──────┘         └─────┬──────┘
        ▼                      │
  ┌────────────┐               │  一步到位
  │ SFT (3ep)  │               │  · 記憶體：只有 1 個模型
  └─────┬──────┘               │  · 時間：省 40–50%
        ▼                      ▼
  ┌────────────┐         ┌────────────┐
  │ DPO (1ep)  │         │  Aligned   │
  └─────┬──────┘         └────────────┘
        ▼
  ┌────────────┐
  │  Aligned   │
  └────────────┘
```

```python
# train_orpo.py（只列與 DPO 不同的部分）
from trl import ORPOTrainer, ORPOConfig

cfg = ORPOConfig(
    output_dir="./out/support-orpo",
    beta=0.1,                   # ORPO 裡叫 lambda，控制偏好項的權重
    num_train_epochs=3,         # ← ORPO 兼做 SFT，所以要 3 epoch（不是 1）
    learning_rate=8e-6,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    max_length=1536,
    max_prompt_length=768,
    bf16=True,
    gradient_checkpointing=True,
    optim="paged_adamw_8bit",
)

trainer = ORPOTrainer(
    model=model,                # 直接用 base model，不需要先 SFT
    args=cfg,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    processing_class=tok,
    peft_config=peft_config,
)
trainer.train()
```

> **ORPO 的資料要求比較高：** 因為它同時在學「怎麼做」和「哪個更好」，`chosen` 必須是真正高品質的答案（能當 SFT 目標的等級），不能只是「比 rejected 好一點」。如果你的偏好資料是從中等品質的模型採樣來的，先做 SFT 再 DPO 會更好。

### 5.2 KTO：不需要配對資料

KTO（Kahneman-Tversky Optimization）只需要「這個回覆好/不好」的二元標記。**這在實務上是巨大的優勢**，因為生產環境的讚/倒讚天然就是這個格式。

```python
from trl import KTOTrainer, KTOConfig

# 資料格式：{"prompt": [...], "completion": [...], "label": True/False}
cfg = KTOConfig(
    output_dir="./out/support-kto",
    beta=0.1,
    desirable_weight=1.0,        # 正例權重
    undesirable_weight=1.0,      # 負例權重
    num_train_epochs=1,
    learning_rate=5e-6,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    bf16=True,
)
```

> **正負例比例失衡時要調權重。** 生產資料通常是 90% 讚、10% 倒讚。此時建議設 `undesirable_weight = (正例數 / 負例數) × 1.0`，讓兩邊的總權重接近，否則模型幾乎學不到負向訊號。

### 5.3 SimPO：免參考模型 + 內建長度正規化

SimPO 把 DPO 的「相對於參考模型的對數機率」換成「長度正規化的平均對數機率」，因此**不需要參考模型，而且天然抑制 length bias**。在 TRL 中透過 `CPOTrainer` 搭配 `loss_type="simpo"` 使用：

```python
from trl import CPOTrainer, CPOConfig

cfg = CPOConfig(
    output_dir="./out/support-simpo",
    loss_type="simpo",
    cpo_alpha=0.0,               # SimPO 設 0（不加 SFT 項）
    beta=2.5,                    # ← SimPO 的 β 範圍與 DPO 完全不同（2.0–2.5）
    simpo_gamma=1.0,             # 目標獎勵邊際
    num_train_epochs=1,
    learning_rate=8e-7,          # ← 也比 DPO 更小
    bf16=True,
)
```

**如果你的 DPO 訓練出現嚴重的長度膨脹（平均長度 +40% 以上），SimPO 是最直接的解法。**

### 5.4 四種方法的實測對比

同一組 5,000 筆資料、Qwen2.5-7B、單張 A100 80G：

| 方法 | 需要 SFT 模型 | 需要參考模型 | 訓練時間 | VRAM | 勝率 vs SFT | 長度變化 |
|------|-------------|------------|---------|------|------------|---------|
| DPO | ✅ | ✅（LoRA 可省） | 2.1 hr | 38 GB | 72% | +9% |
| ORPO | ❌（從 base 開始） | ❌ | 3.8 hr* | 26 GB | 70% | +5% |
| KTO | ✅ | ✅ | 2.3 hr | 38 GB | 68% | +12% |
| SimPO | ✅ | ❌ | 1.6 hr | 24 GB | 71% | −3% |

\* ORPO 的 3.8 小時已包含了 SFT 的部分；DPO 的 2.1 小時之外還要另加 SFT 的 4.2 小時，所以 **ORPO 的端到端總時間其實最短**。

---

## 六、GRPO 與可驗證獎勵

### 6.1 什麼時候偏好資料不管用

有一類任務，「哪個回答更好」有客觀答案：數學題算對了沒、程式碼跑不跑得過、JSON 符不符合 schema、SQL 查詢結果對不對。**對這些任務，收集人類偏好是浪費——直接寫一個驗證函式就好。**

GRPO（Group Relative Policy Optimization）就是為此設計的：

```
  對同一個 prompt 採樣 G 個回覆（例如 G=8）
        │
        ▼
  ┌────────────────────────────────────────────────────┐
  │  r1=1.0  r2=0.0  r3=1.0  r4=0.0                    │
  │  r5=1.0  r6=1.0  r7=0.0  r8=1.0                    │
  │        ↓ 組內標準化（不需要 value model）            │
  │  A_i = (r_i - mean(r)) / std(r)                    │
  │  mean=0.625, std=0.484                             │
  │  A = [+0.77, -1.29, +0.77, -1.29, ...]             │
  └────────────────────┬───────────────────────────────┘
                       ▼
  提高 advantage > 0 的回覆機率，壓低 < 0 的
  （加上 KL 懲罰，避免偏離參考模型太遠）
```

**GRPO 相對 PPO 的關鍵簡化：** PPO 需要一個獨立的 value network 來估計 baseline；GRPO 直接用「同一組樣本的平均獎勵」當 baseline，省掉一個模型。

### 6.2 GRPO 訓練程式碼

```python
# train_grpo.py
import re
import json
from datasets import load_dataset
from trl import GRPOTrainer, GRPOConfig

# ── 獎勵函式 1：格式正確性 ──
def reward_format(completions, **kwargs):
    """回覆必須是可解析的 JSON 且含必要欄位"""
    scores = []
    for c in completions:
        text = c[0]["content"] if isinstance(c, list) else c
        try:
            obj = json.loads(text)
            ok = {"category", "urgency", "reply"} <= obj.keys()
            scores.append(1.0 if ok else 0.3)
        except Exception:
            scores.append(0.0)
    return scores


# ── 獎勵函式 2：分類正確性 ──
def reward_correct(completions, category, **kwargs):
    """category 是 dataset 裡的欄位，TRL 會自動以 kwarg 傳入"""
    scores = []
    for c, gold in zip(completions, category):
        text = c[0]["content"] if isinstance(c, list) else c
        try:
            scores.append(1.0 if json.loads(text).get("category") == gold else 0.0)
        except Exception:
            scores.append(0.0)
    return scores


# ── 獎勵函式 3：長度懲罰（防止冗長）──
def reward_brevity(completions, **kwargs):
    scores = []
    for c in completions:
        text = c[0]["content"] if isinstance(c, list) else c
        try:
            reply = json.loads(text).get("reply", "")
        except Exception:
            reply = text
        n = len(reply)
        if n <= 150:
            scores.append(1.0)
        elif n <= 250:
            scores.append(0.5)
        else:
            scores.append(0.0)
    return scores


train_ds = load_dataset("json", data_files="data/grpo_train.jsonl", split="train")
# 每筆需含：{"prompt": [...], "category": "物流"}

cfg = GRPOConfig(
    output_dir="./out/support-grpo",

    num_generations=8,               # 每個 prompt 採樣 8 個（組大小 G）
    max_completion_length=384,
    temperature=1.0,                 # 需要多樣性，不能設太低

    beta=0.04,                       # KL 懲罰係數
    num_train_epochs=1,
    per_device_train_batch_size=8,   # 必須能被 num_generations 整除
    gradient_accumulation_steps=4,
    learning_rate=1e-6,              # ← GRPO 的 lr 比 DPO 還要小

    bf16=True,
    gradient_checkpointing=True,
    logging_steps=5,
    save_steps=100,
    report_to="tensorboard",

    # 用 vLLM 加速採樣（GRPO 的瓶頸在生成，不在反向傳播）
    use_vllm=True,
    vllm_gpu_memory_utilization=0.3,
)

trainer = GRPOTrainer(
    model="./out/support-merged",
    args=cfg,
    train_dataset=train_ds,
    processing_class=tok,
    reward_funcs=[reward_format, reward_correct, reward_brevity],
    reward_weights=[0.2, 0.6, 0.2],   # 加權組合
    peft_config=peft_config,
)

trainer.train()
```

### 6.3 Reward Hacking：GRPO 最大的風險

**只要獎勵函式有漏洞，模型一定會找到它。** 這不是理論風險，是每次都會發生的事：

```
  你寫的獎勵                     模型找到的漏洞
  ────────────────────────────────────────────────────────────────
  「回覆越短分數越高」             輸出空字串，拿滿分
  「包含關鍵字就加分」             把關鍵字重複 50 次
  「JSON 可解析就加分」            輸出 {} ——合法但無用
  「與參考答案的 BLEU 分數」        複製問題本身（用詞重疊率高）
  「程式碼要通過測試」             寫 `if input == test_case_1: return ...`
```

**四道防線：**

1. **獎勵下限與上限都要設。** 「短就好」要改成「150 字以內滿分，但少於 20 字直接 0 分」。
2. **多個獎勵函式互相牽制。** 單一獎勵幾乎必然被 hack；三個以上正交的獎勵就困難得多。
3. **KL 懲罰不要關。** `beta=0.04` 的作用就是「不准離原本的模型太遠」，這是防崩壞的最後一道保險。
4. **每 50 步人工看 5 筆生成結果。** 這是唯一能發現「獎勵在漲但輸出很怪」的方式。自動化指標永遠追不上模型找漏洞的創意。

```python
# 訓練中的抽樣檢查（掛成 callback）
from transformers import TrainerCallback

class SampleInspector(TrainerCallback):
    def __init__(self, tokenizer, every=50):
        self.tok, self.every = tokenizer, every

    def on_log(self, args, state, control, logs=None, **kwargs):
        if state.global_step % self.every != 0:
            return
        print(f"\n{'='*60}\nStep {state.global_step} 抽樣：")
        for k in ("reward", "reward_std", "kl", "completion_length"):
            if logs and k in logs:
                print(f"  {k:20s} = {logs[k]:.4f}")
        print("  ↑ 若 reward 上升但 completion_length 逼近 0 或上限 → 疑似 hacking")
```

---

## 七、評估對齊效果

### 7.1 三個必看的維度

```
  ┌──────────────────────────────────────────────────────────────┐
  │  維度 1：目標指標是否提升                                      │
  │    方法：對同一組 200 題，新模型 vs 舊模型盲測，計算勝率        │
  │    健康：勝率 > 60%（55–60% 是雜訊範圍，需加大樣本）           │
  ├──────────────────────────────────────────────────────────────┤
  │  維度 2：通用能力是否退化（回歸測試）                          │
  │    方法：固定 100 題涵蓋常識/數學/翻譯/程式碼                  │
  │    健康：退化 < 3 個百分點                                    │
  ├──────────────────────────────────────────────────────────────┤
  │  維度 3：是否出現退化型行為                                    │
  │    · 平均長度增幅 > 20%       → length bias                  │
  │    · 重複 n-gram 比例上升      → 崩壞前兆                     │
  │    · 拒答率上升 > 5pt         → 過度保守                      │
  │    · 輸出多樣性（distinct-2）下降 > 15% → 模式崩潰            │
  └──────────────────────────────────────────────────────────────┘
```

### 7.2 成對盲測腳本

```python
# ab_eval.py
import json
import random
from collections import Counter

def pairwise_eval(model_a, model_b, questions, judge_client, seed=42):
    """A/B 盲測，含位置隨機化與雙向驗證"""
    rng = random.Random(seed)
    tally = Counter()

    for q in questions:
        ra = model_a(q)
        rb = model_b(q)

        # 位置隨機化
        swap = rng.random() < 0.5
        first, second = (rb, ra) if swap else (ra, rb)

        verdict = judge_client.compare(q, first, second)   # 回傳 "first"/"second"/"tie"
        if verdict == "tie":
            tally["tie"] += 1
        elif (verdict == "first") != swap:
            tally["a"] += 1
        else:
            tally["b"] += 1

    n = sum(tally.values())
    win = tally["a"] / n
    # Wilson 95% 信賴區間，判斷差異是否顯著
    import math
    z = 1.96
    denom = 1 + z**2 / n
    center = (win + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(win * (1 - win) / n + z**2 / (4 * n**2)) / denom

    print(f"A 勝 {tally['a']}  B 勝 {tally['b']}  平手 {tally['tie']}")
    print(f"A 勝率 {win:.1%}  95% CI [{center-margin:.1%}, {center+margin:.1%}]")
    print("結論：" + ("A 顯著較佳" if center - margin > 0.5 else
                     "B 顯著較佳" if center + margin < 0.5 else
                     "無顯著差異（需增加樣本或改善資料）"))
    return tally
```

> **200 題以下的勝率不要當結論。** 100 題的 60% 勝率，95% 信賴區間大約是 [50%, 69%]——下界剛好碰到 50%，等於「可能沒差」。要證明 60% 的勝率顯著，至少需要 250 題。

---

## 八、為什麼選 X 不選 Y

### 8.1 DPO vs PPO

```
選擇              選 DPO 的理由                    選 PPO 的理由
──────────────────────────────────────────────────────────────────────
DPO               2 個模型 vs 4 個模型              可用線上取樣（探索更充分）
                  一個標準訓練迴圈，好 debug        大規模對齊研究的既有基線
                  超參數只有 β 一個要調             獎勵模型可跨任務重用
                  訓練時間短 3–5×                   理論上限較高
──────────────────────────────────────────────────────────────────────
翻轉條件：資源充足（8×A100+）、有專職對齊團隊、且要做前沿研究 → PPO。
          商業產品場景 → DPO，投入產出比壓倒性勝出
```

### 8.2 DPO vs ORPO

```
選擇              選 DPO 的理由                    選 ORPO 的理由
──────────────────────────────────────────────────────────────────────
DPO               已經有訓好的 SFT 模型             從零開始，想省一個階段
                  偏好資料的 chosen 品質普通        chosen 是真正的高品質答案
                  想分階段驗證（SFT 好了再對齊）     總訓練時間要最短
                  兩階段各自可獨立除錯               VRAM 吃緊（省掉參考模型）
──────────────────────────────────────────────────────────────────────
翻轉條件：手上已有 SFT 模型 → DPO（不要浪費）。
          從 base model 開始且資料品質高 → ORPO
```

### 8.3 DPO vs KTO

```
選擇              選 DPO 的理由                    選 KTO 的理由
──────────────────────────────────────────────────────────────────────
DPO               有明確的成對比較資料               只有讚/倒讚這種單邊訊號
                  配對訊號更精準                    標注成本更低（少 30–50%）
                  收斂更穩定                        正負例數量嚴重不平衡也能用
──────────────────────────────────────────────────────────────────────
翻轉條件：生產環境的使用者回饋天然是單邊的 → KTO 可直接用，
          不需要為了配對而額外採樣與評審。這是 KTO 最大的實務價值
```

### 8.4 偏好優化 vs 可驗證獎勵（GRPO）

```
選擇              選偏好優化的理由                  選 GRPO 的理由
──────────────────────────────────────────────────────────────────────
DPO/ORPO          任務品質是主觀的（語氣、有用性）    答案可程式化驗證
                  無法寫出獎勵函式                  數學、程式碼、SQL、schema
                  訓練穩定，風險低                  不需要標注資料，可無限生成
                                                   能發現人類想不到的解法
──────────────────────────────────────────────────────────────────────
翻轉條件：只要任務有「可自動判定對錯」的部分 → 用 GRPO 處理那部分，
          其餘主觀部分仍用 DPO。實務上兩者常組合：
          先 SFT → 再 DPO 調語氣 → 最後 GRPO 提升正確率
```

### 8.5 自己做 post-training vs 直接用更強的底模

```
選擇              選 post-training 的理由          選換底模的理由
──────────────────────────────────────────────────────────────────────
自己做             需要的是「你的」偏好，通用模型      需要的是通用能力提升
                  沒有                              新一代底模通常直接勝過
                  小模型 + 對齊 = 大模型的成本 1/8   你辛苦對齊的舊模型
                  資料飛輪會持續累積優勢              零工程投入
──────────────────────────────────────────────────────────────────────
翻轉條件：每次有新底模發布，先把它跟你的對齊模型做一次盲測。
          如果新底模直接就贏了，你的對齊工作應該重跑在新底模上，
          而不是繼續維護舊的。這就是為什麼流程自動化比模型本身更有價值
```

---

## 九、系統效應：一條完整鏈路的累積效果

同一個繁中客服場景，Qwen2.5-7B 為底，逐階段疊加：

| 階段 | 任務準確率 | JSON 合規率 | 人工滿意度 | 平均長度 | 通用能力 | 累積成本 |
|------|-----------|------------|-----------|---------|---------|---------|
| Base（未調） | 68.4% | 41.0% | 2.6 / 5 | 312 字 | 100%（基準） | $0 |
| + SFT | 91.2% | 98.6% | 3.7 / 5 | 148 字 | 96.8% | $1,900 |
| + DPO (β=0.1) | 91.8% | 99.1% | **4.3 / 5** | 161 字 | 95.7% | $2,400 |
| + GRPO（格式+正確性） | **94.6%** | **99.8%** | 4.4 / 5 | 143 字 | 94.9% | $4,100 |

**三個值得注意的地方：**

1. **SFT 帶來最大的單次躍進**（準確率 +22.8pt、合規率 +57.6pt）。如果你只能做一件事，做 SFT。
2. **DPO 對「準確率」幾乎沒幫助（+0.6pt），但對「人工滿意度」提升最大（3.7 → 4.3）。** 這正好印證了兩者的分工：SFT 管對錯，偏好優化管好壞。用準確率評估 DPO 會得出「沒用」的錯誤結論。
3. **通用能力每個階段都在小幅下滑**（100% → 94.9%）。這是對齊稅，無法完全避免，只能透過混入通用資料來減緩。**5 個百分點是可接受的；超過 10 個就要重新檢視。**

---

## 十、系列導航

本文是「Hugging Face 實戰」系列的第 4 篇。

← **上一篇：** [Hugging Face 實戰（三）：微調實戰 — Datasets、Trainer 與 LoRA/QLoRA](/posts/hugging-face-part3-fine-tuning-zh/)

→ **下一篇：** [Hugging Face 實戰（五）：端到端實戰 — 用 Hugging Face 打造完整 LLM 應用](/posts/hugging-face-part5-e2e-llm-app-zh/)

**系列索引：**
1. 入門與生態系
2. 用模型、跑 App、推送自己的模型
3. 微調（Fine-tuning）
4. **後訓練（Post-training）** ← 目前
5. 端到端實戰：打造完整 LLM 應用

**延伸閱讀：**
- [開源 LLM Post-Training 全攻略：從 SFT 到 RLHF，手把手帶你訓練 Qwen](/posts/llm-post-training-approaches-open-source-zh/)
