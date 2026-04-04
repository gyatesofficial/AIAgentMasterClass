-- =============================================================================
-- FILE: chapter_01_introduction/exercises.sql
-- TOPIC: Introduction to Snowflake — Account Basics, System Views, Metadata
-- COURSE: Snowflake Master Course | Chapter 1
-- =============================================================================
-- Run these exercises top-to-bottom in a Snowflake Worksheet.
-- Use the DEV_WH warehouse for all queries in this chapter.
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Check Snowflake version, current context (role, warehouse, database)
-- WHY IT MATTERS: Always confirm your context before running DDL or DML —
--                 the wrong role or database leads to hard-to-trace errors.
-- =============================================================================

SELECT CURRENT_VERSION()    AS snowflake_version,
       CURRENT_ROLE()       AS active_role,
       CURRENT_USER()       AS logged_in_user,
       CURRENT_WAREHOUSE()  AS active_warehouse,
       CURRENT_DATABASE()   AS active_database,
       CURRENT_SCHEMA()     AS active_schema,
       CURRENT_TIMESTAMP()  AS query_time;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Show all databases the current role can see
-- WHY IT MATTERS: SHOW commands return metadata from Snowflake's metadata layer
--                 instantly — no warehouse needed. They never scan micro-partitions.
-- =============================================================================

SHOW DATABASES;

-- Filter just the databases you created (excludes Snowflake-provided databases)
-- The result set from SHOW can be queried using the special result scan trick:
SELECT "name", "created_on", "owner", "comment"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE  "name" NOT IN ('SNOWFLAKE', 'SNOWFLAKE_SAMPLE_DATA');

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Show all virtual warehouses and their current state
-- WHY IT MATTERS: Warehouses drive all SQL compute costs. Understanding their
--                 state (STARTED, SUSPENDED) helps you manage credits.
-- =============================================================================

SHOW WAREHOUSES;

-- Pull warehouse size and state into a clean result set
SELECT "name"            AS warehouse_name,
       "size"            AS warehouse_size,
       "state"           AS current_state,
       "auto_suspend"    AS auto_suspend_seconds,
       "max_cluster_count"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Explore all roles and confirm which role you are currently using
-- WHY IT MATTERS: Snowflake RBAC is role-based, not user-based. Understanding
--                 role hierarchy is fundamental to security and access design.
-- =============================================================================

-- List all roles visible to the current user
SHOW ROLES;

-- Check which roles are granted to your current user
SHOW GRANTS TO USER IDENTIFIER($CURRENT_USER);  -- replace with your username if needed
-- Example: SHOW GRANTS TO USER my_username;

-- Confirm the role currently in use
SELECT CURRENT_ROLE() AS my_current_role;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Explore INFORMATION_SCHEMA system views within a database
-- WHY IT MATTERS: Every Snowflake database has an INFORMATION_SCHEMA with views
--                 that expose schema metadata for that database.
-- =============================================================================

USE DATABASE ANALYTICS_DB;

-- List all tables visible in INFORMATION_SCHEMA
SELECT table_name, table_type
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.TABLES
ORDER  BY table_name;

-- List all schemas in the database
SELECT schema_name, created, last_altered
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.SCHEMATA
ORDER  BY schema_name;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Query ACCOUNT_USAGE views for account-wide telemetry
-- WHY IT MATTERS: ACCOUNT_USAGE is the gold standard for Snowflake operational
--                 intelligence — query history, credit usage, login events, etc.
--                 Note: ACCOUNT_USAGE has a ~45-minute latency.
-- REQUIRES: ACCOUNTADMIN or a role with IMPORTED PRIVILEGES on SNOWFLAKE DB
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Check credit usage for the last 30 days across all warehouses
SELECT warehouse_name,
       SUM(credits_used)         AS total_credits,
       SUM(credits_used_compute) AS compute_credits,
       SUM(credits_used_cloud_services) AS cloud_service_credits
FROM   SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE  start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP  BY 1
ORDER  BY 2 DESC;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Query the QUERY_HISTORY view to see recent queries
-- WHY IT MATTERS: QUERY_HISTORY is your primary debugging tool. It shows
--                 execution time, partitions scanned, bytes scanned, and more.
-- =============================================================================

-- Last 20 queries run by the current user (from INFORMATION_SCHEMA — no latency)
SELECT query_id,
       query_text,
       warehouse_name,
       execution_status,
       total_elapsed_time    / 1000 AS elapsed_seconds,
       partitions_scanned,
       partitions_total,
       bytes_scanned         / 1024 / 1024 AS mb_scanned
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(
               USER_NAME     => CURRENT_USER(),
               RESULT_LIMIT  => 20
             ))
ORDER  BY start_time DESC;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Query ACCOUNT_USAGE.DATABASES for database metadata history
-- WHY IT MATTERS: This view includes dropped databases (unlike SHOW DATABASES),
--                 making it useful for auditing and recovery investigations.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

SELECT database_name,
       created,
       last_altered,
       deleted,         -- populated when a database is dropped
       retention_time,
       owner,
       comment
FROM   SNOWFLAKE.ACCOUNT_USAGE.DATABASES
WHERE  deleted IS NULL   -- filter out dropped databases
ORDER  BY created DESC;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Inspect current session parameters
-- WHY IT MATTERS: Session parameters control timezone, date format, query tag,
--                 and many other behavioural settings. Knowing the defaults
--                 prevents silent bugs in date/time arithmetic.
-- =============================================================================

-- Show parameters that differ from their system default for the current session
SHOW PARAMETERS IN SESSION;

-- Show a specific parameter
SHOW PARAMETERS LIKE 'TIMEZONE' IN SESSION;
SHOW PARAMETERS LIKE 'DATE_OUTPUT_FORMAT' IN SESSION;
SHOW PARAMETERS LIKE 'TIMESTAMP_OUTPUT_FORMAT' IN SESSION;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: View Snowflake regions and cloud providers
-- WHY IT MATTERS: Data residency requirements often dictate which region
--                 you deploy in. Understanding the region list helps with
--                 multi-cloud and data localisation planning.
-- =============================================================================

-- SHOW REGIONS lists all Snowflake deployment regions across AWS, Azure, GCP
SHOW REGIONS;

SELECT "region_group", "cloud", "name" AS region_name, "display_name"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER  BY "cloud", "region_group";

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Show all schemas in the ANALYTICS_DB database
-- WHY IT MATTERS: Schemas are the primary namespace organiser in Snowflake.
--                 Understanding your schema layout is essential before writing
--                 any cross-schema queries.
-- =============================================================================

USE DATABASE ANALYTICS_DB;
SHOW SCHEMAS;

-- Also query INFORMATION_SCHEMA for schema details
SELECT schema_name,
       created,
       last_altered,
       retention_time
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.SCHEMATA
WHERE  schema_name != 'INFORMATION_SCHEMA'
ORDER  BY schema_name;

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Check account details including Snowflake edition
-- WHY IT MATTERS: Feature availability depends on your account edition.
--                 Enterprise unlocks multi-cluster warehouses, column-level
--                 security, and Time Travel up to 90 days.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Current account identifier (used for data sharing and replication)
SELECT CURRENT_ACCOUNT()         AS account_locator,
       CURRENT_REGION()          AS deployment_region,
       CURRENT_ORGANIZATION_NAME() AS org_name;

-- Show account-level parameters
SHOW PARAMETERS IN ACCOUNT;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Show file formats available in the account / current database
-- WHY IT MATTERS: File formats define how Snowflake parses incoming data
--                 during COPY INTO operations. Understanding what exists
--                 prevents you from re-creating duplicates.
-- =============================================================================

USE DATABASE ANALYTICS_DB;

-- Show file formats in the current database
SHOW FILE FORMATS IN DATABASE ANALYTICS_DB;

-- Show file formats in SNOWFLAKE_SAMPLE_DATA (pre-built examples to inspect)
SHOW FILE FORMATS IN DATABASE SNOWFLAKE_SAMPLE_DATA;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Query storage usage across databases
-- WHY IT MATTERS: Storage is billed separately from compute in Snowflake.
--                 Monitoring storage prevents surprise bills, especially when
--                 Time Travel is set to 90 days on large tables.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Account-level storage usage summary
SELECT usage_date,
       storage_bytes     / POWER(1024, 3) AS storage_gb,
       stage_bytes       / POWER(1024, 3) AS stage_gb,
       failsafe_bytes    / POWER(1024, 3) AS failsafe_gb
FROM   SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
ORDER  BY usage_date DESC
LIMIT  10;

USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: Explore INFORMATION_SCHEMA table function: QUERY_HISTORY
-- WHY IT MATTERS: INFORMATION_SCHEMA functions return near-real-time data
--                 (no latency unlike ACCOUNT_USAGE). Use them for live
--                 debugging during development sessions.
-- =============================================================================

-- Query history for the last hour on the current warehouse
SELECT query_id,
       query_type,
       query_text,
       execution_status,
       ROUND(total_elapsed_time / 1000, 2)   AS elapsed_sec,
       ROUND(bytes_scanned / 1024 / 1024, 2) AS mb_scanned,
       partitions_scanned,
       partitions_total,
       ROUND(100.0 * partitions_scanned
             / NULLIF(partitions_total, 0), 1)  AS pct_partitions_scanned
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
               DATERANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
               RESULT_LIMIT    => 100
             ))
WHERE  warehouse_name = 'DEV_WH'
ORDER  BY start_time DESC;

-- =============================================================================
-- END OF CHAPTER 1 EXERCISES
-- =============================================================================
