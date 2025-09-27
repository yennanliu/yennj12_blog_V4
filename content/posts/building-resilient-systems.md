---
title: "Building Resilient Systems: Handling Failure at Scale"
date: 2025-08-10T15:28:17+08:00
draft: false
authors: ["yen"]
categories: ["engineering", "architecture"]
tags: ["resilience", "fault-tolerance", "reliability", "distributed-systems"]
summary: "How we built systems that gracefully handle failures and maintain service availability even when components fail."
readTime: "10 min"
---

System failures are inevitable. The question isn't whether your system will fail, but how gracefully it handles those failures. Building resilient systems requires embracing failure as a first-class concern in your architecture.

## The Reality of Distributed Systems

Modern applications are complex distributed systems with many potential failure points:

- **Network partitions** between services
- **Hardware failures** causing server downtime  
- **Software bugs** leading to crashes
- **Traffic spikes** overwhelming system capacity
- **Dependency failures** cascading through the system

Each of these can bring down an entire application if not properly handled.

## Circuit Breaker Pattern

The circuit breaker prevents cascading failures by failing fast when dependencies are unhealthy:

```go
type CircuitBreaker struct {
    name         string
    state        CircuitState
    failures     int64
    successes    int64
    lastFailTime time.Time
    settings     CircuitSettings
    mutex        sync.RWMutex
}

type CircuitSettings struct {
    MaxFailures     int64
    ResetTimeout    time.Duration
    SuccessThreshold int64
}

func (cb *CircuitBreaker) Execute(operation func() error) error {
    cb.mutex.RLock()
    state := cb.state
    failures := cb.failures
    lastFailTime := cb.lastFailTime
    cb.mutex.RUnlock()

    switch state {
    case CircuitClosed:
        return cb.executeInClosedState(operation)
    case CircuitOpen:
        if time.Since(lastFailTime) > cb.settings.ResetTimeout {
            return cb.executeInHalfOpenState(operation)
        }
        return ErrCircuitOpen
    case CircuitHalfOpen:
        return cb.executeInHalfOpenState(operation)
    }

    return nil
}

func (cb *CircuitBreaker) executeInClosedState(operation func() error) error {
    err := operation()
    
    cb.mutex.Lock()
    defer cb.mutex.Unlock()
    
    if err != nil {
        cb.failures++
        cb.lastFailTime = time.Now()
        
        if cb.failures >= cb.settings.MaxFailures {
            cb.state = CircuitOpen
            log.Warn("Circuit breaker opened", "name", cb.name)
        }
        return err
    }
    
    cb.failures = 0
    return nil
}
```

## Retry Strategies

Implement intelligent retry mechanisms with exponential backoff:

```go
type RetryConfig struct {
    MaxRetries    int
    BaseDelay     time.Duration
    MaxDelay      time.Duration
    BackoffFactor float64
    Jitter        bool
}

func RetryWithBackoff(operation func() error, config RetryConfig) error {
    var lastErr error
    
    for attempt := 0; attempt <= config.MaxRetries; attempt++ {
        if attempt > 0 {
            delay := calculateDelay(attempt, config)
            if config.Jitter {
                delay = addJitter(delay)
            }
            time.Sleep(delay)
        }
        
        lastErr = operation()
        if lastErr == nil {
            return nil
        }
        
        // Don't retry for certain error types
        if !isRetryableError(lastErr) {
            return lastErr
        }
        
        log.Debug("Retrying operation", 
            "attempt", attempt+1, 
            "error", lastErr)
    }
    
    return fmt.Errorf("operation failed after %d attempts: %w", 
        config.MaxRetries+1, lastErr)
}

func calculateDelay(attempt int, config RetryConfig) time.Duration {
    delay := float64(config.BaseDelay) * 
            math.Pow(config.BackoffFactor, float64(attempt-1))
    
    if delay > float64(config.MaxDelay) {
        delay = float64(config.MaxDelay)
    }
    
    return time.Duration(delay)
}

func addJitter(delay time.Duration) time.Duration {
    jitter := time.Duration(rand.Float64() * float64(delay) * 0.1)
    return delay + jitter
}
```

## Bulkhead Pattern

Isolate critical resources to prevent total system failure:

```go
// Thread pool isolation
type BulkheadExecutor struct {
    pools map[string]*ThreadPool
    mutex sync.RWMutex
}

type ThreadPool struct {
    name     string
    workers  chan struct{}
    queue    chan Task
    metrics  *PoolMetrics
}

func NewBulkheadExecutor() *BulkheadExecutor {
    return &BulkheadExecutor{
        pools: make(map[string]*ThreadPool),
    }
}

func (be *BulkheadExecutor) CreatePool(name string, size int, queueSize int) {
    pool := &ThreadPool{
        name:    name,
        workers: make(chan struct{}, size),
        queue:   make(chan Task, queueSize),
        metrics: NewPoolMetrics(),
    }
    
    // Fill worker semaphore
    for i := 0; i < size; i++ {
        pool.workers <- struct{}{}
    }
    
    // Start worker goroutines
    for i := 0; i < size; i++ {
        go pool.worker()
    }
    
    be.mutex.Lock()
    be.pools[name] = pool
    be.mutex.Unlock()
}

func (tp *ThreadPool) worker() {
    for task := range tp.queue {
        <-tp.workers // Acquire worker slot
        
        start := time.Now()
        err := task.Execute()
        duration := time.Since(start)
        
        tp.metrics.RecordExecution(duration, err)
        tp.workers <- struct{} // Release worker slot
    }
}

func (be *BulkheadExecutor) Submit(poolName string, task Task) error {
    be.mutex.RLock()
    pool, exists := be.pools[poolName]
    be.mutex.RUnlock()
    
    if !exists {
        return fmt.Errorf("pool %s does not exist", poolName)
    }
    
    select {
    case pool.queue <- task:
        return nil
    default:
        pool.metrics.RecordRejection()
        return ErrPoolFull
    }
}
```

## Graceful Degradation

Design systems that continue operating with reduced functionality:

```go
type FeatureFlag struct {
    name        string
    enabled     bool
    fallback    func() interface{}
    healthCheck func() bool
}

type FeatureManager struct {
    flags   map[string]*FeatureFlag
    mutex   sync.RWMutex
    monitor *HealthMonitor
}

func (fm *FeatureManager) Execute(flagName string, primary func() (interface{}, error)) (interface{}, error) {
    fm.mutex.RLock()
    flag, exists := fm.flags[flagName]
    fm.mutex.RUnlock()
    
    if !exists {
        return primary()
    }
    
    // Check if feature is healthy
    if !flag.enabled || (flag.healthCheck != nil && !flag.healthCheck()) {
        log.Info("Feature degraded, using fallback", "feature", flagName)
        
        if flag.fallback != nil {
            return flag.fallback(), nil
        }
        
        return nil, ErrFeatureDegraded
    }
    
    return primary()
}

// Example usage
func (s *SearchService) SearchProducts(query string) (*SearchResults, error) {
    return s.featureManager.Execute("advanced_search", func() (interface{}, error) {
        // Advanced search with ML ranking
        return s.advancedSearch(query)
    })
}

func (s *SearchService) setupSearchDegradation() {
    s.featureManager.RegisterFlag("advanced_search", &FeatureFlag{
        name:    "advanced_search",
        enabled: true,
        fallback: func() interface{} {
            // Simple text-based search fallback
            return s.simpleSearch(query)
        },
        healthCheck: func() bool {
            // Check if ML service is responsive
            return s.mlService.IsHealthy()
        },
    })
}
```

## Health Checks and Monitoring

Implement comprehensive health monitoring:

```go
type HealthChecker struct {
    checks   map[string]HealthCheck
    timeout  time.Duration
    cache    *HealthCache
}

type HealthCheck interface {
    Name() string
    Check(ctx context.Context) HealthStatus
    IsCritical() bool
}

type DatabaseHealthCheck struct {
    db       *sql.DB
    critical bool
}

func (dhc *DatabaseHealthCheck) Check(ctx context.Context) HealthStatus {
    ctx, cancel := context.WithTimeout(ctx, time.Second*5)
    defer cancel()
    
    err := dhc.db.PingContext(ctx)
    if err != nil {
        return HealthStatus{
            Status:  StatusUnhealthy,
            Message: fmt.Sprintf("Database ping failed: %v", err),
        }
    }
    
    // Check if we can perform a simple query
    var count int
    err = dhc.db.QueryRowContext(ctx, "SELECT 1").Scan(&count)
    if err != nil {
        return HealthStatus{
            Status:  StatusUnhealthy,
            Message: fmt.Sprintf("Database query failed: %v", err),
        }
    }
    
    return HealthStatus{
        Status:  StatusHealthy,
        Message: "Database is healthy",
    }
}

func (hc *HealthChecker) CheckAll(ctx context.Context) map[string]HealthStatus {
    results := make(map[string]HealthStatus)
    
    // Run checks concurrently
    var wg sync.WaitGroup
    var mutex sync.Mutex
    
    for name, check := range hc.checks {
        wg.Add(1)
        go func(name string, check HealthCheck) {
            defer wg.Done()
            
            // Check cache first
            if cached := hc.cache.Get(name); cached != nil {
                mutex.Lock()
                results[name] = *cached
                mutex.Unlock()
                return
            }
            
            status := check.Check(ctx)
            
            // Cache result
            hc.cache.Set(name, &status, time.Minute)
            
            mutex.Lock()
            results[name] = status
            mutex.Unlock()
        }(name, check)
    }
    
    wg.Wait()
    return results
}
```

## Load Shedding

Protect system capacity during traffic spikes:

```go
type LoadShedder struct {
    maxConcurrency int64
    current        int64
    queue          chan Request
    metrics        *LoadMetrics
}

func NewLoadShedder(maxConcurrency int, queueSize int) *LoadShedder {
    return &LoadShedder{
        maxConcurrency: int64(maxConcurrency),
        queue:         make(chan Request, queueSize),
        metrics:       NewLoadMetrics(),
    }
}

func (ls *LoadShedder) Process(req Request, handler func(Request) error) error {
    current := atomic.LoadInt64(&ls.current)
    
    // Reject if over capacity
    if current >= ls.maxConcurrency {
        ls.metrics.RecordShed()
        return ErrOverCapacity
    }
    
    // Try to queue request
    select {
    case ls.queue <- req:
        atomic.AddInt64(&ls.current, 1)
        defer atomic.AddInt64(&ls.current, -1)
        
        return handler(req)
    default:
        ls.metrics.RecordShed()
        return ErrQueueFull
    }
}

// Priority-based load shedding
func (ls *LoadShedder) ProcessWithPriority(req PriorityRequest, handler func(Request) error) error {
    current := atomic.LoadInt64(&ls.current)
    
    if current >= ls.maxConcurrency {
        // Shed low priority requests first
        if req.Priority < PriorityHigh {
            ls.metrics.RecordShed()
            return ErrOverCapacity
        }
        
        // For high priority requests, try to preempt lower priority ones
        if ls.preemptLowPriority() {
            atomic.AddInt64(&ls.current, 1)
            defer atomic.AddInt64(&ls.current, -1)
            return handler(req.Request)
        }
        
        return ErrOverCapacity
    }
    
    atomic.AddInt64(&ls.current, 1)
    defer atomic.AddInt64(&ls.current, -1)
    
    return handler(req.Request)
}
```

## Chaos Engineering

Proactively test system resilience:

```go
type ChaosExperiment struct {
    name        string
    enabled     bool
    probability float64
    impact      ChaosImpact
    schedule    *ChaosSchedule
}

type ChaosImpact interface {
    Apply(ctx context.Context) error
    Rollback(ctx context.Context) error
}

type LatencyInjection struct {
    delay    time.Duration
    variance time.Duration
}

func (li *LatencyInjection) Apply(ctx context.Context) error {
    delay := li.delay
    if li.variance > 0 {
        variance := time.Duration(rand.Float64() * float64(li.variance))
        delay += variance
    }
    
    select {
    case <-time.After(delay):
        return nil
    case <-ctx.Done():
        return ctx.Err()
    }
}

type ChaosMonkey struct {
    experiments []*ChaosExperiment
    enabled     bool
    logger      logger.Logger
}

func (cm *ChaosMonkey) MaybeInjectChaos(ctx context.Context, operation string) error {
    if !cm.enabled {
        return nil
    }
    
    for _, exp := range cm.experiments {
        if !exp.enabled {
            continue
        }
        
        if rand.Float64() < exp.probability {
            cm.logger.Info("Injecting chaos", 
                "experiment", exp.name,
                "operation", operation)
                
            return exp.impact.Apply(ctx)
        }
    }
    
    return nil
}

// Usage in service calls
func (s *PaymentService) ProcessPayment(ctx context.Context, req PaymentRequest) error {
    // Inject chaos for testing
    if err := s.chaosMonkey.MaybeInjectChaos(ctx, "process_payment"); err != nil {
        return err
    }
    
    // Normal payment processing
    return s.processPaymentInternal(ctx, req)
}
```

## Metrics and Alerting

Monitor system resilience with key metrics:

```go
type ResilienceMetrics struct {
    CircuitBreakerState   *prometheus.GaugeVec
    RetryAttempts        *prometheus.CounterVec
    LoadShedCount        *prometheus.CounterVec
    DegradationEvents    *prometheus.CounterVec
    RecoveryTime         *prometheus.HistogramVec
}

func NewResilienceMetrics() *ResilienceMetrics {
    return &ResilienceMetrics{
        CircuitBreakerState: prometheus.NewGaugeVec(
            prometheus.GaugeOpts{
                Name: "circuit_breaker_state",
                Help: "Circuit breaker state (0=closed, 1=half-open, 2=open)",
            },
            []string{"service", "operation"},
        ),
        
        RetryAttempts: prometheus.NewCounterVec(
            prometheus.CounterOpts{
                Name: "retry_attempts_total",
                Help: "Total number of retry attempts",
            },
            []string{"service", "operation", "result"},
        ),
        
        LoadShedCount: prometheus.NewCounterVec(
            prometheus.CounterOpts{
                Name: "load_shed_total",
                Help: "Total number of requests shed",
            },
            []string{"service", "reason"},
        ),
    }
}

// Alerting rules for system resilience
const alertingRules = `
groups:
  - name: resilience
    rules:
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state == 2
        for: 1m
        annotations:
          summary: "Circuit breaker is open for {{ $labels.service }}"
          
      - alert: HighRetryRate
        expr: rate(retry_attempts_total[5m]) > 10
        for: 2m
        annotations:
          summary: "High retry rate detected"
          
      - alert: LoadSheddingActive
        expr: rate(load_shed_total[5m]) > 1
        for: 30s
        annotations:
          summary: "Load shedding is active"
`
```

## Key Principles for Resilient Systems

1. **Fail fast**: Don't let failing operations consume resources
2. **Isolate failures**: Use bulkheads to prevent cascade failures  
3. **Degrade gracefully**: Maintain core functionality when possible
4. **Monitor everything**: Comprehensive observability is essential
5. **Test failures**: Use chaos engineering to validate resilience
6. **Plan for recovery**: Design systems that can recover automatically

Building resilient systems requires thinking about failure from day one. By implementing these patterns and practices, you can build systems that not only survive failures but recover gracefully and continue serving users even under adverse conditions.

Remember: resilience is not a destination but an ongoing practice. Continuously test, monitor, and improve your system's ability to handle failure.