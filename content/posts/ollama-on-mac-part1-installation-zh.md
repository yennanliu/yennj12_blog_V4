---
title: "ollama on mac - part 1 - 安裝與第一個本地模型"
date: 2026-07-15T09:00:00+08:00
draft: false
description: "從零開始在 macOS 上安裝 Ollama,認識硬體需求與記憶體對照,並跑起你的第一個本地 LLM,完整掌握 CLI 指令與背後運作原理。"
categories: ["engineering", "ai", "all"]
tags: ["Ollama", "LLM", "macOS", "Local LLM", "Apple Silicon", "AI Engineering", "Llama"]
authors: ["yen"]
readTime: "18 min"
---

> 大部分人第一次聽到「在自己的 Mac 上跑 LLM」,直覺反應是:那不是要一張幾萬塊的顯示卡、還要會編譯一堆奇怪的 C++ 專案嗎?
> 現實是:在 Apple Silicon 的 Mac 上,你只要下載一個 `.dmg`、拖進 `/Applications`,再打一行 `ollama run llama3.2`,兩分鐘後就能跟一個本地模型對話。
> 沒有 API 金鑰、沒有帳單、沒有網路也能用,而且你的 prompt 永遠不會離開這台電腦。
> 這一系列會帶你從安裝一路走到 API 整合與工具呼叫;這篇 Part 1,我們先把地基打穩。

---

## 一、為什麼要在本機跑 LLM?

在動手安裝之前,先搞清楚一件事:**為什麼不直接用 OpenAI、Claude 這類雲端 API 就好?** 這決定了 Ollama 值不值得你花時間。

本地跑 LLM 的核心價值有五個:

- **隱私(Privacy)**:你的 prompt、公司的程式碼、病歷、合約草稿,全部留在這台 Mac 上,不會經過任何第三方伺服器。對受法規管制的產業(醫療、金融、法務)這幾乎是唯一能用 LLM 的方式。
- **離線(Offline)**:飛機上、咖啡廳的爛 Wi-Fi、公司內網隔離環境,只要模型已經下載好,完全不需要網路。
- **零 API 費用(Zero cost)**:雲端 API 是按 token 計費,重度使用一個月幾百美金跑不掉。本地模型下載後,你想 call 幾百萬次都是免費的,只花電費。
- **低延遲(Low latency)**:沒有網路來回(round-trip),第一個 token 通常在幾十毫秒內就出來,適合需要即時回饋的互動場景。
- **可實驗(Experimentation)**:想試不同模型、改參數、自訂 system prompt、做 fine-tune、跑 RAG,本地環境讓你毫無顧忌地亂玩,不用擔心帳單爆炸。

當然,天下沒有白吃的午餐。**本地跑 LLM 的取捨**大致如下:

| 面向 | 雲端 API(GPT-4、Claude) | 本地 Ollama |
|------|---------------------------|-------------|
| 模型能力 | 頂級(數千億參數) | 中小型(1B–70B),品質稍遜 |
| 隱私 | 資料送到第三方 | 完全在本機 |
| 費用 | 按 token 付費,長期昂貴 | 免費(僅硬體與電費) |
| 延遲 | 受網路影響 | 穩定、低延遲 |
| 硬體門檻 | 幾乎為零 | 需要足夠 RAM |
| 維運 | 廠商負責 | 自己管理 |

**一句話結論**:如果你要的是「宇宙最強、偶爾用一下」,雲端 API 更合適;如果你要的是「隱私、離線、大量實驗、不想被計費」,那 Ollama 就是為你設計的。而且兩者不衝突——很多人是本地開發原型、正式上線再接雲端,或反過來用本地模型處理敏感資料。

Ollama 本身是一個**開源工具**,把「下載模型、載入記憶體、提供推論服務」這件麻煩事包成一行指令。它底層用的是 `llama.cpp`,但你完全不需要知道這件事就能用。

### 一個實際的成本對照

具體感受一下差距。假設你在做一個內部工具,每天要處理 500 次請求、每次平均 1,500 tokens:

```text
雲端 API(以 GPT-4 級別粗估):
  500 次/天 × 1,500 tokens × 30 天 ≈ 22.5M tokens/月
  以每 1M tokens 約 $10 計 → 每月約 $200+,一年 $2,400+

本地 Ollama(llama3.1:8b):
  硬體:一台 16GB Mac(可能你本來就有)
  API 費用:$0
  電費:幾乎可忽略
```

當然,GPT-4 的品質更高;但對很多「不需要頂級智慧、只要夠用」的批次任務(分類、摘要、抽取、格式轉換),本地 8B 模型完全能勝任,而且**一年省下的錢遠超過一台 Mac**。這就是為什麼越來越多團隊把「能本地跑的就本地跑」當作預設策略。

---

## 二、系統需求與硬體

### 基本需求

- **作業系統**:macOS Sonoma(v14)或更新版本。
- **晶片**:
  - **Apple Silicon(M1/M2/M3/M4 系列)**:CPU + GPU 都能參與運算,透過 Metal 做 GPU 加速,這是最推薦的選擇。
  - **Intel x86 Mac**:只能用 CPU 推論,速度明顯較慢,小模型還堪用,大模型會很吃力。
- **記憶體(RAM)**:這是**最關鍵的限制因素**。本地 LLM 要把整個模型權重載入記憶體,模型多大就吃多少 RAM。

### 統一記憶體(Unified Memory)為什麼重要

Apple Silicon 最大的優勢是**統一記憶體架構**:CPU 和 GPU 共用同一塊記憶體,不像傳統 PC 那樣「系統 RAM」和「顯卡 VRAM」是分開的。

這代表什麼?在一台 32GB 的 M 系列 Mac 上,GPU 可以直接存取接近全部 32GB 的空間來放模型;而在 PC 上,你可能有 32GB RAM 但顯卡只有 8GB VRAM,大模型根本塞不進 GPU。**這就是為什麼一台看似普通的 MacBook,跑 LLM 的能力往往勝過同價位的 Windows 筆電。**

### RAM 需求估算

粗略的心法:一個 **Q4 量化(4-bit quantized)** 的模型,大約需要:

```text
所需 RAM ≈ (參數量 B) × 0.6~0.75 GB + 系統與 context 開銷
```

- 8B 模型 ≈ 5–6 GB
- 3B 模型 ≈ 2–3 GB
- 70B 模型 ≈ 40–48 GB

注意這只是模型權重本身;實際跑起來還要留給 macOS 系統、其他 App、以及 context window(對話越長吃越多)。**保守一點,永遠多留 4–8GB 給系統。**

### Mac RAM → 建議模型大小對照表

| Mac 記憶體 | 建議模型規模 | 具體範例 | 備註 |
|-----------|-------------|---------|------|
| 8 GB | ≤ 3B(最多勉強 7B) | `llama3.2:1b`、`llama3.2:3b`、`qwen3:4b` | 開太多其他 App 會卡;7B 要關掉瀏覽器 |
| 16 GB | 最高 8B–13B | `llama3.1:8b`、`mistral:7b`、`gemma3:4b` | 甜蜜點,日常最實用的配置 |
| 32 GB | 32B 級別 | `qwen3:32b`、`gemma3:27b` | 品質明顯提升,速度尚可 |
| 64 GB+ | 70B | `llama3.1:70b` | 接近雲端小模型的體驗 |

**給初學者的建議**:不管你有多少 RAM,第一次都先從 `llama3.2:3b` 這種小模型開始。跑得快、下載也快,先把流程走通,再慢慢往上升級。

### 怎麼看自己的 Mac 有多少記憶體

不確定自己的配置?點左上角蘋果圖示 →「關於這台 Mac」,就能看到晶片型號與記憶體大小。或用終端機:

```bash
# 查看晶片與記憶體
sysctl -n machdep.cpu.brand_string   # Intel Mac 才有意義
sysctl hw.memsize                    # 記憶體(bytes)
system_profiler SPHardwareDataType | grep -E "Chip|Memory"
```

```text
      Chip: Apple M2 Pro
      Memory: 16 GB
```

看到 `Apple M...` 開頭代表你是 Apple Silicon,能享受 GPU 加速與統一記憶體;看到 Intel 字樣則只能走 CPU 推論,選模型時要更保守。

---

## 三、兩種安裝方式:GUI 與 Homebrew

Ollama 在 macOS 上有兩條安裝路線。我先講結論:**大部分人用 GUI(.dmg)就對了**;如果你是重度 CLI 使用者、想用 Homebrew 統一管理套件,才選 Homebrew。

### 方法 A:GUI 安裝(.dmg,推薦新手)

步驟:

1. 打開瀏覽器到 [https://ollama.com/download](https://ollama.com/download),下載 macOS 版的 `Ollama.dmg`。
2. 雙擊掛載 `.dmg`,把 **Ollama.app** 拖進 `/Applications` 資料夾。
3. 第一次打開 `Ollama.app`,它會問你要不要安裝 CLI 指令的符號連結(symlink)到 `/usr/local/bin/ollama`。**按同意**,這樣你才能在終端機用 `ollama` 指令。
4. 安裝完成後,你會在螢幕右上角的 **menu bar(選單列)看到一個 Ollama 的羊駝圖示**。這代表背景 server 已經自動啟動了。

```text
安裝完成後,menu bar 會多一個羊駝圖示 🦙
點它可以看到:
  • Ollama is running
  • View logs
  • Quit Ollama
```

**GUI 版的好處**:server 會自動啟動、會自動提示更新、menu bar 隨時能看狀態,對不想碰終端機設定的人最友善。

### 方法 B:Homebrew 安裝(給 CLI 老手)

如果你已經在用 [Homebrew](https://brew.sh/) 管理套件:

```bash
# 安裝 CLI 版本(formula)
brew install ollama
```

安裝完之後,**Homebrew 的 formula 版本不會自動啟動 server**,你要手動啟動:

```bash
# 方式一:前景啟動(關掉終端機 server 就停)
ollama serve

# 方式二:用 brew services 讓它背景常駐、開機自動啟動
brew services start ollama
```

如果你想要的是**含 menu bar 圖示的 GUI App**,Homebrew 也可以裝 cask:

```bash
# 裝 GUI 版(等同下載 .dmg)
brew install --cask ollama
```

### GUI vs Homebrew 怎麼選

| 比較項 | GUI(.dmg / cask) | Homebrew formula |
|--------|-------------------|------------------|
| Server 啟動 | 開 App 自動啟動 | 需手動 `ollama serve` 或 `brew services start` |
| Menu bar 圖示 | 有 | 無(cask 才有) |
| 自動更新 | App 內建自動更新 | `brew upgrade ollama` |
| 開機自啟 | 可設定 | `brew services` 管理 |
| 適合對象 | 新手、想要圖形化狀態 | CLI 重度使用者、要腳本化 |
| 版本管理 | 手動 / 內建 | 跟其他 brew 套件統一管理 |

**我的建議**:第一次玩,直接用 GUI `.dmg`。等你熟了、要寫自動化腳本、或想在 headless 環境(例如 SSH 進去的 Mac mini)跑,再改用 `brew install ollama` + `ollama serve`。

---

## 四、驗證安裝

裝完別急著跑模型,先確認三件事都 OK:

### 1. CLI 版本

```bash
ollama --version
```

```text
ollama version is 0.5.7
```

如果這行有版本號跑出來,代表 CLI symlink 裝好了。如果出現 `command not found: ollama`,先跳到第九節排查。

### 2. Menu bar App

看螢幕右上角有沒有羊駝圖示。有,代表 GUI server 在跑。(Homebrew formula 使用者這步跳過,改看下一步。)

### 3. Server 有沒有活著

Ollama 的核心是一個跑在 **`localhost:11434`** 的 HTTP server。用 `curl` 打它一下:

```bash
curl http://localhost:11434
```

```text
Ollama is running
```

看到 `Ollama is running` 就代表 server 正常。如果連不上,可能是 server 沒啟動——GUI 使用者打開 App,Homebrew 使用者跑 `ollama serve`。

**這三步都過,才算真的裝好。** 尤其第三步,後面 Part 3 講 REST API、Part 4 講應用整合,全部都靠這個 11434 port。

---

## 五、跑第一個模型:`ollama run llama3.2`

現在來跑第一個本地 LLM。一行指令搞定:

```bash
ollama run llama3.2
```

**第一次跑會先自動下載模型**(之後就不用了)。你會看到下載進度:

```text
pulling manifest
pulling dde5aa3fc5ff... 100% ▕████████████████▏ 2.0 GB
pulling 966de95ca8a6... 100% ▕████████████████▏ 1.4 KB
pulling fcc5a6bec9da... 100% ▕████████████████▏ 7.7 KB
pulling a70ff7e570d9... 100% ▕████████████████▏ 6.0 KB
pulling 56bb8bd477a5... 100% ▕████████████████▏  96 B
pulling 34bb5ab01051... 100% ▕████████████████▏ 561 B
verifying sha256 digest
writing manifest
success
>>> Send a message (/? for help)
```

`llama3.2` 預設是 3B 版本,大約 2GB。下載速度看你的網路,通常幾分鐘內完成。

下載完會**直接進入互動對話模式**,提示符號變成 `>>>`。試著問它問題:

```text
>>> 用一句話解釋什麼是 Ollama
Ollama 是一個讓你在本機電腦上輕鬆下載、執行與管理大型語言模型(LLM)的
開源工具,不需要雲端 API 也能與 AI 對話。

>>> 幫我寫一個 Python 函式,計算費氏數列第 n 項
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```

聊完要離開,輸入 `/bye`:

```text
>>> /bye
```

就這樣,你已經在自己的 Mac 上跑起一個完全本地的 LLM 了。**沒有網路、沒有金鑰、沒有帳單。**

如果你只想下載模型、暫時不進對話,用 `pull`:

```bash
ollama pull llama3.2
```

---

## 六、互動模式教學

進入 `>>>` 對話後,除了直接打字聊天,還有一組斜線指令(slash commands)可以用。

### 查看說明

```text
>>> /?
Available Commands:
  /set            Set session variables
  /show           Show model information
  /load <model>   Load a session or model
  /save <model>   Save your current session
  /clear          Clear session context
  /bye            Exit
  /?, /help       Help for a command
```

### 調整參數:`/set`

想讓回答更有創意或更保守,調 `temperature`:

```text
>>> /set parameter temperature 0.7
Set parameter 'temperature' to '0.7'
```

`temperature` 越高越發散(適合創意寫作),越低越穩定(適合事實問答)。

### 查看模型資訊:`/show`

```text
>>> /show info
  Model
    architecture        llama
    parameters          3.2B
    context length      131072
    quantization        Q4_K_M

>>> /show modelfile
# 顯示這個模型的 Modelfile 定義(system prompt、參數、template 等)
```

`/show modelfile` 會印出模型的完整定義,包括 system prompt 和 template——這在 Part 3 自訂 Modelfile 時超級有用。

### 多行輸入

要貼一段程式碼或長文,用三個引號 `"""` 包起來:

```text
>>> """
... 請幫我 review 這段程式碼:
... def add(a, b):
...     return a - b
... """
你的函式名稱是 add(加法),但實作卻是 a - b(減法),
這是一個 bug,應該改成 return a + b。
```

**常用互動指令小抄**:

| 指令 | 作用 |
|------|------|
| `/?` 或 `/help` | 顯示說明 |
| `/set parameter <name> <value>` | 調整參數(如 temperature) |
| `/show info` | 顯示模型架構、參數量、context 長度 |
| `/show modelfile` | 顯示完整 Modelfile 定義 |
| `/clear` | 清除當前對話 context |
| `/bye` | 離開互動模式 |
| `"""..."""` | 多行輸入 |

---

## 七、核心 CLI 指令巡禮

離開互動模式後,`ollama` 在終端機裡還有一整套管理指令。這是你日常會反覆用到的核心工具。

### `ollama pull` — 只下載不執行

```bash
ollama pull mistral:7b
```

適合你想預先下載好幾個模型,晚點再用。

### `ollama list`(別名 `ollama ls`)— 看已下載的模型

```bash
ollama list
```

```text
NAME              ID              SIZE      MODIFIED
llama3.2:latest   a80c4f17acd5    2.0 GB    5 minutes ago
mistral:7b        f974a74358d6    4.1 GB    2 hours ago
qwen3:4b          bd8c8b3a5e3d    2.6 GB    1 day ago
```

### `ollama ps` — 看正在記憶體裡的模型

```bash
ollama ps
```

```text
NAME              ID              SIZE      PROCESSOR    UNTIL
llama3.2:latest   a80c4f17acd5    3.5 GB    100% GPU     4 minutes from now
```

這個指令很重要:它告訴你**哪些模型正佔用記憶體、用 CPU 還是 GPU、以及還會被留在記憶體多久(keep-alive)**。`PROCESSOR` 顯示 `100% GPU` 代表完全跑在 Apple Silicon 的 GPU 上。

### `ollama stop` — 從記憶體卸載模型

```bash
ollama stop llama3.2
```

模型跑完預設會在記憶體裡待一段時間(方便下次快速回應)。如果你記憶體吃緊、想立刻釋放,用 `stop` 手動卸載。

### `ollama rm` — 刪除模型檔案

```bash
ollama rm mistral:7b
```

```text
deleted 'mistral:7b'
```

這是**從硬碟刪掉**模型檔案(不只是卸載記憶體),要重用得重新 `pull`。

### `ollama show` — 看模型詳細資訊

```bash
ollama show llama3.2
```

```text
  Model
    architecture        llama
    parameters          3.2B
    context length      131072
    quantization        Q4_K_M

  Parameters
    temperature         0.6
    top_p               0.9

  License
    Llama 3.2 Community License
```

### `ollama cp` — 複製模型(常用於自訂)

```bash
ollama cp llama3.2 my-llama
```

把現有模型複製一份改名,方便你之後基於它改 Modelfile 做自訂版本(Part 3 詳談)。

### CLI 指令總覽小抄

| 指令 | 作用 | 範例 |
|------|------|------|
| `ollama run <model>` | 下載(若無)並進入對話 | `ollama run llama3.2` |
| `ollama pull <model>` | 只下載模型 | `ollama pull mistral:7b` |
| `ollama list` / `ls` | 列出已下載模型 | `ollama list` |
| `ollama ps` | 列出記憶體中運行的模型 | `ollama ps` |
| `ollama stop <model>` | 從記憶體卸載 | `ollama stop llama3.2` |
| `ollama rm <model>` | 刪除模型檔案 | `ollama rm mistral:7b` |
| `ollama show <model>` | 顯示模型資訊 | `ollama show llama3.2` |
| `ollama cp <src> <dst>` | 複製模型 | `ollama cp llama3.2 my-llama` |
| `ollama serve` | 手動啟動 server | `ollama serve` |
| `ollama --version` | 顯示版本 | `ollama --version` |

---

## 八、Ollama 在背後怎麼運作

理解底層架構,之後遇到問題才知道從哪查。Ollama 其實是**「client-server 架構」**:你打的 `ollama` 指令是 client,真正做事的是背景那個 server。

### 架構圖

```text
┌──────────────────────────────────────────────────────────────┐
│                        你的 Mac                                │
│                                                                │
│   ┌───────────────┐         ┌───────────────────────────┐    │
│   │  ollama CLI   │         │   Menu bar App (GUI)      │    │
│   │  (你打的指令)  │         │   自動啟動 server          │    │
│   └───────┬───────┘         └────────────┬──────────────┘    │
│           │                              │                    │
│           │   HTTP 請求                  │ 啟動 / 監控         │
│           ▼                              ▼                    │
│   ┌────────────────────────────────────────────────────┐    │
│   │        Ollama Server (localhost:11434)             │    │
│   │  ┌──────────────┐   ┌───────────────────────────┐  │    │
│   │  │  REST API    │   │   模型排程 / keep-alive    │  │    │
│   │  │  /api/chat   │   │   記憶體載入 & 卸載         │  │    │
│   │  │  /api/generate│  └───────────────────────────┘  │    │
│   │  └──────┬───────┘                                   │    │
│   └─────────┼──────────────────────────────────────────┘    │
│             │ 載入權重                                        │
│             ▼                                                 │
│   ┌────────────────────────┐    ┌────────────────────────┐  │
│   │  Model in RAM / GPU     │    │  模型檔案(硬碟)        │  │
│   │  (統一記憶體, Metal)     │◀───│  ~/.ollama/models      │  │
│   └────────────────────────┘    └────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 運作流程

1. **Server 啟動**:GUI App 開啟時自動啟動 server;Homebrew 使用者用 `ollama serve` 手動啟動。Server 監聽 **port 11434**。
2. **模型儲存**:所有下載的模型放在 **`~/.ollama/models`**。這裡會隨你 pull 越多模型越大,要注意硬碟空間。
3. **記憶體載入**:當你 `ollama run` 或透過 API 呼叫某模型,server 把模型權重從硬碟載入記憶體(Apple Silicon 上會直接放到統一記憶體讓 GPU 用)。第一次載入會慢一點(冷啟動),之後就快。
4. **keep-alive 概念**:模型跑完不會馬上從記憶體踢掉,預設會**保留一段時間**(這就是 `ollama ps` 裡 `UNTIL` 欄位的意思)。這樣你連續問問題時不用每次重新載入。想立刻釋放就用 `ollama stop`。(keep-alive 的細部調整放到 Part 3 講。)

### 日誌(Logs)在哪

出問題時,日誌是第一手線索:

```bash
# GUI App 日誌
~/.ollama/logs/app.log

# Server 日誌
~/.ollama/logs/server.log
```

**關鍵心智模型**:記住 CLI 只是個「遙控器」,真正跑模型的是那個 `localhost:11434` 的 server。所以任何整合(Python、LangChain、Open WebUI)本質上都是在對這個 port 發 HTTP 請求。這條主線會貫穿整個系列。

---

## 九、常見安裝與執行問題排查

第一次裝難免踩坑。這裡整理最常見的問題與解法。

| 症狀 | 可能原因 | 解法 |
|------|---------|------|
| `command not found: ollama` | CLI symlink 沒裝,或不在 PATH | 開 Ollama.app 讓它裝 symlink;或確認 `/usr/local/bin` 在 PATH。Homebrew 使用者跑 `brew link ollama` |
| `curl localhost:11434` 連不上 | server 沒啟動 | GUI:開 App;Homebrew:`ollama serve` 或 `brew services start ollama` |
| `Error: listen tcp 127.0.0.1:11434: bind: address already in use` | port 11434 被別的程序占用 | 用 `lsof -i :11434` 找出占用者;關掉舊的 server,或設 `OLLAMA_HOST` 換 port |
| 模型跑到一半當掉 / 系統變超慢 | 記憶體不足(模型太大) | 換小一點的模型(如 3B);`ollama stop` 卸載其他模型;關掉吃 RAM 的 App |
| 模型下載很慢 / 中途斷線 | 網路問題 | Ollama 支援斷點續傳,重跑 `ollama pull` 會接續下載;換更穩的網路 |
| 回應非常慢(每秒幾個字) | 跑在 CPU 而非 GPU,或模型過大 | `ollama ps` 看 `PROCESSOR` 欄;Intel Mac 只能用 CPU;換更小模型 |
| 硬碟空間不足 | 模型檔案累積在 `~/.ollama/models` | `ollama list` 看佔用;`ollama rm` 刪不用的;或用 `OLLAMA_MODELS` 搬到外接硬碟 |

### 幾個實用排查指令

```bash
# 看誰占用了 11434 port
lsof -i :11434

# 即時追蹤 server 日誌
tail -f ~/.ollama/logs/server.log

# 看目前記憶體用量與運行模型
ollama ps

# 看已下載模型佔用多少空間
ollama list
```

**環境變數預告**:兩個之後常用的環境變數——`OLLAMA_MODELS`(改模型儲存位置,例如搬到外接 SSD)和 `OLLAMA_HOST`(改綁定的位址與 port)。詳細用法留到 Part 3 講 API 與設定時再深入。

### 更新與移除

```bash
# 更新:GUI 版會自動提示更新,或重新下載 .dmg
# Homebrew 版:
brew upgrade ollama
```

要完整移除 Ollama,刪掉這三處:

```text
1. /Applications/Ollama.app          ← App 本體
2. /usr/local/bin/ollama             ← CLI symlink
3. ~/.ollama                         ← 模型、設定、日誌
   (以及 ~/Library 底下的相關 cache)
```

---

## 十、小結與下一篇預告

到這裡,你應該已經完成:

- **搞懂為什麼要本地跑 LLM**:隱私、離線、零費用、低延遲、可實驗,以及它跟雲端 API 的取捨。
- **確認硬體條件**:macOS 14+、Apple Silicon 的統一記憶體優勢,並用 RAM 對照表選對模型大小。
- **裝好 Ollama**:GUI(.dmg)或 Homebrew,並通過 `ollama --version`、menu bar、`curl localhost:11434` 三重驗證。
- **跑起第一個模型**:`ollama run llama3.2`,學會互動模式的斜線指令。
- **掌握核心 CLI**:pull、list、ps、stop、rm、show、cp。
- **理解底層架構**:CLI ↔ `localhost:11434` server ↔ 記憶體中的模型,以及 keep-alive 與日誌位置。
- **會排查常見問題**:port 占用、記憶體不足、command not found、下載慢。

**現在你手上有一個能跑的本地 LLM 環境了。** 但你可能會問:`llama3.2` 之外還有哪些模型?我的 Mac 該選 Llama、Qwen、Gemma 還是 Mistral?哪個適合寫程式、哪個適合中文、哪個適合 RAG?

這正是 **Part 2 - 公開模型全覽與選型指南** 要回答的。我們會走一遍 Ollama 的模型庫,依照用途、語言、大小,教你怎麼挑出最適合你硬體與任務的模型。

我們下一篇見。

---

## 系列導覽

- **Part 1 — 安裝與第一個本地模型(本篇)**
- [Part 2 — 公開模型全覽與選型指南](../ollama-on-mac-part2-public-models-zh/)
- [Part 3 — REST API 與自訂 Modelfile](../ollama-on-mac-part3-api-modelfile-zh/)
- [Part 4 — 與應用整合(Python、OpenAI SDK、LangChain、Open WebUI、RAG)](../ollama-on-mac-part4-app-integration-zh/)
- [Part 5 — 工具呼叫、多模型服務與進階實踐](../ollama-on-mac-part5-advanced-zh/)

## 參考連結

- [Ollama 官方文件](https://docs.ollama.com/)
- [Ollama macOS 文件](https://docs.ollama.com/macos)
- [Ollama 下載頁面](https://ollama.com/download)
- [Ollama 模型搜尋](https://ollama.com/search)
