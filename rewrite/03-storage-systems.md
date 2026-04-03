# Module 3: Storage Systems Deep Dive

## The Storage Landscape

Choosing the right storage engine is one of the highest-impact decisions in system design. It's also one of the most misunderstood. Teams often pick a database because they've used it before or because it's popular, without considering whether it actually fits their workload.

Here's the fundamental distinction: **OLTP** (Online Transaction Processing) systems handle lots of small, fast reads and writes — a user adding an item to their cart, a payment being processed, a profile being updated. **OLAP** (Online Analytical Processing) systems handle few, large, complex reads — "What was our revenue by region last quarter?" or "Which products have declining sales trends?"

Think of it this way: an online store has two very different data needs. The checkout flow is OLTP — it processes one order at a time, needs to be fast, and must be correct (you can't charge the wrong amount). The monthly sales report is OLAP — it scans millions of rows, aggregates numbers, and generates summaries. Trying to do both with the same storage engine leads to one workload starving the other.

> **Key Takeaway:** There is no universal "best" database. The right choice depends on whether your primary workload is transactional (OLTP), analytical (OLAP), or a mix. Most real systems need both, often using different storage engines connected by data pipelines.

---

## OLTP Storage Engines

OLTP databases are optimized for point lookups and small writes. The two dominant approaches differ in how they organize data on disk.

### B-Tree Engines (PostgreSQL, MySQL InnoDB)

B-trees are the classic approach, used by most relational databases. They organize data in a balanced tree structure where each "page" (typically 4-16 KB) contains sorted keys and pointers to child pages. Finding any record requires traversing from the root to a leaf — typically 3-4 page reads, regardless of how much data you have.

**Strengths**: Fast reads, efficient range queries, mature and well-understood, good for read-heavy workloads.

**How writes work**: To update a record, the database finds the page containing that record and overwrites it in place. To ensure durability, every change is first written to a **Write-Ahead Log (WAL)** — a sequential append-only file. If the database crashes mid-write, the WAL can replay uncommitted changes on restart.

### LSM-Tree Engines (RocksDB, Cassandra, LevelDB)

LSM-trees (Log-Structured Merge Trees) take a different approach: all writes go to an in-memory buffer (memtable). When the buffer fills up, it's flushed to disk as a sorted file called an **SSTable** (Sorted String Table). Over time, background processes merge SSTables together (**compaction**) to keep read performance manageable.

**Strengths**: Extremely fast writes (sequential I/O only), good compression, excellent for write-heavy workloads.

**Trade-off**: Reads may need to check multiple SSTables before finding a value. Bloom filters help skip SSTables that definitely don't contain a key, but reads are still generally slower than B-tree point lookups.

### When to Choose Which

| Factor | B-Tree (PostgreSQL) | LSM-Tree (Cassandra) |
|--------|--------------------|-----------------------|
| Read speed | Faster (single lookup) | Slower (check multiple SSTables) |
| Write speed | Slower (random I/O, in-place updates) | Faster (sequential I/O, append-only) |
| Space efficiency | Moderate (fragmentation) | Better (compaction reduces waste) |
| Read-heavy workloads | Excellent | Good |
| Write-heavy workloads | Good | Excellent |
| Transactions | Full ACID support | Limited or none |
| Scaling | Primarily vertical | Horizontally scalable |
| Use cases | Web apps, e-commerce, CMS | IoT, time-series, messaging, logging |

Here's a PostgreSQL example showing typical OLTP patterns — notice how each query touches a small number of rows:

```sql
-- OLTP pattern: point lookup by primary key
SELECT name, email, subscription_tier
FROM users
WHERE user_id = 'usr_12345';

-- OLTP pattern: insert a single row with constraints
INSERT INTO orders (customer_id, total_amount, status)
VALUES ('usr_12345', 89.99, 'pending')
RETURNING order_id;

-- OLTP pattern: update one row in a transaction
BEGIN;
  UPDATE inventory
  SET quantity = quantity - 1, reserved = reserved + 1
  WHERE product_id = 'prod_67890' AND quantity > 0;
COMMIT;
```

These queries are fast because they touch few rows and use indexed lookups. The same database would struggle with "scan all 500 million orders and compute monthly revenue by region" — that's an OLAP query.

---

## OLAP and Columnar Storage

Analytical queries have a fundamentally different access pattern than transactional ones. Instead of reading all columns for one row, they read a few columns across millions of rows.

### Why Row-Based Storage Fails for Analytics

In a traditional row-based database, data is stored row by row on disk:

```
Row 1: [user_id=1, name="Alice", email="alice@ex.com", city="NYC", signup_date="2025-01-15"]
Row 2: [user_id=2, name="Bob", email="bob@ex.com", city="LA", signup_date="2025-02-20"]
Row 3: [user_id=3, name="Charlie", email="charlie@ex.com", city="NYC", signup_date="2025-03-10"]
```

To answer "How many users are in NYC?", the database reads *every column of every row* from disk, even though it only needs `city`. For a table with 50 columns and a billion rows, that's 49 columns of wasted I/O.

### Column-Oriented Storage

Columnar databases store data column by column:

```
user_id column:    [1, 2, 3, ...]
name column:       ["Alice", "Bob", "Charlie", ...]
city column:       ["NYC", "LA", "NYC", ...]
signup_date column: ["2025-01-15", "2025-02-20", "2025-03-10", ...]
```

Now "How many users are in NYC?" only reads the `city` column — a fraction of the data. Better still, columns compress extremely well because adjacent values are often similar:

- **Run-Length Encoding**: `["NYC", "NYC", "NYC", "LA", "LA"]` becomes `[("NYC", 3), ("LA", 2)]`
- **Dictionary Encoding**: Replace repeated strings with small integers. If "NYC" appears a million times, store the integer `0` a million times and keep one mapping: `{0: "NYC", 1: "LA", ...}`
- **Bit-Packing**: A column with 4 unique values needs only 2 bits per value instead of a full string

These techniques can reduce storage by 10x or more, which also means 10x less I/O for queries.

### Modern Columnar Engines

**ClickHouse**: Open-source, extremely fast for aggregation queries. Uses its own MergeTree engine. Popular for real-time analytics dashboards and log analysis.

**Apache Druid**: Optimized for sub-second OLAP queries on event data. Pre-aggregates data on ingestion. Popular for user-facing analytics.

**Google BigQuery**: Serverless columnar warehouse based on Google's Dremel technology. You pay per query (data scanned) with no infrastructure to manage. Excellent for variable workloads.

> **Key Takeaway:** Columnar storage is dramatically faster for analytics because it reads only the columns a query needs and compresses those columns efficiently. If your queries scan millions of rows but only use a few columns — and most analytical queries do — columnar storage is the clear choice.

---

## Modern Table Formats: Parquet, Delta Lake, Iceberg, Hudi

The traditional approach — store raw files on a data lake, query them with Spark or Presto — worked but had serious problems: no transactions, no schema enforcement, terrible performance with many small files, and no way to update or delete individual records.

Modern table formats solve these problems by adding database-like features on top of object storage.

### Apache Parquet

Parquet is a **columnar file format**, not a table format. It's the building block that the others are built on. A Parquet file organizes data into row groups (typically 128 MB each), where each column within a row group is stored contiguously and compressed independently.

Every Parquet file contains metadata: min/max values per column per row group, null counts, and encoding information. Query engines use this metadata to skip entire row groups that can't contain relevant data — a technique called **predicate pushdown**.

### Delta Lake

Delta Lake, created by Databricks, adds **ACID transactions** to data lakes. It works by maintaining a transaction log (`_delta_log/`) alongside your Parquet data files. Every operation (write, update, delete) creates a new log entry describing what changed.

Key capabilities:
- **ACID transactions**: Multiple writers can safely update the same table concurrently
- **Time travel**: Query data as it existed at any previous point in time
- **Schema enforcement**: Reject writes that don't match the expected schema
- **Schema evolution**: Safely add new columns without rewriting existing data

Here's how Delta Lake operations look in PySpark. Notice how they feel like database operations, but they're running on files in S3 or HDFS:

```python
from delta.tables import DeltaTable
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("DeltaLakeDemo") \
    .config("spark.jars.packages", "io.delta:delta-core_2.12:2.4.0") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .getOrCreate()

# Write a DataFrame as a Delta table — creates Parquet files + transaction log
df = spark.read.json("s3://data-lake/raw/events/2026-04-01/")
df.write.format("delta").mode("overwrite").save("s3://data-lake/silver/events")

# Read the Delta table — exactly like reading a regular table
events = spark.read.format("delta").load("s3://data-lake/silver/events")

# MERGE operation — upsert (update existing rows, insert new ones)
# This is impossible with plain Parquet files
delta_table = DeltaTable.forPath(spark, "s3://data-lake/silver/events")
delta_table.alias("target").merge(
    new_data.alias("source"),
    "target.event_id = source.event_id"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()

# Time travel — query the table as it was 24 hours ago
yesterday = spark.read.format("delta") \
    .option("timestampAsOf", "2026-04-01") \
    .load("s3://data-lake/silver/events")
```

### Apache Iceberg

Created at Netflix, Iceberg focuses on **correctness and performance at scale**. Its killer features:

- **Hidden partitioning**: You define partition transforms (e.g., "partition by month of event_date") and Iceberg handles the details. Users don't need to know the partitioning scheme to write efficient queries.
- **Partition evolution**: Change your partitioning strategy without rewriting data. Start partitioned by day; switch to hour when volume increases.
- **Snapshot isolation**: Readers and writers never conflict. Readers see a consistent snapshot while writes proceed concurrently.

### Apache Hudi

Created at Uber for their incremental processing needs, Hudi (Hadoop Upserts Deletes and Incrementals) provides two storage types:

- **Copy-on-Write (CoW)**: Rewrites entire files on every update. Optimal for read-heavy workloads.
- **Merge-on-Read (MoR)**: Writes updates to a delta log, merging on read. Optimal for write-heavy workloads with less frequent reads.

### Comparison

| Feature | Delta Lake | Iceberg | Hudi |
|---------|-----------|---------|------|
| ACID transactions | Yes | Yes | Yes |
| Time travel | Yes | Yes | Yes |
| Schema evolution | Yes | Yes | Yes |
| Hidden partitioning | No | Yes | No |
| Partition evolution | Limited | Yes | Limited |
| Upsert support | Yes | Yes | Yes (core feature) |
| Incremental queries | Yes | Yes | Yes (core feature) |
| Best for | Databricks ecosystem | Multi-engine, correctness | Incremental processing |
| Origin | Databricks | Netflix | Uber |

> **Key Takeaway:** If you're building a data lake today, use a table format. Delta Lake is the default if you're in the Databricks ecosystem. Iceberg is the best choice for multi-engine environments and complex partitioning needs. Hudi excels at incremental processing and near-real-time ingestion.

---

## Object Storage Patterns

Object storage (S3, GCS, Azure Blob Storage) is the foundation of modern data systems. It's virtually unlimited in capacity, extremely durable (11 nines), and cheap — roughly $0.023/GB/month for standard storage. Nearly every data lake, lakehouse, and modern data platform stores its data here.

### Partitioning Strategies

How you organize files in object storage dramatically affects query performance. The standard approach is **Hive-style partitioning**, where the directory path encodes partition values:

```
s3://data-lake/events/
  year=2026/month=04/day=01/part-00000.parquet
  year=2026/month=04/day=01/part-00001.parquet
  year=2026/month=04/day=02/part-00000.parquet
  year=2026/month=03/day=31/part-00000.parquet
```

A query filtering on `WHERE year=2026 AND month=04 AND day=01` only lists and reads files in that specific directory, skipping everything else. Without partitioning, the query engine would need to scan every file in the entire dataset.

Here's a Python example showing how to write partitioned data to S3 and set up lifecycle policies for cost optimization. The lifecycle policy automatically moves old data to cheaper storage tiers:

```python
import boto3
from datetime import datetime

s3 = boto3.client('s3')

def upload_partitioned_data(bucket: str, data: bytes, event_date: datetime):
    """Upload data to S3 with Hive-style partitioning.

    The key (path) encodes the date, so query engines can use
    partition pruning to skip irrelevant files.
    """
    key = (
        f"events/"
        f"year={event_date.year}/"
        f"month={event_date.month:02d}/"
        f"day={event_date.day:02d}/"
        f"data-{datetime.utcnow().strftime('%H%M%S')}.parquet"
    )
    s3.put_object(Bucket=bucket, Key=key, Body=data)
    return key

def setup_lifecycle_policy(bucket: str):
    """Configure storage tiering to reduce costs automatically.

    Hot data (recent) stays in Standard storage for fast access.
    After 90 days, it moves to Infrequent Access (50% cheaper).
    After 365 days, it moves to Glacier (90% cheaper).
    After 7 years, it's deleted (compliance retention met).
    """
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            'Rules': [
                {
                    'ID': 'tiered-storage',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'events/'},
                    'Transitions': [
                        {'Days': 90, 'StorageClass': 'STANDARD_IA'},
                        {'Days': 365, 'StorageClass': 'GLACIER'},
                    ],
                    'Expiration': {'Days': 2555},  # ~7 years
                }
            ]
        }
    )
```

### Storage Tiers

| Tier | Cost (per GB/month) | Access Time | Use Case |
|------|---------------------|-------------|----------|
| Standard | $0.023 | Milliseconds | Active data, frequent access |
| Infrequent Access | $0.0125 | Milliseconds | Older data, occasional access |
| Glacier | $0.004 | Minutes to hours | Archives, compliance |
| Glacier Deep Archive | $0.00099 | 12+ hours | Regulatory retention |

A well-designed lifecycle policy can cut storage costs by 60-80% for data that ages out of active use.

---

## HTAP: Bridging OLTP and OLAP

The traditional pattern — separate OLTP and OLAP systems connected by ETL — works but introduces latency. Your analytics are always hours behind reality. **HTAP** (Hybrid Transactional/Analytical Processing) databases aim to handle both workloads in a single system.

**TiDB**: A MySQL-compatible distributed database that separates transaction processing (TiKV, row-based) from analytical processing (TiFlash, columnar). Writes go to TiKV; TiFlash maintains a columnar replica for analytics. Queries are automatically routed to the appropriate engine.

**CockroachDB**: A distributed SQL database with strong consistency. Handles OLTP well and has improving analytical capabilities, though it's not a replacement for a dedicated warehouse at large scale.

**SingleStore (formerly MemSQL)**: An in-memory database that supports both row and column storage. Tables can be configured as row-store (OLTP) or column-store (OLAP).

**When HTAP makes sense**: Small to medium scale where operational and analytical queries run on the same data and you want to avoid the complexity of a separate data warehouse and ETL pipeline. When your analytics need to reflect the latest transactions immediately.

**When to keep systems separate**: Large scale where OLTP and OLAP workloads would interfere with each other, when you need specialized analytical features (star schemas, materialized views, window functions), or when your analytical data comes from multiple sources.

---

## Choosing the Right Storage: A Decision Framework

When facing a storage decision, work through these questions in order:

1. **What's the primary access pattern?**
   - Point lookups and small writes → OLTP (PostgreSQL, MySQL, DynamoDB)
   - Full table scans and aggregations → OLAP (BigQuery, Snowflake, ClickHouse)
   - Key-value lookups at extreme speed → Cache (Redis) or Key-Value store (DynamoDB)

2. **What's the data structure?**
   - Structured with relationships → Relational (PostgreSQL)
   - Hierarchical/flexible → Document (MongoDB)
   - Relationship-heavy → Graph (Neo4j)
   - Time-series → Specialized (InfluxDB, TimescaleDB)

3. **What are the consistency requirements?**
   - Strong consistency (financial, inventory) → ACID database
   - Eventual consistency acceptable (social feeds, analytics) → AP systems (Cassandra, DynamoDB)

4. **What's the scale?**
   - Moderate (< 1TB, < 10K QPS) → Almost anything works; pick what your team knows
   - Large (1-100 TB, 10K-100K QPS) → Requires careful selection and potentially sharding
   - Massive (100+ TB, 100K+ QPS) → Specialized distributed systems, often multiple engines

5. **What's the team's expertise?**
   - This matters more than people admit. A team that knows PostgreSQL deeply will outperform one using Cassandra for the first time, even if Cassandra is the "better" theoretical fit.

> **Key Takeaway:** Start with the simplest storage that meets your requirements. PostgreSQL is remarkably capable — it handles JSON documents, full-text search, geospatial queries, and moderate analytics in addition to traditional relational workloads. Only introduce specialized systems when you have a clear need that PostgreSQL can't meet.

---

## What's Next

Now that you understand how data is stored, Module 4 covers how it's *processed*. We'll explore batch processing — the workhorse of data engineering — including ETL pipelines, workflow orchestration with Airflow, and the architectural patterns (Lambda and Kappa) that determine how batch and stream processing coexist.
