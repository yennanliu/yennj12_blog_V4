---
title: "AI FDE 技能地圖：25 個核心主題怎麼連在一起"
date: 2026-10-15T09:00:00+08:00
draft: false
description: "把 25 篇 FDE core topic 排成四個技能堆疊——建模與檢索、代理與執行、平台與安全、客戶與交付——並給出三條各五篇的閱讀路線，讓你知道先讀哪一篇、為什麼。"
categories: ["all", "ai", "engineering"]
tags: ["AI", "FDE", "fde-core-topic", "cheatsheet", "RKK"]
authors: ["yen"]
readTime: "9 min"
aliases:
  - /posts/ai-fde-essential-guide-part1-zh/
  - /posts/ai-fde-essential-guide-part2-zh/
  - /posts/ai-fde-essential-guide-part3-zh/
  - /posts/ai-fde-essential-guide-part4-zh/
  - /posts/ai-fde-essential-guide-part5-zh/
---

> 多數人學 AI 工程的方式，是把套件清單從上往下背：框架、向量資料庫、雲端服務、監控工具。
> 背完以後，面對客戶一句「我們的資料不能離開新加坡，而且法務要在兩週內看到 demo」，還是不知道該從哪裡動手。
> Forward Deployed Engineer（FDE）的工作不是「會用很多工具」，
> 而是把客戶的限制條件變成一個能跑的系統——技能只有放在那條路徑上，才知道哪些重要、哪些可以先跳過。

這篇是本站 25 篇《FDE core topic》的地圖。它不重複任何一篇的內容，只做一件事：說明這 25 個主題為什麼分成四個堆疊、每個堆疊在客戶專案裡負責什麼、它們之間的資料怎麼流，以及你該從哪一篇開始讀。每個主題都附上原文連結；數字、機制與取捨都留在原文裡。

---

## 一、FDE 到底在做什麼

FDE（Forward Deployed Engineer）是被派到客戶現場、把一個 AI 產品落地成客戶系統的工程師。這個角色和純後端工程師的差別，不在技術深度，而在**輸入**：後端工程師拿到的是規格，FDE 拿到的是限制條件——資料在哪裡、誰能看、延遲要多少、預算是誰批、誰會在最後一刻說不。

「能跑的系統」在這裡有三個具體的意思，缺一個就不算交付：

- **上線**：在客戶的環境、客戶的資料、客戶的流量下跑，而不是在 notebook 裡跑。
- **可觀測**：出問題時有人能說出是哪一層壞了，而不是重啟碰運氣。
- **有人買單**：客戶的決策者看得到它解決了什麼問題，願意繼續投資。

這三個條件分別對應技術堆疊、觀測點與交付迴圈，所以 FDE 的技能自然依照「限制條件如何變成系統」這條路徑分組：

```
客戶限制條件                                        能跑的系統
（資料位置、合規、延遲、預算、決策者）              （上線、可觀測、有人買單）
      │                                                 ▲
      │   客戶與交付：問出限制、排出優先序、證明價值    │
      ▼                                                 │
┌──────────────────────────────────────────────────────────┐
│ 建模與檢索   →   代理與執行   →   平台與安全             │
│ 模型看到什麼     系統怎麼一步步做   在哪裡跑、多快、誰能碰│
└──────────────────────────────────────────────────────────┘
```

前三個堆疊是技術路徑，一個請求會依序穿過它們；第四個堆疊包在外面，決定這條路徑該不該建、建多大、怎麼讓客戶看見它值得。下面逐一說明。

---

## 二、建模與檢索：決定模型看到什麼

這個堆疊回答的問題是：**在模型開始生成之前，它的上下文裡該放什麼、不該放什麼、放進去的東西對不對。**

FDE 在這一層花最多時間的不是選模型，而是管理那個有限的上下文視窗。客戶的文件庫通常遠大於任何模型的 context window，所以每個請求都得決定：哪些歷史對話要留、哪些工具輸出要修剪、要從知識庫撈哪幾段回來、撈回來的順序要不要重排。這些決定直接決定答案品質，而且會隨著客戶資料增長而退化——昨天 recall 還好的向量索引，今天可能因為持續寫入而變差。

評估也屬於這一層。RAG 系統沒有「正確答案」可以比對，所以 FDE 要先建立三個互相獨立的量尺（撈到的上下文相不相關、答案有沒有忠於上下文、答案有沒有回到問題），再決定人工標註跟 LLM 裁判各占多少。沒有這一層，後面所有調整都是憑感覺。

| 技能 | 解決的問題 | 原文 |
|---|---|---|
| Context Management | Token 預算怎麼分、對話與工具輸出怎麼修剪 | [fde-core-concept-1](/posts/fde-core-concept-1-context-management-zh/) |
| Memory Architecture | Agent 的短期、長期、程序性記憶各放哪裡、怎麼遺忘 | [fde-core-concept-2](/posts/fde-core-concept-2-memory-architecture-zh/) |
| Hybrid Search & RRF | 關鍵字檢索與向量檢索怎麼融合排名 | [fde-core-concept-4](/posts/fde-core-concept-4-hybrid-search-rrf-zh/) |
| Re-ranking & Cross-Encoder | 粗召回之後怎麼用較貴的模型精排前幾名 | [fde-core-concept-5](/posts/fde-core-concept-5-reranking-cross-encoder-zh/) |
| Vector Drift & Blue-Green Indexing | 向量索引持續更新後 recall 衰退，怎麼零停機重建 | [fde-core-concept-15](/posts/fde-core-concept-15-vector-drift-blue-green-zh/) |
| LLM-as-Judge & Bias Mitigation | 用模型當裁判大規模評估，並消除裁判本身的偏見 | [fde-core-concept-19](/posts/fde-core-concept-19-llm-judge-bias-mitigation-zh/) |
| RAG Triad Metrics | 上下文相關度、忠實度、答案相關度三個指標怎麼量、怎麼追蹤 | [fde-core-concept-20](/posts/fde-core-concept-20-rag-triad-metrics-zh/) |

讀這一層的順序建議是 1 → 4 → 5 → 20：先懂預算，再懂撈什麼，再懂怎麼排，最後懂怎麼量。2、15、19 是這條主線上的分支，等主線穩了再回頭。

---

## 三、代理與執行：決定系統怎麼一步步做

這個堆疊回答的問題是：**當一個任務需要多個步驟、多個工具、多次模型呼叫，系統怎麼保證它會結束、會收斂、失敗後能接續、不會把後端壓垮。**

客戶 demo 裡的 Agent 通常是一個自由迴圈：模型想、呼叫工具、再想、再呼叫，直到它自己覺得完成。上線後這個設計的問題會一次全部出現——迴圈不收斂、一個請求卡住幾十秒把 Web Server 連線池吃光、Pod 被搶佔後整個任務從頭重跑並重複送出副作用、一個租戶的突發流量讓其他租戶全部變慢。FDE 在這一層做的事，是把「模型自由決定下一步」收斂成「圖上有限的幾條邊」，並把每一步變成可以中斷、可以重放、可以限速的工作單元。

下面是一個請求穿過前三個堆疊的典型路徑。注意兩個結構性決定：同步 HTTP 在進入 Agent 之前就被切成非同步事件，而每個工具呼叫在扇出之前先經過反壓與配額。右側標的是該元件屬於哪個堆疊——同一個請求會在三個堆疊之間來回，這是為什麼它們不能分開學。

```
使用者 ──HTTP──▶ [輸入護欄：注入 / PII 檢查]        ← 平台與安全
                        │
                        ▼
                 [事件佇列：同步 → 非同步]          ← 代理與執行
                        │
                        ▼
                 [狀態機 / DAG：每步冪等、可續傳]   ← 代理與執行
                   ▲    │
     檢索 + 重排   │    │ 工具扇出
   [hybrid, RRF] ──┘    ▼
     ← 建模與檢索  [反壓 + 公平排程：Token Bucket]  ← 代理與執行
                        │
                        ▼
                 [模型路由 → 推理服務]              ← 平台與安全
                  KV 快取、連續批次、區域端點、CMEK
```

| 技能 | 解決的問題 | 原文 |
|---|---|---|
| State Machine & DAG | 把自由迴圈收斂成有限的圖，讓 Agent 行為可稽核、可測試 | [fde-core-concept-3](/posts/fde-core-concept-3-state-machine-dag-zh/) |
| Async Event-Driven Pipeline | 把長時間的模型推論從同步 HTTP 解耦，保護連線池 | [fde-core-concept-11](/posts/fde-core-concept-11-async-event-driven-pipeline-zh/) |
| Backpressure & Fair-Share | 多租戶突發流量下，怎麼限速又保障每個租戶的最低吞吐 | [fde-core-concept-12](/posts/fde-core-concept-12-backpressure-fair-share-zh/) |
| Idempotency & State Recovery | Pod 掛掉後怎麼從斷點續傳，而且不重複副作用 | [fde-core-concept-13](/posts/fde-core-concept-13-idempotency-state-recovery-zh/) |
| Speculative Tool Execution | 並行多個工具呼叫時，怎麼壓制尾部延遲、回傳部分結果 | [fde-core-concept-14](/posts/fde-core-concept-14-speculative-tool-fanout-zh/) |

這五篇有明確的先後：3 是骨架，11 讓骨架能承受真實流量，13 讓骨架能從失敗中恢復，12 和 14 分別處理「太多請求進來」和「一個請求扇出太多」兩種壓力。

---

## 四、平台與安全：決定在哪裡跑、多快、誰能碰

這個堆疊回答兩個問題：**推理服務的延遲與成本從哪裡來、怎麼壓**；以及**客戶的資料與模型的輸入輸出，在每一個邊界上由誰控制**。

效能這一半，FDE 關心的是兩個指標的拉鋸：首字延遲（TTFT）決定使用者覺得「快不快」，吞吐量決定每個 token 要花多少錢。量化、連續批次、KV 快取、投機解碼這些技術都在這兩者之間移動；而上下文快取則是一把雙面刃——命中時省錢，沒管好驅逐就變成按時間計費的隱性成本。模型路由把這件事再往上推一層：不是所有請求都值得送給最貴的模型，問題是怎麼在送出之前就判斷出來。

安全這一半，是客戶法務與資安最先問、也最常擋住專案的部分。它不是一道牆而是一串邊界：使用者輸入進來時（提示注入）、Agent 讀取外部文件時（間接注入）、資料進入管線之前（PII 去識別化）、資料與模型跑在哪個區域（資料主權）、靜態資料由誰持有金鑰（CMEK / BYOK）。FDE 要能在白板上畫出每一道邊界，並說出為什麼這個客戶需要其中哪幾道。

| 技能 | 解決的問題 | 原文 |
|---|---|---|
| TTFT & Throughput Optimization | 首字延遲與吞吐量的硬體級優化技術及其取捨 | [fde-core-concept-16](/posts/fde-core-concept-16-ttft-throughput-optimization-zh/) |
| Context Cache Eviction | 上下文快取的驅逐策略與計費陷阱 | [fde-core-concept-17](/posts/fde-core-concept-17-context-caching-eviction-zh/) |
| Semantic Model Routing | 依請求的不確定性把流量導向最便宜的可行模型 | [fde-core-concept-18](/posts/fde-core-concept-18-semantic-model-routing-zh/) |
| Prompt Injection & Jailbreak Defense | 使用者直接輸入的攻擊，怎麼建縱深防禦 | [fde-core-concept-6](/posts/fde-core-concept-6-prompt-injection-jailbreak-zh/) |
| Indirect Prompt Injection | Agent 讀到的外部內容藏有指令，怎麼用特權隔離與沙盒擋住 | [fde-core-concept-7](/posts/fde-core-concept-7-indirect-prompt-injection-zh/) |
| PII 去識別化與格式保留加密 | 資料進入 AI 管線前的隱私護欄 | [fde-core-concept-8](/posts/fde-core-concept-8-pii-deidentification-zh/) |
| Data Residence & Sovereign AI | 金融、醫療場景的區域與地緣合規架構 | [fde-core-concept-9](/posts/fde-core-concept-9-data-residence-sovereign-ai-zh/) |
| CMEK / BYOK 信封加密 | 客戶自主持有金鑰的加密架構 | [fde-core-concept-10](/posts/fde-core-concept-10-cmek-byok-envelope-zh/) |

效能三篇（16 → 17 → 18）與安全五篇（6 → 7 → 8 → 9 → 10）各自成線，彼此獨立；先讀哪一線取決於你的客戶先問延遲還是先問合規。

---

## 五、客戶與交付：決定該不該建、建多大、怎麼證明

這個堆疊回答的問題是：**前三個堆疊的技術決定，該由什麼輸入來驅動；做出來之後，怎麼讓客戶的決策者看見它值得。**

這是 FDE 與純工程角色分道的地方。客戶的第一句話幾乎永遠是模糊的（「我們想要 AI」），FDE 的第一個動作不是畫架構，而是用結構化的問法把它收斂成一張約束清單——規模、合規、現有系統、延遲、預算。這張清單直接決定前三個堆疊裡哪些主題要用、哪些是過度設計。接著是找出誰真的能拍板、誰會在最後一刻擋住；把 PoC 的成功標準在動手前就寫成可以打分的矩陣；最後把技術指標翻譯成決策者聽得懂的價值敘事，並準備好回應常見的異議。

這四件事不是線性的，而是一個迴圈：PoC 結果會改寫約束，約束改寫會換掉利害關係人，新的利害關係人會提出新的異議。系統出問題時，結構化排錯則是這個迴圈裡的回饋通道——從使用者症狀出發，逐層排除，而不是從最熟的元件開始猜。

```
      ┌───────────────────────────────────────────────────────────────┐
      │                                                               │
      ▼                                                               │
 [Discovery] ──▶ [利害關係人圖] ──▶ [PoC 評分矩陣] ──▶ [Value Story]  ┘
 問出約束清單      誰拍板、誰擋        Go / No-Go          回應異議、擴大
      │                                    │
      │ 約束清單驅動                        │ PoC 失敗 / 上線後故障
      ▼                                    ▼
 [技術堆疊：建模與檢索 → 代理與執行 → 平台與安全] ◀── [Structured
                                                   Troubleshooting]
                                                   逐層排除，不從最熟的元件猜
```

| 技能 | 解決的問題 | 原文 |
|---|---|---|
| Discovery to Technical Constraints | 把模糊需求問成可驅動架構的約束清單 | [fde-core-concept-21](/posts/fde-core-concept-21-discovery-to-constraints-zh/) |
| Structured Troubleshooting | 從使用者症狀出發、自上而下逐層排錯 | [fde-core-concept-22](/posts/fde-core-concept-22-structured-troubleshooting-zh/) |
| Stakeholder Mapping | 找出決策者與隱形阻擋者，對每一種人講不同的話 | [fde-core-concept-23](/posts/fde-core-concept-23-stakeholder-mapping-zh/) |
| POC Scoring & ROI | 動手前先定成功指標與 Go/No-Go 閘門 | [fde-core-concept-24](/posts/fde-core-concept-24-poc-scoring-roi-zh/) |
| Value Story & Objection Handling | 把技術指標翻成業務成果，並破解常見異議 | [fde-core-concept-25](/posts/fde-core-concept-25-value-story-objection-zh/) |

順序就是迴圈的順序：21 → 23 → 24 → 25，22 隨時可以插進來。

---

## 六、四個堆疊怎麼互相牽動

把四個堆疊分開講是為了方便讀，但客戶專案裡它們從不單獨出現。幾個常見的牽動：

- **約束清單決定技術堆疊的規模。** Discovery（21）問出「單一租戶、流量平穩」，那麼反壓與公平排程（12）就是過度設計；問出「資料不能離開特定區域」，那麼模型路由（18）的可選模型集合就被資料主權（9）直接砍掉一截。
- **評估指標決定 PoC 能不能打分。** PoC 評分矩陣（24）需要可量化的成功標準，而 RAG 系統的成功標準正是 RAG Triad（20）與 LLM 裁判（19）提供的；沒有先建評估，PoC 就只能靠 demo 現場的感覺。
- **安全邊界決定 Agent 能做什麼。** 間接注入（7）的防禦方式是限制讀過外部內容的模型能呼叫哪些工具，這直接改寫狀態機（3）的圖——某些邊在特權隔離下根本不存在。
- **排錯需要每一層都有觀測點。** 結構化排錯（22）之所以能逐層排除，前提是 RAG Triad（20）的追蹤、非同步管線（11）的佇列深度、推理服務（16、17）的 TTFT 與快取命中率都有被記錄。觀測不是事後加的，而是每個堆疊建的時候就留下的。
- **價值敘事要用技術堆疊的數字。** Value Story（25）說服決策者靠的是客戶自己的資料跑出來的數字——重排序前後的檢索品質、路由前後的成本、非同步化前後的並發量——這些都是前三個堆疊裡本來就該量的東西。

一句話：**客戶與交付決定要量什麼，前三個堆疊負責量得出來。** 這也是為什麼四個堆疊必須一起學，而不是先技術再補「軟技能」。

學這張地圖時有三個常見的誤讀，先說在前面：

1. **把堆疊當成順序。** 四個堆疊是分類，不是時程。真實專案裡第一週就會同時碰到 Discovery、資料主權和檢索品質。
2. **把安全當成最後一層。** 安全那五篇描述的是邊界，而邊界決定架構——先把 Agent 做出來再補 PII 去識別化，通常意味著重做資料管線。
3. **把客戶與交付當成非技術。** 那五篇的輸出（約束清單、成功指標、價值數字）全部是前三個堆疊的輸入或輸出，它們是同一個系統的兩端。

---

## 七、客戶的一句話，對應哪一篇

這張表是給你在客戶會議裡用的。左欄是客戶常說的原話，中欄是它真正在問的技術問題，右欄是先讀哪一篇。

| 客戶說 | 其實在問 | 先讀 |
|---|---|---|
| 「資料不能離開我們所在的區域」 | 模型與資料的區域端點、主權控制 | [9](/posts/fde-core-concept-9-data-residence-sovereign-ai-zh/)，再看 [10](/posts/fde-core-concept-10-cmek-byok-envelope-zh/) |
| 「法務要求金鑰在我們自己手上」 | 客戶自主金鑰與信封加密 | [10](/posts/fde-core-concept-10-cmek-byok-envelope-zh/) |
| 「答案常常引用錯文件」 | 檢索品質：撈什麼、怎麼排、怎麼量 | [4](/posts/fde-core-concept-4-hybrid-search-rrf-zh/)、[5](/posts/fde-core-concept-5-reranking-cross-encoder-zh/)、[20](/posts/fde-core-concept-20-rag-triad-metrics-zh/) |
| 「什麼都沒改，但越來越常答錯」 | 向量索引在持續寫入下的退化 | [15](/posts/fde-core-concept-15-vector-drift-blue-green-zh/) |
| 「尖峰時間整個網頁卡住」 | 同步推論耗盡連線池、缺乏反壓 | [11](/posts/fde-core-concept-11-async-event-driven-pipeline-zh/)、[12](/posts/fde-core-concept-12-backpressure-fair-share-zh/) |
| 「Agent 跑到一半掛了，會重複寄信」 | 冪等與斷點續傳 | [13](/posts/fde-core-concept-13-idempotency-state-recovery-zh/) |
| 「第一個字出來太慢」 | 首字延遲與快取 | [16](/posts/fde-core-concept-16-ttft-throughput-optimization-zh/)、[17](/posts/fde-core-concept-17-context-caching-eviction-zh/) |
| 「每個月的模型帳單太高」 | 請求層級的模型路由 | [18](/posts/fde-core-concept-18-semantic-model-routing-zh/) |
| 「有人在聊天框貼了奇怪的指令」 | 直接與間接提示注入 | [6](/posts/fde-core-concept-6-prompt-injection-jailbreak-zh/)、[7](/posts/fde-core-concept-7-indirect-prompt-injection-zh/) |
| 「上傳的文件裡有客戶個資」 | 進入管線前的去識別化 | [8](/posts/fde-core-concept-8-pii-deidentification-zh/) |
| 「老闆要看到 ROI 才放行」 | PoC 成功標準與價值敘事 | [24](/posts/fde-core-concept-24-poc-scoring-roi-zh/)、[25](/posts/fde-core-concept-25-value-story-objection-zh/) |
| 「哪個部門要用、誰簽字還不清楚」 | 約束清單與利害關係人圖 | [21](/posts/fde-core-concept-21-discovery-to-constraints-zh/)、[23](/posts/fde-core-concept-23-stakeholder-mapping-zh/) |
| 「出問題時每個團隊都說不是自己」 | 逐層排錯與觀測點 | [22](/posts/fde-core-concept-22-structured-troubleshooting-zh/) |
| 「Agent 要記得上次的對話」 | 記憶層級與上下文預算 | [2](/posts/fde-core-concept-2-memory-architecture-zh/)、[1](/posts/fde-core-concept-1-context-management-zh/) |

---

## 八、從哪裡開始

每篇原文的閱讀時間約 13–18 分鐘（依各篇 readTime），25 篇全部讀完需要不少時間。如果你只有一個下午，依你的背景挑一條路線，每條五篇、各自成一個閉環。

### 路線 A：剛接觸 AI 工程

目標是建立「一個 RAG 請求從頭到尾會經過什麼」的完整畫面，不碰分散式與合規。

1. [Context Management](/posts/fde-core-concept-1-context-management-zh/) — 先懂上下文是有限的、要分配的
2. [Hybrid Search & RRF](/posts/fde-core-concept-4-hybrid-search-rrf-zh/) — 知識怎麼撈回來
3. [Re-ranking & Cross-Encoder](/posts/fde-core-concept-5-reranking-cross-encoder-zh/) — 撈回來的怎麼排
4. [RAG Triad Metrics](/posts/fde-core-concept-20-rag-triad-metrics-zh/) — 怎麼知道答案好不好
5. [Prompt Injection & Jailbreak Defense](/posts/fde-core-concept-6-prompt-injection-jailbreak-zh/) — 第一道安全邊界長什麼樣

### 路線 B：後端工程師轉 AI

你已經懂佇列、冪等、限速與連線池；這條路線告訴你這些概念在 LLM 系統裡的新形狀，以及推理服務和一般 API 服務的根本差異。

1. [State Machine & DAG](/posts/fde-core-concept-3-state-machine-dag-zh/) — 為什麼 Agent 不能是自由迴圈
2. [Async Event-Driven Pipeline](/posts/fde-core-concept-11-async-event-driven-pipeline-zh/) — 秒級推論延遲對連線池的衝擊
3. [Idempotency & State Recovery](/posts/fde-core-concept-13-idempotency-state-recovery-zh/) — 多步驟 Agent 的斷點續傳
4. [TTFT & Throughput Optimization](/posts/fde-core-concept-16-ttft-throughput-optimization-zh/) — 推理服務的效能模型與一般服務不同在哪
5. [Semantic Model Routing](/posts/fde-core-concept-18-semantic-model-routing-zh/) — 成本是請求層級的決定，不是月底的帳單

### 路線 C：顧問 / 解決方案架構師轉 FDE

你已經會問問題、會畫利害關係人圖；這條路線補上你在白板前必須能講清楚的那幾個技術邊界，再回到你熟悉的交付迴圈。

1. [Discovery to Technical Constraints](/posts/fde-core-concept-21-discovery-to-constraints-zh/) — 約束清單怎麼問出來
2. [Data Residence & Sovereign AI](/posts/fde-core-concept-9-data-residence-sovereign-ai-zh/) — 法務最先問的那道邊界
3. [PII 去識別化](/posts/fde-core-concept-8-pii-deidentification-zh/) — 資安第二個會問的
4. [POC Scoring & ROI](/posts/fde-core-concept-24-poc-scoring-roi-zh/) — 動手前把成功標準寫成矩陣
5. [Value Story & Objection Handling](/posts/fde-core-concept-25-value-story-objection-zh/) — 把結果講給決策者聽

三條路線讀完，各自會留下一個明顯的缺口——A 缺分散式執行，B 缺客戶與交付，C 缺檢索與評估——那個缺口就是你的第二條路線。

---

## 九、從舊的五篇「必備技能指南」過來的讀者

本站原本有一個五篇的《AI Forward Deployed Engineer 必備技能指南》系列，現在由這張地圖取代，舊網址會自動導到這裡。舊系列是套件與程式碼清單，沒有解釋每個選擇背後的「為什麼」；上面 25 篇每一篇都有機制、數字與取捨，所以地圖只負責指路。舊的五個部分對應如下：

| 舊系列 | 原本涵蓋 | 現在去哪裡讀 |
|---|---|---|
| （一）基礎核心概念與技術棧 | Python 生態、深度學習框架、提示工程、模型最佳化 | 套件清單不再維護；推理最佳化見 [16](/posts/fde-core-concept-16-ttft-throughput-optimization-zh/)，上下文與提示結構見 [1](/posts/fde-core-concept-1-context-management-zh/)、[6](/posts/fde-core-concept-6-prompt-injection-jailbreak-zh/) |
| （二）多智慧體系統與框架實戰 | LangGraph、CrewAI、MCP、代理安全 | [3](/posts/fde-core-concept-3-state-machine-dag-zh/)、[13](/posts/fde-core-concept-13-idempotency-state-recovery-zh/)、[14](/posts/fde-core-concept-14-speculative-tool-fanout-zh/)、[7](/posts/fde-core-concept-7-indirect-prompt-injection-zh/) |
| （三）企業級 AI 整合與部署 | 雲端平台、安全合規、RAG、資料管線 | [9](/posts/fde-core-concept-9-data-residence-sovereign-ai-zh/)、[10](/posts/fde-core-concept-10-cmek-byok-envelope-zh/)、[8](/posts/fde-core-concept-8-pii-deidentification-zh/)、[4](/posts/fde-core-concept-4-hybrid-search-rrf-zh/)、[5](/posts/fde-core-concept-5-reranking-cross-encoder-zh/)、[11](/posts/fde-core-concept-11-async-event-driven-pipeline-zh/) |
| （四）生產環境監控與最佳化 | LLM 指標、分散式追蹤、故障診斷、成本 | [20](/posts/fde-core-concept-20-rag-triad-metrics-zh/)、[19](/posts/fde-core-concept-19-llm-judge-bias-mitigation-zh/)、[22](/posts/fde-core-concept-22-structured-troubleshooting-zh/)、[18](/posts/fde-core-concept-18-semantic-model-routing-zh/)、[17](/posts/fde-core-concept-17-context-caching-eviction-zh/) |
| （五）客戶協作與問題解決 | 需求分析、技術溝通、交付管理、ROI | [21](/posts/fde-core-concept-21-discovery-to-constraints-zh/)、[23](/posts/fde-core-concept-23-stakeholder-mapping-zh/)、[24](/posts/fde-core-concept-24-poc-scoring-roi-zh/)、[25](/posts/fde-core-concept-25-value-story-objection-zh/) |

---

## 十、摘要

- FDE 的輸入是客戶的限制條件，輸出是能跑的系統；技能依照這條轉換路徑分成四個堆疊，而不是依照工具或套件。
- **建模與檢索**決定模型看到什麼，**代理與執行**決定系統怎麼一步步做，**平台與安全**決定在哪裡跑、多快、誰能碰，**客戶與交付**決定該不該建、建多大、怎麼證明。
- 前三個堆疊是一個請求依序穿過的路徑；第四個堆疊是包在外面的迴圈，約束清單從它流進來，可量化的結果從它流出去。
- 四個堆疊互相牽動：約束決定規模、評估決定 PoC 能否打分、安全邊界改寫狀態機的圖、觀測點決定排錯能否逐層進行。
- 從你的背景挑一條五篇的路線開始；讀完後的缺口就是下一條路線。

全部 25 篇都收在 [fde-core-topic](/tags/fde-core-topic/) 標籤下。
