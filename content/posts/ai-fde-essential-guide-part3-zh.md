---
title: "AI Forward Deployed Engineer 必備技能指南（三）：企業級 AI 整合與部署策略"
date: 2026-05-26T17:01:52+09:00
draft: false
weight: 3
description: "深入探討企業級 AI 系統整合策略，包含雲端平台部署、安全性管理、RAG 架構設計與企業數據管道建構"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Cloud Deployment", "GCP", "AWS", "Azure", "RAG", "Data Pipeline", "Security", "cheatsheet"]
authors: ["yen"]
readTime: "18 min"
---

## 前言

企業級 AI 整合與部署是 AI FDE 最具挑戰性的工作之一。需要處理複雜的企業架構、安全合規要求、數據整合與系統可靠性問題。本文將深入探討雲端平台部署策略、企業安全框架、RAG 架構設計與數據管道建構等核心技術。

## 1. 雲端平台部署策略

### Google Cloud Platform (GCP) 深度整合

**Vertex AI 生產部署：**
```python
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic
import yaml

class GCPAIDeploymentManager:
    def __init__(self, project_id: str, region: str = "us-central1"):
        self.project_id = project_id
        self.region = region
        
        # 初始化 Vertex AI
        aiplatform.init(
            project=project_id,
            location=region,
            staging_bucket=f"gs://{project_id}-ml-staging"
        )
    
    def deploy_custom_model(self, model_config: dict):
        """部署客製化模型到 Vertex AI"""
        
        # 創建容器映像
        container_spec = {
            "image_uri": model_config["container_image"],
            "env": [
                {"name": "MODEL_NAME", "value": model_config["model_name"]},
                {"name": "MODEL_VERSION", "value": model_config["version"]},
                {"name": "BATCH_SIZE", "value": str(model_config.get("batch_size", 32))}
            ],
            "ports": [{"container_port": 8080}]
        }
        
        # 模型規格定義
        model = aiplatform.Model.upload(
            display_name=model_config["display_name"],
            artifact_uri=model_config["model_artifacts_uri"],
            serving_container_image_uri=model_config["container_image"],
            serving_container_predict_route="/predict",
            serving_container_health_route="/health",
            serving_container_environment_variables=model_config.get("env_vars", {}),
            sync=True
        )
        
        # 部署到端點
        endpoint = model.deploy(
            machine_type=model_config.get("machine_type", "n1-standard-4"),
            min_replica_count=model_config.get("min_replicas", 1),
            max_replica_count=model_config.get("max_replicas", 10),
            accelerator_type=model_config.get("accelerator_type"),
            accelerator_count=model_config.get("accelerator_count"),
            traffic_percentage=100,
            sync=True
        )
        
        return {
            "model_id": model.resource_name,
            "endpoint_id": endpoint.resource_name,
            "prediction_url": endpoint.predict_url
        }
    
    def setup_auto_scaling(self, endpoint_name: str, scaling_config: dict):
        """設定自動擴展策略"""
        client = gapic.EndpointServiceClient()
        
        # 自動擴展設定
        autoscaling_config = {
            "min_replica_count": scaling_config["min_replicas"],
            "max_replica_count": scaling_config["max_replicas"],
            "target_utilization": scaling_config.get("target_cpu_utilization", 70),
            "scale_in_replicas": scaling_config.get("scale_in_replicas", 1),
            "scale_out_replicas": scaling_config.get("scale_out_replicas", 2)
        }
        
        # 更新端點配置
        update_request = gapic.UpdateEndpointRequest(
            endpoint={
                "name": endpoint_name,
                "traffic_split": {"0": 100},
                "deployed_models": [{
                    "automatic_resources": {
                        "min_replica_count": autoscaling_config["min_replica_count"],
                        "max_replica_count": autoscaling_config["max_replica_count"]
                    }
                }]
            }
        )
        
        operation = client.update_endpoint(request=update_request)
        return operation.result()

# 部署配置範例
deployment_config = {
    "model_name": "enterprise-llm-v1",
    "display_name": "Enterprise LLM Model",
    "version": "1.0.0",
    "container_image": "gcr.io/project-id/enterprise-llm:latest",
    "model_artifacts_uri": "gs://project-bucket/models/enterprise-llm-v1/",
    "machine_type": "n1-highmem-8",
    "min_replicas": 2,
    "max_replicas": 20,
    "accelerator_type": "NVIDIA_TESLA_T4",
    "accelerator_count": 1,
    "env_vars": {
        "MAX_SEQUENCE_LENGTH": "2048",
        "TEMPERATURE": "0.7",
        "TOP_P": "0.9"
    }
}
```

### AWS 企業級部署架構

**Amazon SageMaker 多模型端點：**
```python
import boto3
import sagemaker
from sagemaker.multidatamodel import MultiDataModel
from sagemaker.pytorch import PyTorchModel

class AWSAIDeploymentManager:
    def __init__(self, region: str, role_arn: str):
        self.region = region
        self.role_arn = role_arn
        self.session = sagemaker.Session()
        self.s3_client = boto3.client('s3')
        
    def deploy_multi_model_endpoint(self, models_config: list):
        """部署多模型端點以節省成本"""
        
        # 設定多模型容器
        container = {
            'Image': '763104351884.dkr.ecr.us-west-2.amazonaws.com/pytorch-inference:1.12.0-gpu-py38',
            'ModelDataUrl': 's3://my-bucket/models/',
            'Mode': 'MultiModel'
        }
        
        # 創建多模型數據模型
        multi_data_model = MultiDataModel(
            name="enterprise-multi-model",
            model_data_prefix="s3://my-bucket/models/",
            role=self.role_arn,
            container_def=container,
            sagemaker_session=self.session
        )
        
        # 部署端點
        predictor = multi_data_model.deploy(
            initial_instance_count=2,
            instance_type='ml.g4dn.xlarge',
            endpoint_name='enterprise-multi-model-endpoint',
            data_capture_config={
                'EnableCapture': True,
                'InitialSamplingPercentage': 100,
                'DestinationS3Uri': 's3://my-bucket/data-capture/',
                'CaptureOptions': [
                    {'CaptureMode': 'Input'},
                    {'CaptureMode': 'Output'}
                ]
            }
        )
        
        return predictor
    
    def setup_serverless_inference(self, model_config: dict):
        """設定無伺服器推理端點"""
        
        model = PyTorchModel(
            entry_point='inference.py',
            source_dir='code/',
            model_data=model_config['model_data_url'],
            role=self.role_arn,
            framework_version='1.12.0',
            py_version='py38',
            predictor_cls=sagemaker.predictor.Predictor
        )
        
        # 無伺服器配置
        serverless_config = sagemaker.ServerlessInferenceConfig(
            memory_size_in_mb=6144,  # 6GB
            max_concurrency=50,
            provisioned_concurrency=10
        )
        
        predictor = model.deploy(
            serverless_inference_config=serverless_config,
            endpoint_name=f"serverless-{model_config['name']}"
        )
        
        return predictor
    
    def configure_auto_scaling(self, endpoint_name: str, scaling_policy: dict):
        """配置 SageMaker 端點自動擴展"""
        
        autoscaling_client = boto3.client('application-autoscaling')
        
        # 註冊可擴展目標
        autoscaling_client.register_scalable_target(
            ServiceNamespace='sagemaker',
            ResourceId=f'endpoint/{endpoint_name}/variant/AllTraffic',
            ScalableDimension='sagemaker:variant:DesiredInstanceCount',
            MinCapacity=scaling_policy['min_capacity'],
            MaxCapacity=scaling_policy['max_capacity'],
            RoleARN=self.role_arn
        )
        
        # 設定擴展策略
        autoscaling_client.put_scaling_policy(
            PolicyName=f'{endpoint_name}-target-tracking-policy',
            ServiceNamespace='sagemaker',
            ResourceId=f'endpoint/{endpoint_name}/variant/AllTraffic',
            ScalableDimension='sagemaker:variant:DesiredInstanceCount',
            PolicyType='TargetTrackingScaling',
            TargetTrackingScalingPolicyConfiguration={
                'TargetValue': scaling_policy['target_invocations_per_instance'],
                'PredefinedMetricSpecification': {
                    'PredefinedMetricType': 'SageMakerVariantInvocationsPerInstance'
                },
                'ScaleOutCooldown': 300,
                'ScaleInCooldown': 600
            }
        )
```

### Azure OpenAI 企業整合

**Azure 認知服務部署：**
```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.cognitiveservices.language.textanalytics import TextAnalyticsClient

class AzureAIDeploymentManager:
    def __init__(self, subscription_id: str, resource_group: str):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.credential = DefaultAzureCredential()
        
    def deploy_openai_service(self, deployment_config: dict):
        """部署 Azure OpenAI 服務"""
        
        client = CognitiveServicesManagementClient(
            self.credential, 
            self.subscription_id
        )
        
        # 創建認知服務帳戶
        account_info = {
            'location': deployment_config['location'],
            'sku': {'name': deployment_config['sku']},
            'kind': 'OpenAI',
            'properties': {
                'customSubDomainName': deployment_config['subdomain'],
                'publicNetworkAccess': 'Enabled',
                'networkAcls': {
                    'defaultAction': 'Allow',
                    'virtualNetworkRules': [],
                    'ipRules': deployment_config.get('allowed_ips', [])
                }
            }
        }
        
        operation = client.accounts.begin_create(
            resource_group_name=self.resource_group,
            account_name=deployment_config['account_name'],
            account=account_info
        )
        
        account = operation.result()
        
        # 部署模型
        model_deployments = []
        for model_config in deployment_config['models']:
            deployment = client.deployments.begin_create_or_update(
                resource_group_name=self.resource_group,
                account_name=deployment_config['account_name'],
                deployment_name=model_config['deployment_name'],
                deployment={
                    'properties': {
                        'model': {
                            'format': 'OpenAI',
                            'name': model_config['model_name'],
                            'version': model_config['version']
                        },
                        'scaleSettings': {
                            'scaleType': 'Standard',
                            'capacity': model_config['capacity']
                        }
                    }
                }
            )
            model_deployments.append(deployment.result())
        
        return {
            'account': account,
            'deployments': model_deployments
        }
    
    def setup_private_endpoint(self, config: dict):
        """設定私有端點以增強安全性"""
        
        from azure.mgmt.network import NetworkManagementClient
        
        network_client = NetworkManagementClient(
            self.credential,
            self.subscription_id
        )
        
        # 創建私有端點
        private_endpoint_params = {
            'location': config['location'],
            'subnet': {'id': config['subnet_id']},
            'privateLinkServiceConnections': [{
                'name': f"{config['service_name']}-connection",
                'privateLinkServiceId': config['service_resource_id'],
                'groupIds': ['account']
            }]
        }
        
        operation = network_client.private_endpoints.begin_create_or_update(
            resource_group_name=self.resource_group,
            private_endpoint_name=config['endpoint_name'],
            parameters=private_endpoint_params
        )
        
        return operation.result()
```

## 2. 企業安全框架與合規性

### 身份驗證與授權系統

**企業級 RBAC 實作：**
```python
from enum import Enum
from dataclasses import dataclass
from typing import Set, List, Dict, Optional
import jwt
import hashlib
from datetime import datetime, timedelta

class UserRole(Enum):
    ADMIN = "admin"
    DATA_SCIENTIST = "data_scientist"
    ANALYST = "analyst"
    VIEWER = "viewer"
    EXTERNAL_CLIENT = "external_client"

class ResourceType(Enum):
    MODEL = "model"
    DATASET = "dataset"
    PIPELINE = "pipeline"
    ENDPOINT = "endpoint"
    LOGS = "logs"

class Permission(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    DEPLOY = "deploy"

@dataclass
class AccessControl:
    resource_type: ResourceType
    resource_id: str
    permissions: Set[Permission]
    conditions: Dict[str, any] = None

class EnterpriseSecurityManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.role_permissions = self._setup_role_permissions()
        self.audit_log = []
        
    def _setup_role_permissions(self) -> Dict[UserRole, List[AccessControl]]:
        """定義角色權限矩陣"""
        return {
            UserRole.ADMIN: [
                AccessControl(ResourceType.MODEL, "*", {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.DEPLOY}),
                AccessControl(ResourceType.DATASET, "*", {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE}),
                AccessControl(ResourceType.PIPELINE, "*", {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.EXECUTE}),
                AccessControl(ResourceType.LOGS, "*", {Permission.READ})
            ],
            UserRole.DATA_SCIENTIST: [
                AccessControl(ResourceType.MODEL, "*", {Permission.CREATE, Permission.READ, Permission.UPDATE}),
                AccessControl(ResourceType.DATASET, "*", {Permission.READ}),
                AccessControl(ResourceType.PIPELINE, "*", {Permission.CREATE, Permission.READ, Permission.EXECUTE})
            ],
            UserRole.ANALYST: [
                AccessControl(ResourceType.MODEL, "*", {Permission.READ}),
                AccessControl(ResourceType.DATASET, "*", {Permission.READ}),
                AccessControl(ResourceType.PIPELINE, "*", {Permission.READ, Permission.EXECUTE})
            ],
            UserRole.VIEWER: [
                AccessControl(ResourceType.MODEL, "*", {Permission.READ}),
                AccessControl(ResourceType.DATASET, "public_*", {Permission.READ})
            ],
            UserRole.EXTERNAL_CLIENT: [
                AccessControl(ResourceType.ENDPOINT, "client_*", {Permission.READ}, 
                           conditions={"time_limit": "business_hours", "rate_limit": 1000})
            ]
        }
    
    def authenticate_user(self, token: str) -> Optional[Dict]:
        """驗證用戶令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # 檢查令牌是否過期
            if datetime.utcnow() > datetime.fromtimestamp(payload['exp']):
                return None
                
            return {
                'user_id': payload['user_id'],
                'role': UserRole(payload['role']),
                'permissions': payload.get('permissions', []),
                'organization': payload.get('organization'),
                'expires_at': payload['exp']
            }
        except jwt.InvalidTokenError:
            return None
    
    def authorize_action(self, user_context: Dict, resource_type: ResourceType, 
                        resource_id: str, action: Permission) -> bool:
        """授權檢查"""
        user_role = user_context['role']
        user_permissions = self.role_permissions.get(user_role, [])
        
        for access_control in user_permissions:
            if (access_control.resource_type == resource_type and
                self._match_resource_pattern(access_control.resource_id, resource_id) and
                action in access_control.permissions):
                
                # 檢查額外條件
                if access_control.conditions:
                    if not self._check_conditions(access_control.conditions, user_context):
                        continue
                
                # 記錄訪問日誌
                self._log_access(user_context, resource_type, resource_id, action, "GRANTED")
                return True
        
        self._log_access(user_context, resource_type, resource_id, action, "DENIED")
        return False
    
    def _match_resource_pattern(self, pattern: str, resource_id: str) -> bool:
        """資源模式匹配"""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            return resource_id.startswith(pattern[:-1])
        return pattern == resource_id
    
    def _check_conditions(self, conditions: Dict, user_context: Dict) -> bool:
        """檢查額外訪問條件"""
        # 時間限制檢查
        if "time_limit" in conditions:
            current_hour = datetime.now().hour
            if conditions["time_limit"] == "business_hours":
                if not (9 <= current_hour <= 17):
                    return False
        
        # 速率限制檢查
        if "rate_limit" in conditions:
            # 實作速率限制邏輯
            pass
        
        return True
    
    def _log_access(self, user_context: Dict, resource_type: ResourceType,
                   resource_id: str, action: Permission, result: str):
        """記錄訪問審計日誌"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': user_context['user_id'],
            'organization': user_context.get('organization'),
            'resource_type': resource_type.value,
            'resource_id': resource_id,
            'action': action.value,
            'result': result,
            'ip_address': user_context.get('ip_address'),
            'user_agent': user_context.get('user_agent')
        }
        
        self.audit_log.append(log_entry)
        
        # 實際環境中應該寫入外部審計系統
        print(f"AUDIT: {log_entry}")
```

### 數據安全與加密

**端到端數據保護：**
```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
import base64

class DataSecurityManager:
    def __init__(self):
        self.symmetric_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.symmetric_key)
        
        # 生成 RSA 密鑰對
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        self.public_key = self.private_key.public_key()
    
    def encrypt_sensitive_data(self, data: bytes, classification: str = "confidential") -> Dict:
        """根據數據分類進行加密"""
        
        if classification == "public":
            # 公開數據不需加密
            return {
                "data": base64.b64encode(data).decode(),
                "encrypted": False,
                "classification": classification
            }
        
        elif classification in ["internal", "confidential", "restricted"]:
            # 使用對稱加密
            encrypted_data = self.cipher_suite.encrypt(data)
            
            return {
                "data": base64.b64encode(encrypted_data).decode(),
                "encrypted": True,
                "encryption_type": "symmetric",
                "classification": classification,
                "key_id": self._get_key_fingerprint(self.symmetric_key)
            }
        
        elif classification == "top_secret":
            # 使用非對稱加密
            encrypted_data = self.public_key.encrypt(
                data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return {
                "data": base64.b64encode(encrypted_data).decode(),
                "encrypted": True,
                "encryption_type": "asymmetric",
                "classification": classification
            }
    
    def decrypt_sensitive_data(self, encrypted_package: Dict) -> bytes:
        """解密敏感數據"""
        
        if not encrypted_package["encrypted"]:
            return base64.b64decode(encrypted_package["data"])
        
        encrypted_data = base64.b64decode(encrypted_package["data"])
        
        if encrypted_package["encryption_type"] == "symmetric":
            return self.cipher_suite.decrypt(encrypted_data)
        
        elif encrypted_package["encryption_type"] == "asymmetric":
            return self.private_key.decrypt(
                encrypted_data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
    
    def _get_key_fingerprint(self, key: bytes) -> str:
        """生成密鑰指紋"""
        digest = hashes.Hash(hashes.SHA256())
        digest.update(key)
        return base64.b64encode(digest.finalize()).decode()[:16]
    
    def implement_data_masking(self, data: Dict, user_role: UserRole) -> Dict:
        """根據用戶角色實施數據遮罩"""
        
        masking_rules = {
            UserRole.EXTERNAL_CLIENT: {
                "personal_id": "***MASKED***",
                "email": lambda x: x.split('@')[0][:3] + "***@" + x.split('@')[1],
                "phone": lambda x: x[:3] + "***" + x[-4:] if len(x) > 7 else "***MASKED***"
            },
            UserRole.ANALYST: {
                "personal_id": lambda x: x[:4] + "***" + x[-2:] if len(x) > 6 else "***MASKED***"
            },
            UserRole.DATA_SCIENTIST: {
                # 數據科學家可以看到更多詳細數據，但仍需遮罩部分敏感信息
            },
            UserRole.ADMIN: {
                # 管理員可以看到所有數據
            }
        }
        
        rules = masking_rules.get(user_role, {})
        masked_data = data.copy()
        
        for field, mask_func in rules.items():
            if field in masked_data:
                if callable(mask_func):
                    masked_data[field] = mask_func(str(masked_data[field]))
                else:
                    masked_data[field] = mask_func
        
        return masked_data
```

## 3. RAG (Retrieval-Augmented Generation) 架構設計

### 企業級向量數據庫實作

**向量搜尋與語意檢索：**
```python
import chromadb
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict, Optional
import hashlib

class EnterpriseRAGSystem:
    def __init__(self, collection_name: str = "enterprise_knowledge"):
        # 初始化向量數據庫
        self.chroma_client = chromadb.PersistentClient(path="./vector_db")
        
        # 初始化嵌入模型
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        
        # 創建或獲取集合
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
    def add_documents(self, documents: List[Dict[str, any]], batch_size: int = 100):
        """批量添加文件到向量數據庫"""
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            
            # 準備批次數據
            texts = [doc['content'] for doc in batch]
            metadatas = []
            ids = []
            
            for doc in batch:
                # 生成唯一 ID
                doc_id = self._generate_doc_id(doc)
                ids.append(doc_id)
                
                # 準備元數據
                metadata = {
                    'source': doc.get('source', 'unknown'),
                    'title': doc.get('title', ''),
                    'category': doc.get('category', 'general'),
                    'access_level': doc.get('access_level', 'internal'),
                    'created_at': doc.get('created_at', ''),
                    'last_updated': doc.get('last_updated', ''),
                    'content_length': len(doc['content'])
                }
                metadatas.append(metadata)
            
            # 生成嵌入向量
            embeddings = self.embedding_model.encode(texts).tolist()
            
            # 添加到向量數據庫
            self.collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
    
    def semantic_search(self, query: str, n_results: int = 5, 
                       access_level: str = "internal",
                       filters: Optional[Dict] = None) -> List[Dict]:
        """執行語意搜尋"""
        
        # 生成查詢嵌入
        query_embedding = self.embedding_model.encode([query]).tolist()
        
        # 構建過濾條件
        where_clause = {"access_level": {"$in": self._get_allowed_access_levels(access_level)}}
        
        if filters:
            where_clause.update(filters)
        
        # 執行搜尋
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        # 格式化結果
        formatted_results = []
        for i, doc in enumerate(results['documents'][0]):
            formatted_results.append({
                'content': doc,
                'metadata': results['metadatas'][0][i],
                'similarity_score': 1 - results['distances'][0][i],  # 轉換為相似度分數
                'relevance_rank': i + 1
            })
        
        return formatted_results
    
    def hybrid_search(self, query: str, keyword_weight: float = 0.3, 
                     semantic_weight: float = 0.7) -> List[Dict]:
        """混合搜尋：結合關鍵詞與語意搜尋"""
        
        # 語意搜尋
        semantic_results = self.semantic_search(query, n_results=20)
        
        # 關鍵詞搜尋 (簡化實作)
        keyword_results = self._keyword_search(query, n_results=20)
        
        # 合併與重新排序
        combined_scores = {}
        
        for result in semantic_results:
            doc_id = result['metadata'].get('id', hash(result['content']))
            combined_scores[doc_id] = {
                'doc': result,
                'semantic_score': result['similarity_score'],
                'keyword_score': 0
            }
        
        for result in keyword_results:
            doc_id = result['metadata'].get('id', hash(result['content']))
            if doc_id in combined_scores:
                combined_scores[doc_id]['keyword_score'] = result['score']
            else:
                combined_scores[doc_id] = {
                    'doc': result,
                    'semantic_score': 0,
                    'keyword_score': result['score']
                }
        
        # 計算最終分數
        final_results = []
        for doc_id, scores in combined_scores.items():
            final_score = (semantic_weight * scores['semantic_score'] + 
                          keyword_weight * scores['keyword_score'])
            
            result_doc = scores['doc'].copy()
            result_doc['final_score'] = final_score
            final_results.append(result_doc)
        
        # 按分數排序
        final_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        return final_results[:10]
    
    def _generate_doc_id(self, doc: Dict) -> str:
        """生成文件唯一 ID"""
        content_hash = hashlib.md5(doc['content'].encode()).hexdigest()
        source = doc.get('source', 'unknown')
        return f"{source}_{content_hash[:12]}"
    
    def _get_allowed_access_levels(self, user_access_level: str) -> List[str]:
        """根據用戶權限獲取允許訪問的數據級別"""
        access_hierarchy = {
            "public": ["public"],
            "internal": ["public", "internal"],
            "confidential": ["public", "internal", "confidential"],
            "restricted": ["public", "internal", "confidential", "restricted"]
        }
        
        return access_hierarchy.get(user_access_level, ["public"])
    
    def _keyword_search(self, query: str, n_results: int) -> List[Dict]:
        """關鍵詞搜尋實作 (簡化版)"""
        # 實際環境中應使用如 Elasticsearch 等全文搜尋引擎
        query_terms = query.lower().split()
        
        # 獲取所有文檔
        all_docs = self.collection.get()
        
        scored_docs = []
        for i, doc in enumerate(all_docs['documents']):
            score = sum(term in doc.lower() for term in query_terms) / len(query_terms)
            if score > 0:
                scored_docs.append({
                    'content': doc,
                    'metadata': all_docs['metadatas'][i],
                    'score': score
                })
        
        scored_docs.sort(key=lambda x: x['score'], reverse=True)
        return scored_docs[:n_results]
```

### 智能文件處理與分塊策略

**適應性文件分塊：**
```python
import re
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class DocumentChunk:
    content: str
    chunk_type: str
    metadata: Dict
    start_position: int
    end_position: int
    chunk_id: str

class IntelligentDocumentChunker:
    def __init__(self, max_chunk_size: int = 512, overlap_size: int = 50):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        
    def process_document(self, document: Dict) -> List[DocumentChunk]:
        """智能文件分塊處理"""
        
        content = document['content']
        doc_type = self._detect_document_type(content)
        
        if doc_type == "code":
            return self._chunk_code_document(content, document)
        elif doc_type == "structured":
            return self._chunk_structured_document(content, document)
        elif doc_type == "academic":
            return self._chunk_academic_document(content, document)
        else:
            return self._chunk_general_document(content, document)
    
    def _detect_document_type(self, content: str) -> str:
        """檢測文件類型"""
        
        # 程式碼檢測
        code_patterns = [
            r'def\s+\w+\(',  # Python 函數
            r'function\s+\w+\(',  # JavaScript 函數
            r'class\s+\w+',  # 類別定義
            r'import\s+\w+',  # 導入語句
            r'\{\s*[\w\s:]+\s*\}',  # JSON 物件
        ]
        
        if any(re.search(pattern, content) for pattern in code_patterns):
            return "code"
        
        # 學術論文檢測
        academic_patterns = [
            r'Abstract\s*:',
            r'Keywords\s*:',
            r'References\s*\n',
            r'Fig\.\s+\d+',
            r'Table\s+\d+',
        ]
        
        if any(re.search(pattern, content, re.IGNORECASE) for pattern in academic_patterns):
            return "academic"
        
        # 結構化文件檢測
        structured_patterns = [
            r'^#+\s',  # Markdown 標題
            r'^\d+\.\s',  # 編號列表
            r'^\*\s',  # 項目符號
        ]
        
        if any(re.search(pattern, content, re.MULTILINE) for pattern in structured_patterns):
            return "structured"
        
        return "general"
    
    def _chunk_code_document(self, content: str, document: Dict) -> List[DocumentChunk]:
        """程式碼文件分塊"""
        chunks = []
        
        # 按函數/類別分塊
        function_pattern = r'(def\s+\w+.*?(?=def\s+\w+|class\s+\w+|$))'
        class_pattern = r'(class\s+\w+.*?(?=class\s+\w+|def\s+\w+|$))'
        
        code_blocks = re.findall(f'{class_pattern}|{function_pattern}', content, re.DOTALL)
        
        position = 0
        for i, block_match in enumerate(code_blocks):
            block = block_match[0] or block_match[1]  # 取非空的匹配
            
            if len(block.strip()) > 0:
                chunk = DocumentChunk(
                    content=block.strip(),
                    chunk_type="code_block",
                    metadata={
                        **document.get('metadata', {}),
                        'block_index': i,
                        'programming_language': self._detect_language(block)
                    },
                    start_position=position,
                    end_position=position + len(block),
                    chunk_id=f"{document.get('id', 'unknown')}_code_{i}"
                )
                chunks.append(chunk)
            
            position += len(block)
        
        return chunks
    
    def _chunk_structured_document(self, content: str, document: Dict) -> List[DocumentChunk]:
        """結構化文件分塊（按章節）"""
        chunks = []
        
        # 按標題分塊
        section_pattern = r'(^#+\s+.+$)'
        sections = re.split(section_pattern, content, flags=re.MULTILINE)
        
        current_section = ""
        section_content = ""
        position = 0
        
        for i, part in enumerate(sections):
            if re.match(r'^#+\s+', part):
                # 這是一個標題
                if section_content.strip():
                    # 保存前一個章節
                    chunk = DocumentChunk(
                        content=f"{current_section}\n{section_content}".strip(),
                        chunk_type="section",
                        metadata={
                            **document.get('metadata', {}),
                            'section_title': current_section.strip('#').strip(),
                            'section_level': len(current_section) - len(current_section.lstrip('#'))
                        },
                        start_position=position - len(section_content),
                        end_position=position,
                        chunk_id=f"{document.get('id', 'unknown')}_section_{len(chunks)}"
                    )
                    chunks.append(chunk)
                
                current_section = part
                section_content = ""
            else:
                section_content += part
            
            position += len(part)
        
        # 添加最後一個章節
        if section_content.strip():
            chunk = DocumentChunk(
                content=f"{current_section}\n{section_content}".strip(),
                chunk_type="section",
                metadata={
                    **document.get('metadata', {}),
                    'section_title': current_section.strip('#').strip() if current_section else "Final Section"
                },
                start_position=position - len(section_content),
                end_position=position,
                chunk_id=f"{document.get('id', 'unknown')}_section_{len(chunks)}"
            )
            chunks.append(chunk)
        
        return chunks
    
    def _chunk_general_document(self, content: str, document: Dict) -> List[DocumentChunk]:
        """一般文件分塊（固定大小 + 重疊）"""
        chunks = []
        words = content.split()
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap_size):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_content = ' '.join(chunk_words)
            
            chunk = DocumentChunk(
                content=chunk_content,
                chunk_type="text_chunk",
                metadata={
                    **document.get('metadata', {}),
                    'chunk_index': i // (self.max_chunk_size - self.overlap_size),
                    'word_count': len(chunk_words)
                },
                start_position=i,
                end_position=i + len(chunk_words),
                chunk_id=f"{document.get('id', 'unknown')}_chunk_{len(chunks)}"
            )
            chunks.append(chunk)
        
        return chunks
    
    def _detect_language(self, code: str) -> str:
        """檢測程式語言"""
        language_patterns = {
            'python': [r'def\s+\w+', r'import\s+\w+', r'class\s+\w+', r'if\s+__name__'],
            'javascript': [r'function\s+\w+', r'var\s+\w+', r'const\s+\w+', r'=>'],
            'java': [r'public\s+class', r'import\s+java\.', r'public\s+static\s+void'],
            'cpp': [r'#include\s*<', r'int\s+main\s*\(', r'std::'],
            'sql': [r'SELECT\s+', r'FROM\s+', r'WHERE\s+', r'INSERT\s+INTO']
        }
        
        for language, patterns in language_patterns.items():
            if any(re.search(pattern, code, re.IGNORECASE) for pattern in patterns):
                return language
        
        return "unknown"
```

## 4. 企業數據管道與 ETL 架構

### 即時數據處理管道

**Apache Kafka + Apache Spark 整合：**
```python
from kafka import KafkaProducer, KafkaConsumer
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import json

class EnterpriseDataPipeline:
    def __init__(self, kafka_config: Dict, spark_config: Dict):
        self.kafka_config = kafka_config
        
        # 初始化 Spark Session
        self.spark = SparkSession.builder \
            .appName("EnterpriseAIPipeline") \
            .config("spark.sql.adaptive.enabled", "true") \
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
            .getOrCreate()
        
        # 設定日誌級別
        self.spark.sparkContext.setLogLevel("WARN")
        
    def create_streaming_pipeline(self, input_topic: str, output_topic: str):
        """創建即時數據處理管道"""
        
        # 從 Kafka 讀取串流數據
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_config['bootstrap_servers']) \
            .option("subscribe", input_topic) \
            .option("startingOffsets", "latest") \
            .load()
        
        # 定義數據結構
        schema = StructType([
            StructField("user_id", StringType(), True),
            StructField("event_type", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("data", MapType(StringType(), StringType()), True)
        ])
        
        # 解析 JSON 數據
        parsed_df = df.select(
            from_json(col("value").cast("string"), schema).alias("parsed_data"),
            col("timestamp").alias("kafka_timestamp")
        ).select("parsed_data.*", "kafka_timestamp")
        
        # 數據清洗與轉換
        cleaned_df = self._clean_and_transform_data(parsed_df)
        
        # 特徵工程
        enriched_df = self._feature_engineering(cleaned_df)
        
        # 異常檢測
        anomaly_df = self._detect_anomalies(enriched_df)
        
        # 輸出到 Kafka
        query = anomaly_df \
            .select(to_json(struct("*")).alias("value")) \
            .writeStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_config['bootstrap_servers']) \
            .option("topic", output_topic) \
            .option("checkpointLocation", "/tmp/kafka-checkpoint") \
            .outputMode("append") \
            .start()
        
        return query
    
    def _clean_and_transform_data(self, df):
        """數據清洗與轉換"""
        
        return df \
            .filter(col("user_id").isNotNull()) \
            .filter(col("event_type").isin(["click", "view", "purchase", "search"])) \
            .withColumn("hour", hour(col("timestamp"))) \
            .withColumn("day_of_week", dayofweek(col("timestamp"))) \
            .withColumn("is_weekend", when(col("day_of_week").isin([1, 7]), 1).otherwise(0))
    
    def _feature_engineering(self, df):
        """特徵工程"""
        
        # 時間窗口聚合
        windowed_df = df \
            .withWatermark("timestamp", "10 minutes") \
            .groupBy(
                col("user_id"),
                window(col("timestamp"), "5 minutes")
            ) \
            .agg(
                count("*").alias("event_count"),
                countDistinct("event_type").alias("unique_event_types"),
                collect_list("event_type").alias("event_sequence")
            )
        
        # 添加衍生特徵
        enhanced_df = windowed_df \
            .withColumn("events_per_minute", col("event_count") / 5.0) \
            .withColumn("event_diversity", col("unique_event_types") / col("event_count"))
        
        return enhanced_df
    
    def _detect_anomalies(self, df):
        """異常檢測"""
        
        # 簡單的統計異常檢測
        stats_df = df \
            .select(
                mean("event_count").alias("mean_events"),
                stddev("event_count").alias("stddev_events")
            )
        
        # 收集統計信息
        stats = stats_df.collect()[0]
        mean_events = stats["mean_events"]
        stddev_events = stats["stddev_events"]
        
        # 標記異常 (使用 Z-score)
        threshold = 2.0  # Z-score 閾值
        
        anomaly_df = df \
            .withColumn(
                "z_score",
                abs(col("event_count") - lit(mean_events)) / lit(stddev_events)
            ) \
            .withColumn(
                "is_anomaly",
                when(col("z_score") > threshold, 1).otherwise(0)
            ) \
            .withColumn("anomaly_score", col("z_score"))
        
        return anomaly_df
    
    def setup_batch_processing(self, input_path: str, output_path: str):
        """設定批次處理作業"""
        
        # 讀取批次數據
        batch_df = self.spark.read \
            .option("multiline", "true") \
            .json(input_path)
        
        # 數據品質檢查
        quality_report = self._data_quality_check(batch_df)
        
        # 數據處理
        processed_df = batch_df \
            .transform(self._clean_and_transform_data) \
            .transform(self._feature_engineering)
        
        # 分區並寫入
        processed_df \
            .repartition(col("day_of_week")) \
            .write \
            .mode("overwrite") \
            .partitionBy("day_of_week") \
            .parquet(output_path)
        
        return quality_report
    
    def _data_quality_check(self, df):
        """數據品質檢查"""
        
        total_records = df.count()
        
        quality_metrics = {
            "total_records": total_records,
            "null_user_ids": df.filter(col("user_id").isNull()).count(),
            "null_timestamps": df.filter(col("timestamp").isNull()).count(),
            "duplicate_records": total_records - df.dropDuplicates().count(),
            "completeness_rate": 1.0 - (df.filter(col("user_id").isNull()).count() / total_records)
        }
        
        return quality_metrics
```

### 機器學習管道自動化

**MLOps 流程實作：**
```python
from mlflow import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
import joblib
from typing import Dict, Any

class MLOpsManager:
    def __init__(self, experiment_name: str):
        self.experiment_name = experiment_name
        mlflow.set_experiment(experiment_name)
        
    def create_training_pipeline(self, config: Dict):
        """創建訓練管道"""
        
        with mlflow.start_run(run_name=f"training_{config['model_name']}"):
            
            # 記錄參數
            mlflow.log_params(config)
            
            # 數據準備
            X_train, y_train, X_test, y_test = self._prepare_data(config['data_config'])
            
            # 模型訓練
            model = self._train_model(X_train, y_train, config['model_config'])
            
            # 模型評估
            metrics = self._evaluate_model(model, X_test, y_test)
            mlflow.log_metrics(metrics)
            
            # 記錄模型
            mlflow.sklearn.log_model(
                model, 
                "model",
                registered_model_name=config['model_name']
            )
            
            # 模型驗證
            validation_passed = self._validate_model(model, metrics, config['validation_criteria'])
            
            if validation_passed:
                # 推進到生產環境
                self._promote_to_production(config['model_name'], mlflow.active_run().info.run_id)
            
            return {
                "run_id": mlflow.active_run().info.run_id,
                "metrics": metrics,
                "validation_passed": validation_passed
            }
    
    def _prepare_data(self, data_config: Dict):
        """數據準備"""
        # 實際實作會從數據湖或數據倉庫讀取數據
        # 這裡使用模擬數據
        from sklearn.datasets import make_classification
        from sklearn.model_selection import train_test_split
        
        X, y = make_classification(
            n_samples=data_config.get('n_samples', 10000),
            n_features=data_config.get('n_features', 20),
            n_informative=data_config.get('n_informative', 10),
            random_state=42
        )
        
        return train_test_split(X, y, test_size=0.2, random_state=42)
    
    def _train_model(self, X_train, y_train, model_config: Dict):
        """模型訓練"""
        
        model = RandomForestClassifier(
            n_estimators=model_config.get('n_estimators', 100),
            max_depth=model_config.get('max_depth', 10),
            random_state=42
        )
        
        model.fit(X_train, y_train)
        return model
    
    def _evaluate_model(self, model, X_test, y_test):
        """模型評估"""
        
        y_pred = model.predict(X_test)
        
        return {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, average='weighted'),
            "recall": recall_score(y_test, y_pred, average='weighted')
        }
    
    def _validate_model(self, model, metrics: Dict, criteria: Dict) -> bool:
        """模型驗證"""
        
        for metric_name, threshold in criteria.items():
            if metrics.get(metric_name, 0) < threshold:
                print(f"Model failed validation: {metric_name} = {metrics.get(metric_name)} < {threshold}")
                return False
        
        return True
    
    def _promote_to_production(self, model_name: str, run_id: str):
        """推進模型到生產環境"""
        
        client = mlflow.tracking.MlflowClient()
        
        # 獲取模型版本
        model_version = client.create_model_version(
            name=model_name,
            source=f"runs:/{run_id}/model",
            run_id=run_id
        )
        
        # 設定為生產階段
        client.transition_model_version_stage(
            name=model_name,
            version=model_version.version,
            stage="Production"
        )
        
        print(f"Model {model_name} version {model_version.version} promoted to Production")
    
    def setup_model_monitoring(self, model_name: str):
        """設定模型監控"""
        
        # 模型效能監控
        def monitor_model_performance():
            # 獲取生產模型
            client = mlflow.tracking.MlflowClient()
            model_version = client.get_latest_versions(model_name, stages=["Production"])[0]
            
            # 載入模型
            model_uri = f"models:/{model_name}/{model_version.version}"
            model = mlflow.sklearn.load_model(model_uri)
            
            # 獲取新數據並評估
            # 實際實作會從監控系統獲取新數據
            new_data = self._get_new_data()
            
            if new_data:
                predictions = model.predict(new_data['X'])
                
                # 計算效能指標
                if 'y' in new_data:  # 如果有真實標籤
                    accuracy = accuracy_score(new_data['y'], predictions)
                    
                    # 記錄監控指標
                    with mlflow.start_run():
                        mlflow.log_metric("production_accuracy", accuracy)
                        mlflow.log_metric("data_drift_score", self._calculate_data_drift(new_data['X']))
                        
                    # 檢查是否需要重新訓練
                    if accuracy < 0.8:  # 效能閾值
                        self._trigger_retraining(model_name)
        
        return monitor_model_performance
    
    def _get_new_data(self):
        """獲取新數據用於監控"""
        # 實際實作會從生產環境獲取數據
        return None
    
    def _calculate_data_drift(self, new_data):
        """計算數據漂移"""
        # 實際實作會使用如 evidently 等工具
        return 0.0
    
    def _trigger_retraining(self, model_name: str):
        """觸發模型重新訓練"""
        print(f"Triggering retraining for model: {model_name}")
        # 實際實作會啟動重新訓練流程
```

## 總結

本文深入探討了企業級 AI 整合與部署的關鍵技術：

1. **雲端平台部署**：GCP Vertex AI、AWS SageMaker、Azure OpenAI 的企業級應用
2. **安全框架**：RBAC 權限管理、數據加密、審計日誌與合規性
3. **RAG 架構**：向量數據庫、智能文件分塊、語意搜尋與混合檢索
4. **數據管道**：即時串流處理、批次作業、MLOps 自動化與模型監控

下一篇將專注於生產環境 AI 系統的監控與最佳化，包含效能調優、故障診斷與成本管理。

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"content": "Plan 5-part AI FDE blog series structure and topics", "status": "completed", "activeForm": "Planning 5-part AI FDE blog series structure and topics"}, {"content": "Create Part 1: AI FDE \u57fa\u790e\u6838\u5fc3\u6982\u5ff5\u8207\u6280\u8853\u68e7", "status": "completed", "activeForm": "Creating Part 1: AI FDE \u57fa\u790e\u6838\u5fc3\u6982\u5ff5\u8207\u6280\u8853\u68e7"}, {"content": "Create Part 2: \u591a\u667a\u6167\u9ad4\u7cfb\u7d71\u8207\u6846\u67b6\u5be6\u6230", "status": "completed", "activeForm": "Creating Part 2: \u591a\u667a\u6167\u9ad4\u7cfb\u7d71\u8207\u6846\u67b6\u5be6\u6230"}, {"content": "Create Part 3: \u4f01\u696d\u7d1a AI \u6574\u5408\u8207\u90e8\u7f72\u7b56\u7565", "status": "completed", "activeForm": "Creating Part 3: \u4f01\u696d\u7d1a AI \u6574\u5408\u8207\u90e8\u7f72\u7b56\u7565"}, {"content": "Create Part 4: \u751f\u7522\u74b0\u5883 AI \u7cfb\u7d71\u76e3\u63a7\u8207\u6700\u4f73\u5316", "status": "in_progress", "activeForm": "Creating Part 4: \u751f\u7522\u74b0\u5883 AI \u7cfb\u7d71\u76e3\u63a7\u8207\u6700\u4f73\u5316"}, {"content": "Create Part 5: \u5ba2\u6236\u5354\u4f5c\u8207\u554f\u984c\u89e3\u6c7a\u5be6\u52d9", "status": "pending", "activeForm": "Creating Part 5: \u5ba2\u6236\u5354\u4f5c\u8207\u554f\u984c\u89e3\u6c7a\u5be6\u52d9"}]
