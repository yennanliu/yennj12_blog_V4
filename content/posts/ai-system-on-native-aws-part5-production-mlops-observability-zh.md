---
title: "AI System on Native AWS - Part 5 - 生產化 MLOps 與可觀測性"
date: 2026-07-22T09:00:00+08:00
draft: false
description: "前四篇蓋好了四個 AI 系統,但『能跑』跟『敢上線』之間隔著一整套 MLOps。本篇收束整個系列,講清楚 AWS 原生 AI 系統的生產化:SageMaker 的三種部署策略與藍綠/金絲雀更新、Bedrock 模型呼叫日誌與 CloudWatch/X-Ray 可觀測性、模型漂移偵測、成本治理與 tag 分帳、以及用 CDK Pipelines 做基礎設施 CI/CD。全部用 CDK(CloudFormation)描述,並附一張跨五篇的系統對照總表。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "MLOps", "SageMaker", "CloudWatch", "Observability", "Bedrock", "CI/CD", "AI Engineering"]
authors: ["yen"]
readTime: "27 min"
---

> 大部分 AI 專案死在「demo 很成功、上線三個月後沒人敢動」。因為沒有人知道:模型現在準不準?這個月的 token 花了多少、花在誰身上?想更新模型會不會把線上搞掛?出錯了要去哪裡看?
> 「能跑」是原型,「敢上線、敢更新、出事查得到、花多少算得清」才是生產系統。這中間隔著的東西,叫 MLOps。
> AWS 原生的好消息是:可觀測性、部署策略、成本治理這些「非功能」的東西,很多都是 managed service 免費附贈或一行設定就開——CloudWatch 收指標、X-Ray 追鏈路、Bedrock 呼叫日誌記每一次推論、SageMaker 藍綠部署零停機、Cost Allocation Tag 讓每個系統的花費一目了然。
> 這是 Part 5,也是整個系列的收束:把前四個「能跑」的系統,變成「敢上線」的系統。

---

## 一、情境與痛點:「能跑」到「敢上線」之間的鴻溝

回顧一下前四篇,我們蓋了四個 AI 系統:RAG 問答、IDP 管線、即時推薦、自主 Agent。每一個 `cdk deploy` 之後都能動。但「能動」的 demo 跟「敢放給幾十萬人用」的生產系統,中間隔著四個要命的問題:

```
問題           症狀                                   沒解決的下場
──────────────────────────────────────────────────────────────────────
① 看不見      模型變笨了、延遲飆高了,沒人發現           客訴爆了才知道
② 不敢改      想換個更好的模型,但怕改壞線上             系統凍結,技術債累積
③ 算不清      這個月 AI 花了多少?哪個系統燒最兇?        帳單來了才心臟病
④ 追不到      Agent 做錯決定 / RAG 答錯,查不出為什麼    無法歸因,無法改進
```

這四個問題,對應 MLOps 的四根支柱:**可觀測性(看得見)、部署策略(敢改)、成本治理(算得清)、可追溯性(追得到)**。這一篇就逐一拆解,並且用 CDK 把它們變成基礎設施的一部分——**MLOps 不是上線後才補的東西,而是從第一天就 code 進 stack 裡。**

---

## 二、可觀測性:看得見模型的健康

AI 系統的可觀測性比一般後端多一層。一般後端你看「延遲、錯誤率、吞吐」;AI 系統你還要看「**模型行為本身**」——它答對了嗎?它拒答了嗎?token 用了多少?信心分數如何?

### 2.1 三層可觀測性

```
┌──────────────────────────────────────────────────────────┐
│  第三層:模型品質(Model Quality)                          │
│   準確率、拒答率、幻覺率、信心分數分佈、使用者回饋(讚/倒讚)  │
├──────────────────────────────────────────────────────────┤
│  第二層:AI 用量(AI Usage)                                │
│   token in/out、每次呼叫成本、模型延遲、限流(429)次數      │
├──────────────────────────────────────────────────────────┤
│  第一層:基礎設施(Infra)                                  │
│   Lambda 延遲/錯誤、API Gateway 4xx/5xx、DynamoDB 節流      │
└──────────────────────────────────────────────────────────┘
```

第一層用 CloudWatch 內建指標就有。第二層要靠 **Bedrock model invocation logging**。第三層要靠你自己埋(把信心分數、使用者回饋寫成自訂指標)。

### 2.2 Bedrock 模型呼叫日誌:記下每一次推論

Bedrock 可以把**每一次模型呼叫的完整輸入輸出**記到 CloudWatch Logs 與 S3。這是 AI 系統可觀測性與合規審計的基石——出事時,你能精確重現「當時餵了什麼 prompt、模型回了什麼」。

```typescript
// lib/observability.ts 片段:開啟 Bedrock 呼叫日誌
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';

const invocationLogGroup = new logs.LogGroup(this, 'BedrockInvocationLogs', {
  retention: logs.RetentionDays.THREE_MONTHS,
});
const invocationLogBucket = new s3.Bucket(this, 'BedrockLogBucket');

const loggingRole = new iam.Role(this, 'BedrockLoggingRole', {
  assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
});
invocationLogGroup.grantWrite(loggingRole);
invocationLogBucket.grantWrite(loggingRole);

// 帳號層級的 Bedrock logging 設定(每個帳號一份)
new bedrock.CfnApplicationInferenceProfile; // (示意:實務上用 CfnModelInvocationLoggingConfiguration 或 API)
```

> Bedrock 的呼叫日誌是**帳號層級**設定(`PutModelInvocationLoggingConfiguration`),開一次全帳號生效。務必啟用——它同時滿足「除錯」「成本歸因」「合規審計」三個需求。注意 prompt/completion 可能含 PII,S3 桶要加密並限制存取。

### 2.3 自訂指標與儀表板

把「模型品質」指標埋成 CloudWatch 自訂指標,例如 RAG 的「無引用回答率」、IDP 的「轉人工比例」、Agent 的「平均 ReAct 輪數」。

```typescript
// 在各系統的 Lambda 裡發自訂指標
import { CloudWatchClient, PutMetricDataCommand } from '@aws-sdk/client-cloudwatch';
const cw = new CloudWatchClient({});

await cw.send(new PutMetricDataCommand({
  Namespace: 'AISystems/RAG',
  MetricData: [
    { MetricName: 'AnsweredWithoutCitation', Value: citations.length === 0 ? 1 : 0, Unit: 'Count' },
    { MetricName: 'TokensIn',  Value: usage.inputTokens,  Unit: 'Count' },
    { MetricName: 'TokensOut', Value: usage.outputTokens, Unit: 'Count' },
  ],
}));
```

用 CDK 把儀表板與告警也 code 進去:

```typescript
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';

const alarmTopic = new sns.Topic(this, 'AIAlarms');

// 例:RAG「無引用回答率」超過 5% 就告警(可能是檢索壞了或模型在幻覺)
new cw.Metric({ namespace: 'AISystems/RAG', metricName: 'AnsweredWithoutCitation', statistic: 'Average' })
  .createAlarm(this, 'NoCitationAlarm', {
    threshold: 0.05, evaluationPeriods: 3,
    comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  })
  .addAlarmAction(new actions.SnsAction(alarmTopic));

// 例:Bedrock 限流(429)升高告警
new cw.Metric({ namespace: 'AWS/Bedrock', metricName: 'InvocationClientErrors', statistic: 'Sum' })
  .createAlarm(this, 'ThrottleAlarm', {
    threshold: 50, evaluationPeriods: 1,
    comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  })
  .addAlarmAction(new actions.SnsAction(alarmTopic));
```

### 2.4 端到端追蹤:X-Ray

一個 Agent 請求可能穿過 API Gateway → Lambda → Bedrock Agent → 多個工具 Lambda → DynamoDB。出錯時你要知道是哪一段慢/壞。開啟 X-Ray tracing,整條鏈路的火焰圖就有了。

```typescript
// Lambda 開 tracing
new lambdaNode.NodejsFunction(this, 'Fn', {
  tracing: lambda.Tracing.ACTIVE,   // X-Ray
  /* ... */
});
// API Gateway、Step Functions 也各有 tracingEnabled 選項
```

---

## 三、部署策略:敢改的底氣

AI 系統最常見的「不敢動」,是怕換模型/改 prompt 把線上搞壞。解法是**漸進式部署**:新版本先吃一小撮流量,指標沒問題再擴大,壞了自動回滾。

### 3.1 SageMaker 的三種部署形態(呼應 Part 3)

```
形態              適用                           更新策略
──────────────────────────────────────────────────────────
即時 Endpoint     高頻低延遲(推薦排序)           藍綠 / 金絲雀,零停機
Serverless        稀疏流量、可容忍冷啟動           直接換,免管容量
Async Endpoint    大 payload、長推論(影片/大文件)  佇列式,免同步等待
```

### 3.2 SageMaker Endpoint 的藍綠/金絲雀更新

SageMaker 原生支援更新 endpoint 時做**金絲雀(canary)或線性(linear)** 流量轉移,搭配 CloudWatch alarm 自動回滾。

```typescript
// 更新 SageMaker Endpoint 時的部署設定(CfnEndpoint 的 deploymentConfig)
const endpoint = new sagemaker.CfnEndpoint(this, 'RankingEndpoint', {
  endpointConfigName: newConfig.attrEndpointConfigName,
  deploymentConfig: {
    blueGreenUpdatePolicy: {
      trafficRoutingConfiguration: {
        type: 'CANARY',                                  // 先切一小塊
        canarySize: { type: 'CAPACITY_PERCENT', value: 10 },
        waitIntervalInSeconds: 600,                      // 觀察 10 分鐘
      },
      terminationWaitInSeconds: 600,
    },
    autoRollbackConfiguration: {
      alarms: [{ alarmName: modelLatencyAlarm.alarmName }], // 延遲/錯誤超標自動回滾
    },
  },
});
```

### 3.3 Bedrock 的版本控制:用 Alias 而非 hardcode 模型

對 Bedrock 應用,「敢改」的關鍵是**別把模型 ID 寫死在程式碼裡**。用抽象層隔開:

- **Agent / Prompt**:用 **Agent Alias**(如 `prod`、`staging`)指向特定版本。要升級就把 alias 指到新版本,要回滾就指回去——程式碼不動。
- **模型選擇**:把 model ID 放進 SSM Parameter Store 或環境變數,換模型時改設定不改 code。
- **Prompt**:用 **Bedrock Prompt Management** 管理 prompt 版本,而不是散落在程式碼字串裡。

```typescript
// 用 SSM 參數解耦模型選擇,換模型只改參數不改 code
import * as ssm from 'aws-cdk-lib/aws-ssm';
const modelParam = new ssm.StringParameter(this, 'RagModelId', {
  parameterName: '/ai/rag/model-id',
  stringValue: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
});
queryFn.addEnvironment('MODEL_PARAM', modelParam.parameterName);
modelParam.grantRead(queryFn);
```

### 3.4 影子部署(Shadow)評估新模型

要換模型又不敢直接切?**影子模式**:把線上真實流量複製一份餵給新模型,但不回傳給使用者,只記錄新模型的表現。比較新舊模型在**同一批真實流量**上的差異,有數據後再切。SageMaker 的 shadow variant 原生支援這件事。

---

## 四、成本治理:算得清

AI 系統的帳單很容易失控,因為成本藏在「每次呼叫的 token」裡,不像 EC2 那樣一眼看到。治理的核心是**歸因**:每一塊錢花在哪個系統、哪個功能、哪個團隊。

### 4.1 用 Cost Allocation Tag 分帳

給每個系統的資源打上一致的 tag,就能在 Cost Explorer 按系統/團隊/環境切分帳單。CDK 可以在 stack 層級一次打好。

```typescript
// bin/app.ts:給整個 app 打 tag
import { Tags } from 'aws-cdk-lib';

const app = new cdk.App();
const ragStack = new RagStack(app, 'RagStack');
Tags.of(ragStack).add('ai-system', 'rag-chatbot');
Tags.of(ragStack).add('team', 'platform');
Tags.of(ragStack).add('env', 'prod');
Tags.of(ragStack).add('cost-center', 'CC-1042');
```

> 打完 tag 記得去 Billing console 把這些 tag **啟用為 Cost Allocation Tag**(打 tag 本身不會自動出現在帳單分析裡,要手動啟用)。這是最多人漏的一步。

### 4.2 五個系統的成本形狀總覽

跨五篇,我們反覆看到「延遲需求決定成本形狀」這個母題。彙整如下:

```
系統            成本主導項              成本形狀           省錢的關鍵槓桿
──────────────────────────────────────────────────────────────────────────
RAG(P1)        OpenSearch 向量庫       固定成本大         低流量改 Aurora pgvector
IDP(P2)        Textract 每頁費          變動(線性)        前置過濾、只對需要的頁開貴功能
推薦(P3)        SageMaker 常駐實例       常駐運算           兩階段召回、小模型、自動擴縮
Agent(P4)       LLM token × 迴圈輪數     變動(放大)        清楚的工具定義、簡單任務降級
MLOps(P5)       日誌儲存 + 監控          變動(小)          日誌設 retention、抽樣高頻 trace
```

**這張表是整個系列最重要的一張。** 它說明:**沒有「AWS AI 系統的通用成本模型」,成本形狀由系統的延遲與吞吐需求決定**。要求 100ms 就得養常駐機器(推薦);能接受零流量零成本就用 serverless(RAG 查詢層);按件處理就是變動成本(IDP)。設計時先問「我的延遲需求是什麼」,成本形狀就出來了。

### 4.3 主動成本護欄

- **AWS Budgets**:設定每個 tag 的預算,超過門檻自動告警(甚至觸發 Lambda 限流)。
- **Bedrock Provisioned Throughput vs On-Demand**:穩定高流量用 provisioned(折扣),尖峰不定用 on-demand。錯配是常見的浪費。
- **Prompt caching**:Bedrock 支援 prompt caching,重複的長 system prompt 能省下可觀的 input token 費用。

---

## 五、CDK CI/CD:讓基礎設施自己部署自己

前四篇我們都手動 `cdk deploy`。生產環境要的是:**推 code 到 git → 自動測試 → 自動部署到 staging → 人工核准 → 部署到 prod**。用 **CDK Pipelines**(自我變異的 CodePipeline)實現,整條 pipeline 本身也是 CDK 描述的。

```typescript
// lib/pipeline-stack.ts 片段
import * as pipelines from 'aws-cdk-lib/pipelines';

const pipeline = new pipelines.CodePipeline(this, 'AISystemsPipeline', {
  synth: new pipelines.ShellStep('Synth', {
    input: pipelines.CodePipelineSource.gitHub('yennanliu/ai-systems', 'main'),
    commands: ['npm ci', 'npm run test', 'npx cdk synth'],
  }),
});

// staging:自動部署
const staging = new AISystemsStage(this, 'Staging', { env: stagingEnv });
pipeline.addStage(staging, {
  post: [new pipelines.ShellStep('SmokeTest', {
    commands: ['npm run e2e -- --endpoint $API_URL'],   // 打真實 endpoint 做煙霧測試
  })],
});

// prod:人工核准後才部署
const prod = new AISystemsStage(this, 'Prod', { env: prodEnv });
pipeline.addStage(prod, {
  pre: [new pipelines.ManualApprovalStep('PromoteToProd')],
});
```

**這帶來一個閉環**:第二節的 CloudWatch 告警、第三節的自動回滾、第四節的成本 tag、第五節的 pipeline——它們全都是同一份 CDK 程式碼的一部分。基礎設施、監控、部署流程、成本標籤,**全部版本控制、全部 code review、全部可回溯**。這就是「MLOps 從第一天就 code 進 stack」的完整樣貌。

---

## 六、技術選型考量:為什麼選 X 不選 Y

### 6.1 CloudWatch vs 第三方可觀測性(Datadog / Langfuse)

```
選擇              CloudWatch/X-Ray                第三方(Datadog/Langfuse)
──────────────────────────────────────────────────────────────────────
整合              AWS 原生,零額外設定              要接 SDK / agent
LLM 專屬視角      基礎(要自己埋品質指標)           Langfuse 對 LLM trace/評估更專精
成本              按用量,無額外授權費               另付授權
跨雲              綁 AWS                          跨雲/跨供應商統一視圖
```

**翻盤條件**:當你需要**LLM 專屬的深度可觀測性**(prompt 版本比較、逐步 trace、內建評估、標註),Langfuse 這類 LLM-native 工具體驗遠勝 CloudWatch;跨雲或已重度使用 Datadog 的團隊也會選第三方。但若你就在 AWS 上、要快、不想多付授權費,CloudWatch + X-Ray + Bedrock 日誌自己拼,基本盤是夠的。

### 6.2 CDK Pipelines vs 一般 CodePipeline vs GitHub Actions

- **CDK Pipelines**:pipeline 本身用 CDK 定義、能自我變異(改了 pipeline 定義,下次跑會自己更新自己),跟 CDK app 天生一體。
- **一般 CodePipeline**:更多手動配置,適合非 CDK 的部署。
- **GitHub Actions**:跑 `cdk deploy` 也完全可行,團隊已在 GitHub 生態時最省事;缺點是憑證要跨到 AWS(用 OIDC role 解決)。

CDK 專案用 CDK Pipelines 最順;但如果團隊的 CI 標準已是 GitHub Actions,用 Actions 跑 `cdk deploy` 沒有錯,別為了「純」而硬換。

### 6.3 自動回滾 vs 人工回滾

自動回滾(綁 CloudWatch alarm)快、無人值守,適合指標明確的劣化(延遲、錯誤率)。但**模型品質的劣化常常沒有即時指標**(答案變爛不會讓延遲變高)。所以策略是:**基礎指標自動回滾 + 模型品質靠影子評估/離線評測擋在上線前**。別指望自動回滾能接住「模型變笨」這種安靜的劣化。

---

## 七、系列總結:五個系統,一套心法

走完五篇,我們蓋了五個 AWS 原生 AI 系統。最後用一張總表把它們放在一起看:

```
        情境              核心 AWS 服務                  架構母題              成本形狀
────────────────────────────────────────────────────────────────────────────────────────
P1 RAG   知識問答          Bedrock KB + OpenSearch        檢索+生成            固定(向量庫)
        客服/內部知識       Serverless + Lambda            managed RAG
────────────────────────────────────────────────────────────────────────────────────────
P2 IDP   髒文件結構化       Textract + Comprehend +        事件驅動+狀態機       變動(每頁)
        發票/合約/理賠      Bedrock + Step Functions       +冪等+人工回路
────────────────────────────────────────────────────────────────────────────────────────
P3 推薦  即時個人化         Kinesis + Feature Store +      串流+特徵一致性       常駐(低延遲)
        電商/影音/資訊流    SageMaker Endpoint             +兩階段召回排序
────────────────────────────────────────────────────────────────────────────────────────
P4 Agent 自主行動          Bedrock Agents + Lambda        ReAct+工具+護欄       變動(token×輪數)
        客服/維運/自動化    Action Groups + Guardrails     +最小權限+人工關卡
────────────────────────────────────────────────────────────────────────────────────────
P5 MLOps 生產化            CloudWatch + X-Ray +           可觀測+部署+          變動(監控)
        監控/部署/治理      CDK Pipelines + Cost Tag       成本歸因+CI/CD
```

如果只帶走三句話,我希望是這三句:

1. **能外包給 managed service 的,就別自己 host。** 對 90% 的團隊,自己養 GPU、自建向量庫、手刻 ReAct 迴圈不是競爭力,是負債。AWS 原生服務讓你把工程力氣花在「把服務接成解決業務問題的系統」,而不是「維護基礎設施」。

2. **系統的延遲與吞吐需求,決定了它的架構母題與成本形狀。** RAG 要不要即時決定了固定成本、推薦的 100ms 逼出常駐運算、Agent 的多步驟放大了 token 成本。先問需求,再選架構——不是反過來。

3. **MLOps 不是上線後才補的,是從第一天就 code 進 stack 的。** 可觀測性、部署策略、成本標籤、CI/CD,全部用 CDK 描述、全部版本控制。「能跑」跟「敢上線」的距離,就是這一整套非功能設計。

而 CDK(CloudFormation)是貫穿這一切的線:五個系統、每一個資源、每一條權限、每一個告警、每一個成本標籤,都是同一種語言寫出來的、可版本控制、可 review、可一鍵重建的程式碼。這,就是「AI System on Native AWS」的全貌。

感謝一路讀到這裡。願你的下一個 AI 系統,從 demo 到上線,都走得穩。

---

## 系列導覽

- **Part 1**:Serverless RAG 智慧客服知識庫
- **Part 2**:智慧文件處理(IDP)管線
- **Part 3**:即時個人化推薦系統
- **Part 4**:自主 AI Agent 工具呼叫系統
- **Part 5(本篇)**:生產化 MLOps 與可觀測性
