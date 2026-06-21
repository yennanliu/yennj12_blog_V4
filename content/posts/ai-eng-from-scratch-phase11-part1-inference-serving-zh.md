---
title: "AI 工程從零開始｜Phase 11 Part 1：LLM 推論工程 — 從實驗到每秒千次請求"
date: 2026-06-21T19:30:00+08:00
draft: false
weight: 22
description: "深入解析 LLM 生產推論：vLLM PagedAttention、連續批次、投機解碼、量化（GPTQ/AWQ/INT4）、推論成本優化與 SLA 設計"
categories: ["engineering", "ai", "all"]
tags: ["AI", "LLM", "Inference", "vLLM", "Quantization", "Serving", "Production", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人把 LLM 推論想成「載入模型，呼叫 generate()，等結果」。*
> *實際上，每個 token 都在搶 GPU HBM 頻寬，記憶體碎片化讓吞吐量砍半，*
> *一個設計不良的 batch 策略讓 A100 的使用率停在 12%。*
> *真正的推論工程是記憶體管理、排程策略、精度取捨三件事同時做對。*

---

**面試情境**：「你的團隊剛把一個 70B 參數的對話模型從研究環境搬到生產，目前 p99 延遲 18 秒、GPU 使用率 15%、每千 token 成本 $0.04。CTO 要求三個月內把成本降到 $0.008、p99 降到 4 秒。你的架構計畫是什麼？」

---

## 一、核心問題：LLM 推論為什麼貴又慢

LLM 推論和傳統深度學習推論有本質上的差異。ResNet 做影像分類，輸入固定大小，一次 forward pass，批次容易排。LLM 是**自回歸生成**（autoregressive generation）：每個 token 依賴前面所有 token，必須一步一步產生。

**三個根本瓶頸：**

**瓶頸一：記憶體頻寬牆（Memory Bandwidth Wall）**

70B 模型 FP16 佔 140 GB。A100-80GB 只能塞下半個模型，必須 tensor parallel。每生成一個 token，模型的所有 140 GB 權重都要從 HBM 讀一次。A100 HBM 頻寬 2 TB/s，讀 140 GB 需要 70 ms——這就是單 token 延遲的硬下限，和計算無關。

**瓶頸二：KV Cache 爆炸**

Transformer 的 attention 需要存每個 token 的 Key 和 Value 向量（KV Cache），讓後續 token 不必重算。70B 模型每個 token 的 KV Cache 約 0.8 MB（依模型架構不同）。2048 token 的對話 = 1.6 GB KV Cache。同時跑 40 個對話 = 64 GB，比模型本身還大。

**瓶頸三：靜態批次的空洞（Static Batching Waste）**

傳統做法：等一批請求湊齊，一起跑，全部跑完再接下一批。問題：請求的輸出長度不一，短的跑完要等長的，GPU 算到一半在空轉。

這三個瓶頸共同造成 Naive HuggingFace `generate()` 的慘況：**GPU 使用率 10–20%、p99 延遲動輒 15–20 秒、每千 token $0.03–0.05**。

---

## 二、三個演進階段（POC → MVP → Scale）

### ╔══ Phase 1：POC / < 1K DAU ══╗

**目標**：驗證模型效果，不管效能。

```
┌─────────────────────────────────────────────┐
│  使用者 → FastAPI → HuggingFace generate()  │
│           ↓                                  │
│       單顆 A100（或 4× A10G）               │
│       model.generate(max_new_tokens=512)     │
│       靜態批次大小 = 1                       │
└─────────────────────────────────────────────┘
```

- **成本**：A100 $3.09/hr，QPS 約 0.5，每千 token ≈ $0.05
- **延遲**：p50 6 秒，p99 18 秒
- **可接受的捷徑**：無 queue、無 SLA、無監控
- **致命問題**：無法同時服務 > 3 個使用者

---

### ╔══ Phase 2：MVP / 1K–50K DAU ══╗

**目標**：上線可用，team 不需要半夜修火。

```
┌──────────────┐     ┌─────────────────────────────────┐
│  Load        │────▶│  vLLM Serving Engine             │
│  Balancer    │     │  ┌─────────────────────────────┐ │
└──────────────┘     │  │  Continuous Batching         │ │
                     │  │  PagedAttention (KV Cache)   │ │
                     │  │  max_num_seqs = 256           │ │
                     │  └─────────────────────────────┘ │
                     │  2× A100-80GB (Tensor Parallel)  │
                     └─────────────────────────────────┘
                              ↓
                     ┌─────────────────┐
                     │  Prometheus +   │
                     │  Grafana 監控   │
                     └─────────────────┘
```

- **新增組件**：vLLM、Tensor Parallel、基本監控
- **成本**：每千 token ≈ $0.012（比 Phase 1 低 4×）
- **延遲**：p50 1.8 秒，p99 5 秒
- **解決問題**：記憶體碎片、批次空洞
- **仍有問題**：沒有量化，模型佔 GPU 記憶體多；冷啟動 3 分鐘

---

### ╔══ Phase 3：Scale / 50K–500K DAU ══╗

**目標**：自動擴容、成本最佳化、SLA 有保證。

```
┌──────────────┐   ┌──────────────┐   ┌────────────────────┐
│  API Gateway │──▶│  Request     │──▶│  Router            │
│  (rate limit)│   │  Queue       │   │  (模型版本 / 優先)  │
└──────────────┘   │  (Redis      │   └──────────┬─────────┘
                   │   Stream)    │              │
                   └──────────────┘    ┌─────────┴──────────┐
                                       │                    │
                              ┌────────▼───────┐  ┌────────▼───────┐
                              │ vLLM Cluster A │  │ vLLM Cluster B │
                              │ AWQ INT4 量化  │  │ FP16 高精度    │
                              │ 4× A100        │  │ 2× A100        │
                              │ (高吞吐路由)   │  │ (低延遲路由)   │
                              └────────────────┘  └────────────────┘
                                       │
                              ┌────────▼───────────────────────┐
                              │  Autoscaler (KEDA)             │
                              │  metric: vllm:num_requests_wait│
                              └────────────────────────────────┘
```

- **新增組件**：請求佇列、模型量化、雙軌路由（吞吐 vs 延遲）、KEDA 自動擴容
- **成本**：每千 token ≈ $0.006（比 Phase 1 低 8×）
- **延遲**：p50 0.9 秒，p99 3.2 秒（INT4 路由）
- **解決問題**：量化省 50% GPU 記憶體，同機器塞兩倍並行

---

## 三、KV Cache 與記憶體瓶頸

KV Cache 是 LLM 推論記憶體問題的核心，必須深入理解。

**KV Cache 的大小公式：**

```
每個 token 的 KV Cache 大小
= 2（K+V）× num_layers × num_heads × head_dim × dtype_bytes

例：LLaMA-2-70B（FP16）
= 2 × 80 × 64 × 128 × 2 bytes
= 2 × 80 × 64 × 128 × 2
= 3,276,800 bytes ≈ 3.1 MB / token
```

2048 token 的對話 = 6.4 GB KV Cache。
同時跑 20 個對話 = 128 GB，超過單張 A100-80GB。

**Naive 分配的問題：**

```
傳統靜態分配（問題所在）：

GPU HBM 80GB
┌────────────────────────────────────────────────────┐
│ 模型權重 35GB │ Seq1(預留) │ Seq2(預留) │ 碎片     │
│               │  20GB      │  20GB      │  5GB浪費 │
└────────────────────────────────────────────────────┘

問題：
1. Seq1 實際只用了 8GB，12GB 空洞無法給別人用
2. 無法預知輸出長度，只能保守預留最大值
3. 碎片化造成 30–40% 記憶體浪費
```

這就是為什麼 Naive 實作的 GPU 使用率永遠在 15% 以下——不是算力不夠，是記憶體管理太差。

---

## 四、vLLM PagedAttention：作業系統思維解決 LLM 記憶體

PagedAttention 的靈感直接來自 OS 的**虛擬記憶體分頁**。

**核心思想：** 把 KV Cache 切成固定大小的 block（page），按需分配，不預留連續空間。

```
PagedAttention 記憶體佈局：

物理 GPU 記憶體（Block Pool）：
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ B001 │ B002 │ B003 │ B004 │ B005 │ B006 │ B007 │ B008 │
│ 16t  │ 16t  │ 16t  │ 16t  │ 16t  │ 16t  │ 16t  │ 16t  │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘

邏輯序列到物理 Block 的映射表（Block Table）：
Seq1（已生成 38 token）→ [B001, B003, B007]（前 3 page）
Seq2（已生成 20 token）→ [B002, B005]
Seq3（已生成 50 token）→ [B004, B006, B008]

特性：
- Block 大小固定（預設 16 token）
- 不同 Seq 的 Block 可以不連續
- Seq 結束後 Block 立刻回收，無碎片
```

**數字效果：**
- 記憶體浪費從 40% 降至 < 4%（只有最後一個 block 可能不滿）
- 相同 GPU 可同時跑的並行 sequence 數量提升 5–10×
- vLLM 論文報告：對比 HuggingFace Text Generation Inference，**吞吐量提升 24×**

**Prefix Caching（進階）：**

對話系統中，system prompt 每次都一樣（例：「你是一個客服助理...」）。PagedAttention 可以讓這段 prefix 的 KV Cache **跨請求共享**，不需要重算，對長 system prompt 場景可再省 30–50% 計算。

---

## 五、連續批次（Continuous Batching）：利用率的革命

**靜態批次的空洞問題：**

```
靜態批次（Static Batching）的時間線：

時間軸 ────────────────────────────────────────▶
        t0          t5         t10        t15

Seq A   [████████████████████] done at t10
Seq B   [██████████████████████████████] done at t15
Seq C   [█████████] done at t5
Seq D   等待 t0...等待...等待...等待 t15 才能開始

問題：Seq C 跑完後 GPU 有空位，但靜態批次要等整批都完成才接新請求
GPU 浪費：t5–t15 之間 Seq C 的位置空著
```

**連續批次的解法：**

```
連續批次（Continuous Batching）的時間線：

時間軸 ────────────────────────────────────────▶
        t0          t5         t10        t15

Seq A   [████████████████████]
Seq B   [██████████████████████████████]
Seq C   [█████████] ← done
Seq D              [█████████████████] ← Seq C 完成後立刻插入
Seq E                        [████████] ← Seq A 完成後插入

效果：GPU 幾乎沒有空洞，使用率從 15% 提升到 65–80%
```

**實作關鍵：iteration-level scheduling**

傳統排程以「請求」為單位。連續批次以**每個 decode step（每個 token 生成）**為單位重新排程，每生成一個 token 就檢查是否有 sequence 完成，立刻補入新請求。

vLLM 實作中，這個排程器稱為 `Scheduler`，核心邏輯：
1. 每個 step 前，呼叫 `scheduler.schedule()` 決定本步跑哪些 seq
2. 跑完後，標記完成的 seq，從 waiting queue 補入新 seq
3. 如果 KV Cache 快滿，觸發 **preemption**（暫停低優先序列，swap 到 CPU RAM）

**效能數字：**
- 對比靜態批次，相同硬體吞吐提升 **3–5×**
- A100 GPU 使用率從 15% 提升至 **60–75%**

---

## 六、投機解碼（Speculative Decoding）：小模型加速大模型

**核心洞察：** 大模型生成每個 token 慢，但**驗證**一個 token 序列（並行 forward pass）快。

```
投機解碼流程：

Draft Model（小，如 68M 參數）：
快速生成 k=5 個候選 token
[t1_draft, t2_draft, t3_draft, t4_draft, t5_draft]
    ↓
Target Model（大，如 70B 參數）：
一次 forward pass 同時驗證全部 5 個 token
                    ↓
驗證結果：[✓ t1, ✓ t2, ✓ t3, ✗ t4]
                    ↓
接受前 3 個 draft token，
用 target model 的 t4 替換錯誤的草稿
                    ↓
實際輸出：t1, t2, t3, t4_target（共 4 個 token，只用了 1 次大模型 forward）
```

**為什麼這樣快？**

- 大模型一次 forward pass 的時間，和生成 1 個 token 差不多（主要瓶頸在記憶體讀取，而非計算）
- 但驗證 k=5 個 token 的 forward pass，能接受約 3–4 個（acceptance rate ≈ 75–80% 對話場景）
- 等效速度：用 1 次大模型的時間，生成 3–4 個 token

**適用場景與限制：**

- 最有效：輸出高度可預測（程式碼補全、範本填空）
- 效果差：創意寫作、高溫度取樣（acceptance rate 下降到 40% 以下就不划算）
- 延遲改善：p50 延遲降低 **2–3×**，p99 改善相對小（長尾是 draft 命中率低的請求）

**Draft model 的來源：**

1. 同系列小模型（LLaMA-70B 配 LLaMA-7B）
2. Medusa heads：在大模型頂部加幾個輕量 head 並行預測未來 token，不需要獨立模型

---

## 七、量化技術：GPTQ/AWQ/INT4/FP8 的精度-速度取捨

量化是**把模型權重從高精度（FP16/BF16）轉成低位元數（INT8/INT4/FP8）**，以犧牲一點精度換取大幅降低記憶體佔用和提升吞吐。

**主要量化方法比較：**

| 方法 | 位元數 | 壓縮比 | 精度損失 | 量化速度 | 適用場景 |
|------|--------|--------|---------|---------|---------|
| FP16 | 16-bit | 1× | 基準 | — | 研究/高精度需求 |
| GPTQ | INT4 | 4× | < 2% ppl | 慢（需校準集） | 批次推論，CPU offload |
| AWQ | INT4 | 4× | < 1% ppl | 中等 | **生產首選** |
| INT8（LLM.int8） | 8-bit | 2× | < 0.5% | 快 | 記憶體稍緊時 |
| FP8 | 8-bit | 2× | < 0.3% | 最快（H100 原生） | H100 最佳選擇 |

**AWQ（Activation-aware Weight Quantization）的優勢：**

AWQ 的洞察：不是所有權重一樣重要。少數「顯著」的權重對輸出影響大，應該**保持高精度或用較小的量化誤差**。AWQ 分析 activation 分佈找出這些權重，其他權重才激進量化。

結果：70B 模型 AWQ INT4 量化後：
- 記憶體從 140 GB 降至 **35 GB**（單張 A100-80GB 就能跑）
- 推論吞吐提升約 **1.8–2.2×**（記憶體頻寬是瓶頸，位元數減半吞吐接近翻倍）
- 精度損失在 MMLU、HumanEval 等 benchmark 上 **< 1%**

**FP8（H100 專屬）：**

H100 Tensor Core 原生支援 FP8 運算，不需要 dequantize，速度最快。和 AWQ INT4 相比精度更好，但記憶體節省只有 2×（不如 INT4 的 4×）。100K+ DAU 且預算允許用 H100 的場景，FP8 是首選。

**量化的 flip condition：**

- 精度極敏感（醫療診斷、法律文件）：不量化，用 FP16
- 對話/程式碼補全/摘要：AWQ INT4 是甜蜜點
- H100 環境：FP8 > AWQ INT4（速度更快且精度更好）

---

## 八、為什麼選 X 不選 Y

**決策 1：vLLM vs HuggingFace TGI vs TensorRT-LLM**

```
選擇        選 vLLM 的理由                    不選的理由
────────────────────────────────────────────────────────────────
vLLM        PagedAttention 記憶體效率最高       —
            生態系豐富，社群活躍，模型支援廣
            Continuous Batching 開箱即用

HF TGI      部署簡單，Hugging Face Hub 整合好   記憶體管理效率低於 vLLM
                                               自訂排程策略困難

TRT-LLM     最高原始吞吐（NVIDIA 官方最佳化）   需要手動 compile，模型支援有限
                                               每次更新模型要重新 compile

flip：若模型固定不變、追求極致吞吐，TensorRT-LLM 每秒 token 數
     比 vLLM 高約 30–40%，值得投入編譯成本。
```

**決策 2：AWQ INT4 vs FP16**

```
選擇        選 AWQ INT4 的理由                  不選的理由
────────────────────────────────────────────────────────────────
AWQ INT4    記憶體降低 4×，吞吐提升 1.8×        精度損失約 0.5–1%
            70B 模型單張 A100 可跑              量化需要校準資料集和時間
            成本降低 ~50%

FP16        零精度損失，標準訓練格式             記憶體佔用 4× 大
                                               需要多張 GPU，成本高

flip：精度關鍵場景（基準測試、科學計算）用 FP16。對話應用 AWQ INT4。
```

**決策 3：Tensor Parallelism vs Pipeline Parallelism**

```
選擇        選 Tensor Parallel 的理由           不選 Pipeline Parallel 的理由
────────────────────────────────────────────────────────────────
TP          延遲低（所有 GPU 同時算同一 layer）  通訊量大，NVLink 速度要夠
            實作相對簡單（vLLM 內建）

PP          可用慢速網路（跨機器）              Pipeline bubble 浪費，延遲較高
            適合超大模型（> 8 GPU）              複雜度高

flip：跨機器（InfiniBand 以下速度）用 PP；同機器 NVLink 用 TP。
     70B 模型 2–4 GPU 用 TP；175B+ 跨 8 GPU 考慮 TP+PP 混合。
```

**決策 4：連續批次 vs 請求排隊**

```
選擇        選 Continuous Batching 的理由       不選靜態批次的理由
────────────────────────────────────────────────────────────────
CB          GPU 使用率 60–75%（vs 靜態 15%）    實作複雜度較高
            短請求不需要等長請求               需要 iteration-level 排程器
            吞吐量提升 3–5×

靜態批次    實作簡單                           短請求等待長請求，使用率低
                                               吞吐量浪費嚴重

flip：QPS < 5 且請求長度方差小，靜態批次夠用。任何生產環境都用 CB。
```

**決策 5：投機解碼 vs 標準 Autoregressive**

```
選擇        選投機解碼的理由                    不選的理由
────────────────────────────────────────────────────────────────
Speculative 延遲降低 2–3×（對話/程式碼場景）   需要維護 draft model
Decoding    不需要額外 GPU（draft model 小）   acceptance rate 低時（< 50%）
            p50 改善明顯                       反而比標準慢

標準 AR     實作簡單，適合所有場景              延遲較高

flip：acceptance rate < 60% 的場景（高溫度生成、多語言）不要用投機解碼。
     先在 staging 環境量測 acceptance rate 再決定。
```

**決策 6：KEDA 自動擴容 vs 固定副本**

```
選擇        選 KEDA 的理由                      不選固定副本的理由
────────────────────────────────────────────────────────────────
KEDA        根據 waiting queue 長度動態擴縮容   設定複雜，冷啟動 2–3 分鐘
(autoscale) 低峰時省 60–70% GPU 費用            需要 GPU 資源池預熱

固定副本    零冷啟動，SLA 穩定                  低峰期浪費大量 GPU 成本
                                               突發流量無法應對

flip：流量非常穩定（方差 < 20%）用固定副本。有明顯日夜流量差異必用 KEDA。
     設定 min_replicas=1 避免冷啟動 SLA 失效。
```

---

## 九、系統效應：Naive vs vLLM vs 量化

| 指標 | Naive HF generate() | vLLM FP16 | vLLM + AWQ INT4 | vLLM + AWQ + Spec Decode |
|------|--------------------|-----------|-----------------|--------------------------| 
| 硬體 | 4× A100-80GB | 2× A100-80GB | 1× A100-80GB | 1× A100-80GB + draft |
| 吞吐（tok/s） | 120 | 1,800 | 3,200 | 5,500 |
| GPU 使用率 | 12% | 65% | 72% | 78% |
| p50 延遲 | 6.2 s | 1.4 s | 0.9 s | 0.5 s |
| p99 延遲 | 18 s | 4.8 s | 3.1 s | 2.2 s |
| 每千 token | $0.045 | $0.011 | $0.006 | $0.004 |
| 並行 seq 數 | 8 | 120 | 240 | 240 |

**關鍵洞察：**

1. **最大的跳躍在 Naive → vLLM FP16**：不是量化，是 PagedAttention + Continuous Batching。光這一步吞吐提升 **15×**，成本降低 **4×**。
2. **量化的貢獻是硬體效率**：從 2 張 A100 降到 1 張就能跑，節省硬體成本，但延遲改善相對有限。
3. **投機解碼主要改善 p50**：p99 改善較小，因為長尾往往是 draft acceptance rate 低的複雜請求。
4. **回答面試題**：從 $0.04 到 $0.008 是可以達到的（vLLM + AWQ INT4），從 p99 18s 到 4s 也是可以的（vLLM FP16 就夠了）。

---

## 十、面試答題要點

**題目重述**：「70B 模型 p99 18 秒、成本 $0.04/千 token，如何 3 個月內達到 p99 4 秒、成本 $0.008？」

> *「我會分三個階段處理。第一步是部署 vLLM 替換 HuggingFace generate()，啟用 PagedAttention 和 Continuous Batching，這兩個機制可以把 GPU 使用率從 12% 提升到 65%，吞吐量提升約 15×，預估 p99 從 18 秒降至 5 秒，成本降至約 $0.012，用 2 週可以完成。第二步是對模型做 AWQ INT4 量化，精度損失小於 1%，記憶體降低 4×，70B 模型從需要 4 張 A100 降至 1 張即可跑，成本再降至 $0.006–0.008，預估 3–4 週。第三步視流量特性決定是否加投機解碼：先量測 acceptance rate，若對話場景 acceptance rate > 70% 則加入，可把 p50 再降 2×；同時設定 KEDA 根據 waiting queue 長度自動擴縮容，低峰省 60% GPU 費用。整體 3 個月的目標：p99 3–3.5 秒、每千 token $0.006，可以達成。」*

**關鍵數字要記住：**
- vLLM vs HuggingFace：吞吐 **24×**（論文數字）
- Naive GPU 使用率：**10–15%** → vLLM 後：**60–75%**
- AWQ INT4：記憶體 **4×** 節省，精度損失 **< 1%**
- 投機解碼：p50 延遲降低 **2–3×**，acceptance rate 需 **> 60%** 才划算
- KV Cache 大小：70B FP16 每 token 約 **3 MB**，2048 context = **6.4 GB**

---

## 十一、系列導航

| | |
|---|---|
| ← 上一篇 | [Phase 10 Part 3：RAG 系統評估與生產化](/posts/ai-eng-from-scratch-phase10-part3-rag-eval-zh/) |
| → 下一篇 | [Phase 11 Part 2：多模型服務與成本治理](/posts/ai-eng-from-scratch-phase11-part2-multi-model-zh/) |

---

*本文是「AI 工程從零開始」系列第 11 階段第 1 篇，涵蓋 LLM 推論生產化的核心技術棧。*
