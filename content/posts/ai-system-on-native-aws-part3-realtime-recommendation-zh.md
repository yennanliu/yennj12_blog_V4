---
title: "AI System on Native AWS - Part 3 - 即時個人化推薦系統"
date: 2026-07-20T09:00:00+08:00
draft: false
description: "推薦系統是最經典、商業價值最直接的 AI 系統。本篇用純 AWS 原生服務打造一套即時個人化推薦:Kinesis 收即時行為、SageMaker Feature Store 管線上/離線特徵、SageMaker Endpoint 做低延遲推論、DynamoDB 當候選集與快取,並用 API Gateway + Lambda 對外服務。全部用 CDK(CloudFormation)描述,深入談 online/offline 特徵一致性、召回+排序兩階段、冷啟動與 A/B 測試。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "SageMaker", "Kinesis", "Feature Store", "Recommendation", "DynamoDB", "MLOps", "AI Engineering"]
authors: ["yen"]
readTime: "26 min"
---

> 大部分人做推薦系統:離線跑個協同過濾,把結果算好塞進一張表,前端去查。上線第一天很香,第三天發現使用者剛剛看過、剛剛買過的東西還一直被推——因為推薦是「昨天算好的」,而使用者是「此刻在變的」。
> 真正的個人化推薦難在「即時」:使用者這一秒點了什麼,下一個畫面就要反映。這要求你把「離線訓練的模型」跟「線上即時的特徵」接起來,而且兩邊算特徵的邏輯必須一模一樣,否則線上線下不一致,模型準確度直接崩。
> AWS 原生的解法:Kinesis 收即時事件、Feature Store 同時服務線上/離線且保證一致、SageMaker Endpoint 毫秒級推論、DynamoDB 撐高併發查詢。
> 這是 Part 3:當 AI 系統要在「使用者還在線上」的當下做決策時,架構長什麼樣。

---

## 一、情境與痛點:個人化的即時性

推薦系統無所不在:電商的「你可能也喜歡」、影音的「接下來播放」、新聞的資訊流、外送 App 的餐廳排序。它的商業價值最直接——**推得準,轉換率、停留時間、GMV 直接漲**。

但「推得準」有一個常被低估的維度:**即時性(recency)**。

- 使用者剛把一台筆電加入購物車 → 下一頁還在推同一台筆電,體驗很蠢。
- 使用者剛看完一部恐怖片 → 首頁應該立刻多一點同類,而不是等明天的批次。
- 使用者是**新用戶**,沒有歷史 → 冷啟動,你拿什麼推?

這帶出推薦系統最核心的工程難題,不是模型,而是**特徵的即時性與一致性**:

```
離線訓練時:  用「過去 30 天的行為」算出特徵 → 訓練模型
線上服務時:  用「此刻的即時行為」算出特徵 → 餵給同一個模型

如果兩邊算特徵的邏輯不一致(training-serving skew),
模型在線上看到的特徵分佈,跟它訓練時看到的不一樣 → 準確度崩盤。
```

這就是為什麼推薦系統不是「訓練一個模型」那麼簡單,而是要蓋一整套**特徵基礎設施**。

---

## 二、系統目的:功能與非功能需求

**功能需求:**

- 收集即時行為事件(點擊、瀏覽、加購、購買、停留時長)。
- 即時更新使用者特徵(近期偏好、即時 session 行為)。
- 給定 user,回傳個人化排序後的推薦清單(Top-N)。
- 支援**冷啟動**(新用戶 / 新商品)。
- 支援 **A/B 測試**:多個模型版本並行,分流量比較效果。

**非功能需求:**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 線上延遲 | P99 < 100ms | 推薦要嵌在頁面載入路徑上 |
| 特徵一致性 | 線上/離線特徵零 skew | 否則模型準確度不可信 |
| 即時性 | 行為 → 特徵更新 < 數秒 | 「剛剛看過」要立刻反映 |
| 併發 | 尖峰數萬 QPS | 首頁流量 |
| 可實驗 | 模型可灰度、可 A/B、可秒級回滾 | 推薦是持續迭代的 |

「P99 < 100ms」+「特徵零 skew」這兩條,是整個架構的靈魂。前者逼你用線上特徵快取 + 低延遲 endpoint;後者逼你用**同一套特徵定義**同時服務訓練與推論——這正是 SageMaker Feature Store 存在的理由。

---

## 三、系統設計與架構

現代推薦幾乎都是**兩階段:召回(Retrieval)+ 排序(Ranking)**。

- **召回**:從幾百萬個候選商品裡,快速篩出幾百個「可能相關」的候選集。要快、要廣,精度可以粗。
- **排序**:對這幾百個候選,用較重的模型精算每一個的分數,排序取 Top-N。要準,量少所以可以慢一點。

為什麼要兩階段?因為對幾百萬商品逐一用重模型打分,延遲扛不住;而只用重模型又跑不完。先粗篩再精排,是延遲與精度的經典解法。

### 3.1 整體架構

```
        【 即時特徵管線 】                          【 線上服務路徑 】
┌──────────┐  行為事件                    ┌──────────┐  推薦請求   ┌──────────────┐
│  前端/App │ ──────────┐                 │  前端/App │ ─────────▶ │ API Gateway   │
└──────────┘           ▼                 └──────────┘            └──────┬───────┘
              ┌──────────────┐                                          ▼
              │   Kinesis     │                              ┌────────────────────┐
              │  Data Stream  │                              │   Lambda (推論編排)  │
              └──────┬───────┘                              └──┬──────────┬──────┘
                     ▼                                         │          │
              ┌──────────────┐  更新即時特徵                    │召回       │取線上特徵
              │   Lambda      │ ──────────────┐                ▼          ▼
              │ (特徵計算)     │               ▼         ┌──────────┐ ┌────────────────┐
              └──────────────┘      ┌────────────────┐  │ DynamoDB  │ │ Feature Store   │
                                    │ Feature Store   │  │ 候選集/    │ │ (Online Store)  │
                                    │ (Online Store)  │  │ 商品metadata│ └────────┬───────┘
                                    └────────────────┘  └──────────┘          │
                                             │                                 │特徵向量
                       離線同步(自動)         ▼                                 ▼
                                    ┌────────────────┐                ┌────────────────┐
                                    │ Feature Store   │  訓練用         │ SageMaker       │
                                    │ (Offline / S3)  │ ─────────────▶ │ Endpoint(排序)  │
                                    └────────────────┘   訓練模型       └────────┬───────┘
                                                                                 ▼
                                                                        排序後 Top-N 回前端
```

### 3.2 兩條路徑,一個共享的特徵層

- **即時特徵管線(寫入路徑)**:前端把行為事件打進 Kinesis → Lambda 消費、計算即時特徵(如「近 10 分鐘看過的類別」)→ 寫進 Feature Store 的 **Online Store**。Feature Store 會自動把同樣的特徵同步一份到 **Offline Store(S3)** 供訓練用。**同一份特徵定義,同時服務線上推論與離線訓練——這就是消滅 training-serving skew 的機制。**
- **線上服務路徑(讀取路徑)**:請求進來 → Lambda 先做召回(從 DynamoDB 撈候選集)→ 從 Feature Store Online Store 取該 user 的即時特徵 → 組成特徵向量餵給 SageMaker Endpoint 排序 → 回傳 Top-N。

### 3.3 冷啟動怎麼辦

- **新用戶**:沒有個人特徵,召回退化為「熱門 / 趨勢 / 依註冊時填的偏好」,排序用「人口統計特徵」的通用模型。
- **新商品**:沒有互動歷史,用**內容特徵**(標題、類別、圖片 embedding)做 content-based 召回,先曝光收集資料。

冷啟動不是靠模型硬解,而是靠**架構上的 fallback 分支**:特徵不足時走另一條規則路徑。

---

## 四、CDK(CloudFormation)實作

### 4.1 即時事件流:Kinesis + 特徵計算 Lambda

```typescript
// lib/streaming.ts 片段
import * as kinesis from 'aws-cdk-lib/aws-kinesis';
import * as lambdaNode from 'aws-cdk-lib/aws-lambda-nodejs';
import { KinesisEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { StartingPosition } from 'aws-cdk-lib/aws-lambda';
import { Duration } from 'aws-cdk-lib';

const eventStream = new kinesis.Stream(this, 'BehaviorStream', {
  streamMode: kinesis.StreamMode.ON_DEMAND,   // 免自己算 shard,隨流量擴縮
  retentionPeriod: Duration.hours(24),
});

const featureFn = new lambdaNode.NodejsFunction(this, 'FeatureComputeFn', {
  entry: 'lib/lambda/feature-compute/index.ts',
  timeout: Duration.minutes(1),
  memorySize: 512,
  environment: { FEATURE_GROUP: 'user-realtime-features' },
});

featureFn.addEventSource(new KinesisEventSource(eventStream, {
  startingPosition: StartingPosition.LATEST,
  batchSize: 100,
  maxBatchingWindow: Duration.seconds(2),   // 攢 2 秒或 100 筆就觸發,兼顧延遲與效率
  bisectBatchOnError: true,                 // 出錯時二分批,避免整批卡死
  retryAttempts: 3,
}));
```

特徵計算 Lambda:把行為事件轉成特徵,寫進 Feature Store Online Store。

```typescript
// lib/lambda/feature-compute/index.ts
import { SageMakerFeatureStoreRuntimeClient, PutRecordCommand }
  from '@aws-sdk/client-sagemaker-featurestore-runtime';

const fs = new SageMakerFeatureStoreRuntimeClient({});
const GROUP = process.env.FEATURE_GROUP!;

export const handler = async (event: any) => {
  for (const rec of event.Records) {
    const data = JSON.parse(Buffer.from(rec.kinesis.data, 'base64').toString());
    // 假設下游已聚合出即時特徵(近 10 分鐘類別偏好、session 長度…)
    const features = deriveFeatures(data);
    await fs.send(new PutRecordCommand({
      FeatureGroupName: GROUP,
      Record: [
        { FeatureName: 'user_id',        ValueAsString: String(data.userId) },
        { FeatureName: 'event_time',     ValueAsString: data.ts },
        { FeatureName: 'recent_categories', ValueAsString: features.recentCategories.join(',') },
        { FeatureName: 'session_clicks', ValueAsString: String(features.sessionClicks) },
        { FeatureName: 'last_item_id',   ValueAsString: String(data.itemId) },
      ],
    }));
  }
};
```

### 4.2 Feature Store:線上/離線雙寫的特徵群組

Feature Group 用 L1 construct,重點是**同時啟用 Online Store 與 Offline Store**——這就是一致性的來源。

```typescript
// lib/feature-store.ts 片段
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import * as s3 from 'aws-cdk-lib/aws-s3';

const offlineBucket = new s3.Bucket(this, 'FeatureOffline');

new sagemaker.CfnFeatureGroup(this, 'UserFeatureGroup', {
  featureGroupName: 'user-realtime-features',
  recordIdentifierFeatureName: 'user_id',
  eventTimeFeatureName: 'event_time',
  featureDefinitions: [
    { featureName: 'user_id',            featureType: 'String' },
    { featureName: 'event_time',         featureType: 'String' },
    { featureName: 'recent_categories',  featureType: 'String' },
    { featureName: 'session_clicks',     featureType: 'Integral' },
    { featureName: 'last_item_id',       featureType: 'String' },
  ],
  onlineStoreConfig: { enableOnlineStore: true },     // 線上:毫秒級讀取
  offlineStoreConfig: {                               // 離線:自動同步到 S3 供訓練
    s3StorageConfig: { s3Uri: offlineBucket.s3UrlForObject('features') },
  },
  roleArn: featureStoreRole.roleArn,
});
```

### 4.3 候選集與商品資料:DynamoDB

召回階段要極快地撈候選集與商品 metadata,用 DynamoDB(單位數毫秒)。

```typescript
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

// 商品表:itemId 主鍵,存 metadata 與內容 embedding(給冷啟動 content-based 召回)
const itemTable = new dynamodb.Table(this, 'ItemTable', {
  partitionKey: { name: 'itemId', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
});
// 召回候選表:以 category / segment 為 key,value 是預先算好的候選商品清單
const candidateTable = new dynamodb.Table(this, 'CandidateTable', {
  partitionKey: { name: 'segment', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
});
```

### 4.4 SageMaker 排序模型 Endpoint

排序模型部署成 **SageMaker 即時 Endpoint**,開啟自動擴縮以扛尖峰。

```typescript
// lib/ranking-endpoint.ts 片段
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import * as applicationautoscaling from 'aws-cdk-lib/aws-applicationautoscaling';

const model = new sagemaker.CfnModel(this, 'RankingModel', {
  executionRoleArn: smRole.roleArn,
  primaryContainer: {
    image: '<account>.dkr.ecr.<region>.amazonaws.com/ranking:latest',
    modelDataUrl: 's3://<bucket>/models/ranking/model.tar.gz',
  },
});

const endpointConfig = new sagemaker.CfnEndpointConfig(this, 'RankingConfig', {
  productionVariants: [{
    modelName: model.attrModelName,
    variantName: 'v1',
    initialVariantWeight: 1,
    instanceType: 'ml.c6i.xlarge',
    initialInstanceCount: 2,
  }],
});

const endpoint = new sagemaker.CfnEndpoint(this, 'RankingEndpoint', {
  endpointConfigName: endpointConfig.attrEndpointConfigName,
});

// 依 InvocationsPerInstance 自動擴縮
const target = new applicationautoscaling.ScalableTarget(this, 'EpScaling', {
  serviceNamespace: applicationautoscaling.ServiceNamespace.SAGEMAKER,
  resourceId: `endpoint/${endpoint.attrEndpointName}/variant/v1`,
  scalableDimension: 'sagemaker:variant:DesiredInstanceCount',
  minCapacity: 2, maxCapacity: 20,
});
target.scaleToTrackMetric('InvocationScaling', {
  predefinedMetric: applicationautoscaling.PredefinedMetric.SAGEMAKER_VARIANT_INVOCATIONS_PER_INSTANCE,
  targetValue: 750,
});
```

> A/B 測試就靠這裡:在 `productionVariants` 放兩個 variant(v1 / v2),用 `initialVariantWeight` 分流量(如 90/10),SageMaker 幫你把請求按權重分配。要回滾就把權重調回去,秒級生效,不用重新部署。

### 4.5 線上推論編排 Lambda

```typescript
// lib/lambda/recommend/index.ts(核心邏輯示意)
import { SageMakerRuntimeClient, InvokeEndpointCommand } from '@aws-sdk/client-sagemaker-runtime';
import { SageMakerFeatureStoreRuntimeClient, GetRecordCommand }
  from '@aws-sdk/client-sagemaker-featurestore-runtime';

const smrt = new SageMakerRuntimeClient({});
const fsrt = new SageMakerFeatureStoreRuntimeClient({});

export const handler = async (event: any) => {
  const userId = event.requestContext.authorizer?.claims?.sub ?? event.queryStringParameters?.uid;

  // 1) 取線上即時特徵
  const feat = await fsrt.send(new GetRecordCommand({
    FeatureGroupName: 'user-realtime-features',
    RecordIdentifierValueAsString: userId,
  }));
  const hasFeatures = (feat.Record?.length ?? 0) > 0;

  // 2) 召回:有特徵走個人化候選,沒特徵(冷啟動)走熱門
  const candidates = hasFeatures
    ? await recallByUser(userId, feat)     // 查 DynamoDB 候選表
    : await recallTrending();              // 冷啟動 fallback

  // 3) 排序:把候選 + 特徵組成 payload,呼叫 SageMaker Endpoint
  const scored = await smrt.send(new InvokeEndpointCommand({
    EndpointName: process.env.RANKING_ENDPOINT!,
    ContentType: 'application/json',
    Body: JSON.stringify({ userFeatures: toVector(feat), candidates }),
  }));
  const ranking = JSON.parse(new TextDecoder().decode(scored.Body));

  // 4) 取 Top-N 回傳
  return { statusCode: 200, body: JSON.stringify({ items: ranking.slice(0, 20) }) };
};
```

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 自建(SageMaker)vs Amazon Personalize(全託管推薦)

```
選擇            自建 SageMaker 兩階段             Amazon Personalize
──────────────────────────────────────────────────────────────────────
控制權          完全掌握召回/排序/特徵            AWS 幫你端到端,黑箱較多
上手速度        慢(要自己訓練、部署)             快(丟資料就能出推薦)
客製            任意模型、任意特徵                受限於 Personalize recipe
即時性          自己設計,可做到秒級               內建即時個人化
成本            實例費 + 開發成本                 按用量,但規模大時偏貴
```

**翻盤條件**:團隊小、要快速上線、推薦邏輯不需要高度客製 → 直接用 **Amazon Personalize**,它把召回排序特徵全包了,是「推薦版的 Bedrock Knowledge Base」。當你需要客製模型架構、特殊特徵、或要把推薦跟其他 ML 系統深度整合 → 才值得自建。**本篇示範自建,是為了講清楚底層原理;多數團隊的務實起點其實是 Personalize。**

### 5.2 Feature Store vs 自己用 Redis/DynamoDB 存特徵

```
選擇              SageMaker Feature Store          自建 Redis/DynamoDB
──────────────────────────────────────────────────────────────────────
線上/離線一致性    原生保證(同定義雙寫)             要自己確保兩套邏輯一致
時間旅行/回填      內建(point-in-time)             自己做很痛
延遲              線上讀取毫秒級                    Redis 更低,但要自己管
維運              全託管                            自己管叢集
```

**翻盤條件**:當你對延遲極度敏感(要 < 5ms)、且願意自己扛「線上線下特徵一致」的工程負擔 → 用 Redis(ElastiCache)當線上特徵層。但一致性這件事自己做非常容易出錯,Feature Store 的核心價值就是幫你消滅這個最隱蔽的 bug。

### 5.3 Kinesis vs SQS vs Kafka(MSK)

- **Kinesis Data Streams**:全託管、原生接 Lambda、支援多消費者重播、On-Demand 免管 shard——即時行為流的預設首選。
- **SQS**:是佇列不是串流,不能重播、不保順序(標準佇列),不適合「特徵要按時序聚合」的場景。
- **MSK(Kafka)**:生態豐富、吞吐極高,但要自己管叢集;除非你已重度使用 Kafka,否則 Kinesis 的免維運更適合。

### 5.4 SageMaker 即時 Endpoint vs Serverless Inference vs Batch Transform

- **即時 Endpoint**:常駐實例,穩定低延遲,適合高頻線上推論(排序模型正是如此)。
- **Serverless Inference**:免常駐、按用量,但有冷啟動,適合流量稀疏、能容忍偶發延遲的場景。
- **Batch Transform**:離線大批打分,適合「每天預算好推薦」的舊式作法——但那就失去即時性了。

排序在 P99 100ms 的要求下,只能選常駐的即時 Endpoint。

---

## 六、成本估算

以「日活 100 萬、尖峰 1 萬 QPS」估算(概略):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| SageMaker Endpoint | ml.c6i.xlarge × 平均 6 台(2–20 自動擴縮) | **~$1,500–2,000**(常駐大戶) |
| Kinesis On-Demand | 每日數千萬事件 | ~$300–600 |
| Feature Store 線上讀寫 | 高頻讀寫 | ~$400–800 |
| DynamoDB | 召回查詢高併發 | ~$500–1,000 |
| Lambda / API Gateway | 高 QPS | ~$500 |
| **合計** | | **~$3,200–4,900 / 月** |

**成本洞察**:推薦系統的成本結構跟前兩篇又不同——**它是「常駐運算主導」**(SageMaker Endpoint 與 DynamoDB 容量)。因為要求 P99 < 100ms,你不能像 RAG 那樣「零流量零成本」,必須養著常駐機器。優化方向:

- **用兩階段架構本身就是省錢**:召回把候選從百萬砍到數百,排序 Endpoint 的每次推論成本才壓得下來。
- **排序模型盡量小**:能用 gradient boosting(輕量)就別用深度模型,c6i 這種 CPU 實例遠比 GPU 便宜。
- **善用自動擴縮**:離峰把 Endpoint 縮到 min capacity,不要 24 小時滿載。

三篇下來的成本母題已經很清楚:**RAG 是固定成本(向量庫)、IDP 是變動成本(每頁)、推薦是常駐運算成本(低延遲要求)**。系統的延遲需求,直接決定了它的成本形狀。

---

## 七、延伸與常見的坑

**延伸方向:**

- **多目標排序**:不只優化點擊率,還要平衡多樣性、新穎性、商業目標(利潤高的商品)。排序層變成多目標模型。
- **序列模型**:用 Transformer 類序列模型(如 SASRec)捕捉「行為順序」,比靜態特徵更懂使用者當下意圖。
- **近線特徵**:除了即時(Kinesis)與離線(每日訓練),加一層「近線」特徵(每幾分鐘聚合),平衡新鮮度與計算成本。
- **接 Bedrock**:用 LLM 生成推薦理由(「因為你最近看了 X,所以推薦 Y」),提升可解釋性與轉換。

**最容易踩的坑:**

1. **Training-serving skew**:離線訓練用 pandas 算特徵、線上用 Lambda 算特徵,兩套邏輯不知不覺就分岔了。**唯一解是共用同一份特徵定義**(Feature Store 的意義),或至少共用同一份特徵計算程式碼。
2. **冷啟動沒 fallback**:新用戶查不到特徵,Lambda 直接報錯或回空清單。一定要有規則式 fallback 分支。
3. **Endpoint 冷啟動/擴縮跟不上**:尖峰來得比擴縮快,前幾分鐘延遲爆高。用 provisioned capacity 或 predictive scaling 預熱。
4. **候選集過期**:召回候選表如果是離線算的,商品下架了還在推。要設 TTL 並定期刷新。
5. **A/B 測試沒有護欄**:新模型 variant 分了 10% 流量卻默默變差。一定要接 CloudWatch alarm 監控每個 variant 的線上指標,劣化自動調回權重。

---

## 小結

推薦系統把 AI 系統推進到一個新層次:它不再是「處理進來的請求」,而是要在**使用者還在線上的當下、100 毫秒內、用此刻的即時特徵**做出決策。這逼出了兩個關鍵基礎設施——**即時串流(Kinesis)** 與 **線上/離線一致的特徵層(Feature Store)**,以及兩階段召回排序的經典架構。

到目前為止,我們的三個系統都還是「被動響應」:給問題答問題、給文件抽資料、給 user 給推薦。下一篇,系統要開始**主動規劃與行動**——當使用者說「幫我查這個客戶的訂單狀態,如果逾期就發提醒信」,AI 要自己決定呼叫哪些工具、按什麼順序、把結果串起來。這就是 Part 4:自主 AI Agent 工具呼叫系統。

---

## 系列導覽

- **Part 1**:Serverless RAG 智慧客服知識庫
- **Part 2**:智慧文件處理(IDP)管線
- **Part 3(本篇)**:即時個人化推薦系統
- **Part 4**:自主 AI Agent 工具呼叫系統 —— Bedrock Agents + Lambda Action Groups + Guardrails
- **Part 5**:生產化 MLOps 與可觀測性 —— 部署策略、模型日誌、成本治理、CDK CI/CD
