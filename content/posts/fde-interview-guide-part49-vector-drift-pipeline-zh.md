---
title: "FDE Interview Guide Part 49：百萬級 RAG 系統的即時資料漂移與向量索引自動更新管線"
date: 2026-06-08T09:00:00+08:00
draft: false
description: "深度解析企業 RAG 系統中的向量資料漂移問題：Lambda Vector Architecture、HNSW Graph Drift 監控、Blue-Green Index Deployment，以及如何在零停機的前提下維持百萬級知識庫的索引精準度。"
categories: ["engineering", "all"]
tags: ["RKK", "Interview", "Cloud", "AI", "RAG", "VectorSearch", "DataPipeline", "MLOps", "VertexAI"]
authors: ["yen"]
readTime: "26 min"
---

> 大多數工程師的直覺：「索引過期了？重新跑一次 Re-indexing 就好。」
> 資深 FDE 的直覺：「Re-indexing 要數小時，這期間服務怎麼辦？Re-indexing 之後 HNSW 圖會不會因此失衡？」
> 大多數工程師的直覺：「那就頻繁做增量更新，隨時保持最新。」
> 資深 FDE 的直覺：「增量更新累積到一定程度，Graph Drift 會讓 RECALL@10 從 95% 跌到 70%，這才是真正的定時炸彈。」

---

## 面試情境

> **面試官**：「你們的企業客戶每天會在 GCS 上新增、修改、刪除數千份 PDF 文件。你們的 AI Agent 需要即時查詢這些知識庫，但現在常常給出已被刪除或過期的內容，讓客戶非常不滿。我知道 Vertex AI Vector Search 支援增量更新，但我聽說大規模頻繁更新會造成 HNSW 圖退化，進而影響搜尋精準度。請告訴我，你會如何設計一套既能即時響應文件變更、又能長期維持向量索引健康度的自動化管線？在系統規模達到百萬向量時，你的設計會有哪些具體調整？」

---

## 一、核心問題：為什麼向量索引的「即時性」與「精準度」天生對立？

### 1.1 RAG 系統的資料新鮮度危機

在企業 RAG（Retrieval-Augmented Generation）場景中，知識庫並非靜態的。法規文件每週更新、產品手冊每月改版、內部 SOP 隨業務調整。當 AI Agent 仰賴向量檢索來回答問題時，索引延遲（Index Lag）直接等同於「AI 在說謊」。

典型的痛點數字：

- 文件刪除後，向量索引平均滯後 **4–8 小時**才能同步
- 在此期間，Agent 回答基於已廢棄文件的機率高達 **23%**
- 企業客戶每月因 AI 給出過期資訊而提交的客訴工單：平均 **340 件**

### 1.2 三重矛盾的根本原因

```
矛盾一：即時性 vs. 批次效率
┌────────────────────────────────────────────┐
│  即時更新：每次文件變更立即寫入向量索引      │
│  優點：延遲 < 30 秒                         │
│  缺點：HNSW 圖節點連結逐漸失衡（Graph Drift）│
│        每 10K 次增量更新後，RECALL@10 下降約 8%│
└────────────────────────────────────────────┘

矛盾二：完整重建 vs. 服務可用性
┌────────────────────────────────────────────┐
│  Batch Re-indexing：定期完整重建 HNSW 圖     │
│  優點：索引結構完美，精準度最高              │
│  缺點：100 萬向量重建需要 3–5 小時           │
│        重建期間服務降級或完全停機            │
└────────────────────────────────────────────┘

矛盾三：刪除操作 vs. 向量索引特性
┌────────────────────────────────────────────┐
│  向量資料庫刪除並非真正刪除                  │
│  而是打「墓碑標記」（Tombstone），圖結構保留  │
│  大量 Tombstone 累積會拖慢搜尋速度 40%       │
│  且被刪文件的向量仍可能出現在 Top-K 候選集   │
└────────────────────────────────────────────┘
```

### 1.3 問題的本質：兩個時間維度的解耦

正確的解題框架不是「二選一」，而是**將即時性問題與精準度問題解耦到不同的時間維度**：

- **秒級**：處理文件變更事件，保證新內容可被查詢到
- **分鐘級**：維護刪除黑名單，確保廢棄內容不出現在結果中
- **夜間**：批次修復 HNSW 圖結構，恢復長期精準度

這正是 **Lambda Vector Architecture** 的核心思想。

---

## 二、三個演進階段

### ╔══ Phase 1（POC / < 10K 文件）══╗

**設計哲學**：用最簡單的方式驗證 RAG 業務價值，不過度工程化。

```
┌──────────────────────────────────────────────────────┐
│                   Phase 1 架構                        │
│                                                      │
│  GCS Bucket                                          │
│  ┌──────────┐   Object Finalize   ┌──────────────┐  │
│  │ PDF 文件  │──────Trigger───────▶│ Cloud Run    │  │
│  └──────────┘                     │ (Embed 服務) │  │
│                                   └──────┬───────┘  │
│                                          │           │
│                                    Upsert │           │
│                                          ▼           │
│                              ┌──────────────────┐    │
│                              │ Vertex AI Vector  │    │
│                              │ Search（單一索引） │    │
│                              └──────────────────┘    │
│                                          │           │
│                                     Query │           │
│                                          ▼           │
│                              ┌──────────────────┐    │
│                              │   Agent / LLM    │    │
│                              └──────────────────┘    │
└──────────────────────────────────────────────────────┘
```

**新增元件（vs 零）**：

| 元件 | 用途 | 月成本估算 |
|------|------|-----------|
| GCS Object Finalize Trigger | 文件上傳事件偵測 | $0（免費配額內） |
| Cloud Run（Embed 服務） | PDF 解析 + 向量化 | ~$30 |
| Vertex AI Vector Search（單索引） | 向量儲存與搜尋 | ~$50 |
| Firestore（可選，存中繼資料） | 文件 metadata | ~$5 |

**Phase 1 成本**：~$85/月

**解決的問題**：

- 文件新增可自動索引，延遲約 2–5 分鐘
- 基本的 RAG 查詢功能可用

**遺留的問題**：

- 刪除文件後，向量索引無法立即感知（需手動觸發）
- 無監控，無法得知 RECALL 是否下滑
- 10K 文件以上重建需要 30+ 分鐘停機

---

### ╔══ Phase 2（MVP / 10K–200K 文件）══╗

**設計哲學**：引入刪除黑名單機制，解決最緊迫的「過期資訊」問題，同時加入基本監控。

```
┌────────────────────────────────────────────────────────────────┐
│                        Phase 2 架構                             │
│                                                                │
│  GCS Bucket                                                    │
│  ┌──────────┐   Cloud Storage Trigger                          │
│  │ 文件變更  │──────────────────────────▶ Cloud Pub/Sub Topic  │
│  └──────────┘   (新增/修改/刪除)          └────────┬──────────┘│
│                                                    │           │
│                                              Subscribe │        │
│                                                    ▼           │
│                                          ┌───────────────────┐ │
│                                          │  Cloud Run Worker │ │
│                                          │  ┌─────────────┐  │ │
│                                          │  │ 新增/修改：  │  │ │
│                                          │  │ → Embed     │  │ │
│                                          │  │ → Upsert    │  │ │
│                                          │  ├─────────────┤  │ │
│                                          │  │ 刪除：      │  │ │
│                                          │  │ → Blacklist │  │ │
│                                          │  │   寫入      │  │ │
│                                          │  └─────────────┘  │ │
│                                          └──────┬────────────┘ │
│                             ┌────────────────────┴──────────┐  │
│                             │                               │  │
│                             ▼                               ▼  │
│                   ┌──────────────────┐         ┌──────────────┐│
│                   │ Vertex AI Vector │         │  Firestore   ││
│                   │ Search（單索引） │         │ Blacklist    ││
│                   └─────────┬────────┘         │ (doc_id set) ││
│                             │                  └──────┬───────┘│
│                       Query │                         │        │
│                             ▼                  Filter │        │
│                   ┌──────────────────┐                │        │
│                   │  查詢中台 API    │◀───────────────┘        │
│                   └─────────┬────────┘                         │
│                             │                                  │
│                             ▼                                  │
│                   ┌──────────────────┐                         │
│                   │   Agent / LLM    │                         │
│                   └──────────────────┘                         │
│                                                                │
│  ┌────────────────────────────────────┐                        │
│  │ Cloud Scheduler（每晚 3 AM）        │                        │
│  │ → 觸發完整 Re-indexing             │                        │
│  │ → 清空 Blacklist                   │                        │
│  └────────────────────────────────────┘                        │
└────────────────────────────────────────────────────────────────┘
```

**新增元件（vs Phase 1）**：

| 元件 | 用途 | 月成本增量 |
|------|------|-----------|
| Cloud Pub/Sub | 解耦事件觸發與處理 | ~$5 |
| Firestore Blacklist | O(1) 刪除 ID 過濾 | ~$8 |
| 查詢中台 API（Cloud Run） | 合併 Vector 結果 + Blacklist 過濾 | ~$20 |
| Cloud Scheduler + Cloud Run Re-indexing | 每日自動重建 | ~$15 |

**Phase 2 成本**：~$183/月

**解決的問題**：

- 刪除的文件在 Blacklist 寫入後 < 60 秒即可過濾，不再出現在 Agent 回答中
- 每日夜間重建確保 HNSW 圖長期健康
- 基本的事件驅動架構，可擴展到 200K 文件

**遺留的問題**：

- 夜間重建期間（約 45 分鐘），索引暫停更新（新文件有延遲）
- 重建與查詢使用同一索引，重建期間搜尋效能下降
- 無法應對突發的大量文件更新（例如：全公司 SOP 一次性重傳）

---

### ╔══ Phase 3（Scale / 200K–1M+ 向量）══╗

**設計哲學**：Lambda Vector Architecture，Base + Delta 雙軌並行，Blue-Green 無停機切換，Cloud Composer 自動化運維。

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Phase 3 Lambda Vector Architecture                │
│                                                                     │
│  GCS Bucket                                                         │
│  ┌──────────┐  Object Trigger  ┌─────────────────────────────────┐  │
│  │ 文件變更  │────────────────▶│        Cloud Dataflow           │  │
│  └──────────┘                  │  ┌───────────┐ ┌─────────────┐ │  │
│                                │  │PDF 解析   │ │ Embedding   │ │  │
│                                │  │Chunking   │▶│ (Gecko API) │ │  │
│                                │  └───────────┘ └──────┬──────┘ │  │
│                                └─────────────────────── │ ──────┘  │
│                                         ┌───────────────┘          │
│                                         │                          │
│                          ┌──────────────┼──────────────┐          │
│                          │              │              │          │
│                          ▼              ▼              ▼          │
│               ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│               │  Delta Index│  │  Firestore  │  │ BigQuery   │  │
│               │（即時，SSD） │  │  Blacklist  │  │ 事件日誌   │  │
│               │  < 100K 向量│  │  Deleted_IDs│  │（稽核用）  │  │
│               └──────┬──────┘  └──────┬──────┘  └────────────┘  │
│                      │                │                          │
│               ┌──────┴──────┐         │                          │
│               │  Base Index │         │                          │
│               │（批次，HDD） │         │                          │
│               │  > 900K 向量│         │                          │
│               └──────┬──────┘         │                          │
│                      │                │                          │
│                      ▼                ▼                          │
│               ┌──────────────────────────────────────────────┐  │
│               │             查詢中台（Cloud Run）              │  │
│               │  ┌──────────────────────────────────────┐    │  │
│               │  │  Parallel Query（Base + Delta 同時）  │    │  │
│               │  │         ↓                            │    │  │
│               │  │  合併 Top-K 候選集（去重）             │    │  │
│               │  │         ↓                            │    │  │
│               │  │  Blacklist 過濾（O(1)，Firestore）    │    │  │
│               │  │         ↓                            │    │  │
│               │  │  重新排序 + 回傳 Top-K                │    │  │
│               │  └──────────────────────────────────────┘    │  │
│               └──────────────────┬───────────────────────────┘  │
│                                  │                              │
│                                  ▼                              │
│                        ┌──────────────────┐                     │
│                        │   Agent / LLM    │                     │
│                        └──────────────────┘                     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          Cloud Composer（Airflow）夜間自動化管線           │  │
│  │                                                          │  │
│  │  03:00  ┌──────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  每天   │ Batch    │─▶│ New Base     │─▶│ Blue-Green│  │  │
│  │         │ Re-index │  │ Index Build  │  │ Switch    │  │  │
│  │         │ (Delta   │  │（背景運算）   │  │（流量切換）│  │  │
│  │         │ + Base   │  └──────────────┘  └───────────┘  │  │
│  │         │ 合併）   │                                    │  │
│  │         └──────────┘                                    │  │
│  │  觸發條件：                                              │  │
│  │  1. 每日凌晨 3 點（定時）                                │  │
│  │  2. RECALL@10 監控下滑 > 5%（事件驅動）                  │  │
│  │  3. Delta Index 超過 80K 向量（容量觸發）                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**新增元件（vs Phase 2）**：

| 元件 | 用途 | 月成本增量 |
|------|------|-----------|
| Cloud Dataflow（串流管線） | 高吞吐量向量化處理，支援背壓控制 | ~$120 |
| Delta Index（SSD 型） | 即時增量向量，< 100K 向量，查詢 < 10ms | ~$80 |
| Base Index（HDD 型） | 主索引，100 萬向量，查詢 < 50ms | ~$200 |
| Cloud Composer（Airflow） | 夜間批次重建自動化 DAG 調度 | ~$150 |
| Cloud Monitoring + Alert | RECALL@10 自動監控與觸發 | ~$20 |
| BigQuery 事件日誌 | 全量稽核與 Drift 分析 | ~$30 |

**Phase 3 總成本**：~$783/月（100 萬向量規模）

**解決的問題**：

- 文件新增延遲 < 30 秒（Delta Index 即時寫入）
- 刪除操作延遲 < 10 秒（Blacklist O(1) 過濾）
- 夜間重建零停機（Blue-Green 切換）
- HNSW Graph Drift 自動監控與修復
- 突發大量更新由 Dataflow 背壓機制自動緩衝

---

## 三、Lambda Vector Architecture 深度解析

### 3.1 雙索引設計的核心邏輯

Lambda Vector Architecture 借鑒 Lambda Architecture（批次層 + 速度層）的思想，將向量索引分為兩種截然不同的存在形態：

```
┌────────────────────────────────────────────────────────┐
│              雙索引特性對比                               │
│                                                        │
│  屬性              Base Index          Delta Index     │
│  ─────────────────────────────────────────────────── │
│  向量數量上限      1,000,000+          < 100,000       │
│  儲存媒介          HDD（成本優先）      SSD（延遲優先） │
│  HNSW 圖結構       完美平衡            允許輕度失衡      │
│  查詢延遲（P99）   < 80ms              < 15ms           │
│  寫入支援          唯讀（只在重建時）   即時 Upsert/Delete│
│  RECALL@10 目標   > 93%               > 85%            │
│  重建週期          每日夜間             每 6 小時合併     │
└────────────────────────────────────────────────────────┘
```

**設計精妙之處**：

1. **讀寫分離**：Base Index 永遠處於唯讀狀態，不受即時更新干擾，因此 HNSW 圖結構長期穩定
2. **成本分層**：Delta Index 小而快（SSD 貴但量少），Base Index 大而穩（HDD 便宜），整體成本比全 SSD 節省約 **60%**
3. **精準度兜底**：即使 Delta Index 有少量 Graph Drift，Base Index 的高精準度確保整體 RECALL 不崩盤

### 3.2 Parallel Query 並發搜索邏輯

當用戶發起查詢時，查詢中台同時向兩個索引發起請求：

```python
# 查詢中台的核心邏輯（偽代碼）
async def parallel_vector_search(query_embedding, k=20):
    # 同時查詢兩個索引（各取 k 個候選）
    base_results, delta_results = await asyncio.gather(
        base_index.search(query_embedding, top_k=k),
        delta_index.search(query_embedding, top_k=k)
    )

    # 合併並去重（以 doc_id 為 key）
    combined = merge_and_deduplicate(base_results, delta_results)
    # Delta 的結果優先（更新的文件應覆蓋舊版本）

    # Blacklist 過濾（Firestore O(1) 讀取）
    deleted_ids = firestore.get_blacklist()
    filtered = [r for r in combined if r.doc_id not in deleted_ids]

    # 回傳 Top-K（Delta 結果已覆蓋 Base 中的舊版本）
    return filtered[:k]
```

**關鍵細節**：

- Parallel Query 的額外延遲開銷：**+5–10ms**（相比單索引查詢）
- Firestore Blacklist 讀取延遲：< 3ms（得益於 Firestore 的記憶體快取）
- 合併 + 去重的時間複雜度：O(2k log 2k)，k=20 時幾乎可忽略

---

## 四、HNSW Graph Drift 量化監控與自動修復

### 4.1 Graph Drift 的形成機制

HNSW（Hierarchical Navigable Small World）是大多數向量資料庫的底層索引結構。其核心特性是：**節點之間的連結（邊）是在插入時基於當時的鄰域分佈決定的**。

```
┌──────────────────────────────────────────────────────────┐
│                  HNSW Graph Drift 示意圖                   │
│                                                          │
│  初始狀態（健康）：                                        │
│  每個節點平均有 16 條出邊，鄰域均勻分佈                    │
│                                                          │
│    ●──●──●──●──●    ←  Layer 2（全局導航）               │
│    │        │                                            │
│  ●─●─●─●─●─●─●─●  ←  Layer 1（區域橋接）               │
│  │ │ │ │ │ │ │ │                                         │
│  ●●●●●●●●●●●●●●●  ←  Layer 0（精確搜尋）               │
│                                                          │
│  50K 次增量更新後（退化）：                                │
│  新節點集中插入某區域，舊節點連結斷裂                       │
│                                                          │
│    ●──●──●──●──●    ←  Layer 2（部分橋接斷裂）          │
│    │     ╳  │                                            │
│  ●─●─●─●─◆─◆─◆─◆  ←  Layer 1（新增向量集群）          │
│  │ │ │ │ ◆◆◆◆◆◆◆◆◆                                     │
│  ●●●●●●●●◆◆◆◆◆◆◆  ←  Layer 0（局部過密，搜尋繞遠路）  │
│                                                          │
│  結果：P99 查詢延遲從 45ms → 120ms，RECALL@10 從 93% → 74%│
└──────────────────────────────────────────────────────────┘
```

### 4.2 RECALL@10 的持續監控架構

**監控指標定義**：

- **RECALL@10**：在已知 Ground Truth 的情況下，Top-10 結果中包含正確答案的比例
- **監控頻率**：每 30 分鐘執行一次 Golden Query Set 評估
- **觸發閾值**：RECALL@10 下滑 > 5%（從基準線 93% 跌至 < 88%）觸發緊急 Rebalance

**自動修復觸發條件**（三選一，任一滿足即觸發）：

| 觸發條件 | 門檻值 | 優先級 |
|---------|--------|--------|
| RECALL@10 下滑 | > 5%（低於 88%） | P0 緊急 |
| Delta Index 向量數 | > 80,000 | P1 計畫性 |
| 定時排程 | 每日凌晨 3:00 | P2 例行 |

**Cloud Monitoring Alert 配置**：

```yaml
# alerting_policy.yaml（偽示意）
condition:
  metric: custom.googleapis.com/vector_search/recall_at_10
  comparison: COMPARISON_LT
  threshold_value: 0.88
  duration: 5m   # 持續 5 分鐘才觸發（避免誤報）
notification_channels:
  - pagerduty_oncall
  - pubsub_topic: rebalance-trigger-topic  # 同時觸發自動修復
```

---

## 五、Cloud Dataflow 串流管線設計

### 5.1 管線處理流程

```
┌──────────────────────────────────────────────────────────────┐
│              Cloud Dataflow 文件處理管線                       │
│                                                              │
│  GCS Event                                                   │
│  ┌──────────┐                                               │
│  │ 文件變更  │                                               │
│  │ 通知     │                                               │
│  └────┬─────┘                                               │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Step 1: 事件解析與路由                                │  │
│  │  ├── 新增/修改 → 進入 Embedding 管線                   │  │
│  │  └── 刪除 → 直接寫入 Firestore Blacklist（跳過 Embed）  │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │（僅新增/修改）                   │
│                           ▼                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Step 2: PDF 解析 + Chunking                          │  │
│  │  ├── 文字提取（PDFMiner）                              │  │
│  │  ├── 語意分塊（Chunk Size: 512 tokens，Overlap: 50）   │  │
│  │  └── 中繼資料附加（doc_id, version, timestamp, url）   │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │                                 │
│                           ▼                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Step 3: Batch Embedding（Gecko API）                  │  │
│  │  ├── 批次大小：32 chunks/request（最佳吞吐量）          │  │
│  │  ├── 並發工作者：8 個（Dataflow 自動擴縮容）            │  │
│  │  └── 背壓控制：Queue 超過 10K 時自動降速               │  │
│  └────────────────────────┬─────────────────────────────┘  │
│                           │                                 │
│         ┌─────────────────┴─────────────────┐               │
│         │                                   │               │
│         ▼                                   ▼               │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │ Delta Index     │               │   BigQuery      │     │
│  │ Upsert 寫入     │               │   事件日誌寫入   │     │
│  │ P99 < 200ms     │               │（非同步，不阻塞） │     │
│  └─────────────────┘               └─────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Dataflow 效能參數調優

| 參數 | 建議值 | 理由 |
|------|--------|------|
| 最大工作者數量 | 8 | 超過 8 個時 Gecko API 成為瓶頸 |
| Chunk 批次大小 | 32 | Gecko API 最佳 QPS/成本比 |
| 串流視窗 | 30 秒滾動視窗 | 平衡延遲與批次效率 |
| 機器類型 | n1-standard-4 | PDF 解析 CPU 密集，不需要 GPU |
| 持久化磁碟 | 100 GB SSD | 臨時 PDF 快取 |

**吞吐量上限**：理論最高 **3,000 個 chunks/分鐘**，相當於每分鐘處理約 **200 頁 PDF**。

---

## 六、Blue-Green Index Deployment 零停機切換

### 6.1 切換流程設計

```
┌────────────────────────────────────────────────────────────┐
│               Blue-Green Index 切換時序圖                    │
│                                                            │
│  時間軸：                                                   │
│                                                            │
│  03:00  ┌─────────────────────────────────────────────┐   │
│  啟動   │ Airflow DAG 啟動                              │   │
│         │ → 讀取 Delta Index 所有向量                   │   │
│         │ → 讀取當前 Base Index（Blue）                 │   │
│         └───────────────────┬─────────────────────────┘   │
│                             │                             │
│  03:05  ┌───────────────────▼─────────────────────────┐   │
│  建立   │ 在背景建立新的 Green Index                     │   │
│  Green  │ = merge(Blue Index + Delta Index)             │   │
│  Index  │ → HNSW 重建（ef_construction=400）           │   │
│         │ → 期間 Blue Index 繼續服務查詢，完全不受影響   │   │
│         └───────────────────┬─────────────────────────┘   │
│                             │                             │
│  05:00~ ┌───────────────────▼─────────────────────────┐   │
│  05:30  │ Green Index 建立完成                          │   │
│  驗證   │ → 自動執行 Golden Query Set 評估              │   │
│         │ → 確認 RECALL@10 > 93%（否則回滾，繼續用 Blue）│   │
│         │ → 確認查詢延遲 P99 < 80ms                    │   │
│         └───────────────────┬─────────────────────────┘   │
│                             │                             │
│  05:31  ┌───────────────────▼─────────────────────────┐   │
│  切換   │ 流量切換：Blue → Green                        │   │
│         │ → 更新查詢中台的 Base Index Endpoint 指標     │   │
│         │ → 使用 Cloud Run 環境變數熱更新（< 5 秒）     │   │
│         │ → 清空 Delta Index（重置為空）                │   │
│         │ → 清空 Firestore Blacklist                    │   │
│         └───────────────────┬─────────────────────────┘   │
│                             │                             │
│  05:32  ┌───────────────────▼─────────────────────────┐   │
│  清理   │ 舊 Blue Index 保留 24 小時後刪除              │   │
│         │ → 作為緊急回滾備份                            │   │
│         │ → 新的 Green Index 晉升為下一輪的 Blue        │   │
│         └─────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

### 6.2 Cloud Composer DAG 結構

整個夜間重建管線由 Cloud Composer（Apache Airflow）管理，DAG 包含以下任務節點：

```
check_delta_size
    │
    ├── [Delta < 1K] → skip_reindex（直接結束）
    │
    └── [Delta >= 1K] → build_green_index
                              │
                         validate_green_index
                              │
                    ┌─────────┴─────────┐
                    │                   │
               [PASS]              [FAIL]
                    │                   │
           switch_to_green      alert_oncall
                    │           rollback_to_blue
           clear_delta_index
                    │
           update_monitoring_baseline
```

**失敗處理**：若 Green Index 驗證失敗，DAG 自動回滾（保留 Blue Index），並透過 PagerDuty 通知值班工程師，下一輪凌晨再嘗試。

---

## 七、Firestore Blacklist 的設計細節

### 7.1 為什麼 Firestore 而非其他方案

刪除黑名單是整個架構中最高頻讀取的元件。每一次用戶查詢都必須在 Blacklist 中過濾結果。

**效能要求**：

- 讀取延遲：< 5ms（P99），否則顯著影響用戶感知的查詢延遲
- 並發讀取：> 1,000 QPS（百萬級 MAU 場景）
- 資料結構：需要 O(1) 的存在性查詢（`is doc_id in blacklist?`）

**Firestore Blacklist 資料模型**：

```
Collection: deleted_ids
Document: {doc_id}        ← 以 doc_id 作為 Document ID（天然 O(1)）
  Fields:
    deleted_at: Timestamp
    deleted_by: String
    version: String
    reason: String        ← "user_delete" | "system_purge"
```

**查詢方式**：

```python
# O(1) 單次讀取，不掃描全集合
doc_ref = db.collection('deleted_ids').document(doc_id)
snapshot = doc_ref.get()
is_deleted = snapshot.exists  # 利用 Document 存在性，無需讀取欄位值
```

### 7.2 Blacklist 的生命週期管理

Blacklist 在每日夜間重建完成後會被清空。但在清空前，必須確保：

1. Green Index 已完全排除所有 Blacklist 中的向量（在重建時跳過這些 doc_id）
2. Green Index 的 RECALL 驗證通過
3. 流量已完全切換至 Green Index

**清空時機的競態條件（Race Condition）防護**：

使用 Firestore Transaction 確保「清空 Blacklist」和「更新 Index Endpoint」是原子操作。若 Transaction 失敗，回滾至安全狀態，不清空 Blacklist。

---

## 八、為什麼選 X 不選 Y：關鍵設計決策對比

| 設計決策 | 選 X | 不選 Y | Flip Condition |
|---------|------|--------|---------------|
| **雙索引 vs 單索引即時更新** | Lambda Vector Architecture（Base + Delta 分離） | 單一索引持續 Upsert | 若向量總數 < 50K 且每日更新 < 500 筆，單索引維護成本更低，直接用 Phase 1 |
| **Firestore Blacklist vs 向量直接刪除** | Firestore O(1) 過濾，刪除延遲 < 10 秒 | 直接從向量索引刪除（Tombstone 機制） | 若 Blacklist 超過 50K 條且不做夜間清空，改用 Redis Set 降低 Firestore 讀取成本 |
| **Cloud Dataflow vs Cloud Run 串流** | Dataflow：背壓控制、自動擴縮、At-Least-Once 語意 | Cloud Run：無內建背壓，突發流量易丟失事件 | 若每日更新量 < 1,000 份文件，Cloud Run 的冷啟動成本可接受，Dataflow 過於昂貴 |
| **HDD Base Index vs SSD Base Index** | HDD Base：查詢 P99 < 80ms，成本低 60% | SSD Base：P99 < 20ms 但成本高 3x | 若 SLA 要求查詢 P99 < 30ms（如即時對話場景），必須升級為 SSD Base |
| **Blue-Green 切換 vs 滾動更新** | Blue-Green：舊索引完整保留，驗證失敗可立即回滾 | 滾動更新：新舊向量混合，驗證困難，回滾複雜 | 向量索引不支援部分回滾，Blue-Green 幾乎是唯一合理選擇，無 Flip |
| **Cloud Composer vs Cloud Scheduler + Cloud Run** | Composer：DAG 依賴管理、失敗重試、視覺化監控 | Scheduler + Run：簡單但缺乏任務依賴追蹤 | 若重建管線 < 3 個步驟且無分支邏輯，Scheduler + Run 成本更低（Composer 約 $150/月） |
| **RECALL@10 監控 vs 延遲監控** | RECALL@10：直接量化索引精準度劣化 | 純延遲監控：Graph Drift 初期延遲不變，只有精準度下滑 | 必須兩者並用：延遲監控系統健康，RECALL 監控索引品質，缺一不可 |

---

## 九、系統效應：導入前後的數字對比

| 指標 | 導入前（Phase 1/單索引） | 導入後（Phase 3/Lambda Architecture） | 改善幅度 |
|------|------------------------|--------------------------------------|--------|
| **文件刪除後 Agent 仍引用過期資料的機率** | 23%（索引滯後 4–8 小時） | < 0.1%（Blacklist 10 秒內生效） | **-99.6%** |
| **新文件上線延遲** | 5–30 分鐘（批次 Embed） | < 30 秒（Dataflow 即時串流） | **-98%** |
| **搜尋 RECALL@10（穩定狀態）** | 93%（剛重建後）→ 74%（月末） | 93% ± 2%（夜間自動修復維持） | **+19%（月末精準度）** |
| **查詢延遲 P50** | 35ms | 45ms（+10ms 來自 Parallel Query 合併） | **-28%（考量精準度後等效改善）** |
| **查詢延遲 P99** | 450ms（Graph Drift 後） | 85ms（穩定） | **-81%** |
| **Re-indexing 停機時間** | 3–5 小時/次（每週） | 0 秒（Blue-Green 切換） | **-100%** |
| **月均客訴工單（AI 過期資訊相關）** | 340 件 | 12 件 | **-96.5%** |
| **每月運維成本（工程師介入重建）** | 16 人時/月 | 1 人時/月（僅監控異常處理） | **-93.8%** |
| **索引儲存成本（100 萬向量）** | $280/月（全 SSD 單索引） | $165/月（SSD Delta + HDD Base 分層） | **-41%** |
| **系統月總成本** | ~$350/月 | ~$783/月（功能大幅提升下的成本增加） | 成本增加 2.2x，但精準度與可用性大幅提升 |

---

## 十、面試答題要點

> *「面對百萬向量的 RAG 知識庫，頻繁更新帶來的索引退化問題，核心解法是 **Lambda Vector Architecture**：將索引分為 Base（批次重建、唯讀、精準度高）與 Delta（即時寫入、允許輕度 Graph Drift）兩層，查詢時 Parallel Query 同時打兩個索引再合併去重，透過 Firestore Blacklist 實現 O(1) 的刪除過濾，把文件刪除到 Agent 不再引用的延遲從 4 小時壓縮至 10 秒。演進路徑上，Phase 1 的單索引方案適合 < 10K 文件驗證業務價值；Phase 2 在單索引基礎上加入 Blacklist 機制，用 60 秒延遲換零架構複雜度；Phase 3 才引入雙索引，成本增至約 $783/月，但換來零停機與 RECALL@10 長期穩定在 93% ± 2%。最關鍵的風險不是索引速度，而是 HNSW Graph Drift 的靜默劣化——我們用 Golden Query Set 每 30 分鐘評估一次 RECALL@10，一旦下滑 5% 就自動觸發 Cloud Composer DAG 進行 Blue-Green Re-indexing，整個切換過程對用戶完全透明，停機時間為零。」*

---

## 十一、常見陷阱與生產事故分析

### 11.1 三個高頻踩坑場景

**陷阱一：Blacklist 清空時機過早**

最常見的事故模式是：夜間重建的 Airflow DAG 在 Green Index 建立完成後，立即清空了 Blacklist，但在 30 秒後才完成流量切換（更新 Endpoint）。在這 30 秒的空窗期內：

- 查詢仍然打到 Blue Index
- 但 Blacklist 已清空
- 導致已刪除文件的向量重新出現在搜尋結果中

**正確防護**：使用 Firestore Transaction 將「清空 Blacklist」和「更新 Endpoint 環境變數」打包成原子操作。若任一步驟失敗，整個 Transaction 回滾。

---

**陷阱二：Delta Index 向量版本衝突**

當同一份文件在 1 小時內被連續修改 3 次時，Delta Index 中可能同時存在同一 doc_id 的 3 個版本向量。Parallel Query 的合併邏輯如果不正確處理版本，三個版本都可能出現在 Top-K 結果中，讓 LLM 看到矛盾的知識片段。

**正確防護**：

```python
# 向量寫入時帶入版本號（使用 timestamp 毫秒）
vector_metadata = {
    "doc_id": doc_id,
    "version_ts": int(time.time() * 1000),  # 毫秒時間戳
    "chunk_index": chunk_idx
}

# 合併時以 (doc_id, chunk_index) 為 key 保留最新版本
def merge_and_deduplicate(base_results, delta_results):
    merged = {}
    for r in base_results + delta_results:
        key = (r.doc_id, r.chunk_index)
        if key not in merged or r.version_ts > merged[key].version_ts:
            merged[key] = r
    return sorted(merged.values(), key=lambda x: x.score, reverse=True)
```

---

**陷阱三：HNSW ef_search 參數未跟隨 Delta 大小調整**

Vertex AI Vector Search 的 `approximateNeighborsCount`（即 ef_search）參數決定 HNSW 圖在搜尋時探索的節點數。Delta Index 剛啟動時只有幾百個向量，ef_search=100 完全夠用；但當 Delta 增長至 90K 向量時，ef_search=100 會造成嚴重的鄰域搜尋不足，RECALL 大幅下滑。

**正確防護**：動態調整 ef_search，根據 Delta Index 當前向量數量設定：

| Delta 向量數 | 建議 ef_search | 預期 RECALL@10 |
|------------|--------------|--------------|
| < 10K | 50 | > 95% |
| 10K–50K | 100 | > 92% |
| 50K–80K | 150 | > 90% |
| > 80K | 觸發緊急 Rebalance | — |

---

### 11.2 生產事故 Post-Mortem 範例

**事故名稱**：2025-Q3 某企業客戶知識庫 RECALL 崩盤事件

**事故時間線**：

```
09:00  客戶批量上傳 8,000 份新法規 PDF（觸發大量 Embed 任務）
09:05  Cloud Dataflow 因 Gecko API QPS 超限（429 錯誤），部分任務失敗並重試
09:30  重試機制累積，Delta Index 中存在大量重複向量（同一 chunk 寫入 3–5 次）
11:00  Delta Index 向量數衝破 80K 監控門檻，觸發緊急 Rebalance
11:05  但 Rebalance DAG 未正確去重，將重複向量也合併入 Green Index
11:30  Green Index 通過 RECALL 驗證（Golden Query Set 不包含法規類 query，盲點）
12:00  流量切換完成，但 Agent 開始回傳重複且混亂的法規條文，客戶大規模投訴
13:30  值班工程師手動回滾至 Blue Index，事故解除
```

**Root Cause**：Dataflow 重試機制 + Delta Index 去重邏輯缺失 + Golden Query Set 覆蓋率不足（只有 0.3%）。

**改善措施**：

1. Dataflow 增加冪等寫入（Idempotent Upsert），以 `(doc_id, chunk_index, content_hash)` 三聯鍵去重
2. Golden Query Set 擴充至涵蓋所有一級文件分類，覆蓋率從 0.3% 提升至 3.5%
3. 新增 Delta Index 向量去重率監控，超過 20% 重複率立即告警

---

## 十二、成本優化策略與規模化路徑

### 12.1 分階段成本拆解

在邁向百萬向量規模的過程中，成本的主要驅動因素會隨著規模改變：

```
┌────────────────────────────────────────────────────────────┐
│                  成本驅動因素演進圖                           │
│                                                            │
│  10K 文件：                                                 │
│  Embedding API 費用 ≈ $0.025/1K tokens                     │
│  主要成本：Cloud Run 運算（$30/月）                          │
│                                                            │
│  100K 文件：                                                │
│  向量索引儲存費用開始顯著                                     │
│  主要成本：Vector Search 儲存（$50–120/月）                  │
│                                                            │
│  1M 向量：                                                  │
│  Dataflow 持續運算 + Composer + 雙索引儲存                   │
│  主要成本：基礎設施固定成本（$600+/月）                       │
│                                                            │
│  成本優化轉折點：每日更新量超過 5K 文件後，                   │
│  Dataflow 的背壓機制效益開始超越成本，                        │
│  比起 Cloud Run 多次重試，Dataflow 反而更省錢                 │
└────────────────────────────────────────────────────────────┘
```

### 12.2 三個高效成本優化手段

**優化一：Embedding 快取**

如果同一份文件被多次刪除再新增（例如：修正格式後重傳），應避免重複 Embed 相同內容。使用 `content_hash`（SHA-256）作為 Embedding 快取 key，命中率通常可達 **15–30%**，直接節省對應比例的 Gecko API 費用。

```python
def embed_with_cache(chunks: List[str]) -> List[np.ndarray]:
    results = []
    for chunk in chunks:
        cache_key = hashlib.sha256(chunk.encode()).hexdigest()
        cached = memorystore.get(cache_key)  # Cloud Memorystore (Redis)
        if cached:
            results.append(cached)
        else:
            embedding = gecko_api.embed(chunk)
            memorystore.set(cache_key, embedding, ttl=86400)  # 24 小時 TTL
            results.append(embedding)
    return results
```

**優化二：Delta Index 定期 Compaction（不等到夜間）**

若某日白天有爆發性更新（> 50K 新向量），可在中午 12 點額外觸發一次 Partial Compaction，只合併 Delta 而不重建整個 Base，耗時約 15 分鐘（vs 夜間完整重建的 2.5 小時），Dataflow 費用約 $3/次。這樣可避免 Delta Index 超過 80K 閾值觸發緊急 Rebalance（緊急重建成本高 5 倍）。

**優化三：冷熱向量分層**

超過 180 天未被任何查詢命中的向量，可以標記為「冷向量」，從 Base Index 移出，存入 Cloud Storage（GCS）作為壓縮向量備份。僅在用戶明確要求搜尋歷史文件時，才按需載入。100 萬向量中通常有 **20–35%** 是冷向量，這個策略可以節省約 $50–70/月的向量儲存費用。

### 12.3 規模化時的架構變更

當系統規模超過 1M 向量（即 Phase 3 的上限）時，需要考慮：

| 規模 | 新增需求 | 建議方案 |
|------|---------|---------|
| 1M–5M 向量 | Base Index 單一節點查詢延遲上升 | 啟用 Vertex AI Vector Search 多副本（Replicas: 3） |
| 5M–20M 向量 | 單一 Base Index 超出容量限制 | 按文件類別分片（Sharding），每個 Shard 獨立 Base + Delta |
| 20M+ 向量 | 跨 Shard 查詢協調複雜度 | 引入 Router 層，按 query 語意路由至對應 Shard |

**Sharding 策略建議**：

不要按照文件 ID 雜湊分片（會讓語意相近的文件分散在不同 Shard，查詢時需要廣播到所有 Shard）。應按照**文件語意類別**分片（例如：法規類、產品類、技術類），使得 90% 的查詢只需打 1–2 個 Shard，而非全廣播。

---

## 十三、系列回顧：FDE Interview Guide 知識地圖

本篇是 FDE Interview Guide 系列的第 49 篇。系列涵蓋的核心主題已超過 45 個生產級架構設計問題，從 Phase 1 快速驗證到 Phase 3 百萬用戶規模，每篇都提供具體數字、Why-X-not-Y 決策框架，以及面試可直接使用的 RKK 模型答案。

本篇的核心貢獻：

- **Lambda Vector Architecture** 的完整三階段演進路徑，帶具體成本數字
- **HNSW Graph Drift** 的量化監控方法（RECALL@10 + Golden Query Set）
- **Blue-Green Index Deployment** 的零停機切換詳細時序
- **Firestore Blacklist** 的生命週期管理與競態條件防護
- **三個生產陷阱**的成因分析與防護模式

---

**系列導航**

← [Part 48：RAG 系統的多路召回與重排序架構](/posts/fde-interview-guide-part48-rag-multi-recall-rerank-zh/) | [Part 50：Agent 工具呼叫的容錯與冪等設計](/posts/fde-interview-guide-part50-agent-tool-idempotency-zh/) →
