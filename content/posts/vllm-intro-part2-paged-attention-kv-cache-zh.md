---
title: "vLLM Intro Part 2 — PagedAttention 與 KV Cache — 把作業系統的分頁搬進 GPU"
date: 2026-09-11T10:00:00+08:00
draft: false
weight: 2
description: "vLLM 原始碼導讀系列第二篇：拆解 PagedAttention 的分頁機制與 kernel 記憶體佈局、Copy-on-Write 共享、自動前綴快取的 hash 鏈與 LRU 淘汰、KV cache 量化與多層卸載，以及一份能讓你算出併發上限的記憶體規劃手冊。"
categories: ["all", "ai", "engineering"]
tags: ["vLLM", "PagedAttention", "KV Cache", "LLM", "AI", "GPU", "Prefix Caching", "繁體中文"]
authors: ["yen"]
readTime: "26 min"
---

> *大多數人理解 KV cache 的方式，是「把算過的 K 和 V 存起來，下次不用重算」，然後就不再想這件事。*
> *真正的答案是：KV cache 不是一個快取，它是一個**動態成長、生命週期不可預測、大小可達模型權重數倍**的堆積區——它是 GPU 上的 malloc 問題，而不是 memoization 問題。*
> *把它當快取寫，你會浪費 70% 的記憶體。*
> *把它當作業系統的虛擬記憶體寫，你會拿回那 70%。*

---

## 前言

[Part 1](../vllm-intro-part1-architecture-overview-zh) 建立了地圖，也留下一個結論：**記憶體就是吞吐量**。這一篇把那句話展開成機制。

主角是 vLLM 論文的同名貢獻——**PagedAttention**。它的核心洞見用一句話講完：*KV cache 的記憶體管理問題，和作業系統管理虛擬記憶體的問題，是同一個問題。* 因此 OS 五十年來的答案——分頁、頁表、寫入時複製、換頁、LRU——可以整套搬過來。

本篇的目標：**讀完之後，你知道一個 block 裡實際躺著什麼、block table 長什麼樣、前綴命中怎麼判定不會出錯、以及在你的硬體上該把 `--block-size` 和 `--kv-cache-dtype` 設成什麼。**

---

## 一、核心問題：連續配置的三種浪費

先看清楚被 PagedAttention 取代的東西。傳統推論框架為每個序列配一段**連續**的 KV 空間，長度是 `max_model_len`：

```
GPU KV 記憶體（連續配置）

序列 A：max_len=2048，實際只生成 120 個 token
┌──────────────────────────────────────────────────────────┐
│████████│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│ 已用   │              預留但永遠用不到                    │
│ 120    │                  1928                            │
└──────────────────────────────────────────────────────────┘
         ↑ 內部碎片（internal fragmentation）：94% 浪費

序列 B 結束後釋放，留下一個 2048 的洞：
┌────────┬──────────────┬────────┬──────────────┬──────────┐
│ 序列 C │ ░░ 空洞 ░░   │ 序列 D │ ░░ 空洞 ░░   │  未配置  │
└────────┴──────────────┴────────┴──────────────┴──────────┘
                  ↑ 外部碎片：總量夠但沒有夠大的連續段

序列 E 要做 n=4 的平行取樣，共用同一個 prompt：
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ prompt KV ×1 │ prompt KV ×2 │ prompt KV ×3 │ prompt KV ×4 │
└──────────────┴──────────────┴──────────────┴──────────────┘
        ↑ 完全相同的內容存了 4 份：無法共享
```

vLLM 論文對既有系統的量測結論是：**60%–80% 的 KV 記憶體因碎片化與過度預留而浪費**。也就是說，一張 80 GB 的卡上，實際承載有效 KV 的可能只有 15 GB。

三種浪費，三個對應的 OS 概念：

| 浪費類型 | OS 的答案 | vLLM 的實作 |
|---|---|---|
| 內部碎片（預留過多） | 分頁：按需配置固定大小的頁 | KVCacheBlock，預設 16 token/頁 |
| 外部碎片（空洞） | 頁表：邏輯連續 ≠ 實體連續 | block_table，per-request 的邏輯→實體映射 |
| 無法共享 | 寫入時複製（COW） | ref_cnt + 分岔時才複製 |

---

## 二、三個演進階段

同樣的 KV 管理問題，在三個規模下有三套答案。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：連續配置 —— 能跑就好                     ║
### ╚═══════════════════════════════════════════════════╝

```
┌────────────────────────────────────────────────┐
│  KV Cache = torch.zeros(max_seqs, max_len, ...)│
│  每個序列一個固定 slot                          │
│  seq_id → 直接當 index                          │
└────────────────────────────────────────────────┘
```

- **可接受的捷徑**：實作 20 行，attention kernel 用現成的 FlashAttention 即可（因為記憶體連續）。
- **成本**：`max_seqs × max_len × 每token位元組`。8B 模型、64 seqs、8192 len → 64 × 8192 × 128 KB = **64 GB**，而且不管實際用多少都吃這麼多。
- **解決了什麼**：能跑，程式碼簡單，沒有間接層開銷。
- **還沒解決什麼**：全部三種浪費。併發數被 `max_seqs` 硬鎖死，而 `max_seqs` 被記憶體鎖死。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：PagedAttention —— 分頁 + COW             ║
### ╚═══════════════════════════════════════════════════╝

```
邏輯視角（每個 request 看到的）        實體視角（GPU HBM 裡真實的）
┌─────────────────────────────┐       ┌──────────────────────────────┐
│ Request A 的 block_table    │       │  分頁池（BlockPool）          │
│ [ 7, 3, 12, 0 ]             │──┐    │ ┌──┬──┬──┬──┬──┬──┬──┬──┬──┐ │
└─────────────────────────────┘  │    │ │0 │1 │2 │3 │4 │5 │6 │7 │8 │ │
┌─────────────────────────────┐  ├───▶│ ├──┼──┼──┼──┼──┼──┼──┼──┼──┤ │
│ Request B 的 block_table    │  │    │ │A3│B1│free│A1│B2│free│..│A0│..│
│ [ 1, 4, 9 ]                 │──┘    │ └──┴──┴──┴──┴──┴──┴──┴──┴──┘ │
└─────────────────────────────┘       └──────────────────────────────┘
                                       每個 block = 16 個 token 的 K/V
```

- **新增元件**：BlockPool、FreeBlockQueue（雙向鏈結串列，O(1) 摘除/插入）、per-request block_table、以及一個能吃 block_table 的 attention kernel。
- **複雜度 delta**：attention kernel 要自己寫（不能直接用 FlashAttention 的連續版本），因為 K/V 現在散在不連續的實體位置。
- **記憶體 delta**：浪費從 60–80% 降到 **<4%**（只有每條序列的最後一個 block 可能沒填滿）。
- **解決了什麼**：三種浪費全解。同樣 48 GB 的 KV 池，8B 模型從 6 條併發變成 190+ 條。
- **還沒解決什麼**：同一個 system prompt 在不同請求之間仍然重算 prefill。block 釋放後內容就沒人管了。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：Prefix Caching + 多層卸載                ║
### ╚═══════════════════════════════════════════════════╝

```
                    ┌──────────────────────────────────┐
   新請求進來 ─────▶│ 逐 block 算 hash，查 cache_blocks │
                    └────────────┬─────────────────────┘
                        命中 │        │ 未命中
                   ┌─────────▼──┐  ┌──▼──────────────────┐
                   │ ref_cnt++  │  │ 從 free queue 頭部取 │
                   │ 從 free    │  │ 若該 block 有 hash， │
                   │ queue 摘除 │  │ 從 cache 表移除(淘汰)│
                   └────────────┘  └─────────────────────┘
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  ┌───────────┐      ┌─────────────┐      ┌─────────────┐
  │ GPU HBM   │ 溢出 │  CPU DRAM   │ 溢出 │  本地 SSD    │
  │ 熱前綴    │─────▶│  溫前綴     │─────▶│  冷前綴      │
  │ ~µs 存取  │      │ ~ms 存取    │      │ ~10ms 存取   │
  └───────────┘      └─────────────┘      └─────────────┘
      （Offloading Connector / LMCache 等外掛提供二三層）
```

- **新增元件**：block hash 計算（含 parent hash 鏈）、`cache_blocks` 雜湊表、LRU 淘汰策略、以及選配的 KV offloading connector。
- **複雜度 delta**：正確性風險。hash 撞了就會回答錯誤內容——所以 vLLM 從 0.11 起預設用 `sha256`，並把 LoRA id、多模態輸入 hash、cache salt 全部納入 hash 輸入。
- **效果 delta**：長 system prompt / RAG / 多輪對話場景，TTFT 可降 5–20×。
- **解決了什麼**：跨請求的 prefill 重算。
- **還沒解決什麼**：**跨 pod 不共享**。多副本部署時，同一個前綴在 8 個 pod 各存一份，且路由不感知前綴就等於白做——這是 Part 1 Phase 3 要用前綴感知路由解決的問題。

---

## 三、分頁機制：block、block_table、與 slot mapping

### 3.1 一個 block 裡有什麼

`block_size`（預設 16）指的是**一個 block 存幾個 token 的 KV**，注意是「所有層、所有 KV head 的那個 token 的 K 和 V」。

```
一個 KVCacheBlock（block_size=16，Llama-3-8B：32 層、8 KV heads、head_dim=128、FP16）

實際上 vLLM 為「每一層」各配一個 block 池。以單層來看：
┌──────────────────────────────────────────────────────────┐
│ K cache block：8 heads × 16 tokens × 128 dim × 2 bytes    │
│               = 32 KB                                     │
├──────────────────────────────────────────────────────────┤
│ V cache block：同上 = 32 KB                                │
└──────────────────────────────────────────────────────────┘
單層單 block = 64 KB；32 層 → 一個「邏輯 block」實際佔 2 MB

驗算：2 MB / 16 tokens = 128 KB/token ✓ 與 Part 1 的表格一致
```

管理層看到的資料結構很小（`vllm/v1/core/kv_cache_utils.py`）：

```python
class KVCacheBlock:
    block_id: int                          # 實體 block 編號
    block_hash: BlockHash | None           # 內容 hash，None 表示未快取
    ref_cnt: int                           # 有幾個 request 正在用它
    prev_free_block: KVCacheBlock | None   # free queue 的雙向指標
    next_free_block: KVCacheBlock | None
```

**注意 `ref_cnt` 和 `block_hash` 是兩件獨立的事**：

| ref_cnt | block_hash | 狀態 | 在 free queue 裡？ |
|---|---|---|---|
| > 0 | 有 | 正在被使用，且已可被共享 | 否 |
| > 0 | None | 正在被寫入（還沒填滿 16 個 token） | 否 |
| 0 | 有 | **沒人用，但內容還在**——可被前綴命中救回 | 是 |
| 0 | None | 全新或剛被淘汰的空 block | 是 |

第三種狀態是整個設計的精髓：**釋放不等於清空**。一個對話結束了，它的 block 進 free queue 尾端排隊等死，但只要還沒被別人拿走，使用者三十秒後追問時就能整段命中。

### 3.2 block_table：每個請求的頁表

```
Request A：prompt 40 個 token，已生成 5 個，共 45 個 token
block_size = 16 → 需要 ceil(45/16) = 3 個 block

邏輯 block 0   邏輯 block 1   邏輯 block 2
[tok 0..15]    [tok 16..31]   [tok 32..44 + 3 空位]
     │              │               │
     ▼              ▼               ▼
block_table = [  7  ,     3   ,     12   ]
                 │        │          │
                 ▼        ▼          ▼
             實體池的第 7、3、12 個 block（位置完全隨機）
```

在 forward 時，`GPUModelRunner` 把所有 running request 的 block_table 堆成一個 2D tensor `[num_reqs, max_num_blocks]`，連同 `slot_mapping`（每個新 token 要寫到分頁池的哪個絕對位置）一起餵給 attention kernel。

**V1 的 block_table 是 append-only 的**——這是相對 V0 的一個簡化。V1 允許表裡出現重複的 cached block；官方文件說明「這種重複會在 request 釋放時一併消除」，用少量的記帳冗餘換掉一大堆邊界情況。

### 3.3 為什麼 block_size 預設是 16

`--block-size` 可調（8/16/32/64/128）。取捨是：

| block_size | 內部碎片 | block_table 長度 | kernel 效率 | 前綴快取粒度 |
|---|---|---|---|---|
| 8 | 最小（平均浪費 4 token） | 最長，索引開銷大 | 差，每 block 工作量太小 | 最細，命中率最高 |
| **16（預設）** | 平均浪費 8 token | 平衡 | 好，恰好對齊 warp 工作量 | 平衡 |
| 128 | 大（平均浪費 64 token） | 最短 | 好，但 batch 內長度差異大時反而浪費 | 粗，前綴要 128 個 token 完全一致才命中 |

**16 的理由主要來自 kernel**：一個 warp（32 threads）處理一個 query token 對一整個 block 的 K，16 個 token 恰好讓每個 thread group 分到合理的工作量，且 16×head_dim 的資料量對 shared memory 友善。

**翻轉條件**：如果你在跑超長 context（128K+）且前綴幾乎不重複，`--block-size 32` 可以縮短 block_table 的索引開銷；如果你的前綴命中是主要收益來源（大量短 system prompt 變體），`--block-size 8` 能提高命中率。多數情況不要動它。注意部分 attention backend 對 block_size 有限制（例如某些 FlashInfer 路徑只支援特定值），改之前先看啟動日誌有沒有 fallback 警告。

---

## 四、Kernel 層：那個奇怪的記憶體佈局

分頁在管理層很優雅，代價全部丟給 kernel。看一下 `csrc/attention/` 裡 K cache 的形狀：

```
K cache: [num_blocks, num_kv_heads, head_size / x, block_size, x]
V cache: [num_blocks, num_kv_heads, head_size,     block_size]
```

V 的佈局很直覺，K 為什麼多切一個 `x` 出來？

### 4.1 x 是什麼

`x` 由**記憶體對齊**決定：`x = 16 bytes / dtype_bytes`。

- FP16（2 bytes）→ x = 8
- FP8（1 byte）→ x = 16

理由：GPU 的一次向量化載入指令最寬是 16 bytes（`float4`）。把 head_size 這一維切成 `head_size/x` 段、每段 `x` 個元素並放在**最內層**，可以保證每個 thread 一次 `LDG.E.128` 就拿到 16 bytes 連續資料，達成完全合併的記憶體存取（coalesced access）。

具體展開（HEAD_SIZE=128、BLOCK_SIZE=16、x=8）：

```
K cache 形狀 = [num_blocks, num_kv_heads, 16, 16, 8]
                                          ↑   ↑   ↑
                                  head_size/x │   x
                                          block_size

一個 (block, head) 切片的記憶體排列：

            block 內的 token index →
          t0   t1   t2  ...  t15
        ┌────┬────┬────┬────┬────┐
d[0:8]  │····│····│····│····│····│  ← 每格 8 個元素 = 16 bytes = 一次載入
d[8:16] │····│····│····│····│····│
   ⋮    │    │    │    │    │    │
d[120:128]│··│····│····│····│····│
        └────┴────┴────┴────┴────┘
        共 16 列 × 16 行 × 8 = 2048 個元素 = 一個 head 在此 block 的全部 K
```

**為什麼 K 要而 V 不要？** 因為兩者在 attention 裡的存取方向不同：

- **Q·K^T**：需要沿 `head_dim` 做點積 → 同一個 token 的 head_dim 要連續 → 把 head_dim 切段放內層。
- **P·V**：需要沿 `token` 維度做加權和 → 同一個 head_dim 位置的不同 token 要連續 → V 的 `block_size` 自然就在最內層。

一句話：**佈局跟著歸約方向走**。這是所有高效能 attention kernel 的共同設計原則。

### 4.2 執行緒的分工

```
一個 CUDA thread block 處理：一個 (sequence, head) 對
  ├─ NUM_WARPS 個 warp（例如 4 個，NUM_THREADS=128）
  │    └─ 每個 warp 處理「一個 query token × 一整個 KV block」
  │         └─ warp 內分成若干 thread group（THREAD_GROUP_SIZE = 2~4）
  │              └─ 每個 thread group 負責一個 key token
  │
  └─ 6 個 block 分給 4 個 warp：warp0→block 0,4；warp1→block 1,5；…
```

關鍵公式：

```
VEC_SIZE          = 16 bytes / sizeof(scalar_t) / THREAD_GROUP_SIZE
qk                = scale × dot(q_vec, k_vec)   （thread group 內做跨執行緒歸約）
softmax(x)        = exp(x − max) / Σ exp(x − max)   （warp 內先歸約，再跨 warp）
NUM_ROWS_PER_THREAD = HEAD_SIZE / WARP_SIZE = 128 / 32 = 4
```

最後一行的意思是：累加輸出時，每個 thread 負責 head_dim 上的 4 個位置，`accs[4]` 就是它的暫存器累加器。

### 4.3 為什麼現在多數情況不走這個 kernel

值得說清楚：**上面這個手寫 PagedAttention kernel，在 2026 年的 vLLM 裡已經不是主力路徑。**

現代 attention backend（FlashAttention v2/v3、FlashInfer、Triton 版）都已原生支援 paged KV cache——它們直接吃 block_table，內部自己處理不連續存取，同時保有 FlashAttention 的 online softmax 與 tiling 優勢。vLLM 會依 GPU 架構、head_dim、dtype 自動選擇 backend（`VLLM_ATTENTION_BACKEND` 可覆寫）。

那為什麼還要理解舊 kernel？因為**它是唯一一份把「分頁如何影響記憶體存取模式」講清楚的參考實作**。理解了它，你才會知道為什麼 `block_size` 不能亂設、為什麼某些 head_dim 沒有最佳化路徑、以及為什麼換 dtype 會連帶影響 kernel 選擇。Part 4 會回到 backend 選擇這題。

---

## 五、Copy-on-Write：共享的正確做法

平行取樣（`n=4`）和 beam search 會從同一個 prompt 分岔出多條序列。分岔點之前的 KV **完全相同**。

```
時間 →

  prompt（40 token，3 個 block）
  ┌────┬────┬────┐
  │ b7 │ b3 │b12 │   ref_cnt: b7=1, b3=1, b12=1
  └────┴────┴────┘
         │
         │  n=4 分岔
         ├─────────┬─────────┬─────────┐
         ▼         ▼         ▼         ▼
      seq0      seq1      seq2      seq3
   [7,3,12]  [7,3,12]  [7,3,12]  [7,3,12]   ← 4 條共用同 3 個 block
                                              ref_cnt: b7=4, b3=4, b12=4
                                              記憶體用量：1 份，不是 4 份
         │
         │  各自生成 token，b12 只有 8/16 格是滿的 → 要寫入
         ▼
   seq0 想寫 b12 的第 9 格，但 ref_cnt(b12)=4 > 1
   → 觸發 COW：
       1. 配一個新 block b20
       2. 把 b12 的內容複製過去
       3. seq0 的 block_table 改成 [7, 3, 20]
       4. b12.ref_cnt-- → 3
   b7 和 b3 是滿的且永遠不會再被寫，繼續共享到序列結束
```

**效果**：vLLM 論文量測平行取樣與 beam search 場景，**記憶體開銷最多降 55%，吞吐最多提升 2.2×**。

**現代的注意事項**：V1 移除了 `best_of`，beam search 也從引擎核心移到上層（`vllm/beam_search.py`，以多次 `generate` 呼叫實作）。COW 機制本身仍在，主要服務於 `n>1` 的平行取樣與前綴共享。如果你的舊程式碼依賴引擎內建 beam search，遷移時要注意這個變化。

---

## 六、Automatic Prefix Caching：hash 鏈與 LRU

這是 vLLM V1 預設開啟、且對真實 workload 收益最大的一個功能。

### 6.1 block hash：為什麼要串成鏈

一個直覺但**錯誤**的作法：拿 block 內 16 個 token 的內容算 hash。

錯在哪？因為 `[the, cat, sat]` 出現在文件開頭和出現在第 500 個 token，**它們的 K/V 值完全不同**——attention 的 K/V 依賴前面所有 token。所以 hash 必須把「路徑」也編進去：

```
block_hash[i] = H( block_hash[i-1] , token_ids[i×16 : (i+1)×16] , extra_keys )
                        ↑ parent hash                                 ↑
                   把整條前綴路徑摺疊進來              LoRA id / 多模態 hash / cache_salt

範例：兩個請求
  R1: "You are a helpful assistant. ... 請問 A?"
  R2: "You are a helpful assistant. ... 請問 B?"

  block 0: [You are a helpful assistant...]  → hash h0     ✓ 兩者相同
  block 1: [...繼續 system prompt...]        → H(h0, ...) = h1  ✓ 相同
  block 2: [...system prompt 結尾 + 請問 A?] → H(h1, tokA) ≠ H(h1, tokB)  ✗ 分岔

  → R2 命中 block 0、1，只需 prefill block 2
```

**`extra_keys` 為什麼必要**：同樣的文字 token，掛不同 LoRA adapter 算出來的 K/V 不同；多模態請求裡 `<image>` 這個 placeholder token 對應的是完全不同的圖片。漏掉這些，你會拿到別人的答案。`cache_salt` 則是給多租戶場景的隔離手段——把 tenant id 混進去，就算兩個租戶送了一模一樣的 prompt 也不會互相命中（這是一個真實的側通道風險）。

**hash 演算法**：從 0.11 起預設 `sha256`。官方文件明說更早的預設「不保證無碰撞」。可選 `sha256_cbor`（跨版本可重現）、`xxhash`/`xxhash_cbor`（快得多，但碰撞機率高）。

```
選擇             理由                          代價
──────────────────────────────────────────────────────────────
sha256（預設）   密碼學強度，碰撞機率可忽略     每 block 約幾 µs CPU
xxhash           快 5–10×                      非密碼學 hash，理論上可被構造碰撞
sha256_cbor      序列化穩定，跨 Python 版本一致 比 sha256 再慢一些

翻轉條件：只有在 profiling 明確顯示 hash 是 CPU 瓶頸（極短 prompt、超高 QPS、
單機多 DP rank）時才換 xxhash，且僅限單租戶、可信輸入的環境。
```

### 6.2 四個資料結構

```
① BlockPool          list[KVCacheBlock]，啟動時一次配好，執行期不再 new
                     （避免 Python 物件配置出現在熱路徑上）

② FreeBlockQueue     雙向鏈結串列，維持 LRU 序
                     頭部 = 最久沒被用到 → 下一個被淘汰
                     尾部 = 剛剛被釋放
                     O(1) 從中間摘除（命中時），O(1) 從頭部取、尾部插

③ cached_block_hash_to_block    dict[BlockHash, dict[block_id, KVCacheBlock]]
                                前綴查表用

④ req_to_blocks     dict[request_id, list[KVCacheBlock]]
                    就是每個請求的 block_table
```

**為什麼 free queue 要用鏈結串列而不是 heap 或 deque？** 因為兩種操作都要 O(1)：
- 淘汰：從頭部取 → deque 也行
- **命中**：一個躺在 queue 中間的 cached block 被復用，要從「中間」摘除 → 只有雙向鏈結串列能 O(1) 做到

### 6.3 配置與淘汰的完整流程

```
【新請求 allocate_slots】
  1. 逐 block 算 hash（只算「已滿」的 block；未滿的不算，因為內容還會變）
  2. 查 cached_block_hash_to_block
     ├─ 命中：ref_cnt++ ；若 ref_cnt 從 0 變 1，從 free queue 中間摘除
     └─ 未命中：停止比對（前綴是連續的，一斷就全斷）
  3. 剩餘需要的 block 從 free queue 頭部取
     ├─ 若取到的 block 帶著 hash（= 別人的快取）
     │    → 從 cached_block_hash_to_block 移除該項、清空 block_hash  【淘汰發生】
     └─ ref_cnt = 1
  4. 之後每當某個 block 被寫滿 16 個 token
     → 算 hash、寫進 cached_block_hash_to_block  【自動快取】

【請求結束 free】
  1. 反序走訪它的 block（尾→頭）
  2. ref_cnt--
  3. ref_cnt 歸 0 者，接到 free queue 尾端
     ※ 內容不清空、hash 不移除 → 留給未來的前綴命中
```

第 2 步的「一斷就全斷」值得強調：**前綴快取只在前綴上生效**。中間插一個字，後面全部要重算。這對 prompt 設計有直接指導意義：

```
❌ 錯誤：把變動的東西放前面
   "現在時間是 2026-09-11 14:32:07。你是一個助理，規則如下：<3000 token 規則>...{使用者問題}"
   → 每秒鐘 hash 都不同，命中率 0%

✅ 正確：固定的放前面，變動的放後面
   "你是一個助理，規則如下：<3000 token 規則>...現在時間是 2026-09-11。{使用者問題}"
   → 3000 token 的規則段永遠命中
```

第 3 步的「反序走訪」也不是隨便寫的：從尾巴開始放回 free queue，可以讓**越靠近 prompt 開頭的 block 越晚被淘汰**——而開頭正是最可能被別人共用的部分。這是一個很小但很聰明的細節。

### 6.4 怎麼知道它在work

看兩個指標的比值：

```promql
rate(vllm:prefix_cache_hits[5m]) / rate(vllm:prefix_cache_queries[5m])
```

| 命中率 | 判讀 | 該做什麼 |
|---|---|---|
| > 0.7 | 健康，多輪對話 / 固定 system prompt 場景的正常值 | 沒事 |
| 0.3–0.7 | 普通，可能有部分變動內容擋在前面 | 檢查 prompt 模板順序 |
| < 0.1 且 workload 明明有共同前綴 | 有問題 | 檢查：多副本路由是否隨機？KV 池是否太小導致快取一直被淘汰？prompt 前面有沒有時間戳/uuid？ |
| < 0.1 且 workload 本來就沒共同前綴 | 正常 | 前綴快取幫不上忙，別浪費時間調它 |

V1 也提供了 block 生命週期的指標（`vllm:kv_block_lifetime_seconds`、`vllm:kv_block_idle_before_evict_seconds`、`vllm:kv_block_reuse_gap_seconds`）。**`reuse_gap` 的 P90 大於 `idle_before_evict` 的 P50，就是「KV 池太小」的鐵證**——block 平均在被重用之前就被淘汰了。這時加 KV 池（提高 `gpu_memory_utilization`、降 `max_model_len`、開 FP8 KV）會有立即效果。

---

## 七、KV Cache 量化：把記憶體再砍一半

KV cache 佔用可以直接用低精度儲存：

```bash
vllm serve <model> --kv-cache-dtype fp8
```

| dtype | 每 token（8B 模型） | 相對 FP16 | 品質影響 |
|---|---|---|---|
| `auto`（FP16/BF16） | 128 KB | 100% | 基準 |
| `fp8`（E4M3） | 64 KB | 50% | 多數任務可忽略；長 context 的精確召回略降 |
| `fp8_e5m2` | 64 KB | 50% | 動態範圍大、精度低，一般不如 E4M3 |

**50% 的 KV 記憶體 = 2× 的併發上限**。以 Part 1 的算式，48 GB 池從 393K token 變成 786K token，8192 context 下併發從 48 條變 96 條。

代價與注意事項：

1. **品質**：FP8 E4M3 有 3 個尾數位。對大多數生成任務影響落在噪聲範圍內；但對「從 100K context 中精確找出某個數字」這類 needle-in-haystack 任務，實測會有可量測的退化。**上線前用你自己的評測集比一次**，不要憑感覺。
2. **硬體**：FP8 KV 需要 Ada（L40S/4090）或 Hopper（H100/H200）以上；Ampere（A100）沒有原生 FP8，走軟體轉換會賠掉部分收益。
3. **前綴快取相容**：兩者可以同時開。
4. **kernel 支援**：不是所有 attention backend 都支援 FP8 KV，啟動時注意有沒有 fallback 警告。

```
選擇            選 FP8 KV 的理由                不選的理由 / 何時該用 FP16
──────────────────────────────────────────────────────────────────────
fp8 KV          記憶體減半 → 併發加倍            Ampere 及更舊：無原生支援
vs fp16 KV      長 context 場景收益最大          高精度召回任務：可量測的品質損失
                Hopper/Ada 上幾乎零額外成本      評測集沒跑過：別在生產環境賭

翻轉條件：你的 `Maximum concurrency` 已經 > 100，記憶體不是瓶頸 → 沒必要開，
留著 FP16 的品質餘裕。反之若併發 < 20，開 FP8 是最便宜的一倍提升。
```

---

## 八、記憶體規劃手冊：從硬體反推服務能力

把前面全部串起來，變成一份可以直接套的流程。

### 8.1 啟動日誌該看哪三行

```
# 1. 權重佔用
INFO ... Model loading took 15.2 GiB and 8.34 seconds

# 2. KV 池大小 ← 最重要的一行
INFO ... GPU KV cache size: 393,216 tokens

# 3. 併發倍率 ← 第二重要
INFO ... Maximum concurrency for 8,192 tokens per request: 48.00x
```

第三行的意思是：**在每個請求用滿 `max_model_len` 的最壞情況下，你能同時服務 48 個請求。** 這是最壞情況估計，實際併發通常更高（多數請求用不到 max_model_len），但它是你做容量規劃的安全下限。

### 8.2 決策流程

```
                    ┌──────────────────────────┐
                    │ 讀啟動日誌的 concurrency │
                    └───────────┬──────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
      concurrency < 10    10 ≤ x < 50          x ≥ 50
            │                   │                   │
            ▼                   ▼                   ▼
    ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐
    │ 記憶體嚴重不足 │  │ 尚可，但流量尖峰 │  │ 記憶體充足        │
    │ 依序嘗試：     │  │ 會觸發搶佔      │  │ 瓶頸在別處：      │
    │ 1 開 fp8 KV   │  │ 1 開 fp8 KV     │  │ 檢查 CPU 核心數、 │
    │ 2 降 max_len  │  │ 2 提高 gpu-util │  │ tokenize 開銷、   │
    │ 3 權重量化    │  │   到 0.93–0.95  │  │ max_num_batched_  │
    │   FP8/AWQ     │  │ 3 觀察搶佔指標   │  │ tokens 是否太小   │
    │ 4 加 TP       │  └────────────────┘  └──────────────────┘
    │ 5 換 GQA 模型 │
    └───────────────┘
```

### 8.3 三個真實配置

**(a) 8B 模型、單張 L40S 48 GB、聊天機器人（平均 1.5K token）**

```bash
vllm serve Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.92
```
權重 16 GB + 開銷 6 GB → KV 池約 22 GB → 約 172K token → 8192 下併發 21×，1.5K 平均下實際併發 100+。**夠用，不要動它。**

**(b) 70B FP8、4×H100、RAG（平均 20K token prompt）**

```bash
vllm serve <70B-FP8> --tensor-parallel-size 4 --max-model-len 32768 \
  --kv-cache-dtype fp8 --gpu-memory-utilization 0.93 \
  --max-num-batched-tokens 16384
```
權重 70 GB / 4 卡 = 17.5 GB/卡 → 每卡 KV 約 50 GB，總 200 GB。FP8 KV 下每 token 160 KB → 1.3M token → 32K 下併發 40×。RAG 前綴命中率高，實際 TTFT 會遠低於冷啟動值。`max-num-batched-tokens` 拉大是因為 20K 的 prompt 需要吞吐導向的 prefill。

**(c) 32B、2×A100 80G、長文件分析（平均 100K token）**

```bash
vllm serve <32B> --tensor-parallel-size 2 --max-model-len 131072 \
  --gpu-memory-utilization 0.95 --max-num-seqs 16
```
A100 沒有原生 FP8，KV 只能 FP16。權重 64 GB / 2 = 32 GB/卡 → KV 約 40 GB/卡、80 GB 總。每 token 假設 160 KB → 500K token → **131K context 下併發只有 3.8×**。這是典型的「長 context 把併發吃光」場景：把 `max_num_seqs` 明確設成 16 避免排程器過度樂觀，並認知這台機器就是低併發高單價的用途。

---

## 九、為什麼選 X 不選 Y

```
選擇                 選 X 的理由                        不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────────
分頁 KV              浪費 <4%（只剩尾端 block）          連續配置：浪費 60–80%，
vs 連續配置          支援 COW 共享與前綴快取             但 kernel 簡單、無間接層
                     ────────────────────────────────────────────────────────
                     翻轉條件：單一使用者、固定長度、極致低延遲的嵌入式場景，
                     連續配置省掉 block_table 查表的那幾微秒可能還有意義。
                     服務化場景沒有任何理由選連續配置。

block_size = 16      kernel 效率與碎片的平衡點           8：命中率高但索引開銷大
vs 8 / 64 / 128      多數 backend 的最佳支援             128：碎片大、前綴粒度粗
                     ────────────────────────────────────────────────────────
                     翻轉條件：128K+ 超長 context 且前綴不重複 → 試 32；
                     大量短前綴變體且命中率是主要收益 → 試 8。先量測再改。

sha256 hash          碰撞機率可忽略，多租戶安全          xxhash：快 5–10× 但
vs xxhash            正確性優先                          非密碼學強度
                     ────────────────────────────────────────────────────────
                     翻轉條件：profiling 顯示 hash 佔用可觀 CPU（極短 prompt +
                     超高 QPS），且環境單租戶可信。

Recompute 搶佔       實作簡單、無 PCIe 傳輸              Swap 到 CPU：省算力但
vs Swap 到 CPU       V1 已移除 swap                     PCIe 頻寬成新瓶頸，
                     GPU 算力通常比 PCIe 便宜            且引入複雜的換頁狀態機
                     ────────────────────────────────────────────────────────
                     翻轉條件：prompt 極長（100K+）且重算成本遠高於傳輸成本時，
                     swap 理論上更划算——但 V1 選擇用 KV offloading connector
                     這個更通用的機制來覆蓋這個場景，而不是回頭做 swap。

前綴快取預設開       絕大多數 workload 有共同前綴        關閉：省下 hash 的 CPU
vs 預設關            未命中時成本僅是 hash 計算          與 block 記帳開銷
                     ────────────────────────────────────────────────────────
                     翻轉條件：你的請求前綴完全隨機（例如純粹的 embedding 批次），
                     `--no-enable-prefix-caching` 可省下每 block 幾微秒。收益極小。

fp8 KV cache         記憶體減半，併發加倍                fp16：品質無損
vs fp16 KV           Hopper/Ada 上幾乎無額外成本         Ampere 無原生支援
                     ────────────────────────────────────────────────────────
                     翻轉條件：見第七節。核心判準是「你的 concurrency 是不是瓶頸」。

GPU-only KV          存取延遲 µs 級，無外部依賴          多層卸載：DRAM/SSD 可放
vs 多層卸載          架構簡單                            10–100× 的熱前綴，命中
（LMCache 等）                                            DRAM 仍比重算 prefill 快
                     ────────────────────────────────────────────────────────
                     翻轉條件：前綴重用率高、prompt 長（RAG / 程式碼庫 / 長對話），
                     且 `kv_block_reuse_gap` 顯示 block 常在重用前被淘汰。
                     此時多層卸載是比加 GPU 便宜一個量級的解法。
```

---

## 十、系列導航

本篇把 Part 1 的「記憶體就是吞吐量」拆成了機制：**分頁**解決碎片、**COW** 解決同一請求內的共享、**hash 鏈 + LRU** 解決跨請求的共享、**FP8 與多層卸載**把池子再撐大。

記憶體現在管好了。但記憶體只是配額——**誰能拿到配額、什麼時候拿、拿多少，是排程器的事**。

下一篇是整個系列離「效能調參」最近的一篇：連續批次到底怎麼運作、V1 那個統一 token 預算排程器為什麼比 V0 的雙軌制乾淨、chunked prefill 這個旋鈕如何在 TTFT 與 ITL 之間權衡、記憶體不足時誰會被搶佔、以及投機解碼在什麼負載下是賺的、什麼負載下是賠的。

- **Part 3 — 連續批次與排程器**：統一 token 預算、Chunked Prefill、搶佔、投機解碼與調參手冊

← [Part 1 — 全景架構 — 從一次 model.generate() 到一個推論引擎](../vllm-intro-part1-architecture-overview-zh) | [Part 3 — 連續批次與排程器 — 決定誰在這一輪前進一格 →](../vllm-intro-part3-scheduler-continuous-batching-zh)

---

*本文基於 vLLM `main` 分支（2026 年 9 月，版本參考 0.19.x）、官方 PagedAttention 與 Prefix Caching 設計文件、以及 SOSP 2023 論文撰寫。資料結構與欄位名稱對照 `vllm/v1/core/` 原始碼；記憶體與延遲數字為量級估算。*
