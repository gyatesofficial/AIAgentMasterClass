# Module 10: Capstone Project -- Real-Time E-Commerce Analytics Platform

## Why a Capstone Matters

This capstone is designed to be THE project on your resume. Hiring managers want to see a complete, end-to-end data platform -- not a collection of disconnected tutorials. They want proof that you can take messy, multi-source data and turn it into something an analyst, a machine learning model, or a business stakeholder can actually use.

Everything you built in Modules 1 through 9 converges here: Docker containerization, SQL modeling, Python pipelines, Kafka streaming, Airflow orchestration, star schema design, data quality with Great Expectations, and AI-powered embeddings. This is not a toy example. This is essentially a miniature version of what you would build at a mid-size company running an e-commerce platform.

> **Key Takeaway:** A single well-built, fully documented project is worth more than ten half-finished repos. This capstone is your chance to show depth, not breadth.

---

## Architecture Overview

The platform follows a layered architecture that mirrors real production data systems. Every layer maps directly to a module you have already completed:

```
Data Sources          Ingestion           Raw Storage         Processing
+-----------+      +-------------+     +------------+     +-----------+
| REST API  |----->| Python/httpx|---->|            |     |           |
| (products)|      +-------------+     |  PostgreSQL |---->| Star      |
| Kafka     |----->| Kafka       |---->|  raw.*     |     | Schema    |
| (events)  |      | Consumer    |     |            |     | Builder   |
| CSV       |----->| FileLoader  |---->|            |     |           |
| (inventory)|     +-------------+     +------------+     +-----------+
                                                               |
        AI / Serving          Quality              Warehouse   |
      +-------------+    +------------+      +-----------+     |
      | Embeddings  |<---| Airflow    |<-----|analytics.*|<----+
      | Vector      |    | Quality    |      |dim/fact   |
      | FastAPI     |    | Checks     |      |tables     |
      +-------------+    +------------+      +-----------+
```

### How Modules 1-9 Connect

| Layer | Module | What You Built |
|-------|--------|----------------|
| **Infrastructure** | Module 1 (Docker, Git) | `docker-compose.yml` that spins up Postgres, Airflow, Kafka, MinIO |
| **Storage** | Module 2 (SQL) | Raw tables, dimension tables, fact tables -- all the DDL in `sql/` |
| **Data Modeling** | Module 3 (Modeling) | Star schema with SCD Type 2 dimensions and grain-level fact tables |
| **Python Pipelines** | Module 4 (Python) | The `src/` package: API clients, file loaders, Kafka producer/consumer |
| **Ingestion** | Module 5 (Ingestion) | Three ingestion patterns: REST API, streaming (Kafka), batch file loads |
| **Orchestration** | Module 6 (Airflow) | Four DAGs that run ingestion, transformation, quality checks, and embeddings |
| **Transformation** | Module 7 (Transforms) | `StarSchemaBuilder` with SCD logic, dimension key lookups, derived facts |
| **Data Quality** | Module 8 (Quality) | Great Expectations integration + custom quality checks with alerting |
| **AI / Serving** | Module 9 (AI) | Product embeddings via pgvector, similarity search API via FastAPI |

> **At your job:** This is the same layered approach used at companies like Shopify, Instacart, and Wayfair. The specific tools differ (Snowflake instead of Postgres, Flink instead of Kafka consumer, dbt instead of raw SQL), but the architecture pattern is universal. If you can explain each layer and why it exists, you can adapt to any company's stack.

---

## Project Structure

The companion code lives in `de-fast-track/modules/module-10/`. The `starter/` directory has TODO stubs for you to implement. The `solution/` directory has complete, working code.

```
ecommerce-data-platform/
├── docker-compose.yml          # Full stack: Postgres+pgvector, Airflow, Kafka, MinIO
├── pyproject.toml              # Python dependencies
├── .env.example                # Environment variable template
├── .github/workflows/ci.yml   # GitHub Actions CI pipeline
├── sql/
│   ├── 001_create_raw_tables.sql
│   ├── 002_create_dim_tables.sql
│   ├── 003_create_fact_tables.sql
│   ├── 004_create_quality_tables.sql
│   └── 005_create_vector_tables.sql
├── data/
│   └── generate_seed_data.py   # Creates realistic test data
├── dags/
│   ├── ingest_products.py      # Ingestion DAG
│   ├── transform_star_schema.py # Transformation DAG
│   ├── quality_checks.py       # Data quality DAG
│   └── embeddings_pipeline.py  # AI embeddings DAG
├── src/
│   ├── common/
│   │   ├── config.py           # Centralized configuration
│   │   └── db.py               # Database connection utilities
│   ├── ingestion/
│   │   ├── api_client.py       # REST API product ingestion
│   │   ├── file_loader.py      # CSV/JSON file loading
│   │   ├── kafka_producer.py   # Event stream producer
│   │   └── kafka_consumer.py   # Event stream consumer
│   ├── transformation/
│   │   └── star_schema.py      # Star schema builder with SCD
│   ├── quality/
│   │   ├── expectations.py     # Quality check definitions
│   │   └── alerts.py           # Alerting on failures
│   └── ai/
│       ├── embeddings.py       # Product embedding generation
│       ├── vector_search.py    # Similarity search logic
│       └── api.py              # FastAPI serving layer
└── tests/
    ├── test_ingestion.py
    ├── test_transformation.py
    └── test_quality.py
```

> **At your job:** This is not an arbitrary file layout. Separating `src/` into domain-oriented subpackages (`ingestion/`, `transformation/`, `quality/`, `ai/`) is standard practice. It means different team members can work on different layers without stepping on each other. When a hiring manager opens your repo, this structure signals "this person has worked on real teams."

---

## Phase 1: Infrastructure Setup

**TL;DR:** Get Docker Compose running with Postgres (+ pgvector), Airflow, Kafka, and MinIO. Create all database schemas. Generate seed data.

### Docker Compose Stack

The `docker-compose.yml` spins up seven services. This is your entire data platform in one command.

See companion code: `starter/docker-compose.yml`

```yaml
services:
  warehouse-db:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: dataeng
      POSTGRES_PASSWORD: dataeng
      POSTGRES_DB: warehouse
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
      - warehouse_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataeng"]
      interval: 10s
      timeout: 5s
      retries: 5

  airflow-db:
    image: postgres:16
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow

  airflow-init:
    image: apache/airflow:2.8.1-python3.11
    depends_on:
      - airflow-db
    environment:
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-db:5432/airflow
    command: >
      bash -c "airflow db init &&
        airflow users create --username admin --password admin
        --firstname Admin --lastname User --role Admin --email admin@example.com || true"

  airflow-webserver:
    image: apache/airflow:2.8.1-python3.11
    depends_on:
      airflow-init:
        condition: service_completed_successfully
      warehouse-db:
        condition: service_healthy
    ports:
      - "8080:8080"
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-db:5432/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src:/opt/airflow/src
    command: webserver

  airflow-scheduler:
    image: apache/airflow:2.8.1-python3.11
    depends_on:
      airflow-init:
        condition: service_completed_successfully
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-db:5432/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src:/opt/airflow/src
    command: scheduler

  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.6.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

volumes:
  warehouse_data:
  minio_data:
```

Notice the key design decisions here. The `warehouse-db` uses `pgvector/pgvector:pg16` instead of plain Postgres because we need vector similarity search later. The SQL files in `sql/` are mounted to `/docker-entrypoint-initdb.d` so schemas are created automatically on first boot. The Airflow webserver and scheduler both mount `./dags` and `./src` so they can find your DAG definitions and source code.

> **At your job:** Production environments would separate these into individual services on Kubernetes, each with its own scaling policy. But for development and portfolio purposes, Docker Compose gives you the entire stack with `docker compose up -d`. This is exactly how most teams develop locally.

### Database Schema

The SQL files execute in alphabetical order when the database starts. They create three schemas: `raw` (landing zone), `analytics` (star schema), and `quality` (check results and quarantine).

See companion code: `starter/sql/001_create_raw_tables.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS quality;

-- Raw tables
CREATE TABLE raw.products (
    product_id INT PRIMARY KEY,
    product_name VARCHAR(300) NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    unit_cost NUMERIC(10,2),
    unit_price NUMERIC(10,2),
    description TEXT,
    loaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE raw.events (
    event_id VARCHAR(50) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    customer_id INT,
    product_id INT,
    event_data JSONB,
    event_timestamp TIMESTAMP NOT NULL,
    loaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE raw.inventory (
    product_id INT,
    warehouse VARCHAR(50),
    quantity_on_hand INT,
    reorder_point INT,
    loaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (product_id, warehouse)
);

CREATE TABLE raw.customers (
    customer_id INT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    segment VARCHAR(50),
    signup_date DATE,
    loaded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_raw_events_type ON raw.events(event_type);
CREATE INDEX idx_raw_events_ts ON raw.events(event_timestamp);
```

Every raw table has a `loaded_at` timestamp. This is not optional -- it is how you debug "when did this bad data arrive?" in production. The `event_data JSONB` column on `raw.events` stores the full event payload so you never lose data during ingestion, even if your schema does not cover every field.

See companion code: `starter/sql/002_create_dim_tables.sql`

```sql
-- Dimension tables
CREATE TABLE analytics.dim_products (
    product_key SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    product_name VARCHAR(300),
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    unit_cost NUMERIC(10,2),
    unit_price NUMERIC(10,2),
    effective_date DATE NOT NULL,
    expiry_date DATE NOT NULL DEFAULT '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE analytics.dim_customers (
    customer_key SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    name VARCHAR(200),
    email VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    segment VARCHAR(50),
    signup_date DATE,
    effective_date DATE NOT NULL,
    expiry_date DATE NOT NULL DEFAULT '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE analytics.dim_time (
    time_key INT PRIMARY KEY,
    calendar_date DATE NOT NULL UNIQUE,
    day_of_week VARCHAR(10),
    month INT,
    month_name VARCHAR(10),
    quarter INT,
    year INT,
    is_weekend BOOLEAN
);

-- Populate dim_time for 2024-2027
INSERT INTO analytics.dim_time (time_key, calendar_date, day_of_week,
    month, month_name, quarter, year, is_weekend)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT,
    d,
    TRIM(TO_CHAR(d, 'Day')),
    EXTRACT(MONTH FROM d),
    TRIM(TO_CHAR(d, 'Month')),
    EXTRACT(QUARTER FROM d),
    EXTRACT(YEAR FROM d),
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series('2024-01-01'::date, '2027-12-31'::date, '1 day') d;

CREATE INDEX idx_dim_products_natural ON analytics.dim_products(product_id, is_current);
CREATE INDEX idx_dim_customers_natural ON analytics.dim_customers(customer_id, is_current);
```

The `dim_products` and `dim_customers` tables use SCD Type 2 columns: `effective_date`, `expiry_date`, and `is_current`. This means when a customer moves from New York to Boston, we do not overwrite the old row. We expire it and insert a new current row. Historical orders still join to the version of the customer that existed when the order was placed. This is one of the most important concepts in dimensional modeling, and having it in your capstone is a strong signal to interviewers.

The `dim_time` table is pre-populated with every date from 2024 to 2027. This is standard practice -- analysts can join on `time_key` (an integer in `YYYYMMDD` format) to get day-of-week, quarter, and other calendar attributes without computing them in every query.

See companion code: `starter/sql/003_create_fact_tables.sql`

```sql
CREATE TABLE analytics.fact_orders (
    order_key SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    customer_key INT REFERENCES analytics.dim_customers(customer_key),
    product_key INT REFERENCES analytics.dim_products(product_key),
    time_key INT REFERENCES analytics.dim_time(time_key),
    quantity INT NOT NULL,
    unit_price NUMERIC(10,2),
    revenue NUMERIC(12,2),
    cost NUMERIC(12,2),
    profit NUMERIC(12,2)
);

CREATE TABLE analytics.fact_events (
    event_key SERIAL PRIMARY KEY,
    event_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    customer_key INT REFERENCES analytics.dim_customers(customer_key),
    product_key INT REFERENCES analytics.dim_products(product_key),
    time_key INT REFERENCES analytics.dim_time(time_key),
    event_data JSONB,
    event_timestamp TIMESTAMP NOT NULL
);

CREATE INDEX idx_fact_orders_time ON analytics.fact_orders(time_key);
CREATE INDEX idx_fact_orders_customer ON analytics.fact_orders(customer_key);
CREATE INDEX idx_fact_orders_product ON analytics.fact_orders(product_key);
CREATE INDEX idx_fact_events_type ON analytics.fact_events(event_type);
CREATE INDEX idx_fact_events_time ON analytics.fact_events(time_key);
```

Two fact tables, two different grains. `fact_orders` has one row per purchase line item. `fact_events` has one row per user interaction (page view, add to cart, search, etc.). The foreign keys to dimension tables enforce referential integrity -- you cannot load an order for a customer that does not exist in the dimension.

See companion code: `starter/sql/004_create_quality_tables.sql`

```sql
CREATE TABLE quality.check_results (
    check_id SERIAL PRIMARY KEY,
    check_name VARCHAR(200) NOT NULL,
    table_name VARCHAR(200),
    status VARCHAR(20) NOT NULL,
    details JSONB,
    checked_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE quality.quarantine (
    quarantine_id SERIAL PRIMARY KEY,
    source_table VARCHAR(200),
    record_data JSONB,
    violation_reason VARCHAR(500),
    quarantined_at TIMESTAMP DEFAULT NOW()
);
```

The quality schema gives you an audit trail. Every time quality checks run, the results are logged. The quarantine table is for records that fail validation -- they get isolated instead of silently corrupting your analytics tables.

See companion code: `starter/sql/005_create_vector_tables.sql`

```sql
CREATE TABLE analytics.product_embeddings (
    product_id INT PRIMARY KEY,
    product_name VARCHAR(300),
    category VARCHAR(100),
    description TEXT,
    embedding vector(384),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_product_embeddings_hnsw
ON analytics.product_embeddings USING hnsw (embedding vector_cosine_ops);
```

The `vector(384)` column stores embeddings from the `all-MiniLM-L6-v2` model (which produces 384-dimensional vectors). The HNSW index enables approximate nearest neighbor search -- this is what makes similarity queries fast even with thousands of products.

### Common Utilities

See companion code: `starter/src/common/config.py`

```python
"""Capstone project configuration."""
import os


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataeng:dataeng@localhost:5432/warehouse")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_USER = os.getenv("DB_USER", "dataeng")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "dataeng")
    DB_NAME = os.getenv("DB_NAME", "warehouse")

    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
    S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
    S3_BUCKET = os.getenv("S3_BUCKET", "raw-data")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
```

Every secret and connection string comes from environment variables with sensible defaults for local development. This pattern means the same code runs locally (hitting `localhost:5432`) and in CI (hitting a test database) without any code changes. The `.env.example` file documents which variables exist; developers copy it to `.env` and fill in their values.

See companion code: `starter/src/common/db.py`

```python
"""Database utilities."""
import psycopg2
from contextlib import contextmanager
from .config import Config


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(Config.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(commit=True):
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
```

The context managers handle connection lifecycle automatically. `get_cursor(commit=True)` means you never forget to commit or close a connection. The `rollback()` in the exception handler ensures partial writes do not corrupt the database.

### Seed Data Generator

See companion code: `starter/data/generate_seed_data.py`

```python
"""Generate seed data for the capstone project."""
import json
import csv
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUTPUT_DIR = Path(__file__).parent / "seed"
OUTPUT_DIR.mkdir(exist_ok=True)

CATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Audio", "Peripherals", "Accessories"],
    "Clothing": ["Shirts", "Pants", "Outerwear", "Shoes", "Accessories"],
    "Home & Garden": ["Furniture", "Kitchen", "Decor", "Tools", "Lighting"],
    "Sports": ["Running", "Yoga", "Cycling", "Outdoor", "Equipment"],
    "Books": ["Technical", "Fiction", "Business", "Science", "Self-Help"],
}

BRANDS = ["TechBrand", "ComfyWear", "ErgoLife", "FastFeet", "FlexFit",
           "SoundWave", "OReilly", "HomeStyle", "ActiveGear", "ReadMore"]

CITIES = [
    ("New York", "NY"), ("Los Angeles", "CA"), ("Chicago", "IL"),
    ("Houston", "TX"), ("Phoenix", "AZ"), ("Philadelphia", "PA"),
    ("San Antonio", "TX"), ("San Diego", "CA"), ("Dallas", "TX"),
    ("Austin", "TX"),
]

FIRST_NAMES = ["Alice","Bob","Carol","David","Eve","Frank","Grace","Hank","Ivy","Jack",
               "Karen","Leo","Mia","Noah","Olivia","Pete","Quinn","Rose","Sam","Tina"]
LAST_NAMES = ["Smith","Johnson","Brown","Davis","Wilson","Moore","Taylor","Anderson","Lee","Martinez"]


def generate_products(count=500):
    products = []
    pid = 1
    for category, subcats in CATEGORIES.items():
        for subcat in subcats:
            for i in range(count // (len(CATEGORIES) * 5)):
                cost = round(5 + random.random() * 195, 2)
                markup = 1.5 + random.random() * 2
                products.append({
                    "product_id": pid,
                    "product_name": f"{subcat} {random.choice(['Pro','Plus','Lite','Max','Ultra','Basic'])} {pid}",
                    "category": category,
                    "subcategory": subcat,
                    "brand": random.choice(BRANDS),
                    "unit_cost": cost,
                    "unit_price": round(cost * markup, 2),
                    "description": f"High-quality {subcat.lower()} product in the {category.lower()} category.",
                })
                pid += 1
    with open(OUTPUT_DIR / "products.json", "w") as f:
        json.dump(products[:count], f, indent=2)
    print(f"Generated {min(len(products), count)} products")
    return products[:count]


def generate_customers(count=1000):
    customers = []
    for i in range(1, count + 1):
        city, state = random.choice(CITIES)
        customers.append({
            "customer_id": i,
            "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "email": f"customer{i}@example.com",
            "city": city,
            "state": state,
            "segment": random.choice(["Consumer", "Consumer", "Consumer", "SMB", "SMB", "Enterprise"]),
            "signup_date": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 730))).strftime("%Y-%m-%d"),
        })
    with open(OUTPUT_DIR / "customers.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=customers[0].keys())
        writer.writeheader()
        writer.writerows(customers)
    print(f"Generated {count} customers")
    return customers


def generate_inventory(products, warehouses=None):
    if warehouses is None:
        warehouses = ["warehouse-east", "warehouse-west", "warehouse-central"]
    rows = []
    for p in products:
        for wh in warehouses:
            rows.append({
                "product_id": p["product_id"],
                "warehouse": wh,
                "quantity_on_hand": random.randint(0, 500),
                "reorder_point": random.randint(10, 50),
            })
    with open(OUTPUT_DIR / "inventory.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} inventory records")


def generate_events(products, customers, count=10000):
    event_types = ["page_view", "add_to_cart", "remove_from_cart", "purchase", "search"]
    events = []
    for _ in range(count):
        etype = random.choices(event_types, weights=[40, 25, 5, 20, 10], k=1)[0]
        cust = random.choice(customers)
        prod = random.choice(products)
        ts = datetime(2025, 1, 1) + timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": etype,
            "customer_id": cust["customer_id"],
            "product_id": prod["product_id"],
            "timestamp": ts.isoformat(),
        }
        if etype == "purchase":
            qty = random.randint(1, 4)
            event["quantity"] = qty
            event["unit_price"] = prod["unit_price"]
            event["total_amount"] = round(qty * prod["unit_price"], 2)
        elif etype == "search":
            event["search_term"] = random.choice(
                ["laptop", "shoes", "headphones", "desk", "book", "camera"]
            )
        events.append(event)

    with open(OUTPUT_DIR / ".." / "sample_events.json", "w") as f:
        json.dump(events, f, indent=2)
    print(f"Generated {count} events")


if __name__ == "__main__":
    products = generate_products(500)
    customers = generate_customers(1000)
    generate_inventory(products)
    generate_events(products, customers, 10000)
    print("\nSeed data generation complete!")
```

Expected output:

```
Generated 500 products
Generated 1000 customers
Generated 1500 inventory records
Generated 10000 events

Seed data generation complete!
```

The seed data is realistic: 5 categories with 5 subcategories each, 500 products with cost/markup pricing, 1,000 customers across 10 cities, 1,500 inventory records across 3 warehouses, and 10,000 events with weighted probabilities (page views are most common, purchases less so). Using `random.seed(42)` makes it deterministic -- every team member generates the same data.

### Verify Phase 1

```bash
# Generate seed data
mkdir -p data/seed
python data/generate_seed_data.py

# Start the stack
docker compose up -d

# Wait 1-2 minutes for everything to initialize, then verify:

# Database schemas exist
docker compose exec warehouse-db psql -U dataeng -d warehouse -c "\dt raw.*"
docker compose exec warehouse-db psql -U dataeng -d warehouse -c "\dt analytics.*"

# MinIO is running -- open http://localhost:9001 (minioadmin/minioadmin)
# Airflow is running -- open http://localhost:8080 (admin/admin)
```

> **Phase 1 Checkpoint:** All services running, schemas created, seed data generated.

---

## Phase 2: Data Ingestion

**TL;DR:** Build three ingestion pipelines: (1) JSON file loader for products, (2) Kafka producer/consumer for real-time user events, (3) CSV file loader for customer and inventory data. Each is wrapped in an Airflow DAG.

### File Loader (Products, Customers, Inventory)

See companion code: `solution/src/ingestion/file_loader.py`

```python
"""File loader — loads CSV/JSON seed data into Postgres raw tables."""
import csv
import json
import logging
import psycopg2
from ..common.config import Config

logger = logging.getLogger(__name__)


class FileLoader:
    def __init__(self, db_url: str = None):
        self.conn = psycopg2.connect(db_url or Config.DATABASE_URL)

    def load_customers(self, filepath: str):
        with open(filepath) as f:
            reader = csv.DictReader(f)
            cur = self.conn.cursor()
            count = 0
            for row in reader:
                cur.execute("""
                    INSERT INTO raw.customers (customer_id, name, email, city, state, segment, signup_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (customer_id) DO UPDATE SET
                        name=EXCLUDED.name, email=EXCLUDED.email, city=EXCLUDED.city,
                        state=EXCLUDED.state, segment=EXCLUDED.segment, loaded_at=NOW()
                """, (row["customer_id"], row["name"], row["email"],
                      row["city"], row["state"], row["segment"], row["signup_date"]))
                count += 1
            self.conn.commit()
            logger.info(f"Loaded {count} customers")

    def load_inventory(self, filepath: str):
        with open(filepath) as f:
            reader = csv.DictReader(f)
            cur = self.conn.cursor()
            count = 0
            for row in reader:
                cur.execute("""
                    INSERT INTO raw.inventory (product_id, warehouse, quantity_on_hand, reorder_point)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (product_id, warehouse) DO UPDATE SET
                        quantity_on_hand=EXCLUDED.quantity_on_hand, loaded_at=NOW()
                """, (row["product_id"], row["warehouse"],
                      row["quantity_on_hand"], row["reorder_point"]))
                count += 1
            self.conn.commit()
            logger.info(f"Loaded {count} inventory records")

    def load_products(self, filepath: str):
        with open(filepath) as f:
            products = json.load(f)
        cur = self.conn.cursor()
        for p in products:
            cur.execute("""
                INSERT INTO raw.products (product_id, product_name, category, subcategory,
                    brand, unit_cost, unit_price, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    product_name=EXCLUDED.product_name, category=EXCLUDED.category,
                    unit_price=EXCLUDED.unit_price, loaded_at=NOW()
            """, (p["product_id"], p["product_name"], p["category"],
                  p["subcategory"], p["brand"], p["unit_cost"],
                  p["unit_price"], p.get("description", "")))
        self.conn.commit()
        logger.info(f"Loaded {len(products)} products")

    def close(self):
        self.conn.close()
```

Every INSERT uses `ON CONFLICT ... DO UPDATE`. This makes the pipeline idempotent -- you can run it twice and get the same result. This is critical for production pipelines where retries are common.

### Kafka Streaming (Events)

See companion code: `solution/src/ingestion/kafka_producer.py`

```python
"""Event producer — simulates e-commerce traffic."""
import json
import time
import random
import uuid
import logging
from datetime import datetime
from confluent_kafka import Producer
from ..common.config import Config

logger = logging.getLogger(__name__)

EVENT_TYPES = ["page_view", "add_to_cart", "remove_from_cart", "purchase", "search"]


class EventProducer:
    def __init__(self, bootstrap_servers: str = None, topic: str = "ecommerce-events"):
        self.topic = topic
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers or Config.KAFKA_BOOTSTRAP_SERVERS,
        })

    def generate_event(self, customer_id: int) -> dict:
        etype = random.choices(EVENT_TYPES, weights=[40, 25, 5, 20, 10], k=1)[0]
        product_id = random.randint(1, 500)
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": etype,
            "customer_id": customer_id,
            "product_id": product_id,
            "timestamp": datetime.now().isoformat(),
        }
        if etype == "purchase":
            qty = random.randint(1, 4)
            price = round(10 + random.random() * 190, 2)
            event["quantity"] = qty
            event["unit_price"] = price
            event["total_amount"] = round(qty * price, 2)
        elif etype == "search":
            event["search_term"] = random.choice(
                ["laptop", "shoes", "headphones", "desk", "book", "camera"]
            )
        return event

    def run(self, events_per_second: float = 10.0, max_events: int = 0):
        logger.info(f"Producing to '{self.topic}' at ~{events_per_second} events/sec")
        count = 0
        try:
            while True:
                event = self.generate_event(random.randint(1, 1000))
                self.producer.produce(
                    self.topic,
                    key=str(event["customer_id"]),
                    value=json.dumps(event),
                )
                self.producer.poll(0)
                count += 1
                if max_events and count >= max_events:
                    break
                time.sleep(1.0 / events_per_second)
        except KeyboardInterrupt:
            pass
        finally:
            self.producer.flush()
            logger.info(f"Produced {count} events")
```

The producer uses `customer_id` as the Kafka message key. This ensures all events for the same customer land on the same partition, preserving per-customer ordering. The weighted `random.choices` creates realistic traffic patterns: 40% page views, 25% add-to-cart, 20% purchases, 10% search, 5% remove-from-cart.

See companion code: `solution/src/ingestion/kafka_consumer.py`

```python
"""Kafka event consumer — reads events and inserts to raw.events."""
import json
import logging
import psycopg2
from confluent_kafka import Consumer, KafkaError
from ..common.config import Config

logger = logging.getLogger(__name__)


class EventConsumer:
    def __init__(self, bootstrap_servers: str = None, topic: str = "ecommerce-events",
                 group_id: str = "capstone-consumer"):
        self.topic = topic
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers or Config.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
        })
        self.consumer.subscribe([topic])
        self.conn = psycopg2.connect(Config.DATABASE_URL)

    def consume(self, max_messages: int = 1000) -> int:
        cur = self.conn.cursor()
        count = 0
        while count < max_messages:
            msg = self.consumer.poll(1.0)
            if msg is None:
                break
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    break
                logger.error(f"Consumer error: {msg.error()}")
                continue

            event = json.loads(msg.value().decode("utf-8"))
            cur.execute("""
                INSERT INTO raw.events (event_id, event_type, customer_id, product_id,
                    event_data, event_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
            """, (
                event["event_id"], event["event_type"],
                event.get("customer_id"), event.get("product_id"),
                json.dumps(event), event["timestamp"],
            ))
            count += 1
            if count % 100 == 0:
                self.conn.commit()

        self.conn.commit()
        logger.info(f"Consumed {count} events")
        return count

    def close(self):
        self.consumer.close()
        self.conn.close()
```

The consumer commits to Postgres every 100 messages for throughput, and stores the full event JSON in `event_data` alongside the parsed fields. The `ON CONFLICT DO NOTHING` handles duplicate events gracefully -- exactly-once semantics at the database level.

> **At your job:** In production, you would likely use a framework like Flink or Spark Structured Streaming instead of a raw consumer loop. But the pattern is identical: consume from a topic, deserialize, insert to a raw table. Understanding the fundamentals makes the frameworks easy to learn.

### Airflow DAG for Ingestion

See companion code: `solution/dags/ingest_products.py`

```python
"""DAG: Ingest products from seed data."""
from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="ingest_products",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["capstone", "ingestion"],
)
def ingest_products():

    @task()
    def load_products():
        from src.ingestion.file_loader import FileLoader
        loader = FileLoader()
        loader.load_products("data/seed/products.json")
        loader.close()

    @task()
    def load_customers():
        from src.ingestion.file_loader import FileLoader
        loader = FileLoader()
        loader.load_customers("data/seed/customers.csv")
        loader.close()

    @task()
    def load_inventory():
        from src.ingestion.file_loader import FileLoader
        loader = FileLoader()
        loader.load_inventory("data/seed/inventory.csv")
        loader.close()

    load_products()
    load_customers()
    load_inventory()


ingest_products()
```

Three independent tasks -- products, customers, and inventory can load in parallel since they write to different tables. The imports happen inside the task functions (not at module level) so Airflow's DAG parser stays fast. This is an Airflow best practice that trips up many beginners.

> **Pro Tip:** Create similar DAGs for events (`ingest_events.py`) and inventory. The events DAG should trigger the Kafka consumer; the inventory DAG should use the FileLoader.

> **Phase 2 Checkpoint:** All three ingestion pipelines load data into raw tables. Products, customers, and inventory in the database.

---

## Phase 3: Transformation (Star Schema Population)

**TL;DR:** Transform raw data into a star schema with SCD Type 2 for customers, SCD Type 1 for products, and fact tables populated via dimension key lookups. Orders are derived from purchase events.

See companion code: `solution/src/transformation/star_schema.py`

```python
"""Star schema builder — transforms raw data into analytics dimensions and facts."""
import logging
import psycopg2
from ..common.config import Config

logger = logging.getLogger(__name__)


class StarSchemaBuilder:
    def __init__(self, db_url: str = None):
        self.conn = psycopg2.connect(db_url or Config.DATABASE_URL)

    def build_dim_products(self):
        cur = self.conn.cursor()
        # Expire changed products
        cur.execute("""
            UPDATE analytics.dim_products dp
            SET expiry_date = CURRENT_DATE - 1, is_current = FALSE
            FROM raw.products rp
            WHERE dp.product_id = rp.product_id AND dp.is_current = TRUE
              AND (dp.category != rp.category OR dp.unit_price != rp.unit_price)
        """)
        # Insert new/changed products
        cur.execute("""
            INSERT INTO analytics.dim_products (product_id, product_name, category, subcategory,
                brand, unit_cost, unit_price, effective_date)
            SELECT product_id, product_name, category, subcategory, brand,
                   unit_cost, unit_price, CURRENT_DATE
            FROM raw.products rp
            WHERE NOT EXISTS (
                SELECT 1 FROM analytics.dim_products dp
                WHERE dp.product_id = rp.product_id AND dp.is_current = TRUE
            )
        """)
        self.conn.commit()
        logger.info("dim_products built")

    def build_dim_customers(self):
        cur = self.conn.cursor()
        # SCD Type 2 for customer changes
        cur.execute("""
            UPDATE analytics.dim_customers dc
            SET expiry_date = CURRENT_DATE - 1, is_current = FALSE
            FROM raw.customers rc
            WHERE dc.customer_id = rc.customer_id AND dc.is_current = TRUE
              AND (dc.city != rc.city OR dc.state != rc.state OR dc.segment != rc.segment)
        """)
        cur.execute("""
            INSERT INTO analytics.dim_customers (customer_id, name, email, city, state,
                segment, signup_date, effective_date)
            SELECT customer_id, name, email, city, state, segment, signup_date::date, CURRENT_DATE
            FROM raw.customers rc
            WHERE NOT EXISTS (
                SELECT 1 FROM analytics.dim_customers dc
                WHERE dc.customer_id = rc.customer_id AND dc.is_current = TRUE
            )
        """)
        self.conn.commit()
        logger.info("dim_customers built")

    def build_fact_events(self):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO analytics.fact_events (event_id, event_type, customer_key, product_key,
                time_key, event_data, event_timestamp)
            SELECT re.event_id, re.event_type, dc.customer_key, dp.product_key,
                   TO_CHAR(re.event_timestamp, 'YYYYMMDD')::INT,
                   re.event_data, re.event_timestamp
            FROM raw.events re
            LEFT JOIN analytics.dim_customers dc
                ON re.customer_id = dc.customer_id AND dc.is_current = TRUE
            LEFT JOIN analytics.dim_products dp
                ON re.product_id = dp.product_id AND dp.is_current = TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM analytics.fact_events fe WHERE fe.event_id = re.event_id
            )
        """)
        self.conn.commit()
        cur.execute("SELECT COUNT(*) FROM analytics.fact_events")
        logger.info(f"fact_events: {cur.fetchone()[0]} total rows")

    def build_fact_orders(self):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO analytics.fact_orders (order_id, customer_key, product_key, time_key,
                quantity, unit_price, revenue, cost, profit)
            SELECT re.event_id, dc.customer_key, dp.product_key,
                   TO_CHAR(re.event_timestamp, 'YYYYMMDD')::INT,
                   (re.event_data->>'quantity')::INT,
                   (re.event_data->>'unit_price')::NUMERIC,
                   (re.event_data->>'total_amount')::NUMERIC,
                   (re.event_data->>'quantity')::INT * COALESCE(dp.unit_cost, 0),
                   (re.event_data->>'total_amount')::NUMERIC - (re.event_data->>'quantity')::INT * COALESCE(dp.unit_cost, 0)
            FROM raw.events re
            LEFT JOIN analytics.dim_customers dc
                ON re.customer_id = dc.customer_id AND dc.is_current = TRUE
            LEFT JOIN analytics.dim_products dp
                ON re.product_id = dp.product_id AND dp.is_current = TRUE
            WHERE re.event_type = 'purchase'
              AND NOT EXISTS (
                  SELECT 1 FROM analytics.fact_orders fo WHERE fo.order_id = re.event_id
              )
        """)
        self.conn.commit()
        cur.execute("SELECT COUNT(*) FROM analytics.fact_orders")
        logger.info(f"fact_orders: {cur.fetchone()[0]} total rows")

    def run(self):
        self.build_dim_products()
        self.build_dim_customers()
        self.build_fact_events()
        self.build_fact_orders()
        logger.info("Star schema build complete")

    def close(self):
        self.conn.close()
```

This is the heart of the project. Study it carefully:

- **`build_dim_products`**: First expires any product rows where the category or price changed (SCD Type 2 expiration), then inserts new rows for products that do not have a current dimension record. The `NOT EXISTS` pattern ensures idempotency.
- **`build_dim_customers`**: Same SCD Type 2 pattern for customers. Tracks changes in city, state, and segment. When a customer moves from New York to Boston, the old row gets `is_current = FALSE` and a new row is inserted.
- **`build_fact_events`**: Joins raw events to dimension tables to get surrogate keys (`customer_key`, `product_key`), converts the timestamp to `time_key` format (`YYYYMMDD` integer), and deduplicates via `NOT EXISTS`.
- **`build_fact_orders`**: Filters for `event_type = 'purchase'` only, extracts quantity/price/amount from the JSONB `event_data` column, and calculates cost and profit using the dimension table's `unit_cost`.

> **At your job:** The pattern of "expire old dimension rows, insert new ones, then populate facts with dimension key lookups" is the backbone of every Kimball-style data warehouse. dbt automates much of this with snapshot models, but understanding the raw SQL gives you the ability to debug when dbt does something unexpected.

### Airflow DAG for Transformation

See companion code: `solution/dags/transform_star_schema.py`

```python
"""DAG: Build star schema from raw data."""
from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="transform_star_schema",
    schedule="0 7 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["capstone", "transformation"],
)
def transform_star_schema():

    @task()
    def build_dimensions():
        from src.transformation.star_schema import StarSchemaBuilder
        builder = StarSchemaBuilder()
        builder.build_dim_products()
        builder.build_dim_customers()
        builder.close()

    @task()
    def build_facts():
        from src.transformation.star_schema import StarSchemaBuilder
        builder = StarSchemaBuilder()
        builder.build_fact_events()
        builder.build_fact_orders()
        builder.close()

    dims = build_dimensions()
    facts = build_facts()
    dims >> facts


transform_star_schema()
```

Dimensions must be built before facts (the `dims >> facts` dependency). Facts need surrogate keys from the dimension tables, so this ordering is not optional. The schedule is `0 7 * * *` (7 AM daily), giving the ingestion DAG time to complete first.

> **Phase 3 Checkpoint:** Star schema populated. Dimensions have correct SCD behavior. Fact tables have proper foreign key lookups.

---

## Phase 4: Data Quality and AI Component

**TL;DR:** Add quality checks on raw event data (null checks, uniqueness, valid event types, row count). Build a product embeddings pipeline that generates vectors and stores them in pgvector. Serve similarity search and semantic product search via FastAPI.

### Data Quality Checks

See companion code: `solution/src/quality/expectations.py`

```python
"""Data quality checks for the capstone pipeline."""
import logging
import psycopg2
import json
from ..common.config import Config

logger = logging.getLogger(__name__)


def run_quality_checks(db_url: str = None) -> list[dict]:
    conn = psycopg2.connect(db_url or Config.DATABASE_URL)
    cur = conn.cursor()
    results = []

    checks = [
        ("raw_events_not_empty", "SELECT COUNT(*) FROM raw.events", lambda v: v > 0),
        ("raw_events_no_null_ids", "SELECT COUNT(*) FROM raw.events WHERE event_id IS NULL", lambda v: v == 0),
        ("raw_events_valid_types",
         "SELECT COUNT(*) FROM raw.events WHERE event_type NOT IN ('page_view','add_to_cart','remove_from_cart','purchase','search')",
         lambda v: v == 0),
        ("dim_products_no_duplicates",
         "SELECT COUNT(*) - COUNT(DISTINCT product_id) FROM analytics.dim_products WHERE is_current",
         lambda v: v == 0),
        ("dim_customers_no_duplicates",
         "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM analytics.dim_customers WHERE is_current",
         lambda v: v == 0),
        ("fact_orders_positive_revenue",
         "SELECT COUNT(*) FROM analytics.fact_orders WHERE revenue < 0",
         lambda v: v == 0),
        ("fact_orders_no_orphans",
         "SELECT COUNT(*) FROM analytics.fact_orders fo LEFT JOIN analytics.dim_customers dc ON fo.customer_key = dc.customer_key WHERE dc.customer_key IS NULL",
         lambda v: v == 0),
    ]

    for name, sql, check_fn in checks:
        cur.execute(sql)
        value = cur.fetchone()[0]
        passed = check_fn(value)
        status = "PASS" if passed else "FAIL"
        results.append({"check": name, "value": value, "status": status})
        logger.info(f"  {status}: {name} (value={value})")

        # Log to quality.check_results
        cur.execute("""
            INSERT INTO quality.check_results (check_name, table_name, status, details)
            VALUES (%s, %s, %s, %s)
        """, (name, "", status, json.dumps({"value": value})))

    conn.commit()
    conn.close()
    return results
```

Seven checks covering four quality dimensions:
- **Completeness:** `raw_events_not_empty` -- the table should have data
- **Validity:** `raw_events_no_null_ids` -- primary keys must not be null
- **Consistency:** `raw_events_valid_types` -- only known event types allowed
- **Uniqueness:** `dim_products_no_duplicates`, `dim_customers_no_duplicates` -- no duplicate current rows
- **Accuracy:** `fact_orders_positive_revenue` -- revenue should not be negative
- **Referential integrity:** `fact_orders_no_orphans` -- every order should link to a real customer

Every check result is logged to `quality.check_results` for auditing. This means you can query historical check results: "When did the orphan check first start failing?"

See companion code: `solution/src/quality/alerts.py`

```python
"""Alerting functions for quality check failures."""
import logging

logger = logging.getLogger(__name__)


def send_alert(check_name: str, details: dict):
    """Send an alert for a failed quality check.
    In production, this would integrate with Slack, PagerDuty, email, etc.
    """
    logger.warning(f"QUALITY ALERT: {check_name} -- {details}")


def evaluate_results(results: list[dict]) -> bool:
    """Evaluate quality check results and alert on failures. Returns True if all passed."""
    failures = [r for r in results if r["status"] == "FAIL"]
    if failures:
        for f in failures:
            send_alert(f["check"], f)
        logger.error(f"{len(failures)} quality checks FAILED")
        return False
    logger.info("All quality checks passed")
    return True
```

The alerting layer is intentionally simple -- a logging call that you can extend to Slack, PagerDuty, or email. The `evaluate_results` function returns a boolean so the Airflow DAG can fail the task if any check does not pass, preventing downstream consumers from using bad data.

### Airflow DAG for Quality Checks

See companion code: `solution/dags/quality_checks.py`

```python
"""DAG: Run data quality checks."""
from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="quality_checks",
    schedule="0 8 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["capstone", "quality"],
)
def quality_checks():

    @task()
    def run_checks():
        from src.quality.expectations import run_quality_checks
        from src.quality.alerts import evaluate_results
        results = run_quality_checks()
        all_passed = evaluate_results(results)
        if not all_passed:
            raise Exception("Quality checks failed -- see alerts")

    run_checks()


quality_checks()
```

Scheduled at 8 AM, one hour after the transformation DAG. If checks fail, the task raises an exception, which Airflow marks as a failure and triggers any configured alerting (email, Slack webhook, etc.).

### AI Component -- Product Embeddings

See companion code: `solution/src/ai/embeddings.py`

```python
"""Product embedder — generates and stores product embeddings."""
import logging
import psycopg2
from sentence_transformers import SentenceTransformer
from ..common.config import Config

logger = logging.getLogger(__name__)


class ProductEmbedder:
    def __init__(self, db_url: str = None, model_name: str = "all-MiniLM-L6-v2"):
        self.conn = psycopg2.connect(db_url or Config.DATABASE_URL)
        self.model = SentenceTransformer(model_name)

    def embed_products(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT product_id, product_name, category, description
            FROM raw.products
            WHERE product_id NOT IN (SELECT product_id FROM analytics.product_embeddings)
        """)
        products = cur.fetchall()
        if not products:
            logger.info("No new products to embed")
            return

        texts = [f"{r[1]} - {r[2]} - {r[3] or ''}" for r in products]
        embeddings = self.model.encode(texts, show_progress_bar=True)

        for product, embedding in zip(products, embeddings):
            cur.execute("""
                INSERT INTO analytics.product_embeddings (product_id, product_name, category, description, embedding)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding, updated_at = NOW()
            """, (product[0], product[1], product[2], product[3], embedding.tolist()))
        self.conn.commit()
        logger.info(f"Embedded {len(products)} products")

    def close(self):
        self.conn.close()
```

The embedder only processes products that do not already have embeddings (`NOT IN` subquery), making it incremental. The text fed to the model combines name, category, and description: `"Running Pro 42 - Sports - High-quality running product"`. This gives the embedding enough context for meaningful similarity.

### Similarity Search API

See companion code: `solution/src/ai/vector_search.py`

```python
"""Vector similarity search for products."""
import psycopg2
from sentence_transformers import SentenceTransformer
from ..common.config import Config


class ProductSearch:
    def __init__(self, db_url: str = None, model_name: str = "all-MiniLM-L6-v2"):
        self.conn = psycopg2.connect(db_url or Config.DATABASE_URL)
        self.model = SentenceTransformer(model_name)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        embedding = self.model.encode(query).tolist()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT product_id, product_name, category, description,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM analytics.product_embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (embedding, embedding, limit))
        return [
            {"product_id": r[0], "product_name": r[1], "category": r[2],
             "description": r[3], "similarity": float(r[4])}
            for r in cur.fetchall()
        ]

    def similar_to(self, product_id: int, limit: int = 5) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT p2.product_id, p2.product_name, p2.category,
                   1 - (p1.embedding <=> p2.embedding) AS similarity
            FROM analytics.product_embeddings p1, analytics.product_embeddings p2
            WHERE p1.product_id = %s AND p2.product_id != %s
            ORDER BY p1.embedding <=> p2.embedding LIMIT %s
        """, (product_id, product_id, limit))
        return [{"product_id": r[0], "product_name": r[1], "category": r[2], "similarity": float(r[3])}
                for r in cur.fetchall()]

    def close(self):
        self.conn.close()
```

Two search modes: `search()` takes a natural language query ("noise cancelling headphones"), embeds it, and finds the closest products. `similar_to()` takes a product ID and finds its nearest neighbors. The `<=>` operator is pgvector's cosine distance -- the HNSW index makes this fast.

See companion code: `solution/src/ai/api.py`

```python
"""FastAPI application for product search."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ShopFast Product Search", version="1.0")

_search = None


def get_search():
    global _search
    if _search is None:
        from .vector_search import ProductSearch
        _search = ProductSearch()
    return _search


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search")
def search_products(req: SearchRequest):
    return {"results": get_search().search(req.query, limit=req.limit)}


@app.get("/similar/{product_id}")
def similar_products(product_id: int, limit: int = 5):
    results = get_search().similar_to(product_id, limit=limit)
    if not results:
        raise HTTPException(404, "Product not found or no embeddings available")
    return {"results": results}
```

Try the API:

```bash
# Similar products
curl http://localhost:8000/similar/42?top_k=3

# Semantic search
curl "http://localhost:8000/search?q=noise+cancelling+headphones&top_k=5"

# Health check
curl http://localhost:8000/health
```

### Airflow DAG for Embeddings

See companion code: `solution/dags/embeddings_pipeline.py`

```python
"""DAG: Generate product embeddings."""
from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="embeddings_pipeline",
    schedule="0 9 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["capstone", "ai"],
)
def embeddings_pipeline():

    @task()
    def generate_embeddings():
        from src.ai.embeddings import ProductEmbedder
        embedder = ProductEmbedder()
        embedder.embed_products()
        embedder.close()

    generate_embeddings()


embeddings_pipeline()
```

Scheduled at 9 AM -- after quality checks pass at 8 AM. This creates a natural pipeline: ingest (daily) -> transform (7 AM) -> quality (8 AM) -> embeddings (9 AM). Each stage depends on the previous one completing successfully.

> **Phase 4 Checkpoint:** Quality checks run and pass. Product embeddings stored in pgvector. Similarity API returns results.

---

## Phase 5: Testing, CI/CD, and Documentation

**TL;DR:** Write unit tests, set up GitHub Actions CI, create a comprehensive README, and draw an architecture diagram. This is what turns a project into a portfolio piece.

### Tests

See companion code: `solution/tests/test_ingestion.py`

```python
"""Tests for ingestion components."""
import pytest
import json
import tempfile
import csv


def test_generate_seed_data():
    """Verify seed data generator produces expected output."""
    import random
    random.seed(42)

    categories = {"Electronics": ["Phones"], "Clothing": ["Shirts"]}
    products = []
    pid = 1
    for cat, subcats in categories.items():
        for sub in subcats:
            for i in range(5):
                products.append({"product_id": pid, "product_name": f"{sub} {pid}", "category": cat})
                pid += 1
    assert len(products) == 10
    assert all("product_id" in p for p in products)


def test_file_loader_customers_format():
    """Verify CSV format is correct for customer loading."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.DictWriter(f, fieldnames=["customer_id", "name", "email", "city", "state", "segment", "signup_date"])
        writer.writeheader()
        writer.writerow({
            "customer_id": 1, "name": "Test User", "email": "test@test.com",
            "city": "NYC", "state": "NY", "segment": "Consumer", "signup_date": "2025-01-01",
        })
        path = f.name

    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["customer_id"] == "1"
```

See companion code: `solution/tests/test_transformation.py`

```python
"""Tests for transformation logic."""
import pytest


def test_star_schema_builder_instantiation():
    """Verify StarSchemaBuilder can be imported."""
    from src.transformation.star_schema import StarSchemaBuilder
    assert StarSchemaBuilder is not None


def test_scd_type_2_logic():
    """Test SCD Type 2 logic conceptually."""
    existing = {"customer_id": 1, "city": "New York", "is_current": True}
    incoming = {"customer_id": 1, "city": "Boston"}

    changed = existing["city"] != incoming["city"]
    assert changed is True

    if changed:
        existing["is_current"] = False
        new_row = {**incoming, "is_current": True}
        assert new_row["city"] == "Boston"
        assert new_row["is_current"] is True
        assert existing["is_current"] is False
```

See companion code: `solution/tests/test_quality.py`

```python
"""Tests for quality check logic."""
import pytest
from src.quality.alerts import evaluate_results


def test_evaluate_all_pass():
    results = [
        {"check": "test1", "value": 0, "status": "PASS"},
        {"check": "test2", "value": 100, "status": "PASS"},
    ]
    assert evaluate_results(results) is True


def test_evaluate_with_failure():
    results = [
        {"check": "test1", "value": 0, "status": "PASS"},
        {"check": "test2", "value": 5, "status": "FAIL"},
    ]
    assert evaluate_results(results) is False


def test_evaluate_empty():
    assert evaluate_results([]) is True
```

The testing strategy covers three layers: ingestion (data format validation), transformation (SCD logic), and quality (alert evaluation). These tests run without a database connection, making them fast and suitable for CI.

> **At your job:** Teams with good test coverage catch bugs before they reach production. Even simple tests like "can I import this module?" and "does SCD logic correctly expire old rows?" prevent the most common failures.

### GitHub Actions CI

See companion code: `solution/.github/workflows/ci.yml`

```yaml
name: Capstone CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: dataeng
          POSTGRES_PASSWORD: dataeng
          POSTGRES_DB: warehouse
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --tb=short
```

The CI pipeline spins up a real Postgres instance with pgvector. This means your tests run against the same database engine as production -- no SQLite mocking that hides Postgres-specific issues. The `pip install -e ".[dev]"` installs both the main dependencies and the dev dependencies (pytest, ruff, pytest-cov) from `pyproject.toml`.

### README Template

Your README should look something like this (from the course PDF):

```markdown
# Real-Time E-Commerce Analytics Platform

A production-grade data platform built as the capstone project for
**The Data Engineering Fast Track** course.

## Architecture

[Include your architecture diagram here]

**Data Sources:** REST API (products), Kafka stream (user events), CSV (inventory)
**Storage:** S3/MinIO data lake + Postgres analytics warehouse
**Processing:** Python + SQL transformations, Airflow orchestration
**Data Model:** Star schema (fact_orders, fact_events, dim_products, dim_customers, dim_time)
**Data Quality:** Great Expectations with automated alerting
**AI Component:** Product embeddings via pgvector for similarity search

## Quick Start

```bash
# Clone and setup
git clone https://github.com/gyatesofficial/de-fast-track.git
cd de-fast-track/module-10/starter
cp .env.example .env

# Generate seed data
python data/generate_seed_data.py

# Start all services
docker-compose up -d

# Wait 1-2 minutes, then:
# Airflow UI: http://localhost:8080 (admin/admin)
# MinIO UI: http://localhost:9001 (minioadmin/minioadmin)
# Similarity API: http://localhost:8000/docs
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Orchestration | Apache Airflow 2.8 |
| Warehouse | PostgreSQL 16 + pgvector |
| Data Lake | MinIO (S3-compatible) |
| Streaming | Apache Kafka |
| Data Quality | Great Expectations |
| AI/Embeddings | OpenAI API / sentence-transformers |
| API | FastAPI |
| Infrastructure | Docker Compose, Terraform |
| CI/CD | GitHub Actions |
| Language | Python 3.11 |

## Data Model

### Star Schema

**Fact Tables:**
- `fact_orders` -- completed purchases (grain: one row per order line)
- `fact_events` -- all user events (grain: one row per event)

**Dimension Tables:**
- `dim_products` -- product catalog (SCD Type 1)
- `dim_customers` -- customer profiles (SCD Type 2)
- `dim_time` -- date dimension (2024-2027)

## Running Tests

```bash
pytest tests/ -v
```

## License

MIT
```

### Architecture Diagram Guide

For your draw.io or Excalidraw diagram, include these components:

**Left column (Data Sources):**
- REST API icon -> "Product Catalog API"
- Kafka icon -> "User Event Stream"
- File icon -> "CSV Inventory Upload"

**Center-top (Ingestion):**
- Airflow icon -> three sub-boxes: "API Ingester", "Kafka Consumer", "File Loader"

**Center (Storage):**
- S3 bucket -> "MinIO / S3 Data Lake" with layers: raw/ staging/ prod/
- Database -> "PostgreSQL + pgvector" with: Raw Schema, Analytics Star Schema, Vector Embeddings

**Center-bottom (Processing):**
- "SQL Transformations" (CTEs, Window Functions, SCD Type 2)
- "Great Expectations" (Schema, Completeness, Freshness, Volume)
- "Embedding Pipeline" (OpenAI / sentence-transformers)

**Right column (Serving):**
- "Analytics Queries"
- "FastAPI" with /similar/{id} and /search endpoints
- "Quality Alerts"

**Bottom:**
- Docker Compose, Terraform, GitHub Actions icons

---

## Completion Checklist

### Core Requirements (Must Have)

- [ ] **Repository structure** -- clean, organized, follows the template
- [ ] **Docker Compose** -- full stack starts with `docker compose up -d`
- [ ] **Data ingestion** -- at least 2 of 3 sources working (API, Kafka, CSV)
- [ ] **Star schema** -- fact and dimension tables populated with correct relationships
- [ ] **Airflow DAGs** -- at least 2 DAGs (ingestion + transformation)
- [ ] **Data quality** -- at least 5 Great Expectations checks that run and pass
- [ ] **AI component** -- product embeddings stored in pgvector
- [ ] **Similarity API** -- FastAPI endpoint returns similar products
- [ ] **Tests** -- at least 5 passing tests
- [ ] **README** -- includes architecture, setup instructions, tech stack

### Above and Beyond (Bonus)

- [ ] All 3 data sources working
- [ ] SCD Type 2 implemented in customer dimension
- [ ] Volume anomaly detection in quality checks
- [ ] Slack/webhook alerting on quality failures
- [ ] Terraform configs for AWS deployment
- [ ] GitHub Actions CI pipeline
- [ ] Data dictionary / column-level documentation
- [ ] Architecture diagram (draw.io / Excalidraw)
- [ ] Semantic search endpoint (query text -> similar products)
- [ ] 5-minute video walkthrough

### Scoring Guide

| Score | Level | Description |
|-------|-------|-------------|
| 10/10 Core | **Complete** | All core requirements met |
| 8-9/10 Core | **Strong** | Minor gaps but demonstrates full understanding |
| 6-7/10 Core | **Acceptable** | Key components work but some are incomplete |
| < 6/10 Core | **Needs Work** | Major components missing -- revisit relevant modules |
| 5+ Bonus | **Outstanding** | Portfolio-ready project, go get that job! |

---

## Making It Portfolio-Ready

### What Hiring Managers Actually Look For

When a hiring manager opens your GitHub profile and clicks on this repo, they spend about 30 seconds deciding whether to look deeper. Here is what they check, in order:

1. **README quality.** Is there a clear description, architecture diagram, and "how to run" section? If the README is empty or says "TODO", they close the tab.
2. **Repository structure.** Does it look like a real project? Separate directories for source code, tests, configs, and infrastructure? Or is everything dumped in the root?
3. **Docker Compose / infrastructure as code.** Can they actually run it? `docker compose up -d` that works is worth more than 10 pages of documentation.
4. **Tests.** Even a few tests signal professionalism. No tests signals "this person writes code and hopes it works."
5. **Commit history.** Clean, descriptive commits show discipline. A single "initial commit" with 50 files suggests the project was built in one sitting and never iterated on.

> **At your job:** These same criteria apply to code review. Senior engineers notice the same things: clean structure, meaningful tests, good documentation, and clear commit messages.

### How to Present the Project

**GitHub Profile Optimization:**
- Pin this repository to your profile
- Write a profile README that mentions "Real-Time E-Commerce Analytics Platform" with a link
- Add relevant topics to the repo: `data-engineering`, `airflow`, `kafka`, `postgres`, `python`, `docker`, `star-schema`, `pgvector`

**Resume Line Item:**
> Built end-to-end e-commerce data platform ingesting from 3 sources (REST API, Kafka, CSV), transforming to star schema with SCD Type 2 dimensions, automated quality checks, and AI-powered product similarity search via pgvector -- orchestrated by Airflow, containerized with Docker Compose, tested with CI/CD.

**LinkedIn Post:**
Share the architecture diagram with a post explaining one interesting technical decision (e.g., "Why I chose SCD Type 2 for customers" or "How pgvector makes product similarity search fast"). Technical posts with visuals get engagement from hiring managers.

---

## Extension Ideas

Once the core capstone is working, here are ways to expand it and deepen your skills:

### Add More Data Sources
- **Webhook ingestion:** Build a FastAPI endpoint that receives real-time order notifications and writes to Kafka
- **Web scraping:** Add a competitor price scraper that runs daily and feeds into a `raw.competitor_prices` table
- **Third-party APIs:** Integrate a weather API and correlate sales with weather patterns

### Scale with Kubernetes
- Convert `docker-compose.yml` to Kubernetes manifests or Helm charts
- Deploy Airflow on Kubernetes using the KubernetesExecutor
- Add horizontal pod autoscaling for the FastAPI service

### Add Monitoring and Observability
- Add Prometheus metrics to the FastAPI service (request latency, error rates)
- Set up Grafana dashboards for pipeline health
- Implement structured logging with JSON output to a centralized log system
- Add OpenTelemetry tracing across the pipeline stages

### Enhance the AI Layer
- Add a RAG (Retrieval-Augmented Generation) endpoint that answers product questions using embeddings + an LLM
- Implement user-based collaborative filtering: "customers who bought X also bought Y"
- Build a recommendation API that combines vector similarity with purchase history

### Production Hardening
- Add Terraform configs for deploying to AWS (RDS, MSK, ECS)
- Implement blue-green deployments for the API layer
- Add data retention policies and automated cleanup of old raw data
- Build a data catalog with column-level documentation

---

## Interview Prep: How to Talk About This Project

When an interviewer asks "Tell me about a data engineering project you have built," this is what you walk them through. Here is how to structure your answer and what questions to expect.

### The 2-Minute Walkthrough

Follow this structure:

1. **Problem statement** (10 seconds): "I built an end-to-end analytics platform for an e-commerce company that needed to unify product, customer, and event data from three different sources."
2. **Architecture overview** (30 seconds): "Data flows from a REST API, Kafka stream, and CSV files through ingestion pipelines into a Postgres raw layer. Airflow orchestrates daily transformations into a star schema with SCD Type 2 customer dimensions. Quality checks gate every load. Product embeddings stored in pgvector power a similarity search API."
3. **Technical depth** (60 seconds): Pick ONE interesting challenge and go deep. For example: "The trickiest part was getting SCD Type 2 right for customers. When a customer moves cities, I expire the old dimension row and insert a new one, so historical orders still join to the address that was current when the order was placed."
4. **Impact / results** (20 seconds): "The platform processes 10,000 events daily, maintains 7 automated quality checks, and serves product similarity search with sub-100ms latency."

### Questions You Should Expect

**"Why did you choose Postgres over Snowflake/BigQuery?"**
"For a portfolio project, Postgres gives me full control and zero cloud costs. The concepts transfer directly -- star schemas, SCD, and quality checks work the same way. I chose pgvector specifically because it lets me show AI integration without a separate vector database."

**"How would you scale this?"**
"The Kafka consumer is the bottleneck -- I would add consumer group parallelism. For the warehouse, I would move to a columnar engine like DuckDB or Snowflake. The embeddings pipeline would benefit from batch processing with GPU acceleration. Airflow would move to KubernetesExecutor for per-task scaling."

**"What happens when the pipeline fails?"**
"Every stage is idempotent -- I can rerun safely because of ON CONFLICT clauses. Quality checks gate downstream processing, so bad data does not reach the analytics layer. Airflow retries failed tasks automatically. The quality.check_results table provides an audit trail of every check."

**"How do you handle schema changes?"**
"The SCD Type 2 pattern naturally handles additive changes. For breaking changes, I would version the raw tables (raw_v2.events) and run both versions in parallel during migration. The quality checks would catch any unexpected schema drift."

**"Walk me through the data model."**
"It is a classic Kimball star schema. Two fact tables at different grains: fact_orders for completed purchases (one row per line item) and fact_events for all user interactions. Three dimensions: products (SCD Type 1), customers (SCD Type 2 tracking city/state/segment changes), and a pre-populated time dimension. The foreign keys from facts to dimensions use surrogate keys, not natural keys."

---

## Deliverables Summary

When you are done, you should have:

1. **GitHub repository** -- public, with clean commit history
2. **Working Docker Compose stack** -- one command to run everything
3. **Architecture diagram** -- visual overview of the system
4. **README.md** -- comprehensive documentation
5. **(Optional) 5-minute video walkthrough** -- record yourself explaining the project
6. **(Optional) Blog post** -- write up your design decisions for LinkedIn

**This project IS your portfolio piece.** When an interviewer asks "tell me about a data engineering project you have built," this is what you walk them through. Make it clean, make it work, make it yours.

You have got this. Go build something awesome.

---

*End of Module 10 -- End of The Data Engineering Fast Track*
