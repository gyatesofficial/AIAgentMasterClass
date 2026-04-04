-- =============================================================================
-- FILE: chapter_08_security/exercises.sql
-- TOPIC: Security & RBAC — Roles, Masking, Row Access, Network Policies
-- COURSE: Snowflake Master Course | Chapter 8
-- =============================================================================
-- Snowflake has enterprise-grade security built into the platform:
--   RBAC            — Role-based access control for all objects
--   DAC             — Discretionary access control (owner can grant to others)
--   Column-level    — Masking policies hide sensitive columns per role
--   Row-level       — Row access policies filter rows based on user context
--   Network         — IP allowlist/denylist for login control
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   GOVERNANCE;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Create functional roles and establish a role hierarchy
-- WHY IT MATTERS: Role hierarchies in Snowflake follow a DAG (Directed Acyclic
--                 Graph). Granting role A to role B means B inherits all of A's
--                 privileges. Design hierarchies top-down by job function.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Application-specific roles (not yet in our setup script — useful for a specific app)
CREATE ROLE IF NOT EXISTS APP_READER_ROLE
    COMMENT = 'Read-only access for the reporting application service account';

CREATE ROLE IF NOT EXISTS APP_WRITER_ROLE
    COMMENT = 'Read/write access for the application backend service account';

-- Establish hierarchy: writer inherits reader, reader inherits PUBLIC
GRANT ROLE APP_READER_ROLE TO ROLE APP_WRITER_ROLE;
GRANT ROLE APP_WRITER_ROLE TO ROLE SYSADMIN;   -- SYSADMIN manages app roles
GRANT ROLE APP_READER_ROLE TO ROLE SYSADMIN;

-- Verify the role graph
SHOW GRANTS ON ROLE APP_WRITER_ROLE;
SHOW GRANTS ON ROLE APP_READER_ROLE;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Create a user example (commented — fill in real values)
-- WHY IT MATTERS: Users are the login identities in Snowflake. Best practices:
--                 - Assign a DEFAULT_ROLE that is least-privilege
--                 - Use MUST_CHANGE_PASSWORD for human users
--                 - Use RSA key-pair auth for service accounts (no password)
-- =============================================================================

-- Human user example (uncomment and customise)
/*
CREATE USER IF NOT EXISTS john_doe
    LOGIN_NAME            = 'john_doe'
    DISPLAY_NAME          = 'John Doe'
    EMAIL                 = 'john.doe@yourcompany.com'
    PASSWORD              = 'TempPassword123!'
    DEFAULT_ROLE          = DATA_ANALYST_ROLE
    DEFAULT_WAREHOUSE     = ANALYTICS_WH
    DEFAULT_NAMESPACE     = ANALYTICS_DB.MARTS
    MUST_CHANGE_PASSWORD  = TRUE
    COMMENT               = 'Data Analyst — Finance team';

GRANT ROLE DATA_ANALYST_ROLE TO USER john_doe;
*/

-- Service account with key-pair authentication (no password — more secure)
/*
CREATE USER IF NOT EXISTS svc_reporting_app
    LOGIN_NAME            = 'svc_reporting_app'
    DISPLAY_NAME          = 'Reporting App Service Account'
    DEFAULT_ROLE          = APP_READER_ROLE
    DEFAULT_WAREHOUSE     = REPORTING_WH
    DEFAULT_NAMESPACE     = ANALYTICS_DB.MARTS
    RSA_PUBLIC_KEY        = '<paste_base64_encoded_public_key_here>'
    COMMENT               = 'Service account for Tableau/Power BI connections';

GRANT ROLE APP_READER_ROLE TO USER svc_reporting_app;
*/

SELECT 'Review user creation comments above.' AS note;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Grant database, schema, and table privileges
-- WHY IT MATTERS: In Snowflake, you must grant privileges at EACH level:
--                 Account (warehouse) > Database > Schema > Object.
--                 Missing any level breaks the privilege chain.
-- =============================================================================

USE ROLE SYSADMIN;

-- Grant the minimum needed for APP_READER_ROLE to read MARTS tables
GRANT USAGE ON WAREHOUSE REPORTING_WH          TO ROLE APP_READER_ROLE;
GRANT USAGE ON DATABASE  ANALYTICS_DB          TO ROLE APP_READER_ROLE;
GRANT USAGE ON SCHEMA    ANALYTICS_DB.MARTS    TO ROLE APP_READER_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA ANALYTICS_DB.MARTS    TO ROLE APP_READER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA ANALYTICS_DB.MARTS TO ROLE APP_READER_ROLE;
GRANT SELECT ON ALL VIEWS  IN SCHEMA ANALYTICS_DB.MARTS    TO ROLE APP_READER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA ANALYTICS_DB.MARTS  TO ROLE APP_READER_ROLE;

-- Grant APP_WRITER_ROLE insert/update on STAGING (inherits reader's grants)
GRANT USAGE ON SCHEMA    ANALYTICS_DB.STAGING    TO ROLE APP_WRITER_ROLE;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ANALYTICS_DB.STAGING TO ROLE APP_WRITER_ROLE;

-- Verify grants
SHOW GRANTS TO ROLE APP_READER_ROLE;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: SHOW GRANTS — inspect who has access to what
-- WHY IT MATTERS: SHOW GRANTS is the most important command for access auditing.
--                 You can query grants on any object or to any role/user.
-- =============================================================================

-- What privileges does APP_READER_ROLE have?
SHOW GRANTS TO ROLE APP_READER_ROLE;

-- What roles are granted to DATA_ENGINEER_ROLE? (its privilege chain)
SHOW GRANTS TO ROLE DATA_ENGINEER_ROLE;

-- Who has been granted the DATA_ANALYST_ROLE?
SHOW GRANTS OF ROLE DATA_ANALYST_ROLE;

-- What privileges exist on the ANALYTICS_DB database?
SHOW GRANTS ON DATABASE ANALYTICS_DB;

-- What privileges exist on the MARTS schema?
SHOW GRANTS ON SCHEMA ANALYTICS_DB.MARTS;

-- Comprehensive: query ACCOUNT_USAGE for a full privilege audit
USE ROLE ACCOUNTADMIN;
SELECT grantee_name,
       granted_on,
       name         AS object_name,
       privilege,
       granted_by,
       created_on
FROM   SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE  deleted_on IS NULL
  AND  grantee_name = 'APP_READER_ROLE'
ORDER  BY granted_on;
USE ROLE SYSADMIN;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: Create and apply an email masking policy
-- WHY IT MATTERS: Masking policies apply column-level security — analysts see
--                 masked values, privileged roles see the real data. The mask
--                 is enforced at query time, not at storage time.
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE SCHEMA ANALYTICS_DB.GOVERNANCE;

-- Create a masking policy that hides email addresses for non-privileged roles
CREATE OR REPLACE MASKING POLICY mp_email_mask
    AS (email_val VARCHAR) RETURNS VARCHAR ->
    CASE
        WHEN CURRENT_ROLE() IN ('DATA_ENGINEER_ROLE', 'ACCOUNTADMIN', 'SYSADMIN')
            THEN email_val                          -- real email for privileged roles
        WHEN CURRENT_ROLE() IN ('DATA_ANALYST_ROLE', 'DBT_ROLE')
            THEN REGEXP_REPLACE(email_val,          -- show domain, hide local part
                    '^[^@]+', '****')
        ELSE '****@****.***'                        -- fully masked for all other roles
    END
    COMMENT = 'Masks email addresses based on caller role';

-- Apply the masking policy to the email column in perm_customers
ALTER TABLE ANALYTICS_DB.STAGING.perm_customers
    MODIFY COLUMN email
    SET MASKING POLICY ANALYTICS_DB.GOVERNANCE.mp_email_mask;

-- Test the policy as DATA_ENGINEER_ROLE (should see real email)
USE ROLE DATA_ENGINEER_ROLE;
SELECT customer_id, full_name, email FROM ANALYTICS_DB.STAGING.perm_customers LIMIT 5;

-- Test as DATA_ANALYST_ROLE (should see ****@domain.com)
USE ROLE DATA_ANALYST_ROLE;
SELECT customer_id, full_name, email FROM ANALYTICS_DB.STAGING.perm_customers LIMIT 5;

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Create a masking policy for phone numbers
-- WHY IT MATTERS: Different PII types need different masking strategies.
--                 Phone numbers are often partially masked (last 4 visible)
--                 rather than fully hidden.
-- =============================================================================

USE SCHEMA ANALYTICS_DB.GOVERNANCE;

CREATE OR REPLACE MASKING POLICY mp_phone_mask
    AS (phone_val VARCHAR) RETURNS VARCHAR ->
    CASE
        WHEN CURRENT_ROLE() IN ('DATA_ENGINEER_ROLE', 'ACCOUNTADMIN', 'SYSADMIN')
            THEN phone_val                          -- full number for privileged roles
        WHEN CURRENT_ROLE() IN ('DATA_ANALYST_ROLE')
            THEN REGEXP_REPLACE(phone_val,         -- show only last 4 digits
                    '[0-9](?=[0-9]{4})', '*')       -- e.g., +1-***-***-1234
        ELSE '***-***-****'                         -- fully masked
    END
    COMMENT = 'Masks phone numbers — last 4 digits visible to analysts';

-- Apply to a hypothetical customers table phone column
-- ALTER TABLE ANALYTICS_DB.STAGING.customers
--     MODIFY COLUMN phone_number
--     SET MASKING POLICY ANALYTICS_DB.GOVERNANCE.mp_phone_mask;

SHOW MASKING POLICIES IN SCHEMA ANALYTICS_DB.GOVERNANCE;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Create a row access policy
-- WHY IT MATTERS: Row access policies filter the rows a user can see based
--                 on their role or any session context variable.
--                 Use case: regional teams only see their region's data.
-- =============================================================================

USE SCHEMA ANALYTICS_DB.GOVERNANCE;

-- Create a mapping table that maps roles to allowed regions
CREATE OR REPLACE TABLE row_access_region_map (
    role_name  VARCHAR(100),
    region     VARCHAR(50)
);

INSERT INTO row_access_region_map VALUES
    ('DATA_ENGINEER_ROLE',  'Americas'),
    ('DATA_ENGINEER_ROLE',  'EMEA'),
    ('DATA_ENGINEER_ROLE',  'APAC'),
    ('DATA_ANALYST_ROLE',   'Americas'),       -- Americas analyst
    ('REPORTING_ROLE',      'Americas'),
    ('REPORTING_ROLE',      'EMEA'),
    ('SYSADMIN',            'Americas'),
    ('SYSADMIN',            'EMEA'),
    ('SYSADMIN',            'APAC'),
    ('ACCOUNTADMIN',        'Americas'),
    ('ACCOUNTADMIN',        'EMEA'),
    ('ACCOUNTADMIN',        'APAC');

-- Row access policy: only return rows where the region is in the caller's allowed list
CREATE OR REPLACE ROW ACCESS POLICY rap_region_filter
    ON ANALYTICS_DB.STAGING.daily_sales (region)
    AS (region_val VARCHAR) RETURNS BOOLEAN ->
    EXISTS (
        SELECT 1
        FROM   ANALYTICS_DB.GOVERNANCE.row_access_region_map m
        WHERE  m.role_name = CURRENT_ROLE()
          AND  m.region    = region_val
    )
    COMMENT = 'Filter rows by region based on caller role';

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Apply a row access policy to a table
-- WHY IT MATTERS: The policy itself does nothing until applied to a table.
--                 You can apply one policy to multiple tables.
-- =============================================================================

-- Apply the row access policy to daily_sales
ALTER TABLE ANALYTICS_DB.STAGING.daily_sales
    ADD ROW ACCESS POLICY ANALYTICS_DB.GOVERNANCE.rap_region_filter
    ON (region);

-- Test: DATA_ANALYST_ROLE should only see Americas
USE ROLE DATA_ANALYST_ROLE;
SELECT DISTINCT region FROM ANALYTICS_DB.STAGING.daily_sales ORDER BY 1;
-- Expected: only 'Americas' (based on the mapping table above)

-- Test: DATA_ENGINEER_ROLE should see all regions
USE ROLE DATA_ENGINEER_ROLE;
SELECT DISTINCT region FROM ANALYTICS_DB.STAGING.daily_sales ORDER BY 1;
-- Expected: Americas, APAC, EMEA

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Network policy syntax (commented — requires real IP ranges)
-- WHY IT MATTERS: Network policies are your first line of defence.
--                 They prevent anyone from an unknown IP from connecting,
--                 even with valid credentials.
-- =============================================================================

-- Create a network policy allowing office and VPN IPs only
-- REPLACE THE IP ADDRESSES BELOW WITH YOUR ACTUAL CIDRs

/*
CREATE NETWORK POLICY IF NOT EXISTS CORPORATE_POLICY
    ALLOWED_IP_LIST = (
        '203.0.113.0/24',     -- Corporate office (replace with real CIDR)
        '198.51.100.50/32',   -- VPN gateway (replace with real IP)
        '192.0.2.0/28'        -- CI/CD runner IP range (replace with real CIDR)
    )
    BLOCKED_IP_LIST = ()      -- explicitly block nothing (allowlist-only approach)
    COMMENT         = 'Corporate access policy — office and VPN only';

-- Apply to the account (all users)
ALTER ACCOUNT SET NETWORK_POLICY = CORPORATE_POLICY;

-- Override for a specific user (e.g., remote contractor with fixed IP)
ALTER USER contractor_alex SET NETWORK_POLICY = CONTRACTOR_POLICY;

-- Remove from account
-- ALTER ACCOUNT UNSET NETWORK_POLICY;
*/

SHOW NETWORK POLICIES;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Enable MFA for a user (instructions)
-- WHY IT MATTERS: MFA prevents credential stuffing and phishing attacks.
--                 Snowflake supports TOTP (time-based one-time password) via
--                 Google Authenticator, Okta, or any TOTP app.
-- =============================================================================

-- MFA enrollment is done by the USER (not an admin):
--   1. User logs in to the Snowflake web UI
--   2. Goes to: avatar menu → Profile → Multi-Factor Authentication
--   3. Scans the QR code with an authenticator app
--   4. Enters the 6-digit code to verify
--
-- Account admins can REQUIRE MFA for specific users:
--   ALTER USER john_doe SET MINS_TO_BYPASS_MFA = 0;  -- no bypass allowed
--
-- Bypass MFA for a service account (should use key-pair auth instead):
--   ALTER USER svc_reporting_app SET DISABLE_MFA = TRUE;
--
-- Check MFA status for all users:
USE ROLE ACCOUNTADMIN;
SELECT name, login_name, mfa_enrolled, created_on, last_success_login
FROM   SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE  deleted_on IS NULL
ORDER  BY last_success_login DESC NULLS LAST;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Create a security integration (SAML SSO example)
-- WHY IT MATTERS: Security integrations connect Snowflake to external IdPs
--                 (Okta, Azure AD, PingFederate) for SSO authentication.
--                 This eliminates per-user passwords entirely.
-- =============================================================================

-- SAML 2.0 integration with Okta (replace with real SSO metadata URL)
/*
CREATE SECURITY INTEGRATION IF NOT EXISTS OKTA_SSO
    TYPE                   = SAML2
    ENABLED                = TRUE
    SAML2_ISSUER           = 'http://www.okta.com/your_app_id'
    SAML2_SSO_URL          = 'https://yourcompany.okta.com/app/snowflake/your_app_id/sso/saml'
    SAML2_PROVIDER         = 'OKTA'
    SAML2_X509_CERT        = '<base64_encoded_cert_from_okta>'
    SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = 'Login with Okta'
    SAML2_ENABLE_SP_INITIATED = TRUE
    COMMENT                = 'Okta SAML SSO integration for Snowflake login';
*/

-- OAuth integration for partner tools (e.g., Tableau)
/*
CREATE SECURITY INTEGRATION IF NOT EXISTS TABLEAU_OAUTH
    TYPE                  = OAUTH
    ENABLED               = TRUE
    OAUTH_CLIENT          = TABLEAU_DESKTOP
    OAUTH_ISSUE_REFRESH_TOKENS = TRUE
    OAUTH_REFRESH_TOKEN_VALIDITY = 7776000   -- 90 days in seconds
    COMMENT               = 'OAuth integration for Tableau Desktop';
*/

SHOW SECURITY INTEGRATIONS;

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Test masking by switching roles
-- WHY IT MATTERS: Always verify masking policies work BEFORE applying them
--                 to production tables. Role-switching within a session makes
--                 this testing fast and repeatable.
-- =============================================================================

USE DATABASE ANALYTICS_DB;
USE SCHEMA STAGING;

-- As SYSADMIN (should see real email — role is in privileged list)
USE ROLE SYSADMIN;
SELECT customer_id, full_name, email FROM perm_customers LIMIT 3;

-- As DATA_ENGINEER_ROLE (real email)
USE ROLE DATA_ENGINEER_ROLE;
SELECT customer_id, full_name, email FROM perm_customers LIMIT 3;

-- As DATA_ANALYST_ROLE (partially masked — ****@domain.com)
USE ROLE DATA_ANALYST_ROLE;
SELECT customer_id, full_name, email FROM perm_customers LIMIT 3;

-- As REPORTING_ROLE (fully masked)
USE ROLE REPORTING_ROLE;
SELECT customer_id, full_name, email FROM perm_customers LIMIT 3;

-- Return to ACCOUNTADMIN
USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Query POLICY_REFERENCES to see all applied policies
-- WHY IT MATTERS: As your data platform grows, it becomes critical to know
--                 WHICH policies are applied to WHICH objects.
--                 POLICY_REFERENCES is the audit view for this.
-- =============================================================================

-- Find all objects with masking policies applied
SELECT policy_name,
       policy_kind,
       ref_entity_name,
       ref_entity_domain,
       ref_column_name,
       ref_arg_column_names,
       policy_status
FROM   TABLE(ANALYTICS_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
               POLICY_NAME => 'ANALYTICS_DB.GOVERNANCE.MP_EMAIL_MASK'
             ));

-- Find all policies on a specific table
SELECT policy_name,
       policy_kind,
       ref_column_name,
       policy_status
FROM   TABLE(ANALYTICS_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
               REF_ENTITY_NAME   => 'ANALYTICS_DB.STAGING.PERM_CUSTOMERS',
               REF_ENTITY_DOMAIN => 'TABLE'
             ));

-- Account-wide policy reference view (ACCOUNT_USAGE — ~45 min latency)
SELECT policy_name,
       policy_kind,
       ref_entity_name,
       ref_column_name
FROM   SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE  policy_status = 'ACTIVE'
ORDER  BY policy_name, ref_entity_name;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Create a session policy to enforce timeout settings
-- WHY IT MATTERS: Session policies set idle/UI timeout limits per user or role.
--                 Shorter timeouts reduce the window for stolen session exploits.
-- =============================================================================

USE SCHEMA ANALYTICS_DB.GOVERNANCE;

-- Session policy: 30-min idle timeout for analyst users
CREATE OR REPLACE SESSION POLICY sp_analyst_session
    SESSION_IDLE_TIMEOUT_MINS   = 30
    SESSION_UI_IDLE_TIMEOUT_MINS = 15
    COMMENT = 'Enforce 30-minute idle timeout for DATA_ANALYST_ROLE users';

-- Apply session policy to a role (affects all users assigned that role)
-- ALTER ROLE DATA_ANALYST_ROLE SET SESSION POLICY sp_analyst_session;

-- Session policy for service accounts (long timeout — don't interrupt pipelines)
CREATE OR REPLACE SESSION POLICY sp_service_account_session
    SESSION_IDLE_TIMEOUT_MINS   = 240   -- 4-hour timeout for long-running pipelines
    SESSION_UI_IDLE_TIMEOUT_MINS = 240
    COMMENT = 'Session policy for service accounts running long ETL pipelines';

SHOW SESSION POLICIES;

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: Audit — query LOGIN_HISTORY for failed login attempts
-- WHY IT MATTERS: Failed logins can signal brute-force attacks, credential
--                 stuffing, or mis-configured service accounts.
--                 Login history is retained for 365 days in ACCOUNT_USAGE.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- Failed logins in the last 7 days
SELECT event_timestamp,
       user_name,
       client_ip,
       reported_client_type,
       first_authentication_factor,
       error_message
FROM   SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE  event_timestamp >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  is_success = 'NO'
ORDER  BY event_timestamp DESC
LIMIT  50;

-- Summary: top offending IPs (potential brute force sources)
SELECT client_ip,
       COUNT(*) AS failed_attempts,
       COUNT(DISTINCT user_name) AS distinct_users_targeted,
       MIN(event_timestamp) AS first_attempt,
       MAX(event_timestamp) AS last_attempt
FROM   SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE  event_timestamp >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND  is_success = 'NO'
GROUP  BY client_ip
ORDER  BY failed_attempts DESC
LIMIT  20;

-- Suspicious: successful login from a new IP for a user who normally uses one IP
WITH user_ips AS (
    SELECT user_name,
           client_ip,
           COUNT(*) AS login_count,
           DENSE_RANK() OVER (PARTITION BY user_name ORDER BY COUNT(*) DESC) AS ip_rank
    FROM   SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
    WHERE  event_timestamp >= DATEADD('day', -90, CURRENT_TIMESTAMP())
      AND  is_success = 'YES'
    GROUP  BY 1, 2
)
SELECT user_name, client_ip, login_count
FROM   user_ips
WHERE  ip_rank > 5          -- flag IPs that are not in a user's top 5 usual IPs
ORDER  BY user_name, login_count;

USE ROLE SYSADMIN;

-- =============================================================================
-- END OF CHAPTER 8 EXERCISES
-- =============================================================================
