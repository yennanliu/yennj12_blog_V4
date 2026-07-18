---
title: "AI System on Native AWS - Part 7 - 基礎模型客製化與模型治理"
date: 2026-07-24T09:00:00+08:00
draft: false
description: "當通用模型不夠好、或你有大量專有資料想讓模型內化時,就得客製基礎模型。但企業真正的難題不是『怎麼 fine-tune』,而是『如何治理』——訓練資料哪來的、評估過了沒、誰核准上線、出問題能不能回溯。本篇用純 AWS 原生服務打造一條可治理的模型客製管線:RAG/Prompt/Fine-tune/蒸餾的決策框架、資料準備、Bedrock 客製模型與 SageMaker 微調、Model Registry、自動評估關卡、Model Cards 與審批工作流,全部用 CDK(CloudFormation)描述。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Bedrock", "SageMaker", "Fine-tuning", "Model Governance", "MLOps", "Enterprise", "AI Engineering"]
authors: ["yen"]
readTime: "27 min"
---

> 大部分人聽到「模型不夠好」的第一反應是 fine-tune。於是花了三週標資料、燒了一筆 GPU 錢、訓出一個模型——然後發現它在你沒測到的地方變笨了,而且沒人記得訓練資料是哪來的、當初為什麼這樣調。
> 企業客製模型的真正難點,從來不是「怎麼訓」,而是「怎麼治理」:什麼情況才該 fine-tune(多數時候你其實該用 RAG)、訓練資料的來源與授權可追溯嗎、模型上線前過了哪些評估關卡、誰簽核的、出事能不能回滾到上一版。
> 沒有治理的 fine-tune,是把一個黑箱換成一個更貴、更難解釋的黑箱。
> 這是 Part 7:當你決定動模型本身時,如何讓每一步都可稽核、可評估、可回溯。

---

## 一、情境與痛點:先問「該不該客製」,再問「怎麼客製」

先講一個殘酷的事實:**大多數「模型不夠好」的問題,不該用 fine-tune 解**。

企業常見的三種「不夠好」,對應三種不同的解法:

```
症狀                              根因                  正解
──────────────────────────────────────────────────────────────────────
答不出公司內部知識                  模型沒看過你的資料       RAG(Part 1/6),不是 fine-tune
不遵守特定格式/語氣/流程             行為沒對齊              Prompt 工程 → 不夠再 fine-tune
懂領域但術語/風格不對(醫療/法律/金融) 領域分佈偏移            Fine-tune / 領域續訓
要把大模型能力壓進便宜小模型         成本/延遲               蒸餾(Distillation)
```

**用 fine-tune 解「知識缺失」是最常見的錯誤**:你以為把公司文件拿去訓練模型就會記住,實際上它只學到「風格」,知識還是會忘、會幻覺,而且文件一更新你就得重訓。知識問題永遠先用 RAG。

真正該 fine-tune 的場景很窄但很真實:**當你要的是「行為/風格/領域分佈」的改變,而且 prompt 怎麼調都到不了**——例如讓模型穩定輸出特定 JSON schema、用醫療術語但保持謹慎語氣、模仿公司特有的客服話術。這時 fine-tune 才有意義。

而一旦你決定動模型,企業的重心立刻從「技術」轉向「治理」:這是 Part 7 的核心。

---

## 二、系統目的:功能與非功能需求

**功能需求:**

- 一個決策框架:輸入問題類型,輸出該用 RAG / Prompt / Fine-tune / 蒸餾。
- 資料準備管線:蒐集、清洗、去識別化、格式化訓練資料,並記錄來源(lineage)。
- 訓練:支援 Bedrock 客製模型(託管 fine-tune)與 SageMaker 自訂訓練。
- 模型註冊:每個模型版本進 Model Registry,附評估結果與 Model Card。
- 評估關卡:自動評估(準確、安全、偏見)通過才能進入審批。
- 審批工作流:人工簽核後才部署,可一鍵回滾。

**非功能需求:**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 可追溯 | 每個模型可回答「用什麼資料、誰訓的、誰核准的」 | 合規稽核的底線 |
| 可評估 | 上線前有量化的品質/安全門檻 | 防止「感覺變好」的自欺 |
| 可回滾 | 新模型劣化能秒級退回上一版 | 生產安全 |
| 可重現 | 同樣資料 + 設定能重跑出同樣模型 | 稽核與除錯 |
| 資料合規 | 訓練資料的授權與 PII 處理有紀錄 | 法遵紅線 |

這張表的關鍵字全是「可」——**模型治理的本質,是把一個原本靠個人記憶與 notebook 的黑箱流程,變成可追溯、可評估、可回滾、可重現的工程流程**。

---

## 三、系統設計與架構

### 3.1 客製方式決策樹

```
                    「模型不夠好」
                          │
              ┌───────────┴───────────┐
         缺的是「知識」?            缺的是「行為/風格」?
              │                          │
              ▼                     Prompt 能解嗎?
        RAG(Part 1/6)              ┌────┴────┐
        文件更新即生效              能         不能
        零訓練成本                 │           │
                              Prompt 工程   Fine-tune
                                            │
                                   要更便宜/更快嗎?
                                            │
                                        Distillation
                                   (大模型當老師,訓小模型)
```

### 3.2 可治理的模型客製管線

```
┌──────────────┐   ①資料準備(可追溯)
│  原始資料源    │ ──────────────────┐
│ 工單/對話/標註 │                    ▼
└──────────────┘         ┌────────────────────────┐
                         │ 資料準備(SageMaker /     │
                         │ Glue):清洗→去識別化→格式  │
                         │ 化;寫入 lineage 紀錄       │
                         └───────────┬────────────┘
                                     ▼ 訓練集(版本化於 S3)
                         ┌────────────────────────┐
              ②訓練       │ Bedrock 客製模型 或        │
                         │ SageMaker 訓練 Job        │
                         └───────────┬────────────┘
                                     ▼ 候選模型
                         ┌────────────────────────┐
              ③評估關卡   │ 自動評估:準確 / 安全 /     │──不過──▶ 退回,不得上線
                         │ 偏見 / 回歸(LLM-as-judge) │
                         └───────────┬────────────┘
                                     ▼ 通過
                         ┌────────────────────────┐
              ④註冊+審批  │ Model Registry(版本+     │
                         │ Model Card)→ 人工審批     │
                         └───────────┬────────────┘
                                     ▼ 核准
                         ┌────────────────────────┐
              ⑤部署+回滾  │ 部署(Provisioned/Endpoint)│
                         │ 綁 CloudWatch alarm 自動回滾│
                         └────────────────────────┘
```

每個階段都留下**不可變的紀錄**:資料版本、訓練設定、評估分數、審批人、部署時間。這條 audit trail 就是「治理」的實體。

### 3.3 兩條訓練路線:Bedrock 託管 vs SageMaker 自訂

- **Bedrock 客製模型**:提供託管的 fine-tuning(對支援的基礎模型)與 **model distillation**。你上傳訓練資料、選基礎模型、設超參數,Bedrock 幫你訓、產出一個私有的客製模型,用 **Provisioned Throughput** 部署。適合「不想碰訓練基礎設施」的團隊。
- **SageMaker 自訂訓練**:完全掌控——自帶容器、自訂訓練腳本、PEFT/LoRA、任意開源模型。適合需要深度客製或訓練非 Bedrock 模型時。

企業通常兩者並用:能用 Bedrock 託管就用,需要極致控制才落到 SageMaker。

---

## 四、CDK(CloudFormation)實作

### 4.1 資料準備與 lineage

訓練集必須**版本化且可追溯**。用 S3 版本化 + 一張 DynamoDB lineage 表記錄「這版訓練集由哪些來源、用什麼腳本、在何時產生」。

```typescript
// lib/data-prep.ts 片段
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

const trainingBucket = new s3.Bucket(this, 'TrainingData', {
  versioned: true,                         // 訓練集版本化(可重現的前提)
  encryption: s3.BucketEncryption.KMS_MANAGED,
});

// lineage:每個 dataset 版本 → 來源、去識別化紀錄、產生腳本 commit
const lineageTable = new dynamodb.Table(this, 'DatasetLineage', {
  partitionKey: { name: 'datasetVersion', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecovery: true,
});
```

去識別化用 Part 2 的 Comprehend PII 偵測,在資料進訓練集**之前**遮蔽——訓練資料裡帶 PII 是最嚴重的治理事故之一(模型可能把它背出來)。

### 4.2 Bedrock 客製模型(託管 fine-tune)

```typescript
// lib/bedrock-customization.ts 片段
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';

const customizationRole = new iam.Role(this, 'CustomizationRole', {
  assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
});
trainingBucket.grantRead(customizationRole);
outputBucket.grantWrite(customizationRole);

// Fine-tuning job:產出一個私有的客製模型
new bedrock.CfnCustomModel /* 或用 CustomModelJob API 觸發 */ (this, 'CustomModel', {
  modelName: 'support-tone-v3',
  baseModelIdentifier: 'amazon.nova-lite-v1:0',   // 選一個可 fine-tune 的基礎模型
  customizationType: 'FINE_TUNING',
  roleArn: customizationRole.roleArn,
  trainingDataConfig: { s3Uri: `${trainingBucket.s3UrlForObject('v3/train.jsonl')}` },
  validationDataConfig: { validators: [{ s3Uri: trainingBucket.s3UrlForObject('v3/val.jsonl') }] },
  outputDataConfig: { s3Uri: outputBucket.s3UrlForObject('models/support-tone-v3') },
  hyperParameters: { epochCount: '2', learningRate: '0.00001', batchSize: '8' },
});
```

> **蒸餾(Distillation)**在 Bedrock 上是同一套管線的變體:你不提供標註資料,而是提供 prompt,讓一個強「老師模型」(如 Claude)產生回應當訓練訊號,訓出一個便宜小「學生模型」。適合「大模型效果好但太貴」時,把能力壓進小模型省成本——這是 Part 5 成本治理的模型級手段。

### 4.3 自動評估關卡:上線前的品質守門員

**這是整條管線最重要的一段**。候選模型必須通過自動評估才能進審批。評估至少三個維度:準確(回歸測試集)、安全(有害輸出率)、偏見。用一個 evaluation Lambda 對固定測試集打分,任一維度未達門檻就 fail。

```typescript
// lib/lambda/evaluate/index.ts 片段(核心邏輯)
import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
const brt = new BedrockRuntimeClient({});

export const handler = async (event: any) => {
  const { candidateModelArn, testSetUri } = event;
  const testSet = await loadJsonl(testSetUri);   // [{ input, expected }]

  let pass = 0, unsafe = 0;
  for (const t of testSet) {
    const out = await invokeCandidate(candidateModelArn, t.input);
    // 用 LLM-as-judge(強模型當裁判)評分,而非脆弱的字串比對
    const judge = await judgeWithClaude(t.input, t.expected, out);
    if (judge.correct) pass++;
    if (judge.unsafe) unsafe++;
  }
  const accuracy = pass / testSet.length;
  const unsafeRate = unsafe / testSet.length;

  // 門檻:準確率 ≥ 0.85 且 有害率 ≤ 0.01 且 不低於現行 prod 模型
  const gatePassed = accuracy >= 0.85 && unsafeRate <= 0.01
    && accuracy >= (await getProdAccuracy()) - 0.02;   // 回歸防護:不得比現行差

  return { accuracy, unsafeRate, gatePassed };   // gatePassed=false → 管線中止
};
```

> **回歸防護**是治理的靈魂:新模型不只要「夠好」,還要「不比現行差」。很多 fine-tune 在目標任務上進步、卻在其他任務上悄悄退化(catastrophic forgetting)。評估集一定要涵蓋「不該退化的既有能力」,而不只是新任務。

### 4.4 Model Registry + Model Card:可追溯的模型身分證

通過評估的模型註冊進 **SageMaker Model Registry**,並附一份 **Model Card**(記錄用途、訓練資料、評估結果、限制、負責人)。

```typescript
// lib/model-governance.ts 片段
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';

const modelPackageGroup = new sagemaker.CfnModelPackageGroup(this, 'SupportModelGroup', {
  modelPackageGroupName: 'support-tone-models',
  modelPackageGroupDescription: '客服語氣客製模型的版本庫',
});

// 每個通過評估的候選 → 註冊為一個 model package(狀態 PendingManualApproval)
new sagemaker.CfnModelPackage(this, 'SupportModelV3', {
  modelPackageGroupName: modelPackageGroup.modelPackageGroupName,
  modelApprovalStatus: 'PendingManualApproval',    // ★ 預設待審批,不能直接上線
  modelPackageDescription: 'support-tone v3, fine-tuned on 12k curated tickets',
  customerMetadataProperties: {
    datasetVersion: 'v3',
    accuracy: '0.89',
    unsafeRate: '0.004',
    trainedBy: 'ml-platform',
    lineageRef: 'arn:...:dataset/v3',
  },
});
```

SageMaker 也提供 **Model Cards** 這個原生資源,把上述治理資訊結構化保存,產出稽核用的模型文件。

### 4.5 審批與部署:人工簽核 + 自動回滾

審批用 EventBridge 接 Model Registry 狀態變更:當有人把 model package 狀態改為 `Approved`,觸發部署 pipeline;部署綁 CloudWatch alarm 自動回滾(呼應 Part 5)。

```typescript
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';

new events.Rule(this, 'OnModelApproved', {
  eventPattern: {
    source: ['aws.sagemaker'],
    detailType: ['SageMaker Model Package State Change'],
    detail: { ModelApprovalStatus: ['Approved'], ModelPackageGroupName: ['support-tone-models'] },
  },
  targets: [new targets.LambdaFunction(deployFn)],   // deployFn 部署 + 設自動回滾 alarm
});
```

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 RAG vs Fine-tune(最重要的一題)

```
面向            RAG                              Fine-tune
──────────────────────────────────────────────────────────────
知識更新        改文件即生效                       要重訓
可解釋          有引用來源                         黑箱
成本            檢索 + 生成                        訓練 + 託管(Provisioned 貴)
擅長            知識、事實、時效性                  行為、風格、格式、領域語氣
幻覺            低(有依據)                        不因 fine-tune 消失
```

**預設選 RAG。** 只有當問題明確是「行為/風格/格式對齊」且 prompt 到不了時,才 fine-tune。最強的組合往往是**兩者並用**:fine-tune 調語氣與格式,RAG 供知識與時效。

### 5.2 Bedrock 託管 fine-tune vs SageMaker 自訂訓練

```
選擇              Bedrock 客製模型                SageMaker 自訂
──────────────────────────────────────────────────────────────
基礎設施          全託管,不碰 GPU                 自帶容器、自管訓練
模型選擇          限支援的基礎模型                 任意(含開源)
技術如 LoRA/PEFT  抽象掉                          完全掌控
部署              Provisioned Throughput          Endpoint(Part 3)
適合              快速客製、不想維運               深度客製、非 Bedrock 模型
```

**翻盤條件**:要 fine-tune 的模型不在 Bedrock 支援清單、或你要用 LoRA/QLoRA 這類技巧精算成本、或要訓練純開源模型 → SageMaker。否則 Bedrock 託管省下大量基礎設施工。

### 5.3 自動評估 vs 純人工評估

- **純人工評估**:準,但慢、不可規模化、每次改模型都要重找人,而且主觀不一致。
- **自動評估(LLM-as-judge + 固定測試集)**:可重複、可放進管線當關卡、每次 commit 都能跑,是治理能規模化的前提。
- **正解**:自動評估當**必過的關卡**擋在管線裡,人工評估當**上線前的抽樣複核**。兩者不是二選一。

**翻盤條件**:高風險領域(醫療、法律)的最終上線,人工複核不可省;但日常迭代靠自動評估守門。

### 5.4 為什麼「回歸集」比「新任務測試集」更重要

大家都會測「新模型在目標任務上有沒有變好」,卻常忘了測「有沒有把別的能力搞壞」。fine-tune 的災難性遺忘是隱形的——**你優化了 A,B 悄悄退化,而你根本沒測 B**。治理的評估集必須把「現有能力」當成回歸測試守住,這比證明新能力更重要。

---

## 六、成本估算

以「一次 fine-tune 迭代(含資料準備、訓練、評估),客製模型月部署」估算(概略):

| 項目 | 用量 | 概略成本 |
|------|------|---------|
| 資料準備(Glue/SageMaker Processing + Comprehend PII) | 一次性 | ~$50–200 /次 |
| Bedrock fine-tuning job | 依資料量與 epoch | ~$100–1,000 /次 |
| 自動評估(LLM-as-judge) | 每次數百到數千次裁判呼叫 | ~$20–100 /次 |
| 客製模型部署(Provisioned Throughput) | **常駐、按 model unit 計時** | **~$數千 / 月起**(大戶) |
| Model Registry / Model Cards | 幾乎免費 | ~$0 |
| **迭代一次的一次性成本** | | **~$300–1,300** |

**成本洞察**:fine-tune 的隱藏成本不在「訓練」而在「**部署**」。Bedrock 客製模型必須用 **Provisioned Throughput** 託管(不能用 on-demand 隨用隨付),等於你要**常駐付一整套產能的月費**——這往往比訓練貴一個數量級。這帶來一個嚴肅的成本判斷:

- **低頻使用的客製模型不划算**:如果客製模型每天只被呼叫幾千次,常駐 Provisioned 的月費攤下來每次呼叫貴得離譜。此時「RAG + 好的 prompt」幾乎一定更省。
- **只有高頻、且 fine-tune 帶來的效果/成本改善能覆蓋常駐月費時**,客製模型才是對的。**先算清楚 break-even 流量,再決定要不要 fine-tune**——這是 Part 5 成本母題在模型層的具體化。

---

## 七、延伸與常見的坑

**延伸方向:**

- **持續評估(上線後)**:模型上線不是終點。接 Part 5 的可觀測性,持續在真實流量上抽樣評估,偵測資料漂移導致的品質衰退,觸發重訓。
- **蒸餾降本**:用 Claude 當老師蒸餾出小模型,在保留多數能力的同時大砍推論成本,是高頻場景的關鍵手段。
- **A/B 與影子評估**:新客製模型上線前,用 Part 5 的 shadow 模式在真實流量上跟現行模型比,有數據再切。
- **偏見與公平性稽核**:對面向使用者的模型,加入分群(性別、地區)的公平性評估,納入評估關卡。

**最容易踩的坑:**

1. **拿 fine-tune 解知識問題**:最貴、最常見的錯。知識用 RAG,永遠先問「這是知識還是行為問題」。
2. **沒有回歸集**:只測新任務、沒守住舊能力,災難性遺忘上線才發現。
3. **訓練資料帶 PII**:模型會把它背出來,是嚴重的資料外洩。訓練前必須去識別化並留紀錄。
4. **模型可以直接上線**:沒有「PendingManualApproval」的預設狀態與審批關卡,等於沒有治理。
5. **忽略 Provisioned Throughput 的常駐月費**:訓完很興奮,帳單來了才發現部署比訓練貴十倍。先算 break-even。
6. **lineage 斷掉**:三個月後沒人能回答「這個 prod 模型是用哪版資料訓的」,稽核直接不合格。lineage 要從資料準備第一步就記。

---

## 小結

客製模型的企業級難題,是把一個靠個人與 notebook 的黑箱流程,變成**可追溯、可評估、可回滾、可重現**的治理管線。技術上,先用決策樹擋掉「其實該用 RAG」的多數情況;真的要動模型時,Bedrock 託管與 SageMaker 自訂各有位置。但無論哪條路,**評估關卡(尤其回歸防護)、Model Registry、Model Card、審批工作流、lineage 紀錄**,才是「治理」的實體——沒有它們,fine-tune 只是把一個黑箱換成更貴的黑箱。

到目前為止,進階篇處理的都還是「請求-回應」式的系統。下一篇,我們回到即時的世界,但把賭注拉到最高:當系統要在**幾十毫秒內、對每一筆交易做出「放行或攔截」的決定**,而對手是會主動規避你的詐欺集團時,架構要怎麼設計。這是 Part 8:即時串流 ML 與詐欺偵測。

---

## 系列導覽(進階篇)

- **Part 6**:企業級多租戶 RAG 平台
- **Part 7(本篇)**:基礎模型客製化與模型治理
- **Part 8**:即時串流 ML 與詐欺偵測
- **Part 9**:企業 AI 安全、合規與資料治理
- **Part 10**:企業 AI 平台工程 —— 落地區、LLM Gateway 與 FinOps

> 基礎篇回顧:Part 1 RAG 問答 · Part 2 IDP 管線 · Part 3 即時推薦 · Part 4 自主 Agent · Part 5 MLOps 與可觀測性
