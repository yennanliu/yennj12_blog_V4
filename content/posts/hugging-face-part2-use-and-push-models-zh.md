---
title: "Hugging Face 實戰（二）：用模型、跑 App、推送自己的模型"
date: 2026-08-14T09:00:00+08:00
draft: false
weight: 2
description: "如何從兩百萬個 repo 中挑對模型、用四個抽象層載入它、用 Gradio 與 FastAPI + vLLM 把它變成服務，並把自己的模型完整推上 Hub。含量化、Spaces 部署與 Model Card 撰寫範例。"
categories: ["engineering", "ai", "all"]
tags: ["Hugging Face", "Transformers", "Gradio", "vLLM", "TGI", "LLM", "MLOps", "Python", "繁體中文"]
authors: ["yen"]
readTime: "26 min"
series: ["hugging-face"]
---

> *大多數人挑模型的方式是看 Trending 第一名，然後 `from_pretrained` 下去。*
> *正確答案是：先確定 VRAM 上限與授權條款，再從那個交集裡挑排行最高的。*
> *大多數人把 `pipeline` 包進 Flask 就當作上線了。*
> *正確答案是：那個架構在第 5 個並發請求就會開始排隊，而你需要的是 continuous batching。*

---

**上一篇**我們把環境架好、跑出第一個結果。這一篇處理三件實際工作：**挑對模型、把它變成別人能用的服務、把自己訓練的成果推回 Hub。**

---

## 一、選模型：從兩百萬個 repo 中挑對那一個

### 1.1 四道篩選器，順序不能顛倒

```
  2,000,000+ 個模型
        │
        ▼
  ┌──────────────────────────────────────────────┐
  │ 篩選 1：任務類型（pipeline_tag）              │  → 剩約 5%
  │   text-generation / embeddings / ASR / …     │
  └──────────────┬───────────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────────┐
  │ 篩選 2：VRAM 是否放得下（硬限制）              │  → 剩約 1%
  │   參數量 × dtype bytes × 1.2 ≤ 你的 VRAM      │
  └──────────────┬───────────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────────┐
  │ 篩選 3：授權是否允許你的用途（法務限制）        │  → 剩約 0.6%
  │   Apache-2.0 / MIT / Llama Community / …     │
  └──────────────┬───────────────────────────────┘
                 ▼
  ┌──────────────────────────────────────────────┐
  │ 篩選 4：目標語言與領域的實測表現                │  → 剩 3–5 個候選
  │   用你自己的 50 題測試集跑，不要只看榜單        │
  └──────────────┬───────────────────────────────┘
                 ▼
              最終選擇
```

**順序很重要。** 很多人從第 4 步開始（「我要最強的」），花兩天調通一個 70B 模型，最後才發現公司規定資料不能出境、而那個模型的授權禁止商用。**硬限制先過，偏好後談。**

### 1.2 中文場景的實務建議（2026 年中）

| 用途 | 推薦起點 | 參數量 | 授權 | 備註 |
|------|---------|--------|------|------|
| 中文對話 / 通用 | `Qwen/Qwen2.5-7B-Instruct` | 7B | Apache-2.0 | 中文能力強、授權寬鬆，預設首選 |
| 邊緣裝置 / 低延遲 | `Qwen/Qwen2.5-1.5B-Instruct` | 1.5B | Apache-2.0 | int4 後約 1.2GB |
| 繁中在地化 | `MediaTek-Research/Breeze-7B-Instruct-v1_0` | 7B | Apache-2.0 | 台灣用語與繁體最佳化 |
| 中文 Embedding | `BAAI/bge-m3` | 568M | MIT | 多語、支援長文與混合檢索 |
| 中文 Reranker | `BAAI/bge-reranker-v2-m3` | 568M | Apache-2.0 | RAG 精排必備 |
| 語音辨識 | `openai/whisper-large-v3-turbo` | 809M | MIT | 中文 WER 明顯優於 base |

> 模型迭代很快，這張表的價值不在具體型號，而在**「先看授權、再看規模、最後看能力」的挑選邏輯**。

### 1.3 用程式碼做篩選

```python
from huggingface_hub import list_models

MY_VRAM_GB = 24
OK_LICENSES = {"apache-2.0", "mit", "bsd-3-clause"}

def rough_params_b(model_id: str) -> float | None:
    """從 repo 名稱粗估參數量，例如 Qwen2.5-7B-Instruct → 7.0"""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])", model_id)
    return float(m.group(1)) if m else None

candidates = []
for m in list_models(task="text-generation", sort="downloads",
                     direction=-1, limit=200, full=True):
    lic = (m.card_data or {}).get("license") if m.card_data else None
    size = rough_params_b(m.id)
    if lic not in OK_LICENSES or size is None:
        continue
    vram_bf16 = size * 2 * 1.2
    vram_int4 = size * 0.5 * 1.2
    if vram_int4 <= MY_VRAM_GB:
        candidates.append((m.id, size, lic, vram_bf16, vram_int4))

print(f"{'模型':<45} {'B':>6} {'授權':<14} {'bf16':>7} {'int4':>7}")
for cid, size, lic, b16, i4 in candidates[:12]:
    fits = "✓" if b16 <= MY_VRAM_GB else "需量化"
    print(f"{cid:<45} {size:>6.1f} {lic:<14} {b16:>6.1f}G {i4:>6.1f}G  {fits}")
```

**但最終決策一定要靠你自己的測試集。** 準備 50 題涵蓋你實際場景的問題，跑過 3–5 個候選模型，人工評分。這半天的投資，可以避免上線後才發現「榜單第一在我的領域裡表現最差」。

---

## 二、載入模型的四個抽象層

```
  抽象程度高                                             抽象程度低
  控制力低                                                 控制力高
  ◀────────────────────────────────────────────────────────────▶

  ┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────┐
  │ pipeline │  │ AutoModel  │  │ 量化載入      │  │ 推論伺服器    │
  │          │  │ + generate │  │ bnb/AWQ/GPTQ │  │ vLLM / TGI   │
  ├──────────┤  ├────────────┤  ├──────────────┤  ├──────────────┤
  │ 原型     │  │ 自訂邏輯    │  │ VRAM 不足    │  │ 生產服務      │
  │ 離線批次  │  │ 拿 hidden  │  │ 成本壓縮      │  │ 高並發        │
  └──────────┘  └────────────┘  └──────────────┘  └──────────────┘
```

第一篇已經講過前兩層。這裡處理後兩層——它們決定你的成本與可服務規模。

### 2.1 第三層：量化載入

量化就是**用更少的位元表示同一個權重**，以少量精度換大量記憶體。

```
  同一個 Qwen2.5-7B 在不同精度下：

  精度      VRAM      相對品質      推論速度      適用
  ──────────────────────────────────────────────────────────────
  bf16      16.8 GB   100%（基準）  1.0×          24GB 以上顯卡
  int8      8.8 GB    99.3%         0.7×（較慢）  12–16GB
  nf4       5.0 GB    97.5%         0.9×          8–12GB
  AWQ int4  4.6 GB    98.5%         1.6×（較快）  8–12GB，生產推薦
```

**注意 int8 反而變慢**——bitsandbytes 的 int8 需要在運算時反量化，額外開銷抵銷了頻寬節省。想要「又小又快」，應該用 AWQ 或 GPTQ 這類**預先量化**的模型。

**bitsandbytes（動態量化，任何模型都能用）：**

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",              # nf4 品質優於 fp4
    bnb_4bit_compute_dtype=torch.bfloat16,  # 計算時反量化成 bf16
    bnb_4bit_use_double_quant=True,         # 二次量化，再省約 0.4GB
)

model_id = "Qwen/Qwen2.5-7B-Instruct"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto",
)
print(f"VRAM 佔用：{model.get_memory_footprint() / 1e9:.2f} GB")
```

**AWQ（預先量化，速度最佳）：**

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

# 直接載入社群已量化好的 repo，不需要 quantization_config
model_id = "Qwen/Qwen2.5-7B-Instruct-AWQ"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
```

> **選擇原則：** 開發與微調時用 bitsandbytes（彈性高、任何模型都能量化）；生產部署找官方或社群的 AWQ / GPTQ 版本（速度快 1.5–2×）。**兩者不要混用**——用 bnb 微調出來的 LoRA，部署時應該合併回 bf16 底模再重新量化。

### 2.2 第四層：推論伺服器

**為什麼 `pipeline` 不能當服務？** 關鍵在批次策略：

```
  靜態批次（transformers pipeline）
  ─────────────────────────────────
  請求 A ████████████████████  (生成 200 token)
  請求 B ████░░░░░░░░░░░░░░░░  (只需 40 token，但要等 A 結束)
  請求 C ░░░░░░░░░░░░░░░░░░░░  (完全等待，直到整批完成)
         └─── GPU 有 60% 時間在算 padding ───┘

  連續批次（vLLM / TGI）
  ─────────────────────────────────
  請求 A ████████████████████
  請求 B ████↵ 完成即離開，槽位立刻給 D
  請求 C   ████████████↵
  請求 D     ██████████████████
         └─── GPU 使用率 > 85% ───┘

  實測差異（7B 模型、A10G、50 並發）：
    pipeline + Flask   ：  8 req/s，P99 12,000 ms
    vLLM               ： 62 req/s，P99  1,400 ms
```

**vLLM 提供 OpenAI 相容 API，這是目前最省事的生產選擇：**

```bash
pip install vllm

python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct-AWQ \
  --served-model-name my-chat \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --port 8000
```

```python
# 用 OpenAI SDK 呼叫自己的 vLLM，換模型只要改 base_url
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

resp = client.chat.completions.create(
    model="my-chat",
    messages=[{"role": "user", "content": "用三句話說明 continuous batching"}],
    temperature=0.7,
    max_tokens=256,
)
print(resp.choices[0].message.content)
```

**TGI（Text Generation Inference）是 Hugging Face 官方的方案，Docker 一行啟動：**

```bash
docker run --gpus all --shm-size 1g -p 8080:80 \
  -v $HF_HOME/hub:/data \
  -e HF_TOKEN=$HF_TOKEN \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id Qwen/Qwen2.5-7B-Instruct \
  --max-input-tokens 4096 \
  --max-total-tokens 8192 \
  --quantize awq
```

> `--shm-size 1g` 不能省。少了它，多 GPU 的 NCCL 通訊會在啟動時卡死，而錯誤訊息完全不會提到共享記憶體。

---

## 三、三個演進階段：從腳本到服務

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 1：本機腳本 + Gradio（0–100 使用者）                       ║
╚══════════════════════════════════════════════════════════════════╝

  ┌──────────────┐        ┌───────────────────────────┐
  │  瀏覽器       │───────▶│  Gradio（單一 process）    │
  │              │◀───────│  內含 transformers 模型    │
  └──────────────┘        └───────────────────────────┘

  部署：demo.launch() 或推到 HF Spaces
  成本：$0（Space CPU 免費層）/ $0.60 per hr（T4 Space）
  並發：1–3（超過就排隊）
  能做：Demo、內部工具、使用者訪談
  不能做：SLA、認證、多租戶
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 2：API + 專用推論伺服器（100–10K 使用者）                   ║
╚══════════════════════════════════════════════════════════════════╝

  ┌────────┐   ┌──────────────────┐   ┌──────────────────────┐
  │ Web/App│──▶│  FastAPI         │──▶│  vLLM (A10G × 1)     │
  └────────┘   │  · 認證 / 限流    │   │  continuous batching │
               │  · Prompt 組裝    │   │  OpenAI 相容 API      │
               │  · 業務邏輯       │   └──────────────────────┘
               └────────┬─────────┘
                        ▼
               ┌──────────────────┐
               │  Redis 快取       │  ← 相同 prompt 直接回，省 30–50% 呼叫
               └──────────────────┘

  新增：業務層與推論層分離、快取、串流回應、健康檢查
  成本：~$750/月（A10G）+ $30（Redis）
  並發：40–80（7B AWQ）
  解決：延遲穩定、可水平擴充業務層、模型可獨立升級
  未解決：GPU 閒置時仍在燒錢、單點故障
```

```
╔══════════════════════════════════════════════════════════════════╗
║  Phase 3：多模型 + 自動擴縮（10K+ 使用者）                         ║
╚══════════════════════════════════════════════════════════════════╝

  ┌────────┐  ┌───────────┐  ┌────────────────────────────────┐
  │ API GW │─▶│  Router   │─▶│  K8s GPU node pool             │
  │ 限流   │  │  · 依難度  │  │  ┌──────────┐  ┌──────────┐    │
  │ 計量   │  │  · 依成本  │  │  │ 7B AWQ   │  │ 1.5B     │    │
  └────────┘  └─────┬─────┘  │  │ ×3 (HPA) │  │ ×2 分類   │    │
                    │        │  └──────────┘  └──────────┘    │
                    │        └────────────────┬───────────────┘
                    ▼                         ▼
         ┌────────────────────┐   ┌──────────────────────────┐
         │ 語意快取（向量比對） │   │ 私有 Model Registry      │
         │ 命中率 25–40%       │   │ 掃描 + 授權審核 + mirror  │
         └────────────────────┘   └──────────────────────────┘
                    │
                    ▼
         ┌────────────────────────────────────────────┐
         │ 可觀測性：TTFT / tokens-per-sec / 成本/請求 │
         └────────────────────────────────────────────┘

  新增：模型路由（簡單問題丟 1.5B，複雜的丟 7B）、語意快取、HPA、成本歸因
  成本：~$3,500/月，但單位 token 成本比 Phase 2 低約 55%
  解決：尖峰擴充、成本最佳化、多團隊隔離
  代價：Kubernetes + GPU 排程的維運複雜度
```

---

## 四、用 Gradio 把模型變成 App

Gradio 是 Hugging Face 官方的 UI 框架，**它的價值在於「模型函式 → 網頁」只需要包一層**。

### 4.1 最小可用的串流聊天介面

```python
# app.py
import torch
import gradio as gr
from threading import Thread
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model.eval()


def chat(message, history, system_prompt, temperature, max_tokens):
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:                    # Gradio 5 的 messages 格式
        messages.append(turn)
    messages.append({"role": "user", "content": message})

    prompt = tok.apply_chat_template(messages, tokenize=False,
                                     add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)

    streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
    kwargs = dict(
        **inputs,
        streamer=streamer,
        max_new_tokens=int(max_tokens),
        temperature=float(temperature),
        top_p=0.9,
        do_sample=temperature > 0,
    )
    # 在背景執行緒生成，主執行緒逐塊 yield 給前端
    Thread(target=model.generate, kwargs=kwargs).start()

    partial = ""
    for chunk in streamer:
        partial += chunk
        yield partial


demo = gr.ChatInterface(
    fn=chat,
    type="messages",
    title="🤗 我的第一個 LLM 助理",
    description="以 Qwen2.5-1.5B-Instruct 驅動，支援串流回應。",
    additional_inputs=[
        gr.Textbox("你是一位友善且精準的中文技術助理。", label="System Prompt"),
        gr.Slider(0.0, 1.5, value=0.7, step=0.1, label="Temperature"),
        gr.Slider(64, 2048, value=512, step=64, label="Max Tokens"),
    ],
    examples=[
        ["用三句話解釋什麼是 LoRA"],
        ["幫我寫一個 Python 的 LRU cache"],
    ],
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
```

**三個讓體驗差很多的細節：**

1. **串流是必須的，不是加分項。** 生成 500 token 大約要 12 秒。沒有串流時使用者盯著空白畫面 12 秒；有串流時 0.4 秒就看到第一個字。技術上一樣慢，感知上差 30 倍。
2. **`Thread` + `TextIteratorStreamer` 是標準組合。** `model.generate` 是阻塞呼叫，必須丟到背景執行緒，主執行緒才能持續 yield。
3. **`type="messages"`** 是 Gradio 5 的格式，與 OpenAI 的訊息結構一致，換後端時不用改資料轉換。

### 4.2 部署到 Spaces

Space 本質上就是一個 Hub repo，裡面有 `app.py` 和 `requirements.txt`：

```python
# deploy_space.py
from huggingface_hub import HfApi

api = HfApi()
REPO = "your-username/my-llm-chat"

api.create_repo(
    repo_id=REPO,
    repo_type="space",
    space_sdk="gradio",
    private=False,
    exist_ok=True,
)

api.upload_folder(
    folder_path="./my_space",     # 內含 app.py, requirements.txt, README.md
    repo_id=REPO,
    repo_type="space",
    commit_message="初次部署",
)
print(f"https://huggingface.co/spaces/{REPO}")
```

```
my_space/
├── app.py               上面那份 Gradio 程式
├── requirements.txt     transformers / torch / accelerate / gradio
└── README.md            開頭的 YAML 決定 Space 設定
```

`README.md` 的 front matter 是 Space 的組態檔：

```yaml
---
title: My LLM Chat
emoji: 🤗
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "5.9.1"
app_file: app.py
pinned: false
license: apache-2.0
suggested_hardware: t4-small     # 免費 CPU 跑不動 1.5B 以上
---
```

> **Spaces 成本注意：** 免費層是 2 vCPU + 16GB RAM，**沒有 GPU**。1.5B 模型在 CPU 上每個 token 約 200ms，一段回答要等一分鐘。要 GPU 就要升級到付費硬體（T4 small 約 $0.40/hr，A10G small 約 $1.05/hr），而且**Space 只要有人開著就在計費**。務必在 Settings 裡開啟 sleep（閒置後自動休眠）。

### 4.3 生產服務：FastAPI 前面、vLLM 後面

Gradio 適合 Demo，正式產品需要把**業務邏輯**與**推論**分開：

```python
# server.py
import os
import time
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

app = FastAPI(title="LLM Gateway")

llm = AsyncOpenAI(
    base_url=os.getenv("VLLM_URL", "http://vllm:8000/v1"),
    api_key="not-needed",
)
API_KEYS = set(os.getenv("API_KEYS", "").split(","))

SYSTEM = "你是一位客服助理，只根據提供的資訊回答，不確定時請說不知道。"


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    stream: bool = False
    temperature: float = Field(0.7, ge=0.0, le=2.0)


def auth(x_api_key: str = Header(...)):
    if x_api_key not in API_KEYS:
        raise HTTPException(401, "invalid api key")
    return x_api_key


@app.post("/chat")
async def chat(req: ChatRequest, _=Depends(auth)):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": req.message},
    ]

    if req.stream:
        async def gen():
            s = await llm.chat.completions.create(
                model="my-chat", messages=messages,
                temperature=req.temperature, max_tokens=512, stream=True,
            )
            async for chunk in s:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {delta}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    t0 = time.perf_counter()
    resp = await llm.chat.completions.create(
        model="my-chat", messages=messages,
        temperature=req.temperature, max_tokens=512,
    )
    return {
        "reply": resp.choices[0].message.content,
        "usage": resp.usage.model_dump(),
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }


@app.get("/healthz")
async def healthz():
    try:
        await llm.models.list()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, f"llm unreachable: {e}")
```

**這個分層帶來三個好處：** 業務層可以無 GPU 水平擴充（便宜）、模型可以獨立升級或替換、`/healthz` 讓 K8s 能正確判斷就緒狀態。

---

## 五、推送自己的模型到 Hub

### 5.1 三種推送方式

```
  方式                     適合                        指令 / API
  ─────────────────────────────────────────────────────────────────────
  push_to_hub()           訓練完直接推                 model.push_to_hub(id)
  HfApi.upload_folder()   已有本機資料夾、要細部控制     api.upload_folder(...)
  hf CLI                  CI/CD、大檔案、shell 腳本    hf upload <repo> <path>
```

### 5.2 訓練後直接推送（最常用）

```python
from huggingface_hub import create_repo

REPO = "your-username/qwen2.5-1.5b-support-zh"

create_repo(REPO, repo_type="model", private=True, exist_ok=True)

model.push_to_hub(REPO, private=True, commit_message="v1: 客服語料微調")
tokenizer.push_to_hub(REPO)
```

> **一定要一起推 tokenizer。** 只推 model 的 repo 是壞掉的 repo——別人（包括三個月後的你）`from_pretrained` 會直接失敗。這是 Hub 上最常見的 repo 缺陷。

### 5.3 完整控制：`upload_folder`

```python
from huggingface_hub import HfApi, create_repo

api = HfApi()
REPO = "your-username/qwen2.5-1.5b-support-zh"
create_repo(REPO, repo_type="model", private=True, exist_ok=True)

api.upload_folder(
    folder_path="./output/final",
    repo_id=REPO,
    repo_type="model",
    commit_message="v1.2: 加入 2026Q2 語料，格式遵從率 89% → 94%",
    ignore_patterns=[
        "checkpoint-*",      # 中間檢查點，通常有數十 GB
        "*.log", "runs/",    # TensorBoard 紀錄
        "optimizer.pt",      # 優化器狀態，只有續訓才需要
    ],
)

# 打上版本標籤，之後可以用 revision="v1.2" 精確載入
api.create_tag(REPO, tag="v1.2", repo_type="model")
```

> **`ignore_patterns` 不加會出事。** `Trainer` 預設會在輸出目錄留下每個 checkpoint，一個 7B 模型訓練 3 epoch 可能產生 90GB 的中間檔。不小心全推上去，除了浪費頻寬，之後每個人 clone 你的 repo 都會拉這 90GB。

### 5.4 CLI 推送（適合 CI）

```bash
# 建立 repo
hf repo create your-username/my-model --type model --private

# 上傳整個資料夾
hf upload your-username/my-model ./output/final . \
  --commit-message "v1.2 release" \
  --exclude "checkpoint-*" "*.log"

# 上傳單一檔案
hf upload your-username/my-model ./adapter_model.safetensors
```

大檔案（> 5GB）建議開啟 Xet / 分塊上傳加速：

```bash
pip install "huggingface_hub[hf_xet]"
export HF_HUB_ENABLE_HF_TRANSFER=1     # 高速下載/上傳後端
```

### 5.5 Model Card：不是文件，是介面

`README.md` 開頭的 YAML 是**機器可讀的中繼資料**，它決定你的模型在 Hub 上能不能被搜尋到、能不能被 `pipeline` 自動識別：

````markdown
---
license: apache-2.0
base_model: Qwen/Qwen2.5-1.5B-Instruct
library_name: transformers
pipeline_tag: text-generation
language:
  - zh
  - en
tags:
  - customer-support
  - lora
  - traditional-chinese
datasets:
  - your-username/support-tickets-zh
metrics:
  - accuracy
model-index:
  - name: qwen2.5-1.5b-support-zh
    results:
      - task:
          type: text-generation
        dataset:
          name: internal-support-eval
          type: custom
        metrics:
          - type: accuracy
            value: 0.912
---

# Qwen2.5-1.5B Support (繁中客服)

以 `Qwen/Qwen2.5-1.5B-Instruct` 為底，用 12,400 筆去識別化的繁中客服對話
做 LoRA 微調（r=16, α=32），目標是穩定輸出結構化的工單分類與回覆草稿。

## 用途與限制

**適用：** 電商情境的訂單、退換貨、物流查詢分類與初步回覆草稿。
**不適用：** 醫療、法律、金融建議；不得作為最終決策依據。
**已知失效模式：** 對於同時包含三個以上訴求的長工單，分類準確率下降至 71%。

## 快速開始

```python
from transformers import pipeline

pipe = pipeline("text-generation",
                model="your-username/qwen2.5-1.5b-support-zh",
                torch_dtype="bfloat16", device_map="auto")
print(pipe([{"role": "user", "content": "我上週三下的單到現在還沒出貨"}],
           max_new_tokens=256)[0]["generated_text"][-1]["content"])
```

## 評估結果

| 指標 | 底模 | 本模型 |
|------|------|--------|
| 工單分類準確率 | 68.4% | 91.2% |
| JSON 格式合規率 | 41.0% | 98.6% |
| 平均回覆長度 | 312 字 | 148 字 |

評估集：2,000 筆人工標注工單，與訓練集無重疊（以工單 ID 切分）。

## 訓練細節

- LoRA r=16, alpha=32, dropout=0.05，target: q/k/v/o/gate/up/down_proj
- 3 epoch, lr=2e-4, cosine schedule, warmup 3%
- 有效 batch size 32（per_device 4 × grad_accum 8）
- 硬體：1× A10G 24GB，訓練時間 4.2 小時

## 偏誤與風險

訓練語料來自單一電商平台 2024–2026 的工單，對於該平台以外的商品類別、
或非台灣地區的物流用語，表現會顯著下降。回覆草稿必須經人工確認後才可發送。
````

**一份好的 Model Card 必須回答四個問題：** 這模型能做什麼、**不能**做什麼、怎麼評估出來的、什麼情況會壞掉。第二和第四點最常被省略，也最重要——它們是下游使用者判斷「能不能用在我的場景」的唯一依據。

### 5.6 私有 repo 與組織治理

```python
from huggingface_hub import HfApi

api = HfApi()

# 建立組織 repo（權限跟著組織成員設定走）
api.create_repo("my-org/internal-classifier", private=True, exist_ok=True)

# 從私有變公開（發布時）
api.update_repo_settings("my-org/internal-classifier", private=False)

# 檢查誰改了什麼
for c in api.list_repo_commits("my-org/internal-classifier")[:5]:
    print(f"{c.created_at:%Y-%m-%d}  {c.authors[0]:<16} {c.title}")
```

**企業環境的三條規則：**

1. **內部模型一律 private + 組織 repo**，不要放在個人帳號下——人員異動時 repo 會跟著走。
2. **CI 只給 fine-grained write token，並限定到單一 repo。**
3. **公開發布前檢查 repo 歷史。** Git 會保留所有 commit，如果你曾經不小心推過含真實客戶資料的 dataset，把它 delete 掉是不夠的——歷史裡還在。這種情況要開新 repo 重推。

---

## 六、為什麼選 X 不選 Y

### 6.1 Gradio vs FastAPI

```
選擇              選 Gradio 的理由                 選 FastAPI 的理由
──────────────────────────────────────────────────────────────────────
Gradio            30 行就有完整 UI + 串流           需要自訂前端與認證
                  一鍵推到 Spaces                   要接既有系統的 API 契約
                  非工程師能直接試用                 要精細控制限流與計量
──────────────────────────────────────────────────────────────────────
翻轉條件：需要 SLA、多租戶、或 UI 要嵌進既有產品時 → FastAPI。
          實務上兩者常並存：Gradio 給內部驗證，FastAPI 給正式流量
```

### 6.2 vLLM vs TGI

```
選擇              選 vLLM 的理由                   選 TGI 的理由
──────────────────────────────────────────────────────────────────────
vLLM              吞吐通常較高（PagedAttention）    Docker 開箱即用，參數少
                  OpenAI 相容 API，遷移成本近乎零   與 HF 生態整合最緊密
                  社群大、新模型支援最快            內建 Prometheus metrics
                                                   在 HF Inference Endpoints 上原生支援
──────────────────────────────────────────────────────────────────────
翻轉條件：已經在用 HF Inference Endpoints → TGI（就是它在跑）。
          要自架且吞吐是首要指標 → vLLM。
          兩者差距在 2026 年已經不大，選團隊熟悉的那個
```

### 6.3 bitsandbytes vs AWQ / GPTQ

```
選擇              選 bitsandbytes 的理由           選 AWQ/GPTQ 的理由
──────────────────────────────────────────────────────────────────────
bitsandbytes      任何模型都能即時量化              推論快 1.5–2×
                  是 QLoRA 微調的必要條件           品質損失更小（有校準）
                  不需要預先跑量化流程              vLLM/TGI 原生支援
──────────────────────────────────────────────────────────────────────
翻轉條件：訓練/微調 → bitsandbytes（QLoRA 必須）。
          生產推論 → AWQ/GPTQ。
          自己的微調模型要上線 → 先合併 LoRA 回 bf16，再用 AutoAWQ 量化一次
```

### 6.4 push_to_hub vs 自建 S3 / MinIO

```
選擇              選 Hub 的理由                    選自建的理由
──────────────────────────────────────────────────────────────────────
HF Hub            免費 CDN，全球下載快              資料完全不能離開內網
                  Git 版本控制與 diff              已有 MLflow / S3 的既有流程
                  Model Card 生態與可搜尋性         需要自訂稽核與保存政策
                  與所有 HF 工具無縫整合            超大規模下的頻寬成本
──────────────────────────────────────────────────────────────────────
翻轉條件：法遵要求資料不出境 → 自建（可用 huggingface_hub 的 endpoint 參數
          指向自架的 Hub-compatible 服務，程式碼幾乎不用改）
```

### 6.5 pipeline 批次 vs 推論伺服器

```
選擇              選 pipeline 批次的理由           選推論伺服器的理由
──────────────────────────────────────────────────────────────────────
pipeline 批次      離線工作負載（一次跑 10 萬筆）    線上請求、要求低延遲
                  無需常駐服務，跑完即釋放 GPU      並發 > 5
                  程式碼簡單，好排錯                需要 P99 保證
──────────────────────────────────────────────────────────────────────
翻轉條件：離線 ETL / 資料標注 / 批次嵌入 → pipeline 就夠，
          而且成本更低（用完關機）。只要有「使用者在等」→ 推論伺服器
```

---

## 七、系統效應：三種架構的實測對比

情境：7B 模型、繁中客服問答、平均輸入 300 token / 輸出 200 token。

| 指標 | Gradio + transformers | FastAPI + vLLM (A10G) | + 語意快取 + 路由 |
|------|----------------------|----------------------|------------------|
| 並發能力 | 2–3 | 55 | 55（快取命中不佔 GPU） |
| P50 延遲 | 4,200 ms | 980 ms | 340 ms |
| P99 延遲 | 18,000 ms | 2,100 ms | 2,200 ms |
| 首 token 時間（TTFT） | 3,800 ms | 210 ms | 45 ms（命中時） |
| GPU 使用率 | 22% | 87% | 71% |
| 每百萬 token 成本 | $18.4 | $2.1 | $1.3 |
| 上線所需工時 | 0.5 天 | 4 天 | 12 天 |

**這張表要傳達的重點是：從 Gradio 換到 vLLM，成本降低 8.7 倍、延遲降低 4 倍，代價是 3.5 天工時。** 這個投資報酬率在有真實流量後幾乎必然划算；但在還沒有使用者之前做，就只是把 3.5 天花在還不確定有沒有人要的產品上。

---

## 八、常見錯誤與排查

| 症狀 | 原因 | 解法 |
|------|------|------|
| Space 一直顯示 "Building" | `requirements.txt` 裝不起來（多半是 torch 版本） | 在 requirements 明確指定 `torch==2.x.x`，看 Space 的 Build logs |
| vLLM 啟動時 OOM | `--gpu-memory-utilization` 預設 0.9，加上其他程序爆掉 | 降到 0.85，或關掉佔用 GPU 的其他行程 |
| 推上去的模型別人載不了 | 只推了 model，沒推 tokenizer | `tokenizer.push_to_hub(REPO)` |
| repo 大小異常（80GB+） | checkpoint 被一起推上去 | `ignore_patterns=["checkpoint-*"]`，已推的需重建 repo |
| 串流卡住不動 | `model.generate` 在主執行緒阻塞 | 用 `Thread` + `TextIteratorStreamer` |
| Docker TGI 多卡啟動卡死 | 少了 `--shm-size` | 加 `--shm-size 1g` |

---

## 九、動手驗收：把一個模型從挑選到上線

```
Day 1  用第一節的四道篩選器，選出 3 個候選模型
       準備 50 題自己場景的測試集，跑過三個模型並人工評分
       ↓
Day 2  選定模型，用 AWQ 版本啟 vLLM，量測 P50/P99 與吞吐
       寫 Gradio 介面，推到 private Space 給團隊試用
       ↓
Day 3  收集回饋，寫 FastAPI gateway（認證、限流、串流）
       加上 /healthz 與基本 metrics
       ↓
Day 4  如果有微調需求 → 進入第三篇
       如果現成模型已達標 → 直接寫 Model Card 記錄選型依據並上線
```

---

## 十、系列導航

本文是「Hugging Face 實戰」系列的第 2 篇。

← **上一篇：** [Hugging Face 實戰（一）：它到底是什麼，以及如何開始](/posts/hugging-face-part1-getting-started-zh/)

→ **下一篇：** [Hugging Face 實戰（三）：微調實戰 — Datasets、Trainer 與 LoRA/QLoRA](/posts/hugging-face-part3-fine-tuning-zh/)

**系列索引：**
1. 入門與生態系
2. **用模型、跑 App、推送自己的模型** ← 目前
3. 微調（Fine-tuning）
4. 後訓練（Post-training）
5. 端到端實戰：打造完整 LLM 應用
