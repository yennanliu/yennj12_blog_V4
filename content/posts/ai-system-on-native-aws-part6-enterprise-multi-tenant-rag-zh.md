---
title: "AI System on Native AWS - Part 6 - 企業級多租戶 RAG 平台"
date: 2026-07-23T09:00:00+08:00
draft: false
description: "系列進入企業篇。Part 1 的單租戶 RAG 一上到企業就崩:租戶之間的資料絕不能互看、每個使用者只能看到有權限的文件、成本要能拆到每個租戶頭上、還要能撐住幾百個租戶。本篇用純 AWS 原生服務打造多租戶 RAG 平台:租戶隔離的三種模型(silo/pool/bridge)、以 Verified Permissions(Cedar)做文件級授權、metadata filtering、hybrid search + reranking、語意快取降本、以及每租戶成本歸因,全部用 CDK(CloudFormation)描述。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Bedrock", "RAG", "Multi-tenancy", "Verified Permissions", "OpenSearch Serverless", "Enterprise", "AI Engineering"]
authors: ["yen"]
readTime: "27 min"
---

> 大部分 RAG 的 demo 只有一個租戶、一個使用者、一批文件,跑起來很漂亮。一放到企業就爆:A 公司的合約絕不能被 B 公司檢索到、行銷部的人不該問得出財務部的薪資表、而且老闆要知道這個月每個客戶到底燒了你多少 token。
> 單租戶 RAG 是玩具,多租戶 RAG 才是產品。難點不在「檢索」,而在「檢索之前,先確定這個人有權看到哪些東西」——而且要在毫秒級、要能撐幾百個租戶、還要能把成本拆得清清楚楚。
> AWS 原生的解法:用 Verified Permissions(Cedar 政策引擎)在檢索前算出可見範圍、用 metadata filtering 把範圍壓進向量檢索、用語意快取把重複問題的成本歸零、用 tenant tag 把每一塊錢歸因到租戶。
> 這是進階篇的起點,也是 Part 1 的企業級進化:當 RAG 要賣給一百家公司時,系統長什麼樣。

---

## 關於進階篇(Part 6–10)

前五篇(Part 1–5)我們各自蓋了一個能跑的 AI 系統。但「能跑」跟「賣得出去、扛得住稽核、管得動成本」之間,還隔著一整套**企業級**的考量:多租戶隔離、模型客製與治理、即時風控、資安合規、平台化。進階篇這五篇,把前面的系統往「企業平台」推進:

- **Part 6(本篇)**:企業級多租戶 RAG 平台 —— 租戶隔離 + 文件級授權 + 語意快取
- **Part 7**:基礎模型客製化與模型治理 —— Fine-tuning、蒸餾、Model Registry、評估關卡
- **Part 8**:即時串流 ML 與詐欺偵測 —— Kinesis + Managed Flink + Neptune 圖偵測
- **Part 9**:企業 AI 安全、合規與資料治理 —— PrivateLink、KMS、Macie、Lake Formation、SCP
- **Part 10**:企業 AI 平台工程 —— 多帳號落地區、LLM Gateway、Service Catalog、FinOps

一樣全程用 **AWS CDK(TypeScript / CloudFormation)** 描述。

---

## 一、情境與痛點:單租戶到多租戶的斷崖

你把 Part 1 的 RAG 客服做成功了,現在要把它變成一個 **SaaS 產品**賣給一百家企業客戶。同一天你會撞上三面牆:

- **隔離牆**:A 公司上傳的合約,B 公司**絕對不能**在檢索結果裡看到哪怕一個片段。這不是準確度問題,是資安事故——一次跨租戶洩漏就足以讓整個產品出局。
- **授權牆**:就算在同一個租戶內,行銷部的員工不該檢索到 HR 的薪資檔、外包廠商只能看到公開文件。權限是**文件級、甚至片段級**的。
- **成本牆**:向量庫與 LLM 的帳單是一整包,但你要按租戶收費、要知道哪個大客戶在虧錢。成本必須**歸因到租戶**。

這三面牆,單租戶 RAG 一個都沒解。而且它們必須在**檢索發生之前**就處理好——你不能先檢索出所有片段、再事後過濾(那等於資料已經離開了它該待的邊界,而且浪費檢索成本)。

核心心法:**多租戶 RAG 的難點是「授權」而不是「檢索」。檢索是 Part 1 就解掉的;企業級要解的是「這個 principal,在這個 tenant 裡,對哪些資源有 read 權限」——並把答案變成向量檢索的過濾條件。**

---

## 二、系統目的:功能與非功能需求

**功能需求:**

- 多租戶:一套平台服務 N 個租戶,租戶間資料完全隔離。
- 文件級 / 片段級授權:依 principal 的角色、部門、屬性決定可見文件。
- 檢索前過濾:授權範圍在向量檢索階段就生效,不做事後過濾。
- 語意快取:語意相近的問題命中快取,不重複打 LLM。
- 每租戶成本歸因與用量配額(quota / rate limit)。

**非功能需求:**

| 面向 | 目標 | 為什麼 |
|------|------|--------|
| 隔離 | 跨租戶洩漏機率為零 | 一次洩漏 = 產品出局 |
| 授權延遲 | 授權判斷 < 10ms | 卡在檢索前的關鍵路徑上 |
| 規模 | 支援 500+ 租戶 | SaaS 要長大 |
| 成本歸因 | 每租戶 token/檢索成本可拆 | 定價與 FinOps 的前提 |
| 噪音鄰居 | 大租戶不拖垮小租戶 | 公平性與 SLA |

「授權判斷 < 10ms」+「檢索前過濾」這兩條,直接排除了「查一個關聯式權限表再 join」的作法,把我們推向 **Verified Permissions(Cedar)這種專用政策引擎 + 向量庫 metadata filtering** 的組合。

---

## 三、系統設計與架構

### 3.1 先選租戶隔離模型:Silo / Pool / Bridge

這是多租戶系統的第一個、也是最重要的決策。SaaS 領域的三種經典模型套在向量庫上:

```
模型      向量庫配置                       隔離強度    成本效率    適用
──────────────────────────────────────────────────────────────────────
Silo     每租戶一個獨立 collection/index    最強        最差       高合規/大客戶
Pool     所有租戶共用 index,靠 tenantId    最弱        最好       海量小租戶
         欄位過濾
Bridge   分層:大客戶 silo、長尾 pool        折衷        折衷       混合客群(推薦)
```

- **Silo(倉儲式)**:每個租戶一套自己的向量索引。物理隔離最強、噪音鄰居問題天然消失,但幾百個租戶就是幾百套索引,OpenSearch 的固定成本乘以租戶數,長尾小租戶會把你拖垮。
- **Pool(共池式)**:所有租戶的向量塞進同一個索引,每筆向量帶 `tenantId` metadata,檢索時強制加 `tenantId = X` 的過濾。成本最優、擴縮最容易,但隔離全靠「過濾條件不能寫錯」——一個 bug 就是跨租戶洩漏。
- **Bridge(橋接式)**:大客戶 / 高合規客戶走 silo,長尾小客戶走 pool。**這是多數 B2B SaaS 的務實選擇**,也是本篇的主線。

### 3.2 整體架構

```
┌──────────┐  JWT(含 tenantId + 角色/部門屬性)   ┌──────────────┐
│  使用者    │ ──────────────────────────────────▶ │ API Gateway   │
└──────────┘                                      └──────┬───────┘
      ▲                                                  ▼
      │ 答案 + 引用(僅限可見範圍)             ┌────────────────────────┐
      │                                      │   Lambda(Orchestrator)  │
      │                                      └──┬────────┬────────┬────┘
      │                     ①授權(<10ms)         │        │檢索前  │
      │                     ▼                    │        ▼        │
      │            ┌──────────────────┐          │  ┌──────────────┐│
      │            │ Verified          │          │  │ 語意快取       ││ ②快取命中?
      │            │ Permissions(Cedar)│──────────┘  │(ElastiCache)  ││    命中→直接回
      │            │ 回傳可見 doc 標籤   │             └──────┬───────┘│
      │            └──────────────────┘                    未命中      │
      │                                                     ▼          │
      │                                          ┌────────────────────┐│
      │                                          │ Bedrock KB / OpenSearch│
      │                                          │ 帶 tenantId + 可見標籤  ││③帶過濾檢索
      │                                          │ 的 metadata filter    ││
      │                                          └──────────┬───────────┘│
      │                                                     ▼            │
      │                                          ┌────────────────────┐  │
      │                                          │ Rerank + Claude 生成 │  │
      └──────────────────────────────────────────│ + 寫回語意快取         │◀─┘
                                                 └────────────────────┘
```

一次請求的四步:**授權 → 查快取 → 帶過濾檢索 → 生成並回填快取**。授權與快取都在「昂貴的檢索/生成」之前,這個順序是省錢與安全的關鍵。

### 3.3 為什麼授權要獨立成一個政策引擎

你當然可以把權限塞進一張 DynamoDB 表,每次查一次。但企業授權規則會長成這樣:「使用者可讀文件,若 (文件.tenant == 使用者.tenant) 且 (文件.department in 使用者.departments 或 文件.visibility == 'public') 且 (使用者.clearance >= 文件.classification)」。用程式碼 if-else 拼這個,很快變成沒人敢改的義大利麵。

**Amazon Verified Permissions** 用 **Cedar** 政策語言把「誰能對什麼做什麼」抽成宣告式政策,與業務程式碼分離、可獨立稽核、毫秒級評估。這正是文件級授權該用的工具。

---

## 四、CDK(CloudFormation)實作

### 4.1 授權:Verified Permissions 政策存放區與政策

```typescript
// lib/authz.ts 片段
import * as vp from 'aws-cdk-lib/aws-verifiedpermissions';

const policyStore = new vp.CfnPolicyStore(this, 'RagPolicyStore', {
  validationSettings: { mode: 'STRICT' },
  schema: {
    cedarJson: JSON.stringify({
      RagApp: {
        entityTypes: {
          User: { shape: { type: 'Record', attributes: {
            tenant: { type: 'String' },
            departments: { type: 'Set', element: { type: 'String' } },
            clearance: { type: 'Long' },
          } } },
          Document: { shape: { type: 'Record', attributes: {
            tenant: { type: 'String' },
            department: { type: 'String' },
            visibility: { type: 'String' },
            classification: { type: 'Long' },
          } } },
        },
        actions: { ReadDocument: { appliesTo: { principalTypes: ['User'], resourceTypes: ['Document'] } } },
      },
    }),
  },
});

// 靜態政策:同租戶 + (同部門 或 public) + 密級足夠 才可讀
new vp.CfnPolicy(this, 'ReadPolicy', {
  policyStoreId: policyStore.attrPolicyStoreId,
  definition: { static: {
    description: 'Tenant-isolated, department + clearance based read',
    statement: `
      permit(principal, action == RagApp::Action::"ReadDocument", resource)
      when {
        principal.tenant == resource.tenant &&
        (resource.visibility == "public" || resource.department in principal.departments) &&
        principal.clearance >= resource.classification
      };`,
  } },
});
```

### 4.2 檢索前:把授權結果變成 metadata filter

關鍵技巧:我們**不**對每份文件逐一問 Verified Permissions(那要問幾千次)。而是先算出 principal 的**可見維度**(tenant、部門集合、密級),把它們直接編譯成向量檢索的 metadata filter。Verified Permissions 用來**驗證政策邏輯與稽核**,線上熱路徑用它推導出的過濾條件。

```typescript
// lib/lambda/query/index.ts 片段
import { BedrockAgentRuntimeClient, RetrieveAndGenerateCommand }
  from '@aws-sdk/client-bedrock-agent-runtime';

const brt = new BedrockAgentRuntimeClient({});

export const handler = async (event: any) => {
  const claims = event.requestContext.authorizer.jwt.claims;
  const tenant = claims['custom:tenant'];
  const departments = String(claims['custom:departments'] ?? '').split(',');
  const clearance = Number(claims['custom:clearance'] ?? 0);

  // 由授權維度組出 metadata filter:租戶隔離 + 部門/公開 + 密級
  const retrievalFilter = {
    andAll: [
      { equals: { key: 'tenant', value: tenant } },              // 硬隔離,永遠存在
      { orAll: [
        { equals: { key: 'visibility', value: 'public' } },
        { in: { key: 'department', value: departments } },
      ] },
      { lessThanOrEquals: { key: 'classification', value: clearance } },
    ],
  };

  const res = await brt.send(new RetrieveAndGenerateCommand({
    input: { text: event.question },
    retrieveAndGenerateConfiguration: {
      type: 'KNOWLEDGE_BASE',
      knowledgeBaseConfiguration: {
        knowledgeBaseId: resolveKbForTenant(tenant),   // Bridge:大租戶回自己的 silo KB
        modelArn: process.env.MODEL_ARN!,
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 8,
            filter: retrievalFilter,                    // ★ 檢索前過濾,不做事後過濾
          },
        },
      },
    },
  }));
  // ...整理引用回傳
};
```

> **隔離的最後一道保險**:`tenant` 過濾條件用 pool 模型時是唯一的隔離屏障。務必在**平台層強制注入**(從驗證過的 JWT claim 取,絕不接受前端傳入),並寫整合測試「A 租戶的 token 永遠檢索不到 B 租戶的資料」當作 CI 的紅線。

### 4.3 Ingestion 時給每個 chunk 打上授權 metadata

授權過濾能生效的前提:**寫入時就把 tenant / department / visibility / classification 打進每個 chunk 的 metadata**。Bedrock KB 支援對 S3 文件附一份 `.metadata.json`。

```typescript
// 上傳文件時,同時寫一份 side-car metadata(供 KB 索引為可過濾欄位)
// s3://bucket/tenantA/hr/salary.pdf
// s3://bucket/tenantA/hr/salary.pdf.metadata.json
const metadata = {
  metadataAttributes: {
    tenant:         { value: { type: 'STRING', stringValue: 'tenantA' }, includeForEmbedding: false },
    department:     { value: { type: 'STRING', stringValue: 'hr' },      includeForEmbedding: false },
    visibility:     { value: { type: 'STRING', stringValue: 'private' }, includeForEmbedding: false },
    classification: { value: { type: 'NUMBER', numberValue: 3 },         includeForEmbedding: false },
  },
};
```

### 4.4 語意快取:重複問題不再打 LLM

企業客服有大量重複問題(「怎麼重設密碼」被問一千次)。**語意快取**把問題向量化,若跟快取裡某個問題夠相近(cosine > 0.95)且**在同一租戶/授權範圍**內,直接回快取答案。

```typescript
// lib/lambda/query/semantic-cache.ts 片段
import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';
// 用 ElastiCache for Redis(啟用向量搜尋)或 MemoryDB 存快取向量

async function tryCache(tenant: string, authzKey: string, question: string, redis: any) {
  const emb = await embed(question);                 // Titan Embeddings
  // 快取 key 一定要含 tenant + 授權維度,否則會跨權限洩漏答案!
  const hits = await redis.call('FT.SEARCH', `cache:${tenant}`,
    `(@authz:{${authzKey}})=>[KNN 1 @vec $q]`, 'PARAMS', 2, 'q', toBytes(emb), 'DIALECT', 2);
  if (hits && similarity(hits) > 0.95) return hits.answer;   // 命中
  return null;
}
```

> **快取的隔離陷阱**:快取 key 必須包含租戶與授權維度。若只用「問題文字」當 key,高權限使用者問過的答案會被低權限使用者的相同問題命中——**快取變成越權管道**。這是多租戶語意快取最陰險的坑。

### 4.5 每租戶成本歸因與配額

用 API Gateway 的 **usage plan + API key(每租戶一把)** 做限流與配額,並在每次 LLM 呼叫後把 token 用量寫進帶 `tenant` 維度的 CloudWatch 自訂指標,供 FinOps 拆帳。

```typescript
import * as apigw from 'aws-cdk-lib/aws-apigateway';

const plan = api.addUsagePlan('TenantPlan', {
  throttle: { rateLimit: 50, burstLimit: 100 },     // 防噪音鄰居
  quota: { limit: 100000, period: apigw.Period.MONTH },
});
// 每個租戶一把 key,綁到 plan;帳單與限流天然按租戶切開
const key = api.addApiKey('TenantA-Key');
plan.addApiKey(key);
```

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 Verified Permissions(Cedar) vs 自建權限表 vs OPA

```
選擇                優勢                              代價 / 翻盤條件
──────────────────────────────────────────────────────────────────────
Verified Perms      宣告式、可稽核、AWS 託管、毫秒級      規則極度動態時政策管理成本上升
自建 DynamoDB 表    簡單直觀                          複雜規則變義大利麵,難稽核
OPA/Rego(自架)    生態強、跨雲                        要自己 host 與維運
```

**翻盤條件**:授權規則極簡(只有 tenant 隔離、沒有部門/密級的複雜組合)時,一個 `tenant` 過濾條件就夠,不需要政策引擎。規則一旦涉及多屬性組合、且需要合規稽核「為什麼這個人能看這份檔」,Verified Permissions 的價值才浮現。

### 5.2 Bridge vs 純 Silo vs 純 Pool(再論)

**翻盤條件**:
- 客戶數少(< 20)、每個都是大合約、合規要求物理隔離 → **純 Silo** 划算,別為了省成本冒隔離風險。
- 海量長尾小租戶(數千個免費/低價戶)、隔離靠應用層即可 → **純 Pool**,把固定成本攤到極致。
- 兩種客群都有 → **Bridge**,用租戶等級決定走哪條路,並在 CDK 用同一組 construct 參數化產生。

### 5.3 事後過濾 vs 檢索前過濾

有人會問:先檢索 Top-50、再用授權過濾出 Top-8 不行嗎?**不行,三個理由**:

- **洩漏風險**:被過濾掉的片段已經進了你的應用記憶體與 LLM context,一個記錄 bug 就外洩。
- **檢索品質**:如果 Top-8 全被過濾掉,你就沒有答案了——授權必須是檢索的一部分,不是之後。
- **成本**:檢索更多、把不該看的也算進去,純浪費。

檢索前過濾(metadata filter)是唯一正確解。

### 5.4 語意快取 vs 精確快取 vs 不快取

- **精確快取**(問題字串完全相同才命中):命中率低,企業問題措辭千變萬化。
- **語意快取**(語意相近即命中):命中率高、省 LLM 成本最多,但要小心「相近但不相同」導致答非所問,設高門檻(0.95+)並保留原引用。
- **不快取**:答案時效性極高(如即時庫存)時反而正確。

---

## 六、成本估算

以「200 租戶、每月 50 萬次問答、其中 30% 命中語意快取」估算(概略):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| OpenSearch Serverless(Pool 共池 + 少數 Silo) | 共池 4 OCU + 5 個大租戶各自 index | **~$1,200**(固定大戶) |
| Bedrock 生成(Claude,扣除快取 30%) | 35 萬次有效呼叫 | ~$700–1,400 |
| 語意快取嵌入 + ElastiCache | 50 萬次嵌入 + Redis 節點 | ~$300 |
| Verified Permissions | 授權評估(推導維度,非逐檔) | ~$50–150 |
| Lambda / API Gateway | 高用量 | ~$300 |
| **合計** | | **~$2,600–3,400 / 月** |

**成本洞察**:多租戶把 Part 1 的「固定成本大戶」問題放大了——**向量庫的固定成本現在要被 200 個租戶分攤**,這正是 Pool 模型省錢的來源(共享固定成本),也是 Silo 模型昂貴的原因(固定成本 × 租戶數)。三個降本槓桿:

- **語意快取直接砍生成成本**:30% 命中 = 30% 的 LLM 費用消失,而且延遲更低。命中率是這套系統最值得優化的單一指標。
- **Bridge 混合隔離**:讓長尾租戶共享固定成本,只有付得起的大客戶才獨享 silo。
- **成本歸因驅動定價**:有了每租戶 token 數據,才能設計「用越多付越多」的定價,把虧錢的大戶轉成賺錢的。

---

## 七、延伸與常見的坑

**延伸方向:**

- **Hybrid search + reranking**:企業文件常有專有名詞、料號,純向量檢索抓不到。加關鍵字(BM25)混合檢索,再用 Cohere Rerank(Bedrock 上)重排前 K,大幅提升企業場景準確度。
- **租戶自助上傳與 ingestion 隔離**:每個租戶一個 S3 prefix + 獨立 ingestion job,避免一個大租戶的重建拖垮全體。
- **Per-tenant 模型選擇**:高階租戶用 Claude Opus、免費租戶用便宜模型,用 SSM 參數依租戶等級路由(呼應 Part 5 的模型解耦)。
- **稽核報表**:用 Verified Permissions 的評估日誌產出「誰在何時存取了哪份文件」,滿足企業合規需求。

**最容易踩的坑:**

1. **tenant 過濾條件漏注入**:任何一條檢索路徑忘了加 tenant filter,就是跨租戶洩漏。要在平台層集中強制,並用 CI 紅線測試守住。
2. **快取 key 不含授權維度**:語意快取變成越權管道,高權限的答案洩漏給低權限使用者。
3. **從前端接收 tenantId**:永遠只從驗證過的 JWT claim 取租戶身分,絕不信任前端傳入的租戶參數。
4. **Silo 無限膨脹**:每個小租戶都給獨立 index,OpenSearch 固定成本爆炸。長尾一定要進 pool。
5. **metadata 沒設 `includeForEmbedding: false`**:授權屬性若被納入 embedding,會污染語意向量、影響檢索品質——它們只該是可過濾欄位,不是語意的一部分。

---

## 小結

多租戶 RAG 把 Part 1 的「檢索問題」升級成「**授權 + 隔離 + 歸因**問題」。企業級的關鍵洞察是:**檢索之前先確定可見範圍,而且這個範圍要用政策引擎推導、用 metadata filter 落地、用 tenant tag 歸因**。Silo/Pool/Bridge 的隔離選擇、Verified Permissions 的宣告式授權、語意快取的降本、每租戶的配額與成本拆分——這些才是把一個 RAG demo 變成能賣給一百家公司的產品的距離。

下一篇,我們處理另一個企業級硬骨頭:當通用模型不夠好、或你有大量專有資料想讓模型「內化」時,該怎麼**客製基礎模型**——以及更重要的,怎麼**治理**這些客製模型,讓它們的訓練、評估、上線都可稽核、可回溯、有品質關卡。這是 Part 7:基礎模型客製化與模型治理。

---

## 系列導覽(進階篇)

- **Part 6(本篇)**:企業級多租戶 RAG 平台
- **Part 7**:基礎模型客製化與模型治理
- **Part 8**:即時串流 ML 與詐欺偵測
- **Part 9**:企業 AI 安全、合規與資料治理
- **Part 10**:企業 AI 平台工程 —— 落地區、LLM Gateway 與 FinOps

> 基礎篇回顧:Part 1 RAG 問答 · Part 2 IDP 管線 · Part 3 即時推薦 · Part 4 自主 Agent · Part 5 MLOps 與可觀測性
