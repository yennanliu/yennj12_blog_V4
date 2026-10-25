---
title: "Marvell 美股深度分析 part 3 - 護城河與競爭者：對上博通、Credo 與台灣設計服務廠"
date: 2026-10-26T11:00:00+08:00
draft: false
description: "用 competitor-analysis 實跑 Marvell（MRVL）：客製化 AI 晶片被博通與台灣設計服務廠兩面夾擊，光電互連面對 Credo、Astera Labs 與 NVIDIA 自研。絕對成長很強，相對市占卻在下滑，綜合護城河只有 5.2 分。"
categories: ["all", "finance"]
tags: ["MRVL", "Marvell", "美股", "競爭分析", "護城河", "Broadcom", "ASIC", "InvestSkill", "investing"]
authors: ["yen"]
readTime: "14 min"
---

> 大部分人看 Marvell，看到資料中心營收年增 46%，覺得它是 AI 大贏家。
> 但同一季，博通的 AI 營收年增 221%，Credo 年增 115%，Astera Labs 年增 104%。
> 在一個整體高速成長的市場裡，成長得比對手慢，代表市占正在流失。
> 這篇把 Marvell 放回競爭者中間比較：它的護城河在哪裡，又在哪裡被侵蝕。

---

> ⚠️ **免責聲明**：本文為教育性分析與閱讀筆記，數字引用自公開申報文件與註明出處的公開資料，**不構成任何投資建議或買賣訊號**。投資決策請自行判斷並諮詢專業意見。股價與估值以 **2026-10-23 收盤（$228.51）** 計。
>
> **說明**：本系列的 InvestSkill 分析由 Claude（Anthropic 開發的 AI）在本機執行，文章也由 Claude 協助撰寫。競爭者數字由技能透過網路檢索取得，可信度低於 SEC 申報文件，引用時逐項標註來源。

---

## 一、Marvell 打的三場仗

Marvell 的資料中心業務面對三組不同的對手：

```
                   Marvell
       ┌──────────────┼───────────────┐
       ▼              ▼               ▼
   客製化 AI 晶片   光電與互連      交換器晶片
   博通（龍頭）     博通            博通（龍頭）
   世芯 Alchip      Credo           NVIDIA
   創意 GUC         Astera Labs     Cisco
   聯發科           NVIDIA 自研
```

三場仗有一個共同的對手：**博通（Broadcom）**。它在客製化晶片和交換器都是龍頭，在光電 DSP 也是 Marvell 的主要對手。

---

## 二、InvestSkill 怎麼看：competitor-analysis

![competitor-analysis 對 Marvell 的執行摘要與護城河辨識：窄護城河邊緣，趨勢收窄中](/images/posts/mrvl/03a-competitor-moat.webp)

*技能的判定：「窄護城河，處於『無明確護城河』的邊緣，趨勢『收窄中』。」Marvell 有真實的智慧財產與轉換成本，但三個主要戰場的對手規模都比它大一個數量級。*

技能逐項檢查五種護城河來源：

| 護城河來源 | 判定 | 證據 |
|---|---|---|
| 網路效應 | ✗ | B2B 元件；UALink 等是開放標準 |
| 成本優勢 | ✗（相對劣勢） | 博通季營收 $296 億，Marvell $27 億，採購與研發的規模都輸 |
| 無形資產 | ◐ 中度 | 超過 10,000 件已核准與申請中的專利；2nm／1.4nm 平台、CPO、矽光子 |
| 轉換成本 | ◐ 中度但有週期性 | 同一代客製晶片很難替換，但**每換一代就重新競標** |
| 有效規模 | ◐ 弱 | 高階客製 ASIC 只容得下少數業者，但第一名是博通 |

「轉換成本有週期性」是理解 Marvell 最重要的一點。客製化晶片的合作通常是：雲端業者和設計夥伴一起開發一代晶片，量產兩三年；下一代再重新選夥伴。所以 Marvell 的客戶關係**每兩三年就要重新贏一次**。

---

## 三、第一場仗：客製化 AI 晶片

### 市場結構

依技能引用的第三方估計，博通占客製化 AI ASIC 市場約 60–85%，Marvell 約 8–12%。這些數字都是分析師估計，不同來源差異很大，只能當作量級參考。

用兩家公司自己公布的數字比較，差距同樣明顯（季底都在 2026 年 8 月初）：

| 指標 | 博通 Q3 FY26 | Marvell Q2 FY27 |
|---|---|---|
| AI／資料中心營收 | AI 半導體 $167 億，年增 221% | 資料中心 $21.7 億，年增 46% |

博通的 AI 營收約是 Marvell 整個資料中心營收的 **7.7 倍**，而且成長得更快。兩者口徑不同（Marvell 的資料中心還包含儲存與傳統網通），但方向很清楚。

### 兩面夾擊

Marvell 在這場仗裡被夾在中間：

```
博通：AI 半導體營收 $167 億／季，高毛利、規模大
            ▲
            │ 夾擊
         Marvell
            │
            ▼
世芯、創意、聯發科：報價低、毛利低
```

技能整理的設計案動態（**全部是分析師或媒體說法，公司未證實**）：

- **AWS Trainium 3／4**：Benchmark 分析師認為已轉給世芯；世芯北美營收占比從 2026 Q1 的 23% 跳到 Q2 的 51%，與這個說法吻合。RBC 則認為會是雙供應商。
- **Google**：媒體報導 Marvell 在 2026-07 和 Google 簽下新的客製晶片協議，而那張 5,897 萬股的認股權證就是發給 Google。10-Q 沒有點名客戶，但報導的股數與履約價和 10-Q 一致。
- **聯發科**：已切入 Google TPU 專案，目標 2027 年取得 15–20% 市占（聯發科 2Q26 法說稿）。

如果這些說法屬實，Marvell 的處境是：**失去一個大客戶的一代產品，又用股權換回另一個大客戶**。這正是技能說「買方議價力明顯上升」的原因。

---

## 四、第二場仗：光電與互連

這是 Marvell 最強的一塊。在 PAM4 光電 DSP 上，主要供應商是 Marvell 和博通兩家；10-K 稱自己有「industry-leading PAM technology」。

但這個市場正在被三方面侵蝕：

| 威脅 | 說明 |
|---|---|
| Credo、Astera Labs | 從主動電纜（AEC）、Retimer 切入，成長極快：最近一季營收年增 115% 與 104% |
| NVIDIA 自研 | 技能引用的產業分析指出 NVIDIA 正在自研 1.6T DSP（定性資料，未量化） |
| CPO／LPO 技術 | 把光學元件直接封裝在晶片旁，可能減少獨立 DSP 的需求 |

Marvell 的防守是 Celestial AI 的 Photonic Fabric（用光做 scale-up 互連）和自己的 CPO 產品。如果成功，可以跨入 Credo、Astera Labs 以銅線為主的領域；但目前 Celestial 的營收「not material」。

---

## 五、財務對標：成長、毛利、效率

先看成長。最近一季的營收年增率：

```
最近一季營收年增率（%）
Credo         ██████████████████████████████████  +115%
Astera Labs   ███████████████████████████████     +104%
Broadcom      █████████████████████████           +86%
Marvell       ███████████                         +36.5%
Coherent      ██████████                          +33.8%
```

（各公司季底不同，數字由技能檢索自各公司財報新聞稿或 8-K，見文末。）

再看毛利率：

```
最近一季 GAAP 毛利率（%）
Astera Labs   ██████████████████████████████████  73.3%
Broadcom      ████████████████████████████████    69.1%
Credo         ██████████████████████████████      64.5%
Marvell       █████████████████████████           53.1%
Coherent      ██████████████████                  38.5%
世芯 Alchip   ████████████████                    34.8%
```

Marvell 的毛利率剛好落在「產品型」業者（Astera、博通、Credo，65–75%）和「設計服務型」業者（世芯，約 35%）之間。技能的解讀是：**客製化 ASIC 業務本質上更接近代工服務**，晶圓成本直接轉嫁給客戶，拉低了 Marvell 的整體毛利率。

最後看研發效率，也就是每花 $1 研發，能產生多少毛利：

```
每 $1 研發創造的毛利（倍）
Broadcom      ██████████████████████████████████  7.05x
Coherent      ██████████████████                  3.63x
Credo         █████████████                       2.70x
Astera Labs   ██████████                          2.12x
Marvell       █████████                           1.96x
```

Marvell 在美國同業中最低。原因之一是 Q2 研發費用年增 42.8%，包含併購 Celestial 與 XConn 帶入的人員，投資還沒有轉成營收。

![competitor-analysis 的競爭對標表與資本報酬計算](/images/posts/mrvl/03b-competitor-benchmark.webp)

*技能把 Marvell 與 8 家同業並排比較。表下的資本報酬是用申報數字計算的：含商譽的 ROIC 約 7%，排除商譽約 23%。*

### ROIC：併購溢價稀釋了報酬

投入資本報酬率（ROIC）是「每一塊投入的資本，每年賺回多少」。技能的計算：

| 指標 | TTM |
|---|---|
| 營業利益 | $1,561.4M |
| 投入資本（權益＋負債−現金） | $19,561.7M |
| **ROIC（含商譽）** | **約 6.9%** |
| ROIC（扣除商譽 $13,873.9M） | 約 23.9% |

（稅率假設約 13%，技能計算。）

這兩個數字一起看很有意思：**營運本身的報酬很好（約 23%），但歷次併購（Cavium、Inphi、Innovium、Celestial）付出的溢價，把整體報酬稀釋到低於半導體業約 10% 的資本成本**。換句話說，Marvell 過去的併購還沒有證明自己創造了價值。

---

## 六、定價權：認股權證是最重要的訊號

| 證據 | 方向 |
|---|---|
| 毛利率 41.3%（FY25）→ 51.0%（FY26）→ 53.1%（Q2 FY27） | ↑，但 10-Q 歸因於產能吸收與產品組合，不是漲價 |
| 毛利率比 Credo、Astera、博通低 10–20 個百分點 | ↓ 同類產品議價力較弱 |
| 客戶認股權證：FY25 420 萬股、FY26 100 萬股、2026-08 **5,897 萬股** | ↓↓ 以股權換訂單，會計上沖減營收 |
| 10-K：平均售價持續面臨壓力 | ↓ |

最後一張認股權證的規模，是前兩張加起來的 11 倍以上。技能說：「這是本次分析中最重要的單一競爭訊號。」以 $228.51 計算，這張權證已經價內（履約價 $206.58）。

---

## 七、護城河綜合評分

![competitor-analysis 的定價權分析與護城河綜合評分 5.2](/images/posts/mrvl/03c-competitor-score.webp)

*綜合護城河分數 5.2／10，屬「無明確護城河（4–6 分）的上緣，接近窄護城河」。競爭地位只拿 4 分：絕對成長強，但落後博通、Credo 與 Astera Labs。*

| 項目 | 權重 | 分數 |
|---|---|---|
| 護城河來源強度 | 25% | 6.0 |
| 護城河持久性 | 20% | 5.0 |
| 競爭地位 | 20% | 4.0 |
| 產業吸引力（五力 2.4 × 2） | 15% | 4.8 |
| 定價權 | 10% | 5.0 |
| 創新定位 | 10% | 6.5 |
| **綜合** | 100% | **5.2** |

技能的最終訊號是 **NEUTRAL 4.8／HOLD**。

---

## 八、多方的反駁

公平起見，Marvell 的競爭地位也有幾個強的論點：

1. **兩大生態系同時押注 Marvell。** NVIDIA 以 $20 億認購特別股，把 Marvell 的客製化 XPU 接進 NVLink 生態系；媒體報導 Google 也簽了新協議。
2. **管理層反應很快。** 2026 年 2 月完成兩筆收購，3 月引進 NVIDIA，7 月簽下 Google，在傳出 Trainium 失守後兩季內補上新的大客戶（技能整理）。
3. **認股權證也可以是好消息。** 它依營收里程碑既得，等於客戶承諾了多年的大額採購。如果里程碑全部達成，代表一份很大的長期合約。
4. **光互連的路線圖完整。** 從 DSP、CPO、LPO 到 Photonic Fabric，Marvell 在每一條技術路線上都有產品，替代風險被部分對沖。

---

## 九、追蹤清單

| 訊號 | 偏多 | 偏空 |
|---|---|---|
| 資料中心成長 vs 博通 | 連續兩季達到博通 AI 營收成長率的一半以上 | 持續大幅落後 |
| 客戶設計案 | 認股權證開始依營收里程碑既得 | 證實失去前三大客製專案，或 Customer A 占比跌破 10% |
| 毛利率 | 往 56% 以上移動（產品組合轉向互連） | 連續兩季低於 50% |
| 光互連 | Celestial 或 UALink 交換器公開量產設計案 | NVIDIA 自研 DSP 在 1.6T 世代取得過半連接埠 |

---

## 十、小結：成長的市場、收窄的護城河

Marvell 處在一個非常好的市場裡：AI 資料中心的客製化晶片和光互連都在高速成長。但競爭分析顯示：

- **在客製化晶片，它是第二名，而且被博通和台灣設計服務廠兩面夾擊**；
- **在光電互連，它有真正的護城河，但面臨新進者、NVIDIA 自研和新技術三方面的侵蝕**；
- **它需要用股權換訂單**，代表定價權在客戶手上。

用一句話總結：**Marvell 是 AI 浪潮的受益者，但不是定價者**。下一篇算估值：在這樣的競爭地位下，2,000 億美元的市值合理嗎？

---

## 系列導航

- [part 1：AI 資料中心晶片產業全景：Marvell 站在哪一層](/posts/mrvl-stock-analysis-part1-ai-chip-industry-map-zh/)
- [part 2：拆解財報：資料中心成長與盈餘品質](/posts/mrvl-stock-analysis-part2-financials-zh/)
- **part 3：護城河與競爭者：對上博通、Credo 與台灣設計服務廠（本篇）**
- [part 4：估值：2,000 億美元市值隱含了什麼](/posts/mrvl-stock-analysis-part4-valuation-zh/)
- [part 5：空方論點、催化劑與結論](/posts/mrvl-stock-analysis-part5-bear-case-catalysts-zh/)

---

## 資料來源

**Marvell（一手文件）**

- FY2026 10-K，2026-03-11，accession 0001835632-26-000011：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1835632/000183563226000011/mrvl-20260131.htm)
- Q2 FY2027 10-Q，2026-08-28，accession 0001835632-26-000025：[SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1835632/000183563226000025/mrvl-20260801.htm)

**競爭者（`competitor-analysis` 技能網路檢索，2026-10-25 取得）**

- 財報：[博通 Q3 FY26 8-K](https://www.sec.gov/Archives/edgar/data/0001730168/000173016826000076/avgo-08022026x8kxex99.htm)、[Credo Q1 FY27](https://www.sec.gov/Archives/edgar/data/0001807794/000162828026059795/credoq12027ex-991.htm)、[Astera Labs Q2 2026](https://www.asteralabs.com/news/astera-labs-reports-second-quarter-2026-financial-results/)、[Coherent FY26](https://www.sec.gov/Archives/edgar/data/0000820318/000119312526346860/d128030dex991.htm)、[世芯 Q2 2026](https://www.financialcontent.com/article/gnwcq-2026-8-26-alchip-technologies-reports-2026-second-quarter-financial-results)、[聯發科 2Q26 法說稿](https://www.mediatek.com/hubfs/MediaTek%20Assets/Pdfs/Quarterly%20Earnings%20Release/2026/Quarterly%20Earnings%20Release-2026Q2/Prepared%20remarks.pdf)
- 市占與設計案（分析師或媒體說法）：[Motley Fool：Marvell vs Broadcom](https://www.fool.com/investing/2026/06/30/better-custom-asic-stock-marvell-vs-broadcom/)、[Benchmark 降評（Trainium）](https://finviz.com/news/251291/marvell-mrvl-stock-downgraded-as-concerns-grow-over-amazon-trainium-transitions)、[Evertiq：Marvell 與 Google 擴大合作](https://evertiq.com/design/2026-08-20-marvell-and-google-expand-custom-silicon-partnership)、[光電 DSP 競爭（定性）](https://globaltechresearch.substack.com/p/whats-going-on-with-marvell-mrvl)

分析工具：[InvestSkill](https://github.com/yennanliu/InvestSkill)（`competitor-analysis`），執行日期 2026-10-25。
