---
title: "DE 系統設計面試指南 Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板"
date: 2026-11-24T11:30:00+08:00
draft: false
weight: 15
description: "資安 SaaS 的資料平台模擬面試：2,000 個租戶、每天 3 TB 的端點、防火牆、DNS、雲端稽核與登入日誌，如何正規化成 OCSF、在一分鐘內做有狀態的偵測、讓最大租戶不拖垮其他人，以及為什麼熱層的查詢引擎決定了每 GB 的成本。"
categories: ["all", "engineering", "architecture"]
tags: ["RKK", "Interview", "Data Engineering", "System Design", "Mock Interview", "Cybersecurity", "Multi-Tenancy", "OCSF", "ClickHouse", "Flink", "AWS"]
authors: ["yen"]
readTime: "17 min"
series: ["de-system-design-interview"]
---

> 多數人遇到資安平台題，第一反應是「把所有日誌丟進 Elasticsearch，再寫幾條規則」。  
> 然後面試官問：「最大的客戶上線那天，其他 1,999 家的告警都慢了十分鐘，你怎麼發現、怎麼擋？」  
> 資安 SaaS 的難處不在偵測規則本身，而在**同一套管線要同時服務 2,000 個大小差一千倍、彼此絕不能看見對方資料的客戶，而且成本要算得出每 GB 多少錢**。  
> 這一題考的是你會不會把「隔離、新鮮度分層、單位成本」當成三個同等重要的設計輸入。

Part 6 到 Part 9 的四個產業案例，消費者都在公司內部。本篇換成 **B2B SaaS**：消費者是 2,000 家客戶的資安分析師，資料是客戶的、規則是我們的、帳單依 GB 計價。它把 [Part 10](/posts/de-system-design-interview-part10-freshness-sla-tiers-zh/) 的新鮮度分級、[Part 12](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/) 的晚到處理、[Part 13](/posts/de-system-design-interview-part13-schema-evolution-zh/) 的 schema 演進和 [Part 14](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/) 的儲存效率放進同一題，基本概念請回到各篇，本篇只談它們在多租戶資安情境下的取捨。

---

## 面試情境

> **面試官**：「我們是一家資安 SaaS，2,000 家企業客戶把端點代理程式事件、防火牆與 VPN、DNS、雲端稽核日誌（例如 AWS CloudTrail）和身分提供者的登入日誌送進來，平均每天合計 3 TB，還在成長。每家客戶要有自己的安全儀表板：各嚴重度的告警數、風險最高的主機與使用者、MTTD 與 MTTR，並且能從告警下鑽到原始事件做調查。最大的客戶是最小的一千倍，有些歐洲客戶要求資料不能離開歐盟。請設計這個資料平台。」

---

## 一、這一題在考什麼

和前面的案例並排，就看得出這題多了哪些維度。

| 面向 | 點擊流（Part 5） | 支付（Part 6） | 資安 SaaS（本篇） |
|---|---|---|---|
| 資料屬於誰 | 公司自己 | 公司自己 | **每個租戶各自擁有**，互不可見 |
| 一筆資料的價值 | 極低 | 每筆都是錢 | 平常極低；**某一筆**可能就是入侵的唯一證據 |
| 資料缺漏的後果 | 指標略低 | 對帳差異 | 儀表板顯示「沒有威脅」，客戶以為很安全 |
| 新鮮度 | 一種 | 一種（T+1） | 三種：偵測秒級、儀表板分鐘級、合規報表每日 |
| 成本怎麼看 | 平台總成本 | 平台總成本 | **每 GB 擷取的成本**，直接決定毛利 |

所以三個主軸是：**多租戶隔離與吵鬧鄰居**、**依新鮮度拆開的偵測與分析路徑**、**以每 GB 成本選擇儲存引擎**。只談 SIEM 功能而不談租戶，是這題最常見的失分方式。

---

## 二、0–10 分鐘：釐清與估算

> **候選人**：「先確認資料怎麼進來。端點事件是我們自己的代理程式推送，其他來源呢？」
>
> **面試官**：「代理程式用 HTTPS 批次推送。防火牆用 syslog 送到我們在客戶端部署的收集器。雲端稽核日誌是我們從客戶的 S3 bucket 拉取，身分提供者是呼叫它的 API 拉取。」
>
> **候選人**：「所以有推、有拉，而且拉取的來源天生就是批次、會延遲幾分鐘。偵測規則是誰寫的？客戶能自訂嗎？」
>
> **面試官**：「我們提供約 500 條內建規則，大客戶可以自訂。」
>
> **候選人**：「告警要多快？儀表板呢？」
>
> **面試官**：「高嚴重度告警希望一分鐘內出現。儀表板幾分鐘的延遲可以接受。合規報表每月給稽核，每天產一次就好。」
>
> **候選人**：「原始事件的搜尋要保留多久？查詢的型態是什麼？」
>
> **面試官**：「標準方案 30 天可以互動式搜尋、資料保留一年，更長的保留是加價方案。分析師通常是『這台主機過去 7 天連過哪些 IP』這種查詢，偶爾會對一整年的資料做威脅獵捕。」
>
> **候選人**：「我們的支援工程師能看客戶的資料嗎？客戶需要知道誰看過嗎？」
>
> **面試官**：「需要客戶授權，而且客戶要能查到存取紀錄。」

**評註**：「推還是拉」問出了晚到資料的來源；「查詢型態」決定了熱層要用倒排索引還是欄式儲存，這是本題成本最大的決定；最後一個問題把稽核紀錄變成正式需求，而不是事後補上的功能。

估算（假設原始事件平均 1 KB：DNS 約 0.3 KB、CloudTrail 約 1–2 KB；工作時段尖峰為平均的 3 倍；欄式壓縮比 8 倍、gzip 10 倍、倒排索引大小約為原始的 1.1 倍）：

```
tenants                  = 2,000      avg 3 TB / 2,000 = 1.5 GB per tenant/day
events/day               = 3 TB / 1 KB                 = 3,000,000,000
avg events/s             = 3B / 86,400                 ≈ 34,700 /s
peak events/s            = 34,700 × 3                  ≈ 104,000 /s  (~104 MB/s)
design target            = peak + agent reconnect bursts ≈ 150,000 /s

skew  smallest tenant    = 0.15 GB/day ≈ 150,000 events/day ≈ 2 /s
      largest tenant     = 150 GB/day (5% of total)    ≈ 1,740 /s avg
      ratio              = 150 / 0.15                   = 1,000×

hot 30 days (raw)        = 3 TB × 30                   = 90 TB
  columnar, 2 replicas   = 90 / 8 × 2                  ≈ 22.5 TB on disk
  inverted index, 1 rep. = 90 × 1.1 × 2                ≈ 198 TB on disk
cold 1 year (Parquet)    = 3 TB × 365 / 8              ≈ 137 TB
raw archive 90 days      = 3 TB × 90 / 10              = 27 TB
monthly ingest           = 3 TB × 30                   = 90 TB = 90,000 GB
```

> **候選人**：「三個數字決定設計。第一，尖峰每秒十萬筆、約 100 MB/s，一個中型的 Kafka 加串流叢集就處理得了，吞吐量不是難點。第二，熱層 30 天如果用倒排索引約 198 TB，用欄式儲存約 22.5 TB，差了將近 9 倍，這個選擇會主導每 GB 的成本，我等一下會專門討論。第三，最小租戶每秒只有 2 筆，最大的每秒上千筆，所以『每個租戶一套表』在長尾端會產生大量的小檔與小分片，而『全部共用』在頭部會有吵鬧鄰居，兩端要用不同的策略。」

**評註**：估算直接導出三個後續要深挖的主題，而且每個都附了數字。注意候選人沒有在吞吐量上多花時間——這和 [Part 6](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/) 用估算排除方向是同一個技巧。

---

## 三、10–15 分鐘：資料契約——正規化到 OCSF

> **候選人**：「來源有幾十種格式，偵測規則和儀表板不可能每種各寫一份。我會在擷取時正規化成一個共同的 schema。與其自己發明，我會採用 OCSF（Open Cybersecurity Schema Framework），它是開放標準，依事件類別定義欄位，例如 Authentication（class_uid 3002）、Network Activity（4001）、DNS Activity（4003）、Process Activity（1007）、API Activity（6003）。Amazon Security Lake 也用它，客戶要匯出時比較好對接。」

每一筆正規化後的事件，在 OCSF 的類別欄位之外，再加上平台自己的信封欄位：

```
tenant_id          string     -- 由擷取端點依憑證決定，絕不信任 payload 內的值
event_uid          string     -- (agent_id, seq)；無序號的來源用來源紀錄 ID 或（檔案, 位移）
class_uid          int        -- OCSF 類別，例如 3002 Authentication
time               timestamp  -- 事件發生時間（OCSF 的 time），由來源提供
observed_time      timestamp  -- 我們收到的時間；拆出擷取延遲用
source_type        string     -- fw_vendor_a / edr_agent / cloudtrail / idp ...
parser_version     string     -- 哪一版解析器產生這一列
enrich_version     map        -- {asset: v812, geoip: 2026-11-18, ioc: v55203}
unmapped           map        -- 對應不到 OCSF 的欄位原樣保留
raw_ref            string     -- 原始資料在 S3 的位置（檔案 + 位移）
```

`event_uid` 的來源有優先順序：代理程式自己的 `(agent_id, seq)`；來源系統給的紀錄 ID（例如雲端稽核日誌的 event ID）；批次送來的檔案用（檔案名稱, 位移或行號），同一個檔案重送時仍然得到相同的值。**內容雜湊不能當成唯一 ID**：時間戳只到秒的來源，同一秒內兩次登入失敗的內容完全相同，雜湊會把它們當成同一筆而去掉一筆，「五次失敗」的規則就可能湊不滿。真的什麼識別都沒有的來源，只能不去重、接受重送造成的重複，由後面的告警去重吸收。

> **候選人**：「四個重點。一，`tenant_id` 由擷取端點從客戶端憑證推出來，payload 裡就算有也不採用；這是隔離的第一道防線。二，兩個時間：`time` 是事件發生的時間，偵測和時間軸都用它；`observed_time` 是收到的時間，用來把 MTTD 拆成『資料晚到』和『我們偵測慢』兩段。三，`parser_version` 加上 `unmapped` 加上 `raw_ref`，是應付廠商改格式的保險：解析器有錯時，可以從原始資料用新版解析器重放。原始檔只留 90 天，所以重放與「打開原始位元組」的範圍就是 90 天；超過之後，冷層的正規化事件（含 `unmapped`）就是調查時看到的原始紀錄。若合約要求整個保留期都拿得到原始位元組，原始檔要跟著保留等級走，一年份約 110 TB 而不是 27 TB，這是要另外計價的方案。四，擴充欄位要記錄當時用的版本，這在深挖偵測時會用到。」
>
> **面試官**：「某家防火牆廠商更新韌體，日誌多了兩個欄位、改了一個欄位名稱。」
>
> **候選人**：「新增欄位不影響：解析器不認得的欄位進 `unmapped`，資料不會丟。改名比較危險，舊解析器會把那個欄位當成缺值，如果它是來源 IP，網路規則就靜悄悄地失效。所以每個 `(tenant, source_type, parser_version)` 都要監控解析失敗率和**關鍵欄位的空值率**；空值率從 0% 跳到 100% 是比解析錯誤更常見的訊號。修好解析器後發佈新版，對受影響時段從 `raw_ref` 重放。schema 相容規則本身沿用 [Part 13](/posts/de-system-design-interview-part13-schema-evolution-zh/) 的做法。」

**評註**：採用既有標準而不是自創 schema，是資深的訊號；「關鍵欄位空值率」比「解析失敗率」更貼近真實事故。資安情境下，缺資料最危險的地方在於它看起來就是「沒有威脅」。

---

## 四、15–25 分鐘：架構與三個演進階段

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 1  POC: one search cluster, index per tenant (< 50 tenants)   ║
╚══════════════════════════════════════════════════════════════════════╝

┌───────────┐  HTTPS  ┌───────────┐   ┌──────────────────┐   ┌──────────┐
│ Agents /  │────────▶│ Collector │──▶│ Search cluster   │──▶│ Dashboard│
│ syslog    │         │ + parsers │   │ index per tenant │   └──────────┘
└───────────┘         └───────────┘   └────────┬─────────┘
                                               │ scheduled queries
                                               ▼ every 5 min
                                        ┌──────────────┐
                                        │ Alerts table │
                                        └──────────────┘
```

**可行的範圍**：數十個租戶、每天 100 GB 以內，幾個人就能維運。**新增**：收集器、解析器、搜尋叢集。**失效的原因**：每個租戶每天一個索引，2,000 個租戶 × 30 天就是 60,000 個索引，分片數量壓垮叢集的中繼資料；排程查詢每 5 分鐘掃一次，晚到 6 分鐘的事件永遠不會被規則看到；儲存是原始資料的 2 倍以上，每 GB 成本隨規模線性上升。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 2  MVP: stream detection + shared columnar (~500 tenants)     ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────┐  ┌───────────┐  ┌────────────┐  ┌──────────────────────┐
│ Agents / │─▶│ Ingest    │─▶│ Kafka: raw │─▶│ Flink: parse → OCSF  │
│ pullers  │  │ auth,quota│  │ key =      │  │ dedup → enrich       │
└──────────┘  └─────┬─────┘  │ tenant_id  │  └──┬────────┬──────┬───┘
                    │        └────────────┘     │        │      │
                    ▼ raw gz                    ▼        ▼      ▼
             ┌─────────────┐   ┌────────────────────┐ ┌──────┐ ┌────────┐
             │ S3 raw      │   │ Flink: detection   │ │Click-│ │Iceberg │
             │ archive 90d │   │ stateless+stateful │ │House │ │on S3   │
             └─────────────┘   └─────────┬──────────┘ │30 d  │ │1 year  │
                                         ▼            └──┬───┘ └───┬────┘
                               ┌───────────────────┐     │         │
                               │ Postgres: alerts, │     ▼         ▼
                               │ incidents         │  dashboards  Athena
                               └───────────────────┘  + search    hunts,
                                                                  reports
```

**新增**：Kafka、Flink 的正規化與偵測作業、共用的欄式熱層、Iceberg 冷層、告警與事件庫。**成本與複雜度**：元件從 3 個變成 8 個，需要專人維運串流；但熱層磁碟從約 2.2 倍原始量降到約 0.25 倍。**解決**：告警在一分鐘內、晚到事件仍會被規則看到、分片數量不再隨租戶數成長。**仍然存在**：最大的租戶會和其他人搶同一組資源；所有資料在同一個區域；每個租戶的保留期一樣。

```
╔══════════════════════════════════════════════════════════════════════╗
║  Phase 3  Scale: regional cells, pool + silo tiers (2,000+ tenants)  ║
╚══════════════════════════════════════════════════════════════════════╝

                    ┌──────────────────────────────────┐
                    │ Global control plane             │
                    │ tenant → cell, plan, quota, keys │
                    │ (no event data)                  │
                    └────────┬───────────────┬─────────┘
                             │               │
          ┌──────────────────▼───┐       ┌───▼──────────────────┐
          │ Cell: us-east        │       │ Cell: eu-central     │
          │ ┌──────────────────┐ │       │ ┌──────────────────┐ │
          │ │ Pool: long tail  │ │       │ │ Pool: long tail  │ │
          │ │ shared tables    │ │       │ │ shared tables    │ │
          │ └──────────────────┘ │       │ └──────────────────┘ │
          │ ┌──────────────────┐ │       │ ┌──────────────────┐ │
          │ │ Silo: top tenants│ │       │ │ Silo: BYOK /     │ │
          │ │ own tables+quota │ │       │ │ regulated        │ │
          │ └──────────────────┘ │       │ └──────────────────┘ │
          └──────────────────────┘       └──────────────────────┘
```

**新增**：依區域切分的 cell（每個 cell 是一整套 Phase 2 的資料平面）、頭部租戶的獨立資源、每租戶配額、依保留等級分區、稽核紀錄、回溯獵捕。**成本與複雜度**：每多一個區域就多一套固定成本，維運從「一個叢集」變成「多個 cell 的發佈與監控」。**解決**：資料落地要求、吵鬧鄰居、保留期可以當作計價方案。**仍然存在**：跨區域的全域統計（例如某個 IOC 在多少客戶出現）只能用不含客戶資料的彙總做，而且要合約允許。

| | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 偵測 | 每 5 分鐘排程查詢 | 串流，事件時間 + 晚到路徑 | 加上回溯獵捕與客戶自訂規則 |
| 熱層 | 每租戶一個索引 | 共用欄式表，`tenant_id` 為排序首欄 | 長尾共用、頭部獨立 |
| 隔離 | 索引權限 | 查詢層強制注入 `tenant_id` + row policy | 加上配額、每租戶金鑰、區域 cell |
| 保留 | 全部 30 天 | 熱 30 天、冷 1 年 | 保留等級即計價方案 |
| 每 GB 成本（估計） | 約 $0.9 以上（倒排索引熱層） | 約 $0.4–0.5 | 約 $0.4，加上每個 cell 的固定成本 |

---

## 五、深挖一：多租戶隔離與吵鬧鄰居

> **面試官**：「你說長尾共用、頭部獨立。為什麼不全部用每租戶一張表？那樣隔離最乾淨。」
>
> **候選人**：「隔離最乾淨，但成本和維運會被長尾拖垮。我把三種做法攤開比較，名稱沿用 AWS SaaS 架構指引的 pool / bridge / silo。」

| 策略 | 怎麼做 | 優點 | 缺點 | 成本 | 何時選 | 何時失效 |
|---|---|---|---|---|---|---|
| Pool（共用表） | 所有租戶同一張表，`tenant_id` 為排序鍵首欄，查詢層強制過濾 | 檔案大小健康、資源利用率高、新租戶零成本上線 | 一個漏掉的 `WHERE` 就是跨租戶外洩；大租戶搶資源 | 最低 | 長尾租戶 | 單一租戶佔比過高，或要求每租戶金鑰 |
| Bridge（共用叢集、各自的表或資料庫） | 每租戶自己的表，跑在同一個叢集上 | 權限邊界清楚、刪除租戶就是刪表 | 2,000 租戶 × 數十個事件類別 = 數萬張表，最小租戶每天只有十幾 MB，小 part 與中繼資料暴增 | 中 | 數十到數百個中型租戶 | 租戶數上千 |
| Silo（獨立資源） | 獨立的表、運算配額，甚至獨立叢集 | 效能與故障完全隔離；可用客戶自己的金鑰 | 每個 silo 有固定成本，資源利用率低 | 最高 | 頭部租戶、受監管客戶 | 用在長尾，固定成本超過營收 |

> **候選人**：「所以我的設計是：佔總量前 1% 的約 20 個租戶，以及要求自帶金鑰的客戶，進 silo；其餘全部 pool。這個門檻不是固定的，租戶的日擷取量超過例如總量的 1% 就自動標記為搬遷候選。」
>
> **面試官**：「pool 裡怎麼保證不會看到別人的資料？」
>
> **候選人**：「三層，任何一層出錯都還有下一層擋著。」

```
 analyst request (JWT: tenant=T42, user=alice, role=analyst)
        │
        ▼
┌───────────────────────────┐  1. tenant_id comes only from the token;
│ Query API                 │     user-supplied tenant filters are rejected
│ builds parameterized SQL  │
└────────────┬──────────────┘
             ▼
┌───────────────────────────┐  2. connects as a role bound to a ROW POLICY
│ Columnar store            │     (tenant_id = T42); a missing WHERE
│ row policy + quotas       │     still returns only T42 rows
└────────────┬──────────────┘
             ▼
┌───────────────────────────┐  3. every query is logged: who, tenant,
│ Audit log (append-only)   │     filters, rows returned; tenant can read
└───────────────────────────┘     its own audit trail
```

> **候選人**：「除此之外還有一個測試：每次發佈都跑一組『金絲雀租戶』的查詢，用租戶 A 的身分搜尋只存在於租戶 B 的特殊字串，結果必須是零筆。這比審查程式碼可靠，因為它檢查的是實際行為。」
>
> **面試官**：「最大的租戶上線那天，其他人的告警慢了十分鐘。」
>
> **候選人**：「症狀和診斷大概是這樣：偵測延遲的 p99 從 40 秒升到 10 分鐘，但 Kafka 消費延遲只集中在少數幾個分區。查分區對應的租戶，全部是新上線的那一家。原因是我用 `tenant_id` 當分區鍵的主要部分，大租戶的流量全落在幾個分區上。
>
> 修法分三層。一，**擷取端配額**：每個租戶依方案有每秒與每日的上限，超過的部分先寫進 S3 原始檔、延後處理，而不是塞進共用的即時佇列。二，**分區鍵加鹽**：silo 租戶的分區鍵是 `tenant_id + hash(host) mod N`，N 依它的流量設定，把負載攤到多個分區；有狀態的偵測在 Flink 裡重新以 `(tenant, user)` 或 `(tenant, host)` 分組，所以入口怎麼分區不影響規則的正確性。三，**查詢端配額**：每租戶限制並行查詢數、單次查詢的最長執行時間與記憶體，超過 30 天的長範圍查詢導到 Athena，而不是在熱層上跑。」
>
> **面試官**：「每個租戶用自己的加密金鑰呢？」
>
> **候選人**：「要分層處理，因為它有成本也有技術上的限制。如果每個租戶都配一把 KMS customer managed key，每把每月約 $1，2,000 把就是每月 $2,000，還沒算 API 呼叫。更根本的是，共用表的一個資料檔混了很多租戶的資料，沒辦法用不同的金鑰加密同一個檔案裡的不同列。所以：pool 租戶的熱層用磁碟層級加密，冷層的檔案是同一個保留等級的租戶共用的（下一節會講為什麼），用平台的金鑰做 S3 伺服器端加密——pool 方案**不提供每租戶金鑰**，隔離靠的是前面三道存取控制。要求自帶金鑰（BYOK）的客戶一律進 silo，它的表和 S3 前綴都用客戶的 key，解約時刪除金鑰就讓資料無法讀取（crypto-shredding）。」

**評註**：候選人沒有停在「加上 `WHERE tenant_id`」，而是給出三道防線和一個能自動驗證隔離的測試；吵鬧鄰居的回答從症狀開始，指出分區層的根因，再分擷取、分區、查詢三處修正。金鑰的回答點出「共用檔案無法每租戶加密」這個技術限制，這是只背過「per-tenant key」的人答不出來的。

---

## 六、深挖二：偵測——無狀態比對、有狀態關聯與晚到

> **面試官**：「舉一條有狀態的規則，說明它怎麼在串流中執行。」
>
> **候選人**：「『同一個使用者 10 分鐘內連續失敗 5 次以上，接著從一個新國家登入成功』。先分清楚兩種規則。無狀態規則只看單筆事件，例如『連到已知惡意 IP』，每筆事件獨立判斷，水平擴展沒有問題，內建規則大多是這種。有狀態規則要記住過去，必須依實體分組，並且以事件時間判斷順序。」

```sql
-- Flink SQL; auth_events = OCSF Authentication (3002), enriched upstream
SELECT *
FROM auth_events
MATCH_RECOGNIZE (
  PARTITION BY tenant_id, user_uid
  ORDER BY event_time                      -- OCSF time, as rowtime
  MEASURES
    FIRST(F.event_time) AS first_fail_at,
    COUNT(F.event_uid)  AS fail_count,
    S.event_time        AS success_at,
    S.src_country       AS country
  ONE ROW PER MATCH
  AFTER MATCH SKIP PAST LAST ROW
  PATTERN (F{5,} S) WITHIN INTERVAL '10' MINUTE
  DEFINE
    F AS F.status = 'Failure',
    S AS S.status = 'Success' AND S.is_new_country
)
```

這個樣式要求五次失敗與成功**緊鄰**：`MATCH_RECOGNIZE` 預設是嚴格連續比對，中間只要夾了一筆其他登入事件（例如 MFA 挑戰）就不會命中。所以輸入要先篩到只剩登入成功與失敗兩種事件，或在樣式中加入一個可略過的變數。

> **候選人**：「兩個不明顯的地方。第一，`PARTITION BY` 一定包含 `tenant_id`，否則兩家公司都有叫 `admin` 的帳號，會被當成同一個人。第二，`is_new_country` 是在擴充階段算好的：查這個使用者過去 30 天出現過的國家，而且**只能用這筆事件之前的資料**。如果基準是每天批次算的，它的生效時間是算完寫入的那一刻，不是它描述的那一天——和 [Part 9](/posts/de-system-design-interview-part9-streaming-media-feature-platform-zh/) 的特徵生效時間是同一個陷阱。」
>
> **面試官**：「狀態會有多大？」

```
stateful rule (per tenant+user)
  active users      = 2,000 tenants × 2,500 users (assumed avg) = 5,000,000
  state per user    ≈ 5 recent failures + country set ≈ 200 B
  total             ≈ 5M × 200 B                              ≈ 1 GB

dedup by event_uid (RocksDB, ~56 B per key incl. overhead)
  1-hour window     = 3B / 24 = 125M keys × 56 B              ≈ 7 GB
  24-hour window    = 7 GB × 24                               ≈ 168 GB
```

> **候選人**：「關聯規則的狀態很小。真正大的是去重：如果要在串流裡對一整天去重，狀態約 168 GB，checkpoint 和復原都會變慢。所以串流只做 1 小時視窗的去重（約 7 GB），涵蓋代理程式重送最常見的情況；超出視窗的重複由熱層的去重表引擎（ClickHouse 的 `ReplacingMergeTree`）在合併時處理，冷層由每日批次處理。合併是背景進行、時間不保證的，所以合併前查得到重複：儀表板的物化視圖吃的是串流去重後的資料，調查查詢需要精確筆數時才加 `FINAL` 或以 `event_uid` 去重。偵測端對重複的容忍度高，因為下一段的告警去重會吸收它。」
>
> **面試官**：「筆電離線兩天，回到公司一次把事件送上來。」
>
> **候選人**：「這些事件的 `time` 是兩天前，watermark 早就過了。這裡有一個要先講清楚的取捨：事件時間的樣式比對要等 watermark 推進才會輸出，watermark 落後多少，每一則告警就至少晚多少。如果為了涵蓋晚到而把 watermark 設成落後 15 分鐘，連準時到的事件都要等 15 分鐘，一分鐘內告警的目標就不可能達成。所以即時偵測的 watermark 只落後約 30 秒（依來源各自設定，並對閒置來源設 idle timeout）。超過的事件不丟，而是走**晚到路徑**：寫入熱層與冷層照常進行，同時送進回溯偵測作業，用相同的規則定義對受影響的 `(tenant, entity, 時間範圍)` 重跑。雲端稽核日誌這類固定晚幾分鐘的批次來源，由每 5 分鐘一次的微批次回溯處理；離線兩天的筆電也走同一條路。產生的告警標記為 `late_detection`，而且 MTTD 的計算會把擷取延遲獨立出來。」

```
MTTD for one incident (laptop offline two days)

 time (event)      observed_time            alert created
     │                  │                         │
─────┼──────────────────┼─────────────────────────┼──────▶
 Mon 09:12          Wed 08:55                Wed 09:03
     └─ ingest delay ───┘└─── detection delay ────┘
          47 h 43 m                8 m

 dashboard shows: MTTD 47 h 51 m = ingest 47 h 43 m + platform 8 m
```

> **候選人**：「不拆開的話，客戶會看到 MTTD 47 小時，以為我們的偵測很慢；拆開之後，他看到的是自己有一台筆電兩天沒連線，這本身就是一個值得處理的資安發現。」
>
> **面試官**：「規則觸發太多次，分析師被淹沒。」
>
> **候選人**：「兩層收斂。**告警去重**：以 `(tenant, rule_id, entity)` 為鍵，1 小時內同一鍵再次觸發只累加次數、更新最後出現時間，不開新告警。**事件歸併**：**同一個租戶內**共用同一個實體（主機或使用者）、在 2 小時內發生的不同告警，歸到同一個 incident（歸併鍵是 `(tenant_id, entity)`，否則兩家客戶各有一台 `server1` 就會被併成一案），嚴重度取其中最高者。儀表板上的告警數、MTTR 都以 incident 為單位計算，否則一次暴力破解就會讓告警數暴增一千倍、MTTR 失真。」
>
> **面試官**：「今天威脅情資更新，某個 IP 被標為惡意。上週就有人連過它。」
>
> **候選人**：「這要分清楚兩個問題。上週那筆事件被擴充時，這個 IP 還不在 IOC 清單上，事件上的 `enrich_version.ioc` 記錄了當時的版本——這是事實，不能改寫，否則上週的報表會變。今天新增的 IOC 觸發一個**回溯獵捕**：用新 IOC 對熱層 30 天的資料搜尋，命中的產生新的告警，類型標記為 `retro_ioc_match`，並連回原始事件。『當時知道什麼』與『現在知道什麼』分開保存，和 [Part 6](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/) 的業務時間與記錄時間是同一個結構。」

**評註**：這一段的資歷訊號有四個：`PARTITION BY` 帶租戶、擴充基準的生效時間、把 MTTD 拆成擷取與偵測兩段、IOC 回溯不改寫歷史。晚到與去重的一般策略見 [Part 12](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)，這裡的重點是它們在多租戶資安情境下的具體選擇。

---

## 七、深挖三：熱層引擎、保留等級與每 GB 成本

> **面試官**：「業界很多 SIEM 用 Elasticsearch 類的搜尋引擎，你為什麼用欄式儲存當熱層？」
>
> **候選人**：「因為這裡的查詢型態大多是『欄位過濾 + 時間範圍 + 彙總』，而不是依相關性排序的全文搜尋。分析師問的是『主機 H 過去 7 天連過哪些 IP』、『各嚴重度每小時的告警數』，這些在欄式儲存上掃的是少數幾欄、而且有排序鍵可以跳過不相關的資料塊。三種引擎攤開比較：」

| 引擎 | 怎麼做 | 優點 | 缺點 | 30 天熱層成本（本題） | 何時選 | 何時失效 |
|---|---|---|---|---|---|---|
| 倒排索引（OpenSearch / Elasticsearch 類） | 每個詞建索引，依相關性搜尋 | 任意字串的全文搜尋最快；生態成熟 | 索引約為原始的 1.1 倍，加副本約 198 TB；彙總查詢較慢；分片管理吃人力 | 約 $55K / 月 | 非結構化日誌為主、需要相關性排序、資料量小 | 每天 TB 級、以彙總為主 |
| 欄式（ClickHouse 類） | 依排序鍵存欄位，壓縮後掃描，可加 bloom filter 跳讀索引 | 壓縮約 8 倍，22.5 TB；彙總與時間範圍查詢快；物化視圖做儀表板 | 任意子字串搜尋要靠 token / ngram bloom filter，比倒排索引慢；更新與刪除成本高 | 約 $11K / 月 | 結構化事件、儀表板彙總、欄位過濾的調查查詢 | 大量自由文字的模糊搜尋是核心功能 |
| S3 + Iceberg + Athena | Parquet 檔 + table format，按掃描量計費 | 儲存最便宜、可存數年；同一份資料可給多種引擎 | 互動延遲數秒到數分鐘；每次查詢按 TB 掃描付費 | 不作熱層；一年冷層約 $2.5K / 月 | 長範圍獵捕、合規報表、系統紀錄 | 需要秒級互動 |

> **候選人**：「熱層表的設計是：依天分區，排序鍵 `(tenant_id, class_uid, time, event_uid)`——結尾的 `event_uid` 不能省，去重表引擎是以整個排序鍵判斷重複的，少了它，同租戶同類別同一毫秒的兩筆不同事件會在合併時被丟掉一筆——對主機、使用者、IP 欄位加 bloom filter 跳讀索引，對原始訊息加 token bloom filter 應付偶爾的關鍵字搜尋。儀表板不直接查事件表，而是查物化視圖：以 `(tenant_id, 分鐘, severity, rule_id)` 預先彙總，儀表板一次查詢只讀幾千列。分割與排序的原理在 [Part 14](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)。」
>
> **面試官**：「每個租戶的保留期不同，冷層怎麼刪？」
>
> **候選人**：「如果用 `(tenant_id, day)` 分區，2,000 個租戶 × 365 天就是七十三萬個分區，最小租戶每天只有約 19 MB 的 Parquet，全是小檔。如果只用 day 分區，刪除某個租戶的舊資料就變成列級刪除，要重寫整個檔案。
>
> 我的做法是以**保留等級**分區：`(retention_class, day)`，等級例如 90 天、1 年、3 年，同等級的租戶共用分區、在檔案內依 `tenant_id` 排序。到期刪除就是丟棄整個舊分區，運算成本幾乎為零；但在 Iceberg 上丟棄分區只是讓目前的快照不再引用那些檔案，舊快照仍然指著它們，資料還能用時間旅行讀到、也還在計費。所以保留期作業的最後一步是讓舊快照過期並清除孤兒檔案（`expire_snapshots`，Athena 上是 `VACUUM`），檔案被實際刪除才算完成；Athena 查詢時先以 day 剪枝，再用檔案的 `tenant_id` 最小最大值統計跳過不相關的檔案。租戶升級方案時，把它的資料搬到新等級；解約時才做一次列級刪除加壓實，這是低頻操作。這樣保留期就成了可以直接賣的方案，而不是一個每個租戶各自不同的維運負擔。」

**評註**：候選人把「為什麼不用業界常見的方案」講成查詢型態的推論，給出成本差距，也承認欄式儲存在模糊搜尋上的弱點，並說出何時倒排索引才是對的。保留等級分區把一個計價需求翻譯成了儲存佈局。

---

## 八、故障、監控與成本

**症狀 → 診斷**

| 症狀 | 先看哪裡 | 常見根因 | 處理 |
|---|---|---|---|
| 某租戶的防火牆告警從凌晨起為 0 | `(tenant, source_type)` 的事件量對比上週同時段；關鍵欄位空值率 | 廠商韌體改了欄位名稱，來源 IP 全為空 | 儀表板顯示「資料來源異常」而非「無告警」；修解析器並從 `raw_ref` 重放 |
| 所有租戶的偵測延遲 p99 從 40 秒升到 10 分鐘 | Kafka 各分區的消費延遲分佈 | 單一大租戶集中在少數分區 | 擷取配額、silo 租戶分區鍵加鹽 |
| 所有租戶的搜尋 p95 從 1 秒升到 15 秒 | 熱層的查詢紀錄，依租戶彙總 CPU 與掃描量 | 一個租戶對 30 天資料跑正規表示式 | 每租戶查詢配額；長範圍查詢導到 Athena |
| 某租戶 MTTD 突然變成 30 小時 | MTTD 的擷取延遲與偵測延遲兩段 | 代理程式離線後批次補送 | 平台無異常；以端點離線告警通知客戶 |
| 冷層查詢費用一週翻倍 | Athena 每租戶掃描量 | 某客戶的排程獵捕沒有時間範圍 | 強制查詢帶時間條件；依掃描量計費到該租戶 |

> **候選人**：「第一列最重要。資安產品最危險的故障是**安靜**：資料沒進來時，儀表板顯示零告警，看起來和『很安全』一模一樣。所以每個 `(tenant, source_type)` 都有預期流量的基準，掉到基準的 20% 以下就同時告警給我們和客戶。」

**每月成本估算**（3 TB/天、單一區域、on-demand；單價為假設值，實際以 AWS 報價為準）：

```
ingest collectors + load balancers                      ≈  $2.0K
MSK: 6 brokers × $0.84/h × 730 h ≈ $3.7K
     + 17 TB storage × $0.10/GB-month ≈ $1.7K           ≈  $5.4K
Managed Flink: 64 KPU × $0.11/h × 730 h                 ≈  $5.1K
ClickHouse hot 30d: 12 nodes × $1.0/h × 730 h ≈ $8.8K
     + 30 TB gp3 × $0.08/GB-month ≈ $2.4K               ≈ $11.2K
S3: Iceberg 1 year (137 TB, Standard→IA) + raw 90d      ≈  $2.5K
Athena: ~200 TB scanned × $5/TB                         ≈  $1.0K
Postgres (alerts, incidents, config) + enrichment cache ≈  $2.5K
KMS: 2,000 keys × $1                                    ≈  $2.0K
cross-AZ traffic, monitoring, misc                      ≈  $3.0K
──────────────────────────────────────────────────────────────────
total                                                   ≈ $34.7K / month
cost per GB ingested = $34.7K / 90,000 GB               ≈ $0.39 / GB

same design with an inverted-index hot tier
  ~40 nodes × $1.2/h × 730 h ≈ $35K + 248 TB × $0.08 ≈ $20K ≈ $55K
  total ≈ $34.7K − $11.2K + $55K ≈ $78.5K → ≈ $0.87 / GB
```

> **候選人**：「三個結論。一，熱層引擎的選擇讓每 GB 成本差了一倍多，是單一最大的決定。二，KMS 每租戶一把金鑰就佔總成本約 6%，這也是我只對 BYOK 方案給獨立金鑰的原因之一。三，每 GB 成本必須依租戶分攤：擷取量是主要因子，但查詢掃描量也要記到租戶頭上，否則一個重度獵捕的客戶會由其他人補貼。最小租戶每天 0.15 GB，變動成本每月不到 $2，但它的固定成本（儀表板、設定、支援）遠高於此，所以方案要有最低月費。」

**評註**：成本估算的單價都標成假設，重點是比例與推論：哪一個決定主導成本、成本怎麼分攤到租戶、定價結構怎麼由成本結構推出。

---

## 九、為什麼選 X 不選 Y

| 選擇 | 選 X 的理由 | 不選 Y 的理由 | 翻轉條件 |
|---|---|---|---|
| 長尾 pool + 頭部 silo vs 全部每租戶一張表 | 長尾的檔案大小健康、資源利用率高；頭部隔離吵鬧鄰居 | 2,000 租戶 × 數十類別 = 數萬張表，小檔與中繼資料壓垮叢集 | 租戶數在 100 以下，或合約要求所有客戶實體隔離 |
| 欄式熱層 vs 倒排索引熱層 | 磁碟約 22.5 TB 對 198 TB；彙總快；每 GB 成本約 $0.39 對 $0.87 | 倒排索引的優勢在相關性全文搜尋，這題的查詢以欄位過濾和彙總為主 | 產品核心是對非結構化日誌做模糊搜尋，且資料量小到成本不是瓶頸 |
| 擷取時正規化成 OCSF vs 查詢時才解析 | 規則與儀表板只寫一次；擷取時就能監控解析品質 | 每條規則各自處理幾十種格式，廠商一改格式就有規則靜默失效 | 很少被查詢的來源，只保存原始資料、需要時再解析 |
| 串流偵測 + 晚到回溯 vs 每 5 分鐘批次查詢 | 一分鐘內告警；以事件時間判斷，晚到事件不會被跳過 | 排程查詢的時間窗與晚到資料錯開，晚到 6 分鐘就永遠漏掉 | 規則需要數天的基準（例如罕見程序），改用每日批次 |
| 擴充時記錄版本 + IOC 回溯獵捕 vs 新 IOC 直接改寫舊事件 | 歷史報表可重現；新知識以新告警呈現 | 改寫後無法回答「當時為什麼沒告警」 | 擴充值本身錯誤（例如 GeoIP 資料庫壞檔），需要修正並重放 |
| 只對 BYOK 方案給獨立 KMS 金鑰 vs 每租戶一把 | 省下每月約 $2,000；pool 以平台金鑰加密，隔離靠存取控制 | 共用檔案無法每列不同金鑰，每租戶一把就得放棄共用檔案，回到數十萬個小分區 | 法規或合約要求所有客戶都用客戶管理的金鑰 |
| 保留等級分區 vs `(tenant_id, day)` 分區 | 到期刪除是丟分區；檔案大小健康 | 七十三萬個分區、長尾每天十幾 MB 的小檔 | 單一租戶大到值得自己一張表（silo），它就用自己的分區 |

---

## 十、系統效應與系列導航

從 Phase 1 到 Phase 3 的前後對照，沿用前文假設；標示為目標的是設計目標，不是量測值。

| 指標 | 改造前（單一搜尋叢集、每租戶索引） | 改造後（串流偵測 + 欄式熱層 + cell） |
|---|---|---|
| 高嚴重度告警延遲 | 5–10 分鐘（排程週期 + 查詢時間） | p95 < 60 秒（目標） |
| 晚到事件 | 錯過排程窗口即漏掉 | 晚到路徑回溯偵測，標記 `late_detection` |
| 熱層 30 天磁碟 | 約 198 TB | 約 22.5 TB |
| 每 GB 擷取成本 | 約 $0.87 以上（倒排索引熱層，估計） | 約 $0.39（估計） |
| 大租戶影響其他人 | 共用分片，無法限制 | 擷取與查詢配額、silo 資源 |
| 跨租戶外洩防線 | 索引權限一層 | token 決定租戶、row policy、稽核紀錄、金絲雀測試 |
| 資料來源中斷 | 顯示為零告警 | 依來源流量基準告警，儀表板標示來源異常 |
| 保留期 | 全部相同 | 保留等級即計價方案，到期以分區刪除 |
| 資料落地 | 單一區域 | 區域 cell，控制平面不含事件資料 |

**本篇重點**

- 多租戶題先問「資料屬於誰、最大與最小差多少」，再用估算決定哪一端用 pool、哪一端用 silo。
- 隔離要多道防線：租戶只從憑證推出、儲存層 row policy、稽核紀錄，再加一個能自動驗證的金絲雀測試。
- 偵測走串流並以事件時間判斷；晚到事件走回溯路徑；MTTD 拆成擷取延遲與偵測延遲。
- 擴充與 IOC 比對保存「當時知道什麼」，新知識以新告警呈現，不改寫歷史。
- 熱層引擎由查詢型態決定，它也是每 GB 成本最大的單一因子；保留等級把計價方案直接變成儲存佈局。

**DE 系統設計面試指南**

- [Part 1：答題框架與資料系統基本功](/posts/de-system-design-interview-part1-framework-fundamentals-zh/)
- [Part 2：批次管線、資料擷取與可重跑設計](/posts/de-system-design-interview-part2-batch-pipeline-ingestion-zh/)
- [Part 3：串流與即時系統](/posts/de-system-design-interview-part3-streaming-realtime-zh/)
- [Part 4：儲存、倉儲與 Lakehouse 設計](/posts/de-system-design-interview-part4-storage-warehouse-lakehouse-zh/)
- [Part 5：完整模擬面試與常見情境](/posts/de-system-design-interview-part5-mock-interview-scenarios-zh/)
- [Part 6：支付業案例——帳本、對帳與可稽核的資料平台](/posts/de-system-design-interview-part6-payments-ledger-reconciliation-zh/)
- [Part 7：廣告業案例——點擊計費、預算控制與歸因](/posts/de-system-design-interview-part7-adtech-click-billing-attribution-zh/)
- [Part 8：叫車業案例——即時位置、供需與行程資料](/posts/de-system-design-interview-part8-ride-hailing-geo-realtime-zh/)
- [Part 9：影音串流案例——觀看事件、特徵平台與實驗指標](/posts/de-system-design-interview-part9-streaming-media-feature-platform-zh/)
- [Part 10：誰在查、要多新鮮、要多準——依新鮮度選架構](/posts/de-system-design-interview-part10-freshness-sla-tiers-zh/)
- [Part 11：重跑一次結果會一樣嗎——冪等、確定性與回補策略](/posts/de-system-design-interview-part11-idempotency-rerun-backfill-zh/)
- [Part 12：重複、亂序與晚到——事件正確性的處理策略](/posts/de-system-design-interview-part12-dedup-ordering-late-data-zh/)
- [Part 13：Schema 演進——契約、相容性與變更流程](/posts/de-system-design-interview-part13-schema-evolution-zh/)
- [Part 14：儲存與查詢效率——讀得少、算得少、存得巧](/posts/de-system-design-interview-part14-storage-query-efficiency-zh/)
- **Part 15：資安 SaaS 案例——多租戶威脅偵測儀表板**（本篇）

**延伸閱讀**

- OCSF（Open Cybersecurity Schema Framework）官方 schema 瀏覽器：schema.ocsf.io
- AWS Well-Architected Framework, "SaaS Lens"（pool / bridge / silo 隔離模型）
- Apache Flink 文件：Table API & SQL — Pattern Recognition（MATCH_RECOGNIZE）
- ClickHouse 文件：Row Policies、Quotas 與 Data Skipping Indexes
