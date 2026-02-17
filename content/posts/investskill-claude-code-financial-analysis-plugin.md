---
title: "InvestSkill: Professional Investment Analysis Plugin for Claude Code"
date: 2026-02-17T10:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "tools", "finance"]
tags: ["Claude Code", "AI", "Investment", "Financial Analysis", "Stock Analysis", "Plugin", "MCP", "Trading", "Economics", "Portfolio Management"]
summary: "Discover InvestSkill, a comprehensive Claude Code plugin marketplace that brings professional investment analysis and stock evaluation capabilities directly into your AI development workflow. From fundamental analysis to technical indicators, transform Claude into your personal financial analyst."
description: "Complete guide to InvestSkill, a Claude Code plugin that provides six powerful analytical tools for stock evaluation, fundamental analysis, technical analysis, economics research, portfolio review, and sector analysis. Learn how to integrate AI-powered financial analysis into your development environment."
readTime: "15 min"
---

## 🎯 Introduction: AI-Powered Investment Analysis in Your IDE

Financial markets are complex, data-driven environments where timely analysis can make the difference between profit and loss. Traders, investors, and financial analysts typically juggle multiple platforms, tools, and data sources to research stocks, analyze trends, and make informed decisions.

**InvestSkill** changes this paradigm by bringing professional-grade investment analysis tools directly into Claude Code, your AI-powered development environment. Instead of switching between trading platforms, financial terminals, and research tools, you can now leverage Claude's intelligence for comprehensive market analysis without leaving your workflow.

### **The Vision**

InvestSkill represents a new category of AI tooling: **context-aware financial analysis**. It's not just about running calculations or fetching data—it's about having an AI assistant that understands:
- Market fundamentals and valuation metrics
- Technical chart patterns and indicators
- Macroeconomic trends and their market impacts
- Portfolio construction and optimization
- Sector rotation and relative positioning

All accessible through simple slash commands in Claude Code.

### **Who Is This For?**

- **Retail Investors**: Individual investors seeking deeper analysis before making trades
- **Quantitative Developers**: Building algorithmic trading systems and need quick market insights
- **Financial Analysts**: Professionals who want to automate routine analysis tasks
- **Students & Learners**: Anyone studying finance, trading, or market analysis
- **Developers Building FinTech**: Engineers working on financial applications who need market context

> ⚠️ **Important Disclaimer**: InvestSkill is an educational tool designed to assist with financial analysis and research. It does not provide financial advice, investment recommendations, or trading signals. Always conduct your own due diligence and consult with qualified financial professionals before making investment decisions.

## 🚀 What Makes InvestSkill Unique?

### **Problem: The Fragmented Analysis Workflow**

Traditional investment analysis involves:

1. **Multiple Platforms**: Yahoo Finance for quotes, TradingView for charts, SEC EDGAR for filings, economic calendars for data
2. **Context Switching**: Constantly moving between tools breaks concentration and slows decision-making
3. **Manual Integration**: Combining fundamental, technical, and economic data requires manual effort
4. **Limited AI Integration**: Existing AI tools don't understand financial analysis deeply
5. **Repetitive Research**: Performing the same analysis steps for each stock evaluation

### **Solution: Unified AI-Powered Analysis**

InvestSkill solves these challenges by providing:

✅ **Single Interface**: All analysis tools accessible through Claude Code
✅ **Contextual Intelligence**: Claude understands financial concepts and relationships
✅ **Workflow Integration**: Analyze markets while building trading systems or financial apps
✅ **Comprehensive Coverage**: Six specialized analysis skills covering all major dimensions
✅ **Automated Insights**: Let AI synthesize complex data into actionable information

## 📦 The Six Pillars of Financial Analysis

InvestSkill provides six specialized analytical capabilities, each designed to address a specific dimension of market research:

### **1. Stock Evaluation** (`/stock-eval`)

**Purpose**: Comprehensive fundamental and valuation analysis
**Use Case**: Quick overview before initiating a position

**What It Analyzes**:
- Company fundamentals (revenue, earnings, margins)
- Valuation metrics (P/E, P/S, P/B, PEG ratios)
- Growth rates and trends
- Competitive positioning
- Risk factors and concerns

**Example Usage**:
```bash
/stock-eval AAPL
# Returns: Comprehensive evaluation of Apple Inc.
# - Current valuation vs historical averages
# - Growth trajectory analysis
# - Competitive moat assessment
# - Key risk factors
```

**When to Use**:
- Before initiating new positions
- Quarterly re-evaluation of holdings
- Comparing investment opportunities
- Due diligence on unfamiliar companies

---

### **2. Fundamental Analysis** (`/fundamental-analysis`)

**Purpose**: Deep-dive financial statement examination
**Use Case**: Understanding a company's financial health

**What It Analyzes**:
- Income statement trends (revenue, COGS, operating income)
- Balance sheet strength (assets, liabilities, equity)
- Cash flow analysis (operating, investing, financing)
- Financial ratios (liquidity, leverage, efficiency)
- Year-over-year and quarter-over-quarter comparisons

**Example Usage**:
```bash
/fundamental-analysis MSFT
# Returns: Multi-year financial analysis
# - Revenue and margin trends
# - Balance sheet health metrics
# - Cash flow sustainability
# - Financial ratio comparison to industry
```

**When to Use**:
- Value investing research
- Credit risk assessment
- Long-term investment decisions
- Identifying financial red flags

---

### **3. Technical Analysis** (`/technical-analysis`)

**Purpose**: Chart patterns and technical indicators
**Use Case**: Timing entry and exit points

**What It Analyzes**:
- Price action and trend identification
- Support and resistance levels
- Technical indicators (RSI, MACD, moving averages)
- Chart patterns (head & shoulders, triangles, flags)
- Volume analysis and momentum

**Example Usage**:
```bash
/technical-analysis TSLA
# Returns: Technical outlook
# - Current trend (bullish/bearish/neutral)
# - Key support and resistance levels
# - Overbought/oversold conditions
# - Potential entry/exit zones
```

**When to Use**:
- Swing trading setups
- Timing position entries
- Setting stop-loss levels
- Identifying breakout opportunities

---

### **4. Economics Analysis** (`/economics-analysis`)

**Purpose**: US economic indicators assessment
**Use Case**: Understanding macroeconomic backdrop

**What It Analyzes**:
- GDP growth and economic expansion/contraction
- Inflation metrics (CPI, PCE)
- Employment data (jobs reports, unemployment rate)
- Interest rates and Federal Reserve policy
- Leading economic indicators

**Example Usage**:
```bash
/economics-analysis
# Returns: Current economic environment
# - GDP growth trajectory
# - Inflation trends and Fed response
# - Employment health
# - Recession risk indicators
# - Market sector implications
```

**When to Use**:
- Asset allocation decisions
- Sector rotation strategies
- Risk-on vs risk-off positioning
- Understanding market volatility drivers

---

### **5. Portfolio Review** (`/portfolio-review`)

**Purpose**: Performance analysis and optimization
**Use Case**: Evaluating and improving portfolio construction

**What It Analyzes**:
- Portfolio composition and diversification
- Risk-adjusted returns (Sharpe ratio, volatility)
- Correlation analysis between holdings
- Sector and asset class allocation
- Rebalancing recommendations

**Example Usage**:
```bash
/portfolio-review
# (Provide current holdings)
# Returns: Portfolio health analysis
# - Diversification score
# - Risk concentration areas
# - Correlation matrix
# - Optimization suggestions
```

**When to Use**:
- Quarterly portfolio reviews
- After major market moves
- Before adding new positions
- Rebalancing decisions

---

### **6. Sector Analysis** (`/sector-analysis`)

**Purpose**: Market positioning and rotation insights
**Use Case**: Understanding sector dynamics and trends

**What It Analyzes**:
- Sector performance vs market benchmarks
- Relative strength and momentum
- Economic cycle positioning
- Sector rotation patterns
- Industry-specific catalysts

**Example Usage**:
```bash
/sector-analysis technology
# Returns: Technology sector outlook
# - Performance vs S&P 500
# - Sub-sector leaders/laggards
# - Cyclical positioning
# - Key catalysts and headwinds
```

**When to Use**:
- Sector rotation strategies
- Market cycle positioning
- Thematic investing research
- Relative value analysis

## 🔧 Installation & Setup

Getting started with InvestSkill takes just three simple commands:

### **Step 1: Add the InvestSkill Marketplace**

```bash
/plugin marketplace add yennanliu/InvestSkill
```

This registers the InvestSkill plugin marketplace with your Claude Code installation. You only need to do this once.

### **Step 2: Install the US Stock Analysis Plugin**

```bash
/plugin install us-stock-analysis
```

This installs the complete suite of six analysis skills into your Claude Code environment.

### **Step 3: Verify Installation**

```bash
/plugin list
```

You should see `us-stock-analysis` in your installed plugins list. All six slash commands (`/stock-eval`, `/fundamental-analysis`, `/technical-analysis`, `/economics-analysis`, `/portfolio-review`, `/sector-analysis`) are now available.

### **Configuration (Optional)**

InvestSkill works out of the box, but you can customize behavior through SKILL.md files located in:

```
~/.claude/skills/us-stock-analysis/
├── stock-eval/SKILL.md
├── fundamental-analysis/SKILL.md
├── technical-analysis/SKILL.md
├── economics-analysis/SKILL.md
├── portfolio-review/SKILL.md
└── sector-analysis/SKILL.md
```

Each SKILL.md file contains:
- Detailed analysis methodology
- Data sources and references
- Customization options
- Best practices for that analysis type

## 💡 Real-World Usage Scenarios

### **Scenario 1: Pre-Trade Due Diligence**

**Goal**: Evaluate a potential stock purchase

**Workflow**:
```bash
# Step 1: Quick evaluation
/stock-eval NVDA

# Step 2: Deep fundamentals
/fundamental-analysis NVDA

# Step 3: Technical timing
/technical-analysis NVDA

# Step 4: Economic context
/economics-analysis
```

**Outcome**: Comprehensive understanding of NVDA from multiple angles before making a trade decision.

---

### **Scenario 2: Portfolio Optimization**

**Goal**: Improve existing portfolio allocation

**Workflow**:
```bash
# Step 1: Current portfolio health
/portfolio-review
# (Provide current holdings)

# Step 2: Sector concentration check
/sector-analysis technology
/sector-analysis healthcare
/sector-analysis financials

# Step 3: Individual position review
/stock-eval AAPL
/stock-eval JNJ
/stock-eval JPM
```

**Outcome**: Identify over-concentrations, correlation risks, and rebalancing opportunities.

---

### **Scenario 3: Macro-Driven Trading**

**Goal**: Position portfolio based on economic outlook

**Workflow**:
```bash
# Step 1: Economic environment
/economics-analysis

# Step 2: Sector positioning
/sector-analysis consumer-discretionary
/sector-analysis utilities

# Step 3: Specific opportunities
/stock-eval XLY  # Consumer Discretionary ETF
/stock-eval XLU  # Utilities ETF
```

**Outcome**: Data-driven sector rotation based on macroeconomic trends.

---

### **Scenario 4: Building a Trading System**

**Goal**: Develop algorithmic trading signals

**Workflow**:
```python
# In your Python trading system
def generate_signals():
    # Use Claude Code with InvestSkill for research
    # /technical-analysis SPY
    # /economics-analysis

    # Implement signal logic based on insights
    if rsi < 30 and gdp_growth > 2.0:
        return "BUY"
    # ... more logic
```

**Outcome**: Combine AI-powered analysis with systematic trading rules.

## 🏗️ Technical Architecture

InvestSkill is built on the Claude Code plugin marketplace infrastructure:

### **Component Architecture**

```
InvestSkill/
├── marketplace.json           # Plugin registry
├── plugins/
│   └── us-stock-analysis/
│       ├── plugin.json        # Plugin metadata
│       └── skills/
│           ├── stock-eval/
│           │   └── SKILL.md
│           ├── fundamental-analysis/
│           │   └── SKILL.md
│           ├── technical-analysis/
│           │   └── SKILL.md
│           ├── economics-analysis/
│           │   └── SKILL.md
│           ├── portfolio-review/
│           │   └── SKILL.md
│           └── sector-analysis/
│               └── SKILL.md
├── .github/
│   └── workflows/
│       ├── validate-json.yml
│       ├── validate-skills.yml
│       ├── auto-release.yml
│       └── greet-first-time.yml
└── README.md
```

### **Key Technologies**

- **JSON-based Configuration**: Simple, declarative plugin and marketplace definitions
- **Markdown Skill Definitions**: Human-readable SKILL.md files with frontmatter
- **GitHub Actions CI/CD**: Automated validation, testing, and release packaging
- **SHA256 Checksums**: Security verification for all releases
- **GitHub Pages**: Documentation hosting and distribution

### **Quality Assurance Pipeline**

1. **JSON Validation**: Ensures `marketplace.json` and `plugin.json` are well-formed
2. **SKILL.md Validation**: Verifies frontmatter structure and required fields
3. **Automated Testing**: Validates skill invocation patterns
4. **Release Packaging**: Automatic versioning and checksum generation
5. **Pull Request Automation**: Auto-labeling and contributor greetings

### **How Skills Are Invoked**

When you type `/stock-eval AAPL`:

1. Claude Code recognizes the slash command
2. Loads `stock-eval/SKILL.md` prompt template
3. Injects the ticker symbol (`AAPL`) into the template
4. Claude processes the enriched prompt with financial analysis context
5. Returns structured analysis based on the skill's methodology

This architecture ensures:
- **Consistency**: Same analysis methodology every time
- **Transparency**: SKILL.md files are readable and modifiable
- **Extensibility**: Easy to add new skills or customize existing ones
- **Maintainability**: Automated CI/CD ensures quality

## 🎓 Best Practices & Tips

### **1. Combine Multiple Skills for Comprehensive Analysis**

Don't rely on a single skill—use multiple perspectives:

```bash
# Fundamental + Technical + Economic
/stock-eval AAPL
/technical-analysis AAPL
/economics-analysis
```

### **2. Regular Portfolio Reviews**

Schedule periodic reviews (e.g., monthly or quarterly):

```bash
# Monthly routine
/portfolio-review
/sector-analysis [your concentrated sectors]
/economics-analysis
```

### **3. Document Your Analysis**

InvestSkill outputs can be copied into:
- Trading journals
- Investment research notes
- Decision logs for backtesting

### **4. Understand Limitations**

- InvestSkill provides **analysis**, not **advice**
- Data quality depends on available sources
- AI can identify patterns but cannot predict the future
- Always verify critical information from primary sources

### **5. Customize Skill Definitions**

Modify SKILL.md files to match your:
- Investment philosophy (value, growth, momentum)
- Risk tolerance
- Time horizons
- Preferred metrics and indicators

### **6. Integrate with Your Workflow**

Use InvestSkill alongside:
- **Backtesting frameworks**: Validate strategies
- **Trading platforms**: Execute informed trades
- **Portfolio management tools**: Track performance
- **Research databases**: Deep-dive specific topics

## 🔮 Future Roadmap

The InvestSkill project is actively evolving. Planned enhancements include:

### **Short-Term (Next 3 Months)**

- **Crypto Analysis Plugin**: Bitcoin, Ethereum, and altcoin evaluation
- **Options Analysis**: Greeks, implied volatility, and strategy evaluation
- **Real-Time Data Integration**: Live market data via MCP servers
- **Backtesting Helpers**: Skills for strategy validation

### **Medium-Term (6-12 Months)**

- **International Markets**: Coverage beyond US stocks
- **Fixed Income Analysis**: Bond evaluation and yield curve analysis
- **Risk Management Tools**: VaR, scenario analysis, stress testing
- **Machine Learning Integration**: Predictive models and signals

### **Long-Term Vision**

- **Community Marketplace**: Share and discover user-created analysis skills
- **Custom MCP Servers**: Direct integration with brokers and data providers
- **Multi-Asset Analysis**: Unified framework for stocks, bonds, crypto, commodities
- **Collaborative Research**: Share analyses within teams

## 🤝 Contributing & Community

InvestSkill is an open-source project welcoming contributions from the financial and developer communities.

### **How to Contribute**

1. **Report Issues**: Found a bug or have a feature request? [Open an issue](https://github.com/yennanliu/InvestSkill/issues)
2. **Submit Pull Requests**: Improve existing skills or add new ones
3. **Share Your Skills**: Create custom analysis skills and contribute them
4. **Improve Documentation**: Help others get started with better guides
5. **Provide Feedback**: Share your experience and suggestions

### **Development Setup**

```bash
# Fork and clone the repository
git clone https://github.com/yennanliu/InvestSkill.git
cd InvestSkill

# Create a new skill
mkdir -p plugins/us-stock-analysis/skills/my-new-skill
cd plugins/us-stock-analysis/skills/my-new-skill

# Create SKILL.md with proper frontmatter
cat > SKILL.md << 'EOF'
---
title: "My New Analysis Skill"
version: "1.0.0"
description: "Custom analysis for..."
---

# Analysis methodology...
EOF

# Test locally
/plugin install us-stock-analysis
/my-new-skill AAPL

# Submit PR when ready
git checkout -b feature/my-new-skill
git add .
git commit -m "Add new skill: my-new-skill"
git push origin feature/my-new-skill
```

### **Community Resources**

- **GitHub Repository**: [yennanliu/InvestSkill](https://github.com/yennanliu/InvestSkill)
- **Discussions**: Share strategies and ask questions
- **Wiki**: Detailed documentation and examples
- **Issue Tracker**: Bug reports and feature requests

## 📝 Conclusion

InvestSkill represents a new paradigm in financial analysis tooling: **AI-native, workflow-integrated, and developer-friendly**. By bringing professional investment analysis directly into Claude Code, it eliminates context-switching, accelerates research, and empowers better-informed decision-making.

### **Key Takeaways**

✅ **Unified Analysis**: Six specialized skills covering all major analysis dimensions
✅ **Easy Setup**: Three commands to get started
✅ **Flexible**: Customize skills to match your investment philosophy
✅ **Open Source**: Community-driven and extensible
✅ **Production-Ready**: Battle-tested with automated CI/CD

### **Getting Started Today**

```bash
# Install in 30 seconds
/plugin marketplace add yennanliu/InvestSkill
/plugin install us-stock-analysis
/stock-eval AAPL
```

Whether you're a retail investor researching your next position, a quantitative developer building trading systems, or a financial analyst automating routine tasks, InvestSkill provides the AI-powered analysis capabilities you need—right where you work.

### **Remember**

InvestSkill is a **tool for analysis and education**, not a source of financial advice. Markets are inherently unpredictable, and past performance doesn't guarantee future results. Always:
- Conduct thorough due diligence
- Understand the risks involved
- Diversify your investments
- Consult qualified financial professionals
- Never invest more than you can afford to lose

---

**Ready to transform your investment analysis workflow?** Start exploring InvestSkill today and experience the power of AI-driven financial research integrated directly into your development environment.

**Project Repository**: [https://github.com/yennanliu/InvestSkill](https://github.com/yennanliu/InvestSkill)

**Questions or feedback?** Open an issue or join the discussion on GitHub!

---

*InvestSkill is an independent open-source project and is not affiliated with any brokerage, financial institution, or investment advisor. Use at your own discretion and responsibility.*
