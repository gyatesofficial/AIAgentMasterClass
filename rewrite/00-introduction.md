# Module 0: Welcome & Setup

## Who This Course Is For

If you've ever stared at a job posting for "Data Engineer" and wondered whether you're ready, this course is for you. We built it for three kinds of people, and if you see yourself in any of them, you're in the right place.

**The analyst leveling up.** You know SQL. You can build dashboards in Tableau or Looker. You've probably written some Python scripts to clean data. But you've hit a ceiling. You want to build the pipelines that *feed* those dashboards -- the infrastructure that makes analytics possible at scale. You're tired of waiting for someone else to give you clean data and you want to be the person who builds the system that delivers it.

**The backend developer pivoting.** You can build APIs, deploy services, and write production code. You understand databases and have probably worked with Docker. But you've noticed that data engineering roles pay well, the problems are interesting, and the field is growing fast. What you need is the domain knowledge -- how data warehouses work, what orchestration means in practice, why "data quality" is a job unto itself. Your engineering skills will translate directly; you just need the data-specific concepts.

**The junior DE who needs depth.** Maybe you've already landed a data engineering role, or you're in an adjacent position where you touch pipelines. You can follow tutorials, but when something breaks at 2 AM, you're not confident you understand the system well enough to fix it. You need a mental model of how all the pieces fit together -- not just how to use Airflow, but *why* Airflow exists and what problem it solved that cron jobs couldn't.

No matter which camp you fall into, we assume you have basic Python skills, some SQL knowledge, and familiarity with the command line. That's it. Everything else, we'll build from the ground up.

---

## The 2026 Data Engineering Landscape

Before we touch a single tool, let's zoom out. What does a modern data engineering system actually look like? When an interviewer asks you to "describe the modern data stack," or when your manager asks you to architect a data platform from scratch, this is the mental model you need.

Every data platform in production today -- whether it's at a three-person startup or at Netflix -- follows the same fundamental flow:

```
Sources --> Ingestion --> Storage --> Processing --> Orchestration --> Quality --> Serving
```

Let's walk through each stage, because understanding this pipeline end-to-end is the single most important thing you can learn in this course.

### Sources: Where Data Comes From

Data doesn't appear out of thin air. It comes from somewhere, and understanding the "somewhere" matters more than most people realize.

**Transactional databases** are the most common source. Your company's PostgreSQL or MySQL database backing the web application -- the one that stores users, orders, products, payments. This is typically the first data source any DE connects to. At your first job, someone will say, "We need analytics on our orders table," and you'll need to figure out how to get that data out without killing the production database.

**APIs and SaaS tools** are the second major category. Stripe for payments, Salesforce for CRM, Google Analytics for web traffic, Shopify for e-commerce. Every business runs on dozens of SaaS tools, and each one has data locked inside it that the business needs for reporting. You'll spend a surprising amount of your career writing API extractors or configuring tools that pull data from these sources.

**Event streams** come from user behavior -- clicks, page views, add-to-cart events, search queries. These arrive in real time, often at massive volume (think millions of events per hour for a mid-size e-commerce site), and they're the foundation of real-time analytics and personalization.

**Files and flat data** still matter more than you'd think. CSVs from partners, Excel files from finance teams, JSON dumps from third-party vendors. A huge part of real-world data engineering is dealing with messy, inconsistent file-based data that arrives on unpredictable schedules.

### Ingestion: Getting Data In

Ingestion is the process of moving data from sources into your data platform. This sounds simple -- and conceptually it is -- but it's where a shocking number of pipelines break.

The two fundamental patterns are **batch** and **streaming**. Batch ingestion runs on a schedule: every hour, every day, pull the latest data. Streaming ingestion is continuous: as events happen, they flow into your platform in near-real-time. Most companies use both. Your order history might be batch-ingested nightly, while clickstream data flows in continuously via Kafka.

The key challenge in ingestion is **change data capture** (CDC) -- figuring out what changed since your last pull. If you have a table with 100 million rows and 500 changed today, you don't want to re-copy all 100 million. You want to capture just the 500 changes. Tools like Debezium, Fivetran, and Airbyte exist specifically to solve this problem, and understanding CDC will come up in virtually every DE interview.

### Storage: Where Data Lives

Once data is ingested, it needs to live somewhere. The choice of storage system is one of the most consequential architectural decisions you'll make, because it affects everything downstream.

**Data warehouses** (Snowflake, BigQuery, Redshift) are optimized for analytical queries -- the kind of SQL that aggregates millions of rows across joins. They're columnar, meaning they store data by column rather than by row, which makes aggregations blazingly fast.

**Data lakes** (S3, GCS, ADLS) store raw data in its original format -- Parquet files, JSON, CSVs, images, whatever. They're cheap, scalable, and flexible. The trade-off is that they don't have a query engine built in; you need to bring your own (Spark, DuckDB, Trino).

**Lakehouses** (Delta Lake, Apache Iceberg) are the modern hybrid: lake-like storage with warehouse-like features (ACID transactions, schema enforcement, time travel). In 2026, this is where the industry is headed, and we'll cover it in depth in Modules 6-7.

**Operational databases** (PostgreSQL, MySQL) store the transactional data your application uses. As a DE, you'll read from these but rarely write to them. Your job is to get data *out* of the operational database and into the analytical layer without impacting production performance.

### Processing: Transforming Data

Raw data is almost never in the shape your business needs. Orders might be in one table, customers in another, products in a third, and the business wants a single report that joins all three, calculates revenue by category, and filters to the last 90 days.

**Batch processing** (Spark, dbt, pandas, Polars, DuckDB) handles transformations that run on a schedule. "Every morning at 6 AM, rebuild the revenue dashboard." This is the bread and butter of most DE work.

**Stream processing** (Kafka Streams, Flink, Spark Streaming) handles transformations that must happen in real time. "When a user places an order, update the inventory count and trigger a shipping notification within 5 seconds." This is more complex and less common, but increasingly important.

At your first DE job, you'll almost certainly start with batch processing. A senior engineer will ask you to write a transformation in SQL or Python that takes raw data and produces a clean, aggregated table for the analytics team. This is where you prove your value early.

### Orchestration: Making It All Run

Orchestration is the layer that ties everything together. It answers the question: "In what order do things run, and what happens when something fails?"

Apache Airflow is the dominant orchestration tool in 2026, and it's what we'll use in this course. Airflow lets you define DAGs (Directed Acyclic Graphs) -- workflows where each step depends on the completion of previous steps. "First, extract data from Postgres. Then, load it into the warehouse. Then, run the dbt transformations. Then, update the dashboard. If any step fails, alert the on-call engineer."

Other tools exist (Dagster, Prefect, Mage), and each has trade-offs we'll discuss. But Airflow has the largest community, the most job postings, and the deepest integration ecosystem. When you learn Airflow, you learn the concepts that transfer to any orchestrator.

### Quality: Trusting Your Data

Data quality is the difference between a data platform that people trust and one they ignore. If your revenue dashboard shows $0 on a Monday morning because a pipeline silently failed, the business loses trust in the entire data team. Rebuilding that trust takes months.

Data quality tools (dbt tests, Great Expectations, Soda, Monte Carlo) let you define expectations about your data and get alerted when reality doesn't match. "This table should have between 10,000 and 100,000 rows. Revenue should never be negative. Every order should have a valid customer ID." These checks are the safety net that catches problems before they reach stakeholders.

### Serving: Delivering Value

All of the above exists to serve one purpose: getting the right data to the right people in the right format at the right time. Serving is the final mile.

**BI dashboards** (Tableau, Looker, Metabase, Power BI) are the most common serving layer. Analysts and business users query pre-built dashboards or write ad-hoc SQL against the warehouse.

**Reverse ETL** pushes data back into operational tools. "Take the customer lifetime value we calculated in the warehouse and push it back into Salesforce so the sales team can see it." Tools like Census and Hightouch specialize in this.

**ML features** serve processed data to machine learning models. "Every time a user loads the home page, fetch their real-time engagement score from the feature store so the recommendation model can personalize what they see."

**APIs** expose data to applications. "The mobile app needs to show the user's order history, pulled from the data warehouse."

> **Key Takeaway:** Every data engineering role you'll ever have exists somewhere in this pipeline. Understanding the full picture -- Sources through Serving -- is what separates a junior DE who can follow instructions from a senior DE who can architect solutions.

---

## Career Paths: What Data Engineering Roles Actually Look Like

Let's talk about what you're actually signing up for. Data engineering roles vary dramatically depending on the size and stage of the company.

### Startup DE (Seed to Series B, 1-3 DEs)

At a startup, you *are* the data team. You'll set up the entire data stack from scratch -- choose the warehouse, configure ingestion, write the first pipelines, build the first dashboards. The upside is enormous learning: you'll touch every part of the stack in your first month. The downside is that there's no one to learn from, no code review, and no on-call rotation -- it's just you.

**Typical salary range:** $120k-$180k base + equity (equity can be worth a lot or nothing)

**What your day looks like:** Monday you're debugging a broken Fivetran connector. Tuesday you're writing a dbt model for the sales team. Wednesday you're setting up Airflow. Thursday the CEO needs a one-off analysis. Friday you're figuring out why Snowflake costs went up 300%.

**Skills that matter most:** Breadth over depth. SQL fluency, basic Python, one cloud platform (AWS or GCP), comfort with ambiguity.

### Mid-Size Company DE (Series C+, 5-20 DEs)

This is where many DEs find their sweet spot. The data platform exists but needs to scale and mature. There's a team to collaborate with, established processes, and enough complexity to be intellectually challenging without the chaos of a startup.

**Typical salary range:** $150k-$250k total compensation

**What your day looks like:** You own a specific domain (payments pipeline, user analytics, ML feature engineering). You write code, review PRs, participate in on-call rotations, and work with stakeholders to understand their data needs. There are sprint planning meetings and architecture discussions.

**Skills that matter most:** Deep expertise in 2-3 areas (e.g., Spark + Airflow + dbt), ability to design and own systems end-to-end, strong communication with non-technical stakeholders.

### Big Tech DE (FAANG/MANGA, 50+ DEs)

Big tech data engineering is a different world. The scale is enormous (petabytes, millions of events per second), the tooling is often internal (you might use Google's proprietary orchestrator instead of Airflow), and the role is more specialized.

**Typical salary range:** $200k-$350k+ total compensation (base + bonus + RSUs)

**What your day looks like:** You own a specific pipeline or set of pipelines. You spend significant time on system design, code review, and cross-team coordination. You might not write a SQL query for weeks because you're designing the infrastructure that runs SQL queries for 500 other people.

**Skills that matter most:** Distributed systems knowledge, ability to work at massive scale, system design interview skills, comfort with internal tools and proprietary systems.

### The Interview Landscape

Data engineering interviews in 2026 typically involve:

1. **SQL** -- Always. Often medium-to-hard LeetCode-style problems involving window functions, CTEs, and self-joins.
2. **Python coding** -- Data manipulation, API interaction, basic algorithms.
3. **System design** -- "Design a real-time analytics pipeline for an e-commerce platform." This is where this course pays for itself.
4. **Domain knowledge** -- Questions about data modeling, warehouse design, pipeline architecture, and data quality.
5. **Behavioral** -- "Tell me about a time a pipeline broke in production and how you fixed it."

The system design round is where most candidates fail and where the salary negotiation leverage lives. Companies pay a premium for engineers who can think architecturally.

---

## The Course Project: Real-Time E-Commerce Analytics Platform

Theory without practice is just trivia. Throughout this course, you'll build a complete data platform for a fictional e-commerce company called **ShopFast**. This isn't a toy project -- it's designed to mirror what you'd actually build at a Series B e-commerce startup.

### The Business Context

ShopFast is a mid-size online retailer. The dataset you'll work with includes:

- **~1 million orders** spanning two years
- **~50,000 customers** with demographic and behavioral data
- **~10,000 products** across multiple categories

The business needs answers to questions like:
- What's our revenue by category, trending over the last 90 days?
- Which customer segments have the highest lifetime value?
- What products are frequently purchased together?
- What's our real-time order volume, and are we seeing anomalies?

### The Architecture You'll Build

By the end of this course, you'll have a working platform that includes:

```
Source (PostgreSQL)  -->  Ingestion (Python ETL + Kafka)
        |                         |
        v                         v
   Data Lake (MinIO/S3)    Stream Processing
        |                         |
        v                         v
   Data Warehouse         Real-Time Dashboard
   (PostgreSQL + dbt)     (Streaming Consumer)
        |
        v
   Data Quality (dbt tests + Soda)
        |
        v
   Orchestration (Airflow)
```

Each module adds a new layer to this architecture. By Module 10, you'll have a fully functioning, monitored, tested data platform running locally on your machine.

### Why These Specific Tools?

Every technology choice in this course is deliberate. Let me explain the reasoning, because "why this tool?" is one of the most important questions a data engineer can ask.

**PostgreSQL as the source and warehouse database.** Postgres is the most popular relational database in the data engineering world. It's open source, it's incredibly capable (supporting JSON, arrays, window functions, CTEs, materialized views), and it runs everywhere. We use it as both the source (simulating the production app database) and the analytical warehouse. In a real production setting, you'd likely use Snowflake or BigQuery for the warehouse, but Postgres lets us run everything locally without cloud costs. More importantly, everything you learn about writing analytical SQL in Postgres transfers directly to any warehouse.

Why Postgres over MySQL? Postgres has superior support for analytical workloads -- better window functions, richer data types, native JSON support, and more standards-compliant SQL. MySQL is great for web application backends, but Postgres is the DE's database.

**Apache Airflow for orchestration.** Airflow is the most widely adopted workflow orchestrator in data engineering. Created at Airbnb in 2014 and open-sourced in 2015, it defines the category. When you look at DE job postings, Airflow appears more than any other orchestration tool. Its DAG-based model (define workflows as Python code, with tasks that have dependencies) has become the standard mental model for pipeline orchestration.

The competitors are real -- Dagster has better local development, Prefect has a cleaner API, Mage has a better UI. But Airflow has the ecosystem: thousands of pre-built connectors, a massive community, managed offerings from every cloud provider (MWAA on AWS, Cloud Composer on GCP), and deep integration with virtually every data tool. Learning Airflow first gives you the strongest foundation.

**Apache Kafka for streaming.** Kafka is the industry standard for event streaming. Created at LinkedIn to handle their massive event volume (trillions of events per day), it's now used by virtually every company that does real-time data processing. Kafka's core concept -- a distributed, durable, append-only log -- is one of the most important ideas in modern data architecture.

In this course, we use Kafka to stream e-commerce events (orders, page views, inventory changes) in real time. The patterns you'll learn -- producers, consumers, topics, consumer groups -- apply to every streaming platform (Amazon Kinesis, Google Pub/Sub, Azure Event Hubs).

**MinIO as an S3 replacement.** Amazon S3 is the de facto standard for object storage and data lake storage. Every cloud provider has an S3-compatible service (GCS, ADLS). MinIO is an open-source, S3-compatible object store that runs locally. This means you can learn S3 patterns -- bucket creation, object upload/download, lifecycle policies -- without spending a cent on AWS.

When you get to your real job and someone says "put the raw files in S3," you'll already know the API and the mental model. The only difference is that the endpoint URL changes from `localhost:9000` to `s3.amazonaws.com`.

**Docker for environment reproducibility.** Here's a painful truth about data engineering: "it works on my machine" is the root cause of an embarrassing number of production incidents. Docker solves this by packaging your code *and its entire environment* (OS, libraries, configuration) into a container that runs identically everywhere.

In this course, Docker serves a practical purpose: with a single `docker compose up` command, you get PostgreSQL, Airflow, Kafka, and MinIO all running on your laptop, configured correctly and talking to each other. No manual installation, no version conflicts, no "I'm on Windows and the instructions are for Mac" problems.

At your first DE job, Docker will be one of the first things you encounter. Your pipelines will likely run in Docker containers, your local development environment will use Docker Compose, and your deployment pipeline will build and push Docker images. Getting comfortable with Docker now pays dividends immediately.

---

## Setting Up Your Development Environment

Let's get your hands dirty. By the end of this section, you'll have a fully functional data engineering environment running on your machine.

### Prerequisites

Before we start, make sure you have the following installed:

- **Python 3.11+** -- Check with `python --version` or `python3 --version`
- **Docker Desktop** -- [Download here](https://www.docker.com/products/docker-desktop/). Make sure Docker is running (you should see the whale icon in your system tray/menu bar). Allocate at least 4GB of RAM to Docker in Settings > Resources.
- **Git** -- Check with `git --version`
- **A code editor** -- VS Code is recommended, but anything works

### Step 1: Clone the Course Repository

```bash
git clone https://github.com/gyatesofficial/de-fast-track.git
cd de-fast-track
```

The repository is structured by module:

```
de-fast-track/
  docker-compose.yml          # The entire dev environment
  requirements.txt            # Python dependencies
  .env.example                # Environment variables template
  init-scripts/
    01_init.sql               # Database initialization
  modules/
    module-0/
      test_setup.py           # Verify your setup
    module-1/
      starter/                # Your starting point
      solution/               # Reference solution
    module-2/
      starter/
      solution/
    ...
```

Each module has a `starter/` directory with scaffolded code and a `solution/` directory with the complete implementation. Try to work through the starter files before looking at solutions.

### Step 2: Start the Infrastructure

This is the moment Docker earns its keep. One command brings up the entire stack:

```bash
docker compose up -d
```

This starts five services defined in the `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: dataeng
      POSTGRES_PASSWORD: dataeng
      POSTGRES_DB: warehouse
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataeng"]
      interval: 10s
      timeout: 5s
      retries: 5

  airflow-init:
    image: apache/airflow:2.9.0
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://dataeng:dataeng@postgres:5432/warehouse
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    entrypoint: >
      bash -c "
        airflow db init &&
        airflow users create
          --username admin
          --password admin
          --firstname Admin
          --lastname User
          --role Admin
          --email admin@example.com || true
      "

  airflow-webserver:
    image: apache/airflow:2.9.0
    depends_on:
      airflow-init:
        condition: service_completed_successfully
    ports:
      - "8080:8080"
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://dataeng:dataeng@postgres:5432/warehouse
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./modules:/opt/airflow/modules
    command: webserver

  airflow-scheduler:
    image: apache/airflow:2.9.0
    depends_on:
      airflow-init:
        condition: service_completed_successfully
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://dataeng:dataeng@postgres:5432/warehouse
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./modules:/opt/airflow/modules
    command: scheduler

  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    ports:
      - "2181:2181"

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
  postgres_data:
  minio_data:
```

Let's break down what's happening here, because understanding Docker Compose is a skill you'll use every single day as a DE:

**Postgres** is our database. The `healthcheck` block is important -- it tells Docker to ping the database every 10 seconds and only consider it "healthy" when `pg_isready` succeeds. Other services use `depends_on: postgres: condition: service_healthy` to wait for Postgres to actually be ready before starting. Without this, Airflow would try to connect before Postgres is accepting connections, and you'd get cryptic connection errors.

The `volumes` section mounts `./init-scripts` into the container at `/docker-entrypoint-initdb.d`. Postgres automatically executes any `.sql` files in that directory on first startup. Our `01_init.sql` creates the schemas we'll use throughout the course:

```sql
-- Initialize warehouse schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS quality;

GRANT ALL ON SCHEMA raw TO dataeng;
GRANT ALL ON SCHEMA staging TO dataeng;
GRANT ALL ON SCHEMA analytics TO dataeng;
GRANT ALL ON SCHEMA quality TO dataeng;
```

These four schemas follow a common data warehouse pattern you'll see at most companies:
- **raw** -- Data as it arrived from the source, untransformed. The "source of truth."
- **staging** -- Data that's been cleaned, typed, and deduplicated, but not yet modeled for analytics.
- **analytics** -- The final, business-ready tables that stakeholders query. Dimensional models, aggregations, metrics.
- **quality** -- Tables and logs related to data quality checks and monitoring.

**Airflow** has three services: `airflow-init` (runs once to initialize the database and create an admin user), `airflow-webserver` (the UI you'll access at `localhost:8080`), and `airflow-scheduler` (the process that actually triggers your DAGs on schedule). The `LocalExecutor` configuration means tasks run in the scheduler process itself -- simple for development, though production deployments typically use `CeleryExecutor` or `KubernetesExecutor` for parallel execution.

**Kafka** requires Zookeeper for cluster coordination (managing broker metadata, leader election, etc.). In production, newer versions of Kafka can run without Zookeeper using KRaft mode, but the Confluent images still use the traditional setup. The `KAFKA_ADVERTISED_LISTENERS` configuration is the most common source of Kafka connection issues -- it tells clients how to connect to the broker. We configure two listeners: one for internal Docker network communication (`kafka:29092`) and one for your local machine (`localhost:9092`).

**MinIO** provides an S3-compatible API on port 9000 and a web console on port 9001. The web console is genuinely useful -- you can browse buckets, upload files, and manage access policies through a clean UI.

### Step 3: Install Python Dependencies

Create a virtual environment and install the required packages:

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The `requirements.txt` includes the core libraries you'll use throughout the course:

```
# Core
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
pandas==2.2.2
polars==0.20.25
duckdb==0.10.3
pydantic==2.7.1
# Testing
pytest==8.2.1
pytest-cov==5.0.0
# API & HTTP
requests==2.32.3
httpx==0.27.0
# File formats
pyarrow==16.1.0
fastparquet==2024.5.0
# Utilities
python-dotenv==1.0.1
rich==13.7.1
```

A few things worth noting about these choices:

- **psycopg2-binary** is the PostgreSQL adapter. The `-binary` variant includes pre-compiled C extensions so you don't need `libpq-dev` installed. In production, you'd use `psycopg2` (non-binary) for better performance, but binary is simpler for development.
- **pandas and Polars** are both included intentionally. Pandas is the incumbent -- you'll encounter it at every company, in every legacy codebase. Polars is the modern alternative, significantly faster for large datasets and with a more expressive API. We'll use both so you can compare.
- **DuckDB** is an embedded analytical database -- think "SQLite for analytics." It can query Parquet files, CSV files, and pandas DataFrames directly using SQL. It's become incredibly popular for local data exploration and is a tool you should have in your toolkit.
- **PyArrow** is the Python implementation of Apache Arrow, a columnar memory format. It's the bridge between file formats (Parquet), compute engines (Spark, DuckDB), and Python (pandas, Polars). You'll encounter Arrow everywhere in modern data engineering.
- **Pydantic** provides data validation using Python type hints. We'll use it to define schemas for our data models, ensuring that data conforms to expected shapes before we process it.

### Step 4: Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

The defaults work out of the box with our Docker Compose setup:

```
DB_HOST=localhost
DB_PORT=5432
DB_USER=dataeng
DB_PASSWORD=dataeng
DB_NAME=warehouse
API_BASE_URL=http://localhost:5000
API_KEY=dev-key-change-me
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=raw-data
LOG_LEVEL=INFO
AIRFLOW_UID=50000
```

A note on `AIRFLOW_UID`: this sets the user ID inside the Airflow container. On Linux, this should match your host user ID (run `id -u` to check). On Mac and Windows, `50000` works fine. Getting this wrong causes file permission issues where Airflow can't read your DAG files -- a common stumbling block.

### Step 5: Verify Everything Works

Now the moment of truth. Run the verification script:

```bash
python modules/module-0/test_setup.py
```

Here's what the script does:

```python
"""Module 0: Environment Verification Script
Run this to verify your development environment is set up correctly.
"""
import psycopg2
import pandas as pd
import polars as pl
import duckdb
import pyarrow
from pydantic import BaseModel

print(f"pandas:  {pd.__version__}")
print(f"polars:  {pl.__version__}")
print(f"duckdb:  {duckdb.__version__}")
print(f"pyarrow: {pyarrow.__version__}")

conn = psycopg2.connect(
    host="localhost",
    database="warehouse",
    user="dataeng",
    password="dataeng"
)
cur = conn.cursor()
cur.execute("SELECT version();")
print(f"PostgreSQL: {cur.fetchone()[0]}")
conn.close()

print("\n✅ All good! You're ready for the course.")
```

If everything is set up correctly, you'll see version numbers for each library and a successful PostgreSQL connection. If you see errors, here are the most common fixes:

**"connection refused" from PostgreSQL** -- Docker isn't running, or Postgres hasn't finished starting. Run `docker compose ps` to check service status. Wait 30 seconds and try again.

**Import errors for Python packages** -- You're not in the virtual environment. Run `source .venv/bin/activate` and try again.

**Docker Compose errors** -- Make sure Docker Desktop is running and you've allocated enough RAM (4GB minimum). On Mac, check Docker Desktop > Settings > Resources.

### Step 6: Verify Airflow and MinIO

Open your browser and check the UIs:

- **Airflow**: Navigate to `http://localhost:8080`. Log in with username `admin`, password `admin`. You should see an empty DAGs list -- we'll populate it in Module 4.
- **MinIO**: Navigate to `http://localhost:9001`. Log in with `minioadmin` / `minioadmin`. You should see the MinIO console with no buckets yet.

If both UIs load, your environment is fully operational.

---

## How This Course Is Structured

Each module in this course follows a consistent pattern:

1. **Concept introduction** -- We explain the *what* and the *why* before we touch any code. Understanding the problem a tool solves is more important than memorizing its syntax.
2. **Guided walkthrough** -- We build something together, with detailed explanations at each step.
3. **Hands-on exercise** -- You take the `starter/` code and complete it. This is where the real learning happens.
4. **Solution review** -- Compare your approach to the `solution/` directory. There's often more than one right answer; the goal is to understand the trade-offs.

Here's the module map:

| Module | Topic | What You'll Build |
|--------|-------|-------------------|
| 0 | Welcome & Setup | Dev environment |
| 1 | Data Modeling Foundations | Dimensional model for ShopFast |
| 2 | Incremental Loading | SCD2 dimensions + incremental facts |
| 3 | Python ETL Pipelines | Production-grade extraction pipeline |
| 4 | Orchestration with Airflow | DAGs for the ShopFast pipeline |
| 5 | Modern File Formats & DataFrames | Parquet, Polars, DuckDB exploration |
| 6 | Real-Time Streaming with Kafka | Event producer + consumer |
| 7 | Data Quality & Contracts | dbt tests, Soda checks, schema contracts |
| 8 | Infrastructure & Deployment | Terraform, Docker, CI/CD |
| 9 | Semantic Search & AI Pipelines | Embeddings + vector search |
| 10 | Monitoring & Observability | Pipeline metrics + alerting |

**The best way to learn:** Don't just read. Type the code. Break it. Fix it. Change parameters and see what happens. Add a print statement to understand what a variable contains. The gap between "I understand this conceptually" and "I can build this" is only bridged by doing.

---

## A Note from Your Instructor

Data engineering is one of the most rewarding careers in tech. You build the infrastructure that powers every data-driven decision a company makes. When the CEO quotes a revenue number in an all-hands meeting, that number came from a pipeline you built. When the ML team deploys a model that increases conversion by 3%, it was trained on data you delivered. When an analyst discovers a trend that changes the company's strategy, they found it in a table you created.

The work is often invisible. Nobody toasts the data engineer at the company party. But when the data is wrong, or late, or missing -- everyone notices. There's a quiet satisfaction in building systems that just work, day after day, processing millions of records while you sleep.

This course will give you the skills to build those systems. Let's get started.

---

## What Comes Next

In Module 1, we dive into data modeling -- the art and science of structuring data for analytical workloads. You'll learn about dimensional modeling (star schemas, fact tables, dimension tables), why it matters, and you'll build your first dimensional model for the ShopFast dataset. If SQL is your strongest skill, this is where you'll shine. If it's not, this is where you'll build it.

Let's go.
