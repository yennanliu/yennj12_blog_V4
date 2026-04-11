# NVIDIA Blog Post Automation

自動從 NVIDIA 開發者博客生成繁體中文技術文章的 GitHub Action。

## 功能特性

✅ **日常自動化**：每天自動從 NVIDIA 博客發現新文章
✅ **智能去重**：避免重複發佈相同的文章
✅ **繁體中文**：使用 OpenAI GPT-4 翻譯和改寫為高質量繁體中文
✅ **自動提交**：自動提交和推送到 Git 倉庫
✅ **格式標準**：生成的文章符合既有博客格式
✅ **可配置**：支持自定義觸發時間、模型選擇等

## 設置步驟

### 1. 配置 GitHub Secrets

在 GitHub 倉庫設置中，添加以下 secret：

**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名稱 | 值 | 說明 |
|-----------|-----|------|
| `OPENAI_API_KEY` | `sk-...` | OpenAI API 密鑰（來自 https://platform.openai.com/api-keys） |

### 2. 驗證工作流

工作流文件已在 `.github/workflows/nvidia-blog-daily.yml`

### 3. 選項配置

可以在工作流文件中自定義：

```yaml
# 修改觸發時間（Cron 格式）
  schedule:
    - cron: '0 9 * * *'  # 每天 UTC 9:00 (台北時間 17:00)

# 修改 OpenAI 模型
OPENAI_MODEL = "gpt-4-turbo"  # 或 "gpt-4", "gpt-3.5-turbo"
```

## 工作原理

```
GitHub Action Trigger (Daily)
    ↓
Fetch NVIDIA Blog RSS
    ↓
Extract Latest Article
    ↓
Check for Duplicates
    ├─ Already Posted? → Exit
    └─ New Article? → Continue
         ↓
Generate with OpenAI
    ├─ Summarize content
    ├─ Translate to Traditional Chinese
    └─ Format as blog post
    ↓
Save to content/posts/
    ↓
Auto Commit & Push
    ↓
Optional: Create Pull Request
```

## 文件結構

```
.github/
├── workflows/
│   └── nvidia-blog-daily.yml       # GitHub Action 工作流
└── nvidia_blog_metadata.json       # 已發佈文章記錄（自動生成）

scripts/
└── generate_nvidia_blog.py         # 核心生成腳本

content/posts/
└── nvidia-*.md                     # 自動生成的博客文章
```

## 手動觸發

可以在 GitHub 倉庫的 Actions 標籤手動觸發：

1. 點擊 "Actions"
2. 選擇 "Daily NVIDIA Blog Post Generator"
3. 點擊 "Run workflow"

## 已發佈文章追蹤

系統自動在 `.github/nvidia_blog_metadata.json` 中記錄已發佈的文章：

```json
{
  "posted_articles": [
    {
      "url": "https://developer.nvidia.com/blog/...",
      "title": "Article Title",
      "posted_date": "2024-01-15T12:00:00"
    }
  ]
}
```

## 故障排除

### 問題 1：工作流不運行

**檢查清單**：
- ✓ GitHub Secrets 已正確配置
- ✓ 工作流文件在 `.github/workflows/` 目錄
- ✓ Workflow 權限設置正確（Settings → Actions → General）

### 問題 2：OpenAI API 錯誤

**可能原因**：
- API 密鑰無效或已過期
- 賬戶余額不足
- API 速率限制

**解決方案**：
```bash
# 驗證 API 密鑰
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 問題 3：文章未發佈

檢查工作流日誌：
1. 進入 GitHub 倉庫的 Actions 標籤
2. 選擇最近的工作流運行
3. 查看詳細日誌

## 成本估算

| 操作 | 平均 Token | 平均成本 |
|-----|---------|--------|
| 單篇文章生成 | ~2,000 | ~$0.10 (GPT-4-Turbo) |
| 每日運行 | ~2,000 | ~$0.10 |
| 每月運行 | ~60,000 | ~$3 |

**注意**：使用 GPT-3.5-Turbo 可以降低成本 90%，質量略低。

## 自定義

### 修改發佈時間

編輯 `.github/workflows/nvidia-blog-daily.yml`：

```yaml
schedule:
  - cron: '0 9 * * *'  # 現在：每天 9:00 UTC
  # 改為：每週五 10:00 UTC
  - cron: '0 10 * * 5'
```

### 修改生成邏輯

編輯 `scripts/generate_nvidia_blog.py`：

```python
# 修改 OpenAI 模型
OPENAI_MODEL = "gpt-3.5-turbo"  # 更便宜

# 修改博客內容長度
max_tokens=3000  # 改為 2000 以加快速度

# 修改生成溫度（0=確定性，1=創意）
temperature=0.5  # 改為更保守
```

### 添加自定義標籤

編輯提示詞中的 categories 和 tags：

```python
"categories": ["all", "NVIDIA", "技術", "AI"]
"tags": ["NVIDIA", "AI", "加速計算"]
```

## 限制和注意事項

⚠️ **已知限制**：

1. **RSS 延遲**：可能不是即時更新
2. **內容質量**：翻譯質量取決於原文清晰度
3. **語境**：AI 可能無法完全理解專業術語
4. **成本**：每篇文章產生 OpenAI API 成本

✅ **最佳實踐**：

1. 定期審查自動生成的內容
2. 在發佈前檢查技術準確性
3. 監控 OpenAI 使用成本
4. 保持 API 密鑰安全
5. 定期更新工作流依賴

## 禁用自動化

### 臨時禁用

註釋 `.github/workflows/nvidia-blog-daily.yml` 中的 `schedule` 部分：

```yaml
# on:
#   schedule:
#     - cron: '0 9 * * *'
  workflow_dispatch:  # 保留手動觸發
```

### 永久刪除

刪除文件：
```bash
rm .github/workflows/nvidia-blog-daily.yml
```

## 開發和測試

### 本地測試

```bash
# 安裝依賴
pip install requests beautifulsoup4 feedparser openai pyyaml

# 設置環境變數
export OPENAI_API_KEY="sk-..."

# 運行腳本
python scripts/generate_nvidia_blog.py
```

### 測試不同模型

```python
# 在 scripts/generate_nvidia_blog.py 中修改
OPENAI_MODEL = "gpt-3.5-turbo"  # 快速測試

# 或在運行時設置環境變數
export OPENAI_MODEL="gpt-4"
```

### 清除去重記錄

```bash
# 移除已發佈記錄以重新發佈相同文章
rm .github/nvidia_blog_metadata.json
```

## 與其他工具集成

### 發送通知

在工作流中添加通知步驟：

```yaml
- name: Send Slack notification
  if: success()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {
        "text": "✅ New NVIDIA blog post published!"
      }
```

### 發送郵件

```yaml
- name: Send email notification
  if: success()
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: ${{ secrets.EMAIL_SERVER }}
    server_port: ${{ secrets.EMAIL_PORT }}
    username: ${{ secrets.EMAIL_USERNAME }}
    password: ${{ secrets.EMAIL_PASSWORD }}
    subject: "New NVIDIA Blog Post Published"
    to: "you@example.com"
```

## 常見問題

**Q: 可以使用不同的博客源嗎？**
A: 可以。修改 `NVIDIA_BLOG_RSS` 和 `NVIDIA_BLOG_URL` 常數即可支持其他 RSS 源。

**Q: 如何改進翻譯質量？**
A: 調整 OpenAI 提示詞，或在工作流中添加人工審核步驟。

**Q: 成本太高怎麼辦？**
A: 改用 GPT-3.5-Turbo 或降低發佈頻率（例如每週而非每日）。

**Q: 可以自動發佈到社交媒體嗎？**
A: 可以，在工作流中添加額外的 Action 步驟。

## 許可證

MIT License - 可自由使用和修改

## 支持

如遇到問題，請：
1. 檢查工作流日誌
2. 驗證環境變數設置
3. 測試 OpenAI API 連接
4. 查看本文檔的故障排除部分

## 更新日誌

### v1.0 (2024-01-15)
- 初始版本
- 支持 NVIDIA 博客 RSS 源
- 使用 OpenAI GPT-4
- 自動去重和提交
