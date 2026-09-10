---
title: "RAGFlow Intro Part 2 — 資料進場 — DeepDoc 解析、Chunking 策略與 14 種模板"
date: 2026-09-10T10:00:00+08:00
draft: false
weight: 2
description: "RAGFlow 原始碼導讀系列第二篇：拆解 DeepDoc 的 OCR／版面辨識／表格結構辨識三層視覺管線、五條解析後端路線、14 種 chunk 模板各自的結構假設，以及 naive_merge 的切分契約與 chunk 加值管線的真實成本。"
categories: ["all", "ai", "engineering"]
tags: ["RAGFlow", "RAG", "AI", "DeepDoc", "OCR", "Chunking", "Document Parsing", "繁體中文"]
authors: ["yen"]
readTime: "26 min"
---

> *大多數人處理 RAG 的文件解析，是 `PyPDF2.extract_text()` 加一個 `RecursiveCharacterTextSplitter(512, 50)`，然後把精力全部投在 prompt 上。*
> *真正的答案是：如果 chunk 是壞的，prompt 再怎麼調都是在補救；而 chunk 的品質，在解析那一步就已經決定了 80%。*
> *「Quality in, quality out」不是口號，它是一個工程順序的宣告。*
> *這篇文章拆的就是 RAGFlow 的「in」。*

---

## 前言

[Part 1](../ragflow-intro-part1-overview-architecture-zh) 畫完了 RAGFlow 的全景圖。本篇下鑽到 ingestion 路徑的前半段——**從一個二進位檔案，到一組準備好被編碼的 chunk**。

這一段對應兩個目錄：

```
deepdoc/          「這份文件長什麼樣子」  ← 視覺與格式理解
├── vision/       OCR / 版面辨識 / 表格結構辨識（ONNX 模型）
└── parser/       19 個格式解析器 + 外部解析後端接入

rag/app/          「這份文件該怎麼切」    ← 14 種切分模板
rag/nlp/          切分契約與分詞（__init__.py 68 KB，delim.py，rag_tokenizer.py）
```

順序很重要：**先理解版面，再決定切法。** 反過來就是 naive RAG。

---

## 一、核心問題：為什麼「抽文字」不等於「解析」

先看一個具體的失敗案例。一份雙欄排版的論文 PDF，用純文字抽取會得到：

```
Abstract  1. Introduction        ← 兩欄的標題被讀成同一行
We propose a novel  Recent work  ← 左欄句子 + 右欄句子黏在一起
method for  in retrieval-augment
document  ed generation has
understanding.  shown that ...
```

這串文字不管怎麼切，都不會產生一個可用的 chunk。**問題不在切分器，在於輸入已經沒有結構了。**

再看一份財報的表格。純文字抽取得到：

```
2024 2025 營收 1,234 1,567 毛利 456 623 毛利率 37% 39.8%
```

LLM 看到這串，回答「2025 年毛利率」時有相當機率答成 37%。**表格的行列關係在抽文字的那一刻就消失了。**

RAGFlow 的答案是：**把文件當圖片看。** `deepdoc/README.md` 的第一句話是 "We use vision information to resolve problems as human being."——人類讀文件時是先看版面、再讀內容，機器也應該如此。

這帶來一個必然的架構後果：**解析階段需要跑模型，因此需要 CPU/GPU 資源，因此必須是非同步任務。** 這就是為什麼 RAGFlow 一定要有 Task Executor 和佇列，而不能在 API 請求裡同步解析。

---

## 二、DeepDoc 的三層視覺管線

`deepdoc/vision/` 有三個 ONNX 模型，構成一條流水線：

```
      一頁 PDF（render 成圖片）
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ ① OCR（det.onnx + rec.onnx）                                │
│    文字偵測：找出所有文字框（bbox）                          │
│    文字辨識：每個框裡的字是什麼 + confidence                 │
│    → [(bbox, text, score), ...]                             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ ② Layout Recognition（layout.onnx）                         │
│    把頁面切成 10 種語意區塊：                                │
│      Text / Title / Figure / Figure caption /               │
│      Table / Table caption / Header / Footer /              │
│      Reference / Equation                                    │
│    → 決定「哪些文字是連續的」「哪塊要交給 TSR」               │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ ③ TSR — Table Structure Recognition（tsr.onnx）             │
│    只對 layout 判定為 Table 的區域執行，辨識 5 種結構標籤：   │
│      Column / Row / Column header /                         │
│      Projected row header / Spanning cell                   │
│    → 把表格重組成「LLM 讀得懂的句子」                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
        帶版面座標與型別標記的 sections
        （page_num_int / top_int / position_int）
```

三層各自解決一個具體問題：

**OCR 解決「文字在不在」。** 掃描件、截圖、拍照的合約，沒有 OCR 就是零。RAGFlow 的 OCR 輸出帶 confidence，這個分數後面還有妙用（見下方自動旋轉）。

**Layout 解決「文字順序對不對」。** 這是雙欄論文問題的解答：知道左欄是一個 Text 區塊、右欄是另一個，就能正確地把兩欄分開讀。同時，`Header`、`Footer`、`Reference` 被辨識出來之後可以直接丟掉——**頁眉頁腳如果進了 chunk，每個 chunk 都會被同一段雜訊污染。**

**TSR 解決「表格關係在不在」。** README 特別提到 TSR 的輸出不是 HTML 就結束，而是 "we also reassemble the content into sentences which could be well comprehended by LLM"。也就是說，`毛利率 | 37% | 39.8%` 這一列會被重組成帶表頭的敘述，讓 LLM 不需要自己推斷欄位對應。

### 2.1 一個很聰明的小設計：表格自動旋轉

掃描件裡的表格經常是橫放的（旋轉 90°/180°/270°）。RAGFlow 的處理方式不是訓一個角度分類器，而是：

```
對表格區域，分別以 0° / 90° / 180° / 270° 執行 OCR
      │
      ▼
比較四次的 OCR confidence 平均分
      │
      ▼
選最高分的角度 → 以該角度重跑 OCR → 再做 TSR
```

**用 OCR 自己的信心分數當旋轉偵測器**，不需要額外模型。代價是同一塊區域要 OCR 四次，所以它有開關：`TABLE_AUTO_ROTATE=false`（預設 `true`）。

這是一個典型的工程折衷：**四倍計算換一個不用維護的模型。** 在表格佔比不高的文件上，成本可忽略；如果你的資料集是「一萬份掃描表格」，這個開關值得關掉並改用專用模型。

### 2.2 模型格式：`.onnx` 與 `.ort` 並存

一個容易踩的細節。RAGFlow 正在做 Go 遷移（Part 5 詳談），而 Go 的 in-process DeepDoc backend 載入的是 **`.ort`（FlatBuffer）**，Python 側載入的是 **`.onnx`**：

| | Go（in-process） | Python |
|---|---|---|
| 格式 | `.ort` | `.onnx` |
| 檔案 | `det.ort`、`layout.ort`、`tsr.ort`、`rec.ort`、`ocr.res` | `det.onnx`、`layout.onnx`、`tsr.onnx`、`rec.onnx`、`ocr.res` |
| 下載腳本 | `ragflow_deps/download_go_deps.py` | `ragflow_deps/download_deps.py` |

`internal/development.md` 特別警告：**兩種格式並存於 `rag/res/deepdoc/`，不要為了「清理」刪掉其中一種。** 而且如果目錄裡只有 `.onnx`，Go server 啟動時會直接 fatal：`no in-process DeepDoc backend serving`——目錄看起來滿的，但 Go 後端拿不到它要的權重。

---

## 三、五條解析後端路線

DeepDoc 不是唯一選擇。`rag/app/naive.py` 用一個 `layout_recognize` 參數決定走哪條路：

```python
raw_layout_recognize = parser_config.get("layout_recognize", "DeepDOC")
```

```
                        parser_config["layout_recognize"]
                                    │
        ┌───────────┬───────────────┼───────────────┬──────────────┐
        ▼           ▼               ▼               ▼              ▼
  ┌──────────┐ ┌──────────┐  ┌───────────┐   ┌──────────┐   ┌───────────┐
  │ DeepDOC  │ │ Plain    │  │  MinerU   │   │ Docling  │   │  VLM      │
  │ （預設）  │ │ Text     │  │           │   │          │   │ (視覺模型) │
  ├──────────┤ ├──────────┤  ├───────────┤   ├──────────┤   ├───────────┤
  │ 本地 ONNX│ │ 只抽文字 │  │ 外部服務  │   │ 外部服務 │   │ 每頁一次   │
  │ 成本≈0   │ │ 最快     │  │ 學術文件  │   │ IBM 開源 │   │ 多模態呼叫 │
  │ 版面+表格│ │ 無結構   │  │ 公式強    │   │ 結構完整 │   │ 品質上限高 │
  └──────────┘ └──────────┘  └───────────┘   └──────────┘   └───────────┘
```

除了這五條，`deepdoc/parser/` 裡還接了一整排第三方解析器：`mineru_parser.py`、`docling_parser.py`、`mistral_parser.py`、`monkeyocrv2_parser.py`、`paddleocr_parser.py`、`somark_parser.py`、`tcadp_parser.py`、`opendataloader_parser.py`。**這是一個明確的架構訊號：RAGFlow 不打算在「誰的 OCR 最準」這件事上打贏所有人，它打算成為那個可以插任何解析器的框架。**

原生格式解析器則是老老實實一個一個寫：`pdf_parser.py`、`docx_parser.py`、`excel_parser.py`、`ppt_parser.py`、`html_parser.py`、`markdown_parser.py`、`json_parser.py`、`txt_parser.py`、`epub_parser.py`、`figure_parser.py`，加上 `parser/resume/` 一整個子模組。

### 3.1 選哪一條？

| 情境 | 建議 | 理由 |
|---|---|---|
| 一般企業文件（Word / 一般 PDF / PPT） | **DeepDOC** | 成本可預測，表格處理夠好 |
| 純文字 / Markdown / 程式碼文件 | **Plain Text** | 沒有版面可辨識，跑模型是浪費 |
| 學術論文（大量公式） | **MinerU** | 公式與參考文獻處理明顯較好 |
| 版面極端複雜、量不大 | **VLM** | 品質上限最高，成本按頁計 |
| 已有自家 OCR 服務 | 寫一個 parser | `deepdoc/parser/` 就是給人插隊的 |

**VLM 路線的成本要算清楚。** 一份 300 頁的 PDF，若每頁都走多模態模型，就是 300 次 vision 呼叫。以常見的 vision 模型定價，單份文件的解析成本可能落在 0.3～1.5 美元；一萬份就是四位數美金。DeepDOC 走本地 ONNX，同樣一萬份的邊際成本只有 CPU 時間。

---

## 四、14 種 Chunk 模板

解析完得到 sections，接下來要切。RAGFlow 不提供「一個」切分器，而是 14 個。`rag/svr/task_executor.py` 開頭那張表就是註冊中心：

```python
FACTORY = {
    "general": naive,
    ParserType.NAIVE.value: naive,          # naive
    ParserType.PAPER.value: paper,          # paper
    ParserType.BOOK.value: book,            # book
    ParserType.PRESENTATION.value: presentation,
    ParserType.MANUAL.value: manual,
    ParserType.LAWS.value: laws,
    ParserType.QA.value: qa,
    ParserType.TABLE.value: table,
    ParserType.RESUME.value: resume,
    ParserType.PICTURE.value: picture,
    ParserType.ONE.value: one,
    ParserType.AUDIO.value: audio,
    ParserType.EMAIL.value: email,
    ParserType.KG.value: naive,             # knowledge_graph 復用 naive
    ParserType.TAG.value: tag,
}
```

每個模板的核心是**一組關於文件結構的假設**。選錯模板，等於用錯誤的假設切分。

| 模板 | 檔案（大小） | 結構假設 | 適用 |
|---|---|---|---|
| `naive` | `naive.py`（63 KB） | 無特殊結構，靠分隔符 + token 上限 | 通用預設 |
| `paper` | `paper.py`（14 KB） | 有 Abstract / Sections / References 的學術結構 | 論文 |
| `book` | `book.py`（9 KB） | 章節層級 + 目錄 | 書籍、長篇報告 |
| `presentation` | `presentation.py`（10 KB） | **一頁一 chunk**，每頁附縮圖 | PPT / Keynote |
| `manual` | `manual.py`（14 KB） | 層級標題（1. / 1.1 / 1.1.1）為切分邊界 | 產品手冊、SOP |
| `laws` | `laws.py`（10 KB） | 條 / 款 / 項的編號體系 | 法規、合約 |
| `qa` | `qa.py`（19 KB） | 問答成對出現，**Q 進 `question_kwd`，A 進內容** | FAQ、客服知識庫 |
| `table` | `table.py`（28 KB） | 每列一筆記錄 + 表頭是欄位名 | Excel、CSV、資料表 |
| `resume` | `resume.py`（**116 KB**） | 姓名/學歷/經歷/技能的欄位抽取 | 履歷 |
| `picture` | `picture.py`（8 KB） | 圖片走 OCR 或 vision 模型描述 | 圖檔 |
| `one` | `one.py`（8 KB） | **整份文件一個 chunk**，不切 | 短文件、需要完整上下文 |
| `audio` | `audio.py`（3 KB） | 走 ASR 轉文字後再切 | 錄音、會議記錄 |
| `email` | `email.py`（5 KB） | 標頭（寄件者/主旨/日期）+ 正文 + 附件分開 | 郵件匯出 |
| `tag` | `tag.py`（6 KB） | **不產生檢索用 chunk**，而是產生標籤庫 | 標籤知識庫 |

三個值得特別講的：

### 4.1 `resume.py` 為什麼有 116 KB

因為履歷解析本質上是**實體抽取 + 正規化**，不是切分。它要處理：「台大」和「國立臺灣大學」是同一所學校、「2020.3-2022.7」和「2020年3月至2022年7月」是同一段期間、姓氏辨識（`rag/nlp/surname.py` 有 9 KB 的姓氏表）。

這 116 KB 大部分是**規則與詞表**，不是邏輯。它是整個 repo 裡最「不 AI」也最實用的一段程式碼——**在一個明確且窄的領域裡，規則的 ROI 遠高於模型。**

### 4.2 `tag` 模板：不產生 chunk 的 chunk 模板

`tag` 模板做的事是：讀一份「標籤定義文件」，把它變成一個標籤庫。之後其他文件在 ingestion 時，`content_tagging` 步驟會用這個標籤庫給 chunk 打標籤，寫進 `tag_feas` 欄位（型別是 `rank_features`）。

檢索時，`_tag_feature_scores()` 會計算「查詢的標籤向量」與「chunk 的標籤向量」的 cosine，**乘以 10 之後加進最終分數**。這是一個很輕量的領域知識注入機制：不用微調 embedding 模型，用標籤共現就能把領域先驗塞進排序。

### 4.3 `one` 模板存在的理由

「整份文件一個 chunk」聽起來像是放棄 RAG。但在兩個場景是最優解：

- **短文件**（一頁的公告、一則規則）：切了只會製造碎片，讓上下文不完整
- **需要全局理解的文件**（一份簡短合約）：任何切分都會讓 LLM 看不到條款之間的關係

現代長上下文模型讓 `one` 模板的適用範圍變大了。**當單份文件 < 8K token 且文件總數不多時，`one` + 直接全塞的效果往往勝過任何切分策略。**

---

## 五、`naive_merge`：切分契約

`naive` 是預設模板，也是理解 RAGFlow 切分哲學的關鍵。它的核心函式在 `rag/nlp/__init__.py`：

```python
def naive_merge(sections, chunk_token_num=128,
                delimiter=DEFAULT_DELIMITER,
                overlapped_percent=0,
                strategy=MergeStrategy.OVER_CAP):
```

四個參數，四個決定。

### 5.1 分隔符優先，而不是 token 優先

```python
DEFAULT_DELIMITER = "\n!?;。；！？"   # rag/nlp/delim.py
```

預設分隔符是**換行 + 中英文句末標點**。切分的第一步永遠是「按分隔符切成段落」，token 上限只用來決定「相鄰段落要不要合併」。

程式碼裡的註解把這個契約寫得很明白：

> A section is split on the delimiter whenever one is present — even when the whole section already fits `chunk_token_num`. The delimiter is a chunk boundary and its text must never leak into a chunk.

**分隔符是邊界，不是提示。** 這與 `RecursiveCharacterTextSplitter` 的邏輯相反：後者是「先按大小切，切不開才找分隔符」，前者是「先按分隔符切，再看要不要合併」。

差別在哪？看一個例子。一段 300 token 的文字，包含 5 個句子，`chunk_token_num=128`：

```
遞迴切分：  [1-128 token] [129-256] [257-300]     ← 句子被切斷
naive_merge：[句1+句2] [句3+句4] [句5]            ← 邊界永遠在句號上
```

### 5.2 `MergeStrategy`：允許一次邊界溢出

```python
class MergeStrategy(Enum):
    UNDER_CAP = "under_cap"   # 只在不超過 token_size 時合併，絕不溢出
    OVER_CAP  = "over_cap"    # 預設：允許最後一個段落造成一次溢出
```

`OVER_CAP` 的行為是：貪婪累加段落，當下一段會超過上限時，**還是把它併進來**，然後才關閉這個 chunk。

**為什麼要允許溢出？** 因為不允許溢出的結果是產生大量「差一點就滿」的小 chunk，以及被孤立的短尾段落。允許一次溢出，讓 chunk 大小分布集中，代價是有些 chunk 會比設定值大 20～50%。

另外一個明文規定的契約：**永不做「原子切分」（atom-split）**。

> No atom-split is ever performed: a paragraph larger than `token_size` becomes its own chunk. The model layer truncates oversize units.

也就是說，如果有一個 500 token 的段落而上限是 128，它會**原封不動變成一個 500 token 的 chunk**，交給下游 embedding 時截斷（`truncate(c, mdl.max_length - 10)`）。設計者寧願讓一個 chunk 過大，也不願在段落中間切一刀。

### 5.3 `chunk_token_num`：128 還是 512？

程式碼裡兩個數字都出現：

```python
# 函式簽名的預設值
def naive_merge(sections, chunk_token_num=128, ...)

# naive.chunk() 拿不到 parser_config 時的 fallback
parser_config = kwargs.get("parser_config",
    {"chunk_token_num": 512, "delimiter": DEFAULT_DELIMITER,
     "layout_recognize": "DeepDOC", "analyze_hyperlink": True})
```

UI 上的預設值是 **128**。這比多數教學文章建議的 512～1024 小很多，原因是：

1. **RAGFlow 用混合檢索。** 小 chunk 對關鍵字匹配有利（IDF 訊號集中，不被長文稀釋）。
2. **有 parent/child 與 TOC 增強機制。** 檢索用小 chunk 命中，回傳時可以擴展上下文（`retrieval_by_children`、`retrieval_by_toc`、`table_context_size`、`image_context_size`）。
3. **重排時 token 相似度會算 bigram。** chunk 越小，bigram 訊號越乾淨。

**如果你把 RAGFlow 當純向量庫用（關掉全文檢索），128 會太小；反之，128 配上混合檢索 + 上下文擴展是合理的。**

### 5.4 `overlapped_percent` 與反直覺的實作

重疊的實作有一個細節值得注意：**分組時就先預留了重疊空間**。

```python
# 合併門檻不是 token_size，而是
threshold = token_size * (100 - overlapped_percent) / 100
```

也就是設 20% 重疊、上限 128 時，分組階段只用 102 token 當門檻，剩下 26 token 留給前綴重疊。這樣加上重疊之後總長還在 128 附近，**不會出現「設了重疊，chunk 就全部超標」的情況**。設 `overlapped_percent=0` 時門檻退化成 `token_size`，行為與舊版完全一致。

### 5.5 反引號自訂分隔符：一個旁路

```python
has_custom = has_wrapped_delimiter(delimiter)
if has_custom:
    # Custom delimiters ignore chunk_token_num: each segment is its own chunk.
```

如果分隔符欄位裡有**用反引號包起來**的 token（例如 `` `###` ``），行為會完全改變：**每個切出來的段落各自成為一個 chunk，完全忽略 `chunk_token_num`。**

這是給結構化文件的逃生門。例如一份用 `---` 分隔的 FAQ、或每筆記錄用固定標記開頭的日誌，使用者只要指定該標記，就能得到「一筆記錄一個 chunk」的精確切分，不受 token 上限干擾。

### 5.6 完整切分流程圖

```
sections（來自解析層）
      │
      ▼
┌──────────────────────────────────────────────┐
│ 換行正規化：\r\n 和 \r 都轉成 \n              │
│ （否則 delimiter "\n" 在 Windows 檔案上失效） │
└──────────────────┬───────────────────────────┘
                   ▼
        分隔符欄位有反引號包裹？
         ┌─────────┴─────────┐
        是                    否
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌──────────────────────────────┐
│ 每段各自成 chunk │  │ 按分隔符切成 paragraphs       │
│ 忽略 token 上限  │  │ （分隔符文字本身不進 chunk）   │
└──────────────────┘  └──────────────┬───────────────┘
                                     ▼
                      ┌──────────────────────────────┐
                      │ _merge_paragraph_groups()    │
                      │ OVER_CAP：貪婪累加，允許一次  │
                      │ 邊界溢出後關閉 chunk          │
                      │ 門檻 = size×(100-overlap)/100│
                      └──────────────┬───────────────┘
                                     ▼
                      ┌──────────────────────────────┐
                      │ _apply_overlap_unconditional │
                      │ 加上前一 chunk 的尾部作前綴   │
                      └──────────────┬───────────────┘
                                     ▼
                            chunks（待加值）
```

---

## 六、三個演進階段：切分策略

### ╔══ Phase 1：用預設值（POC / 文件同質） ══╗

```
上傳 ──▶ parser_id = naive
         layout_recognize = DeepDOC
         chunk_token_num = 128
         delimiter = "\n!?;。；！？"
         其他加值全關
              │
              ▼
         看 UI 的 chunk 列表，人工抽查 20 個
```

- **新增元件**：無，就是預設值
- **成本**：只有 embedding 的 token 費用
- **解決的問題**：驗證資料能不能用、chunk 看起來合不合理
- **剩下的問題**：法條、表格、履歷這類文件的召回率明顯偏低；掃描件表格仍會混欄

**Phase 1 的關鍵動作不是調參數，是看 chunk。** RAGFlow 把 chunk 可視化做出來就是為了這件事。抽查 20 個 chunk，如果有 5 個是「半句話」或「表頭和資料分家」，就該進 Phase 2。

### ╔══ Phase 2：模板分流 + 人工介入（MVP） ══╗

```
              上傳檔案
                 │
       ┌─────────┴──────────┬────────────┬──────────┐
       ▼                    ▼            ▼          ▼
┌──────────────┐   ┌──────────────┐ ┌─────────┐ ┌────────┐
│ 合約/法規     │   │ 財報/報表    │ │ FAQ     │ │ 其他   │
│ parser=laws  │   │ parser=table │ │parser=qa│ │ naive  │
└──────┬───────┘   └──────┬───────┘ └────┬────┘ └───┬────┘
       └───────────────────┴──────────────┴──────────┘
                           ▼
              ┌────────────────────────────┐
              │ 抽查 chunk，人工修正：      │
              │ · important_kwd（檢索 ^30）│
              │ · questions（檢索 ^20）    │
              │ · available_int=0 停用雜訊 │
              └────────────────────────────┘
```

- **新增元件 vs Phase 1**：多個知識庫（每個知識庫一種 `parser_id`）、人工 chunk 修正流程、`table_context_size` / `image_context_size` 上下文擴展
- **成本增量**：人力（每 100 份文件約 1～2 小時抽查）
- **解決的問題**：結構化文件的召回率；表格與圖片的上下文完整性
- **剩下的問題**：解析參數還是全域的，同一個知識庫裡混合格式時無法分流；跨文件的全局問題（「這批合約有哪些共同風險」）答不出來

**這一階段最高 ROI 的動作是 `important_kwd`。** 檢索時它的 boost 是 30（是 `content_ltks` 的 15 倍），本地重排時 token 還要再乘 5。**在 20 個關鍵 chunk 上各加 3 個關鍵詞，效果通常大於把 embedding 模型換成更貴的那個。**

### ╔══ Phase 3：可編排 pipeline + 語意增強（Scale） ══╗

RAGFlow 在 2025-10-15 加入了 "orchestrable ingestion pipeline"，程式碼在 `rag/flow/`：

```
┌────────────────────────────────────────────────────────────────┐
│  Pipeline(Graph)  —  rag/flow/pipeline.py                      │
│                                                                │
│  ┌──────┐   ┌────────┐   ┌─────────┐   ┌───────────┐          │
│  │ File │──▶│ Parser │──▶│ Chunker │──▶│ Tokenizer │──▶ index │
│  │      │   │        │   │         │   │           │          │
│  └──────┘   └───┬────┘   └────┬────┘   └───────────┘          │
│                 │             │                                │
│                 │             ├── token_chunker                │
│                 │             └── title_chunker/               │
│                 │                  ├── hierarchy_chunker       │
│                 │                  └── group_chunker           │
│                 ▼                                              │
│           ┌───────────┐   ┌──────────┐                        │
│           │ Extractor │   │ Compiler │                        │
│           └───────────┘   └──────────┘                        │
└────────────────────────────────────────────────────────────────┘
        每個節點都是 ProcessBase 子類，DSL 用 JSON 描述
```

`rag/flow/` 的目錄結構直接對應這些階段：`file.py`、`parser/`、`chunker/`（含 `token_chunker.py` 與 `title_chunker/`）、`tokenizer/`、`extractor/`、`compiler/`。所有節點繼承自 `ProcessBase`，介面就一個 `async def _invoke(**kwargs)`。

- **新增元件 vs Phase 2**：DAG 化的 ingestion（同一知識庫可以按檔案型別走不同分支）、`hierarchy_chunker`（依標題層級建立父子 chunk）、TOC 抽取（`build_TOC`）、RAPTOR 摘要樹、GraphRAG 圖抽取
- **成本增量**：LLM 呼叫（見下一節的算式）
- **解決的問題**：混合格式知識庫、全局性問題、多跳問題
- **剩下的問題**：pipeline DSL 的除錯體驗（有 `CANVAS_DEBUG_DOC_ID` 這個特殊 doc id 專門用來 debug pipeline）；GraphRAG 的成本可能是一般 ingestion 的 10～50 倍

### 三階段對照

| 維度 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 切分方式 | naive 128 token | 4～5 種模板分流 | DAG pipeline + 父子 chunk |
| 解析後端 | DeepDOC | DeepDOC + 選配 VLM | 按型別分流（MinerU/Docling/VLM） |
| 人工介入 | 抽查 | `important_kwd` + `questions` | 抽查 + 回饋迴路 |
| LLM 加值 | 全關 | 選擇性開 `question_proposal` | 全開 + RAPTOR + GraphRAG |
| 每 1000 chunk 成本 | 僅 embedding | + 1000～2000 次 LLM 呼叫 | + 5000～20000 次 LLM 呼叫 |
| 適合 | 驗證 | 生產 | 高價值知識庫 |

---

## 七、Chunk 加值管線：四個 LLM 步驟與它們的帳單

切完之後，`build_chunks()` 裡有一整組可選的加值步驟，每一個都是對**每個 chunk** 呼叫一次 LLM：

```
        chunks（純文字）
              │
    ┌─────────┼─────────┬──────────────┬─────────────┐
    ▼         ▼         ▼              ▼             ▼
┌────────┐┌────────┐┌──────────┐  ┌─────────┐  ┌────────┐
│keyword_││question││ content_ │  │ gen_    │  │build_  │
│extract-││_propos-││ tagging  │  │ metadata│  │TOC     │
│ion     ││al      ││          │  │         │  │        │
├────────┤├────────┤├──────────┤  ├─────────┤  ├────────┤
│抽 topn ││生成 topn││ 對標籤庫 │  │抽結構化 │  │抽目錄  │
│關鍵字  ││個可能  ││ 打分     │  │metadata │  │層級    │
│        ││問句    ││          │  │         │  │        │
│→       ││→      ││→        │  │→       │  │→      │
│import- ││quest-  ││tag_feas  │  │doc      │  │toc_kwd │
│ant_kwd ││ion_kwd ││          │  │metadata │  │        │
│（^30） ││（^20） ││（×10）   │  │（可過濾）│  │        │
└────────┘└────────┘└──────────┘  └─────────┘  └────────┘
    每個 chunk 一次      每個 chunk 一次    每份文件一次
```

**成本算式**（假設 5 萬份文件、平均 40 chunk/份 = 200 萬 chunk）：

| 加值項目 | 呼叫次數 | 說明 |
|---|---|---|
| `keyword_extraction` | 200 萬 | 每 chunk 一次 |
| `question_proposal` | 200 萬 | 每 chunk 一次 |
| `content_tagging` | 200 萬 | 每 chunk 一次 |
| `gen_metadata` | 5 萬 | 每份文件一次 |
| `build_TOC` | 5 萬 | 每份文件一次 |
| **合計** | **≈ 610 萬次** | |

以一次呼叫平均 800 input + 100 output token、用便宜的小模型（$0.15/$0.60 per M token）估算：**約 900 美元**。用旗艦模型會是 20～40 倍。

**這就是為什麼這些開關預設全關。** 它們不是「應該打開的優化」，而是「在高價值知識庫上值得花錢的投資」。實務建議：

- **先只開 `question_proposal`**：它產生的 `question_kwd` 在 embedding 階段會**取代內容**被編碼（見 Part 3），對 FAQ 型查詢的提升最直接
- **`keyword_extraction` 的替代方案是人工**：20 個關鍵 chunk 手動加關鍵詞，勝過 200 萬次自動抽取
- **`content_tagging` 需要先有標籤庫**（用 `tag` 模板建），沒有標籤庫時它是空轉

### 7.1 一個容易忽略的並發控制

這些 LLM 呼叫都在 `chat_limiter` 之下（`rag/graphrag/utils.py`），並且 `task_executor.py` 有一個 `@timeout(60 * 80, 1)` 裝飾在任務處理函式上——**單一任務的上限是 80 分鐘**。一份 500 頁的 PDF 若同時開三種加值，很容易撞到這個上限而失敗重試。

實務上如果看到 task 反覆超時，處理順序是：先關掉加值 → 確認解析本身能過 → 再逐項打開。

---

## 八、為什麼選 X 不選 Y

```
決定                  選 X 的理由                        不選 Y 的理由 / Y 更好的時機
────────────────────────────────────────────────────────────────────────────────────
分隔符優先切分         語意邊界永遠不被破壞；             大小優先（遞迴切分）：實作簡單、
vs 大小優先切分        分隔符文字不洩漏進 chunk；         chunk 大小極均勻，但句子會被切斷
                      中英標點預設全覆蓋                  ▶ 翻轉點：文件完全沒有標點結構
                                                           （如 OCR 出來的連續字流）

允許一次邊界溢出       chunk 大小分布集中，不產生          嚴格不溢出（UNDER_CAP）：大小可控，
（OVER_CAP 預設）      「差一點就滿」的碎片和孤立短尾      但碎片多、短尾多
vs 嚴格不超上限                                           ▶ 翻轉點：embedding 模型上下文很短
                                                           且截斷代價高時用 UNDER_CAP

不做原子切分           寧可一個超大 chunk 被下游截斷，     硬切段落：保證大小，但可能在句中、
（超長段落原樣保留）   也不在段落中間切一刀                甚至詞中切開
vs 硬切                                                   ▶ 翻轉點：資料裡有異常長段落
                                                           （整篇無換行）時需要前置清理

14 種模板              法條、表格、履歷的結構假設完全      單一通用切分器：零設定，
vs 一個通用切分器      不同；讓使用者「選對假設」比        但在結構化文件上召回率差一截
                      「調對參數」容易                     ▶ 翻轉點：文件同質性高時，
                                                           naive 就是最佳解

本地 ONNX（DeepDoc）  單頁邊際成本≈0；輸出是結構化的       VLM 逐頁解析：品質上限高，
vs 逐頁 VLM            版面座標與型別，不是自由文字；      但成本按頁線性增長、延遲高
                      可離線、可預測                       ▶ 翻轉點：頁數少但版面極端
                                                           （手寫、複雜圖表）時

OCR 信心分數做旋轉     不需要額外模型、不需要標註資料、     訓練角度分類器：一次推論、
偵測（四次 OCR）       零維護成本                          但要資料、要訓練、要維護
vs 專用角度模型                                            ▶ 翻轉點：表格佔比極高時，
                                                           四倍 OCR 成本變得顯著

LLM 加值預設全關       200 萬 chunk 開三項 = 610 萬次      預設全開：品質更好，
vs 預設全開            呼叫；使用者應該明確選擇付這筆錢     但新使用者第一次上傳就收到帳單
                                                          ▶ 翻轉點：高價值、小規模知識庫
                                                            （如公司核心 SOP）值得全開
```

---

## 九、系統效應：解析與切分改對之後

以下數字來自公開基準與實務經驗的量級估計（RAGFlow 本身沒有發布官方 benchmark，`rag/benchmark.py` 是給使用者自己跑的），用意是說明**改動的方向與量級**，不是精確承諾。

| 指標 | naive 抽文字 + 512 固定切分 | DeepDoc + 模板切分 | 主要來源 |
|---|---|---|---|
| 掃描件可用率 | ≈ 0%（抽出空字串） | 可用 | OCR |
| 表格欄位正確率 | 低（欄列關係消失） | 顯著提升 | TSR + 表格重組 |
| 雙欄論文語句完整率 | 低（左右欄交錯） | 高 | Layout 分區 |
| chunk 半句話比例 | 每 chunk 都有機率 | 接近 0（邊界在標點上） | 分隔符優先 |
| 頁眉頁腳污染 | 每 chunk 都有 | 0（Header/Footer 被辨識丟棄） | Layout 分類 |
| 專名查詢命中 | 靠向量近似 | `important_kwd^30` 精確命中 | 人工介入 + 混合檢索 |
| FAQ 型查詢命中 | 靠內容相似 | `question_kwd` 直接匹配（^20） | `qa` 模板 / `question_proposal` |
| 解析成本（1 萬份） | 幾乎為零 | CPU 時間（DeepDOC）或 $$$（VLM） | 後端選擇 |

**要記住的取捨**：DeepDoc 不是免費的。它把「解析」從一個 O(檔案大小) 的字串操作，變成一個 O(頁數 × 模型推論) 的計算任務。這是 RAGFlow 一定要有非同步 worker 架構的根本原因——也是 Part 5 的主題。

---

## 十、系列導航

本篇處理完「資料進場」。chunk 現在是一組帶版面座標、可能帶關鍵字與問句的文字片段。下一步是把它們變成向量並存起來——這比想像中有更多設計決定。

- **Part 3 — Encode 與 Save**：為什麼向量是 `0.1 × 檔名 + 0.9 × 內容`、有 `questions` 時為什麼改編碼問句、後綴驅動的動態 mapping 全表、以及那個把 TF 壓成 `min(freq,1)` 的自訂相似度為什麼存在。

← [Part 1 — 全景架構 — 從一份 PDF 到一句帶引用的答案](../ragflow-intro-part1-overview-architecture-zh) | [Part 3 — Encode 與 Save — 向量化、索引 Schema 與雙引擎抽象 →](../ragflow-intro-part3-embedding-indexing-zh)

---

*本文基於 RAGFlow `main` 分支（2026 年 9 月）原始碼撰寫。所有參數預設值、檔案大小與模板列表皆從原始碼實際核對；成本估算為量級推估，實際數字依模型定價與文件特性而異。*
