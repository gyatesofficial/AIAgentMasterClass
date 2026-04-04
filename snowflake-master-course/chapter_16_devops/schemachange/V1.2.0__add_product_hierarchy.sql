-- =============================================================================
-- schemachange Migration V1.2.0 – Add Product Hierarchy
-- Snowflake Master Course | Chapter 16
-- =============================================================================
-- Extends the product model with a full three-level hierarchy:
--   Department → Category → Subcategory
-- Also adds a product_attributes VARIANT column for flexible metadata storage
-- and a product_inventory table.
--
-- Author:    data-platform-team
-- Date:      2024-03-05
-- Ticket:    DATA-072
-- Depends:   V1.1.0__add_customer_segments.sql
-- =============================================================================

USE ROLE    SYSADMIN;
USE WAREHOUSE COMPUTE_WH;
USE DATABASE ANALYTICS;

-- ── Department reference table (top level) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.PRODUCT_DEPARTMENTS (
    DEPARTMENT_ID    NUMBER AUTOINCREMENT PRIMARY KEY,
    DEPARTMENT_NAME  VARCHAR(100) NOT NULL UNIQUE,
    DISPLAY_ORDER    INTEGER      NOT NULL DEFAULT 0,
    IS_ACTIVE        BOOLEAN      NOT NULL DEFAULT TRUE,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO ANALYTICS.MARTS.PRODUCT_DEPARTMENTS (DEPARTMENT_NAME, DISPLAY_ORDER)
VALUES
    ('Electronics',       1),
    ('Clothing',          2),
    ('Home & Kitchen',    3),
    ('Sports & Outdoors', 4),
    ('Books & Media',     5),
    ('Health & Beauty',   6),
    ('Toys & Games',      7);

-- ── Category reference table (second level) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.PRODUCT_CATEGORIES (
    CATEGORY_ID      NUMBER AUTOINCREMENT PRIMARY KEY,
    DEPARTMENT_ID    INTEGER       NOT NULL REFERENCES ANALYTICS.MARTS.PRODUCT_DEPARTMENTS(DEPARTMENT_ID),
    CATEGORY_NAME    VARCHAR(100)  NOT NULL,
    CATEGORY_SLUG    VARCHAR(100)  NOT NULL,  -- URL-safe identifier
    IS_ACTIVE        BOOLEAN       NOT NULL DEFAULT TRUE,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UNIQUE (DEPARTMENT_ID, CATEGORY_NAME)
);

INSERT INTO ANALYTICS.MARTS.PRODUCT_CATEGORIES (DEPARTMENT_ID, CATEGORY_NAME, CATEGORY_SLUG)
VALUES
    (1, 'Audio',          'audio'),
    (1, 'Computers',      'computers'),
    (1, 'Wearables',      'wearables'),
    (1, 'Smart Home',     'smart-home'),
    (2, 'Men''s Apparel', 'mens-apparel'),
    (2, 'Women''s Apparel','womens-apparel'),
    (2, 'Footwear',       'footwear'),
    (3, 'Kitchen',        'kitchen'),
    (3, 'Bedding',        'bedding'),
    (4, 'Fitness',        'fitness'),
    (4, 'Outdoor Gear',   'outdoor-gear');

-- ── Subcategory reference table (third level) ────────────────────────────────
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.PRODUCT_SUBCATEGORIES (
    SUBCATEGORY_ID   NUMBER AUTOINCREMENT PRIMARY KEY,
    CATEGORY_ID      INTEGER       NOT NULL REFERENCES ANALYTICS.MARTS.PRODUCT_CATEGORIES(CATEGORY_ID),
    SUBCATEGORY_NAME VARCHAR(100)  NOT NULL,
    SUBCATEGORY_SLUG VARCHAR(100)  NOT NULL,
    IS_ACTIVE        BOOLEAN       NOT NULL DEFAULT TRUE,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO ANALYTICS.MARTS.PRODUCT_SUBCATEGORIES (CATEGORY_ID, SUBCATEGORY_NAME, SUBCATEGORY_SLUG)
VALUES
    (1, 'Headphones',        'headphones'),
    (1, 'Speakers',          'speakers'),
    (1, 'Earbuds',           'earbuds'),
    (2, 'Laptops',           'laptops'),
    (2, 'Monitors',          'monitors'),
    (3, 'Smartwatches',      'smartwatches'),
    (3, 'Fitness Trackers',  'fitness-trackers'),
    (4, 'Voice Assistants',  'voice-assistants'),
    (10, 'Yoga',             'yoga'),
    (10, 'Running',          'running');

-- ── Extend the DIM_PRODUCTS table with hierarchy columns ──────────────────────
ALTER TABLE ANALYTICS.RAW.PRODUCTS
    ADD COLUMN IF NOT EXISTS DEPARTMENT_ID    INTEGER,
    ADD COLUMN IF NOT EXISTS CATEGORY_ID      INTEGER,
    ADD COLUMN IF NOT EXISTS SUBCATEGORY_ID   INTEGER,
    ADD COLUMN IF NOT EXISTS DESCRIPTION      VARCHAR(2000),
    ADD COLUMN IF NOT EXISTS ATTRIBUTES       VARIANT,   -- flexible JSON metadata
    ADD COLUMN IF NOT EXISTS WEIGHT_KG        DECIMAL(8,3),
    ADD COLUMN IF NOT EXISTS UPDATED_AT       TIMESTAMP_NTZ;

-- ── Product inventory table ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ANALYTICS.MARTS.PRODUCT_INVENTORY (
    INVENTORY_ID        NUMBER AUTOINCREMENT PRIMARY KEY,
    PRODUCT_ID          VARCHAR(50)   NOT NULL,
    WAREHOUSE_LOCATION  VARCHAR(10)   NOT NULL,  -- e.g. US-EAST, EU-WEST
    QUANTITY_ON_HAND    INTEGER       NOT NULL DEFAULT 0,
    QUANTITY_RESERVED   INTEGER       NOT NULL DEFAULT 0,
    REORDER_POINT       INTEGER       NOT NULL DEFAULT 10,
    REORDER_QUANTITY    INTEGER       NOT NULL DEFAULT 50,
    LAST_RESTOCKED_AT   TIMESTAMP_NTZ,
    UPDATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UNIQUE (PRODUCT_ID, WAREHOUSE_LOCATION)
);

-- ── View: full product hierarchy (denormalized) ───────────────────────────────
CREATE OR REPLACE VIEW ANALYTICS.MARTS.DIM_PRODUCTS_FULL AS
SELECT
    p.PRODUCT_ID,
    p.PRODUCT_NAME,
    p.SKU,
    p.PRICE,
    p.IS_ACTIVE,
    p.DESCRIPTION,
    p.ATTRIBUTES,
    p.WEIGHT_KG,

    -- Category hierarchy
    sub.SUBCATEGORY_NAME,
    sub.SUBCATEGORY_SLUG,
    cat.CATEGORY_NAME,
    cat.CATEGORY_SLUG,
    dep.DEPARTMENT_NAME,

    -- IDs for joining
    p.CATEGORY_ID,
    p.SUBCATEGORY_ID,
    p.DEPARTMENT_ID,

    -- Price tiers
    CASE
        WHEN p.PRICE <   25 THEN 'Budget'
        WHEN p.PRICE <  100 THEN 'Mid-Range'
        WHEN p.PRICE <  500 THEN 'Premium'
        ELSE                     'Luxury'
    END                                                             AS price_tier,

    p._LOADED_AT

FROM ANALYTICS.RAW.PRODUCTS                         p
LEFT JOIN ANALYTICS.MARTS.PRODUCT_SUBCATEGORIES    sub ON p.SUBCATEGORY_ID = sub.SUBCATEGORY_ID
LEFT JOIN ANALYTICS.MARTS.PRODUCT_CATEGORIES       cat ON p.CATEGORY_ID    = cat.CATEGORY_ID
LEFT JOIN ANALYTICS.MARTS.PRODUCT_DEPARTMENTS      dep ON p.DEPARTMENT_ID  = dep.DEPARTMENT_ID;

-- ── Grant permissions on new objects ─────────────────────────────────────────
GRANT SELECT ON TABLE ANALYTICS.MARTS.PRODUCT_DEPARTMENTS   TO ROLE DATA_ANALYST;
GRANT SELECT ON TABLE ANALYTICS.MARTS.PRODUCT_CATEGORIES    TO ROLE DATA_ANALYST;
GRANT SELECT ON TABLE ANALYTICS.MARTS.PRODUCT_SUBCATEGORIES TO ROLE DATA_ANALYST;
GRANT SELECT ON TABLE ANALYTICS.MARTS.PRODUCT_INVENTORY     TO ROLE DATA_ANALYST;
GRANT SELECT ON VIEW  ANALYTICS.MARTS.DIM_PRODUCTS_FULL     TO ROLE DATA_ANALYST;

GRANT ALL ON TABLE ANALYTICS.MARTS.PRODUCT_DEPARTMENTS      TO ROLE DATA_ENGINEER;
GRANT ALL ON TABLE ANALYTICS.MARTS.PRODUCT_CATEGORIES       TO ROLE DATA_ENGINEER;
GRANT ALL ON TABLE ANALYTICS.MARTS.PRODUCT_SUBCATEGORIES    TO ROLE DATA_ENGINEER;
GRANT ALL ON TABLE ANALYTICS.MARTS.PRODUCT_INVENTORY        TO ROLE DATA_ENGINEER;
