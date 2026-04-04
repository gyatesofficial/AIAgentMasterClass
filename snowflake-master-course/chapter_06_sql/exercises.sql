-- =============================================================================
-- FILE: chapter_06_sql/exercises.sql
-- TOPIC: Advanced SQL — Window Functions, Semi-Structured, PIVOT, MERGE, CTEs
-- COURSE: Snowflake Master Course | Chapter 6
-- =============================================================================
-- Snowflake supports the full SQL:2011 standard plus many extensions.
-- This chapter covers the features that separate intermediate from advanced
-- Snowflake SQL practitioners.
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE DEV_WH;
USE DATABASE ANALYTICS_DB;
USE SCHEMA   STAGING;

-- =============================================================================
-- SETUP: Create sample tables for all exercises
-- =============================================================================

CREATE OR REPLACE TABLE employees (
    emp_id      NUMBER       NOT NULL,
    emp_name    VARCHAR(100) NOT NULL,
    department  VARCHAR(50),
    hire_date   DATE,
    salary      NUMBER(10, 2),
    manager_id  NUMBER
);

INSERT INTO employees VALUES
    (1,  'Alice Martin',  'Engineering',  '2019-03-15', 95000,  NULL),
    (2,  'Bob Chen',      'Engineering',  '2020-06-01', 82000,  1),
    (3,  'Carol White',   'Marketing',    '2018-11-20', 78000,  NULL),
    (4,  'David Kim',     'Engineering',  '2021-01-10', 75000,  1),
    (5,  'Eve Johnson',   'Marketing',    '2022-04-05', 68000,  3),
    (6,  'Frank Brown',   'Finance',      '2017-08-22', 110000, NULL),
    (7,  'Grace Lee',     'Finance',      '2019-05-14', 92000,  6),
    (8,  'Henry Wilson',  'Engineering',  '2023-02-28', 70000,  2),
    (9,  'Iris Davis',    'Marketing',    '2020-09-17', 73000,  3),
    (10, 'Jack Taylor',   'Finance',      '2021-07-30', 88000,  6);

CREATE OR REPLACE TABLE daily_sales (
    sale_date   DATE         NOT NULL,
    region      VARCHAR(50)  NOT NULL,
    product_id  NUMBER       NOT NULL,
    revenue     NUMBER(12,2) NOT NULL,
    units_sold  NUMBER       NOT NULL
);

-- Generate 2 years of daily sales across 3 regions
INSERT INTO daily_sales
SELECT
    DATEADD('day', ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '2022-01-01') AS sale_date,
    CASE MOD(SEQ4(), 3) WHEN 0 THEN 'Americas' WHEN 1 THEN 'EMEA' ELSE 'APAC' END AS region,
    UNIFORM(1, 20, RANDOM())                  AS product_id,
    ROUND(UNIFORM(100, 50000, RANDOM())::FLOAT, 2) AS revenue,
    UNIFORM(1, 500, RANDOM())                 AS units_sold
FROM TABLE(GENERATOR(ROWCOUNT => 2000));

-- Create a VARIANT column table for semi-structured exercises
CREATE OR REPLACE TABLE events_json (
    event_id    NUMBER,
    user_id     NUMBER,
    raw_event   VARIANT,
    created_at  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO events_json (event_id, user_id, raw_event)
SELECT
    SEQ4() + 1,
    UNIFORM(1, 100, RANDOM()),
    PARSE_JSON('{
        "event_type": "page_view",
        "page": "/product/' || UNIFORM(1, 50, RANDOM())::VARCHAR || '",
        "duration_sec": ' || UNIFORM(5, 300, RANDOM())::VARCHAR || ',
        "tags": ["web", "mobile"],
        "device": {
            "type": "' || CASE MOD(SEQ4(), 3) WHEN 0 THEN 'desktop' WHEN 1 THEN 'mobile' ELSE 'tablet' END || '",
            "os": "' || CASE MOD(SEQ4(), 2) WHEN 0 THEN 'macOS' ELSE 'Windows' END || '"
        }
    }')
FROM TABLE(GENERATOR(ROWCOUNT => 500));

-- =============================================================================
-- EXERCISE 1
-- PURPOSE: Window functions — ROW_NUMBER, RANK, DENSE_RANK
-- WHY IT MATTERS: These functions assign ordinal positions within a partition.
--                 ROW_NUMBER is unique; RANK has gaps after ties; DENSE_RANK has no gaps.
-- =============================================================================

SELECT emp_id,
       emp_name,
       department,
       salary,
       ROW_NUMBER()  OVER (PARTITION BY department ORDER BY salary DESC) AS row_num,
       RANK()        OVER (PARTITION BY department ORDER BY salary DESC) AS rank_in_dept,
       DENSE_RANK()  OVER (PARTITION BY department ORDER BY salary DESC) AS dense_rank_in_dept
FROM   employees
ORDER  BY department, salary DESC;

-- Practical use: find the top earner in each department
SELECT department, emp_name, salary
FROM (
    SELECT department, emp_name, salary,
           ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rn
    FROM   employees
)
WHERE rn = 1;

-- =============================================================================
-- EXERCISE 2
-- PURPOSE: LAG and LEAD for time-series analysis
-- WHY IT MATTERS: LAG/LEAD avoid self-joins for period-over-period comparisons.
--                 They are the backbone of MoM, WoW, and DoD calculations.
-- =============================================================================

WITH daily_region_revenue AS (
    SELECT
        sale_date,
        region,
        SUM(revenue) AS daily_revenue
    FROM   daily_sales
    GROUP  BY 1, 2
)
SELECT
    sale_date,
    region,
    daily_revenue,
    LAG(daily_revenue)  OVER (PARTITION BY region ORDER BY sale_date) AS prev_day_revenue,
    LEAD(daily_revenue) OVER (PARTITION BY region ORDER BY sale_date) AS next_day_revenue,
    ROUND(
        100.0 * (daily_revenue - LAG(daily_revenue) OVER (PARTITION BY region ORDER BY sale_date))
        / NULLIF(LAG(daily_revenue) OVER (PARTITION BY region ORDER BY sale_date), 0),
        2
    ) AS pct_change_from_prev_day
FROM   daily_region_revenue
ORDER  BY region, sale_date
LIMIT  30;

-- =============================================================================
-- EXERCISE 3
-- PURPOSE: NTILE for quartile/decile segmentation
-- WHY IT MATTERS: NTILE divides rows into N equally-sized buckets.
--                 Use it for salary banding, revenue quartiles, customer tiers.
-- =============================================================================

-- Segment employees into salary quartiles
SELECT emp_id,
       emp_name,
       department,
       salary,
       NTILE(4)  OVER (ORDER BY salary)            AS salary_quartile,
       NTILE(10) OVER (PARTITION BY department ORDER BY salary) AS dept_salary_decile
FROM   employees
ORDER  BY salary;

-- Label the quartiles
SELECT emp_name, department, salary,
       CASE NTILE(4) OVER (ORDER BY salary)
           WHEN 1 THEN 'Q1 — Bottom 25%'
           WHEN 2 THEN 'Q2 — Lower Middle'
           WHEN 3 THEN 'Q3 — Upper Middle'
           WHEN 4 THEN 'Q4 — Top 25%'
       END AS salary_band
FROM   employees
ORDER  BY salary;

-- =============================================================================
-- EXERCISE 4
-- PURPOSE: Running totals with SUM() OVER (cumulative sum)
-- WHY IT MATTERS: Cumulative sums track progress toward a target, monitor
--                 spend burn-down, or compute running balances — impossible
--                 with a simple GROUP BY.
-- =============================================================================

-- Running total of revenue by region, ordered by date
WITH region_daily AS (
    SELECT sale_date,
           region,
           SUM(revenue) AS daily_revenue
    FROM   daily_sales
    WHERE  sale_date BETWEEN '2023-01-01' AND '2023-03-31'
    GROUP  BY 1, 2
)
SELECT sale_date,
       region,
       daily_revenue,
       SUM(daily_revenue) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total_revenue,
       AVG(daily_revenue) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS rolling_7_day_avg
FROM   region_daily
ORDER  BY region, sale_date;

-- =============================================================================
-- EXERCISE 5
-- PURPOSE: QUALIFY to filter on window function results (deduplication pattern)
-- WHY IT MATTERS: QUALIFY is Snowflake's syntactic sugar for filtering window
--                 function results — eliminating the need for a subquery wrapper.
--                 This is the fastest way to deduplicate tables in Snowflake.
-- =============================================================================

-- Deduplicate daily_sales: keep only the first row per (sale_date, region, product_id)
-- This is a common pattern when source data has duplicate events
SELECT sale_date, region, product_id, revenue, units_sold
FROM   daily_sales
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY sale_date, region, product_id
    ORDER BY revenue DESC          -- keep the highest revenue row for each key
) = 1
LIMIT 20;

-- Find employees who earn more than their department average
SELECT emp_name, department, salary,
       AVG(salary) OVER (PARTITION BY department) AS dept_avg
FROM   employees
QUALIFY salary > AVG(salary) OVER (PARTITION BY department)
ORDER  BY department, salary DESC;

-- =============================================================================
-- EXERCISE 6
-- PURPOSE: Query VARIANT columns with dot notation and ::TYPE casting
-- WHY IT MATTERS: Snowflake stores JSON, XML, and Avro as VARIANT.
--                 Dot notation navigates the hierarchy; ::TYPE casts values
--                 to SQL types for filtering, joining, and aggregating.
-- =============================================================================

-- Navigate VARIANT structure with : operator
SELECT
    event_id,
    user_id,
    raw_event:event_type::VARCHAR              AS event_type,
    raw_event:page::VARCHAR                    AS page_path,
    raw_event:duration_sec::NUMBER             AS duration_seconds,
    raw_event:device:type::VARCHAR             AS device_type,
    raw_event:device:os::VARCHAR               AS operating_system
FROM   events_json
LIMIT  10;

-- Filter on a VARIANT field
SELECT event_id, user_id, raw_event:page::VARCHAR AS page
FROM   events_json
WHERE  raw_event:device:type::VARCHAR = 'mobile'
  AND  raw_event:duration_sec::NUMBER > 60
LIMIT  10;

-- Aggregate on VARIANT fields
SELECT raw_event:device:type::VARCHAR AS device_type,
       COUNT(*)                        AS event_count,
       AVG(raw_event:duration_sec::NUMBER) AS avg_duration_sec
FROM   events_json
GROUP  BY 1
ORDER  BY 2 DESC;

-- =============================================================================
-- EXERCISE 7
-- PURPOSE: FLATTEN a nested array in a VARIANT column
-- WHY IT MATTERS: FLATTEN is the only way to explode JSON arrays into rows.
--                 Without it, you cannot filter, join, or aggregate on
--                 individual array elements.
-- =============================================================================

-- Flatten the "tags" array — produces one row per tag per event
SELECT e.event_id,
       e.user_id,
       e.raw_event:event_type::VARCHAR AS event_type,
       f.index                          AS tag_position,
       f.value::VARCHAR                 AS tag
FROM   events_json e,
       LATERAL FLATTEN(INPUT => e.raw_event:tags) f
ORDER  BY e.event_id, f.index
LIMIT  20;

-- Count events per tag
SELECT f.value::VARCHAR AS tag,
       COUNT(DISTINCT e.event_id) AS event_count
FROM   events_json e,
       LATERAL FLATTEN(INPUT => e.raw_event:tags) f
GROUP  BY 1
ORDER  BY 2 DESC;

-- =============================================================================
-- EXERCISE 8
-- PURPOSE: PIVOT sales data from rows to columns
-- WHY IT MATTERS: PIVOT transposes distinct values in one column into separate
--                 result columns. Essential for cross-tab reports and BI-ready
--                 wide tables.
-- =============================================================================

-- Revenue per region, pivoted so each region becomes a column
WITH monthly_revenue AS (
    SELECT DATE_TRUNC('month', sale_date) AS revenue_month,
           region,
           ROUND(SUM(revenue), 2)          AS total_revenue
    FROM   daily_sales
    WHERE  sale_date BETWEEN '2023-01-01' AND '2023-06-30'
    GROUP  BY 1, 2
)
SELECT *
FROM   monthly_revenue
PIVOT  (SUM(total_revenue) FOR region IN ('Americas', 'EMEA', 'APAC'))
    AS p (revenue_month, americas_revenue, emea_revenue, apac_revenue)
ORDER  BY revenue_month;

-- UNPIVOT: reverse a pivot — turn columns back into rows
-- (Useful when source data arrives in wide format but you need long format)
-- CREATE OR REPLACE TABLE wide_revenue AS (above pivot result);
-- SELECT * FROM wide_revenue UNPIVOT (revenue FOR region IN (americas_revenue, emea_revenue, apac_revenue));

-- =============================================================================
-- EXERCISE 9
-- PURPOSE: Complex MERGE — upsert with conditional DELETE
-- WHY IT MATTERS: MERGE is the Swiss Army knife of incremental data loading.
--                 It handles INSERT, UPDATE, and DELETE in a single atomic
--                 statement — critical for SCD Type 1 and CDC pipelines.
-- =============================================================================

-- Create a staging table simulating an incoming delta
CREATE OR REPLACE TABLE employees_delta (
    emp_id      NUMBER,
    emp_name    VARCHAR(100),
    department  VARCHAR(50),
    salary      NUMBER(10, 2),
    is_deleted  BOOLEAN DEFAULT FALSE   -- TRUE = soft delete signal
);

INSERT INTO employees_delta VALUES
    (2,  'Bob Chen',       'Engineering', 85000, FALSE),   -- UPDATE: salary raise
    (5,  'Eve Johnson',    'Marketing',   NULL,  TRUE),    -- DELETE: resigned
    (11, 'Kate Robinson',  'Finance',     95000, FALSE);   -- INSERT: new hire

-- MERGE with three-way logic:
--   MATCHED + is_deleted  -> DELETE from target
--   MATCHED + not deleted -> UPDATE salary
--   NOT MATCHED           -> INSERT new row
MERGE INTO employees AS target
USING employees_delta AS source
    ON target.emp_id = source.emp_id
WHEN MATCHED AND source.is_deleted = TRUE THEN
    DELETE
WHEN MATCHED AND source.is_deleted = FALSE THEN
    UPDATE SET
        target.emp_name   = source.emp_name,
        target.department = source.department,
        target.salary     = source.salary
WHEN NOT MATCHED AND source.is_deleted = FALSE THEN
    INSERT (emp_id, emp_name, department, salary)
    VALUES (source.emp_id, source.emp_name, source.department, source.salary);

-- Verify results
SELECT * FROM employees ORDER BY emp_id;

-- =============================================================================
-- EXERCISE 10
-- PURPOSE: Recursive CTE for org chart traversal
-- WHY IT MATTERS: Recursive CTEs traverse hierarchical data (org charts,
--                 BOM trees, folder structures) without procedural loops.
--                 Snowflake fully supports SQL:1999 recursive CTEs.
-- =============================================================================

-- Walk the employee hierarchy from top-level managers to individual contributors
WITH RECURSIVE org_chart (emp_id, emp_name, department, salary, manager_id, depth, path) AS (
    -- Anchor: top-level employees (no manager)
    SELECT emp_id,
           emp_name,
           department,
           salary,
           manager_id,
           0                   AS depth,
           emp_name::VARCHAR   AS path
    FROM   employees
    WHERE  manager_id IS NULL

    UNION ALL

    -- Recursive step: join employees to their managers
    SELECT e.emp_id,
           e.emp_name,
           e.department,
           e.salary,
           e.manager_id,
           oc.depth + 1,
           oc.path || ' -> ' || e.emp_name
    FROM   employees  e
    JOIN   org_chart  oc ON e.manager_id = oc.emp_id
)
SELECT LPAD('', depth * 4, ' ') || emp_name AS org_chart,
       department,
       salary,
       depth                               AS hierarchy_level,
       path                                AS reporting_chain
FROM   org_chart
ORDER  BY path;

-- =============================================================================
-- EXERCISE 11
-- PURPOSE: MATCH_RECOGNIZE for pattern detection in event sequences
-- WHY IT MATTERS: MATCH_RECOGNIZE finds row patterns in ordered sequences —
--                 like detecting a price that rises three consecutive days,
--                 or a user session funnel. No other SQL construct can do this.
-- =============================================================================

-- Detect consecutive days where revenue increased (upward trend pattern)
WITH daily_region_totals AS (
    SELECT sale_date,
           region,
           SUM(revenue) AS daily_revenue
    FROM   daily_sales
    WHERE  region = 'Americas'
    GROUP  BY 1, 2
)
SELECT *
FROM   daily_region_totals
MATCH_RECOGNIZE (
    PARTITION BY region
    ORDER BY     sale_date
    MEASURES
        FIRST(sale_date)    AS trend_start,
        LAST(sale_date)     AS trend_end,
        COUNT(*)            AS days_in_trend,
        FIRST(daily_revenue) AS start_revenue,
        LAST(daily_revenue)  AS end_revenue
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO NEXT ROW
    PATTERN  (UP{3,})    -- match 3 or more consecutive "up" rows
    DEFINE   UP AS daily_revenue > LAG(daily_revenue) OVER (ORDER BY sale_date)
)
ORDER BY trend_start;

-- =============================================================================
-- EXERCISE 12
-- PURPOSE: ASOF JOIN for time-series joins (point-in-time lookup)
-- WHY IT MATTERS: ASOF JOIN matches each row on the left with the most recent
--                 row on the right where the join key is <= the left key.
--                 Eliminates expensive range-join subqueries for price/FX lookups.
-- =============================================================================

-- Create a currency exchange rates table (sparse — rates change infrequently)
CREATE OR REPLACE TABLE fx_rates (
    rate_date  DATE        NOT NULL,
    currency   CHAR(3)     NOT NULL,
    usd_rate   NUMBER(10, 6) NOT NULL
);

INSERT INTO fx_rates VALUES
    ('2023-01-01', 'EUR', 1.0700),
    ('2023-02-01', 'EUR', 1.0850),
    ('2023-03-15', 'EUR', 1.0920),
    ('2023-01-01', 'GBP', 1.2100),
    ('2023-03-01', 'GBP', 1.2340);

CREATE OR REPLACE TABLE eur_sales (
    sale_date  DATE,
    amount_eur NUMBER(12,2),
    customer   VARCHAR(100)
);

INSERT INTO eur_sales VALUES
    ('2023-01-15', 5000,  'Acme GmbH'),
    ('2023-02-20', 8000,  'Beta AG'),
    ('2023-04-10', 12000, 'Gamma GmbH');

-- ASOF JOIN: for each sale, find the most recent EUR/USD rate on or before the sale date
SELECT s.sale_date,
       s.customer,
       s.amount_eur,
       r.usd_rate,
       r.rate_date              AS rate_as_of,
       ROUND(s.amount_eur * r.usd_rate, 2) AS amount_usd
FROM   eur_sales s
ASOF JOIN fx_rates r
    MATCH_CONDITION (s.sale_date >= r.rate_date)
    ON  r.currency = 'EUR'
ORDER BY s.sale_date;

-- =============================================================================
-- EXERCISE 13
-- PURPOSE: Regex functions — REGEXP_LIKE, REGEXP_SUBSTR, REGEXP_REPLACE
-- WHY IT MATTERS: Regex unlocks pattern-based parsing of messy string data —
--                 extracting email domains, validating phone numbers, parsing
--                 log lines, and cleaning text fields.
-- =============================================================================

-- Sample dirty data
CREATE OR REPLACE TABLE contact_data (
    id      NUMBER,
    raw_text VARCHAR(500)
);

INSERT INTO contact_data VALUES
    (1, 'Call Alice at +1-800-555-0100 or email alice@example.com'),
    (2, 'Contact: bob@company.co.uk | Phone: (555) 234-5678'),
    (3, 'No contact info available'),
    (4, 'Reach out to carol@subdomain.example.org for pricing');

-- REGEXP_LIKE: returns TRUE if the string matches the pattern
SELECT id, raw_text,
       REGEXP_LIKE(raw_text, '.*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*') AS has_email,
       REGEXP_LIKE(raw_text, '.*\d{3}[-.\s]\d{3}[-.\s]\d{4}.*')                     AS has_phone
FROM   contact_data;

-- REGEXP_SUBSTR: extract the first email address from raw text
SELECT id,
       REGEXP_SUBSTR(raw_text, '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}') AS extracted_email,
       REGEXP_SUBSTR(raw_text, '[\+\(]?[0-9][0-9\s\-\(\)]{7,}[0-9]')             AS extracted_phone
FROM   contact_data;

-- REGEXP_REPLACE: sanitise text by removing phone numbers
SELECT id,
       REGEXP_REPLACE(
           raw_text,
           '[\+\(]?[0-9][0-9\s\-\(\)]{7,}[0-9]',
           '[PHONE REDACTED]'
       ) AS sanitised_text
FROM   contact_data;

-- =============================================================================
-- EXERCISE 14
-- PURPOSE: Date math — DATEADD, DATEDIFF, DATE_TRUNC, LAST_DAY
-- WHY IT MATTERS: Date arithmetic is in every analytics query.
--                 Snowflake's date functions are ANSI-standard but have
--                 powerful Snowflake-specific extensions worth knowing.
-- =============================================================================

-- DATEADD: add intervals to a date
SELECT
    CURRENT_DATE()                                   AS today,
    DATEADD('day',    7,  CURRENT_DATE())            AS one_week_later,
    DATEADD('month', -3,  CURRENT_DATE())            AS three_months_ago,
    DATEADD('year',   1,  CURRENT_DATE())            AS next_year;

-- DATEDIFF: measure the gap between two dates
SELECT emp_id,
       emp_name,
       hire_date,
       DATEDIFF('day',   hire_date, CURRENT_DATE())  AS days_employed,
       DATEDIFF('month', hire_date, CURRENT_DATE())  AS months_employed,
       DATEDIFF('year',  hire_date, CURRENT_DATE())  AS years_employed
FROM   employees
ORDER  BY hire_date;

-- DATE_TRUNC: round down to start of a period
SELECT
    CURRENT_DATE()                              AS today,
    DATE_TRUNC('week',    CURRENT_DATE())       AS week_start,
    DATE_TRUNC('month',   CURRENT_DATE())       AS month_start,
    DATE_TRUNC('quarter', CURRENT_DATE())       AS quarter_start,
    DATE_TRUNC('year',    CURRENT_DATE())       AS year_start;

-- LAST_DAY, NEXT_DAY, DAYOFWEEK
SELECT sale_date,
       LAST_DAY(sale_date)                      AS last_day_of_month,
       LAST_DAY(sale_date, 'quarter')           AS last_day_of_quarter,
       DAYOFWEEK(sale_date)                     AS day_of_week_num,   -- 0=Sun
       DAYNAME(sale_date)                       AS day_name,
       WEEKOFYEAR(sale_date)                    AS iso_week
FROM   daily_sales
LIMIT  5;

-- =============================================================================
-- EXERCISE 15
-- PURPOSE: Complex analytical query combining CTEs + window functions
-- WHY IT MATTERS: Real-world analytics queries layer multiple concepts.
--                 This exercise shows how CTEs, window functions, aggregations,
--                 and filtering compose into a complete business insight.
-- =============================================================================

-- Business question: "Which products are top performers in each region,
-- what is their month-over-month revenue change, and how do they rank globally?"

WITH
-- Step 1: Aggregate to monthly product-region level
monthly_product AS (
    SELECT DATE_TRUNC('month', sale_date)   AS revenue_month,
           region,
           product_id,
           SUM(revenue)                      AS monthly_revenue,
           SUM(units_sold)                   AS monthly_units
    FROM   daily_sales
    WHERE  sale_date BETWEEN '2023-01-01' AND '2023-12-31'
    GROUP  BY 1, 2, 3
),

-- Step 2: Add month-over-month change per product per region
with_mom AS (
    SELECT revenue_month,
           region,
           product_id,
           monthly_revenue,
           monthly_units,
           LAG(monthly_revenue) OVER (
               PARTITION BY region, product_id
               ORDER BY revenue_month
           ) AS prev_month_revenue,
           ROUND(
               100.0 * (monthly_revenue - LAG(monthly_revenue) OVER (
                   PARTITION BY region, product_id ORDER BY revenue_month
               )) / NULLIF(LAG(monthly_revenue) OVER (
                   PARTITION BY region, product_id ORDER BY revenue_month
               ), 0),
               2
           ) AS mom_pct_change
    FROM   monthly_product
),

-- Step 3: Rank products within each region per month
with_rank AS (
    SELECT *,
           RANK()  OVER (PARTITION BY revenue_month, region ORDER BY monthly_revenue DESC) AS regional_rank,
           RANK()  OVER (PARTITION BY revenue_month          ORDER BY monthly_revenue DESC) AS global_rank,
           SUM(monthly_revenue) OVER (PARTITION BY revenue_month, region)                  AS region_monthly_total,
           ROUND(100.0 * monthly_revenue
               / SUM(monthly_revenue) OVER (PARTITION BY revenue_month, region), 2)        AS pct_of_region
    FROM   with_mom
)

-- Final output: top 3 products per region per month with all metrics
SELECT revenue_month,
       region,
       product_id,
       monthly_revenue,
       monthly_units,
       mom_pct_change,
       regional_rank,
       global_rank,
       pct_of_region
FROM   with_rank
WHERE  regional_rank <= 3
ORDER  BY revenue_month, region, regional_rank;

-- =============================================================================
-- END OF CHAPTER 6 EXERCISES
-- =============================================================================
