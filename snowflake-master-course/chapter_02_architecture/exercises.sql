-- =============================================================================
-- FILE: chapter_02_architecture/exercises.sql
-- TOPIC: Snowflake Architecture — Micro-Partitions, Caching, Query Execution
-- COURSE: Snowflake Master Course | Chapter 2
-- =============================================================================
-- Snowflake stores data in immutable compressed columnar micro-partitions
-- (~50-500 MB uncompressed). The query engine uses partition metadata to
-- prune irrelevant partitions before scanning a single byte.
-- Three cache layers exist:
--   1. Metadata cache   — instant, free, no warehouse needed
--   2. Result cache     — free, 24-hour TTL, exact query match required
--   3. Local disk cache — on SSD of warehouse nodes, cleared on resize/suspend
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   STAGING;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create a table and load sample data to observe micro-partition behaviour
-- WHY IT MATTERS: Every INSERT creates new micro-partitions. Understanding
--                 natural ordering helps you choose effective clustering keys.
-- =============================================================================

-- Create a sales events table with a natural time ordering
CREATE OR REPLACE TABLE arch_sales_events (
    event_id      NUMBER        NOT NULL,
    event_date    DATE          NOT NULL,
    region        VARCHAR(50),
    product_id    NUMBER,
    revenue       NUMBER(12, 2),
    channel       VARCHAR(30)
);

-- Insert 3 years of synthetic data across multiple regions
-- Snowflake will create several micro-partitions automatically
INSERT INTO arch_sales_events
SELECT
    SEQ4()                                                    AS event_id,
    DATEADD('day', UNIFORM(0, 1095, RANDOM(42)), '2022-01-01') AS event_date,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'North America'
        WHEN 1 THEN 'Europe'
        WHEN 2 THEN 'Asia Pacific'
        ELSE        'Latin America'
    END                                                        AS region,
    UNIFORM(1, 200, RANDOM(7))                                AS product_id,
    ROUND(UNIFORM(10, 5000, RANDOM(13))::FLOAT, 2)           AS revenue,
    CASE MOD(SEQ4(), 3)
        WHEN 0 THEN 'Online'
        WHEN 1 THEN 'In-Store'
        ELSE        'Partner'
    END                                                        AS channel
FROM TABLE(GENERATOR(ROWCOUNT => 500000));

-- Confirm row count
SELECT COUNT(*) AS total_rows FROM arch_sales_events;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Inspect SYSTEM$CLUSTERING_INFORMATION on the table
-- WHY IT MATTERS: This function reveals how well a table's data is physically
--                 sorted for a given clustering key. The depth histogram
--                 shows how many micro-partitions each value appears in.
-- =============================================================================

-- Check clustering information for event_date (natural insertion order)
SELECT PARSE_JSON(
    SYSTEM$CLUSTERING_INFORMATION('arch_sales_events', '(event_date)')
) AS clustering_info;

-- Interpret key fields:
--   "average_depth"          -> 1.0 = perfectly sorted, higher = more overlap
--   "total_partition_count"  -> total micro-partitions
--   "partition_depth_histogram" -> distribution of overlapping partitions

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Run a filtered query and observe partition pruning statistics
-- WHY IT MATTERS: partitions_scanned / partitions_total = efficiency ratio.
--                 Ideally you want a tiny fraction scanned vs total.
-- =============================================================================

-- Query a single month — Snowflake should prune most partitions
SELECT region,
       SUM(revenue)  AS total_revenue,
       COUNT(*)      AS event_count
FROM   arch_sales_events
WHERE  event_date BETWEEN '2023-06-01' AND '2023-06-30'
GROUP  BY region
ORDER  BY total_revenue DESC;

-- Now check the last query's partition statistics
SELECT query_text,
       partitions_scanned,
       partitions_total,
       ROUND(100.0 * partitions_scanned / NULLIF(partitions_total, 0), 1) AS pct_scanned,
       bytes_scanned / 1024 / 1024 AS mb_scanned
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 5))
ORDER  BY start_time DESC
LIMIT  1;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Demonstrate the result cache — run the same query twice and compare
-- WHY IT MATTERS: Result cache serves identical queries from a cached result
--                 in milliseconds with zero credit consumption.
--                 Cache key = exact SQL text + parameter context.
-- =============================================================================

-- First execution — no cache, warehouse must compute
SELECT SUM(revenue) AS total_revenue_2023
FROM   arch_sales_events
WHERE  event_date BETWEEN '2023-01-01' AND '2023-12-31';

-- Note the execution time from the query profile

-- Second execution — should hit result cache (< 10 ms, 0 credits)
SELECT SUM(revenue) AS total_revenue_2023
FROM   arch_sales_events
WHERE  event_date BETWEEN '2023-01-01' AND '2023-12-31';

-- Disable the result cache for the current session and run again
ALTER SESSION SET USE_CACHED_RESULT = FALSE;

SELECT SUM(revenue) AS total_revenue_2023
FROM   arch_sales_events
WHERE  event_date BETWEEN '2023-01-01' AND '2023-12-31';

-- Re-enable result cache
ALTER SESSION SET USE_CACHED_RESULT = TRUE;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Query QUERY_HISTORY to confirm cache hits
-- WHY IT MATTERS: The is_client_generated_statement flag and
--                 bytes_scanned = 0 are indicators of result cache hits.
-- =============================================================================

-- Look for queries where the result cache was used (bytes_scanned = 0)
SELECT query_id,
       query_text,
       start_time,
       total_elapsed_time,
       bytes_scanned,
       CASE WHEN bytes_scanned = 0 THEN 'RESULT CACHE HIT' ELSE 'COMPUTED' END AS cache_status
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 20))
WHERE  query_text ILIKE '%total_revenue_2023%'
ORDER  BY start_time DESC;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Show warehouse details including cluster node count
-- WHY IT MATTERS: Warehouse size determines the number of compute nodes.
--                 XS=1, S=2, M=4, L=8, XL=16 nodes (each node has CPU+RAM+SSD).
-- =============================================================================

SHOW WAREHOUSES;

-- Review the "size" and "max_cluster_count" columns
-- For ANALYTICS_WH you should see MAX_CLUSTER_COUNT = 3
SELECT "name"              AS warehouse,
       "size"              AS size,
       "max_cluster_count" AS max_clusters,
       "min_cluster_count" AS min_clusters,
       "auto_suspend"      AS suspend_after_seconds,
       "scaling_policy"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Observe metadata-only queries (COUNT(*) without warehouse activity)
-- WHY IT MATTERS: COUNT(*) on a table with no filters is served from partition
--                 metadata — it never reads actual data. This means 0 credits
--                 even for a table with billions of rows.
-- =============================================================================

-- Suspend the warehouse first to prove no compute is needed
ALTER WAREHOUSE DEV_WH SUSPEND;

-- This COUNT(*) should work even with a suspended warehouse
-- (Snowflake reads from metadata cache, not the warehouse)
SELECT COUNT(*) AS row_count FROM arch_sales_events;

-- Resume the warehouse for subsequent exercises
ALTER WAREHOUSE DEV_WH RESUME;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Check clustering depth to understand sort quality
-- WHY IT MATTERS: Average depth > 1 means partitions overlap on the key column,
--                 reducing pruning efficiency. Ideal is 1.0.
-- =============================================================================

-- Check depth for multiple potential clustering keys
SELECT
    'event_date'   AS candidate_key,
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('arch_sales_events','(event_date)'))['average_depth']::FLOAT
        AS avg_depth
UNION ALL
SELECT
    'region',
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('arch_sales_events','(region)'))['average_depth']::FLOAT
UNION ALL
SELECT
    'product_id',
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('arch_sales_events','(product_id)'))['average_depth']::FLOAT
ORDER BY avg_depth;

-- The column with the lowest average depth is naturally best sorted (best for pruning).

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Use EXPLAIN to inspect the query execution plan
-- WHY IT MATTERS: EXPLAIN shows you what Snowflake will do before running the query —
--                 ideal for reviewing TableScan steps, join strategies, and sort operators.
-- =============================================================================

EXPLAIN
SELECT region,
       DATE_TRUNC('month', event_date) AS month,
       SUM(revenue) AS monthly_revenue
FROM   arch_sales_events
WHERE  event_date >= '2023-01-01'
  AND  channel     = 'Online'
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- EXPLAIN USING TEXT shows the plan in readable text format
EXPLAIN USING TEXT
SELECT region,
       DATE_TRUNC('month', event_date) AS month,
       SUM(revenue) AS monthly_revenue
FROM   arch_sales_events
WHERE  event_date >= '2023-01-01'
  AND  channel     = 'Online'
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Check bytes_scanned from QUERY_HISTORY for recent queries
-- WHY IT MATTERS: bytes_scanned is a leading indicator of query cost.
--                 High bytes_scanned on a filtered query signals missing pruning.
-- =============================================================================

SELECT query_id,
       SUBSTR(query_text, 1, 60)                      AS query_snippet,
       total_elapsed_time / 1000                       AS elapsed_sec,
       bytes_scanned      / 1024 / 1024                AS mb_scanned,
       partitions_scanned,
       partitions_total,
       compilation_time   / 1000                       AS compile_sec,
       execution_time     / 1000                       AS execute_sec
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 10))
WHERE  query_type = 'SELECT'
ORDER  BY start_time DESC;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Demonstrate partition pruning with a date range filter vs full scan
-- WHY IT MATTERS: Side-by-side comparison makes the value of date-based
--                 partitioning immediately tangible.
-- =============================================================================

-- FULL SCAN — no filter; all partitions must be read
SELECT COUNT(*), SUM(revenue) FROM arch_sales_events;

-- PRUNED SCAN — narrow date range; most partitions skipped
SELECT COUNT(*), SUM(revenue)
FROM   arch_sales_events
WHERE  event_date BETWEEN '2022-01-01' AND '2022-01-07';

-- Compare partitions_scanned for both queries
SELECT query_text,
       partitions_scanned,
       partitions_total,
       ROUND(100.0 * partitions_scanned / NULLIF(partitions_total,0), 1) AS pct_scanned
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 10))
WHERE  query_text ILIKE '%arch_sales_events%'
ORDER  BY start_time DESC
LIMIT  4;

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Observe how warehouse size affects query execution time
-- WHY IT MATTERS: Larger warehouses parallelize work across more nodes.
--                 Doubling size roughly halves execution time for CPU-bound queries,
--                 but credits consumed per query stays roughly the same.
-- =============================================================================

-- Run an aggregation on XS warehouse
USE WAREHOUSE DEV_WH;   -- DEV_WH is X-SMALL

SELECT channel,
       YEAR(event_date)  AS yr,
       SUM(revenue)      AS revenue,
       AVG(revenue)      AS avg_revenue
FROM   arch_sales_events
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- Note the elapsed time, then switch to a larger warehouse and re-run
-- ALTER SESSION SET USE_CACHED_RESULT = FALSE;
-- USE WAREHOUSE ANALYTICS_WH;    -- LARGE
-- Re-run the same query and compare elapsed times

-- INSTRUCTOR NOTE: With 500k rows the difference will be small.
-- With 500M rows, the L warehouse would be ~4x faster than XS.

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Query ACCOUNT_USAGE for cloud services credit consumption
-- WHY IT MATTERS: Cloud services (metadata ops, compilation, auth) are free
--                 up to 10% of daily compute credits. Exceeding that threshold
--                 incurs additional charges.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

SELECT DATE_TRUNC('day', start_time)      AS usage_day,
       warehouse_name,
       SUM(credits_used_compute)          AS compute_credits,
       SUM(credits_used_cloud_services)   AS cloud_svc_credits,
       ROUND(100.0 * SUM(credits_used_cloud_services)
             / NULLIF(SUM(credits_used_compute), 0), 2) AS cloud_svc_pct
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP  BY 1, 2
HAVING SUM(credits_used_compute) > 0
ORDER  BY 1 DESC, 2;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Observe auto-suspend — suspend the warehouse manually and watch it resume
-- WHY IT MATTERS: Auto-resume is transparent — queries trigger it automatically.
--                 This exercise makes the mechanism visible so you trust it.
-- =============================================================================

-- Manually suspend DEV_WH
ALTER WAREHOUSE DEV_WH SUSPEND;

-- Verify it is suspended
SHOW WAREHOUSES LIKE 'DEV_WH';

-- Run a query — Snowflake will auto-resume the warehouse before executing
-- (you will see a brief delay as the warehouse boots)
SELECT CURRENT_TIMESTAMP() AS resumed_at, COUNT(*) AS row_check
FROM   arch_sales_events
LIMIT  1;

-- Check status again — should be STARTED
SHOW WAREHOUSES LIKE 'DEV_WH';

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: Query warehouse metering history to see credit burn over time
-- WHY IT MATTERS: WAREHOUSE_METERING_HISTORY is billed-to-the-second data.
--                 Plotting this reveals idle time and optimisation opportunities.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

SELECT warehouse_name,
       start_time,
       end_time,
       DATEDIFF('minute', start_time, end_time) AS active_minutes,
       credits_used_compute,
       credits_used_cloud_services,
       credits_used
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  start_time >= DATEADD('day', -1, CURRENT_TIMESTAMP())
ORDER  BY start_time DESC
LIMIT  50;

USE ROLE SYSADMIN;

-- =============================================================================
-- CLEANUP (optional — uncomment to remove test objects)
-- =============================================================================
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.arch_sales_events;

-- =============================================================================
-- END OF CHAPTER 2 EXERCISES
-- =============================================================================
