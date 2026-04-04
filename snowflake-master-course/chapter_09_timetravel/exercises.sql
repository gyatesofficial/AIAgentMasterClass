-- =============================================================================
-- FILE: chapter_09_timetravel/exercises.sql
-- TOPIC: Time Travel, Fail-safe, and Zero-Copy Cloning
-- COURSE: Snowflake Master Course | Chapter 9
-- =============================================================================
-- Snowflake's data resilience stack:
--   Time Travel  — Query/restore data from any point in the retention window
--                  (0-90 days for Enterprise; 0-1 day for Standard)
--   Fail-safe    — Additional 7-day emergency recovery window after Time Travel
--                  expires; accessible only by Snowflake Support
--   Zero-copy    — Clones are instant, metadata-only snapshots; storage is shared
--                  until the clone diverges (copy-on-write)
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   STAGING;

-- =============================================================================
-- SETUP: Create a table with some history to travel through
-- =============================================================================

CREATE OR REPLACE TABLE tt_orders (
    order_id    NUMBER        NOT NULL,
    customer_id NUMBER,
    status      VARCHAR(20)   DEFAULT 'PENDING',
    amount      NUMBER(12, 2),
    created_at  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
DATA_RETENTION_TIME_IN_DAYS = 14
COMMENT = 'Time Travel demo table — production-grade retention';

INSERT INTO tt_orders (order_id, customer_id, amount)
SELECT SEQ4() + 1,
       UNIFORM(1, 50, RANDOM()),
       ROUND(UNIFORM(10, 2000, RANDOM())::FLOAT, 2)
FROM   TABLE(GENERATOR(ROWCOUNT => 100));

-- Capture a timestamp right after the initial insert
SET ts_after_insert = CURRENT_TIMESTAMP();

-- Wait a moment, then make changes (simulate pipeline processing)
UPDATE tt_orders SET status = 'PROCESSING' WHERE order_id <= 40;

SET ts_after_update = CURRENT_TIMESTAMP();

-- Simulate accidental deletion
DELETE FROM tt_orders WHERE order_id BETWEEN 11 AND 20;

SET ts_after_delete = CURRENT_TIMESTAMP();

-- Verify current state
SELECT status, COUNT(*) AS cnt, SUM(amount) AS total
FROM   tt_orders GROUP BY 1;

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Query a table AT a specific past timestamp
-- WHY IT MATTERS: The AT clause is the core of Time Travel. It rewinds the
--                 table's view to exactly the state it was in at that moment.
--                 No restore needed — it's a live read of historical data.
-- =============================================================================

-- See data as it looked right after the initial insert (before any updates)
SELECT status, COUNT(*) AS cnt
FROM   tt_orders AT (TIMESTAMP => $ts_after_insert::TIMESTAMP_NTZ)
GROUP  BY 1;
-- All rows should show status = 'PENDING'

-- See data after the UPDATE but before the DELETE
SELECT status, COUNT(*) AS cnt
FROM   tt_orders AT (TIMESTAMP => $ts_after_update::TIMESTAMP_NTZ)
GROUP  BY 1;
-- Should show PENDING + PROCESSING rows, all 100 rows intact

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: Query BEFORE a specific statement_id (exact statement rollback)
-- WHY IT MATTERS: The BEFORE clause is the most surgical Time Travel option.
--                 It rewinds to immediately before a specific query ran —
--                 perfect when you know the query_id of the mistake.
-- =============================================================================

-- Find the query_id of the DELETE statement
SELECT query_id,
       query_text,
       start_time
FROM   TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(RESULT_LIMIT => 20))
WHERE  query_text ILIKE '%DELETE%tt_orders%'
ORDER  BY start_time DESC
LIMIT  1;

-- Capture that query ID (replace with actual ID from above)
-- SET delete_query_id = '<paste_query_id_here>';

-- Query the table as it was BEFORE the delete ran
-- SELECT COUNT(*) AS row_count_before_delete
-- FROM   tt_orders BEFORE (STATEMENT => $delete_query_id);

-- Alternative: use a literal query ID string
-- SELECT * FROM tt_orders BEFORE (STATEMENT => 'abc123-...')
-- WHERE order_id BETWEEN 11 AND 20;

SELECT 'Replace <paste_query_id_here> above with actual ID from QUERY_HISTORY.' AS instruction;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: Query using OFFSET (relative seconds ago)
-- WHY IT MATTERS: OFFSET is useful when you know "it broke about 5 minutes ago"
--                 but don't have the exact timestamp.
-- =============================================================================

-- Look at data as it was 5 minutes ago (adjust offset as needed)
SELECT COUNT(*) AS row_count_5min_ago
FROM   tt_orders AT (OFFSET => -300);   -- 300 seconds = 5 minutes

-- 2 minutes ago
SELECT COUNT(*) AS row_count_2min_ago
FROM   tt_orders AT (OFFSET => -120);

-- Immediately after object creation (maximum safe offset)
SELECT COUNT(*) AS row_count_at_insert
FROM   tt_orders AT (TIMESTAMP => $ts_after_insert::TIMESTAMP_NTZ);

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Create a backup table via CTAS with AT clause
-- WHY IT MATTERS: The fastest way to recover deleted or corrupted rows is
--                 CTAS FROM <table> AT (...). This materialises the historical
--                 state as a new table — no external backup files needed.
-- =============================================================================

-- Recover the deleted rows by creating a table from the pre-delete state
CREATE OR REPLACE TABLE tt_orders_recovered AS
SELECT *
FROM   tt_orders AT (TIMESTAMP => $ts_after_update::TIMESTAMP_NTZ)
WHERE  order_id BETWEEN 11 AND 20;

SELECT COUNT(*) AS recovered_rows FROM tt_orders_recovered;
-- Should show 10 rows

-- Optionally merge the recovered rows back into the original table
MERGE INTO tt_orders AS target
USING tt_orders_recovered AS src
    ON target.order_id = src.order_id
WHEN NOT MATCHED THEN
    INSERT (order_id, customer_id, status, amount, created_at)
    VALUES (src.order_id, src.customer_id, src.status, src.amount, src.created_at);

-- Verify recovery
SELECT COUNT(*) AS restored_total FROM tt_orders;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: DROP and UNDROP a table
-- WHY IT MATTERS: Accidental drops happen. UNDROP reverses a DROP within the
--                 retention window, restoring the table and ALL its data —
--                 no restore job, no downtime.
-- =============================================================================

-- Create a test table to safely drop
CREATE OR REPLACE TABLE tt_temp_important (
    id    NUMBER,
    data  VARCHAR(100)
);
INSERT INTO tt_temp_important VALUES (1, 'Critical data'), (2, 'More critical data');

-- Accidentally drop it
DROP TABLE tt_temp_important;

-- Try to query it — will fail
-- SELECT * FROM tt_temp_important;  -- Table 'TT_TEMP_IMPORTANT' does not exist

-- Recover it with UNDROP (must happen within DATA_RETENTION_TIME_IN_DAYS)
UNDROP TABLE tt_temp_important;

-- Verify data is fully restored
SELECT * FROM tt_temp_important;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: DROP and UNDROP a schema
-- WHY IT MATTERS: Schema-level UNDROP restores the schema AND all objects within
--                 it. This is the recovery path for accidentally dropping a schema.
-- =============================================================================

-- Create a test schema
CREATE SCHEMA IF NOT EXISTS test_droppable_schema;
CREATE TABLE test_droppable_schema.test_table (id NUMBER, val VARCHAR);
INSERT INTO test_droppable_schema.test_table VALUES (1, 'hello'), (2, 'world');

-- Drop the schema (this also drops all objects in it)
DROP SCHEMA test_droppable_schema;

-- Verify it's gone
SHOW SCHEMAS LIKE 'TEST_DROPPABLE_SCHEMA';

-- UNDROP the entire schema (restores tables, views, and all objects)
UNDROP SCHEMA test_droppable_schema;

-- Verify full restoration
SELECT * FROM test_droppable_schema.test_table;

-- Databases can also be undropped the same way:
-- DROP DATABASE my_db;
-- UNDROP DATABASE my_db;

-- Cleanup
DROP SCHEMA IF EXISTS test_droppable_schema;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: Clone a table — zero-copy, instant
-- WHY IT MATTERS: Cloning creates a complete, independent copy in milliseconds
--                 regardless of table size. Until the clone is modified, it
--                 shares micro-partitions with the source (zero extra storage).
-- =============================================================================

-- Clone tt_orders for development testing
CREATE OR REPLACE TABLE tt_orders_dev
    CLONE tt_orders
    COMMENT = 'Dev clone of tt_orders — safe to modify; shares storage until diverged';

-- Clone is identical to source at the moment of creation
SELECT 'source' AS origin, COUNT(*) AS rows FROM tt_orders
UNION ALL
SELECT 'clone',             COUNT(*) FROM tt_orders_dev;

-- Modifying the clone creates new micro-partitions (clone diverges, source unchanged)
UPDATE tt_orders_dev SET status = 'TEST_MODE' WHERE order_id <= 10;

-- Source is untouched
SELECT status, COUNT(*) FROM tt_orders     WHERE order_id <= 10 GROUP BY 1;
-- Clone has the change
SELECT status, COUNT(*) FROM tt_orders_dev WHERE order_id <= 10 GROUP BY 1;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: Clone a schema (clones all objects inside it at once)
-- WHY IT MATTERS: Schema cloning is the fastest way to create a complete
--                 dev/test environment. Every table, view, and stage inside
--                 is cloned in a single statement — no scripting needed.
-- =============================================================================

-- Clone the entire STAGING schema into a dev variant
CREATE SCHEMA IF NOT EXISTS STAGING_DEV
    CLONE STAGING
    COMMENT = 'Cloned from STAGING for sprint 2024-Q1 development';

-- Verify all objects were cloned
SHOW TABLES IN SCHEMA ANALYTICS_DB.STAGING_DEV;

-- Objects in the clone share storage with STAGING until modified
-- Schema-level DDL changes (ALTER TABLE, DROP, etc.) on STAGING_DEV
-- do NOT affect the original STAGING schema

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Clone with AT timestamp — clone from a historical state
-- WHY IT MATTERS: You can create a clone from a point in time, not just the
--                 current state. This is how you create historical snapshots
--                 for end-of-month or quarterly reporting freezes.
-- =============================================================================

-- Clone tt_orders from the state BEFORE the delete (all 100 rows)
CREATE OR REPLACE TABLE tt_orders_eom_snapshot
    CLONE tt_orders AT (TIMESTAMP => $ts_after_update::TIMESTAMP_NTZ)
    COMMENT = 'End-of-period snapshot — reflects state before batch delete';

SELECT COUNT(*) AS snapshot_rows FROM tt_orders_eom_snapshot;
-- Should show 100 rows (pre-delete state)

-- Current table has fewer rows
SELECT COUNT(*) AS current_rows FROM tt_orders;

-- This pattern is also used for "undo accidental truncation":
-- If someone ran TRUNCATE TABLE production_table by mistake:
--   1. Find the timestamp just before the TRUNCATE
--   2. CREATE TABLE production_table_backup CLONE production_table AT (TIMESTAMP => ...)
--   3. TRUNCATE production_table;  INSERT INTO production_table SELECT * FROM backup;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Modify a cloned table and observe divergence from source
-- WHY IT MATTERS: Demonstrating copy-on-write behaviour makes the zero-cost
--                 cloning value proposition tangible. Modified partitions in
--                 the clone are new; unmodified partitions are still shared.
-- =============================================================================

-- Run a large update on the dev clone
UPDATE tt_orders_dev
SET    status = 'DEV_PROCESSED',
       amount = amount * 1.10   -- 10% price increase test
WHERE  status = 'PROCESSING';

-- Source is still at its original state
SELECT status, ROUND(AVG(amount),2) AS avg_amount FROM tt_orders     GROUP BY 1 ORDER BY 1;

-- Clone reflects the changes
SELECT status, ROUND(AVG(amount),2) AS avg_amount FROM tt_orders_dev GROUP BY 1 ORDER BY 1;

-- Check approximate table sizes (storage divergence)
-- NOTE: Storage_bytes shows in INFORMATION_SCHEMA after a short delay
SELECT table_name, active_bytes, time_travel_bytes, clone_group_id
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.TABLE_STORAGE_METRICS
WHERE  table_schema = 'STAGING'
  AND  table_name   IN ('TT_ORDERS', 'TT_ORDERS_DEV')
ORDER  BY table_name;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: Set DATA_RETENTION_TIME_IN_DAYS at different levels
-- WHY IT MATTERS: Retention can be set at account, database, schema, or table
--                 level. Higher levels are the default; lower levels override.
--                 Longer retention = more storage cost.
-- =============================================================================

-- Set retention at table level (overrides schema/database defaults)
ALTER TABLE tt_orders
    SET DATA_RETENTION_TIME_IN_DAYS = 30;    -- 30-day Time Travel for this table

-- Set shorter retention on a transient staging table to save storage cost
ALTER TABLE tt_orders_dev
    SET DATA_RETENTION_TIME_IN_DAYS = 1;     -- dev table: 1-day only

-- Set at schema level (all future tables inherit this unless overridden)
ALTER SCHEMA ANALYTICS_DB.STAGING
    SET DATA_RETENTION_TIME_IN_DAYS = 7;

-- Set at database level
ALTER DATABASE ANALYTICS_DB
    SET DATA_RETENTION_TIME_IN_DAYS = 14;

-- Check current retention settings
SHOW TABLES LIKE 'TT_ORDERS%' IN SCHEMA ANALYTICS_DB.STAGING;

SELECT table_name, retention_time
FROM   ANALYTICS_DB.INFORMATION_SCHEMA.TABLES
WHERE  table_schema = 'STAGING'
  AND  table_name   LIKE 'TT_ORDERS%';

-- NOTE: To disable Time Travel entirely (e.g., for very large transient tables):
--   ALTER TABLE big_temp_table SET DATA_RETENTION_TIME_IN_DAYS = 0;
--   This also saves Fail-safe storage cost (Fail-safe only applies when TT > 0)

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: Query streams that capture historical changes using Time Travel
-- WHY IT MATTERS: Streams record CDC offsets. Combined with Time Travel,
--                 you can inspect the exact change set that a stream will
--                 (or did) process, aiding in pipeline debugging.
-- =============================================================================

-- Create a stream on tt_orders to capture future changes
CREATE OR REPLACE STREAM stream_tt_orders
    ON TABLE tt_orders
    APPEND_ONLY = FALSE
    COMMENT = 'CDC stream for tt_orders pipeline';

-- Make some changes to populate the stream
INSERT INTO tt_orders (order_id, customer_id, amount)
VALUES (200, 99, 999.99), (201, 88, 1500.00);

UPDATE tt_orders SET status = 'SHIPPED' WHERE order_id = 200;

-- Query the stream to see the pending change set
SELECT *,
       METADATA$ACTION    AS cdc_action,
       METADATA$ISUPDATE  AS is_update_row,
       METADATA$ROW_ID    AS row_id
FROM   stream_tt_orders;

-- Check stream metadata
SHOW STREAMS LIKE 'STREAM_TT_ORDERS' IN SCHEMA ANALYTICS_DB.STAGING;

-- The "stale_after" column tells you when this stream will expire
-- (set to current_time + DATA_RETENTION_TIME_IN_DAYS of the source table)
SELECT "name",
       "stale"           AS is_stale,
       "stale_after"     AS expires_at,
       "mode"            AS stream_mode,
       "source_database_name",
       "source_schema_name",
       "source_table_name"
FROM   TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- Consume the stream in a transaction (stream offset advances after a DML commits)
BEGIN;
    INSERT INTO tt_orders_recovered
    SELECT order_id, customer_id, status, amount, created_at
    FROM   stream_tt_orders
    WHERE  METADATA$ACTION = 'INSERT';
COMMIT;

-- After consuming, the stream should be empty (offset advanced)
SELECT COUNT(*) AS pending_changes FROM stream_tt_orders;

-- =============================================================================
-- CLEANUP (optional)
-- =============================================================================
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.tt_orders;
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.tt_orders_dev;
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.tt_orders_recovered;
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.tt_orders_eom_snapshot;
-- DROP TABLE IF EXISTS ANALYTICS_DB.STAGING.tt_temp_important;
-- DROP SCHEMA IF EXISTS ANALYTICS_DB.STAGING_DEV;
-- DROP STREAM IF EXISTS ANALYTICS_DB.STAGING.stream_tt_orders;

-- =============================================================================
-- END OF CHAPTER 9 EXERCISES
-- =============================================================================
