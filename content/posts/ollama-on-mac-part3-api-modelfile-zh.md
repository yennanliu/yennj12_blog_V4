---
title: "ollama on mac - part 3 - REST API 與自訂 Modelfile"
date: 2026-07-17T09:00:00+08:00
draft: false
description: "深入 Ollama 的 REST API 與 Modelfile:把 Mac 變成本機 LLM 伺服器,掌握 /api/generate、/api/chat、options 調校、結構化輸出,並用 Modelfile 打造專屬模型。"
categories: ["engineering", "ai", "all"]
tags: ["Ollama", "LLM", "REST API", "Modelfile", "macOS", "AI Engineering", "Local LLM"]
authors: ["yen"]
readTime: "22 min"
---

> 大多數人用 Ollama:打開終端機,`ollama run llama3.2`,聊兩句就關掉。
> 資深工程師用 Ollama:把它當成一台跑在 `localhost:11434` 的本機 LLM 伺服器。
> 前者是玩具,後者是可以接進整個系統的基礎設施。
> 這一篇,我們把那道 HTTP 門推開。

在 [Part 1](../ollama-on-mac-part1-installation-zh/) 我們裝好了 Ollama、跑起第一個模型;[Part 2](../ollama-on-mac-part2-public-models-zh/) 我們把公開模型全覽過一遍、學會怎麼選型。到這裡為止,你都還停留在 `ollama run` 這個「門面」。

但 `ollama run` 只是一個 CLI 包裝,它底下真正在做事的,是一個 HTTP 伺服器。**只要你懂 REST API 與 Modelfile,你就能把 Ollama 從一個聊天玩具,升級成一個可以被任何程式語言呼叫、可以客製 persona、可以輸出結構化 JSON 的本機推論引擎。** 這一篇是整個系列裡最偏「參考手冊」的一篇,建議收藏後隨查隨用。

---

## 一、為什麼 CLI 只是門面

當你輸入 `ollama run llama3.2`,實際發生的事情是:

1. CLI 檢查後台是否有 `ollama serve` 在跑(GUI App 會自動幫你起)。
2. CLI 透過 HTTP 呼叫 `http://localhost:11434/api/chat`。
3. 伺服器把模型載入記憶體、跑推論、把結果串流回 CLI。
4. CLI 只是把串流的文字印在你的終端機上。

換句話說,**你在終端機看到的每一個字,都是先經過一次 HTTP 往返的**。CLI 能做的,你的程式全部都能做,而且能做得更多:控制參數、拿到 token 計數、強制 JSON 輸出、同時對多個模型下指令。

這帶來一個關鍵心態轉換:

> **不要把 Ollama 想成一個「應用程式」,要把它想成一個「服務」。** 就像你不會直接操作 PostgreSQL 的資料檔,而是透過連線埠去查詢一樣——Ollama 的正確用法,是透過 `localhost:11434` 這個埠去呼叫。

---

## 二、Ollama 伺服器架構回顧

Ollama 的核心是一個常駐的 HTTP 伺服器,預設綁在 `127.0.0.1:11434`。所有互動——不管是 CLI、桌面 App、還是你自己寫的 Python/Node 程式——最終都變成對這個埠的 HTTP 請求。

```
                     你的環境                          Ollama Server
┌──────────────────────────────────────┐   ┌───────────────────────────────┐
│                                        │   │                               │
│  ollama run (CLI)  ─┐                  │   │   ┌───────────────────────┐   │
│                     │                  │   │   │  HTTP Router           │   │
│  curl / httpie   ───┤                  │   │   │  /api/generate         │   │
│                     │   HTTP over TCP  │   │   │  /api/chat             │   │
│  Python requests ───┼──────────────────┼──▶│   │  /api/tags /api/ps ... │   │
│                     │  localhost:11434 │   │   └───────────┬───────────┘   │
│  Node fetch      ───┤                  │   │               │               │
│                     │                  │   │               ▼               │
│  桌面 App / Web UI ─┘                  │   │   ┌───────────────────────┐   │
│                                        │   │   │  Model Runtime (llama  │   │
└──────────────────────────────────────┘   │   │  .cpp / GGUF loader)    │   │
                                             │   │  + 記憶體中的模型權重   │   │
        `ollama serve` 啟動這個伺服器        │   └───────────────────────┘   │
        (GUI App 會自動在背景起)             └───────────────────────────────┘
```

**手動啟動伺服器:**

```bash
# 前景啟動(會佔用這個終端機視窗,方便看 log)
ollama serve

# 若已被 GUI App 佔用 11434,會看到:
# Error: listen tcp 127.0.0.1:11434: bind: address already in use
```

**確認伺服器活著:**

```bash
curl http://localhost:11434
# 回應純文字:Ollama is running
```

看到 `Ollama is running` 就代表這台本機 LLM 伺服器已經在待命了。接下來所有的 curl 範例,前提都是這個伺服器有在跑。

---

## 三、/api/generate:單輪補全

`/api/generate` 是最基礎的端點:給一段 prompt,拿一段補全。它**沒有對話歷史概念**,適合單次的、無狀態的任務——摘要、翻譯、分類、產生一段文字。

### 3.1 最小範例(關掉串流)

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2",
  "prompt": "Why is the sky blue?",
  "stream": false
}'
```

回應(為了可讀已格式化):

```json
{
  "model": "llama3.2",
  "created_at": "2026-07-17T01:23:45.678Z",
  "response": "The sky appears blue because of Rayleigh scattering...",
  "done": true,
  "done_reason": "stop",
  "context": [128006, 882, 128007, 271, 10445, ...],
  "total_duration": 4830000000,
  "load_duration": 1120000000,
  "prompt_eval_count": 26,
  "prompt_eval_duration": 340000000,
  "eval_count": 298,
  "eval_duration": 3370000000
}
```

### 3.2 每個回應欄位的意義

| 欄位 | 意義 | 白話 |
|------|------|------|
| `response` | 模型產生的文字 | 你要的答案 |
| `done` | 是否結束 | `stream:true` 時只有最後一塊為 `true` |
| `done_reason` | 結束原因 | `stop`(自然結束)/`length`(達 num_predict) |
| `context` | token id 陣列 | 可回傳給下一次請求以延續上下文(generate 專用) |
| `total_duration` | 總耗時 | 單位是**奈秒 (ns)** |
| `load_duration` | 載入模型耗時 | 模型已在記憶體時會很小 |
| `prompt_eval_count` | 輸入 prompt 的 token 數 | 用來算 input tokens |
| `prompt_eval_duration` | 處理輸入耗時 | prefill 階段 |
| `eval_count` | 產生的 token 數 | 用來算 output tokens |
| `eval_duration` | 產生 token 的耗時 | decode 階段 |

**關鍵重點:所有 `*_duration` 單位都是奈秒 (nanoseconds)。** 換算成秒要除以 10 億。

### 3.3 怎麼算 tokens/sec(每秒吐幾個字)

推論速度是本地 LLM 最重要的效能指標,公式是:

```
生成速度 (tokens/sec) = eval_count / (eval_duration / 1e9)
```

用上面的例子:

```
= 298 / (3,370,000,000 / 1,000,000,000)
= 298 / 3.37
≈ 88.4 tokens/sec
```

**在 M 系列 Mac 上,一個 8B 模型大約落在 30–90 tokens/sec,取決於晶片與量化等級。** 這個數字你可以直接拿來比較不同模型、不同 `options` 設定的效能,不用另外裝工具。同理,`load_duration` 大(例如 1.1 秒)代表這次請求觸發了模型載入——這正是下一節 `keep_alive` 要處理的問題。

### 3.4 stream 預設為 true

**這是最多人踩到的坑:`stream` 的預設值是 `true`。** 如果你不寫 `"stream": false`,你拿到的不是一個 JSON,而是一串以換行分隔的 JSON(JSONL),每一塊是一個小片段:

```json
{"model":"llama3.2","created_at":"...","response":"The","done":false}
{"model":"llama3.2","created_at":"...","response":" sky","done":false}
{"model":"llama3.2","created_at":"...","response":" appears","done":false}
...
{"model":"llama3.2","created_at":"...","response":"","done":true,"total_duration":...,"eval_count":298,...}
```

- **串流模式 (`stream:true`)**:每產生一個 token 就立刻回傳,適合聊天 UI 的「打字機效果」,使用者不必等整段跑完。最後一塊 `done:true` 才帶完整的統計數據。
- **非串流模式 (`stream:false`)**:等整段跑完,一次回傳完整 JSON。適合後端批次處理、你只要最終結果的場景。

**用 curl 測試時建議一律加 `"stream": false`**,否則你會看到滿螢幕的 JSONL 難以閱讀。

---

## 四、/api/chat:多輪對話

`/api/chat` 是 `/api/generate` 的進階版,也是實務上最常用的端點。差別在於它用 **messages 陣列 + roles** 來表達一段對話。

### 4.1 基本範例

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "stream": false
}'
```

回應:

```json
{
  "model": "llama3.2",
  "created_at": "2026-07-17T01:30:00.000Z",
  "message": {
    "role": "assistant",
    "content": "Hello! How can I help you today?"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 890000000,
  "prompt_eval_count": 31,
  "eval_count": 12,
  "eval_duration": 130000000
}
```

注意 chat 的回應把文字放在 `message.content`(而不是 generate 的 `response`),`message` 還可能帶 `thinking`(推理模型的思考過程)與 `tool_calls`(工具呼叫,Part 5 詳談)。

### 4.2 三種 role

| role | 用途 |
|------|------|
| `system` | 設定模型的行為、人格、規則。通常放在第一則。 |
| `user` | 使用者說的話。 |
| `assistant` | 模型過去的回覆。用來維護對話歷史。 |

### 4.3 怎麼維護多輪對話歷史

**Ollama 的 API 是無狀態的(stateless)——伺服器不會記得你上一輪說了什麼。** 維護對話歷史是「你的程式」的責任:每一輪,你都要把「完整的歷史」重新塞進 `messages` 陣列送出去。

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    {"role": "system",    "content": "你是一個台灣的旅遊助理,回答用繁體中文。"},
    {"role": "user",      "content": "推薦台南一日遊"},
    {"role": "assistant", "content": "早上去赤崁樓,中午吃牛肉湯,下午逛神農街..."},
    {"role": "user",      "content": "那晚餐呢?"}
  ],
  "stream": false
}'
```

模型能回答「晚餐」是接續前文,正是因為你把前三則對話一起送了進去。**這也意味著對話越長,`prompt_eval_count` 越大、每次請求越慢、越吃 context window**——這就是為什麼 `num_ctx` 很重要(第五節)。

### 4.4 generate vs chat:何時用哪個

| 情境 | 用哪個 | 原因 |
|------|--------|------|
| 單次摘要 / 翻譯 / 分類 | `/api/generate` | 無需歷史,更輕量 |
| 聊天機器人 / 多輪問答 | `/api/chat` | 天生支援對話歷史 |
| 需要 system prompt 設定人格 | 兩者皆可 | generate 也能透過 Modelfile/直接欄位設 |
| 視覺(圖片輸入) | `/api/chat` | `messages` 裡放 `images` |
| 工具呼叫 (function calling) | `/api/chat` | `tools` 陣列(見 Part 5) |
| 需要延續 raw context token | `/api/generate` | 回傳的 `context` 可再送回 |

**簡單原則:新專案一律用 `/api/chat`。** 它更通用、更貼近其他主流 API(如 OpenAI 的 chat completions),未來要加工具呼叫、視覺都不用改架構。`/api/generate` 留給那些「一問一答、不需要記憶」的純函式型任務。

視覺與工具的預覽——`messages` 支援 `"images": [base64...]` 做圖片理解,以及 `"tools": [...]` 做函式呼叫——完整內容我們留到 [Part 5](../ollama-on-mac-part5-advanced-zh/)。

---

## 五、options 參數調校

`options` 是一個放在 top-level 的物件,`/api/generate` 和 `/api/chat` 都能用。它控制模型「怎麼生成」——創意程度、長度、重複懲罰、上下文大小等。

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "寫一句關於海的詩"}],
  "stream": false,
  "options": {
    "temperature": 0.8,
    "top_p": 0.9,
    "num_ctx": 8192,
    "num_predict": 128,
    "seed": 42
  }
}'
```

### 5.1 參數對照表

| 參數 | 白話解釋 | 範圍 | 建議值 |
|------|----------|------|--------|
| `temperature` | 隨機性/創意。越高越發散,越低越保守 | 0.0–2.0 | 事實任務 0.1–0.3;創作 0.7–1.0 |
| `top_p` | 核採樣。只從累積機率前 p 的 token 挑 | 0.0–1.0 | 0.9(與 temperature 二選一調) |
| `top_k` | 只從機率最高的 k 個 token 挑 | 1–100 | 40 |
| `seed` | 隨機種子。固定後可重現輸出 | 任意整數 | 需可重現時設固定值(如 42) |
| `num_ctx` | 上下文視窗大小(token) | 依模型 | 預設常為 2048/4096;長文拉大 |
| `num_predict` | 最多產生幾個 token | -1 表無限 | 依需求,避免暴衝設個上限 |
| `repeat_penalty` | 重複懲罰。越高越不愛重複字 | 1.0–1.5 | 1.1 |
| `stop` | 停止字串陣列,遇到就停 | 字串陣列 | 依格式設,如 `["\n\n"]` |

### 5.2 幾個實務心法

- **要穩定/事實正確**:`temperature` 壓到 `0.1`~`0.2`,再配 `seed` 固定,輸出幾乎可重現。做測試、做資料抽取時必備。
- **要創意/多樣**:`temperature` 拉到 `0.8`~`1.0`。
- **temperature 與 top_p 通常只調一個**,兩個都動很難預測。
- **輸出停不下來或跑題**:設 `num_predict` 上限,或用 `stop` 卡住格式邊界。

### 5.3 num_ctx 拉大的記憶體代價

`num_ctx` 決定模型「能看多長的上下文」。很多人以為越大越好,直接開到 32K——但**context window 是要花記憶體的**,而且是隨長度增長的 KV cache。

```
記憶體大致構成 ≈ 模型權重 (固定) + KV cache (隨 num_ctx 線性增長)
```

- 一個 8B 模型權重大約 4.7GB(Q4 量化)。
- `num_ctx` 從 4096 拉到 32768(8 倍),KV cache 也大約放大 8 倍,可能多吃好幾 GB。
- 在 16GB 的 Mac 上,盲目拉大 `num_ctx` 很容易觸發記憶體壓力、甚至讓推論慢到不可用。

**原則:num_ctx 設「夠用就好」。** 你的對話/文件實際多長,就設多少(留一點餘裕)。真的要處理長文再拉大,並同時觀察 `ollama ps` 顯示的記憶體佔用(見第八節)。

---

## 六、結構化輸出(強制 JSON)

把 LLM 接進系統時,最頭痛的就是「它回一堆廢話,我還要用正則去挖答案」。Ollama 提供 top-level 的 `format` 欄位來解決這件事。

### 6.1 format: "json" — 強制合法 JSON

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    {"role": "user", "content": "用 JSON 回覆這句話的情緒與信心:今天真是糟透了。欄位:sentiment, confidence"}
  ],
  "format": "json",
  "stream": false
}'
```

回應的 `message.content` 會是一個**保證能被 parse 的 JSON 字串**:

```json
{ "sentiment": "negative", "confidence": 0.94 }
```

**注意:`format:"json"` 只保證「語法合法」,不保證「欄位正確」。** 你仍應在 prompt 裡明確講清楚要哪些欄位。

### 6.2 format 傳 JSON Schema — 約束到指定結構

更強的用法:`format` 直接傳一個 JSON Schema,模型的輸出會被約束到符合這個 schema。

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [
    {"role": "user", "content": "抽取:王小明,32 歲,住在台北,是軟體工程師。"}
  ],
  "format": {
    "type": "object",
    "properties": {
      "name":       { "type": "string" },
      "age":        { "type": "integer" },
      "city":       { "type": "string" },
      "occupation": { "type": "string" }
    },
    "required": ["name", "age", "city", "occupation"]
  },
  "stream": false
}'
```

回應:

```json
{ "name": "王小明", "age": 32, "city": "台北", "occupation": "軟體工程師" }
```

### 6.3 實用場景

- **欄位抽取**:把自由文字(履歷、發票、客服對話)轉成結構化資料。
- **分類**:強制模型只回 `{"category": "..."}`,再配一個 `enum` schema 限制類別集合。
- **給 seed + temperature 0**:結構化輸出時把 `temperature` 設 `0`、加 `seed`,可讓抽取結果高度穩定,方便寫測試。

> **這是把本地 LLM 產品化的關鍵一步。** 有了 schema 約束,LLM 的輸出從「一段自然語言」變成「一個可靠的 API 回應」,下游程式可以直接 `json.loads()` 使用,不必再寫脆弱的字串解析。

---

## 七、其他管理端點

除了推論,Ollama 還有一整組管理端點,對應你熟悉的 CLI 指令。這對「用程式管理模型」很有用(例如部署時自動 pull 模型)。

### 7.1 端點 ↔ CLI 對照表

| HTTP 端點 | 方法 | 對應 CLI | 功能 |
|-----------|------|----------|------|
| `/api/tags` | GET | `ollama list` | 列出本機已下載的模型 |
| `/api/ps` | GET | `ollama ps` | 列出目前載入記憶體中的模型 |
| `/api/show` | POST | `ollama show` | 看模型的參數、template、modelfile、能力 |
| `/api/pull` | POST | `ollama pull` | 下載模型(串流進度) |
| `/api/delete` | DELETE | `ollama rm` | 刪除本機模型 |
| `/api/create` | POST | `ollama create` | 從 Modelfile 建立模型 |
| `/api/generate` | POST | (run 底層) | 單輪補全 |
| `/api/chat` | POST | `ollama run` | 多輪對話 |
| `/api/embed` | POST | — | 產生 embeddings(見 Part 4) |

### 7.2 各端點 curl 範例

**列出本機模型:**

```bash
curl http://localhost:11434/api/tags
```

```json
{
  "models": [
    {
      "name": "llama3.2:latest",
      "size": 2019393189,
      "digest": "a80c4f17acd5...",
      "details": { "parameter_size": "3.2B", "quantization_level": "Q4_K_M" }
    }
  ]
}
```

**看目前載入記憶體的模型(含到期時間):**

```bash
curl http://localhost:11434/api/ps
```

```json
{
  "models": [
    {
      "name": "llama3.2:latest",
      "size_vram": 3271557120,
      "expires_at": "2026-07-17T01:40:00.000Z"
    }
  ]
}
```

**看模型細節:**

```bash
curl http://localhost:11434/api/show -d '{"model": "llama3.2"}'
# 回傳 parameters / template / modelfile / capabilities(如是否支援 vision/tools)
```

**下載模型(會串流進度):**

```bash
curl http://localhost:11434/api/pull -d '{"model": "qwen2.5:7b"}'
```

```json
{"status":"pulling manifest"}
{"status":"downloading","digest":"sha256:...","total":4700000000,"completed":1200000000}
{"status":"success"}
```

**刪除模型:**

```bash
curl -X DELETE http://localhost:11434/api/delete -d '{"model": "qwen2.5:7b"}'
```

---

## 八、keep_alive 與記憶體管理

這是本地 LLM 效能的隱藏關鍵。**模型第一次被呼叫時,要從硬碟載入記憶體(可能好幾秒);之後每次請求都很快;但閒置一段時間後,Ollama 會把它卸載以釋放記憶體。** `keep_alive` 就是控制「閒置多久才卸載」。

### 8.1 keep_alive 的三種值

`keep_alive` 是一個 top-level 欄位:

| 值 | 意義 | 適用場景 |
|------|------|----------|
| `"5m"`(預設) | 閒置 5 分鐘後卸載 | 一般互動使用 |
| `"0"` | 用完立刻卸載 | 記憶體極吃緊、跑完一次就好 |
| `"-1"` | 永遠不卸載 | 常駐服務、要求低延遲 |
| `"10m"` / `"1h"` | 自訂時間 | 依你的流量調 |

```bash
# 這次請求後保留 30 分鐘
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "hi"}],
  "keep_alive": "30m",
  "stream": false
}'

# 只想預熱(載入模型但不生成):送空 prompt
curl http://localhost:11434/api/generate -d '{"model": "llama3.2", "keep_alive": "-1"}'

# 立刻卸載,釋放記憶體
curl http://localhost:11434/api/generate -d '{"model": "llama3.2", "keep_alive": "0"}'
```

### 8.2 載入 → 快取 → 卸載 時間線

```
時間軸 ──────────────────────────────────────────────────────────────▶

  T0            T1                      T2                  T3         T4
  │             │                       │                   │          │
  ▼             ▼                       ▼                   ▼          ▼
┌──────────┐ ┌──────────┐          ┌──────────┐        (閒置...)   ┌────────┐
│ 首次請求  │ │ 第二次    │  ......  │ 第 N 次   │  ─ 5 分鐘無請求 ─▶│ 卸載   │
│ 需 load  │ │ 已快取    │          │ 已快取    │                    │ 釋放RAM│
│ ~3s 才回 │ │ ~0.1s 回 │          │ ~0.1s 回 │                    └────────┘
└──────────┘ └──────────┘          └──────────┘                         │
   慢!          快                     快                    下一次請求 ─┘
(load_duration                                              又要重新 load(慢)
  很大)
```

**實務建議:**

- **開發時**:預設 `5m` 就好。
- **常駐 API 服務**:把 `OLLAMA_KEEP_ALIVE=-1`(或每次請求帶 `keep_alive:"-1"`),避免使用者遇到「第一個請求特別慢」。代價是模型一直佔著記憶體。
- **記憶體吃緊(16GB Mac 想同時開別的東西)**:縮短到 `"1m"` 或跑完設 `"0"`。
- **多模型輪流用**:配合 `OLLAMA_MAX_LOADED_MODELS`(第九節)控制同時載入幾個。

用 `ollama ps` / `/api/ps` 隨時可以看目前有哪些模型佔著記憶體、還有多久到期。

---

## 九、用 Modelfile 客製模型

REST API 讓你「呼叫」模型;**Modelfile 讓你「打造」模型**。它的語法像 Dockerfile,你用一個基底模型加上系統提示、參數、few-shot 範例,就能 `ollama create` 出一個帶有固定人格與設定的新模型,之後直接 `ollama run 你的模型名` 即可,不必每次都在請求裡塞一堆 options 和 system prompt。

### 9.1 Modelfile 指令對照表

| 指令 | 必要 | 作用 |
|------|------|------|
| `FROM` | ✅ | 指定基底模型(模型名、GGUF 檔路徑、或 Safetensors 目錄) |
| `SYSTEM` | | 內建的系統提示(人格/規則) |
| `PARAMETER` | | 設定預設參數(對應 options),如 temperature、num_ctx、stop |
| `TEMPLATE` | | 自訂 prompt 模板(Go template 語法) |
| `MESSAGE` | | 內建 few-shot 範例對話(user/assistant) |
| `ADAPTER` | | 掛上 LoRA adapter(支援 Llama/Mistral/Gemma/Phi3) |
| `LICENSE` | | 標註授權條款 |

### 9.2 範例一:台灣繁體、簡潔、固定 persona 助理

建立一個檔案 `Modelfile`(無副檔名):

```dockerfile
FROM llama3.2

# 系統提示:固定人格與規則
SYSTEM """
你是「小幫手」,一位專業、友善的台灣本地技術助理。
規則:
1. 一律使用台灣繁體中文與台灣慣用語回答。
2. 回答務求簡潔,先給結論,再給最多三點說明。
3. 不確定時直接說「我不確定」,不要編造。
"""

# 預設參數
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
```

**建立並執行:**

```bash
# 從 Modelfile 建立新模型,命名為 tw-helper
ollama create tw-helper -f ./Modelfile

# 直接使用
ollama run tw-helper "什麼是 REST API?"
```

因為 persona 與參數已經烤進模型,呼叫 API 時你只要:

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "tw-helper",
  "messages": [{"role": "user", "content": "什麼是 REST API?"}],
  "stream": false
}'
```

**驗證烤進去的設定:**

```bash
ollama show --modelfile tw-helper
```

會印出完整的 Modelfile 內容(包含它從 `llama3.2` 繼承來的預設 TEMPLATE),你可以確認 SYSTEM 與 PARAMETER 都正確寫入了。

### 9.3 範例二:長 context + few-shot 範例

假設你要做一個「把中文口語轉成正式書面語」的模型,而且輸入可能很長。用 `MESSAGE` 給 few-shot 教它格式,用 `num_ctx` 拉大上下文:

```dockerfile
FROM qwen2.5:7b

SYSTEM "你是一個中文潤稿助理,把使用者輸入的口語句子改寫成正式的書面繁體中文,只回改寫結果,不要多餘說明。"

PARAMETER temperature 0.2
PARAMETER num_ctx 8192
PARAMETER stop "<|im_end|>"

# few-shot:教它輸入輸出的格式
MESSAGE user "這東西超難用的啦,根本沒人會想碰"
MESSAGE assistant "此產品的使用體驗欠佳,難以吸引使用者採用。"
MESSAGE user "我覺得這個計畫應該不會成功吧大概"
MESSAGE assistant "本人推測此計畫成功的可能性偏低。"
```

```bash
ollama create formalizer -f ./Modelfile
ollama run formalizer "拜託幫我看一下這段碼哪裡爛掉了"
# → 期望輸出類似:懇請協助檢視此段程式碼的問題所在。
```

**MESSAGE 的威力**在於:few-shot 範例被烤進模型後,每次呼叫都自帶示範,輸出格式會非常穩定,而且不佔用你請求時的 messages 空間。

### 9.4 ADAPTER 與 LICENSE

- **`ADAPTER <path>`**:如果你自己用 LoRA 微調過(Llama/Mistral/Gemma/Phi3),可以用 `ADAPTER ./my-lora` 把 adapter 掛到基底模型上,不用合併整包權重。
- **`LICENSE "..."`**:標註你這個客製模型的授權條款,分享時清楚交代。

```dockerfile
FROM llama3.2
ADAPTER ./adapters/my-finetune
LICENSE "Apache-2.0"
```

---

## 十、環境變數設定

前面講的 `keep_alive`、`num_ctx` 都是「單次請求」層級。要調整整台伺服器的行為,靠的是**環境變數**。這些變數是設給「伺服器 (`ollama serve`)」的,不是設給 CLI。

### 10.1 環境變數對照表

| 環境變數 | 作用 | 範例值 |
|----------|------|--------|
| `OLLAMA_HOST` | 伺服器綁定的位址與埠 | `0.0.0.0:11434`(對 LAN 開放)/ 預設 `127.0.0.1:11434` |
| `OLLAMA_MODELS` | 模型儲存目錄 | `/Volumes/SSD/ollama-models`(預設 `~/.ollama/models`) |
| `OLLAMA_KEEP_ALIVE` | 預設 keep-alive 時間 | `"10m"` / `"-1"` |
| `OLLAMA_NUM_PARALLEL` | 每個模型可同時處理幾個請求 | `4` |
| `OLLAMA_MAX_LOADED_MODELS` | 同時最多載入幾個模型 | `2` |
| `OLLAMA_FLASH_ATTENTION` | 開啟 flash attention(省記憶體/加速) | `1` |
| `OLLAMA_CONTEXT_LENGTH` | 預設 context window 大小 | `8192` |
| `OLLAMA_DEBUG` | 詳細除錯日誌 | `1` |

### 10.2 在 macOS 怎麼設

**方法 A:桌面 GUI App(用 launchctl)**

Mac 的 GUI App 是被 launchd 管理的,要用 `launchctl setenv` 設定,然後**重啟 App** 才會生效:

```bash
# 把模型改存到外接 SSD
launchctl setenv OLLAMA_MODELS "/Volumes/SSD/ollama-models"

# 讓模型常駐不卸載
launchctl setenv OLLAMA_KEEP_ALIVE "-1"

# 設完後:完全結束 Ollama App,再重新打開
```

**方法 B:手動跑 `ollama serve`(用 export)**

如果你自己用終端機啟動伺服器,直接在同一個 shell export 即可:

```bash
export OLLAMA_HOST=0.0.0.0:11434
export OLLAMA_KEEP_ALIVE=-1
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_FLASH_ATTENTION=1
ollama serve
```

### 10.3 常見用途

- **搬移模型儲存位置**:內建硬碟快滿了?設 `OLLAMA_MODELS` 到外接 SSD,把幾十 GB 的模型移出去。
- **對區網開放**:設 `OLLAMA_HOST=0.0.0.0:11434`,同一個 Wi-Fi 下的其他裝置就能用 `http://你的Mac-IP:11434` 呼叫。適合團隊共用一台 Mac Studio 當推論機。
- **提升吞吐**:`OLLAMA_NUM_PARALLEL` 讓單一模型能同時服務多個請求;`OLLAMA_MAX_LOADED_MODELS` 讓你同時載入多個不同模型(記憶體要夠)。
- **省記憶體/加速**:`OLLAMA_FLASH_ATTENTION=1` 在支援的模型上能降低 KV cache 記憶體、加快長 context 推論。

### 10.4 安全提醒

> **⚠️ `OLLAMA_HOST=0.0.0.0` 會把你的 Ollama 伺服器對整個網路開放,而 Ollama 沒有內建任何身分驗證(no auth)。** 任何能連到這個埠的人都能用你的模型、甚至刪除你的模型。**絕對不要**直接把 `0.0.0.0:11434` 暴露到公網。要跨網路使用,請放在反向代理(如 Nginx + 驗證)或 SSH 通道後面。這個主題我們在 [Part 5](../ollama-on-mac-part5-advanced-zh/) 的「多模型服務與進階實踐」會完整處理。

---

## 十一、小結與下一篇預告

這一篇我們把 Ollama 從「CLI 玩具」升級成「本機 LLM 伺服器」:

- **REST API 是核心**:一切都是對 `localhost:11434` 的 HTTP 請求。`/api/generate` 做單輪、`/api/chat` 做多輪(新專案優先用 chat)。
- **看懂回應數據**:`*_duration` 是奈秒,`eval_count / eval_duration` 可算出 tokens/sec;`stream` 預設是 `true`,curl 測試記得關掉。
- **options 調校**:temperature/top_p 控創意、num_predict/stop 控長度、`num_ctx` 拉大要付記憶體代價。
- **結構化輸出**:`format:"json"` 保證合法 JSON,傳 JSON Schema 更能約束結構——這是產品化的關鍵。
- **keep_alive 管理延遲與記憶體**:`-1` 常駐低延遲、`0` 立即釋放、`5m` 折衷。
- **Modelfile 打造專屬模型**:`FROM` + `SYSTEM` + `PARAMETER` + `MESSAGE`,把 persona 與參數烤進模型。
- **環境變數調伺服器**:改儲存位置、開 LAN、調 keep-alive/並行,並牢記 `0.0.0.0` 無驗證的風險。

現在你手上有一台可程式化呼叫、可客製、可輸出結構化資料的本機 LLM 伺服器。**[Part 4 — 與應用整合](../ollama-on-mac-part4-app-integration-zh/)** 就要把這些 API 接進真實應用:Python(含 OpenAI 相容介面)、Node.js、串接 LangChain,以及用 `/api/embed` 做 embeddings 與簡易 RAG。門已經推開,接下來我們走進去蓋東西。

---

## 系列導覽

- [Part 1 — 安裝與第一個本地模型](../ollama-on-mac-part1-installation-zh/)
- [Part 2 — 公開模型全覽與選型指南](../ollama-on-mac-part2-public-models-zh/)
- **Part 3 — REST API 與自訂 Modelfile(本篇)**
- [Part 4 — 與應用整合](../ollama-on-mac-part4-app-integration-zh/)
- [Part 5 — 工具呼叫、多模型服務與進階實踐](../ollama-on-mac-part5-advanced-zh/)

## 參考連結

- [Ollama API 文件](https://docs.ollama.com/api)
- [Ollama Chat API](https://docs.ollama.com/api/chat)
- [Ollama Modelfile 文件](https://docs.ollama.com/modelfile)
- [Ollama 官方文件首頁](https://docs.ollama.com/)
