-- =============================================================================
-- FILE: chapter_10_sharing/exercises.sql
-- TOPIC: Secure Data Sharing — Shares, Consumers, Reader Accounts
-- COURSE: Snowflake Master Course | Chapter 10
-- =============================================================================
-- Snowflake Secure Data Sharing lets you share live data across accounts
-- with ZERO data copying. The consumer queries your data in your storage —
-- they only pay for their compute.
--
-- Architecture:
--   Provider account  -> creates a SHARE
--   Consumer account  -> creates a DATABASE FROM SHARE
--   Data flows:        only the query result leaves the provider's storage
--
-- Snowflake Marketplace is built on the same sharing primitives.
-- =============================================================================

USE ROLE ACCOUNTADMIN;   -- Data sharing requires ACCOUNTADMIN
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   MARTS;

-- =============================================================================
-- SETUP: Create objects to share
-- =============================================================================

-- Create a shareable summary table in MARTS
CREATE OR REPLACE TABLE shared_sales_summary (
    revenue_month DATE,
    region        VARCHAR(50),
    total_revenue NUMBER(18, 2),
    order_count   NUMBER,
    avg_order     NUMBER(12, 2)
)
COMMENT = 'Aggregated sales data — safe to share with partners (no PII)';

INSERT INTO shared_sales_summary
SELECT DATE_TRUNC('month', sale_date),
       region,
       SUM(revenue),
       COUNT(*),
       ROUND(AVG(revenue), 2)
FROM   ANALYTICS_DB.STAGING.daily_sales
GROUP  BY 1, 2;

-- Create a secure view for sharing (hides query logic from consumer)
CREATE OR REPLACE SECURE VIEW shared_kpi_view AS
SELECT revenue_month,
       region,
       total_revenue,
       order_count,
       ROUND(100.0 * total_revenue / SUM(total_revenue) OVER (PARTITION BY revenue_month), 2) AS pct_of_month
FROM   shared_sales_summary;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create a share object
-- WHY IT MATTERS: A SHARE is the container that holds references to objects
--                 you want to expose to consumer accounts. The SHARE itself
--                 does not copy data — it creates a pointer.
-- =============================================================================

-- Create the share (name must be unique within the account)
CREATE SHARE IF NOT EXISTS partner_sales_share
    COMMENT = 'Monthly sales summary share for strategic partner accounts';

-- Verify the share was created
SHOW SHARES;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Grant database, schema, and table/view privileges to the share
-- WHY IT MATTERS: Like roles, shares need USAGE at each level of the hierarchy:
--                 Database -> Schema -> Objects.
--                 You cannot grant SELECT directly without USAGE on the container.
-- =============================================================================

-- Step 1: Grant USAGE on the database to the share
GRANT USAGE ON DATABASE ANALYTICS_DB TO SHARE partner_sales_share;

-- Step 2: Grant USAGE on the specific schema(s) to share
GRANT USAGE ON SCHEMA ANALYTICS_DB.MARTS TO SHARE partner_sales_share;

-- Step 3: Grant SELECT on specific tables/views to the share
GRANT SELECT ON TABLE ANALYTICS_DB.MARTS.shared_sales_summary TO SHARE partner_sales_share;
GRANT SELECT ON VIEW  ANALYTICS_DB.MARTS.shared_kpi_view       TO SHARE partner_sales_share;

-- Verify grants on the share
SHOW GRANTS TO SHARE partner_sales_share;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Add a consumer account to the share
-- WHY IT MATTERS: Until you add a consumer account, the share is created but
--                 not accessible by anyone. Each consumer is identified by their
--                 Snowflake account identifier.
-- =============================================================================

-- Add a consumer account (replace with real account identifier)
-- Account identifier format: <org_name>.<account_name>  (new format)
-- or  <account_locator>.<region>.<cloud>               (legacy format)

-- New org-based format (preferred):
-- ALTER SHARE partner_sales_share ADD ACCOUNTS = myorg.partner_account_name;

-- Legacy locator format:
-- ALTER SHARE partner_sales_share ADD ACCOUNTS = xy98765.us-east-1.aws;

-- Add multiple consumer accounts at once:
-- ALTER SHARE partner_sales_share
--     ADD ACCOUNTS = myorg.partner_a, myorg.partner_b;

-- Allow consumers from any Snowflake account to discover and request this share
-- (Snowflake Marketplace / Data Exchange mode):
-- ALTER SHARE partner_sales_share SET SHARE_RESTRICTIONS = FALSE;

SELECT 'Replace placeholder account IDs with real Snowflake account identifiers.' AS note;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Show all shares — both outbound (I created) and inbound (shared to me)
-- WHY IT MATTERS: SHOW SHARES gives a complete picture of both sides of your
--                 sharing relationships. Use it to audit active shares regularly.
-- =============================================================================

-- Show all shares (inbound and outbound)
SHOW SHARES;

-- Filter to only shares you have created (outbound)
SELECT "kind",
       "name"        AS share_name,
       "database_name",
       "to"          AS consumer_accounts,
       "owner",
       "comment",
       "created_on"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE  "kind" = 'OUTBOUND';

-- Show inbound shares (shared TO your account from another provider)
SELECT "kind",
       "name",
       "owner_account",
       "comment",
       "created_on"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE  "kind" = 'INBOUND';

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Show grants to a share — inspect what objects are included
-- WHY IT MATTERS: As the share grows over time, you need to audit exactly
--                 which objects and which consumers have access.
-- =============================================================================

-- Detailed list of all grants to the share
SHOW GRANTS TO SHARE partner_sales_share;

-- Query ACCOUNT_USAGE for comprehensive sharing audit
SELECT share_name,
       object_name,
       object_kind,
       granted_to,
       grant_option,
       created_on
FROM   SNOWFLAKE.ACCOUNT_USAGE.SHARES
WHERE  share_name = 'PARTNER_SALES_SHARE'
ORDER  BY created_on;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Create a database from a share (consumer side)
-- WHY IT MATTERS: This is what the CONSUMER runs in their own account.
--                 The database they create is a live, read-only window into
--                 the provider's data — no ETL, no duplication.
-- =============================================================================

-- CONSUMER SIDE (run this in the consumer account, not the provider account)
-- Replace PROVIDER_ACCOUNT with the actual provider account identifier

-- From the consumer account:
-- CREATE DATABASE partner_data
--     FROM SHARE PROVIDER_ACCOUNT.partner_sales_share
--     COMMENT = 'Live data feed from strategic partner — do not modify';

-- Grant the shared database to an analyst role in the consumer account:
-- GRANT IMPORTED PRIVILEGES ON DATABASE partner_data TO ROLE DATA_ANALYST_ROLE;

-- Query the shared data (consumer pays their own compute, reads provider's storage):
-- SELECT * FROM partner_data.MARTS.shared_kpi_view LIMIT 10;

-- The data is always current — no refresh jobs needed
-- If the provider inserts a new row, the consumer sees it immediately

SELECT 'Consumer-side commands shown in comments above.' AS note;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Create a reader account (managed account for non-Snowflake customers)
-- WHY IT MATTERS: Reader accounts let you share data with parties who do not
--                 have a Snowflake account. You create and manage the account
--                 for them; they pay no Snowflake fees (you pay compute on their behalf).
-- =============================================================================

-- Create a reader (managed) account for a partner who doesn't have Snowflake
-- REQUIRES: ACCOUNTADMIN
-- NOTE: Reader account names must be globally unique within your org

/*
CREATE MANAGED ACCOUNT partner_reader_account
    ADMIN_NAME    = 'reader_admin'
    ADMIN_PASSWORD = 'TempReaderPass123!'   -- reader admin will change this on first login
    TYPE          = READER
    COMMENT       = 'Managed reader account for Acme Corp — no Snowflake license needed';

-- The result shows the reader account's login URL and locator
-- Share that URL with the reader account user

-- Add the reader account to the share
ALTER SHARE partner_sales_share
    ADD ACCOUNTS = <reader_account_locator>;
*/

-- List all managed accounts you have created
SHOW MANAGED ACCOUNTS;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Revoke an object from a share
-- WHY IT MATTERS: When data agreements change (e.g., a partner contract ends),
--                 you need to quickly and cleanly remove their access.
--                 Revoking takes effect immediately — no waiting for ETL jobs.
-- =============================================================================

-- Revoke SELECT on the KPI view (stop sharing just that object)
REVOKE SELECT ON VIEW ANALYTICS_DB.MARTS.shared_kpi_view FROM SHARE partner_sales_share;

-- Verify the view is no longer in the share
SHOW GRANTS TO SHARE partner_sales_share;

-- Revoke schema access (removes all objects in that schema from the share)
-- REVOKE USAGE ON SCHEMA ANALYTICS_DB.MARTS FROM SHARE partner_sales_share;

-- Revoke a specific consumer account (remove just that consumer, keep the share)
-- ALTER SHARE partner_sales_share REMOVE ACCOUNTS = myorg.partner_account_name;

-- Re-grant the view if needed (for exercise continuity)
GRANT SELECT ON VIEW ANALYTICS_DB.MARTS.shared_kpi_view TO SHARE partner_sales_share;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Drop a share
-- WHY IT MATTERS: When a data sharing agreement ends entirely, DROP SHARE
--                 immediately and cleanly removes all consumer access.
--                 Consumers immediately lose the ability to query the data.
-- =============================================================================

-- Before dropping a share, first remove all consumer accounts
-- ALTER SHARE partner_sales_share REMOVE ACCOUNTS = myorg.partner_a;

-- Then drop the share
-- DROP SHARE partner_sales_share;

-- Verify it is gone
-- SHOW SHARES;

-- For this exercise, we keep the share active
SELECT 'DROP SHARE syntax shown in comments above — share kept for query in Exercise 10.' AS note;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Query ACCOUNT_USAGE for share usage statistics
-- WHY IT MATTERS: Monitoring share usage lets you understand which consumers
--                 are actively using your data, how often they query it, and
--                 what compute costs they incur (for reader accounts, you pay).
-- =============================================================================

-- Which consumers are querying your shared data?
SELECT share_name,
       consumer_account_name,
       consumer_organization_name,
       query_count,
       bytes_sent,
       credits_used_by_reader_accounts,
       start_time,
       end_time
FROM   SNOWFLAKE.ACCOUNT_USAGE.DATA_TRANSFER_HISTORY
WHERE  start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
ORDER  BY start_time DESC
LIMIT  50;

-- Credit consumption for reader accounts (you pay their compute)
SELECT reader_account_name,
       SUM(credits_used) AS total_credits_charged_to_provider
FROM   SNOWFLAKE.ACCOUNT_USAGE.READER_ACCOUNT_USAGE_HISTORY
WHERE  start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP  BY 1
ORDER  BY 2 DESC;

-- Shares metadata from ACCOUNT_USAGE
SELECT name           AS share_name,
       owner,
       kind,
       comment,
       created_on,
       deleted_on
FROM   SNOWFLAKE.ACCOUNT_USAGE.SHARES
WHERE  kind      = 'OUTBOUND'
  AND  deleted_on IS NULL
ORDER  BY created_on;

-- =============================================================================
-- CLEANUP (optional)
-- =============================================================================
-- DROP SHARE IF EXISTS partner_sales_share;
-- DROP TABLE IF EXISTS ANALYTICS_DB.MARTS.shared_sales_summary;
-- DROP VIEW IF EXISTS ANALYTICS_DB.MARTS.shared_kpi_view;

-- =============================================================================
-- END OF CHAPTER 10 EXERCISES
-- =============================================================================
