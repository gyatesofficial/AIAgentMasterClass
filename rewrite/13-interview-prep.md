# Appendix C: Interview Preparation for Data Engineers

## The Data Engineering Interview Landscape

Data engineering interviews are different from software engineering interviews. You will not be asked to implement a red-black tree or solve dynamic programming puzzles. Instead, you will face a combination of: SQL coding challenges, Python coding for data tasks, system design for data pipelines, data modeling questions, and behavioral questions about working with data at scale.

After conducting 150+ system design interviews at three companies, I can tell you: the difference between candidates who get offers and those who do not is rarely technical knowledge. Most senior candidates know Kafka, know SQL, know the CAP theorem. The difference is **how they think and communicate**.

The best candidates treat the interview as a collaborative design session -- like a meeting with a colleague to whiteboard an architecture. They ask clarifying questions, state assumptions explicitly, explain trade-offs, and invite the interviewer into the decision-making process.

> **Key Takeaway:** Data engineering interviews test five things: (1) Can you write production-quality SQL? (2) Can you design data systems? (3) Can you model data correctly? (4) Can you write Python for data tasks? (5) Can you communicate technical decisions clearly? This appendix prepares you for all five.

---

## Part 1: Data Modeling Interview Questions

Data modeling questions test whether you understand how to structure data for analytical workloads. These tie directly to Module 1 (Foundations) and Module 6 (dbt).

### Question 1: Design a Star Schema for a Ride-Sharing Company

**Interviewer:** "Design the data model for a ride-sharing analytics platform. The business wants to analyze ride volume, revenue, driver performance, and rider behavior."

**Strong answer:**

"I would start with a star schema centered on a `fact_rides` table. The grain is one row per completed ride.

**Fact table:**

```sql
fact_rides (
    ride_key            BIGINT,         -- Surrogate key
    ride_id             VARCHAR,        -- Business key
    rider_key           BIGINT,         -- FK to dim_rider
    driver_key          BIGINT,         -- FK to dim_driver
    pickup_location_key BIGINT,         -- FK to dim_location
    dropoff_location_key BIGINT,        -- FK to dim_location
    pickup_date_key     INT,            -- FK to dim_date
    pickup_time_key     INT,            -- FK to dim_time
    vehicle_key         BIGINT,         -- FK to dim_vehicle
    -- Measures
    ride_distance_miles DECIMAL(8,2),
    ride_duration_minutes DECIMAL(8,2),
    base_fare           DECIMAL(8,2),
    surge_multiplier    DECIMAL(4,2),
    total_fare          DECIMAL(8,2),
    driver_payout       DECIMAL(8,2),
    platform_fee        DECIMAL(8,2),
    tip_amount          DECIMAL(8,2),
    rating_by_rider     INT,            -- 1-5
    rating_by_driver    INT,            -- 1-5
    wait_time_minutes   DECIMAL(6,2),
    ride_status         VARCHAR         -- 'completed', 'cancelled_rider', 'cancelled_driver'
)
```

**Dimension tables:**

- `dim_rider`: rider demographics, signup date, lifetime rides, rider tier (SCD Type 2 for tier changes)
- `dim_driver`: driver demographics, signup date, vehicle type, average rating, driver tier (SCD Type 2)
- `dim_location`: city, neighborhood, latitude, longitude, H3 hex cell (for geospatial aggregation)
- `dim_date`: standard date dimension with day of week, holiday flags, fiscal period
- `dim_time`: hour, minute, time-of-day bucket (morning rush, midday, evening rush, late night)
- `dim_vehicle`: vehicle type, year, model, capacity

I would use SCD Type 2 on `dim_rider` and `dim_driver` because tier changes affect analysis. If a driver was 'gold' tier when they gave a ride, we want to know that, not just their current tier."

**Follow-up: "Why not a single timestamp column instead of separate date and time dimension keys?"**

"Separate date and time dimensions make aggregation much faster. If I want 'total rides on Saturdays during evening rush,' I can filter on `dim_date.day_of_week = 'Saturday'` and `dim_time.time_bucket = 'evening_rush'` using simple equality joins. With a single timestamp, every query needs date functions like `EXTRACT(DOW FROM timestamp)` and `EXTRACT(HOUR FROM timestamp)`, which cannot use sort keys or clustering as effectively."

**Follow-up: "How would you handle cancelled rides?"**

"I would include them in `fact_rides` with a `ride_status` column. Cancelled rides have measures of zero for fare and distance but still have valid data for wait time, location, and time. Analyzing cancellation patterns is a key business need: where are cancellations happening? Which drivers cancel most? What time of day has the highest cancellation rate? Excluding them would lose this analytical capability."

---

### Question 2: Explain SCD Types and When to Use Each

**Interviewer:** "What are Slowly Changing Dimensions and when would you use Type 1 vs Type 2 vs Type 3?"

**Strong answer:**

"Slowly Changing Dimensions handle the problem of attribute changes in dimension tables over time.

**Type 1 (Overwrite):** Replace the old value with the new value. No history is preserved. Use this when history does not matter -- for example, fixing a typo in a product name or updating a customer's email address.

**Type 2 (Add New Row):** Create a new row with the new value, marking the old row as inactive with `valid_from` and `valid_to` dates. This preserves full history. Use this when the change is analytically meaningful -- for example, when a customer changes their address (affects regional sales analysis) or when a customer's loyalty tier changes (affects behavior analysis).

**Type 3 (Add New Column):** Add a `previous_value` and `current_value` column. Only tracks one change. I almost never recommend this because it is limited to exactly one historical value, which is rarely sufficient.

In practice, I default to Type 1 for most attributes and use Type 2 selectively for attributes that drive analytical decisions. Over-using Type 2 causes dimension table bloat and query complexity. Under-using it means you lose important history.

A common mistake is using Type 2 for everything. If your `dim_customer` table has 1 million customers and you track 10 attributes with Type 2, you might end up with 15 million rows, most of which are historical and rarely queried. Be selective."

---

### Question 3: Normalize vs. Denormalize

**Interviewer:** "When would you normalize your data model and when would you denormalize it?"

**Strong answer:**

"The choice depends on the workload pattern.

**Normalize (3NF) when:**
- The system is write-heavy (OLTP) and you need to minimize data redundancy
- You need referential integrity enforced at the database level
- The data is the operational source of truth (transactional databases)
- Example: the production PostgreSQL database behind a web application

**Denormalize (star schema, wide tables) when:**
- The system is read-heavy (OLAP/analytics) and you need fast query performance
- Users are running aggregations, joins, and filters across large datasets
- The data is loaded in batch and queried frequently
- Example: a Snowflake data warehouse serving Tableau dashboards

**The trade-off in one sentence:** Normalization optimizes for write performance and data integrity. Denormalization optimizes for read performance and query simplicity.

In modern data engineering, the common pattern is: normalized in the source system, denormalized in the warehouse. The dbt transformation layer (Module 6) handles the conversion."

---

## Part 2: SQL Coding Challenges

SQL is the most tested skill in data engineering interviews. You will be asked to write queries on a whiteboard or in a shared coding environment. These questions map directly to Module 2 (SQL Mastery).

### Challenge 1: Deduplicate Records

**Problem:** "Given a table `raw_events` with duplicate records (same `event_id` appearing multiple times due to at-least-once delivery), write a query to deduplicate it, keeping only the first occurrence based on `received_at`."

```sql
-- Method 1: ROW_NUMBER (most common approach)
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY received_at ASC
        ) AS rn
    FROM raw_events
)
SELECT * FROM ranked WHERE rn = 1;

-- Method 2: QUALIFY (Snowflake/BigQuery -- more concise)
SELECT *
FROM raw_events
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY event_id
    ORDER BY received_at ASC
) = 1;
```

**What interviewers look for:** Do you know ROW_NUMBER vs RANK vs DENSE_RANK? (ROW_NUMBER assigns unique numbers even for ties; RANK leaves gaps; DENSE_RANK does not.) Can you explain why you chose `ORDER BY received_at ASC`? (We want the first occurrence, so ascending order puts it at row number 1.)

---

### Challenge 2: Running Totals and Moving Averages

**Problem:** "Write a query that shows daily revenue with a 7-day moving average and a running total for the month."

```sql
SELECT
    order_date,
    daily_revenue,
    -- 7-day moving average (current day + 6 preceding days)
    AVG(daily_revenue) OVER (
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d,
    -- Running total for the month (resets each month)
    SUM(daily_revenue) OVER (
        PARTITION BY DATE_TRUNC('month', order_date)
        ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS monthly_running_total
FROM (
    SELECT
        DATE_TRUNC('day', order_timestamp) AS order_date,
        SUM(total_amount) AS daily_revenue
    FROM orders
    GROUP BY 1
) daily
ORDER BY order_date;
```

**What interviewers look for:** Do you understand the difference between `ROWS BETWEEN` and `RANGE BETWEEN`? Can you explain why `PARTITION BY DATE_TRUNC('month', order_date)` resets the running total each month?

---

### Challenge 3: Gap and Island Detection

**Problem:** "Given a table of user login dates, find consecutive login streaks (islands) for each user."

```sql
-- Classic gaps-and-islands using the ROW_NUMBER trick
WITH numbered AS (
    SELECT
        user_id,
        login_date,
        -- Subtracting a sequential number from the date
        -- creates a constant value for consecutive dates
        login_date - INTERVAL '1 day' * ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY login_date
        ) AS group_key
    FROM (
        SELECT DISTINCT user_id, DATE_TRUNC('day', login_timestamp) AS login_date
        FROM user_logins
    ) daily_logins
)
SELECT
    user_id,
    MIN(login_date) AS streak_start,
    MAX(login_date) AS streak_end,
    COUNT(*) AS streak_days
FROM numbered
GROUP BY user_id, group_key
HAVING COUNT(*) >= 3  -- Only streaks of 3+ days
ORDER BY user_id, streak_start;
```

**Explain the trick:** If a user logs in on Jan 1, 2, 3, 5, 6: subtracting row numbers (1,2,3,4,5) from the dates gives (Dec 31, Dec 31, Dec 31, Jan 1, Jan 1). The consecutive days map to the same `group_key`, while the gap creates a new group.

---

### Challenge 4: Sessionization

**Problem:** "Given a table of page view events with timestamps, define a session as a group of events where no two consecutive events are more than 30 minutes apart. Assign session IDs."

```sql
WITH time_gaps AS (
    SELECT
        user_id,
        event_timestamp,
        page_url,
        LAG(event_timestamp) OVER (
            PARTITION BY user_id ORDER BY event_timestamp
        ) AS prev_event_ts,
        DATEDIFF('minute',
            LAG(event_timestamp) OVER (
                PARTITION BY user_id ORDER BY event_timestamp
            ),
            event_timestamp
        ) AS minutes_since_last
    FROM page_views
),
session_starts AS (
    SELECT
        *,
        CASE
            WHEN minutes_since_last IS NULL THEN 1      -- First event
            WHEN minutes_since_last > 30 THEN 1          -- New session
            ELSE 0
        END AS is_new_session
    FROM time_gaps
)
SELECT
    user_id,
    event_timestamp,
    page_url,
    SUM(is_new_session) OVER (
        PARTITION BY user_id
        ORDER BY event_timestamp
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_id
FROM session_starts;
```

**What interviewers look for:** Can you use LAG to compute inter-event time? Can you use a cumulative SUM of a flag to assign group IDs? This is a pattern that appears constantly in product analytics (Module 6, Case Study 3 in Appendix B).

---

### Challenge 5: Pivot / Unpivot

**Problem:** "Given a table with one row per student per subject with their score, pivot it to show one row per student with columns for each subject."

```sql
-- Pivot (rows to columns)
SELECT
    student_id,
    MAX(CASE WHEN subject = 'math' THEN score END) AS math_score,
    MAX(CASE WHEN subject = 'science' THEN score END) AS science_score,
    MAX(CASE WHEN subject = 'english' THEN score END) AS english_score
FROM student_scores
GROUP BY student_id;

-- Unpivot (columns to rows) -- Snowflake syntax
SELECT student_id, subject, score
FROM student_scores_wide
UNPIVOT (score FOR subject IN (math_score, science_score, english_score));
```

---

### Challenge 6: Cumulative Distinct Count

**Problem:** "For each day, show the cumulative number of distinct users who have ever made a purchase up to that day."

```sql
-- This is tricky because COUNT(DISTINCT) does not work as a window function
WITH first_purchases AS (
    SELECT
        user_id,
        MIN(DATE_TRUNC('day', purchase_timestamp)) AS first_purchase_date
    FROM purchases
    GROUP BY user_id
),
daily_new_users AS (
    SELECT
        first_purchase_date AS purchase_date,
        COUNT(*) AS new_users
    FROM first_purchases
    GROUP BY first_purchase_date
)
SELECT
    purchase_date,
    new_users,
    SUM(new_users) OVER (
        ORDER BY purchase_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_distinct_users
FROM daily_new_users
ORDER BY purchase_date;
```

**The key insight:** You cannot use `COUNT(DISTINCT user_id)` as a window function over expanding frames. Instead, find each user's first purchase date, count new users per day, then use a cumulative SUM.

---

## Part 3: System Design for Data Pipelines

System design interviews for data engineers focus on designing data systems, not web applications. You will be asked to design ETL pipelines, real-time analytics systems, and data platforms.

### The 45-Minute Structure

**Minutes 1-8: Requirements and Scale Estimation**

Ask clarifying questions. The interviewer deliberately leaves the problem ambiguous.

Sample dialogue:

> **You**: "Before I start designing, I'd like to understand the requirements. When you say 'design a data warehouse for analytics,' who are the primary users?"
>
> **Interviewer**: "We have about 20 analysts, a few executives, and a data science team."
>
> **You**: "Got it. And what's the data volume? Are we talking gigabytes or petabytes?"
>
> **Interviewer**: "We process about 50,000 orders per day, so maybe a few terabytes total."
>
> **You**: "And for freshness -- do stakeholders need real-time data, or is daily sufficient?"

Always estimate scale: "50,000 orders/day times 500 bytes is about 25 MB/day raw. Over 5 years, that is 45 GB. With dimension tables and 3x overhead: roughly 150 GB. This is well within a single Snowflake warehouse."

**Minutes 8-20: High-Level Architecture**

Draw 5-7 boxes connected by arrows. State technology choices with one-sentence justifications.

```
[Data Sources] --> [Ingestion (Airbyte)] --> [Raw Storage (S3)]
    --> [Transform (dbt on Snowflake)] --> [Analytics Tables]
                                                --> [BI (Tableau)]
                                                --> [ML (Python)]
```

**Minutes 20-35: Component Deep Dive**

The interviewer steers you to the most interesting component. Go deep: data models, schema design, query patterns, error handling.

**Minutes 35-40: Scale and Optimize**

Identify bottlenecks: "At 10x scale, the transformation step becomes the bottleneck. I would switch from full-refresh to incremental dbt models and parallelize independent transformations."

**Minutes 40-45: Trade-offs and Alternatives**

Acknowledge what you sacrificed: "I chose Snowflake over BigQuery because the team is multi-cloud, but BigQuery would be cheaper for sporadic query patterns."

---

### Design Problem 1: Real-Time Analytics Dashboard

**Prompt:** "Design a system that shows real-time metrics (orders per minute, revenue, active users) on a dashboard that updates every 10 seconds."

**Strong answer structure:**

```
[Web App Events] ---> [Kafka] ---> [Flink/Spark Streaming] ---> [Redis]
[Mobile Events]  --->                                              |
[API Events]     --->                                              v
                                                            [Dashboard (WebSocket)]
                           |
                           v (parallel path)
                      [S3 Parquet] ---> [Snowflake] ---> [Tableau]
                      (batch archive)   (historical)     (historical dashboards)
```

"I would use a lambda architecture with two paths:

**Real-time path:** Events flow through Kafka, processed by Flink for windowed aggregations (orders per minute, running revenue totals), and written to Redis. The dashboard reads from Redis via WebSocket for sub-second updates.

**Batch path:** The same Kafka events are also written to S3 as Parquet files (hourly partitions), loaded into Snowflake by dbt for historical analytics. This gives us the full history for trend analysis, cohort analysis, and ad-hoc queries.

**Why two paths?** Real-time aggregations in Redis are approximate and ephemeral (last 24 hours). Batch processing in Snowflake is exact and permanent. The real-time dashboard answers 'what is happening right now?' while the historical dashboards answer 'what happened last quarter?'

**Key design decisions:**
- Kafka partitioned by event type (orders, page views, user actions) for parallel processing
- Flink tumbling windows of 60 seconds for per-minute metrics, with late event tolerance of 5 minutes
- Redis TTL of 24 hours on real-time aggregations (do not keep stale data)
- S3 lifecycle policy: Standard for 30 days, IA for 90 days, Glacier for 1 year

**What breaks first at 10x scale?** Redis becomes the bottleneck for writes. I would shard Redis by metric type and add read replicas for the dashboard. Kafka scales horizontally by adding partitions. Flink scales by adding task slots."

---

### Design Problem 2: ETL Pipeline for a Data Warehouse

**Prompt:** "Design an ETL pipeline that ingests data from 10 different sources (3 databases, 4 APIs, 3 file drops) into a data warehouse for a team of 30 analysts."

**Strong answer structure:**

"First, let me understand the sources:
- 3 databases (PostgreSQL, MySQL, MongoDB): CDC for real-time, full extract for initial load
- 4 APIs (Salesforce, HubSpot, Stripe, Google Analytics): scheduled extraction, rate-limited
- 3 file drops (CSV files from partners, landing in S3): event-driven trigger

```
[PostgreSQL]  --CDC--->  [Airbyte]  --->  [S3 Raw Layer]
[MySQL]       --CDC--->                        |
[MongoDB]     --CDC--->                        v
[Salesforce]  --API--->               [Snowflake Raw Schema]
[HubSpot]     --API--->                        |
[Stripe]      --API--->                        v
[GA4]         --API--->              [dbt: Staging -> Intermediate -> Marts]
[Partner CSV] --S3 event--->                   |
                                    +----------+----------+
                                    |          |          |
                                    v          v          v
                              [Marketing   [Finance   [Product
                               Marts]       Marts]     Marts]
                                    |          |          |
                                    v          v          v
                              [Tableau]   [Mode]    [Jupyter]
```

**Orchestration:** Airflow with a dependency chain:
1. Extract all sources in parallel (10 Airbyte sync jobs)
2. Wait for all extracts to complete (using Airflow sensor or trigger rules)
3. Run dbt staging models (clean each source independently)
4. Run dbt intermediate models (join across sources)
5. Run dbt mart models (business-specific aggregations)
6. Run dbt tests (data quality)
7. Notify Slack on success, PagerDuty on failure

**Data modeling:** Star schema in the marts layer. Key fact tables: `fact_orders`, `fact_leads`, `fact_website_sessions`. Shared dimensions: `dim_customer`, `dim_product`, `dim_date`. Customer dimension uses SCD Type 2 for segment changes.

**Error handling:**
- Airbyte retries each source 3 times with exponential backoff
- If a source fails, the pipeline continues with other sources (partial load is better than no load)
- dbt tests run after transformation; failures alert but do not block dashboard access to yesterday's data
- Idempotent loads: every run can be safely re-executed without creating duplicates

**Cost estimate:** Airbyte Cloud ($500/month for 10 connectors), Snowflake ($3K-$5K/month for this volume), Airflow on Astronomer ($400/month). Total: roughly $5K/month for 30 analysts."

---

### Design Problem 3: Data Lake to Lakehouse Migration

**Prompt:** "Your company has a 500 TB data lake on S3 with Parquet files, queried by Spark and Athena. Leadership wants to migrate to a lakehouse architecture. Design the migration."

**Strong answer:**

"I would migrate to Apache Iceberg on top of the existing S3 data. Iceberg gives us ACID transactions, schema evolution, time travel, and partition evolution without moving the data to a new system.

**Phase 1 (weeks 1-4): Foundation**
- Deploy an Iceberg catalog (AWS Glue Catalog or Nessie for git-like branching)
- Convert the 10 most-queried tables from Parquet to Iceberg format using in-place migration (Iceberg can register existing Parquet files without rewriting them)
- Validate that existing Spark jobs and Athena queries work against Iceberg tables

**Phase 2 (weeks 5-8): Pipeline migration**
- Update Spark write paths to use Iceberg's merge-on-read for incremental updates
- Implement partition evolution: migrate from static `year/month/day` partitioning to Iceberg's hidden partitioning (queries do not need to know about partition structure)
- Add schema evolution: enable column additions and renames without breaking existing queries

**Phase 3 (weeks 9-12): Advanced features**
- Enable time travel for debugging and auditing (query data as of any point in time)
- Implement table maintenance: compaction (merge small files), expire snapshots (clean up old metadata), orphan file cleanup
- Connect Snowflake as a query engine for analyst access (Snowflake supports Iceberg external tables)

**Key trade-off:** Iceberg vs Delta Lake vs Hudi. I chose Iceberg because of its vendor neutrality (works with Spark, Flink, Trino, Snowflake, BigQuery), its hidden partitioning (the strongest partition evolution story), and its momentum in the open-source community. Delta Lake is strong if you are committed to the Databricks ecosystem."

---

## Part 4: Python Coding for Data Engineering Interviews

Python questions in DE interviews focus on practical data tasks, not algorithms. You will be asked to write API clients, file processors, and data validators.

### Challenge 1: API Client with Pagination and Rate Limiting

**Problem:** "Write a Python function that fetches all records from a paginated REST API, handling rate limits (429 responses) with exponential backoff."

```python
import requests
import time
from typing import Generator

def fetch_all_records(base_url: str, api_key: str,
                      max_retries: int = 5) -> Generator[dict, None, None]:
    """Fetch all records from a paginated API with rate limit handling.

    Yields individual records. Handles pagination via cursor-based
    pagination and rate limits via exponential backoff.
    """
    cursor = None
    retry_count = 0

    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = requests.get(base_url, params=params,
                                    headers=headers, timeout=30)

            if response.status_code == 429:
                # Rate limited: exponential backoff
                retry_count += 1
                if retry_count > max_retries:
                    raise Exception(f"Rate limited {max_retries} times, giving up")
                wait_time = min(2 ** retry_count, 60)  # Max 60 seconds
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait_time = int(retry_after)
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            retry_count = 0  # Reset on success

            data = response.json()
            for record in data["results"]:
                yield record

            # Check for next page
            cursor = data.get("next_cursor")
            if not cursor:
                break  # No more pages

        except requests.exceptions.Timeout:
            retry_count += 1
            if retry_count > max_retries:
                raise
            time.sleep(2 ** retry_count)


# Usage:
# for record in fetch_all_records("https://api.example.com/users", "key123"):
#     process(record)
```

**What interviewers look for:** Generator pattern (memory efficient for large datasets), exponential backoff, proper error handling, respecting Retry-After headers, timeout on requests.

---

### Challenge 2: File Processing with Schema Validation

**Problem:** "Write a function that reads a CSV file, validates each row against a schema, writes valid rows to a Parquet file, and logs invalid rows to a separate error file."

```python
import csv
import json
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]

def validate_row(row: dict, schema: dict) -> ValidationResult:
    """Validate a single row against a schema definition.

    Schema format:
    {
        "columns": {
            "user_id": {"type": "int", "required": True},
            "email": {"type": "str", "required": True, "pattern": "@"},
            "age": {"type": "int", "required": False, "min": 0, "max": 150},
        }
    }
    """
    errors = []

    for col_name, rules in schema["columns"].items():
        value = row.get(col_name)

        # Required check
        if rules.get("required") and (value is None or value == ""):
            errors.append(f"{col_name}: required but missing")
            continue

        if value is None or value == "":
            continue

        # Type check
        expected_type = rules.get("type")
        if expected_type == "int":
            try:
                int(value)
            except ValueError:
                errors.append(f"{col_name}: expected int, got '{value}'")
                continue
        elif expected_type == "float":
            try:
                float(value)
            except ValueError:
                errors.append(f"{col_name}: expected float, got '{value}'")
                continue

        # Range check
        if "min" in rules and float(value) < rules["min"]:
            errors.append(f"{col_name}: {value} below minimum {rules['min']}")
        if "max" in rules and float(value) > rules["max"]:
            errors.append(f"{col_name}: {value} above maximum {rules['max']}")

        # Pattern check
        if "pattern" in rules and rules["pattern"] not in str(value):
            errors.append(f"{col_name}: does not match pattern '{rules['pattern']}'")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def process_csv_to_parquet(
    input_path: str,
    output_path: str,
    error_path: str,
    schema: dict
) -> dict:
    """Read CSV, validate, write valid rows to Parquet, errors to JSON lines."""
    valid_rows = []
    error_count = 0
    total_count = 0

    with open(input_path, "r") as csv_file, \
         open(error_path, "w") as error_file:

        reader = csv.DictReader(csv_file)

        for row in reader:
            total_count += 1
            result = validate_row(row, schema)

            if result.is_valid:
                valid_rows.append(row)
            else:
                error_count += 1
                error_record = {
                    "row_number": total_count,
                    "row_data": row,
                    "errors": result.errors,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                error_file.write(json.dumps(error_record) + "\n")

    # Write valid rows to Parquet
    if valid_rows:
        table = pa.Table.from_pylist(valid_rows)
        pq.write_table(table, output_path, compression="snappy")

    return {
        "total_rows": total_count,
        "valid_rows": len(valid_rows),
        "error_rows": error_count,
        "error_rate": round(error_count / max(total_count, 1), 4),
    }
```

**What interviewers look for:** Clean separation of validation and I/O, use of Parquet (not CSV) for output, error logging with context (row number, specific error), summary statistics returned.

---

### Challenge 3: Data Deduplication in Python

**Problem:** "Write a function that deduplicates records from a large file that does not fit in memory. Records are JSON lines with an `id` field."

```python
import json
import hashlib
from pathlib import Path
from typing import Iterator

def deduplicate_large_file(
    input_path: str,
    output_path: str,
    key_field: str = "id"
) -> dict:
    """Deduplicate a JSON lines file that may not fit in memory.

    Uses a set of hashed keys (much smaller than full records)
    to track seen records. For a file with 100M records and
    UUID keys, the set uses roughly 4 GB of memory.

    For truly massive files, use an external sort or Bloom filter.
    """
    seen_keys = set()
    total = 0
    duplicates = 0

    with open(input_path, "r") as infile, \
         open(output_path, "w") as outfile:

        for line in infile:
            total += 1
            record = json.loads(line)
            key = record.get(key_field)

            if key is None:
                # No key -- write it (or skip it, depending on requirements)
                outfile.write(line)
                continue

            # Hash the key to save memory (16 bytes vs variable-length string)
            key_hash = hashlib.md5(str(key).encode()).digest()

            if key_hash not in seen_keys:
                seen_keys.add(key_hash)
                outfile.write(line)
            else:
                duplicates += 1

    return {
        "total_records": total,
        "unique_records": total - duplicates,
        "duplicates_removed": duplicates,
    }
```

**Follow-up: "What if even the key hashes do not fit in memory?"**

"I would use a probabilistic approach with a Bloom filter. It gives a small false positive rate (maybe 0.1%), meaning some duplicates might slip through, but it uses dramatically less memory. For a 0.1% false positive rate with 1 billion records, a Bloom filter uses about 1.2 GB. Alternatively, I would sort the file externally (using Unix `sort` or a merge sort on disk) and then deduplicate the sorted output in a single pass."

---

## Part 5: Behavioral Questions for Data Engineers

Behavioral questions in DE interviews are specific to the challenges of working with data: quality issues, pipeline failures, stakeholder communication, and technical trade-offs.

### Question 1: "Tell me about a time data quality failed."

**Framework:** Use STAR (Situation, Task, Action, Result) but lead with the impact.

**Example answer:**

"At my previous company, we had a data quality incident that went undetected for three weeks. Our marketing team was running campaigns based on a customer segmentation model that relied on purchase frequency data. A schema change in our source PostgreSQL database renamed a column from `order_total` to `total_amount`. Our extraction pipeline did not break -- it just started loading NULLs for that column.

**Impact:** The segmentation model classified high-value customers as inactive because their purchase amounts appeared to be zero. Marketing sent win-back campaigns to our best customers, which felt insulting and generated complaints.

**What I did:** First, I fixed the extraction to handle the renamed column. Second, I backfilled three weeks of data. Third -- and this is the important part -- I implemented three preventive measures:
1. Schema drift detection in our ingestion layer that alerts when source columns change
2. A dbt test on the orders model: `accepted_range` on `order_total` with a minimum of $0.01 (null or zero values fail the test)
3. A daily anomaly check that compares today's average order value against the 30-day rolling average and alerts if it deviates by more than 20%

**Result:** We have not had a similar incident in the 18 months since. The schema drift detection has caught 4 upstream changes before they affected downstream models."

---

### Question 2: "Tell me about a time you disagreed with a stakeholder about technical approach."

**Example answer:**

"Our VP of Analytics wanted to switch from Snowflake to BigQuery because BigQuery's per-query pricing seemed cheaper for our usage pattern. I disagreed because the migration would take 3-4 months, our 20 analysts would need retraining on BigQuery SQL dialects, and our dbt models had Snowflake-specific SQL that would need rewriting.

I did not just say 'no.' I ran the numbers. I estimated the total cost of migration: 3 months of engineering time (roughly $120K in loaded salary), analyst productivity loss during transition (estimated 30% reduction for 2 months), and the risk of pipeline incidents during migration.

Then I showed that we could achieve the same cost savings ($40K/year) by optimizing our Snowflake usage: auto-suspend on idle warehouses, materialized views for the top 10 dashboard queries, and right-sizing our ETL warehouse from Large to Medium.

The VP agreed to the optimization approach. We achieved the cost savings in 2 weeks instead of 3 months. The lesson: when you disagree, come with data and an alternative solution, not just objections."

---

### Question 3: "How do you prioritize when everything is urgent?"

**Example answer:**

"I use a simple framework: revenue impact times time sensitivity. A broken billing pipeline that affects invoicing this week is higher priority than a slow dashboard that annoys analysts.

Concretely, I categorize issues into four tiers:
- **P0:** Data loss or corruption affecting production systems or financial reporting. Drop everything.
- **P1:** Pipeline failures affecting stakeholder SLAs (dashboards not refreshed by agreed time). Fix today.
- **P2:** Performance degradation or non-critical quality issues. Fix this week.
- **P3:** Improvements, optimizations, technical debt. Scheduled in sprint planning.

I communicate this prioritization to stakeholders immediately. If an analyst asks me to investigate a dashboard discrepancy and I am in the middle of fixing a pipeline that feeds financial reporting, I tell them: 'I am fixing a P0 issue affecting finance. I will look at your dashboard issue this afternoon. If you need it sooner, here is the raw data query you can run directly.'"

---

### Question 4: "Describe a pipeline you built from scratch."

**Framework:** Walk through the pipeline end-to-end, but focus on decisions and trade-offs, not just technology.

"I built the customer analytics pipeline at [Company]. The source was our PostgreSQL production database with customer, order, and product data. The requirement was daily refreshed dashboards for 20 analysts showing customer lifetime value, cohort retention, and product affinity.

**Decision 1: Ingestion method.** I chose CDC (Change Data Capture) via Airbyte rather than full extracts. With 5 million customer records, a full extract took 45 minutes. CDC captured only changes, reducing ingestion to under 3 minutes. The trade-off: CDC is more complex to set up and can miss changes if the WAL is purged.

**Decision 2: Transformation approach.** I used dbt with incremental models for the fact tables. The `fact_orders` table grows by 50K rows/day; full refresh would scan 20M rows every run. Incremental processing touches only new and updated rows.

**Decision 3: Data quality.** I implemented three layers of tests: dbt generic tests (not null, unique, relationships), dbt custom tests (order amounts within expected range, no future-dated orders), and a daily reconciliation against the source database (total orders and revenue must match).

The pipeline ran in Airflow with a 2 AM start time and a 6:30 AM SLA. It consistently completed in 18 minutes. Over 12 months, we had 2 incidents: one Snowflake outage (not our fault) and one schema change in the source database (caught by our schema drift detection within 15 minutes)."

---

## Part 6: Take-Home Project Tips

Many companies include a take-home project in the DE interview process. This is where your Module 10 capstone becomes your secret weapon.

### Your Capstone IS Your Take-Home

If a company asks you to "build a data pipeline that ingests, transforms, and serves data," you have already done this. Adapt your capstone:

1. **Read the requirements carefully.** Match your capstone architecture to their specific ask. Do they want real-time? Add a Kafka component. Do they want ML? Add a simple model. Do they want cost analysis? Include it (you covered this in Appendix A).

2. **Do not over-engineer.** A clean, well-documented pipeline with 5 components beats a sprawling system with 15 components and no documentation. Reviewers spend 30-60 minutes evaluating your project. Make it easy to understand.

3. **Include a README with these sections:**
   - Architecture diagram (even ASCII art works)
   - How to run it (Docker Compose up, ideally)
   - Technology choices and why
   - Data model with schema descriptions
   - What you would do differently with more time
   - What breaks at 10x scale

4. **Include tests.** Even 5-10 tests show that you think about quality. Test your dbt models, test your Python functions, test your API responses.

5. **Include monitoring.** Even a simple `print(f"Loaded {row_count} rows in {duration}s")` shows operational awareness. A Grafana dashboard is better. Airflow with alerting is best.

### Common Take-Home Mistakes

- **No README or poor documentation.** The reviewer cannot figure out how to run it. Automatic fail.
- **Works on your machine only.** Not containerized, hard-coded paths, missing dependencies. Use Docker.
- **No error handling.** The API returns a 500 and the pipeline crashes with an unhandled exception.
- **No data quality.** Raw data flows straight to the output with no validation, deduplication, or null handling.
- **Premature optimization.** Using Kafka, Flink, and Redis for a project that processes 1000 rows. Shows lack of judgment.

---

## Part 7: Company-Specific Interview Preparation

### FAANG / Big Tech (Google, Meta, Amazon, Netflix, Apple)

**Format:** Typically 5-6 rounds over a full day (virtual or on-site):
1. SQL coding (45 min): Medium to hard LeetCode-style SQL problems. Window functions, CTEs, self-joins.
2. Python coding (45 min): Data processing tasks, not algorithmic puzzles.
3. System design (45 min): "Design a data pipeline for..." at massive scale.
4. Data modeling (45 min): Design a star schema, discuss trade-offs, handle edge cases.
5. Behavioral (45 min): Leadership principles (Amazon), collaboration stories, handling ambiguity.
6. Hiring manager (30 min): Culture fit, career goals, team dynamics.

**What differentiates FAANG interviews:**
- Scale expectations are higher. "How does this work at 1 billion events per day?" is a normal follow-up.
- They care about custom solutions. "Kafka does not meet our latency requirements at this scale. What would you build?"
- They test fundamentals deeply. Do not just know that Parquet is columnar; explain how column pruning reduces I/O.
- Behavioral questions are rigorous, especially at Amazon (every answer should map to a Leadership Principle).

**Preparation tips:**
- Practice SQL daily for 2 weeks before the interview. Use LeetCode Database problems (medium and hard).
- Prepare 8-10 behavioral stories using STAR format. Ensure each story demonstrates a different quality (technical depth, conflict resolution, working with ambiguity, delivering under pressure).
- Study the company's public engineering blog. Netflix Tech Blog, Meta Engineering, Google Cloud Blog all publish articles about their data infrastructure.

---

### Unicorn / Late-Stage Startup (Stripe, Databricks, Snowflake, Airbnb)

**Format:** Typically 4-5 rounds:
1. Technical screen (SQL + Python, 60 min)
2. System design (45-60 min)
3. Practical/take-home project (2-4 hours, done at home)
4. Behavioral + culture fit (45 min)
5. Hiring manager (30 min)

**What differentiates unicorn interviews:**
- More practical and less theoretical than FAANG. "How would you actually build this?" vs "What is the theoretical optimal approach?"
- Take-home projects are common. You may build a small pipeline from scratch.
- They value speed of delivery. Can you build something good in 4 hours?
- Domain knowledge matters. If interviewing at Stripe, know payment data. At Databricks, know Spark deeply.

---

### Mid-Market and Enterprise Companies

**Format:** Typically 3-4 rounds:
1. Technical screen (SQL focus, 45 min)
2. System design or architecture discussion (45 min)
3. Behavioral (30-45 min)
4. Hiring manager (30 min)

**What differentiates enterprise interviews:**
- SQL is the primary technical assessment. Window functions, CTEs, and performance tuning.
- Less emphasis on distributed systems and more on data modeling, warehouse optimization, and BI integration.
- They care about communication with non-technical stakeholders. "How would you explain this data model to a product manager?"
- Domain knowledge can be a significant advantage (healthcare, finance, retail).

---

### Early-Stage Startup (Seed to Series B)

**Format:** Typically 2-3 rounds:
1. Technical conversation (60 min, mix of SQL, Python, and architecture)
2. Take-home project or pair programming (2-3 hours)
3. Founder/CTO (30-45 min)

**What differentiates startup interviews:**
- Breadth over depth. Can you do ingestion AND transformation AND analytics AND infra?
- They want to see pragmatism. "I would use BigQuery and dbt Cloud to ship this in 2 weeks" beats "I would design a custom lakehouse architecture."
- Speed and scrappiness matter. They need someone who can build the first version alone.
- Culture fit with the founding team matters as much as technical ability.

---

## Part 8: Practice Plan

### 4-Week Interview Preparation Schedule

**Week 1: SQL Foundations**
- Days 1-3: Practice 3 medium SQL problems per day (LeetCode Database section)
- Days 4-5: Practice 2 hard SQL problems per day
- Days 6-7: Write SQL solutions to the challenges in Part 2 of this appendix from memory

**Week 2: System Design + Data Modeling**
- Days 1-2: Practice designing an ETL pipeline (Design Problem 2 above). Time yourself to 45 minutes.
- Days 3-4: Practice designing a real-time system (Design Problem 1 above). Time yourself to 45 minutes.
- Days 5-6: Practice data modeling questions (Part 1 above). Draw schemas on paper.
- Day 7: Review the case studies in Appendix B. Practice describing one architecture in 5 minutes.

**Week 3: Python + Behavioral**
- Days 1-3: Code the Python challenges in Part 4. Then write them again from memory.
- Days 4-5: Write out your behavioral stories (Part 5). Practice delivering them out loud in 2 minutes each.
- Days 6-7: Mock interview with a friend or practice partner. Full 45-minute system design.

**Week 4: Company-Specific Prep**
- Days 1-2: Research the specific company. Read their engineering blog. Understand their data stack.
- Days 3-4: Practice the interview format specific to that company type (Part 7 above).
- Days 5-6: Review weak areas identified in mock interviews.
- Day 7: Rest. You are prepared.

---

## Quick Reference: What to Review the Night Before

- [ ] Star schema design pattern: fact tables, dimension tables, grain, surrogate keys
- [ ] SCD Type 1 vs Type 2 (when to use each)
- [ ] SQL window functions: ROW_NUMBER, RANK, LAG, LEAD, SUM OVER
- [ ] CTE syntax and when to use CTEs vs subqueries
- [ ] Deduplication pattern: ROW_NUMBER OVER (PARTITION BY key ORDER BY timestamp)
- [ ] Python: requests library, error handling, generators
- [ ] System design: Lambda architecture (real-time + batch paths)
- [ ] Kafka basics: topics, partitions, consumer groups, at-least-once delivery
- [ ] dbt basics: staging → intermediate → marts, incremental models, tests
- [ ] Airflow basics: DAGs, operators, sensors, task dependencies
- [ ] Cost optimization: auto-suspend, partition pruning, lifecycle policies
- [ ] Your 3 best behavioral stories (data quality failure, technical disagreement, pipeline build)
- [ ] Your capstone project architecture (be ready to draw it from memory)

> **Key Takeaway:** Interview preparation is not about memorizing answers. It is about internalizing patterns so deeply that you can apply them to any question. The SQL patterns, system design structures, and communication frameworks in this appendix are the same patterns used in every module of this course. You have been preparing for these interviews since Module 0. Trust your preparation, communicate clearly, and show your thinking process.
