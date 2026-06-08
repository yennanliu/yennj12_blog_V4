---
title: "Vector Drift & Blue-Green Indexing：向量圖結構健康度與零停機切換"
date: 2026-06-08T10:00:00+08:00
draft: false
description: "深入解析 HNSW 向量圖在持續增量更新下的 recall 衰退機制，以及 Lambda 架構 + Blue-Green 切換如何在不停機的前提下將 recall@10 恢復至 94% 以上。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "fde-core-topics", "Cloud", "VectorDB", "RAG", "DataPipeline"]
authors: ["yen"]
readTime: "18 min"
---

**核心定義：向量索引的「健康度」不等於資料存在，而是指 HNSW 圖的連結品質——增量插入累積後圖結構失衡，recall 靜默下滑；Blue-Green 重建搭配 Lambda 雙索引架構，是兼顧零停機與高精度的唯一根治手段。**

---

## 一、為什麼面試官問這個

RAG 系統上線後，工程師最容易忽略的問題不是「向量有沒有進去」，而是「向量索引精度是否隨時間穩定」。向量資料庫不像關聯式資料庫——寫入成功不等於查詢品質維持。面試官問這個，實際在測試三個層次的判斷力：

- **你是否理解 ANN 索引的內部結構**：HNSW 不是 B-Tree，插入操作不做全域重平衡，因此 recall 會隨增量操作靜默衰退。候選人若只知道「向量存進去就能查」，代表從未在生產規模下操作過 RAG。
- **你是否能設計「寫入友好 + 讀取高精度」的分層架構**：Lambda 架構在向量場景的應用屬於進階知識。弱答案只說「定期重建索引」卻無法說明如何做到零停機；強答案會畫出 Base + Delta 雙索引，並描述夜間管線的每一個驗證步驟。
- **你是否有刪除場景的務實方案**：向量資料庫普遍不支援就地刪除後的圖修復，黑名單過濾是業界慣例。候選人若不知道，代表缺乏真實生產維運經驗。

**弱答案特徵**：「我們每週排程重建索引，重建期間暫停寫入。」沒有說明 recall 衰退速率、重建後如何驗證、流量如何切換、舊索引如何回滾。

**強答案特徵**：點出 HNSW 圖失衡的具體機制（節點鄰居數不均、長尾節點導致搜尋路徑加長），提出 Base + Delta 雙索引架構及查詢合併策略，描述 recall@10 golden-set 驗證閾值（≥ 90%），以及 10% → 50% → 100% 漸進流量切換與 24 小時回滾窗口的完整流程。

**面試情境**：「你的 RAG 系統上線六個月後，客服團隊反映搜尋到的文章越來越舊、越來越不相關，但後台顯示知識庫文件每天都有新增。你的 vector search 服務的 QPS 和錯誤率都正常。你怎麼診斷，又怎麼解決？」

這個情境的陷阱在於——所有「系統健康」指標都正常，問題是隱性的精度衰退。正確的診斷路徑是：

1. 先查 `delta_index_size`：若六個月來持續增量、從未重建，Delta 可能已累積數十萬筆——HNSW 圖嚴重漂移。
2. 對 golden test set 執行 recall@10 採樣，確認數字（如：發現 recall 已從 94% 跌至 71%）。
3. 執行緊急全量重建，驗證通過後 Blue-Green swap，並建立夜間排程防止再次發生。
4. 補建監控：`delta_index_size` 超過 40K 時告警，每小時採樣 recall。

---

## 二、核心原理與技術深度

### HNSW 圖為什麼會漂移（Drift）

HNSW（Hierarchical Navigable Small World）是目前最主流的 ANN 索引結構。它在建構時為每個節點在各層維持固定的鄰居數（參數 `M`，通常 16–64），搜尋時從最頂層貪心向下導航，每層選取距離 query 最近的鄰居繼續往下，直到 Layer 0 收集候選集。理論上在 `M=16, efConstruction=200` 的設定下，靜態資料集的 recall@10 可達 95%–97%。

問題出在**增量插入**的設計取捨：每次 `upsert` 操作只為新節點連結鄰居，不會重新審視既有節點的連結是否仍是最優。隨著插入量累積：

1. **連結配額耗盡**：每個節點在 Layer 0 的最大鄰居數受 `maxM` 上限約束（通常 `2M = 32`）。新節點湧入後，熱門區域的既有節點鄰居槽被新鄰居佔滿，無法再接納更相關的連結。
2. **長尾節點形成**：早期插入的節點在當時的圖中連結度良好，但後來的新節點繞過它們建立更短路徑；舊節點的入度（in-degree）下降，在貪心導航中被跳過的機率升高，形同孤立。
3. **圖直徑（diameter）增長**：健康圖的平均搜尋跳數約 6–8 跳（1M 向量規模）。漂移後平均跳數可增至 12–15 跳，每跳需要計算鄰居的餘弦距離，搜尋延遲線性上升。

**實測衰退數字**（1M 維度 768 的向量索引，`M=16, efSearch=100`）：

| 增量插入量 | recall@10 | P50 搜尋延遲 | P99 搜尋延遲 |
|-----------|-----------|------------|------------|
| 0（剛重建）| 94% | 12ms | 28ms |
| 5,000 筆 | 93% | 13ms | 30ms |
| 10,000 筆 | 91% | 15ms | 34ms |
| 20,000 筆 | 87% | 18ms | 41ms |
| 50,000 筆 | 78% | 24ms | 58ms |

**每 5,000 筆增量，recall@10 約下滑 1 個百分點**。超過 50,000 筆後曲線加速惡化，原因是高層（Layer 2+）的導航錯誤開始累積——頂層的錯誤鄰居會把整條搜尋路徑帶偏，底層再怎麼細搜都無法彌補。

### HNSW 圖失衡的機制示意

```
── 剛重建後（健康圖）─────────────────────────────────────────

  Layer 2:   [A] ─────────────── [E] ─────── [I]
               │                   │
  Layer 1:   [A]──[B]──[C]──[D]──[E]──[F]──[G]──[H]──[I]
               │    │    │    │    │    │    │    │    │
  Layer 0:   [A][a][B][b][C][c][D][d][E][e][F][f][G][g][H][h][I]
              每節點鄰居均勻，搜尋路徑 ≤ 8 跳，recall 94%

── 50,000 次增量插入後（漂移圖）──────────────────────────────

  Layer 2:   [A] ─────────────────────────── [I]
               │                               │
  Layer 1:   [A]──[B]──[C]──[D]──[E]──[F]──[G]──[H]──[I]
               │              │              (B', C' 長尾：
  Layer 0:   [A][a][B][b]   [D][d][E]...    鄰居槽耗盡，
                       │                    入度低，貪心
                   [孤立區域]               路徑不經過它們)
              搜尋路徑 ≥ 14 跳，recall 78%
```

### Lambda 架構：Base + Delta 雙索引

解法不是「更頻繁地鎖定重建」，而是把**靜態精度需求**與**動態寫入需求**分離：

```
┌──────────────────────────────────────────────────────────┐
│  寫入路徑                                                 │
│                                                          │
│  Document Update                                         │
│       │                                                  │
│       ▼                                                  │
│  Embed（Vertex AI Text Embeddings）                      │
│       │                                                  │
│       ├──▶  Delta Index（write-optimized, < 50K 向量）   │
│       │     接受 real-time upsert，略有 recall 損耗       │
│       │                                                  │
│       └──▶  Deleted IDs Blacklist（Firestore Hash Set） │
│             O(1) lookup，TTL = 下次重建完成後清空         │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  查詢路徑                                                 │
│                                                          │
│  User Query                                              │
│       │                                                  │
│       ▼                                                  │
│  Embed Query                                             │
│       │                                                  │
│       ├──▶  Base Index ANN（Top-K × 2）  ──┐            │
│       │     大型、唯讀、完整最佳化 HNSW     │            │
│       │                                   ├─▶ Merge    │
│       └──▶  Delta Index ANN（Top-K × 2） ──┘  → Dedup  │
│                                                → Filter  │
│                                                  Blacklist│
│                                                → Rerank  │
│                                                → Top-K   │
└──────────────────────────────────────────────────────────┘
```

**查詢合併邏輯**：Base 和 Delta 各自返回 `Top-(K×2)` 候選（避免漏掉邊界附近的相關文件），合併去重後共約 `2K` 個候選，過濾黑名單，再以 cross-encoder reranker 精排，最終返回 Top-K。整個 merge + filter + rerank 流程在 20–30ms 完成，在 P99 延遲 50–80ms 的 RAG 系統中佔比合理。

**查詢合併的延遲拆解**（K=10，候選池 20 筆）：

```
步驟                        典型延遲
─────────────────────────────────────────
Query Embedding             8ms
Base Index ANN（並行）      12ms  ┐ 並行執行
Delta Index ANN（並行）     4ms   ┘ 取較長者 12ms
Merge + Dedup               <1ms
Firestore Blacklist Filter  3–5ms（get_all 20 IDs）
Cross-Encoder Rerank        15–20ms（20 筆候選）
─────────────────────────────────────────
P50 總延遲                  約 42ms
P99 總延遲                  約 75ms
─────────────────────────────────────────
```

Base 和 Delta ANN 必須**並行**執行，否則序列執行會讓延遲增加 4ms（Delta ANN 時間），雖然看起來小，但在高 QPS 場景下是不必要的序列瓶頸。Cloud Run 的並行 HTTP 請求或 Python `asyncio.gather` 都可實現。

### 刪除處理：Blacklist 方案的細節

向量資料庫刪除一個節點若要維持圖連通性，需要重新連結其鄰居（類似鏈結串列刪除節點），但 HNSW 多層結構的重連代價接近局部重建——商業向量資料庫通常不支援，或支援但不保證圖結構品質。

**Firestore Hash Set 實作**：

```python
# 刪除時寫入黑名單（Cloud Firestore）
def mark_deleted(doc_id: str):
    db.collection("vector_blacklist").document(doc_id).set({
        "deleted_at": firestore.SERVER_TIMESTAMP,
        "rebuild_epoch": current_epoch()  # 下次重建完成後清除
    })

# 查詢時過濾（O(1) Firestore 讀取）
def filter_blacklist(candidates: list[str]) -> list[str]:
    blacklist_refs = [db.collection("vector_blacklist").document(id)
                      for id in candidates]
    snapshots = db.get_all(blacklist_refs)
    deleted = {s.id for s in snapshots if s.exists}
    return [id for id in candidates if id not in deleted]
```

Firestore 單次 `get_all`（批次讀取）對 20 個 ID 的延遲約 3–5ms，遠低於 ANN 搜尋本身的耗時。

**Blacklist 的生命週期管理**：每次 Blue-Green swap 完成後，已重建入 Base 的向量在 Base 中已物理消失，對應的 blacklist 條目可以安全清除。清除時機以 `rebuild_epoch` 欄位為準，任何 `rebuild_epoch <= current_completed_epoch` 的條目均可批次刪除。Firestore 批次刪除上限 500 筆/次，若黑名單超過 500 筆需分批處理。

**幽靈文件的 GDPR 涵義**：在 GDPR「被遺忘權」場景下，用戶要求刪除其個人資料。若僅刪除原始文件但未更新向量索引，向量仍可能透過語義相似性查詢被間接召回，LLM 再生成時洩漏個人資料。Blacklist 確保查詢層立即生效（< 1 分鐘），重建確保索引層永久清除，兩層缺一不可。

### 夜間重建管線（Nightly Rebalance Pipeline）

以 Cloud Composer（Airflow）實作的 DAG，每晚 02:00 UTC 執行：

```
DAG: vector_index_nightly_rebuild
────────────────────────────────────────────────────────
Step 1: re_embed_changed_docs
  - 從 Cloud Spanner 讀取過去 24h 有變更的 doc_id
  - 批次呼叫 Vertex AI Embedding API（每批 250 筆）
  - 新向量寫入 GCS staging bucket
  估計時間：5–15 分鐘（取決於變更量）

Step 2: merge_delta_into_base
  - 讀取 Base Index 快照 + Delta Index 所有向量
  - 在 n1-highmem-8 × 4 worker node 上執行 HNSW 全量重建
  - 重建結果寫入 GCS（新版本路徑，非覆蓋原路徑）
  估計時間：40–60 分鐘（1M 向量規模）

Step 3: validate_recall
  - 對 golden test set（500 個 query，人工標注 Top-10）
    執行 ANN 搜尋，計算 recall@10
  - 若 recall@10 < 90%：DAG 標記 FAILED，PagerDuty 告警，
    pipeline 中止，不進行 swap
  - 若 recall@10 ≥ 90%：繼續下一步
  估計時間：3–5 分鐘

Step 4: blue_green_swap（漸進切換）
  - 10% 流量路由至 Green（新索引）→ 觀察 5 分鐘
    監控：recall 採樣、P99 延遲、錯誤率
  - 50% 流量路由至 Green → 觀察 5 分鐘
  - 100% 流量路由至 Green
  - Blue（舊索引）保留 24 小時，隨時可一鍵回滾
  - 24 小時後清空 Delta Index、清空 Blacklist（已重建入 Base）
  估計時間：15 分鐘（含觀察窗口）

總管線時間：約 70–95 分鐘
────────────────────────────────────────────────────────
```

**Blue-Green swap 期間查詢延遲**：因為同時維持兩組索引 endpoint，load balancer 需要做加權路由，額外引入約 < 5ms 的路由決策延遲，對 P50 影響可忽略，P99 增加約 3–5ms。切換完成後恢復正常。

### 端對端情境走查：一次完整的知識庫更新週期

以一個企業客服 RAG 系統為例，知識庫有 800K 份文件，每天新增或修改約 2,000 份：

```
週一 09:00：知識庫管理員上傳 500 份新產品手冊
  │
  ├─ Pub/Sub 接收 500 個 doc_update 事件
  ├─ Cloud Run embedding worker（並行 20 instances）
  │  批次 embed（每批 250 筆，2 批）→ 約 3 分鐘
  └─ Delta Index upsert 500 筆
     delta_index_size: 500 → 3,000（加上週末累積）

週二 02:00：夜間重建管線啟動
  Step 1: re_embed_changed_docs（週一全天共 2,000 份）→ 12 分鐘
  Step 2: merge Base（800K）+ Delta（3,000）→ 全量重建 → 52 分鐘
  Step 3: validate recall@10（500 golden queries）→ 94.2% ✓
  Step 4: Blue-Green swap
    - 10% 流量 → Green → 觀察 5 分鐘 → P99 28ms, recall 採樣 94% ✓
    - 50% 流量 → Green → 觀察 5 分鐘 → 正常 ✓
    - 100% 流量 → Green
    - Blue 保留 24h
  總時間：72 分鐘

週二 02:00 之後查詢：
  - 使用者 query「XX 產品保固條款」
  - Base ANN（803K 向量） + Delta ANN（0 向量，剛重建後清空）→ merge
  - recall@10: 94%，P50: 12ms，P99: 28ms ← 恢復健康狀態
```

這個走查說明了為什麼「Delta 在重建完成後清空」是關鍵步驟——重建後 Base 已包含所有向量，Delta 繼續存在只會造成重複計算，應立即清空讓 Delta 從 0 重新累積。

### 為什麼選 Lambda 架構不選其他替代方案

| 選擇 | 選它的理由 | 不選的理由 | 翻轉條件（何時反過來選） |
|------|-----------|-----------|----------------------|
| **Lambda（Base + Delta）** | 精度與即時性分離；Base 高精度、Delta 快速接收；夜間重建不影響線上流量 | 查詢路徑複雜度翻倍（雙 ANN + merge）；維護兩套 endpoint；需要 golden test set 持續維護 | 寫入量極低（< 100 筆/天）時單索引更簡單 |
| **HNSW efSearch 調高補償** | 實作最簡單，不需改架構 | recall 補償有限（+5% efSearch 延遲翻倍）；根本沒解決圖失衡問題，只是搜尋更多節點 | 幾乎從不；這是治標不治本的短期妥協 |
| **IVF（Inverted File Index）** | 重建成本比 HNSW 低；支援就地添加新向量到 cluster | 需要定期重新 cluster（kmeans）才能維持精度；cluster 不平衡時 recall 更差；不適合高維（> 512 dim）稀疏查詢 | 向量維度 < 256 且資料分佈穩定時 IVF 是合理選擇 |
| **Blacklist（Firestore）** | O(1) 查詢；不影響圖結構；實作 1 天完成 | 已刪除向量仍佔用 index 空間直到下次重建；大量刪除（> 20%）時 blacklist 本身也變慢 | 若刪除佔比 > 30%，應該提前觸發全量重建而非依賴 blacklist |
| **全量即時重建（每次寫入後）** | 索引始終最新最精確 | 1M 向量重建需 45–60 分鐘；寫入 QPS > 1 時根本跟不上；費用 = $0.80 × 寫入次數，不可接受 | 僅適用於測試環境或資料集極小（< 10K 向量）的 PoC |
| **Recall 閾值 90%（不是 95%）** | 允許一點點 recall 損耗換取更快的重建週期；50 筆新增後即可上線不必等精度達到峰值 | 若應用場景對 recall 極度敏感（如醫療知識庫），90% 可能不夠 | 醫療、法律等高合規場景應提高至 95%，並搭配人工抽查 |

### 監控指標設計：如何早期發現 Drift

光靠 recall 指標還不夠，要在 recall 崩潰前就察覺。生產環境應同時追蹤：

```
監控指標組合（Cloud Monitoring）
─────────────────────────────────────────────────────
1. delta_index_size（向量數量）
   告警閾值：> 40,000 → warning，> 50,000 → 觸發提前重建
   採樣頻率：每 5 分鐘

2. recall_at_10_base（Base Index 對 golden set）
   告警閾值：< 92% → warning，< 90% → CRITICAL
   採樣頻率：每小時（50 query 子集，避免頻繁呼叫 ANN 增加延遲）

3. recall_at_10_delta（Delta Index 對 golden set）
   告警閾值：< 89% → warning（Delta 正常應有 -2% penalty）
   採樣頻率：每小時

4. merge_query_p99_latency（查詢合併服務 P99）
   告警閾值：> 100ms → warning（正常應 < 80ms）
   採樣頻率：每分鐘（Cloud Run request latency 自動採集）

5. blacklist_size（Firestore blacklist 文件數）
   告警閾值：> 5,000 → warning，代表大量刪除尚未被重建消化
   採樣頻率：每小時

6. nightly_rebuild_duration（重建 DAG 執行時間）
   告警閾值：> 90 分鐘 → warning（可能是資料量暴增）
   採樣頻率：每次 DAG 執行完成後記錄
─────────────────────────────────────────────────────
```

**診斷 SOP**：當聯合 recall@10 低於 90% 時，依序檢查：
1. `delta_index_size` 是否超標 → 若是，立即提前重建
2. `recall_at_10_base` 是否低 → 若是，上次重建可能有 bug，檢查 DAG 日誌
3. `recall_at_10_delta` 異常低 → 可能是 embedding model 版本不一致，檢查 model metadata
4. P99 延遲同時升高 → 圖直徑增長，優先重建，同時調高 `efSearch` 作為臨時補償

---

## 三、三個實作層次

### Layer 1 — 最小可行（Minimal）

**核心做法**：單一向量索引，接受增量 upsert，每週排程全量重建，重建期間設定 maintenance window（停止寫入，讀取繼續，但精度不保證）。

**新增元件**：
- 一個 Vertex AI Vector Search endpoint
- Cloud Scheduler cron job（每週日凌晨觸發重建）
- 基本的 recall 監控（每日對 50 個 golden query 抽樣）

**解決的問題**：recall 不會永久累積惡化；有可預期的重建節奏，工程團隊知道「週一早上索引是新鮮的」。

**遺留問題**：
- maintenance window 對 24/7 服務不可接受（每週停寫 1–2 小時）
- 已刪除文件仍出現在查詢結果（幽靈文件）
- 無重建後品質驗證，若 pipeline 有 bug 靜默上爛索引
- 週末插入的大量文件（最多 7 天的增量）recall 可能跌至 78%

**成本/複雜度**：低。工程工時 1–2 天。月費約 $50–$100（單 endpoint + 偶發重建計算費）。

---

### Layer 2 — 生產就緒（Production-Ready）

**新增元件（相較 Layer 1）**：
- **Delta Index**：獨立的寫入優化索引，接受 real-time upsert，容量上限 50,000 向量
- **Deleted IDs Blacklist**：Firestore collection，O(1) 查詢時過濾
- **查詢合併中間件**：Cloud Run service，並行 ANN + merge + filter + rerank
- **夜間重建 DAG**：Cloud Composer，包含 re-embed、merge、recall 驗證、Blue-Green swap 四步驟
- **Golden Test Set**：500 個人工標注的 query，維護於 GCS，用於 recall@10 閾值驗證

**解決的問題**：
- 零停機：Delta 接收實時寫入，Base 背景重建
- Recall 每日恢復至 94%，Delta 累積期間最差 ≈ 91%（< 10,000 筆）
- 刪除不影響查詢結果
- 重建有品質關卡，自動阻擋劣質索引上線

**具體數字**：
- Delta Index recall penalty：約 -2% 相較全量重建的 Base（Delta 小圖，鄰居候選池較小）
- 夜間重建（1M 向量）：約 45–60 分鐘，費用約 $0.80/次，月費 $24
- Delta Index 維持小規模（< 50K 向量），Delta ANN P50 延遲 < 5ms（圖小，搜尋快）
- Blue-Green 切換額外延遲：< 5ms（加權路由開銷）

**成本/複雜度**：中。工程工時 1–2 週。月費約 $150–$250（雙 endpoint + Firestore + Cloud Composer + Cloud Run）。

---

### Layer 3 — 企業級（Enterprise-Grade）

**新增元件（相較 Layer 2）**：

- **自動漂移偵測**：每小時對 golden test set 執行 recall@10 採樣（50 query 子集）。若連續 3 次 < 88%（Delta 累積異常快），自動觸發提前重建，不等夜間排程。告警同時寫入 PagerDuty + Cloud Monitoring。
- **Canary Shadow Query**：新索引上線前，以 1% 真實流量做 shadow 比對——同時查詢 Blue 和 Green，比較 Top-10 的 Jaccard 相似度。若相似度 < 85%（代表結果集差異過大），阻擋 Blue-Green swap 並觸發人工審查。
- **多地域同步**：asia-east1 / us-central1 各自維持獨立 Base + Delta，以地域為單位漸進切換。地域間以 Cloud Spanner 同步 rebuild epoch，保證全域一致性。
- **分層成本最佳化**：超過 90 天未被查詢命中的向量移至「冷層索引」（較低的 `M` 和 `efSearch` 參數，精度 -5%，費用 -40%）；熱向量保留高精度 Base。使用 Bigtable 追蹤每個向量的最後命中時間。
- **完整審計鏈**：每次 Blue-Green swap 的 recall 驗證報告、流量切換時間軸、Canary 比對結果，全部寫入 Cloud Spanner，保留 90 天。SRE 可隨時查詢「哪個版本的索引在何時以何種 recall 上線」。

**解決的問題**：SLA 級別的精度保證（每小時監控）、跨地域一致性、成本控制（冷熱分層）、可審計性（合規需求）。

**成本/複雜度**：高。工程工時 4–8 週。月費相較 Layer 2 增加 $200–$500（多地域 endpoint × 2、Spanner、Bigtable、額外 Cloud Run instances）。

### 三層架構成本與精度對比

| 維度 | Layer 1（Minimal） | Layer 2（Production） | Layer 3（Enterprise） |
|------|-------------------|----------------------|----------------------|
| 停機需求 | 每週 1–2h 停寫 | 零停機 | 零停機 |
| recall@10 最差情況 | 78%（7 天末段） | 91%（Delta < 10K） | 91%（自動提前重建） |
| recall@10 平均 | ~86% | ~93% | ~93–94% |
| 刪除幽靈文件 | 存在，直到重建 | 查詢時過濾 | 查詢時過濾 + 審計 |
| 重建品質保證 | 無 | recall ≥ 90% 關卡 | recall ≥ 90% + Canary |
| 工程工時 | 1–2 天 | 1–2 週 | 4–8 週 |
| 月費估算 | $50–$100 | $150–$250 | $350–$750 |
| 適用規模 | < 50K 向量、PoC | 50K–2M 向量、生產 | 2M+ 向量、多地域、合規 |

---

## 四、常見錯誤與陷阱

| 錯誤模式 | 後果 | 正確做法 |
|---------|------|---------|
| 單一索引，重建時暫停寫入 | maintenance window 影響可用性；重建期間新文件遺失，24/7 服務 SLA 破功 | Lambda 雙索引：Delta 接收實時寫入，Base 背景重建，零停機 |
| 重建後未做 recall 驗證直接 swap | 若 embedding pipeline 有 bug（如模型版本漂移、API 回傳 truncated 向量），劣質索引靜默上線，使用者查詢品質崩潰，需數天才能察覺 | 對 500 query golden test set 驗證 recall@10 ≥ 90% 才允許 swap；不過關則 DAG FAILED，自動告警 |
| 誤以為向量資料庫支援就地刪除 | 已刪除文件仍出現在查詢結果（幽靈文件），RAG 系統基於過時或已下架的知識生成回答，在合規場景（如 GDPR 刪除權）造成法律風險 | Deleted IDs Blacklist（Firestore Hash Set）於查詢時 O(1) 過濾；下次重建完成後黑名單清空 |
| Blue-Green 一次全量切換（0% → 100%） | 若新索引有問題，全量流量即時受影響；若要回滾，需要重新路由，期間服務降級數分鐘 | 漸進切換 10% → 50% → 100%，每步觀察 5–10 分鐘，舊 Blue 索引保留 24 小時供一鍵回滾 |
| Delta Index 無上限，無限期累積 | Delta 超過 100K 向量後自身也發生嚴重漂移（Delta 的 recall@10 可跌至 85%）；merge 查詢延遲增加；夜間重建時 merge 步驟耗時暴增 | Delta 設硬上限（50K 向量），觸及上限時強制提前觸發夜間重建管線，不等定時排程 |
| 未分別追蹤 Base 和 Delta 各自的 recall | 聯合 recall 下滑時不知道是 Base 老化、Delta 過大，還是 merge 邏輯問題，難以診斷根因 | 三個獨立指標：Base recall@10、Delta recall@10、merge 後聯合 recall@10；分別設告警閾值 |
| Embedding 模型升版後未同步重建兩個索引 | Base 使用舊版 embedding space，Delta 使用新版；ANN 距離計算基於不同向量空間，merge 結果語義混亂，top-K 排序完全錯誤 | 模型升版時強制觸發 Base + Delta 同步全量重建；版本號寫入 index metadata，查詢中間件驗證兩索引版本一致才合並 |
| Golden Test Set 長期不更新 | 知識庫內容演進後，golden queries 不再代表真實用戶需求；recall 指標虛高，掩蓋實際精度退步 | 每季度從真實查詢日誌中採樣更新 golden set（確保匿名化 PII），保持 500 query 規模，人工驗證 Top-10 標注 |

---

## 五、與其他核心主題的關聯

- **Part 4（Hybrid Search & RRF）**：Hybrid Search 的向量分支輸入直接依賴 Base + Delta merge 後的 Top-K 候選集。RRF fusion 必須在 blacklist 過濾之後才執行——否則已刪除文件的向量分數會污染 BM25 + ANN 的 rank 融合結果，導致幽靈文件進入最終排序。
- **Part 5（Reranking & Cross-Encoder）**：Cross-encoder reranker 的輸入集合品質直接受 HNSW recall 制約。若 recall@10 衰退到 78%，代表有 22% 的真正相關文件未進入 reranker 的候選池，cross-encoder 再怎麼精排也無法彌補這個早期損失——精度天花板被 ANN 決定。
- **Part 11（Async Event-Driven Pipeline）**：Delta Index 的寫入路徑最自然地以事件驅動架構實作：文件更新事件 → Pub/Sub topic → Cloud Run embedding worker（並行擴展）→ Delta Index upsert。夜間重建的四步 DAG（re-embed → merge → validate → swap）是 Cloud Composer 的典型使用場景，需要嚴格的步驟依賴與失敗中止語意。
- **Part 3（State Machine & DAG）**：重建管線本身是一個嚴格的有向無環圖，每個節點失敗必須中止整條 pipeline，不可跳過 validate 直接進 swap。State Machine 的狀態轉換（REBUILDING → VALIDATING → SWAPPING → STABLE）需要在分散式環境下保持一致性，防止兩個 DAG 實例同時進行 swap（應加 Firestore distributed lock）。
- **Part 12（Backpressure & Fair-Share）**：Delta Index 的寫入路徑在知識庫大量更新時（如批次匯入 10,000 份文件），embedding worker 需要背壓控制——否則 Pub/Sub 積壓爆炸、Delta Index 在數小時內觸及 50K 上限，強迫提前重建而干擾夜間排程。Fair-share 佇列確保批次更新不擠佔實時寫入。

---

## 六、系統效應：導入 Lambda 架構前後對比

| 指標 | 導入前（單索引 + 週重建） | 導入後（Lambda + 夜間重建） | 改善幅度 |
|------|--------------------------|----------------------------|---------|
| recall@10 平均 | 86%（週末末段 78%） | 93%（Delta < 10K 時） | +7–15pp |
| recall@10 最差時段 | 78%（週五末段） | 91%（Delta 接近上限） | +13pp |
| 停機需求 | 每週 1–2 小時停寫 | 零停機 | 100% 消除 |
| 幽靈文件出現率 | 持續存在直到重建 | 查詢時即時過濾（< 1ms） | 即時消除 |
| 重建品質保證 | 無（上線即生效） | recall ≥ 90% 品質關卡 | 有品質下限 |
| 回滾能力 | 無（覆蓋後無法還原） | 舊索引保留 24h，一鍵回滾 | 完整回滾窗口 |
| 精度事故偵測 | 平均 3–5 天才感知 | 每小時採樣，< 1 小時告警 | 偵測速度 72x |
| 月費 | ~$80（單 endpoint） | ~$200（雙 endpoint + 管線） | +$120 |
| 工程複雜度 | 低 | 中（1–2 週實作） | 可接受的成本 |

核心結論：**$120/月的額外費用換來 recall 平均提升 7–15pp，以及零停機與即時刪除能力**。對一個每天服務 10 萬次查詢的 RAG 系統而言，recall 提升 7pp 代表每天多找到 7,000 次正確答案——這個 ROI 在絕大多數產品場景下都完全合理。

---

## 七、面試一句話（Killer Phrase）

> *「向量索引的精度不是靜態保證——HNSW 圖在每 5,000 次增量插入後 recall@10 約下滑 1%，累積 50,000 筆時從 94% 跌至 78%，且這個衰退完全靜默、監控面板上不會出現任何紅燈。我的標準做法是 Lambda 架構：Base Index 每晚全量重建，Delta Index 接收實時寫入，查詢時雙索引並行 ANN、merge 結果、過 Firestore Blacklist 濾掉已刪除向量、再 cross-encoder rerank 回傳 Top-K；重建完成後不直接切流量，先對 500 個 golden queries 驗證 recall@10 ≥ 90%，通過後才以 10% → 50% → 100% 的漸進 Blue-Green 切換上線，舊索引保留 24 小時作為回滾窗口，切換期間額外引入 < 5ms 延遲，對用戶完全透明。」*

---

**系列導航**

← [前一篇](/posts/fde-interview-core-topic-14-embedding-versioning-zh/) | [後一篇](/posts/fde-interview-core-topic-16-multimodal-retrieval-zh/) →
