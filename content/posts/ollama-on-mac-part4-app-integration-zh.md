---
title: "ollama on mac - part 4 - 與應用整合(Python、OpenAI SDK、LangChain、Open WebUI、RAG)"
date: 2026-07-18T09:00:00+08:00
draft: false
description: "把本機 Ollama 模型接進真實應用的完整實戰:官方 Python/JS SDK、OpenAI 相容層、LangChain、Open WebUI,以及手把手打造一個離線可跑的本地 RAG。"
categories: ["engineering", "ai", "all"]
tags: ["Ollama", "LLM", "Python", "OpenAI API", "LangChain", "Open WebUI", "RAG", "Embeddings", "AI Engineering"]
authors: ["yen"]
readTime: "24 min"
---

> 很多人以為要用本地模型,就得把整個 app 打掉重寫、換掉所有 SDK。
> 於是遲遲不敢動手,繼續每個月付雲端 API 帳單。
> 事實上,對絕大多數既有專案而言,你只要改一行 `base_url`。
> **模型跑起來只是開始,把它接進你的應用,才是價值真正發生的地方。**

在 Part 1 我們把 Ollama 裝起來、跑了第一個模型;Part 2 挑了適合的公開模型;Part 3 玩了 REST API 與 Modelfile。到這裡,你手上已經有一個穩定跑在 `localhost:11434` 的本機推論服務。但一個孤立的模型沒有意義——真正的價值在於它成為你程式碼裡的一個函式呼叫、你 IDE 裡的自動補全、你知識庫上的問答引擎。

這一篇,我們把「整合」這件事講透。

---

## 一、整合的三條路:你其實只需要選一條

先建立心智模型。不管你用什麼語言、什麼框架,把本機模型接進應用永遠是這張圖:

```
┌──────────────────────────────────────────────────────────────┐
│                        你的應用程式                             │
│         (Web 後端 / CLI 腳本 / 桌面 App / Jupyter)              │
└───────────────┬───────────────┬───────────────┬───────────────┘
                │               │               │
        ┌───────▼──────┐ ┌──────▼───────┐ ┌─────▼────────┐
        │  路線 A       │ │  路線 B       │ │  路線 C       │
        │  官方 SDK     │ │  OpenAI 相容  │ │  框架 / App   │
        │  ollama-py   │ │  /v1/...     │ │  LangChain   │
        │  ollama-js   │ │  base_url    │ │  Open WebUI  │
        └───────┬──────┘ └──────┬───────┘ └─────┬────────┘
                │               │               │
                └───────────────┼───────────────┘
                                │  HTTP
                       ┌────────▼─────────┐
                       │  Ollama 服務      │
                       │  localhost:11434 │
                       └────────┬─────────┘
                                │
                       ┌────────▼─────────┐
                       │  本機模型         │
                       │  llama3.2 / ...  │
                       └──────────────────┘
```

三條路各有適用場景:

- **路線 A(官方 SDK)**:全新專案、想用 Ollama 特有功能(如原生 `ps`、`pull`、embed)、想要最乾淨的 API。
- **路線 B(OpenAI 相容層)**:你已經有一個用 OpenAI SDK 寫好的專案,想直接遷移到本機。**改 `base_url` 就好。**
- **路線 C(框架 / 現成 App)**:你要做複雜的 RAG / agent pipeline(用 LangChain),或只是想要一個聊天 UI(用 Open WebUI)、想在 IDE 裡寫程式(用 Continue)。

**關鍵洞察:這三條路底層都是打 `localhost:11434` 的 HTTP。** 選哪一條純粹取決於「你想要多少抽象層」,而不是能力差異。接下來逐一實戰。

---

## 二、官方 Python SDK 實戰

最直接的路。先裝:

```bash
pip install ollama
```

（前提:Ollama 服務已在跑。Part 1 教過,`ollama serve` 或 macOS 上開著 app 即可。模型也要先 `ollama pull llama3.2`。）

### 基本 chat

```python
import ollama

resp = ollama.chat(
    model='llama3.2',
    messages=[{'role': 'user', 'content': '用一句話解釋什麼是向量資料庫'}],
)
print(resp['message']['content'])
```

回傳是一個 dict,內容在 `resp['message']['content']`。多輪對話就把歷史訊息一路塞進 `messages` 陣列——**Ollama 本身是無狀態的,對話歷史由你的應用維護**。

### generate:單次文字生成

當你不需要「對話角色」概念,只想給一段 prompt 拿一段輸出(例如摘要、翻譯、分類),用 `generate` 更直覺:

```python
import ollama

resp = ollama.generate(model='llama3.2', prompt='把這句翻成英文:今天天氣很好')
print(resp['response'])   # 注意:generate 的結果在 'response' 鍵
```

### streaming:逐字輸出(必學)

沒有 streaming 的本地 LLM 體驗很糟——使用者要盯著空白畫面等好幾秒。加上 `stream=True`,回傳就變成一個 generator,逐塊 (chunk) 吐出:

```python
import ollama

stream = ollama.chat(
    model='llama3.2',
    messages=[{'role': 'user', 'content': '寫一首關於秋天的短詩'}],
    stream=True,
)

for chunk in stream:
    print(chunk['message']['content'], end='', flush=True)
print()  # 收尾換行
```

`end=''` 讓片段接在一起,`flush=True` 強制即時刷新到終端。**這幾行是所有本地 CLI 工具的標準寫法,背下來。**

### 管理類 API:list / ps / pull

SDK 不只做推論,還能管模型——這是相容層做不到的 Ollama 專屬能力:

```python
import ollama

# 列出本機已下載的模型
for m in ollama.list()['models']:
    print(m['model'])

# 看目前載入到記憶體的模型(對應 CLI 的 ollama ps)
print(ollama.ps())

# 用程式碼下載模型(第一次跑腳本可自動備妥)
ollama.pull('llama3.2')
```

`ollama.pull()` 在部署腳本或 Docker entrypoint 裡特別好用:**啟動時自動確保模型存在**,不用人工先 pull。

### Client:連到自訂 host

預設連 `localhost:11434`。如果 Ollama 跑在別台機器(例如你有一台 Mac Studio 當推論伺服器),用 `Client`:

```python
from ollama import Client

client = Client(host='http://192.168.1.50:11434')
resp = client.chat(model='llama3.2', messages=[{'role': 'user', 'content': 'Hi'}])
print(resp['message']['content'])
```

（要讓 Ollama 對外服務,得設 `OLLAMA_HOST=0.0.0.0`,這在 Part 5 進階部署會細講。）

### AsyncClient:高併發場景

如果你在寫 async 的 Web 後端(FastAPI、aiohttp),用 `AsyncClient` 避免阻塞事件迴圈:

```python
import asyncio
from ollama import AsyncClient

async def main():
    client = AsyncClient()
    resp = await client.chat(
        model='llama3.2',
        messages=[{'role': 'user', 'content': '一句話介紹 async 的好處'}],
    )
    print(resp['message']['content'])

    # async streaming
    async for chunk in await client.chat(
        model='llama3.2',
        messages=[{'role': 'user', 'content': '數到五'}],
        stream=True,
    ):
        print(chunk['message']['content'], end='', flush=True)
    print()

asyncio.run(main())
```

**takeaway:同步腳本用 `ollama.chat`,Web 服務用 `AsyncClient`,需要跨機器用 `Client(host=...)`。**

---

## 三、官方 JavaScript SDK

前端工程師、寫 Node 後端、或做 Electron 桌面 App 的人,用 JS SDK。

```bash
npm install ollama
```

### 基本 chat(Node)

```js
import ollama from 'ollama'

const res = await ollama.chat({
  model: 'llama3.2',
  messages: [{ role: 'user', content: '用一句話解釋 event loop' }],
})

console.log(res.message.content)
```

注意 JS 版的回傳是物件屬性 `res.message.content`(不是 Python 的 dict 索引)。

### streaming(Node)

```js
import ollama from 'ollama'

const stream = await ollama.chat({
  model: 'llama3.2',
  messages: [{ role: 'user', content: '寫三個學 JS 的理由' }],
  stream: true,
})

for await (const chunk of stream) {
  process.stdout.write(chunk.message.content)
}
process.stdout.write('\n')
```

`for await...of` 對應 Python 的 async generator,`process.stdout.write` 對應 `print(end='')`。

**何時用 JS?** 當你的整合點就在 JS 生態:Next.js API route、Electron 主行程、VS Code extension、瀏覽器擴充。**若只是資料處理、RAG、機器學習相關,Python 生態(numpy、LangChain、向量庫)成熟得多,建議用 Python。**

---

## 四、OpenAI 相容層(本篇最重要一節)

這是讓「遷移零痛苦」成真的魔法。Ollama 內建一個 **OpenAI 相容的 HTTP 端點**,長得跟 OpenAI 官方 API 一模一樣:

- Base URL: `http://localhost:11434/v1/`
- API key: **任意非空字串**(會被忽略,慣例填 `"ollama"`)
- 端點:`/v1/chat/completions`、`/v1/completions`、`/v1/embeddings`、`/v1/models`

### 為什麼「改 base_url 就能接」

OpenAI 的 Python SDK(`openai` 套件)本質上只是一個 HTTP client,它把請求送到 `client.base_url`。這個值預設是 `https://api.openai.com/v1`。**你把它改成 `http://localhost:11434/v1`,同一份程式碼就打到本機 Ollama 了。** 請求格式相容,回傳格式也相容,上層邏輯一行都不用動。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",   # 非空即可,內容被忽略
)

r = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "Hi"}],
)
print(r.choices[0].message.content)
```

**這意味著:任何『會講 OpenAI API』的工具或函式庫——LlamaIndex、Vercel AI SDK、各種 agent 框架、你三年前寫的舊專案——都能靠改 `base_url` + `api_key` 指向 Ollama,完全不改其他程式碼。** 這是 Ollama 整合生態最強大的一點。

### streaming(相容層)

streaming 也完全比照 OpenAI 寫法:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

stream = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "數到十"}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:                      # 最後一塊 delta 可能是 None
        print(delta, end="", flush=True)
print()
```

注意 `chunk.choices[0].delta.content` 這個路徑,以及要判斷 `None`——這是 OpenAI streaming 的標準結構,一字不差搬過來即可。

### embeddings(相容層)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

resp = client.embeddings.create(
    model="nomic-embed-text",
    input="向量檢索的核心是相似度計算",
)
vec = resp.data[0].embedding
print(len(vec))   # nomic-embed-text 是 768 維
```

### 支援 / 不支援功能一覽

相容不代表 100% 對等。實務上你會踩到的差異整理如下:

| 功能 | 相容層是否支援 | 備註 |
|------|:---:|------|
| `/v1/chat/completions` | ✅ | 主力端點,對話用 |
| `/v1/completions` | ✅ | 舊式單次補全 |
| `/v1/embeddings` | ✅ | 需用 embed 模型如 nomic-embed-text |
| `/v1/models` | ✅ | 列出本機模型 |
| streaming | ✅ | `stream=True` 標準運作 |
| JSON mode | ✅ | `response_format={"type":"json_object"}` |
| tool calling(工具呼叫) | ✅ | 視模型而定,Part 5 深講 |
| vision(圖片 base64) | ✅ | 需視覺模型如 llava |
| `logprobs` | ❌ | 不支援 |
| `logit_bias` | ❌ | 不支援 |
| `n`(一次多個候選) | ❌ | 不支援,只回一個 |
| `tool_choice` | ⚠️ | 部分支援,行為與雲端不完全一致 |

**takeaway:對話、streaming、embeddings、JSON mode、工具呼叫這些主流功能都能無痛遷移;會出問題的是 `logprobs`、`n`、`logit_bias` 這類進階取樣參數。遷移前先確認你有沒有用到它們。**

### 實務:把現有 OpenAI 專案遷到 Ollama

最漂亮的作法是用環境變數,讓同一份程式碼在雲端 / 本機之間切換:

```python
import os
from openai import OpenAI

# 本機:export OPENAI_BASE_URL=http://localhost:11434/v1 ; export OPENAI_API_KEY=ollama
# 雲端:export OPENAI_BASE_URL=https://api.openai.com/v1 ; export OPENAI_API_KEY=sk-...
client = OpenAI(
    base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.environ.get("OPENAI_API_KEY", "ollama"),
)

MODEL = os.environ.get("LLM_MODEL", "llama3.2")

r = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "測試"}],
)
print(r.choices[0].message.content)
```

**開發用本機模型(免費、離線、隱私),上線切雲端(能力更強)——只換環境變數,程式碼零改動。** 這是很多團隊的實際做法。

---

## 五、LangChain 整合

當你的需求超出「單次問答」,進入「多步驟 pipeline、記憶、檢索、agent」時,LangChain 提供結構化的抽象。Ollama 有官方整合套件:

```bash
pip install langchain-ollama
```

三個核心類別:

```python
from langchain_ollama import ChatOllama, OllamaEmbeddings, OllamaLLM

llm = ChatOllama(model="llama3.2", temperature=0)   # 對話模型
embeddings = OllamaEmbeddings(model="nomic-embed-text")  # 向量化
```

### 一個小 chain:prompt → llm → 輸出

LangChain 的精髓是用 `|` 把元件串成 pipeline(LCEL 語法):

```python
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

llm = ChatOllama(model="llama3.2", temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一個專業的技術翻譯,只輸出翻譯結果,不要解釋。"),
    ("user", "把這句翻成英文:{text}"),
])

# prompt 填值 → 丟給 llm → 把回應物件轉成純字串
chain = prompt | llm | StrOutputParser()

result = chain.invoke({"text": "本地模型讓資料不出你的機器"})
print(result)
```

`chain.stream({...})` 也支援 streaming,寫法與前面一致。**LangChain 的價值在於:當你要接向量庫、加對話記憶、串多個模型時,這套 `|` 組合語法能讓 pipeline 保持清晰。** 但若只是簡單呼叫,直接用官方 SDK 更輕。

---

## 六、動手做一個本機 RAG(重頭戲)

RAG(Retrieval-Augmented Generation,檢索增強生成)是本地模型最實用的應用:**讓模型根據你自己的文件回答問題**,不靠它的內建知識、不會亂編。而且全程在本機跑,你的文件一個 byte 都不外流。

### RAG 流程

```
   ┌──────────────┐
   │  你的文件      │  (筆記 / 手冊 / PDF 文字)
   └──────┬───────┘
          │ 1. 切塊 (chunking)
          ▼
   ┌──────────────┐
   │  文字片段      │  chunk 1, chunk 2, ... chunk N
   └──────┬───────┘
          │ 2. embed (nomic-embed-text)
          ▼
   ┌──────────────┐        ┌───────────────────────────┐
   │  向量庫        │◀───────│  索引階段 (只做一次)         │
   │  [vec1..vecN] │        └───────────────────────────┘
   └──────┬───────┘
          │
   ══════════════════════ 以下是查詢階段 (每次提問) ══════════════════════
          │
   ┌──────▼───────┐  3. 使用者提問
   │  Query 文字   │──────┐
   └──────────────┘      │ 4. embed (同一個模型!)
                         ▼
                  ┌──────────────┐
                  │  Query 向量   │
                  └──────┬───────┘
                         │ 5. cosine 相似度比對
                         ▼
                  ┌──────────────┐
                  │  取 top-k     │  最相關的 k 個 chunk
                  └──────┬───────┘
                         │ 6. 塞進 prompt(當作 context)
                         ▼
                  ┌──────────────┐
                  │  llama3.2    │  7. 依據 context 生成答案
                  └──────┬───────┘
                         ▼
                     最終答案
```

### 完整可跑的 Python

以下用 `ollama.embed` 做向量化、用 `numpy` 手算 cosine 相似度、用 `ollama.chat` 生成。**刻意不引入重量級向量庫,讓你看清 RAG 的原理骨架**——它其實沒有你想的那麼玄。

```python
import ollama
import numpy as np

EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "llama3.2"

# ── 0. 準備知識庫(真實情境:從檔案讀入後切塊) ──
documents = [
    "Ollama 的預設服務埠是 11434。",
    "nomic-embed-text 輸出的向量是 768 維,且已做 L2 正規化。",
    "要讓對話有記憶,必須由應用自己維護 messages 歷史,Ollama 本身無狀態。",
    "OpenAI 相容端點的 base_url 是 http://localhost:11434/v1,api_key 填任意非空字串。",
    "Open WebUI 預設跑在 3000 埠,透過 Docker 部署最方便。",
]

# ── 1 & 2. 索引階段:把每個 chunk embed 成向量 ──
def embed(text: str) -> np.ndarray:
    resp = ollama.embed(model=EMBED_MODEL, input=text)
    return np.array(resp["embeddings"][0], dtype=np.float32)

doc_vectors = np.vstack([embed(d) for d in documents])   # shape: (N, 768)

# ── 5. cosine 相似度(向量已 L2 正規化,點積即 cosine) ──
def cosine_topk(query_vec: np.ndarray, matrix: np.ndarray, k: int = 2):
    # 保險起見再正規化一次,避免模型輸出未正規化
    q = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)
    scores = m @ q                       # 每個 doc 與 query 的相似度
    top_idx = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_idx]

# ── 查詢階段 ──
def rag_answer(question: str, k: int = 2) -> str:
    # 3 & 4. 把問題 embed(務必用同一個 EMBED_MODEL!)
    q_vec = embed(question)

    # 5 & 6. 取最相關的 k 個 chunk 當 context
    hits = cosine_topk(q_vec, doc_vectors, k=k)
    context = "\n".join(f"- {documents[i]}" for i, _ in hits)

    # 7. 把 context 塞進 prompt,要求模型只依據它回答
    prompt = f"""請只根據以下資料回答問題,若資料中沒有答案,就說「資料中沒有相關資訊」。

參考資料:
{context}

問題:{question}"""

    resp = ollama.chat(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp["message"]["content"]

if __name__ == "__main__":
    print(rag_answer("Ollama 服務跑在哪個埠?"))
    print("---")
    print(rag_answer("Open WebUI 用哪個埠?"))
```

跑起來,第一題會抓到「11434」那條 chunk,第二題會抓到「3000」那條——**模型不是憑記憶回答,而是依據你餵的文件回答**。這就是 RAG 消除幻覺的機制。

### 兩個必記重點

1. **index 與 query 一定要用同一個 embedding 模型。** 不同模型產生的向量空間不相容,cosine 相似度會變成亂數。這是新手最常見、最難 debug 的錯誤。
2. **這個 numpy 版本只是教學骨架。** 當文件量從幾十條長到上萬條,線性掃描太慢。這時把 `doc_vectors` + `cosine_topk` 換成專門的向量庫——**Chroma(輕量、內嵌好裝)或 FAISS(高效能)**——它們用 ANN 索引把檢索加速幾個數量級。但原理跟上面一模一樣:embed → 存 → 查相似度 → top-k。

**takeaway:RAG 的本質就是「用相似度找出相關片段,塞進 prompt」。搞懂 numpy 版,你就搞懂了所有向量庫在做什麼。**

---

## 七、現成 App:Open WebUI 與其他 GUI

不想寫程式,只想要一個像 ChatGPT 的網頁介面?**Open WebUI** 是最受歡迎的自架方案,功能齊全(對話歷史、多模型切換、RAG 上傳文件、使用者管理)。

### 用 Docker 裝(推薦)

```bash
docker run -d -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

然後打開瀏覽器到 **http://localhost:3000**。它會自動偵測跑在 `host.docker.internal:11434` 的 Ollama。

幾個參數解釋:
- `-p 3000:8080`:把容器的 8080 對外映射到你機器的 3000 埠。
- `--add-host=host.docker.internal:host-gateway`:**這行是關鍵**。容器內的 `localhost` 是容器自己,不是你的 Mac。這個參數讓容器能透過 `host.docker.internal` 連回宿主機上的 Ollama。
- `-v open-webui:/app/backend/data`:用 volume 保存對話歷史,容器重建不丟資料。

### 用 pip 裝(不想碰 Docker)

```bash
pip install open-webui
open-webui serve
```

一樣開 http://localhost:3000。pip 版直接跑在你機器上,`localhost:11434` 就能連到 Ollama,不需要 `host.docker.internal` 那套。

### 其他 GUI 選擇

- **Enchanted**:macOS 原生 App,介面精緻,支援 iOS,適合只想要純本機聊天體驗的人。
- **Msty**:跨平台桌面 App,開箱即用,內建模型下載與 RAG,對非工程師友善。
- **LM Studio 風格的客戶端**:一堆桌面 client 都能連 Ollama 或走 OpenAI 相容層。

**takeaway:要團隊共用、要 RAG、要 Web 存取 → Open WebUI;只要個人本機聊天、要最輕 → Enchanted / Msty。**

---

## 八、編輯器 / 開發整合:在 IDE 裡用本機模型寫程式

把本機模型接進 IDE,你就有了一個**離線、免費、程式碼不外流**的 AI 助手。

### VS Code + Continue

[Continue](https://www.continue.dev/) 是最成熟的開源 AI coding 擴充。裝好擴充後,在它的設定裡把 model provider 指向 `ollama`:

```json
{
  "models": [
    {
      "title": "Llama 3.2 (local)",
      "provider": "ollama",
      "model": "llama3.2"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Autocomplete",
    "provider": "ollama",
    "model": "qwen2.5-coder:1.5b"
  }
}
```

**對話用大一點的模型、自動補全用小而快的模型**(補全對延遲極敏感,1.5b 這種小模型才跟得上打字速度)。

### ollama launch

Ollama 也提供 `ollama launch` 協助設定 Claude Code / VS Code 等工具接上本機模型,省去手動填設定的功夫。

### 隱私 vs 能力的取捨

在 IDE 用本機模型,核心是一筆權衡:

- **隱私 / 成本 / 離線贏面**:程式碼永遠不離開你的機器(對受規範的產業、機密專案是硬需求),沒有 API 費用,飛機上也能用。
- **能力輸面**:本機能跑的模型(7B–14B 為主)在複雜重構、跨檔案推理上,仍不如頂級雲端模型。

**務實建議:日常補全、樣板、小函式、regex、解釋程式碼——本機模型完全夠用,體驗又快又免費;真正燒腦的架構級任務,再切雲端。** 兩者不衝突,Continue 可以同時配置多個 provider,隨時切換。

---

## 九、整合選型:情境 → 建議方式

一張表收斂前面所有選擇:

| 你的情境 | 建議整合方式 | 為什麼 |
|---------|------------|-------|
| 寫個快速腳本 / 自動化任務 | 官方 SDK(`ollama` / `ollama-js`) | API 最乾淨,還能用 pull/ps 等專屬功能 |
| 已有 OpenAI 專案要遷本機 | OpenAI 相容層(改 `base_url`) | 幾乎零改動,一行搞定 |
| 前端 / Node / Electron | 官方 JS SDK | 貼合 JS 生態 |
| 複雜 RAG / agent / 多步 pipeline | LangChain(`langchain-ollama`) | 結構化組合,好接向量庫與記憶 |
| 要客製 RAG 又想懂原理 | 官方 SDK + numpy / Chroma | 完全掌控檢索邏輯 |
| 只想要聊天 UI(團隊共用) | Open WebUI | 功能全、自架、支援多人 |
| 個人本機聊天(最輕) | Enchanted / Msty | 原生 App,開箱即用 |
| 在 IDE 寫程式 | VS Code + Continue | 補全 / 對話都指向本機 |

**takeaway:沒有「最好」的整合方式,只有「最貼合你場景」的。既有專案優先走相容層,新專案優先走官方 SDK,要 pipeline 才上 LangChain。**

---

## 十、常見整合陷阱:症狀 → 解法

這些坑幾乎每個人都會踩一次,提前記住省下好幾小時 debug:

| 症狀 | 原因 | 解法 |
|------|------|------|
| 相容層報 404 / 路徑錯誤 | `base_url` 尾斜線或缺 `/v1` | 用 `http://localhost:11434/v1`,不要重複斜線 |
| 相容層報 401 / 認證失敗 | `api_key` 傳了空字串 | 填任意非空字串,如 `"ollama"` |
| `model not found` | 模型還沒下載 | 先 `ollama pull llama3.2`,或程式裡 `ollama.pull()` |
| Connection refused | Ollama 服務沒跑 | 確認 `ollama serve` 或 macOS app 開著,`curl localhost:11434` 測 |
| streaming 只拿到片段 / 卡住 | 沒逐 chunk 處理,或忘了 flush | 用 `for chunk in stream` 逐塊處理,`flush=True` |
| Docker 容器連不到 Ollama | 容器內 `localhost` 是容器自己 | 加 `--add-host=host.docker.internal:host-gateway`,連 `host.docker.internal:11434` |
| 瀏覽器前端呼叫被擋(CORS) | 跨來源請求被拒 | 設 `OLLAMA_ORIGINS` 允許來源,或後端代理 |
| 長文丟進去記憶體爆掉 / 變超慢 | context 超過模型上限或機器 RAM | 縮短 context、RAG 只塞 top-k、選 context window 較大的模型 |
| RAG 檢索結果像亂數 | index 與 query 用了不同 embedding 模型 | 兩端統一用同一個 embed 模型 |

**最容易忽略的兩個:`base_url` 的 `/v1` 與尾斜線、以及 RAG 的「同一個 embedding 模型」。** 這兩個錯誤不會噴 exception,只會給你安靜的錯誤結果,最難查。

---

## 十一、小結

這一篇我們把「本機模型 → 真實應用」的整條路走完:

- **三條整合路**:官方 SDK、OpenAI 相容層、框架/現成 App——底層都是打 `localhost:11434`。
- **官方 Python SDK**:chat / generate / streaming / list / ps / pull / Client / AsyncClient 全套。
- **OpenAI 相容層**:改一行 `base_url` + 非空 `api_key`,既有 OpenAI 專案零痛苦遷移。
- **LangChain**:複雜 pipeline 的結構化組合。
- **本機 RAG**:embed → cosine → top-k → 塞 prompt → 生成,用 numpy 看清原理,量大再換 Chroma/FAISS。
- **現成 App / IDE**:Open WebUI 給你聊天 UI,Continue 給你離線 coding 助手。

你現在有能力把本機模型接進任何應用了。但目前的模型還只是「回答問題」——**下一步,是讓它主動呼叫工具、查資料、執行動作,變成真正的 agent。**

Part 5 我們進入進階實踐:**工具呼叫(tool/function calling)、多模型服務、以及生產級部署的調校**。這是把 Ollama 從「玩具」變成「基礎設施」的最後一哩路。

---

## 系列導覽

- Part 1 — [安裝與第一個本地模型](../ollama-on-mac-part1-installation-zh/)
- Part 2 — [公開模型全覽與選型指南](../ollama-on-mac-part2-public-models-zh/)
- Part 3 — [REST API 與自訂 Modelfile](../ollama-on-mac-part3-api-modelfile-zh/)
- **Part 4 — 與應用整合(本篇)**
- Part 5 — [工具呼叫、多模型服務與進階實踐](../ollama-on-mac-part5-advanced-zh/)

## 參考連結

- Ollama 官方文件:https://docs.ollama.com/
- OpenAI 相容性說明:https://docs.ollama.com/api/openai-compatibility
- Ollama Python SDK:https://github.com/ollama/ollama-python
- Open WebUI:https://github.com/open-webui/open-webui
