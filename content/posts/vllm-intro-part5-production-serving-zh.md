---
title: "vLLM Intro Part 5 — 生產部署與服務化 — 從 vllm serve 到一份可被驗收的 SLO"
date: 2026-09-11T13:00:00+08:00
draft: false
weight: 5
description: "vLLM 原始碼導讀系列最終篇：拆解 OpenAI 相容 API 的完整面、Multi-LoRA 多租戶服務、結構化輸出的取樣層約束、Prometheus 指標全表與症狀診斷鏈、P/D 分離與 KV Connector 的實際配置，以及一套不會騙自己的 benchmark 方法。"
categories: ["all", "ai", "engineering", "infrastructure", "architecture"]
tags: ["vLLM", "Production", "LoRA", "Structured Output", "Observability", "Prometheus", "Kubernetes", "繁體中文"]
authors: ["yen"]
readTime: "28 min"
---

> *大多數人上線 LLM 服務的方式，是把 `vllm serve` 包進 Dockerfile，接上 LB，看到 200 就宣布完成。*
> *真正的答案是：一個推論服務的難度不在啟動，在於你能不能回答三個問題——現在慢在哪裡、加一張卡能買到多少、以及這個數字明天還會不會是真的。*
> *能回答，你有一個服務。不能回答，你有一個會在流量尖峰當天讓你熬夜的黑箱。*

---

## 前言

前四篇拆完了引擎：[記憶體](../vllm-intro-part2-paged-attention-kv-cache-zh)、[排程](../vllm-intro-part3-scheduler-continuous-batching-zh)、[平行化與量化](../vllm-intro-part4-distributed-quantization-zh)。這一篇處理最後一段路——**把引擎變成服務**。

這段路上有五件事：對外的 API 面要長什麼樣、一個模型怎麼服務多個租戶、怎麼保證輸出格式可被程式解析、怎麼知道系統現在的狀態、以及怎麼在成本與 SLO 之間找到那個點。

本篇的目標：**讀完之後，你有一份可以直接照抄的生產檢查清單，以及一套從 Grafana 指標反推根因的方法。**

---

## 一、核心問題：從「跑得起來」到「可被驗收」

```
┌──────────────────────────────────────────────────────────────┐
│                      vllm serve <model>                       │
│                            ✓ 跑起來了                          │
└──────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌────────────────┐    ┌────────────────┐
│ 問題 ①        │    │ 問題 ②         │    │ 問題 ③         │
│ 「現在慢在    │    │ 「加一張卡能   │    │ 「這個數字明天 │
│   哪裡？」    │    │   買到多少？」 │    │   還算數嗎？」 │
├───────────────┤    ├────────────────┤    ├────────────────┤
│ 需要：        │    │ 需要：         │    │ 需要：         │
│ · 分階段指標  │    │ · 可信的       │    │ · 回歸測試     │
│   (queue/     │    │   benchmark    │    │ · 版本鎖定     │
│    prefill/   │    │ · 容量模型     │    │ · 品質監控     │
│    decode)    │    │ · 飽和曲線     │    │ · 金絲雀發布   │
│ · 症狀→根因鏈 │    │                │    │                │
└───────────────┘    └────────────────┘    └────────────────┘
```

這三個問題對應本篇的第六、八、九節。在那之前，先把服務面補齊。

---

## 二、三個演進階段

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：單機 Docker —— 能對外服務                ║
### ╚═══════════════════════════════════════════════════╝

```
┌─────────────┐        ┌─────────────────────────────┐
│  你的後端   │───────▶│  vLLM 容器 :8000             │
│             │ OpenAI │  vllm/vllm-openai:vX.Y.Z     │
└─────────────┘  SDK   │  --api-key sk-xxx            │
                       └─────────────────────────────┘
```

```bash
docker run --gpus all -p 8000:8000 \
  --shm-size=16g \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/.cache/vllm:/root/.cache/vllm \
  vllm/vllm-openai:v0.19.1 \
  --model Qwen/Qwen3-8B \
  --served-model-name gpt-4o-mini \
  --api-key $VLLM_API_KEY \
  --max-model-len 8192
```

四個容易漏掉的細節：

| 參數 | 為什麼必要 |
|---|---|
| `--shm-size=16g` | Docker 預設 `/dev/shm` 只有 64 MB，多進程通訊會炸 `Bus error` |
| 掛 `~/.cache/vllm` | torch.compile 快取，不掛的話每次重啟重編譯 5 分鐘 |
| `--served-model-name` | 讓客戶端的 model 欄位不用改（可以偽裝成既有模型名，平滑遷移） |
| 鎖定 image tag | 絕對不要用 `:latest`。vLLM 迭代快，行為可能在小版本間變化 |

- **可接受的捷徑**：無備援、無指標、金鑰用環境變數、沒有限流。
- **還沒解決什麼**：一切生產問題。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：K8s + 可觀測性 —— 可被驗收               ║
### ╚═══════════════════════════════════════════════════╝

```
                ┌────────────────────────────────────────┐
                │  Gateway：認證、限流、用量計費          │
                └────────────────┬───────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
      │ vLLM Pod ×3  │  │ vLLM Pod     │  │ vLLM Pod     │
      │ TP=2         │  │              │  │              │
      │ + N 個 LoRA  │  │              │  │              │
      │ /metrics     │  │ /metrics     │  │ /metrics     │
      │ /health      │  │ /health      │  │ /health      │
      └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
             └─────────────────┼─────────────────┘
                               ▼
        ┌────────────────────────────────────────────────┐
        │ Prometheus → Grafana → Alertmanager             │
        │ · TTFT/ITL P50/P95/P99                          │
        │ · KV 使用率、前綴命中率、佇列長度                │
        │ · 每個 LoRA 的用量（計費）                       │
        └────────────────────────────────────────────────┘
```

**新增元件與理由**：

| 新增 | 為什麼 |
|---|---|
| readiness probe 指向 `/health`，`initialDelaySeconds: 300` | 模型載入 + 編譯要數分鐘；預設值會讓 pod 被無限重啟 |
| liveness probe 但**不要太敏感** | 長 prefill 時 HTTP 可能短暫無回應，太敏感會誤殺 |
| Prometheus ServiceMonitor 抓 `/metrics` | 第六節 |
| `--api-key` + Gateway 二層認證 | vLLM 的 api-key 是單一共享金鑰，做不到 per-tenant |
| PVC 掛 HF cache 與 compile cache | 啟動時間從 20 分鐘降到 2 分鐘 |
| 資源請求：CPU ≥ `2 + N` 實體核心 | Part 1 提過，CPU 不足會直接拖垮 GPU |
| HPA 依 `vllm:num_requests_waiting` 而非 CPU | CPU 使用率對 GPU 服務毫無意義 |

- **成本 delta**：卡數 ×3 起跳，加上 observability stack。
- **解決了什麼**：高可用、可觀測、可下 SLO。
- **還沒解決什麼**：前綴快取跨 pod 不共享；prefill 與 decode 共用資源導致尾延遲難壓；擴容粒度粗。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：P/D 分離 + 智慧路由 —— SLO 可分別達成    ║
### ╚═══════════════════════════════════════════════════╝

```
        ┌─────────────────────────────────────────────────┐
        │  路由層（prefix-aware + 負載感知）                │
        │  · 依 prompt 前綴 hash 導向同一組 → 提高命中率    │
        │  · 依各 pod 的 KV 使用率做加權                    │
        └──────┬──────────────────────────┬───────────────┘
               │                          │
     ┌─────────▼──────────┐    ┌──────────▼──────────────┐
     │  Prefill 池         │    │  Decode 池               │
     │  · 大 max_num_      │    │  · 小 max_num_batched_   │
     │    batched_tokens   │    │    tokens，保 ITL        │
     │  · 高 TP（壓 TTFT） │    │  · 大 max_num_seqs       │
     │  · 副本數依 prompt  │    │  · 副本數依併發會話數    │
     │    長度與 QPS 定    │    │                          │
     └─────────┬──────────┘    └──────────▲──────────────┘
               │   KV Connector（NIXL/Mooncake，RDMA）     │
               └──────────────────────────────────────────┘
                              │
                 ┌────────────▼────────────────┐
                 │ KV 多層儲存（選配）           │
                 │ GPU HBM → CPU DRAM → SSD     │
                 └──────────────────────────────┘
```

- **新增元件**：路由器、KV connector、P/D 兩組獨立的 deployment 與 HPA、以及一套新的失敗模式（KV 傳輸失敗要能 fallback 成本地重算）。
- **成本 delta**：總卡數增加，但**單位 token 成本下降**，因為兩邊各自跑在最佳工作點。
- **重要認知**：官方文件明說 P/D 分離「**不會提升整體吞吐**」。它買的是**尾延遲的可控性**與**兩階段可獨立擴容**。如果你的問題是「吞吐不夠」，P/D 分離不是答案，加卡才是。
- **什麼時候該做**：P99 TTFT / P50 TTFT > 5、或你已經在為了壓 ITL 而犧牲吞吐。

---

## 三、API 面：你對外承諾了什麼

### 3.1 端點全表

| 端點 | 用途 | 需要的模型類型 |
|---|---|---|
| `/v1/chat/completions` | 對話生成（主力） | 有 chat template 的生成模型 |
| `/v1/completions` | 純文字續寫 | 生成模型 |
| `/v1/chat/completions/batch` | 批次對話 | 同上 |
| `/v1/responses`（+ cancel / status） | Responses API 風格 | 生成模型 |
| `/v1/embeddings` | 向量嵌入 | embedding 模型 |
| `/classify` | 分類 | 分類模型 |
| `/score`、`/v1/score` | 成對評分 | cross-encoder |
| `/v1/audio/transcriptions` | 語音轉文字 | ASR 模型（如 Whisper） |
| `/v1/audio/translations` | 語音翻譯 | 同上 |
| `/tokenize`、`/detokenize` | tokenizer 工具 | 任意 |
| `/health` | 健康檢查 | — |
| `/metrics` | Prometheus 指標 | — |
| `/v1/models` | 列出模型與 LoRA | — |
| `/v1/load_lora_adapter`、`/v1/unload_lora_adapter` | 動態 LoRA（需開啟旗標） | — |

**已知的相容性落差**（官方明列）：
- Completions 的 `suffix` 參數不支援
- Chat Completions 的 `user` 參數被忽略
- 沒有 chat template 的模型不能用 chat 端點

第三點是新手最常撞的牆：base model（非 instruct 版）通常沒有 chat template，要用 `--chat-template` 自己給一份，或改用 `/v1/completions`。

### 3.2 vLLM 專屬參數

透過 `extra_body` 傳入：

```python
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[...],
    extra_body={
        # 取樣
        "top_k": 50,
        "repetition_penalty": 1.05,
        "min_p": 0.05,
        # 停止條件
        "stop_token_ids": [128009],
        "include_stop_str_in_output": False,
        # 結構化輸出（見第五節）
        "structured_outputs": {"json": my_schema},
        # 回傳 prompt 的 token（除錯用）
        "echo": False,
        "add_generation_prompt": True,
    },
)
```

### 3.3 一個容易忽略的擴充點：API server 水平擴充

```bash
vllm serve <model> --api-server-count 4
```

當你的 prompt 很短、QPS 很高時，**瓶頸會落在 tokenization 而不是 GPU**。這個旗標啟動多個 API server 進程共享同一個 EngineCore。官方另外提到 `VLLM_USE_FASTOKENS=1` 可讓 BPE tokenizer 快 2–3×。

判斷方式：GPU 利用率低於 60% 但吞吐上不去，且 `vllm:request_queue_time_seconds` 不高 → 大概率是 CPU 端瓶頸。

---

## 四、Multi-LoRA：一個底模服務多個租戶

### 4.1 為什麼這件事重要

```
不用 LoRA：每個客製模型一個實例
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│客戶A模型 │ │客戶B模型 │ │客戶C模型 │ │客戶D模型 │
│ 16 GB    │ │ 16 GB    │ │ 16 GB    │ │ 16 GB    │
│ 1×GPU    │ │ 1×GPU    │ │ 1×GPU    │ │ 1×GPU    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
  4 張卡，每張的 KV 池都只服務一個客戶 → 利用率極低

用 Multi-LoRA：
┌────────────────────────────────────────────────────┐
│  1×GPU                                              │
│  ┌──────────────────────────────────────────────┐  │
│  │ 底模 16 GB（共用）                             │  │
│  ├──────────────────────────────────────────────┤  │
│  │ LoRA A (rank 32) │ LoRA B │ LoRA C │ LoRA D  │  │
│  │    ~100 MB       │ ~100MB │ ~100MB │ ~100MB  │  │
│  ├──────────────────────────────────────────────┤  │
│  │ KV 池 ~55 GB（所有客戶共用，連續批次調度）     │  │
│  └──────────────────────────────────────────────┘  │
│  同一個 batch 裡可以混合不同 LoRA 的請求            │
└────────────────────────────────────────────────────┘
  1 張卡，成本降 75%，且 batch 更大 → 吞吐更好
```

### 4.2 設定

```bash
vllm serve meta-llama/Llama-3.2-3B-Instruct \
  --enable-lora \
  --max-loras 8 \
  --max-lora-rank 64 \
  --max-cpu-loras 32 \
  --lora-modules \
      sql-lora=/models/sql-lora \
      support-lora=/models/support-lora
```

| 參數 | 意義 | 怎麼設 |
|---|---|---|
| `--max-loras` | **同時活躍**在 GPU 上的 adapter 數 | 設成你尖峰時同時有流量的租戶數；越大佔用越多記憶體 |
| `--max-lora-rank` | 所有 adapter 中的最大 rank | 設成實際最大值。若 adapter 的 rank 是 [16,32,64]，設 64；設過大會浪費記憶體 |
| `--max-cpu-loras` | CPU 端快取的 adapter 數 | 設大一點（如 64），swap 到 GPU 很快 |

**注意 `max_loras` 與 `max_cpu_loras` 的關係**：GPU 上只放 `max_loras` 個，其餘在 CPU；請求進來時若 adapter 不在 GPU，會觸發一次 CPU→GPU 的搬運（幾十毫秒）。所以**把 `max_loras` 設成能覆蓋 80% 流量的熱門 adapter 數**是合理的起點。

### 4.3 動態載入

```bash
VLLM_ALLOW_RUNTIME_LORA_UPDATING=True vllm serve <base> --enable-lora
```

```bash
curl -X POST http://localhost:8000/v1/load_lora_adapter \
  -H "Content-Type: application/json" \
  -d '{"lora_name": "new-tenant", "lora_path": "/models/new-tenant"}'
```

這讓「新客戶上線」從「重啟服務」變成「一個 API 呼叫」。**但要注意安全性**：這個端點允許從任意路徑載入權重，**絕對不能對公網開放**，一定要在 Gateway 層擋掉。

### 4.4 使用

```python
# 客戶端只要改 model 名
client.chat.completions.create(model="sql-lora", messages=[...])
```

vLLM 會把 `sql-lora` 對應到底模 + 該 adapter。`/v1/models` 會同時列出底模與所有 adapter。

**計費**：`vllm:` 指標目前不會按 LoRA 分標籤，所以租戶用量計費要在 Gateway 層做（依 model 名稱累計 token 數）。

### 4.5 代價

Multi-LoRA 不是免費的：

| 代價 | 量級 | 緩解 |
|---|---|---|
| 每個 token 多做 LoRA 矩陣運算 | 吞吐降 5–15% | 用較小的 rank |
| adapter 不在 GPU 時要 swap | 首次請求 +20–80 ms | 提高 `max_loras` |
| **前綴快取要分 adapter** | 命中率下降 | Part 2 提過：LoRA id 進 hash。這是正確性要求，不能省 |
| 記憶體佔用 | `max_loras × rank × 層數 × hidden × 2 × 2 bytes` | rank 64、8 個 adapter 的 8B 模型約 1.5 GB |

```
選擇              選 Multi-LoRA 的理由              不選的理由 / 翻轉條件
────────────────────────────────────────────────────────────────────────
Multi-LoRA        成本降 75%+（共用底模與 KV 池）    吞吐降 5–15%
vs 獨立實例       新租戶上線只要一個 API 呼叫        前綴快取按 adapter 分隔
                  batch 更大，GPU 利用率更好         故障域共用（一個 pod 掛
                                                     掉所有租戶受影響）
                  ──────────────────────────────────────────────────────
                  翻轉條件：(a) 只有 1–2 個客製模型且流量都很大 → 獨立實例
                  的隔離性與效能更好；(b) 客戶要求硬體級隔離（合規需求）→
                  必須獨立實例；(c) 微調幅度大到 LoRA 撐不住（需要全參數
                  微調）→ 本來就不是 LoRA 的場景。
```

---

## 五、結構化輸出：讓程式能解析回應

LLM 回「大概是 JSON 的東西」是生產環境的災難來源。vLLM 在**取樣層**強制約束，而不是靠 prompt 拜託模型。

### 5.1 機制

```
每個 decode step：

  模型輸出 logits [vocab_size=152064]
            │
            ▼
  ┌─────────────────────────────────────────────────┐
  │ 語法引擎（xgrammar / guidance / outlines）        │
  │ 依目前的解析狀態，算出「下一個 token 的合法集合」  │
  │ 例：剛輸出 {"name"，下一個必須是 :                │
  └─────────────────────┬───────────────────────────┘
                        ▼
  ┌─────────────────────────────────────────────────┐
  │ 把非法 token 的 logit 設為 -inf                   │
  └─────────────────────┬───────────────────────────┘
                        ▼
            取樣 → 保證輸出一定合法
```

**關鍵差異**：這不是「驗證後重試」，是**在取樣的當下就排除非法選項**。所以輸出 100% 符合 schema，不需要 retry 迴圈。

### 5.2 五種約束

| 類型 | 用途 | 範例 |
|---|---|---|
| `choice` | 限定在幾個選項之一 | 情感分類：`["正面","負面","中性"]` |
| `regex` | 正規表達式 | email、電話、日期格式 |
| `json` | JSON Schema 或 Pydantic 模型 | 結構化抽取 |
| `grammar` | EBNF 上下文無關文法 | 產生合法 SQL、DSL |
| `structural_tag` | 在指定的類 XML 標籤內套 JSON schema | 工具呼叫、混合自然語言與結構 |

### 5.3 用法

```python
from pydantic import BaseModel

class Invoice(BaseModel):
    vendor: str
    amount: float
    currency: str
    line_items: list[str]

# 線上服務（OpenAI SDK）
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": f"抽取發票欄位：{text}"}],
    extra_body={"structured_outputs": {"json": Invoice.model_json_schema()}},
)

# 或用標準的 response_format
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[...],
    response_format={"type": "json_schema",
                     "json_schema": {"name": "invoice",
                                     "schema": Invoice.model_json_schema()}},
)
```

離線推論用 `SamplingParams(structured_outputs=StructuredOutputsParams(json=...))`。

### 5.4 後端與代價

```
--structured-outputs-config.backend auto   # 預設：依請求內容自動選

選擇          選 X 的理由                     不選 Y 的理由
──────────────────────────────────────────────────────────────
xgrammar      效能最好（編譯期預計算遮罩）     複雜 schema 可能不支援，
vs guidance   Rust 風格 regex                  此時會 fallback
vs outlines   ─────────────────────────────────────────────────
              翻轉條件：留 auto。只有在遇到「某個 schema 被拒絕」時才
              手動指定後端。三者的語法細節不同（尤其 regex 方言），
              切換後要重測。
```

**代價與注意事項**：

1. **首次使用某 schema 有編譯成本**（把 schema 編成 FSM/遮罩表），幾十到幾百毫秒。相同 schema 會被快取，所以**固定 schema 的服務只付一次**；每個請求都用不同 schema 的場景要留意。
2. **約束會改變輸出分布**。強制 JSON 可能讓模型「為了合法而說謊」——例如 schema 要求 `amount: float` 但文件裡沒有金額，模型會編一個。**必要欄位應該設計成 `Optional`，並允許 `null`**。
3. **推理模型要特別設定**：讓模型先自由思考再輸出結構化結果，需要 `--structured-outputs-config.enable_in_reasoning` 這類設定（依模型而異），否則約束會把思考過程也一起卡死。
4. **吞吐影響**：每個 step 多一次遮罩計算，實測影響通常在 5% 以內。

---

## 六、可觀測性：從指標反推根因

這是本篇最實用的一節。

### 6.1 指標全表

vLLM V1 在 `/metrics` 以 `vllm:` 前綴輸出：

**Gauge（當下狀態）**

| 指標 | 意義 | 健康範圍 |
|---|---|---|
| `vllm:num_requests_running` | 正在跑的請求數 | 依配置；接近 `max_num_seqs` 代表滿載 |
| `vllm:num_requests_waiting` | 排隊中的請求數 | **持續 > 0 就是容量不足** |
| `vllm:kv_cache_usage_perc` | KV block 使用率（0–1） | 0.6–0.9；> 0.95 會頻繁搶佔 |

**Counter（累計）**

| 指標 | 意義 |
|---|---|
| `vllm:prompt_tokens_total` | 累計 prompt token（計費用） |
| `vllm:generation_tokens_total` | 累計生成 token（計費用） |
| `vllm:request_success_total` | 完成的請求數（依 finish_reason 分標籤） |
| `vllm:prefix_cache_queries` | 前綴快取查詢數 |
| `vllm:prefix_cache_hits` | 前綴快取命中數 |

**Histogram（分布）**

| 指標 | 意義 | 這是你的 SLO |
|---|---|---|
| `vllm:time_to_first_token_seconds` | TTFT | ✓ |
| `vllm:inter_token_latency_seconds` | ITL / TPOT | ✓ |
| `vllm:e2e_request_latency_seconds` | 端到端延遲 | ✓ |
| `vllm:request_queue_time_seconds` | 純排隊時間 | 診斷用 |
| `vllm:request_prefill_time_seconds` | prefill 時間 | 診斷用 |
| `vllm:request_decode_time_seconds` | decode 時間 | 診斷用 |
| `vllm:request_prompt_tokens` | 輸入長度分布 | 容量規劃用 |
| `vllm:request_generation_tokens` | 輸出長度分布 | 容量規劃用 |

**KV block 生命週期（V1 新增，很有用但少人看）**

| 指標 | 意義 |
|---|---|
| `vllm:kv_block_lifetime_seconds` | block 從配置到淘汰的時間 |
| `vllm:kv_block_idle_before_evict_seconds` | 被淘汰前閒置了多久 |
| `vllm:kv_block_reuse_gap_seconds` | 兩次被使用之間隔了多久 |

**已從 V0 移除**：`vllm:num_requests_swapped`、`vllm:cpu_cache_usage_perc`（V1 移除 CPU swap）、`vllm:tokens_total`、`vllm:time_in_queue_requests`。舊 dashboard 遷移時會遇到。

### 6.2 三個最重要的推導式

**① TTFT 的拆解**

```
TTFT = request_queue_time + request_prefill_time

  queue_time 高  → 容量不足 → 擴容 / 降 max_model_len / 提高 max_num_seqs
  prefill_time 高 → prompt 太長或預算太小 → 升 max_num_batched_tokens
                     或檢查前綴命中率（命中了就不用算）
```

這個拆解能省下你大量猜測時間。**兩者的處方是相反的**——queue 高要提高併發，prefill 高要提高單輪預算，搞錯方向會越調越糟。

**② 前綴快取健康度**

```promql
rate(vllm:prefix_cache_hits[5m]) / rate(vllm:prefix_cache_queries[5m])
```

**③ KV 池是否太小**

```promql
histogram_quantile(0.9, rate(vllm:kv_block_reuse_gap_seconds_bucket[10m]))
  >
histogram_quantile(0.5, rate(vllm:kv_block_idle_before_evict_seconds_bucket[10m]))
```

成立代表：**block 平均在被重用之前就被淘汰了**。這是「KV 池太小」的鐵證，比看 `kv_cache_usage_perc` 更直接——後者可能顯示 0.8 看起來健康，但快取一直在洗牌。

### 6.3 症狀 → 診斷 → 處方

| 症狀 | 先看什麼 | 最可能的根因 | 處方 |
|---|---|---|---|
| P99 TTFT 飆高，P50 正常 | `num_requests_waiting` | 流量尖峰時容量不足 | HPA 依 waiting 擴容；或加 queue 上限快速失敗 |
| TTFT 整體高 | `queue_time` vs `prefill_time` | 見 6.2 ① | 依拆解結果 |
| ITL 有週期性尖刺 | `request_prefill_time` 的分布 | 長 prompt 塞爆單輪預算 | 降 `max_num_batched_tokens`（Part 3） |
| ITL 整體高且平坦 | `num_requests_running` | batch 太大 | 降 `max_num_seqs` |
| 吞吐低 + GPU 利用率低 | CPU 使用率、`api-server-count` | CPU bound（tokenize） | 加 `--api-server-count`、`VLLM_USE_FASTOKENS=1`、加 CPU |
| `kv_cache_usage_perc` > 0.95 | `num_requests_running` | KV 不足，頻繁搶佔 | Part 3 第五節四方向 + FP8 KV |
| 前綴命中率突然掉 | 有沒有改 prompt 模板 / 加 pod | 變動內容跑到前綴；或路由分散 | 重排模板；導入前綴感知路由 |
| `request_success_total{reason="length"}` 佔比高 | `request_generation_tokens` 分布 | `max_tokens` 設太小，輸出被截斷 | 調高上限；或檢查模型是否不收斂 |
| 偶發 500 / 連線重置 | pod 事件、OOMKilled | GPU OOM 或 CPU OOM | 降 `gpu_memory_utilization`；加 memory limit |
| 重啟後前幾分鐘特別慢 | 啟動日誌 | torch.compile 重編譯 | 掛 compile cache PVC（Part 4） |

### 6.4 該設的告警

```yaml
# 只列最關鍵的四條，多了會麻痺
- alert: VLLMQueueBacklog
  expr: vllm:num_requests_waiting > 10
  for: 2m
  # 容量不足，準備擴容

- alert: VLLMTTFTSLOBreach
  expr: histogram_quantile(0.95, rate(vllm:time_to_first_token_seconds_bucket[5m])) > 2
  for: 5m
  # 直接對應使用者體驗

- alert: VLLMKVCacheSaturated
  expr: vllm:kv_cache_usage_perc > 0.95
  for: 5m
  # 即將進入搶佔地獄

- alert: VLLMPrefixCacheCollapse
  expr: rate(vllm:prefix_cache_hits[10m]) / rate(vllm:prefix_cache_queries[10m]) < 0.2
  for: 15m
  # 通常代表有人改了 prompt 模板，成本會悄悄上升
```

最後一條特別值得設：**前綴命中率崩塌不會讓服務掛掉，只會讓成本默默上漲 2–3 倍**，而沒有告警的話你會在月底的帳單才發現。

---

## 七、P/D 分離與 KV Connector

### 7.1 為什麼要拆

```
混合部署（Phase 2）：
  一輪 batch = 60 個 decode + 8000 個 prefill token
  · prefill 想要大 batch（compute-bound，要餵飽 SM）
  · decode 想要小 batch 快速迭代（memory-bound，要低 ITL）
  · 兩者在同一組參數下，必然有一方是次優的

分離部署（Phase 3）：
  Prefill 池：max_num_batched_tokens = 32768，TP=8，追求 TTFT
  Decode 池：max_num_batched_tokens = 2048，max_num_seqs = 512，追求 ITL
  → 各自調到最佳，互不干擾
```

### 7.2 三層抽象

官方設計文件把 KV 傳輸拆成三層：

```
┌──────────────────────────────────────────────────────────┐
│ Connector：從 producer 取得 KV 給 consumer                │
│   NixlConnector / MooncakeConnector / LMCacheConnectorV1 │
│   / OffloadingConnector / ...                            │
├──────────────────────────────────────────────────────────┤
│ LookupBuffer：insert / drop_select                       │
│   （語意類似 SQL 的 insert 與 select-then-delete）        │
├──────────────────────────────────────────────────────────┤
│ Pipe：單向 FIFO，send_tensor / recv_tensor               │
│   （底層可以是 NCCL、RDMA、共享記憶體）                   │
└──────────────────────────────────────────────────────────┘
```

這個分層的價值在於：**同一套抽象既服務「P/D 之間傳 KV」，也服務「KV 卸載到 DRAM/SSD」**。`OffloadingConnector` 和 `NixlConnector` 實作同一個介面，只是 pipe 的另一端不同。

### 7.3 配置骨架

```bash
# Prefill 實例（producer）
vllm serve <model> --port 8100 \
  --kv-transfer-config \
    '{"kv_connector":"NixlConnector","kv_role":"kv_producer"}'

# Decode 實例（consumer）
vllm serve <model> --port 8200 \
  --kv-transfer-config \
    '{"kv_connector":"NixlConnector","kv_role":"kv_consumer"}'

# 前面需要一個 proxy：先打 prefill 拿到 KV 傳輸完成訊號，再打 decode 串流
```

**實務上不要自己寫 proxy**。用 vLLM 生態的 router 專案或 Kubernetes 上的推論 gateway，它們已經處理了：KV 傳輸失敗的 fallback、P/D 副本比例的動態調整、前綴感知路由。

### 7.4 KV 多層卸載

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ 層級         │ 容量         │ 存取延遲      │ 相對重算     │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ GPU HBM      │ 10–100 GB    │ ~µs          │ 基準（最快） │
│ CPU DRAM     │ 100 GB–2 TB  │ ~1–5 ms      │ 仍快 10–50×  │
│ 本地 NVMe    │ 1–100 TB     │ ~10–50 ms    │ 仍快 2–10×   │
│ 重算 prefill │ —            │ 100–2000 ms  │ 1×           │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**判斷是否值得**：把 20K token 的 prefill 從 SSD 讀回來要 50 ms，重算要 500 ms → **賺 10 倍**。前提是命中率夠高，否則你只是多付了寫入成本。

```
選擇              選 X 的理由                      不選 Y 的理由 / 翻轉條件
─────────────────────────────────────────────────────────────────────────
P/D 分離          尾延遲可控，兩階段獨立擴容        不提升總吞吐
vs 混合部署       長 prompt 不再干擾 decode         架構複雜度大幅上升
                  ─────────────────────────────────────────────────────
                  翻轉條件：P99/P50 TTFT < 3 且沒有為壓 ITL 而犧牲吞吐 →
                  混合部署更簡單，別過早優化。

KV 多層卸載       比加 GPU 便宜一個量級             增加外部依賴與失敗面
vs 只用 HBM       長 prompt 高重用場景收益巨大      命中率低時純粹是負擔
                  ─────────────────────────────────────────────────────
                  翻轉條件：`kv_block_reuse_gap` P90 > `idle_before_evict`
                  P50（6.2 ③）且 prompt 長 → 值得。反之不值得。

前綴感知路由      多副本下命中率可從 30% → 80%      需要額外的路由元件
vs 隨機/輪詢      成本直接下降                      路由本身成為新單點
                  ─────────────────────────────────────────────────────
                  翻轉條件：單副本，或 workload 本來就沒有共同前綴。
```

---

## 八、Benchmark：一套不會騙自己的方法

### 8.1 vLLM 內建工具

```bash
# 吞吐基準（離線，沒有網路與排隊因素）
vllm bench throughput --model <model> \
  --input-len 1024 --output-len 256 --num-prompts 1000

# 線上服務基準（有排隊、有併發，比較接近真實）
vllm bench serve --model <model> \
  --dataset-name sharegpt --dataset-path <path> \
  --request-rate 20 --num-prompts 2000

# 單次延遲
vllm bench latency --model <model> --input-len 1024 --output-len 128
```

### 8.2 五個讓 benchmark 說謊的陷阱

**陷阱一：用固定長度的合成資料。**
`--input-len 1024 --output-len 256` 讓所有請求長度一致，這會**高估**你的吞吐——真實流量的長度分布是重尾的，長請求會佔用資源更久。**用你自己的請求 log 重放**，退而求其次用 ShareGPT 這類真實分布的資料集。

**陷阱二：測峰值吞吐而不是 SLO 下的吞吐（goodput）。**
把 `--request-rate inf` 打滿，你會得到一個很漂亮的 tokens/s，以及一個 30 秒的 P99 延遲。**正確的做法是掃描 request rate，找出「P95 延遲仍在 SLO 內」的最大 rate**：

```
  吞吐 ▲
       │           ┌──────────────── 飽和區（延遲爆炸）
       │        ╱
       │     ╱ ← 你要找的點：SLO 邊界
       │  ╱
       └──────────────────────────▶ request rate
            ↑ 線性區
```

**陷阱三：沒有暖機。**
第一批請求會觸發 CUDA graph 的形狀捕捉、前綴快取是空的、compile cache 可能沒命中。**丟掉前 60 秒的資料。**

**陷阱四：前綴快取造成的虛假優勢。**
如果你的 benchmark 資料集重複度很高，前綴命中率會接近 100%，吞吐看起來好得不像話。**真實流量的命中率通常在 30–70%**。測的時候記錄 `prefix_cache_hits/queries`，如果和生產環境差太多，這個 benchmark 沒有參考價值。

**陷阱五：只測一個維度。**
至少要掃三個維度的組合：輸入長度（短/中/長）、輸出長度（短/長）、併發（低/中/高）。一張只有單點的 benchmark 表無法回答「加一張卡能買到多少」。

### 8.3 容量規劃

```
步驟 1：測出單實例的飽和點
  掃 request rate，找出 P95 TTFT < SLO 且 P95 ITL < SLO 的最大 QPS
  → 假設得到 QPS_max = 18

步驟 2：加安全邊際
  生產環境留 30% headroom（處理流量抖動、GC、鄰居噪音）
  → QPS_safe = 18 × 0.7 = 12.6

步驟 3：算副本數
  尖峰 QPS = 100 → 副本數 = ceil(100 / 12.6) = 8

步驟 4：驗證擴容能力
  HPA 從觸發到新 pod ready 要多久？
  模型載入 2 分鐘 + compile cache 命中 30 秒 ≈ 2.5 分鐘
  → 你的流量能在 2.5 分鐘內漲多少？若漲得比這快，需要預留更多 headroom
    或做 predictive scaling

步驟 5：算成本
  8 副本 × TP=2 × $4/hr = $64/hr = $46k/月
  對照：同樣流量走商用 API 要多少？
  → 這是決定「自架 vs 買 API」的唯一依據
```

第 4 步最常被忽略。**LLM 服務的擴容速度是分鐘級，不是秒級**——這改變了你的 autoscaling 策略：閾值要設得比一般 web 服務保守得多，而且 scale-down 要非常慢（避免剛縮完又要擴）。

---

## 九、生產檢查清單

上線前逐項確認：

**部署**
- [ ] image tag 鎖定具體版本，不用 `:latest`
- [ ] `--shm-size` ≥ 8g（容器環境）
- [ ] HF cache 與 `~/.cache/vllm`（compile cache）掛載持久化儲存
- [ ] CPU 請求 ≥ `2 + GPU數` 實體核心
- [ ] readiness probe `initialDelaySeconds` 覆蓋模型載入 + 編譯時間
- [ ] liveness probe 不過度敏感（`timeoutSeconds` 給足）

**配置**
- [ ] `--max-model-len` 設成實際需要的值，不是模型上限
- [ ] 啟動日誌的 `GPU KV cache size` 與 `Maximum concurrency` 已檢視且合理
- [ ] `--max-num-batched-tokens` 依 SLO 類型設定（Part 3）
- [ ] 量化方案已用自己的評測集驗證品質（Part 4）
- [ ] 多機部署已確認 `NCCL_DEBUG=INFO` 顯示 RDMA 而非 socket

**安全**
- [ ] `--api-key` 設定，且 Gateway 有 per-tenant 認證
- [ ] `/v1/load_lora_adapter` 等管理端點未對外開放
- [ ] `VLLM_SERVER_DEV_MODE` **未**開啟
- [ ] 多租戶場景已用 `cache_salt` 隔離前綴快取
- [ ] 輸入長度上限有在 Gateway 層擋（避免單一請求吃光 KV）

**可觀測性**
- [ ] Prometheus 已抓 `/metrics`，dashboard 含 TTFT/ITL/KV/前綴命中率
- [ ] 四條核心告警已設（6.4）
- [ ] 有辦法把單一請求的 trace 關聯到 vLLM 側的延遲拆解

**容量與韌性**
- [ ] 用真實流量分布做過 benchmark，知道單實例飽和點
- [ ] HPA 依 `num_requests_waiting` 而非 CPU
- [ ] 知道擴容需要多久，並據此設 headroom
- [ ] 有 queue 上限與快速失敗（避免無限排隊導致雪崩）
- [ ] 模型更新有金絲雀流程與回滾方案

---

## 十、系列導航

五篇走完了。回頭看，vLLM 的整個設計可以收斂成一條主線：

```
Part 1  問題：LLM 推論是 memory-bound，單條序列快不起來
              → 唯一解法是攤提，攤提需要大 batch，大 batch 需要記憶體
                                    │
Part 2  記憶體：分頁（浪費 60-80% → <4%）、COW 共享、前綴快取、FP8
              → 省下的記憶體變成更多併發
                                    │
Part 3  排程：連續批次消除氣泡、統一 token 預算讓 prefill 與 decode 共存
              → 更多併發真的變成更高吞吐
                                    │
Part 4  規模：量化壓小模型、TP/PP/DP/EP 切開模型、編譯消除 CPU 開銷
              → 單卡裝不下的模型也能服務
                                    │
Part 5  服務：API 面、多租戶、結構化輸出、可觀測性、P/D 分離
              → 引擎變成一個可被驗收的系統
```

每一層都在為上一層創造條件。這也是為什麼**單獨調某一個參數往往沒用**——你調的是一條鏈上的一環，而瓶頸可能在別處。本系列反覆出現的方法論其實只有一句：**先量測，找出你撞的是哪道牆，再選對應的工具。**

最後三個實務建議：

1. **從預設值開始。** V1 的哲學是零設定，前綴快取、chunked prefill、torch.compile 都預設開啟且對多數場景合理。**你唯一該主動設的通常是 `--max-model-len`、`--tensor-parallel-size`、`--gpu-memory-utilization` 三個。**
2. **量測你自己的流量。** 本系列所有數字都是量級估算。真正有意義的數字只有一組——你用自己的 trace、自己的模型、自己的硬體跑出來的那組。
3. **關注模型架構而不只是引擎。** GQA 把 KV cache 除以 5、MLA 再除一個量級、MoE 讓等效參數量和計算量脫鉤。**這些架構層的改動對推論成本的影響，大於任何引擎優化。** 選模型的時候把推論成本當成一個選型維度，比事後調參有效得多。

← [Part 4 — 分散式推論、量化與編譯優化 — 讓模型放得下也跑得快](../vllm-intro-part4-distributed-quantization-zh)

系列全部文章：

- [Part 1 — 全景架構 — 從一次 model.generate() 到一個推論引擎](../vllm-intro-part1-architecture-overview-zh)
- [Part 2 — PagedAttention 與 KV Cache — 把作業系統的分頁搬進 GPU](../vllm-intro-part2-paged-attention-kv-cache-zh)
- [Part 3 — 連續批次與排程器 — 決定誰在這一輪前進一格](../vllm-intro-part3-scheduler-continuous-batching-zh)
- [Part 4 — 分散式推論、量化與編譯優化 — 讓模型放得下也跑得快](../vllm-intro-part4-distributed-quantization-zh)
- **Part 5（本篇）— 生產部署與服務化 — 從 vllm serve 到一份可被驗收的 SLO**

---

*本文基於 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）、官方線上服務文件、LoRA 文件、結構化輸出文件、V1 指標設計文件與分離式預填充設計文件撰寫。所有端點、參數與指標名稱皆對照官方文件；成本、延遲與容量數字為量級估算，務必以自己的 benchmark 為準。vLLM 迭代極快，細節請以你安裝的版本為準。*
