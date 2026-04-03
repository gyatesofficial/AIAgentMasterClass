# Module 5: Stream Processing & Real-Time Systems

## Why Real-Time?

Not everything needs to be real-time — but some things absolutely do. When a credit card transaction looks fraudulent, you can't wait for tomorrow's batch job to flag it. When a user is browsing your website, you want recommendations based on what they're doing *right now*, not what they did yesterday. When a server is about to run out of disk space, you need an alert within seconds, not hours.

Real-time processing isn't better than batch processing — it's more complex and more expensive. The question isn't "should we do real-time?" but "which specific use cases justify the added complexity?"

Common real-time use cases:
- **Fraud detection**: Score every transaction in milliseconds
- **Live dashboards**: Show business metrics that update every few seconds
- **Recommendations**: Adapt to user behavior in the current session
- **Alerting**: Detect anomalies and notify humans immediately
- **IoT**: Process sensor data as it arrives from thousands of devices

> **Key Takeaway:** Batch and real-time aren't competing approaches — they're complementary. Most systems use both. Use batch for the 90% of work where latency doesn't matter. Use streaming for the 10% where freshness is critical.

---

## Message Brokers and Kafka Fundamentals

At the heart of every streaming system is a **message broker** — a system that receives messages from producers and delivers them to consumers. Apache Kafka has become the de facto standard.

### Why Kafka Won

Before Kafka, message brokers (RabbitMQ, ActiveMQ) followed the traditional queue model: a message is delivered to one consumer, then deleted. Kafka introduced a fundamentally different model: messages are *appended to a log* and *retained for a configurable period* (days, weeks, or indefinitely). Consumers read from the log at their own pace, and multiple consumers can independently read the same messages.

This design gives you:
- **Durability**: Messages survive broker restarts (they're on disk)
- **Replayability**: New consumers can start from the beginning and process historical data
- **Decoupling**: Producers and consumers don't need to know about each other
- **Scalability**: Partitioning distributes load across multiple brokers

### Core Concepts

**Topics** are named feeds of messages. "user-events" might contain all user interactions. "orders" might contain all order events. Choose topic granularity based on how consumers need the data.

**Partitions** divide a topic across multiple brokers for parallelism. Messages within a partition are strictly ordered. A topic with 12 partitions can be consumed by up to 12 parallel consumer instances.

**Consumer Groups** allow multiple instances of a service to divide the work. Each partition is assigned to exactly one consumer in the group — so with 12 partitions and 4 consumers, each consumer handles 3 partitions.

**Offsets** track each consumer's position in a partition. If a consumer crashes and restarts, it resumes from its last committed offset — no data is lost.

Here's a practical example showing a Kafka producer and consumer in Python. The producer publishes user events; the consumer processes them. Notice how the consumer commits offsets after successful processing to ensure at-least-once delivery:

```python
from confluent_kafka import Producer, Consumer
import json
from datetime import datetime

# --- Producer: Publish user events to Kafka ---

def create_producer():
    """Create a Kafka producer with reliability settings.

    'acks=all' means the producer waits for all replicas to confirm
    receipt before considering a write successful. This is slower
    but guarantees no data loss.
    """
    return Producer({
        'bootstrap.servers': 'kafka-broker-1:9092,kafka-broker-2:9092',
        'acks': 'all',
        'retries': 3,
        'retry.backoff.ms': 1000,
    })

def publish_user_event(producer, user_id: str, event_type: str, data: dict):
    """Publish a user event to the 'user-events' topic.

    The key (user_id) determines which partition receives this message.
    All events for the same user go to the same partition, preserving
    ordering per user — critical for session analysis.
    """
    event = {
        'user_id': user_id,
        'event_type': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'data': data,
    }
    producer.produce(
        topic='user-events',
        key=user_id.encode('utf-8'),
        value=json.dumps(event).encode('utf-8'),
    )
    producer.flush()  # Ensure delivery (in production, batch flushes)

# --- Consumer: Process user events ---

def create_consumer(group_id: str):
    """Create a Kafka consumer.

    'auto.offset.reset=earliest' means a new consumer group starts
    from the beginning of the topic. 'enable.auto.commit=False'
    gives us manual control over when offsets are committed —
    we only commit after successful processing.
    """
    return Consumer({
        'bootstrap.servers': 'kafka-broker-1:9092,kafka-broker-2:9092',
        'group.id': group_id,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
    })

def process_events():
    consumer = create_consumer('analytics-pipeline')
    consumer.subscribe(['user-events'])

    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            print(f"Consumer error: {msg.error()}")
            continue

        event = json.loads(msg.value().decode('utf-8'))
        try:
            handle_event(event)
            # Only commit offset after successful processing
            consumer.commit(asynchronous=False)
        except Exception as e:
            print(f"Processing failed: {e}")
            # Don't commit — message will be reprocessed on next poll

def handle_event(event: dict):
    """Route events to appropriate handlers."""
    handlers = {
        'page_view': handle_page_view,
        'purchase': handle_purchase,
        'search': handle_search,
    }
    handler = handlers.get(event['event_type'])
    if handler:
        handler(event)
```

---

## Schema Evolution with Avro

In a streaming system, producers and consumers are different services deployed independently. You can't update them simultaneously. When the producer starts sending events with a new field, old consumers need to handle it gracefully. When a consumer expects a field that old producers don't send, it needs a sensible default.

**Apache Avro** solves this with explicit schemas and a **Schema Registry** that enforces compatibility rules.

Here's an example showing schema evolution. Version 1 of the event has basic fields. Version 2 adds an optional `device_type` field with a default value — this is backward compatible because old consumers can still read v2 messages (they just ignore the new field), and new consumers can read v1 messages (they get the default value):

```json
// Version 1: Original event schema
{
  "type": "record",
  "name": "UserEvent",
  "namespace": "com.example.events",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "event_type", "type": "string"},
    {"name": "timestamp", "type": "long"},
    {"name": "page_url", "type": ["null", "string"], "default": null}
  ]
}

// Version 2: Added device_type with a default — backward compatible
{
  "type": "record",
  "name": "UserEvent",
  "namespace": "com.example.events",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "event_type", "type": "string"},
    {"name": "timestamp", "type": "long"},
    {"name": "page_url", "type": ["null", "string"], "default": null},
    {"name": "device_type", "type": "string", "default": "unknown"}
  ]
}
```

**Safe changes** (backward compatible): Adding a field with a default value. Making a required field optional.

**Unsafe changes** (breaking): Removing a field without a default. Changing a field's type. Renaming a field.

> **Key Takeaway:** Always use a schema registry in production streaming systems. It prevents breaking changes from reaching production and documents the contract between producers and consumers. Enforce at least backward compatibility; full compatibility is even safer.

---

## Stream Processing Frameworks

Raw Kafka consumers work for simple event handling, but complex logic — windowed aggregations, stateful processing, joining multiple streams — requires a stream processing framework.

### Apache Flink

Flink is the most powerful stream processing framework. It provides **exactly-once processing** guarantees, **event-time processing** (handling late and out-of-order events), and **stateful computation** (maintaining state across events).

Flink's key concepts:
- **Event time vs. processing time**: Event time is when the event actually happened; processing time is when the system processes it. Using event time produces correct results even when events arrive late.
- **Watermarks**: A mechanism for tracking progress in event time. A watermark of T means "all events with timestamp ≤ T have arrived."
- **Windows**: Group events for aggregation. Tumbling windows (fixed, non-overlapping), sliding windows (overlapping), session windows (gap-based).

### Kafka Streams

Kafka Streams is a *library*, not a framework. You embed it in a regular Java/Kotlin application — no separate cluster to manage. It's perfect for moderate-scale stream processing where you want simplicity over raw power.

### Spark Structured Streaming

Spark's streaming model is **micro-batch**: it processes data in tiny batches (as small as 100ms). This is technically not true streaming, but for many use cases the distinction doesn't matter. The big advantage: you use the same Spark API for both batch and streaming.

Here's a practical Spark Structured Streaming example that reads from Kafka, computes real-time aggregations, and writes results to a sink:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, max as spark_max
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType
)

spark = SparkSession.builder \
    .appName("RealTimeAnalytics") \
    .getOrCreate()

# Define the schema for incoming events
event_schema = StructType([
    StructField("user_id", StringType()),
    StructField("event_type", StringType()),
    StructField("page_url", StringType()),
    StructField("amount", DoubleType()),
    StructField("timestamp", TimestampType()),
])

# Read from Kafka — this creates an unbounded streaming DataFrame
raw_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "user-events") \
    .option("startingOffsets", "latest") \
    .load()

# Parse JSON messages into structured columns
events = raw_stream \
    .selectExpr("CAST(value AS STRING) as json_str") \
    .select(from_json(col("json_str"), event_schema).alias("event")) \
    .select("event.*")

# Compute 5-minute windowed aggregations:
# For each 5-minute window, count events, unique users, and total revenue.
# The watermark ("10 minutes") tells Spark to wait up to 10 minutes
# for late-arriving events before finalizing a window.
windowed_stats = events \
    .withWatermark("timestamp", "10 minutes") \
    .groupBy(
        window("timestamp", "5 minutes"),
        "event_type"
    ) \
    .agg(
        count("*").alias("event_count"),
        avg("amount").alias("avg_amount"),
    )

# Write results to console (in production: write to a database or dashboard)
query = windowed_stats.writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate", False) \
    .trigger(processingTime="30 seconds") \
    .start()

query.awaitTermination()
```

This code computes sliding-window analytics on a continuous stream. The watermark handles late events — if an event arrives 8 minutes late, it's still counted in the correct window. If it arrives 12 minutes late, it's dropped.

### When to Use Each

| Framework | Best For | Trade-off |
|-----------|----------|-----------|
| Apache Flink | Complex stateful processing, exactly-once semantics, event-time processing | Steeper learning curve, separate cluster |
| Kafka Streams | Moderate complexity, Java/Kotlin teams, no separate cluster | Limited to Kafka ecosystem, less powerful windowing |
| Spark Structured Streaming | Teams already using Spark, batch+stream unified API | Micro-batch (not true streaming), higher latency floor |

---

## Real-Time Analytics Engines

Sometimes you don't need to *process* a stream — you need to *query* it. Real-time analytics engines ingest streaming data and make it queryable with sub-second latency.

**ClickHouse**: Open-source columnar database designed for real-time analytical queries. Ingests millions of rows per second and queries billions of rows in milliseconds. Popular for log analysis, user analytics, and real-time dashboards.

**Apache Druid**: Pre-aggregates data on ingestion, enabling sub-second OLAP queries. Designed for time-series event data. Used by companies like Airbnb, Netflix, and Walmart for user-facing analytics.

**Apache Pinot**: Similar to Druid but designed at LinkedIn for user-facing analytics at massive scale. Low-latency queries on freshly ingested data. Powers LinkedIn's "Who Viewed Your Profile" and similar features.

**When to use these vs. a warehouse**: Use a real-time analytics engine when you need sub-second query latency on data that's seconds or minutes old. Use a warehouse (Snowflake, BigQuery) when queries can tolerate minutes to hours of latency and you need more complex SQL support, joins, and ad-hoc exploration.

---

## Event Sourcing and CQRS

### Event Sourcing

Traditional systems store current state: "Account balance is $500." Event sourcing stores every state change: "Deposited $200, withdrew $50, deposited $350." The current state is derived by replaying all events.

Why this matters:
- **Complete audit trail**: You know exactly how the system got to its current state
- **Time travel**: Reconstruct the state at any point in time
- **Debugging**: Replay events to reproduce bugs
- **Flexibility**: Build new views of the same data by replaying events through new logic

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

@dataclass
class Event:
    event_type: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)

class BankAccount:
    """An event-sourced bank account.

    Instead of storing the balance directly, we store every transaction
    as an event. The balance is computed by replaying all events.
    """

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.events: List[Event] = []

    def deposit(self, amount: float, description: str = ""):
        event = Event(
            event_type="deposited",
            data={"amount": amount, "description": description}
        )
        self.events.append(event)

    def withdraw(self, amount: float, description: str = ""):
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        event = Event(
            event_type="withdrawn",
            data={"amount": amount, "description": description}
        )
        self.events.append(event)

    @property
    def balance(self) -> float:
        """Derive current balance from event history."""
        balance = 0.0
        for event in self.events:
            if event.event_type == "deposited":
                balance += event.data["amount"]
            elif event.event_type == "withdrawn":
                balance -= event.data["amount"]
        return balance

    @property
    def statement(self) -> List[dict]:
        """Generate a complete statement from events."""
        running_balance = 0.0
        entries = []
        for event in self.events:
            if event.event_type == "deposited":
                running_balance += event.data["amount"]
            elif event.event_type == "withdrawn":
                running_balance -= event.data["amount"]
            entries.append({
                "date": event.timestamp.isoformat(),
                "type": event.event_type,
                "amount": event.data["amount"],
                "balance": running_balance,
            })
        return entries
```

### CQRS (Command Query Responsibility Segregation)

CQRS separates the write model (commands) from the read model (queries). Instead of one database serving both reads and writes, you have optimized models for each:

- **Write side**: Optimized for accepting commands and storing events. Might use an event store or append-only log.
- **Read side**: Optimized for queries. Might be a denormalized table, a search index, or a materialized view. Updated asynchronously from the write side's events.

This is powerful when reads and writes have very different requirements — for example, writes need ACID guarantees while reads need sub-millisecond lookups across many dimensions.

> **Key Takeaway:** Event sourcing and CQRS add complexity. Use them when you genuinely need an audit trail, time travel, or very different read/write optimization. For most CRUD applications, a regular database is simpler and sufficient.

---

## Case Study: Real-Time Fraud Detection Pipeline

Let's design a fraud detection system that scores every credit card transaction in under 100 milliseconds.

### Architecture

```
[Transaction] → [Kafka] → [Feature Enrichment (Flink)] → [ML Scoring] → [Decision]
                              ↕                              ↕
                         [Feature Store (Redis)]      [Model Registry]
```

1. **Ingestion**: Every transaction arrives on a Kafka topic, partitioned by `user_id` for ordering guarantees.

2. **Feature Enrichment**: A Flink job enriches each transaction with features from Redis: user's average transaction amount (30-day), number of transactions in the last hour, distance from the user's typical location, device fingerprint reputation score.

3. **ML Scoring**: The enriched transaction is scored by an ML model (served via a low-latency gRPC endpoint). The model outputs a fraud probability between 0 and 1.

4. **Decision Logic**: Based on the score and business rules:
   - Score < 0.3: Approve immediately
   - Score 0.3-0.7: Approve but flag for manual review
   - Score > 0.7: Decline and alert the fraud team

5. **Feedback Loop**: Confirmed fraud cases and false positives are fed back into model training. The feature store is updated in real-time with the latest transaction data.

**The 100ms budget**: Feature lookup from Redis (~5ms) + ML inference (~30ms) + Kafka overhead (~15ms) + Flink processing (~20ms) + decision logic (~5ms) = ~75ms, leaving headroom for network variability.

> **Key Takeaway:** Real-time systems require strict latency budgets. Break the total budget into components, and ensure each component has headroom. The latency budget shapes every technology choice — you can't use a technology that takes 200ms in a 100ms pipeline, no matter how good its other features are.

---

## What's Next

Now that you understand both batch and stream processing, Module 6 covers where all this processed data goes for analysis: the data warehouse. We'll dive deep into Snowflake, BigQuery, and Redshift — how they work internally, how to optimize queries, and how to design a warehouse that serves your entire organization.
