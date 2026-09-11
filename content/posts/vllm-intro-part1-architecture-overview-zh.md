---
title: "vLLM Intro Part 1 — 全景架構 — 從一次 model.generate() 到一個推論引擎"
date: 2026-09-11T09:00:00+08:00
draft: false
weight: 1
description: "vLLM 原始碼與架構導讀系列第一篇：用一張全景圖說清楚這個 9 萬星的 LLM 推論引擎由哪些子系統組成、一個請求進來之後經過哪些階段、GPU 記憶體到底被誰吃掉，以及 V1 重寫改變了什麼。"
categories: ["all", "ai", "engineering", "infrastructure"]
tags: ["vLLM", "LLM", "AI", "Inference", "PagedAttention", "Architecture", "GPU", "繁體中文"]
authors: ["yen"]
readTime: "24 min"
---

> *大多數人部署 LLM 的方式，是 `pipeline("text-generation")` 加一台 A100，跑得動就上線，跑不動就換 H100。*
> *真正的答案是：LLM 推論的瓶頸幾乎從來不是算力，而是記憶體頻寬與記憶體管理；一張卡能同時服務 3 個人還是 300 個人，差別不在 GPU 型號，在你有沒有一個引擎。*
> *`generate()` 只需要一行。引擎需要一整套子系統。*
> *這個系列拆解的是後者。*

---

## 前言：這個系列要做什麼

[vLLM](https://github.com/vllm-project/vllm)（UC Berkeley Sky Computing Lab 起家，Apache-2.0，2023-02 開源，現由社群與 PyTorch Foundation 生態共同維護）是目前部署量最大的開源 LLM 推論引擎：GitHub 上約 **9.1 萬顆星、2.2 萬 fork**，官方定位是「a high-throughput and memory-efficient inference and serving engine for LLMs」。

它值得逐層讀完，理由不是星星數，而是：**它把「LLM 推論」這件事從一個模型函式呼叫，重新定義成一個作業系統問題。** 分頁、換頁、排程、搶佔、快取、共享——這些名詞你在 vLLM 裡看到的全部是本義，不是比喻。讀它等於讀一份「把 OS 概念套用到 GPU 記憶體」的完整實作。

這個系列分成五篇：

| Part | 主題 | 對應原始碼 |
|---|---|---|
| **Part 1（本篇）** | 全景架構、請求生命週期、記憶體帳本、V0→V1 | `vllm/v1/engine/`、`vllm/config.py` |
| Part 2 | PagedAttention 與 KV Cache 管理、Prefix Caching | `vllm/v1/core/kv_cache_manager.py`、`csrc/attention/` |
| Part 3 | 連續批次、統一排程器、Chunked Prefill、投機解碼 | `vllm/v1/core/sched/scheduler.py` |
| Part 4 | 分散式推論、量化、torch.compile 與 CUDA Graph | `vllm/distributed/`、`vllm/compilation/` |
| Part 5 | 生產部署：API 面、Multi-LoRA、可觀測性、P/D 分離 | `vllm/entrypoints/openai/`、`vllm/distributed/kv_transfer/` |

本篇的目標很單純：**讀完之後，你能在腦中畫出 vLLM 的方塊圖，說得出一個 token 是怎麼從 HTTP request 走到 SSE chunk，並且知道你那張 80 GB 的卡上，每一 GB 分別被誰吃掉。**

本文以 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）為準。vLLM 迭代極快，細節請以你 pip 裝的版本為準。

---

## 一、核心問題：`model.generate()` 在哪裡壞掉

先講清楚 vLLM 存在的理由。一個「教學版推論服務」長這樣：

```
HTTP request ──▶ tokenizer ──▶ model.generate(input_ids) ──▶ decode ──▶ response
                                        │
                                        └── 一次一個請求，或湊滿 8 個一起跑
```

這條路徑在 demo 上可以跑，在真實流量上會在四個地方同時壞掉。要理解為什麼，得先看清楚 LLM 推論其實是**兩個性質完全不同的階段**。

### 1.1 Prefill 與 Decode：一個算力受限，一個頻寬受限

```
使用者輸入：「請解釋 PagedAttention」  (假設 8 個 token)

┌──────────────── Prefill 階段（一次） ────────────────┐
│  8 個 token 一起送進模型                              │
│  每層做一次 8×8 的 attention，GEMM 形狀肥             │
│  → GPU 算力吃滿，compute-bound                        │
│  → 產出：8 個 token 的 K/V（存進 KV cache）+ 第 1 個輸出 token │
└──────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────── Decode 階段（重複 N 次） ────────────┐
│  每次只送 1 個 token 進去                             │
│  但要把「整個模型的權重」從 HBM 讀進 SM 一遍          │
│  GEMM 退化成 GEMV，算力使用率常低於 5%                │
│  → 記憶體頻寬吃滿，memory-bound                       │
│  → 每次產出 1 個 token，KV cache 長度 +1              │
└──────────────────────────────────────────────────────┘
```

這個不對稱是整個推論優化領域的起點。**Decode 階段每產生一個 token，都要把幾十 GB 的權重從 HBM 搬一次。** 一個 70B 的 FP16 模型是 140 GB 權重；H100 的 HBM3 頻寬約 3.35 TB/s，理論上每秒最多搬 24 次權重，也就是**單一序列的解碼上限大約每秒 24 個 token**——不管你的 GPU 有多少 TFLOPS。

結論很反直覺但很重要：**單條序列的解碼速度，幾乎完全由記憶體頻寬決定，加算力沒用。** 唯一的解法是**攤提**：同一次權重搬運，順便算 64 條序列的 GEMV。這就是 batching 的全部意義，也是為什麼推論引擎的核心是排程器而不是 kernel。

### 1.2 四個壞點

**壞點一：靜態批次讓 GPU 大部分時間在等。** `generate()` 收滿一個 batch 才跑，跑完整批才收下一批。但同一批裡有人要生 20 個 token、有人要生 2000 個，短的早就好了卻不能離開，長的還沒完別人不能進來。實務上 GPU 利用率常低於 30%。

**壞點二：KV cache 用「連續配置」造成 60–80% 記憶體浪費。** 傳統實作為每個序列預留 `max_model_len` 長度的連續 KV 空間。一個請求可能只生 100 個 token，卻佔了 8192 個 token 的位置。vLLM 論文量測到既有系統「**因碎片化與過度預留，浪費 60%–80% 的記憶體**」——而 KV cache 就是你能同時服務多少人的直接上限。

**壞點三：共同前綴被重複計算。** 同一個 3000 token 的 system prompt，1000 個請求就重算 1000 次 prefill。這部分算力是純粹浪費的。

**壞點四：沒有搶佔機制，長請求會餓死短請求。** 記憶體滿了就 OOM，沒有降級路徑。

vLLM 的四個核心主張，正好一一對應：

| vLLM 主張 | 對應壞點 | 實作位置 |
|---|---|---|
| **Continuous batching** — 以 iteration 為單位調度，完成即離開、新請求隨時插入 | 壞點一 | `vllm/v1/core/sched/scheduler.py` |
| **PagedAttention** — KV cache 分頁存放，非連續配置，浪費壓到 4% 以下 | 壞點二 | `vllm/v1/core/kv_cache_manager.py`、`csrc/attention/` |
| **Automatic Prefix Caching** — 相同前綴的 KV block 直接復用 | 壞點三 | `vllm/v1/core/block_pool.py` |
| **Preemption + recompute** — 記憶體不足時搶佔低優先序列，之後重算 | 壞點四 | `Scheduler._try_schedule()` |

原始論文的量測結果是：相同延遲下，**吞吐量比 HuggingFace Transformers 高最多 24×，比 TGI 高最多 3.5×**。這個數字不是靠更快的 kernel，是靠**不浪費記憶體**——省下來的記憶體換成更大的 batch，更大的 batch 攤提掉權重搬運成本。

**「記憶體就是吞吐量」**——這句話是整個 vLLM 的設計主軸，後面四篇都在展開它。

---

## 二、全景圖：六個子系統

以下是 vLLM 的方塊圖。每個方塊標了對應的原始碼路徑，之後四篇會逐個拆開。

```
             ┌──────────────────────────────────────────────────┐
             │  Entrypoints                                     │
             │  ┌──────────────┐        ┌────────────────────┐  │
             │  │ LLM (離線)   │        │ vllm serve (線上)  │  │
             │  │ entrypoints/ │        │ FastAPI :8000      │  │
             │  │   llm.py     │        │ entrypoints/openai/│  │
             │  └──────┬───────┘        └─────────┬──────────┘  │
             └─────────┼──────────────────────────┼─────────────┘
                       │                          │ tokenize / 多模態載入
                       └────────────┬─────────────┘
                                    │  ZeroMQ IPC（V1：跨進程）
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  EngineCore 進程          vllm/v1/engine/core.py           │
        │                                                            │
        │   ┌──────────────────┐        ┌─────────────────────────┐ │
        │   │   Scheduler      │◀──────▶│   KVCacheManager        │ │
        │   │  統一 token 預算 │  配額   │  BlockPool / FreeQueue  │ │
        │   │  waiting/running │        │  hash → block 快取表    │ │
        │   │ v1/core/sched/   │        │  v1/core/               │ │
        │   └────────┬─────────┘        └─────────────────────────┘ │
        │            │ SchedulerOutput（這一輪跑哪些 req、各幾個 token）│
        └────────────┼───────────────────────────────────────────────┘
                     ▼
        ┌───────────────────────────────────────────────────────────┐
        │  Executor（mp / ray / uni）      vllm/v1/executor/         │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
        │  │ Worker 0 │ │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ ...  │
        │  │  GPU 0   │ │  GPU 1   │ │  GPU 2   │ │  GPU 3   │      │
        │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘      │
        └───────┼────────────┼────────────┼────────────┼────────────┘
                │  每個 Worker 內含一個 GPUModelRunner
                ▼
        ┌───────────────────────────────────────────────────────────┐
        │  GPUModelRunner        vllm/v1/worker/gpu_model_runner.py  │
        │  ┌────────────┐ ┌──────────────┐ ┌────────┐ ┌───────────┐ │
        │  │ InputBatch │▶│ nn.Module    │▶│ Sampler│▶│ 輸出 token│ │
        │  │ 組 tensor  │ │ + Attention  │ │ v1/    │ │           │ │
        │  │ block_table│ │   Backend    │ │ sample/│ │           │ │
        │  └────────────┘ └──────┬───────┘ └────────┘ └───────────┘ │
        └────────────────────────┼───────────────────────────────────┘
                                 ▼
        ┌───────────────────────────────────────────────────────────┐
        │  GPU HBM：權重 + KV Cache 分頁池 + activation 暫存區        │
        └───────────────────────────────────────────────────────────┘
```

六個子系統，一句話各自的職責：

1. **Entrypoints（`vllm/entrypoints/`）** — 兩個入口。`LLM` 類別給離線批次推論（跑評測、產資料集）；`vllm serve` 起一個 FastAPI 服務，提供 OpenAI 相容 API。它們**不做重活**：只負責 tokenize、多模態前處理、以及把請求丟給 EngineCore。
2. **EngineCore（`vllm/v1/engine/core.py`）** — V1 的核心，**跑在獨立進程**。裡面只有兩件事：排程與 KV cache 記帳。它是整個系統唯一知道「現在誰在跑、記憶體還剩多少」的地方。
3. **Scheduler（`vllm/v1/core/sched/scheduler.py`）** — 每個 iteration 決定「這一輪要跑哪些請求、每個請求跑幾個 token」。V1 的排程器不再區分 prefill batch 與 decode batch，統一成一個 `{request_id: num_tokens}` 的 token 預算表——這是 V1 最重要的一個改動，Part 3 會整篇講它。
4. **KVCacheManager（`vllm/v1/core/`）** — GPU 記憶體的分頁管理員。維護 block pool、free block 雙向鏈結串列、以及 `hash → block_id` 的前綴快取表。Part 2 的主角。
5. **Executor / Worker（`vllm/v1/executor/`、`vllm/v1/worker/`）** — 每張 GPU 一個 Worker 進程。單機用 Python `multiprocessing`，多機用 Ray。Worker 負責初始化分散式通訊群組、載入自己那一份權重分片。
6. **GPUModelRunner（`vllm/v1/worker/gpu_model_runner.py`）** — 真正跑 forward 的地方：把 SchedulerOutput 攤平成 tensor（含 block table）、呼叫模型、跑 attention backend、取樣、回傳 token id。CUDA graph 的錄製與重播也在這裡。

### 2.1 V1 的進程拓撲

V1 最容易被忽略但影響最大的改動，是**把 API 伺服器和引擎核心拆成不同進程**：

```
            ┌─────────────────┐          ┌─────────────────┐
            │ APIServer 進程  │          │ APIServer 進程  │   ← --api-server-count N
            │ HTTP + tokenize │   ...    │ HTTP + tokenize │
            └────────┬────────┘          └────────┬────────┘
                     └───────────┬────────────────┘
                                 │ ZeroMQ
                     ┌───────────▼────────────┐
                     │  EngineCore 進程        │  ← 每個 DP rank 一個
                     │  Scheduler + KV 記帳    │
                     └───────────┬────────────┘
                                 │ shared memory / IPC
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
        ┌─────────┐         ┌─────────┐         ┌─────────┐
        │Worker 0 │         │Worker 1 │   ...   │Worker N │  ← 每張 GPU 一個
        │ GPU 0   │         │ GPU 1   │         │ GPU N   │
        └─────────┘         └─────────┘         └─────────┘
```

為什麼要拆？因為 **Python GIL**。V0 時代，HTTP 處理、tokenization、detokenization、排程全部擠在同一個進程裡，當併發拉高，**CPU 端的 tokenize 會直接拖慢 GPU 的排程迴圈**——GPU 明明還有餘裕，但因為 scheduler 拿不到 GIL 而空轉。V1 把 CPU 密集的部分（HTTP、tokenize、多模態解碼）推到 API server 進程，EngineCore 進程只做排程，兩邊用 ZeroMQ 傳 token id。

這個設計的實務後果是：**你的機器需要至少 `2 + N` 顆實體核心**（1 個 API server、1 個 engine core、N 個 GPU worker）。CPU 給太少，GPU 一定跑不滿——這是雲上跑 vLLM 最常見的隱形瓶頸，因為多數人只看 GPU 規格，不看 vCPU 配比。

---

## 三、一個請求的生命週期

把上面的方塊圖換成時間軸。假設使用者送出一個 500 token 的 prompt，要求生成 200 個 token。

```
 t=0     POST /v1/chat/completions
   │
   │  ┌─ API Server 進程 ────────────────────────────────────────┐
   ├─▶│ ① 套用 chat template → 純文字                            │
   │  │ ② tokenizer 編碼 → 500 個 token id                       │
   │  │ ③ 組出 EngineCoreRequest，ZeroMQ 送給 EngineCore          │
   │  └──────────────────────────────────────────────────────────┘
   │
   │  ┌─ EngineCore 進程：Scheduler ─────────────────────────────┐
   ├─▶│ ④ 進 waiting queue                                       │
   │  │ ⑤ 查前綴快取：前 480 token 命中（system prompt 別人用過） │
   │  │    → 直接復用 30 個 block，只需 prefill 剩下 20 個 token  │
   │  │ ⑥ 向 KVCacheManager 要 block：ref_cnt++、從 free queue 摘除│
   │  │ ⑦ 這一輪 token 預算 8192，分配 20 個給它 → 進 running     │
   │  └──────────────────────────────────────────────────────────┘
   │
   │  ┌─ GPUModelRunner ─────────────────────────────────────────┐
   ├─▶│ ⑧ 攤平成 tensor：input_ids[20]、positions[20]、block_table │
   │  │ ⑨ forward：PagedAttention 依 block_table 去分頁池取 K/V   │
   │  │ ⑩ Sampler：temperature / top_p / 結構化約束 → 第 1 個 token│
   │  └──────────────────────────────────────────────────────────┘
   │
 t≈30ms  ← TTFT（Time To First Token）：第一個 token 回到使用者
   │
   │  ┌─ 接下來 199 個 iteration，每輪 ────────────────────────────┐
   ├─▶│ 排程器把它和其他 60 個請求放進同一個 batch                 │
   │  │ 每個請求貢獻 1 個 token → batch 形狀 [61, hidden]          │
   │  │ 權重搬一次，61 條序列一起前進 → 這就是攤提                 │
   │  │ 每 16 個 token 用滿一個 block，就向 KVCacheManager 再要一個│
   │  └──────────────────────────────────────────────────────────┘
   │
 t≈30ms + 199×15ms ≈ 3.0s   ← 每個 token 約 15ms = TPOT / ITL
   │
   ├─▶ 產生 EOS 或達到 max_tokens
   │   KVCacheManager：ref_cnt--，block 依 LRU 順序放回 free queue 尾端
   │   （注意：block 內容不清空，之後前綴命中還能救回來）
   ▼
 t≈3.0s  串流結束，回傳 finish_reason
```

有三個細節值得單獨標出來：

**細節一：⑤ 的前綴命中直接吃掉 96% 的 prefill 成本。** 這不是選配優化，V1 預設開啟。你的 system prompt 越長、越固定，這個機制省得越多。Part 2 會講它怎麼做到不出錯。

**細節二：⑦ 的「分配 20 個 token」是可以被切開的。** 如果這個請求需要 prefill 5000 個 token，而本輪預算只剩 2000，排程器會只跑 2000 個，剩下 3000 留到下一輪——這叫 chunked prefill。它的目的是**不讓一個長 prompt 的 prefill 把所有人的 decode 卡住**。Part 3 主題。

**細節三：釋放時 block 不清空。** 這是 vLLM 記憶體管理最漂亮的一手：free queue 是 LRU 序，block 只有在真的要被別人拿去用的當下才失效。所以一個剛結束的對話，30 秒後使用者追問，前綴很可能還在。

---

## 四、三個演進階段

同一個 vLLM，在不同規模下該長成完全不同的樣子。以下用三個階段說明。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：POC —— 單卡、單模型、< 10 QPS           ║
### ╚═══════════════════════════════════════════════════╝

```
┌──────────────┐      ┌────────────────────────────────┐
│  你的 App    │─────▶│  vllm serve Qwen3-8B            │
│              │ HTTP │  單一進程組，1×A100 80G / L40S  │
└──────────────┘      │  TP=1, gpu-mem-util=0.90        │
                      └────────────────────────────────┘
```

**指令**：

```bash
vllm serve Qwen/Qwen3-8B \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

就這樣。**這個階段不要調任何參數。** V1 的預設值（前綴快取開、chunked prefill 開、torch.compile 開、CUDA graph piecewise 模式）已經是多數場景的合理解。

- **可接受的捷徑**：沒有備援、沒有 autoscaling、模型直接從 HuggingFace 拉、tokenizer 和引擎同進程。
- **能撐多久**：8B FP16 模型佔 16 GB，80 GB 卡上還有約 55 GB 給 KV cache。以 8192 context 算，大約可以放 400–600 條併發序列——**遠超過你 POC 階段的流量**。
- **成本**：單張 A100 雲上約 $1.5–2.5/hr，月約 $1.1k–1.8k。
- **解決了什麼**：能用、延遲可接受、API 和 OpenAI 相容所以前端不用改。
- **還沒解決什麼**：機器掛了就全掛；模型換版本要停機；沒有任何指標；長 prompt 進來會把短請求的 ITL 拖爛（因為你還沒調 `max_num_batched_tokens`）。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：MVP —— 單機多卡、K8s、10–200 QPS        ║
### ╚═══════════════════════════════════════════════════╝

```
                    ┌────────────────────────────┐
    ┌──────────┐    │  Ingress / Gateway         │
    │ 客戶端   │───▶│  （限流、認證、路由）       │
    └──────────┘    └──────────┬─────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
      │ vLLM Pod #1   │ │ vLLM Pod #2   │ │ vLLM Pod #3   │
      │ 4×H100, TP=4  │ │ 4×H100, TP=4  │ │ 4×H100, TP=4  │
      │ 70B FP8       │ │ 70B FP8       │ │ 70B FP8       │
      └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
              └────────┬────────┴─────────────────┘
                       ▼
          ┌─────────────────────────────┐
          │ Prometheus + Grafana        │
          │ /metrics（TTFT/ITL/KV 使用率│
          │  /前綴命中率/佇列長度）      │
          └─────────────────────────────┘
```

**相對 Phase 1 新增的元件**：

| 新增 | 為什麼 |
|---|---|
| K8s Deployment + readiness probe（`/health`） | 節點掛掉自動重拉；模型載入約 1–3 分鐘，probe 沒設好會被誤殺 |
| 多副本 + 負載平衡 | 單點故障消失；但要注意**前綴快取是 per-pod 的**，隨機路由會浪費命中率 |
| Prometheus 抓 `/metrics` | 沒有 TTFT/ITL 的百分位數，你連 SLO 有沒有破都不知道 |
| 模型權重放共用儲存（PVC / S3 + 本地快取） | 每個 pod 各自從 HF 拉 140 GB，啟動要 20 分鐘且會被限流 |
| `--tensor-parallel-size 4` | 70B FP8 是 70 GB 權重，單卡放不下，或放得下但沒空間給 KV |
| FP8 量化 | 權重從 140 GB 砍到 70 GB，省下的 70 GB 全部變成 KV cache |
| `--max-num-batched-tokens` 明確設定 | 預設值對你的 prompt 長度分布不一定合適 |

**指令**：

```bash
vllm serve meta-llama/Llama-3.3-70B-Instruct-FP8 \
  --tensor-parallel-size 4 \
  --max-model-len 32768 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.92 \
  --enable-prefix-caching \
  --served-model-name gpt-4o-mini
```

- **成本 delta**：Phase 1 的 1 張卡變成 3×4=12 張 H100，雲上約 $30–45/hr，月約 $22k–33k。**成本跳了 20 倍，這是最痛的一步。**
- **複雜度 delta**：從「一個指令」變成「一份 Helm chart + 一組 dashboard + 一份 runbook」。
- **解決了什麼**：高可用、可觀測、能撐住 100+ QPS、模型可以滾動更新。
- **還沒解決什麼**：前綴快取在多副本之間不共享（同一個使用者的第二輪對話可能打到別的 pod，重算整段歷史）；prefill 與 decode 還混在同一個 batch，長 prompt 進來時 P99 ITL 仍會抖；擴容以 pod 為單位，粒度是 4 張卡。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：Scale —— 多機、P/D 分離、200 QPS – 1M MAU║
### ╚═══════════════════════════════════════════════════╝

```
                  ┌──────────────────────────────────────┐
   ┌──────────┐   │  智慧路由器（prefix-aware routing）    │
   │ 客戶端   │──▶│  依 prompt hash 把同前綴導向同一組     │
   └──────────┘   └──────┬────────────────────┬──────────┘
                         │                    │
       ┌─────────────────▼──────┐   ┌─────────▼────────────────┐
       │  Prefill 叢集           │   │  Decode 叢集              │
       │  TP=8，大 batch         │   │  TP=8 + DP，大併發        │
       │  最佳化 TTFT            │   │  最佳化 ITL 與吞吐        │
       │  ┌─────┐ ┌─────┐        │   │  ┌─────┐ ┌─────┐ ┌─────┐ │
       │  │ P1  │ │ P2  │        │   │  │ D1  │ │ D2  │ │ D3  │ │
       │  └──┬──┘ └──┬──┘        │   │  └──▲──┘ └──▲──┘ └──▲──┘ │
       └─────┼───────┼───────────┘   └─────┼───────┼───────┼────┘
             │       │                     │       │       │
             └───────┴──── KV Connector ───┴───────┴───────┘
                       （NIXL / Mooncake，RDMA 直傳 KV）
                                │
                   ┌────────────▼─────────────┐
                   │  多層 KV 儲存             │
                   │  GPU HBM → CPU DRAM → SSD │
                   │  （LMCache / Offloading）  │
                   └──────────────────────────┘
```

**相對 Phase 2 新增的元件**：

| 新增 | 為什麼 |
|---|---|
| Prefill / Decode 分離部署 | prefill 是 compute-bound、decode 是 memory-bound，混在一起兩邊都不最佳；分開後可以**各自獨立調 TP 與副本數** |
| KV Connector（NIXL / Mooncake） | P 算完的 KV 要送給 D，走 RDMA 而不是重算 |
| 前綴感知路由 | 讓同一個 session、同一份文件的請求打到同一組 pod，把跨 pod 的前綴快取失效問題壓下去 |
| KV 多層卸載（LMCache 等） | HBM 放不下的熱前綴放 DRAM/SSD，命中 DRAM 仍比重算 prefill 快一個量級 |
| DP + EP（MoE 模型） | MoE 的 expert 層適合 EP，attention 層適合 TP/DP，混合策略 |
| 投機解碼（EAGLE / MTP） | 低 QPS 時段用來壓 ITL |

- **成本 delta**：卡數再乘 3–5 倍，但**單位 token 成本會下降**——因為 P/D 分離後兩邊都能跑在自己的最佳工作點。實測上 P/D 分離不會提高總吞吐（官方文件明說「does not improve overall throughput」），它買的是**尾延遲的穩定**與**兩個階段可獨立擴容**。
- **複雜度 delta**：這是質變。你現在要維運一個分散式系統：KV 傳輸失敗要有 fallback、P 和 D 的副本比例要跟著流量形狀調、路由器本身變成新的單點。
- **解決了什麼**：P99 TTFT 與 P99 ITL 可以分別下 SLO 並分別達成；長文件場景（RAG、程式碼庫）的前綴命中率從 30% 拉到 80%+。
- **還沒解決什麼**：跨 region、模型多租戶隔離、以及最難的一題——**成本歸因**：哪個客戶吃掉了你的 KV cache。

**什麼時候該從 Phase 2 跳到 Phase 3？** 三個訊號任一出現即可考慮：(a) `vllm:prefix_cache_hits / vllm:prefix_cache_queries` 長期低於 0.4 而你的 workload 明明有共同前綴；(b) P99 TTFT 與 P50 TTFT 差距超過 5 倍；(c) 你已經在為了壓 ITL 而刻意調低 `max_num_batched_tokens`，卻因此犧牲了吞吐。

---

## 五、記憶體帳本：你那 80 GB 到底被誰吃掉

這是 vLLM 最該先算清楚、卻最少人算的一件事。啟動時 vLLM 會做一次 **memory profiling**：先載入權重，再跑一次假的 forward 量出峰值 activation，然後把剩下的全部劃給 KV cache。

```
┌────────────────────────────────────────────────────────────┐
│  GPU 總記憶體 80 GB (H100 / A100 80G)                       │
├────────────────────────────────────────────────────────────┤
│ ① 模型權重           │ 16 GB   │ 8B × FP16 = 2 bytes/param  │
├──────────────────────┼─────────┼────────────────────────────┤
│ ② 非 torch 開銷      │ ~1 GB   │ NCCL buffer、CUDA context  │
├──────────────────────┼─────────┼────────────────────────────┤
│ ③ 峰值 activation    │ ~4 GB   │ 由 profiling 實測，與      │
│                      │         │ max_num_batched_tokens 相關│
├──────────────────────┼─────────┼────────────────────────────┤
│ ④ CUDA Graph 記憶體  │ ~1-3 GB │ V1 比 V0 吃更多，可用      │
│                      │         │ cudagraph_capture_sizes 調 │
├──────────────────────┼─────────┼────────────────────────────┤
│ ⑤ KV Cache 分頁池    │ ~48 GB  │ = 80×0.9 − ① − ② − ③ − ④   │
│    ← 剩下的全部       │         │ 這就是你的併發上限         │
├──────────────────────┼─────────┼────────────────────────────┤
│ ⑥ 保留給系統         │ 8 GB    │ 80 × (1 − 0.90)            │
└──────────────────────┴─────────┴────────────────────────────┘
```

`--gpu-memory-utilization`（預設 0.9）控制的是 ①–⑤ 的**總和上限**，不是只有 KV cache。這是最常見的誤解。把它從 0.90 調到 0.95，你多拿到的 4 GB **全部**進 KV cache 池——但同時你也把 OOM 的緩衝從 8 GB 砍到 4 GB。

### 5.1 每個 token 的 KV cache 要多少記憶體

公式：

```
每 token 每層 KV 位元組 = 2 (K 和 V) × num_kv_heads × head_dim × dtype_bytes
每 token 總位元組       = 上式 × num_layers
```

三個實例（FP16 KV cache）：

| 模型 | 層數 | KV heads | head_dim | 每 token | 8192 context 一條序列 |
|---|---|---|---|---|---|
| Llama-3-8B（GQA 8） | 32 | 8 | 128 | 128 KB | 1.0 GB |
| Llama-3-70B（GQA 8） | 80 | 8 | 128 | 320 KB | 2.5 GB |
| Llama-2-13B（MHA 40） | 40 | 40 | 128 | 800 KB | 6.4 GB |

注意最後一行：**沒有 GQA 的舊模型，KV cache 大到離譜**。vLLM 論文提到 LLaMA-13B 單一序列的 KV 最多可佔 1.7 GB，就是這個意思。GQA（Grouped-Query Attention）把 KV head 從 40 砍到 8，等於把 KV cache 直接除以 5——**這是近年模型架構對推論成本影響最大的一個改動**，比任何 kernel 優化都有效。

### 5.2 反推你的併發上限

有了上面兩張表，你可以直接算：

```
可容納的總 token 數 = KV 池大小 / 每 token 位元組

例：8B 模型、80 GB 卡、KV 池 48 GB
  48 GB / 128 KB = 約 393,000 個 token

如果平均每條序列（prompt + 輸出）2000 token：
  393,000 / 2000 ≈ 196 條併發序列

如果平均 32,000 token（長文件 RAG）：
  393,000 / 32,000 ≈ 12 條併發序列   ← 差 16 倍
```

**這個算式解釋了 90% 的「為什麼我的 vLLM 這麼慢」。** 不是引擎慢，是你的 context 太長，導致併發數掉到兩位數，batch 湊不起來，權重搬運無從攤提。啟動日誌裡的 `GPU KV cache size: X tokens` 和 `Maximum concurrency for N tokens per request: Y x` 這兩行，是你最該先看的兩個數字。

如果 Y 小於 10，你有四條路：開 KV cache FP8 量化（記憶體減半）、降 `max_model_len`、加 TP、或換成 GQA/MLA 架構的模型。

---

## 六、V0 → V1：重寫了什麼

vLLM 在 0.8 之後把引擎整個重寫成 V1，並在後續版本移除 V0。理解這個轉折能省下你很多讀舊教學的困惑。

| 面向 | V0 | V1 |
|---|---|---|
| 進程模型 | API server 與引擎同進程，GIL 爭用 | API server / EngineCore / Worker 三層分離 |
| 排程 | prefill batch 與 decode batch 分開，兩套邏輯 | **統一 token 預算**，一個 `{req_id: n_tokens}` 字典 |
| Chunked prefill | 選配，依模型啟發式決定 | **預設開啟**，所有場景 |
| Prefix caching | 選配 | **預設開啟** |
| CUDA Graph | 全圖捕捉，attention 也在圖裡 | **Piecewise**：以 attention 為切點，圖只捕捉中間段 |
| torch.compile | 選配 | **預設開啟**，且啟動前編譯完畢，服務中不會再觸發編譯 |
| KV 換頁到 CPU（swap） | 有 | **移除**，統一用 recompute |
| `best_of` 取樣 | 有 | **移除** |
| 每請求 logits processor | 有 | **移除**（架構不相容） |
| logprobs 語意 | 後處理過的 | **原始 logits**，可用 `--logprobs-mode` 切換 |

四個設計目標寫在官方 V1 指南裡：**簡潔的模組結構、接近零的 CPU 開銷、統一的優化整合路徑、以及零設定預設值（功能自動開啟）**。

最後一點對使用者影響最大：**V1 的哲學是「不要調參」**。前綴快取、chunked prefill、torch.compile、CUDA graph 全部預設開。你唯一該主動設的通常只有三個：`--max-model-len`、`--tensor-parallel-size`、`--gpu-memory-utilization`。

被移除的功能要特別注意：如果你的舊程式碼用 `best_of` 或自訂 logits processor，遷移到 V1 會直接壞掉，需要改用 `n` 參數或結構化輸出來達成類似效果。

---

## 七、效能語彙：四個數字與它們的互斥關係

談 vLLM 調參之前，得先把詞彙統一。四個數字：

```
       請求送出                                        最後一個 token
           │                                                  │
           ├──────── TTFT ────────┤                           │
           │   (Time To First Token)                          │
           │   = 排隊時間 + prefill 時間                       │
           │                       │                          │
           │                       ├──┬──┬──┬──┬──┬──┬──┬──┬──┤
           │                          ↕                       │
           │                        TPOT / ITL                │
           │                   (每個輸出 token 的間隔)          │
           │                                                  │
           ├──────────────── E2E Latency ─────────────────────┤

Throughput  = 整個系統每秒吐出的總 token 數（output tokens/s）
Goodput     = 其中「滿足 SLO」的那部分 —— 真正該被優化的目標
```

它們**互相拉扯**，這是推論調參的全部難度所在：

| 你調的旋鈕 | TTFT | ITL | 吞吐 | 原因 |
|---|---|---|---|---|
| `max_num_batched_tokens` ↑（如 2048→16384） | ↓ 變好 | ↑ 變差 | ↑ 變好 | 一輪能塞更多 prefill，但 decode 要等更久的 forward |
| `max_num_seqs` ↑ | — | ↑ 變差 | ↑ 變好 | batch 更大，攤提更好，但每輪更慢 |
| `gpu_memory_utilization` ↑ | ↓ 變好 | ↓ 變好 | ↑ 變好 | KV 池變大 → 搶佔變少（但 OOM 風險上升） |
| 開投機解碼 | — | ↓ 變好 | ↓ 變差（高負載時） | 用額外算力換 token 步數 |
| TP ↑ | ↓ 變好 | ↓ 變好 | 次線性提升 | 每卡負擔變小，但多了 all-reduce 通訊 |
| P/D 分離 | ↓ 穩定 | ↓ 穩定 | — 不變 | 買的是尾延遲穩定，不是總吞吐 |

**一個實務原則**：先定義 SLO（例如「P95 TTFT < 500ms 且 P95 ITL < 50ms」），然後最大化在此約束下的吞吐。直接優化 raw throughput 幾乎必然做出一個延遲很爛的系統——因為最大吞吐點通常出現在佇列很長的地方。

---

## 八、為什麼選 vLLM 不選 X

推論引擎的選擇不是非黑即白。以下是六個真實的比較。

```
選擇                選 vLLM 的理由                     不選對方的理由 / 對方何時更好
────────────────────────────────────────────────────────────────────────────────
vLLM               連續批次 + 分頁 KV，高併發吞吐最強    HF Transformers：沒有批次調度，
vs HF Transformers  OpenAI 相容 API 開箱即用             併發下 GPU 利用率 <30%，只適合
                   模型覆蓋面最廣（數百個架構）          單次實驗、教學、或超小模型
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：你只是要跑一次 forward 看看輸出，或要做 training-time
                   的自訂 hook——那 Transformers 更直接，別為此裝一個引擎。

vLLM               純 Python + CUDA kernel，改一行就生效  TensorRT-LLM：同硬體同模型上
vs TensorRT-LLM     模型上線速度以天計                    延遲可再低 10–30%（尤其小 batch），
                   跨廠牌（NVIDIA/AMD/TPU/CPU）           但要 build engine、綁 NVIDIA、
                   社群大、新模型當天就有支援             新模型支援滯後數週到數月
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：模型固定不動、硬體固定是 NVIDIA、且你在為每毫秒延遲付錢
                   （高頻交易式場景）。那 TensorRT-LLM 的編譯期優化值得那份工程成本。

vLLM               通用推論引擎，功能面最完整            SGLang：在「大量共享前綴 +
vs SGLang           生態整合最廣（K8s、Ray、KServe…）     複雜多輪程式化呼叫」場景，
                   Prefix caching 已經補上大部分差距      RadixAttention 的前綴共享更細緻
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：你的 workload 是 agent 式的樹狀分支（同一 prefix 分岔出
                   幾十條路徑），SGLang 的前綴樹結構天生更貼合。兩者近年互相收斂，
                   建議用你的真實 trace 各跑一次 benchmark 再決定。

vLLM               Continuous batching 高併發            TGI：HuggingFace 生態整合更緊，
vs TGI              社群與功能迭代速度更快                Rust 前端 CPU 開銷低。但吞吐在
                   量化與平行策略選項更多                 原論文量測中低 vLLM 最多 3.5×
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：你已經深度綁在 HF Inference Endpoints 上，換掉的遷移
                   成本高於效能收益。

vLLM               GPU 上的吞吐高一個量級以上            llama.cpp / Ollama：單機單人、
vs llama.cpp/Ollama 生產級的 API、指標、多租戶            CPU / Apple Silicon、GGUF 量化到
                   多副本、TP/PP/DP 完整                  4-bit 塞進筆電——這些 vLLM 做不到
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：本機開發、離線、無 GPU、或你要的就是「一個指令跑起來」。
                   別用 vLLM 做本機玩具，也別用 Ollama 扛生產流量。

vLLM               自架、成本可控、資料不出境            商用 API（如 Bedrock 等）：
vs 託管 API         模型與參數完全自主                    無需維運、無需買卡、按量計費
                   高用量下單位成本低 5–20 倍             低用量下自架絕對更貴
                   ─────────────────────────────────────────────────────────────
                   翻轉條件：日均 token 量低於約 5,000 萬，或團隊沒有 GPU 維運能力。
                   算一下：一張 H100 月租約 $2.5k，能吐多少 token？除下去和 API
                   單價比。低於損益點就別自架——這是純算術題，不是技術偏好。
```

---

## 九、系統效應：vLLM 相對 naive 推論改了什麼

把本篇提到的設計整理成一張對照表——這也是後面四篇要逐一驗證的清單。

| 環節 | naive 做法（`model.generate()`） | vLLM 做法 | 效果 |
|---|---|---|---|
| 批次 | 靜態批次，湊滿才跑、跑完才換 | 連續批次，以 iteration 為單位進出 | GPU 利用率從 <30% 拉到 >80% |
| KV 記憶體 | 每序列預留 `max_len` 連續空間 | 16 token 一頁的分頁池，非連續配置 | 浪費從 60–80% 降到 <4% |
| 共同前綴 | 每次重算 | hash 鏈比對，命中直接復用 block | 長 system prompt 場景 TTFT 降 5–20× |
| 長 prompt | 整段 prefill，塞住所有人 | Chunked prefill，切成小塊與 decode 混跑 | P99 ITL 抖動大幅收斂 |
| 記憶體不足 | OOM | 搶佔 + 之後重算 | 從「掛掉」變成「變慢」 |
| 平行取樣 | 每條各存一份 KV | Copy-on-Write 共享 block | 記憶體省最多 55%，吞吐最多 2.2× |
| 多卡 | 手寫 device_map | TP / PP / DP / EP 四種平行度可組合 | 70B 以上模型可服務化 |
| Kernel 啟動開銷 | 每層一次 Python dispatch | torch.compile + piecewise CUDA graph | 小模型的 CPU 開銷幾乎消失 |
| 可觀測性 | 無 | `/metrics` 完整 Prometheus 指標 | TTFT/ITL/KV 使用率/命中率可下 SLO |
| API | 自己寫 Flask | OpenAI 相容（chat/completions/embeddings/…） | 前端零改動即可切換 |

---

## 十、系列導航

本篇建立了地圖：六個子系統、一個請求的生命週期、三個部署階段、以及那張決定一切的記憶體帳本。

接下來四篇逐層下鑽：

- **Part 2 — PagedAttention 與 KV Cache**：分頁的完整機制（logical/physical block、block table）、kernel 層的記憶體佈局（為什麼是 `[num_blocks, num_kv_heads, head_size/x, block_size, x]`）、Copy-on-Write 共享、自動前綴快取的 hash 鏈與 LRU 淘汰、以及 KV cache 量化。
- **Part 3 — 排程器**：連續批次的實作、V1 統一 token 預算排程器、chunked prefill 的 TTFT/ITL 取捨、搶佔與重算、投機解碼的接受率數學，以及一份調參手冊。
- **Part 4 — 分散式與編譯優化**：TP/PP/DP/EP 四種平行度的通訊量分析、多機部署與 NCCL 排錯、量化方法與硬體支援矩陣、torch.compile 的 piecewise CUDA graph、attention backend 選擇。
- **Part 5 — 生產部署**：OpenAI 相容 API 全表、Multi-LoRA、結構化輸出、指標與症狀診斷鏈、P/D 分離與 KV connector、benchmark 與容量規劃。

→ [vLLM Intro Part 2 — PagedAttention 與 KV Cache — 把作業系統的分頁搬進 GPU](../vllm-intro-part2-paged-attention-kv-cache-zh)

---

*本文基於 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）與官方文件撰寫。所有參數名稱、預設值與架構描述皆對照官方文件與原始碼；記憶體、成本與延遲數字為量級估算，實際值依硬體、模型與工作負載而異。vLLM 迭代極快，細節請以你安裝的版本為準。*
