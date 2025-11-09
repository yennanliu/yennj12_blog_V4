---
title: "Kubernetes Autoscaling Complete Guide (Part 6): Advanced Autoscaling Patterns"
date: 2025-11-09T22:00:00+08:00
draft: false
authors: ["yennj12 team"]
categories: ["all", "engineering", "devops", "kubernetes", "architecture"]
tags: ["Kubernetes", "K8S", "Autoscaling", "StatefulSet", "Multi-Cluster", "Cost Optimization", "Spot Instances", "FinOps", "Advanced Patterns", "Batch Jobs"]
summary: "Part 6 of the Kubernetes Autoscaling series: Advanced autoscaling patterns for stateful applications, multi-cluster deployments, cost optimization strategies, batch job scaling, and emerging technologies. Real-world architectures and production-grade implementations."
readTime: "40 min"
---

## Series Overview

This is **Part 6** of the Kubernetes Autoscaling Complete Guide series:

- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Application-level autoscaling theory
- **[Part 2: Cluster Autoscaling & Cloud Providers](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Infrastructure-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Practical implementation
- **[Part 4: Monitoring, Alerting & Threshold Tuning](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)** - Production observability
- **[Part 5: VPA & Resource Optimization](./kubernetes-autoscaling-complete-guide-part5-vpa-resource-optimization.md)** - Right-sizing strategies
- **Part 6 (This Post)**: Advanced Autoscaling Patterns - Stateful apps, multi-cluster, cost optimization

---

Beyond basic HPA and cluster autoscaling, production Kubernetes deployments require sophisticated patterns for stateful workloads, multi-cluster architectures, aggressive cost optimization, and specialized workload types. This guide explores advanced autoscaling strategies used by leading organizations.

## Pattern 1: Stateful Application Autoscaling

### The StatefulSet Challenge

```
Traditional HPA with StatefulSets:
┌────────────────────────────────────────────────────────────┐
│  CHALLENGES                                                │
│                                                             │
│  1. Ordered Pod Creation/Deletion                          │
│     • pod-0 must exist before pod-1                        │
│     • Slow scale-up during traffic spikes                  │
│                                                             │
│  2. Persistent Volumes                                      │
│     • Each pod has unique PVC                              │
│     • Storage costs accumulate                             │
│     • PVCs remain after scale-down                         │
│                                                             │
│  3. State Synchronization                                   │
│     • New pods must sync state (databases, caches)         │
│     • Sync time adds to scale-up latency                   │
│     • Potential data consistency issues                    │
│                                                             │
│  4. Service Discovery                                       │
│     • Clients must discover new pods                       │
│     • DNS updates take time                                │
│     • Connection draining needed on scale-down             │
└────────────────────────────────────────────────────────────┘
```

### Pattern 1A: Database Scaling with StatefulSet

**Scenario:** PostgreSQL cluster with read replicas that scale based on read query load.

```yaml
# PostgreSQL StatefulSet
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres-replicas
  namespace: databases
spec:
  serviceName: postgres-replicas
  replicas: 2  # Initial: 1 primary + 1 replica

  selector:
    matchLabels:
      app: postgres
      role: replica

  template:
    metadata:
      labels:
        app: postgres
        role: replica
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9187"  # postgres_exporter
    spec:
      initContainers:
      # Initialize replica from primary
      - name: init-replica
        image: postgres:15
        command:
        - bash
        - -c
        - |
          if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
            # Clone from primary
            pg_basebackup -h postgres-primary -D /var/lib/postgresql/data -U replication -v -P
            # Create recovery signal
            touch /var/lib/postgresql/data/standby.signal
          fi
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data

      containers:
      # PostgreSQL replica
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_USER
          value: postgres
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata

        ports:
        - containerPort: 5432
          name: postgres

        resources:
          requests:
            cpu: 1
            memory: 2Gi
          limits:
            cpu: 4
            memory: 8Gi

        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        - name: config
          mountPath: /etc/postgresql/postgresql.conf
          subPath: postgresql.conf

      # Postgres Exporter for metrics
      - name: postgres-exporter
        image: prometheuscommunity/postgres-exporter:latest
        env:
        - name: DATA_SOURCE_NAME
          value: "postgresql://postgres:$(POSTGRES_PASSWORD)@localhost:5432/postgres?sslmode=disable"
        ports:
        - containerPort: 9187
          name: metrics
        resources:
          requests:
            cpu: 100m
            memory: 128Mi

      volumes:
      - name: config
        configMap:
          name: postgres-config

  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: gp3-encrypted
      resources:
        requests:
          storage: 100Gi

---
# Headless service for StatefulSet
apiVersion: v1
kind: Service
metadata:
  name: postgres-replicas
  namespace: databases
spec:
  clusterIP: None
  selector:
    app: postgres
    role: replica
  ports:
  - port: 5432
    name: postgres

---
# Regular service for read traffic (load balanced)
apiVersion: v1
kind: Service
metadata:
  name: postgres-read
  namespace: databases
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9187"
spec:
  type: ClusterIP
  selector:
    app: postgres
    role: replica
  ports:
  - port: 5432
    name: postgres

---
# HPA for read replicas based on custom metrics
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: postgres-replicas-hpa
  namespace: databases
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: postgres-replicas

  minReplicas: 2   # Always have at least 1 replica + 1 primary
  maxReplicas: 10  # Max read replicas

  metrics:
  # Scale based on active connections
  - type: Pods
    pods:
      metric:
        name: pg_stat_database_numbackends
      target:
        type: AverageValue
        averageValue: "50"  # 50 connections per replica

  # Scale based on replication lag
  - type: Pods
    pods:
      metric:
        name: pg_replication_lag_seconds
      target:
        type: AverageValue
        averageValue: "5"  # Keep lag under 5 seconds

  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60  # Wait 1 min before scale-up
      policies:
      - type: Pods
        value: 1                       # Add 1 replica at a time
        periodSeconds: 60
      selectPolicy: Min

    scaleDown:
      stabilizationWindowSeconds: 600  # Wait 10 min before scale-down
      policies:
      - type: Pods
        value: 1                        # Remove 1 replica at a time
        periodSeconds: 300              # Every 5 minutes
      selectPolicy: Min

---
# PrometheusRule for PostgreSQL monitoring
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: postgres-autoscaling-rules
  namespace: monitoring
spec:
  groups:
  - name: postgres-custom-metrics
    interval: 15s
    rules:
    # Active connections per pod
    - record: pg_stat_database_numbackends
      expr: |
        sum(pg_stat_database_numbackends{datname="postgres"}) by (pod, namespace)

    # Replication lag in seconds
    - record: pg_replication_lag_seconds
      expr: |
        pg_replication_lag

  - name: postgres-alerts
    rules:
    # Alert when replicas are at max
    - alert: PostgresReplicasMaxedOut
      expr: |
        (
          kube_statefulset_status_replicas{statefulset="postgres-replicas"}
          /
          kube_statefulset_spec_replicas{statefulset="postgres-replicas"}
        ) >= 0.9
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "PostgreSQL replicas near maximum capacity"
        description: "Consider increasing maxReplicas or optimizing queries"

    # Alert on high replication lag
    - alert: PostgresHighReplicationLag
      expr: pg_replication_lag_seconds > 30
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "PostgreSQL replication lag is high"
        description: "Replication lag is {{ $value }}s, may impact read consistency"
```

### Pattern 1B: Redis Cache Cluster Autoscaling

```yaml
# Redis Cluster with dynamic scaling
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
  namespace: caching
spec:
  serviceName: redis-cluster
  replicas: 6  # 3 master + 3 replica

  selector:
    matchLabels:
      app: redis-cluster

  template:
    metadata:
      labels:
        app: redis-cluster
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command:
        - redis-server
        args:
        - /conf/redis.conf
        - --cluster-enabled
        - "yes"
        - --cluster-config-file
        - /data/nodes.conf
        - --cluster-node-timeout
        - "5000"
        - --maxmemory
        - "2gb"
        - --maxmemory-policy
        - "allkeys-lru"

        ports:
        - containerPort: 6379
          name: client
        - containerPort: 16379
          name: gossip

        resources:
          requests:
            cpu: 500m
            memory: 2Gi
          limits:
            cpu: 2
            memory: 4Gi

        volumeMounts:
        - name: data
          mountPath: /data
        - name: conf
          mountPath: /conf

      # Redis Exporter sidecar
      - name: redis-exporter
        image: oliver006/redis_exporter:latest
        ports:
        - containerPort: 9121
          name: metrics
        resources:
          requests:
            cpu: 100m
            memory: 128Mi

  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi

---
# Custom Metrics based on Redis metrics
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-adapter-redis
  namespace: monitoring
data:
  config.yaml: |
    rules:
    # Redis memory usage percentage
    - seriesQuery: 'redis_memory_used_bytes'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        as: "redis_memory_usage_percentage"
      metricsQuery: |
        (redis_memory_used_bytes / redis_memory_max_bytes) * 100

    # Redis connected clients
    - seriesQuery: 'redis_connected_clients'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        as: "redis_clients_per_pod"
      metricsQuery: |
        sum(redis_connected_clients) by (pod, namespace)

    # Redis operations per second
    - seriesQuery: 'redis_instantaneous_ops_per_sec'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        as: "redis_ops_per_second"
      metricsQuery: |
        sum(rate(redis_commands_total[2m])) by (pod, namespace)

---
# HPA for Redis based on memory and ops
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: redis-cluster-hpa
  namespace: caching
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: redis-cluster

  minReplicas: 6   # Minimum cluster size (3 master + 3 replica)
  maxReplicas: 18  # Max 9 master + 9 replica

  metrics:
  # Memory usage
  - type: Pods
    pods:
      metric:
        name: redis_memory_usage_percentage
      target:
        type: AverageValue
        averageValue: "75"  # Scale when memory > 75%

  # Operations per second
  - type: Pods
    pods:
      metric:
        name: redis_ops_per_second
      target:
        type: AverageValue
        averageValue: "10000"  # Scale at 10k ops/sec per pod

  behavior:
    scaleUp:
      stabilizationWindowSeconds: 120
      policies:
      - type: Pods
        value: 2  # Add 2 pods at a time (1 master + 1 replica)
        periodSeconds: 120

    scaleDown:
      stabilizationWindowSeconds: 600
      policies:
      - type: Pods
        value: 2  # Remove 2 pods at a time
        periodSeconds: 300
```

### Key Considerations for Stateful Autoscaling

1. **Data Synchronization Time**: Account for data replication delays
2. **Ordered Scaling**: StatefulSets scale sequentially, slower than Deployments
3. **Storage Management**: Implement PVC cleanup policies
4. **State Warmup**: Consider warm-up time for caches/databases
5. **Split Read/Write**: Scale read replicas independently from write nodes

## Pattern 2: Multi-Cluster & Multi-Region Autoscaling

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│              MULTI-CLUSTER AUTOSCALING ARCHITECTURE                 │
│                                                                      │
│  ┌────────────────┐     ┌────────────────┐     ┌────────────────┐  │
│  │   REGION 1     │     │   REGION 2     │     │   REGION 3     │  │
│  │   (US-EAST)    │     │   (EU-WEST)    │     │   (AP-SOUTH)   │  │
│  │                │     │                │     │                │  │
│  │  EKS Cluster 1 │     │  EKS Cluster 2 │     │  EKS Cluster 3 │  │
│  │  • HPA         │     │  • HPA         │     │  • HPA         │  │
│  │  • Karpenter   │     │  • Karpenter   │     │  • Karpenter   │  │
│  │  • Local LB    │     │  • Local LB    │     │  • Local LB    │  │
│  └───────┬────────┘     └───────┬────────┘     └───────┬────────┘  │
│          │                      │                      │            │
│          └──────────────────────┴──────────────────────┘            │
│                               ↓                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │               GLOBAL LOAD BALANCER                             │ │
│  │                                                                 │ │
│  │  • Route 53 / CloudFlare / Global Accelerator                 │ │
│  │  • Geographic routing                                          │ │
│  │  • Latency-based routing                                       │ │
│  │  • Weighted routing (for gradual shifts)                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                               ↓                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │            CENTRALIZED AUTOSCALING CONTROLLER                  │ │
│  │                                                                 │ │
│  │  • Aggregate metrics from all clusters                         │ │
│  │  • Intelligent workload distribution                           │ │
│  │  • Cost-aware cluster selection                               │ │
│  │  • Capacity prediction                                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Pattern 2A: Federated HPA with Cluster API

```yaml
# Install Cluster API
---
apiVersion: v1
kind: Namespace
metadata:
  name: cluster-api-system

---
# Management cluster setup
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: workload-cluster-us-east
  namespace: default
spec:
  clusterNetwork:
    pods:
      cidrBlocks: ["192.168.0.0/16"]
  infrastructureRef:
    apiVersion: infrastructure.cluster.x-k8s.io/v1beta1
    kind: AWSCluster
    name: workload-cluster-us-east
  controlPlaneRef:
    kind: KubeadmControlPlane
    apiVersion: controlplane.cluster.x-k8s.io/v1beta1
    name: workload-cluster-us-east-control-plane

---
# Multi-cluster autoscaling with KubeFed
apiVersion: types.kubefed.io/v1beta1
kind: FederatedHorizontalPodAutoscaler
metadata:
  name: federated-app-hpa
  namespace: default
spec:
  # Target deployment across clusters
  placement:
    clusters:
    - name: us-east-1-cluster
      weight: 40
    - name: eu-west-1-cluster
      weight: 30
    - name: ap-south-1-cluster
      weight: 30

  template:
    spec:
      scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: my-app

      minReplicas: 3  # Per cluster minimum
      maxReplicas: 20 # Per cluster maximum

      metrics:
      - type: Resource
        resource:
          name: cpu
          target:
            type: Utilization
            averageUtilization: 70

  # Override for specific clusters
  overrides:
  - clusterName: us-east-1-cluster
    clusterOverrides:
    - path: "/spec/minReplicas"
      value: 5  # Higher baseline in primary region
    - path: "/spec/maxReplicas"
      value: 50

---
# Federated deployment
apiVersion: types.kubefed.io/v1beta1
kind: FederatedDeployment
metadata:
  name: my-app
  namespace: default
spec:
  placement:
    clusters:
    - name: us-east-1-cluster
    - name: eu-west-1-cluster
    - name: ap-south-1-cluster

  template:
    spec:
      replicas: 5
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
            image: myapp:v1.0
            resources:
              requests:
                cpu: 500m
                memory: 512Mi
```

### Pattern 2B: Custom Multi-Cluster Autoscaler

```go
// Custom multi-cluster autoscaling controller
package main

import (
    "context"
    "fmt"
    "time"

    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/client-go/kubernetes"
    "k8s.io/client-go/tools/clientcmd"
)

type ClusterConfig struct {
    Name           string
    KubeConfig     string
    Region         string
    CostPerCPUHour float64
    Latency        time.Duration
}

type MultiClusterAutoscaler struct {
    clusters map[string]*kubernetes.Clientset
    configs  []ClusterConfig
}

func NewMultiClusterAutoscaler(configs []ClusterConfig) (*MultiClusterAutoscaler, error) {
    mca := &MultiClusterAutoscaler{
        clusters: make(map[string]*kubernetes.Clientset),
        configs:  configs,
    }

    // Initialize clients for each cluster
    for _, config := range configs {
        clientConfig, err := clientcmd.BuildConfigFromFlags("", config.KubeConfig)
        if err != nil {
            return nil, err
        }

        clientset, err := kubernetes.NewForConfig(clientConfig)
        if err != nil {
            return nil, err
        }

        mca.clusters[config.Name] = clientset
    }

    return mca, nil
}

// Decision algorithm: cost-aware + latency-aware scaling
func (mca *MultiClusterAutoscaler) ScaleDecision(
    ctx context.Context,
    totalReplicas int,
    userRegion string,
) (map[string]int, error) {

    allocation := make(map[string]int)

    // Step 1: Get current capacity in each cluster
    capacities := make(map[string]int)
    for name, client := range mca.clusters {
        nodes, err := client.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
        if err != nil {
            return nil, err
        }

        // Calculate available capacity
        var availableCPU int64
        for _, node := range nodes.Items {
            availableCPU += node.Status.Allocatable.Cpu().MilliValue()
        }
        capacities[name] = int(availableCPU / 500) // Assume 500m per pod
    }

    // Step 2: Cost-aware allocation
    // Prioritize cheapest region first
    sortedConfigs := sortByCost(mca.configs)

    remaining := totalReplicas
    for _, config := range sortedConfigs {
        available := capacities[config.Name]

        // Allocate up to available capacity
        allocated := min(remaining, available)
        allocation[config.Name] = allocated
        remaining -= allocated

        if remaining == 0 {
            break
        }
    }

    // Step 3: Latency-aware adjustment
    // If user is in specific region, ensure minimum local replicas
    if userRegion != "" {
        minLocal := max(3, totalReplicas/10) // At least 10% or 3 replicas
        if allocation[userRegion] < minLocal {
            allocation[userRegion] = minLocal
        }
    }

    return allocation, nil
}

// Apply scaling decisions to clusters
func (mca *MultiClusterAutoscaler) ApplyScaling(
    ctx context.Context,
    allocation map[string]int,
    deployment string,
    namespace string,
) error {

    for clusterName, replicas := range allocation {
        client := mca.clusters[clusterName]

        // Update deployment replica count
        scale, err := client.AppsV1().Deployments(namespace).
            GetScale(ctx, deployment, metav1.GetOptions{})
        if err != nil {
            return fmt.Errorf("failed to get scale for %s in %s: %v",
                deployment, clusterName, err)
        }

        scale.Spec.Replicas = int32(replicas)

        _, err = client.AppsV1().Deployments(namespace).
            UpdateScale(ctx, deployment, scale, metav1.UpdateOptions{})
        if err != nil {
            return fmt.Errorf("failed to update scale for %s in %s: %v",
                deployment, clusterName, err)
        }

        fmt.Printf("Scaled %s in %s to %d replicas\n",
            deployment, clusterName, replicas)
    }

    return nil
}

func main() {
    configs := []ClusterConfig{
        {
            Name:           "us-east-1",
            KubeConfig:     "/home/user/.kube/us-east-1",
            Region:         "us-east-1",
            CostPerCPUHour: 0.04,
            Latency:        50 * time.Millisecond,
        },
        {
            Name:           "eu-west-1",
            KubeConfig:     "/home/user/.kube/eu-west-1",
            Region:         "eu-west-1",
            CostPerCPUHour: 0.045,
            Latency:        100 * time.Millisecond,
        },
        {
            Name:           "ap-south-1",
            KubeConfig:     "/home/user/.kube/ap-south-1",
            Region:         "ap-south-1",
            CostPerCPUHour: 0.038, // Cheapest
            Latency:        150 * time.Millisecond,
        },
    }

    autoscaler, err := NewMultiClusterAutoscaler(configs)
    if err != nil {
        panic(err)
    }

    ctx := context.Background()

    // Main reconciliation loop
    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    for range ticker.C {
        // Get total desired replicas from global metrics
        totalReplicas := calculateGlobalReplicas()

        // Determine optimal allocation
        allocation, err := autoscaler.ScaleDecision(
            ctx,
            totalReplicas,
            "us-east-1", // Primary user region
        )
        if err != nil {
            fmt.Printf("Error in scale decision: %v\n", err)
            continue
        }

        // Apply scaling
        err = autoscaler.ApplyScaling(
            ctx,
            allocation,
            "my-app",
            "production",
        )
        if err != nil {
            fmt.Printf("Error applying scaling: %v\n", err)
        }
    }
}

func calculateGlobalReplicas() int {
    // Aggregate metrics from all clusters
    // Calculate desired total replicas
    // This would query Prometheus/Thanos for global metrics
    return 50 // Placeholder
}

func sortByCost(configs []ClusterConfig) []ClusterConfig {
    // Sort by cost (cheapest first)
    sorted := make([]ClusterConfig, len(configs))
    copy(sorted, configs)
    // ... sorting logic
    return sorted
}

func min(a, b int) int {
    if a < b {
        return a
    }
    return b
}

func max(a, b int) int {
    if a > b {
        return a
    }
    return b
}
```

### Pattern 2C: Global Metrics Aggregation with Thanos

```yaml
# Thanos setup for multi-cluster metrics
---
# Thanos Sidecar on each cluster's Prometheus
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: prometheus
  namespace: monitoring
spec:
  template:
    spec:
      containers:
      # Prometheus
      - name: prometheus
        image: prom/prometheus:latest
        args:
        - --storage.tsdb.path=/prometheus
        - --storage.tsdb.min-block-duration=2h
        - --storage.tsdb.max-block-duration=2h
        volumeMounts:
        - name: storage
          mountPath: /prometheus

      # Thanos Sidecar
      - name: thanos-sidecar
        image: thanosio/thanos:latest
        args:
        - sidecar
        - --prometheus.url=http://localhost:9090
        - --tsdb.path=/prometheus
        - --objstore.config-file=/etc/thanos/objstore.yaml
        - --grpc-address=0.0.0.0:10901
        volumeMounts:
        - name: storage
          mountPath: /prometheus
        - name: objstore-config
          mountPath: /etc/thanos
        ports:
        - containerPort: 10901
          name: grpc

---
# Thanos Query (global query layer)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: thanos-query
  namespace: monitoring
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: thanos-query
        image: thanosio/thanos:latest
        args:
        - query
        - --http-address=0.0.0.0:9090
        - --grpc-address=0.0.0.0:10901
        # Connect to all cluster Prometheus instances
        - --store=prometheus-us-east-1.monitoring.svc.cluster.local:10901
        - --store=prometheus-eu-west-1.monitoring.svc.cluster.local:10901
        - --store=prometheus-ap-south-1.monitoring.svc.cluster.local:10901
        - --query.replica-label=replica
        ports:
        - containerPort: 9090
          name: http
        - containerPort: 10901
          name: grpc

---
# Global HPA using Thanos metrics
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-adapter-thanos
  namespace: monitoring
data:
  config.yaml: |
    rules:
    # Global request rate across all clusters
    - seriesQuery: 'http_requests_total{job="my-app"}'
      resources:
        template: <<.Resource>>
      name:
        as: "global_requests_per_second"
      metricsQuery: |
        sum(rate(http_requests_total{job="my-app"}[2m]))

    # Global CPU usage
    - seriesQuery: 'container_cpu_usage_seconds_total{pod=~"my-app.*"}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
      name:
        as: "global_cpu_usage"
      metricsQuery: |
        sum(rate(container_cpu_usage_seconds_total{pod=~"my-app.*"}[5m]))
```

## Pattern 3: Aggressive Cost Optimization

### Spot Instance Strategy with Multiple Fallbacks

```yaml
# Karpenter NodePool with spot + on-demand mix
---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: cost-optimized-spot
spec:
  template:
    metadata:
      labels:
        workload-type: spot-eligible
        cost-optimized: "true"
    spec:
      requirements:
      # Maximize spot instance types for availability
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot"]

      # Allow wide range of instance types
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["c", "m", "r", "t"]  # Compute, general, memory, burstable

      - key: karpenter.k8s.aws/instance-generation
        operator: Gt
        values: ["4"]  # Generation 5+

      # Size flexibility
      - key: karpenter.k8s.aws/instance-size
        operator: In
        values: ["large", "xlarge", "2xlarge", "4xlarge"]

      nodeClassRef:
        name: cost-optimized

  # Aggressive consolidation
  disruption:
    consolidationPolicy: WhenUnderutilized
    consolidateAfter: 30s
    expireAfter: 12h  # Refresh nodes every 12 hours

  limits:
    cpu: "500"
    memory: 1000Gi

---
# On-demand fallback NodePool
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: on-demand-fallback
spec:
  template:
    metadata:
      labels:
        workload-type: on-demand-fallback
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["on-demand"]

      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["m", "c"]

      nodeClassRef:
        name: cost-optimized

  weight: 10  # Lower priority, used when spot unavailable

  limits:
    cpu: "200"

---
# Application deployment with spot tolerance
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cost-sensitive-app
  namespace: production
spec:
  replicas: 10
  template:
    spec:
      # Prefer spot nodes
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: karpenter.sh/capacity-type
                operator: In
                values: ["spot"]

          # Fallback to on-demand if needed
          - weight: 50
            preference:
              matchExpressions:
              - key: workload-type
                operator: In
                values: ["on-demand-fallback"]

      # Tolerate spot interruptions
      tolerations:
      - key: karpenter.sh/disruption
        operator: Exists
        effect: NoSchedule

      # Topology spread for availability
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: cost-sensitive-app

      containers:
      - name: app
        image: myapp:v1.0
        resources:
          requests:
            cpu: 500m
            memory: 512Mi

---
# PDB to handle spot interruptions gracefully
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cost-sensitive-app-pdb
  namespace: production
spec:
  minAvailable: 70%  # Keep 70% pods running during spot interruptions
  selector:
    matchLabels:
      app: cost-sensitive-app
```

### Cost-Aware Scheduling with Custom Scheduler

```go
// Custom scheduler plugin for cost-aware pod placement
package main

import (
    "context"
    "fmt"

    v1 "k8s.io/api/core/v1"
    "k8s.io/apimachinery/pkg/runtime"
    "k8s.io/kubernetes/pkg/scheduler/framework"
)

type CostAwarePlugin struct {
    handle framework.Handle
}

var _ framework.ScorePlugin = &CostAwarePlugin{}

// Pricing data (could be fetched from external API)
var instancePricing = map[string]float64{
    "t3.large":     0.0832,
    "m5.large":     0.096,
    "c5.large":     0.085,
    "m5.xlarge":    0.192,
    "c5.xlarge":    0.17,
    "r5.large":     0.126,
    "spot-t3.large": 0.0250,  // ~70% savings
    "spot-m5.large": 0.0288,
    "spot-c5.large": 0.0255,
}

func (c *CostAwarePlugin) Name() string {
    return "CostAwarePlugin"
}

// Score nodes based on cost
func (c *CostAwarePlugin) Score(
    ctx context.Context,
    state *framework.CycleState,
    pod *v1.Pod,
    nodeName string,
) (int64, *framework.Status) {

    nodeInfo, err := c.handle.SnapshotSharedLister().NodeInfos().Get(nodeName)
    if err != nil {
        return 0, framework.NewStatus(framework.Error, fmt.Sprintf("getting node %q: %v", nodeName, err))
    }

    node := nodeInfo.Node()

    // Get instance type from node labels
    instanceType := node.Labels["node.kubernetes.io/instance-type"]
    capacityType := node.Labels["karpenter.sh/capacity-type"]

    // Determine pricing key
    pricingKey := instanceType
    if capacityType == "spot" {
        pricingKey = "spot-" + instanceType
    }

    // Get cost
    cost, exists := instancePricing[pricingKey]
    if !exists {
        cost = 0.1 // Default cost if unknown
    }

    // Convert to score (lower cost = higher score)
    // Normalize: max price 0.2, min price 0.02
    // Score range: 0-100
    normalizedCost := (cost - 0.02) / (0.2 - 0.02)
    score := int64((1 - normalizedCost) * 100)

    // Bonus for spot instances
    if capacityType == "spot" {
        score += 20
    }

    return score, framework.NewStatus(framework.Success)
}

// ScoreExtensions of the Score plugin
func (c *CostAwarePlugin) ScoreExtensions() framework.ScoreExtensions {
    return c
}

// NormalizeScore is called after scoring all nodes
func (c *CostAwarePlugin) NormalizeScore(
    ctx context.Context,
    state *framework.CycleState,
    pod *v1.Pod,
    scores framework.NodeScoreList,
) *framework.Status {
    // Scores are already normalized in Score()
    return framework.NewStatus(framework.Success)
}

func New(_ runtime.Object, h framework.Handle) (framework.Plugin, error) {
    return &CostAwarePlugin{handle: h}, nil
}
```

### FinOps Dashboard and Automation

```yaml
# CronJob for daily cost optimization report
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cost-optimization-report
  namespace: finops
spec:
  schedule: "0 9 * * *"  # Daily at 9 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: finops-reporter
          containers:
          - name: reporter
            image: finops-reporter:latest
            env:
            - name: PROMETHEUS_URL
              value: "http://prometheus.monitoring:9090"
            - name: SLACK_WEBHOOK
              valueFrom:
                secretKeyRef:
                  name: slack-webhook
                  key: url
            command:
            - /bin/bash
            - -c
            - |
              #!/bin/bash

              echo "=== Daily Cost Optimization Report ==="
              echo ""

              # Calculate total cluster cost
              TOTAL_CPU=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=sum(kube_pod_container_resource_requests{resource='cpu'})" | jq -r '.data.result[0].value[1]')
              TOTAL_MEM=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=sum(kube_pod_container_resource_requests{resource='memory'})" | jq -r '.data.result[0].value[1]')

              CPU_COST=$(echo "$TOTAL_CPU * 0.04 * 24" | bc)
              MEM_COST=$(echo "$TOTAL_MEM / 1073741824 * 0.005 * 24" | bc)
              DAILY_COST=$(echo "$CPU_COST + $MEM_COST" | bc)

              echo "Daily Cost: \$${DAILY_COST}"
              echo ""

              # Identify optimization opportunities
              echo "=== Optimization Opportunities ==="

              # Over-provisioned workloads (VPA recommendations)
              curl -s "$PROMETHEUS_URL/api/v1/query?query=(kube_pod_container_resource_requests{resource='cpu'} - on(pod) kube_verticalpodautoscaler_status_recommendation_containerrecommendations_target{resource='cpu'}) / kube_pod_container_resource_requests{resource='cpu'} > 0.5" \
                | jq -r '.data.result[] | "\(.metric.namespace)/\(.metric.pod): \(.value[1] * 100)% over-provisioned"'

              # Spot instance opportunities
              ONDEMAND_COUNT=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=count(kube_node_labels{label_karpenter_sh_capacity_type='on-demand'})" | jq -r '.data.result[0].value[1]')
              echo ""
              echo "On-demand nodes: $ONDEMAND_COUNT (Consider spot instances for 70% savings)"

              # Send to Slack
              curl -X POST $SLACK_WEBHOOK \
                -H 'Content-Type: application/json' \
                -d "{\"text\": \"Daily Cost Report: \\\$${DAILY_COST}\"}"

          restartPolicy: OnFailure

---
# PrometheusRule for cost alerts
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cost-alerts
  namespace: monitoring
spec:
  groups:
  - name: cost-optimization
    interval: 1h
    rules:
    # Alert when daily cost exceeds budget
    - alert: DailyCostExceedsBudget
      expr: |
        (
          sum(kube_pod_container_resource_requests{resource="cpu"}) * 0.04 +
          sum(kube_pod_container_resource_requests{resource="memory"}) / 1073741824 * 0.005
        ) * 24 > 1000
      labels:
        severity: warning
        team: finops
      annotations:
        summary: "Daily infrastructure cost exceeds $1000"
        description: "Current daily cost: ${{ $value }}"

    # Alert on underutilized nodes
    - alert: UnderutilizedNodes
      expr: |
        (
          sum(kube_node_status_allocatable{resource="cpu"}) -
          sum(kube_pod_container_resource_requests{resource="cpu"})
        ) / sum(kube_node_status_allocatable{resource="cpu"}) > 0.5
      for: 2h
      labels:
        severity: info
        team: platform
      annotations:
        summary: "Cluster has >50% unused CPU capacity"
        description: "Consider scaling down or consolidating workloads"

    # Spot savings opportunity
    - alert: SpotSavingsOpportunity
      expr: |
        count(kube_node_labels{label_karpenter_sh_capacity_type="on-demand"})
        /
        count(kube_node_labels)
        > 0.3
      for: 4h
      labels:
        severity: info
        team: finops
      annotations:
        summary: ">30% on-demand nodes detected"
        description: "Evaluate workloads for spot instance eligibility (70% potential savings)"
```

## Pattern 4: Batch Job & Queue-Based Autoscaling

### Pattern 4A: Kubernetes Job Autoscaling with KEDA

```yaml
# KEDA ScaledJob for queue-driven batch processing
---
apiVersion: v1
kind: Secret
metadata:
  name: aws-sqs-credentials
  namespace: batch-processing
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "AKIAIOSFODNN7EXAMPLE"
  AWS_SECRET_ACCESS_KEY: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

---
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: aws-sqs-auth
  namespace: batch-processing
spec:
  secretTargetRef:
  - parameter: awsAccessKeyID
    name: aws-sqs-credentials
    key: AWS_ACCESS_KEY_ID
  - parameter: awsSecretAccessKey
    name: aws-sqs-credentials
    key: AWS_SECRET_ACCESS_KEY

---
# ScaledJob (not Deployment) for batch processing
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: image-processing-job
  namespace: batch-processing
spec:
  # Job template
  jobTargetRef:
    template:
      spec:
        containers:
        - name: processor
          image: image-processor:v1.0
          env:
          - name: SQS_QUEUE_URL
            value: "https://sqs.us-west-2.amazonaws.com/123456789/image-queue"
          - name: AWS_REGION
            value: "us-west-2"
          resources:
            requests:
              cpu: 2
              memory: 4Gi
            limits:
              cpu: 4
              memory: 8Gi
        restartPolicy: OnFailure

  # Polling interval
  pollingInterval: 10  # Check queue every 10 seconds

  # Cooldown period
  cooldownPeriod: 60   # Wait 60s after last trigger before scaling down

  # Max replicas
  maxReplicaCount: 100

  # Successful job retention
  successfulJobsHistoryLimit: 5
  failedJobsHistoryLimit: 5

  # Scaling strategy
  scalingStrategy:
    strategy: "accurate"  # Create jobs based on queue length
    # "default" = one job per event
    # "custom" = custom logic
    # "accurate" = jobs = queue length / messages per job

  triggers:
  - type: aws-sqs-queue
    authenticationRef:
      name: aws-sqs-auth
    metadata:
      queueURL: "https://sqs.us-west-2.amazonaws.com/123456789/image-queue"
      queueLength: "5"     # Process 5 messages per job
      awsRegion: "us-west-2"
      identityOwner: "operator"

---
# Alternative: Kafka-based job scaling
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: kafka-consumer-job
  namespace: batch-processing
spec:
  jobTargetRef:
    template:
      spec:
        containers:
        - name: consumer
          image: kafka-consumer:v1.0
          env:
          - name: KAFKA_BROKERS
            value: "kafka:9092"
          - name: KAFKA_TOPIC
            value: "events"
          - name: KAFKA_CONSUMER_GROUP
            value: "batch-processors"
        restartPolicy: OnFailure

  pollingInterval: 15
  maxReplicaCount: 50

  triggers:
  - type: kafka
    metadata:
      bootstrapServers: "kafka:9092"
      consumerGroup: "batch-processors"
      topic: "events"
      lagThreshold: "100"  # Create job when lag > 100 messages
      offsetResetPolicy: "latest"
```

### Pattern 4B: ML Training Job Autoscaling with Volcano

```yaml
# Install Volcano scheduler
---
apiVersion: v1
kind: Namespace
metadata:
  name: volcano-system

---
# Volcano scheduler deployment
# (Use official Volcano installation)

---
# ML Training job with gang scheduling
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: distributed-training
  namespace: ml-training
spec:
  # Minimum pods required to start job
  minAvailable: 4  # 1 master + 3 workers minimum

  schedulerName: volcano

  # Queue for resource management
  queue: ml-training-queue

  # Plugins
  plugins:
    ssh: []        # Enable SSH between pods
    svc: []        # Create service for pod communication
    env: []        # Environment variable injection

  # Policies
  policies:
  - event: PodEvicted
    action: RestartJob
  - event: PodFailed
    action: RestartJob

  # Task groups
  tasks:
  # Master task
  - name: master
    replicas: 1
    template:
      spec:
        containers:
        - name: tensorflow
          image: tensorflow/tensorflow:latest-gpu
          command:
          - python
          - train.py
          - --role=master
          resources:
            requests:
              cpu: 4
              memory: 16Gi
              nvidia.com/gpu: 1
            limits:
              cpu: 8
              memory: 32Gi
              nvidia.com/gpu: 1

  # Worker tasks (auto-scalable)
  - name: worker
    replicas: 3
    minAvailable: 1  # At least 1 worker
    template:
      spec:
        containers:
        - name: tensorflow
          image: tensorflow/tensorflow:latest-gpu
          command:
          - python
          - train.py
          - --role=worker
          resources:
            requests:
              cpu: 8
              memory: 32Gi
              nvidia.com/gpu: 2
            limits:
              cpu: 16
              memory: 64Gi
              nvidia.com/gpu: 2

  # Parameter server tasks
  - name: ps
    replicas: 2
    template:
      spec:
        containers:
        - name: tensorflow
          image: tensorflow/tensorflow:latest
          command:
          - python
          - train.py
          - --role=ps
          resources:
            requests:
              cpu: 2
              memory: 8Gi
            limits:
              cpu: 4
              memory: 16Gi

---
# Queue with capacity limits
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
metadata:
  name: ml-training-queue
spec:
  weight: 1
  capability:
    cpu: "100"
    memory: "500Gi"
    nvidia.com/gpu: "20"

---
# HPA for worker pods (scale workers based on GPU utilization)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: training-workers-hpa
  namespace: ml-training
spec:
  scaleTargetRef:
    apiVersion: batch.volcano.sh/v1alpha1
    kind: Job
    name: distributed-training

  minReplicas: 3
  maxReplicas: 20

  metrics:
  # GPU utilization
  - type: Pods
    pods:
      metric:
        name: DCGM_FI_DEV_GPU_UTIL
      target:
        type: AverageValue
        averageValue: "80"  # Target 80% GPU utilization

  # Training throughput
  - type: Pods
    pods:
      metric:
        name: training_samples_per_second
      target:
        type: AverageValue
        averageValue: "1000"
```

### Pattern 4C: Scheduled Autoscaling (Predictive)

```yaml
# CronHPA for scheduled scaling
---
apiVersion: autoscaling.alibabacloud.com/v1beta1
kind: CronHorizontalPodAutoscaler
metadata:
  name: business-hours-scaling
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server

  # Business hours scaling schedule
  jobs:
  # Scale up for morning traffic (8 AM)
  - name: morning-scale-up
    schedule: "0 8 * * 1-5"  # Weekdays at 8 AM
    targetSize: 20

  # Scale up for lunch traffic (12 PM)
  - name: lunch-scale-up
    schedule: "0 12 * * 1-5"
    targetSize: 30

  # Scale down for evening (6 PM)
  - name: evening-scale-down
    schedule: "0 18 * * 1-5"
    targetSize: 15

  # Scale down for night (10 PM)
  - name: night-scale-down
    schedule: "0 22 * * *"
    targetSize: 5

  # Weekend minimal scaling
  - name: weekend-minimal
    schedule: "0 0 * * 0,6"  # Midnight on Sat/Sun
    targetSize: 3

---
# Alternative: Using native CronJob + kubectl scale
apiVersion: batch/v1
kind: CronJob
metadata:
  name: morning-scale-up
  namespace: production
spec:
  schedule: "0 8 * * 1-5"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: autoscaler
          containers:
          - name: kubectl
            image: bitnami/kubectl:latest
            command:
            - kubectl
            - scale
            - deployment/api-server
            - --replicas=20
            - -n
            - production
          restartPolicy: OnFailure
```

## Pattern 5: Emerging Technologies & Future Patterns

### Pattern 5A: Predictive Autoscaling with Machine Learning

```python
# ML-based predictive autoscaling model
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from kubernetes import client, config
import datetime

class PredictiveAutoscaler:
    def __init__(self):
        config.load_kube_config()
        self.apps_v1 = client.AppsV1Api()
        self.model = RandomForestRegressor(n_estimators=100)
        self.is_trained = False

    def collect_training_data(self, days=30):
        """Collect historical data for training"""
        # Query Prometheus for historical metrics
        # Features: hour, day_of_week, month, previous_load, etc.
        # Target: actual_replicas_needed

        data = {
            'hour': [],
            'day_of_week': [],
            'month': [],
            'previous_load': [],
            'previous_replicas': [],
            'actual_replicas': []
        }

        # Fetch from Prometheus
        # ... (implementation details)

        return pd.DataFrame(data)

    def train(self):
        """Train the prediction model"""
        df = self.collect_training_data()

        X = df[['hour', 'day_of_week', 'month', 'previous_load', 'previous_replicas']]
        y = df['actual_replicas']

        self.model.fit(X, y)
        self.is_trained = True

        print(f"Model trained with {len(df)} samples")
        print(f"Feature importances: {self.model.feature_importances_}")

    def predict_replicas(self, deployment, namespace):
        """Predict required replicas for next hour"""
        if not self.is_trained:
            raise Exception("Model not trained")

        now = datetime.datetime.now()

        # Current state
        deployment_obj = self.apps_v1.read_namespaced_deployment(
            deployment, namespace
        )
        current_replicas = deployment_obj.spec.replicas

        # Get current load from Prometheus
        current_load = self.get_current_load(deployment, namespace)

        # Prepare features
        features = np.array([[
            now.hour,
            now.weekday(),
            now.month,
            current_load,
            current_replicas
        ]])

        # Predict
        predicted_replicas = int(self.model.predict(features)[0])

        # Apply safety bounds
        min_replicas = 2
        max_replicas = 100
        predicted_replicas = max(min_replicas, min(predicted_replicas, max_replicas))

        return predicted_replicas

    def apply_scaling(self, deployment, namespace, replicas):
        """Apply predicted scaling"""
        body = {
            'spec': {
                'replicas': replicas
            }
        }

        self.apps_v1.patch_namespaced_deployment_scale(
            deployment,
            namespace,
            body
        )

        print(f"Scaled {deployment} to {replicas} replicas")

    def run(self, deployment, namespace, interval=300):
        """Main loop"""
        import time

        while True:
            try:
                predicted = self.predict_replicas(deployment, namespace)
                self.apply_scaling(deployment, namespace, predicted)

                print(f"[{datetime.datetime.now()}] Scaled to {predicted} replicas")

            except Exception as e:
                print(f"Error: {e}")

            time.sleep(interval)  # Every 5 minutes

# Usage
if __name__ == "__main__":
    autoscaler = PredictiveAutoscaler()
    autoscaler.train()
    autoscaler.run("api-server", "production")
```

### Pattern 5B: Serverless Kubernetes with Knative

```yaml
# Knative Service with autoscaling
---
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: knative-app
  namespace: serverless
spec:
  template:
    metadata:
      annotations:
        # Autoscaling configuration
        autoscaling.knative.dev/class: "kpa.autoscaling.knative.dev"
        autoscaling.knative.dev/metric: "concurrency"
        autoscaling.knative.dev/target: "10"  # Target 10 concurrent requests
        autoscaling.knative.dev/minScale: "0"  # Scale to zero
        autoscaling.knative.dev/maxScale: "100"
        autoscaling.knative.dev/scaleDownDelay: "30s"
        autoscaling.knative.dev/window: "60s"  # Evaluation window

    spec:
      containers:
      - image: myapp:v1.0
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 512Mi

---
# Advanced: RPS-based autoscaling
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: rps-based-app
  namespace: serverless
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/metric: "rps"  # Requests per second
        autoscaling.knative.dev/target: "100"   # Target 100 RPS per pod
        autoscaling.knative.dev/targetUtilizationPercentage: "70"
    spec:
      containers:
      - image: myapp:v1.0
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
```

### Pattern 5C: Service Mesh Integration (Istio)

```yaml
# Istio VirtualService with traffic-based autoscaling
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: my-app
  namespace: production
spec:
  hosts:
  - my-app.example.com
  http:
  - match:
    - headers:
        x-version:
          exact: canary
    route:
    - destination:
        host: my-app
        subset: canary
      weight: 10  # 10% traffic to canary
  - route:
    - destination:
        host: my-app
        subset: stable
      weight: 90

---
# DestinationRule
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: my-app
  namespace: production
spec:
  host: my-app
  subsets:
  - name: stable
    labels:
      version: stable
  - name: canary
    labels:
      version: canary

---
# HPA using Istio metrics
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app-istio-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  minReplicas: 2
  maxReplicas: 50

  metrics:
  # Istio request rate
  - type: Pods
    pods:
      metric:
        name: istio_requests_per_second
      target:
        type: AverageValue
        averageValue: "100"

  # Istio P99 latency
  - type: Pods
    pods:
      metric:
        name: istio_request_duration_p99
      target:
        type: AverageValue
        averageValue: "200m"  # 200ms

---
# Prometheus rules for Istio metrics
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: istio-custom-metrics
  namespace: monitoring
spec:
  groups:
  - name: istio-autoscaling
    interval: 15s
    rules:
    - record: istio_requests_per_second
      expr: |
        sum(rate(istio_requests_total{destination_workload="my-app"}[2m])) by (pod)

    - record: istio_request_duration_p99
      expr: |
        histogram_quantile(0.99,
          sum(rate(istio_request_duration_milliseconds_bucket{destination_workload="my-app"}[2m])) by (pod, le)
        )
```

## Best Practices Summary

### Stateful Applications
✅ Use conservative scaling policies (slower scale-up/down)
✅ Implement proper health checks and readiness probes
✅ Plan for data synchronization time
✅ Use PVCs with appropriate storage classes
✅ Consider split architectures (read/write separation)

### Multi-Cluster
✅ Centralize metrics with Thanos or Prometheus federation
✅ Implement intelligent routing with global load balancers
✅ Use cost-aware scheduling
✅ Plan for cross-cluster failover
✅ Monitor inter-cluster latency

### Cost Optimization
✅ Maximize spot instance usage (70-90% savings)
✅ Implement aggressive consolidation
✅ Use FinOps dashboards for visibility
✅ Set up cost alerts and budgets
✅ Regular right-sizing reviews

### Batch Jobs
✅ Use KEDA ScaledJobs for queue-driven processing
✅ Implement proper job cleanup policies
✅ Set resource limits to prevent runaway costs
✅ Use gang scheduling for distributed jobs
✅ Monitor job success rates

## Key Takeaways

1. **Stateful Scaling**: Requires careful planning, slower policies, and split read/write architectures
2. **Multi-Cluster**: Centralized metrics and intelligent distribution critical for success
3. **Cost Optimization**: Spot instances + right-sizing + consolidation = 60-80% savings
4. **Batch Processing**: Queue-based autoscaling with KEDA scales jobs efficiently
5. **Future**: ML-based prediction, serverless K8s, and service mesh integration emerging

## Related Topics

### Autoscaling Series
- **[Part 1: HPA Fundamentals](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)**
- **[Part 2: Cluster Autoscaling](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)**
- **[Part 3: Hands-On Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)**
- **[Part 4: Monitoring & Alerting](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)**
- **[Part 5: VPA & Resource Optimization](./kubernetes-autoscaling-complete-guide-part5-vpa-resource-optimization.md)**

## Conclusion

Advanced autoscaling patterns unlock significant value:

- **Stateful applications** can scale safely with proper planning
- **Multi-cluster deployments** enable global scale and resilience
- **Cost optimization** delivers 60-80% infrastructure savings
- **Batch processing** scales efficiently with queue-based triggers
- **Emerging technologies** push boundaries of what's possible

These patterns, combined with foundational HPA and VPA, create comprehensive autoscaling architectures that balance performance, cost, and reliability at scale.

Next up: **Part 7 - Production Troubleshooting & War Stories** 🔧

Happy scaling! 🚀
