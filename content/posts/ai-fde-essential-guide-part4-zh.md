---
title: "AI Forward Deployed Engineer 必備技能指南（四）：生產環境 AI 系統監控與最佳化"
date: 2026-05-26T17:05:09+09:00
draft: false
description: "深入探討生產環境 AI 系統的全方位監控策略、效能最佳化技術、故障診斷流程與成本管理實務"
categories: ["engineering", "ai", "all"]
tags: ["AI", "FDE", "Monitoring", "Optimization", "MLOps", "Performance", "Cost Management", "Production", "cheatsheet"]
authors: ["yen"]
readTime: "20 min"
---

## 前言

生產環境 AI 系統的監控與最佳化是確保企業 AI 應用成功的關鍵。從模型效能追蹤、基礎設施監控到成本控制，AI FDE 需要建立全方位的可觀測性體系。本文將深入探討 LLM-native 指標設計、分散式監控架構、智能故障診斷與企業級成本最佳化策略。

## 1. LLM-native 指標與評估體系

### 核心效能指標設計

**LLM 特定指標框架：**
```python
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
import numpy as np
from collections import deque
import time
import asyncio
from enum import Enum

class MetricType(Enum):
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    QUALITY = "quality"
    COST = "cost"
    RELIABILITY = "reliability"

@dataclass
class LLMMetrics:
    timestamp: float
    request_id: str
    model_name: str
    
    # 效能指標
    time_to_first_token: float  # TTFT - 首個 token 延遲
    time_per_output_token: float  # TPOT - 每個輸出 token 時間
    total_latency: float
    tokens_per_second: float
    
    # 品質指標
    perplexity: Optional[float] = None
    bleu_score: Optional[float] = None
    rouge_score: Optional[Dict[str, float]] = None
    human_feedback_score: Optional[float] = None
    
    # 成本指標
    input_tokens: int = 0
    output_tokens: int = 0
    compute_cost: float = 0.0
    
    # 可靠性指標
    success: bool = True
    error_type: Optional[str] = None
    retry_count: int = 0

class LLMMetricsCollector:
    def __init__(self, buffer_size: int = 10000):
        self.metrics_buffer = deque(maxlen=buffer_size)
        self.real_time_stats = {}
        
    def collect_metric(self, metric: LLMMetrics):
        """收集單一指標"""
        self.metrics_buffer.append(metric)
        self._update_real_time_stats(metric)
    
    def _update_real_time_stats(self, metric: LLMMetrics):
        """更新即時統計"""
        model_name = metric.model_name
        
        if model_name not in self.real_time_stats:
            self.real_time_stats[model_name] = {
                'total_requests': 0,
                'successful_requests': 0,
                'total_latency': 0,
                'total_cost': 0,
                'recent_latencies': deque(maxlen=100),
                'recent_quality_scores': deque(maxlen=100)
            }
        
        stats = self.real_time_stats[model_name]
        stats['total_requests'] += 1
        
        if metric.success:
            stats['successful_requests'] += 1
            stats['total_latency'] += metric.total_latency
            stats['recent_latencies'].append(metric.total_latency)
            
            if metric.human_feedback_score is not None:
                stats['recent_quality_scores'].append(metric.human_feedback_score)
        
        stats['total_cost'] += metric.compute_cost
    
    def get_sla_metrics(self, model_name: str, time_window: int = 3600) -> Dict:
        """獲取 SLA 相關指標"""
        cutoff_time = time.time() - time_window
        
        recent_metrics = [
            m for m in self.metrics_buffer 
            if m.model_name == model_name and m.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        successful_metrics = [m for m in recent_metrics if m.success]
        
        # 計算關鍵 SLA 指標
        return {
            'availability': len(successful_metrics) / len(recent_metrics),
            'p50_latency': np.percentile([m.total_latency for m in successful_metrics], 50),
            'p95_latency': np.percentile([m.total_latency for m in successful_metrics], 95),
            'p99_latency': np.percentile([m.total_latency for m in successful_metrics], 99),
            'average_ttft': np.mean([m.time_to_first_token for m in successful_metrics]),
            'average_tpot': np.mean([m.time_per_output_token for m in successful_metrics]),
            'error_rate': 1 - (len(successful_metrics) / len(recent_metrics)),
            'total_requests': len(recent_metrics),
            'requests_per_second': len(recent_metrics) / time_window
        }
    
    def detect_performance_anomalies(self, model_name: str) -> List[Dict]:
        """檢測效能異常"""
        anomalies = []
        
        if model_name not in self.real_time_stats:
            return anomalies
        
        stats = self.real_time_stats[model_name]
        recent_latencies = list(stats['recent_latencies'])
        
        if len(recent_latencies) < 10:
            return anomalies
        
        # 統計異常檢測
        mean_latency = np.mean(recent_latencies)
        std_latency = np.std(recent_latencies)
        
        # 檢測延遲異常
        for i, latency in enumerate(recent_latencies[-10:]):
            if latency > mean_latency + 3 * std_latency:
                anomalies.append({
                    'type': 'high_latency',
                    'value': latency,
                    'threshold': mean_latency + 3 * std_latency,
                    'severity': 'high' if latency > mean_latency + 5 * std_latency else 'medium'
                })
        
        # 檢測品質下降
        recent_quality = list(stats['recent_quality_scores'])
        if len(recent_quality) >= 5:
            recent_avg = np.mean(recent_quality[-5:])
            historical_avg = np.mean(recent_quality[:-5]) if len(recent_quality) > 5 else recent_avg
            
            if recent_avg < historical_avg * 0.9:  # 品質下降超過 10%
                anomalies.append({
                    'type': 'quality_degradation',
                    'current_quality': recent_avg,
                    'historical_quality': historical_avg,
                    'severity': 'high'
                })
        
        return anomalies
```

### 進階品質評估

**多維度品質檢測：**
```python
import torch
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import SentenceTransformer
from typing import List, Tuple

class LLMQualityEvaluator:
    def __init__(self):
        self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.toxicity_threshold = 0.7
        self.coherence_threshold = 0.6
        
    def evaluate_response_quality(self, prompt: str, response: str, 
                                expected_response: Optional[str] = None) -> Dict:
        """全面評估回應品質"""
        
        quality_scores = {}
        
        # 1. 語言流暢度評估
        quality_scores['fluency'] = self._evaluate_fluency(response)
        
        # 2. 相關性評估
        quality_scores['relevance'] = self._evaluate_relevance(prompt, response)
        
        # 3. 一致性評估
        quality_scores['coherence'] = self._evaluate_coherence(response)
        
        # 4. 安全性評估
        quality_scores['safety'] = self._evaluate_safety(response)
        
        # 5. 事實正確性評估（如果有預期答案）
        if expected_response:
            quality_scores['factual_accuracy'] = self._evaluate_factual_accuracy(
                response, expected_response
            )
        
        # 6. 幻覺檢測
        quality_scores['hallucination_score'] = self._detect_hallucination(prompt, response)
        
        # 計算綜合品質分數
        weights = {
            'fluency': 0.15,
            'relevance': 0.25,
            'coherence': 0.20,
            'safety': 0.25,
            'factual_accuracy': 0.10,
            'hallucination_score': 0.05
        }
        
        overall_score = sum(
            quality_scores.get(metric, 0.5) * weight 
            for metric, weight in weights.items()
        )
        
        quality_scores['overall_quality'] = overall_score
        
        return quality_scores
    
    def _evaluate_fluency(self, response: str) -> float:
        """評估語言流暢度"""
        # 簡化實作：基於語言模型困惑度
        sentences = response.split('.')
        
        fluency_indicators = {
            'avg_sentence_length': self._calculate_avg_sentence_length(sentences),
            'repetition_rate': self._calculate_repetition_rate(response),
            'grammar_errors': self._count_grammar_errors(response)
        }
        
        # 正規化分數
        fluency_score = 1.0
        
        # 懲罰過短或過長的句子
        if fluency_indicators['avg_sentence_length'] < 5 or fluency_indicators['avg_sentence_length'] > 50:
            fluency_score *= 0.8
        
        # 懲罰高重複率
        if fluency_indicators['repetition_rate'] > 0.3:
            fluency_score *= 0.7
        
        # 懲罰語法錯誤
        fluency_score *= max(0.1, 1.0 - fluency_indicators['grammar_errors'] * 0.1)
        
        return max(0.0, min(1.0, fluency_score))
    
    def _evaluate_relevance(self, prompt: str, response: str) -> float:
        """評估回應相關性"""
        
        # 使用語意相似度評估
        prompt_embedding = self.sentence_model.encode([prompt])
        response_embedding = self.sentence_model.encode([response])
        
        # 計算餘弦相似度
        similarity = torch.nn.functional.cosine_similarity(
            torch.tensor(prompt_embedding),
            torch.tensor(response_embedding)
        ).item()
        
        return max(0.0, min(1.0, similarity))
    
    def _evaluate_coherence(self, response: str) -> float:
        """評估內容一致性"""
        sentences = [s.strip() for s in response.split('.') if s.strip()]
        
        if len(sentences) <= 1:
            return 1.0
        
        # 計算相鄰句子間的語意相似度
        coherence_scores = []
        
        for i in range(len(sentences) - 1):
            sim = torch.nn.functional.cosine_similarity(
                torch.tensor(self.sentence_model.encode([sentences[i]])),
                torch.tensor(self.sentence_model.encode([sentences[i + 1]]))
            ).item()
            coherence_scores.append(sim)
        
        return np.mean(coherence_scores) if coherence_scores else 1.0
    
    def _evaluate_safety(self, response: str) -> float:
        """評估內容安全性"""
        
        # 檢測有害內容關鍵詞
        harmful_keywords = [
            'violent', 'illegal', 'discriminatory', 'hateful', 
            'toxic', 'offensive', 'inappropriate'
        ]
        
        safety_score = 1.0
        
        response_lower = response.lower()
        
        for keyword in harmful_keywords:
            if keyword in response_lower:
                safety_score *= 0.7
        
        # 檢測個人資訊洩露
        if self._contains_pii(response):
            safety_score *= 0.5
        
        return max(0.0, safety_score)
    
    def _evaluate_factual_accuracy(self, response: str, expected: str) -> float:
        """評估事實正確性"""
        
        # 提取關鍵事實
        response_facts = self._extract_facts(response)
        expected_facts = self._extract_facts(expected)
        
        if not expected_facts:
            return 0.5  # 無法評估
        
        # 計算事實重疊度
        overlap = len(set(response_facts) & set(expected_facts))
        accuracy = overlap / len(expected_facts) if expected_facts else 0.5
        
        return accuracy
    
    def _detect_hallucination(self, prompt: str, response: str) -> float:
        """檢測幻覺內容"""
        
        # 簡化實作：檢查回應是否包含提示中沒有的具體數字、日期等
        import re
        
        prompt_numbers = set(re.findall(r'\d+', prompt))
        response_numbers = set(re.findall(r'\d+', response))
        
        # 計算新增數字的比例
        new_numbers = response_numbers - prompt_numbers
        hallucination_indicator = len(new_numbers) / max(len(response_numbers), 1)
        
        return 1.0 - min(hallucination_indicator, 1.0)
    
    def _calculate_avg_sentence_length(self, sentences: List[str]) -> float:
        """計算平均句子長度"""
        if not sentences:
            return 0
        return sum(len(s.split()) for s in sentences) / len(sentences)
    
    def _calculate_repetition_rate(self, text: str) -> float:
        """計算重複率"""
        words = text.lower().split()
        if len(words) <= 1:
            return 0
        
        unique_words = len(set(words))
        return 1.0 - (unique_words / len(words))
    
    def _count_grammar_errors(self, text: str) -> int:
        """計算語法錯誤（簡化實作）"""
        # 實際環境中應使用 LanguageTool 等工具
        error_patterns = [
            r'\b(a)\s+[aeiou]',  # 錯誤的不定冠詞
            r'\b(an)\s+[bcdfg-hj-np-tv-z]',  # 錯誤的不定冠詞
        ]
        
        errors = 0
        for pattern in error_patterns:
            errors += len(re.findall(pattern, text, re.IGNORECASE))
        
        return errors
    
    def _contains_pii(self, text: str) -> bool:
        """檢測個人識別資訊"""
        import re
        
        # 簡化的 PII 檢測模式
        pii_patterns = [
            r'\b\d{4}-\d{4}-\d{4}-\d{4}\b',  # 信用卡號
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # 電子郵件
        ]
        
        for pattern in pii_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _extract_facts(self, text: str) -> List[str]:
        """提取文本中的事實（簡化實作）"""
        # 實際環境中應使用 NER 和關係抽取
        import re
        
        facts = []
        
        # 提取數字事實
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        facts.extend([f"number_{num}" for num in numbers])
        
        # 提取日期事實
        dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b', text)
        facts.extend([f"date_{date}" for date in dates])
        
        return facts
```

## 2. 分散式監控架構

### 可觀測性基礎設施

**OpenTelemetry + Prometheus 整合：**
```python
from opentelemetry import trace, metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from prometheus_client import Counter, Histogram, Gauge
import asyncio
import logging

class AISystemObservability:
    def __init__(self, service_name: str):
        self.service_name = service_name
        
        # 設定追蹤
        self.tracer = trace.get_tracer(__name__)
        
        # 自定義指標
        self.setup_custom_metrics()
        
        # 設定結構化日誌
        self.setup_logging()
        
    def setup_custom_metrics(self):
        """設定自定義指標"""
        
        # 計數器指標
        self.request_counter = Counter(
            'ai_requests_total',
            'Total AI model requests',
            ['model_name', 'endpoint', 'status']
        )
        
        self.token_counter = Counter(
            'ai_tokens_total',
            'Total tokens processed',
            ['model_name', 'token_type']  # input/output
        )
        
        # 直方圖指標
        self.latency_histogram = Histogram(
            'ai_request_duration_seconds',
            'AI request latency in seconds',
            ['model_name', 'endpoint'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        )
        
        self.ttft_histogram = Histogram(
            'ai_time_to_first_token_seconds',
            'Time to first token in seconds',
            ['model_name'],
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        
        # 量表指標
        self.active_requests = Gauge(
            'ai_active_requests',
            'Number of active AI requests',
            ['model_name']
        )
        
        self.model_quality_score = Gauge(
            'ai_model_quality_score',
            'Model quality score (0-1)',
            ['model_name', 'metric_type']
        )
        
        self.gpu_utilization = Gauge(
            'ai_gpu_utilization_percent',
            'GPU utilization percentage',
            ['gpu_id', 'model_name']
        )
    
    def setup_logging(self):
        """設定結構化日誌"""
        
        self.logger = logging.getLogger(self.service_name)
        self.logger.setLevel(logging.INFO)
        
        # JSON 格式處理器
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "service": "%(name)s", '
            '"level": "%(levelname)s", "message": "%(message)s", '
            '"trace_id": "%(trace_id)s", "span_id": "%(span_id)s"}'
        )
        
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def track_ai_request(self, model_name: str, endpoint: str, func):
        """AI 請求追蹤裝飾器"""
        
        def decorator(*args, **kwargs):
            # 增加活躍請求計數
            self.active_requests.labels(model_name=model_name).inc()
            
            with self.tracer.start_as_current_span(
                f"{self.service_name}.{endpoint}",
                attributes={
                    "ai.model.name": model_name,
                    "ai.endpoint": endpoint,
                    "ai.service": self.service_name
                }
            ) as span:
                start_time = time.time()
                
                try:
                    # 執行實際函數
                    result = func(*args, **kwargs)
                    
                    # 記錄成功指標
                    duration = time.time() - start_time
                    
                    self.request_counter.labels(
                        model_name=model_name,
                        endpoint=endpoint,
                        status='success'
                    ).inc()
                    
                    self.latency_histogram.labels(
                        model_name=model_name,
                        endpoint=endpoint
                    ).observe(duration)
                    
                    # 添加追蹤屬性
                    span.set_attributes({
                        "ai.response.success": True,
                        "ai.response.duration": duration,
                        "ai.tokens.input": result.get('input_tokens', 0),
                        "ai.tokens.output": result.get('output_tokens', 0)
                    })
                    
                    # 記錄 token 使用
                    if 'input_tokens' in result:
                        self.token_counter.labels(
                            model_name=model_name,
                            token_type='input'
                        ).inc(result['input_tokens'])
                    
                    if 'output_tokens' in result:
                        self.token_counter.labels(
                            model_name=model_name,
                            token_type='output'
                        ).inc(result['output_tokens'])
                    
                    return result
                    
                except Exception as e:
                    # 記錄錯誤指標
                    self.request_counter.labels(
                        model_name=model_name,
                        endpoint=endpoint,
                        status='error'
                    ).inc()
                    
                    span.set_attributes({
                        "ai.response.success": False,
                        "ai.error.type": type(e).__name__,
                        "ai.error.message": str(e)
                    })
                    
                    self.logger.error(
                        f"AI request failed: {e}",
                        extra={
                            "trace_id": span.get_span_context().trace_id,
                            "span_id": span.get_span_context().span_id,
                            "model_name": model_name,
                            "endpoint": endpoint
                        }
                    )
                    
                    raise
                
                finally:
                    # 減少活躍請求計數
                    self.active_requests.labels(model_name=model_name).dec()
        
        return decorator
    
    def update_quality_metrics(self, model_name: str, quality_scores: Dict):
        """更新品質指標"""
        
        for metric_type, score in quality_scores.items():
            self.model_quality_score.labels(
                model_name=model_name,
                metric_type=metric_type
            ).set(score)
    
    def update_gpu_metrics(self, gpu_metrics: Dict):
        """更新 GPU 指標"""
        
        for gpu_id, metrics in gpu_metrics.items():
            self.gpu_utilization.labels(
                gpu_id=gpu_id,
                model_name=metrics.get('model_name', 'unknown')
            ).set(metrics['utilization_percent'])

# 使用範例
observability = AISystemObservability("ai-inference-service")

@observability.track_ai_request("gpt-4", "chat_completion")
def generate_response(prompt: str) -> Dict:
    # 模擬 AI 推理
    time.sleep(1.2)
    
    return {
        'response': 'Generated response',
        'input_tokens': 50,
        'output_tokens': 100,
        'model_version': '1.0.0'
    }
```

### 分散式追蹤與日誌聚合

**Jaeger + ELK Stack 整合：**
```python
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import elasticsearch
from datetime import datetime
import json

class DistributedTraceManager:
    def __init__(self, jaeger_endpoint: str, elasticsearch_host: str):
        self.setup_jaeger_tracing(jaeger_endpoint)
        self.setup_elasticsearch_logging(elasticsearch_host)
        
    def setup_jaeger_tracing(self, endpoint: str):
        """設定 Jaeger 分散式追蹤"""
        
        # 配置 Jaeger 導出器
        jaeger_exporter = JaegerExporter(
            agent_host_name="localhost",
            agent_port=14268,
            collector_endpoint=endpoint,
        )
        
        # 設定追蹤提供者
        trace.set_tracer_provider(TracerProvider())
        tracer = trace.get_tracer(__name__)
        
        # 添加批次處理器
        span_processor = BatchSpanProcessor(jaeger_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)
        
        self.tracer = tracer
    
    def setup_elasticsearch_logging(self, host: str):
        """設定 Elasticsearch 日誌聚合"""
        
        self.es_client = elasticsearch.Elasticsearch([host])
        
        # 創建索引映射
        index_mapping = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "service_name": {"type": "keyword"},
                    "trace_id": {"type": "keyword"},
                    "span_id": {"type": "keyword"},
                    "level": {"type": "keyword"},
                    "message": {"type": "text"},
                    "model_name": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "duration": {"type": "float"},
                    "error_type": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "request_size": {"type": "integer"},
                    "response_size": {"type": "integer"}
                }
            }
        }
        
        index_name = f"ai-logs-{datetime.now().strftime('%Y-%m')}"
        
        try:
            if not self.es_client.indices.exists(index=index_name):
                self.es_client.indices.create(index=index_name, body=index_mapping)
        except Exception as e:
            print(f"Failed to create Elasticsearch index: {e}")
    
    def log_ai_operation(self, operation_type: str, details: Dict):
        """記錄 AI 操作到 Elasticsearch"""
        
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service_name": "ai-service",
            "trace_id": format(span_context.trace_id, '032x'),
            "span_id": format(span_context.span_id, '016x'),
            "operation_type": operation_type,
            **details
        }
        
        index_name = f"ai-logs-{datetime.now().strftime('%Y-%m')}"
        
        try:
            self.es_client.index(index=index_name, body=log_entry)
        except Exception as e:
            print(f"Failed to log to Elasticsearch: {e}")
    
    def create_distributed_span(self, operation_name: str, model_name: str):
        """創建分散式追蹤 span"""
        
        return self.tracer.start_as_current_span(
            operation_name,
            attributes={
                "ai.model.name": model_name,
                "ai.operation": operation_name,
                "service.name": "ai-inference"
            }
        )
    
    def search_logs(self, query: Dict, time_range: Optional[Dict] = None) -> List[Dict]:
        """搜尋日誌"""
        
        search_body = {
            "query": {
                "bool": {
                    "must": [query]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 100
        }
        
        if time_range:
            search_body["query"]["bool"]["must"].append({
                "range": {
                    "timestamp": time_range
                }
            })
        
        try:
            response = self.es_client.search(
                index="ai-logs-*",
                body=search_body
            )
            
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Failed to search logs: {e}")
            return []
    
    def analyze_error_patterns(self, time_window: str = "1h") -> Dict:
        """分析錯誤模式"""
        
        aggregation_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "error_type"}},
                        {"range": {"timestamp": {"gte": f"now-{time_window}"}}}
                    ]
                }
            },
            "aggs": {
                "error_types": {
                    "terms": {"field": "error_type"},
                    "aggs": {
                        "models": {
                            "terms": {"field": "model_name"}
                        },
                        "endpoints": {
                            "terms": {"field": "endpoint"}
                        }
                    }
                },
                "error_timeline": {
                    "date_histogram": {
                        "field": "timestamp",
                        "interval": "5m"
                    }
                }
            }
        }
        
        try:
            response = self.es_client.search(
                index="ai-logs-*",
                body=aggregation_query
            )
            
            return {
                "error_types": response["aggregations"]["error_types"]["buckets"],
                "timeline": response["aggregations"]["error_timeline"]["buckets"]
            }
        except Exception as e:
            print(f"Failed to analyze error patterns: {e}")
            return {}
```

## 3. 智能故障診斷與自動恢復

### 故障檢測系統

**多層次異常檢測：**
```python
import numpy as np
from scipy import stats
from sklearn.ensemble import IsolationForest
from typing import Dict, List, Tuple
from collections import defaultdict, deque
import time

class IntelligentFaultDetector:
    def __init__(self):
        self.metric_history = defaultdict(lambda: deque(maxlen=1000))
        self.anomaly_detectors = {}
        self.alert_rules = []
        self.incident_tracker = {}
        
    def register_metric_stream(self, metric_name: str, detection_method: str = "statistical"):
        """註冊指標流監控"""
        
        if detection_method == "statistical":
            self.anomaly_detectors[metric_name] = StatisticalAnomalyDetector()
        elif detection_method == "isolation_forest":
            self.anomaly_detectors[metric_name] = MLAnomalyDetector()
        elif detection_method == "threshold":
            self.anomaly_detectors[metric_name] = ThresholdAnomalyDetector()
    
    def add_alert_rule(self, rule: Dict):
        """添加告警規則"""
        self.alert_rules.append(rule)
    
    def process_metric(self, metric_name: str, value: float, timestamp: float, 
                      context: Dict = None) -> List[Dict]:
        """處理指標並檢測異常"""
        
        # 記錄歷史數據
        self.metric_history[metric_name].append({
            'value': value,
            'timestamp': timestamp,
            'context': context or {}
        })
        
        alerts = []
        
        # 執行異常檢測
        if metric_name in self.anomaly_detectors:
            detector = self.anomaly_detectors[metric_name]
            
            # 獲取歷史數據
            historical_values = [
                point['value'] for point in self.metric_history[metric_name]
            ]
            
            is_anomaly, anomaly_score, explanation = detector.detect_anomaly(
                current_value=value,
                historical_values=historical_values[-100:],  # 最近 100 個點
                context=context
            )
            
            if is_anomaly:
                alert = self._create_anomaly_alert(
                    metric_name=metric_name,
                    value=value,
                    timestamp=timestamp,
                    anomaly_score=anomaly_score,
                    explanation=explanation,
                    context=context
                )
                alerts.append(alert)
        
        # 檢查規則告警
        rule_alerts = self._check_alert_rules(metric_name, value, timestamp, context)
        alerts.extend(rule_alerts)
        
        # 更新事件追蹤
        self._update_incident_tracking(alerts)
        
        return alerts
    
    def _create_anomaly_alert(self, metric_name: str, value: float, timestamp: float,
                            anomaly_score: float, explanation: str, context: Dict) -> Dict:
        """創建異常告警"""
        
        severity = self._calculate_severity(anomaly_score, context)
        
        return {
            'type': 'anomaly',
            'metric_name': metric_name,
            'current_value': value,
            'anomaly_score': anomaly_score,
            'severity': severity,
            'timestamp': timestamp,
            'explanation': explanation,
            'context': context,
            'alert_id': f"anomaly_{metric_name}_{int(timestamp)}"
        }
    
    def _check_alert_rules(self, metric_name: str, value: float, 
                          timestamp: float, context: Dict) -> List[Dict]:
        """檢查告警規則"""
        
        alerts = []
        
        for rule in self.alert_rules:
            if rule['metric'] == metric_name:
                if self._evaluate_rule_condition(rule, value, context):
                    alert = {
                        'type': 'rule',
                        'rule_name': rule['name'],
                        'metric_name': metric_name,
                        'current_value': value,
                        'threshold': rule['threshold'],
                        'severity': rule['severity'],
                        'timestamp': timestamp,
                        'message': rule['message'].format(value=value),
                        'context': context,
                        'alert_id': f"rule_{rule['name']}_{int(timestamp)}"
                    }
                    alerts.append(alert)
        
        return alerts
    
    def _evaluate_rule_condition(self, rule: Dict, value: float, context: Dict) -> bool:
        """評估規則條件"""
        
        condition_type = rule['condition']
        threshold = rule['threshold']
        
        if condition_type == 'greater_than':
            return value > threshold
        elif condition_type == 'less_than':
            return value < threshold
        elif condition_type == 'equals':
            return abs(value - threshold) < 0.001
        elif condition_type == 'not_equals':
            return abs(value - threshold) >= 0.001
        elif condition_type == 'percentage_increase':
            # 需要歷史數據比較
            historical_avg = self._get_historical_average(rule['metric'], window=rule.get('window', 300))
            if historical_avg:
                increase = (value - historical_avg) / historical_avg
                return increase > threshold
        
        return False
    
    def _calculate_severity(self, anomaly_score: float, context: Dict) -> str:
        """計算告警嚴重程度"""
        
        # 基於異常分數
        if anomaly_score > 0.9:
            base_severity = 'critical'
        elif anomaly_score > 0.7:
            base_severity = 'high'
        elif anomaly_score > 0.5:
            base_severity = 'medium'
        else:
            base_severity = 'low'
        
        # 考慮業務影響
        if context.get('business_impact') == 'high':
            if base_severity in ['medium', 'low']:
                base_severity = 'high'
        
        return base_severity
    
    def _update_incident_tracking(self, alerts: List[Dict]):
        """更新事件追蹤"""
        
        for alert in alerts:
            alert_id = alert['alert_id']
            
            if alert_id not in self.incident_tracker:
                self.incident_tracker[alert_id] = {
                    'first_occurrence': alert['timestamp'],
                    'last_occurrence': alert['timestamp'],
                    'count': 1,
                    'status': 'open',
                    'alert_data': alert
                }
            else:
                self.incident_tracker[alert_id]['last_occurrence'] = alert['timestamp']
                self.incident_tracker[alert_id]['count'] += 1
    
    def get_active_incidents(self) -> List[Dict]:
        """獲取活躍事件"""
        
        active_incidents = []
        current_time = time.time()
        
        for incident_id, incident in self.incident_tracker.items():
            if (incident['status'] == 'open' and 
                current_time - incident['last_occurrence'] < 3600):  # 1小時內
                active_incidents.append(incident)
        
        return active_incidents
    
    def resolve_incident(self, incident_id: str, resolution_note: str = ""):
        """解決事件"""
        
        if incident_id in self.incident_tracker:
            self.incident_tracker[incident_id]['status'] = 'resolved'
            self.incident_tracker[incident_id]['resolution_time'] = time.time()
            self.incident_tracker[incident_id]['resolution_note'] = resolution_note

class StatisticalAnomalyDetector:
    def __init__(self, zscore_threshold: float = 3.0):
        self.zscore_threshold = zscore_threshold
    
    def detect_anomaly(self, current_value: float, historical_values: List[float], 
                      context: Dict = None) -> Tuple[bool, float, str]:
        """統計異常檢測"""
        
        if len(historical_values) < 10:
            return False, 0.0, "Insufficient data for statistical analysis"
        
        # 計算 Z-score
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        
        if std == 0:
            return False, 0.0, "No variation in historical data"
        
        zscore = abs(current_value - mean) / std
        is_anomaly = zscore > self.zscore_threshold
        
        # 正規化異常分數
        anomaly_score = min(zscore / (self.zscore_threshold * 2), 1.0)
        
        explanation = f"Z-score: {zscore:.2f}, Mean: {mean:.2f}, Std: {std:.2f}"
        
        return is_anomaly, anomaly_score, explanation

class MLAnomalyDetector:
    def __init__(self):
        self.isolation_forest = IsolationForest(contamination=0.1, random_state=42)
        self.trained = False
    
    def detect_anomaly(self, current_value: float, historical_values: List[float], 
                      context: Dict = None) -> Tuple[bool, float, str]:
        """機器學習異常檢測"""
        
        if len(historical_values) < 50:
            return False, 0.0, "Insufficient data for ML analysis"
        
        # 準備訓練數據
        X = np.array(historical_values).reshape(-1, 1)
        
        # 訓練模型（如果尚未訓練或需要更新）
        if not self.trained or len(historical_values) % 100 == 0:
            self.isolation_forest.fit(X)
            self.trained = True
        
        # 檢測當前值
        current_X = np.array([[current_value]])
        anomaly_score = self.isolation_forest.decision_function(current_X)[0]
        prediction = self.isolation_forest.predict(current_X)[0]
        
        is_anomaly = prediction == -1
        
        # 轉換異常分數到 0-1 範圍
        normalized_score = 1.0 / (1.0 + np.exp(anomaly_score))
        
        explanation = f"Isolation Forest score: {anomaly_score:.3f}"
        
        return is_anomaly, normalized_score, explanation

class ThresholdAnomalyDetector:
    def __init__(self, upper_threshold: Optional[float] = None, 
                 lower_threshold: Optional[float] = None):
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold
    
    def detect_anomaly(self, current_value: float, historical_values: List[float], 
                      context: Dict = None) -> Tuple[bool, float, str]:
        """閾值異常檢測"""
        
        is_anomaly = False
        explanation_parts = []
        
        if self.upper_threshold is not None and current_value > self.upper_threshold:
            is_anomaly = True
            explanation_parts.append(f"Above upper threshold: {current_value} > {self.upper_threshold}")
        
        if self.lower_threshold is not None and current_value < self.lower_threshold:
            is_anomaly = True
            explanation_parts.append(f"Below lower threshold: {current_value} < {self.lower_threshold}")
        
        # 計算與閾值的距離作為異常分數
        anomaly_score = 0.0
        if is_anomaly:
            if self.upper_threshold is not None and current_value > self.upper_threshold:
                anomaly_score = min((current_value - self.upper_threshold) / self.upper_threshold, 1.0)
            elif self.lower_threshold is not None and current_value < self.lower_threshold:
                anomaly_score = min((self.lower_threshold - current_value) / abs(self.lower_threshold), 1.0)
        
        explanation = "; ".join(explanation_parts) if explanation_parts else "Within thresholds"
        
        return is_anomaly, anomaly_score, explanation
```

### 自動恢復機制

**智能自愈系統：**
```python
import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Callable

class RecoveryAction(Enum):
    RESTART_SERVICE = "restart_service"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    SWITCH_MODEL = "switch_model"
    CLEAR_CACHE = "clear_cache"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CIRCUIT_BREAK = "circuit_break"

class AutoRecoverySystem:
    def __init__(self):
        self.recovery_strategies = {}
        self.execution_history = deque(maxlen=100)
        self.circuit_breakers = {}
        self.recovery_locks = {}
        
    def register_recovery_strategy(self, failure_pattern: str, strategy: 'RecoveryStrategy'):
        """註冊恢復策略"""
        self.recovery_strategies[failure_pattern] = strategy
    
    async def handle_failure(self, failure_context: Dict) -> Dict:
        """處理故障"""
        
        failure_type = self._classify_failure(failure_context)
        
        # 檢查是否有匹配的恢復策略
        strategy = self._match_recovery_strategy(failure_type, failure_context)
        
        if not strategy:
            return {
                'success': False,
                'reason': 'No matching recovery strategy found',
                'failure_type': failure_type
            }
        
        # 檢查恢復鎖避免並發執行同類型恢復
        lock_key = f"{failure_type}_{failure_context.get('service_name', 'unknown')}"
        
        if lock_key in self.recovery_locks:
            return {
                'success': False,
                'reason': 'Recovery already in progress',
                'failure_type': failure_type
            }
        
        # 設定恢復鎖
        self.recovery_locks[lock_key] = True
        
        try:
            # 執行恢復策略
            recovery_result = await strategy.execute(failure_context)
            
            # 記錄執行歷史
            self._record_recovery_execution(failure_context, strategy, recovery_result)
            
            return recovery_result
            
        except Exception as e:
            return {
                'success': False,
                'reason': f'Recovery execution failed: {str(e)}',
                'failure_type': failure_type
            }
        
        finally:
            # 移除恢復鎖
            self.recovery_locks.pop(lock_key, None)
    
    def _classify_failure(self, failure_context: Dict) -> str:
        """分類故障類型"""
        
        # 基於指標和上下文分類故障
        if failure_context.get('metric_name') == 'latency' and failure_context.get('current_value', 0) > 10:
            return 'high_latency'
        elif failure_context.get('metric_name') == 'error_rate' and failure_context.get('current_value', 0) > 0.1:
            return 'high_error_rate'
        elif failure_context.get('metric_name') == 'memory_usage' and failure_context.get('current_value', 0) > 0.9:
            return 'memory_exhaustion'
        elif failure_context.get('metric_name') == 'cpu_usage' and failure_context.get('current_value', 0) > 0.9:
            return 'cpu_exhaustion'
        elif 'connection' in str(failure_context.get('error_message', '')).lower():
            return 'connection_failure'
        elif 'timeout' in str(failure_context.get('error_message', '')).lower():
            return 'timeout_failure'
        else:
            return 'unknown_failure'
    
    def _match_recovery_strategy(self, failure_type: str, failure_context: Dict) -> Optional['RecoveryStrategy']:
        """匹配恢復策略"""
        
        # 直接匹配
        if failure_type in self.recovery_strategies:
            return self.recovery_strategies[failure_type]
        
        # 模式匹配
        for pattern, strategy in self.recovery_strategies.items():
            if pattern in failure_type or failure_type in pattern:
                return strategy
        
        return None
    
    def _record_recovery_execution(self, failure_context: Dict, strategy: 'RecoveryStrategy', result: Dict):
        """記錄恢復執行歷史"""
        
        execution_record = {
            'timestamp': time.time(),
            'failure_context': failure_context,
            'strategy_name': strategy.__class__.__name__,
            'result': result,
            'success': result.get('success', False)
        }
        
        self.execution_history.append(execution_record)

class RecoveryStrategy(ABC):
    def __init__(self, name: str, max_retries: int = 3, retry_delay: float = 5.0):
        self.name = name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    @abstractmethod
    async def execute(self, failure_context: Dict) -> Dict:
        """執行恢復動作"""
        pass
    
    async def _retry_with_backoff(self, action: Callable, max_retries: int = None) -> bool:
        """帶退避的重試機制"""
        
        retries = max_retries or self.max_retries
        
        for attempt in range(retries):
            try:
                await action()
                return True
            except Exception as e:
                if attempt < retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)  # 指數退避
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        
        return False

class ServiceRestartStrategy(RecoveryStrategy):
    def __init__(self, service_manager):
        super().__init__("ServiceRestart")
        self.service_manager = service_manager
    
    async def execute(self, failure_context: Dict) -> Dict:
        """重啟服務恢復策略"""
        
        service_name = failure_context.get('service_name')
        
        if not service_name:
            return {
                'success': False,
                'reason': 'Service name not provided in failure context'
            }
        
        try:
            # 停止服務
            await self.service_manager.stop_service(service_name)
            
            # 等待一段時間
            await asyncio.sleep(2)
            
            # 重新啟動服務
            await self.service_manager.start_service(service_name)
            
            # 驗證服務健康狀態
            health_check_passed = await self._retry_with_backoff(
                lambda: self.service_manager.check_service_health(service_name)
            )
            
            if health_check_passed:
                return {
                    'success': True,
                    'action': RecoveryAction.RESTART_SERVICE.value,
                    'service_name': service_name,
                    'message': f'Successfully restarted service {service_name}'
                }
            else:
                return {
                    'success': False,
                    'reason': f'Service {service_name} restart failed health check'
                }
                
        except Exception as e:
            return {
                'success': False,
                'reason': f'Failed to restart service {service_name}: {str(e)}'
            }

class AutoScalingStrategy(RecoveryStrategy):
    def __init__(self, scaling_manager):
        super().__init__("AutoScaling")
        self.scaling_manager = scaling_manager
    
    async def execute(self, failure_context: Dict) -> Dict:
        """自動擴展恢復策略"""
        
        service_name = failure_context.get('service_name')
        metric_name = failure_context.get('metric_name')
        current_value = failure_context.get('current_value', 0)
        
        # 決定擴展方向
        if metric_name in ['cpu_usage', 'memory_usage', 'latency'] and current_value > 0.8:
            scale_direction = 'up'
            scale_factor = 1.5
        elif metric_name == 'request_rate' and current_value > 1000:
            scale_direction = 'up'
            scale_factor = 2.0
        else:
            return {
                'success': False,
                'reason': 'No scaling decision could be made based on metrics'
            }
        
        try:
            if scale_direction == 'up':
                result = await self.scaling_manager.scale_up(service_name, scale_factor)
                action = RecoveryAction.SCALE_UP
            else:
                result = await self.scaling_manager.scale_down(service_name, scale_factor)
                action = RecoveryAction.SCALE_DOWN
            
            return {
                'success': True,
                'action': action.value,
                'service_name': service_name,
                'scale_factor': scale_factor,
                'new_instance_count': result.get('new_instance_count'),
                'message': f'Successfully scaled {scale_direction} service {service_name}'
            }
            
        except Exception as e:
            return {
                'success': False,
                'reason': f'Failed to scale service {service_name}: {str(e)}'
            }

class ModelSwitchStrategy(RecoveryStrategy):
    def __init__(self, model_manager):
        super().__init__("ModelSwitch")
        self.model_manager = model_manager
    
    async def execute(self, failure_context: Dict) -> Dict:
        """模型切換恢復策略"""
        
        current_model = failure_context.get('model_name')
        service_name = failure_context.get('service_name')
        
        if not current_model:
            return {
                'success': False,
                'reason': 'Current model name not provided in failure context'
            }
        
        # 獲取備用模型
        fallback_models = await self.model_manager.get_fallback_models(current_model)
        
        if not fallback_models:
            return {
                'success': False,
                'reason': f'No fallback models available for {current_model}'
            }
        
        # 嘗試切換到每個備用模型
        for fallback_model in fallback_models:
            try:
                # 執行模型切換
                await self.model_manager.switch_model(service_name, fallback_model)
                
                # 驗證新模型健康狀態
                health_check_passed = await self._retry_with_backoff(
                    lambda: self.model_manager.check_model_health(fallback_model)
                )
                
                if health_check_passed:
                    return {
                        'success': True,
                        'action': RecoveryAction.SWITCH_MODEL.value,
                        'original_model': current_model,
                        'fallback_model': fallback_model,
                        'service_name': service_name,
                        'message': f'Successfully switched from {current_model} to {fallback_model}'
                    }
                    
            except Exception as e:
                continue  # 嘗試下一個備用模型
        
        return {
            'success': False,
            'reason': f'Failed to switch to any fallback model for {current_model}'
        }

# 使用範例
async def setup_auto_recovery():
    recovery_system = AutoRecoverySystem()
    
    # 註冊恢復策略
    recovery_system.register_recovery_strategy(
        'high_latency',
        AutoScalingStrategy(scaling_manager)
    )
    
    recovery_system.register_recovery_strategy(
        'high_error_rate',
        ModelSwitchStrategy(model_manager)
    )
    
    recovery_system.register_recovery_strategy(
        'connection_failure',
        ServiceRestartStrategy(service_manager)
    )
    
    return recovery_system
```

## 4. 成本最佳化與資源管理

### 智能成本控制

**動態資源分配與成本監控：**
```python
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import numpy as np
from datetime import datetime, timedelta

class ResourceType(Enum):
    GPU = "gpu"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"

@dataclass
class ResourceUsage:
    resource_type: ResourceType
    used: float
    total: float
    cost_per_unit: float
    timestamp: datetime
    model_name: str
    service_name: str

@dataclass
class CostOptimizationRecommendation:
    action_type: str  # scale_down, switch_instance_type, schedule_shutdown
    estimated_savings: float  # 每月預估節省金額
    impact_assessment: str  # 對效能的影響評估
    confidence_score: float  # 建議信心分數
    implementation_details: Dict

class IntelligentCostOptimizer:
    def __init__(self):
        self.resource_usage_history = {}
        self.cost_models = {}
        self.optimization_rules = []
        self.budget_limits = {}
        
    def register_cost_model(self, resource_type: ResourceType, cost_function: Callable):
        """註冊成本計算模型"""
        self.cost_models[resource_type] = cost_function
    
    def set_budget_limit(self, service_name: str, monthly_budget: float):
        """設定服務預算限制"""
        self.budget_limits[service_name] = monthly_budget
    
    def track_resource_usage(self, usage: ResourceUsage):
        """追蹤資源使用情況"""
        key = f"{usage.service_name}_{usage.model_name}_{usage.resource_type.value}"
        
        if key not in self.resource_usage_history:
            self.resource_usage_history[key] = deque(maxlen=1000)
        
        self.resource_usage_history[key].append(usage)
    
    def calculate_current_costs(self, time_window: timedelta = timedelta(hours=24)) -> Dict:
        """計算當前成本"""
        
        current_time = datetime.now()
        cutoff_time = current_time - time_window
        
        cost_breakdown = {}
        
        for key, usage_history in self.resource_usage_history.items():
            service_name, model_name, resource_type = key.split('_')
            
            # 篩選時間窗口內的使用數據
            recent_usage = [
                usage for usage in usage_history 
                if usage.timestamp >= cutoff_time
            ]
            
            if not recent_usage:
                continue
            
            # 計算平均使用量
            avg_usage = np.mean([usage.used for usage in recent_usage])
            cost_per_unit = recent_usage[-1].cost_per_unit
            
            # 計算時間窗口內的總成本
            hours_in_window = time_window.total_seconds() / 3600
            total_cost = avg_usage * cost_per_unit * hours_in_window
            
            # 組織成本分解
            if service_name not in cost_breakdown:
                cost_breakdown[service_name] = {}
            
            if model_name not in cost_breakdown[service_name]:
                cost_breakdown[service_name][model_name] = {}
            
            cost_breakdown[service_name][model_name][resource_type] = {
                'usage': avg_usage,
                'cost_per_unit': cost_per_unit,
                'total_cost': total_cost
            }
        
        return cost_breakdown
    
    def analyze_cost_patterns(self, service_name: str) -> Dict:
        """分析成本模式"""
        
        patterns = {
            'hourly_distribution': self._analyze_hourly_cost_distribution(service_name),
            'weekly_trend': self._analyze_weekly_cost_trend(service_name),
            'resource_efficiency': self._analyze_resource_efficiency(service_name),
            'cost_drivers': self._identify_cost_drivers(service_name)
        }
        
        return patterns
    
    def generate_optimization_recommendations(self, service_name: str) -> List[CostOptimizationRecommendation]:
        """生成成本最佳化建議"""
        
        recommendations = []
        
        # 分析資源使用模式
        patterns = self.analyze_cost_patterns(service_name)
        
        # 1. 閒置資源檢測
        idle_recommendations = self._detect_idle_resources(service_name, patterns)
        recommendations.extend(idle_recommendations)
        
        # 2. 過度配置檢測
        overprovisioning_recommendations = self._detect_overprovisioning(service_name, patterns)
        recommendations.extend(overprovisioning_recommendations)
        
        # 3. 時間排程最佳化
        scheduling_recommendations = self._optimize_scheduling(service_name, patterns)
        recommendations.extend(scheduling_recommendations)
        
        # 4. 實例類型最佳化
        instance_recommendations = self._optimize_instance_types(service_name, patterns)
        recommendations.extend(instance_recommendations)
        
        # 按預估節省金額排序
        recommendations.sort(key=lambda x: x.estimated_savings, reverse=True)
        
        return recommendations
    
    def _analyze_hourly_cost_distribution(self, service_name: str) -> Dict:
        """分析每小時成本分佈"""
        
        hourly_costs = defaultdict(list)
        
        for key, usage_history in self.resource_usage_history.items():
            if not key.startswith(service_name):
                continue
            
            for usage in usage_history:
                hour = usage.timestamp.hour
                cost = usage.used * usage.cost_per_unit
                hourly_costs[hour].append(cost)
        
        # 計算每小時平均成本
        hourly_avg = {
            hour: np.mean(costs) for hour, costs in hourly_costs.items()
        }
        
        return {
            'hourly_average': hourly_avg,
            'peak_hours': sorted(hourly_avg.keys(), key=lambda h: hourly_avg[h], reverse=True)[:3],
            'low_usage_hours': sorted(hourly_avg.keys(), key=lambda h: hourly_avg[h])[:3]
        }
    
    def _detect_idle_resources(self, service_name: str, patterns: Dict) -> List[CostOptimizationRecommendation]:
        """檢測閒置資源"""
        
        recommendations = []
        
        # 檢查低使用時段
        low_usage_hours = patterns['hourly_distribution']['low_usage_hours']
        
        if len(low_usage_hours) >= 6:  # 如果有6小時或更多的低使用時段
            # 計算潛在節省
            current_hourly_cost = self._calculate_average_hourly_cost(service_name)
            potential_savings = current_hourly_cost * len(low_usage_hours) * 30  # 每月
            
            recommendation = CostOptimizationRecommendation(
                action_type="schedule_shutdown",
                estimated_savings=potential_savings,
                impact_assessment="Minimal impact during low-usage hours",
                confidence_score=0.8,
                implementation_details={
                    "shutdown_hours": low_usage_hours,
                    "automation_script": "schedule_auto_shutdown.py",
                    "wake_up_trigger": "demand_based"
                }
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def _detect_overprovisioning(self, service_name: str, patterns: Dict) -> List[CostOptimizationRecommendation]:
        """檢測過度配置"""
        
        recommendations = []
        efficiency = patterns['resource_efficiency']
        
        for resource_type, efficiency_score in efficiency.items():
            if efficiency_score < 0.6:  # 效率低於60%
                
                # 建議縮減配置
                current_cost = self._get_current_resource_cost(service_name, resource_type)
                potential_savings = current_cost * (1 - efficiency_score) * 0.8  # 保守估計
                
                recommendation = CostOptimizationRecommendation(
                    action_type="scale_down",
                    estimated_savings=potential_savings,
                    impact_assessment=f"Low impact - {resource_type} utilization is only {efficiency_score*100:.1f}%",
                    confidence_score=0.9,
                    implementation_details={
                        "resource_type": resource_type,
                        "current_efficiency": efficiency_score,
                        "recommended_reduction": f"{(1-efficiency_score)*50:.1f}%",
                        "gradual_scaling": True
                    }
                )
                
                recommendations.append(recommendation)
        
        return recommendations
    
    def _optimize_instance_types(self, service_name: str, patterns: Dict) -> List[CostOptimizationRecommendation]:
        """最佳化實例類型"""
        
        recommendations = []
        
        # 分析當前資源使用比例
        resource_usage = patterns['resource_efficiency']
        
        gpu_usage = resource_usage.get('gpu', 0)
        cpu_usage = resource_usage.get('cpu', 0)
        memory_usage = resource_usage.get('memory', 0)
        
        # GPU 最佳化建議
        if gpu_usage < 0.5 and gpu_usage > 0:  # GPU 使用率低但有使用
            current_gpu_cost = self._get_current_resource_cost(service_name, 'gpu')
            
            # 建議使用較小的 GPU 實例
            potential_savings = current_gpu_cost * 0.4  # 假設可節省40%
            
            recommendation = CostOptimizationRecommendation(
                action_type="switch_instance_type",
                estimated_savings=potential_savings,
                impact_assessment="Moderate impact - may increase latency slightly",
                confidence_score=0.7,
                implementation_details={
                    "current_gpu_usage": gpu_usage,
                    "recommended_action": "Switch to smaller GPU instance",
                    "suggested_instance": "g4dn.xlarge instead of g4dn.2xlarge",
                    "rollback_plan": "Monitor latency and scale back if needed"
                }
            )
            
            recommendations.append(recommendation)
        
        # CPU/Memory 比例最佳化
        if abs(cpu_usage - memory_usage) > 0.3:  # CPU 和記憶體使用率差異大
            current_compute_cost = self._get_current_resource_cost(service_name, 'cpu')
            potential_savings = current_compute_cost * 0.15
            
            if cpu_usage > memory_usage:
                instance_type = "CPU-optimized"
            else:
                instance_type = "Memory-optimized"
            
            recommendation = CostOptimizationRecommendation(
                action_type="switch_instance_type",
                estimated_savings=potential_savings,
                impact_assessment="Low impact - better resource alignment",
                confidence_score=0.8,
                implementation_details={
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory_usage,
                    "recommended_instance_type": instance_type,
                    "migration_plan": "Blue-green deployment recommended"
                }
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    async def implement_recommendation(self, recommendation: CostOptimizationRecommendation, 
                                     service_name: str) -> Dict:
        """實施最佳化建議"""
        
        implementation_result = {
            'success': False,
            'action_taken': recommendation.action_type,
            'estimated_savings': recommendation.estimated_savings,
            'actual_impact': None
        }
        
        try:
            if recommendation.action_type == "scale_down":
                result = await self._execute_scale_down(service_name, recommendation.implementation_details)
            elif recommendation.action_type == "schedule_shutdown":
                result = await self._execute_scheduled_shutdown(service_name, recommendation.implementation_details)
            elif recommendation.action_type == "switch_instance_type":
                result = await self._execute_instance_switch(service_name, recommendation.implementation_details)
            else:
                result = {'success': False, 'reason': 'Unsupported action type'}
            
            implementation_result.update(result)
            
        except Exception as e:
            implementation_result['error'] = str(e)
        
        return implementation_result
    
    def monitor_budget_usage(self) -> Dict:
        """監控預算使用情況"""
        
        budget_status = {}
        current_month_costs = self.calculate_current_costs(timedelta(days=30))
        
        for service_name, budget_limit in self.budget_limits.items():
            if service_name in current_month_costs:
                total_service_cost = sum(
                    sum(model_costs.values()) if isinstance(model_costs, dict) 
                    else model_costs
                    for model_costs in current_month_costs[service_name].values()
                )
                
                usage_percentage = (total_service_cost / budget_limit) * 100
                
                budget_status[service_name] = {
                    'budget_limit': budget_limit,
                    'current_spend': total_service_cost,
                    'usage_percentage': usage_percentage,
                    'remaining_budget': budget_limit - total_service_cost,
                    'alert_level': self._get_budget_alert_level(usage_percentage)
                }
        
        return budget_status
    
    def _get_budget_alert_level(self, usage_percentage: float) -> str:
        """獲取預算告警級別"""
        
        if usage_percentage >= 95:
            return 'critical'
        elif usage_percentage >= 80:
            return 'warning'
        elif usage_percentage >= 70:
            return 'watch'
        else:
            return 'normal'

# 使用範例
async def setup_cost_optimization():
    optimizer = IntelligentCostOptimizer()
    
    # 設定預算限制
    optimizer.set_budget_limit("ai-inference-service", 10000)  # $10,000/月
    optimizer.set_budget_limit("model-training-service", 5000)  # $5,000/月
    
    # 定期生成最佳化建議
    while True:
        services = ["ai-inference-service", "model-training-service"]
        
        for service in services:
            recommendations = optimizer.generate_optimization_recommendations(service)
            
            # 自動實施低風險建議
            for recommendation in recommendations:
                if (recommendation.confidence_score > 0.8 and 
                    recommendation.estimated_savings > 100):  # 節省超過$100
                    
                    print(f"Implementing optimization for {service}: {recommendation.action_type}")
                    result = await optimizer.implement_recommendation(recommendation, service)
                    print(f"Implementation result: {result}")
        
        # 檢查預算狀態
        budget_status = optimizer.monitor_budget_usage()
        
        for service, status in budget_status.items():
            if status['alert_level'] in ['warning', 'critical']:
                print(f"Budget alert for {service}: {status['usage_percentage']:.1f}% used")
        
        # 每小時檢查一次
        await asyncio.sleep(3600)
```

## 總結

本文深入探討了生產環境 AI 系統監控與最佳化的核心技術：

1. **LLM-native 指標**：時延、品質、成本與可靠性的全方位評估體系
2. **分散式監控**：OpenTelemetry、Prometheus 與 ELK Stack 的企業整合
3. **智能故障診斷**：多層次異常檢測與自動恢復機制
4. **成本最佳化**：動態資源分配、預算控制與智能成本建議

下一篇將完成系列最終篇，專注於客戶協作與問題解決實務，包含需求分析、技術溝通與專案交付管理。

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"content": "Plan 5-part AI FDE blog series structure and topics", "status": "completed", "activeForm": "Planning 5-part AI FDE blog series structure and topics"}, {"content": "Create Part 1: AI FDE \u57fa\u790e\u6838\u5fc3\u6982\u5ff5\u8207\u6280\u8853\u68e7", "status": "completed", "activeForm": "Creating Part 1: AI FDE \u57fa\u790e\u6838\u5fc3\u6982\u5ff5\u8207\u6280\u8853\u68e7"}, {"content": "Create Part 2: \u591a\u667a\u6167\u9ad4\u7cfb\u7d71\u8207\u6846\u67b6\u5be6\u6230", "status": "completed", "activeForm": "Creating Part 2: \u591a\u667a\u6167\u9ad4\u7cfb\u7d71\u8207\u6846\u67b6\u5be6\u6230"}, {"content": "Create Part 3: \u4f01\u696d\u7d1a AI \u6574\u5408\u8207\u90e8\u7f72\u7b56\u7565", "status": "completed", "activeForm": "Creating Part 3: \u4f01\u696d\u7d1a AI \u6574\u5408\u8207\u90e8\u7f72\u7b56\u7565"}, {"content": "Create Part 4: \u751f\u7522\u74b0\u5883 AI \u7cfb\u7d71\u76e3\u63a7\u8207\u6700\u4f73\u5316", "status": "completed", "activeForm": "Creating Part 4: \u751f\u7522\u74b0\u5883 AI \u7cfb\u7d71\u76e3\u63a7\u8207\u6700\u4f73\u5316"}, {"content": "Create Part 5: \u5ba2\u6236\u5354\u4f5c\u8207\u554f\u984c\u89e3\u6c7a\u5be6\u52d9", "status": "in_progress", "activeForm": "Creating Part 5: \u5ba2\u6236\u5354\u4f5c\u8207\u554f\u984c\u89e3\u6c7a\u5be6\u52d9"}]
