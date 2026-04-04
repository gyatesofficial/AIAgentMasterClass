-- =============================================================================
-- schemachange Migration V1.1.0 – Add Customer Segments
-- Snowflake Master Course | Chapter 16
-- =============================================================================
-- Adds the CUSTOMER_SEGMENTS reference table, a computed SEGMENT_RANK column
-- to the raw customers table, and a segment transition history table for
-- tracking when customers move between tiers.
--
-- Author:    data-platform-team
-- Date:      2024-02-10
-- Ticket:    DATA-045
-- Depends:   V1.0.0__initial_schema.sql
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE COMPUTE_WH;
USE DATABASE ANALYTICS;

-- ── Reference / lookup table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.CUSTOMER_SEGMENTS (
    SEGMENT_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
    SEGMENT_NAME        VARCHAR(20)   NOT NULL,
    SEGMENT_RANK        INTEGER       NOT NULL,   -- 1=Bronze … 4=Platinum
    MIN_LIFETIME_VALUE  DECIMAL(12,2) NOT NULL,   -- Minimum LTV to qualify
    MAX_LIFETIME_VALUE  DECIMAL(12,2),            -- NULL = no upper bound
    DISCOUNT_PCT        DECIMAL(5,2)  NOT NULL DEFAULT 0.00,
    SUPPORT_SLA_HOURS   INTEGER       NOT NULL DEFAULT 72,
    DESCRIPTION         VARCHAR(500),
    CREATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Seed initial segment definitions
INSERT INTO ANALYTICS.MARTS.CUSTOMER_SEGMENTS
    (SEGMENT_NAME, SEGMENT_RANK, MIN_LIFETIME_VALUE, MAX_LIFETIME_VALUE,
     DISCOUNT_PCT, SUPPORT_SLA_HOURS, DESCRIPTION)
VALUES
    ('Bronze',   1,       0.00,    499.99,  0.00,  72, 'Entry tier. Standard support. No discounts.'),
    ('Silver',   2,     500.00,   1999.99,  5.00,  48, 'Mid tier. Priority email support. 5% discount.'),
    ('Gold',     3,    2000.00,   4999.99, 10.00,  24, 'High tier. Dedicated chat support. 10% discount.'),
    ('Platinum', 4,    5000.00,      NULL, 15.00,   4, 'VIP tier. 24/7 phone support. 15% discount + dedicated CSM.');

-- ── Segment transition history ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.CUSTOMER_SEGMENT_HISTORY (
    HISTORY_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
    CUSTOMER_ID         VARCHAR(50)   NOT NULL,
    PREVIOUS_SEGMENT    VARCHAR(20),
    NEW_SEGMENT         VARCHAR(20)   NOT NULL,
    EFFECTIVE_DATE      DATE          NOT NULL DEFAULT CURRENT_DATE(),
    REASON              VARCHAR(100),  -- e.g. 'LTV_THRESHOLD', 'MANUAL_OVERRIDE', 'PROMOTION'
    CHANGED_BY          VARCHAR(100),
    CREATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Index for efficient customer lookups
CREATE INDEX IF NOT EXISTS idx_seg_history_customer
    ON ANALYTICS.MARTS.CUSTOMER_SEGMENT_HISTORY (CUSTOMER_ID, EFFECTIVE_DATE);

-- ── Add SEGMENT_RANK column to raw CUSTOMERS table ────────────────────────────
-- Raw table gets a denormalized rank for faster downstream processing

ALTER TABLE ANALYTICS.RAW.CUSTOMERS
    ADD COLUMN IF NOT EXISTS SEGMENT_RANK INTEGER;

-- Backfill the rank for existing rows
UPDATE ANALYTICS.RAW.CUSTOMERS
SET SEGMENT_RANK = CASE UPPER(TRIM(SEGMENT))
                       WHEN 'PLATINUM' THEN 4
                       WHEN 'GOLD'     THEN 3
                       WHEN 'SILVER'   THEN 2
                       WHEN 'BRONZE'   THEN 1
                       ELSE                  0
                   END
WHERE SEGMENT_RANK IS NULL;

-- ── Stored procedure: auto-reclassify customers based on LTV ─────────────────

CREATE OR REPLACE PROCEDURE ANALYTICS.MARTS.RECLASSIFY_CUSTOMER_SEGMENTS()
RETURNS TABLE (CUSTOMER_ID VARCHAR, OLD_SEGMENT VARCHAR, NEW_SEGMENT VARCHAR)
LANGUAGE SQL
EXECUTE AS CALLER
AS $$
BEGIN
    -- Create temp table of customers whose segment should change
    CREATE OR REPLACE TEMPORARY TABLE TEMP_SEGMENT_CHANGES AS
    SELECT
        c.CUSTOMER_ID,
        c.SEGMENT                                        AS old_segment,
        s.SEGMENT_NAME                                   AS new_segment
    FROM ANALYTICS.MARTS.DIM_CUSTOMERS  c
    JOIN ANALYTICS.MARTS.CUSTOMER_SEGMENTS s
        ON  c.LIFETIME_VALUE >= s.MIN_LIFETIME_VALUE
        AND (c.LIFETIME_VALUE <  s.MAX_LIFETIME_VALUE OR s.MAX_LIFETIME_VALUE IS NULL)
    WHERE c.SEGMENT != s.SEGMENT_NAME;

    -- Log changes into history table
    INSERT INTO ANALYTICS.MARTS.CUSTOMER_SEGMENT_HISTORY
        (CUSTOMER_ID, PREVIOUS_SEGMENT, NEW_SEGMENT, REASON, CHANGED_BY)
    SELECT
        CUSTOMER_ID,
        old_segment,
        new_segment,
        'LTV_THRESHOLD',
        'SYSTEM_PROCEDURE'
    FROM TEMP_SEGMENT_CHANGES;

    -- Return the changes (caller can log or alert on these)
    RETURN TABLE(SELECT * FROM TEMP_SEGMENT_CHANGES);
END;
$$;

-- ── Grant permissions on new objects ─────────────────────────────────────────
GRANT SELECT ON TABLE ANALYTICS.MARTS.CUSTOMER_SEGMENTS         TO ROLE DATA_ANALYST;
GRANT SELECT ON TABLE ANALYTICS.MARTS.CUSTOMER_SEGMENT_HISTORY  TO ROLE DATA_ANALYST;
GRANT SELECT ON TABLE ANALYTICS.MARTS.CUSTOMER_SEGMENTS         TO ROLE DATA_SCIENTIST;
GRANT ALL    ON TABLE ANALYTICS.MARTS.CUSTOMER_SEGMENTS         TO ROLE DATA_ENGINEER;
GRANT ALL    ON TABLE ANALYTICS.MARTS.CUSTOMER_SEGMENT_HISTORY  TO ROLE DATA_ENGINEER;
GRANT USAGE  ON PROCEDURE ANALYTICS.MARTS.RECLASSIFY_CUSTOMER_SEGMENTS()
    TO ROLE DATA_ENGINEER;
