# Module 7: Data Lakes & Lakehouse Architecture

## The Data Lake Promise (and Pitfalls)

The data lake concept was revolutionary: dump *everything* into cheap object storage — structured tables, JSON logs, images, videos, sensor data — and figure out how to use it later. At a fraction of the cost of a warehouse, you'd have all your data in one place, ready for any analysis.

The reality? Many data lakes became **data swamps** — vast repositories of undocumented, ungoverned data that nobody could find or trust. Without schema enforcement, without access controls, without lineage tracking, the lake filled with duplicates, stale data, and mysterious files that nobody remembered creating.

The problem wasn't the concept — it was the lack of governance. A data lake without cataloging, quality checks, and access controls is just a very expensive file share.

> **Key Takeaway:** The data lake is still the right foundation for modern data architecture — object storage is too cheap and flexible to ignore. But success requires treating it as an engineered system with zones, schemas, quality gates, and governance, not as a dumping ground.

---

## Zone-Based Architecture

The solution to the data swamp is organizing the lake into zones with clear purposes, ownership, and quality expectations.

### Raw / Landing Zone

**Purpose**: Exact copies of source data, as-is. No transformations, no cleaning. This is your audit trail and reprocessing safety net.

**Contents**: CSV files from SFTP drops, JSON from API extractions, Parquet files from database exports, log files, images, PDFs.

**Rules**: Append-only (never modify), partitioned by source and ingestion date, retained for 1-7 years depending on compliance requirements.

```
s3://data-lake/raw/
  ├── postgres_orders/dt=2026-04-01/orders.parquet
  ├── stripe_payments/dt=2026-04-01/payments.json
  ├── web_events/dt=2026-04-01/events.json.gz
  └── support_tickets/dt=2026-04-01/tickets.csv
```

### Cleansed / Curated Zone

**Purpose**: Cleaned, validated, and standardized data. Consistent column names, correct data types, deduplication applied, schema enforced.

**Contents**: Parquet/Delta files with enforced schemas. Each dataset has an owner and a documented SCD (slowly changing dimension) strategy.

**Rules**: Schema-on-write enforced, quality checks must pass before data lands here, versioned with change tracking.

### Analytics / Consumption Zone

**Purpose**: Business-ready datasets optimized for specific use cases. Aggregations, feature tables, materialized views.

**Contents**: Star schemas for BI tools, feature tables for ML, pre-aggregated metrics for dashboards.

**Rules**: Tight access controls, SLA on freshness, documented lineage from raw to consumption.

The data flows through zones like water through a treatment plant: raw water (landing) → filtered and treated (cleansed) → safe to drink (consumption). Each stage adds quality and removes impurities.

---

## The Lakehouse Revolution

The traditional architecture forced a choice: data lake (cheap, flexible, but no transactions or governance) or data warehouse (reliable, governed, but expensive and limited to structured data). Most companies ran both, connected by ETL pipelines that copied data from lake to warehouse.

The **lakehouse** eliminates this duplication by adding warehouse-like capabilities directly to the data lake: ACID transactions, schema enforcement, indexing, and governance — all on top of cheap object storage.

### The Medallion Architecture (Bronze / Silver / Gold)

The most popular lakehouse pattern, pioneered by Databricks:

**Bronze Layer** (Raw): Ingested data with minimal processing. Append-only, preserves the original format. Includes metadata columns like ingestion timestamp and source.

**Silver Layer** (Cleansed): Cleaned, validated, and conformed data. Deduplication, type casting, null handling, schema enforcement. This is your "single source of truth."

**Gold Layer** (Business): Aggregated, business-ready datasets. Star schemas, feature tables, metric tables. Optimized for specific consumers.

```python
from delta.tables import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, when, trim, lower

spark = SparkSession.builder.appName("Medallion").getOrCreate()

# --- Bronze: Ingest raw data as-is, add metadata ---
def ingest_to_bronze(source_path: str, bronze_path: str):
    """Load raw data into the bronze layer.

    We add ingestion metadata but don't modify the source data.
    This preserves the original record for auditing and reprocessing.
    """
    raw_df = spark.read.json(source_path)
    bronze_df = raw_df \
        .withColumn("_ingested_at", current_timestamp()) \
        .withColumn("_source_file", col("_metadata.file_path"))

    bronze_df.write \
        .format("delta") \
        .mode("append") \
        .save(bronze_path)

# --- Silver: Clean and validate ---
def bronze_to_silver(bronze_path: str, silver_path: str):
    """Transform bronze data into clean, validated silver records.

    This is where data quality happens: type casting, null handling,
    deduplication, and standardization. If a record fails validation,
    it goes to a quarantine table instead of silver.
    """
    bronze_df = spark.read.format("delta").load(bronze_path)

    silver_df = bronze_df \
        .dropDuplicates(["order_id"]) \
        .filter(col("order_id").isNotNull()) \
        .withColumn("customer_email", lower(trim(col("customer_email")))) \
        .withColumn("order_total", col("order_total").cast("decimal(10,2)")) \
        .withColumn("status", when(
            col("status").isin("pending", "completed", "cancelled"),
            col("status")
        ).otherwise("unknown"))

    # Upsert: update existing records, insert new ones
    if DeltaTable.isDeltaTable(spark, silver_path):
        delta_table = DeltaTable.forPath(spark, silver_path)
        delta_table.alias("target").merge(
            silver_df.alias("source"),
            "target.order_id = source.order_id"
        ).whenMatchedUpdateAll() \
         .whenNotMatchedInsertAll() \
         .execute()
    else:
        silver_df.write.format("delta").save(silver_path)

# --- Gold: Business-ready aggregations ---
def silver_to_gold(silver_path: str, gold_path: str):
    """Build business-ready aggregations from silver data.

    Gold tables are optimized for specific consumers: dashboards,
    reports, ML features. They denormalize and pre-aggregate
    to minimize query complexity and latency.
    """
    silver_df = spark.read.format("delta").load(silver_path)

    daily_metrics = silver_df \
        .filter(col("status") == "completed") \
        .groupBy("order_date", "product_category") \
        .agg(
            {"order_total": "sum", "order_id": "countDistinct",
             "customer_id": "countDistinct"}
        ) \
        .withColumnRenamed("sum(order_total)", "revenue") \
        .withColumnRenamed("count(DISTINCT order_id)", "order_count") \
        .withColumnRenamed("count(DISTINCT customer_id)", "unique_customers")

    daily_metrics.write \
        .format("delta") \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .save(gold_path)
```

---

## Lakehouse Technologies Compared

### Delta Lake

Created by Databricks, Delta Lake is the most widely adopted lakehouse format. It stores data as Parquet files with a JSON-based transaction log (`_delta_log/`). Every operation creates a new log entry, enabling ACID transactions, time travel, and audit history.

**Strengths**: Tight Spark integration, mature tooling, large community, Z-ordering for multi-dimensional clustering, Change Data Feed for CDC.

### Apache Iceberg

Created at Netflix, Iceberg takes a different approach to metadata management. Instead of a simple transaction log, it maintains a hierarchy of metadata files, manifest lists, and manifest files that provide efficient metadata operations even at massive scale.

**Killer feature — Hidden partitioning**: Users don't need to know the partitioning scheme. If a table is partitioned by `month(event_date)`, you just query `WHERE event_date = '2026-04-01'` and Iceberg automatically prunes to the April partition. No need for synthetic partition columns.

**Killer feature — Partition evolution**: Change your partitioning strategy without rewriting data. Start with monthly partitions; switch to daily when volume grows. Old data keeps its old partitioning; new data uses the new scheme. Queries seamlessly span both.

### Apache Hudi

Created at Uber for near-real-time data lake ingestion. Hudi's strength is its two storage types that let you optimize for your read/write balance:

- **Copy-on-Write**: Every update rewrites the affected file. Read-optimized — queries always read clean Parquet files.
- **Merge-on-Read**: Updates go to a delta log; reads merge base files with deltas. Write-optimized — updates are fast, but reads do more work.

### When to Choose Which

| If you... | Choose |
|-----------|--------|
| Use Databricks | Delta Lake (native integration) |
| Need multi-engine support (Spark + Trino + Flink) | Iceberg (best multi-engine story) |
| Need near-real-time upserts from CDC | Hudi (designed for this use case) |
| Need partition evolution | Iceberg (best-in-class) |
| Want the largest community | Delta Lake |

---

## Performance Optimization

### File Compaction

Over time, streaming ingestion and frequent updates create many small files. Small files hurt query performance because each file has overhead (opening the file, reading metadata, scheduling work). **Compaction** merges small files into larger, optimally-sized ones:

```python
# Delta Lake: compact small files (OPTIMIZE)
spark.sql("OPTIMIZE silver.orders")

# With Z-ordering: co-locate related data for faster multi-column filters
spark.sql("OPTIMIZE silver.orders ZORDER BY (customer_id, order_date)")
```

### Z-Ordering

Z-ordering is a multi-dimensional clustering technique. It co-locates rows with similar values across multiple columns in the same files, so filters on any of those columns can skip more files. It's especially useful when queries filter on different combinations of columns.

### Data Skipping

Modern table formats store min/max statistics per column per file. When a query has a filter like `WHERE amount > 1000`, the engine checks each file's statistics and skips files where `max(amount) < 1000`. More data skipping = less I/O = faster queries.

> **Key Takeaway:** Lakehouse performance depends on physical data layout. Compact small files regularly, use Z-ordering on frequently filtered columns, and monitor data skipping effectiveness. A well-organized lakehouse can match warehouse query performance at a fraction of the cost.

---

## Multi-Format Data Handling

A key advantage of lakehouses over warehouses is handling data variety:

**Structured data** (CSVs, database exports): Convert to Parquet/Delta on ingestion. This is the most common and best-supported path.

**Semi-structured data** (JSON, XML, Avro): Modern engines handle nested and semi-structured data natively. Spark and BigQuery can query JSON fields directly, and Iceberg supports nested types in its schema.

**Unstructured data** (images, PDFs, audio): Store the raw files in object storage. Create metadata tables in the lakehouse that reference the file paths and contain extracted features (image embeddings, OCR text, audio transcriptions). Query the metadata to find relevant files.

```python
# Semi-structured: query nested JSON fields directly
events = spark.read.format("delta").load("s3://lake/silver/events")

# Extract nested fields without flattening the entire structure
events.select(
    col("event_id"),
    col("user.name").alias("user_name"),
    col("user.preferences.theme").alias("theme"),
    col("metadata.device_type").alias("device"),
).filter(col("metadata.device_type") == "mobile")
```

---

## Case Study: Pinterest's Data Lakehouse

Pinterest processes over 1 billion events per day from 450+ million monthly active users. They migrated from a traditional Hadoop-based data lake to a lakehouse architecture to solve three problems:

1. **Data quality**: Raw files had no schema enforcement, leading to silent data corruption that wasn't caught until dashboards showed wrong numbers days later.

2. **Slow queries**: Small files from streaming ingestion meant queries read thousands of tiny files. A query that should take 30 seconds took 10 minutes.

3. **No updates/deletes**: GDPR required deleting user data on request. With plain Parquet files, "deleting" a user meant rewriting entire partitions — expensive and slow.

**Solution**: They adopted Apache Iceberg as their table format, which gave them ACID transactions (schema enforcement and consistent reads), hidden partitioning (simpler queries, automatic pruning), and row-level deletes (GDPR compliance without rewriting entire partitions).

**Results**: Query performance improved 3-5x from better file organization and data skipping. GDPR deletion requests went from hours to minutes. Data quality issues dropped by 80% with schema enforcement. Storage costs decreased 30% from better compression and reduced data duplication.

> **Key Takeaway:** The lakehouse isn't just a theoretical improvement — it solves real operational problems: data quality, query performance, compliance, and cost. If you're running a data lake today, adopting a table format (Delta, Iceberg, or Hudi) is the single highest-ROI improvement you can make.

---

## What's Next

With storage and processing covered, Module 8 shifts to one of the fastest-growing areas in data engineering: ML platforms and feature stores. You'll learn how to bridge the gap between experimental ML in notebooks and production ML serving millions of predictions per day.
