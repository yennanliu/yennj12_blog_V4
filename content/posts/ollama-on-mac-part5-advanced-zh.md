---
title: "ollama on mac - part 5 - 工具呼叫、多模型服務與進階實踐"
date: 2026-07-19T09:00:00+08:00
draft: false
description: "從會跑模型到蓋 agent、上生產：Ollama 工具呼叫與 function calling、多模態 vision、reasoning 推理模型、Apple Silicon 效能調校、多模型並行服務、遠端存取安全與生產實務全攻略。"
categories: ["engineering", "ai", "all"]
tags: ["Ollama", "LLM", "Tool Calling", "Agent", "Function Calling", "Performance", "Metal", "macOS", "AI Engineering"]
authors: ["yen"]
readTime: "24 min"
---

> 大多數人裝完 Ollama，跑幾句 `ollama run llama3`，覺得「喔，本地也能聊天」，就把它當成離線玩具。
> 少數人會把它接進 App、串 API，當成一個省錢的雲端替代品。
> 但真正把 Ollama 用透的人，會把它當成一個**能跑 agent、能看圖、能推理、能上生產的本地 LLM 平台**。
> 這篇是全系列的最後一塊拼圖：把前四篇的能力組合起來，蓋出真正能用的東西。

---

## 一、從「會跑模型」到「用模型蓋東西」

前面四篇，我們一路走過：

- **Part 1**：把 Ollama 裝起來，跑出第一個本地模型。
- **Part 2**：認識公開模型生態，學會依任務與硬體選型（量化、參數量）。
- **Part 3**：用 REST API 與自訂 Modelfile 把模型變成可程式化的服務。
- **Part 4**：把 Ollama 接進真實應用（chatbot、RAG、streaming）。

到這裡，你已經會「呼叫模型」了。但**呼叫模型只是起點**。真正有價值的系統，是讓模型能：

1. **主動使用工具**（查天氣、查資料庫、算數）——這是 agent 的核心。
2. **看得懂圖片**（截圖、發票、手寫）——多模態。
3. **會多步推理**（數學、規劃、除錯）——reasoning 模型。
4. **跑得夠快、記憶體不爆**——效能調校。
5. **同時服務多個模型與請求**——並行架構。
6. **安全地被遠端存取**——這一點做錯會出大事。
7. **穩定地待在生產環境**——監控、版本、磁碟、log。

本篇就把這七件事一次講清楚。這是全系列最長、最「工程」的一篇，建議搭配一台 Apple Silicon 的 Mac 邊讀邊試。

**核心心態轉換**：前四篇你是「模型的使用者」；這一篇開始，你是「本地 LLM 系統的架構師」。

---

## 二、工具呼叫 / Function Calling：讓模型會用工具

### 2.1 最重要的觀念：模型不執行工具

新手最大的誤解，是以為「function calling」代表模型會自己去查天氣、自己去跑資料庫。**不是。**

模型能做的只有一件事：**根據對話，決定「現在應該呼叫哪個工具、帶什麼參數」，然後把這個決定用結構化 JSON 吐出來。** 真正去執行工具的是**你的程式**。執行完，你再把結果餵回去，模型才根據結果產生最終回答。

```
┌──────────────────────────────────────────────────────────────┐
│                    Tool Calling 迴圈                            │
└──────────────────────────────────────────────────────────────┘

   使用者問題
      │
      ▼
 ┌─────────┐   「我需要 get_temperature('台北')」
 │  Model  │──────────────────────────────┐
 └─────────┘                              ▼
      ▲                          ┌──────────────────┐
      │                          │  你的程式         │
      │  role:"tool" 把結果餵回   │  真正執行工具     │
      │  content:"30°C"          │  (查 API/DB/算數) │
      └──────────────────────────└──────────────────┘
      │
      ▼
 ┌─────────┐
 │  Model  │──▶ 「台北目前 30°C，比東京的 18°C 高。」
 └─────────┘        (沒有再要求工具 → 迴圈結束)
```

**關鍵**：模型不執行、不上網、不碰你的資料庫。它只負責「決策」，執行權永遠在你手上——這也正是安全性的來源。

### 2.2 哪些模型支援 tool calling？

不是每個模型都會回 `tool_calls`。訓練時有針對 function calling 微調過的才可靠：

| 模型 | Tool Calling | 參數量 | 備註 |
|------|:---:|------|------|
| `qwen3` | ✅ 佳 | 0.6B–235B | 本篇範例主力，中文好、工具呼叫穩 |
| `llama3.1` / `llama3.3` | ✅ 佳 | 8B / 70B | Meta 官方支援 tools，生態成熟 |
| `mistral` / `mistral-nemo` | ✅ 佳 | 7B / 12B | 歐系，工具呼叫可靠 |
| `qwen2.5` | ✅ 佳 | 0.5B–72B | 上一代，仍廣泛使用 |
| `llama3.2` | ✅ 可 | 1B / 3B | 小模型，工具呼叫較不穩 |
| `gemma3` | ⚠️ 部分 | 1B–27B | 依版本，建議實測 |
| `phi3` | ⚠️ 有限 | 3.8B | 小模型，複雜工具易出錯 |

**經驗法則**：**工具呼叫的可靠度和模型大小正相關**。7–8B 以上才建議用在正式 agent；1–3B 的小模型偶爾會亂帶參數、忘記呼叫，或呼叫了不存在的工具。

### 2.3 Python SDK：直接把函式丟進去

Ollama 的 Python SDK 有個很方便的特性：**你可以直接把 Python 函式當工具傳進去，SDK 會自動從函式簽名與 docstring 產生 JSON schema**。你完全不用手寫 schema。

```python
from ollama import chat

def get_temperature(city: str) -> str:
    """Get the current temperature for a city
    Args:
        city: The name of the city
    """
    return {'Taipei': '30°C', 'Tokyo': '18°C'}.get(city, 'Unknown')

messages = [{'role': 'user', 'content': '溫度:台北跟東京?'}]

# 第一次呼叫：模型決定要用哪個工具
response = chat(model='qwen3', messages=messages, tools=[get_temperature])
messages.append(response.message)

# 檢查模型有沒有要求呼叫工具
if response.message.tool_calls:
    for call in response.message.tool_calls:
        if call.function.name == 'get_temperature':
            # 你的程式真正執行工具
            result = get_temperature(**call.function.arguments)
            # 把結果用 role:"tool" 餵回去
            messages.append({
                'role': 'tool',
                'tool_name': call.function.name,
                'content': str(result),
            })
    # 第二次呼叫：模型根據工具結果產生最終答案
    final = chat(model='qwen3', messages=messages, tools=[get_temperature])
    print(final.message.content)
```

**流程拆解**（背下來，這是所有 agent 的骨架）：

1. 準備 messages + tools，呼叫 `chat`。
2. 模型回 `response.message.tool_calls`（可能有多個）。
3. **把 `response.message` 原封不動 append 回 messages**（這步常被忘，忘了模型就失憶）。
4. 逐一執行每個 tool call，把結果以 `role:"tool"` append。
5. 再呼叫一次 `chat`，模型產生最終文字答案。

> **重點**：`call.function.arguments` 已經是 dict，可以直接 `**` 解包給函式；不需要 `json.loads`。

### 2.4 原始 REST API 的 tools JSON 格式

不用 SDK、想用任何語言（curl、Go、Node）時，就得自己組 tools 的 JSON schema：

```json
{
  "model": "qwen3",
  "messages": [
    {"role": "user", "content": "溫度:台北跟東京?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_temperature",
        "description": "Get the current temperature for a city",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "The name of the city"
            }
          },
          "required": ["city"]
        }
      }
    }
  ]
}
```

模型的回覆會在 `message.tool_calls` 帶回結構化決策：

```json
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "function": {
          "name": "get_temperature",
          "arguments": {"city": "Taipei"}
        }
      }
    ]
  }
}
```

你的後續請求要把工具結果以 `role:"tool"` 加進 messages 陣列，再送一次：

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3",
  "messages": [
    {"role": "user", "content": "溫度:台北跟東京?"},
    {"role": "assistant", "content": "", "tool_calls": [
      {"function": {"name": "get_temperature", "arguments": {"city": "Taipei"}}}
    ]},
    {"role": "tool", "tool_name": "get_temperature", "content": "30°C"}
  ],
  "tools": [ ... ],
  "stream": false
}'
```

**SDK 的自動 schema vs 手寫 JSON**：SDK 方便但只限 Python；手寫 JSON 通用於所有語言，且能精確控制 description（description 寫得好，模型呼叫得準——這是最容易被低估的 prompt 工程）。

### 2.5 多工具、多輪：agent loop 的雛形

真實場景通常一次給模型多個工具，而且模型可能需要**連續呼叫多次**（先查 A，根據 A 的結果再查 B）。這時 2.3 的 if 判斷就不夠了，要包成 while 迴圈——這就是下一節的 agent。

---

## 三、打造一個小 Agent：工具呼叫的 while 迴圈

Agent 的定義其實很樸素：**「反覆讓模型呼叫工具，直到它不再要求工具、給出最終答案為止」**。把 2.3 的一次性判斷改成 while 迴圈即可。

```python
from ollama import chat

def get_temperature(city: str) -> str:
    """Get the current temperature for a city
    Args:
        city: The name of the city
    """
    return {'Taipei': '30°C', 'Tokyo': '18°C', 'New York': '5°C'}.get(city, 'Unknown')

def calculate(expression: str) -> str:
    """Evaluate a simple arithmetic expression
    Args:
        expression: A math expression like '30 - 18'
    """
    try:
        # 正式環境請勿直接 eval 使用者輸入；這裡僅為示範
        return str(eval(expression, {'__builtins__': {}}, {}))
    except Exception as e:
        return f'Error: {e}'

TOOLS = [get_temperature, calculate]
TOOL_MAP = {'get_temperature': get_temperature, 'calculate': calculate}

def run_agent(user_input: str, model: str = 'qwen3', max_steps: int = 6):
    messages = [{'role': 'user', 'content': user_input}]

    for step in range(max_steps):
        response = chat(model=model, messages=messages, tools=TOOLS)
        messages.append(response.message)

        # 沒有工具呼叫 → 模型給了最終答案，結束迴圈
        if not response.message.tool_calls:
            return response.message.content

        # 有工具呼叫 → 逐一執行，把結果餵回
        for call in response.message.tool_calls:
            fn = TOOL_MAP.get(call.function.name)
            if fn is None:
                result = f'Error: unknown tool {call.function.name}'
            else:
                result = fn(**call.function.arguments)
            print(f'  [step {step}] 呼叫 {call.function.name}({call.function.arguments}) -> {result}')
            messages.append({
                'role': 'tool',
                'tool_name': call.function.name,
                'content': str(result),
            })

    return '（達到最大步數上限，agent 停止）'

print(run_agent('台北比紐約熱幾度？'))
```

執行時你會看到類似：

```
  [step 0] 呼叫 get_temperature({'city': 'Taipei'}) -> 30°C
  [step 0] 呼叫 get_temperature({'city': 'New York'}) -> 5°C
  [step 1] 呼叫 calculate({'expression': '30 - 5'}) -> 25
台北目前約 30°C，紐約約 5°C，台北比紐約熱 25 度。
```

模型自己規劃了：先查兩地溫度 → 再算差值 → 給答案。這就是一個能運作的本地 agent。

### 3.1 `max_steps` 是安全帶，不是裝飾

**一定要設 `max_steps`**。小模型偶爾會陷入「一直呼叫工具、永遠不收尾」的迴圈，沒有上限就是無窮迴圈燒 CPU。生產環境我通常設 6–10 步。

### 3.2 本地 Agent 的優勢與限制

| 面向 | 本地 Agent（Ollama） | 雲端 API Agent |
|------|------|------|
| **隱私** | ✅ 資料不出機器，適合敏感資料 | ⚠️ 資料送到第三方 |
| **成本** | ✅ 跑再多次都免費 | ❌ 每次呼叫都計費，agent 迴圈成本疊加快 |
| **延遲** | ✅ 無網路往返 | 依網路而定 |
| **工具呼叫可靠度** | ⚠️ 小模型較弱，需 7B+ | ✅ 前沿模型很穩 |
| **複雜推理** | ⚠️ 受本地模型能力限制 | ✅ 更強 |

**結論**：本地 agent 特別適合「工具呼叫邏輯明確、要處理敏感資料、會頻繁呼叫」的場景（例如內部知識庫、本機檔案操作）。若任務需要極強推理，用小模型做路由、必要時再轉大模型或雲端（見第七節與第九節）。

---

## 四、多模態 Vision：讓模型看得懂圖片

Ollama 支援多個能「看圖」的視覺模型。常見選擇：

| 模型 | 特色 | 記憶體需求 |
|------|------|------|
| `llava` | 老牌 vision 模型，通用看圖問答 | 中 |
| `llama3.2-vision` | Meta 官方，11B / 90B，品質好 | 高（11B 約需 8GB+） |
| `qwen2.5-vl` | Qwen 視覺版，OCR、中文表現佳 | 中–高 |

### 4.1 CLI 傳圖：直接把路徑寫進 prompt

```bash
ollama run llama3.2-vision "描述這張圖 /path/to/image.png"
```

CLI 會偵測 prompt 中的檔案路徑並把圖片載入。

### 4.2 API：base64 放進 images 欄位

```bash
# 先把圖片轉 base64
IMG=$(base64 -i receipt.png)

curl http://localhost:11434/api/chat -d "{
  \"model\": \"llama3.2-vision\",
  \"messages\": [{
    \"role\": \"user\",
    \"content\": \"這張發票的總金額是多少？\",
    \"images\": [\"$IMG\"]
  }],
  \"stream\": false
}"
```

`messages[].images` 是一個字串陣列，每個元素是一張圖的 base64。

### 4.3 Python：直接給檔案路徑

Python SDK 更省事，`images` 可以直接放檔案路徑，SDK 會幫你讀檔轉 base64：

```python
from ollama import chat

# 看圖問答
res = chat(model='llama3.2-vision', messages=[{
    'role': 'user',
    'content': '這張圖裡有幾個人？他們在做什麼？',
    'images': ['/path/to/photo.jpg'],
}])
print(res.message.content)

# OCR：把圖片裡的文字抽出來
res = chat(model='qwen2.5-vl', messages=[{
    'role': 'user',
    'content': '把這張圖片裡的所有文字逐字抓出來，保留排版。',
    'images': ['/path/to/document.png'],
}])
print(res.message.content)
```

**三種常見用途**：

- **描述圖片**：無障礙 alt text、圖庫自動標籤。
- **OCR / 文件抽取**：發票、名片、螢幕截圖轉文字（`qwen2.5-vl` 對中文較友善）。
- **看圖問答（VQA）**：客服上傳截圖問問題、教育場景解圖。

### 4.4 硬體提醒

**Vision 模型比同尺寸的純文字模型更吃記憶體**，因為要額外載入影像編碼器，而且圖片本身會佔用大量 context token。在 8GB 記憶體的 Mac 上跑 `llama3.2-vision` 會很吃緊，建議 **16GB 以上**。如果 `ollama ps`（見第六節）顯示 GPU offload 不到 100%，代表記憶體不夠、部分算在 CPU 上，速度會明顯變慢。

---

## 五、推理 / Thinking 模型：讓模型「先想再答」

`deepseek-r1`、`qwen3`（think 模式）這類 **reasoning 模型**，會在給出答案前先產生一段「思考過程」（thinking trace）。這段思考通常能大幅提升數學、多步邏輯、程式除錯的正確率。

### 5.1 CLI 行為

```bash
ollama run deepseek-r1
>>> 一個水池有兩個進水管，單獨開分別要 4 小時和 6 小時裝滿，兩管一起開要多久？
```

CLI 會先印出模型的思考過程（通常會標示或以不同區塊呈現），接著才是最終答案。你會看到它一步步推導 `1/4 + 1/6 = 5/12`，再得出 `12/5 = 2.4 小時`。

### 5.2 API / SDK：think=True 與獨立的 thinking 欄位

在 API 和 SDK 中，可以用 `think=True` 開啟思考，而且**思考內容和最終答案是分開的**——`response.message.thinking` 是思考，`response.message.content` 是答案。這讓你可以只把 `content` 顯示給使用者，把 `thinking` 留給 log 除錯。

```python
from ollama import chat

res = chat(
    model='qwen3',
    messages=[{'role': 'user', 'content': '27 * 43 是多少？一步步算。'}],
    think=True,
)

print('=== 思考過程 ===')
print(res.message.thinking)   # 推理軌跡（可只留給 log）
print('=== 最終答案 ===')
print(res.message.content)    # 給使用者看的答案
```

### 5.3 何時值得用推理模型？

| 情境 | 建議 |
|------|------|
| 數學、邏輯謎題、多步推導 | ✅ 用 reasoning 模型 |
| 程式除錯、演算法設計 | ✅ 值得 |
| 複雜規劃（分解任務、排程） | ✅ 值得 |
| 一般閒聊、翻譯、簡單問答 | ❌ 別用——慢又費 token |
| 需要低延遲的即時互動 | ❌ 別用——思考會拖長回應時間 |

**代價很實在**：思考會多產生幾百到幾千個 token，延遲可能是一般回答的**數倍**。所以 reasoning 模型是「該用才用」的重型工具，不是預設選項。一個好策略是：用一般模型處理多數請求，偵測到「這題需要推理」時才切換到 reasoning 模型。

---

## 六、效能調校（Apple Silicon 專章）

這是 Mac 使用者最關心的一節。好消息：**Apple Silicon 上 Ollama 自動用 Metal GPU 加速，你什麼都不用設定**（沒有 CUDA，也不需要 CUDA）。M 系列晶片的**統一記憶體（unified memory）**由 CPU 和 GPU 共用，這對 LLM 特別有利——不用像獨顯那樣把資料在 VRAM 和 RAM 之間搬。

### 6.1 用 `ollama ps` 看模型跑在哪裡

```bash
ollama ps
```

```
NAME            ID              SIZE      PROCESSOR    UNTIL
qwen3:8b        abc123          6.5 GB    100% GPU     4 minutes from now
```

**`PROCESSOR` 這欄是關鍵**：

- **`100% GPU`** → 模型完全載入 GPU（unified memory），這是最理想的狀態，最快。
- **`70% GPU / 30% CPU`** → 記憶體不夠，部分層數 spill 到 CPU，**速度會明顯下降**。
- **`100% CPU`** → 完全沒用到 GPU，最慢。

看到不是 100% GPU，代表模型（加上 context）超出可用記憶體。解法：換小一點/量化更低的模型、降低 `num_ctx`、關掉背景吃記憶體的 App，或加開下面的省記憶體選項。

### 6.2 記憶體是最大瓶頸：模型大小 × num_ctx

統一記憶體要同時裝下：**模型權重 + KV cache（隨 context 長度成長）+ 系統其他程式**。兩個放大記憶體用量的旋鈕：

- **模型大小 / 量化**：7–8B 的 Q4 約需 5–6GB；同樣 8B 的 fp16 要 16GB。（量化細節見 Part 2。）
- **`num_ctx`**：context window 越大，KV cache 越大。把 `num_ctx` 從 4096 拉到 32768，KV cache 記憶體可能增加數 GB。

### 6.3 兩個省記憶體 / 加速的環境變數

```bash
# Flash Attention：降低長 context 的記憶體用量，長文可能加速
launchctl setenv OLLAMA_FLASH_ATTENTION "1"

# KV cache 量化：把 KV cache 從 fp16 壓成 q8_0 或 q4_0，長 context 省記憶體
launchctl setenv OLLAMA_KV_CACHE_TYPE "q8_0"

# 設完要重啟 Ollama（GUI 版：離開 App 再開；或重啟 ollama serve）
```

- **`OLLAMA_FLASH_ATTENTION=1`**：更省記憶體，長 context 情境常能加速。
- **`OLLAMA_KV_CACHE_TYPE`**：`q8_0`（品質幾乎無損、省一半 KV 記憶體）是最安全的選擇；`q4_0` 省更多但長文品質可能略降。**只有在你需要很長 context 時才需要動這個。**

### 6.4 keep_alive：避免重複載入延遲

模型第一次載入要花幾秒到十幾秒（把權重讀進記憶體）。`keep_alive` 控制模型用完後在記憶體待多久：

```bash
# 單次請求指定：載入後保留 30 分鐘
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3",
  "prompt": "hi",
  "keep_alive": "30m"
}'

# 全域預設（設 -1 表示永久常駐，0 表示用完立刻卸載）
launchctl setenv OLLAMA_KEEP_ALIVE "30m"
```

**取捨**：常駐（`keep_alive` 長 / `-1`）= 沒有重載延遲，但一直佔記憶體；用完即卸（`0`）= 省記憶體，但下次請求要重新載入。**互動式服務設長一點，批次跑完就散的設短一點。**

### 6.5 如何量測 tokens/sec

**方法一：`ollama run --verbose`**

```bash
ollama run qwen3 --verbose "寫一段 100 字的自我介紹"
```

跑完會印出計時，包含 `eval rate`（每秒生成幾個 token）。

**方法二：從 API 的計時欄位算**

API 回應（`stream:false`）帶回這些欄位（單位是奈秒）：

```json
{
  "eval_count": 250,
  "eval_duration": 5000000000,
  "prompt_eval_count": 40,
  "prompt_eval_duration": 300000000
}
```

生成速度公式：

```python
tokens_per_sec = eval_count / (eval_duration / 1e9)
# = 250 / (5_000_000_000 / 1e9) = 250 / 5 = 50 tokens/sec
```

> `eval_count`/`eval_duration` 是「生成」階段；`prompt_eval_*` 是「讀入 prompt」階段，兩者分開看。

### 6.6 實際速度概略區間

以下為**概略值**，實際依晶片世代（M1/M2/M3/M4）、記憶體頻寬與 context 長度而異：

- 在 M 系列 Mac 上，**7–8B 的 Q4 模型約每秒數十個 token（約 20–60 tokens/sec）**，互動體感流暢。
- 1–3B 小模型可達**約上百 tokens/sec**。
- 30B 以上大模型會掉到**約個位數到十幾 tokens/sec**，且很吃記憶體。

只要 `ollama ps` 顯示 `100% GPU`，你就拿到了這台機器該有的速度；掉出 100% GPU 才是真正的效能問題。

### 6.7 症狀 → 原因 → 調校手段

| 症狀 | 可能原因 | 調校手段 |
|------|------|------|
| 生成很慢（tokens/sec 低） | 模型太大 spill 到 CPU | `ollama ps` 確認；換小模型/更低量化，或降 `num_ctx` |
| 記憶體爆掉 / 系統卡頓 | 模型 + KV cache 超出 unified memory | 降 `num_ctx`、開 `OLLAMA_KV_CACHE_TYPE=q8_0`、減少常駐模型數 |
| 長文回應變超慢 | KV cache 隨 context 膨脹 | 開 `OLLAMA_FLASH_ATTENTION=1` + KV cache 量化 |
| 每次第一個請求都卡好幾秒 | 模型被卸載又重載 | 拉長 `keep_alive` / `OLLAMA_KEEP_ALIVE` |
| `ollama ps` 顯示部分 CPU | 記憶體不足以全載 GPU | 關背景 App、換量化版本、縮 context |
| 想更快但品質可接受 | 用了過高精度 | 改用 Q4 量化版（Part 2） |

---

## 七、多模型 / 並行服務

預設情況下 Ollama 一次只跑一個模型、序列處理請求。要服務多人或多模型，需要調三個環境變數：

```bash
launchctl setenv OLLAMA_NUM_PARALLEL "4"        # 每個模型同時處理的請求數
launchctl setenv OLLAMA_MAX_LOADED_MODELS "3"   # 同時常駐記憶體的模型數
launchctl setenv OLLAMA_KEEP_ALIVE "30m"        # 常駐時間
# 重啟 Ollama 生效
```

三者的交互作用與**記憶體預算**：

- **`OLLAMA_NUM_PARALLEL`**：同一個模型並行處理幾個請求。並行越多，KV cache 記憶體需求越高（每個並行請求各自有一份 context）。
- **`OLLAMA_MAX_LOADED_MODELS`**：允許幾個**不同**模型同時待在記憶體。越多越省切換時間，但每個模型都吃一份權重記憶體。
- **`keep_alive`**：模型閒置多久才卸載，讓出記憶體。

**核心約束**：`所有常駐模型的權重 + 所有並行請求的 KV cache` 必須裝進 unified memory。開太大會 spill 到 CPU（見第六節），反而更慢。

```
┌───────────────────────────────────────────────────────────┐
│           Unified Memory（例如 32GB）                        │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ qwen3:1.7b   │  │ qwen3:8b     │  │ llama3.2-vis │       │
│  │ (路由/分類)   │  │ (主力問答)    │  │ (看圖)        │       │
│  │  ~1.5GB      │  │  ~6GB        │  │  ~9GB        │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│    MAX_LOADED_MODELS=3 → 三個同時 resident                   │
│    NUM_PARALLEL=4 → 每個模型可同時服務 4 個請求               │
│    剩餘記憶體要留給 KV cache 與系統                           │
└───────────────────────────────────────────────────────────┘
```

### 7.1 策略：小模型路由 + 大模型攻堅

一個省資源又快的架構：**用一個很小的模型當「路由器 / 分類器」，判斷請求難度，只有難題才丟給大模型（或 reasoning 模型）。**

```python
from ollama import chat

def route(user_input: str) -> str:
    """用小模型判斷難度，回 'simple' 或 'hard'"""
    r = chat(model='qwen3:1.7b', messages=[{
        'role': 'user',
        'content': f'這個問題需要深度推理嗎？只回 simple 或 hard：\n{user_input}',
    }])
    return 'hard' if 'hard' in r.message.content.lower() else 'simple'

def answer(user_input: str) -> str:
    if route(user_input) == 'hard':
        # 難題：用大模型 + 思考模式
        r = chat(model='qwen3:8b', messages=[{'role': 'user', 'content': user_input}], think=True)
    else:
        # 簡單題：小模型快速回
        r = chat(model='qwen3:1.7b', messages=[{'role': 'user', 'content': user_input}])
    return r.message.content

print(answer('你好嗎？'))                    # → 走小模型，快
print(answer('證明根號 2 是無理數'))          # → 走大模型 + 思考
```

**效益**：多數「你好」「幫我改個錯字」類請求由 1.7B 秒回，省下大模型的算力給真正需要的難題。這也是雲端服務常用的成本優化手法，本地一樣適用。

---

## 八、遠端存取與安全（請務必讀完這一節）

### 8.1 開放 LAN 存取

預設 Ollama 只聽 `127.0.0.1`（本機）。要讓區網其他機器連進來，設 `OLLAMA_HOST`：

```bash
# Mac GUI 版
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
# 然後完全離開 Ollama App 再重開

# 或 ollama serve 版
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

`0.0.0.0:11434` 表示監聽所有網卡的 11434 埠。

### 8.2 最重要的安全警告

> ### ⚠️ Ollama 沒有任何內建驗證機制。
> **任何能連到 11434 埠的人，都能無限制使用你的模型、讀取你載入的資料、耗盡你的資源。**
> **絕對不要把 11434 埠直接暴露到公網。** 不要在路由器上做 port forwarding 把它開到 internet，不要綁到有公網 IP 的雲主機而不加保護。

把 Ollama 裸奔上公網，等於把你的機器算力免費開放給全世界，還可能被當跳板。這不是理論——網路上有人專門掃描開放的 11434 埠。

### 8.3 正確的四種暴露方式

```
┌──────────┐     HTTPS + Auth      ┌──────────────────┐    localhost    ┌──────────┐
│  Client  │ ────────────────────▶ │  Reverse Proxy    │ ──────────────▶ │  Ollama  │
│ (外部)   │   帳密 / Token / TLS   │  (nginx / Caddy)  │   :11434        │  :11434  │
└──────────┘                       │  驗證 + 加密       │  (只聽本機)     └──────────┘
                                   └──────────────────┘
```

| 暴露方式 | 風險 | 建議 |
|------|------|------|
| **直接開 `0.0.0.0` 上公網** | 🔴 極高：無驗證，任何人可用 | ❌ 絕對禁止 |
| **反向代理（nginx / Caddy）+ auth + TLS** | 🟢 低 | ✅ 對外服務的標準做法；加 Basic Auth 或 API token，用 TLS 加密 |
| **SSH tunnel** | 🟢 低 | ✅ 個人遠端最簡單：`ssh -L 11434:localhost:11434 user@mac`，之後連本機 11434 就等於連遠端 |
| **VPN / Tailscale** | 🟢 低 | ✅ 團隊/多裝置最方便，Ollama 只在私有網段可見 |
| **僅開 LAN（`0.0.0.0` 但有防火牆隔離公網）** | 🟡 中 | ⚠️ 內網可信才行；仍建議加代理 |

**SSH tunnel 一行搞定個人遠端**：

```bash
# 在你的筆電上執行，把遠端 Mac 的 11434 映射到本機
ssh -L 11434:localhost:11434 user@your-mac.local
# 之後在筆電上 curl localhost:11434 就等於打到遠端 Mac，全程走 SSH 加密
```

**Caddy 反向代理範例**（自動 TLS + Basic Auth）：

```
# Caddyfile
ollama.example.com {
    basicauth {
        admin $2a$14$...bcrypt-hash...
    }
    reverse_proxy localhost:11434
}
```

### 8.4 瀏覽器 CORS：OLLAMA_ORIGINS

如果你從網頁前端（JavaScript）直接呼叫 Ollama，瀏覽器會擋 CORS。用 `OLLAMA_ORIGINS` **明確限制**允許的來源，別用 `*`：

```bash
launchctl setenv OLLAMA_ORIGINS "https://myapp.example.com"
```

### 8.5 本地硬體不夠時：Ollama Cloud 模型

如果任務需要的模型（例如 235B、70B）大到本地跑不動，Ollama 提供 **cloud 模型**（模型名後綴 `:cloud`），把運算 offload 到 Ollama 的雲，但你用的還是同一套 API：

```bash
ollama signin                     # 先登入
ollama run qwen3:235b-cloud       # 在雲端跑巨型模型，本機當客戶端
```

適合「大部分用本地小模型，偶爾需要超大模型」的混合場景。注意這代表資料會送到 Ollama 雲端，敏感資料要斟酌。

---

## 九、上生產的實務清單

把 Ollama 從「我機器上跑得動」推到「穩定服務別人」，需要一份 checklist：

### 9.1 部署前

- [ ] **Pre-pull 模型**：部署時就先 `ollama pull` 好所有要用的模型，別等第一個使用者請求才下載（會 timeout）。
- [ ] **Pin 版本**：用明確的 tag（`qwen3:8b`）而非浮動的 `latest`；講究可重現性時可用 digest 鎖定。避免某天模型悄悄更新導致行為改變。
- [ ] **確認磁碟空間**：模型存在 `~/.ollama/models`，大模型動輒數 GB 到數十 GB。監控這個目錄別把磁碟塞爆。

### 9.2 運行中監控

- [ ] **監控 `/api/ps`**：定期查詢哪些模型常駐、跑在 GPU 還是 CPU。
- [ ] **記錄 timing 指標**：從 API 回應蒐集 `eval_count`/`eval_duration` 算 tokens/sec，建 dashboard 觀察退化。
- [ ] **看 server log**：`ollama serve` 的輸出（或 `server.log`）記錄載入、錯誤、OOM。

```bash
# 快速健檢腳本
curl -s http://localhost:11434/api/ps | python3 -m json.tool
```

### 9.3 資源與策略

- [ ] **設合理的 `keep_alive`**：互動服務常駐、批次任務用完即卸。
- [ ] **調 `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS`**：依記憶體預算，別開到 spill 到 CPU。
- [ ] **模型路由策略**：小模型分類 + 大模型攻堅（第七節），省算力。
- [ ] **安全**：確認沒有裸奔公網，反向代理 / VPN / SSH tunnel 到位（第八節）。

### 9.4 何時該搬離本地 Mac

| 訊號 | 建議 |
|------|------|
| 併發請求量超過單機負荷 | 搬到專用伺服器或雲 GPU（Linux + NVIDIA） |
| 需要的模型本地記憶體裝不下 | 用 `:cloud` 模型，或雲 GPU |
| 需要 24/7 高可用 | Mac 當開發機、生產放伺服器叢集 |
| 尖峰負載不固定 | 雲端彈性擴縮，本地做基準負載 |

**Mac 上的 Ollama 是絕佳的開發、原型、個人與小團隊工具**；當規模上去，搬到 Linux + 獨立 GPU 或雲是自然的下一步——好消息是 API 一模一樣，程式幾乎不用改。

---

## 十、為什麼選 X 不選 Y（迷你決策表）

| 決策 | 選 X | 選 Y | 何時翻轉 |
|------|------|------|------|
| **本地 Ollama vs 雲 API** | 隱私、零邊際成本、可離線、可控 | 前沿模型能力最強、免維運 | 需要最強推理、免管硬體、量大到本地不划算 → 選雲 |
| **小模型 agent vs 大模型 agent** | 快、省記憶體、可路由 | 工具呼叫更穩、推理更強 | 工具鏈複雜、參數易錯、需多步規劃 → 選大模型 |
| **reasoning 模型 vs 一般模型** | 數學/多步邏輯正確率高 | 快、省 token、低延遲 | 只是閒聊/翻譯/簡單問答 → 選一般模型 |
| **常駐（keep_alive 長）vs 用完即卸** | 無重載延遲、互動流暢 | 省記憶體、可多模型輪替 | 記憶體吃緊、模型多、請求稀疏 → 選用完即卸 |
| **反向代理 vs SSH tunnel** | 多人、對外服務、正式 | 個人、臨時、最簡單 | 只有自己遠端用一下 → SSH tunnel 就夠 |

---

## 十一、全系列總結：你的本地 LLM 能力成長路徑

五篇走完，你從「裝好 Ollama」一路走到「能蓋 agent、上生產」。回顧這條路：

```
能力成長路徑
════════════════════════════════════════════════════════════════

Part 1          Part 2          Part 3          Part 4          Part 5
安裝            選型            API/客製        整合            進階
  │               │               │               │               │
  ▼               ▼               ▼               ▼               ▼
跑出第一        依任務/硬       REST API +      接進 App:       tool calling
個本地模型  →   體選對模型  →   自訂          →  chatbot /   →   / agent / vision
                (量化/參數)     Modelfile       RAG / stream    / reasoning /
                                                                效能 / 安全 / 生產
  │               │               │               │               │
使用者 ─────────────────────────────────────────────────────▶ 架構師
```

| 階段 | 你學會的核心能力 | 產出 |
|------|------|------|
| **Part 1 安裝** | 安裝、`ollama run`、基本 CLI | 能在本機跑模型 |
| **Part 2 選型** | 模型生態、量化、參數量 vs 硬體 | 會為任務挑對模型 |
| **Part 3 API/客製** | REST API、Modelfile、system prompt | 把模型變成可程式化服務 |
| **Part 4 整合** | chatbot、RAG、streaming、SDK | 接進真實應用 |
| **Part 5 進階** | tool calling、agent、vision、reasoning、效能、安全、生產 | 蓋出能上線的本地 LLM 系統 |

### 給你的下一步建議

1. **挑一個真實痛點**，用本篇的 agent 骨架做一個能自動化它的小工具（例如查內部文件、整理檔案、批次 OCR）。
2. **建立量測習慣**：用 `ollama ps` 和 tokens/sec 培養對「什麼配置在你機器上最快」的直覺。
3. **把安全內化成反射**：任何要遠端存取的場景，先問「這有沒有裸奔公網？」。
4. **善用混合架構**：本地小模型處理日常、reasoning 或雲模型處理難題，兼顧成本與能力。

本地 LLM 的門檻，這幾年被 Ollama 拉到極低——一台 Mac、幾個指令，你就擁有一個不用付月費、資料不外流、可以任你改造的 AI 平台。從玩具到生產，差別不在硬體，而在你是否把這五篇的能力串成一套系統。

**現在，去蓋點東西吧。** 感謝你一路讀到系列的最後一篇，祝你的本地 AI 專案順利。

---

## 系列導覽

- Part 1 — [安裝與第一個本地模型](../ollama-on-mac-part1-installation-zh/)
- Part 2 — [公開模型全覽與選型指南](../ollama-on-mac-part2-public-models-zh/)
- Part 3 — [REST API 與自訂 Modelfile](../ollama-on-mac-part3-api-modelfile-zh/)
- Part 4 — [與應用整合](../ollama-on-mac-part4-app-integration-zh/)
- **Part 5 — 工具呼叫、多模型服務與進階實踐（本篇）**

## 參考連結

- [Ollama 官方文件](https://docs.ollama.com/)
- [Tool Calling 能力文件](https://docs.ollama.com/capabilities/tool-calling)
- [GPU / 效能文件](https://docs.ollama.com/gpu)
- [Ollama API 文件](https://docs.ollama.com/api)
