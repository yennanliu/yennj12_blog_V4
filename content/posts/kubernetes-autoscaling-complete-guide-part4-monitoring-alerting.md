---
title: "Kubernetes Autoscaling Complete Guide (Part 4): Monitoring, Alerting & Threshold Tuning"
date: 2025-11-09T18:00:00+08:00
draft: false
authors: ["yennj12 team"]
categories: ["all", "engineering", "devops", "kubernetes", "monitoring"]
tags: ["Kubernetes", "K8S", "Monitoring", "Prometheus", "Grafana", "Alerting", "EKS", "Observability", "Metrics", "Dashboard", "AlertManager"]
summary: "Part 4 of the Kubernetes Autoscaling series: Complete guide to monitoring EKS autoscaling with Prometheus and Grafana. Includes CDK setup, alerting rules, custom dashboards, and threshold tuning strategies for production-grade observability."
readTime: "30 min"
---

## Series Overview

This is **Part 4** of the Kubernetes Autoscaling Complete Guide series:

- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Application-level autoscaling theory
- **[Part 2: Cluster Autoscaling & Cloud Providers](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Infrastructure-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Practical implementation with Apache-PHP
- **Part 4 (This Post)**: Monitoring, Alerting & Threshold Tuning - Production observability

---

Building on the HPA demo from Part 3, this guide implements a complete monitoring and alerting stack for your EKS cluster. We'll deploy Prometheus for metrics collection, Grafana for visualization, AlertManager for notifications, and establish best practices for threshold tuning.

## What We'll Build

```
┌──────────────────────────────────────────────────────────────────────┐
│                  MONITORING ARCHITECTURE                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    DATA COLLECTION LAYER                       │ │
│  │                                                                 │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │ │
│  │  │  Metrics │  │   Node   │  │   kube   │  │   HPA    │      │ │
│  │  │  Server  │  │ Exporter │  │  state   │  │  metrics │      │ │
│  │  │          │  │          │  │  metrics │  │          │      │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │ │
│  │       │             │             │             │             │ │
│  │       └─────────────┴─────────────┴─────────────┘             │ │
│  │                            ↓                                   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                               ↓                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                  PROMETHEUS (Storage & Queries)                │ │
│  │                                                                 │ │
│  │  • Time-series database                                        │ │
│  │  • PromQL query engine                                         │ │
│  │  • Service discovery                                            │ │
│  │  • Recording rules                                              │ │
│  └────────────┬───────────────────────┬──────────────────────────┘ │
│               │                       │                             │
│               ↓                       ↓                             │
│  ┌────────────────────────┐  ┌──────────────────────────────────┐ │
│  │    ALERTMANAGER        │  │          GRAFANA                 │ │
│  │                        │  │                                   │ │
│  │  • Alert routing       │  │  • Dashboards                    │ │
│  │  • Grouping            │  │  • Data sources                  │ │
│  │  • Deduplication       │  │  • Annotations                   │ │
│  │  • Silencing           │  │  • Variables                     │ │
│  └────┬───────────────────┘  └──────────────────────────────────┘ │
│       │                                                             │
│       ↓                                                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │               NOTIFICATION CHANNELS                            │ │
│  │                                                                 │ │
│  │  Email  │  Slack  │  PagerDuty  │  OpsGenie  │  Webhook       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

Starting from the Part 3 setup, ensure you have:

```bash
# EKS cluster from Part 3 running
kubectl get nodes

# Helm installed
helm version

# kubectl configured
kubectl config current-context

# Part 3 application deployed
kubectl get deployment php-apache
kubectl get hpa php-apache-hpa
```

## Part 1: Prometheus Stack Setup

### Option A: Using kube-prometheus-stack (Recommended)

The `kube-prometheus-stack` includes Prometheus, Grafana, AlertManager, and exporters in one package.

#### Step 1: Update CDK Stack

Add Prometheus stack to `lib/eks-hpa-demo-stack.ts`:

```typescript
import * as cdk from 'aws-cdk-lib';
import * as eks from 'aws-cdk-lib/aws-eks';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class EksHpaDemoStack extends cdk.Stack {
  public readonly cluster: eks.Cluster;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ... existing VPC and cluster code from Part 3 ...

    // Create namespace for monitoring
    const monitoringNamespace = this.cluster.addManifest('monitoring-namespace', {
      apiVersion: 'v1',
      kind: 'Namespace',
      metadata: {
        name: 'monitoring',
        labels: {
          name: 'monitoring',
        },
      },
    });

    // Install kube-prometheus-stack using Helm
    const prometheusStack = this.cluster.addHelmChart('PrometheusStack', {
      chart: 'kube-prometheus-stack',
      repository: 'https://prometheus-community.github.io/helm-charts',
      namespace: 'monitoring',
      release: 'prometheus',
      version: '54.2.2', // Check for latest version
      wait: true,
      timeout: cdk.Duration.minutes(15),

      values: {
        // Prometheus configuration
        prometheus: {
          prometheusSpec: {
            // Retention period
            retention: '30d',
            retentionSize: '50GB',

            // Storage
            storageSpec: {
              volumeClaimTemplate: {
                spec: {
                  accessModes: ['ReadWriteOnce'],
                  resources: {
                    requests: {
                      storage: '50Gi',
                    },
                  },
                  storageClassName: 'gp3', // AWS EBS gp3
                },
              },
            },

            // Resource limits
            resources: {
              requests: {
                cpu: '500m',
                memory: '2Gi',
              },
              limits: {
                cpu: '2000m',
                memory: '4Gi',
              },
            },

            // Service monitors to scrape
            serviceMonitorSelectorNilUsesHelmValues: false,
            podMonitorSelectorNilUsesHelmValues: false,

            // Additional scrape configs
            additionalScrapeConfigs: [
              {
                job_name: 'kubernetes-pods',
                kubernetes_sd_configs: [
                  {
                    role: 'pod',
                  },
                ],
                relabel_configs: [
                  {
                    source_labels: ['__meta_kubernetes_pod_annotation_prometheus_io_scrape'],
                    action: 'keep',
                    regex: 'true',
                  },
                  {
                    source_labels: ['__meta_kubernetes_pod_annotation_prometheus_io_path'],
                    action: 'replace',
                    target_label: '__metrics_path__',
                    regex: '(.+)',
                  },
                  {
                    source_labels: ['__address__', '__meta_kubernetes_pod_annotation_prometheus_io_port'],
                    action: 'replace',
                    regex: '([^:]+)(?::\\d+)?;(\\d+)',
                    replacement: '$1:$2',
                    target_label: '__address__',
                  },
                ],
              },
            ],
          },

          // Service configuration
          service: {
            type: 'LoadBalancer', // Or ClusterIP with ingress
            annotations: {
              'service.beta.kubernetes.io/aws-load-balancer-type': 'nlb',
              'service.beta.kubernetes.io/aws-load-balancer-internal': 'true',
            },
          },
        },

        // Grafana configuration
        grafana: {
          enabled: true,
          adminPassword: 'admin123', // Change in production!

          persistence: {
            enabled: true,
            storageClassName: 'gp3',
            size: '10Gi',
          },

          resources: {
            requests: {
              cpu: '250m',
              memory: '512Mi',
            },
            limits: {
              cpu: '500m',
              memory: '1Gi',
            },
          },

          service: {
            type: 'LoadBalancer',
            annotations: {
              'service.beta.kubernetes.io/aws-load-balancer-type': 'nlb',
              'service.beta.kubernetes.io/aws-load-balancer-internal': 'true',
            },
          },

          // Pre-configured data sources
          datasources: {
            'datasources.yaml': {
              apiVersion: 1,
              datasources: [
                {
                  name: 'Prometheus',
                  type: 'prometheus',
                  url: 'http://prometheus-kube-prometheus-prometheus.monitoring:9090',
                  access: 'proxy',
                  isDefault: true,
                },
              ],
            },
          },

          // Default dashboards
          defaultDashboardsEnabled: true,
          defaultDashboardsTimezone: 'UTC',

          // Additional dashboard providers
          dashboardProviders: {
            'dashboardproviders.yaml': {
              apiVersion: 1,
              providers: [
                {
                  name: 'default',
                  orgId: 1,
                  folder: '',
                  type: 'file',
                  disableDeletion: false,
                  editable: true,
                  options: {
                    path: '/var/lib/grafana/dashboards/default',
                  },
                },
              ],
            },
          },
        },

        // AlertManager configuration
        alertmanager: {
          enabled: true,

          alertmanagerSpec: {
            storage: {
              volumeClaimTemplate: {
                spec: {
                  accessModes: ['ReadWriteOnce'],
                  resources: {
                    requests: {
                      storage: '10Gi',
                    },
                  },
                  storageClassName: 'gp3',
                },
              },
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

          config: {
            global: {
              resolve_timeout: '5m',
            },
            route: {
              group_by: ['alertname', 'cluster', 'service'],
              group_wait: '10s',
              group_interval: '10s',
              repeat_interval: '12h',
              receiver: 'default',
              routes: [
                {
                  match: {
                    alertname: 'Watchdog',
                  },
                  receiver: 'null',
                },
                {
                  match: {
                    severity: 'critical',
                  },
                  receiver: 'critical',
                  continue: true,
                },
                {
                  match: {
                    severity: 'warning',
                  },
                  receiver: 'warning',
                },
              ],
            },
            receivers: [
              {
                name: 'null',
              },
              {
                name: 'default',
                // Configure in next section
              },
              {
                name: 'critical',
                // Configure in next section
              },
              {
                name: 'warning',
                // Configure in next section
              },
            ],
          },
        },

        // Node exporter (collects node metrics)
        nodeExporter: {
          enabled: true,
        },

        // Kube-state-metrics (K8s object metrics)
        kubeStateMetrics: {
          enabled: true,
        },

        // Prometheus operator
        prometheusOperator: {
          resources: {
            requests: {
              cpu: '200m',
              memory: '256Mi',
            },
            limits: {
              cpu: '500m',
              memory: '512Mi',
            },
          },
        },
      },
    });

    prometheusStack.node.addDependency(monitoringNamespace);

    // Output monitoring URLs
    new cdk.CfnOutput(this, 'PrometheusURL', {
      value: 'http://prometheus-kube-prometheus-prometheus.monitoring:9090',
      description: 'Prometheus internal URL',
    });

    new cdk.CfnOutput(this, 'GrafanaURL', {
      value: 'Access via: kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80',
      description: 'Grafana port-forward command',
    });

    new cdk.CfnOutput(this, 'AlertManagerURL', {
      value: 'http://prometheus-kube-prometheus-alertmanager.monitoring:9093',
      description: 'AlertManager internal URL',
    });
  }
}
```

#### Step 2: Deploy Updated Stack

```bash
cd cdk

# Deploy monitoring stack
cdk deploy

# Wait for Helm chart installation (takes 5-10 minutes)

# Verify installation
kubectl get pods -n monitoring

# Expected output:
# NAME                                                     READY   STATUS    RESTARTS   AGE
# alertmanager-prometheus-kube-prom-alertmanager-0         2/2     Running   0          5m
# prometheus-grafana-xxx                                   3/3     Running   0          5m
# prometheus-kube-prom-operator-xxx                        1/1     Running   0          5m
# prometheus-kube-state-metrics-xxx                        1/1     Running   0          5m
# prometheus-prometheus-node-exporter-xxx                  1/1     Running   0          5m
# prometheus-prometheus-kube-prom-prometheus-0             2/2     Running   0          5m
```

### Option B: Manual Helm Installation

If you prefer manual installation:

```bash
# Add Prometheus community Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Create monitoring namespace
kubectl create namespace monitoring

# Install kube-prometheus-stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set prometheus.prometheusSpec.retention=30d \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=50Gi \
  --set grafana.adminPassword=admin123 \
  --set grafana.persistence.enabled=true \
  --set grafana.persistence.size=10Gi \
  --wait

# Verify installation
kubectl get pods -n monitoring
kubectl get svc -n monitoring
```

## Part 2: Accessing Monitoring Tools

### Access Grafana

```bash
# Method 1: Port forwarding (recommended for testing)
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# Access at: http://localhost:3000
# Username: admin
# Password: admin123 (or what you set in values)

# Method 2: LoadBalancer (if configured)
kubectl get svc -n monitoring prometheus-grafana

# Get external IP/DNS
export GRAFANA_URL=$(kubectl get svc -n monitoring prometheus-grafana -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Grafana: http://$GRAFANA_URL"
```

### Access Prometheus

```bash
# Port forward Prometheus
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090

# Access at: http://localhost:9090

# Query examples:
# - up{job="kubernetes-nodes"}
# - kube_pod_container_resource_requests_cpu_cores
# - rate(container_cpu_usage_seconds_total[5m])
```

### Access AlertManager

```bash
# Port forward AlertManager
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-alertmanager 9093:9093

# Access at: http://localhost:9093
```

## Part 3: HPA-Specific Monitoring

### Create ServiceMonitor for PHP-Apache

Create `k8s/servicemonitor.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: php-apache-monitor
  namespace: default
  labels:
    app: php-apache
    release: prometheus  # Must match Prometheus release name
spec:
  selector:
    matchLabels:
      app: php-apache
  endpoints:
  - port: http
    interval: 15s
    path: /metrics  # If your app exposes metrics
    # Or use a sidecar exporter

  namespaceSelector:
    matchNames:
    - default
```

### Create PrometheusRule for HPA Alerts

Create `k8s/prometheus-rules.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hpa-alerts
  namespace: monitoring
  labels:
    release: prometheus  # Must match Prometheus release name
spec:
  groups:
  - name: hpa-autoscaling
    interval: 30s
    rules:
    # Alert when HPA is at maximum replicas
    - alert: HPAMaxedOut
      expr: |
        (
          kube_horizontalpodautoscaler_status_current_replicas{namespace="default"}
          /
          kube_horizontalpodautoscaler_spec_max_replicas{namespace="default"}
        ) >= 1
      for: 5m
      labels:
        severity: warning
        component: hpa
      annotations:
        summary: "HPA {{ $labels.horizontalpodautoscaler }} at maximum capacity"
        description: "HPA {{ $labels.horizontalpodautoscaler }} in namespace {{ $labels.namespace }} has been at maximum replicas ({{ $value }}) for more than 5 minutes. Consider increasing maxReplicas or adding more nodes."
        dashboard_url: "http://grafana/d/hpa-dashboard"

    # Alert when HPA cannot scale
    - alert: HPAUnableToScale
      expr: |
        kube_horizontalpodautoscaler_status_condition{condition="ScalingLimited",status="true"} == 1
      for: 10m
      labels:
        severity: warning
        component: hpa
      annotations:
        summary: "HPA {{ $labels.horizontalpodautoscaler }} unable to scale"
        description: "HPA {{ $labels.horizontalpodautoscaler }} has been unable to scale for 10 minutes. Check for resource constraints or scaling limits."

    # Alert when HPA cannot fetch metrics
    - alert: HPAMetricsUnavailable
      expr: |
        kube_horizontalpodautoscaler_status_condition{condition="ScalingActive",status="false"} == 1
      for: 5m
      labels:
        severity: critical
        component: hpa
      annotations:
        summary: "HPA {{ $labels.horizontalpodautoscaler }} metrics unavailable"
        description: "HPA {{ $labels.horizontalpodautoscaler }} cannot fetch metrics. Check Metrics Server status."
        runbook_url: "https://docs/troubleshooting/hpa-metrics"

    # Alert on rapid scaling activity (thrashing)
    - alert: HPAScalingThrashing
      expr: |
        rate(kube_horizontalpodautoscaler_status_current_replicas[15m]) > 0.5
      for: 30m
      labels:
        severity: warning
        component: hpa
      annotations:
        summary: "HPA {{ $labels.horizontalpodautoscaler }} scaling too frequently"
        description: "HPA is scaling up/down frequently ({{ $value }} changes/min), indicating possible threshold misconfiguration or unstable load."

    # Alert when CPU usage is consistently high
    - alert: HighCPUUsageBeforeScaling
      expr: |
        (
          sum(rate(container_cpu_usage_seconds_total{namespace="default",pod=~"php-apache.*"}[5m])) by (pod)
          /
          sum(kube_pod_container_resource_requests{namespace="default",pod=~"php-apache.*",resource="cpu"}) by (pod)
        ) > 0.9
      for: 3m
      labels:
        severity: warning
        component: application
      annotations:
        summary: "Pod {{ $labels.pod }} CPU usage very high"
        description: "CPU usage is at {{ $value | humanizePercentage }} of requested resources. Scaling may be delayed."

    # Alert when memory usage is high
    - alert: HighMemoryUsage
      expr: |
        (
          sum(container_memory_working_set_bytes{namespace="default",pod=~"php-apache.*"}) by (pod)
          /
          sum(kube_pod_container_resource_limits{namespace="default",pod=~"php-apache.*",resource="memory"}) by (pod)
        ) > 0.9
      for: 5m
      labels:
        severity: warning
        component: application
      annotations:
        summary: "Pod {{ $labels.pod }} memory usage critical"
        description: "Memory usage is at {{ $value | humanizePercentage }} of limits. Pod may be OOMKilled."

    # Alert when pods are pending (cannot be scheduled)
    - alert: PodsPendingScheduling
      expr: |
        sum(kube_pod_status_phase{namespace="default",pod=~"php-apache.*",phase="Pending"}) > 0
      for: 10m
      labels:
        severity: critical
        component: scheduler
      annotations:
        summary: "{{ $value }} php-apache pods pending scheduling"
        description: "Pods cannot be scheduled. Check node resources and Cluster Autoscaler status."

  - name: cluster-resources
    interval: 30s
    rules:
    # Alert when cluster CPU is near capacity
    - alert: ClusterCPUPressure
      expr: |
        (
          sum(kube_node_status_allocatable{resource="cpu"})
          -
          sum(kube_pod_container_resource_requests{resource="cpu"})
        ) < 2
      for: 5m
      labels:
        severity: warning
        component: cluster
      annotations:
        summary: "Cluster CPU capacity low"
        description: "Only {{ $value }} CPU cores available cluster-wide. Consider adding nodes or enabling Cluster Autoscaler."

    # Alert when cluster memory is near capacity
    - alert: ClusterMemoryPressure
      expr: |
        (
          sum(kube_node_status_allocatable{resource="memory"})
          -
          sum(kube_pod_container_resource_requests{resource="memory"})
        ) / (1024 * 1024 * 1024) < 4
      for: 5m
      labels:
        severity: warning
        component: cluster
      annotations:
        summary: "Cluster memory capacity low"
        description: "Only {{ $value }}GB memory available cluster-wide."

    # Alert on node not ready
    - alert: NodeNotReady
      expr: |
        kube_node_status_condition{condition="Ready",status="true"} == 0
      for: 5m
      labels:
        severity: critical
        component: node
      annotations:
        summary: "Node {{ $labels.node }} not ready"
        description: "Node has been not ready for 5 minutes."
```

Apply the monitoring configurations:

```bash
kubectl apply -f k8s/servicemonitor.yaml
kubectl apply -f k8s/prometheus-rules.yaml

# Verify PrometheusRule is loaded
kubectl get prometheusrule -n monitoring

# Check if rules are active in Prometheus
# Port forward and visit: http://localhost:9090/rules
```

## Part 4: Custom Grafana Dashboards

### Dashboard 1: HPA Overview

Create `grafana-dashboards/hpa-overview.json`:

```json
{
  "dashboard": {
    "title": "HPA Autoscaling Overview",
    "tags": ["kubernetes", "hpa", "autoscaling"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Current vs Desired Replicas",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "kube_horizontalpodautoscaler_status_current_replicas{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}",
            "legendFormat": "Current Replicas",
            "refId": "A"
          },
          {
            "expr": "kube_horizontalpodautoscaler_status_desired_replicas{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}",
            "legendFormat": "Desired Replicas",
            "refId": "B"
          },
          {
            "expr": "kube_horizontalpodautoscaler_spec_min_replicas{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}",
            "legendFormat": "Min Replicas",
            "refId": "C"
          },
          {
            "expr": "kube_horizontalpodautoscaler_spec_max_replicas{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}",
            "legendFormat": "Max Replicas",
            "refId": "D"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "min": 0
          }
        }
      },
      {
        "title": "CPU Utilization vs Target",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "sum(rate(container_cpu_usage_seconds_total{namespace=\"default\",pod=~\"php-apache.*\"}[5m])) by (pod) / sum(kube_pod_container_resource_requests{namespace=\"default\",pod=~\"php-apache.*\",resource=\"cpu\"}) by (pod) * 100",
            "legendFormat": "{{ pod }} CPU %",
            "refId": "A"
          },
          {
            "expr": "kube_horizontalpodautoscaler_spec_target_metric{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}",
            "legendFormat": "HPA Target (%)",
            "refId": "B"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100
          }
        }
      },
      {
        "title": "Scaling Events Timeline",
        "type": "table",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "changes(kube_horizontalpodautoscaler_status_current_replicas{namespace=\"default\",horizontalpodautoscaler=\"php-apache-hpa\"}[1h]) > 0",
            "format": "table",
            "instant": true
          }
        ]
      },
      {
        "title": "Pod Count by Status",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 16},
        "targets": [
          {
            "expr": "count(kube_pod_info{namespace=\"default\",pod=~\"php-apache.*\"})",
            "legendFormat": "Total Pods"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": null, "color": "green"},
                {"value": 8, "color": "yellow"},
                {"value": 10, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "title": "Average Response Time",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 20},
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{namespace=\"default\",pod=~\"php-apache.*\"}[5m]))",
            "legendFormat": "P95 Latency",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{namespace=\"default\",pod=~\"php-apache.*\"}[5m]))",
            "legendFormat": "P99 Latency",
            "refId": "B"
          }
        ]
      },
      {
        "title": "Request Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 20},
        "targets": [
          {
            "expr": "sum(rate(http_requests_total{namespace=\"default\",pod=~\"php-apache.*\"}[5m]))",
            "legendFormat": "Requests/sec"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps"
          }
        }
      }
    ],
    "refresh": "30s",
    "time": {
      "from": "now-1h",
      "to": "now"
    }
  }
}
```

### Dashboard 2: Resource Utilization

Create comprehensive resource monitoring dashboard:

```bash
# Download pre-built Kubernetes dashboards
# Dashboard ID 15661 - Kubernetes Cluster Monitoring
# Dashboard ID 15760 - Kubernetes Views / Global

# Import via Grafana UI:
# 1. Go to Dashboards → Import
# 2. Enter dashboard ID
# 3. Select Prometheus data source
# 4. Click Import
```

### Import Dashboards via ConfigMap

Create `k8s/grafana-dashboards.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: hpa-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  hpa-dashboard.json: |
    {
      "annotations": {
        "list": [
          {
            "builtIn": 1,
            "datasource": "-- Grafana --",
            "enable": true,
            "hide": true,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts",
            "type": "dashboard"
          }
        ]
      },
      "editable": true,
      "gnetId": null,
      "graphTooltip": 0,
      "id": null,
      "links": [],
      "panels": [
        {
          "datasource": "Prometheus",
          "fieldConfig": {
            "defaults": {
              "color": {
                "mode": "palette-classic"
              },
              "custom": {
                "axisLabel": "",
                "axisPlacement": "auto",
                "barAlignment": 0,
                "drawStyle": "line",
                "fillOpacity": 10,
                "gradientMode": "none",
                "hideFrom": {
                  "tooltip": false,
                  "viz": false,
                  "legend": false
                },
                "lineInterpolation": "linear",
                "lineWidth": 1,
                "pointSize": 5,
                "scaleDistribution": {
                  "type": "linear"
                },
                "showPoints": "never",
                "spanNulls": true
              },
              "mappings": [],
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  {
                    "color": "green",
                    "value": null
                  }
                ]
              },
              "unit": "short"
            },
            "overrides": []
          },
          "gridPos": {
            "h": 9,
            "w": 12,
            "x": 0,
            "y": 0
          },
          "id": 2,
          "options": {
            "legend": {
              "calcs": [],
              "displayMode": "list",
              "placement": "bottom"
            },
            "tooltip": {
              "mode": "single"
            }
          },
          "pluginVersion": "8.0.0",
          "targets": [
            {
              "expr": "kube_horizontalpodautoscaler_status_current_replicas{namespace=\"default\"}",
              "interval": "",
              "legendFormat": "{{ horizontalpodautoscaler }} - Current",
              "refId": "A"
            },
            {
              "expr": "kube_horizontalpodautoscaler_status_desired_replicas{namespace=\"default\"}",
              "interval": "",
              "legendFormat": "{{ horizontalpodautoscaler }} - Desired",
              "refId": "B"
            }
          ],
          "title": "HPA Replica Count",
          "type": "timeseries"
        }
      ],
      "refresh": "30s",
      "schemaVersion": 27,
      "style": "dark",
      "tags": ["kubernetes", "hpa"],
      "templating": {
        "list": []
      },
      "time": {
        "from": "now-6h",
        "to": "now"
      },
      "timepicker": {},
      "timezone": "",
      "title": "HPA Monitoring",
      "uid": "hpa-monitoring",
      "version": 1
    }
```

Apply dashboard:

```bash
kubectl apply -f k8s/grafana-dashboards.yaml

# Restart Grafana to pick up new dashboard
kubectl rollout restart deployment -n monitoring prometheus-grafana
```

## Part 5: AlertManager Configuration

### Configure Notification Channels

#### Slack Integration

Update AlertManager config in Helm values or via ConfigMap:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-config
  namespace: monitoring
type: Opaque
stringData:
  alertmanager.yaml: |
    global:
      resolve_timeout: 5m
      slack_api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'

    route:
      group_by: ['alertname', 'cluster', 'service']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 12h
      receiver: 'slack-notifications'
      routes:
      - match:
          alertname: Watchdog
        receiver: 'null'
      - match:
          severity: critical
        receiver: 'slack-critical'
        continue: true
      - match:
          severity: warning
        receiver: 'slack-warnings'

    receivers:
    - name: 'null'

    - name: 'slack-notifications'
      slack_configs:
      - channel: '#kubernetes-alerts'
        title: 'Kubernetes Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'
        send_resolved: true

    - name: 'slack-critical'
      slack_configs:
      - channel: '#kubernetes-critical'
        title: ':fire: CRITICAL Alert'
        text: '{{ range .Alerts }}*{{ .Labels.alertname }}*\n{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'
        send_resolved: true
        color: 'danger'

    - name: 'slack-warnings'
      slack_configs:
      - channel: '#kubernetes-warnings'
        title: ':warning: Warning Alert'
        text: '{{ range .Alerts }}*{{ .Labels.alertname }}*\n{{ .Annotations.summary }}\n{{ end }}'
        send_resolved: true
        color: 'warning'

    inhibit_rules:
    - source_match:
        severity: 'critical'
      target_match:
        severity: 'warning'
      equal: ['alertname', 'cluster', 'service']
```

#### Email Notifications

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@example.com'
  smtp_auth_username: 'alerts@example.com'
  smtp_auth_password: 'your-app-password'

receivers:
- name: 'email-notifications'
  email_configs:
  - to: 'team@example.com'
    headers:
      Subject: '[{{ .Status }}] {{ .GroupLabels.alertname }}'
    html: |
      <h2>Alert: {{ .GroupLabels.alertname }}</h2>
      {{ range .Alerts }}
      <h3>{{ .Annotations.summary }}</h3>
      <p>{{ .Annotations.description }}</p>
      <p><strong>Severity:</strong> {{ .Labels.severity }}</p>
      <p><strong>Started:</strong> {{ .StartsAt }}</p>
      {{ end }}
```

#### PagerDuty Integration

```yaml
receivers:
- name: 'pagerduty'
  pagerduty_configs:
  - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
    description: '{{ .GroupLabels.alertname }}: {{ .Annotations.summary }}'
    severity: '{{ .Labels.severity }}'
```

### Apply AlertManager Configuration

```bash
# Apply secret
kubectl apply -f k8s/alertmanager-secret.yaml

# Or update via Helm
helm upgrade prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --reuse-values \
  --set alertmanager.config.global.slack_api_url='https://hooks.slack.com/...' \
  --set alertmanager.config.route.receiver='slack-notifications'

# Restart AlertManager
kubectl rollout restart statefulset -n monitoring alertmanager-prometheus-kube-prom-alertmanager
```

## Part 6: Threshold Tuning Strategies

### Understanding the HPA Formula

```
desiredReplicas = ceil[currentReplicas * (currentMetricValue / targetMetricValue)]

Target Utilization = (Sum of Pod Resource Usage) / (Sum of Pod Resource Requests)
```

### Step 1: Baseline Measurement

```bash
# Run application under normal load for 1 hour
kubectl run baseline-load --image=busybox:1.36 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://php-apache; sleep 0.1; done"

# Collect metrics
kubectl top pods -l app=php-apache --watch > baseline-metrics.txt

# Query Prometheus for average CPU usage
# PromQL: avg(rate(container_cpu_usage_seconds_total{pod=~"php-apache.*"}[1h]))

# Example result: 150m (0.15 cores)
```

### Step 2: Load Testing

```bash
# Install hey (HTTP load generator)
# macOS: brew install hey
# Linux: wget https://hey-release.s3.us-east-2.amazonaws.com/hey_linux_amd64

# Test different load levels
# Light load: 10 req/s
hey -z 5m -q 10 http://$(kubectl get svc php-apache -o jsonpath='{.spec.clusterIP}')

# Medium load: 50 req/s
hey -z 5m -q 50 http://$(kubectl get svc php-apache -o jsonpath='{.spec.clusterIP}')

# Heavy load: 200 req/s
hey -z 5m -q 200 http://$(kubectl get svc php-apache -o jsonpath='{.spec.clusterIP}')

# Record CPU usage at each level
kubectl top pods -l app=php-apache
```

### Step 3: Calculate Optimal Thresholds

**Example Data:**

| Load Level | Requests/sec | Avg CPU per Pod | Replicas | CPU % of Request (200m) |
|------------|--------------|-----------------|----------|-------------------------|
| Baseline   | 10           | 50m             | 1        | 25%                     |
| Light      | 50           | 120m            | 1        | 60%                     |
| Medium     | 100          | 180m            | 2        | 90%                     |
| Heavy      | 200          | 160m            | 3        | 80%                     |

**Analysis:**

```
# Current target: 50% CPU utilization (100m of 200m request)

# At 50 req/s:
# - CPU usage: 120m (60%)
# - HPA triggers scale-up to 2 pods
# - New CPU per pod: 60m (30%)
# - System stable

# Conclusion: 50% target is appropriate

# If we used 70% target:
# - At 50 req/s, CPU would be 120m (60% < 70%)
# - No scale-up
# - At 100 req/s, CPU hits 180m (90%)
# - Late scale-up, potential latency spike
```

### Step 4: Recommended Thresholds by Application Type

#### CPU-Bound Applications

```yaml
# Conservative (prioritize availability)
metrics:
- type: Resource
  resource:
    name: cpu
    target:
      type: Utilization
      averageUtilization: 50  # Scale at 50%

# Balanced (cost + performance)
metrics:
- type: Resource
  resource:
    name: cpu
    target:
      type: Utilization
      averageUtilization: 70  # Scale at 70%

# Aggressive (cost-optimized)
metrics:
- type: Resource
  resource:
    name: cpu
    target:
      type: Utilization
      averageUtilization: 80  # Scale at 80%
```

#### Memory-Bound Applications

```yaml
metrics:
- type: Resource
  resource:
    name: memory
    target:
      type: Utilization
      averageUtilization: 75  # Memory typically more stable

# Note: Memory scaling is tricky because:
# 1. Memory doesn't "free up" like CPU
# 2. Pods must be restarted to reduce memory
# 3. Consider VPA for memory optimization
```

#### Latency-Sensitive Applications

```yaml
# Use custom metrics for response time
metrics:
- type: Pods
  pods:
    metric:
      name: http_request_duration_p99_seconds
    target:
      type: AverageValue
      averageValue: "0.2"  # 200ms P99 latency

# Or request rate
- type: Pods
  pods:
    metric:
      name: http_requests_per_second
    target:
      type: AverageValue
      averageValue: "100"  # 100 req/s per pod
```

### Step 5: Tuning Scaling Behavior

#### Fast-Scaling Workloads (E-commerce, APIs)

```yaml
behavior:
  scaleUp:
    stabilizationWindowSeconds: 0    # Immediate
    policies:
    - type: Percent
      value: 100                      # Double capacity
      periodSeconds: 15               # Every 15s
    selectPolicy: Max

  scaleDown:
    stabilizationWindowSeconds: 300  # 5 minutes
    policies:
    - type: Percent
      value: 25                       # Max 25% reduction
      periodSeconds: 60
    selectPolicy: Min
```

#### Batch Processing Workloads

```yaml
behavior:
  scaleUp:
    stabilizationWindowSeconds: 60   # Wait 1 min
    policies:
    - type: Pods
      value: 2                        # Add 2 pods at a time
      periodSeconds: 60
    selectPolicy: Max

  scaleDown:
    stabilizationWindowSeconds: 600  # 10 minutes
    policies:
    - type: Pods
      value: 1                        # Remove 1 pod at a time
      periodSeconds: 120              # Every 2 minutes
    selectPolicy: Min
```

### Step 6: Continuous Optimization

Create a monitoring query dashboard:

```promql
# 1. Average CPU utilization over time
avg(rate(container_cpu_usage_seconds_total{pod=~"php-apache.*"}[5m]))
  /
avg(kube_pod_container_resource_requests{pod=~"php-apache.*",resource="cpu"})

# 2. HPA scaling frequency
changes(kube_horizontalpodautoscaler_status_current_replicas[1h])

# 3. Time in different replica counts
count_over_time(kube_horizontalpodautoscaler_status_current_replicas[24h])

# 4. Cost per request (estimate)
(
  sum(kube_pod_container_resource_requests{pod=~"php-apache.*",resource="cpu"}) * 0.04
)
/
sum(rate(http_requests_total{pod=~"php-apache.*"}[5m]))
```

## Part 7: Testing the Complete Setup

### Scenario 1: Normal Traffic Pattern

```bash
# Generate steady load
kubectl run load-test-normal --image=busybox:1.36 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://php-apache; sleep 0.05; done"

# Monitor in Grafana
# - HPA dashboard shows gradual scale-up
# - CPU stays around target (50%)
# - No alerts triggered
# - Replicas: 1 → 2 → 3 (stabilizes)

# Clean up
kubectl delete pod load-test-normal
```

### Scenario 2: Traffic Spike

```bash
# Generate sudden spike
for i in {1..10}; do
  kubectl run load-spike-$i --image=busybox:1.36 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://php-apache; done" &
done

# Expected behavior:
# T+0s:   Spike detected
# T+30s:  HPA scales to 5 replicas
# T+60s:  HPA scales to 8 replicas
# T+90s:  Stable at 8 replicas

# Alerts triggered:
# - HPAMaxedOut (if hits 10 replicas)
# - HighCPUUsageBeforeScaling

# Stop spike
kubectl delete pod -l run=load-spike
```

### Scenario 3: Cluster Capacity Test

```bash
# Scale up beyond cluster capacity
kubectl scale deployment php-apache --replicas=20

# Expected:
# - Pods go to Pending state
# - PodsPendingScheduling alert fires
# - ClusterCPUPressure alert fires (if no Cluster Autoscaler)
# - Cluster Autoscaler adds nodes (if enabled)

# Check pending pods
kubectl get pods | grep Pending

# Scale back down
kubectl scale deployment php-apache --replicas=2
```

## Part 8: Cleanup

### Remove Monitoring Stack

```bash
# Delete PrometheusRules
kubectl delete prometheusrule -n monitoring hpa-alerts

# Delete ServiceMonitor
kubectl delete servicemonitor -n default php-apache-monitor

# Uninstall Prometheus stack
helm uninstall prometheus -n monitoring

# Or via CDK (remove from stack and redeploy)
# Comment out Prometheus Helm chart in CDK code
cdk deploy

# Delete monitoring namespace
kubectl delete namespace monitoring
```

## Key Takeaways

### Monitoring Checklist

✅ **Metrics Collection**
- [ ] Metrics Server installed and healthy
- [ ] Node Exporter running on all nodes
- [ ] kube-state-metrics deployed
- [ ] Application metrics exposed (if using custom metrics)

✅ **Storage & Retention**
- [ ] Prometheus storage configured (50GB recommended)
- [ ] Retention period set (30 days minimum)
- [ ] Grafana dashboards backed up

✅ **Alerting**
- [ ] PrometheusRules deployed and active
- [ ] AlertManager configured with notification channels
- [ ] Alert routing rules tested
- [ ] Runbooks documented

✅ **Dashboards**
- [ ] HPA overview dashboard imported
- [ ] Resource utilization dashboard configured
- [ ] Cluster health dashboard available
- [ ] Application-specific dashboards created

✅ **Threshold Tuning**
- [ ] Baseline metrics collected
- [ ] Load testing performed
- [ ] Thresholds calculated and documented
- [ ] Scaling behavior tuned for workload type

### Recommended Alert Thresholds

| Alert | Threshold | Rationale |
|-------|-----------|-----------|
| **HPAMaxedOut** | 95% of maxReplicas for 5 min | Early warning before hitting limit |
| **HighCPUUsage** | >90% of requests for 3 min | Indicates scaling may be delayed |
| **HighMemoryUsage** | >90% of limits for 5 min | Prevent OOMKills |
| **PodsPending** | Any pods pending for 10 min | Capacity issue |
| **ClusterCPUPressure** | <2 cores available | Proactive capacity planning |
| **HPAScalingThrashing** | >0.5 changes/min for 30 min | Configuration issue |

### Cost Optimization via Monitoring

```bash
# Query to identify over-provisioned resources
# (Requested but not used)

# CPU waste
sum(kube_pod_container_resource_requests{resource="cpu"})
-
sum(rate(container_cpu_usage_seconds_total[1d]))

# Memory waste
sum(kube_pod_container_resource_requests{resource="memory"})
-
sum(container_memory_working_set_bytes)

# Right-sizing recommendation:
# Set requests to P95 usage + 20% buffer
```

## Related Topics

### Autoscaling Series
- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Theory and approaches
- **[Part 2: Cluster Autoscaling](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Node-level autoscaling
- **[Part 3: Hands-On HPA Demo](./kubernetes-autoscaling-complete-guide-part3-hands-on-hpa-demo.md)** - Implementation guide

### Kubernetes Monitoring
- **[Kubernetes Complete Guide (Part 3): Advanced Features](./kubernetes-complete-guide-part3-advanced-zh.md)** - Includes monitoring setup (Traditional Chinese)
- **[Building Production Kubernetes Platform on AWS EKS](./building-production-kubernetes-platform-aws-eks-cdk.md)** - Production observability patterns

## Conclusion

This guide established production-grade monitoring for Kubernetes autoscaling:

1. **Metrics Collection**: Deployed complete Prometheus stack with exporters
2. **Visualization**: Created Grafana dashboards for real-time visibility
3. **Alerting**: Configured AlertManager with multi-channel notifications
4. **Threshold Tuning**: Established data-driven approach to optimization
5. **Testing**: Validated monitoring under various load scenarios

### Implementation Checklist

**Week 1: Foundation**
- [ ] Deploy Prometheus stack
- [ ] Configure basic dashboards
- [ ] Verify metrics collection

**Week 2: Alerting**
- [ ] Create PrometheusRules
- [ ] Configure notification channels
- [ ] Test alert routing

**Week 3: Optimization**
- [ ] Collect baseline metrics
- [ ] Perform load testing
- [ ] Tune HPA thresholds

**Week 4: Production**
- [ ] Document runbooks
- [ ] Train team on dashboards
- [ ] Establish review cadence

### Next Steps

1. **Integrate with CI/CD**: Automatic threshold updates based on load tests
2. **Add Custom Metrics**: Application-specific business metrics
3. **Implement SLOs**: Service Level Objectives with error budgets
4. **Cost Optimization**: Continuous right-sizing based on actual usage
5. **ML-Based Autoscaling**: Predictive scaling using historical patterns

With comprehensive monitoring in place, you can confidently operate Kubernetes autoscaling in production, quickly identify issues, and continuously optimize for performance and cost.

Happy monitoring! 📊
