---
title: "Hermes Agent 完全入門指南：自我改進的 AI 智能體"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent", "tools"]
tags: ["Hermes Agent", "AI Agent", "自動化", "安裝指南", "NousResearch"]
summary: "詳細介紹 Hermes Agent，一個具有自我學習和改進能力的 AI 系統。涵蓋核心功能、安裝步驟、配置方式和實際應用，幫助你快速上手這個強大的自主 AI 系統。"
readTime: "35 min"
---

Hermes Agent 是由 Nous Research 開發的革新性 AI 系統，其獨特之處在於**內置學習循環**——它從經驗中創建技能、在使用中改進技能、並持久化存儲知識。這不是單純的聊天機器人，而是一個真正自主改進的智能體系統。

---

## 什麼是 Hermes Agent？

### 核心概念

```
傳統 AI 系統：
輸入 → LLM → 輸出（每次都是獨立的）

Hermes Agent：
輸入 → LLM 
  ↓
[學習機制]
  ├→ 自動創建技能
  ├→ 在使用中改進
  └→ 搜索過往對話
  ↓
更聰明的 LLM → 更好的輸出

特點：
✓ 自我改進（Self-improving）
✓ 持久記憶（Persistent memory）
✓ 技能創建（Skill creation）
✓ 多平台訪問（Multi-platform）
✓ 本地運行（Local-first）
```

### 區別於其他系統

| 特性 | ChatGPT | Claude | Hermes Agent |
|------|---------|--------|------------|
| 本地運行 | ❌ | ❌ | ✅ |
| 自我學習 | ❌ | ❌ | ✅ |
| 創建技能 | ❌ | ❌ | ✅ |
| 長期記憶 | 有限 | 有限 | ✅ |
| 自動化任務 | ❌ | ❌ | ✅ |
| 多平台接入 | 網頁 | 網頁 | Telegram/Discord/Slack |
| 開源 | ❌ | ❌ | ✅ |

---

## 核心功能詳解

### 1. 自動技能創建

Hermes 在完成複雜任務後會自動創建「技能」，以便未來快速復用。

```
第一次：
用戶提出複雜需求 
  → Hermes 思考、查詢、提出方案
  → 耗時 5 分鐘

自動創建技能後：
用戶提出相似需求
  → Hermes 調用已有技能
  → 耗時 10 秒
```

**示例技能**：
- 網頁數據爬取技能
- 圖片批量處理技能
- 代碼 debug 技能
- 文本總結技能

### 2. 邊用邊學

```
使用中的改進循環：

用戶反饋 "這個結果還不夠好"
  ↓
Hermes 分析失敗原因
  ↓
修改技能實現
  ↓
重新執行
  ↓
如果成功 → 更新技能版本
```

### 3. 持久化記憶系統

```
所有對話被存儲在本地：
- FTS5 全文搜索（超快）
- 用戶檔案（偏好、背景）
- 對話歷史（可搜索）
- 上下文理解（跨對話）

優勢：
✓ 隱私第一（所有數據本地）
✓ 永不遺忘（持久記憶）
✓ 更好的上下文理解
✓ 個性化體驗
```

### 4. 多平台訪問

```
同一個 Hermes 系統，多個入口：

Telegram 機器人 → 邊走邊聊
Discord 伺服器 → 團隊協作
Slack 應用 → 工作場景
WhatsApp → 個人消息
Signal → 隱私優先
終端界面 → 開發者喜歡

核心系統在後端統一：
├─ 同一個知識庫
├─ 同一套技能
└─ 同一份記憶
```

---

## 安裝指南

### 前置要求

```
硬件：
- Mac/Linux/WSL2：2GB+ RAM
- GPU（可選）：加快推理

軟件：
- Node.js 18+
- Python 3.9+
- Git
- API 密鑰（可選）
```

### 快速安裝（推薦）

最簡單的方式：

```bash
# 一行命令安裝
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# 安裝完成後，運行
hermes

# 進入交互式聊天
```

### 手動安裝（完全控制）

如果想要更多控制，進行手動安裝：

```bash
# 1. 克隆倉庫
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent

# 2. 安裝依賴
npm install
pip install -r requirements.txt

# 3. 配置系統
hermes setup

# 4. 啟動
hermes start
```

### Docker 安裝（推薦用於服務器）

```bash
# 構建 Docker 映像
docker build -t hermes-agent .

# 運行容器
docker run -it \
  -v ~/.hermes:/root/.hermes \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  hermes-agent

# 容器內運行
hermes
```

---

## 配置和設置

### 初始化設置

```bash
hermes setup
```

這個命令會引導你配置：

```
1. 選擇 LLM 提供商
   □ Nous Portal（推薦，Hermes 官方）
   □ OpenRouter（200+ 模型）
   □ OpenAI
   □ 自定義端點

2. 輸入 API 密鑰

3. 選擇默認模型
   - hermes-3-70b（推薦）
   - hermes-3-8b（輕量）
   - mixtral-8x7b
   - 自定義

4. 配置存儲位置
   ~/.hermes/data/  # 知識庫和技能
   ~/.hermes/config/ # 配置文件

5. 選擇平台集成
   □ Telegram
   □ Discord
   □ Slack
   □ 終端（默認啟用）
```

### 配置文件結構

```yaml
# ~/.hermes/config/hermes.yml
system:
  name: "Hermes"
  version: "1.0"
  data_path: "/home/user/.hermes/data"

llm:
  provider: "openrouter"  # 或 nous, openai, custom
  model: "nousresearch/hermes-3-70b-instruct"
  api_key: "${OPENROUTER_API_KEY}"
  temperature: 0.7
  max_tokens: 4096

memory:
  database: "fts5"  # 全文搜索
  retention_days: 365  # 保存 1 年
  search_limit: 10   # 每次搜索最多 10 條

skills:
  auto_create: true    # 自動創建技能
  persistence: true    # 持久化技能
  max_skills: 1000
  skill_dir: "./skills"

platforms:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
  
  discord:
    enabled: false
    bot_token: "${DISCORD_BOT_TOKEN}"
  
  slack:
    enabled: false
    bot_token: "${SLACK_BOT_TOKEN}"

scheduling:
  enabled: true        # 啟用 cron 任務
  timezone: "Asia/Taipei"
```

---

## 使用方式

### 基本交互

```bash
# 啟動終端界面
hermes

# 在提示符下輸入
> 幫我分析一下 Python 代碼的性能瓶頸

# Hermes 會：
# 1. 理解你的需求
# 2. 搜索過往相關對話
# 3. 調用相關技能
# 4. 給出分析結果
# 5. 自動存儲此對話
```

### 查看技能

```bash
# 列出所有技能
hermes skills list

# 輸出：
# Skill: data_analysis (v2)
#   - Created: 2024-01-15
#   - Used: 23 times
#   - Success rate: 95%
# 
# Skill: web_scraping (v4)
#   - Created: 2024-01-10
#   - Used: 142 times
#   - Success rate: 89%
```

### 設置自動任務

```bash
# 設置每日總結任務
hermes schedule add "每天上午 9 點生成昨日總結"

# 設置週期性任務
hermes schedule add "每週五檢查項目進度"

# 查看已設置的任務
hermes schedule list
```

### 搜索過往對話

```bash
# 搜索包含「Python」的對話
hermes search "Python"

# 高級搜索
hermes search --type "skill" --date "last 7 days"

# 輸出對話上下文便於復用
```

---

## 實戰例子

### 例子 1：自動生成周報

```
對話 1：
> 幫我總結這周的工作

Hermes 會記住你的風格和需求，
第一次可能花 2 分鐘

之後每週：
> 周報

自動使用創建的「周報技能」
直接生成包含關鍵信息的周報
耗時 15 秒
```

### 例子 2：代碼代理

```
> 我的 Python 腳本有 bug，幫我修

Hermes 會：
1. 請你提供代碼
2. 分析可能的問題
3. 提出修復方案
4. 創建「Debug Python 代碼」技能

下次類似問題：
> 這段代碼有問題 [粘貼代碼]

直接調用已有技能，秒速返回結果
```

### 例子 3：團隊協作

```
通過 Discord/Slack：
@hermes 統計這月的銷售數據

Hermes 會：
1. 訪問數據源（如已連接）
2. 進行計算
3. 生成報告
4. 發送到頻道

團隊成員可以在聊天中與 Hermes 互動
共享同一套技能和記憶
```

---

## 模型選擇指南

Hermes 支持多種模型，選擇時考慮：

| 模型 | 速度 | 質量 | 成本 | 推薦場景 |
|------|------|------|------|---------|
| Hermes-3-8B | 🚀🚀🚀 | ⭐⭐⭐ | 💰 | 本地部署、快速推理 |
| Hermes-3-70B | 🚀🚀 | ⭐⭐⭐⭐⭐ | 💰💰 | 複雜任務、高精度 |
| Mixtral-8x7B | 🚀🚀 | ⭐⭐⭐⭐ | 💰 | 均衡選擇 |
| GPT-4 | 🚀 | ⭐⭐⭐⭐⭐ | 💰💰💰 | 最高精度 |

**推薦**：開始用 Hermes-3-8B（輕量），需要更好結果時升級到 70B。

---

## 常見問題

### Q: 數據安全嗎？
**A**: 完全安全。數據存儲在本地 `~/.hermes/` 目錄，永遠不上傳到遠程伺服器（除非你選擇雲同步）。

### Q: 可以離線運行嗎？
**A**: 可以。推理可以本地進行（使用 8B 模型），但調用 API 模型需要網絡。

### Q: 技能可以分享嗎？
**A**: 可以。技能存儲為文本文件，可以通過 Git 分享或導出。

### Q: 如何清除記憶？
**A**: 
```bash
hermes reset              # 清除所有記憶和技能
hermes reset --skills     # 只清除技能
hermes reset --memory     # 只清除對話記憶
```

### Q: 支持自定義 Agent 嗎？
**A**: 支持。可以通過編寫 Python 模組擴展功能。

---

## 進階功能

### 創建自定義技能

```python
# skills/my_skill.py
from hermes import Skill

class MyAnalysisSKill(Skill):
    name = "custom_analysis"
    description = "我的自定義分析技能"
    
    def execute(self, input_data):
        # 你的邏輯
        result = analyze(input_data)
        return result

# Hermes 會自動發現和註冊此技能
```

### 連接數據源

```yaml
# 配置數據源
data_sources:
  - name: "company_db"
    type: "postgresql"
    connection: "postgresql://user:pass@localhost/db"
    
  - name: "api_endpoint"
    type: "rest"
    url: "https://api.example.com"
    auth: "bearer ${API_TOKEN}"

# 在對話中使用
> 從公司數據庫查詢今月銷售額

Hermes 會自動連接並查詢
```

### MCP 伺服器集成

```
Hermes 支持 Model Context Protocol
可以連接任何 MCP 伺服器

示例：
- Claude 工具
- LangChain 工具
- 自定義工具
```

---

## 部署選項

### 選項 1：本地開發機

```bash
# 簡單安裝，適合個人使用
hermes setup
hermes start
```

### 選項 2：VPS 服務器

```bash
# Docker 部署
docker run -d \
  -v hermes_data:/root/.hermes \
  -e OPENROUTER_API_KEY=$KEY \
  hermes-agent
```

### 選項 3：無服務器（Serverless）

Hermes 支持在 Modal、Daytona 等平台運行。

### 選項 4：GPU 集群

```yaml
# 配置 GPU 加速
inference:
  device: "cuda"  # 使用 GPU
  batch_size: 32
  quantization: "4bit"  # 內存優化
```

---

## 總結

Hermes Agent 代表了 AI 系統的未來方向：
- ✅ 自主學習和改進
- ✅ 隱私和本地優先
- ✅ 開源和可擴展
- ✅ 多平台訪問
- ✅ 企業級功能

無論你是開發者想要強大的 AI 工具，還是非技術人員想要自動化日常任務，Hermes Agent 都提供了一個強大且易用的解決方案。

**現在就開始探索 Hermes Agent 的無限可能吧！**
