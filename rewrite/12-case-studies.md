# Appendix B: Real-World Case Studies for Data Engineers

## Why Case Studies Matter

Every module in this course teaches a concept in isolation: data modeling in Module 1, SQL in Module 2, orchestration in Module 8. But real data engineering problems do not arrive in neatly labeled modules. They arrive as messy business requirements that demand you combine multiple skills simultaneously.

These four case studies show how the concepts from Modules 0-10 come together in production systems. Each case study is structured the same way: the business context, the data architecture, the specific technical decisions (mapped to course modules), the startup vs. enterprise approach, and the lessons learned.

These are not hypothetical. They are composites based on real systems I have seen at real companies, simplified for clarity but faithful to the actual patterns and trade-offs.

> **Key Takeaway:** Read these case studies with your capstone project in mind. The e-commerce case study directly mirrors your Module 10 capstone. The others show how the same foundational skills apply in different domains.

---

## Case Study 1: E-Commerce Data Platform

### This Is Your Capstone at Production Scale

If you completed the Module 10 capstone project (building an e-commerce analytics pipeline), this case study shows what that system looks like when a real company runs it in production with 10 million customers, 50 data team members, and $2M/year in data platform costs.

### Business Context

**Company:** Mid-market e-commerce retailer, $500M annual revenue, 10M customers, 200K orders/day.

**Data team:** 8 data engineers, 15 analysts, 5 data scientists, 3 analytics engineers, and a head of data.

**Business requirements:**
- Marketing needs customer segmentation and attribution reporting (which campaigns drive purchases?)
- Operations needs inventory forecasting and supply chain analytics
- Finance needs daily revenue reporting with 99.9% accuracy (this feeds SEC filings)
- Product needs A/B test analysis for website experiments
- Executives need a daily KPI dashboard available by 7 AM ET

### The Architecture

```
[Shopify API]  ──┐
[Stripe API]   ──┤
[Google Ads]   ──┤──→ [Airbyte Cloud] ──→ [S3 Raw Layer] ──→ [Snowflake Raw]
[Zendesk API]  ──┤                                               │
[PostgreSQL]   ──┘                                               ▼
                                                          [dbt (Airflow)]
                                                               │
                                               ┌───────────────┼───────────────┐
                                               ▼               ▼               ▼
                                        [Staging Layer]  [Intermediate]  [Marts Layer]
                                                                               │
                                                          ┌────────────────────┼──────────┐
                                                          ▼                    ▼          ▼
                                                    [Tableau]           [Python/ML]  [Reverse ETL]
                                                   (Dashboards)        (Forecasting) (Hightouch → Braze)
```

### Module-by-Module Breakdown

**Module 1 (Data Modeling):** The data model is a classic star schema with these core fact tables:

```sql
-- fact_orders: grain is one row per order line item
-- This is the most-queried table in the warehouse
CREATE TABLE marts.fact_orders (
    order_key           BIGINT,         -- Surrogate key
    order_id            VARCHAR,        -- Business key from Shopify
    order_line_id       VARCHAR,
    order_date_key      INT,            -- FK to dim_date
    customer_key        BIGINT,         -- FK to dim_customer (SCD Type 2)
    product_key         BIGINT,         -- FK to dim_product
    channel_key         INT,            -- FK to dim_channel
    promotion_key       INT,            -- FK to dim_promotion
    quantity            INT,
    unit_price          DECIMAL(10,2),
    discount_amount     DECIMAL(10,2),
    tax_amount          DECIMAL(10,2),
    shipping_amount     DECIMAL(10,2),
    gross_revenue       DECIMAL(10,2),  -- quantity * unit_price
    net_revenue         DECIMAL(10,2),  -- gross - discount
    cost_of_goods       DECIMAL(10,2),
    gross_margin        DECIMAL(10,2),  -- net_revenue - cogs
    is_first_order      BOOLEAN,        -- Derived: is this the customer's first order?
    is_returned         BOOLEAN,
    _loaded_at          TIMESTAMP       -- Pipeline metadata
);

-- dim_customer: SCD Type 2 tracks address changes (for regional analytics)
-- and loyalty tier changes (for retention analysis)
CREATE TABLE marts.dim_customer (
    customer_key        BIGINT,         -- Surrogate key
    customer_id         VARCHAR,        -- Business key
    email_hash          VARCHAR,        -- Hashed for privacy
    first_order_date    DATE,
    customer_segment    VARCHAR,        -- 'new', 'active', 'at_risk', 'churned'
    lifetime_orders     INT,
    lifetime_revenue    DECIMAL(12,2),
    loyalty_tier        VARCHAR,        -- 'bronze', 'silver', 'gold', 'platinum'
    state               VARCHAR,
    country             VARCHAR,
    is_current          BOOLEAN,        -- SCD Type 2
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP
);
```

The customer segmentation uses a behavioral model: customers with no orders in 90 days are "at risk," and 180 days means "churned." This is recalculated daily by a dbt model.

**Module 2 (SQL):** The most complex queries in this system use window functions heavily. Here is the actual query that calculates customer cohort retention, which is the most requested report from marketing:

```sql
-- Customer cohort retention analysis
-- This query shows, for each monthly cohort, what % of customers
-- return to purchase in subsequent months
WITH customer_cohorts AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', first_order_date) AS cohort_month
    FROM marts.dim_customer
    WHERE is_current = TRUE
),
monthly_activity AS (
    SELECT DISTINCT
        o.customer_id,
        DATE_TRUNC('month', o.order_date) AS activity_month
    FROM marts.fact_orders o
),
cohort_retention AS (
    SELECT
        c.cohort_month,
        DATEDIFF('month', c.cohort_month, a.activity_month) AS months_since_first,
        COUNT(DISTINCT a.customer_id) AS active_customers
    FROM customer_cohorts c
    INNER JOIN monthly_activity a ON c.customer_id = a.customer_id
    WHERE a.activity_month >= c.cohort_month
    GROUP BY 1, 2
)
SELECT
    cohort_month,
    months_since_first,
    active_customers,
    FIRST_VALUE(active_customers) OVER (
        PARTITION BY cohort_month ORDER BY months_since_first
    ) AS cohort_size,
    ROUND(100.0 * active_customers / FIRST_VALUE(active_customers) OVER (
        PARTITION BY cohort_month ORDER BY months_since_first
    ), 1) AS retention_pct
FROM cohort_retention
ORDER BY cohort_month, months_since_first;
```

**Module 3 (Python):** Python is used for custom Airbyte connectors where the off-the-shelf ones do not work (a common reality). The Shopify API connector needed custom logic for handling API rate limits and paginating through 200K daily orders.

**Module 4 (Warehousing):** Snowflake is the warehouse. Three separate warehouses handle different workloads:
- `ETL_WH` (Large, auto-suspend 60s): Runs dbt models overnight
- `BI_WH` (Small, multi-cluster 1-4, auto-suspend 120s): Serves Tableau dashboards
- `ADHOC_WH` (Medium, auto-suspend 60s, resource monitor at 500 credits/month): Analyst queries

**Module 5 (Data Lake):** S3 serves as the raw layer. All Airbyte output lands in S3 as Parquet files partitioned by date before being loaded into Snowflake raw tables. This means if Snowflake has an issue, the raw data is still safe in S3.

**Module 6 (dbt):** The dbt project has 180+ models organized into staging, intermediate, and marts layers. Incremental models handle the high-volume tables (fact_orders, fact_page_views). The most critical dbt configuration:

```yaml
# dbt_project.yml (partial)
models:
  ecommerce:
    staging:
      +materialized: view          # Staging is always views (no storage cost)
    intermediate:
      +materialized: table         # Intermediate materializes for performance
    marts:
      +materialized: incremental   # Marts are incremental where possible
      +on_schema_change: append_new_columns
```

**Module 7 (Spark):** Not used in the primary pipeline (Snowflake handles the transformation volume). Spark is used by the data science team for large-scale feature engineering and model training on customer behavior data, running on EMR with spot instances.

**Module 8 (Orchestration):** Airflow manages the entire pipeline with a carefully designed DAG dependency chain:

```
extract_shopify → load_raw_orders → dbt_staging → dbt_intermediate → dbt_marts → dbt_test → notify_slack
extract_stripe  ↗                                                                            ↗
extract_ga      ↗                                                                  alert_on_failure
```

The pipeline runs at 2 AM ET and must complete by 6:30 AM so dashboards are fresh by 7 AM. SLA enforcement: if the DAG has not completed by 6 AM, PagerDuty alerts the on-call data engineer.

**Module 9 (Data Quality):** Every dbt model has tests. The most critical tests on fact_orders:

```yaml
models:
  - name: fact_orders
    tests:
      - dbt_utils.recency:
          datepart: hour
          field: _loaded_at
          interval: 6  # Fail if no data in last 6 hours
    columns:
      - name: net_revenue
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: -1000   # Allow reasonable refunds
              max_value: 50000   # Flag outliers
      - name: order_id
        tests:
          - unique
          - not_null
```

Additionally, a daily reconciliation query compares total revenue in fact_orders against the Shopify API to ensure the pipeline has not dropped or duplicated orders. This check is non-negotiable because finance uses this data for SEC reporting.

**Module 10 (Capstone):** This entire system is what your capstone project aspires to become. The key difference between your capstone and this production system: operational maturity. This system has monitoring, alerting, on-call rotation, runbooks for common failures, cost controls, and a data catalog.

### Startup vs. Enterprise Approach

| Aspect | Startup (Pre-Series B) | Enterprise (This Case Study) |
|--------|----------------------|----------------------------|
| Team size | 1-2 data engineers | 8 DEs + 15 analysts + 5 DS |
| Warehouse | BigQuery (serverless, no admin) | Snowflake (more control, better for large teams) |
| Ingestion | Fivetran or manual scripts | Airbyte Cloud + custom connectors |
| Transformation | dbt Cloud (managed) | dbt Core on Airflow (self-managed for flexibility) |
| Data model | Single fact table, 3-4 dimensions | 15+ fact tables, 30+ dimensions, SCD Type 2 |
| Quality | dbt tests only | dbt tests + reconciliation + anomaly detection |
| Cost | $500-$2K/month | $100K-$200K/month |
| Time to build | 2-4 weeks for MVP | 6-12 months for full platform |

**The startup version of this system** would be: Shopify data → Fivetran → BigQuery → dbt Cloud → Looker. One data engineer, $1K/month, built in two weeks. It lacks the sophistication but delivers 80% of the value.

### Lessons Learned

1. **Data reconciliation against source systems is non-negotiable.** When your data feeds financial reporting, you cannot tolerate discrepancies. Build automated reconciliation from day one.
2. **SCD Type 2 is worth the complexity for customer data.** Marketing needs to know that a customer was in the "gold" tier when they made a purchase, not just their current tier.
3. **Separate your BI warehouse from your ETL warehouse.** The most common production incident was Tableau dashboards timing out because a large ad-hoc query was consuming all the compute.
4. **Invest in incremental models early.** The team started with full-refresh dbt models. At 200K orders/day, the full refresh took 3 hours. Switching to incremental reduced it to 20 minutes.

---

## Case Study 2: Fintech Real-Time Fraud Detection Pipeline

### When Latency Is Measured in Dollars

In e-commerce, a slow dashboard is an inconvenience. In fraud detection, a slow pipeline means money stolen from customers. This case study shows how a fintech company built a real-time fraud detection system where the data pipeline IS the product.

### Business Context

**Company:** Digital payments processor, handling 15K transactions/second at peak, $80B annual transaction volume.

**Data team:** 6 data engineers, 4 ML engineers, 3 platform engineers.

**Requirements:**
- Every transaction must receive a fraud/not-fraud decision in under 100ms
- False positive rate must stay below 1.5% (blocking legitimate transactions costs revenue and customer trust)
- Must detect new fraud patterns within hours, not days
- Full audit trail required for regulatory compliance (PCI DSS, SOX)
- System must handle 3x traffic spikes during holidays (Black Friday, Cyber Monday)

### The Architecture

```
[Mobile App]     ──┐
[Web Checkout]   ──┤──→ [API Gateway] ──→ [Kafka] ──→ [Flink] ──→ [Decision Engine] ──→ [Response]
[Partner APIs]   ──┘         │                            │              │
                             │                            ▼              ▼
                             │                     [Feature Store]  [Audit Log]
                             │                      (Redis + S3)    (Kafka → S3)
                             │                            │
                             │                            ▼
                             │                     [ML Model Serving]
                             │                      (TorchServe/gRPC)
                             │                            │
                             ▼                            ▼
                      [Batch Pipeline]           [Model Training]
                    (Spark on EMR, daily)      (Spark + PyTorch, weekly)
                             │
                             ▼
                      [Snowflake]
                   (Analytics & Reporting)
```

### Module-by-Module Breakdown

**Module 1 (Data Modeling):** The transaction data model is unusual because it must serve both real-time scoring (denormalized for speed) and batch analytics (star schema for flexibility).

The real-time model in Redis is a flat, denormalized structure optimized for single-key lookups:

```json
{
  "user_id": "u_12345",
  "features": {
    "txn_count_1h": 7,
    "txn_count_24h": 23,
    "txn_amount_1h": 459.32,
    "txn_amount_24h": 1847.50,
    "unique_merchants_1h": 4,
    "unique_merchants_24h": 12,
    "max_txn_amount_24h": 299.99,
    "avg_txn_amount_30d": 67.42,
    "is_new_device": false,
    "is_new_merchant": true,
    "distance_from_last_txn_km": 3.2,
    "time_since_last_txn_seconds": 847
  },
  "updated_at": "2026-04-03T14:22:07Z"
}
```

The batch analytics model in Snowflake is a star schema:

```sql
-- fact_transactions: one row per transaction, used for analytics
CREATE TABLE marts.fact_transactions (
    transaction_key     BIGINT,
    transaction_id      VARCHAR,
    transaction_ts      TIMESTAMP,
    user_key            BIGINT,         -- FK to dim_user
    merchant_key        BIGINT,         -- FK to dim_merchant
    device_key          BIGINT,         -- FK to dim_device
    amount              DECIMAL(12,2),
    currency            VARCHAR(3),
    fraud_score         FLOAT,          -- ML model output (0-1)
    fraud_decision      VARCHAR,        -- 'approve', 'decline', 'review'
    is_fraud_confirmed  BOOLEAN,        -- Ground truth (labeled later)
    rule_triggers       ARRAY,          -- Which rules fired
    model_version       VARCHAR,        -- Which ML model version scored this
    latency_ms          INT,            -- End-to-end scoring latency
    _loaded_at          TIMESTAMP
);
```

**Module 2 (SQL):** The analytics team runs complex queries to evaluate model performance and identify fraud patterns. Here is the query that calculates the precision/recall curve by score threshold, which the ML team uses to tune the decision boundary:

```sql
-- Model performance by score threshold
-- This helps the ML team decide: at what fraud_score should we decline?
WITH thresholds AS (
    SELECT 0.1 AS threshold UNION ALL SELECT 0.2 UNION ALL SELECT 0.3
    UNION ALL SELECT 0.4 UNION ALL SELECT 0.5 UNION ALL SELECT 0.6
    UNION ALL SELECT 0.7 UNION ALL SELECT 0.8 UNION ALL SELECT 0.9
),
scored AS (
    SELECT
        t.threshold,
        f.is_fraud_confirmed,
        CASE WHEN f.fraud_score >= t.threshold THEN 1 ELSE 0 END AS predicted_fraud
    FROM marts.fact_transactions f
    CROSS JOIN thresholds t
    WHERE f.transaction_ts > DATEADD('day', -30, CURRENT_TIMESTAMP())
        AND f.is_fraud_confirmed IS NOT NULL  -- Only labeled transactions
)
SELECT
    threshold,
    SUM(CASE WHEN predicted_fraud = 1 AND is_fraud_confirmed THEN 1 ELSE 0 END) AS true_positives,
    SUM(CASE WHEN predicted_fraud = 1 AND NOT is_fraud_confirmed THEN 1 ELSE 0 END) AS false_positives,
    SUM(CASE WHEN predicted_fraud = 0 AND is_fraud_confirmed THEN 1 ELSE 0 END) AS false_negatives,
    -- Precision: of all we flagged, how many were actually fraud?
    ROUND(100.0 * SUM(CASE WHEN predicted_fraud = 1 AND is_fraud_confirmed THEN 1 ELSE 0 END)
        / NULLIF(SUM(predicted_fraud), 0), 2) AS precision_pct,
    -- Recall: of all actual fraud, how many did we catch?
    ROUND(100.0 * SUM(CASE WHEN predicted_fraud = 1 AND is_fraud_confirmed THEN 1 ELSE 0 END)
        / NULLIF(SUM(is_fraud_confirmed::INT), 0), 2) AS recall_pct
FROM scored
GROUP BY threshold
ORDER BY threshold;
```

**Module 3 (Python):** The Flink jobs are written in Java for performance, but the feature engineering pipeline, model training, and monitoring are all Python. The most critical Python component is the feature computation service that updates Redis:

```python
# Simplified feature computation -- runs inside Flink (via PyFlink)
# or as a standalone service consuming from Kafka
def compute_user_features(transaction: dict, current_features: dict) -> dict:
    """Update a user's real-time features based on a new transaction.

    This runs for every transaction (15K/second at peak).
    Must complete in under 5ms to stay within the latency budget.
    """
    now = transaction["timestamp"]
    amount = transaction["amount"]

    # Sliding window counters (approximate -- use HyperLogLog in production)
    features = current_features.copy()
    features["txn_count_1h"] = features.get("txn_count_1h", 0) + 1
    features["txn_count_24h"] = features.get("txn_count_24h", 0) + 1
    features["txn_amount_1h"] = features.get("txn_amount_1h", 0) + amount
    features["txn_amount_24h"] = features.get("txn_amount_24h", 0) + amount

    # Velocity checks
    last_txn_time = features.get("last_txn_timestamp")
    if last_txn_time:
        features["time_since_last_txn_seconds"] = (now - last_txn_time).total_seconds()

    # Geographic anomaly
    last_lat = features.get("last_txn_lat")
    last_lon = features.get("last_txn_lon")
    if last_lat and last_lon and transaction.get("lat"):
        features["distance_from_last_txn_km"] = haversine(
            last_lat, last_lon, transaction["lat"], transaction["lon"]
        )

    features["last_txn_timestamp"] = now
    features["last_txn_lat"] = transaction.get("lat")
    features["last_txn_lon"] = transaction.get("lon")

    return features
```

**Module 7 (Spark):** Spark runs the daily batch pipeline that:
1. Recomputes exact features for all users (the real-time approximate features drift over time)
2. Joins transactions with merchant data, device fingerprints, and chargeback reports
3. Creates training datasets for the ML models
4. Loads analytics-ready data into Snowflake

**Module 8 (Orchestration):** Airflow orchestrates the batch pipeline but NOT the real-time pipeline. The real-time pipeline runs continuously via Flink and is monitored by a separate system (Prometheus + Grafana). This is a critical architectural decision: batch orchestrators like Airflow are not designed for real-time systems.

**Module 9 (Data Quality):** Data quality in fraud detection is literally a matter of financial safety. The quality checks include:

- **Completeness:** Every transaction must have a fraud score. Missing scores mean unscored transactions are approved by default, creating a vulnerability.
- **Latency:** If scoring latency exceeds 100ms, transactions are routed to a fallback rules-only engine. The Flink job monitors its own p99 latency and emits alerts.
- **Model drift:** The batch pipeline compares the daily fraud rate against the model's predicted fraud rate. If they diverge by more than 2 percentage points, an alert fires and the ML team investigates.
- **Feature consistency:** The batch pipeline recomputes features exactly and compares them to the real-time approximations. Drift beyond 5% triggers a reconciliation job that corrects the real-time features.

### The Latency Budget

This is the single most important design artifact in this system:

| Component | Budget | Actual p99 | Notes |
|-----------|--------|-----------|-------|
| API Gateway → Kafka | 5ms | 3ms | Internal network, same AZ |
| Kafka → Flink | 5ms | 4ms | Consumer lag monitored |
| Feature lookup (Redis) | 5ms | 2ms | Redis cluster, local replica |
| ML inference (gRPC) | 30ms | 22ms | TorchServe with GPU, batched |
| Rules engine | 10ms | 7ms | In-memory rule evaluation |
| Decision → Response | 5ms | 3ms | Serialization + network |
| **Total** | **60ms** | **41ms** | **Budget: 100ms, headroom: 59ms** |

The 59ms of headroom is not waste. It absorbs spikes during Black Friday and allows for future feature additions without breaching the SLA.

### Startup vs. Enterprise Approach

| Aspect | Startup (Seed to Series A) | Enterprise (This Case Study) |
|--------|---------------------------|----------------------------|
| Fraud detection | Rules-only engine (no ML) | ML ensemble + rules + graph analysis |
| Latency target | 500ms (acceptable for most merchants) | 100ms (required by card networks) |
| Feature store | PostgreSQL with materialized views | Redis cluster + S3 feature archive |
| Model training | Scikit-learn on a laptop, weekly | PyTorch on Spark + GPU, daily |
| Monitoring | Basic alerting on fraud rate | Full observability stack (Prometheus, Grafana, PagerDuty) |
| Compliance | Basic logging | Full audit trail, PCI DSS Level 1, SOX |
| Cost | $2K-$5K/month | $150K-$300K/month |
| Team | 1-2 engineers | 13 engineers across three specialties |

**The startup version:** Transactions → PostgreSQL → Python rules engine → Decision. No ML, no streaming, no Redis. The rules engine checks: is the amount above $500? Is the card used in a new country? Is the velocity above 10 transactions/hour? This catches 60-70% of fraud. Good enough to get started. You can add ML later.

### Lessons Learned

1. **Start with rules, add ML later.** A simple rules engine catches the obvious fraud. ML catches the subtle fraud. But ML without rules is dangerous because ML models can be fooled by novel attack patterns.
2. **The feature store is the hardest part.** Keeping real-time features consistent with batch features is an ongoing engineering challenge. Budget 30% of your engineering time for this.
3. **Latency budgets prevent scope creep.** When someone says "let's add one more feature to the model," you can point to the latency budget and ask: "Which 5ms are you willing to give up?"
4. **Compliance is not optional in fintech.** PCI DSS requires encryption at rest and in transit, access logging, vulnerability scanning, and annual audits. This adds 20-30% overhead to every engineering decision. Factor it in from the start.

---

## Case Study 3: SaaS Analytics Platform (Product Analytics)

### Understanding User Behavior at Scale

Product analytics is the use case that makes data engineering directly visible to the entire company. When the CEO asks "how many users are active this week?" or the product manager asks "what is the conversion rate of our new onboarding flow?", the answer comes from the data platform you built.

### Business Context

**Company:** B2B SaaS product (project management tool), 500K active users, 2M events/day.

**Data team:** 4 data engineers, 8 analysts, 2 analytics engineers.

**Requirements:**
- Track every user interaction (page views, clicks, feature usage) via event tracking
- Self-service analytics for product managers (they should not need to ask a data engineer for basic metrics)
- Experimentation platform for A/B tests on product features
- Funnel analysis: sign-up → onboarding → activation → retention → expansion
- Usage-based billing: compute each customer's monthly usage for invoicing

### The Architecture

```
[Web App]        ──┐
[Mobile App]     ──┤──→ [Segment] ──→ [S3 Raw] ──→ [Snowflake]
[Backend Events] ──┘        │              │            │
                            │              │            ▼
                            ▼              │     [dbt (daily + hourly)]
                     [Amplitude]           │            │
                   (Real-time product      │     ┌──────┼──────┐
                    analytics)             │     ▼      ▼      ▼
                                           │  [Marts] [Billing] [Experiments]
                                           │     │      │          │
                                           │     ▼      ▼          ▼
                                           │  [Mode]  [Stripe]  [Statsig]
                                           │ (Self-    (Usage    (A/B test
                                           │  serve)   billing)  analysis)
                                           ▼
                                    [Spark on EMR]
                                   (Heavy aggregations,
                                    ML features, backfills)
```

### The Event Table: The Heart of Product Analytics

Every SaaS analytics platform revolves around an event table. Getting this right is the single most important data modeling decision:

```sql
-- The core event table: one row per user interaction
-- This table receives 2M+ rows/day and is the source of truth
-- for all product analytics
CREATE TABLE raw.events (
    event_id        VARCHAR,        -- UUID, globally unique
    event_name      VARCHAR,        -- 'page_viewed', 'button_clicked', 'feature_used'
    event_timestamp TIMESTAMP,
    user_id         VARCHAR,        -- Authenticated user (null if anonymous)
    anonymous_id    VARCHAR,        -- Device/session ID (always present)
    session_id      VARCHAR,
    properties      VARIANT,        -- JSON blob of event-specific properties
    context         VARIANT,        -- Device, browser, IP, UTM params
    received_at     TIMESTAMP,      -- When Segment received the event
    _loaded_at      TIMESTAMP       -- When our pipeline loaded it
);

-- Example event:
-- event_name: 'project_created'
-- properties: {"project_name": "Q2 Launch", "template": "kanban", "team_size": 5}
-- context: {"browser": "Chrome", "os": "macOS", "utm_source": "google"}
```

**Why VARIANT/JSON for properties?** Because every event type has different properties. A "page_viewed" event has `page_url` and `referrer`. A "project_created" event has `project_name` and `template`. Enforcing a rigid schema across hundreds of event types is impractical. The VARIANT column lets you store structured data flexibly, and Snowflake can query inside it efficiently.

**Module 2 (SQL):** The most common product analytics queries are funnel analyses and retention calculations. Here is the activation funnel that the product team reviews weekly:

```sql
-- Activation funnel: what % of new signups complete each onboarding step?
-- This directly drives product decisions about onboarding UX
WITH signups AS (
    SELECT
        user_id,
        MIN(event_timestamp) AS signup_ts
    FROM raw.events
    WHERE event_name = 'account_created'
        AND event_timestamp > DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY user_id
),
funnel_steps AS (
    SELECT
        s.user_id,
        s.signup_ts,
        -- Step 1: Created an account (100% by definition)
        TRUE AS step_1_signup,
        -- Step 2: Completed profile setup
        MAX(CASE WHEN e.event_name = 'profile_completed'
            AND e.event_timestamp <= DATEADD('day', 7, s.signup_ts)
            THEN TRUE ELSE FALSE END) AS step_2_profile,
        -- Step 3: Created first project
        MAX(CASE WHEN e.event_name = 'project_created'
            AND e.event_timestamp <= DATEADD('day', 7, s.signup_ts)
            THEN TRUE ELSE FALSE END) AS step_3_project,
        -- Step 4: Invited a team member
        MAX(CASE WHEN e.event_name = 'team_member_invited'
            AND e.event_timestamp <= DATEADD('day', 7, s.signup_ts)
            THEN TRUE ELSE FALSE END) AS step_4_invite,
        -- Step 5: Active for 3+ days in first week (activation!)
        CASE WHEN COUNT(DISTINCT CASE WHEN e.event_timestamp <= DATEADD('day', 7, s.signup_ts)
            THEN DATE_TRUNC('day', e.event_timestamp) END) >= 3
            THEN TRUE ELSE FALSE END AS step_5_activated
    FROM signups s
    LEFT JOIN raw.events e ON s.user_id = e.user_id
    GROUP BY s.user_id, s.signup_ts
)
SELECT
    COUNT(*) AS total_signups,
    SUM(step_2_profile::INT) AS completed_profile,
    ROUND(100.0 * SUM(step_2_profile::INT) / COUNT(*), 1) AS pct_profile,
    SUM(step_3_project::INT) AS created_project,
    ROUND(100.0 * SUM(step_3_project::INT) / COUNT(*), 1) AS pct_project,
    SUM(step_4_invite::INT) AS invited_team,
    ROUND(100.0 * SUM(step_4_invite::INT) / COUNT(*), 1) AS pct_invite,
    SUM(step_5_activated::INT) AS activated,
    ROUND(100.0 * SUM(step_5_activated::INT) / COUNT(*), 1) AS pct_activated
FROM funnel_steps;
```

**Module 6 (dbt):** The dbt project has two run frequencies:
- **Hourly:** Core event rollups and near-real-time metrics (active users, feature usage counts)
- **Daily:** Full funnel calculations, retention cohorts, billing aggregations

```sql
-- dbt model: intermediate/int_daily_user_activity.sql
-- Incremental model that summarizes daily user activity
-- Used by retention, engagement, and billing models downstream
{{
    config(
        materialized='incremental',
        unique_key=['user_id', 'activity_date'],
        incremental_strategy='merge'
    )
}}

SELECT
    user_id,
    DATE_TRUNC('day', event_timestamp) AS activity_date,
    COUNT(*) AS total_events,
    COUNT(DISTINCT event_name) AS distinct_events,
    COUNT(DISTINCT session_id) AS sessions,
    MIN(event_timestamp) AS first_event_at,
    MAX(event_timestamp) AS last_event_at,
    SUM(CASE WHEN event_name LIKE 'feature_%' THEN 1 ELSE 0 END) AS feature_events,
    ARRAY_AGG(DISTINCT event_name) AS event_types
FROM raw.events
WHERE user_id IS NOT NULL
{% if is_incremental() %}
    AND event_timestamp > (SELECT MAX(last_event_at) FROM {{ this }})
{% endif %}
GROUP BY 1, 2
```

**Usage-based billing** (a unique requirement for SaaS) uses this daily activity data to compute each customer's monthly invoice:

```sql
-- marts/mart_monthly_billing.sql
-- Computes usage metrics per customer account per month
-- Feeds directly into the Stripe billing integration
SELECT
    a.account_id,
    DATE_TRUNC('month', d.activity_date) AS billing_month,
    COUNT(DISTINCT d.user_id) AS active_users,
    SUM(d.total_events) AS total_events,
    SUM(d.sessions) AS total_sessions,
    -- Billing tier based on active users
    CASE
        WHEN COUNT(DISTINCT d.user_id) <= 5 THEN 'free'
        WHEN COUNT(DISTINCT d.user_id) <= 25 THEN 'team'
        WHEN COUNT(DISTINCT d.user_id) <= 100 THEN 'business'
        ELSE 'enterprise'
    END AS billing_tier,
    -- Calculated price
    CASE
        WHEN COUNT(DISTINCT d.user_id) <= 5 THEN 0
        WHEN COUNT(DISTINCT d.user_id) <= 25 THEN COUNT(DISTINCT d.user_id) * 12
        WHEN COUNT(DISTINCT d.user_id) <= 100 THEN COUNT(DISTINCT d.user_id) * 10
        ELSE COUNT(DISTINCT d.user_id) * 8  -- Volume discount
    END AS monthly_charge_usd
FROM {{ ref('int_daily_user_activity') }} d
JOIN {{ ref('dim_user_accounts') }} a ON d.user_id = a.user_id
GROUP BY 1, 2
```

**Module 9 (Data Quality):** When your event data drives billing, quality is financial. The critical quality checks:

1. **Event volume anomaly detection:** If daily event volume drops more than 30% from the 7-day average, alert immediately. A tracking code bug can silently stop sending events, leading to under-billing customers (revenue loss) or under-counting usage (wrong product decisions).
2. **Schema validation:** Every event must have `event_id`, `event_name`, `event_timestamp`, and `user_id` or `anonymous_id`. Events failing validation go to a dead-letter queue for investigation.
3. **Billing reconciliation:** Monthly billing totals are compared against Stripe records. Any discrepancy over $100 triggers a manual review.

### Startup vs. Enterprise Approach

| Aspect | Startup (Early stage) | Enterprise (This Case Study) |
|--------|----------------------|----------------------------|
| Event tracking | Custom script, 5-10 event types | Segment with tracking plan, 200+ event types |
| Analytics tool | Amplitude or Mixpanel (managed) | Custom warehouse + Mode (self-serve SQL) |
| Billing | Manual CSV upload to Stripe | Automated pipeline: events → dbt → Stripe API |
| Experimentation | Feature flags (LaunchDarkly) | Full A/B testing platform with statistical rigor |
| Team | 1 data-aware backend engineer | 4 DEs + 8 analysts + 2 analytics engineers |
| Cost | $500/month (Amplitude + Segment free tiers) | $80K/month (Snowflake + tools + headcount) |

### Lessons Learned

1. **Define your tracking plan before writing any code.** A tracking plan is a spreadsheet listing every event, its properties, and when it fires. Without it, you get inconsistent event names ("button_click" vs "buttonClick" vs "btn_clicked") and missing properties that make analysis impossible.
2. **Event data is append-only; schema changes are painful.** If you add a new property to an event, historical events do not have it. Design your event properties to be stable. Use the VARIANT/JSON column to handle evolving properties gracefully.
3. **Usage-based billing is a data engineering problem.** The billing pipeline must be as reliable as the payment processing system. Treat it with the same rigor.
4. **Self-serve analytics requires investment in data modeling.** Analysts cannot write queries against raw event data efficiently. The dbt marts layer (clean, documented, tested) is what makes self-serve possible.

---

## Case Study 4: Healthcare Data Pipeline

### When Data Quality Is Life-or-Death

Healthcare data engineering is unique because the consequences of errors are not financial or reputational -- they are clinical. A duplicate patient record can lead to a wrong medication being administered. A missing lab result can delay a diagnosis. A data quality failure in healthcare is categorically different from a data quality failure in e-commerce.

### Business Context

**Company:** Regional health system, 12 hospitals, 3M patient encounters/year, 200 clinics.

**Data team:** 10 data engineers, 6 analysts, 4 clinical informaticists (domain experts who bridge clinical and technical).

**Requirements:**
- Consolidate patient data from 15 different EHR (Electronic Health Record) systems into a single analytics platform
- Population health analytics: identify high-risk patients for preventive care programs
- Regulatory reporting: CMS quality measures, state health department reports
- Clinical research data marts for academic hospital partners
- HIPAA compliance on every single component
- Data must be accurate. Period. A wrong lab value or duplicate patient record is a patient safety issue.

### The Architecture

```
[Epic EHR]       ──┐
[Cerner EHR]     ──┤
[Lab Systems]    ──┤──→ [HL7/FHIR Interface Engine] ──→ [S3 Raw (Encrypted)]
[Radiology PACS] ──┤          (Mirth Connect)                    │
[Claims Data]    ──┤                                             ▼
[Pharmacy]       ──┘                                    [Snowflake (BAA)]
                                                              │
                                                              ▼
                                                     [dbt (Clinical Models)]
                                                              │
                                                    ┌─────────┼─────────┐
                                                    ▼         ▼         ▼
                                              [Quality    [Clinical   [Research
                                               Measures]   Analytics]  Data Marts]
                                                    │         │         │
                                                    ▼         ▼         ▼
                                              [CMS        [Tableau]  [REDCap]
                                               Reporting]             (Research)
```

### HIPAA: The Constraint That Shapes Everything

HIPAA (Health Insurance Portability and Accountability Act) is not a box-checking exercise. It fundamentally constrains your architecture:

**What HIPAA requires for data engineering:**

1. **Encryption at rest and in transit.** Every S3 bucket uses AES-256 encryption. Every database connection uses TLS. Every Snowflake connection uses encrypted channels.
2. **Access controls with audit logging.** Every query against patient data is logged with the user, timestamp, and data accessed. Role-based access control (RBAC) ensures analysts can only see data for their facility.
3. **Business Associate Agreements (BAAs).** Every vendor that touches patient data must sign a BAA. This means Snowflake (has BAA option), AWS (has BAA), dbt Cloud (has BAA). Your favorite random SaaS tool? Probably does not have a BAA. You cannot use it.
4. **Minimum necessary access.** Users should only see the patient data they need for their job function. An analyst studying diabetes outcomes should not have access to psychiatric records.
5. **De-identification for research.** Research data marts must strip or hash all 18 HIPAA identifiers (name, DOB, SSN, address, etc.).

```sql
-- De-identification view for research data marts
-- Strips all 18 HIPAA identifiers while preserving analytical value
CREATE VIEW research.encounters_deidentified AS
SELECT
    -- Replace patient_id with a one-way hash (cannot be reversed)
    SHA2(patient_id || 'research_salt_2026') AS research_patient_id,
    -- Shift dates by a random offset per patient (preserves intervals)
    encounter_date + patient_date_offset AS encounter_date_shifted,
    -- Age in years (age > 89 → '90+' per HIPAA Safe Harbor)
    CASE WHEN age > 89 THEN 90 ELSE age END AS age_category,
    -- Keep clinical data but remove identifying context
    diagnosis_code,
    procedure_code,
    lab_results,
    -- Remove: name, DOB, SSN, address, phone, email, MRN, etc.
    -- State-level geography only (ZIP codes with < 20K population → NULL)
    CASE WHEN zip_population >= 20000 THEN LEFT(zip_code, 3) ELSE NULL END AS zip_3digit
FROM clinical.encounters e
JOIN clinical.patient_date_offsets o ON e.patient_id = o.patient_id;
```

### Module-by-Module Breakdown

**Module 1 (Data Modeling):** Healthcare data modeling uses domain-specific standards. The OMOP (Observational Medical Outcomes Partnership) Common Data Model is widely adopted:

```sql
-- Simplified OMOP-inspired patient encounter model
-- The key challenge: patient matching across 15 different EHR systems
CREATE TABLE clinical.dim_patient (
    patient_key         BIGINT,
    master_patient_id   VARCHAR,  -- Enterprise Master Patient Index (EMPI)
    -- A single patient may have different IDs across systems:
    epic_mrn            VARCHAR,  -- Medical Record Number in Epic
    cerner_mrn          VARCHAR,  -- MRN in Cerner
    -- Demographics
    birth_date          DATE,
    gender              VARCHAR,
    race                VARCHAR,
    ethnicity           VARCHAR,
    -- Derived risk scores (updated daily)
    hcc_risk_score      FLOAT,    -- CMS Hierarchical Condition Category
    readmission_risk    FLOAT,    -- 30-day readmission probability
    -- SCD Type 2 for address changes (affects care coordination)
    address_line_1      VARCHAR,
    city                VARCHAR,
    state               VARCHAR,
    zip_code            VARCHAR,
    is_current          BOOLEAN,
    valid_from          DATE,
    valid_to            DATE
);
```

**The Master Patient Index (EMPI) problem:** The hardest data engineering challenge in healthcare is patient matching. Patient "John Smith, DOB 1985-03-15" in the Epic system is the same person as "Jon Smith, DOB 03/15/1985" in the Cerner system. But "John Smith, DOB 1985-03-15" in one hospital may be a completely different person than "John Smith, DOB 1985-03-15" in another hospital.

Duplicate patient records in a clinical setting can result in:
- Duplicate medication orders (overdose risk)
- Missing allergies from the other record (adverse reaction risk)
- Fragmented clinical history (misdiagnosis risk)

The EMPI uses probabilistic matching with weighted scores across name, DOB, SSN, address, and phone number. This is typically handled by dedicated EMPI software (IBM Initiate, Verato), not built from scratch.

**Module 2 (SQL):** Clinical quality measures are complex SQL queries mandated by CMS. Here is a simplified version of the diabetes HbA1c control measure:

```sql
-- CMS Quality Measure: Diabetes HbA1c Control
-- Denominator: Patients 18-75 with diabetes diagnosis
-- Numerator: Those patients with HbA1c < 8.0 in the measurement period
-- This feeds regulatory reporting submitted to CMS quarterly

WITH diabetic_patients AS (
    SELECT DISTINCT p.patient_key, p.master_patient_id
    FROM clinical.dim_patient p
    JOIN clinical.fact_diagnoses d ON p.patient_key = d.patient_key
    WHERE d.diagnosis_code LIKE 'E11%'  -- ICD-10 codes for Type 2 diabetes
        AND p.is_current = TRUE
        AND DATEDIFF('year', p.birth_date, CURRENT_DATE()) BETWEEN 18 AND 75
),
latest_hba1c AS (
    SELECT
        l.patient_key,
        l.result_value,
        l.result_date,
        ROW_NUMBER() OVER (
            PARTITION BY l.patient_key
            ORDER BY l.result_date DESC
        ) AS rn
    FROM clinical.fact_lab_results l
    WHERE l.lab_code = '4548-4'  -- LOINC code for HbA1c
        AND l.result_date >= DATEADD('year', -1, CURRENT_DATE())
)
SELECT
    COUNT(dp.patient_key) AS denominator,
    SUM(CASE WHEN h.result_value < 8.0 THEN 1 ELSE 0 END) AS numerator,
    ROUND(100.0 * SUM(CASE WHEN h.result_value < 8.0 THEN 1 ELSE 0 END)
        / COUNT(dp.patient_key), 1) AS performance_rate_pct
FROM diabetic_patients dp
LEFT JOIN latest_hba1c h ON dp.patient_key = h.patient_key AND h.rn = 1;
```

**Module 8 (Orchestration):** The orchestration is conservative by design. Healthcare pipelines favor reliability over speed:

- **No auto-retry on failure.** If a pipeline fails, it alerts and waits for human review. An auto-retry that inserts duplicate records is worse than a delayed pipeline.
- **Reconciliation at every stage.** Row counts are compared at ingestion, staging, and marts layers. Any discrepancy halts the pipeline.
- **Change data capture (CDC) from EHR systems.** EHR data changes retroactively (a doctor amends a note, a lab result is corrected). The pipeline must handle late-arriving updates, not just new inserts.

**Module 9 (Data Quality):** Data quality in healthcare is the most rigorous of any industry:

```yaml
# dbt tests for clinical data -- these are non-negotiable
models:
  - name: fact_lab_results
    tests:
      # A patient cannot have a lab result before their birth date
      - dbt_utils.expression_is_true:
          expression: "result_date >= patient_birth_date"
          name: lab_result_after_birth
      # HbA1c values outside 2-20 are likely data entry errors
      - dbt_utils.expression_is_true:
          expression: "CASE WHEN lab_code = '4548-4' THEN result_value BETWEEN 2.0 AND 20.0 ELSE TRUE END"
          name: hba1c_reasonable_range
    columns:
      - name: patient_key
        tests:
          - not_null
          - relationships:
              to: ref('dim_patient')
              field: patient_key
      - name: result_value
        tests:
          - not_null
      - name: lab_code
        tests:
          - not_null
          - accepted_values:
              values: ['4548-4', '2345-7', '718-7']  # Known LOINC codes only
```

### Startup vs. Enterprise Approach

| Aspect | Health Tech Startup | Enterprise Health System (This Case) |
|--------|-------------------|-------------------------------------|
| Data sources | 1-2 EHR integrations via FHIR API | 15 EHR systems, HL7v2 + FHIR + flat files |
| Patient matching | Simple deterministic matching | Probabilistic EMPI with manual review |
| Compliance | HIPAA basics + SOC 2 | HIPAA + HITRUST + state regulations + IRB for research |
| Quality checks | Standard dbt tests | Clinical validation rules + reconciliation + manual chart review |
| Infrastructure | All-managed (BigQuery + dbt Cloud) | Hybrid (on-prem interface engine + cloud warehouse) |
| Team | 2-3 engineers with clinical advisor | 10 DEs + 4 clinical informaticists |
| Cost | $3K-$10K/month | $200K-$500K/month |
| Time to build | 3-6 months MVP | 18-24 months for full platform |

### Lessons Learned

1. **Domain expertise is non-negotiable.** You cannot build healthcare data pipelines without clinical informaticists on the team. ICD-10 codes, LOINC codes, HL7 message parsing, clinical workflow understanding -- these require deep domain knowledge.
2. **Data quality checks must be clinically meaningful.** A test that checks "not null" is not enough. You need tests like "a patient's discharge date cannot be before their admission date" and "a HbA1c value above 20 is almost certainly a data error."
3. **Patient matching is the hardest problem.** Plan to spend 30-40% of your engineering effort on the EMPI and data reconciliation. Getting this wrong has patient safety consequences.
4. **HIPAA adds cost and complexity to everything.** Budget 20-30% more time and cost for HIPAA compliance. Every vendor evaluation, every architecture decision, every data access request goes through a compliance review.
5. **Late-arriving data is the norm, not the exception.** Clinical data gets amended, corrected, and back-dated constantly. Your pipeline must handle updates gracefully, not just inserts.

---

## Cross-Case-Study Module Map

Here is how each course module appears across all four case studies:

| Module | E-Commerce | Fraud Detection | SaaS Analytics | Healthcare |
|--------|-----------|----------------|----------------|------------|
| 1: Data Modeling | Star schema, SCD2 customers | Denormalized (real-time) + star (batch) | Event table + VARIANT/JSON | OMOP standard, EMPI |
| 2: SQL | Cohort retention, window functions | Precision/recall by threshold | Funnel analysis, activation metrics | Clinical quality measures |
| 3: Python | Custom API connectors | Feature computation service | Event processing scripts | HL7 message parsing |
| 4: Warehousing | Snowflake multi-warehouse | Snowflake for batch analytics | Snowflake with hourly refreshes | Snowflake with BAA, RBAC |
| 5: Data Lake | S3 raw layer (safety net) | S3 feature archive + audit logs | S3 raw events from Segment | S3 encrypted, lifecycle managed |
| 6: dbt | 180+ models, incremental | Batch feature recomputation | Hourly + daily models, billing | Clinical models with strict tests |
| 7: Spark | ML feature engineering | Daily batch recomputation | Heavy aggregations, backfills | Not used (volume is moderate) |
| 8: Orchestration | Airflow with SLA monitoring | Airflow for batch only; Flink is self-managed | Airflow with hourly + daily DAGs | Conservative: no auto-retry |
| 9: Data Quality | Revenue reconciliation | Latency monitoring, drift detection | Volume anomaly detection, billing reconciliation | Clinical validation, patient safety checks |
| 10: Capstone | This IS the production capstone | Extends capstone with real-time | Extends capstone with event tracking | Extends capstone with compliance |

---

## Patterns Across All Four Case Studies

**1. Every system has a "source of truth" problem.** E-commerce reconciles against Shopify. Fraud detection reconciles features between real-time and batch. SaaS analytics reconciles billing against Stripe. Healthcare reconciles patient records across 15 systems. The reconciliation pipeline is as important as the primary pipeline.

**2. Data modeling is the foundation.** In every case study, the data model was designed first and drove all downstream decisions. Changing the data model after the system is built is the most expensive refactoring you can do.

**3. Incremental processing is essential at scale.** Every case study that handles more than a few thousand rows/day uses incremental models. Full-refresh dbt models do not scale.

**4. Data quality investment scales with consequence severity.** E-commerce checks revenue accuracy. Fintech checks latency and model drift. SaaS checks billing accuracy. Healthcare checks clinical validity. The investment in quality is proportional to the cost of getting it wrong.

**5. The startup version of every system is radically simpler.** You do not need Kafka, Flink, Redis, and a 13-person team to solve these problems at startup scale. You need PostgreSQL, Python, dbt, and one capable engineer. Scale the architecture when the business demands it, not before.

> **Key Takeaway:** These case studies are not meant to intimidate. They are meant to show that the skills you are learning in Modules 0-10 are the same skills used at production scale. The difference is operational maturity, not fundamentally different technology. Build your capstone well, and you have demonstrated 80% of what these production systems require.

---

## What's Next

Appendix C (Interview Prep) shows you how to discuss these architectures in interviews. Practice describing the trade-offs, drawing the architecture diagrams from memory, and explaining why you would choose one approach over another.
