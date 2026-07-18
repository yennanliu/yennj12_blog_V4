---
title: "AI System on Native AWS - Part 1 - Serverless RAG 智慧客服知識庫"
date: 2026-07-18T09:00:00+08:00
draft: false
description: "用純 AWS 原生服務打造一套 Serverless RAG 問答系統:Bedrock Knowledge Bases 負責切塊與嵌入、OpenSearch Serverless 當向量庫、Lambda + API Gateway 提供問答 API,全部用 CDK(CloudFormation)一鍵部署。本篇是系列開場,先講清楚 RAG 這個最常見的 AI 系統怎麼在 AWS 上長出來,包含情境、系統設計、架構、CDK 實作、技術選型與成本。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Bedrock", "RAG", "OpenSearch Serverless", "Lambda", "LLM", "AI Engineering", "Serverless"]
authors: ["yen"]
readTime: "24 min"
---

> 大部分人做企業內部問答機器人:租一台 GPU、裝 LangChain、自己接一個 Pinecone、再寫一堆膠水程式碼,三個月後發現光是「文件更新後要重新 embedding」這件事就沒人想維護。
> AWS 原生的作法不一樣:文件丟進 S3,Bedrock Knowledge Bases 自動幫你切塊、嵌入、同步進向量庫;問答時呼叫一個 `RetrieveAndGenerate` API,連檢索帶生成、還附引用來源,一次搞定。
> 沒有一台伺服器需要你開機、沒有一個模型需要你自己 host,計費按呼叫次數走,資料永遠不離開你的 AWS 帳號。
> 這一系列會帶你走過五種「最常見、最能直接落地」的 AWS 原生 AI 系統;這篇 Part 1,我們從所有 AI 應用的起點——RAG 問答——開始。

---

## 關於這個系列

「在雲上做 AI」有兩條路。一條是把 AWS 當成一台大型的 Linux 機房:自己開 EC2、自己裝 vLLM、自己管 Kubernetes、自己接開源向量庫。另一條是**用 AWS 原生的 managed AI 服務**(Bedrock、SageMaker、Textract、Comprehend、Personalize…),把「模型 host、擴縮、容錯」全部外包給雲廠商,你只寫「把這些服務接起來」的黏合邏輯。

這個系列走的是第二條路。原因很簡單:**對 90% 的團隊來說,自己 host 模型不是核心競爭力,而是負債**。我們會用五篇,各自完整拆解一個最常見的 AWS 原生 AI 系統,每一篇都包含:**情境與痛點 → 系統目的 → 系統設計與架構 → CDK(CloudFormation)實作 → 技術選型考量 → 成本 → 延伸與坑**。

- **Part 1(本篇)**:Serverless RAG 智慧客服知識庫 —— Bedrock Knowledge Bases + OpenSearch Serverless
- **Part 2**:智慧文件處理(IDP)管線 —— Textract + Comprehend + Bedrock + Step Functions
- **Part 3**:即時個人化推薦系統 —— Kinesis + Feature Store + SageMaker Endpoint
- **Part 4**:自主 AI Agent 工具呼叫系統 —— Bedrock Agents + Lambda Action Groups + Guardrails
- **Part 5**:生產化 MLOps 與可觀測性 —— SageMaker 部署策略、模型呼叫日誌、成本治理、CDK CI/CD

全系列的基礎設施都用 **AWS CDK(TypeScript)** 描述,底層產出的就是 CloudFormation。為什麼是 CDK 不是手刻 CloudFormation YAML?這個問題我們在本篇最後會回答。

---

## 一、情境與痛點:為什麼 RAG 是所有 AI 系統的起點

先講一個具體場景。

你是一家 SaaS 公司,累積了三年的產品文件、API 手冊、客服工單、內部 Wiki——加起來幾千份 PDF 跟 Markdown。現在有兩群人每天都在問同樣的問題:

- **客戶**:「你們的 webhook 重試機制是幾次?」「企業版支援 SSO 嗎?」——這些答案文件裡都有,但客戶找不到,只好開工單。
- **新進客服/工程師**:「這個錯誤碼是什麼意思?」「退款流程的 SOP 在哪?」——答案散在十個不同系統裡。

你想做一個問答機器人,讓大家用**自然語言**問,系統從**你自己的文件**裡找答案,並且**附上出處**(這樣才敢信)。這就是 RAG(Retrieval-Augmented Generation,檢索增強生成)。

為什麼不直接把文件塞給 LLM、或直接用 ChatGPT?三個致命問題:

- **上下文塞不下**:幾千份文件動輒上千萬 token,任何模型的 context window 都放不下。
- **會幻覺**:純 LLM 沒看過你的內部文件,只會一本正經地編一個看起來很合理的答案。
- **資料外流**:把內部合約、客戶資料貼到外部 ChatGPT,法遵直接否決。

RAG 的解法是:**先檢索、再生成**。把「找出最相關的幾段文字」跟「用這幾段文字生成答案」拆成兩步。

```
使用者問題
    │
    ▼
┌──────────────┐    把問題轉成向量,去向量庫找最像的 K 段文字
│   檢索 Retrieve │ ─────────────────────────────────────────▶ 相關文件片段 ×K
└──────────────┘
    │
    ▼
┌──────────────┐    把「問題 + 檢索到的片段」一起丟給 LLM
│   生成 Generate │ ─────────────────────────────────────────▶ 有根據、附引用的答案
└──────────────┘
```

RAG 之所以是「所有 AI 系統的起點」,是因為它是最小、最實用、投報率最高的一個 LLM 應用:**不需要訓練模型、不需要標資料、當天就能看到價值**。也因此,它幾乎是每個團隊踏進 AWS AI 的第一步。

---

## 二、系統目的:功能與非功能需求

在動手前,先把「這個系統到底要做到什麼」講清楚。這一步決定了後面所有的架構取捨。

**功能需求(Functional):**

- 支援上傳 PDF / Word / Markdown / HTML,系統自動切塊、嵌入、建索引。
- 文件更新後能**增量同步**,不用整批重建。
- 問答時回傳答案 **+ 引用來源**(哪份文件、哪一段)。
- 支援多輪對話(記得上一個問題的脈絡)。
- 依使用者身分做**文件層級的權限過濾**(客戶只能看到公開文件)。

**非功能需求(Non-functional):**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 延遲 | P95 < 3.5s(檢索 + 生成) | 客服對話體感能接受的上限 |
| 準確性 | 答案必須可溯源,禁止無引用回答 | 沒有出處的答案不敢給客戶 |
| 資料主權 | 文件與向量永不離開自己的 AWS 帳號 | 法遵、資安紅線 |
| 維運 | 無伺服器需長期開機,免管 GPU | 團隊沒有 MLOps 人力 |
| 成本 | 隨用量計費,零流量近乎零成本 | 初期流量不確定 |
| 擴縮 | 能從 10 QPS 平滑到 500 QPS | 上線後流量會爆發 |

這張表就是我們選 **Serverless + Bedrock 全託管**路線的理由:團隊沒有 MLOps 人力、要資料主權、要隨用量計費——這三條同時成立時,自己 host 模型幾乎必輸。

---

## 三、系統設計與架構

整個系統拆成兩條資料流:**離線的知識注入(Ingestion)** 與 **線上的問答(Query)**。

### 3.1 整體架構

```
                         【 Ingestion:離線知識注入 】
┌──────────┐   上傳    ┌──────────────┐   觸發同步   ┌───────────────────────┐
│  文件來源  │ ───────▶ │   S3 Bucket   │ ──────────▶ │  Bedrock Knowledge Base │
│ PDF/MD/… │          │  (docs/)      │             │  ┌──────────────────┐  │
└──────────┘          └──────────────┘             │  │ 1. Chunking 切塊  │  │
                                                    │  │ 2. Titan Embed   │  │
                                                    │  │    嵌入向量        │  │
                                                    │  └────────┬─────────┘  │
                                                    └───────────┼────────────┘
                                                                ▼
                                                    ┌───────────────────────┐
                                                    │ OpenSearch Serverless   │
                                                    │  (向量索引 + metadata)   │
                                                    └───────────────────────┘

                         【 Query:線上問答 】
┌──────────┐  HTTPS   ┌──────────────┐   invoke   ┌──────────────┐
│  前端/App │ ───────▶ │ API Gateway   │ ─────────▶ │    Lambda     │
│(Cognito) │          │  (REST/JWT)   │           │ (Orchestrator)│
└──────────┘          └──────────────┘           └───────┬──────┘
      ▲                                                   │ RetrieveAndGenerate
      │  答案 + 引用                                        ▼
      │                                          ┌────────────────────────┐
      └──────────────────────────────────────── │  Bedrock KB + Claude     │
                                                 │  檢索 K 段 → 生成帶引用答案 │
                                                 └────────────────────────┘
```

核心洞察:**Bedrock Knowledge Bases 把 RAG 裡最麻煩的那半(切塊策略、embedding 呼叫、向量庫同步、retrieval 排序)全部包成一個 managed service**。你不用自己寫 chunking、不用自己呼叫 embedding model、不用自己維護「文件改了要 reindex」的排程。你只要:(1) 把文件丟 S3;(2) 呼叫一次 `StartIngestionJob` 或開啟自動同步;(3) 問答時呼叫 `RetrieveAndGenerate`。

### 3.2 線上問答的資料流(一次請求發生什麼)

1. 前端帶著 Cognito 發的 JWT 打 API Gateway。
2. API Gateway 用 Cognito Authorizer 驗證 token,通過才轉給 Lambda。
3. Lambda 呼叫 Bedrock 的 `RetrieveAndGenerate`,帶上使用者問題、Knowledge Base ID、要用的生成模型(Claude)。
4. Bedrock 內部:把問題向量化 → 去 OpenSearch Serverless 找最相關的 K 段 → 把片段 + 問題組成 prompt → 呼叫 Claude 生成 → 回傳答案與 `citations`(每段答案對應到哪個文件片段)。
5. Lambda 把答案與引用整理成前端要的 JSON 回傳。

關鍵是:**檢索與生成這兩步,在 `RetrieveAndGenerate` 裡是一次 API 呼叫完成的**。你也可以拆成 `Retrieve`(只檢索)+ 自己組 prompt 呼叫 `InvokeModel`(自己生成),換取更多控制權——這個取捨我們在第五節談。

---

## 四、CDK(CloudFormation)實作

以下用 AWS CDK v2(TypeScript)描述整套基礎設施。CDK 合成出來的就是 CloudFormation 模板,`cdk deploy` 底層走的是 CloudFormation 的 change set。

### 4.1 專案結構

```
rag-chatbot/
├── bin/app.ts                      # CDK app 進入點
├── lib/
│   ├── rag-stack.ts                # 主 stack
│   ├── constructs/
│   │   ├── vector-store.ts         # OpenSearch Serverless collection
│   │   ├── knowledge-base.ts       # Bedrock Knowledge Base + Data Source
│   │   └── query-api.ts            # API Gateway + Lambda + Cognito
│   └── lambda/
│       └── query/index.ts          # 問答 orchestrator
├── cdk.json
└── package.json
```

### 4.2 向量庫:OpenSearch Serverless Collection

Bedrock Knowledge Base 需要一個向量庫。這裡用 OpenSearch Serverless(向量檢索用途),它需要三種 policy:加密(encryption)、網路(network)、資料存取(data access)。

```typescript
// lib/constructs/vector-store.ts
import { Construct } from 'constructs';
import * as oss from 'aws-cdk-lib/aws-opensearchserverless';

export interface VectorStoreProps {
  collectionName: string;
  /** 稍後會建立的 KB 執行角色 ARN,要放進 data access policy */
  kbRoleArn: string;
}

export class VectorStore extends Construct {
  public readonly collection: oss.CfnCollection;

  constructor(scope: Construct, id: string, props: VectorStoreProps) {
    super(scope, id);

    // 1) 加密 policy:用 AWS 託管金鑰加密整個 collection
    const encryptionPolicy = new oss.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: `${props.collectionName}-enc`,
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: [`collection/${props.collectionName}`] }],
        AWSOwnedKey: true,
      }),
    });

    // 2) 網路 policy:此範例用 public endpoint(正式環境建議改 VPC endpoint)
    const networkPolicy = new oss.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: `${props.collectionName}-net`,
      type: 'network',
      policy: JSON.stringify([{
        Rules: [
          { ResourceType: 'collection', Resource: [`collection/${props.collectionName}`] },
          { ResourceType: 'dashboard', Resource: [`collection/${props.collectionName}`] },
        ],
        AllowFromPublic: true,
      }]),
    });

    // 3) collection 本體:type = VECTORSEARCH
    this.collection = new oss.CfnCollection(this, 'Collection', {
      name: props.collectionName,
      type: 'VECTORSEARCH',
      description: 'Vector store for RAG knowledge base',
    });
    this.collection.addDependency(encryptionPolicy);
    this.collection.addDependency(networkPolicy);

    // 4) 資料存取 policy:允許 KB 角色讀寫索引
    const dataAccessPolicy = new oss.CfnAccessPolicy(this, 'DataAccessPolicy', {
      name: `${props.collectionName}-data`,
      type: 'data',
      policy: JSON.stringify([{
        Rules: [
          {
            ResourceType: 'index',
            Resource: [`index/${props.collectionName}/*`],
            Permission: ['aoss:CreateIndex', 'aoss:ReadDocument', 'aoss:WriteDocument',
                         'aoss:UpdateIndex', 'aoss:DescribeIndex'],
          },
          {
            ResourceType: 'collection',
            Resource: [`collection/${props.collectionName}`],
            Permission: ['aoss:CreateCollectionItems', 'aoss:DescribeCollectionItems'],
          },
        ],
        Principal: [props.kbRoleArn],
      }]),
    });
    this.collection.addDependency(dataAccessPolicy);
  }
}
```

> 注意 OpenSearch Serverless 的 data access policy 是**它自己一套**權限系統,跟 IAM 分開。很多人第一次踩的坑就是 IAM 給了權限、KB 卻還是連不進 collection——因為忘了在 aoss data access policy 裡把 KB 角色列為 Principal。

### 4.3 Bedrock Knowledge Base 與 Data Source

Knowledge Base 用 L1 construct(`CfnKnowledgeBase`)。它綁定:一個 embedding 模型(Titan Embeddings)、一個向量庫(上面的 collection)、一個 data source(S3)。

```typescript
// lib/constructs/knowledge-base.ts
import { Construct } from 'constructs';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Stack } from 'aws-cdk-lib';

export interface KnowledgeBaseProps {
  docsBucket: s3.Bucket;
  collectionArn: string;
  kbRole: iam.Role;
  embeddingModelArn: string;   // Titan Embeddings v2
}

export class KnowledgeBase extends Construct {
  public readonly knowledgeBaseId: string;

  constructor(scope: Construct, id: string, props: KnowledgeBaseProps) {
    super(scope, id);
    const region = Stack.of(this).region;

    const kb = new bedrock.CfnKnowledgeBase(this, 'KB', {
      name: 'support-knowledge-base',
      roleArn: props.kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: props.embeddingModelArn,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: props.collectionArn,
          vectorIndexName: 'support-index',
          fieldMapping: {
            vectorField: 'vector',
            textField: 'text',
            metadataField: 'metadata',
          },
        },
      },
    });

    // Data Source:S3 + 固定大小切塊(300 token,overlap 20%)
    new bedrock.CfnDataSource(this, 'S3DataSource', {
      knowledgeBaseId: kb.attrKnowledgeBaseId,
      name: 's3-docs',
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: { bucketArn: props.docsBucket.bucketArn },
      },
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: 'FIXED_SIZE',
          fixedSizeChunkingConfiguration: { maxTokens: 300, overlapPercentage: 20 },
        },
      },
    });

    this.knowledgeBaseId = kb.attrKnowledgeBaseId;
  }
}
```

Knowledge Base 的執行角色需要能:讀 S3、呼叫 embedding 模型、寫 OpenSearch Serverless。

```typescript
// rag-stack.ts 片段:KB 執行角色
const kbRole = new iam.Role(this, 'KbRole', {
  assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
});
docsBucket.grantRead(kbRole);
kbRole.addToPolicy(new iam.PolicyStatement({
  actions: ['bedrock:InvokeModel'],
  resources: [`arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`],
}));
kbRole.addToPolicy(new iam.PolicyStatement({
  actions: ['aoss:APIAccessAll'],
  resources: [vectorStore.collection.attrArn],
}));
```

### 4.4 問答 API:Lambda + API Gateway + Cognito

問答 Lambda 只做一件事:呼叫 `RetrieveAndGenerate`,整理回傳。

```typescript
// lib/lambda/query/index.ts
import { BedrockAgentRuntimeClient, RetrieveAndGenerateCommand }
  from '@aws-sdk/client-bedrock-agent-runtime';

const client = new BedrockAgentRuntimeClient({});
const KB_ID = process.env.KNOWLEDGE_BASE_ID!;
const MODEL_ARN = process.env.MODEL_ARN!;   // Claude 的推論 profile ARN

export const handler = async (event: any) => {
  const { question, sessionId } = JSON.parse(event.body ?? '{}');

  const res = await client.send(new RetrieveAndGenerateCommand({
    input: { text: question },
    ...(sessionId ? { sessionId } : {}),
    retrieveAndGenerateConfiguration: {
      type: 'KNOWLEDGE_BASE',
      knowledgeBaseConfiguration: {
        knowledgeBaseId: KB_ID,
        modelArn: MODEL_ARN,
        retrievalConfiguration: {
          vectorSearchConfiguration: { numberOfResults: 5 },  // 取 Top-5 片段
        },
      },
    },
  }));

  // 整理引用來源:每一段 citation 對應到哪個 S3 檔案
  const citations = (res.citations ?? []).flatMap(c =>
    (c.retrievedReferences ?? []).map(r => ({
      source: r.location?.s3Location?.uri,
      snippet: r.content?.text?.slice(0, 200),
    })));

  return {
    statusCode: 200,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      answer: res.output?.text,
      sessionId: res.sessionId,       // 回傳 sessionId 以支援多輪對話
      citations,
    }),
  };
};
```

把 Lambda 掛到 API Gateway,並用 Cognito User Pool 保護:

```typescript
// lib/constructs/query-api.ts 片段
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as lambdaNode from 'aws-cdk-lib/aws-lambda-nodejs';
import { Duration } from 'aws-cdk-lib';

const userPool = new cognito.UserPool(this, 'UserPool', { selfSignUpEnabled: false });

const queryFn = new lambdaNode.NodejsFunction(this, 'QueryFn', {
  entry: 'lib/lambda/query/index.ts',
  timeout: Duration.seconds(30),
  memorySize: 512,
  environment: { KNOWLEDGE_BASE_ID: kbId, MODEL_ARN: modelArn },
});
// 只給 Lambda 呼叫這個 KB 的權限
queryFn.addToRolePolicy(new iam.PolicyStatement({
  actions: ['bedrock:RetrieveAndGenerate', 'bedrock:Retrieve', 'bedrock:InvokeModel'],
  resources: ['*'],   // 正式環境請收斂到特定 KB 與 model ARN
}));

const api = new apigw.RestApi(this, 'RagApi', {
  defaultCorsPreflightOptions: { allowOrigins: apigw.Cors.ALL_ORIGINS },
});
const authorizer = new apigw.CognitoUserPoolsAuthorizer(this, 'Auth', {
  cognitoUserPools: [userPool],
});
api.root.addResource('ask').addMethod('POST',
  new apigw.LambdaIntegration(queryFn),
  { authorizer, authorizationType: apigw.AuthorizationType.COGNITO });
```

### 4.5 部署

```bash
npm install
npx cdk bootstrap           # 首次:建立 CDK 需要的 S3/IAM 資源
npx cdk synth               # 合成 CloudFormation 模板,先看一眼
npx cdk deploy              # 底層走 CloudFormation change set 部署
# 部署後:上傳文件到 docs bucket,再啟動一次 ingestion job
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <KB_ID> --data-source-id <DS_ID>
```

從 `cdk synth` 到系統上線,你沒有碰過任何一台伺服器、沒有 host 任何一個模型。這就是「原生 AWS」的意義。

---

## 五、技術選型考量:為什麼選 X 不選 Y

RAG 系統每一個元件都有替代方案。以下是幾個關鍵決策,以及「什麼時候該翻盤選 Y」。

### 5.1 Bedrock Knowledge Bases vs 自建 LangChain 管線

```
選擇                  選 Bedrock KB 的理由              自建 LangChain 的理由
──────────────────────────────────────────────────────────────────────────
切塊/嵌入/同步        全託管,不用自己寫、自己排程          你需要非常客製的切塊策略
向量庫維護            KB 幫你管索引 lifecycle              你要多租戶 / 特殊索引結構
上手速度             幾天內上線                          你已有成熟的 RAG pipeline
控制權               中等(切塊策略有限選項)              完全掌握每一步
```

**翻盤條件**:當你需要 (1) 語意切塊 / 版面感知切塊等 KB 不支援的策略、(2) 檢索後自訂 rerank / 多階段檢索、(3) 跨多個異質資料源做複雜 join——這時自建管線(可搭 Lambda + 開源套件)才划算。但對 8 成場景,KB 的預設就夠好。

### 5.2 向量庫:OpenSearch Serverless vs Aurora pgvector vs Pinecone

```
選擇                    優勢                          代價 / 翻盤條件
──────────────────────────────────────────────────────────────────────
OpenSearch Serverless   Bedrock KB 原生支援,免管節點     最低 OCU 有固定成本(見成本節)
Aurora pgvector         已有 Postgres,省一套系統          需自己管實例、擴縮
Pinecone(第三方)      向量檢索體驗最佳                  資料出 AWS 帳號,法遵可能不允許
```

**翻盤條件**:資料量小、已經在用 Aurora、且流量低到不想付 OpenSearch 的最低月費 → 選 Aurora pgvector(Bedrock KB 也支援)。資料主權沒問題、追求極致檢索體驗 → 才考慮 Pinecone。

### 5.3 生成模型:Claude vs Titan vs Llama(都在 Bedrock 上)

- **Claude(Anthropic)**:遵循指令、拒絕幻覺、引用邏輯最穩,是 RAG 生成的預設首選。
- **Titan Text**:AWS 自家,便宜,適合簡單摘要,複雜推理稍弱。
- **Llama(Meta)**:開源權重、可自行微調,若你要 fine-tune 或有特殊授權需求時考慮。

RAG 的瓶頸通常不在生成而在檢索品質,所以生成模型先用 Claude 求穩,之後再依成本壓力往下調。

### 5.4 `RetrieveAndGenerate` vs `Retrieve` + 自己 `InvokeModel`

- **一次搞定的 `RetrieveAndGenerate`**:少寫程式碼、少一次網路往返、引用格式 Bedrock 幫你處理好。
- **拆開的 `Retrieve` + `InvokeModel`**:你能在中間插入 rerank、過濾、改寫 prompt、加 few-shot、做 guardrail 檢查——控制權大很多。

先用合體版上線,等你要優化檢索品質或 prompt 時,再拆開。

### 5.5 為什麼用 CDK 而不是手刻 CloudFormation YAML

```
選擇            CDK(TypeScript)                手刻 CloudFormation YAML
─────────────────────────────────────────────────────────────────────
抽象化          用迴圈/函式/型別產生資源            純宣告,重複的東西要複製貼上
IAM 權限        grantRead() 一行搞定最小權限        自己拼 policy JSON,易錯
重用            Construct 可跨專案打包重用           巢狀 stack,體驗較差
型別檢查        編譯期就抓到打錯的屬性               部署到一半才報錯
```

CDK 產出的仍然是 CloudFormation(可用 `cdk synth` 檢視),等於你拿到「有型別、能寫邏輯」的 CloudFormation。對於 IAM 權限特別多的 AI 系統,`grant*()` 這類方法自動產生最小權限 policy,省下大量手拼 JSON 的錯誤。

---

## 六、成本估算

Serverless 的美好是「零流量近乎零成本」,但 RAG 有一個容易被忽略的**固定成本**:向量庫。

以「每月 10 萬次問答、文件庫 5 GB」估算(us-east-1 概略單價,實際以帳單為準):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| OpenSearch Serverless | 最低 2 OCU(檢索)+ 索引,約 $0.24/OCU·hr | **~$350**(固定成本大戶) |
| Bedrock 嵌入(Titan v2) | 首次 5 GB ≈ 數百萬 token,增量少 | ~$5 一次性 + 少量 |
| Bedrock 生成(Claude) | 10 萬次 × 平均 2K in / 400 out token | ~$60–200(視模型等級) |
| Lambda | 10 萬次呼叫、每次 <1s | < $1 |
| API Gateway | 10 萬次請求 | ~$0.35 |
| S3 儲存 | 5 GB | ~$0.12 |
| **合計** | | **~$420–560 / 月** |

**成本洞察**:這套系統的成本結構是「一大塊固定 + 一小塊變動」。固定成本幾乎全來自 OpenSearch Serverless 的最低 OCU。這帶來一個重要的架構結論——

- **流量很低(< 1 萬次/月)時**:OpenSearch 的固定月費會讓「每次問答的均攤成本」高得離譜。此時改用 **Aurora Serverless v2 + pgvector**(可縮到很低)或甚至把向量存進 DynamoDB 自己算相似度,反而划算。
- **流量中高時**:固定成本被攤平,OpenSearch Serverless 的免維運優勢就贏了。

這正是第五節「向量庫翻盤條件」的成本版註解。

---

## 七、延伸與常見的坑

**上線後你一定會遇到的優化題:**

- **檢索品質不夠好**:答案答非所問,通常是切塊策略問題。改用語意切塊、加大 overlap、或引入 **hybrid search**(向量 + 關鍵字混合)。這時就是把 `RetrieveAndGenerate` 拆成 `Retrieve` + 自訂 rerank 的時機。
- **幻覺仍然出現**:在 prompt 裡強制「只能根據提供的片段回答,找不到就說不知道」,並掛上 **Bedrock Guardrails**(Part 4 會深入)過濾幻覺與敏感內容。
- **權限過濾**:客戶不該看到內部文件。在 ingestion 時給每個 chunk 打 metadata(如 `visibility: public`),檢索時用 metadata filter 限制範圍。
- **評估沒有基準**:你怎麼知道改了切塊策略是變好還變壞?建立一組「問題 → 標準答案」的評測集,用 LLM-as-judge 打分,每次改動都跑一遍。這是把 RAG 從「感覺不錯」推進到「可量化改善」的關鍵。
- **多輪對話的 session 成本**:`sessionId` 會讓 Bedrock 帶入歷史,token 用量隨對話增長,記得設對話長度上限。

**最容易踩的三個坑:**

1. **忘了 aoss data access policy**:IAM 對了、KB 還是連不進向量庫——因為 OpenSearch Serverless 有獨立的一套資料存取權限。
2. **模型要先在 Bedrock console 開啟存取**:Bedrock 的 foundation model 預設是「未啟用」,要先在 Model access 頁面申請開通,CDK 才 invoke 得到。
3. **ingestion job 不會自動跑**:上傳文件到 S3 後,除非設定自動同步,否則要手動 `start-ingestion-job`,不然向量庫是空的。

---

## 小結

RAG 是所有 AI 系統的起點,也是最能展現「AWS 原生」威力的地方:**你把整個 RAG 裡最麻煩的檢索基礎設施,外包給 Bedrock Knowledge Bases + OpenSearch Serverless,自己只寫幾十行 Lambda 與 CDK**。沒有 GPU、沒有模型 host、資料留在自己帳號、隨用量計費。

下一篇,我們處理另一個超高頻的 AI 系統:**當「知識」不是乾淨的 Markdown,而是幾百萬張掃描的 PDF、發票、合約**時,怎麼用 Textract + Comprehend + Bedrock + Step Functions 蓋一條智慧文件處理(IDP)管線。

---

## 系列導覽

- **Part 1(本篇)**:Serverless RAG 智慧客服知識庫
- **Part 2**:智慧文件處理(IDP)管線 —— Textract + Comprehend + Bedrock + Step Functions
- **Part 3**:即時個人化推薦系統 —— Kinesis + Feature Store + SageMaker Endpoint
- **Part 4**:自主 AI Agent 工具呼叫系統 —— Bedrock Agents + Lambda Action Groups + Guardrails
- **Part 5**:生產化 MLOps 與可觀測性 —— 部署策略、模型日誌、成本治理、CDK CI/CD
