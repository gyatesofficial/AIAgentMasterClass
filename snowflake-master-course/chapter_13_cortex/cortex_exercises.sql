-- =============================================================================
-- Chapter 13: Snowflake Cortex – All Features
-- Snowflake Master Course
-- =============================================================================
-- Prerequisites:
--   USE ROLE    SYSADMIN;
--   USE DATABASE ANALYTICS;
--   USE SCHEMA   PUBLIC;
--   USE WAREHOUSE COMPUTE_WH;
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Exercise 1: COMPLETE – Simple prompt
-- Ask the LLM a straightforward question
-- ---------------------------------------------------------------------------
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'mistral-large2',
    'Explain what a Snowflake Virtual Warehouse is in two sentences.'
) AS llm_response;


-- ---------------------------------------------------------------------------
-- Exercise 2: COMPLETE – System prompt + JSON extraction
-- Force the model to respond in strict JSON for downstream parsing
-- ---------------------------------------------------------------------------
SELECT
    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large2',
        [
            {
                'role': 'system',
                'content': 'You are a data extraction assistant. Always respond with valid JSON only, no prose.'
            },
            {
                'role': 'user',
                'content': 'Extract the company name, invoice number, and total amount from this text: "Invoice #INV-20240315 from Acme Corp for consulting services totaling $4,250.00 due March 31 2024."'
            }
        ],
        { 'temperature': 0, 'max_tokens': 200 }
    ) AS extracted_json;


-- ---------------------------------------------------------------------------
-- Exercise 3: SUMMARIZE – Condense a long text field
-- Summarize product descriptions stored in a table
-- ---------------------------------------------------------------------------
SELECT
    PRODUCT_ID,
    PRODUCT_NAME,
    LEFT(DESCRIPTION, 100) || '...'                             AS description_preview,
    SNOWFLAKE.CORTEX.SUMMARIZE(DESCRIPTION)                     AS summary
FROM ANALYTICS.MARTS.DIM_PRODUCTS
WHERE LENGTH(DESCRIPTION) > 200
LIMIT 5;


-- ---------------------------------------------------------------------------
-- Exercise 4: SENTIMENT – Score customer reviews
-- Returns a float between -1 (negative) and 1 (positive)
-- ---------------------------------------------------------------------------
SELECT
    REVIEW_ID,
    CUSTOMER_ID,
    LEFT(REVIEW_TEXT, 80) || '...'                              AS review_preview,
    SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT)                     AS sentiment_score,
    CASE
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) >=  0.3 THEN 'POSITIVE'
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) <= -0.3 THEN 'NEGATIVE'
        ELSE 'NEUTRAL'
    END                                                          AS sentiment_label
FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS
ORDER BY sentiment_score ASC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- Exercise 5: TRANSLATE – Translate review text to English
-- Useful for a global product with multi-language reviews
-- ---------------------------------------------------------------------------
SELECT
    REVIEW_ID,
    SOURCE_LANGUAGE,
    REVIEW_TEXT                                                   AS original_text,
    SNOWFLAKE.CORTEX.TRANSLATE(REVIEW_TEXT, SOURCE_LANGUAGE, 'en') AS english_translation
FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS
WHERE SOURCE_LANGUAGE != 'en'
LIMIT 10;


-- ---------------------------------------------------------------------------
-- Exercise 6: EXTRACT_ANSWER – Question answering from context
-- Pull a specific fact out of an unstructured document
-- ---------------------------------------------------------------------------
SELECT
    DOC_ID,
    SNOWFLAKE.CORTEX.EXTRACT_ANSWER(
        DOCUMENT_TEXT,
        'What is the payment due date?'
    )                                                             AS due_date_answer,
    SNOWFLAKE.CORTEX.EXTRACT_ANSWER(
        DOCUMENT_TEXT,
        'What is the total invoice amount?'
    )                                                             AS invoice_amount_answer
FROM ANALYTICS.PUBLIC.INVOICE_DOCUMENTS
LIMIT 5;


-- ---------------------------------------------------------------------------
-- Exercise 7: CLASSIFY_TEXT – Categorize support tickets
-- Map free-text tickets to a predefined set of categories
-- ---------------------------------------------------------------------------
SELECT
    TICKET_ID,
    LEFT(TICKET_TEXT, 80)                                         AS ticket_preview,
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        TICKET_TEXT,
        ['Billing', 'Technical', 'Shipping', 'Returns', 'General Inquiry']
    )['label']::STRING                                            AS ticket_category,
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        TICKET_TEXT,
        ['Billing', 'Technical', 'Shipping', 'Returns', 'General Inquiry']
    )['score']::FLOAT                                             AS confidence_score
FROM ANALYTICS.PUBLIC.SUPPORT_TICKETS
LIMIT 20;


-- ---------------------------------------------------------------------------
-- Exercise 8: Batch LLM processing – Apply COMPLETE to every row
-- Generate a personalized email subject line for each customer
-- ---------------------------------------------------------------------------
SELECT
    CUSTOMER_ID,
    FULL_NAME,
    SEGMENT,
    SNOWFLAKE.CORTEX.COMPLETE(
        'snowflake-arctic',
        'Write a one-sentence personalized email subject line for a '
            || SEGMENT || ' tier customer named ' || FULL_NAME
            || ' about their upcoming renewal. Be friendly and concise.'
    )                                                             AS email_subject
FROM ANALYTICS.MARTS.DIM_CUSTOMERS
WHERE IS_ACTIVE = TRUE
LIMIT 10;


-- ---------------------------------------------------------------------------
-- Exercise 9: Parse JSON from LLM response with TRY_PARSE_JSON
-- Safely extract structured fields from LLM output
-- ---------------------------------------------------------------------------
WITH llm_output AS (
    SELECT
        ORDER_ID,
        SNOWFLAKE.CORTEX.COMPLETE(
            'mistral-large2',
            [
                {
                    'role': 'system',
                    'content': 'Respond only with a JSON object with fields: risk_level (LOW/MEDIUM/HIGH), reason (string), recommended_action (string).'
                },
                {
                    'role': 'user',
                    'content': 'Assess fraud risk for an order: amount=$' || AMOUNT::STRING
                        || ', country=' || COUNTRY_CODE
                        || ', is_new_customer=' || IS_NEW_CUSTOMER::STRING
                }
            ],
            { 'temperature': 0 }
        )                                                          AS raw_json
    FROM ANALYTICS.PUBLIC.ORDERS_RISK_STAGING
    LIMIT 20
)
SELECT
    ORDER_ID,
    TRY_PARSE_JSON(raw_json)                                      AS parsed,
    TRY_PARSE_JSON(raw_json)['risk_level']::STRING                AS risk_level,
    TRY_PARSE_JSON(raw_json)['reason']::STRING                    AS reason,
    TRY_PARSE_JSON(raw_json)['recommended_action']::STRING        AS recommended_action
FROM llm_output;


-- ---------------------------------------------------------------------------
-- Exercise 10: Create a Cortex Search Service
-- Index your product catalog for semantic search
-- ---------------------------------------------------------------------------
CREATE OR REPLACE CORTEX SEARCH SERVICE ANALYTICS.PUBLIC.PRODUCT_SEARCH
    ON PRODUCT_NAME, DESCRIPTION, CATEGORY
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            PRODUCT_ID,
            PRODUCT_NAME,
            DESCRIPTION,
            CATEGORY,
            PRICE
        FROM ANALYTICS.MARTS.DIM_PRODUCTS
        WHERE IS_ACTIVE = TRUE
    );

-- Query the Cortex Search Service via SQL
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'ANALYTICS.PUBLIC.PRODUCT_SEARCH',
        '{
            "query": "wireless noise cancelling headphones",
            "columns": ["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PRICE"],
            "limit": 5
        }'
    )
) AS search_results;


-- ---------------------------------------------------------------------------
-- Exercise 11: ML FORECAST – Create a forecast model
-- Predict next 30 days of daily revenue
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SNOWFLAKE.ML.FORECAST ANALYTICS.PUBLIC.REVENUE_FORECAST (
    INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_REVENUE_FOR_FORECAST'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_REVENUE'
);

-- Underlying view for the forecast model
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.DAILY_REVENUE_FOR_FORECAST AS
SELECT
    ORDER_DATE,
    SUM(AMOUNT) AS DAILY_REVENUE
FROM ANALYTICS.MARTS.FCT_ORDERS
WHERE STATUS = 'COMPLETED'
GROUP BY ORDER_DATE
ORDER BY ORDER_DATE;


-- ---------------------------------------------------------------------------
-- Exercise 12: ML FORECAST – Call the model to generate predictions
-- ---------------------------------------------------------------------------
CALL ANALYTICS.PUBLIC.REVENUE_FORECAST!FORECAST(
    FORECASTING_PERIODS => 30,
    CONFIG_OBJECT       => { 'prediction_interval': 0.9 }
);

-- Retrieve forecast results from the last call
SELECT *
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY TS;


-- ---------------------------------------------------------------------------
-- Exercise 13: ML ANOMALY_DETECTION – Create and call
-- Detect anomalous spikes in daily order counts
-- ---------------------------------------------------------------------------
-- Create the anomaly detection model (trained on labeled data)
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION ANALYTICS.PUBLIC.ORDER_ANOMALY_DETECTOR (
    INPUT_DATA    => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_ORDERS',
    LABEL_COLNAME     => 'IS_ANOMALY'   -- set to NULL for unsupervised mode
);

-- Source view
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS AS
SELECT
    ORDER_DATE,
    COUNT(*)                                              AS DAILY_ORDERS,
    NULL::BOOLEAN                                         AS IS_ANOMALY
FROM ANALYTICS.MARTS.FCT_ORDERS
GROUP BY ORDER_DATE;

-- Run detection on new (held-out) data
CALL ANALYTICS.PUBLIC.ORDER_ANOMALY_DETECTOR!DETECT_ANOMALIES(
    INPUT_DATA    => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_ORDERS'
);

SELECT *
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE IS_ANOMALY = TRUE
ORDER BY TS;


-- ---------------------------------------------------------------------------
-- Exercise 14: ML CLASSIFICATION – Create and call
-- Predict customer churn (binary classification)
-- ---------------------------------------------------------------------------
-- Training step (uses labeled historical data)
CREATE OR REPLACE SNOWFLAKE.ML.CLASSIFICATION ANALYTICS.PUBLIC.CHURN_CLASSIFIER (
    INPUT_DATA  => SYSTEM$REFERENCE('TABLE', 'ANALYTICS.ML_FEATURES.CUSTOMER_CHURN_FEATURES'),
    TARGET_COLNAME => 'IS_CHURNED'
);

-- Score new customers
CALL ANALYTICS.PUBLIC.CHURN_CLASSIFIER!PREDICT(
    INPUT_DATA    => SYSTEM$REFERENCE('TABLE', 'ANALYTICS.ML_FEATURES.NEW_CUSTOMERS_TO_SCORE'),
    PREDICTED_CLASS_COLNAME => 'PREDICTED_CHURN',
    PREDICTED_SCORE_COLNAME => 'CHURN_PROBABILITY'
);

SELECT *
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY CHURN_PROBABILITY DESC
LIMIT 20;

-- Show feature importances from the trained model
CALL ANALYTICS.PUBLIC.CHURN_CLASSIFIER!SHOW_FEATURE_IMPORTANCE();
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));


-- ---------------------------------------------------------------------------
-- Exercise 15: Complete Cortex pipeline
-- Ingest reviews → compute sentiment → classify → aggregate by sentiment
-- ---------------------------------------------------------------------------

-- Step 1: Ensure reviews table exists and is populated
-- (In practice, this is loaded via Snowpipe or COPY INTO)
CREATE TABLE IF NOT EXISTS ANALYTICS.PUBLIC.CUSTOMER_REVIEWS (
    REVIEW_ID       NUMBER AUTOINCREMENT PRIMARY KEY,
    CUSTOMER_ID     VARCHAR(50),
    ORDER_ID        VARCHAR(50),
    PRODUCT_ID      VARCHAR(50),
    REVIEW_TEXT     VARCHAR(10000),
    REVIEW_DATE     DATE,
    SOURCE_LANGUAGE VARCHAR(10) DEFAULT 'en',
    CREATED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Step 2: Create enriched review view with sentiment + classification
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.REVIEWS_ENRICHED AS
SELECT
    REVIEW_ID,
    CUSTOMER_ID,
    PRODUCT_ID,
    REVIEW_DATE,
    REVIEW_TEXT,

    -- Sentiment score (-1 to 1)
    SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT)                       AS sentiment_score,

    -- Sentiment label bucket
    CASE
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) >=  0.3 THEN 'POSITIVE'
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) <= -0.3 THEN 'NEGATIVE'
        ELSE 'NEUTRAL'
    END                                                            AS sentiment_label,

    -- Text classification: what topic is the review about?
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        REVIEW_TEXT,
        ['Product Quality', 'Shipping Speed', 'Customer Service', 'Pricing', 'Other']
    )['label']::STRING                                             AS review_topic,

    -- Auto-generated summary (for long reviews)
    CASE
        WHEN LENGTH(REVIEW_TEXT) > 300
        THEN SNOWFLAKE.CORTEX.SUMMARIZE(REVIEW_TEXT)
        ELSE REVIEW_TEXT
    END                                                            AS review_summary

FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS;

-- Step 3: Aggregate sentiment by product for executive dashboard
SELECT
    p.PRODUCT_NAME,
    p.CATEGORY,
    COUNT(r.REVIEW_ID)                                             AS review_count,
    ROUND(AVG(r.sentiment_score), 3)                               AS avg_sentiment,
    SUM(CASE WHEN r.sentiment_label = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_count,
    SUM(CASE WHEN r.sentiment_label = 'NEUTRAL'  THEN 1 ELSE 0 END) AS neutral_count,
    SUM(CASE WHEN r.sentiment_label = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count,
    -- Percentage positive
    ROUND(
        100.0 * SUM(CASE WHEN r.sentiment_label = 'POSITIVE' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1
    )                                                              AS pct_positive
FROM ANALYTICS.PUBLIC.REVIEWS_ENRICHED r
JOIN ANALYTICS.MARTS.DIM_PRODUCTS       p ON r.PRODUCT_ID = p.PRODUCT_ID
GROUP BY 1, 2
ORDER BY avg_sentiment DESC;
