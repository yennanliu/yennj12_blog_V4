## Java / Spring Boot / backend engineering (26 posts incl. crypto-quant 3, shopping-cart 2) — 26 posts

### Series-level observations
- **This is not really a Java batch.** 9 of the 26 have no Java in them. `building-resilient-systems`, `microservices-architecture-patterns` and `optimizing-database-performance` are written in Go/SQL. The crypto trio is Python. `express-*` and `typescript-*` are Node/TS. `comprehensive-java-learning-journey` has zero Java code: all 29 of its fences are mermaid. So readers who arrive through a Java tag get mixed results.
- **Too many "Complete Guide" posts that cover the same ground.** Four posts each work through Runnable/Callable/ExecutorService/producer-consumer/singleton from scratch: the java-concurrency guide, Part 2 and Part 3, plus `comprehensive-java-learning-journey`. Singleton, Observer and Strategy are each written out in full twice, once in `essential-design-patterns-java` and again in concurrency Part 3. None of these posts links to the others. Part 2's opening says "Building upon our comprehensive overview" but there's no link, and the first post isn't even named "Part 1". There's no series nav anywhere in the concurrency set.
- **Correctness bugs in code meant to be copied.** The worst: the shopping-cart Part 2 lock-around-`@Transactional` design is defeated by self-invocation, the WebSocket Redis fan-out double-delivers, MySQL "consistent hashing" is plain `hash % N`, the sharding "distributed transaction" is sequential commits, and `.properties` files have inline `#` comments. Details are under each post. These are the batch's biggest trust risk, bigger than staleness.
- **Unsourced numbers presented as results.** Throughput/latency tables (`data-consistency` §Performance Benchmarks), "10,000+ connections / <50ms" (websocket), a "3,700% return" ROI (employee-management) and "40% increase in user engagement" (db-performance) give no hardware, no load tool, no repo link. Either label them "illustrative targets" or delete them.
- **Version staleness pattern.** The project write-ups pin Spring Boot 2.7+ (OSS EOL Nov 2023) or 3.0.12 (EOL). Only the 2026 shopping-cart pair is on 3.2 + JDK 21. None of the pre-2026 Java posts treat virtual threads as current: GA since JDK 21 (Sept 2023), yet they're filed under "Emerging" / "Java 9+". Node 20 and ESLint 8 have both reached EOL, and Express 4 is shown although Express 5 is now `latest`.
- **Front-matter hygiene across the "YennJ12 Engineering Team" posts.** Every one carries category `ai` and tag `AI` although none is about AI (Java concurrency, SAGA, design patterns, Express, TS). Drop `ai` from categories and `AI` from tags. The two 2025-09-29 `-zh` posts use singular `author: "yennj12 team"`, which doesn't match any `content/authors/` slug.
- **The four Spring Boot + Vue project posts are READMEs, as suspected.** They share one template: Problem Statement, Core Philosophy blockquote, Why This Stack, Architecture, Backend Deep Dive, Future Roadmap Phase 1/2/3, Business Value & ROI, `localhost` "Live Demo"/"Swagger" links. They read like auto-expanded READMEs with invented business framing. The 2026 shopping-cart pair is the model to follow instead: it has a real PR, a real bottleneck and a real before/after.
- **`-zh` posts: prose-led vs code-led.** The shopping-cart pair is genuinely prose-led: reasoning between short snippets, good Traditional Chinese, a few Mainland terms (「默認」, 「消息佇列」). `jvm-memory-*-zh`, `spring-boot-code-loading-*-zh` and `spring-boot-multi-environment-*-zh` are code-led. Their explanations are hidden in Javadoc blocks inside `@Component` classes, and their Chinese is mostly headings plus one-line intros.

### Per-post

#### `building-resilient-systems.md`
**Verdict:** restructure
- 86% Go code with 1–2 sentences per pattern. For example, "## Bulkhead Pattern" is almost 80 lines of code, and the prose never says when to choose a bulkhead over a rate limiter or load shedding. Add a short "when/threshold" paragraph per pattern, such as retry budgets and circuit-breaker thresholds in % errors over N seconds.
- Circuit breaker `Execute` reads state under `RLock` and then acts on it after releasing the lock (lines ~48–62), which is a classic check-then-act race. Either fix it or point readers at a library (resilience4j / sony/gobreaker).
- "Chaos Engineering" is a hand-rolled experiment framework. Linking to real tools (Chaos Mesh, AWS FIS, Gremlin) would help more than 70 lines of interfaces.
- The front matter has only `summary` and no `description`. Same identical timestamp (2025-08-10T15:28:17) as the two sister posts: this looks like seed content. Consider merging all three into one "resilience + performance" post, or retiring.

#### `comprehensive-java-learning-journey-fundamentals-to-advanced.md`
**Verdict:** rewrite/merge
- There's no Java in a Java learning post: 29 mermaid diagrams and bullet walls ("Loop Optimization", "Control Flow Security"). A reader learns nothing here they couldn't get from a table of contents.
- The "🚀 Future-Oriented Learning" section (line ~1101) calls Project Loom virtual threads and Panama "emerging". Both have been GA/final for years (JDK 21 / JDK 22).
- "📊 Project Impact & Learning Outcomes" / "Skill Development Metrics" ("Complete understanding of Java language fundamentals") is self-congratulatory filler.
- Recommend turning it into a short index/roadmap post that links the concurrency, design-patterns, JVM-memory and Spring posts in this batch, plus the JavaHelloWorld repo. That also gives the Java posts the hub they currently lack.

#### `crypto-quantitative-trading-part1-fundamentals.md`
**Verdict:** light edit
- The series nav is broken: "**Continue to Part 2**: [...](#)" links to `#`. Replace it with `/posts/crypto-quantitative-trading-part2-strategies-backtesting/`.
- "Share them in the comments below!" — the site has no comment system (no giscus/disqus in the theme). Remove it from all three parts.
- The "Why Crypto is Ideal" block ("Free API access", "Settlement ~10 minutes") has no caveats about exchange counterparty risk, wash trading in volume data, or survivorship bias in exchange-listed symbols. One paragraph would make it honest.
- Good pedagogical arc and solid indicator code. The "Practical Example" pipeline would be stronger if it showed its actual output (one chart or printed stats).

#### `crypto-quantitative-trading-part2-strategies-backtesting.md`
**Verdict:** light edit
- "Complete Example: Strategy Comparison" (line ~1078) runs the strategies but never shows results. The reader is left without the one thing a backtesting post promises. Add a real results table: return, Sharpe, max drawdown, trades, and the data period.
- In `_close_position`, P&L subtracts only the exit commission, so the entry commission is never charged to `pnl` and per-trade P&L is overstated. The backtester is decent otherwise: slippage and commission are modelled, and hourly annualisation uses `sqrt(365*24)`.
- The Part 3 link is also `(#)`. Same comments CTA as Part 1.

#### `crypto-quantitative-trading-part3-production-deployment.md`
**Verdict:** light edit
- The `(#)` links and comments CTA need the same fixes. The duplicate `### **Implementation**` headings under Walk-Forward and Monte Carlo should get distinct names.
- The book list names "Algorithmic Trading" by Stefan Jansen. The title is *Machine Learning for Algorithmic Trading*. Verify the course names too.
- The testnet-first framing is responsible. Add a sentence on API-key scope (trade-only, no withdrawal, IP allow-list), which matters more than anything in the Docker section.

#### `data-consistency-patterns-java-enterprise-applications.md`
**Verdict:** restructure
- The "📊 Performance Benchmarks" tables (Optimistic 1,200 rps, 2PC P99 1,200ms…) have no setup, hardware or tool. Remove them or label them "illustrative".
- The 2PC section's `BookingTransactionCoordinator` is a hand-rolled coordinator annotated with local `@Transactional`. It doesn't show XA/JTA (Atomikos/Narayana), so readers may think this is how 2PC is done. Say plainly that you'd use a JTA manager or, more usually, avoid 2PC (and link the SAGA post).
- No transactional-outbox coverage, which is the pattern most Spring teams actually need. It belongs in "Future Considerations" or its own section.
- Remove `ai` from categories and `AI` from tags. Cross-link `saga-pattern-*` and shopping-cart Part 2 (Redisson locks), which shows the same optimistic-vs-lock trade-off in practice.

#### `essential-design-patterns-java-comprehensive-guide.md`
**Verdict:** restructure
- The recommended Enum Singleton `DatabaseManager` holds one shared `java.sql.Connection` (line ~46). That's a real anti-pattern: JDBC connections aren't meant to be shared across threads, so use a pool. Pick a different example, and add a line noting that in Spring the container's singleton scope replaces most hand-written singletons.
- No modern Java: no records for Builder alternatives, lambdas/`Function<>` for Strategy, or sealed interfaces. That's where a 2025 post could add something beyond GoF.
- Observer/Strategy duplicate `java-concurrency-design-patterns-thread-interfaces-part3`. Cross-link them and cut one of the two versions.
- The title is 105 characters and gets truncated on cards. Shorten it to something like "Essential Design Patterns in Java".

#### `express-nodejs-backend-framework-best-practices.md`
**Verdict:** light edit
- It pins `"express": "^4.18.2"` (line ~1429). Express 5 is now the default: it forwards rejected promises to error middleware, so the `catchAsync` wrapper (line ~700) is unnecessary on v5. Update, or add a note.
- `eslint ^8` and `.eslintrc.json` are EOL/deprecated (ESLint 9 flat config). `node:20-alpine` reached EOL in April 2026, so move to 22/24 LTS.
- It's a solid, well-organised checklist. The body ends with a hand-typed "**Tags:** #Express …" line, which duplicates front-matter tags; remove it. Also remove the `ai` category and `AI` tag.

#### `java-concurrency-deep-dive-runnable-callable-patterns-part2.md`
**Verdict:** restructure
- `VolatileExample` puts `counter++` on a `volatile int` with the comment "volatile write ensures visibility". That's true, but readers will infer the increment is atomic, and it isn't. Add the explicit counter-example; it's the most-asked JMM question.
- "Benchmarking Concurrent Operations" times with `System.nanoTime()` around `IntStream.parallel()` inside a Spring `@Component`, so there's no warm-up, no JMH, and the numbers are meaningless. Replace it with a JMH skeleton, or at least a warning.
- No virtual threads, `StructuredTaskScope` or `ScopedValue` anywhere, in a 2025 "internal mechanisms" deep dive. Add a section, or state the JDK version scope up front.
- The opening references "our comprehensive overview" without a link. Add series nav (Part 1 → 2 → 3) at the bottom.

#### `java-concurrency-design-patterns-thread-interfaces-part3.md`
**Verdict:** light edit
- The duplicate headings `### 📋 Pattern Overview` / `### 🛠️ Implementation with Thread Interfaces` repeat for all five patterns, so the TOC is five identical pairs. Prefix them with the pattern name.
- The closing comparison table (Complexity/Performance: "Optimized", "Highly optimized") is vague. Replace it with concrete guidance, e.g. queue capacity versus producer rate, or when Observer should become an event bus.
- It overlaps `essential-design-patterns-java` (Observer, Strategy) and Part 1 (producer-consumer at Part 1 line ~1136). Keep the concurrent angle here and link out for the basic pattern.
- Series nav is missing.

#### `java-concurrency-threading-runnable-callable-guide.md`
**Verdict:** restructure
- This is effectively Part 1, but neither the filename nor the title says so, and there's no nav. Retitle it "… Part 1" (keep the slug) and add series nav.
- The closing evolution diagram (line ~1615) lumps "Virtual Threads" under "Java 9+: Reactive Streams". Virtual threads are JDK 21 and deserve their own section, and they change the thread-pool-sizing advice in "🔧 Thread Pool Tuning".
- "📈 Performance Comparison Table" has no performance data (it's a feature matrix). Rename it.
- Producer-consumer and singleton here re-appear in Part 3 and the design-patterns post. Trim them to one canonical home.

#### `jvm-memory-heap-stack-comprehensive-guide-zh.md`
**Verdict:** restructure
- 「垃圾回收機制詳解」 contains no explanation of GC, only a `GarbageCollectionAnalyzer` MXBean class. There's also no comparison of the G1 / ZGC (generational since JDK 21) / Shenandoah / Parallel collectors, which is what readers look for. Add a 「為什麼選 G1 不選 ZGC」-style table with pause-time and throughput numbers.
- The JVM flags in 「記憶體參數配置」 are buried in a Javadoc comment on a `@Component JVMTuningGuide`. Pull them out into a flag table with explanations, and mention container-aware sizing (`-XX:MaxRAMPercentage`), which matters more than `-Xmx` in Kubernetes.
- Code-led: the Chinese prose is thin between 100-line classes. Front matter uses singular `author:` and has no `readTime`.

#### `microservices-architecture-patterns.md`
**Verdict:** consider retiring
- At 319 lines, it covers the textbook list (API Gateway, DB-per-service, events, circuit breaker, discovery, tracing) with a 10-line Go snippet each. That's no deeper than the microservices.io overview.
- "When we started our journey… millions of users" is a production narrative with no specifics. Either add real context or drop the first-person framing.
- The circuit breaker is also covered in `building-resilient-systems` and SAGA in `saga-pattern-*`. If kept, rewrite it as a hub that links those posts.

#### `mysql-sharding-strategies-comprehensive-guide.md`
**Verdict:** restructure
- `determineShardKeyConsistent` (line ~366) is labelled "Consistent hashing implementation for better resharding", but it's MD5 `% numberOfShards`, so resharding still remaps nearly all keys. Either implement a real hash ring or virtual buckets, or rename it. Also, `Math.abs(hash) % n` goes negative for `Integer.MIN_VALUE`, so use `Math.floorMod`.
- "Cross-Shard Transactions" (line ~1253) opens N connections and commits them in sequence. If shard 2's commit fails after shard 1 committed, the data is inconsistent, so this is not a distributed transaction. Mention XA, or point to SAGA/outbox.
- No mention of Vitess, Apache ShardingSphere, ProxySQL or managed options (PlanetScale, Aurora Limitless, TiDB). In 2026 "build your own router" is rarely the answer, and the post should say when it is.
- The title is 118 characters; shorten it.

#### `optimizing-database-performance.md`
**Verdict:** light edit
- The `pg_stat_statements` query selects `total_time` / `mean_time` (line ~40). Those columns were renamed to `total_exec_time` / `mean_exec_time` in PostgreSQL 13, so the query errors on any supported version.
- "Results and Impact" (15s→50ms P95, "40% increase in user engagement", "30% reduction in database server requirements") has no system named and no timeframe. Label it a composite/illustrative case, or add context.
- The Go cache code ignores the `json.Unmarshal` error and uses a fixed TTL with no stampede protection. One paragraph on single-flight/jittered TTL would add real value.
- Add a `description`. Postgres is the real topic, but the tags include the meaningless `AI`.

#### `saga-pattern-distributed-transactions-spring-boot.md`
**Verdict:** restructure
- The "Choreography" implementation uses Spring's in-process `ApplicationEventPublisher` / `@EventListener`. That's single-JVM eventing, not cross-service choreography, and it contradicts the Kafka config shown later (line ~944). Show the Kafka producer/consumer path instead.
- It saves the saga event and publishes in the same method with no transactional outbox, which is the dual-write bug every real SAGA hits. Add an outbox section: it's the most valuable thing this post could teach.
- No mention of orchestration frameworks (Temporal, Camunda, Axon, Eventuate). A "when to use a framework vs hand-roll" decision would help practitioners.
- The "📈 Performance Comparison" table rates 2PC Complexity "Low" and Debugging "Easy". Many readers would dispute that, so justify or soften it.

#### `shopping-cart-high-concurrency-part1-zh.md`
**Verdict:** light edit
- **Copy-paste bug:** the HikariCP block (line ~166) puts `# 等待連線最多 3 秒` on the same line as `connection-timeout=3000`. `.properties` files don't support trailing comments, so the value becomes the whole string and binding fails at startup. Move the comments to their own lines.
- The virtual-thread caveat in 「注意事項」 is muddled ("native 方法不支援 Virtual Thread 的 pinning unpark"). The real JDK 21 issue is pinning inside `synchronized` blocks, which JDK 24 (JEP 491) fixed; older Connector/J uses `synchronized`. Rewrite it with that framing.
- The description promises "能承受 C10K" but the body has no load-test numbers. Add a before/after (e.g. k6/Gatling RPS, P99, pool wait time) or drop the C10K claim.
- The series name counts 方案一–三 here and 方案四、五、七 in Part 2, so 方案六 is missing. Either explain it (it seems to be the MQ item in 「生產環境的進一步優化方向」) or renumber.
- Use Taiwan terms: 「默認」→「預設」, 「消息佇列」→「訊息佇列」. Otherwise this is the best post in the batch: prose-led, real PR, honest 「什麼時候不該快取？」 section.

#### `shopping-cart-high-concurrency-part2-zh.md`
**Verdict:** light edit
- **Correctness bug:** in 「正確設計：鎖在事務外部」, `placeOrder()` calls `doPlaceOrder()` on `this`. Spring's proxy doesn't intercept self-invocation, so `@Transactional` on `doPlaceOrder` never applies and each repository call commits on its own. The section's central claim ("事務在這裡 commit… commit 之後才釋放") is false as written. Fix it with `TransactionTemplate`, a separate bean, or self-injection, and say why. It's a great teaching moment.
- The `leaseTime` / watchdog paragraph is accurate and useful. Consider showing the observed P99 lock-wait under contention to back up `tryLock(3, 30, …)`.
- Same terminology note (「默認」 ×3). The heading 「方案七」 needs the 方案六 explanation (see Part 1).
- Strong ending (「小結：兩篇的演進路徑」). Add a link to `spring-boot-ecommerce-shopping-cart-stripe-integration`, which describes the same codebase before the upgrade.

#### `spotify-playlist-full-stack-application.md`
**Verdict:** consider retiring
- The core feature relies on Spotify's `/recommendations` endpoint (`spotifyApiService.getRecommendations`, line ~181). Spotify deprecated Recommendations, Audio Features and related endpoints for new apps in Nov 2024, so readers can't reproduce this.
- The title promises an "ML Recommendation Engine" / 「基於深度學習的個人偏好建模」, but the code just forwards seeds to Spotify's API. There's no ML.
- English title and slug, Chinese body (lang-mismatch); Spring Boot 2.x; `localhost:8888` "API 文件" link; README-template sections (「未來發展規劃」 3-6 / 6-12 / 1-2 年). If kept, rename it `-zh`, add a deprecation note and remove the ML claims.

#### `spring-boot-code-loading-compilation-transformation-zh.md`
**Verdict:** restructure
- The title promises Spring Boot-specific loading, but it never covers the parts unique to Spring Boot: the fat-jar layout (`BOOT-INF/`), `JarLauncher` and its launched class loader, `AutoConfiguration.imports` (which replaced `spring.factories` in 2.7/3.0), and the condition-evaluation report (`--debug`). Those would be the reason to read it.
- 「Spring Boot 自動配置機制」 "analyses" auto-config by filtering bean names containing "AutoConfiguration". It also has a stub method (「這裡可以實作條件註解的分析邏輯」) and puts `@EnableAutoConfiguration` on the analyzer itself. Replace it with a prose explanation plus `ConditionEvaluationReport`.
- Code-led at 91%, with Chinese reduced to headings. Uses singular `author:` and has no `readTime`.

#### `spring-boot-ecommerce-shopping-cart-stripe-integration.md`
**Verdict:** restructure
- Stale: it says "Spring Boot 2.7+" (line ~67), but the same `ShoppingCart` repo was upgraded to 3.2.5 in the 2026 shopping-cart series. Add a banner that links `shopping-cart-high-concurrency-part1-zh`, or update the stack.
- The Stripe flow uses server-side `ConfirmationMethod.MANUAL` + `paymentIntent.confirm()` (lines ~760–794). Stripe now steers integrations to the Payment Element / Checkout with automatic confirmation, with the webhook as the source of truth. Update it, or explain why manual.
- README template: "Core Philosophy" quote, Future Roadmap Phase 1/2/3, "Business Value & ROI", `localhost:9999` Swagger link, and "<2% cart abandonment rate" as a success metric (the industry norm is around 70%). Cut these to the Stripe and cart-merge logic, which is the real content.
- Remove the emoji in the title (🛍️) and the `AI` tag. There's no `description`.

#### `spring-boot-multi-environment-configuration-guide-zh.md`
**Verdict:** restructure
- **Wrong precedence list** in 「配置優先級順序」 (line ~58). It labels `application-{profile}.yml` 「最高優先級」 and then also calls CLI args highest. It also ranks env vars *below* the yml files, when in Spring Boot environment variables override `application-*.yml`. Readers will misconfigure prod from this.
- It uses `spring.redis.*` (lines ~214, ~291, `@Value("${spring.redis.host…}")`). On Boot 3.x the prefix is `spring.data.redis.*`, and the old keys are silently ignored.
- `DatabaseConfig` hand-builds a `HikariConfig` bean per `@Profile`, re-implementing what `spring.datasource.hikari.*` already does per profile. This is an anti-pattern to teach. The intro says dev uses 「本地 MySQL」, but the code uses H2.
- The 「相關文章」 link `/categories/spring-boot/` points at a non-canonical category (drift/dead link). Use `/tags/spring-boot/`. A half-width comma appears in 「開發中,應用程式」 (line 14).

#### `spring-boot-vue-employee-management-system.md`
**Verdict:** rewrite/merge
- "💰 Cost Analysis & ROI Calculation" (line ~1734) invents 520 staff-hours saved, $51,000/yr savings and a "3,700% return" for a demo CRUD app. It damages the post's credibility, so delete it.
- Version inconsistency: it states "Spring Boot 2.7+", but the security config uses `requestMatchers(...)`, which is Spring Security 6 / Boot 3 API. Pin the real version.
- The summary says "Spring Boot microservices architecture", while the body says "Microservices-Ready Monolith". Pick one.
- At 1,930 lines for an employee CRUD system, it's the most README-like post in the batch. Cut it to ~400 lines: the non-obvious parts (file upload, pagination, Docker compose) plus a repo link.

#### `spring-boot-websocket-chat-room-application.md`
**Verdict:** restructure
- **Duplicate-delivery bug:** `sendMessage` has `@SendTo("/topic/public")` (local broadcast) *and* calls `publishToCluster` → Redis. The Redis listener on every instance, including the sender's, re-broadcasts to `/topic/public`, so clients on the originating node see every message twice. Filter by origin instance ID, or use a broker relay (RabbitMQ/ActiveMQ STOMP) instead of the simple broker plus Redis.
- Invalid images: `FROM openjdk:17-jre-alpine` (line ~1197) doesn't exist (the `openjdk` images are deprecated). Use `eclipse-temurin:17-jre-alpine` (or 21). Spring Boot 3.0.12 is EOL.
- "Performance Metrics & Achievements" (<50ms, 10,000+ connections, 99.9% uptime) has no test behind it, and "Gaming Integration Features" is roadmap filler. Remove them or label them as goals.
- `setAllowedOriginPatterns("*")` should come with a production warning. "Live Demo: http://localhost:8080" isn't a demo.

#### `typescript-best-practices-comprehensive-guide.md`
**Verdict:** light edit
- The recommended tsconfig uses `"moduleResolution": "node"` (node10), which is deprecated. Use `"bundler"` or `"nodenext"`, and verify it against the current TS 6/7 status. `eslint ^8` + `.eslintrc` style config is EOL; show `typescript-eslint` flat config.
- "✅ GOOD: Use const enum" conflicts with `isolatedModules`/`verbatimModuleSyntax` and Node's type-stripping (`erasableSyntaxOnly`). Modern guidance prefers unions or `as const` objects, so flip that example.
- The "Related Posts" block links a Java concurrency Part 2 and an MCP post, which are unrelated to TS. Link `express-nodejs-backend-framework-best-practices` instead. Remove the hand-typed "**Tags:**" footer, and `ai`/`AI`.

#### `webhooks-comprehensive-guide-java-implementation.md`
**Verdict:** light edit
- The GitHub validation uses legacy `X-Hub-Signature` / HMAC-SHA1 (lines ~362, ~411). GitHub recommends `X-Hub-Signature-256` (SHA-256). For Stripe, recommend the SDK's `Webhook.constructEvent` over hand-parsing `t=`/`v1=`. The rest of the security code is good: constant-time `MessageDigest.isEqual` and a 5-minute replay window.
- The controller binds `@RequestBody String payload`. Add a note that the signature must be computed over the raw bytes, and that any filter re-serialising JSON breaks verification. This is the #1 real-world webhook bug.
- At 1,938 lines, the "Event Models and DTOs" section (~380 lines of POJOs) is boilerplate. Cut it to the interesting fields or use records.
- The title is 116 characters; shorten it to "Webhooks in Java: A Practical Guide". Cross-link the Stripe cart post, which claims webhook support.

### Top 5 highest-impact fixes in this batch
1. **Fix the copy-paste correctness bugs:** self-invocation `@Transactional` in `shopping-cart-high-concurrency-part2-zh` 「正確設計」, the inline `#` comments in Part 1's `.properties` block, the double-delivery Redis fan-out in `spring-boot-websocket-chat-room-application`, "consistent hashing" that is `% N` plus the non-atomic multi-shard commit in `mysql-sharding-*`, the wrong config-precedence list and `spring.redis.*` keys in `spring-boot-multi-environment-*-zh`, and the renamed `pg_stat_statements` columns in `optimizing-database-performance`.
2. **Delete or label the fabricated-looking results:** the employee-management ROI (3,700%), websocket "10,000+ connections / <50ms", `data-consistency` benchmark tables, db-performance business impact, and Stripe "<2% cart abandonment". Replace them with measured numbers (as the shopping-cart series could) or mark them "illustrative".
3. **Consolidate the Java basics cluster:** make `comprehensive-java-learning-journey` a short hub, rename the concurrency guide to Part 1, add Part 1→2→3 nav, and pick one home each for Singleton/Observer/Strategy/producer-consumer (design-patterns vs concurrency Part 3).
4. **Refresh versions in one pass:** add virtual threads (JDK 21) and JDK 24 pinning to the concurrency posts, bump the project posts from Boot 2.7/3.0 (or add a "superseded by" banner, e.g. Stripe cart → shopping-cart series), fix `openjdk:17-jre-alpine`, and move to Express 5 / ESLint 9 / Node 22+. Retire or add a deprecation note to the Spotify post, whose `/recommendations` endpoint no longer works for new apps.
5. **Front-matter sweep:** remove `ai`/`AI` from every non-AI post here, fix `author:` → `authors:` on the two 2025-09-29 `-zh` posts, replace the `(#)` Part-2/Part-3 links and the "comments below" CTAs in the crypto trio, and shorten the >100-character titles (design patterns, MySQL sharding, webhooks).
