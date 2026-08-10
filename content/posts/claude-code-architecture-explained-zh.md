---
title: "深入理解 Claude Code 架構：Plugin、Skill、Sub-agent 與 MCP 完整指南"
date: 2026-01-17T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "ai", "tools"]
tags: ["AI", "claude-code", "mcp", "plugin", "skill", "agent", "開發工具", "自動化", "架構設計", "development-tools"]
summary: "完整解析 Claude Code 的核心架構元件：從底層的 MCP 協議到高層的 Sub-agent，了解 Plugin、Skill、Sub-agent 與 MCP 的運作原理、使用時機與層級關係。"
readTime: "20 min"
---

Claude Code 作為 Anthropic 官方推出的 AI 驅動開發工具，其強大功能背後是由多個精心設計的架構元件組成。本文將深入解析 **MCP (Model Context Protocol)**、**Plugin**、**Skill** 和 **Sub-agent** 這四個核心概念，幫助開發者全面理解 Claude Code 的架構設計並有效運用。

## 🎯 核心概念概覽

在深入探討之前，讓我們先建立整體概念：

```
使用者
  │
  ▼
┌──────────────────────────────────────────────────────┐
│            Claude Code 主要實例                       │
│         (與使用者直接互動的 Claude)                    │
└─────────────┬────────────────────────────────────────┘
              │
              ├─────► Skill (技能/指令)
              │       /commit, /review-pr, /test
              │       └─► 高層級命令快捷方式
              │
              ├─────► Sub-agent (子代理)
              │       專門處理特定任務的 AI 代理
              │       ├─► Bash Agent (命令執行專家)
              │       ├─► Explore Agent (程式碼探索專家)
              │       ├─► Plan Agent (架構規劃專家)
              │       └─► General Purpose Agent (通用代理)
              │
              └─────► MCP + Plugin (底層能力擴展)
                      │
                      ├─► MCP Protocol (協議層)
                      │   └─► 定義 Claude 如何與外部工具溝通
                      │
                      └─► Plugins (插件層)
                          ├─► Database Plugin (資料庫連接)
                          ├─► API Plugin (API 整合)
                          ├─► File System Plugin (檔案系統)
                          └─► Custom Tools (自訂工具)
```

### 📊 元件層級與關係

這四個元件形成了清晰的層級架構：

| 層級 | 元件 | 抽象程度 | 主要用途 |
|------|------|---------|---------|
| **L4** | **Skill** | 最高 | 使用者友善的命令介面 |
| **L3** | **Sub-agent** | 高 | 專門任務的獨立 AI 代理 |
| **L2** | **Plugin** | 中 | 預建的功能擴展包 |
| **L1** | **MCP** | 最低 | 底層通訊協議 |

## 📘 L1: MCP (Model Context Protocol) - 基礎協議層

### 🔍 什麼是 MCP？

**Model Context Protocol (模型上下文協議)** 是 Anthropic 開發的開放協議，定義了 AI 模型如何與外部系統、工具和資料源安全地互動。

```
┌─────────────────────────────────────────────────────┐
│              MCP 協議架構                            │
│                                                     │
│  ┌────────────┐         ┌────────────┐            │
│  │  Claude    │◄───────►│ MCP Client │            │
│  │   Code     │  JSON   │            │            │
│  └────────────┘   RPC   └─────┬──────┘            │
│                               │                     │
│                               │ stdio/HTTP         │
│                               │                     │
│                      ┌────────▼──────┐             │
│                      │  MCP Server   │             │
│                      │               │             │
│                      │ ┌───────────┐ │             │
│                      │ │ Tools     │ │             │
│                      │ │ Registry  │ │             │
│                      │ └───────────┘ │             │
│                      │               │             │
│                      │ ┌───────────┐ │             │
│                      │ │ Resources │ │             │
│                      │ │ Manager   │ │             │
│                      │ └───────────┘ │             │
│                      │               │             │
│                      │ ┌───────────┐ │             │
│                      │ │ Prompts   │ │             │
│                      │ │ Templates │ │             │
│                      │ └───────────┘ │             │
│                      └───────┬───────┘             │
│                              │                      │
│                    ┌─────────┴─────────┐           │
│                    │                   │           │
│              ┌─────▼──────┐     ┌─────▼──────┐    │
│              │ File       │     │ Database   │    │
│              │ System     │     │ Queries    │    │
│              └────────────┘     └────────────┘    │
│                    │                   │           │
│              ┌─────▼──────┐     ┌─────▼──────┐    │
│              │ APIs       │     │ Custom     │    │
│              │            │     │ Services   │    │
│              └────────────┘     └────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 🎯 MCP 的核心能力

MCP 提供三大核心功能：

#### 1. **Tools (工具)**

讓 Claude 執行特定操作的函式：

```python
# MCP Server 範例：定義自訂工具
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("my-custom-server")

@server.list_tools()
async def list_available_tools():
    """定義 Claude 可使用的工具"""
    return [
        Tool(
            name="query_database",
            description="查詢 PostgreSQL 資料庫",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL 查詢語句"
                    },
                    "database": {
                        "type": "string",
                        "description": "目標資料庫名稱"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="send_slack_message",
            description="發送 Slack 訊息到指定頻道",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["channel", "message"]
            }
        )
    ]

@server.call_tool()
async def execute_tool(name: str, arguments: dict):
    """執行工具呼叫"""
    if name == "query_database":
        query = arguments["query"]
        database = arguments.get("database", "main")

        # 執行資料庫查詢
        result = await run_database_query(query, database)

        return [TextContent(
            type="text",
            text=f"查詢結果：\n{result}"
        )]

    elif name == "send_slack_message":
        # 發送 Slack 訊息
        success = await send_to_slack(
            arguments["channel"],
            arguments["message"]
        )

        return [TextContent(
            type="text",
            text="✅ 訊息已發送" if success else "❌ 發送失敗"
        )]
```

#### 2. **Resources (資源)**

讓 Claude 讀取外部資料：

```python
@server.list_resources()
async def list_resources():
    """列出可用資源"""
    return [
        Resource(
            uri="db://production/users",
            name="使用者資料表",
            description="生產環境的使用者資料",
            mimeType="application/json"
        ),
        Resource(
            uri="api://github/repos",
            name="GitHub 倉庫列表",
            description="組織的 GitHub 倉庫",
            mimeType="application/json"
        )
    ]

@server.read_resource()
async def read_resource(uri: str):
    """讀取特定資源"""
    if uri.startswith("db://"):
        # 查詢資料庫
        data = await query_database(uri)
        return ResourceContents(
            uri=uri,
            mimeType="application/json",
            text=json.dumps(data)
        )
```

#### 3. **Prompts (提示模板)**

預定義的提示模板：

```python
@server.list_prompts()
async def list_prompts():
    """提供提示模板"""
    return [
        Prompt(
            name="code_review",
            description="執行程式碼審查",
            arguments=[
                PromptArgument(
                    name="file_path",
                    description="要審查的檔案路徑",
                    required=True
                ),
                PromptArgument(
                    name="focus_areas",
                    description="重點審查領域（例：安全性、效能）",
                    required=False
                )
            ]
        )
    ]

@server.get_prompt()
async def get_prompt(name: str, arguments: dict):
    """返回完整的提示內容"""
    if name == "code_review":
        file_path = arguments["file_path"]
        focus = arguments.get("focus_areas", "一般品質")

        return PromptMessage(
            role="user",
            content=f"""
請審查以下檔案：{file_path}

重點關注：{focus}

檢查項目：
1. 程式碼品質與可讀性
2. 潛在的 bug 或錯誤
3. 效能問題
4. 安全性漏洞
5. 最佳實踐遵循

請提供詳細的改進建議。
            """
        )
```

### 🔧 設定 MCP Server

**Claude Code 設定檔 (`~/.config/claude-code/settings.json`)：**

```json
{
  "mcpServers": {
    "database-tools": {
      "command": "python",
      "args": ["/path/to/database-mcp-server.py"],
      "env": {
        "DATABASE_URL": "postgresql://localhost/mydb"
      },
      "description": "資料庫查詢工具",
      "enabled": true
    },
    "slack-integration": {
      "command": "node",
      "args": ["/path/to/slack-mcp-server.js"],
      "env": {
        "SLACK_TOKEN": "${SLACK_BOT_TOKEN}"
      },
      "description": "Slack 訊息整合",
      "enabled": true
    },
    "custom-tools": {
      "command": "uvx",
      "args": ["my-mcp-package"],
      "description": "自訂開發工具集",
      "enabled": true
    }
  }
}
```

### 🎯 何時使用 MCP？

**使用 MCP 的場景：**

✅ **需要連接外部系統**
- 資料庫查詢（PostgreSQL、MySQL、MongoDB）
- API 整合（REST、GraphQL）
- 雲端服務（AWS、GCP、Azure）

✅ **需要自訂工具**
- 公司內部系統整合
- 專有協議或格式
- 特殊業務邏輯

✅ **需要即時資料**
- 監控系統狀態
- 查詢生產環境資料
- 即時日誌分析

❌ **不需要 MCP 的場景：**
- 簡單的檔案操作（Claude Code 內建）
- 標準 Git 操作（內建支援）
- 基本程式碼編輯（核心功能）

### 📊 MCP 實際應用範例

#### 範例 1：連接 PostgreSQL 資料庫

```python
# database_mcp_server.py
import asyncio
import asyncpg
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("postgres-mcp")

@server.call_tool()
async def handle_tool(name: str, arguments: dict):
    if name == "query_users":
        conn = await asyncpg.connect(
            user='admin',
            password='secret',
            database='production',
            host='localhost'
        )

        rows = await conn.fetch(
            'SELECT * FROM users WHERE active = $1',
            True
        )

        await conn.close()

        return [TextContent(
            type="text",
            text=f"找到 {len(rows)} 位活躍使用者\n{rows}"
        )]
```

**使用方式：**
```
使用者: "查詢所有活躍使用者"
Claude: [使用 MCP tool "query_users"]
結果: 返回使用者列表
```

#### 範例 2：整合 Jira API

```typescript
// jira_mcp_server.ts
import { Server } from "@modelcontextprotocol/sdk/server";
import JiraClient from "jira-client";

const server = new Server({
  name: "jira-integration",
  version: "1.0.0",
});

const jira = new JiraClient({
  protocol: "https",
  host: "your-domain.atlassian.net",
  username: process.env.JIRA_EMAIL,
  password: process.env.JIRA_API_TOKEN,
  apiVersion: "2",
  strictSSL: true,
});

server.setRequestHandler("tools/call", async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "create_jira_ticket") {
    const issue = await jira.addNewIssue({
      fields: {
        project: { key: args.project },
        summary: args.summary,
        description: args.description,
        issuetype: { name: "Bug" },
      },
    });

    return {
      content: [
        {
          type: "text",
          text: `✅ 已建立 Jira ticket: ${issue.key}`,
        },
      ],
    };
  }
});
```

## 🔌 L2: Plugin (插件) - 預建功能擴展

### 🔍 什麼是 Plugin？

**Plugin** 是基於 MCP 協議構建的預先打包好的功能模組，提供特定領域的能力擴展。可以將 Plugin 視為「MCP Server 的應用商店版本」。

```
┌───────────────────────────────────────────────────┐
│           Plugin 生態系統                          │
│                                                   │
│  ┌─────────────────┐      ┌─────────────────┐    │
│  │   Official      │      │   Community     │    │
│  │   Plugins       │      │   Plugins       │    │
│  └────────┬────────┘      └────────┬────────┘    │
│           │                        │             │
│    ┌──────┴──────┐          ┌──────┴──────┐      │
│    │             │          │             │      │
│ ┌──▼───┐   ┌────▼────┐  ┌──▼───┐   ┌────▼────┐  │
│ │ DB   │   │ GitHub  │  │ AWS  │   │ Custom  │  │
│ │Plugin│   │ Plugin  │  │Plugin│   │ Plugins │  │
│ └──┬───┘   └────┬────┘  └──┬───┘   └────┬────┘  │
│    │            │           │            │       │
│    └────────────┴───────────┴────────────┘       │
│                     │                            │
│            ┌────────▼─────────┐                  │
│            │   MCP Protocol   │                  │
│            │   (底層通訊)      │                  │
│            └──────────────────┘                  │
└───────────────────────────────────────────────────┘
```

### 📦 常見 Plugin 類型

#### 1. **資料庫 Plugins**

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://user:pass@localhost/db"
      }
    },
    "mongodb": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-mongodb"],
      "env": {
        "MONGODB_URI": "mongodb://localhost:27017/mydb"
      }
    }
  }
}
```

**提供的能力：**
- 執行 SQL/NoSQL 查詢
- 資料庫 schema 檢視
- 資料匯入/匯出
- 效能分析

#### 2. **版本控制 Plugins**

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    },
    "gitlab": {
      "command": "python",
      "args": ["-m", "mcp_gitlab"],
      "env": {
        "GITLAB_TOKEN": "${GITLAB_ACCESS_TOKEN}",
        "GITLAB_URL": "https://gitlab.com"
      }
    }
  }
}
```

**提供的能力：**
- 建立/管理 Pull Requests
- Issue 管理
- 程式碼審查
- CI/CD 整合

#### 3. **雲端服務 Plugins**

```json
{
  "mcpServers": {
    "aws": {
      "command": "python",
      "args": ["-m", "mcp_aws"],
      "env": {
        "AWS_REGION": "us-east-1",
        "AWS_PROFILE": "default"
      }
    },
    "gcp": {
      "command": "node",
      "args": ["gcp-mcp-server.js"],
      "env": {
        "GCP_PROJECT_ID": "my-project",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/credentials.json"
      }
    }
  }
}
```

**提供的能力：**
- 資源管理（EC2、S3、Lambda 等）
- 監控與日誌
- 成本分析
- 部署自動化

#### 4. **開發工具 Plugins**

```json
{
  "mcpServers": {
    "docker": {
      "command": "npx",
      "args": ["-y", "mcp-docker-server"]
    },
    "kubernetes": {
      "command": "kubectl-mcp",
      "args": ["--context", "production"]
    }
  }
}
```

### 🆚 Plugin vs 直接使用 MCP

| 特性 | 直接使用 MCP | 使用 Plugin |
|------|-------------|------------|
| **設定複雜度** | 高（需撰寫 Server 程式） | 低（安裝即用） |
| **客製化程度** | 完全客製化 | 有限（依 Plugin 設計） |
| **維護成本** | 高（自行維護） | 低（社群維護） |
| **學習曲線** | 陡峭 | 平緩 |
| **適用場景** | 特殊需求、公司內部系統 | 常見工具、標準服務 |

### 🎯 何時使用 Plugin？

✅ **應該使用 Plugin：**
- 連接常見服務（GitHub、AWS、資料庫）
- 快速原型開發
- 標準化工作流程
- 團隊協作（共用配置）

❌ **應該自建 MCP Server：**
- 公司專有系統
- 特殊安全要求
- 需要深度客製化
- 現有 Plugin 無法滿足需求

### 📊 Plugin 實戰範例

#### 範例 1：使用 GitHub Plugin 自動化 PR 流程

```bash
# 安裝 GitHub MCP Plugin
npm install -g @modelcontextprotocol/server-github
```

**Claude Code 使用情境：**

```
使用者: "為 feature/login-page 分支建立 PR 到 main"

Claude: [使用 GitHub Plugin]
       1. 檢查分支狀態
       2. 建立 Pull Request
       3. 新增審查者
       4. 套用標籤

結果: ✅ PR #123 已建立
      https://github.com/user/repo/pull/123
```

#### 範例 2：整合多個 Plugins 進行完整工作流程

```
使用者: "部署最新版本到 staging 環境"

Claude 執行流程：
  1. [Git Plugin] 確認在 main 分支
  2. [Docker Plugin] 建立 Docker image
  3. [AWS Plugin] 推送到 ECR
  4. [Kubernetes Plugin] 更新 staging deployment
  5. [Slack Plugin] 發送通知到 #deployments 頻道

結果: 🚀 v1.2.3 已部署到 staging
```

## 🎨 L3: Skill (技能) - 高階命令介面

### 🔍 什麼是 Skill？

**Skill** 是 Claude Code 提供的高階命令介面，類似「巨集」或「快捷命令」，將複雜的多步驟操作包裝成簡單的斜槓命令。

```
┌────────────────────────────────────────────────────┐
│              Skill 執行流程                         │
│                                                    │
│  使用者輸入: /commit -m "Add feature"              │
│       │                                            │
│       ▼                                            │
│  ┌──────────────┐                                 │
│  │ Skill Parser │ 解析命令與參數                   │
│  └──────┬───────┘                                 │
│         │                                          │
│         ▼                                          │
│  ┌──────────────┐                                 │
│  │ Skill Logic  │ 執行預定義流程                   │
│  └──────┬───────┘                                 │
│         │                                          │
│    ┌────┴────┐                                    │
│    │         │                                    │
│    ▼         ▼                                    │
│ ┌────┐   ┌────────┐                              │
│ │Bash│   │Sub-agent│ 可能呼叫                     │
│ │Tool│   │        │                              │
│ └────┘   └────────┘                              │
│    │         │                                    │
│    ▼         ▼                                    │
│  執行 Git 操作                                     │
└────────────────────────────────────────────────────┘
```

### 📋 內建 Skills 列表

Claude Code 預設提供多個實用 Skills：

#### 1. **/commit** - Git 提交管理

```bash
# 基本用法
/commit                          # 智能生成 commit message
/commit -m "Fix bug"             # 使用自訂訊息
/commit --amend                  # 修改上次 commit

# Skill 內部流程：
# 1. git status 檢查變更
# 2. git diff 分析差異
# 3. 生成語意化 commit message
# 4. git add 加入變更
# 5. git commit 提交
# 6. 顯示結果
```

**執行示例：**
```
使用者: /commit

Claude 分析程式碼變更：
  - 新增 UserService.ts
  - 修改 auth.middleware.ts
  - 更新測試檔案

生成的 Commit Message:
  feat(auth): implement user authentication service

  - Add UserService with login/logout methods
  - Update auth middleware to use new service
  - Add comprehensive unit tests

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

執行: git add . && git commit -m "..."
✅ Commit 成功！
```

#### 2. **/review-pr** - Pull Request 審查

```bash
/review-pr 123                   # 審查 PR #123
/review-pr --full                # 完整深度審查
/review-pr 123 --security        # 重點安全審查

# Skill 流程：
# 1. [GitHub Plugin] 獲取 PR 資訊
# 2. [Read Tool] 讀取變更檔案
# 3. [Sub-agent] 深度分析程式碼
# 4. 生成審查報告
# 5. [GitHub Plugin] 發佈評論
```

#### 3. **/test** - 自動化測試

```bash
/test                            # 執行所有測試
/test unit                       # 只執行單元測試
/test src/utils/validator.test.ts  # 測試特定檔案

# Skill 流程：
# 1. 偵測測試框架（Jest, Pytest, Go test 等）
# 2. [Bash Tool] 執行測試命令
# 3. 解析測試結果
# 4. 如有失敗，分析原因並提供修復建議
```

#### 4. **/build** - 專案建構

```bash
/build                           # 執行建構流程
/build --prod                    # 生產環境建構
/build --watch                   # 監看模式

# Skill 流程：
# 1. 識別專案類型（Node.js, Python, Go 等）
# 2. 執行對應建構命令
# 3. 監控建構過程
# 4. 報告建構結果
# 5. 如失敗，分析錯誤並修復
```

#### 5. **/deploy** - 部署管理

```bash
/deploy staging                  # 部署到 staging
/deploy production --confirm     # 部署到 production

# Skill 流程：
# 1. [Docker Plugin] 建立 container
# 2. [AWS/K8s Plugin] 執行部署
# 3. 健康檢查
# 4. [Slack Plugin] 發送通知
```

### 🛠️ 建立自訂 Skill

**Skill 定義檔案結構：**

```typescript
// ~/.config/claude-code/skills/my-skill.ts
import { Skill } from '@claude/skill-sdk';

export const myCustomSkill: Skill = {
  name: 'deploy-full-stack',
  description: '一鍵部署前後端應用',

  // 命令參數定義
  arguments: {
    environment: {
      type: 'string',
      required: true,
      choices: ['dev', 'staging', 'production']
    },
    skipTests: {
      type: 'boolean',
      default: false
    }
  },

  // 執行邏輯
  async execute(args, context) {
    const { environment, skipTests } = args;

    // 步驟 1: 執行測試（除非跳過）
    if (!skipTests) {
      await context.runSkill('test');
    }

    // 步驟 2: 建構前端
    await context.bash('cd frontend && npm run build');

    // 步驟 3: 建構後端
    await context.bash('cd backend && go build');

    // 步驟 4: 建立 Docker images
    await context.plugin('docker', 'build', {
      tags: [`app-frontend:${environment}`, `app-backend:${environment}`]
    });

    // 步驟 5: 部署
    if (environment === 'production') {
      await context.confirmWithUser('確定要部署到 production？');
    }

    await context.plugin('kubernetes', 'deploy', {
      namespace: environment,
      manifests: ['k8s/frontend.yaml', 'k8s/backend.yaml']
    });

    // 步驟 6: 驗證部署
    const health = await context.plugin('kubernetes', 'healthCheck', {
      namespace: environment
    });

    if (health.status === 'healthy') {
      await context.plugin('slack', 'sendMessage', {
        channel: '#deployments',
        message: `✅ 已成功部署到 ${environment}`
      });

      return { success: true, message: '部署完成！' };
    } else {
      throw new Error('部署健康檢查失敗');
    }
  }
};
```

**使用自訂 Skill：**
```bash
# 註冊 Skill
claude-code skill add deploy-full-stack

# 使用
/deploy-full-stack staging
/deploy-full-stack production --skip-tests
```

### 🎯 何時使用 Skill？

✅ **應該建立 Skill：**
- 重複性高的工作流程
- 多步驟操作需要協調
- 團隊標準化流程
- 需要輸入驗證的操作

❌ **不需要 Skill：**
- 一次性任務
- 簡單單一命令
- 高度變化的操作
- 僅用於個人的臨時指令

### 📊 Skill vs Sub-agent

| 特性 | Skill | Sub-agent |
|------|-------|-----------|
| **本質** | 預定義命令腳本 | 獨立 AI 代理 |
| **智能程度** | 低（按腳本執行） | 高（自主決策） |
| **使用方式** | /skill-name | 自動或手動呼叫 |
| **適用場景** | 固定流程 | 複雜分析任務 |
| **成本** | 低（不消耗額外 tokens） | 高（獨立 API 呼叫） |

## 🤖 L4: Sub-agent (子代理) - 專門任務代理

### 🔍 什麼是 Sub-agent？

**Sub-agent** 是 Claude Code 為處理特定複雜任務而啟動的專門 AI 代理實例。每個 Sub-agent 都是一個獨立的 Claude 實例，具有特定的系統提示和工具集。

```
┌──────────────────────────────────────────────────────┐
│          主要 Claude Code 實例                        │
│          (與使用者對話)                               │
└────────────────────┬─────────────────────────────────┘
                     │
          ┌──────────┴───────────┐
          │   決定需要專門處理    │
          └──────────┬───────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
     ▼               ▼               ▼
┌─────────┐   ┌──────────┐   ┌──────────┐
│ Bash    │   │ Explore  │   │  Plan    │
│ Agent   │   │ Agent    │   │  Agent   │
│         │   │          │   │          │
│專精:    │   │專精:     │   │專精:     │
│命令執行 │   │程式碼探索│   │架構規劃  │
│         │   │          │   │          │
│工具:    │   │工具:     │   │工具:     │
│• Bash   │   │• Glob    │   │• Read    │
│         │   │• Grep    │   │• Glob    │
│         │   │• Read    │   │• Grep    │
└─────────┘   └──────────┘   └──────────┘
     │               │               │
     └───────────────┴───────────────┘
                     │
                     ▼
            ┌────────────────┐
            │  完成任務後     │
            │  返回結果       │
            └────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│          主要實例繼續處理                             │
└──────────────────────────────────────────────────────┘
```

### 🎨 內建 Sub-agent 類型

#### 1. **Bash Agent** - 命令執行專家

```
角色: 專門執行複雜的 Bash 命令和系統操作
工具: Bash (唯一工具)
使用時機: 需要執行多步驟命令序列

範例任務:
- Git 操作（複雜的 rebase、merge）
- 建構和部署腳本
- 系統管理任務
- 批次檔案處理
```

**實際使用範例：**
```
使用者: "將所有 .js 檔案轉換為 .ts，保留原始檔案"

主要 Claude: [分析任務] → [啟動 Bash Agent]

Bash Agent 執行:
#!/bin/bash
for file in $(find . -name "*.js"); do
  ts_file="${file%.js}.ts"
  cp "$file" "$ts_file"
  # 使用 jscodeshift 轉換語法
  npx jscodeshift -t typescript.js "$ts_file"
  echo "✅ Converted: $file → $ts_file"
done

返回: 轉換完成，共處理 47 個檔案
```

#### 2. **Explore Agent** - 程式碼探索專家

```
角色: 專門探索和理解大型程式碼庫
工具: Glob, Grep, Read (不能寫檔案)
使用時機: 需要深入理解程式碼結構

範例任務:
- "找出所有使用 deprecated API 的地方"
- "分析專案的目錄結構"
- "找出所有 API endpoints"
- "追蹤函式呼叫鏈"
```

**實際使用範例：**
```
使用者: "找出專案中所有的 API endpoints 和它們的認證方式"

主要 Claude: [啟動 Explore Agent]

Explore Agent 執行策略:
1. [Glob] 找出所有路由檔案：**/*route*.{ts,js}
2. [Grep] 搜尋 app.get, app.post, app.put, app.delete
3. [Read] 讀取每個路由檔案
4. [Grep] 搜尋認證中介層：authenticateToken, requireAuth
5. [分析] 組織成結構化報告

返回:
┌──────────────────────────────────────────────────────┐
│ API Endpoints 分析報告                               │
├──────────────────────────────────────────────────────┤
│ 公開 Endpoints (無認證):                             │
│  • GET  /api/health                                  │
│  • POST /api/auth/login                              │
│  • POST /api/auth/register                           │
│                                                      │
│ 需要認證 (JWT Token):                                │
│  • GET    /api/users/profile       [requireAuth]    │
│  • PUT    /api/users/profile       [requireAuth]    │
│  • GET    /api/posts               [requireAuth]    │
│  • POST   /api/posts               [requireAuth]    │
│  • DELETE /api/posts/:id           [requireAuth]    │
│                                                      │
│ 管理員專用 (Admin Role):                             │
│  • GET    /api/admin/users         [requireAdmin]   │
│  • DELETE /api/admin/users/:id     [requireAdmin]   │
└──────────────────────────────────────────────────────┘
```

#### 3. **Plan Agent** - 架構規劃專家

```
角色: 進入「規劃模式」設計實作策略
工具: Read, Glob, Grep (只能探索，不能寫)
使用時機: 複雜功能需要先規劃再實作

流程:
1. 理解需求
2. 探索現有程式碼
3. 設計實作方案
4. 寫入計畫檔案
5. 請求使用者批准
6. 退出規劃模式，開始實作
```

**實際使用範例：**
```
使用者: "新增使用者個人檔案圖片上傳功能"

主要 Claude: [判斷為複雜功能] → [啟動 Plan Agent]

Plan Agent 流程:

第一階段：探索現有架構
  [Glob] 找出使用者相關檔案
  [Read] 讀取 User model, UserController, UserService
  [Grep] 搜尋現有的檔案上傳實作

第二階段：設計方案並寫入計畫檔案
  [Write] 建立 /tmp/claude-plan-xxx.md

計畫內容:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 實作計畫：使用者頭像上傳功能

## 1. 資料庫變更
- User table 新增欄位：avatar_url (VARCHAR)
- 建立 migration: 20260117_add_user_avatar.sql

## 2. 後端實作
檔案：src/controllers/UserController.ts
- 新增 POST /api/users/avatar endpoint
- 使用 multer 處理 multipart/form-data
- 檔案驗證：
  * 只接受 jpg, png, webp
  * 最大 5MB
- 儲存到 AWS S3 bucket: user-avatars/
- 更新 User.avatar_url

檔案：src/services/S3Service.ts
- uploadUserAvatar(userId, file) 方法
- 使用預先簽署的 URL

## 3. 前端實作
檔案：src/components/UserProfile/AvatarUpload.tsx
- 新增檔案選擇 UI
- 圖片預覽
- 上傳進度條
- 錯誤處理

## 4. 測試
- 單元測試：UserController.test.ts
- 整合測試：avatar-upload.e2e.test.ts

## 5. 風險與考量
- S3 bucket CORS 設定
- 檔案大小限制
- 圖片壓縮/調整大小
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ExitPlanMode] 請使用者批准計畫

使用者批准後 → 主要 Claude 按計畫實作
```

#### 4. **General Purpose Agent** - 通用任務代理

```
角色: 處理不特定類型的複雜多步驟任務
工具: 所有工具（Read, Write, Edit, Bash, Grep, Glob 等）
使用時機: 需要結合多種操作的任務

範例任務:
- "重構這個模組，提高可測試性"
- "實作完整的登入功能（前後端）"
- "診斷並修復這個 bug"
```

### 🔄 Sub-agent 生命週期

```
┌──────────────────────────────────────────────────┐
│ 1. 任務判斷                                       │
│    主要 Claude 分析任務是否需要 Sub-agent         │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ 2. Agent 選擇                                     │
│    根據任務類型選擇適當的 Sub-agent               │
│    • 命令執行 → Bash Agent                       │
│    • 程式碼探索 → Explore Agent                  │
│    • 功能規劃 → Plan Agent                       │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ 3. Agent 啟動                                     │
│    建立新的 Claude 實例，載入專門系統提示         │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ 4. 任務執行                                       │
│    Sub-agent 獨立執行，可進行多輪對話             │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ 5. 結果返回                                       │
│    完成後將結果返回給主要實例                     │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ 6. Agent 終止                                     │
│    Sub-agent 實例關閉，釋放資源                   │
└──────────────────────────────────────────────────┘
```

### 🎯 何時使用 Sub-agent？

Sub-agent 會在以下情況**自動啟動**：

✅ **Bash Agent 自動啟動時機：**
- 需要執行複雜的 Git 操作
- 多步驟建構或部署流程
- 批次檔案處理任務
- 系統管理操作

✅ **Explore Agent 自動啟動時機：**
- 「找出所有...」類型的問題
- 需要理解大型程式碼庫結構
- 追蹤函式或 API 使用情況
- 分析專案架構

✅ **Plan Agent 自動啟動時機：**
- 實作新功能（中到大型）
- 架構重構
- 跨多個檔案的變更
- 需要設計決策的任務

### 🆚 主要實例 vs Sub-agent

| 特性 | 主要 Claude 實例 | Sub-agent |
|------|----------------|-----------|
| **角色** | 與使用者對話 | 專門任務執行 |
| **系統提示** | 通用 | 專門化 |
| **工具存取** | 全部 | 受限（依類型） |
| **對話能力** | 與使用者互動 | 自主執行 |
| **Token 消耗** | 累積整個對話 | 獨立計算 |
| **適用任務** | 一般任務 | 複雜專門任務 |

## 🎯 整合應用：四個元件協同運作

### 實戰場景：建立完整的 Web 應用

```
任務: "建立一個部落格系統，包含使用者認證、文章 CRUD、評論功能"
```

**執行流程分析：**

#### 階段 1：規劃階段（Plan Agent）

```
主要 Claude: [判斷為大型功能] → [啟動 Plan Agent]

Plan Agent:
  [Explore Agent] 探索現有專案結構
  [Read] 檢查現有認證機制
  [設計] 建立實作計畫

計畫產出:
  - 資料庫 schema 設計
  - API endpoints 規格
  - 前端元件架構
  - 實作順序與依賴關係

[ExitPlanMode] 請求使用者批准
```

#### 階段 2：實作後端（使用 Skill + MCP）

```
主要 Claude: [執行 /backend-setup Skill]

Skill 流程:
  1. [Write] 建立 User, Post, Comment models
  2. [Write] 建立 migration 檔案
  3. [Bash Agent] 執行 migration
     bash: npx prisma migrate dev --name init

  4. [Write] 建立 AuthController
  5. [MCP: Database Plugin] 測試連接
  6. [Write] 建立 PostController, CommentController

  7. [Test Sub-agent] 執行測試
     bash: npm test
```

#### 階段 3：實作前端（General Purpose Agent）

```
主要 Claude: [啟動 General Purpose Agent]

Agent 執行:
  1. [Write] 建立 React 元件結構
     components/
       ├── Auth/
       │   ├── LoginForm.tsx
       │   └── RegisterForm.tsx
       ├── Post/
       │   ├── PostList.tsx
       │   ├── PostDetail.tsx
       │   └── PostEditor.tsx
       └── Comment/
           └── CommentSection.tsx

  2. [Write] 設定 API client (axios)
  3. [Write] 實作 state management (Zustand)
  4. [Edit] 整合路由 (React Router)

  5. [Bash Tool] 啟動開發伺服器
     bash: npm run dev
```

#### 階段 4：整合與測試（Skill + Sub-agents）

```
主要 Claude: [執行 /integration-test Skill]

Skill 流程:
  1. [Bash Agent] 啟動後端
     bash: cd backend && npm start &

  2. [Bash Agent] 啟動前端
     bash: cd frontend && npm run dev &

  3. [MCP: Browser Plugin] 執行 E2E 測試
     - 註冊新使用者
     - 登入
     - 建立文章
     - 新增評論
     - 登出

  4. [Test Agent] 執行所有測試套件
     bash: npm run test:all

  5. 產生測試報告
```

#### 階段 5：部署（Skill + Multiple Plugins）

```
主要 Claude: [執行 /deploy-full-stack Skill]

Skill 流程:
  1. [Docker Plugin] 建立 images
     - backend:latest
     - frontend:latest

  2. [AWS Plugin] 推送到 ECR

  3. [Kubernetes Plugin] 部署到叢集
     kubectl apply -f k8s/

  4. [MCP: Monitoring Plugin] 設定監控
     - Prometheus metrics
     - Grafana dashboards

  5. [Slack Plugin] 發送部署通知
     ✅ 部落格系統已部署
     🔗 https://blog.example.com
```

### 🎭 元件協同運作圖

```
                    使用者指令
                         │
                         ▼
        ┌────────────────────────────────┐
        │      主要 Claude Code 實例      │
        │     (對話管理與協調)            │
        └────────┬──────────┬─────────┬──┘
                 │          │         │
        ┌────────┘          │         └──────┐
        │                   │                │
        ▼                   ▼                ▼
┌──────────────┐   ┌───────────────┐  ┌──────────┐
│   Skill      │   │   Sub-agent   │  │   MCP    │
│   執行器      │   │   管理器       │  │   客戶端  │
└──────┬───────┘   └───────┬───────┘  └────┬─────┘
       │                   │                │
       │                   │                │
       │   ┌───────────────┴──────┐         │
       │   │                      │         │
       ▼   ▼                      ▼         ▼
┌─────────────┐          ┌──────────────┐  ┌────────────┐
│預定義工作流程│          │專門 AI 代理   │  │外部工具集合│
│• /commit    │          │• Bash Agent  │  │• Database  │
│• /test      │          │• Explore Agt │  │• GitHub    │
│• /deploy    │          │• Plan Agent  │  │• AWS       │
└─────────────┘          └──────────────┘  └────────────┘
       │                         │                 │
       └─────────────┬───────────┴─────────────────┘
                     │
                     ▼
              ┌────────────┐
              │  實際執行   │
              │  • Bash    │
              │  • Read    │
              │  • Write   │
              │  • API     │
              └────────────┘
```

## 🎓 決策指南：何時使用哪個元件？

### 決策樹

```
收到任務
    │
    ▼
是標準工作流程嗎？
    │
    ├─ 是 → 使用 Skill
    │       例：/commit, /test, /deploy
    │
    └─ 否
        │
        ▼
    需要外部系統整合嗎？
        │
        ├─ 是 → 使用 MCP/Plugin
        │       例：資料庫查詢、API 呼叫
        │
        └─ 否
            │
            ▼
        是複雜的探索/分析任務嗎？
            │
            ├─ 是 → 使用 Sub-agent
            │       • 程式碼探索 → Explore Agent
            │       • 命令執行 → Bash Agent
            │       • 功能規劃 → Plan Agent
            │
            └─ 否 → 主要實例直接處理
                    簡單檔案編輯、對話回應
```

### 實用範例對照表

| 任務描述 | 推薦方案 | 原因 |
|---------|---------|------|
| "提交程式碼變更" | **Skill**: /commit | 標準化 Git 工作流程 |
| "查詢生產環境資料庫的使用者數" | **MCP/Plugin**: Database | 需要外部系統連接 |
| "找出專案中所有使用 deprecated API 的地方" | **Sub-agent**: Explore | 需要深度程式碼探索 |
| "建立一個 REST API" | **Sub-agent**: Plan → General | 複雜功能需先規劃 |
| "修正這個拼寫錯誤" | **主要實例** | 簡單編輯 |
| "部署到 Kubernetes" | **Skill** + **Plugin** | 結合工作流程與外部整合 |
| "分析這個 bug 的根本原因" | **Sub-agent**: Explore + General | 需要探索和推理 |
| "建立 GitHub Pull Request" | **Plugin**: GitHub | 直接 API 整合 |

## 📊 效能與成本考量

### Token 消耗比較

```
任務: "找出專案中所有 TODO 註解"

方案 A：主要實例直接處理
┌────────────────────────────────────┐
│ 讀取所有檔案                        │
│ 分析每個檔案                        │
│ 彙整結果                            │
│                                    │
│ Token 消耗: ~15,000 tokens         │
│ 時間: 30 秒                         │
└────────────────────────────────────┘

方案 B：使用 Explore Agent
┌────────────────────────────────────┐
│ 主要實例 (100 tokens)              │
│   └─► 啟動 Explore Agent           │
│         └─► Grep "TODO" (200 tokens)│
│         └─► 讀取匹配檔案 (500 tokens)│
│         └─► 彙整 (300 tokens)       │
│                                    │
│ Token 總消耗: ~1,100 tokens        │
│ 時間: 5 秒                          │
└────────────────────────────────────┘

💡 節省: 93% tokens, 83% 時間
```

### 何時值得使用 Sub-agent？

✅ **值得：**
- 任務需要專門知識（例：複雜 Git 操作）
- 大量重複操作（例：批次檔案處理）
- 需要專注的深度分析
- 長時間執行的背景任務

❌ **不值得：**
- 簡單的一行命令
- 單一檔案的小修改
- 直接的問答互動
- 已有 Skill 可用的場景

## 🚀 最佳實踐

### 1. 層級化思維

```
高層級 (使用者友善)
    ↕
Skill - 標準化工作流程快捷方式
    ↕
Sub-agent - 專門任務的智能代理
    ↕
Plugin - 特定服務的預建整合
    ↕
MCP - 底層通訊協議
    ↕
低層級 (靈活但複雜)
```

**原則：** 盡可能使用高層級抽象，只在必要時降級

### 2. 組合使用

最強大的應用是組合多個元件：

```python
# 範例：自動化 Code Review 流程

# Skill 定義
@skill("review-and-deploy")
async def review_and_deploy(pr_number: int):
    # 1. 使用 GitHub Plugin 取得 PR 資訊
    pr_info = await plugins.github.get_pr(pr_number)

    # 2. 使用 Explore Agent 分析變更
    analysis = await agents.explore(
        f"分析 PR #{pr_number} 的所有變更檔案"
    )

    # 3. 使用 General Agent 執行審查
    review = await agents.general(
        f"根據分析結果審查程式碼品質",
        context=analysis
    )

    # 4. 如果審查通過，使用 Bash Agent 合併
    if review.approved:
        await agents.bash(
            f"git checkout main && git merge pr-{pr_number}"
        )

        # 5. 使用 Deploy Skill 部署
        await skills.deploy("staging")

        # 6. 使用 Slack Plugin 通知
        await plugins.slack.send(
            f"✅ PR #{pr_number} 已審查、合併並部署到 staging"
        )
```

### 3. 錯誤處理與備援

```python
async def robust_task_execution(task):
    try:
        # 嘗試使用 Skill（最快）
        return await execute_skill(task)
    except SkillNotFound:
        try:
            # Skill 不存在，使用 Sub-agent
            return await execute_with_subagent(task)
        except SubagentError:
            # Sub-agent 失敗，使用 Plugin
            return await execute_with_plugin(task)
    except Exception as e:
        # 所有方法失敗，回退到主要實例
        return await main_instance.handle(task)
```

## 🎉 總結

### 核心概念回顧

| 元件 | 層級 | 本質 | 主要用途 |
|------|------|------|---------|
| **MCP** | L1 基礎 | 通訊協議 | 定義 Claude 如何與外部世界溝通 |
| **Plugin** | L2 整合 | 預建模組 | 快速連接常見服務 |
| **Skill** | L3 自動化 | 命令快捷方式 | 標準化工作流程 |
| **Sub-agent** | L4 智能 | 專門 AI 代理 | 處理複雜專門任務 |

### 關鍵要點

1. **MCP 是基礎** - 所有外部整合都建立在 MCP 協議之上
2. **Plugin 是捷徑** - 使用現成 Plugin 而非重複造輪子
3. **Skill 是效率** - 為重複任務建立 Skill 以提升團隊效率
4. **Sub-agent 是智能** - 信任 Claude Code 自動選擇適當的 Agent

### 快速參考

```
需要連接外部系統？
  → 先找 Plugin，找不到就寫 MCP Server

重複執行的工作流程？
  → 建立 Skill

複雜的探索或分析任務？
  → 讓 Claude 自動啟動適當的 Sub-agent

簡單的編輯或對話？
  → 直接使用主要實例
```

### 延伸學習資源

- **MCP 官方文件**: https://spec.modelcontextprotocol.io/
- **Claude Code 文件**: https://docs.anthropic.com/claude/docs/claude-code
- **Plugin 倉庫**: https://github.com/modelcontextprotocol/servers
- **Skill 開發指南**: Claude Code CLI 內建說明

---

## 🏷️ 標籤與分類

**標籤**: AI, claude-code, mcp, plugin, skill, agent, 開發工具, 自動化, 架構設計
**分類**: AI, development-tools, automation
**難度**: 中級
**閱讀時間**: 20 分鐘
