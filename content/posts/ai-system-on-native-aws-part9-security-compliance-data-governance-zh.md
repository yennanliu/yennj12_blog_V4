---
title: "AI System on Native AWS - Part 9 - 企業 AI 安全、合規與資料治理"
date: 2026-07-26T09:00:00+08:00
draft: false
description: "當 AI 系統處理的是病歷、金流、個資,而且要通過稽核時,資安與合規不是加分項而是上線的門票。本篇把這個橫跨所有系統的維度單獨講透:用 PrivateLink/VPC endpoint 讓資料永不觸網、KMS 客戶金鑰全程加密、Macie + Comprehend 做 PII 偵測與去識別化、Lake Formation 做資料湖細粒度授權、Organizations SCP 從組織層鎖死可用模型與區域、CloudTrail + Guardrails 做全鏈稽核,全部用 CDK(CloudFormation)描述,對應 HIPAA/GDPR 的實際控制點。"
categories: ["engineering", "ai", "all"]
tags: ["AWS", "CDK", "CloudFormation", "Security", "Compliance", "Data Governance", "PrivateLink", "KMS", "Lake Formation", "Enterprise"]
authors: ["yen"]
readTime: "27 min"
---

> 大部分團隊做 AI 的資安是「上線後補」:先把系統做出來,等法遵來問「資料會不會流到外面」「病歷有沒有加密」「誰存取過這些資料」時,才發現整套架構要重來。
> 在受管制的產業,順序是反的:**資安與合規是上線的門票,不是上線後的裝飾**。資料能不能不經過公網、金鑰是不是你自己掌握、個資有沒有去識別化、每一次存取有沒有留痕、模型會不會被誘導洩漏敏感資料——這些不通過,系統再聰明也不能上線。
> 好消息是,在 AWS 上這些大多是「設定」而非「重寫」:PrivateLink 讓 Bedrock 呼叫永不觸網、KMS 讓你掌握金鑰、SCP 從組織層畫紅線、Macie 自動掃出散落的個資。
> 這是 Part 9:把橫跨前面所有系統的資安、合規、資料治理維度,一次講透——並且用 CDK 把它們變成基礎設施的一部分,而不是文件裡的承諾。

---

## 一、情境與痛點:合規是門票,不是裝飾

前面八篇的系統,只要換一個場景就全部進入「受管制」狀態:

- RAG 問答的文件是**病歷**(HIPAA)、IDP 處理的是**含個資的合約**(GDPR/個資法)、推薦與風控碰的是**金流與消費行為**(PCI DSS)。
- 這些場景下,一個看似無害的設計會變成合規事故:把 prompt 送去區域外的模型端點(資料跨境)、向量庫沒加密(靜態資料未保護)、log 裡印出完整 prompt 含身分證號(PII 外洩)、沒人知道誰在何時存取了哪份病歷(稽核缺口)。

企業 AI 的資安可以拆成五個必須同時成立的問題:

```
問題                        對應控制                        沒做的後果
──────────────────────────────────────────────────────────────────────
① 資料會不會流到公網?         PrivateLink / VPC endpoint      資料跨網,合規直接不過
② 資料有沒有全程加密?         KMS 客戶金鑰(CMK)+ TLS         靜態/傳輸未加密,稽核失敗
③ 個資有沒有被找出並保護?     Macie + Comprehend PII          散落的個資 = 未爆彈
④ 誰能存取什麼資料?          Lake Formation + IAM 細粒度     權限過大 = 內部威脅
⑤ 每次存取有沒有留痕?         CloudTrail + Bedrock 呼叫日誌   無稽核軌跡 = 無法歸責
```

再加上一個 AI 特有的問題:**⑥ 模型本身會不會變成洩漏管道?**(被 prompt injection 誘導吐出訓練資料或系統提示、把 A 使用者的 context 洩漏給 B)——這靠 Guardrails 與租戶隔離(Part 6)守住。

這一篇逐一拆解,重點是:**這些控制要「code 進 stack」,由 CDK 強制施行,而不是靠一份沒人執行的資安政策文件。**

---

## 二、系統目的:控制目標

不同於前面幾篇的「功能/非功能需求」,合規系統的目的是一組**控制目標(control objectives)**,每一個都要能舉證:

| 控制目標 | 具體要求 | 對應法規範例 |
|---------|---------|-------------|
| 資料不出境/不觸網 | AI 服務呼叫走私有網路,限定區域 | GDPR 資料主權、資料在地化 |
| 靜態與傳輸加密 | 全部用 KMS CMK 加密,TLS 傳輸 | HIPAA、PCI DSS |
| 最小權限 | 每個角色只有必要權限,資料湖欄位級授權 | 所有框架的核心 |
| PII 保護 | 敏感欄位偵測、遮蔽、去識別化 | GDPR、個資法 |
| 完整稽核軌跡 | 誰、何時、對什麼資料、做了什麼 | HIPAA、SOC 2 |
| 護欄與隔離 | 模型不洩漏敏感內容、租戶不互穿 | AI 特有風險 |
| 可舉證 | 上述都能自動產生稽核證據 | 稽核的實務前提 |

**核心心法:合規不是「相信我們有做」,而是「拿得出證據證明有做」。** 所以每個控制都要伴隨可查詢的紀錄(CloudTrail、Config、Macie 報告),而且最好由 SCP/Config Rule 自動阻擋違規,而非事後發現。

---

## 三、系統設計與架構

### 3.1 防禦縱深:五層控制

```
┌──────────────────────────────────────────────────────────────┐
│  ⑤ 組織層:Organizations SCP + Control Tower                   │
│     從最上層畫紅線:禁用未核准區域、禁用未核准模型、強制加密       │
├──────────────────────────────────────────────────────────────┤
│  ④ 網路層:VPC + PrivateLink/VPC Endpoint                      │
│     Bedrock/SageMaker/S3 呼叫全走私有網路,無 Internet Gateway  │
├──────────────────────────────────────────────────────────────┤
│  ③ 資料層:KMS CMK + Lake Formation + Macie                    │
│     全程加密、資料湖欄位級授權、自動掃描 PII                     │
├──────────────────────────────────────────────────────────────┤
│  ② 應用層:Guardrails + 租戶隔離(Part 6)+ PII 去識別化          │
│     模型輸入輸出過濾、跨租戶隔離、log 遮蔽                       │
├──────────────────────────────────────────────────────────────┤
│  ① 稽核層:CloudTrail + Bedrock 呼叫日誌 + Config              │
│     全鏈留痕、組態合規持續監控                                   │
└──────────────────────────────────────────────────────────────┘
```

縱深的意義:**任何一層被突破,還有其他層兜住**。prompt injection 繞過 Guardrails,還有租戶隔離擋著;IAM 設錯,還有 SCP 從組織層封住區域;應用忘了加密,還有 SCP 強制拒絕未加密寫入。

### 3.2 關鍵原則:資料永不觸網

受管制 AI 最常被質疑的一點:「你把病歷送去 Bedrock,資料會不會流出去?」答案取決於你怎麼連 Bedrock。

```
❌ 走公網:VPC → NAT Gateway → Internet → Bedrock 公開端點
   資料離開你的私有網路,即使加密,合規上仍是「觸網」

✅ 走 PrivateLink:VPC → Interface VPC Endpoint → Bedrock(AWS 內網)
   流量永不離開 AWS 骨幹網,不經過公網,滿足資料主權要求
```

透過 **Interface VPC Endpoint(PrivateLink)**,你對 Bedrock、SageMaker、S3、Comprehend 的呼叫全部走 AWS 內部網路,VPC 甚至可以完全沒有對外的 Internet Gateway。這是「資料不出境/不觸網」控制目標的技術落地。

---

## 四、CDK(CloudFormation)實作

### 4.1 網路層:私有 VPC + Bedrock/S3 PrivateLink

```typescript
// lib/network.ts 片段
import * as ec2 from 'aws-cdk-lib/aws-ec2';

// 隔離子網:沒有 NAT、沒有 IGW,資料無法自己流到公網
const vpc = new ec2.Vpc(this, 'SecureVpc', {
  natGateways: 0,
  subnetConfiguration: [
    { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
  ],
});

// Bedrock 走 Interface Endpoint(PrivateLink)—— 呼叫模型永不觸網
vpc.addInterfaceEndpoint('BedrockRuntime', {
  service: ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
  privateDnsEnabled: true,
});
vpc.addInterfaceEndpoint('BedrockAgentRuntime', {
  service: ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENT_RUNTIME,
});
// SageMaker、Comprehend、KMS、Secrets 也各自加 endpoint
vpc.addInterfaceEndpoint('SageMakerRuntime', {
  service: ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_RUNTIME,
});
// S3 用 Gateway Endpoint(免費)
vpc.addGatewayEndpoint('S3', { service: ec2.GatewayVpcEndpointAwsService.S3 });
```

### 4.2 資料層:KMS 客戶金鑰,全程加密

用**客戶自管金鑰(CMK)**而非 AWS 託管金鑰,才能自己掌控金鑰輪替、稽核金鑰使用、必要時撤銷(等於讓資料立即不可讀)。

```typescript
// lib/encryption.ts 片段
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';

const dataKey = new kms.Key(this, 'AiDataKey', {
  enableKeyRotation: true,                 // 自動年度輪替
  alias: 'alias/ai-data',
  description: 'CMK for all AI system data at rest',
});

// 所有存放敏感資料的資源都用這把 CMK
const docsBucket = new s3.Bucket(this, 'SecureDocs', {
  encryption: s3.BucketEncryption.KMS,
  encryptionKey: dataKey,
  enforceSSL: true,                        // 強制 TLS(拒絕非加密傳輸)
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  versioned: true,
});
// DynamoDB、OpenSearch、SNS/SQS、CloudWatch Logs 同樣指定 encryptionKey: dataKey
```

### 4.3 資料層:Macie 自動掃描散落的 PII

你不會知道所有敏感資料在哪——使用者上傳的 PDF 裡可能夾著身分證影本。**Macie** 自動掃 S3,用 ML 找出 PII 並分級告警。

```typescript
// lib/macie.ts 片段
import * as macie from 'aws-cdk-lib/aws-macie';

new macie.CfnSession(this, 'MacieSession', {
  findingPublishingFrequency: 'FIFTEEN_MINUTES',
  status: 'ENABLED',
});
// 定期敏感資料探索 job,掃描文件桶,findings 進 EventBridge → 告警/自動隔離
new macie.CfnClassificationJob(this, 'PiiScan', {
  jobType: 'SCHEDULED',
  name: 'docs-pii-scan',
  s3JobDefinition: { bucketDefinitions: [{ accountId: this.account, buckets: [docsBucket.bucketName] }] },
  scheduleFrequency: { dailySchedule: {} },
});
```

而在資料進 RAG/訓練/log **之前**的即時去識別化,用 Part 2 的 Comprehend PII(偵測後遮蔽/token 化),確保 PII 不會進入向量庫、log、或訓練集。

### 4.4 資料層:Lake Formation 欄位級授權

企業資料湖(給訓練與分析用)不能是「有 S3 權限就能看全部」。**Lake Formation** 提供**表級、欄位級、列級**的細粒度授權——資料科學家能看去識別化後的欄位,但看不到原始身分證號。

```typescript
// lib/lake-formation.ts 片段
import * as lakeformation from 'aws-cdk-lib/aws-lakeformation';

// 授予「資料科學家角色」只能存取特定資料庫、且排除敏感欄位
new lakeformation.CfnPrincipalPermissions(this, 'DsGrant', {
  principal: { dataLakePrincipalIdentifier: dataScientistRole.roleArn },
  resource: {
    tableWithColumns: {
      catalogId: this.account,
      databaseName: 'customer_analytics',
      name: 'transactions',
      columnWildcard: { excludedColumnNames: ['ssn', 'card_number', 'full_name'] }, // 排除敏感欄
    },
  },
  permissions: ['SELECT'],
  permissionsWithGrantOption: [],
});
```

### 4.5 組織層:SCP 從最上層畫紅線

**Service Control Policy(SCP)** 是組織層的護欄:即使某個帳號的 IAM 開了權限,SCP 拒絕的操作**任何人都做不了**。這是防止「資料跨境」「用未核准模型」的最強手段——它不靠應用自律,而是從組織根部封死。

```typescript
// lib/scp.ts 片段(用 Organizations,通常在管理帳號部署)
import * as org from 'aws-cdk-lib/aws-organizations';   // 或用 CfnPolicy 直接寫

// 範例 SCP JSON:禁止在核准區域以外呼叫 Bedrock;禁止關閉加密
const scpDocument = {
  Version: '2012-10-17',
  Statement: [
    {
      Sid: 'DenyBedrockOutsideApprovedRegions',
      Effect: 'Deny',
      Action: ['bedrock:*'],
      Resource: '*',
      Condition: { StringNotEquals: { 'aws:RequestedRegion': ['eu-central-1', 'eu-west-1'] } },
    },
    {
      Sid: 'DenyUnencryptedS3',
      Effect: 'Deny',
      Action: 's3:PutObject',
      Resource: '*',
      Condition: { StringNotEquals: { 's3:x-amz-server-side-encryption': 'aws:kms' } },
    },
    {
      Sid: 'DenyDisableGuardDutyOrCloudTrail',
      Effect: 'Deny',
      Action: ['cloudtrail:StopLogging', 'guardduty:DeleteDetector'],
      Resource: '*',
    },
  ],
};
```

> SCP 把「資料只能留在歐洲區、寫 S3 一定要加密、沒人能關掉稽核日誌」變成**物理上做不到的違規**,而不是「請大家遵守」的政策。這是合規從「承諾」變「強制」的關鍵躍遷。

### 4.6 稽核層:CloudTrail + Config + Bedrock 呼叫日誌

```typescript
// lib/audit.ts 片段
import * as cloudtrail from 'aws-cdk-lib/aws-cloudtrail';
import * as config from 'aws-cdk-lib/aws-config';

// 全區、含資料事件的 CloudTrail,日誌用 CMK 加密、防篡改
const trail = new cloudtrail.Trail(this, 'AuditTrail', {
  isMultiRegionTrail: true,
  encryptionKey: dataKey,
  enableFileValidation: true,              // 防竄改驗證
});
trail.addS3EventSelector([{ bucket: docsBucket }], { readWriteType: cloudtrail.ReadWriteType.ALL });

// AWS Config:持續監控組態合規(如:是否有未加密資源、是否有公開桶)
new config.ManagedRule(this, 'S3Encrypted', {
  identifier: config.ManagedRuleIdentifiers.S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED,
});
```

外加 Part 5 的 **Bedrock model invocation logging**:每一次模型呼叫的輸入輸出留痕(記得日誌桶本身用 CMK 加密、限制存取,因為它含 prompt)。至此,「誰在何時對哪份資料做了什麼、餵給模型什麼、模型回了什麼」全鏈可查。

---

## 五、技術選型考量:為什麼選 X 不選 Y

### 5.1 PrivateLink vs NAT Gateway 出公網

```
選擇            PrivateLink(VPC Endpoint)        NAT + 公網
──────────────────────────────────────────────────────────
資料路徑        永不離開 AWS 內網                  經過公網
合規            滿足資料主權/在地化                跨網,受管制場景通常不過
成本            每個 endpoint 有小時費 + 流量費     NAT 也要錢
複雜度          要為每個服務加 endpoint             簡單
```

**翻盤條件**:非受管制、資料不敏感的內部工具,走 NAT 出公網更省事。一旦碰到病歷、金流、個資,PrivateLink 幾乎是強制的——「資料不觸網」通常是白紙黑字的稽核要求。

### 5.2 KMS 客戶金鑰(CMK) vs AWS 託管金鑰

- **AWS 託管金鑰**:免費、零管理,但你無法稽核金鑰使用、無法自訂輪替、無法撤銷。
- **客戶自管 CMK**:能稽核每次金鑰使用(誰解密了什麼)、自訂輪替政策、必要時撤銷金鑰讓資料瞬間不可讀(加密刪除)。**受管制場景幾乎都要求 CMK**,因為「金鑰掌控權」本身是控制目標。

**翻盤條件**:非敏感資料用託管金鑰省成本與管理;敏感資料一律 CMK。

### 5.3 SCP(預防) vs Config Rule(偵測)

- **SCP**:**預防性**——違規操作直接被拒,根本做不成。強,但要小心設太死綁住正常作業。
- **Config Rule**:**偵測性**——違規發生後告警/自動修復。彈性,但資料可能已經暴露一段時間。
- **正解**:高風險用 SCP 硬擋(區域、加密、關稽核),其餘用 Config 持續偵測 + 自動修復。兩者互補,不是二選一。

### 5.4 應用層 PII 去識別化 vs 只靠 Macie 事後掃描

- **Macie**:事後掃描,找出「已經存在的」PII——重要,但它是**偵測**,資料已經落地了。
- **Comprehend 即時去識別化**:在資料進向量庫/log/訓練集**之前**遮蔽——**預防**,PII 根本不進敏感位置。
- **正解**:即時去識別化擋在入口(預防),Macie 掃描兜底(偵測漏網的)。**只靠 Macie 等於承認 PII 會先落地再說**,對高敏感場景不夠。

---

## 六、成本與稽核效益

合規的「成本」要對比「不合規的代價」。以一套受管制 AI 平台的資安附加成本估算(概略,疊加在業務系統之上):

| 項目 | 用量 | 概略月費 |
|------|------|---------|
| Interface VPC Endpoints | ~8 個服務 × 多 AZ | ~$150–400 |
| KMS CMK | 幾把金鑰 + 大量請求 | ~$50–200 |
| Macie | 掃描資料量計費 | ~$300–1,500(視資料量) |
| CloudTrail 資料事件 + Config | 高事件量 | ~$200–600 |
| Lake Formation | 幾乎免費(底層 Glue/S3 計費) | ~$0 |
| **資安合規附加成本** | | **~$700–2,700 / 月** |

**成本洞察**:資安合規是進階篇裡**成本形狀最特別**的——它幾乎不隨業務流量變動,而是「一套固定的控制稅」。但它的價值不在省錢,而在**它是門票**:

- **沒有它,系統不能上線**:在受管制產業,PrivateLink、CMK、稽核軌跡不是選配,是「能不能做這門生意」的前提。$2,000/月換一張進入醫療/金融市場的門票,ROI 無限大。
- **違規的代價是數量級之上**:GDPR 罰款可達全球營收 4%、一次病歷外洩的和解與商譽損失以百萬計。合規成本對比的是這個,不是絕對值。
- **自動化稽核省下的是人力**:CloudTrail + Config + Macie 自動產出稽核證據,省下每次稽核季手工蒐證的大量人月——這是隱形但巨大的節省。

---

## 七、延伸與常見的坑

**延伸方向:**

- **多帳號隔離**:用 Organizations 把 prod/非 prod、不同資料敏感等級拆到不同帳號,爆炸半徑最小化——這是 Part 10 落地區的核心。
- **BYOK / 外部金鑰**:最高合規要求下,用 KMS External Key Store(XKS)把金鑰放在你自己的 HSM,AWS 完全碰不到金鑰材料。
- **資料保留與刪除權**:GDPR 的「被遺忘權」要求能刪除特定個人的所有資料,包括向量庫裡的 embedding——設計時就要能按 subject 定位並刪除。
- **模型層合規**:確認所用的 Bedrock 模型在你的區域可用、其資料使用政策符合要求(Bedrock 不用你的資料訓練基礎模型,但仍要在合規文件中載明)。

**最容易踩的坑:**

1. **log 印出完整 prompt/回應**:含身分證號、卡號的 prompt 被寫進 CloudWatch Logs,log 本身變成 PII 外洩點。log 前必須遮蔽,且 log 桶要 CMK 加密。
2. **VPC Endpoint 漏一個服務**:加了 Bedrock endpoint 卻忘了 KMS/S3/Secrets endpoint,某個呼叫悄悄走了公網。要盤點所有依賴服務。
3. **SCP 設太死綁死自己**:一條 `Deny` 沒設好例外,連 CI/CD 或管理員都動不了。SCP 要在非 prod 組織單元先測。
4. **只加密 S3,忘了其他**:向量庫(OpenSearch)、佇列(SQS)、日誌、DynamoDB、快照都要用同一把 CMK,漏一個就是未加密的敏感資料。
5. **稽核日誌可被關掉/竄改**:CloudTrail 沒開檔案驗證、沒用 SCP 保護,攻擊者可先關 log 再作案。日誌的完整性本身要被保護。
6. **合規當一次性專案**:過了稽核就鬆懈。合規是持續狀態,要靠 Config 持續監控 + 自動修復維持,而非年度衝刺。

---

## 小結

在受管制產業,資安合規不是 AI 系統的裝飾,而是**上線的門票**。它的工程本質是把六個控制目標——資料不觸網、全程加密、最小權限、PII 保護、完整稽核、護欄隔離——用**防禦縱深的五層控制**落地,而且**每一層都 code 進 CDK、由 SCP/Config 強制施行、產出可舉證的稽核軌跡**。關鍵心法有三:預防勝於偵測(SCP + 入口去識別化)、掌控金鑰即掌控資料(CMK)、合規是可舉證的持續狀態而非一次性承諾。

進階篇走到這裡,我們已經有了:多租戶平台、可治理的模型、即時風控、資安合規的地基。最後一篇,把這一切收束成一個問題:**當一個企業有幾十個團隊、上百個 AI 專案時,平台團隊該如何把這些能力打包成「內部產品」,讓每個團隊都能自助、安全、且成本可控地用 AI?** 這是 Part 10,也是整個系列的終章:企業 AI 平台工程。

---

## 系列導覽(進階篇)

- **Part 6**:企業級多租戶 RAG 平台
- **Part 7**:基礎模型客製化與模型治理
- **Part 8**:即時串流 ML 與詐欺偵測
- **Part 9(本篇)**:企業 AI 安全、合規與資料治理
- **Part 10**:企業 AI 平台工程 —— 落地區、LLM Gateway 與 FinOps

> 基礎篇回顧:Part 1 RAG 問答 · Part 2 IDP 管線 · Part 3 即時推薦 · Part 4 自主 Agent · Part 5 MLOps 與可觀測性
