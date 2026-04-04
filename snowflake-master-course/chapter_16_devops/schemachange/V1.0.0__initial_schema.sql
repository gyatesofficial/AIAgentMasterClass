-- =============================================================================
-- schemachange Migration V1.0.0 – Initial Schema
-- Snowflake Master Course | Chapter 16
-- =============================================================================
-- This migration creates the foundational database objects for the analytics
-- platform. Run once in a pristine environment.
--
-- Author:    data-platform-team
-- Date:      2024-01-15
-- Ticket:    DATA-001
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE COMPUTE_WH;

-- ── Databases ─────────────────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS ANALYTICS
    DATA_RETENTION_TIME_IN_DAYS = 14
    COMMENT = 'Primary analytics database';

-- ── Schemas ───────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS ANALYTICS.RAW
    COMMENT = 'Raw ingestion layer – source data arrives here unmodified';

CREATE SCHEMA IF NOT EXISTS ANALYTICS.STAGING
    COMMENT = 'Cleaned / typed staging models (dbt stg_ views)';

CREATE SCHEMA IF NOT EXISTS ANALYTICS.MARTS
    COMMENT = 'Business-ready dimensional models (dim_ and fct_ tables)';

CREATE SCHEMA IF NOT EXISTS ANALYTICS.GOVERNANCE
    COMMENT = 'Data governance objects: tags, masking policies, row access policies';

-- ── Warehouses ────────────────────────────────────────────────────────────────
CREATE WAREHOUSE IF NOT EXISTS TRANSFORM_WH
    WAREHOUSE_SIZE        = 'SMALL'
    AUTO_SUSPEND          = 120
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    COMMENT = 'Used by dbt and ELT pipelines';

CREATE WAREHOUSE IF NOT EXISTS ANALYTICS_WH
    WAREHOUSE_SIZE        = 'MEDIUM'
    AUTO_SUSPEND          = 120
    AUTO_RESUME           = TRUE
    INITIALLY_SUSPENDED   = TRUE
    MIN_CLUSTER_COUNT     = 1
    MAX_CLUSTER_COUNT     = 3
    SCALING_POLICY        = 'ECONOMY'
    COMMENT = 'Multi-cluster BI analytics warehouse';

-- ── Roles ─────────────────────────────────────────────────────────────────────
CREATE ROLE IF NOT EXISTS DATA_ENGINEER
    COMMENT = 'Full access to all schemas. Manages pipelines and transformations.';

CREATE ROLE IF NOT EXISTS DATA_ANALYST
    COMMENT = 'Read-only access to marts schema.';

CREATE ROLE IF NOT EXISTS DATA_SCIENTIST
    COMMENT = 'Read access to marts + ml_features. Can create models.';

CREATE ROLE IF NOT EXISTS DBT_ROLE
    COMMENT = 'Service account role for dbt Cloud CI/CD runs.';

-- ── Core tables: RAW layer ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ANALYTICS.RAW.CUSTOMERS (
    CUSTOMER_ID     VARCHAR(50)     NOT NULL,
    EMAIL           VARCHAR(255),
    FULL_NAME       VARCHAR(255),
    PHONE           VARCHAR(50),
    COUNTRY_CODE    VARCHAR(10),
    SEGMENT         VARCHAR(20),
    CREATED_AT      VARCHAR(50),
    IS_ACTIVE       VARCHAR(10),
    _FILE_NAME      VARCHAR(500),
    _LOADED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS ANALYTICS.RAW.ORDERS (
    ORDER_ID        VARCHAR(50)     NOT NULL,
    CUSTOMER_ID     VARCHAR(50),
    ORDER_DATE      VARCHAR(20),
    PRODUCT_ID      VARCHAR(50),
    AMOUNT          VARCHAR(20),
    STATUS          VARCHAR(30),
    REGION          VARCHAR(50),
    CREATED_AT      VARCHAR(50),
    _FILE_NAME      VARCHAR(500),
    _LOADED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS ANALYTICS.RAW.PRODUCTS (
    PRODUCT_ID      VARCHAR(50)     NOT NULL,
    PRODUCT_NAME    VARCHAR(255),
    CATEGORY        VARCHAR(100),
    PRICE           VARCHAR(20),
    SKU             VARCHAR(50),
    IS_ACTIVE       VARCHAR(10),
    _FILE_NAME      VARCHAR(500),
    _LOADED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

-- ── Internal stages for file ingestion ───────────────────────────────────────
CREATE STAGE IF NOT EXISTS ANALYTICS.RAW.CUSTOMER_STAGE
    FILE_FORMAT = (TYPE = CSV FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1)
    COMMENT = 'Internal stage for customer CSV files';

CREATE STAGE IF NOT EXISTS ANALYTICS.RAW.ORDER_STAGE
    FILE_FORMAT = (TYPE = CSV FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1)
    COMMENT = 'Internal stage for order CSV files';

CREATE STAGE IF NOT EXISTS ANALYTICS.PUBLIC.PYTHON_STAGE
    COMMENT = 'Stage for Snowpark Python UDF/UDTF/SP bytecode';

-- ── Grant base privileges ─────────────────────────────────────────────────────
GRANT USAGE ON DATABASE  ANALYTICS              TO ROLE DATA_ENGINEER;
GRANT USAGE ON WAREHOUSE TRANSFORM_WH           TO ROLE DATA_ENGINEER;
GRANT ALL   ON ALL SCHEMAS  IN DATABASE ANALYTICS TO ROLE DATA_ENGINEER;
GRANT ALL   ON ALL TABLES   IN DATABASE ANALYTICS TO ROLE DATA_ENGINEER;

GRANT USAGE ON DATABASE  ANALYTICS              TO ROLE DATA_ANALYST;
GRANT USAGE ON WAREHOUSE ANALYTICS_WH           TO ROLE DATA_ANALYST;
GRANT USAGE ON SCHEMA    ANALYTICS.MARTS        TO ROLE DATA_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA ANALYTICS.MARTS TO ROLE DATA_ANALYST;

GRANT USAGE ON DATABASE  ANALYTICS              TO ROLE DBT_ROLE;
GRANT USAGE ON WAREHOUSE TRANSFORM_WH           TO ROLE DBT_ROLE;
GRANT ALL   ON ALL SCHEMAS  IN DATABASE ANALYTICS TO ROLE DBT_ROLE;
GRANT ALL   ON ALL TABLES   IN DATABASE ANALYTICS TO ROLE DBT_ROLE;
GRANT CREATE TABLE ON SCHEMA ANALYTICS.STAGING  TO ROLE DBT_ROLE;
GRANT CREATE TABLE ON SCHEMA ANALYTICS.MARTS    TO ROLE DBT_ROLE;
GRANT CREATE VIEW  ON SCHEMA ANALYTICS.STAGING  TO ROLE DBT_ROLE;
