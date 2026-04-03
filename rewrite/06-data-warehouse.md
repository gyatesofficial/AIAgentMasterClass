# Module 6: Data Warehouse Architecture

## What is a Data Warehouse?

A data warehouse is a central repository where structured data from across your organization is collected, integrated, and stored for analytical querying. It's the single source of truth for business intelligence — the place where analysts, executives, and data scientists go to answer questions about the business.

How it differs from a regular database: your transactional database (PostgreSQL, MySQL) is optimized for running your application — fast point lookups, concurrent writes, ACID transactions. A data warehouse is optimized for *analytical queries* — scanning millions of rows, computing aggregations, joining large tables. Trying to run heavy analytics on your production database is like using a sports car to haul freight: technically possible, but a terrible idea that will slow down both workloads.

The data warehouse landscape has shifted dramatically over the past decade. On-premises warehouses (Teradata, Oracle, Netezza) required massive upfront investment and a dedicated team to manage. Cloud warehouses (Snowflake, BigQuery, Redshift) flipped the model: no infrastructure to manage, elastic compute, and pay-as-you-go pricing.

> **Key Takeaway:** A data warehouse isn't just a "big database." It's architecturally different — optimized for scanning, aggregation, and complex joins on large datasets, with separate compute and storage, columnar format, and MPP (Massively Parallel Processing) execution.

---

## Cloud Warehouse Deep Dive

### Snowflake

Snowflake's architecture has three layers that scale independently:

**Storage Layer**: Data is stored in a proprietary columnar format on cloud object storage (S3, GCS, or Azure Blob). You pay for storage regardless of compute usage. Data is automatically compressed and organized into **micro-partitions** — contiguous chunks of 50-500 MB that contain metadata (min/max values per column) for efficient pruning.

**Compute Layer**: Virtual warehouses are clusters of compute nodes that execute queries. The key insight: compute and storage are fully separated. You can spin up multiple warehouses of different sizes, each querying the same data simultaneously. A small warehouse for ad-hoc queries, a large one for ETL, and a medium one for dashboards — all hitting the same tables without interference.

**Cloud Services Layer**: Handles authentication, query parsing, optimization, metadata management, and transaction coordination. This runs 24/7 and is included in your Snowflake bill (though it's typically a small percentage).

**Killer features**: Zero-copy cloning (instantly create a full copy of a table or database for development/testing — no additional storage until data diverges), time travel (query data as it existed up to 90 days ago), automatic clustering (Snowflake reorganizes micro-partitions in the background).

### BigQuery

BigQuery is Google's serverless warehouse, built on two internal technologies:

**Dremel**: The distributed query execution engine. It uses a tree architecture where a root node distributes query fragments to thousands of leaf nodes, each scanning a portion of the data in parallel. This is why BigQuery can scan petabytes in seconds.

**Colossus**: Google's distributed file system that stores data in a columnar format called Capacitor. Data is automatically replicated and encrypted.

**Serverless model**: There are no clusters to manage. You submit a query, BigQuery allocates resources, runs it, and you pay for the data scanned. This is ideal for variable workloads — you're not paying for idle compute during off-hours.

**Pricing options**: On-demand ($5 per TB scanned — great for variable/exploratory use) or flat-rate slots (reserved compute capacity — better for predictable, heavy workloads).

### Amazon Redshift

Redshift is the oldest major cloud warehouse. It uses a **node-based architecture** — you choose a cluster size and node type. This is closer to traditional provisioning but offers Redshift Serverless as a newer option.

**Strengths**: Deep AWS integration, lower cost for predictable workloads with reserved instances, familiar PostgreSQL-compatible SQL.

**Limitations**: Less elastic than Snowflake (resizing a cluster takes time), manual vacuum/analyze required for optimal performance.

### Comparison

| Feature | Snowflake | BigQuery | Redshift |
|---------|-----------|----------|----------|
| Architecture | Separate compute/storage | Serverless | Node-based (+ serverless option) |
| Scaling | Instant (add/resize warehouses) | Automatic | Minutes to resize |
| Pricing model | Per-second compute + storage | Per-TB scanned or flat-rate | Per-node-hour + storage |
| Best for | Multi-workload, multi-team | Variable/unpredictable queries | Predictable AWS workloads |
| Concurrency | Excellent (multi-cluster) | Excellent (auto-scaled) | Good (with WLM tuning) |
| Ecosystem | Multi-cloud | GCP-native | AWS-native |

---

## Partitioning and Clustering

As data volumes grow, full table scans become expensive and slow. **Partitioning** and **clustering** let the query engine skip irrelevant data.

### Partitioning

Partitioning divides a table into segments based on a column value — typically a date. When a query filters on the partition column, the engine only reads the relevant partitions, skipping the rest entirely.

In BigQuery, partition pruning can turn a multi-terabyte scan into a few gigabytes:

```sql
-- Create a partitioned table in BigQuery
CREATE TABLE analytics.user_events (
    event_id      STRING,
    user_id       STRING,
    event_type    STRING,
    event_data    JSON,
    event_date    DATE
)
PARTITION BY event_date
CLUSTER BY user_id, event_type;

-- This query only scans partitions for April 2026 — not the full table.
-- If the table has 3 years of data, you just skipped ~97% of it.
SELECT event_type, COUNT(*) as event_count
FROM analytics.user_events
WHERE event_date BETWEEN '2026-04-01' AND '2026-04-30'
GROUP BY event_type;
```

### Clustering

Clustering sorts data within each partition by specified columns. When a query filters on the clustering columns, the engine can skip blocks of data within a partition. In the example above, clustering by `user_id, event_type` means queries filtering on a specific user or event type will be fast even within a single day's partition.

**Snowflake's approach**: Snowflake automatically clusters micro-partitions based on the order data was loaded. You can define explicit clustering keys for tables where the natural insert order doesn't match query patterns:

```sql
-- Snowflake: define clustering keys for optimal query pruning
ALTER TABLE analytics.user_events
CLUSTER BY (event_date, user_id);

-- Check clustering quality
SELECT SYSTEM$CLUSTERING_INFORMATION('analytics.user_events');
```

> **Key Takeaway:** Always partition time-series data by date — it's the single most impactful optimization for analytical tables. Add clustering on frequently filtered columns (user_id, region, product_category) for additional speedup.

---

## Materialized Views and Query Optimization

### Materialized Views

A materialized view is a pre-computed query result stored as a table. Instead of running an expensive aggregation every time someone loads a dashboard, you compute it once and serve from the materialized view.

```sql
-- Create a materialized view for daily revenue by category
-- This query runs once. Dashboards read from the view instantly.
CREATE MATERIALIZED VIEW analytics.daily_revenue_by_category AS
SELECT
    DATE_TRUNC('day', order_date) AS day,
    p.category,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    COUNT(DISTINCT o.customer_id) AS unique_customers
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
GROUP BY 1, 2;

-- Dashboards query the materialized view — sub-second response
SELECT day, category, revenue
FROM analytics.daily_revenue_by_category
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY day, revenue DESC;
```

**When to use materialized views vs. caching vs. pre-aggregation tables:**
- **Materialized views**: Automated refresh, query optimizer can redirect queries automatically. Best for standard aggregations that many users run.
- **Result caching**: Warehouse-level caching of identical queries. Zero cost but only helps when the exact same query is repeated.
- **Pre-aggregation tables**: Manually managed summary tables built by your ETL pipeline. More control but more maintenance. Best for complex transformations the warehouse can't express as a materialized view.

### Query Optimization Techniques

**1. Avoid SELECT ***: Only select the columns you need. In a columnar warehouse, every extra column is additional I/O.

```sql
-- BAD: Reads all 50 columns from disk
SELECT * FROM user_events WHERE event_date = '2026-04-01';

-- GOOD: Reads only 3 columns — potentially 15x less I/O
SELECT user_id, event_type, event_data
FROM user_events
WHERE event_date = '2026-04-01';
```

**2. Filter early**: Push filters as close to the source tables as possible. Join smaller result sets.

**3. Use approximate functions**: When exact counts aren't needed, `APPROX_COUNT_DISTINCT()` is much faster than `COUNT(DISTINCT)` on large datasets.

```sql
-- Exact distinct count — may scan billions of values
SELECT COUNT(DISTINCT user_id) FROM user_events;

-- Approximate — ~2% error but 10-100x faster
SELECT APPROX_COUNT_DISTINCT(user_id) FROM user_events;
```

**4. Understand your query execution plan**: Use `EXPLAIN` to see how the warehouse plans to execute your query. Look for full table scans on large tables, missing partition pruning, and inefficient join orders.

---

## Multi-Tenant Analytics

In most organizations, multiple teams share the same data warehouse. Product analytics, marketing, finance, data science — each with different query patterns, SLAs, and cost sensitivities. Designing for multiple tenants requires balancing isolation with efficiency.

### Workload Isolation

In Snowflake, create separate virtual warehouses per team or workload type:

```sql
-- ETL warehouse: large, runs at night, auto-suspends quickly
CREATE WAREHOUSE etl_warehouse
    WAREHOUSE_SIZE = 'X-LARGE'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;

-- Analyst warehouse: medium, available during business hours
CREATE WAREHOUSE analyst_warehouse
    WAREHOUSE_SIZE = 'MEDIUM'
    AUTO_SUSPEND = 300
    AUTO_RESUME = TRUE;

-- Dashboard warehouse: small but always on for consistent performance
CREATE WAREHOUSE dashboard_warehouse
    WAREHOUSE_SIZE = 'SMALL'
    AUTO_SUSPEND = 0
    AUTO_RESUME = TRUE;
```

This ensures the nightly ETL job doesn't slow down analyst queries, and a data scientist running an expensive query doesn't affect dashboard load times.

### Cost Allocation

Track warehouse usage by team using resource monitors and tags:

```sql
-- Snowflake resource monitor: alert and suspend at spending limits
CREATE RESOURCE MONITOR marketing_budget
    WITH CREDIT_QUOTA = 500
    TRIGGERS
        ON 80 PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE marketing_warehouse
    SET RESOURCE_MONITOR = marketing_budget;
```

### Row-Level Security

When different teams or customers should see different subsets of data, use row-level security policies:

```sql
-- Only show each team their own data
CREATE ROW ACCESS POLICY team_data_policy AS (team_id INT)
RETURNS BOOLEAN ->
    team_id = CURRENT_ROLE()::INT
    OR IS_ROLE_IN_SESSION('DATA_ADMIN');
```

> **Key Takeaway:** Design your warehouse for multi-tenancy from the start. Separate workloads by compute (different warehouses), control costs with resource monitors, and enforce data access with row-level security. Retrofitting these later is painful.

---

## Case Study: Designing a Multi-Team Analytics Warehouse

A mid-sized SaaS company with three main analytics consumers: **Product** (user behavior analysis), **Marketing** (campaign attribution, funnel analysis), and **Finance** (revenue recognition, forecasting).

### Schema Design

Use a layered approach:

- **Raw layer** (`raw.*`): Direct copies of source data, minimal transformation. Owned by the data engineering team.
- **Staging layer** (`staging.*`): Cleaned and standardized data. Consistent naming, data types, and deduplication. Still resembles source structure.
- **Analytics layer** (`analytics.*`): Business-logic-enriched dimensional models. Star schemas with fact and dimension tables. This is what teams query.
- **Team layers** (`product.*`, `marketing.*`, `finance.*`): Team-specific models built on the analytics layer. Each team owns their models and can iterate independently.

```sql
-- Analytics layer: shared fact table all teams use
CREATE TABLE analytics.fact_user_activity (
    activity_id     BIGINT,
    activity_date   DATE,
    user_key        INT REFERENCES analytics.dim_users,
    activity_type   STRING,
    feature_used    STRING,
    session_id      STRING,
    duration_sec    INT,
    revenue_impact  DECIMAL(10,2)
);

-- Product team layer: their own aggregation
CREATE TABLE product.feature_adoption AS
SELECT
    feature_used,
    DATE_TRUNC('week', activity_date) AS week,
    COUNT(DISTINCT user_key) AS unique_users,
    SUM(duration_sec) / 3600.0 AS total_hours
FROM analytics.fact_user_activity
GROUP BY 1, 2;

-- Marketing team layer: their own attribution model
CREATE TABLE marketing.campaign_attribution AS
SELECT
    c.campaign_id,
    c.campaign_name,
    COUNT(DISTINCT a.user_key) AS attributed_users,
    SUM(a.revenue_impact) AS attributed_revenue
FROM analytics.fact_user_activity a
JOIN marketing.campaign_touchpoints c
    ON a.user_key = c.user_key
    AND a.activity_date BETWEEN c.start_date AND c.end_date
GROUP BY 1, 2;
```

This layered design gives each team autonomy over their models while maintaining a shared, governed foundation. The analytics layer is the "contract" — stable, well-tested, and owned by the data team.

---

## What's Next

Data warehouses are powerful but store only structured, curated data. Module 7 explores data lakes and the lakehouse architecture — how to handle raw, semi-structured, and unstructured data alongside your warehouse, and how modern lakehouse formats are blurring the line between the two.
