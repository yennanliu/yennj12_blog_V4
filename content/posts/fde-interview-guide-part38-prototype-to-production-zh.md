---
title: "FDE 面試準備指南（三十八）：RKK 實戰——從 POC 到 Production：AI 系統的生產化清單與遷移設計"
date: 2026-06-05T16:00:00+08:00
draft: false
description: "以 Google FDE 視角拆解 AI 系統從 POC 到生產環境最容易失敗的五個環節：Token Budget 的失控、延遲 SLA 的差距、狀態持久化的缺失、錯誤處理的不完整、以及 Rollback 機制的缺席；包含 FDE 的生產化清單、模型版本釘選策略、Prompt 版本控制，以及如何跟客戶說明『這個 POC 還沒準備好上線』"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Production", "POC", "Deployment", "Rollback", "SLA", "Token Budget", "RKK", "Interview", "Google"]
authors: ["yen"]
readTime: "19 min"
---

> JD 說的「transitioning from rapid prototypes to production-grade agentic workflows」，  
> 背後是一個很具體的問題：  
> 同樣一個 Agent，在 Demo 時跑得很好，  
> 上了生產後為什麼開始出錯、變慢、或者花了預算的 10 倍？  
> 這篇是 FDE 的生產化診斷清單。

---

## 面試情境

> **面試官：**「你幫客戶做了一個 3 週的 RAG + Agent POC，Demo 很成功。客戶的 CTO 說：太好了，下個月上線。你說：先等一下，我們需要做幾件事。你會說什麼？」

---

## 一、POC 和 Production 的根本差距

```
POC 的環境假設：
  ├── 只有你在用（沒有並發）
  ├── 測試資料乾淨（不代表真實資料的雜亂）
  ├── 成本不是問題（你跑幾百個 query 不心疼）
  ├── 出錯了就 debug（沒有 SLA 壓力）
  └── 每次 demo 都是最好的情況（你挑了最好的例子）

Production 的現實：
  ├── 100 個並發用戶同時問問題
  ├── 用戶問的問題比你預期的更奇怪
  ├── 每個 query 的成本都在累積
  ├── 出錯了客戶打電話來，你要在 1 小時內定位問題
  └── 最壞的情況會發生（Murphy's Law）

POC 成功 ≠ 可以直接上線。
這中間的距離，就是生產化的工程工作。
```

---

## 二、生產化的五個關鍵差距

### 差距 1：Token Budget 的失控

```
POC 時的問題：
  你測試了 50 個問題，每個問題大約 2,000 input tokens。
  你算了一下，成本還好，可以接受。

Production 的現實：
  ├── 某些用戶的問題很長（貼了整份合約）→ 10,000 tokens
  ├── Multi-turn 對話的 history 累積 → 每輪增加 500 tokens
  ├── Agent 的 ReAct loop 多跑了幾輪 → input tokens 加倍
  └── 月底看帳單：成本是預估的 8 倍

生產化設計（Token Budget 管理）：

  1. 設定每個請求的 Token Budget 上限
  
     MAX_INPUT_TOKENS = 8000
     
     def prepare_context(query, history, retrieved_docs):
         total_budget = MAX_INPUT_TOKENS
         
         # 預留 system_prompt 用量（固定）
         total_budget -= len(tokenize(SYSTEM_PROMPT))
         
         # 預留 query 用量
         total_budget -= len(tokenize(query))
         
         # 對話歷史：只保留最近 5 輪，或 Budget 允許的範圍
         history_tokens = 0
         trimmed_history = []
         for turn in reversed(history):
             turn_tokens = len(tokenize(str(turn)))
             if history_tokens + turn_tokens < total_budget * 0.3:
                 trimmed_history.insert(0, turn)
                 history_tokens += turn_tokens
         
         # 剩餘 budget 給 retrieved docs
         remaining = total_budget - history_tokens
         trimmed_docs = truncate_to_token_budget(retrieved_docs, remaining)
         
         return trimmed_history, trimmed_docs

  2. Token 用量的可觀測性
     每個 LLM 呼叫記錄 input_tokens / output_tokens（見 Part 35）
     設定 Alert：7 日平均 cost-per-request 超過基線 20% → 通知

  3. 設定 ReAct loop 的上限
     max_iterations=5（而不是讓 Agent 無限循環）
     超過上限 → 回傳「我需要更多資訊才能完成這個任務」
```

### 差距 2：延遲 SLA 的差距

```
POC 時：
  你跑了 10 個測試，平均 3 秒。「還可以，可以接受。」

Production 的問題：
  ├── P99 延遲（最慢的 1%）可能是 15 秒（高峰 + 外部 API 慢）
  ├── Cold Start：Cloud Run 的第一個請求在 auto-scale 後可能 10+ 秒
  └── 客戶的 SLA 要求是：「95% 的請求在 5 秒內回應」

生產化設計（延遲 SLA）：

  1. 定義 SLA 而不只是「平均值」
     目標：P50 < 2s，P95 < 5s，P99 < 10s
     不是「平均 3 秒」（平均值掩蓋了尾部延遲）

  2. 解決 Cold Start 問題
     Cloud Run 設定 min-instances = 2（確保有 warm 實例）
     代價：持續計費，即使沒有流量
     → 判斷：如果用戶對 Cold Start 敏感，min-instances 是必要的成本

  3. 設定 Tool 呼叫的 Timeout
     每個外部 Tool 呼叫都要有 timeout（而不是無限等待）
     
     async def call_tool_with_timeout(tool_func, *args, timeout=5.0):
         try:
             return await asyncio.wait_for(
                 tool_func(*args),
                 timeout=timeout
             )
         except asyncio.TimeoutError:
             return {"status": "timeout",
                     "message": f"{tool_func.__name__} 呼叫超時"}

  4. 非同步 streaming（改善感知延遲）
     Gemini 支援 Streaming 回應（逐字輸出）
     → 用戶看到第一個字的時間（TTFT）比等完整回答快得多
     → 感知延遲比實際延遲重要
     → 對長回答尤其明顯（法律分析、報告生成）
```

### 差距 3：狀態持久化的缺失

```
POC 時：
  你把 Conversation History 存在 Python dict（記憶體）。
  重啟就清空，但測試時沒差。

Production 的問題：
  ├── Cloud Run 的實例可能被 Scale Down → 記憶體清空 → 對話斷掉
  ├── 多個 Cloud Run 實例 → 用戶的下一個請求打到不同實例 → 找不到對話
  └── 部署新版本 → Rolling Update → 一半實例有舊狀態，一半沒有

生產化設計（Session State 持久化）：

  選項 A：Firestore（ADK 原生支援）
    ADK Session State 直接持久化到 Firestore。
    特點：
    ├── 跨實例共享（Cloud Run Scale Out 後也能讀到）
    ├── 自動 TTL（設定 session 過期時間）
    └── 整合 ADK 不需要額外代碼
    代價：每個 read/write 有 Firestore 的網路延遲（約 10-50ms）

  選項 B：Cloud Memorystore（Redis）
    更高效能的 session cache（< 5ms 延遲）
    適合：高頻讀寫的 session state
    代價：不是全託管（需要設定和維護 Redis instance）

  設計原則：
    ├── Session State 要有 TTL（不能永久存著所有對話）
    ├── PII 不存在 Session State（用 anonymized token 代替）
    └── Session 大小要設上限（防止某個 session 占用大量儲存）
```

### 差距 4：錯誤處理的不完整

```
POC 時：
  出錯了就看 error log，重跑。

Production 的問題：
  用戶不是工程師，他們不會「重跑」，他們只會感覺系統壞了。

生產化設計（錯誤分類和處理）：

  錯誤分類          處理方式                  用戶看到的
  ───────────────────────────────────────────────────────────────
  外部 API timeout  重試 3 次後 graceful return  「系統暫時無法連線，請稍後再試。」
  Token 超限        截斷 context，繼續執行       正常回答，但可能不完整
  LLM 拒絕回答      捕獲 SAFETY finish_reason   「這個問題超出了我的服務範圍。」
  工具執行失敗       回傳結構化錯誤               「我無法完成這個操作，原因是...」
  系統錯誤（500）    全局 Exception Handler       「系統遇到問題，已通知工程師。」
                                                 + 記錄到 Cloud Logging

  不允許的行為：
  ❌ 把 Python Exception stack trace 直接回給用戶
  ❌ 讓 Agent 在 Tool 失敗後繼續假裝成功
  ❌ 靜默吞掉錯誤（讓用戶以為成功了但其實沒有）

  全局錯誤處理（FastAPI 包裝 ADK）：

  @app.exception_handler(Exception)
  async def global_exception_handler(request, exc):
      # 記錄到 Cloud Logging，帶 trace_id 方便 debug
      logger.error("Unhandled exception", extra={
          "trace_id": get_trace_id(),
          "error_type": type(exc).__name__,
          "user_id": request.state.user_id,
      })
      # 回給用戶的是安全的錯誤訊息，不是 stack trace
      return JSONResponse(
          status_code=500,
          content={"message": "系統遇到問題，工程師已收到通知。"}
      )
```

### 差距 5：Rollback 機制的缺席

```
POC 時：
  出問題就改代碼重部署。反正是測試環境。

Production 的問題：
  ├── 新版 Prompt 讓系統開始給出奇怪的答案 → 需要立刻 Rollback
  ├── 新模型版本（gemini-2.0-flash → 新版）改變了輸出格式 → 系統壞了
  └── 沒有 Rollback 機制 → 修好之前系統一直壞著

生產化設計（Rollback 三層）：

  Layer 1：Prompt 版本控制
    
    所有 Prompt 用版本管理，不是直接改代碼裡的字串：
    
    PROMPT_REGISTRY = {
        "claims_assistant_v1": "你是保險理賠助理...",
        "claims_assistant_v2": "你是專業的理賠審核員...",  # 當前版本
        "claims_assistant_v3": "你是嚴謹的風險評估專家...",  # 測試中
    }
    
    ACTIVE_PROMPT = os.getenv("ACTIVE_PROMPT", "claims_assistant_v2")
    
    Rollback Prompt：只需要改環境變數，不需要重新部署代碼。

  Layer 2：模型版本釘選

    不要用 "gemini-latest" 或 "gemini-2.0-flash"（會跟著 Google 更新）。
    要用具體版本：

    MODEL_VERSION = "gemini-2.0-flash-001"  # 釘選版本
    # 升級前要先在 Staging 環境跑 Eval Pipeline 通過，再改這個值

    為什麼重要：
    LLM 的新版本可能改變輸出格式或行為，
    即使是同名模型，小版本升級也可能讓你的 Prompt 解析失效。

  Layer 3：Traffic Splitting（Canary 部署）

    不要「全量切換」到新版本——用 Canary Release：

    Cloud Run Traffic Splitting：
    90% → 穩定版（v2）
    10% → 新版（v3，Canary）

    監控 Canary 的指標 24 小時：
    ├── Error Rate 有沒有升高？
    ├── P95 延遲有沒有升高？
    └── Shadow Eval 的 Faithfulness 有沒有退化？

    都正常 → 逐步把 Canary 流量提升到 100%
    有問題 → 把 Canary 流量改回 0%（一鍵 Rollback）

    實務上：
    gcloud run services update-traffic claims-agent \
      --to-revisions=LATEST=10,STABLE=90
    # Rollback：
    gcloud run services update-traffic claims-agent \
      --to-revisions=STABLE=100
```

---

## 三、FDE 的生產化 Go-Live 清單

```
告訴客戶「還沒準備好上線」的依據：

技術維度：
  □ Token Budget 有上限設定，不能被單一用戶「炸掉」
  □ 每個 Tool 呼叫有 timeout，不會無限等待
  □ Session State 有持久化（不存記憶體）
  □ 全局錯誤處理，用戶看不到 stack trace
  □ Cloud Run 的 min-instances > 0（避免冷啟動影響 SLA）
  □ Prompt 有版本控制，可以一鍵 Rollback
  □ 模型版本已釘選，不跟著 Google 自動更新
  □ Eval Pipeline 已建立，有 Baseline 指標

可觀測性維度：
  □ Cloud Trace 已整合，每個請求有 Trace ID
  □ Structured Logging，Log 和 Trace 用 Trace ID 串聯
  □ Cloud Monitoring 的 Alert 已設定（Error Rate / 延遲 / 成本）
  □ 有 Dashboard 可以讓客戶自己看系統健康狀況

安全維度：
  □ API Key 和 DB 憑證在 Secret Manager，不在代碼裡
  □ Cloud Run 使用 dedicated Service Account（最小權限）
  □ PII 不出現在 Log 和 Trace 裡
  □ 如果有合規要求：VPC-SC / CMEK 已設定

流量和成本維度：
  □ 有並發限制（Rate Limiting），防止單一用戶打垮系統
  □ Cost Alert：月費超過 X 金額 → 通知（防止意外的帳單爆炸）
  □ 有 load test 結果，知道系統能撐多少並發

如果上面清單有超過 3 個 □ 未勾選，這個系統還沒準備好上線。
```

---

## 四、面試官地雷題

**地雷 1：「客戶說：POC 跑得很好，下個月上線，有什麼問題嗎？
你怎麼回應，同時不讓客戶覺得你在拖延？」**

```
答：這是個溝通問題，不只是技術問題。

    不說：「還有很多問題沒解決，上線太早了。」（讓客戶失去信心）
    
    說：「POC 驗證了核心 AI 能力完全可行——這是最重要的里程碑。
         下個月上線是可以的，但我建議我們做一個 soft launch，
         先讓 100 個內部用戶使用兩週，
         而不是第一天就開放給全部 5,000 個用戶。
         
         這兩週我們並行處理三件事：
         第一，建立 Token Budget 管理和 Error Handling（3 天）
         第二，設定 Monitoring 和 Alert（2 天）
         第三，建立 Prompt 版本控制和 Rollback 機制（1 天）
         
         Soft launch 讓我們在真實流量下發現問題，
         同時把影響範圍控制在可控的範圍內。
         比起『下個月開放給所有人然後出問題』，
         這個方式讓你有更好的上線故事。」
```

**地雷 2：「你說釘選模型版本（gemini-2.0-flash-001），
但 Google 可能在那個版本退役後強制升級。你怎麼管理？」**

```
答：這是真實會發生的事，需要主動管理：

    1. 追蹤模型版本的 deprecation 通知
       → 訂閱 Vertex AI 的 release notes 和 deprecation email
       → 在程式碼裡加 TODO：「此版本將於 YYYY-MM 退役，需要在 30 天前升級」

    2. 升級流程（不是等到退役才處理）
       新版本發布 → Staging 環境切換 + 跑 Eval Pipeline
       → 指標沒有退化 → 更新 MODEL_VERSION 環境變數
       → 用 Canary 部署逐步升到 Production
       
    3. 這個流程要在 Runbook 裡記錄下來，
       讓客戶的工程師知道「每次模型升級要做什麼」——
       FDE 不能永遠陪在那裡，要把流程留下來。
```

**地雷 3：「Canary 部署的時候，Eval 顯示新版本比舊版好，
但少數用戶投訴新版本的回答風格變了。你怎麼做決定？」**

```
答：這暴露了 Eval Pipeline 的一個盲點——
    Eval 衡量的是「準確率和相關性」，
    但沒有衡量「回答風格的一致性」。

    短期決策（24 小時內）：
    如果投訴數量超過 5% → 暫時把 Canary 流量降回 0%
    不是「Rollback」（Rollback 是緊急措施），
    是「暫停 Canary 升級，做進一步分析」

    中期分析：
    找出新舊版本回答風格差異的根因——
    是模型版本變了，還是 Prompt 措辭引起了不同的風格？
    如果是 Prompt 問題，調整 Prompt 的風格指引，再重新測試。
    如果是模型本身的風格差異，評估是否值得讓用戶適應。

    加入 Eval 指標：
    下次版本升級，加入「回答風格一致性」的評估——
    用 embedding similarity 比較新舊版本的回答風格分佈，
    確保風格沒有大幅漂移。

    告訴客戶：
    「這次 Canary 發現了一個我們 Eval Pipeline 沒有覆蓋到的維度：
     回答風格。我會把這個加入我們的品質閘門，
     確保下次升級前這個維度也經過驗證。」
```

---

## 五、面試回答完整示範

```
面試官問：「POC 成功了，CTO 說下個月上線。你說先等一下，你會說什麼？」

先肯定再定義差距（30 秒）：
「POC 驗證了最重要的事——AI 能夠準確分析合約條款，
 這是整個系統的核心。現在要做的是讓它可以讓 1,000 個用戶同時用，
 而不只是在 Demo 環境跑一個人。」

最關鍵的五件事（2 分鐘）：
「我的清單有五個優先項目：

 第一，Token Budget 管理：
 現在有些用戶貼了整份合約進來，input tokens 爆到 20,000，
 成本是正常的 10 倍。我需要加入 context 截斷邏輯。

 第二，延遲 SLA：
 Cold Start 在 Cloud Run Scale Out 後是 8 秒，
 超過客戶的 5 秒 SLA。需要設定 min-instances=2。

 第三，Error Handling：
 SAP API 有 10% 的時間會 timeout，
 現在 timeout 會讓整個 Agent crash。
 需要加 graceful fallback。

 第四，Rollback 機制：
 Prompt 和模型版本要有版本控制，
 出問題可以一分鐘內 Rollback，不需要重新部署。

 第五，Observability：
 需要 Cloud Trace 和 Alert，
 這樣客戶打電話來說系統慢的時候，我能在 5 分鐘內定位問題。

建議的路徑（30 秒）：
『這五件事，一個工程師可以在 2 週內完成。
  然後我建議先做 2 週的 Internal Pilot——
  讓你的 IT 部門 50 個人先用，
  我們在真實流量下確認沒有問題後，
  再開放給全部用戶。
  這樣下個月底你有信心告訴所有人：系統準備好了。』」
```

---

**「能 Demo」和「可以放到生產」之間的距離，**  
**是 FDE 和一般 AI 工程師最核心的差距之一。**  
**知道這個距離是什麼，並且有辦法系統性地填補它，**  
**才是 FDE 對客戶真正的價值。**
