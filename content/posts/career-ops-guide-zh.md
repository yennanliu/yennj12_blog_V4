---
title: "Career-Ops 完全使用指南：AI 驅動的智能求職系統"
date: 2026-04-11T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "career", "AI", "job-search"]
tags: ["Career-Ops", "求職", "AI", "應聘工具", "職業發展", "自動化"]
summary: "深入講解 Career-Ops，一個由 AI 驅動的求職系統，幫助你在數百個工作機會中找到最適合的職位。涵蓋安裝、配置、使用技巧和策略，助力你高效求職。"
readTime: "40 min"
---

傳統求職方式低效且被動：你提交簡歷，公司用 AI 篩選你。Career-Ops 反轉了這個過程：**你用 AI 來評估公司**。這個開源工具由一位求職者創建，他用它評估了 740+ 個職位，最終成功獲得了 Head of Applied AI 角色。本文詳細講解如何使用 Career-Ops。

---

## 什麼是 Career-Ops？

### 核心概念

```
傳統求職：
隨處發送簡歷 → 等待公司回應 → 被動篩選 → 低成功率

Career-Ops：
自動發現職位 → AI 評估匹配度 → 優先級排序 → 主動出擊

特點：
✓ 智能匹配（基於你的背景和目標）
✓ 批量評估（同時評估數百個職位）
✓ 自動應聘（可選）
✓ 面試準備（自動生成 STAR 故事）
✓ 簡歷優化（為每個職位定製）
✓ 隱私優先（完全本地運行）
```

### 數據

```
創始人 Santiago 的真實數據：
- 評估職位數：740+
- 成功獲聘：是（Head of Applied AI）
- 公司包括：Anthropic, OpenAI, Retool, n8n 等
- 平均評估時間：每個職位 30-60 秒
- 節省時間：~400 小時（與傳統方式比較）
```

---

## Career-Ops 的核心功能

### 1. 智能職位篩選

```
傳統方式：
看職位標題 → 是否感興趣？ → 申請或跳過

Career-Ops：
職位描述 → AI 評估 10 個維度 → 打分 → 優先級排序

評估維度：
┌─ 角色適配度（Role Fit）
├─ 公司規模（Company Size）
├─ 薪資範圍（Compensation）
├─ 地點/遠程（Location/Remote）
├─ 成長機會（Growth Opportunity）
├─ 工作環境（Work Environment）
├─ 技術棧（Tech Stack）
├─ 領導風格（Leadership Style）
├─ 公司文化（Company Culture）
└─ 個人興趣匹配（Personal Interest Match）

最終分數：A-F 等級
```

### 2. 自動簡歷優化

```
傳統方式：
一份通用簡歷 → 投給所有公司 → ATS 篩選失敗

Career-Ops：
職位描述 → 提取關鍵詞 → 為該職位定製簡歷
  ├─ 調整措辭
  ├─ 高亮相關經驗
  ├─ 優化 ATS 關鍵詞
  ├─ 生成 PDF（ATS 友好格式）
  └─ 存儲版本歷史

結果：ATS 通過率提升 3-5 倍
```

### 3. 職位源自動發現

```
預配置的 45+ 公司和 19 個職位板：

科技巨頭：
- Google, Apple, Meta, Amazon, Microsoft
- OpenAI, Anthropic, xAI
- Stripe, Notion, Figma

初創獨角獸：
- Retool, n8n, Loom, Airtable
- Wellfound (YC 職位)

職位板：
- LinkedIn
- AngelList (Wellfound)
- 45 個公司的官網職位頁面
```

### 4. 批量評估和 A-F 打分

```
自動評估流程：

職位發現 → 
  ↓
提取職位信息 →
  ↓
AI 評估（基於你的背景）→
  ↓
分配 A-F 等級 →
  ↓
自動計算匹配度百分比 →
  ↓
優先級隊列

結果示例：
A 級：80-100% （強烈推薦）
B 級：60-79%  （值得關注）
C 級：40-59%  （可能有趣）
D 級：20-39%  （備選）
F 級：<20%   （不推薦）
```

### 5. 面試準備

```
Career-Ops 自動從所有評估中收集 STAR 故事：

STAR = Situation, Task, Action, Result

系統會跟踪你在評估中提到的：
✓ 克服的技術挑戰
✓ 領導力案例
✓ 創新舉例
✓ 失敗和學習
✓ 影響指標

面試時自動提示相關故事
```

### 6. 人類在環（Human-in-the-loop）

```
重要特性：
❌ 不自動提交申請
✅ AI 推薦
✅ 你決定

每一步都有人工檢查點：
職位發現 → [你確認要評估]
  ↓
AI 評估完成 → [你查看評分]
  ↓
簡歷生成 → [你審核後提交]
  ↓
應聘決定 → [由你控制]
```

---

## 安裝和設置

### 前置要求

```
軟件：
- Node.js 18+
- Python 3.9+
- Git
- Claude API 密鑰（Anthropic）

硬件：
- 任何現代電腦
- 500MB 磁盤空間
- 網絡連接（用於職位抓取）

時間投入：
- 首次設置：30 分鐘
- 添加經歷信息：1-2 小時
```

### 安裝步驟

```bash
# 1. 克隆倉庫
git clone https://github.com/santifer/career-ops.git
cd career-ops

# 2. 安裝 Node.js 依賴
npm install

# 3. 安裝 Python 依賴（用於數據處理）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. 配置環境變數
cp .env.example .env

# 編輯 .env 文件
cat > .env << 'EOF'
ANTHROPIC_API_KEY=your_claude_api_key_here
EOF

# 5. 驗證安裝
npm run test

# 6. 啟動應用
npm start
```

### 配置文件

Career-Ops 使用 YAML 配置文件：

```yaml
# config/profile.yml
# 你的背景信息

personal:
  name: "張三"
  email: "zhangsan@example.com"
  phone: "+86 1234567890"
  location: "北京"

background:
  current_title: "高級軟體工程師"
  current_company: "某科技公司"
  years_experience: 7
  
  education:
    - degree: "計算機科學學士"
      school: "清華大學"
      year: 2019

  skills:
    - Python (Expert)
    - JavaScript (Expert)
    - AWS (Intermediate)
    - React (Expert)
    - Machine Learning (Intermediate)

  languages:
    - Chinese (Native)
    - English (Fluent)

career_goals:
  target_titles:
    - "AI Engineer"
    - "Machine Learning Engineer"
    - "Applied AI Engineer"
  
  desired_companies:
    - "Anthropic"
    - "OpenAI"
    - "Google DeepMind"
  
  salary_expectation: "300k-500k USD"
  
  remote_preference: "fully_remote"
  
  values:
    - Impact
    - Learning
    - Autonomy

preferences:
  company_size: "any"  # startup, scale-up, enterprise, any
  industry: "AI"       # tech, fintech, healthcare, etc.
  
  # 不感興趣的方面
  deal_breakers:
    - "Frequent on-site requirements"
    - "Micromanagement culture"
```

### CV/簡歷配置

```yaml
# config/resume_template.yml
# 你的簡歷基礎信息

contact:
  email: zhangsan@example.com
  phone: +86 1234567890
  linkedin: linkedin.com/in/zhangsan
  github: github.com/zhangsan

summary: |
  7 年軟體工程經驗，專注於 AI 和機器學習。
  領導過 10+ 個項目，在數據處理和模型優化方面有深度專業知識。

experience:
  - title: "高級軟體工程師"
    company: "某科技公司"
    duration: "2021-現在"
    achievements:
      - "設計並實現機器學習管道，將推理速度提升 5 倍"
      - "領導 5 人團隊，成功交付 3 個核心項目"
      - "優化數據處理流程，節省成本 40%"
  
  - title: "軟體工程師"
    company: "另一家公司"
    duration: "2019-2021"
    achievements:
      - "開發 Python 後端系統，支持 100 萬日活用戶"
      - "實現自動化測試，測試覆蓋率達 85%"

education:
  - degree: "計算機科學學士"
    institution: "清華大學"
    year: 2019
    gpa: 3.8/4.0

certifications:
  - "AWS Solutions Architect Associate"
  - "Google Cloud Associate Cloud Engineer"

projects:
  - title: "開源 ML 框架"
    description: "2000+ stars on GitHub"
    link: "github.com/zhangsan/..."
```

---

## 使用工作流

### 步驟 1：發現職位

```bash
# 運行職位發現爬蟲
npm run discover

# 輸出：
# ✓ Searching Anthropic careers... found 5 positions
# ✓ Searching OpenAI jobs... found 8 positions
# ✓ Searching Retool careers... found 3 positions
# ...
# Total found: 127 new positions
```

Career-Ops 會自動檢查預配置的 45+ 公司和 19 個職位板。

### 步驟 2：評估職位

```bash
# 評估所有新發現的職位
npm run evaluate

# 對話式評估（如果 AI 有疑問）
# AI: "你對這個職位的地點要求是？"
# 你: "完全遠程優先"

# 進度條：
# Evaluating positions... [████████████░░░░░░░░] 60%
```

每個職位會被評估為 A-F 等級。

### 步驟 3：查看儀表板

```bash
# 啟動 Web 儀表板
npm run dashboard

# 在瀏覽器打開 http://localhost:3000
```

儀表板顯示：

```
┌─────────────────────────────────────────────┐
│ Career-Ops Dashboard                        │
├─────────────────────────────────────────────┤
│ 總職位數：247                                  │
│ 已評估：127                                   │
│ A 級（85%+）：12 個 ⭐⭐⭐                   │
│ B 級（60-85%）：31 個 ⭐⭐                   │
│ C 級（40-60%）：45 個 ⭐                     │
│ D-F 級：39 個                                │
├─────────────────────────────────────────────┤
│ 按公司篩選：                                  │
│ ☑ Anthropic (5) ☑ OpenAI (8) ☑ Google (3)  │
│ ☑ Stripe (2) ☑ Retool (3) ...               │
└─────────────────────────────────────────────┘
```

### 步驟 4：優化簡歷

```bash
# 為 A 級職位生成優化的簡歷
npm run generate-resumes --grade A

# 輸出：
# ✓ Anthropic - AI Safety Research - resume.pdf
# ✓ OpenAI - Applied AI Engineer - resume.pdf
# ✓ Google DeepMind - ML Engineer - resume.pdf
# ...
# Generated 12 customized resumes
```

每份簡歷會：
- 調整措辭以匹配職位描述
- 突出相關經驗
- 優化 ATS 關鍵詞
- 使用 ATS 友好的格式
- 自動添加 LinkedIn/GitHub 鏈接

### 步驟 5：準備應聘和面試

```bash
# 查看針對特定職位的建議
npm run prepare Anthropic "AI Safety Research"

# 輸出：
# 職位匹配分析：
# ─────────────────
# 期望技能：
#   ☑ Python - 你有 Expert
#   ☑ Machine Learning - 你有 Intermediate
#   ☐ TensorFlow - 你缺少 this
#   ☑ Research - 你有相關經驗

# 推薦的 STAR 故事：
# 1. "時我領導實現 ML 管道優化..." (Story ID: 42)
# 2. "當我負責開源項目..." (Story ID: 15)

# 預期薪資：
# 職位: $300k - $450k base
# 你的目標: $300k - $500k
# 匹配度: ✓ Good

# 文化適配：
# 注重：研究、創新、自主
# 你的背景：✓ 對應所有價值觀
```

---

## 進階功能

### 1. 批量應聘（可選）

```yaml
# config/application_settings.yml
auto_apply:
  enabled: false  # 默認禁用，保護隱私
  # 如果啟用，設置規則：
  apply_rules:
    - condition: "grade == A"
      action: "apply_immediately"
    - condition: "grade == B AND remote == true"
      action: "apply_immediately"
    - condition: "grade <= C"
      action: "manual_review_required"
```

### 2. 薪資談判分析

```bash
npm run salary-analysis

# 輸出職位的薪資範圍和數據
# Anthropic AI Safety Researcher:
# - Base: $300k - $400k
# - Stock: $500k - $1M (4 years)
# - Bonus: 10-20%
# - Your target: $350k-$500k ✓ Aligned
```

### 3. 面試故事庫

```bash
# 查看面試故事
npm run stories

# 交互式搜索：
# > find stories about "leadership"
#   
#   Story 1: Led 5-person team...
#   Story 2: Mentored 3 junior engineers...
#   Story 3: Made difficult decision to refactor...

# 編輯故事
npm run edit-story 42
```

### 4. 對標分析

```bash
npm run benchmark

# 比較你和職位要求的對標：
#
# 技能對標：
# Python: 你 Expert vs 要求 Expert ✓
# ML: 你 Intermediate vs 要求 Advanced ⚠
# AWS: 你 Beginner vs 要求 Intermediate ✗
#
# 經驗對標：
# 總經驗：你 7 年 vs 要求 5-8 年 ✓
# 領導經驗：你 有 vs 要求 有 ✓
# 初創經驗：你 無 vs 要求 優先 ⚠

# 建議：
# - 強化 AWS 技能（3 個職位要求）
# - 突出領導經驗（最有說服力）
```

---

## 最佳實踐

### 1. 信息的完整性

```
你提供的信息越詳細，AI 評估越準確：

✅ 好：
  "7 年軟體工程經驗，3 年領導，在 ML 和數據工程方面深厚"

❌ 不好：
  "軟體工程師"

✅ 好：
  skills:
    - Python (7 years, Expert)
    - Machine Learning (3 years, Advanced)
    - AWS (2 years, Intermediate)

❌ 不好：
  skills:
    - Python
    - ML
```

### 2. 定期更新設置

```bash
# 每週更新一次偏好
npm run update-profile

# 添加新的項目或成就
npm run add-achievement "Led migration to microservices..."

# 更新薪資期望
npm run update-salary "350k-550k"

# 系統會根據新信息重新評估所有職位
```

### 3. 優先級管理

```bash
# 關注 A 級職位
npm run filter --grade A

# 優先應聘 A 級且遠程的職位
npm run filter --grade A --remote true

# 按公司優先級排序
npm run sort-by company_preference
```

### 4. 跟踪應聘

```bash
# 記錄應聘信息
npm run track-application

# 交互式添加：
# 公司：Anthropic
# 職位：AI Safety Researcher
# 申請日期：2024-01-15
# 狀態：Applied
# 備註：強烈感興趣
```

---

## 統計和分析

### 查看進度

```bash
npm run stats

# 輸出：
# ════════════════════════════════════════
# Career-Ops Statistics
# ════════════════════════════════════════
#
# Opportunities Discovered: 247
# Evaluated: 127 (51%)
# Applications Sent: 18
#
# Grade Distribution:
#   A: 12 (9.4%)
#   B: 31 (24.4%)
#   C: 45 (35.4%)
#   D: 28 (22.0%)
#   F: 11 (8.7%)
#
# Top Companies:
#   1. Anthropic (5 positions)
#   2. OpenAI (8 positions)
#   3. Google (6 positions)
#   4. Stripe (4 positions)
#   5. Retool (3 positions)
#
# Application Status:
#   Applied: 18
#   In Progress: 3
#   Interviews Scheduled: 2
#   Offers: 0
#   Rejected: 5
#
# Weeks Active: 4
# Avg Applications per Week: 4.5
# Current Success Rate: 11.1% (2/18)
```

---

## 數據隱私和安全

### 本地優先架構

```
Career-Ops 的隱私設計：

✓ 所有數據存儲本地（~/.career-ops/）
✓ 簡歷存儲加密
✓ API 密鑰不會被記錄
✓ 不追蹤用戶行為
✓ 不與第三方共享數據
✓ 開源代碼，可自主審計

只有必要的網絡請求：
- Claude API（職位評估）
- 職位頁面抓取（公司頁面、LinkedIn 等）
```

### 安全最佳實踐

```bash
# 1. 保護你的 API 密鑰
# 不要提交 .env 文件到 Git
echo ".env" >> .gitignore

# 2. 定期備份
cp -r ~/.career-ops ~/backups/career-ops-$(date +%Y%m%d)

# 3. 審計日誌
cat ~/.career-ops/logs/access.log

# 4. 安全刪除敏感數據
npm run delete-old-resumes --older-than 90days
```

---

## 與其他工具集成

### 連接到 LinkedIn

```python
# 可選：自動導入 LinkedIn 信息
python scripts/import_linkedin.py

# 需要：
# - LinkedIn 個人資料 URL
# - 瀏覽器自動化（Playwright）
```

### 導出到 Notion/Google Sheets

```bash
# 導出職位列表
npm run export --format csv

# 導出簡歷跟踪
npm run export-applications --format sheets

# 結果：applications.csv（可導入 Excel/Sheets）
```

---

## 性能指標（基於創始人數據）

Santiago 的實際結果：

```
評估前：
- 投遞 100+ 職位
- 成功率 5-10%
- 時間投入：40+ 小時

使用 Career-Ops：
- 評估 740+ 職位
- 只申請優質職位（A/B 級）
- 成功率：22%（18/82）
- 時間投入：~40 小時（自動化節省時間）
- 最終成功：Head of Applied AI 角色 @Anthropic

關鍵洞察：
✓ 質量 > 數量（專注 A/B 級職位）
✓ 個性化簡歷提升 3-5 倍通過率
✓ AI 評估減少無謂申請
✓ 面試準備更充分
```

---

## 總結

Career-Ops 改變了求職方式：

**傳統求職缺陷**：
❌ 廣撒網，低成功率
❌ 簡歷通用，ATS 篩選率低
❌ 被動等待
❌ 信息不對稱

**Career-Ops 優勢**：
✅ AI 智能評估，專注優質機會
✅ 自動優化簡歷，ATS 友好
✅ 主動出擊，數據驅動
✅ 充分準備，面試有針對性

**使用 Career-Ops 的你**：
- 評估 100+ 職位（而不是盲目投遞）
- 成功率提升 2-3 倍
- 節省 30-50% 的時間
- 找到更適合的職位
- 更有信心談判薪資

**立即開始**：
```bash
git clone https://github.com/santifer/career-ops.git
cd career-ops
npm install
npm start
```

祝你求職成功！🚀
