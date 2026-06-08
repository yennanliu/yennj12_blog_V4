---
title: "TTFT & Throughput Optimization：首字延遲與推理吞吐量的硬體級優化"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析 LLM 推理服務的兩大核心指標——首字時間（TTFT）與每秒 Token 吞吐量——以及 Quantization、Continuous Batching、PagedAttention、Speculative Decoding、Flash Attention 五大硬體級優化技術的原理與取捨。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "MLOps", "Inference", "Performance"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：LLM 推理服務存在兩個永遠相互拉扯的指標——TTFT（首字延遲，決定用戶感知流暢度）與 Throughput（每秒 Token 數，決定 GPU 成本與容量）；所有推理優化技術本質上都是在這兩者之間移動作業點。**

---

## 一、為什麼面試官問這個

面試官問 TTFT / Throughput 優化，真正測試的是三件事：

- **你是否理解 LLM 推理的計算瓶頸** — Prefill 受限於 FLOPS（矩陣乘法），Decode 受限於 Memory Bandwidth（KV Cache 讀取）。能分清楚這兩個瓶頸才是起點。
- **你是否能從業務 SLA 倒推系統設計** — 互動式聊天 TTFT < 500ms 優先；批次摘要任務 Throughput 最大化優先。混淆兩者設計方向是初階錯誤。
- **你是否知道業界標準工具** — vLLM、TGI、GPTQ、AWQ、Flash Attention 不是加分項，是基本盤。沒提過這些工具，面試官會直接降級評分。

**弱答案長什麼樣：**「可以用更快的 GPU」、「換成更小的模型」——這種回答顯示你沒有系統化思考，只是在說廢話。

**強答案長什麼樣：** 先拆解 Prefill vs Decode 的不同瓶頸，再針對每個瓶頸選對應工具，最後說明在給定 SLA 下如何調整 Batch Size 在 TTFT 與 Throughput 間取得平衡，並給出具體數字。

---

## 二、核心原理與技術深度

### 2.1 Prefill vs Decode：兩個截然不同的計算瓶頸

LLM 推理分為兩個階段，具有完全不同的計算特性：

```
┌──────────────────────────────────────────────────────────────────┐
│  PREFILL 階段（Compute-Bound，計算密集）                           │
│                                                                    │
│  輸入 Prompt：N 個 Token                                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  步驟 1：Q, K, V 投影                                       │  │
│  │          N × d_model → 三個 N × d_head 矩陣                │  │
│  │  步驟 2：Attention Score 計算                               │  │
│  │          Score = QK^T / sqrt(d_k)  ← NxN 矩陣乘法         │  │
│  │          FLOPS = O(N² × d_model)                           │  │
│  │  步驟 3：Softmax + 加權 V                                   │  │
│  │          所有 N 個 Token 並行處理 → GPU 利用率高             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  瓶頸：FLOPS（輸入越長，計算量平方增長）                             │
│  輸出：第一個 Output Token ← 這就是 TTFT 的終點                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  DECODE 階段（Memory-Bound，記憶體頻寬密集）                       │
│                                                                    │
│  每一步只生成 1 個新 Token（Auto-regressive）                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  步驟 1：從 KV Cache 讀取所有歷史 K, V                      │  │
│  │          HBM → SRAM（記憶體頻寬瓶頸在此）                   │  │
│  │  步驟 2：計算新 Token 對所有歷史 Token 的 Attention          │  │
│  │          FLOPS 極低（只有 1 × N 而非 N × N）                │  │
│  │  步驟 3：寫回新 K, V 到 KV Cache                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  瓶頸：Memory Bandwidth（每步都要讀寫整個 KV Cache）               │
│  公式：Tokens/sec ≈ HBM Bandwidth / KV Cache Size per Token      │
└──────────────────────────────────────────────────────────────────┘
```

**具體數字（LLaMA-2 70B，A100 80GB SXM）：**

| 指標 | 數值 |
|------|------|
| Prefill 延遲（1024 token prompt） | ~120ms |
| Decode 速度（FP16，batch=1） | ~22 tokens/sec |
| KV Cache 大小（70B，每 1000 tokens） | ~1.3 GB |
| A100 HBM Bandwidth | 2 TB/s |
| H100 HBM Bandwidth | 3.35 TB/s |

**TTFT vs Throughput 的根本矛盾：**
- Batch Size 越大 → Throughput 越高（GPU 利用率高）→ 但 Prefill 需等所有請求到齊，TTFT 上升
- Batch Size 越小 → TTFT 越低 → 但 GPU 大量閒置，Throughput 崩潰

這就是為什麼不存在「一個最佳 Batch Size」——必須根據 SLA 動態調整。

---

### 2.2 五大優化技術的機制

#### 技術一：Quantization（量化）

將模型權重從高精度壓縮至低精度，直接減少 VRAM 佔用和記憶體傳輸量：

```
FP32 (32-bit): ████████████████████████████████  每個參數 4 bytes
FP16 (16-bit): ████████████████                  每個參數 2 bytes  → 2x 壓縮
INT8  (8-bit): ████████                           每個參數 1 byte   → 4x 壓縮
INT4  (4-bit): ████                               每個參數 0.5 byte → 8x 壓縮
```

**兩種主流量化演算法：**

**GPTQ（Post-Training Quantization）：**
- 逐層最小化量化誤差，利用二階 Hessian 矩陣補償精度損失
- 一次性離線計算（70B 模型約 2–4 小時），推理時零額外開銷
- 適合 INT4 量化，精度損失比直接截斷低 60%

**AWQ（Activation-aware Weight Quantization）：**
- 分析哪些權重通道對 Activation 影響最大（約 1% 的 salient weights）
- 對關鍵通道保留更高精度或做 scaling 補償
- 比 GPTQ 在 INT4 下精度更好，特別是數學和推理任務

**實測效能對比（LLaMA-2 70B，A100 80GB）：**

| 格式 | VRAM 用量 | Throughput | TTFT 改善 | MMLU 精度損失 |
|------|----------|-----------|----------|--------------|
| FP32 | 280 GB   | 0.6x      | 基準      | 0%           |
| FP16 | 140 GB   | 1.0x      | —        | < 0.1%       |
| INT8 | 70 GB    | 1.4x      | -30%     | < 1%         |
| INT4 | 35 GB    | 1.7x      | -45%     | 1–3%         |

INT8 是大多數任務的最佳平衡點：VRAM 減半、Throughput 提升 40%、精度損失幾乎不可感知。

---

#### 技術二：Continuous Batching（Iteration-Level Batching）

**Static Batching 的根本問題：** 等最長序列完成才釋放 GPU Slot，短序列強制等待。

```
Static Batching（傳統方式）：
時間軸 ──────────────────────────────────────────────────▶

Req A  [■■■■■■■■■■■■■■■■■■■■■■■■] 完成（200 tokens）
Req B  [■■■■■■■■] ░░░░░░░░░░░░░░░ 完成，但被迫等待 A
Req C  [■■■■■■■■■■■■] ░░░░░░░░░░░ 完成，但被迫等待 A
Req D  （佇列中等待）               └── 只能在這裡才能進入

GPU 利用率：約 35–45%（大量 idle 時間）
```

```
Continuous Batching（Iteration-Level）：
時間軸 ──────────────────────────────────────────────────▶

Req A  [■■■■■■■■■■■■■■■■■■■■■■■■] 完成
Req B  [■■■■■■■■]                  完成 → Slot 立即釋放
Req C  [■■■■■■■■■■■■]              完成 → Slot 立即釋放
Req D            [■■■■■■]          B 完成後立即插入
Req E                    [■■■■■■■■■] C 完成後立即插入
Req F                         [■■■] 持續插入

GPU 利用率：約 85–95%（幾乎無 idle 時間）
```

**吞吐量改善：3–5x vs 靜態批次（vLLM benchmark，LLaMA-2 13B，A100）。**

vLLM 和 TGI（Text Generation Inference）都預設啟用 Continuous Batching。實作上，每個 Token 生成步驟（iteration）之後，框架會掃描哪些序列已完成，釋放其 KV Cache Slot，並從佇列中插入新請求。

---

#### 技術三：PagedAttention（vLLM 核心創新）

**傳統 KV Cache 的記憶體碎片問題：**

每個請求的最大輸出長度事先未知，系統必須預留最大可能長度的連續記憶體。實際使用率通常只有 50–60%，加上碎片化，整體 GPU 記憶體利用率僅 40%。

```
傳統連續 KV Cache 分配：
┌──────────┬──────────────┬──────────┬──────────────┐
│ Req A    │              │ Req B    │              │
│ 512 tok  │   碎片/預留   │ 256 tok  │   碎片/預留   │
│ ████████ │  ░░░░░░░░░░  │ ████████ │  ░░░░░░░░░░  │
└──────────┴──────────────┴──────────┴──────────────┘
 實際使用             未使用（但已鎖定，無法給其他請求）
```

```
PagedAttention（非連續分頁，類似 OS 虛擬記憶體）：
實體 Pages（每 Page = 16 tokens 的 KV Cache）：
┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
│ A0 │ B0 │ A1 │ C0 │ B1 │ A2 │ D0 │ B2 │ A3 │ C1 │
└────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘

Page Table（邏輯 → 實體映射）：
  Req A 的 KV Cache：邏輯 [0,1,2,3] → 實體 [A0,A1,A2,A3]
  Req B 的 KV Cache：邏輯 [0,1,2]   → 實體 [B0,B1,B2]
  Req C 的 KV Cache：邏輯 [0,1]     → 實體 [C0,C1]

按需分配，無碎片，任何空閒 Page 都可給任何請求使用
```

**效果量化：**
- GPU 記憶體利用率：40% → 80%（翻倍）
- 有效 Batch Size 提升：~40%
- 每 Token 成本降低：~35%
- 額外的副作用：支援 Prefix Caching（相同 Prompt 前綴的 KV Cache 跨請求共享）

---

#### 技術四：Speculative Decoding（推測解碼）

**核心想法：** 用一個小模型（Draft Model，68M–7B）快速生成 N 個候選 Token，再用大模型（Target Model，70B）一次 Forward Pass 並行驗證所有候選。

```
標準 Decode（每步只生成 1 個 Token）：
Step 1: Target(70B) → token₁           [1 Token/step]
Step 2: Target(70B) → token₂           [1 Token/step]
Step 3: Target(70B) → token₃           [1 Token/step]
總耗時：3 × T_target

Speculative Decoding（N=5 個候選）：
Draft(7B) 快速生成：[t₁][t₂][t₃][t₄][t₅]  → 耗時 5 × T_draft（≪ T_target）
Target(70B) 並行驗證：
  [✓ t₁][✓ t₂][✓ t₃][✗ t₄]（拒絕）
接受前 3 個 Token，拒絕位置重新採樣
本輪生成 3 個 Token，耗時 ≈ 1 × T_target + 5 × T_draft

期望加速比（α = 接受率）：
  E[tokens per step] = (1 - α^(N+1)) / (1 - α)
  α=0.85, N=5 → E = ~4.0 tokens per Target step
  α=0.65, N=5 → E = ~2.2 tokens per Target step（不划算）
```

**適用條件判斷：**

| 任務類型 | 典型接受率 | 建議啟用？ | 原因 |
|---------|----------|----------|------|
| 程式碼生成 | 85–92% | 強烈建議 | 語法高度可預測 |
| 機器翻譯 | 80–88% | 建議 | 詞序固定 |
| 文件摘要 | 72–80% | 視情況 | 邊緣案例 |
| 開放式對話 | 55–70% | 不建議 | 多樣性高，Draft 猜錯多 |
| 創意寫作 | 45–65% | 不建議 | 低接受率反而更慢 |

**閾值：接受率 < 75% 時，Speculative Decoding 帶來的額外 Draft 計算開銷超過收益，實際比不用更慢。**

---

#### 技術五：Flash Attention（融合 GPU Kernel）

**標準 Attention 的記憶體瓶頸：**

NxN Attention Score Matrix 必須完整寫入 HBM（GPU 高頻寬記憶體），再讀回做 Softmax，再寫回，再讀回做加權求和。對於長序列，這個矩陣極其龐大。

```
標準 Attention 的記憶體存取模式：
HBM（高頻寬記憶體，慢但大）
  ↓ 讀取 Q, K
SRAM（片上快取，快但小）
  → 計算 Score = QK^T（NxN）
  ↓ 寫回 Score 到 HBM     ← O(N²) 記憶體使用
  ↓ 讀回 Score 從 HBM
SRAM
  → Softmax(Score)
  ↓ 寫回到 HBM
  ↓ 讀回 Softmax(Score)
SRAM
  → × V → Output
  ↓ 寫回 Output 到 HBM

問題：N=32K 時，Score Matrix = 32K × 32K × 2 bytes ≈ 2 GB！
```

```
Flash Attention（Tiling + Kernel Fusion）：
HBM
  ↓ 讀取 Q 的第一個 Tile（如 128 tokens）
  ↓ 讀取 K, V 的對應 Tile
SRAM（片上完成所有計算）
  → Tile Score = Q_tile × K_tile^T
  → 增量式 Softmax（online softmax algorithm）
  → 增量式 × V
  ↓ 只寫回最終 Output（每個 Tile 的貢獻）到 HBM

記憶體：O(N)   ← 從未有過完整的 NxN 矩陣
速度：  2–4x faster（減少 HBM 讀寫次數）
VRAM：  N=128K context 需要 ~2 GB vs 標準的 ~32 TB（不可能）
```

**Flash Attention 2 vs Flash Attention 1：**
- FA2 改善了 GPU Thread Block 的工作分配，在 Causal Attention（decoder-only）下速度再提升 2x
- FA2 支援 GQA（Grouped Query Attention），對 LLaMA-2/3 等使用 GQA 的模型有額外加速

**實際要求：** 超過 32K context 的推理任務，Flash Attention 是強制要求，否則 VRAM 耗盡。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**目標：** 最快上線，流量 < 100 QPS，POC 或內部工具場景。

**實作清單：**
- 部署 vLLM（`pip install vllm`，單張 A100 或 H100）
- 啟用 Continuous Batching（vLLM 預設開啟）
- 使用 FP16 精度（不量化，避免除錯複雜度）
- Flash Attention 通過 `--enable-chunked-prefill` 旗標啟用

**不做：** Speculative Decoding（需額外 Draft Model 維運）、INT4 量化（精度風險未評估）、PagedAttention 細粒度調優。

**效能基準（LLaMA-2 70B，FP16，2x A100 80GB）：**
- TTFT（512 token prompt）：~200ms
- Throughput（batch=8）：~180 tokens/sec
- GPU 記憶體利用率：~45%
- 月成本（Cloud 按需，2x A100）：~$5,000–$7,000

**遺留問題：** 記憶體利用率低，無法應對 burst 流量，VRAM 浪費導致有效 Batch Size 受限。

---

### Layer 2 — 生產就緒（Production-Ready）

**目標：** 穩定服務 1K–50K DAU，SLA：TTFT P95 < 500ms，P99 Throughput > 20 tokens/sec/user。

**在 Layer 1 基礎上新增：**

**1. AWQ INT8 Quantization：**
- 使用 `autoawq` 套件對模型做一次性量化（70B 模型約 4–8 小時）
- VRAM 從 140 GB 降至 70 GB → 同一台 2x A100 可服務更大 Batch
- Throughput 提升 40%，TTFT 改善 30%

**2. 確認 PagedAttention 版本（vLLM >= 0.2.x）：**
- GPU 記憶體利用率從 ~45% 提升至 ~80%
- 啟用 Prefix Caching（相同 System Prompt 的 KV Cache 跨請求共享，減少重複 Prefill）

**3. 動態 Batch Size 策略（根據佇列深度）：**

| 佇列深度 | Batch Size | 策略 | TTFT / Throughput |
|---------|-----------|------|------------------|
| < 10 req | 4–8 | TTFT 優先 | P95 TTFT < 200ms |
| 10–50 req | 16–32 | 平衡 | P95 TTFT < 400ms |
| > 50 req | 64–128 | Throughput 優先 | P95 TTFT < 1000ms |

**4. 監控指標（Prometheus + Grafana）：**
- `vllm:time_to_first_token_seconds`（P50/P95/P99）
- `vllm:e2e_request_latency_seconds`（端到端）
- `vllm:gpu_cache_usage_perc`（KV Cache 使用率，> 90% 觸發告警）
- `vllm:num_running_seqs`（當前並發序列數）

**效能提升（vs Layer 1）：**
- Throughput：180 → 520 tokens/sec（2.9x）
- GPU 記憶體利用率：45% → 82%
- 有效並發請求數：8 → 22（同樣 VRAM）

**遺留問題：** Speculative Decoding 未啟用；超長 context（> 32K）高並發場景 VRAM 仍有壓力。

---

### Layer 3 — 企業級（Enterprise-Grade）

**目標：** 200K+ DAU，多地區部署，成本最優，支援 128K+ context 長文件處理。

**在 Layer 2 基礎上新增：**

**1. Speculative Decoding（按任務類型選擇性啟用）：**
- Coding / 翻譯服務：接受率驗證 > 80% 後啟用，Throughput 再提升 1.5–2x
- 對話服務：維持關閉（接受率 < 70%，啟用反而變慢）
- Draft Model 選型：同系列小模型（LLaMA-3 8B 作為 LLaMA-3 70B 的 Draft）

**2. Disaggregated Prefill / Decode（分離部署）：**

```
Prefill Pool（FLOPS 優先，H100 SXM）：
  ┌──────────┐  ┌──────────┐
  │  H100 #1 │  │  H100 #2 │  ← 處理 Prefill 計算（FLOPS 密集）
  └────┬─────┘  └────┬─────┘
       │              │
       └──────┬───────┘
              ▼
         KV Cache 傳輸（NVLink / Infiniband）
              │
Decode Pool（Bandwidth 優先，A100）：
       ┌──────┴───────┐
  ┌────▼─────┐  ┌─────▼────┐
  │  A100 #1 │  │  A100 #2 │  ← 處理 Decode（Memory Bandwidth 密集）
  └──────────┘  └──────────┘
```

- Prefill 用 H100（高 FLOPS），Decode 用 A100（高 HBM Bandwidth / 成本低）
- 兩個 Pool 獨立擴縮容，成本最優化

**3. 多模型路由（Cascade 策略）：**
- 分類器判斷請求複雜度 → 路由至 7B / 13B / 70B
- 70% 請求由 7B 模型處理（速度 10x，成本 $0.05/M tokens vs $0.8/M tokens）
- 整體成本降低 60–80%

**4. Flash Attention 2 + Chunked Prefill（128K Context）：**
- 超長文件分析場景：法律合約審查、程式碼庫分析
- Chunked Prefill 將長 Prompt 拆成多個 Chunk，避免 Prefill 獨佔 GPU 阻塞 Decode

**運維複雜度：** 需要 ML Platform 團隊（2–4 人）；建議基於 SGLang 或 LMDeploy 框架，原生支援 Disaggregated 部署。

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| Batch Size 設太大（如 256）以最大化 Throughput | TTFT 從 200ms 暴增至 5–10s，互動式應用完全不可用，用戶流失 | 根據 SLA 設 Batch 上限；互動式 chat batch ≤ 16 |
| 盲目對所有模型使用 INT4 量化 | 數學推理、程式碼生成精度損失 5–15%，用戶投訴率上升 | 先在 MMLU、HumanEval 驗證；精度損失 < 2% 才上線 |
| 分不清 TTFT 和 E2E Latency | 以為系統正常，實際 Decode 速度崩潰（OOM 後 Swap 到 CPU DRAM） | 分別設獨立告警：TTFT P95 < 500ms；Decode Speed > 10 tok/sec |
| Speculative Decoding 用於開放式對話 | Draft 接受率 < 60%，Target Model 重算比例高，比不用 Speculative 更慢 | 先測接受率；< 75% 不啟用；對話任務幾乎永遠不應啟用 |
| 未設定 KV Cache 的 Session 記憶體上限 | 長 session 保留完整 KV Cache → 數小時內記憶體耗盡，服務崩潰 | 設定 max_model_len；對非活躍 session 實施 KV 驅逐（LRU） |
| FP32 推理（完全沒有量化意識） | VRAM 是 FP16 的 2x，同一 GPU 只能跑 batch=1，Throughput 只有最優解的 10% | 最低標準：FP16；生產環境至少評估 INT8 AWQ |
| 把 Prefill 和 Decode 的瓶頸混為一談 | 以為換更快 GPU 就能同時改善兩個指標，結果優化方向錯誤浪費預算 | Prefill 優先買 FLOPS（H100 vs A100 3x FLOPS）；Decode 優先買 HBM Bandwidth |

---

## 五、與其他核心主題的關聯

- **KV Cache 管理 & 記憶體架構（Core Topic 15）：** PagedAttention 的正確性依賴精確的 KV Cache 生命週期管理；Part 15 深入 KV Cache 資料結構，本篇從優化角度延伸應用層面。
- **LLM 服務化架構（FDE Guide Part 31–32）：** Continuous Batching 與 vLLM 是 Vertex AI Model Garden 的底層推理引擎；企業級推理服務的佇列設計建立於本篇 Batch Size 調控策略之上。
- **GPU 成本優化與選型（Core Topic 17）：** INT8/INT4 量化效果直接決定 GPU SKU 選型的 ROI（A100 vs H100 vs L4 的 $/token 比較），本篇提供量化效能基準數字。
- **可觀測性與 SLA 設計（FDE Guide Part 35–38）：** TTFT 與 Throughput 的 Prometheus 指標是 LLM 服務 SLO 定義的基礎；告警閾值設定依賴本篇建立的數字基準（P95 TTFT < 500ms、Decode Speed > 10 tok/sec）。

---

## 六、面試一句話（Killer Phrase）

> *「LLM 推理有兩個截然不同的瓶頸：Prefill 受限於 FLOPS（NxN Attention 計算量隨輸入平方增長），決定 TTFT；Decode 受限於 Memory Bandwidth（每步都要讀完整個 KV Cache），決定吞吐量。我的標準優化棧是：用 AWQ INT8 Quantization 把 VRAM 減半同時 Throughput 提升 40%，用 vLLM 的 PagedAttention 把 GPU 利用率從 40% 推到 80%，再用 Continuous Batching 讓吞吐量再乘以 3–5 倍。TTFT 和 Throughput 之間本質上是 Batch Size 的取捨——互動式聊天我會把 Batch 上限壓在 16 以確保 TTFT P95 < 500ms，批次任務則開放到 128 最大化 GPU 吞吐；Speculative Decoding 只在接受率驗證超過 80% 後啟用，通常限於 coding 和翻譯場景。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-15-kv-cache-memory-management-zh/) | [後一篇](/posts/fde-interview-core-topic-17-gpu-cost-optimization-zh/) →
