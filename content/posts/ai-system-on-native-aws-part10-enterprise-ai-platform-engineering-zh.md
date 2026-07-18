---
title: "AI System on Native AWS - Part 10 - 企業 AI 平台工程"
date: 2026-07-27T09:00:00+08:00
draft: false
description: "系列終章。當一個企業有幾十個團隊、上百個 AI 專案時,讓每個團隊各自接 Bedrock、各自寫 CDK、各自處理合規,是災難。平台團隊要把前九篇的能力打包成『內部產品』:多帳號落地區(Control Tower)、統一的 LLM Gateway(集中路由/限流/快取/日誌/分帳)、Service Catalog 與可重用 CDK Construct 黃金路徑、FinOps 分帳、平台級可觀測性。全部用 CDK(CloudFormation)描述,並以一張橫跨 Part 1–10 的總表收束整個系列。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Platform Engineering", "LLM Gateway", "FinOps", "Control Tower", "Service Catalog", "Enterprise", "AI Engineering"]
authors: ["yen"]
readTime: "28 min"
---

> 一個團隊接 Bedrock,叫專案。五十個團隊各自接 Bedrock,叫混亂:每個團隊重新踩一次合規的坑、各自把 API key 寫死在 Lambda、成本一整包分不清誰花的、某個團隊的失控迴圈把整個帳號的 Bedrock 配額吃光、資安團隊要追五十套不同的架構。
> 企業 AI 的最終形態,不是「更強的模型」,而是「平台」:把前九篇的能力——多租戶、模型治理、合規、可觀測——打包成內部團隊可以「自助點用」的產品。讓應用團隊專注寫業務邏輯,把落地區、閘道、護欄、分帳這些重複的重活,一次做對、所有人共享。
> 這是平台工程(Platform Engineering)套在 AI 上:黃金路徑(golden path)讓做對的事變得最容易,集中閘道讓治理有單一施力點,自助讓平台團隊不變成瓶頸。
> 這是 Part 10,整個系列的終章:把十篇累積的一切,收束成一個企業能長期運營的 AI 平台。

---

## 一、情境與痛點:從「幾個專案」到「幾十個團隊」

前九篇每一篇都在教「怎麼蓋一個好的 AI 系統」。但當你的公司從「一個 AI 專案」長成「五十個團隊都想用 AI」時,一個新的、組織層級的問題浮現:

```
沒有平台時,每個團隊各自為政的後果
──────────────────────────────────────────────────────────────
合規          每個團隊重踩 Part 9 的坑,資安追五十套架構追到死
成本          Bedrock 帳單一整包,不知道哪個團隊、哪個專案花的
配額          一個團隊的失控 agent 迴圈吃光全帳號 Bedrock TPM,全公司癱瘓
一致性        A 團隊用 Claude、B 團隊 hardcode 舊模型、C 團隊沒接 Guardrails
重複造輪      每個團隊重寫一次向量庫、重寫一次授權、重寫一次可觀測性
安全          API key 散落各處,某個 repo 一外洩全公司曝險
```

平台工程的答案:**把重複的、需要做對的重活,抽成一個中央平台;讓應用團隊透過「自助」與「黃金路徑」消費它**。平台團隊的產品不是某個 AI 應用,而是「讓別人安全、快速、可控地蓋 AI 應用的能力」。

核心心法三條:
- **黃金路徑(Golden Path)**:讓「做對的事」成為阻力最小的路。團隊照著鋪好的路走,合規、可觀測、成本標籤自動就位。
- **集中施力點(Single Point of Control)**:所有 LLM 呼叫走同一個閘道,治理(限流、日誌、快取、分帳)只需在一處施行。
- **自助不設限(Self-service)**:平台團隊提供能力,不當審批瓶頸——否則平台自己變成塞車點。

---

## 二、系統目的:平台的產品需求

平台的「使用者」是**內部的應用團隊**。它的需求以「開發者體驗 + 治理」雙軸衡量:

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 自助 | 團隊幾分鐘內取得合規的 AI 環境 | 平台不能是瓶頸 |
| 一致治理 | 所有專案自動套用護欄、加密、稽核 | Part 9 的控制不靠自律 |
| 成本可歸因 | 每個團隊/專案的花費清清楚楚 | FinOps 與分帳的前提 |
| 配額公平 | 單一團隊無法拖垮全體 | 噪音鄰居(組織版) |
| 黃金路徑 | 常見場景(RAG/Agent)有現成範本 | 不重複造輪 |
| 集中可觀測 | 平台級看板:用量、成本、品質、事故 | 平台自己要被管理 |

注意這張表跟前面所有篇都不同:**它的需求不是關於某個 AI 功能,而是關於「如何讓一個組織可持續地大規模用 AI」**。這是從「系統設計」升維到「平台設計」。

---

## 三、系統設計與架構

### 3.1 三個支柱

```
┌─────────────────────────────────────────────────────────────────┐
│                        企業 AI 平台                                │
│                                                                   │
│  ① 落地區(Landing Zone)        ② LLM Gateway         ③ 黃金路徑    │
│  ───────────────────────    ─────────────────    ──────────────  │
│  Control Tower 多帳號         集中的 Bedrock 代理     Service Catalog│
│  帳號工廠 + SCP 護欄           路由/限流/快取/日誌/     + 可重用 CDK    │
│  (Part 9 的合規基線)          分帳的單一入口          Construct 庫    │
│                                                                   │
│         每個團隊拿到一個「已經合規的帳號」+「一個閘道端點」            │
│         + 「幾個 cdk 一行就生出 RAG/Agent 的 construct」            │
└─────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌──────────────┐        ┌──────────────┐         ┌──────────────┐
│  團隊 A 帳號    │        │  團隊 B 帳號    │         │  團隊 C 帳號    │
│ (RAG 客服)     │        │ (IDP 管線)     │         │ (推薦系統)     │
│ 自動繼承護欄    │        │ 自動繼承護欄    │         │ 自動繼承護欄    │
└──────┬───────┘        └──────┬───────┘         └──────┬───────┘
       └────────────────────────┼─────────────────────────┘
                                 ▼  所有 LLM 呼叫都走這裡
                       ┌────────────────────┐
                       │    LLM Gateway       │──▶ CloudWatch(用量/成本/品質看板)
                       │ (共享服務帳號)         │──▶ 分帳(每團隊 token)
                       └────────────────────┘
```

### 3.2 支柱一:多帳號落地區

**為什麼多帳號**:單帳號塞所有團隊 = 爆炸半徑最大、配額互搶、成本混一鍋、權限難隔離。**AWS Control Tower** 提供「帳號工廠」——每個團隊/專案一個帳號,新帳號一出生就自動套用組織的 SCP 護欄(Part 9)、日誌集中化、合規基線。團隊拿到的是一個**「已經合規」的沙盒**,而不是一張白紙。

### 3.3 支柱二:LLM Gateway(整個平台的核心)

這是平台最有價值的單一元件。**所有團隊不直接呼叫 Bedrock,而是呼叫平台的 LLM Gateway**。這個集中代理讓治理有了單一施力點:

```
團隊應用 ──▶ LLM Gateway ──▶ Bedrock
                │
                ├─ 認證與授權(哪個團隊、哪個專案)
                ├─ 路由(依用途/成本選模型;主模型掛了切備援)
                ├─ 限流與配額(每團隊 TPM/RPM,防噪音鄰居)
                ├─ 語意快取(跨團隊共享常見查詢,省成本)
                ├─ Guardrails(集中掛,不靠各團隊自覺)
                ├─ 用量計量(每次呼叫的 token → 分帳)
                └─ 集中日誌(Part 5/9 的稽核,一處全收)
```

一個閘道,把 Part 4 的護欄、Part 5 的可觀測與成本、Part 6 的配額、Part 9 的稽核,全部**收斂到一個必經之路**。改一次,全公司受惠;治理一處,處處生效。

### 3.4 支柱三:黃金路徑(Service Catalog + Construct 庫)

平台把前九篇的系統做成**參數化的可重用資產**:

- **Service Catalog 產品**:團隊在自助入口點「RAG 客服」「文件處理管線」,填幾個參數,平台用預先驗證的 CloudFormation 幫他生出一整套合規的系統。
- **可重用 CDK Construct 庫**:給有工程能力的團隊,一個 `new RagChatbot(this, ...)` 就內含 Part 1 的檢索 + Part 6 的多租戶隔離 + Part 9 的加密 + Part 5 的可觀測——**把「做對」封裝進 construct,團隊想做錯都難**。

---

## 四、CDK(CloudFormation)實作

### 4.1 LLM Gateway:集中代理

Gateway 部署在共享服務帳號,用 API Gateway + Lambda(或 Fargate)實作,是所有 LLM 流量的必經點。

```typescript
// lib/llm-gateway.ts 片段
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as lambdaNode from 'aws-cdk-lib/aws-lambda-nodejs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Duration } from 'aws-cdk-lib';

// 每團隊配額與計量表
const usageTable = new dynamodb.Table(this, 'GatewayUsage', {
  partitionKey: { name: 'teamId', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'window', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
});

const gatewayFn = new lambdaNode.NodejsFunction(this, 'GatewayFn', {
  entry: 'lib/lambda/gateway/index.ts',
  timeout: Duration.seconds(60),
  memorySize: 1024,
  environment: { USAGE_TABLE: usageTable.tableName, CACHE_ENDPOINT: cache.endpoint },
});

const api = new apigw.RestApi(this, 'LlmGateway', { /* mTLS / private */ });
// 每團隊一把 key + usage plan(組織級限流,防單一團隊吃光配額)
const plan = api.addUsagePlan('PerTeam', {
  throttle: { rateLimit: 100, burstLimit: 200 },
});
api.root.addResource('invoke').addMethod('POST', new apigw.LambdaIntegration(gatewayFn), {
  apiKeyRequired: true,
});
```

Gateway Lambda 的核心邏輯:認證 → 配額 → 快取 → 路由 → 呼叫 → 計量 → 日誌。

```typescript
// lib/lambda/gateway/index.ts 片段
export const handler = async (event: any) => {
  const teamId = authenticate(event);                 // 由 key/JWT 解出團隊
  const { prompt, purpose } = JSON.parse(event.body);

  // 1) 配額檢查(組織級防噪音鄰居)
  if (await overQuota(teamId)) return resp(429, { error: 'team quota exceeded' });

  // 2) 語意快取(跨團隊共享常見查詢,但注意資料邊界)
  const cached = await semanticCache.get(teamId, prompt);
  if (cached) { await meter(teamId, 0, 'cache_hit'); return resp(200, cached); }

  // 3) 路由:依用途/成本選模型;主模型 throttle 就切備援(跨區/降級)
  const model = route(purpose);                       // e.g. 'complex'→Claude Opus, 'cheap'→Haiku
  const out = await invokeWithFallback(model, prompt);// 內含 Guardrails + 重試 + 備援

  // 4) 計量與分帳(每次 token → usageTable,供 FinOps)
  await meter(teamId, out.usage.totalTokens, model.id);
  // 5) 集中稽核日誌(Part 9)
  await auditLog(teamId, purpose, model.id, out.usage);

  await semanticCache.set(teamId, prompt, out);
  return resp(200, out);
};
```

> Gateway 是平台的「收費站 + 護欄 + 保險絲」三合一。它讓 Part 4(護欄)、Part 5(成本/可觀測)、Part 6(配額)、Part 9(稽核)從「每個團隊各自做」變成「平台做一次」。這是整個平台投報率最高的單一投資。

### 4.2 黃金路徑:把整套系統封裝成一個 Construct

```typescript
// lib/constructs/rag-chatbot.ts —— 平台提供給團隊的黃金路徑
import { Construct } from 'constructs';

export interface RagChatbotProps {
  teamId: string;
  tenants: 'single' | 'multi';       // 要不要 Part 6 的多租戶隔離
  dataClassification: 'public' | 'confidential' | 'regulated';
}

export class RagChatbot extends Construct {
  constructor(scope: Construct, id: string, props: RagChatbotProps) {
    super(scope, id);

    // 自動套用:加密(Part 9)、可觀測(Part 5)、多租戶授權(Part 6)、走 Gateway
    const key = platformKmsKey(this, props.dataClassification);
    const kb = new KnowledgeBase(this, 'KB', { encryptionKey: key /* ... */ });
    if (props.tenants === 'multi') applyTenantIsolation(this, kb);
    if (props.dataClassification === 'regulated') applyPrivateLinkAndSCPChecks(this);
    wireObservability(this, props.teamId);           // 自動接平台看板
    routeThroughGateway(this, props.teamId);          // 不直連 Bedrock,強制走閘道
  }
}

// 團隊端只要:
// new RagChatbot(this, 'Support', { teamId: 'cs', tenants: 'multi', dataClassification: 'regulated' });
// 一行,就內含前九篇所有的最佳實踐。
```

**這就是黃金路徑的威力**:團隊寫一行,平台把 Part 1、5、6、9 的正確做法全部注入。「做對」變成阻力最小的選項,「做錯」反而要繞過平台、更費力。

### 4.3 FinOps:分帳與成本看板

Gateway 的計量資料 + Part 5 的 cost allocation tag,合起來產出每團隊、每專案、每模型的成本歸因。

```typescript
// lib/finops.ts 片段:把 Gateway 用量匯總成分帳報表 + 預算告警
import * as budgets from 'aws-cdk-lib/aws-budgets';

// 每團隊一個預算,超過門檻自動告警(甚至觸發 Gateway 降級該團隊到便宜模型)
new budgets.CfnBudget(this, 'TeamCsBudget', {
  budget: {
    budgetName: 'team-cs-ai',
    budgetType: 'COST',
    timeUnit: 'MONTHLY',
    budgetLimit: { amount: 3000, unit: 'USD' },
    costFilters: { TagKeyValue: ['user:team$cs'] },
  },
  notificationsWithSubscribers: [{
    notification: { notificationType: 'ACTUAL', comparisonOperator: 'GREATER_THAN',
                    threshold: 80, thresholdType: 'PERCENTAGE' },
    subscribers: [{ subscriptionType: 'SNS', address: finopsTopic.topicArn }],
  }],
});
```

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 集中 LLM Gateway vs 各團隊直連 Bedrock

```
選擇            LLM Gateway(集中)              各團隊直連 Bedrock
──────────────────────────────────────────────────────────────
治理施力點       單一,改一次全公司生效            分散,治理靠每團隊自律
成本歸因         天然按團隊計量                   要靠 tag,易漏
配額             組織級公平分配                   共搶帳號配額,噪音鄰居
快取             跨團隊共享,省最多                各自快取或不快取
延遲             多一跳(可忽略,~數 ms)          少一跳
單點風險         Gateway 掛 = 全公司受影響         無單點
```

**翻盤條件**:公司只有一兩個 AI 團隊、還沒有治理與分帳的痛 → 直連 Bedrock 更簡單,別過早平台化。**平台化是規模的產物**——團隊數過了某個門檻(通常 5–10 個),Gateway 的治理收益才超過它的複雜度與單點風險(單點用多區 + 直連 fallback 緩解)。

### 5.2 Service Catalog(低程式碼) vs CDK Construct 庫(程式碼) vs 兩者

- **Service Catalog**:給非工程或想要極簡自助的團隊,點選填參數即得。
- **CDK Construct 庫**:給有工程能力、要客製的團隊,`import` 進自己的 CDK app。
- **正解**:兩者都給。同一套底層最佳實踐,包裝成兩種消費介面,覆蓋不同成熟度的團隊。

### 5.3 平台團隊 vs 讓每個團隊自理

**翻盤條件**:平台團隊本身是成本,小公司養不起也不需要。判斷點是「**重複的痛 × 團隊數**」——當「每個團隊都在重踩合規坑、重寫可觀測、成本分不清」的痛乘以團隊數,超過養一個平台團隊的成本時,平台化才划算。別為了「架構漂亮」而在三個團隊時就蓋平台。

### 5.4 買(第三方 LLM Gateway/LLMOps) vs 自建

市面上有現成的 LLM Gateway 與 LLMOps 平台。自建的理由:與 AWS 原生服務(IAM、Bedrock、CloudWatch、Organizations)深度整合、資料不出自己帳號、完全客製治理邏輯。買的理由:更快、功能開箱即用。**與本系列一致的原則**:能用原生服務組出、且治理與資料主權是核心需求時,自建划算;純想快速起步、治理需求標準,買現成的省事。

---

## 六、成本與價值

平台本身的營運成本(概略,不含各團隊的業務系統):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| LLM Gateway(API GW + Lambda/Fargate) | 全公司流量匯聚 | ~$500–2,000 |
| 共享語意快取(ElastiCache) | 跨團隊共享 | ~$300–800 |
| 集中日誌/看板(CloudWatch/OpenSearch) | 全公司 | ~$500–1,500 |
| Control Tower / Config / 稽核 | 組織級 | ~$300–1,000 |
| **平台營運成本** | | **~$1,600–5,300 / 月** |

**成本洞察**:平台的成本要看**它替全公司省下與避免的**,而非絕對值:

- **跨團隊共享快取**:一個團隊快取的常見查詢,別的團隊也命中,省下的 LLM 費用隨團隊數放大——這是集中化獨有的紅利。
- **避免重複建設**:五十個團隊不用各自重蓋向量庫、可觀測、合規,省下的是幾十個人月的工程時間。
- **成本可見即成本可控**:FinOps 分帳讓浪費無所遁形,通常光是「讓每個團隊看到自己的帳單」就能砍掉可觀的無謂用量。
- **配額防護避免災難性帳單**:一個失控 agent 迴圈在沒有 Gateway 限流時能燒出天文數字帳單;Gateway 的配額就是保險絲。

平台不是成本中心,是**讓「全公司大規模用 AI」這件事在財務與治理上可持續的前提**。

---

## 七、系列總結:十篇,一條從系統到平台的路

十篇走完,我們從「蓋一個 AI 系統」一路走到「運營一個 AI 平台」。用一張總表收束整個系列:

```
        主題                  核心 AWS 服務                  關鍵心法
────────────────────────────────────────────────────────────────────────────
【基礎篇:蓋一個能跑的系統】
P1 RAG   知識問答              Bedrock KB + OpenSearch        檢索+生成,managed RAG
P2 IDP   髒文件結構化          Textract + Step Functions      事件驅動+狀態機+人工回路
P3 推薦  即時個人化            Kinesis + Feature Store + SM   串流+特徵一致性+召回排序
P4 Agent 自主行動             Bedrock Agents + Guardrails    ReAct+工具+護欄+最小權限
P5 MLOps 生產化               CloudWatch + CDK Pipelines     可觀測+部署+成本+CI/CD
────────────────────────────────────────────────────────────────────────────
【進階篇:讓系統成為企業平台】
P6 多租戶 賣給一百家公司        Verified Permissions + KB      授權先於檢索+隔離+歸因
P7 模型治理 客製與可稽核        Bedrock 客製 + Model Registry  RAG優先+評估關卡+回歸防護
P8 風控  即時對抗性決策         Kinesis+Flink+Neptune          重運算非同步+規則ML圖混合
P9 合規  受管制資料上線         PrivateLink+KMS+SCP+Macie      合規是門票+預防勝偵測
P10 平台 讓組織可持續用 AI      Gateway+Control Tower+Catalog  集中施力+黃金路徑+自助
────────────────────────────────────────────────────────────────────────────
```

如果整個系列只留三句話:

1. **能外包給 managed service 的,就別自己 host。** 從 Part 1 到 Part 10,我們沒有自己 host 過一個模型、自建過一個向量庫叢集、手刻過一個 ReAct 迴圈。工程力氣要花在「把服務接成解決業務問題的系統」,而非維護基礎設施。這對一個團隊如此,對一個平台更是如此。

2. **需求決定形狀。** 系統的延遲、吞吐、合規、規模需求,決定它的架構母題與成本形狀——RAG 的固定成本、IDP 的變動成本、推薦與風控的常駐成本、合規的控制稅、平台的共享紅利。先問需求,再選架構,永遠不要反過來。

3. **治理與平台不是上線後才補的,是設計的一部分。** 可觀測性、安全、合規、成本歸因、多租戶隔離、模型治理——這些「非功能」的東西,是「能跑的 demo」跟「一個組織能長期、安全、可控地大規模運營的 AI」之間的全部距離。而它們最終都收斂到同一個實作原則:**code 進 stack,由 CDK 描述、由護欄強制、可版本控制、可稽核、可重建。**

從第一篇的一個 Lambda,到最後一篇的一整個平台,貫穿始終的是同一種語言:**CDK(CloudFormation)**。每一個系統、每一條權限、每一個護欄、每一個成本標籤、每一個稽核控制,都是可版本控制、可 review、可一鍵重建的程式碼。這,就是「AI System on Native AWS」十篇的全貌——從一個系統,到一個平台。

謝謝你讀完這十篇。願你的組織用 AI,用得又快、又穩、又安全。

---

## 系列導覽

**基礎篇**
- Part 1:Serverless RAG 智慧客服知識庫
- Part 2:智慧文件處理(IDP)管線
- Part 3:即時個人化推薦系統
- Part 4:自主 AI Agent 工具呼叫系統
- Part 5:生產化 MLOps 與可觀測性

**進階篇**
- Part 6:企業級多租戶 RAG 平台
- Part 7:基礎模型客製化與模型治理
- Part 8:即時串流 ML 與詐欺偵測
- Part 9:企業 AI 安全、合規與資料治理
- **Part 10(本篇)**:企業 AI 平台工程 —— 落地區、LLM Gateway 與 FinOps
