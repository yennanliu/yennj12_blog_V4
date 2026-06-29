---
title: "Cloudflare AI 安全稽核系統（三）：LLM Agent 的安全反模式——十個讓報告失去公信力的做法"
date: 2026-06-29T11:00:00+08:00
draft: false
description: "從 Cloudflare security-audit-skill 的設計原則出發，系統化整理 LLM agent 做安全稽核時最常見的十個反模式，以及如何在 agent pipeline 設計中從根源消除這些問題"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "Security", "LLM", "Cloudflare", "Anti-Pattern", "System Design", "Prompt Engineering", "Agent Pipeline"]
authors: ["yen"]
readTime: "22 min"
---

> 一份有三個真實 MEDIUM 漏洞的報告，  
> 比一份有三十個「潛在可能理論上存在風險」的報告有用十倍。  
> 安全報告的公信力一旦失去，工程師會停止閱讀它。

---

## 一、為什麼 LLM Agent 特別容易產生廢話安全報告

LLM 有一個普遍的傾向：**它會試圖看起來有幫助**。

在安全稽核的場景，這個傾向帶來的問題是：

```
工程師期待的 LLM 行為：
  如果沒找到漏洞 → 說「我沒找到漏洞，這個部分看起來安全」

LLM 實際的行為：
  如果沒找到確定的漏洞 → 說「這裡可能存在潛在的風險...」
                         「雖然沒有明確的漏洞，但理論上...」
                         「建議加強這部分的防護，因為...」
```

這就是「廢話型安全報告」的根源——它讓 LLM 看起來有在做事，但對工程師毫無價值。

Cloudflare 的 `security-audit-skill` 明確列出了這個問題的解法，也列出了最常見的反模式。本篇把這些反模式系統化整理，並從 agent pipeline 設計的角度說明如何從根源消除。

---

## 二、反模式地圖

```
十個反模式的分類：

┌─────────────────────────────────────────────────────────────┐
│  類型 A：「看起來嚴格，實際上沒用」的 finding               │
│    反模式 1：OWASP checklist 當 bug list                    │
│    反模式 2：用模糊語言掩蓋不確定性                         │
│    反模式 3：Defense-in-depth 缺失膨脹成漏洞                │
│    反模式 4：部署情境視而不見                               │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  類型 B：「用量充數」的報告結構問題                         │
│    反模式 5：用 LOW 充厚度                                  │
│    反模式 6：只說壞處，不說好處                             │
│    反模式 7：不提歷史漏洞基準                               │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  類型 C：「懶惰的調查」導致的誤判                           │
│    反模式 8：太快放棄                                       │
│    反模式 9：不驗證 parser/runtime 行為假設                 │
│    反模式 10：不做根本原因分析就重複報告                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、類型 A：「看起來嚴格，實際上沒用」的 Finding

### 反模式 1：把 OWASP 偏離當成 Bug

**症狀：**
```
Finding: "Missing Content-Security-Policy header"
Severity: MEDIUM
Description: "The application does not implement CSP,
              which is recommended by OWASP."
```

**問題：**

OWASP 是 checklist，不是 bug list。

「偏離 OWASP 建議」不等於「存在可利用的漏洞」。缺少 CSP 在以下情況根本不重要：

- 這是一個純 API server，沒有 HTML 回應
- CSP 在 upstream reverse proxy 已經設定
- 這個應用沒有 XSS 的攻擊面（沒有 user-controlled output 進入 HTML）

**正確做法：**
```
錯的：「沒有 CSP，違反 OWASP」→ MEDIUM

對的：先問「這個應用有 XSS 的攻擊面嗎？」
       ↓ 有 user input 進入 HTML，且有 XSS 漏洞
       → 報告那個 XSS 漏洞（CSP 的缺失在 impact 裡提一筆）
       ↓ 沒有 XSS 的攻擊面
       → CSP 是 hardening note，不是漏洞
```

**如何在 agent 設計中消除：**

Hunt agent 的指令要明確：「OWASP 偏離本身不是 finding。你需要找到具體的攻擊路徑。」

---

### 反模式 2：用模糊語言掩蓋不確定性

**症狀：**
```
"This function could theoretically be vulnerable..."
"An attacker might potentially exploit..."
"There is a possibility that..."
"This may lead to..."
```

**問題：**

這些語言是 confirmation bias 的產物——agent 覺得「這裡看起來有問題」，但沒有花時間確認，就用模糊語言留下後路。

對工程師來說，這類 finding 沒有可操作性：

```
工程師讀到「could theoretically be vulnerable」的反應：
  「我要怎麼修？」→ 不知道
  「這個有多嚴重？」→ 不知道
  「這是真的問題嗎？」→ 不知道
  
  結果：把這條 finding 標記為低優先，下次再說。
  永遠不會修。
```

**正確做法：**

```
二元原則：
  能 exploit → 說具體怎麼 exploit，用什麼輸入，得到什麼結果
  不能 exploit → 說沒有這個漏洞，或說為什麼這個路徑是安全的

沒有「可能」、「也許」、「理論上」的空間。
```

**如何在 agent 設計中消除：**

Validation phase 的 agent 被明確指令：拒絕所有包含「potentially」「theoretically」「might」的 finding，除非 finding 中同時有具體的 exploit 示範。

---

### 反模式 3：Defense-in-Depth 缺失膨脹成漏洞

**症狀：**
```
Finding: "Insufficient output encoding"
Severity: HIGH
Description: "Output encoding is not applied in the template layer.
              An attacker could inject malicious scripts."

（但 input validation 在入口已經過濾了所有 HTML 字符）
```

**問題：**

這個 finding 的 severity 是錯的——即使 output encoding 缺失，攻擊者也無法注入，因為 input 在進入系統之前就被清理了。

報告一個「在現有防禦下無法被利用的缺失」，會讓工程師做不必要的工作，並且讓報告的 credibility 下降（「這個 AI 說的東西都是廢話」）。

**判斷框架：**

```
問題：如果攻擊者嘗試利用這個缺失，他能成功嗎？

能成功 → 漏洞，報告
  → Severity 看：likelihood × actual impact

不能成功，因為有其他 defense layer → Hardening note
  → 在報告的 "Hardening Recommendations" 區段提及
  → 說清楚：「X 缺失，但 Y 目前防禦了這個攻擊。如果 Y 被移除，X 會變成漏洞。」

不確定 → 繼續調查，不要猜
```

---

### 反模式 4：部署情境視而不見

**症狀：**
```
Finding: "No rate limiting on authentication endpoint"
Severity: HIGH
Description: "The /api/login endpoint has no rate limiting,
              allowing brute force attacks."

（但這個服務部署在 Cloudflare Workers 後面，
  Cloudflare 的 WAF 和 Rate Limiting 在邊緣已經啟用）
```

**問題：**

孤立地看 codebase 而不考慮部署情境，會產生大量的「在生產環境中實際上已經被保護了」的 finding。

**正確做法：**

Recon phase 的 Agent 1a 要明確調查部署模型：

```
調查清單：
  - 有沒有 reverse proxy / CDN？（Cloudflare、Nginx、AWS ALB）
  - 有沒有 WAF？（Cloudflare WAF、AWS WAF、ModSecurity）
  - 有沒有 API gateway？（Kong、AWS API Gateway）
  - 這些組件有沒有提供額外的安全功能？

這些資訊要進入 architecture.md，
所有 Hunt agents 都要看這份文件，
在評估 finding severity 時把部署情境納入考量。
```

---

## 四、類型 B：「用量充數」的報告結構問題

### 反模式 5：用 LOW 充厚度

**症狀：**

```
報告包含：
  - 1 個 HIGH
  - 2 個 MEDIUM
  - 15 個 LOW（missing X-Frame-Options、console.log in production、
                 outdated dependency version、...）

工程師看到 18 個 finding，感覺這份報告很詳盡。
```

**問題：**

15 個 LOW 沒有讓報告更有價值——它讓工程師花時間在「很多可能根本不重要的東西」上，降低了他們對真正重要的 HIGH 和 MEDIUM 的關注度。

**Cloudflare 的明確原則：**

> 「3 個 MEDIUM 比 10 個 LOW 有用。報告的長度應該反映 codebase 的複雜度，不是用來填充的。」

**正確做法：**

```
LOW 的處理方式：
  - 合理的 LOW（真的有 impact，只是機率低）→ 簡短列出，不長篇大論
  - 「感覺應該要修」但無法 exploit → Hardening note，不是 finding
  - 信息量低的 LOW（outdated dep version）→ 可以省略，或只在 appendix 提

原則：報告的品質 = 每個 finding 的平均可操作性
```

**如何在 agent 設計中消除：**

Report phase 的 agent 有明確指令：「LOW 需要有明確的攻擊情境才能列入。如果一個 LOW 的攻擊情境是『在非常特定的條件下，攻擊者可以獲得一些額外資訊』，考慮是否真的需要列出。」

---

### 反模式 6：只說壞處，不說好處

**症狀：**

報告裡全是 finding，沒有提到這個 codebase 做得好的地方。

**問題：**

這讓報告失去可信度——一個工程師看到一份「只有問題、沒有優點」的報告，第一個反應是「這個 AI 只會說問題，不懂我們的系統」。

更重要的是：說明「哪裡做得好」讓工程師知道這份報告有真正讀過程式碼，而不是在亂槍打鳥。

**Cloudflare 的明確原則：**

> 「如果 auth 做得很扎實，就明確說出來。這樣你報的問題才有公信力。」

**正確做法：**

```
報告結構應包含 "Positive Patterns" 區段：

Positive Patterns:
- Authentication: JWT 驗證有做 algorithm pinning，防止 alg:none 攻擊
- SQL: 所有 database queries 都使用 parameterized statements，無例外
- Secrets: 沒有 hardcoded credentials，全部從環境變數讀取
- Dependencies: 核心依賴都在 latest stable 版本，無已知 CVE
```

---

### 反模式 7：不提歷史漏洞基準

**症狀：**

Finding 報告：「這個功能可能有 XSS」，但不提這種類型的 XSS 在同類型軟體中是否常見，或者歷史上是否真的被利用過。

**問題：**

沒有基準的 severity 評估是主觀的。「在理論上可能造成影響」和「這類漏洞在過去 2 年內已被實際利用過 X 次」的 severity 應該是不同的。

**正確做法：**

Validation phase 的 Baseline Test：

```
基準問題：
1. 這種漏洞在同類型軟體（同語言、同框架、同功能）中常見嗎？
2. 這種攻擊在 CVE 資料庫或 HackerOne 上有紀錄嗎？
3. 這個 codebase 的實際部署是否有額外的防護讓這個攻擊不切實際？

基準對 severity 的影響：
  常見且有真實案例 → 提升 severity
  理論上可能但無真實案例、攻擊成本極高 → 降低 severity
```

---

## 五、類型 C：「懶惰的調查」導致的誤判

### 反模式 8：太快放棄

**症狀：**

```
Finding 調查過程：
  發現：這個應用用了 parameterized queries
  結論：「沒有 SQL injection」
  
找到第一個 defense 就停下來。
```

**問題：**

「有 parameterized queries」不等於「沒有 SQL injection」。

正確的調查方式是繼續追：

```
追蹤清單（即使有 parameterized queries）：
  1. 有沒有任何 sql.raw() 或 .query(string) 的直接用法？
  2. ORM 的 query builder 有沒有允許 raw expression 的方法？
  3. 有沒有動態構建 ORDER BY 或 LIMIT 子句？（這些通常不能 parameterize）
  4. 有沒有 stored procedure 接受 user input？
  5. Migration scripts 或 admin 工具有沒有放鬆限制？
```

**Cloudflare 的明確原則：**

> 「找到一個 defense 不代表調查結束。繼續找可以繞過的方法。」

**如何在 agent 設計中消除：**

Hunt agent 的指令包含：「找到一個 defense 之後，你的任務是嘗試繞過它。如果確認無法繞過，才能標記這個路徑為安全。」

---

### 反模式 9：不驗證 Parser/Runtime 行為假設

**症狀：**

```
Finding: "JSON parsing allows prototype pollution"
Severity: HIGH
Description: "User-controlled JSON input could lead to prototype pollution
              because JSON.parse does not sanitize __proto__ keys."

（但這個應用用的是 Node.js 18+，
  V8 的 JSON.parse 在這個版本已經對 __proto__ 做了特殊處理）
```

**問題：**

Agent 的假設基於「它認為 JSON.parse 的行為應該是這樣」，而不是「JSON.parse 在這個 runtime 版本的實際行為」。

**正確做法：**

```
Parser/Runtime Test 的執行方式：

1. 確認使用的 library / runtime 版本
2. 查閱官方文件或 changelog
3. 如果不確定，明確標注「需要在實際環境中驗證」
4. 不要靠直覺或「我以為是這樣」

常見的假設陷阱：
  - URL parsing 在不同框架的行為差異
  - JSON 特殊 key 的處理（__proto__, constructor）
  - Multipart form parsing 的邊界處理
  - HTTP header 大小寫敏感性
  - Cookie 的 domain matching 規則
```

---

### 反模式 10：不做根本原因分析就重複報告

**症狀：**

```
Finding A: "XSS in /api/export endpoint"
Finding B: "Stored XSS via user profile"
Finding C: "Reflected XSS in search results"

（這三個 finding 的根本原因都是：template rendering 缺少 output encoding，
  而這個 template 組件在整個 codebase 都是共用的）
```

**問題：**

三個 finding 讓工程師誤以為有三個獨立的問題需要修，但實際上只需要修一個地方：那個 template 組件。

**正確做法：**

在 Validation phase 的去重步驟：

```
去重問題：
  「這些 finding 有相同的 root cause 嗎？」
  
  相同 root cause 的定義：
    - 相同的脆弱程式碼（即使被多個地方呼叫）
    - 相同的修復方式
  
  去重後的報告：
    Finding: "Missing output encoding in shared template component"
    Severity: HIGH
    Impact: "Affects /api/export, user profile, search results"
    Fix: "Add output encoding in template-engine.ts:render()"
    
這讓工程師知道：修一個地方，三個問題都解決。
```

---

## 六、這些反模式如何在 Pipeline 設計中被系統性消除

```
反模式與消除機制的對應：

反模式                          消除機制
────────────────────────────────────────────────────────────
OWASP checklist 思維            Hunt agent 指令：要求 exploit path
模糊語言（potentially/might）   Validation agent：拒絕無 exploit demo 的 finding
Defense-in-depth 膨脹           Validation Test 4（mitigation test）
忽略部署情境                    Recon Agent 1a + architecture.md
LOW 充數                        Report agent 指令：LOW 需要 attack scenario
只說壞處                        Report template：強制包含 Positive Patterns 區段
不做基準比較                    Validation Test 3（baseline test）
太快放棄                        Hunt agent 指令：找到 defense 後繼續嘗試繞過
不驗證 parser 假設              Validation Test 5（parser/runtime test）
重複報告同 root cause           Phase 3 去重步驟（先於 validation）
```

這個對應關係說明了一件事：**這些反模式不是靠「讓 LLM 更聰明」來解決的，而是靠 pipeline 設計——把消除反模式的步驟硬編碼進系統架構裡。**

---

## 七、從這個系統學到的 Agent Pipeline 設計原則

### 原則 1：把品質標準編碼進 Phase，而不是靠 Prompt

```
不好的做法：
  在每個 agent 的 prompt 裡寫：「請不要使用模糊語言」

好的做法：
  設計一個獨立的 Phase，專門負責拒絕模糊語言的 finding

原因：
  前者依賴 LLM 記住並遵守要求（在長 context 下容易忘）
  後者把這個要求硬化成系統結構，不依賴個別 agent 的記憶
```

### 原則 2：讓「否定」成為一個明確的任務

```
大多數 agent pipeline 只設計了「找東西」的 agent
Cloudflare 的系統明確設計了「否定東西」的 agent

Adversarial validation 的 agent 被明確告知：
  「你的任務是推翻這個 finding。假設它是錯的。」

這讓「否定」成為一個 first-class 任務，而不是「找 agent 的附帶工作」
```

### 原則 3：Fresh Context 作為最後防線

```
Phase 6 Independent Verification 的關鍵設計：
  全新的 agent，沒有任何前序 phase 的 context

這不是信任問題——而是因為帶著 context 的 agent 會下意識地
從「我已知的框架」來看問題，而不是真正重新讀一次

Fresh context agent 更容易發現：
  「等等，這行號是錯的」
  「這個函數在這個版本根本不存在」
  「找到的路徑其實不能到達這個 sink」
```

### 原則 4：Structured Output 是品質的基礎設施

```
為什麼 findings.json + schema validation 很重要：

1. 它強迫 agent 明確化每個 finding 的每個維度
   （不能只說「這裡有問題」，要填 severity, confidence, trace, conditions）

2. Validator 在格式錯誤時立刻報錯
   （不讓模糊的 finding 以「格式正確」的假象通過）

3. 跨 run 累積讓系統變得更強
   （每次 run 都基於上次的已知問題，往更深的地方探索）
```

---

## 八、給工程師的實踐建議

如果你在建構自己的 AI 安全稽核系統，或者在評估用 AI 做安全工作的方案：

```
評估清單：

□ 這個系統有沒有明確拒絕「potentially vulnerable」這類說法？
□ Validation 是否由獨立的 agent 做（而不是 self-review）？
□ 系統有沒有 structured output + schema validation？
□ 有沒有把部署情境（WAF、CDN、proxy）納入分析？
□ 報告有沒有包含「做得好的地方」？
□ 系統有沒有 deduplication before validation？
□ 有沒有機制讓多次 run 累積覆蓋率？

如果以上有超過 3 個「沒有」：
  這個系統可能會產生大量需要人工過濾的 false positives，
  長期使用會讓工程師失去信任。
```

---

## 九、結語：AI 安全工具的成熟度標誌

Cloudflare 這個 repo 最有意思的地方，是它把「反模式清單」和「消除反模式的機制」都公開了。

這代表他們在建這個系統的過程中，犯過這些錯，看到過這些問題，然後系統性地把修正編碼進 pipeline 的設計裡。

這是 AI agent 系統從「玩具」走向「生產可用」的關鍵路徑：

```
玩具：讓 LLM 做事，看輸出結果
生產可用：
  1. 知道 LLM 會在哪裡出錯
  2. 設計 pipeline 結構來系統性消除這些錯誤
  3. 有 structured output + validation 讓錯誤無法通過
  4. 有 independent verification 作為最後防線
```

這不是「信任 AI」——這是「設計一個讓 AI 的錯誤在到達你之前就被擋掉的系統」。

---

## 系列導覽

- [第一篇](/posts/cloudflare-security-audit-skill-part1-pipeline-zh/)：六階段 Pipeline 全解析
- [第二篇](/posts/cloudflare-security-audit-skill-part2-agent-design-zh/)：Agent 設計深潛——Hunt 策略、Sub-Agent Spawning、Adversarial Validation
- **第三篇（本篇）**：LLM Agent 的安全反模式——十個讓報告失去公信力的做法
