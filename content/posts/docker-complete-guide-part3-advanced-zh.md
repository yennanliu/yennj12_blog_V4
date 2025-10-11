---
title: "Docker 完整指南（三）：進階應用與生產實踐"
date: 2025-10-11T11:30:00+08:00
draft: false
description: "深入探討 Docker 進階主題，包含 Dockerfile 最佳實踐、多階段建立、Docker Compose 編排、網路進階配置、安全性強化、效能優化與生產環境部署策略。"
categories: ["Engineering", "DevOps", "Docker", "all"]
tags: ["Docker", "Dockerfile", "Docker Compose", "容器編排", "微服務", "CI/CD", "容器安全", "效能優化", "生產部署"]
authors: ["yennj12 team"]
readTime: "70 min"
---

## 🎯 前言

經過前兩篇文章的學習，我們已經掌握了 Docker 的基礎概念與指令操作。本文將深入探討 Docker 的進階應用，涵蓋從開發到生產環境的完整實踐。

**本文重點：**
- Dockerfile 最佳實踐與優化
- 多階段建立（Multi-stage Build）
- Docker Compose 完整應用
- 網路進階配置
- 安全性強化
- 效能調優
- 生產環境部署策略

## 📝 Dockerfile 深度解析

### Dockerfile 指令完整對照表

| 指令 | 作用 | 層級影響 | 範例 |
|------|------|----------|------|
| **FROM** | 指定基礎映像 | 是 | `FROM node:18-alpine` |
| **LABEL** | 添加元資料 | 否 | `LABEL version="1.0"` |
| **RUN** | 執行指令 | 是 | `RUN npm install` |
| **CMD** | 容器啟動指令 | 否 | `CMD ["npm", "start"]` |
| **ENTRYPOINT** | 容器進入點 | 否 | `ENTRYPOINT ["python"]` |
| **COPY** | 複製檔案 | 是 | `COPY app.py /app/` |
| **ADD** | 複製並解壓 | 是 | `ADD archive.tar.gz /app/` |
| **ENV** | 設定環境變數 | 否 | `ENV NODE_ENV=production` |
| **ARG** | 建立時變數 | 否 | `ARG VERSION=1.0` |
| **WORKDIR** | 設定工作目錄 | 否 | `WORKDIR /app` |
| **EXPOSE** | 聲明埠 | 否 | `EXPOSE 8080` |
| **VOLUME** | 定義掛載點 | 否 | `VOLUME ["/data"]` |
| **USER** | 切換使用者 | 否 | `USER appuser` |
| **HEALTHCHECK** | 健康檢查 | 否 | `HEALTHCHECK CMD curl -f http://localhost/` |
| **ONBUILD** | 觸發器指令 | 否 | `ONBUILD COPY . /app` |
| **SHELL** | 設定 Shell | 否 | `SHELL ["/bin/bash", "-c"]` |
| **STOPSIGNAL** | 停止信號 | 否 | `STOPSIGNAL SIGTERM` |

### Dockerfile 最佳實踐

#### 1. 基礎映像選擇

```dockerfile
# ❌ 不推薦：使用完整版本
FROM ubuntu:latest

# ✅ 推薦：使用 Alpine 基礎映像
FROM node:18-alpine

# ✅ 推薦：使用 Distroless（最小化）
FROM gcr.io/distroless/nodejs18-debian11

# ✅ 推薦：指定確切版本
FROM python:3.11.5-slim-bookworm
```

**映像大小對照：**

| 基礎映像 | 大小 | 適用場景 |
|----------|------|----------|
| `ubuntu:latest` | ~77 MB | 完整功能需求 |
| `node:18` | ~900 MB | 開發環境 |
| `node:18-slim` | ~170 MB | 較小生產映像 |
| `node:18-alpine` | ~110 MB | 最小化生產映像 |
| `distroless` | ~50 MB | 安全性要求高 |

#### 2. 層級優化技巧

```dockerfile
# ❌ 不推薦：每個 RUN 創建一層
FROM ubuntu:20.04
RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y pip
RUN pip install flask

# ✅ 推薦：合併 RUN 指令
FROM ubuntu:20.04
RUN apt-get update && \
    apt-get install -y \
        python3 \
        python3-pip && \
    pip3 install flask && \
    rm -rf /var/lib/apt/lists/*

# ✅ 更好：使用 heredoc（Docker 23.0+）
FROM ubuntu:20.04
RUN <<EOF
apt-get update
apt-get install -y python3 python3-pip
pip3 install flask
rm -rf /var/lib/apt/lists/*
EOF
```

#### 3. 快取優化策略

```dockerfile
# ❌ 不推薦：先複製所有檔案
FROM node:18-alpine
WORKDIR /app
COPY . .
RUN npm install

# ✅ 推薦：先複製依賴檔案，利用快取
FROM node:18-alpine
WORKDIR /app

# 先複製依賴定義檔案
COPY package*.json ./
RUN npm ci --only=production

# 再複製程式碼
COPY . .

# 建立時快取 node_modules
RUN npm run build
```

**快取策略說明：**

```mermaid
graph TB
    A[COPY package.json] -->|快取命中| B[使用快取的 npm install]
    A -->|檔案變更| C[重新執行 npm install]
    B --> D[COPY 原始碼]
    C --> D
    D -->|程式碼變更| E[重新建立]
    D -->|程式碼未變| F[使用快取]

    style B fill:#4ecdc4
    style F fill:#4ecdc4
    style C fill:#ff6b6b
    style E fill:#ff6b6b
```

#### 4. .dockerignore 檔案

```bash
# .dockerignore 範例

# 版本控制
.git
.gitignore
.svn

# 依賴目錄
node_modules
bower_components
__pycache__
*.pyc
.Python

# 建立產物
dist
build
*.egg-info
target

# IDE 設定
.idea
.vscode
*.swp
*.swo
*~

# 日誌與臨時檔案
*.log
npm-debug.log*
logs
tmp
temp

# 測試相關
coverage
.nyc_output
.pytest_cache
*.test

# 文件
README.md
CHANGELOG.md
LICENSE
docs

# CI/CD
.github
.gitlab-ci.yml
.travis.yml
Jenkinsfile

# Docker
Dockerfile*
docker-compose*.yml
.dockerignore

# 環境變數（敏感資訊）
.env
.env.local
.env.*.local
secrets.yml
```

### 完整的 Dockerfile 範例

#### Node.js 應用程式

```dockerfile
# 使用官方 Node.js 18 Alpine 映像
FROM node:18-alpine AS base

# 添加元資料
LABEL maintainer="devops@example.com" \
      version="1.0.0" \
      description="Node.js Application"

# 安裝 dumb-init（正確處理信號）
RUN apk add --no-cache dumb-init

# 設定工作目錄
WORKDIR /app

# 設定環境變數
ENV NODE_ENV=production \
    PORT=3000

# ===== 依賴階段 =====
FROM base AS dependencies

# 複製依賴定義檔案
COPY package*.json ./

# 安裝生產依賴
RUN npm ci --only=production && \
    npm cache clean --force

# ===== 建立階段 =====
FROM base AS build

# 複製依賴定義檔案
COPY package*.json ./

# 安裝所有依賴（包含開發依賴）
RUN npm ci && \
    npm cache clean --force

# 複製原始碼
COPY . .

# 執行建立（如果需要）
RUN npm run build

# ===== 生產階段 =====
FROM base AS production

# 創建非 root 使用者
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# 從依賴階段複製 node_modules
COPY --from=dependencies --chown=nodejs:nodejs /app/node_modules ./node_modules

# 從建立階段複製建立產物
COPY --from=build --chown=nodejs:nodejs /app/dist ./dist
COPY --chown=nodejs:nodejs package*.json ./

# 切換到非 root 使用者
USER nodejs

# 暴露埠
EXPOSE 3000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD node healthcheck.js || exit 1

# 使用 dumb-init 啟動應用
ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "dist/server.js"]
```

#### Python Flask 應用

```dockerfile
# ===== 建立階段 =====
FROM python:3.11-slim AS builder

# 設定工作目錄
WORKDIR /app

# 安裝建立依賴
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴到虛擬環境
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ===== 生產階段 =====
FROM python:3.11-slim

# 設定標籤
LABEL maintainer="devops@example.com"

# 安裝運行時依賴
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* /var/tmp/*

# 創建應用使用者
RUN useradd -m -u 1000 -s /bin/bash appuser

# 設定工作目錄
WORKDIR /app

# 從建立階段複製虛擬環境
COPY --from=builder /opt/venv /opt/venv

# 設定環境變數
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production

# 複製應用程式碼
COPY --chown=appuser:appuser . .

# 切換到非 root 使用者
USER appuser

# 暴露埠
EXPOSE 5000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 啟動應用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

## 🔨 多階段建立（Multi-stage Build）

### 多階段建立的優勢

```mermaid
graph LR
    A[原始碼] --> B[建立階段]
    B --> C[編譯產物]
    C --> D[生產階段]
    D --> E[最終映像]

    B -.->|不包含| E
    C -->|只複製需要的| E

    style B fill:#ff6b6b
    style D fill:#4ecdc4
    style E fill:#a8e6cf
```

**效益對照表：**

| 項目 | 單階段建立 | 多階段建立 |
|------|------------|------------|
| **映像大小** | 1-2 GB | 100-300 MB |
| **建立工具** | 包含 | 不包含 |
| **安全性** | 低（包含編譯器） | 高（只有執行檔） |
| **建立時間** | 較快 | 稍慢（但可快取） |
| **維護性** | 低 | 高 |

### Go 應用多階段範例

```dockerfile
# ===== 建立階段 =====
FROM golang:1.21-alpine AS builder

# 安裝建立工具
RUN apk add --no-cache git ca-certificates tzdata

# 設定工作目錄
WORKDIR /build

# 複製 go mod 檔案
COPY go.mod go.sum ./

# 下載依賴
RUN go mod download && \
    go mod verify

# 複製原始碼
COPY . .

# 建立應用
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags='-w -s -extldflags "-static"' \
    -a \
    -o /app/server \
    ./cmd/server

# ===== 生產階段 =====
FROM scratch

# 從 builder 複製必要檔案
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /app/server /server

# 設定時區
ENV TZ=Asia/Taipei

# 暴露埠
EXPOSE 8080

# 非 root 使用者
USER 65534:65534

# 啟動應用
ENTRYPOINT ["/server"]
```

**映像大小對照：**
- 單階段建立：~800 MB
- 多階段建立：~10 MB
- 減少：**98.75%**

### Java Spring Boot 多階段範例

```dockerfile
# ===== 建立階段 =====
FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /build

# 複製 pom.xml 並下載依賴（快取優化）
COPY pom.xml .
RUN mvn dependency:go-offline -B

# 複製原始碼並建立
COPY src ./src
RUN mvn clean package -DskipTests && \
    java -Djarmode=layertools -jar target/*.jar extract

# ===== 生產階段 =====
FROM eclipse-temurin:17-jre-alpine

# 設定標籤
LABEL maintainer="devops@example.com"

# 安裝工具
RUN apk add --no-cache curl

# 創建應用使用者
RUN addgroup -g 1000 spring && \
    adduser -D -u 1000 -G spring spring

WORKDIR /app

# 從建立階段複製分層
COPY --from=build /build/dependencies/ ./
COPY --from=build /build/spring-boot-loader/ ./
COPY --from=build /build/snapshot-dependencies/ ./
COPY --from=build /build/application/ ./

# 設定擁有者
RUN chown -R spring:spring /app

USER spring

EXPOSE 8080

# 健康檢查
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

# 啟動應用
ENTRYPOINT ["java", "org.springframework.boot.loader.JarLauncher"]
```

## 🎭 Docker Compose 深入應用

### Docker Compose 檔案結構

```yaml
version: "3.8"  # Compose 檔案版本

services:       # 服務定義
  service-name:
    build:      # 建立配置
    image:      # 映像名稱
    ports:      # 埠映射
    volumes:    # 資料卷掛載
    environment: # 環境變數
    depends_on: # 依賴關係
    networks:   # 網路配置
    deploy:     # 部署配置
    healthcheck: # 健康檢查

volumes:        # 資料卷定義
networks:       # 網路定義
configs:        # 配置定義
secrets:        # 密鑰定義
```

### 完整的生產級 Compose 範例

```yaml
version: "3.8"

# ========== 服務定義 ==========
services:

  # Nginx 反向代理
  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx-cache:/var/cache/nginx
      - nginx-logs:/var/log/nginx
    networks:
      - frontend
    depends_on:
      - web
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    labels:
      - "com.example.description=Nginx reverse proxy"
      - "com.example.department=ops"
      - "com.example.environment=production"

  # Web 應用
  web:
    build:
      context: ./app
      dockerfile: Dockerfile
      target: production
      args:
        - NODE_ENV=production
        - BUILD_DATE=${BUILD_DATE}
        - VERSION=${VERSION}
    image: myapp:${VERSION:-latest}
    container_name: web-app
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
      - DATABASE_URL=postgres://postgres:${DB_PASSWORD}@postgres:5432/myapp
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=${LOG_LEVEL:-info}
    env_file:
      - .env
    volumes:
      - app-logs:/app/logs
      - app-uploads:/app/uploads
    networks:
      - frontend
      - backend
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    healthcheck:
      test: ["CMD", "node", "healthcheck.js"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # PostgreSQL 資料庫
  postgres:
    image: postgres:15-alpine
    container_name: postgres-db
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=myapp
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./database/init:/docker-entrypoint-initdb.d:ro
      - ./database/backup:/backup
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 2G
    command:
      - "postgres"
      - "-c"
      - "max_connections=200"
      - "-c"
      - "shared_buffers=256MB"
      - "-c"
      - "effective_cache_size=1GB"

  # Redis 快取
  redis:
    image: redis:7-alpine
    container_name: redis-cache
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
    networks:
      - backend
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    command: redis-server /usr/local/etc/redis/redis.conf
    deploy:
      resources:
        limits:
          memory: 512M

  # 背景工作器
  worker:
    build:
      context: ./app
      dockerfile: Dockerfile
      target: production
    image: myapp:${VERSION:-latest}
    container_name: app-worker
    restart: unless-stopped
    environment:
      - NODE_ENV=production
      - WORKER_MODE=true
      - DATABASE_URL=postgres://postgres:${DB_PASSWORD}@postgres:5432/myapp
      - REDIS_URL=redis://redis:6379
    volumes:
      - app-logs:/app/logs
    networks:
      - backend
    depends_on:
      - postgres
      - redis
    command: ["node", "worker.js"]
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1.0'
          memory: 512M

  # 監控 - Prometheus
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus:/etc/prometheus:ro
      - prometheus-data:/prometheus
    networks:
      - monitoring
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'

  # 監控 - Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    networks:
      - monitoring
    depends_on:
      - prometheus

# ========== 資料卷定義 ==========
volumes:
  postgres-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./data/postgres
  redis-data:
  app-logs:
  app-uploads:
  nginx-cache:
  nginx-logs:
  prometheus-data:
  grafana-data:

# ========== 網路定義 ==========
networks:
  frontend:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
  backend:
    driver: bridge
    internal: true
    ipam:
      config:
        - subnet: 172.21.0.0/24
  monitoring:
    driver: bridge
```

### Compose 環境變數管理

**.env 檔案範例：**

```bash
# 應用版本
VERSION=1.0.0
BUILD_DATE=2023-12-01

# 資料庫設定
DB_PASSWORD=your_secure_password_here
POSTGRES_VERSION=15

# Redis 設定
REDIS_PASSWORD=your_redis_password

# 應用設定
NODE_ENV=production
LOG_LEVEL=info
JWT_SECRET=your_jwt_secret

# Grafana 設定
GRAFANA_PASSWORD=admin_password

# 其他設定
TZ=Asia/Taipei
```

### Compose 實用指令

```bash
# 啟動所有服務（背景運行）
docker-compose up -d

# 查看服務狀態
docker-compose ps

# 查看日誌（實時）
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f web

# 進入服務容器
docker-compose exec web bash

# 擴展服務
docker-compose up -d --scale worker=3

# 重新建立並啟動
docker-compose up -d --build

# 停止並刪除所有資源
docker-compose down

# 停止並刪除（包含資料卷）
docker-compose down -v

# 驗證配置檔
docker-compose config

# 只建立映像
docker-compose build

# 拉取所有映像
docker-compose pull

# 重啟特定服務
docker-compose restart web

# 查看資源使用
docker-compose top
```

## 🔐 容器安全性最佳實踐

### 安全性檢查清單

| 類別 | 檢查項目 | 實施方法 |
|------|----------|----------|
| **基礎映像** | 使用最小化映像 | Alpine, Distroless |
| **漏洞掃描** | 定期掃描映像 | `docker scan`, Trivy |
| **非 root 使用者** | 不使用 root 運行 | USER 指令 |
| **密鑰管理** | 不在映像中存儲密鑰 | Docker Secrets, 環境變數 |
| **網路隔離** | 最小權限網路 | 自訂網路, 防火牆規則 |
| **資源限制** | 限制CPU和記憶體 | deploy.resources |
| **唯讀檔案系統** | 盡可能使用唯讀 | --read-only |
| **能力限制** | 移除不必要的能力 | --cap-drop |

### 1. 使用非 root 使用者

```dockerfile
# ❌ 不推薦：使用 root 使用者
FROM nginx:alpine
COPY app /usr/share/nginx/html

# ✅ 推薦：創建並使用非 root 使用者
FROM nginx:alpine

# 創建使用者和群組
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# 設定檔案權限
COPY --chown=appuser:appgroup app /app

# 切換使用者
USER appuser

# 使用非特權埠
EXPOSE 8080
```

### 2. 最小化映像攻擊面

```dockerfile
# 使用最小化基礎映像
FROM gcr.io/distroless/nodejs18-debian11

# 或使用 Alpine
FROM node:18-alpine

# 移除不必要的套件
RUN apk del apk-tools && \
    rm -rf /var/cache/apk/*

# 唯讀檔案系統
# docker run --read-only --tmpfs /tmp myapp
```

### 3. 密鑰管理

```bash
# 使用 Docker Secrets（Swarm 模式）
echo "my_secret_password" | docker secret create db_password -

# 在 Compose 中使用
version: "3.8"
services:
  app:
    image: myapp
    secrets:
      - db_password
secrets:
  db_password:
    external: true

# 在應用中讀取
# cat /run/secrets/db_password
```

### 4. 映像掃描

```bash
# 使用 Docker Scan
docker scan myapp:latest

# 使用 Trivy
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest \
  image myapp:latest

# 使用 Clair
docker run -p 6060:6060 -d --name clair-db postgres:latest
docker run -p 6061:6061 --link clair-db:postgres -d quay.io/coreos/clair:latest
```

### 5. 容器運行時安全

```bash
# 限制容器能力
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE myapp

# 使用安全選項
docker run \
  --security-opt=no-new-privileges:true \
  --security-opt=apparmor=docker-default \
  myapp

# 唯讀根檔案系統
docker run --read-only --tmpfs /tmp --tmpfs /run myapp

# 資源限制
docker run \
  --memory="512m" \
  --cpus="1.0" \
  --pids-limit=100 \
  myapp
```

## ⚡ 效能優化策略

### 映像大小優化

```mermaid
graph TB
    A[映像優化策略] --> B[選擇精簡基礎映像]
    A --> C[多階段建立]
    A --> D[合併 RUN 指令]
    A --> E[清理快取與臨時檔案]
    A --> F[使用 .dockerignore]

    B --> B1[Alpine: ~5-10MB<br/>Distroless: ~20-50MB]
    C --> C1[只保留執行時檔案<br/>減少 80-95%]
    D --> D1[減少層數<br/>優化快取]
    E --> E1[減少 10-30%]
    F --> F1[加快建立速度<br/>減少內容]

    style A fill:#4ecdc4
```

**優化前後對照：**

| 項目 | 優化前 | 優化後 | 改善 |
|------|--------|--------|------|
| **映像大小** | 1.5 GB | 150 MB | 90% |
| **建立時間** | 10 分鐘 | 2 分鐘 | 80% |
| **層數** | 25 層 | 8 層 | 68% |
| **啟動時間** | 30 秒 | 3 秒 | 90% |

### 建立優化技巧

```dockerfile
# 1. 使用 BuildKit（Docker 18.09+）
# export DOCKER_BUILDKIT=1

# 2. 使用快取掛載（BuildKit）
FROM golang:1.21-alpine
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -o app

# 3. 使用秘密掛載
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm install

# 4. 並行化建立步驟
FROM base AS deps-stage1
RUN npm install package1

FROM base AS deps-stage2
RUN npm install package2

FROM base AS final
COPY --from=deps-stage1 /app/node_modules ./
COPY --from=deps-stage2 /app/node_modules ./
```

### 容器運行時優化

```yaml
# docker-compose.yml 效能配置
version: "3.8"

services:
  app:
    image: myapp:latest
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
    # 使用主機網路（效能最佳）
    network_mode: "host"
    # 或使用自訂網路
    networks:
      - app-network
    # IPC 模式
    ipc: "shareable"
    # 日誌配置
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        compress: "true"
```

### 網路效能優化

```bash
# 1. 使用主機網路（最佳效能）
docker run --network host myapp

# 2. 自訂 MTU
docker network create --opt com.docker.network.driver.mtu=9000 mynetwork

# 3. 禁用 iptables（內部網路）
docker network create --internal mynetwork

# 4. 使用 overlay 網路（Swarm）
docker network create --driver overlay --attachable mynetwork
```

## 🚀 生產環境部署策略

### 部署架構

```mermaid
graph TB
    subgraph "負載均衡層"
        LB[Load Balancer<br/>Nginx/HAProxy]
    end

    subgraph "應用層"
        APP1[App Container 1]
        APP2[App Container 2]
        APP3[App Container 3]
    end

    subgraph "資料層"
        DB[(PostgreSQL<br/>Primary)]
        REDIS[(Redis<br/>Cache)]
        DB2[(PostgreSQL<br/>Replica)]
    end

    subgraph "監控層"
        PROM[Prometheus]
        GRAF[Grafana]
        ALERT[AlertManager]
    end

    LB --> APP1
    LB --> APP2
    LB --> APP3

    APP1 --> DB
    APP2 --> DB
    APP3 --> DB

    APP1 --> REDIS
    APP2 --> REDIS
    APP3 --> REDIS

    DB --> DB2

    PROM --> APP1
    PROM --> APP2
    PROM --> APP3
    PROM --> DB
    PROM --> REDIS

    GRAF --> PROM
    ALERT --> PROM

    style LB fill:#4ecdc4
    style DB fill:#ff6b6b
    style PROM fill:#feca57
```

### 高可用性配置

```yaml
version: "3.8"

services:
  # 應用服務（多實例）
  app:
    image: myapp:${VERSION}
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
        order: start-first
      rollback_config:
        parallelism: 1
        delay: 5s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
      placement:
        constraints:
          - node.role == worker
        preferences:
          - spread: node.labels.zone
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s

  # 資料庫（主從複製）
  postgres-primary:
    image: postgres:15
    environment:
      - POSTGRES_REPLICATION_MODE=master
    volumes:
      - postgres-primary-data:/var/lib/postgresql/data
    deploy:
      placement:
        constraints:
          - node.labels.database == primary

  postgres-replica:
    image: postgres:15
    environment:
      - POSTGRES_REPLICATION_MODE=slave
      - POSTGRES_MASTER_HOST=postgres-primary
    volumes:
      - postgres-replica-data:/var/lib/postgresql/data
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.labels.database == replica
```

### 滾動更新策略

```bash
# Docker Swarm 滾動更新
docker service update \
  --image myapp:v2.0 \
  --update-parallelism 1 \
  --update-delay 10s \
  --update-failure-action rollback \
  myapp

# 使用 Compose
docker-compose up -d --no-deps --build app

# 藍綠部署
# 1. 部署綠色環境
docker-compose -f docker-compose.green.yml up -d

# 2. 測試綠色環境
curl http://green.example.com/health

# 3. 切換流量（更新 Nginx 配置）
docker exec nginx nginx -s reload

# 4. 停止藍色環境
docker-compose -f docker-compose.blue.yml down
```

### 監控與日誌

```yaml
# Prometheus 配置
version: "3.8"

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
    ports:
      - "9090:9090"

  # 應用暴露 metrics
  app:
    image: myapp:latest
    environment:
      - METRICS_ENABLED=true
    ports:
      - "3000:3000"
      - "9100:9100"  # Metrics 埠

  # Node Exporter
  node-exporter:
    image: prom/node-exporter:latest
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'

  # cAdvisor（容器監控）
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    ports:
      - "8080:8080"
```

## 🎯 CI/CD 整合實踐

### GitLab CI 範例

```yaml
# .gitlab-ci.yml
stages:
  - test
  - build
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  IMAGE_NAME: ${CI_REGISTRY_IMAGE}:${CI_COMMIT_SHORT_SHA}

# 測試階段
test:
  stage: test
  image: node:18-alpine
  script:
    - npm ci
    - npm run test
    - npm run lint
  coverage: '/Statements\s+:\s+(\d+\.\d+)%/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml

# 建立映像
build:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build --pull -t $IMAGE_NAME .
    - docker tag $IMAGE_NAME ${CI_REGISTRY_IMAGE}:latest
    - docker push $IMAGE_NAME
    - docker push ${CI_REGISTRY_IMAGE}:latest
  only:
    - main
    - develop

# 部署到開發環境
deploy-dev:
  stage: deploy
  image: docker/compose:latest
  before_script:
    - apk add --no-cache openssh-client
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
    - mkdir -p ~/.ssh
    - chmod 700 ~/.ssh
    - ssh-keyscan $DEV_SERVER_IP >> ~/.ssh/known_hosts
  script:
    - ssh $DEV_USER@$DEV_SERVER_IP "
        cd /app &&
        docker-compose pull app &&
        docker-compose up -d app
      "
  environment:
    name: development
    url: https://dev.example.com
  only:
    - develop

# 部署到生產環境
deploy-prod:
  stage: deploy
  image: docker/compose:latest
  before_script:
    - apk add --no-cache openssh-client
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
  script:
    - ssh $PROD_USER@$PROD_SERVER_IP "
        cd /app &&
        docker-compose pull app &&
        docker-compose up -d --no-deps app
      "
  environment:
    name: production
    url: https://example.com
  when: manual
  only:
    - main
```

### GitHub Actions 範例

```yaml
# .github/workflows/docker-build.yml
name: Docker Build and Push

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test

      - name: Run linter
        run: npm run lint

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-

      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - name: Deploy to production
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /app
            docker-compose pull
            docker-compose up -d --no-deps app
            docker system prune -f
```

## 📊 總結與最佳實踐清單

### 核心知識回顧

本系列文章涵蓋了 Docker 從入門到實戰的完整內容：

**第一篇：基礎概念**
- Docker 架構與核心元件
- 容器 vs 虛擬機
- 安裝與配置

**第二篇：指令操作**
- 容器生命週期管理
- 映像操作技巧
- 網路與儲存配置

**第三篇：進階實踐**（本篇）
- Dockerfile 優化
- 多階段建立
- Docker Compose 編排
- 安全性與效能
- 生產環境部署

### Docker 最佳實踐檢查清單

#### 📝 開發階段

- [ ] 使用 .dockerignore 排除不必要的檔案
- [ ] 利用建立快取優化建立速度
- [ ] 使用 Bind Mount 實現程式碼熱重載
- [ ] 為映像添加明確的標籤版本
- [ ] 使用 Docker Compose 管理多容器應用

#### 🏗️ 映像建立

- [ ] 選擇最小化的基礎映像（Alpine, Distroless）
- [ ] 使用多階段建立減少映像大小
- [ ] 合併 RUN 指令減少層數
- [ ] 在每個 RUN 末尾清理快取和臨時檔案
- [ ] 先複製依賴檔案，再複製原始碼（快取優化）
- [ ] 使用非 root 使用者運行容器
- [ ] 添加健康檢查（HEALTHCHECK）
- [ ] 使用 LABEL 添加元資料

#### 🔐 安全性

- [ ] 定期掃描映像漏洞
- [ ] 不在映像中存儲敏感資訊
- [ ] 使用 Docker Secrets 管理密鑰
- [ ] 限制容器能力（--cap-drop）
- [ ] 使用唯讀檔案系統
- [ ] 設定資源限制（CPU、記憶體）
- [ ] 使用官方或可信的基礎映像
- [ ] 定期更新基礎映像

#### 🌐 網路配置

- [ ] 使用自訂網路替代預設 bridge
- [ ] 為服務設定有意義的網路別名
- [ ] 後端服務使用內部網路（internal）
- [ ] 最小化暴露的埠
- [ ] 使用反向代理（Nginx, Traefik）

#### 💾 資料管理

- [ ] 使用 Volume 而非 Bind Mount 持久化資料
- [ ] 為 Volume 使用有意義的命名
- [ ] 定期備份重要資料
- [ ] 避免在容器內存儲狀態
- [ ] 使用外部儲存服務（S3, NFS）

#### 🚀 生產部署

- [ ] 設定容器重啟策略（restart: unless-stopped）
- [ ] 實作健康檢查和就緒探測
- [ ] 配置日誌輪替避免磁碟填滿
- [ ] 使用滾動更新策略
- [ ] 準備回滾方案
- [ ] 實作監控和告警（Prometheus, Grafana）
- [ ] 設定資源限制和預留
- [ ] 文件化部署流程

#### 📊 監控與維護

- [ ] 收集並分析容器日誌
- [ ] 監控容器資源使用（CPU、記憶體、網路）
- [ ] 設定關鍵指標告警
- [ ] 定期清理未使用的映像和容器
- [ ] 追蹤映像大小變化
- [ ] 測試災難恢復流程

### 常見錯誤與解決方案

| 問題 | 原因 | 解決方案 |
|------|------|----------|
| **映像太大** | 包含不必要的檔案和工具 | 使用多階段建立、Alpine 映像 |
| **建立緩慢** | 沒有優化快取層 | 調整 Dockerfile 指令順序 |
| **容器無法啟動** | 權限或依賴問題 | 檢查日誌、使用健康檢查 |
| **資料遺失** | 未使用 Volume | 使用 Volume 持久化資料 |
| **網路連接失敗** | 網路配置錯誤 | 檢查網路設定和防火牆 |
| **效能不佳** | 資源限制不當 | 調整 CPU、記憶體限制 |
| **安全漏洞** | 使用過時映像 | 定期更新和掃描映像 |

### 學習資源推薦

**官方文件**
- [Docker 官方文件](https://docs.docker.com/)
- [Docker Hub](https://hub.docker.com/)
- [Docker Compose 文件](https://docs.docker.com/compose/)

**進階學習**
- Docker 認證考試（DCA）
- Kubernetes（容器編排）
- Docker Swarm（集群管理）
- Helm（Kubernetes 套件管理）

**社群與工具**
- Docker Community Forums
- GitHub Docker 範例專案
- Play with Docker（線上實驗環境）
- Portainer（容器管理 UI）

## 🎉 結語

Docker 容器技術已經成為現代軟體開發和部署的標準工具。透過本系列三篇文章的學習，您已經掌握了：

1. **基礎知識**：理解容器化的概念和 Docker 架構
2. **實務操作**：熟練使用 Docker CLI 管理容器和映像
3. **進階技能**：掌握 Dockerfile 優化、Compose 編排和生產部署

### 下一步建議

- **實踐專案**：將現有專案容器化
- **學習編排**：深入學習 Kubernetes 或 Docker Swarm
- **持續優化**：關注效能和安全性
- **社群參與**：貢獻開源專案，分享經驗

Docker 的學習是一個持續的過程，隨著實踐經驗的累積，您將能夠構建更高效、更安全、更可靠的容器化應用。

祝您在容器化技術的道路上不斷進步！🚀
