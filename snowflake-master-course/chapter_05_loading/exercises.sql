-- =============================================================================
-- FILE: chapter_05_loading/exercises.sql
-- TOPIC: Data Loading — Stages, COPY INTO, Snowpipe, Semi-Structured Data
-- COURSE: Snowflake Master Course | Chapter 5
-- =============================================================================
-- Snowflake's loading architecture:
--   Files on cloud storage (S3/GCS/Azure or internal stage)
--   -> COPY INTO [table] (batch) or Snowpipe (continuous)
--   -> Micro-partitions written to Snowflake storage
-- This chapter exercises the full spectrum of loading patterns.
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   RAW;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create an internal stage and understand the PUT command
-- WHY IT MATTERS: Internal stages are Snowflake-managed cloud storage.
--                 PUT uploads local files into a stage from SnowSQL or Snowpark.
--                 (PUT cannot be run from the Worksheets UI — only from SnowSQL/driver)
-- =============================================================================

-- Create a named internal stage for raw CSV files
CREATE OR REPLACE STAGE stg_raw_csv
    FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    COMMENT     = 'Internal stage for raw CSV file uploads';

-- Create a stage for JSON payloads
CREATE OR REPLACE STAGE stg_raw_json
    FILE_FORMAT = (TYPE = JSON STRIP_OUTER_ARRAY = TRUE)
    COMMENT     = 'Internal stage for JSON API payloads';

-- SnowSQL PUT command (run from your local terminal, not Worksheets):
-- snowsql -a myaccount -u myuser -q "PUT file:///path/to/customers.csv @ANALYTICS_DB.RAW.stg_raw_csv AUTO_COMPRESS=TRUE;"
--
-- PUT syntax:
--   PUT file://<local_path> @<stage_name>
--       [OVERWRITE = TRUE|FALSE]
--       [AUTO_COMPRESS = TRUE|FALSE]
--       [PARALLEL = <n>]          -- parallel upload threads (default 4)
--
-- After PUT, verify files are staged:
LIST @stg_raw_csv;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: COPY INTO from CSV with common options
-- WHY IT MATTERS: COPY INTO is the primary batch loading mechanism.
--                 Understanding its options prevents load failures and data
--                 quality issues.
-- =============================================================================

-- Target table for CSV load
CREATE OR REPLACE TABLE raw_customers (
    customer_id   NUMBER,
    full_name     VARCHAR(200),
    email         VARCHAR(320),
    country_code  CHAR(2),
    signup_date   DATE,
    annual_spend  NUMBER(12, 2)
);

-- COPY INTO with explicit file format options inline (no reusable format object needed)
-- INSTRUCTOR NOTE: Replace @stg_raw_csv with your actual stage and file pattern
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT = (
    TYPE                        = CSV
    SKIP_HEADER                 = 1
    FIELD_DELIMITER             = ','
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF                     = ('NULL', 'null', '')
    DATE_FORMAT                 = 'YYYY-MM-DD'
    EMPTY_FIELD_AS_NULL         = TRUE
)
ON_ERROR = SKIP_FILE    -- skip files with errors rather than aborting the entire load
PURGE    = FALSE;       -- keep source files after load (for auditability)

-- Verify loaded row count
SELECT COUNT(*) AS loaded_rows FROM raw_customers;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: COPY INTO with column transformation
-- WHY IT MATTERS: Transformations inside COPY INTO avoid a separate INSERT/SELECT
--                 step. You can reorder columns, cast types, apply functions,
--                 and derive values from the $N positional column notation.
-- =============================================================================

CREATE OR REPLACE TABLE raw_customers_transformed (
    customer_id   NUMBER,
    full_name     VARCHAR(200),
    email_lower   VARCHAR(320),     -- force to lowercase during load
    country_code  CHAR(2),
    signup_year   NUMBER,           -- derived from signup_date
    annual_spend  NUMBER(12, 2),
    loaded_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- COPY with transformation (column mapping using positional references $1, $2, ...)
COPY INTO raw_customers_transformed (customer_id, full_name, email_lower, country_code, signup_year, annual_spend)
FROM (
    SELECT
        $1::NUMBER,             -- customer_id
        $2::VARCHAR,            -- full_name
        LOWER($3::VARCHAR),     -- email → force lowercase
        UPPER($4::CHAR(2)),     -- country_code → force uppercase
        YEAR($5::DATE),         -- extract year from signup_date
        $6::NUMBER(12,2)        -- annual_spend
    FROM @stg_raw_csv/customers/
)
FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1);

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Load JSON data with STRIP_OUTER_ARRAY
-- WHY IT MATTERS: Most REST API responses return JSON arrays [ {...}, {...} ].
--                 STRIP_OUTER_ARRAY splits the array so each element becomes
--                 a separate row in the VARIANT column.
-- =============================================================================

-- Target table: a single VARIANT column holds the raw JSON document
CREATE OR REPLACE TABLE raw_events_json (
    raw_payload   VARIANT,
    loaded_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Load JSON from stage
-- Each element of the JSON array becomes one row in raw_payload (VARIANT)
COPY INTO raw_events_json (raw_payload)
FROM  @stg_raw_json/events/
FILE_FORMAT = (
    TYPE              = JSON
    STRIP_OUTER_ARRAY = TRUE   -- critical: splits JSON array into individual rows
    STRIP_NULL_VALUES = FALSE
);

-- Query the VARIANT column using dot notation
SELECT
    raw_payload:event_id::NUMBER   AS event_id,
    raw_payload:event_type::VARCHAR AS event_type,
    raw_payload:user_id::NUMBER    AS user_id,
    raw_payload:timestamp::TIMESTAMP_NTZ AS event_ts,
    raw_payload:properties         AS properties_json
FROM raw_events_json
LIMIT 10;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Load Parquet files with MATCH_BY_COLUMN_NAME
-- WHY IT MATTERS: Parquet files embed column names in their schema.
--                 MATCH_BY_COLUMN_NAME auto-maps Parquet columns to table columns
--                 by name instead of by position — more robust to schema changes.
-- =============================================================================

CREATE OR REPLACE STAGE stg_raw_parquet
    FILE_FORMAT = (TYPE = PARQUET SNAPPY_COMPRESSION = TRUE);

CREATE OR REPLACE TABLE raw_orders (
    order_id     NUMBER,
    customer_id  NUMBER,
    order_date   DATE,
    status       VARCHAR(50),
    total_amount NUMBER(12, 2),
    currency     CHAR(3)
);

-- MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE means the column names in the Parquet
-- file are matched to the table columns regardless of case
COPY INTO raw_orders
FROM  @stg_raw_parquet/orders/
FILE_FORMAT = (
    TYPE                = PARQUET
    SNAPPY_COMPRESSION  = TRUE
)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Use VALIDATION_MODE to preview errors before loading
-- WHY IT MATTERS: VALIDATION_MODE dry-runs the COPY without writing any data.
--                 This lets you fix file issues before they cause partial loads
--                 or abort the entire batch.
-- =============================================================================

-- RETURN_ERRORS: shows all rows that would fail to load
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT      = (TYPE = CSV SKIP_HEADER = 1)
VALIDATION_MODE  = RETURN_ERRORS;

-- RETURN_n_ROWS: validates and previews the first N rows (not a full scan)
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT      = (TYPE = CSV SKIP_HEADER = 1)
VALIDATION_MODE  = RETURN_10_ROWS;

-- RETURN_ALL_ERRORS: like RETURN_ERRORS but continues after the first bad file
-- (useful when loading many files and you want a complete error report)
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT      = (TYPE = CSV SKIP_HEADER = 1)
VALIDATION_MODE  = RETURN_ALL_ERRORS;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Understand and test ON_ERROR options
-- WHY IT MATTERS: ON_ERROR controls what happens when a row fails to parse.
--                 Choosing the wrong option can silently drop data or
--                 abort an entire load due to one bad row.
-- =============================================================================

-- ON_ERROR = ABORT_STATEMENT (default): stops the entire load on first error
-- COPY INTO raw_customers ... ON_ERROR = ABORT_STATEMENT;

-- ON_ERROR = CONTINUE: skips bad rows, loads the rest
-- COPY INTO raw_customers ... ON_ERROR = CONTINUE;

-- ON_ERROR = SKIP_FILE: skips the entire file containing the error
-- COPY INTO raw_customers ... ON_ERROR = SKIP_FILE;

-- ON_ERROR = SKIP_FILE_n: skip the file if more than n errors occur
-- COPY INTO raw_customers ... ON_ERROR = SKIP_FILE_5;

-- ON_ERROR = SKIP_FILE_n%: skip the file if more than n% of rows error
-- COPY INTO raw_customers ... ON_ERROR = SKIP_FILE_0.5%;

-- Demonstrate CONTINUE with a deliberately mixed-quality file
-- (works best with a real file; shown here as documentation)
SELECT 'See ON_ERROR option comments above for full syntax reference.' AS note;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Query COPY_HISTORY to audit past load operations
-- WHY IT MATTERS: COPY_HISTORY is your load audit trail. It shows every file
--                 Snowflake has seen, whether it was loaded, skipped, or errored,
--                 and how many rows were affected.
-- =============================================================================

-- Recent COPY history for the current database (INFORMATION_SCHEMA — no latency)
SELECT file_name,
       table_name,
       last_load_time,
       status,
       row_count,
       row_parsed,
       first_error_message,
       first_error_line_number
FROM   TABLE(INFORMATION_SCHEMA.COPY_HISTORY(
               TABLE_NAME    => 'RAW_CUSTOMERS',
               START_TIME    => DATEADD('day', -7, CURRENT_TIMESTAMP())
             ))
ORDER  BY last_load_time DESC;

-- Account-wide COPY history (ACCOUNT_USAGE — ~45 min latency, 1-year retention)
USE ROLE ACCOUNTADMIN;
SELECT table_name,
       schema_name,
       file_name,
       last_load_time,
       status,
       row_count,
       error_count
FROM   SNOWFLAKE.ACCOUNT_USAGE.LOAD_HISTORY
WHERE  last_load_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER  BY last_load_time DESC
LIMIT  50;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Create a Snowpipe definition for continuous loading
-- WHY IT MATTERS: Snowpipe is serverless continuous ingestion — it auto-loads
--                 new files within ~1 minute of landing in a stage.
--                 Billed per file loaded (not per active warehouse).
-- =============================================================================

-- Snowpipe auto-ingests files from a stage into a table
-- Triggered by: cloud event notifications (SQS/SNS, GCS Pub/Sub, Azure Event Grid)
-- OR by calling the Snowpipe REST API (insertFiles endpoint)

CREATE OR REPLACE PIPE pipe_customers
    AUTO_INGEST = TRUE   -- requires cloud event notification setup on the bucket
    COMMENT     = 'Continuous ingestion pipe for customer CSV files'
AS
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1);

-- Show the pipe (note the notification_channel for SNS/Pub/Sub setup)
SHOW PIPES IN SCHEMA ANALYTICS_DB.RAW;

-- Check pipe status and queue
SELECT SYSTEM$PIPE_STATUS('pipe_customers');

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Show pipes and inspect their metadata
-- WHY IT MATTERS: In production, Snowpipes can stall silently if the cloud
--                 event notification is misconfigured. Regular SHOW PIPES
--                 checks reveal staleness or error states.
-- =============================================================================

SHOW PIPES IN DATABASE ANALYTICS_DB;

-- Query ACCOUNT_USAGE for pipe credit consumption
USE ROLE ACCOUNTADMIN;
SELECT pipe_name,
       credits_used,
       bytes_inserted,
       files_inserted,
       start_time,
       end_time
FROM   SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY
WHERE  start_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER  BY start_time DESC
LIMIT  20;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: COPY INTO with PATTERN matching for selective file loads
-- WHY IT MATTERS: Stages often contain many files. PATTERN lets you load only
--                 files matching a regex, which is critical for partitioned
--                 directories (e.g., load only January files).
-- =============================================================================

-- Load only files whose names match a date-based pattern
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1)
PATTERN     = '.*2024-01.*\.csv'    -- regex: only January 2024 CSV files
ON_ERROR    = SKIP_FILE;

-- Load only files from a specific subdirectory
COPY INTO raw_orders
FROM  @stg_raw_parquet/orders/us/   -- trailing slash = load all files in this prefix
FILE_FORMAT             = (TYPE = PARQUET)
MATCH_BY_COLUMN_NAME    = CASE_INSENSITIVE
PATTERN                 = '.*orders_.*\.snappy\.parquet';

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Load semi-structured JSON and FLATTEN nested arrays
-- WHY IT MATTERS: Real-world JSON often has nested arrays (e.g., line items
--                 in an order). FLATTEN explodes them into relational rows
--                 so you can query them with standard SQL.
-- =============================================================================

-- Assume raw_events_json is already loaded (from Exercise 4)
-- Each row has a raw_payload VARIANT with a nested "tags" array

-- Flatten the nested "tags" array — one row per tag per event
SELECT
    raw_payload:event_id::NUMBER        AS event_id,
    raw_payload:event_type::VARCHAR     AS event_type,
    f.value::VARCHAR                    AS tag
FROM   raw_events_json,
       LATERAL FLATTEN(INPUT => raw_payload:tags) f
LIMIT  20;

-- Flatten a nested "items" array (order line items)
SELECT
    raw_payload:order_id::NUMBER         AS order_id,
    item.value:product_id::NUMBER        AS product_id,
    item.value:product_name::VARCHAR     AS product_name,
    item.value:quantity::NUMBER          AS quantity,
    item.value:unit_price::NUMBER(10,2)  AS unit_price,
    item.value:quantity::NUMBER * item.value:unit_price::NUMBER AS line_total
FROM   raw_events_json,
       LATERAL FLATTEN(INPUT => raw_payload:items) item
WHERE  raw_payload:event_type::VARCHAR = 'ORDER';

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Use the PURGE option to auto-delete staged files after successful load
-- WHY IT MATTERS: PURGE = TRUE automatically removes files from the stage
--                 after a successful COPY INTO, keeping stages clean and
--                 preventing re-loading stale files.
-- =============================================================================

-- PURGE = TRUE: delete staged files after successful load
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/archive/
FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1)
PURGE       = TRUE;     -- remove files from stage after successful load

-- FORCE = TRUE: reload files even if they have been loaded before
-- (normally Snowflake tracks file metadata and skips already-loaded files)
-- Use with caution — can cause duplicate data if target table has no dedup logic!
-- COPY INTO raw_customers
-- FROM  @stg_raw_csv/customers/
-- FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1)
-- FORCE       = TRUE;

SELECT 'PURGE and FORCE options demonstrated in comments above.' AS note;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Load with an inline file format (no pre-created format object)
-- WHY IT MATTERS: Inline file formats are useful for one-off loads or when
--                 you want the COPY statement to be self-contained.
-- =============================================================================

-- Inline JSON format — everything defined in-line, no FORMAT object needed
COPY INTO raw_events_json (raw_payload)
FROM  @stg_raw_json/events/
FILE_FORMAT = (
    TYPE              = JSON
    STRIP_OUTER_ARRAY = TRUE
    DATE_FORMAT       = 'YYYY-MM-DD'
    TIMESTAMP_FORMAT  = 'YYYY-MM-DD HH24:MI:SS'
);

-- Inline TSV (tab-separated) format
CREATE OR REPLACE TABLE raw_tsv_test (col1 VARCHAR, col2 VARCHAR, col3 NUMBER);

COPY INTO raw_tsv_test
FROM  @stg_raw_csv/tsv/
FILE_FORMAT = (
    TYPE            = CSV
    FIELD_DELIMITER = '\t'   -- tab character
    SKIP_HEADER     = 1
    NULL_IF         = ('\\N', '')
);

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: Validate load results using the VALIDATE() table function
-- WHY IT MATTERS: VALIDATE() re-runs the parsing of files from a past COPY
--                 and returns detailed error information row-by-row.
--                 Essential for diagnosing why some rows were rejected.
-- =============================================================================

-- Run a COPY and capture the JOB_ID (shown in the result metadata)
COPY INTO raw_customers
FROM  @stg_raw_csv/customers/
FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1)
ON_ERROR    = CONTINUE;   -- continue past errors so we have something to validate

-- Get the last COPY query ID
SET last_copy_id = LAST_QUERY_ID();

-- VALIDATE() shows detailed error information for every rejected row
SELECT *
FROM   TABLE(VALIDATE(raw_customers, JOB_ID => $last_copy_id));

-- You can also call VALIDATE with a specific query ID string
-- SELECT * FROM TABLE(VALIDATE(raw_customers, JOB_ID => '<paste_query_id_here>'));

-- Columns returned by VALIDATE:
--   ERROR               — error description
--   FILE                — file name containing the bad row
--   LINE                — line number of the bad row
--   CHARACTER           — character position of the error
--   BYTE_OFFSET         — byte offset in the file
--   CATEGORY            — error category (e.g., conversion error)
--   COLUMN_NAME         — column that caused the error
--   ROW_NUMBER          — row number within the file
--   ROW_START_LINE      — start line of the row
--   REJECTED_RECORD     — the raw text of the rejected row

-- =============================================================================
-- END OF CHAPTER 5 EXERCISES
-- =============================================================================
