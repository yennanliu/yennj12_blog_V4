---
title: "Fine-Tuning LLMs with AWS Bedrock: A Complete Guide to Post-Training Customization"
date: 2025-12-21T11:00:00Z
draft: false
authors: ["yen"]
categories: ["all", "AI", "AWS", "Machine Learning", "MLOps"]
tags: ["AWS Bedrock", "LLM", "fine-tuning", "machine-learning", "AI", "Claude", "Titan", "AWS CDK", "Python", "boto3", "reinforcement-learning"]
summary: "Comprehensive guide to fine-tuning and customizing Large Language Models (LLMs) with AWS Bedrock - covering supervised fine-tuning, continued pre-training, and reinforcement fine-tuning with practical examples and AWS CDK infrastructure setup."
readTime: "28 min"
---

## 🎯 Introduction to LLM Post-Training with AWS Bedrock

### 📋 What is LLM Fine-Tuning?

**Fine-tuning** is the process of taking a pre-trained Large Language Model (LLM) and further training it on your specific dataset to improve its performance for your particular use case. While foundation models like Claude, Titan, or Llama are incredibly capable, they're trained on broad, general data. Fine-tuning allows you to:

- **Improve accuracy** for domain-specific tasks (legal, medical, finance)
- **Adapt writing style** to match your brand voice
- **Enhance performance** on specialized workflows
- **Reduce hallucinations** by grounding responses in your data
- **Optimize for specific formats** (JSON output, structured responses)

### 🚀 Why AWS Bedrock for Fine-Tuning?

**AWS Bedrock** provides a fully managed service for customizing foundation models without needing deep ML expertise or managing infrastructure:

✅ **No Infrastructure Management** - AWS handles compute, storage, and scaling
✅ **Multiple Customization Methods** - Fine-tuning, continued pre-training, reinforcement learning
✅ **Data Privacy** - Your training data never leaves your AWS account or trains other models
✅ **Multiple Model Support** - Amazon Titan, Meta Llama, Cohere Command, and more
✅ **Cost-Effective** - Pay only for training time and inference
✅ **Enterprise Security** - Customer managed keys, VPC endpoints, IAM integration

### 🎯 Recent Updates (December 2025)

Amazon Bedrock now supports **Reinforcement Fine-Tuning**, delivering **66% accuracy gains** on average over base models. This new capability allows you to:

- Train models with small sets of prompts instead of large labeled datasets
- Use rule-based or AI-based judges to define reward functions
- Optimize for both objective tasks (code generation, math) and subjective tasks (chatbot interactions)

### 🏗️ Three Approaches to Model Customization

```
┌─────────────────────────────────────────────────────────────┐
│                  AWS Bedrock Customization                   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌──────────────┐   ┌──────────────────┐
│  Fine-Tuning  │   │  Continued   │   │  Reinforcement   │
│               │   │ Pre-Training │   │  Fine-Tuning     │
└───────────────┘   └──────────────┘   └──────────────────┘
│                   │                   │
│ Labeled data      │ Unlabeled data    │ Prompt + feedback│
│ Task-specific     │ Domain knowledge  │ Alignment-focused│
│ 100-10K examples  │ Large corpus      │ Small prompt set │
└───────────────────┴──────────────────┴──────────────────┘
```

#### 1. Supervised Fine-Tuning
**Best for:** Task-specific improvements with labeled data
- Provide prompt-completion pairs
- Improves accuracy on specific tasks
- Requires 100-10,000 labeled examples

#### 2. Continued Pre-Training
**Best for:** Domain adaptation with unlabeled data
- Train on domain-specific text corpus
- Model learns domain vocabulary and concepts
- No labels required, just relevant text

#### 3. Reinforcement Fine-Tuning (NEW)
**Best for:** Alignment and preference optimization
- Uses small prompt sets with feedback
- Rule-based or AI-based reward signals
- Ideal for instruction following and safety

## 🚀 Getting Started: Prerequisites and Setup

### 🔧 Prerequisites

**AWS Account Requirements:**
- AWS account with Bedrock access
- IAM permissions for Bedrock, S3, IAM
- Service quota for model customization (request if needed)

**Development Environment:**
- Python 3.9+
- AWS CLI configured
- boto3 SDK
- AWS CDK (for infrastructure as code)

**Knowledge Requirements:**
- Basic understanding of LLMs
- Familiarity with AWS services
- Python programming
- Basic ML concepts

### 📦 Installation and Setup

```bash
# Create project directory
mkdir bedrock-finetuning
cd bedrock-finetuning

# Set up Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install required packages
pip install boto3 pandas jsonlines aws-cdk-lib constructs

# Configure AWS credentials
aws configure
# Enter your AWS Access Key ID, Secret Key, Region (us-east-1), and format (json)

# Verify Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

### 🏗️ Project Structure

```
bedrock-finetuning/
├── data/
│   ├── training/
│   │   ├── training_data.jsonl
│   │   └── validation_data.jsonl
│   └── synthetic/
│       └── generated_samples.jsonl
├── scripts/
│   ├── prepare_data.py
│   ├── start_training.py
│   ├── evaluate_model.py
│   └── inference.py
├── infrastructure/
│   ├── cdk/
│   │   ├── app.py
│   │   ├── bedrock_stack.py
│   │   └── requirements.txt
│   └── config.yaml
├── notebooks/
│   └── data_exploration.ipynb
├── logs/
├── models/
│   └── custom_models/
└── requirements.txt
```

## 💻 Part 1: Data Preparation for Fine-Tuning

### 📝 Data Format Requirements

**For Fine-Tuning (Prompt-Completion Pairs):**

```jsonl
{"prompt": "Classify the sentiment of this review: The product exceeded my expectations!", "completion": "positive"}
{"prompt": "Classify the sentiment of this review: Terrible quality, broke after one day.", "completion": "negative"}
{"prompt": "Classify the sentiment of this review: It's okay, nothing special.", "completion": "neutral"}
```

**For Continued Pre-Training (Raw Text):**

```jsonl
{"text": "Machine learning is a subset of artificial intelligence that focuses on enabling systems to learn from data..."}
{"text": "Neural networks consist of interconnected layers of nodes, where each connection has an associated weight..."}
```

**For Reinforcement Fine-Tuning (Prompts with Multiple Responses):**

```jsonl
{
  "prompt": "Write a Python function to calculate fibonacci numbers",
  "responses": [
    {"text": "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)", "score": 0.6},
    {"text": "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a", "score": 1.0}
  ]
}
```

### 🛠️ Data Preparation Script

**scripts/prepare_data.py:**

```python
#!/usr/bin/env python3
"""
Data preparation script for AWS Bedrock fine-tuning
Validates format, splits data, uploads to S3
"""

import json
import jsonlines
import pandas as pd
import boto3
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BedrockDataPreparator:
    """Prepare and validate training data for Bedrock fine-tuning"""

    def __init__(self, s3_bucket: str, s3_prefix: str = "bedrock-training"):
        self.s3_client = boto3.client('s3')
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix

    def validate_fine_tuning_data(self, data: List[Dict[str, Any]]) -> bool:
        """
        Validate fine-tuning data format

        Requirements:
        - Each record must have 'prompt' and 'completion'
        - Prompt must be non-empty string
        - Completion must be non-empty string
        - Max 10,000 records
        """
        if len(data) > 10000:
            logger.error(f"Dataset has {len(data)} records. Max is 10,000.")
            return False

        for idx, record in enumerate(data):
            # Check required fields
            if 'prompt' not in record or 'completion' not in record:
                logger.error(f"Record {idx} missing 'prompt' or 'completion'")
                return False

            # Check non-empty
            if not record['prompt'] or not record['completion']:
                logger.error(f"Record {idx} has empty prompt or completion")
                return False

            # Check types
            if not isinstance(record['prompt'], str) or not isinstance(record['completion'], str):
                logger.error(f"Record {idx} has non-string prompt or completion")
                return False

            # Check length (recommended)
            if len(record['prompt']) > 2048:
                logger.warning(f"Record {idx} has very long prompt ({len(record['prompt'])} chars)")

            if len(record['completion']) > 2048:
                logger.warning(f"Record {idx} has very long completion ({len(record['completion'])} chars)")

        logger.info(f"✅ Validated {len(data)} training records")
        return True

    def split_data(self, data: List[Dict[str, Any]],
                   train_ratio: float = 0.8) -> tuple:
        """
        Split data into training and validation sets

        Args:
            data: List of training examples
            train_ratio: Proportion for training (default 0.8)

        Returns:
            Tuple of (training_data, validation_data)
        """
        import random
        random.shuffle(data)

        split_idx = int(len(data) * train_ratio)
        train_data = data[:split_idx]
        val_data = data[split_idx:]

        logger.info(f"Split: {len(train_data)} training, {len(val_data)} validation")
        return train_data, val_data

    def save_jsonl(self, data: List[Dict[str, Any]], filepath: str):
        """Save data in JSONL format"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with jsonlines.open(filepath, mode='w') as writer:
            for record in data:
                writer.write(record)

        logger.info(f"Saved {len(data)} records to {filepath}")

    def upload_to_s3(self, local_path: str, s3_key: str) -> str:
        """
        Upload training data to S3

        Returns:
            S3 URI (s3://bucket/key)
        """
        try:
            self.s3_client.upload_file(local_path, self.s3_bucket, s3_key)
            s3_uri = f"s3://{self.s3_bucket}/{s3_key}"
            logger.info(f"Uploaded to {s3_uri}")
            return s3_uri
        except Exception as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise

    def prepare_dataset(self,
                       input_file: str,
                       output_dir: str = "data/training",
                       upload: bool = True) -> Dict[str, str]:
        """
        Complete data preparation pipeline

        Args:
            input_file: Path to raw data file (JSON or JSONL)
            output_dir: Directory for processed data
            upload: Whether to upload to S3

        Returns:
            Dictionary with S3 URIs for train/val data
        """
        logger.info("=" * 60)
        logger.info("Starting Data Preparation Pipeline")
        logger.info("=" * 60)

        # Load data
        logger.info(f"Loading data from {input_file}")
        with open(input_file, 'r') as f:
            if input_file.endswith('.jsonl'):
                data = [json.loads(line) for line in f]
            else:
                data = json.load(f)

        # Validate
        if not self.validate_fine_tuning_data(data):
            raise ValueError("Data validation failed")

        # Split
        train_data, val_data = self.split_data(data)

        # Save locally
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        train_file = f"{output_dir}/train_{timestamp}.jsonl"
        val_file = f"{output_dir}/val_{timestamp}.jsonl"

        self.save_jsonl(train_data, train_file)
        self.save_jsonl(val_data, val_file)

        result = {
            "train_local": train_file,
            "val_local": val_file
        }

        # Upload to S3
        if upload:
            train_s3_key = f"{self.s3_prefix}/train_{timestamp}.jsonl"
            val_s3_key = f"{self.s3_prefix}/val_{timestamp}.jsonl"

            result["train_s3_uri"] = self.upload_to_s3(train_file, train_s3_key)
            result["val_s3_uri"] = self.upload_to_s3(val_file, val_s3_key)

        logger.info("=" * 60)
        logger.info("Data Preparation Complete!")
        logger.info("=" * 60)

        return result


def create_sample_dataset(output_file: str, num_samples: int = 100):
    """
    Create sample sentiment analysis dataset for testing

    Args:
        output_file: Where to save the sample data
        num_samples: Number of samples to generate
    """
    import random

    templates = {
        "positive": [
            "This product is amazing! Highly recommend.",
            "Exceeded all my expectations. Five stars!",
            "Best purchase I've made this year.",
            "Absolutely love it. Will buy again.",
            "Outstanding quality and fast shipping."
        ],
        "negative": [
            "Terrible quality. Don't waste your money.",
            "Broke after one day. Very disappointed.",
            "Worst purchase ever. Asking for refund.",
            "Nothing like the description. Avoid!",
            "Poor quality and slow delivery."
        ],
        "neutral": [
            "It's okay, nothing special.",
            "Does what it's supposed to do.",
            "Average product at average price.",
            "No complaints but not impressed.",
            "Pretty standard, meets expectations."
        ]
    }

    samples = []
    sentiments = list(templates.keys())

    for _ in range(num_samples):
        sentiment = random.choice(sentiments)
        review = random.choice(templates[sentiment])

        samples.append({
            "prompt": f"Classify the sentiment of this review: {review}",
            "completion": sentiment
        })

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with jsonlines.open(output_file, mode='w') as writer:
        writer.writeall(samples)

    logger.info(f"Created {num_samples} sample records in {output_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare data for Bedrock fine-tuning")
    parser.add_argument("--input", required=True, help="Input data file")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", default="bedrock-training", help="S3 prefix")
    parser.add_argument("--output-dir", default="data/training", help="Output directory")
    parser.add_argument("--no-upload", action="store_true", help="Skip S3 upload")

    args = parser.parse_args()

    # Prepare data
    preparator = BedrockDataPreparator(
        s3_bucket=args.bucket,
        s3_prefix=args.prefix
    )

    result = preparator.prepare_dataset(
        input_file=args.input,
        output_dir=args.output_dir,
        upload=not args.no_upload
    )

    print("\n✅ Data preparation complete!")
    print(f"Training data: {result['train_s3_uri']}")
    print(f"Validation data: {result['val_s3_uri']}")
```

## 💻 Part 2: Fine-Tuning Job Execution

### 🚀 Starting a Fine-Tuning Job

**scripts/start_training.py:**

```python
#!/usr/bin/env python3
"""
Start AWS Bedrock fine-tuning job
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BedrockFineTuner:
    """Manage Bedrock model fine-tuning jobs"""

    def __init__(self, region: str = "us-east-1"):
        self.bedrock = boto3.client('bedrock', region_name=region)
        self.region = region

    def create_fine_tuning_job(self,
                               job_name: str,
                               base_model_id: str,
                               training_data_s3_uri: str,
                               validation_data_s3_uri: str,
                               output_s3_uri: str,
                               role_arn: str,
                               hyperparameters: Dict[str, str] = None) -> str:
        """
        Create a fine-tuning job

        Args:
            job_name: Unique name for the job
            base_model_id: Foundation model to fine-tune (e.g., 'amazon.titan-text-express-v1')
            training_data_s3_uri: S3 URI for training data
            validation_data_s3_uri: S3 URI for validation data
            output_s3_uri: S3 URI for output model
            role_arn: IAM role ARN with permissions
            hyperparameters: Training hyperparameters

        Returns:
            Job ARN
        """
        logger.info("=" * 70)
        logger.info("Creating Fine-Tuning Job")
        logger.info("=" * 70)

        # Default hyperparameters for Titan models
        if hyperparameters is None:
            hyperparameters = {
                "epochCount": "3",
                "batchSize": "1",
                "learningRate": "0.00001",
                "learningRateWarmupSteps": "0"
            }

        try:
            response = self.bedrock.create_model_customization_job(
                jobName=job_name,
                customModelName=f"{job_name}-model",
                roleArn=role_arn,
                baseModelIdentifier=base_model_id,
                customizationType="FINE_TUNING",
                trainingDataConfig={
                    "s3Uri": training_data_s3_uri
                },
                validationDataConfig={
                    "validators": [{
                        "s3Uri": validation_data_s3_uri
                    }]
                },
                outputDataConfig={
                    "s3Uri": output_s3_uri
                },
                hyperParameters=hyperparameters
            )

            job_arn = response['jobArn']

            logger.info(f"✅ Fine-tuning job created successfully!")
            logger.info(f"Job ARN: {job_arn}")
            logger.info(f"Job Name: {job_name}")
            logger.info(f"Base Model: {base_model_id}")
            logger.info("=" * 70)

            return job_arn

        except Exception as e:
            logger.error(f"Failed to create fine-tuning job: {e}")
            raise

    def get_job_status(self, job_arn: str) -> Dict[str, Any]:
        """Get status of a fine-tuning job"""
        try:
            response = self.bedrock.get_model_customization_job(
                jobIdentifier=job_arn
            )
            return response
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            raise

    def wait_for_completion(self, job_arn: str,
                           check_interval: int = 60,
                           timeout: int = 7200) -> Dict[str, Any]:
        """
        Wait for fine-tuning job to complete

        Args:
            job_arn: Job ARN to monitor
            check_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final job status
        """
        logger.info(f"Monitoring job: {job_arn}")
        logger.info(f"Check interval: {check_interval}s, Timeout: {timeout}s")

        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time

            if elapsed > timeout:
                logger.error(f"⏰ Timeout reached after {timeout}s")
                break

            status = self.get_job_status(job_arn)
            current_status = status['status']

            if current_status != last_status:
                logger.info(f"Status: {current_status}")
                last_status = current_status

            # Terminal states
            if current_status == 'Completed':
                logger.info("✅ Fine-tuning job completed successfully!")
                return status
            elif current_status in ['Failed', 'Stopped']:
                logger.error(f"❌ Job ended with status: {current_status}")
                if 'failureMessage' in status:
                    logger.error(f"Failure message: {status['failureMessage']}")
                return status

            # Wait before next check
            time.sleep(check_interval)

        return self.get_job_status(job_arn)

    def list_custom_models(self) -> list:
        """List all custom models"""
        try:
            response = self.bedrock.list_custom_models()
            models = response.get('modelSummaries', [])

            logger.info(f"Found {len(models)} custom models:")
            for model in models:
                logger.info(f"  - {model['modelName']} ({model['modelArn']})")

            return models
        except Exception as e:
            logger.error(f"Failed to list custom models: {e}")
            raise

    def create_provisioned_throughput(self,
                                     model_arn: str,
                                     throughput_name: str,
                                     model_units: int = 1) -> str:
        """
        Create provisioned throughput for custom model

        Args:
            model_arn: ARN of custom model
            throughput_name: Name for provisioned throughput
            model_units: Number of model units (1-10)

        Returns:
            Provisioned throughput ARN
        """
        try:
            response = self.bedrock.create_provisioned_model_throughput(
                modelUnits=model_units,
                provisionedModelName=throughput_name,
                modelId=model_arn
            )

            throughput_arn = response['provisionedModelArn']
            logger.info(f"✅ Created provisioned throughput: {throughput_arn}")

            return throughput_arn
        except Exception as e:
            logger.error(f"Failed to create provisioned throughput: {e}")
            raise


def main():
    """Example usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Start Bedrock fine-tuning job")
    parser.add_argument("--job-name", required=True, help="Job name")
    parser.add_argument("--base-model", required=True,
                       help="Base model ID (e.g., amazon.titan-text-express-v1)")
    parser.add_argument("--train-data", required=True, help="S3 URI for training data")
    parser.add_argument("--val-data", required=True, help="S3 URI for validation data")
    parser.add_argument("--output-s3", required=True, help="S3 URI for output")
    parser.add_argument("--role-arn", required=True, help="IAM role ARN")
    parser.add_argument("--epochs", type=int, default=3, help="Number of epochs")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=0.00001, help="Learning rate")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--wait", action="store_true", help="Wait for completion")

    args = parser.parse_args()

    # Create fine-tuner
    fine_tuner = BedrockFineTuner(region=args.region)

    # Set hyperparameters
    hyperparameters = {
        "epochCount": str(args.epochs),
        "batchSize": str(args.batch_size),
        "learningRate": str(args.learning_rate),
        "learningRateWarmupSteps": "0"
    }

    # Create job
    job_arn = fine_tuner.create_fine_tuning_job(
        job_name=args.job_name,
        base_model_id=args.base_model,
        training_data_s3_uri=args.train_data,
        validation_data_s3_uri=args.val_data,
        output_s3_uri=args.output_s3,
        role_arn=args.role_arn,
        hyperparameters=hyperparameters
    )

    print(f"\n✅ Job created: {job_arn}")

    # Wait for completion if requested
    if args.wait:
        print("\n⏳ Waiting for job to complete...")
        final_status = fine_tuner.wait_for_completion(job_arn)
        print(f"\nFinal status: {final_status['status']}")


if __name__ == "__main__":
    main()
```

### 📊 Monitoring Training Progress

**scripts/monitor_training.py:**

```python
#!/usr/bin/env python3
"""
Monitor Bedrock fine-tuning job progress
"""

import boto3
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def monitor_job(job_arn: str, region: str = "us-east-1"):
    """Monitor and display training progress"""

    bedrock = boto3.client('bedrock', region_name=region)

    print("\n" + "=" * 80)
    print(f"Monitoring Fine-Tuning Job")
    print("=" * 80)
    print(f"Job ARN: {job_arn}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")

    start_time = time.time()

    while True:
        try:
            response = bedrock.get_model_customization_job(
                jobIdentifier=job_arn
            )

            status = response['status']
            elapsed = time.time() - start_time
            elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))

            # Display status
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {status} | Elapsed: {elapsed_str}")

            # Show metrics if available
            if 'trainingMetrics' in response:
                metrics = response['trainingMetrics']
                print(f"  Training Loss: {metrics.get('trainingLoss', 'N/A')}")

            if 'validationMetrics' in response:
                metrics = response['validationMetrics']
                print(f"  Validation Loss: {metrics.get('validationLoss', 'N/A')}")

            # Terminal states
            if status in ['Completed', 'Failed', 'Stopped']:
                print("\n" + "=" * 80)
                print(f"Job finished with status: {status}")

                if status == 'Completed':
                    print(f"Custom Model ARN: {response.get('outputModelArn', 'N/A')}")
                elif 'failureMessage' in response:
                    print(f"Failure reason: {response['failureMessage']}")

                print("=" * 80)
                break

            time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            print("\n\nMonitoring interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error monitoring job: {e}")
            time.sleep(60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python monitor_training.py <job_arn> [region]")
        sys.exit(1)

    job_arn = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else "us-east-1"

    monitor_job(job_arn, region)
```

## 💻 Part 3: Infrastructure as Code with AWS CDK

### 🏗️ CDK Stack for Bedrock Fine-Tuning

**infrastructure/cdk/bedrock_stack.py:**

```python
"""
AWS CDK Stack for Bedrock Fine-Tuning Infrastructure
"""

from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class BedrockFineTuningStack(Stack):
    """CDK Stack for Bedrock fine-tuning infrastructure"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for training data and outputs
        self.training_bucket = s3.Bucket(
            self, "BedrockTrainingBucket",
            bucket_name=f"bedrock-training-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldTrainingData",
                    expiration=Duration.days(90),
                    noncurrent_version_expiration=Duration.days(30)
                )
            ],
            removal_policy=RemovalPolicy.RETAIN
        )

        # IAM role for Bedrock service
        self.bedrock_role = iam.Role(
            self, "BedrockServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for Bedrock model customization"
        )

        # Grant Bedrock access to S3 bucket
        self.training_bucket.grant_read_write(self.bedrock_role)

        # Policy for Bedrock model customization
        self.bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:CreateModelCustomizationJob",
                    "bedrock:GetModelCustomizationJob",
                    "bedrock:ListModelCustomizationJobs",
                    "bedrock:StopModelCustomizationJob",
                    "bedrock:CreateProvisionedModelThroughput",
                    "bedrock:GetProvisionedModelThroughput",
                    "bedrock:DeleteProvisionedModelThroughput",
                    "bedrock:ListCustomModels",
                    "bedrock:GetCustomModel",
                    "bedrock:DeleteCustomModel"
                ],
                resources=["*"]
            )
        )

        # CloudWatch Logs for training job logs
        self.log_group = logs.LogGroup(
            self, "BedrockTrainingLogs",
            log_group_name="/aws/bedrock/training",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )

        # IAM role for Lambda functions (if using Lambda for orchestration)
        self.lambda_role = iam.Role(
            self, "BedrockLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant Lambda permissions to interact with Bedrock
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:CreateModelCustomizationJob",
                    "bedrock:GetModelCustomizationJob",
                    "bedrock:ListModelCustomizationJobs"
                ],
                resources=["*"]
            )
        )

        # Grant Lambda access to S3
        self.training_bucket.grant_read_write(self.lambda_role)

        # Output important values
        from aws_cdk import CfnOutput

        CfnOutput(
            self, "TrainingBucketName",
            value=self.training_bucket.bucket_name,
            description="S3 bucket for training data"
        )

        CfnOutput(
            self, "BedrockRoleArn",
            value=self.bedrock_role.role_arn,
            description="IAM role ARN for Bedrock service"
        )

        CfnOutput(
            self, "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="IAM role ARN for Lambda functions"
        )
```

**infrastructure/cdk/app.py:**

```python
#!/usr/bin/env python3
"""
CDK App for Bedrock Fine-Tuning Infrastructure
"""

import aws_cdk as cdk
from bedrock_stack import BedrockFineTuningStack

app = cdk.App()

BedrockFineTuningStack(
    app, "BedrockFineTuningStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1"
    ),
    description="Infrastructure for AWS Bedrock LLM fine-tuning"
)

app.synth()
```

**Deploy the infrastructure:**

```bash
# Navigate to CDK directory
cd infrastructure/cdk

# Install CDK dependencies
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy stack
cdk deploy

# Note the outputs (bucket name, role ARNs)
```

## 💻 Part 4: Model Inference and Evaluation

### 🔮 Using Your Fine-Tuned Model

**scripts/inference.py:**

```python
#!/usr/bin/env python3
"""
Inference with fine-tuned Bedrock model
"""

import boto3
import json
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BedrockInference:
    """Perform inference with fine-tuned models"""

    def __init__(self, region: str = "us-east-1"):
        self.bedrock_runtime = boto3.client(
            'bedrock-runtime',
            region_name=region
        )

    def invoke_model(self,
                    model_arn: str,
                    prompt: str,
                    max_tokens: int = 512,
                    temperature: float = 0.7) -> Dict[str, Any]:
        """
        Invoke fine-tuned model

        Args:
            model_arn: ARN of fine-tuned model or provisioned throughput
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Model response
        """
        # Build request body (format depends on base model)
        request_body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": max_tokens,
                "temperature": temperature,
                "topP": 0.9
            }
        }

        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=model_arn,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )

            # Parse response
            response_body = json.loads(response['body'].read())

            return response_body

        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise

    def batch_inference(self,
                       model_arn: str,
                       prompts: list,
                       max_tokens: int = 512) -> list:
        """Run inference on multiple prompts"""
        results = []

        for idx, prompt in enumerate(prompts):
            logger.info(f"Processing prompt {idx + 1}/{len(prompts)}")

            try:
                result = self.invoke_model(
                    model_arn=model_arn,
                    prompt=prompt,
                    max_tokens=max_tokens
                )
                results.append({
                    "prompt": prompt,
                    "response": result,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "prompt": prompt,
                    "error": str(e),
                    "status": "failed"
                })

        return results


def compare_models(base_model_id: str,
                  custom_model_arn: str,
                  test_prompts: list,
                  region: str = "us-east-1"):
    """
    Compare base model vs fine-tuned model

    Args:
        base_model_id: Base foundation model ID
        custom_model_arn: Fine-tuned model ARN
        test_prompts: List of test prompts
        region: AWS region
    """
    inference = BedrockInference(region=region)

    print("\n" + "=" * 80)
    print("Model Comparison: Base vs Fine-Tuned")
    print("=" * 80 + "\n")

    for idx, prompt in enumerate(test_prompts, 1):
        print(f"Test {idx}: {prompt}")
        print("-" * 80)

        # Base model
        print("Base Model Response:")
        try:
            base_response = inference.invoke_model(base_model_id, prompt)
            print(json.dumps(base_response, indent=2))
        except Exception as e:
            print(f"Error: {e}")

        print()

        # Fine-tuned model
        print("Fine-Tuned Model Response:")
        try:
            custom_response = inference.invoke_model(custom_model_arn, prompt)
            print(json.dumps(custom_response, indent=2))
        except Exception as e:
            print(f"Error: {e}")

        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run inference with fine-tuned model")
    parser.add_argument("--model-arn", required=True, help="Fine-tuned model ARN")
    parser.add_argument("--prompt", help="Single prompt for inference")
    parser.add_argument("--prompts-file", help="File with multiple prompts")
    parser.add_argument("--compare", help="Base model ID for comparison")
    parser.add_argument("--region", default="us-east-1", help="AWS region")

    args = parser.parse_args()

    inference = BedrockInference(region=args.region)

    if args.prompt:
        # Single prompt
        result = inference.invoke_model(args.model_arn, args.prompt)
        print(json.dumps(result, indent=2))

    elif args.prompts_file:
        # Multiple prompts from file
        with open(args.prompts_file, 'r') as f:
            prompts = [line.strip() for line in f if line.strip()]

        if args.compare:
            compare_models(args.compare, args.model_arn, prompts, args.region)
        else:
            results = inference.batch_inference(args.model_arn, prompts)
            print(json.dumps(results, indent=2))
```

## 🎯 Complete End-to-End Example

### Step-by-Step Fine-Tuning Workflow

```bash
# Step 1: Deploy infrastructure
cd infrastructure/cdk
cdk deploy
# Note the outputs: BucketName, BedrockRoleArn

# Step 2: Create sample data (or use your own)
python -c "from scripts.prepare_data import create_sample_dataset; create_sample_dataset('data/raw/samples.jsonl', 500)"

# Step 3: Prepare and upload data
python scripts/prepare_data.py \
  --input data/raw/samples.jsonl \
  --bucket bedrock-training-ACCOUNT-REGION \
  --prefix training-data

# Step 4: Start fine-tuning job
python scripts/start_training.py \
  --job-name sentiment-classifier-v1 \
  --base-model amazon.titan-text-express-v1 \
  --train-data s3://bedrock-training-ACCOUNT-REGION/training-data/train_*.jsonl \
  --val-data s3://bedrock-training-ACCOUNT-REGION/training-data/val_*.jsonl \
  --output-s3 s3://bedrock-training-ACCOUNT-REGION/models/ \
  --role-arn arn:aws:iam::ACCOUNT:role/BedrockServiceRole \
  --epochs 3 \
  --wait

# Step 5: Monitor training (in another terminal)
python scripts/monitor_training.py arn:aws:bedrock:REGION:ACCOUNT:model-customization-job/JOB_ID

# Step 6: Test fine-tuned model
python scripts/inference.py \
  --model-arn arn:aws:bedrock:REGION:ACCOUNT:provisioned-model/MODEL_ID \
  --prompt "Classify the sentiment of this review: Best product ever!"

# Step 7: Compare with base model
python scripts/inference.py \
  --model-arn arn:aws:bedrock:REGION:ACCOUNT:provisioned-model/MODEL_ID \
  --prompts-file test_prompts.txt \
  --compare amazon.titan-text-express-v1
```

## 🎯 Best Practices and Tips

### 📊 Data Quality Best Practices

1. **Data Volume**
   - Minimum: 100 examples for simple tasks
   - Recommended: 500-1,000 examples for most use cases
   - Maximum: 10,000 examples per job

2. **Data Diversity**
   - Cover all edge cases and variations
   - Balance class distributions
   - Include negative examples

3. **Prompt Engineering**
   - Keep prompts consistent in format
   - Use clear, specific instructions
   - Test prompt templates before fine-tuning

### 🔧 Hyperparameter Tuning

```python
# Conservative (safe, slower learning)
conservative_params = {
    "epochCount": "5",
    "batchSize": "1",
    "learningRate": "0.000005"
}

# Moderate (recommended starting point)
moderate_params = {
    "epochCount": "3",
    "batchSize": "1",
    "learningRate": "0.00001"
}

# Aggressive (faster, risk of overfitting)
aggressive_params = {
    "epochCount": "2",
    "batchSize": "2",
    "learningRate": "0.00005"
}
```

### 💰 Cost Optimization

- **Use validation sets** to prevent overfitting (saves re-training costs)
- **Start with smaller datasets** to validate approach
- **Use on-demand inference** for testing, provisioned throughput for production
- **Delete unused custom models** to avoid storage costs
- **Monitor training time** - stop if loss plateaus early

### 🔒 Security Best Practices

```python
# Always use encryption
training_config = {
    "s3Uri": "s3://bucket/data/",
    "encryption": {
        "type": "KMS",
        "kmsKeyId": "arn:aws:kms:region:account:key/key-id"
    }
}

# Use VPC endpoints for private connectivity
vpc_config = {
    "subnetIds": ["subnet-xxx", "subnet-yyy"],
    "securityGroupIds": ["sg-xxx"]
}

# Enable CloudTrail logging for audit
# Enable S3 bucket versioning for data recovery
# Use IAM policies with least privilege principle
```

## 🎉 Conclusion

You've now learned how to fine-tune LLMs with AWS Bedrock, covering:

✅ **Three customization approaches** - Fine-tuning, continued pre-training, reinforcement fine-tuning
✅ **Complete data preparation pipeline** - Validation, formatting, upload to S3
✅ **Production-ready Python scripts** - Training job management, monitoring, inference
✅ **Infrastructure as Code** - CDK stack for reproducible deployments
✅ **Best practices** - Data quality, hyperparameters, cost optimization, security

### Key Takeaways

1. **Start Simple** - Begin with a small dataset and basic fine-tuning
2. **Validate Thoroughly** - Use held-out validation data to prevent overfitting
3. **Monitor Costs** - Fine-tuning is charged by the hour, monitor your jobs
4. **Iterate** - Fine-tuning is iterative; expect to refine data and hyperparameters
5. **Secure Your Data** - Use encryption, VPCs, and IAM best practices

### Next Steps

**Enhance your fine-tuning:**
- Implement automated evaluation metrics
- Build CI/CD pipelines for model updates
- Create A/B testing for model versions
- Set up monitoring and alerting for inference quality
- Explore reinforcement fine-tuning for alignment tasks

**Advanced topics:**
- Multi-task fine-tuning
- Few-shot learning optimization
- Model compression and distillation
- Cross-model ensemble approaches

### Resources

Sources:
- [Customize models in Amazon Bedrock with your own data using fine-tuning and continued pre-training | AWS News Blog](https://aws.amazon.com/blogs/aws/customize-models-in-amazon-bedrock-with-your-own-data-using-fine-tuning-and-continued-pre-training/)
- [Amazon Bedrock now supports reinforcement fine-tuning delivering 66% accuracy gains on average over base models - AWS](https://aws.amazon.com/about-aws/whats-new/2025/12/bedrock-reinforcement-fine-tuning-66-base-models/)
- [Customize your model to improve its performance for your use case - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/custom-models.html)
- [Code samples for model customization - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-code-samples.html)
- [Prepare your training datasets for fine-tuning and continued pre-training - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-prepare.html)
- [Fine-tune LLMs with synthetic data for context-based Q&A using Amazon Bedrock | Artificial Intelligence](https://aws.amazon.com/blogs/machine-learning/fine-tune-llms-with-synthetic-data-for-context-based-qa-using-amazon-bedrock/)

---

## 🏷️ Tags & Categories

**Tags**: AWS Bedrock, LLM, fine-tuning, machine-learning, AI, Claude, Titan, AWS CDK, Python, boto3, reinforcement-learning
**Categories**: AI, AWS, Machine Learning, MLOps
**Difficulty**: Intermediate to Advanced
**Time to Complete**: 6-8 hours
