---
title: "Kubernetes Autoscaling Complete Guide (Part 5): Vertical Pod Autoscaler & Resource Optimization"
date: 2025-11-09T20:00:00+08:00
draft: false
authors: ["yennj12 team"]
categories: ["all", "engineering", "devops", "kubernetes", "optimization"]
tags: ["Kubernetes", "K8S", "VPA", "Vertical Pod Autoscaler", "Resource Optimization", "Cost Optimization", "Right-sizing", "Performance", "FinOps"]
summary: "Part 5 of the Kubernetes Autoscaling series: Deep dive into Vertical Pod Autoscaler (VPA), resource right-sizing strategies, combining VPA with HPA, and production-grade resource optimization techniques for cost-effective Kubernetes operations."
readTime: "35 min"
---

## Series Overview

This is **Part 5** of the Kubernetes Autoscaling Complete Guide series:

- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Application-level autoscaling theory
- **[Part 2: Cluster Autoscaling & Cloud Providers](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Infrastructure-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Practical implementation with Apache-PHP
- **[Part 4: Monitoring, Alerting & Threshold Tuning](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)** - Production observability
- **Part 5 (This Post)**: VPA & Resource Optimization - Right-sizing and cost optimization

---

While Horizontal Pod Autoscaler (HPA) scales the number of pod replicas, Vertical Pod Autoscaler (VPA) optimizes resource requests and limits for individual pods. This guide explores VPA architecture, implementation strategies, safe combination with HPA, and comprehensive resource optimization techniques.

## The Resource Management Challenge

### The Cost of Misconfigured Resources

```
OVER-PROVISIONED SCENARIO:
┌─────────────────────────────────────────────────────────────┐
│  Pod Resource Configuration                                 │
│                                                              │
│  Requested: 2 CPU, 4GB RAM                                  │
│  Actual Usage: 0.3 CPU (15%), 800MB RAM (20%)              │
│                                                              │
│  Waste: 1.7 CPU (85%), 3.2GB RAM (80%)                     │
│  Monthly Cost: $120                                          │
│  Wasted Cost: $102/month per pod                            │
│                                                              │
│  With 100 pods: $10,200/month wasted                        │
└─────────────────────────────────────────────────────────────┘

UNDER-PROVISIONED SCENARIO:
┌─────────────────────────────────────────────────────────────┐
│  Pod Resource Configuration                                 │
│                                                              │
│  Requested: 0.5 CPU, 512MB RAM                              │
│  Actual Usage: 0.8 CPU (160%), 1.2GB RAM (240%)            │
│                                                              │
│  Problems:                                                   │
│  • CPU throttling → slow response times                     │
│  • OOMKilled → pod restarts                                 │
│  • Service degradation                                       │
│  • Customer impact → lost revenue                           │
└─────────────────────────────────────────────────────────────┘

VPA OPTIMIZED:
┌─────────────────────────────────────────────────────────────┐
│  Pod Resource Configuration                                 │
│                                                              │
│  Requested: 0.4 CPU, 1GB RAM                                │
│  Actual Usage: 0.35 CPU (87%), 900MB RAM (90%)             │
│                                                              │
│  Result:                                                     │
│  • 80% cost savings vs over-provisioned                     │
│  • No throttling or OOM issues                              │
│  • Optimal resource utilization                             │
└─────────────────────────────────────────────────────────────┘
```

### Business Impact

| Metric | Without VPA | With VPA | Impact |
|--------|-------------|----------|--------|
| **Resource Waste** | 40-70% typical | 5-15% | 60%+ cost reduction |
| **OOMKilled Events** | Common | Rare | Better reliability |
| **CPU Throttling** | Frequent | Minimal | Improved performance |
| **Manual Tuning Time** | Hours/week | Automated | Operational efficiency |
| **Right-sizing Accuracy** | Guesswork | Data-driven | Precision optimization |

## Understanding Vertical Pod Autoscaler

### VPA Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        VPA ARCHITECTURE                              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   VPA ADMISSION CONTROLLER                     │ │
│  │                                                                 │ │
│  │  • Intercepts pod creation requests                            │ │
│  │  • Injects resource requests/limits                            │ │
│  │  • Works at pod admission time                                 │ │
│  └────────────────┬───────────────────────────────────────────────┘ │
│                   │                                                  │
│                   ↓                                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   VPA RECOMMENDER                              │ │
│  │                                                                 │ │
│  │  • Monitors pod resource usage (from Metrics Server)           │ │
│  │  • Analyzes historical metrics                                 │ │
│  │  • Calculates optimal resource requests                        │ │
│  │  • Stores recommendations in VPA objects                       │ │
│  └────────────────┬───────────────────────────────────────────────┘ │
│                   │                                                  │
│                   ↓                                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   VPA UPDATER                                  │ │
│  │                                                                 │ │
│  │  • Checks if pods need resource updates                        │ │
│  │  • Evicts pods with outdated resource configs                  │ │
│  │  • Triggers pod recreation with new resources                  │ │
│  │  • Respects PodDisruptionBudgets                              │ │
│  └────────────────┬───────────────────────────────────────────────┘ │
│                   │                                                  │
│                   ↓                                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              KUBERNETES API & METRICS                          │ │
│  │                                                                 │ │
│  │  Metrics Server → VPA Recommender → VPA Object → Updater       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### VPA vs HPA Comparison

| Aspect | VPA | HPA |
|--------|-----|-----|
| **Scaling Direction** | Vertical (resources per pod) | Horizontal (number of pods) |
| **What it Changes** | CPU/memory requests & limits | Replica count |
| **Pod Disruption** | Yes (recreation required) | No (gradual) |
| **Best For** | Right-sizing, cost optimization | Traffic scaling, load handling |
| **Stateful Apps** | Suitable | Complex |
| **Response Time** | Minutes (pod restart) | Seconds to minutes |
| **Use Case** | Unknown resource needs | Known scaling patterns |
| **Combine with Other** | Can combine with HPA (carefully) | Can combine with VPA |

## Part 1: Installing VPA

### Prerequisites

```bash
# Ensure Metrics Server is installed
kubectl get deployment metrics-server -n kube-system

# Verify metrics are available
kubectl top nodes
kubectl top pods -A
```

### Installation via Manifests

```bash
# Clone VPA repository
git clone https://github.com/kubernetes/autoscaler.git
cd autoscaler/vertical-pod-autoscaler

# Install VPA components
./hack/vpa-up.sh

# Verify installation
kubectl get pods -n kube-system | grep vpa

# Expected output:
# vpa-admission-controller-xxx   1/1     Running   0          2m
# vpa-recommender-xxx            1/1     Running   0          2m
# vpa-updater-xxx                1/1     Running   0          2m

# Verify CRDs
kubectl get crd | grep verticalpodautoscaler

# Expected:
# verticalpodautoscalercheckpoints.autoscaling.k8s.io
# verticalpodautoscalers.autoscaling.k8s.io
```

### Installation via Helm

```bash
# Add VPA Helm repository
helm repo add fairwinds-stable https://charts.fairwinds.com/stable
helm repo update

# Install VPA
helm install vpa fairwinds-stable/vpa \
  --namespace kube-system \
  --set recommender.enabled=true \
  --set updater.enabled=true \
  --set admissionController.enabled=true

# Verify installation
helm status vpa -n kube-system
kubectl get pods -n kube-system -l app.kubernetes.io/name=vpa
```

### Installation via AWS CDK (EKS Integration)

Add to your CDK stack from Part 3:

```typescript
import * as cdk from 'aws-cdk-lib';
import * as eks from 'aws-cdk-lib/aws-eks';
import { Construct } from 'constructs';

export class EksVpaStack extends cdk.Stack {
  constructor(scope: Construct, id: string, cluster: eks.Cluster, props?: cdk.StackProps) {
    super(scope, id, props);

    // Install VPA using Helm
    const vpa = cluster.addHelmChart('VPA', {
      chart: 'vpa',
      repository: 'https://charts.fairwinds.com/stable',
      namespace: 'kube-system',
      release: 'vpa',
      version: '4.4.6', // Check for latest version

      values: {
        // Recommender configuration
        recommender: {
          enabled: true,
          extraArgs: {
            'v': '4', // Verbose logging
            'pod-recommendation-min-cpu-millicores': '25', // Minimum CPU recommendation
            'pod-recommendation-min-memory-mb': '100', // Minimum memory recommendation
            'recommendation-margin-fraction': '0.15', // 15% safety margin
            'storage': 'prometheus', // Optional: Use Prometheus for history
          },
          resources: {
            requests: {
              cpu: '200m',
              memory: '512Mi',
            },
            limits: {
              cpu: '500m',
              memory: '1Gi',
            },
          },
        },

        // Updater configuration
        updater: {
          enabled: true,
          extraArgs: {
            'min-replicas': '2', // Only update deployments with 2+ replicas
            'eviction-tolerance': '0.5', // Max 50% pods can be evicting
          },
          resources: {
            requests: {
              cpu: '100m',
              memory: '256Mi',
            },
            limits: {
              cpu: '200m',
              memory: '512Mi',
            },
          },
        },

        // Admission Controller configuration
        admissionController: {
          enabled: true,
          generateCertificate: true,
          resources: {
            requests: {
              cpu: '100m',
              memory: '256Mi',
            },
            limits: {
              cpu: '200m',
              memory: '512Mi',
            },
          },
        },

        // Metrics Server dependency
        metrics: {
          enabled: false, // Assuming already installed
        },
      },
    });

    // Output VPA status check command
    new cdk.CfnOutput(this, 'VPAStatusCommand', {
      value: 'kubectl get pods -n kube-system -l app.kubernetes.io/name=vpa',
      description: 'Command to check VPA pods status',
    });
  }
}
```

## Part 2: VPA Update Modes

VPA supports four update modes that control how it applies recommendations:

### Mode 1: Off (Recommendation Only)

**Use Case**: Testing VPA without impacting workloads

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa-off
  namespace: default
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Off"  # Only generate recommendations

# VPA will NOT modify pods, only provide recommendations
# Check recommendations:
# kubectl describe vpa my-app-vpa-off
```

**Benefits:**
- Safe exploration of VPA recommendations
- No disruption to running workloads
- Understand resource usage patterns
- Plan resource adjustments

**Example Output:**

```bash
kubectl describe vpa my-app-vpa-off

# Output shows recommendations:
Recommendation:
  Container Recommendations:
    Container Name: my-app
    Lower Bound:
      Cpu:     150m
      Memory:  256Mi
    Target:
      Cpu:     300m      # Recommended request
      Memory:  512Mi     # Recommended request
    Uncapped Target:
      Cpu:     300m
      Memory:  512Mi
    Upper Bound:
      Cpu:     1
      Memory:  2Gi
```

### Mode 2: Initial (Apply on Pod Creation Only)

**Use Case**: New deployments, gradual rollout

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa-initial
  namespace: default
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Initial"  # Apply only when pods are created

  resourcePolicy:
    containerPolicies:
    - containerName: my-app
      minAllowed:
        cpu: 100m
        memory: 128Mi
      maxAllowed:
        cpu: 2
        memory: 4Gi
```

**Behavior:**
- VPA sets resource requests when pods are **first created**
- No changes to existing running pods
- Useful for new deployments or scaling events
- Safe for production workloads

**When to Use:**
- Initial deployment with unknown resource needs
- Canary deployments
- Blue/green deployments
- When combined with HPA (pods recreated during scale events)

### Mode 3: Recreate (Apply by Restarting Pods)

**Use Case**: Production optimization with controlled disruption

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa-recreate
  namespace: default
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Recreate"  # VPA will evict and recreate pods

  resourcePolicy:
    containerPolicies:
    - containerName: my-app
      minAllowed:
        cpu: 100m
        memory: 128Mi
      maxAllowed:
        cpu: 2
        memory: 4Gi
      controlledResources: ["cpu", "memory"]
      mode: Auto  # VPA manages both requests and limits

# PodDisruptionBudget to control eviction rate
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
  namespace: default
spec:
  minAvailable: 2  # At least 2 pods must remain available
  selector:
    matchLabels:
      app: my-app
```

**Behavior:**
- VPA evicts pods with outdated resource configuration
- Pods are recreated with new resource requests
- Respects PodDisruptionBudgets
- Gradual rollout to maintain availability

**Important Considerations:**
- **Disruption**: Pods will be restarted
- **Stateful Apps**: Handle with care (use PVCs, proper shutdown)
- **PDBs Required**: Prevent cascading failures
- **Monitoring**: Watch for elevated pod restart rates

### Mode 4: Auto (Future - Not Yet Implemented)

**Status**: Planned feature for in-place resource updates

```yaml
# Future capability (not yet available)
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa-auto
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Auto"  # In-place updates without pod restart

# When available, will update resources WITHOUT pod eviction
# Requires Kubernetes in-place resource update feature
```

**Expected Behavior** (when implemented):
- Update pod resources without restart
- Zero disruption
- Immediate application of new limits

## Part 3: VPA Configuration Deep Dive

### Basic VPA Configuration

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa
  namespace: default
spec:
  # Target workload
  targetRef:
    apiVersion: apps/v1
    kind: Deployment  # Can be: Deployment, StatefulSet, DaemonSet, ReplicaSet
    name: my-app

  # Update policy
  updatePolicy:
    updateMode: "Auto"  # Off, Initial, Recreate, Auto

  # Resource policy (constraints and rules)
  resourcePolicy:
    containerPolicies:
    - containerName: '*'  # Apply to all containers, or specify name
      minAllowed:
        cpu: 100m
        memory: 128Mi
      maxAllowed:
        cpu: 2
        memory: 4Gi
      controlledResources: ["cpu", "memory"]  # What VPA should manage

      # Resource scaling mode
      mode: Auto  # Auto (manage requests & limits) or Off
```

### Advanced VPA Configuration

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: advanced-vpa
  namespace: production
  labels:
    app: my-app
    environment: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Recreate"

    # Minimum number of replicas required
    minReplicas: 2  # Don't update if less than 2 replicas

  resourcePolicy:
    containerPolicies:

    # Application container
    - containerName: app
      minAllowed:
        cpu: 200m
        memory: 256Mi
      maxAllowed:
        cpu: 4
        memory: 8Gi
      controlledResources: ["cpu", "memory"]
      mode: Auto

      # Resource scaling factors
      controlledValues: RequestsAndLimits  # or RequestsOnly

    # Sidecar container (different policy)
    - containerName: sidecar
      minAllowed:
        cpu: 50m
        memory: 64Mi
      maxAllowed:
        cpu: 500m
        memory: 512Mi
      controlledResources: ["cpu", "memory"]
      mode: Auto

  # Recommender configuration
  recommenders:
  - name: custom-recommender  # Use custom recommender if deployed
```

### Resource Policy Options Explained

#### controlledResources

```yaml
# Option 1: Manage both CPU and memory
controlledResources: ["cpu", "memory"]

# Option 2: CPU only
controlledResources: ["cpu"]

# Option 3: Memory only
controlledResources: ["memory"]
```

#### controlledValues

```yaml
# Option 1: Manage both requests and limits (default)
controlledValues: RequestsAndLimits
# VPA sets both resource requests and limits
# Limit = Request * current limit/request ratio

# Option 2: Manage requests only
controlledValues: RequestsOnly
# VPA only sets resource requests
# Limits remain as defined in pod spec
```

**Example:**

```yaml
# Original pod spec:
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m     # 5x request
    memory: 512Mi # 4x request

# With controlledValues: RequestsAndLimits
# VPA recommendation: 200m CPU, 256Mi memory
# VPA sets:
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m    # 5x request (ratio preserved)
    memory: 1Gi   # 4x request (ratio preserved)

# With controlledValues: RequestsOnly
# VPA sets:
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 500m     # Original limit (unchanged)
    memory: 512Mi # Original limit (unchanged)
```

## Part 4: Combining VPA with HPA

### The Challenge

**VPA and HPA can conflict** when both try to manage the same workload:

```
Conflict Scenario:
┌────────────────────────────────────────────────────────────┐
│  Time: 10:00 - High CPU usage detected                    │
│                                                             │
│  HPA: "CPU is high, scale from 3 to 6 pods"               │
│  VPA: "CPU is high, increase CPU requests from 100m to 200m"│
│                                                             │
│  Result: Both scale simultaneously                         │
│  • HPA adds 3 pods with old 100m requests                 │
│  • VPA tries to recreate all 6 pods with 200m requests    │
│  • Cascading pod restarts                                  │
│  • Service disruption                                      │
└────────────────────────────────────────────────────────────┘
```

### Safe Combination Strategies

#### Strategy 1: VPA for CPU, HPA for Custom Metrics

**Recommendation:** Most common and safest approach

```yaml
# VPA configuration
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Initial"  # Only apply on new pods (from HPA scaling)

  resourcePolicy:
    containerPolicies:
    - containerName: '*'
      minAllowed:
        cpu: 100m
        memory: 256Mi
      maxAllowed:
        cpu: 2
        memory: 4Gi
      # KEY: Only manage CPU
      controlledResources: ["cpu"]
      controlledValues: RequestsOnly

---
# HPA configuration
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  minReplicas: 2
  maxReplicas: 20

  # KEY: Use custom metrics, NOT CPU
  metrics:
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"

  # Or use memory (since VPA manages CPU)
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70
```

**Why This Works:**
- VPA optimizes CPU requests based on actual usage
- HPA scales replicas based on request rate or memory
- No conflict: they manage different dimensions

#### Strategy 2: VPA Off Mode + Manual Right-sizing

```yaml
# VPA in recommendation-only mode
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa-readonly
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  updatePolicy:
    updateMode: "Off"  # Recommendations only

---
# HPA manages scaling
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app

  minReplicas: 3
  maxReplicas: 50

  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Process:**
1. VPA generates recommendations
2. Review recommendations weekly/monthly
3. Manually update deployment resource requests
4. HPA continues to scale horizontally

**Benefits:**
- Zero conflict
- Full control over resource changes
- Suitable for conservative environments

#### Strategy 3: Separate Workloads

**Best Practice:** Use VPA and HPA on different workloads

```yaml
# VPA for stateful workloads (vertical scaling)
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: database-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: postgres
  updatePolicy:
    updateMode: "Recreate"
  resourcePolicy:
    containerPolicies:
    - containerName: postgres
      minAllowed:
        cpu: 1
        memory: 2Gi
      maxAllowed:
        cpu: 8
        memory: 32Gi

---
# HPA for stateless workloads (horizontal scaling)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 5
  maxReplicas: 100
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Configuration Matrix

| VPA Mode | HPA Metric | Result | Recommendation |
|----------|------------|--------|----------------|
| **Off** | CPU | ✅ Safe | VPA provides insights, HPA scales |
| **Initial** | Custom (requests/sec) | ✅ Safe | VPA right-sizes on scale events |
| **Initial** | Memory | ✅ Safe | Different resources managed |
| **Recreate** | CPU | ⚠️ Risky | Can cause thrashing |
| **Recreate** | Custom | ✅ Safe | VPA updates resources, HPA scales on different metric |
| **Recreate** | Memory | ⚠️ Moderate | Monitor closely |

## Part 5: Production VPA Examples

### Example 1: Stateless Web Application

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: production
spec:
  replicas: 5
  selector:
    matchLabels:
      app: web-app
  template:
    metadata:
      labels:
        app: web-app
    spec:
      containers:
      - name: nginx
        image: nginx:1.25
        resources:
          requests:
            cpu: 100m      # Initial guess
            memory: 128Mi  # Initial guess
          limits:
            cpu: 500m
            memory: 512Mi

---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: web-app-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-app

  updatePolicy:
    updateMode: "Recreate"

  resourcePolicy:
    containerPolicies:
    - containerName: nginx
      minAllowed:
        cpu: 50m
        memory: 64Mi
      maxAllowed:
        cpu: 1
        memory: 1Gi
      controlledResources: ["cpu", "memory"]
      controlledValues: RequestsAndLimits

---
# PDB to ensure availability during updates
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-app-pdb
  namespace: production
spec:
  minAvailable: 3  # Keep at least 3 pods running
  selector:
    matchLabels:
      app: web-app
```

### Example 2: Stateful Database

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: databases
spec:
  serviceName: postgres
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        resources:
          requests:
            cpu: 2
            memory: 4Gi
          limits:
            cpu: 4
            memory: 16Gi
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data

  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi

---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: postgres-vpa
  namespace: databases
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: postgres

  updatePolicy:
    updateMode: "Initial"  # Safer for stateful apps

  resourcePolicy:
    containerPolicies:
    - containerName: postgres
      minAllowed:
        cpu: 1
        memory: 2Gi
      maxAllowed:
        cpu: 8
        memory: 32Gi
      controlledResources: ["cpu", "memory"]
      controlledValues: RequestsOnly  # Keep original limits

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: databases
spec:
  maxUnavailable: 1  # Only 1 pod can be down at a time
  selector:
    matchLabels:
      app: postgres
```

### Example 3: Microservices with Different Profiles

```yaml
# CPU-intensive service
---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: image-processor-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: image-processor

  updatePolicy:
    updateMode: "Recreate"

  resourcePolicy:
    containerPolicies:
    - containerName: processor
      minAllowed:
        cpu: 500m      # Higher CPU baseline
        memory: 256Mi
      maxAllowed:
        cpu: 8         # Allow significant CPU growth
        memory: 2Gi
      controlledResources: ["cpu", "memory"]

---
# Memory-intensive service
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: cache-service-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: cache-service

  updatePolicy:
    updateMode: "Recreate"

  resourcePolicy:
    containerPolicies:
    - containerName: redis
      minAllowed:
        cpu: 100m
        memory: 1Gi       # Higher memory baseline
      maxAllowed:
        cpu: 2
        memory: 16Gi      # Allow significant memory growth
      controlledResources: ["cpu", "memory"]

---
# Balanced service
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-service-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service

  updatePolicy:
    updateMode: "Initial"  # Apply on HPA scale events

  resourcePolicy:
    containerPolicies:
    - containerName: api
      minAllowed:
        cpu: 100m
        memory: 128Mi
      maxAllowed:
        cpu: 2
        memory: 2Gi
      controlledResources: ["cpu", "memory"]
```

## Part 6: Resource Optimization Strategies

### Strategy 1: Rightsizing Workflow

**Phase 1: Discovery (Week 1)**

```bash
# Step 1: Deploy VPA in "Off" mode for all deployments
for deployment in $(kubectl get deployments -n production -o name); do
  cat <<EOF | kubectl apply -f -
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: $(basename $deployment)-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: $(basename $deployment)
  updatePolicy:
    updateMode: "Off"
EOF
done

# Step 2: Wait for 7 days to collect data

# Step 3: Collect recommendations
kubectl get vpa -n production -o yaml > vpa-recommendations.yaml

# Step 4: Analyze recommendations
for vpa in $(kubectl get vpa -n production -o name); do
  echo "=== $vpa ==="
  kubectl describe $vpa -n production | grep -A 20 "Target:"
done
```

**Phase 2: Analysis (Week 2)**

```bash
# Generate resource optimization report
cat > analyze-vpa.sh <<'EOF'
#!/bin/bash

echo "VPA Recommendations Analysis"
echo "============================="
echo ""

for vpa in $(kubectl get vpa -n production -o name); do
  deployment=$(kubectl get $vpa -n production -o jsonpath='{.spec.targetRef.name}')

  echo "Deployment: $deployment"

  # Current requests
  current_cpu=$(kubectl get deployment $deployment -n production -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}')
  current_mem=$(kubectl get deployment $deployment -n production -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}')

  # VPA recommendations
  target_cpu=$(kubectl get $vpa -n production -o jsonpath='{.status.recommendation.containerRecommendations[0].target.cpu}')
  target_mem=$(kubectl get $vpa -n production -o jsonpath='{.status.recommendation.containerRecommendations[0].target.memory}')

  echo "  Current: CPU=$current_cpu, Memory=$current_mem"
  echo "  Target:  CPU=$target_cpu, Memory=$target_mem"
  echo ""
done
EOF

chmod +x analyze-vpa.sh
./analyze-vpa.sh
```

**Phase 3: Implementation (Week 3)**

```bash
# Apply recommendations gradually
# Start with non-critical services

# 1. Test environment first
kubectl patch deployment my-app -n production -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [
          {
            "name": "my-app",
            "resources": {
              "requests": {
                "cpu": "300m",
                "memory": "512Mi"
              }
            }
          }
        ]
      }
    }
  }
}'

# 2. Monitor for issues
kubectl top pods -n production -l app=my-app --watch

# 3. If stable, proceed with production
```

### Strategy 2: Cluster-Wide Optimization

```yaml
# Create VPA for all deployments using a script
apiVersion: v1
kind: ConfigMap
metadata:
  name: vpa-automation
  namespace: kube-system
data:
  create-vpas.sh: |
    #!/bin/bash

    # Create VPA for all deployments in specific namespaces
    NAMESPACES="production staging development"

    for ns in $NAMESPACES; do
      for deployment in $(kubectl get deployments -n $ns -o name); do
        deployment_name=$(basename $deployment)

        cat <<EOF | kubectl apply -f -
    apiVersion: autoscaling.k8s.io/v1
    kind: VerticalPodAutoscaler
    metadata:
      name: ${deployment_name}-vpa
      namespace: $ns
      labels:
        managed-by: vpa-automation
    spec:
      targetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: ${deployment_name}
      updatePolicy:
        updateMode: "Initial"  # Safe default
      resourcePolicy:
        containerPolicies:
        - containerName: '*'
          minAllowed:
            cpu: 50m
            memory: 64Mi
          maxAllowed:
            cpu: 4
            memory: 8Gi
    EOF
      done
    done

    echo "VPA objects created for all deployments"

---
# CronJob to run automation weekly
apiVersion: batch/v1
kind: CronJob
metadata:
  name: vpa-optimizer
  namespace: kube-system
spec:
  schedule: "0 2 * * 0"  # Every Sunday at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: vpa-automation
          containers:
          - name: optimizer
            image: bitnami/kubectl:latest
            command:
            - /bin/bash
            - -c
            - |
              # Generate cost savings report
              echo "Weekly VPA Optimization Report"
              echo "=============================="

              total_savings=0

              for ns in production staging; do
                echo ""
                echo "Namespace: $ns"
                echo "---"

                for vpa in $(kubectl get vpa -n $ns -o name); do
                  deployment=$(kubectl get $vpa -n $ns -o jsonpath='{.spec.targetRef.name}')

                  # Calculate potential savings
                  # (This is simplified; real calculation would be more complex)

                  echo "  $deployment: Review recommendations"
                done
              done
          restartPolicy: OnFailure
```

### Strategy 3: Cost Attribution & Showback

```yaml
# Prometheus rules for cost tracking
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: resource-cost-tracking
  namespace: monitoring
spec:
  groups:
  - name: resource-costs
    interval: 5m
    rules:

    # CPU cost per namespace
    - record: namespace:cpu_cost:sum
      expr: |
        sum(
          kube_pod_container_resource_requests{resource="cpu", unit="core"}
          * 0.04  # $0.04 per CPU hour
        ) by (namespace)

    # Memory cost per namespace
    - record: namespace:memory_cost:sum
      expr: |
        sum(
          kube_pod_container_resource_requests{resource="memory", unit="byte"}
          / (1024*1024*1024)  # Convert to GB
          * 0.005  # $0.005 per GB hour
        ) by (namespace)

    # Total cost per namespace
    - record: namespace:total_cost:sum
      expr: |
        namespace:cpu_cost:sum + namespace:memory_cost:sum

    # VPA optimization potential
    - record: namespace:vpa_savings_potential:sum
      expr: |
        sum(
          kube_pod_container_resource_requests{resource="cpu"}
          - on(pod, namespace) group_left()
          kube_verticalpodautoscaler_spec_resourcepolicy_container_policies_target{resource="cpu"}
        ) by (namespace)
        * 0.04  # CPU price

---
# Grafana dashboard for cost tracking (ConfigMap)
apiVersion: v1
kind: ConfigMap
metadata:
  name: cost-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  cost-dashboard.json: |
    {
      "dashboard": {
        "title": "Kubernetes Cost & VPA Savings",
        "panels": [
          {
            "title": "Monthly Cost by Namespace",
            "targets": [
              {
                "expr": "namespace:total_cost:sum * 730",
                "legendFormat": "{{ namespace }}"
              }
            ]
          },
          {
            "title": "VPA Potential Savings",
            "targets": [
              {
                "expr": "namespace:vpa_savings_potential:sum * 730",
                "legendFormat": "{{ namespace }}"
              }
            ]
          }
        ]
      }
    }
```

## Part 7: Monitoring VPA

### VPA Metrics

```yaml
# ServiceMonitor for VPA components
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vpa-metrics
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: vpa
  endpoints:
  - port: metrics
    interval: 30s

---
# PrometheusRule for VPA alerts
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: vpa-alerts
  namespace: monitoring
spec:
  groups:
  - name: vpa-health
    interval: 30s
    rules:

    # VPA recommender not running
    - alert: VPARecommenderDown
      expr: up{job="vpa-recommender"} == 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "VPA Recommender is down"
        description: "VPA Recommender has been down for 5 minutes"

    # VPA updater not running
    - alert: VPAUpdaterDown
      expr: up{job="vpa-updater"} == 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "VPA Updater is down"
        description: "VPA Updater has been down for 5 minutes"

    # Large discrepancy between current and recommended
    - alert: VPARecommendationMismatch
      expr: |
        (
          kube_pod_container_resource_requests{resource="cpu"}
          /
          kube_verticalpodautoscaler_status_recommendation_containerrecommendations_target{resource="cpu"}
        ) > 2 or
        (
          kube_pod_container_resource_requests{resource="cpu"}
          /
          kube_verticalpodautoscaler_status_recommendation_containerrecommendations_target{resource="cpu"}
        ) < 0.5
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "Pod resources deviate significantly from VPA recommendation"
        description: "Pod {{ $labels.pod }} in {{ $labels.namespace }} has resource requests 2x different from VPA target"

    # OOMKilled pods that VPA should have prevented
    - alert: OOMKilledDespiteVPA
      expr: |
        increase(kube_pod_container_status_terminated_reason{reason="OOMKilled"}[1h]) > 0
        and on(pod, namespace)
        kube_verticalpodautoscaler_spec_updatepolicy_updatemode{update_mode!="Off"} == 1
      labels:
        severity: warning
      annotations:
        summary: "Pod OOMKilled despite VPA enabled"
        description: "Pod {{ $labels.pod }} was OOMKilled even though VPA is active. Review VPA maxAllowed settings."
```

### Grafana Dashboard for VPA

```bash
# Dashboard showing VPA effectiveness
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: vpa-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  vpa-overview.json: |
    {
      "dashboard": {
        "title": "VPA Overview",
        "panels": [
          {
            "title": "VPA Recommendations vs Actual",
            "type": "graph",
            "targets": [
              {
                "expr": "kube_pod_container_resource_requests{resource='cpu'}",
                "legendFormat": "Actual - {{ pod }}"
              },
              {
                "expr": "kube_verticalpodautoscaler_status_recommendation_containerrecommendations_target{resource='cpu'}",
                "legendFormat": "VPA Target - {{ target_name }}"
              }
            ]
          },
          {
            "title": "VPA Update Events",
            "type": "table",
            "targets": [
              {
                "expr": "changes(kube_pod_container_resource_requests[1h])",
                "format": "table"
              }
            ]
          },
          {
            "title": "Cost Savings from VPA",
            "type": "stat",
            "targets": [
              {
                "expr": "sum(namespace:vpa_savings_potential:sum) * 730"
              }
            ]
          }
        ]
      }
    }
EOF
```

## Part 8: Troubleshooting VPA

### Common Issues

#### Issue 1: VPA Not Generating Recommendations

**Symptoms:**
```bash
kubectl describe vpa my-app-vpa

# Shows:
# Recommendation: <none>
```

**Diagnosis:**
```bash
# Check VPA recommender logs
kubectl logs -n kube-system deployment/vpa-recommender

# Check if Metrics Server is working
kubectl top pods -n default

# Verify VPA can access metrics
kubectl get --raw /apis/metrics.k8s.io/v1beta1/pods
```

**Solutions:**
```bash
# 1. Ensure Metrics Server is installed
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 2. Wait for sufficient data collection (minimum 24 hours)

# 3. Verify pod has resource requests defined
kubectl get deployment my-app -o yaml | grep -A 5 resources

# 4. Restart VPA recommender
kubectl rollout restart deployment/vpa-recommender -n kube-system
```

#### Issue 2: VPA Causing Excessive Pod Restarts

**Symptoms:**
- Frequent pod evictions
- Service disruption
- High pod restart counts

**Diagnosis:**
```bash
# Check pod restart events
kubectl get events --field-selector reason=Evicted -n production

# View VPA updater logs
kubectl logs -n kube-system deployment/vpa-updater

# Check PodDisruptionBudget
kubectl get pdb -n production
```

**Solutions:**
```yaml
# 1. Add/update PodDisruptionBudget
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # Ensure minimum availability

---
# 2. Change VPA update mode
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa
spec:
  updatePolicy:
    updateMode: "Initial"  # Less disruptive

---
# 3. Increase minReplicas
spec:
  updatePolicy:
    minReplicas: 3  # Don't update if less than 3 replicas
```

#### Issue 3: VPA and HPA Conflict

**Symptoms:**
- Thrashing (rapid scale up/down)
- Unexpected pod restarts
- Resource request fluctuations

**Diagnosis:**
```bash
# Check both VPA and HPA status
kubectl get vpa,hpa -n production

# View scaling events
kubectl get events --sort-by='.lastTimestamp' | grep -E 'Scaled|Evicted'

# Check if both manage same resources
kubectl describe vpa my-app-vpa | grep controlledResources
kubectl describe hpa my-app-hpa | grep metrics
```

**Solutions:**
```yaml
# Option 1: VPA for CPU, HPA for custom metrics
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa
spec:
  resourcePolicy:
    containerPolicies:
    - containerName: '*'
      controlledResources: ["cpu"]  # VPA manages CPU only

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app-hpa
spec:
  metrics:
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second  # HPA uses custom metric
      target:
        type: AverageValue
        averageValue: "1000"

---
# Option 2: Use VPA in "Off" mode
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: my-app-vpa
spec:
  updatePolicy:
    updateMode: "Off"  # Recommendations only
```

## Part 9: Best Practices

### Production Checklist

✅ **Before Enabling VPA:**
- [ ] Metrics Server installed and verified
- [ ] Baseline metrics collected (minimum 7 days)
- [ ] PodDisruptionBudgets configured
- [ ] Resource limits defined in pod specs
- [ ] Monitoring and alerting in place

✅ **VPA Configuration:**
- [ ] Start with "Off" mode for analysis
- [ ] Set appropriate min/max bounds
- [ ] Use "Initial" mode for safety
- [ ] Configure PDBs for "Recreate" mode
- [ ] Test in non-production first

✅ **When Combining VPA + HPA:**
- [ ] VPA manages different resources than HPA
- [ ] Use "Initial" update mode
- [ ] Monitor for conflicts
- [ ] Document the strategy

✅ **Monitoring:**
- [ ] Track VPA recommendations vs actual
- [ ] Alert on excessive evictions
- [ ] Monitor OOMKilled events
- [ ] Track cost savings

### Deployment Patterns

**Pattern 1: Gradual Rollout**

```bash
# Week 1: Analysis only
kubectl apply -f vpa-off-mode.yaml

# Week 2: Apply to test environment
kubectl apply -f vpa-initial-mode-test.yaml

# Week 3: Apply to production (low-risk services)
kubectl apply -f vpa-initial-mode-prod.yaml

# Week 4: Expand to more services
kubectl apply -f vpa-recreate-mode-prod.yaml
```

**Pattern 2: Service Tiers**

```yaml
# Tier 1: Critical services - VPA Off mode
# (manual review required)

# Tier 2: Important services - VPA Initial mode
# (apply on scale events only)

# Tier 3: Standard services - VPA Recreate mode
# (automatic updates with PDB protection)
```

## Key Takeaways

### VPA Value Proposition

1. **Cost Optimization**: 40-70% reduction in wasted resources
2. **Performance**: Right-sized pods perform better
3. **Automation**: Reduces manual resource tuning effort
4. **Reliability**: Prevents OOMKilled events

### When to Use VPA

✅ **Good Fit:**
- Unknown resource requirements
- Variable workload patterns
- Stateful applications
- Long-running services
- Cost optimization initiatives

❌ **Not Recommended:**
- Short-lived jobs (insufficient data)
- Highly variable workloads (frequent restarts)
- Critical services without PDBs
- When combined with HPA on same metric

### VPA Mode Selection Guide

| Scenario | Recommended Mode | Rationale |
|----------|------------------|-----------|
| **Initial deployment** | Off → Initial | Learn first, then apply |
| **Stateless apps** | Recreate | Safe with PDBs |
| **Stateful apps** | Initial | Minimize disruption |
| **Critical services** | Off | Manual control |
| **With HPA** | Initial + Custom HPA metrics | Avoid conflicts |
| **Testing** | Off | No impact |

## Related Topics

### Autoscaling Series
- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - HPA theory and approaches
- **[Part 2: Cluster Autoscaling](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Node-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Practical implementation
- **[Part 4: Monitoring & Alerting](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)** - Observability

## Conclusion

Vertical Pod Autoscaler is a powerful tool for resource optimization in Kubernetes, enabling:

1. **Automated Right-Sizing**: Data-driven resource allocation
2. **Cost Reduction**: Eliminate over-provisioning waste
3. **Performance Improvement**: Prevent throttling and OOMKills
4. **Operational Efficiency**: Reduce manual tuning effort

### Implementation Roadmap

**Month 1: Foundation**
- Install VPA components
- Deploy in "Off" mode cluster-wide
- Collect baseline recommendations

**Month 2: Testing**
- Enable "Initial" mode in test environment
- Validate recommendations
- Establish monitoring

**Month 3: Production**
- Gradual rollout to production
- Start with non-critical services
- Expand based on success

**Month 4: Optimization**
- Fine-tune min/max bounds
- Combine with HPA where appropriate
- Measure cost savings

### Next Steps

1. **Install VPA**: Follow installation guide for your platform
2. **Start Small**: Enable "Off" mode for a few deployments
3. **Analyze Data**: Review recommendations after 7 days
4. **Implement Gradually**: Move to "Initial" or "Recreate" mode
5. **Monitor & Iterate**: Track savings and adjust

VPA transforms resource management from guesswork to data-driven optimization, delivering significant cost savings while improving application reliability. Combined with HPA and Cluster Autoscaler, it completes the Kubernetes autoscaling toolkit.

Happy optimizing! 💰📊
