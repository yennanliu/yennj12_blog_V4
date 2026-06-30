---
title: "把站台從 3.1GB 砍到 503MB：finance_data 部署效能調校全紀錄"
date: 2026-06-30T09:00:00+08:00
draft: false
description: "finance_data 是一個由 ~42 個每日分析任務自動產生報告的 MkDocs 站台，膨脹到搜尋索引 195MB、首頁 1MB、單次部署 752MB、CI 跑 15 分鐘。這篇拆解我們用六個改動把它降到搜尋索引 0.86MB、首頁 53KB、部署 387MB、CI 6.5 分鐘的完整過程與設計取捨。"
categories: ["engineering", "all"]
tags: ["MkDocs", "Performance", "CI/CD", "GitHub Pages", "GitHub Actions", "Static Site", "Optimization", "WebP", "Search Index"]
authors: ["yen"]
readTime: "16 min"
---

> 多數人優化靜態站台的做法：壓縮一下圖片、開個快取就收工。
> 但當站台是由 42 個機器人每天自動寫進去的 5,000 頁報告時，問題不在「檔案大」，
> 而在「整個 pipeline 的每個環節都在重複放大成本」——搜尋索引、導覽樹、git 歷史、部署觸發頻率。
> 真正的調校，是找出那些被無限複製的單位成本。

---

## 一、問題：一個會自己長大的站台

[`finance_data`](https://github.com/yennanliu/finance_data) 是一個自動化金融分析站台。它的內容不是人手寫的，而是由大約 **42 個每日排程任務**自動產生：10-K / 10-Q / 13-F 財報摘要、investor day 筆記、AI 生成的個股報告、notebook PDF……每天都有新的 dated report 被寫進 repo，再透過 MkDocs（Material 主題）建置成靜態站台，部署到 GitHub Pages。

這種「機器人持續寫入」的特性，讓站台的成本不是線性增加，而是**在好幾個環節同時被放大**。等到我們去看的時候，數字已經很難看：

```
症狀                          數字
──────────────────────────────────────────────
搜尋索引 (search_index.json)   195 MB
首頁 HTML                      1.07 MB
單一深層報告頁 HTML            590 KB
單次部署 payload               752 MB
建置完成的站台總大小           ~3.1 GB
CI 建置 + 部署時間             ~15 分鐘
每天觸發部署次數               ~42 次（每個分析任務 push 一次）
```

最致命的不是任何單一數字，而是**它們互相加乘**：5,000 頁 × 每頁 1MB 的導覽樹 = 站台爆炸；42 次/天 × 752MB 的部署 = CI 排隊塞車。我們要做的，是逐一拆掉這些放大器。

下面六個改動，依「投資報酬率」由高到低排列。

---

## 二、改動一：把報告內文踢出搜尋索引（195MB → 0.86MB）

### 問題

MkDocs Material 的搜尋功能，會把**每一頁的全文**抽出來，建成一份 `search_index.json`，在使用者載入站台時下載到瀏覽器。對一般文件站台這沒問題；但我們有 5,000 頁、每頁動輒上萬字的財報內文，索引直接膨脹到 **195MB**。

這代表每個訪客一進站，瀏覽器就要默默下載一個 195MB 的 JSON。這不只是部署大小問題，是**直接打在使用者體驗上的災難**。

### 解法

MkDocs 支援用 front matter 把單頁排除在搜尋之外：

```yaml
---
search:
  exclude: true
---
```

關鍵在於：報告內文沒有人會用「全文搜尋」去找——使用者是透過個股的 index 頁、表格連結進去的。所以報告內文對搜尋索引**毫無價值，卻佔了 99% 的體積**。

在 `scripts/build_docs.py` 的建置流程裡，我們讓每個複製出來的 Markdown 報告自動帶上這段 front matter：

```python
SEARCH_EXCLUDE_FM = "---\nsearch:\n  exclude: true\n---\n\n"

def copy_file(src: Path, dst: Path, prepend: str = ""):
    """複製 src → dst。Markdown 可選擇性地在前面插入 front matter。"""
    ensure(dst.parent)
    if src.suffix == ".md":
        content = src.read_text(encoding="utf-8")
        content = prepend + content          # ← 插入排除標記
        dst.write_text(content, encoding="utf-8")

# 建置報告時一律帶上排除標記
for f in md_files:
    copy_file(f, dst_dir / f.name, prepend=SEARCH_EXCLUDE_FM)
```

### 結果

```
搜尋索引     195 MB ──────────────────────▶ 0.86 MB   (−99.6%)
```

索引裡只剩下手寫的導覽頁、index 頁、about 等真正需要被搜尋的內容。**單一改動拿下整個專案最大的一塊肥肉。**

---

## 三、改動二：導覽從 expand 改成 prune（首頁 1MB → 53KB）

### 問題

我們原本在 `mkdocs.yml` 開了 `navigation.expand`：

```yaml
theme:
  features:
    - navigation.expand
```

`navigation.expand` 會把**整棵導覽樹「全部展開」渲染進每一頁的 HTML**。當你只有 50 頁時這很方便；當你有 5,000 頁時，這代表**每一頁的 HTML 裡都塞了一份完整的 5,000 項目側邊欄**，光導覽就佔掉約 1MB。

```
   ┌──────────────────────────────────────────────┐
   │  navigation.expand                            │
   │                                               │
   │  每一頁 HTML 都內嵌「全部 5,000 頁」的側邊欄  │
   │                                               │
   │   頁面1.html ┐                                │
   │   頁面2.html ├──▶ 各自帶一份 ~1MB 完整 nav    │
   │   頁面3.html ┘                                │
   │   ... × 5000                                  │
   └──────────────────────────────────────────────┘
```

### 解法

改用 `navigation.prune`：

```yaml
validation:
  nav:
    omitted_files: info

theme:
  features:
    # 移除 navigation.expand（效能考量）：它強迫整棵 5,000 頁的樹
    # 在每一頁都展開渲染（每頁約 1MB HTML）。navigation.prune 只輸出
    # 當前頁面所屬的子樹，單頁重量下降約 80–95%。
    - navigation.prune
```

`navigation.prune` 只渲染**當前頁面所在的那條分支**，其餘按需載入。每頁不再背負整棵樹。

### 結果

```
首頁 HTML         1.07 MB ──────────▶ 53 KB    (−95%)
```

---

## 四、改動三：報告頁不要全進側邊欄（深層頁 590KB → 195KB）

### 問題

改動二解決了「每頁渲染整棵樹」，但還有第二層問題：`awesome-pages` 外掛預設會把**每一個報告頁（~3,500 頁的 dated report）都加進全域導覽樹**。即使用 prune，那棵「源頭的樹」本身就太大，導致深層頁面仍有 590KB。

### 解法

我們在 `build_docs.py` 的 `build_nav_pages()` 裡，對每個 ticker 目錄寫一個 `.pages` 設定，**只讓 `index.md` 進入導覽**，個別報告頁不進側邊欄：

```python
# 效能修正 #2b — 讓個別的 dated report 不要進全域導覽樹。
# 否則 awesome-pages 會把每一頁報告（約 3,500 頁）都加進 nav……
# 只列出每個 ticker 的 index.md，側邊欄就只剩一個 ticker 一條目；
# 報告頁仍由 MkDocs 正常建置，透過各 ticker 頁內的表格連結進入。
for section in [DST_REPORTS, DST_MARKET_NEWS]:
    if not section.exists():
        continue
    for ticker_dir in section.iterdir():
        if ticker_dir.is_dir():
            write(ticker_dir / ".pages", "nav:\n  - index.md\n")
```

設計重點：**報告頁照常被建置、照常能訪問**——只是它們從「側邊欄條目」降級成「ticker 頁內表格裡的連結」。導覽的職責是「找到某支股票」，而不是「列出那支股票的每一份歷史報告」。

### 結果

```
深層報告頁 HTML   590 KB ──────────▶ 195 KB   (−67%)
側邊欄條目        ~3,500 → 一個 ticker 一條
```

---

## 五、改動四：拿掉沒人用的 `fetch-depth: 0`（clone 2.3GB → ~50MB）

### 問題

CI workflow 裡有這麼一行，看起來人畜無害：

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0          # 給 git-revision-date 外掛抓完整歷史
```

`fetch-depth: 0` 代表 **clone 整個 git 歷史**。對一個「42 個機器人每天 commit 二進位報告」的 repo 來說，歷史裡累積了約 **2.3GB 的 binary blob**。每次 CI 跑都要先把這 2.3GB 拉下來。

而那個註解裡說的 `git-revision-date` 外掛——**根本沒有安裝**。我們是在為一個不存在的功能付完整歷史 clone 的代價。

### 解法

直接移除，回到預設的 shallow checkout：

```yaml
- uses: actions/checkout@v4
  # 淺層 checkout（預設 fetch-depth: 1）。先前的完整歷史 clone
  # （fetch-depth: 0）是為了一個未安裝的 git-revision-date 外掛，
  # 它只是白白花時間 clone 了約 2.3 GB 的二進位歷史。
```

### 結果

```
CI clone 大小     2.3 GB ──────────▶ ~50 MB
```

這是最典型的「**複製貼上一行設定，活了好幾年沒人質疑**」的隱形成本。

---

## 六、改動五：notebook PDF 改連 GitHub raw、截圖 PNG 轉 WebP

### 5a. PDF 不複製，改連 raw（−200MB）

notebook 目錄裡有大量 PDF。原本建置時是直接複製進站台：

```python
for f in list(pdfs) + list(txts) + list(mds):
    copy_file(f, dst_dir / f.name)
```

但 PDF 是「下載型」資源，沒必要佔用 GitHub Pages 的部署空間——它已經在 repo 裡了。改成**只複製文字/markdown，PDF 直接連到 GitHub raw**：

```python
NOTEBOOK_RAW_BASE = "https://raw.githubusercontent.com/yennanliu/finance_data/main/notebook_llm"

# 只複製 text/markdown — PDF 改從 GitHub 連結
for f in txts + mds:
    prepend = SEARCH_EXCLUDE_FM if f.suffix == ".md" else ""
    copy_file(f, dst_dir / f.name, prepend=prepend)

def nb_link(f: Path) -> str:
    # PDF 不隨站台發佈 — 連到 GitHub raw 副本。
    if f.suffix == ".pdf":
        return f"{NOTEBOOK_RAW_BASE}/{ticker_dir.name}/{f.name}"
    ...
```

**取捨**：使用者點 PDF 時會跳轉到 GitHub raw（多一跳），但換來部署 payload 直接少 200MB。對「偶爾被下載」的資源，這個取捨完全划算。

### 5b. 截圖 PNG → WebP（1.33MB → 0.26MB）

README 的 demo 截圖原本是 PNG：

```markdown
<img src="docs/pic/demo_1.png" width="80%" alt="Landing Page"/>
```

轉成 WebP 後：

```markdown
<img src="docs/pic/demo_1.webp" width="80%" alt="Landing Page"/>
```

```
demo 截圖總和   1.33 MB ──────────▶ 0.26 MB   (−80%)
```

WebP 在同等視覺品質下通常比 PNG 小 70–80%，現代瀏覽器全面支援。**截圖、示意圖這類非透明關鍵資產，預設就該用 WebP。**

---

## 七、改動六：報告保留 120 天 + 部署 debounce

### 6a. 120 天保留視窗

站台已發佈 5,028 頁報告，但**沒人會去看一年前某支股票的某日報告**。我們加了一個保留視窗：檔名帶日期、且超過 120 天的報告，建置時不發佈（**原始檔仍保留在 repo，只是不進站台**）。

```python
RETENTION_DAYS = int(os.environ.get("REPORT_RETENTION_DAYS", "120"))
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

def within_retention(f: Path) -> bool:
    """True 代表應該發佈：夠新、無日期、或關閉保留時。
    無日期檔案（手寫頁、index）永遠發佈。"""
    if RETENTION_DAYS <= 0:
        return True
    d = _file_date(f)          # 從檔名解析 YYYY-MM-DD
    if d is None:
        return True            # 無日期 = 手寫頁，一律發佈
    return (TODAY_DATE - d).days <= RETENTION_DAYS

md_files    = [f for f in md_files    if within_retention(f)]
html_files  = [f for f in html_files  if within_retention(f)]
other_files = [f for f in other_files if within_retention(f)]
```

設計重點：**無日期的檔案（手寫導覽頁、index）永遠發佈**——保留視窗只砍「過期的自動產生報告」，不會誤傷人工內容。視窗可由環境變數調整，要全量發佈時設 `REPORT_RETENTION_DAYS=0` 即可。

```
已發佈報告   5,028 → 3,486 頁
```

### 6b. 部署 debounce：從 42 次/天 → 1 次/晚

這是整個專案最隱蔽、卻最傷的問題。原本的 deploy 觸發條件包含所有內容目錄：

```yaml
on:
  push:
    paths:
      - "ai_gen_report/**"
      - "notebook_llm/**"
      - "10-k/**"
      - "10-q/**"
      # ... 還有一堆內容目錄
```

而那些目錄正是 **42 個每日分析任務寫入的地方**。結果就是：每個任務一 push，就觸發一次完整站台（752MB）建置與部署。**每天排隊塞進幾十次全站建置**，CI 永遠在跑、永遠在等。

解法是把觸發條件**只限縮在「站台設定 / 樣式 / 資產」的改動**，內容則由**每晚一次的 cron** 統一發佈：

```yaml
on:
  push:
    branches:
      - main
    # 效能修正 #6 — debounce。內容目錄由約 42 個每日分析任務寫入；
    # 每次 push 都部署 = 每天排隊數十次全站（752MB）建置。
    # 內容改由下方的 nightly cron 統一發佈。
    paths:
      - "mkdocs.yml"
      - "scripts/build_docs.py"
      - ".github/workflows/deploy.yml"
      - "docs/overrides/**"
      - "docs/stylesheets/**"
      - "docs/javascripts/**"
      - "docs/includes/**"
```

```
   改動前                          改動後
   ┌─────────────────┐            ┌─────────────────┐
   │ 任務1 push ─┐    │            │ 任務1 push ─┐    │
   │ 任務2 push ─┼─▶  │            │ 任務2 push ─┤    │
   │  ...        │ 各觸發│          │  ...        ├─▶ 不觸發│
   │ 任務42 push─┘ 一次 │          │ 任務42 push─┘ 部署 │
   │             部署   │          │                  │
   │  = 42 次/天 全站   │          │  每晚 cron ─▶ 1 次│
   │    建置塞車        │          │    統一建置        │
   └─────────────────┘            └─────────────────┘
```

設計重點：**內容更新的「即時性」其實沒那麼重要**——分析報告晚幾小時上線完全可接受。但「站台壞了要馬上修」很重要，所以設定 / 樣式 / 資產的改動仍即時觸發。把這兩種需求拆開，是整個 debounce 的核心判斷。

---

## 八、為什麼選 X 不選 Y

| 決策 | 選的方案 | 為什麼不選另一個 |
|------|----------|------------------|
| 縮搜尋索引 | front matter `search.exclude` | 不選「整站關搜尋」：手寫導覽頁仍需要被搜尋；報告內文才是該排除的 99% |
| 導覽渲染 | `navigation.prune` | 不選 `navigation.expand`：expand 把整棵 5,000 頁樹塞進每一頁，5,000 倍放大 |
| 報告頁導覽 | `.pages` 只列 index.md | 不選「全進側邊欄」：3,500 條側邊欄項目沒有導覽價值，反而拖垮每頁 |
| git checkout | shallow（預設 depth 1） | 不選 `fetch-depth: 0`：完整歷史是為了一個沒安裝的外掛，純浪費 2.3GB clone |
| PDF 發佈 | 連 GitHub raw | 不選「複製進站」：PDF 已在 repo，複製等於把 200MB 二進位資料部署兩次 |
| 截圖格式 | WebP | 不選 PNG：同畫質下 WebP 小 80%，瀏覽器全面支援 |
| 內容部署時機 | nightly cron | 不選「每次 push 即部署」：42 任務 × 752MB 全站建置 = CI 永久塞車；內容不需即時 |

**Flip condition（什麼時候該反過來選）**：

- 若站台只有幾十頁，`navigation.expand` 反而提供更好的瀏覽體驗，不需要 prune。
- 若真的安裝了 `git-revision-date` 之類需要歷史的外掛，`fetch-depth: 0` 就是必要的。
- 若內容需要「即時上線」（例如新聞快報站），就不能 debounce 到 nightly，得改用更細的條件或手動觸發。

---

## 九、系統效應：改動前 vs 改動後

| 指標 | 改動前 | 改動後 | 變化 |
|------|--------|--------|------|
| 搜尋索引 | 195 MB | 0.86 MB | **−99.6%** |
| 首頁 HTML | 1.07 MB | 53 KB | −95% |
| 深層報告頁 HTML | 590 KB | 195 KB | −67% |
| 截圖資產 | 1.33 MB | 0.26 MB | −80% |
| CI clone | 2.3 GB | ~50 MB | −98% |
| 單次部署 payload | 752 MB | 387 MB | −49% |
| 建置完成站台 | ~3.1 GB | 503 MB | **−84%** |
| 每日部署次數 | ~42 次 | 1 次（nightly） | −97% |
| CI 建置 + 部署時間 | ~15 分鐘 | ~6.5 分鐘 | **−57%** |

最有感的兩個體驗變化：**訪客不再下載 195MB 索引**，以及 **CI 不再整天塞車**。

---

## 十、可複用的心法

這次調校沒有用到任何花俏技術，所有改動都是設定層級的。真正的價值在於診斷思路：

1. **找「被無限複製的單位成本」**：5,000 頁 × 每頁 1MB nav、42 次/天 × 752MB 部署——放大器比絕對值更值得修。
2. **問「這東西有人用嗎」**：報告內文的全文搜尋、3,500 條側邊欄、不存在的外掛要的完整歷史——大量成本花在沒人用的功能上。
3. **分離「即時性需求」**：設定要即時部署、內容可以晚幾小時——把兩種需求拆開，就能放心 debounce。
4. **資源放對位置**：PDF 留在 repo 連 raw、截圖用 WebP——不是刪掉，而是用對的形式放在對的地方。
5. **保留視窗而非永久累積**：自動產生的內容若沒有保留策略，必然無限膨脹；加一個可調的視窗就解決。

> 一句話總結：當站台是機器人在寫的，調校的對象不是「檔案」，而是「成本被放大的每一個環節」。

---

**參考連結**

- PR: [perf: cut search index 195MB→<1MB, slim deploy & nav, debounce CI](https://github.com/yennanliu/finance_data/pull/11)
- Repo: [yennanliu/finance_data](https://github.com/yennanliu/finance_data)
- [MkDocs Material — Search 設定](https://squidfunk.github.io/mkdocs-material/setup/setting-up-site-search/)
- [MkDocs Material — Navigation 設定](https://squidfunk.github.io/mkdocs-material/setup/setting-up-navigation/)
