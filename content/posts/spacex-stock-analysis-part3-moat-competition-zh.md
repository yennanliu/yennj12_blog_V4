---
title: "SpaceX 美股深度分析 part 3 - 護城河與競爭者：發射、寬頻、AI 各打一場仗"
date: 2026-10-25T11:00:00+08:00
draft: false
description: "用 competitor-analysis 實跑 SpaceX（SPCX）：發射對 Blue Origin、ULA、Rocket Lab，寬頻對 Amazon Leo 與中國星座，AI 對 OpenAI、Anthropic。前兩場是寬護城河，第三場沒有護城河。"
categories: ["all", "finance"]
tags: ["SPCX", "SpaceX", "美股", "競爭分析", "護城河", "Starlink", "Amazon Leo", "Blue Origin", "InvestSkill", "investing"]
authors: ["yen"]
readTime: "15 min"
---

> 大部分人說 SpaceX 有護城河，理由是「沒有人能像它一樣回收火箭」。
> 這句話對發射成立，對 Starlink 也大致成立。
> 但 SpaceX 現在最大的營收來源是出租 AI 算力，而它最大的客戶同時也是 AI 市場的競爭對手。
> 護城河要一場仗一場仗看：同一家公司，可能一邊是寬護城河，另一邊完全沒有護城河。

---

> ⚠️ **免責聲明**：本文為教育性分析與閱讀筆記，數字引用自公開申報文件與註明出處的公開資料，**不構成任何投資建議或買賣訊號**。投資決策請自行判斷並諮詢專業意見。股價與估值以 **2026-10-23 收盤（$147.49）** 計。
>
> **利益揭露**：本系列的 InvestSkill 分析由 Claude（Anthropic 開發的 AI）在本機執行，文章也由 Claude 協助撰寫。本篇會比較 SpaceX 與 Anthropic 在 AI 市場的競爭關係，而 Anthropic 同時也是 SpaceX 的雲端算力客戶，請讀者自行評估。

---

## 一、護城河是什麼，為什麼要分三場仗看

**直覺**：護城河是「讓競爭對手就算想搶，也搶不走你利潤」的結構性優勢。一家公司今天賺很多錢，不代表有護城河；要看的是十年後對手能不能用更低的成本做到一樣的事。

晨星（Morningstar）的框架把護城河分成五種來源：

| 來源 | 白話解釋 | 例子 |
|---|---|---|
| 成本優勢 | 同樣的東西，你做得比別人便宜 | 可回收火箭 |
| 有效規模 | 市場只容得下少數業者，新進者賺不到錢 | 發射、衛星星系 |
| 無形資產 | 執照、專利、品牌 | 頻譜執照 |
| 轉換成本 | 客戶換供應商很麻煩 | 政府長約、已安裝的天線 |
| 網路效應 | 用的人越多，對每個人越有價值 | 社群平台 |

SpaceX 的三個事業面對三組完全不同的對手，所以這篇把競爭拆成三場仗：

```
                SpaceX
      ┌────────────┼─────────────┐
      ▼            ▼             ▼
    發射之戰       寬頻之戰      AI 之戰
    Blue Origin    Amazon Leo    OpenAI
    ULA            OneWeb        Anthropic（也是客戶）
    Arianespace    AST（D2C）    Google
    Rocket Lab     中國星座      Meta
    中國可回收火箭
```

---

## 二、InvestSkill 怎麼看：competitor-analysis

這篇使用 `competitor-analysis` 技能。SpaceX 的數字只能來自 10-Q、424B4 與手工資料包；競爭對手的數字則開放網路搜尋，並要求註明出處。

![competitor-analysis 對 SpaceX 的執行摘要：發射與寬頻為寬護城河，AI 無護城河，綜合 7.0 分](/images/posts/spacex/03a-competitor-summary.webp)

*技能的結論：發射和 Starlink 各自是寬護城河，SI／AI 沒有護城河。因為 SI 已經是最大的營收部門，綜合護城河分數被拉到 7.0／10，屬於「窄護城河上緣」。*

要先提醒：**競爭對手的數字大多來自新聞報導**，可信度低於 SpaceX 的 SEC 申報文件。技能自己把這部分的信心評為 MEDIUM 到 LOW，本文引用時也會逐項標註來源。

---

## 三、發射之戰：寬護城河，但對手正在追

### SpaceX 的優勢有多大

- **市占**：2025 年送上軌道超過 2,200 公噸，**占全球入軌質量 80% 以上**（424B4）。
- **成本**：NASA 估計第一版 Falcon 9 每公斤約 $2,700，比歷史平均 $18,500 低約 85%（424B4 引述）。之後的助推器重複使用把成本再壓低。
- **可靠度**：Falcon 系列任務成功率超過 99%，單一助推器最多重複飛行 34 次（截至 2026-03-31）。

這是典型的**成本優勢＋有效規模**：SpaceX 每年發射次數越多，固定成本攤得越薄，越能壓低價格；對手發射次數少，單位成本降不下來。

### 對手現況

| 對手 | 主力火箭 | 2026 年現況 | 來源 |
|---|---|---|---|
| Blue Origin | New Glenn | 2026-04 第三次發射把酬載送入錯誤軌道；之後地面試車發生爆炸，發射台受損，報導指計畫 12 月復飛 | Wikipedia、Nasdaq |
| ULA | Vulcan | 目標 2026 年 18–22 次發射，仍在提升頻率 | Spaceflight Now |
| Arianespace | Ariane 6 | 目標 2026 年 7–8 次 | European Spaceflight |
| Rocket Lab | Electron／Neutron | Neutron 尚未首飛，管理層表示早期檔期有限 | Stocktwits |
| 中國 LandSpace | 朱雀三號 | 2026-08 首次在陸地回收一級火箭 | Caixin |

來源由 `competitor-analysis` 與 `industry-map` 技能網路檢索取得，連結見文末。

這張表的重點是：**西方主要對手到 2026 年都還沒穩定地做到可回收重型發射**。中國的朱雀三號是一個警訊，代表技術差距正在縮小，但它主要服務中國市場，對 SpaceX 的國際商業發射影響有限。

### 護城河的裂縫：自己的發射次數在下降

技能特別點出一個反向訊號：

| 指標 | Q3 2025 | Q3 2026 | 變化 |
|---|---|---|---|
| Falcon 發射 | 43 次 | 33 次 | −23% |
| 其中客戶發射 | 15 次 | 12 次 | −20% |
| 入軌質量 | 525 公噸 | 476 公噸 | −9% |

來源：10-Q Key Business Metrics。

10-Q 只說 Space 部門成本下降是因為「客戶發射次數減少」，沒有解釋為什麼減少。技能的判斷是「比較像內部優先序或 Starship 轉型造成，還不是市占流失」，我同意這是最可能的解釋，但這需要用接下來幾季的數據確認。如果客戶發射持續減少、Starship 又遲遲沒有客戶任務，就會變成真正的問題。

---

## 四、寬頻之戰：規模差距一個數量級以上

### 衛星數量

Starlink 和其他 LEO 寬頻星系的規模差距非常大：

```
LEO 寬頻星系在軌衛星數（顆）
Starlink     ██████████████████████████████████  > 11,100   2026-09-30，10-Q
Amazon Leo   █                                    ~ 396      2026-07 初，GeekWire
千帆 Qianfan ▏                                     218       2026-07-04，工信部
國網 Guowang ▏                                     204       2026-09，Wikipedia
```

（OneWeb 的最新衛星數本次未取得，不列入。）

以這張表計算，Starlink 的占比約 93%。Amazon Leo 是唯一財力足以挑戰的對手，但進度落後：FCC 要求在 2026 年 7 月前部署約 1,600 顆，Amazon 已經申請展延（Fierce Network）。而且 Amazon Leo 的部分衛星**還得向 SpaceX 買發射服務**。

### 營收與利潤

| 業者 | 最新營收 | 年增 | 利潤 |
|---|---|---|---|
| **Starlink（Connectivity）** | Q3 2026 $5,248M | +69.5% | 營業利益率 45.1% |
| Eutelsat OneWeb（LEO） | FY2025-26 €297M | +69.5% | 集團營收 €1.23B，持平 |
| Viasat（GEO） | FY2026 $4.64B | +2.7% | Adj. EBITDA 率約 33% |

Starlink 一季的營收，是 OneWeb 一整年 LEO 營收的十幾倍。

### 為什麼這是護城河

衛星寬頻的護城河來自三個互相強化的因素：

```
Starlink 用戶增加 ──▶ 內部發射需求增加 ──▶ Falcon 發射次數增加
        ▲                                      │
        │                                      ▼
網路容量大、延遲低 ◀── 衛星放得多、換得快 ◀── 單次發射成本下降
```

這不是典型的網路效應（多一個用戶不會讓其他用戶的網路變快），而是**成本飛輪**：Starlink 的需求讓 Falcon 有更多發射次數，攤低發射成本，再讓 Starlink 用更低的成本擴充星系。對手要複製，得同時擁有便宜的發射和大量的用戶，這正是 Amazon Leo 面臨的困境。

### 定價權偏弱

這場仗唯一的負面訊號是**價格**。Starlink 消費型 ARPU 從 Q3 2025 的 $83 降到 Q3 2026 的 $69（−17%）；訂戶年增 89%，消費者營收只增加 57%。技能的判讀是「成長靠以量換價，定價能力偏弱」。

不過要分清楚：**降價是 Starlink 自己的選擇**（進入低所得國家、推出便宜方案），不是被對手逼的。真正的定價壓力測試，要等 Amazon Leo 開始大規模商轉之後才會出現。

---

## 五、直連手機之戰：頻譜決定勝負

直連手機（D2C）讓一般手機不用額外裝置就能連衛星。這場仗的關鍵不是火箭，而是**頻譜**：

| | Starlink Mobile | AST SpaceMobile（ASTS） |
|---|---|---|
| 在軌衛星 | 約 650 顆 V1 Mobile（2026-03-31） | 13 顆（2026-08） |
| 用戶規模 | 每月約 740 萬台不重複裝置，約 30 國 | 尚在早期 |
| 營收 | 含在 Enterprise & Government，Q3 $2,127M（+91%） | Q2 2026 $31.5M |
| 頻譜 | 2026-05 以約 $196 億收購 EchoStar 的 AWS-4／H-block | 與電信商合作使用其頻譜 |
| 獲利 | Connectivity 部門獲利 | Q2 淨損 $230.9M |

來源：424B4、10-Q；ASTS 數字取自其 8-K（技能檢索）。

SpaceX 用約 $196 億買下頻譜，等於提前把這場仗最稀缺的投入買到手。這是**無形資產型護城河**：頻譜執照有限，而且受監管，不是有錢就買得到。

---

## 六、AI 之戰：沒有護城河，而且對手就是客戶

這是 SpaceX 最弱的一場仗。

### SI 部門到底在賣什麼

| SI 營收組成（Q3 2026） | 金額 | 說明 |
|---|---|---|
| SI Solutions & Infrastructure | $7,022M | 主要是 GPU 雲端算力出租，另含 Grok、X、Cursor 訂閱 |
| 其中 Customer B（雲端服務） | 約 $5,028M | 推算：34.5% × 合併營收 |
| 其中 Cursor | $608M | 2026-08-14 起併入 |
| X 廣告 | $538M | 年增 18.5% |
| **SI 合計** | **$7,560M** | |

SI 營收約三分之二來自單一雲端客戶。換句話說，**SI 現在主要是一家「GPU 房東」**，而不是一家靠模型或應用賺錢的 AI 公司。

### 和 AI 對手比較

| 指標 | SpaceX SI | OpenAI | Anthropic | Google Cloud |
|---|---|---|---|---|
| 營收規模 | Q3 $7.56B（年化約 $30B，以算力出租為主） | 年化約 $50B（FT，2026-10） | 官方 $47B；Bloomberg 報導 2026-07 逾 $65B | Q2 2026 $24.8B（+82%） |
| 營業利益率 | Q3 5.7%；9M −30.1% | 未揭露 | 未揭露 | — |
| 算力 | 1.7 GW 額定容量 | — | 向 SpaceX 租約 325,000 顆 GPU | 2026 資本支出指引 $195–205B |

OpenAI 與 Anthropic 的數字為媒體報導或私募輪揭露，兩者的營收認列方式也不同，不能直接比較。

### 為什麼說沒有護城河

1. **成本優勢？沒有。** GPU 向 NVIDIA 買，晶片由台積電生產。SpaceX 在這一層是付費者，和其他雲端業者沒有本質差異。
2. **轉換成本？很低。** 公開說明書揭露的 Anthropic 合約，三個月後雙方都可以提前 90 天終止。
3. **客戶就是對手。** Grok 和 Anthropic 的 Claude 在模型市場直接競爭，但 SpaceX 又把算力租給 Anthropic。如果 Customer B 確實是 Anthropic，SI 的營收就有很大一部分取決於一家競爭對手的訓練需求。

一個可能的反駁是：SpaceX 能比別人更快蓋好資料中心（公開說明書宣稱是「第一家部署 GW 級連貫 AI 訓練叢集的公司」），而且長期有軌道 AI 算力的選擇權。但「蓋得快」是執行力，不是結構性優勢；軌道算力則要到 2028 年後才會開始部署。

---

## 七、技能的護城河辨識與五力分析

`competitor-analysis` 把三個事業分別對照五種護城河來源：

![competitor-analysis 的護城河辨識表：發射與 Starlink 在成本優勢與有效規模上評為強，SI 多數項目評為弱](/images/posts/spacex/03b-competitor-moat.webp)

*發射與 Starlink 在成本優勢、有效規模兩欄都是「強」；SI 在成本優勢與轉換成本都是「弱」。證據欄逐項註明出處。*

再用波特五力（Porter's Five Forces）替三個產業打分，5 分代表對 SpaceX 最有利：

| 力量 | 發射 | 寬頻／D2C | AI |
|---|---|---|---|
| 產業內競爭 | 4 | 4 | 1 |
| 新進入者威脅 | 4 | 4 | 3 |
| 供應商議價力 | 4 | 4 | 2 |
| 買方議價力 | 2 | 4 | 1 |
| 替代品威脅 | 4 | 3 | 2 |
| **產業吸引力** | **3.6** | **3.8** | **1.8** |

（技能輸出，分數 1–5。）

發射的「買方議價力」只有 2 分，因為主要買家是美國政府與少數大型衛星業者，議價力很強。AI 的五項幾乎都是低分：競爭極度激烈、供應商（NVIDIA）強勢、大客戶議價力高、替代品（開源模型、超大型雲端）很多。

---

## 八、綜合護城河評分

![competitor-analysis 的綜合護城河評分 7.0 與投資訊號 BULLISH 6.6／HOLD](/images/posts/spacex/03c-competitor-score.webp)

*綜合護城河 7.0／10，計算式列在表下方。最終訊號 BULLISH 6.6，動作 HOLD：技能明確說這是對「業務品質」的評分，不是對進場價位的評分。*

技能用營收占比加權五力分數，所以 SI（Q3 占營收 51.9%）會把整體拖下來。它也提醒，**如果改用營業利益加權，結果會明顯偏向 Starlink**。我認為營業利益加權更能反映價值來源：Q3 的 $2,791M 營業利益中，Connectivity 貢獻了 $2,367M（85%）。

所以我的版本是這樣的：

| 事業 | 護城河 | 趨勢 | 對估值的意義 |
|---|---|---|---|
| 發射 | 寬 | 穩定（但要追蹤 Falcon 發射次數） | 價值主要透過 Starlink 實現 |
| Starlink 寬頻 | 寬 | 加寬 | **SpaceX 價值的核心** |
| 直連手機 | 正在建立（靠頻譜） | 加寬 | 中期成長選擇權 |
| AI 算力／模型 | 無 | 不確定 | 營收大，但不該用護城河等級的倍數估值 |

---

## 九、什麼會讓護城河變窄

把技能的論點失效條件，和我自己的觀察合併成一張追蹤清單：

| 訊號 | 門檻 | 資料來源 |
|---|---|---|
| Amazon Leo 開始大規模商轉 | 在軌衛星超過 1,600 顆 | Amazon 公告、FCC 文件 |
| 對手發射頻率提升 | New Glenn＋Vulcan 年發射合計 > 30 次 | 各公司發射紀錄 |
| Falcon 客戶發射持續下滑 | 連續兩季年減 > 20%，且 Starship 到 2027 年中仍無客戶任務 | 10-Q Key Business Metrics |
| Starlink 定價權惡化 | ARPU 連續兩季年減 > 15%，且 Connectivity 營業利益率 < 35% | 10-Q |
| AI 大客戶流失 | Customer B 終止或大幅縮減合約 | 8-K、10-Q Note 3 |

---

## 十、小結：買的是 Starlink，附贈一家 AI 房東

SpaceX 的護城河是真實的，但集中在發射和 Starlink。這兩個事業互相強化，對手的規模差距達一到兩個數量級，短期內很難追上。

問題在於，SpaceX 現在最大的營收部門是沒有護城河的 AI 算力業務，而它的成長高度依賴一個可以用 90 天通知終止合約的客戶。如果用一句話總結這篇：**投資 SpaceX，買到的是一個寬護城河的 Starlink，加上一家沒有護城河、資本支出巨大的 AI 房東。**

那麼，這兩部分加起來值多少錢？兩兆美元的市值合理嗎？下一篇用 `stock-valuation` 做分部估值。

---

## 系列導航

- [part 1：太空產業全景：誰卡住瓶頸、利潤落在哪裡](/posts/spacex-stock-analysis-part1-space-industry-map-zh/)
- [part 2：拆解財報：三個事業、一張合併報表](/posts/spacex-stock-analysis-part2-financials-zh/)
- **part 3：護城河與競爭者：發射、寬頻、AI 各打一場仗（本篇）**
- [part 4：估值：兩兆美元要怎麼算才合理](/posts/spacex-stock-analysis-part4-valuation-zh/)
- [part 5：空方論點、催化劑與結論](/posts/spacex-stock-analysis-part5-bear-case-catalysts-zh/)

延伸閱讀：[Rocket Lab (RKLB) 2025 10-K 深度解析](/posts/rklb-2025-10k-deep-dive-zh/)。

---

## 資料來源

**SpaceX（一手文件）**

- 424B4 最終公開說明書，2026-06-12，accession 0001628280-26-042639：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm)
- Form 10-Q，季底 2026-09-30，2026-10-22 申報，accession 0001628280-26-066880：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1181412/000162828026066880/spcx-20260930.htm)

**競爭對手（`competitor-analysis` 與 `industry-map` 技能網路檢索，2026-10-25 取得）**

- 發射：[Wikipedia：New Glenn 發射列表](https://en.wikipedia.org/wiki/List_of_New_Glenn_launches)、[Nasdaq：Blue Origin 發射台與復飛](https://www.nasdaq.com/articles/jeff-bezos-blue-origin-scrapped-its-destroyed-launchpad-and-plans-return-flight-december)、[Spaceflight Now：ULA 2026 發射頻率](https://spaceflightnow.com/2026/02/11/ula-sets-sights-on-ramping-up-launch-cadence-in-2026/)、[European Spaceflight：Ariane 6](https://europeanspaceflight.com/?p=5466)、[Stocktwits：Rocket Lab Neutron](https://stocktwits.com/news-articles/markets/equity/rklb-very-very-careful-with-limited-neutron-slots/cZoZh6kRJf1)、[Caixin：朱雀三號回收](https://www.caixinglobal.com/2026-08-19/chinas-landspace-recovers-booster-in-reusable-rocket-breakthrough-102475639.html)
- 寬頻：[GeekWire：Amazon Leo](https://www.geekwire.com/2026/amazon-leo-atlas-ula-launch-satellites/)、[Fierce Network：Amazon Leo 延後](https://www.fierce-network.com/broadband/amazon-leo-pushes-out-its-commercial-service-deadline)、[Wikipedia：國網](https://en.wikipedia.org/wiki/Guowang)、[Wikipedia：千帆](https://en.wikipedia.org/wiki/Qianfan)、[Eutelsat FY2025-26 簡報](https://www.eutelsat.com/system/files/2026-08/DOC_INVESTORS_Presentation-FY-2025-26_EN_070826.pdf)、[Viasat FY2026 10-K](https://www.sec.gov/Archives/edgar/data/0000797721/000119312526248290/vsat-20260331.htm)
- 直連手機：[AST SpaceMobile 8-K](https://www.sec.gov/Archives/edgar/data/0001780312/000119312526342540/asts-ex99_1.htm)
- AI：[Bloomberg Gov（轉引 FT）：OpenAI 年化營收](https://news.bgov.com/artificial-intelligence/openais-annualized-revenue-nears-50-billion-ft-says)、[w.media：Alphabet 2026 資本支出指引](https://w.media/?p=41917)

分析工具：[InvestSkill](https://github.com/yennanliu/InvestSkill)（`competitor-analysis`），執行日期 2026-10-25。
