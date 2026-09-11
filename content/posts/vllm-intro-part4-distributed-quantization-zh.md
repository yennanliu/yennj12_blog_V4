---
title: "vLLM Intro Part 4 — 分散式推論、量化與編譯優化 — 讓模型放得下也跑得快"
date: 2026-09-11T12:00:00+08:00
draft: false
weight: 4
description: "vLLM 原始碼導讀系列第四篇：拆解 TP／PP／DP／EP 四種平行度的切法與通訊量、多機部署與 NCCL 排錯、量化方法與硬體支援矩陣、torch.compile 的 piecewise CUDA Graph 為什麼切在 attention 上，以及 attention backend 的選擇邏輯。"
categories: ["all", "ai", "engineering", "infrastructure"]
tags: ["vLLM", "Distributed Inference", "Tensor Parallelism", "Quantization", "FP8", "CUDA Graph", "torch.compile", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
---

> *大多數人遇到「模型放不下」的反應，是把 `--tensor-parallel-size` 開到卡數，跑起來就當解決了。*
> *真正的答案是：TP 的每一層都要做一次 all-reduce，沒有 NVLink 的機器上這件事會吃掉你 40% 的時間；而在很多情況下，正確的答案不是切模型，是把模型變小。*
> *放得下和跑得快，是兩個問題，常常要用相反的手段。*

---

## 前言

[Part 3](../vllm-intro-part3-scheduler-continuous-batching-zh) 之前的所有討論都在一張 GPU 的邊界內。這一篇跨出去，並且處理三個互相糾纏的問題：

1. **模型放不下一張卡** → 切開它（平行化）
2. **模型放得下但太擠，KV 池不夠** → 壓縮它（量化）
3. **模型放得下也不擠，但 GPU 沒跑滿** → 消除開銷（編譯與圖捕捉）

這三題的順序很重要，而多數人的直覺順序是錯的。**先量化再考慮平行化**——一個 70B 模型 FP16 要 140 GB（2 張 H100），FP8 只要 70 GB（1 張 H100 勉強、2 張很舒服）。省下來的不只是卡，還有 Part 3 講的那些 all-reduce 通訊。

本篇的目標：**讀完之後，你能對著一個模型和一組硬體，說出該用哪種平行度、哪種量化、以及為什麼。**

---

## 一、核心問題：三道不同的牆

```
                    你的模型 + 你的硬體
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌─────────────┐     ┌──────────────┐
  │ 牆 ①      │      │ 牆 ②        │     │ 牆 ③         │
  │ 容量牆    │      │ 頻寬牆      │     │ 開銷牆       │
  │           │      │             │     │              │
  │ 權重 >    │      │ 權重放得下  │     │ GPU 利用率低 │
  │ 單卡記憶體│      │ 但 KV 池太小│     │ 但不是 memory│
  │           │      │ 併發 < 10   │     │ bound        │
  ├───────────┤      ├─────────────┤     ├──────────────┤
  │ 解法：    │      │ 解法：      │     │ 解法：       │
  │ TP / PP   │      │ 量化        │     │ torch.compile│
  │ （切模型）│      │ （壓縮模型）│     │ CUDA Graph   │
  │           │      │ FP8 KV      │     │ 更好的 kernel│
  └───────────┘      └─────────────┘     └──────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                  三者可以疊加，但順序是：
                  ② → ① → ③
            （先壓縮，不夠才切，最後才調編譯）
```

為什麼是這個順序？因為**量化是唯一一個「純賺」的手段**：它同時減少權重佔用、減少記憶體頻寬需求（decode 是 memory-bound！）、增加 KV 池空間。而平行化總是引入通訊成本，是「用通訊換容量」的交換。

---

## 二、三個演進階段

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：單卡 —— TP=1                             ║
### ╚═══════════════════════════════════════════════════╝

```
┌────────────────────────────────────────────┐
│  1 × H100 80GB                              │
│  ┌──────────────────────────────────────┐  │
│  │ 8B FP16 權重 16GB + KV 池 ~55GB       │  │
│  │ 無跨卡通訊                            │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

- **可接受的捷徑**：什麼都不用設。
- **成本**：$2–4/hr。
- **解決了什麼**：**零通訊開銷**——這是單卡唯一但巨大的優勢。同樣的 8B 模型跑 TP=1 vs TP=2，單請求延遲通常 TP=1 更好（因為省下 all-reduce）。
- **還沒解決什麼**：模型一大就撞牆；單卡吞吐上限固定。
- **關鍵認知**：**能用單卡就用單卡。** 只在放不下、或 KV 池不夠時才切。很多人一開始就上 TP=8，然後困惑為什麼延遲沒有變成 1/8。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：單機多卡 —— TP=N，NVLink 域內             ║
### ╚═══════════════════════════════════════════════════╝

```
┌──────────────────────────────────────────────────────────────┐
│  1 台機器，8 × H100，NVLink / NVSwitch（900 GB/s）            │
│                                                               │
│   GPU0     GPU1     GPU2     GPU3   ... GPU7                 │
│  ┌────┐   ┌────┐   ┌────┐   ┌────┐     ┌────┐                │
│  │頭  │   │頭  │   │頭  │   │頭  │     │頭  │  每層的 attention│
│  │0-3 │   │4-7 │   │8-11│   │12- │     │28- │  heads 切開      │
│  └─┬──┘   └─┬──┘   └─┬──┘   └─┬──┘     └─┬──┘                │
│    └────────┴────────┴────────┴──────────┘                    │
│              每層 2 次 all-reduce（attn 後、MLP 後）           │
│              NVLink 上約 20–50 µs/次                          │
└──────────────────────────────────────────────────────────────┘
```

- **新增元件**：NCCL 通訊群組、Worker 進程組（`mp` backend）、權重分片載入。
- **成本 delta**：8 倍卡數，但吞吐提升通常是 **5–6.5 倍**（次線性）——差額就是通訊與同步開銷。
- **複雜度 delta**：低。單機 TP 幾乎是免費的：一個 flag，vLLM 處理其餘。
- **解決了什麼**：70B、120B 級模型可服務；每卡 KV 空間變大。
- **還沒解決什麼**：單機卡數上限（通常 8）；跨機通訊是完全不同的世界。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：多機 —— TP×PP×DP×EP 混合                  ║
### ╚═══════════════════════════════════════════════════╝

```
┌──── Node 0 ────────────┐  ┌──── Node 1 ────────────┐
│ GPU0-7                  │  │ GPU0-7                  │
│ 第 0–39 層              │  │ 第 40–79 層             │
│ TP=8（NVLink 內）       │  │ TP=8（NVLink 內）       │
└───────────┬─────────────┘  └───────────▲─────────────┘
            │  PP：只傳「層邊界的 hidden  │
            │  state」，資料量小          │
            └───────────────────────────┘
                InfiniBand / RoCE，需 GPUDirect RDMA

MoE 模型再疊一層：
┌─────────────────────────────────────────────────────┐
│  Attention 層：TP 或 DP                              │
│  Expert 層：EP —— 每張卡放不同的 expert              │
│             （--enable-expert-parallel）             │
│  → 用 all-to-all 把 token 路由到對應 expert 所在的卡  │
└─────────────────────────────────────────────────────┘
```

- **新增元件**：Ray 叢集（或 mp 的 `--nnodes/--node-rank/--master-addr`）、RDMA 網路配置、共用權重儲存、跨節點健康檢查。
- **成本 delta**：卡數乘 N，且需要 InfiniBand/RoCE 網路（不便宜）。
- **複雜度 delta**：**這是質變**。跨機通訊沒配好，效能可能比單機還差——因為 NCCL 會靜默 fallback 到 TCP socket。
- **解決了什麼**：400B+ 模型、超大 MoE、以及極高吞吐需求。
- **還沒解決什麼**：故障域變大（任一節點掛掉整個實例重啟）、啟動時間變長、除錯難度指數上升。

---

## 三、四種平行度：切在哪一維

這是本篇的核心。四種平行度切的是**完全不同的維度**，理解這點就不會亂用。

```
一個 Transformer 層：

   輸入 [batch, seq, hidden]
        │
        ▼
  ┌──────────────────┐
  │ Attention        │  ← TP 切這裡的 head 維度
  │  Q,K,V 投影      │     EP 不動這裡
  │  多個 head       │
  └────────┬─────────┘
           │  ← all-reduce ①（TP 時）
           ▼
  ┌──────────────────┐
  │ MLP / MoE        │  ← TP 切這裡的 hidden 中間維度
  │  up → act → down │     EP 切這裡的 expert 維度（MoE 才有）
  └────────┬─────────┘
           │  ← all-reduce ②（TP 時）
           ▼
   輸出 [batch, seq, hidden]

  ══════════ PP 切在「層與層之間」 ══════════
  ══════════ DP 切在「batch 維度」 ══════════
```

### 3.1 對照表

| | TP（Tensor Parallel） | PP（Pipeline Parallel） | DP（Data Parallel） | EP（Expert Parallel） |
|---|---|---|---|---|
| **切什麼** | 層內的權重矩陣（head / hidden 維） | 層與層之間 | batch（請求） | MoE 的 expert |
| **每卡放** | 每層的 1/N | 全部層的 1/N | 完整模型 | attention 完整 + 部分 expert |
| **通訊時機** | **每層 2 次 all-reduce** | 每個 stage 邊界 1 次 P2P | 幾乎無（各自獨立） | 每個 MoE 層 2 次 all-to-all |
| **通訊量** | 大（`batch×seq×hidden×2` 每層） | 小（只有邊界 hidden state） | 極小 | 中（依 top-k 路由） |
| **延遲影響** | 降低單請求延遲 | **不降低**（反而多了 stage 延遲） | 不變 | 依網路而定 |
| **吞吐影響** | 次線性提升 | 線性提升（需夠多請求填滿管線） | 線性提升 | 讓超大 MoE 可行 |
| **對網路要求** | **極高**，需 NVLink | 中，跨機可接受 | 低 | 高 |
| **flag** | `--tensor-parallel-size` | `--pipeline-parallel-size` | `--data-parallel-size` | `--enable-expert-parallel` |

### 3.2 TP：為什麼一定要 NVLink

TP 的通訊量可以直接算。以 70B 模型（hidden=8192、80 層）、batch 中共 8192 個 token、BF16：

```
每次 all-reduce 的資料量 = 8192 tokens × 8192 hidden × 2 bytes = 128 MB
每層 2 次 → 每層 256 MB
80 層 → 一次 forward 共 20 GB 的 all-reduce 流量

NVLink 4.0（900 GB/s 雙向）：20 GB / 900 GB/s ≈ 22 ms
PCIe 4.0 x16（32 GB/s）：   20 GB / 32 GB/s  ≈ 625 ms   ← 災難
100 Gb Ethernet（12.5 GB/s）：20 GB / 12.5 ≈ 1600 ms    ← 更災難
```

**這就是為什麼 TP 不該跨機**（除非有 400G+ InfiniBand，且即使如此也不理想）。官方文件的建議一致：**TP 用在節點內、PP 用在節點間**。

官方也明確提到一個例外情況：**沒有 NVLink 的卡（如 L40S）**，即使在單機內，PP 也可能優於 TP——因為 L40S 之間走 PCIe，TP 的 all-reduce 成本過高。

### 3.3 PP：為什麼它不降延遲

```
PP=4，一個請求走完 4 個 stage：

單一請求：
  t →  ┌──────┐
       │stage0│
       └──┬───┘
          ▼   ┌──────┐
              │stage1│      ← stage0 此時閒置（氣泡）
              └──┬───┘
                 ▼   ┌──────┐
                     │stage2│
                     └──┬───┘
                        ▼   ┌──────┐
                            │stage3│
                            └──────┘
  總延遲 = 4 個 stage 的時間總和 = 和單卡跑完整模型一樣（甚至更慢）

多個請求（管線填滿）：
  stage0: │r1│r2│r3│r4│r5│r6│
  stage1:    │r1│r2│r3│r4│r5│
  stage2:       │r1│r2│r3│r4│
  stage3:          │r1│r2│r3│
                ↑ 穩態時所有 stage 都在工作 → 吞吐 ≈ 4×
```

**結論**：PP 提升吞吐不提升延遲，且需要足夠的併發請求填滿管線。如果你的流量稀疏，PP 的氣泡會讓 GPU 大量閒置。

**官方提到的一個實用規則**：當 GPU 數量無法整除 attention head 數時，TP 切不開（例如 6 張卡切 32 個 head），這時用 PP（`tp_size=1, pp_size=6`）。

### 3.4 DP 與 EP：MoE 的專屬組合

MoE 模型（如 DeepSeek、Mixtral 系列）有個特點：**attention 層是稠密的、expert 層是稀疏的**，兩者適合不同的平行策略。

```
                    ┌─────────────────────────────────┐
                    │  Attention 層（稠密）            │
                    │  → DP：每張卡處理不同的請求      │
                    │     各自有完整的 attention 權重   │
                    └───────────────┬─────────────────┘
                                    │ all-to-all（把 token 送去對應 expert）
                    ┌───────────────▼─────────────────┐
                    │  MoE 層（稀疏，例如 256 experts）│
                    │  → EP：GPU0 放 expert 0-31       │
                    │         GPU1 放 expert 32-63 ... │
                    │     每個 token 只啟動 top-8      │
                    └───────────────┬─────────────────┘
                                    │ all-to-all（把結果送回原卡）
                                    ▼
```

**為什麼 attention 用 DP 而不是 TP？** 因為 MoE 模型的 attention 層通常用 MLA 或 GQA，KV head 數很少（例如 1 或 8）。TP=8 時每張卡只分到 1 個 KV head，甚至要複製——**KV cache 反而被重複儲存 8 份**。用 DP 讓每張卡獨立處理不同請求，KV cache 不重複。

```bash
# 典型的大型 MoE 配置
vllm serve <moe-model> \
  --data-parallel-size 8 \
  --enable-expert-parallel \
  --tensor-parallel-size 1
```

### 3.5 決策樹

```
                    模型權重（量化後）能放進單卡嗎？
                              │
              ┌───────────────┴───────────────┐
             是                              否
              │                               │
      KV 池夠嗎（併發 > 20）？          是 MoE 模型嗎？
              │                               │
      ┌───────┴───────┐              ┌────────┴────────┐
     是              否             是                否
      │               │              │                 │
   ┌──▼──┐      ┌─────▼─────┐  ┌─────▼──────┐   ┌──────▼──────┐
   │TP=1 │      │ 先試量化  │  │ DP + EP    │   │ 單機放得下？│
   │最快 │      │ 仍不夠→TP │  │ attention  │   └──────┬──────┘
   └─────┘      └───────────┘  │ 用 DP/小TP │     ┌────┴────┐
                               └────────────┘    是        否
                                                  │         │
                                            ┌─────▼───┐ ┌───▼────────┐
                                            │ TP=卡數 │ │ TP=節點內  │
                                            │（有NVLink│ │ PP=節點數  │
                                            │ 才划算）│ │            │
                                            └─────────┘ └────────────┘
```

---

## 四、多機部署與排錯

### 4.1 兩種後端

```bash
# Ray（傳統做法，適合已有 Ray 叢集）
# 先在各節點跑 run_cluster.sh 組叢集，再從 head node：
vllm serve <model> \
  --tensor-parallel-size 8 \
  --pipeline-parallel-size 2 \
  --distributed-executor-backend ray

# 原生 multiprocessing（較新，不需要 Ray）
# head node:
vllm serve <model> --tensor-parallel-size 8 --pipeline-parallel-size 2 \
  --nnodes 2 --node-rank 0 --master-addr 10.0.0.1
# worker node:
vllm serve <model> --tensor-parallel-size 8 --pipeline-parallel-size 2 \
  --nnodes 2 --node-rank 1 --master-addr 10.0.0.1
```

```
選擇              選 Ray 的理由                    選 mp 的理由
─────────────────────────────────────────────────────────────────
ray               已有 Ray 叢集可複用               多一層依賴與故障面
vs mp             彈性排程、與 Ray Serve 整合       啟動較慢
                  多模型共用叢集容易                除錯要懂 Ray
                  ───────────────────────────────────────────────
mp                無額外依賴，啟動快                需要自己管節點編排
                  故障訊息直接                      沒有 Ray 的彈性排程
                  單機預設就是它                    多模型共用要靠 K8s
                  ───────────────────────────────────────────────
翻轉條件：單機一律用 mp（預設）。多機若你已在跑 Ray（訓練、資料處理）就用 Ray；
若是純 K8s 環境且只跑推論，mp 的依賴面小得多。
```

### 4.2 五個最常見的多機故障

| 症狀 | 原因 | 診斷 | 解法 |
|---|---|---|---|
| 跨機吞吐遠低於預期（差 5–10×） | NCCL 靜默 fallback 到 TCP socket | `NCCL_DEBUG=INFO`，看日誌有沒有 `NET/IB/GDRDMA`；若是 `NET/Socket` 就中了 | 啟用 GPUDirect RDMA、確認 IB 驅動與 `NCCL_IB_HCA` 設定 |
| 啟動時卡在 "Waiting for..." | 節點間無法互通，或 master_addr 錯 | `nc -zv <master> <port>`；檢查安全群組 | 開通埠、用內網 IP 而非主機名 |
| `Bus error` / `shared memory` 錯誤 | 容器 `/dev/shm` 太小（Docker 預設 64 MB） | `df -h /dev/shm` | `--shm-size=16g` 或掛 tmpfs |
| 某節點模型載入失敗 | 權重沒同步到所有節點 | 檢查各節點 HF cache | 預先下載到所有節點，或用共用 PVC |
| 效能不穩定、偶發 hang | NCCL 逾時預設太短，或網路抖動 | `NCCL_DEBUG=WARN` 看有無 timeout | 調 `NCCL_TIMEOUT`；檢查網路品質 |

**第一項是最隱蔽也最常見的**。vLLM 跑得起來、結果正確、只是慢——而慢的原因是 20 GB 的 all-reduce 走了 TCP。**每次新建多機叢集，第一件事就是開 `NCCL_DEBUG=INFO` 確認那一行。**

---

## 五、量化：把模型變小

量化是唯一能同時解決容量牆與頻寬牆的手段。

### 5.1 兩個維度：權重 vs 啟動

```
          W16A16（FP16 基準）
               │
     ┌─────────┴─────────┐
     ▼                   ▼
  W8A16 / W4A16       W8A8 / W4A8
  「只量化權重」       「權重+啟動都量化」
     │                   │
  · AWQ (W4A16)      · FP8 (W8A8)
  · GPTQ (W4A16)     · INT8 (W8A8)
  · GGUF             · NVFP4 / MXFP4 (W4A4，Blackwell)
     │                   │
  減少記憶體佔用      減少記憶體佔用 + 用低精度 Tensor Core
  與記憶體頻寬        → 算力也變快
     │                   │
  計算時仍要反量化    需要硬體原生支援對應精度
  回 FP16 → 算力不變
```

**關鍵區別**：
- **W4A16（AWQ/GPTQ）**：權重壓到 4 bit，記憶體省 75%。但計算時要反量化回 FP16，**算力沒有變快**。在 memory-bound 的 decode 階段效果極好（少搬 4 倍資料），在 compute-bound 的 prefill 階段反而**因為反量化開銷變慢**。
- **W8A8（FP8/INT8）**：權重和啟動都是 8 bit，可以直接用 FP8 Tensor Core 算。記憶體省 50%，**算力也提升**（H100 的 FP8 算力是 BF16 的 2 倍）。

所以：

```
你的瓶頸是什麼？
  ├─ 低併發、延遲敏感（memory-bound 主導）→ W4A16（AWQ/GPTQ）壓縮率最高
  ├─ 高併發、吞吐主導（prefill 佔比高）→ FP8 W8A8，算力也賺
  └─ 只是放不下 → 先 FP8，不夠再 W4
```

### 5.2 硬體支援矩陣

依官方文件整理（✅ 支援 / ❌ 不支援）：

| 方法 | Volta | Turing | Ampere | Ada | Hopper | AMD | Intel GPU | x86 CPU |
|---|---|---|---|---|---|---|---|---|
| AWQ (W4A16) | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| GPTQ (W4A16) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Marlin kernel | ❌ | ✅* | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| INT8 W8A8 | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| **FP8 W8A8** | ❌ | ❌ | ❌ | **✅** | **✅** | ✅ | ❌ | ❌ |
| BitsAndBytes | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| GGUF | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

*Turing 不支援 Marlin MXFP4。

**最該記住的一行**：**FP8 需要 Ada（L40S/4090）或 Hopper（H100/H200）以上。A100 沒有原生 FP8。** 這一條決定了非常多的架構選擇——A100 叢集只能走 AWQ/GPTQ/INT8 路線。

**Marlin** 值得單獨提：它是 W4A16 的高效能 kernel，把 AWQ/GPTQ 模型的反量化開銷壓到很低。vLLM 會在支援的硬體上自動選用（`gptq_marlin`、`awq_marlin`），日誌會顯示。如果你看到 `Using ExllamaV2` 或非 Marlin 的 kernel，效能會差一截，檢查一下模型的 group_size 與 desc_act 設定是否被 Marlin 支援。

### 5.3 怎麼選

```
選擇             選 X 的理由                        不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────
FP8 (W8A8)       記憶體 50%，算力 ~2×               需 Ada/Hopper+
vs FP16          品質損失極小（多數評測 <1%）       Ampere 及更舊無原生支援
                 可線上量化（--quantization fp8），
                 不需預先產生量化權重
                 ────────────────────────────────────────────────────────
                 翻轉條件：你在 H100/H200/L40S 上 → 幾乎沒理由跑 FP16。
                 這是 2026 年最該預設開啟的一個選項。

AWQ/GPTQ (W4A16) 記憶體 25%，壓縮率最高            品質損失較明顯（1–3%）
vs FP8           Ampere/Turing 也能用               prefill 階段可能比 FP16 慢
                 適合單卡塞大模型                   需要預先量化的 checkpoint
                 ────────────────────────────────────────────────────────
                 翻轉條件：A100 上要跑 70B 單卡，或你就是要把 120B 塞進 2 張卡 →
                 W4 是唯一解。有 H100 且併發高 → FP8 更好。

AWQ              激活感知，通常品質略優於 GPTQ      模型可得性：某些模型
vs GPTQ          Marlin kernel 支援好               只有 GPTQ 版本
                 ────────────────────────────────────────────────────────
                 翻轉條件：看 HuggingFace 上有哪個版本。品質差異在多數任務
                 小於評測噪聲，別為此糾結——挑有 Marlin 支援的那個。

llm-compressor   官方推薦的起點                     需要自己跑量化流程
vs 現成量化模型  支援 FP8/INT8/INT4 多格式          （需要校準資料集與 GPU 時間）
                 可針對你的資料校準，品質更好
                 ────────────────────────────────────────────────────────
                 翻轉條件：你的領域資料分布特殊（醫療、法律、非英語），
                 自己校準值得。一般場景用社群現成的量化模型即可。

GGUF             單檔攜帶、llama.cpp 生態           vLLM 的 GGUF 支援
vs 原生格式      極低 bit（2–3 bit）選項多          成熟度不如 AWQ/GPTQ，
                                                    效能通常較差
                 ────────────────────────────────────────────────────────
                 翻轉條件：你已經有 GGUF 檔且不想重新量化。生產環境建議
                 用 AWQ/GPTQ/FP8。

不量化           零品質風險                         浪費記憶體與頻寬
                 除錯基準線                         ────────────────────
                 翻轉條件：做品質評測的對照組、或模型很小（< 3B）記憶體
                 根本不是問題時。
```

### 5.4 品質驗證：別跳過這步

量化必然有損。**上線前必須用你自己的評測集比一次**，而不是看別人的 MMLU 分數。

一個務實的做法：

```
1. 準備 200–500 筆你的真實請求（含預期輸出或人工評分標準）
2. FP16 基準跑一次，存下輸出
3. 量化版本跑一次
4. 比較：
   · 自動指標（若有標準答案）：準確率、F1、BLEU
   · LLM-as-judge：用一個更強的模型兩兩比較
   · 人工抽樣：至少看 50 筆
5. 特別檢查：長 context 的精確召回、數字、專有名詞、多語言
   ← 這幾類最容易在量化後退化
```

第 5 點的原因：量化的誤差在 attention 的長距離依賴上會累積，而「從 50K token 裡找出那個數字」正是最依賴長距離精確 attention 的任務。

---

## 六、torch.compile 與 Piecewise CUDA Graph

第三道牆：GPU 沒跑滿，但不是記憶體問題。

### 6.1 問題：Python 的 CPU 開銷

```
一次 forward 的 CPU 端工作（80 層模型）：

for layer in layers:            ← Python 迴圈
    x = layer.input_norm(x)     ← PyTorch dispatch → CUDA kernel launch
    x = layer.attn(x)           ← 多個 kernel
    x = layer.post_norm(x)      ← ...
    x = layer.mlp(x)            ← ...

每層約 15–30 次 kernel launch，80 層 → 1200–2400 次
每次 launch 的 CPU 開銷約 5–10 µs → 總計 6–24 ms 的純 CPU 時間

小模型的 decode step 本身可能只要 8 ms
→ CPU 成為瓶頸，GPU 在等 CPU 餵指令
```

兩個解法疊加：

1. **torch.compile**：把多個小算子融合成大 kernel，減少 launch 次數與中間 tensor。
2. **CUDA Graph**：把整串 kernel launch 序列錄下來，之後一次 replay，**CPU 開銷降到接近零**。

### 6.2 為什麼是「piecewise」

CUDA Graph 要求**所有 kernel 的形狀與位址在 replay 時完全固定**。但 attention 做不到：

- KV cache 的 block_table 每輪都不同
- 序列長度每輪都變
- 不同 backend 內部有動態分支

所以 vLLM 選了一個折衷：**以 attention 為切點，把計算圖切成數段，只對 attention 之間的段落錄 CUDA Graph**。

```
一層 Transformer 的 piecewise 切分：

┌──────────────────────────────────────────────────────────────┐
│  [CUDA Graph 片段 A]                                          │
│   input_layernorm → QKV projection → rope                    │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  torch.ops.vllm.unified_attention_with_output                │
│  ← 對 Dynamo 是一個不透明的 custom op（splitting_op）         │
│  ← eager 模式執行，可以自由處理 block_table 與動態形狀        │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  [CUDA Graph 片段 B]                                          │
│   out projection → residual → post_norm → MLP → residual     │
└──────────────────────────────────────────────────────────────┘
```

官方設計文件的描述是：**只對 attention 之間的段落捕捉 cudagraph**，好處是「讓 attention 保持 eager 的彈性、簡化記憶體管理（不用把 attention kernel 納入圖的記憶體池）」。

### 6.3 三種 cudagraph_mode

| 模式 | 行為 | 適用 |
|---|---|---|
| `PIECEWISE`（預設） | 只捕捉 attention 之間的片段 | 通用、安全 |
| `FULL` | 連 attention 一起捕捉（需 backend 支援） | 小模型、MoE，decode 可再快一些 |
| `FULL_AND_PIECEWISE` | decode 用 FULL、prefill 用 PIECEWISE | 兩邊都要 |
| `NONE` | 關閉 | 除錯用 |

```bash
# 除錯：關閉編譯與圖捕捉，看是不是它們的問題
vllm serve <model> --enforce-eager

# 追求 decode 極速（小模型）
vllm serve <model> --compilation-config '{"cudagraph_mode":"FULL_AND_PIECEWISE"}'

# 限制捕捉的形狀，減少啟動時間與記憶體
vllm serve <model> --compilation-config '{"cudagraph_capture_sizes":[1,8,16,32,64,128]}'
```

### 6.4 啟動時間與快取

torch.compile 的編譯很慢（首次可能 3–10 分鐘）。兩個關鍵事實：

1. **所有編譯在服務請求之前完成**——官方文件強調「沒有請求會觸發新的編譯」，所以不會出現線上的延遲尖刺。
2. **編譯結果會快取在 `~/.cache/vllm/torch_compile_cache`**，快取鍵由設定、PyTorch 版本、模型程式碼 hash 共同決定。

**生產環境必做**：把這個目錄掛成 PVC 或烘進 image。否則每次 pod 重啟都要重編譯 5 分鐘，autoscaling 完全失去意義。

```yaml
# K8s 範例
volumeMounts:
  - name: vllm-compile-cache
    mountPath: /root/.cache/vllm
```

---

## 七、Attention Backend：那個你通常不該動的選項

vLLM 有多個 attention 實作，啟動時自動選擇：

| Backend | 適用 | 特點 |
|---|---|---|
| FlashAttention（v2/v3） | Ampere 以上，多數情況 | 通用預設，成熟穩定；v3 需 Hopper |
| FlashInfer | Hopper/Blackwell | 在某些形狀與 FP8 路徑上更快；JIT 編譯 kernel |
| Triton 版 | 廣泛硬體（含 AMD） | 可攜性好，效能略遜 |
| FlashMLA | DeepSeek 系 MLA 架構 | MLA 專用，把 KV 壓成 latent |
| XFormers | 舊硬體 fallback | 相容性用途 |

```bash
# 覆寫（除錯或已知某 backend 更快時）
VLLM_ATTENTION_BACKEND=FLASHINFER vllm serve <model>
```

**通常不要動它。** vLLM 的自動選擇考慮了 GPU 架構、head_dim、dtype、是否用 FP8 KV、block_size 等多個因素。但有兩個情況值得檢查啟動日誌：

1. **看到 fallback 警告**（例如「FP8 KV cache not supported by backend X, falling back to Y」）→ 你開的某個功能可能沒生效。
2. **效能明顯低於同類報告** → 試著換 backend 做 A/B。FlashInfer 在 Hopper + FP8 的某些配置上確實更快。

**MLA 值得特別說明**：DeepSeek 系列用的 Multi-head Latent Attention 把 KV 壓縮成一個低維 latent 向量再展開，**KV cache 可以小一個數量級**。這是架構層面的優化，比任何量化都有效——但只有支援 MLA 的模型能用。這也呼應 Part 2 的結論：**模型架構對推論成本的影響大於引擎優化**。

---

## 八、三個真實配置的完整推導

### 8.1 案例 A：8B 模型、4×L40S 48GB、聊天服務

```
① 量化：L40S 是 Ada → 支援 FP8。8B FP8 = 8 GB
② 平行：8 GB 放得下單卡（48 GB），KV 池可得約 35 GB
   → 併發充足，不需要 TP
   → L40S 之間沒有 NVLink，TP 反而會被 PCIe 拖累
③ 結論：跑 4 個獨立實例（DP 式部署），前面放 LB
```

```bash
# 每張卡一個實例，用 CUDA_VISIBLE_DEVICES 分開
CUDA_VISIBLE_DEVICES=0 vllm serve <8B-FP8> --port 8000 \
  --max-model-len 8192 --max-num-batched-tokens 4096
# ... 重複 GPU 1,2,3
```

**吞吐是 TP=4 的 1.3–1.8 倍**，因為完全沒有跨卡通訊。**代價**：前綴快取分散在 4 個實例，需要前綴感知路由才能挽回（Part 5）。

### 8.2 案例 B：70B、8×H100、RAG 服務

```
① 量化：H100 支援 FP8。70B FP8 = 70 GB
② 平行：70 GB 單卡（80GB）放得下但只剩 5 GB 給 KV → 併發個位數，不可行
   TP=2 → 每卡 35 GB 權重，KV 池 ~35 GB/卡，總 70 GB
   → 20K context 下併發約 25×，可行
③ 8 張卡 → 4 組 TP=2 的實例
```

```bash
vllm serve <70B-FP8> --tensor-parallel-size 2 \
  --max-model-len 32768 --kv-cache-dtype fp8 \
  --max-num-batched-tokens 16384 --gpu-memory-utilization 0.93
```

**為什麼不是 1 組 TP=8？** 因為 TP=8 的 all-reduce 開銷比 TP=2 大得多，而 TP=2 已經解決了容量問題。**「夠用就好」是 TP 的原則**——TP 只在你需要更多記憶體時增加，不是越大越好。

### 8.3 案例 C：超大 MoE（600B 級）、2 節點 × 8×H200

```
① 量化：FP8 → 約 600 GB
② 單節點 8×141GB = 1128 GB，放得下
   但要留 KV 空間 → 跨 2 節點更舒服
③ MoE 架構 → attention 用 DP、expert 用 EP
④ 跨節點必須有 InfiniBand + GPUDirect RDMA
```

```bash
# 每節點
vllm serve <moe-fp8> \
  --data-parallel-size 16 \
  --enable-expert-parallel \
  --tensor-parallel-size 1 \
  --nnodes 2 --node-rank $RANK --master-addr $HEAD_IP \
  --gpu-memory-utilization 0.92
```

**上線前第一件事**：`NCCL_DEBUG=INFO` 確認看到 `NET/IB/GDRDMA`。這個配置若走 TCP，效能會差一個數量級。

---

## 九、為什麼選 X 不選 Y（彙整）

```
選擇                選 X 的理由                      不選 Y 的理由 / 翻轉條件
─────────────────────────────────────────────────────────────────────────────
先量化後平行化      量化是純賺：省記憶體+省頻寬      先平行化：引入通訊開銷，
vs 先平行化後量化   減少所需卡數                      且可能發現量化後根本不需要
                    ─────────────────────────────────────────────────────────
                    翻轉條件：品質要求極高、不接受任何量化損失的場景
                    （法務、醫療的關鍵決策）。此時只能靠加卡。

TP 限節點內         all-reduce 走 NVLink，20 GB      跨節點 TP：即使 400G IB
vs TP 跨節點        流量約 22 ms                      也要 50 ms+，且延遲抖動大
                    ─────────────────────────────────────────────────────────
                    翻轉條件：無。跨節點一律用 PP 或 DP。這是硬性建議。

TP（節點內）        降低單請求延遲                    PP：不降延遲，需要併發
vs PP（節點間）     通訊頻繁但頻寬足夠                填滿管線；但通訊量小，
                                                      可跨機
                    ─────────────────────────────────────────────────────────
                    翻轉條件：GPU 數無法整除 head 數 → 只能 PP。
                    沒有 NVLink 的卡（L40S）→ PP 可能勝過 TP。

DP（多實例）        零通訊，吞吐線性                  TP：延遲較好，前綴快取
vs TP（單實例）     故障隔離好                        集中不分散
                    ─────────────────────────────────────────────────────────
                    翻轉條件：模型放得下單卡 → 選 DP（多實例）。
                    放不下 → 只能 TP。前綴命中是主要收益 → TP 或前綴感知路由。

DP+EP（MoE）        KV cache 不重複儲存               純 TP：MLA/GQA 下 KV head
vs 純 TP            expert 天然可切                   太少，TP 會複製 KV
                    ─────────────────────────────────────────────────────────
                    翻轉條件：稠密模型（非 MoE）→ 沒有 EP 可用，回到 TP/PP。

torch.compile 開    減少 kernel launch 與中間 tensor  關閉：啟動快、除錯直接
vs --enforce-eager  小模型收益最大（CPU bound）        ─────────────────────
                    ─────────────────────────────────────────────────────────
                    翻轉條件：除錯時、或你在快速迭代模型程式碼時，用
                    `--enforce-eager` 省下每次 5 分鐘的編譯。生產環境一定要開。

PIECEWISE graph     通用、安全、attention 保持彈性    FULL：decode 可再快一些
vs FULL graph                                         但需 backend 支援且記憶體
                                                      佔用更高
                    ─────────────────────────────────────────────────────────
                    翻轉條件：小模型（< 14B）+ 低併發 + 延遲敏感 →
                    試 FULL_AND_PIECEWISE，量測後再決定。
```

---

## 十、系列導航

本篇處理了三道牆：**量化**打掉頻寬牆（也順便幫容量牆）、**TP/PP/DP/EP** 打掉容量牆、**torch.compile 與 CUDA Graph** 打掉開銷牆。順序很重要：先壓縮，不夠才切，最後才調編譯。

到這裡，引擎本身的機制已經講完了：記憶體怎麼管、誰在什麼時候跑、模型怎麼切怎麼壓、kernel 怎麼加速。

最後一篇回到**系統**：把這個引擎放進一個真實的生產環境需要什麼。OpenAI 相容 API 的完整面、一個基礎模型上掛幾十個 LoRA 的多租戶做法、結構化輸出怎麼在取樣層強制約束、那份完整的 Prometheus 指標表以及從症狀反推診斷的方法、P/D 分離與 KV connector 的實際配置、還有最實際的一題——**怎麼 benchmark 才不會騙自己**。

- **Part 5 — 生產部署與服務化**：API 面、Multi-LoRA、結構化輸出、可觀測性、P/D 分離、容量規劃

← [Part 3 — 連續批次與排程器 — 決定誰在這一輪前進一格](../vllm-intro-part3-scheduler-continuous-batching-zh) | [Part 5 — 生產部署與服務化 — 從 vllm serve 到一份可被驗收的 SLO →](../vllm-intro-part5-production-serving-zh)

---

*本文基於 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）、官方平行化與擴充文件、量化支援矩陣、torch.compile 設計文件撰寫。通訊量、延遲與成本數字為量級估算；量化的品質影響依模型與任務而異，務必用自己的評測集驗證。*
