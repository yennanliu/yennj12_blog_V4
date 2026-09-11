---
title: "Mem0 Intro Part 2 — 寫入路徑 — ADD-only 萃取管線與那次自我否定"
date: 2026-09-11T15:00:00+08:00
draft: false
weight: 2
description: "Mem0 原始碼導讀系列第二篇：逐行拆解 _add_to_vector_store() 的八個階段、為什麼 v3 放棄了論文裡的 ADD/UPDATE/DELETE/NOOP 四動作模型、UUID 映射成整數的防幻覺技巧、md5 去重的邊界，以及一次 add() 到底花多少錢。"
categories: ["all", "ai", "engineering"]
tags: ["Mem0", "AI Agent", "Memory", "LLM", "Prompt Engineering", "spaCy", "繁體中文"]
authors: ["yen"]
readTime: "26 min"
---

> *大多數人設計「讓 LLM 自己管理記憶」的方式，是給它一組工具——新增、更新、刪除——然後相信它會做對的事。*
> *真正的答案是：LLM 在「該不該覆蓋一條既有事實」這件事上的判斷力，遠低於你的期待；而它判斷錯的代價是不可逆的——被刪掉的記憶不會回來。*
> *Mem0 自己寫過那個版本，也自己把它拆掉了。*
> *這一篇講的是拆掉的理由，以及換上去的東西。*

---

## 前言

[Part 1](/posts/mem0-intro-part1-architecture-overview-zh/) 建立了地圖，也留下一個伏筆：**Mem0 v3 的萃取管線只有 ADD，沒有 UPDATE 和 DELETE。**

這件事違反直覺。一個記憶系統怎麼可能不支援更新？使用者說「我搬到柏林了」，難道不該把「使用者住在里斯本」改掉嗎？

答案是：**不該——至少不該由萃取階段的那次 LLM 呼叫來決定。** 這一篇解釋為什麼，並逐行拆解取而代之的八階段管線。

本篇的目標：**讀完之後，你能算出一次 `add()` 花了幾次 LLM 呼叫、幾次 embedding、幾次資料庫往返，知道什麼時候該用 `infer=False`，並且明白你必須自己補上哪一塊治理邏輯。**

---

## 一、核心問題：讓 LLM 管記憶會出什麼事

### 1.1 v2 的做法：四動作模型

Mem0 的[原始論文](https://arxiv.org/abs/2504.19413)描述的是一個兩階段管線：

```
階段一：萃取
  對話 ──LLM 呼叫 #1──▶ 候選事實清單
                         ["使用者住在柏林", "使用者喜歡爵士樂"]

階段二：更新（這是問題所在）
  對每個候選事實：
    向量檢索出相似的既有記憶
    ──LLM 呼叫 #2──▶ 從四個工具裡選一個：
        ADD    新增一條
        UPDATE 改寫某條既有記憶
        DELETE 刪掉某條既有記憶
        NOOP   什麼都不做
```

這個設計很優雅，而且在論文的 LOCOMO 評測上表現不錯（相對 OpenAI 的記憶方案有 26% 的 LLM-as-a-Judge 相對提升）。程式碼至今還留在 repo 裡——`DEFAULT_UPDATE_MEMORY_PROMPT` 與 `get_update_memory_messages()` 仍然在 `mem0/configs/prompts.py`，只是主路徑已經不走它們了。

### 1.2 四動作模型的四個壞點

**壞點一：DELETE 是不可逆的，而 LLM 會判斷錯。** 使用者說「我現在不常跑步了」——該刪掉「使用者每週跑 40 公里」嗎？還是該新增一條「使用者減少了跑步頻率」？兩者的差別是：前者永久失去了「他曾經是個跑者」這個資訊。**LLM 在這個選擇上沒有可靠的先驗，而錯誤是靜默且永久的。**

**壞點二：UPDATE 會摧毀時序脈絡。** 把「住在里斯本」改寫成「住在柏林」之後，你再也回答不了「他什麼時候搬的家」——而這正是 LongMemEval 和 BEAM 裡最難的那類問題。

**壞點三：成本與延遲是候選事實數量的線性倍數。** 一次對話萃出 5 條事實，就要 1 + 5 = 6 次 LLM 呼叫。延遲從一秒變成好幾秒。

**壞點四：ID 幻覺。** 要 LLM 說出「更新 `a3f8b2e1-...` 這條」，它有相當的機率編一個不存在的 UUID 出來，或者把兩條的 ID 記混。

### 1.3 v3 的答案：只做 ADD，把治理外移

官方遷移文件把改動總結成一句話：

> **Extraction**: Single-pass ADD-only (one LLM call, no UPDATE/DELETE)

以及一段設計說明：

> The key architectural decision is **ADD-only extraction**. New facts are stored alongside old ones. Nothing is overwritten or deleted. When information changes, both the old and new facts survive. This preserves temporal context and eliminates information loss from premature consolidation.

四個壞點的對應解法：

| v2 的壞點 | v3 的解法 |
|---|---|
| DELETE 不可逆且會判斷錯 | **不給 DELETE 這個選項**。要刪就由應用程式明確呼叫 `delete()` |
| UPDATE 摧毀時序 | **新舊並存**。「里斯本」和「柏林」兩條都在，由檢索階段的時序訊號決定誰排前面 |
| N+1 次 LLM 呼叫 | **一次**。既有記憶與新訊息一起餵進同一個 prompt，只回傳要新增的 |
| ID 幻覺 | **把 UUID 映射成 "0"、"1"、"2"**，LLM 只看得到整數 |

改版的效果，官方數字是 **LoCoMo 71.4 → 91.6、LongMemEval 67.8 → 93.4，同時萃取延遲大約減半**。

**但這不是免費的。** 代價寫在同一份評測文件的 LongMemEval 分項裡：`knowledge_update` 是所有分項中最低的 93.6，官方的解釋是「older facts are preserved rather than overwritten, so semantically similar prior facts can still surface alongside newer ones」。

**翻譯成人話：你會撈到過時的事實。** 這個代價被有意識地接受了，並把解決它的責任推給兩個地方——檢索階段的排序（Part 3），以及 Platform 的背景整合（Part 5）。**如果你用 OSS，這塊是你自己的責任。**

---

## 二、三個演進階段

同一個「寫入記憶」的問題，Mem0 自己走過三代。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 1：v1 —— 存原始訊息，不做萃取               ║
### ╚═══════════════════════════════════════════════════╝

```
messages ──▶ 逐則嵌入 ──▶ 寫進向量庫
             （就是現在的 infer=False 路徑）
```

- **可接受的捷徑**：零 LLM 成本、零延遲、完全無損。
- **成本**：每則訊息一次 embedding（約 $0.00002）。
- **解決了什麼**：跨 session 持久化、語意檢索。
- **還沒解決什麼**：存的是「使用者說的話」而不是「關於使用者的事實」。檢索「飲食限制」撈到的是一整段閒聊，裡面剛好提到過敏——**噪音比訊號多得多**。而且同一件事講十次就存十份。

這條路徑至今仍在，就是 `infer=False`。第六節會講它什麼時候才是對的選擇。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 2：v2 —— 兩階段萃取 + 四動作更新            ║
### ╚═══════════════════════════════════════════════════╝

```
messages ──LLM#1──▶ 候選事實
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    事實 A         事實 B         事實 C
   檢索相似       檢索相似       檢索相似
   ──LLM#2──▶    ──LLM#3──▶    ──LLM#4──▶
   ADD/UPDATE/    ADD/UPDATE/    ADD/UPDATE/
   DELETE/NOOP    DELETE/NOOP    DELETE/NOOP
```

- **新增元件**：`FACT_RETRIEVAL_PROMPT`、`DEFAULT_UPDATE_MEMORY_PROMPT`、相似記憶檢索、以及一個把 LLM 決策映射回實際操作的執行層。
- **成本 delta**：LLM 呼叫從 0 變成 1+N 次。一次 `add()` 從免費變成 $0.005–0.03。
- **延遲 delta**：從毫秒變成 2–5 秒。
- **解決了什麼**：存的終於是乾淨的事實了，檢索品質大幅提升。
- **還沒解決什麼**：1.2 節的四個壞點。而且**它們不是實作 bug，是模型能力的邊界**——換更強的模型只能緩解，不能消除。

### ╔═══════════════════════════════════════════════════╗
### ║  Phase 3：v3 —— 單次 ADD-only + 外部治理           ║
### ╚═══════════════════════════════════════════════════╝

```
  ┌─────────────────────────────────────────────────────────┐
  │  一次 LLM 呼叫，輸入包含四種東西：                       │
  │   · 新訊息（要萃取的對象）                               │
  │   · 對話摘要（使用者的既有輪廓）                         │
  │   · 最近已萃取的記憶（本 session 內去重）                 │
  │   · 既有記憶（跨 session 去重，ID 已映射成整數）          │
  │                                                          │
  │  輸出只有一種東西：要新增的事實清單                       │
  └────────────────────────┬────────────────────────────────┘
                           ▼
              hash 去重 → 批次嵌入 → 批次寫入
                           │
                           ▼
     ┌──────────────────────────────────────────────┐
     │  治理被移到別的地方：                          │
     │  · 檢索階段排序（時序訊號、實體加權）           │
     │  · 應用程式明確呼叫 update() / delete()        │
     │  · Platform 的 Dream（Supersede / Merge）      │
     │  · 你自己的背景整合作業（OSS 必須自己寫）       │
     └──────────────────────────────────────────────┘
```

- **新增元件**：`ADDITIVE_EXTRACTION_PROMPT`（一個近 500 行的巨型提示詞）、UUID→整數映射、md5 去重、批次化的實體連結、以及 SQLite 的 `messages` 滾動視窗。
- **成本 delta**：LLM 呼叫從 1+N 降回 **1 次**。延遲大約減半。
- **複雜度 delta**：寫入端**下降**（少了一整個決策執行層），但**系統整體的複雜度上升**——因為治理責任被推到了外面，而 OSS 沒有提供那個外面。
- **解決了什麼**：不可逆刪除、時序遺失、成本、ID 幻覺。
- **還沒解決什麼**：記憶只增不減。這是**這一代設計明確接受的代價**，也是你在生產環境必須自己補的那一塊。

---

## 三、八個階段：逐行拆解

以下是 `Memory._add_to_vector_store()` 的完整流程（`mem0/memory/main.py`，約第 879 行起）。原始碼裡的註解直接寫著 `# === V3 PHASED BATCH PIPELINE ===`。

```
┌─ Phase 0：情境蒐集 ────────────────────────────────────────────┐
│  session_scope = _build_session_scope(filters)                 │
│  last_messages = self.db.get_last_messages(session_scope,      │
│                                            limit=10)           │
│  parsed_messages = parse_messages(messages)                    │
│                                                                │
│  從 SQLite 的 messages 表撈最近 10 則原始訊息                   │
│  ← 目的：讓 LLM 知道「剛剛講過什麼」，避免重複萃取              │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 1：既有記憶檢索 ────────────────────────────────────────┐
│  search_filters = 只保留 user_id / agent_id / run_id           │
│  query_embedding = embed(parsed_messages, "search")            │
│  existing_results = vector_store.search(top_k=10, ...)         │
│                                                                │
│  ★ 關鍵技巧：UUID → 整數映射                                   │
│  for idx, mem in enumerate(existing_results):                  │
│      uuid_mapping[str(idx)] = mem.id        # 真實 UUID 留在本地│
│      existing_memories.append({"id": str(idx), "text": ...})   │
│                                       ↑ LLM 只看到 "0","1","2" │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 2：LLM 萃取（唯一一次 LLM 呼叫）───────────────────────┐
│  system_prompt = ADDITIVE_EXTRACTION_PROMPT                    │
│  if 只有 agent_id 沒有 user_id:                                │
│      system_prompt += AGENT_CONTEXT_SUFFIX                     │
│                                                                │
│  user_prompt = generate_additive_extraction_prompt(            │
│      existing_memories, new_messages,                          │
│      last_k_messages, custom_instructions)                     │
│                                                                │
│  response = llm.generate_response(                             │
│      ..., response_format={"type": "json_object"})             │
│                                                                │
│  ★ 失敗處理：拋 LLMError，不吞掉                                │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 3：批次嵌入 ────────────────────────────────────────────┐
│  mem_texts = [m["text"] for m in extracted_memories]           │
│  mem_embeddings_list = embed_batch(mem_texts, "add")           │
│  ← 一次網路往返，不是 N 次                                      │
│  ← except: 退回逐條嵌入                                         │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 4+5：CPU 處理 + hash 去重 ─────────────────────────────┐
│  existing_hashes = {既有記憶 payload 裡的 hash}                 │
│  seen_hashes = set()          # 本批內去重                     │
│                                                                │
│  for mem in extracted_memories:                                │
│      mem_hash = md5(text).hexdigest()                          │
│      if 撞既有 or 撞本批: continue                              │
│      text_lemmatized = lemmatize_for_bm25(text)  # 給 BM25 用   │
│      payload = {data, text_lemmatized, hash,                   │
│                 created_at, updated_at, attributed_to, ...}    │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 6：批次持久化 ──────────────────────────────────────────┐
│  vector_store.insert(vectors=[...], ids=[...], payloads=[...]) │
│  ← except: 退回逐條 insert                                      │
│  db.batch_add_history([{event: "ADD", ...}])                   │
│  ← except: 退回逐條 add_history                                 │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 7：批次實體連結（五個子步驟）──────────────────────────┐
│  7a  extract_entities_batch(all_texts)  ← spaCy，非 LLM        │
│      全域去重：同一個實體在多條記憶出現只算一次                  │
│  7b  embed_batch(unique_entity_texts)   ← 一次嵌入所有實體      │
│  7c  entity_store.search_batch(top_k=1) ← 一次查所有實體        │
│  7d  分流：                                                     │
│      精確字面命中 or 語意相似度 ≥ 0.95 → 更新既有實體           │
│         payload["linked_memory_ids"] |= 新的 memory_ids        │
│      否則 → 收集起來準備新增                                    │
│  7e  entity_store.insert(全部新實體)    ← 一次寫入              │
│                                                                │
│  ★ 整段包在 try/except 裡：實體連結失敗不會讓 add() 失敗        │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌─ Phase 8：保存原始訊息 + 回傳 ────────────────────────────────┐
│  db.save_messages(messages, session_scope)                     │
│  ← 給下一次 Phase 0 當情境用                                    │
│  return [{"id": ..., "memory": ..., "event": "ADD"}]           │
│                                    ↑ 永遠是 ADD                │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 UUID→整數映射：一個值得偷學的技巧

```python
# Map UUIDs to integers (anti-hallucination)
existing_memories = []
uuid_mapping = {}
for idx, mem in enumerate(existing_results):
    uuid_mapping[str(idx)] = mem.id
    existing_memories.append({"id": str(idx), "text": mem.payload.get("data", "")})
```

原始碼的註解只有一句 `(anti-hallucination)`，但這個技巧的價值遠超過 Mem0 本身。

**問題**：LLM 對長隨機字串的複製能力很差。要它從 `[{"id": "7f3a9b2e-4c81-4d5a-9e12-8b6f0a3c5d7e", ...}]` 裡挑一個出來原樣回傳，錯字、漏字、混搭兩個 ID 的機率都不低。而在記憶系統裡，一個編出來的 ID 意味著更新到不存在的記憶，或者更糟——更新到別人的記憶。

**解法**：LLM 只在一個 0–9 的命名空間裡工作，真實 UUID 留在本地的 `uuid_mapping` 字典。**模型只要能數到 9 就不會錯。**

**通用原則**：任何時候你要 LLM 引用一組外部識別碼，都應該先把它們映射成一個小而密集的命名空間。這對引用編號、工具 ID、檔案索引都適用。

### 3.2 ADD-only 提示詞裡最重要的三段

`ADDITIVE_EXTRACTION_PROMPT` 有近 500 行。三段值得單獨看：

**第一段：明確界定唯一動作。**

> You are a Memory Extractor — a precise, evidence-bound processor responsible for extracting rich, contextual memories from conversations. **Your sole operation is ADD.**

**第二段：既有記憶只能用來去重，不能拿來萃取。**

> Use these ONLY for deduplication and linking — do NOT extract new memories from Existing Memories. Your extractions must come exclusively from New Messages.

這一句在防一個很實際的失敗模式：LLM 看到既有記憶，把它們當成「上下文」，然後把它們改寫一遍當成新事實輸出——結果就是每次 `add()` 都把記憶庫翻倍。

**第三段：assistant 訊息也要萃取，但要轉換視角。**

> **Assistant messages**: Specific recommendations given, plans or schedules created, information researched, solutions provided, agreements reached
>
> Attribute correctly: use "User" for user-stated facts. For assistant-generated content, frame in terms of the user's context (e.g., "User was recommended X").

這是一個容易被忽略的設計。Agent 說「我幫你訂了週五下午三點的餐廳」是一個**必須記住**的事實，但它不是使用者說的。提示詞同時列了明確的排除清單：不要萃取 assistant 對使用者的模糊描述（「你看起來很有熱情」）、通用的附和（「好問題！」）、以及 assistant 對自己能力的自述。

### 3.3 `attributed_to`：說話者歸屬

```python
if mem.get("attributed_to"):
    mem_metadata["attributed_to"] = mem["attributed_to"]
```

多人對話（群聊）場景下，「誰說的」是關鍵資訊。這個欄位會被 promote 到搜尋結果的頂層（Part 3 會看到 `promoted_payload_keys` 清單），所以你可以直接讀，不用去挖 metadata。

---

## 四、去重：三道防線與它們的漏洞

v3 沒有 UPDATE，所以**去重是唯一能阻止記憶爆炸的機制**。它有三道防線，強度遞減。

```
┌─────────────────────────────────────────────────────────────┐
│ 防線一：LLM 層（語意去重）                                    │
│ 提示詞餵進「既有記憶」與「最近已萃取記憶（最多 20 條）」       │
│ 要求：語意等價且無新增脈絡者，跳過                             │
│                                                              │
│ 強度：能抓語意相近但字面不同的（「愛喝咖啡」vs「每天要喝咖啡」）│
│ 漏洞：只看 top-10 的既有記憶。第 11 條相似的看不到             │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 防線二：跨批 hash（字面去重）                                 │
│ existing_hashes = {既有 top-10 的 md5}                       │
│ 撞到就丟                                                      │
│                                                              │
│ 強度：100% 可靠                                               │
│ 漏洞：md5 是精確比對。差一個標點就不算重複                     │
│       而且同樣只比對 top-10                                   │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 防線三：批內 hash                                             │
│ seen_hashes：同一次 add() 萃出兩條一模一樣的，只留一條         │
│                                                              │
│ 強度：100% 可靠                                               │
│ 漏洞：無（範圍本來就只有這一批）                              │
└─────────────────────────────────────────────────────────────┘
```

**三道防線都繞不過的那個洞**：使用者在三個月內用三十種不同說法表達同一個偏好。每一次的 top-10 檢索都可能沒撈到前一次那條，或者語意接近到 LLM 覺得「有新增脈絡」而放行。**結果是三十條說著同一件事的記憶，互相稀釋檢索排名。**

這不是 bug，是 ADD-only 架構的必然結果。Platform 用 Dream 的 Merge 動作解決，OSS 沒有——所以你必須自己寫，第七節有具體做法。

---

## 五、成本模型：一次 `add()` 花多少錢

把八個階段換算成實際開銷。假設一次 `add()` 傳入 4 則訊息、萃出 3 條記憶、包含 5 個實體。

| 階段 | 操作 | 次數 | 量級 |
|---|---|---|---|
| Phase 0 | SQLite 讀 | 1 | < 1ms |
| Phase 1 | Embedding（對話整段） | 1 | ~30ms、~$0.00002 |
| Phase 1 | 向量庫檢索 | 1 | ~10–50ms |
| **Phase 2** | **LLM 生成** | **1** | **~700–1500ms、$0.002–0.02** |
| Phase 3 | Embedding 批次（3 條） | 1 | ~30ms |
| Phase 6 | 向量庫批次寫入 | 1 | ~10–30ms |
| Phase 6 | SQLite 批次寫入 | 1 | < 5ms |
| Phase 7a | spaCy 實體抽取 | 1 | ~5–20ms、**$0** |
| Phase 7b | Embedding 批次（5 實體） | 1 | ~30ms |
| Phase 7c | 實體庫批次檢索 | 1 | ~10–50ms |
| Phase 7e | 實體庫批次寫入 | 1 | ~10–30ms |
| Phase 8 | SQLite 寫入 | 1 | < 5ms |
| | **合計** | **1 次 LLM + 3 次 embedding + 6 次 DB** | **~1.0–1.8s、$0.002–0.02** |

三個結論：

**結論一：LLM 佔了 80% 的延遲與 99% 的成本。** 所有其他優化都是噪音。要降成本只有三條路：換更便宜的模型、減少 `add()` 的呼叫次數、或對簡單訊息用 `infer=False`。

**結論二：批次化是 v3 的隱形貢獻。** Phase 3、7b、7c、7e 全都是批次操作，而且每個都帶 fallback。如果逐條做，5 個實體就是 5 次嵌入 + 5 次檢索 + 5 次寫入——**網路往返從 3 次變成 15 次**。在雲端向量庫上這是 300ms 的差距。

**結論三：把它移出請求路徑。** 1–1.8 秒擋在使用者面前是不可接受的。官方評測文件描述的正確做法是 "Conversation enters the pipeline asynchronously (after the agent responds)"。

### 5.1 降低 LLM 成本的三個實際手段

```
手段一：不是每一輪都 add()
   ❌ 每次使用者發言都 add()
   ✅ 每 N 輪、或對話結束時、或偵測到「值得記」的訊號時才 add()

   一個實用的過濾器：先用規則或小模型判斷這輪有沒有新資訊
   （長度、是否包含第一人稱陳述、是否包含決定性動詞）
   能砍掉 50–70% 的無效 add()

手段二：萃取用小模型
   萃取是一個結構化抽取任務，不需要最強的模型
   用一個便宜的小模型通常夠用，成本可降一個量級
   ← 但務必用自己的語料比對過萃取品質再換

手段三：對明確的事實用 infer=False
   使用者在表單裡填了「素食主義者」——這不需要 LLM 萃取
   m.add("User is vegetarian", user_id=..., infer=False)
   ← 零 LLM 成本、零延遲、且保證原文不被改寫
```

---

## 六、`infer=False`：什麼時候該繞過萃取

`infer=False` 走的是完全不同的一條路（`_add_to_vector_store()` 開頭的分支）：

```python
if not infer:
    for message_dict in messages:
        if message_dict["role"] == "system":
            continue                          # system 訊息直接跳過
        per_msg_meta["role"] = message_dict["role"]
        if message_dict.get("name"):
            per_msg_meta["actor_id"] = message_dict["name"]
        msg_embeddings = self.embedding_model.embed(msg_content, "add")
        mem_id = self._create_memory(msg_content, {...}, per_msg_meta)
```

**注意它做了什麼、沒做什麼**：

| | `infer=True`（預設） | `infer=False` |
|---|---|---|
| LLM 呼叫 | 1 次 | **0 次** |
| 存的內容 | 萃取出的事實 | **原始訊息逐字** |
| 去重 | 三道防線 | **無** |
| `text_lemmatized` | 有 | **無** → BM25 檢索不到 |
| 實體連結 | 有 | **無** → 實體加權失效 |
| hash | 有 | 由 `_create_memory()` 內部產生 |
| 延遲 | 1–1.8s | ~50ms |
| 事件 | `ADD` | `ADD` |

**第四、五行是最容易被忽略的代價**：用 `infer=False` 存進去的記憶，**只能靠語意向量被檢索到**——三訊號融合退化成單訊號。Part 3 會看到這意味著什麼。

```
選擇             選 infer=True 的理由            選 infer=False 的理由
────────────────────────────────────────────────────────────────────────
infer=True       存的是乾淨的事實，檢索精準       每次 1–1.8s、$0.002–0.02
（預設）          三道去重防線                     LLM 可能改寫或漏掉細節
                 完整的 BM25 + 實體訊號
                 ──────────────────────────────────────────────────────
infer=False      零成本、零延遲、原文無損         沒有去重 → 重複內容堆積
                 保證不被 LLM 改寫                 沒有詞形還原 → BM25 失效
                                                  沒有實體 → 實體加權失效
                 ──────────────────────────────────────────────────────
翻轉條件：
· 內容已經是結構化事實（表單欄位、系統事件、明確的使用者設定）→ infer=False
· 內容是自由對話 → infer=True
· 內容是必須逐字保留的（法規條文、合約條款、使用者的原話引用）→ infer=False
  但要認知它的檢索能力較弱，考慮同時用 infer=True 存一份萃取版
· 你在做批次匯入且已經有乾淨的事實清單 → infer=False，省下大筆 LLM 費用
```

---

## 七、ADD-only 的長期代價，以及你必須自己補的那塊

這一節是本篇最實用的部分。

### 7.1 熵增曲線

```
記憶條數
   ▲
   │                                            ╱ ADD-only（無治理）
   │                                        ╱
   │                                    ╱
   │                                ╱
   │                            ╱
   │                        ╱
   │                    ╱         ┌─────────────── 有背景整合
   │                ╱      ┌──────┘
   │            ╱   ┌──────┘
   │        ╱ ┌─────┘
   │    ╱┌───┘
   │  ╱─┘
   └──────────────────────────────────────────────────▶ 時間
                     ↑
              大約在這裡，檢索品質開始下降：
              · top-k 被同義的舊記憶佔滿
              · 過時的事實與最新的事實分數接近
              · 每次萃取的「既有記憶 top-10」都撈到同一批
```

**症狀怎麼看**：定期抽樣跑一次 `get_all(filters={"user_id": ...})`，看一個活躍使用者累積了多少條。如果某個使用者有 300 條記憶而其中你一眼能看出 50 條在講同一件事，你已經在曲線的右半邊了。

### 7.2 四個補償機制（OSS 要自己寫）

**補償一：週期性合併作業。**

```
每週對每個活躍 user_id：
  1. get_all() 撈出全部記憶
  2. 兩兩算餘弦相似度（或先用向量庫的聚類能力分群）
  3. 相似度 > 0.92 的群組，交給 LLM 合併成一條
  4. update() 寫回代表條，delete() 其餘
  5. 記錄在你自己的稽核表（Mem0 的 history 只記 ADD）
```

**注意第 5 步**：v3 的 `batch_add_history` 只寫 `event: "ADD"`，你的合併操作要自己留痕，否則之後追查「這條記憶哪來的」會斷線。

**補償二：時效標註。** 對會過時的事實（住址、職稱、目前專案），在 metadata 裡寫上 `valid_from`，檢索後在應用層做時序排序：

```python
results = m.search(q, filters={"user_id": u})["results"]
# 同一 topic 的多條，只保留 valid_from 最新的
```

**補償三：善用 `expiration_date`。** OSS 支援這個參數，過期的記憶預設不會出現在 `search()` 與 `get_all()`：

```python
m.add(messages, user_id="u_1", expiration_date="2026-12-31")
```

對「這一季的目標」「這次專案的偏好」這類天生有時效的東西，**在寫入時就標好過期日**，比事後清理便宜得多。

**補償四：明確的 `delete()`。** 當使用者在 UI 上明確說「忘掉這件事」時，直接呼叫 `delete()`。ADD-only 限制的是**萃取階段的自動決策**，不是 API——`update()` 和 `delete()` 都還在，而且由你的應用程式呼叫時，判斷來自使用者的明確意圖而不是 LLM 的猜測。**這正是 v3 想要的分工。**

### 7.3 一個不該做的補償

**不要把 `custom_instructions` 寫成「如果發現矛盾就不要萃取新的」。** 這等於把 UPDATE 的判斷偷渡回 LLM，而且是在一個沒有既有記憶完整視野（只有 top-10）的情況下做的——比 v2 更糟。`custom_instructions` 應該用來調整**萃取什麼**（例如「只記與醫療相關的事實」「忽略閒聊」），不是調整**要不要覆蓋**。

---

## 八、為什麼選 X 不選 Y

```
選擇                選 X 的理由                        不選 Y 的理由 / 翻轉條件
─────────────────────────────────────────────────────────────────────────────
ADD-only            不可逆錯誤消失（沒有 DELETE）      四動作模型：能主動維持
vs ADD/UPDATE/      保留時序脈絡                       記憶庫乾淨，不需要外部
   DELETE/NOOP      1 次 LLM 呼叫而非 1+N              治理
                    LoCoMo 71.4→91.6                   ─────────────────────────
                    ─────────────────────────────────────────────────────────
                    翻轉條件：你的場景記憶量小且高度結構化（例如只記 20 個固定
                    欄位的使用者設定），四動作模型的自動維護反而更省事。但那種
                    場景其實該用一張資料表，不是記憶層。

單次 LLM 呼叫       延遲減半、成本降 N 倍              多次呼叫：每個事實都能
vs 逐事實決策        提示詞能看到全域脈絡               拿到專屬的相似記憶視野
                    ─────────────────────────────────────────────────────────
                    翻轉條件：對話極長（單次 add 要處理 50+ 則訊息）時，單次
                    呼叫的提示詞會撐爆 context。此時該做的是把 add() 切小批，
                    而不是回頭走多次決策。

UUID → 整數映射     消除 ID 幻覺                       直接給 UUID：不需要
vs 直接給 UUID      省 token（UUID 每個約 12 token）    維護映射表
                    ─────────────────────────────────────────────────────────
                    翻轉條件：無。這個技巧沒有缺點，應該推廣到任何要 LLM 引用
                    外部識別碼的場景。

spaCy 抽實體        毫秒級、零成本、可離線             LLM 抽實體：能理解上下文、
vs LLM 抽實體       批次處理效率高（nlp.pipe）          支援任意語言、能抽抽象概念
                    ─────────────────────────────────────────────────────────
                    翻轉條件：非英語語料。`en_core_web_sm` 在中文上幾乎抽不到
                    東西，整條實體訊號會靜默失效。此時要嘛換 spaCy 的中文模型
                    （`zh_core_web_sm`），要嘛接受只有語意訊號，要嘛自己在
                    寫入後補一層 LLM 實體抽取寫進 metadata。

md5 hash 去重       O(1)、100% 可靠、零成本            語意去重：能抓字面不同
vs 純語意去重        不會誤判                           但意思相同的
                    ─────────────────────────────────────────────────────────
                    翻轉條件：兩者不是二選一，Mem0 同時用。真正的問題是兩者
                    都只比對 top-10。要更強的去重，只能靠離線的批次合併作業。

批次操作 + fallback 網路往返從 15 次降到 3 次          逐條操作：錯誤定位精準，
vs 逐條操作          雲端向量庫上省 300ms+              部分失敗不影響其他
                    ─────────────────────────────────────────────────────────
                    翻轉條件：無——Mem0 每個批次操作都帶逐條 fallback，
                    等於同時拿到兩者的好處。這是值得抄的模式。

非同步 add()        使用者不用等 1–1.8 秒              同步 add()：程式碼簡單，
vs 同步 add()       可以用佇列削 LLM rate limit 的峰     寫入完成後立刻可讀
                    ─────────────────────────────────────────────────────────
                    翻轉條件：批次匯入、離線處理、或測試環境——同步更好除錯。
                    線上互動路徑一律非同步。
```

---

## 九、系統效應：v2 → v3 改了什麼

| 環節 | v2（兩階段四動作） | v3（單次 ADD-only） | 效果 |
|---|---|---|---|
| LLM 呼叫次數 | 1 + N（N = 候選事實數） | **1** | 成本降 N 倍，延遲約減半 |
| 可用動作 | ADD / UPDATE / DELETE / NOOP | **只有 ADD** | 消除不可逆的錯誤刪除 |
| 舊事實 | 可能被覆蓋或刪除 | **保留** | 時序脈絡完整 |
| ID 給 LLM 的形式 | UUID | **整數 "0","1","2"** | 消除 ID 幻覺，省 token |
| 既有記憶的用途 | 決定要更新誰 | **僅去重參考** | 提示詞責任變小、更可靠 |
| 嵌入 | 逐條 | **批次 + fallback** | 網路往返大幅減少 |
| 實體連結 | 外部圖資料庫（Neo4j 等） | **內建實體庫 + 批次連結** | 少一個要維運的系統，但失去圖查詢 |
| 去重 | 靠 LLM 判斷 | **LLM + md5 雙層** | 字面重複 100% 擋掉 |
| LLM 失敗 | 靜默回傳空清單 | **拋 `LLMError`** | 呼叫端能分辨「服務掛了」與「沒東西可記」 |
| 記憶總量 | 會被壓縮 | **單調成長** | ← 這是代價，需要外部治理 |
| LoCoMo | 71.4 | **91.6** | |
| LongMemEval | 67.8 | **93.4** | |

最後三行要一起看：**分數大幅提升，但代價是把記憶治理的責任推給了使用者。** 在 Platform 上那個責任由 Dream 承接；在 OSS 上，它是你的。

---

## 十、系列導航

本篇拆解了寫入路徑：八個階段、一次 LLM 呼叫、三道去重防線，以及那個被刻意接受的代價——**記憶只增不減**。

v3 的邏輯是：**與其讓 LLM 在寫入時做不可靠的取捨，不如把所有事實都留著，讓檢索階段決定誰該出現。** 這把壓力全部轉移到了讀取路徑——如果「住在里斯本」和「住在柏林」兩條並存，那麼**檢索必須有能力把後者排前面**。

下一篇就是那個檢索：語意向量、BM25 關鍵字、實體加權三條訊號怎麼算出來、怎麼融合成一個分數、那個會隨啟用訊號變化的自適應分母是什麼、`threshold` 到底在 gate 什麼，以及 `explain=True` 怎麼用來診斷「為什麼那條記憶沒被撈到」。

- **Part 3 — 讀取路徑**：語意 + BM25 + 實體的多訊號融合檢索

← [Part 1 — 全景架構 — 為什麼 Agent 需要一個記憶層而不是更長的上下文](/posts/mem0-intro-part1-architecture-overview-zh/) | [Part 3 — 讀取路徑 — 語意、關鍵字與實體的三訊號融合 →](/posts/mem0-intro-part3-hybrid-retrieval-zh/)

---

*本文基於 mem0 `main` 分支（2026 年 9 月，版本 2.0.20）原始碼撰寫。流程階段、函式名稱與常數皆對照 `mem0/memory/main.py` 的 `_add_to_vector_store()` 與 `mem0/configs/prompts.py`；v2 與 v3 的行為差異對照官方 `docs/migration/oss-v2-to-v3.mdx`。成本與延遲數字為量級估算。*
