---
title: "ChatPDF RAG 優化（二）：後端強化與進階 RAG —— 安全、資源邊界、多查詢擴展"
date: 2026-06-30T10:30:00+08:00
draft: false
description: "RAG demo 能跑,不代表能上線。本篇拆解 chatPDF 如何補上 production 該有的防線:上傳的 PDF magic bytes 驗證與 OOM 防護、BM25 的 LRU 快取、多查詢擴展、檢索評分過濾、頁碼級引用、LLM gateway 重試退避——把 RAG pipeline 從「能跑」變成「能扛」。"
categories: ["engineering", "ai", "all"]
tags: ["RAG", "LLM", "ChatPDF", "Security", "Backend", "Production", "Multi-Query", "LRU Cache", "API Hardening"]
authors: ["yen"]
readTime: "17 min"
---

> 多數 RAG 專案的生命週期:demo 驚艷 → 上線 → 第一個惡意上傳把記憶體吃爆 → 第一個含程式碼的 PDF 讓檢索掛掉 → 緊急修補。
> 這篇講的就是「在出事之前」把那些防線一次補齊。
> 核心不是新功能,而是把每一個「會出事的環節」都加上邊界、退路、與防呆。

---

## 一、為什麼 demo 跟 production 是兩回事

[上一篇](../chatpdf-rag-optimization-part1-chunking-retrieval-zh/)解決了 RAG 的品質核心:切塊與檢索。但品質好不等於能上線。[PR #2](https://github.com/yennanliu/chatPDF/pull/2) 的主題是 **hardening(強化)**——把這套系統從「在我電腦上能跑」推到「面對真實使用者、惡意輸入、長時間運行都不會倒」。

它涵蓋兩條主線:

```
┌─────────────────────────────────────────────────────┐
│  後端強化(165 測試,+30 新增)                        │
│  ├─ 安全:上傳驗證、輸入邊界、刪除順序、錯誤訊息淨化  │
│  ├─ 資源:檔案大小限制、BM25 LRU 快取、歷史視窗      │
│  └─ 進階 RAG:多查詢擴展、檢索評分、頁碼引用、去重    │
├─────────────────────────────────────────────────────┤
│  前端現代化(+10 Vitest 測試)                         │
│  ├─ 集中式 typed API client、Toast 通知              │
│  └─ 進階 RAG 設定面板、搜尋、暗色模式、匯出           │
└─────────────────────────────────────────────────────┘
```

下面挑最有代表性的幾個防線拆解。

---

## 二、上傳安全:在記憶體被吃爆之前擋下來

### 問題:兩個經典攻擊面

1. **偽裝檔案**:有人把 `.exe` 改名成 `.pdf`,或宣稱 content-type 是 PDF 但內容不是。
2. **OOM / DoS**:有人上傳一個 10GB 的「PDF」。如果程式先把整個檔案讀進記憶體再檢查,光讀就把伺服器打掛了。

### 解法:magic bytes + 先驗大小再讀

**第一道:magic bytes 驗證。** 真正的 PDF 一定以 `%PDF` 開頭。光看副檔名或 content-type 不夠,要看**檔案內容的前幾個 byte**:

```python
# content-type 不對,或內容開頭不是 %PDF → 415 拒絕
if file.content_type not in (None, "application/pdf") \
        or not content.startswith(b"%PDF"):
    raise HTTPException(status_code=415, detail="Only PDF files are accepted")
```

這同時擋掉「錯的 MIME type」和「改副檔名偽裝」兩種情況。

**第二道:在讀進記憶體之前先擋大小。** 關鍵是順序——在 multipart 解析階段就檢查 `file.size`,**不要等到整個檔案 buffer 進記憶體才檢查**:

```python
# 解析階段就擋(還沒讀進記憶體)
if file.size is not None and file.size > max_bytes:
    raise HTTPException(status_code=413, detail="File too large")

content = await file.read()
# 讀完再驗一次當保險(有些情況 file.size 為 None)
if len(content) > max_bytes:
    raise HTTPException(status_code=413, detail="File too large")
```

```
   惡意上傳 10GB
        │
        ▼
   ┌──────────────┐   file.size > max?  ┌─────────┐
   │ multipart 解析│ ──────Yes──────────▶│ 413 拒絕 │  ← 記憶體零負擔
   └──────┬───────┘                     └─────────┘
          │ No
          ▼
   讀進記憶體 → 再驗一次(兜底)→ 驗 %PDF magic bytes
```

**設計重點:防護的順序就是防護的一切。** 同樣是檢查大小,「讀之前檢查」是防 OOM,「讀之後檢查」只是兜底。先後順序錯了,防線就形同虛設。

---

## 三、刪除順序:先刪 DB row,再清向量與檔案

刪除一份文件牽涉三個地方:資料庫的 row、向量庫的 embedding、磁碟上的檔案。順序很重要。

**原則:先刪「真相來源」(DB),再刪衍生資料(向量、檔案)。** 而且後面的清理要用 try-except 包住,避免某個清理失敗就連鎖中斷,留下一堆孤兒資源:

```
   刪除流程
   ──────────────────────────────────
   1. 刪 DB row          ← 先斷掉「這份文件存在」的真相
   2. try: 刪向量 embedding
      except: 記 log,繼續
   3. try: 刪磁碟檔案
      except: 記 log,繼續
```

為什麼這個順序?如果先刪檔案、DB row 還在,使用者會看到一份「點開卻 404」的鬼文件;反過來先斷 DB,即使向量或檔案清理失敗,使用者視角它已經消失了,殘留的孤兒資源頂多是背景待清,不影響正確性。

---

## 四、BM25 的 LRU 快取:堵住記憶體洩漏

### 問題

上一篇的 Hybrid Retriever 每次查詢都要對語料重建一份 BM25 索引。如果為了加速而把每次建好的索引都 cache 起來,**沒有上限的 cache 就是一個記憶體洩漏**——長時間運行的伺服器會被慢慢吃爆。

### 解法:OrderedDict 實作 LRU,上限 64

```python
from collections import OrderedDict

_bm25_cache: OrderedDict = OrderedDict()
_BM25_CACHE_MAX = 64

# cache 命中:把它移到尾端(刷新「最近使用」)
# cache miss:插入新的,若超過上限就淘汰最舊的(隊首)
while len(self._bm25_cache) > self._BM25_CACHE_MAX:
    self._bm25_cache.popitem(last=False)   # 淘汰最久沒用的
```

`OrderedDict` 天然支援 LRU:`move_to_end()` 把命中的項目移到尾端表示「剛用過」,`popitem(last=False)` 淘汰隊首(最久沒用)的。上限 64 是「夠用又不會爆」的平衡點。

**設計重點:任何 cache 都必須有上限。** 無上限的 cache 不是優化,是定時炸彈。

---

## 五、進階 RAG 之一:多查詢擴展(Multi-Query Expansion)

### 問題

使用者問問題的方式很隨意,常常跟文件裡的用詞對不上。使用者問「公司賺錢嗎」,文件寫「淨利率」「營業利益」——語意接近,但單一查詢可能撈不全。

### 解法:讓 LLM 幫忙改寫成多種問法,合併檢索結果

```
   原始 query: "公司賺錢嗎?"
        │
        ▼  LLM 改寫成 N 種問法
   ┌────────────────────────────┐
   │ "公司的獲利能力如何?"        │
   │ "淨利率與營業利益表現?"      │
   │ "是否處於盈利狀態?"          │
   └────────────┬───────────────┘
                ▼  各自檢索,以 chunk key 合併
        每個 chunk 保留「最高分」
                ▼
           更全面的 context
```

實作上:`_expand_queries()` 請 LLM 給 N 種替代問法,**大小寫不敏感去重**,各自檢索後**以 chunk key 合併、每個 chunk 保留最高分**。這樣同一段落不會因為被多個查詢撈到而重複,且取的是它在所有問法下的最佳表現。

**取捨**:多查詢會增加 LLM 呼叫與檢索次數(成本上升),換來 recall 提升。對「答不全比答慢更糟」的場景值得;對極度在意延遲/成本的場景可關掉。

---

## 六、進階 RAG 之二:檢索評分過濾(Retrieval Grading)

撈回 top-k 不代表這 k 個都相關。最後一名可能分數低到根本是噪音,塞進 context 只會干擾 LLM。

解法是一個可配置的 `min_score` 門檻,在排序後、生成前**過濾掉低於門檻的弱命中**:

```python
# 低於 min_score 的 chunk 直接丟掉,不進 context
if rag_config.min_score > 0:
    context = [c for c in context if c.get("score", 0.0) >= rag_config.min_score]
```

**設計重點:寧缺勿濫。** 給 LLM 三段精準的內容,比給它十段(其中七段是噪音)更容易答對。`min_score > 0` 才啟用,預設不開,讓使用者按需開啟。

---

## 七、進階 RAG 之三:頁碼級引用(Page-Aware Citations)

RAG 答案最被詬病的就是「無法驗證」。chatPDF 在切塊入庫時就記下**每個 chunk 來自第幾頁**:

```python
# 入庫時把頁碼寫進 metadata
metadatas.append({
    "doc_id": doc_id,
    "chunk_index": len(chunks),
    "file": file_name,
    "page": page_no,        # ← 記下頁碼
})

# 引用時帶上頁碼
citation = {"file": c["metadata"]["file"], "page": c["metadata"].get("page")}
```

於是每條引用都能精確到「`report.pdf` 第 12 頁」,使用者可以直接翻去原文核對。**RAG 的可信度,很大一部分來自「可被查證」。**

---

## 八、進階 RAG 之四:LLM Gateway 重試與退避

外部 LLM API 偶爾會 timeout、rate limit、5xx。沒有重試機制的話,使用者就直接吃到一個失敗。chatPDF 把重試交給 provider SDK 處理,並把 temperature 參數化:

```python
# SDK 層處理暫時性錯誤的重試/退避
llm = get_llm(provider, model, temperature=0.0)
#   max_retries=settings.llm_max_retries   (預設 2)
```

temperature 參數化的好處:**生成答案用 0.0(穩定),judge/評估呼叫也用 0.0(可重現)**,而需要多樣性的場景(如多查詢改寫)可調高。同一個 gateway 服務多種用途。

---

## 九、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 上傳驗證 | magic bytes(`%PDF`) | 不選只看副檔名/MIME:兩者都能偽造,內容騙不了 |
| 大小檢查 | 讀進記憶體「之前」 | 不選讀完才查:讀完才查 = OOM 已經發生 |
| 刪除順序 | 先 DB row 再衍生資料 | 不選先刪檔案:會留下「點開 404」的鬼文件 |
| cache 上限 | LRU 上限 64 | 不選無上限 cache:長跑伺服器會記憶體洩漏 |
| 弱命中 | min_score 過濾 | 不選全塞進 context:噪音會干擾 LLM 答題 |
| 引用粒度 | 頁碼級 | 不選只標檔名:無法精確查證,可信度打折 |
| API 失敗 | 重試 + 退避 | 不選直接失敗:暫時性錯誤不該讓使用者吃到 |

**Flip condition**:

- 內網、全可信的使用者環境,上傳驗證可放寬(但 magic bytes 幾乎零成本,還是建議留)。
- 語料極小、查詢量極低時,BM25 cache 可省略(直接每次重算也不慢)。
- 極度在意延遲的即時場景,多查詢擴展與 response scoring 可關掉。

---

## 十、系統效應:改動前 vs 改動後

| 面向 | 改動前 | 改動後 |
|------|--------|--------|
| 上傳安全 | 只看副檔名 | magic bytes + 先驗大小再讀 |
| 大檔案 | 可能 OOM | 解析階段即 413 拒絕 |
| 刪除 | 順序不定,易留孤兒 | DB 先行 + try-except 清理 |
| BM25 記憶體 | 無上限(會洩漏) | LRU 上限 64 |
| 檢索召回 | 單一查詢 | 多查詢擴展,recall 提升 |
| context 品質 | 含弱命中噪音 | min_score 過濾 |
| 引用 | 僅檔名 | 頁碼級可查證 |
| API 穩定性 | 直接失敗 | 重試 + 退避 |
| 測試 | — | 後端 195 測試全綠,前端 +10 Vitest |

---

## 十一、小結

這篇沒有一個「炫技」的功能,全部都是**把會出事的環節提前補上防線**:

1. **安全靠「順序」**:先驗大小再讀(防 OOM)、先刪 DB 再清衍生(防孤兒)。
2. **資源靠「邊界」**:任何 cache 都要有上限,任何輸入都要有長度限制。
3. **品質靠「退路」**:重試退避兜住 API、min_score 濾掉噪音、頁碼引用支撐可信度。

> 一句話總結:demo 比的是「最好的情況能多好」,production 比的是「最壞的情況能多不壞」。

下一篇([第三部分](../chatpdf-rag-optimization-part3-observability-eval-zh/))處理最後一塊:**可觀測性與評估**——Langfuse 追蹤、評估歷史持久化、即時答案評分、無依賴 SVG 圖表。沒有量測,就沒有持續優化。

---

**系列導覽**

- [第一部分:語意切塊與混合檢索](../chatpdf-rag-optimization-part1-chunking-retrieval-zh/)
- 第二部分:後端強化與進階 RAG(本篇)
- [第三部分:可觀測性與評估](../chatpdf-rag-optimization-part3-observability-eval-zh/)

**參考連結**

- PR: [harden backend + RAG, modernize frontend #2](https://github.com/yennanliu/chatPDF/pull/2)
- Repo: [yennanliu/chatPDF](https://github.com/yennanliu/chatPDF)
