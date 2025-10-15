---
title: "Spring Boot 多環境配置完整指南：開發、測試、生產環境管理"
date: 2025-10-15T10:00:00Z
draft: false
authors: ["yen"]
categories: ["all", "spring-boot", "backend", "devops"]
tags: ["spring-boot", "configuration", "docker", "environment", "redis", "database", "production"]
summary: "深入探討 Spring Boot 多環境配置管理，包括資料庫切換、Redis 配置、以及 Docker 容器化部署的完整實作指南。"
readTime: "18 min"
---

## 🎯 為什麼需要多環境配置？

在現代軟體開發中,應用程式通常需要在多個環境中運行：

### 📋 常見環境類型與挑戰

**開發環境 (Development)**
- 開發人員本地機器
- 使用本地資料庫或輕量級資料庫
- 詳細的日誌輸出便於除錯
- 不需要 Redis 等快取服務

**測試環境 (Staging/UAT)**
- 模擬生產環境的配置
- 使用獨立的測試資料庫
- 啟用效能監控
- 測試與第三方服務的整合

**生產環境 (Production)**
- 正式對外服務的環境
- 高可用性資料庫叢集
- 啟用 Redis 快取提升效能
- 嚴格的安全性與日誌管理

### 🎯 核心需求分析

不同環境需要不同的配置：
- **資料庫連接**：開發環境用本地 MySQL，生產環境用 RDS
- **快取服務**：開發環境不用 Redis，生產環境必須啟用
- **日誌級別**：開發環境 DEBUG，生產環境 INFO/WARN
- **安全設定**：開發環境寬鬆，生產環境嚴格

## 🏗️ Spring Boot 多環境配置架構

### 🔧 Profile 機制原理

Spring Boot 使用 Profile 機制來管理不同環境的配置：

```text
src/main/resources/
├── application.yml                    # 基礎配置（所有環境共用）
├── application-dev.yml               # 開發環境專屬配置
├── application-stage.yml             # 測試環境專屬配置
└── application-prod.yml              # 生產環境專屬配置
```

**配置優先級順序**：
```
1. application-{profile}.yml (最高優先級)
2. application.yml (基礎配置)
3. 環境變數
4. 命令列參數 (最高優先級，可覆蓋所有)
```

### 🎨 配置文件結構設計

**基礎配置檔案 - `application.yml`**

```yaml
# ============================================
# 基礎配置 - 所有環境共用
# ============================================
spring:
  application:
    name: employee-management-system

  # JPA 基礎配置
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        jdbc:
          batch_size: 25

  # 檔案上傳限制
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 5MB

# Server 基礎配置
server:
  port: 8080
  servlet:
    context-path: /api

# Actuator 監控端點
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when-authorized

# 應用程式基本資訊
info:
  app:
    name: ${spring.application.name}
    version: 1.0.0
    description: Employee Management System
```

**開發環境配置 - `application-dev.yml`**

```yaml
# ============================================
# 開發環境配置
# ============================================
spring:
  # H2 記憶體資料庫（快速啟動，無需安裝）
  datasource:
    url: jdbc:h2:mem:devdb
    driver-class-name: org.h2.Driver
    username: sa
    password:
    hikari:
      maximum-pool-size: 5
      minimum-idle: 2

  # JPA 開發設定
  jpa:
    hibernate:
      ddl-auto: create-drop  # 每次啟動重建資料表
    show-sql: true           # 顯示 SQL 語句
    properties:
      hibernate:
        format_sql: true     # SQL 格式化

  # H2 Console 啟用（方便查看資料庫）
  h2:
    console:
      enabled: true
      path: /h2-console

  # Redis 停用（開發環境不需要）
  cache:
    type: simple             # 使用簡單的記憶體快取

  # 開發環境 CORS 設定（允許前端跨域）
  web:
    cors:
      allowed-origins: "http://localhost:3000,http://localhost:8080"
      allowed-methods: "*"
      allowed-headers: "*"

# 日誌配置
logging:
  level:
    root: INFO
    com.employee.system: DEBUG        # 應用程式詳細日誌
    org.springframework.web: DEBUG    # Spring Web 詳細日誌
    org.springframework.security: DEBUG
    org.hibernate.SQL: DEBUG          # SQL 語句日誌
    org.hibernate.type.descriptor.sql.BasicBinder: TRACE  # SQL 參數值
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss} - %msg%n"

# JWT 開發配置（較短的有效期便於測試）
jwt:
  secret: dev-secret-key-change-in-production
  expiration: 3600000      # 1 小時
  refresh-expiration: 86400000  # 1 天

# 檔案上傳路徑
app:
  upload:
    dir: ./uploads/dev
```

**測試環境配置 - `application-stage.yml`**

```yaml
# ============================================
# 測試環境配置
# ============================================
spring:
  # 測試用 MySQL 資料庫
  datasource:
    url: jdbc:mysql://${DB_HOST:localhost}:3306/${DB_NAME:employee_stage}?useSSL=false&serverTimezone=UTC&allowPublicKeyRetrieval=true
    driver-class-name: com.mysql.cj.jdbc.Driver
    username: ${DB_USER:stage_user}
    password: ${DB_PASSWORD:stage_password}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 5
      connection-timeout: 20000
      idle-timeout: 300000
      leak-detection-threshold: 60000

  # JPA 測試設定
  jpa:
    hibernate:
      ddl-auto: validate     # 驗證資料表結構，不自動建立
    show-sql: false
    properties:
      hibernate:
        format_sql: false

  # Redis 部分啟用（測試快取功能）
  redis:
    host: ${REDIS_HOST:localhost}
    port: ${REDIS_PORT:6379}
    password: ${REDIS_PASSWORD:}
    lettuce:
      pool:
        max-active: 8
        max-idle: 8
        min-idle: 2

  cache:
    type: redis
    redis:
      time-to-live: 600000   # 10 分鐘快取

# 日誌配置（平衡詳細度與效能）
logging:
  level:
    root: INFO
    com.employee.system: INFO
    org.springframework.web: INFO
    org.springframework.security: WARN
    org.hibernate.SQL: DEBUG
  file:
    name: ./logs/stage/application.log
    max-size: 10MB
    max-history: 7

# JWT 測試配置
jwt:
  secret: ${JWT_SECRET:stage-secret-key-please-change}
  expiration: 7200000      # 2 小時
  refresh-expiration: 604800000  # 7 天

# 檔案上傳配置
app:
  upload:
    dir: ${UPLOAD_DIR:/app/uploads/stage}
  cors:
    allowed-origins: ${CORS_ORIGINS:http://stage.example.com}
```

**生產環境配置 - `application-prod.yml`**

```yaml
# ============================================
# 生產環境配置
# ============================================
spring:
  # 生產 MySQL 資料庫（使用環境變數）
  datasource:
    url: jdbc:mysql://${DB_HOST}:${DB_PORT:3306}/${DB_NAME}?useSSL=true&requireSSL=true&serverTimezone=UTC
    driver-class-name: com.mysql.cj.jdbc.Driver
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20      # 較大的連接池
      minimum-idle: 10
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000
      leak-detection-threshold: 60000

  # JPA 生產設定
  jpa:
    hibernate:
      ddl-auto: validate         # 僅驗證，絕不自動修改
    show-sql: false              # 不顯示 SQL（效能考量）
    properties:
      hibernate:
        format_sql: false
        jdbc:
          batch_size: 50         # 批次處理提升效能
        order_inserts: true
        order_updates: true

  # Redis 完整啟用（生產環境必須）
  redis:
    host: ${REDIS_HOST}
    port: ${REDIS_PORT:6379}
    password: ${REDIS_PASSWORD}
    ssl: true                    # 啟用 SSL
    timeout: 2000ms
    lettuce:
      pool:
        max-active: 20
        max-idle: 10
        min-idle: 5
        max-wait: 2000ms
      shutdown-timeout: 100ms

  cache:
    type: redis
    redis:
      time-to-live: 1800000      # 30 分鐘快取
      cache-null-values: false   # 不快取 null 值

  # 安全的 CORS 設定
  web:
    cors:
      allowed-origins: ${CORS_ORIGINS}  # 必須從環境變數設定
      allowed-methods: GET,POST,PUT,DELETE
      allowed-headers: Authorization,Content-Type
      allow-credentials: true
      max-age: 3600

# 生產日誌配置（僅記錄重要資訊）
logging:
  level:
    root: WARN
    com.employee.system: INFO
    org.springframework.web: WARN
    org.springframework.security: WARN
    org.hibernate.SQL: WARN
  file:
    name: /var/log/employee-system/application.log
    max-size: 100MB
    max-history: 30
  pattern:
    file: "%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n"

# JWT 生產配置（強安全性）
jwt:
  secret: ${JWT_SECRET}          # 必須從環境變數或密鑰管理服務讀取
  expiration: 3600000            # 1 小時
  refresh-expiration: 2592000000 # 30 天

# 檔案上傳配置
app:
  upload:
    dir: ${UPLOAD_DIR:/app/uploads/prod}
    max-size: 5242880            # 5MB
    allowed-extensions: jpg,jpeg,png,pdf

# Actuator 安全配置
management:
  endpoints:
    web:
      exposure:
        include: health,info     # 僅暴露必要端點
  endpoint:
    health:
      show-details: never        # 不暴露詳細健康資訊

# Server 生產配置
server:
  port: ${SERVER_PORT:8080}
  error:
    include-stacktrace: never    # 不暴露堆疊追蹤
    include-message: never       # 不暴露錯誤訊息
  tomcat:
    threads:
      max: 200                   # 最大執行緒數
      min-spare: 10
    max-connections: 8192        # 最大連接數
    accept-count: 100
```

## 💻 Java 程式碼實作

### 🔧 配置類別設計

**1. 資料庫配置類別 - `DatabaseConfig.java`**

```java
package com.employee.system.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;

/**
 * 資料庫配置類別
 * 根據不同環境提供不同的資料庫配置
 */
@Configuration
@Slf4j
public class DatabaseConfig {

    @Value("${spring.datasource.url}")
    private String jdbcUrl;

    @Value("${spring.datasource.username}")
    private String username;

    @Value("${spring.datasource.password}")
    private String password;

    @Value("${spring.datasource.driver-class-name}")
    private String driverClassName;

    /**
     * 開發環境資料源（H2 記憶體資料庫）
     */
    @Bean
    @Profile("dev")
    public DataSource devDataSource() {
        log.info("====================================");
        log.info("初始化開發環境資料源 (H2 Database)");
        log.info("JDBC URL: {}", jdbcUrl);
        log.info("====================================");

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        config.setDriverClassName(driverClassName);

        // 開發環境較小的連接池
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(20000);

        return new HikariDataSource(config);
    }

    /**
     * 測試環境資料源（MySQL）
     */
    @Bean
    @Profile("stage")
    public DataSource stageDataSource() {
        log.info("====================================");
        log.info("初始化測試環境資料源 (MySQL)");
        log.info("JDBC URL: {}", jdbcUrl);
        log.info("====================================");

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        config.setDriverClassName(driverClassName);

        // 測試環境中等連接池
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(5);
        config.setConnectionTimeout(20000);
        config.setLeakDetectionThreshold(60000);

        return new HikariDataSource(config);
    }

    /**
     * 生產環境資料源（MySQL with 優化配置）
     */
    @Bean
    @Profile("prod")
    public DataSource prodDataSource() {
        log.info("====================================");
        log.info("初始化生產環境資料源 (MySQL Production)");
        log.info("JDBC URL: {}", maskPassword(jdbcUrl));
        log.info("====================================");

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        config.setDriverClassName(driverClassName);

        // 生產環境較大的連接池
        config.setMaximumPoolSize(20);
        config.setMinimumIdle(10);
        config.setConnectionTimeout(30000);
        config.setIdleTimeout(600000);
        config.setMaxLifetime(1800000);
        config.setLeakDetectionThreshold(60000);

        // 生產環境額外配置
        config.addDataSourceProperty("cachePrepStmts", "true");
        config.addDataSourceProperty("prepStmtCacheSize", "250");
        config.addDataSourceProperty("prepStmtCacheSqlLimit", "2048");
        config.addDataSourceProperty("useServerPrepStmts", "true");

        return new HikariDataSource(config);
    }

    /**
     * 遮蔽密碼資訊（安全性）
     */
    private String maskPassword(String url) {
        if (url.contains("password=")) {
            return url.replaceAll("password=[^&]*", "password=****");
        }
        return url;
    }
}
```

**2. Redis 配置類別 - `RedisConfig.java`**

```java
package com.employee.system.config;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.impl.LaissezFaireSubTypeValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * Redis 快取配置
 * 開發環境停用，測試/生產環境啟用
 */
@Configuration
@EnableCaching
@Slf4j
public class RedisConfig {

    @Value("${spring.redis.host:localhost}")
    private String redisHost;

    @Value("${spring.redis.port:6379}")
    private int redisPort;

    @Value("${spring.redis.password:}")
    private String redisPassword;

    /**
     * 開發環境：使用簡單的記憶體快取（不需要 Redis）
     */
    @Bean
    @Profile("dev")
    public CacheManager devCacheManager() {
        log.info("====================================");
        log.info("開發環境：使用簡單記憶體快取（無 Redis）");
        log.info("====================================");
        return new org.springframework.cache.concurrent.ConcurrentMapCacheManager();
    }

    /**
     * 測試/生產環境：使用 Redis
     */
    @Bean
    @Profile({"stage", "prod"})
    public LettuceConnectionFactory redisConnectionFactory() {
        log.info("====================================");
        log.info("初始化 Redis 連接");
        log.info("Redis Host: {}", redisHost);
        log.info("Redis Port: {}", redisPort);
        log.info("====================================");

        RedisStandaloneConfiguration config = new RedisStandaloneConfiguration();
        config.setHostName(redisHost);
        config.setPort(redisPort);

        if (redisPassword != null && !redisPassword.isEmpty()) {
            config.setPassword(redisPassword);
        }

        return new LettuceConnectionFactory(config);
    }

    /**
     * Redis Template 配置
     */
    @Bean
    @Profile({"stage", "prod"})
    public RedisTemplate<String, Object> redisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        // Jackson 序列化配置
        Jackson2JsonRedisSerializer<Object> jackson2JsonRedisSerializer =
            new Jackson2JsonRedisSerializer<>(Object.class);

        ObjectMapper objectMapper = new ObjectMapper();
        objectMapper.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.ANY);
        objectMapper.activateDefaultTyping(
            LaissezFaireSubTypeValidator.instance,
            ObjectMapper.DefaultTyping.NON_FINAL
        );

        jackson2JsonRedisSerializer.setObjectMapper(objectMapper);

        // String 序列化
        StringRedisSerializer stringRedisSerializer = new StringRedisSerializer();

        // Key 使用 String 序列化
        template.setKeySerializer(stringRedisSerializer);
        template.setHashKeySerializer(stringRedisSerializer);

        // Value 使用 JSON 序列化
        template.setValueSerializer(jackson2JsonRedisSerializer);
        template.setHashValueSerializer(jackson2JsonRedisSerializer);

        template.afterPropertiesSet();

        return template;
    }

    /**
     * Redis Cache Manager 配置
     */
    @Bean
    @Profile({"stage", "prod"})
    public CacheManager redisCacheManager(RedisConnectionFactory connectionFactory) {
        log.info("====================================");
        log.info("初始化 Redis Cache Manager");
        log.info("====================================");

        // 預設快取配置
        RedisCacheConfiguration defaultConfig = RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(30))  // 預設 30 分鐘過期
            .serializeKeysWith(
                RedisSerializationContext.SerializationPair.fromSerializer(
                    new StringRedisSerializer()))
            .serializeValuesWith(
                RedisSerializationContext.SerializationPair.fromSerializer(
                    new Jackson2JsonRedisSerializer<>(Object.class)))
            .disableCachingNullValues();  // 不快取 null 值

        // 不同快取的個別配置
        Map<String, RedisCacheConfiguration> cacheConfigurations = new HashMap<>();

        // 員工資料快取：1 小時
        cacheConfigurations.put("employees",
            defaultConfig.entryTtl(Duration.ofHours(1)));

        // 部門資料快取：2 小時（較少變動）
        cacheConfigurations.put("departments",
            defaultConfig.entryTtl(Duration.ofHours(2)));

        // 使用者資料快取：30 分鐘
        cacheConfigurations.put("users",
            defaultConfig.entryTtl(Duration.ofMinutes(30)));

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(cacheConfigurations)
            .transactionAware()
            .build();
    }
}
```

**3. 環境感知服務類別 - `EnvironmentService.java`**

```java
package com.employee.system.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.util.Arrays;

/**
 * 環境資訊服務
 * 提供當前運行環境的資訊
 */
@Service
@Slf4j
public class EnvironmentService {

    @Autowired
    private Environment environment;

    @Value("${spring.datasource.url:N/A}")
    private String datasourceUrl;

    @Value("${spring.redis.host:N/A}")
    private String redisHost;

    @Value("${spring.cache.type:N/A}")
    private String cacheType;

    /**
     * 應用程式啟動時顯示環境資訊
     */
    @PostConstruct
    public void displayEnvironmentInfo() {
        String[] activeProfiles = environment.getActiveProfiles();
        String profile = activeProfiles.length > 0 ? activeProfiles[0] : "default";

        log.info("========================================");
        log.info("🚀 應用程式環境資訊");
        log.info("========================================");
        log.info("當前環境: {}", profile.toUpperCase());
        log.info("資料庫 URL: {}", maskSensitiveInfo(datasourceUrl));
        log.info("快取類型: {}", cacheType);
        log.info("Redis 主機: {}", redisHost);
        log.info("========================================");
    }

    /**
     * 檢查是否為開發環境
     */
    public boolean isDevelopment() {
        return Arrays.asList(environment.getActiveProfiles()).contains("dev");
    }

    /**
     * 檢查是否為測試環境
     */
    public boolean isStaging() {
        return Arrays.asList(environment.getActiveProfiles()).contains("stage");
    }

    /**
     * 檢查是否為生產環境
     */
    public boolean isProduction() {
        return Arrays.asList(environment.getActiveProfiles()).contains("prod");
    }

    /**
     * 檢查 Redis 是否啟用
     */
    public boolean isRedisEnabled() {
        return "redis".equalsIgnoreCase(cacheType);
    }

    /**
     * 取得當前環境名稱
     */
    public String getCurrentEnvironment() {
        String[] profiles = environment.getActiveProfiles();
        return profiles.length > 0 ? profiles[0] : "default";
    }

    /**
     * 遮蔽敏感資訊
     */
    private String maskSensitiveInfo(String info) {
        if (info.contains("password=")) {
            info = info.replaceAll("password=[^&]*", "password=****");
        }
        return info;
    }
}
```

**4. Service 層使用快取 - `EmployeeService.java`**

```java
package com.employee.system.service;

import com.employee.system.dto.EmployeeDto;
import com.employee.system.entity.Employee;
import com.employee.system.repository.EmployeeRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 員工服務類別
 * 展示如何使用快取註解
 */
@Service
@Slf4j
@Transactional
public class EmployeeService {

    @Autowired
    private EmployeeRepository employeeRepository;

    @Autowired
    private EnvironmentService environmentService;

    /**
     * 根據 ID 查詢員工（使用快取）
     * 開發環境：記憶體快取
     * 測試/生產環境：Redis 快取
     */
    @Cacheable(value = "employees", key = "#id", unless = "#result == null")
    public EmployeeDto getEmployeeById(Long id) {
        log.info("從資料庫查詢員工 ID: {} (環境: {})",
                 id, environmentService.getCurrentEnvironment());

        Employee employee = employeeRepository.findById(id)
            .orElseThrow(() -> new RuntimeException("員工不存在: " + id));

        return convertToDto(employee);
    }

    /**
     * 查詢所有員工（使用快取）
     */
    @Cacheable(value = "employees", key = "'all'")
    public List<EmployeeDto> getAllEmployees() {
        log.info("從資料庫查詢所有員工 (環境: {})",
                 environmentService.getCurrentEnvironment());

        return employeeRepository.findAll()
            .stream()
            .map(this::convertToDto)
            .collect(Collectors.toList());
    }

    /**
     * 更新員工資料（更新快取）
     */
    @CachePut(value = "employees", key = "#id")
    public EmployeeDto updateEmployee(Long id, EmployeeDto employeeDto) {
        log.info("更新員工 ID: {} (環境: {})",
                 id, environmentService.getCurrentEnvironment());

        Employee employee = employeeRepository.findById(id)
            .orElseThrow(() -> new RuntimeException("員工不存在: " + id));

        // 更新邏輯...
        employee.setFirstName(employeeDto.getFirstName());
        employee.setLastName(employeeDto.getLastName());
        employee.setEmail(employeeDto.getEmail());

        Employee updated = employeeRepository.save(employee);

        // 清除所有員工的快取
        evictAllEmployeesCache();

        return convertToDto(updated);
    }

    /**
     * 刪除員工（清除快取）
     */
    @CacheEvict(value = "employees", key = "#id")
    public void deleteEmployee(Long id) {
        log.info("刪除員工 ID: {} (環境: {})",
                 id, environmentService.getCurrentEnvironment());

        employeeRepository.deleteById(id);

        // 清除所有員工的快取
        evictAllEmployeesCache();
    }

    /**
     * 清除所有員工快取
     */
    @CacheEvict(value = "employees", key = "'all'")
    public void evictAllEmployeesCache() {
        log.info("清除所有員工快取 (環境: {})",
                 environmentService.getCurrentEnvironment());
    }

    /**
     * Entity 轉 DTO
     */
    private EmployeeDto convertToDto(Employee employee) {
        return EmployeeDto.builder()
            .id(employee.getId())
            .firstName(employee.getFirstName())
            .lastName(employee.getLastName())
            .email(employee.getEmail())
            .build();
    }
}
```

## 🐳 Docker 容器化部署

### 📦 Dockerfile 設計

**多階段建置 Dockerfile**

```dockerfile
# ============================================
# Stage 1: Build Stage (Maven 編譯)
# ============================================
FROM maven:3.8.6-eclipse-temurin-17 AS build

WORKDIR /app

# 複製 pom.xml 並下載依賴（利用 Docker 快取）
COPY pom.xml .
RUN mvn dependency:go-offline -B

# 複製原始碼並編譯
COPY src ./src
RUN mvn clean package -DskipTests -B

# ============================================
# Stage 2: Runtime Stage (執行環境)
# ============================================
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

# 建立非 root 使用者（安全性）
RUN addgroup -g 1001 appuser && \
    adduser -D -u 1001 -G appuser appuser

# 複製編譯好的 JAR 檔案
COPY --from=build /app/target/*.jar app.jar

# 建立日誌和上傳目錄
RUN mkdir -p /app/logs /app/uploads && \
    chown -R appuser:appuser /app

# 切換到非 root 使用者
USER appuser

# 暴露埠號
EXPOSE 8080

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/api/actuator/health || exit 1

# 啟動指令（使用環境變數指定 Profile）
ENTRYPOINT ["java", \
            "-Djava.security.egd=file:/dev/./urandom", \
            "-Dspring.profiles.active=${SPRING_PROFILE:prod}", \
            "-jar", \
            "app.jar"]
```

### 🎯 Docker Compose 配置

**完整的多環境 Docker Compose 配置**

**`docker-compose.dev.yml` - 開發環境**

```yaml
version: '3.8'

services:
  # Spring Boot 應用（開發環境）
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: employee-system-dev
    environment:
      - SPRING_PROFILE=dev
    ports:
      - "8080:8080"
    volumes:
      - ./logs:/app/logs
      - ./uploads:/app/uploads
    networks:
      - employee-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/api/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  employee-network:
    driver: bridge
```

**`docker-compose.stage.yml` - 測試環境**

```yaml
version: '3.8'

services:
  # MySQL 資料庫
  mysql:
    image: mysql:8.0
    container_name: employee-mysql-stage
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME:-employee_stage}
      MYSQL_USER: ${DB_USER:-stage_user}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_stage_data:/var/lib/mysql
      - ./sql/init:/docker-entrypoint-initdb.d
    networks:
      - employee-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 10s
      retries: 5

  # Redis 快取
  redis:
    image: redis:7-alpine
    container_name: employee-redis-stage
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "6379:6379"
    volumes:
      - redis_stage_data:/data
    networks:
      - employee-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # Spring Boot 應用（測試環境）
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: employee-system-stage
    environment:
      - SPRING_PROFILE=stage
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=${DB_NAME:-employee_stage}
      - DB_USER=${DB_USER:-stage_user}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - JWT_SECRET=${JWT_SECRET}
    ports:
      - "8080:8080"
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs
      - ./uploads:/app/uploads
    networks:
      - employee-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/api/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  mysql_stage_data:
    driver: local
  redis_stage_data:
    driver: local

networks:
  employee-network:
    driver: bridge
```

**`docker-compose.prod.yml` - 生產環境**

```yaml
version: '3.8'

services:
  # MySQL 資料庫（生產配置）
  mysql:
    image: mysql:8.0
    container_name: employee-mysql-prod
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_prod_data:/var/lib/mysql
      - ./sql/init:/docker-entrypoint-initdb.d
      - ./mysql/conf:/etc/mysql/conf.d  # 自定義 MySQL 配置
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max_connections=500
      - --innodb_buffer_pool_size=2G
    networks:
      - employee-network
    restart: always
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 10s
      retries: 5

  # Redis 快取（生產配置）
  redis:
    image: redis:7-alpine
    container_name: employee-redis-prod
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000
    ports:
      - "6379:6379"
    volumes:
      - redis_prod_data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf  # 自定義 Redis 配置
    networks:
      - employee-network
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "--pass", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # Spring Boot 應用（生產環境）
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: employee-system-prod
    environment:
      - SPRING_PROFILE=prod
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - JWT_SECRET=${JWT_SECRET}
      - UPLOAD_DIR=/app/uploads/prod
      - CORS_ORIGINS=${CORS_ORIGINS}
      - JAVA_OPTS=-Xms512m -Xmx2048m -XX:+UseG1GC -XX:MaxGCPauseMillis=200
    ports:
      - "8080:8080"
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs:/var/log/employee-system
      - uploads_prod_data:/app/uploads/prod
    networks:
      - employee-network
    restart: always
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/api/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2048M
        reservations:
          cpus: '1'
          memory: 512M

  # Nginx 反向代理
  nginx:
    image: nginx:alpine
    container_name: employee-nginx-prod
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - uploads_prod_data:/var/www/uploads:ro
    depends_on:
      - app
    networks:
      - employee-network
    restart: always

volumes:
  mysql_prod_data:
    driver: local
  redis_prod_data:
    driver: local
  uploads_prod_data:
    driver: local

networks:
  employee-network:
    driver: bridge
```

### 🔐 環境變數管理

**`.env.dev` - 開發環境變數**

```bash
# 開發環境配置
SPRING_PROFILE=dev
```

**`.env.stage` - 測試環境變數**

```bash
# 測試環境配置
SPRING_PROFILE=stage

# 資料庫配置
DB_ROOT_PASSWORD=stage_root_password
DB_NAME=employee_stage
DB_USER=stage_user
DB_PASSWORD=stage_db_password

# Redis 配置
REDIS_PASSWORD=stage_redis_password

# JWT 配置
JWT_SECRET=stage_jwt_secret_key_minimum_256_bits

# CORS 配置
CORS_ORIGINS=http://stage-frontend.example.com
```

**`.env.prod` - 生產環境變數**

```bash
# 生產環境配置
SPRING_PROFILE=prod

# 資料庫配置（使用強密碼）
DB_ROOT_PASSWORD=<strong-root-password>
DB_NAME=employee_prod
DB_USER=prod_user
DB_PASSWORD=<strong-db-password>

# Redis 配置
REDIS_PASSWORD=<strong-redis-password>

# JWT 配置（使用密鑰管理服務）
JWT_SECRET=<strong-jwt-secret-minimum-256-bits>

# CORS 配置
CORS_ORIGINS=https://app.example.com,https://www.example.com

# 檔案上傳配置
UPLOAD_DIR=/app/uploads/prod

# Java 記憶體配置
JAVA_OPTS=-Xms1024m -Xmx2048m -XX:+UseG1GC
```

### 🚀 Docker 部署指令

**開發環境啟動**

```bash
# 使用開發環境配置啟動
docker-compose -f docker-compose.dev.yml --env-file .env.dev up -d

# 查看日誌
docker-compose -f docker-compose.dev.yml logs -f app

# 停止
docker-compose -f docker-compose.dev.yml down
```

**測試環境啟動**

```bash
# 使用測試環境配置啟動
docker-compose -f docker-compose.stage.yml --env-file .env.stage up -d

# 查看所有服務狀態
docker-compose -f docker-compose.stage.yml ps

# 查看特定服務日誌
docker-compose -f docker-compose.stage.yml logs -f app

# 重新建置並啟動
docker-compose -f docker-compose.stage.yml up -d --build

# 停止並刪除資料卷（慎用）
docker-compose -f docker-compose.stage.yml down -v
```

**生產環境啟動**

```bash
# 使用生產環境配置啟動
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 檢查健康狀態
docker-compose -f docker-compose.prod.yml ps

# 查看資源使用情況
docker stats

# 查看應用程式日誌（不使用 -f 避免阻塞）
docker-compose -f docker-compose.prod.yml logs --tail=100 app

# 執行資料庫備份
docker exec employee-mysql-prod mysqldump -u root -p${DB_ROOT_PASSWORD} ${DB_NAME} > backup.sql

# 滾動更新（零停機）
docker-compose -f docker-compose.prod.yml up -d --no-deps --build app

# 停止（保留資料卷）
docker-compose -f docker-compose.prod.yml down
```

### 🔄 Docker Build 參數化

**使用 Build Args 指定環境**

```bash
# 建置開發環境映像
docker build \
  --build-arg SPRING_PROFILE=dev \
  -t employee-system:dev \
  .

# 建置測試環境映像
docker build \
  --build-arg SPRING_PROFILE=stage \
  -t employee-system:stage \
  .

# 建置生產環境映像
docker build \
  --build-arg SPRING_PROFILE=prod \
  -t employee-system:prod \
  .

# 執行特定環境的容器
docker run -d \
  --name employee-system-prod \
  -p 8080:8080 \
  --env-file .env.prod \
  employee-system:prod
```

## 📊 監控與驗證

### 🔍 驗證配置載入

**建立監控端點 - `ConfigController.java`**

```java
package com.employee.system.controller;

import com.employee.system.service.EnvironmentService;
import lombok.AllArgsConstructor;
import lombok.Data;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

/**
 * 配置資訊監控端點
 * 僅在開發/測試環境啟用
 */
@RestController
@RequestMapping("/api/config")
public class ConfigController {

    @Autowired
    private Environment environment;

    @Autowired
    private EnvironmentService environmentService;

    @Value("${spring.datasource.url:N/A}")
    private String datasourceUrl;

    @Value("${spring.cache.type:N/A}")
    private String cacheType;

    /**
     * 取得當前配置資訊
     */
    @GetMapping("/info")
    public ConfigInfo getConfigInfo() {
        // 生產環境不暴露配置資訊
        if (environmentService.isProduction()) {
            throw new RuntimeException("生產環境不允許存取配置資訊");
        }

        ConfigInfo info = new ConfigInfo();
        info.setEnvironment(environmentService.getCurrentEnvironment());
        info.setActiveProfiles(Arrays.asList(environment.getActiveProfiles()));
        info.setDatasourceUrl(maskSensitiveInfo(datasourceUrl));
        info.setCacheType(cacheType);
        info.setRedisEnabled(environmentService.isRedisEnabled());

        return info;
    }

    /**
     * 健康檢查端點
     */
    @GetMapping("/health")
    public Map<String, Object> healthCheck() {
        Map<String, Object> health = new HashMap<>();
        health.put("status", "UP");
        health.put("environment", environmentService.getCurrentEnvironment());
        health.put("database", "UP");
        health.put("cache", environmentService.isRedisEnabled() ? "Redis" : "Simple");

        return health;
    }

    /**
     * 遮蔽敏感資訊
     */
    private String maskSensitiveInfo(String info) {
        if (info.contains("password=")) {
            info = info.replaceAll("password=[^&]*", "password=****");
        }
        return info;
    }

    @Data
    @AllArgsConstructor
    private static class ConfigInfo {
        private String environment;
        private java.util.List<String> activeProfiles;
        private String datasourceUrl;
        private String cacheType;
        private boolean redisEnabled;

        public ConfigInfo() {}
    }
}
```

### 📈 測試不同環境

**測試腳本 - `test-environments.sh`**

```bash
#!/bin/bash

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Spring Boot 多環境配置測試${NC}"
echo -e "${YELLOW}========================================${NC}"

# 測試開發環境
echo -e "\n${GREEN}1. 測試開發環境 (dev)${NC}"
docker-compose -f docker-compose.dev.yml --env-file .env.dev up -d
sleep 10

echo -e "檢查配置..."
curl -s http://localhost:8080/api/config/info | jq '.'

echo -e "檢查健康狀態..."
curl -s http://localhost:8080/api/config/health | jq '.'

docker-compose -f docker-compose.dev.yml down

# 測試測試環境
echo -e "\n${GREEN}2. 測試測試環境 (stage)${NC}"
docker-compose -f docker-compose.stage.yml --env-file .env.stage up -d
sleep 30

echo -e "檢查配置..."
curl -s http://localhost:8080/api/config/info | jq '.'

echo -e "檢查 Redis 連接..."
docker exec employee-redis-stage redis-cli -a stage_redis_password ping

docker-compose -f docker-compose.stage.yml down

# 測試生產環境
echo -e "\n${GREEN}3. 測試生產環境 (prod)${NC}"
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
sleep 30

echo -e "檢查健康狀態..."
curl -s http://localhost:8080/api/actuator/health | jq '.'

echo -e "檢查 Redis 連接..."
docker exec employee-redis-prod redis-cli -a ${REDIS_PASSWORD} ping

docker-compose -f docker-compose.prod.yml down

echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}所有環境測試完成！${NC}"
echo -e "${YELLOW}========================================${NC}"
```

## 🎯 最佳實踐與注意事項

### ✅ 配置管理最佳實踐

**1. 安全性**
- ❌ **絕對不要**將敏感資訊（密碼、金鑰）寫在配置檔案中
- ✅ **必須**使用環境變數或密鑰管理服務
- ✅ 生產環境使用 AWS Secrets Manager 或 HashiCorp Vault
- ✅ `.env` 檔案加入 `.gitignore`

**2. 配置分離**
- ✅ 基礎配置放在 `application.yml`
- ✅ 環境特定配置放在 `application-{profile}.yml`
- ✅ 敏感配置使用環境變數
- ✅ 使用 `@Value` 和 `@ConfigurationProperties` 注入配置

**3. 資料庫管理**
- ✅ 開發環境使用 H2/SQLite 記憶體資料庫
- ✅ 測試環境使用獨立的測試資料庫
- ✅ 生產環境使用 RDS 或資料庫叢集
- ✅ 使用 Flyway/Liquibase 管理資料庫版本

**4. 快取策略**
- ✅ 開發環境不使用 Redis（減少依賴）
- ✅ 測試環境使用 Redis 測試快取功能
- ✅ 生產環境使用 Redis Cluster（高可用）
- ✅ 設定合理的快取過期時間

### ⚠️ 常見陷阱與解決方案

**問題 1：Profile 沒有正確載入**
```bash
# 解決方案：明確指定 Profile
java -jar app.jar --spring.profiles.active=prod

# Docker 環境
docker run -e SPRING_PROFILES_ACTIVE=prod app:latest
```

**問題 2：環境變數沒有生效**
```yaml
# 錯誤寫法
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/db

# 正確寫法（使用環境變數）
spring:
  datasource:
    url: jdbc:mysql://${DB_HOST:localhost}:${DB_PORT:3306}/${DB_NAME:db}
```

**問題 3：Redis 連接失敗**
```java
// 解決方案：使用 @ConditionalOnProperty 條件化 Bean
@Configuration
@ConditionalOnProperty(name = "spring.cache.type", havingValue = "redis")
public class RedisConfig {
    // Redis 配置...
}
```

**問題 4：Docker 容器內連接資料庫失敗**
```yaml
# 錯誤：使用 localhost
DB_HOST=localhost

# 正確：使用 Docker Compose 服務名稱
DB_HOST=mysql
```

## 🎉 總結

### 📊 多環境配置架構優勢

**1. 開發效率提升**
- 開發人員無需安裝 MySQL、Redis 等服務
- 使用 H2 記憶體資料庫快速啟動
- 詳細的日誌輸出便於除錯

**2. 測試環境隔離**
- 獨立的測試資料庫避免污染生產資料
- 模擬生產環境配置提前發現問題
- 支援自動化測試和持續整合

**3. 生產環境安全**
- 敏感資訊完全隔離
- 效能優化配置（連接池、快取）
- 完整的監控和日誌管理

**4. 維護成本降低**
- 統一的配置管理方式
- 清晰的環境區分
- 容易的新環境建立

### 🚀 延伸學習

**進階主題**：
1. **Spring Cloud Config**：集中化配置管理
2. **Kubernetes ConfigMap**：容器編排環境配置
3. **AWS Parameter Store**：雲端配置管理
4. **Vault Integration**：密鑰管理整合

**相關資源**：
- [Spring Boot 官方文檔](https://spring.io/projects/spring-boot)
- [Docker Compose 文檔](https://docs.docker.com/compose/)
- [Redis 最佳實踐](https://redis.io/docs/manual/patterns/)

### 💡 核心要點回顧

1. ✅ 使用 Spring Profile 管理不同環境配置
2. ✅ 敏感資訊必須使用環境變數
3. ✅ 開發環境簡化配置，生產環境強化安全
4. ✅ Docker Compose 統一管理容器化部署
5. ✅ Redis 快取視環境需求啟用/停用
6. ✅ 完整的健康檢查和監控機制

透過本文的完整指南，你可以建立一個專業、安全、易維護的 Spring Boot 多環境配置架構，無論是本地開發、測試環境還是生產部署，都能游刃有餘！

---

## 🔗 相關資源

| 資源 | 連結 |
|------|------|
| 📂 **完整範例程式碼** | [GitHub - SpringPlayground](https://github.com/yennanliu/SpringPlayground) |
| 📖 **Spring Boot 文檔** | [官方文檔](https://spring.io/projects/spring-boot) |
| 🐳 **Docker 文檔** | [Docker 官方文檔](https://docs.docker.com/) |
| 📚 **相關文章** | [Spring Boot 系列文章](/categories/spring-boot/) |
