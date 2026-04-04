-- =============================================================================
-- FILE: chapter_04_objects/exercises.sql
-- TOPIC: Snowflake Object Types — Tables, Views, Stages, Streams, Tasks, Clones
-- COURSE: Snowflake Master Course | Chapter 4
-- =============================================================================
-- Snowflake has a rich object model. This chapter exercises every major object
-- type so you understand when to use each one.
-- Object hierarchy: Organization > Account > Database > Schema > Objects
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   STAGING;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create permanent, temporary, and transient tables — understand differences
-- WHY IT MATTERS:
--   PERMANENT  — full Time Travel + Fail-safe; default; suits production data
--   TEMPORARY  — session-scoped; auto-dropped at session end; no Fail-safe
--   TRANSIENT  — cross-session; no Fail-safe; lower storage cost (no 7-day Fail-safe)
-- =============================================================================

-- Permanent table: Time Travel enabled, Fail-safe enabled
CREATE OR REPLACE TABLE perm_customers (
    customer_id   NUMBER         NOT NULL PRIMARY KEY,
    full_name     VARCHAR(200)   NOT NULL,
    email         VARCHAR(320),
    country_code  CHAR(2),
    created_at    TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
)
DATA_RETENTION_TIME_IN_DAYS = 7
COMMENT = 'Permanent customer dimension — full Time Travel and Fail-safe';

-- Temporary table: only visible in this session; auto-dropped on disconnect
CREATE OR REPLACE TEMPORARY TABLE temp_session_work (
    id      NUMBER,
    value   VARCHAR(100)
)
COMMENT = 'Session-scoped scratch table — gone when session ends';

-- Transient table: cross-session but NO Fail-safe (saves storage cost)
CREATE OR REPLACE TRANSIENT TABLE trans_staging_load (
    batch_id     NUMBER,
    source_file  VARCHAR(500),
    load_ts      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    row_count    NUMBER
)
DATA_RETENTION_TIME_IN_DAYS = 1
COMMENT = 'Transient staging table for intermediate load tracking';

-- Insert rows into each
INSERT INTO perm_customers (customer_id, full_name, email, country_code)
VALUES (1, 'Alice Smith', 'alice@example.com', 'US'),
       (2, 'Bob Jones',   'bob@example.com',   'GB'),
       (3, 'Chen Wei',    'chen@example.com',  'CN');

INSERT INTO temp_session_work VALUES (1, 'temp_data');
INSERT INTO trans_staging_load (batch_id, source_file, row_count) VALUES (1001, 'customers_20240101.csv', 3);

-- Compare table types in INFORMATION_SCHEMA
SELECT table_name, table_type, is_transient, retention_time
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.TABLES
WHERE  table_name IN ('PERM_CUSTOMERS', 'TEMP_SESSION_WORK', 'TRANS_STAGING_LOAD');

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Create a standard view and a secure view
-- WHY IT MATTERS: Secure views hide the view definition from non-owners.
--                 Use them when sharing data with analysts who should not see
--                 how sensitive columns are masked or filtered.
-- =============================================================================

-- Standard view — anyone with SELECT on the view can also see the definition
CREATE OR REPLACE VIEW v_customers_public AS
SELECT customer_id,
       full_name,
       country_code
FROM   perm_customers
WHERE  country_code != 'BLOCKED';   -- internal filter logic visible to all

-- Secure view — view definition hidden from non-owners
CREATE OR REPLACE SECURE VIEW v_customers_secure AS
SELECT customer_id,
       full_name,
       country_code,
       -- Mask the email domain — logic hidden from data consumers
       LEFT(email, CHARINDEX('@', email) - 1) || '@*****.***' AS masked_email
FROM   perm_customers;

-- Confirm IS_SECURE flag
SELECT table_name, table_type, is_secure
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.VIEWS
WHERE  table_name IN ('V_CUSTOMERS_PUBLIC', 'V_CUSTOMERS_SECURE');

SELECT * FROM v_customers_secure;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Create a materialized view for pre-computed aggregates
-- WHY IT MATTERS: Materialized views are automatically maintained by Snowflake
--                 whenever base table data changes. They dramatically speed up
--                 repeated aggregation queries on large tables.
-- REQUIRES: Enterprise edition
-- =============================================================================

-- First create a suitable base table
CREATE OR REPLACE TABLE sales_transactions (
    txn_id      NUMBER,
    txn_date    DATE,
    customer_id NUMBER,
    product_id  NUMBER,
    amount      NUMBER(12,2),
    channel     VARCHAR(30)
);

INSERT INTO sales_transactions
SELECT SEQ4(),
       DATEADD('day', UNIFORM(0, 365, RANDOM()), '2023-01-01'),
       UNIFORM(1, 3, RANDOM()),
       UNIFORM(1, 50, RANDOM()),
       ROUND(UNIFORM(10, 1000, RANDOM())::FLOAT, 2),
       CASE MOD(SEQ4(), 3) WHEN 0 THEN 'Online' WHEN 1 THEN 'In-Store' ELSE 'Partner' END
FROM   TABLE(GENERATOR(ROWCOUNT => 100000));

-- Create materialized view on monthly channel aggregates
CREATE OR REPLACE MATERIALIZED VIEW mv_monthly_channel_revenue AS
SELECT DATE_TRUNC('month', txn_date) AS revenue_month,
       channel,
       COUNT(*)                       AS transaction_count,
       SUM(amount)                    AS total_revenue,
       AVG(amount)                    AS avg_order_value
FROM   sales_transactions
GROUP  BY 1, 2;

-- Query the materialized view — Snowflake serves pre-computed results
SELECT * FROM mv_monthly_channel_revenue ORDER BY revenue_month, channel;

-- Check that it exists in INFORMATION_SCHEMA
SHOW MATERIALIZED VIEWS IN SCHEMA ANALYTICS_DB.STAGING;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Create CSV and JSON file formats
-- WHY IT MATTERS: File formats are reusable objects that define parsing rules
--                 for staged files. Centralising them ensures consistent behaviour
--                 across all COPY INTO statements.
-- =============================================================================

-- CSV file format for typical pipe-delimited exports
CREATE OR REPLACE FILE FORMAT ff_csv_pipe
    TYPE                  = CSV
    FIELD_DELIMITER       = '|'
    RECORD_DELIMITER      = '\n'
    SKIP_HEADER           = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF               = ('NULL', 'null', '')
    EMPTY_FIELD_AS_NULL   = TRUE
    DATE_FORMAT           = 'YYYY-MM-DD'
    TIMESTAMP_FORMAT      = 'YYYY-MM-DD HH24:MI:SS'
    COMMENT               = 'Pipe-delimited CSV with header row';

-- Standard comma-delimited CSV
CREATE OR REPLACE FILE FORMAT ff_csv_standard
    TYPE            = CSV
    FIELD_DELIMITER = ','
    SKIP_HEADER     = 1
    NULL_IF         = ('NULL', '')
    EMPTY_FIELD_AS_NULL = TRUE;

-- JSON file format for API response payloads
CREATE OR REPLACE FILE FORMAT ff_json
    TYPE              = JSON
    STRIP_OUTER_ARRAY = TRUE    -- removes the top-level [ ] from JSON arrays
    STRIP_NULL_VALUES = FALSE   -- keep null values so we can detect missing fields
    COMMENT           = 'JSON with outer array stripped — suitable for API payloads';

-- Parquet file format
CREATE OR REPLACE FILE FORMAT ff_parquet
    TYPE                     = PARQUET
    SNAPPY_COMPRESSION       = TRUE
    BINARY_AS_TEXT           = FALSE
    COMMENT                  = 'Snappy-compressed Parquet — used for Spark/dbt exports';

SHOW FILE FORMATS IN SCHEMA ANALYTICS_DB.STAGING;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Create an internal stage and list its contents
-- WHY IT MATTERS: Stages are pointers to storage locations (internal or external).
--                 Internal stages are managed by Snowflake — no S3/GCS/Azure needed.
-- =============================================================================

-- Named internal stage (general purpose)
CREATE OR REPLACE STAGE stg_customer_uploads
    FILE_FORMAT = ff_csv_standard
    COMMENT     = 'Internal stage for customer data uploads';

-- Named internal stage with encryption setting
CREATE OR REPLACE STAGE stg_json_payloads
    FILE_FORMAT = ff_json
    COMMENT     = 'Internal stage for JSON API payloads';

-- List stages
SHOW STAGES IN SCHEMA ANALYTICS_DB.STAGING;

-- List files in a stage (will be empty until you PUT files)
LIST @stg_customer_uploads;
LIST @stg_json_payloads;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Create a sequence and use it to generate surrogate keys
-- WHY IT MATTERS: Sequences generate unique, monotonically increasing values.
--                 In Snowflake they are non-blocking (unlike identity columns),
--                 so concurrent inserts never contend on sequence lock.
-- =============================================================================

CREATE OR REPLACE SEQUENCE seq_customer_id
    START  = 1000
    INCREMENT = 1
    COMMENT = 'Surrogate key generator for the customer dimension';

-- Use the sequence directly in an INSERT
INSERT INTO perm_customers (customer_id, full_name, email, country_code)
VALUES (seq_customer_id.NEXTVAL, 'Diana Prince', 'diana@example.com', 'US'),
       (seq_customer_id.NEXTVAL, 'Ethan Hunt',   'ethan@example.com', 'US');

-- Use sequence in a SELECT to generate IDs for a CTAS
CREATE OR REPLACE TABLE seq_demo AS
SELECT seq_customer_id.NEXTVAL AS generated_id,
       UNIFORM(1, 100, RANDOM()) AS payload
FROM   TABLE(GENERATOR(ROWCOUNT => 5));

SELECT * FROM seq_demo;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Create a stream on a table to capture CDC (change data capture)
-- WHY IT MATTERS: Streams record INSERT, UPDATE, and DELETE operations against
--                 a table. They are the foundation of ELT pipelines in Snowflake
--                 — no external Kafka or Debezium needed.
-- =============================================================================

-- Create a stream on perm_customers to track changes
CREATE OR REPLACE STREAM stream_customers
    ON TABLE perm_customers
    APPEND_ONLY = FALSE   -- capture inserts AND updates/deletes
    COMMENT = 'CDC stream on perm_customers — feeds downstream staging pipeline';

-- Make a change to generate stream records
INSERT INTO perm_customers (customer_id, full_name, email, country_code)
VALUES (seq_customer_id.NEXTVAL, 'Frank Castle', 'frank@example.com', 'US');

UPDATE perm_customers SET country_code = 'CA' WHERE full_name = 'Alice Smith';
DELETE FROM perm_customers WHERE full_name = 'Bob Jones';

-- Query the stream — shows the pending changes with metadata columns
SELECT *,
       METADATA$ACTION,        -- INSERT or DELETE
       METADATA$ISUPDATE,      -- TRUE for the new row in an UPDATE pair
       METADATA$ROW_ID         -- unique row identifier for deduplication
FROM   stream_customers;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Create a basic task and a task tree (DAG)
-- WHY IT MATTERS: Tasks are Snowflake's native scheduler. They can be chained
--                 into DAGs for multi-step pipeline orchestration without
--                 Airflow, Prefect, or external schedulers.
-- =============================================================================

-- Root task: runs on a schedule (every 5 minutes)
CREATE OR REPLACE TASK task_root_log
    WAREHOUSE = DEV_WH
    SCHEDULE  = '5 MINUTE'
    COMMENT   = 'Root task: logs a heartbeat timestamp every 5 minutes'
AS
INSERT INTO trans_staging_load (batch_id, source_file, row_count)
VALUES (SEQ4(), 'heartbeat', 0);

-- Child task: runs after the root task completes (no independent schedule)
CREATE OR REPLACE TASK task_child_cleanup
    WAREHOUSE = DEV_WH
    AFTER     task_root_log
    COMMENT   = 'Child task: runs after root task; removes old heartbeat rows'
AS
DELETE FROM trans_staging_load
WHERE  source_file = 'heartbeat'
  AND  load_ts < DATEADD('hour', -1, CURRENT_TIMESTAMP());

-- Tasks are created in SUSPENDED state — resume them to activate
ALTER TASK task_child_cleanup RESUME;
ALTER TASK task_root_log RESUME;

-- Check task status
SHOW TASKS IN SCHEMA ANALYTICS_DB.STAGING;

-- Suspend tasks (to avoid unnecessary credit use during this exercise)
ALTER TASK task_root_log SUSPEND;
ALTER TASK task_child_cleanup SUSPEND;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Create a Dynamic Table
-- WHY IT MATTERS: Dynamic Tables replace complex task+stream pipelines for
--                 declarative, auto-refreshing materialised results.
--                 You define WHAT you want; Snowflake figures out WHEN and HOW.
-- =============================================================================

CREATE OR REPLACE DYNAMIC TABLE dt_customer_revenue_summary
    TARGET_LAG = '5 minutes'   -- refresh within 5 minutes of base table changes
    WAREHOUSE  = DEV_WH
    COMMENT    = 'Auto-refreshing customer revenue summary; replaces task+stream pipeline'
AS
SELECT c.customer_id,
       c.full_name,
       c.country_code,
       COUNT(t.txn_id)   AS total_transactions,
       SUM(t.amount)     AS lifetime_value,
       MAX(t.txn_date)   AS last_purchase_date
FROM   perm_customers    c
LEFT JOIN sales_transactions t ON c.customer_id = t.customer_id
GROUP  BY 1, 2, 3;

-- Query the dynamic table like any other table
SELECT * FROM dt_customer_revenue_summary ORDER BY lifetime_value DESC;

-- Check refresh status
SHOW DYNAMIC TABLES IN SCHEMA ANALYTICS_DB.STAGING;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Show all objects in the current schema
-- WHY IT MATTERS: SHOW OBJECTS gives a quick inventory of everything in a schema,
--                 useful for auditing, documentation, and cleanup.
-- =============================================================================

-- Show all object types in the current schema
SHOW OBJECTS    IN SCHEMA ANALYTICS_DB.STAGING;
SHOW TABLES     IN SCHEMA ANALYTICS_DB.STAGING;
SHOW VIEWS      IN SCHEMA ANALYTICS_DB.STAGING;
SHOW STAGES     IN SCHEMA ANALYTICS_DB.STAGING;
SHOW STREAMS    IN SCHEMA ANALYTICS_DB.STAGING;
SHOW TASKS      IN SCHEMA ANALYTICS_DB.STAGING;
SHOW SEQUENCES  IN SCHEMA ANALYTICS_DB.STAGING;

-- Query INFORMATION_SCHEMA for a combined object inventory
SELECT table_schema, table_name, table_type
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.TABLES
WHERE  table_schema = 'STAGING'
ORDER  BY table_type, table_name;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Create an external table definition (pointing to cloud storage)
-- WHY IT MATTERS: External tables let you query files on S3, GCS, or Azure
--                 directly from SQL without loading them into Snowflake storage.
-- NOTE: This requires a storage integration. The example is illustrative;
--       see chapter_05_loading for a fully working example.
-- =============================================================================

-- INSTRUCTOR NOTE: Replace 's3://your-bucket/path/' with a real S3 location
-- and create a storage integration first (requires ACCOUNTADMIN):
--
-- CREATE STORAGE INTEGRATION s3_integration
--   TYPE = EXTERNAL_STAGE
--   STORAGE_PROVIDER = 'S3'
--   ENABLED = TRUE
--   STORAGE_ALLOWED_LOCATIONS = ('s3://your-bucket/');
--
-- GRANT USAGE ON INTEGRATION s3_integration TO ROLE DATA_ENGINEER_ROLE;

-- External stage pointing to S3 (illustrative — update bucket and integration)
-- CREATE OR REPLACE STAGE ext_stg_s3_raw
--     URL               = 's3://your-bucket/raw/customers/'
--     STORAGE_INTEGRATION = s3_integration
--     FILE_FORMAT       = ff_csv_standard
--     COMMENT           = 'External stage pointing to S3 raw customer files';
--
-- External table over the stage (schema defined explicitly for CSV)
-- CREATE OR REPLACE EXTERNAL TABLE ext_customers (
--     customer_id  NUMBER     AS (VALUE:c1::NUMBER),
--     full_name    VARCHAR    AS (VALUE:c2::VARCHAR),
--     email        VARCHAR    AS (VALUE:c3::VARCHAR),
--     country_code CHAR(2)    AS (VALUE:c4::CHAR(2))
-- )
--     LOCATION     = @ext_stg_s3_raw
--     FILE_FORMAT  = ff_csv_standard
--     AUTO_REFRESH = TRUE     -- refresh metadata when new files land
--     COMMENT      = 'External table over S3 customer CSV files';

SELECT 'External table setup requires a storage integration — see comment above.' AS note;

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: ALTER TABLE — add, drop, and modify columns
-- WHY IT MATTERS: Schema evolution is constant in real projects.
--                 Snowflake ALTER TABLE is near-instant for most operations
--                 because it modifies metadata, not data.
-- =============================================================================

-- Add new columns to perm_customers
ALTER TABLE perm_customers
    ADD COLUMN phone_number  VARCHAR(20),
    ADD COLUMN is_active     BOOLEAN DEFAULT TRUE,
    ADD COLUMN loyalty_tier  VARCHAR(20) DEFAULT 'BRONZE';

-- Verify the new columns
DESCRIBE TABLE perm_customers;

-- Modify a column — widen VARCHAR (safe, never shrinks data)
ALTER TABLE perm_customers
    MODIFY COLUMN phone_number VARCHAR(30);

-- Rename a column
ALTER TABLE perm_customers
    RENAME COLUMN loyalty_tier TO loyalty_level;

-- Drop a column (irreversible without Time Travel!)
ALTER TABLE perm_customers
    DROP COLUMN phone_number;

-- View final table structure
DESCRIBE TABLE perm_customers;

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Show streams and tasks status across the schema
-- WHY IT MATTERS: In production, you need to monitor stream offset positions
--                 and task run history to detect pipeline staleness or failures.
-- =============================================================================

-- Stream status — check stale_after and bytes_latest
SHOW STREAMS IN SCHEMA ANALYTICS_DB.STAGING;
SELECT "name"        AS stream_name,
       "table_name"  AS source_table,
       "stale"       AS is_stale,
       "stale_after" AS staleness_date,
       "mode"        AS stream_mode
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- Task run history (last 10 runs per task)
SELECT name           AS task_name,
       state          AS task_state,
       scheduled_time,
       query_start_time,
       completed_time,
       return_value,
       error_message
FROM   TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
               SCHEDULED_TIME_RANGE_START => DATEADD('day', -1, CURRENT_TIMESTAMP()),
               RESULT_LIMIT               => 50
             ))
ORDER  BY scheduled_time DESC;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Clone a table — zero-copy clone
-- WHY IT MATTERS: Cloning is Snowflake's killer feature for dev/test.
--                 A clone starts as a pointer to the original micro-partitions.
--                 No data is copied until the clone diverges (copy-on-write).
--                 Cost: zero storage until you modify the clone.
-- =============================================================================

-- Clone perm_customers into a development sandbox
CREATE OR REPLACE TABLE perm_customers_dev
    CLONE perm_customers
    COMMENT = 'Zero-copy dev clone of perm_customers — safe to modify';

-- The clone is identical to the source at the moment of cloning
SELECT COUNT(*) AS source_rows FROM perm_customers;
SELECT COUNT(*) AS clone_rows  FROM perm_customers_dev;

-- Modify the clone — only changed micro-partitions incur new storage cost
UPDATE perm_customers_dev SET loyalty_level = 'GOLD' WHERE customer_id < 1003;

-- The original table is unchanged
SELECT customer_id, loyalty_level FROM perm_customers;
SELECT customer_id, loyalty_level FROM perm_customers_dev;

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: DROP and UNDROP a table
-- WHY IT MATTERS: Snowflake's DROP does not immediately delete data — it enters
--                 Time Travel. UNDROP reverses the drop within the retention window,
--                 making accidents recoverable without a backup restore.
-- =============================================================================

-- Create a table to safely drop
CREATE OR REPLACE TABLE drop_test (id NUMBER, note VARCHAR);
INSERT INTO drop_test VALUES (1, 'Important data'), (2, 'More important data');

-- Drop the table
DROP TABLE drop_test;

-- Verify it is gone from normal queries
-- SELECT * FROM drop_test;  -- would error

-- UNDROP within the Time Travel window
UNDROP TABLE drop_test;

-- Verify data is restored
SELECT * FROM drop_test;

-- Schemas and databases can also be undropped:
-- DROP SCHEMA SANDBOX;
-- UNDROP SCHEMA SANDBOX;

-- =============================================================================
-- END OF CHAPTER 4 EXERCISES
-- =============================================================================
