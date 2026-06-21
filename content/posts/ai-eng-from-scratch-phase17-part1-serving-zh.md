---
title: "AI 工程從零開始｜Phase 17 Part 1：AI 推論服務架構 — 從單機到全球部署"
date: 2026-06-22T02:30:00+08:00
draft: false
weight: 36
description: "深入解析 AI 推論服務工程：模型服務器選型（Triton/TorchServe/vLLM）、負載均衡、自動擴縮容、GPU 共享與多租戶隔離架構"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Infrastructure", "Serving", "Triton", "GPU", "Kubernetes", "Production", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人：把 `torch.load()` 包一層 Flask，貼上 `/predict` 就叫「部署」。*
> *真正的做法：從服務框架選型、GPU 共享策略、冷啟動預熱到多租戶隔離，每一層都有可量測的 SLO。*
> *差距不在演算法，而在系統設計——單機 GPU 使用率 23% vs 叢集使用率 78%，成本相差 3.4 倍。*
> *本文從 POC 到全球部署，逐層拆解 AI 推論服務的工程決策。*

---

## 面試情境

> 你的電商平台每天有 500 萬次商品推薦請求，目前用一台 A100 跑 PyTorch 模型，P99 延遲 1.2s，GPU 使用率只有 23%。CTO 說三個月後要支援 10 倍流量，同時把 P99 壓到 200ms 以內，預算只能增加 2 倍。你會如何重新設計推論服務架構？請解釋你在服務框架選型、擴縮容策略、GPU 共享、以及多租戶隔離四個面向的決策依據。

---

## 一、核心問題：AI 推論服務與傳統 Web 服務的本質差異

AI 推論服務並不是「把模型包一個 HTTP 端點」這麼簡單。它在資源模型、延遲特性、擴縮容行為上，與傳統 Web 服務有根本性差異。

**資源模型的差異**

傳統 Web 服務以 CPU 為主，水平擴展幾乎無代價——增加一台虛擬機需要 30 秒，成本線性增加。AI 推論服務以 GPU 為主，GPU 節點冷啟動需要 45–120 秒（含驅動初始化、CUDA context 建立、模型載入），每台 A100 機器成本約 $3–6/hour，是 CPU 機器的 15–30 倍。

**延遲特性的差異**

Web API 的 P99 延遲通常在 50–200ms 之間，主要瓶頸是 I/O（資料庫查詢、網路呼叫）。AI 推論的延遲受模型大小、Batch Size、精度（FP32/FP16/INT8）決定：

- ResNet-50 on A100：FP16，Batch=32 → 3ms/request
- BERT-large on A100：FP16，Batch=8 → 28ms/request
- GPT-2（1.5B）on A100：FP16，Batch=1 → 85ms/request，Batch=8 → 220ms/request

延遲與吞吐量存在根本性衝突：增大 Batch Size 可以提升 GPU 使用率與整體吞吐，但會增加個別請求的等待時間（Queue Time）。

**擴縮容行為的差異**

Web 服務可以在 10–30 秒內新增一個 Pod（容器），GPU Pod 需要：

1. 節點 Provisioning（若使用 Auto Scaling）：60–300 秒
2. 容器映像拉取（若模型打包在映像內）：30–120 秒（10GB 映像）
3. 模型載入到 GPU 記憶體：5–60 秒（視模型大小）
4. Warm-up 推論（JIT 編譯、CUDA kernel 初始化）：10–30 秒

**合計冷啟動時間：2–8 分鐘**。這意味著傳統的「請求高峰來了再擴容」策略完全失效，必須使用預測性擴縮容（Predictive Autoscaling）。

**多模型管理的複雜度**

一個成熟的 AI 平台通常同時運行 50–200 個模型版本（不同業務場景、A/B 測試版本、多語言模型）。若每個模型占一台 GPU，成本不可接受；若讓多個模型共享一台 GPU，需要解決記憶體分配、隔離、排程三個問題。

---

## 二、三個演進階段（POC/MVP/Scale）

### Phase 1：POC / 單機（< 10K 日活）

**目標**：快速驗證模型效果，不要過度工程化。

```
┌─────────────────────────────────────────────┐
│              Flask / FastAPI                │
│              /predict endpoint              │
└─────────────────┬───────────────────────────┘
                  │  HTTP
                  ▼
┌─────────────────────────────────────────────┐
│         PyTorch / TensorFlow Model          │
│         單一 GPU（V100 16GB）               │
│         GPU 使用率：23%                     │
│         P99 延遲：1.2s                      │
└─────────────────────────────────────────────┘
```

**新增組件**：Flask + 裸 PyTorch，無佇列，無批次處理。
**成本**：$2.4/hour（1× V100 on-demand）
**解決了什麼**：模型可以對外提供服務。
**留下了什麼問題**：無法水平擴展、冷啟動慢、GPU 嚴重低使用率、無監控。

---

### Phase 2：MVP / 小叢集（10K–200K 日活）

**目標**：達到生產可用的 SLO，讓團隊不需要半夜救火。

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                           │
│                                                                 │
│  ┌─────────────┐     ┌─────────────────────────────────────┐   │
│  │   Ingress   │────▶│         Triton Inference Server     │   │
│  │  (NGINX)    │     │   (Deployment: 3 replicas)          │   │
│  └─────────────┘     │   GPU: 3× A10G 24GB                 │   │
│                      │   動態批次：on                       │   │
│                      │   GPU 使用率：55%                    │   │
│                      │   P99 延遲：320ms                    │   │
│                      └────────────────┬────────────────────┘   │
│                                       │                        │
│  ┌─────────────────────────────────┐  │                        │
│  │     Model Repository (S3)       │◀─┘ 模型熱載入             │
│  │     v1.0, v1.1, v2.0-shadow     │                          │
│  └─────────────────────────────────┘                          │
│                                                                 │
│  ┌─────────────┐     ┌─────────────────────────────────────┐   │
│  │ Prometheus  │────▶│          Grafana Dashboard          │   │
│  │  + DCGM     │     │  GPU 使用率、延遲、佇列深度          │   │
│  └─────────────┘     └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**新增組件**：Triton Inference Server、Kubernetes Deployment、動態批次（Dynamic Batching）、Prometheus + DCGM 監控、S3 模型儲存庫。
**成本**：$12/hour（3× A10G on-demand）→ 每日活躍用戶成本降至 1/3。
**解決了什麼**：水平擴展、動態批次、模型版本管理、基礎監控。
**留下了什麼問題**：冷啟動仍需 45 秒、無法應對突發流量、多模型共用 GPU 記憶體管理粗糙。

---

### Phase 3：Scale / 全球叢集（200K–1M+ 日活）

**目標**：企業級，自動擴縮容，成本最優，P99 < 200ms 全球可用。

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Global Load Balancer (Anycast)                     │
└────────────────────┬──────────────────────────┬────────────────────────┘
                     │                          │
         ┌───────────▼──────────┐   ┌───────────▼──────────┐
         │   Region: US-East    │   │   Region: AP-Tokyo   │
         │  ┌────────────────┐  │   │  ┌────────────────┐  │
         │  │  Istio Gateway │  │   │  │  Istio Gateway │  │
         │  └───────┬────────┘  │   │  └───────┬────────┘  │
         │          │           │   │          │           │
         │  ┌───────▼────────┐  │   │  ┌───────▼────────┐  │
         │  │ Triton Cluster │  │   │  │ Triton Cluster │  │
         │  │ 8× A100 80GB   │  │   │  │ 4× A100 80GB   │  │
         │  │ MIG 7 slices   │  │   │  │ MIG 7 slices   │  │
         │  │ 使用率：78%    │  │   │  │ 使用率：74%    │  │
         │  └───────┬────────┘  │   │  └───────┬────────┘  │
         │          │           │   │          │           │
         │  ┌───────▼────────┐  │   │  ┌───────▼────────┐  │
         │  │ KEDA + HPA     │  │   │  │ KEDA + HPA     │  │
         │  │ 預測性擴縮容   │  │   │  │ 預測性擴縮容   │  │
         │  └────────────────┘  │   │  └────────────────┘  │
         └──────────────────────┘   └──────────────────────┘
                     │                          │
         ┌───────────▼──────────────────────────▼───────────┐
         │              Shared Model Registry                │
         │         (Object Storage + CDN 預熱)               │
         │    模型快取命中率：94%，載入時間：8s vs 原 45s   │
         └───────────────────────────────────────────────────┘
```

**新增組件**：全球 Anycast 路由、Istio Service Mesh、A100 MIG（Multi-Instance GPU）、KEDA（事件驅動自動擴縮容）、CDN 模型預熱、跨區域複製。
**成本**：$58/hour（12× A100，含 Reserved Instance 折扣 30%）→ GPU 使用率 78%，有效算力成本降至 Phase 1 的 29%。
**解決了什麼**：冷啟動從 45s → 8s（CDN 預熱）、全球 P99 < 180ms、GPU 使用率 78%、多租戶隔離。

---

## 三、模型服務框架：Triton vs TorchServe vs vLLM

選擇服務框架是 AI 推論架構最關鍵的決策之一。三個主流選項各有適用場景。

```
┌──────────────────────────────────────────────────────────────────────┐
│                    模型服務框架能力對比                               │
├──────────────────┬──────────────────┬──────────────────┬─────────────┤
│    能力維度      │      Triton      │   TorchServe     │    vLLM     │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  支援框架        │ TF/PT/ONNX/      │ PyTorch Only     │ PyTorch     │
│                  │ TensorRT/Custom  │                  │ (LLM 專用)  │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  動態批次        │ ✓ 原生支援       │ ✓ 原生支援       │ ✓ 連續批次  │
│                  │ 精細控制         │ 較簡單           │ PagedAttn   │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  多模型共用      │ ✓ Model          │ ✓ Multi-Model    │ ✗ 單模型    │
│  GPU             │   Repository     │   Server         │   優化      │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  推論吞吐        │ ResNet50:        │ ResNet50:        │ Llama-7B:   │
│  （A100 80GB）   │ 18,000 req/s     │ 12,000 req/s     │ 2,400 tok/s │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  延遲（P99）     │ ResNet50:        │ ResNet50:        │ Llama-7B    │
│                  │ 4ms              │ 8ms              │ first token │
│                  │                  │                  │ 280ms       │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  Ensemble        │ ✓ Pipeline 編排  │ ✗               │ ✗           │
│  Pipeline        │ 內建 DAG 執行    │                  │             │
├──────────────────┼──────────────────┼──────────────────┼─────────────┤
│  運維複雜度      │ 高（需要         │ 中（PyTorch     │ 低（專注    │
│                  │  配置 backend）  │  生態友好）      │  LLM 場景） │
└──────────────────┴──────────────────┴──────────────────┴─────────────┘
```

**Triton Inference Server（推薦用於多模型異構場景）**

Triton 最強的能力是 Ensemble Pipeline——可以把前處理、推論、後處理串成 DAG，在 GPU 端做 zero-copy 傳遞，避免每個步驟都走 CPU 序列化。對於需要同時服務 ResNet、BERT、XGBoost 等不同框架模型的平台，Triton 的 Model Repository 配合 Dynamic Batching 是最佳選擇。

典型配置下，Triton 的動態批次可以在 1–5ms 的等待視窗內聚合請求，將 GPU 使用率從 23% 提升至 68%，吞吐量提升 3.2 倍，而 P99 延遲只增加 12ms。

**TorchServe（推薦用於純 PyTorch 快速上線）**

若團隊全部使用 PyTorch，TorchServe 的開發體驗更友好：自定義 handler 只需繼承 `BaseHandler`，模型打包用 `torch-model-archiver`，版本管理 API 開箱即用。缺點是跨框架支援弱，Ensemble Pipeline 需要自行實現。

**vLLM（推薦用於 LLM 生成式 AI 服務）**

vLLM 的核心創新是 PagedAttention：將 KV Cache 分頁管理，消除 LLM 推論中因 KV Cache 碎片化導致的 GPU 記憶體浪費（傳統方式浪費 60–80% KV Cache 記憶體）。在 Llama-7B 場景下，vLLM vs 原始 HuggingFace Inference：

- 吞吐量：2,400 tok/s vs 320 tok/s（7.5 倍提升）
- GPU 記憶體利用率：82% vs 34%
- 支援並發請求數：128 vs 8

---

## 四、負載均衡策略：AI 工作負載的特殊考量

AI 推論服務的負載均衡不能直接套用傳統 Round-Robin 或 Least-Connections，原因在於：

**1. 請求體積差異巨大**

一個圖片分類請求的 payload 可能是 50KB，一個文件摘要請求可能是 2MB。Least-Connections 只計算連接數，不考慮每個請求的 GPU 計算量。更好的策略是「最少待處理 Token」（Least Pending Tokens）或「最低佇列深度」（Least Queue Depth）。

**2. GPU 記憶體是硬性限制**

當一個 GPU 節點的記憶體即將耗盡，新請求應該路由到其他節點，而不是繼續送進去導致 OOM（Out-of-Memory）崩潰。負載均衡器需要感知每個節點的 GPU 記憶體使用量（透過 DCGM 指標）。

**3. 模型版本的親和性**

若節點 A 已經載入 v2.1 模型，節點 B 只有 v2.0，將 v2.1 的請求路由到節點 A 可以避免動態載入延遲（節省 5–15 秒）。這需要帶有「模型版本標籤」的親和性路由。

**4. 批次對齊的最佳化**

動態批次效果最好時，需要同類型請求聚集在同一個節點。圖片分類和文本分類的最佳 Batch Size 不同（前者 32，後者 8），混合路由會降低批次效率。

**實作方案：加權最少連接 + 健康感知路由**

```
請求進來 → L7 負載均衡（Envoy/Istio）
  ├── 讀取後端節點指標（DCGM via Prometheus）：
  │   ├── GPU 記憶體使用率
  │   ├── 佇列深度（Pending Requests）
  │   └── 已載入模型版本
  ├── 計算路由分數 = (1 - GPU Mem %) × (1 / Queue Depth) × Version Match Bonus
  └── 選擇分數最高的節點
```

這套策略在 200K DAU 場景下，相比純 Round-Robin，P99 延遲降低 31%，GPU OOM 事件從每天 12 次 → 0 次。

---

## 五、自動擴縮容：GPU 節點的冷啟動與預熱

GPU 節點的冷啟動問題是 AI 推論服務擴縮容的核心挑戰。

```
┌─────────────────────────────────────────────────────────────────────┐
│                   GPU 節點冷啟動時間線                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  傳統方式（無預熱）：                                               │
│  ├── 節點 Provision（Auto Scaling）：60–180s                        │
│  ├── 容器映像拉取（10GB 模型映像）：30–120s                         │
│  ├── 模型從 S3 載入 GPU 記憶體：15–45s                              │
│  └── Warm-up 推論（JIT/CUDA 初始化）：10–30s                        │
│  ════════════════════════════════════════                           │
│  合計：115–375s（平均 ~240s）                                       │
│                                                                     │
│  最佳化後（CDN 預熱 + 節點預留）：                                  │
│  ├── 節點已預留（Warm Pool）：0s                                    │
│  ├── 容器映像已快取於節點：0s                                       │
│  ├── 模型從本地 NVMe 快取載入：5–8s                                 │
│  └── Warm-up 推論：2–3s                                             │
│  ════════════════════════════════════════                           │
│  合計：7–11s（平均 ~8s）                                            │
│                                                                     │
│  冷啟動改善：45s（Phase 2 基準）→ 8s（Phase 3 最佳化）             │
└─────────────────────────────────────────────────────────────────────┘
```

**KEDA（Kubernetes Event-Driven Autoscaling）配置**

KEDA 允許基於自定義指標（如 GPU 佇列深度、每秒請求數）觸發 HPA，而不只是 CPU/記憶體：

```yaml
# ScaledObject 配置示意（非完整 YAML）
triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: triton_pending_request_count
      threshold: "50"          # 佇列深度超過 50 就開始擴容
      query: sum(triton_pending_request_count{model="recommend_v2"})
```

**預測性擴縮容（Predictive Autoscaling）**

對於有規律流量模式的服務（如電商推薦，每晚 8–10pm 高峰），可以用時間序列預測（Prophet/LSTM）提前 15–20 分鐘開始擴容，避免高峰時才觸發冷啟動：

- 預測準確度（MAPE）：< 12%，足以在流量高峰前 15 分鐘準備好足夠節點
- 成本影響：提前擴容多花 8% 費用，但避免了 P99 在高峰前 5 分鐘飆升至 5s+ 的體驗損失

**Warm Pool 節點預留策略**

始終保持 N 個「預熱就緒」的 GPU 節點：
- 已拉取容器映像
- 已載入常用模型到 GPU 記憶體
- 未處理請求（閒置中）

成本：多花 20–30% GPU 費用，但 P99 冷啟動延遲降至 < 10s（vs 原本 4 分鐘）。對於 P99 < 200ms 的 SLO，這是必要投資。

---

## 六、GPU 共享：MIG/MPS/時間片的工程取捨

單一 A100 80GB GPU 跑一個小模型（1GB）是嚴重浪費。GPU 共享技術允許多個工作負載共用一個 GPU，但方式不同，取捨各異。

**MIG（Multi-Instance GPU）**

NVIDIA A100/H100 支援 MIG，可以把一個 GPU 切成最多 7 個獨立的「mini GPU」，每個有獨立的計算引擎、記憶體、快取，完全硬體隔離：

- 1× A100 80GB → 7× MIG 1g.10gb（每個有 10GB 顯存）
- 或 → 3× MIG 2g.20gb（每個有 20GB 顯存）+ 1× 1g.10gb

適用場景：多租戶 SaaS，需要嚴格的效能隔離（一個租戶的工作負載不能影響另一個）。  
限制：MIG 配置在運行時不能動態調整，需要排空該 GPU 才能重新切分；不支援 NVLink 跨 GPU 通訊。

**MPS（Multi-Process Service）**

MPS 允許多個 CUDA 應用共享同一個 GPU，透過一個共享的 CUDA Context 序列化 kernel 提交，減少 context switch 開銷：

- GPU 使用率提升：從 23% → 61%（4 個小模型共用，各原本 23%）
- 記憶體隔離：無（任一程序崩潰可能影響其他程序）
- 效能干擾：輕度（< 5% throughput 下降）

適用場景：內部服務，信任邊界內，多個推論 Worker 共用同一 GPU。不適合多租戶 SaaS（安全邊界不足）。

**時間片（Time-Slicing）**

最簡單的共享方式：Kubernetes GPU Time-slicing 讓多個 Pod 共享一個 GPU，透過時間片輪流使用：

- 配置簡單，Kubernetes 內建支援
- 無記憶體隔離（所有 Pod 看到相同顯存上限，但實際共用）
- 效能最差：context switch 開銷 8–12%，不適合延遲敏感場景

適用場景：開發/測試環境，或對延遲不敏感的離線批次推論。

**選擇決策樹**

- 多租戶 SaaS，需要 SLA 保證 → **MIG**
- 同一業務單元，多個模型，信任環境 → **MPS**
- 開發環境，低成本為主 → **Time-Slicing**

---

## 七、多租戶隔離：成本分攤與安全邊界

當 AI 推論平台服務多個業務部門或外部客戶時，需要在三個層面建立隔離：

**計算隔離**

使用 Kubernetes Namespace + Resource Quota 劃定每個租戶的 GPU 資源上限：
- 每個租戶有獨立的 Namespace
- ResourceQuota 限制 `nvidia.com/gpu` 使用量
- 配合 MIG，確保一個租戶的推論不影響另一個的延遲

**網路隔離**

Istio NetworkPolicy 確保租戶 A 的 Pod 無法直接呼叫租戶 B 的 Model Server。所有跨租戶流量必須經過 API Gateway（統一認證、限流）。

**成本分攤（Showback/Chargeback）**

DCGM 指標收集每個 Pod 的 GPU 時間使用量，配合 Kubernetes Cost Allocation（如 Kubecost）：

- 每小時計算：`GPU 時間使用率 × GPU 節點成本 × 使用比例`
- 精確度：誤差 < 5%（vs 按節點數分攤的 30–40% 誤差）
- 典型結果：電商推薦部門佔 45% GPU 費用，NLP 搜尋佔 30%，電腦視覺佔 25%

**模型版本安全邊界**

多租戶環境下，模型儲存庫的存取控制至關重要：
- 每個租戶只能存取自己的模型版本
- 使用 IAM Role（而非 Access Key）綁定 Pod SA，最小權限原則
- 模型加密（AES-256）存放於 Object Storage，防止橫向移動

---

## 八、為什麼選 X 不選 Y

### 決策 1：Triton vs TorchServe

| 選擇 | 選 Triton 的理由 | 不選 TorchServe 的理由 |
|------|-----------------|----------------------|
| 服務框架 | 支援 TF/ONNX/TensorRT/Custom，Ensemble Pipeline 原生 DAG | 只支援 PyTorch；Ensemble 需自行實現 |
| 多模型共用 | Model Repository 熱載入，無需重啟 | 跨框架模型共存複雜 |
| 效能 | ResNet50 18,000 req/s；P99 4ms | ResNet50 12,000 req/s；P99 8ms |
| 生產可靠性 | NVIDIA 原生維護，與 CUDA/TensorRT 深度整合 | Facebook 主導，PyTorch 生態強但非 GPU 廠商 |

**Flip Condition**：若團隊 100% PyTorch 且沒有 Ensemble Pipeline 需求，TorchServe 的開發體驗更友好（handler 撰寫更直覺），應選 TorchServe。

---

### 決策 2：vLLM vs Triton（LLM 服務）

| 選擇 | 選 vLLM 的理由 | 不選 Triton 的理由 |
|------|---------------|------------------|
| LLM 推論 | PagedAttention 消除 KV Cache 碎片，記憶體利用率 82% vs 34% | Triton 無內建 PagedAttention；需自行整合 |
| 吞吐量 | Llama-7B 2,400 tok/s vs HF 原生 320 tok/s（7.5×） | Triton 做 LLM 需額外配置 FasterTransformer backend |
| 連續批次 | Continuous Batching 原生支援，動態合併流式請求 | Triton 動態批次對 variable-length LLM 效果差 |
| 運維簡單 | 一個 Docker 映像搞定 LLM 服務 | Triton 配置複雜（config.pbtxt，多 backend） |

**Flip Condition**：若需要在同一個節點同時服務 LLM + CNN + 傳統 ML 模型（混合工作負載），Triton 的多框架能力優先，vLLM 作為 Triton 的 Custom Backend 整合。

---

### 決策 3：MIG vs MPS（GPU 共享）

| 選擇 | 選 MIG 的理由 | 不選 MPS 的理由 |
|------|-------------|---------------|
| 多租戶 SaaS | 硬體級隔離，一個租戶 OOM 不影響其他人 | MPS 共享 CUDA Context，崩潰可能連帶 |
| SLA 保證 | MIG slice 有獨立 SM、L2 Cache，效能可預測 | MPS 共享快取，高負載時互相干擾 |
| 安全邊界 | 符合 SOC2/ISO27001 的硬體隔離要求 | MPS 記憶體空間未隔離，不符合合規要求 |
| 計量計費 | 每個 MIG slice 獨立計費，精確 Chargeback | MPS 需額外 profiling 才能分攤成本 |

**Flip Condition**：若是內部平台（同一信任域），且工作負載都是延遲敏感型小模型（< 2GB），MPS 的效能（更少切換開銷）和靈活性（動態分配）優於 MIG。

---

### 決策 4：KEDA vs HPA（自動擴縮容）

| 選擇 | 選 KEDA 的理由 | 不選純 HPA 的理由 |
|------|--------------|----------------|
| 指標來源 | 支援 Prometheus/SQS/Kafka 等 50+ 事件源 | HPA 原生只支援 CPU/Memory，需額外 Custom Metrics Adapter |
| 佇列深度觸發 | 可直接基於 `triton_pending_request_count` 擴容 | HPA 感知佇列深度需要 Prometheus Adapter 額外配置 |
| Scale-to-Zero | 支援縮容至 0（離峰省成本） | HPA 最小值通常設 1，無法真正 Scale-to-Zero |
| 預熱感知 | 結合 Warm Pool 可實現預測性擴容 | HPA 是反應式，無預測能力 |

**Flip Condition**：若叢集規模小（< 5 個 GPU 節點）且流量模式簡單，標準 HPA + Custom Metrics 已足夠，KEDA 的額外運維複雜度不值得。

---

### 決策 5：S3 + CDN 模型快取 vs 模型打包進容器映像

| 選擇 | 選 S3+CDN 的理由 | 不選打包進映像的理由 |
|------|----------------|-------------------|
| 冷啟動速度 | CDN edge 快取命中率 94%，載入 8s vs 映像拉取 45–120s | 映像大（含 10GB 模型），拉取耗時 |
| 版本更新 | 模型更新只需上傳 S3，不需重建映像 | 每次模型更新都要重建並推送 10GB+ 映像 |
| 儲存成本 | S3 $0.023/GB/月；僅儲存模型本身 | Container Registry 儲存多版本映像成本 3–5× |
| A/B 測試 | 同一映像可動態切換載入 v1.0 或 v2.0 | 需要兩個不同映像標籤，調度更複雜 |

**Flip Condition**：若模型極小（< 500MB，如輕量 embedding 模型），且 CI/CD 流程已整合模型訓練，打包進映像可以簡化部署流程，不必額外維護 S3 版本管理。

---

### 決策 6：Istio Service Mesh vs 純 NGINX 負載均衡

| 選擇 | 選 Istio 的理由 | 不選純 NGINX 的理由 |
|------|--------------|-------------------|
| 流量觀測 | 自動 distributed tracing（Jaeger），無需改動應用代碼 | NGINX 需要手動埋點或 OpenTelemetry SDK |
| 細粒度路由 | 支援 Header-based routing（模型版本親和性）、Weight-based A/B | NGINX upstream 設定較靜態 |
| mTLS | 服務間通訊自動加密，零代碼改動 | NGINX 需手動配置 SSL Termination，維運複雜 |
| 限流熔斷 | Envoy 內建 Circuit Breaker、Rate Limiting | NGINX 限流功能有限，複雜策略需要 Lua 插件 |

**Flip Condition**：小型部署（< 10 個服務，< 3 個 GPU 節點），Istio 的 control plane 資源消耗（~1 CPU, 1.5GB RAM per node sidecar）不划算，純 NGINX Ingress Controller 已足夠。

---

## 九、系統效應

| 指標 | Phase 1（單機 Flask）| Phase 2（Triton 叢集）| Phase 3（全球 Scale）|
|------|--------------------|-----------------------|---------------------|
| GPU 使用率 | 23% | 55% | 78% |
| P99 延遲 | 1,200ms | 320ms | 180ms |
| 每日最大 QPS | 58 | 820 | 8,500 |
| GPU 冷啟動時間 | 45s | 35s | 8s |
| 每 100 萬請求成本 | $4.12 | $1.46 | $0.68 |
| 月可用性 SLO | 95.2%（無 HA）| 99.5% | 99.95% |
| 模型部署時間 | 15 分鐘（手動）| 3 分鐘（CI/CD）| 90 秒（藍綠部署）|
| GPU OOM 事件（月）| 48 次 | 4 次 | 0 次 |
| 同時支援模型數量 | 1 | 12 | 200+ |
| 多租戶隔離 | 無 | Namespace 級別 | MIG 硬體級別 |

**成本效益分析**：從 Phase 1 到 Phase 3，雖然 GPU 數量從 1 台增加到 12 台（成本 12×），但每 100 萬請求的服務成本從 $4.12 降至 $0.68（降低 83%），吞吐量提升 146 倍。這是 GPU 使用率從 23% → 78% 帶來的複利效應：相同的 GPU 資源，透過批次、共享、擴縮容最佳化，可以服務 3.4 倍的請求量。

---

## 十、面試答題要點

> *「我會分三個階段推進。Phase 1（現況 POC）先確診問題：GPU 使用率 23% 的根本原因是缺乏動態批次和請求聚合，而不是硬體不足；Phase 2（MVP，預算 2×）換用 Triton Inference Server 啟用 Dynamic Batching，配合 KEDA 基於佇列深度的自動擴縮容，預計 GPU 使用率從 23% 提升至 55–60%，P99 從 1.2s 降至 320ms，3 台 A10G 即可覆蓋 3× 流量增長；Phase 3（Scale，3 個月目標）加入 A100 MIG 切片以提升多模型共用效率、CDN 模型快取將冷啟動從 45s 壓到 8s、Istio 實現模型版本親和性路由，最終在預算 2× 的前提下支撐 10× 流量，P99 達到 180ms。最關鍵的 Why-X-not-Y 決策是選 Triton 而非 TorchServe：因為我們有多框架模型（PyTorch 推薦 + ONNX 精排 + TensorRT 圖像），Triton 的 Ensemble Pipeline 可以做 zero-copy 串接，單次請求端到端延遲比每步驟獨立服務節省 35–40ms。」*

---

## 十一、系列導航

← [Phase 16 Part 2：AI 訓練平台的分散式儲存與資料管線](/posts/ai-eng-from-scratch-phase16-part2-storage-zh/)

→ [Phase 17 Part 2：AI 推論服務的可觀測性與成本最佳化](/posts/ai-eng-from-scratch-phase17-part2-observability-zh/)

---

*本文為「AI 工程從零開始」系列第 17 階段第 1 篇，聚焦 AI 推論服務的工程架構設計。歡迎在下方留言分享你的實際部署經驗。*
