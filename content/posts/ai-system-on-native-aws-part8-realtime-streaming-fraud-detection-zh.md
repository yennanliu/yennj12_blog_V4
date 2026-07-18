---
title: "AI System on Native AWS - Part 8 - 即時串流 ML 與詐欺偵測"
date: 2026-07-25T09:00:00+08:00
draft: false
description: "詐欺偵測是即時 ML 的極限測試:要在幾十毫秒內對每筆交易做出放行或攔截的決定,特徵要用『此刻及過去幾秒』的行為即時算出,對手還會主動規避你的規則。本篇用純 AWS 原生服務打造即時串流風控:Kinesis 收交易流、Managed Service for Apache Flink 做串流特徵、SageMaker/Fraud Detector 毫秒級評分、Neptune 圖資料庫抓詐欺團夥、DynamoDB 當線上特徵與決策存放,全部用 CDK(CloudFormation)描述,深入談串流特徵一致性、時間窗、圖偵測與規則+ML 混合決策。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Kinesis", "Managed Flink", "Fraud Detection", "Neptune", "SageMaker", "Streaming", "AI Engineering"]
authors: ["yen"]
readTime: "27 min"
---

> Part 3 的推薦系統要求 100ms、但推錯了頂多少賺一點。詐欺偵測也要求毫秒級,可是判斷錯了——放行一筆盜刷、或攔下一筆正常消費——都是真金白銀或客戶流失。而且推薦的使用者不會故意騙你,詐欺的對手會主動研究你的規則、繞過它、隔天換一套手法再來。
> 這是即時 ML 的最高難度:延遲最緊、代價最高、對手最刁鑽,而且你能用來判斷的特徵,大多得從「此刻及過去幾秒的行為串流」裡當場算出來——批次算好的特徵,對「一分鐘內連刷 20 筆」這種攻擊完全無效。
> AWS 原生的解法:Kinesis 收交易、Managed Flink 在流上算時間窗特徵、SageMaker 毫秒評分、Neptune 用圖找出「看似無關但其實同夥」的帳號、規則引擎兜住 ML 抓不到的已知手法。
> 這是 Part 8:當一個 AI 決策要在幾十毫秒內、面對主動對抗的對手時,系統長什麼樣。

---

## 一、情境與痛點:即時、對抗、高代價

詐欺偵測(信用卡盜刷、帳號盜用、洗錢、刷單)有三個把它跟前面所有系統區分開的特性:

- **延遲極緊**:交易授權必須在使用者按下付款到頁面回應之間完成,通常留給風控的預算只有幾十毫秒。你沒時間做重運算。
- **特徵要即時**:最有價值的訊號是「速度型」特徵——「這張卡過去 60 秒刷了幾次」「這個裝置過去 5 分鐘登入了幾個帳號」。這些**無法預先批次算好**,必須在事件流上即時計算。
- **對手會對抗**:詐欺集團會測試你的門檻、找到規則的邊界、然後大規模利用。你的模型今天有效,不代表下週有效——這是一場持續的軍備競賽。

這三點合起來,排除了很多看似合理的作法:

```
天真作法                         為什麼在詐欺場景失效
──────────────────────────────────────────────────────────────
用批次算好的使用者特徵              抓不到「此刻連續刷」的速度型攻擊
純規則引擎(if 金額 > X 就擋)       對手一測就知道門檻,繞過只是時間問題
純黑箱 ML 模型                    抓不到已知手法,且無法解釋為何擋(法遵要求)
只看單筆交易                       抓不到「一百個帳號協同」的團夥詐欺
```

正解是一個**多層混合系統**:串流即時特徵 + ML 模型 + 規則引擎 + 圖分析,每一層補另一層的盲點。

---

## 二、系統目的:功能與非功能需求

**功能需求:**

- 即時消費交易/行為事件流。
- 在流上計算時間窗特徵(近 N 秒/分鐘的速度、金額、地理跳躍)。
- 對每筆交易輸出風險分數與決策(放行 / 挑戰 / 攔截)。
- 圖分析:偵測共用裝置、卡號、收款帳戶的**詐欺團夥**。
- 規則引擎:即時封鎖已知手法(不必等重訓模型)。
- 決策可解釋、可稽核(為什麼擋這筆)。

**非功能需求:**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 端到端延遲 | P99 < 50ms | 卡在付款授權路徑上 |
| 特徵新鮮度 | 速度型特徵 < 1s 反映 | 攻擊在秒級發生 |
| 特徵一致性 | 線上/離線零 skew | 模型準確度的前提(同 Part 3) |
| 可解釋 | 每個決策有理由 | 法遵 + 客訴處理 |
| 可快速反應 | 新手法可即時上規則 | 對抗性,等重訓來不及 |
| 高可用 | 風控掛了要能 fail-safe | 不能因風控故障擋掉所有交易 |

「P99 < 50ms」比 Part 3 的 100ms 更緊,且加上了「對抗性」與「可解釋」——這把架構推向 **Flink 串流計算 + 輕量 ML + 規則 + 圖** 的組合,而不是單一模型。

---

## 三、系統設計與架構

### 3.1 整體架構

```
┌──────────┐  交易事件   ┌──────────────┐
│ 交易/登入  │ ─────────▶ │   Kinesis     │
│  來源     │            │  Data Stream  │
└──────────┘            └───┬───────┬───┘
                            │       │
        ①串流特徵計算         ▼       ▼ ②同步評分路徑
              ┌──────────────────┐  ┌──────────────────────────────────┐
              │ Managed Service   │  │  Lambda / API(同步決策 < 50ms)    │
              │ for Apache Flink   │  │  ┌────────┐ ┌────────┐ ┌───────┐ │
              │ 時間窗聚合:近60s    │  │  │規則引擎 │ │ML 評分  │ │圖查詢  │ │
              │ 刷卡次數/金額/地理   │  │  │(已知手法)│ │SageMaker│ │Neptune│ │
              └────────┬─────────┘  │  └───┬────┘ └───┬────┘ └───┬───┘ │
                       ▼            │      └──────┬───┴──────────┘     │
              ┌──────────────────┐  │             ▼ 綜合決策             │
              │ 線上特徵 store     │◀─┼──── 取特徵 ─┤ 放行/挑戰/攔截        │
              │ (DynamoDB/         │  │             └────────┬───────────┘
              │  ElastiCache)      │  └──────────────────────┼───────────┘
              └────────┬─────────┘                          ▼
                       │離線同步                     ┌──────────────┐
                       ▼                             │ 決策紀錄       │
              ┌──────────────────┐                  │ DynamoDB(稽核)│
              │ Feature 離線 store │──▶ 訓練/回測      └──────────────┘
              │ (S3)              │
              └──────────────────┘
```

### 3.2 三個關鍵設計

**① 串流特徵:為什麼要 Flink 而不是 Lambda 聚合**

「近 60 秒這張卡刷了幾次」這種特徵,需要**有狀態的時間窗聚合**:系統要記住每張卡的滑動窗口計數,事件一來就更新。Lambda 是無狀態的,自己在 Lambda 裡維護窗口要靠外部存放 + 讀寫,又慢又容易錯。**Managed Service for Apache Flink** 天生為此而生:滑動窗、會話窗、watermark 處理遲到事件,都是 Flink 的原生能力,算完把特徵推進線上 store。

**② 同步決策路徑:規則 + ML + 圖的並行查詢**

決策路徑必須在 50ms 內完成,所以它只做「查」不做「算」:規則引擎查已知黑名單/門檻、ML 模型用**已經算好的**線上特徵評分、圖查詢看這個實體是否連到已知詐欺網。三者並行,綜合成一個決策。**重運算(特徵計算)全在非同步的 Flink 側完成,同步路徑只查結果**——這是壓住延遲的核心。

**③ 圖偵測:抓 ML 看不到的團夥**

單筆交易看起來都正常,但如果「50 個不同帳號共用同一個收款帳戶、同一個裝置指紋」,那是團夥詐欺。這是**關係**問題,不是單點問題,關聯式/單筆 ML 都抓不到。**Neptune 圖資料庫**把帳號、卡、裝置、收款方建成圖,一個圖查詢就能揪出「異常密集連結」的可疑社群。

### 3.3 規則 + ML 為什麼要並存

- **純 ML**:擅長抓「沒見過的異常模式」,但抓不到「已知的具體手法」(它可能覺得某個已知詐騙 IP 的交易不夠異常),而且黑箱、難解釋。
- **純規則**:能即時封鎖已知手法、完全可解釋,但對手一測就繞過,且無法泛化到新手法。
- **並存**:規則擋已知、ML 抓未知、規則提供可解釋的底線、ML 提供泛化能力。詐欺對抗是軍備競賽,你需要「能立刻反應的規則」+「能學習泛化的模型」兩條腿走路。

---

## 四、CDK(CloudFormation)實作

### 4.1 事件流與線上特徵存放

```typescript
// lib/streaming.ts 片段
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Duration } from 'aws-cdk-lib';

const txStream = new kinesis.Stream(this, 'TxStream', {
  streamMode: kinesis.StreamMode.ON_DEMAND,
  retentionPeriod: Duration.hours(24),
});

// 線上特徵:以 entity(卡號/裝置)為 key,存滑動窗聚合結果,DynamoDB 個位數毫秒讀取
const featureTable = new dynamodb.Table(this, 'OnlineFeatures', {
  partitionKey: { name: 'entityKey', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute: 'ttl',                 // 舊窗口自動過期
});
```

### 4.2 Managed Flink 串流特徵應用

Flink 應用把 jar/zip 放 S3,用 CDK 部署成 Managed Flink 應用,消費 Kinesis、算時間窗特徵、寫進 DynamoDB。

```typescript
// lib/flink.ts 片段
import * as kda from 'aws-cdk-lib/aws-kinesisanalyticsv2';
import * as iam from 'aws-cdk-lib/aws-iam';

const flinkRole = new iam.Role(this, 'FlinkRole', {
  assumedBy: new iam.ServicePrincipal('kinesisanalytics.amazonaws.com'),
});
txStream.grantRead(flinkRole);
featureTable.grantWriteData(flinkRole);
flinkAppBucket.grantRead(flinkRole);

new kda.CfnApplication(this, 'FeatureApp', {
  runtimeEnvironment: 'FLINK-1_20',
  serviceExecutionRole: flinkRole.roleArn,
  applicationConfiguration: {
    applicationCodeConfiguration: {
      codeContent: { s3ContentLocation: {
        bucketArn: flinkAppBucket.bucketArn, fileKey: 'flink/feature-app.jar' } },
      codeContentType: 'ZIPFILE',
    },
    flinkApplicationConfiguration: {
      parallelismConfiguration: { configurationType: 'CUSTOM', parallelism: 4, autoScalingEnabled: true },
      checkpointConfiguration: { configurationType: 'DEFAULT' },  // 有狀態容錯的關鍵
    },
    environmentProperties: { propertyGroups: [{
      propertyGroupId: 'FeatureConfig',
      propertyMap: { INPUT_STREAM: txStream.streamName, FEATURE_TABLE: featureTable.tableName },
    }] },
  },
});
```

Flink 應用內部的時間窗特徵邏輯(概念示意,實際為 Flink Java/SQL):

```java
// 近 60 秒滑動窗:每張卡的刷卡次數與總金額
txStream
  .keyBy(tx -> tx.cardId)
  .window(SlidingEventTimeWindows.of(Time.seconds(60), Time.seconds(5)))
  .aggregate(new VelocityAggregator())   // count, sumAmount, distinctMerchants, geoJump
  .addSink(new DynamoDbFeatureSink());   // 寫回線上特徵表,供同步路徑查
```

### 4.3 同步決策 Lambda:並行查規則 / ML / 圖

```typescript
// lib/lambda/decide/index.ts 片段
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, GetCommand } from '@aws-sdk/lib-dynamodb';
import { SageMakerRuntimeClient, InvokeEndpointCommand } from '@aws-sdk/client-sagemaker-runtime';

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const smrt = new SageMakerRuntimeClient({});

export const handler = async (event: any) => {
  const tx = JSON.parse(event.body);

  // 三路並行查詢(不做重運算,只查已算好的東西),壓住 50ms
  const [features, ruleHit, graphRisk] = await Promise.all([
    ddb.send(new GetCommand({ TableName: process.env.FEATURE_TABLE!,
                              Key: { entityKey: `card#${tx.cardId}` } })),
    checkRules(tx),                       // 規則引擎:黑名單/門檻/已知手法
    queryGraphRisk(tx),                   // Neptune:是否連到已知詐欺網(可設短逾時)
  ]);

  // 規則命中已知詐欺 → 直接攔,不必等 ML(可解釋、最快)
  if (ruleHit.block) return decision('BLOCK', ruleHit.reason, tx);

  // ML 評分:用「已經算好的」線上特徵 + 圖風險
  const score = await smrt.send(new InvokeEndpointCommand({
    EndpointName: process.env.FRAUD_ENDPOINT!,
    ContentType: 'application/json',
    Body: JSON.stringify({ tx, features: features.Item, graphRisk }),
  }));
  const risk = JSON.parse(new TextDecoder().decode(score.Body)).risk;

  // 分數分帶:低→放行、中→挑戰(OTP/3DS)、高→攔截
  const action = risk < 0.3 ? 'ALLOW' : risk < 0.8 ? 'CHALLENGE' : 'BLOCK';
  return decision(action, `ml_risk=${risk.toFixed(2)}`, tx);
};

// fail-safe:任何依賴逾時,退回保守但不全擋的預設(避免風控故障癱瘓交易)
```

### 4.4 Neptune 圖:團夥偵測

```typescript
// lib/graph.ts 片段
import * as neptune from 'aws-cdk-lib/aws-neptune';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

const cluster = new neptune.CfnDBCluster(this, 'FraudGraph', {
  dbClusterIdentifier: 'fraud-graph',
  vpcSecurityGroupIds: [sg.securityGroupId],
  dbSubnetGroupName: subnetGroup.ref,
  storageEncrypted: true,
});
new neptune.CfnDBInstance(this, 'FraudGraphInstance', {
  dbClusterIdentifier: cluster.ref,
  dbInstanceClass: 'db.r6g.large',
});
// 圖模型:(Account)-[:USES]->(Device), (Account)-[:PAYS_TO]->(Payee), (Card)-[:LINKED]->(Account)
// 團夥查詢(Gremlin 概念):找出「共用同一裝置/收款方且已有一個已知詐欺標記」的密集社群
```

> 圖查詢在 50ms 同步路徑裡要**設短逾時 + 快取常見實體的圖風險**;深度的社群偵測(整張圖的密集子圖分析)放在**非同步**跑,結果寫回線上表供同步路徑快查。同步路徑只做「這個實體的預算好圖風險是多少」的點查。

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 Managed Flink vs Lambda 聚合 vs Kinesis Analytics SQL

```
選擇              優勢                          代價 / 翻盤條件
──────────────────────────────────────────────────────────────
Managed Flink     有狀態時間窗、exactly-once、    學習曲線陡、有基礎成本
                  遲到事件處理,串流特徵首選
Lambda 自聚合      簡單、無新服務                 無狀態,窗口要外部存放,易錯且慢
Kinesis SQL(舊)  上手快                        表達力有限,複雜特徵吃力
```

**翻盤條件**:特徵極簡(只需「這筆金額 > 門檻」這種單點判斷、不需跨事件窗口)→ Lambda 就夠,不必引入 Flink。一旦需要「近 N 秒的聚合、去重、會話」這類有狀態計算,Flink 幾乎是唯一不痛的選擇。

### 5.2 自建 SageMaker 模型 vs Amazon Fraud Detector

```
選擇              自建 SageMaker                 Amazon Fraud Detector
──────────────────────────────────────────────────────────────
控制權            完全掌握特徵與模型              AWS 幫你端到端(專為詐欺設計)
上手              慢                            快(丟歷史交易就能訓)
客製              任意                          受限於其特徵/模型範式
即時特徵整合       自己接 Flink                   內建部分即時能力
```

**翻盤條件**:團隊沒有 ML 人力、要快速上線、詐欺型態常見(卡不當使用、註冊濫用)→ **Fraud Detector** 是「詐欺版的 Personalize」,直接用。要深度客製特徵、整合自家串流、或詐欺型態特殊 → 自建 SageMaker。本篇示範自建以講清原理;許多團隊的務實起點是 Fraud Detector。

### 5.3 為什麼一定要圖資料庫

有人會問:團夥關係用關聯式 JOIN 不行嗎?**不行**——「找出跟這個帳號在 3 跳之內共用資源的所有帳號」這種查詢,在關聯式資料庫是遞迴 self-join,深度一深就爆炸;而在圖資料庫是原生的遍歷操作,毫秒完成。**關係的深度查詢是圖資料庫的主場**,詐欺團夥偵測正是典型。

### 5.4 同步 vs 非同步的分工

詐欺系統最重要的架構決策:**什麼放同步、什麼放非同步**。

- **同步(< 50ms,關鍵路徑)**:只做點查與輕評分——查已算好的特徵、查規則、查預算好的圖風險、跑輕量 ML。
- **非同步(Flink / 批次)**:所有重運算——時間窗聚合、整圖社群偵測、模型重訓、標籤回填。

**把任何重運算放進同步路徑,就是把 50ms 目標判死刑。** 這條分工線是整個系統成立的前提。

---

## 六、成本估算

以「日均 500 萬筆交易、尖峰 2,000 TPS」估算(概略):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| Managed Flink | 4–8 KPU 自動擴縮 + 常駐 | **~$800–1,600**(串流常駐大戶) |
| Kinesis On-Demand | 每日 500 萬事件 | ~$200–400 |
| SageMaker Endpoint(輕量詐欺模型) | 常駐 + 自動擴縮 | ~$800–1,500 |
| Neptune | db.r6g.large × 2(HA) | ~$700–1,000 |
| DynamoDB(線上特徵 + 決策紀錄) | 高頻讀寫 | ~$800–1,500 |
| Lambda | 高 TPS | ~$400 |
| **合計** | | **~$3,700–6,400 / 月** |

**成本洞察**:詐欺系統是進階篇裡**常駐成本最重**的——Flink、SageMaker Endpoint、Neptune 全是 24 小時開著的服務,因為攻擊不分時段、延遲不能妥協。這跟 Part 3 推薦的「常駐運算」母題一致,但更極端(多了 Flink 與 Neptune 兩個常駐大戶)。但要用對的框架看這筆成本:

- **這是「保費」不是「開銷」**:$5,000/月的系統若攔下每月數十萬美元的詐欺損失,ROI 是壓倒性的。詐欺系統的成本要對比「不做的損失」,而非絕對值。
- **省錢的槓桿在「同步/非同步分工」**:把重運算推到非同步,同步路徑才能用便宜的輕量資源撐高 TPS。分工做對,常駐成本能壓在合理範圍。

---

## 七、延伸與常見的坑

**延伸方向:**

- **標籤延遲(label lag)**:詐欺的真實標籤常在數天後(退單、客訴)才到。訓練要處理這個延遲,並用「近似即時標籤」(如挑戰失敗)做早期訊號。
- **概念漂移與自動重訓**:對手在變,模型會過期。接 Part 5 的可觀測性監控線上分數分佈,漂移時觸發 Part 7 的重訓管線——三篇在此匯流。
- **可解釋性報表**:法遵要求「為什麼擋這筆」。保存每個決策的 top 特徵貢獻(SHAP)與命中的規則,產出可解釋紀錄。
- **主動學習**:把「挑戰」帶回的結果(通過/失敗)當成廉價標籤,持續餵回訓練,加速對抗迭代。

**最容易踩的坑:**

1. **把重運算放進同步路徑**:在決策 Lambda 裡現算時間窗、跑整圖查詢——50ms 目標當場崩。重運算一律非同步。
2. **串流特徵的 skew**:Flink 線上算的特徵跟訓練時離線算的定義不一致,模型準確度崩(同 Part 3 的 training-serving skew,串流版更難察覺)。
3. **沒有 fail-safe**:風控依賴的某個服務逾時,Lambda 直接報錯,結果所有交易被擋——風控故障不該癱瘓業務,要有保守 fallback。
4. **只靠 ML 不要規則**:新型已知手法爆發時,重訓來不及,沒有規則引擎你只能眼睜睜看著損失。
5. **忽略遲到事件**:交易事件亂序/遲到很常見,Flink 沒設好 watermark,窗口聚合就算錯。
6. **圖無限增長**:Neptune 圖若不設老化/歸檔,幾個月後查詢變慢。要定期把陳舊關係歸檔。

---

## 小結

詐欺偵測把即時 ML 逼到極限:**最緊的延遲、最高的代價、最刁鑽的對抗對手**。它的架構心法可以濃縮成一句——**重運算全部非同步(Flink 算特徵、整圖偵測、重訓),同步路徑只做點查與輕評分**;而決策本身是**規則(擋已知、可解釋)+ ML(抓未知、能泛化)+ 圖(揪團夥)** 的混合,任何單一手段都有致命盲點。這也是為什麼詐欺系統是進階篇裡服務最多、常駐成本最重、但 ROI 最清楚的一個。

進階篇到這裡,我們已經處理了多租戶、模型治理、即時風控。但有一個橫跨所有系統的維度我們一直只點到為止:**當這些 AI 系統要處理的是受管制的敏感資料(病歷、金流、個資),而且要通過稽核時,資安、合規、資料治理該怎麼設計?** 下一篇把這個維度單獨拉出來講透。這是 Part 9:企業 AI 安全、合規與資料治理。

---

## 系列導覽(進階篇)

- **Part 6**:企業級多租戶 RAG 平台
- **Part 7**:基礎模型客製化與模型治理
- **Part 8(本篇)**:即時串流 ML 與詐欺偵測
- **Part 9**:企業 AI 安全、合規與資料治理
- **Part 10**:企業 AI 平台工程 —— 落地區、LLM Gateway 與 FinOps

> 基礎篇回顧:Part 1 RAG 問答 · Part 2 IDP 管線 · Part 3 即時推薦 · Part 4 自主 Agent · Part 5 MLOps 與可觀測性
