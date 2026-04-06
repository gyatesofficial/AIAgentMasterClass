# Module 1: Data Modeling Foundations

Data modeling is where data engineering begins. Before you write a single pipeline, before you spin up Airflow, before you touch Spark -- you need to understand how to structure data so that it actually serves the people who use it. This module covers the theory, patterns, and practical decisions that separate a well-designed data warehouse from a dumpster fire of duplicated, contradictory tables.

---

## 1.1 Why Data Modeling Matters

If you take one thing from this module, let it be this: **bad models produce bad data**. No amount of clever ETL, expensive tooling, or dashboard polish can fix a data model that was designed poorly from the start.

You have seen the anti-pattern even if you do not have the vocabulary for it yet. Somewhere in every poorly-governed data environment there is a table called `orders_final_FINAL_v2` sitting alongside `orders_backup_USE_THIS_ONE`. Nobody knows which is correct. Reports from marketing do not match reports from finance. Analysts spend 80% of their time wrangling data and 20% actually analyzing it. That is what happens when nobody invests in modeling.

A good data model gives you:

- **Clean, intuitive queries** -- analysts can self-serve without needing to understand 47 joins
- **A single source of truth** -- one agreed-upon definition of "revenue," "active customer," or "churn"
- **Performance** -- the data is physically organized for the questions people actually ask
- **Auditability** -- you can trace any number back to its source

### When You'll Use This at Work

Data modeling is not a one-time design exercise you do on day one and forget. You will revisit your models every time the business adds a new product line, enters a new market, acquires a company, or changes how it defines a metric. At mature companies, data modeling review is a formal process with stakeholder sign-off. At startups, it is often you and a whiteboard.

### Interview Prep

Data modeling is the single most common topic in data engineering interviews. Interviewers will hand you a business scenario and ask you to design a schema on the spot. They are testing whether you can identify the grain of a fact table, choose appropriate dimension attributes, and reason about trade-offs like normalization versus denormalization. The concepts in this module will come up in virtually every technical interview loop you encounter.

---

## 1.2 OLTP vs OLAP

Before you can model data for analytics, you need to understand the two fundamentally different worlds that data lives in.

### OLTP: Online Transaction Processing

OLTP databases are the databases behind your applications. When a customer places an order on Amazon, that order gets written to an OLTP database. When you update your profile on LinkedIn, that write hits an OLTP database.

Characteristics of OLTP systems:

- **Small, fast queries**: `SELECT * FROM orders WHERE id = 12345` -- look up one row by primary key
- **High concurrency**: thousands of users reading and writing simultaneously
- **Normalized schemas**: data is split across many tables to eliminate redundancy (3rd normal form)
- **Optimized for writes**: inserts and updates need to be fast so the application feels responsive
- **Row-oriented storage**: entire rows are stored together on disk, which is great for fetching a single complete record

Real-world examples: the PostgreSQL database behind a Rails app, the MySQL database behind a WordPress site, the DynamoDB table storing user sessions for a mobile app.

### OLAP: Online Analytical Processing

OLAP databases are where analytics happens. When a VP of Sales asks "What was our revenue by region for Q3, compared to last year?" that question gets answered by an OLAP system.

Characteristics of OLAP systems:

- **Large scan queries**: `SELECT region, SUM(revenue) FROM fact_orders WHERE year = 2025 GROUP BY region` -- aggregate millions of rows
- **Low concurrency**: maybe a few dozen analysts and dashboards, not thousands of app users
- **Denormalized schemas**: data is pre-joined and flattened so queries are simpler and faster
- **Optimized for reads**: complex aggregations need to be fast; nobody is doing single-row inserts
- **Columnar storage**: columns are stored together on disk, so scanning one column across a billion rows is extremely efficient

Real-world examples: Snowflake, BigQuery, Redshift, ClickHouse, DuckDB.

### Your Job as a Data Engineer

Here is the core loop of data engineering, distilled to one sentence: **you move data FROM OLTP systems TO OLAP systems, transforming it along the way so it is useful for analysis.**

The application team owns the OLTP database. The analytics team consumes the OLAP database. You own the space in between -- the extraction, transformation, loading, quality checks, and modeling that makes raw operational data into something an analyst can query with confidence.

```
[OLTP: App Database]  -->  [Your ETL/ELT Pipeline]  -->  [OLAP: Data Warehouse]
   (normalized)              (transform & model)           (denormalized)
   (row-oriented)                                          (columnar)
   (small fast queries)                                    (big scan queries)
```

### The Postgres Exception

Here is a practical nuance the textbooks often skip: **PostgreSQL can serve as both your OLTP and OLAP system** if you are a small-to-medium company. Postgres is remarkably versatile. If you have fewer than 50 million rows in your fact tables, a well-indexed Postgres instance with some materialized views can handle both your application workload and your analytics workload.

This is not a permanent architecture -- eventually you will outgrow it. But for a Series A startup with 10 engineers, running a separate Snowflake instance that costs $30k/month makes no sense when Postgres on a beefy RDS instance can do the job for $500/month.

At Spotify's scale (hundreds of billions of stream events), you absolutely need a dedicated OLAP system. At a 20-person startup tracking thousands of orders per day, Postgres is fine.

### Common Mistakes

- **Querying the production OLTP database directly for analytics.** This is the number one mistake junior data engineers make. Your heavy analytical queries will compete with the application's transactional queries, causing the app to slow down or time out. Always use a read replica at minimum, or better yet, extract data into a separate analytical store.
- **Over-normalizing your OLAP schema.** Normalization is great for OLTP. For OLAP, it means analysts need 12 joins to answer a simple question. Denormalize aggressively in your warehouse.

### Interview Prep

If an interviewer asks "What is the difference between OLTP and OLAP?" they are not looking for a textbook definition. They want you to demonstrate that you understand the implications for schema design, storage format, query patterns, and how data flows between the two. Mention that your job as a DE is to bridge the gap.

---

## 1.3 Dimensional Modeling

Dimensional modeling is the dominant approach for designing OLAP schemas. It was formalized by Ralph Kimball in the 1990s, and it remains the most practical and widely-used methodology in the industry. The reason it has persisted for 30 years is simple: it works.

The core idea is to separate your data into two types of tables: **facts** and **dimensions**.

### Facts: The Business Events

A fact table records something that happened. Each row represents a measurable business event at a specific grain (level of detail).

Examples of facts:
- **E-commerce**: an order line item (one product within one order)
- **Streaming**: a stream event (one user listened to one track)
- **Ad tech**: an impression (one ad was shown to one user)
- **SaaS**: a subscription event (one user started, renewed, or cancelled a plan)
- **Finance**: a transaction (one debit or credit to one account)

At Spotify, the central fact table might be `fact_streams` where each row represents one stream event: a user played a track, on a specific date, from a specific playlist, on a specific device. The grain is "one stream."

At Uber, the central fact table might be `fact_trips` where each row represents one completed trip: a rider, a driver, a pickup location, a dropoff location, a fare amount, a date.

**Facts should be lean.** A fact row contains:
1. Foreign keys pointing to dimension tables (who, what, when, where)
2. Numeric measures (how much, how many)
3. Degenerate dimensions (order ID, invoice number -- identifiers that do not warrant their own dimension table)

That is it. No descriptive text. No attributes that change. Keep fact tables skinny and long (many rows, few columns).

**Why keep facts lean?** Because fact tables are by far the largest tables in your warehouse. If your fact table has 500 million rows, every unnecessary column you add wastes storage and slows down every query that scans the table. A VARCHAR(200) product name sitting in every fact row is repeated 500 million times. That same product name stored once in a dimension table with 10,000 rows and joined at query time is negligible.

### Dimensions: The Context

A dimension table provides the descriptive context around a fact. Dimensions answer the "who, what, when, where, how" questions.

Examples of dimensions:
- **dim_customer**: name, email, city, state, segment, signup date
- **dim_product**: product name, category, subcategory, brand, price
- **dim_date**: calendar date, day of week, month, quarter, year, is_weekend, is_holiday
- **dim_store**: store name, address, region, square footage
- **dim_campaign**: campaign name, channel, start date, budget

Dimensions are typically wide (many columns) and short (relatively few rows compared to facts). A retailer might have 50,000 products but 500 million order line items.

### Star Schema

When you put facts and dimensions together, you get a **star schema** -- so named because the diagram looks like a star with the fact table at the center and dimension tables radiating outward.

```
                    dim_customer
                         |
                         |
    dim_product --- fact_orders --- dim_date
                         |
                         |
                    dim_promotion
```

The star schema is the default starting point for virtually every analytical data model. It is intuitive for analysts (they understand "orders" joined with "customers" and "products"), it performs well (dimension lookups via foreign keys are fast), and it is easy to extend (adding a new dimension just means adding a new foreign key to the fact table).

### Surrogate Keys vs Natural Keys

This is a decision you will make for every dimension table, and getting it wrong causes real pain downstream.

A **natural key** is the identifier from the source system: `customer_id = 12345` from your application database. A **surrogate key** is a synthetic key you generate in your warehouse: `customer_key = 1` (typically a serial/auto-increment integer).

**Why use surrogate keys?**

1. **Source systems change.** If Marketing migrates from Salesforce to HubSpot, the customer IDs change. If your fact table uses the natural key, you have to update millions of rows. If it uses a surrogate key, you update one row in the dimension table.

2. **SCD Type 2 requires them.** When a customer moves from New York to San Francisco, you create a new dimension row for the same customer (more on this in section 1.4). That new row needs its own unique key. The natural key (`customer_id = 12345`) now appears in two rows -- so it cannot be the primary key.

3. **Cross-system integration.** When you combine customers from two different source systems, natural keys collide. Customer 12345 in the billing system is not the same as customer 12345 in the CRM. Surrogate keys eliminate this problem.

4. **Performance.** Integer surrogate keys are smaller and faster to join on than VARCHAR natural keys or composite keys.

**The rule:** dimension tables have a surrogate key as their primary key and also store the natural key for traceability. Fact tables reference dimensions via surrogate keys.

### Pre-Calculated Measures

One of the most practical decisions in dimensional modeling is what to pre-calculate in the fact table. Consider an order line item:

```
quantity = 3, unit_price = 29.99, discount = 5.00
```

You could store just these raw values and calculate revenue at query time: `quantity * unit_price - discount`. But if every single dashboard query needs to do this multiplication across 500 million rows, you are wasting compute on every query.

Instead, pre-calculate at load time:

```sql
revenue = quantity * unit_price - discount  -- 84.97
cost = quantity * unit_cost                 -- 45.00
profit = revenue - cost                     -- 39.97
```

Now every query that needs revenue just does `SUM(revenue)` instead of `SUM(quantity * unit_price - discount)`. This is faster, simpler, and -- critically -- it ensures every report calculates revenue the same way. No more arguments about whether the discount should be subtracted before or after tax.

**Pre-calculate measures that have an agreed-upon business definition.** Revenue, cost, profit, margin -- these should be computed once, correctly, at load time. Do not make every analyst re-derive them.

### The Date Dimension

Every dimensional model has a date dimension. It deserves special attention because dates are used in virtually every analytical query and because the date dimension has unique properties.

Unlike other dimensions, the date dimension is **fully pre-populated**. You generate all rows upfront (typically 10-20 years of dates) before any facts are loaded. Every calendar date gets a row, whether or not any business events occurred on that date.

The date key is typically an integer in `YYYYMMDD` format (e.g., `20250315` for March 15, 2025). This is both human-readable and efficient for range queries.

```sql
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,          -- YYYYMMDD format
    calendar_date   DATE NOT NULL UNIQUE,
    day_of_week     VARCHAR(10) NOT NULL,
    day_of_month    INT NOT NULL,
    month           INT NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    quarter         INT NOT NULL,
    year            INT NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE
);
```

Why not just use a DATE column in the fact table? Because the date dimension gives you pre-built attributes for grouping and filtering. `WHERE is_weekend = TRUE` is cleaner than `WHERE EXTRACT(ISODOW FROM order_date) IN (6, 7)`. `GROUP BY quarter` is cleaner than `GROUP BY EXTRACT(QUARTER FROM order_date)`. And you can add business-specific attributes like fiscal quarter, holiday flags, or promotion periods that do not exist in a raw DATE type.

Here is how to populate a date dimension in PostgreSQL:

```sql
INSERT INTO dim_date (date_key, calendar_date, day_of_week, day_of_month,
                      month, month_name, quarter, year, is_weekend, is_holiday)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_key,
    d AS calendar_date,
    TO_CHAR(d, 'Day') AS day_of_week,
    EXTRACT(DAY FROM d) AS day_of_month,
    EXTRACT(MONTH FROM d) AS month,
    TO_CHAR(d, 'Month') AS month_name,
    EXTRACT(QUARTER FROM d) AS quarter,
    EXTRACT(YEAR FROM d) AS year,
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend,
    FALSE AS is_holiday
FROM generate_series('2024-01-01'::date, '2026-12-31'::date, '1 day') AS d;
```

### When You'll Use This at Work

Dimensional modeling is the bread and butter of data warehouse design. Every time you build a new analytical dataset -- whether in Snowflake, BigQuery, Redshift, or plain Postgres -- you will be thinking in terms of facts and dimensions. Even if your team uses dbt models that produce flat tables, the mental framework of "what is the grain, what are the measures, what are the dimensions" guides every design decision.

### Common Mistakes

- **Making the grain too coarse.** If your grain is "one row per order" but an order can have multiple products, you lose the ability to analyze at the product level. Always define the finest useful grain and aggregate upward.
- **Putting descriptive attributes in the fact table.** Product name, customer name, category -- these belong in dimensions. The fact table should only have keys and measures.
- **Forgetting to index dimension foreign keys in the fact table.** Without indexes on `customer_key`, `product_key`, and `date_key`, your star schema joins will be full table scans.
- **Not pre-populating the date dimension.** If you generate date rows on the fly as facts arrive, you will have gaps for dates with no events, which breaks time-series reporting.

---

## 1.4 Slowly Changing Dimensions (SCDs)

Here is the problem: dimensions change. A customer moves from New York to San Francisco. A product gets reclassified from "Electronics" to "Smart Home." A salesperson transfers to a different region.

When that change happens, what do you do with the historical data? If Customer 12345 placed an order when they lived in New York and now they live in San Francisco, which city should show up in a report analyzing orders by customer location?

The answer depends on your business requirements, and Slowly Changing Dimension (SCD) types give you a vocabulary for the options.

### SCD Type 1: Overwrite

The simplest approach: just overwrite the old value with the new one. The customer moved to San Francisco? Update the row:

```
Before: customer_id=12345, name="Alice", city="New York"
After:  customer_id=12345, name="Alice", city="San Francisco"
```

**Pros:** Simple. No complexity. Dimension table stays small.

**Cons:** You lose history. Every historical order for this customer now shows "San Francisco" even if they were in New York when they placed it. If the VP of Sales asks "What was our NYC revenue last year?" the numbers are wrong because Alice's old NYC orders now count toward San Francisco.

**When to use Type 1:** For attributes where history does not matter. A customer's email address, a product's internal SKU code, a typo correction. If nobody will ever ask "what was the old value?" then Type 1 is fine.

### SCD Type 2: Add a New Row

The industry standard for important attributes. When a value changes, you do NOT update the existing row. Instead, you expire the old row and insert a new one:

```
customer_key=1001, customer_id=12345, name="Alice", city="New York",
    effective_date='2023-01-15', expiry_date='2025-03-01', is_current=FALSE

customer_key=1002, customer_id=12345, name="Alice", city="San Francisco",
    effective_date='2025-03-01', expiry_date='9999-12-31', is_current=TRUE
```

Now the same natural key (`customer_id = 12345`) has two rows in the dimension table, each with its own surrogate key. Orders placed before March 2025 reference `customer_key = 1001` (New York). Orders placed after reference `customer_key = 1002` (San Francisco). Historical queries are accurate.

This is why surrogate keys exist. The natural key is no longer unique in the dimension table, so you need a separate primary key.

**The `9999-12-31` convention:** The current row always has an expiry date of `9999-12-31` (a far-future sentinel value). This makes range queries simple: `WHERE '2025-06-15' BETWEEN effective_date AND expiry_date` works for both current and historical rows.

**Pros:** Full history preserved. Historical reports remain accurate. This is the gold standard.

**Cons:** Dimension tables grow over time (one new row per change per entity). Queries for "current" data need a `WHERE is_current = TRUE` filter.

**When to use Type 2:** For any attribute where historical accuracy matters. Customer location (for geographic analysis), product category (for category-level reporting), product price (for margin calculations), customer segment (for cohort analysis).

**Type 2 is the default.** If you are not sure which type to use, use Type 2. It is better to preserve history you do not need than to lose history you do need. You cannot go back in time and recreate overwritten data.

### SCD Type 3: Add a Column

Instead of adding rows, add columns for the old and new values:

```
customer_id=12345, name="Alice", current_city="San Francisco", previous_city="New York"
```

**Pros:** Simple to query both current and previous values. No row explosion.

**Cons:** Only tracks one level of history (current vs previous, not the full history). What happens when the customer moves a third time? You lose the original value.

**When to use Type 3:** Rarely. It is useful when you specifically need to compare "before and after" for a known change event (like a company reorganization that reassigns all accounts to new regions). In practice, Type 3 is uncommon.

### The Real-World Approach: Mix and Match

In practice, you do not pick one SCD type for an entire dimension table. You pick a type per attribute:

- **Customer dimension:**
  - `city`, `state`, `segment` --> Type 2 (historical accuracy matters for geographic and cohort analysis)
  - `email` --> Type 1 (nobody analyzes by historical email addresses)
  - `name` --> Type 1 (name corrections are not analytically relevant)

- **Product dimension:**
  - `category`, `subcategory` --> Type 2 (category-level reporting needs historical accuracy)
  - `unit_price`, `unit_cost` --> Type 2 (margin calculations need the price at time of sale)
  - `product_name` --> Type 1 (name tweaks are cosmetic)

Here is a complete SCD Type 2 dimension table definition:

```sql
CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,       -- surrogate key
    customer_id     INT NOT NULL,             -- natural key
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    city            VARCHAR(100),
    state           VARCHAR(50),
    country         VARCHAR(50) DEFAULT 'US',
    segment         VARCHAR(50),
    created_date    DATE,
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_dim_customer_natural ON dim_customer(customer_id, is_current);
```

And the matching product dimension:

```sql
CREATE TABLE dim_product (
    product_key     SERIAL PRIMARY KEY,
    product_id      INT NOT NULL,
    product_name    VARCHAR(300) NOT NULL,
    category        VARCHAR(100),
    subcategory     VARCHAR(100),
    brand           VARCHAR(100),
    unit_cost       NUMERIC(10,2),
    unit_price      NUMERIC(10,2),
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_dim_product_natural ON dim_product(product_id, is_current);
```

### When You'll Use This at Work

Every warehouse you touch will have SCD decisions baked into it. When a stakeholder says "our geographic revenue numbers shifted overnight and nobody changed the reports," the first thing you check is whether a dimension attribute was overwritten (Type 1) when it should have been versioned (Type 2). Getting SCD right is the difference between a trustworthy warehouse and one that produces mysterious data drift.

### Interview Prep

Interviewers love SCD questions. The standard question is: "A customer changes their address. How do you handle this in your data warehouse?" The strong answer walks through all three types, explains the trade-offs, and states that Type 2 is the default for analytically important attributes. Bonus points if you mention the `effective_date` / `expiry_date` / `is_current` pattern and explain why surrogate keys are necessary for Type 2.

### Common Mistakes

- **Using Type 1 for everything because it is simpler.** You will not realize the damage until a stakeholder asks a historical question and the numbers are wrong. By then, the history is gone.
- **Forgetting the `is_current` flag.** Without it, every query that wants "current customer data" needs a `WHERE expiry_date = '9999-12-31'` filter, which is error-prone and non-obvious to analysts.
- **Not indexing the natural key + `is_current` combo.** The most common lookup pattern is "give me the current row for customer_id = 12345." Without an index, this scans the entire dimension table.

---

## 1.5 Modern Approaches

The Kimball dimensional model has been the standard for decades, and it still works well. But modern columnar warehouses (Snowflake, BigQuery, Redshift, Databricks) have changed some of the performance assumptions that drove traditional star schema design. Two modern patterns are worth knowing.

### One Big Table (OBT)

The One Big Table approach says: skip the star schema entirely. Pre-join all your dimensions into a single wide, denormalized table.

Instead of `fact_orders` joining to `dim_customer`, `dim_product`, and `dim_date`, you create a single table called `orders_wide` that has every column from every dimension baked in:

```
order_id | customer_name | customer_city | customer_segment | product_name | category | brand | order_date | day_of_week | quantity | revenue | profit
```

**Why this works in modern warehouses:**

- **Columnar storage makes wide tables cheap.** If your query only needs `customer_city` and `revenue`, the engine only reads those two columns from disk, even if the table has 200 columns. The other 198 columns cost nothing.
- **No joins means simpler queries and faster execution.** `SELECT city, SUM(revenue) FROM orders_wide GROUP BY city` is faster than joining three tables.
- **Compression.** Columnar warehouses compress repeated values extremely efficiently. The string "Electronics" repeated 50 million times in a category column compresses down to almost nothing.

**When OBT makes sense:**

- Your fact table has fewer than ~100 million rows (beyond that, the duplication of dimension data can become meaningful even with compression)
- You are using a columnar warehouse (Snowflake, BigQuery, Redshift)
- Your analysts are writing SQL directly and prefer simple queries
- You do not need SCD Type 2 history (OBT is awkward with versioned dimensions)

**When OBT does not make sense:**

- You need historical dimension tracking (SCD Type 2)
- You have very large fact tables (billions of rows) where dimension data duplication adds up
- Multiple fact tables share the same dimensions (you would duplicate dimension data across every OBT)

### Wide Event Tables with JSONB

Another modern pattern: store events as wide rows with a JSONB (or VARIANT in Snowflake, or STRUCT in BigQuery) column for flexible attributes.

```sql
CREATE TABLE events (
    event_id     UUID PRIMARY KEY,
    event_type   VARCHAR(50),
    event_time   TIMESTAMP,
    user_id      INT,
    properties   JSONB        -- flexible key-value pairs
);
```

This is common for product analytics (tracking user clicks, page views, feature usage) where the set of attributes varies by event type. A "page_view" event has a URL; a "purchase" event has an amount; a "signup" event has a referral source. JSONB lets you store all of these in the same table without needing 300 nullable columns.

Modern warehouses handle semi-structured data well. In BigQuery, you can query into STRUCT fields. In Snowflake, you can query into VARIANT columns. The performance penalty compared to native columns is small and shrinking.

### The Practical Approach: Use Both

At most companies, the answer is not "star schema OR OBT OR event tables." It is all of them, layered:

1. **Raw layer**: event tables and source system replicas (messy, complete, append-only)
2. **Modeled layer**: star schema with proper dimensions and facts (the "single source of truth")
3. **Mart layer**: OBT-style wide tables pre-joined for specific teams or dashboards

This layered approach (often called "medallion architecture" -- bronze/silver/gold) gives you the best of all worlds. The star schema preserves history and enforces consistency. The OBT marts give analysts the simplicity they want.

### When You'll Use This at Work

If you join a modern data team using dbt, you will almost certainly see this layered pattern. Your staging models clean the raw data, your intermediate models implement dimensional modeling, and your mart models denormalize into wide tables for specific use cases. Understanding when to use each pattern -- and why -- is what makes you effective.

---

## 1.6 Data Vault Basics

Data Vault is an enterprise data modeling methodology designed for large organizations with complex, evolving source systems. You do not need to master Data Vault for most jobs, but you need to know it exists and understand the core concepts -- because it comes up in interviews and you may encounter it at large enterprises.

### The Core Components

**Hubs** store the unique business keys for a business concept. A `hub_customer` table might have just `customer_id` and a hash key and a load timestamp. That is it -- no descriptive attributes.

**Links** store the relationships between hubs. An `link_order_customer` table connects orders to customers. Links are where many-to-many relationships live.

**Satellites** store the descriptive attributes and their change history. A `sat_customer_details` table has name, email, city, segment -- with effective dates for tracking changes.

### Why Data Vault Exists

Data Vault solves a specific problem: **what happens when your source systems are messy, constantly changing, and you need to integrate data from dozens of them?** The hub/link/satellite separation means you can load data from any source system without redesigning your model. New sources just add new satellites.

It is also fully auditable and supports parallel loading (hubs, links, and satellites can be loaded independently).

### Why You Probably Won't Use It

Data Vault is complex. The number of tables explodes (a simple star schema with 4 tables becomes 10+ tables in Data Vault). Queries require many joins. It makes sense for Fortune 500 companies with 50 source systems and dedicated data architecture teams. It does not make sense for a 5-person data team at a startup.

### Interview Prep

If an interviewer asks about Data Vault, they are testing whether you know the landscape of modeling methodologies beyond Kimball. A strong answer is: "Data Vault uses hubs for business keys, links for relationships, and satellites for descriptive attributes with history tracking. It is designed for enterprise environments with many heterogeneous source systems. I would use it when I need to integrate many sources at scale, but for most analytical use cases I would start with dimensional modeling because it is simpler and more accessible for analysts."

---

## 1.7 Hands-On: Design a Schema for ShopFast E-Commerce

Now we put it all together. ShopFast is a mid-size e-commerce company with approximately 50,000 customers, 10,000 products in 20 categories, and 1,000,000 orders over the past 2 years.

### The Business Questions

The analytics team needs to answer:

1. **Revenue by category and month** -- Which product categories are growing? Which are declining?
2. **Customer lifetime value** -- Who are our best customers? What segments spend the most?
3. **Product performance** -- Which products have the highest margins? Which are being returned most?
4. **Geographic trends** -- Which cities and states generate the most revenue?

### Step 1: Identify the Grain

The grain is the most fundamental decision. Ask: "What does one row in my fact table represent?"

For ShopFast, the grain is **one row per order line item** -- one product within one order. Not one row per order (too coarse -- you lose product-level detail). Not one row per shipment or per payment (those could be separate fact tables if needed).

Why this grain? Because every business question above can be answered at the line item level and aggregated upward. Revenue by category requires knowing which products were in each order. Customer lifetime value requires summing line-item revenue per customer. Product margins require knowing cost and revenue per product per order.

### Step 2: Identify the Dimensions

Look at the business questions and ask "by what?" and "for which?"

- Revenue **by category** and **by month** --> `dim_product` (has category), `dim_date` (has month)
- Customer lifetime value **by customer** and **by segment** --> `dim_customer` (has segment)
- Product performance **by product** --> `dim_product`
- Geographic trends **by city/state** --> `dim_customer` (has city, state)

Three dimensions: `dim_date`, `dim_customer`, `dim_product`.

### Step 3: Identify the Measures

What numeric values do we need to aggregate?

- `quantity` -- how many units
- `unit_price` -- the price charged (at time of sale)
- `discount_amount` -- any discount applied
- `revenue` -- pre-calculated: `quantity * unit_price - discount_amount`
- `cost` -- pre-calculated: `quantity * unit_cost` (unit_cost comes from dim_product)
- `profit` -- pre-calculated: `revenue - cost`

### Step 4: SCD Decisions

What changes over time and does historical accuracy matter?

- **Customer city/state** --> SCD Type 2. Geographic analysis needs to reflect where the customer was when they ordered, not where they are now.
- **Customer segment** --> SCD Type 2. Cohort analysis (comparing enterprise vs SMB revenue) needs historical accuracy.
- **Customer email/name** --> SCD Type 1. Not analytically relevant.
- **Product category/subcategory** --> SCD Type 2. Category-level reporting needs historical accuracy.
- **Product price** --> SCD Type 2. Margin calculations need the price at time of sale.
- **Product name** --> SCD Type 1. Name changes are cosmetic.

### The Complete Solution

Here is the full dimensional model. This is what you would implement in a real warehouse:

```sql
-- =============================================
-- DIMENSION: Date
-- =============================================
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,          -- YYYYMMDD format
    calendar_date   DATE NOT NULL UNIQUE,
    day_of_week     VARCHAR(10) NOT NULL,
    day_of_month    INT NOT NULL,
    month           INT NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    quarter         INT NOT NULL,
    year            INT NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE
);

-- Populate date dimension (2024-01-01 through 2026-12-31)
INSERT INTO dim_date (date_key, calendar_date, day_of_week, day_of_month,
                      month, month_name, quarter, year, is_weekend, is_holiday)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_key,
    d AS calendar_date,
    TO_CHAR(d, 'Day') AS day_of_week,
    EXTRACT(DAY FROM d) AS day_of_month,
    EXTRACT(MONTH FROM d) AS month,
    TO_CHAR(d, 'Month') AS month_name,
    EXTRACT(QUARTER FROM d) AS quarter,
    EXTRACT(YEAR FROM d) AS year,
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend,
    FALSE AS is_holiday
FROM generate_series('2024-01-01'::date, '2026-12-31'::date, '1 day') AS d;

-- =============================================
-- DIMENSION: Customer (SCD Type 2)
-- =============================================
CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,       -- surrogate key
    customer_id     INT NOT NULL,             -- natural key from source
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    city            VARCHAR(100),
    state           VARCHAR(50),
    country         VARCHAR(50) DEFAULT 'US',
    segment         VARCHAR(50),
    created_date    DATE,
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_dim_customer_natural ON dim_customer(customer_id, is_current);

-- =============================================
-- DIMENSION: Product (SCD Type 2)
-- =============================================
CREATE TABLE dim_product (
    product_key     SERIAL PRIMARY KEY,
    product_id      INT NOT NULL,
    product_name    VARCHAR(300) NOT NULL,
    category        VARCHAR(100),
    subcategory     VARCHAR(100),
    brand           VARCHAR(100),
    unit_cost       NUMERIC(10,2),
    unit_price      NUMERIC(10,2),
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_dim_product_natural ON dim_product(product_id, is_current);

-- =============================================
-- FACT: Orders (grain = one row per order line item)
-- =============================================
CREATE TABLE fact_orders (
    order_key       SERIAL PRIMARY KEY,
    order_id        INT NOT NULL,             -- degenerate dimension
    customer_key    INT NOT NULL REFERENCES dim_customer(customer_key),
    product_key     INT NOT NULL REFERENCES dim_product(product_key),
    date_key        INT NOT NULL REFERENCES dim_date(date_key),
    quantity        INT NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) DEFAULT 0,
    revenue         NUMERIC(12,2) NOT NULL,   -- pre-calculated
    cost            NUMERIC(12,2),            -- pre-calculated
    profit          NUMERIC(12,2),            -- pre-calculated
    order_status    VARCHAR(20)
);

CREATE INDEX idx_fact_orders_date ON fact_orders(date_key);
CREATE INDEX idx_fact_orders_customer ON fact_orders(customer_key);
CREATE INDEX idx_fact_orders_product ON fact_orders(product_key);
```

### Loading the Model from Source Data

The source system has a typical OLTP schema: `src_customers`, `src_products`, `src_orders`, and `src_order_items`. Here is how you load the dimensional model from these sources:

```sql
-- Load dim_customer (initial load -- all customers are "current")
INSERT INTO dim_customer (customer_id, name, email, city, state, country,
                          segment, created_date, effective_date)
SELECT id, name, email, city, state, country, segment,
       created_at::date, created_at::date
FROM src_customers;

-- Load dim_product (initial load)
INSERT INTO dim_product (product_id, product_name, category, subcategory,
                         brand, unit_cost, unit_price, effective_date)
SELECT id, product_name, category, subcategory, brand,
       unit_cost, unit_price, created_at::date
FROM src_products;

-- Load fact_orders (join source tables and pre-calculate measures)
INSERT INTO fact_orders (order_id, customer_key, product_key, date_key,
                         quantity, unit_price, discount_amount,
                         revenue, cost, profit, order_status)
SELECT
    o.id,
    dc.customer_key,
    dp.product_key,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    (oi.quantity * oi.unit_price - oi.discount),           -- revenue
    (oi.quantity * dp.unit_cost),                           -- cost
    (oi.quantity * oi.unit_price - oi.discount) - (oi.quantity * dp.unit_cost),  -- profit
    o.status
FROM src_orders o
JOIN src_order_items oi ON o.id = oi.order_id
JOIN dim_customer dc ON o.customer_id = dc.customer_id AND dc.is_current = TRUE
JOIN dim_product dp ON oi.product_id = dp.product_id AND dp.is_current = TRUE;
```

Notice what happens in the fact load:

1. We join `src_orders` to `src_order_items` to get the line-item grain
2. We look up the surrogate keys from `dim_customer` and `dim_product` (joining on the natural key with `is_current = TRUE` for the initial load)
3. We convert the order date to the `YYYYMMDD` integer format to match `dim_date`
4. We pre-calculate `revenue`, `cost`, and `profit` at load time

### Querying the Star Schema

With the model in place, the business questions become straightforward SQL:

**Revenue by category and month:**

```sql
SELECT
    dp.category,
    dd.year,
    dd.month,
    dd.month_name,
    SUM(fo.revenue) AS total_revenue,
    COUNT(DISTINCT fo.order_id) AS num_orders
FROM fact_orders fo
JOIN dim_product dp ON fo.product_key = dp.product_key
JOIN dim_date dd ON fo.date_key = dd.date_key
GROUP BY dp.category, dd.year, dd.month, dd.month_name
ORDER BY dd.year, dd.month, dp.category;
```

**Top customers by lifetime value:**

```sql
SELECT
    dc.customer_id,
    dc.name,
    dc.segment,
    SUM(fo.revenue) AS lifetime_revenue,
    SUM(fo.profit) AS lifetime_profit,
    COUNT(DISTINCT fo.order_id) AS num_orders
FROM fact_orders fo
JOIN dim_customer dc ON fo.customer_key = dc.customer_key
GROUP BY dc.customer_id, dc.name, dc.segment
ORDER BY lifetime_revenue DESC
LIMIT 20;
```

**Geographic revenue trends:**

```sql
SELECT
    dc.state,
    dc.city,
    dd.quarter,
    dd.year,
    SUM(fo.revenue) AS total_revenue,
    SUM(fo.profit) AS total_profit
FROM fact_orders fo
JOIN dim_customer dc ON fo.customer_key = dc.customer_key
JOIN dim_date dd ON fo.date_key = dd.date_key
GROUP BY dc.state, dc.city, dd.quarter, dd.year
ORDER BY total_revenue DESC;
```

These queries are clean, readable, and performant. An analyst who has never seen this schema before can understand what each query does. That is the power of dimensional modeling.

---

## Module 1 Project

Build the complete ShopFast dimensional model from scratch.

**Starter files:**
- `modules/module-1/starter/requirements.md` -- the full business requirements
- `modules/module-1/starter/source_data.sql` -- OLTP source tables with seed data (100 customers, 50 products, 200 orders, 500 order line items)
- `modules/module-1/starter/template_ddl.sql` -- skeleton DDL with hints for each table

**Your deliverables:**
1. Complete the DDL in `template_ddl.sql` with all column definitions, data types, and constraints
2. Add appropriate indexes for common query patterns
3. Write the INSERT statements to load data from source tables into your dimensional model
4. Write at least two analytical queries that answer the business questions from the requirements

**What "good" looks like:**
- Every dimension has a surrogate key and a natural key
- SCD Type 2 metadata (`effective_date`, `expiry_date`, `is_current`) on customer and product dimensions
- Fact table has pre-calculated `revenue`, `cost`, and `profit`
- Grain is clearly one row per order line item
- Indexes on all foreign keys in the fact table
- The date dimension is fully populated for the relevant date range

**Solution:** `modules/module-1/solution/dimensional_model.sql`

---

## What's Next

With a solid understanding of data modeling -- facts, dimensions, star schemas, SCDs, and modern alternatives -- you have the foundation for everything that follows. In Module 2, we will tackle the tools and infrastructure that move data from source systems into these models: ingestion pipelines, orchestration, and the mechanics of ETL and ELT.
