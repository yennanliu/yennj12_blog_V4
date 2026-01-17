---
title: "Claude Code 最佳實踐指南：提升 AI 輔助開發效率的 20 個技巧"
date: 2026-01-17T12:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "development-tools"]
tags: ["AI", "claude-code", "最佳實踐", "開發效率", "提示工程", "工作流程", "生產力"]
summary: "完整的 Claude Code 最佳實踐指南：從基礎使用到進階技巧，涵蓋提示工程、檔案管理、錯誤處理與團隊協作，幫助開發者充分發揮 AI 輔助開發的潛力。"
readTime: "18 min"
---

Claude Code 作為 Anthropic 官方推出的 AI 驅動開發工具，正在改變軟體開發的工作方式。然而，要充分發揮其潛力，需要掌握正確的使用方法和最佳實踐。本文彙整了 20 個實用技巧，幫助開發者更有效地使用 Claude Code。

## 🎯 為什麼需要最佳實踐？

在深入技巧之前，先理解為什麼最佳實踐如此重要：

```
❌ 常見錯誤使用方式：
使用者: "幫我修這個 bug"
Claude: [不知道要看哪個檔案]
使用者: "檢查 app.js"
Claude: [讀取後發現需要其他檔案]
使用者: "還需要 utils.js"
...反覆來回多次...

✅ 最佳實踐方式：
使用者: "在 src/app.js 的第 45 行有個錯誤，當使用者
      登入時會拋出 'undefined is not a function'。
      可能與 src/utils/auth.js 的 validateToken
      函式有關。請幫我診斷並修復。"
Claude: [一次性理解問題背景，高效解決]
```

**效率差異：**
- 錯誤方式：5-10 次對話來回，耗時 10-15 分鐘
- 最佳實踐：1-2 次對話，耗時 2-3 分鐘
- **效率提升：5 倍以上**

## 📋 最佳實踐總覽

本文將最佳實踐分為五大類別：

```
┌─────────────────────────────────────────────────────┐
│           Claude Code 最佳實踐架構                  │
│                                                     │
│  ┌────────────────┐      ┌────────────────┐       │
│  │  溝通技巧      │      │  專案管理      │       │
│  │                │      │                │       │
│  │ • 清晰指令     │      │ • 檔案組織     │       │
│  │ • 提供背景     │      │ • 版本控制     │       │
│  │ • 分步驟       │      │ • 文檔維護     │       │
│  └────────────────┘      └────────────────┘       │
│                                                     │
│  ┌────────────────┐      ┌────────────────┐       │
│  │  效率優化      │      │  品質保證      │       │
│  │                │      │                │       │
│  │ • Context 管理 │      │ • 程式碼審查   │       │
│  │ • 工具使用     │      │ • 測試策略     │       │
│  │ • 批次處理     │      │ • 安全檢查     │       │
│  └────────────────┘      └────────────────┘       │
│                                                     │
│  ┌────────────────┐                                │
│  │  團隊協作      │                                │
│  │                │                                │
│  │ • 共享規範     │                                │
│  │ • 知識傳承     │                                │
│  │ • 工作流程     │                                │
│  └────────────────┘                                │
└─────────────────────────────────────────────────────┘
```

## 🗣️ 類別一：有效溝通技巧

### 1. 提供清晰、具體的指令

**❌ 不好的做法：**
```
"幫我優化這個函式"
"這裡有個 bug"
"讓這個程式更快"
```

**✅ 好的做法：**
```
"優化 src/utils/dataProcessor.js:processLargeDataset()
函式的效能。目前處理 10,000 筆資料需要 5 秒，目標
是降到 1 秒以內。可能的優化方向：
1. 使用 Map 取代陣列查找
2. 實作批次處理
3. 考慮使用 Web Workers"
```

**範例對比：**

```typescript
// ❌ 模糊指令
"改善這個 API"

// ✅ 具體指令
"重構 src/api/userService.ts 的 fetchUserData() 方法：
1. 加入請求快取機制（5 分鐘過期）
2. 實作錯誤重試邏輯（最多 3 次，指數退避）
3. 加入 TypeScript 型別定義
4. 新增單元測試
5. 使用現有的 axios 實例（src/config/axios.ts）"
```

### 2. 提供充足的背景資訊

**背景資訊檢查清單：**

```markdown
在請求協助前，確認是否提供：

✓ 專案背景
  - 專案類型（React SPA、Node.js API、Python CLI 等）
  - 技術棧（使用的框架、函式庫）
  - 開發環境（Node 版本、套件管理工具）

✓ 問題背景
  - 預期行為 vs 實際行為
  - 重現步驟
  - 錯誤訊息（完整的 stack trace）
  - 相關檔案路徑

✓ 限制條件
  - 必須使用的技術或方法
  - 不能修改的部分
  - 效能或安全性要求
  - 相容性需求
```

**實際範例：**

```
// ❌ 缺乏背景
"使用者無法登入"

// ✅ 完整背景
"在生產環境中，使用者嘗試用 Google OAuth 登入時失敗。

【環境資訊】
- Next.js 14.0 with App Router
- next-auth 5.0.0
- 部署在 Vercel

【錯誤訊息】
OAuthAccountNotLinked: Another account already exists with
the same email address

【重現步驟】
1. 使用者先用 email/password 註冊（user@example.com）
2. 登出
3. 嘗試用 Google 帳號登入（同樣的 email）
4. 出現上述錯誤

【相關檔案】
- src/app/api/auth/[...nextauth]/route.ts
- src/lib/auth.ts
- prisma/schema.prisma

【預期行為】
應該自動連結現有帳號，或顯示友善的錯誤訊息"
```

### 3. 將複雜任務分解為小步驟

**為什麼要分步驟？**

```
大任務（一次完成）：
┌────────────────────────────────────┐
│ 建立完整的電商網站                  │
│ • 前端 UI                           │
│ • 後端 API                          │
│ • 資料庫設計                        │
│ • 使用者認證                        │
│ • 支付整合                          │
│ • Email 通知                        │
└────────────────────────────────────┘
         ↓
    ❌ 問題：
    • 難以追蹤進度
    • 錯誤難以定位
    • 無法逐步驗證
    • 容易超出 context

小步驟（逐步完成）：
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Step 1   │ → │ Step 2   │ → │ Step 3   │
│ 資料庫   │   │ API 基礎 │   │ 使用者   │
│ Schema   │   │ 架構     │   │ CRUD     │
└──────────┘   └──────────┘   └──────────┘
         ↓            ↓            ↓
    ✅ 優點：
    • 逐步驗證功能
    • 問題容易定位
    • 可隨時調整方向
    • Context 保持清晰
```

**實際步驟規劃範例：**

```markdown
任務：實作使用者認證系統

【Step 1: 資料庫設計】（15 分鐘）
- 設計 User schema（Prisma）
- 包含必要欄位：email, password hash, roles
- 建立 migration

【Step 2: 註冊功能】（20 分鐘）
- POST /api/auth/register endpoint
- Email 驗證
- 密碼雜湊（bcrypt）
- 寫入資料庫
- 單元測試

【Step 3: 登入功能】（20 分鐘）
- POST /api/auth/login endpoint
- 驗證憑證
- 產生 JWT token
- 單元測試

【Step 4: JWT 中介層】（15 分鐘）
- 建立 authenticateToken middleware
- 驗證 token 有效性
- 將 user 資訊附加到 request

【Step 5: 保護路由】（10 分鐘）
- 套用 middleware 到需要認證的路由
- 測試保護機制

【Step 6: 前端整合】（30 分鐘）
- 登入/註冊表單
- Token 儲存（localStorage）
- API 呼叫攔截器
- 錯誤處理

每個步驟完成後都要測試驗證！
```

### 4. 使用範例和參考資料

**提供範例的好處：**

```typescript
// ❌ 只描述需求
"建立一個 API endpoint 來取得使用者資料"

// ✅ 提供參考範例
"建立一個類似現有 getProducts 的 API endpoint 來取得
使用者資料。參考 src/api/products.ts:

現有範例：
export async function getProducts(req: Request, res: Response) {
  try {
    const products = await db.product.findMany({
      where: { active: true },
      include: { category: true }
    });
    return res.json({ data: products });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}

請建立類似的 getUsers endpoint，但需要：
1. 只返回 active users
2. Include user's roles 和 profile
3. 支援 pagination（page, limit 參數）
4. 加入 search 功能（by email or name）"
```

### 5. 明確指出不要改動的部分

**範例：**

```typescript
// ✅ 明確標示不可修改的部分
"重構 src/services/paymentService.ts，改善錯誤處理。

⚠️ 不要修改：
- processPayment() 的函式簽名
- PAYMENT_GATEWAY_URL 常數
- 現有的 webhook 處理邏輯

✅ 可以修改：
- 錯誤處理方式
- 重試邏輯
- 日誌記錄
- 型別定義"
```

## 📁 類別二：專案與檔案管理

### 6. 維護清晰的檔案結構

**良好的專案結構：**

```
src/
├── components/          # UI 元件
│   ├── common/         # 共用元件
│   ├── features/       # 功能特定元件
│   └── layouts/        # 版面配置
├── services/           # API 服務層
│   ├── api/           # API 呼叫
│   └── business/      # 業務邏輯
├── utils/             # 工具函式
│   ├── validation/    # 驗證函式
│   └── formatting/    # 格式化函式
├── types/             # TypeScript 型別定義
├── hooks/             # React Hooks
├── contexts/          # React Contexts
└── config/            # 設定檔

【原則】
✓ 按功能分組，而非檔案類型
✓ 每個資料夾有明確的職責
✓ 避免巢狀超過 3 層
✓ 相關檔案放在一起
```

### 7. 使用描述性的檔案和函式命名

**命名對比：**

```typescript
// ❌ 不好的命名
data.ts
utils.ts
helper.ts
function doStuff() {}
function handle() {}

// ✅ 好的命名
userDataTransformer.ts
dateFormatUtils.ts
authenticationHelper.ts
function transformUserDataForDisplay() {}
function handleUserLoginSuccess() {}
```

**命名規範範例：**

```typescript
// 檔案命名
userAuthenticationService.ts    // 服務類別
formatUserName.ts              // 工具函式
UserProfileCard.tsx            // React 元件
useUserData.ts                 // Custom Hook
UserContext.tsx                // React Context

// 函式命名（動詞開頭）
function fetchUserData() {}         // 取得資料
function validateEmail() {}         // 驗證
function transformToDTO() {}        // 轉換
function calculateTotalPrice() {}   // 計算
function isUserAuthenticated() {}   // 布林判斷

// 變數命名（名詞）
const userData = ...
const isLoading = ...
const hasError = ...
const userCount = ...
```

### 8. 適時使用 .claudeignore

**範例 .claudeignore 檔案：**

```bash
# .claudeignore

# 依賴套件
node_modules/
.pnp/
.pnp.js

# 建置產物
dist/
build/
.next/
out/

# 快取
.cache/
.parcel-cache/
.eslintcache

# 環境變數（敏感資訊）
.env
.env.local
.env.*.local

# 日誌
*.log
npm-debug.log*

# IDE 設定
.vscode/
.idea/
*.swp
*.swo

# 測試覆蓋率報告
coverage/
.nyc_output/

# 大型資料檔案
*.csv
*.json.large
data/raw/

# 圖片和媒體（通常不需要 Claude 讀取）
*.png
*.jpg
*.jpeg
*.gif
*.mp4
*.pdf

# 編譯後的檔案
*.min.js
*.bundle.js
```

**何時使用 .claudeignore：**

```
✅ 應該忽略：
- 第三方套件（node_modules）
- 編譯產物（dist, build）
- 大型資料檔案
- 二進位檔案
- 機密資訊（.env）

❌ 不應該忽略：
- 原始碼檔案
- 設定檔（tsconfig.json, package.json）
- 測試檔案
- 文檔檔案
```

### 9. 保持程式碼庫的文檔更新

**必要的文檔類型：**

```markdown
專案根目錄/
├── README.md              # 專案概述、快速開始
├── CONTRIBUTING.md        # 貢獻指南
├── ARCHITECTURE.md        # 架構說明
└── docs/
    ├── API.md            # API 文檔
    ├── DEPLOYMENT.md     # 部署指南
    └── DEVELOPMENT.md    # 開發指南
```

**README.md 範本：**

```markdown
# 專案名稱

簡短的專案描述（1-2 句話）

## 🚀 快速開始

\`\`\`bash
# 安裝依賴
npm install

# 啟動開發伺服器
npm run dev

# 執行測試
npm test
\`\`\`

## 📁 專案結構

\`\`\`
src/
├── components/    # React 元件
├── services/      # API 服務
└── utils/         # 工具函式
\`\`\`

## 🔧 技術棧

- **前端**: React 18 + TypeScript
- **狀態管理**: Zustand
- **樣式**: Tailwind CSS
- **API**: REST + Axios

## 📝 主要功能

1. 使用者認證（JWT）
2. 資料視覺化（Chart.js）
3. 即時通知（WebSocket）

## 🤝 貢獻指南

請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 授權

MIT License
```

### 10. 定期進行程式碼審查（Code Review）

**使用 Claude Code 進行 Code Review：**

```bash
# 使用 /review-pr 技能
/review-pr 123

# 或明確指示審查重點
"審查 Pull Request #123，重點檢查：
1. 安全性漏洞（SQL injection, XSS）
2. 效能問題（N+1 queries, 記憶體洩漏）
3. 程式碼品質（複雜度、可讀性）
4. 測試覆蓋率
5. 文檔完整性"
```

**自動化 Code Review 檢查清單：**

```typescript
// 建立 .github/PULL_REQUEST_TEMPLATE.md

## 變更描述
<!-- 描述這次 PR 的變更內容 -->

## 變更類型
- [ ] Bug 修復
- [ ] 新功能
- [ ] 重構
- [ ] 文檔更新
- [ ] 效能優化

## 檢查清單
- [ ] 程式碼遵循專案風格指南
- [ ] 已新增/更新相關測試
- [ ] 所有測試通過
- [ ] 已更新文檔
- [ ] 無安全性疑慮
- [ ] 已執行 ESLint/Prettier
- [ ] PR 標題清楚描述變更
```

## ⚡ 類別三：效率優化技巧

### 11. 善用 Claude Code 的內建工具

**常用工具與使用時機：**

```typescript
// 1. Read Tool - 讀取檔案
"讀取 src/components/UserProfile.tsx 檢查錯誤"

// 2. Edit Tool - 精確編輯
"在 src/utils/format.ts:23 將 formatDate 改為使用
date-fns 而非 moment.js"

// 3. Write Tool - 建立新檔案
"建立 src/hooks/useAuth.ts，實作自訂的認證 Hook"

// 4. Bash Tool - 執行命令
"執行 npm test 檢查測試結果"

// 5. Grep Tool - 搜尋程式碼
"在整個專案中搜尋所有使用 'localStorage' 的地方"

// 6. Glob Tool - 尋找檔案
"找出所有 .test.ts 檔案"
```

**工具使用最佳實踐：**

```
✅ 有效使用：
"使用 Grep 找出所有包含 'TODO' 的檔案，然後逐一處理"
"用 Glob 列出所有 React 元件，檢查哪些缺少 PropTypes"

❌ 無效使用：
"搜尋整個專案" （太模糊）
"看看有什麼檔案" （無明確目標）
```

### 12. 批次處理相似任務

**範例：批次重構**

```typescript
// ❌ 逐一處理
"重構 UserCard.tsx"
"重構 ProductCard.tsx"
"重構 OrderCard.tsx"
...

// ✅ 批次處理
"批次重構所有 Card 元件（UserCard, ProductCard,
OrderCard, CommentCard），統一：
1. 將 class components 改為 functional components
2. 使用 TypeScript interface 定義 props
3. 套用統一的樣式結構
4. 加入 data-testid 屬性

請使用 Glob 找出所有 *Card.tsx 檔案並逐一處理"
```

**批次任務規劃：**

```markdown
【批次任務範本】

任務：將所有 API 呼叫從 fetch 遷移到 axios

Step 1: 掃描識別
- 使用 Grep 找出所有包含 'fetch(' 的檔案
- 列出受影響的檔案清單

Step 2: 建立遷移計畫
- 為每個檔案規劃變更內容
- 識別共通模式

Step 3: 批次執行
- 按優先順序逐一遷移
- 每個檔案遷移後執行測試

Step 4: 驗證
- 執行完整測試套件
- 手動測試關鍵功能
```

### 13. 利用 Skills 簡化重複工作

**建立自訂 Skill 範例：**

```typescript
// 範例：建立元件的 Skill

// ~/.config/claude-code/skills/create-component.ts
export const createComponentSkill: Skill = {
  name: 'create-react-component',
  description: '建立標準的 React 元件（含測試和故事書）',

  arguments: {
    componentName: {
      type: 'string',
      required: true,
      description: '元件名稱（PascalCase）'
    },
    hasState: {
      type: 'boolean',
      default: false,
      description: '是否需要狀態管理'
    }
  },

  async execute(args, context) {
    const { componentName, hasState } = args;

    // 1. 建立元件檔案
    await context.write(
      `src/components/${componentName}/${componentName}.tsx`,
      generateComponentCode(componentName, hasState)
    );

    // 2. 建立測試檔案
    await context.write(
      `src/components/${componentName}/${componentName}.test.tsx`,
      generateTestCode(componentName)
    );

    // 3. 建立 Storybook 故事
    await context.write(
      `src/components/${componentName}/${componentName}.stories.tsx`,
      generateStoryCode(componentName)
    );

    // 4. 建立 index.ts
    await context.write(
      `src/components/${componentName}/index.ts`,
      `export { ${componentName} } from './${componentName}';\n`
    );

    return {
      success: true,
      message: `✅ 元件 ${componentName} 建立完成！`
    };
  }
};
```

**使用 Skill：**

```bash
# 使用自訂 Skill
/create-react-component UserAvatar --hasState=true

# 結果：自動產生
# - UserAvatar.tsx
# - UserAvatar.test.tsx
# - UserAvatar.stories.tsx
# - index.ts
```

### 14. 設定合適的編輯器整合

**VS Code 設定範例：**

```json
// .vscode/settings.json
{
  // Claude Code 相關設定
  "claude.autoSave": true,
  "claude.contextFiles": [
    "package.json",
    "tsconfig.json",
    ".env.example"
  ],

  // 編輯器設定
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  },

  // TypeScript 設定
  "typescript.tsdk": "node_modules/typescript/lib",
  "typescript.enablePromptUseWorkspaceTsdk": true,

  // 檔案排除（與 .claueignore 同步）
  "files.exclude": {
    "**/node_modules": true,
    "**/dist": true,
    "**/.next": true
  }
}
```

**推薦的 VS Code 擴充套件：**

```json
{
  "recommendations": [
    "anthropics.claude-code",        // Claude Code 官方擴充
    "dbaeumer.vscode-eslint",        // ESLint
    "esbenp.prettier-vscode",        // Prettier
    "ms-vscode.vscode-typescript-next", // TypeScript
    "bradlc.vscode-tailwindcss",     // Tailwind CSS
    "formulahendry.auto-rename-tag", // HTML 標籤重命名
    "streetsidesoftware.code-spell-checker" // 拼字檢查
  ]
}
```

### 15. 使用 Todo List 追蹤進度

**何時使用 TodoWrite 工具：**

```typescript
// ✅ 應該使用 Todo List 的情況：

// 1. 複雜的多步驟任務
"實作使用者認證系統（包含註冊、登入、JWT、密碼重設）"

// 2. 需要追蹤進度的功能開發
"建立電商購物車功能"

// 3. 有多個子任務的重構工作
"重構整個資料層以使用 TypeScript"

// ❌ 不需要 Todo List 的情況：

// 1. 簡單的單一修改
"修正 Button 元件的樣式"

// 2. 快速的 bug 修復
"修正拼字錯誤"

// 3. 簡單的查詢或問答
"解釋這個函式的作用"
```

**Todo List 使用範例：**

```typescript
// Claude 會自動建立並管理 Todo List

任務：實作使用者認證系統

✓ 完成：設計 User schema（Prisma）
✓ 完成：實作註冊 API endpoint
🔄 進行中：實作登入功能
⏳ 待處理：建立 JWT middleware
⏳ 待處理：保護需要認證的路由
⏳ 待處理：前端整合（登入表單）
⏳ 待處理：撰寫整合測試

【優點】
• 清楚追蹤進度
• 隨時了解剩餘工作
• 容易從中斷處繼續
• 可以隨時調整優先順序
```

## 🎯 類別四：品質保證

### 16. 要求測試覆蓋

**測試策略：**

```typescript
// 明確要求測試類型

"實作 calculateShippingCost() 函式，並包含以下測試：

【單元測試】（calculateShippingCost.test.ts）
- 基本運費計算
- 重量超過限制的情況
- 偏遠地區加價
- 無效輸入的錯誤處理
- 邊界值測試（0, 負數, 極大值）

【整合測試】（shippingService.integration.test.ts）
- 與實際 API 的整合
- 資料庫查詢
- 快取機制

【期望覆蓋率】
- 語句覆蓋率 > 90%
- 分支覆蓋率 > 85%
- 函式覆蓋率 = 100%"
```

**測試驅動開發（TDD）流程：**

```
1. 先寫測試
   "為 UserService.createUser() 撰寫測試，包含：
   - 成功建立使用者
   - Email 已存在的錯誤
   - 無效 Email 格式
   - 密碼強度不足"

2. 實作功能
   "根據上述測試實作 UserService.createUser()"

3. 重構優化
   "重構 createUser() 以提升可讀性，保持測試通過"
```

### 17. 進行安全性檢查

**安全檢查清單：**

```typescript
"審查 src/api/userController.ts 的安全性，檢查：

【注入攻擊】
✓ SQL Injection 防護
✓ NoSQL Injection 防護
✓ Command Injection 防護

【XSS 防護】
✓ 輸入驗證
✓ 輸出編碼
✓ Content Security Policy

【認證與授權】
✓ 密碼雜湊（bcrypt, 不是 MD5）
✓ JWT token 驗證
✓ 角色權限檢查
✓ Rate limiting

【敏感資訊】
✓ 無密碼或 API key 寫在程式碼中
✓ 錯誤訊息不洩漏內部資訊
✓ 日誌不記錄敏感資料

【依賴套件】
✓ 無已知漏洞的套件
✓ 套件版本為最新穩定版"
```

**常見安全漏洞範例：**

```typescript
// ❌ 不安全的程式碼
app.get('/user/:id', (req, res) => {
  const query = `SELECT * FROM users WHERE id = ${req.params.id}`;
  db.query(query); // SQL Injection 風險
});

// ✅ 安全的程式碼
app.get('/user/:id', async (req, res) => {
  const userId = parseInt(req.params.id);
  if (isNaN(userId)) {
    return res.status(400).json({ error: 'Invalid user ID' });
  }

  const user = await db.query(
    'SELECT * FROM users WHERE id = ?',
    [userId]
  );
});

// 請 Claude Code 檢查
"審查上述程式碼的安全性，並提供改善建議"
```

### 18. 要求性能優化說明

**效能分析要求：**

```typescript
"分析 src/components/DataTable.tsx 的效能問題：

【目前狀況】
- 渲染 1000 筆資料需要 3 秒
- 捲動時有明顯卡頓
- 每次篩選都重新渲染整個表格

【請執行】
1. 使用 React DevTools Profiler 識別瓶頸
2. 列出效能問題清單
3. 提供優化方案（含預期改善幅度）
4. 實作最有效的 3 個優化
5. 測試優化後的效能

【優化技術參考】
- React.memo()
- useMemo() / useCallback()
- 虛擬捲動（react-window）
- 分頁或無限捲動
- Web Workers"
```

**效能優化對比：**

```typescript
// ❌ 效能不佳
function DataTable({ data }) {
  return (
    <table>
      {data.map(item => (
        <Row
          key={item.id}
          data={item}
          onEdit={() => handleEdit(item)}  // 每次都建立新函式
        />
      ))}
    </table>
  );
}

// ✅ 效能優化
import { memo, useMemo, useCallback } from 'react';
import { FixedSizeList } from 'react-window';

const Row = memo(({ data, onEdit }) => {
  return <tr>{/* ... */}</tr>;
});

function DataTable({ data }) {
  const handleEdit = useCallback((item) => {
    // 處理編輯
  }, []);

  const sortedData = useMemo(() => {
    return data.sort((a, b) => a.id - b.id);
  }, [data]);

  return (
    <FixedSizeList
      height={600}
      itemCount={sortedData.length}
      itemSize={50}
    >
      {({ index, style }) => (
        <Row
          style={style}
          data={sortedData[index]}
          onEdit={handleEdit}
        />
      )}
    </FixedSizeList>
  );
}
```

### 19. 驗證邊界情況和錯誤處理

**完整的錯誤處理範例：**

```typescript
"實作 processPayment() 函式，包含完整的錯誤處理：

【輸入驗證】
- 金額必須 > 0
- 信用卡號碼格式檢查
- CVV 長度檢查
- 過期日期驗證

【錯誤情境處理】
- 網路逾時（30 秒）
- API 回傳 4xx 錯誤
- API 回傳 5xx 錯誤
- 餘額不足
- 信用卡過期
- 信用卡被拒

【重試策略】
- 網路錯誤：重試 3 次，指數退避
- 5xx 錯誤：重試 2 次
- 4xx 錯誤：不重試，直接返回錯誤

【日誌記錄】
- 成功交易：記錄金額、時間
- 失敗交易：記錄錯誤原因、重試次數
- 敏感資訊：遮罩信用卡號（只顯示後 4 碼）"
```

**邊界測試範例：**

```typescript
// 測試邊界情況
describe('calculateDiscount', () => {
  it('handles zero amount', () => {
    expect(calculateDiscount(0, 0.1)).toBe(0);
  });

  it('handles negative amount', () => {
    expect(() => calculateDiscount(-100, 0.1))
      .toThrow('Amount must be positive');
  });

  it('handles 100% discount', () => {
    expect(calculateDiscount(100, 1)).toBe(0);
  });

  it('handles discount > 100%', () => {
    expect(() => calculateDiscount(100, 1.5))
      .toThrow('Discount cannot exceed 100%');
  });

  it('handles very large amounts', () => {
    expect(calculateDiscount(Number.MAX_SAFE_INTEGER, 0.1))
      .toBeLessThan(Number.MAX_SAFE_INTEGER);
  });

  it('handles floating point precision', () => {
    expect(calculateDiscount(0.1 + 0.2, 0.1))
      .toBeCloseTo(0.27, 2);
  });
});
```

### 20. 要求程式碼文檔

**文檔要求範例：**

```typescript
"為 src/services/emailService.ts 新增完整的 JSDoc 文檔：

【要求】
- 每個 public 函式都要有 JSDoc
- 描述函式用途、參數、返回值
- 包含使用範例
- 說明可能拋出的錯誤
- 標註 @since 版本資訊"
```

**良好的文檔範例：**

```typescript
/**
 * 發送歡迎郵件給新註冊的使用者
 *
 * 此函式會根據使用者的語言偏好發送對應語言的歡迎郵件。
 * 郵件包含帳號啟用連結，有效期限為 24 小時。
 *
 * @param {string} email - 使用者的電子郵件地址
 * @param {string} username - 使用者名稱
 * @param {string} [locale='en'] - 語言代碼（en, zh-TW, ja 等）
 * @returns {Promise<EmailResult>} 郵件發送結果
 *
 * @throws {InvalidEmailError} 當 email 格式無效時
 * @throws {EmailServiceError} 當郵件服務發生錯誤時
 *
 * @example
 * // 發送英文歡迎郵件
 * await sendWelcomeEmail('user@example.com', 'John');
 *
 * @example
 * // 發送繁體中文歡迎郵件
 * await sendWelcomeEmail('user@example.com', '王小明', 'zh-TW');
 *
 * @since 1.0.0
 */
export async function sendWelcomeEmail(
  email: string,
  username: string,
  locale: string = 'en'
): Promise<EmailResult> {
  // 實作...
}

/**
 * 郵件發送結果
 *
 * @typedef {Object} EmailResult
 * @property {boolean} success - 是否發送成功
 * @property {string} messageId - 郵件訊息 ID
 * @property {number} timestamp - 發送時間戳記
 */
```

## 🤝 類別五：團隊協作

### 團隊使用 Claude Code 的最佳實踐

**建立團隊規範：**

```markdown
# 團隊 Claude Code 使用規範

## 1. 提示詞風格指南

### 命名規則
- 使用清晰、描述性的變數名稱
- 遵循專案的命名慣例（camelCase, PascalCase）
- 避免縮寫（除非是廣為人知的）

### 程式碼風格
- 遵循 ESLint 規則
- 使用 Prettier 格式化
- 優先使用 TypeScript

### 文檔要求
- 所有 public API 必須有 JSDoc
- 複雜邏輯需要註解說明
- README 保持更新

## 2. Git 工作流程

### Commit 訊息格式
feat: 新增使用者認證功能
fix: 修復登入按鈕樣式
refactor: 重構資料處理邏輯
docs: 更新 API 文檔
test: 新增單元測試

### Branch 命名
feature/user-authentication
bugfix/login-button-style
refactor/data-processing
docs/api-documentation

## 3. Code Review 標準

- 安全性檢查
- 效能考量
- 測試覆蓋率
- 文檔完整性
- 程式碼可讀性

## 4. 使用 Claude Code 的時機

✅ 適合使用：
- 實作新功能
- 重構舊程式碼
- 撰寫測試
- 文檔生成
- Bug 診斷

⚠️ 謹慎使用：
- 關鍵安全性程式碼（需人工審查）
- 複雜的架構決策（需團隊討論）
- 生產環境熱修復（需多重驗證）
```

## 📋 最佳實踐總結檢查清單

**使用前檢查：**

```markdown
☐ 提供清晰、具體的指令
☐ 包含充足的背景資訊
☐ 將複雜任務分解為小步驟
☐ 指明參考資料或範例
☐ 標示不可修改的部分
```

**專案設定檢查：**

```markdown
☐ 專案結構清晰且合邏輯
☐ 檔案命名具描述性
☐ .claudeignore 正確設定
☐ README 文檔完整
☐ 編輯器整合已設定
```

**程式碼品質檢查：**

```markdown
☐ 包含適當的測試
☐ 進行安全性審查
☐ 效能已優化
☐ 錯誤處理完整
☐ 文檔齊全
```

## 🎯 實戰範例：完整開發流程

**情境：實作一個使用者註冊功能**

```typescript
// Step 1: 明確需求
"實作使用者註冊功能，包含以下需求：

【功能需求】
- Email 和密碼註冊
- Email 格式驗證
- 密碼強度檢查（最少 8 字元，含大小寫和數字）
- Email 重複檢查
- 註冊成功後發送驗證郵件

【技術棧】
- Backend: Node.js + Express + TypeScript
- Database: PostgreSQL + Prisma
- Email: SendGrid

【檔案結構】
src/
├── api/
│   └── auth/
│       └── register.ts
├── services/
│   ├── userService.ts
│   └── emailService.ts
├── validators/
│   └── authValidator.ts
└── types/
    └── user.ts

【要求】
1. 包含完整的錯誤處理
2. 撰寫單元測試（Jest）
3. 加入 JSDoc 文檔
4. 遵循 RESTful API 慣例"

// Step 2: 使用 Todo List 追蹤進度
// Claude Code 會自動建立：
// ✓ 建立 User type 定義
// ✓ 實作 auth validator
// 🔄 實作 userService.createUser()
// ⏳ 實作 emailService.sendVerificationEmail()
// ⏳ 實作 API endpoint
// ⏳ 撰寫測試

// Step 3: 逐步實作並驗證
// 每個步驟完成後執行測試

// Step 4: Code Review
"/review-pr --focus=security,performance,tests"

// Step 5: 文檔更新
"更新 API.md，新增註冊 endpoint 的文檔"

// Step 6: Commit
"/commit"
```

## 🚀 結論：持續改進

使用 Claude Code 是一個持續學習和改進的過程：

### **進階技巧學習路徑：**

```
初級（1-2 週）
├─ 基本指令使用
├─ 檔案讀寫操作
└─ 簡單的程式碼修改

中級（1 個月）
├─ 複雜任務分解
├─ 多檔案協調
├─ 測試與文檔
└─ Sub-agent 使用

高級（2-3 個月）
├─ 自訂 Skills
├─ MCP 整合
├─ 工作流程優化
└─ 團隊協作規範

專家級（持續）
├─ 架構設計諮詢
├─ 效能深度優化
├─ 安全審計
└─ 最佳實踐貢獻
```

### **關鍵心態：**

1. **Claude Code 是助手，不是替代品** - 仍需人工判斷和決策
2. **明確溝通比速度重要** - 花時間寫清楚需求可節省後續時間
3. **持續驗證和測試** - 不要盲目信任 AI 生成的程式碼
4. **文檔和註解很重要** - 幫助 Claude 理解專案背景
5. **從錯誤中學習** - 記錄有效和無效的提示方式

### **下一步行動：**

```markdown
☐ 檢視並更新專案的 README.md
☐ 建立 .claudeignore 檔案
☐ 設定編輯器整合
☐ 與團隊分享使用規範
☐ 建立常用 Skills
☐ 定期進行 Code Review
☐ 持續學習新功能和最佳實踐
```

---

## 延伸閱讀

- [深入理解 Claude Code Context Window](/claude-code-context-window-deep-dive-zh)
- [Claude Code 開發工作流程完整指南](/claude-code-development-workflow-zh)
- [深入理解 Claude Code 架構](/claude-code-architecture-explained-zh)

**標籤**: #claude-code #最佳實踐 #AI開發 #提示工程 #開發效率 #程式設計
