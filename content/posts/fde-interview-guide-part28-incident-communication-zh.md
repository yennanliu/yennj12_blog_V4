---
title: "FDE 面試準備指南（二十八）：顧問實戰——生產事故診斷與客戶溝通語言"
date: 2026-06-04T20:00:00+08:00
draft: false
description: "以 Google FDE 顧問視角拆解 AI 系統生產事故的處理全流程：P95 延遲異常的診斷思路、不停機排查策略、如何在技術細節與客戶語言之間切換，以及事故後的信任重建框架"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Consultant", "Incident", "Debugging", "Observability", "GCP", "Vertex AI", "Interview", "Google", "RKK"]
authors: ["yen"]
readTime: "16 min"
---

> 技術問題，工程師能解。  
> 但客戶打電話來的時候，他不想聽技術。  
> 他想知道：這個問題嚴不嚴重？會影響我的業務嗎？你什麼時候能修好？  
> FDE 要能同時給工程師一個診斷計畫，給客戶一個聽得懂的答案。

---

## 面試情境

> **面試官：**「你的客戶在生產環境上部署了一個 RAG-based 問答 Agent。上線三週後，客戶的工程師傳訊息說：每天凌晨 2 點到 4 點，P95 延遲從平常的 800ms 跳到 4 秒，然後自己恢復正常。這個問題已經發生三天了，今天下午客戶的 CTO 要開檢討會。你怎麼處理？」

---

## 一、FDE 在這個場景中要做兩件事

```
事情 1：技術診斷
  ├── 找出根因假設（2 小時內）
  ├── 確認診斷路徑（不停機）
  └── 給工程師可執行的排查步驟

事情 2：客戶溝通
  ├── 在 CTO 會議前準備好說法
  ├── 用業務語言描述問題嚴重性
  └── 給出有承諾的 Next Step（不是「我們在看」）

兩件事要同時跑。不能只顧技術，忘了客戶在等；
也不能只顧安撫客戶，卻說不出診斷計畫。
```

---

## 二、技術診斷：系統化的假設樹

看到「特定時間窗延遲飆高，自動恢復」這個 Pattern，要有一個系統化的思考框架：

```
延遲異常 Pattern 分類：

Pattern A：週期性（固定時間，固定症狀）
  → 最常見原因：排程任務衝突、快取過期、Token Refresh
  → 本題特徵符合：凌晨 2-4 點，每天發生

Pattern B：隨機性（不定時，難以復現）
  → 最常見原因：資源爭用、External API 不穩定

Pattern C：累積性（越用越慢，重啟恢復）
  → 最常見原因：記憶體洩漏、連線池耗盡
```

**本題是 Pattern A。先排查週期性原因。**

### 假設樹（針對 RAG Agent 凌晨延遲）

```
P95 延遲凌晨 2-4 點 → 4 秒（平常 800ms）

假設 1：向量資料庫維護窗口
  根據：許多託管 Vector DB（Pinecone, Vertex AI Vector Search）
         有排程的 Index 重建或壓縮作業
  症狀：查詢延遲增加，但不完全失敗
  確認方法：
    → 查 Vector DB 的 maintenance schedule 文件
    → 看 Pinecone / Vertex AI Dashboard 的 operation log

假設 2：Embedding Model 的 Cold Start
  根據：如果 Embedding 服務是 Cloud Run（auto-scaling to zero），
         凌晨流量低 → 實例縮到 0 → 第一個 request 觸發 cold start
  症狀：第一個 request 特別慢（10-30 秒），後續恢復
  確認方法：
    → Cloud Run metrics → instance count at 2am
    → 看 request log 裡有沒有 "cold start" 標記

假設 3：LLM API Rate Limit / Throttling
  根據：Vertex AI Gemini API 有 per-minute quota
         如果有批次任務在凌晨跑，可能會打到 quota 上限
  症狀：API 回應變慢，有 429 retry 的 backoff
  確認方法：
    → Cloud Monitoring → Vertex AI API → quota utilization
    → 看有沒有凌晨跑的 batch job（Cloud Scheduler / Dataflow）

假設 4：資料庫連線池耗盡
  根據：如果 RAG Pipeline 用 pgvector（Cloud SQL），
         可能有連線池的 max_connections 限制
  症狀：等待連線的佇列時間增加
  確認方法：
    → Cloud SQL Insights → active connections at 2am
    → 看有沒有凌晨的 ETL job 佔用大量連線

假設 5：網路層問題（VPC / CDN）
  根據：GCP 的某些區域有低流量時段的路由最佳化
  症狀：所有服務都慢，不只 AI 部分
  確認方法：
    → Cloud Trace → 哪個 span 的時間最長？
    → 如果是 LLM 之前的步驟（Embedding、Retrieval）就是下游問題
```

---

## 三、不停機的排查路徑

客戶的生產環境不能輕易重啟，這是 FDE 必須知道的排查原則：

```
診斷工具優先順序（從無侵入到有侵入）：

Level 1（完全無侵入）：讀現有 Log 和 Metrics
  → Cloud Logging：filter timestamp 2am-4am, 查 error / warning
  → Cloud Monitoring：看 Latency 分布的 percentile breakdown
  → Vertex AI Dashboard：看 model latency vs. total request latency

Level 2（低侵入）：調整 Log Verbosity
  → 把 Log level 暫時調到 DEBUG（只在非高峰期）
  → 增加 custom metrics：記錄每個 span 的耗時
    （Retrieval time / Embedding time / LLM generation time 分開記）

Level 3（有侵入）：加入 Tracing
  → 在 RAG Pipeline 每個步驟加入 Cloud Trace span
  → 找出是哪個步驟的延遲在凌晨增加

Level 4（重現問題）：在非生產環境模擬
  → 在 Staging 環境重跑凌晨的流量 Pattern
  → 這是最後手段，因為需要額外環境和時間
```

### 快速診斷腳本

```python
# 快速查 Cloud Logging，找凌晨的延遲分布
from google.cloud import logging_v2
from datetime import datetime, timedelta

client = logging_v2.Client()

# 查過去三天凌晨 2-4 點的 high latency log
filter_str = """
    resource.type="cloud_run_revision"
    timestamp >= "2026-06-01T18:00:00Z"
    timestamp <= "2026-06-04T20:00:00Z"
    httpRequest.latency > "2s"
    severity >= WARNING
"""

entries = client.list_entries(filter_=filter_str, order_by="timestamp asc")
for entry in entries:
    print(f"{entry.timestamp}: latency={entry.http_request.latency}, "
          f"url={entry.http_request.request_url}")
```

```bash
# 用 gcloud 快速查 Vertex AI API 的 quota 使用率
gcloud monitoring metrics list \
  --filter="metric.type:aiplatform.googleapis.com/prediction/request_count" \
  --start-time="2026-06-04T02:00:00+08:00" \
  --end-time="2026-06-04T04:00:00+08:00"
```

---

## 四、CTO 會議前：準備好你的說法

這是 FDE 最需要練習的轉換：**從技術語言切換到業務語言**。

### 不好的說法（讓 CTO 更擔心）

```
❌ 「我們發現 P95 延遲在 02:00-04:00 UTC+8 時段
    從 p50=450ms 上升至 p95=4200ms，
    我們懷疑是 Vector Search index compaction
    或 Cloud Run cold start 導致的 tail latency 問題，
    我們正在分析 trace data。」

問題：
├── CTO 不知道這嚴不嚴重
├── 「我們懷疑」讓人不安心
└── 沒有說對業務的影響
```

### 好的說法（讓 CTO 知道你在掌控）

```
✅ 「目前狀況：
    每天凌晨 2 到 4 點，約有 5% 的查詢回應時間
    超過 3 秒（正常是 1 秒以內）。
    這個時段是你們的業務低峰期，影響的使用者數量有限。
    問題在 4 點之後會自動恢復。

    我的判斷：
    這是一個週期性的效能問題，不是系統故障。
    問題有一個可預測的模式，這讓我們更容易找出根因。

    接下來 24 小時：
    我會確認三個假設（最可能的原因），
    明天同一時間我會盯著 metrics 看，今晚不需要有人值班。
    明天早上 10 點，我會給你們一個根因報告
    和一個修復計畫。

    如果問題在我找到根因前影響了白天的業務，
    我會立刻通知你。」
```

**說法的結構：**

```
1. 現在的情況是什麼（客觀描述，不誇大不縮小）
2. 對業務的實際影響有多大（幫他定錨）
3. 你的判斷（這是什麼類型的問題）
4. 接下來你要做什麼（具體的動作，有時間點）
5. 什麼情況下你會再次聯絡他（設定預期）
```

---

## 五、根因確認後：修復與預防

假設最終根因是 Cloud Run Cold Start：

```
短期修復（立刻做）：
  # 設定最小實例數，避免縮到 0
  gcloud run services update rag-embedding-service \
    --min-instances=1 \
    --region=asia-east1

  效果：Cold Start 問題消失
  代價：即使凌晨沒有流量，也有一個實例在跑
  成本影響：約 $X/月（要告知客戶，讓他們決定）

長期改善（下週做）：
  1. 加入 Warming Request（定時 ping 保持 warm）
  2. 設定 Scheduled Scaling（凌晨前提前 scale up）
  3. 加入 Latency Alerting（P95 > 2s 自動通知）

架構改善（下個 sprint）：
  把 Embedding 服務改為使用 Vertex AI 
  Prediction Endpoint（有內建的 auto-scaling
  和 min-replicas 控制，比 Cloud Run 更適合 AI 推論）
```

---

## 六、事故後的信任重建

事故解決了之後，FDE 有一件額外的工作：**讓這次事故變成加分項**。

```
事故後的動作：

1. 寫一份簡短的 Post-Mortem（1-2 頁）
   包含：
   ├── 發生了什麼（事實，不是解釋）
   ├── 為什麼發生（根因，不是藉口）
   ├── 我們做了什麼（已修復的）
   └── 我們接下來會做什麼（預防再次發生）

2. 把 Post-Mortem 分享給客戶工程師（不只是 CTO）
   → 讓工程師層面也理解這個問題
   → 建立技術信任

3. 用這次事故推動 Observability 改善
   「這次我們發現有一些監控是不夠的。
    我建議我們在這個系統上加入 X、Y、Z 的監控，
    這樣未來類似的問題可以在 5 分鐘內被 Alert 通知，
    而不是三天後才發現。」
   → 把事故轉化成客戶投資 observability 的動力
```

---

## 七、面試回答的完整示範

```
面試官期待聽到的結構：

「我會同時做兩件事：

技術面：
我的第一個假設是週期性原因——凌晨 2-4 點，每天規律發生，
這個 Pattern 最常見的是排程任務衝突（Index 重建、Batch job）
或服務的 Cold Start（Cloud Run 縮到 0 個實例）。

我會先看 Cloud Logging 和 Cloud Monitoring，
不需要改任何程式碼，先確認是哪個假設。
預計 2 小時內可以縮小範圍。

客戶面：
下午的 CTO 會議，我會先說清楚影響範圍——
這是低峰期問題，對業務的即時影響有限。
然後給他一個確定的承諾：明天早上 10 點，
我會給他根因報告和修復計畫。

FDE 的職責是讓客戶知道你在掌控局面，
而不是讓他跟你一起擔心。」
```

---

**事故的本質不是失敗，是信任的考驗。**  
**處理好了，是 FDE 最快建立客戶信任的機會。**
