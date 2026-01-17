---
title: "Building Centralized Grafana + Prometheus Monitoring with AWS CDK: Multi-Service Observability Platform"
date: 2026-01-17T11:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "architecture"]
tags: ["prometheus", "grafana", "aws", "cdk", "monitoring", "observability", "metrics", "ecs", "kubernetes", "eks", "fargate", "alerting"]
summary: "Comprehensive guide to architecting a production-ready centralized Prometheus + Grafana monitoring platform using AWS CDK that aggregates metrics from multiple services, clusters, and infrastructure components with federation, remote storage, and advanced alerting."
readTime: "23 min"
---

In modern distributed systems running on AWS, monitoring individual services in isolation creates operational blind spots. A centralized Prometheus + Grafana platform provides unified visibility across all infrastructure, enabling correlation analysis, efficient troubleshooting, and proactive alerting. This post explores building a production-grade monitoring hub using AWS CDK that aggregates metrics from EKS clusters, ECS services, Lambda functions, and custom applications.

## The Challenge: Fragmented Observability

Organizations running microservices across AWS face critical monitoring challenges:

- **Isolated Metrics**: Each service/cluster has its own Prometheus instance, preventing holistic analysis
- **Data Silos**: No centralized view of system-wide performance and health
- **Scaling Complexity**: Managing dozens of Prometheus instances becomes operationally expensive
- **Correlation Difficulty**: Cross-service debugging requires manual metric aggregation
- **Storage Management**: Each Prometheus instance handles its own long-term storage
- **Alerting Chaos**: Duplicate alerts from multiple Prometheus instances
- **Query Performance**: Complex cross-cluster queries are slow or impossible

## Why Centralized Prometheus + Grafana Architecture?

Before diving into implementation, let's understand the architectural benefits:

### **Centralized vs Distributed Monitoring**

```
Traditional Distributed Approach:
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ EKS Cluster  │    │ ECS Service  │    │  Lambda      │
│              │    │              │    │  Functions   │
│ Prometheus   │    │ Prometheus   │    │  CloudWatch  │
│ Grafana      │    │ Grafana      │    │  Metrics     │
└──────────────┘    └──────────────┘    └──────────────┘
      ↓                    ↓                    ↓
   Isolated          No Correlation        Manual Export

Centralized Approach:
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ EKS Cluster  │    │ ECS Service  │    │  Lambda      │
│              │    │              │    │  Functions   │
│ Prometheus   │───►│ Prometheus   │───►│ CloudWatch   │
│ (Scraper)    │    │ (Scraper)    │    │ Exporter     │
└──────────────┘    └──────────────┘    └──────────────┘
      │                    │                    │
      └────────────────────┴────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │  Central Prometheus     │
              │  (Federation/Remote)    │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   Centralized Grafana   │
              │   (Unified Dashboards)  │
              └─────────────────────────┘
```

### **Key Benefits**

| Capability | Distributed | Centralized |
|-----------|------------|-------------|
| **Cross-Service Queries** | Manual aggregation | Native support |
| **Unified Dashboards** | Multiple logins | Single pane of glass |
| **Alert Deduplication** | Complex rules needed | Built-in |
| **Long-term Storage** | Per-instance management | Centralized (Cortex/Thanos) |
| **Operational Overhead** | High (N instances) | Low (1 instance) |
| **Cost Efficiency** | N × infrastructure | Optimized shared resources |

## Architecture Overview: Multi-Tier Monitoring Platform

Our centralized monitoring architecture uses Prometheus federation and remote write to aggregate metrics from distributed sources:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AWS CLOUD                                    │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              METRIC SOURCES (Multi-Account/Region)         │   │
│  │                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐   │   │
│  │  │  EKS Cluster  │  │ ECS Services  │  │   Lambda     │   │   │
│  │  │  us-east-1    │  │  us-west-2    │  │  Functions   │   │   │
│  │  │               │  │               │  │              │   │   │
│  │  │ Prometheus    │  │ Prometheus    │  │ CloudWatch   │   │   │
│  │  │ Server        │  │ Server        │  │ → Exporter   │   │   │
│  │  │ (Scraper)     │  │ (Scraper)     │  │              │   │   │
│  │  └───────┬───────┘  └───────┬───────┘  └──────┬───────┘   │   │
│  │          │                   │                 │           │   │
│  │          │ /federate         │ remote_write    │ /metrics  │   │
│  └──────────┼───────────────────┼─────────────────┼───────────┘   │
│             │                   │                 │               │
│             └───────────────────┴─────────────────┘               │
│                                 │                                 │
│                                 ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │         CENTRALIZED PROMETHEUS (ECS Fargate)                │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │  Prometheus Server (High Availability)               │  │ │
│  │  │                                                       │  │ │
│  │  │  • Federation Endpoint                               │  │ │
│  │  │  • Remote Write Receiver                             │  │ │
│  │  │  • Time Series Database                              │  │ │
│  │  │  • Recording Rules                                   │  │ │
│  │  │  • Alert Manager Integration                         │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  │                           │                                 │ │
│  │  ┌────────────────────────┴────────────────────┐           │ │
│  │  │                                              │           │ │
│  │  ▼                                              ▼           │ │
│  │  ┌──────────────────┐           ┌──────────────────────┐  │ │
│  │  │ EFS Volume       │           │  Alert Manager       │  │ │
│  │  │ (TSDB Storage)   │           │  (ECS Task)          │  │ │
│  │  │                  │           │                      │  │ │
│  │  │ • Long-term data │           │ • Route alerts       │  │ │
│  │  │ • High IOPS      │           │ • Deduplication      │  │ │
│  │  │ • Automatic      │           │ • Grouping           │  │ │
│  │  │   backup         │           │ • Silencing          │  │ │
│  │  └──────────────────┘           └──────────┬───────────┘  │ │
│  └──────────────────────────────────────────────┼────────────┘ │
│                                                 │               │
│                                                 ▼               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           CENTRALIZED GRAFANA (ECS Fargate)                 │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │  Grafana Server (Multi-AZ)                           │  │ │
│  │  │                                                       │  │ │
│  │  │  • Unified Dashboards                                │  │ │
│  │  │  • Multi-Prometheus Data Sources                     │  │ │
│  │  │  • Cross-Cluster Queries                             │  │ │
│  │  │  • Team Dashboards                                   │  │ │
│  │  │  • Alert Visualization                               │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  │                           │                                 │ │
│  │                           ▼                                 │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │  EFS Volume (Grafana Data)                           │  │ │
│  │  │  • Dashboards persistence                            │  │ │
│  │  │  • User settings                                     │  │ │
│  │  │  • Plugins                                           │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              NOTIFICATION CHANNELS                          │ │
│  │                                                              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │ │
│  │  │  Slack   │  │ PagerDuty│  │   Email  │  │  Webhook │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              SUPPORTING SERVICES                            │ │
│  │                                                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │ │
│  │  │     VPC      │  │     ALB      │  │   Route53 DNS    │  │ │
│  │  │  (Multi-AZ)  │  │  (HTTPS)     │  │   (monitoring.)  │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │ │
│  │                                                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │ │
│  │  │   Secrets    │  │   IAM Roles  │  │   CloudWatch     │  │ │
│  │  │   Manager    │  │              │  │   Metrics        │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### **Data Flow Architecture**

```
┌──────────────────────────────────────────────────────────────┐
│ 1. METRIC COLLECTION (Distributed Sources)                  │
│    • Kubernetes pods expose /metrics endpoints               │
│    • Node exporters scrape system metrics                    │
│    • Custom applications export business metrics             │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. LOCAL PROMETHEUS (Per Cluster/Service)                   │
│    • Scrape metrics every 15-30 seconds                      │
│    • Apply initial relabeling rules                          │
│    • Store metrics locally (1-7 days)                        │
│    • Evaluate local alerts                                   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. METRIC AGGREGATION (Federation/Remote Write)             │
│    • Federation: Central pulls from /federate endpoints      │
│    • Remote Write: Local pushes to central receiver          │
│    • Compression and batching for efficiency                 │
│    • Cross-region replication                                │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. CENTRAL PROMETHEUS (ECS Fargate)                         │
│    • Receive and deduplicate metrics                         │
│    • Apply global recording rules                            │
│    • Store in EFS-backed TSDB (30-90 days)                  │
│    • Evaluate global alerts                                  │
│    • Expose unified query API                                │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. VISUALIZATION (Grafana)                                  │
│    • Query central Prometheus                                │
│    • Cross-cluster analysis                                  │
│    • Render unified dashboards                               │
│    • Display alerts and annotations                          │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. ALERTING (Alert Manager)                                 │
│    • Receive alerts from Prometheus                          │
│    • Deduplicate and group alerts                            │
│    • Route to notification channels                          │
│    • Track alert states and silences                         │
└──────────────────────────────────────────────────────────────┘
```

## CDK Implementation: Infrastructure as Code

Let's build the complete monitoring platform using AWS CDK with TypeScript.

### **Project Structure**

```
centralized-monitoring-cdk/
├── bin/
│   └── monitoring-platform.ts          # CDK app entry
├── lib/
│   ├── stacks/
│   │   ├── vpc-stack.ts                # Network infrastructure
│   │   ├── prometheus-stack.ts         # Central Prometheus
│   │   ├── grafana-stack.ts            # Grafana server
│   │   ├── alertmanager-stack.ts       # Alert Manager
│   │   └── exporters-stack.ts          # CloudWatch exporters
│   ├── constructs/
│   │   ├── efs-storage.ts              # EFS for persistence
│   │   ├── alb-setup.ts                # Load balancer
│   │   └── iam-roles.ts                # IAM permissions
│   └── config/
│       ├── prometheus-config.yaml      # Prometheus configuration
│       ├── alertmanager-config.yaml    # Alert Manager config
│       └── recording-rules.yaml        # Prometheus rules
├── grafana/
│   ├── dashboards/
│   │   ├── cluster-overview.json       # Kubernetes dashboard
│   │   ├── ecs-services.json           # ECS metrics
│   │   └── cross-cluster.json          # Multi-cluster view
│   └── provisioning/
│       ├── datasources/                # Prometheus data sources
│       └── dashboards/                 # Dashboard provisioning
├── prometheus/
│   ├── rules/
│   │   ├── recording-rules.yml         # Pre-aggregation rules
│   │   └── alerting-rules.yml          # Alert definitions
│   └── config/
│       └── prometheus.yml              # Main configuration
├── package.json
├── tsconfig.json
└── cdk.json
```

### **Configuration Management**

```typescript
// lib/config/monitoring-config.ts
export interface MonitoringConfig {
  environment: 'dev' | 'staging' | 'production';
  prometheus: PrometheusConfig;
  grafana: GrafanaConfig;
  alertManager: AlertManagerConfig;
  storage: StorageConfig;
  networking: NetworkingConfig;
}

export interface PrometheusConfig {
  retention: string;              // e.g., "30d"
  scrapeInterval: string;         // e.g., "15s"
  evaluationInterval: string;     // e.g., "15s"
  remoteWriteEnabled: boolean;
  federationEnabled: boolean;
  cpu: number;                    // ECS CPU units
  memory: number;                 // ECS memory (MB)
  desiredCount: number;           // Number of tasks
  externalLabels: Record<string, string>;
}

export interface GrafanaConfig {
  adminUser: string;
  domain?: string;
  enableAuth: boolean;
  cpu: number;
  memory: number;
  desiredCount: number;
  plugins: string[];
}

export interface AlertManagerConfig {
  enabled: boolean;
  cpu: number;
  memory: number;
  slackWebhook?: string;
  pagerDutyKey?: string;
  emailFrom?: string;
  emailTo: string[];
}

export interface StorageConfig {
  efsPerformanceMode: 'generalPurpose' | 'maxIO';
  efsThroughputMode: 'bursting' | 'provisioned';
  provisionedThroughputMibps?: number;
  prometheusVolumeSize: number;  // GB
  grafanaVolumeSize: number;     // GB
}

export interface NetworkingConfig {
  vpcCidr: string;
  maxAzs: number;
  enableNatGateway: boolean;
  enableVpcFlowLogs: boolean;
}

export const monitoringConfigs: Record<string, MonitoringConfig> = {
  dev: {
    environment: 'dev',
    prometheus: {
      retention: '7d',
      scrapeInterval: '30s',
      evaluationInterval: '30s',
      remoteWriteEnabled: true,
      federationEnabled: true,
      cpu: 1024,        // 1 vCPU
      memory: 2048,     // 2 GB
      desiredCount: 1,
      externalLabels: {
        cluster: 'central',
        environment: 'dev',
      },
    },
    grafana: {
      adminUser: 'admin',
      enableAuth: true,
      cpu: 512,
      memory: 1024,
      desiredCount: 1,
      plugins: [
        'grafana-piechart-panel',
        'grafana-worldmap-panel',
      ],
    },
    alertManager: {
      enabled: true,
      cpu: 256,
      memory: 512,
      emailTo: ['dev-team@company.com'],
    },
    storage: {
      efsPerformanceMode: 'generalPurpose',
      efsThroughputMode: 'bursting',
      prometheusVolumeSize: 100,
      grafanaVolumeSize: 20,
    },
    networking: {
      vpcCidr: '10.0.0.0/16',
      maxAzs: 2,
      enableNatGateway: true,
      enableVpcFlowLogs: false,
    },
  },
  production: {
    environment: 'production',
    prometheus: {
      retention: '90d',
      scrapeInterval: '15s',
      evaluationInterval: '15s',
      remoteWriteEnabled: true,
      federationEnabled: true,
      cpu: 4096,        // 4 vCPU
      memory: 16384,    // 16 GB
      desiredCount: 3,  // High availability
      externalLabels: {
        cluster: 'central',
        environment: 'production',
      },
    },
    grafana: {
      adminUser: 'admin',
      domain: 'monitoring.company.com',
      enableAuth: true,
      cpu: 2048,
      memory: 4096,
      desiredCount: 2,
      plugins: [
        'grafana-piechart-panel',
        'grafana-worldmap-panel',
        'grafana-clock-panel',
      ],
    },
    alertManager: {
      enabled: true,
      cpu: 1024,
      memory: 2048,
      slackWebhook: process.env.SLACK_WEBHOOK_URL,
      pagerDutyKey: process.env.PAGERDUTY_INTEGRATION_KEY,
      emailFrom: 'alerts@company.com',
      emailTo: [
        'oncall@company.com',
        'sre-team@company.com',
      ],
    },
    storage: {
      efsPerformanceMode: 'maxIO',
      efsThroughputMode: 'provisioned',
      provisionedThroughputMibps: 100,
      prometheusVolumeSize: 1000,
      grafanaVolumeSize: 100,
    },
    networking: {
      vpcCidr: '10.0.0.0/16',
      maxAzs: 3,
      enableNatGateway: true,
      enableVpcFlowLogs: true,
    },
  },
};
```

### **VPC Stack - Network Foundation**

```typescript
// lib/stacks/vpc-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';
import { NetworkingConfig } from '../config/monitoring-config';

export interface VpcStackProps extends cdk.StackProps {
  config: NetworkingConfig;
}

export class VpcStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly prometheusSecurityGroup: ec2.SecurityGroup;
  public readonly grafanaSecurityGroup: ec2.SecurityGroup;
  public readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: VpcStackProps) {
    super(scope, id, props);

    const { config } = props;

    // Create VPC with public and private subnets
    this.vpc = new ec2.Vpc(this, 'MonitoringVpc', {
      ipAddresses: ec2.IpAddresses.cidr(config.vpcCidr),
      maxAzs: config.maxAzs,
      natGateways: config.enableNatGateway ? config.maxAzs : 0,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
        {
          name: 'Isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // Enable VPC Flow Logs if configured
    if (config.enableVpcFlowLogs) {
      this.vpc.addFlowLog('VpcFlowLogs', {
        destination: ec2.FlowLogDestination.toCloudWatchLogs(),
      });
    }

    // Security group for ALB
    this.albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for monitoring ALB',
      allowAllOutbound: true,
    });

    // Allow HTTPS from anywhere
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS from internet'
    );

    // Security group for Prometheus
    this.prometheusSecurityGroup = new ec2.SecurityGroup(
      this,
      'PrometheusSecurityGroup',
      {
        vpc: this.vpc,
        description: 'Security group for Prometheus',
        allowAllOutbound: true,
      }
    );

    // Allow Prometheus port from ALB and internal VPC
    this.prometheusSecurityGroup.addIngressRule(
      this.albSecurityGroup,
      ec2.Port.tcp(9090),
      'Allow Prometheus access from ALB'
    );

    this.prometheusSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(config.vpcCidr),
      ec2.Port.tcp(9090),
      'Allow Prometheus federation from VPC'
    );

    // Security group for Grafana
    this.grafanaSecurityGroup = new ec2.SecurityGroup(
      this,
      'GrafanaSecurityGroup',
      {
        vpc: this.vpc,
        description: 'Security group for Grafana',
        allowAllOutbound: true,
      }
    );

    // Allow Grafana port from ALB
    this.grafanaSecurityGroup.addIngressRule(
      this.albSecurityGroup,
      ec2.Port.tcp(3000),
      'Allow Grafana access from ALB'
    );

    // Allow Grafana to access Prometheus
    this.prometheusSecurityGroup.connections.allowFrom(
      this.grafanaSecurityGroup,
      ec2.Port.tcp(9090),
      'Allow Grafana to query Prometheus'
    );

    // Outputs
    new cdk.CfnOutput(this, 'VpcId', {
      value: this.vpc.vpcId,
      exportName: 'MonitoringVpcId',
    });

    new cdk.CfnOutput(this, 'VpcCidr', {
      value: this.vpc.vpcCidrBlock,
      exportName: 'MonitoringVpcCidr',
    });
  }
}
```

### **Prometheus Stack - Central Metrics Server**

```typescript
// lib/stacks/prometheus-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';
import { PrometheusConfig, StorageConfig } from '../config/monitoring-config';
import * as path from 'path';
import * as fs from 'fs';

export interface PrometheusStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  securityGroup: ec2.SecurityGroup;
  prometheusConfig: PrometheusConfig;
  storageConfig: StorageConfig;
  alb: elbv2.ApplicationLoadBalancer;
}

export class PrometheusStack extends cdk.Stack {
  public readonly service: ecs_patterns.ApplicationLoadBalancedFargateService;
  public readonly fileSystem: efs.FileSystem;
  public readonly prometheusUrl: string;

  constructor(scope: Construct, id: string, props: PrometheusStackProps) {
    super(scope, id, props);

    const { vpc, securityGroup, prometheusConfig, storageConfig, alb } = props;

    // Create ECS Cluster
    const cluster = new ecs.Cluster(this, 'PrometheusCluster', {
      vpc,
      clusterName: 'monitoring-prometheus-cluster',
      containerInsights: true,
    });

    // Create EFS for Prometheus data persistence
    this.fileSystem = new efs.FileSystem(this, 'PrometheusEfs', {
      vpc,
      encrypted: true,
      lifecyclePolicy: efs.LifecyclePolicy.AFTER_14_DAYS,
      performanceMode: storageConfig.efsPerformanceMode === 'maxIO'
        ? efs.PerformanceMode.MAX_IO
        : efs.PerformanceMode.GENERAL_PURPOSE,
      throughputMode: storageConfig.efsThroughputMode === 'provisioned'
        ? efs.ThroughputMode.PROVISIONED
        : efs.ThroughputMode.BURSTING,
      provisionedThroughputPerSecond: storageConfig.provisionedThroughputMibps
        ? cdk.Size.mebibytes(storageConfig.provisionedThroughputMibps)
        : undefined,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Create access point for Prometheus
    const accessPoint = this.fileSystem.addAccessPoint('PrometheusAccessPoint', {
      path: '/prometheus',
      createAcl: {
        ownerGid: '65534',
        ownerUid: '65534',
        permissions: '755',
      },
      posixUser: {
        gid: '65534',
        uid: '65534',
      },
    });

    // Create task definition
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'PrometheusTask', {
      cpu: prometheusConfig.cpu,
      memoryLimitMiB: prometheusConfig.memory,
      family: 'prometheus-server',
    });

    // Add EFS volume
    const volumeName = 'prometheus-storage';
    taskDefinition.addVolume({
      name: volumeName,
      efsVolumeConfiguration: {
        fileSystemId: this.fileSystem.fileSystemId,
        transitEncryption: 'ENABLED',
        authorizationConfig: {
          accessPointId: accessPoint.accessPointId,
          iam: 'ENABLED',
        },
      },
    });

    // Load Prometheus configuration from file
    const prometheusConfigYaml = this.loadPrometheusConfig(prometheusConfig);

    // Add Prometheus container
    const prometheusContainer = taskDefinition.addContainer('prometheus', {
      image: ecs.ContainerImage.fromRegistry('prom/prometheus:latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'prometheus',
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        PROMETHEUS_RETENTION: prometheusConfig.retention,
      },
      command: [
        '--config.file=/etc/prometheus/prometheus.yml',
        '--storage.tsdb.path=/prometheus',
        `--storage.tsdb.retention.time=${prometheusConfig.retention}`,
        '--web.console.libraries=/usr/share/prometheus/console_libraries',
        '--web.console.templates=/usr/share/prometheus/consoles',
        '--web.enable-lifecycle',
        '--web.enable-admin-api',
      ],
      portMappings: [{
        containerPort: 9090,
        protocol: ecs.Protocol.TCP,
      }],
      healthCheck: {
        command: ['CMD-SHELL', 'wget --no-verbose --tries=1 --spider http://localhost:9090/-/healthy || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // Mount EFS volume
    prometheusContainer.addMountPoints({
      sourceVolume: volumeName,
      containerPath: '/prometheus',
      readOnly: false,
    });

    // Grant EFS permissions
    this.fileSystem.grantReadWrite(taskDefinition.taskRole);

    // Create Fargate service
    this.service = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this,
      'PrometheusService',
      {
        cluster,
        serviceName: 'prometheus',
        taskDefinition,
        desiredCount: prometheusConfig.desiredCount,
        loadBalancer: alb,
        publicLoadBalancer: false,
        securityGroups: [securityGroup],
        taskSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      }
    );

    // Configure health check
    this.service.targetGroup.configureHealthCheck({
      path: '/-/healthy',
      interval: cdk.Duration.seconds(30),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    // Auto scaling
    const scaling = this.service.service.autoScaleTaskCount({
      minCapacity: prometheusConfig.desiredCount,
      maxCapacity: prometheusConfig.desiredCount * 2,
    });

    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    scaling.scaleOnMemoryUtilization('MemoryScaling', {
      targetUtilizationPercent: 80,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Allow EFS connections
    this.fileSystem.connections.allowDefaultPortFrom(this.service.service.connections);

    this.prometheusUrl = `http://${this.service.loadBalancer.loadBalancerDnsName}`;

    // Outputs
    new cdk.CfnOutput(this, 'PrometheusUrl', {
      value: this.prometheusUrl,
      description: 'Prometheus Server URL',
      exportName: 'PrometheusUrl',
    });

    new cdk.CfnOutput(this, 'PrometheusEfsId', {
      value: this.fileSystem.fileSystemId,
      description: 'Prometheus EFS File System ID',
      exportName: 'PrometheusEfsId',
    });
  }

  private loadPrometheusConfig(config: PrometheusConfig): string {
    // Generate Prometheus configuration dynamically
    const prometheusConfig = {
      global: {
        scrape_interval: config.scrapeInterval,
        evaluation_interval: config.evaluationInterval,
        external_labels: config.externalLabels,
      },
      scrape_configs: [
        {
          job_name: 'prometheus',
          static_configs: [{
            targets: ['localhost:9090'],
          }],
        },
        // Federation from remote Prometheus instances
        ...(config.federationEnabled ? [{
          job_name: 'federate-eks-clusters',
          scrape_interval: '30s',
          honor_labels: true,
          metrics_path: '/federate',
          params: {
            'match[]': [
              '{job="kubernetes-apiservers"}',
              '{job="kubernetes-nodes"}',
              '{job="kubernetes-pods"}',
              '{job="kubernetes-cadvisor"}',
              '{job="kubernetes-service-endpoints"}',
            ],
          },
          static_configs: [
            // Add your EKS Prometheus endpoints here
            // { targets: ['prometheus.eks-cluster-1.internal:9090'] },
            // { targets: ['prometheus.eks-cluster-2.internal:9090'] },
          ],
        }] : []),
      ],
      remote_write: config.remoteWriteEnabled ? [
        // Configure remote write endpoints if needed
        // { url: 'http://cortex:9009/api/prom/push' }
      ] : [],
      rule_files: [
        '/etc/prometheus/recording-rules.yml',
        '/etc/prometheus/alerting-rules.yml',
      ],
    };

    return JSON.stringify(prometheusConfig, null, 2);
  }
}
```

### **Grafana Stack - Visualization Platform**

```typescript
// lib/stacks/grafana-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import { Construct } from 'constructs';
import { GrafanaConfig, StorageConfig } from '../config/monitoring-config';

export interface GrafanaStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  securityGroup: ec2.SecurityGroup;
  grafanaConfig: GrafanaConfig;
  storageConfig: StorageConfig;
  prometheusUrl: string;
  alb: elbv2.ApplicationLoadBalancer;
}

export class GrafanaStack extends cdk.Stack {
  public readonly service: ecs_patterns.ApplicationLoadBalancedFargateService;
  public readonly grafanaUrl: string;

  constructor(scope: Construct, id: string, props: GrafanaStackProps) {
    super(scope, id, props);

    const { vpc, securityGroup, grafanaConfig, storageConfig, prometheusUrl, alb } = props;

    // Create ECS Cluster
    const cluster = new ecs.Cluster(this, 'GrafanaCluster', {
      vpc,
      clusterName: 'monitoring-grafana-cluster',
      containerInsights: true,
    });

    // Create EFS for Grafana data
    const fileSystem = new efs.FileSystem(this, 'GrafanaEfs', {
      vpc,
      encrypted: true,
      performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
      throughputMode: efs.ThroughputMode.BURSTING,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const accessPoint = fileSystem.addAccessPoint('GrafanaAccessPoint', {
      path: '/grafana',
      createAcl: {
        ownerGid: '472',
        ownerUid: '472',
        permissions: '755',
      },
      posixUser: {
        gid: '472',
        uid: '472',
      },
    });

    // Create admin password secret
    const adminSecret = new secretsmanager.Secret(this, 'GrafanaAdminPassword', {
      secretName: 'grafana-admin-credentials',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: grafanaConfig.adminUser }),
        generateStringKey: 'password',
        excludePunctuation: true,
        passwordLength: 16,
      },
    });

    // Task definition
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'GrafanaTask', {
      cpu: grafanaConfig.cpu,
      memoryLimitMiB: grafanaConfig.memory,
      family: 'grafana-server',
    });

    // Add volume
    const volumeName = 'grafana-storage';
    taskDefinition.addVolume({
      name: volumeName,
      efsVolumeConfiguration: {
        fileSystemId: fileSystem.fileSystemId,
        transitEncryption: 'ENABLED',
        authorizationConfig: {
          accessPointId: accessPoint.accessPointId,
          iam: 'ENABLED',
        },
      },
    });

    // Grafana container
    const grafanaContainer = taskDefinition.addContainer('grafana', {
      image: ecs.ContainerImage.fromRegistry('grafana/grafana:latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'grafana',
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        GF_SERVER_ROOT_URL: grafanaConfig.domain
          ? `https://${grafanaConfig.domain}`
          : '',
        GF_SECURITY_ADMIN_USER: grafanaConfig.adminUser,
        GF_INSTALL_PLUGINS: grafanaConfig.plugins.join(','),
        GF_AUTH_ANONYMOUS_ENABLED: (!grafanaConfig.enableAuth).toString(),
        GF_PATHS_DATA: '/var/lib/grafana',
        GF_PATHS_PROVISIONING: '/etc/grafana/provisioning',
      },
      secrets: {
        GF_SECURITY_ADMIN_PASSWORD: ecs.Secret.fromSecretsManager(adminSecret, 'password'),
      },
      portMappings: [{
        containerPort: 3000,
        protocol: ecs.Protocol.TCP,
      }],
      healthCheck: {
        command: ['CMD-SHELL', 'wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // Mount EFS
    grafanaContainer.addMountPoints({
      sourceVolume: volumeName,
      containerPath: '/var/lib/grafana',
      readOnly: false,
    });

    // Grant EFS permissions
    fileSystem.grantReadWrite(taskDefinition.taskRole);

    // Create service
    this.service = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this,
      'GrafanaService',
      {
        cluster,
        serviceName: 'grafana',
        taskDefinition,
        desiredCount: grafanaConfig.desiredCount,
        loadBalancer: alb,
        publicLoadBalancer: true,
        securityGroups: [securityGroup],
        taskSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      }
    );

    // Health check
    this.service.targetGroup.configureHealthCheck({
      path: '/api/health',
      interval: cdk.Duration.seconds(30),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    // Auto scaling
    const scaling = this.service.service.autoScaleTaskCount({
      minCapacity: grafanaConfig.desiredCount,
      maxCapacity: grafanaConfig.desiredCount * 2,
    });

    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
    });

    // Allow EFS connections
    fileSystem.connections.allowDefaultPortFrom(this.service.service.connections);

    this.grafanaUrl = `http://${this.service.loadBalancer.loadBalancerDnsName}`;

    // Outputs
    new cdk.CfnOutput(this, 'GrafanaUrl', {
      value: this.grafanaUrl,
      description: 'Grafana Dashboard URL',
      exportName: 'GrafanaUrl',
    });

    new cdk.CfnOutput(this, 'GrafanaAdminSecretArn', {
      value: adminSecret.secretArn,
      description: 'Grafana Admin Password Secret ARN',
      exportName: 'GrafanaAdminSecretArn',
    });
  }
}
```

## Prometheus Configuration Files

### **Main Prometheus Configuration**

```yaml
# prometheus/config/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'central'
    environment: 'production'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load rules
rule_files:
  - '/etc/prometheus/recording-rules.yml'
  - '/etc/prometheus/alerting-rules.yml'

# Scrape configurations
scrape_configs:
  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Federation from EKS clusters
  - job_name: 'federate-eks-us-east-1'
    scrape_interval: 30s
    honor_labels: true
    metrics_path: '/federate'
    params:
      'match[]':
        - '{job=~"kubernetes-.*"}'
        - '{__name__=~"container_.*"}'
        - '{__name__=~"node_.*"}'
    static_configs:
      - targets:
          - 'prometheus.eks-us-east-1.internal:9090'
        labels:
          cluster: 'eks-us-east-1'
          region: 'us-east-1'

  - job_name: 'federate-eks-us-west-2'
    scrape_interval: 30s
    honor_labels: true
    metrics_path: '/federate'
    params:
      'match[]':
        - '{job=~"kubernetes-.*"}'
        - '{__name__=~"container_.*"}'
        - '{__name__=~"node_.*"}'
    static_configs:
      - targets:
          - 'prometheus.eks-us-west-2.internal:9090'
        labels:
          cluster: 'eks-us-west-2'
          region: 'us-west-2'

  # ECS Service Discovery
  - job_name: 'ecs-services'
    ec2_sd_configs:
      - region: us-east-1
        port: 9090
        filters:
          - name: tag:monitoring
            values: ['prometheus']
    relabel_configs:
      - source_labels: [__meta_ec2_tag_Name]
        target_label: instance
      - source_labels: [__meta_ec2_tag_Service]
        target_label: service

  # CloudWatch Exporter
  - job_name: 'cloudwatch'
    static_configs:
      - targets:
          - 'cloudwatch-exporter:9106'

# Remote write (optional - for long-term storage)
remote_write:
  - url: http://cortex:9009/api/prom/push
    queue_config:
      capacity: 10000
      max_shards: 200
      max_samples_per_send: 1000
```

### **Recording Rules**

```yaml
# prometheus/rules/recording-rules.yml
groups:
  - name: aggregation_rules
    interval: 30s
    rules:
      # Aggregate CPU usage by cluster
      - record: cluster:cpu_usage:rate5m
        expr: sum(rate(container_cpu_usage_seconds_total[5m])) by (cluster)

      # Aggregate memory usage by cluster
      - record: cluster:memory_usage_bytes:sum
        expr: sum(container_memory_usage_bytes) by (cluster)

      # Aggregate request rate by service
      - record: service:http_requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (service, cluster)

      # Aggregate error rate by service
      - record: service:http_errors:rate5m
        expr: sum(rate(http_requests_total{status=~"5.."}[5m])) by (service, cluster)

      # P95 latency by service
      - record: service:http_request_duration_p95:5m
        expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le))

  - name: kubernetes_aggregations
    interval: 30s
    rules:
      # Pod count by namespace and cluster
      - record: namespace:pod_count:sum
        expr: sum(kube_pod_info) by (namespace, cluster)

      # Node capacity by cluster
      - record: cluster:node_capacity_cpu_cores:sum
        expr: sum(kube_node_status_capacity{resource="cpu"}) by (cluster)

      # Node available memory by cluster
      - record: cluster:node_available_memory_bytes:sum
        expr: sum(kube_node_status_allocatable{resource="memory"}) by (cluster)
```

### **Alerting Rules**

```yaml
# prometheus/rules/alerting-rules.yml
groups:
  - name: infrastructure_alerts
    interval: 30s
    rules:
      # High CPU usage across cluster
      - alert: HighClusterCPUUsage
        expr: cluster:cpu_usage:rate5m > 0.8
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "High CPU usage in cluster {{ $labels.cluster }}"
          description: "CPU usage is {{ $value | humanizePercentage }} in cluster {{ $labels.cluster }}"

      # Low available memory
      - alert: LowClusterMemory
        expr: cluster:node_available_memory_bytes:sum < 1073741824
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Low available memory in cluster {{ $labels.cluster }}"
          description: "Only {{ $value | humanize1024 }} available in cluster {{ $labels.cluster }}"

      # Pod crash looping
      - alert: PodCrashLooping
        expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Pod {{ $labels.namespace }}/{{ $labels.pod }} is crash looping"
          description: "Pod has restarted {{ $value }} times in the last 15 minutes"

  - name: application_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: service:http_errors:rate5m / service:http_requests:rate5m > 0.05
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate in {{ $labels.service }}"
          description: "Error rate is {{ $value | humanizePercentage }} in {{ $labels.service }}"

      # High latency
      - alert: HighLatency
        expr: service:http_request_duration_p95:5m > 1
        for: 10m
        labels:
          severity: warning
          team: backend
        annotations:
          summary: "High P95 latency in {{ $labels.service }}"
          description: "P95 latency is {{ $value }}s in {{ $labels.service }}"

      # Service down
      - alert: ServiceDown
        expr: up{job=~".*"} == 0
        for: 2m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Service {{ $labels.job }} is down"
          description: "Service {{ $labels.job }} in cluster {{ $labels.cluster }} is unreachable"
```

## Grafana Dashboard Provisioning

### **Prometheus Data Source Configuration**

```yaml
# grafana/provisioning/datasources/prometheus.yaml
apiVersion: 1

datasources:
  - name: Central Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s
      queryTimeout: 60s
      httpMethod: POST

  - name: EKS US-East-1
    type: prometheus
    access: proxy
    url: http://prometheus.eks-us-east-1.internal:9090
    editable: false
    jsonData:
      timeInterval: 15s

  - name: EKS US-West-2
    type: prometheus
    access: proxy
    url: http://prometheus.eks-us-west-2.internal:9090
    editable: false
    jsonData:
      timeInterval: 15s
```

### **Dashboard Provisioning**

```yaml
# grafana/provisioning/dashboards/default.yaml
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: true
```

### **Cross-Cluster Dashboard Example**

```json
// grafana/dashboards/cross-cluster.json
{
  "dashboard": {
    "title": "Cross-Cluster Overview",
    "tags": ["kubernetes", "cross-cluster"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "CPU Usage by Cluster",
        "type": "graph",
        "datasource": "Central Prometheus",
        "targets": [
          {
            "expr": "cluster:cpu_usage:rate5m",
            "legendFormat": "{{ cluster }}",
            "refId": "A"
          }
        ],
        "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 }
      },
      {
        "id": 2,
        "title": "Memory Usage by Cluster",
        "type": "graph",
        "datasource": "Central Prometheus",
        "targets": [
          {
            "expr": "cluster:memory_usage_bytes:sum",
            "legendFormat": "{{ cluster }}",
            "refId": "A"
          }
        ],
        "gridPos": { "x": 12, "y": 0, "w": 12, "h": 8 }
      },
      {
        "id": 3,
        "title": "Request Rate by Service (All Clusters)",
        "type": "graph",
        "datasource": "Central Prometheus",
        "targets": [
          {
            "expr": "sum(service:http_requests:rate5m) by (service)",
            "legendFormat": "{{ service }}",
            "refId": "A"
          }
        ],
        "gridPos": { "x": 0, "y": 8, "w": 24, "h": 8 }
      },
      {
        "id": 4,
        "title": "Error Rate Comparison",
        "type": "heatmap",
        "datasource": "Central Prometheus",
        "targets": [
          {
            "expr": "service:http_errors:rate5m / service:http_requests:rate5m",
            "legendFormat": "{{ service }} @ {{ cluster }}",
            "refId": "A"
          }
        ],
        "gridPos": { "x": 0, "y": 16, "w": 24, "h": 8 }
      }
    ]
  }
}
```

## Deployment and Operations

### **Deploy the Complete Stack**

```bash
# Set environment
export AWS_REGION=us-east-1
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# Install dependencies
npm install

# Bootstrap CDK (first time only)
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$AWS_REGION

# Deploy VPC stack first
cdk deploy MonitoringVpcStack --context env=production

# Deploy Prometheus
cdk deploy PrometheusStack --context env=production

# Deploy Grafana
cdk deploy GrafanaStack --context env=production

# Deploy all stacks
cdk deploy --all --context env=production --require-approval never

# Get deployment outputs
aws cloudformation describe-stacks \
  --stack-name GrafanaStack \
  --query 'Stacks[0].Outputs' \
  --output table
```

### **Configure Remote Prometheus Instances**

On each remote Prometheus (EKS, ECS), configure remote write:

```yaml
# Remote Prometheus configuration
remote_write:
  - url: http://<central-prometheus-alb-dns>:9090/api/v1/write
    queue_config:
      capacity: 10000
      max_shards: 100
      max_samples_per_send: 500
    write_relabel_configs:
      - source_labels: [__name__]
        regex: 'up|container_.*|node_.*|kube_.*'
        action: keep
```

### **Verify Federation**

```bash
# Test federation endpoint
curl 'http://<central-prometheus>/federate?match[]={job="kubernetes-nodes"}'

# Check ingested metrics
curl 'http://<central-prometheus>/api/v1/query?query=up'

# Verify remote write
curl 'http://<central-prometheus>/api/v1/query?query=prometheus_remote_storage_samples_total'
```

## Production Best Practices

### **1. High Availability Configuration**

```typescript
// Deploy Prometheus with multiple replicas
prometheusConfig: {
  desiredCount: 3,  // 3 instances for HA
  // Use consistent hashing for federation
}

// Use EFS for shared storage
storageConfig: {
  efsPerformanceMode: 'maxIO',
  efsThroughputMode: 'provisioned',
  provisionedThroughputMibps: 100,
}
```

### **2. Cost Optimization**

| Strategy | Implementation | Savings |
|----------|---------------|---------|
| **Metric Filtering** | Only scrape essential metrics | 40-60% storage |
| **Down-sampling** | Reduce resolution for old data | 30-50% storage |
| **Recording Rules** | Pre-aggregate common queries | 20-40% query cost |
| **Fargate Spot** | Use Spot instances for non-prod | 70% compute cost |

### **3. Security Hardening**

```typescript
// Enable encryption
prometheusSecurityGroup.addIngressRule(
  ec2.Peer.ipv4(vpc.vpcCidrBlock),
  ec2.Port.tcp(9090),
  'Allow only VPC traffic'
);

// Use IAM roles for service accounts
// Implement network policies
// Enable audit logging
```

### **4. Monitoring the Monitoring**

```yaml
# Alert on Prometheus issues
- alert: PrometheusDown
  expr: up{job="prometheus"} == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Prometheus is down"

- alert: PrometheusFederationFailing
  expr: prometheus_remote_storage_samples_failed_total > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Prometheus federation failing"
```

## Conclusion

This centralized Prometheus + Grafana architecture provides enterprise-grade observability for distributed AWS environments. By federating metrics from multiple sources into a unified platform, teams gain:

- **Unified Visibility**: Single dashboard for all infrastructure and applications
- **Efficient Operations**: Centralized management reduces operational overhead
- **Better Correlation**: Cross-service analysis for faster troubleshooting
- **Cost Optimization**: Shared infrastructure reduces total monitoring costs
- **Scalability**: Architecture scales horizontally with workload growth

**Key Takeaways:**

1. **Federation** enables centralized metrics without changing application code
2. **ECS Fargate** provides serverless, scalable infrastructure for Prometheus/Grafana
3. **EFS storage** ensures data persistence and high availability
4. **Recording rules** optimize query performance and reduce storage costs
5. **Multi-tier alerting** prevents alert fatigue and ensures timely responses

The complete implementation is available in the [CDK Playground repository](https://github.com/yennanliu/cdk-playground/tree/main/prometheus-grafana-stack), including full configuration examples, dashboards, and deployment scripts.

---

**Related Posts:**
- [Building Centralized Monitoring System with AWS CloudWatch and Grafana](/centralized-monitoring-system-aws-cloudwatch-grafana-cdk)
- [Building Centralized Logging with OpenSearch and AWS CDK](/building-centralized-logging-opensearch-aws-cdk)
- [Building Production Kubernetes Platform with AWS EKS and CDK](/building-production-kubernetes-platform-aws-eks-cdk)

**Tags:** #prometheus #grafana #aws #cdk #monitoring #observability #kubernetes #eks #ecs #fargate #metrics #alerting #federation
