# Module 5: Apache Spark & Big Data Processing

> **What you'll learn:** When your data gets too big for a single machine, Spark is the industry standard. By the end of this module you'll know PySpark the way it's actually used in production -- and just as importantly, when NOT to use it.

DuckDB has changed everything. You don't always need Spark anymore. But when your data hits 100GB+, Spark is still king. At a mid-to-large company, your daily batch jobs are probably Spark. Even if you never write a Spark job from scratch, you will inherit one, debug one, or optimize one. This module prepares you for all three.

---

## 5.1 When You Need Spark (And When You Don't)

> **TL;DR**
> - Most data engineers don't need Spark for their day-to-day work
> - DuckDB/Polars handle up to ~100GB on a single machine, often faster than Spark
> - Spark shines at 100GB+ or when you need distributed compute across a cluster
> - Learn it because job postings require it and you WILL eventually hit big data

Here's something that might be controversial: most data engineers don't need Spark. If you're processing 500MB of data daily, Spark is like renting a school bus to drive yourself to work. It works, but you're paying for 40 seats you're not using and it takes 10 minutes just to start the engine.

So why learn it? Because at some point in your career, you WILL hit data that's too big for a single machine. And when that happens, Spark is the industry standard.

### The Decision Framework

| Data Size | Recommended Tool | Why |
|-----------|-----------------|-----|
| < 1 GB | Pandas, Polars | Fits in memory, simple |
| 1--10 GB | DuckDB, Polars | Single machine, crazy fast |
| 10--100 GB | DuckDB (maybe Spark) | DuckDB handles this surprisingly well |
| 100 GB+ | Spark | You actually need distributed compute |
| 1 TB+ | Spark (cluster) | No question |

The twist: DuckDB and Polars have gotten ridiculously good. A modern laptop with 32GB RAM can process 50--100GB files with DuckDB. That wasn't true 3 years ago.

### Quick Comparison: DuckDB vs. Spark on 1GB

```python
# DuckDB -- processes 1GB CSV in seconds
import duckdb

con = duckdb.connect()
result = con.sql("""
    SELECT
        vendor_id,
        COUNT(*) as trips,
        AVG(total_amount) as avg_amount
    FROM read_csv('nyc_taxi_2024.csv')
    GROUP BY vendor_id
""").fetchdf()
# Time: ~3 seconds on a laptop
```

```python
# Spark on the same data -- significant overhead
from pyspark.sql import SparkSession
from pyspark.sql.functions import count, avg

spark = SparkSession.builder.appName("test").getOrCreate()
df = spark.read.csv("nyc_taxi_2024.csv", header=True, inferSchema=True)
result = df.groupBy("vendor_id").agg(
    count("*").alias("trips"),
    avg("total_amount").alias("avg_amount"),
)
result.show()
# Time: ~15-30 seconds (most of it is JVM startup)
```

DuckDB: 3 seconds. Spark: 20 seconds. On the same data.

### When You Actually Need Spark

1. **Data literally doesn't fit on one machine** -- 500GB+ with no single server large enough
2. **You need cluster-level processing** -- EMR, Databricks, Dataproc
3. **Your company already uses Spark** -- ecosystem is there, team knows it, infra exists
4. **Streaming at scale** -- Spark Structured Streaming for real-time processing
5. **Job postings require it** -- this is a valid reason

> **Pro Tip:** In production, companies sometimes spin up a 20-node Spark cluster to process 5GB daily. That's $3,000/month in cloud costs for something DuckDB could do on a $20/month server. Know your data size. Pick the right tool.

> **At your job:** When someone proposes using Spark for a new project, the first question you should ask is "how big is the data?" If the answer is under 50GB, push back and suggest DuckDB or Polars first. You'll save your team thousands in cloud costs and hours in development time. If the data is 500GB+, Spark is the obvious choice -- don't fight it.

---

## 5.2 Spark Architecture -- Drivers, Executors, Partitions

> **TL;DR**
> - Spark splits data into partitions and processes them in parallel across executors
> - The Driver coordinates everything; Executors do the actual work
> - Transformations are lazy (build a plan); Actions trigger execution
> - Shuffles (data exchange between executors) are the most expensive operation

If you don't understand Spark's architecture, you'll write code that's 10x slower than it should be. PySpark jobs that take 4 hours can often be optimized to 15 minutes just by understanding how data moves through the system.

### The Three Components

```
+-----------------------------------------------+
|                    DRIVER                      |
|  * Creates SparkSession                        |
|  * Builds execution plan                       |
|  * Coordinates executors                       |
|  * Collects results                            |
+-----------------------------------------------+
        |           |           |
   +---------+ +---------+ +---------+
   |Executor 1| |Executor 2| |Executor 3|
   |         | |         | |         |
   |Partition 0| |Partition 1| |Partition 2|
   |Partition 3| |Partition 4| |Partition 5|
   +---------+ +---------+ +---------+
```

**1. The Driver** -- The boss. Your main program runs here. It creates the SparkSession, reads your code, builds an execution plan, coordinates executors, and collects results. The driver runs on ONE machine. If you accidentally pull all your data to the driver (with `.collect()`), you'll crash it.

**2. Executors** -- The workers. They run on separate machines (or separate cores in local mode), store data partitions in memory, execute tasks, and report results back to the driver.

**3. Partitions** -- The data chunks. This is THE concept in Spark:
- Your data is split into partitions (chunks)
- Each partition is processed independently and in parallel
- More partitions = more parallelism (up to a point)
- Default: 200 partitions for shuffles, but configurable

Think of it like counting words in a library of 10,000 books. Without Spark, you read every book yourself. With Spark, you hire 10 workers, split the books into 10 piles, and each worker counts their pile simultaneously. 10x faster.

But if you need to SORT all the words alphabetically, the workers need to exchange data -- Worker A has some "Z" words that Worker B needs. This data exchange is called a **shuffle**, and it's the most expensive operation in Spark.

### Lazy Evaluation: Why It Matters

> **Key Concept: Transformations vs. Actions**
>
> Spark is lazy. It doesn't do anything until it absolutely has to.
>
> **Transformations** = instructions that build a plan (lazy): `filter()`, `select()`, `groupBy()`, `join()`, `withColumn()`
>
> **Actions** = triggers that execute the plan: `show()`, `count()`, `collect()`, `write()`
>
> This matters because Spark optimizes the entire chain before running it -- reordering operations, skipping unnecessary columns, combining steps. This is called the **Catalyst optimizer**.

This is not just a trivia fact for interviews. Lazy evaluation is what makes Spark fast at scale. Here's why:

Imagine you write this chain: read a 100GB file, add 5 columns, filter to 1% of rows, then group by category. A naive engine would read 100GB, compute 5 new columns on every row, THEN filter. But Spark's optimizer sees the whole plan and says: "Wait, I can push that filter earlier, read only the columns I need, and skip computing columns on rows I'm going to throw away." That single optimization can turn a 2-hour job into a 10-minute job.

```python
# This does NOTHING yet (just builds a plan)
df = spark.read.parquet("data/")
filtered = df.filter(df.amount > 100)
grouped = filtered.groupBy("category").count()

# THIS triggers execution of the entire chain
grouped.show()
```

> **At your job:** When your Spark job is slow, the first thing to check is the execution plan. Run `.explain(mode="formatted")` on your DataFrame before calling an action. Look for `BroadcastHashJoin` (good) vs `SortMergeJoin` (potentially slow), `Exchange` (shuffle -- expensive), and `FileScan` (are you reading all columns or just what you need?).

### Getting Started with PySpark

```bash
# Start PySpark with Docker
docker run -it --rm \
    -p 4040:4040 \
    -v $(pwd)/data:/data \
    apache/spark:3.5.1-python3 \
    /opt/spark/bin/pyspark
```

Or use the companion Docker Compose setup:

> **Companion code:** `de-fast-track/modules/module-5/starter/docker-compose.yml`

```yaml
services:
  spark-master:
    image: bitnami/spark:3.5.1
    environment:
      - SPARK_MODE=master
    ports:
      - "8081:8080"
      - "7077:7077"
    volumes:
      - ./scripts:/opt/spark-scripts
      - ./data:/opt/spark-data

  spark-worker:
    image: bitnami/spark:3.5.1
    environment:
      - SPARK_MODE=worker
      - SPARK_MASTER_URL=spark://spark-master:7077
    depends_on:
      - spark-master
```

```python
# In the PySpark shell -- SparkSession is pre-created as `spark`
data = [(i, f"product_{i % 10}", i * 9.99) for i in range(1000000)]
df = spark.createDataFrame(data, ["id", "product", "amount"])

# Check partitions
print(f"Number of partitions: {df.rdd.getNumPartitions()}")

# This is lazy -- nothing happens yet
filtered = df.filter(df.amount > 5000)
print("Filtered defined -- nothing executed yet")

# This triggers execution
count = filtered.count()
print(f"Count: {count}")
# Now check the Spark UI at http://localhost:4040 -- you'll see the completed job
```

Expected output:

```
Number of partitions: 8
Filtered defined -- nothing executed yet
Count: 499500
```

> **Common Mistake:**
>
> **Calling `.collect()` on large data** -- Pulls everything to the driver. 50GB of data = dead driver. Use `.show()` for previews, `.write()` for output.
>
> **Too few partitions** -- 100 cores but 10 partitions means 90 cores sit idle.
>
> **Too many partitions** -- 100,000 partitions for 1GB creates scheduling overhead. Rule of thumb: target ~128MB per partition.

---

## 5.3 DataFrames API -- Reading, Transforming, Writing Data

> **TL;DR**
> - The DataFrame API is where you spend 90% of your time in Spark
> - Always define schemas explicitly in production (don't use `inferSchema`)
> - Use Parquet for output -- it's 10x smaller and faster than CSV
> - `F.col()` is your best friend for column references

The DataFrame API is similar to Pandas, but distributed. If you know Pandas, you'll pick this up fast -- just some syntax differences.

### Reading Data

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("DataFrames Tutorial") \
    .config("spark.sql.adaptive.enabled", "true") \
    .getOrCreate()

# CSV (quick and dirty)
df_csv = spark.read \
    .option("header", "true") \
    .option("inferSchema", "true") \
    .csv("data/orders.csv")

# Parquet (preferred -- columnar, compressed, schema included)
df_parquet = spark.read.parquet("data/orders.parquet")

# JSON
df_json = spark.read.json("data/events.json")

# With explicit schema (faster and more reliable than inferSchema)
from pyspark.sql.types import (
    StructType, StructField, StringType,
    IntegerType, DoubleType, DateType
)

order_schema = StructType([
    StructField("order_id", IntegerType(), False),      # Not nullable
    StructField("customer_id", IntegerType(), False),
    StructField("product", StringType(), True),          # Nullable
    StructField("quantity", IntegerType(), True),
    StructField("price", DoubleType(), True),
    StructField("order_date", DateType(), True),
])

df = spark.read.schema(order_schema).csv("data/orders.csv", header=True)

# Always check your data after loading
df.printSchema()
df.show(5)
print(f"Rows: {df.count()}, Partitions: {df.rdd.getNumPartitions()}")
```

> **Pro Tip:** Always define your schema explicitly in production. `inferSchema=True` reads the entire file twice -- once to figure out types, once to actually load. On large files, that doubles your read time.

> **At your job:** The first time you load a new dataset, use `inferSchema` to see what Spark guesses. Then hardcode that schema. Your coworkers will thank you when the pipeline doesn't break because a column that was always integers suddenly has a string value in row 50 million.

### Transformations

Here's the companion code for exploring data with Spark (see `de-fast-track/modules/module-5/solution/scripts/01_explore.py`):

```python
from pyspark.sql import functions as F

# Select columns
df.select("order_id", "customer_id", "price").show()

# Filter rows
expensive = df.filter(F.col("price") > 100)
# Equivalently:
expensive = df.where(df.price > 100)

# Add computed columns
df_enriched = df.withColumn(
    "total", F.col("quantity") * F.col("price")
).withColumn(
    "tax", F.col("quantity") * F.col("price") * 0.08
).withColumn(
    "order_year", F.year("order_date")
)

# Rename columns
df_renamed = df.withColumnRenamed("price", "unit_price")

# Drop columns
df_slim = df.drop("some_unnecessary_column")

# Handle nulls
df_clean = df.fillna({"quantity": 0, "product": "unknown"})
df_no_nulls = df.dropna(subset=["order_id", "customer_id"])

# Type casting
df_typed = df.withColumn("price", F.col("price").cast("decimal(10,2)"))

# String operations
df_strings = df.withColumn(
    "product_upper", F.upper(F.col("product"))
).withColumn(
    "product_trimmed", F.trim(F.col("product"))
)

# Date operations
df_dates = df.withColumn(
    "order_month", F.date_format("order_date", "yyyy-MM")
).withColumn(
    "days_ago", F.datediff(F.current_date(), F.col("order_date"))
)
```

### Aggregations

```python
# Basic groupby
summary = df.groupBy("product").agg(
    F.count("*").alias("order_count"),
    F.sum("price").alias("total_revenue"),
    F.avg("price").alias("avg_price"),
    F.min("order_date").alias("first_order"),
    F.max("order_date").alias("last_order"),
)
summary.show()

# Multiple groupby columns with ordering
monthly = df.withColumn("month", F.date_format("order_date", "yyyy-MM")) \
    .groupBy("month", "product") \
    .agg(F.sum(F.col("quantity") * F.col("price")).alias("revenue")) \
    .orderBy("month", F.desc("revenue"))

monthly.show(20)
```

Here's the enriched exploration from the companion code (`01_explore.py`):

```python
"""Module 5 Solution: Spark Data Exploration."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark = SparkSession.builder.appName("Module5-Explore").getOrCreate()

# Load data
orders = spark.read.csv("/opt/spark-data/sample_orders.csv", header=True, inferSchema=True)
customers = spark.read.csv("/opt/spark-data/sample_customers.csv", header=True, inferSchema=True)
products = spark.read.csv("/opt/spark-data/sample_products.csv", header=True, inferSchema=True)

# Schema inspection
print("=== Orders Schema ===")
orders.printSchema()
print(f"Row count: {orders.count()}")
orders.show(10)

# Basic statistics
print("=== Summary Statistics ===")
orders.describe("quantity", "unit_price", "discount").show()

# Revenue by product (join orders to products)
enriched = orders.join(products, orders.product_id == products.product_id, "left") \
    .withColumn("revenue", F.col("quantity") * F.col("unit_price") - F.col("discount")) \
    .withColumn("cost", F.col("quantity") * F.col("unit_cost")) \
    .withColumn("profit", F.col("revenue") - F.col("cost"))

print("=== Revenue by Category ===")
enriched.groupBy("category") \
    .agg(
        F.sum("revenue").alias("total_revenue"),
        F.count("*").alias("order_count"),
        F.avg("revenue").alias("avg_order_value"),
    ) \
    .orderBy(F.desc("total_revenue")) \
    .show()

# Window functions: rank customers by total spend
customer_spend = enriched.groupBy("customer_id") \
    .agg(F.sum("revenue").alias("total_spend"))

window = Window.orderBy(F.desc("total_spend"))
ranked = customer_spend.withColumn("rank", F.rank().over(window))

print("=== Customer Ranking by Spend ===")
ranked.join(customers, "customer_id", "left") \
    .select("rank", "name", "city", "total_spend") \
    .show()

# Daily trends
print("=== Daily Order Trends ===")
orders.withColumn("order_day", F.to_date("order_date")) \
    .groupBy("order_day") \
    .agg(F.count("*").alias("orders"), F.sum(F.col("quantity") * F.col("unit_price")).alias("revenue")) \
    .orderBy("order_day") \
    .show()

spark.stop()
```

### Writing Data

```python
# Parquet -- the go-to for data lakes
df_enriched.write \
    .mode("overwrite") \
    .parquet("output/orders_enriched")

# Partitioned by date -- standard for data lakes
df_enriched.write \
    .mode("overwrite") \
    .partitionBy("order_year") \
    .parquet("output/orders_by_year")

# CSV (for humans or legacy systems)
summary.coalesce(1).write \
    .mode("overwrite") \
    .option("header", "true") \
    .csv("output/summary")

# To a database via JDBC
df_enriched.write \
    .format("jdbc") \
    .option("url", "jdbc:postgresql://localhost:5432/warehouse") \
    .option("dbtable", "public.orders_enriched") \
    .option("user", "postgres") \
    .option("password", "postgres") \
    .mode("overwrite") \
    .save()
```

**Write modes:**
- `overwrite` -- replace everything
- `append` -- add to existing data
- `ignore` -- do nothing if data exists
- `error` / `errorifexists` -- fail if data exists (default)

> **Common Mistake:**
>
> **`inferSchema=True` on large files** -- Define your schema. It's faster and more reliable.
>
> **Writing CSV when you should write Parquet** -- Parquet is 10x smaller, 10x faster to read, and includes the schema. Always use Parquet unless someone specifically needs CSV.
>
> **`.coalesce(1)` on large data** -- Merges all partitions to 1 file. Fine for small summary tables. Do NOT coalesce 10GB of data into one file.

---

## 5.4 Spark SQL -- Running SQL on Distributed Data

> **TL;DR**
> - Register DataFrames as views, then query with standard SQL
> - Spark SQL supports window functions, CTEs, and everything you'd expect
> - You can query Parquet files directly without registering views
> - Mix DataFrame API and SQL freely -- use whatever's clearest

You can use Spark and barely write any Python. Spark SQL lets you run standard SQL on distributed datasets.

### Basic Usage

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("Spark SQL").getOrCreate()

# Read data
orders = spark.read.parquet("data/orders.parquet")
customers = spark.read.parquet("data/customers.parquet")

# Register as SQL views
orders.createOrReplaceTempView("orders")
customers.createOrReplaceTempView("customers")

# Now write standard SQL!
result = spark.sql("""
    SELECT
        c.name,
        c.segment,
        COUNT(o.order_id) AS total_orders,
        SUM(o.quantity * o.price) AS total_revenue,
        AVG(o.quantity * o.price) AS avg_order_value
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.order_date >= '2026-01-01'
    GROUP BY c.name, c.segment
    HAVING total_revenue > 1000
    ORDER BY total_revenue DESC
""")

result.show(20)
```

It's the exact same SQL you'd write in Postgres. But it runs distributed across your Spark cluster.

### Window Functions in SQL

```python
spark.sql("""
    SELECT
        order_id,
        customer_id,
        price,
        order_date,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id ORDER BY order_date DESC
        ) as rn,
        SUM(price) OVER (
            PARTITION BY customer_id ORDER BY order_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as running_total,
        LAG(price) OVER (
            PARTITION BY customer_id ORDER BY order_date
        ) as prev_order_amount
    FROM orders
""").show()
```

### Querying Files Directly

You don't even need to register views for ad-hoc analysis:

```python
# Query Parquet files directly
spark.sql("""
    SELECT * FROM parquet.`data/orders.parquet`
    WHERE price > 100
    LIMIT 10
""").show()

# Query CSV files directly
spark.sql("SELECT * FROM csv.`data/orders.csv`").show()
```

### When to Use DataFrame API vs. SQL

| Use Case | Preference |
|----------|-----------|
| Complex multi-step transformations | DataFrame API (chaining) |
| Ad-hoc analysis / exploration | SQL |
| Analysts maintaining the code | SQL |
| Dynamic column operations | DataFrame API |
| Joins with complex logic | SQL (often easier to read) |

In practice, use both. Many production jobs mix DataFrame API and SQL in the same script.

> **At your job:** If you're building a pipeline that analysts will eventually maintain, lean toward Spark SQL. Most analysts are fluent in SQL but less comfortable with PySpark's DataFrame API. If you're building complex transformation logic with lots of conditional branching, the DataFrame API gives you more programmatic control.

---

## 5.5 Joins, Aggregations, and Window Functions

> **TL;DR**
> - Broadcast small tables in joins to avoid expensive shuffles
> - Anti joins are great for data quality checks (finding orphaned records)
> - Window functions without `partitionBy` send all data to one executor -- very slow
> - Check for data skew on join keys before running large joins

Joins are where most Spark performance problems live. Understanding how Spark joins data will make or break your job execution times.

### Join Types

```python
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.appName("Joins").getOrCreate()

# Sample data
orders = spark.createDataFrame([
    (1, 101, 29.99), (2, 102, 49.99), (3, 101, 19.99),
    (4, 103, 99.99), (5, 999, 14.99),   # 999 = no matching customer
], ["order_id", "customer_id", "amount"])

customers = spark.createDataFrame([
    (101, "Alice", "premium"), (102, "Bob", "standard"),
    (103, "Charlie", "basic"), (104, "Diana", "premium"),   # 104 = no orders
], ["customer_id", "name", "segment"])

# INNER JOIN -- only matching rows
inner = orders.join(customers, "customer_id", "inner")
inner.show()
# Result: 4 rows (order 5 excluded, customer 104 excluded)

# LEFT JOIN -- all orders, even without customer match
left = orders.join(customers, "customer_id", "left")
left.show()
# Result: 5 rows (order 5 has null name/segment)

# ANTI JOIN -- orders WITHOUT matching customers (data quality check!)
orphans = orders.join(customers, "customer_id", "left_anti")
orphans.show()
# Result: just order 5 -- great for finding data quality issues

# SEMI JOIN -- orders that HAVE matching customers (no customer columns added)
matched = orders.join(customers, "customer_id", "left_semi")
matched.show()
# Result: 4 order rows, no customer columns
```

> **At your job:** Anti joins are your secret weapon for data quality. Before loading data into your warehouse, run an anti join against your dimension tables to find orphaned foreign keys. This catches data issues before they corrupt your reports. The companion code in `02_quality_checks.py` shows this pattern in action.

### Broadcast Joins -- The Key Optimization

When you join two DataFrames, Spark shuffles data across the network so matching keys land on the same executor. This is slow. If one side is small, you can avoid the shuffle entirely:

```python
from pyspark.sql.functions import broadcast

# Send the entire small table to every executor -- no shuffle needed
result = orders.join(broadcast(customers), "customer_id", "inner")
```

> **Key Concept: Broadcast Joins**
>
> Spark auto-broadcasts tables under 10MB. For tables up to ~100MB, manually broadcast them with `broadcast()`. If one table has 100MB and the other has 100GB, broadcasting saves massive shuffle time.

### Window Functions with DataFrame API

```python
from pyspark.sql.window import Window

orders_data = spark.createDataFrame([
    (1, 101, 100.0, "2026-01-01"),
    (2, 101, 200.0, "2026-01-15"),
    (3, 101, 150.0, "2026-02-01"),
    (4, 102, 300.0, "2026-01-10"),
    (5, 102, 250.0, "2026-01-20"),
    (6, 102, 175.0, "2026-02-05"),
], ["order_id", "customer_id", "amount", "order_date"])

# Define window specs
customer_window = Window.partitionBy("customer_id").orderBy("order_date")
customer_all = Window.partitionBy("customer_id")

result = orders_data.select(
    "*",
    F.row_number().over(customer_window).alias("order_number"),

    F.sum("amount").over(
        customer_window.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    ).alias("running_total"),

    F.lag("amount", 1).over(customer_window).alias("prev_amount"),
    F.lead("amount", 1).over(customer_window).alias("next_amount"),

    F.sum("amount").over(customer_all).alias("customer_total"),

    (F.col("amount") / F.sum("amount").over(customer_all) * 100)
        .cast("decimal(5,2)").alias("pct_of_total"),
)

result.show()
```

Expected output:

```
+--------+-----------+------+----------+------------+-------------+-----------+-----------+--------------+------------+
|order_id|customer_id|amount|order_date|order_number|running_total|prev_amount|next_amount|customer_total|pct_of_total|
+--------+-----------+------+----------+------------+-------------+-----------+-----------+--------------+------------+
|       1|        101| 100.0|2026-01-01|           1|        100.0|       null|      200.0|         450.0|       22.22|
|       2|        101| 200.0|2026-01-15|           2|        300.0|      100.0|      150.0|         450.0|       44.44|
|       3|        101| 150.0|2026-02-01|           3|        450.0|      200.0|       null|         450.0|       33.33|
|       4|        102| 300.0|2026-01-10|           1|        300.0|       null|      250.0|         725.0|       41.38|
|       5|        102| 250.0|2026-01-20|           2|        550.0|      300.0|      175.0|         725.0|       34.48|
|       6|        102| 175.0|2026-02-05|           3|        725.0|      250.0|       null|         725.0|       24.14|
+--------+-----------+------+----------+------------+-------------+-----------+-----------+--------------+------------+
```

> **Common Mistake:**
>
> **Joining two huge tables without checking for data skew** -- If 90% of your data has `customer_id = NULL`, one partition processes 90% of the work. Filter nulls before joining.
>
> **Window functions without `partitionBy`** -- `Window.orderBy(...)` without `partitionBy(...)` creates a single partition for ALL data. Everything goes to one executor. Very slow.

---

## 5.6 Data Quality Checks in Spark

> **At your job:** Data quality checks are not optional. Every production Spark pipeline should validate its inputs before transforming and its outputs before publishing. Bad data in, bad data out -- except now it's bad data at scale.

Here's the companion quality checks script (`de-fast-track/modules/module-5/solution/scripts/02_quality_checks.py`):

```python
"""Module 5 Solution: Spark Data Quality Checks."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("Module5-Quality").getOrCreate()

orders = spark.read.csv("/opt/spark-data/sample_orders.csv", header=True, inferSchema=True)
customers = spark.read.csv("/opt/spark-data/sample_customers.csv", header=True, inferSchema=True)
products = spark.read.csv("/opt/spark-data/sample_products.csv", header=True, inferSchema=True)

print("=" * 60)
print("DATA QUALITY REPORT")
print("=" * 60)

# 1. Null value analysis
print("\n--- Null Values ---")
for col_name in orders.columns:
    null_count = orders.filter(F.col(col_name).isNull()).count()
    if null_count > 0:
        print(f"  {col_name}: {null_count} nulls")

# 2. Duplicate detection
print("\n--- Duplicates ---")
total = orders.count()
distinct = orders.select("order_id").distinct().count()
dupes = total - distinct
print(f"  Total rows: {total}, Distinct order_ids: {distinct}, Duplicates: {dupes}")

# 3. Range validation
print("\n--- Range Validation ---")
neg_prices = orders.filter(F.col("unit_price") < 0).count()
neg_qty = orders.filter(F.col("quantity") <= 0).count()
print(f"  Negative prices: {neg_prices}")
print(f"  Non-positive quantities: {neg_qty}")

# 4. Referential integrity
print("\n--- Referential Integrity ---")
orphan_customers = orders.join(customers, orders.customer_id == customers.customer_id, "left_anti").count()
orphan_products = orders.join(products, orders.product_id == products.product_id, "left_anti").count()
print(f"  Orders with unknown customer_id: {orphan_customers}")
print(f"  Orders with unknown product_id: {orphan_products}")

# 5. Quality report as DataFrame
quality_checks = spark.createDataFrame([
    ("null_check", "No nulls in key columns", "PASS" if dupes == 0 else "FAIL"),
    ("duplicate_check", f"{dupes} duplicate order_ids", "PASS" if dupes == 0 else "FAIL"),
    ("negative_prices", f"{neg_prices} negative prices", "PASS" if neg_prices == 0 else "FAIL"),
    ("orphan_customers", f"{orphan_customers} orphaned", "PASS" if orphan_customers == 0 else "WARN"),
    ("orphan_products", f"{orphan_products} orphaned", "PASS" if orphan_products == 0 else "WARN"),
], ["check_name", "details", "result"])

print("\n--- Quality Summary ---")
quality_checks.show(truncate=False)

spark.stop()
```

> **At your job:** Build a reusable quality check framework. Every time you load data into a new table, run nulls, duplicates, range checks, and referential integrity. Write the results to a quality report table. When the CFO asks "can we trust this data?", you point to the quality report instead of shrugging.

---

## 5.7 Transformation Pipelines

The real power of Spark is chaining transformations into pipelines. Here's the companion transformation script (`de-fast-track/modules/module-5/solution/scripts/03_transform.py`):

```python
"""Module 5 Solution: Spark Transformation Pipeline."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("Module5-Transform").getOrCreate()

# Read raw data
orders = spark.read.csv("/opt/spark-data/sample_orders.csv", header=True, inferSchema=True)
customers = spark.read.csv("/opt/spark-data/sample_customers.csv", header=True, inferSchema=True)
products = spark.read.csv("/opt/spark-data/sample_products.csv", header=True, inferSchema=True)

# Enrich orders with customer and product info
enriched = orders \
    .join(customers, "customer_id", "left") \
    .join(products, "product_id", "left") \
    .withColumn("revenue", F.col("quantity") * orders["unit_price"] - F.col("discount")) \
    .withColumn("cost", F.col("quantity") * F.col("unit_cost")) \
    .withColumn("profit", F.col("revenue") - F.col("cost")) \
    .withColumn("order_month", F.date_format("order_date", "yyyy-MM")) \
    .withColumn("order_day_of_week", F.dayofweek("order_date"))

print("=== Enriched Orders ===")
enriched.select(
    "order_id", "name", "category", "quantity", "revenue", "profit", "status"
).show(10)

# Aggregate: revenue by category and month
revenue_by_category = enriched \
    .groupBy("category", "order_month") \
    .agg(
        F.sum("revenue").alias("total_revenue"),
        F.sum("profit").alias("total_profit"),
        F.count("*").alias("order_count"),
        F.countDistinct("customer_id").alias("unique_customers"),
    ) \
    .orderBy("order_month", F.desc("total_revenue"))

print("=== Revenue by Category & Month ===")
revenue_by_category.show()

# Aggregate: customer summary
customer_summary = enriched \
    .groupBy("customer_id", "name", "city", "state") \
    .agg(
        F.sum("revenue").alias("lifetime_value"),
        F.count("*").alias("total_orders"),
        F.avg("revenue").alias("avg_order_value"),
        F.min("order_date").alias("first_order"),
        F.max("order_date").alias("last_order"),
    ) \
    .orderBy(F.desc("lifetime_value"))

print("=== Customer Summary ===")
customer_summary.show()

# Write results as Parquet
enriched.write.mode("overwrite").parquet("/opt/spark-data/output/enriched_orders")
revenue_by_category.write.mode("overwrite").parquet("/opt/spark-data/output/revenue_by_category")
customer_summary.write.mode("overwrite").parquet("/opt/spark-data/output/customer_summary")

print("Parquet files written to /opt/spark-data/output/")
spark.stop()
```

> **At your job:** This is the pattern you'll see everywhere: read raw data, join with dimension tables, compute business metrics, write enriched output. The specifics change (taxi trips instead of orders, ad impressions instead of products), but the skeleton is always the same. Master this pattern once and you can build any Spark pipeline.

---

## 5.8 UDFs -- When to Use Them (Rarely) and Alternatives

> **TL;DR**
> - UDFs are 10--100x slower than built-in functions due to serialization overhead
> - Always try built-in functions first (`F.when`, `F.regexp_extract`, etc.)
> - If you must use UDFs, use Pandas UDFs (vectorized) for 10--100x speedup over regular UDFs
> - Regular UDFs are a last resort

UDFs (User Defined Functions) let you run custom Python code on Spark data. The problem: they're slow. Like, 10--100x slower than built-in functions.

### Why UDFs Are Slow

Built-in Spark functions run in the JVM -- compiled, optimized, fast. UDFs run in Python. For every row, Spark serializes data from JVM to Python (via a socket), runs your function, then serializes back. That per-row overhead kills performance.

### Don't Use a UDF When Built-In Functions Work

```python
from pyspark.sql import functions as F
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

# BAD -- UDF for something built-in functions handle perfectly
@udf(returnType=StringType())
def categorize_amount_udf(amount):
    if amount > 100: return "high"
    elif amount > 50: return "medium"
    else: return "low"

df.withColumn("tier", categorize_amount_udf(df.amount))   # Slow!

# GOOD -- Built-in when/otherwise (runs in JVM, no serialization)
df.withColumn("tier",
    F.when(F.col("amount") > 100, "high")
    .when(F.col("amount") > 50, "medium")
    .otherwise("low")
)
```

### When You Genuinely Need a UDF

```python
import re
from pyspark.sql.functions import udf
from pyspark.sql.types import ArrayType, StringType

# Complex regex that can't be expressed with built-in functions
@udf(returnType=ArrayType(StringType()))
def extract_emails(text):
    """Extract all email addresses from text."""
    if text is None:
        return []
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(pattern, text)

df.withColumn("emails", extract_emails(df.description)).show()
```

### Better Alternative: Pandas UDFs (Vectorized)

If you must use UDFs, Pandas UDFs process batches of rows instead of one at a time -- 10--100x faster:

```python
import pandas as pd
from pyspark.sql.functions import pandas_udf

@pandas_udf("double")
def calculate_discount(amounts: pd.Series, quantities: pd.Series) -> pd.Series:
    """Vectorized UDF -- processes batches, not individual rows."""
    base_discount = 0.05
    volume_discount = (quantities > 10).astype(float) * 0.1
    return amounts * (1 - base_discount - volume_discount)

df.withColumn("discounted", calculate_discount(df.amount, df.quantity)).show()
```

### The UDF Decision Ladder

1. First, try **built-in functions** (`F.when`, `F.regexp_extract`, `F.split`, etc.)
2. If that fails, try **Spark SQL expressions**
3. If that fails, use a **Pandas UDF**
4. **Last resort:** regular UDF

---

## 5.9 Performance Tuning -- Partitioning, Caching, Broadcast Joins, AQE

> **TL;DR**
> - The four performance killers: data skew, wrong partition count, no caching, unnecessary shuffles
> - Enable AQE (Adaptive Query Execution) -- it's a free performance boost
> - Cache DataFrames you use multiple times; unpersist when done
> - Read execution plans to understand what Spark is actually doing

This is the section that'll make you look like a Spark wizard. Most PySpark jobs are slow because of a handful of common issues.

### Performance Killer #1: Data Skew

Data skew means some partitions have way more data than others. If partition 1 has 10 rows and partition 2 has 10 million rows, your cluster sits idle while one executor does all the work.

```python
# Detect skew -- check key distribution
df.groupBy("join_key").count().orderBy(F.desc("count")).show(10)
# If one key has 10M rows and others have 1K, you have skew

# Fix: salt the skewed key
num_salts = 10
skewed_df = skewed_df.withColumn(
    "salt", (F.rand() * num_salts).cast("int")
)
# Explode salts on the other table to match
other_df = other_df.withColumn(
    "salt", F.explode(F.array([F.lit(i) for i in range(num_salts)]))
)
# Join on key + salt distributes the work evenly
result = skewed_df.join(other_df, ["join_key", "salt"]).drop("salt")
```

> **At your job:** Data skew is the #1 reason Spark jobs take forever. The classic scenario: you're joining on `customer_id` and 40% of your orders have `customer_id = NULL` (guest checkouts). One executor gets 40% of all data while the others finish in seconds. Always filter nulls before joining on nullable columns, or salt the keys.

### Performance Killer #2: Wrong Partition Count

```python
# Check current partition count
print(f"Partitions: {df.rdd.getNumPartitions()}")

# Repartition -- more partitions (triggers shuffle)
df_repartitioned = df.repartition(200)

# Coalesce -- fewer partitions (no shuffle, faster)
df_small = df.coalesce(10)

# Rule of thumb: target 128MB per partition
# 10GB of data: 10,000MB / 128MB = ~80 partitions
```

### Performance Killer #3: Not Caching

If you read from the same DataFrame multiple times, cache it:

```python
# Without cache -- reads from disk TWICE
count = df.filter(df.status == "active").count()
total = df.filter(df.status == "active").agg(F.sum("amount")).collect()

# With cache -- reads once, stores in memory
active = df.filter(df.status == "active").cache()
count = active.count()               # First call: reads + caches
total = active.agg(F.sum("amount")).collect()   # Second call: from memory

# IMPORTANT: free memory when done
active.unpersist()
```

**Cache when:** you use the same DataFrame in multiple actions, or it's expensive to compute.

**Don't cache when:** you only use it once, or it's too big to fit in memory.

### Performance Killer #4: Unnecessary Shuffles

```python
# BAD: Repartition then immediately coalesce -- useless shuffle
df.repartition(200).coalesce(50)

# BAD: Distinct before a join -- two shuffles when one might do
df1.distinct().join(df2, "key")
# If possible, deduplicate AFTER the join
```

### Adaptive Query Execution (AQE) -- Free Performance

AQE (Spark 3.0+) optimizes your job DURING execution based on actual data statistics:

```python
# Enable AQE (default in Spark 3.2+)
spark.conf.set("spark.sql.adaptive.enabled", "true")

# Auto-coalesce: combines small shuffle partitions
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")

# Auto-broadcast: detects small join sides at runtime
spark.conf.set("spark.sql.adaptive.autoBroadcastJoinThreshold", "10MB")

# Skew optimization: splits skewed partitions automatically
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
```

### Reading Execution Plans

```python
df.filter(df.amount > 100) \
    .groupBy("category") \
    .agg(F.sum("amount")) \
    .explain(mode="formatted")

# Look for:
# - "BroadcastHashJoin" (good) vs "SortMergeJoin" (potentially slow)
# - "Exchange" = shuffle (expensive)
# - "FileScan" -- are you reading all columns or just what you need?
```

### Quick Wins Checklist

```
- Enable AQE: spark.sql.adaptive.enabled = true
- Select only columns you need (don't SELECT *)
- Filter early (push filters before joins)
- Use Parquet (column pruning + predicate pushdown)
- Broadcast small tables in joins
- Cache DataFrames used multiple times
- Partition writes by date for downstream efficiency
- Check for data skew on join keys
```

### Debugging OOM Errors

> **At your job:** When your Spark job dies with `OutOfMemoryError`, here's the debugging checklist:
>
> 1. **Driver OOM:** Did you call `.collect()` or `.toPandas()` on a huge DataFrame? Use `.show()` or `.write()` instead.
> 2. **Executor OOM:** Is one executor getting all the data? Check for data skew. Run `df.groupBy("join_key").count().orderBy(F.desc("count")).show(10)`.
> 3. **Too many partitions cached:** Are you caching everything and never calling `.unpersist()`? Memory is finite.
> 4. **Increase memory:** Sometimes you just need more RAM. `spark.executor.memory=8g` in your config. But fix the root cause first -- throwing memory at a skew problem just delays the crash.

---

## 5.10 Delta Lake / Apache Iceberg -- Modern Table Formats

> **TL;DR**
> - Plain Parquet files lack transactions, updates, deletes, and time travel
> - Delta Lake adds ACID transactions, MERGE/upsert, time travel, and schema evolution
> - Delta Lake (Databricks) vs. Iceberg (Netflix) -- both solve the same problems
> - Use Delta if on Databricks; use Iceberg for multi-engine flexibility

Here's a real scenario: you have a data lake with millions of Parquet files in S3. A pipeline writes new data while a Spark job reads. The read job picks up a half-written file. Corrupt data. Dashboard breaks.

Or: you need to delete all data for a GDPR request. Good luck finding and rewriting every Parquet file containing that user.

### The Problems with Plain Parquet

1. **No ACID transactions** -- reads can see partially written data
2. **No updates/deletes** -- Parquet files are immutable
3. **No schema evolution** -- adding a column breaks old files
4. **No time travel** -- can't roll back mistakes
5. **Small file problem** -- streaming creates thousands of tiny files

### Delta Lake in Action

Here's the companion Delta Lake code (`de-fast-track/modules/module-5/solution/scripts/04_delta_lake.py`):

```python
from pyspark.sql import SparkSession
from delta import configure_spark_with_delta_pip

# Setup Spark with Delta Lake
builder = SparkSession.builder \
    .appName("DeltaLake") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog")

spark = configure_spark_with_delta_pip(builder).getOrCreate()

# Write a Delta table
orders = spark.createDataFrame([
    (1, "Alice", 99.99, "2026-02-19"),
    (2, "Bob", 149.50, "2026-02-19"),
    (3, "Charlie", 29.99, "2026-02-19"),
], ["order_id", "customer", "amount", "date"])

orders.write.format("delta").mode("overwrite").save("data/delta/orders")

# Read it back
df = spark.read.format("delta").load("data/delta/orders")
df.show()
```

### Updates, Deletes, and MERGE

```python
from delta.tables import DeltaTable

delta_table = DeltaTable.forPath(spark, "data/delta/orders")

# UPDATE -- change Alice's amount
delta_table.update(
    condition="customer = 'Alice'",
    set={"amount": "109.99"}
)

# DELETE -- remove Charlie
delta_table.delete("customer = 'Charlie'")

# MERGE (upsert) -- the most powerful operation
new_data = spark.createDataFrame([
    (1, "Alice", 119.99, "2026-02-20"),   # Update existing
    (4, "Diana", 199.00, "2026-02-20"),   # Insert new
], ["order_id", "customer", "amount", "date"])

delta_table.alias("target").merge(
    new_data.alias("source"),
    "target.order_id = source.order_id"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()
```

> **At your job:** MERGE is the operation you'll use most in production pipelines. It handles the "upsert" pattern: if the record exists, update it; if not, insert it. This makes your pipelines idempotent -- you can re-run them safely without creating duplicates.

### Time Travel

```python
# Read a previous version
df_v0 = spark.read.format("delta") \
    .option("versionAsOf", 0) \
    .load("data/delta/orders")

# Read as of a specific timestamp
df_yesterday = spark.read.format("delta") \
    .option("timestampAsOf", "2026-02-18") \
    .load("data/delta/orders")

# View history
delta_table.history().show()

# Restore to a previous version (undo a mistake!)
delta_table.restoreToVersion(0)
```

### Schema Evolution

```python
# Add a new column -- existing data gets nulls
new_with_status = spark.createDataFrame([
    (5, "Eve", 75.25, "2026-02-20", "completed"),
], ["order_id", "customer", "amount", "date", "status"])

new_with_status.write.format("delta") \
    .mode("append") \
    .option("mergeSchema", "true") \
    .save("data/delta/orders")
```

### OPTIMIZE -- Fix the Small Files Problem

```python
# Compact small files into larger ones
delta_table.optimize().executeCompaction()

# Z-ORDER -- co-locate related data for faster queries
delta_table.optimize().executeZOrderBy("date", "customer")
```

### Delta Lake vs. Iceberg

| Feature | Delta Lake | Apache Iceberg |
|---------|-----------|---------------|
| Creator | Databricks | Netflix |
| Ecosystem | Tight Spark integration | Multi-engine (Spark, Trino, Flink) |
| Industry adoption | Dominant in Databricks shops | Growing fast, especially multi-cloud |
| Community | Open source + Databricks extras | Fully open source |

If you're on Databricks, use Delta Lake. If you want engine flexibility, Iceberg is the better bet. Both solve the same problems.

---

## 5.11 Running Spark on AWS EMR and Databricks

> **TL;DR**
> - In production, Spark runs on managed clusters: EMR, Databricks, Dataproc
> - EMR Serverless is the simplest AWS option -- no cluster management
> - Databricks is the most popular Spark platform overall
> - Your PySpark code is identical everywhere -- only deployment differs

Running Spark on your laptop is great for learning. In production, you need managed clusters.

### Option 1: AWS EMR

```bash
# Submit a PySpark job to EMR
aws emr add-steps \
    --cluster-id j-XXXXXXXXXXXXX \
    --steps Type=Spark,Name="Daily ETL",\
    ActionOnFailure=CONTINUE,\
    Args=[--deploy-mode,cluster,s3://my-bucket/scripts/etl.py]
```

**EMR Serverless** -- no cluster management at all:

```bash
aws emr-serverless start-job-run \
    --application-id 00xxxxxxxxxxxxxxxxx \
    --execution-role-arn arn:aws:iam::123456789:role/emr-role \
    --job-driver '{
        "sparkSubmit": {
            "entryPoint": "s3://my-bucket/scripts/etl.py",
            "sparkSubmitParameters": "--conf spark.sql.adaptive.enabled=true"
        }
    }'
```

### Option 2: Databricks

The most popular Spark platform. Founded by the creators of Spark. Features: managed notebooks, built-in Delta Lake, Unity Catalog for governance, auto-scaling clusters, and built-in job scheduling.

### Option 3: Google Dataproc / Azure Synapse

Same concept, different cloud: Dataproc for GCP, Synapse for Azure.

### Option 4: Kubernetes

```bash
spark-submit \
    --master k8s://https://k8s-apiserver:443 \
    --deploy-mode cluster \
    --conf spark.kubernetes.container.image=my-spark:latest \
    --conf spark.executor.instances=5 \
    s3://my-bucket/etl.py
```

> **Pro Tip:** For job hunting: learn EMR and Databricks terminology. Most job postings mention one or both. The actual PySpark code is identical everywhere -- it's just the deployment wrapper that differs.

> **At your job:** Your first week, ask: "Where does our Spark run?" The answer tells you everything about the team's maturity. If it's "we ssh into a server and run spark-submit," there's work to do. If it's "Databricks with scheduled jobs," you're in a good spot.

---

## Module 5 Project: Processing NYC Taxi Data with PySpark

Process the NYC Taxi dataset using PySpark -- exploration, data quality checks, transformations, analytics with window functions, and Delta Lake output.

### Step 1: Set Up the Environment

```yaml
# docker-compose.yaml
version: '3.8'

services:
  spark-master:
    image: bitnami/spark:3.5.1
    environment:
      - SPARK_MODE=master
      - SPARK_MASTER_HOST=spark-master
    ports:
      - "8081:8080"    # Spark Master UI
      - "7077:7077"
      - "4040:4040"    # Spark App UI
    volumes:
      - ./data:/data
      - ./scripts:/scripts
      - ./output:/output

  spark-worker:
    image: bitnami/spark:3.5.1
    environment:
      - SPARK_MODE=worker
      - SPARK_MASTER_URL=spark://spark-master:7077
      - SPARK_WORKER_MEMORY=4g
      - SPARK_WORKER_CORES=2
    depends_on:
      - spark-master
    volumes:
      - ./data:/data
      - ./output:/output
```

```bash
mkdir -p data scripts output

# Download NYC taxi data (3-6 months, ~100MB each)
for month in 01 02 03 04 05 06; do
  wget -P data/ \
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-$month.parquet"
done

docker compose up -d
```

### Step 2: Explore the Data

```python
# scripts/01_explore.py
"""Explore and understand the dataset."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder \
    .appName("NYC Taxi - Explore") \
    .config("spark.sql.adaptive.enabled", "true") \
    .getOrCreate()

# Read all months at once with glob pattern
df = spark.read.parquet("data/yellow_tripdata_2023-*.parquet")

print(f"Total rows: {df.count():,}")
print(f"Partitions: {df.rdd.getNumPartitions()}")

print("\nSchema:")
df.printSchema()

print("\nSample data:")
df.show(5, truncate=False)

# Check for nulls across all columns
print("\nNull counts per column:")
null_counts = df.select([
    F.sum(F.when(F.col(c).isNull(), 1).otherwise(0)).alias(c)
    for c in df.columns
])
null_counts.show(truncate=False)

# Check value distributions
print("\nPassenger count distribution:")
df.groupBy("passenger_count").count().orderBy("passenger_count").show()

spark.stop()
```

### Step 3: Data Quality Checks

```python
# scripts/02_quality_checks.py
"""Identify and handle data quality issues."""
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder \
    .appName("NYC Taxi - Quality") \
    .config("spark.sql.adaptive.enabled", "true") \
    .getOrCreate()

df = spark.read.parquet("data/yellow_tripdata_2023-*.parquet")
total = df.count()

print("=== DATA QUALITY REPORT ===\n")

neg_fares = df.filter(F.col("fare_amount") < 0).count()
print(f"Negative fares: {neg_fares:,} ({neg_fares/total*100:.2f}%)")

long_trips = df.filter(F.col("trip_distance") > 200).count()
print(f"Trips > 200 miles: {long_trips:,}")

zero_pax = df.filter(
    (F.col("passenger_count") == 0) | F.col("passenger_count").isNull()
).count()
print(f"Zero/null passengers: {zero_pax:,}")

time_travel = df.filter(
    F.col("tpep_dropoff_datetime") < F.col("tpep_pickup_datetime")
).count()
print(f"Dropoff before pickup: {time_travel:,}")

# Apply quality filters
print(f"\n=== CLEANING ===")
print(f"Before: {total:,} rows")

df_clean = df.filter(
    (F.col("fare_amount") >= 0) &
    (F.col("fare_amount") < 1000) &
    (F.col("trip_distance") > 0) &
    (F.col("trip_distance") < 200) &
    (F.col("passenger_count") > 0) &
    (F.col("tpep_dropoff_datetime") > F.col("tpep_pickup_datetime")) &
    (F.col("tpep_pickup_datetime").between("2023-01-01", "2023-12-31"))
)

clean_count = df_clean.count()
print(f"After:  {clean_count:,} rows")
print(f"Removed: {total - clean_count:,} rows ({(total-clean_count)/total*100:.2f}%)")

df_clean.write.mode("overwrite").parquet("output/cleaned_taxi_data")

spark.stop()
```

### Step 4: Transformations and Analytics

```python
# scripts/03_transform.py
"""Transform data and compute analytics with window functions."""
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window

spark = SparkSession.builder \
    .appName("NYC Taxi - Transform") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

df = spark.read.parquet("output/cleaned_taxi_data")

# === ENRICHMENT ===
df_enriched = df.withColumn(
    "trip_duration_minutes",
    (F.unix_timestamp("tpep_dropoff_datetime") -
     F.unix_timestamp("tpep_pickup_datetime")) / 60
).withColumn(
    "avg_speed_mph",
    F.when(
        F.col("trip_duration_minutes") > 0,
        F.col("trip_distance") / (F.col("trip_duration_minutes") / 60)
    ).otherwise(0)
).withColumn(
    "pickup_hour", F.hour("tpep_pickup_datetime")
).withColumn(
    "pickup_date", F.to_date("tpep_pickup_datetime")
).withColumn(
    "pickup_month", F.month("tpep_pickup_datetime")
).withColumn(
    "is_weekend", F.dayofweek("tpep_pickup_datetime").isin([1, 7]).cast("int")
).withColumn(
    "tip_percentage",
    F.when(F.col("fare_amount") > 0,
        (F.col("tip_amount") / F.col("fare_amount") * 100).cast("decimal(5,2)")
    ).otherwise(0)
).withColumn(
    "fare_category",
    F.when(F.col("total_amount") > 100, "premium")
     .when(F.col("total_amount") > 50, "high")
     .when(F.col("total_amount") > 20, "medium")
     .otherwise("budget")
)

# === ANALYTICS ===

# Hourly demand pattern
hourly_demand = df_enriched.groupBy("pickup_hour").agg(
    F.count("*").alias("trip_count"),
    F.avg("fare_amount").alias("avg_fare"),
    F.avg("trip_duration_minutes").alias("avg_duration"),
    F.avg("tip_percentage").alias("avg_tip_pct"),
).orderBy("pickup_hour")

print("=== Hourly Demand ===")
hourly_demand.show(24)

# Daily revenue with window functions (7-day and 30-day moving averages)
daily_revenue = df_enriched.groupBy("pickup_date").agg(
    F.count("*").alias("trips"),
    F.sum("total_amount").alias("revenue"),
    F.avg("total_amount").alias("avg_fare"),
)

window_7d = Window.orderBy("pickup_date").rowsBetween(-6, 0)
window_30d = Window.orderBy("pickup_date").rowsBetween(-29, 0)

daily_with_trends = daily_revenue.select(
    "*",
    F.avg("revenue").over(window_7d).alias("revenue_7d_avg"),
    F.avg("revenue").over(window_30d).alias("revenue_30d_avg"),
    F.avg("trips").over(window_7d).alias("trips_7d_avg"),
).orderBy("pickup_date")

print("=== Daily Revenue with Trends ===")
daily_with_trends.show(10)

# === WRITE TO DELTA LAKE ===
df_enriched.write \
    .format("delta") \
    .mode("overwrite") \
    .partitionBy("pickup_month") \
    .save("output/delta/taxi_enriched")

daily_with_trends.write \
    .format("delta") \
    .mode("overwrite") \
    .save("output/delta/daily_revenue")

hourly_demand.write \
    .format("delta") \
    .mode("overwrite") \
    .save("output/delta/hourly_demand")

print("\nAll outputs written to Delta Lake")
spark.stop()
```

### Step 5: Run Everything

```bash
# Submit jobs to Spark cluster
docker compose exec spark-master spark-submit \
    --master spark://spark-master:7077 \
    /scripts/01_explore.py

docker compose exec spark-master spark-submit \
    --master spark://spark-master:7077 \
    /scripts/02_quality_checks.py

docker compose exec spark-master spark-submit \
    --master spark://spark-master:7077 \
    --packages io.delta:delta-spark_2.12:3.1.0 \
    /scripts/03_transform.py
```

### Expected Output

- Data quality report showing issues found and percentage cleaned
- Enriched dataset with trip duration, speed, tip %, fare category
- Hourly demand analysis showing peak hours (typically 6--8 PM)
- Daily revenue with 7-day and 30-day moving averages
- All outputs in Delta Lake format with month partitioning

### Stretch Goals

1. **Zone lookup** -- Join with the taxi zone shapefile to get pickup/dropoff neighborhood names
2. **Surge pricing indicator** -- Flag hours above the 90th percentile of demand
3. **Delta time travel** -- Compare this month's data vs. last month's
4. **Anomaly detection** -- Flag days where revenue is > 2 standard deviations from the 30-day average

---

## What's Next

Now that you can process data at scale with Spark, Module 6 covers Apache Kafka and streaming -- what happens when your data arrives continuously instead of in batches. You'll learn when you actually need real-time processing (hint: less often than you think), how Kafka works under the hood, and how to build streaming pipelines.
