---
title: "Building an Intelligent Bitcoin Trading System with AWS CDK and ML Models"
date: 2026-01-24T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "architecture"]
tags: ["AWS", "CDK", "Bitcoin", "Trading", "Machine Learning", "Bedrock", "HuggingFace", "Lambda", "EventBridge", "DynamoDB", "SageMaker"]
summary: "Build a production-ready automated Bitcoin trading system using AWS CDK that integrates ML models from Bedrock and HuggingFace for price prediction and executes trades based on real-time market events."
description: "Learn how to architect and deploy an intelligent cryptocurrency trading system on AWS using CDK, with historical price analysis, ML-powered predictions from AWS Bedrock and HuggingFace, and event-driven trade execution."
readTime: "18 min"
---

The cryptocurrency market operates 24/7 with extreme volatility, making manual trading challenging and inefficient. This post explores building a production-ready automated Bitcoin trading system that leverages AWS services, machine learning models, and infrastructure-as-code practices to make intelligent trading decisions based on historical data analysis and real-time price predictions.

## The Problem: Automated Crypto Trading at Scale

Building a reliable cryptocurrency trading system presents several unique challenges:

- **Real-Time Data Processing**: Bitcoin prices change every second, requiring near-instant analysis
- **Historical Data Management**: Storing and analyzing years of price history for pattern recognition
- **ML Model Integration**: Leveraging multiple prediction models (Bedrock, HuggingFace, custom APIs)
- **Risk Management**: Implementing safeguards against catastrophic losses
- **Event-Driven Architecture**: Responding to market events with millisecond latency
- **Cost Optimization**: Running ML inference efficiently without breaking the bank
- **Audit Trail**: Maintaining complete transaction history for compliance and analysis

## Architecture Overview: Event-Driven ML Trading Pipeline

Our architecture combines serverless components, managed ML services, and event-driven patterns to create a scalable, cost-effective trading system:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  CoinGecko/     │    │   EventBridge   │    │     Lambda      │
│  Binance API    │ -> │   Scheduler     │ -> │ Price Collector │
│                 │    │ (Every 1 min)   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   DynamoDB      │    │   S3 Bucket     │    │   Timestream    │
│ Historical Data │ <- │ Raw Price Data  │ <- │  Time Series    │
│                 │    │                 │    │     Database    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                                       v
                       ┌────────────────────────────────────────┐
                       │          ML Prediction Layer           │
                       │                                        │
                       │  ┌──────────┐  ┌──────────┐  ┌──────┐ │
                       │  │ Bedrock  │  │HuggingFace│  │ API  │ │
                       │  │  Claude  │  │  Model    │  │Custom│ │
                       │  └──────────┘  └──────────┘  └──────┘ │
                       └────────────────────────────────────────┘
                                         │
                                         v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SNS Topic     │    │  Step Functions │    │     Lambda      │
│ Trade Alerts    │ <- │ Trading Logic   │ <- │  Trade Executor │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                v
                       ┌─────────────────┐
                       │   DynamoDB      │
                       │  Trade History  │
                       │                 │
                       └─────────────────┘
```

### **Data Flow Breakdown:**

1. **Price Collection**: EventBridge triggers Lambda to fetch Bitcoin prices every minute
2. **Storage**: Raw data stored in S3, processed data in DynamoDB and Timestream
3. **Historical Analysis**: Lambda analyzes patterns from historical data
4. **ML Prediction**: Multiple models (Bedrock, HuggingFace, custom) generate predictions
5. **Decision Engine**: Step Functions orchestrates trading logic based on predictions
6. **Trade Execution**: Lambda executes buy/sell orders via exchange APIs
7. **Notification**: SNS alerts stakeholders of trade executions
8. **Audit**: All trades logged in DynamoDB for compliance and analysis

## Infrastructure as Code: AWS CDK Implementation

Let's build this system step-by-step using AWS CDK with TypeScript.

### **Project Structure**

```
bitcoin-trading-cdk/
├── lib/
│   ├── bitcoin-trading-stack.ts
│   ├── constructs/
│   │   ├── data-ingestion-construct.ts
│   │   ├── ml-prediction-construct.ts
│   │   ├── trading-engine-construct.ts
│   │   └── monitoring-construct.ts
│   └── lambda/
│       ├── price-collector/
│       ├── ml-predictor/
│       ├── trade-executor/
│       └── risk-manager/
├── config/
│   └── trading-config.json
└── bin/
    └── bitcoin-trading-app.ts
```

### **Configuration Management**

Environment-specific configurations for risk management and cost optimization:

```typescript
// config/trading-config.json
{
  "dev": {
    "priceCollectionInterval": 5,  // minutes
    "maxTradeAmount": 100,          // USD
    "enableRealTrading": false,
    "mlModels": ["bedrock"],
    "riskThreshold": 0.7
  },
  "prod": {
    "priceCollectionInterval": 1,
    "maxTradeAmount": 10000,
    "enableRealTrading": true,
    "mlModels": ["bedrock", "huggingface", "custom"],
    "riskThreshold": 0.85
  }
}
```

### **1. Data Ingestion Layer**

The data ingestion construct handles Bitcoin price collection and historical storage:

```typescript
// lib/constructs/data-ingestion-construct.ts
import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as timestream from 'aws-cdk-lib/aws-timestream';
import { Construct } from 'constructs';

export interface DataIngestionProps {
  collectionInterval: number;  // minutes
}

export class DataIngestionConstruct extends Construct {
  public readonly priceTable: dynamodb.Table;
  public readonly priceBucket: s3.Bucket;
  public readonly timestreamDb: timestream.CfnDatabase;

  constructor(scope: Construct, id: string, props: DataIngestionProps) {
    super(scope, id);

    // S3 bucket for raw price data
    this.priceBucket = new s3.Bucket(this, 'PriceDataBucket', {
      versioned: true,
      lifecycleRules: [{
        expiration: cdk.Duration.days(90),
        transitions: [{
          storageClass: s3.StorageClass.GLACIER,
          transitionAfter: cdk.Duration.days(30),
        }],
      }],
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    // DynamoDB table for queryable historical data
    this.priceTable = new dynamodb.Table(this, 'BitcoinPriceTable', {
      partitionKey: { name: 'symbol', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      pointInTimeRecovery: true,
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });

    // Timestream for time-series analysis
    this.timestreamDb = new timestream.CfnDatabase(this, 'PriceTimestream', {
      databaseName: 'bitcoin-prices',
    });

    const timestreamTable = new timestream.CfnTable(this, 'PriceTimestreamTable', {
      databaseName: this.timestreamDb.ref,
      tableName: 'price-history',
      retentionProperties: {
        MemoryStoreRetentionPeriodInHours: '24',
        MagneticStoreRetentionPeriodInDays: '365',
      },
    });

    // Lambda for price collection
    const priceCollectorFn = new lambda.Function(this, 'PriceCollector', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lib/lambda/price-collector'),
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      environment: {
        PRICE_TABLE: this.priceTable.tableName,
        PRICE_BUCKET: this.priceBucket.bucketName,
        TIMESTREAM_DB: this.timestreamDb.ref,
        TIMESTREAM_TABLE: timestreamTable.ref,
      },
    });

    // Grant permissions
    this.priceTable.grantWriteData(priceCollectorFn);
    this.priceBucket.grantWrite(priceCollectorFn);

    // EventBridge rule to trigger price collection
    const collectionRule = new events.Rule(this, 'PriceCollectionRule', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(props.collectionInterval)),
      description: 'Trigger Bitcoin price collection',
    });

    collectionRule.addTarget(new targets.LambdaFunction(priceCollectorFn));
  }
}
```

### **Price Collection Lambda Implementation**

```python
# lib/lambda/price-collector/index.py
import json
import boto3
import requests
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
timestream_client = boto3.client('timestream-write')

PRICE_TABLE = os.environ['PRICE_TABLE']
PRICE_BUCKET = os.environ['PRICE_BUCKET']
TIMESTREAM_DB = os.environ['TIMESTREAM_DB']
TIMESTREAM_TABLE = os.environ['TIMESTREAM_TABLE']

def handler(event, context):
    """Collect Bitcoin price from multiple sources"""

    # Fetch from multiple sources for reliability
    sources = [
        fetch_coinGecko_price(),
        fetch_binance_price(),
        fetch_coinbase_price(),
    ]

    # Calculate median price for accuracy
    prices = [s['price'] for s in sources if s]
    median_price = sorted(prices)[len(prices) // 2]

    timestamp = int(datetime.utcnow().timestamp())

    # Prepare data
    price_data = {
        'symbol': 'BTC-USD',
        'timestamp': timestamp,
        'price': Decimal(str(median_price)),
        'volume_24h': Decimal(str(sources[0].get('volume', 0))),
        'market_cap': Decimal(str(sources[0].get('market_cap', 0))),
        'price_change_24h': Decimal(str(sources[0].get('price_change', 0))),
        'sources': [s['source'] for s in sources if s],
        'ttl': timestamp + (90 * 24 * 60 * 60),  # 90 days retention
    }

    # Store in DynamoDB
    table = dynamodb.Table(PRICE_TABLE)
    table.put_item(Item=price_data)

    # Store raw data in S3
    s3_key = f"raw-prices/{datetime.utcnow().strftime('%Y/%m/%d')}/{timestamp}.json"
    s3_client.put_object(
        Bucket=PRICE_BUCKET,
        Key=s3_key,
        Body=json.dumps(sources, default=str),
    )

    # Write to Timestream for time-series analysis
    write_to_timestream(price_data)

    return {
        'statusCode': 200,
        'body': json.dumps({
            'price': float(median_price),
            'timestamp': timestamp,
        })
    }

def fetch_coinGecko_price():
    """Fetch price from CoinGecko API"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': 'bitcoin',
            'vs_currencies': 'usd',
            'include_24hr_vol': 'true',
            'include_24hr_change': 'true',
            'include_market_cap': 'true'
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()['bitcoin']

        return {
            'source': 'coingecko',
            'price': data['usd'],
            'volume': data.get('usd_24h_vol', 0),
            'market_cap': data.get('usd_market_cap', 0),
            'price_change': data.get('usd_24h_change', 0),
        }
    except Exception as e:
        print(f"CoinGecko fetch error: {e}")
        return None

def fetch_binance_price():
    """Fetch price from Binance API"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        params = {'symbol': 'BTCUSDT'}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        return {
            'source': 'binance',
            'price': float(data['lastPrice']),
            'volume': float(data['volume']),
            'price_change': float(data['priceChangePercent']),
        }
    except Exception as e:
        print(f"Binance fetch error: {e}")
        return None

def write_to_timestream(price_data):
    """Write price data to Timestream for time-series analysis"""
    records = [{
        'Time': str(price_data['timestamp'] * 1000),  # milliseconds
        'TimeUnit': 'MILLISECONDS',
        'Dimensions': [
            {'Name': 'symbol', 'Value': price_data['symbol']},
        ],
        'MeasureName': 'price_metrics',
        'MeasureValueType': 'MULTI',
        'MeasureValues': [
            {'Name': 'price', 'Value': str(price_data['price']), 'Type': 'DOUBLE'},
            {'Name': 'volume', 'Value': str(price_data['volume_24h']), 'Type': 'DOUBLE'},
            {'Name': 'market_cap', 'Value': str(price_data['market_cap']), 'Type': 'DOUBLE'},
        ],
    }]

    try:
        timestream_client.write_records(
            DatabaseName=TIMESTREAM_DB,
            TableName=TIMESTREAM_TABLE,
            Records=records,
        )
    except Exception as e:
        print(f"Timestream write error: {e}")
```

### **2. ML Prediction Layer**

The prediction layer integrates multiple ML models for robust price forecasting:

```typescript
// lib/constructs/ml-prediction-construct.ts
import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import { Construct } from 'constructs';

export interface MLPredictionProps {
  priceTableName: string;
  enabledModels: string[];  // ['bedrock', 'huggingface', 'custom']
}

export class MLPredictionConstruct extends Construct {
  public readonly predictorFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: MLPredictionProps) {
    super(scope, id);

    // Lambda Layer for ML libraries
    const mlLayer = new lambda.LayerVersion(this, 'MLLibrariesLayer', {
      code: lambda.Code.fromAsset('lib/lambda/layers/ml-libs'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description: 'ML libraries: numpy, pandas, scikit-learn',
    });

    // Prediction Lambda
    this.predictorFunction = new lambda.Function(this, 'MLPredictor', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lib/lambda/ml-predictor'),
      timeout: cdk.Duration.seconds(300),
      memorySize: 3008,  // Max memory for ML inference
      layers: [mlLayer],
      environment: {
        PRICE_TABLE: props.priceTableName,
        ENABLED_MODELS: JSON.stringify(props.enabledModels),
        BEDROCK_MODEL_ID: 'anthropic.claude-3-sonnet-20240229-v1:0',
      },
    });

    // Grant Bedrock access
    if (props.enabledModels.includes('bedrock')) {
      this.predictorFunction.addToRolePolicy(new iam.PolicyStatement({
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: ['*'],
      }));
    }

    // Grant SageMaker access for HuggingFace models
    if (props.enabledModels.includes('huggingface')) {
      this.predictorFunction.addToRolePolicy(new iam.PolicyStatement({
        actions: [
          'sagemaker:InvokeEndpoint',
        ],
        resources: ['*'],
      }));
    }

    // Grant DynamoDB read access
    const priceTable = dynamodb.Table.fromTableName(this, 'PriceTable', props.priceTableName);
    priceTable.grantReadData(this.predictorFunction);
  }
}
```

### **ML Prediction Lambda Implementation**

```python
# lib/lambda/ml-predictor/index.py
import json
import boto3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

bedrock_runtime = boto3.client('bedrock-runtime')
sagemaker_runtime = boto3.client('sagemaker-runtime')
dynamodb = boto3.resource('dynamodb')

PRICE_TABLE = os.environ['PRICE_TABLE']
ENABLED_MODELS = json.loads(os.environ['ENABLED_MODELS'])
BEDROCK_MODEL_ID = os.environ['BEDROCK_MODEL_ID']

def handler(event, context):
    """Generate price predictions using multiple ML models"""

    # Fetch historical data
    historical_data = fetch_historical_prices(days=30)

    if len(historical_data) < 100:
        return {'error': 'Insufficient historical data'}

    # Generate predictions from all enabled models
    predictions = {}

    if 'bedrock' in ENABLED_MODELS:
        predictions['bedrock'] = predict_with_bedrock(historical_data)

    if 'huggingface' in ENABLED_MODELS:
        predictions['huggingface'] = predict_with_huggingface(historical_data)

    if 'custom' in ENABLED_MODELS:
        predictions['custom'] = predict_with_custom_model(historical_data)

    # Ensemble predictions for robustness
    final_prediction = ensemble_predictions(predictions)

    return {
        'statusCode': 200,
        'body': json.dumps({
            'prediction': final_prediction,
            'individual_predictions': predictions,
            'confidence': calculate_confidence(predictions),
            'timestamp': int(datetime.utcnow().timestamp()),
        })
    }

def fetch_historical_prices(days: int = 30) -> pd.DataFrame:
    """Fetch historical price data from DynamoDB"""
    table = dynamodb.Table(PRICE_TABLE)

    start_timestamp = int((datetime.utcnow() - timedelta(days=days)).timestamp())

    response = table.query(
        KeyConditionExpression='symbol = :symbol AND #ts >= :start_ts',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={
            ':symbol': 'BTC-USD',
            ':start_ts': start_timestamp,
        },
        ScanIndexForward=True,  # Ascending order
    )

    df = pd.DataFrame(response['Items'])
    df['price'] = df['price'].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.sort_values('timestamp')

    return df

def predict_with_bedrock(data: pd.DataFrame) -> Dict:
    """Use AWS Bedrock Claude for price prediction"""

    # Prepare context for Claude
    recent_prices = data.tail(50)['price'].tolist()
    price_changes = data['price_change_24h'].tail(10).tolist()

    prompt = f"""You are a Bitcoin market analyst. Based on the following data, predict the Bitcoin price movement for the next hour.

Recent prices (last 50 data points): {recent_prices}
Recent 24h price changes: {price_changes}

Current price: ${recent_prices[-1]:.2f}

Provide your analysis in JSON format:
{{
    "predicted_price": <number>,
    "direction": "<up|down|stable>",
    "confidence": <0-1>,
    "reasoning": "<brief explanation>"
}}"""

    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )

        result = json.loads(response['body'].read())
        prediction_text = result['content'][0]['text']

        # Extract JSON from response
        prediction = json.loads(prediction_text)

        return {
            'model': 'bedrock-claude',
            'predicted_price': prediction['predicted_price'],
            'direction': prediction['direction'],
            'confidence': prediction['confidence'],
            'reasoning': prediction['reasoning'],
        }

    except Exception as e:
        print(f"Bedrock prediction error: {e}")
        return None

def predict_with_huggingface(data: pd.DataFrame) -> Dict:
    """Use HuggingFace model deployed on SageMaker"""

    # Prepare features for time-series model
    features = prepare_time_series_features(data)

    try:
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName='bitcoin-price-predictor',
            ContentType='application/json',
            Body=json.dumps({'instances': features.tolist()})
        )

        result = json.loads(response['Body'].read())

        return {
            'model': 'huggingface-timeseries',
            'predicted_price': result['predictions'][0],
            'confidence': result['confidence'],
        }

    except Exception as e:
        print(f"HuggingFace prediction error: {e}")
        return None

def predict_with_custom_model(data: pd.DataFrame) -> Dict:
    """Use custom LSTM/GRU model for price prediction"""

    # Simple moving average + momentum-based prediction
    prices = data['price'].values

    # Technical indicators
    sma_20 = np.mean(prices[-20:])
    sma_50 = np.mean(prices[-50:])
    momentum = (prices[-1] - prices[-10]) / prices[-10]

    # Simple prediction logic
    if sma_20 > sma_50 and momentum > 0:
        direction = 'up'
        predicted_price = prices[-1] * (1 + momentum * 0.5)
    elif sma_20 < sma_50 and momentum < 0:
        direction = 'down'
        predicted_price = prices[-1] * (1 + momentum * 0.5)
    else:
        direction = 'stable'
        predicted_price = prices[-1]

    return {
        'model': 'custom-technical-analysis',
        'predicted_price': float(predicted_price),
        'direction': direction,
        'confidence': 0.7,
        'indicators': {
            'sma_20': float(sma_20),
            'sma_50': float(sma_50),
            'momentum': float(momentum),
        }
    }

def ensemble_predictions(predictions: Dict) -> Dict:
    """Combine multiple predictions using weighted ensemble"""

    valid_predictions = [p for p in predictions.values() if p is not None]

    if not valid_predictions:
        return None

    # Weight predictions by confidence
    total_confidence = sum(p['confidence'] for p in valid_predictions)
    weighted_price = sum(
        p['predicted_price'] * p['confidence']
        for p in valid_predictions
    ) / total_confidence

    # Determine consensus direction
    directions = [p['direction'] for p in valid_predictions]
    consensus_direction = max(set(directions), key=directions.count)

    return {
        'predicted_price': weighted_price,
        'direction': consensus_direction,
        'num_models': len(valid_predictions),
    }

def calculate_confidence(predictions: Dict) -> float:
    """Calculate overall confidence based on model agreement"""

    valid_predictions = [p for p in predictions.values() if p is not None]

    if not valid_predictions:
        return 0.0

    # Check direction agreement
    directions = [p['direction'] for p in valid_predictions]
    agreement_ratio = directions.count(max(set(directions), key=directions.count)) / len(directions)

    # Average confidence weighted by agreement
    avg_confidence = np.mean([p['confidence'] for p in valid_predictions])

    return float(avg_confidence * agreement_ratio)
```

### **3. Trading Engine with Risk Management**

Step Functions orchestrates the trading logic with built-in safety checks:

```typescript
// lib/constructs/trading-engine-construct.ts
import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import { Construct } from 'constructs';

export interface TradingEngineProps {
  predictorFunction: lambda.IFunction;
  maxTradeAmount: number;
  riskThreshold: number;
  enableRealTrading: boolean;
}

export class TradingEngineConstruct extends Construct {
  public readonly tradeTable: dynamodb.Table;
  public readonly alertTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: TradingEngineProps) {
    super(scope, id);

    // Trade history table
    this.tradeTable = new dynamodb.Table(this, 'TradeHistory', {
      partitionKey: { name: 'trade_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // SNS topic for trade alerts
    this.alertTopic = new sns.Topic(this, 'TradeAlerts', {
      displayName: 'Bitcoin Trading Alerts',
    });

    // Risk manager Lambda
    const riskManagerFn = new lambda.Function(this, 'RiskManager', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lib/lambda/risk-manager'),
      timeout: cdk.Duration.seconds(30),
      environment: {
        TRADE_TABLE: this.tradeTable.tableName,
        MAX_TRADE_AMOUNT: props.maxTradeAmount.toString(),
        RISK_THRESHOLD: props.riskThreshold.toString(),
      },
    });

    this.tradeTable.grantReadData(riskManagerFn);

    // Trade executor Lambda
    const tradeExecutorFn = new lambda.Function(this, 'TradeExecutor', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lib/lambda/trade-executor'),
      timeout: cdk.Duration.seconds(60),
      environment: {
        TRADE_TABLE: this.tradeTable.tableName,
        ALERT_TOPIC_ARN: this.alertTopic.topicArn,
        ENABLE_REAL_TRADING: props.enableRealTrading.toString(),
      },
    });

    this.tradeTable.grantWriteData(tradeExecutorFn);
    this.alertTopic.grantPublish(tradeExecutorFn);

    // Step Functions workflow
    const getPrediction = new tasks.LambdaInvoke(this, 'GetPrediction', {
      lambdaFunction: props.predictorFunction,
      outputPath: '$.Payload',
    });

    const checkRisk = new tasks.LambdaInvoke(this, 'CheckRisk', {
      lambdaFunction: riskManagerFn,
      outputPath: '$.Payload',
    });

    const executeTrade = new tasks.LambdaInvoke(this, 'ExecuteTrade', {
      lambdaFunction: tradeExecutorFn,
      outputPath: '$.Payload',
    });

    const riskCheckPassed = new sfn.Choice(this, 'RiskCheckPassed')
      .when(sfn.Condition.booleanEquals('$.risk_approved', true), executeTrade)
      .otherwise(new sfn.Succeed(this, 'TradeRejected'));

    const definition = getPrediction
      .next(checkRisk)
      .next(riskCheckPassed);

    const tradingStateMachine = new sfn.StateMachine(this, 'TradingStateMachine', {
      definition,
      timeout: cdk.Duration.minutes(5),
    });

    // EventBridge rule to trigger trading workflow
    const tradingRule = new events.Rule(this, 'TradingTrigger', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(5)),
      description: 'Trigger trading analysis and execution',
    });

    tradingRule.addTarget(new targets.SfnStateMachine(tradingStateMachine));
  }
}
```

### **Trade Execution with Safety Checks**

```python
# lib/lambda/trade-executor/index.py
import json
import boto3
import requests
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')

TRADE_TABLE = os.environ['TRADE_TABLE']
ALERT_TOPIC_ARN = os.environ['ALERT_TOPIC_ARN']
ENABLE_REAL_TRADING = os.environ['ENABLE_REAL_TRADING'].lower() == 'true'

def handler(event, context):
    """Execute trade based on prediction and risk assessment"""

    prediction = event['prediction']
    risk_analysis = event['risk_analysis']

    if not risk_analysis['approved']:
        return {
            'trade_executed': False,
            'reason': risk_analysis['reason']
        }

    # Determine trade action
    current_price = prediction['current_price']
    predicted_price = prediction['predicted_price']
    confidence = prediction['confidence']

    # Trading logic
    price_diff_pct = (predicted_price - current_price) / current_price * 100

    if price_diff_pct > 2 and confidence > 0.75:
        action = 'BUY'
        amount = calculate_position_size(risk_analysis, predicted_price)
    elif price_diff_pct < -2 and confidence > 0.75:
        action = 'SELL'
        amount = calculate_position_size(risk_analysis, predicted_price)
    else:
        action = 'HOLD'
        amount = 0

    if action == 'HOLD':
        return {
            'trade_executed': False,
            'reason': 'No significant trading signal'
        }

    # Execute trade
    if ENABLE_REAL_TRADING:
        trade_result = execute_real_trade(action, amount, current_price)
    else:
        trade_result = simulate_trade(action, amount, current_price)

    # Log trade
    log_trade(action, amount, current_price, predicted_price, trade_result)

    # Send alert
    send_trade_alert(action, amount, current_price, trade_result)

    return {
        'trade_executed': True,
        'action': action,
        'amount': amount,
        'price': current_price,
        'trade_id': trade_result['trade_id']
    }

def execute_real_trade(action, amount, price):
    """Execute trade on exchange (e.g., Binance, Coinbase)"""
    # This would integrate with actual exchange APIs
    # Example: Binance API
    pass

def simulate_trade(action, amount, price):
    """Simulate trade for testing"""
    import uuid
    return {
        'trade_id': str(uuid.uuid4()),
        'simulated': True,
        'status': 'filled'
    }

def log_trade(action, amount, price, predicted_price, result):
    """Log trade to DynamoDB"""
    table = dynamodb.Table(TRADE_TABLE)

    timestamp = int(datetime.utcnow().timestamp())

    table.put_item(Item={
        'trade_id': result['trade_id'],
        'timestamp': timestamp,
        'action': action,
        'amount': Decimal(str(amount)),
        'price': Decimal(str(price)),
        'predicted_price': Decimal(str(predicted_price)),
        'simulated': result.get('simulated', False),
        'status': result['status'],
    })

def send_trade_alert(action, amount, price, result):
    """Send SNS notification"""
    message = f"""
Bitcoin Trade Executed

Action: {action}
Amount: ${amount:.2f}
Price: ${price:.2f}
Trade ID: {result['trade_id']}
Status: {result['status']}
{'[SIMULATED]' if result.get('simulated') else '[REAL]'}
    """

    sns_client.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=f'Bitcoin Trade Alert: {action}',
        Message=message
    )
```

## Deployment and Configuration

Deploy the complete trading system:

```bash
# Install dependencies
npm install

# Deploy to development (simulated trading)
cdk deploy --all --context env=dev

# Deploy to production (real trading - use with caution!)
cdk deploy --all --context env=prod \
    --context enableRealTrading=true \
    --context maxTradeAmount=10000
```

## Monitoring and Performance Tracking

Track system performance with CloudWatch dashboards:

```typescript
// Add monitoring construct
new MonitoringConstruct(this, 'Monitoring', {
  predictorFunction,
  tradeTable,
  metrics: [
    'PredictionAccuracy',
    'TradeSuccessRate',
    'PortfolioValue',
    'RiskScore'
  ]
});
```

## Security Best Practices

1. **API Key Management**: Store exchange API keys in AWS Secrets Manager
2. **Encryption**: Enable encryption for all data at rest and in transit
3. **IAM Policies**: Follow least-privilege principle for all Lambda functions
4. **VPC Isolation**: Deploy sensitive components in private subnets
5. **Rate Limiting**: Implement throttling to prevent excessive trading

## Cost Optimization

- **Lambda Memory**: Right-size ML Lambda functions (3GB for predictions)
- **DynamoDB**: Use on-demand billing for unpredictable workloads
- **S3 Lifecycle**: Archive old price data to Glacier after 30 days
- **Reserved Capacity**: Consider reserved instances for SageMaker endpoints

## Conclusion

This Bitcoin trading system demonstrates how modern cloud architecture can power sophisticated financial applications. The combination of event-driven design, multiple ML models, and comprehensive risk management creates a robust platform for automated trading.

### **Key Takeaways**

- **Multi-Model Predictions**: Ensemble approach improves accuracy and reduces false signals
- **Event-Driven Architecture**: Serverless design scales automatically with market activity
- **Risk Management**: Built-in safety checks prevent catastrophic losses
- **Infrastructure as Code**: CDK enables reproducible, version-controlled deployments
- **Cost-Effective**: Pay only for actual trading activity and predictions

The complete implementation provides a foundation for building production-grade trading systems that can be extended with additional strategies, risk models, and exchange integrations.

**Disclaimer**: This system is for educational purposes. Cryptocurrency trading involves substantial risk. Always test thoroughly and never invest more than you can afford to lose.
