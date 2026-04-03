# Module 2: Data Modeling & Schema Design

## Why Data Modeling Matters

Bad data models are the number one cause of system redesigns. Not server outages, not scaling problems, not technology choices — *how you structure your data* determines whether a system is a joy to work with or a nightmare that gets slower and more confusing with every new feature.

Think of data modeling like designing the floor plan of a building. Get it right, and every room connects logically — people flow naturally from the lobby to the elevator to their office. Get it wrong, and you end up with hallways that dead-end, bathrooms accessible only through the kitchen, and a conference room that requires walking through someone's office. You *can* work in that building, but everything takes longer and feels wrong.

The good news: there isn't one "right" data model for all situations. Different parts of the same system might use different modeling approaches. The key is matching the model to the access patterns — how will the data actually be read and written?

> **Key Takeaway:** Before choosing any technology or writing any SQL, understand your access patterns. Are reads or writes more frequent? Do you need complex joins or simple lookups? Is the data naturally tabular, hierarchical, or graph-structured? The answers to these questions determine your model.

---

## Relational Modeling Fundamentals

Relational databases have dominated data storage for 40+ years because the relational model is remarkably versatile. Let's build up the core concepts using a concrete example: an e-commerce order system.

### Tables, Rows, and Relationships

A relational database organizes data into **tables** (relations). Each table has a fixed set of **columns** (attributes) and contains **rows** (tuples). A **primary key** uniquely identifies each row. A **foreign key** references a row in another table, creating a relationship.

### Normalization: Eliminating Redundancy

**Normalization** is the process of organizing data to reduce redundancy and prevent update anomalies. There are several "normal forms," but in practice, you mostly care about the first three.

**First Normal Form (1NF)**: Every column holds a single, atomic value. No arrays, no comma-separated lists, no nested structures.

Here's a table that violates 1NF — the `phone_numbers` column holds multiple values:

```sql
-- BAD: Violates 1NF — multi-valued column
CREATE TABLE customers_bad (
    customer_id   SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    phone_numbers TEXT  -- Stores "555-0100, 555-0101"
);
```

The fix is to move phone numbers to their own table, with one row per phone number:

```sql
-- GOOD: 1NF — each value gets its own row
CREATE TABLE customers (
    customer_id  SERIAL PRIMARY KEY,
    name         TEXT NOT NULL
);

CREATE TABLE customer_phones (
    phone_id     SERIAL PRIMARY KEY,
    customer_id  INTEGER REFERENCES customers(customer_id),
    phone_number TEXT NOT NULL,
    phone_type   TEXT DEFAULT 'mobile'  -- mobile, home, work
);
```

**Second Normal Form (2NF)**: Every non-key column depends on the *entire* primary key, not just part of it. This only matters for tables with composite primary keys.

**Third Normal Form (3NF)**: Every non-key column depends *directly* on the primary key, not on another non-key column. For example, if your `orders` table has both `customer_id` and `customer_name`, the name depends on the customer, not the order. It should live only in the `customers` table.

Here's a properly normalized e-commerce schema. Notice how each piece of information lives in exactly one place:

```sql
-- Customers: one row per customer
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Products: one row per product
CREATE TABLE products (
    product_id    SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    price         DECIMAL(10,2) NOT NULL,
    description   TEXT
);

-- Orders: one row per order (header information)
CREATE TABLE orders (
    order_id      SERIAL PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    order_date    TIMESTAMP DEFAULT NOW(),
    status        TEXT DEFAULT 'pending',
    shipping_addr TEXT NOT NULL
);

-- Order items: one row per product per order (the line items)
CREATE TABLE order_items (
    item_id       SERIAL PRIMARY KEY,
    order_id      INTEGER REFERENCES orders(order_id),
    product_id    INTEGER REFERENCES products(product_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    DECIMAL(10,2) NOT NULL  -- Price at time of purchase
);
```

Notice that `unit_price` is stored in `order_items` even though `products` has a `price` column. This is intentional — the product price might change, but the price a customer paid should never change. This is called "snapshotting" and it's a common pattern.

### When to Denormalize

Normalization optimizes for *write correctness* — no data is duplicated, so updates happen in one place. But it can hurt *read performance* because answering questions requires joining multiple tables.

Consider this query: "Show me all orders with customer names and product names." In our normalized schema, that's a four-table join:

```sql
SELECT c.name AS customer_name,
       o.order_id,
       o.order_date,
       p.name AS product_name,
       oi.quantity,
       oi.unit_price
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.order_date > CURRENT_DATE - INTERVAL '30 days';
```

At small scale, this is fine. At millions of orders, these joins become expensive. **Denormalization** trades storage space and write complexity for read performance by duplicating data:

```sql
-- Denormalized order view — all info in one table
CREATE TABLE order_details_flat (
    order_id       INTEGER,
    order_date     TIMESTAMP,
    customer_id    INTEGER,
    customer_name  TEXT,       -- Duplicated from customers
    customer_email TEXT,       -- Duplicated from customers
    product_id     INTEGER,
    product_name   TEXT,       -- Duplicated from products
    category       TEXT,       -- Duplicated from products
    quantity       INTEGER,
    unit_price     DECIMAL(10,2),
    line_total     DECIMAL(10,2)  -- Pre-computed
);
```

Now the same query is a simple scan of one table — no joins needed. The trade-off: if a customer changes their name, you need to update every row where they appear. In an analytics context where you're reading historical data, this is usually acceptable.

> **Key Takeaway:** Normalize your operational/transactional data (OLTP) for correctness. Denormalize your analytical data (OLAP) for read performance. Most systems need both — a normalized source of truth and denormalized views for queries.

---

## Dimensional Modeling: Star and Snowflake Schemas

When your data is primarily used for analytics — dashboards, reports, ad-hoc queries — **dimensional modeling** provides a structure optimized for those patterns.

### Fact Tables and Dimension Tables

A **fact table** records business events (measurements). Each row is something that happened: an order was placed, a page was viewed, a payment was processed. Fact tables are tall (many rows) and narrow-ish (mostly foreign keys and numeric measures).

A **dimension table** provides context for facts. Each row describes a business entity: a customer, a product, a date, a location. Dimension tables are short (fewer rows) and wide (many descriptive columns).

### Star Schema

In a star schema, the fact table sits in the center, connected to dimension tables radiating outward like points of a star. There's exactly one join between the fact table and any dimension.

Here's a star schema for retail analytics:

```sql
-- Fact table: one row per order line item
CREATE TABLE fact_sales (
    sale_id        SERIAL PRIMARY KEY,
    date_key       INTEGER REFERENCES dim_date(date_key),
    customer_key   INTEGER REFERENCES dim_customer(customer_key),
    product_key    INTEGER REFERENCES dim_product(product_key),
    store_key      INTEGER REFERENCES dim_store(store_key),
    -- Measures (the numbers you aggregate)
    quantity       INTEGER,
    unit_price     DECIMAL(10,2),
    total_amount   DECIMAL(10,2),
    discount       DECIMAL(10,2),
    profit         DECIMAL(10,2)
);

-- Date dimension: one row per day, pre-populated
CREATE TABLE dim_date (
    date_key         INTEGER PRIMARY KEY,   -- e.g., 20260401
    full_date        DATE,
    day_of_week      TEXT,      -- Monday, Tuesday, ...
    month_name       TEXT,
    quarter          INTEGER,
    year             INTEGER,
    is_weekend       BOOLEAN,
    is_holiday       BOOLEAN,
    fiscal_quarter   INTEGER,
    fiscal_year      INTEGER
);

-- Customer dimension
CREATE TABLE dim_customer (
    customer_key   INTEGER PRIMARY KEY,
    customer_id    INTEGER,    -- Business key (from source system)
    name           TEXT,
    email          TEXT,
    segment        TEXT,       -- VIP, Regular, New
    city           TEXT,
    state          TEXT,
    country        TEXT,
    -- SCD Type 2 fields (explained below)
    effective_date DATE,
    expiry_date    DATE,
    is_current     BOOLEAN
);

-- Product dimension
CREATE TABLE dim_product (
    product_key    INTEGER PRIMARY KEY,
    product_id     INTEGER,
    name           TEXT,
    category       TEXT,
    subcategory    TEXT,
    brand          TEXT,
    supplier       TEXT
);
```

Now analytical queries become simple and fast:

```sql
-- Monthly revenue by product category — no complex joins needed
SELECT d.year,
       d.month_name,
       p.category,
       SUM(f.total_amount) AS revenue,
       SUM(f.profit) AS profit,
       COUNT(*) AS transactions
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY d.year, d.month_name, p.category
ORDER BY d.year, d.month_name;
```

### Slowly Changing Dimensions (SCD)

What happens when dimension data changes? A customer moves to a new city. A product gets recategorized. There are three standard approaches:

**Type 1 — Overwrite**: Just update the row. Simple but you lose history. "What city was this customer in when they made that purchase?" becomes unanswerable.

**Type 2 — Add a New Row**: Create a new row with the updated values and an `effective_date`. Mark the old row as expired. The `is_current` flag tells you which row is active. You keep full history, but the dimension table grows and queries need to filter on `is_current` or date ranges.

**Type 3 — Add a Column**: Keep both old and new values in the same row (`previous_city`, `current_city`). Simple to query but only tracks one change.

Most data warehouses use Type 2 for important dimensions (customers, products) and Type 1 for less important ones (where history doesn't matter).

> **Key Takeaway:** Dimensional modeling (star schemas) is the standard for analytical data. Fact tables record "what happened," dimension tables provide "context." This separation makes analytical queries simple, fast, and intuitive.

---

## Document and Graph Models

Relational databases work beautifully for structured, tabular data with well-defined relationships. But not all data fits neatly into tables.

### Document Databases

When your data is naturally hierarchical — a product listing with nested specifications, a user profile with varying fields, a blog post with embedded comments — a **document database** stores it as a single JSON-like document:

```json
{
  "_id": "prod_12345",
  "name": "Wireless Noise-Canceling Headphones",
  "brand": "AudioTech",
  "price": 299.99,
  "category": ["Electronics", "Audio", "Headphones"],
  "specifications": {
    "driver_size": "40mm",
    "frequency_response": "4Hz-40kHz",
    "battery_life_hours": 30,
    "weight_grams": 250,
    "connectivity": ["Bluetooth 5.2", "USB-C", "3.5mm"]
  },
  "reviews": [
    {
      "user_id": "user_789",
      "rating": 5,
      "text": "Best headphones I've ever owned",
      "date": "2026-03-15"
    },
    {
      "user_id": "user_456",
      "rating": 4,
      "text": "Great sound, slightly tight fit",
      "date": "2026-03-20"
    }
  ],
  "inventory": {
    "warehouse_a": 150,
    "warehouse_b": 80,
    "warehouse_c": 200
  }
}
```

The advantages: no joins needed to load a complete product (it's all in one document), flexible schema (different products can have different specifications), and natural mapping to how applications use data.

The trade-off: if you need to find "all reviews by user_789 across all products," you're scanning every document. Relationships *between* documents are awkward. Document databases shine for *self-contained entities* read as a whole; they struggle with *cross-entity queries*.

**Embed vs Reference**: Put data inside the document (embed) when it's always accessed together and owned by the parent. Use references (foreign keys) when data is shared across documents or updated independently.

### Graph Databases

When *relationships* are the most important part of your data, graph databases are the natural fit. Social networks, recommendation engines, fraud detection, knowledge graphs — all are fundamentally about connections.

A graph database stores **nodes** (entities) and **edges** (relationships), both of which can have **properties**. Here's how you'd model a social network in Neo4j's Cypher query language:

```cypher
// Create users (nodes)
CREATE (alice:User {name: 'Alice', joined: date('2025-01-15')})
CREATE (bob:User {name: 'Bob', joined: date('2025-02-20')})
CREATE (charlie:User {name: 'Charlie', joined: date('2025-03-10')})

// Create relationships (edges)
CREATE (alice)-[:FOLLOWS {since: date('2025-03-01')}]->(bob)
CREATE (bob)-[:FOLLOWS {since: date('2025-03-15')}]->(charlie)
CREATE (alice)-[:FOLLOWS {since: date('2025-04-01')}]->(charlie)

// Find friends-of-friends (2 hops) — trivial in a graph, painful in SQL
MATCH (alice:User {name: 'Alice'})-[:FOLLOWS]->()-[:FOLLOWS]->(recommended)
WHERE NOT (alice)-[:FOLLOWS]->(recommended) AND recommended <> alice
RETURN DISTINCT recommended.name AS suggestion;
```

That "friends-of-friends" query would require self-joins and subqueries in SQL and would get slower as the network grows. In a graph database, it's a simple traversal that stays fast regardless of total data size — it only touches the nodes it visits.

> **Key Takeaway:** Use relational databases for structured data with complex queries and transactions. Use document databases for hierarchical, self-contained entities with flexible schemas. Use graph databases when relationships are the primary query pattern.

---

## Event-Driven Schemas

In modern distributed systems, events are often the primary data format. An **event** records something that happened: "user clicked button," "order was placed," "temperature exceeded threshold." Designing schemas for events requires thinking differently from traditional database design.

### The Event Envelope Pattern

Every event should include metadata (the "envelope") alongside its payload:

```json
{
  "event_id": "evt_a1b2c3d4",
  "event_type": "order.placed",
  "event_version": "2.1",
  "timestamp": "2026-04-01T14:30:00Z",
  "source": "order-service",
  "correlation_id": "req_x7y8z9",
  "payload": {
    "order_id": "ord_12345",
    "customer_id": "cust_678",
    "items": [
      {"product_id": "prod_111", "quantity": 2, "price": 29.99}
    ],
    "total": 59.98
  }
}
```

The envelope (`event_id`, `event_type`, `timestamp`, `source`, `correlation_id`) is standardized across all events. The `payload` varies by event type. The `correlation_id` lets you trace a request across multiple services.

### Schema Evolution with Avro

In streaming systems, producers and consumers evolve independently. You can't take down every consumer to change the event format. **Apache Avro** handles this with explicit schema definitions and compatibility rules.

Here's an Avro schema for an order event. The schema is registered in a Schema Registry, and each message includes the schema ID so consumers know how to deserialize it:

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "com.example.events",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total_amount", "type": "double"},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "item_count", "type": "int"},
    {"name": "timestamp", "type": "long"}
  ]
}
```

**Schema evolution rules:**
- **Backward compatible**: New schema can read old data. Adding a field *with a default value* is backward compatible — old messages just get the default.
- **Forward compatible**: Old schema can read new data. Removing a field *that had a default* is forward compatible — new messages just ignore the removed field.
- **Full compatible**: Both directions work. This is the safest option for production systems.

> **Key Takeaway:** In event-driven systems, schema evolution is not optional — it's a fundamental design concern. Use a schema registry and enforce compatibility rules. Adding optional fields is safe; removing required fields or changing types is not.

---

## Case Study: Designing the Data Model for an E-Commerce Platform

Let's tie everything together by designing the data model for a mid-sized e-commerce platform. This isn't just one model — different parts of the system need different approaches.

### The Operational Database (Relational, Normalized)

The transactional core — handling orders, payments, inventory — uses a normalized relational model. Correctness is paramount here: you can't oversell inventory or charge the wrong amount.

```sql
-- Core operational tables (PostgreSQL)
CREATE TABLE users (
    user_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE inventory (
    product_id    INTEGER REFERENCES products(product_id),
    warehouse_id  INTEGER REFERENCES warehouses(warehouse_id),
    quantity      INTEGER NOT NULL CHECK (quantity >= 0),
    reserved      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, warehouse_id)
);
```

### The Product Catalog (Document Store)

Product data varies wildly — a laptop has specifications (RAM, CPU, screen size) that a t-shirt doesn't (size, color, material). A document store handles this naturally with flexible schemas per product type.

### The Analytics Warehouse (Dimensional Model)

Business intelligence queries use a star schema built by nightly ETL from the operational database. Analysts query fact_orders joined to dimension tables, never touching the production database.

### The Recommendation Engine (Graph)

User-product interactions (viewed, purchased, wishlisted) form a graph. Finding "users who bought X also bought Y" is a graph traversal.

### The Event Stream (Avro on Kafka)

Every user action — page view, add to cart, purchase, review — is published as an Avro event to Kafka. This feeds the analytics warehouse (batch consumption), the recommendation engine (stream processing), and the real-time dashboards.

**The key insight**: a single e-commerce platform uses at least four different data modeling approaches, each matched to its specific access patterns and requirements. The operational database is normalized for correctness. The product catalog is denormalized for flexibility. The analytics warehouse is dimensionally modeled for query performance. The event stream is schema-evolved for decoupling.

> **Key Takeaway:** Real systems use multiple data models. Don't force everything into one paradigm. Match the model to the workload: relational for transactions, documents for flexible entities, dimensional for analytics, graphs for relationships, events for decoupled communication.

---

## What's Next

Now that you understand how to model data, Module 3 dives into *where* to store it. We'll explore the internals of storage engines — how B-trees and LSM-trees work, why columnar storage revolutionized analytics, and how modern table formats like Delta Lake and Apache Iceberg brought database-like reliability to data lakes.
