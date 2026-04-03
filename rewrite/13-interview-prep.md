# Module 13: Interview Preparation & Portfolio Projects

## The Interview Mindset

After conducting 150+ system design interviews at three companies, I can tell you: the difference between candidates who get offers and those who don't is rarely technical knowledge. Most senior candidates know Kafka, know SQL, know the CAP theorem. The difference is **how they think and communicate**.

**Wrong mindset**: "I need to design the perfect system and impress the interviewer with cutting-edge technology."

**Right mindset**: "I need to understand the business problem, solve it effectively, and communicate my reasoning clearly."

The best candidates treat the interview as a **collaborative design session** — like a meeting with a colleague to whiteboard an architecture. They ask clarifying questions, state assumptions explicitly, explain trade-offs, and invite the interviewer into the decision-making process.

> **Key Takeaway:** System design interviews test three things: (1) Can you break down ambiguous problems? (2) Can you design reasonable solutions? (3) Can you communicate your thinking? Technical depth is table stakes — communication and structured thinking are the differentiators.

---

## The 45-Minute Structure

Most system design interviews are 45 minutes. Here's how to allocate that time:

### Minutes 1-8: Requirements and Scale Estimation

This phase is critical and most candidates rush through it. Slow down. Ask questions. The interviewer deliberately leaves the problem ambiguous to see if you'll clarify before building.

**Sample dialogue:**

> **You**: "Before I start designing, I'd like to understand the requirements. When you say 'design a data warehouse for analytics,' who are the primary users?"
>
> **Interviewer**: "We have about 20 analysts, a few executives, and a data science team."
>
> **You**: "Got it. And what's the data volume? Are we talking gigabytes or petabytes?"
>
> **Interviewer**: "We process about 50,000 orders per day, so maybe a few terabytes total."
>
> **You**: "Okay, and for freshness — do stakeholders need real-time data, or is daily sufficient?"
>
> **Interviewer**: "Daily is fine for most use cases, but the fraud team wants near-real-time."

In 5 minutes, you've established: user count, data volume, freshness requirements, and identified a specialized need (fraud team). This shapes every subsequent decision.

**Always estimate scale**: "50,000 orders/day × 500 bytes ≈ 25 MB/day raw. Over 5 years, that's ~45 GB. With dimension tables, transformations, and 3x overhead: ~150 GB total. This is well within a single PostgreSQL instance, but a cloud warehouse gives us elasticity and separation of concerns."

### Minutes 8-20: High-Level Architecture

Draw the major components and data flow. Keep it simple — 5-7 boxes connected by arrows. For each component, state the technology choice and a one-sentence justification.

```
[Data Sources] → [Ingestion (Airbyte)] → [Raw Storage (S3)]
         → [Transform (dbt on Snowflake)] → [Analytics Tables]
                                                    → [BI (Tableau)]
                                                    → [ML (Python)]
```

**What to include**: Data sources, ingestion method, storage, processing/transformation, serving layer, key data flows.

**What NOT to include yet**: Internal component details, specific configurations, error handling. Those come in the deep dive.

### Minutes 20-35: Component Deep Dive

The interviewer will steer you toward the most interesting components. Pick 1-2 and go deep: data models, API design, algorithms, scaling strategies.

This is where your technical knowledge shows. If you're asked to deep-dive on the data model, walk through your star schema design — fact tables, dimension tables, how SCD Type 2 handles customer changes. If you're asked about the ingestion pipeline, discuss exactly-once delivery, schema evolution, and error handling.

### Minutes 35-40: Scale and Optimize

Identify bottlenecks in your design and explain how to address them:

- "The transformation step is the bottleneck at 10x scale. I'd switch from a single dbt run to incremental models and parallelize independent transformations."
- "At 100x the current query load, I'd add materialized views for common dashboard queries and implement a caching layer."

### Minutes 40-45: Trade-offs and Alternatives

End by acknowledging what you sacrificed and why:

- "I chose Snowflake over BigQuery because the team is multi-cloud, but BigQuery would be cheaper for sporadic query patterns."
- "I went with batch processing for simplicity, but if the fraud team's real-time requirement grows, I'd add a Kafka + Flink pipeline alongside the batch path."

---

## Advanced Interview Techniques

### Technique 1: Assumption Surfacing

Vocalize your assumptions instead of making them silently:

> "I'm assuming this is a read-heavy system — maybe 100:1 read-to-write ratio. Does that match your expectations?"

This shows structured thinking and gives the interviewer a chance to redirect you. Silent assumptions lead to wrong designs; vocalized assumptions lead to useful corrections.

### Technique 2: Iterative Design

Start with the simplest architecture that works, then add complexity:

> "For the initial design with 50K orders/day, I'd start with PostgreSQL and a daily cron job running Python scripts. As we scale to 500K orders/day, I'd move to Airflow for orchestration and Snowflake for the warehouse. At 5M orders/day, I'd add streaming with Kafka for the real-time use cases."

This demonstrates that you understand when complexity is justified — which is far more impressive than jumping straight to a distributed architecture for a small-scale problem.

### Technique 3: Failure Mode Analysis

Identify critical failure scenarios and your mitigation:

| Failure Scenario | Impact | Mitigation | Recovery Time |
|-----------------|--------|------------|---------------|
| Primary database down | No new data ingestion | Read replicas + auto-failover | <5 minutes |
| ETL pipeline fails | Stale dashboard data | Retry logic + alerting, serve last-known-good | <30 minutes |
| Data warehouse corruption | Wrong analytics | Point-in-time restore from immutable raw data | 4-8 hours |

> **Key Takeaway:** These techniques — assumption surfacing, iterative design, failure mode analysis — separate candidates who "know the technology" from candidates who "think like architects." Practice them until they're natural.

---

## Common Mistakes and How to Avoid Them

### Mistake 1: Jumping to Technology Too Quickly

**Bad**: "I'd use Kafka, Spark, and Snowflake."
**Good**: "The first question is whether we need real-time processing. Given that daily freshness is acceptable for most users, I'd start with a simpler batch architecture. For the fraud team's real-time needs, I'd add a focused streaming pipeline — Kafka for ingestion, Flink for processing — rather than making the entire system real-time."

### Mistake 2: Over-Engineering

**Bad**: 15 microservices, event sourcing, CQRS, and a custom ML platform for a system that processes 1 GB/day for 10 analysts.

**Good**: "At this scale — 1 GB/day, 10 users — the architecture should be simple: Airbyte for ingestion, dbt for transformation, Snowflake for warehousing, Tableau for visualization. Total cost: ~$500/month. I'd invest complexity only where the business requires it."

### Mistake 3: Ignoring Business Context

**Bad**: Technically perfect system that costs 10x the budget or requires a team of 20 to operate when the company has 3 data engineers.

**Good**: "Given a 3-person team and a 6-month timeline, I'd choose managed services over self-hosted: BigQuery over self-managed Spark, Airbyte Cloud over custom connectors. The total cost is higher per unit, but the operational cost is dramatically lower."

### Mistake 4: Not Handling Ambiguity

**Bad**: Making assumptions without clarifying.

**Good**: "You mentioned 'real-time analytics' — could you clarify what that means here? Are we talking sub-second latency for fraud detection, or a dashboard that refreshes every few minutes? Those are very different architectures."

---

## Communication Frameworks

### The Three-Level Explanation

When explaining a design decision, adjust depth based on your audience:

- **Executive summary**: "I'm choosing Kafka because it's the most reliable way to handle our event volume without data loss."
- **Engineering peer**: "I'm choosing Kafka over RabbitMQ because we need message replay for reprocessing, topic-based routing for multiple consumers, and the throughput handles our 50K events/second peak."
- **Deep dive**: "I'd configure Kafka with 12 partitions per topic — matching our consumer parallelism — replication factor 3 for durability, and 7-day retention for reprocessing capability. We'd use Avro with Schema Registry for schema evolution."

In an interview, start with the executive summary and go deeper based on interviewer interest.

### The Assumption → Implication Pattern

Structure your reasoning as a chain:

> "Given that we have 10x more reads than writes (assumption) → we need to optimize our read path (implication) → so I'm choosing a denormalized data model with pre-computed aggregations (decision) → which gives us sub-second dashboard queries but requires more complex write logic and 2x storage (trade-offs)."

---

## Practice Questions with Solutions

### Question 1: Design a Data Warehouse for E-Commerce

**Setup**: E-commerce company. 1M customers, 50K orders/day, sources include PostgreSQL, Stripe, Google Analytics, Zendesk.

**Requirements phase**: 20 analysts, 5 executives, 10 marketers. Daily freshness. 7-year retention for compliance. $5K/month budget.

**Scale estimation**: 50K orders × 500 bytes = 25 MB/day raw. With all sources: ~700 MB/day. Over 7 years: ~1.8 TB. This is modest — a single cloud warehouse handles this easily.

**Architecture**: Sources → Airbyte (ingestion) → S3 raw layer → dbt (transform) → Snowflake (warehouse) → Tableau (dashboards). Airflow orchestrates everything.

**Deep dive on data model**: Star schema with `fact_orders` (one row per order line item, measures: quantity, revenue, discount, profit) joined to dimensions: `dim_customer` (SCD Type 2 for address changes), `dim_product` (category, brand, supplier), `dim_date` (fiscal calendar, holidays).

**Scaling strategy**: Incremental dbt models, materialized views for top 10 dashboard queries, Snowflake auto-suspend for cost control, resource monitors per team.

### Question 2: Design a Real-Time Fraud Detection System

**Setup**: Payment processor. 10K transactions/second, decisions in <100ms, <2% false positive rate.

**Architecture**: Transaction → Kafka (partitioned by user_id) → Flink (feature enrichment) → ML Ensemble (gRPC) → Decision Engine → Response.

**Latency budget**: Kafka (15ms) + Feature lookup from Redis (5ms) + ML inference (30ms) + Rules engine (10ms) + Network (15ms) = 75ms. Under budget with headroom.

**ML approach**: Four-model ensemble — gradient boosting (tabular features), neural network (complex interactions), graph neural network (fraud rings), anomaly detection (novel patterns). Weighted voting with dynamic weights.

**Key points to mention**: Feature store for training/serving consistency, model A/B testing with gradual rollout, graceful degradation (rules-only if ML fails), PCI DSS compliance, real-time model monitoring for drift.

### Question 3: Design a Content Recommendation System

**Setup**: Media platform. 10M users, 1M content items, real-time recommendations on homepage.

**Architecture**: User events (Kafka) → Feature pipeline (Spark) → Feature Store (Feast) → Training (weekly, MLflow) → Serving (FastAPI + Redis).

**Algorithm**: Collaborative filtering (users who watched X also watched Y) + content-based (similar genre/tags/duration) + popularity baseline. Multi-armed bandit to balance strategies.

**Key points to mention**: Cold start problem (new users: use popularity and demographics; new content: use content features and boost exploration), diversity in recommendations (MMR), A/B testing framework, latency budget (<50ms), offline evaluation (precision@k, recall@k, NDCG) vs online evaluation (click-through rate, watch time, retention).

---

## Portfolio Projects

Build 2-3 projects that demonstrate system design thinking, not just coding ability. Below are detailed blueprints for each — follow them step by step, and you'll have portfolio pieces that stand out in any interview.

### Project 1: Production-Grade Data Pipeline (3-4 weeks)

**What it demonstrates**: orchestration, data modeling, quality engineering, operational maturity.

**The scenario**: You're building a pipeline that ingests public weather data and NYC taxi trip records, transforms them into an analytics-ready star schema, and serves a dashboard showing how weather affects taxi demand. This mirrors what real data teams build daily.

#### Week 1: Set Up Infrastructure and Ingestion

**Step 1 — Create your project structure:**

```
weather-taxi-pipeline/
├── dags/                    # Airflow DAG definitions
│   └── weather_taxi_dag.py
├── dbt/                     # dbt transformation project
│   ├── models/
│   │   ├── staging/         # Clean raw data
│   │   ├── intermediate/    # Join and enrich
│   │   └── marts/           # Final star schema
│   ├── tests/               # Data quality tests
│   └── dbt_project.yml
├── scripts/
│   └── extract.py           # Extraction scripts
├── docker-compose.yml       # Local Airflow + Postgres
├── requirements.txt
└── README.md
```

**Step 2 — Stand up local Airflow with Docker Compose.** Use the official Apache Airflow Docker Compose file as a starting point. You need three services: the Airflow webserver, the scheduler, and a Postgres database that doubles as your local warehouse.

```yaml
# docker-compose.yml (simplified — extend the official Airflow compose)
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: warehouse
      POSTGRES_USER: pipeline
      POSTGRES_PASSWORD: pipeline
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

**Step 3 — Write extraction scripts.** Pull data from two free public APIs:

- **Weather**: NOAA Climate Data Online (free API key) or Open-Meteo (no key required). Pull daily temperature, precipitation, and wind speed for New York City.
- **Taxi trips**: NYC Taxi & Limousine Commission publishes Parquet files on their website. Download one month of yellow taxi trip data (~3M rows).

```python
# scripts/extract.py
import requests
import pandas as pd
from pathlib import Path

def extract_weather(start_date: str, end_date: str) -> pd.DataFrame:
    """Pull daily weather from Open-Meteo (free, no API key).

    Returns a DataFrame with columns: date, temperature_max,
    temperature_min, precipitation, wind_speed_max.
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "America/New_York",
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()["daily"]
    return pd.DataFrame(data)

def extract_taxi_trips(year: int, month: int) -> pd.DataFrame:
    """Download NYC yellow taxi trip data (Parquet format).

    The TLC publishes monthly files. Each file is ~100MB
    with 2-3 million rows.
    """
    url = (
        f"https://d37ci6vzurychx.cloudfront.net/trip-data/"
        f"yellow_tripdata_{year}-{month:02d}.parquet"
    )
    return pd.read_parquet(url)
```

**Step 4 — Load raw data into Postgres.** Write a simple loader that creates `raw_weather` and `raw_taxi_trips` tables. Use `pandas.to_sql()` for simplicity, or `COPY` for performance. Don't transform anything yet — raw means raw.

#### Week 2: Build the Transformation Layer with dbt

**Step 5 — Initialize dbt and connect to Postgres:**

```bash
cd dbt/
dbt init weather_taxi --adapter postgres
```

Configure `profiles.yml` to point at your local Postgres.

**Step 6 — Build staging models.** These clean raw data without changing its grain (one row in = one row out):

```sql
-- dbt/models/staging/stg_weather.sql
-- Clean and rename columns from the raw weather extract.
-- One row per day for NYC.

SELECT
    time::date                           AS weather_date,
    temperature_2m_max                   AS temp_high_f,
    temperature_2m_min                   AS temp_low_f,
    precipitation_sum                    AS precipitation_inches,
    wind_speed_10m_max                   AS wind_speed_max_mph,
    CASE
        WHEN precipitation_sum > 0.5 THEN 'rainy'
        WHEN temperature_2m_max < 32 THEN 'freezing'
        WHEN wind_speed_10m_max > 25 THEN 'windy'
        ELSE 'clear'
    END                                  AS weather_category
FROM {{ source('raw', 'raw_weather') }}
```

```sql
-- dbt/models/staging/stg_taxi_trips.sql
-- Clean taxi trips: filter invalid records, normalize columns.
-- Drop rows with null pickup times or impossible fares.

SELECT
    tpep_pickup_datetime::date           AS trip_date,
    tpep_pickup_datetime                 AS pickup_at,
    tpep_dropoff_datetime                AS dropoff_at,
    passenger_count,
    trip_distance,
    fare_amount,
    tip_amount,
    total_amount,
    PULocationID                         AS pickup_location_id,
    DOLocationID                         AS dropoff_location_id
FROM {{ source('raw', 'raw_taxi_trips') }}
WHERE tpep_pickup_datetime IS NOT NULL
  AND fare_amount > 0
  AND trip_distance > 0
```

**Step 7 — Build the star schema in the marts layer:**

```sql
-- dbt/models/marts/fact_daily_trips.sql
-- Fact table: one row per day with aggregated trip metrics
-- joined to weather conditions. This is the table dashboards query.

SELECT
    t.trip_date,
    w.weather_category,
    w.temp_high_f,
    w.precipitation_inches,
    COUNT(*)                             AS total_trips,
    AVG(t.trip_distance)                 AS avg_distance,
    AVG(t.fare_amount)                   AS avg_fare,
    SUM(t.total_amount)                  AS total_revenue,
    AVG(t.tip_amount)                    AS avg_tip
FROM {{ ref('stg_taxi_trips') }} t
LEFT JOIN {{ ref('stg_weather') }} w
    ON t.trip_date = w.weather_date
GROUP BY 1, 2, 3, 4
```

**Step 8 — Add dbt tests for data quality:**

```yaml
# dbt/models/marts/schema.yml
models:
  - name: fact_daily_trips
    description: "Daily taxi trip aggregates joined with weather"
    columns:
      - name: trip_date
        tests:
          - not_null
          - unique
      - name: total_trips
        tests:
          - not_null
      - name: avg_fare
        tests:
          - not_null
          # Fares should be reasonable
          - dbt_utils.accepted_range:
              min_value: 5
              max_value: 200
```

#### Week 3: Orchestrate with Airflow and Add Monitoring

**Step 9 — Write the Airflow DAG that ties everything together:**

```python
# dags/weather_taxi_dag.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "weather_taxi_pipeline",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["portfolio", "weather", "taxi"],
) as dag:

    extract_weather = PythonOperator(
        task_id="extract_weather",
        python_callable=extract_weather_task,  # Wraps extract.py
    )

    extract_taxi = PythonOperator(
        task_id="extract_taxi",
        python_callable=extract_taxi_task,
    )

    # dbt run handles staging → intermediate → marts
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="cd /opt/airflow/dbt && dbt run --profiles-dir .",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/dbt && dbt test --profiles-dir .",
    )

    # Extract in parallel, then transform, then test
    [extract_weather, extract_taxi] >> dbt_run >> dbt_test
```

**Step 10 — Add monitoring and alerting.** Configure Airflow email alerts on failure. Add a Slack webhook notification for pipeline completion. Log row counts at each stage so you can spot anomalies.

#### Week 4: Polish and Document

**Step 11 — Build a simple dashboard.** Use Streamlit (Python, quick to build) or Metabase (free, SQL-based). Show: trips per day colored by weather category, average fare by weather type, a heatmap of rainy days vs. trip volume.

**Step 12 — Write your design document** (see the Documentation section below).

**Step 13 — Deploy to the cloud (optional but impressive).** Push the pipeline to Astronomer (free trial), GCP Cloud Composer, or AWS MWAA. Use BigQuery or Snowflake (free trial) instead of Postgres. This shows you can operate in a real cloud environment.

---

### Project 2: Real-Time Analytics Platform (4-6 weeks)

**What it demonstrates**: streaming architecture, multi-backend design, real-time processing.

**The scenario**: You're building a platform that ingests live Reddit posts from specific subreddits, analyzes sentiment in real time, and serves a live dashboard showing trending topics, sentiment shifts, and volume spikes. This mirrors what companies like Spotify and Twitter build for real-time content analytics.

#### Week 1: Set Up Kafka and Data Ingestion

**Step 1 — Stand up Kafka locally with Docker Compose:**

```yaml
# docker-compose.yml
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  redis:
    image: redis:7
    ports:
      - "6379:6379"
```

**Step 2 — Build a Reddit producer.** Use the `praw` library (Reddit's official Python wrapper) to stream new posts and comments from chosen subreddits:

```python
# producer/reddit_producer.py
import praw
import json
from kafka import KafkaProducer
from datetime import datetime

# Reddit API credentials (free — create an app at reddit.com/prefs/apps)
reddit = praw.Reddit(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    user_agent="streaming-analytics:v1.0",
)

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

# Stream comments from multiple subreddits in real time
subreddits = reddit.subreddit("technology+programming+datascience")
for comment in subreddits.stream.comments(skip_existing=True):
    event = {
        "id": comment.id,
        "subreddit": comment.subreddit.display_name,
        "author": str(comment.author),
        "body": comment.body[:1000],  # Truncate long comments
        "created_utc": comment.created_utc,
        "score": comment.score,
        "ingested_at": datetime.utcnow().isoformat(),
    }
    producer.send("reddit-comments", value=event)
```

**Step 3 — Verify the topic is receiving data.** Use the Kafka console consumer to see messages flowing: `kafka-console-consumer --bootstrap-server localhost:9092 --topic reddit-comments --from-beginning`

#### Week 2: Build the Stream Processor

**Step 4 — Build a Faust stream processor** (Python-native stream processing, simpler than Flink for a portfolio project):

```python
# processor/stream_processor.py
import faust
from textblob import TextBlob
from datetime import datetime

app = faust.App(
    "reddit-analytics",
    broker="kafka://localhost:9092",
    store="rocksdb://",  # Local state store for aggregations
)

# Input topic
comments_topic = app.topic("reddit-comments", value_type=bytes)

# Output topics
enriched_topic = app.topic("reddit-enriched", value_type=bytes)
alerts_topic = app.topic("reddit-alerts", value_type=bytes)

# Windowed table: track comment volume per subreddit (5-min windows)
volume_table = app.Table(
    "subreddit_volume",
    default=int,
).tumbling(300)  # 5-minute tumbling window

@app.agent(comments_topic)
async def process_comments(comments):
    """Enrich each comment with sentiment analysis and
    update the per-subreddit volume counter.

    If volume spikes above 2x the recent average,
    emit an alert to the alerts topic.
    """
    async for event in comments:
        comment = json.loads(event)

        # Sentiment analysis using TextBlob
        blob = TextBlob(comment["body"])
        sentiment = blob.sentiment

        enriched = {
            **comment,
            "sentiment_polarity": sentiment.polarity,   # -1.0 to 1.0
            "sentiment_subjectivity": sentiment.subjectivity,
            "sentiment_label": (
                "positive" if sentiment.polarity > 0.1
                else "negative" if sentiment.polarity < -0.1
                else "neutral"
            ),
            "word_count": len(comment["body"].split()),
            "processed_at": datetime.utcnow().isoformat(),
        }

        # Update volume counter
        subreddit = comment["subreddit"]
        volume_table[subreddit] += 1

        # Send enriched event downstream
        await enriched_topic.send(value=json.dumps(enriched).encode())
```

**Step 5 — If you want to use Spark Streaming instead** (more widely used in industry but heavier to set up), replace Faust with PySpark:

```python
# Alternative: Spark Structured Streaming
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, udf
from pyspark.sql.types import StringType, FloatType

spark = SparkSession.builder \
    .appName("reddit-analytics") \
    .getOrCreate()

# Read from Kafka
raw_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "reddit-comments") \
    .load()

# Parse JSON and add sentiment (via UDF)
@udf(returnType=FloatType())
def sentiment_score(text):
    from textblob import TextBlob
    return float(TextBlob(text).sentiment.polarity)

enriched = raw_stream \
    .select(from_json(col("value").cast("string"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("sentiment", sentiment_score(col("body")))

# Write to console for debugging, or to another Kafka topic
enriched.writeStream \
    .outputMode("append") \
    .format("console") \
    .start() \
    .awaitTermination()
```

#### Week 3: Multi-Backend Storage

**Step 6 — Write enriched data to three backends** (this is the key architectural decision that shows multi-backend thinking):

- **Redis** — for real-time aggregations (last 5 minutes of sentiment by subreddit). Dashboards read from Redis for instant response.
- **Elasticsearch** — for full-text search over comments. Powers a "search comments by keyword" feature.
- **S3 or local Parquet files** — for historical analysis. Write hourly Parquet partitions for batch analytics.

```python
# sinks/redis_sink.py
import redis
import json

r = redis.Redis(host="localhost", port=6379)

def write_to_redis(enriched_event: dict):
    """Update real-time aggregations in Redis.

    Stores: current 5-min average sentiment per subreddit,
    total comment count, and the last 100 comments.
    """
    subreddit = enriched_event["subreddit"]
    pipeline = r.pipeline()

    # Increment comment count
    pipeline.incr(f"count:{subreddit}")

    # Push to a capped list of recent comments
    pipeline.lpush(f"recent:{subreddit}", json.dumps(enriched_event))
    pipeline.ltrim(f"recent:{subreddit}", 0, 99)

    # Update running sentiment average (simplified)
    pipeline.lpush(f"sentiment:{subreddit}", enriched_event["sentiment_polarity"])
    pipeline.ltrim(f"sentiment:{subreddit}", 0, 299)  # Keep last 300

    pipeline.execute()
```

#### Weeks 4-5: Dashboard and Polish

**Step 7 — Build a live dashboard with Streamlit:**

```python
# dashboard/app.py
import streamlit as st
import redis
import json
import pandas as pd
import time

r = redis.Redis(host="localhost", port=6379)

st.title("Reddit Real-Time Sentiment Dashboard")

# Auto-refresh every 10 seconds
placeholder = st.empty()

while True:
    with placeholder.container():
        subreddits = ["technology", "programming", "datascience"]

        for sub in subreddits:
            count = int(r.get(f"count:{sub}") or 0)
            sentiments = r.lrange(f"sentiment:{sub}", 0, 299)
            if sentiments:
                avg_sentiment = sum(float(s) for s in sentiments) / len(sentiments)
            else:
                avg_sentiment = 0

            st.metric(
                label=f"r/{sub}",
                value=f"{count} comments",
                delta=f"Sentiment: {avg_sentiment:.2f}",
            )

        # Show recent comments
        st.subheader("Recent Comments")
        recent = r.lrange("recent:technology", 0, 9)
        for item in recent:
            comment = json.loads(item)
            emoji = "🟢" if comment["sentiment_polarity"] > 0.1 else "🔴" if comment["sentiment_polarity"] < -0.1 else "⚪"
            st.text(f"{emoji} [{comment['subreddit']}] {comment['body'][:120]}")

    time.sleep(10)
    st.rerun()
```

**Step 8 — Add a Grafana dashboard** showing Kafka consumer lag, processing latency, and throughput metrics. This proves you think about operational concerns, not just features.

**Step 9 — Write your design document** covering the architecture diagram, why you chose each storage backend, how you'd scale each component, and what breaks first under 100x load.

---

### Project 3: ML-Powered Churn Prediction System (3-4 weeks)

**What it demonstrates**: ML engineering, feature engineering, model deployment, monitoring, and the full lifecycle from training to serving.

**The scenario**: You're building a system that predicts which users of a SaaS product will churn in the next 30 days, serves those predictions via an API, and monitors model performance over time. This is one of the most common ML applications in industry.

#### Week 1: Data Preparation and Feature Engineering

**Step 1 — Get the data.** Use the Telco Customer Churn dataset from Kaggle (free, ~7K rows) or generate synthetic data that mimics SaaS usage patterns:

```python
# data/generate_synthetic.py
"""Generate synthetic SaaS user data for churn prediction.

Each row represents a user with their activity metrics
over the last 90 days and whether they churned.
"""
import pandas as pd
import numpy as np

np.random.seed(42)
n_users = 50_000

users = pd.DataFrame({
    "user_id": range(n_users),
    "signup_days_ago": np.random.randint(30, 730, n_users),
    "plan": np.random.choice(["free", "basic", "pro", "enterprise"],
                             n_users, p=[0.4, 0.3, 0.2, 0.1]),
    "logins_last_30d": np.random.poisson(12, n_users),
    "logins_last_7d": np.random.poisson(3, n_users),
    "features_used_last_30d": np.random.poisson(5, n_users),
    "support_tickets_last_90d": np.random.poisson(1, n_users),
    "api_calls_last_30d": np.random.poisson(50, n_users),
    "team_size": np.random.choice([1, 2, 5, 10, 25, 50], n_users,
                                  p=[0.3, 0.2, 0.2, 0.15, 0.1, 0.05]),
    "days_since_last_login": np.random.exponential(7, n_users).astype(int),
})

# Churn probability increases with inactivity, small teams, free plan
churn_score = (
    0.3 * (users["days_since_last_login"] > 14).astype(float)
    + 0.2 * (users["logins_last_30d"] < 5).astype(float)
    + 0.15 * (users["plan"] == "free").astype(float)
    + 0.1 * (users["team_size"] == 1).astype(float)
    + 0.1 * (users["support_tickets_last_90d"] > 3).astype(float)
    + np.random.normal(0, 0.15, n_users)
)
users["churned"] = (churn_score > 0.4).astype(int)

users.to_parquet("data/users.parquet", index=False)
print(f"Generated {n_users} users, churn rate: {users['churned'].mean():.1%}")
```

**Step 2 — Build a feature store with Feast:**

```python
# feature_store/feature_definitions.py
"""Define features in Feast so training and serving use
the exact same feature computation — eliminating
training/serving skew.
"""
from feast import Entity, Feature, FeatureView, FileSource
from feast.types import Float32, Int32, String
from datetime import timedelta

# Entity: the user we're predicting churn for
user = Entity(name="user_id", join_keys=["user_id"])

# Source: our Parquet file (in production, this would be a warehouse)
user_source = FileSource(
    path="data/users.parquet",
    timestamp_field="event_timestamp",
)

# Feature view: the set of features available for this entity
user_activity_fv = FeatureView(
    name="user_activity",
    entities=[user],
    ttl=timedelta(days=1),
    schema=[
        Feature(name="logins_last_30d", dtype=Int32),
        Feature(name="logins_last_7d", dtype=Int32),
        Feature(name="features_used_last_30d", dtype=Int32),
        Feature(name="days_since_last_login", dtype=Int32),
        Feature(name="support_tickets_last_90d", dtype=Int32),
        Feature(name="api_calls_last_30d", dtype=Int32),
        Feature(name="team_size", dtype=Int32),
        Feature(name="plan", dtype=String),
    ],
    source=user_source,
)
```

**Step 3 — Train the model with MLflow tracking:**

```python
# training/train.py
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score
)
from sklearn.preprocessing import LabelEncoder

# Load data
df = pd.read_parquet("data/users.parquet")

# Encode categorical features
le = LabelEncoder()
df["plan_encoded"] = le.fit_transform(df["plan"])

feature_cols = [
    "logins_last_30d", "logins_last_7d", "features_used_last_30d",
    "days_since_last_login", "support_tickets_last_90d",
    "api_calls_last_30d", "team_size", "plan_encoded",
]

X = df[feature_cols]
y = df["churned"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Train with MLflow experiment tracking
mlflow.set_experiment("churn-prediction")

with mlflow.start_run(run_name="gradient_boosting_v1"):
    # Log parameters
    params = {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.1,
        "min_samples_leaf": 20,
    }
    mlflow.log_params(params)

    # Train
    model = GradientBoostingClassifier(**params, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    metrics = {
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "auc_roc": roc_auc_score(y_test, y_prob),
    }
    mlflow.log_metrics(metrics)
    print(f"Metrics: {metrics}")

    # Log the model — this saves it in MLflow's model registry
    mlflow.sklearn.log_model(model, "churn_model")

    # Log feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    print(f"\nFeature importance:\n{importance}")
```

#### Week 2: Model Serving API

**Step 4 — Build a FastAPI serving endpoint:**

```python
# serving/app.py
"""Serve churn predictions via REST API.

The API loads the latest model from MLflow's registry
and returns a churn probability for any user.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow.sklearn
import numpy as np

app = FastAPI(title="Churn Prediction API")

# Load the latest model from MLflow
model = mlflow.sklearn.load_model("models:/churn_model/production")

class PredictionRequest(BaseModel):
    logins_last_30d: int
    logins_last_7d: int
    features_used_last_30d: int
    days_since_last_login: int
    support_tickets_last_90d: int
    api_calls_last_30d: int
    team_size: int
    plan_encoded: int  # 0=free, 1=basic, 2=pro, 3=enterprise

class PredictionResponse(BaseModel):
    churn_probability: float
    risk_level: str  # low, medium, high
    top_risk_factors: list[str]

@app.post("/predict", response_model=PredictionResponse)
def predict_churn(request: PredictionRequest):
    features = np.array([[
        request.logins_last_30d, request.logins_last_7d,
        request.features_used_last_30d, request.days_since_last_login,
        request.support_tickets_last_90d, request.api_calls_last_30d,
        request.team_size, request.plan_encoded,
    ]])

    probability = float(model.predict_proba(features)[0, 1])

    # Determine risk level
    if probability > 0.7:
        risk = "high"
    elif probability > 0.3:
        risk = "medium"
    else:
        risk = "low"

    # Identify top risk factors by comparing to population averages
    risk_factors = []
    if request.days_since_last_login > 14:
        risk_factors.append("inactive_14_plus_days")
    if request.logins_last_30d < 5:
        risk_factors.append("low_engagement")
    if request.plan_encoded == 0:
        risk_factors.append("free_plan")
    if request.team_size == 1:
        risk_factors.append("single_user_account")

    return PredictionResponse(
        churn_probability=round(probability, 4),
        risk_level=risk,
        top_risk_factors=risk_factors,
    )

@app.get("/health")
def health():
    return {"status": "healthy", "model_version": "v1"}
```

**Step 5 — Test the API locally:**

```bash
# Start the server
uvicorn serving.app:app --reload --port 8000

# Test with curl
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "logins_last_30d": 2,
    "logins_last_7d": 0,
    "features_used_last_30d": 1,
    "days_since_last_login": 21,
    "support_tickets_last_90d": 4,
    "api_calls_last_30d": 3,
    "team_size": 1,
    "plan_encoded": 0
  }'
```

#### Week 3: Monitoring and Dashboard

**Step 6 — Add model monitoring.** Track prediction distributions over time to detect model drift:

```python
# monitoring/monitor.py
"""Track model predictions over time.

Compares recent prediction distributions to the training
distribution. If they diverge significantly, the model
may need retraining (concept drift).
"""
from collections import deque
from datetime import datetime
import statistics

class ModelMonitor:
    def __init__(self, training_churn_rate: float = 0.25):
        self.predictions = deque(maxlen=10_000)
        self.training_churn_rate = training_churn_rate
        self.alerts = []

    def log_prediction(self, probability: float):
        self.predictions.append({
            "probability": probability,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def check_drift(self) -> dict:
        """Compare recent prediction distribution to training baseline."""
        if len(self.predictions) < 100:
            return {"status": "insufficient_data"}

        recent_probs = [p["probability"] for p in self.predictions]
        current_churn_rate = sum(
            1 for p in recent_probs if p > 0.5
        ) / len(recent_probs)

        drift_magnitude = abs(current_churn_rate - self.training_churn_rate)

        status = "healthy"
        if drift_magnitude > 0.10:
            status = "warning"
            self.alerts.append(f"Churn rate shifted by {drift_magnitude:.1%}")
        if drift_magnitude > 0.20:
            status = "critical"
            self.alerts.append(f"Major drift detected: {drift_magnitude:.1%}")

        return {
            "status": status,
            "current_churn_rate": round(current_churn_rate, 4),
            "training_churn_rate": self.training_churn_rate,
            "drift_magnitude": round(drift_magnitude, 4),
            "sample_size": len(recent_probs),
            "mean_probability": round(statistics.mean(recent_probs), 4),
        }
```

**Step 7 — Build a Streamlit monitoring dashboard** that shows: prediction volume over time, churn probability distribution (histogram), drift metrics, top risk factors across all recent predictions, and model performance metrics from MLflow.

**Step 8 — Write your design document and deploy.** Containerize everything with Docker, push to a cloud provider, and document your architecture decisions.

---

### Documentation Matters

For each project, write a design document that covers:

- **Problem statement**: What business problem does this solve? Who are the users? What's the current pain point?
- **Architecture diagram**: A clean diagram (use draw.io, Excalidraw, or even ASCII) showing every component and how data flows between them.
- **Technology choices and justifications**: For each component, state what you chose and why. "I chose Redis for real-time aggregations because it supports atomic increments and has sub-millisecond reads" is far better than "I used Redis."
- **Trade-offs**: What alternatives did you consider? Why did you reject them? "I considered Elasticsearch for real-time aggregations but chose Redis because our access pattern is key-value lookups, not full-text search. If we needed search, I'd add Elasticsearch as a secondary store."
- **Data model**: Show your schema designs with explanations. Include entity-relationship diagrams for relational data.
- **What breaks first at 10x scale**: Identify the bottleneck. "At 10x volume, the single Redis instance becomes the bottleneck. I'd shard by subreddit using Redis Cluster and add read replicas for the dashboard."
- **What I'd do differently**: Be honest about shortcuts you took and how you'd improve them. "I used TextBlob for sentiment analysis because it's simple, but in production I'd use a fine-tuned transformer model for much higher accuracy."

A well-documented project where you explain your decisions is far more impressive than a complex project with no documentation.

---

## Career Development: Senior to Staff

The jump from senior to staff engineer isn't about deeper technical knowledge — it's about broader impact and different ways of thinking.

**Senior engineers** solve well-defined problems. "Build this feature," "Fix this bug," "Design this service."

**Staff engineers** define which problems to solve. "Our data platform costs are growing faster than revenue — what's the strategy?" "We're expanding to 5 new markets — what infrastructure changes do we need?"

The key shifts:

1. **From implementation to architecture**: You spend less time coding and more time designing systems, writing design documents, and reviewing others' designs.

2. **From single-team to cross-team**: You identify problems that span multiple teams and drive alignment on solutions.

3. **From technical to sociotechnical**: You consider not just "what's the best technology?" but "what can our team actually operate?" and "how does this decision affect the organization?"

4. **From answering to asking**: The most valuable skill is asking the right questions. "What problem are we actually solving?" "What happens if we do nothing?" "What's the simplest thing that could work?"

> **Key Takeaway:** To grow toward staff engineer, practice thinking about systems in terms of business impact, organizational capability, and long-term evolution — not just technical elegance. Write design documents. Mentor others. Drive cross-team initiatives. The code you write matters less than the decisions you influence.

---

## Conclusion

You've now traveled from the fundamentals of system design through storage engines, processing paradigms, data warehouses, lakehouses, ML platforms, distributed systems, observability, and cost optimization. You've studied how Netflix, Uber, Spotify, Airbnb, and Twitter solve problems at massive scale. And you've learned how to communicate your design thinking in interviews and career growth.

The most important thing to remember: **there are no perfect systems, only appropriate trade-offs.** Every technology, every architecture, every design decision involves giving something up to get something else. The mark of a great engineer is not knowing every technology — it's knowing how to evaluate trade-offs in context, make a decision, and communicate why.

Build things. Break things. Learn from both. Good luck.
