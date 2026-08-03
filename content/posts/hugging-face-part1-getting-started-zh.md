---
title: "Hugging Face 實戰（一）：它到底是什麼，以及如何開始"
date: 2026-08-13T09:00:00+08:00
draft: false
weight: 1
description: "從零認識 Hugging Face：Hub、Transformers、Datasets、Spaces 五大支柱的關係，帳號與 Token 設定、CLI 安裝、快取機制，以及三行程式碼跑起第一個模型。含完整可執行範例。"
categories: ["engineering", "ai", "all"]
tags: ["Hugging Face", "Transformers", "LLM", "AI", "MLOps", "Python", "繁體中文"]
authors: ["yen"]
readTime: "22 min"
series: ["hugging-face"]
---

> *大多數人以為 Hugging Face 就是「一個下載模型的地方」。*
> *正確答案是：它是一整套從模型託管、資料集、訓練、評估到部署的工程基礎設施。*
> *大多數人第一天卡在 `OSError: model not found`、第二天卡在 40GB 的 C 槽被塞爆。*
> *這篇文章帶你把地基打對：搞懂它的架構、把環境裝乾淨，然後三行程式碼跑出第一個結果。*

---

**本文適合誰：** 聽過 Hugging Face、看過別人貼 `from transformers import pipeline`，但不確定整個生態系怎麼組起來、也不確定自己該從哪一步開始的工程師。

---

## 一、Hugging Face 是什麼：AI 界的 GitHub + PyPI + Heroku

### 1.1 一句話定義

[Hugging Face](https://huggingface.co/) 是一個**以 Git 為底層的機器學習資產託管平台**，加上一組讓你能三行程式碼用起這些資產的 Python 套件。

它同時扮演三個角色：

| 類比 | Hugging Face 對應 | 你在上面放什麼 |
|------|------------------|---------------|
| GitHub | Hub（Model / Dataset repo） | 模型權重、資料集、版本歷史 |
| PyPI | `transformers`、`datasets`、`peft`… | 用一行 `pip install` 取得的函式庫 |
| Heroku / Vercel | Spaces | 一個 URL 就能分享的 Demo App |

理解這個三重身分很重要，因為新手最常見的困惑——「我到底是在用網站，還是在用套件？」——答案是**兩個都要用，而且它們透過 Hub 串在一起**。

### 1.2 為什麼它會變成事實標準

在 Hugging Face 之前，你想跑一個別人論文裡的模型，流程大概是這樣：

```
找論文 → 找 GitHub repo → 發現 README 只有一行「code coming soon」
      → 找到權重在 Google Drive → 下載 4GB → 發現 PyTorch 版本不對
      → 改 3 天的 loading script → 終於跑起來 → 但 tokenizer 又不一樣
```

Hugging Face 做的事情本質上是**把「模型」變成一個有標準介面的套件**：權重、tokenizer 設定、前處理設定、推論設定全部打包在同一個 repo，用同一組 API 讀取。

```
                         標準化前                    標準化後
                    ─────────────────         ─────────────────────
  模型權重          各種格式 .pth/.bin        safetensors（統一、安全、零拷貝）
  分詞器            自己刻                    tokenizer.json（統一 spec）
  設定              寫死在程式碼裡            config.json（宣告式）
  載入方式          每個 repo 都不一樣        AutoModel.from_pretrained(id)
  版本管理          「請下載 v2_final.zip」   Git commit / tag / branch
```

**這個標準化的價值不在於方便，而在於可替換性。** 當 `AutoModelForCausalLM.from_pretrained()` 對任何模型都成立時，你的程式碼就與模型解耦了——換模型只需要改一個字串。

---

## 二、生態系全貌：五大支柱與它們的關係

Hugging Face 的元件很多，但只要抓住「**Hub 是中心，其他都是圍繞它的工具**」這條主軸就不會迷路。

```
                    ┌──────────────────────────────────────┐
                    │        Hugging Face Hub              │
                    │  （Git + LFS 底層的資產儲存中心）      │
                    │                                      │
                    │   Models    Datasets    Spaces       │
                    │   ~2M+      ~400K+      ~600K+       │
                    └───┬──────────┬──────────┬────────────┘
                        │          │          │
        ┌───────────────┘          │          └──────────────┐
        │                          │                         │
        ▼                          ▼                         ▼
┌───────────────┐        ┌──────────────────┐      ┌──────────────────┐
│ transformers  │        │    datasets      │      │  Spaces Runtime  │
│ 載入/推論/訓練 │        │ 載入/串流/處理    │      │ Gradio/Streamlit │
└───────┬───────┘        └──────────────────┘      │ /Docker 部署     │
        │                                          └──────────────────┘
        │  延伸工具鏈
        ├──▶ peft        參數高效微調（LoRA / QLoRA）
        ├──▶ trl         後訓練（SFT / DPO / GRPO）
        ├──▶ accelerate  多卡與混合精度的分散式抽象
        ├──▶ diffusers   影像/影片生成模型
        ├──▶ evaluate    指標計算
        └──▶ TGI / vLLM  生產級推論伺服器
```

### 2.1 五大支柱各自解決什麼問題

| 支柱 | 解決的問題 | 什麼時候你會需要它 |
|------|-----------|------------------|
| **Hub** | 模型與資料的版本化託管 | 第一天就需要 |
| **transformers** | 統一的載入與推論 API | 第一天就需要 |
| **datasets** | 大於記憶體的資料集處理 | 開始訓練/評估時 |
| **Spaces** | 零維運的 Demo 分享 | 要給非工程師看時 |
| **Inference Providers** | 不想自己養 GPU 的 API 呼叫 | 只做原型或流量很低時 |

### 2.2 一個常見誤解：Hub 不是「免費 GPU」

Hub 免費提供的是**儲存與頻寬**（公開 repo 幾乎無上限），不是運算。運算分成三類，成本結構完全不同：

```
  ┌─────────────────────────────────────────────────────────────┐
  │  A. 你自己的機器                                             │
  │     成本：硬體攤提；上限：你的 VRAM                            │
  │     適合：開發、微調小模型、隱私敏感資料                        │
  ├─────────────────────────────────────────────────────────────┤
  │  B. Inference Providers（Serverless API）                    │
  │     成本：按 token 計價；上限：供應商的模型清單                 │
  │     適合：原型、低流量、不想碰 infra                           │
  ├─────────────────────────────────────────────────────────────┤
  │  C. Inference Endpoints / 自架 TGI / vLLM                    │
  │     成本：按 GPU 小時（A10G 約 $1/hr、A100 約 $4/hr）          │
  │     適合：生產環境、需要固定延遲與私有部署                       │
  └─────────────────────────────────────────────────────────────┘
```

新手最常見的帳單意外，是把 Inference Endpoint 開起來測試後忘記關——它是**按時計費而非按請求計費**，閒置一整週就是 $170 起跳。記得設定 scale-to-zero。

---

## 三、從零開始：五個步驟把環境弄乾淨

### 3.1 Step 1 — 註冊與建立 Token

到 [huggingface.co/join](https://huggingface.co/join) 註冊後，到 **Settings → Access Tokens** 建立 token。這裡有一個很多人忽略的選擇：

| Token 類型 | 權限範圍 | 建議用途 |
|-----------|---------|---------|
| Fine-grained | 可指定到單一 repo、單一動作 | **CI/CD 與生產環境（推薦）** |
| Read | 讀取所有你有權限的 repo | 本機開發、下載 gated 模型 |
| Write | 讀寫所有 repo | 本機推送模型時臨時使用 |

**實務建議：** 本機開發用一個 `read` token；要推送模型時再開一個 fine-grained 的 write token 並限定到目標 repo。不要在 CI 裡放全域 write token——那等同於把你所有模型 repo 的刪除權限交給 CI。

### 3.2 Step 2 — 安裝套件

```bash
# 基礎三件組（CPU 版本，先確認流程跑得通）
pip install "transformers>=4.44" "huggingface_hub>=0.34" datasets

# PyTorch：務必依照你的 CUDA 版本安裝，不要盲目 pip install torch
# CUDA 12.1 範例：
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 加速與量化（有 GPU 時）
pip install accelerate bitsandbytes

# 之後幾篇會用到
pip install peft trl gradio sentence-transformers
```

> **踩坑提醒：** `pip install torch` 在沒有指定 index 的情況下，Linux 上會裝到綁定特定 CUDA 版本的 wheel，macOS 上則是 CPU/MPS 版本。如果你的 `torch.cuda.is_available()` 回傳 `False`，九成是這一步裝錯了，不是驅動問題。

### 3.3 Step 3 — 登入

`huggingface_hub` v0.34 之後提供了新的 `hf` CLI，舊的 `huggingface-cli` 仍可使用但已標記為過渡：

```bash
# 新版指令（推薦）
hf auth login

# 舊版指令（等價，仍可用）
huggingface-cli login

# 確認身分
hf auth whoami
```

登入後 token 會存在 `~/.cache/huggingface/token`。在**伺服器或 CI 環境**中不要用互動式登入，改用環境變數：

```bash
export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxx"
```

`huggingface_hub` 會自動讀取 `HF_TOKEN`，所有套件（transformers、datasets、peft）都吃這個變數，不需要在程式碼裡傳 token 參數。

### 3.4 Step 4 — 設定快取位置（很重要）

這是**最多人踩、也最痛的坑**。預設快取在 `~/.cache/huggingface/hub`，而現代模型動輒 15–150GB：

```
  Llama-3.1-8B  (bf16)      ~16 GB
  Qwen2.5-14B   (bf16)      ~28 GB
  Llama-3.1-70B (bf16)     ~140 GB
  Flux.1-dev                ~24 GB
```

在系統碟空間有限、或多人共用機器時，務必先改掉：

```bash
# 放到大容量磁碟
export HF_HOME=/data/hf

# 結構會是：
#   /data/hf/hub/     模型與資料集快取
#   /data/hf/token    憑證
```

```bash
# 檢視目前快取用了多少空間
hf cache scan

# 互動式刪除不用的 revision
hf cache delete
```

> **多人共用機器的最佳實務：** 設一個共用的 `HF_HOME=/opt/shared/hf` 並給 group 寫入權限。同一個 8B 模型被三個人各下載一份，就是浪費 48GB 與三倍頻寬。

### 3.5 Step 5 — 驗證安裝

```python
# verify_setup.py
import torch
import transformers
from huggingface_hub import whoami

print(f"transformers : {transformers.__version__}")
print(f"torch        : {torch.__version__}")
print(f"CUDA 可用    : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU          : {torch.cuda.get_device_name(0)}")
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"VRAM         : {vram:.1f} GB")
elif torch.backends.mps.is_available():   # Apple Silicon
    print("裝置         : MPS (Apple Silicon)")

try:
    print(f"HF 帳號      : {whoami()['name']}")
except Exception:
    print("HF 帳號      : 未登入（公開模型仍可下載）")
```

**VRAM 是你唯一真正的硬限制。** 記住這條估算公式，之後每次選模型都會用到：

```
  推論所需 VRAM ≈ 參數量 × 每參數位元組 × 1.2（KV cache 與碎片的緩衝）

  例：8B 模型
    fp32  (4 bytes)  →  8 × 4 × 1.2 = 38.4 GB   ← A100 才裝得下
    bf16  (2 bytes)  →  8 × 2 × 1.2 = 19.2 GB   ← 24GB 卡剛好
    int8  (1 byte)   →  8 × 1 × 1.2 =  9.6 GB   ← 12GB 卡可行
    int4  (0.5 byte) →  8 × 0.5 × 1.2 = 4.8 GB  ← 8GB 卡可行
```

---

## 四、Hub 的解剖：一個 repo 裡面到底有什麼

### 4.1 Model repo 的檔案結構

以一個典型的 causal LM 為例：

```
meta-llama/Llama-3.1-8B-Instruct/
├── config.json                    模型架構定義（層數、hidden size、attention 型態）
├── generation_config.json         預設生成參數（temperature、top_p、eos_token_id）
├── model-00001-of-00004.safetensors   權重分片 1
├── model-00002-of-00004.safetensors   權重分片 2
├── model-00003-of-00004.safetensors   權重分片 3
├── model-00004-of-00004.safetensors   權重分片 4
├── model.safetensors.index.json   分片索引（哪個張量在哪個檔）
├── tokenizer.json                 快速分詞器（Rust 實作，完整 spec）
├── tokenizer_config.json          分詞器設定 + chat_template
├── special_tokens_map.json        特殊 token 對應
├── README.md                      ← Model Card（授權、限制、評測結果）
└── .gitattributes                 LFS 追蹤規則
```

三個關鍵觀念：

**1. `safetensors` 不只是新格式，是安全需求。** 舊的 `.bin` 是 Python `pickle`，載入等同執行任意程式碼——下載一個惡意 `.bin` 就是遠端執行漏洞。`safetensors` 是純資料格式，無法夾帶程式碼，而且支援 memory-map 零拷貝載入，速度也更快。**看到只提供 `.bin` 的 repo，先確認來源可信度。**

**2. `chat_template` 決定對話模型能不能正常回話。** 這是藏在 `tokenizer_config.json` 裡的一段 Jinja 模板，定義了 system/user/assistant 訊息要怎麼拼成一個字串。用錯 template 的症狀非常典型：模型會自問自答、或在回答後繼續生成假的使用者發言。**永遠用 `tokenizer.apply_chat_template()`，不要手動拼字串。**

**3. Model Card 不是文件，是合規依據。** 商用前必須讀 `license` 欄位。常見授權的實際差異：

| 授權 | 商用 | 需注意 |
|------|------|--------|
| Apache-2.0 / MIT | ✅ 自由 | 保留授權聲明即可 |
| Llama 3.x Community | ✅ 有條件 | MAU > 7 億需另外申請；產品名須標示 "Llama" |
| Gemma Terms | ✅ 有條件 | 受使用政策約束，需傳遞條款給下游 |
| CC-BY-NC | ❌ | 禁止商用，很多研究模型是這個 |
| gated（需申請） | 依 repo | 需在網頁上同意條款後 token 才能下載 |

### 4.2 用 API 探索 Hub

```python
from huggingface_hub import HfApi, list_models

api = HfApi()

# 找出「文字生成」任務中下載量最高的 10 個模型
models = list_models(
    task="text-generation",
    sort="downloads",
    direction=-1,
    limit=10,
)
for m in models:
    print(f"{m.downloads:>12,}  {m.id}")

# 查看單一 repo 的細節
info = api.model_info("Qwen/Qwen2.5-7B-Instruct", files_metadata=True)
print(f"授權       : {info.card_data.get('license')}")
print(f"最新 commit: {info.sha[:8]}")
total = sum(f.size or 0 for f in info.siblings)
print(f"repo 大小  : {total / 1e9:.1f} GB")
```

### 4.3 精準下載：不要整包拉

`from_pretrained()` 會下載整個 repo。當 repo 同時放了 fp32、bf16、GGUF 三種格式時，你可能會下載到三倍的東西。用 `allow_patterns` 控制：

```python
from huggingface_hub import snapshot_download

path = snapshot_download(
    repo_id="Qwen/Qwen2.5-7B-Instruct",
    allow_patterns=["*.safetensors", "*.json", "tokenizer*"],
    ignore_patterns=["*.bin", "*.pth", "*.gguf"],   # 排除重複格式
    revision="main",        # 生產環境請改成固定的 commit SHA
)
print(path)
```

> **生產環境鐵則：** `revision` 一定要釘死在 commit SHA。`main` 會變——模型作者深夜推一個 commit 修改了 `generation_config.json` 的 `temperature`，你的線上服務行為就在無人變更程式碼的情況下改變了。這種事故很難 debug，因為 git log 上什麼都沒發生。

---

## 五、第一支程式：從三行到理解每一層

### 5.1 最高抽象層：`pipeline`

```python
from transformers import pipeline

clf = pipeline("sentiment-analysis")
print(clf("這家餐廳的服務真是讓人印象深刻。"))
# [{'label': 'POSITIVE', 'score': 0.9134}]
```

三行就跑起來了，但**這段程式碼有兩個生產環境不能接受的問題**：

1. 沒有指定模型 → 用的是預設的英文模型，處理中文結果不可靠
2. 沒有釘版本 → 預設模型未來可能被替換

正確寫法：

```python
from transformers import pipeline

clf = pipeline(
    task="sentiment-analysis",
    model="uer/roberta-base-finetuned-jd-binary-chinese",  # 明確指定中文模型
    device_map="auto",     # 有 GPU 就用 GPU
)
results = clf([
    "這家餐廳的服務真是讓人印象深刻。",
    "等了四十分鐘，上錯菜還不道歉。",
])
for r in results:
    print(f"{r['label']:>10}  {r['score']:.3f}")
```

### 5.2 `pipeline` 到底幫你做了什麼

理解這一層，之後 debug 才有方向：

```
  輸入文字 "這家餐廳..."
        │
        ▼
  ┌──────────────────────────────────────────┐
  │ 1. Tokenizer                             │
  │    文字 → token id → tensor              │
  │    [101, 6821, 2157, ...]                │
  └──────────────┬───────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────┐
  │ 2. 前處理：padding / truncation / 搬到 GPU │
  └──────────────┬───────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────┐
  │ 3. Model forward                         │
  │    logits: tensor([[-2.1, 3.4]])         │
  └──────────────┬───────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────┐
  │ 4. 後處理：softmax → label 對應 → dict     │
  └──────────────┬───────────────────────────┘
                 ▼
  [{'label': 'POSITIVE', 'score': 0.9134}]
```

`pipeline` 把這四步全包了。方便，但**它一次只處理一批、沒有連續批次（continuous batching）、也不做 KV cache 最佳化**——所以它適合原型與離線批次處理，不適合當線上服務。（第二篇會講服務化該用什麼。）

### 5.3 下一層：`AutoTokenizer` + `AutoModel`

當你需要控制細節時，就要拆開來寫：

```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_id = "uer/roberta-base-finetuned-jd-binary-chinese"

tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSequenceClassification.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto",
)
model.eval()

texts = ["服務很好，會再來", "難吃又貴，不推薦"]
inputs = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=512)
inputs = {k: v.to(model.device) for k, v in inputs.items()}

with torch.no_grad():                       # 推論時關掉梯度，省一半記憶體
    logits = model(**inputs).logits

probs = torch.softmax(logits, dim=-1)
for text, p in zip(texts, probs):
    label = model.config.id2label[p.argmax().item()]
    print(f"{label:>10} ({p.max():.3f})  {text}")
```

**`Auto*` 類別的魔法在哪裡？** 它讀 `config.json` 裡的 `architectures` 欄位，動態決定要 import 哪個實作類別。所以同一段程式碼可以載入 BERT、RoBERTa、DeBERTa 而不需要改任何一個字——這就是第一節說的「可替換性」。

### 5.4 生成式模型：正確的 chat 寫法

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

model_id = "Qwen/Qwen2.5-1.5B-Instruct"   # 1.5B，一般筆電也跑得動

tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

messages = [
    {"role": "system", "content": "你是一位精簡扼要的技術助理，回答控制在三句話內。"},
    {"role": "user", "content": "用比喻解釋什麼是 embedding。"},
]

# 關鍵：用 apply_chat_template，不要手動拼字串
text = tok.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,   # 在結尾加上 assistant 起始標記
)
inputs = tok(text, return_tensors="pt").to(model.device)

with torch.no_grad():
    out = model.generate(
        **inputs,
        max_new_tokens=256,
        temperature=0.7,
        top_p=0.9,
        do_sample=True,
        repetition_penalty=1.05,
    )

# 只解碼新生成的部分，去掉 prompt
reply = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
print(reply)
```

我們印出 template 展開後的樣子，看看 `apply_chat_template` 實際做了什麼：

```
<|im_start|>system
你是一位精簡扼要的技術助理，回答控制在三句話內。<|im_end|>
<|im_start|>user
用比喻解釋什麼是 embedding。<|im_end|>
<|im_start|>assistant
```

那些 `<|im_start|>` 是 Qwen 系列的特殊 token。**Llama 3 用的是完全不同的 `<|begin_of_text|>` / `<|start_header_id|>`。** 這就是為什麼手動拼字串幾乎一定會出錯，而且錯得很隱晦——模型還是會生成東西，只是品質莫名其妙地差。

---

## 六、三個演進階段：你現在在哪一格

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 1：個人探索（單機 / 免費額度）                              ║
╚══════════════════════════════════════════════════════════════════╝

  ┌──────────┐   pipeline / from_pretrained   ┌──────────────┐
  │  筆電或   │ ─────────────────────────────▶ │  HF Hub      │
  │  Colab   │                                │  公開模型     │
  └──────────┘ ◀───────────────────────────── └──────────────┘
                    模型檔（快取到本機）

  用到的東西：transformers、pipeline、Colab T4
  模型規模  ：< 3B（fp16）或 < 8B（int4）
  成本      ：$0（Colab 免費層）
  能做      ：驗證想法、跑通流程、做 side project
  做不到    ：並發服務、穩定延遲、資料隱私保證
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 2：團隊產品（自架推論 + 私有 repo）                         ║
╚══════════════════════════════════════════════════════════════════╝

  ┌─────────┐    ┌──────────────┐    ┌────────────────────────┐
  │ 前端/API │───▶│  FastAPI     │───▶│  TGI / vLLM (A10G×1)   │
  └─────────┘    │  業務邏輯     │    │  continuous batching   │
                 └──────┬───────┘    └───────────┬────────────┘
                        │                        │ 啟動時拉取
                        ▼                        ▼
                 ┌──────────────┐    ┌────────────────────────┐
                 │  Postgres    │    │  HF Hub 私有 repo       │
                 │  對話紀錄     │    │  釘死 commit SHA        │
                 └──────────────┘    └────────────────────────┘

  新增       ：私有 repo、推論伺服器、版本釘選、CI 下載快取
  模型規模   ：7B–14B（bf16 或 AWQ int4）
  成本       ：~$750/月（A10G 全時運行）
  解決       ：並發、P99 延遲可控、模型版本可追溯
  仍未解決   ：多模型共存的資源競爭、跨區部署
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 3：企業規模（多模型 + 自動擴縮 + 治理）                      ║
╚══════════════════════════════════════════════════════════════════╝

  ┌──────────┐   ┌────────────┐   ┌──────────────────────────────┐
  │ API GW   │──▶│  Router    │──▶│  模型池（K8s + GPU node pool）│
  │ 認證/限流 │   │  依任務分流 │   │  ┌────────┐ ┌────────┐       │
  └──────────┘   └─────┬──────┘   │  │ 8B 通用 │ │ 3B 分類 │  …    │
                       │          │  │ ×4 replica│ ×2      │       │
                       │          │  └────────┘ └────────┘       │
                       │          └──────────────┬───────────────┘
                       ▼                         ▼
              ┌──────────────┐        ┌────────────────────────┐
              │ 語意快取      │        │ 內部 Hub Mirror        │
              │ (Redis)      │        │ 掃毒 + 授權審核 + 快取  │
              └──────────────┘        └────────────────────────┘
                       │
                       ▼
              ┌───────────────────────────────────────┐
              │ 可觀測性：Prometheus + OTel + 離線評估  │
              └───────────────────────────────────────┘

  新增     ：模型路由、語意快取、內部 mirror、自動擴縮、評估管線
  成本     ：~$4,000–15,000/月（依流量），但每 token 成本比 Phase 2 低 60%+
  解決     ：成本最佳化、供應鏈安全、多團隊共用、合規稽核
  代價     ：需要 1–2 名專職平台工程師
```

**判斷自己該在哪一格的簡單規則：** 沒有付費使用者 → Phase 1。有付費使用者但 QPS < 10 → Phase 2。多個團隊、多個模型、或有稽核需求 → Phase 3。**不要提前跳級**，Phase 3 的架構在 Phase 1 的流量下只會拖慢你的迭代速度。

---

## 七、為什麼選 X 不選 Y

### 7.1 `pipeline` vs `AutoModel`

```
選擇                選 pipeline 的理由              不選 AutoModel 的理由
────────────────────────────────────────────────────────────────────────
pipeline            前後處理全包，5 行搞定           AutoModel 要自己寫
                    任務語意清楚，可讀性高            decode / softmax / label 對應
                    適合原型、離線批次
────────────────────────────────────────────────────────────────────────
翻轉條件：需要控制 batch 策略、要拿中間層 hidden state、要自訂 generation
          loop、或要接推論伺服器時 → 改用 AutoModel
```

### 7.2 `safetensors` vs `pytorch_model.bin`

```
選擇                選 safetensors 的理由           不選 .bin 的理由
────────────────────────────────────────────────────────────────────────
safetensors         純資料格式，無程式碼執行風險      .bin 是 pickle，載入 = 執行程式碼
                    memory-map 零拷貝，載入快 2–5×    需要先全部反序列化到記憶體
                    可只讀取部分張量                  必須整包載入
────────────────────────────────────────────────────────────────────────
翻轉條件：幾乎沒有。只有在老舊 repo 尚未轉換時才被迫用 .bin，
          此時務必確認發布者身分，並在隔離環境載入
```

### 7.3 自架推論 vs Inference Providers（Serverless API）

```
選擇                選自架的理由                    選 API 的理由
────────────────────────────────────────────────────────────────────────
自架 TGI/vLLM       高流量時單位成本低 5–20×         流量低時完全不用付閒置費
                    延遲可控（無冷啟動）              零維運、零 GPU 知識需求
                    資料不出自己的網路                幾分鐘就能上線
                    可用任何自訓模型                  自動享有供應商的最佳化
────────────────────────────────────────────────────────────────────────
翻轉條件（成本交叉點）：
  A10G 自架 ≈ $750/月，可服務約 3,000 萬 token/月
  Serverless 約 $0.2–0.6 / 1M token
  → 每月 < 300 萬 token 時，API 明顯較便宜
  → 每月 > 2,000 萬 token 時，自架明顯較便宜
  → 中間灰色地帶：看你有沒有人力維運，通常「沒有」就選 API
```

### 7.4 `device_map="auto"` vs 手動 `.to("cuda")`

```
選擇                選 device_map 的理由            不選手動搬移的理由
────────────────────────────────────────────────────────────────────────
device_map="auto"   自動跨多卡切分大模型             手動只能整個模型放一張卡
                    VRAM 不夠時自動 offload 到 CPU   OOM 就是 OOM
                    程式碼在 1 卡與 8 卡都能跑        每種硬體要寫不同分支
────────────────────────────────────────────────────────────────────────
翻轉條件：小模型（< 3B）且確定單卡放得下時，手動 .to("cuda") 更快也更好預測。
          device_map 的 offload 一旦觸發，推論速度可能掉到 1/20——
          它讓你「跑得起來」，不代表「跑得快」
```

### 7.5 完整微調 vs 直接用現成模型

```
選擇                選現成模型的理由                選微調的理由
────────────────────────────────────────────────────────────────────────
現成 Instruct 模型   零訓練成本，今天就能上線         領域術語準確率可提升 20–30%
                    社群持續更新                     輸出格式穩定度大幅提高
                    可隨時換更強的模型                延遲不變但小模型即可勝任
────────────────────────────────────────────────────────────────────────
翻轉條件：先用 prompt engineering + few-shot 試到極限。
          若準確率仍差目標 > 15 個百分點，且你有 > 1,000 筆高品質標注 →
          才值得微調（第三篇詳談）
```

---

## 八、開始前先知道的六個坑

| # | 症狀 | 真正原因 | 解法 |
|---|------|---------|------|
| 1 | `OSError: ... is not a local folder` | repo 是 gated，或 token 沒權限 | 到網頁上同意授權 → `hf auth login` |
| 2 | `CUDA out of memory` | 用 fp32 載入，或忘了 `torch.no_grad()` | 加 `torch_dtype=torch.bfloat16`、包 `no_grad` |
| 3 | 模型自問自答、生成假對話 | 沒用 `apply_chat_template` | 一律用 template，不手拼字串 |
| 4 | 系統碟被塞爆 | 快取在 `~/.cache` | 設 `HF_HOME`，定期 `hf cache scan` |
| 5 | 線上行為突然改變，程式碼卻沒動 | `revision="main"` 被上游更新 | 釘死 commit SHA |
| 6 | 中文結果很差 | 用了英文為主的模型 | 選 Qwen / Breeze / Taiwan-LLM 等中文優化模型 |

**額外提醒：** `trust_remote_code=True` 會執行 repo 裡的 Python 檔案。有些新架構確實需要它，但那等同於 `curl | bash`——只對你信任的組織（Qwen、Microsoft、官方 org）開啟，並且務必同時釘死 `revision`。

---

## 九、把它跑起來：一個 15 分鐘的驗收練習

做完這個練習，你就完成了 Phase 1 的所有基本功。

```python
# quickstart.py — 中文評論分析小工具
import torch
from transformers import pipeline

DEVICE = 0 if torch.cuda.is_available() else -1

# 1) 情感分類
sentiment = pipeline(
    "sentiment-analysis",
    model="uer/roberta-base-finetuned-jd-binary-chinese",
    device=DEVICE,
)

# 2) 零樣本分類：不需訓練就能自訂類別
zero_shot = pipeline(
    "zero-shot-classification",
    model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    device=DEVICE,
)

# 3) 摘要（用小型生成模型）
summarizer = pipeline(
    "text2text-generation",
    model="csebuetnlp/mT5_multilingual_XLSum",
    device=DEVICE,
)

reviews = [
    "外送遲到一小時，客服態度還很差，以後不會再訂了。",
    "介面設計很直覺，第一次用就上手，客服回應也快。",
    "功能很強大但價格偏高，小團隊可能負擔不起。",
]

LABELS = ["產品功能", "客戶服務", "價格", "物流配送"]

for r in reviews:
    s = sentiment(r)[0]
    z = zero_shot(r, candidate_labels=LABELS)
    print(f"\n評論：{r}")
    print(f"  情感：{s['label']} ({s['score']:.2f})")
    print(f"  主題：{z['labels'][0]} ({z['scores'][0]:.2f})")
```

**這個練習驗證了四件事：** 環境裝對了、GPU/CPU 判斷正確、能從 Hub 下載模型、能處理中文。任何一步失敗，回頭對照第三節與第八節。

---

## 十、系列導航

本文是「Hugging Face 實戰」系列的第 1 篇。

**系列規劃：**

| # | 主題 | 你會學到 |
|---|------|---------|
| **1（本文）** | **入門與生態系** | **Hub 架構、環境設定、第一支程式** |
| 2 | 用模型、跑 App、推自己的模型 | 量化載入、Gradio/FastAPI 服務化、推送到 Hub |
| 3 | 微調（Fine-tuning） | Datasets、Trainer、LoRA/QLoRA、評估 |
| 4 | 後訓練（Post-training） | SFT → DPO / ORPO / GRPO，偏好資料與對齊 |
| 5 | 端到端實戰 | 完整 RAG 客服系統，含程式碼與部署 |

→ **下一篇：** [Hugging Face 實戰（二）：用模型、跑 App、推送自己的模型](/posts/hugging-face-part2-use-and-push-models-zh/)

**延伸閱讀：**
- [開源 LLM Post-Training 全攻略：從 SFT 到 RLHF](/posts/llm-post-training-approaches-open-source-zh/)
- [AI 工程從零開始｜Phase 10 Part 3：LLM 微調 — LoRA、QLoRA 與指令對齊](/posts/ai-eng-from-scratch-phase10-part3-finetuning-zh/)
