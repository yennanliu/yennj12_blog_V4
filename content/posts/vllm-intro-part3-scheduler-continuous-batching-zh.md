---
title: "vLLM Intro Part 3 — 連續批次與排程器 — 決定誰在這一輪前進一格"
date: 2026-09-11T11:00:00+08:00
draft: false
weight: 3
description: "vLLM 原始碼導讀系列第三篇：拆解連續批次的實作、V1 統一 token 預算排程器如何取代 V0 的雙軌制、Chunked Prefill 在 TTFT 與 ITL 之間的取捨、搶佔與重算機制、投機解碼的接受率數學，以及一份可直接套用的調參手冊。"
categories: ["all", "ai", "engineering", "architecture"]
tags: ["vLLM", "Scheduler", "Continuous Batching", "Chunked Prefill", "Speculative Decoding", "LLM", "AI", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
---

> *大多數人調 LLM 推論效能的方式，是把 batch size 調大，看到吞吐上升就停手。*
> *真正的答案是：在連續批次的世界裡「batch size」根本不是一個固定值——它是排程器每一輪重新決定的結果，而排程器真正在分配的不是「幾個請求」，是「這一輪的 token 預算怎麼切」。*
> *看不懂那份預算表，你調的每一個參數都是在賭。*

---

## 前言

[Part 2](../vllm-intro-part2-paged-attention-kv-cache-zh) 把 KV 記憶體管好了：分頁、共享、快取、量化。但記憶體只是**配額**。

這一篇處理的是**分配**：每一次 GPU forward 之前，有一個元件要回答「這一輪跑哪些請求、每個請求推進幾個 token」。它叫 Scheduler，住在 `vllm/v1/core/sched/scheduler.py`，是整個 vLLM 裡最短但最關鍵的一段程式碼——**你所有的延遲數字都是它的輸出**。

本篇的目標：**讀完之後，你看到 P99 ITL 抖動能立刻猜出是哪個參數的問題，看到 GPU 利用率低能說出是 CPU bound 還是 batch 湊不起來，並且知道投機解碼在你的負載下是賺還是賠。**

---

## 一、核心問題：靜態批次的氣泡

先看清楚被連續批次取代的東西。

### 1.1 靜態批次為什麼浪費

```
靜態批次（static batching）：湊滿 4 個請求一起跑，跑完整批才換下一批

時間 →   t0    t1    t2    t3    t4    t5    t6    t7    t8
       ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
req A  │ P   │ D   │ D   │ END │░░░░░│░░░░░│░░░░░│░░░░░│░░░░░│ 3 個 token
req B  │ P   │ D   │ D   │ D   │ D   │ D   │ D   │ D   │ END │ 8 個 token
req C  │ P   │ D   │ END │░░░░░│░░░░░│░░░░░│░░░░░│░░░░░│░░░░░│ 2 個 token
req D  │ P   │ D   │ D   │ D   │ END │░░░░░│░░░░░│░░░░░│░░░░░│ 4 個 token
       └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
                                  ↑
                        ░░░ = 氣泡：GPU 在算 padding，純浪費
                        req E 在門外排隊，但要等 t8 之後才能進來

有效算力 = 17 / (4×9) = 47%
```

兩個獨立的損失：

1. **Padding 浪費**：短序列結束後，它在 batch 裡的位置變成 padding，GPU 照算不誤。生成長度分布越發散，浪費越大。真實流量的輸出長度常呈重尾分布（多數 50 token，少數 2000 token），**47% 已經是樂觀估計**。
2. **排隊延遲**：新請求必須等整批結束。P99 TTFT 直接等於「最長那個請求的總生成時間」。

### 1.2 連續批次：以 iteration 為單位

```
連續批次（continuous batching）：每一輪重新決定 batch 組成

時間 →   t0    t1    t2    t3    t4    t5    t6    t7    t8
       ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
req A  │ P   │ D   │ D   │ END │     │     │     │     │     │
req B  │ P   │ D   │ D   │ D   │ D   │ D   │ D   │ D   │ END │
req C  │ P   │ D   │ END │     │     │     │     │     │     │
req D  │ P   │ D   │ D   │ D   │ END │     │     │     │     │
req E  │     │     │ P   │ D   │ D   │ D   │ D   │ END │     │  ← C 一走就補上
req F  │     │     │     │ P   │ D   │ D   │ D   │ D   │ END │  ← A 一走就補上
       └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
         槽位永遠是滿的，沒有 padding 氣泡
有效算力 ≈ 90%+
```

機制只有一句話：**每一個 forward step 結束後，排程器重新檢查所有請求的狀態，完成的移出、等待的移入。** 沒有「批」這個概念，只有「這一輪」。

這件事之所以可行，完全建立在 Part 2 的分頁機制上——序列可以隨時進出，是因為它們的 KV 不需要連續空間；新請求能立刻插入，是因為配 block 是 O(1) 的。**PagedAttention 是連續批次的前提條件**，兩者是同一套設計的兩面。

---

## 二、三個演進階段

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：靜態批次 —— 湊滿才跑                     ║
### ╚═══════════════════════════════════════════════════╝

```
┌─────────────┐   湊滿 N 個或等 T 毫秒   ┌──────────────┐
│ 請求佇列    │ ───────────────────────▶ │ model.generate│
└─────────────┘                          │ (整批跑到完)  │
                                         └──────────────┘
```

- **可接受的捷徑**：程式碼 30 行，用 HF Transformers 就能寫完。
- **成本**：GPU 有效利用率 30–50%；P99 TTFT = 最長請求的完整生成時間（可能是 30 秒）。
- **解決了什麼**：比逐一處理好——至少攤提了權重搬運。
- **還沒解決什麼**：氣泡、排隊延遲、以及最痛的一點——**你無法同時滿足吞吐與延遲**，只能二選一。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：連續批次 + 雙軌排程（V0 模式）           ║
### ╚═══════════════════════════════════════════════════╝

```
┌──────────┐        ┌─────────────────────────────────────┐
│ waiting  │───────▶│ Scheduler（每 iteration 跑一次）     │
│ queue    │        │  IF 有 waiting 且記憶體夠            │
└──────────┘        │     → 組一個「prefill batch」        │
┌──────────┐        │  ELSE                                │
│ running  │◀──────▶│     → 組一個「decode batch」         │
│ queue    │        │  兩者互斥，一輪只能是其中一種         │
└──────────┘        └─────────────────────────────────────┘
┌──────────┐
│ swapped  │  記憶體不足時被換到 CPU 的請求
└──────────┘
```

- **新增元件**：三個佇列、搶佔機制（recompute / swap 兩種策略）、每 iteration 的重新排程迴圈。
- **複雜度 delta**：從「一個函式」變成「一個狀態機」。prefill 與 decode 兩套路徑各自有 batch 組裝、記憶體檢查、kernel 選擇邏輯，**大量重複程式碼**。
- **效果 delta**：GPU 利用率 30% → 70–80%；P99 TTFT 從「等整批」變成「等一輪」。
- **解決了什麼**：氣泡與排隊。
- **還沒解決什麼**：**prefill 與 decode 互斥造成的抖動**。一個 32K token 的 prompt 進來，那一輪全部拿去做 prefill，所有正在 decode 的使用者卡住 800ms——ITL 出現一根巨大的尖刺。這就是著名的 "prefill 打斷 decode" 問題。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：統一 token 預算（V1 模式）               ║
### ╚═══════════════════════════════════════════════════╝

```
┌──────────────────────────────────────────────────────────────┐
│  Scheduler（V1）：不分 prefill/decode，只分 token 預算         │
│                                                               │
│  token_budget = max_num_batched_tokens   (例如 8192)          │
│                                                               │
│  輸出一份字典：                                                │
│  {                                                            │
│    "req_A": 1,      ← decode 中，推進 1 個 token               │
│    "req_B": 1,      ← decode 中                               │
│    "req_C": 1,      ← decode 中                               │
│    ...（60 個 decode 請求，共 60 token）                       │
│    "req_X": 4096,   ← prefill 中，這輪只做 4096 個（chunked）  │
│    "req_Y": 4036,   ← prefill 中，吃掉剩下的預算               │
│  }                  總和 = 8192 ✓                             │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼  一次 forward，全部一起跑
              ┌──────────────────────────────────┐
              │ 60 個 decode token + 8132 個      │
              │ prefill token 在同一個 batch 裡   │
              └──────────────────────────────────┘
```

- **新增元件**：其實是**移除**元件。沒有 prefill batch / decode batch 的分支、沒有 swapped queue（V1 移除 CPU swap）、沒有依模型特性決定是否開 chunked prefill 的啟發式。
- **複雜度 delta**：**下降**。官方 V1 指南說明新排程器「以一個 per-request 的 token 預算字典消除了 prefill/decode 的嚴格分界」，讓 chunked prefill、prefix caching、投機解碼可以無縫疊加——因為它們在這個模型下都只是「某個請求這輪要幾個 token」的不同算法。
- **效果 delta**：P99 ITL 的尖刺大幅收斂；CPU 開銷下降（少了一整套分支邏輯）。
- **解決了什麼**：prefill 打斷 decode。
- **還沒解決什麼**：**單輪內的公平性仍是 FCFS**（或 priority）。一個超長 prompt 仍會在多輪內持續吃掉大部分預算；「concurrent partial prefills」（同時推進多個 prefill 的細緻配額）在官方功能表上仍標記為進行中。

**這就是為什麼 V1 值得整個重寫。** 不是為了效能數字，是為了讓「加一個新功能」不再需要改兩條路徑。

---

## 三、V1 排程器：一輪裡發生什麼

拆解 `Scheduler.schedule()` 的邏輯骨架。

```
每個 iteration：

┌─ 初始化 ──────────────────────────────────────────────┐
│  token_budget = max_num_batched_tokens                 │
│  scheduled = {}                                        │
└────────────────────────────────────────────────────────┘
            │
┌─ 步驟 1：先服務 running（decode 優先） ────────────────┐
│  for req in running:                                   │
│     需要的 token 數 = 1（或 1+k，若開投機解碼）         │
│     需要新 block 嗎？（token 數 % block_size == 0）     │
│       ├─ 要，但 KV 池沒空位                             │
│       │    → 【搶佔】從 running 尾端踢出最晚來的請求     │
│       │      釋放它的 block，把它放回 waiting 隊首       │
│       │      重試本請求                                 │
│       └─ 有空位 → 配置                                 │
│     scheduled[req] = 1;  token_budget -= 1             │
└────────────────────────────────────────────────────────┘
            │
┌─ 步驟 2：用剩餘預算服務 waiting（prefill） ────────────┐
│  while token_budget > 0 and waiting:                   │
│     req = waiting[0]        ← FCFS，或依 priority 排序  │
│     ① 查前綴快取 → 得到 num_computed_tokens             │
│     ② 還要算的 = len(prompt) − num_computed_tokens      │
│     ③ 這輪實際做 = min(還要算的, token_budget)          │
│           ← 【chunked prefill 就是這一行】              │
│     ④ 向 KVCacheManager 要 block；要不到就 break        │
│     ⑤ scheduled[req] = 這輪實際做                       │
│        token_budget -= 這輪實際做                       │
│        若沒做完 → 它留在「partial prefill」狀態，下輪續 │
│     ⑥ 檢查 len(running) < max_num_seqs，否則 break      │
└────────────────────────────────────────────────────────┘
            │
            ▼
      SchedulerOutput → Executor → GPUModelRunner.forward()
```

四個值得標出來的細節：

**細節一：decode 優先於 prefill。** 步驟 1 先跑完才輪到步驟 2。理由是**已經在生成的使用者正在等**，而還在排隊的使用者還沒開始等。這個順序讓 ITL 比 TTFT 更受保護——符合「串流體驗中，卡住比慢開始更難受」的直覺。

**細節二：搶佔發生在步驟 1 的中間，不是事後補救。** 排程器不會先組好 batch 再發現 OOM，而是邊配置邊檢查，配不到就當場搶佔。被搶佔的一定是 running 佇列**尾端**（最晚加入的），這讓早到的請求不會被反覆搶佔而餓死。

**細節三：兩個獨立的上限。** `token_budget`（`max_num_batched_tokens`）限制「這輪算多少 token」，`max_num_seqs` 限制「同時有多少請求在飛」。前者控制單輪 forward 的時長，後者控制 batch 的寬度。**兩個都會成為瓶頸，且症狀不同**——第八節有對照表。

**細節四：partial prefill 的狀態就在 `num_computed_tokens` 這個數字裡。** 沒有額外的狀態機。一個請求 prefill 到一半，它就只是「一個 `num_computed_tokens=4096` 但 prompt 長度 12288 的請求」，下一輪照樣走步驟 2 的邏輯。**這種「用一個數字表達狀態」的設計，是 V1 比 V0 乾淨的根本原因。**

### 3.1 排程策略：FCFS vs Priority

```bash
# 預設
--scheduling-policy fcfs

# 優先序（數字小 = 優先高，同優先序內仍 FCFS）
--scheduling-policy priority
```

priority 模式下，請求可帶 `priority` 參數。**適用場景**：同一個叢集同時服務互動式聊天（低延遲要求）與批次任務（可等）。把批次任務設低優先序，它們會自動填滿互動流量的空隙，且尖峰時第一個被搶佔。

**注意**：priority 只影響「誰先進 running」與「誰先被搶佔」，不影響已在 running 中的請求每輪拿到的 token 數（decode 都是 1 個）。它不是一個 QoS 的完整解法。

---

## 四、Chunked Prefill：那個最該懂的旋鈕

`max_num_batched_tokens` 是 vLLM 裡影響延遲曲線最大的單一參數。

### 4.1 它在做什麼

```
情境：一個 32,768 token 的 prompt 進來，同時有 60 個使用者正在 decode

【沒有 chunked prefill】
  iteration N:   32,768 個 prefill token，0 個 decode
                 forward 耗時 ≈ 800 ms
                 → 60 個使用者的 ITL 這一輪變成 800 ms（平常 15 ms）
                 → P99 ITL 圖表上一根 50 倍高的尖刺

【有 chunked prefill，max_num_batched_tokens = 8192】
  iteration N:   60 decode + 8,132 prefill   → ≈ 200 ms
  iteration N+1: 60 decode + 8,132 prefill   → ≈ 200 ms
  iteration N+2: 60 decode + 8,132 prefill   → ≈ 200 ms
  iteration N+3: 60 decode + 8,192 prefill   → ≈ 200 ms（做完）
                 → 每輪 ITL 200 ms，尖刺高度降為 1/4
                 → 該請求的 TTFT 從 800ms 變成 800ms（總量沒變，但分散了）

【max_num_batched_tokens = 2048】
  需要 16 輪，每輪 ≈ 55 ms
                 → ITL 尖刺幾乎看不出來
                 → 但該請求的 TTFT 變成 16 × 55 = 880 ms（略增，因為每輪有固定開銷）
                 → 且 decode 的攤提變差：每輪只有 60 個 decode token 卻要付一次完整權重搬運
```

**核心取捨一句話**：`max_num_batched_tokens` 大 → TTFT 好、吞吐好、ITL 差；小 → ITL 好、TTFT 與吞吐差。

官方調參文件給的方向很明確：

| 設定 | 官方描述 | 適用 |
|---|---|---|
| 2048 | 較佳的 inter-token latency | 互動式聊天，ITL 是主要 SLO |
| 8192+ | 較佳的 TTFT 與吞吐 | 一般平衡點，V1 的典型預設量級 |
| > 8192（大 GPU） | 「為取得最佳吞吐，在大 GPU 上設為 > 8192」 | 批次處理、離線推論、長 prompt RAG |

### 4.2 為什麼不能無限大

三個天花板：

1. **記憶體**：`max_num_batched_tokens` 直接決定 profiling 時量到的峰值 activation。設 65536 會讓 activation 吃掉好幾 GB，這些記憶體是從 KV 池扣的——**你可能因為把預算設太大而讓併發數下降**。
2. **CUDA graph 捕捉**：V1 對不同 batch 形狀捕捉 CUDA graph，形狀空間太大會拉長啟動時間與記憶體。
3. **報酬遞減**：prefill 在幾千 token 時就已經 compute-bound 了，再加 token 只是線性增加時間，不再提升 GPU 效率。

### 4.3 一個實用的起手式

```
你的 SLO 是什麼？
    │
    ├── 「串流要順」（ITL 主導，如聊天 UI）
    │      → max_num_batched_tokens = 2048~4096
    │        max_num_seqs = 128~256
    │
    ├── 「要快點開始回」（TTFT 主導，如搜尋摘要）
    │      → max_num_batched_tokens = 8192~16384
    │        並考慮 P/D 分離（Part 5）
    │
    └── 「只要總量大」（吞吐主導，如離線批次）
           → max_num_batched_tokens = 16384~32768
             max_num_seqs = 512+
             gpu_memory_utilization = 0.95
```

設完之後**必看**：`vllm:time_to_first_token_seconds` 與 `vllm:inter_token_latency_seconds` 的 P95/P99，而不是平均值。平均值在這裡毫無資訊量。

---

## 五、搶佔：記憶體不足時誰倒楣

當 running 中的請求要新 block 而 KV 池空了，排程器搶佔。

```
搶佔流程（V1）：

  running = [A(早), B, C, D, E(晚)]
  A 需要新 block，但 free queue 空了
        │
        ▼
  從 running 尾端取 E
  ├─ 釋放 E 的所有 block（ref_cnt--，放回 free queue）
  ├─ E 的 num_computed_tokens 重設為 0（或前綴快取命中的部分）
  └─ E 插回 waiting 佇列的最前面
        │
        ▼
  A 拿到 block，繼續
        │
        ▼
  之後 E 重新被排程時：整段 prompt + 已生成的 token 全部重算 prefill
  （但前綴快取可能救回大部分 —— 這是兩個機制的協同）
```

### 5.1 為什麼 V1 選 recompute 而非 swap

V0 有兩種搶佔策略，V1 只留一種：

```
選擇              選 Recompute 的理由                不選 Swap 的理由
──────────────────────────────────────────────────────────────────────
Recompute         無 PCIe 傳輸，不佔用頻寬            Swap 到 CPU：
vs Swap to CPU    實作簡單，沒有換頁狀態機             · PCIe 頻寬遠低於 HBM，
                  與前綴快取天然協同（重算時大量命中） 　搬 KV 可能比重算還慢
                  GPU 算力相對 PCIe 頻寬「便宜」       · 需要維護 swapped 佇列與
                  V1 已完全移除 swap，相關指標         　換入換出的狀態機
                  （num_requests_swapped、            · 佔用 CPU 記憶體且不可控
                   cpu_cache_usage_perc）也一併移除
                  ────────────────────────────────────────────────────
                  翻轉條件：prompt 極長（100K+）且前綴不可快取時，重算成本
                  理論上高於傳輸成本。但 V1 選擇用更通用的 KV offloading
                  connector（Part 5）覆蓋這個場景，而不是回頭做 swap——
                  因為 connector 可以同時服務「跨實例 KV 共享」這個更大的需求。
```

### 5.2 搶佔是一個警訊

偶發搶佔正常，持續搶佔代表配置有問題。官方調參文件給的四個方向：

| 做法 | 效果 | 代價 |
|---|---|---|
| 提高 `gpu_memory_utilization` | KV 池變大 | OOM 緩衝變小 |
| 降低 `max_num_seqs` | 同時在飛的請求變少 | 吞吐下降 |
| 降低 `max_num_batched_tokens` | 每輪配置需求變小 | TTFT/吞吐下降 |
| 提高 `tensor_parallel_size` / `pipeline_parallel_size` | 每卡分到的 KV 空間變大 | 需要更多卡 + 通訊開銷 |

還有兩個文件沒列但同樣有效的：**開 FP8 KV cache**（Part 2）與**降 `max_model_len`**。後者最常被忽略——很多人把 `max_model_len` 設成模型支援的最大值（128K），但實際 99% 的請求都在 4K 以內，白白讓排程器保守。

---

## 六、投機解碼：用算力換 token 步數

Decode 是 memory-bound 的（Part 1），意思是**GPU 算力在 decode 時是閒置的**。投機解碼把這份閒置算力拿來用。

### 6.1 機制

```
一般 decode：一次 forward 產出 1 個 token
  [已生成] ──forward──▶ t1
  [已生成,t1] ──forward──▶ t2
  [已生成,t1,t2] ──forward──▶ t3
  3 個 token = 3 次權重搬運

投機解碼（num_speculative_tokens = 3）：
  ┌─ 步驟 1：草稿 ────────────────────────────────┐
  │  用便宜的方法猜 3 個 token：t1', t2', t3'      │
  │  · n-gram：查前文有沒有出現過同樣的 pattern    │
  │  · EAGLE/MTP：一個小小的頭，成本約主模型的 5%  │
  │  · draft model：一個 1B 小模型                 │
  └────────────────────────────────────────────────┘
  ┌─ 步驟 2：驗證（一次 forward）─────────────────┐
  │  把 [已生成, t1', t2', t3'] 一起送進主模型     │
  │  ← 這是 prefill 形狀！算力吃得滿，但只搬一次權重│
  │  得到每個位置的真實機率分布                     │
  └────────────────────────────────────────────────┘
  ┌─ 步驟 3：拒絕取樣 ────────────────────────────┐
  │  逐個比對：t1' 接受、t2' 接受、t3' 拒絕        │
  │  → 採納 t1, t2，並從修正分布重新取樣出 t3      │
  │  → 這一次 forward 產出了 3 個 token            │
  └────────────────────────────────────────────────┘
```

**關鍵保證**：vLLM 的拒絕取樣「與目標分布對齊」，也就是**理論上無損**——輸出分布和不開投機解碼完全一致。這不是近似加速。

### 6.2 什麼時候賺、什麼時候賠

設 α 為接受率、k 為投機 token 數、c 為草稿成本佔主模型的比例。每次驗證的期望產出 token 數約為：

```
E[tokens] = (1 − α^(k+1)) / (1 − α)

加速比 ≈ E[tokens] / (1 + c×k)
```

代幾個數：

| 方法 | 典型 α | k | c | E[tokens] | 加速比 |
|---|---|---|---|---|---|
| n-gram（重複性文本） | 0.7 | 3 | ~0 | 2.6 | **2.6×** |
| n-gram（一般文本） | 0.2 | 3 | ~0 | 1.25 | 1.25× |
| EAGLE / MTP | 0.75 | 4 | 0.1 | 3.2 | **2.3×** |
| draft model 1B→70B | 0.6 | 5 | 0.05 | 2.4 | 1.9× |
| draft model 1B→8B | 0.6 | 5 | 0.3 | 2.4 | **0.96×（虧了）** |

最後一行是重點：**草稿模型相對主模型太大，就會賠本**。1B 草稿配 8B 主模型，草稿成本佔 30%，加速比跌破 1。

但上表只算了單條序列。**真正決定賺賠的是 batch 大小**：

```
        低 QPS（batch=4）                高 QPS（batch=128）
    ┌──────────────────────────┐   ┌──────────────────────────┐
    │ GPU 算力大量閒置          │   │ GPU 算力已被 batch 吃滿   │
    │ 投機用掉的是「本來浪費的」│   │ 投機和其他請求搶算力      │
    │ → ITL 明顯下降            │   │ → 總吞吐下降              │
    │ → 淨賺                    │   │ → 淨賠                    │
    └──────────────────────────┘   └──────────────────────────┘
```

官方文件的說法一致：低 QPS（latency-focused）收益高，尤其 EAGLE 與 MTP；高 QPS（throughput-focused）報酬遞減，而 n-gram / suffix decoding 這類極輕量方法「在尖峰流量時的額外開銷最小」。

### 6.3 設定

```bash
# n-gram：零額外模型，適合有大量重複的場景（程式碼補全、文件改寫、結構化輸出）
vllm serve <model> \
  --speculative-config '{"method":"ngram","num_speculative_tokens":3,
                         "prompt_lookup_max":4,"prompt_lookup_min":2}'

# EAGLE：需要對應的 EAGLE 頭權重，加速最明顯
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --speculative-config '{"method":"eagle","model":"<eagle-head-repo>",
                         "num_speculative_tokens":4}'

# draft model：最通用但也最容易賠本
vllm serve <big-model> \
  --speculative-config '{"method":"draft_model","model":"<small-model>",
                         "num_speculative_tokens":5}'
```

Python 端用 `LLM(..., speculative_config={...})`，鍵名相同。

**上線前必做**：用你的真實 trace 跑一次 A/B。官方文件直說「實際收益取決於你的模型家族、流量形態、硬體與取樣設定」。我的建議是把它當成一個**在離峰時段開、尖峰時段關**的動態設定，而不是一個固定配置。

### 6.4 一個容易踩的坑

投機解碼會讓每個請求在一輪內要求 `1 + k` 個 token 的 KV 空間，而不是 1 個。這代表：

- KV 池的消耗速度變成 (1+k) 倍的尖峰（雖然拒絕後會回收）
- 搶佔頻率上升
- `max_num_batched_tokens` 的有效容量下降

如果你開了投機解碼之後看到搶佔指標飆升，先降 `num_speculative_tokens`，再考慮調記憶體。

---

## 七、把三個機制疊在一起看

V1 統一預算模型的價值，在於這三件事可以同時發生而不需要特殊處理：

```
某一個 iteration，token_budget = 8192：

┌────────────────────────────────────────────────────────────────┐
│ req_01 … req_50   各 1 token    = 50      ← 純 decode           │
│ req_51 … req_58   各 5 token    = 40      ← decode + 投機(k=4)  │
│ req_59            2048 token              ← chunked prefill 第 3 塊│
│ req_60            4096 token              ← chunked prefill 第 1 塊│
│ req_61            1958 token              ← 前綴命中 90% 後的殘餘 │
│                   ─────────────────                             │
│                   合計 8192 ✓                                    │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
        一次 forward，一次權重搬運，推進 8192 個 token 的計算
        其中 90 個是「真正產出使用者可見 token」的
```

在 V0 的雙軌模型下，`req_59`~`req_61` 的 prefill 和 `req_01`~`req_58` 的 decode **不可能在同一輪**。V1 之所以能，是因為它從頭就不區分這兩者——對排程器來說，它們都只是「某個請求要算 N 個 token」。

這也解釋了為什麼前綴快取、chunked prefill、投機解碼在 V1 全部是**預設開啟**：它們不是三個互相干擾的功能，而是同一個預算分配問題的三種輸入。

---

## 八、調參手冊：症狀 → 診斷 → 處方

這一節是本篇最實用的部分。左邊是你在 Grafana 上看到的，右邊是你該做的。

### 8.1 症狀對照表

| 症狀（指標） | 最可能的原因 | 處方 | 驗證方式 |
|---|---|---|---|
| P99 ITL 有週期性尖刺，P50 正常 | 長 prompt 的 prefill 塞爆單輪預算 | 降 `max_num_batched_tokens` 到 2048–4096 | 尖刺高度應下降至原本的 1/2–1/4 |
| ITL 整體偏高且平坦 | batch 太大，每輪 forward 本來就慢 | 降 `max_num_seqs` | 吞吐會下降，確認是否可接受 |
| TTFT 的 P50 就很高 | 佇列在排隊，容量不足 | 看 `vllm:num_requests_waiting`；若持續 > 0 則需擴容或降 `max_model_len` | waiting 應回到接近 0 |
| TTFT 高但 `num_requests_waiting` ≈ 0 | prefill 本身慢（prompt 太長 / 預算太小） | 升 `max_num_batched_tokens` | `vllm:request_prefill_time_seconds` 應下降 |
| 吞吐低、GPU 利用率也低 | CPU bound（tokenize / API server） | 加 `--api-server-count`、確認實體核心 ≥ `2+N`、試 `VLLM_USE_FASTOKENS=1` | GPU 利用率應上升 |
| 吞吐低但 GPU 利用率高 | 已經跑滿，是硬體極限 | 擴容 / 量化 / 換架構 | — |
| `vllm:kv_cache_usage_perc` 長期 > 0.95 | KV 池不足，頻繁搶佔 | 見第五節四方向 + FP8 KV | 使用率應降到 0.7–0.9 |
| `kv_cache_usage_perc` 長期 < 0.3 | 記憶體浪費，batch 湊不起來 | 升 `max_num_seqs` 與 `max_num_batched_tokens` | 吞吐應上升 |
| 前綴命中率低但 workload 有共同前綴 | prompt 模板把變動內容放前面；或多副本隨機路由 | 重排 prompt；導入前綴感知路由（Part 5） | `prefix_cache_hits/queries` 應上升 |
| 開了投機解碼後吞吐反而降 | 高 QPS 下算力已飽和 | 關掉，或改用 n-gram，或只在離峰開 | 對照 A/B |
| 啟動很久（> 10 分鐘） | torch.compile 首次編譯 + 權重下載 | 掛載 `~/.cache/vllm/torch_compile_cache`；權重預先放本地 | 第二次啟動應大幅縮短 |

### 8.2 參數之間的關係圖

```
                    ┌─────────────────────────┐
                    │ gpu_memory_utilization  │
                    │        (0.90)           │
                    └───────────┬─────────────┘
                                │ 決定 KV 池大小
                                ▼
              ┌─────────────────────────────────────┐
              │         KV Cache 池                  │
              │   啟動日誌：GPU KV cache size: N     │
              └──────┬───────────────────────┬──────┘
                     │                       │
        限制併發上限 │                       │ 不足時觸發
                     ▼                       ▼
           ┌──────────────────┐      ┌──────────────┐
           │  max_num_seqs    │      │   搶佔       │
           │  (batch 寬度)    │      │ (recompute)  │
           └────────┬─────────┘      └──────────────┘
                    │
                    │  兩者同時限制每輪工作量
                    ▼
           ┌──────────────────────────┐
           │ max_num_batched_tokens   │──▶ 單輪 forward 時長
           │    (token 預算)          │       │
           └──────────────────────────┘       ├──▶ ITL（大則差）
                    │                         └──▶ TTFT（大則好）
                    │ 也決定 profiling 的
                    ▼ 峰值 activation
           ┌──────────────────────────┐
           │ 回頭吃掉 KV 池的空間      │  ← 循環依賴！設太大反而降低併發
           └──────────────────────────┘

           ┌──────────────────────────┐
           │     max_model_len        │──▶ 影響「最壞情況併發估計」
           │  設成 128K 但實際用 4K   │     排程器會過度保守
           └──────────────────────────┘
```

最後那個循環依賴值得再強調：**`max_num_batched_tokens` 設太大會透過 activation 反過來壓縮 KV 池**。這是很多人調參越調越慢的原因——他們只看到「預算變大應該更快」，沒看到併發數悄悄掉了。改完永遠回頭確認啟動日誌的 `GPU KV cache size`。

---

## 九、為什麼選 X 不選 Y

```
選擇                 選 X 的理由                        不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────────
連續批次             GPU 利用率 90%+，無 padding 氣泡    靜態批次：實作簡單，
vs 靜態批次          新請求隨時可插入                    無排程器 CPU 開銷
                     ────────────────────────────────────────────────────────
                     翻轉條件：離線批次且所有序列長度一致（如固定長度的 embedding），
                     靜態批次沒有排程開銷反而更快。生成式服務永遠選連續批次。

統一 token 預算      一套邏輯覆蓋 prefill/decode/投機    雙軌制：prefill 與 decode
vs 雙軌 prefill/     新功能不需要改兩條路徑              各自可用不同 kernel 最佳化
   decode 排程       chunked prefill 天然可行            （但 V1 用 backend 選擇
                                                         解決了這一點）
                     ────────────────────────────────────────────────────────
                     翻轉條件：無。V0 已被移除，這題已有定論。

Decode 優先          保護 ITL：正在串流的使用者不卡頓    Prefill 優先：新請求的
vs Prefill 優先                                          TTFT 更好
                     ────────────────────────────────────────────────────────
                     翻轉條件：非串流的批次 API（使用者只等最終結果），此時 ITL
                     無意義，prefill 優先能提高整體吞吐。vLLM 不直接提供此開關，
                     實務上用「調大 max_num_batched_tokens」達成類似效果。

FCFS                 公平、可預測、無飢餓                Priority：可分級 QoS
vs Priority          實作簡單                            但需要上游正確設 priority
                     ────────────────────────────────────────────────────────
                     翻轉條件：同叢集混跑互動流量與批次任務時，priority 是正解。
                     單一類型流量用 FCFS 就好。

Chunked prefill 開   ITL 尖刺收斂，V1 預設               關閉：長 prompt 的 TTFT
vs 關                長短請求混合場景必要                略好（少了分塊的固定開銷）
                     ────────────────────────────────────────────────────────
                     翻轉條件：純批次離線推論、沒有併發 decode 需要保護時，
                     關掉可以省下每塊的排程開銷。線上服務不要關。

投機解碼開           低 QPS 下 ITL 降 2–3×               關閉：高 QPS 下搶算力，
vs 關                無損（拒絕取樣對齊目標分布）         總吞吐下降；額外 KV 消耗
                     ────────────────────────────────────────────────────────
                     翻轉條件：見 6.2。判準是「你的 GPU 算力在 decode 時是否閒置」。
                     用 batch 大小當代理指標：平均 batch < 16 大概率賺，> 64 大概率賠。

n-gram 投機          零額外模型與記憶體                  EAGLE/MTP：加速更高但
vs EAGLE/MTP         尖峰時開銷最小                      需要對應權重、佔記憶體、
                     重複性文本（程式碼/改寫）效果極好    模型支援有限
                     ────────────────────────────────────────────────────────
                     翻轉條件：你的模型有官方 EAGLE3/MTP 頭且是延遲敏感場景 →
                     選 EAGLE/MTP。否則先試 n-gram，成本幾乎為零。
```

---

## 十、系列導航

本篇把「配額」變成了「分配」：連續批次消除氣泡、統一 token 預算讓 prefill 與 decode 共存、chunked prefill 是那個最該懂的旋鈕、搶佔是壓力的洩壓閥、投機解碼把閒置算力換成 token 步數。

到目前為止，所有討論都在**一張 GPU 的邊界內**。但真實的大模型放不進一張卡，真實的流量也不會停在一台機器。

下一篇跨出這道邊界：四種平行度（TP/PP/DP/EP）各自切開模型的哪一維、通訊量差多少、多機部署時 NCCL 走不走 RDMA 怎麼確認；以及兩個把單卡效率再往上推的方向——量化（AWQ/GPTQ/FP8/INT8 與硬體支援矩陣）與編譯優化（torch.compile 的 piecewise CUDA graph 到底切在哪裡、為什麼要切在 attention 上）。

- **Part 4 — 分散式推論、量化與編譯優化**：TP/PP/DP/EP、多機部署、量化矩陣、torch.compile 與 CUDA Graph

← [Part 2 — PagedAttention 與 KV Cache — 把作業系統的分頁搬進 GPU](../vllm-intro-part2-paged-attention-kv-cache-zh) | [Part 4 — 分散式推論、量化與編譯優化 — 讓模型放得下也跑得快 →](../vllm-intro-part4-distributed-quantization-zh)

---

*本文基於 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）、官方 V1 引擎指南、最佳化與調參文件、投機解碼文件撰寫。排程流程對照 `vllm/v1/core/sched/scheduler.py`；延遲與加速比數字為量級估算，實際值依模型、硬體與流量形態而異。*
