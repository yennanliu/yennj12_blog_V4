---
title: "Building Scalable WordPress on AWS ECS Fargate"
date: 2025-08-10T16:08:16+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "architecture"]
tags: ["AI", "aws", "ecs", "fargate", "wordpress", "containers", "rds", "efs", "cdk"]
summary: "Comprehensive guide to deploying production-ready WordPress on AWS ECS Fargate, exploring containerization strategies, infrastructure decisions, and scalability patterns for high-traffic content management systems."
readTime: "16 min"
---

Traditional WordPress hosting on shared servers or single instances has limitations when it comes to scalability, reliability, and performance. Modern content management platforms need to handle traffic spikes, ensure high availability, and provide seamless scaling. This post explores building a production-ready WordPress platform using AWS ECS Fargate, diving into architectural decisions, tradeoffs, and implementation details.

## The Challenge: WordPress at Scale

WordPress powers over 40% of websites globally, but scaling it beyond a single server presents several challenges:

- **Traffic Variability**: Content sites experience unpredictable traffic patterns
- **Database Bottlenecks**: MySQL becomes the limiting factor at scale  
- **File Storage**: Shared file systems for uploads and media
- **Session Management**: Handling user sessions across multiple instances
- **Plugin Compatibility**: Ensuring third-party plugins work in containerized environments
- **Security**: Protecting against vulnerabilities and attacks
- **Cost Optimization**: Balancing performance with operational costs

Let's explore how containerized WordPress on ECS Fargate addresses these challenges.

## Architecture Overview

Our scalable WordPress platform uses a microservices approach with these AWS components:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│ CloudFront  │    │     ALB      │    │ECS Fargate  │    │     RDS     │
│   (CDN)     │───▶│ (Load Bal.)  │───▶│ WordPress   │───▶│   MySQL     │
└─────────────┘    └──────────────┘    │ Container   │    │  (Multi-AZ) │
                                       └─────────────┘    └─────────────┘
                                              │
                                              ▼
                                       ┌─────────────┐
                                       │     EFS     │
                                       │(File System)│
                                       └─────────────┘
```

### Core Components

1. **ECS Fargate**: Serverless containers for WordPress application
2. **Application Load Balancer**: Distributes traffic across multiple containers
3. **RDS MySQL**: Managed database with Multi-AZ deployment
4. **EFS**: Shared file system for WordPress uploads and plugins
5. **CloudFront**: Global CDN for static content delivery
6. **Secrets Manager**: Secure storage for database credentials

## CDK Infrastructure Implementation

### VPC and Network Setup

The foundation starts with a properly configured network:

```typescript
// lib/ecs-wordpress-stack.ts
export class EcsWordpressStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC with public and private subnets across multiple AZs
    const vpc = new ec2.Vpc(this, 'WordPressVpc', {
      maxAzs: 2,
      natGateways: 2, // One per AZ for high availability
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'PublicSubnet',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'PrivateSubnet',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 28,
          name: 'IsolatedSubnet',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // Security group for ECS tasks
    const ecsSecurityGroup = new ec2.SecurityGroup(this, 'EcsSecurityGroup', {
      vpc,
      description: 'Security group for ECS WordPress tasks',
      allowAllOutbound: true,
    });

    // Security group for RDS
    const rdsSecurityGroup = new ec2.SecurityGroup(this, 'RdsSecurityGroup', {
      vpc,
      description: 'Security group for RDS MySQL instance',
      allowAllOutbound: false,
    });

    // Allow ECS to connect to RDS on MySQL port
    rdsSecurityGroup.addIngressRule(
      ecsSecurityGroup,
      ec2.Port.tcp(3306),
      'Allow ECS tasks to connect to MySQL'
    );

    // Security group for EFS
    const efsSecurityGroup = new ec2.SecurityGroup(this, 'EfsSecurityGroup', {
      vpc,
      description: 'Security group for EFS file system',
      allowAllOutbound: false,
    });

    // Allow ECS to connect to EFS on NFS port
    efsSecurityGroup.addIngressRule(
      ecsSecurityGroup,
      ec2.Port.tcp(2049),
      'Allow ECS tasks to connect to EFS'
    );
  }
}
```

**Key Design Decisions:**

- **Multi-AZ deployment** ensures high availability
- **Private subnets** for ECS tasks provide security isolation
- **Isolated subnets** for RDS eliminate internet access
- **Security groups** implement least-privilege access

### EFS File System for Persistent Storage

WordPress requires shared storage for uploads, themes, and plugins:

```typescript
// EFS File System with encryption
const fileSystem = new efs.FileSystem(this, 'WordPressFileSystem', {
  vpc,
  securityGroup: efsSecurityGroup,
  encrypted: true,
  lifecyclePolicy: efs.LifecyclePolicy.AFTER_30_DAYS,
  performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
  throughputMode: efs.ThroughputMode.BURSTING,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});

// EFS Access Points for better security and performance
const accessPoint = new efs.AccessPoint(this, 'WordPressAccessPoint', {
  fileSystem,
  path: '/var/www/html',
  creationInfo: {
    ownerGid: '33',    // www-data group
    ownerUid: '33',    // www-data user
    permissions: '755',
  },
  posixUser: {
    gid: 33,
    uid: 33,
  },
});

// Create mount targets in each AZ
const mountTargets = vpc.privateSubnets.map((subnet, index) => {
  return new efs.MountTarget(this, `MountTarget${index}`, {
    fileSystem,
    subnet,
    securityGroup: efsSecurityGroup,
  });
});
```

### RDS MySQL Database

Managed MySQL database with high availability:

```typescript
// Database subnet group for RDS
const dbSubnetGroup = new rds.SubnetGroup(this, 'DbSubnetGroup', {
  vpc,
  description: 'Subnet group for WordPress RDS instance',
  subnets: {
    subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
  },
});

// RDS MySQL instance
const database = new rds.DatabaseInstance(this, 'WordPressDatabase', {
  engine: rds.DatabaseInstanceEngine.mysql({
    version: rds.MysqlEngineVersion.VER_8_0,
  }),
  instanceType: ec2.InstanceType.of(
    ec2.InstanceClass.T3,
    ec2.InstanceSize.MICRO
  ),
  vpc,
  subnetGroup: dbSubnetGroup,
  securityGroups: [rdsSecurityGroup],
  
  // Database configuration
  databaseName: 'wordpress',
  credentials: rds.Credentials.fromGeneratedSecret('wordpressadmin', {
    excludeCharacters: '"@/\\\'',
  }),
  
  // Storage configuration
  allocatedStorage: 20,
  maxAllocatedStorage: 100,
  storageEncrypted: true,
  storageType: rds.StorageType.GP2,
  
  // Backup and maintenance
  backupRetention: cdk.Duration.days(7),
  deleteAutomatedBackups: true,
  deletionProtection: false,
  
  // Multi-AZ for production
  multiAz: true,
  
  // Monitoring
  monitoringInterval: cdk.Duration.seconds(60),
  enablePerformanceInsights: true,
  
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
```

## ECS Fargate Configuration

### Cluster and Task Definition

Setting up the ECS cluster and WordPress container:

```typescript
// ECS Cluster
const cluster = new ecs.Cluster(this, 'WordPressCluster', {
  vpc,
  containerInsights: true,
});

// Task Definition
const taskDefinition = new ecs.FargateTaskDefinition(this, 'WordPressTaskDef', {
  memoryLimitMiB: 2048,
  cpu: 1024,
});

// WordPress container
const wordpressContainer = taskDefinition.addContainer('wordpress', {
  image: ecs.ContainerImage.fromRegistry('wordpress:latest'),
  memoryReservationMiB: 1024,
  
  // Environment variables
  environment: {
    WORDPRESS_DB_HOST: database.instanceEndpoint.hostname,
    WORDPRESS_DB_NAME: 'wordpress',
    WORDPRESS_TABLE_PREFIX: 'wp_',
    
    // WordPress configuration
    WORDPRESS_CONFIG_EXTRA: `
      define('WP_REDIS_HOST', 'localhost');
      define('FORCE_SSL_ADMIN', true);
      define('WP_DEBUG', false);
      define('WP_DEBUG_LOG', false);
      define('WP_DEBUG_DISPLAY', false);
    `,
  },
  
  // Secrets from AWS Secrets Manager
  secrets: {
    WORDPRESS_DB_USER: ecs.Secret.fromSecretsManager(
      database.secret!,
      'username'
    ),
    WORDPRESS_DB_PASSWORD: ecs.Secret.fromSecretsManager(
      database.secret!,
      'password'
    ),
  },
  
  // Logging
  logging: ecs.LogDrivers.awsLogs({
    streamPrefix: 'wordpress',
    logRetention: logs.RetentionDays.ONE_WEEK,
  }),
});

// Configure container ports
wordpressContainer.addPortMappings({
  containerPort: 80,
  protocol: ecs.Protocol.TCP,
});

// EFS volume mount
taskDefinition.addVolume({
  name: 'wordpress-data',
  efsVolumeConfiguration: {
    fileSystemId: fileSystem.fileSystemId,
    transitEncryption: 'ENABLED',
    accessPoint: accessPoint.accessPointId,
  },
});

// Mount EFS volume in container
wordpressContainer.addMountPoints({
  sourceVolume: 'wordpress-data',
  containerPath: '/var/www/html/wp-content',
  readOnly: false,
});
```

### ECS Service with Auto Scaling

Configuring the service with automatic scaling:

```typescript
// Application Load Balancer
const alb = new elbv2.ApplicationLoadBalancer(this, 'WordPressALB', {
  vpc,
  internetFacing: true,
  securityGroup: albSecurityGroup,
});

// Target Group
const targetGroup = new elbv2.ApplicationTargetGroup(this, 'WordPressTargets', {
  vpc,
  port: 80,
  protocol: elbv2.ApplicationProtocol.HTTP,
  targetType: elbv2.TargetType.IP,
  
  // Health check configuration
  healthCheck: {
    enabled: true,
    healthyHttpCodes: '200,302',
    interval: cdk.Duration.seconds(30),
    path: '/wp-admin/install.php',
    protocol: elbv2.Protocol.HTTP,
    timeout: cdk.Duration.seconds(5),
    unhealthyThresholdCount: 2,
    healthyThresholdCount: 5,
  },
});

// ALB Listener
const listener = alb.addListener('WordPressListener', {
  port: 80,
  protocol: elbv2.ApplicationProtocol.HTTP,
  defaultTargetGroups: [targetGroup],
});

// ECS Service
const service = new ecs.FargateService(this, 'WordPressService', {
  cluster,
  taskDefinition,
  serviceName: 'wordpress-service',
  
  // Desired count and capacity
  desiredCount: 2,
  minHealthyPercent: 50,
  maxHealthyPercent: 200,
  
  // Network configuration
  assignPublicIp: false,
  securityGroups: [ecsSecurityGroup],
  vpcSubnets: {
    subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
  },
  
  // Load balancer configuration
  loadBalancers: [{
    targetGroup,
    containerName: 'wordpress',
    containerPort: 80,
  }],
  
  // Enable service discovery
  cloudMapOptions: {
    name: 'wordpress',
    cloudMapNamespace: cluster.defaultCloudMapNamespace,
    dnsRecordType: servicediscovery.DnsRecordType.A,
  },
});

// Auto Scaling Configuration
const scaling = service.autoScaleTaskCount({
  minCapacity: 1,
  maxCapacity: 10,
});

// CPU-based scaling
scaling.scaleOnCpuUtilization('CpuScaling', {
  targetUtilizationPercent: 70,
  scaleInCooldown: cdk.Duration.minutes(5),
  scaleOutCooldown: cdk.Duration.minutes(2),
});

// Memory-based scaling
scaling.scaleOnMemoryUtilization('MemoryScaling', {
  targetUtilizationPercent: 80,
  scaleInCooldown: cdk.Duration.minutes(5),
  scaleOutCooldown: cdk.Duration.minutes(2),
});
```

## Custom WordPress Container

Creating an optimized WordPress container:

```dockerfile
# Dockerfile for optimized WordPress
FROM wordpress:6.4-php8.2-apache

# Install additional PHP extensions
RUN apt-get update && apt-get install -y \
    libmemcached-dev \
    libzip-dev \
    libfreetype6-dev \
    libjpeg62-turbo-dev \
    libpng-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install PHP extensions for better performance
RUN docker-php-ext-configure gd \
    --with-freetype \
    --with-jpeg \
    --with-webp \
    && docker-php-ext-install -j$(nproc) gd zip opcache

# Install Redis extension for object caching
RUN pecl install redis-5.3.7 \
    && docker-php-ext-enable redis

# Install APCu for additional caching
RUN pecl install apcu \
    && docker-php-ext-enable apcu

# Copy custom PHP configuration
COPY php.ini /usr/local/etc/php/conf.d/wordpress.ini

# Copy custom WordPress configuration
COPY wp-config-docker.php /usr/src/wordpress/

# Copy custom .htaccess for better performance
COPY .htaccess /var/www/html/

# Set proper permissions
RUN chown -R www-data:www-data /var/www/html \
    && chmod -R 755 /var/www/html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1
```

### PHP Optimization Configuration

```ini
; php.ini - Production optimizations
[PHP]
memory_limit = 256M
upload_max_filesize = 32M
post_max_size = 32M
max_execution_time = 300
max_input_vars = 3000

; OPcache configuration
opcache.enable=1
opcache.memory_consumption=128
opcache.interned_strings_buffer=8
opcache.max_accelerated_files=4000
opcache.revalidate_freq=2
opcache.fast_shutdown=1
opcache.save_comments=1

; APCu configuration
apc.enabled=1
apc.shm_size=32M
apc.ttl=7200
apc.enable_cli=1

; Session configuration
session.cookie_httponly=1
session.cookie_secure=1
session.use_strict_mode=1
```

### WordPress Configuration

```php
<?php
// wp-config-docker.php - Optimized WordPress configuration
define('DB_NAME', getenv('WORDPRESS_DB_NAME'));
define('DB_USER', getenv('WORDPRESS_DB_USER'));
define('DB_PASSWORD', getenv('WORDPRESS_DB_PASSWORD'));
define('DB_HOST', getenv('WORDPRESS_DB_HOST'));
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', '');

// Security keys (should be generated for production)
define('AUTH_KEY',         'your-auth-key');
define('SECURE_AUTH_KEY',  'your-secure-auth-key');
define('LOGGED_IN_KEY',    'your-logged-in-key');
define('NONCE_KEY',        'your-nonce-key');
define('AUTH_SALT',        'your-auth-salt');
define('SECURE_AUTH_SALT', 'your-secure-auth-salt');
define('LOGGED_IN_SALT',   'your-logged-in-salt');
define('NONCE_SALT',       'your-nonce-salt');

// WordPress Database Table prefix
$table_prefix = getenv('WORDPRESS_TABLE_PREFIX') ?: 'wp_';

// Redis Object Cache
define('WP_REDIS_HOST', 'localhost');
define('WP_REDIS_PORT', 6379);
define('WP_REDIS_TIMEOUT', 1);
define('WP_REDIS_READ_TIMEOUT', 1);

// WordPress debugging
define('WP_DEBUG', false);
define('WP_DEBUG_LOG', false);
define('WP_DEBUG_DISPLAY', false);

// Security enhancements
define('DISALLOW_FILE_EDIT', true);
define('DISALLOW_FILE_MODS', true);
define('FORCE_SSL_ADMIN', true);
define('WP_POST_REVISIONS', 3);
define('AUTOSAVE_INTERVAL', 300);

// Performance optimizations
define('WP_MEMORY_LIMIT', '256M');
define('WP_MAX_MEMORY_LIMIT', '512M');
define('COMPRESS_CSS', true);
define('COMPRESS_SCRIPTS', true);
define('CONCATENATE_SCRIPTS', true);

// Multisite configuration (if needed)
// define('WP_ALLOW_MULTISITE', true);

// Custom content directory (if using EFS)
define('WP_CONTENT_DIR', '/var/www/html/wp-content');
define('WP_CONTENT_URL', 'http://' . $_SERVER['HTTP_HOST'] . '/wp-content');

// Database repair
define('WP_ALLOW_REPAIR', false);

if (!defined('ABSPATH')) {
    define('ABSPATH', __DIR__ . '/');
}

require_once ABSPATH . 'wp-settings.php';
```

## CDN and Performance Optimization

### CloudFront Distribution

Setting up global content delivery:

```typescript
// CloudFront Origin Access Control for S3
const originAccessControl = new cloudfront.OriginAccessControl(this, 'OAC', {
  description: 'WordPress static content OAC',
});

// S3 bucket for static assets
const assetsBucket = new s3.Bucket(this, 'WordPressAssets', {
  bucketName: `wordpress-assets-${cdk.Aws.ACCOUNT_ID}`,
  versioned: true,
  encryption: s3.BucketEncryption.S3_MANAGED,
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});

// CloudFront distribution
const distribution = new cloudfront.Distribution(this, 'WordPressDistribution', {
  defaultRootObject: 'index.php',
  
  // Origins
  additionalBehaviors: {
    // Static assets from S3
    '/wp-content/uploads/*': {
      origin: new origins.S3Origin(assetsBucket, {
        originAccessControl,
      }),
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      compress: true,
    },
    
    // WordPress admin (no caching)
    '/wp-admin/*': {
      origin: new origins.LoadBalancerV2Origin(alb, {
        protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      }),
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
    },
    
    // API endpoints (no caching)
    '/wp-json/*': {
      origin: new origins.LoadBalancerV2Origin(alb, {
        protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      }),
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
    },
  },
  
  // Default behavior for dynamic content
  defaultBehavior: {
    origin: new origins.LoadBalancerV2Origin(alb, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
    }),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: new cloudfront.CachePolicy(this, 'WordPressCachePolicy', {
      cachePolicyName: 'WordPress-Dynamic-Content',
      comment: 'Cache policy for WordPress dynamic content',
      defaultTtl: cdk.Duration.seconds(0),
      maxTtl: cdk.Duration.days(1),
      minTtl: cdk.Duration.seconds(0),
      cookieBehavior: cloudfront.CacheCookieBehavior.allowList(
        'wordpress_*', 'wp-*', 'comment_*'
      ),
      headerBehavior: cloudfront.CacheHeaderBehavior.allowList(
        'Accept-Encoding', 'CloudFront-Viewer-Country', 'Host'
      ),
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.all(),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
    }),
    allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
    compress: true,
  },
  
  // Geographic restrictions
  geoRestriction: cloudfront.GeoRestriction.allowlist('US', 'CA', 'GB', 'DE', 'FR'),
  
  // Security headers
  responseHeadersPolicy: new cloudfront.ResponseHeadersPolicy(this, 'SecurityHeaders', {
    comment: 'Security headers for WordPress',
    securityHeadersBehavior: {
      contentTypeOptions: { override: true },
      frameOptions: { frameOption: cloudfront.HeadersFrameOption.DENY, override: true },
      referrerPolicy: { referrerPolicy: cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN, override: true },
      strictTransportSecurity: {
        accessControlMaxAge: cdk.Duration.seconds(31536000),
        includeSubdomains: true,
        preload: true,
        override: true,
      },
    },
  }),
});
```

## Architecture Tradeoffs Analysis

### ECS Fargate vs EC2 Container Service

**Advantages of Fargate:**
- **Serverless containers**: No EC2 instance management
- **Auto-scaling**: Scales based on demand automatically
- **Cost efficiency**: Pay only for running containers
- **Security**: AWS manages underlying infrastructure

**Disadvantages:**
- **Cost at scale**: More expensive than EC2 for consistent workloads
- **Limited customization**: Less control over underlying OS
- **Cold starts**: Slight delay when scaling up
- **Storage limitations**: EFS required for persistent storage

```typescript
// Cost comparison for different deployment options
const costAnalysis = {
  // Fargate (2 vCPU, 4GB RAM, running 24/7)
  fargate: {
    monthlyHours: 24 * 30,
    vCpuCostPerHour: 0.04048,
    memoryCostPerHour: 0.004445,
    monthlyCost: (24 * 30) * (2 * 0.04048 + 4 * 0.004445), // ~$90/month
  },
  
  // EC2 with ECS (t3.medium)
  ec2: {
    instanceCost: 41.61, // t3.medium monthly
    storageGost: 10,     // EBS storage
    monthlyCost: 51.61,  // ~$52/month
  },
  
  // Managed services (WordPress.com, WP Engine)
  managed: {
    basicPlan: 25,       // Basic plan
    businessPlan: 96,    // Business plan with CDN
    enterprisePlan: 450, // Enterprise plan
  }
};
```

### EFS vs S3 for File Storage

**Why EFS for WordPress:**
```typescript
// EFS advantages for WordPress file storage
const efsAdvantages = {
  fileSystem: 'POSIX-compliant file system interface',
  concurrency: 'Multiple containers can read/write simultaneously',
  performance: 'Low-latency access for frequent file operations',
  plugins: 'WordPress plugins expect traditional file system',
  uploads: 'Direct file uploads without additional processing'
};

// S3 alternative considerations
const s3Alternative = {
  cost: 'Lower storage costs for large files',
  durability: '99.999999999% (11 9s) durability',
  cdn: 'Native CloudFront integration',
  limitations: 'Requires plugin for WordPress integration'
};
```

### RDS vs Self-managed MySQL

**RDS MySQL Benefits:**
- Automated backups and point-in-time recovery
- Multi-AZ deployment for high availability
- Automated patching and maintenance
- Performance Insights for monitoring
- Read replicas for read scaling

**Cost vs Feature Comparison:**
```sql
-- RDS pricing (us-east-1, t3.micro)
-- Instance: $0.017/hour = ~$12/month
-- Storage: $0.115/GB/month
-- Backup: Free for backup retention ≤ DB size

-- Self-managed alternative
-- EC2 t3.micro: $8.5/month
-- EBS storage: $10/month
-- Manual maintenance: Engineering time
-- Total: ~$18.5/month + operational overhead
```

## Performance Optimization Strategies

### Database Optimization

```sql
-- WordPress-specific MySQL optimizations
-- my.cnf configuration for RDS parameter group

[mysqld]
# InnoDB settings for WordPress
innodb_buffer_pool_size = 512M
innodb_buffer_pool_instances = 2
innodb_flush_log_at_trx_commit = 2
innodb_flush_method = O_DIRECT
innodb_log_file_size = 128M

# Query cache (MySQL 5.7 and earlier)
query_cache_type = 1
query_cache_size = 64M
query_cache_limit = 2M

# Connection settings
max_connections = 100
max_connect_errors = 10000

# Slow query logging
slow_query_log = 1
long_query_time = 2

# WordPress-specific optimizations
tmp_table_size = 64M
max_heap_table_size = 64M
join_buffer_size = 1M
sort_buffer_size = 2M
```

### Container Performance Tuning

```typescript
// Task definition with performance optimizations
const optimizedTaskDefinition = new ecs.FargateTaskDefinition(this, 'OptimizedWordPressTask', {
  memoryLimitMiB: 4096,  // Increased memory
  cpu: 2048,             // Increased CPU
  
  // Platform version for better performance
  platformVersion: ecs.FargatePlatformVersion.LATEST,
  
  // Task role for AWS service access
  taskRole: taskRole,
  executionRole: executionRole,
});

// WordPress container with resource limits
const optimizedContainer = optimizedTaskDefinition.addContainer('wordpress', {
  image: ecs.ContainerImage.fromRegistry('your-account.dkr.ecr.region.amazonaws.com/wordpress:optimized'),
  memoryReservationMiB: 3072,
  memoryLimitMiB: 4096,
  
  // Resource allocation
  cpu: 1536,
  
  // Environment variables for performance
  environment: {
    // PHP-FPM optimizations
    PHP_FPM_PM: 'dynamic',
    PHP_FPM_PM_MAX_CHILDREN: '50',
    PHP_FPM_PM_START_SERVERS: '10',
    PHP_FPM_PM_MIN_SPARE_SERVERS: '5',
    PHP_FPM_PM_MAX_SPARE_SERVERS: '20',
    PHP_FPM_PM_MAX_REQUESTS: '1000',
    
    // Apache optimizations
    APACHE_MAX_REQUEST_WORKERS: '400',
    APACHE_SERVER_LIMIT: '16',
    APACHE_THREAD_LIMIT: '25',
    APACHE_THREADS_PER_CHILD: '25',
  },
  
  // Health check
  healthCheck: {
    command: ['CMD-SHELL', 'curl -f http://localhost/wp-admin/admin-ajax.php?action=health || exit 1'],
    interval: cdk.Duration.seconds(30),
    timeout: cdk.Duration.seconds(5),
    retries: 3,
    startPeriod: cdk.Duration.seconds(60),
  },
});
```

## Security Implementation

### Network Security

```typescript
// Security group configurations with least privilege
const albSecurityGroup = new ec2.SecurityGroup(this, 'ALBSecurityGroup', {
  vpc,
  description: 'Security group for Application Load Balancer',
  allowAllOutbound: false,
});

// Allow HTTP and HTTPS traffic
albSecurityGroup.addIngressRule(
  ec2.Peer.anyIpv4(),
  ec2.Port.tcp(80),
  'Allow HTTP traffic'
);
albSecurityGroup.addIngressRule(
  ec2.Peer.anyIpv4(),
  ec2.Port.tcp(443),
  'Allow HTTPS traffic'
);

// Allow outbound to ECS tasks
albSecurityGroup.addEgressRule(
  ecsSecurityGroup,
  ec2.Port.tcp(80),
  'Allow outbound to ECS tasks'
);

// ECS security group - only allow traffic from ALB
ecsSecurityGroup.addIngressRule(
  albSecurityGroup,
  ec2.Port.tcp(80),
  'Allow traffic from ALB'
);

// Allow outbound for database and EFS access
ecsSecurityGroup.addEgressRule(
  rdsSecurityGroup,
  ec2.Port.tcp(3306),
  'Allow database access'
);
ecsSecurityGroup.addEgressRule(
  efsSecurityGroup,
  ec2.Port.tcp(2049),
  'Allow EFS access'
);
```

### Application Security

```php
// wp-config.php security enhancements
// Disable file editing
define('DISALLOW_FILE_EDIT', true);
define('DISALLOW_FILE_MODS', true);

// Security keys (use AWS Secrets Manager in production)
define('WP_DEBUG', false);
define('WP_DEBUG_LOG', false);
define('WP_DEBUG_DISPLAY', false);

// Database security
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', 'utf8mb4_unicode_ci');

// Force SSL
define('FORCE_SSL_ADMIN', true);
if (isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    $_SERVER['HTTPS'] = 'on';
}

// Limit post revisions
define('WP_POST_REVISIONS', 3);

// Increase memory limit securely
define('WP_MEMORY_LIMIT', '256M');

// Hide WordPress version
function remove_wp_version() {
    return '';
}
add_filter('the_generator', 'remove_wp_version');

// Disable XML-RPC
add_filter('xmlrpc_enabled', '__return_false');

// Security headers
function add_security_headers() {
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('X-XSS-Protection: 1; mode=block');
    header('Referrer-Policy: strict-origin-when-cross-origin');
    header('Permissions-Policy: geolocation=(), microphone=(), camera=()');
}
add_action('send_headers', 'add_security_headers');
```

## Monitoring and Observability

### CloudWatch Metrics and Alarms

```typescript
// Custom metrics for WordPress performance
const wordpressMetrics = {
  // Application Load Balancer metrics
  responseTime: new cloudwatch.Metric({
    namespace: 'AWS/ApplicationELB',
    metricName: 'TargetResponseTime',
    dimensionsMap: {
      LoadBalancer: alb.loadBalancerFullName,
    },
    statistic: 'Average',
  }),
  
  // ECS Service metrics
  cpuUtilization: new cloudwatch.Metric({
    namespace: 'AWS/ECS',
    metricName: 'CPUUtilization',
    dimensionsMap: {
      ServiceName: service.serviceName,
      ClusterName: cluster.clusterName,
    },
    statistic: 'Average',
  }),
  
  // RDS metrics
  databaseConnections: new cloudwatch.Metric({
    namespace: 'AWS/RDS',
    metricName: 'DatabaseConnections',
    dimensionsMap: {
      DBInstanceIdentifier: database.instanceIdentifier,
    },
    statistic: 'Average',
  }),
};

// CloudWatch Alarms
const highResponseTimeAlarm = new cloudwatch.Alarm(this, 'HighResponseTime', {
  metric: wordpressMetrics.responseTime,
  threshold: 2.0,
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  alarmDescription: 'WordPress response time is too high',
});

const highCpuAlarm = new cloudwatch.Alarm(this, 'HighCPUUtilization', {
  metric: wordpressMetrics.cpuUtilization,
  threshold: 80,
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  alarmDescription: 'ECS tasks CPU utilization is high',
});

const highDbConnectionsAlarm = new cloudwatch.Alarm(this, 'HighDatabaseConnections', {
  metric: wordpressMetrics.databaseConnections,
  threshold: 80,
  evaluationPeriods: 2,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  alarmDescription: 'Database connection count is high',
});
```

### Application Performance Monitoring

```typescript
// X-Ray tracing for request tracking
const xrayRole = new iam.Role(this, 'XRayTaskRole', {
  assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName('AWSXRayDaemonWriteAccess'),
  ],
});

// Add X-Ray daemon sidecar container
const xrayContainer = taskDefinition.addContainer('xray-daemon', {
  image: ecs.ContainerImage.fromRegistry('amazon/aws-xray-daemon:latest'),
  memoryReservationMiB: 32,
  cpu: 32,
  essential: false,
  
  environment: {
    AWS_REGION: cdk.Aws.REGION,
  },
  
  logging: ecs.LogDrivers.awsLogs({
    streamPrefix: 'xray',
    logRetention: logs.RetentionDays.ONE_WEEK,
  }),
});

xrayContainer.addPortMappings({
  containerPort: 2000,
  protocol: ecs.Protocol.UDP,
});
```

## Backup and Disaster Recovery

### Automated Backup Strategy

```typescript
// RDS automated backups
const backupVault = new backup.BackupVault(this, 'WordPressBackupVault', {
  backupVaultName: 'wordpress-backup-vault',
  encryptionKey: kms.Alias.fromAliasName(this, 'BackupKey', 'alias/aws/backup'),
});

// Backup plan for RDS
const backupPlan = new backup.BackupPlan(this, 'WordPressBackupPlan', {
  backupPlanName: 'wordpress-backup-plan',
  backupPlanRules: [
    new backup.BackupPlanRule({
      ruleName: 'daily-backup',
      targets: [
        new backup.BackupTarget({
          backupResource: backup.BackupResource.fromRdsDatabase(database),
        }),
      ],
      scheduleExpression: events.Schedule.cron({ hour: '2', minute: '0' }),
      deleteAfter: cdk.Duration.days(30),
      moveToColdStorageAfter: cdk.Duration.days(7),
    }),
    new backup.BackupPlanRule({
      ruleName: 'weekly-backup',
      targets: [
        new backup.BackupTarget({
          backupResource: backup.BackupResource.fromRdsDatabase(database),
        }),
      ],
      scheduleExpression: events.Schedule.cron({ weekDay: '1', hour: '1', minute: '0' }),
      deleteAfter: cdk.Duration.days(90),
      moveToColdStorageAfter: cdk.Duration.days(30),
    }),
  ],
});

// EFS backup
const efsBackup = new backup.BackupPlanRule({
  ruleName: 'efs-daily-backup',
  targets: [
    new backup.BackupTarget({
      backupResource: backup.BackupResource.fromEfsFileSystem(fileSystem),
    }),
  ],
  scheduleExpression: events.Schedule.cron({ hour: '3', minute: '0' }),
  deleteAfter: cdk.Duration.days(14),
});
```

## Cost Optimization Strategies

### Resource Right-sizing

```typescript
// Cost optimization based on traffic patterns
const costOptimizedConfig = {
  // Development environment
  development: {
    rds: {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      multiAz: false,
      backupRetention: cdk.Duration.days(1),
    },
    ecs: {
      cpu: 512,
      memory: 1024,
      desiredCount: 1,
      minCapacity: 1,
      maxCapacity: 2,
    },
  },
  
  // Production environment
  production: {
    rds: {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
      multiAz: true,
      backupRetention: cdk.Duration.days(7),
    },
    ecs: {
      cpu: 1024,
      memory: 2048,
      desiredCount: 2,
      minCapacity: 2,
      maxCapacity: 10,
    },
  },
};

// Scheduled scaling for predictable traffic patterns
const scheduledScaling = service.autoScaleTaskCount({
  minCapacity: 1,
  maxCapacity: 10,
});

// Scale up during business hours
scheduledScaling.scaleOnSchedule('ScaleUpMorning', {
  schedule: autoscaling.Schedule.cron({ hour: '8', minute: '0' }),
  minCapacity: 3,
  maxCapacity: 10,
});

// Scale down during off hours
scheduledScaling.scaleOnSchedule('ScaleDownEvening', {
  schedule: autoscaling.Schedule.cron({ hour: '20', minute: '0' }),
  minCapacity: 1,
  maxCapacity: 5,
});
```

### Cost Monitoring

```typescript
// Budget alerts for cost control
const budget = new budgets.CfnBudget(this, 'WordPressBudget', {
  budget: {
    budgetName: 'wordpress-monthly-budget',
    budgetLimit: {
      amount: 100,
      unit: 'USD',
    },
    timeUnit: 'MONTHLY',
    budgetType: 'COST',
    costFilters: {
      service: ['Amazon Elastic Container Service', 'Amazon Relational Database Service'],
    },
  },
  notificationsWithSubscribers: [
    {
      notification: {
        notificationType: 'ACTUAL',
        comparisonOperator: 'GREATER_THAN',
        threshold: 80,
      },
      subscribers: [
        {
          subscriptionType: 'EMAIL',
          address: 'devops@company.com',
        },
      ],
    },
  ],
});
```

## Deployment and CI/CD Pipeline

### Multi-environment Deployment

```typescript
// Environment-specific configurations
interface EnvironmentConfig {
  stackName: string;
  rdsInstanceType: ec2.InstanceType;
  ecsTaskCount: number;
  enableMultiAz: boolean;
  backupRetentionDays: number;
}

const environments: { [key: string]: EnvironmentConfig } = {
  dev: {
    stackName: 'wordpress-dev',
    rdsInstanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
    ecsTaskCount: 1,
    enableMultiAz: false,
    backupRetentionDays: 1,
  },
  staging: {
    stackName: 'wordpress-staging',
    rdsInstanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
    ecsTaskCount: 2,
    enableMultiAz: true,
    backupRetentionDays: 3,
  },
  prod: {
    stackName: 'wordpress-prod',
    rdsInstanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
    ecsTaskCount: 3,
    enableMultiAz: true,
    backupRetentionDays: 7,
  },
};

// Deploy stack for each environment
Object.entries(environments).forEach(([env, config]) => {
  new EcsWordpressStack(app, config.stackName, {
    env: { region: 'us-east-1' },
    config,
  });
});
```

### CI/CD Pipeline with CodePipeline

```typescript
// CI/CD Pipeline
const pipeline = new codepipeline.Pipeline(this, 'WordPressPipeline', {
  pipelineName: 'wordpress-ecs-pipeline',
  stages: [
    {
      stageName: 'Source',
      actions: [
        new codepipeline_actions.GitHubSourceAction({
          actionName: 'Source',
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
          project: new codebuild.Project(this, 'BuildProject', {
            buildSpec: codebuild.BuildSpec.fromObject({
              version: '0.2',
              phases: {
                pre_build: {
                  commands: [
                    'echo Logging in to Amazon ECR...',
                    'aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com',
                  ],
                },
                build: {
                  commands: [
                    'echo Build started on `date`',
                    'echo Building the Docker image...',
                    'cd ecs-wordpress-2',
                    'docker build -t $IMAGE_REPO_NAME:$IMAGE_TAG .',
                    'docker tag $IMAGE_REPO_NAME:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME:$IMAGE_TAG',
                  ],
                },
                post_build: {
                  commands: [
                    'echo Build completed on `date`',
                    'echo Pushing the Docker image...',
                    'docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME:$IMAGE_TAG',
                  ],
                },
              },
            }),
            environment: {
              buildImage: codebuild.LinuxBuildImage.STANDARD_5_0,
              privileged: true,
            },
          }),
          input: sourceArtifact,
        }),
      ],
    },
    {
      stageName: 'Deploy',
      actions: [
        new codepipeline_actions.EcsDeployAction({
          actionName: 'Deploy',
          service: service,
          input: buildArtifact,
        }),
      ],
    },
  ],
});
```

## Lessons Learned and Best Practices

### 1. Container Design

```dockerfile
# Multi-stage build for optimized images
FROM wordpress:6.4-php8.2-apache AS base

# Development stage
FROM base AS development
RUN apt-get update && apt-get install -y \
    xdebug \
    && docker-php-ext-enable xdebug

# Production stage
FROM base AS production
# Remove unnecessary packages and files
RUN apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy production-only configurations
COPY --from=development /usr/local/etc/php/conf.d/production.ini /usr/local/etc/php/conf.d/
```

### 2. Database Connection Management

```php
// WordPress database connection optimization
// wp-config.php additions
define('WP_ALLOW_REPAIR', false);

// Connection pooling for high traffic
define('DB_CONNECTION_TIMEOUT', 5);
define('DB_RETRY_INTERVAL', 1);

// Custom database error handling
function custom_db_error_handler($wp_error) {
    error_log('WordPress database error: ' . $wp_error->get_error_message());
    
    // Implement exponential backoff for connection retries
    $retry_count = get_transient('db_retry_count') ?: 0;
    $backoff_time = min(pow(2, $retry_count), 60); // Max 60 seconds
    
    if ($retry_count < 5) {
        set_transient('db_retry_count', $retry_count + 1, $backoff_time);
        sleep($backoff_time);
        return true; // Retry connection
    }
    
    return false; // Give up
}
```

### 3. Monitoring and Alerting

```typescript
// Comprehensive monitoring dashboard
const dashboard = new cloudwatch.Dashboard(this, 'WordPressDashboard', {
  dashboardName: 'WordPress-ECS-Performance',
  widgets: [
    [
      new cloudwatch.GraphWidget({
        title: 'ECS Service Metrics',
        left: [wordpressMetrics.cpuUtilization, wordpressMetrics.memoryUtilization],
        right: [service.metricTaskCount()],
      }),
    ],
    [
      new cloudwatch.GraphWidget({
        title: 'Application Load Balancer',
        left: [wordpressMetrics.responseTime, alb.metricRequestCount()],
        right: [alb.metricHttpCodeTarget(elbv2.HttpCodeTarget.TARGET_2XX_COUNT)],
      }),
    ],
    [
      new cloudwatch.GraphWidget({
        title: 'RDS Performance',
        left: [wordpressMetrics.databaseConnections, database.metricCPUUtilization()],
        right: [database.metricReadLatency(), database.metricWriteLatency()],
      }),
    ],
  ],
});
```

## Conclusion

Building a scalable WordPress platform on AWS ECS Fargate provides significant advantages for content-heavy applications:

- **Automatic scaling** handles traffic fluctuations without manual intervention
- **Container isolation** improves security and resource utilization
- **Managed services** reduce operational overhead
- **High availability** through multi-AZ deployments
- **Cost efficiency** with pay-per-use pricing models

Key takeaways from this implementation:

1. **Container Optimization**: Design lightweight, secure containers with proper resource allocation
2. **Storage Strategy**: Use EFS for shared WordPress files and RDS for reliable database operations
3. **Security First**: Implement network isolation, encryption, and least-privilege access
4. **Monitor Everything**: Comprehensive observability is crucial for production WordPress deployments
5. **Cost Management**: Right-size resources and implement scheduled scaling for predictable traffic patterns

The complete implementation is available in the [CDK playground repository](https://github.com/yennanliu/cdk-playground/tree/main/ecs-wordpress-2), demonstrating how modern containerization approaches can transform traditional WordPress hosting into a scalable, enterprise-grade platform.

Whether you're migrating from traditional hosting or building a new WordPress platform, the patterns demonstrated here provide a solid foundation for scalable, secure, and cost-effective content management systems on AWS.
