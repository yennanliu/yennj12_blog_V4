---
title: "Building AI Music Generation Platform: AWS CDK Architecture with SageMaker and Bedrock Comparison"
date: 2026-01-17T09:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "architecture"]
tags: ["AI", "aws", "cdk", "sagemaker", "bedrock", "machine-learning", "music-generation", "generative-ai", "lambda", "s3", "api-gateway"]
summary: "Complete guide to architecting a production-ready AI music generation platform on AWS using CDK, comparing SageMaker and Bedrock approaches with detailed pros, cons, and implementation strategies for generating music from text prompts."
readTime: "21 min"
---

Building an AI-powered music generation platform requires careful architectural planning to balance model performance, cost efficiency, and scalability. With the emergence of foundation models like Meta's MusicGen and open-source alternatives, enterprises can now deploy sophisticated music generation capabilities. This post explores designing production-grade infrastructure using AWS CDK, comparing SageMaker and Bedrock deployment approaches.

## The Challenge: Production AI Music Generation

Creating a platform that generates music from text prompts presents unique technical challenges:

- **Model Hosting**: Large AI models (1-10GB) require GPU infrastructure for acceptable latency
- **Scalability**: Traffic patterns vary dramatically between peak creative hours and idle periods
- **Cost Management**: GPU instances are expensive; inefficient utilization rapidly increases costs
- **Latency Requirements**: Users expect music generation in 30-90 seconds, not minutes
- **Multi-Modal Inputs**: Handle text prompts ("upbeat rock guitar solo"), style parameters (genre, tempo), duration controls
- **Output Management**: Generated audio files require storage, streaming, and lifecycle management
- **Model Versioning**: Continuous improvement necessitates model updates without downtime

## Music Generation Models: Technology Landscape

Before diving into infrastructure, understanding available models guides architectural decisions:

### **Leading AI Music Generation Models**

| Model | Organization | Size | Strengths | Limitations |
|-------|-------------|------|-----------|------------|
| **MusicGen** | Meta AI | 300M-3.3B params | High quality, multiple duration options, controllable | Large model size, GPU intensive |
| **Riffusion** | Hayk & Seth | Stable Diffusion-based | Fast inference, good for short clips | Less coherent for long compositions |
| **AudioCraft** | Meta AI | Various | Comprehensive audio generation suite | Complex deployment |
| **MusicLM** | Google | Not public | State-of-art quality (research only) | Not available for commercial use |
| **Jukebox** | OpenAI | 1.2B-5B params | Long-form generation, multiple genres | Very slow inference, high compute cost |

### **Why MusicGen for Production?**

Meta's MusicGen offers the best balance for production deployment:

```
MusicGen Capabilities:
┌────────────────────────────────────────────┐
│ • Text-to-music generation                 │
│ • Melody conditioning (convert humming)    │
│ • Genre/style control (rock, jazz, EDM)    │
│ • Duration control (up to 30s standard)    │
│ • Multiple model sizes (300M, 1.5B, 3.3B)  │
│ • Reasonable inference time (30-60s)       │
│ • Open source (MIT license)                │
└────────────────────────────────────────────┘
```

**Key Features:**
- **Text prompts**: "Energetic rock guitar with heavy drums, 120 BPM"
- **Style transfer**: Convert melodies between genres
- **Controllable generation**: Tempo, key, instrumentation parameters
- **Quality vs Speed tradeoff**: Multiple model sizes for different use cases

## Architecture Comparison: SageMaker vs Bedrock

AWS offers two primary paths for deploying ML models, each with distinct advantages:

### **High-Level Architecture Comparison**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SAGEMAKER ARCHITECTURE                              │
│                                                                         │
│  User Request → API Gateway → Lambda (Orchestration)                   │
│                                    ↓                                    │
│                      SageMaker Endpoint (Real-time)                    │
│                      • GPU instance (ml.g5.xlarge)                     │
│                      • Custom Docker container                          │
│                      • Auto-scaling enabled                             │
│                      • Model artifacts in S3                            │
│                                    ↓                                    │
│                      Generated Audio → S3 Bucket                       │
│                                    ↓                                    │
│                      Pre-signed URL → User                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      BEDROCK ARCHITECTURE                               │
│                                                                         │
│  User Request → API Gateway → Lambda (Orchestration)                   │
│                                    ↓                                    │
│                      Bedrock API (Serverless)                          │
│                      • No infrastructure management                     │
│                      • Pay-per-token pricing                            │
│                      • Built-in model catalog                           │
│                      • Limited to AWS-provided models                   │
│                                    ↓                                    │
│                      Generated Audio → S3 Bucket                       │
│                                    ↓                                    │
│                      Pre-signed URL → User                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### **Detailed Comparison Matrix**

| Aspect | SageMaker Approach | Bedrock Approach |
|--------|-------------------|------------------|
| **Model Selection** | Any open-source or custom model | Limited to AWS model catalog |
| **Infrastructure** | Manage EC2 instances, scaling policies | Fully serverless, zero management |
| **Pricing Model** | Hourly instance charges (e.g., $1.19/hr for g5.xlarge) | Pay-per-invocation (varies by model) |
| **Cold Start** | Keep instances warm or accept 3-5 min cold start | No cold start, instant availability |
| **Customization** | Full control: custom inference code, pre/post-processing | Limited to API parameters |
| **Deployment Complexity** | High: Docker images, model artifacts, endpoints | Low: API integration only |
| **Cost at Low Volume** | High: Minimum 1 instance running 24/7 | Low: Pay only for actual usage |
| **Cost at High Volume** | Low: Fixed hourly cost regardless of requests | High: Per-request costs accumulate |
| **Model Updates** | Full control: version management, A/B testing | AWS controls model versions |
| **Latency** | Predictable: warm instances respond in seconds | Variable: depends on AWS backend load |
| **Compliance** | Full control: VPC deployment, network isolation | Shared service: limited network control |

## SageMaker Architecture Deep Dive

For custom models like MusicGen, SageMaker provides complete control over the deployment:

### **Core Architecture Components**

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER LAYER                                   │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   Web UI     │  │   Mobile     │  │   API        │            │
│  │   React App  │  │   iOS/Android│  │   Clients    │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                  │                     │
│         └─────────────────┴──────────────────┘                     │
│                           │                                         │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (REST API)                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  POST /generate-music                                        │  │
│  │  GET  /status/{requestId}                                    │  │
│  │  GET  /download/{musicId}                                    │  │
│  │                                                               │  │
│  │  • Rate limiting: 100 requests/second                        │  │
│  │  • Authentication: API keys or Cognito                       │  │
│  │  • Request validation                                         │  │
│  │  • CORS configuration                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               LAMBDA ORCHESTRATION LAYER                            │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  MusicGenerationOrchestrator Lambda                           │ │
│  │                                                                │ │
│  │  Responsibilities:                                             │ │
│  │  1. Parse and validate user prompts                           │ │
│  │  2. Extract style parameters (genre, tempo, mood)             │ │
│  │  3. Invoke SageMaker endpoint asynchronously                  │ │
│  │  4. Store request metadata in DynamoDB                        │ │
│  │  5. Return request ID for status polling                      │ │
│  │                                                                │ │
│  │  Config: 512MB RAM, 30s timeout, Python 3.11                  │ │
│  └────────────────────────┬──────────────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  SAGEMAKER REAL-TIME ENDPOINT                       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  MusicGen Model Endpoint                                     │  │
│  │                                                               │  │
│  │  Instance: ml.g5.xlarge                                       │  │
│  │  • 1x NVIDIA A10G Tensor Core GPU (24GB)                     │  │
│  │  • 4 vCPUs, 16GB RAM                                          │  │
│  │  • Cost: ~$1.19/hour (~$850/month 24/7)                      │  │
│  │                                                               │  │
│  │  Container:                                                    │  │
│  │  • Custom Docker image with PyTorch 2.0                      │  │
│  │  • MusicGen model loaded at startup                          │  │
│  │  • Inference script: generate_music.py                       │  │
│  │                                                               │  │
│  │  Auto-scaling:                                                │  │
│  │  • Min instances: 1 (always warm)                            │  │
│  │  • Max instances: 5                                           │  │
│  │  • Scale on: Invocations > 10/minute                         │  │
│  │                                                               │  │
│  │  Generation Flow:                                             │  │
│  │  1. Receive prompt: "upbeat rock guitar, 120 BPM"            │  │
│  │  2. Tokenize text input                                       │  │
│  │  3. Run model inference (30-60s for 30s audio)               │  │
│  │  4. Convert output tensors to WAV/MP3                        │  │
│  │  5. Return audio bytes (or upload to S3)                     │  │
│  └────────────────────────┬──────────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      STORAGE & DELIVERY                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  S3 Bucket: generated-music-assets                           │  │
│  │                                                               │  │
│  │  Structure:                                                    │  │
│  │  /audio/                                                       │  │
│  │    └── {userId}/                                              │  │
│  │         └── {requestId}/                                      │  │
│  │              ├── output.mp3    (final audio)                 │  │
│  │              ├── metadata.json (prompt, params, timestamps)   │  │
│  │              └── waveform.png  (visualization)                │  │
│  │                                                               │  │
│  │  Lifecycle:                                                    │  │
│  │  • Delete after 30 days (configurable)                       │  │
│  │  • Intelligent tiering for cost optimization                 │  │
│  │                                                               │  │
│  │  Access:                                                       │  │
│  │  • Pre-signed URLs with 24-hour expiration                   │  │
│  │  • CloudFront CDN for faster global delivery (optional)      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  DynamoDB: MusicGenerationRequests                           │  │
│  │                                                               │  │
│  │  Schema:                                                       │  │
│  │  {                                                             │  │
│  │    "requestId": "uuid-v4",                                    │  │
│  │    "userId": "user-123",                                      │  │
│  │    "prompt": "upbeat rock guitar, 120 BPM",                  │  │
│  │    "parameters": {                                            │  │
│  │      "duration": 30,                                          │  │
│  │      "genre": "rock",                                         │  │
│  │      "tempo": 120,                                            │  │
│  │      "model": "musicgen-medium"                               │  │
│  │    },                                                          │  │
│  │    "status": "processing | completed | failed",               │  │
│  │    "outputUrl": "s3://bucket/path/output.mp3",               │  │
│  │    "createdAt": 1705456789,                                   │  │
│  │    "completedAt": 1705456850,                                 │  │
│  │    "generationTimeMs": 61000                                  │  │
│  │  }                                                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  MONITORING & OBSERVABILITY                         │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐        │
│  │ CloudWatch  │  │  X-Ray      │  │  SageMaker Model    │        │
│  │   Metrics   │  │  Tracing    │  │    Monitor          │        │
│  │             │  │             │  │                     │        │
│  │ • Latency   │  │ • E2E trace │  │ • Model drift       │        │
│  │ • Errors    │  │ • Bottleneck│  │ • Data quality      │        │
│  │ • Cost      │  │             │  │ • Bias detection    │        │
│  └─────────────┘  └─────────────┘  └─────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

### **SageMaker CDK Implementation**

```typescript
import * as cdk from 'aws-cdk-lib';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export class MusicGenSageMakerStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 bucket for model artifacts and generated music
    const modelBucket = new s3.Bucket(this, 'ModelBucket', {
      bucketName: 'musicgen-models-and-outputs',
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
      lifecycleRules: [{
        id: 'DeleteOldGenerations',
        enabled: true,
        expiration: cdk.Duration.days(30), // Auto-delete after 30 days
      }],
    });

    // DynamoDB table for request tracking
    const requestTable = new dynamodb.Table(this, 'RequestTable', {
      tableName: 'MusicGenerationRequests',
      partitionKey: { name: 'requestId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'userId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl', // Auto-cleanup
    });

    // Add GSI for querying by user
    requestTable.addGlobalSecondaryIndex({
      indexName: 'UserIdIndex',
      partitionKey: { name: 'userId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'createdAt', type: dynamodb.AttributeType.NUMBER },
    });

    // IAM role for SageMaker execution
    const sagemakerRole = new iam.Role(this, 'SageMakerRole', {
      assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSageMakerFullAccess'),
      ],
    });

    modelBucket.grantReadWrite(sagemakerRole);

    // SageMaker Model - References the MusicGen model in S3
    const model = new sagemaker.CfnModel(this, 'MusicGenModel', {
      modelName: 'musicgen-medium-v1',
      executionRoleArn: sagemakerRole.roleArn,
      primaryContainer: {
        image: `763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:2.0.0-gpu-py310`, // Deep Learning Container
        modelDataUrl: `s3://${modelBucket.bucketName}/models/musicgen-medium.tar.gz`,
        environment: {
          SAGEMAKER_CONTAINER_LOG_LEVEL: '20',
          SAGEMAKER_REGION: this.region,
          MODEL_NAME: 'facebook/musicgen-medium',
          INFERENCE_TIMEOUT: '180', // 3 minutes for music generation
        },
      },
    });

    // SageMaker Endpoint Configuration
    const endpointConfig = new sagemaker.CfnEndpointConfig(this, 'EndpointConfig', {
      endpointConfigName: 'musicgen-endpoint-config',
      productionVariants: [{
        variantName: 'AllTraffic',
        modelName: model.modelName!,
        instanceType: 'ml.g5.xlarge', // GPU instance for fast inference
        initialInstanceCount: 1, // Start with 1 instance
        initialVariantWeight: 1,
      }],
    });

    endpointConfig.addDependency(model);

    // SageMaker Endpoint
    const endpoint = new sagemaker.CfnEndpoint(this, 'Endpoint', {
      endpointName: 'musicgen-production',
      endpointConfigName: endpointConfig.endpointConfigName!,
    });

    endpoint.addDependency(endpointConfig);

    // Auto-scaling for the endpoint
    const scalableTarget = new cdk.aws_applicationautoscaling.ScalableTarget(this, 'ScalableTarget', {
      serviceNamespace: cdk.aws_applicationautoscaling.ServiceNamespace.SAGEMAKER,
      resourceId: `endpoint/${endpoint.endpointName}/variant/AllTraffic`,
      scalableDimension: 'sagemaker:variant:DesiredInstanceCount',
      minCapacity: 1,
      maxCapacity: 5,
    });

    scalableTarget.scaleOnMetric('InvocationScaling', {
      metric: new cdk.aws_cloudwatch.Metric({
        namespace: 'AWS/SageMaker',
        metricName: 'InvocationsPerInstance',
        dimensionsMap: {
          EndpointName: endpoint.endpointName!,
          VariantName: 'AllTraffic',
        },
        statistic: 'Average',
        period: cdk.Duration.minutes(1),
      }),
      scalingSteps: [
        { upper: 10, change: 0 }, // No scaling if < 10 invocations
        { lower: 10, change: +1 }, // Add instance if > 10 invocations
        { lower: 50, change: +2 }, // Add 2 instances if > 50 invocations
      ],
      adjustmentType: cdk.aws_applicationautoscaling.AdjustmentType.CHANGE_IN_CAPACITY,
    });

    // Lambda function for orchestration
    const orchestratorLambda = new lambda.Function(this, 'OrchestratorLambda', {
      functionName: 'music-generation-orchestrator',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/orchestrator'),
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        SAGEMAKER_ENDPOINT: endpoint.endpointName!,
        S3_BUCKET: modelBucket.bucketName,
        DYNAMODB_TABLE: requestTable.tableName,
      },
    });

    // Grant permissions
    requestTable.grantReadWriteData(orchestratorLambda);
    modelBucket.grantReadWrite(orchestratorLambda);
    orchestratorLambda.addToRolePolicy(new iam.PolicyStatement({
      actions: ['sagemaker:InvokeEndpoint'],
      resources: [endpoint.ref],
    }));

    // API Gateway
    const api = new apigateway.RestApi(this, 'MusicGenAPI', {
      restApiName: 'Music Generation API',
      description: 'API for generating music from text prompts',
      deployOptions: {
        stageName: 'prod',
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        metricsEnabled: true,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
      },
    });

    // API endpoints
    const musicResource = api.root.addResource('music');
    const generateResource = musicResource.addResource('generate');

    generateResource.addMethod('POST', new apigateway.LambdaIntegration(orchestratorLambda), {
      apiKeyRequired: true,
      requestValidator: new apigateway.RequestValidator(this, 'RequestValidator', {
        restApi: api,
        validateRequestBody: true,
        validateRequestParameters: true,
      }),
      requestModels: {
        'application/json': new apigateway.Model(this, 'GenerateRequestModel', {
          restApi: api,
          contentType: 'application/json',
          schema: {
            type: apigateway.JsonSchemaType.OBJECT,
            required: ['prompt'],
            properties: {
              prompt: { type: apigateway.JsonSchemaType.STRING },
              duration: { type: apigateway.JsonSchemaType.NUMBER, default: 30 },
              genre: { type: apigateway.JsonSchemaType.STRING },
              tempo: { type: apigateway.JsonSchemaType.NUMBER },
            },
          },
        }),
      },
    });

    // API Key for authentication
    const apiKey = api.addApiKey('MusicGenApiKey', {
      apiKeyName: 'music-gen-key',
    });

    const usagePlan = api.addUsagePlan('UsagePlan', {
      name: 'Standard',
      throttle: {
        rateLimit: 10,
        burstLimit: 20,
      },
      quota: {
        limit: 1000,
        period: apigateway.Period.MONTH,
      },
    });

    usagePlan.addApiKey(apiKey);
    usagePlan.addApiStage({
      stage: api.deploymentStage,
    });

    // Outputs
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: api.url,
      description: 'Music Generation API URL',
    });

    new cdk.CfnOutput(this, 'ApiKeyId', {
      value: apiKey.keyId,
      description: 'API Key ID for authentication',
    });

    new cdk.CfnOutput(this, 'EndpointName', {
      value: endpoint.endpointName!,
      description: 'SageMaker Endpoint Name',
    });
  }
}
```

### **Lambda Orchestrator Implementation**

```python
# lambda/orchestrator/index.py
import json
import boto3
import uuid
import time
from datetime import datetime

sagemaker_runtime = boto3.client('sagemaker-runtime')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

ENDPOINT_NAME = os.environ['SAGEMAKER_ENDPOINT']
S3_BUCKET = os.environ['S3_BUCKET']
TABLE_NAME = os.environ['DYNAMODB_TABLE']

table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    """
    Orchestrates music generation requests
    """
    try:
        # Parse request
        body = json.loads(event['body'])
        prompt = body['prompt']
        duration = body.get('duration', 30)
        genre = body.get('genre', 'general')
        tempo = body.get('tempo', 120)

        # Extract user ID from request context (Cognito or API Key)
        user_id = event['requestContext']['identity']['apiKey']

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Prepare SageMaker input
        sagemaker_input = {
            'prompt': prompt,
            'duration': duration,
            'genre': genre,
            'tempo': tempo,
            'model': 'musicgen-medium',
        }

        # Store initial request in DynamoDB
        table.put_item(Item={
            'requestId': request_id,
            'userId': user_id,
            'prompt': prompt,
            'parameters': sagemaker_input,
            'status': 'processing',
            'createdAt': int(time.time()),
            'ttl': int(time.time()) + (30 * 24 * 60 * 60), # 30 days TTL
        })

        # Invoke SageMaker endpoint asynchronously
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='application/json',
            Body=json.dumps(sagemaker_input),
        )

        # Parse response
        result = json.loads(response['Body'].read().decode())
        audio_bytes = result['audio']  # Base64 encoded audio

        # Upload to S3
        s3_key = f"audio/{user_id}/{request_id}/output.mp3"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType='audio/mpeg',
        )

        # Generate pre-signed URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': s3_key},
            ExpiresIn=86400  # 24 hours
        )

        # Update DynamoDB with completion
        table.update_item(
            Key={'requestId': request_id, 'userId': user_id},
            UpdateExpression='SET #status = :status, outputUrl = :url, completedAt = :completed',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'completed',
                ':url': presigned_url,
                ':completed': int(time.time()),
            }
        )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
            'body': json.dumps({
                'requestId': request_id,
                'status': 'completed',
                'downloadUrl': presigned_url,
                'message': 'Music generated successfully',
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

## Bedrock Architecture Alternative

AWS Bedrock offers a serverless alternative, though currently limited in music generation models:

### **Bedrock Architecture**

```typescript
// Note: Bedrock doesn't currently have music generation models
// This is a conceptual implementation showing how it would work

import * as bedrock from 'aws-cdk-lib/aws-bedrock';

export class MusicGenBedrockStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Storage bucket
    const outputBucket = new s3.Bucket(this, 'OutputBucket', {
      bucketName: 'musicgen-bedrock-outputs',
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    // Lambda function using Bedrock
    const bedrockLambda = new lambda.Function(this, 'BedrockLambda', {
      functionName: 'music-generation-bedrock',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromInline(`
import json
import boto3
import base64

bedrock = boto3.client('bedrock-runtime')

def handler(event, context):
    body = json.loads(event['body'])
    prompt = body['prompt']

    # Invoke Bedrock (conceptual - no music model yet)
    response = bedrock.invoke_model(
        modelId='amazon.music-gen-v1',  # Hypothetical model
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'prompt': prompt,
            'duration': body.get('duration', 30),
            'genre': body.get('genre'),
        })
    )

    result = json.loads(response['body'].read())

    return {
        'statusCode': 200,
        'body': json.dumps({
            'audio_url': result['audio_url'],
            'status': 'completed'
        })
    }
      `),
      timeout: cdk.Duration.seconds(180),
      environment: {
        S3_BUCKET: outputBucket.bucketName,
      },
    });

    // Grant Bedrock permissions
    bedrockLambda.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    outputBucket.grantReadWrite(bedrockLambda);
  }
}
```

## Detailed Pros and Cons Analysis

### **SageMaker Approach**

**Pros:**

1. **Model Flexibility**
   - Deploy any open-source model (MusicGen, AudioCraft, custom models)
   - Full control over inference pipeline
   - Custom pre/post-processing logic

2. **Performance Optimization**
   - Keep instances warm for consistent latency
   - Batch processing capabilities
   - GPU acceleration for complex models

3. **Cost at Scale**
   - Fixed hourly cost regardless of request volume
   - Break-even at ~850 requests/month
   - Predictable infrastructure costs

4. **Customization**
   - Custom Docker containers
   - Model fine-tuning on your data
   - A/B testing between model versions

5. **Enterprise Features**
   - VPC deployment for network isolation
   - Private endpoint support
   - Full compliance control (HIPAA, SOC2)

**Cons:**

1. **Operational Complexity**
   - Manage Docker images, model artifacts
   - Handle endpoint deployments and updates
   - Monitor instance health and scaling

2. **Cold Start Latency**
   - 3-5 minutes to launch new instances
   - Must keep at least 1 instance running ($850/month minimum)

3. **Infrastructure Overhead**
   - Complex CDK code for endpoint management
   - Auto-scaling configuration required
   - Model deployment pipelines needed

4. **Cost at Low Volume**
   - Expensive for prototyping/low traffic
   - Minimum $850/month even with zero requests

### **Bedrock Approach**

**Pros:**

1. **Zero Infrastructure Management**
   - No servers, containers, or scaling to manage
   - AWS handles all backend infrastructure
   - Focus entirely on application logic

2. **Cost Efficiency at Low Volume**
   - Pay only for actual API calls
   - No minimum monthly costs
   - Perfect for prototyping and MVPs

3. **Instant Availability**
   - No cold start delays
   - Models available 24/7 without pre-warming
   - Immediate scaling to handle traffic spikes

4. **Simple Integration**
   - Single API call for inference
   - No model deployment pipelines
   - Automatic model updates from AWS

5. **Rapid Development**
   - Deploy in minutes vs hours/days
   - Minimal CDK code required
   - Easy experimentation with different models

**Cons:**

1. **Limited Model Selection**
   - Only AWS-provided models available
   - Currently no music generation models (as of 2026)
   - Cannot use custom or open-source models

2. **No Customization**
   - Fixed inference parameters
   - Cannot modify preprocessing/postprocessing
   - No model fine-tuning options

3. **Cost at High Volume**
   - Per-invocation pricing adds up quickly
   - More expensive than SageMaker beyond 1000+ requests/month
   - Unpredictable costs with traffic spikes

4. **Limited Control**
   - Cannot choose model versions
   - No control over model updates
   - Limited network isolation options

5. **Vendor Lock-in**
   - Tight coupling to AWS Bedrock
   - Cannot migrate to other cloud providers easily
   - Dependent on AWS model roadmap

## Cost Analysis: Break-Even Calculation

### **Monthly Cost Comparison**

```
SageMaker Costs:
┌────────────────────────────────────────────────────────┐
│ ml.g5.xlarge instance: $1.19/hour                      │
│ 24/7 operation: $1.19 × 24 × 30 = $857/month          │
│                                                        │
│ Additional costs:                                      │
│ • Model storage (S3): ~$5/month                       │
│ • Data transfer: ~$10/month                           │
│ • CloudWatch logs: ~$5/month                          │
│                                                        │
│ Total: ~$877/month (fixed, regardless of volume)      │
└────────────────────────────────────────────────────────┘

Bedrock Costs (Hypothetical):
┌────────────────────────────────────────────────────────┐
│ Assumed pricing: $0.08 per generation                  │
│ (Similar to Stable Diffusion on Bedrock)              │
│                                                        │
│ Volume-based costs:                                    │
│ • 100 generations/month: $8                           │
│ • 500 generations/month: $40                          │
│ • 1,000 generations/month: $80                        │
│ • 5,000 generations/month: $400                       │
│ • 10,000 generations/month: $800                      │
│ • 20,000 generations/month: $1,600                    │
│                                                        │
│ Break-even point: ~10,950 generations/month           │
└────────────────────────────────────────────────────────┘
```

### **Cost Decision Matrix**

| Monthly Volume | Best Choice | Estimated Cost |
|---------------|------------|----------------|
| **< 100 generations** | Bedrock | $8 |
| **100-500** | Bedrock | $40 |
| **500-1,000** | Bedrock | $80 |
| **1,000-10,000** | Depends on growth | $80-800 |
| **> 10,000** | SageMaker | $877 (fixed) |

## Production Use Cases and Examples

### **Use Case 1: Music Streaming App Background Tracks**

**Scenario**: Generate personalized background music for meditation, study, or sleep

```python
# Example API request
{
  "prompt": "Calm ambient music with soft piano, slow tempo for meditation",
  "duration": 120,  # 2 minutes
  "genre": "ambient",
  "tempo": 60,
  "mood": "relaxing"
}
```

**Best Approach**: SageMaker
- High volume (thousands of generations daily)
- Fixed costs benefit from scale
- Custom model fine-tuned on relaxation music

### **Use Case 2: Video Content Creator Tool**

**Scenario**: YouTubers generate custom background music for videos

```python
{
  "prompt": "Upbeat electronic music, 140 BPM, energetic for tech review video",
  "duration": 180,
  "genre": "electronic",
  "tempo": 140,
  "instrumentation": ["synthesizer", "drums"]
}
```

**Best Approach**: Hybrid
- Use Bedrock for low-volume users (free tier)
- Migrate power users to SageMaker endpoints
- Volume-based pricing tiers

### **Use Case 3: Game Development Studio**

**Scenario**: Generate adaptive background music for game scenarios

```python
{
  "prompt": "Intense orchestral battle music, fast tempo, heroic theme",
  "duration": 60,
  "genre": "orchestral",
  "tempo": 160,
  "mood": "intense",
  "dynamic_range": "high"
}
```

**Best Approach**: SageMaker
- Need custom models trained on game music
- Low latency requirements
- Batch generation during development

## Advanced Features and Optimizations

### **Model Optimization Strategies**

1. **Model Quantization**
   ```python
   # Reduce model size and inference time
   from transformers import AutoModelForCausalLM

   model = AutoModelForCausalLM.from_pretrained(
       "facebook/musicgen-medium",
       torch_dtype=torch.float16,  # Half-precision
       device_map="auto"
   )
   ```

2. **Batch Processing**
   ```python
   # Process multiple prompts together
   prompts = [
       "rock guitar solo",
       "jazz piano",
       "ambient synth"
   ]

   # Generate in parallel
   outputs = model.generate(prompts, batch_size=3)
   ```

3. **Caching Strategy**
   ```python
   # Cache similar prompts
   import hashlib

   def get_cache_key(prompt, params):
       data = f"{prompt}_{params['duration']}_{params['genre']}"
       return hashlib.md5(data.encode()).hexdigest()
   ```

### **Monitoring and Alerting**

```typescript
// CloudWatch alarms for production
const latencyAlarm = new cloudwatch.Alarm(this, 'HighLatency', {
  metric: new cloudwatch.Metric({
    namespace: 'AWS/SageMaker',
    metricName: 'ModelLatency',
    dimensionsMap: {
      EndpointName: endpoint.endpointName!,
      VariantName: 'AllTraffic',
    },
    statistic: 'Average',
    period: cdk.Duration.minutes(5),
  }),
  threshold: 60000, // 60 seconds
  evaluationPeriods: 2,
  alarmDescription: 'Music generation taking too long',
});

// Cost monitoring
const costAlarm = new cloudwatch.Alarm(this, 'HighCost', {
  metric: new cloudwatch.Metric({
    namespace: 'AWS/SageMaker',
    metricName: 'InvocationCount',
    dimensionsMap: {
      EndpointName: endpoint.endpointName!,
    },
    statistic: 'Sum',
    period: cdk.Duration.days(1),
  }),
  threshold: 10000,
  evaluationPeriods: 1,
  alarmDescription: 'Daily invocations exceeding budget',
});
```

## Deployment and Testing

### **Deployment Workflow**

```bash
# 1. Package model artifacts
cd model
python download_musicgen.py
tar -czf musicgen-medium.tar.gz model/

# 2. Upload to S3
aws s3 cp musicgen-medium.tar.gz s3://musicgen-models/models/

# 3. Deploy CDK stack
cd ../infrastructure
npm install
cdk bootstrap
cdk deploy MusicGenSageMakerStack

# 4. Test endpoint
python test_generation.py
```

### **Testing Script**

```python
# test_generation.py
import boto3
import json
import time

api_url = "https://api-id.execute-api.us-east-1.amazonaws.com/prod"
api_key = "your-api-key"

def test_music_generation():
    # Test rock music
    rock_prompt = {
        "prompt": "Energetic rock guitar with heavy drums, 120 BPM",
        "duration": 30,
        "genre": "rock",
        "tempo": 120
    }

    response = requests.post(
        f"{api_url}/music/generate",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json"
        },
        json=rock_prompt
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    # Download and verify audio
    result = response.json()
    audio_url = result['downloadUrl']

    audio_response = requests.get(audio_url)
    with open('output_rock.mp3', 'wb') as f:
        f.write(audio_response.content)

    print("✅ Rock music generated successfully")

    # Test R&B music
    rnb_prompt = {
        "prompt": "Smooth R&B with soulful vocals, slow tempo, romantic mood",
        "duration": 30,
        "genre": "rnb",
        "tempo": 80
    }

    response = requests.post(
        f"{api_url}/music/generate",
        headers={"x-api-key": api_key},
        json=rnb_prompt
    )

    print("✅ R&B music generated successfully")

if __name__ == "__main__":
    test_music_generation()
```

## Conclusion

Building production-grade AI music generation infrastructure requires careful evaluation of architectural tradeoffs. Both SageMaker and Bedrock offer compelling advantages depending on your requirements.

### **Choose SageMaker When:**
- You need custom models (MusicGen, custom fine-tuned models)
- High volume usage (>10,000 generations/month)
- Require full control over inference pipeline
- Need VPC deployment for compliance
- Latency predictability is critical

### **Choose Bedrock When:**
- Prototyping or MVP development
- Low volume usage (<5,000 generations/month)
- Want zero infrastructure management
- Need rapid deployment
- Cost predictability at low scale matters
- AWS catalog models meet your needs

### **Hybrid Approach:**
For many production scenarios, a hybrid strategy offers the best of both worlds:
1. **Start with Bedrock** for quick validation and MVP
2. **Monitor usage patterns** and cost trajectories
3. **Migrate to SageMaker** when volume justifies fixed infrastructure costs
4. **Maintain Bedrock** as fallback during SageMaker maintenance

### **Real-World Recommendations**

| Scenario | Recommendation | Rationale |
|----------|---------------|-----------|
| **Startup MVP** | Bedrock | Minimize upfront investment |
| **Growing Product (1K-10K users)** | SageMaker | Predictable costs at scale |
| **Enterprise Platform** | SageMaker + Multi-region | High availability, compliance |
| **Research/Experimentation** | Bedrock | Rapid iteration, low overhead |

The complete CDK implementation, including custom Docker containers for MusicGen, Lambda functions, and testing scripts, is available in the [CDK playground repository](https://github.com/yennanliu/cdk-playground/tree/main/ai-music-generation).

Whether you're building a music creation platform for content creators, integrating generative music into games, or developing adaptive soundscapes for meditation apps, understanding these architectural patterns enables you to make informed infrastructure decisions that balance performance, cost, and operational complexity.
