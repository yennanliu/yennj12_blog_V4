---
title: "Building a Serverless URL Shortener: Architecture Decisions and AWS CDK Implementation"
date: 2025-08-10T15:55:00+08:00
draft: false
authors: ["yen"]
categories: ["engineering", "architecture"]
tags: ["serverless", "aws", "cdk", "dynamodb", "lambda", "api-gateway"]
summary: "Deep dive into designing and building a production-ready URL shortener using AWS serverless services, exploring architectural tradeoffs, and implementing with AWS CDK."
readTime: "18 min"
---

Building a URL shortener might seem straightforward, but designing one that scales to millions of requests while maintaining reliability and performance requires careful architectural decisions. This post explores the design choices, tradeoffs, and implementation details of a serverless URL shortener built with AWS CDK.

## The Challenge: More Than Just Shortened URLs

URL shorteners like bit.ly and tinyurl.com handle billions of requests daily. While the core functionality is simple—mapping short codes to long URLs—production systems must address:

- **Scale**: Handling millions of requests per day
- **Availability**: 99.9%+ uptime for critical link infrastructure
- **Performance**: Sub-100ms response times globally
- **Cost Efficiency**: Economical at scale with unpredictable traffic
- **Analytics**: Click tracking and usage metrics
- **Security**: Preventing abuse and malicious links

Let's explore how serverless architecture addresses these challenges.

## Architecture Overview

Our URL shortener uses a fully serverless approach with these AWS services:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│   CloudFront│    │ API Gateway  │    │   Lambda    │    │  DynamoDB   │
│             │───▶│              │───▶│             │───▶│             │
│ (CDN + UI)  │    │ (REST API)   │    │ (Business   │    │ (Data Store)│
└─────────────┘    └──────────────┘    │  Logic)     │    └─────────────┘
                                       └─────────────┘
                                              │
                                              ▼
                                      ┌─────────────┐
                                      │ CloudWatch  │
                                      │ (Monitoring)│
                                      └─────────────┘
```

### Core Components

1. **API Gateway**: RESTful API endpoints for URL operations
2. **Lambda Functions**: Business logic for shortening and expanding URLs  
3. **DynamoDB**: NoSQL database for storing URL mappings
4. **CloudFront**: Global CDN for the web interface
5. **S3**: Static website hosting for the frontend

## CDK Infrastructure Implementation

### DynamoDB Table Design

The heart of our system is the DynamoDB table structure:

```typescript
// lib/url-shortener-stack.ts
const urlTable = new dynamodb.Table(this, 'UrlTable', {
  tableName: 'url-shortener-table',
  partitionKey: { 
    name: 'shortCode', 
    type: dynamodb.AttributeType.STRING 
  },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecovery: true,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
  
  // Global Secondary Index for reverse lookups
  globalSecondaryIndexes: [{
    indexName: 'originalUrl-index',
    partitionKey: { 
      name: 'originalUrl', 
      type: dynamodb.AttributeType.STRING 
    },
    projectionType: dynamodb.ProjectionType.ALL,
  }]
});

// Add TTL for automatic cleanup
urlTable.addGlobalSecondaryIndex({
  indexName: 'ttl-index',
  partitionKey: { 
    name: 'ttlExpiry', 
    type: dynamodb.AttributeType.NUMBER 
  },
  sortKey: { 
    name: 'shortCode', 
    type: dynamodb.AttributeType.STRING 
  }
});
```

**Key Design Decisions:**

- **Partition Key**: `shortCode` ensures even distribution and fast lookups
- **GSI**: `originalUrl` index prevents duplicate shortened URLs
- **TTL**: Automatic cleanup of expired URLs
- **Pay-per-request**: Cost-effective for unpredictable traffic patterns

### Lambda Functions Architecture

Our system uses multiple Lambda functions for different responsibilities:

```typescript
// URL Shortening Function
const shortenFunction = new lambda.Function(this, 'ShortenFunction', {
  runtime: lambda.Runtime.NODEJS_18_X,
  handler: 'shorten.handler',
  code: lambda.Code.fromAsset('lambda'),
  environment: {
    TABLE_NAME: urlTable.tableName,
    BASE_URL: props.domainName || api.url
  },
  timeout: cdk.Duration.seconds(30),
  memorySize: 256,
});

// URL Expansion Function  
const expandFunction = new lambda.Function(this, 'ExpandFunction', {
  runtime: lambda.Runtime.NODEJS_18_X,
  handler: 'expand.handler',
  code: lambda.Code.fromAsset('lambda'),
  environment: {
    TABLE_NAME: urlTable.tableName
  },
  timeout: cdk.Duration.seconds(10),
  memorySize: 128,
});

// Analytics Function
const analyticsFunction = new lambda.Function(this, 'AnalyticsFunction', {
  runtime: lambda.Runtime.NODEJS_18_X,
  handler: 'analytics.handler',
  code: lambda.Code.fromAsset('lambda'),
  environment: {
    TABLE_NAME: urlTable.tableName
  }
});
```

## Short Code Generation Algorithm

One of the most critical design decisions is the short code generation strategy:

```javascript
// lambda/shorten.js
const crypto = require('crypto');

class ShortCodeGenerator {
  constructor() {
    // Base62 encoding for URL-safe characters
    this.charset = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
    this.base = this.charset.length; // 62
  }

  // Counter-based approach with randomization
  generateShortCode(counter = Date.now()) {
    let result = '';
    let num = counter;
    
    // Add randomness to prevent predictability
    const random = crypto.randomInt(0, 1000);
    num = (num * 1000) + random;
    
    // Convert to base62
    while (num > 0) {
      result = this.charset[num % this.base] + result;
      num = Math.floor(num / this.base);
    }
    
    // Ensure minimum length of 6 characters
    while (result.length < 6) {
      result = this.charset[0] + result;
    }
    
    return result;
  }

  // Hash-based approach for deterministic codes
  generateHashBasedCode(url) {
    const hash = crypto
      .createHash('md5')
      .update(url)
      .digest('hex');
    
    // Take first 8 characters and convert to base62
    let num = parseInt(hash.substring(0, 8), 16);
    let result = '';
    
    while (num > 0 && result.length < 7) {
      result = this.charset[num % this.base] + result;
      num = Math.floor(num / this.base);
    }
    
    return result || this.charset[0].repeat(6);
  }
}

// Usage in Lambda handler
exports.handler = async (event) => {
  const { originalUrl, customCode, expiryDays } = JSON.parse(event.body);
  const generator = new ShortCodeGenerator();
  
  let shortCode;
  if (customCode) {
    // Validate custom code availability
    shortCode = customCode;
  } else {
    // Generate unique code with retry logic
    let attempts = 0;
    const maxAttempts = 5;
    
    do {
      shortCode = generator.generateShortCode();
      attempts++;
      
      // Check if code already exists
      const existingItem = await dynamodb.getItem({
        TableName: process.env.TABLE_NAME,
        Key: { shortCode: { S: shortCode } }
      }).promise();
      
      if (!existingItem.Item) break;
      
    } while (attempts < maxAttempts);
    
    if (attempts >= maxAttempts) {
      throw new Error('Failed to generate unique short code');
    }
  }
  
  // Store in DynamoDB with TTL
  const ttlExpiry = expiryDays ? 
    Math.floor(Date.now() / 1000) + (expiryDays * 24 * 60 * 60) : 
    null;
    
  await dynamodb.putItem({
    TableName: process.env.TABLE_NAME,
    Item: {
      shortCode: { S: shortCode },
      originalUrl: { S: originalUrl },
      createdAt: { S: new Date().toISOString() },
      clickCount: { N: '0' },
      ...(ttlExpiry && { ttlExpiry: { N: ttlExpiry.toString() } })
    },
    ConditionExpression: 'attribute_not_exists(shortCode)'
  }).promise();
  
  return {
    statusCode: 201,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*'
    },
    body: JSON.stringify({
      shortCode,
      shortUrl: `${process.env.BASE_URL}/${shortCode}`,
      originalUrl,
      expiresAt: ttlExpiry ? new Date(ttlExpiry * 1000).toISOString() : null
    })
  };
};
```

## URL Expansion with Analytics

The expansion function handles redirects and tracks analytics:

```javascript
// lambda/expand.js
const AWS = require('aws-sdk');
const dynamodb = new AWS.DynamoDB();

exports.handler = async (event) => {
  const shortCode = event.pathParameters.shortCode;
  const userAgent = event.headers['User-Agent'] || 'Unknown';
  const sourceIp = event.requestContext.identity.sourceIp;
  const referer = event.headers.Referer || event.headers.referer || 'Direct';

  try {
    // Get URL mapping with consistent read
    const result = await dynamodb.getItem({
      TableName: process.env.TABLE_NAME,
      Key: { shortCode: { S: shortCode } },
      ConsistentRead: true
    }).promise();

    if (!result.Item) {
      return {
        statusCode: 404,
        headers: { 'Content-Type': 'text/html' },
        body: `
          <html>
            <head><title>Link Not Found</title></head>
            <body>
              <h1>404 - Short link not found</h1>
              <p>The link you're looking for doesn't exist or has expired.</p>
            </body>
          </html>
        `
      };
    }

    const originalUrl = result.Item.originalUrl.S;
    const currentCount = parseInt(result.Item.clickCount?.N || '0');

    // Atomic counter increment for analytics
    await dynamodb.updateItem({
      TableName: process.env.TABLE_NAME,
      Key: { shortCode: { S: shortCode } },
      UpdateExpression: 'ADD clickCount :increment SET lastAccessedAt = :timestamp',
      ExpressionAttributeValues: {
        ':increment': { N: '1' },
        ':timestamp': { S: new Date().toISOString() }
      }
    }).promise();

    // Log detailed analytics (could be sent to CloudWatch or separate analytics service)
    console.log(JSON.stringify({
      event: 'url_accessed',
      shortCode,
      originalUrl,
      userAgent,
      sourceIp,
      referer,
      timestamp: new Date().toISOString(),
      clickCount: currentCount + 1
    }));

    // Perform 301 redirect
    return {
      statusCode: 301,
      headers: {
        Location: originalUrl,
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      }
    };

  } catch (error) {
    console.error('Error expanding URL:', error);
    
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: 'Internal server error',
        message: 'Failed to process short URL'
      })
    };
  }
};
```

## API Gateway Configuration

Setting up the REST API with proper routing and CORS:

```typescript
// API Gateway setup with custom domain
const api = new apigateway.RestApi(this, 'UrlShortenerApi', {
  restApiName: 'URL Shortener Service',
  description: 'Serverless URL shortener API',
  defaultCorsPreflightOptions: {
    allowOrigins: apigateway.Cors.ALL_ORIGINS,
    allowMethods: apigateway.Cors.ALL_METHODS,
    allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key']
  },
  deployOptions: {
    stageName: 'prod',
    throttlingRateLimit: 1000,
    throttlingBurstLimit: 2000,
    metricsEnabled: true,
    loggingLevel: apigateway.MethodLoggingLevel.INFO
  }
});

// API Routes
const urlsResource = api.root.addResource('urls');

// POST /urls - Create short URL  
urlsResource.addMethod('POST', new apigateway.LambdaIntegration(shortenFunction), {
  requestValidator: new apigateway.RequestValidator(this, 'RequestValidator', {
    restApi: api,
    validateRequestBody: true,
    validateRequestParameters: true
  }),
  requestModels: {
    'application/json': new apigateway.Model(this, 'ShortenModel', {
      restApi: api,
      contentType: 'application/json',
      schema: {
        type: apigateway.JsonSchemaType.OBJECT,
        properties: {
          originalUrl: { 
            type: apigateway.JsonSchemaType.STRING,
            pattern: '^https?://.+',
            minLength: 1,
            maxLength: 2048
          },
          customCode: {
            type: apigateway.JsonSchemaType.STRING,
            pattern: '^[a-zA-Z0-9]{3,20}$'
          },
          expiryDays: {
            type: apigateway.JsonSchemaType.NUMBER,
            minimum: 1,
            maximum: 365
          }
        },
        required: ['originalUrl']
      }
    })
  }
});

// GET /{shortCode} - Redirect to original URL
const shortCodeResource = api.root.addResource('{shortCode}');
shortCodeResource.addMethod('GET', new apigateway.LambdaIntegration(expandFunction));

// GET /analytics/{shortCode} - Get URL analytics
const analyticsResource = api.root.addResource('analytics');
analyticsResource.addResource('{shortCode}')
  .addMethod('GET', new apigateway.LambdaIntegration(analyticsFunction));
```

## Frontend Implementation

A simple but functional web interface:

```html
<!-- ui/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URL Shortener</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: #f5f5f5;
        }
        .container {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .form-group {
            margin-bottom: 1rem;
        }
        label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }
        input[type="text"], input[type="number"] {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 1rem;
        }
        button {
            background: #007bff;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }
        button:hover {
            background: #0056b3;
        }
        .result {
            margin-top: 1rem;
            padding: 1rem;
            background: #e7f3ff;
            border-radius: 4px;
            border-left: 4px solid #007bff;
        }
        .error {
            background: #ffe7e7;
            border-left-color: #dc3545;
        }
        .loading {
            opacity: 0.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>URL Shortener</h1>
        
        <form id="urlForm">
            <div class="form-group">
                <label for="originalUrl">Original URL:</label>
                <input type="text" id="originalUrl" placeholder="https://example.com" required>
            </div>
            
            <div class="form-group">
                <label for="customCode">Custom Short Code (optional):</label>
                <input type="text" id="customCode" placeholder="my-link" pattern="[a-zA-Z0-9]{3,20}">
            </div>
            
            <div class="form-group">
                <label for="expiryDays">Expiry (days, optional):</label>
                <input type="number" id="expiryDays" placeholder="30" min="1" max="365">
            </div>
            
            <button type="submit" id="submitBtn">Shorten URL</button>
        </form>
        
        <div id="result" style="display: none;"></div>
    </div>

    <script>
        const API_BASE_URL = 'YOUR_API_GATEWAY_URL'; // Replace with actual API URL
        
        document.getElementById('urlForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = document.getElementById('submitBtn');
            const result = document.getElementById('result');
            
            submitBtn.textContent = 'Shortening...';
            submitBtn.disabled = true;
            result.style.display = 'none';
            
            const formData = {
                originalUrl: document.getElementById('originalUrl').value,
                customCode: document.getElementById('customCode').value || undefined,
                expiryDays: parseInt(document.getElementById('expiryDays').value) || undefined
            };
            
            try {
                const response = await fetch(`${API_BASE_URL}/urls`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    result.innerHTML = `
                        <strong>Success!</strong><br>
                        <strong>Short URL:</strong> 
                        <a href="${data.shortUrl}" target="_blank">${data.shortUrl}</a><br>
                        <strong>Original URL:</strong> ${data.originalUrl}<br>
                        ${data.expiresAt ? `<strong>Expires:</strong> ${new Date(data.expiresAt).toLocaleDateString()}` : ''}
                    `;
                    result.className = 'result';
                    document.getElementById('urlForm').reset();
                } else {
                    throw new Error(data.error || 'Failed to create short URL');
                }
                
            } catch (error) {
                result.innerHTML = `<strong>Error:</strong> ${error.message}`;
                result.className = 'result error';
            } finally {
                result.style.display = 'block';
                submitBtn.textContent = 'Shorten URL';
                submitBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
```

## Architecture Tradeoffs Analysis

### Serverless vs. Traditional Architecture

**Advantages of Serverless:**
- **Cost**: Pay only for actual usage, not idle time
- **Scalability**: Automatic scaling from 0 to millions of requests
- **Maintenance**: No server management or patching
- **Reliability**: Built-in redundancy and fault tolerance

**Disadvantages:**
- **Cold Starts**: 100-500ms latency for first request
- **Vendor Lock-in**: Tight coupling to AWS services
- **Debugging**: Limited local development and debugging tools
- **State**: Stateless architecture requires external storage for all data

### DynamoDB vs. Relational Database

**Why DynamoDB:**
```javascript
// DynamoDB advantages for URL shortener:
const advantages = {
  performance: 'Single-digit millisecond latency',
  scalability: 'Handles millions of requests automatically',
  availability: '99.99% uptime SLA',
  cost: 'Pay per request, no idle costs',
  integration: 'Native AWS service integration'
};

// Tradeoffs:
const tradeoffs = {
  queries: 'Limited query patterns, no JOINs',
  consistency: 'Eventually consistent by default',
  learning_curve: 'NoSQL data modeling required',
  analytics: 'Complex aggregations require additional processing'
};
```

**Alternative: RDS with Aurora Serverless**
```sql
-- Traditional SQL approach
CREATE TABLE urls (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  short_code VARCHAR(20) UNIQUE NOT NULL,
  original_url TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NULL,
  click_count INT DEFAULT 0,
  INDEX idx_short_code (short_code),
  INDEX idx_expires (expires_at)
);

-- Better for complex analytics
SELECT 
  DATE(created_at) as date,
  COUNT(*) as urls_created,
  SUM(click_count) as total_clicks
FROM urls 
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at);
```

### API Gateway vs. Application Load Balancer

**API Gateway Benefits:**
- Built-in authentication and authorization
- Request/response transformation
- Rate limiting and throttling
- Automatic API documentation
- Direct Lambda integration

**Cost Comparison:**
```javascript
// API Gateway pricing (simplified)
const apiGatewayMonthly = {
  requests: 10_000_000, // 10M requests
  cost_per_million: 3.50,
  total: 35 // $35/month
};

// ALB + EC2 alternative
const albMonthly = {
  alb_hours: 24 * 30, // Always running
  cost_per_hour: 0.0225,
  requests: 10_000_000,
  cost_per_million_lcu: 0.008,
  total: 16.2 + 80 // ~$96/month (ALB + small EC2)
};
```

## Performance Optimizations

### DynamoDB Optimization

```javascript
// Batch operations for analytics
const batchWriteAnalytics = async (events) => {
  const chunks = chunk(events, 25); // DynamoDB batch limit
  
  for (const eventChunk of chunks) {
    const putRequests = eventChunk.map(event => ({
      PutRequest: {
        Item: {
          shortCode: { S: event.shortCode },
          timestamp: { S: event.timestamp },
          userAgent: { S: event.userAgent },
          sourceIp: { S: event.sourceIp },
          referer: { S: event.referer }
        }
      }
    }));
    
    await dynamodb.batchWriteItem({
      RequestItems: {
        [ANALYTICS_TABLE]: putRequests
      }
    }).promise();
  }
};

// Connection pooling for better performance
const https = require('https');
const agent = new https.Agent({
  keepAlive: true,
  maxSockets: 50
});

AWS.config.update({
  httpOptions: { agent }
});
```

### Lambda Optimization

```javascript
// Connection reuse across invocations
let dynamodbClient;

exports.handler = async (event) => {
  // Initialize client outside handler for connection reuse
  if (!dynamodbClient) {
    dynamodbClient = new AWS.DynamoDB.DocumentClient({
      maxRetries: 3,
      retryDelayOptions: {
        customBackoff: (retryCount) => Math.pow(2, retryCount) * 100
      }
    });
  }
  
  // Warm-up logic to prevent cold starts
  if (event.source === 'aws.events') {
    return { statusCode: 200, body: 'Warm-up successful' };
  }
  
  // Main business logic
  return processRequest(event);
};

// CloudWatch Events for Lambda warming
const warmingRule = new events.Rule(this, 'WarmingRule', {
  schedule: events.Schedule.rate(cdk.Duration.minutes(5))
});

warmingRule.addTarget(new targets.LambdaFunction(shortenFunction));
```

## Security Considerations

### Input Validation and Sanitization

```javascript
const validateAndSanitizeUrl = (url) => {
  // URL validation
  try {
    const parsedUrl = new URL(url);
    
    // Whitelist allowed protocols
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      throw new Error('Only HTTP and HTTPS URLs are allowed');
    }
    
    // Block internal/private networks
    const hostname = parsedUrl.hostname;
    if (
      hostname === 'localhost' ||
      hostname.startsWith('192.168.') ||
      hostname.startsWith('10.') ||
      hostname.startsWith('172.16.') ||
      hostname === '127.0.0.1'
    ) {
      throw new Error('Private network URLs are not allowed');
    }
    
    // Length validation
    if (url.length > 2048) {
      throw new Error('URL too long');
    }
    
    return parsedUrl.toString();
    
  } catch (error) {
    throw new Error(`Invalid URL: ${error.message}`);
  }
};

// Rate limiting per IP
const rateLimiter = new Map();

const checkRateLimit = (sourceIp, limit = 100, windowMs = 3600000) => {
  const now = Date.now();
  const windowStart = now - windowMs;
  
  if (!rateLimiter.has(sourceIp)) {
    rateLimiter.set(sourceIp, []);
  }
  
  const requests = rateLimiter.get(sourceIp);
  const recentRequests = requests.filter(timestamp => timestamp > windowStart);
  
  if (recentRequests.length >= limit) {
    throw new Error('Rate limit exceeded');
  }
  
  recentRequests.push(now);
  rateLimiter.set(sourceIp, recentRequests);
};
```

### Malicious URL Detection

```javascript
// Integration with URL scanning services
const scanUrl = async (url) => {
  const scanResult = await axios.post('https://urlscan.io/api/v1/scan/', {
    url: url,
    visibility: 'private'
  }, {
    headers: {
      'API-Key': process.env.URLSCAN_API_KEY
    }
  });
  
  // Wait for scan results
  await new Promise(resolve => setTimeout(resolve, 10000));
  
  const result = await axios.get(scanResult.data.api);
  
  if (result.data.verdicts.overall.malicious) {
    throw new Error('Malicious URL detected');
  }
  
  return result.data;
};
```

## Monitoring and Observability

### CloudWatch Metrics and Alarms

```typescript
// Custom metrics for business logic
const urlCreationMetric = new cloudwatch.Metric({
  namespace: 'URLShortener',
  metricName: 'UrlsCreated',
  statistic: 'Sum'
});

const urlAccessMetric = new cloudwatch.Metric({
  namespace: 'URLShortener', 
  metricName: 'UrlsAccessed',
  statistic: 'Sum'
});

// Alarms for critical thresholds
new cloudwatch.Alarm(this, 'HighErrorRateAlarm', {
  metric: api.metricClientError(),
  threshold: 10,
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
});

new cloudwatch.Alarm(this, 'DynamoDBThrottleAlarm', {
  metric: urlTable.metricThrottleEvents(),
  threshold: 1,
  evaluationPeriods: 1
});
```

### Distributed Tracing

```javascript
// X-Ray integration for request tracing
const AWSXRay = require('aws-xray-sdk-core');
const AWS = AWSXRay.captureAWS(require('aws-sdk'));

exports.handler = async (event) => {
  const segment = AWSXRay.getSegment();
  const subsegment = segment.addNewSubsegment('url-processing');
  
  try {
    subsegment.addAnnotation('shortCode', shortCode);
    subsegment.addMetadata('requestInfo', {
      userAgent: event.headers['User-Agent'],
      sourceIp: event.requestContext.identity.sourceIp
    });
    
    const result = await processUrlRequest(event);
    subsegment.close();
    return result;
    
  } catch (error) {
    subsegment.addError(error);
    subsegment.close(error);
    throw error;
  }
};
```

## Cost Analysis and Optimization

### Pricing Breakdown (Monthly, 10M requests)

```javascript
const costBreakdown = {
  // API Gateway
  apiGateway: {
    requests: 10_000_000,
    costPerMillion: 3.50,
    total: 35
  },
  
  // Lambda
  lambda: {
    requests: 10_000_000,
    avgDuration: 200, // ms
    memorySize: 256,  // MB
    gbSeconds: (10_000_000 * 0.2 * 256) / 1024,
    costPerGbSecond: 0.0000166667,
    requestCost: 10_000_000 * 0.0000002,
    total: 8.35
  },
  
  // DynamoDB
  dynamodb: {
    writeRequests: 10_000_000,
    readRequests: 10_000_000,
    storage: 1, // GB
    writeRequestCost: 10_000_000 * 0.00000125,
    readRequestCost: 10_000_000 * 0.00000025,
    storageCost: 1 * 0.25,
    total: 15
  },
  
  // CloudWatch
  monitoring: 5,
  
  // Total monthly cost
  total: 63.35 // ~$63/month for 10M requests
};

console.log(`Cost per request: ${costBreakdown.total / 10}¢ per 1000 requests`);
```

### Cost Optimization Strategies

```javascript
// 1. Optimize Lambda memory allocation
const memoryOptimization = {
  128: { cost: 4.17, avgDuration: 300 },
  256: { cost: 8.35, avgDuration: 200 }, // Sweet spot
  512: { cost: 16.70, avgDuration: 150 }
};

// 2. Use DynamoDB on-demand vs provisioned
const dynamoOptimization = async () => {
  // Switch to provisioned for predictable workloads
  if (monthlyRequests > 40_000_000) {
    return 'provisioned'; // More cost effective at scale
  }
  return 'on-demand';
};

// 3. CloudFront caching for static responses
const cloudfrontConfig = {
  cacheBehaviors: [{
    pathPattern: '/favicon.ico',
    cachePolicyId: 'static-cache-policy',
    ttl: 86400 // 24 hours
  }]
};
```

## Deployment and CI/CD

### CDK Deployment Pipeline

```typescript
// Multi-environment deployment
class UrlShortenerPipeline extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const sourceArtifact = new codepipeline.Artifact('Source');
    const buildArtifact = new codepipeline.Artifact('Build');

    const pipeline = new codepipeline.Pipeline(this, 'Pipeline', {
      pipelineName: 'url-shortener-pipeline',
      stages: [
        {
          stageName: 'Source',
          actions: [
            new codepipeline_actions.GitHubSourceAction({
              actionName: 'GitHub',
              owner: 'yennanliu',
              repo: 'cdk-playground',
              branch: 'main',
              oauthToken: cdk.SecretValue.secretsManager('github-token'),
              output: sourceArtifact,
            }),
          ],
        },
        {
          stageName: 'Build',
          actions: [
            new codepipeline_actions.CodeBuildAction({
              actionName: 'Build',
              project: new codebuild.PipelineProject(this, 'BuildProject', {
                buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec.yml'),
                environment: {
                  buildImage: codebuild.LinuxBuildImage.STANDARD_5_0,
                  privileged: true,
                },
              }),
              input: sourceArtifact,
              outputs: [buildArtifact],
            }),
          ],
        },
        {
          stageName: 'Deploy-Dev',
          actions: [
            new codepipeline_actions.CloudFormationCreateUpdateStackAction({
              actionName: 'Deploy',
              stackName: 'url-shortener-dev',
              templatePath: buildArtifact.atPath('template.yml'),
              adminPermissions: true,
              parameterOverrides: {
                Environment: 'dev'
              }
            }),
          ],
        }
      ],
    });
  }
}
```

## Future Enhancements and Scale Considerations

### Geographic Distribution

```typescript
// Multi-region deployment for global performance
const regions = ['us-east-1', 'eu-west-1', 'ap-southeast-1'];

regions.forEach(region => {
  new UrlShortenerStack(app, `UrlShortener-${region}`, {
    env: { region },
    crossRegionReferences: true
  });
});

// Route 53 for geographic routing
const hostedZone = new route53.HostedZone(this, 'HostedZone', {
  zoneName: 'short.example.com'
});

const recordSet = new route53.RecordSet(this, 'GeographicRecord', {
  zone: hostedZone,
  recordName: 'api',
  recordType: route53.RecordType.A,
  target: route53.RecordTarget.fromAlias(
    new targets.ApiGatewayDomain(customDomain)
  ),
  geoLocation: route53.GeoLocation.country('US')
});
```

### Advanced Analytics

```javascript
// Stream processing for real-time analytics
const kinesisStream = new kinesis.Stream(this, 'AnalyticsStream', {
  shardCount: 1
});

const analyticsProcessor = new lambda.Function(this, 'AnalyticsProcessor', {
  runtime: lambda.Runtime.NODEJS_18_X,
  handler: 'analytics-processor.handler',
  code: lambda.Code.fromAsset('lambda'),
});

new lambda.EventSourceMapping(this, 'KinesisEventSource', {
  eventSourceArn: kinesisStream.streamArn,
  target: analyticsProcessor,
  batchSize: 100,
  maxBatchingWindow: cdk.Duration.seconds(5)
});

// Real-time dashboard with aggregated metrics
const timeSeriesAnalytics = `
SELECT 
  TUMBLE_START(rowtime, INTERVAL '1' MINUTE) as window_start,
  COUNT(*) as click_count,
  COUNT(DISTINCT short_code) as unique_urls,
  APPROX_COUNT_DISTINCT(source_ip) as unique_visitors
FROM source_table
GROUP BY TUMBLE(rowtime, INTERVAL '1' MINUTE)
`;
```

## Lessons Learned and Best Practices

### 1. Design for Failure
```javascript
// Circuit breaker pattern for external dependencies
const circuitBreaker = {
  state: 'CLOSED', // CLOSED, OPEN, HALF_OPEN
  failureCount: 0,
  successCount: 0,
  lastFailureTime: null,
  
  async execute(operation) {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > 60000) {
        this.state = 'HALF_OPEN';
      } else {
        throw new Error('Circuit breaker is OPEN');
      }
    }
    
    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }
};
```

### 2. Monitoring is Critical
```javascript
// Custom business metrics
const recordMetric = (metricName, value, unit = 'Count') => {
  const params = {
    Namespace: 'URLShortener',
    MetricData: [{
      MetricName: metricName,
      Value: value,
      Unit: unit,
      Timestamp: new Date()
    }]
  };
  
  return cloudwatch.putMetricData(params).promise();
};
```

### 3. Security by Design
```javascript
// Input validation schema
const urlRequestSchema = {
  type: 'object',
  properties: {
    originalUrl: {
      type: 'string',
      format: 'uri',
      pattern: '^https?://',
      maxLength: 2048
    },
    customCode: {
      type: 'string',
      pattern: '^[a-zA-Z0-9]{3,20}$'
    }
  },
  required: ['originalUrl'],
  additionalProperties: false
};
```

## Conclusion

Building a production-ready URL shortener requires careful consideration of architecture, scalability, security, and cost. The serverless approach offers significant advantages for this use case:

- **Automatic scaling** handles traffic spikes without pre-provisioning
- **Cost efficiency** with pay-per-use pricing model
- **High availability** through managed services
- **Reduced operational overhead** with no servers to manage

Key takeaways from this implementation:

1. **Start Simple**: Begin with core functionality and iterate
2. **Design for Scale**: Use patterns that grow with your traffic
3. **Monitor Everything**: Observability is crucial for production systems  
4. **Security First**: Validate inputs and protect against abuse
5. **Cost Awareness**: Understand pricing models and optimize accordingly

The complete implementation is available in the [CDK playground repository](https://github.com/yennanliu/cdk-playground/tree/main/urlShortener-app), demonstrating how infrastructure as code enables rapid iteration and reliable deployments.

Whether you're building your first serverless application or optimizing an existing system, the patterns and practices demonstrated here provide a solid foundation for scalable, cost-effective solutions on AWS.
