-- =============================================================================
-- FILE: setup/00_account_setup.sql
-- PURPOSE: Enterprise-grade Snowflake account bootstrap
-- RUN AS:  ACCOUNTADMIN
-- COURSE:  Snowflake Master Course
-- =============================================================================
-- This script provisions every role, warehouse, database, schema, and privilege
-- used throughout the course. Run it once at the start of the course.
-- It is idempotent — all CREATE statements use IF NOT EXISTS.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- SECTION 1: ROLE CREATION
-- =============================================================================
-- We follow the principle of least-privilege. Each role gets only the access
-- it needs for its job function. Roles are the primary access-control unit in
-- Snowflake — users inherit privileges through their role grants, never directly.

-- Core functional roles
CREATE ROLE IF NOT EXISTS DATA_ENGINEER_ROLE
    COMMENT = 'Full read/write access to RAW and STAGING schemas; can operate warehouses';

CREATE ROLE IF NOT EXISTS DATA_ANALYST_ROLE
    COMMENT = 'Read access to STAGING and MARTS schemas for analysis and reporting';

CREATE ROLE IF NOT EXISTS DATA_SCIENTIST_ROLE
    COMMENT = 'Read access to MARTS and ML_FEATURES; can write to ML_FEATURES schema';

CREATE ROLE IF NOT EXISTS DBT_ROLE
    COMMENT = 'Service account role for dbt transformations; write access to STAGING and MARTS';

CREATE ROLE IF NOT EXISTS REPORTING_ROLE
    COMMENT = 'Read-only access to MARTS schema for BI tools (Tableau, Power BI, Looker)';

CREATE ROLE IF NOT EXISTS GOVERNANCE_ROLE
    COMMENT = 'Manages data masking policies, row access policies, and object tags';

-- =============================================================================
-- SECTION 2: ROLE HIERARCHY
-- =============================================================================
-- Snowflake roles form a directed acyclic graph (DAG).
-- Granting role A to role B means B inherits all of A's privileges.
-- SYSADMIN sits at the top of the functional hierarchy so it can manage
-- all objects created by functional roles.

-- DATA_ENGINEER_ROLE inherits from DATA_ANALYST_ROLE
-- (engineers can do everything analysts can, plus more)
GRANT ROLE DATA_ANALYST_ROLE   TO ROLE DATA_ENGINEER_ROLE;

-- DATA_ENGINEER_ROLE inherits from REPORTING_ROLE
GRANT ROLE REPORTING_ROLE      TO ROLE DATA_ANALYST_ROLE;

-- DATA_SCIENTIST_ROLE inherits ANALYST read access
GRANT ROLE DATA_ANALYST_ROLE   TO ROLE DATA_SCIENTIST_ROLE;

-- DBT_ROLE is a peer of DATA_ENGINEER_ROLE; grant it to engineers so they can
-- impersonate dbt when debugging transformation pipelines
GRANT ROLE DBT_ROLE            TO ROLE DATA_ENGINEER_ROLE;

-- Elevate all functional roles to SYSADMIN so SYSADMIN can manage their objects
GRANT ROLE DATA_ENGINEER_ROLE  TO ROLE SYSADMIN;
GRANT ROLE DATA_ANALYST_ROLE   TO ROLE SYSADMIN;
GRANT ROLE DATA_SCIENTIST_ROLE TO ROLE SYSADMIN;
GRANT ROLE DBT_ROLE            TO ROLE SYSADMIN;
GRANT ROLE REPORTING_ROLE      TO ROLE SYSADMIN;
GRANT ROLE GOVERNANCE_ROLE     TO ROLE SYSADMIN;

-- =============================================================================
-- SECTION 3: WAREHOUSE CREATION
-- =============================================================================
-- Warehouses are pure compute — they are billed per second (60-second minimum).
-- Choose the right size for each workload; over-provisioning wastes credits.

-- DEV_WH: X-Small for development and ad-hoc queries
--   XS = 1 compute node, ~1 credit/hour
--   Fast auto-suspend to minimise idle cost
CREATE WAREHOUSE IF NOT EXISTS DEV_WH
    WAREHOUSE_SIZE        = 'X-SMALL'
    AUTO_SUSPEND          = 60           -- seconds; suspend after 1 minute idle
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    COMMENT               = 'Development and ad-hoc query warehouse. Keep small to control cost.';

-- TRANSFORM_WH: Medium for dbt and EL transformation pipelines
--   M = 4 compute nodes; good balance for typical transformation workloads
CREATE WAREHOUSE IF NOT EXISTS TRANSFORM_WH
    WAREHOUSE_SIZE        = 'MEDIUM'
    AUTO_SUSPEND          = 120
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    MAX_CLUSTER_COUNT     = 1            -- single-cluster for predictable serialised transforms
    COMMENT               = 'dbt and ELT transformation pipelines. Run as DBT_ROLE.';

-- ANALYTICS_WH: Large, multi-cluster for concurrent analyst workloads
--   L = 8 compute nodes; multi-cluster scales out (not up) under concurrency
CREATE WAREHOUSE IF NOT EXISTS ANALYTICS_WH
    WAREHOUSE_SIZE        = 'LARGE'
    AUTO_SUSPEND          = 300
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    MIN_CLUSTER_COUNT     = 1
    MAX_CLUSTER_COUNT     = 3            -- up to 3 clusters for concurrency scaling
    SCALING_POLICY        = 'ECONOMY'   -- spin up extra clusters only when queue builds
    COMMENT               = 'Analyst and data science queries. Multi-cluster for concurrency.';

-- REPORTING_WH: Small for BI tool dashboards
--   S = 2 compute nodes; dashboards hit the result cache most of the time
CREATE WAREHOUSE IF NOT EXISTS REPORTING_WH
    WAREHOUSE_SIZE        = 'SMALL'
    AUTO_SUSPEND          = 180
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    COMMENT               = 'BI tool dashboard queries (Tableau, Looker, Power BI).';

-- =============================================================================
-- SECTION 4: RESOURCE MONITORS
-- =============================================================================
-- Resource monitors prevent runaway credit spend. They trigger notifications
-- (and optionally suspend warehouses) when thresholds are crossed.

-- Account-level monthly cap: alert at 80%, suspend at 100%
CREATE RESOURCE MONITOR IF NOT EXISTS ACCOUNT_MONTHLY_MONITOR
    WITH CREDIT_QUOTA = 500             -- adjust to your monthly budget
    FREQUENCY         = MONTHLY
    START_TIMESTAMP   = IMMEDIATELY
    TRIGGERS
        ON 75  PERCENT DO NOTIFY        -- email account admins at 75%
        ON 90  PERCENT DO NOTIFY        -- email again at 90%
        ON 100 PERCENT DO SUSPEND;      -- suspend all warehouses at 100%

-- Apply the monitor to the account
ALTER ACCOUNT SET RESOURCE_MONITOR = ACCOUNT_MONTHLY_MONITOR;

-- Warehouse-level monitor for ANALYTICS_WH (heavy usage risk)
CREATE RESOURCE MONITOR IF NOT EXISTS ANALYTICS_WH_MONITOR
    WITH CREDIT_QUOTA = 150
    FREQUENCY         = MONTHLY
    START_TIMESTAMP   = IMMEDIATELY
    TRIGGERS
        ON 80  PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE ANALYTICS_WH SET RESOURCE_MONITOR = ANALYTICS_WH_MONITOR;

-- =============================================================================
-- SECTION 5: DATABASE CREATION
-- =============================================================================

-- Production analytics database
CREATE DATABASE IF NOT EXISTS ANALYTICS_DB
    DATA_RETENTION_TIME_IN_DAYS = 14    -- 14-day Time Travel for production data
    COMMENT                     = 'Production analytics database — source of truth';

-- Development / sandbox database (shorter retention to save storage cost)
CREATE DATABASE IF NOT EXISTS ANALYTICS_DB_DEV
    DATA_RETENTION_TIME_IN_DAYS = 1
    COMMENT                     = 'Developer sandbox; mirrors ANALYTICS_DB schema, not data';

-- Shared raw ingestion database
CREATE DATABASE IF NOT EXISTS RAW_DB
    DATA_RETENTION_TIME_IN_DAYS = 7
    COMMENT                     = 'Landing zone for all raw source data before transformation';

-- =============================================================================
-- SECTION 6: SCHEMA CREATION
-- =============================================================================
-- Within ANALYTICS_DB we use a layered schema architecture:
--   RAW       -> Untransformed source data (data engineers only)
--   STAGING   -> Cleaned, typed, deduplicated (dbt models)
--   MARTS     -> Business-facing dimensional models / aggregates
--   ML_FEATURES -> Feature store tables for ML model training
--   GOVERNANCE  -> Policy objects, audit tables, tag references

USE DATABASE ANALYTICS_DB;

CREATE SCHEMA IF NOT EXISTS RAW
    DATA_RETENTION_TIME_IN_DAYS = 7
    COMMENT = 'Raw ingestion landing zone — do not query directly in BI tools';

CREATE SCHEMA IF NOT EXISTS STAGING
    DATA_RETENTION_TIME_IN_DAYS = 7
    COMMENT = 'Cleaned and typed intermediate models produced by dbt';

CREATE SCHEMA IF NOT EXISTS MARTS
    DATA_RETENTION_TIME_IN_DAYS = 14
    COMMENT = 'Business-facing dimensional and aggregate models';

CREATE SCHEMA IF NOT EXISTS ML_FEATURES
    DATA_RETENTION_TIME_IN_DAYS = 14
    COMMENT = 'Feature store: training datasets and model feature tables';

CREATE SCHEMA IF NOT EXISTS GOVERNANCE
    DATA_RETENTION_TIME_IN_DAYS = 30
    COMMENT = 'Masking policies, row access policies, object tags, audit helpers';

-- Mirror schemas in the DEV database
USE DATABASE ANALYTICS_DB_DEV;
CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS STAGING;
CREATE SCHEMA IF NOT EXISTS MARTS;
CREATE SCHEMA IF NOT EXISTS ML_FEATURES;

-- =============================================================================
-- SECTION 7: PRIVILEGE GRANTS — DATABASE LEVEL
-- =============================================================================

USE ROLE SYSADMIN;

-- Grant USAGE on databases so roles can see them
GRANT USAGE ON DATABASE ANALYTICS_DB     TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB     TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB     TO ROLE DATA_SCIENTIST_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB     TO ROLE DBT_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB     TO ROLE REPORTING_ROLE;

GRANT USAGE ON DATABASE RAW_DB           TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE ON DATABASE RAW_DB           TO ROLE DBT_ROLE;

GRANT USAGE ON DATABASE ANALYTICS_DB_DEV TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB_DEV TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB_DEV TO ROLE DATA_SCIENTIST_ROLE;
GRANT USAGE ON DATABASE ANALYTICS_DB_DEV TO ROLE DBT_ROLE;

-- =============================================================================
-- SECTION 8: PRIVILEGE GRANTS — SCHEMA AND TABLE LEVEL
-- =============================================================================

-- RAW schema: only DATA_ENGINEER_ROLE and DBT_ROLE can read/write
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.RAW TO ROLE DATA_ENGINEER_ROLE;
GRANT CREATE TABLE, CREATE VIEW,
      CREATE STAGE, CREATE PIPE        ON SCHEMA ANALYTICS_DB.RAW TO ROLE DATA_ENGINEER_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON ALL TABLES IN SCHEMA ANALYTICS_DB.RAW TO ROLE DATA_ENGINEER_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.RAW TO ROLE DATA_ENGINEER_ROLE;

GRANT USAGE                            ON SCHEMA ANALYTICS_DB.RAW TO ROLE DBT_ROLE;
GRANT SELECT                           ON ALL TABLES IN SCHEMA ANALYTICS_DB.RAW TO ROLE DBT_ROLE;
GRANT SELECT                           ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.RAW TO ROLE DBT_ROLE;

-- STAGING schema: DBT_ROLE writes; analysts read
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_SCIENTIST_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.STAGING TO ROLE DBT_ROLE;

GRANT CREATE TABLE, CREATE VIEW        ON SCHEMA ANALYTICS_DB.STAGING TO ROLE DBT_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON ALL TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DBT_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DBT_ROLE;

GRANT SELECT                           ON ALL TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_ANALYST_ROLE;
GRANT SELECT                           ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_ANALYST_ROLE;
GRANT SELECT                           ON ALL TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_SCIENTIST_ROLE;
GRANT SELECT                           ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE DATA_SCIENTIST_ROLE;

-- MARTS schema: DBT_ROLE writes; analysts and reporting read
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_SCIENTIST_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.MARTS TO ROLE DBT_ROLE;
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.MARTS TO ROLE REPORTING_ROLE;

GRANT CREATE TABLE, CREATE VIEW,
      CREATE MATERIALIZED VIEW         ON SCHEMA ANALYTICS_DB.MARTS TO ROLE DBT_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON ALL TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DBT_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DBT_ROLE;

GRANT SELECT                           ON ALL TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_ANALYST_ROLE;
GRANT SELECT                           ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_ANALYST_ROLE;
GRANT SELECT                           ON ALL VIEWS  IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_ANALYST_ROLE;
GRANT SELECT                           ON FUTURE VIEWS IN SCHEMA ANALYTICS_DB.MARTS TO ROLE DATA_ANALYST_ROLE;

GRANT SELECT                           ON ALL TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE REPORTING_ROLE;
GRANT SELECT                           ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE REPORTING_ROLE;
GRANT SELECT                           ON ALL VIEWS  IN SCHEMA ANALYTICS_DB.MARTS TO ROLE REPORTING_ROLE;
GRANT SELECT                           ON FUTURE VIEWS IN SCHEMA ANALYTICS_DB.MARTS TO ROLE REPORTING_ROLE;

-- ML_FEATURES schema: data scientists read and write
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.ML_FEATURES TO ROLE DATA_SCIENTIST_ROLE;
GRANT CREATE TABLE                     ON SCHEMA ANALYTICS_DB.ML_FEATURES TO ROLE DATA_SCIENTIST_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON ALL TABLES IN SCHEMA ANALYTICS_DB.ML_FEATURES TO ROLE DATA_SCIENTIST_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE   ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.ML_FEATURES TO ROLE DATA_SCIENTIST_ROLE;

-- GOVERNANCE schema: only GOVERNANCE_ROLE manages policies; ACCOUNTADMIN applies them
GRANT USAGE                            ON SCHEMA ANALYTICS_DB.GOVERNANCE TO ROLE GOVERNANCE_ROLE;
GRANT CREATE TABLE, CREATE VIEW        ON SCHEMA ANALYTICS_DB.GOVERNANCE TO ROLE GOVERNANCE_ROLE;

-- =============================================================================
-- SECTION 9: WAREHOUSE GRANTS
-- =============================================================================

GRANT USAGE ON WAREHOUSE DEV_WH        TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE ON WAREHOUSE DEV_WH        TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE ON WAREHOUSE DEV_WH        TO ROLE DATA_SCIENTIST_ROLE;
GRANT USAGE ON WAREHOUSE DEV_WH        TO ROLE DBT_ROLE;

GRANT USAGE ON WAREHOUSE TRANSFORM_WH  TO ROLE DATA_ENGINEER_ROLE;
GRANT USAGE ON WAREHOUSE TRANSFORM_WH  TO ROLE DBT_ROLE;

GRANT USAGE ON WAREHOUSE ANALYTICS_WH  TO ROLE DATA_ANALYST_ROLE;
GRANT USAGE ON WAREHOUSE ANALYTICS_WH  TO ROLE DATA_SCIENTIST_ROLE;

GRANT USAGE ON WAREHOUSE REPORTING_WH  TO ROLE REPORTING_ROLE;
GRANT USAGE ON WAREHOUSE REPORTING_WH  TO ROLE DATA_ANALYST_ROLE;

-- =============================================================================
-- SECTION 10: USER CREATION EXAMPLES (COMMENTED OUT — fill in real values)
-- =============================================================================
-- Uncomment and customise when onboarding real team members.
-- Always use a strong temporary password and require reset on first login.

/*
CREATE USER IF NOT EXISTS alice_engineer
    LOGIN_NAME          = 'alice_engineer'
    DISPLAY_NAME        = 'Alice (Data Engineer)'
    EMAIL               = 'alice@yourcompany.com'
    PASSWORD            = 'TempPass123!'   -- user will change on first login
    DEFAULT_ROLE        = DATA_ENGINEER_ROLE
    DEFAULT_WAREHOUSE   = TRANSFORM_WH
    DEFAULT_NAMESPACE   = ANALYTICS_DB.STAGING
    MUST_CHANGE_PASSWORD = TRUE;

GRANT ROLE DATA_ENGINEER_ROLE TO USER alice_engineer;

CREATE USER IF NOT EXISTS bob_analyst
    LOGIN_NAME          = 'bob_analyst'
    DISPLAY_NAME        = 'Bob (Data Analyst)'
    EMAIL               = 'bob@yourcompany.com'
    PASSWORD            = 'TempPass123!'
    DEFAULT_ROLE        = DATA_ANALYST_ROLE
    DEFAULT_WAREHOUSE   = ANALYTICS_WH
    DEFAULT_NAMESPACE   = ANALYTICS_DB.MARTS
    MUST_CHANGE_PASSWORD = TRUE;

GRANT ROLE DATA_ANALYST_ROLE TO USER bob_analyst;

CREATE USER IF NOT EXISTS dbt_service_account
    LOGIN_NAME          = 'dbt_service_account'
    DISPLAY_NAME        = 'dbt Service Account'
    EMAIL               = 'platform@yourcompany.com'
    DEFAULT_ROLE        = DBT_ROLE
    DEFAULT_WAREHOUSE   = TRANSFORM_WH
    DEFAULT_NAMESPACE   = ANALYTICS_DB.STAGING
    -- Use key-pair authentication for service accounts (no password)
    RSA_PUBLIC_KEY      = '<paste_public_key_here>';

GRANT ROLE DBT_ROLE TO USER dbt_service_account;
*/

-- =============================================================================
-- SECTION 11: NETWORK POLICY (COMMENTED OUT — fill in your IP ranges)
-- =============================================================================
-- Network policies restrict which IP addresses can connect to Snowflake.
-- Create a policy with your office/VPN IP ranges, then apply it to the account
-- (or to individual users for granular control).

/*
CREATE NETWORK POLICY IF NOT EXISTS CORPORATE_NETWORK_POLICY
    ALLOWED_IP_LIST   = ('203.0.113.0/24', '198.51.100.0/24')  -- replace with real CIDRs
    BLOCKED_IP_LIST   = ()
    COMMENT           = 'Restrict access to corporate office and VPN IP ranges';

-- Apply to the account (affects all users)
ALTER ACCOUNT SET NETWORK_POLICY = CORPORATE_NETWORK_POLICY;

-- Or apply to a specific user only
-- ALTER USER alice_engineer SET NETWORK_POLICY = CORPORATE_NETWORK_POLICY;
*/

-- =============================================================================
-- SECTION 12: VERIFY SETUP
-- =============================================================================

USE ROLE SYSADMIN;

-- Show everything we created
SHOW ROLES       LIKE '%_ROLE';
SHOW WAREHOUSES;
SHOW DATABASES;

USE DATABASE ANALYTICS_DB;
SHOW SCHEMAS;

-- Verify resource monitors
USE ROLE ACCOUNTADMIN;
SHOW RESOURCE MONITORS;

-- =============================================================================
-- END OF SETUP SCRIPT
-- =============================================================================
-- Next step: open chapter_01_introduction/exercises.sql and start the course!
-- =============================================================================
