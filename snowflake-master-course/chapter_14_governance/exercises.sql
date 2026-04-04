-- =============================================================================
-- Chapter 14: Data Governance in Snowflake
-- Snowflake Master Course
-- =============================================================================
-- Covers: Tags, Masking Policies, Access History, Classification,
--         Lineage, MFA auditing, and more.
-- =============================================================================

USE ROLE   ACCOUNTADMIN;
USE DATABASE ANALYTICS;
USE SCHEMA   PUBLIC;
USE WAREHOUSE COMPUTE_WH;


-- ---------------------------------------------------------------------------
-- Exercise 1: Create classification tags
-- ---------------------------------------------------------------------------
-- PII category tag (what type of personal data is this?)
CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.PII_CATEGORY
    ALLOWED_VALUES 'EMAIL', 'PHONE', 'SSN', 'DOB', 'FULL_NAME', 'ADDRESS', 'NONE';

-- Data sensitivity classification tag
CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION
    ALLOWED_VALUES 'PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED';

-- Data owner / steward tag (free-form team name)
CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.DATA_OWNER;

-- Retention policy tag
CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.RETENTION_DAYS
    ALLOWED_VALUES '30', '90', '365', '2555', 'INDEFINITE';


-- ---------------------------------------------------------------------------
-- Exercise 2: Apply tags to columns (email, phone, ssn)
-- ---------------------------------------------------------------------------

-- Tag EMAIL column
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN EMAIL
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'EMAIL',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'CONFIDENTIAL';

-- Tag PHONE column
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN PHONE
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'PHONE',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'CONFIDENTIAL';

-- Hypothetical SSN column
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN SSN
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'SSN',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'RESTRICTED';

-- Tag FULL_NAME column
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN FULL_NAME
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'FULL_NAME',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'INTERNAL';

-- Verify
SELECT *
FROM TABLE(
    INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(
        'ANALYTICS.MARTS.DIM_CUSTOMERS',
        'table'
    )
);


-- ---------------------------------------------------------------------------
-- Exercise 3: Apply tags to tables and schemas
-- ---------------------------------------------------------------------------

-- Tag the entire DIM_CUSTOMERS table
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    SET TAG ANALYTICS.GOVERNANCE.DATA_OWNER          = 'customer-data-team',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'CONFIDENTIAL',
            ANALYTICS.GOVERNANCE.RETENTION_DAYS      = '365';

-- Tag the MARTS schema
ALTER SCHEMA ANALYTICS.MARTS
    SET TAG ANALYTICS.GOVERNANCE.DATA_OWNER          = 'data-engineering',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'INTERNAL';

-- Tag the RAW schema as restricted (contains raw PII before masking)
ALTER SCHEMA ANALYTICS.RAW
    SET TAG ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'RESTRICTED',
            ANALYTICS.GOVERNANCE.DATA_OWNER          = 'data-platform';


-- ---------------------------------------------------------------------------
-- Exercise 4: Query TAG_REFERENCES to find all PII columns
-- ---------------------------------------------------------------------------

-- All columns tagged with a PII_CATEGORY value across the account
SELECT
    TAG_DATABASE,
    TAG_SCHEMA,
    TAG_NAME,
    TAG_VALUE,
    OBJECT_DATABASE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    COLUMN_NAME,
    DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME    = 'PII_CATEGORY'
  AND TAG_VALUE  != 'NONE'
  AND DOMAIN      = 'COLUMN'
ORDER BY OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, COLUMN_NAME;

-- Summary: count of PII columns per table
SELECT
    OBJECT_DATABASE                     AS database_name,
    OBJECT_SCHEMA                       AS schema_name,
    OBJECT_NAME                         AS table_name,
    COUNT(COLUMN_NAME)                  AS pii_column_count,
    LISTAGG(TAG_VALUE, ', ')
        WITHIN GROUP (ORDER BY TAG_VALUE) AS pii_categories
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME = 'PII_CATEGORY'
  AND TAG_VALUE != 'NONE'
  AND DOMAIN    = 'COLUMN'
GROUP BY 1, 2, 3
ORDER BY pii_column_count DESC;


-- ---------------------------------------------------------------------------
-- Exercise 5: Run SYSTEM$CLASSIFY_SCHEMA
-- Automatically detect and tag PII columns in a schema
-- ---------------------------------------------------------------------------

-- Classify all tables in the MARTS schema (may take several minutes)
SELECT SYSTEM$CLASSIFY_SCHEMA(
    'ANALYTICS.MARTS',
    {
        'auto_tag': true,
        'use_cortex_classification': true
    }
);

-- Review classification suggestions before auto-applying
SELECT SYSTEM$CLASSIFY(
    'ANALYTICS.MARTS.DIM_CUSTOMERS',
    { 'use_cortex_classification': true }
);


-- ---------------------------------------------------------------------------
-- Exercise 6: Create a masking policy using tag-based logic
-- ---------------------------------------------------------------------------

-- Masking policy for string/email columns
CREATE OR REPLACE MASKING POLICY ANALYTICS.GOVERNANCE.PII_STRING_MASK
    AS (val STRING) RETURNS STRING ->
    CASE
        -- ACCOUNTADMIN and governance roles see plaintext
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'DATA_GOVERNANCE_ROLE') THEN val
        -- Data scientists see partially masked values
        WHEN CURRENT_ROLE() = 'DATA_SCIENTIST' THEN
            REGEXP_REPLACE(val, '(.{2}).*(@.*)', '\\1****\\2')
        -- Everyone else sees fully masked value
        ELSE '***MASKED***'
    END;

-- Masking policy for SSN (9-digit number stored as string)
CREATE OR REPLACE MASKING POLICY ANALYTICS.GOVERNANCE.SSN_MASK
    AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'DATA_GOVERNANCE_ROLE') THEN val
        ELSE 'XXX-XX-' || RIGHT(val, 4)   -- show last 4 only
    END;

-- Attach masking policy to EMAIL column
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN EMAIL
    SET MASKING POLICY ANALYTICS.GOVERNANCE.PII_STRING_MASK;

-- Attach SSN masking policy
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN SSN
    SET MASKING POLICY ANALYTICS.GOVERNANCE.SSN_MASK;

-- Tag-based masking policy: apply mask automatically to any column tagged
--  with DATA_CLASSIFICATION = RESTRICTED
CREATE OR REPLACE MASKING POLICY ANALYTICS.GOVERNANCE.TAG_BASED_MASK
    AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'DATA_GOVERNANCE_ROLE') THEN val
        ELSE '***RESTRICTED***'
    END;

-- Attach policy via tag (all columns with DATA_CLASSIFICATION=RESTRICTED get masked)
ALTER TAG ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION
    SET MASKING POLICY ANALYTICS.GOVERNANCE.TAG_BASED_MASK
    USING (ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION);


-- ---------------------------------------------------------------------------
-- Exercise 7: Query ACCESS_HISTORY for sensitive column access
-- ---------------------------------------------------------------------------

-- Who has accessed PII columns in the last 7 days?
SELECT
    ah.USER_NAME,
    ah.ROLE_NAME,
    ah.QUERY_START_TIME,
    ah.QUERY_ID,
    objs.value['objectName']::STRING                AS object_accessed,
    cols.value['columnName']::STRING                AS column_accessed
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY        ah,
LATERAL FLATTEN(INPUT => ah.OBJECTS_MODIFIED)      objs,
LATERAL FLATTEN(INPUT => objs.value['columns'])    cols
WHERE ah.QUERY_START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND cols.value['columnName']::STRING IN ('EMAIL', 'PHONE', 'SSN')
ORDER BY ah.QUERY_START_TIME DESC
LIMIT 100;

-- Count accesses to restricted columns by role
SELECT
    ah.ROLE_NAME,
    cols.value['columnName']::STRING                AS sensitive_column,
    COUNT(*)                                        AS access_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY        ah,
LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED) objs,
LATERAL FLATTEN(INPUT => objs.value['columns'])    cols
WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND cols.value['columnName']::STRING IN ('EMAIL', 'PHONE', 'SSN', 'FULL_NAME')
GROUP BY 1, 2
ORDER BY access_count DESC;


-- ---------------------------------------------------------------------------
-- Exercise 8: Query LOGIN_HISTORY for security audit
-- ---------------------------------------------------------------------------

-- Failed login attempts in the last 24 hours
SELECT
    EVENT_TIMESTAMP,
    USER_NAME,
    CLIENT_IP,
    ERROR_MESSAGE,
    REPORTED_CLIENT_TYPE,
    FIRST_AUTHENTICATION_FACTOR,
    SECOND_AUTHENTICATION_FACTOR
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
  AND IS_SUCCESS = 'NO'
ORDER BY EVENT_TIMESTAMP DESC;

-- Top 10 users by login frequency this month
SELECT
    USER_NAME,
    COUNT(*)                                        AS login_count,
    SUM(CASE WHEN IS_SUCCESS = 'YES' THEN 1 END)   AS successful,
    SUM(CASE WHEN IS_SUCCESS = 'NO'  THEN 1 END)   AS failed,
    MIN(EVENT_TIMESTAMP)                            AS first_login,
    MAX(EVENT_TIMESTAMP)                            AS last_login
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY USER_NAME
ORDER BY login_count DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- Exercise 9: Find users without MFA enabled
-- ---------------------------------------------------------------------------
SELECT
    NAME                                            AS user_name,
    EMAIL,
    HAS_MFA,
    LOGIN_NAME,
    DEFAULT_ROLE,
    DISABLED,
    LAST_SUCCESS_LOGIN
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE HAS_MFA    = FALSE
  AND DISABLED   = FALSE
  AND DELETED_ON IS NULL
ORDER BY LAST_SUCCESS_LOGIN DESC NULLS FIRST;

-- Users who logged in recently but still lack MFA (highest risk)
SELECT
    u.NAME,
    u.EMAIL,
    u.DEFAULT_ROLE,
    MAX(lh.EVENT_TIMESTAMP)                         AS last_login
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS        u
JOIN SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY lh
  ON lh.USER_NAME = u.NAME
 AND lh.IS_SUCCESS = 'YES'
 AND lh.EVENT_TIMESTAMP >= DATEADD('day', -30, CURRENT_TIMESTAMP())
WHERE u.HAS_MFA   = FALSE
  AND u.DISABLED  = FALSE
GROUP BY 1, 2, 3
ORDER BY last_login DESC;


-- ---------------------------------------------------------------------------
-- Exercise 10: Check data lineage via ACCESS_HISTORY
-- ---------------------------------------------------------------------------

-- What downstream objects read from DIM_CUSTOMERS?
SELECT DISTINCT
    src.value['objectName']::STRING                 AS source_object,
    tgt.value['objectName']::STRING                 AS target_object,
    ah.QUERY_ID,
    ah.QUERY_START_TIME,
    ah.USER_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY        ah,
LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED) src,
LATERAL FLATTEN(INPUT => ah.OBJECTS_MODIFIED)      tgt
WHERE src.value['objectName']::STRING ILIKE '%DIM_CUSTOMERS%'
  AND ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
ORDER BY ah.QUERY_START_TIME DESC
LIMIT 50;


-- ---------------------------------------------------------------------------
-- Exercise 11: Create a data classification report
-- ---------------------------------------------------------------------------

-- Comprehensive report: all tagged columns with masking policy status
SELECT
    tr.OBJECT_DATABASE                              AS database_name,
    tr.OBJECT_SCHEMA                                AS schema_name,
    tr.OBJECT_NAME                                  AS table_name,
    tr.COLUMN_NAME,
    MAX(CASE WHEN tr.TAG_NAME = 'PII_CATEGORY'       THEN tr.TAG_VALUE END) AS pii_category,
    MAX(CASE WHEN tr.TAG_NAME = 'DATA_CLASSIFICATION' THEN tr.TAG_VALUE END) AS classification,
    MAX(CASE WHEN tr.TAG_NAME = 'DATA_OWNER'          THEN tr.TAG_VALUE END) AS data_owner,
    -- Check if a masking policy is applied
    mp.POLICY_NAME                                  AS masking_policy
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES     tr
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES mp
    ON  mp.REF_DATABASE_NAME = tr.OBJECT_DATABASE
    AND mp.REF_SCHEMA_NAME   = tr.OBJECT_SCHEMA
    AND mp.REF_ENTITY_NAME   = tr.OBJECT_NAME
    AND mp.REF_COLUMN_NAME   = tr.COLUMN_NAME
    AND mp.POLICY_KIND       = 'MASKING_POLICY'
WHERE tr.DOMAIN = 'COLUMN'
GROUP BY 1, 2, 3, 4, mp.POLICY_NAME
ORDER BY 1, 2, 3, 4;


-- ---------------------------------------------------------------------------
-- Exercise 12: Grant SELECT on SNOWFLAKE.ACCOUNT_USAGE to a governance role
-- ---------------------------------------------------------------------------

-- Create the governance role (if not already created)
CREATE ROLE IF NOT EXISTS DATA_GOVERNANCE_ROLE;

-- Grant access to Account Usage schema (gives read-only visibility into
-- query history, access logs, login history, etc.)
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE
    TO ROLE DATA_GOVERNANCE_ROLE;

-- Grant the governance role permission to manage tags and masking policies
GRANT USAGE ON DATABASE  ANALYTICS                TO ROLE DATA_GOVERNANCE_ROLE;
GRANT USAGE ON SCHEMA    ANALYTICS.GOVERNANCE     TO ROLE DATA_GOVERNANCE_ROLE;
GRANT ALL   ON ALL TAGS  IN SCHEMA ANALYTICS.GOVERNANCE TO ROLE DATA_GOVERNANCE_ROLE;
GRANT ALL   ON ALL MASKING POLICIES IN SCHEMA ANALYTICS.GOVERNANCE TO ROLE DATA_GOVERNANCE_ROLE;

-- Allow governance role to apply tags to any object in the database
GRANT APPLY TAG ON ACCOUNT TO ROLE DATA_GOVERNANCE_ROLE;

-- Grant governance role to a specific user
GRANT ROLE DATA_GOVERNANCE_ROLE TO USER your_governance_admin;

-- Verify the role's privileges
SHOW GRANTS TO ROLE DATA_GOVERNANCE_ROLE;
