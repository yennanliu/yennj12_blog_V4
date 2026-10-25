---
title: "Marvell 美股深度分析 part 1 - AI 資料中心晶片產業全景：Marvell 站在哪一層"
date: 2026-10-26T09:00:00+08:00
draft: false
description: "用 InvestSkill 的 industry-map 實跑 Marvell（MRVL）：從台積電、CoWoS、GPU、客製化 XPU 到光電 DSP 與交換器，拆解 AI 資料中心半導體價值鏈，找出誰在收過路費、Marvell 真正的護城河在哪一層。"
categories: ["all", "finance"]
tags: ["MRVL", "Marvell", "美股", "半導體", "AI 晶片", "產業分析", "InvestSkill", "investing"]
authors: ["yen"]
readTime: "15 min"
---

> 大部分人提到 Marvell，會說它是「AI 晶片股」，跟輝達、博通放在同一籃子。
> 稍微懂一點的人會說：Marvell 不做 GPU，它幫雲端業者設計客製化 AI 晶片。
> 但翻開財報會發現，Marvell 最有定價權的產品其實不是 AI 晶片本身，而是把晶片連在一起的光電訊號處理器。
> 想判斷這檔一年內從 74 美元漲到 316 美元、又跌回 228 美元的股票，得先看懂 AI 資料中心晶片的整條產業鏈。

---

> ⚠️ **免責聲明**：本文為教育性分析與閱讀筆記，數字引用自公開申報文件，**不構成任何投資建議或買賣訊號**。投資決策請自行判斷並諮詢專業意見。股價與估值以 **2026-10-23 收盤（$228.51）** 計。
>
> **說明**：本系列的 InvestSkill 分析由 Claude（Anthropic 開發的 AI）在本機執行，文章也由 Claude 協助撰寫；所有數字都對回 SEC 申報文件重新驗算過。

---

## 系列導覽

這個系列分五篇，每篇都**在本機實際跑一次** [InvestSkill](https://github.com/yennanliu/InvestSkill) 的分析技能，把終端機輸出截圖放進文章，再用自己的話解讀。做法和 [SpaceX 系列](/posts/spacex-stock-analysis-part1-space-industry-map-zh/) 相同。

| 篇 | 主題 | 使用的技能 |
|---|---|---|
| **part 1（本篇）** | AI 資料中心晶片產業全景 | `industry-map` |
| part 2 | 拆解財報：資料中心成長與盈餘品質 | `financial-report-analyst`、`fact-check` |
| part 3 | 護城河與競爭者：對上博通、Credo 與台灣設計服務廠 | `competitor-analysis` |
| part 4 | 估值：2,000 億美元市值隱含了什麼 | `stock-valuation` |
| part 5 | 空方論點、催化劑與結論 | `bear-case`、`catalyst-calendar` |

---

## 一、為什麼現在要看 Marvell

Marvell Technology（MRVL）是一家**無晶圓廠（fabless）半導體公司**：它設計晶片，但交給台積電生產。公司把產品歸成兩個終端市場：

| 終端市場 | 主要產品 | FY2026 營收 | 占比 |
|---|---|---|---|
| **資料中心** | 客製化 AI 晶片（XPU）、光電 DSP、交換器晶片、儲存控制器 | $6,100.3M | 74% |
| **通訊與其他** | 企業網路、電信基礎設施、消費性產品 | $2,094.3M | 26% |

來源：FY2026 10-K（會計年度截至 2026-01-31）。

過去一年股價的波動非常劇烈：

```
MRVL 收盤價（US$，Yahoo Finance 日線）
2025-10-24     $84.13
2026-02-04     $73.73   ← 52 週低點
2026-06-04    $316.43   ← 52 週高點，四個月漲 4.3 倍
2026-10-23    $228.51   ← 比高點低 28%
```

以 2026-08-21 的流通股數 876.9M 股計算，市值約 **$2,004 億**。

驅動這波行情的是 AI。資料中心營收兩年內從 $22 億成長到 $61 億：

```
資料中心營收（US$ M）
FY2024    █████████                           2,217   占營收 40%
FY2025    ████████████████                    4,164   占營收 72%
FY2026    ████████████████████████            6,100   占營收 74%
Q2×4      ██████████████████████████████████  8,686   Q2 FY27 年化，占營收 79%
```

兩年年複合成長率約 66%（本文計算）。換句話說，Marvell 在三年內從一家「什麼都做一點」的網通晶片公司，變成一家幾乎純粹押注 AI 資料中心的公司。

---

## 二、怎麼做的：在本機跑 InvestSkill

### 步驟 0：取得財報

和 SpaceX 不同，Marvell 是上市多年的公司，資料齊全。用 `fetch:edgar` 下載最新的 10-K 與 10-Q，再用 `fetch:fundamentals` 從 SEC 的 XBRL 資料產生資料包：

![InvestSkill fetch:edgar 下載 Marvell FY2026 10-K 與 Q2 FY2027 10-Q，fetch:fundamentals 抓出營收與自由現金流](/images/posts/mrvl/00-fetch-edgar.webp)

*10-K（會計年度截至 2026-01-31）存成 442 KB 純文字，10-Q（季底 2026-08-01）303 KB。XBRL 資料包抓到 FY2026 營收 $8,195M、淨利 $2,670M、自由現金流 $1,396M。股價（$228.51）由我手動填入。*

`fetch:fundamentals` 只涵蓋最近一個完整會計年度，所以我另外把 Q2 FY27 的季度數字和 TTM（近四季）計算補進資料包。TTM 一律用「FY2026 − 6M FY2026 + 6M FY2027」計算。

### 步驟 1：跑分析技能

七個技能都以 `claude -p` 在本機無人值守地執行，提示詞限定只能讀 10-K、10-Q 與資料包；需要同業資料的技能（`industry-map`、`competitor-analysis`、`catalyst-calendar`）另外開放網路搜尋並要求註明出處。

| 技能 | 用在 | 執行時間 | 訊號 |
|---|---|---|---|
| `industry-map` | part 1 | 3.6 分鐘 | NEUTRAL 5.4／HOLD |
| `financial-report-analyst` | part 2 | 3.8 分鐘 | NEUTRAL 5.8／HOLD |
| `fact-check` | part 2 | 7.2 分鐘 | 驗證分數 9.6 |
| `competitor-analysis` | part 3 | 7.4 分鐘 | NEUTRAL 4.8／HOLD |
| `stock-valuation` | part 4 | 5.6 分鐘 | BEARISH 2.5／SELL |
| `bear-case` | part 5 | 3.3 分鐘 | BEARISH 3.8／SELL |
| `catalyst-calendar` | part 5 | 3.6 分鐘 | （見 part 5） |

這篇用的是 `industry-map`：

![industry-map 技能對 Marvell 的執行摘要：範圍、價值集中在哪、價值遷移方向](/images/posts/mrvl/01a-industry-map-summary.webp)

*第一行是實際下的指令。摘要的重點：毛利最高的瓶頸是台積電與 NVIDIA；Marvell 毛利率 51–53%，低於上游的台積電與做連接晶片的同業；下一波稀缺可能移到「把晶片連起來」的互連層。*

---

## 三、AI 資料中心晶片的價值鏈

先建立直覺：**一座 AI 資料中心就是幾萬顆運算晶片，加上把它們連在一起的網路**。運算晶片負責算，網路負責讓幾萬顆晶片像一台超級電腦一樣協作。

把這條鏈畫出來：

```
上游（製造）          中游（晶片設計，fabless）                   下游（客戶）

晶圓代工：台積電 ──▶  商用 GPU（NVIDIA、AMD）                     ┐
CoWoS 封裝＋HBM ──▶   客製化 XPU（博通、Marvell★）                ├─▶ 光模組／ODM
                      光電 DSP（Marvell★、博通）                  ├─▶ 雲端業者
                      交換器／Scale-up（博通、NVIDIA、Marvell★）  │   AWS、微軟、
                      儲存控制器（Marvell★）                      ┘   Google、Meta
```

（★ 為 Marvell 所在的節點。）

`industry-map` 技能整理的分層表裡，最值得注意的是每一層的毛利率：

| 層級 | 代表公司 | 集中度 | 最新毛利率（來源期間） |
|---|---|---|---|
| 先進製程晶圓代工 | 台積電 | 近乎獨占 | 66.4%（2026 Q3） |
| 商用 GPU＋CUDA | NVIDIA | 近乎獨占 | 71.1%（FY2026） |
| 客製化 XPU 設計服務 | 博通、Marvell、世芯（Alchip）、創意（GUC） | 寡占，客戶議價力強 | 世芯約 26%（推算） |
| 光電 DSP | Marvell、博通 | 雙寡占 | 兩家都沒有揭露分項 |
| Scale-up 互連 | NVIDIA、博通、Astera Labs、Marvell | 標準還在形成 | Astera Labs 75.7%（2025） |
| AEC／Retimer | Credo、Astera Labs、Marvell | 寡占 | Credo 68.2%（FY2026） |
| 光模組 | Coherent、中際旭創 | 分散 | Coherent 37.5%（FY2026） |

同業數字由技能透過網路檢索取得，來源見文末；世芯毛利率是技能用第三方數據推算的，不是公司公布的數字。

讀這張表的方法很簡單：**毛利率越高，代表這一層越稀缺、越能定價**。台積電和 NVIDIA 在最上面，光模組在最下面。Marvell 的合併毛利率（FY2026 51.0%、Q2 FY27 53.1%）落在中間。

---

## 四、Marvell 同時站在四個節點

`industry-map` 把 Marvell 的業務對應到四個節點：

| 節點 | Marvell 的產品（10-K Item 1） | 角色 |
|---|---|---|
| **客製化 XPU／ASIC** | 5nm、3nm 量產，2nm 開發中；SerDes、die-to-die、客製 HBM 等 IP | 第二大客製化晶片夥伴，挑戰者 |
| **光電互連** | PAM4 與 coherent-lite DSP、TIA、驅動器、AEC DSP、PCIe retimer | **核心護城河** |
| **交換器** | Teralynx（最高 51.2 Tbps）；開發中的 UALink scale-up 交換器；XConn 的 PCIe／CXL 交換器 | 追趕者 |
| **儲存控制器** | HDD／SSD 控制器（10-K：「所有現有 HDD 廠」都在用） | 現金牛，成長慢 |

逐一用白話說明：

- **客製化 XPU**：雲端業者（例如 AWS、Google）想要不用 NVIDIA GPU、自己的 AI 晶片時，會找博通或 Marvell 這種公司一起設計。客戶決定架構，Marvell 提供 IP、設計能力與量產服務。
- **光電 DSP**：資料中心裡的光纖連線，每一端都需要一顆數位訊號處理器把電訊號轉成光訊號。AI 叢集越大，需要的光連線越多，DSP 需求就越大。
- **交換器與 scale-up 互連**：把幾千顆晶片連成一個網路的「路由器」晶片。這一層由博通領先。
- **儲存控制器**：硬碟與 SSD 裡的控制晶片，成熟但穩定。

一個重要的限制：**Marvell 沒有揭露客製化晶片和光電各自的營收**。10-Q 只說資料中心的成長來自「electro-optics, custom, storage, and switching」，所以外界無法精確拆分哪一塊貢獻多少。

---

## 五、瓶頸分析：誰在收過路費

`industry-map` 用四個因子（供應稀缺、可替代性、轉換成本、需求不彈性）替每一層打分：

![industry-map 的瓶頸評分：台積電 9.5 最高，光電 DSP 7.5，客製化 XPU 6.5，儲存控制器 5.3](/images/posts/mrvl/01b-industry-map-chokepoints.webp)

*台積電 9.5 分、GPU 與 CoWoS 各 8.3 分。Marvell 的四個節點中，光電 DSP 最高（7.5），客製化 XPU 只有 6.5：雖然營收規模大，但客戶擁有架構，可以換夥伴或自己做。*

技能下了一個很直白的結論：「**真正收過路費的是台積電**……從軍火商的角度看，最好的標的是 TSM，不是 MRVL。」

這句話的邏輯是：不管最後是 NVIDIA 的 GPU、博通的 XPU 還是 Marvell 的 XPU 勝出，每一顆晶片都要經過台積電的先進製程和 CoWoS 封裝。Marvell 則夾在中間：

```
上游：台積電（毛利 66%）         ← 議價力在供應商
          │
          ▼
中游：Marvell（毛利 51–53%）
          │
          ▼
下游：少數雲端業者               ← 議價力在買方
      前十大客戶占 FY2026 營收 82%
```

兩邊的議價力都不在 Marvell 手上。唯一明確站在 Marvell 這邊的，是**光電 DSP 這一層**：主要供應商只有 Marvell 和博通兩家。

### 客製化 XPU 為什麼不是好瓶頸

技能用世芯（Alchip）的例子說明這一層的風險：世芯 2025 年營收從 $16 億掉到 $9.92 億，原因是失去最大客戶的一個產品世代。設計夥伴是可以**整代被換掉**的。

更直接的證據來自 Marvell 自己。2026-08-18，Marvell 發給一位客戶最多 **5,897 萬股**的認股權證，履約價 $206.58，依營收里程碑在 FY27 Q3 到 FY33 之間分批既得（10-Q Note 15）。這相當於流通股的約 6.7%。**要用股權換訂單，代表議價力在客戶手上。**（10-Q 沒有點名這位客戶；part 3 會討論媒體報導。）

---

## 六、價值遷移：下一個瓶頸在互連

技能提出的價值遷移假說是：**運算晶片的供給追上需求之後，稀缺性會移往「把晶片連起來」的互連層**。

原因是 AI 叢集越做越大：從一個機櫃（幾十顆 GPU）擴大到多個機櫃、甚至多個資料中心園區（幾十萬顆晶片）。晶片之間的頻寬、延遲和功耗，會成為新的瓶頸。

Marvell 在這個方向上的布局：

| 布局 | 內容 | 狀態 |
|---|---|---|
| Celestial AI 收購 | Photonic Fabric 光子互連平台，用光取代銅線做 scale-up | 2026-02-02 完成，$35 億；10-Q 說營收「not material」 |
| XConn 收購 | PCIe／CXL 交換晶片，補強 UALink 交換器團隊 | 2026-02-10 完成 |
| NVIDIA 策略合作 | 讓 Marvell 的客製化 XPU 接上 NVIDIA 的 NVLink 生態系；NVIDIA 以 $20 億認購可轉換特別股 | 2026-03-31 完成 |
| 共封裝光學（CPO）、LPO | 把光學元件直接封裝在晶片旁邊 | 產品開發中 |

CPO 和 LPO 對 Marvell 是一把雙面刃：

- **不利**：這些技術可能減少獨立光電 DSP 的需求，侵蝕 Marvell 現在的護城河。
- **有利**：如果 Marvell 自己的 CPO 和 Photonic Fabric 被採用，價值會從光模組廠移到晶片廠。

技能列出三個確認訊號：Celestial 開始揭露營收、UALink 交換器拿到量產設計案，以及 5,897 萬股認股權證開始依營收里程碑既得。

---

## 七、集中度與供應鏈風險

| 風險 | 證據（申報文件） | 嚴重度 |
|---|---|---|
| 台灣單點 | 10-K：多數產品由台灣的第三方晶圓廠製造；替代的先進製程晶圓廠「有限」 | 高 |
| 客戶集中 | 前十大客戶占 FY2026 營收 82%；Distributor A 占 Q2 FY27 營收 44% | 高 |
| 客戶自研 | 10-K：大型雲端業者已在投資自研晶片，AI 設計工具可能加速這個趨勢 | 中高 |
| 中國與出口管制 | Q2 FY27 依出貨地計，中國占 42%（10-K 說多數是非中國客戶的在地代工廠） | 中 |
| 採購承諾 | 對晶圓廠與封測廠的無條件採購承諾 $85.2 億（2026-08-01） | 中 |

最後一項值得特別注意：無條件採購承諾從 FY2026 年底的 $26.7 億，半年內增加到 **$85.2 億**（10-Q Note 9）。這代表管理層對需求很有信心，提前鎖產能；但如果 AI 需求放緩，這些承諾不會跟著減少。

---

## 八、小結：位置不錯，但不是收過路費的那一層

`industry-map` 的最終訊號：

![industry-map 對 Marvell 的投資意涵與訊號：NEUTRAL 5.4／HOLD](/images/posts/mrvl/01c-industry-map-signal.webp)

*技能的結論：「產業位置偏多，估值和議價力結構偏空，綜合為中性。」NEUTRAL 5.4，動作 HOLD。*

我的整理：

| 問題 | 答案 |
|---|---|
| Marvell 在哪一層？ | 中游晶片設計層，同時占客製化 XPU、光電 DSP、交換器、儲存控制器四個節點 |
| 真正的護城河？ | 光電 DSP（和博通雙寡占） |
| 營收最大的業務？ | 推測是客製化 XPU，但毛利偏低、客戶議價力強（財報未分項揭露） |
| 誰收過路費？ | 台積電，其次是 NVIDIA |
| 下一個機會？ | 互連層（Celestial、UALink、CPO），目前營收「not material」 |
| 估值？ | EV／TTM 營收約 21 倍，已經反映不少成長（part 4 詳細計算） |

產業分析告訴我們 Marvell **站的位置不錯**：它踩在 AI 資料中心成長最快的兩條線上（客製化晶片、光互連）。但它也告訴我們，這個位置**夾在強勢的供應商和強勢的客戶之間**。下一篇用財報驗證：成長的品質如何？

---

## 系列導航

- **part 1：AI 資料中心晶片產業全景（本篇）**
- part 2：拆解財報：資料中心成長與盈餘品質
- part 3：護城河與競爭者：對上博通、Credo 與台灣設計服務廠
- part 4：估值：2,000 億美元市值隱含了什麼
- part 5：空方論點、催化劑與結論

延伸閱讀：[SpaceX 美股深度分析系列](/posts/spacex-stock-analysis-part1-space-industry-map-zh/)、[AMD 2025 10-K 深度解析](/posts/amd-2025-10k-deep-dive-zh/)、[InvestSkill 介紹](/posts/investskill-claude-code-financial-analysis-plugin/)。

---

## 資料來源

- Marvell FY2026 10-K，2026-03-11 申報，accession 0001835632-26-000011：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1835632/000183563226000011/mrvl-20260131.htm)
- Marvell Q2 FY2027 10-Q，2026-08-28 申報，accession 0001835632-26-000025：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1835632/000183563226000025/mrvl-20260801.htm)
- XBRL companyfacts（FY2021–FY2026 歷史營收）：[SEC](https://data.sec.gov/api/xbrl/companyfacts/CIK0001835632.json)
- 股價：Yahoo Finance chart API 日線收盤，取得於 2026-10-25
- 同業數字（`industry-map` 技能網路檢索）：[台積電 3Q26 新聞稿](https://pr.tsmc.com/english/news/3346)、[NVIDIA Q4 FY26 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000019/q4fy26pr.htm)、[Credo FY26 8-K](https://www.sec.gov/Archives/edgar/data/0001807794/000162828026039474/credoq42026ex-991.htm)、[Astera Labs 2025 財報](https://asteralabs.gcs-web.com/news-releases/news-release-details/astera-labs-reports-fourth-quarter-and-full-year-2025-financial)、[Coherent FY26](https://coherent.gcs-web.com/node/17126/pdf)、[世芯 2025（SemiWiki）](https://www.semiwiki.com/forum/threads/alchip-technologies-reports-q4-and-2025-fy-financial-results.24811/)
- 分析工具：[InvestSkill](https://github.com/yennanliu/InvestSkill)（`fetch:edgar`、`fetch:fundamentals`、`industry-map`），執行日期 2026-10-25
