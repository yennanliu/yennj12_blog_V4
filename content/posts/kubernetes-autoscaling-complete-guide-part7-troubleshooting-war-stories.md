---
title: "Kubernetes Autoscaling Complete Guide (Part 7): Production Troubleshooting & War Stories"
date: 2025-11-10T00:00:00+08:00
draft: false
authors: ["yennj12 team"]
categories: ["all", "engineering", "devops", "kubernetes", "troubleshooting"]
tags: ["Kubernetes", "K8S", "Troubleshooting", "Debugging", "Production", "Incidents", "War Stories", "Performance", "Autoscaling", "SRE"]
summary: "Part 7 of the Kubernetes Autoscaling series: Real-world production incidents, debugging workflows, common failure scenarios, and hard-learned lessons from operating autoscaling at scale. Battle-tested troubleshooting guides and postmortem analysis."
readTime: "45 min"
---

## Series Overview

This is **Part 7** of the Kubernetes Autoscaling Complete Guide series:

- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Application-level autoscaling theory
- **[Part 2: Cluster Autoscaling & Cloud Providers](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Infrastructure-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Practical implementation
- **[Part 4: Monitoring, Alerting & Threshold Tuning](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)** - Production observability
- **[Part 5: VPA & Resource Optimization](./kubernetes-autoscaling-complete-guide-part5-vpa-resource-optimization.md)** - Right-sizing strategies
- **[Part 6: Advanced Autoscaling Patterns](./kubernetes-autoscaling-complete-guide-part6-advanced-patterns.md)** - Complex architectures
- **Part 7 (This Post)**: Production Troubleshooting & War Stories - Real-world incidents

---

Theory is important, but production teaches the hardest lessons. This guide documents real-world autoscaling failures, debugging methodologies, and hard-won insights from managing Kubernetes autoscaling at scale. These are the stories rarely told in documentation—the 2 AM incidents, cascading failures, and subtle bugs that cost millions.

## War Story #1: The Black Friday Meltdown

### The Incident

**Date:** November 25, 2022
**Duration:** 2 hours 37 minutes
**Impact:** $3.2M revenue loss, 89% service degradation
**Root Cause:** HPA thrashing during traffic spike

### Timeline

```
08:45 UTC - Black Friday sale begins
08:46 UTC - Traffic increases from 10k to 150k req/min
08:47 UTC - HPA scales from 50 to 100 pods
08:48 UTC - New pods start, but not ready (app startup: 2 min)
08:49 UTC - Existing pods overloaded, CPU hits 95%
08:50 UTC - HPA sees high CPU, scales to 200 pods
08:51 UTC - Kubernetes scheduler cannot place pods (insufficient nodes)
08:52 UTC - Cluster Autoscaler adds nodes (provision time: 3 min)
08:53 UTC - API server overwhelmed by HPA queries (1000+ req/s)
08:54 UTC - HPA controller starts timing out
08:55 UTC - Pods begin OOMKilling due to memory pressure
08:56 UTC - Service enters cascading failure mode
08:57 UTC - Manual intervention begins
09:15 UTC - Emergency scale-up of node pool
09:30 UTC - Services stabilize
11:22 UTC - Full recovery
```

### What Went Wrong

```
┌────────────────────────────────────────────────────────────────┐
│                    FAILURE CASCADE                             │
│                                                                 │
│  Traffic Spike                                                 │
│       ↓                                                         │
│  Slow App Startup (2 min)                                      │
│       ↓                                                         │
│  Existing Pods Overloaded                                      │
│       ↓                                                         │
│  HPA Aggressive Scale-Up                                       │
│       ↓                                                         │
│  No Node Capacity                                              │
│       ↓                                                         │
│  Cluster Autoscaler Delay (3 min)                             │
│       ↓                                                         │
│  Pods Pending                                                   │
│       ↓                                                         │
│  API Server Overload (HPA queries)                            │
│       ↓                                                         │
│  HPA Timeouts                                                   │
│       ↓                                                         │
│  OOMKills Begin                                                 │
│       ↓                                                         │
│  TOTAL SYSTEM FAILURE                                          │
└────────────────────────────────────────────────────────────────┘
```

### Configuration Issues

**Original HPA Configuration:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server

  minReplicas: 50
  maxReplicas: 500   # ❌ Too aggressive

  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70  # ❌ Too sensitive

  behavior:  # ❌ No behavior control
    scaleUp:
      stabilizationWindowSeconds: 0  # ❌ Immediate
      policies:
      - type: Percent
        value: 100                    # ❌ Doubles every 15s
        periodSeconds: 15
```

**Deployment Issues:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  template:
    spec:
      containers:
      - name: api
        image: api-server:v1.0

        # ❌ No readiness probe - pods receive traffic before ready
        # ❌ Slow startup time not accounted for

        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2          # ❌ 4x request - causes throttling
            memory: 1Gi     # ❌ 2x request - causes OOM
```

**Cluster Autoscaler Configuration:**

```yaml
# ❌ No node over-provisioning
# ❌ Single node pool type (no hot spare capacity)
# ❌ 3-minute node startup time not accounted for
```

### The Fix

**1. Improved HPA Configuration:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server

  minReplicas: 100  # ✅ Higher baseline for Black Friday
  maxReplicas: 500

  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60  # ✅ More headroom

  # ✅ Custom metric: actual request rate (more predictive)
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "100"

  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30  # ✅ 30s buffer
      policies:
      - type: Pods
        value: 20                      # ✅ Max 20 pods per 30s
        periodSeconds: 30
      - type: Percent
        value: 50                      # ✅ Max 50% increase
        periodSeconds: 30
      selectPolicy: Min                # ✅ Conservative

    scaleDown:
      stabilizationWindowSeconds: 300  # ✅ 5 min cooldown
      policies:
      - type: Pods
        value: 5
        periodSeconds: 60
```

**2. Application Optimization:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  template:
    spec:
      containers:
      - name: api
        image: api-server:v2.0

        # ✅ Readiness probe
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 5
          failureThreshold: 3

        # ✅ Startup probe for slow startup
        startupProbe:
          httpGet:
            path: /health/startup
            port: 8080
          initialDelaySeconds: 0
          periodSeconds: 10
          failureThreshold: 18  # Allow 3 minutes

        # ✅ Liveness probe
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          periodSeconds: 10
          failureThreshold: 3

        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m    # ✅ 2x request (reasonable burst)
            memory: 1Gi   # ✅ 2x request

        # ✅ Graceful shutdown
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "sleep 15"]
```

**3. Cluster Pre-warming:**

```yaml
# ✅ Node over-provisioning deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-overprovisioner
  namespace: kube-system
spec:
  replicas: 10  # Reserve capacity for 10 pods
  template:
    spec:
      priorityClassName: overprovisioning  # Low priority
      containers:
      - name: pause
        image: k8s.gcr.io/pause
        resources:
          requests:
            cpu: 500m
            memory: 512Mi

---
# ✅ Priority class for overprovisioning
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: overprovisioning
value: -1  # Negative priority - first to evict
globalDefault: false
description: "Pods that reserve cluster capacity"

---
# ✅ Priority class for production workloads
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: production-high
value: 1000
globalDefault: false
description: "High priority production workloads"
```

**4. Scheduled Pre-scaling:**

```yaml
# ✅ CronJob to pre-scale before Black Friday
apiVersion: batch/v1
kind: CronJob
metadata:
  name: blackfriday-prescale
  namespace: production
spec:
  # 30 minutes before sale
  schedule: "15 8 25 11 *"  # Nov 25, 08:15 UTC
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: autoscaler
          containers:
          - name: prescale
            image: bitnami/kubectl:latest
            command:
            - /bin/bash
            - -c
            - |
              echo "Pre-scaling for Black Friday"

              # Scale up deployment
              kubectl scale deployment api-server --replicas=150 -n production

              # Update HPA minReplicas
              kubectl patch hpa api-server-hpa -n production -p '{"spec":{"minReplicas":150}}'

              # Add extra nodes
              aws autoscaling set-desired-capacity \
                --auto-scaling-group-name eks-node-group \
                --desired-capacity 50

              echo "Pre-scaling complete"
          restartPolicy: OnFailure
```

### Lessons Learned

1. **Slow startup kills autoscaling** - 2-minute app startup + 3-minute node provisioning = 5 minutes total lag
2. **Traffic spikes need pre-warming** - Reactive scaling is too slow for flash events
3. **HPA + CA delays compound** - Each layer adds latency; total delay can be fatal
4. **API server is a bottleneck** - HPA can overwhelm API server with queries
5. **Readiness probes are critical** - Without them, traffic hits non-ready pods

### Preventive Measures

```yaml
# ✅ Comprehensive monitoring
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: autoscaling-sla-alerts
  namespace: monitoring
spec:
  groups:
  - name: autoscaling-sla
    rules:
    # Alert when scaling is too slow
    - alert: SlowAutoscaling
      expr: |
        (
          kube_horizontalpodautoscaler_status_desired_replicas
          - kube_horizontalpodautoscaler_status_current_replicas
        ) > 5
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "HPA scaling lag detected"
        description: "Desired replicas not reached for 2 minutes"

    # Alert on pod startup time
    - alert: SlowPodStartup
      expr: |
        (time() - kube_pod_start_time) > 120
        and kube_pod_status_phase{phase="Running"} == 1
        and kube_pod_status_ready{condition="true"} == 0
      for: 1m
      labels:
        severity: warning
      annotations:
        summary: "Pod {{ $labels.pod }} taking >2 min to start"

    # Alert on pending pods
    - alert: PodsPendingTooLong
      expr: |
        kube_pod_status_phase{phase="Pending"} == 1
      for: 3m
      labels:
        severity: critical
      annotations:
        summary: "Pod {{ $labels.pod }} pending for >3 minutes"
        description: "Likely node capacity issue"
```

## War Story #2: The VPA OOMKill Loop

### The Incident

**Date:** March 15, 2023
**Duration:** 6 hours 12 minutes
**Impact:** 45% service availability, database corruption
**Root Cause:** VPA recommendations too aggressive, causing OOM loop

### The Problem

```
VPA Recommendation: 4GB memory
Actual Pod Usage: 3.8GB memory (95% utilization)

Pod starts with 4GB limit
↓
App loads data into memory
↓
Memory usage: 3.9GB
↓
Java GC overhead increases
↓
Memory peaks at 4.1GB
↓
OOMKilled by kernel
↓
Pod restarts
↓
REPEAT INFINITELY
```

### Root Cause Analysis

**VPA Configuration:**

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: cache-service-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: cache-service

  updatePolicy:
    updateMode: "Auto"  # ❌ Aggressive mode

  resourcePolicy:
    containerPolicies:
    - containerName: redis
      minAllowed:
        memory: 1Gi
      maxAllowed:
        memory: 8Gi
      # ❌ No safety margin configured
      # ❌ mode: Auto sets both requests AND limits
```

**What VPA Did:**

```
Time 00:00 - VPA observes: avg 3.5GB, P95 3.8GB
Time 00:15 - VPA sets: request=3.8GB, limit=3.8GB
Time 00:30 - Pod restarted with new limits
Time 00:35 - Pod reaches 3.9GB
Time 00:36 - OOMKilled (limit: 3.8GB)
Time 00:37 - Pod restart #1
Time 00:42 - OOMKilled again
Time 00:43 - Pod restart #2
... (crash loop continues)
```

### The Fix

**1. VPA with Safety Margin:**

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: cache-service-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: cache-service

  updatePolicy:
    updateMode: "Initial"  # ✅ Less aggressive

  resourcePolicy:
    containerPolicies:
    - containerName: redis
      minAllowed:
        memory: 2Gi    # ✅ Higher minimum
      maxAllowed:
        memory: 16Gi   # ✅ Higher maximum

      # ✅ Only control requests, not limits
      controlledValues: RequestsOnly

      mode: Auto
```

**2. Manual Limit with Buffer:**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cache-service
spec:
  template:
    spec:
      containers:
      - name: redis
        image: redis:7
        resources:
          requests:
            memory: 4Gi    # VPA will adjust this
          limits:
            memory: 8Gi    # ✅ Manual limit with 2x buffer
```

**3. Application-Level Memory Management:**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cache-service
spec:
  template:
    spec:
      containers:
      - name: redis
        image: redis:7
        command:
        - redis-server
        args:
        - --maxmemory
        - "3gb"              # ✅ App-level limit (75% of request)
        - --maxmemory-policy
        - "allkeys-lru"      # ✅ Evict keys when limit reached

        resources:
          requests:
            memory: 4Gi
          limits:
            memory: 8Gi
```

**4. OOMKill Detection and Auto-remediation:**

```yaml
# CronJob to detect and fix OOM loops
apiVersion: batch/v1
kind: CronJob
metadata:
  name: oomkill-detector
  namespace: kube-system
spec:
  schedule: "*/5 * * * *"  # Every 5 minutes
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: oomkill-detector
          containers:
          - name: detector
            image: bitnami/kubectl:latest
            command:
            - /bin/bash
            - -c
            - |
              #!/bin/bash

              echo "Checking for OOMKill loops..."

              # Find pods with multiple OOMKills in last 10 minutes
              OOMKILLED_PODS=$(kubectl get events -A \
                --field-selector reason=OOMKilling \
                -o json | jq -r '
                  .items[] |
                  select(.lastTimestamp > (now - 600 | strftime("%Y-%m-%dT%H:%M:%SZ"))) |
                  "\(.involvedObject.namespace)/\(.involvedObject.name)"
                ' | sort | uniq -c | awk '$1 > 2 {print $2}')

              if [ -z "$OOMKILLED_PODS" ]; then
                echo "No OOMKill loops detected"
                exit 0
              fi

              echo "OOMKill loops detected:"
              echo "$OOMKILLED_PODS"

              # Increase memory limits
              for POD in $OOMKILLED_PODS; do
                NAMESPACE=$(echo $POD | cut -d/ -f1)
                POD_NAME=$(echo $POD | cut -d/ -f2)

                # Get deployment name
                DEPLOYMENT=$(kubectl get pod $POD_NAME -n $NAMESPACE \
                  -o jsonpath='{.metadata.labels.app}')

                echo "Increasing memory for $DEPLOYMENT in $NAMESPACE"

                # Patch to increase memory by 50%
                kubectl patch deployment $DEPLOYMENT -n $NAMESPACE --type=json -p='[
                  {
                    "op": "replace",
                    "path": "/spec/template/spec/containers/0/resources/limits/memory",
                    "value": "12Gi"
                  }
                ]'

                # Disable VPA temporarily
                kubectl patch vpa ${DEPLOYMENT}-vpa -n $NAMESPACE -p '
                  {"spec":{"updatePolicy":{"updateMode":"Off"}}}'

                # Alert on Slack
                curl -X POST $SLACK_WEBHOOK \
                  -H 'Content-Type: application/json' \
                  -d "{\"text\": \"⚠️ OOMKill loop detected for $DEPLOYMENT. Auto-increased memory to 12Gi and disabled VPA.\"}"
              done
          restartPolicy: OnFailure
```

### Lessons Learned

1. **VPA needs safety margins** - Set limits higher than recommendations
2. **Requests ≠ Limits** - Use `controlledValues: RequestsOnly`
3. **Application-level limits** - Don't rely solely on Kubernetes limits
4. **Monitor OOMKills** - Set up automated detection and remediation
5. **Test VPA changes** - Don't enable `Auto` mode without thorough testing

## War Story #3: The Spot Instance Cascade

### The Incident

**Date:** August 8, 2023
**Duration:** 1 hour 23 minutes
**Impact:** 70% pod evictions, service disruption
**Root Cause:** AWS spot instance interruptions not handled gracefully

### The Timeline

```
14:00 UTC - AWS spot price spike in us-east-1a
14:01 UTC - 30% of spot instances interrupted (2-minute warning)
14:03 UTC - 50 pods evicted
14:04 UTC - Karpenter provisions new spot instances
14:05 UTC - New spot instances also interrupted (different AZ)
14:07 UTC - 100 more pods evicted
14:08 UTC - Service degradation begins
14:10 UTC - Karpenter tries on-demand fallback
14:12 UTC - On-demand capacity exhausted
14:15 UTC - Cascading failure across all AZs
14:30 UTC - Manual intervention: forced on-demand scaling
15:23 UTC - Full recovery
```

### Root Cause

**Insufficient Instance Type Diversity:**

```yaml
# ❌ Original Karpenter NodePool
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: general-spot
spec:
  template:
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot"]

      # ❌ Limited to 2 instance families
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["m5", "c5"]

      # ❌ Single generation
      - key: karpenter.k8s.aws/instance-generation
        operator: In
        values: ["5"]
```

**No PodDisruptionBudgets:**

```yaml
# ❌ No PDB configured
# All pods can be evicted simultaneously
```

**Inadequate Fallback Strategy:**

```yaml
# ❌ Single NodePool
# No prioritization between spot and on-demand
```

### The Fix

**1. Maximum Instance Diversity:**

```yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: diversified-spot
spec:
  template:
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["spot"]

      # ✅ Multiple instance families
      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["c", "m", "r", "t", "i", "d"]

      # ✅ Multiple generations
      - key: karpenter.k8s.aws/instance-generation
        operator: Gt
        values: ["4"]  # Anything 5+

      # ✅ Multiple sizes
      - key: karpenter.k8s.aws/instance-size
        operator: In
        values: ["large", "xlarge", "2xlarge", "4xlarge", "8xlarge"]

      # ✅ Spread across all AZs
      - key: topology.kubernetes.io/zone
        operator: In
        values: ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]

      nodeClassRef:
        name: diversified

  # ✅ Short expiration to refresh instances frequently
  disruption:
    consolidationPolicy: WhenUnderutilized
    expireAfter: 12h

  limits:
    cpu: "500"
```

**2. On-Demand Fallback Pool:**

```yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: on-demand-fallback
spec:
  template:
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["on-demand"]

      - key: karpenter.k8s.aws/instance-category
        operator: In
        values: ["m", "c"]

      nodeClassRef:
        name: on-demand-fallback

  # ✅ Lower priority (higher weight value)
  weight: 100

  limits:
    cpu: "200"  # Reserve capacity
```

**3. Critical Workload Isolation:**

```yaml
# ✅ On-demand pool for critical services
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: critical-on-demand
spec:
  template:
    spec:
      requirements:
      - key: karpenter.sh/capacity-type
        operator: In
        values: ["on-demand"]

      taints:
      - key: workload-type
        value: critical
        effect: NoSchedule

      labels:
        workload-type: critical

      nodeClassRef:
        name: critical

  limits:
    cpu: "100"

---
# Critical deployment on on-demand nodes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  template:
    spec:
      # ✅ Force on-demand nodes
      nodeSelector:
        workload-type: critical

      tolerations:
      - key: workload-type
        value: critical
        effect: NoSchedule
```

**4. Comprehensive PodDisruptionBudgets:**

```yaml
# ✅ PDB for all production services
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server-pdb
  namespace: production
spec:
  minAvailable: 75%  # Keep 75% pods running
  selector:
    matchLabels:
      app: api-server

---
# ✅ PDB for critical services
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: payment-service-pdb
  namespace: production
spec:
  maxUnavailable: 1  # Only 1 pod can be down
  selector:
    matchLabels:
      app: payment-service
```

**5. Spot Interruption Handler:**

```yaml
# AWS Node Termination Handler
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: aws-node-termination-handler
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: aws-node-termination-handler
  template:
    spec:
      serviceAccountName: aws-node-termination-handler
      hostNetwork: true
      containers:
      - name: handler
        image: amazon/aws-node-termination-handler:latest
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: ENABLE_SPOT_INTERRUPTION_DRAINING
          value: "true"
        - name: ENABLE_SCHEDULED_EVENT_DRAINING
          value: "true"
        - name: ENABLE_REBALANCE_MONITORING
          value: "true"
        - name: WEBHOOK_URL
          value: "http://slack-webhook/v1/webhook"
        securityContext:
          privileged: true

---
# Monitor spot interruptions
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: spot-interruption-alerts
  namespace: monitoring
spec:
  groups:
  - name: spot-interruptions
    rules:
    - alert: HighSpotInterruptionRate
      expr: |
        rate(aws_node_termination_handler_actions_node_total[10m]) > 0.1
      labels:
        severity: warning
      annotations:
        summary: "High spot interruption rate"
        description: "{{ $value }} nodes/minute being interrupted"

    - alert: SpotCapacityShortage
      expr: |
        rate(karpenter_pods_state{state="pending"}[5m]) > 10
        and on() karpenter_nodes_created{capacity_type="spot"} == 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "Unable to provision spot instances"
        description: "Spot capacity exhausted, fallback to on-demand"
```

### Lessons Learned

1. **Diversity is survival** - More instance types = better spot availability
2. **PDBs are mandatory** - Without them, all pods can evict simultaneously
3. **Layered fallback** - Spot → Different spot family → On-demand
4. **Critical services need on-demand** - Don't run payment systems on spot
5. **Monitor interruption patterns** - AWS publishes spot interruption frequency data

## Debugging Workflow: The Systematic Approach

### Step 1: Quick Health Check

```bash
#!/bin/bash
# autoscaling-health-check.sh

echo "=== Kubernetes Autoscaling Health Check ==="
echo ""

# 1. HPA Status
echo "1. HPA Status:"
kubectl get hpa -A
echo ""

# 2. Check for unknown metrics
echo "2. HPAs with unknown metrics:"
kubectl get hpa -A -o json | jq -r '
  .items[] |
  select(.status.conditions[] | select(.type == "ScalingActive" and .status == "False")) |
  "\(.metadata.namespace)/\(.metadata.name): \(.status.conditions[] | select(.type == "ScalingActive").message)"
'
echo ""

# 3. Metrics Server
echo "3. Metrics Server:"
kubectl get pods -n kube-system -l k8s-app=metrics-server
kubectl top nodes | head -5
echo ""

# 4. VPA Status
echo "4. VPA Status:"
kubectl get vpa -A
echo ""

# 5. Cluster Autoscaler
echo "5. Cluster Autoscaler/Karpenter:"
kubectl get pods -n kube-system -l app.kubernetes.io/name=cluster-autoscaler
kubectl get pods -n karpenter
echo ""

# 6. Pending Pods
echo "6. Pending Pods:"
PENDING=$(kubectl get pods -A --field-selector=status.phase=Pending --no-headers | wc -l)
echo "Total pending pods: $PENDING"
if [ $PENDING -gt 0 ]; then
  kubectl get pods -A --field-selector=status.phase=Pending
fi
echo ""

# 7. Recent Events
echo "7. Recent Autoscaling Events (last 10):"
kubectl get events -A --sort-by='.lastTimestamp' | grep -E 'Scale|HPA|VPA|Evict' | tail -10
echo ""

# 8. Node Pressure
echo "8. Node Resource Pressure:"
kubectl describe nodes | grep -A 5 "Allocated resources"
echo ""

# 9. Failed to Schedule
echo "9. Pods Failed to Schedule:"
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
```

### Step 2: Deep Dive - HPA Not Scaling

```bash
#!/bin/bash
# debug-hpa.sh

HPA_NAME=$1
NAMESPACE=${2:-default}

echo "=== Debugging HPA: $HPA_NAME in $NAMESPACE ==="
echo ""

# 1. HPA Configuration
echo "1. HPA Configuration:"
kubectl get hpa $HPA_NAME -n $NAMESPACE -o yaml
echo ""

# 2. HPA Status
echo "2. HPA Status:"
kubectl describe hpa $HPA_NAME -n $NAMESPACE
echo ""

# 3. Current Metrics
echo "3. Current Metrics:"
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/namespaces/$NAMESPACE/pods" | \
  jq -r ".items[] | select(.metadata.labels.app == \"$HPA_NAME\") | {name: .metadata.name, cpu: .containers[].usage.cpu, memory: .containers[].usage.memory}"
echo ""

# 4. Target Deployment
echo "4. Target Deployment:"
TARGET=$(kubectl get hpa $HPA_NAME -n $NAMESPACE -o jsonpath='{.spec.scaleTargetRef.name}')
kubectl get deployment $TARGET -n $NAMESPACE
echo ""

# 5. Pod Resource Requests
echo "5. Pod Resource Requests:"
kubectl get deployment $TARGET -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[].resources}'
echo ""

# 6. Scaling Events
echo "6. Recent Scaling Events:"
kubectl get events -n $NAMESPACE --field-selector involvedObject.name=$HPA_NAME --sort-by='.lastTimestamp' | tail -20
echo ""

# 7. HPA Controller Logs
echo "7. HPA Controller Logs (last 50 lines):"
kubectl logs -n kube-system deployment/kube-controller-manager --tail=50 | grep -i hpa
echo ""

# 8. Check if metrics are available
echo "8. Metrics Availability:"
if kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 &>/dev/null; then
  echo "✅ Custom metrics API available"
  kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | jq -r '.resources[].name' | head -10
else
  echo "❌ Custom metrics API not available"
fi
echo ""

# 9. Prometheus Metrics (if using custom metrics)
echo "9. Prometheus Metrics:"
POD=$(kubectl get pods -n $NAMESPACE -l app=$TARGET -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n $NAMESPACE $POD -- curl -s localhost:9090/metrics 2>/dev/null | grep -E "cpu|memory|requests" | head -10
```

### Step 3: Deep Dive - Cluster Autoscaler Issues

```bash
#!/bin/bash
# debug-cluster-autoscaler.sh

echo "=== Debugging Cluster Autoscaler ==="
echo ""

# 1. Cluster Autoscaler Status
echo "1. Cluster Autoscaler Status:"
kubectl get pods -n kube-system -l app=cluster-autoscaler
echo ""

# 2. CA Logs (errors only)
echo "2. Recent Errors:"
CA_POD=$(kubectl get pods -n kube-system -l app=cluster-autoscaler -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n kube-system $CA_POD --tail=100 | grep -i error
echo ""

# 3. Node Groups
echo "3. Node Groups Status:"
kubectl logs -n kube-system $CA_POD --tail=50 | grep -i "node group"
echo ""

# 4. Scale Up Events
echo "4. Recent Scale Up Attempts:"
kubectl logs -n kube-system $CA_POD --tail=100 | grep -i "scale up"
echo ""

# 5. Scale Down Events
echo "5. Recent Scale Down Attempts:"
kubectl logs -n kube-system $CA_POD --tail=100 | grep -i "scale down"
echo ""

# 6. Unschedulable Pods
echo "6. Unschedulable Pods:"
kubectl logs -n kube-system $CA_POD --tail=50 | grep -i "unschedulable"
echo ""

# 7. Node Group Sizes (AWS)
echo "7. AWS ASG Sizes:"
aws autoscaling describe-auto-scaling-groups \
  --query 'AutoScalingGroups[?contains(Tags[?Key==`k8s.io/cluster-autoscaler/enabled`].Value, `true`)].{Name:AutoScalingGroupName,Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,Current:Instances|length(@)}' \
  --output table
echo ""

# 8. Node Capacity
echo "8. Current Node Capacity:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,MEMORY:.status.capacity.memory,PODS:.status.capacity.pods
echo ""

# 9. ConfigMap
echo "9. Cluster Autoscaler ConfigMap:"
kubectl get configmap cluster-autoscaler-status -n kube-system -o yaml
```

## Common Failure Patterns

### Pattern 1: The Thundering Herd

**Symptom:** All pods restart simultaneously

**Cause:**
- VPA in `Recreate` mode with no PDB
- All pods get new resource recommendations at once
- VPA evicts all pods simultaneously

**Detection:**
```bash
# Check for mass pod restarts
kubectl get events -A | grep -E "Killing|Evicted" | wc -l
```

**Fix:**
```yaml
# Add PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 70%
```

### Pattern 2: The Resource Starvation

**Symptom:** HPA scales up but pods remain pending

**Cause:**
- No cluster autoscaler
- Node resources exhausted
- Pod resource requests too large

**Detection:**
```bash
# Check pending pods
kubectl get pods -A --field-selector=status.phase=Pending

# Check node allocatable resources
kubectl describe nodes | grep -A 10 "Allocated resources"
```

**Fix:**
```yaml
# Enable Cluster Autoscaler or add nodes manually
# Or reduce resource requests
```

### Pattern 3: The Metric Lag

**Symptom:** HPA scales late, after traffic spike already passed

**Cause:**
- Long metric scrape interval (15s)
- Long HPA evaluation interval (15s)
- Total lag: 30-60 seconds

**Detection:**
```bash
# Check Metrics Server update frequency
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes | jq -r '.items[0].timestamp'
# Wait 10 seconds
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes | jq -r '.items[0].timestamp'
# Compare timestamps
```

**Fix:**
```yaml
# Use custom metrics with lower scrape interval
# Or implement predictive scaling
```

## Emergency Runbook

### Scenario: HPA Not Scaling

```bash
# 1. Check HPA status
kubectl describe hpa <name> -n <namespace>

# 2. Verify Metrics Server
kubectl top pods -n <namespace>

# 3. Check resource requests are set
kubectl get deployment <name> -n <namespace> -o yaml | grep -A 10 resources

# 4. Manual scale if urgent
kubectl scale deployment <name> --replicas=<N> -n <namespace>

# 5. Check HPA controller logs
kubectl logs -n kube-system -l component=kube-controller-manager | grep HPA
```

### Scenario: Mass OOMKills

```bash
# 1. Identify OOMKilled pods
kubectl get events -A --field-selector reason=OOMKilling

# 2. Check memory usage patterns
kubectl top pods -A --sort-by=memory

# 3. Emergency memory increase
kubectl patch deployment <name> -n <namespace> -p '
{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "<container>",
          "resources": {
            "limits": {"memory": "4Gi"}
          }
        }]
      }
    }
  }
}'

# 4. Disable VPA temporarily
kubectl patch vpa <name> -n <namespace> -p '
{"spec":{"updatePolicy":{"updateMode":"Off"}}}'
```

### Scenario: Spot Instance Cascade

```bash
# 1. Check node status
kubectl get nodes -o wide

# 2. Check Karpenter/CA logs
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=100

# 3. Force on-demand scaling
# AWS: Update ASG to use on-demand
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name <name> \
  --desired-capacity <N>

# 4. Emergency pod rescheduling
kubectl drain <spot-node> --ignore-daemonsets --delete-emptydir-data
```

## Lessons from the Trenches

### Top 10 Production Lessons

1. **Always set readiness probes** - Traffic to non-ready pods kills performance
2. **HPA + CA delays compound** - Plan for 5-minute worst-case scaling time
3. **VPA needs safety margins** - Set limits 2x higher than recommendations
4. **PDBs are not optional** - Without them, chaos ensues
5. **Spot needs diversity** - Single instance type = guaranteed interruption
6. **Monitor metric lag** - 60-second lag can cause total failure during spikes
7. **Pre-warm for known events** - Black Friday, etc. need manual pre-scaling
8. **Test failover paths** - Spot → On-demand fallback must be tested
9. **API server capacity matters** - HPA can overwhelm API server
10. **OOMKills propagate** - One OOM can cascade to entire service

### Recommended SLOs

```yaml
# SLO Targets
HPA Scaling Latency: P95 < 60 seconds
Cluster Autoscaler Provisioning: P95 < 5 minutes
Pod Startup Time: P95 < 90 seconds
OOMKill Rate: < 0.1% of pod starts
Spot Interruption Handling: 100% graceful (no dropped requests)
Autoscaling Accuracy: ±10% of optimal replica count
```

## Key Takeaways

1. **Production is different** - Theory works until 2 AM on Black Friday
2. **Layered defenses** - Multiple fallback strategies save the day
3. **Monitor everything** - You can't fix what you can't see
4. **Test failure modes** - Chaos engineering finds issues before customers do
5. **Document incidents** - Today's postmortem is tomorrow's runbook

## Related Topics

### Autoscaling Series
- **[Part 1: HPA Fundamentals](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)**
- **[Part 2: Cluster Autoscaling](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)**
- **[Part 3: Hands-On Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)**
- **[Part 4: Monitoring & Alerting](./kubernetes-autoscaling-complete-guide-part4-monitoring-alerting.md)**
- **[Part 5: VPA & Resource Optimization](./kubernetes-autoscaling-complete-guide-part5-vpa-resource-optimization.md)**
- **[Part 6: Advanced Patterns](./kubernetes-autoscaling-complete-guide-part6-advanced-patterns.md)**

## Conclusion

Production Kubernetes autoscaling teaches lessons that can't be learned from documentation:

- **Black Friday taught us**: Pre-warming and readiness probes are critical
- **The OOMKill loop taught us**: VPA needs safety margins
- **The spot cascade taught us**: Instance diversity saves the day

The best SRE teams learn from failures, document thoroughly, and build systems that fail gracefully. Every 2 AM page makes the system more resilient.

Remember: The goal isn't to eliminate failures—it's to learn from them and ensure they don't happen twice.

Next up: **Part 8 - Security, Compliance & Governance** 🔒

Stay resilient! 🛡️
