---
title: "finance_data: A Python Toolkit for Downloading SEC Financial Filings from EDGAR"
date: 2026-02-24T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "finance", "tools"]
tags: ["Python", "SEC", "EDGAR", "Finance", "Financial Data", "10-K", "10-Q", "13-F", "Data Engineering", "Open Source"]
summary: "Introducing finance_data — a lightweight Python toolkit that automates downloading SEC financial filings (10-K, 10-Q, 13-F) from EDGAR. Search by ticker symbol, download in bulk, and respect SEC rate limits out of the box."
description: "A complete guide to the finance_data open-source project: a Python-based toolkit for downloading SEC EDGAR financial reports including 10-K annual reports, 10-Q quarterly filings, and 13-F institutional holdings. Covers setup, usage examples, and the underlying architecture."
readTime: "10 min"
---

## Introduction: The Pain of Getting Clean SEC Data

Every serious investor, quant developer, or financial analyst eventually faces the same problem: **getting clean, structured financial data is surprisingly hard**.

While paid services like Bloomberg Terminal or Refinitiv cost thousands of dollars per year, the SEC's EDGAR database is completely free and contains the authoritative source of truth for all US public company filings — annual reports (10-K), quarterly reports (10-Q), and institutional holdings (13-F). The catch? Navigating EDGAR manually is tedious, and automating it means dealing with ticker-to-CIK conversion, pagination, rate limits, and messy HTML responses.

**[finance_data](https://github.com/yennanliu/finance_data)** solves this by wrapping all that complexity into a clean, minimal Python toolkit.

## What is finance_data?

`finance_data` is an open-source Python project that provides scripts to batch-download SEC financial filings from EDGAR. It handles:

- **Ticker → CIK conversion** automatically (no need to look up CIK numbers manually)
- **Rate limiting** (max 10 requests/second, per SEC's official guidelines)
- **Bulk downloads** — pass multiple tickers in one command
- **Organized storage** with a clean directory structure for each filing type

The project is intentionally lightweight: a single Python file with minimal dependencies (`requests`). No ORM, no database, no Docker — just a script you can run immediately.

## Project Structure

```
finance_data/
├── 10-k/          # Annual report filings (10-K)
├── 10-q/          # Quarterly report filings (10-Q)
├── 13-f/          # Institutional holdings (13-F)
└── script/
    ├── download_10k.py       # Main download script (v1)
    └── download_10k_pdf.py   # PDF downloader (v2, uses uv)
```

Each downloaded file follows a consistent naming convention:

```
{TICKER}_{DATE}_10K.html
```

For example: `AAPL_2024-09-28_10K.html`

## Quick Start

### Installation

```bash
git clone https://github.com/yennanliu/finance_data
cd finance_data
pip install requests
```

That's it. No complex setup required.

### Download a Single Company's 10-K Filings

```bash
python script/download_10k.py AAPL
```

This fetches Apple's most recent 10-K annual report from EDGAR and saves it to the `10-k/` directory.

### Download Multiple Companies at Once

```bash
python script/download_10k.py AAPL MSFT TSLA
```

Pass any number of ticker symbols separated by spaces. The script downloads them sequentially while respecting SEC rate limits.

### Download More Historical Filings

```bash
python script/download_10k.py AAPL MSFT TSLA -n 10
```

The `-n` flag controls how many filings to retrieve per ticker (defaults to the most recent). Setting `-n 10` gives you a decade of annual reports.

### V2: PDF Downloader with `uv`

For a PDF-formatted version of the filings, use the v2 script powered by `uv`:

```bash
uv run script/download_10k_pdf.py AAPL
```

## How It Works: Under the Hood

### Step 1: Ticker to CIK Resolution

SEC EDGAR identifies companies by CIK (Central Index Key), not by ticker symbol. The script automatically queries EDGAR's company search API to resolve any ticker to its CIK:

```
https://efts.sec.gov/LATEST/search-index?q={TICKER}&dateRange=custom&...
```

### Step 2: Fetching Filing Metadata

Once the CIK is known, the script queries EDGAR's submissions API:

```
https://data.sec.gov/submissions/CIK{cik_padded}.json
```

This returns structured JSON with all filings — filing dates, accession numbers, document types, and file paths.

### Step 3: Filtering by Filing Type

The script filters submissions by type (`10-K`, `10-Q`, `13-F`) and limits the count based on the `-n` parameter.

### Step 4: Downloading HTML Documents

For each filing, the script constructs the full document URL and downloads the HTML content:

```
https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}.htm
```

### Step 5: Rate Limiting

To comply with SEC's guidelines (max 10 requests per second), the script includes built-in delays between requests. This prevents your IP from being throttled or blocked.

## Use Cases

### 1. Fundamental Analysis Research

Download 10-K annual reports for companies you're researching. The HTML format makes it easy to parse financial statements programmatically or feed the content to an LLM for analysis.

```bash
# Download 5 years of annual reports for a watchlist
python script/download_10k.py NVDA AMD INTC QCOM -n 5
```

### 2. Building a Local Financial Database

Combine with a simple ETL pipeline to extract and store key financial metrics (revenue, EPS, free cash flow) into a local SQLite or PostgreSQL database for backtesting and screening.

### 3. Institutional Holdings Tracking

The `13-f/` directory and corresponding scripts let you track what major funds (hedge funds, mutual funds, ETFs) are buying and selling each quarter — the same data that drives "smart money" analysis.

### 4. LLM-Powered Document Analysis

Pair the downloaded HTML filings with Claude or GPT-4 for automated analysis:

- Extract risk factors from 10-K filings
- Compare year-over-year changes in MD&A sections
- Summarize earnings notes and forward guidance

### 5. Academic and Quantitative Research

Build clean datasets for factor research, academic studies, or machine learning models that require historical financial statement data.

## Why EDGAR Over Paid Data Providers?

| Feature | EDGAR (finance_data) | Yahoo Finance API | Bloomberg |
|---|---|---|---|
| Cost | Free | Free (limited) | $2,000+/month |
| Coverage | All SEC filers | US + some global | Global |
| Historical depth | Full history | ~5 years | Full history |
| Filing types | 10-K, 10-Q, 13-F, 8-K, etc. | Summary only | Full |
| Raw source | Yes (official) | Derived | Derived |
| API stability | High (government) | Variable | High |

EDGAR is the **primary source** — every financial data provider ultimately derives their data from it. Going directly to EDGAR means you get the raw, unprocessed filings before any normalization or potential data errors introduced by aggregators.

## Limitations and What's Next

**Current Limitations:**
- Downloads HTML/PDF but does not parse or structure the financial data (yet)
- No database storage built-in — files are saved to disk
- English-language filings only (SEC requirement)
- US public companies only

**Potential Extensions:**
- Add structured parsing for financial statements (balance sheet, income statement, cash flow)
- Support additional filing types: 8-K (material events), DEF 14A (proxy statements), S-1 (IPO filings)
- Async downloads for faster bulk processing
- Integration with pandas/polars for immediate data analysis

## Project Links

- **GitHub Repository**: [https://github.com/yennanliu/finance_data](https://github.com/yennanliu/finance_data)
- **Demo / Docs Site**: [https://yennj12.js.org/finance_data](https://yennj12.js.org/finance_data)

## Conclusion

`finance_data` fills a practical gap in the open-source financial tooling ecosystem: a simple, zero-dependency script that gets you from a list of tickers to local SEC filings in under a minute.

Whether you're a developer building a financial application, a quant researcher analyzing fundamentals, or an investor doing your own due diligence, having direct programmatic access to SEC filings is a powerful capability — and now it takes just two commands to set up.

```bash
pip install requests
python script/download_10k.py AAPL MSFT TSLA NVDA -n 5
```

Star the repo, open issues for filing types you'd like supported, and happy researching.

> ⚠️ **Disclaimer**: This tool is for educational and research purposes. Always consult qualified financial professionals before making investment decisions.
