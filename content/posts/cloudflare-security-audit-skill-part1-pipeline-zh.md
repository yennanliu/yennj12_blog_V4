---
title: "Cloudflare AI 安全稽核系統（一）：六階段 Multi-Agent Pipeline 全解析"
date: 2026-06-29T09:00:00+08:00
draft: false
description: "Cloudflare 開源了內部 AI 安全稽核系統 security-audit-skill——一個教科書級的六階段 Multi-Agent Pipeline：Recon→Hunt→Validate→Report→Structured Output→Verify，本篇拆解整個架構設計與核心設計決策"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "Security", "Multi-Agent", "Pipeline", "LLM", "Cloudflare", "System Design", "Open Source"]
authors: ["yen"]
readTime: "18 min"
---

> 多數 AI 安全工具的做法：把程式碼丟給一個 LLM，問它「有沒有漏洞？」  
> Cloudflare 的做法：六個獨立 phase、多個平行 agent、adversarial validation、獨立事實查核。  
> 差別不在「用了 AI」，而在「怎麼讓 AI 不說廢話」。

---

## 一、為什麼這個 repo 值得深讀

Cloudflare 在 2024 年開源了 [`security-audit-skill`](https://github.com/cloudflare/security-audit-skill)，把他們內部用 AI agent 做安全稽核的系統公開出來。

這不是一個「讓 ChatGPT 讀你的程式碼」的玩具。這是一個：

- **六階段 orchestrated pipeline**，每個 phase 有明確的輸入/輸出
- **Multi-agent 架構**，同一 phase 內多個 agent 平行執行
- **Adversarial validation**：找漏洞的 agent 和驗證漏洞的 agent 是不同的
- **Structured output + schema validation**：輸出有嚴格的 JSON schema
- **Independent verification**：最後一道全新 agent 逐一查核每一個事實宣稱

```
整個 Pipeline 的資料流：

codebase
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Recon                                             │
│  Agent 1a (Overview)  Agent 1b (Trust)  Agent 1c (Input)   │
│           └─────────────────────────────┘                  │
│                        ▼                                    │
│                  architecture.md                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Hunt                                              │
│  Agent(injection) Agent(access) Agent(crypto) Agent(logic)  │
│  Agent(feature)   Agent(chain)  Agent(wildcard) ...         │
│  每個 agent 可以 spawn sub-agents                           │
└─────────────────────────────────────────────────────────────┘
    │  raw findings
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: Validate                                          │
│  全新 agents 嘗試「推翻」每一個 finding                     │
│  adversarial review → 殺掉 false positives                  │
└─────────────────────────────────────────────────────────────┘
    │  validated findings
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Report                                            │
│  REPORT.md（人看的）+ FINDINGS-DETAIL.md（MEDIUM+ 詳細）   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: Structured Output                                 │
│  findings.json（符合 report-schema.json）                   │
│  Node.js validator 驗證格式                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 6: Independent Verification                          │
│  全新 agents 逐一比對：每一個事實宣稱 vs 實際原始碼         │
│  最後一道防線                                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
最終報告（可信賴的）
```

---

## 二、Phase 1：Recon（偵察）

### 目標

在進攻之前，先完整理解這個系統是什麼、信任邊界在哪裡、外部輸入從哪裡進來。

### 三個平行 Research Agent

```
Phase 1 並行架構：

                    codebase
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    Agent 1a        Agent 1b     Agent 1c
   ─────────        ────────     ────────
   Overview &       Trust        Input
   Tech Stack       Boundaries   Surface
                    & Access     Inventory
                    Control
          │            │            │
          └────────────┼────────────┘
                       ▼
                architecture.md
              （下一 phase 的輸入）
```

**Agent 1a — Overview & Tech Stack**
- 這是什麼類型的應用？（Web API / CLI / daemon / library）
- 部署模型是什麼？（container / serverless / on-prem）
- 使用者類型有哪些？（anonymous / authenticated / admin）
- 技術棧：語言、框架、資料庫
- 類比基準：跟什麼樣的軟體比較（同類型的安全基準）

**Agent 1b — Trust Boundaries & Access Control**
- 所有 authentication 機制在哪裡？
- authorization 邏輯在哪裡？
- 特權分離（privilege separation）如何實作？
- 信任邊界：什麼是 trusted / untrusted？

**Agent 1c — Input Surface Inventory**
- 所有網路 endpoints（REST / GraphQL / WebSocket / RPC）
- 檔案上傳、IPC 機制、環境變數
- 所有「危險 sink」：SQL 執行、shell 執行、template rendering、檔案寫入
- 這是最關鍵的輸出——Hunt phase 的攻擊起點

### 輸出：architecture.md

這份文件是整個 pipeline 的基礎。後續所有 Hunt agent 都會把這份文件當成 context 的一部分。

如果 codebase 有特殊複雜度（plugin system、multi-tenant、複雜 auth chain），Recon phase 會 spawn 額外的 research agent 深入挖掘。

---

## 三、Phase 2：Hunt（攻擊）

### 設計哲學：攻擊者思維

Hunt phase 的核心指令不是「檢查有沒有漏洞」，而是「嘗試打破它」。這是關鍵的差異：

```
防禦者思維（錯的）：
"有沒有 SQL injection 防護？" → 看到 parameterized queries → 標記為安全

攻擊者思維（對的）：
"我要嘗試注入" → 找到所有 sql.raw() 的呼叫
              → 追蹤每一個的輸入來源
              → 有沒有哪一條路徑沒有被 parameterize？
              → 有沒有特殊的 edge case？
```

### 七個攻擊面向 + 兩個特殊類別

每個攻擊面向都有對應的 agent（或多個 agent）：

| 面向 | 代表攻擊手法 |
|------|------------|
| Injection | SQL/HTML/Shell/Template/Path injection，含 stored/second-order |
| Access Control | 越權存取、IDOR、privilege escalation |
| Resource & File Handling | Path traversal、SSRF、unsafe deserialization、TOCTOU race |
| Cryptography & Secrets | 弱隨機數、hardcoded secrets、broken key derivation、timing side-channel |
| Business Logic | 狀態機違規、競爭條件、數值操控、隱性信任假設 |
| Feature Abuse & Data Leakage | 合法功能被惡用：export 當資料外洩、search 當 oracle |
| Chained Attacks | 多步驟組合攻擊：info disclosure + IDOR、cross-component validation gap |
| Wildcard | 探索意外漏洞：奇特程式碼、半成品功能、undocumented endpoints |
| Obvious Things | Hardcoded credentials、unprotected debug endpoints、missing security headers |

### Agent 數量決策

```
小型 library（< 10K lines）：3-4 agents

中型 web app（10K-100K lines）：6-8 agents

大型應用（100K+ lines）或有複雜子系統：8-12+ agents
    → 不只按攻擊面向分
    → 也按子系統分：
      - auth subsystem × injection agents
      - plugin system × access control agents
      - media pipeline × resource handling agents
```

### Sub-Agent Spawning

這是這個系統最強大的特性之一：Hunt agent 在發現有趣的地方時，可以 spawn sub-agents 往更深的地方挖。

```
Hunt Agent（injection）
    │
    ├─ 發現一個複雜的 ORM 查詢構建器
    │       │
    │       └─ spawn Sub-Agent：專門分析這個 ORM 所有的 raw query 呼叫
    │
    └─ 發現一個 template engine 整合點
            │
            └─ spawn Sub-Agent：追蹤所有 user input 進入 template 的路徑
```

這讓 agent 可以在不耗盡主 context window 的情況下做深度分析。

---

## 四、Phase 3：Validate（驗證）

### Adversarial Review 的設計原則

這個 phase 的設計動機是：**找到漏洞的 agent 和驗證漏洞的 agent 不能是同一個。**

為什麼？因為發現漏洞的 agent 有 confirmation bias——它已經相信這個漏洞存在，驗證只是走過場。

解法：另一批全新的 agent，**以推翻為目標**，讀實際的原始碼：

```
Phase 2 找到的 finding：
"在 /api/users/:id 可以透過修改 id 存取其他用戶的資料"

Phase 3 Validator 的任務：
1. 找到實際的 handler 程式碼
2. 檢查每一層 middleware
3. 確認 auth middleware 是否有 per-resource check
4. 嘗試構建具體的攻擊請求
5. 確認影響：真的能拿到什麼？
```

### 五個驗證測試

| 測試 | 目的 |
|------|------|
| Exploitation test | 驗證資料流是否如 finding 所說；構建具體觸發輸入 |
| Impact test | 攻擊者真正能拿到什麼？不接受「只有 field names」 |
| Baseline test | 同類型軟體有這個問題嗎？歷史上真的被打過嗎？ |
| Mitigation test | 有沒有其他防禦層阻擋這個攻擊？ |
| Parser/runtime test | 假設是否符合實際規格，而不是直覺？ |

### 去重：先整合再驗證

在驗證之前，先把 Hunt phase 各 agent 報來的 findings 做 deduplication——不同 agent 從不同角度找到同一個根本原因的漏洞，要合併成一個 finding，避免報告膨脹。

---

## 五、Phase 4 & 5：Report 與 Structured Output

### 四個輸出文件

```
┌─────────────────────────────────────────────────────────────┐
│  REPORT.md                                                  │
│  ─────────                                                  │
│  • Executive summary                                        │
│  • Baseline comparison（跟同類型軟體比）                     │
│  • Findings table（嚴重度 × 數量）                          │
│  • 每個 finding 的：路徑、攻擊情境、影響、修復建議          │
│  • Hardening notes                                          │
│  • Positive patterns（做得好的地方——增加報告公信力）        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  FINDINGS-DETAIL.md                                         │
│  ──────────────────                                         │
│  只包含 MEDIUM 以上的 findings                              │
│  • 完整資料流（從入口到 sink 的每一行）                     │
│  • 具體觸發請求                                             │
│  • 攻擊者能取得什麼                                         │
│  • Baseline comparison                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  findings.json                                              │
│  ─────────────                                              │
│  符合 report-schema.json 的結構化輸出                       │
│  每個 finding 包含：                                        │
│  • severity（CRITICAL/HIGH/MEDIUM/LOW/INFO）                │
│  • verdict（confirmed/rejected）                            │
│  • attack_scenario（具體情境）                              │
│  • cwe_id（標準漏洞分類）                                   │
│  • file_paths（受影響的檔案）                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  architecture.md                                            │
│  ────────────────                                           │
│  Phase 1 產出，貫穿整個 pipeline                            │
└─────────────────────────────────────────────────────────────┘
```

### Structured Output 的重要性

`findings.json` 由 Node.js validator 驗證格式，這讓輸出可以：

- 被 CI/CD pipeline 消費
- 跨多次 run 累積比較（系統會讀取先前的 findings.json 避免重複報告）
- 整合進 security dashboard

---

## 六、Phase 6：Independent Verification（獨立驗證）

這是整個 pipeline 最後、也最微妙的一個 phase。

### 為什麼需要最後一道驗證？

即使通過了 Phase 3 的 adversarial review，仍然有一個問題：報告裡的**事實宣稱**（factual claims）是否準確？

- "在第 47 行的函數沒有做 input validation" → 第 47 行真的是那個函數嗎？
- "auth middleware 只驗證 token 存在，不驗證 scope" → 真的嗎？
- "這個 endpoint 沒有 rate limiting" → 真的沒有？或者在 upstream proxy 有？

### 做法

全新的 agent（沒有任何前序 phase 的 context）逐一讀取 `findings.json` 裡的每一個事實宣稱，並對照實際原始碼：

```
Verification Agent 的工作：

findings.json 中的一個 finding：
{
  "title": "IDOR in user profile endpoint",
  "file_paths": ["src/handlers/users.ts:127"],
  "description": "Missing per-resource authorization check"
}

Verification 步驟：
1. 讀 src/handlers/users.ts 第 127 行附近的程式碼
2. 確認這個 handler 是否真的缺少 per-resource check
3. 確認 middleware chain
4. 標記：verified / needs-correction
```

---

## 七、整個系統的設計原則

### 只報你能 exploit 的東西

這是整個系統最核心的原則，值得單獨強調：

```
不接受的 finding（佔篇幅但沒用）：
❌ "This function could theoretically be vulnerable to..."
❌ "An attacker might potentially..."
❌ "There is a possibility of..."

接受的 finding（有實際價值）：
✅ "Send POST /api/upload with Content-Type: text/html and body <script>...</script>
    The response will include the script tag unescaped.
    Attacker gains: XSS in the admin dashboard."
```

**有能力 exploit 就說，沒有就說沒有。沒有中間地帶。**

### Defense-in-depth 缺失不是漏洞

```
情境：
Layer A（Input validation）：存在，能擋住攻擊
Layer B（Output encoding）：缺失

這是漏洞嗎？

答案：不是漏洞，是 hardening note。
理由：攻擊被 Layer A 擋住了。Layer B 缺失是縱深防禦問題，
      但如果 Layer A 已經有效，這不構成可利用的漏洞。

什麼時候變成漏洞？
當 Layer A 有任何可繞過的條件時。
```

### 多次 run 是 additive

測試顯示，單次 run 大約只能找到所有漏洞的 50%。系統設計支援多次 run：

```
Run 1：找到 findings A, B, C
Run 2：讀取 findings.json，跳過已知的 A, B, C，
       專注於不同的程式碼路徑
       找到 findings D, E
Run 3：繼續累積...
```

---

## 八、為什麼選這個架構，不選別的

| 設計決策 | 選這個 | 不選那個 |
|---------|--------|--------|
| 多個 Hunt agent vs 一個 | 平行攻擊面向，不同 context window，互不干擾 | 單一 agent：context 污染，越寫越偏 |
| Adversarial validation vs self-review | 找漏洞的 agent 有 confirmation bias，新 agent 以反駁為目標 | 同一 agent review 自己的輸出：假驗證 |
| Phase 6 independent verify vs skip | 報告裡的行號、函數名可能是幻覺；最後一道確認 | 直接輸出：看起來正確但內容錯誤 |
| JSON schema + Node.js validator vs free-form | 可被程式消費、跨 run 累積、CI 整合 | Markdown only：人看可以，機器難處理 |
| architecture.md 先行 vs 直接攻擊 | 沒有地圖就會重複檢查同一個地方、漏掉不明顯的入口 | 直接 Hunt：散彈打鳥，覆蓋率低 |

**翻轉條件：**
- 如果 codebase 極小（< 1K lines），單一 agent 就夠，多 agent 的 orchestration overhead 不值得
- 如果只需要快速 triage，可以省略 Phase 6，但要在報告裡標注「未驗證事實準確性」

---

## 九、實際使用這個 skill 的流程

```bash
# 這個 skill 是 Claude Code skill，透過 /skill 或 slash command 觸發
# 基本用法：指向你的 repo

# 1. 確保 Claude Code 已安裝且在專案目錄
cd your-project

# 2. 執行 security audit skill
# 在 Claude Code 中輸入：
/security-audit

# 3. 系統會自動執行六個 phases，產出：
# - architecture.md
# - REPORT.md
# - FINDINGS-DETAIL.md
# - findings.json
```

系統也會讀取先前 run 的 `findings.json`，所以可以持續累積覆蓋率。

---

## 十、這個系統教會我們的事

Cloudflare 這個 repo 最有價值的地方，不只是「可以直接用的工具」，而是它示範了：

**如何設計一個讓 AI agent 不說廢話的系統。**

```
一般 AI 安全工具的問題：
LLM → 大量 "potentially vulnerable" → 工程師花時間逐一查 → 80% 是假陽性 → 喪失信任

這個系統的解法：
1. Recon 先建立地圖（減少盲目掃描）
2. Hunt 用攻擊者思維（要求具體 exploit，不接受猜測）
3. Validate 用 adversarial review（confirmation bias 消除）
4. Schema validation（格式錯誤在這裡被擋掉）
5. Independent verify（事實宣稱最後查核）

結果：3 個 confirmed MEDIUM 比 30 個 theoretical LOW 有用。
```

---

## 系列導覽

- **第一篇（本篇）**：六階段 Pipeline 全解析
- [第二篇](/posts/cloudflare-security-audit-skill-part2-agent-design-zh/)：Agent 設計深潛——Hunt 策略、Sub-Agent Spawning、Adversarial Validation
- [第三篇](/posts/cloudflare-security-audit-skill-part3-llm-security-zh/)：LLM Agent 的安全反模式——十個讓報告失去公信力的做法
