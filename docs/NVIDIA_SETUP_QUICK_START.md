# NVIDIA 博客自動化快速開始指南

只需 5 分鐘設置每日自動從 NVIDIA 博客生成繁體中文技術文章。

## 快速設置（3 步）

### 1️⃣ 獲取 OpenAI API 密鑰

1. 訪問 https://platform.openai.com/api-keys
2. 點擊 "Create new secret key"
3. 複製密鑰（開頭為 `sk-`）

**成本提示**：
- GPT-4 Turbo: ~$0.10/篇文章
- GPT-3.5 Turbo: ~$0.01/篇文章（推薦）

### 2️⃣ 設置 GitHub Secret

1. 進入你的倉庫
2. **Settings** → **Secrets and variables** → **Actions**
3. 點擊 **New repository secret**
4. 名稱：`OPENAI_API_KEY`
5. 值：粘貼你的 API 密鑰
6. 點擊 **Add secret**

### 3️⃣ 啟用工作流

工作流已自動配置，會在：
- ⏰ 每天 UTC 9:00 (台北時間 17:00) 運行
- 🖱️ 或手動觸發（Actions 標籤）

✅ **完成！** 

現在系統會每天自動發佈新的 NVIDIA 博客文章。

---

## 驗證設置

### 檢查工作流是否運行

1. 進入 **Actions** 標籤
2. 選擇 **"Daily NVIDIA Blog Post Generator"**
3. 查看最近的運行日誌

### 常見狀態

| 狀態 | 含義 | 操作 |
|-----|------|------|
| ✅ passed | 成功發佈 | 檢查新文章 |
| ❌ failed | 失敗 | 查看日誌排查 |
| ⏭️ skipped | 跳過（重複） | 正常，無需操作 |

### 查看生成的文章

新文章自動保存到：`content/posts/nvidia-*.md`

---

## 手動觸發工作流

如果想立即測試而不等待每日運行：

1. 進入 **Actions**
2. 選擇 **"Daily NVIDIA Blog Post Generator"**
3. 點擊 **"Run workflow"**
4. 選擇 **main** 分支
5. 點擊 **"Run workflow"**

5 分鐘內會生成新文章。

---

## 常見問題

### ❓ Q: 文章沒有生成？

**檢查清單**：
- [ ] OpenAI API 密鑰正確設置
- [ ] API 密鑰有效（未過期）
- [ ] 賬戶有足夠額度
- [ ] 工作流文件存在：`.github/workflows/nvidia-blog-daily.yml`

**查看日誌**：
1. Actions → 最近運行 → 點擊進入
2. 查看 "Generate blog post from NVIDIA" 步驟的錯誤信息

### ❓ Q: 成本太高？

**解決方案**：
1. 編輯 `scripts/generate_nvidia_blog.py`
2. 改為 `OPENAI_MODEL = "gpt-3.5-turbo"`
3. 成本降低 90%，質量略低

### ❓ Q: 可以改變運行時間？

**是的**：
1. 編輯 `.github/workflows/nvidia-blog-daily.yml`
2. 修改 `cron: '0 9 * * *'`
3. 例如：`'0 17 * * *'` = 每天 17:00 UTC

[Cron 表達式幫助](https://crontab.guru/)

### ❓ Q: 如何禁用自動化？

**臨時禁用**：
在工作流文件中註釋 schedule 部分：
```yaml
# schedule:
#   - cron: '0 9 * * *'
```

**永久刪除**：
```bash
rm .github/workflows/nvidia-blog-daily.yml
```

### ❓ Q: 翻譯質量不好？

編輯 `scripts/generate_nvidia_blog.py` 的提示詞部分，添加更多指導。

---

## 了解更多

詳細文檔：[NVIDIA_BLOG_AUTOMATION.md](./NVIDIA_BLOG_AUTOMATION.md)

包含：
- 完整配置指南
- 故障排除
- 高級自定義
- 成本優化
- 集成選項

---

## 支持

遇到問題？

1. **查看工作流日誌**（最快解決）
2. **檢查 OpenAI API 狀態**：https://status.openai.com/
3. **驗證 API 密鑰**：
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer sk-..."
   ```

---

## 提示和技巧

### 🎯 如何選擇模型？

| 模型 | 速度 | 質量 | 成本 |
|------|------|------|------|
| gpt-4-turbo | 中等 | 最高 | $0.01-0.03/篇 |
| gpt-4 | 慢 | 最高 | $0.03-0.06/篇 |
| gpt-3.5-turbo | 快 | 高 | $0.001-0.003/篇 |

**推薦**：gpt-3.5-turbo（成本-質量最優）

### 📊 監控成本

每月預期成本（基於每日運行）：
- gpt-4-turbo: ~$3/月
- gpt-3.5-turbo: ~$0.03/月

在 OpenAI 儀表板查看使用情況：https://platform.openai.com/usage

### 🔒 安全最佳實踐

- ✅ API 密鑰存儲在 GitHub Secrets
- ✅ 從不在代碼中硬編碼密鑰
- ✅ 定期輪換 API 密鑰
- ✅ 監控異常使用

---

**設置完成！祝你享受自動化博客！** 🚀
