---
title: "Kubernetes Autoscaling Complete Guide (Part 3): Hands-On HPA Demo with Apache-PHP"
date: 2025-11-09T16:00:00+08:00
draft: false
authors: ["yennj12 team"]
categories: ["all", "engineering", "devops", "kubernetes", "tutorial"]
tags: ["Kubernetes", "K8S", "HPA", "Autoscaling", "AWS", "EKS", "CDK", "TypeScript", "Tutorial", "Demo", "Apache", "PHP", "Load Testing"]
summary: "Part 3 of the Kubernetes Autoscaling series: Hands-on tutorial demonstrating Horizontal Pod Autoscaler with a real Apache-PHP application. Includes complete AWS CDK infrastructure code, Kubernetes manifests, load testing, and step-by-step deployment guide."
readTime: "25 min"
---

## Series Overview

This is **Part 3** of the Kubernetes Autoscaling Complete Guide series:

- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Application-level autoscaling theory and approaches
- **[Part 2: Cluster Autoscaling & Cloud Providers](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Infrastructure-level autoscaling strategies
- **Part 3 (This Post)**: Hands-On HPA Demo - Practical implementation with Apache-PHP application

---

After understanding the theory and strategies of Kubernetes autoscaling in Parts 1 and 2, it's time to get hands-on. This tutorial walks through a complete end-to-end implementation of Horizontal Pod Autoscaler using a simple Apache-PHP application, demonstrating CPU-based autoscaling in action.

We'll provision an EKS cluster using AWS CDK (TypeScript), deploy a sample PHP application with Kubernetes manifests, configure HPA, and observe the autoscaling behavior under load.

## What We'll Build

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEMO ARCHITECTURE                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              AWS Infrastructure (CDK)                    │  │
│  │                                                           │  │
│  │  VPC → EKS Cluster → Managed Node Group                 │  │
│  │   ↓        ↓               ↓                             │  │
│  │  3 AZs   v1.28      t3.medium (1-5 nodes)               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Kubernetes Workload (YAML)                       │  │
│  │                                                           │  │
│  │  Deployment (apache-php) → Service → HPA                │  │
│  │       ↓                        ↓          ↓               │  │
│  │  Initial: 1 pod          ClusterIP    Min: 1, Max: 10   │  │
│  │  Image: k8s.gcr.io/      Port: 80     Target: 50% CPU   │  │
│  │         hpa-example                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Load Testing & Monitoring                   │  │
│  │                                                           │  │
│  │  Load Generator → Observability → Scaling Events        │  │
│  │       ↓                 ↓                ↓                │  │
│  │  BusyBox Pod      kubectl top      HPA Metrics          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

Before starting, ensure you have:

```bash
# Required tools
- AWS CLI v2.x
- Node.js v18+ and npm
- kubectl v1.28+
- AWS CDK v2.x
- Docker (optional, for local testing)

# AWS credentials configured
aws configure

# Verify installations
aws --version
node --version
kubectl version --client
cdk --version
```

## Project Structure

```
hpa-demo/
├── cdk/                          # AWS CDK Infrastructure
│   ├── bin/
│   │   └── eks-hpa-demo.ts      # CDK app entry point
│   ├── lib/
│   │   └── eks-hpa-demo-stack.ts # EKS cluster stack
│   ├── package.json
│   ├── tsconfig.json
│   └── cdk.json
├── k8s/                          # Kubernetes Manifests
│   ├── deployment.yaml          # Apache-PHP deployment
│   ├── service.yaml             # ClusterIP service
│   ├── hpa.yaml                 # HorizontalPodAutoscaler
│   └── load-generator.yaml      # Load testing pod
├── scripts/
│   ├── deploy.sh                # Deployment automation
│   └── cleanup.sh               # Resource cleanup
└── README.md
```

## Part 1: Infrastructure Setup with AWS CDK

### Step 1: Initialize CDK Project

```bash
# Create project directory
mkdir hpa-demo && cd hpa-demo
mkdir cdk && cd cdk

# Initialize CDK project
cdk init app --language=typescript

# Install dependencies
npm install @aws-cdk/aws-eks @aws-cdk/aws-ec2 @aws-cdk/aws-iam
```

### Step 2: Create EKS Stack

Create `lib/eks-hpa-demo-stack.ts`:

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

    // Create VPC for EKS cluster
    const vpc = new ec2.Vpc(this, 'EksHpaVpc', {
      maxAzs: 3,
      natGateways: 1, // Cost optimization: use 1 NAT gateway
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      ],
    });

    // IAM role for EKS cluster
    const clusterRole = new iam.Role(this, 'EksClusterRole', {
      assumedBy: new iam.ServicePrincipal('eks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonEKSClusterPolicy'),
      ],
    });

    // Create EKS cluster
    this.cluster = new eks.Cluster(this, 'EksHpaCluster', {
      version: eks.KubernetesVersion.V1_28,
      clusterName: 'hpa-demo-cluster',
      vpc: vpc,
      defaultCapacity: 0, // We'll add managed node group separately
      role: clusterRole,
      endpointAccess: eks.EndpointAccess.PUBLIC_AND_PRIVATE,

      // Enable cluster logging
      clusterLogging: [
        eks.ClusterLoggingTypes.API,
        eks.ClusterLoggingTypes.AUDIT,
        eks.ClusterLoggingTypes.AUTHENTICATOR,
      ],
    });

    // Add managed node group
    const nodeGroup = this.cluster.addNodegroupCapacity('hpa-demo-nodes', {
      instanceTypes: [
        ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
      ],
      minSize: 1,
      maxSize: 5,
      desiredSize: 2,

      // Use spot instances for cost savings (optional)
      capacityType: eks.CapacityType.ON_DEMAND,

      diskSize: 20,

      // Node labels
      labels: {
        'workload-type': 'general',
        'demo': 'hpa',
      },

      // Enable SSH access (optional)
      // remoteAccess: {
      //   sshKeyName: 'your-key-name',
      // },
    });

    // Install Metrics Server (required for HPA)
    const metricsServerManifest = this.cluster.addManifest('metrics-server', {
      apiVersion: 'v1',
      kind: 'ServiceAccount',
      metadata: {
        name: 'metrics-server',
        namespace: 'kube-system',
        labels: {
          'k8s-app': 'metrics-server',
        },
      },
    });

    // Apply Metrics Server using Helm (alternative approach)
    const metricsServer = this.cluster.addHelmChart('MetricsServer', {
      chart: 'metrics-server',
      repository: 'https://kubernetes-sigs.github.io/metrics-server/',
      namespace: 'kube-system',
      values: {
        args: [
          '--cert-dir=/tmp',
          '--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname',
          '--kubelet-use-node-status-port',
          '--metric-resolution=15s',
        ],
      },
    });

    // Output cluster details
    new cdk.CfnOutput(this, 'ClusterName', {
      value: this.cluster.clusterName,
      description: 'EKS Cluster Name',
    });

    new cdk.CfnOutput(this, 'ClusterArn', {
      value: this.cluster.clusterArn,
      description: 'EKS Cluster ARN',
    });

    new cdk.CfnOutput(this, 'KubectlRole', {
      value: this.cluster.kubectlRole?.roleArn || 'N/A',
      description: 'IAM Role for kubectl access',
    });

    new cdk.CfnOutput(this, 'ConfigCommand', {
      value: `aws eks update-kubeconfig --name ${this.cluster.clusterName} --region ${this.region}`,
      description: 'Command to configure kubectl',
    });

    // Output for accessing cluster
    new cdk.CfnOutput(this, 'NodeGroupName', {
      value: nodeGroup.nodegroupName,
      description: 'EKS Node Group Name',
    });
  }
}
```

### Step 3: CDK App Entry Point

Create `bin/eks-hpa-demo.ts`:

```typescript
#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EksHpaDemoStack } from '../lib/eks-hpa-demo-stack';

const app = new cdk.App();

new EksHpaDemoStack(app, 'EksHpaDemoStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-west-2',
  },
  description: 'EKS cluster for HPA demo with Apache-PHP application',
  tags: {
    Project: 'HPA-Demo',
    Environment: 'Development',
    ManagedBy: 'CDK',
  },
});
```

### Step 4: CDK Configuration

Update `cdk.json`:

```json
{
  "app": "npx ts-node --prefer-ts-exts bin/eks-hpa-demo.ts",
  "watch": {
    "include": [
      "**"
    ],
    "exclude": [
      "README.md",
      "cdk*.json",
      "**/*.d.ts",
      "**/*.js",
      "tsconfig.json",
      "package*.json",
      "yarn.lock",
      "node_modules",
      "test"
    ]
  },
  "context": {
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/core:checkSecretUsage": true,
    "@aws-cdk/core:target-partitions": [
      "aws",
      "aws-cn"
    ],
    "@aws-cdk-containers/ecs-service-extensions:enableDefaultLogDriver": true,
    "@aws-cdk/aws-ec2:uniqueImdsv2TemplateName": true,
    "@aws-cdk/aws-ecs:arnFormatIncludesClusterName": true,
    "@aws-cdk/aws-iam:minimizePolicies": true,
    "@aws-cdk/core:validateSnapshotRemovalPolicy": true,
    "@aws-cdk/aws-codepipeline:crossAccountKeyAliasStackSafeResourceName": true,
    "@aws-cdk/aws-s3:createDefaultLoggingPolicy": true,
    "@aws-cdk/aws-sns-subscriptions:restrictSqsDescryption": true,
    "@aws-cdk/aws-apigateway:disableCloudWatchRole": true,
    "@aws-cdk/core:enablePartitionLiterals": true,
    "@aws-cdk/aws-events:eventsTargetQueueSameAccount": true,
    "@aws-cdk/aws-iam:standardizedServicePrincipals": true,
    "@aws-cdk/aws-ecs:disableExplicitDeploymentControllerForCircuitBreaker": true,
    "@aws-cdk/aws-iam:importedRoleStackSafeDefaultPolicyName": true,
    "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": true,
    "@aws-cdk/aws-route53-patters:useCertificate": true,
    "@aws-cdk/customresources:installLatestAwsSdkDefault": false,
    "@aws-cdk/aws-rds:databaseProxyUniqueResourceName": true,
    "@aws-cdk/aws-codedeploy:removeAlarmsFromDeploymentGroup": true,
    "@aws-cdk/aws-apigateway:authorizerChangeDeploymentLogicalId": true,
    "@aws-cdk/aws-ec2:launchTemplateDefaultUserData": true,
    "@aws-cdk/aws-secretsmanager:useAttachedSecretResourcePolicyForSecretTargetAttachments": true,
    "@aws-cdk/aws-redshift:columnId": true,
    "@aws-cdk/aws-stepfunctions-tasks:enableEmrServicePolicyV2": true,
    "@aws-cdk/aws-ec2:restrictDefaultSecurityGroup": true,
    "@aws-cdk/aws-apigateway:requestValidatorUniqueId": true,
    "@aws-cdk/aws-kms:aliasNameRef": true,
    "@aws-cdk/aws-autoscaling:generateLaunchTemplateInsteadOfLaunchConfig": true,
    "@aws-cdk/core:includePrefixInUniqueNameGeneration": true,
    "@aws-cdk/aws-efs:denyAnonymousAccess": true,
    "@aws-cdk/aws-opensearchservice:enableOpensearchMultiAzWithStandby": true,
    "@aws-cdk/aws-lambda-nodejs:useLatestRuntimeVersion": true,
    "@aws-cdk/aws-efs:mountTargetOrderInsensitiveLogicalId": true,
    "@aws-cdk/aws-rds:auroraClusterChangeScopeOfInstanceParameterGroupWithEachParameters": true,
    "@aws-cdk/aws-appsync:useArnForSourceApiAssociationIdentifier": true,
    "@aws-cdk/aws-rds:preventRenderingDeprecatedCredentials": true,
    "@aws-cdk/aws-codepipeline-actions:useNewDefaultBranchForCodeCommitSource": true,
    "@aws-cdk/aws-cloudwatch-actions:changeLambdaPermissionLogicalIdForLambdaAction": true,
    "@aws-cdk/aws-codepipeline:crossAccountKeysDefaultValueToFalse": true,
    "@aws-cdk/aws-codepipeline:defaultPipelineTypeToV2": true,
    "@aws-cdk/aws-kms:reduceCrossAccountRegionPolicyScope": true,
    "@aws-cdk/aws-eks:nodegroupNameAttribute": true,
    "@aws-cdk/aws-ec2:ebsDefaultGp3Volume": true,
    "@aws-cdk/aws-ecs:removeDefaultDeploymentAlarm": true,
    "@aws-cdk/custom-resources:logApiResponseDataPropertyTrueDefault": false
  }
}
```

### Step 5: Deploy Infrastructure

```bash
# Bootstrap CDK (first time only)
cdk bootstrap

# Review CloudFormation template
cdk synth

# Deploy the stack
cdk deploy

# This will:
# 1. Create VPC with public/private subnets
# 2. Provision EKS cluster (takes ~15 minutes)
# 3. Create managed node group
# 4. Install Metrics Server
# 5. Output kubectl configuration command
```

### Step 6: Configure kubectl

```bash
# Update kubeconfig (use the output from CDK deploy)
aws eks update-kubeconfig --name hpa-demo-cluster --region us-west-2

# Verify cluster access
kubectl get nodes

# Expected output:
# NAME                          STATUS   ROLES    AGE   VERSION
# ip-10-0-1-xxx.ec2.internal    Ready    <none>   5m    v1.28.x
# ip-10-0-2-xxx.ec2.internal    Ready    <none>   5m    v1.28.x

# Verify Metrics Server is running
kubectl get pods -n kube-system | grep metrics-server

# Expected output:
# metrics-server-xxx   1/1     Running   0          5m
```

## Part 2: Application Deployment with Kubernetes YAML

Now let's deploy the Apache-PHP application with HPA configuration.

### Step 1: Create Kubernetes Manifests Directory

```bash
cd ..
mkdir k8s
cd k8s
```

### Step 2: Deployment Manifest

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: php-apache
  namespace: default
  labels:
    app: php-apache
    demo: hpa
spec:
  # Initial replica count (HPA will manage this)
  replicas: 1

  selector:
    matchLabels:
      app: php-apache

  template:
    metadata:
      labels:
        app: php-apache
        demo: hpa
      annotations:
        # Prometheus scraping (optional)
        prometheus.io/scrape: "true"
        prometheus.io/port: "80"
        prometheus.io/path: "/metrics"

    spec:
      containers:
      - name: php-apache
        # Official HPA example image from Kubernetes
        image: registry.k8s.io/hpa-example:latest
        imagePullPolicy: Always

        ports:
        - containerPort: 80
          name: http
          protocol: TCP

        # Resource requests and limits (CRITICAL for HPA)
        resources:
          requests:
            # HPA calculates based on these requests
            cpu: 200m      # 200 millicores = 0.2 CPU
            memory: 128Mi
          limits:
            cpu: 500m      # Max 0.5 CPU
            memory: 256Mi

        # Liveness probe
        livenessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        # Readiness probe
        readinessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3

        # Environment variables (optional)
        env:
        - name: APP_ENV
          value: "production"
        - name: LOG_LEVEL
          value: "info"

      # Termination grace period
      terminationGracePeriodSeconds: 30

      # Security context
      securityContext:
        runAsNonRoot: false  # Apache needs root
        fsGroup: 33          # www-data group
```

### Step 3: Service Manifest

Create `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: php-apache
  namespace: default
  labels:
    app: php-apache
    demo: hpa
spec:
  type: ClusterIP  # Internal service only

  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
    name: http

  selector:
    app: php-apache

  # Session affinity (optional)
  sessionAffinity: None
```

### Step 4: HorizontalPodAutoscaler Manifest

Create `hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache-hpa
  namespace: default
  labels:
    app: php-apache
    demo: hpa
spec:
  # Target deployment
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache

  # Replica limits
  minReplicas: 1
  maxReplicas: 10

  # Scaling metrics
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50  # Target 50% CPU utilization

  # Scaling behavior (optional but recommended)
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # Wait 5 minutes before scaling down
      policies:
      - type: Percent
        value: 50          # Scale down max 50% of pods at a time
        periodSeconds: 60  # Every minute
      - type: Pods
        value: 2           # Or max 2 pods per minute
        periodSeconds: 60
      selectPolicy: Min    # Choose the more conservative policy

    scaleUp:
      stabilizationWindowSeconds: 0      # Immediate scale up
      policies:
      - type: Percent
        value: 100         # Double the pods
        periodSeconds: 15  # Every 15 seconds
      - type: Pods
        value: 4           # Or add max 4 pods
        periodSeconds: 15
      selectPolicy: Max    # Choose the more aggressive policy
```

### Step 5: Load Generator Manifest

Create `load-generator.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: load-generator
  namespace: default
  labels:
    app: load-generator
    demo: hpa
spec:
  containers:
  - name: busybox
    image: busybox:1.36
    command:
    - /bin/sh
    - -c
    - |
      echo "Starting load generation..."
      echo "Target: http://php-apache.default.svc.cluster.local"
      echo "Press Ctrl+C to stop"
      while true; do
        wget -q -O- http://php-apache.default.svc.cluster.local
        sleep 0.01  # 100 requests per second
      done
    resources:
      requests:
        cpu: 100m
        memory: 64Mi
      limits:
        cpu: 200m
        memory: 128Mi
  restartPolicy: Never
```

### Step 6: Deploy to Kubernetes

```bash
# Deploy all resources
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f hpa.yaml

# Verify deployment
kubectl get deployments
kubectl get pods
kubectl get svc
kubectl get hpa

# Expected output:
# NAME         READY   UP-TO-DATE   AVAILABLE   AGE
# php-apache   1/1     1            1           30s

# NAME                          READY   STATUS    RESTARTS   AGE
# php-apache-xxxxxxxxxx-xxxxx   1/1     Running   0          30s

# NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
# php-apache   ClusterIP   10.100.xx.xx    <none>        80/TCP    30s

# NAME             REFERENCE               TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
# php-apache-hpa   Deployment/php-apache   0%/50%    1         10        1          30s
```

## Part 3: Testing HPA in Action

### Step 1: Monitor Initial State

```bash
# Terminal 1: Watch HPA status
watch -n 1 kubectl get hpa php-apache-hpa

# Terminal 2: Watch pod status
watch -n 1 kubectl get pods -l app=php-apache

# Terminal 3: Monitor resource usage
watch -n 1 kubectl top pods -l app=php-apache
```

### Step 2: Generate Load

```bash
# Apply load generator
kubectl apply -f load-generator.yaml

# Monitor load generator logs
kubectl logs -f load-generator

# You should see continuous HTTP requests being made
```

### Step 3: Observe Autoscaling Behavior

**Timeline of Events:**

```
Time    CPU Usage    Replicas    HPA Action
-----   ---------    --------    -----------
0:00    5%           1           Normal operation
1:00    65%          1           CPU exceeds target (50%)
1:30    80%          2           Scale up to 2 pods
2:00    70%          3           Scale up to 3 pods
2:30    55%          4           Scale up to 4 pods
3:00    45%          4           Stable (below target)
```

**Watch HPA metrics:**

```bash
# Detailed HPA status
kubectl describe hpa php-apache-hpa

# Output shows:
# - Current CPU utilization
# - Desired replicas calculation
# - Scaling events
# - Conditions

# Example output:
# Name:                                                  php-apache-hpa
# Namespace:                                             default
# Reference:                                             Deployment/php-apache
# Metrics:                                               ( current / target )
#   resource cpu on pods  (as a percentage of request):  65% (130m) / 50%
# Min replicas:                                          1
# Max replicas:                                          10
# Deployment pods:                                       3 current / 4 desired
# Events:
#   Type     Reason             Age   From                       Message
#   ----     ------             ----  ----                       -------
#   Normal   SuccessfulRescale  2m    horizontal-pod-autoscaler  New size: 2; reason: cpu resource utilization (percentage of request) above target
#   Normal   SuccessfulRescale  1m    horizontal-pod-autoscaler  New size: 3; reason: cpu resource utilization (percentage of request) above target
```

### Step 4: Monitor Metrics

```bash
# View pod CPU/memory usage
kubectl top pods

# Expected output during load:
# NAME                          CPU(cores)   MEMORY(bytes)
# php-apache-xxxxxxxxxx-xxxxx   130m         45Mi
# php-apache-xxxxxxxxxx-yyyyy   125m         43Mi
# php-apache-xxxxxxxxxx-zzzzz   128m         44Mi

# View node resource usage
kubectl top nodes

# Check HPA metrics from API
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/namespaces/default/pods" | jq .
```

### Step 5: Stop Load and Observe Scale-Down

```bash
# Delete load generator
kubectl delete pod load-generator

# Watch HPA scale down (takes 5 minutes due to stabilizationWindow)
watch kubectl get hpa php-apache-hpa

# Timeline:
# Time after load stops:
# 0:00    CPU drops to ~5%
# 5:00    HPA starts scale-down
# 5:30    Replicas reduced to 2
# 6:00    Replicas reduced to 1 (minReplicas)
```

## Part 4: Advanced Scenarios

### Scenario 1: Adjust HPA Target

```bash
# Edit HPA to change target utilization
kubectl edit hpa php-apache-hpa

# Change averageUtilization from 50% to 30%
# This will cause more aggressive scaling

# Or apply updated manifest
cat <<EOF | kubectl apply -f -
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache
  minReplicas: 2      # Changed from 1
  maxReplicas: 15     # Changed from 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 30  # Changed from 50%
EOF
```

### Scenario 2: Memory-Based Autoscaling

Update `hpa.yaml` to include memory metrics:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: php-apache-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: php-apache
  minReplicas: 1
  maxReplicas: 10

  metrics:
  # CPU-based scaling
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50

  # Memory-based scaling
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70

  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Pods
        value: 2
        periodSeconds: 15
```

### Scenario 3: Multiple Load Generators

Create heavier load with multiple generators:

```bash
# Generate 3 load generators
for i in {1..3}; do
  kubectl run load-generator-$i --image=busybox:1.36 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://php-apache; done"
done

# Watch rapid scaling
kubectl get hpa -w

# Clean up
kubectl delete pod -l run=load-generator
```

### Scenario 4: Test HPA Limits

```bash
# Set very high load to test maxReplicas
kubectl run mega-load --image=busybox:1.36 --restart=Never -- /bin/sh -c "for i in {1..100}; do (while true; do wget -q -O- http://php-apache; done) & done; wait"

# HPA will scale up to maxReplicas: 10
kubectl get pods -l app=php-apache

# Verify HPA hits the ceiling
kubectl describe hpa php-apache-hpa | grep "ScaledToMax"
```

## Part 5: Monitoring and Troubleshooting

### View HPA Events

```bash
# Get scaling events
kubectl get events --field-selector involvedObject.name=php-apache-hpa --sort-by='.lastTimestamp'

# Example events:
# 5m   Normal  SuccessfulRescale  HPA  New size: 3; reason: cpu resource utilization above target
# 2m   Normal  SuccessfulRescale  HPA  New size: 5; reason: cpu resource utilization above target
# 1m   Normal  SuccessfulRescale  HPA  New size: 4; reason: All metrics below target
```

### Check HPA Conditions

```bash
# View HPA conditions
kubectl get hpa php-apache-hpa -o yaml | grep -A 10 conditions

# Healthy HPA shows:
# - AbleToScale: True
# - ScalingActive: True
# - ScalingLimited: False (unless at min/max)
```

### Troubleshooting Common Issues

**Issue 1: HPA shows `<unknown>` for targets**

```bash
# Check if Metrics Server is running
kubectl get pods -n kube-system | grep metrics-server

# Check Metrics Server logs
kubectl logs -n kube-system deployment/metrics-server

# Verify metrics are available
kubectl top pods

# If Metrics Server not installed:
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

**Issue 2: HPA not scaling despite high CPU**

```bash
# Verify resource requests are set
kubectl get deployment php-apache -o yaml | grep -A 5 resources

# Resource requests MUST be defined for HPA to work
# If missing, add them to deployment.yaml and reapply

# Check HPA calculation
kubectl describe hpa php-apache-hpa
# Look for: "unable to compute replica count"
```

**Issue 3: Pods not starting (Insufficient resources)**

```bash
# Check node resources
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check pending pods
kubectl get pods | grep Pending

# Describe pending pod
kubectl describe pod <pod-name>
# Look for: "0/2 nodes are available: insufficient cpu"

# Solution: Cluster Autoscaler will add nodes, or manually scale node group
```

## Part 6: Cleanup

### Delete Kubernetes Resources

```bash
# Delete HPA
kubectl delete hpa php-apache-hpa

# Delete service
kubectl delete svc php-apache

# Delete deployment
kubectl delete deployment php-apache

# Delete load generator (if still running)
kubectl delete pod load-generator

# Or delete all at once
kubectl delete -f k8s/
```

### Destroy CDK Infrastructure

```bash
cd cdk

# Destroy the stack
cdk destroy

# Confirm when prompted
# This will:
# - Delete EKS cluster
# - Remove node group
# - Delete VPC and subnets
# - Clean up all AWS resources

# Note: Cluster deletion takes ~10 minutes
```

### Verify Cleanup

```bash
# Verify no EKS clusters
aws eks list-clusters --region us-west-2

# Verify no running EC2 instances
aws ec2 describe-instances --filters "Name=tag:Project,Values=HPA-Demo" --query "Reservations[].Instances[].InstanceId"

# Check CloudFormation stacks
aws cloudformation list-stacks --stack-status-filter DELETE_IN_PROGRESS DELETE_COMPLETE
```

## Key Takeaways

### HPA Formula

The HPA controller uses this formula to calculate desired replicas:

```
desiredReplicas = ceil[currentReplicas * (currentMetricValue / targetMetricValue)]

Example:
- Current replicas: 2
- Current CPU: 120m per pod (60% of 200m request)
- Target CPU: 50%

desiredReplicas = ceil[2 * (60% / 50%)] = ceil[2 * 1.2] = ceil[2.4] = 3
```

### Best Practices Demonstrated

1. **Resource Requests are Mandatory**
   - HPA calculates based on percentage of requested resources
   - Without requests, HPA cannot function

2. **Conservative Scale-Down**
   - 5-minute stabilization window prevents flapping
   - Gradual scale-down (50% or 2 pods max per minute)

3. **Aggressive Scale-Up**
   - Immediate response to load spikes (0s stabilization)
   - Fast scale-up (100% or 4 pods per 15 seconds)

4. **Realistic Limits**
   - minReplicas: 1 (for demo; use 2+ in production)
   - maxReplicas: 10 (adjust based on cluster capacity)

5. **Combined with Readiness Probes**
   - New pods only receive traffic when ready
   - Prevents cascading failures during scale-up

### Monitoring Checklist

```bash
# Essential commands for HPA monitoring
kubectl get hpa                    # Quick status
kubectl describe hpa <name>        # Detailed info
kubectl top pods                   # Resource usage
kubectl get events --watch         # Real-time events
kubectl logs -f deployment/<name>  # Application logs
```

## Related Topics

For more autoscaling knowledge, explore the series:

### Autoscaling Series
- **[Part 1: Horizontal Pod Autoscaler](./kubernetes-autoscaling-complete-guide-part1-horizontal-pod-autoscaler.md)** - Theory and approaches
- **[Part 2: Cluster Autoscaling](./kubernetes-autoscaling-complete-guide-part2-cluster-autoscaling.md)** - Node-level autoscaling

### Kubernetes Fundamentals
- **[Kubernetes Complete Guide (Part 1): Introduction](./kubernetes-complete-guide-part1-introduction-zh.md)** - Architecture and concepts
- **[Kubernetes Complete Guide (Part 3): Advanced Features](./kubernetes-complete-guide-part3-advanced-zh.md)** - Production practices

### Production Kubernetes
- **[Building Production Kubernetes Platform on AWS EKS](./building-production-kubernetes-platform-aws-eks-cdk.md)** - Full platform architecture

## Conclusion

This hands-on tutorial demonstrated a complete end-to-end HPA implementation:

1. **Infrastructure as Code**: Provisioned EKS cluster with AWS CDK in TypeScript
2. **Application Deployment**: Used Kubernetes YAML manifests for declarative deployment
3. **HPA Configuration**: Configured CPU-based autoscaling with behavioral controls
4. **Load Testing**: Observed real-time scaling under load
5. **Production Patterns**: Demonstrated best practices for stable autoscaling

### What You Learned

- ✅ Setting up EKS cluster with CDK
- ✅ Deploying applications with resource requests
- ✅ Configuring HPA with scaling behaviors
- ✅ Load testing autoscaling behavior
- ✅ Monitoring and troubleshooting HPA
- ✅ Cleanup and cost management

### Next Steps

1. **Experiment with different targets**: Try 30%, 70% CPU utilization
2. **Add memory metrics**: Implement multi-metric autoscaling
3. **Integrate custom metrics**: Use Prometheus Adapter for application-specific metrics
4. **Deploy to production**: Apply these patterns to real applications
5. **Combine with Cluster Autoscaler**: See Part 2 for node-level autoscaling

The patterns demonstrated here form the foundation for production-grade Kubernetes autoscaling. Start simple with CPU-based HPA, then progressively adopt advanced techniques as your needs grow.

Happy autoscaling! 🚀
