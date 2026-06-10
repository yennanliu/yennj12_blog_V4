---
title: "FDE core topic - Context Cache Eviction：硬體級上下文快取驅逐策略與計費陷阱"
date: 2026-06-08T10:00:00+08:00
draft: false
weight: 17
description: "深入解析 Vertex AI Context Caching 的 KV 快取原理、三層驅逐架構設計，以及如何避免每小時 $4.50 的隱性計費陷阱。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topic", "Cloud", "VertexAI", "Caching", "CostOptimization"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：Vertex AI Context Caching 將大型 prompt prefix 的 KV activations 固定在 TPU 記憶體，後續呼叫跳過 prefill 階段，token 成本降至 1/4——但按小時計費的機制讓閒置快取成為最隱蔽的成本炸彈，正確的驅逐策略是區分工程師與初學者的分水嶺。**

---

## 一、為什麼面試官問這個

LLM 系統的推論成本往往由「重複處理相同 prefix」所主導。面試官問 Context Cache Eviction，真正在測三件事：

- **成本意識**：你是否理解 Vertex AI 計費模型的按小時收費邏輯，以及如何在活躍用戶與閒置用戶之間動態調配快取資源。不懂計費細節的候選人，設計出的系統往往在上線後讓帳單暴增 3-5 倍。
- **架構判斷力**：你能否設計出跨越 L1/L2/L3 三層的快取驅逐策略，而不只是「開快取就好」這種淺層答案。強候選人能說清楚每層的觸發條件、成本邊界、以及在什麼情況下應該主動驅逐而不是等 TTL 過期。
- **數字感**：1M token context 每小時值多少錢？32K token 閾值的意義是什麼？Break-even 點在哪裡？面試官期待聽到具體數字，不是模糊的「可以節省很多」。

**弱答案長這樣：**
「我會用 Vertex AI Context Cache 減少 token 費用，設定 TTL 讓它自動過期就好。」這個答案暴露了兩個問題：不知道 TTL 最長 24 小時（閒置快取繼續燒錢），也不知道應該主動驅逐而非被動等待。

**強答案長這樣：**
「Context Cache 按小時計費，閒置用戶繼續計費是主要陷阱。我會用 Redis sliding window 判斷活躍度——超過 32K token 且每 10 分鐘 >5 次請求才升級到 L2 快取；閒置 15 分鐘後，觸發 Gemini Flash 非同步壓縮，把 1M token 壓縮到 1K 存入 Firestore，再呼叫 `CachedContent.delete()` 主動釋放 L2，避免 $4.50/hr 的浪費。」

---

## 二、核心原理與技術深度

### 2.1 Transformer Prefill 的物理成本

Transformer 模型處理 token 序列分為兩個階段：

1. **Prefill（前置計算）**：將輸入 token 序列全部轉換為 Key-Value（KV）矩陣，計算每個 token 對其他所有 token 的 attention。時間複雜度 O(n²)，n 為 token 數量。1M token 的 prefill 在 TPU v5e 上約需 6-10 秒。
2. **Decode（解碼生成）**：逐 token 生成輸出，每步只需處理當前 token 對已有 KV cache 的 attention。時間複雜度 O(n)，速度快得多。

對於固定的系統 prompt（工具 schema、文件上下文、角色定義），**每次呼叫都重做 prefill 是純粹的浪費**。Vertex AI Context Caching 的本質是把這份「計算結果」（KV activations）快取在 TPU 的 HBM（High Bandwidth Memory）中，後續呼叫直接跳過 prefill，讀取已計算好的 KV 矩陣。

```
無快取呼叫流程：

 用戶請求
    │
    ▼
┌───────────────────────────────────────────────┐
│  Prefill 階段（1M tokens）                     │
│  ┌─────────────────────────────────────────┐  │
│  │ token[0] → token[1] → ... → token[1M]  │  │  耗時：~8 秒
│  │ 計算每個 token 的 K、V 矩陣              │  │  費用：$1.25（input tokens）
│  └─────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐   │
│  │  New Query（200 tokens）               │   │
│  └────────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
    │
    ▼
 生成回應（Decode 階段）


快取命中流程：

 用戶請求 + cache_id
    │
    ▼
┌───────────────────────────────────────────────┐
│  TPU HBM KV Store                             │
│  ┌─────────────────────────────────────────┐  │
│  │ 讀取 Cached KV activations（1M tokens）  │  │  耗時：~0.3 秒
│  │ 無需重算，直接載入                        │  │  費用：$0.3125（cached tokens）
│  └─────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐   │
│  │  New Query（200 tokens）               │   │
│  └────────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
    │
    ▼
 生成回應（Decode 階段）
```

### 2.2 計費模型詳解

Vertex AI Context Cache 的計費有**三個計量維度**，必須同時理解：

| 計費項目 | 單價（Gemini 1.5 Pro） | 說明 |
|---------|----------------------|------|
| 標準 input token | $1.25 / 1M tokens | 每次呼叫的非快取部分 |
| cached input token | $0.3125 / 1M tokens | 快取命中的 prefix 部分（節省 75%） |
| 快取儲存費 | $4.50 / 1M tokens / hr | **無論是否有呼叫都計費** |
| output token | $5.00 / 1M tokens | 不受快取影響 |

**關鍵計算：Break-even 頻率**

假設系統 prompt 為 1M tokens：
- 每次呼叫節省 = $1.25 - $0.3125 = **$0.9375 / 呼叫**
- 每小時儲存成本 = **$4.50**
- Break-even = 4.50 / 0.9375 ≈ **每小時 4.8 次呼叫**

低於 4.8 次/小時，開快取反而更貴。這個數字對低活躍用戶（例如睡眠中的用戶）來說輕易就會破功。

### 2.3 32K Token 最小閾值的由來

Vertex AI 要求 Context Cache prefix 至少達到 **32,768 tokens**。這個限制來自 TPU 記憶體管理的頁面對齊（page alignment）設計——TPU HBM 以 32K token 為基本分配單位。小於此閾值時，管理 KV store 的 metadata、lookup table、eviction scheduler 所帶來的開銷，超過了省下的 prefill 計算量，平台直接拒絕。

```
token 數量 vs. 快取效益（概念圖）：

 淨效益
    ▲
    │                               ╔══════════════════════╗
    │                         ╱     ║   快取有效區域         ║
    │                        ╱      ║   淨效益為正           ║
    │                       ╱       ╚══════════════════════╝
  0 ├──────────────────────────────────────────────────────▶
    │◄─────────────────────►│              token 數量
    │    管理開銷 > 節省      32K
    │    Vertex AI 不受理
    │
    ▼  損失
```

在實作端，需要在呼叫 API 之前自行做 token 計數（可用 `google.generativeai.count_tokens()` 或 Tiktoken 近似值），確認超過 32K 門檻後才建立快取。Token 計數本身的延遲約 50-100ms，但這個成本一次性發生在「是否升級至 L2」的決策點，遠小於因錯誤建立快取而浪費的儲存費。

**32K 閾值的邊界效應**：若系統 prompt 長期維持在 30-35K token 之間（例如動態注入工具 schema 導致長度浮動），應設定一個保守的觸發閾值（例如 36K），避免在閾值附近反覆建立和刪除快取（每次建刪都有 API overhead 和最少 1 分鐘的費用）。

### 2.4 快取生命週期與驅逐 API

每個 `CachedContent` 物件有：

- **`name`**：格式為 `cachedContents/{id}`，是後續操作的唯一識別符
- **`expire_time`**：可在建立時指定，最長 24 小時，預設 1 小時
- **`update_time`** / **`create_time`**：用於計費審計

主動驅逐的正確方式：

```python
# 主動釋放，停止計費
from google.cloud import aiplatform

client = aiplatform.gapic.GenAiCacheServiceClient(...)
client.delete_cached_content(name=cache_id)
# 呼叫後立即停止計費，不等 expire_time
```

這是與「設定短 TTL」最大的區別：短 TTL 只是讓快取「較快」過期，但在過期之前的每分鐘仍在計費。`CachedContent.delete()` 是即時停止，是成本控制的正確工具。

### 2.5 快取一致性問題

Context Cache 有一個關鍵限制：**快取建立後 prefix 不可修改**。若系統 prompt 版本更新（例如工具 schema 新增一個 function、文件內容更新），必須：

1. 建立新的 `CachedContent`（新版 prefix → 新的 `cache_id`）
2. 呼叫 `CachedContent.delete()` 刪除舊快取
3. 更新所有 session 的 `cache_id` 指向新版本

在工程實作上，`cache_id` 應帶版本資訊：

```
cache_id = f"cc_{uid}_{session_id}_{prefix_hash[:8]}"
```

其中 `prefix_hash` 是系統 prompt 內容的 SHA-256 前 8 位。任何 prompt 變更都會產生新 hash，觸發自動重新建立快取。這個設計避免了舊快取與新 prompt 版本混用的一致性問題，代價是版本切換期間有一次完整 prefill 費用。

```
Prompt 版本更新流程：

  v1 prefix ──▶ cache_id_v1 (CachedContent)
                     │
  prompt 更新        │ CachedContent.delete(cache_id_v1)
                     │ → 立即停止 v1 計費
                     ▼
  v2 prefix ──▶ CachedContent.create()
                     │
                     ▼
               cache_id_v2 (新快取)
               → 下次呼叫命中 v2
```

### 2.6 觀測性：成本追蹤不可少

上線後必須監控三個指標，否則帳單暴增時無從找起：

| 指標 | 意義 | 警報門檻 |
|------|------|---------|
| `cached_input_tokens / input_tokens` | 快取命中率；應 > 80% 才值得 | < 50% 連續 10 分鐘 → 快取失效 |
| `active_cache_count` | 當前存活的 CachedContent 數量 | > 預期活躍 session 數 × 1.2 → 洩漏 |
| `cache_storage_cost_hourly` | 每小時儲存費，對應 active_cache_count × 4.50 | 偏差 > 20% → 閒置快取未被驅逐 |

這三個指標應寫入 Cloud Monitoring，設定 PagerDuty 告警。`cache_storage_cost_hourly` 超標是最強的「主動驅逐邏輯失效」信號——成本可以自動告警，比等月帳單下來再救火有效得多。

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**做什麼：** 只用 Redis 儲存最近 3 輪對話的純文字，每次呼叫傳完整 system prompt 加上近期對話給 Vertex AI，不使用 Context Cache。

```
用戶請求
    │
    ▼
┌─────────────────────────────┐
│  Redis（session store）      │
│  key: session:{uid}         │  TTL: 30 min
│  value: last 3 turns (text) │  延遲: < 1 ms
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  組裝完整 prompt             │
│  system_prompt (1M tokens)  │
│  + recent_turns (< 1K)      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Vertex AI Gemini API       │  每次完整 prefill
│  input: 1M + 1K tokens      │  費用: ~$1.25 / 次呼叫
│  無 cache_id                │  延遲: 8-10 秒（prefill）
└─────────────────────────────┘
```

**解決什麼問題：** 無狀態、快速可運行的基線實作。Redis 讀取 < 1ms，近期對話有連續性，無任何第三方依賴。工程師 2 小時內可完成，適合早期驗證產品假設。

**代價與侷限：** 每次呼叫都支付完整 1M token prefill 費用。100 次/天 = $125/天 input token 費用。長對話歷史超過 3 輪後截斷，用戶感受到失憶。流量增長後成本線性上升，沒有任何槓桿效果。

**適合場景：** 日活躍用戶 < 1,000、預算敏感的早期原型、系統 prompt < 32K token 的輕量應用。當系統 prompt 因業務擴展超過 32K token 時，應立即評估升級到 Layer 2。

**升級觸發條件：** 監控 `input_token_cost_daily` 超過 $500，或日活躍用戶突破 1,000，任一條件成立即可優先排期 Layer 2 遷移。

---

### Layer 2 — 生產就緒（Production-Ready）

**做什麼：** 在 L1 基礎上加入 Vertex AI Context Cache，但用 Redis sliding window 計數器判斷活躍度，只有符合條件的用戶才建立 L2 快取，避免為閒置用戶付費。

**觸發條件（兩者同時滿足）：**
- 條件 A：累計對話 token 數 > 32,768（確保達到 Vertex AI 最小閾值）
- 條件 B：Redis 活躍度計數器 > 5 req / 10 min（確保 break-even 頻率）

```
用戶請求
    │
    ▼
┌───────────────────────────────────────────────────────┐
│  活躍度判斷層（Redis）                                  │
│                                                       │
│  INCR sliding_window:{uid}                            │
│  EXPIRE sliding_window:{uid} 600   # 10 分鐘視窗      │
│                                                       │
│  total_tokens = count_tokens(system_prompt + history) │
│                                                       │
│  if total_tokens > 32768 AND req_count > 5:           │
│      → 進入 L2 快取路徑                               │
│  else:                                                │
│      → L1 直連路徑（不建立快取）                      │
└──────────────────────┬────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼ L2 路徑                  ▼ L1 路徑
┌──────────────────┐     ┌────────────────────────┐
│  檢查 cache_id   │     │  組裝完整 prompt         │
│  是否已存在       │     │  直接呼叫 Vertex AI      │
│  （Redis 查找）   │     │  費用：$1.25 / 次         │
└────────┬─────────┘     └────────────────────────┘
         │
    ┌────┴────┐
    │存在      │不存在
    ▼          ▼
命中快取    建立新快取
$0.3125/M  CachedContent.create()
           儲存 cache_id 到 Redis
           費用開始計算：$4.50/hr
```

**解決什麼問題：** 活躍用戶每次呼叫節省 $0.9375（1M token prefix），系統整體 input token 費用下降 60-70%。閒置用戶不建立 L2 快取，避免無謂的儲存費用。

**遺留問題：** 用戶突然離開（關掉 app、睡覺），已建立的 L2 快取繼續計費直到 TTL 到期（最長 24 小時）。對有 1,000 個活躍 session、每個 session 都有 1M token 快取的系統，一夜的閒置成本可達 1,000 × $4.50 = **$4,500**。

**適合場景：** 日活躍用戶 1,000–50,000、對話平均長度 > 50K token 的應用。

**監控重點：** 部署 Layer 2 後，應在 Cloud Monitoring 設定 `active_cache_count` 儀表板。若 `active_cache_count` 在業務低峰期（例如凌晨 2-5 點）仍維持在 session 數的 80% 以上，代表閒置快取未被清除，月帳單將持續超支——這是升級到 Layer 3 的強烈信號。

---

### Layer 3 — 企業級（Enterprise-Grade）

**做什麼：** 加入閒置偵測（15 分鐘觸發）、Gemini Flash 非同步壓縮、主動驅逐（`CachedContent.delete()`）、Firestore 永久快照，構成完整的快取生命週期管理。

```
┌──────────────────────────────────────────────────────────────────┐
│                    完整三層快取生命週期                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  L1: Redis                                                  │ │
│  │  ┌──────────────────┐                                       │ │
│  │  │  last 3 turns    │  TTL: 30 min  延遲: <1ms  成本: ~$0  │ │
│  │  │  session:{uid}   │                                       │ │
│  │  └────────┬─────────┘                                       │ │
│  └───────────┼─────────────────────────────────────────────────┘ │
│              │ 活躍 & token > 32K                                 │
│  ┌───────────┼─────────────────────────────────────────────────┐ │
│  │  L2: Vertex AI Context Cache                  ↓             │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │  KV activations（TPU HBM）                            │  │ │
│  │  │  cache_id: hash(uid+session+version)                  │  │ │
│  │  │  延遲: 0.3s（vs 8s prefill）                           │  │ │
│  │  │  成本: $4.50/hr（無論呼叫與否）                         │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────┬─────────────────────────────┘ │
│                                  │ 閒置 15 分鐘                   │
│  ┌───────────────────────────────┼─────────────────────────────┐ │
│  │  壓縮與驅逐流程               ↓                              │ │
│  │                                                              │ │
│  │  [Cloud Tasks / Pub/Sub]                                     │ │
│  │       │                                                      │ │
│  │       ▼                                                      │ │
│  │  Gemini Flash 壓縮 Job（非同步）                              │ │
│  │  ┌────────────────────────────────────────────────────┐     │ │
│  │  │  輸入：完整對話歷史（1M tokens）                     │     │ │
│  │  │  輸出：核心記憶摘要（< 1K tokens）                   │     │ │
│  │  │  壓縮率：1000x                                      │     │ │
│  │  │  成本：~$0.001 per job（Gemini Flash 費率）          │     │ │
│  │  └──────────────────────┬─────────────────────────────┘     │ │
│  │                         │                                    │ │
│  │          ┌──────────────┴───────────────┐                   │ │
│  │          ▼                              ▼                   │ │
│  │  ┌──────────────┐           CachedContent.delete(cache_id)  │ │
│  │  │  L3: Firestore│           ← 立即停止 $4.50/hr 計費        │ │
│  │  │  snapshot    │                                           │ │
│  │  │  < 1K tokens │  永久保存，無 TPU 成本                    │ │
│  │  │  schema_ver  │  讀取成本：Firestore reads ~$0.0001       │ │
│  │  └──────────────┘                                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

用戶回歸流程（數天後）：
    │
    ▼
檢查 Redis → 未命中（已過期）
    │
    ▼
檢查 Firestore → 載入 core memory snapshot（< 1K tokens）
    │
    ▼
以 snapshot 作為 system prompt prefix → 冷啟動
上下文連續性完整，無需使用者重新說明背景
```

**解決什麼問題：**

| 問題 | L2 的處理方式 | L3 的改進 |
|------|-------------|---------|
| 閒置用戶計費 | 等 TTL 到期（最長 24hr，$108/day per session） | 15 min 後主動驅逐，閒置成本 ≈ $0 |
| 長期記憶遺失 | 快取過期後上下文消失 | Firestore 快照永久保存核心記憶 |
| 壓縮延遲影響用戶 | N/A | 非同步觸發，不阻塞用戶最後一個 response |
| 快照格式升級 | N/A | schema_version 欄位，冷啟動時做版本遷移 |

**成本比較（1,000 個 session，1M token prefix 各）：**

| 場景 | L1 | L2（無驅逐） | L3（有主動驅逐） |
|------|----|-----------|--------------------|
| 活躍時間（8hr/天）input token 省下 | $0 | $7,500/天 | $7,500/天 |
| 閒置時間（16hr/天）儲存費 | $0 | $72,000/天 | **< $100/天** |
| 淨成本（1,000 session/天） | 高 input | 高儲存 | 最優 |

---

## 四、為什麼選 X 不選 Y

每個驅逐策略的設計選擇背後都有具體的取捨理由。以下是面試中最常被追問的決策點：

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | Y 何時反而更好 |
|------|-----------|------------|-------------|
| **主動 delete() vs 短 TTL** | 即時停止計費，閒置 15 min 後零成本 | 短 TTL（如 1hr）仍有最多 60 分鐘浪費，高 session 數時差距巨大 | session 數 < 100、工程複雜度優先於成本時 |
| **Redis sliding window vs 固定計時器** | 精確反映用戶實際活躍度，不因短暫停頓（如思考 2 分鐘）而驅逐 | 固定 15 分鐘計時器從最後一次請求起計，但對低頻用戶過於寬鬆 | 用戶行為極為規律（如排程任務）時固定計時器更簡單 |
| **Gemini Flash 壓縮 vs 截斷歷史** | 保留語義精華，1K token 快照含關鍵事實與用戶偏好 | 截斷歷史（保留最後 N 輪）丟失早期重要背景，用戶會感受到失憶 | 對話無狀態、不需跨 session 記憶的場景直接截斷更簡單 |
| **Firestore vs Cloud SQL 儲存快照** | Serverless、按讀取次數計費、無連線池管理、全球多區域複製 | Cloud SQL 需管理連線池，冷啟動連線延遲 200-500ms，成本固定較高 | 快照需要複雜查詢（如按時間範圍搜索）時 Cloud SQL 更適合 |
| **非同步壓縮 Job vs 同步壓縮** | 用戶最後一次請求不需等壓縮完成，response 延遲不受影響 | 同步壓縮讓最後一次請求的 p99 延遲飆至 30+ 秒，用戶體驗極差 | Job 排程系統複雜度超出團隊能力時，接受同步延遲作為妥協 |
| **L1 Redis vs 直接呼叫 Vertex AI** | < 1ms 讀取最近對話，Vertex AI 呼叫減少（成本和延遲都降低） | 每次都呼叫 Vertex AI 即使是取最近 3 輪對話也需 200-300ms API overhead | Redis 不可用（無 managed Redis 預算）時直接呼叫 Vertex AI |

**關鍵翻轉條件（Flip Condition）**

整個三層架構的前提是「系統 prompt 大且固定」。若系統 prompt < 32K token，或每次呼叫的 prompt 都高度動態（如 RAG 注入不同文件），Context Cache 完全無效——此時應轉向 **Semantic Cache**（Part 4 Hybrid Search 的快取變體），對相似 query 的輸出做快取，而非對 prefix 的 KV activations 做快取。

---

## 五、常見錯誤與陷阱（實際踩坑記錄）

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 對所有用戶無差別開啟 Context Cache | 低活躍用戶貢獻 $4.50/hr 浪費，月帳單超出預算 3-5 倍 | 用 Redis sliding window 確認 >5 req/10min 才觸發 L2 |
| 依賴 TTL 自然過期清除快取 | 快取可能存活最長 24hr，閒置 1,000 session = $108,000/天浪費 | 閒置 15 分鐘後呼叫 `CachedContent.delete()` 主動驅逐 |
| prefix 長度低於 32K token 仍建立快取 | API 返回錯誤（INVALID_ARGUMENT）或靜默失敗，徒增複雜度 | 呼叫端先做 token 計數，低於 32K 走 L1 直連 |
| 壓縮 Job 同步執行在請求路徑上 | 用戶最後一次請求需等待 Gemini Flash 壓縮完成，p99 延遲 > 30 秒 | 壓縮 Job 非同步觸發（Cloud Tasks 或 Pub/Sub），不阻塞 response |
| cache_id 未與用戶 session 隔離 | 不同用戶共享同一快取，造成上下文污染或 GDPR 資料外洩風險 | `cache_id = hash(uid + session_id + prefix_version)` |
| 忽略 cached token 與 new token 的分項計費 | 預算估算偏差 > 75%，成本模型完全失準 | 分開追蹤 `cached_input_tokens` 和 `input_tokens` 兩個 metric，寫入 Cloud Monitoring |
| Firestore 快照未設 schema_version | Prompt 格式升級後，舊快照讀取失敗，冷啟動拋 500 | 快照加入 `schema_version` 欄位，冷啟動時做版本相容性檢查與自動遷移 |

---

## 六、系統效應：加入主動驅逐前後的數字對比

以下為實際部署三層架構前後，系統可觀測指標的典型變化（基準：1,000 個並發 session，1M token 系統 prompt）：

| 指標 | 無快取（Layer 1） | 有快取但無驅逐（Layer 2） | 有主動驅逐（Layer 3） |
|------|----------------|------------------------|-------------------|
| 每次呼叫 input token 成本 | $1.25 / 1M | $0.3125 / 1M（-75%） | $0.3125 / 1M（-75%） |
| prefill 延遲（p50） | ~8 秒 | ~0.3 秒（-96%） | ~0.3 秒（-96%） |
| 閒置期間儲存費（每 24hr） | $0 | $108,000 | **< $1,000** |
| 快取命中率 | N/A | 60-85%（視活躍度） | 75-90%（精確選擇活躍用戶） |
| 壓縮 Job 每次成本 | N/A | N/A | ~$0.001（Gemini Flash） |
| 冷啟動上下文品質 | 完整（但每次重算） | 丟失（快取過期後失憶） | **完整（Firestore 快照）** |

**最關鍵的改善**：Layer 2 → Layer 3 的遷移主要效益不在推論成本（兩者相同），而在於**閒置成本從 $108,000/天 降至 < $1,000/天**，同時用戶跨 session 回歸時保有完整記憶，不需重複說明背景（用戶體驗顯著提升，客服類應用中用戶滿意度可提升 15-25%）。

**工程投入估算**：Layer 1 → Layer 2 需約 2 週工程工時（Redis 活躍度計數器 + CachedContent API 整合）；Layer 2 → Layer 3 需額外 3 週（Cloud Tasks 排程 + Gemini Flash 壓縮 Job + Firestore schema 設計 + 主動驅逐邏輯）。兩段遷移各自 ROI 為正，可分期執行。

---

## 七、與其他核心主題的關聯

- **Part 1 — Context Management**：Context Cache 是 context window 管理的硬體層延伸；L3 Firestore 快照正是 Part 1「長期記憶壓縮策略」的具體實作，把無限增長的對話歷史收斂到 < 1K token 核心記憶。
- **Part 2 — Memory Architecture**：三層快取（Redis L1 / Vertex AI L2 / Firestore L3）直接對應 Part 2 的 Working Memory / Semantic Cache / Cold Storage 三層記憶體架構模型，每層各有不同的延遲、成本、持久性特徵。
- **Part 12 — Backpressure & Fair Share**：Redis sliding window 活躍度判斷（>5 req/10min）與 Part 12 的 token bucket 限流機制可共用同一組 Redis counter，避免重複基礎設施；兩者都以「請求速率」作為資源分配的決策信號。
- **Part 13 — Idempotency & State Recovery**：Gemini Flash 壓縮 Job 必須設計為冪等操作（同一 session 多次觸發，結果相同、不重複寫入 Firestore），對應 Part 13 的非同步 Job 冪等設計原則；`CachedContent.delete()` 呼叫失敗時需要 retry with idempotency key。同樣地，若壓縮 Job 在寫入 Firestore 之前崩潰，下次重試應能安全地重新執行整個流程——這是 Part 13 介紹的「at-least-once + idempotent operation」組合在本主題中的直接應用。

---

## 八、面試一句話（Killer Phrase）

> *「Vertex AI Context Cache 把 1M token prefix 的 KV activations 固定在 TPU HBM，讓後續呼叫跳過 prefill，token 成本從 $1.25 降到 $0.3125 per 1M——但它按小時收 $4.50 儲存費，閒置用戶的快取每小時無聲燒錢，這是最常見的成本失控點。我的設計是三層架構：L1 Redis 存最近三輪對話（延遲 < 1ms、成本近零），L2 Vertex AI Context Cache 只在對話超過 32K token 且 Redis 活躍度計數器確認 >5 req/10min 時才啟動（精確控制 break-even），L3 閒置 15 分鐘後觸發 Gemini Flash 非同步壓縮 Job 把 1M token 壓縮到 1K token 的核心快照寫入 Firestore，同時呼叫 `CachedContent.delete()` 主動釋放 L2——這樣閒置成本歸零，用戶回歸時從 Firestore 冷啟動仍保有完整上下文，在成本與用戶體驗之間找到最佳均衡。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-16-zh/) | [後一篇](/posts/fde-interview-core-topic-18-zh/) →
