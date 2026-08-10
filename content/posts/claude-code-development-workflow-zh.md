---
title: "Claude Code 開發工作流程完整指南：從需求到部署的最佳實踐"
date: 2026-01-17T14:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "ai", "tools"]
tags: ["AI", "claude-code", "工作流程", "開發流程", "最佳實踐", "軟體開發", "敏捷開發", "development-tools"]
summary: "詳細解析使用 Claude Code 的標準開發工作流程：涵蓋需求分析、架構設計、功能開發、測試部署等完整生命週期，並提供不同開發情境的具體實踐策略。"
readTime: "25 min"
---

使用 Claude Code 進行開發不僅僅是「問 AI 寫程式碼」那麼簡單。真正高效的開發需要建立系統化的工作流程，從需求分析到部署上線，每個階段都有最佳實踐。本文將深入探討如何在軟體開發生命週期的各個階段充分發揮 Claude Code 的潛力。

## 🎯 為什麼需要標準化工作流程？

### 無流程 vs 有流程的對比

```
❌ 無流程開發（混亂模式）：
使用者: "幫我寫個登入功能"
Claude: [寫了一些程式碼]
使用者: "欸不對，我要用 OAuth"
Claude: [重寫]
使用者: "忘了說，還要雙因素驗證"
Claude: [再改]
使用者: "糟糕，沒考慮到資料庫設計..."
...反覆修改，浪費大量時間...

結果：
• 程式碼品質不一致
• 缺少測試和文檔
• 頻繁返工
• 技術債累積

✅ 有流程開發（系統化模式）：

階段 1: 需求分析 (15 分鐘)
→ 明確功能範圍
→ 識別技術限制
→ 規劃整體架構

階段 2: 設計規劃 (20 分鐘)
→ 資料庫設計
→ API 設計
→ 前端架構

階段 3: 開發實作 (60 分鐘)
→ 後端開發
→ 前端開發
→ 整合測試

階段 4: 測試部署 (30 分鐘)
→ 單元測試
→ 整合測試
→ 部署檢查

結果：
• 高品質、可維護的程式碼
• 完整的測試覆蓋
• 清晰的文檔
• 減少技術債
```

## 📋 標準開發流程總覽

### 完整的開發生命週期

```
┌────────────────────────────────────────────────────┐
│          Claude Code 開發生命週期                  │
│                                                    │
│  1️⃣ 需求分析階段 (Requirements Analysis)          │
│     ├─ 理解需求                                    │
│     ├─ 識別限制條件                                │
│     ├─ 評估可行性                                  │
│     └─ 定義驗收標準                                │
│                                                    │
│  2️⃣ 設計規劃階段 (Design & Planning)              │
│     ├─ 架構設計                                    │
│     ├─ 資料庫設計                                  │
│     ├─ API 設計                                    │
│     └─ 任務分解                                    │
│                                                    │
│  3️⃣ 開發實作階段 (Implementation)                 │
│     ├─ 後端開發                                    │
│     ├─ 前端開發                                    │
│     ├─ 整合開發                                    │
│     └─ 程式碼審查                                  │
│                                                    │
│  4️⃣ 測試驗證階段 (Testing & Validation)           │
│     ├─ 單元測試                                    │
│     ├─ 整合測試                                    │
│     ├─ E2E 測試                                    │
│     └─ 效能測試                                    │
│                                                    │
│  5️⃣ 部署上線階段 (Deployment)                     │
│     ├─ 部署前檢查                                  │
│     ├─ 部署執行                                    │
│     ├─ 監控驗證                                    │
│     └─ 文檔更新                                    │
│                                                    │
│  6️⃣ 維護優化階段 (Maintenance)                    │
│     ├─ Bug 修復                                    │
│     ├─ 效能優化                                    │
│     ├─ 功能增強                                    │
│     └─ 重構優化                                    │
└────────────────────────────────────────────────────┘
```

## 1️⃣ 需求分析階段

### 目標：充分理解並明確化需求

**與 Claude Code 的對話流程：**

```markdown
步驟 1: 初步需求描述
────────────────────────────────────────

使用者:
"我需要在電商網站加入購物車功能"

Claude 回應（引導式提問）:
"我來幫你分析購物車功能的需求。請回答以下問題：

【功能範圍】
1. 需要哪些核心功能？
   - 新增商品到購物車
   - 修改商品數量
   - 移除商品
   - 清空購物車
   - 其他？

2. 需要支援哪些特殊情境？
   - 未登入使用者的購物車（臨時儲存）
   - 多裝置同步
   - 購物車有效期限
   - 庫存檢查

【技術限制】
3. 現有技術棧？
   - 前端框架（React, Vue, Angular?）
   - 後端語言（Node.js, Python, Java?）
   - 資料庫（PostgreSQL, MongoDB?）
   - 狀態管理（Redux, Zustand?）

4. 整合需求？
   - 需要整合哪些現有功能？
   - 有哪些 API 要串接？

【限制條件】
5. 效能要求？
   - 預期使用者數量
   - 回應時間要求
   - 併發處理需求

6. 安全性要求？
   - 需要什麼層級的資料保護？
   - 是否需要防止惡意操作？"
```

**需求文檔範本：**

```markdown
步驟 2: 整理需求文檔
────────────────────────────────────────

使用者提供詳細資訊後：

"請根據我的回答，整理一份完整的需求文檔，
包含功能需求、技術需求、限制條件和驗收標準"

Claude 產出:

# 購物車功能需求文檔

## 1. 功能需求

### 1.1 核心功能
- **新增商品**: 使用者可將商品加入購物車
  - 支援指定數量
  - 支援選擇商品規格（顏色、尺寸）
  - 即時更新購物車數量顯示

- **修改數量**: 使用者可調整購物車中的商品數量
  - 支援直接輸入數量
  - 支援 +/- 按鈕調整
  - 數量限制：1-99

- **移除商品**: 使用者可從購物車移除商品
  - 提供確認對話框
  - 支援一鍵清空功能

- **購物車查看**: 顯示購物車內容
  - 商品資訊（名稱、圖片、價格、規格）
  - 小計和總計
  - 優惠折扣顯示

### 1.2 進階功能
- **臨時購物車**: 未登入使用者的購物車
  - 使用 localStorage 暫存
  - 登入後自動合併

- **庫存檢查**: 即時檢查商品庫存
  - 庫存不足時提示
  - 自動調整到最大可購買數量

- **購物車同步**: 多裝置購物車同步
  - 登入使用者的購物車存在伺服器
  - 裝置間即時同步

## 2. 技術需求

### 2.1 技術棧
- **前端**: React 18 + TypeScript
- **狀態管理**: Zustand
- **後端**: Node.js + Express
- **資料庫**: PostgreSQL
- **快取**: Redis（購物車資料）

### 2.2 API 設計
```typescript
// 購物車 API endpoints
POST   /api/cart/items        // 新增商品
PUT    /api/cart/items/:id    // 更新數量
DELETE /api/cart/items/:id    // 移除商品
GET    /api/cart              // 取得購物車
DELETE /api/cart              // 清空購物車
POST   /api/cart/merge        // 合併臨時購物車
```

### 2.3 資料庫設計
```sql
-- 購物車資料表
CREATE TABLE carts (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  session_id VARCHAR(255),  -- 未登入使用者
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- 購物車項目資料表
CREATE TABLE cart_items (
  id UUID PRIMARY KEY,
  cart_id UUID REFERENCES carts(id),
  product_id UUID REFERENCES products(id),
  quantity INTEGER CHECK (quantity > 0 AND quantity <= 99),
  variant_id UUID REFERENCES product_variants(id),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(cart_id, product_id, variant_id)
);
```

## 3. 限制條件

### 3.1 效能要求
- API 回應時間 < 200ms
- 支援 1000 併發請求
- 購物車最多 100 個商品

### 3.2 安全性要求
- API 需要認證（JWT）
- 防止 CSRF 攻擊
- 輸入驗證和淨化
- Rate limiting（每分鐘 60 請求）

### 3.3 相容性要求
- 支援現代瀏覽器（Chrome, Firefox, Safari, Edge）
- 移動裝置響應式設計
- 無障礙設計（WCAG 2.1 AA）

## 4. 驗收標準

### 4.1 功能驗收
- [ ] 使用者可以成功新增商品到購物車
- [ ] 購物車數量顯示正確
- [ ] 可以修改商品數量
- [ ] 可以移除商品
- [ ] 總金額計算正確
- [ ] 未登入使用者的購物車在登入後正確合併
- [ ] 庫存不足時正確提示

### 4.2 效能驗收
- [ ] 新增商品回應時間 < 200ms
- [ ] 頁面載入時間 < 1s
- [ ] 支援 1000 併發使用者

### 4.3 安全性驗收
- [ ] 未認證使用者無法存取他人購物車
- [ ] 輸入驗證正常運作
- [ ] XSS 和 CSRF 防護有效

## 5. 開發時程估算

- 資料庫設計與 API 開發: 2 天
- 前端元件開發: 3 天
- 整合與測試: 2 天
- 部署與文檔: 1 天

總計: 8 個工作天
```

### 需求確認檢查清單

```markdown
在進入設計階段前，確認以下項目：

功能需求
☐ 所有核心功能都已明確定義
☐ 邊界情況和例外情境已考慮
☐ 使用者體驗流程清晰
☐ 與現有功能的整合點已識別

技術需求
☐ 技術棧已確定
☐ 資料庫選擇已決定
☐ API 設計原則已定義
☐ 第三方服務整合需求明確

限制條件
☐ 效能要求已量化
☐ 安全性需求已明確
☐ 時間和資源限制已溝通
☐ 相容性要求已定義

驗收標準
☐ 功能驗收標準可測試
☐ 效能指標可量測
☐ 成功標準明確無歧義
```

## 2️⃣ 設計規劃階段

### 目標：設計可擴展、可維護的架構

**使用 Plan Mode 進行架構設計：**

```typescript
// 啟動 Plan Mode（適合複雜功能）

使用者:
"根據購物車需求文檔（docs/cart-requirements.md），
進入 Plan Mode 設計完整的實作計畫"

Claude 回應:
"我將進入 Plan Mode 為購物車功能設計實作計畫。
讓我先探索專案結構..."

[Claude 使用 Plan Agent]
• Glob 掃描專案結構
• Read 讀取相關檔案（現有的 API、資料庫設計）
• Grep 搜尋類似功能的實作參考
```

**Plan Agent 產出的實作計畫：**

```markdown
# 購物車功能實作計畫

## 階段 1: 資料庫設計 (2 小時)

### 1.1 Schema 設計
檔案: `prisma/schema.prisma`

```prisma
model Cart {
  id        String   @id @default(uuid())
  userId    String?  @map("user_id")
  sessionId String?  @map("session_id")
  items     CartItem[]
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  user User? @relation(fields: [userId], references: [id])

  @@index([userId])
  @@index([sessionId])
  @@map("carts")
}

model CartItem {
  id        String   @id @default(uuid())
  cartId    String   @map("cart_id")
  productId String   @map("product_id")
  variantId String?  @map("variant_id")
  quantity  Int
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  cart    Cart    @relation(fields: [cartId], references: [id], onDelete: Cascade)
  product Product @relation(fields: [productId], references: [id])
  variant ProductVariant? @relation(fields: [variantId], references: [id])

  @@unique([cartId, productId, variantId])
  @@index([cartId])
  @@map("cart_items")
}
```

### 1.2 Migration
```bash
npx prisma migrate dev --name add_cart_tables
```

## 階段 2: 後端實作 (4 小時)

### 2.1 服務層
檔案: `src/services/cartService.ts`

功能：
- `getCart(userId, sessionId)`: 取得購物車
- `addItem(cartId, productId, quantity, variantId)`: 新增商品
- `updateItemQuantity(itemId, quantity)`: 更新數量
- `removeItem(itemId)`: 移除商品
- `clearCart(cartId)`: 清空購物車
- `mergeCarts(userId, sessionId)`: 合併購物車
- `validateStock(productId, quantity)`: 驗證庫存

### 2.2 API 層
檔案: `src/api/cart/cartController.ts`

Endpoints:
- `GET /api/cart` → getCart()
- `POST /api/cart/items` → addItem()
- `PUT /api/cart/items/:id` → updateItem()
- `DELETE /api/cart/items/:id` → removeItem()
- `DELETE /api/cart` → clearCart()
- `POST /api/cart/merge` → mergeCarts()

### 2.3 中介層
檔案: `src/middleware/cartMiddleware.ts`

功能：
- `getOrCreateCart`: 取得或建立購物車
- `validateCartAccess`: 驗證購物車存取權限
- `checkStock`: 檢查庫存

### 2.4 驗證層
檔案: `src/validators/cartValidator.ts`

驗證規則：
- 商品 ID 格式
- 數量範圍（1-99）
- Variant ID（如有）

## 階段 3: Redis 快取 (1 小時)

### 3.1 快取策略
檔案: `src/services/cacheService.ts`

快取內容：
- 購物車資料（TTL: 1 小時）
- 商品庫存（TTL: 5 分鐘）

快取 Key 設計：
- `cart:{userId}` 或 `cart:session:{sessionId}`
- `stock:{productId}`

## 階段 4: 前端實作 (6 小時)

### 4.1 狀態管理
檔案: `src/stores/cartStore.ts`

使用 Zustand:
```typescript
interface CartStore {
  cart: Cart | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchCart: () => Promise<void>;
  addItem: (productId, quantity, variantId?) => Promise<void>;
  updateQuantity: (itemId, quantity) => Promise<void>;
  removeItem: (itemId) => Promise<void>;
  clearCart: () => Promise<void>;
}
```

### 4.2 元件開發
檔案結構:
```
src/components/Cart/
├── CartButton.tsx           # 購物車圖示按鈕
├── CartDrawer.tsx           # 購物車側邊欄
├── CartItem.tsx             # 購物車項目
├── CartSummary.tsx          # 購物車摘要
├── AddToCartButton.tsx      # 加入購物車按鈕
└── EmptyCart.tsx            # 空購物車狀態
```

### 4.3 API 整合
檔案: `src/api/cartApi.ts`

使用 axios:
```typescript
export const cartApi = {
  getCart: () => api.get('/cart'),
  addItem: (data) => api.post('/cart/items', data),
  updateItem: (id, data) => api.put(`/cart/items/${id}`, data),
  removeItem: (id) => api.delete(`/cart/items/${id}`),
  clearCart: () => api.delete('/cart'),
};
```

## 階段 5: 測試 (4 小時)

### 5.1 單元測試
- `cartService.test.ts`: 服務層邏輯測試
- `cartController.test.ts`: API 層測試
- `cartStore.test.ts`: 狀態管理測試

### 5.2 整合測試
- `cart.integration.test.ts`: API 整合測試
- 測試完整的購物車流程

### 5.3 E2E 測試
- `cart.e2e.test.ts`: 使用者操作流程測試

## 階段 6: 部署準備 (2 小時)

### 6.1 環境變數
```.env
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://...
```

### 6.2 部署檢查清單
- [ ] Migration 已執行
- [ ] Redis 連線正常
- [ ] API endpoints 測試通過
- [ ] 前端打包成功
- [ ] 環境變數已設定

### 6.3 文檔更新
- API 文檔（OpenAPI/Swagger）
- 使用者操作指南
- 開發者文檔

## 風險與注意事項

⚠️ **潛在風險:**
1. 併發購物車更新衝突
   → 使用樂觀鎖定（Optimistic Locking）

2. Redis 快取與資料庫不一致
   → 實作 Cache-Aside Pattern，設定適當 TTL

3. 庫存超賣問題
   → 在 checkout 時再次驗證庫存

4. 大量商品導致購物車載入慢
   → 實作分頁或虛擬捲動

## 總時程估算

- 階段 1 (資料庫): 2 小時
- 階段 2 (後端): 4 小時
- 階段 3 (快取): 1 小時
- 階段 4 (前端): 6 小時
- 階段 5 (測試): 4 小時
- 階段 6 (部署): 2 小時

**總計: 19 小時 (約 2.5 個工作天)**
```

**Plan Mode 的價值：**

```
✅ 使用 Plan Mode 的好處：

1. 全面性規劃
   • 考慮所有技術層面
   • 識別潛在問題
   • 規劃測試策略

2. 結構化執行
   • 明確的階段劃分
   • 清晰的檔案組織
   • 可追蹤的進度

3. 團隊協作
   • 可供審查的設計文檔
   • 明確的任務分工
   • 統一的實作標準

4. 風險管理
   • 提前識別風險
   • 規劃應對策略
   • 預估時程
```

## 3️⃣ 開發實作階段

### 目標：按計畫高效實作功能

**實作流程範例：後端開發**

```typescript
═══════════════════════════════════════════════════════
對話 1: 資料庫設計與 Migration
═══════════════════════════════════════════════════════

使用者:
"根據實作計畫（docs/cart-implementation-plan.md），
開始階段 1：資料庫設計。

請：
1. 更新 prisma/schema.prisma 加入 Cart 和 CartItem models
2. 產生 migration
3. 執行 migration
4. 驗證 schema"

Claude 執行:
├─ Read prisma/schema.prisma
├─ Edit 加入新的 models
├─ Bash: npx prisma migrate dev --name add_cart_tables
├─ Bash: npx prisma generate
└─ 回報執行結果

【使用 TodoWrite 追蹤進度】
✓ 完成: 設計 Cart 和 CartItem schema
✓ 完成: 建立 migration
✓ 完成: 執行 migration
⏳ 待處理: 實作 cartService
⏳ 待處理: 實作 API endpoints
...

═══════════════════════════════════════════════════════
對話 2: 服務層實作
═══════════════════════════════════════════════════════

使用者:
"實作 src/services/cartService.ts，包含計畫中的所有功能。

要求：
- 使用 Prisma Client
- 包含完整的錯誤處理
- 加入 JSDoc 註解
- 處理邊界情況（庫存不足、商品不存在等）"

Claude 執行:
├─ Read prisma/schema.prisma（了解 schema）
├─ Read src/services/userService.ts（參考現有服務模式）
├─ Write src/services/cartService.ts
└─ 加入完整的型別定義和錯誤處理

產出範例：

```typescript
// src/services/cartService.ts
import { PrismaClient } from '@prisma/client';
import { CartNotFoundError, InsufficientStockError } from '../errors';

const prisma = new PrismaClient();

export class CartService {
  /**
   * 取得購物車
   * @param userId - 使用者 ID（已登入）
   * @param sessionId - Session ID（未登入）
   */
  async getCart(userId?: string, sessionId?: string) {
    if (!userId && !sessionId) {
      throw new Error('userId or sessionId is required');
    }

    let cart = await prisma.cart.findFirst({
      where: userId ? { userId } : { sessionId },
      include: {
        items: {
          include: {
            product: true,
            variant: true,
          },
        },
      },
    });

    // 如果購物車不存在，建立新的
    if (!cart) {
      cart = await prisma.cart.create({
        data: {
          userId,
          sessionId,
        },
        include: {
          items: {
            include: {
              product: true,
              variant: true,
            },
          },
        },
      });
    }

    return cart;
  }

  /**
   * 新增商品到購物車
   */
  async addItem(
    cartId: string,
    productId: string,
    quantity: number,
    variantId?: string
  ) {
    // 驗證庫存
    await this.validateStock(productId, quantity, variantId);

    // 檢查是否已存在
    const existingItem = await prisma.cartItem.findFirst({
      where: {
        cartId,
        productId,
        variantId: variantId || null,
      },
    });

    if (existingItem) {
      // 更新數量
      return await prisma.cartItem.update({
        where: { id: existingItem.id },
        data: {
          quantity: existingItem.quantity + quantity,
        },
        include: {
          product: true,
          variant: true,
        },
      });
    } else {
      // 新增項目
      return await prisma.cartItem.create({
        data: {
          cartId,
          productId,
          variantId,
          quantity,
        },
        include: {
          product: true,
          variant: true,
        },
      });
    }
  }

  /**
   * 驗證庫存
   */
  private async validateStock(
    productId: string,
    quantity: number,
    variantId?: string
  ) {
    const product = await prisma.product.findUnique({
      where: { id: productId },
      include: {
        variants: variantId ? { where: { id: variantId } } : false,
      },
    });

    if (!product) {
      throw new ProductNotFoundError(productId);
    }

    const stock = variantId
      ? product.variants[0]?.stock
      : product.stock;

    if (stock < quantity) {
      throw new InsufficientStockError(
        productId,
        variantId,
        stock,
        quantity
      );
    }
  }

  // ... 其他方法
}

export const cartService = new CartService();
```

【Todo 更新】
✓ 完成: 設計 Cart 和 CartItem schema
✓ 完成: 建立 migration
✓ 完成: 執行 migration
✓ 完成: 實作 cartService ✓
🔄 進行中: 實作 API endpoints
⏳ 待處理: 實作測試
...

═══════════════════════════════════════════════════════
對話 3: API Endpoints 實作
═══════════════════════════════════════════════════════

使用者:
"實作 src/api/cart/cartController.ts 和路由設定。

參考：
- 現有的 API 模式: src/api/products/productController.ts
- Express Router 設定: src/api/index.ts

要求：
- RESTful API 設計
- 使用 async/await
- 完整的錯誤處理
- 輸入驗證（使用 express-validator）"

Claude 執行:
├─ Read src/api/products/productController.ts（學習模式）
├─ Read src/api/index.ts（了解路由結構）
├─ Write src/api/cart/cartController.ts
├─ Write src/api/cart/cartRouter.ts
├─ Edit src/api/index.ts（加入購物車路由）
└─ Write src/validators/cartValidator.ts

產出範例：

```typescript
// src/api/cart/cartController.ts
import { Request, Response, NextFunction } from 'express';
import { cartService } from '../../services/cartService';
import { ApiError } from '../../errors';

export class CartController {
  /**
   * GET /api/cart
   * 取得使用者的購物車
   */
  async getCart(req: Request, res: Response, next: NextFunction) {
    try {
      const userId = req.user?.id;
      const sessionId = req.session?.id;

      const cart = await cartService.getCart(userId, sessionId);

      res.json({
        success: true,
        data: cart,
      });
    } catch (error) {
      next(error);
    }
  }

  /**
   * POST /api/cart/items
   * 新增商品到購物車
   */
  async addItem(req: Request, res: Response, next: NextFunction) {
    try {
      const { productId, quantity, variantId } = req.body;
      const userId = req.user?.id;
      const sessionId = req.session?.id;

      // 取得或建立購物車
      const cart = await cartService.getCart(userId, sessionId);

      // 新增商品
      const item = await cartService.addItem(
        cart.id,
        productId,
        quantity,
        variantId
      );

      res.status(201).json({
        success: true,
        data: item,
      });
    } catch (error) {
      next(error);
    }
  }

  // ... 其他方法
}

export const cartController = new CartController();
```

```typescript
// src/api/cart/cartRouter.ts
import { Router } from 'express';
import { cartController } from './cartController';
import { validateAddItem } from '../../validators/cartValidator';
import { authMiddleware } from '../../middleware/auth';

const router = Router();

// 所有路由都需要認證（或 session）
router.use(authMiddleware.optionalAuth);

router.get('/', cartController.getCart);
router.post('/items', validateAddItem, cartController.addItem);
router.put('/items/:id', cartController.updateItem);
router.delete('/items/:id', cartController.removeItem);
router.delete('/', cartController.clearCart);
router.post('/merge', authMiddleware.requireAuth, cartController.mergeCarts);

export default router;
```

【Todo 更新】
✓ 完成: 實作 cartService
✓ 完成: 實作 API endpoints ✓
🔄 進行中: 撰寫測試
⏳ 待處理: 實作前端
...

═══════════════════════════════════════════════════════
對話 4: 測試撰寫
═══════════════════════════════════════════════════════

使用者:
"為 cartService 撰寫完整的單元測試。

測試框架: Jest
測試檔案: src/services/__tests__/cartService.test.ts

測試涵蓋：
- 正常流程
- 邊界情況
- 錯誤處理
- 併發情境

期望覆蓋率 > 90%"

Claude 執行:
├─ Read src/services/cartService.ts
├─ Read src/services/__tests__/userService.test.ts（參考測試模式）
└─ Write src/services/__tests__/cartService.test.ts

產出範例：

```typescript
// src/services/__tests__/cartService.test.ts
import { cartService } from '../cartService';
import { prisma } from '../../lib/prisma';
import {
  ProductNotFoundError,
  InsufficientStockError,
} from '../../errors';

// Mock Prisma
jest.mock('../../lib/prisma', () => ({
  prisma: {
    cart: {
      findFirst: jest.fn(),
      create: jest.fn(),
    },
    cartItem: {
      findFirst: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
    },
    product: {
      findUnique: jest.fn(),
    },
  },
}));

describe('CartService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getCart', () => {
    it('should return existing cart for user', async () => {
      const mockCart = {
        id: 'cart-1',
        userId: 'user-1',
        items: [],
      };

      (prisma.cart.findFirst as jest.Mock).mockResolvedValue(mockCart);

      const result = await cartService.getCart('user-1');

      expect(result).toEqual(mockCart);
      expect(prisma.cart.findFirst).toHaveBeenCalledWith({
        where: { userId: 'user-1' },
        include: expect.any(Object),
      });
    });

    it('should create new cart if not exists', async () => {
      (prisma.cart.findFirst as jest.Mock).mockResolvedValue(null);
      (prisma.cart.create as jest.Mock).mockResolvedValue({
        id: 'cart-2',
        userId: 'user-2',
        items: [],
      });

      const result = await cartService.getCart('user-2');

      expect(result.id).toBe('cart-2');
      expect(prisma.cart.create).toHaveBeenCalled();
    });

    it('should throw error if no userId or sessionId', async () => {
      await expect(cartService.getCart()).rejects.toThrow();
    });
  });

  describe('addItem', () => {
    it('should add new item to cart', async () => {
      const mockProduct = {
        id: 'product-1',
        stock: 10,
      };

      (prisma.product.findUnique as jest.Mock).mockResolvedValue(mockProduct);
      (prisma.cartItem.findFirst as jest.Mock).mockResolvedValue(null);
      (prisma.cartItem.create as jest.Mock).mockResolvedValue({
        id: 'item-1',
        productId: 'product-1',
        quantity: 2,
      });

      const result = await cartService.addItem('cart-1', 'product-1', 2);

      expect(result.quantity).toBe(2);
      expect(prisma.cartItem.create).toHaveBeenCalled();
    });

    it('should update quantity if item exists', async () => {
      const mockProduct = { id: 'product-1', stock: 10 };
      const existingItem = {
        id: 'item-1',
        quantity: 3,
      };

      (prisma.product.findUnique as jest.Mock).mockResolvedValue(mockProduct);
      (prisma.cartItem.findFirst as jest.Mock).mockResolvedValue(existingItem);
      (prisma.cartItem.update as jest.Mock).mockResolvedValue({
        ...existingItem,
        quantity: 5,
      });

      const result = await cartService.addItem('cart-1', 'product-1', 2);

      expect(result.quantity).toBe(5);
      expect(prisma.cartItem.update).toHaveBeenCalled();
    });

    it('should throw InsufficientStockError when stock is low', async () => {
      const mockProduct = {
        id: 'product-1',
        stock: 2,
      };

      (prisma.product.findUnique as jest.Mock).mockResolvedValue(mockProduct);

      await expect(
        cartService.addItem('cart-1', 'product-1', 5)
      ).rejects.toThrow(InsufficientStockError);
    });

    it('should throw ProductNotFoundError for invalid product', async () => {
      (prisma.product.findUnique as jest.Mock).mockResolvedValue(null);

      await expect(
        cartService.addItem('cart-1', 'invalid-id', 1)
      ).rejects.toThrow(ProductNotFoundError);
    });
  });

  // ... 更多測試
});
```

【Todo 更新】
✓ 完成: 實作 cartService
✓ 完成: 實作 API endpoints
✓ 完成: 撰寫 cartService 單元測試 ✓
🔄 進行中: 撰寫 API 整合測試
⏳ 待處理: 實作前端
...
```

### 前端開發流程

```typescript
═══════════════════════════════════════════════════════
對話 5: Zustand Store 實作
═══════════════════════════════════════════════════════

使用者:
"實作 src/stores/cartStore.ts，使用 Zustand 管理購物車狀態。

參考現有的 Store 模式: src/stores/authStore.ts

包含：
- 購物車狀態
- Loading 和 error 狀態
- 所有 CRUD 操作
- 樂觀更新（Optimistic Updates）"

Claude 產出:

```typescript
// src/stores/cartStore.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { cartApi } from '../api/cartApi';
import type { Cart, CartItem } from '../types/cart';

interface CartStore {
  // State
  cart: Cart | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchCart: () => Promise<void>;
  addItem: (productId: string, quantity: number, variantId?: string) => Promise<void>;
  updateQuantity: (itemId: string, quantity: number) => Promise<void>;
  removeItem: (itemId: string) => Promise<void>;
  clearCart: () => Promise<void>;
  reset: () => void;
}

export const useCartStore = create<CartStore>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        cart: null,
        isLoading: false,
        error: null,

        // Fetch cart
        fetchCart: async () => {
          set({ isLoading: true, error: null });
          try {
            const response = await cartApi.getCart();
            set({ cart: response.data, isLoading: false });
          } catch (error) {
            set({
              error: error.message,
              isLoading: false,
            });
          }
        },

        // Add item with optimistic update
        addItem: async (productId, quantity, variantId) => {
          const previousCart = get().cart;

          // Optimistic update
          set((state) => ({
            cart: state.cart
              ? {
                  ...state.cart,
                  items: [
                    ...state.cart.items,
                    {
                      id: 'temp-' + Date.now(),
                      productId,
                      quantity,
                      variantId,
                      product: null, // Will be filled by API
                    } as CartItem,
                  ],
                }
              : null,
          }));

          try {
            const response = await cartApi.addItem({
              productId,
              quantity,
              variantId,
            });

            // Update with real data
            await get().fetchCart();
          } catch (error) {
            // Rollback on error
            set({ cart: previousCart, error: error.message });
          }
        },

        // Update quantity
        updateQuantity: async (itemId, quantity) => {
          const previousCart = get().cart;

          // Optimistic update
          set((state) => ({
            cart: state.cart
              ? {
                  ...state.cart,
                  items: state.cart.items.map((item) =>
                    item.id === itemId
                      ? { ...item, quantity }
                      : item
                  ),
                }
              : null,
          }));

          try {
            await cartApi.updateItem(itemId, { quantity });
          } catch (error) {
            // Rollback on error
            set({ cart: previousCart, error: error.message });
          }
        },

        // Remove item
        removeItem: async (itemId) => {
          const previousCart = get().cart;

          // Optimistic update
          set((state) => ({
            cart: state.cart
              ? {
                  ...state.cart,
                  items: state.cart.items.filter(
                    (item) => item.id !== itemId
                  ),
                }
              : null,
          }));

          try {
            await cartApi.removeItem(itemId);
          } catch (error) {
            // Rollback on error
            set({ cart: previousCart, error: error.message });
          }
        },

        // Clear cart
        clearCart: async () => {
          const previousCart = get().cart;

          // Optimistic update
          set((state) => ({
            cart: state.cart ? { ...state.cart, items: [] } : null,
          }));

          try {
            await cartApi.clearCart();
          } catch (error) {
            // Rollback on error
            set({ cart: previousCart, error: error.message });
          }
        },

        // Reset state
        reset: () => {
          set({ cart: null, isLoading: false, error: null });
        },
      }),
      {
        name: 'cart-storage',
        partialize: (state) => ({ cart: state.cart }), // Only persist cart data
      }
    )
  )
);
```

═══════════════════════════════════════════════════════
對話 6: React 元件實作
═══════════════════════════════════════════════════════

使用者:
"實作購物車 UI 元件。

參考設計: figma.com/design/cart-ui

元件列表（按計畫）:
1. CartButton - 購物車按鈕（顯示數量）
2. CartDrawer - 購物車側邊欄
3. CartItem - 購物車項目
4. AddToCartButton - 加入購物車按鈕

使用:
- Tailwind CSS
- Radix UI (Drawer, Dialog)
- React Icons

先實作 CartButton"

Claude 執行:
├─ Read src/components/common/Button.tsx（學習元件模式）
├─ Read src/stores/cartStore.ts（理解狀態管理）
└─ Write src/components/Cart/CartButton.tsx

產出範例：

```typescript
// src/components/Cart/CartButton.tsx
import { ShoppingCart } from 'react-icons/ri';
import { useCartStore } from '../../stores/cartStore';
import { Button } from '../common/Button';

interface CartButtonProps {
  onClick: () => void;
}

export function CartButton({ onClick }: CartButtonProps) {
  const cart = useCartStore((state) => state.cart);

  // Calculate total items
  const itemCount = cart?.items.reduce(
    (sum, item) => sum + item.quantity,
    0
  ) || 0;

  return (
    <Button
      variant="ghost"
      size="md"
      onClick={onClick}
      className="relative"
      aria-label={`購物車，${itemCount} 件商品`}
    >
      <ShoppingCart className="w-6 h-6" />

      {/* Badge showing item count */}
      {itemCount > 0 && (
        <span
          className="absolute -top-1 -right-1 bg-red-500 text-white
                     text-xs font-bold rounded-full w-5 h-5
                     flex items-center justify-center"
          aria-label={`${itemCount} 件商品`}
        >
          {itemCount > 99 ? '99+' : itemCount}
        </span>
      )}
    </Button>
  );
}
```

【逐步完成所有元件...】

═══════════════════════════════════════════════════════
對話 7: 整合與測試
═══════════════════════════════════════════════════════

使用者:
"整合所有購物車元件到主應用程式，並執行測試。

步驟:
1. 在 Layout 加入 CartButton
2. 在商品頁加入 AddToCartButton
3. 實作 CartDrawer 的開啟/關閉邏輯
4. 執行所有測試
5. 手動測試完整流程"

Claude 執行:
├─ Edit src/components/Layout/Header.tsx
├─ Edit src/pages/products/[id].tsx
├─ Bash: npm test
├─ 分析測試結果
└─ 提供手動測試檢查清單

【Todo 更新】
✓ 完成: 所有後端開發
✓ 完成: 所有前端開發
✓ 完成: 整合測試
🔄 進行中: 手動測試和 bug 修復
⏳ 待處理: 部署準備
```

## 4️⃣ 測試驗證階段

### 目標：確保功能正確且穩定

**完整測試策略：**

```typescript
使用者:
"執行完整的測試流程，確保購物車功能正常運作。

【測試層級】
1. 單元測試
   - 所有 service 函式
   - 所有 React hooks
   - 工具函式

2. 整合測試
   - API endpoints
   - 資料庫操作
   - 前後端整合

3. E2E 測試
   - 使用者完整流程
   - 不同裝置和瀏覽器

4. 效能測試
   - 回應時間
   - 併發處理

請逐一執行並回報結果"

Claude 執行測試流程:

【階段 1: 單元測試】
```bash
$ npm run test:unit

執行結果:
✓ cartService.test.ts (12 tests)
✓ cartStore.test.ts (8 tests)
✓ cartUtils.test.ts (5 tests)

覆蓋率:
Statements   : 92.5% (148/160)
Branches     : 88.3% (53/60)
Functions    : 95.0% (38/40)
Lines        : 93.1% (135/145)

⚠️ 低覆蓋率區域:
- cartService.ts:156-162 (錯誤處理分支)
→ 建議: 新增錯誤情境測試
```

【階段 2: 整合測試】
```bash
$ npm run test:integration

執行結果:
✓ POST /api/cart/items (4 tests)
✓ PUT /api/cart/items/:id (3 tests)
✓ DELETE /api/cart/items/:id (2 tests)
✓ GET /api/cart (3 tests)

所有 API endpoints 測試通過
平均回應時間: 45ms (< 200ms 目標 ✓)
```

【階段 3: E2E 測試】
```bash
$ npm run test:e2e

執行結果:
✓ User can add items to cart
✓ User can update item quantity
✓ User can remove items
✓ Cart persists across page reloads
✓ Guest cart merges after login

所有使用者流程測試通過
```

【階段 4: 效能測試】
```bash
$ npm run test:performance

結果:
平均回應時間:
- GET /api/cart: 38ms ✓
- POST /api/cart/items: 52ms ✓
- PUT /api/cart/items/:id: 41ms ✓

併發測試 (100 concurrent users):
- 成功率: 100% ✓
- P95 延遲: 125ms ✓
- P99 延遲: 210ms ✓

全部通過效能目標！
```

【測試摘要】
所有測試通過 ✓
- 單元測試: 25/25
- 整合測試: 12/12
- E2E 測試: 5/5
- 效能測試: 通過

建議修復:
1. 提升錯誤處理測試覆蓋率
2. 新增更多邊界情況測試
```

## 5️⃣ 部署上線階段

### 目標：安全、順利地部署到生產環境

**部署檢查清單：**

```markdown
使用者:
"準備將購物車功能部署到生產環境。

請協助完成部署前檢查清單，並生成部署文檔。"

Claude 生成檢查清單:

# 購物車功能部署檢查清單

## 前置檢查

### 1. 程式碼品質
- [x] 所有測試通過（單元、整合、E2E）
- [x] 程式碼已經過 Code Review
- [x] ESLint/Prettier 檢查通過
- [x] 無 TypeScript 錯誤
- [x] 無安全性漏洞（npm audit）

### 2. 資料庫
- [ ] Migration 腳本已準備
- [ ] Migration 已在 staging 環境測試
- [ ] 備份計畫已就緒
- [ ] Rollback 腳本已準備

### 3. 環境變數
- [ ] 生產環境變數已設定
  - DATABASE_URL
  - REDIS_URL
  - SESSION_SECRET
- [ ] API keys 已更新為生產版本
- [ ] 環境變數已加密儲存

### 4. 依賴套件
- [ ] package.json 版本鎖定
- [ ] node_modules 大小合理
- [ ] 無未使用的依賴
- [ ] 安全性更新已套用

### 5. 效能
- [ ] 前端打包已優化（code splitting）
- [ ] 圖片已壓縮
- [ ] API 回應時間符合目標（< 200ms）
- [ ] Redis 快取策略已設定

### 6. 監控
- [ ] 錯誤追蹤已設定（Sentry）
- [ ] 效能監控已設定（New Relic）
- [ ] 日誌系統已配置
- [ ] Alert 規則已設定

### 7. 文檔
- [ ] API 文檔已更新
- [ ] 使用者指南已準備
- [ ] 開發者文檔已更新
- [ ] Changelog 已記錄

## 部署步驟

### Step 1: 資料庫 Migration
```bash
# 在生產環境執行
npm run migrate:production

# 驗證
npm run migrate:status
```

### Step 2: 部署後端
```bash
# 打包
npm run build

# 部署到伺服器
npm run deploy:api

# 健康檢查
curl https://api.example.com/health
```

### Step 3: 部署前端
```bash
# 打包
npm run build:frontend

# 部署到 CDN
npm run deploy:frontend

# 驗證
curl https://example.com
```

### Step 4: 驗證部署
- [ ] 前端頁面正常載入
- [ ] API endpoints 正常回應
- [ ] 購物車功能正常運作
- [ ] 資料庫連線正常
- [ ] Redis 快取正常

### Step 5: 監控觀察
```markdown
部署後監控 (前 24 小時):
- 每小時檢查錯誤率
- 監控 API 回應時間
- 檢查資料庫連線數
- 觀察 Redis 記憶體使用

正常指標:
- 錯誤率 < 0.1%
- API P95 延遲 < 200ms
- 資料庫連線 < 80% pool size
- Redis 記憶體使用 < 70%
```

## Rollback 計畫

### 如果發生問題:

1. **停止新流量**
   ```bash
   # 切換到舊版本
   kubectl rollout undo deployment/api-server
   ```

2. **Rollback 資料庫**
   ```bash
   # 執行 rollback migration
   npm run migrate:rollback
   ```

3. **通知團隊**
   - Slack #incidents 頻道
   - 記錄問題詳情
   - 安排事後檢討

4. **事後檢討**
   - 分析失敗原因
   - 更新部署流程
   - 加強測試覆蓋

## 成功標準

部署被視為成功當:
- [x] 所有健康檢查通過
- [x] 24 小時內無重大錯誤
- [x] 效能指標符合目標
- [x] 使用者回饋正面
- [x] 無需 Rollback
```

## 6️⃣ 維護優化階段

### 目標：持續改進和維護功能

**常見維護情境：**

### 情境 1: Bug 修復

```typescript
使用者:
"生產環境回報：當購物車中有 50+ 商品時，
載入速度很慢（> 5 秒）。

錯誤追蹤 (Sentry):
- URL: /api/cart
- 回應時間: 5.2s (P95: 6.8s)
- 使用者影響: 約 2% 使用者

請協助診斷並修復"

Claude 診斷流程:

【步驟 1: 重現問題】
"根據錯誤報告，讓我們先在開發環境重現問題。

我需要：
1. 建立測試用購物車（50+ 商品）
2. 測量 API 回應時間
3. 分析效能瓶頸"

【步驟 2: 分析問題】
使用 Bash tool 執行分析:
```bash
# 使用效能分析工具
npm run profile:api -- GET /api/cart

結果分析:
┌─────────────────────────┬──────────┐
│ 操作                    │ 時間     │
├─────────────────────────┼──────────┤
│ Prisma 查詢             │ 4.8s     │ ← 瓶頸！
│ 資料序列化              │ 0.3s     │
│ 網路傳輸                │ 0.1s     │
└─────────────────────────┴──────────┘

【診斷】
問題出在 Prisma 查詢，沒有使用 select 限制欄位，
抓取了所有關聯資料（包含不需要的 product descriptions,
reviews 等大量資料）
```

【步驟 3: 實作修復】
```typescript
// 修復前（慢）
const cart = await prisma.cart.findFirst({
  where: { userId },
  include: {
    items: {
      include: {
        product: true, // 抓取所有 product 欄位
        variant: true, // 抓取所有 variant 欄位
      },
    },
  },
});

// 修復後（快）
const cart = await prisma.cart.findFirst({
  where: { userId },
  include: {
    items: {
      include: {
        product: {
          select: {
            id: true,
            name: true,
            price: true,
            imageUrl: true,
            // 只選擇需要的欄位
          },
        },
        variant: {
          select: {
            id: true,
            name: true,
            price: true,
          },
        },
      },
    },
  },
});
```

【步驟 4: 測試驗證】
```bash
# 測試修復後的效能
npm run profile:api -- GET /api/cart

新的結果:
┌─────────────────────────┬──────────┐
│ 操作                    │ 時間     │
├─────────────────────────┼──────────┤
│ Prisma 查詢             │ 0.15s    │ ✓ 改善 97%！
│ 資料序列化              │ 0.08s    │
│ 網路傳輸                │ 0.05s    │
│ 總計                    │ 0.28s    │ ✓ 符合目標！
└─────────────────────────┴──────────┘
```

【步驟 5: 部署修復】
```bash
# 建立 hotfix branch
/commit -m "perf(cart): optimize cart query by selecting only required fields

- Reduce query time from 4.8s to 0.15s (97% improvement)
- Select only necessary product and variant fields
- Fixes slow cart loading for users with 50+ items

Closes #BUG-123"

# 部署到生產環境
npm run deploy:hotfix
```

### 情境 2: 效能優化

```typescript
使用者:
"想優化購物車的整體效能。請分析目前的效能瓶頸，
並提供優化建議"

Claude 分析流程:

【階段 1: 效能基準測試】
執行完整的效能分析:
```bash
npm run test:performance -- --detailed

結果報告:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
購物車效能分析報告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API 回應時間:
├─ GET /api/cart
│  ├─ P50: 145ms
│  ├─ P95: 320ms ⚠️ 超過目標 (200ms)
│  └─ P99: 580ms ⚠️
│
├─ POST /api/cart/items
│  ├─ P50: 180ms
│  ├─ P95: 380ms ⚠️
│  └─ P99: 650ms ⚠️

前端載入時間:
├─ 初次載入: 2.8s ⚠️
├─ React 渲染: 850ms ⚠️
└─ API 呼叫: 320ms

識別的瓶頸:
1. 資料庫查詢未使用索引
2. 無 Redis 快取
3. 前端過度渲染
4. API 回應未壓縮
```

【階段 2: 優化建議】
Claude 提供完整優化計畫:

```markdown
# 購物車效能優化計畫

## 優化 1: 資料庫索引 (預期改善 40%)

### 分析
目前 cart_items 表沒有在 cart_id 上建立索引，
查詢 50+ 商品時需要全表掃描

### 實作
```sql
CREATE INDEX idx_cart_items_cart_id ON cart_items(cart_id);
CREATE INDEX idx_carts_user_id ON carts(user_id);
CREATE INDEX idx_carts_session_id ON carts(session_id);
```

### 預期結果
- 查詢時間: 150ms → 90ms
- P95 延遲: 320ms → 200ms ✓

## 優化 2: Redis 快取 (預期改善 60%)

### 策略
```typescript
// 快取策略
const CART_CACHE_TTL = 3600; // 1 hour

async function getCachedCart(userId: string) {
  // 1. 嘗試從 Redis 讀取
  const cached = await redis.get(`cart:${userId}`);
  if (cached) {
    return JSON.parse(cached);
  }

  // 2. 從資料庫查詢
  const cart = await prisma.cart.findFirst({
    where: { userId },
    include: { items: { include: { product: true } } },
  });

  // 3. 寫入 Redis
  await redis.setex(
    `cart:${userId}`,
    CART_CACHE_TTL,
    JSON.stringify(cart)
  );

  return cart;
}
```

### 預期結果
- 快取命中時: 90ms → 10ms
- P95 延遲: 200ms → 50ms ✓

## 優化 3: 前端優化 (預期改善 50%)

### React.memo 和 useMemo
```typescript
// 優化前
function CartItem({ item }) {
  const formattedPrice = formatPrice(item.price); // 每次都重新計算
  return <div>{formattedPrice}</div>;
}

// 優化後
const CartItem = React.memo(({ item }) => {
  const formattedPrice = useMemo(
    () => formatPrice(item.price),
    [item.price]
  );
  return <div>{formattedPrice}</div>;
});
```

### 虛擬捲動（50+ 商品時）
```typescript
import { FixedSizeList } from 'react-window';

function CartDrawer({ items }) {
  if (items.length > 20) {
    return (
      <FixedSizeList
        height={600}
        itemCount={items.length}
        itemSize={80}
      >
        {({ index, style }) => (
          <CartItem style={style} item={items[index]} />
        )}
      </FixedSizeList>
    );
  }

  return items.map(item => <CartItem key={item.id} item={item} />);
}
```

### 預期結果
- 渲染時間: 850ms → 250ms
- 捲動 FPS: 30fps → 60fps ✓

## 優化 4: API 回應壓縮 (預期改善 70% 傳輸)

```typescript
import compression from 'compression';

app.use(compression({
  level: 6,
  threshold: 1024, // 只壓縮 > 1KB 的回應
}));
```

### 預期結果
- 回應大小: 150KB → 45KB
- 傳輸時間: 200ms → 60ms (on 3G)

## 總體預期改善

| 指標 | 優化前 | 優化後 | 改善幅度 |
|------|--------|--------|---------|
| API P95 延遲 | 320ms | 50ms | 84% ↓ |
| 前端載入時間 | 2.8s | 1.2s | 57% ↓ |
| 資料傳輸量 | 150KB | 45KB | 70% ↓ |

## 實作順序

1. 資料庫索引（最快，影響最大）
2. Redis 快取（中等工作量，效果顯著）
3. API 壓縮（簡單，立即生效）
4. 前端優化（需要較多測試）

總時程估算: 2-3 天
```

## 📋 工作流程最佳實踐總結

### 黃金原則

```markdown
1. **先規劃，再實作**
   • 使用 Plan Mode 設計架構
   • 明確定義驗收標準
   • 分階段執行

2. **持續測試和驗證**
   • 每個階段都要測試
   • 不要累積技術債
   • 自動化測試流程

3. **文檔與程式碼同步更新**
   • README 保持最新
   • API 文檔即時更新
   • 記錄重要決策

4. **監控和回饋循環**
   • 部署後密切監控
   • 收集使用者回饋
   • 持續優化改進

5. **團隊協作**
   • Code Review 機制
   • 知識分享
   • 統一的工作流程
```

### 檢查清單範本

```markdown
每個功能開發的標準流程：

需求分析階段
☐ 功能需求明確
☐ 技術需求確定
☐ 限制條件已識別
☐ 驗收標準可測試

設計規劃階段
☐ 架構設計完成
☐ 資料庫設計確認
☐ API 設計審查
☐ 任務分解清晰

開發實作階段
☐ 程式碼符合規範
☐ 單元測試覆蓋
☐ Code Review 通過
☐ 文檔已更新

測試驗證階段
☐ 單元測試通過
☐ 整合測試通過
☐ E2E 測試通過
☐ 效能測試達標

部署上線階段
☐ 部署檢查清單完成
☐ Rollback 計畫就緒
☐ 監控已設定
☐ 團隊已通知

維護優化階段
☐ 監控指標正常
☐ 問題及時修復
☐ 效能持續優化
☐ 使用者回饋收集
```

## 🚀 下一步行動

```markdown
立即行動
☐ 為目前專案建立工作流程文檔
☐ 設定 Claude Code 的專案模板
☐ 建立常用的檢查清單
☐ 與團隊分享工作流程

持續改進
☐ 定期回顧工作流程效率
☐ 收集團隊回饋並調整
☐ 記錄最佳實踐案例
☐ 建立內部知識庫
```

---

**延伸閱讀：**
- [Claude Code 最佳實踐指南](/claude-code-best-practices-zh)
- [深入理解 Claude Code Context Window](/claude-code-context-window-deep-dive-zh)

**標籤**: #claude-code #工作流程 #開發流程 #軟體開發 #最佳實踐 #敏捷開發
