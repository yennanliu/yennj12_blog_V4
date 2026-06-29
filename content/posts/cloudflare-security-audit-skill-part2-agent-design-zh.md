---
title: "Cloudflare AI 安全稽核系統（二）：Agent 設計深潛——Hunt 策略、Sub-Agent Spawning、Adversarial Validation"
date: 2026-06-29T10:00:00+08:00
draft: false
description: "深入拆解 security-audit-skill 的 Agent 設計：Hunt phase 怎麼派 agent、sub-agent 什麼時候 spawn、adversarial validation 為什麼是 multi-agent 系統的核心防線"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Agent", "Multi-Agent", "Security", "LLM", "Cloudflare", "System Design", "Adversarial", "Agent Pipeline"]
authors: ["yen"]
readTime: "20 min"
---

> 單一 agent 做安全稽核，最大的問題不是「能力不夠」，  
> 而是「confirmation bias」——它既找漏洞，又驗證自己找到的漏洞。  
> Cloudflare 的解法是：讓找漏洞的 agent 和否定漏洞的 agent 永遠是不同的人。

---

## 一、為什麼 Multi-Agent 在安全稽核場景特別有價值

安全稽核和一般的「讓 AI 寫程式」任務有一個關鍵差異：

```
一般 AI 任務的正確性標準：
  輸出可以被執行 → 執行結果符合預期

安全稽核的正確性標準：
  找到的漏洞可以被 exploit → exploit 確實成功
  沒找到的地方確實沒有漏洞
```

第二個標準極難用單一 agent 達到，原因有三：

**原因 1：Context window 污染**
一個 agent 如果既做 Recon 又做 Hunt，它已經建立了對這個系統的「地圖」。這個地圖讓它不容易發現地圖之外的東西——因為它不會主動去懷疑自己的地圖。

**原因 2：Confirmation bias**
找到「可能的漏洞」之後，同一個 agent 驗證時會下意識地尋找支持的證據，而不是反駁的證據。

**原因 3：Context 深度 vs 廣度的矛盾**
深入追蹤一條可疑的程式碼路徑，和廣泛掃描整個 codebase，是兩種相互競爭的任務——在同一個 context window 裡很難同時做好。

Multi-agent 架構解決了這三個問題。

---

## 二、Hunt Phase 的 Agent 分配策略

### 按什麼維度分 Agent？

```
維度 1：攻擊類別（Attack Class）
┌──────────────────────────────────────────────────────────────┐
│  Agent-Injection     → 追蹤所有 untrusted input 到 sink      │
│  Agent-AccessCtrl    → 越權、IDOR、privilege escalation      │
│  Agent-Crypto        → 弱隨機數、hardcoded secrets、timing   │
│  Agent-BusinessLogic → 狀態機、競爭條件、數值邊界            │
│  Agent-FeatureAbuse  → 合法功能被惡用的路徑                  │
│  Agent-Chained       → 多步驟組合攻擊                        │
│  Agent-Wildcard      → 探索意外的地方                        │
└──────────────────────────────────────────────────────────────┘

維度 2：子系統（Subsystem）
┌──────────────────────────────────────────────────────────────┐
│  Agent-Auth-Injection        → auth 子系統 × injection       │
│  Agent-Auth-AccessCtrl       → auth 子系統 × 越權            │
│  Agent-Plugin-Injection      → plugin 系統 × injection       │
│  Agent-Media-Resource        → media pipeline × file handling│
└──────────────────────────────────────────────────────────────┘
```

兩個維度可以組合。系統的設計原則是：**當子系統有明顯的安全邊界時，按子系統切分比只按攻擊類別更有效。**

### Agent 數量決策矩陣

```
codebase 大小 × 複雜度 → agent 數量

          │  低複雜度   │  中複雜度   │  高複雜度
          │（單一功能） │（Web API） │（plugin/multi-tenant）
──────────┼────────────┼────────────┼─────────────────────
< 10K行   │   3-4      │    4-6     │    6-8
10K-100K  │   4-6      │    6-8     │    8-12
> 100K    │   6-8      │    8-12    │    12+

高複雜度特徵：
- Plugin system（第三方程式碼執行）
- Multi-tenant（跨用戶隔離）
- 複雜 auth chain（多層授權）
- 外部整合（Webhook、第三方 API 回調）
```

### 每個 Hunt Agent 的必要 Context

每一個 Hunt agent 啟動時，必須收到以下資訊：

```
1. architecture.md 的完整內容（Phase 1 的輸出）
   → 讓 agent 知道整體架構、信任邊界、輸入端口

2. 負責的攻擊類別 + 調查範圍
   → 「你負責 injection 類，重點是這幾個 endpoint」

3. 相關的起始檔案路徑
   → 「從這幾個檔案開始，往上往下追蹤」

4. Hunting methodology
   → 攻擊者思維的指令集（見下節）

5. Validation rules
   → 什麼樣的 finding 才算可以回報
```

---

## 三、攻擊者思維的具體實作

這是整個系統中最關鍵的部分——**如何讓 agent 真的像攻擊者一樣思考，而不是像 code reviewer。**

### 核心差異：防禦性 vs 攻擊性讀程式碼

```
防禦性讀程式碼（產生廢話 finding）：
  問題：「這個函數有做 input validation 嗎？」
  看到：有 if (!input) throw new Error(...)
  結論：「有 validation，安全」

攻擊性讀程式碼（產生有用 finding）：
  問題：「我能不能繞過這個 validation？」
  看到：if (!input) throw new Error(...)
  思考：
    - 這個 check 只 check null/undefined，不 check 空字串？
    - 如果我傳 "  "（空白字串）呢？
    - 如果我傳一個很長的字串呢？
    - 這個 input 在後面被怎麼使用？
    - 使用點有沒有額外的 assumption？
```

### 六個攻擊性調查角度

| 角度 | 問什麼 | 例子 |
|------|--------|------|
| 錯誤路徑 | 錯誤處理路徑有沒有特殊行為？ | 錯誤訊息洩漏 stack trace、路徑資訊 |
| 邊界條件 | 極端輸入會發生什麼？ | 負數、零、MAX_INT、空字串、null byte |
| 組件假設 | A 組件對 B 組件有沒有隱性假設？ | Auth middleware 假設 JSON，攻擊者送 form-encoded |
| 操作順序 | 如果我改變操作的順序？ | 先 delete 再 update，在刪除和確認之間的 race |
| 並發情境 | 同時發兩個請求會怎樣？ | TOCTOU，double-spend |
| Parser 差異 | 不同組件 parse 同一個輸入的結果是否一致？ | URL parsing、JSON parsing、header parsing |

---

## 四、Sub-Agent Spawning：深度 vs 廣度的解法

### 問題的本質

Hunt phase 的主 agent 面對一個根本矛盾：

```
廣度掃描需要：在整個 codebase 跳來跳去，找可疑的點

深度追蹤需要：從一個可疑的點，往上往下追蹤所有相關路徑

這兩件事在同一個 context window 裡是互相競爭的——
做深度追蹤的細節會擠壓廣度掃描的空間，反之亦然。
```

### Sub-Agent 的觸發條件

主 agent 在發現以下情況時，應該 spawn sub-agent 而不是自己深入：

```
觸發條件 1：複雜的 data flow
主 agent 發現：一個輸入點 → 經過多個中間轉換 → 可能到達危險 sink
觸發 sub-agent：專門追蹤這條 data flow 的每一步

觸發條件 2：不熟悉的組件
主 agent 發現：一個第三方 library 的非標準用法
觸發 sub-agent：深入研究這個 library 的行為和邊界情況

觸發條件 3：複雜的 auth 邏輯
主 agent 發現：authorization 邏輯分散在多個 middleware 和 helper
觸發 sub-agent：完整建構這條 auth 邏輯的地圖

觸發條件 4：Plugin / extension 系統
主 agent 發現：第三方程式碼執行的入口點
觸發 sub-agent：深入分析 sandbox 邊界和逃逸路徑
```

### Sub-Agent 架構圖

```
Hunt Phase 的 Agent 樹狀結構：

Phase 2 Orchestrator
    │
    ├─ Hunt Agent: Injection
    │       │
    │       ├─ 掃描所有 SQL query 點
    │       │       │
    │       │       └─ 發現複雜的 ORM query builder
    │       │               │
    │       │               └─ [spawn] Sub-Agent: ORM Deep Dive
    │       │                           → 分析所有 .raw() 呼叫
    │       │                           → 追蹤 user input 到 raw query 的路徑
    │       │
    │       └─ 掃描所有 template rendering 點
    │               │
    │               └─ 發現 user-controlled template 路徑
    │                       │
    │                       └─ [spawn] Sub-Agent: Template Injection
    │                                   → 確認 template engine 的 sandbox
    │                                   → 測試 sandbox 逃逸路徑
    │
    ├─ Hunt Agent: Access Control
    │       │
    │       └─ ...
    │
    └─ Hunt Agent: Business Logic
            │
            └─ ...
```

### Sub-Agent 的好處

1. **Context 隔離**：sub-agent 有乾淨的 context，不被主 agent 的廣度掃描污染
2. **深度不受限**：主 agent 可以繼續做廣度掃描，sub-agent 獨立做深度追蹤
3. **平行加速**：多個 sub-agent 可以同時追蹤不同的可疑路徑

---

## 五、Adversarial Validation：這個系統最重要的設計

### 為什麼 self-review 不夠

```
情境：Hunt Agent 找到了一個可能的 IDOR

Hunt Agent 的心理狀態：
  「我已經相信這個 IDOR 存在了。」
  「我找到的時候，我相信它是真的。」
  「現在讓我驗證一下...」
  
  驗證過程：
    - 尋找支持的證據 ✓（因為我相信它存在，我更容易注意到支持的東西）
    - 忽略反駁的證據 ✓（不自覺地）
    - 看到 middleware 但不夠仔細 ✓（我已經有結論了）
    
  結果：假陽性通過驗證
```

### Adversarial Validation 的實作

Phase 3 啟動全新的 validator agents，這些 agents 的指令是：

```
你的任務是推翻（disprove）以下 finding。
假設 finding 是錯的，直到你找到無法反駁的證據。

具體步驟：
1. 讀實際的原始碼（不是 Hunt agent 描述的——讀真正的檔案）
2. 找所有可能阻擋這個攻擊的 defense layer
3. 嘗試構建具體的攻擊請求——如果構建不出來，finding 被拒絕
4. 確認攻擊者能實際取得什麼——不接受「可能洩漏一些資訊」
```

### 五個 Validation 測試

```
┌─────────────────────────────────────────────────────────────┐
│ Test 1: Exploitation Test                                   │
│   問：資料流真的如 finding 所說嗎？                         │
│   做：追蹤從入口到 sink 的每一步                            │
│   要求：構建出能觸發的具體輸入                              │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Test 2: Impact Test                                         │
│   問：攻擊者真正能取得什麼？                                │
│   拒絕："might leak some field names"                       │
│   接受："can read any user's email and hashed password"     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Test 3: Baseline Test                                       │
│   問：同類型的軟體通常有這個問題嗎？                        │
│        這個應用的實際部署環境有什麼額外防護？                │
│   用途：避免把「行業標準行為」報成漏洞                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Test 4: Mitigation Test                                     │
│   問：有沒有其他 defense layer 阻擋這個攻擊？               │
│   找：WAF、rate limiter、upstream proxy、framework default  │
│   原則：defense-in-depth 缺失 ≠ 漏洞（見下節）              │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Test 5: Parser/Runtime Test                                 │
│   問：你對這個 library / runtime 的假設符合實際規格嗎？     │
│   做：查文件或原始碼，不要靠直覺                            │
│   常見錯誤："我以為 JSON.parse 會拒絕這個輸入"              │
└─────────────────────────────────────────────────────────────┘
```

### Defense-in-Depth 缺失的判斷

這是 validation 最容易出錯的地方，需要明確的規則：

```
情境 A（不是漏洞）：
  Layer A（Input validation）：存在，能有效阻擋攻擊
  Layer B（Output encoding）：缺失
  
  → Hardening note，不是漏洞
  → 理由：攻擊路徑被 Layer A 切斷
  → 在報告中：列在 "Hardening Recommendations" 區段

情境 B（是漏洞）：
  Layer A（Input validation）：存在，但有 edge case X 可以繞過
  Layer B（Output encoding）：缺失
  
  → 漏洞，severity 取決於 edge case X 的可利用性
  → 理由：Layer A 不可靠，Layer B 缺失讓攻擊成功

情境 C（需要深挖）：
  Layer A：存在
  找到的 finding：Layer A 是否真的能阻擋所有情況？
  
  → 繼續追查 Layer A 的所有可能繞過路徑
  → 「有 parameterized queries」不等於「沒有 SQL injection」
  → 去找所有 sql.raw() 或 query builder 的 concatenation
```

---

## 六、去重（Deduplication）的設計

在 adversarial validation 之前，Phase 3 還要做去重——合併從不同 Hunt agents 回報的相同根本原因。

### 為什麼先去重再驗證

```
不去重直接驗證的問題：
  Hunt Agent A（Injection）：「/api/export 沒有做 output encoding」
  Hunt Agent B（Feature Abuse）：「/api/export 可以 XSS」
  
  Validator 花兩倍時間驗證同一個漏洞
  報告裡同一個漏洞出現兩次，讀者混亂

去重後驗證：
  合併成：「/api/export XSS via missing output encoding」
  一次驗證，一次報告
```

### 去重的判斷標準

```
相同 root cause = 同一個 finding：
  - 相同的脆弱程式碼路徑
  - 相同的攻擊者能力（即使攻擊向量不同）
  - 相同的修復建議

不同 finding（即使看起來相似）：
  - 不同的 root cause（即使症狀相似）
  - 不同的攻擊者能力（即使脆弱點相同）
  - 不同的修復方案
```

---

## 七、Structured Output：讓結果可被程式消費

### findings.json 的核心 Schema

```json
{
  "findings": [
    {
      "verdict": "confirmed",          // confirmed | rejected
      "title": "IDOR in user profile", // 簡短，人可讀
      "severity": "HIGH",              // CRITICAL|HIGH|MEDIUM|LOW|INFO
      "confidence": "HIGH",            // 對 finding 的信心程度
      
      "description": "...",            // 漏洞說明
      "root_cause": "...",             // 根本原因
      
      "trace": {                       // 資料流追蹤
        "entry": "GET /api/users/:id",
        "sink": "db.query('SELECT * FROM users WHERE id = ?', [req.params.id])",
        "path": ["src/handlers/users.ts:127", "src/db/queries.ts:45"]
      },
      
      "conditions": "...",             // 觸發條件
      "execution": "...",              // 具體攻擊步驟
      
      "remediation": {
        "short": "Add authorization check",
        "detail": "..."
      },
      
      "cwe_id": "CWE-284",            // 標準漏洞分類
      "file_paths": ["src/handlers/users.ts"]
    }
  ]
}
```

### 為什麼 Structured Output 重要

```
只有 REPORT.md（純文字）的問題：
  - 無法被 CI/CD pipeline 消費
  - 跨多次 run 難以比較（人工閱讀差異）
  - 無法自動整合進 security dashboard
  - severity 統計需要人工計算

有 findings.json 的好處：
  - CI 可以讀取：severity >= HIGH 就 fail build
  - 多次 run 累積：讀取上次的 findings.json，跳過已知問題
  - Dashboard 整合：自動追蹤 finding 的修復狀態
  - 統計分析：按 CWE 分類統計、趨勢追蹤
```

### Node.js Validator 的角色

`validate-findings.cjs` 在 Phase 5 結束時執行：

```
1. 讀取 findings.json
2. 對照 report-schema.json 驗證每個欄位
3. 檢查必填欄位是否存在
4. 驗證 enum 值是否合法（如 severity 只能是預定義的值）
5. 如果驗證失敗：回報錯誤，要求 agent 修正

這確保：
  - 格式錯誤在 Phase 5 就被擋掉，不進入 Phase 6
  - Phase 6 的 independent verification 基於正確格式的輸入
```

---

## 八、為什麼這些設計決策是對的

| 設計 | 解決的問題 | 代價 |
|------|-----------|------|
| Adversarial validation（不同 agent） | Confirmation bias | 更多 agent，成本 ↑ |
| Sub-agent spawning | Context window 深度/廣度矛盾 | Orchestration 複雜度 ↑ |
| 先去重再驗證 | 避免重複驗證同一 root cause | 需要 dedup 邏輯 |
| Structured output + validator | 輸出可被程式消費 | 需要維護 schema |
| Phase 6 獨立驗證 | 事實宣稱的準確性 | 額外一輪 agent |
| 多次 run 累積 | 單次 run ~50% 覆蓋率 | 需要狀態管理 |

**翻轉條件**（什麼時候可以簡化）：
- 快速 triage：可以省略 Phase 6，但標注「事實未獨立驗證」
- 小型 codebase：Hunt phase 3-4 agents 而非 8-12
- 已知安全的子系統：可以縮減對應的 Hunt agents

---

## 系列導覽

- [第一篇](/posts/cloudflare-security-audit-skill-part1-pipeline-zh/)：六階段 Pipeline 全解析
- **第二篇（本篇）**：Agent 設計深潛——Hunt 策略、Sub-Agent Spawning、Adversarial Validation
- [第三篇](/posts/cloudflare-security-audit-skill-part3-llm-security-zh/)：LLM Agent 的安全反模式——十個讓報告失去公信力的做法
