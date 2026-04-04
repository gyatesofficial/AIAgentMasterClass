-- =============================================================================
-- FILE: chapter_07_warehouses/exercises.sql
-- TOPIC: Warehouse Management — Sizing, Clustering, Query Acceleration, Tuning
-- COURSE: Snowflake Master Course | Chapter 7
-- =============================================================================
-- This chapter covers everything you need to right-size warehouses, interpret
-- performance metrics, cluster tables for pruning, and use advanced Snowflake
-- features like Query Acceleration Service (QAS) to handle data skew.
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   STAGING;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create warehouses with different sizes and configurations
-- WHY IT MATTERS: Choosing the right warehouse size is the single biggest lever
--                 for both performance and cost. This exercise sets up warehouses
--                 with intentionally different configs so you can compare them.
-- =============================================================================

-- Extra-Small: for lightweight ad-hoc queries and development
CREATE WAREHOUSE IF NOT EXISTS PERF_TEST_XS
    WAREHOUSE_SIZE      = 'X-SMALL'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'Performance test — X-Small, 1 node';

-- Medium: for typical transformation workloads
CREATE WAREHOUSE IF NOT EXISTS PERF_TEST_M
    WAREHOUSE_SIZE      = 'MEDIUM'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'Performance test — Medium, 4 nodes';

-- Large: for heavy analytical queries
CREATE WAREHOUSE IF NOT EXISTS PERF_TEST_L
    WAREHOUSE_SIZE      = 'LARGE'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'Performance test — Large, 8 nodes';

SHOW WAREHOUSES LIKE 'PERF_TEST%';

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Alter warehouse size and observe credit consumption change
-- WHY IT MATTERS: Resizing is near-instant. Credits are billed per second at
--                 the CURRENT size. Resizing mid-query takes effect after the
--                 current query completes. Know when to resize up vs scale out.
-- =============================================================================

-- Check current size and credit rate
SHOW WAREHOUSES LIKE 'DEV_WH';

-- Resize up for a heavy workload
ALTER WAREHOUSE DEV_WH SET WAREHOUSE_SIZE = 'MEDIUM';

-- Run your heavy query here...
SELECT region, SUM(revenue) AS total
FROM   staging.daily_sales
GROUP  BY 1;

-- Resize back down after heavy work is done
ALTER WAREHOUSE DEV_WH SET WAREHOUSE_SIZE = 'X-SMALL';

-- Note: resizing does NOT reset the result cache — cached results survive a resize

-- Adjust auto-suspend to reduce idle cost
ALTER WAREHOUSE DEV_WH SET AUTO_SUSPEND = 60;   -- 60 seconds

SHOW WAREHOUSES LIKE 'DEV_WH';

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Check warehouse status, active queries, and history
-- WHY IT MATTERS: Before suspending or resizing a warehouse, confirm no queries
--                 are actively running. SHOW WAREHOUSES gives real-time state.
-- =============================================================================

-- Real-time warehouse state
SHOW WAREHOUSES;

-- Active queries running on a specific warehouse (INFORMATION_SCHEMA — no latency)
SELECT query_id,
       query_text,
       user_name,
       role_name,
       execution_status,
       total_elapsed_time / 1000 AS elapsed_sec
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
               RESULT_LIMIT => 10
             ))
WHERE  warehouse_name = 'DEV_WH'
  AND  execution_status = 'RUNNING'
ORDER  BY start_time DESC;

-- Historical warehouse events (suspend, resume, resize)
USE ROLE ACCOUNTADMIN;
SELECT warehouse_name,
       event_name,          -- STARTED, SUSPENDED, RESIZED
       event_reason,        -- AUTO_SCHEDULED, USER_ISSUED
       event_state,
       timestamp
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY
WHERE  warehouse_name = 'DEV_WH'
  AND  timestamp >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER  BY timestamp DESC;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Query warehouse_metering_history for cost attribution
-- WHY IT MATTERS: Metering history provides billing-accuracy data per warehouse
--                 per hour. Use it to build cost allocation dashboards by team,
--                 project, or workload type.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Daily credit consumption by warehouse for the last 30 days
SELECT warehouse_name,
       DATE_TRUNC('day', start_time)        AS usage_day,
       SUM(credits_used)                    AS total_credits,
       SUM(credits_used_compute)            AS compute_credits,
       SUM(credits_used_cloud_services)     AS cloud_svc_credits,
       COUNT(DISTINCT DATE_TRUNC('hour', start_time)) AS active_hours
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP  BY 1, 2
ORDER  BY usage_day DESC, total_credits DESC;

-- Identify idle warehouse cost (credits consumed with no user queries)
-- NOTE: Cloud services credits still accumulate even for idle warehouses
SELECT warehouse_name,
       SUM(credits_used_cloud_services) AS idle_cloud_svc_credits
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  credits_used_compute = 0     -- no compute = idle warehouse
GROUP  BY 1
ORDER  BY 2 DESC;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Identify queries that spilled to disk (local or remote spill)
-- WHY IT MATTERS: Disk spilling occurs when a query exceeds the warehouse's
--                 available memory. Remote spill (to cloud storage) is very slow.
--                 Spilling is a signal to increase warehouse size.
-- =============================================================================

-- Find queries with significant disk spill in the last 24 hours
SELECT query_id,
       query_text,
       warehouse_name,
       total_elapsed_time / 1000                               AS elapsed_sec,
       bytes_spilled_to_local_storage  / 1024 / 1024          AS local_spill_mb,
       bytes_spilled_to_remote_storage / 1024 / 1024          AS remote_spill_mb,
       bytes_scanned / 1024 / 1024                            AS scanned_mb
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
               DATERANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
               RESULT_LIMIT    => 100
             ))
WHERE  bytes_spilled_to_remote_storage > 0
   OR  bytes_spilled_to_local_storage  > 0
ORDER  BY remote_spill_mb DESC NULLS LAST, local_spill_mb DESC NULLS LAST
LIMIT  20;

-- Spill in ACCOUNT_USAGE (longer history, ~45 min latency)
USE ROLE ACCOUNTADMIN;
SELECT query_id,
       warehouse_name,
       total_elapsed_time / 1000                               AS elapsed_sec,
       bytes_spilled_to_local_storage  / 1024 / 1024          AS local_spill_mb,
       bytes_spilled_to_remote_storage / 1024 / 1024          AS remote_spill_mb
FROM   SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE  start_time  >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  (bytes_spilled_to_local_storage > 0 OR bytes_spilled_to_remote_storage > 0)
ORDER  BY remote_spill_mb DESC NULLS LAST
LIMIT  20;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Check partition pruning efficiency for a query
-- WHY IT MATTERS: If partitions_scanned / partitions_total is close to 1.0,
--                 the warehouse is doing a full scan — clustering can help.
-- =============================================================================

-- First run a query without a clustering key
SELECT COUNT(*), SUM(revenue)
FROM   staging.daily_sales
WHERE  sale_date BETWEEN '2023-06-01' AND '2023-06-30'
  AND  region = 'Americas';

-- Check pruning efficiency for that query
SELECT query_text,
       partitions_scanned,
       partitions_total,
       ROUND(100.0 * partitions_scanned / NULLIF(partitions_total,0), 1) AS pct_scanned,
       bytes_scanned / 1024 / 1024 AS mb_scanned,
       total_elapsed_time / 1000  AS elapsed_sec
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 5))
WHERE  query_text ILIKE '%daily_sales%'
ORDER  BY start_time DESC
LIMIT  1;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Add a clustering key to a table
-- WHY IT MATTERS: Clustering keys physically sort micro-partitions by a column.
--                 Queries that filter on that column prune far more partitions.
--                 BEST for: large tables (>1 TB), with frequent range filters.
-- =============================================================================

-- Check clustering depth BEFORE adding a key
SELECT PARSE_JSON(
    SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales', '(sale_date)')
) AS before_clustering;

-- Add a clustering key on sale_date (most frequent filter column)
-- NOTE: On a large table, this triggers a background reclustering job
ALTER TABLE staging.daily_sales
    CLUSTER BY (sale_date);

-- You can also cluster on multiple columns
-- ALTER TABLE staging.daily_sales CLUSTER BY (sale_date, region);

-- Check that the clustering key was applied
SHOW TABLES LIKE 'DAILY_SALES' IN SCHEMA ANALYTICS_DB.STAGING;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Check SYSTEM$CLUSTERING_INFORMATION before and after clustering
-- WHY IT MATTERS: This function quantifies the quality of physical sort order.
--                 Lower average_depth = better pruning = faster queries = lower cost.
-- =============================================================================

-- Full clustering information object
SELECT PARSE_JSON(
    SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales')
) AS clustering_info;

-- Extract specific metrics from the JSON
SELECT
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales'))['average_depth']::FLOAT
        AS average_depth,
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales'))['average_overlaps']::FLOAT
        AS average_overlaps,
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales'))['total_partition_count']::NUMBER
        AS total_partitions,
    PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('staging.daily_sales'))['total_constant_partition_count']::NUMBER
        AS constant_partitions;

-- After clustering, run the same filtered query and check pruning again
ALTER SESSION SET USE_CACHED_RESULT = FALSE;

SELECT COUNT(*), SUM(revenue)
FROM   staging.daily_sales
WHERE  sale_date BETWEEN '2023-06-01' AND '2023-06-30'
  AND  region = 'Americas';

ALTER SESSION SET USE_CACHED_RESULT = TRUE;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Enable Query Acceleration Service (QAS)
-- WHY IT MATTERS: QAS offloads portions of a query to serverless compute,
--                 automatically handling data skew and large scans without
--                 requiring you to resize the warehouse.
--                 Best for: long-tail queries, ad-hoc analytics.
-- REQUIRES: Enterprise edition
-- =============================================================================

-- Enable QAS on a warehouse with a scale factor cap
ALTER WAREHOUSE ANALYTICS_WH
    SET ENABLE_QUERY_ACCELERATION = TRUE
        QUERY_ACCELERATION_MAX_SCALE_FACTOR = 8;  -- up to 8x the warehouse's normal compute

-- Verify QAS is enabled
SHOW WAREHOUSES LIKE 'ANALYTICS_WH';

-- Check which queries benefited from QAS (ACCOUNT_USAGE — ~45 min latency)
USE ROLE ACCOUNTADMIN;
SELECT query_id,
       query_text,
       total_elapsed_time / 1000 AS elapsed_sec,
       query_acceleration_bytes_scanned / 1024 / 1024 AS qas_mb_scanned,
       query_acceleration_partitions_scanned          AS qas_partitions_scanned
FROM   SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE  start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  query_acceleration_bytes_scanned > 0
ORDER  BY qas_mb_scanned DESC
LIMIT  20;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Query QUERY_HISTORY for long-running queries and optimization targets
-- WHY IT MATTERS: Long queries are usually caused by: missing pruning, spilling,
--                 bad join order, or missing clustering. Identifying them is
--                 the first step to optimization.
-- =============================================================================

-- Top 10 longest queries in the last 7 days
USE ROLE ACCOUNTADMIN;
SELECT query_id,
       SUBSTR(query_text, 1, 80)                AS query_snippet,
       user_name,
       warehouse_name,
       total_elapsed_time / 1000                AS elapsed_sec,
       execution_time     / 1000                AS execution_sec,
       compilation_time   / 1000                AS compile_sec,
       bytes_scanned / 1024 / 1024 / 1024       AS gb_scanned,
       partitions_scanned,
       partitions_total,
       bytes_spilled_to_remote_storage / 1024 / 1024 AS remote_spill_mb
FROM   SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE  start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  execution_status = 'SUCCESS'
ORDER  BY total_elapsed_time DESC
LIMIT  10;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Set AUTO_SUSPEND to different values and understand the tradeoff
-- WHY IT MATTERS: Auto-suspend controls the balance between responsiveness
--                 and idle cost. Very short suspend times save credits but
--                 increase cold-start latency for the next query.
-- =============================================================================

-- Interactive/development warehouse: suspend quickly (1 min idle)
ALTER WAREHOUSE DEV_WH SET AUTO_SUSPEND = 60;

-- Shared analytics warehouse: give it more warmup time (5 min idle)
-- Reduces cold-start restarts for concurrent users
ALTER WAREHOUSE ANALYTICS_WH SET AUTO_SUSPEND = 300;

-- Reporting warehouse attached to a BI tool: suspend after dashboard session
-- BI tools typically refresh every few minutes; 3-min suspend avoids restarts
ALTER WAREHOUSE REPORTING_WH SET AUTO_SUSPEND = 180;

-- Batch/pipeline warehouse: suspend immediately after each task run
-- Tasks auto-resume the warehouse; no need to keep it warm between runs
ALTER WAREHOUSE TRANSFORM_WH SET AUTO_SUSPEND = 60;

-- View the updated settings
SHOW WAREHOUSES;

-- Rule of thumb:
--   Interactive / human-driven workloads: 60-300 seconds
--   Automated / scheduled workloads:      60 seconds (tasks handle resume)
--   BI tools with frequent refreshes:     120-300 seconds

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Create a multi-cluster warehouse and understand scaling policies
-- WHY IT MATTERS: Multi-cluster warehouses scale OUT (add nodes) under concurrency,
--                 not UP (bigger nodes). They are the solution to the "many small
--                 concurrent queries" problem — BI tool dashboards, analyst teams.
-- REQUIRES: Enterprise edition
-- =============================================================================

-- Multi-cluster warehouse for concurrent analyst workloads
CREATE WAREHOUSE IF NOT EXISTS MC_ANALYTICS_WH
    WAREHOUSE_SIZE      = 'MEDIUM'
    MIN_CLUSTER_COUNT   = 1        -- always keep at least 1 cluster warm
    MAX_CLUSTER_COUNT   = 4        -- scale to 4 clusters under heavy concurrency
    SCALING_POLICY      = 'ECONOMY'  -- ECONOMY: waits for queue buildup before adding cluster
                                     -- STANDARD: adds cluster immediately on any queuing
    AUTO_SUSPEND        = 300
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'Multi-cluster warehouse for concurrent analyst queries';

-- Scaling policies:
--   STANDARD  — adds a cluster as soon as any query starts queuing
--               Best for: latency-sensitive, interactive workloads
--   ECONOMY   — waits to see sustained queue buildup before adding a cluster
--               Best for: batch workloads where a few seconds of delay is fine

SHOW WAREHOUSES LIKE 'MC_ANALYTICS_WH';

-- Monitor cluster activity (Enterprise+ feature)
USE ROLE ACCOUNTADMIN;
SELECT start_time,
       end_time,
       warehouse_name,
       cluster_number,
       credits_used_compute
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  warehouse_name = 'MC_ANALYTICS_WH'
ORDER  BY start_time DESC
LIMIT  20;
USE ROLE SYSADMIN;

-- =============================================================================
-- CLEANUP
-- =============================================================================
-- DROP WAREHOUSE IF EXISTS PERF_TEST_XS;
-- DROP WAREHOUSE IF EXISTS PERF_TEST_M;
-- DROP WAREHOUSE IF EXISTS PERF_TEST_L;
-- DROP WAREHOUSE IF EXISTS MC_ANALYTICS_WH;

-- =============================================================================
-- END OF CHAPTER 7 EXERCISES
-- =============================================================================
