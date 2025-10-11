---
title: "Kubernetes 完整指南（一）：基礎概念與架構詳解"
date: 2025-10-11T12:00:00+08:00
draft: false
description: "深入淺出介紹 Kubernetes 容器編排平台，涵蓋核心概念、架構設計、元件功能、與 Docker 的關係，以及完整的安裝配置教學。從零開始掌握 K8S 基礎知識。"
categories: ["Engineering", "DevOps", "Kubernetes", "all"]
tags: ["Kubernetes", "K8S", "容器編排", "雲原生", "微服務", "Docker", "DevOps", "叢集管理", "基礎教學"]
authors: ["yennj12 team"]
readTime: "60 min"
---

## 🎯 前言

Kubernetes（常簡稱為 K8s）是目前最流行的容器編排平台，已成為雲原生應用的事實標準。本系列文章將全面介紹 Kubernetes 的核心概念、實務操作與生產部署。

**本系列文章規劃：**
- **第一篇（本文）**：Kubernetes 基礎概念與架構
- **第二篇**：核心資源與實務操作
- **第三篇**：進階功能與生產實踐

## 📚 什麼是 Kubernetes？

### 核心定義

Kubernetes 是一個**開源的容器編排平台**，用於自動化部署、擴展和管理容器化應用程式。它最初由 Google 設計，現在由 Cloud Native Computing Foundation（CNCF）維護。

```mermaid
graph TB
    A[Kubernetes] --> B[容器編排]
    A --> C[自動化部署]
    A --> D[服務發現]
    A --> E[負載均衡]
    A --> F[自動擴展]
    A --> G[自我修復]

    B --> B1[管理數千個容器]
    C --> C1[滾動更新<br/>零停機部署]
    D --> D1[DNS 與服務註冊]
    E --> E1[流量分發<br/>健康檢查]
    F --> F1[水平/垂直擴展<br/>自動調度]
    G --> G1[故障恢復<br/>重啟容器]

    style A fill:#326ce5
    style B fill:#4ecdc4
    style C fill:#feca57
    style D fill:#ff6b6b
    style E fill:#a8e6cf
    style F fill:#ffb3ba
    style G fill:#bae1ff
```

### Kubernetes 解決的問題

| 挑戰 | 傳統方式 | Kubernetes 解決方案 |
|------|----------|---------------------|
| **容器管理** | 手動管理每個容器 | 聲明式配置，自動管理 |
| **服務發現** | 硬編碼 IP 位址 | 內建 DNS 與服務發現 |
| **負載均衡** | 外部負載均衡器 | 內建 Service 負載均衡 |
| **擴展性** | 手動添加實例 | 自動水平擴展（HPA） |
| **故障恢復** | 人工介入 | 自我修復，自動重啟 |
| **更新部署** | 停機維護 | 滾動更新，零停機 |
| **資源利用** | 低效分配 | 智慧調度，資源優化 |
| **配置管理** | 散落各處 | 統一的 ConfigMap/Secret |

## 🔄 為什麼需要 Kubernetes？

### 容器化的演進

```mermaid
graph LR
    A[單體應用<br/>Monolithic] --> B[容器化應用<br/>Containerized]
    B --> C[容器編排<br/>Orchestrated]
    C --> D[雲原生<br/>Cloud Native]

    A1[難以擴展<br/>部署緩慢] --> A
    B1[可移植<br/>環境一致] --> B
    C1[自動化<br/>高可用] --> C
    D1[微服務<br/>彈性伸縮] --> D

    style A fill:#ff6b6b
    style B fill:#feca57
    style C fill:#4ecdc4
    style D fill:#a8e6cf
```

### Docker vs Kubernetes

```mermaid
graph TB
    subgraph "Docker 生態"
        D1[Docker Engine]
        D2[容器運行]
        D3[映像管理]
        D4[Docker Compose<br/>單機編排]
    end

    subgraph "Kubernetes 生態"
        K1[容器編排]
        K2[叢集管理]
        K3[服務發現]
        K4[負載均衡]
        K5[自動擴展]
        K6[自我修復]
        K7[配置管理]
        K8[儲存編排]
    end

    D1 -.->|運行時| K1
    D3 -.->|映像| K1

    style D1 fill:#0db7ed
    style K1 fill:#326ce5
```

### 對照表

| 特性 | Docker | Docker Compose | Kubernetes |
|------|--------|----------------|------------|
| **適用範圍** | 單容器 | 單機多容器 | 叢集多容器 |
| **擴展性** | 手動 | 有限 | 自動（HPA） |
| **負載均衡** | 需外部 | 基本支援 | 內建 Service |
| **服務發現** | 手動配置 | 容器名稱 | DNS + Service |
| **故障恢復** | 手動 | 重啟策略 | 自動修復 |
| **滾動更新** | 不支援 | 基本支援 | 完整支援 |
| **多主機** | 不支援 | 不支援 | 原生支援 |
| **配置管理** | 環境變數 | .env 檔案 | ConfigMap/Secret |
| **儲存編排** | Volume | Volume | PV/PVC/StorageClass |
| **學習曲線** | 低 | 低 | 高 |

**關係說明：**
- Docker 提供容器運行時
- Kubernetes 使用 Docker（或其他容器運行時）作為底層
- Kubernetes 不是 Docker 的替代品，而是編排層

## 🏗️ Kubernetes 核心架構

### 整體架構圖

```mermaid
graph TB
    subgraph "Control Plane 控制平面"
        API[API Server<br/>kube-apiserver]
        ETCD[(etcd<br/>資料存儲)]
        SCHED[Scheduler<br/>kube-scheduler]
        CM[Controller Manager<br/>kube-controller-manager]
        CCM[Cloud Controller<br/>cloud-controller-manager]
    end

    subgraph "Node 1 工作節點"
        KUBELET1[Kubelet]
        PROXY1[Kube-proxy]
        RUNTIME1[Container Runtime<br/>containerd/CRI-O]
        POD1[Pod]
        POD2[Pod]
    end

    subgraph "Node 2 工作節點"
        KUBELET2[Kubelet]
        PROXY2[Kube-proxy]
        RUNTIME2[Container Runtime]
        POD3[Pod]
        POD4[Pod]
    end

    API <--> ETCD
    API <--> SCHED
    API <--> CM
    API <--> CCM

    KUBELET1 <--> API
    KUBELET2 <--> API

    KUBELET1 --> RUNTIME1
    KUBELET2 --> RUNTIME2

    RUNTIME1 --> POD1
    RUNTIME1 --> POD2
    RUNTIME2 --> POD3
    RUNTIME2 --> POD4

    PROXY1 -.-> POD1
    PROXY1 -.-> POD2
    PROXY2 -.-> POD3
    PROXY2 -.-> POD4

    style API fill:#326ce5
    style ETCD fill:#ff6b6b
    style SCHED fill:#4ecdc4
    style CM fill:#feca57
```

### 控制平面元件（Control Plane）

| 元件 | 作用 | 功能說明 |
|------|------|----------|
| **API Server** | 前端介面 | • 接收所有 REST 請求<br/>• 驗證和處理請求<br/>• 更新 etcd<br/>• 叢集的唯一入口 |
| **etcd** | 資料存儲 | • 分散式鍵值存儲<br/>• 儲存叢集所有狀態<br/>• 強一致性保證<br/>• 支援 watch 機制 |
| **Scheduler** | 調度器 | • 為新 Pod 選擇節點<br/>• 考慮資源需求<br/>• 硬體約束<br/>• 親和性規則 |
| **Controller Manager** | 控制器管理器 | • Node Controller<br/>• Replication Controller<br/>• Endpoints Controller<br/>• Service Account Controller |
| **Cloud Controller** | 雲端控制器 | • 雲端服務整合<br/>• 負載均衡器<br/>• 儲存卷<br/>• 路由管理 |

### 工作節點元件（Node）

| 元件 | 作用 | 功能說明 |
|------|------|----------|
| **Kubelet** | 節點代理 | • 管理 Pod 生命週期<br/>• 執行容器健康檢查<br/>• 回報節點狀態<br/>• 掛載 Volume |
| **Kube-proxy** | 網路代理 | • 維護網路規則<br/>• 實現 Service 抽象<br/>• 負載均衡<br/>• 支援 iptables/IPVS |
| **Container Runtime** | 容器運行時 | • 運行容器<br/>• 拉取映像<br/>• 支援 CRI 介面<br/>• containerd、CRI-O、Docker |

### 元件通訊流程

```mermaid
sequenceDiagram
    participant U as 使用者/kubectl
    participant API as API Server
    participant ETCD as etcd
    participant SCHED as Scheduler
    participant KUBELET as Kubelet
    participant RUNTIME as Container Runtime

    U->>API: 1. 創建 Pod 請求
    API->>ETCD: 2. 儲存 Pod 規格
    ETCD->>API: 3. 確認儲存
    API->>U: 4. 返回成功

    SCHED->>API: 5. Watch 未調度 Pod
    SCHED->>API: 6. 選擇節點並綁定
    API->>ETCD: 7. 更新 Pod 綁定資訊

    KUBELET->>API: 8. Watch 分配到本節點的 Pod
    KUBELET->>RUNTIME: 9. 啟動容器
    RUNTIME->>KUBELET: 10. 容器運行
    KUBELET->>API: 11. 回報 Pod 狀態
    API->>ETCD: 12. 更新狀態
```

## 📦 Kubernetes 核心概念

### 1. Pod - 最小部署單元

**Pod 是什麼？**
- Kubernetes 中最小的可部署單元
- 一個或多個容器的集合
- 共享網路和儲存空間
- 同一個 Pod 內的容器可以透過 localhost 通訊

```mermaid
graph TB
    subgraph "Pod"
        C1[容器 1<br/>主應用]
        C2[容器 2<br/>Sidecar]
        VOL[(共享 Volume)]
        NET[共享網路<br/>localhost]

        C1 -.-> NET
        C2 -.-> NET
        C1 -.-> VOL
        C2 -.-> VOL
    end

    POD_IP[Pod IP: 10.244.1.5]
    POD_IP -.-> NET

    style C1 fill:#4ecdc4
    style C2 fill:#a8e6cf
    style NET fill:#feca57
    style VOL fill:#ff6b6b
```

**Pod 特性對照表：**

| 特性 | 說明 | 範例 |
|------|------|------|
| **共享網路** | 同一 Pod 內容器共享 IP | 容器間透過 localhost 通訊 |
| **共享儲存** | 可掛載相同的 Volume | 日誌收集、資料共享 |
| **生命週期** | 作為一個整體管理 | 同時創建、刪除 |
| **調度單元** | 總是被調度到同一節點 | 保證容器位置關係 |
| **臨時性** | Pod 是短暫的 | IP 會變動，需要 Service |

### 2. Deployment - 應用部署

**Deployment 是什麼？**
- 管理無狀態應用的控制器
- 聲明式更新 Pod 和 ReplicaSet
- 支援滾動更新和回滾
- 確保指定數量的 Pod 運行

```mermaid
graph TB
    D[Deployment<br/>nginx-deployment<br/>replicas: 3] --> RS[ReplicaSet<br/>nginx-rs-abc123]
    RS --> P1[Pod 1<br/>Running]
    RS --> P2[Pod 2<br/>Running]
    RS --> P3[Pod 3<br/>Running]

    D -.->|更新| RS2[ReplicaSet<br/>nginx-rs-def456]
    RS2 -.-> P4[Pod 4<br/>Running]
    RS2 -.-> P5[Pod 5<br/>Running]

    style D fill:#326ce5
    style RS fill:#4ecdc4
    style RS2 fill:#a8e6cf
    style P1 fill:#feca57
    style P2 fill:#feca57
    style P3 fill:#feca57
```

**Deployment 功能：**

| 功能 | 說明 | 指令範例 |
|------|------|----------|
| **創建** | 部署應用 | `kubectl create deployment` |
| **擴展** | 調整副本數 | `kubectl scale deployment` |
| **更新** | 滾動更新 | `kubectl set image` |
| **回滾** | 返回舊版本 | `kubectl rollout undo` |
| **暫停/恢復** | 控制更新流程 | `kubectl rollout pause/resume` |
| **查看歷史** | 版本記錄 | `kubectl rollout history` |

### 3. Service - 服務發現與負載均衡

**Service 是什麼？**
- 為一組 Pod 提供穩定的網路端點
- 內建負載均衡
- 支援服務發現（DNS）
- 解決 Pod IP 不穩定的問題

```mermaid
graph TB
    subgraph "外部存取"
        CLIENT[客戶端]
    end

    subgraph "Service Layer"
        SVC[Service<br/>my-service<br/>ClusterIP: 10.0.0.100]
    end

    subgraph "Pod Layer"
        P1[Pod 1<br/>10.244.1.5]
        P2[Pod 2<br/>10.244.2.8]
        P3[Pod 3<br/>10.244.3.12]
    end

    CLIENT --> SVC
    SVC -.->|負載均衡| P1
    SVC -.->|負載均衡| P2
    SVC -.->|負載均衡| P3

    DNS[CoreDNS<br/>my-service.default.svc.cluster.local]
    DNS -.-> SVC

    style SVC fill:#326ce5
    style P1 fill:#4ecdc4
    style P2 fill:#4ecdc4
    style P3 fill:#4ecdc4
```

**Service 類型對照表：**

| 類型 | 用途 | 存取方式 | 適用場景 |
|------|------|----------|----------|
| **ClusterIP** | 叢集內部存取 | ClusterIP + Port | 後端服務 |
| **NodePort** | 透過節點 IP 存取 | NodeIP:NodePort | 開發測試 |
| **LoadBalancer** | 雲端負載均衡器 | 外部 IP | 生產環境（雲端） |
| **ExternalName** | DNS CNAME 映射 | DNS 名稱 | 外部服務整合 |

### 4. Volume - 資料持久化

**Volume 類型：**

```mermaid
graph TB
    A[Volume 類型] --> B[臨時存儲]
    A --> C[持久存儲]
    A --> D[配置存儲]
    A --> E[投影存儲]

    B --> B1[emptyDir<br/>Pod 生命週期]
    B --> B2[hostPath<br/>節點本地路徑]

    C --> C1[PersistentVolume<br/>持久卷]
    C --> C2[PersistentVolumeClaim<br/>持久卷聲明]

    D --> D1[ConfigMap<br/>配置資料]
    D --> D2[Secret<br/>敏感資料]

    E --> E1[Projected<br/>多種來源投影]

    style A fill:#326ce5
    style B fill:#ff6b6b
    style C fill:#4ecdc4
    style D fill:#feca57
    style E fill:#a8e6cf
```

**Volume 類型對照表：**

| 類型 | 生命週期 | 持久性 | 適用場景 |
|------|----------|--------|----------|
| **emptyDir** | Pod | 否 | 臨時資料、快取 |
| **hostPath** | 節點 | 是 | 系統級存取、測試 |
| **PV/PVC** | 獨立 | 是 | 資料庫、檔案存儲 |
| **ConfigMap** | 獨立 | 是 | 配置檔案 |
| **Secret** | 獨立 | 是 | 密鑰、證書 |
| **NFS** | 獨立 | 是 | 共享檔案系統 |
| **CSI** | 獨立 | 是 | 雲端儲存（EBS, Azure Disk） |

### 5. Namespace - 命名空間

**Namespace 是什麼？**
- 虛擬叢集劃分
- 資源隔離
- 多租戶支援
- 資源配額管理

```mermaid
graph TB
    CLUSTER[Kubernetes Cluster]

    CLUSTER --> NS1[Namespace: default]
    CLUSTER --> NS2[Namespace: development]
    CLUSTER --> NS3[Namespace: production]
    CLUSTER --> NS4[Namespace: kube-system]

    NS1 --> R1[Resources]
    NS2 --> R2[Resources<br/>ResourceQuota<br/>LimitRange]
    NS3 --> R3[Resources<br/>ResourceQuota<br/>LimitRange]
    NS4 --> R4[System Resources<br/>CoreDNS, Metrics]

    style CLUSTER fill:#326ce5
    style NS2 fill:#4ecdc4
    style NS3 fill:#ff6b6b
    style NS4 fill:#feca57
```

**預設 Namespace：**

| Namespace | 用途 | 說明 |
|-----------|------|------|
| **default** | 預設命名空間 | 未指定時使用 |
| **kube-system** | 系統元件 | K8s 核心元件 |
| **kube-public** | 公開資源 | 所有使用者可讀 |
| **kube-node-lease** | 節點心跳 | 節點健康檢查 |

### 6. ConfigMap & Secret - 配置管理

```mermaid
graph LR
    subgraph "配置注入方式"
        CM[ConfigMap<br/>一般配置]
        SEC[Secret<br/>敏感資料]
    end

    subgraph "Pod 使用方式"
        ENV[環境變數]
        VOL[Volume 掛載]
        CMD[命令行參數]
    end

    CM --> ENV
    CM --> VOL
    CM --> CMD

    SEC --> ENV
    SEC --> VOL

    style CM fill:#4ecdc4
    style SEC fill:#ff6b6b
```

**對照表：**

| 項目 | ConfigMap | Secret |
|------|-----------|--------|
| **用途** | 一般配置資料 | 敏感資料（密碼、金鑰） |
| **編碼** | 明文 | Base64 編碼 |
| **大小限制** | 1MB | 1MB |
| **典型內容** | 配置檔、環境變數 | 密碼、API Token、TLS 證書 |
| **安全性** | 低 | 中（需額外加密） |

## 🔧 Kubernetes 安裝與設定

### 安裝方式對照表

| 方式 | 適用場景 | 複雜度 | 生產可用 |
|------|----------|--------|----------|
| **Minikube** | 本地開發、學習 | 低 | ❌ |
| **Kind** | CI/CD、測試 | 低 | ❌ |
| **k3s** | 邊緣運算、IoT | 低 | ✅ |
| **kubeadm** | 自建叢集 | 中 | ✅ |
| **kOps** | AWS 叢集 | 中 | ✅ |
| **EKS/GKE/AKS** | 雲端託管 | 低 | ✅ |
| **Rancher** | 企業管理平台 | 中 | ✅ |

### 1. Minikube 安裝（本地開發）

**系統需求：**
- 2 CPU 核心以上
- 2GB 記憶體以上
- 20GB 磁碟空間
- 容器或虛擬機管理器（Docker、VirtualBox、KVM）

**macOS 安裝：**

```bash
# 使用 Homebrew 安裝
brew install minikube

# 安裝 kubectl
brew install kubectl

# 啟動 Minikube
minikube start --driver=docker --cpus=2 --memory=4096

# 驗證安裝
kubectl cluster-info
kubectl get nodes

# 啟用插件
minikube addons enable dashboard
minikube addons enable metrics-server
minikube addons enable ingress

# 開啟 Dashboard
minikube dashboard
```

**Linux 安裝：**

```bash
# 下載 Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# 安裝 kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 啟動 Minikube
minikube start --driver=docker

# 驗證
kubectl get nodes
```

**Windows 安裝：**

```powershell
# 使用 Chocolatey
choco install minikube
choco install kubernetes-cli

# 或使用 Windows Package Manager
winget install Kubernetes.minikube
winget install Kubernetes.kubectl

# 啟動
minikube start --driver=hyperv

# 驗證
kubectl version --client
kubectl cluster-info
```

### 2. kubectl 配置

**kubectl 配置檔案：** `~/.kube/config`

```yaml
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: <CA_DATA>
    server: https://127.0.0.1:58619
  name: minikube
contexts:
- context:
    cluster: minikube
    user: minikube
  name: minikube
current-context: minikube
users:
- name: minikube
  user:
    client-certificate-data: <CERT_DATA>
    client-key-data: <KEY_DATA>
```

**常用 kubectl 配置指令：**

```bash
# 查看當前 context
kubectl config current-context

# 列出所有 context
kubectl config get-contexts

# 切換 context
kubectl config use-context minikube

# 查看配置
kubectl config view

# 設定命名空間
kubectl config set-context --current --namespace=development

# 添加叢集
kubectl config set-cluster my-cluster \
  --server=https://k8s.example.com:6443 \
  --certificate-authority=/path/to/ca.crt

# 添加使用者
kubectl config set-credentials my-user \
  --client-certificate=/path/to/client.crt \
  --client-key=/path/to/client.key

# 添加 context
kubectl config set-context my-context \
  --cluster=my-cluster \
  --user=my-user \
  --namespace=default
```

### 3. 驗證叢集健康狀態

```bash
# 查看叢集資訊
kubectl cluster-info

# 查看節點
kubectl get nodes
kubectl describe node <node-name>

# 查看元件狀態
kubectl get componentstatuses
# 或
kubectl get cs

# 查看系統 Pod
kubectl get pods -n kube-system

# 查看所有命名空間的資源
kubectl get all --all-namespaces

# 查看事件
kubectl get events --all-namespaces --sort-by='.lastTimestamp'
```

### 4. 第一個 Kubernetes 應用

**創建 Nginx Deployment：**

```bash
# 創建 Deployment
kubectl create deployment nginx --image=nginx:latest

# 查看 Deployment
kubectl get deployments

# 查看 Pod
kubectl get pods

# 暴露服務
kubectl expose deployment nginx --port=80 --type=NodePort

# 查看 Service
kubectl get services

# 取得服務 URL（Minikube）
minikube service nginx --url

# 測試服務
curl $(minikube service nginx --url)
```

**使用 YAML 檔案部署：**

```yaml
# nginx-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.24
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "128Mi"
            cpu: "500m"

---
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  selector:
    app: nginx
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
```

**部署應用：**

```bash
# 應用 YAML
kubectl apply -f nginx-deployment.yaml

# 查看資源
kubectl get deployments,pods,services

# 查看詳細資訊
kubectl describe deployment nginx-deployment
kubectl describe service nginx-service

# 查看 Pod 日誌
kubectl logs <pod-name>

# 進入 Pod
kubectl exec -it <pod-name> -- bash

# 刪除資源
kubectl delete -f nginx-deployment.yaml
```

## 📊 Kubernetes 物件模型

### 宣告式 vs 命令式

```mermaid
graph TB
    A[Kubernetes 管理方式] --> B[命令式<br/>Imperative]
    A --> C[宣告式<br/>Declarative]

    B --> B1[kubectl run]
    B --> B2[kubectl create]
    B --> B3[kubectl expose]
    B --> B4[kubectl scale]

    C --> C1[YAML 檔案]
    C --> C2[kubectl apply]
    C --> C3[版本控制]
    C --> C4[GitOps]

    style A fill:#326ce5
    style B fill:#ff6b6b
    style C fill:#4ecdc4
```

**對照表：**

| 特性 | 命令式（Imperative） | 宣告式（Declarative） |
|------|---------------------|---------------------|
| **命令方式** | `kubectl create`, `run` | `kubectl apply` |
| **配置檔案** | 不需要 | YAML/JSON |
| **版本控制** | 困難 | 容易（Git） |
| **可重複性** | 低 | 高 |
| **生產環境** | 不推薦 | 推薦 |
| **學習曲線** | 低 | 中 |
| **適用場景** | 快速測試、學習 | 生產部署、GitOps |

### YAML 基本結構

```yaml
# 所有 Kubernetes 物件都遵循此結構
apiVersion: apps/v1              # API 版本
kind: Deployment                 # 資源類型
metadata:                        # 元資料
  name: my-app                   # 名稱
  namespace: default             # 命名空間
  labels:                        # 標籤
    app: my-app
    env: production
  annotations:                   # 註解
    description: "My application"
spec:                            # 規格定義
  # 具體規格內容
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: app
        image: my-app:v1.0
```

### 標籤（Labels）與選擇器（Selectors）

```mermaid
graph TB
    subgraph "標籤系統"
        P1[Pod 1<br/>app=web, env=prod]
        P2[Pod 2<br/>app=web, env=dev]
        P3[Pod 3<br/>app=api, env=prod]
        P4[Pod 4<br/>app=api, env=dev]
    end

    subgraph "選擇器"
        S1[Selector: app=web]
        S2[Selector: env=prod]
        S3[Selector: app=web, env=prod]
    end

    S1 -.-> P1
    S1 -.-> P2

    S2 -.-> P1
    S2 -.-> P3

    S3 -.-> P1

    style P1 fill:#4ecdc4
    style P2 fill:#a8e6cf
    style P3 fill:#feca57
    style P4 fill:#ffb3ba
```

**標籤最佳實踐：**

| 標籤鍵 | 說明 | 範例值 |
|--------|------|--------|
| `app` | 應用名稱 | `nginx`, `mysql` |
| `version` | 應用版本 | `v1.0.0`, `stable` |
| `component` | 架構元件 | `frontend`, `backend`, `database` |
| `tier` | 應用層級 | `frontend`, `backend`, `cache` |
| `environment` | 環境 | `production`, `staging`, `dev` |
| `managed-by` | 管理工具 | `helm`, `kubectl`, `terraform` |
| `part-of` | 所屬專案 | `myproject`, `e-commerce` |

## 🎯 學習路徑與資源

### 學習階段規劃

```mermaid
graph TB
    A[第一階段<br/>基礎概念] --> B[第二階段<br/>核心資源]
    B --> C[第三階段<br/>網路與存儲]
    C --> D[第四階段<br/>配置與安全]
    D --> E[第五階段<br/>進階功能]
    E --> F[第六階段<br/>生產實踐]

    A1[理解架構<br/>安裝 K8s<br/>基本指令] --> A
    B1[Pod/Deployment<br/>Service<br/>基本部署] --> B
    C1[Ingress<br/>NetworkPolicy<br/>PV/PVC] --> C
    D1[ConfigMap/Secret<br/>RBAC<br/>Security Context] --> D
    E1[StatefulSet<br/>DaemonSet<br/>Job/CronJob<br/>HPA] --> E
    F1[監控告警<br/>日誌管理<br/>CI/CD<br/>Helm] --> F

    style A fill:#326ce5
    style B fill:#4ecdc4
    style C fill:#a8e6cf
    style D fill:#feca57
    style E fill:#ffb3ba
    style F fill:#ff6b6b
```

### 推薦學習資源

**官方文件：**
- [Kubernetes 官方文件](https://kubernetes.io/docs/)
- [Kubernetes 官方教學](https://kubernetes.io/docs/tutorials/)
- [Kubectl 參考文件](https://kubernetes.io/docs/reference/kubectl/)

**互動式學習：**
- [Play with Kubernetes](https://labs.play-with-k8s.com/)
- [Katacoda Kubernetes Scenarios](https://www.katacoda.com/courses/kubernetes)
- [Kubernetes by Example](https://kubernetesbyexample.com/)

**認證考試：**
- **CKA**（Certified Kubernetes Administrator）- 管理員認證
- **CKAD**（Certified Kubernetes Application Developer）- 開發者認證
- **CKS**（Certified Kubernetes Security Specialist）- 安全專家認證

## 🔍 常見問題解答

### Q1: Kubernetes 和 Docker 是什麼關係？

**答：** Kubernetes 與 Docker 是互補而非競爭關係：

| 層級 | Docker | Kubernetes |
|------|--------|------------|
| **定位** | 容器運行時 | 容器編排平台 |
| **作用** | 運行單個容器 | 管理多個容器 |
| **範圍** | 單機 | 叢集 |
| **關係** | K8s 使用 Docker 作為底層運行時之一 | |

### Q2: 什麼時候需要使用 Kubernetes？

**適合使用 K8s：**
- 微服務架構
- 需要自動擴展
- 多環境部署（dev/staging/prod）
- 需要高可用性
- 容器數量超過 10 個

**不需要 K8s：**
- 單體應用
- 小型專案（<5 個容器）
- 學習階段（可用 Docker Compose）
- 資源有限（管理開銷大）

### Q3: Kubernetes 有哪些替代方案？

| 方案 | 特點 | 適用場景 |
|------|------|----------|
| **Docker Swarm** | 簡單、Docker 原生 | 小規模、簡單需求 |
| **Nomad** | 輕量、支援多種工作負載 | 混合工作負載 |
| **ECS** | AWS 託管 | AWS 生態系統 |
| **Cloud Run** | 無伺服器容器 | 簡單 HTTP 服務 |

### Q4: Kubernetes 學習曲線陡峭嗎？

**學習難度分析：**

| 階段 | 難度 | 時間 | 內容 |
|------|------|------|------|
| **基礎** | ⭐⭐ | 1-2週 | Pod, Deployment, Service |
| **中級** | ⭐⭐⭐ | 1-2月 | Volume, ConfigMap, Ingress |
| **進階** | ⭐⭐⭐⭐ | 3-6月 | StatefulSet, Operator, CRD |
| **專家** | ⭐⭐⭐⭐⭐ | 6月+ | 叢集管理、調優、安全 |

**學習建議：**
1. 先掌握 Docker 基礎
2. 循序漸進，從簡單應用開始
3. 實際操作比理論重要
4. 多看官方文件和範例
5. 參與社群討論

### Q5: 生產環境需要多少資源？

**最小叢集配置（小型）：**
- **Control Plane**：2 CPU, 4GB RAM
- **Worker Node** × 3：2 CPU, 4GB RAM each
- **總計**：8 CPU, 16GB RAM

**推薦配置（中型）：**
- **Control Plane**：4 CPU, 8GB RAM
- **Worker Node** × 5：4 CPU, 8GB RAM each
- **總計**：24 CPU, 48GB RAM

## 🎉 總結

本文介紹了 Kubernetes 的基礎概念，涵蓋：

### 核心知識點

1. **什麼是 Kubernetes**
   - 容器編排平台
   - 解決的問題
   - 與 Docker 的關係

2. **核心架構**
   - 控制平面（Control Plane）
   - 工作節點（Node）
   - 元件通訊流程

3. **核心概念**
   - Pod：最小部署單元
   - Deployment：應用部署管理
   - Service：服務發現與負載均衡
   - Volume：資料持久化
   - Namespace：資源隔離
   - ConfigMap/Secret：配置管理

4. **安裝與配置**
   - Minikube 本地開發環境
   - kubectl 配置
   - 第一個應用部署

### 關鍵要點

- Kubernetes 是容器編排的事實標準
- 聲明式配置是最佳實踐
- 標籤與選擇器是資源管理的核心
- 從簡單開始，循序漸進

### 下一步學習

在第二篇文章中，我們將深入探討：
- 核心工作負載資源（Pod、Deployment、StatefulSet）
- Service 與 Ingress 網路配置
- 儲存管理（PV、PVC、StorageClass）
- ConfigMap 與 Secret 實務應用
- kubectl 進階操作與技巧

掌握這些基礎概念後，您將能夠理解 Kubernetes 的運作原理，為後續深入學習打下堅實的基礎！