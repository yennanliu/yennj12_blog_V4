---
title: "FDE 面試準備指南（二十五）：RKK 實戰——Self-Reflection 與幻覺校正迴圈設計"
date: 2026-06-04T18:00:00+08:00
draft: false
weight: 25
description: "以系統設計視角拆解 Generator-Evaluator 雙節點架構：為什麼 LLM 需要自我檢查機制、Reflexion Pattern 的設計原理、如何防止反思迴圈變成無限循環，以及收斂保證的工程實踐"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Agent", "Self-Reflection", "Hallucination", "LangGraph", "Reflexion", "Generator-Evaluator", "System Design", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "17 min"
---

> LLM 的幻覺問題不會被「更好的 Prompt」完全消除。  
> 更實際的工程思路是：允許 LLM 犯第一次錯，  
> 但設計一個系統讓它能自己發現錯誤、自己修正。  
> 問題是：你怎麼確保「自我修正」不會無限進行下去？

---

## 面試情境

> **面試官：** 「在法務合約問答中，Agent 呼叫外部工具，但工具返回的 JSON 數據包含矛盾的條款。LLM 第一次生成時沒有注意到，產生了嚴重幻覺。你如何設計一個 Self-Reflection 架構，讓 Agent 在輸出最終答案前能自己檢查並校正？如何防止反思機制陷入死循環？」

---

## 一、核心問題：為什麼需要 Self-Reflection

```
沒有 Self-Reflection 的問題：

  Tool 回傳矛盾資料：
  第 3 頁：「違約金為 500 萬台幣」
  第 7 頁：「違約金為 50 萬台幣（與前款衝突）」

  LLM 第一次生成：
  「根據合約，違約金為 50 萬台幣。」（只看了第 7 頁，忽略矛盾）

  結果：
  └── 法務顧問基於錯誤資訊給建議
  └── 客戶簽了有利於對方的合約
  └── FDE 被客戶投訴

如果有 Self-Reflection：
  第一次生成後，由「審查者」指出：
  「你的答案說 50 萬，但第 3 頁寫的是 500 萬，兩者矛盾。請重新分析。」
  
  第二次生成：
  「合約中關於違約金存在矛盾條款：第 3 頁寫 500 萬，第 7 頁寫 50 萬。
   建議客戶在簽約前要求對方澄清哪一條款有效。」
  ← 這才是正確的專業回答
```

---

## 二、Reflexion Pattern：設計原理

```
Reflexion 的三個核心洞察：

洞察 1：同一個 LLM 作為生成者和評估者
  同樣的 Gemini Pro，給它不同的角色（System Prompt），
  它能同時做好「生成答案」和「找出答案的問題」

洞察 2：評估者的視角和生成者不同
  生成者的 System Prompt：「你是一個法務助理，根據合約回答問題」
  評估者的 System Prompt：「你是一個嚴格的法務審查員，專門找答案的問題」
  不同的視角 → 更容易發現問題

洞察 3：錯誤原因要結構化，不能只說「有問題」
  ❌ 「這個答案有問題，請重試」
  ✅ 「第 3 條和第 7 條數字矛盾（500 萬 vs 50 萬），答案沒有提及這個矛盾」
  結構化的錯誤原因 → 生成者能有針對性地修正
```

---

## 三、Generator-Evaluator 架構設計

```
┌──────────────────────────────────────────────────────────────┐
│                    輸入                                       │
│  User Query + Tool Results（可能含矛盾資料）                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Generator Node（生成節點）                       │
│                                                              │
│  System Prompt：「你是一個專業的法務助理。                    │
│  根據提供的合約條款回答問題。                                  │
│  如果有矛盾的條款，必須明確指出並說明不確定性。」              │
│                                                              │
│  Input：                                                     │
│  ├── User Query                                             │
│  ├── Contract Context（Tool 回傳的原始資料）                 │
│  └── [如果是重試] Evaluator 的錯誤原因（feedback）           │
│                                                              │
│  Output：Draft Answer（初稿）                                │
└──────────────────────────┬───────────────────────────────────┘
                           │ Draft Answer
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Evaluator Node（評估節點）                       │
│                                                              │
│  System Prompt：「你是一個嚴格的法務品質審查員。             │
│  你的任務是找出答案的問題，而不是給出正確答案。              │
│  必須以結構化 JSON 格式輸出評估結果。」                       │
│                                                              │
│  Input：                                                     │
│  ├── User Query                                             │
│  ├── Original Context（原始合約資料）                        │
│  └── Draft Answer（等待審查的答案）                          │
│                                                              │
│  Output：                                                    │
│  {                                                           │
│    "has_error": true/false,                                  │
│    "error_type": "contradiction/hallucination/incomplete",  │
│    "error_detail": "第 3 頁寫 500 萬，第 7 頁寫 50 萬...",  │
│    "severity": "HIGH/MEDIUM/LOW"                            │
│  }                                                           │
└──────────────────────────┬───────────────────────────────────┘
                           │ Evaluator 輸出
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Conditional Router（條件路由）                   │
│                                                              │
│  if has_error == false:                                      │
│      → 直接輸出 Draft Answer 給用戶                          │
│                                                              │
│  elif reflection_count < MAX_REFLECTIONS (= 2):             │
│      → reflection_count += 1                                │
│      → 將 error_detail 作為 feedback 送回 Generator         │
│        （Loop back）                                         │
│                                                              │
│  else: (reflection_count >= MAX_REFLECTIONS)                │
│      → 強制終止反思循環                                      │
│      → 跳到 Fallback Node                                    │
└──────────────────────────────────────────────────────────────┘
                           │
               ┌───────────┴────────────────┐
               ▼                            ▼
┌──────────────────────┐        ┌──────────────────────────────┐
│  Final Answer        │        │  Fallback Node               │
│  輸出給用戶          │        │                              │
│                      │        │  「系統無法得出完全確定的答案 │
└──────────────────────┘        │   此問題已標記供人工審核」   │
                                │                              │
                                │  觸發：                      │
                                │  ├── Cloud Logging Alert     │
                                │  └── 通知 Human Reviewer     │
                                └──────────────────────────────┘
```

---

## 四、防止無限迴圈的三層護欄

```
護欄設計：為什麼三層都需要

護欄 1：反思次數上限（Max Reflections）
  位置：Conditional Router
  邏輯：reflection_count >= 2 → 強制跳出
  為什麼是 2 而不是 5 或 10？
  └── 第一次反思通常解決大部分問題
  └── 第二次反思處理殘留問題
  └── 超過 2 次：可能是問題本身無解（矛盾資料），
                或 Evaluator 和 Generator 陷入分歧
  └── Token 成本：每次反思 ≈ 一次完整對話，3 次 = 3x 成本

護欄 2：State 中的全域計數器
  位置：Global State
  邏輯：reflection_count 存在 State 中，跨節點可見
  為什麼不用局部變數？
  └── LangGraph 的 Node 可能在不同的 Context 執行
  └── State 是唯一可靠的跨節點共享位置

護欄 3：Token Budget Check
  位置：每次進入 Generator 前
  邏輯：如果本次 Session 的累計 token 超過預算
        → 立即跳到 Fallback（不管反思次數）
  為什麼需要？
  └── 防止 Evaluator 錯誤地認為每次都有問題
  └── 防止 token 成本無上限燃燒

三層護欄的配合：
  ├── 第一層（次數）解決大多數情況
  ├── 第二層（State）確保跨節點可見
  └── 第三層（Token）兜底防止成本爆炸
```

---

## 五、LangGraph 的圖結構設計

```
完整的 LangGraph Graph：

Nodes（節點）：
  generator  → 生成初稿
  evaluator  → 評估品質
  router     → 決定下一步
  fallback   → 人工兜底
  output     → 輸出給用戶

Edges（邊）：

  START
    │
    ▼
  generator
    │
    ▼
  evaluator
    │
    ▼
  router ─── has_error=false ──────────────────────────── output → END
    │
    ├── has_error=true AND count < MAX ───── generator（回頭，帶 feedback）
    │
    └── has_error=true AND count >= MAX ─── fallback → END

State Schema（全域狀態）：
  {
    "user_query": str,
    "contract_context": list[str],
    "draft_answers": list[str],       ← 每次生成都 append，不覆蓋
    "evaluator_feedbacks": list[dict],← 每次評估都 append
    "reflection_count": int,          ← 核心護欄計數器
    "final_answer": str | None,
    "outcome": "success" | "fallback" | "running"
  }

關鍵設計：draft_answers 和 evaluator_feedbacks 都用 append
└── 不覆蓋歷史 → 完整的決策軌跡 → 方便事後 Debug
```

---

## 六、評估節點的 Prompt 設計要點

```
Evaluator Prompt 設計的核心原則：

原則 1：具體的錯誤分類（讓 Generator 知道怎麼改）
  ❌ 模糊：「答案有問題」
  ✅ 具體：錯誤類型 + 具體位置 + 為什麼是問題

  Error Types：
  ├── contradiction（矛盾）：文件中有互相衝突的說法
  ├── hallucination（幻覺）：答案提到了文件中沒有的資訊
  ├── incomplete（不完整）：答案遺漏了關鍵資訊
  ├── wrong_number（數字錯誤）：金額、日期、百分比等關鍵數字有誤
  └── out_of_scope（超出範圍）：回答了文件外的問題

原則 2：Evaluator 不應該給出正確答案
  錯誤：「你說 50 萬是錯的，應該是 500 萬」
  正確：「第 3 頁寫 500 萬，第 7 頁寫 50 萬，兩者矛盾，答案未提及此矛盾」
  ↑ Evaluator 的工作是指出問題，Generator 的工作是決定怎麼回應

原則 3：嚴重度分級（決定是否值得反思）
  HIGH Severity → 一定要反思（法律事實錯誤）
  MEDIUM Severity → 建議反思（不夠完整）
  LOW Severity → 可以接受輸出（格式問題）

  Router 邏輯細化：
  └── has_error AND severity == "LOW" AND count == 0 → 可以選擇不反思
```

---

## 七、Trade-off 總覽：Self-Reflection 的代價

```
Self-Reflection 的成本：

每次反思 = 1 次 Generator 呼叫 + 1 次 Evaluator 呼叫
         ≈ 2 次完整 LLM 呼叫的成本

例：
  沒有反思：$0.015/次查詢
  1 次反思：$0.045/次查詢（3x）
  2 次反思：$0.075/次查詢（5x）

問題：什麼場景值得這個成本？

值得的場景：
  ├── 高風險決策（法律、醫療、財務）── 錯誤成本 >> 計算成本
  ├── 資料有已知衝突可能（多來源整合）
  └── 用戶期待高精度（專業 B2B 場景）

不值得的場景：
  ├── 日常 FAQ（回答已有標準答案）
  ├── 格式轉換任務（機械性工作）
  └── 成本敏感的高頻查詢

設計建議：
  反思機制應該是 opt-in 而非 default
  只為高風險工作流程啟用
```

---

## 八、面試答題要點

> *「這道題的核心是：設計一個讓 Agent 能自我校正的迴圈，同時確保這個迴圈一定會終止。*
>
> *架構設計：Generator-Evaluator 雙節點模式。Generator（Gemini Pro，法務助理角色）產生初稿；Evaluator（同一個 Gemini Pro，但不同 System Prompt，法務審查員角色）評估初稿，輸出結構化的錯誤報告（has_error + error_type + 具體位置 + severity）。Conditional Router 根據評估結果決定：通過 → 輸出，有問題且可以重試 → 帶 feedback 回到 Generator，已達上限 → Fallback。*
>
> *收斂保證三層：MAX_REFLECTIONS = 2（次數上限），reflection_count 存在 Global State（跨節點可見），Token Budget Check 防止成本無限燃燒。超過上限就跳 Fallback，回傳「需要人工審核」，觸發 Cloud Logging Alert。*
>
> *成本分析：每次反思大約 2~3x 成本，所以反思機制應該只用在高風險場景（法務、財務、醫療），不應該是所有查詢的 default。」*

---

**系列導覽：**  
← [（二十四）RKK 實戰：混合模型路由與語意路由器設計](../fde-interview-guide-part24-hybrid-model-routing-zh/)  
← [系列首篇：（一）RAG 完全攻略](../fde-interview-guide-part1-rag-zh/)
