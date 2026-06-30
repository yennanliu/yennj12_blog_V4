---
title: "finance_data 是怎麼運作的:用 Cron + LLM 全自動生成股票研究報告"
date: 2026-06-30T12:00:00+08:00
draft: false
description: "finance_data 是一個全自動的 AI 投資研究平台:每天靠 GitHub Actions cron 定時觸發,用 yfinance 抓市場數據、爬 Finviz/StockAnalysis/Roic.ai 補齊基本面,再餵給 Claude / OpenAI / Gemini 生成繁體中文研究報告,最後由 MkDocs 建置部署。本篇完整拆解這條 pipeline 的每一個環節。"
categories: ["engineering", "ai", "all"]
tags: ["LLM", "Automation", "GitHub Actions", "Cron", "yfinance", "Finance", "RAG", "Claude", "Data Pipeline", "MkDocs"]
authors: ["yen"]
readTime: "17 min"
---

> 多數人做股票分析:打開券商 App,看 K 線、查財報、Google 新聞,然後自己下判斷。
> finance_data 的做法:讓 42 個機器人每天定時自己抓數據、自己讀財報、自己寫成繁中研究報告、自己發佈上線——全程沒有人手介入。
> 這篇就拆解這條「零人工」pipeline 的每一個齒輪是怎麼咬合的。

---

## 一、它到底是什麼

[`finance_data`](https://github.com/yennanliu/finance_data) 是一個**全自動的 AI 投資研究平台**。它覆蓋 30+ 家公司(AAPL、MSFT、NVDA、TSLA、PLTR、台股 0050、2330.tw……),每天自動產生:

- **個股基本面分析**(fundamental analysis)
- **個股技術面分析**(technical analysis)
- **每日市場新聞摘要**(market news)
- 配合 SEC 申報文件(10-K / 10-Q / 13-F / 6-K)、investor day 簡報、研究 notebook

關鍵字是「**全自動**」:從定時觸發、抓數據、餵 LLM、生成報告、到建置部署上線,**整條鏈沒有任何一步需要人手操作**。

整體 pipeline 長這樣:

```
   ┌──────────────┐   每天定時觸發
   │ GitHub Actions│ ◀────── cron schedule
   │     Cron      │
   └──────┬───────┘
          │ 1. 排程把「某支股票 + 某種分析」丟給腳本
          ▼
   ┌──────────────────────┐
   │  資料蒐集層           │  yfinance + Finviz + StockAnalysis + Roic.ai
   │  fetch_data()         │  → 價格/財報/技術指標/籌碼/新聞
   └──────────┬───────────┘
              │ 2. 把原始數據整理成 LLM context
              ▼
   ┌──────────────────────┐
   │  LLM 生成層           │  Claude / OpenAI / Gemini
   │  call_llm()           │  → 繁體中文研究報告(Markdown)
   └──────────┬───────────┘
              │ 3. 加上 front matter、嵌入圖表、寫檔
              ▼
   ┌──────────────────────┐
   │  報告儲存             │  ai_gen_report/stock/<ticker>/xxx.md
   │  save_report()        │  → git auto-commit
   └──────────┬───────────┘
              │ 4. 每晚 cron 統一建置部署
              ▼
   ┌──────────────────────┐
   │  MkDocs 建置 + 部署   │  build_docs.py → GitHub Pages
   └──────────────────────┘
```

下面逐層拆解。

---

## 二、第一層:Cron 怎麼觸發 AI 報告生成

整個系統的心臟是 GitHub Actions 的排程 workflow。repo 裡有近十個 workflow,各司其職:

```
.github/workflows/
├── daily_analysis.yml        ← 每日個股基本面 + 技術面分析(主力)
├── daily_market_news.yml     ← 每日市場新聞摘要
├── daily_stock_watchlist.yml ← 自選股清單
├── advanced_analysis.yml     ← 進階分析
├── download_10k.yml          ← SEC 財報下載
├── qa_report_quality.yml     ← 報告品質檢查
├── cleanup_refusals.yml      ← 清掉 LLM 拒答的失敗報告
├── daily_progress.yml        ← 進度追蹤
└── deploy.yml                ← MkDocs 建置部署
```

### 排程設計:一支股票一個時段

`daily_analysis.yml` 的核心巧思在於:它不是「一次跑完 24 支股票」,而是**把 24 支股票錯開成每 10 分鐘一支**,分散負載也避免 API rate limit。

```yaml
on:
  schedule:
    # 基本面分析:17:00–21:00 UTC,每 10 分鐘一支股票
    - cron: "0 17 * * *"     # → 0050   fundamental
    - cron: "10 17 * * *"    # → 2330.tw fundamental
    - cron: "20 17 * * *"    # → TSLA   fundamental
    # ... 24 支股票依序排開
    # 技術面分析:21:30–01:30 UTC,同樣 24 支錯開
    - cron: "30 21 * * *"    # → 0050   technical
    # ...
  workflow_dispatch:          # 也支援手動觸發,可自訂參數
    inputs:
      ticker: ...
      analysis_type: ...
      provider: ...
      model: ...
```

### Cron 表達式 → 股票的對應

那「`0 17 * * *` 這個時間點要跑哪支股票、哪種分析」是怎麼決定的?用一個 **case statement 把 cron 表達式對應到 ticker + analysis type**:

```bash
case "${{ github.event.schedule }}" in
  "0 17 * * *")   TICKER="0050";    ANALYSIS_TYPE="fundamental-analysis" ;;
  "10 17 * * *")  TICKER="2330.tw"; ANALYSIS_TYPE="fundamental-analysis" ;;
  "20 17 * * *")  TICKER="TSLA";    ANALYSIS_TYPE="fundamental-analysis" ;;
  "30 21 * * *")  TICKER="0050";    ANALYSIS_TYPE="technical-analysis" ;;
  # ...
esac
```

決定好之後,workflow 就用統一的指令呼叫生成腳本:

```bash
python scripts/generate_analysis.py \
  "$TICKER" \
  --analysis-type "$ANALYSIS_TYPE" \
  --provider      "$PROVIDER" \
  --output-dir    "$OUTPUT_DIR" \
  --model         "$MODEL" \
  --max-tokens    "$MAX_TOKENS"
```

跑完之後 auto-commit:`chore: auto-generate $TICKER $ANALYSIS_TYPE $DATE`。

### 環境變數與密鑰

provider 預設用 **Gemini 2.5 Flash**(便宜、快、token 上限高),三家 API key 都掛在 GitHub Secrets:

```yaml
env:
  DEFAULT_PROVIDER: gemini
  DEFAULT_MODEL: gemini-2.5-flash
  DEFAULT_MAX_TOKENS: "32000"
# Secrets: ANTHROPIC_API_KEY / OPEN_KEY_API / GEMINI_API_KEY
```

**設計重點:用 cron 的「時間」當作排程的 key。** 不需要額外的任務佇列或排程器——GitHub Actions 的 cron 本身就是免費的分散式排程器,每個時間點對應一個任務,天然錯開、天然不重疊。

---

## 三、第二層:市場數據怎麼蒐集

排程觸發後,`generate_analysis.py` 第一件事是呼叫 `fetch_data(ticker)` 把這支股票的所有數據抓齊。資料**不只來自一個源**,而是多源交叉補齊:

```
   fetch_data(ticker)
        │
        ├─ yfinance      ── 價格/財報/籌碼/新聞(主力)
        ├─ Finviz        ── 估值比率、RSI/SMA、持股(爬 HTML 表格)
        ├─ StockAnalysis ── 年度/季度損益表、資產負債表
        └─ Roic.ai       ── 10+ 年歷史價值投資指標
```

### 主力:yfinance

```python
def fetch_data(ticker: str) -> dict:
    """從 Yahoo Finance 下載基本面、價格歷史與新聞。"""
    yf = _get_yf()
    t = yf.Ticker(ticker)
    info = t.info or {}
    # ...
```

它抓的東西非常全:

| 類別 | yfinance 呼叫 | 內容 |
|------|--------------|------|
| 價格 | `t.history(period="2y")` | 兩年 OHLCV、現價、52 週高低、月線收盤 |
| 移動平均 | (計算) | MA 5/10/20/60/120/240 日 |
| 損益 | `t.financials` / `t.quarterly_financials` | 年度 + 季度損益表 |
| 資產負債 | `t.balance_sheet` / `t.quarterly_balance_sheet` | 年度 + 季度 |
| 現金流 | `t.cashflow` / `t.quarterly_cashflow` | 年度 + 季度 |
| 籌碼 | `t.insider_transactions` / `t.institutional_holders` / `t.major_holders` | 內部人、前 20 大機構、主要持股 |
| 分析師 | `t.upgrades_downgrades` / `t.earnings_history` | 最近 10 次評等、近 8 季 EPS 超預期/不如預期 |
| 新聞 | `t.news` | 最新 10 篇 |

### 技術指標自己算

光有 OHLCV 不夠,`compute_technicals(hist)` 從原始價量再推導出一整套技術指標:

```python
def compute_technicals(hist):
    # 從 OHLCV 推導:
    # RSI(14)、MACD(12/26/9)、布林通道、ATR(14)
    # 隨機指標 %K/%D、ADX(14)、OBV、週線 OHLCV 彙總表
    ...
```

### 多源補齊:為什麼不只用 yfinance?

yfinance 偶爾會缺欄位、資料不全。所以再爬三個源交叉補:

- **Finviz**:把 HTML 表格轉成文字,抓 P/E、PEG、毛利率、RSI、SMA、持股比例
- **StockAnalysis**:年度/季度的完整財報表格
- **Roic.ai**:10 年以上的歷史價值投資指標(ROIC、ROE 等)

最後用 `_merge_finviz_into_info()` 把 Finviz 的值**回填到 yfinance 缺的欄位**:

```python
# yfinance 缺的欄位,用 Finviz 解析出的值補上
info = _merge_finviz_into_info(info, finviz_data)
```

`fetch_data()` 回傳一個大字典,同時含**原始 DataFrame**(給畫圖用)和**預先格式化好的文字區塊**(`insider_text`、`institutional_text`、`earnings_text`…,給 LLM 讀用)。

**設計重點:資料層做兩件事——「抓全」與「翻譯成 LLM 看得懂的形式」。** DataFrame 給程式畫圖,文字區塊給 LLM 閱讀,同一份數據兩種用途。

---

## 四、第三層:LLM 怎麼被觸發

數據齊了,接著進 LLM。流程是「組 context → 呼叫 LLM」兩步:

```python
context = build_context(data, analysis_type)        # 把數據填進對應的 prompt 模板
report  = call_llm(ticker, context, analysis_type,  # 呼叫對應的 provider
                   provider, args.model, args.max_tokens)
```

### Prompt 模板:一種分析一個模板

`scripts/analysis/prompts/` 裡每種分析各有一個 prompt 模板:

```
prompts/
├── fundamental.txt              ← 基本面分析
├── technical.txt                ← 技術面分析
├── financial_report_analyst.txt ← 財報分析
├── stock_valuation.txt          ← 估值
├── earnings_call.txt            ← 法說會
├── insider_trading.txt          ← 內部人交易
├── institutional.txt            ← 機構持股
├── sector.txt / economics.txt   ← 產業 / 總經
├── openai_system.txt            ← OpenAI 系統提示
└── gemini_system.txt            ← Gemini 系統提示(較短)
```

`build_context()` 把 `fetch_data()` 整理好的文字數據,連同 `ticker` 和 `TODAY` 填進對應模板,組成最終餵給 LLM 的 prompt。

### 三家 provider 各自的呼叫

`call_llm()` 根據 `provider` 參數,分派到 `call_claude()` / `call_openai()` / `call_gemini()`。三者共通的模式:

1. 從環境變數讀 API key
2. 用 `ticker` / `financial_context` / `TODAY` 格式化 prompt
3. **重試邏輯**:rate limit 時最多 5 次,指數退避(從 30 秒起)
4. 記錄 token 用量與回應長度
5. **偵測拒答並重試**(最多 5 次,逐次升溫)

**Claude**(無 system prompt,純 user message):

```python
response = client.messages.create(
    model=model,
    max_tokens=max_tokens,
    messages=[{"role": "user", "content": prompt}],
)
text = "\n\n".join(b.text for b in response.content)
```

**OpenAI**(讀 `openai_system.txt` 當 system,gpt-4o 上限 16,384 tokens):

```python
response = client.chat.completions.create(
    model=model,
    max_tokens=effective_max_tokens,
    temperature=0.7,
    messages=[
        {"role": "system", "content": system_message},
        {"role": "user",   "content": prompt},
    ],
)
```

**Gemini**(讀 `gemini_system.txt`,上限 65,536 tokens,額外處理截斷):

```python
config = types.GenerateContentConfig(
    system_instruction=system_message,
    max_output_tokens=effective_max_tokens,
    temperature=0.7,
)
# 若 finish_reason == "MAX_TOKENS"(被截斷)→ 用最大預算重試
```

### 一個關鍵細節:拒答處理(Refusal Handling)

LLM 偶爾會拒答(「我無法提供投資建議…」)。系統會**偵測「短回應(<500 字)且含拒答關鍵詞」**,然後**逐次升溫重試**(0.7 → 1.0+),並在 prompt 前面加上中文 override 前綴強制它用中文寫:

```
   呼叫 LLM
      │
      ▼
   回應 < 500 字 且含拒答詞?
      │ Yes                        │ No
      ▼                            ▼
   升溫 + 加中文 override 前綴   採用這份報告
   重試(最多 5 次)
```

那些怎麼重試都拒答的失敗報告,由另一個 workflow `cleanup_refusals.yml` 定期清掉。

**設計重點:LLM 不是「呼叫一次就好」,而是要包一整層韌性**——rate limit 退避、截斷重試、拒答升溫重試。自動化 pipeline 最怕的就是「某次 API 抽風,整天的報告就缺一塊」,這層重試就是防它。

---

## 五、第四層:報告怎麼成形與寫檔

LLM 回傳 Markdown 內文後,`save_report()` 把它包裝成完整的貼文:

1. **加上 YAML front matter**:ticker、日期、分析類型、`language: zh-TW`、provider、model
2. **技術分析額外嵌入互動圖表**:`generate_plotly_candlestick_chart()` 產生含 MA30/MA60/MA200 的 Plotly K 線 HTML,直接嵌進報告
3. **寫檔 + 防撞名**:同一天同類型的報告,後綴自動加 `-2`、`-3`

```python
report = call_llm(...)                       # LLM 生成的繁中內文
# 技術分析:嵌入互動 K 線圖
if analysis_type == "technical-analysis":
    chart = generate_plotly_candlestick_chart(data["hist"])
    report = chart + report
save_report(ticker, final_report, output_dir, analysis_type, provider=provider)
```

輸出路徑長這樣:

```
ai_gen_report/stock/tsla/fundamental_analysis_2026-06-30_gemini.md
ai_gen_report/stock/tsla/technical_analysis_2026-06-30_gemini.md
ai_gen_report/market_news/nvda/market_news_2026-06-30_gemini.md
```

### 每日市場新聞:另一條相似的線

`generate_market_news.py` 是同一套思路的變體,差別在資料源:

- **yfinance** 的 `t.news` + **四個 RSS 源**(Google News、Bing News、Yahoo Finance、Seeking Alpha)用 `ThreadPoolExecutor` 並發抓,各取前 5 則,標題正規化去重
- prompt **強調只能根據提供的新聞分析、不可捏造**
- 輸出含:公司概覽、400–600 字摘要、5–8 個重點、新聞摘要、3–5 則深度分析、情緒評估(emoji)、風險因子、近期催化劑、來源索引

---

## 六、第五層:建置與部署

報告 commit 進 repo 後,由 MkDocs 建置成靜態站台部署到 GitHub Pages。這一層本身也經過大量效能優化(搜尋索引、導覽、部署 debounce),那是另一篇的主題——詳見 [《把站台從 3.1GB 砍到 503MB:finance_data 部署效能調校全紀錄》](../mkdocs-site-size-deploy-perf-tuning-zh/)。

簡言之:內容由 ~42 個每日任務寫入,但**部署改由每晚一次 cron 統一觸發**(而非每次 commit 都部署),`build_docs.py` 負責把 Markdown 報告整理、prerender、套搜尋排除、建導覽,交給 MkDocs 產出站台。

---

## 七、把整條鏈串起來看

用一支股票(以 TSLA 基本面為例)走一遍完整流程:

```
17:20 UTC  cron "20 17 * * *" 觸發
   │
   ▼  case statement → TICKER=TSLA, TYPE=fundamental-analysis
generate_analysis.py TSLA --analysis-type fundamental-analysis --provider gemini
   │
   ▼  fetch_data("TSLA")
   ├─ yfinance:2年K線、財報、籌碼、新聞
   ├─ Finviz / StockAnalysis / Roic.ai:補齊估值與歷史指標
   └─ compute_technicals():RSI/MACD/布林...
   │
   ▼  build_context(data, "fundamental")  → 填進 fundamental.txt 模板
   │
   ▼  call_llm() → call_gemini()
   ├─ 重試/退避/截斷處理/拒答升溫
   └─ 回傳繁中 Markdown 報告
   │
   ▼  save_report()
   ├─ 加 front matter(zh-TW, gemini, 2026-06-30)
   └─ 寫到 ai_gen_report/stock/tsla/fundamental_analysis_2026-06-30_gemini.md
   │
   ▼  git auto-commit: "chore: auto-generate TSLA fundamental-analysis 2026-06-30"
   │
   ▼  (當晚)deploy cron → build_docs.py → MkDocs → GitHub Pages 上線
```

整個過程**從觸發到上線,零人工介入**。

---

## 八、設計上值得學的幾點

| 設計 | 做法 | 為什麼聰明 |
|------|------|-----------|
| 排程 | cron 時間點當 task key | 免費、天然錯開、不需額外排程器 |
| 負載分散 | 24 支股票每 10 分鐘一支 | 避開 API rate limit,失敗只影響一支 |
| 資料蒐集 | 多源交叉補齊 | 單一源(yfinance)會缺欄位,多源互補 |
| 資料形式 | DataFrame + 預格式化文字 | 一份數據兩用:程式畫圖、LLM 閱讀 |
| provider | 三家可切換,預設 Gemini Flash | 成本/速度/上限取捨,可隨時改 |
| LLM 韌性 | 退避 + 截斷重試 + 拒答升溫 | 自動化最怕 API 抽風,重試兜住 |
| 失敗清理 | cleanup_refusals workflow | 拒答的爛報告自動清掉,不污染站台 |
| 部署 | 每晚統一 cron(非每 commit) | 42 任務若每次都部署會塞爆 CI |

**這個專案最值得借鏡的,是它把「一個原本需要分析師每天手動做的工作」拆解成可被 cron + 腳本 + LLM 完全自動化的流水線**,而且每一個會出錯的環節(API 限流、模型拒答、回應截斷、資料缺漏)都有對應的退路。

> 一句話總結:自動化的難點從來不是「讓它跑起來」,而是「讓它在沒人看著的時候,出錯了也能自己撐住」。

---

**參考連結**

- Repo: [yennanliu/finance_data](https://github.com/yennanliu/finance_data)
- 線上站台:[yennanliu.github.io/finance_data](https://yennanliu.github.io/finance_data)
- 相關文章:[把站台從 3.1GB 砍到 503MB:finance_data 部署效能調校全紀錄](../mkdocs-site-size-deploy-perf-tuning-zh/)
- [yfinance](https://github.com/ranaroussi/yfinance)、[MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
