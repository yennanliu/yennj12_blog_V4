---
title: "Harness 工程入門指南：AI 時代的基礎設施自動化"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "DevOps", "infrastructure"]
tags: ["Harness", "CI/CD", "基礎設施", "自動化", "AI", "部署", "工程實踐"]
summary: "深入探討 Harness 在 AI 時代的角色，從基本概念、核心功能到實戰應用，幫助工程團隊建立高效的自動化部署流程，加速 AI 應用的上線速度。"
readTime: "35 min"
---

在 AI 應用快速迭代的時代，傳統的 CI/CD 流程面臨新的挑戰：模型版本管理複雜、部署頻率高、需要快速回滾，以及多環境配置管理困難。本文介紹 Harness——一個現代化的部署平台，如何幫助團隊在 AI 時代實現敏捷、可靠的基礎設施自動化。

---

## 為什麼 AI 工程需要 Harness？

### 傳統 CI/CD 的瓶頸

```
傳統流程：
開發 → Git Push → Jenkins → Docker Build → kubectl apply → 等待 5~10 分鐘

AI 時代的挑戰：
1. 模型版本控制：不僅是代碼，還有模型文件、配置、超參數
2. 高頻部署：每天可能部署 10+ 次
3. 快速回滾需求：A/B 測試需要秒級切換
4. 多環境配置：Dev/Staging/Prod 配置差異大
5. 成本監控：GPU 資源成本高，需要精細控制
```

### Harness 的價值主張

| 需求 | 傳統方式 | Harness 方案 |
|------|---------|------------|
| 部署速度 | 5-10 分鐘 | <2 分鐘 |
| 回滾速度 | 需要重新構建 | 即時回滾 |
| 風險控制 | 全量或手動灰度 | 智能灰度、金絲雀部署 |
| 配置管理 | 多個 YAML 文件 | 集中配置、動態變數 |
| 成本控制 | 無完整監控 | 實時成本追蹤 |

---

## Harness 核心概念

### 1. Pipeline（流程）

Pipeline 是一系列自動化步驟的集合，定義了從代碼提交到上線的完整流程。

```yaml
# Harness Pipeline 示例
pipeline:
  name: AI-Model-Deploy
  stages:
    - stage: Build
      steps:
        - step: 
            name: Build Docker Image
            type: Plugin
            spec:
              image: docker:latest
              commands:
                - docker build -t ai-service:${GIT_COMMIT} .
                - docker push registry.example.com/ai-service:${GIT_COMMIT}
    
    - stage: Test
      steps:
        - step:
            name: Unit Tests
            type: Plugin
            spec:
              image: python:3.11
              commands:
                - pip install -r requirements.txt
                - pytest tests/ --cov
    
    - stage: Deploy-Staging
      steps:
        - step:
            name: Deploy to Staging
            type: Kubernetes
            spec:
              namespace: staging
              resources:
                - ai-service-deployment.yaml
    
    - stage: Approval
      type: Approval
      
    - stage: Deploy-Production
      steps:
        - step:
            name: Canary Deployment
            type: Kubernetes
            spec:
              namespace: production
              strategy: canary
              canary:
                weight: 10  # 10% traffic
                interval: 5m
                threshold: 95  # 95% success rate
```

### 2. Service（服務）

Service 定義了應用的部署單位，包括容器鏡像、資源需求、環境變數等。

```yaml
service:
  name: ai-inference-service
  type: Kubernetes
  spec:
    containers:
      - name: inference-engine
        image: ai-service:${VERSION}
        resources:
          requests:
            memory: 8Gi
            cpu: 4
            nvidia.com/gpu: 1  # GPU 資源
          limits:
            memory: 16Gi
            cpu: 8
            nvidia.com/gpu: 1
        env:
          - MODEL_PATH: /models/llama-13b
          - BATCH_SIZE: 32
          - MAX_TOKENS: 2048
        healthChecks:
          - type: HTTP
            path: /health
            interval: 30s
            timeout: 10s
```

### 3. Environment（環境）

Environment 代表部署目標環境，如開發、測試、預發、生產等。

```yaml
environments:
  - name: Staging
    type: Kubernetes
    spec:
      cluster: staging-cluster
      namespace: staging
      variables:
        LOG_LEVEL: DEBUG
        API_TIMEOUT: 30
  
  - name: Production
    type: Kubernetes
    spec:
      cluster: prod-cluster
      namespace: production
      variables:
        LOG_LEVEL: INFO
        API_TIMEOUT: 10
        ENABLE_MONITORING: true
```

### 4. Deployment（部署）

Deployment 定義了如何將 Service 部署到 Environment 的策略。

```
部署策略：

1. Blue-Green Deploy（藍綠部署）
   舊版本(Blue) ←→ 新版本(Green)
   優點：完全的 0 停機、立即回滾
   缺點：需要 2 倍資源

2. Canary Deploy（金絲雀部署）
   正式版(90%) ← → 新版本(10%)
   優點：風險最低、逐步驗證
   缺點：部署時間長

3. Rolling Deploy（滾動部署）
   Pod1(Old) → Pod1(New)
   Pod2(Old) → Pod2(New)
   優點：資源高效、平滑過渡
   缺點：需要向後兼容

4. Shadow Deploy（影子部署）
   正式流量 → 新版本(複製)
   優點：零風險測試真實流量
   缺點：實時基礎設施要求高
```

---

## AI 應用的實戰場景

### 場景 1：模型更新部署

```yaml
pipeline:
  name: LLM-Model-Update
  trigger:
    - type: Webhook
      on: [push]
      branches: [main]
      paths:
        - models/**
        - src/**

  stages:
    - stage: Validate Model
      steps:
        - step:
            name: Check Model Size
            type: Plugin
            spec:
              image: python:3.11
              commands:
                - ls -lh models/model.safetensors
                - python scripts/validate_model.py models/model.safetensors

    - stage: Build & Push
      steps:
        - step:
            name: Build with New Model
            type: Plugin
            spec:
              image: docker:latest
              commands:
                - docker build --build-arg MODEL_VERSION=${GIT_COMMIT} -t ai-service:${GIT_COMMIT} .
                - docker push ${REGISTRY}/ai-service:${GIT_COMMIT}

    - stage: Performance Test
      parallel: true
      steps:
        - step:
            name: Latency Test
            type: Plugin
            spec:
              image: locust:latest
              commands:
                - locust -f tests/load_test.py --headless -u 100 -r 10 --run-time 5m
        
        - step:
            name: Accuracy Test
            type: Plugin
            spec:
              image: python:3.11
              commands:
                - python tests/accuracy_test.py --model-version ${GIT_COMMIT}

    - stage: Deploy to Staging
      steps:
        - step:
            name: Deploy
            type: Kubernetes
            spec:
              namespace: staging
              strategy: rolling
              
    - stage: Smoke Test
      steps:
        - step:
            name: Verify Endpoints
            type: Plugin
            spec:
              image: curl:latest
              commands:
                - curl -f http://ai-service-staging/health
                - curl -X POST -d '{"input":"test"}' http://ai-service-staging/inference

    - stage: Approval
      type: Manual
      approvers:
        - group: ml-team
      timeout: 24h

    - stage: Deploy to Production
      steps:
        - step:
            name: Canary Deploy
            type: Kubernetes
            spec:
              namespace: production
              strategy: canary
              canary:
                weight: 5
                interval: 10m
                threshold: 98
              rollback:
                condition: error_rate > 2% || latency_p99 > 1000ms
```

### 場景 2：A/B 測試部署

```yaml
pipeline:
  name: Model-AB-Test
  
  stages:
    - stage: Deploy Variant A
      steps:
        - step:
            name: Deploy Model A
            type: Kubernetes
            spec:
              selector:
                version: model-a
              weight: 50
    
    - stage: Deploy Variant B
      steps:
        - step:
            name: Deploy Model B
            type: Kubernetes
            spec:
              selector:
                version: model-b
              weight: 50
    
    - stage: Monitor Metrics
      steps:
        - step:
            name: Collect Metrics
            type: Datadog
            spec:
              metrics:
                - model_a.inference.latency
                - model_b.inference.latency
                - model_a.accuracy
                - model_b.accuracy
              duration: 7d

    - stage: Analyze Results
      steps:
        - step:
            name: Statistical Test
            type: Plugin
            spec:
              image: python:3.11
              commands:
                - python scripts/statistical_analysis.py --duration 7d
```

---

## Harness 的關鍵特性

### 1. GitOps 集成

```yaml
# 使用 GitOps，所有配置即代碼
# 存儲在 Git，version 控制，audit trail 完整

triggers:
  - type: Git
    repo: github.com/myorg/ai-deployment
    branch: main
    paths:
      - deployments/**
    on_change: auto_deploy
```

### 2. 多雲支持

```yaml
# 支持跨雲部署
environments:
  - name: AWS-Prod
    provider: AWS-ECS
    spec:
      region: us-east-1
      cluster: prod-cluster

  - name: GCP-Prod
    provider: GCP-GKE
    spec:
      project: my-project
      cluster: prod-cluster

  - name: Azure-Prod
    provider: Azure-AKS
    spec:
      resource_group: production
      cluster: prod-cluster
```

### 3. 成本控制

```yaml
# 實時成本監控和優化建議
cost_management:
  alerts:
    - threshold: 1000  # 每日 $1000
      action: notify
    - threshold: 1500  # 每日 $1500
      action: scale_down
  
  optimization:
    - type: spot_instances
      savings: 70%
    - type: reserved_instances
      savings: 40%
```

### 4. 審計日誌

```
所有部署操作記錄：
- 誰部署了什麼
- 什麼時候部署
- 部署了哪個版本
- 部署前後的對比
- 回滾記錄
- 審批流程
```

---

## 最佳實踐

### 1. 分層設計

```
Team → Project → Pipeline → Service → Environment

特點：
- Team：組織邊界
- Project：業務單位
- Pipeline：工作流
- Service：部署單位
- Environment：運行環境
```

### 2. 環境隔離

```yaml
# 不同環境的配置差異
dev:
  replicas: 1
  image_pull_policy: Always
  debug: true

staging:
  replicas: 3
  image_pull_policy: IfNotPresent
  debug: false

production:
  replicas: 5
  image_pull_policy: IfNotPresent
  debug: false
  enable_monitoring: true
  enable_alerts: true
```

### 3. 審批流程

```
開發環境：無需審批（快速迭代）
  ↓
測試環境：由測試負責人審批
  ↓
預發環境：由技術負責人審批
  ↓
生產環境：由產品和技術雙方審批（關鍵變更需要 CEO 簽字）
```

### 4. 回滾策略

```yaml
rollback_policy:
  automatic:
    - condition: error_rate > 5%
      duration: 5m
      action: instant_rollback
    - condition: latency_p99 > 5s
      duration: 10m
      action: instant_rollback
  
  manual:
    - requires: on_call_engineer
    - notification: instant_slack_alert
    - safety_check: previous_version_health_check
```

---

## 總結

Harness 在 AI 時代的價值：

| 層面 | 收益 |
|------|------|
| 速度 | 部署時間縮短 50-75% |
| 安全 | 自動化審批、audit trail、秒級回滾 |
| 成本 | 資源利用率提升 30-40%，智能推薦節省 20-30% |
| 可靠性 | 灰度部署降低故障率 90% |
| 開發體驗 | 聚焦模型開發，基礎設施開箱即用 |

對於 AI 團隊，Harness 不僅是部署工具，更是實現**持續交付**和**持續改進**的基礎設施基石。
