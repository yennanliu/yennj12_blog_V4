---
title: "AI System on Native AWS - Part 2 - 智慧文件處理 IDP 管線"
date: 2026-07-19T09:00:00+08:00
draft: false
description: "當你的『知識』不是乾淨的 Markdown,而是幾百萬張掃描的 PDF、發票、合約時,RAG 那套餵不進去。本篇用純 AWS 原生服務打造一條智慧文件處理(IDP)管線:S3 觸發、Step Functions 編排、Textract 抽文字與表格、Comprehend 做實體與分類、Bedrock 做結構化萃取與摘要,全部用 CDK(CloudFormation)描述,並談事件驅動、冪等、非同步大檔與人工複核。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Textract", "Comprehend", "Bedrock", "Step Functions", "IDP", "Serverless", "AI Engineering"]
authors: ["yen"]
readTime: "25 min"
---

> 大部分人處理「一堆掃描的 PDF」:先找個 OCR 套件,發現表格全亂掉;再寫一堆正則去抓欄位,換一家供應商的發票格式就全爆;最後放棄,回去用人工 key-in。
> AWS 原生的作法是把這件事拆成一條流水線:Textract 負責把像素變成有版面、有表格、有 key-value 的結構;Comprehend 認出裡面的實體與分類;Bedrock 用 LLM 把它們變成你要的乾淨 JSON;Step Functions 把這幾步串成一個可重試、可觀測、可分岔到人工複核的狀態機。
> 沒有一台 OCR 伺服器要你養,單頁到上千頁的合約都能吞,失敗的頁面自動重試、信心分數太低的自動轉人工。
> 這是 Part 2:當文件很髒、很多、很不規則時,AI 系統長什麼樣。

---

## 一、情境與痛點:結構化的世界之外

Part 1 的 RAG 有個隱藏前提:**你的文件已經是乾淨的文字**。但真實世界的企業文件長這樣:

- **保險公司**:每天幾萬張理賠單、診斷證明、收據——掃描件,手寫加印刷混雜。
- **供應鏈**:上百家供應商、上百種格式的發票,每張要抓出品項、數量、稅額、到期日。
- **法務/金融**:幾百頁的合約 PDF,要抽出關鍵條款、當事人、金額、生效日。

這些文件的共同特徵:**非結構化、格式不一、量大、還常常是圖片(掃描件)**。你沒辦法直接 `read()` 出文字,更別說塞進 RAG。

傳統作法的死法很固定:

- **通用 OCR**:能出文字,但**表格結構、欄位對應全丟失**——發票的「單價」跟「數量」被拆成兩串沒關係的文字。
- **正則/模板抽取**:對「固定格式」有效,但供應商一改版面就整組壞掉,維護地獄。
- **人工 key-in**:準,但慢、貴、無法擴張。

IDP(Intelligent Document Processing)要解的就是這個:**把非結構化文件,自動變成可查詢、可入庫的結構化資料**,而且要能容忍格式的多樣性。

---

## 二、系統目的:功能與非功能需求

**功能需求:**

- 支援 PDF、PNG、JPG、TIFF;單頁到上千頁。
- 抽出:純文字、**表格**、**key-value 對**(表單欄位)。
- 辨識實體:人名、公司、日期、金額、地址;支援自訂實體(如保單號)。
- 依文件類型分類(發票 / 合約 / 理賠單…),不同類型走不同萃取邏輯。
- 用 LLM 把抽取結果**正規化成固定 schema 的 JSON**。
- **信心分數低的文件自動轉人工複核**,不是靜默出錯。

**非功能需求:**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 吞吐 | 尖峰每小時數萬頁 | 月結、季報時會爆量 |
| 大檔 | 支援 1000+ 頁,不 timeout | 合約、財報很長 |
| 冪等 | 同一份文件重送不會重複入庫 | 事件驅動一定會有重送 |
| 可觀測 | 每份文件跑到哪一步、為何失敗,可查 | 出錯要能追 |
| 準確 | 低信心自動轉人工,不硬吞 | 錯誤的金額比沒答案更糟 |
| 成本 | 按頁計費,離峰接近零 | 流量高度不均 |

「大檔不 timeout」跟「尖峰爆量」這兩條,直接決定了架構必須是**非同步 + 事件驅動 + 狀態機編排**,而不是一個 Lambda 從頭跑到尾。

---

## 三、系統設計與架構

IDP 的本質是一條**多階段流水線**,而且每一階段的失敗語意不同(Textract 大檔是非同步、Comprehend 是同步、Bedrock 可能 429)。用 **Step Functions** 當編排器是最自然的選擇:它天生支援重試、逾時、分支、等待非同步 callback。

### 3.1 整體架構

```
┌──────────┐  上傳    ┌──────────────┐  ObjectCreated 事件   ┌────────────────┐
│  上傳來源  │ ───────▶│  S3 (raw/)    │ ────────────────────▶│  EventBridge    │
└──────────┘         └──────────────┘                       └───────┬────────┘
                                                                      │ 觸發
                                                                      ▼
                                            ┌──────────────────────────────────────┐
                                            │          Step Functions 狀態機          │
                                            │                                        │
      ┌──────────────┐   啟動非同步任務        │  ① Classify(Bedrock 判斷文件類型)      │
      │   Textract    │◀──────────────────────│  ② Textract(抽文字/表格/KV,大檔非同步) │
      │ (async job)   │──── SNS 完成通知 ─────▶│  ③ Comprehend(實體/自訂實體/分類)      │
      └──────────────┘                        │  ④ Bedrock(正規化成目標 JSON schema)   │
                                            │  ⑤ Choice:信心分數 ≥ 門檻?             │
                                            │       ├─ 是 → 寫入 DynamoDB / S3(json/) │
                                            │       └─ 否 → 送 A2I 人工複核佇列         │
                                            └──────────────┬─────────────────────────┘
                                                           ▼
                     ┌─────────────────┐          ┌─────────────────┐
                     │  DynamoDB        │          │  A2I 人工複核     │──▶ 修正後回寫
                     │ 結構化結果 + 狀態  │          │  (Human Review)  │
                     └─────────────────┘          └─────────────────┘
```

### 3.2 為什麼是 Step Functions 而不是「一個大 Lambda」或「一串 SQS」

- **一個大 Lambda 從頭跑到尾**:Textract 處理 1000 頁 PDF 是非同步、可能跑好幾分鐘,Lambda 15 分鐘上限會爆;而且中間任一步失敗,你得自己寫重試狀態。
- **一串 SQS + Lambda 手接**:可行,但「這份文件現在跑到哪一步、為什麼卡住」你得自己記錄、自己拼可觀測性。
- **Step Functions**:每一步是一個 state,內建 `Retry`/`Catch`/`Timeout`,執行歷史(每份文件走過哪些 state、輸入輸出各是什麼)在 console 上一目了然。對「多階段、要重試、要分支、要人工介入」的流水線,這是為它而生的服務。

### 3.3 大檔怎麼辦:非同步 + Task Token

Textract 對多頁 PDF 用的是**非同步 API**(`StartDocumentAnalysis`),你送出後拿到一個 JobId,處理完它發 SNS 通知。Step Functions 用 **`.waitForTaskToken`** 模式完美對接:狀態機在這一步暫停、把 task token 交給 Textract 的完成 callback,等結果回來才繼續——不佔用任何運算資源在那空等。

---

## 四、CDK(CloudFormation)實作

### 4.1 專案結構

```
idp-pipeline/
├── bin/app.ts
├── lib/
│   ├── idp-stack.ts
│   ├── state-machine.ts            # Step Functions 定義
│   └── lambda/
│       ├── classify/index.ts       # Bedrock 判斷文件類型
│       ├── start-textract/index.ts # 啟動非同步 Textract + 傳遞 task token
│       ├── textract-callback/index.ts # 收 SNS,取結果,SendTaskSuccess
│       ├── extract-entities/index.ts  # Comprehend
│       └── normalize/index.ts      # Bedrock 正規化成 JSON schema
└── package.json
```

### 4.2 儲存、佇列與事件觸發

```typescript
// lib/idp-stack.ts 片段
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sns from 'aws-cdk-lib/aws-sns';
import { RemovalPolicy } from 'aws-cdk-lib';

// 上傳桶:啟用 EventBridge 通知,讓 ObjectCreated 事件進 EventBridge
const rawBucket = new s3.Bucket(this, 'RawBucket', {
  eventBridgeEnabled: true,
  encryption: s3.BucketEncryption.S3_MANAGED,
  removalPolicy: RemovalPolicy.RETAIN,
});
const resultBucket = new s3.Bucket(this, 'ResultBucket', {
  encryption: s3.BucketEncryption.S3_MANAGED,
});

// 結果表:以 documentId 為主鍵,記錄狀態機每一步的產物與狀態
const docTable = new dynamodb.Table(this, 'DocTable', {
  partitionKey: { name: 'documentId', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecovery: true,
});

// Textract 完成通知用的 SNS topic
const textractTopic = new sns.Topic(this, 'TextractDoneTopic');
```

### 4.3 關鍵 Lambda:啟動非同步 Textract 並交出 Task Token

```typescript
// lib/lambda/start-textract/index.ts
import { TextractClient, StartDocumentAnalysisCommand } from '@aws-sdk/client-textract';

const textract = new TextractClient({});

export const handler = async (event: any) => {
  // Step Functions 用 waitForTaskToken 呼叫時,會把 token 放進 payload
  const { bucket, key, taskToken } = event;

  const res = await textract.send(new StartDocumentAnalysisCommand({
    DocumentLocation: { S3Object: { Bucket: bucket, Name: key } },
    FeatureTypes: ['TABLES', 'FORMS'],          // 要表格與 key-value
    NotificationChannel: {
      SNSTopicArn: process.env.TEXTRACT_TOPIC_ARN!,
      RoleArn: process.env.TEXTRACT_ROLE_ARN!,
    },
    // 把 taskToken 藏在 JobTag,callback 時才拿得回來對應到這次執行
    JobTag: Buffer.from(taskToken).toString('base64').slice(0, 64),
    ClientRequestToken: key.replace(/[^a-zA-Z0-9-_]/g, '').slice(0, 64), // 冪等
  }));

  return { jobId: res.JobId };
};
```

> **冪等關鍵**:`ClientRequestToken` 用文件 key 當基礎,同一份文件重送時 Textract 不會重複計費開新 job。事件驅動系統一定會有重送(at-least-once),冪等不是加分項而是必需品。

Textract 完成後發 SNS,由 callback Lambda 取回完整結果,並通知 Step Functions 繼續:

```typescript
// lib/lambda/textract-callback/index.ts
import { TextractClient, GetDocumentAnalysisCommand } from '@aws-sdk/client-textract';
import { SFNClient, SendTaskSuccessCommand, SendTaskFailureCommand } from '@aws-sdk/client-sfn';

const textract = new TextractClient({});
const sfn = new SFNClient({});

export const handler = async (event: any) => {
  const msg = JSON.parse(event.Records[0].Sns.Message);
  const { JobId, Status } = msg;
  const taskToken = /* 依 JobTag / 自建映射還原 taskToken */ await resolveToken(JobId);

  if (Status !== 'SUCCEEDED') {
    await sfn.send(new SendTaskFailureCommand({ taskToken, error: 'TextractFailed' }));
    return;
  }
  // 分頁取回所有 block(大檔會分頁)
  let blocks: any[] = [], nextToken: string | undefined;
  do {
    const r = await textract.send(new GetDocumentAnalysisCommand({ JobId, NextToken: nextToken }));
    blocks.push(...(r.Blocks ?? []));
    nextToken = r.NextToken;
  } while (nextToken);

  await sfn.send(new SendTaskSuccessCommand({
    taskToken,
    output: JSON.stringify({ blockCount: blocks.length /*, 摘要結果存 S3 後傳 pointer */ }),
  }));
};
```

### 4.4 Bedrock 正規化:把抽取結果變成乾淨 JSON

Textract + Comprehend 給你的是「原始抽取」,但你要的是「符合 schema 的乾淨資料」。這一步交給 Bedrock,用 LLM 把雜亂輸入對齊到目標 schema,並自評信心分數。

```typescript
// lib/lambda/normalize/index.ts
import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';

const bedrock = new BedrockRuntimeClient({});

export const handler = async (event: any) => {
  const { docType, textractSummary, entities } = event;

  const prompt = `你是文件萃取引擎。根據下列抽取內容,輸出符合 schema 的 JSON。
文件類型:${docType}
Schema:{ invoiceNo, vendor, issueDate, dueDate, currency, lineItems:[{desc,qty,unitPrice,amount}], totalAmount, confidence }
規則:找不到的欄位填 null,不要編造。confidence 為 0~1,代表你對整體抽取的把握。
抽取內容:
${JSON.stringify({ textractSummary, entities }).slice(0, 15000)}
只輸出 JSON。`;

  const res = await bedrock.send(new InvokeModelCommand({
    modelId: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
    contentType: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }],
    }),
  }));
  const body = JSON.parse(new TextDecoder().decode(res.body));
  const json = JSON.parse(body.content[0].text);
  return json;   // { ...結構化欄位, confidence: 0.xx }
};
```

### 4.5 Step Functions 狀態機:把流程串起來

用 CDK 的 `aws-stepfunctions` 高階 construct 描述狀態機,重點是 **Textract 那步用 `waitForTaskToken`**、以及最後的 **信心分數分支**。

```typescript
// lib/state-machine.ts 片段
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Duration } from 'aws-cdk-lib';

const classify = new tasks.LambdaInvoke(this, 'Classify', {
  lambdaFunction: classifyFn, outputPath: '$.Payload',
});

// Textract:等待 task token(非同步大檔)
const textract = new tasks.LambdaInvoke(this, 'StartTextract', {
  lambdaFunction: startTextractFn,
  integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
  payload: sfn.TaskInput.fromObject({
    bucket: sfn.JsonPath.stringAt('$.bucket'),
    key: sfn.JsonPath.stringAt('$.key'),
    taskToken: sfn.JsonPath.taskToken,
  }),
  timeout: Duration.hours(1),
}).addRetry({ maxAttempts: 3, backoffRate: 2, interval: Duration.seconds(30) });

const entities = new tasks.LambdaInvoke(this, 'ExtractEntities', {
  lambdaFunction: extractEntitiesFn, outputPath: '$.Payload',
});
const normalize = new tasks.LambdaInvoke(this, 'Normalize', {
  lambdaFunction: normalizeFn, outputPath: '$.Payload',
}).addRetry({ maxAttempts: 4, backoffRate: 2, errors: ['ThrottlingException'] }); // Bedrock 429

const persist = new tasks.DynamoPutItem(this, 'Persist', { /* 寫入 docTable */ 
  table: docTable, item: { /* ... */ } as any,
});
const humanReview = new tasks.LambdaInvoke(this, 'ToHumanReview', {
  lambdaFunction: toReviewFn,   // 送 A2I / 人工佇列
});

// 信心分支:>= 0.85 直接入庫,否則轉人工
const confidenceChoice = new sfn.Choice(this, 'ConfidenceGate')
  .when(sfn.Condition.numberGreaterThanEquals('$.confidence', 0.85), persist)
  .otherwise(humanReview);

const definition = classify
  .next(textract)
  .next(entities)
  .next(normalize)
  .next(confidenceChoice);

new sfn.StateMachine(this, 'IdpStateMachine', {
  definitionBody: sfn.DefinitionBody.fromChainable(definition),
  timeout: Duration.hours(2),
  tracingEnabled: true,   // 開 X-Ray
});
```

最後用 EventBridge rule 把「S3 有新檔」接到「啟動狀態機」:

```typescript
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';

new events.Rule(this, 'OnUpload', {
  eventPattern: {
    source: ['aws.s3'],
    detailType: ['Object Created'],
    detail: { bucket: { name: [rawBucket.bucketName] } },
  },
  targets: [new targets.SfnStateMachine(stateMachine)],
});
```

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 Textract vs 開源 OCR(Tesseract 等)

```
選擇        選 Textract 的理由                 選開源 OCR 的理由
──────────────────────────────────────────────────────────────────
Textract    表格/表單結構原生輸出,免訓練         成本敏感、只要純文字、量極大
            非同步大檔、內建高準確度              想完全掌控 / 離線 / 地端
開源 OCR     —                                 願意自己養推論機器與模型
```

**翻盤條件**:文件全是「乾淨的純文字掃描、不需要表格結構、量大到 Textract 帳單痛」時,自架 Tesseract/PaddleOCR 在 Fargate 上跑更省。但只要你需要「表格對齊」「key-value 抽取」,Textract 的 `TABLES`/`FORMS` 幾乎沒有免訓練的對手。

### 5.2 為什麼要 Comprehend + Bedrock 兩個都用

- **Comprehend**:偵測 PII、內建/自訂實體、語言、情感——**便宜、穩定、批次友善**,適合「大量、規則明確」的抽取(遮蔽 PII、抓保單號)。
- **Bedrock(LLM)**:處理「需要理解語意、跨欄位推理、正規化格式」的活——把亂七八糟的抽取拼成乾淨 schema、判斷文件類型、生成摘要。

用 Comprehend 做「便宜的粗抽」、用 Bedrock 做「貴但聰明的細修」,是成本與能力的最佳分工。全部丟給 LLM 會貴且慢;全部靠 Comprehend 又處理不了語意正規化。

### 5.3 Step Functions vs 自寫 SQS/Lambda 編排

```
選擇             選 Step Functions               選 SQS+Lambda
────────────────────────────────────────────────────────────────
可觀測性         每次執行的 state 歷史內建          要自己記錄狀態到 DB
重試/逾時/分支    宣告式,內建                      自己寫,容易漏 case
非同步 callback   waitForTaskToken 原生            自己維護 token 映射
成本             按 state transition 計費          極高頻時 SQS 可能更省
```

**翻盤條件**:當流程極度簡單(就一兩步)、或吞吐高到 Step Functions 的 state transition 計費變顯著時,SQS + Lambda 更省。但 IDP 這種「多階段、要人工分支、要追蹤每份文件」的場景,Step Functions 的可觀測性價值遠超那點費用。

### 5.4 信心門檻與 A2I 人工複核

不要追求「100% 自動化」。真正 production-grade 的 IDP 一定有一條**人工複核回路**:低信心的文件轉給 **Amazon A2I(Augmented AI)** 或自建審核佇列,人工修正後回寫,同時把修正資料累積起來——未來可用來微調自訂模型或改進 prompt。**「自動處理 95%、人工兜底 5%」比「假裝 100% 自動、但 5% 靜默出錯」健康得多**,尤其在金額、法律條款這種錯不起的欄位。

---

## 六、成本估算

以「每月 50 萬頁,平均每份 5 頁 = 10 萬份文件」估算(概略):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| Textract(Tables+Forms) | 50 萬頁 × ~$0.065/頁 | **~$32,500**(成本大戶) |
| Comprehend(實體偵測) | 50 萬份單位 | ~$500–1,000 |
| Bedrock 正規化(Claude) | 10 萬次 × ~3K token | ~$300–600 |
| Step Functions | 10 萬次執行 × ~6 transitions | ~$150 |
| Lambda / DynamoDB / S3 | 一般用量 | ~$100 |
| **合計** | | **~$33,500 / 月** |

**成本洞察**:IDP 的成本幾乎完全被 **Textract 的每頁費用**主宰,而且是**變動成本**(跟頁數線性相關)。這帶來兩個很實際的優化方向:

- **不要對每一頁都開 `TABLES + FORMS`**:先用便宜的「純文字偵測」或 Bedrock 分類判斷「這頁有沒有表格/表單」,只對真正需要的頁開昂貴 feature。可省 30–50%。
- **前置去重與過濾**:空白頁、重複頁、封面頁不需要進 Textract。一個便宜的預處理 Lambda 就能砍掉可觀比例。

跟 Part 1 的 RAG(固定成本大、變動小)剛好相反:**IDP 是變動成本主導**,所以優化重點在「少送一點進貴的服務」,而不是「攤平固定成本」。

---

## 七、延伸與常見的坑

**延伸方向:**

- **接回 Part 1 的 RAG**:IDP 產出的乾淨 JSON + 文字,正好可以灌進 Bedrock Knowledge Base,讓「掃描的合約」也能被問答。IDP 是 RAG 的上游資料工廠。
- **自訂文件類型分類器**:當文件類型很多,用 Comprehend Custom Classification 訓練一個分類器,比每次都呼叫 LLM 便宜且快。
- **自訂實體**:保單號、案件編號這種你家特有的欄位,用 Comprehend 自訂實體識別訓練。
- **回饋閉環**:把人工複核的修正,累積成訓練/評估集,持續改進 prompt 與門檻。

**最容易踩的坑:**

1. **同步 vs 非同步用錯**:單頁圖片可用同步 `AnalyzeDocument`,但多頁 PDF 一定要用非同步 `StartDocumentAnalysis`,否則直接失敗。
2. **忘了分頁取結果**:`GetDocumentAnalysis` 對大檔會分頁回傳,漏了 `NextToken` 你只會拿到前面幾頁。
3. **冪等沒做**:S3 事件是 at-least-once,同一份文件可能觸發兩次。沒有 `ClientRequestToken` 與 DynamoDB 條件寫入,你會重複入庫、重複計費。
4. **Bedrock 429 沒重試**:正規化那步在爆量時最容易撞 Bedrock 限流,`Retry` 一定要涵蓋 `ThrottlingException` 並用指數退避。
5. **PII 沒遮**:文件裡常有身分證號、卡號,入庫前用 Comprehend PII 偵測遮蔽,否則資料庫本身變成資安風險。

---

## 小結

當「知識」很髒、很多、還是圖片時,你需要的不是一個模型,而是**一條流水線**。AWS 原生的 IDP 把這條流水線拆成幾個各司其職的 managed service:Textract 看懂版面、Comprehend 抓實體、Bedrock 做語意正規化、Step Functions 編排與容錯、A2I 兜底人工——你只寫幾個 Lambda 與一份 CDK。

跟 RAG 相比,IDP 教會我們一個新的架構母題:**事件驅動 + 狀態機編排 + 冪等 + 人工回路**。這套母題在下一篇會再進化——當系統不只是「處理進來的資料」,而是要**即時對每個使用者做出個人化決策**時,我們會走進串流與特徵工程的世界:即時個人化推薦系統。

---

## 系列導覽

- **Part 1**:Serverless RAG 智慧客服知識庫
- **Part 2(本篇)**:智慧文件處理(IDP)管線
- **Part 3**:即時個人化推薦系統 —— Kinesis + Feature Store + SageMaker Endpoint
- **Part 4**:自主 AI Agent 工具呼叫系統 —— Bedrock Agents + Lambda Action Groups + Guardrails
- **Part 5**:生產化 MLOps 與可觀測性 —— 部署策略、模型日誌、成本治理、CDK CI/CD
