-- =============================================================================
-- Chapter 15: Snowflake Cost Optimization
-- Snowflake Master Course
-- =============================================================================
-- Covers: Credit usage, query costs, result cache, warehouse utilization,
--         resource monitors, storage costs, and performance diagnostics.
-- =============================================================================

USE ROLE    ACCOUNTADMIN;
USE DATABASE SNOWFLAKE;
USE SCHEMA   ACCOUNT_USAGE;
USE WAREHOUSE COMPUTE_WH;


-- ---------------------------------------------------------------------------
-- Exercise 1: Credit usage by warehouse – last 30 days
-- ---------------------------------------------------------------------------
SELECT
    WAREHOUSE_NAME,
    SUM(CREDITS_USED_COMPUTE)                           AS compute_credits,
    SUM(CREDITS_USED_CLOUD_SERVICES)                    AS cloud_service_credits,
    SUM(CREDITS_USED)                                   AS total_credits,
    -- Approximate cost at $3/credit (adjust for your contract rate)
    ROUND(SUM(CREDITS_USED) * 3.0, 2)                  AS approx_cost_usd
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY WAREHOUSE_NAME
ORDER BY total_credits DESC;


-- ---------------------------------------------------------------------------
-- Exercise 2: Credit usage by day – trend for the last 30 days
-- (use this as the basis for a time-series chart in BI tools)
-- ---------------------------------------------------------------------------
SELECT
    DATE_TRUNC('day', START_TIME)::DATE                 AS usage_date,
    WAREHOUSE_NAME,
    SUM(CREDITS_USED_COMPUTE)                           AS compute_credits,
    SUM(CREDITS_USED_CLOUD_SERVICES)                    AS cloud_svc_credits,
    SUM(CREDITS_USED)                                   AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY usage_date DESC, total_credits DESC;


-- ---------------------------------------------------------------------------
-- Exercise 3: Find the most expensive queries (last 7 days)
-- ---------------------------------------------------------------------------
SELECT
    QUERY_ID,
    QUERY_TEXT,
    USER_NAME,
    ROLE_NAME,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    TOTAL_ELAPSED_TIME / 1000                           AS elapsed_seconds,
    BYTES_SCANNED / 1024 / 1024 / 1024                 AS gb_scanned,
    CREDITS_USED_CLOUD_SERVICES                         AS cloud_svc_credits,
    PARTITIONS_TOTAL,
    PARTITIONS_SCANNED,
    ROUND(100.0 * PARTITIONS_SCANNED / NULLIF(PARTITIONS_TOTAL, 0), 1)
                                                        AS pct_partitions_scanned,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME      >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS = 'SUCCESS'
  AND TOTAL_ELAPSED_TIME > 0
ORDER BY TOTAL_ELAPSED_TIME DESC
LIMIT 25;


-- ---------------------------------------------------------------------------
-- Exercise 4: Calculate result cache hit rate
-- ---------------------------------------------------------------------------
SELECT
    DATE_TRUNC('day', START_TIME)::DATE                 AS query_date,
    COUNT(*)                                            AS total_queries,
    SUM(CASE WHEN IS_CLIENT_GENERATED_STATEMENT = FALSE
              AND EXECUTION_TIME = 0
             THEN 1 ELSE 0 END)                         AS result_cache_hits,
    SUM(CASE WHEN QUERY_TYPE = 'SELECT'
             THEN 1 ELSE 0 END)                         AS select_queries,
    ROUND(
        100.0 * SUM(CASE WHEN IS_CLIENT_GENERATED_STATEMENT = FALSE
                          AND EXECUTION_TIME = 0 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    )                                                   AS cache_hit_rate_pct
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND QUERY_TYPE  = 'SELECT'
GROUP BY 1
ORDER BY query_date DESC;

-- Account-level summary
SELECT
    COUNT(*)                                            AS total_select_queries,
    SUM(CASE WHEN EXECUTION_TIME = 0 THEN 1 ELSE 0 END) AS cache_hits,
    ROUND(100.0 * SUM(CASE WHEN EXECUTION_TIME = 0 THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 2)                     AS cache_hit_rate_pct
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND QUERY_TYPE  = 'SELECT';


-- ---------------------------------------------------------------------------
-- Exercise 5: Find warehouses with low utilization
-- ---------------------------------------------------------------------------
WITH warehouse_stats AS (
    SELECT
        WAREHOUSE_NAME,
        SUM(CREDITS_USED)                               AS total_credits,
        COUNT(DISTINCT DATE_TRUNC('hour', START_TIME))  AS active_hours,
        -- A warehouse metering period is one hour
        -- Total possible hours in 30 days = 720
        720                                             AS possible_hours
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY WAREHOUSE_NAME
)
SELECT
    ws.WAREHOUSE_NAME,
    ws.total_credits,
    ws.active_hours,
    ws.possible_hours,
    ROUND(100.0 * ws.active_hours / ws.possible_hours, 1)  AS utilization_pct,
    -- Query count from query_history
    qh.query_count,
    ROUND(ws.total_credits / NULLIF(qh.query_count, 0), 4) AS credits_per_query
FROM warehouse_stats ws
LEFT JOIN (
    SELECT
        WAREHOUSE_NAME,
        COUNT(*) AS query_count
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY WAREHOUSE_NAME
) qh ON ws.WAREHOUSE_NAME = qh.WAREHOUSE_NAME
ORDER BY utilization_pct ASC;


-- ---------------------------------------------------------------------------
-- Exercise 6: Create a resource monitor
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE RESOURCE MONITOR ANALYTICS_MONTHLY_MONITOR
    WITH
        CREDIT_QUOTA      = 1000        -- 1,000 credits per month
        FREQUENCY         = MONTHLY
        START_TIMESTAMP   = IMMEDIATELY
        TRIGGERS
            ON 75  PERCENT DO NOTIFY             -- email alert at 75%
            ON 90  PERCENT DO NOTIFY             -- email alert at 90%
            ON 100 PERCENT DO SUSPEND            -- suspend all warehouses at 100%
            ON 110 PERCENT DO SUSPEND_IMMEDIATE; -- hard stop at 110%

-- Verify the resource monitor was created
SHOW RESOURCE MONITORS LIKE 'ANALYTICS_MONTHLY_MONITOR';


-- ---------------------------------------------------------------------------
-- Exercise 7: Attach resource monitor to a warehouse
-- ---------------------------------------------------------------------------
ALTER WAREHOUSE TRANSFORM_WH
    SET RESOURCE_MONITOR = ANALYTICS_MONTHLY_MONITOR;

ALTER WAREHOUSE ANALYTICS_WH
    SET RESOURCE_MONITOR = ANALYTICS_MONTHLY_MONITOR;

-- Verify
SHOW WAREHOUSES LIKE 'TRANSFORM_WH';


-- ---------------------------------------------------------------------------
-- Exercise 8: Calculate storage costs by database
-- ---------------------------------------------------------------------------
SELECT
    DATABASE_NAME,
    -- Average daily storage in terabytes
    ROUND(AVG(AVERAGE_DATABASE_BYTES)  / POWER(1024, 4), 4)    AS avg_tb_database,
    ROUND(AVG(AVERAGE_FAILSAFE_BYTES)  / POWER(1024, 4), 4)    AS avg_tb_failsafe,
    ROUND(AVG(AVERAGE_STAGE_BYTES)     / POWER(1024, 4), 4)    AS avg_tb_stage,
    -- Combined
    ROUND(
        (AVG(AVERAGE_DATABASE_BYTES) + AVG(AVERAGE_FAILSAFE_BYTES) + AVG(AVERAGE_STAGE_BYTES))
        / POWER(1024, 4), 4
    )                                                            AS avg_tb_total,
    -- Monthly cost estimate: $23/TB/month (on-demand pricing – adjust to contract)
    ROUND(
        (AVG(AVERAGE_DATABASE_BYTES) + AVG(AVERAGE_FAILSAFE_BYTES) + AVG(AVERAGE_STAGE_BYTES))
        / POWER(1024, 4) * 23.0, 2
    )                                                            AS est_monthly_cost_usd
FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
WHERE USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE())
GROUP BY DATABASE_NAME
ORDER BY avg_tb_total DESC;


-- ---------------------------------------------------------------------------
-- Exercise 9: View serverless feature usage
-- ---------------------------------------------------------------------------

-- Dynamic Tables refresh credits
SELECT
    NAME,
    DATE_TRUNC('day', START_TIME)::DATE                         AS usage_date,
    SUM(CREDITS_USED)                                           AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY credits DESC
LIMIT 20;

-- Snowpipe credits
SELECT
    PIPE_NAME,
    DATE_TRUNC('day', START_TIME)::DATE                         AS usage_date,
    SUM(CREDITS_USED)                                           AS credits,
    SUM(FILES_INSERTED)                                         AS files_loaded,
    SUM(BYTES_INSERTED) / 1024 / 1024                          AS mb_loaded
FROM SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY credits DESC
LIMIT 20;

-- Task serverless credits
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    NAME                                                         AS task_name,
    SUM(CREDITS_USED)                                           AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2, 3
ORDER BY total_credits DESC;


-- ---------------------------------------------------------------------------
-- Exercise 10: Calculate projected monthly spend
-- ---------------------------------------------------------------------------
WITH daily_spend AS (
    SELECT
        DATE_TRUNC('day', START_TIME)::DATE                     AS usage_date,
        SUM(CREDITS_USED)                                       AS daily_credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY 1
),
averages AS (
    SELECT
        AVG(daily_credits)                                       AS avg_daily_credits,
        MAX(daily_credits)                                       AS peak_daily_credits,
        MIN(daily_credits)                                       AS min_daily_credits,
        STDDEV(daily_credits)                                    AS stddev_credits
    FROM daily_spend
)
SELECT
    ROUND(avg_daily_credits, 2)                                  AS avg_daily_credits,
    ROUND(avg_daily_credits * 30, 2)                             AS projected_monthly_credits,
    -- Estimated cost at $3/credit
    ROUND(avg_daily_credits * 30 * 3.0, 2)                      AS projected_monthly_cost_usd,
    -- Worst-case: peak * 30
    ROUND(peak_daily_credits * 30, 2)                            AS peak_scenario_credits,
    ROUND(peak_daily_credits * 30 * 3.0, 2)                     AS peak_scenario_cost_usd,
    -- 95th percentile scenario
    ROUND((avg_daily_credits + 2 * stddev_credits) * 30, 2)     AS p95_monthly_credits,
    ROUND((avg_daily_credits + 2 * stddev_credits) * 30 * 3.0, 2) AS p95_monthly_cost_usd
FROM averages;


-- ---------------------------------------------------------------------------
-- Exercise 11: Find queries with remote disk spilling
-- (queries that exceeded memory and spilled to remote storage → very expensive)
-- ---------------------------------------------------------------------------
SELECT
    QUERY_ID,
    LEFT(QUERY_TEXT, 150)                                        AS query_preview,
    USER_NAME,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    TOTAL_ELAPSED_TIME / 1000                                    AS elapsed_seconds,
    BYTES_SCANNED / 1024 / 1024 / 1024                          AS gb_scanned,
    BYTES_SPILLED_TO_REMOTE_STORAGE / 1024 / 1024 / 1024        AS gb_spilled_remote,
    BYTES_SPILLED_TO_LOCAL_STORAGE  / 1024 / 1024 / 1024        AS gb_spilled_local,
    -- Spill ratio: how much of the processed data overflowed?
    ROUND(
        100.0 * BYTES_SPILLED_TO_REMOTE_STORAGE
        / NULLIF(BYTES_SCANNED, 0), 2
    )                                                            AS remote_spill_pct,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND BYTES_SPILLED_TO_REMOTE_STORAGE > 0
  AND EXECUTION_STATUS = 'SUCCESS'
ORDER BY BYTES_SPILLED_TO_REMOTE_STORAGE DESC
LIMIT 20;


-- ---------------------------------------------------------------------------
-- Exercise 12: Identify poor partition pruning queries
-- ---------------------------------------------------------------------------
SELECT
    QUERY_ID,
    LEFT(QUERY_TEXT, 200)                                        AS query_preview,
    USER_NAME,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    PARTITIONS_TOTAL,
    PARTITIONS_SCANNED,
    ROUND(
        100.0 * PARTITIONS_SCANNED / NULLIF(PARTITIONS_TOTAL, 0), 1
    )                                                            AS pct_partitions_scanned,
    TOTAL_ELAPSED_TIME / 1000                                    AS elapsed_seconds,
    BYTES_SCANNED / 1024 / 1024 / 1024                          AS gb_scanned,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME           >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS      = 'SUCCESS'
  AND PARTITIONS_TOTAL      > 100      -- only meaningful for large tables
  AND PARTITIONS_SCANNED    > 0
  AND (1.0 * PARTITIONS_SCANNED / NULLIF(PARTITIONS_TOTAL, 0)) > 0.90  -- scanning > 90%
ORDER BY PARTITIONS_SCANNED DESC
LIMIT 25;
