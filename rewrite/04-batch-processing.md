# Module 4: Batch Processing & ETL

## What is Batch Processing?

Batch processing is the workhorse of data engineering. While real-time systems get the headlines, the vast majority of data work — loading data warehouses, training ML models, generating reports, computing aggregations — happens in batches.

**Batch processing** means collecting data over a period of time, then processing it all at once. Your bank doesn't update your monthly statement in real-time — it waits until the month ends, processes all transactions, and generates the statement. That's batch processing.

The advantages are significant: batch jobs can be optimized for throughput (process a billion rows efficiently), they're easier to debug (you can re-run the same input and get the same output), and they're more cost-effective (you spin up compute resources, do the work, then shut them down).

> **Key Takeaway:** Not everything needs to be real-time. If the business can tolerate data that's hours old, batch processing is simpler, cheaper, and more reliable. Save real-time processing for use cases that genuinely require it (fraud detection, live dashboards, real-time recommendations).

---

## Lambda vs. Kappa Architecture

How should batch and stream processing coexist in your system? Two dominant architectures address this question.

### Lambda Architecture

The Lambda architecture runs two parallel processing paths:

```
                    ┌→ [Batch Layer: Spark/Hadoop] → [Serving Layer]
[Data Source] → [Queue] ─┤                                           → [Query]
                    └→ [Speed Layer: Flink/Storm]  → [Serving Layer]
```

The **batch layer** processes all historical data periodically (e.g., every hour) to produce accurate, complete results. The **speed layer** processes data in real-time to produce approximate, up-to-date results. The query layer merges both views — recent data from the speed layer and historical data from the batch layer.

**Pros**: The batch layer is a simple, reliable source of truth. If the speed layer has a bug, the batch layer corrects it on the next run. You get both completeness and freshness.

**Cons**: You maintain two codebases doing essentially the same computation in different frameworks. This is the Lambda architecture's fatal flaw — the dual maintenance burden is brutal in practice.

### Kappa Architecture

The Kappa architecture simplifies by eliminating the batch layer entirely:

```
[Data Source] → [Event Log (Kafka)] → [Stream Processor] → [Serving Layer] → [Query]
```

All data flows through a single stream processing pipeline. If you need to reprocess historical data (because of a bug or a new computation), you replay events from the log.

**Pros**: One codebase, one processing framework, simpler operations.

**Cons**: Stream processing is inherently more complex than batch. Replaying a year of events through a stream processor is slow. Some computations (complex ML training, graph algorithms) don't fit naturally into streaming.

### Which to Choose

For most teams starting out: **start with batch, add streaming when you have a genuine real-time requirement.** Lambda is appropriate when you need guaranteed correctness *and* real-time speed (e.g., financial reporting). Kappa works well when your primary processing is event-driven and reprocessing is manageable.

---

## ETL vs. ELT

**ETL (Extract, Transform, Load)**: Data is extracted from sources, transformed in a separate processing engine (Spark, Python scripts), then loaded into the destination. This was the standard when data warehouses had limited compute and expensive storage.

**ELT (Extract, Load, Transform)**: Data is extracted and loaded into the destination *first* (raw), then transformed using the destination's own compute engine. This is the modern approach, enabled by cloud warehouses with massive, elastic compute.

```
ETL:  Source → [Transform in Spark] → Warehouse (clean data)
ELT:  Source → Warehouse (raw data) → [Transform in SQL/dbt] → Warehouse (clean data)
```

**Why ELT won for cloud warehouses**: Cloud warehouses like Snowflake and BigQuery have virtually unlimited compute. It's cheaper and simpler to load raw data and transform it using SQL than to maintain a separate Spark cluster. Plus, keeping the raw data means you can always re-transform it if your logic changes.

**dbt (data build tool)** is the poster child of ELT. It lets you define transformations as SQL SELECT statements, manages dependencies between transformations, runs tests, and generates documentation:

```sql
-- models/staging/stg_orders.sql
-- dbt model: clean and standardize raw order data

SELECT
    id AS order_id,
    user_id AS customer_id,
    CAST(created_at AS TIMESTAMP) AS order_date,
    CAST(total AS DECIMAL(10,2)) AS order_total,
    LOWER(TRIM(status)) AS order_status,
    CASE
        WHEN LOWER(TRIM(status)) IN ('completed', 'delivered') THEN TRUE
        ELSE FALSE
    END AS is_completed
FROM {{ source('raw', 'orders') }}
WHERE id IS NOT NULL
  AND created_at IS NOT NULL
```

---

## Workflow Orchestration

A real data pipeline isn't a single script — it's a sequence of interdependent tasks: extract from 5 sources, clean each one, join them together, load into the warehouse, run quality checks, refresh dashboards. If the extraction fails, everything downstream should wait. If the quality check fails, the dashboard shouldn't update.

**Workflow orchestrators** manage these dependencies, handle retries, send alerts on failure, and provide visibility into what's running.

### Apache Airflow

Airflow is the dominant orchestrator. You define workflows as **DAGs** (Directed Acyclic Graphs) in Python. Each node in the DAG is a **task** — a unit of work like "run a SQL query" or "execute a Python function." Edges define dependencies.

Here's a complete Airflow DAG for a daily analytics pipeline. This is a realistic example — it extracts data from multiple sources, transforms it, runs quality checks, and loads the results:

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.email import EmailOperator
from airflow.utils.task_group import TaskGroup

default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'email_on_failure': True,
    'email': ['data-alerts@company.com'],
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# The DAG runs daily at 6 AM UTC, processing the previous day's data.
# catchup=False means it won't backfill missed runs on first deploy.
with DAG(
    dag_id='daily_analytics_pipeline',
    default_args=default_args,
    description='Daily ETL: extract, transform, quality check, load',
    schedule_interval='0 6 * * *',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['analytics', 'daily'],
) as dag:

    def extract_orders(**context):
        """Extract orders from the transactional database.

        Uses the execution_date to only pull yesterday's orders,
        making this pipeline idempotent — running it twice for
        the same date produces the same result.
        """
        execution_date = context['ds']  # YYYY-MM-DD string
        # In production: query source DB, write to staging area
        print(f"Extracting orders for {execution_date}")

    def extract_payments(**context):
        """Extract payment data from the payment provider API."""
        execution_date = context['ds']
        print(f"Extracting payments for {execution_date}")

    def transform_and_join(**context):
        """Join orders with payments, compute derived metrics.

        This task depends on both extractions completing successfully.
        If either fails, this task won't run.
        """
        execution_date = context['ds']
        print(f"Transforming data for {execution_date}")

    def run_quality_checks(**context):
        """Validate transformed data before loading to production.

        Checks: row counts within expected range, no null primary keys,
        amounts are positive, dates are valid. Raises an exception
        (failing the task) if any check fails.
        """
        execution_date = context['ds']
        print(f"Running quality checks for {execution_date}")

    # Task Group: Extraction (these run in parallel)
    with TaskGroup('extraction') as extract_group:
        extract_orders_task = PythonOperator(
            task_id='extract_orders',
            python_callable=extract_orders,
        )
        extract_payments_task = PythonOperator(
            task_id='extract_payments',
            python_callable=extract_payments,
        )

    # Transformation (depends on all extractions)
    transform_task = PythonOperator(
        task_id='transform_and_join',
        python_callable=transform_and_join,
    )

    # Quality checks (depends on transformation)
    quality_task = PythonOperator(
        task_id='quality_checks',
        python_callable=run_quality_checks,
    )

    # Load to production warehouse
    load_task = PostgresOperator(
        task_id='load_to_warehouse',
        postgres_conn_id='warehouse',
        sql='sql/load_daily_analytics.sql',
    )

    # Send completion notification
    notify_task = EmailOperator(
        task_id='send_notification',
        to='analytics-team@company.com',
        subject='Daily Analytics Pipeline Complete - {{ ds }}',
        html_content='Pipeline completed successfully for {{ ds }}.',
    )

    # Define the dependency chain
    extract_group >> transform_task >> quality_task >> load_task >> notify_task
```

The key things to notice:
- **Parallel extraction**: Orders and payments are extracted simultaneously (both are in the same TaskGroup with no dependency between them)
- **Idempotency**: Each task uses `execution_date` to process exactly one day's data, so re-running is safe
- **Failure handling**: 2 retries with 5-minute delays, email alerts on failure
- **Clear dependencies**: The `>>` operator makes the flow explicit and readable

### Dagster: A Modern Alternative

Dagster takes an **asset-based** approach instead of Airflow's **task-based** approach. Instead of defining "what to do" (tasks), you define "what to produce" (assets). Dagster figures out the execution order from asset dependencies. This is arguably a more natural way to think about data pipelines — you care about the outputs, not the steps.

> **Key Takeaway:** Use an orchestrator for any pipeline with more than one step. Airflow is the industry standard with the largest community and ecosystem. Dagster is a strong alternative with a more modern developer experience. Avoid running important pipelines as cron jobs — you'll miss the dependency management, retry logic, and visibility that orchestrators provide.

---

## Data Quality in Batch Pipelines

The most insidious production issue isn't a pipeline that fails — it's a pipeline that *succeeds with wrong data*. A silent data quality bug can propagate through your warehouse for weeks before anyone notices that revenue numbers are wrong.

Data quality checks should be a first-class part of every pipeline — not an afterthought.

### Practical Quality Checks

Here's a data quality validation framework you can use in any Python pipeline. Each check is simple, but together they catch the vast majority of data quality issues:

```python
from dataclasses import dataclass
from typing import List, Optional
import pandas as pd

@dataclass
class QualityCheckResult:
    check_name: str
    passed: bool
    details: str

def run_quality_checks(df: pd.DataFrame, table_name: str) -> List[QualityCheckResult]:
    """Run a suite of data quality checks on a DataFrame.

    Returns a list of results. If any check fails, the pipeline
    should stop and alert the team — loading bad data is worse
    than loading no data.
    """
    results = []

    # Check 1: Row count within expected range
    row_count = len(df)
    expected_min, expected_max = 1000, 1_000_000
    results.append(QualityCheckResult(
        check_name='row_count',
        passed=expected_min <= row_count <= expected_max,
        details=f"Got {row_count} rows (expected {expected_min}-{expected_max})"
    ))

    # Check 2: No null primary keys
    null_pks = df['id'].isnull().sum()
    results.append(QualityCheckResult(
        check_name='no_null_primary_keys',
        passed=null_pks == 0,
        details=f"Found {null_pks} null primary keys"
    ))

    # Check 3: No duplicate primary keys
    duplicate_pks = df['id'].duplicated().sum()
    results.append(QualityCheckResult(
        check_name='no_duplicate_primary_keys',
        passed=duplicate_pks == 0,
        details=f"Found {duplicate_pks} duplicate primary keys"
    ))

    # Check 4: Freshness — most recent record is within expected window
    if 'created_at' in df.columns:
        max_date = pd.to_datetime(df['created_at']).max()
        hours_old = (pd.Timestamp.now() - max_date).total_seconds() / 3600
        results.append(QualityCheckResult(
            check_name='data_freshness',
            passed=hours_old < 48,
            details=f"Most recent record is {hours_old:.1f} hours old"
        ))

    # Check 5: Numeric values in valid range
    if 'amount' in df.columns:
        negative_amounts = (df['amount'] < 0).sum()
        results.append(QualityCheckResult(
            check_name='no_negative_amounts',
            passed=negative_amounts == 0,
            details=f"Found {negative_amounts} negative amounts"
        ))

    return results
```

> **Key Takeaway:** Build quality checks into your pipeline, not after it. The pattern is: extract → transform → **validate** → load. If validation fails, the load doesn't happen. It's always better to have no data than wrong data.

---

## Cost Optimization for Batch

Batch processing has a natural cost advantage: you can schedule jobs for off-peak hours, use spot instances, and shut down resources when they're idle.

**Spot/Preemptible Instances**: Cloud providers sell excess compute capacity at 60-90% discounts. The catch: they can reclaim the instance with 2 minutes notice. Batch jobs are perfect for spot instances because they can be checkpointed and restarted. Configure your Spark or Airflow workers to use spot instances with on-demand instances as fallback.

**Right-Size Your Clusters**: Don't run a 20-node Spark cluster when 5 nodes would finish the job in the same time. Profile your jobs to find the sweet spot between parallelism and overhead.

**Incremental Processing**: Instead of reprocessing all historical data daily, only process what's new. If your pipeline processes the last 24 hours of data instead of the full history, it runs faster and costs less. Use `WHERE created_at > last_processed_timestamp` patterns, or leverage Delta Lake's Change Data Feed.

**Schedule Off-Peak**: Cloud compute often costs less at night and on weekends (lower demand). Schedule non-urgent batch jobs for off-peak hours.

---

## Case Study: Building a Daily Analytics Pipeline

Let's walk through designing a complete daily analytics pipeline for a SaaS company with 50,000 users generating events across a web app, mobile app, and API.

### Requirements

- **Sources**: PostgreSQL (transactional data), Stripe API (payments), Segment (web/mobile events), Zendesk (support tickets)
- **Output**: A Snowflake data warehouse feeding Tableau dashboards
- **Freshness**: Business stakeholders need yesterday's data by 9 AM
- **Scale**: ~2 GB of new data per day across all sources

### Architecture

```
Sources                    Staging (S3)         Transform          Warehouse
────────                   ───────────          ─────────          ─────────
PostgreSQL ──→ ┐
Stripe API ──→ ├──→ Raw Parquet on S3 ──→ dbt models ──→ Snowflake
Segment    ──→ │                               ↓
Zendesk    ──→ ┘                        Quality Checks
                                               ↓
                                    Airflow orchestrates everything
```

### Key Design Decisions

1. **ELT over ETL**: Load raw data to S3 first, then use dbt + Snowflake for transformation. This keeps raw data available for re-transformation and leverages Snowflake's compute.

2. **Idempotent extractions**: Each extractor writes to a date-partitioned path (`s3://staging/stripe/dt=2026-04-01/`). Re-running overwrites the same partition — safe and predictable.

3. **Quality gates**: After transformation, quality checks validate row counts, null rates, and referential integrity. If checks fail, the old data stays in place and the team is alerted.

4. **Incremental models**: dbt models are configured as incremental where possible — only processing rows with `updated_at` after the last run. This keeps dbt execution under 15 minutes even as data grows.

5. **Monitoring**: Pipeline duration, row counts per source, and Snowflake credit usage are tracked in Datadog. Alerts fire if the pipeline hasn't completed by 8 AM or if row counts deviate by more than 20% from the previous day.

> **Key Takeaway:** A good batch pipeline is idempotent (safe to re-run), observable (you know when it fails and why), incremental (processes only new data), and quality-gated (never loads bad data). These properties matter more than the specific technologies you choose.

---

## What's Next

Batch processing handles the bulk of data work, but some use cases can't wait for the next scheduled run. Module 5 introduces stream processing — how to handle data that arrives continuously and needs to be acted on immediately.
