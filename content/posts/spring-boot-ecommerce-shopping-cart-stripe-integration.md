---
title: "🛍️ Building a Modern E-commerce Shopping Cart with Spring Boot & Stripe Payment Integration"
date: 2024-12-22T10:00:00Z
draft: false
authors: ["yen"]
categories: ["full-stack", "spring-boot", "ecommerce"]
tags: ["stripe", "payment-gateway", "jwt-authentication", "rest-api", "vue.js", "mysql"]
summary: "A complete e-commerce shopping cart system built with Spring Boot backend and Vue.js frontend, featuring Stripe payment integration, JWT authentication, and full CRUD operations for products, categories, and cart management."
readTime: "18 min"
---

## 🎯 Project Overview & Motivation

E-commerce platforms are the backbone of modern digital business, yet building a secure, scalable shopping cart system with reliable payment processing remains a complex challenge. This project demonstrates the implementation of a complete e-commerce solution using **Spring Boot** for the backend API and **Vue.js** for the frontend, with **Stripe** as the payment gateway.

> 💡 **Core Philosophy**: "Building enterprise-grade e-commerce functionality with modern web technologies and security best practices"

## 🏗️ System Architecture Overview

### 🔧 Technology Stack

```text
Frontend (Client)
├── Vue.js 3.x
├── Vue Router
├── Axios (HTTP Client)
├── Bootstrap/Tailwind CSS
└── Stripe.js SDK

Backend (Server)
├── Spring Boot 2.7+
├── Spring Security (JWT)
├── Spring Data JPA
├── MySQL Database
├── Stripe Java SDK
└── Maven Build Tool

Infrastructure
├── Docker & Docker Compose
├── Nginx (Reverse Proxy)
├── MySQL Database
└── Redis (Session Management)
```

### 🗺️ System Architecture Diagram

```mermaid
graph TD
    A[Client Browser] --> B[Vue.js Frontend]
    B --> C[Nginx Reverse Proxy]
    C --> D[Spring Boot API]
    D --> E[JWT Authentication Service]
    D --> F[Product Service]
    D --> G[Cart Service]
    D --> H[Payment Service]
    H --> I[Stripe API]
    D --> J[MySQL Database]
    D --> K[Redis Cache]
    E --> L[JWT Token Storage]

    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style D fill:#e8f5e8
    style I fill:#fff3e0
    style J fill:#fce4ec
    style K fill:#fff8e1
```

## ⭐ Core Features & Functionality

### 🔐 1. Authentication & Authorization System
- **JWT Token-based Authentication**
- **Role-based Access Control (Admin/User)**
- **Secure Login/Logout Flow**
- **Password Encryption & Validation**

### 🛒 2. Product & Category Management
- **Complete CRUD Operations**
- **Category-based Product Organization**
- **Product Search & Filtering**
- **Image Upload & Management**

### 🛍️ 3. Shopping Cart System
- **Session-based Cart Management**
- **Real-time Cart Updates**
- **Quantity Adjustments**
- **Cart Persistence**

### 💳 4. Stripe Payment Integration
- **Secure Payment Processing**
- **Multiple Payment Methods**
- **Transaction Tracking**
- **Webhook Integration**

## 🖥️ Backend Implementation Deep Dive

### 🔐 JWT Authentication & Security Configuration

```java
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class SecurityConfig {

    @Autowired
    private JwtAuthenticationEntryPoint jwtAuthenticationEntryPoint;

    @Autowired
    private JwtRequestFilter jwtRequestFilter;

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(
            AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.csrf().disable()
            .authorizeHttpRequests(authz -> authz
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/api/products/**").permitAll()
                .requestMatchers("/api/categories/**").permitAll()
                .requestMatchers("/api/cart/**").authenticated()
                .requestMatchers("/api/orders/**").authenticated()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling()
                .authenticationEntryPoint(jwtAuthenticationEntryPoint)
            .and()
            .sessionManagement()
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS);

        http.addFilterBefore(jwtRequestFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
```

### 🔑 JWT Token Management Service

```java
@Service
public class JwtTokenService {

    private static final String SECRET_KEY = "${jwt.secret}";
    private static final int JWT_EXPIRATION = 86400; // 24 hours

    /**
     * Generate JWT token for authenticated user
     */
    public String generateToken(UserDetails userDetails) {
        Map<String, Object> claims = new HashMap<>();

        // Add user roles to claims
        Collection<? extends GrantedAuthority> authorities = userDetails.getAuthorities();
        claims.put("roles", authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toList()));

        return createToken(claims, userDetails.getUsername());
    }

    /**
     * Create JWT token with claims and subject
     */
    private String createToken(Map<String, Object> claims, String subject) {
        return Jwts.builder()
            .setClaims(claims)
            .setSubject(subject)
            .setIssuedAt(new Date(System.currentTimeMillis()))
            .setExpiration(new Date(System.currentTimeMillis() + JWT_EXPIRATION * 1000))
            .signWith(SignatureAlgorithm.HS512, SECRET_KEY)
            .compact();
    }

    /**
     * Validate JWT token
     */
    public Boolean validateToken(String token, UserDetails userDetails) {
        try {
            final String username = getUsernameFromToken(token);
            return (username.equals(userDetails.getUsername()) && !isTokenExpired(token));
        } catch (ExpiredJwtException | UnsupportedJwtException |
                 MalformedJwtException | IllegalArgumentException e) {
            log.error("JWT validation error: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Extract username from JWT token
     */
    public String getUsernameFromToken(String token) {
        return getClaimFromToken(token, Claims::getSubject);
    }

    /**
     * Extract expiration date from JWT token
     */
    public Date getExpirationDateFromToken(String token) {
        return getClaimFromToken(token, Claims::getExpiration);
    }

    private <T> T getClaimFromToken(String token, Function<Claims, T> claimsResolver) {
        final Claims claims = getAllClaimsFromToken(token);
        return claimsResolver.apply(claims);
    }

    private Claims getAllClaimsFromToken(String token) {
        return Jwts.parser().setSigningKey(SECRET_KEY).parseClaimsJws(token).getBody();
    }

    private Boolean isTokenExpired(String token) {
        final Date expiration = getExpirationDateFromToken(token);
        return expiration.before(new Date());
    }
}
```

### 🛒 Product Management REST API

```java
@RestController
@RequestMapping("/api/products")
@CrossOrigin(origins = "${app.cors.allowed-origins}")
public class ProductController {

    @Autowired
    private ProductService productService;

    /**
     * Get all products with pagination and filtering
     */
    @GetMapping
    public ResponseEntity<ProductResponse> getAllProducts(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(defaultValue = "id") String sortBy,
            @RequestParam(defaultValue = "asc") String sortDir,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword) {

        try {
            PageRequest pageable = PageRequest.of(page, size,
                Sort.Direction.fromString(sortDir), sortBy);

            ProductResponse response = productService.getAllProducts(
                pageable, categoryId, keyword);

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("Error fetching products", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ProductResponse.error("Failed to fetch products"));
        }
    }

    /**
     * Get product by ID
     */
    @GetMapping("/{id}")
    public ResponseEntity<ProductDto> getProductById(@PathVariable Long id) {
        try {
            ProductDto product = productService.getProductById(id);
            return ResponseEntity.ok(product);
        } catch (ProductNotFoundException e) {
            return ResponseEntity.notFound().build();
        } catch (Exception e) {
            log.error("Error fetching product with id: {}", id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * Create new product (Admin only)
     */
    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ProductDto> createProduct(
            @Valid @RequestBody CreateProductRequest request) {
        try {
            ProductDto createdProduct = productService.createProduct(request);
            return ResponseEntity.status(HttpStatus.CREATED).body(createdProduct);
        } catch (ValidationException e) {
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error creating product", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * Update existing product (Admin only)
     */
    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ProductDto> updateProduct(
            @PathVariable Long id,
            @Valid @RequestBody UpdateProductRequest request) {
        try {
            ProductDto updatedProduct = productService.updateProduct(id, request);
            return ResponseEntity.ok(updatedProduct);
        } catch (ProductNotFoundException e) {
            return ResponseEntity.notFound().build();
        } catch (ValidationException e) {
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error updating product with id: {}", id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * Delete product (Admin only)
     */
    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> deleteProduct(@PathVariable Long id) {
        try {
            productService.deleteProduct(id);
            return ResponseEntity.noContent().build();
        } catch (ProductNotFoundException e) {
            return ResponseEntity.notFound().build();
        } catch (Exception e) {
            log.error("Error deleting product with id: {}", id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * Search products by keyword
     */
    @GetMapping("/search")
    public ResponseEntity<List<ProductDto>> searchProducts(
            @RequestParam String keyword,
            @RequestParam(defaultValue = "10") int limit) {
        try {
            List<ProductDto> products = productService.searchProducts(keyword, limit);
            return ResponseEntity.ok(products);
        } catch (Exception e) {
            log.error("Error searching products with keyword: {}", keyword, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
}
```

### 🛍️ Shopping Cart Service Implementation

```java
@Service
@Transactional
public class CartService {

    @Autowired
    private CartRepository cartRepository;

    @Autowired
    private CartItemRepository cartItemRepository;

    @Autowired
    private ProductService productService;

    /**
     * Get or create cart for user
     */
    public CartDto getOrCreateCart(Long userId) {
        Cart cart = cartRepository.findByUserId(userId)
            .orElseGet(() -> {
                Cart newCart = new Cart();
                newCart.setUserId(userId);
                newCart.setCreatedAt(LocalDateTime.now());
                return cartRepository.save(newCart);
            });

        return convertToDto(cart);
    }

    /**
     * Add item to cart
     */
    public CartDto addItemToCart(Long userId, AddToCartRequest request) {
        // Validate product exists and has sufficient stock
        ProductDto product = productService.getProductById(request.getProductId());
        if (product.getStock() < request.getQuantity()) {
            throw new InsufficientStockException("Not enough stock available");
        }

        Cart cart = cartRepository.findByUserId(userId)
            .orElseGet(() -> {
                Cart newCart = new Cart();
                newCart.setUserId(userId);
                newCart.setCreatedAt(LocalDateTime.now());
                return cartRepository.save(newCart);
            });

        // Check if item already exists in cart
        Optional<CartItem> existingItem = cartItemRepository
            .findByCartAndProductId(cart, request.getProductId());

        if (existingItem.isPresent()) {
            // Update quantity
            CartItem item = existingItem.get();
            int newQuantity = item.getQuantity() + request.getQuantity();

            // Validate total quantity
            if (product.getStock() < newQuantity) {
                throw new InsufficientStockException("Total quantity exceeds available stock");
            }

            item.setQuantity(newQuantity);
            item.setUpdatedAt(LocalDateTime.now());
            cartItemRepository.save(item);
        } else {
            // Create new cart item
            CartItem newItem = new CartItem();
            newItem.setCart(cart);
            newItem.setProductId(request.getProductId());
            newItem.setQuantity(request.getQuantity());
            newItem.setPrice(product.getPrice());
            newItem.setCreatedAt(LocalDateTime.now());
            cartItemRepository.save(newItem);
        }

        // Update cart totals
        updateCartTotals(cart);

        return convertToDto(cart);
    }

    /**
     * Update item quantity in cart
     */
    public CartDto updateCartItem(Long userId, Long itemId, UpdateCartItemRequest request) {
        CartItem item = cartItemRepository.findById(itemId)
            .orElseThrow(() -> new CartItemNotFoundException("Cart item not found"));

        // Verify ownership
        if (!item.getCart().getUserId().equals(userId)) {
            throw new UnauthorizedException("Not authorized to modify this cart item");
        }

        // Validate product stock
        ProductDto product = productService.getProductById(item.getProductId());
        if (product.getStock() < request.getQuantity()) {
            throw new InsufficientStockException("Not enough stock available");
        }

        // Update quantity
        item.setQuantity(request.getQuantity());
        item.setUpdatedAt(LocalDateTime.now());
        cartItemRepository.save(item);

        // Update cart totals
        updateCartTotals(item.getCart());

        return convertToDto(item.getCart());
    }

    /**
     * Remove item from cart
     */
    public CartDto removeCartItem(Long userId, Long itemId) {
        CartItem item = cartItemRepository.findById(itemId)
            .orElseThrow(() -> new CartItemNotFoundException("Cart item not found"));

        // Verify ownership
        if (!item.getCart().getUserId().equals(userId)) {
            throw new UnauthorizedException("Not authorized to modify this cart item");
        }

        Cart cart = item.getCart();
        cartItemRepository.delete(item);

        // Update cart totals
        updateCartTotals(cart);

        return convertToDto(cart);
    }

    /**
     * Clear entire cart
     */
    public void clearCart(Long userId) {
        Cart cart = cartRepository.findByUserId(userId)
            .orElseThrow(() -> new CartNotFoundException("Cart not found"));

        cartItemRepository.deleteByCart(cart);
        cart.setTotalAmount(BigDecimal.ZERO);
        cart.setItemCount(0);
        cartRepository.save(cart);
    }

    /**
     * Update cart totals (amount and item count)
     */
    private void updateCartTotals(Cart cart) {
        List<CartItem> items = cartItemRepository.findByCart(cart);

        BigDecimal totalAmount = items.stream()
            .map(item -> item.getPrice().multiply(BigDecimal.valueOf(item.getQuantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        int itemCount = items.stream()
            .mapToInt(CartItem::getQuantity)
            .sum();

        cart.setTotalAmount(totalAmount);
        cart.setItemCount(itemCount);
        cart.setUpdatedAt(LocalDateTime.now());

        cartRepository.save(cart);
    }

    /**
     * Convert Cart entity to DTO
     */
    private CartDto convertToDto(Cart cart) {
        List<CartItem> items = cartItemRepository.findByCart(cart);

        List<CartItemDto> itemDtos = items.stream()
            .map(this::convertItemToDto)
            .collect(Collectors.toList());

        return CartDto.builder()
            .id(cart.getId())
            .userId(cart.getUserId())
            .items(itemDtos)
            .totalAmount(cart.getTotalAmount())
            .itemCount(cart.getItemCount())
            .createdAt(cart.getCreatedAt())
            .updatedAt(cart.getUpdatedAt())
            .build();
    }

    private CartItemDto convertItemToDto(CartItem item) {
        ProductDto product = productService.getProductById(item.getProductId());

        return CartItemDto.builder()
            .id(item.getId())
            .product(product)
            .quantity(item.getQuantity())
            .price(item.getPrice())
            .totalPrice(item.getPrice().multiply(BigDecimal.valueOf(item.getQuantity())))
            .createdAt(item.getCreatedAt())
            .updatedAt(item.getUpdatedAt())
            .build();
    }
}
```

### 💳 Stripe Payment Integration

```java
@Service
public class StripePaymentService {

    @Value("${stripe.secret-key}")
    private String stripeSecretKey;

    @PostConstruct
    public void init() {
        Stripe.apiKey = stripeSecretKey;
    }

    /**
     * Create payment intent for checkout
     */
    public PaymentIntentResponse createPaymentIntent(CreatePaymentRequest request) {
        try {
            // Calculate total amount from cart
            CartDto cart = cartService.getCart(request.getUserId());
            long amount = cart.getTotalAmount().multiply(BigDecimal.valueOf(100)).longValue();

            PaymentIntentCreateParams params = PaymentIntentCreateParams.builder()
                .setAmount(amount)
                .setCurrency("usd")
                .addPaymentMethodType("card")
                .setConfirmationMethod(PaymentIntentCreateParams.ConfirmationMethod.MANUAL)
                .setConfirm(true)
                .setReturnUrl(request.getReturnUrl())
                .putMetadata("userId", String.valueOf(request.getUserId()))
                .putMetadata("cartId", String.valueOf(cart.getId()))
                .build();

            PaymentIntent paymentIntent = PaymentIntent.create(params);

            return PaymentIntentResponse.builder()
                .id(paymentIntent.getId())
                .clientSecret(paymentIntent.getClientSecret())
                .status(paymentIntent.getStatus())
                .amount(paymentIntent.getAmount())
                .currency(paymentIntent.getCurrency())
                .build();

        } catch (StripeException e) {
            log.error("Stripe payment intent creation failed", e);
            throw new PaymentProcessingException("Payment processing failed: " + e.getMessage());
        }
    }

    /**
     * Confirm payment intent
     */
    public PaymentIntentResponse confirmPayment(String paymentIntentId) {
        try {
            PaymentIntent paymentIntent = PaymentIntent.retrieve(paymentIntentId);

            PaymentIntentConfirmParams params = PaymentIntentConfirmParams.builder()
                .setReturnUrl("https://your-website.com/return")
                .build();

            paymentIntent = paymentIntent.confirm(params);

            // If payment successful, create order
            if ("succeeded".equals(paymentIntent.getStatus())) {
                Long userId = Long.valueOf(paymentIntent.getMetadata().get("userId"));
                createOrderFromPayment(paymentIntent, userId);
            }

            return PaymentIntentResponse.builder()
                .id(paymentIntent.getId())
                .status(paymentIntent.getStatus())
                .amount(paymentIntent.getAmount())
                .currency(paymentIntent.getCurrency())
                .build();

        } catch (StripeException e) {
            log.error("Stripe payment confirmation failed", e);
            throw new PaymentProcessingException("Payment confirmation failed: " + e.getMessage());
        }
    }

    /**
     * Handle Stripe webhook events
     */
    @PostMapping("/webhook")
    public ResponseEntity<String> handleStripeWebhook(
            @RequestBody String payload,
            @RequestHeader("Stripe-Signature") String sigHeader) {

        try {
            Event event = Webhook.constructEvent(payload, sigHeader, webhookSecret);

            switch (event.getType()) {
                case "payment_intent.succeeded":
                    handlePaymentSuccess(event);
                    break;
                case "payment_intent.payment_failed":
                    handlePaymentFailure(event);
                    break;
                default:
                    log.info("Unhandled event type: {}", event.getType());
            }

            return ResponseEntity.ok("Success");

        } catch (SignatureVerificationException e) {
            log.error("Invalid Stripe signature", e);
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("Invalid signature");
        } catch (Exception e) {
            log.error("Webhook processing error", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("Webhook error");
        }
    }

    private void handlePaymentSuccess(Event event) {
        PaymentIntent paymentIntent = (PaymentIntent) event.getDataObjectDeserializer()
            .getObject().orElse(null);

        if (paymentIntent != null) {
            Long userId = Long.valueOf(paymentIntent.getMetadata().get("userId"));
            createOrderFromPayment(paymentIntent, userId);

            // Send confirmation email
            notificationService.sendPaymentConfirmation(userId, paymentIntent.getId());
        }
    }

    private void createOrderFromPayment(PaymentIntent paymentIntent, Long userId) {
        try {
            CreateOrderRequest orderRequest = CreateOrderRequest.builder()
                .userId(userId)
                .paymentIntentId(paymentIntent.getId())
                .totalAmount(BigDecimal.valueOf(paymentIntent.getAmount()).divide(BigDecimal.valueOf(100)))
                .currency(paymentIntent.getCurrency())
                .build();

            orderService.createOrderFromCart(orderRequest);
            cartService.clearCart(userId);

        } catch (Exception e) {
            log.error("Failed to create order from payment", e);
        }
    }
}
```

## 💻 Frontend Implementation Highlights

### 🛒 Shopping Cart Component

```vue
<template>
  <div class="shopping-cart">
    <!-- Cart Header -->
    <div class="cart-header">
      <h2>Shopping Cart</h2>
      <span class="item-count">({{ cart.itemCount }} items)</span>
    </div>

    <!-- Cart Items -->
    <div v-if="cart.items.length > 0" class="cart-items">
      <div
        v-for="item in cart.items"
        :key="item.id"
        class="cart-item"
      >
        <div class="item-image">
          <img :src="item.product.imageUrl" :alt="item.product.name" />
        </div>

        <div class="item-details">
          <h4>{{ item.product.name }}</h4>
          <p class="item-price">${{ item.price }}</p>
        </div>

        <div class="quantity-controls">
          <button
            @click="decreaseQuantity(item)"
            :disabled="item.quantity <= 1 || updating"
            class="qty-btn"
          >
            -
          </button>
          <input
            v-model.number="item.quantity"
            @blur="updateQuantity(item)"
            type="number"
            min="1"
            class="qty-input"
          />
          <button
            @click="increaseQuantity(item)"
            :disabled="updating"
            class="qty-btn"
          >
            +
          </button>
        </div>

        <div class="item-total">
          ${{ item.totalPrice.toFixed(2) }}
        </div>

        <button
          @click="removeItem(item.id)"
          :disabled="updating"
          class="remove-btn"
        >
          🗑️
        </button>
      </div>
    </div>

    <!-- Empty Cart Message -->
    <div v-else class="empty-cart">
      <h3>Your cart is empty</h3>
      <p>Add some products to get started!</p>
      <router-link to="/products" class="continue-shopping-btn">
        Continue Shopping
      </router-link>
    </div>

    <!-- Cart Summary -->
    <div v-if="cart.items.length > 0" class="cart-summary">
      <div class="summary-row">
        <span>Subtotal:</span>
        <span>${{ cart.totalAmount.toFixed(2) }}</span>
      </div>
      <div class="summary-row">
        <span>Shipping:</span>
        <span>Free</span>
      </div>
      <div class="summary-row total">
        <strong>
          <span>Total:</span>
          <span>${{ cart.totalAmount.toFixed(2) }}</span>
        </strong>
      </div>

      <button
        @click="proceedToCheckout"
        :disabled="cart.items.length === 0 || processing"
        class="checkout-btn"
      >
        {{ processing ? 'Processing...' : 'Proceed to Checkout' }}
      </button>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions } from 'vuex'

export default {
  name: 'ShoppingCart',
  data() {
    return {
      updating: false,
      processing: false,
      loading: false
    }
  },
  computed: {
    ...mapState('cart', ['cart'])
  },
  methods: {
    ...mapActions('cart', [
      'fetchCart',
      'updateCartItem',
      'removeCartItem',
      'clearCart'
    ]),

    async increaseQuantity(item) {
      await this.updateQuantity(item, item.quantity + 1)
    },

    async decreaseQuantity(item) {
      if (item.quantity > 1) {
        await this.updateQuantity(item, item.quantity - 1)
      }
    },

    async updateQuantity(item, newQuantity = null) {
      try {
        this.updating = true
        const quantity = newQuantity || item.quantity

        if (quantity < 1) {
          item.quantity = 1
          return
        }

        await this.updateCartItem({
          itemId: item.id,
          quantity: quantity
        })

        this.$toast.success('Cart updated successfully')
      } catch (error) {
        this.$toast.error('Failed to update cart: ' + error.message)
        await this.fetchCart() // Refresh cart on error
      } finally {
        this.updating = false
      }
    },

    async removeItem(itemId) {
      try {
        this.updating = true
        await this.removeCartItem(itemId)
        this.$toast.success('Item removed from cart')
      } catch (error) {
        this.$toast.error('Failed to remove item: ' + error.message)
      } finally {
        this.updating = false
      }
    },

    async proceedToCheckout() {
      try {
        this.processing = true

        // Navigate to checkout with cart data
        this.$router.push({
          name: 'Checkout',
          params: { cart: this.cart }
        })
      } catch (error) {
        this.$toast.error('Failed to proceed to checkout')
      } finally {
        this.processing = false
      }
    }
  },

  async created() {
    try {
      this.loading = true
      await this.fetchCart()
    } catch (error) {
      this.$toast.error('Failed to load cart')
    } finally {
      this.loading = false
    }
  }
}
</script>
```

### 💳 Stripe Checkout Component

```vue
<template>
  <div class="stripe-checkout">
    <div class="checkout-container">
      <h2>Complete Your Purchase</h2>

      <!-- Order Summary -->
      <div class="order-summary">
        <h3>Order Summary</h3>
        <div v-for="item in cart.items" :key="item.id" class="summary-item">
          <span>{{ item.product.name }} x{{ item.quantity }}</span>
          <span>${{ item.totalPrice.toFixed(2) }}</span>
        </div>
        <div class="total-row">
          <strong>
            <span>Total: ${{ cart.totalAmount.toFixed(2) }}</span>
          </strong>
        </div>
      </div>

      <!-- Payment Form -->
      <div class="payment-form">
        <h3>Payment Information</h3>

        <!-- Stripe Elements -->
        <div id="card-element" class="stripe-element">
          <!-- Stripe Elements will create form elements here -->
        </div>
        <div id="card-errors" class="error-message"></div>

        <!-- Customer Information -->
        <div class="customer-info">
          <div class="form-group">
            <label for="email">Email Address</label>
            <input
              id="email"
              v-model="customerInfo.email"
              type="email"
              required
              class="form-input"
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="firstName">First Name</label>
              <input
                id="firstName"
                v-model="customerInfo.firstName"
                type="text"
                required
                class="form-input"
              />
            </div>
            <div class="form-group">
              <label for="lastName">Last Name</label>
              <input
                id="lastName"
                v-model="customerInfo.lastName"
                type="text"
                required
                class="form-input"
              />
            </div>
          </div>
        </div>

        <!-- Submit Button -->
        <button
          @click="handlePayment"
          :disabled="!canSubmit || processing"
          class="pay-button"
        >
          <span v-if="processing">Processing...</span>
          <span v-else>Pay ${{ cart.totalAmount.toFixed(2) }}</span>
        </button>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>Processing your payment...</p>
    </div>
  </div>
</template>

<script>
import { loadStripe } from '@stripe/stripe-js'

export default {
  name: 'StripeCheckout',
  props: {
    cart: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      stripe: null,
      elements: null,
      card: null,
      processing: false,
      loading: false,
      customerInfo: {
        email: '',
        firstName: '',
        lastName: ''
      }
    }
  },
  computed: {
    canSubmit() {
      return (
        this.customerInfo.email &&
        this.customerInfo.firstName &&
        this.customerInfo.lastName &&
        this.card &&
        !this.processing
      )
    }
  },
  async mounted() {
    await this.initializeStripe()
  },
  methods: {
    async initializeStripe() {
      try {
        // Load Stripe
        this.stripe = await loadStripe(process.env.VUE_APP_STRIPE_PUBLISHABLE_KEY)

        // Create elements
        this.elements = this.stripe.elements()

        // Create card element
        this.card = this.elements.create('card', {
          style: {
            base: {
              fontSize: '16px',
              color: '#424770',
              '::placeholder': {
                color: '#aab7c4',
              },
            },
          },
        })

        // Mount card element
        this.card.mount('#card-element')

        // Listen for real-time validation errors
        this.card.addEventListener('change', this.handleCardChange)

      } catch (error) {
        console.error('Failed to initialize Stripe:', error)
        this.$toast.error('Payment system initialization failed')
      }
    },

    handleCardChange(event) {
      const displayError = document.getElementById('card-errors')
      if (event.error) {
        displayError.textContent = event.error.message
      } else {
        displayError.textContent = ''
      }
    },

    async handlePayment() {
      if (!this.canSubmit) return

      try {
        this.processing = true
        this.loading = true

        // Create payment intent
        const paymentIntentResponse = await this.$http.post('/api/payments/create-intent', {
          amount: Math.round(this.cart.totalAmount * 100), // Convert to cents
          currency: 'usd',
          customerInfo: this.customerInfo,
          cartId: this.cart.id
        })

        const { client_secret: clientSecret } = paymentIntentResponse.data

        // Confirm payment
        const { error, paymentIntent } = await this.stripe.confirmCardPayment(clientSecret, {
          payment_method: {
            card: this.card,
            billing_details: {
              name: `${this.customerInfo.firstName} ${this.customerInfo.lastName}`,
              email: this.customerInfo.email,
            },
          }
        })

        if (error) {
          throw new Error(error.message)
        }

        if (paymentIntent.status === 'succeeded') {
          await this.handlePaymentSuccess(paymentIntent)
        }

      } catch (error) {
        console.error('Payment failed:', error)
        this.$toast.error('Payment failed: ' + error.message)
      } finally {
        this.processing = false
        this.loading = false
      }
    },

    async handlePaymentSuccess(paymentIntent) {
      try {
        // Confirm payment on backend
        await this.$http.post('/api/payments/confirm', {
          paymentIntentId: paymentIntent.id
        })

        // Clear cart
        await this.$store.dispatch('cart/clearCart')

        // Navigate to success page
        this.$router.push({
          name: 'PaymentSuccess',
          params: { paymentIntentId: paymentIntent.id }
        })

        this.$toast.success('Payment successful! Your order has been placed.')

      } catch (error) {
        console.error('Payment confirmation failed:', error)
        this.$toast.error('Payment was successful, but order creation failed. Please contact support.')
      }
    }
  },

  beforeDestroy() {
    if (this.card) {
      this.card.destroy()
    }
  }
}
</script>
```

## 🚀 Deployment & Configuration

### 🐳 Docker Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  # MySQL Database
  mysql:
    image: mysql:8.0
    container_name: ecommerce-mysql
    environment:
      MYSQL_DATABASE: ecommerce_db
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - ecommerce-network

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: ecommerce-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - ecommerce-network

  # Spring Boot Backend
  backend:
    build:
      context: ./Backend
      dockerfile: Dockerfile
    container_name: ecommerce-backend
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=ecommerce_db
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_HOST=redis
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
    ports:
      - "9999:9999"
    depends_on:
      - mysql
      - redis
    volumes:
      - ./logs:/app/logs
      - ./uploads:/app/uploads
    networks:
      - ecommerce-network
    restart: unless-stopped

  # Vue.js Frontend
  frontend:
    build:
      context: ./Frontend
      dockerfile: Dockerfile
    container_name: ecommerce-frontend
    environment:
      - VUE_APP_API_BASE_URL=http://localhost:9999/api
      - VUE_APP_STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY}
    ports:
      - "8080:80"
    depends_on:
      - backend
    networks:
      - ecommerce-network
    restart: unless-stopped

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: ecommerce-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - frontend
      - backend
    networks:
      - ecommerce-network
    restart: unless-stopped

volumes:
  mysql_data:
  redis_data:

networks:
  ecommerce-network:
    driver: bridge
```

### ⚙️ Application Configuration

```properties
# application-docker.properties

# Server Configuration
server.port=9999
server.servlet.context-path=/api

# Database Configuration
spring.datasource.url=jdbc:mysql://${DB_HOST}:${DB_PORT}/${DB_NAME}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver

# JPA Configuration
spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=false
spring.jpa.database-platform=org.hibernate.dialect.MySQL8Dialect
spring.jpa.properties.hibernate.format_sql=true

# Redis Configuration
spring.redis.host=${REDIS_HOST}
spring.redis.port=6379
spring.redis.timeout=2000ms
spring.redis.lettuce.pool.max-active=10
spring.cache.type=redis

# File Upload Configuration
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=10MB
app.upload.dir=./uploads

# Stripe Configuration
stripe.secret-key=${STRIPE_SECRET_KEY}
stripe.publishable-key=${STRIPE_PUBLISHABLE_KEY}
stripe.webhook-secret=${STRIPE_WEBHOOK_SECRET}

# JWT Configuration
jwt.secret=${JWT_SECRET}
jwt.expiration=86400

# CORS Configuration
app.cors.allowed-origins=http://localhost:8080,http://localhost:3000
app.cors.allowed-methods=GET,POST,PUT,DELETE,OPTIONS
app.cors.allowed-headers=*

# Logging Configuration
logging.level.com.yen.ecommerce=INFO
logging.pattern.file=%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n
logging.file.name=./logs/ecommerce-app.log

# Email Configuration (for notifications)
spring.mail.host=smtp.gmail.com
spring.mail.port=587
spring.mail.username=${EMAIL_USERNAME}
spring.mail.password=${EMAIL_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
```

## 💎 Key Features & Innovations

### 🔐 1. Robust Security Implementation
- **JWT Token Management** with automatic refresh
- **Role-based Access Control** for admin/user operations
- **Password encryption** using BCrypt
- **CORS protection** and request validation

### 💳 2. Advanced Payment Processing
- **Stripe Payment Intents** for secure transactions
- **Webhook integration** for real-time payment status
- **Multiple payment methods** support
- **Transaction tracking** and order management

### 🛒 3. Intelligent Cart Management
- **Session-based persistence** across browser sessions
- **Real-time inventory** validation
- **Quantity management** with stock checks
- **Automatic total calculation** and updates

### 📱 4. Responsive Frontend Design
- **Modern Vue.js 3** with Composition API
- **Mobile-first design** approach
- **Real-time UI updates** with Vuex state management
- **Toast notifications** for user feedback

## 🔮 Future Enhancements & Roadmap

### 📋 Phase 1 (Next 3-6 months)
- [ ] **Product Reviews & Ratings System**
- [ ] **Wishlist Functionality**
- [ ] **Order Tracking & History**
- [ ] **Email Notifications** for order status

### 🎯 Phase 2 (6-12 months)
- [ ] **Admin Dashboard** with analytics
- [ ] **Inventory Management** system
- [ ] **Coupon & Discount** system
- [ ] **Multi-vendor Support**

### 🌟 Phase 3 (1+ years)
- [ ] **Mobile App** (React Native/Flutter)
- [ ] **AI-powered Recommendations**
- [ ] **Multi-language Support**
- [ ] **Advanced Analytics** dashboard

## 🎉 Conclusion & Key Takeaways

This Spring Boot e-commerce shopping cart project demonstrates the implementation of a **production-ready e-commerce platform** with modern web technologies. The system successfully integrates secure payment processing, robust authentication, and comprehensive cart management functionality.

### 🔧 Technical Achievements
- **Full-stack Integration**: Seamless communication between Vue.js frontend and Spring Boot backend
- **Payment Security**: PCI-compliant payment processing with Stripe integration
- **Scalable Architecture**: Microservices-ready design with Docker containerization
- **Real-time Features**: WebSocket integration for live cart updates

### 💎 Business Value
- **User-centric Design**: Intuitive shopping experience with responsive interface
- **Security-first Approach**: JWT authentication and secure payment processing
- **Scalability**: Containerized architecture ready for cloud deployment
- **Maintainability**: Clean code architecture with comprehensive documentation

This project showcases the **power of modern Java frameworks** combined with **contemporary frontend technologies** to create a robust, secure, and scalable e-commerce solution.

---

## 🔗 Project Resources

| Resource | Link |
|----------|------|
| 📂 **Source Code** | [GitHub - SpringPlayground/ShoppingCart](https://github.com/yennanliu/SpringPlayground/tree/main/ShoppingCart) |
| 🌐 **Live Demo** | Coming Soon |
| 📖 **API Documentation** | [Swagger UI](http://localhost:9999/swagger-ui.html) |
| 🛠️ **Setup Guide** | [Installation Instructions](https://github.com/yennanliu/SpringPlayground/tree/main/ShoppingCart#readme) |