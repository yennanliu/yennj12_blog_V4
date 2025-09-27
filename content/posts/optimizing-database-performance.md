---
title: "Database Performance Optimization: From Slow Queries to Sub-millisecond Response Times"
date: 2025-08-10T15:28:17+08:00
draft: false
authors: ["yen"]
categories: ["engineering", "data"]
tags: ["database", "performance", "optimization", "postgresql", "redis"]
summary: "A comprehensive guide to database performance optimization techniques that helped us reduce query response times from seconds to milliseconds."
readTime: "15 min"
---

Database performance is often the bottleneck in web applications. Over the past year, we've transformed our database layer from a source of constant performance issues to a highly optimized system that consistently delivers sub-millisecond response times.

## The Performance Crisis

Our journey began with a crisis. Our main application database was experiencing:

- **Query timeouts**: 15% of queries taking over 30 seconds
- **Connection pool exhaustion**: Regular 503 errors during peak traffic  
- **Cascading failures**: Slow queries blocking other operations
- **Poor user experience**: Page load times exceeding 5 seconds

The root cause analysis revealed multiple issues across our database architecture.

## Systematic Performance Analysis

### 1. Query Analysis and Profiling

The first step was understanding where time was being spent:

```sql
-- Enable query logging for analysis
ALTER SYSTEM SET log_statement = 'all';
ALTER SYSTEM SET log_duration = on;
ALTER SYSTEM SET log_min_duration_statement = 1000; -- Log queries > 1s

-- Analyze slow queries
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    rows
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

This revealed our top performance killers:

```sql
-- Problematic query #1: N+1 query pattern
SELECT * FROM users WHERE id = $1; -- Called 1000+ times per request

-- Problematic query #2: Missing index
SELECT * FROM orders 
WHERE created_at BETWEEN $1 AND $2 
AND status = 'pending'
ORDER BY created_at DESC; -- 45 second execution time
```

### 2. Index Strategy Overhaul

Strategic indexing provided immediate improvements:

```sql
-- Composite index for filtering and sorting
CREATE INDEX CONCURRENTLY idx_orders_status_created 
ON orders (status, created_at DESC) 
WHERE status IN ('pending', 'processing');

-- Partial index for active users
CREATE INDEX CONCURRENTLY idx_users_active_email 
ON users (email) 
WHERE deleted_at IS NULL;

-- Expression index for case-insensitive searches
CREATE INDEX CONCURRENTLY idx_users_lower_email 
ON users (LOWER(email));
```

**Results:**
- Query time reduced from 45s to 12ms (99.97% improvement)
- Index size kept minimal with partial indexes
- No impact on write performance

### 3. Query Optimization Techniques

#### Eliminating N+1 Queries

```go
// Before: N+1 queries
func GetUsersWithOrders(userIDs []string) ([]*User, error) {
    users := make([]*User, 0, len(userIDs))
    
    for _, id := range userIDs {
        user, err := db.GetUser(id) // 1 query per user
        if err != nil {
            return nil, err
        }
        
        orders, err := db.GetOrdersByUserID(id) // 1 query per user
        if err != nil {
            return nil, err
        }
        
        user.Orders = orders
        users = append(users, user)
    }
    
    return users, nil
}

// After: 2 queries total
func GetUsersWithOrders(userIDs []string) ([]*User, error) {
    // Single query to get all users
    users, err := db.GetUsersByIDs(userIDs)
    if err != nil {
        return nil, err
    }
    
    // Single query to get all orders
    orders, err := db.GetOrdersByUserIDs(userIDs)
    if err != nil {
        return nil, err
    }
    
    // Group orders by user ID in memory
    orderMap := groupOrdersByUserID(orders)
    
    for _, user := range users {
        user.Orders = orderMap[user.ID]
    }
    
    return users, nil
}
```

#### Query Restructuring

```sql
-- Before: Inefficient subquery
SELECT * FROM products p
WHERE p.category_id IN (
    SELECT c.id FROM categories c 
    WHERE c.name LIKE '%electronics%'
);

-- After: Efficient join
SELECT p.* 
FROM products p
INNER JOIN categories c ON p.category_id = c.id
WHERE c.name LIKE '%electronics%';
```

## Caching Architecture

### Multi-Level Caching Strategy

```go
type CacheHierarchy struct {
    l1 *LocalCache    // Application-level cache
    l2 *RedisCache    // Distributed cache
    l3 *Database      // Source of truth
}

func (ch *CacheHierarchy) GetUser(id string) (*User, error) {
    // L1: Check local cache
    if user, found := ch.l1.Get("user:" + id); found {
        return user.(*User), nil
    }
    
    // L2: Check Redis
    if userData, err := ch.l2.Get("user:" + id); err == nil {
        user := &User{}
        json.Unmarshal(userData, user)
        
        // Populate L1 cache
        ch.l1.Set("user:"+id, user, time.Minute*5)
        return user, nil
    }
    
    // L3: Query database
    user, err := ch.l3.GetUser(id)
    if err != nil {
        return nil, err
    }
    
    // Populate both cache levels
    userData, _ := json.Marshal(user)
    ch.l2.Set("user:"+id, userData, time.Hour)
    ch.l1.Set("user:"+id, user, time.Minute*5)
    
    return user, nil
}
```

### Cache Invalidation Strategy

```go
type CacheInvalidator struct {
    redis   *redis.Client
    local   cache.Cache
    patterns map[string][]string
}

func (ci *CacheInvalidator) InvalidateUser(userID string) error {
    keys := []string{
        "user:" + userID,
        "user_orders:" + userID,
        "user_preferences:" + userID,
    }
    
    // Invalidate Redis cache
    for _, key := range keys {
        if err := ci.redis.Del(key).Err(); err != nil {
            return err
        }
    }
    
    // Invalidate local cache
    for _, key := range keys {
        ci.local.Delete(key)
    }
    
    return nil
}
```

## Connection Pool Optimization

### Database Connection Management

```go
type DBConfig struct {
    MaxOpenConns    int
    MaxIdleConns    int
    ConnMaxLifetime time.Duration
    ConnMaxIdleTime time.Duration
}

func optimizeConnectionPool() *sql.DB {
    config := &DBConfig{
        MaxOpenConns:    50,  // Based on server capacity
        MaxIdleConns:    25,  // Half of max open
        ConnMaxLifetime: 30 * time.Minute,
        ConnMaxIdleTime: 10 * time.Minute,
    }
    
    db.SetMaxOpenConns(config.MaxOpenConns)
    db.SetMaxIdleConns(config.MaxIdleConns)
    db.SetConnMaxLifetime(config.ConnMaxLifetime)
    db.SetConnMaxIdleTime(config.ConnMaxIdleTime)
    
    return db
}
```

### Connection Pool Monitoring

```go
func monitorConnectionPool(db *sql.DB) {
    ticker := time.NewTicker(time.Minute)
    defer ticker.Stop()
    
    for {
        select {
        case <-ticker.C:
            stats := db.Stats()
            
            metrics.Gauge("db.connections.open").Set(float64(stats.OpenConnections))
            metrics.Gauge("db.connections.idle").Set(float64(stats.Idle))
            metrics.Gauge("db.connections.in_use").Set(float64(stats.InUse))
            metrics.Counter("db.connections.wait_count").Add(float64(stats.WaitCount))
            
            if stats.WaitCount > 0 {
                log.Warn("Database connection pool under pressure", 
                    "wait_count", stats.WaitCount,
                    "wait_duration", stats.WaitDuration)
            }
        }
    }
}
```

## Read Replica Strategy

### Load Balancing Reads and Writes

```go
type DatabaseCluster struct {
    master   *sql.DB
    replicas []*sql.DB
    selector ReplicaSelector
}

type QueryContext struct {
    Type     QueryType
    UserID   string
    Priority Priority
}

func (dc *DatabaseCluster) Query(ctx QueryContext, query string, args ...interface{}) (*sql.Rows, error) {
    switch ctx.Type {
    case QueryTypeWrite, QueryTypeTransactional:
        return dc.master.Query(query, args...)
        
    case QueryTypeRead:
        replica := dc.selector.SelectReplica(ctx)
        return replica.Query(query, args...)
        
    default:
        return nil, errors.New("unknown query type")
    }
}

// Weighted round-robin replica selection
type WeightedRoundRobin struct {
    replicas []ReplicaWithWeight
    current  int
    mutex    sync.Mutex
}

func (wrr *WeightedRoundRobin) SelectReplica(ctx QueryContext) *sql.DB {
    wrr.mutex.Lock()
    defer wrr.mutex.Unlock()
    
    // High priority queries go to least loaded replica
    if ctx.Priority == PriorityHigh {
        return wrr.selectLeastLoaded()
    }
    
    // Standard round-robin for normal queries
    replica := wrr.replicas[wrr.current%len(wrr.replicas)]
    wrr.current++
    return replica.DB
}
```

## Query Result Optimization

### Pagination Best Practices

```sql
-- Inefficient: OFFSET becomes slow with large offsets
SELECT * FROM posts 
ORDER BY created_at DESC 
LIMIT 20 OFFSET 10000;

-- Efficient: Cursor-based pagination
SELECT * FROM posts 
WHERE created_at < $1  -- cursor from previous page
ORDER BY created_at DESC 
LIMIT 20;
```

```go
type CursorPagination struct {
    Cursor string `json:"cursor"`
    Limit  int    `json:"limit"`
}

func (p *PostService) GetPosts(pagination CursorPagination) (*PostsResponse, error) {
    var cursor time.Time
    var err error
    
    if pagination.Cursor != "" {
        cursor, err = time.Parse(time.RFC3339, pagination.Cursor)
        if err != nil {
            return nil, err
        }
    } else {
        cursor = time.Now()
    }
    
    query := `
        SELECT id, title, content, created_at 
        FROM posts 
        WHERE created_at < $1 
        ORDER BY created_at DESC 
        LIMIT $2`
    
    rows, err := p.db.Query(query, cursor, pagination.Limit+1)
    if err != nil {
        return nil, err
    }
    defer rows.Close()
    
    posts := make([]*Post, 0, pagination.Limit)
    var nextCursor string
    
    for rows.Next() {
        post := &Post{}
        if err := rows.Scan(&post.ID, &post.Title, &post.Content, &post.CreatedAt); err != nil {
            return nil, err
        }
        
        if len(posts) == pagination.Limit {
            nextCursor = post.CreatedAt.Format(time.RFC3339)
            break
        }
        
        posts = append(posts, post)
    }
    
    return &PostsResponse{
        Posts:      posts,
        NextCursor: nextCursor,
    }, nil
}
```

### Selective Field Loading

```go
// Don't load unnecessary data
type UserSummary struct {
    ID    string `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

func (us *UserService) GetUserSummaries(ids []string) ([]*UserSummary, error) {
    query := `
        SELECT id, name, email 
        FROM users 
        WHERE id = ANY($1) 
        AND deleted_at IS NULL`
    
    rows, err := us.db.Query(query, pq.Array(ids))
    if err != nil {
        return nil, err
    }
    defer rows.Close()
    
    summaries := make([]*UserSummary, 0, len(ids))
    for rows.Next() {
        summary := &UserSummary{}
        if err := rows.Scan(&summary.ID, &summary.Name, &summary.Email); err != nil {
            return nil, err
        }
        summaries = append(summaries, summary)
    }
    
    return summaries, nil
}
```

## Monitoring and Alerting

### Key Metrics Dashboard

```go
type DatabaseMetrics struct {
    QueryLatencyP50   time.Duration
    QueryLatencyP95   time.Duration
    QueryLatencyP99   time.Duration
    QueriesPerSecond  float64
    ErrorRate         float64
    CacheHitRate      float64
    ConnectionUtilization float64
}

func collectMetrics(db *sql.DB, cache cache.Cache) {
    ticker := time.NewTicker(time.Second * 10)
    defer ticker.Stop()
    
    for {
        select {
        case <-ticker.C:
            stats := db.Stats()
            
            // Connection metrics
            metrics.Gauge("db.connections.utilization").Set(
                float64(stats.InUse) / float64(stats.MaxOpenConns))
            
            // Query performance metrics
            queryStats := getQueryStats()
            metrics.Histogram("db.query.latency").Observe(queryStats.MeanLatency)
            metrics.Counter("db.queries.total").Add(queryStats.Count)
            
            // Cache metrics
            cacheStats := cache.Stats()
            hitRate := float64(cacheStats.Hits) / float64(cacheStats.Hits + cacheStats.Misses)
            metrics.Gauge("cache.hit_rate").Set(hitRate)
        }
    }
}
```

### Automated Performance Alerting

```yaml
# Prometheus alerting rules
groups:
  - name: database_performance
    rules:
      - alert: HighQueryLatency
        expr: histogram_quantile(0.95, db_query_duration_seconds) > 1
        for: 2m
        annotations:
          summary: "Database query latency is high"
          
      - alert: LowCacheHitRate
        expr: cache_hit_rate < 0.8
        for: 5m
        annotations:
          summary: "Cache hit rate is below optimal threshold"
          
      - alert: DatabaseConnectionsHigh
        expr: db_connections_utilization > 0.8
        for: 1m
        annotations:
          summary: "Database connection pool utilization is high"
```

## Results and Impact

Our systematic approach to database optimization yielded significant improvements:

### Performance Improvements
- **Query latency**: 95th percentile reduced from 15s to 50ms
- **Cache hit rate**: Increased from 60% to 95%
- **Connection pool efficiency**: Eliminated connection timeouts
- **Error rate**: Reduced database errors by 99.8%

### Business Impact
- **Page load times**: Improved from 5s to under 500ms
- **User satisfaction**: 40% increase in user engagement metrics
- **Infrastructure costs**: 30% reduction in database server requirements
- **Developer productivity**: Faster development cycles with reliable performance

## Key Takeaways

1. **Measure first**: Use profiling tools to identify actual bottlenecks
2. **Index strategically**: Create indexes that support your most common query patterns
3. **Cache intelligently**: Implement multi-level caching with proper invalidation
4. **Optimize connections**: Right-size connection pools and monitor utilization
5. **Read replicas**: Distribute read load to improve overall performance
6. **Monitor continuously**: Set up comprehensive metrics and alerting

Database performance optimization is an iterative process. Start with the biggest impact changes (usually indexing and caching), then progressively optimize based on monitoring data and changing usage patterns.

The investment in database performance pays dividends not just in user experience, but also in system reliability, development velocity, and infrastructure costs.