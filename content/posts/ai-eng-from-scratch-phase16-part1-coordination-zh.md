---
title: "AI 工程從零開始｜Phase 16 Part 1：多 Agent 協調 — 分工、通訊與共識"
date: 2026-06-22T01:30:00+08:00
draft: false
weight: 34
description: "深入解析多 Agent 系統協調工程：Supervisor/Peer-to-Peer/Market 協調模式、Agent 間通訊協議、衝突解決、任務分配與共識機制"
categories: ["engineering", "ai", "all"]
tags: ["AI", "Multi-Agent", "Coordination", "Swarm", "Agent Communication", "RKK", "Interview"]
authors: ["yen"]
readTime: "23 min"
series: ["ai-eng-from-scratch"]
---

> *大多數人看到多 Agent 系統，第一反應是「多幾個 Agent 就能平行加速」。*
> *工程現實卻是：沒有協調機制的多 Agent，比單 Agent 更慢、更貴、更難除錯。*
> *正確答案是：先確定協調模式，再決定幾個 Agent——而不是反過來。*
> *協調成本才是多 Agent 系統的真正瓶頸，比 LLM token 更貴。*

---

## 面試情境

> 你負責設計一個研究助理平台：使用者輸入一個複雜問題，系統要自動拆解子任務、分派給不同專業 Agent（搜尋、摘要、數據分析、引用驗證），最後整合回一份報告。規模目標是 2,000 個並發研究任務，每個任務平均涉及 8 個子 Agent。請說明協調架構如何設計，以及當兩個 Agent 搶同一份外部資源時你怎麼處理衝突？

---

## 一、核心問題：多 Agent 協調比單 Agent 難在哪裡

### 1.1 單 Agent 的極限在哪裡

單一 LLM Agent 在以下情境開始出現瓶頸：

| 情境 | 問題 | 數字 |
|------|------|------|
| 超長 context | 精度隨 token 數下降 | > 32K tokens 後 recall 掉 15–30% |
| 串行任務鏈 | 無法利用並行，延遲線性增長 | 10 步 × 3s = 30s |
| 異構技能需求 | 同一 Agent 無法同時是程式碼專家與法律專家 | prompt 膨脹、精度下降 |
| 長時間運行 | 上下文視窗耗盡，需要切割狀態 | 超過 4 小時任務必須外化記憶 |

多 Agent 解決了以上問題——但引入了一整類新問題：

**協調成本** = 通訊延遲 + 同步開銷 + 衝突解決 + 狀態一致性

在任務粒度太細時，協調成本 > 並行收益，整體反而更慢。

### 1.2 協調的三個根本挑戰

**挑戰一：誰負責什麼（任務分配）**
- 靜態分工：事先定義每個 Agent 的職責邊界
- 動態分工：任務在執行時才決定由誰承擔
- 兩者都需要「知識地圖」——Agent 有什麼能力

**挑戰二：誰知道什麼（資訊共享）**
- Agent A 找到的資訊，Agent B 何時能看到？
- 共享記憶體的一致性 vs 訊息傳遞的隔離性
- 資訊過時（stale）導致重複工作或決策矛盾

**挑戰三：誰說了算（衝突仲裁）**
- 兩個 Agent 對同一問題得出不同結論
- 兩個 Agent 同時想寫同一個輸出
- 優先級衝突：Agent A 認為現在該停止，Agent B 認為應繼續

---

## 二、三個演進階段（POC → MVP → Scale）

### ╔══ Phase 1：POC（< 5 個並發任務）══╗

```
┌─────────────────────────────────────────────┐
│              Orchestrator Script             │
│   (Python / LangGraph 線性 DAG)             │
└──────────────┬──────────────────────────────┘
               │ 直接函數呼叫（同步）
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌───────┐  ┌───────┐  ┌───────┐
│Search │  │Summar-│  │Cite   │
│Agent  │  │ize    │  │Verify │
│       │  │Agent  │  │Agent  │
└───────┘  └───────┘  └───────┘
    │          │          │
    └──────────┴──────────┘
               │
               ▼
        ┌────────────┐
        │  Shared    │
        │  Dict/JSON │
        └────────────┘
```

**特徵：**
- 協調邏輯寫死在 Python/TypeScript 腳本
- Agent 間用共享 dict 傳遞資料（無鎖）
- 無容錯：任一 Agent 失敗即整個流程中斷
- 建置時間：1–2 天

**可接受的捷徑：**
- 不做重試，失敗直接回報給使用者
- 不做衝突檢測，假設任務互不重疊
- 不做審計日誌

**遺留問題：** 無法並行、無法橫向擴展、無可觀測性

---

### ╔══ Phase 2：MVP（10–200 個並發任務）══╗

```
┌────────────────────────────────────────────────────┐
│                  Supervisor Agent                   │
│   (LLM-based + 規則引擎 + 任務佇列管理)            │
└────────────┬───────────────────────────────────────┘
             │  JSON 訊息（async）
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│Worker  │ │Worker  │ │Worker  │
│Agent 1 │ │Agent 2 │ │Agent N │
│(Search)│ │(Summ.) │ │(Code)  │
└────┬───┘ └────┬───┘ └────┬───┘
     │          │          │
     └──────────┴──────────┘
                │
     ┌──────────▼──────────┐
     │   Task Queue        │
     │   (Redis Streams)   │
     └──────────┬──────────┘
                │
     ┌──────────▼──────────┐
     │   Shared State      │
     │   (Redis Hash +     │
     │    版本鎖)           │
     └─────────────────────┘
```

**新增組件：**
- Redis Streams 作為任務佇列（持久化、可重播）
- 版本鎖（optimistic locking）防止共享狀態覆寫
- Supervisor Agent 做任務分配決策（LLM + 規則混合）
- 基本重試：失敗任務回佇列，最多 3 次

**成本增量：** +Redis（~$50/月），+Supervisor LLM 呼叫（~$0.02/任務）

**解決問題：** 可並行、有容錯、可監控
**遺留問題：** Supervisor 成為單點瓶頸，規模到 500+ 時需要分片

---

### ╔══ Phase 3：Scale（200K–1M+ 任務/天）══╗

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway / Load Balancer               │
└───────────────────────────┬─────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Supervisor  │ │ Supervisor  │ │ Supervisor  │
    │ Shard A     │ │ Shard B     │ │ Shard C     │
    │ (任務 0–33%)│ │(任務34–66%) │ │(任務67–100%)│
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
              ┌────────────▼────────────┐
              │   Kafka Topic per Type  │
              │  search/summarize/code  │
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
  ┌────────────┐   ┌────────────┐   ┌────────────┐
  │ Search     │   │ Summarize  │   │ Code       │
  │ Worker     │   │ Worker     │   │ Worker     │
  │ Pool (×10) │   │ Pool (×5)  │   │ Pool (×3)  │
  └────────────┘   └────────────┘   └────────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Distributed State      │
              │  (Redis Cluster +       │
              │   Postgres 審計日誌)    │
              └─────────────────────────┘
```

**新增組件：**
- Supervisor 水平分片（按任務 ID hash 路由）
- Kafka 替換 Redis Streams（更高吞吐，分區並行）
- Worker Pool 按 Agent 類型獨立擴縮
- Postgres 永久儲存審計日誌（合規需求）
- Circuit breaker 在下游 LLM API 超載時快速失敗

**成本：** 基礎設施 ~$2,000/月，但每任務成本比 Phase 2 低 40%（規模效應）

---

## 三、協調架構：Supervisor vs Peer-to-Peer vs Market

### 3.1 三種架構模式

```
模式一：Supervisor（集中式）
┌─────────────┐
│  Supervisor │◀── 全局視圖、分配決策
└──────┬──────┘
  ┌────┼────┐
  ▼    ▼    ▼
 A1   A2   A3   ← Worker，只執行，不決策

模式二：Peer-to-Peer（分散式）
  A1 ◀──▶ A2
  ▲          ▲
  │          │
  ▼          ▼
  A3 ◀──▶ A4      ← 每個 Agent 都有部分決策權

模式三：Market（競價式）
┌─────────────────┐
│  Task Board     │  ← 任務公告欄
└────────┬────────┘
    A1 出價 $3    A2 出價 $2    A3 出價 $5
         └──────────────────────┘
                     ▼
              最低價 A2 得標      ← 去中心化分配
```

### 3.2 三種模式比較

| 維度 | Supervisor | Peer-to-Peer | Market |
|------|-----------|--------------|--------|
| 全局最優性 | 高（中心化視圖） | 中（局部最優） | 中高（競價近似） |
| 單點失敗風險 | 高 | 低 | 低 |
| 協調延遲 | 低（1 hop） | 高（N hops） | 中（出價輪） |
| 動態適應性 | 低（需重新分配） | 高 | 高 |
| 實作複雜度 | 低 | 高 | 高 |
| 適用規模 | < 50 Agent | 任意 | 任意 |
| 典型場景 | 研究報告生成 | 模擬/遊戲 AI | 算力市場 |

**選擇原則：**
- 任務有明確 DAG 依賴 → Supervisor
- 任務高度動態、無法預知 → Peer-to-Peer
- 資源有限、需要效率最大化 → Market

---

## 四、Agent 間通訊：共享記憶體 vs 訊息佇列 vs 直接呼叫

### 4.1 三種通訊機制

**共享記憶體（Shared Memory）**
```python
# Agent A 寫入
state["search_results"] = results
state["search_done"] = True

# Agent B 讀取
if state.get("search_done"):
    data = state["search_results"]
```
- 延遲：< 1ms（本地），1–5ms（Redis）
- 問題：競爭條件（race condition），需要鎖機制
- 適用：同一進程內的緊密協作 Agent

**訊息佇列（Message Queue）**
```python
# Agent A 發布
queue.publish("task.search.done", {
    "task_id": "t123",
    "results": results,
    "timestamp": now()
})

# Agent B 訂閱
@queue.subscribe("task.search.done")
def handle_search_done(msg):
    process(msg["results"])
```
- 延遲：5–50ms（Redis Streams），10–100ms（Kafka）
- 優點：解耦、可重播、天然背壓
- 適用：跨服務、需要審計軌跡的場景

**直接 HTTP/RPC 呼叫**
```python
# Agent A 同步呼叫 Agent B
result = await agent_b.execute(
    task="summarize",
    content=search_results,
    timeout=30
)
```
- 延遲：10–200ms（含網路）
- 優點：簡單、強類型、可追蹤
- 問題：緊耦合，Agent B 失敗直接影響 A

### 4.2 通訊機制選型

| 場景 | 推薦機制 | 原因 |
|------|---------|------|
| 同進程、高頻小訊息 | 共享記憶體 + 樂觀鎖 | < 1ms 延遲 |
| 跨服務、非同步任務 | Redis Streams / Kafka | 解耦、可重播 |
| 需要即時回應的 RPC | gRPC / HTTP | 強型別、超時控制 |
| 大型檔案/向量傳遞 | 物件儲存（S3）+ 訊息通知 | 避免佇列膨脹 |

**黃金法則：** 訊息大小 > 64KB 時，永遠用引用傳遞（傳 URL）而非值傳遞（傳內容）。

---

## 五、任務分配：靜態分工 vs 動態競標

### 5.1 靜態分工

事先定義每個 Agent 的職責，Supervisor 按規則路由：

```
Task Type Routing Table
┌──────────────────┬─────────────────┬──────────────────┐
│ 任務類型         │ 負責 Agent      │ 備援 Agent       │
├──────────────────┼─────────────────┼──────────────────┤
│ web_search       │ SearchAgent-1   │ SearchAgent-2    │
│ pdf_extract      │ DocAgent-1      │ DocAgent-2       │
│ code_execution   │ CodeAgent-1     │ CodeAgent-2      │
│ citation_verify  │ FactAgent-1     │ FactAgent-2      │
│ final_synthesis  │ WriterAgent-1   │ WriterAgent-2    │
└──────────────────┴─────────────────┴──────────────────┘
```

**優點：** 可預測、低延遲（不需要協調決策）、易除錯
**缺點：** 負載不均（某類型任務突發時某 Agent 空轉）

### 5.2 動態競標

```
動態任務分配流程

  新任務到達
       │
       ▼
┌──────────────┐
│ 任務公告板   │──▶ 廣播給所有可用 Agent
└──────┬───────┘
       │
       │   Agent 評估自身負載 + 能力匹配度
       │
  ┌────┴────┐
  │  出價   │
  │A1: 0.8s │
  │A2: 1.2s │  ← 預估完成時間（越短越好）
  │A3: 0.6s │
  └────┬────┘
       │
       ▼
  A3 得標（最短預估時間）
       │
       ▼
  執行 + 回報結果
```

**出價函數範例：**
```python
def bid_score(agent, task):
    capacity = 1.0 - agent.current_load    # 0.0–1.0
    skill_match = agent.skill_score(task)  # 0.0–1.0
    estimated_time = task.complexity / agent.speed
    return estimated_time / (capacity * skill_match)
    # 分數越低越有競爭力
```

**靜態 vs 動態比較：**

| 維度 | 靜態分工 | 動態競標 |
|------|---------|---------|
| 分配延遲 | < 1ms | 50–200ms（出價輪） |
| 負載均衡品質 | 中 | 高 |
| 實作複雜度 | 低 | 高 |
| 適應突發流量 | 差 | 佳 |
| 除錯難度 | 低 | 高（非確定性） |

**建議：** POC/MVP 用靜態，Scale 階段混用（靜態路由 + 動態負載均衡）。

---

## 六、衝突解決：資源競爭/目標衝突/優先級仲裁

### 6.1 資源競爭衝突

最常見：兩個 Agent 同時想寫同一個輸出位置。

**解法一：樂觀鎖（Optimistic Locking）**
```python
# 讀取時記錄版本號
doc, version = state.get("report_draft", with_version=True)

# 修改後寫回，帶版本校驗
success = state.set(
    "report_draft",
    updated_doc,
    expected_version=version  # 若版本不符則失敗
)
if not success:
    # 衝突：重新讀取、合併、重試
    retry()
```

**解法二：分段所有權（Partition Ownership）**
- 每個 Agent 只寫自己負責的 section（section_1, section_2…）
- 最終由 Writer Agent 合併，避免直接競爭

### 6.2 目標衝突

Agent A 的子目標與 Agent B 的子目標互相矛盾（如：A 要最小化成本，B 要最大化覆蓋率）。

**解法：目標優先級層級**
```
L1（不可違背）: 安全約束（不輸出有害內容、不超預算）
L2（高優先）: 使用者明確要求
L3（中優先）: 品質指標（精度、完整性）
L4（低優先）: 效率指標（速度、成本）
```

衝突發生時，高層級目標自動覆蓋低層級。若同層衝突，升級至 Supervisor 決策。

### 6.3 優先級仲裁

當多個任務同時競爭有限 Agent 資源時：

```
仲裁矩陣
┌─────────────────┬──────┬────────────┬─────────────┐
│ 任務屬性         │ 分數 │ 範例        │ 處理方式     │
├─────────────────┼──────┼────────────┼─────────────┤
│ 使用者等待中    │  10  │ 即時查詢   │ 搶占式優先   │
│ SLA 剩餘 < 30s  │   8  │ 批次報告   │ 提升佇列位置 │
│ 已重試 > 2 次   │   6  │ 失敗重試   │ 給予新資源   │
│ 背景批次        │   2  │ 夜間統計   │ 填補空閒     │
└─────────────────┴──────┴────────────┴─────────────┘
```

**仲裁規則：** 分數最高者優先取得 Agent 資源，同分者 FIFO。

---

## 七、共識機制：多 Agent 決策的一致性保障

### 7.1 為什麼需要共識？

在以下場景，多個 Agent 必須達成一致才能繼續：

- **分叉決策**：Agent A 說「資料足夠」，Agent B 說「需要更多搜尋」
- **品質閘門**：至少 N 個 Agent 同意報告品質達標才能輸出
- **危險操作確認**：刪除資料、發送通知等不可逆操作

### 7.2 三種共識方法

**方法一：投票（Voting）**
```python
votes = {
    "agent_search": "sufficient",    # 3 票
    "agent_fact": "sufficient",
    "agent_logic": "need_more",      # 1 票
    "agent_quality": "sufficient"
}
decision = majority_vote(votes)  # → "sufficient"（3:1）
```
適用：決策較明確，Agent 能力相近

**方法二：加權投票（Weighted Voting）**
```python
weighted_votes = {
    "agent_domain_expert": ("sufficient", weight=3.0),
    "agent_generalist":    ("need_more",  weight=1.0),
}
# 加權後：sufficient=3.0, need_more=1.0 → sufficient
```
適用：Agent 能力有差異，專家 Agent 應有更大影響力

**方法三：否決機制（Veto）**
某些特定 Agent 具有一票否決權（通常是安全/合規 Agent）：
```python
if safety_agent.verdict == "unsafe":
    return "BLOCKED"  # 無論其他 Agent 如何投票
```
適用：有硬性約束（安全、法律合規）的場景

### 7.3 共識的延遲成本

| 共識方法 | 額外延遲 | 適用決策頻率 |
|---------|---------|------------|
| 無共識（單 Agent 決定） | 0ms | 高頻、低風險 |
| 多數投票（N Agent） | N × 平均延遲 | 中頻 |
| 加權投票 | N × 平均延遲 + 計算 | 低頻、高風險 |
| 人工確認（HITL） | 秒～分鐘 | 極低頻、關鍵決策 |

**實務原則：** 只在以下情況引入多 Agent 共識：(1) 決策不可逆，(2) 單 Agent 錯誤率 > 5%，(3) 有明確的損失函數可衡量一致性的價值。

---

## 八、為什麼選 X 不選 Y

### 決策 1：協調架構選 Supervisor 不選 Peer-to-Peer

```
選擇        選 Supervisor 的理由              不選 P2P 的理由
──────────────────────────────────────────────────────────────
Supervisor  全局任務視圖，分配最優             P2P：協調訊息量 O(N²)
vs P2P      除錯簡單：一個決策節點             P2P：死鎖風險難排查
            DAG 依賴關係容易表達               P2P：需要分散式共識算法
            延遲低（1 hop）                    P2P：N hop 累積延遲高
```

**Flip condition：** Agent 數 > 100，且 Supervisor 成為瓶頸（> 80% CPU）→ 切換到分片 Supervisor 或 P2P。

### 決策 2：訊息佇列選 Redis Streams 不選 RabbitMQ

```
選擇        選 Redis Streams 的理由           不選 RabbitMQ 的理由
──────────────────────────────────────────────────────────────
Redis       已有 Redis，零增量基建成本         RabbitMQ：額外維護一套 MQ
Streams     Consumer Group 支援 N:M 消費      RabbitMQ：設定更複雜
vs RabbitMQ 訊息可按 ID 重播（debug 友善）    RabbitMQ：訊息預設消費後刪除
            延遲 < 5ms（本地 Redis）          Kafka：批次設計，延遲 10–50ms
```

**Flip condition：** 任務量 > 100K/天，需要跨 datacenter 複製 → 換 Kafka。

### 決策 3：共享狀態選樂觀鎖不選悲觀鎖

```
選擇        選樂觀鎖的理由                    不選悲觀鎖的理由
──────────────────────────────────────────────────────────────
樂觀鎖      衝突率低（< 5%）時吞吐高          悲觀鎖：持鎖期間其他 Agent 阻塞
vs 悲觀鎖   不持鎖，Agent 可並行讀取          悲觀鎖：死鎖風險
            Redis SET NX 原生支援             悲觀鎖：鎖服務自身成為瓶頸
            衝突時重試成本低（毫秒級）        悲觀鎖：等待時間不可控
```

**Flip condition：** 衝突率 > 20%（多個 Agent 頻繁競爭同一資源）→ 悲觀鎖或分段所有權。

### 決策 4：任務分配選靜態路由不選動態競標（初期）

```
選擇        選靜態路由的理由                  不選動態競標的理由
──────────────────────────────────────────────────────────────
靜態路由    分配延遲 < 1ms                    競標：50–200ms 出價輪延遲
vs 動態競標 完全可預測，易於除錯              競標：非確定性，難重現 bug
            實作 1 天 vs 1 週                競標：需要出價函數調參
            適合 80% 場景（任務類型穩定）     競標：過度設計
```

**Flip condition：** 不同 Agent 負載差異 > 3x，或任務類型分佈高度不均 → 加入動態負載均衡。

### 決策 5：狀態儲存選 Redis 不選純記憶體

```
選擇        選 Redis 的理由                   不選純記憶體的理由
──────────────────────────────────────────────────────────────
Redis       Agent crash 後狀態可恢復          記憶體：進程死亡即狀態遺失
vs 純記憶體  多個 Agent 實例共享同一狀態       記憶體：水平擴展時狀態不同步
            TTL 自動清理過期任務狀態           記憶體：記憶體洩漏難追蹤
            延遲 1–5ms，遠低於 LLM 呼叫       記憶體：跨機器協調無法實現
```

**Flip condition：** 單機 POC、任務量 < 100/天、無容錯需求 → 純記憶體 dict 即可。

### 決策 6：共識方法選多數投票不選全體一致

```
選擇        選多數投票的理由                  不選全體一致的理由
──────────────────────────────────────────────────────────────
多數投票    一個 Agent 超時不阻塞決策          全體一致：最慢 Agent 決定速度
vs 全體一致  容忍單 Agent 錯誤（噪聲）         全體一致：任一 Agent 異常即卡住
            延遲 = 中位數（非最大值）          全體一致：理論上最優但不實際
            適合 3–7 個 Agent 的決策群組       全體一致：> 5 Agent 時幾乎不可用
```

**Flip condition：** 決策涉及安全/合規，不容許任何錯誤 → 加入否決機制（特定 Agent 一票否決）。

---

## 九、系統效應（單 Agent vs 多 Agent 協調）

| 指標 | 單 Agent | 多 Agent（無協調） | 多 Agent（有協調） |
|------|---------|-----------------|-----------------|
| 並發任務吞吐 | 1 task/s | 5 task/s（不穩定） | 8 task/s（穩定） |
| 平均任務延遲（10 步） | 30s | 15s（部分並行） | 8s（全並行） |
| 任務失敗率 | 8% | 25%（無協調衝突） | 3%（有重試+鎖） |
| LLM token 使用/任務 | 15K | 18K（重複工作） | 12K（分工更精準） |
| 月成本（1K 任務/天） | $450 | $540 | $360 |
| 除錯時間/incident | 30 分鐘 | 2 小時 | 45 分鐘 |
| 水平擴展能力 | 無 | 部分 | 線性 |

**關鍵洞察：** 「多 Agent 無協調」是最差選項——比單 Agent 更貴、更不可靠。協調機制本身帶來的開銷（約 20% token overhead）遠小於它消除的重複工作和衝突損失（節省 33% token）。

**規模臨界點：**
- < 3 個 Agent：用 Supervisor + 靜態路由，不要過度設計
- 3–20 個 Agent：加入訊息佇列 + 樂觀鎖
- > 20 個 Agent：分片 Supervisor + Kafka + 動態負載均衡

---

## 十、面試答題要點

> *「這個研究助理平台我會用分片 Supervisor 架構：按任務 ID hash 分到 3 個 Supervisor，每個 Supervisor 管理約 670 個並發任務（2,000 ÷ 3）。Agent 間通訊用 Redis Streams——因為我們已經有 Redis，且訊息可重播利於除錯；當日任務量超過 100K 才考慮換 Kafka。共享狀態用樂觀鎖：Agent 衝突率預估 < 3%，樂觀鎖在這個場景吞吐比悲觀鎖高 5–8 倍。當兩個 Agent 搶同一份外部資源時，我用分段所有權解決：每個 Agent 只能寫自己分配到的 section，最後由 Writer Agent 做最終合併——這樣根本消除競爭而非解決衝突。品質共識用多數投票（4 票中 3 票通過），但安全檢查 Agent 保有一票否決權。預期延遲從串行 24s（8 步 × 3s）降到 8s，任務失敗率從 8% 降到 3%。」*

---

## 十一、系列導航

← [Phase 15 Part 2：Agent 記憶體與長期狀態管理](/posts/ai-eng-from-scratch-phase15-part2-memory-zh/)

→ [Phase 16 Part 2：多 Agent 系統的可觀測性與除錯](/posts/ai-eng-from-scratch-phase16-part2-observability-zh/)

---

*本文為「AI 工程從零開始」系列 Phase 16 Part 1。完整系列涵蓋從 LLM 基礎、Prompt 工程、RAG、Agent 設計到生產部署的全棧 AI 工程知識。*
