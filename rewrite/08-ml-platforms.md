# Module 8: Cloud Infrastructure for Data Engineers

At some point, your laptop isn't enough. You've built pipelines, modeled data in dbt, added quality checks -- all running locally. But nobody is querying your localhost Postgres from a dashboard. To deliver real value, you need to deploy everything you've built to the cloud. This module shows you how.

> *You don't need to be a DevOps engineer, but you need to deploy your own stuff. AWS-focused with transferable concepts.*

Here's a conversation that happens with at least 20 junior data engineers: *"I know Python. I know SQL. I can build pipelines locally. But when it comes to deploying anything to the cloud, I freeze. There are 200+ AWS services and I don't know where to start."*

Good news: you need maybe 10 of them.

---

## 8.1 Cloud Fundamentals for DEs -- What You Need to Know

> **TL;DR:** Out of 200+ AWS services, you need about 10 for data engineering. The core pattern is: S3 for storage, RDS/Redshift for databases, Athena for ad-hoc queries, ECS for compute, and IAM for security. Learn one cloud well and the others are just different UIs.

### The Three Cloud Superpowers

1. **Elasticity** -- scale up when you need it, scale down when you don't
2. **Managed services** -- someone else handles the patching, backups, and uptime
3. **Pay-per-use** -- you pay for what you consume, not what you provision (mostly)

### The AWS Data Engineering Stack

For data engineers, the cloud maps to your pipeline stages:

```
Source -> Ingest -> Store -> Process -> Serve -> Monitor
```

| Pipeline Stage | AWS Service | What It Does |
|---|---|---|
| **Store (raw)** | S3 | Object storage -- your data lake |
| **Store (structured)** | RDS (Postgres) | Managed relational database |
| **Store (warehouse)** | Redshift | Columnar analytics database |
| **Process (batch)** | EMR / Glue | Managed Spark |
| **Process (serverless)** | Lambda | Run code without servers |
| **Query (ad-hoc)** | Athena | SQL on S3 files directly |
| **Orchestrate** | MWAA / Step Functions | Managed Airflow / workflow |
| **Stream** | Kinesis / MSK | Managed Kafka |
| **Compute** | EC2 / ECS / Fargate | Run containers |
| **IAM** | IAM | Access control |
| **Secrets** | Secrets Manager | Store credentials |

That's it. That's the 80/20 of AWS for data engineers.

### At Your Job

Your first cloud task will probably be setting up S3 buckets and IAM roles. Maybe provisioning an RDS instance. You won't be designing VPC architectures or managing Kubernetes clusters on day one. Start with storage and permissions -- those are the foundation everything else rests on.

### The Data Lake Architecture on AWS

Three layers in S3:

- `/raw/` -- data as it arrived, never modified (your safety net)
- `/staging/` -- cleaned, validated, intermediate transformations
- `/prod/` -- final, analytics-ready tables (Parquet/Delta format)

> **Key Concept: Medallion Architecture**
> This layered approach is called the **medallion architecture** (bronze/silver/gold) or raw/staging/prod. Same concept, different names. The key principle: raw data is immutable. You never modify it. All transformations produce new data in downstream layers.

### GCP/Azure Equivalents

Quick reference if you end up at a non-AWS shop:

| AWS | GCP | Azure |
|---|---|---|
| S3 | Cloud Storage | Blob Storage |
| RDS | Cloud SQL | Azure SQL |
| Redshift | BigQuery | Synapse |
| EMR | Dataproc | HDInsight |
| Athena | BigQuery | Synapse Serverless |
| Lambda | Cloud Functions | Azure Functions |
| ECS/Fargate | Cloud Run | Container Apps |
| MWAA | Cloud Composer | Data Factory |

The concepts transfer completely. Learn one cloud well, and the others are just different UIs.

> **Common Mistake**
> - Trying to learn all AWS services. Focus on the data stack above.
> - Using the AWS Console for everything. That's fine for learning, but production uses Infrastructure as Code (Terraform).
> - Running expensive services 24/7 during learning. Set up billing alerts first (covered in Section 8.6).

### Checkpoint

1. What are the three layers of a data lake on S3?
2. What AWS service would you use to run SQL queries directly on files stored in S3?
3. What's the GCP equivalent of S3?

---

## 8.2 The AWS Data Stack -- S3, RDS, Glue, Athena

> **TL;DR:** S3 is your data lake foundation -- cheap, durable, infinitely scalable. Store data as Parquet (not CSV) for 10-100x better query performance. Use Athena to query S3 with standard SQL. Always partition your data to reduce costs. For most startups, S3 + Athena + RDS Postgres covers 90% of use cases.

### S3 -- Your Data Lake

S3 is the foundation of everything. It's cheap ($0.023/GB/month for standard storage), durable (99.999999999% -- eleven 9s), and infinitely scalable.

Set up a data lake bucket:

```bash
# Create the bucket
aws s3 mb s3://my-ecommerce-data-lake-2026 --region us-east-1

# Create the layer structure
aws s3api put-object --bucket my-ecommerce-data-lake-2026 --key raw/
aws s3api put-object --bucket my-ecommerce-data-lake-2026 --key staging/
aws s3api put-object --bucket my-ecommerce-data-lake-2026 --key prod/
```

Upload data with Python and boto3:

```python
import boto3
import pandas as pd
from datetime import datetime

s3 = boto3.client("s3")
BUCKET = "my-ecommerce-data-lake-2026"


def upload_to_data_lake(
    df: pd.DataFrame,
    layer: str,        # raw, staging, prod
    dataset: str,      # orders, customers, etc.
    partition_date: str | None = None,
) -> str:
    """Upload a DataFrame to S3 as Parquet with date partitioning."""
    if partition_date is None:
        partition_date = datetime.now().strftime("%Y-%m-%d")

    # Hive-style partitioning: /layer/dataset/date=YYYY-MM-DD/data.parquet
    key = f"{layer}/{dataset}/date={partition_date}/data.parquet"

    # Write to Parquet in memory, then upload
    buffer = df.to_parquet(index=False)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buffer)

    print(f"Uploaded {len(df)} rows to s3://{BUCKET}/{key}")
    return f"s3://{BUCKET}/{key}"


# Example: upload raw orders
orders_df = pd.DataFrame({
    "order_id": range(1, 1001),
    "customer_id": [i % 200 + 1 for i in range(1000)],
    "order_date": pd.date_range("2026-02-01", periods=1000, freq="h"),
    "total_amount": [round(i * 1.5 + 10, 2) for i in range(1000)],
    "status": ["shipped"] * 400 + ["delivered"] * 300 + ["pending"] * 200 +
["cancelled"] * 100,
})

upload_to_data_lake(orders_df, "raw", "orders", "2026-02-18")
```

**Expected output:**

```
Uploaded 1000 rows to s3://my-ecommerce-data-lake-2026/raw/orders/date=2026-02-18/
data.parquet
```

> **Pro Tip: Why Parquet?**
> Parquet is columnar, compressed, and typed. For analytics workloads, it's 10-100x faster to query than CSV because: (1) query engines only read the columns they need, (2) compression reduces I/O, (3) built-in statistics allow predicate pushdown (skipping rows that don't match your WHERE clause). Never store analytics data as CSV in S3.

### Athena -- SQL on S3

Athena lets you query S3 files using standard SQL. No server to manage, no data to load into a database. You pay $5 per TB scanned.

Create a table definition:

```sql
-- Partitioned table -- critical for cost and performance
CREATE EXTERNAL TABLE IF NOT EXISTS raw_orders_partitioned (
    order_id INT,
    customer_id INT,
    order_date TIMESTAMP,
    total_amount DOUBLE,
    status STRING
)
PARTITIONED BY (date STRING)
STORED AS PARQUET
LOCATION 's3://my-ecommerce-data-lake-2026/raw/orders/'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

-- Tell Athena to discover partitions
MSCK REPAIR TABLE raw_orders_partitioned;
```

Now query it -- just SQL:

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    ROUND(AVG(total_amount), 2) AS avg_amount
FROM raw_orders_partitioned
WHERE date = '2026-02-18'    -- Partition filter: only scans this one day
GROUP BY status
ORDER BY order_count DESC;
```

**Expected output:**

```
status       | order_count | avg_amount
-------------+-------------+------------
 shipped     |         400 |     310.25
 delivered   |         300 |     760.50
 pending     |         200 |    1210.75
 cancelled   |         100 |    1511.00
```

> **Common Mistake**
> The partition filter (`WHERE date = '2026-02-18'`) is critical -- it means Athena only scans that one partition instead of your entire dataset. Without partitions, every query scans everything. That's expensive and slow.

### AWS Glue -- The Catalog

Glue does two things:

1. **Glue Data Catalog** -- a metadata store (think: Hive Metastore). Athena uses this to know about your tables.
2. **Glue ETL** -- managed Spark jobs for transformations. (Honestly, most teams use Airflow + Spark directly because Glue ETL has weird limitations and debugging is painful.)

Set up a Glue Crawler to auto-discover your S3 data:

```bash
aws glue create-crawler \
    --name ecommerce-raw-crawler \
    --role AWSGlueServiceRole \
    --database-name ecommerce_db \
    --targets '{"S3Targets": [{"Path": "s3://my-ecommerce-data-lake-2026/raw/"}]}'

aws glue start-crawler --name ecommerce-raw-crawler
```

The crawler scans your S3 data, infers the schema, and creates table definitions in the Glue Catalog. Athena can then query these tables without you manually writing CREATE TABLE statements.

### When to Use What

| Scenario | Best Choice |
|---|---|
| Small data (< 10GB), simple queries | Athena on S3 (cheapest, simplest) |
| Need ACID transactions, complex joins | RDS Postgres (or Aurora) |
| Large-scale analytics, many users | Redshift (columnar warehouse) |
| Spark transformations | EMR (or Glue ETL if you must) |

For the course project and most startups, **S3 + Athena + RDS Postgres** covers 90% of use cases.

### Checkpoint

1. Why is Parquet dramatically better than CSV for Athena queries?
2. What does `MSCK REPAIR TABLE` do?
3. At what scale would you consider Redshift over Postgres + Athena?

---

## 8.3 Infrastructure as Code with Terraform

> **TL;DR:** Terraform lets you define your cloud infrastructure as version-controlled code files. You describe the desired state, Terraform figures out the steps. Three commands: `init`, `plan`, `apply`. Always read the plan before applying. Store state remotely in S3 for team collaboration.

Clicking through the AWS console works until you need to recreate your environment. Imagine you built your whole data platform in AWS. It's running great. Then your company wants a staging environment that mirrors production. You open the AWS Console and think, *"How did I set all this up again?"*

That's the problem Infrastructure as Code solves. Terraform makes infrastructure reproducible -- you describe what you want, commit it to Git, and anyone on your team can stand up an identical environment with three commands.

### How Terraform Works

1. **Write** -- describe what you want in `.tf` files (HCL language)
2. **Plan** -- Terraform compares your config to what exists and shows what it'll change
3. **Apply** -- Terraform makes the changes

It's declarative: you describe the *desired state*, not the steps to get there.

### S3 Data Lake in Terraform

Here is the main configuration. See the companion code in `module-8/solution/terraform/main.tf`:

```hcl
# main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "dev"
}

variable "project_name" {
  default = "ecommerce-data-platform"
}
```

Now the S3 bucket with all the production guardrails. See `module-8/solution/terraform/s3.tf`:

```hcl
# s3.tf
resource "aws_s3_bucket" "data_lake" {
    bucket = "${var.project_name}-${var.environment}-data-lake"

    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "terraform"
    }
}

# Enable versioning (safety net for accidental deletes)
resource "aws_s3_bucket_versioning" "data_lake" {
    bucket = aws_s3_bucket.data_lake.id
    versioning_configuration {
      status = "Enabled"
    }
}

# Block ALL public access (data lakes should NEVER be public)
resource "aws_s3_bucket_public_access_block" "data_lake" {
    bucket = aws_s3_bucket.data_lake.id

    block_public_acls       = true
    block_public_policy     = true
    ignore_public_acls      = true
    restrict_public_buckets = true
}

# Lifecycle rules: move old raw data to cheaper storage tiers
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
    bucket = aws_s3_bucket.data_lake.id

    rule {
      id      = "archive-raw-data"
      status  = "Enabled"

      filter {
        prefix = "raw/"
      }

      transition {
        days          = 90
        storage_class = "STANDARD_IA"  # Infrequent Access -- 45% cheaper
      }

      transition {
        days          = 365
        storage_class = "GLACIER"  # Long-term archive -- 80% cheaper
      }
    }
}
```

### RDS Postgres in Terraform

See `module-8/solution/terraform/rds.tf`:

```hcl
# rds.tf
resource "aws_db_instance" "postgres" {
    identifier      = "${var.project_name}-${var.environment}-db"
    engine          = "postgres"
    engine_version  = "16.1"
    instance_class  = "db.t3.micro"  # Cheapest option for dev

    allocated_storage     = 20
    max_allocated_storage = 100  # Auto-scale up to 100GB
    storage_type          = "gp3"

    db_name  = "ecommerce"
    username = "dataengineer"
    password = var.db_password  # Never hardcode passwords!

    publicly_accessible    = false  # Access only from within VPC
    vpc_security_group_ids = [aws_security_group.db.id]
    db_subnet_group_name   = aws_db_subnet_group.db.name

    backup_retention_period = 7
    backup_window           = "03:00-04:00"

    # Safety: don't delete production databases on terraform destroy
    deletion_protection = var.environment == "prod" ? true : false
    skip_final_snapshot = var.environment == "dev" ? true : false

    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "terraform"
    }
}

variable "db_password" {
    type      = string
    sensitive = true  # Won't show in terraform plan output
}
```

### IAM Role for Your Pipeline

This is where the principle of least privilege lives. Your pipeline should only be able to access the S3 bucket and RDS instance it needs -- nothing else. See `module-8/solution/terraform/iam.tf`:

```hcl
# iam.tf -- Role that your Airflow tasks assume
resource "aws_iam_role" "pipeline_role" {
    name = "${var.project_name}-${var.environment}-pipeline-role"

    assume_role_policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action = "sts:AssumeRole"
          Effect = "Allow"
          Principal = {
            Service = "ecs-tasks.amazonaws.com"
          }
        },
      ]
    })
}

# Policy: pipeline can read/write to S3 data lake -- nothing else
resource "aws_iam_role_policy" "pipeline_s3_access" {
    name = "s3-data-lake-access"
    role = aws_iam_role.pipeline_role.id

    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Action = [
            "s3:GetObject",
            "s3:PutObject",
            "s3:ListBucket",
            "s3:DeleteObject",
          ]
          Resource = [
              aws_s3_bucket.data_lake.arn,
              "${aws_s3_bucket.data_lake.arn}/*",
          ]
        },
      ]
    })
}
```

### Running Terraform

```bash
# Initialize -- downloads provider plugins
terraform init

# Plan -- shows what will be created/changed/destroyed
terraform plan -var="db_password=supersecret123"

# Apply -- actually creates the resources
terraform apply -var="db_password=supersecret123"

# When you're done, destroy everything to stop charges
terraform destroy -var="db_password=supersecret123"
```

**Expected plan output:**

```
Plan: 6 to add, 0 to change, 0 to destroy.
```

> **Pro Tip: Always read the plan before applying.** Especially look for resources being destroyed -- that's usually not what you want.

### Remote State Management

In production, store Terraform state in S3 (not locally) so your team can share it:

```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket         = "my-terraform-state-bucket"
    key            = "ecommerce-data-platform/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"  # Prevents concurrent applies
  }
}
```

> **Common Mistake**
> - Hardcoding secrets in `.tf` files. Use variables with `sensitive = true` or AWS Secrets Manager.
> - Not using remote state from day one. Local state files get lost and cause drift.
> - Forgetting `terraform destroy` when done experimenting. That's how you get a surprise AWS bill.

### Checkpoint

1. What are the three Terraform commands and what does each do?
2. Why should you never hardcode passwords in Terraform files?
3. What's the purpose of the DynamoDB table in the remote state backend config?

---

## 8.4 Docker for Data Engineers -- Containerizing Pipelines

> **TL;DR:** Docker packages your code AND its environment into a container that runs identically everywhere. Key practices: specific version tags (not `latest`), non-root user, multi-stage builds for smaller images, and layer ordering optimized for cache (dependencies first, code last).

"It works on my machine." Docker eliminates this by packaging your code and its entire environment into a container that runs the same everywhere. For data pipelines, this matters more than you'd think: a pipeline that runs fine with pandas 2.0 on your Mac might silently produce wrong results with pandas 1.5 on a coworker's Linux machine. Containers make your pipelines reproducible, isolated, and deployable.

### Production-Grade Dockerfile

See the companion code in `module-8/solution/Dockerfile`:

```dockerfile
# Use a specific version -- reproducibility matters
FROM python:3.11-slim AS base

# Don't run as root in production
RUN groupadd -r pipeline && useradd -r -g pipeline pipeline

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (Docker caches layers -- this rarely changes)
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN pip install uv && uv sync --frozen --no-dev

# Copy the actual code LAST (this layer changes most often)
COPY src/ ./src/
COPY configs/ ./configs/

# Switch to non-root user
USER pipeline

ENTRYPOINT ["python", "-m", "src.main"]
```

> **Key Concept: Layer Ordering**
> Docker caches each layer. If you put `COPY src/` before `pip install`, every code change invalidates the cache and reinstalls all dependencies. Put dependencies first, code last. This makes rebuilds go from minutes to seconds.

### Docker Compose for Multi-Container Pipelines

Your pipeline doesn't run alone -- it needs Postgres, maybe MinIO for local S3. Docker Compose orchestrates all of it:

```yaml
# docker-compose.yml
version: "3.8"

services:
  pipeline:
      build: .
      environment:
        - DATABASE_URL=postgresql://postgres:postgres@db:5432/ecommerce
        - S3_BUCKET=my-ecommerce-data-lake-2026
        - AWS_REGION=us-east-1
      depends_on:
        db:
            condition: service_healthy
      volumes:
        - ./data:/app/data  # Mount local data directory for dev

  db:
      image: postgres:16
      environment:
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres
        POSTGRES_DB: ecommerce
      ports:
        - "5432:5432"
      volumes:
        - pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U postgres"]
        interval: 5s
        timeout: 5s
        retries: 5

  # Local S3-compatible storage (for development)
  minio:
      image: minio/minio
      command: server /data --console-address ":9001"
      environment:
        MINIO_ROOT_USER: minioadmin
        MINIO_ROOT_PASSWORD: minioadmin
      ports:
        - "9000:9000"
        - "9001:9001"
      volumes:
          - minio_data:/data

volumes:
  pgdata:
  minio_data:
```

### Multi-Stage Builds for Smaller Images

Production images should be small. Multi-stage builds separate the build environment from runtime:

```dockerfile
# Build stage -- has all the build tools
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# Runtime stage -- only what's needed to run
FROM python:3.11-slim AS runtime
RUN groupadd -r pipeline && useradd -r -g pipeline pipeline
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY configs/ ./configs/

ENV PATH="/app/.venv/bin:$PATH"
USER pipeline
ENTRYPOINT ["python", "-m", "src.main"]
```

This produces images of 200-400MB instead of 1-2GB.

### Deploying to AWS ECS

```bash
# Build the image
docker build -t ecommerce-pipeline .

# Tag for ECR (Elastic Container Registry)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-
east-1.amazonaws.com

docker tag ecommerce-pipeline:latest \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/ecommerce-pipeline:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/ecommerce-pipeline:latest
```

> **Common Mistake**
> - Using `latest` tag in production. Always tag with a specific version or Git SHA.
> - Running containers as root. Always use a non-root user.
> - Putting secrets in Dockerfiles or docker-compose. Use environment variables injected at runtime.

### Checkpoint

1. Why should you copy dependency files before source code in a Dockerfile?
2. What's the benefit of a multi-stage Docker build?
3. Why should you never use the `latest` tag in production?

---

## 8.5 CI/CD for Data Pipelines -- GitHub Actions

> **TL;DR:** CI/CD automates testing and deployment triggered by Git pushes. CI runs tests on every push (catches bugs early). CD deploys to production when tests pass on main. Use GitHub Actions with a test Postgres service, and deploy via ECR + ECS. Never deploy from anywhere but your CI pipeline.

You've got Terraform for infrastructure, Docker for packaging. But deploying manually -- SSH, pull, restart -- is a liability in production. CI/CD ensures that every change is tested before it reaches production, and that deployments are automated and repeatable.

### The GitHub Actions Workflow

See the companion code in `module-8/solution/.github/workflows/data-pipeline.yml`:

```yaml
# .github/workflows/data-pipeline.yml
name: Data Pipeline CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: ecommerce-pipeline
  ECS_SERVICE: ecommerce-pipeline-service
  ECS_CLUSTER: data-platform

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_ecommerce
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --frozen

      - name: Lint
        run: |
          uv run ruff check src/ tests/
          uv run ruff format --check src/ tests/

      - name: Type check
        run: uv run mypy src/

      - name: Run unit tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_ecommerce
        run: uv run pytest tests/ -v --tb=short

      - name: Run dbt tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_ecommerce
        run: |
          cd dbt_project
          uv run dbt deps
          uv run dbt build --target test

  build-and-deploy:
    name: Build & Deploy
    needs: test                            # Waits for test job to pass
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'    # Only deploy from main branch

    permissions:
      id-token: write  # Required for AWS OIDC
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push image to ECR
        id: build-image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:latest .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
          echo "image=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_OUTPUT

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
              --cluster $ECS_CLUSTER \
              --service $ECS_SERVICE \
              --force-new-deployment

      - name: Wait for deployment
        run: |
          aws ecs wait services-stable \
              --cluster $ECS_CLUSTER \
              --services $ECS_SERVICE
          echo "Deployment successful!"
```

### How It Works

The workflow has two jobs:

1. `test` -- runs on every push and PR. Spins up a test Postgres, runs linting, type checking, unit tests, and dbt tests. If any step fails, the pipeline stops.
2. `build-and-deploy` -- only runs on `main` branch, and only if tests pass. Builds the Docker image, pushes to ECR, updates the ECS service.

`needs: test` means deploy waits for tests to succeed. `if: github.ref == 'refs/heads/main'` means PRs get tested but not deployed.

### Terraform Plan in PRs

Add infrastructure validation to pull requests:

```yaml
  terraform-plan:
    name: Terraform Plan
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'

    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        working-directory: terraform/
        run: terraform init

      - name: Terraform Plan
        working-directory: terraform/
        run: terraform plan -no-color
```

> **Pro Tip: Secrets Management**
> Never put credentials in workflow files. Use GitHub Secrets (repo -> Settings -> Secrets -> Actions). Better yet, use OIDC with `role-to-assume` -- no static credentials at all.

> **Common Mistake**
> - Not running tests in CI. "I'll test locally" doesn't scale.
> - Deploying on every push to main without a staging step.
> - Not pinning action versions. Use `actions/checkout@v4` not `@main`.

### Checkpoint

1. What's the difference between CI and CD?
2. Why does the deploy job have `if: github.ref == 'refs/heads/main'`?
3. What's the advantage of OIDC over static AWS access keys for CI/CD?

---

## 8.6 Cost Management and Security Basics

> **TL;DR:** Set up billing alerts BEFORE doing anything else. A typical dev data platform costs ~$47/month on AWS. Key cost savers: Spot instances for Spark, S3 lifecycle rules, right-size RDS, schedule dev resources off at night. Security: least privilege IAM, never hardcode secrets, encrypt everything.

S3 is cheap. Redshift is not. Here's how to estimate your cloud bill -- and how to avoid the surprise charges that hit every new cloud user.

### Rule #1: Billing Alerts First

```hcl
# In Terraform
resource "aws_cloudwatch_metric_alarm" "billing_alarm" {
  alarm_name          = "monthly-billing-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600  # 6 hours
  statistic           = "Maximum"
  threshold           = 50       # Alert at $50
  alarm_actions       = [aws_sns_topic.billing_alerts.arn]
  dimensions = {
    Currency = "USD"
  }
}
```

### Cost Estimation for a Typical DE Setup

| Service | Config | Monthly Cost |
|---|---|---|
| S3 | 50GB standard | ~$1.15 |
| RDS Postgres | db.t3.micro, 20GB | ~$15 |
| ECS Fargate | 2 tasks, 0.5 vCPU, 1GB each | ~$30 |
| Athena | ~50 queries/day, 100MB scanned each | ~$0.75 |
| ECR | 5 images | ~$0.50 |
| **Total** | | **~$47/month** |

In production with more data and compute, expect $200-500/month for a small/medium platform.

### Cost-Saving Tips

1. **Use Spot instances for Spark/EMR** -- 60-90% cheaper than on-demand
2. **S3 lifecycle rules** -- move old data to Glacier (configured in Section 8.3)
3. **Right-size RDS** -- start with `db.t3.micro`, scale up only when needed
4. **Schedule dev resources off at night:**

```python
# Lambda function to stop dev RDS at night
import boto3

def lambda_handler(event, context):
    rds = boto3.client('rds')
    rds.stop_db_instance(DBInstanceIdentifier='ecommerce-dev-db')
    return {"status": "stopped"}
```

5. **Athena: always use Parquet + partitions** -- can reduce query costs by 90%+

### Security: Three Rules

**1. Principle of Least Privilege**

Your pipeline role should only have the permissions it actually needs. Never give it admin access just because it's easier:

```hcl
# BAD -- gives access to everything
resource "aws_iam_role_policy_attachment" "bad" {
  role       = aws_iam_role.pipeline_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"  # NEVER
}

# GOOD -- specific permissions for specific resources
resource "aws_iam_role_policy" "good" {
  name = "pipeline-s3-access"
  role = aws_iam_role.pipeline_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject"]
      Resource = ["${aws_s3_bucket.data_lake.arn}/*"]
    }]
  })
}
```

**2. Never Hardcode Secrets**

Use AWS Secrets Manager:

```python
import boto3
import json

def get_secret(secret_name: str, region: str = "us-east-1") -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])

# Usage
db_creds = get_secret("ecommerce/db-credentials")
conn_string = (
    f"postgresql://{db_creds['username']}:{db_creds['password']}"
    f"@{db_creds['host']}:5432/{db_creds['dbname']}"
)
```

**3. Encrypt Everything**

```hcl
resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
```

> **Common Mistake**
> - Using your root AWS account for daily work. Create an IAM user.
> - S3 buckets accidentally set to public. Always block public access.
> - Committing `.env` files with real credentials to Git. Add `.env` to `.gitignore`.

### Checkpoint

1. What should you set up BEFORE creating any AWS resources?
2. How much cheaper is S3 Glacier compared to S3 Standard?
3. What does "principle of least privilege" mean for IAM policies?

---

## 8.7 Module 8 Project -- Deploy Your Pipeline to AWS

> **TL;DR:** Deploy your Airflow pipeline to AWS using Terraform for infrastructure, Docker for packaging, and GitHub Actions for CI/CD. Use MinIO locally as an S3 substitute. The Terraform configs themselves are the primary deliverable -- you don't have to `apply` to a real AWS account if you don't want to spend money.

### Overview

Deploy your Airflow pipeline (from Modules 4 and 7) to AWS using:

- **Terraform** to provision S3, RDS, ECS, IAM
- **Docker** to containerize Airflow and your pipeline code
- **GitHub Actions** for CI/CD
- **MinIO** as a local S3 substitute for development

### Project Structure

```
module-8-project/
|-- terraform/
|   |-- main.tf
|   |-- variables.tf
|   |-- s3.tf
|   |-- rds.tf
|   |-- iam.tf
|   |-- ecs.tf              # Bonus
|   |-- outputs.tf
|   |-- terraform.tfvars.example
|-- docker/
|   |-- Dockerfile
|   |-- Dockerfile.airflow
|-- .github/
|   |-- workflows/
|       |-- pipeline.yml
|-- src/
|   |-- pipeline/
|       |-- __init__.py
|       |-- extract.py
|       |-- transform.py
|       |-- load.py
|       |-- quality.py
|-- dags/
|   |-- ecommerce_pipeline.py
|-- tests/
|   |-- test_extract.py
|   |-- test_transform.py
|   |-- test_quality.py
|-- docker-compose.yml
|-- pyproject.toml
|-- README.md
```

### Step 1: Terraform Infrastructure

Create the Terraform configs from this module. At minimum:

- S3 bucket with versioning, encryption, lifecycle rules, and public access block
- RDS Postgres instance with security group
- IAM role with least-privilege policy for S3 and RDS access
- CloudWatch billing alarm

```bash
cd terraform
terraform init
terraform plan -var="db_password=localtest123"
```

> **Pro Tip:** You don't have to actually `terraform apply` to a real AWS account if you don't want to spend money. The configs themselves are the deliverable. But if you have free tier or credits, go for it.

### Step 2: Dockerize the Pipeline

Write a production-grade Dockerfile with:

- Multi-stage build
- Non-root user
- Layer ordering optimized for caching
- Health check

```bash
docker build -t ecommerce-pipeline .
docker run --rm ecommerce-pipeline --help
```

### Step 3: Docker Compose for Local Dev

Everything should start with one command:

```bash
docker-compose up -d
```

Include: your pipeline container, Postgres, MinIO, and Airflow (webserver + scheduler).

### Step 4: GitHub Actions CI/CD

Create `.github/workflows/pipeline.yml` that:

1. Runs on push to `main` and on PRs
2. Lints code (ruff)
3. Runs unit tests with a test Postgres service
4. Builds Docker image
5. (Optional) Pushes to ECR and deploys to ECS

### Step 5: Environment-Aware Configuration

Your pipeline code should work in both local development and production without code changes. See `module-8/solution/src/pipeline/config.py`:

```python
# src/pipeline/config.py
import os

class Config:
    """Environment-aware configuration."""
    ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

    # S3 / MinIO
    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    S3_BUCKET = os.getenv("S3_BUCKET", "ecommerce-data-lake")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")

    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ecommerce"
    )

    @classmethod
    def is_local(cls) -> bool:
        return cls.ENVIRONMENT == "dev"
```

In dev, the defaults point to your local Docker Compose services (MinIO, local Postgres). In production, environment variables override them to point at real AWS resources. No code changes, no `if` statements scattered through your pipeline.

### Expected Output

- `terraform plan` runs without errors and shows resources to be created
- `docker-compose up` starts all services and the pipeline runs
- GitHub Actions workflow passes on push
- Pipeline reads from and writes to MinIO/S3

### Completion Checklist

- [ ] Terraform configs for S3, RDS, IAM, and billing alarm
- [ ] S3 bucket has versioning, encryption, lifecycle rules, public access block
- [ ] RDS has security group restricting access
- [ ] IAM role follows least privilege
- [ ] No secrets hardcoded anywhere
- [ ] Dockerfile uses multi-stage build, non-root user
- [ ] docker-compose.yml starts full stack locally
- [ ] GitHub Actions workflow runs tests and builds Docker image
- [ ] Pipeline code uses environment variables for configuration
- [ ] README explains how to run locally and how to deploy

---

## What's Next

Module 9 explores data engineering for AI -- embeddings pipelines, feature stores, vector databases, and RAG systems. The infrastructure skills you learned in this module are what make those AI systems production-ready: you'll deploy embedding pipelines in containers, store vectors in managed databases, and use CI/CD to keep everything running reliably.

*End of Module 8*
