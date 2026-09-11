---
title: "Mem0 Intro Part 5 — 生產部署 — OSS 與 Platform 的分界線在哪裡"
date: 2026-09-11T18:00:00+08:00
draft: false
weight: 5
description: "Mem0 原始碼導讀系列最終篇：拆解 OSS 與 Platform 的完整差異、Graph Memory／Temporal Reasoning／Memory Decay／Dream 四個專屬能力各自解決什麼問題與 OSS 的補法、v2→v3 破壞性變更遷移清單、怎麼用官方開源評測框架測自己的資料，以及一份生產檢查清單。"
categories: ["all", "ai", "engineering", "infrastructure", "architecture"]
tags: ["Mem0", "Production", "AI Agent", "Memory", "Evaluation", "MCP", "LangGraph", "繁體中文"]
authors: ["yen"]
readTime: "27 min"
---

> *大多數人評估「要用開源版還是託管版」的方式，是比較功能清單的長度，然後選比較便宜的那個。*
> *真正的答案是：功能清單只告訴你今天缺什麼，不告訴你半年後你會自己寫出什麼。*
> *Mem0 的 OSS 與 Platform 之間那條線，剛好切在「記憶治理」上——而 ADD-only 架構保證了你遲早要處理它。*
> *你不是在選要不要付錢，是在選要不要自己寫。*

---

## 前言

前四篇拆完了 OSS 的全貌：[全景架構](/posts/mem0-intro-part1-architecture-overview-zh/)、[ADD-only 寫入](/posts/mem0-intro-part2-add-extraction-pipeline-zh/)、[三訊號檢索](/posts/mem0-intro-part3-hybrid-retrieval-zh/)、[儲存層選型](/posts/mem0-intro-part4-storage-backends-zh/)。

一路上反覆出現同一句話：**「這個在 Platform 有，OSS 沒有。」** 圖記憶、時序推理、記憶衰減、背景整合、自訂分類、webhook。

這一篇把那條線畫清楚，並且回答一個更實際的問題：**如果你選 OSS，你必須自己補哪些東西，以及那大概要花多少工。**

本篇的目標：**讀完之後，你能做出一個有依據的 OSS/Platform 決策，能完成 v2→v3 的遷移，能用官方開源的框架測自己的資料，並且有一份可以照抄的生產檢查清單。**

---

## 一、核心問題：那條線切在哪裡

官方文件對這件事相當坦白，開宗明義寫著兩者「run the same core extraction and retrieval logic」，差別在三類東西：

```
        ┌────────────────────────────────────────────────────┐
        │  完全相同的部分                                     │
        │  · add / search / get / get_all / update /          │
        │    delete / delete_all / history 全套 API           │
        │  · user_id / agent_id / run_id 作用域                │
        │  · AND / OR / NOT 過濾組合、萬用字元                 │
        │  · 實體感知排序（兩邊都抽實體、都用共享實體加權）    │
        │  · 多模態輸入、記憶過期、reranking、程序記憶         │
        │  · custom_instructions                              │
        │  · Python / JS SDK + REST API                       │
        └────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ 差異一：託管   │  │ 差異二：搜尋排序  │  │ 差異三：管理面    │
│                │  │ （v3-only）      │  │                  │
│ · 誰跑向量庫   │  │ · Graph Memory   │  │ · 組織／專案      │
│ · 誰負責擴充   │  │ · Memory Decay   │  │ · app_id 租戶隔離 │
│ · 有沒有       │  │ · Temporal       │  │ · 專案級事件流    │
│   dashboard    │  │   Reasoning      │  │ · 自訂分類        │
│                │  │ · Dream          │  │ · Webhook         │
│ ← 這是錢的問題 │  │ ← 這是工程量問題 │  │ ← 這是產品面問題  │
└───────────────┘  └──────────────────┘  └──────────────────┘
```

**差異一是最不重要的那個。** 自架一套 pgvector 不難，Part 4 講過。

**差異二才是關鍵**，因為它們全都在解同一個問題：**ADD-only 架構產生的記憶熵增**。Part 2 的結論是「v3 刻意接受了記憶只增不減的代價，把治理責任外移」——**Platform 就是那個「外面」**。

---

## 二、四個 Platform 專屬能力，以及 OSS 的補法

### 2.1 Graph Memory：從外接圖庫變成內建

**變更歷史**：v2 的 OSS 可以接 Neo4j / Memgraph / Kuzu / Apache AGE，用 `enable_graph` + `graph_store` 設定。v3 **把這個整合從 OSS 移除**，改成 Platform 內建、永遠開啟。

官方遷移文件的原話：

> **Graph memory**: `enable_graph` + `graph_store` in config → **Removed**. Graph memory is removed from OSS. It's a built-in, always-on Mem0 Platform feature.

以及平台對照表裡更精確的說明：

> OSS still extracts entities and uses them to boost ranking, but **there is no queryable graph and no `relations` field**.

**所以 OSS 失去了什麼、保留了什麼**：

```
保留：實體共現加權
  查詢「Alice」→ 實體庫查到 Alice → 拿到 linked_memory_ids → 加權那些記憶
  ← Part 3 第四節的那個公式，OSS 完整保有

失去：多跳遍歷與關係查詢
  「Alice 的同事的專案」——這需要沿著邊走兩跳
  「Alice 和 Bob 是什麼關係」——這需要邊有型別（COLLEAGUE / MANAGES / ...）
  OSS 的實體庫只有 entity → [memory_ids] 這種扁平的反向索引，
  沒有 entity → entity 的邊，也沒有邊的型別
```

**OSS 的補法**：

| 需求 | 補法 | 工程量 |
|---|---|---|
| 只要實體加權 | **不用補**，OSS 已經有 | 0 |
| 要「關於 X 的一切」 | `get_all` + metadata filter，寫入時把實體寫進 metadata | 小 |
| 要多跳關係查詢 | 自己在 Mem0 外面掛一個圖庫，寫入後把實體對寫進去 | 中—大 |
| 要關係型別 | 需要 LLM 抽關係三元組，成本會顯著上升 | 大 |

**誠實的建議**：**先確認你真的需要圖。** 多數對話記憶場景，「關於 Alice 的一切」用實體加權就夠了，而多跳查詢（「Alice 的同事的專案」）在真實產品裡的出現頻率遠低於你的想像。**如果你真的需要圖，那可能該考慮的是一個以時序知識圖為核心的系統，而不是在 Mem0 外面補一個。**

### 2.2 Temporal Reasoning：時序訊號

**Platform 做什麼**：寫入時用一個獨立的推理階段，讀出每條記憶的時間中繼資料——事件何時發生、是進行中還是已完成、時間精度如何、以及記憶型別（事件／狀態／計畫／偏好／關係／缺席）。檢索時把查詢的時序意圖分類（**不額外呼叫 LLM**），再用這些中繼資料算一個加分項。

官方強調兩點：這個推理階段**獨立於萃取、可非同步跑**，所以寫入延遲不受影響；以及時序分數是**加分而非過濾**，「semantic relevance always dominates」——它只會把正確的那個日期版本往前推，不會把候選整個踢掉。

**效果**：LongMemEval 的 temporal_reasoning 分項達到 97.0，LoCoMo 的 temporal 是 92.0。

**OSS 完全沒有**。傳 `timestamp` 或 `reference_date` 會直接拋錯：「not supported by the OSS Memory SDK」。

**OSS 的補法**（Part 3 第八節講過，這裡按投入產出比排序）：

```
補法一（最便宜，效果最好）：把時間寫進記憶文字
  custom_instructions = "當事實涉及狀態變化（居住地、職稱、關係、目標），
                        務必在記憶文字中包含對話發生的日期。"

  「使用者自 2026 年 8 月起住在柏林」
  → 時間進了語意向量，查詢「他現在住哪」時帶年份的那條匹配更好
  工程量：一行設定

補法二：檢索後在應用層按 created_at 重排同主題記憶
  工程量：20 行程式碼 + 寫入時要標 topic

補法三：把新舊都給 LLM，附上日期，讓它自己判斷
  「已知關於使用者：
     - [2025-03-14] 使用者住在里斯本
     - [2026-08-02] 使用者住在柏林」
  工程量：改一下 prompt 模板
  ← 現代模型處理這種明確標註的矛盾相當可靠。這其實最符合 ADD-only
    的設計哲學：保留證據，讓最有能力判斷的那一層判斷。

補法四：expiration_date（OSS 支援！）
  對天生有時效的事實在寫入時就標好過期日
  工程量：加一個參數
```

**四個補法加起來，能覆蓋 Platform 時序推理的大部分實用價值**，而且工程量都很小。這是四個專屬能力裡最容易自己補的一個。

### 2.3 Memory Decay：用「最近有沒有被用到」重排

**Platform 做什麼**：每條記憶記錄「最後一次被取回是什麼時候、被取回過幾次」，把這個歷史換算成一個 **0.3× 到 1.5×** 的縮放因子，乘進檢索分數。

```
記憶狀態              縮放因子      排序效果
─────────────────────────────────────────────
剛剛被取回            ≈ 1.5×        強加分
今天被碰過            1.2 – 1.4×    輕度加分
閒置幾天              0.6 – 1.0×    輕度抑制
閒置數週              0.4 – 0.6×    較強抑制
閒置數月／數年        ≈ 0.3×        地板，不會再低
```

檢索流程也很有意思：先把候選池擴大到 `top_k × 3`（最低 50）給重排留空間，用**未截斷**的乘積排序（讓 0.3–1.5 的完整範圍能真的重排），但**回傳的 `score` 會被 clamp 到 [0,1]** 以維持 API 契約，最後對回傳的每條記憶做一次 fire-and-forget 的「強化」（存取歷史 +1，最多保留最近 20 次）。

**設計上的克制值得注意**：0.3 是地板不是零——**衰減永遠不會讓一條記憶消失**，只會降低它的排名。這符合 ADD-only 的一貫哲學。

**OSS 沒有**。傳 `decay` 會拋錯。

**OSS 的補法**：

```python
# 自己維護存取計數：在 search() 之後，對回傳的記憶更新 metadata
results = m.search(q, filters={"user_id": u}, top_k=60)["results"]

# 應用層重排
import math, datetime
def decay_factor(meta):
    last = meta.get("last_accessed") or meta.get("created_at")
    days = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.datetime.fromisoformat(last)).days
    return max(0.3, min(1.5, 1.5 * math.exp(-days / 30)))

reranked = sorted(results,
                  key=lambda r: r["score"] * decay_factor(r.get("metadata") or {}),
                  reverse=True)[:10]

# fire-and-forget 更新存取時間（丟到背景 task）
for r in reranked:
    background_update(r["id"], {"last_accessed": now_iso()})
```

**工程量：中等。** 難的不是公式，是那個 fire-and-forget 的更新——`m.update()` 會重新嵌入記憶文字（浪費），而且高頻更新會對向量庫造成寫入壓力。務實的做法是**把存取計數放在一個獨立的 Redis 或 SQL 表裡**，不要塞進向量庫的 metadata。

### 2.4 Dream：背景整合

這是四個裡面**最難自己補、也最有價值**的一個。它有三個動作：

| 動作 | 做什麼 | 何時跑 | 可用性 |
|---|---|---|---|
| **Supersede** | 新事實與舊事實矛盾時，把舊的標記為已被取代並連結到新的 | 加入記憶時 | 所有方案，永遠開 |
| **Merge** | 把重複的記憶折疊成單一正規版本 | 加入記憶時 | 所有方案，永遠開 |
| **Synthesis** | 把多條記憶蒸餾成更高階的「模式記憶」 | 排程、背景 | 需開啟（Pro 以上） |

**Supersede 的關鍵設計**：被取代的記憶**不刪除、不隱藏**。一般的 `search` 或 `get` 仍會回傳它們，只是帶上「已被取代」的標記。要只拿現況時，明確傳 `latest_only=true`。

**這正是 Part 2 那個問題的正解**：不是在寫入時決定要不要覆蓋（v2 的錯誤），也不是完全不處理（v3 OSS 的現狀），而是**保留兩者但標記關係，讓讀取端決定**。

**Synthesis 的例子**（官方文件的）：四條分別講跑步、重訓、Garmin 手錶、馬拉松目標的記憶，被蒸餾成一條：

> *「使用者維持結構化的健身routine，包含每週長跑（約 40 公里）、規律的腿背重訓、用 Garmin 裝置追蹤訓練，並持續追求漸進的馬拉松時間目標。」*

四條來源記憶**原封不動留著**，新的模式記憶連回它們作為證據。官方強調它是「additive and idempotent」——重跑不會產生重複的模式。

兩個限制值得記：Synthesis **只看純 `user_id` 作用域的記憶**（同時帶 `agent_id` / `run_id` / `app_id` 的會被排除）；而且**只處理啟用之後建立的記憶**，不會回頭批次處理歷史資料。

**OSS 的補法**：

```
Merge  → Part 2 第七節的週期性合併作業
         每週撈 get_all()，相似度 > 0.92 的群組交給 LLM 合併
         工程量：中（一個排程作業 + LLM 呼叫 + 自己的稽核表）

Supersede → 這個最難。要判斷「矛盾」需要 LLM，而且要在
           正確的候選範圍內判斷（不能只看 top-10）
           務實的替代：用 metadata 的 topic 分群 + created_at 取最新
           工程量：中—大

Synthesis → 一個週期性的「為每個活躍使用者產生 profile 摘要」作業
           把摘要用 infer=False 寫回去（記得標 metadata 區分）
           工程量：中
```

**三者加起來大概是一到兩週的工程量，加上持續的維護成本。** 這是評估 OSS vs Platform 時該放進天平的那個數字——不是月費多少，是**這些作業值不值得你的團隊寫和養**。

---

## 三、決策：OSS 還是 Platform

```
選擇              選 OSS 的理由                      選 Platform 的理由
──────────────────────────────────────────────────────────────────────────
資料主權          資料完全在自己的基礎設施           ← OSS 勝
成本              大量使用時單位成本低               小量使用時 Platform 更划算
                  （但要算進工程與維運人力）           （不用養任何東西）
後端自由度        25 種向量庫、18 種 LLM 任選        ← OSS 勝
                  可用本機模型完全離線
記憶治理          **要自己寫**（Merge/Supersede/     ← Platform 勝，而且差距最大
                  Decay/時序）
圖查詢            沒有（只有實體加權）               原生、永遠開
管理面            沒有 dashboard、沒有組織/專案      有
                  沒有 webhook、沒有事件流
上線速度          看你的向量庫與 LLM 設定            幾分鐘（只要 API key）
benchmark 分數    「directionally similar gains      官方公布的數字是這個
                  but not identical numbers」
──────────────────────────────────────────────────────────────────────────
```

**三個判斷訊號**（比功能表更實用）：

```
訊號一：你開始寫「哪條記憶才是最新的」的邏輯了嗎？
  → 是：你正在重造 Supersede。評估一下這條路要走多遠。

訊號二：你的記憶庫在三個月後，單一活躍使用者累積了多少條？
  → 超過 200 條且你一眼看得出大量同義重複 → 你需要 Merge。

訊號三：合規要求資料不出境嗎？
  → 是：沒得選，只能 OSS。此時要把治理作業的工程量正式排進 roadmap，
       而不是等到出問題才處理。
```

**一個折衷路線值得考慮**：用 OSS 跑 `search()`（高頻、低成本、無 LLM），用自己的排程作業處理治理。**這條路的關鍵是先把 Part 3 第五節的標註集建起來**——沒有它，你無法判斷自己補的治理作業是讓系統變好還是變壞。

---

## 四、v2 → v3 遷移清單

如果你有既有的 Mem0 程式碼，這一節是你最需要的。官方遷移文件開頭就掛了一個警告：「**Breaking changes ahead.** This release includes renamed parameters, removed parameters, changed defaults, and a fundamentally different extraction model.」

### 4.1 Python OSS 的破壞性變更

| 變更 | 舊 | 新 | 怎麼改 |
|---|---|---|---|
| `search()` / `get_all()` 的實體 ID | 頂層參數 `user_id="..."` | **放進 `filters`** | `m.search("q", filters={"user_id": "..."})`；用舊寫法會拋 `ValueError` |
| `top_k` 預設 | 100 | **20** | 要舊行為就明確傳 `top_k=100` |
| `threshold` 預設 | `None`（不過濾） | **0.1** | 要舊行為傳 `threshold=0.0` |
| `threshold` 驗證 | 任意 float | **必須在 [0,1]** | 超範圍會拋 `ValueError` |
| `rerank` 預設 | `True` | **False** | 要舊行為傳 `rerank=True` |
| 實體 ID 驗證 | 接受任意字串 | **trim 後拒絕空字串與含內部空白** | 傳乾淨的識別碼 |
| `add()` 的 `messages` | 可以是 `None` | **必須是 str / dict / list[dict]** | 其他型別拋 `Mem0ValidationError`（`VALIDATION_003`） |
| `add()` 回傳的事件 | `ADD` / `UPDATE` / `DELETE` | **只有 `ADD`** | 移除期待 UPDATE/DELETE 的程式碼 |
| 自訂萃取提示詞 | `custom_fact_extraction_prompt` | **`custom_instructions`** | 改名 |
| 自訂更新提示詞 | `custom_update_memory_prompt` | **廢棄** | 改用 `custom_instructions` |
| 圖記憶 | `enable_graph` + `graph_store` | **移除** | 見 2.1 |
| Qdrant client | `>=1.9.1` | `>=1.12.0` | 升相依 |
| Upstash client | `>=0.1.0` | `>=0.6.0` | 升相依 |

### 4.2 TypeScript OSS 額外要注意的

除了對應的改動之外，有一個**只有 TS 才有的坑**：

| 變更 | 說明 |
|---|---|
| `limit` → `topK` | 參數改名 |
| 詞形還原欄位 | `text_lemmatized`（snake_case）→ **`textLemmatized`（camelCase）** |

那個欄位改名的後果，官方文件講得很清楚：

> If you share a vector store collection between Python and TS SDKs, **lemma-based BM25 will not resolve across languages**: keep collections language-scoped.

**翻譯：Python 寫進去的記憶，TS 的 BM25 檢索不到；反之亦然。** 如果你有混合技術棧，**兩邊必須用不同的 collection**，或者統一只用一種 SDK 寫入。這是一個很隱蔽、且只會表現為「檢索品質莫名變差」的問題。

### 4.3 建議的遷移順序

```
1. 先升版但不改程式碼，跑測試 → 收集所有 ValueError / 驗證錯誤
   ← 好消息：v3 把大部分不相容都改成「明確拋錯」而不是靜默行為改變

2. 修 filters 的位置問題（最常見）

3. 明確寫出三個預設值：top_k / threshold / rerank
   ← 就算你想用新預設，也明確寫出來，避免下次改版又被動

4. 移除任何依賴 UPDATE / DELETE 事件的邏輯

5. 如果用過 graph_store：評估 2.1 的四種補法

6. **重跑你的標註集**（Part 3 第五節）
   ← 這一步不能跳。extraction 模型換了、預設值換了、
     ADD-only 換了——召回行為一定變了，你需要知道變好還是變壞

7. 考慮跑一次全量重萃取
   ← 舊的記憶是用 v2 的 prompt 萃出來的，品質與新萃出的不一致。
     要不要重跑取決於你的記憶量與預算
```

---

## 五、評測：用官方框架測自己的資料

Mem0 把整套評測框架開源在 [`mem0ai/memory-benchmarks`](https://github.com/mem0ai/memory-benchmarks)，而且**同時支援 Mem0 Cloud 與自架 OSS 後端**。

```bash
git clone https://github.com/mem0ai/memory-benchmarks.git
cd memory-benchmarks
pip install -r requirements.txt

# 測自架 OSS
cp .env.example .env          # 填 OPENAI_API_KEY
docker compose up -d          # 起本機 Mem0 server + Qdrant
# Mem0 server: http://localhost:8888
# Qdrant:      http://localhost:6333
```

### 5.1 三個 benchmark 該怎麼看

| Benchmark | 測什麼 | 規模 | 官方分數 |
|---|---|---|---|
| LoCoMo | 單跳／多跳／開放域／時序回憶 | 小 | 92.5（6,956 tokens） |
| LongMemEval | 單／多 session、知識更新、時序 | 中 | 94.4（6,787 tokens） |
| BEAM | 十類任務 | **1M / 10M token** | 64.1 / **48.6** |

**BEAM 的 10M 結果才是真相**。從 1M 到 10M，幾個分項的崩塌幅度很說明問題：

```
分項                    1M      10M     變化
────────────────────────────────────────────
preference_following    88.3 →  90.4    持平（甚至更好）
instruction_following   85.2 →  82.5    輕微下降
knowledge_update        65.0 →  75.0    反而上升
information_extraction  70.0 →  56.3    下降
summarization           63.5 →  46.9    明顯下降
multi_session_reasoning 65.2 →  26.1    ← 崩塌
event_ordering          53.6 →  20.2    ← 崩塌
temporal_reasoning      61.8 →  16.3    ← 崩塌
```

**規律很清楚**：「查一個事實」類的任務在大規模下仍然穩健（偏好、指令、知識更新），而「把多個事實按時間或因果串起來」的任務會崩塌。官方也直說這是「open problems across the field」，需要「higher-order representations of how events relate to each other across time」。

**對你的產品意義**：如果你的功能依賴「記得使用者喜歡什麼」——記憶層很可靠。如果依賴「推理出這些事件的先後順序」——**在大規模下不要相信它**，設計上要有降級路徑。

### 5.2 做自己的評測

官方 benchmark 是英文的，跟你的場景大概率不像。建議的做法：

```
1. 從生產 log 抽 50–100 組 (對話, 後續查詢, 期望撈到的記憶)
   ← 「期望撈到哪條」要人工標，這是全部的成本所在

2. 定義兩個指標：
   · Recall@k：期望的記憶有沒有進 top-k
   · Token 數：實際塞進 prompt 的 token
   ← 兩個都要看。只看 recall 會讓你一路把 top_k 調大

3. 建立基線，然後只改一個變數重跑：
   · 換 embedder
   · 開/關 reranker
   · 調 threshold
   · 換萃取模型
   · 開/關 infer

4. 把這個跑成 CI 的一部分
   ← 記憶系統的品質退化是靜默的。沒有回歸測試，
     你會在使用者抱怨的時候才發現三週前的那次改動出了問題
```

**第 4 點是多數團隊會跳過、然後後悔的那一步。**

---

## 六、整合生態

Mem0 的整合面很廣，值得知道有哪些，避免重造輪子。

```
Agent 框架       LangChain / LangGraph / LlamaIndex / CrewAI / AutoGen /
                Agno / Camel AI / OpenAI Agents SDK / Mastra /
                Vercel AI SDK / Strands / Google AI ADK …

AI 編碼工具      Claude Code / Cursor / Codex / OpenCode / Kimi Code /
                Antigravity …（多半透過 MCP）

語音／即時       LiveKit / Pipecat / ElevenLabs

低程式碼         Dify / Flowise / n8n / Zapier

可觀測性         AgentOps / Respan
```

### 6.1 MCP：最通用的接法

Mem0 提供 MCP server，這是把記憶接進**任何支援 MCP 的客戶端**的最短路徑——包括 Claude Code、Cursor 等編碼工具。

**這帶出一個有趣的用法**：把 Mem0 當成**編碼 agent 的長期記憶**，記住「這個 repo 的慣例是什麼」「上次為什麼選了這個方案」「哪些檔案碰不得」。這類知識目前多半寫在 `CLAUDE.md` / `AGENTS.md` 之類的檔案裡（Mem0 自己的 repo 就有這兩個檔案），但那是靜態的——記憶層能讓它隨著使用累積。

**要注意的權衡**：編碼場景的記憶如果記錯，代價是 agent 帶著錯誤的假設改程式碼。這比聊天場景記錯偏好嚴重得多。**建議搭配 `run_id` 把實驗性的記憶隔離開**，確認有用了再升級到 `user_id` 作用域。

### 6.2 框架整合的一個共同陷阱

多數框架整合都提供一個「自動記憶」的 wrapper：每輪對話自動 `add()`、每次呼叫前自動 `search()`。**很方便，也很貴。**

Part 2 算過每次 `add()` 約 $0.002–0.02。自動模式下，一個 20 輪的對話就是 20 次 `add()`——而其中可能只有 3 輪有值得記的東西。

**建議**：用框架整合起步，但**盡快換成手動控制**——自己決定什麼時候呼叫 `add()`。一個簡單的過濾器（長度、是否第一人稱陳述、是否含決定性動詞）就能砍掉 50–70% 的無效呼叫。

---

## 七、成本模型與可觀測性

### 7.1 錢花在哪裡

```
┌──────────────────────────────────────────────────────────┐
│  LLM 萃取（占 90%+）                                      │
│  每次 add() 約 $0.002–0.02                                │
│  × 日均 add() 次數                                        │
│  ← 唯一有意義的優化方向                                    │
├──────────────────────────────────────────────────────────┤
│  Embedding（占 5%）                                        │
│  每次 add() 3 批、每次 search() 1 次                       │
│  單價極低（~$0.00002/次）                                  │
├──────────────────────────────────────────────────────────┤
│  向量庫（占 3%）                                           │
│  隨記憶總數線性成長                                        │
│  1536 維 × 4 bytes = 6 KB/向量                             │
├──────────────────────────────────────────────────────────┤
│  Reranker（若開，占 2%）                                   │
│  每次 search() 一次 API 呼叫                               │
└──────────────────────────────────────────────────────────┘
```

**降成本的優先順序**（效果由大到小）：

1. **減少 `add()` 的次數**——不是每輪都記。一個前置過濾器的投資報酬率最高。
2. **對結構化內容用 `infer=False`**——表單欄位、系統事件、明確設定，零 LLM 成本。
3. **換更便宜的萃取模型**——但要先用自己的語料驗證萃取品質。
4. 其他都是噪音。

### 7.2 該監控的六個指標

Mem0 沒有內建 metrics 端點，這些要自己埋：

| 指標 | 怎麼算 | 警訊 |
|---|---|---|
| `add()` 的 LLM 呼叫量與成本 | 從 LLM client 埋 | 週環比成長超過對話量的成長 → 萃取變囉嗦了 |
| 每次 `add()` 產生的記憶數 | 回傳陣列長度 | **持續 > 5 → 可能在重複萃取既有記憶**（Part 2 的失敗模式） |
| 每使用者記憶總數 | 定期 `get_all()` 統計 | 活躍使用者 > 200 且同義重複明顯 → 該做合併作業了 |
| `search()` 的 Recall@k | 靠標註集，離線跑 | 下降 → 有東西壞了 |
| `search()` 的 `max_possible_score` 分布 | `explain=True` 抽樣 | 不是 2.5 → 有訊號沒在跑（Part 3、Part 4） |
| `messages` 表大小 | SQL count | 無限成長 → 清理作業沒跑 |

**第二個指標是最有診斷價值也最少人看的。** 如果每次 `add()` 都產出 8–10 條記憶，而你的對話其實沒那麼多新資訊，八成是 LLM 把既有記憶當成新事實重新輸出了——記憶庫會以每次對話翻倍的速度爆炸。

---

## 八、生產檢查清單

**安裝與設定**
- [ ] `pip install "mem0ai[nlp]"` 且下載了 spaCy 模型（否則實體訊號靜默失效）
- [ ] 向量庫**確認支援 `keyword_search`**——用 `explain=True` 看 `max_possible_score` 是不是 2.5
- [ ] 版本鎖定，不用 `latest`（v2→v3 這種改版會直接改變行為）
- [ ] 三個預設值明確寫出：`top_k`、`threshold`、`rerank`
- [ ] embedder 在 POC 階段就選定（換了要全量重建）

**架構**
- [ ] `add()` **不在請求路徑上**——丟背景 task 或佇列
- [ ] `search()` 在呼叫模型前，結果有篩選後才進 prompt（不是全塞）
- [ ] 有一個 wrapper 強制注入 `user_id`，業務程式碼碰不到裸的 Mem0（Part 4 第六節）
- [ ] 多進程時 history 不用本機 SQLite

**治理（ADD-only 的必要補償）**
- [ ] 有週期性的合併去重作業
- [ ] 有 `messages` 表的清理作業
- [ ] 會過時的事實有設 `expiration_date` 或有時序補法
- [ ] `custom_instructions` 要求記憶文字包含日期

**安全與合規**
- [ ] 刪除流程涵蓋**四處**：向量庫記憶、實體庫、`history` 表、`messages` 表
- [ ] 已實際跑過一次刪除並到資料庫確認乾淨
- [ ] 知道 `messages` 表存的是**未經萃取的原始對話**，並據此評估風險
- [ ] 不把密碼、金鑰、未遮蔽的敏感資料送進 `add()`
- [ ] `server/` 部署的 `AUTH_DISABLED` 不是 `true`

**品質**
- [ ] 有 50–100 組的標註集
- [ ] 標註集跑成 CI 的一部分
- [ ] 每次改 embedder / 模型 / 參數都重跑
- [ ] 監控「每次 `add()` 產生幾條記憶」

**成本**
- [ ] 有前置過濾器，不是每輪都 `add()`
- [ ] 結構化內容走 `infer=False`
- [ ] LLM 呼叫量有監控與告警

---

## 九、為什麼選 X 不選 Y（彙整）

```
選擇                選 X 的理由                      不選 Y 的理由 / 翻轉條件
──────────────────────────────────────────────────────────────────────────────
OSS                 資料主權、後端自由、成本可控      要自己寫記憶治理
vs Platform         ────────────────────────────────────────────────────────
                    翻轉條件：見第三節的三個訊號。最實際的一條——當你發現
                    自己在寫「哪條才是最新」的邏輯，你正在重造 Supersede。

自己補時序          四個補法工程量都很小             Platform 的時序推理
vs 用 Platform      涵蓋大部分實用價值                LongMemEval 拿 97.0
                    ────────────────────────────────────────────────────────
                    翻轉條件：時序查詢是你產品的核心功能 → 用 Platform 或
                    改用以時序知識圖為核心的系統。偶爾用到 → 自己補就好。

自己補 Merge/Decay  可以照自己的業務規則調           一到兩週工程量 + 持續維護
vs 用 Platform      ────────────────────────────────────────────────────────
                    翻轉條件：這是四個裡最該考慮付錢的一個。合併去重要做對
                    （不誤刪、可追溯、冪等）比看起來難。

不補圖記憶          多數場景實體加權就夠              多跳關係查詢做不到
vs 外掛圖庫         ────────────────────────────────────────────────────────
                    翻轉條件：先確認你真的需要多跳查詢——在真實產品裡它的
                    出現頻率遠低於想像。真的需要 → 考慮專門的時序知識圖系統，
                    而不是在 Mem0 外面補。

手動控制 add()      成本降 50–70%                    要自己判斷什麼值得記
vs 框架的自動記憶   ────────────────────────────────────────────────────────
                    翻轉條件：POC 階段用自動的快速驗證。上線前一定要換手動。

先建標註集          所有調參的前提                   要人工標 50–100 組
vs 靠感覺調參       ────────────────────────────────────────────────────────
                    翻轉條件：無。沒有標註集，你對記憶系統的所有判斷都是猜的。
                    這是整個系列裡我最想強調的一件事。
```

---

## 十、系列導航

五篇走完了。回頭看，Mem0 的整個設計可以收斂成一條主線：

```
Part 1  問題：對話歷史的成本是二次方成長的，而 context 不是記憶
              → 要把「記什麼」和「取什麼」拆成兩個獨立的問題
                                    │
Part 2  寫入：單次 LLM 呼叫、ADD-only、hash 去重、spaCy 實體連結
              → 放棄了自動更新，換來不可逆錯誤的消失與成本減半
                                    │
Part 3  讀取：語意 + BM25 + 實體三訊號融合，自適應分母
              → 把「誰該排前面」的壓力全部接了下來
                                    │
Part 4  儲存：向量庫是主儲存、實體庫是反向索引、SQL 是稽核
              → 後端選擇決定了上面的機制有沒有真的在跑
                                    │
Part 5  治理：ADD-only 的熵增要靠外部解決
              → 那個「外部」就是 OSS 與 Platform 的分界線
```

每一層都在為下一層創造條件，而**每一個設計決策都有一個明確的代價**。這個系列反覆出現的方法論其實只有一句：**先確認機制真的在跑，再談調參。**

最後三個實務建議：

1. **先建標註集，再做任何其他事。** 50 組 (對話, 查詢, 期望記憶) 是你調校記憶系統的唯一依據。沒有它，換 embedder、開 reranker、調 threshold 全部是在賭。
2. **用 `explain=True` 確認三條訊號都在跑。** `max_possible_score` 不是 2.5，就代表你以為有的東西其實沒有。這個檢查只要一分鐘，卻能解釋大量「為什麼效果不如預期」。
3. **把 ADD-only 的治理成本正式排進 roadmap。** 它不會自己消失，而且它出現的時間點通常是產品剛開始成長、你最忙的時候。不管是自己寫還是付錢買，都要在那之前決定。

← [Part 4 — 儲存層與後端選型 — 三個 store、25 種向量庫與那個關鍵能力差異](/posts/mem0-intro-part4-storage-backends-zh/)

系列全部文章：

- [Part 1 — 全景架構 — 為什麼 Agent 需要一個記憶層而不是更長的上下文](/posts/mem0-intro-part1-architecture-overview-zh/)
- [Part 2 — 寫入路徑 — ADD-only 萃取管線與那次自我否定](/posts/mem0-intro-part2-add-extraction-pipeline-zh/)
- [Part 3 — 讀取路徑 — 語意、關鍵字與實體的三訊號融合](/posts/mem0-intro-part3-hybrid-retrieval-zh/)
- [Part 4 — 儲存層與後端選型 — 三個 store、25 種向量庫與那個關鍵能力差異](/posts/mem0-intro-part4-storage-backends-zh/)
- **Part 5（本篇）— 生產部署 — OSS 與 Platform 的分界線在哪裡**

---

*本文基於 mem0 `main` 分支（2026 年 9 月，版本 2.0.20）原始碼與官方文件撰寫。OSS 與 Platform 的差異對照 `docs/platform/platform-vs-oss.mdx`，遷移清單對照 `docs/migration/oss-v2-to-v3.mdx`，benchmark 數字與 Dream／Memory Decay 的機制對照 `docs/core-concepts/memory-evaluation.mdx` 與 `docs/platform/features/`。官方明載 benchmark 分數反映的是託管平台（含 OSS 沒有的專有優化），自架版本應預期方向一致但數值不同。成本與工程量估計為量級估算。*
