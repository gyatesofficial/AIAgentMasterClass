-- =============================================================================
-- FILE: chapter_03_setup/exercises.sql
-- TOPIC: Environment Setup — Sessions, Parameters, Databases, Schemas, Roles
-- COURSE: Snowflake Master Course | Chapter 3
-- =============================================================================
-- This chapter covers the first things you do every time you start a new
-- Snowflake project: verify connectivity, configure session parameters,
-- create your database/schema structure, and test role switching.
-- =============================================================================

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Test connection and confirm your Snowflake version and context
-- WHY IT MATTERS: The first thing any engineer should do after connecting is
--                 verify they are in the right account, region, and role.
-- =============================================================================

SELECT
    CURRENT_ACCOUNT()          AS account_locator,
    CURRENT_REGION()           AS region,
    CURRENT_VERSION()          AS snowflake_version,
    CURRENT_USER()             AS connected_user,
    CURRENT_ROLE()             AS active_role,
    CURRENT_WAREHOUSE()        AS active_warehouse,
    CURRENT_DATABASE()         AS active_database,
    CURRENT_TIMESTAMP()        AS server_time;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Set important session parameters for consistent behaviour
-- WHY IT MATTERS: Snowflake sessions inherit account-level parameter defaults,
--                 but you can override them per session. Consistent timezone
--                 and date format settings prevent silent bugs.
-- =============================================================================

-- Set timezone to UTC (best practice for all data warehouse work)
ALTER SESSION SET TIMEZONE = 'UTC';

-- Set date and timestamp output formats
ALTER SESSION SET DATE_OUTPUT_FORMAT        = 'YYYY-MM-DD';
ALTER SESSION SET TIMESTAMP_OUTPUT_FORMAT   = 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM';
ALTER SESSION SET TIMESTAMP_NTZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF3';

-- Set a query tag so all queries in this session are identifiable in history
ALTER SESSION SET QUERY_TAG = 'chapter_03_setup_exercises';

-- Verify the parameters took effect
SHOW PARAMETERS LIKE '%TIMEZONE%'         IN SESSION;
SHOW PARAMETERS LIKE '%DATE_OUTPUT%'      IN SESSION;
SHOW PARAMETERS LIKE '%QUERY_TAG%'        IN SESSION;

-- Confirm timezone is applied
SELECT CURRENT_TIMESTAMP() AS utc_timestamp;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Create and activate a training database
-- WHY IT MATTERS: Isolating course work in a dedicated database prevents
--                 accidentally touching production data. Always USE the
--                 database after creating it.
-- =============================================================================

USE ROLE SYSADMIN;

-- Create the training database (idempotent)
CREATE DATABASE IF NOT EXISTS TRAINING_DB
    DATA_RETENTION_TIME_IN_DAYS = 1     -- minimal retention for training data
    COMMENT = 'Chapter 3 training database — safe to drop after course';

-- Activate the database for subsequent statements
USE DATABASE TRAINING_DB;

-- Verify
SELECT CURRENT_DATABASE() AS active_db;

-- Explore the auto-created schemas
SHOW SCHEMAS IN DATABASE TRAINING_DB;
-- Snowflake automatically creates INFORMATION_SCHEMA and PUBLIC in every database.

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Create multiple schemas reflecting a layered architecture
-- WHY IT MATTERS: Schema design is the first architectural decision in any
--                 Snowflake project. A clear raw → staging → mart flow
--                 keeps data lineage traceable and access control simple.
-- =============================================================================

USE DATABASE TRAINING_DB;

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Landing zone for raw ingested data — no transformations applied';

CREATE SCHEMA IF NOT EXISTS STAGING
    COMMENT = 'Cleaned, typed, deduplicated models ready for analysis';

CREATE SCHEMA IF NOT EXISTS MARTS
    COMMENT = 'Business-facing aggregates and dimensional models';

CREATE SCHEMA IF NOT EXISTS SANDBOX
    COMMENT = 'Developer scratch space — objects here may be dropped without notice';

-- List all schemas to confirm creation
SHOW SCHEMAS IN DATABASE TRAINING_DB;

-- Switch to STAGING to set it as the default for subsequent exercises
USE SCHEMA STAGING;
SELECT CURRENT_SCHEMA() AS active_schema;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Switch between roles and observe the difference in access
-- WHY IT MATTERS: Every real query you write runs under a specific role.
--                 Switching roles mid-session lets you test privilege boundaries
--                 without logging in/out.
-- =============================================================================

-- Start as SYSADMIN
USE ROLE SYSADMIN;
SELECT CURRENT_ROLE() AS role_check;
SHOW DATABASES;   -- shows all databases SYSADMIN can see

-- Switch to DATA_ANALYST_ROLE (if it exists from setup script)
-- Try to access ANALYTICS_DB (should succeed if grants were applied in Chapter 1)
USE ROLE DATA_ANALYST_ROLE;
SELECT CURRENT_ROLE() AS role_check;
USE DATABASE ANALYTICS_DB;
USE SCHEMA MARTS;
SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE();

-- Switch to REPORTING_ROLE (read-only)
USE ROLE REPORTING_ROLE;
SELECT CURRENT_ROLE() AS role_check;

-- Attempt to create a table as REPORTING_ROLE — should fail with "Insufficient privileges"
-- Uncomment to observe the error:
-- CREATE TABLE test_table (id NUMBER);

-- Return to SYSADMIN
USE ROLE SYSADMIN;
USE DATABASE TRAINING_DB;
USE SCHEMA STAGING;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Test warehouse auto-resume behaviour
-- WHY IT MATTERS: AUTO_RESUME = TRUE means queries automatically boot the
--                 warehouse. Observing this confirms your session config is correct.
-- =============================================================================

USE WAREHOUSE DEV_WH;

-- Manually suspend the warehouse
ALTER WAREHOUSE DEV_WH SUSPEND;

-- Verify it is SUSPENDED
SELECT "name", "state" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- Run a query that requires compute — DEV_WH should auto-resume
-- (you will see a small startup delay the first time)
SELECT 'Warehouse auto-resumed!' AS message, CURRENT_TIMESTAMP() AS resumed_at;

-- Confirm STARTED state
SHOW WAREHOUSES LIKE 'DEV_WH';

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Set and inspect a session-level QUERY_TAG
-- WHY IT MATTERS: Query tags show up in QUERY_HISTORY, making it easy to
--                 filter and attribute queries by workload, application, or user.
--                 This is essential for cost attribution across teams.
-- =============================================================================

-- Tag all queries from this session with a descriptive label
ALTER SESSION SET QUERY_TAG = 'training::chapter_03::setup_exercises';

-- Run a few queries that will carry this tag
SELECT COUNT(*) AS schema_count
FROM   INFORMATION_SCHEMA.SCHEMATA
WHERE  schema_name != 'INFORMATION_SCHEMA';

SELECT table_schema, COUNT(*) AS table_count
FROM   INFORMATION_SCHEMA.TABLES
GROUP  BY table_schema;

-- Find queries with our tag in history (may take a moment to appear)
SELECT query_id,
       query_tag,
       query_text,
       start_time,
       total_elapsed_time
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 20))
WHERE  query_tag ILIKE '%chapter_03%'
ORDER  BY start_time DESC;

-- Reset query tag
ALTER SESSION SET QUERY_TAG = '';

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: SHOW PARAMETERS — understand account vs session vs object defaults
-- WHY IT MATTERS: Snowflake parameters operate at three levels:
--                 Account > User > Session. Session values override user defaults,
--                 user defaults override account defaults.
-- =============================================================================

-- Show all SESSION parameters
SHOW PARAMETERS IN SESSION;

-- Show all ACCOUNT parameters (requires ACCOUNTADMIN or SYSADMIN)
USE ROLE ACCOUNTADMIN;
SHOW PARAMETERS IN ACCOUNT;
USE ROLE SYSADMIN;

-- Show parameters for a specific warehouse
SHOW PARAMETERS IN WAREHOUSE DEV_WH;

-- Show parameters for the current database
SHOW PARAMETERS IN DATABASE TRAINING_DB;

-- Filter to see only parameters that differ from their default
-- (use RESULT_SCAN to query the SHOW output)
SHOW PARAMETERS IN SESSION;
SELECT "key", "value", "default", "description"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE  "value" != "default"
  AND  "value" != ''
ORDER  BY "key";

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: SnowSQL connection string format (reference and examples)
-- WHY IT MATTERS: SnowSQL is the command-line client for Snowflake.
--                 Knowing the connection syntax is essential for automation,
--                 scripting, and CI/CD pipelines.
-- =============================================================================

-- SnowSQL basic connection:
--   snowsql -a <account_identifier> -u <username>
--
-- Account identifier formats:
--   Legacy locator:  xy12345.us-east-1.aws
--   New org format:  myorg-myaccount
--
-- Full example with all flags:
--   snowsql \
--     -a myorg-myaccount \
--     -u alice_engineer \
--     -r DATA_ENGINEER_ROLE \
--     -w TRANSFORM_WH \
--     -d ANALYTICS_DB \
--     -s STAGING \
--     -f setup/00_account_setup.sql
--
-- Run a file:
--   snowsql -a myorg-myaccount -u alice -f chapter_03_setup/exercises.sql
--
-- Pass a variable:
--   snowsql -a myorg-myaccount -u alice -D MY_VAR=hello -q "SELECT '&MY_VAR'"
--
-- ~/.snowsql/config file format (store credentials safely):
--   [connections]
--   accountname = myorg-myaccount
--   username    = alice_engineer
--   rolename    = DATA_ENGINEER_ROLE
--   warehousename = DEV_WH
--   dbname      = ANALYTICS_DB
--   schemaname  = STAGING

-- Python connector example (for reference):
-- import snowflake.connector
-- conn = snowflake.connector.connect(
--     account   = 'myorg-myaccount',
--     user      = 'alice_engineer',
--     password  = 'mypassword',         # use key-pair in production!
--     role      = 'DATA_ENGINEER_ROLE',
--     warehouse = 'DEV_WH',
--     database  = 'ANALYTICS_DB',
--     schema    = 'STAGING'
-- )

SELECT 'See comment block above for SnowSQL connection syntax.' AS note;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Check if a network policy is applied to the current account or user
-- WHY IT MATTERS: Network policies restrict login by IP address. Before
--                 debugging a connection failure, confirm whether a policy
--                 is blocking the originating IP.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Check account-level network policy
SHOW PARAMETERS LIKE 'NETWORK_POLICY' IN ACCOUNT;

-- Check the current user's network policy (user-level overrides account-level)
SHOW PARAMETERS LIKE 'NETWORK_POLICY' IN USER IDENTIFIER(CURRENT_USER());

-- List all network policies defined in the account
SHOW NETWORK POLICIES;

-- Query ACCOUNT_USAGE for network policy history (shows changes over time)
SELECT policy_name,
       policy_owner,
       allowed_ip_list,
       blocked_ip_list,
       created_on,
       deleted_on
FROM   SNOWFLAKE.ACCOUNT_USAGE.NETWORK_POLICIES
WHERE  deleted_on IS NULL
ORDER  BY created_on DESC;

USE ROLE SYSADMIN;

-- =============================================================================
-- CLEANUP (optional)
-- =============================================================================
-- DROP DATABASE IF EXISTS TRAINING_DB;

-- =============================================================================
-- END OF CHAPTER 3 EXERCISES
-- =============================================================================
