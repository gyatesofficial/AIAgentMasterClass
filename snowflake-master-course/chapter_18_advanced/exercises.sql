-- =============================================================================
-- Chapter 18: Advanced Snowflake Patterns
-- Snowflake Master Course
-- =============================================================================
-- Covers: Medallion architecture, Dynamic Tables, Iceberg Tables,
--         Hybrid Tables, Data Vault, CLONE, Replication, Naming conventions,
--         and combined performance techniques.
-- =============================================================================

USE ROLE    SYSADMIN;
USE DATABASE ANALYTICS;
USE WAREHOUSE COMPUTE_WH;


-- ---------------------------------------------------------------------------
-- Exercise 1: Implement Bronze / Silver / Gold schema setup (Medallion)
-- ---------------------------------------------------------------------------
-- Bronze: raw as-landed (immutable append-only)
-- Silver: cleaned, typed, deduplicated
-- Gold:   aggregated, business-ready

CREATE SCHEMA IF NOT EXISTS ANALYTICS.BRONZE
    COMMENT = 'Medallion Bronze: raw as-landed data. Append-only, never modified.';

CREATE SCHEMA IF NOT EXISTS ANALYTICS.SILVER
    COMMENT = 'Medallion Silver: cleaned, typed, deduplicated. One-to-one with source entities.';

CREATE SCHEMA IF NOT EXISTS ANALYTICS.GOLD
    COMMENT = 'Medallion Gold: aggregated, business-ready tables for BI and ML.';

-- Bronze raw events table (semi-structured – keep full payload)
CREATE TABLE IF NOT EXISTS ANALYTICS.BRONZE.RAW_EVENTS (
    EVENT_ID        VARCHAR(100),
    RAW_PAYLOAD     VARIANT          NOT NULL,
    SOURCE_SYSTEM   VARCHAR(50),
    _LOADED_AT      TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _FILE_NAME      VARCHAR(500)
)
DATA_RETENTION_TIME_IN_DAYS = 7
COMMENT = 'Raw clickstream and application events. Append-only.';

-- Silver cleaned orders
CREATE TABLE IF NOT EXISTS ANALYTICS.SILVER.ORDERS (
    ORDER_ID        VARCHAR(50)      NOT NULL,
    CUSTOMER_ID     VARCHAR(50)      NOT NULL,
    PRODUCT_ID      VARCHAR(50),
    ORDER_DATE      DATE             NOT NULL,
    AMOUNT          DECIMAL(12, 2)   NOT NULL,
    STATUS          VARCHAR(20)      NOT NULL,
    REGION          VARCHAR(50),
    _BRONZE_LOADED  TIMESTAMP_NTZ,
    _SILVER_LOADED  TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_silver_orders PRIMARY KEY (ORDER_ID)
)
CLUSTER BY (ORDER_DATE, REGION)
COMMENT = 'Silver orders: typed, deduped, validated.';


-- ---------------------------------------------------------------------------
-- Exercise 2: Create Dynamic Tables for the medallion pipeline
-- ---------------------------------------------------------------------------

-- Silver Dynamic Table: auto-refreshes from Bronze within the target lag
CREATE OR REPLACE DYNAMIC TABLE ANALYTICS.SILVER.ORDERS_DT
    TARGET_LAG = '5 minutes'
    WAREHOUSE  = TRANSFORM_WH
    COMMENT    = 'Silver orders: cleaned and deduplicated via Dynamic Table from Bronze.'
AS
SELECT DISTINCT
    RAW_PAYLOAD['order_id']::VARCHAR(50)                    AS ORDER_ID,
    RAW_PAYLOAD['customer_id']::VARCHAR(50)                 AS CUSTOMER_ID,
    RAW_PAYLOAD['product_id']::VARCHAR(50)                  AS PRODUCT_ID,
    TRY_TO_DATE(RAW_PAYLOAD['order_date']::STRING)          AS ORDER_DATE,
    TRY_TO_DECIMAL(RAW_PAYLOAD['amount']::STRING, 12, 2)    AS AMOUNT,
    UPPER(TRIM(RAW_PAYLOAD['status']::STRING))               AS STATUS,
    COALESCE(UPPER(TRIM(RAW_PAYLOAD['region']::STRING)), 'UNKNOWN') AS REGION,
    _LOADED_AT                                              AS _BRONZE_LOADED
FROM ANALYTICS.BRONZE.RAW_EVENTS
WHERE SOURCE_SYSTEM = 'ORDER_SERVICE'
  AND RAW_PAYLOAD['order_id'] IS NOT NULL
  AND TRY_TO_DECIMAL(RAW_PAYLOAD['amount']::STRING, 12, 2) > 0
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY RAW_PAYLOAD['order_id']::VARCHAR
    ORDER BY _LOADED_AT DESC
) = 1;

-- Gold Dynamic Table: revenue aggregation, auto-refreshes from Silver
CREATE OR REPLACE DYNAMIC TABLE ANALYTICS.GOLD.DAILY_REVENUE_DT
    TARGET_LAG = '15 minutes'
    WAREHOUSE  = TRANSFORM_WH
    COMMENT    = 'Gold daily revenue: aggregated from Silver.ORDERS_DT.'
AS
SELECT
    ORDER_DATE,
    REGION,
    STATUS,
    COUNT(*)                                                AS order_count,
    SUM(AMOUNT)                                             AS total_revenue,
    AVG(AMOUNT)                                             AS avg_order_value,
    MIN(AMOUNT)                                             AS min_order_value,
    MAX(AMOUNT)                                             AS max_order_value
FROM ANALYTICS.SILVER.ORDERS_DT
GROUP BY ORDER_DATE, REGION, STATUS;

-- Monitor Dynamic Table refresh lag
SELECT
    NAME,
    TARGET_LAG,
    STATE,
    LAST_COMPLETED_DEPENDENCY_UPDATE_TIME,
    DATEDIFF('minute',
        LAST_COMPLETED_DEPENDENCY_UPDATE_TIME,
        CURRENT_TIMESTAMP()
    )                                                       AS current_lag_minutes
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE TABLE_SCHEMA IN ('SILVER', 'GOLD')
ORDER BY current_lag_minutes DESC;


-- ---------------------------------------------------------------------------
-- Exercise 3: Create an Iceberg Table (external volume required)
-- ---------------------------------------------------------------------------
-- Prerequisites:
--   1. Create an S3/ADLS/GCS external volume (requires ACCOUNTADMIN)
--   2. Create a catalog integration (for Iceberg catalog like AWS Glue)
-- The below is syntax-complete but requires your external volume name.

/*
-- Step 1: Create external volume (run as ACCOUNTADMIN)
CREATE EXTERNAL VOLUME IF NOT EXISTS my_iceberg_volume
    STORAGE_LOCATIONS = (
        (
            NAME          = 'my-s3-bucket-us-east-1',
            STORAGE_PROVIDER = 'S3',
            STORAGE_BASE_URL = 's3://my-data-lake-bucket/iceberg/',
            STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-iceberg-role'
        )
    );

-- Step 2: Create Iceberg table (Snowflake as catalog)
CREATE ICEBERG TABLE IF NOT EXISTS ANALYTICS.SILVER.ORDERS_ICEBERG (
    ORDER_ID        VARCHAR(50)     NOT NULL,
    CUSTOMER_ID     VARCHAR(50)     NOT NULL,
    ORDER_DATE      DATE            NOT NULL,
    AMOUNT          DECIMAL(12, 2)  NOT NULL,
    STATUS          VARCHAR(20)     NOT NULL,
    REGION          VARCHAR(50)
)
    CATALOG        = 'SNOWFLAKE'         -- Snowflake manages the Iceberg catalog
    EXTERNAL_VOLUME = 'my_iceberg_volume'
    BASE_LOCATION  = 'silver/orders/'   -- Relative path within the volume
    CLUSTER BY     (ORDER_DATE)
    COMMENT        = 'Iceberg table: orders with open table format for cross-engine access.';

-- Insert into Iceberg table (same syntax as regular tables)
INSERT INTO ANALYTICS.SILVER.ORDERS_ICEBERG
SELECT ORDER_ID, CUSTOMER_ID, ORDER_DATE, AMOUNT, STATUS, REGION
FROM ANALYTICS.SILVER.ORDERS
WHERE ORDER_DATE >= '2024-01-01';
*/

-- Note: Uncomment and adjust the above once your external volume is configured.
SELECT 'Exercise 3: Iceberg table creation requires an external volume. See commented code above.' AS note;


-- ---------------------------------------------------------------------------
-- Exercise 4: Create a Hybrid Table with primary + secondary index
-- ---------------------------------------------------------------------------
-- Hybrid Tables are optimized for row-level operational workloads (OLTP-like)
-- while still allowing analytical queries.

CREATE HYBRID TABLE IF NOT EXISTS ANALYTICS.PUBLIC.CUSTOMER_SESSIONS (
    SESSION_ID      VARCHAR(100)    NOT NULL,
    CUSTOMER_ID     VARCHAR(50)     NOT NULL,
    SESSION_START   TIMESTAMP_NTZ   NOT NULL,
    SESSION_END     TIMESTAMP_NTZ,
    PAGE_VIEWS      INTEGER         NOT NULL DEFAULT 0,
    EVENTS_COUNT    INTEGER         NOT NULL DEFAULT 0,
    DEVICE_TYPE     VARCHAR(30),
    IP_ADDRESS      VARCHAR(45),
    IS_CONVERTED    BOOLEAN         NOT NULL DEFAULT FALSE,
    -- Primary key is required on Hybrid Tables
    PRIMARY KEY (SESSION_ID),
    -- Secondary index for customer lookup queries (point lookups)
    INDEX idx_customer (CUSTOMER_ID),
    -- Secondary index for time-range queries
    INDEX idx_session_start (SESSION_START)
)
COMMENT = 'Hybrid Table for real-time session tracking with point-lookup performance.';

-- Point lookup (takes advantage of the primary key index)
SELECT * FROM ANALYTICS.PUBLIC.CUSTOMER_SESSIONS
WHERE SESSION_ID = 'sess_abc123xyz';

-- Customer session history (uses idx_customer secondary index)
SELECT * FROM ANALYTICS.PUBLIC.CUSTOMER_SESSIONS
WHERE CUSTOMER_ID = 'CUST_001'
  AND SESSION_START >= DATEADD('day', -30, CURRENT_TIMESTAMP())
ORDER BY SESSION_START DESC;


-- ---------------------------------------------------------------------------
-- Exercise 5: Multi-table INSERT fan-out
-- ---------------------------------------------------------------------------
-- Route rows from a staging table into multiple destination tables
-- in a single DML statement (one pass over the source).

INSERT ALL
    WHEN STATUS = 'COMPLETED' THEN
        INTO ANALYTICS.MARTS.ORDERS_COMPLETED (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, REGION)
        VALUES (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, REGION)

    WHEN STATUS = 'CANCELLED' THEN
        INTO ANALYTICS.MARTS.ORDERS_CANCELLED (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, CANCELLED_AT)
        VALUES (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, CURRENT_TIMESTAMP())

    WHEN STATUS = 'REFUNDED' THEN
        INTO ANALYTICS.MARTS.ORDERS_REFUNDED (ORDER_ID, CUSTOMER_ID, REFUND_AMOUNT, REFUND_DATE)
        VALUES (ORDER_ID, CUSTOMER_ID, AMOUNT, CURRENT_DATE())

    WHEN STATUS = 'PENDING' AND DATEDIFF('day', ORDER_DATE, CURRENT_DATE()) > 7 THEN
        INTO ANALYTICS.MARTS.ORDERS_STALE_PENDING (ORDER_ID, CUSTOMER_ID, ORDER_DATE, DAYS_PENDING)
        VALUES (ORDER_ID, CUSTOMER_ID, ORDER_DATE, DATEDIFF('day', ORDER_DATE, CURRENT_DATE()))

    -- Catch-all: write every row to the unified mart regardless of status
    WHEN 1 = 1 THEN
        INTO ANALYTICS.MARTS.FCT_ORDERS_UNIFIED (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, STATUS, REGION)
        VALUES (ORDER_ID, CUSTOMER_ID, AMOUNT, ORDER_DATE, STATUS, REGION)

SELECT
    ORDER_ID, CUSTOMER_ID, PRODUCT_ID, AMOUNT, ORDER_DATE, STATUS, REGION
FROM ANALYTICS.RAW.ORDERS_LANDING
WHERE _PROCESSED = FALSE;


-- ---------------------------------------------------------------------------
-- Exercise 6: Optimized MERGE with pre-filtering
-- ---------------------------------------------------------------------------
-- Pre-filter the source CTE to only rows that changed – reduces the
-- number of rows compared during the MERGE and prevents full-table scans.

MERGE INTO ANALYTICS.MARTS.DIM_CUSTOMERS AS target
USING (
    -- Pre-filter: only new or changed customers from the staging area
    SELECT
        s.CUSTOMER_ID,
        LOWER(TRIM(s.EMAIL))                                AS EMAIL,
        INITCAP(TRIM(s.FULL_NAME))                          AS FULL_NAME,
        UPPER(TRIM(s.COUNTRY_CODE))                         AS COUNTRY_CODE,
        INITCAP(LOWER(TRIM(s.SEGMENT)))                     AS SEGMENT,
        TRY_TO_BOOLEAN(s.IS_ACTIVE)                         AS IS_ACTIVE,
        TRY_TO_TIMESTAMP_NTZ(s.CREATED_AT)                  AS CREATED_AT,
        CURRENT_TIMESTAMP()                                 AS _UPDATED_AT
    FROM ANALYTICS.STAGING.STG_CUSTOMERS s
    -- Only process rows that are new OR have changed since last load
    WHERE NOT EXISTS (
        SELECT 1
        FROM ANALYTICS.MARTS.DIM_CUSTOMERS t
        WHERE t.CUSTOMER_ID = s.CUSTOMER_ID
          AND t.EMAIL        = LOWER(TRIM(s.EMAIL))
          AND t.SEGMENT      = INITCAP(LOWER(TRIM(s.SEGMENT)))
          AND t.IS_ACTIVE    = TRY_TO_BOOLEAN(s.IS_ACTIVE)
    )
) AS source
ON target.CUSTOMER_ID = source.CUSTOMER_ID

WHEN MATCHED THEN UPDATE SET
    target.EMAIL         = source.EMAIL,
    target.FULL_NAME     = source.FULL_NAME,
    target.COUNTRY_CODE  = source.COUNTRY_CODE,
    target.SEGMENT       = source.SEGMENT,
    target.IS_ACTIVE     = source.IS_ACTIVE,
    target._UPDATED_AT   = source._UPDATED_AT

WHEN NOT MATCHED THEN INSERT (
    CUSTOMER_ID, EMAIL, FULL_NAME, COUNTRY_CODE,
    SEGMENT, IS_ACTIVE, CREATED_AT, _UPDATED_AT
)
VALUES (
    source.CUSTOMER_ID, source.EMAIL, source.FULL_NAME, source.COUNTRY_CODE,
    source.SEGMENT, source.IS_ACTIVE, source.CREATED_AT, source._UPDATED_AT
);


-- ---------------------------------------------------------------------------
-- Exercise 7: Demonstrate Time Travel on an Iceberg Table
-- ---------------------------------------------------------------------------
-- Iceberg tables support Time Travel using Snowflake's AT/BEFORE syntax.

-- Query data as it existed 1 hour ago
SELECT COUNT(*) AS row_count_1h_ago
FROM ANALYTICS.SILVER.ORDERS_ICEBERG
AT (OFFSET => -3600);   -- 3600 seconds = 1 hour

-- Query at a specific timestamp
SELECT *
FROM ANALYTICS.SILVER.ORDERS_ICEBERG
AT (TIMESTAMP => '2024-06-01 00:00:00'::TIMESTAMP_NTZ)
WHERE ORDER_DATE = '2024-05-31'
LIMIT 10;

-- Restore accidentally deleted rows using Time Travel
-- (Example: accidental DELETE of June data)
INSERT INTO ANALYTICS.SILVER.ORDERS_ICEBERG
SELECT *
FROM ANALYTICS.SILVER.ORDERS_ICEBERG
BEFORE (STATEMENT => '<query_id_of_the_delete>')
WHERE ORDER_DATE BETWEEN '2024-06-01' AND '2024-06-30';


-- ---------------------------------------------------------------------------
-- Exercise 8: Data Vault – Hub, Satellite, Link pattern tables
-- ---------------------------------------------------------------------------

-- Hub: stores only the business key + metadata
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.HUB_CUSTOMER (
    CUSTOMER_HK         VARCHAR(64)     NOT NULL,   -- MD5 of CUSTOMER_ID
    CUSTOMER_BK         VARCHAR(50)     NOT NULL,   -- Business key (CUSTOMER_ID)
    LOAD_DATE           TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    RECORD_SOURCE       VARCHAR(100)    NOT NULL,
    CONSTRAINT pk_hub_customer PRIMARY KEY (CUSTOMER_HK)
);

CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.HUB_ORDER (
    ORDER_HK            VARCHAR(64)     NOT NULL,
    ORDER_BK            VARCHAR(50)     NOT NULL,
    LOAD_DATE           TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    RECORD_SOURCE       VARCHAR(100)    NOT NULL,
    CONSTRAINT pk_hub_order PRIMARY KEY (ORDER_HK)
);

-- Satellite: stores descriptive attributes with full history
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.SAT_CUSTOMER_DETAILS (
    CUSTOMER_HK         VARCHAR(64)     NOT NULL,
    LOAD_DATE           TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    LOAD_END_DATE       TIMESTAMP_NTZ,                -- NULL = current record
    HASH_DIFF           VARCHAR(64)     NOT NULL,     -- MD5 of all attribute columns
    EMAIL               VARCHAR(255),
    FULL_NAME           VARCHAR(255),
    SEGMENT             VARCHAR(20),
    COUNTRY_CODE        VARCHAR(10),
    IS_ACTIVE           BOOLEAN,
    RECORD_SOURCE       VARCHAR(100)    NOT NULL,
    CONSTRAINT pk_sat_customer PRIMARY KEY (CUSTOMER_HK, LOAD_DATE)
);

-- Link: stores relationships between Hubs (many-to-many)
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.LNK_CUSTOMER_ORDER (
    CUST_ORDER_HK       VARCHAR(64)     NOT NULL,     -- MD5 of (CUSTOMER_HK + ORDER_HK)
    CUSTOMER_HK         VARCHAR(64)     NOT NULL,
    ORDER_HK            VARCHAR(64)     NOT NULL,
    LOAD_DATE           TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    RECORD_SOURCE       VARCHAR(100)    NOT NULL,
    CONSTRAINT pk_lnk_customer_order PRIMARY KEY (CUST_ORDER_HK),
    INDEX idx_lnk_customer (CUSTOMER_HK),
    INDEX idx_lnk_order    (ORDER_HK)
);

-- Example: load into Data Vault Hub from staging
INSERT INTO ANALYTICS.MARTS.HUB_CUSTOMER (CUSTOMER_HK, CUSTOMER_BK, RECORD_SOURCE)
SELECT DISTINCT
    MD5(CUSTOMER_ID)                                        AS CUSTOMER_HK,
    CUSTOMER_ID                                             AS CUSTOMER_BK,
    'ORDER_SERVICE'                                         AS RECORD_SOURCE
FROM ANALYTICS.STAGING.STG_CUSTOMERS
WHERE MD5(CUSTOMER_ID) NOT IN (SELECT CUSTOMER_HK FROM ANALYTICS.MARTS.HUB_CUSTOMER);


-- ---------------------------------------------------------------------------
-- Exercise 9: CLONE production DB for dev environment
-- ---------------------------------------------------------------------------

-- Zero-copy clone: instant, only new changes incur storage cost
CREATE DATABASE IF NOT EXISTS DEV_ANALYTICS CLONE ANALYTICS;

-- Clone a single table (useful for testing migrations)
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.DIM_CUSTOMERS_BACKUP
    CLONE ANALYTICS.MARTS.DIM_CUSTOMERS;

-- Clone a schema
CREATE SCHEMA IF NOT EXISTS ANALYTICS.MARTS_BACKUP
    CLONE ANALYTICS.MARTS;

-- Verify clone relationship
SELECT SYSTEM$CLONE_DEPENDENCIES('ANALYTICS');


-- ---------------------------------------------------------------------------
-- Exercise 10: Replication setup (syntax / example)
-- ---------------------------------------------------------------------------

-- Enable replication for a database (run as ACCOUNTADMIN)
-- Replicates to a secondary account in another region/cloud for DR/read scaling

/*
-- On primary account:
USE ROLE ACCOUNTADMIN;

ALTER DATABASE ANALYTICS ENABLE REPLICATION TO ACCOUNTS
    aws_us_west_2.secondary_account_identifier;

-- On secondary account:
USE ROLE ACCOUNTADMIN;

CREATE DATABASE ANALYTICS AS REPLICA OF
    aws_us_east_1.primary_account_identifier.ANALYTICS;

-- Create a replication group for consistent multi-object replication
CREATE REPLICATION GROUP analytics_replication_group
    OBJECT_TYPES = DATABASES, INTEGRATIONS, RESOURCE MONITORS
    DATABASES    = ANALYTICS
    ALLOWED_INTEGRATION_TYPES = NOTIFICATION INTEGRATIONS
    ALLOWED_ACCOUNTS = aws_us_west_2.secondary_account_identifier
    REPLICATION_SCHEDULE = '10 MINUTES';

-- Trigger a manual refresh on the secondary
ALTER REPLICATION GROUP analytics_replication_group REFRESH;
*/

SELECT 'Exercise 10: Replication setup requires ACCOUNTADMIN and cross-account access. See commented code.' AS note;


-- ---------------------------------------------------------------------------
-- Exercise 11: Implement naming conventions check query
-- ---------------------------------------------------------------------------
-- Audit your Snowflake account for objects that violate naming conventions:
--   - Tables: must be UPPER_SNAKE_CASE
--   - Views: must be prefixed with VW_ or be in the STAGING schema (views)
--   - Stored Procedures: must start with SP_
--   - Functions (UDFs): must start with FN_
--   - Schemas: must be one of (RAW, STAGING, MARTS, BRONZE, SILVER, GOLD, GOVERNANCE, ML_FEATURES)

WITH tables_audit AS (
    SELECT
        TABLE_CATALOG,
        TABLE_SCHEMA,
        TABLE_NAME,
        TABLE_TYPE,
        'TABLE' AS object_type,
        CASE
            WHEN TABLE_NAME != UPPER(TABLE_NAME)
            THEN 'FAIL: table name is not UPPER_CASE'
            WHEN TABLE_NAME LIKE '% %'
            THEN 'FAIL: table name contains spaces'
            ELSE 'PASS'
        END AS convention_check
    FROM ANALYTICS.INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
),
views_audit AS (
    SELECT
        TABLE_CATALOG,
        TABLE_SCHEMA,
        TABLE_NAME,
        TABLE_TYPE,
        'VIEW' AS object_type,
        CASE
            WHEN TABLE_SCHEMA = 'STAGING' THEN 'PASS'   -- staging views OK without prefix
            WHEN TABLE_NAME NOT LIKE 'VW_%' AND TABLE_NAME NOT LIKE 'STG_%'
            THEN 'WARN: view name should start with VW_ or STG_'
            ELSE 'PASS'
        END AS convention_check
    FROM ANALYTICS.INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'VIEW'
      AND TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
)
SELECT * FROM tables_audit  WHERE convention_check != 'PASS'
UNION ALL
SELECT * FROM views_audit   WHERE convention_check != 'PASS'
ORDER BY TABLE_SCHEMA, object_type, TABLE_NAME;


-- ---------------------------------------------------------------------------
-- Exercise 12: Performance at scale – clustering + search optimization combined
-- ---------------------------------------------------------------------------

-- Step 1: Enable clustering on a large fact table
-- Best for: tables > 1 TB frequently filtered on a date or region column
ALTER TABLE ANALYTICS.MARTS.FCT_ORDERS
    CLUSTER BY (ORDER_DATE, REGION);

-- Check current clustering depth (depth ~1 = well-clustered, higher = needs reclustering)
SELECT
    SYSTEM$CLUSTERING_INFORMATION('ANALYTICS.MARTS.FCT_ORDERS')::VARIANT AS cluster_info;

-- Step 2: Enable Search Optimization Service on columns used in equality
-- and IN-list predicates (e.g., customer lookup by ID or email)
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    ADD SEARCH OPTIMIZATION ON EQUALITY(CUSTOMER_ID, EMAIL);

ALTER TABLE ANALYTICS.MARTS.FCT_ORDERS
    ADD SEARCH OPTIMIZATION ON EQUALITY(ORDER_ID, CUSTOMER_ID)
                            ON SUBSTRING(STATUS);

-- Step 3: Verify search optimization is active
SELECT
    TABLE_NAME,
    SEARCH_OPTIMIZATION,
    SEARCH_OPTIMIZATION_PROGRESS,
    SEARCH_OPTIMIZATION_BYTES
FROM ANALYTICS.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'MARTS'
  AND SEARCH_OPTIMIZATION = 'ON'
ORDER BY TABLE_NAME;

-- Step 4: Validate that query plans use micro-partition pruning
-- Run EXPLAIN on a typical query and check PARTITIONS_SCANNED / PARTITIONS_TOTAL
EXPLAIN
SELECT
    o.ORDER_ID,
    o.AMOUNT,
    c.FULL_NAME,
    c.SEGMENT
FROM ANALYTICS.MARTS.FCT_ORDERS      o
JOIN ANALYTICS.MARTS.DIM_CUSTOMERS   c ON o.CUSTOMER_ID = c.CUSTOMER_ID
WHERE o.ORDER_DATE BETWEEN '2024-06-01' AND '2024-06-30'
  AND o.REGION     = 'US-EAST'
  AND c.SEGMENT    = 'Gold';
