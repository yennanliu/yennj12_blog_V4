---
title: "Building Centralized Logging with OpenSearch and AWS CDK"
date: 2024-12-15T14:30:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "architecture"]
tags: ["AI", "opensearch", "aws", "cdk", "kubernetes", "logging", "kinesis", "observability", "cloudwatch"]
summary: "Deep dive into architecting a production-ready centralized logging solution using OpenSearch, Kinesis Data Firehose, and AWS CDK for comprehensive Kubernetes cluster observability."
description: "Learn how to build a scalable centralized logging platform using OpenSearch, Kinesis Data Firehose, and AWS CDK to collect, process, and analyze logs from Kubernetes clusters and containerized applications."
readTime: "16 min"
---

Modern cloud-native applications running on Kubernetes generate massive amounts of log data across multiple services, pods, and infrastructure components. Without a centralized logging strategy, debugging issues, monitoring system health, and gaining operational insights becomes nearly impossible. This post explores building a production-ready centralized logging platform using OpenSearch, Kinesis Data Firehose, and AWS CDK.

## The Challenge: Taming Kubernetes Log Complexity

Kubernetes environments present unique logging challenges that traditional approaches struggle to address:

- **Distributed Log Sources**: Logs scattered across multiple pods, nodes, and services
- **Dynamic Infrastructure**: Containers and pods that come and go, making log correlation difficult
- **Volume and Velocity**: High-throughput applications generating millions of log entries per day
- **Multi-Format Data**: Structured JSON logs mixed with unstructured application logs
- **Operational Overhead**: Manual log aggregation and searching across multiple sources
- **Retention and Cost**: Balancing log retention needs with storage costs

## Why OpenSearch + Kinesis for Centralized Logging?

Before diving into the implementation, let's understand why this technology combination excels for Kubernetes logging:

### **OpenSearch: Elasticsearch-Compatible Search and Analytics**

OpenSearch provides powerful search and analytics capabilities specifically designed for log data:

```json
{
  "timestamp": "2024-12-15T14:30:00Z",
  "kubernetes": {
    "namespace": "production",
    "pod_name": "api-server-7d84f9b8c-k5x2p",
    "container": "api-server"
  },
  "level": "ERROR",
  "message": "Database connection failed",
  "request_id": "req-123456789"
}
```

**Key advantages:**
- **Full-text search** across all log fields and message content
- **Time-series analysis** for performance monitoring and trend analysis
- **Flexible querying** with complex filters and aggregations
- **Dashboards and visualizations** through OpenSearch Dashboards
- **Cost-effective** compared to managed Elasticsearch alternatives

### **Kinesis Data Firehose: Reliable Log Delivery**

Kinesis Data Firehose provides reliable, scalable log delivery with built-in transformation:

| Traditional Approach | Kinesis Firehose Approach |
|---------------------|---------------------------|
| Custom log shipping agents | Managed delivery service |
| Manual scaling and monitoring | Automatic scaling |
| Data transformation complexity | Built-in Lambda transformation |
| Single points of failure | Built-in redundancy |

## Architecture Overview: End-to-End Log Pipeline

Our centralized logging architecture follows a modern, serverless approach that scales automatically and requires minimal operational overhead:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EKS Cluster   │    │  CloudWatch     │    │   Kinesis       │
│                 │ -> │     Logs        │ -> │ Data Firehose   │
│ • Pod Logs      │    │                 │    │                 │
│ • App Logs      │    └─────────────────┘    └─────────────────┘
└─────────────────┘                                    │
                                                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│      S3         │    │     Lambda      │    │   OpenSearch    │
│  (Error Logs)   │ <- │  Transformation │ -> │    Service      │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### **Data Flow Breakdown:**

1. **Log Generation**: Kubernetes pods and applications generate logs
2. **Collection**: CloudWatch Logs captures logs via subscription filters
3. **Streaming**: Kinesis Data Firehose receives log streams in real-time
4. **Transformation**: Lambda functions process and enrich log data
5. **Indexing**: Processed logs are indexed in OpenSearch for analysis
6. **Error Handling**: Failed records are stored in S3 for retry and debugging

## Infrastructure as Code: AWS CDK Implementation

Let's explore the key components of our CDK implementation that makes this architecture deployable and maintainable.

### **Configuration-Driven Architecture**

The stack uses environment-specific configurations to support multiple deployment scenarios:

```typescript
// default-values.json
{
  "dev": {
    "opensearchInstanceType": "t3.small.search",
    "opensearchInstanceCount": 1,
    "firehoseBufferSize": 5,
    "logRetentionDays": 7
  },
  "prod": {
    "opensearchInstanceType": "r6g.large.search",
    "opensearchInstanceCount": 3,
    "firehoseBufferSize": 128,
    "logRetentionDays": 365
  }
}
```

This approach enables:
- **Environment consistency** with different resource sizing
- **Cost optimization** for development environments
- **Production reliability** with appropriate redundancy
- **Easy configuration management** without code changes

### **OpenSearch Domain Setup**

The OpenSearch domain is configured for high availability and security:

```typescript
const opensearchDomain = new opensearch.Domain(this, 'LoggingDomain', {
  version: opensearch.EngineVersion.OPENSEARCH_2_3,
  capacity: {
    masterNodes: config.opensearch.masterNodeCount,
    masterNodeInstanceType: config.opensearch.masterInstanceType,
    dataNodes: config.opensearch.dataNodeCount,
    dataNodeInstanceType: config.opensearch.dataInstanceType,
  },
  ebs: {
    volumeSize: config.opensearch.volumeSize,
    volumeType: ec2.EbsDeviceVolumeType.GP3,
  },
  nodeToNodeEncryption: true,
  encryptionAtRest: { enabled: true },
  enforceHttps: true,
  accessPolicies: [
    new iam.PolicyStatement({
      principals: [new iam.ServicePrincipal('firehose.amazonaws.com')],
      actions: ['es:ESHttpPost', 'es:ESHttpPut'],
      resources: ['*'],
    }),
  ],
});
```

**Key architectural decisions:**
- **Multi-AZ deployment** for high availability
- **Encryption at rest and in transit** for security compliance
- **Fine-grained access control** limiting service access
- **GP3 storage** for cost-effective performance

### **Kinesis Data Firehose Configuration**

The Firehose delivery stream handles log transportation with automatic retry and error handling:

```typescript
const deliveryStream = new kinesisFirehose.CfnDeliveryStream(this, 'LogDeliveryStream', {
  deliveryStreamType: 'DirectPut',
  deliveryStreamName: `${config.stackName}-logs`,
  amazonopensearchserviceDestinationConfiguration: {
    domainArn: opensearchDomain.domainArn,
    indexName: 'application-logs',
    roleArn: firehoseRole.roleArn,
    processingConfiguration: {
      enabled: true,
      processors: [{
        type: 'Lambda',
        parameters: [{
          parameterName: 'LambdaArn',
          parameterValue: transformFunction.functionArn,
        }],
      }],
    },
    bufferingHints: {
      sizeInMBs: config.firehose.bufferSize,
      intervalInSeconds: config.firehose.bufferInterval,
    },
    retryOptions: {
      durationInSeconds: 3600,
    },
    s3BackupMode: 'FailedDocumentsOnly',
    s3Configuration: {
      roleArn: firehoseRole.roleArn,
      bucketArn: errorBucket.bucketArn,
      prefix: 'failed-logs/',
    },
  },
});
```

**Performance optimizations:**
- **Configurable buffering** to balance latency and throughput
- **Lambda transformation** for data enrichment and formatting
- **Automatic retry** with exponential backoff for transient failures
- **S3 backup** for failed records to prevent data loss

## Log Transformation: Lambda Processing Pipeline

The Lambda function handles log transformation, enrichment, and formatting for optimal OpenSearch indexing:

### **Log Processing Logic**

```python
import json
import base64
import gzip
from datetime import datetime

def lambda_handler(event, context):
    output = []

    for record in event['records']:
        # Decode the log data
        compressed_payload = base64.b64decode(record['data'])
        uncompressed_payload = gzip.decompress(compressed_payload)
        log_data = json.loads(uncompressed_payload)

        # Process each log event
        for log_event in log_data['logEvents']:
            processed_event = process_log_event(log_event, log_data)

            # Format for OpenSearch
            output_record = {
                'recordId': record['recordId'],
                'result': 'Ok',
                'data': base64.b64encode(
                    json.dumps(processed_event).encode('utf-8')
                ).decode('utf-8')
            }
            output.append(output_record)

    return {'records': output}

def process_log_event(log_event, metadata):
    """Process and enrich individual log events"""

    # Extract Kubernetes metadata
    log_group = metadata.get('logGroup', '')
    kubernetes_info = parse_kubernetes_metadata(log_group)

    # Parse application log message
    message = log_event['message']
    parsed_message = parse_application_log(message)

    # Create enriched log document
    enriched_log = {
        '@timestamp': datetime.utcfromtimestamp(
            log_event['timestamp'] / 1000
        ).isoformat(),
        'kubernetes': kubernetes_info,
        'log_level': parsed_message.get('level', 'INFO'),
        'message': parsed_message.get('message', message),
        'request_id': parsed_message.get('request_id'),
        'source': {
            'log_group': log_group,
            'log_stream': metadata.get('logStream', ''),
        }
    }

    return enriched_log
```

### **Kubernetes Metadata Extraction**

The transformation function extracts valuable Kubernetes context from CloudWatch log groups:

```python
def parse_kubernetes_metadata(log_group):
    """Extract Kubernetes metadata from log group names"""

    # Example: /aws/eks/my-cluster/application/namespace/pod-name
    parts = log_group.split('/')

    if 'eks' in parts:
        return {
            'cluster_name': parts[3] if len(parts) > 3 else 'unknown',
            'namespace': parts[5] if len(parts) > 5 else 'default',
            'pod_name': parts[6] if len(parts) > 6 else 'unknown',
        }

    return {'source': 'application'}
```

## Deployment and Configuration Management

The CDK stack supports flexible deployment scenarios through configuration-driven infrastructure:

### **Multi-Environment Deployment**

Deploy different configurations for various environments:

```bash
# Development environment with minimal resources
cdk deploy --all --context env=dev

# Production environment with high availability
cdk deploy --all --context env=prod \
    --context enableVpc=true \
    --context opensearchInstanceCount=3
```

### **Selective Log Stream Configuration**

Configure specific log groups for OpenSearch ingestion:

```bash
# Deploy with specific EKS log groups
cdk deploy --all \
    --context eksPodGroup="/aws/eks/MyCluster/application" \
    --context logRetentionDays=30
```

### **VPC Integration**

For enhanced security, deploy OpenSearch within a VPC:

```typescript
// Enable VPC deployment
const vpcStack = new VpcStack(app, 'LoggingVpcStack', {
  env: { region: 'us-west-2' }
});

const opensearchStack = new OpenSearchStack(app, 'OpenSearchStack', {
  vpc: vpcStack.vpc,
  env: { region: 'us-west-2' }
});
```

## Monitoring and Observability

A centralized logging platform requires comprehensive monitoring of its own performance:

### **Key Metrics to Track**

```typescript
// CloudWatch metrics for monitoring
const logIngestionRate = new cloudwatch.Metric({
  namespace: 'AWS/Kinesis/Firehose',
  metricName: 'IncomingRecords',
  dimensionsMap: {
    DeliveryStreamName: deliveryStream.deliveryStreamName,
  },
});

const opensearchIndexingErrors = new cloudwatch.Metric({
  namespace: 'AWS/ES',
  metricName: 'IndexingErrors',
  dimensionsMap: {
    DomainName: opensearchDomain.domainName,
  },
});
```

### **Alerting Configuration**

```typescript
// Alert on high error rates
new cloudwatch.Alarm(this, 'HighIndexingErrors', {
  metric: opensearchIndexingErrors,
  threshold: 10,
  evaluationPeriods: 2,
  treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
});

// Alert on low log ingestion (potential pipeline issues)
new cloudwatch.Alarm(this, 'LowLogIngestion', {
  metric: logIngestionRate,
  threshold: 100,
  evaluationPeriods: 3,
  comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
});
```

## Production Considerations and Best Practices

### **Cost Optimization Strategies**

1. **Right-sizing OpenSearch instances** based on actual usage patterns
2. **Implementing log lifecycle policies** for automated data archival
3. **Using reserved instances** for predictable workloads
4. **Configuring appropriate buffer sizes** to optimize Firehose costs

### **Security and Compliance**

```typescript
// Fine-grained access control
const logAnalystRole = new iam.Role(this, 'LogAnalystRole', {
  assumedBy: new iam.ServicePrincipal('opensearch.amazonaws.com'),
  inlinePolicies: {
    LogSearchPolicy: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ['es:ESHttpGet', 'es:ESHttpPost'],
          resources: [`${opensearchDomain.domainArn}/application-logs/_search`],
        }),
      ],
    }),
  },
});
```

### **Disaster Recovery**

1. **Cross-region replication** for critical log data
2. **Automated backup strategies** using S3 lifecycle policies
3. **Infrastructure versioning** through CDK and Git
4. **Runbook procedures** for common failure scenarios

## Real-World Usage Patterns

### **Application Performance Monitoring**

Query examples for common operational scenarios:

```json
{
  "query": {
    "bool": {
      "must": [
        {"range": {"@timestamp": {"gte": "now-1h"}}},
        {"term": {"log_level": "ERROR"}},
        {"exists": {"field": "request_id"}}
      ]
    }
  },
  "aggs": {
    "error_by_service": {
      "terms": {"field": "kubernetes.namespace"}
    }
  }
}
```

### **Debugging Distributed Transactions**

Trace requests across multiple services using correlation IDs:

```json
{
  "query": {
    "term": {"request_id": "req-123456789"}
  },
  "sort": [{"@timestamp": "asc"}]
}
```

## Conclusion: Building Reliable Observability

This centralized logging architecture provides a foundation for comprehensive Kubernetes observability that scales with your infrastructure. The combination of OpenSearch's powerful search capabilities, Kinesis Firehose's reliable delivery, and CDK's infrastructure-as-code approach creates a maintainable, cost-effective solution.

### **Key Takeaways**

- **Serverless architecture** reduces operational overhead while providing automatic scaling
- **Configuration-driven deployment** enables consistent multi-environment management
- **Comprehensive error handling** prevents log data loss during system failures
- **Built-in monitoring** provides visibility into the logging pipeline itself
- **Cost optimization** through right-sizing and lifecycle policies

As your Kubernetes infrastructure grows, this logging platform provides the observability foundation needed for maintaining reliable, performant applications at scale.

The complete implementation is available in the [CDK Playground repository](https://github.com/yennanliu/cdk-playground/tree/main/opensearch-stack-1), including deployment scripts, configuration examples, and monitoring templates.