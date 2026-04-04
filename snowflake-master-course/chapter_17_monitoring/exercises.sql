-- =============================================================================
-- Chapter 17: Snowflake Monitoring
-- Snowflake Master Course
-- =============================================================================
-- Covers: Query history, warehouse utilization, alerts, notifications,
--         storage monitoring, user activity, replication, Snowpipe,
--         and a comprehensive 5-metric monitoring dashboard.
-- =============================================================================

USE ROLE    ACCOUNTADMIN;
USE DATABASE SNOWFLAKE;
USE SCHEMA   ACCOUNT_USAGE;
USE WAREHOUSE COMPUTE_WH;


-- ---------------------------------------------------------------------------
-- Exercise 1: Query query_history for the last 24 hours
-- ---------------------------------------------------------------------------
SELECT
    QUERY_ID,
    LEFT(QUERY_TEXT, 120)                                   AS query_preview,
    USER_NAME,
    ROLE_NAME,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    EXECUTION_STATUS,
    TOTAL_ELAPSED_TIME / 1000                               AS elapsed_seconds,
    BYTES_SCANNED / 1024 / 1024                             AS mb_scanned,
    ROWS_PRODUCED,
    COMPILATION_TIME / 1000                                 AS compile_seconds,
    EXECUTION_TIME   / 1000                                 AS execute_seconds,
    START_TIME,
    END_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
ORDER BY START_TIME DESC
LIMIT 200;


-- ---------------------------------------------------------------------------
-- Exercise 2: Long-running query identification
-- Find queries that ran longer than 5 minutes in the last 7 days
-- ---------------------------------------------------------------------------
SELECT
    QUERY_ID,
    LEFT(QUERY_TEXT, 200)                                   AS query_preview,
    USER_NAME,
    ROLE_NAME,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    TOTAL_ELAPSED_TIME / 1000 / 60                          AS elapsed_minutes,
    EXECUTION_TIME   / 1000 / 60                            AS execution_minutes,
    COMPILATION_TIME / 1000                                 AS compile_seconds,
    BYTES_SCANNED / 1024 / 1024 / 1024                      AS gb_scanned,
    PARTITIONS_SCANNED,
    PARTITIONS_TOTAL,
    ROWS_PRODUCED,
    BYTES_SPILLED_TO_REMOTE_STORAGE / 1024 / 1024           AS mb_spilled_remote,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND TOTAL_ELAPSED_TIME > (5 * 60 * 1000)   -- > 5 minutes in milliseconds
  AND EXECUTION_STATUS = 'SUCCESS'
ORDER BY TOTAL_ELAPSED_TIME DESC
LIMIT 50;


-- ---------------------------------------------------------------------------
-- Exercise 3: Failed query analysis
-- What queries are failing, who runs them, and what errors occur?
-- ---------------------------------------------------------------------------
SELECT
    DATE_TRUNC('hour', START_TIME)                          AS error_hour,
    EXECUTION_STATUS,
    ERROR_CODE,
    ERROR_MESSAGE,
    USER_NAME,
    WAREHOUSE_NAME,
    COUNT(*)                                                AS failure_count,
    LISTAGG(DISTINCT LEFT(QUERY_TEXT, 80), ' | ')
        WITHIN GROUP (ORDER BY START_TIME DESC)             AS sample_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS != 'SUCCESS'
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY failure_count DESC
LIMIT 30;

-- Most common error codes in last 30 days
SELECT
    ERROR_CODE,
    ERROR_MESSAGE,
    COUNT(*)                                                AS occurrences,
    COUNT(DISTINCT USER_NAME)                               AS affected_users
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS = 'FAIL'
  AND ERROR_CODE IS NOT NULL
GROUP BY 1, 2
ORDER BY occurrences DESC
LIMIT 20;


-- ---------------------------------------------------------------------------
-- Exercise 4: Warehouse utilization heatmap query
-- Shows average queue time by hour-of-day × day-of-week
-- ---------------------------------------------------------------------------
SELECT
    DAYNAME(START_TIME)                                     AS day_name,
    DAYOFWEEKISO(START_TIME)                                AS day_num,   -- 1=Mon, 7=Sun
    HOUR(START_TIME)                                        AS hour_of_day,
    WAREHOUSE_NAME,
    COUNT(*)                                                AS query_count,
    ROUND(AVG(TOTAL_ELAPSED_TIME) / 1000, 1)               AS avg_elapsed_sec,
    ROUND(AVG(QUEUED_OVERLOAD_TIME) / 1000, 1)             AS avg_queued_sec,
    -- Utilization signal: how much time is spent waiting vs executing?
    ROUND(
        100.0 * AVG(QUEUED_OVERLOAD_TIME)
        / NULLIF(AVG(TOTAL_ELAPSED_TIME), 0), 1
    )                                                       AS pct_time_queued
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -28, CURRENT_TIMESTAMP())  -- 4 full weeks
  AND EXECUTION_STATUS = 'SUCCESS'
  AND WAREHOUSE_NAME IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY WAREHOUSE_NAME, day_num, hour_of_day;


-- ---------------------------------------------------------------------------
-- Exercise 5: Credit burn rate vs monthly budget
-- How fast are we burning through our monthly credit allocation?
-- ---------------------------------------------------------------------------
WITH daily_credits AS (
    SELECT
        DATE_TRUNC('day', START_TIME)::DATE                 AS usage_date,
        SUM(CREDITS_USED)                                   AS daily_credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= DATE_TRUNC('month', CURRENT_DATE())
    GROUP BY 1
),
budget AS (
    SELECT 2000 AS monthly_budget_credits   -- adjust to your contract
),
running AS (
    SELECT
        usage_date,
        daily_credits,
        SUM(daily_credits) OVER (ORDER BY usage_date)       AS cumulative_credits,
        DAY(usage_date)                                     AS day_of_month,
        DAY(LAST_DAY(usage_date))                           AS days_in_month
    FROM daily_credits
)
SELECT
    r.usage_date,
    ROUND(r.daily_credits, 2)                               AS daily_credits,
    ROUND(r.cumulative_credits, 2)                          AS cumulative_credits,
    b.monthly_budget_credits,
    ROUND(100.0 * r.cumulative_credits / b.monthly_budget_credits, 1) AS pct_budget_used,
    -- Projected month-end spend based on current average burn rate
    ROUND(
        (r.cumulative_credits / r.day_of_month) * r.days_in_month, 2
    )                                                       AS projected_month_end_credits,
    -- Will we exceed budget?
    CASE WHEN (r.cumulative_credits / r.day_of_month) * r.days_in_month
              > b.monthly_budget_credits
         THEN 'OVER BUDGET'
         ELSE 'ON TRACK'
    END                                                     AS budget_status
FROM running r
CROSS JOIN budget b
ORDER BY r.usage_date DESC;


-- ---------------------------------------------------------------------------
-- Exercise 6: Create an Alert for long-running queries
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

-- First, create a notification integration (email) – see Exercise 7
-- Then define the alert condition and action.

CREATE OR REPLACE ALERT ANALYTICS.PUBLIC.LONG_QUERY_ALERT
    WAREHOUSE = COMPUTE_WH
    SCHEDULE  = '5 MINUTES'   -- check every 5 minutes
    IF (
        EXISTS (
            SELECT 1
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD('minute', -10, CURRENT_TIMESTAMP())
              AND EXECUTION_STATUS = 'SUCCESS'
              AND TOTAL_ELAPSED_TIME > (10 * 60 * 1000)  -- > 10 minutes
              AND QUERY_TYPE = 'SELECT'
        )
    )
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'ops_email_integration',
            'data-platform-alerts@example.com',
            'Snowflake Alert: Long-Running Query Detected',
            'A query running longer than 10 minutes was detected in the last 10 minutes. '
            || 'Please review SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY for details.'
        );

-- Activate the alert
ALTER ALERT ANALYTICS.PUBLIC.LONG_QUERY_ALERT RESUME;

-- Verify alert status
SHOW ALERTS LIKE 'LONG_QUERY_ALERT' IN SCHEMA ANALYTICS.PUBLIC;


-- ---------------------------------------------------------------------------
-- Exercise 7: Create an email notification integration
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE NOTIFICATION INTEGRATION ops_email_integration
    TYPE    = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = (
        'data-platform-alerts@example.com',
        'oncall-engineer@example.com'
    );

-- Grant the integration to roles that need to send notifications
GRANT USAGE ON INTEGRATION ops_email_integration TO ROLE SYSADMIN;

-- Test the integration
CALL SYSTEM$SEND_EMAIL(
    'ops_email_integration',
    'data-platform-alerts@example.com',
    'Test: Snowflake Email Integration',
    'This is a test email sent from Snowflake. Integration is working correctly.'
);


-- ---------------------------------------------------------------------------
-- Exercise 8: Storage growth monitoring query
-- ---------------------------------------------------------------------------

-- Weekly storage growth trend
WITH daily_storage AS (
    SELECT
        USAGE_DATE,
        DATABASE_NAME,
        AVG(AVERAGE_DATABASE_BYTES)  / POWER(1024, 3)       AS avg_gb_database,
        AVG(AVERAGE_FAILSAFE_BYTES)  / POWER(1024, 3)       AS avg_gb_failsafe,
        AVG(AVERAGE_STAGE_BYTES)     / POWER(1024, 3)       AS avg_gb_stage
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
    WHERE USAGE_DATE >= DATEADD('day', -90, CURRENT_DATE())
    GROUP BY 1, 2
)
SELECT
    DATABASE_NAME,
    DATE_TRUNC('week', USAGE_DATE)::DATE                    AS week_start,
    ROUND(AVG(avg_gb_database + avg_gb_failsafe + avg_gb_stage), 2) AS avg_total_gb,
    ROUND(MAX(avg_gb_database + avg_gb_failsafe + avg_gb_stage), 2) AS peak_total_gb,
    -- Week-over-week growth
    ROUND(
        AVG(avg_gb_database + avg_gb_failsafe + avg_gb_stage)
        - LAG(AVG(avg_gb_database + avg_gb_failsafe + avg_gb_stage))
          OVER (PARTITION BY DATABASE_NAME ORDER BY DATE_TRUNC('week', USAGE_DATE)),
        2
    )                                                       AS wow_growth_gb
FROM daily_storage
GROUP BY DATABASE_NAME, DATE_TRUNC('week', USAGE_DATE)
ORDER BY DATABASE_NAME, week_start DESC;


-- ---------------------------------------------------------------------------
-- Exercise 9: User activity monitoring
-- ---------------------------------------------------------------------------

-- Active users, their primary roles, and query patterns
SELECT
    USER_NAME,
    ROLE_NAME,
    WAREHOUSE_NAME,
    COUNT(*)                                                AS query_count,
    ROUND(SUM(TOTAL_ELAPSED_TIME) / 1000 / 3600, 2)        AS total_compute_hours,
    ROUND(AVG(TOTAL_ELAPSED_TIME) / 1000, 1)               AS avg_query_seconds,
    COUNT(CASE WHEN EXECUTION_STATUS != 'SUCCESS' THEN 1 END) AS failed_queries,
    MAX(START_TIME)                                         AS last_active
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY USER_NAME, ROLE_NAME, WAREHOUSE_NAME
ORDER BY query_count DESC
LIMIT 50;

-- Dormant accounts: users who haven't logged in for > 60 days
SELECT
    u.NAME                                                  AS user_name,
    u.EMAIL,
    u.DEFAULT_ROLE,
    u.HAS_MFA,
    MAX(lh.EVENT_TIMESTAMP)                                 AS last_login,
    DATEDIFF('day', MAX(lh.EVENT_TIMESTAMP), CURRENT_TIMESTAMP()) AS days_inactive
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS u
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY lh
    ON lh.USER_NAME = u.NAME
   AND lh.IS_SUCCESS = 'YES'
WHERE u.DISABLED  = FALSE
  AND u.DELETED_ON IS NULL
GROUP BY 1, 2, 3, 4
HAVING days_inactive > 60
    OR MAX(lh.EVENT_TIMESTAMP) IS NULL
ORDER BY days_inactive DESC NULLS FIRST;


-- ---------------------------------------------------------------------------
-- Exercise 10: Replication lag monitoring
-- ---------------------------------------------------------------------------

-- Monitor replication group lag (requires Business Critical or above)
SELECT
    REPLICATION_GROUP_NAME,
    PHASE_NAME,
    JOB_CREATED_TIME,
    JOB_FINISHED_TIME,
    TOTAL_SIZE / 1024 / 1024 / 1024                        AS total_gb_replicated,
    DATEDIFF('second', JOB_CREATED_TIME, JOB_FINISHED_TIME) AS duration_seconds,
    STATUS,
    ERROR_MESSAGE
FROM SNOWFLAKE.ACCOUNT_USAGE.REPLICATION_GROUP_REFRESH_HISTORY
WHERE JOB_CREATED_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY JOB_CREATED_TIME DESC
LIMIT 20;

-- Current replication lag (time since last successful sync)
SELECT
    REPLICATION_GROUP_NAME,
    MAX(JOB_FINISHED_TIME)                                  AS last_successful_sync,
    DATEDIFF(
        'minute',
        MAX(JOB_FINISHED_TIME),
        CURRENT_TIMESTAMP()
    )                                                       AS lag_minutes
FROM SNOWFLAKE.ACCOUNT_USAGE.REPLICATION_GROUP_REFRESH_HISTORY
WHERE STATUS = 'SUCCESS'
GROUP BY 1
ORDER BY lag_minutes DESC;


-- ---------------------------------------------------------------------------
-- Exercise 11: Snowpipe load history review
-- ---------------------------------------------------------------------------

-- Files loaded via Snowpipe in the last 7 days
SELECT
    PIPE_NAME,
    FILE_NAME,
    FILE_SIZE / 1024 / 1024                                AS file_mb,
    ROW_COUNT,
    ROW_PARSED,
    ERROR_COUNT,
    STATUS,
    FIRST_COMMIT_TIME,
    LAST_COMMIT_TIME,
    DATEDIFF(
        'second',
        FIRST_COMMIT_TIME,
        LAST_COMMIT_TIME
    )                                                       AS ingest_duration_seconds
FROM SNOWFLAKE.ACCOUNT_USAGE.COPY_HISTORY
WHERE LAST_COMMIT_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND PIPE_NAME IS NOT NULL
ORDER BY LAST_COMMIT_TIME DESC
LIMIT 100;

-- Snowpipe error summary
SELECT
    PIPE_NAME,
    STATUS,
    COUNT(*)                                                AS file_count,
    SUM(ERROR_COUNT)                                        AS total_errors,
    SUM(ROW_COUNT)                                          AS total_rows_attempted,
    SUM(ROW_PARSED)                                         AS total_rows_loaded
FROM SNOWFLAKE.ACCOUNT_USAGE.COPY_HISTORY
WHERE LAST_COMMIT_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND PIPE_NAME IS NOT NULL
GROUP BY PIPE_NAME, STATUS
ORDER BY total_errors DESC;


-- ---------------------------------------------------------------------------
-- Exercise 12: Complete monitoring dashboard – 5 key metrics in one block
-- ---------------------------------------------------------------------------

-- Metric 1: Credit burn rate today
WITH metric_1 AS (
    SELECT
        'CREDIT_BURN_RATE'                                  AS metric_name,
        ROUND(SUM(CREDITS_USED), 2)                         AS metric_value,
        'credits used today'                                AS unit
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= CURRENT_DATE()
),

-- Metric 2: Active queries right now (approximate via recent history)
metric_2 AS (
    SELECT
        'ACTIVE_QUERIES_LAST_5_MIN'                         AS metric_name,
        COUNT(*)                                            AS metric_value,
        'queries in last 5 minutes'                         AS unit
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME >= DATEADD('minute', -5, CURRENT_TIMESTAMP())
      AND EXECUTION_STATUS = 'SUCCESS'
),

-- Metric 3: Failed queries today
metric_3 AS (
    SELECT
        'FAILED_QUERIES_TODAY'                              AS metric_name,
        COUNT(*)                                            AS metric_value,
        'failed queries today'                              AS unit
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME       >= CURRENT_DATE()
      AND EXECUTION_STATUS  = 'FAIL'
),

-- Metric 4: Storage used (latest)
metric_4 AS (
    SELECT
        'TOTAL_STORAGE_GB'                                  AS metric_name,
        ROUND(
            SUM(AVERAGE_DATABASE_BYTES + AVERAGE_FAILSAFE_BYTES + AVERAGE_STAGE_BYTES)
            / POWER(1024, 3), 2
        )                                                   AS metric_value,
        'GB total storage'                                  AS unit
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
    WHERE USAGE_DATE = (
        SELECT MAX(USAGE_DATE) FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
    )
),

-- Metric 5: Users active in the last hour
metric_5 AS (
    SELECT
        'ACTIVE_USERS_LAST_HOUR'                            AS metric_name,
        COUNT(DISTINCT USER_NAME)                           AS metric_value,
        'distinct users active in last hour'                AS unit
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE START_TIME >= DATEADD('hour', -1, CURRENT_TIMESTAMP())
)

-- Combined dashboard query
SELECT metric_name, metric_value, unit FROM metric_1
UNION ALL
SELECT metric_name, metric_value, unit FROM metric_2
UNION ALL
SELECT metric_name, metric_value, unit FROM metric_3
UNION ALL
SELECT metric_name, metric_value, unit FROM metric_4
UNION ALL
SELECT metric_name, metric_value, unit FROM metric_5
ORDER BY metric_name;
