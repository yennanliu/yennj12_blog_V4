---
title: "購物車系統的高並發改造（二）：Redisson 分散式鎖、讀寫分離路由與 Docker HA 水平擴展"
date: 2026-05-25T09:00:00+08:00
draft: false
weight: 2
description: "高並發購物車系列第二篇：深入剖析 Redisson 分散式鎖如何防止超賣與重複下單、AbstractRoutingDataSource + LazyConnectionDataSourceProxy 的讀寫分離路由設計細節（含 @Transactional 的坑），以及 Nginx + MySQL 主從複製的 Docker HA 生產架構。"
categories: ["Engineering", "Architecture", "all"]
tags: ["Spring Boot", "Java", "Redisson", "Distributed Lock", "Read Replica", "Docker", "Nginx", "High Concurrency", "Backend", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "32 min"
---

## 前言

[第一篇](/posts/shopping-cart-high-concurrency-part1-zh/)解決了系統的吞吐量問題：Virtual Threads 讓執行緒不再阻塞在 I/O 上，HikariCP 調校讓資料庫連線不再是瓶頸，Redis 快取讓熱點讀取從記憶體直接回傳。

但吞吐量提升後，反而暴露出一個更深層的問題：

> **並發請求同時寫入同一份資料，怎麼保證正確性？**

想像雙十一活動開始的那一秒，同一個用戶的兩個 Tab 同時按下「加入購物車」；或者同一個人網路不穩，重試了兩次「立即結帳」——這兩種場景都會導致重複訂單或資料不一致。

這篇介紹 PR #228 帶來的三個進階改造：

1. **Redisson 分散式鎖**：防止同一用戶的並發寫入互相干擾
2. **讀寫分離路由**：把讀請求分流到 Replica，Primary 只處理寫入
3. **Docker HA 水平擴展**：Nginx + 多個 App 實例 + MySQL 主從複製

---

## 方案四：Redisson 分散式鎖

### 為什麼需要分散式鎖？

第一篇的 `CartService.addToCart()` 在高並發下有一個隱患：

```java
// Part 1 的版本（沒有鎖）
public void addToCart(AddToCartDto addToCartDto, Product product, User user) {
    Cart cart = new Cart(product, addToCartDto.getQuantity(), user);
    cartRepository.save(cart);  // ← 多個執行緒可能同時執行這一行
}
```

當同一個用戶同時發出兩個「加入購物車」請求時：

```
Thread A: new Cart(productX, qty=1, user) → save → 購物車有 1 個 productX
Thread B: new Cart(productX, qty=1, user) → save → 購物車有 2 個 productX（重複！）
```

`cartRepository.save()` 是 INSERT，沒有天然的唯一性保護。兩個並發的 INSERT 都會成功，導致購物車重複項目。

`OrderService.placeOrder()` 的問題更嚴重：

```
Thread A 和 Thread B 同時呼叫 placeOrder：
  A: listCartItems → 看到 [iPhone, AirPods]
  B: listCartItems → 看到 [iPhone, AirPods]  ← 還沒被 A 清掉
  A: 建立 Order，清空購物車
  B: 建立 Order（相同商品！），清空購物車（已經空了，沒有報錯）
  結果：兩張一模一樣的訂單
```

### 分散式鎖的基本原則

本地的 `synchronized` 或 `ReentrantLock` 只能保護**同一個 JVM 內**的並發。在水平擴展（多個 App 實例）的環境下，不同實例各有自己的鎖，完全無效。

分散式鎖需要一個**所有實例共享的外部儲存**來協調，Redis 是最常見的選擇。

### RedissonConfig 設定

```java
@Configuration
public class RedissonConfig {

    @Value("${spring.data.redis.host:localhost}")
    private String redisHost;

    @Value("${spring.data.redis.port:6379}")
    private int redisPort;

    @Bean(destroyMethod = "shutdown")
    public RedissonClient redissonClient() {
        Config config = new Config();
        config.useSingleServer()
              .setAddress("redis://" + redisHost + ":" + redisPort)
              .setConnectionMinimumIdleSize(4)
              .setConnectionPoolSize(64);  // 從 10 提升到 64，避免高並發下 Redis 連線池本身成為瓶頸
        return Redisson.create(config);
    }
}
```

連線池從預設的 10 提升到 64，理由和 HikariCP 類似：在高並發場景下，Redisson 需要同時持有大量連線來處理鎖的取得、心跳（watchdog）、以及快取操作。

### CartService：加入購物車的鎖

```java
@Slf4j
@Service
@Transactional
public class CartService {

    @Autowired
    private CartRepository cartRepository;

    @Autowired
    private RedissonClient redissonClient;

    public void addToCart(AddToCartDto addToCartDto, Product product, User user) {

        // 鎖的粒度：per-user，而不是全局鎖
        // 不同用戶的操作互不干擾，可以完全並行
        RLock lock = redissonClient.getLock("cart:user:" + user.getId());
        try {
            // tryLock 而非 lock()：
            //   waitTime=3s：最多等 3 秒，等不到就直接拋例外（fail-fast）
            //   leaseTime=10s：鎖最多持有 10 秒，即使 JVM crash 也會自動釋放
            if (!lock.tryLock(3, 10, TimeUnit.SECONDS)) {
                throw new RuntimeException(
                    "Could not acquire cart lock for user " + user.getId()
                    + " — another request is already updating this cart");
            }
            Cart cart = new Cart(product, addToCartDto.getQuantity(), user);
            cartRepository.save(cart);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted while acquiring cart lock", e);
        } finally {
            // isHeldByCurrentThread() 防止 ABA 問題：
            // 如果 leaseTime 到了，鎖可能已被其他執行緒取得，此時不應 unlock
            if (lock.isHeldByCurrentThread()) lock.unlock();
        }
    }

    // ... 其他方法
}
```

#### 關鍵設計決策：`tryLock` 而非 `lock`

`lock()` 是阻塞等待，直到獲得鎖為止。在 Redis 延遲偶發性升高時（網路抖動、Redis GC），可能有數百個執行緒同時阻塞在 `lock()` 等待，迅速耗盡執行緒池。

`tryLock(waitTime=3s)` 最多等 3 秒。如果 3 秒內拿不到鎖，立刻失敗並回傳錯誤。這是**fail-fast 策略**：對用戶的影響是看到一個錯誤訊息，但系統的整體可用性不受影響。

```
情境：Redis 短暫延遲，100 個請求同時加入購物車

lock() 行為：
  100 個執行緒全部阻塞等待 Redis 回應
  → 執行緒池耗盡 → 其他請求（包括讀取操作）也開始 timeout

tryLock(3s) 行為：
  每個請求等最多 3 秒
  → 3 秒後，還沒拿到鎖的請求直接失敗
  → 執行緒快速釋放 → 系統整體可用性維持
```

#### 鎖的粒度：per-user，不是 per-product

鎖的粒度是一個關鍵設計選擇：

```
全局鎖：一次只有一個操作，吞吐量極低
per-product 鎖：防止對同一商品的並發操作，但不能防止同一用戶的重複提交
per-user 鎖：防止同一用戶的並發操作，不同用戶完全並行 ← 選這個
```

對購物車場景，問題的根源是「同一用戶」的並發請求，所以 per-user 鎖是最合適的粒度。

### OrderService：結帳的鎖（更複雜的設計）

`placeOrder` 的鎖設計有一個關鍵的難點：**鎖和事務的交互順序**。

#### 錯誤設計：鎖在事務內部

```java
// ❌ 錯誤：鎖在事務內部取得
@Transactional
public void placeOrder(User user, String sessionId) {
    RLock lock = redissonClient.getLock("order:user:" + user.getId());
    lock.lock();
    try {
        // ... 業務邏輯
    } finally {
        lock.unlock();  // 鎖先釋放
    }
    // @Transactional 在方法結束後 commit → 問題！
}
```

問題：`unlock()` 在 finally 執行，但 `@Transactional` 的 commit 在方法結束後才發生。這意味著：

```
Thread A: unlock() → 鎖釋放
Thread B: 立刻取得鎖 → 讀到 A 還未 commit 的資料（舊資料）→ 重複下單
```

#### 正確設計：鎖在事務外部

```java
// ✅ 正確：鎖包在事務外面
@Service  // 注意：OrderService 類別本身沒有 @Transactional
public class OrderService {

    // 1. 鎖的取得：在事務開始之前
    // 2. doPlaceOrder 執行（含事務 commit）
    // 3. 鎖釋放：在事務 commit 之後
    public void placeOrder(User user, String sessionId) {

        RLock lock = redissonClient.getLock("order:user:" + user.getId());
        try {
            if (!lock.tryLock(3, 30, TimeUnit.SECONDS)) {
                throw new RuntimeException(
                    "Could not acquire order lock for user " + user.getId()
                    + " — a concurrent checkout is already in progress");
            }
            doPlaceOrder(user, sessionId);  // 事務在這裡 commit
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted while acquiring order lock", e);
        } finally {
            if (lock.isHeldByCurrentThread()) lock.unlock();  // commit 之後才釋放
        }
    }

    // 實際的業務邏輯放在一個有 @Transactional 的 package-private 方法
    @Transactional
    void doPlaceOrder(User user, String sessionId) {

        CartDto cartDto = cartService.listCartItems(user);
        List<CartItemDto> cartItemDtoList = cartDto.getCartItems();

        // 冪等性防護：
        // 場景：A 和 B 同時呼叫 placeOrder，A 先拿到鎖並完成下單，清空購物車
        // B 拿到鎖後，購物車已空 → 不應該建立一張空訂單
        if (cartItemDtoList.isEmpty()) {
            log.warn("placeOrder called with empty cart for user {} — skipping (possible duplicate request)",
                    user.getId());
            return;
        }

        // 建立訂單、寫入訂單項目、清空購物車...
        Order newOrder = new Order();
        newOrder.setCreatedDate(new Date());
        newOrder.setSessionId(sessionId);
        newOrder.setUser(user);
        newOrder.setTotalPrice(cartDto.getTotalCost());
        orderRepository.save(newOrder);

        for (CartItemDto cartItemDto : cartItemDtoList) {
            OrderItem orderItem = new OrderItem();
            orderItem.setCreatedDate(new Date());
            orderItem.setPrice(cartItemDto.getProduct().getPrice());
            orderItem.setProduct(cartItemDto.getProduct());
            orderItem.setQuantity(cartItemDto.getQuantity());
            orderItem.setOrder(newOrder);
            orderItemsRepository.save(orderItem);
        }

        cartService.deleteUserCartItems(user);
        // ← 方法結束，@Transactional commit 在這裡發生
    }

    // 讀取操作標記 readOnly=true，讓讀寫分離路由把這些查詢導向 Replica
    @Transactional(readOnly = true)
    public List<Order> listOrders(User user) {
        return orderRepository.findAllByUserOrderByCreatedDateDesc(user);
    }

    @Transactional(readOnly = true)
    public Order getOrder(Integer orderId) throws OrderNotFoundException {
        Optional<Order> order = orderRepository.findById(orderId);
        if (order.isPresent()) return order.get();
        throw new OrderNotFoundException("Order not found");
    }
}
```

正確的執行順序：

```
Thread A 呼叫 placeOrder：
  1. tryLock("order:user:7") → 成功，取得鎖
  2. doPlaceOrder() 開始執行（Spring 開始事務）
  3. 讀取購物車 → 有商品
  4. 建立訂單、清空購物車
  5. doPlaceOrder() 返回 → Spring commit 事務
  6. finally: unlock() → 釋放鎖

Thread B 同時呼叫 placeOrder（在 A 持有鎖期間）：
  1. tryLock("order:user:7") → 等待
  2. A 釋放鎖（已 commit）→ B 取得鎖
  3. doPlaceOrder() 執行
  4. 讀取購物車 → 已空（A 已清空）
  5. 空購物車防護：log.warn + return
  6. 沒有重複訂單 ✅
```

#### `leaseTime=30s` 的選擇

`placeOrder` 的 leaseTime 設為 30 秒（比 addToCart 的 10 秒長），因為它需要：
- 多次資料庫操作（讀購物車 + N 次 INSERT + 清空購物車）
- 可能的網路延遲

如果擔心 JVM crash 導致鎖永遠不釋放，Redisson 的 watchdog 機制會在 `leaseTime` 到期前自動續期（但只有使用 `lock()` 而非 `tryLock(leaseTime)` 時才會啟動 watchdog）。使用固定 leaseTime 的 `tryLock`，鎖會在 leaseTime 後自動過期，不依賴 watchdog，但需要確認業務操作能在 leaseTime 內完成。

### 鎖的單元測試設計

```java
@ExtendWith(MockitoExtension.class)
class CartServiceLockTest {

    @Mock CartRepository cartRepository;
    @Mock RedissonClient redissonClient;
    @Mock RLock rLock;

    @InjectMocks CartService cartService;

    @BeforeEach
    void setUp() throws InterruptedException {
        when(redissonClient.getLock(anyString())).thenReturn(rLock);
        when(rLock.tryLock(anyLong(), anyLong(), any(TimeUnit.class))).thenReturn(true);
        when(rLock.isHeldByCurrentThread()).thenReturn(true);
    }

    // 驗證鎖的 key 是 per-user 的
    @Test
    void addToCart_shouldAcquireLockWithUserScopedKey() {
        cartService.addToCart(dto, product, user);  // user.getId() = 42
        verify(redissonClient).getLock("cart:user:42");
    }

    // 驗證 tryLock 在 save 之前呼叫（順序很重要）
    @Test
    void addToCart_shouldCallTryLockBeforeSave() throws InterruptedException {
        InOrder order = inOrder(rLock, cartRepository);
        cartService.addToCart(dto, product, user);
        order.verify(rLock).tryLock(anyLong(), anyLong(), eq(TimeUnit.SECONDS));
        order.verify(cartRepository).save(any(Cart.class));
    }

    // 驗證拿不到鎖時，DB 操作完全不執行
    @Test
    void addToCart_shouldThrow_whenTryLockFails() throws InterruptedException {
        when(rLock.tryLock(anyLong(), anyLong(), any())).thenReturn(false);
        assertThrows(RuntimeException.class, () -> cartService.addToCart(dto, product, user));
        verify(cartRepository, never()).save(any());  // ← DB 完全不觸碰
    }

    // 驗證不同用戶使用不同的鎖
    @Test
    void addToCart_differentUsers_shouldAcquireDifferentLocks() throws InterruptedException {
        User user2 = new User(); user2.setId(99);
        RLock lock2 = mock(RLock.class);
        when(redissonClient.getLock("cart:user:99")).thenReturn(lock2);
        when(lock2.tryLock(anyLong(), anyLong(), any())).thenReturn(true);
        when(lock2.isHeldByCurrentThread()).thenReturn(true);

        cartService.addToCart(dto, product, user);   // user id=42
        cartService.addToCart(dto, product, user2);  // user id=99

        // 兩個不同的鎖，各自 lock/unlock，互不影響
        verify(rLock).unlock();
        verify(lock2).unlock();
    }
}
```

---

## 方案五：讀寫分離路由（AbstractRoutingDataSource）

### 為什麼需要讀寫分離？

當寫入請求（addToCart、placeOrder）被鎖序列化後，DB 的寫入壓力可控。但讀取操作（listProducts、listOrders、getUser）依然是大量並發的，這些都打在 Primary MySQL 上。

**讀寫分離**讓讀取請求走 Replica，寫入請求走 Primary：
- Primary 的負載大幅降低，對寫入吞吐量的影響最小化
- Replica 可以部署在不同硬體，甚至不同地區（降低讀取延遲）
- Primary 故障時，可以提升 Replica 為 Primary（HA）

### DataSourceConfig 深入解析

```java
@Configuration
@ConditionalOnProperty(name = "app.datasource.replica.enabled", havingValue = "true")
public class DataSourceConfig {

    static final String KEY_PRIMARY = "primary";
    static final String KEY_REPLICA = "replica";

    @Bean("primaryDataSource")
    @ConfigurationProperties(prefix = "app.datasource.primary")
    public DataSource primaryDataSource() {
        return DataSourceBuilder.create().build();  // 從 app.datasource.primary.* 讀設定
    }

    @Bean("replicaDataSource")
    @ConfigurationProperties(prefix = "app.datasource.replica")
    public DataSource replicaDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Primary
    @Bean
    public DataSource dataSource(
            @Qualifier("primaryDataSource") DataSource primary,
            @Qualifier("replicaDataSource") DataSource replica) {

        RoutingDataSource routing = new RoutingDataSource();
        Map<Object, Object> targets = new HashMap<>();
        targets.put(KEY_PRIMARY, primary);
        targets.put(KEY_REPLICA, replica);
        routing.setTargetDataSources(targets);
        routing.setDefaultTargetDataSource(primary);
        routing.afterPropertiesSet();  // 必須呼叫，初始化路由表

        // 關鍵：用 LazyConnectionDataSourceProxy 包裝（詳見下方說明）
        return new LazyConnectionDataSourceProxy(routing);
    }

    static class RoutingDataSource extends AbstractRoutingDataSource {
        @Override
        protected Object determineCurrentLookupKey() {
            // 根據當前事務的 readOnly 標記決定路由
            return TransactionSynchronizationManager.isCurrentTransactionReadOnly()
                    ? KEY_REPLICA
                    : KEY_PRIMARY;
        }
    }
}
```

#### `@ConditionalOnProperty` 的設計意圖

```properties
# 預設不啟用讀寫分離（單機開發環境不需要 Replica）
# app.datasource.replica.enabled=false  ← 默認

# 生產環境才啟用
app.datasource.replica.enabled=true
app.datasource.primary.jdbc-url=jdbc:mysql://primary-host:3306/shopping_cart
app.datasource.replica.jdbc-url=jdbc:mysql://replica-host:3306/shopping_cart
```

用功能開關（feature flag）控制是否啟用讀寫分離，讓開發環境和生產環境使用同一份程式碼，而不需要修改任何業務邏輯。

### LazyConnectionDataSourceProxy：解決路由時機的關鍵

這是這個實作中最容易踩坑的地方。

**問題：Spring 的 transaction manager 何時取得 DB 連線？**

```
沒有 LazyConnectionDataSourceProxy 的執行順序：

1. 請求進入 @Transactional 方法
2. Spring 的 TransactionManager：立刻呼叫 DataSource.getConnection()
   → 此時 TransactionSynchronizationManager.isCurrentTransactionReadOnly() = false（還沒設！）
   → 路由到 PRIMARY
3. TransactionManager 設定 readOnly 標記
4. SQL 開始執行（但已經在 PRIMARY 連線上了）
```

`AbstractRoutingDataSource.determineCurrentLookupKey()` 在 `getConnection()` 時被呼叫，但 `readOnly` 標記在 `getConnection()` 之後才被設定，所以路由永遠返回 PRIMARY。

**解法：**

```
有 LazyConnectionDataSourceProxy 的執行順序：

1. 請求進入 @Transactional 方法
2. TransactionManager：呼叫 DataSource.getConnection()
   → LazyConnectionDataSourceProxy 返回一個「假」的 Proxy Connection，不實際建立連線
3. TransactionManager 設定 readOnly 標記
4. 第一個 SQL 執行時，Proxy 才真正呼叫底層的 getConnection()
   → 此時 readOnly 已設定 → 路由到 REPLICA ✅
```

```java
// LazyConnectionDataSourceProxy 把真實的 getConnection() 延遲到第一個 SQL 執行時
return new LazyConnectionDataSourceProxy(routing);
```

### `jakarta.transaction.Transactional` 的坑

這是一個很容易踩到的細節。Jakarta EE 的 `@Transactional` 不支援 `readOnly` 屬性：

```java
// ❌ 這個不支援 readOnly — jakarta.transaction.Transactional 沒有 readOnly
import jakarta.transaction.Transactional;

@Transactional(readOnly = true)  // 編譯錯誤：readOnly 不存在
public List<Order> listOrders(User user) { ... }

// ✅ 必須用 Spring 的 @Transactional
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)  // 正確：Spring 版本支援 readOnly
public List<Order> listOrders(User user) { ... }
```

當你在 Spring Boot 3.x 從 `javax.*` 遷移到 `jakarta.*` 時，很容易不小心把 `@Transactional` 也一起換成 `jakarta` 版本，導致讀寫分離路由失效。

### 路由的單元測試

```java
class DataSourceRoutingTest {

    private Object routingDataSource;
    private Method determineKey;

    @BeforeEach
    void setUp() throws Exception {
        // 用反射實例化 package-private 的 RoutingDataSource 內部類別
        Class<?> routingClass = null;
        for (Class<?> c : DataSourceConfig.class.getDeclaredClasses()) {
            if (c.getSimpleName().equals("RoutingDataSource")) {
                routingClass = c;
                break;
            }
        }
        routingDataSource = routingClass.getDeclaredConstructor().newInstance();
        determineKey = routingClass.getDeclaredMethod("determineCurrentLookupKey");
        determineKey.setAccessible(true);
        TransactionSynchronizationManager.initSynchronization();
    }

    @Test
    void readOnlyTransaction_shouldRouteToReplica() throws Exception {
        TransactionSynchronizationManager.setCurrentTransactionReadOnly(true);
        assertEquals(DataSourceConfig.KEY_REPLICA, determineKey.invoke(routingDataSource));
    }

    @Test
    void writeTransaction_shouldRouteToPrimary() throws Exception {
        TransactionSynchronizationManager.setCurrentTransactionReadOnly(false);
        assertEquals(DataSourceConfig.KEY_PRIMARY, determineKey.invoke(routingDataSource));
    }

    @Test
    void toggleBetweenReadAndWrite_shouldSwitchCorrectly() throws Exception {
        TransactionSynchronizationManager.setCurrentTransactionReadOnly(true);
        assertEquals(DataSourceConfig.KEY_REPLICA, determineKey.invoke(routingDataSource));

        TransactionSynchronizationManager.setCurrentTransactionReadOnly(false);
        assertEquals(DataSourceConfig.KEY_PRIMARY, determineKey.invoke(routingDataSource));
    }
}
```

這個測試直接操作 `TransactionSynchronizationManager`，驗證路由邏輯本身，不需要任何資料庫或 Spring Context。

---

## 方案七：Docker HA 水平擴展

### 生產架構設計

```
                         Internet
                             ↓
                       Nginx (反向代理)
                    /         |          \
           App Instance 1  App 2      App 3
                    \         |          /
                      Redis (快取 + 鎖)
                             ↓
                    MySQL Primary (讀寫)
                             ↓
                    MySQL Replica (唯讀)
```

### docker-compose-ha.yml 架構

```yaml
services:
  # Nginx 作為 L7 負載均衡器
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - app1
      - app2

  # 多個 App 實例（水平擴展）
  app1:
    build: .
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      - APP_DATASOURCE_REPLICA_ENABLED=true
      - APP_DATASOURCE_PRIMARY_JDBC_URL=jdbc:mysql://mysql-primary:3306/shopping_cart
      - APP_DATASOURCE_REPLICA_JDBC_URL=jdbc:mysql://mysql-replica:3306/shopping_cart
      - SPRING_DATA_REDIS_HOST=redis

  app2:
    build: .
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      # ... 相同設定

  # Redis（單節點，生產環境考慮 Redis Sentinel 或 Cluster）
  redis:
    image: redis:7-alpine
    command: redis-server --save 60 1 --loglevel warning

  # MySQL Primary（接受讀寫）
  mysql-primary:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: shopping_cart
    command:
      - --server-id=1
      - --log-bin=mysql-bin
      - --binlog-format=ROW
      - --gtid-mode=ON            # 啟用 GTID 複製，比傳統 binlog position 更可靠
      - --enforce-gtid-consistency=ON

  # MySQL Replica（唯讀，只接受從 Primary 複製的寫入）
  mysql-replica:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: shopping_cart
    command:
      - --server-id=2
      - --read-only=ON            # 拒絕直接的寫入請求
      - --gtid-mode=ON
      - --enforce-gtid-consistency=ON
```

### Nginx 設定

```nginx
upstream shopping_cart_backend {
    least_conn;                     # 把請求導到連線數最少的實例（比 round-robin 更均勻）
    server app1:9999;
    server app2:9999;
    keepalive 32;                   # 保持 32 個長連線，避免每次請求都重新 TCP 握手
}

server {
    listen 80;

    # 限速：每個 IP 每秒最多 100 個請求（防止單一 IP 的惡意攻擊或 bug 導致的請求風暴）
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200 nodelay;

    location / {
        proxy_pass         http://shopping_cart_backend;
        proxy_http_version 1.1;
        proxy_set_header   Connection "";             # 支援 HTTP/1.1 keepalive
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;   # 傳遞真實 IP（用於日誌和限速）
        proxy_read_timeout 30s;
    }
}
```

### Session 一致性：無狀態設計的重要性

當有多個 App 實例時，用戶的同一個 Session 可能打到不同的實例。如果 Session 存在本地記憶體（默認設定），就會出現：

```
請求 1 → App 1：登入成功，Session 存在 App 1 記憶體
請求 2 → App 2（Nginx 負載均衡）：找不到 Session → 要求重新登入
```

這個系統用 Token（JWT-like 的 auth_token）做驗證，Token 存在 MySQL 並快取在 Redis，**沒有本地 Session**，天然支援水平擴展。這是微服務和容器化部署的基本前提。

### 多階段 Docker Build

```dockerfile
# Stage 1：用 Maven 編譯
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -q   # 預先下載依賴（利用 Docker layer cache）
COPY src ./src
RUN mvn package -DskipTests -q

# Stage 2：只複製 JAR，不帶 Maven 工具和源碼
FROM eclipse-temurin:17-jre-alpine  # Alpine 映像，比 ubuntu 小 80%
WORKDIR /app
COPY --from=builder /build/target/*.jar app.jar

# JVM 調校（針對容器環境）
ENV JAVA_OPTS="-XX:+UseContainerSupport \
               -XX:MaxRAMPercentage=75.0 \
               -XX:+ExitOnOutOfMemoryError"
# UseContainerSupport：JVM 讀取 Docker 的 cgroup 限制，而非主機記憶體
# MaxRAMPercentage：使用容器最大記憶體的 75%（剩餘給 OS 和 off-heap）
# ExitOnOutOfMemoryError：OOM 時讓 container 重啟，而不是讓 JVM 在殭屍狀態繼續跑

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

---

## 三個方案的整合視角

把 Part 1 和 Part 2 的所有方案放在一起看：

```
用戶請求
   ↓
Nginx（限速 + 負載均衡）
   ↓
App Instance（Virtual Threads 處理 I/O 密集操作）
   ├── 讀取操作
   │   ├── Redis 快取命中 → 直接回傳（微秒）
   │   └── 快取未命中
   │       ├── @Transactional(readOnly=true)
   │       └── LazyProxy + RoutingDataSource → MySQL Replica
   │
   └── 寫入操作
       ├── Redisson 分散式鎖（per-user，fail-fast）
       │   └── tryLock 成功 → 繼續
       │       tryLock 失敗 → 立刻返回錯誤（保護執行緒池）
       ├── @Transactional → MySQL Primary（HikariCP pool size=50）
       └── Commit 後釋放鎖 + 同步更新 Redis 快取（@CacheEvict）
```

### 各層故障的影響分析

| 元件故障 | 影響範圍 | 降級策略 |
|---------|---------|---------|
| Nginx 單點 | 全站不可用 | 多 Nginx 實例 + VIP（Keepalived） |
| App 一個實例 | Nginx 自動將流量切到其他實例 | 健康檢查 + 自動剔除 |
| Redis 故障 | 快取失效（讀壓力轉到 DB）、鎖失效（可能重複下單） | Redis Sentinel / Cluster |
| MySQL Replica 故障 | 讀取全走 Primary，負載增加 | `@ConditionalOnProperty` 切回單一 DataSource |
| MySQL Primary 故障 | 寫入不可用 | 手動或自動 promote Replica |

---

## 小結：兩篇的演進路徑

```
出發點：默認的 Spring Boot + MySQL
  ↓ PR #227
方案 1：Virtual Threads（吞吐量）
方案 2：HikariCP 調校（連線池）
方案 3：Redis 快取（熱點讀取）
  ↓ PR #228
方案 4：Redisson 分散式鎖（寫入正確性）
方案 5：讀寫分離路由（讀取擴展性）
方案 7：Docker HA（水平擴展 + 可用性）
```

每個改造都是為了解決上一個改造暴露的新問題：

- 吞吐量提升 → 並發寫入問題浮現 → 加分散式鎖
- 鎖序列化寫入 → 讀取仍是瓶頸 → 讀寫分離
- 單機容量見頂 → 水平擴展

這就是高並發系統演進的典型路徑：**不是一開始就設計「完美」的架構，而是根據實際瓶頸逐步演進。**

完整程式碼見：[PR #228 - ShoppingCart-dev-009-high-concurrency-pt-2](https://github.com/yennanliu/SpringPlayground/pull/228)

---

**系列導覽**

- [第一篇](/posts/shopping-cart-high-concurrency-part1-zh/)：Virtual Threads、HikariCP、Redis 快取
- **第二篇（本篇）**：Redisson 分散式鎖、讀寫分離路由、水平擴展與 Docker HA
