---
title: "購物車系統的高並發改造：Virtual Threads、HikariCP 與 Redis 快取三管齊下"
date: 2026-05-24T09:00:00+08:00
draft: false
description: "深入剖析一個真實 Spring Boot 購物車系統如何從「默認設定」升級到能承受 C10K 的生產級高並發架構：JDK 21 Virtual Threads、HikariCP 連線池調校、Redis 分層快取設計，以及升級到 Spring Boot 3.2 過程中的關鍵踩坑。"
categories: ["Engineering", "Architecture", "all"]
tags: ["Spring Boot", "Java", "High Concurrency", "Redis", "HikariCP", "Virtual Threads", "Backend", "繁體中文"]
authors: ["YennJ12 Engineering Team"]
readTime: "30 min"
---

## 前言

電商系統有一個非常典型的流量特徵：平時風平浪靜，一到促銷活動瞬間湧入幾千上萬個並發請求。

如果你的購物車系統跑在默認的 Spring Boot 設定上，這個瞬間幾乎必定會讓系統崩潰——不是 OOM，就是資料庫連線耗盡，要不然就是 Tomcat 執行緒池打滿、請求開始逾時。

這篇文章深入剖析我們在 [PR #227](https://github.com/yennanliu/SpringPlayground/pull/227) 中對一個 Spring Boot 購物車系統進行的高並發改造，涵蓋三個核心技術方向：

1. **JDK 21 Virtual Threads**：讓每個請求都跑在輕量級虛擬執行緒上
2. **HikariCP 連線池調校**：消除資料庫連線成為瓶頸的問題
3. **Redis 分層快取**：把熱點讀取從資料庫移到記憶體

---

## 系統架構概述

先看清楚我們在改什麼。這是一個標準的 Spring Boot 電商後端：

```
Client (Web/App)
    ↓  HTTP
Spring Boot API (port 9999)
    ├── CartController      → CartService → MySQL (cart table)
    ├── ProductController   → ProductService → MySQL (products table)
    ├── OrderController     → OrderService → MySQL (orders/order_items)
    │                                      → Stripe API (付款)
    ├── UserController      → UserService → MySQL (users)
    └── AuthController      → AuthenticationService → MySQL (auth_tokens)
```

技術棧：Spring Boot 3.2.5 / JPA + Hibernate / MySQL / Redis / Stripe

**幾個重要的資料流特徵：**

- 每個 API 請求都會呼叫 `AuthenticationService.getUser(token)` 做驗證（高頻讀取）
- 商品列表 `ProductService.listProducts()` 是最高流量的端點（讀多寫少）
- 加入購物車 `CartService.addToCart()` 在促銷時有大量並發寫入
- 結帳 `OrderService.placeOrder()` 需要跨多張表的事務操作 + 外部 Stripe API 呼叫

---

## 改造前的問題分析

讓我們先看問題在哪。以下是 Spring Boot 默認設定下，系統在高流量時的崩潰路徑：

### 瓶頸一：Tomcat 執行緒池

Spring Boot 預設的 Tomcat 有 200 個執行緒（`server.tomcat.threads.max=200`）。

每個 HTTP 請求佔用一個執行緒，執行完才釋放。但如果請求需要等待 I/O（查資料庫、呼叫 Stripe API），這個執行緒就**阻塞等待**，什麼都不能做。

```
1000 個並發請求到達
→ 200 個執行緒立刻被佔滿
→ 800 個請求在佇列中等待
→ 等待超過 timeout → 返回 503
```

### 瓶頸二：資料庫連線池耗盡

HikariCP 預設的 `maximum-pool-size = 10`。

```
200 個執行緒 → 同時需要資料庫連線
→ 只有 10 個連線可用
→ 190 個執行緒等待連線（connection timeout 預設 30 秒）
→ 全部逾時，大量請求失敗
```

### 瓶頸三：重複的高頻資料庫查詢

`AuthenticationService.getUser(token)` 在**每一個** API 請求都會被呼叫，直接打 MySQL：

```sql
SELECT * FROM auth_tokens WHERE token = ?
-- 再 JOIN user 表
SELECT * FROM users WHERE id = ?
```

1000 個並發請求 = 最少 2000 次相同結構的 DB 查詢。

---

## 方案一：JDK 21 Virtual Threads

### 原理

傳統的 Platform Thread（平台執行緒）是 OS 執行緒的 1:1 映射，每個執行緒預設佔 1MB 的 Stack 記憶體，且當 I/O 阻塞時，OS 執行緒也跟著阻塞。

JDK 21 引入的 **Virtual Threads**（虛擬執行緒）是 JVM 管理的輕量執行緒：
- 初始 Stack 只有幾 KB，可以動態擴展
- 當遇到 I/O 阻塞（JDBC、HTTP client、Sleep），JVM **自動把虛擬執行緒卸載**，把底層平台執行緒讓給其他任務
- I/O 完成後，再把虛擬執行緒重新掛載到任何可用的平台執行緒上繼續執行

```
Virtual Thread 遇到 JDBC 等待：
  JVM: 把這個 vthread 的狀態存起來，把平台執行緒還給 carrier pool
       → 繼續執行其他 vthread
  JDBC 完成: 重新掛載 vthread → 繼續執行
```

這讓你可以用幾百萬個虛擬執行緒處理並發請求，而不需要佔用幾百萬個 OS 執行緒。

### 啟用方式

Spring Boot 3.2+ 整合了 JDK 21 Virtual Threads，只需一行設定：

```properties
# application.properties
# Approach 1 — Virtual Threads (JDK 21 + Spring Boot 3.2)
# REQUIRES Java 21. Each HTTP request gets a lightweight virtual thread.
spring.threads.virtual.enabled=true
```

Spring Boot 會自動把 Tomcat 的執行緒池換成 Virtual Thread executor，**每個請求都跑在自己的虛擬執行緒上**，不再受 Tomcat 執行緒數限制。

### 為什麼購物車系統特別適合 Virtual Threads？

購物車的大多數操作都是 **I/O 密集型**：

```
addToCart 流程：
  1. 驗證 token → JDBC 查詢（I/O）
  2. 查商品 → JDBC 查詢（I/O）
  3. 儲存 Cart → JDBC 寫入（I/O）

placeOrder 流程：
  1. 驗證 token → JDBC（I/O）
  2. 查購物車 → JDBC（I/O）
  3. 儲存 Order → JDBC（I/O）
  4. 呼叫 Stripe API → HTTP（I/O，最慢！幾百毫秒）
  5. 清空購物車 → JDBC（I/O）
```

Virtual Thread 在所有這些 I/O 等待點都能把平台執行緒讓出，效率極高。

### 注意事項

Virtual Threads 不適合 CPU 密集型任務（例如圖片處理、加密運算），這些工作用傳統的固定執行緒池更合適。此外，舊版 MySQL connector（`mysql-connector-java`）有些 native 方法不支援 Virtual Thread 的 pinning unpark，需要升級到 `mysql-connector-j`。

---

## 方案二：HikariCP 連線池調校

### 問題根源

即使有 Virtual Threads，資料庫連線依然是**有限資源**。一個 Virtual Thread 在等 DB 連線時，仍然是被掛起等待，只是不浪費平台執行緒了。

但如果連線池只有 10 個連線，1000 個並發請求還是要排隊等待，造成延遲堆積。

### 配置調整

```properties
# application.properties
# Approach 2 — HikariCP connection pool tuning
# Default pool (10) is the first bottleneck under concurrency.
# Keep total connections < MySQL max_connections (default 151).
spring.datasource.hikari.maximum-pool-size=50
spring.datasource.hikari.minimum-idle=10
spring.datasource.hikari.connection-timeout=3000        # 等待連線最多 3 秒
spring.datasource.hikari.idle-timeout=600000            # 閒置 10 分鐘後關閉
spring.datasource.hikari.max-lifetime=1800000           # 連線最多存活 30 分鐘
spring.datasource.hikari.pool-name=ShoppingCartHikariPool
```

### 為什麼是 50，不是 200？

這是一個常見的誤解：把 pool size 調得越大越好。

**錯誤**：`maximum-pool-size=500`

MySQL 有一個硬限制：`max_connections`，預設是 151。超過這個數字，MySQL 會直接拒絕連線請求。

還有一個更深層的問題：MySQL 處理每個連線是用**一個 OS 執行緒**。連線數太多，OS 執行緒的切換開銷（context switch）反而比「多等一點」還要貴。

**HikariCP 的官方建議**（Pool Sizing for HikariCP）：

```
最佳 pool size ≈ 核心數 × 2 + 有效的磁碟並行數
```

對一台 8 核的應用伺服器，理論最佳值大約是 17-20。我們設定 50 是因為：
- 考慮到多個應用實例共用 MySQL（`50 × n_instances < 151`）
- 購物車的查詢通常很短，連線快速釋放
- 保留一定緩衝給 DBA 工具和監控系統使用

### 搭配 Virtual Threads 的效果

```
Virtual Threads 的作用：讓平台執行緒不被 I/O 阻塞
HikariCP 的作用：確保有足夠的 DB 連線可用

兩者配合：
  1000 個請求 → 1000 個 Virtual Threads
  → 同時有 50 個在執行 DB 操作（有連線）
  → 其餘 950 個等待連線時被 suspend（不佔平台執行緒）
  → 連線釋放 → 下一個 vthread 繼續
  → 整個過程中，平台執行緒幾乎不閒著
```

---

## 方案三：Redis 分層快取

### 設計思路

不是所有資料都要快取。我們根據三個維度來決定：

| 資料 | 讀取頻率 | 變化頻率 | 快取策略 |
|------|---------|---------|---------|
| Token → User 映射 | **極高**（每個請求都要） | 低（用戶重新登入時） | 快取，15 分鐘 TTL |
| 商品列表 | **高**（首頁、搜尋） | 低（上下架時） | 快取，5 分鐘 TTL |
| 分類列表 | **高**（每頁都需要） | **極低**（幾乎不變） | 快取，30 分鐘 TTL |
| 購物車內容 | 中 | 高（用戶每次操作） | **不快取** |
| 訂單 | 低 | 低 | **不快取** |

### RedisConfig 深入解析

```java
@Configuration
public class RedisConfig {

    public static final String CACHE_TOKENS     = "tokens";
    public static final String CACHE_PRODUCTS   = "products";
    public static final String CACHE_CATEGORIES = "categories";

    @Bean
    public CacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        ObjectMapper mapper = new ObjectMapper();
        mapper.findAndRegisterModules();  // 自動載入 JavaTimeModule 等

        // ⚠️ 關鍵安全設定（詳見後文）
        PolymorphicTypeValidator ptv = BasicPolymorphicTypeValidator.builder()
                .allowIfSubType("com.yen.ShoppingCart")
                .allowIfSubType("java.util")
                .allowIfSubType("java.lang")
                .build();

        mapper.activateDefaultTyping(ptv,
                ObjectMapper.DefaultTyping.NON_FINAL,
                JsonTypeInfo.As.PROPERTY);

        GenericJackson2JsonRedisSerializer jsonSerializer =
                new GenericJackson2JsonRedisSerializer(mapper);

        // 預設配置：Key 用字串序列化，Value 用 JSON
        RedisCacheConfiguration defaults = RedisCacheConfiguration.defaultCacheConfig()
                .serializeKeysWith(SerializationPair.fromSerializer(new StringRedisSerializer()))
                .serializeValuesWith(SerializationPair.fromSerializer(jsonSerializer))
                .disableCachingNullValues();

        // 每個 cache 有獨立的 TTL
        Map<String, RedisCacheConfiguration> perCacheTtl = new HashMap<>();
        perCacheTtl.put(CACHE_TOKENS,     defaults.entryTtl(Duration.ofMinutes(15)));
        perCacheTtl.put(CACHE_PRODUCTS,   defaults.entryTtl(Duration.ofMinutes(5)));
        perCacheTtl.put(CACHE_CATEGORIES, defaults.entryTtl(Duration.ofMinutes(30)));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults.entryTtl(Duration.ofMinutes(10)))
                .withInitialCacheConfigurations(perCacheTtl)
                .build();
    }
}
```

### @Cacheable 和 @CacheEvict 的實際運作

**AuthenticationService — Token 快取（最高頻）：**

```java
// 每個請求都呼叫這個方法驗證身分
@Cacheable(
    value = RedisConfig.CACHE_TOKENS,
    key = "#token",
    unless = "#result == null"   // null 不快取，避免快取「無效 token」
)
public User getUser(String token) {
    // 第一次呼叫：查 DB，結果存入 Redis（key = tokens::<token_value>）
    // 後續呼叫：直接從 Redis 返回，不碰 DB
    AuthenticationToken authToken = repository.findTokenByToken(token);
    if (Helper.notNull(authToken) && Helper.notNull(authToken.getUser())) {
        return authToken.getUser();
    }
    return null;
}

// 用戶重新登入時呼叫，必須讓舊 token 的快取失效
@CacheEvict(value = RedisConfig.CACHE_TOKENS, key = "#authenticationToken.token")
public void saveConfirmationToken(AuthenticationToken authenticationToken) {
    repository.save(authenticationToken);
}
```

快取後的流程：

```
1000 個並發請求（帶同一個 token）

沒有快取：
  → 1000 次 DB 查詢（tokens 表 + users 表 JOIN）
  → MySQL 承受 2000 次查詢

有 Redis 快取：
  → 第 1 次：查 DB，存入 Redis
  → 第 2-1000 次：直接讀 Redis（微秒級）
  → MySQL：只有 1 次查詢
```

**ProductService — 商品列表快取（含 Cache Evict 聯動）：**

```java
// 讀取：有快取就直接回傳，沒有才查 DB 並存入快取
@Cacheable(value = RedisConfig.CACHE_PRODUCTS, key = "'all'")
public List<ProductDto> listProducts() {
    List<Product> products = productRepository.findAll();
    // ... 轉換為 DTO
    return productDtos;
}

// 新增商品：必須使快取失效，否則下次讀到的是舊資料
@CacheEvict(value = RedisConfig.CACHE_PRODUCTS, allEntries = true)
public void addProduct(ProductDto productDto, Category category) {
    productRepository.save(getProductFromDto(productDto, category));
}

// 更新商品：同樣要 evict
@CacheEvict(value = RedisConfig.CACHE_PRODUCTS, allEntries = true)
public void updateProduct(Integer productID, ProductDto productDto, Category category) {
    Product product = getProductFromDto(productDto, category);
    product.setId(productID);
    productRepository.save(product);
}
```

`allEntries = true` 的用法：因為我們用 `key = "'all'"` 把整個列表存成一個快取項目，evict 時也要把這個 key 清掉。如果是按 ID 快取個別商品，則可以用 `key = "#productId"` 精確 evict。

### ⚠️ 重要的安全漏洞修復

原始程式碼使用 `LaissezFaireSubTypeValidator`，這是一個**嚴重的安全漏洞**：

```java
// ❌ 舊的不安全設定
mapper.enableDefaultTyping(LaissezFaireSubTypeValidator.instance, ...);
// LaissezFaireSubTypeValidator 接受任意 Java 類型反序列化
// 攻擊者可以在 Redis value 中注入惡意的 gadget chain，觸發 RCE
```

修復後的設定，使用白名單限制可反序列化的型別：

```java
// ✅ 安全的設定：只允許我們自己的 package 和 JDK 標準類型
PolymorphicTypeValidator ptv = BasicPolymorphicTypeValidator.builder()
        .allowIfSubType("com.yen.ShoppingCart")  // 我們的 domain 類型
        .allowIfSubType("java.util")             // List, Map, etc.
        .allowIfSubType("java.lang")             // String, Integer, etc.
        .build();

mapper.activateDefaultTyping(ptv,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.PROPERTY);
```

這個漏洞在 Jackson 2.x 的文件中有明確警告，但很多舊項目仍在使用不安全的設定。任何把 Java 物件序列化到 Redis 的系統都應該檢查這一點。

---

## Spring Boot 2.x → 3.x 升級的關鍵變化

這次升級從 Spring Boot 2.4.5 到 3.2.5，有幾個必須處理的 breaking change：

### javax.* → jakarta.* 命名空間遷移

Spring Boot 3.x 採用 Jakarta EE 9+，所有 `javax.*` import 必須改成 `jakarta.*`：

```java
// ❌ 舊（Spring Boot 2.x）
import javax.persistence.Entity;
import javax.persistence.Table;
import javax.transaction.Transactional;
import javax.validation.constraints.NotNull;

// ✅ 新（Spring Boot 3.x）
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import jakarta.transaction.Transactional;
import jakarta.validation.constraints.NotNull;
```

這個改動遍及所有 Model 類別、Service 和 Repository。

### Validation 變成需要明確引入

Spring Boot 3 預設不再包含 Bean Validation，需要在 `pom.xml` 明確加入：

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

### MySQL connector 名稱更換

```xml
<!-- ❌ 舊 -->
<dependency>
    <groupId>mysql</groupId>
    <artifactId>mysql-connector-java</artifactId>
</dependency>

<!-- ✅ 新 -->
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
</dependency>
```

### Swagger 套件更換

```xml
<!-- ❌ 舊：springfox（已停止維護，不支援 Spring Boot 3） -->
<dependency>
    <groupId>io.springfox</groupId>
    <artifactId>springfox-boot-starter</artifactId>
    <version>3.0.0</version>
</dependency>

<!-- ✅ 新：springdoc-openapi -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.3.0</version>
</dependency>
```

---

## 快取整合測試策略

快取邏輯很容易寫錯（例如 evict 沒有正確觸發），但不需要真的跑 Redis 才能測試。我們用 `ConcurrentMapCacheManager` 替代：

```java
@SpringJUnitConfig(ProductServiceCacheTest.TestConfig.class)
class ProductServiceCacheTest {

    @EnableCaching
    @Configuration
    static class TestConfig {

        @Bean
        public CacheManager cacheManager() {
            // 用 in-memory 實作取代 Redis，不需要 Redis server
            return new ConcurrentMapCacheManager(
                    RedisConfig.CACHE_TOKENS,
                    RedisConfig.CACHE_PRODUCTS,
                    RedisConfig.CACHE_CATEGORIES
            );
        }

        @Bean
        public ProductRepository productRepository() {
            return Mockito.mock(ProductRepository.class);  // Mock DB
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    @Test
    void listProducts_secondCall_shouldHitCacheNotRepo() {
        when(productRepository.findAll()).thenReturn(List.of(product1, product2));

        productService.listProducts();  // 第一次：查 DB
        productService.listProducts();  // 第二次：應該走快取

        // 關鍵驗證：DB 只被呼叫了一次
        verify(productRepository, times(1)).findAll();
    }

    @Test
    void addProduct_shouldEvictProductCache() {
        when(productRepository.findAll()).thenReturn(List.of(product1));
        productService.listProducts();                        // 暖快取
        verify(productRepository, times(1)).findAll();

        productService.addProduct(productDto, category);      // 觸發 evict

        when(productRepository.findAll()).thenReturn(List.of(product1, product2));
        List<ProductDto> afterAdd = productService.listProducts();  // 應重新查 DB

        verify(productRepository, times(2)).findAll();        // 被呼叫了兩次
        assertEquals(2, afterAdd.size());
    }
}
```

這種測試方式：
- **快**：沒有 I/O，毫秒級
- **隔離**：不依賴任何外部服務
- **精準**：直接驗證快取行為，而不是功能行為

---

## 三個方案的效果與適用條件

### 方案比較

| 方案 | 解決的瓶頸 | 實作成本 | 效果 | 適用場景 |
|------|-----------|---------|------|---------|
| Virtual Threads | Tomcat 執行緒池耗盡 | 低（一行設定） | 高（I/O 密集） | JDK 21 + Spring Boot 3.2+ |
| HikariCP 調校 | DB 連線池耗盡 | 低（幾行設定） | 中高 | 所有場景 |
| Redis 快取 | 重複 DB 查詢 | 中（需要 Redis、設計快取策略） | 極高（對熱點讀取） | 讀多寫少的資料 |

### 什麼時候不該快取？

購物車內容（`cart` 表）**刻意不快取**，原因：

1. **一致性要求高**：用戶加入商品後，下一個請求必須看到最新的購物車
2. **寫入頻率高**：每次 addToCart、updateCartItem、deleteCartItem 都需要 evict，快取命中率極低
3. **資料量小**：每個用戶的購物車通常只有幾個商品，查 DB 很快

> **快取的本質是用一致性換取效能。如果資料一致性要求高於可接受的 staleness，就不應該快取。**

---

## 生產環境的進一步優化方向

這次 PR 建立了高並發的基礎，但還有幾個進階方向值得繼續探索：

### 1. 庫存超賣問題（分散式鎖）

目前的 `addToCart` 沒有庫存控制。如果商品有數量限制，需要引入 Redis 分散式鎖：

```java
// 概念示意：使用 Redisson 分散式鎖防止超賣
public void addToCartWithStockCheck(AddToCartDto dto, Product product, User user) {
    String lockKey = "stock:lock:" + product.getId();
    RLock lock = redissonClient.getLock(lockKey);
    try {
        if (lock.tryLock(3, 10, TimeUnit.SECONDS)) {
            // 在鎖保護下檢查並扣減庫存
            int currentStock = getStock(product.getId());
            if (currentStock < dto.getQuantity()) {
                throw new InsufficientStockException("庫存不足");
            }
            decrementStock(product.getId(), dto.getQuantity());
            cartRepository.save(new Cart(product, dto.getQuantity(), user));
        }
    } finally {
        if (lock.isHeldByCurrentThread()) lock.unlock();
    }
}
```

### 2. 非同步訂單處理（消息佇列）

`placeOrder` 呼叫 Stripe API（可能需要幾百毫秒），並同步清空購物車。在高流量下，可以把這個流程改成非同步：

```
用戶確認購買
→ API 立刻回應「訂單建立中」（Order status: PENDING）
→ 把訂單事件放入 Kafka / RabbitMQ
→ 背景 Consumer 非同步處理：呼叫 Stripe、更新庫存、清空購物車
→ 完成後推送通知給用戶
```

### 3. 讀寫分離

當寫入壓力增加，可以配置 MySQL 主從複製，讀請求走 Replica，寫請求走 Primary：

```yaml
# 概念設定（spring.datasource.routing）
datasources:
  primary:   jdbc:mysql://primary-host:3306/shopping_cart
  replica:   jdbc:mysql://replica-host:3306/shopping_cart
```

### 4. 快取一致性的進階處理

目前的 `@CacheEvict` 是同步的。如果有多個應用實例，某個實例 evict 了快取，其他實例的本地快取（如果有的話）不會立刻失效。Redis 是中央快取，這個問題已經解決，但如果未來加入 Caffeine 等本地快取層，需要考慮 **Cache Invalidation** 機制（例如用 Redis Pub/Sub 通知其他實例）。

---

## 小結

這次改造的核心教訓：

**沒有銀彈，高並發需要系統性地消除每一層的瓶頸。**

```
Tomcat 執行緒層：Virtual Threads 讓 I/O 等待不再阻塞平台執行緒
     ↓
資料庫連線層：HikariCP 調校確保有足夠連線，但不超過 DB 的承載能力
     ↓
資料庫查詢層：Redis 快取把高頻讀取攔截在記憶體，不讓 DB 承受重複查詢
```

三個方案有各自的責任邊界，缺一不可。而且每個方案的代價都很低：Virtual Threads 是一行設定，HikariCP 是幾個數字，Redis 快取是幾個 annotation。

最難的部分不是程式碼，而是**知道什麼該快取、什麼不該快取**，以及理解系統在高流量下的真實崩潰路徑。

完整程式碼見：[PR #227 - ShoppingCart-dev-008-high-concurrency](https://github.com/yennanliu/SpringPlayground/pull/227)
