# Module 6: Apache Kafka & Streaming

> **What you'll learn:** Real-time data is no longer optional for many use cases. By the end of this module you'll understand Kafka's architecture, be able to build producers and consumers in Python, use Kafka Connect for zero-code integrations, and build a complete streaming pipeline.

Every time you add something to cart on Amazon, that event goes through something like Kafka. Every Uber ride update. Every Netflix play event. Every fraud alert on your credit card. Behind all of these is a streaming platform processing millions of events per second, routing them to the right systems, and enabling real-time decisions.

But here is the thing most conference talks won't tell you: **80% of the time, you don't need streaming.** This module will teach you when you do, how to build it, and -- just as importantly -- when to stick with batch.

---

## 6.1 Batch vs. Streaming -- When You Actually Need Real-Time

> **TL;DR**
> - 80% of the time, batch processing is the right choice -- simpler and cheaper
> - Streaming is for fraud detection, real-time recommendations, IoT alerts, live dashboards
> - Streaming is harder, more expensive, and has more failure modes than batch
> - Most production systems use both (hot path for speed, cold path for accuracy)

"We need real-time data!" -- every startup founder, every VP of Product, every stakeholder who watched a conference talk about streaming. And 80% of the time? They don't.

### When Batch Is Fine (And Often Better)

- Daily/hourly dashboards and reports
- Data warehouse loading
- ML model training
- Any use case where "a few hours old" data is acceptable
- Most analytics

If your marketing team looks at a dashboard once a day, processing their data every 5 minutes is a waste of money and engineering effort. A nightly batch job is simpler, cheaper, and easier to debug.

### When You Actually Need Streaming

- **Fraud detection** -- you can't wait an hour to flag a suspicious transaction
- **Real-time recommendations** -- "users viewing this RIGHT NOW also viewed..."
- **IoT monitoring** -- factory sensor goes out of range, alert immediately
- **Live dashboards** -- stock tickers, live sports, operations monitoring
- **Event-driven microservices** -- order placed -> trigger fulfillment -> update inventory

The common thread: **the value of the data degrades rapidly with time.** If a fraudulent transaction happened 2 hours ago, the money is already gone. If a factory sensor hit a dangerous temperature 30 minutes ago, the damage is done.

### The Cost of Streaming

Streaming is harder and more expensive than batch:

- More complex infrastructure (Kafka cluster, schema registry, monitoring)
- Harder to debug (try debugging a race condition at 3 AM)
- More failure modes (consumer lag, partition rebalancing, exactly-once delivery)
- Higher cloud costs (always-on infrastructure vs. spin-up-then-down)

> **Key Concept: The Hybrid Approach**
>
> Most production systems use BOTH batch and streaming:
>
> - **Hot path:** Kafka -> real-time consumer -> quick aggregations -> live dashboard
> - **Cold path:** Kafka -> S3 -> Spark batch job -> data warehouse -> detailed analytics
>
> The hot path gives you speed. The cold path gives you accuracy and depth.

> **Pro Tip**
>
> At most companies, the journey looks like: (1) start with batch, (2) build Airflow pipelines, (3) one use case genuinely needs real-time, (4) add Kafka for THAT use case, (5) gradually expand. Don't try to stream everything on day one.

**At your job:** Your manager says "we need real-time everything." Push back gently. Ask: "What decision changes if we have data in 5 seconds vs. 5 minutes vs. 1 hour?" Most of the time, the honest answer is "nothing changes," and you just saved your team months of unnecessary complexity.

### Checkpoint

1. Name three use cases where streaming is genuinely necessary.
2. Why is streaming more expensive than batch processing?
3. What's the difference between a "hot path" and "cold path" in a hybrid architecture?

---

## 6.2 Kafka Architecture -- Brokers, Topics, Partitions, Consumer Groups

> **TL;DR**
> - Kafka is a distributed log, not a message queue -- messages persist and multiple consumers read independently
> - Topics are split into partitions for parallelism; ordering is guaranteed only within a partition
> - Consumer groups enable independent processing -- analytics and fraud detection read the same data without interference
> - Use KRaft mode (no Zookeeper) for new setups

Kafka isn't a message queue. That's the first misconception to clear up. It's a distributed *log*. Think of an append-only journal that multiple writers can write to and multiple readers can read from, independently, at their own pace.

With a traditional message queue (RabbitMQ, SQS), once a message is consumed, it's gone. With Kafka, messages persist for a configurable retention period (days, weeks, or forever). This is what makes Kafka powerful -- the same stream of events can be consumed by your analytics pipeline, your fraud detection system, your recommendation engine, and your data warehouse loader, all independently, all at their own speed.

### The Five Core Concepts

```
Producers ==> Topic: "orders" (3 partitions)

    || Partition 0: [msg1][msg4][msg7]...    || <= Broker 1
    || Partition 1: [msg2][msg5][msg8]...    || <= Broker 2
    || Partition 2: [msg3][msg6][msg9]...    || <= Broker 3


Consumer Group "analytics" (3 consumers):
  Consumer A -> reads Partition 0
  Consumer B -> reads Partition 1
  Consumer C -> reads Partition 2

Consumer Group "fraud-detection" (2 consumers):
  Consumer X -> reads Partitions 0, 1
  Consumer Y -> reads Partition 2

Both groups read independently - no interference.
```

**1. Brokers** -- The servers in a Kafka cluster. Each stores some data. In production, 3-5+ brokers for redundancy. If one goes down, others still have copies. Think of brokers like nodes in a distributed database -- each one holds a slice of the overall data and can take over for a failed peer.

**2. Topics** -- Named streams of messages (like tables, but append-only). Examples: `orders`, `user-clicks`, `inventory-updates`. A topic is a logical category. When your e-commerce app processes a purchase, it publishes to the `orders` topic. When a user clicks a product, it goes to `user-clicks`. You organize your data streams the same way you'd organize database tables -- by entity or event type.

**3. Partitions** -- Each topic is split into partitions. This is the parallelism mechanism, and understanding it is critical:

- Each partition is an ordered, immutable sequence of messages
- Partitions are distributed across brokers
- Messages within a partition are ordered; across partitions, no ordering guarantee
- More partitions = more parallelism = higher throughput

Why does this matter? If your `orders` topic has 1 partition, only 1 consumer can read it at a time. With 12 partitions, up to 12 consumers can process orders in parallel. Partitions are how Kafka scales horizontally -- you don't buy a bigger server, you add more partitions and more consumers.

**4. Consumer Groups** -- A set of consumers that work together. Each partition is assigned to exactly one consumer in the group. Different groups read independently -- the analytics team and fraud team consume the same messages without interfering. This is the key architectural insight: you write data once, and N different systems can process it independently, each tracking their own position in the stream.

**5. Offsets** -- Each message has a sequential offset (0, 1, 2, ...). Each consumer tracks where it left off. If a consumer crashes and restarts, it picks up from its last committed offset. This is how Kafka provides durability without deleting messages -- each consumer group maintains its own bookmark into the shared log.

### Setting Up Kafka with Docker

For development, a single-broker KRaft setup (no Zookeeper needed):

```yaml
# docker-compose.yaml
version: '3.8'

services:
  kafka:
    image: bitnami/kafka:3.7
    ports:
      - "9092:9092"
    environment:
      - KAFKA_CFG_NODE_ID=1
      - KAFKA_CFG_PROCESS_ROLES=controller,broker        # KRaft mode (no Zookeeper)
      - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
      - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092
      - KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      - KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
      - KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
      - KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE=false
    volumes:
      - kafka-data:/bitnami/kafka

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8080:8080"
    environment:
      - KAFKA_CLUSTERS_0_NAME=local
      - KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS=kafka:9092
    depends_on:
      - kafka

volumes:
  kafka-data:
```

For the hands-on project, the companion code uses a more complete setup with Postgres for persisting processed events. See `de-fast-track/modules/module-6/starter/docker-compose.yml`:

```yaml
services:
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
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8082:8080"
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092

  postgres:
    image: postgres:16
    ports:
      - "5433:5432"
    environment:
      POSTGRES_USER: dataeng
      POSTGRES_PASSWORD: dataeng
      POSTGRES_DB: streaming
    volumes:
      - ./sql:/docker-entrypoint-initdb.d
```

Start it up and create your first topic:

```bash
docker compose up -d

# Create a topic with 3 partitions
docker compose exec kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create \
    --topic orders \
    --partitions 3 \
    --replication-factor 1

# List topics
docker compose exec kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list

# Describe a topic (shows partition details)
docker compose exec kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --describe --topic orders
```

**Expected output (describe):**

```
Topic: orders    TopicId: abc123    PartitionCount: 3    ReplicationFactor: 1
    Topic: orders    Partition: 0    Leader: 1    Replicas: 1    Isr: 1
    Topic: orders    Partition: 1    Leader: 1    Replicas: 1    Isr: 1
    Topic: orders    Partition: 2    Leader: 1    Replicas: 1    Isr: 1
```

> **Common Mistake**
>
> **Too few partitions** -- You can't have more consumers (in a group) than partitions. 3 partitions = max 3 consumers. Plan ahead. You can always add partitions later, but you can never reduce them.
>
> **Assuming global ordering** -- Ordering is only guaranteed within a partition. If you need ordered processing per customer, use `customer_id` as the partition key.

### Checkpoint

1. What's the difference between Kafka and a traditional message queue?
2. Why do partitions matter for parallelism?
3. Can two different consumer groups read the same topic independently?

---

## 6.3 Producing Messages -- Serialization, Partitioning Strategies

> **TL;DR**
> - Use `acks="all"` and `enable.idempotence=True` for reliable production
> - Partition keys ensure all messages for the same entity go to the same partition (ordering)
> - Always call `producer.flush()` before your program exits
> - Batch messages with `linger.ms` for higher throughput with minimal latency increase

```bash
pip install confluent-kafka
```

### Your First Producer

Here is the producer from the course PDF. Notice the production-ready configuration -- this is not a toy example:

```python
# producer.py
"""Kafka Producer -- sends e-commerce order events."""

from confluent_kafka import Producer
import json
import time
import random
from datetime import datetime


def delivery_callback(err, msg):
    """Called once per message to indicate delivery result."""
    if err:
        print(f"Delivery failed: {err}")
    else:
        print(f"Delivered to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")


def create_producer() -> Producer:
    """Create a Kafka producer with production-ready config."""
    config = {
        "bootstrap.servers": "localhost:9092",

        # Reliability
        "acks": "all",                # Wait for all replicas to acknowledge
        "retries": 5,                 # Retry on transient failures
        "retry.backoff.ms": 1000,     # 1s between retries

        # Performance
        "linger.ms": 10,              # Batch messages for up to 10ms
        "batch.size": 65536,          # 64KB batch size
        "compression.type": "snappy", # Compress messages

        # Idempotence -- prevents duplicates on retry
        "enable.idempotence": True,
    }
    return Producer(config)


def generate_order_event() -> dict:
    """Generate a realistic e-commerce order event."""
    products = [
        {"id": "PROD-001", "name": "Wireless Headphones", "price": 79.99},
        {"id": "PROD-002", "name": "USB-C Hub", "price": 49.99},
        {"id": "PROD-003", "name": "Mechanical Keyboard", "price": 149.99},
        {"id": "PROD-004", "name": "Monitor Stand", "price": 39.99},
        {"id": "PROD-005", "name": "Webcam HD", "price": 69.99},
    ]

    product = random.choice(products)
    customer_id = f"CUST-{random.randint(1, 100):04d}"
    quantity = random.randint(1, 3)

    return {
        "event_type": "order_placed",
        "order_id": f"ORD-{int(time.time() * 1000)}-{random.randint(100, 999)}",
        "customer_id": customer_id,
        "product_id": product["id"],
        "product_name": product["name"],
        "quantity": quantity,
        "unit_price": product["price"],
        "total_amount": round(product["price"] * quantity, 2),
        "currency": "USD",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def main():
    producer = create_producer()
    topic = "orders"

    print(f"Starting producer -- sending events to '{topic}'")
    print("Press Ctrl+C to stop\n")

    try:
        count = 0
        while True:
            event = generate_order_event()

            # key = partition key. Same customer_id -> same partition -> ordered
            producer.produce(
                topic=topic,
                key=event["customer_id"],
                value=json.dumps(event),
                callback=delivery_callback,
            )

            producer.poll(0)  # Trigger delivery callbacks

            count += 1
            if count % 10 == 0:
                print(f"Sent {count} events")

            time.sleep(random.uniform(0.1, 0.5))

    except KeyboardInterrupt:
        print(f"\nStopping. Flushing remaining messages...")
        producer.flush(10)
        print(f"Total sent: {count}")


if __name__ == "__main__":
    main()
```

Let's break down every important decision in this code.

### Key Producer Concepts

**Partition Key:** Setting `key=event["customer_id"]` means Kafka hashes the key and always routes it to the same partition. All events for `CUST-0001` go to the same partition, guaranteeing order for that customer. Without a key, Kafka round-robins (good for throughput, bad for ordering).

This is a critical design decision. At your job, when someone says "we need to process events in order," your first question should be: "In order per *what*?" Per customer? Per device? Per account? That entity becomes your partition key.

**`acks="all"`**: Waits for ALL replicas to confirm. Safest setting. Alternatives: `acks=0` (fire and forget), `acks=1` (leader only). In production, always use `"all"` unless you have a specific reason not to (like logging where losing a few messages is acceptable).

**`enable.idempotence=True`**: If the producer retries (network blip), Kafka deduplicates. Without this, retries cause duplicate messages. Always enable in production. Here is why: the producer sends a message, the broker writes it, but the acknowledgment gets lost in the network. The producer retries, and now you have two copies of the same message. Idempotence assigns a sequence number to each message so the broker can detect and discard the duplicate.

**`linger.ms` and `batch.size`**: Instead of sending one message at a time, the producer batches them. A 10ms linger dramatically improves throughput with a tiny latency increase. This is the classic throughput-vs-latency tradeoff -- for most use cases, 10ms of additional latency is invisible but batching can increase throughput 10x.

**`producer.flush()`**: The producer buffers messages internally. If your program exits without flushing, those buffered messages are lost. Always flush on shutdown. The `10` argument is a timeout in seconds -- if messages can't be delivered in 10 seconds, give up.

**`producer.poll(0)`**: This triggers delivery callbacks. Without it, your callbacks never fire. The `0` means "don't wait" -- just check if any callbacks are ready and return immediately.

### Verify Messages Are Flowing

```bash
docker compose exec kafka kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic orders \
    --from-beginning \
    --property print.key=true \
    --property key.separator=": "
```

> **Common Mistake**
>
> **Not calling `producer.flush()`** -- The producer buffers messages. If your program exits without flushing, buffered messages are lost.
>
> **Not setting `enable.idempotence`** -- Network retries cause duplicate messages without it.
>
> **Producing massive messages** -- Kafka's default max is 1MB. Keep messages small; use S3 URLs for large payloads.

### The Companion Code Producer

The companion code in `de-fast-track/modules/module-6/solution/producer.py` generates a richer set of e-commerce events (page views, add-to-cart, searches, purchases) with weighted probabilities that mimic real traffic patterns. It uses `customer_id` as the partition key and includes a delivery callback for monitoring. Study both producers -- the PDF version shows production config patterns while the companion version shows realistic event modeling.

### Checkpoint

1. What does the partition key determine?
2. Why is `enable.idempotence=True` important?
3. What happens if you don't call `flush()` before your program exits?

---

## 6.4 Consuming Messages -- Offsets, Consumer Groups, Exactly-Once

> **TL;DR**
> - Disable auto-commit and commit manually AFTER successful processing
> - At-least-once + idempotent processing is the production sweet spot
> - Always close the consumer cleanly for proper group rebalancing
> - If processing is too slow, Kafka kicks you from the group (`max.poll.interval.ms`)

Producing is the easy part. Consuming is where the real engineering happens -- handling crashes, duplicate processing, and offset management.

### A Production Consumer

```python
# consumer.py
"""Kafka Consumer -- processes e-commerce order events."""

from confluent_kafka import Consumer, KafkaError, KafkaException
import json
from datetime import datetime
import signal
import sys


class OrderProcessor:
    """Processes order events and maintains running aggregations."""

    def __init__(self):
        self.total_revenue = 0.0
        self.order_count = 0
        self.customer_totals = {}

    def process(self, event: dict) -> bool:
        """Process a single order event. Returns True if successful."""
        try:
            order_id = event["order_id"]
            customer_id = event["customer_id"]
            amount = event["total_amount"]

            self.total_revenue += amount
            self.order_count += 1
            self.customer_totals[customer_id] = \
                self.customer_totals.get(customer_id, 0) + amount

            print(
                f"Order {order_id}: ${amount:.2f} from {customer_id} "
                f"| Running total: ${self.total_revenue:.2f} ({self.order_count} orders)"
            )
            return True

        except (KeyError, TypeError) as e:
            print(f"Bad message format: {e} -- skipping")
            return True  # Don't retry malformed messages
        except Exception as e:
            print(f"Processing error: {e} -- will retry")
            return False

    def print_summary(self):
        print(f"\n{'='*50}")
        print(f"SUMMARY")
        print(f"Total orders: {self.order_count}")
        print(f"Total revenue: ${self.total_revenue:.2f}")
        print(f"Avg order value: ${self.total_revenue/max(self.order_count,1):.2f}")
        print(f"Unique customers: {len(self.customer_totals)}")
        if self.customer_totals:
            top = max(self.customer_totals, key=self.customer_totals.get)
            print(f"Top customer: {top} (${self.customer_totals[top]:.2f})")
        print(f"{'='*50}\n")


def create_consumer(group_id: str) -> Consumer:
    """Create a Kafka consumer with production-ready config."""
    config = {
        "bootstrap.servers": "localhost:9092",
        "group.id": group_id,

        # Offset management
        "auto.offset.reset": "earliest",    # Start from beginning if no offset
        "enable.auto.commit": False,        # Manual commit for safety

        # Performance
        "max.poll.interval.ms": 300000,     # 5 min max between polls
        "session.timeout.ms": 45000,        # 45s heartbeat timeout
        "fetch.min.bytes": 1024,            # Min data per fetch
    }
    return Consumer(config)


def main():
    consumer = create_consumer("order-processing-group")
    processor = OrderProcessor()
    running = True

    def shutdown(signum, frame):
        nonlocal running
        print("\nShutdown signal received...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    consumer.subscribe(["orders"])
    print("Consumer started -- waiting for messages...\n")

    try:
        while running:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue  # End of partition -- not an error
                else:
                    raise KafkaException(msg.error())

            # Deserialize
            try:
                event = json.loads(msg.value().decode("utf-8"))
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e} -- skipping")
                consumer.commit(msg)  # Commit to skip this bad message
                continue

            # Process
            success = processor.process(event)

            if success:
                consumer.commit(msg)  # Commit AFTER successful processing
            else:
                print("Will retry on next poll")

    finally:
        processor.print_summary()
        consumer.close()  # Triggers clean group rebalance
        print("Consumer closed cleanly.")


if __name__ == "__main__":
    main()
```

Let's unpack the critical design decisions.

### Why `enable.auto.commit = False`?

With auto-commit enabled (the default), Kafka commits offsets on a timer regardless of whether you actually processed the message. Scenario: Kafka auto-commits offset 42, then your processing crashes on message 42. When the consumer restarts, it picks up at offset 43 -- message 42 is silently lost. You'll never know.

With manual commit, you commit *after* successful processing. If processing crashes, the offset hasn't moved, and the message gets reprocessed on restart. You might process it twice, but you'll never lose it.

### What Happens When a Consumer Crashes?

Say you have 3 consumers in a group reading 3 partitions. Consumer B dies. Here's the sequence:

1. Kafka notices Consumer B missed its heartbeat (after `session.timeout.ms`)
2. Kafka triggers a **rebalance** -- redistributes partitions among surviving consumers
3. Consumer A now reads partitions 0 and 1, Consumer C reads partition 2
4. Processing continues from the last committed offset on each partition

This is why `consumer.close()` matters -- it triggers a clean rebalance immediately instead of waiting for the session timeout. Without it, Kafka waits for the full timeout before reassigning partitions, creating a processing gap.

### Delivery Semantics

> **Key Concept: Delivery Guarantees**
>
> - **At-most-once:** Commit before processing. If processing fails, the message is lost. Fast but unreliable.
> - **At-least-once:** Commit after processing. If the commit fails, the message is reprocessed. Safe but may have duplicates. **This is what we're using.**
> - **Exactly-once:** Requires Kafka transactions or idempotent consumers. Complex but possible.
>
> The production sweet spot: **at-least-once delivery + idempotent processing.**

Exactly-once sounds ideal, but it's genuinely hard. The practical approach: accept that duplicates will happen, and make your processing idempotent so duplicates don't matter:

```python
# Idempotent processing example -- upsert instead of insert
def process_order_idempotent(event: dict, db_conn):
    """Safe to run multiple times -- uses upsert."""
    db_conn.execute("""
        INSERT INTO processed_orders (order_id, customer_id, amount, processed_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (order_id) DO NOTHING  -- Idempotent!
    """, (event["order_id"], event["customer_id"], event["total_amount"]))
```

The `ON CONFLICT DO NOTHING` clause means processing the same order twice has no effect. This pattern -- at-least-once delivery with idempotent writes -- is what most production systems use. It's simpler than true exactly-once and just as correct for the end result.

### Scaling with Consumer Groups

Run multiple consumers in the same group -- Kafka distributes partitions automatically:

```bash
# Terminal 1 -- gets partitions 0, 1
python consumer.py

# Terminal 2 (same group) -- gets partition 2
python consumer.py

# Kafka automatically rebalances!
```

If you add a third consumer and your topic has 3 partitions, each consumer gets exactly one partition. If you add a fourth consumer, one sits idle -- you can't have more consumers than partitions in a group.

### The Companion Code Consumer

The companion consumer in `de-fast-track/modules/module-6/solution/consumer.py` extends these patterns by writing events to Postgres. It uses two tables: `raw_events` for all events and `order_events` specifically for purchases. Both use `ON CONFLICT DO NOTHING` for idempotent processing. Study how it handles the database connection alongside the consumer lifecycle -- the `finally` block closes both the consumer and the database connection.

> **Common Mistake**
>
> **Auto-commit enabled** -- Leads to silent data loss. Kafka commits offsets on a timer regardless of whether you processed the message. Always commit manually.
>
> **Processing too slowly** -- If `max.poll.interval.ms` expires, Kafka kicks you from the group. Process fast or increase the timeout.
>
> **Not closing the consumer** -- `consumer.close()` triggers a clean rebalance. Without it, Kafka waits for the session timeout before reassigning partitions.

### Checkpoint

1. Why should you disable auto-commit?
2. What's the difference between at-most-once and at-least-once delivery?
3. What happens when you start a second consumer with the same group ID?

---

## 6.5 Kafka Connect -- Plugging Into Databases Without Code

> **TL;DR**
> - Source connectors stream data FROM external systems INTO Kafka
> - Sink connectors stream data FROM Kafka TO external systems
> - Debezium provides CDC (Change Data Capture) -- every database change becomes a Kafka message
> - Manage connectors via REST API; monitor them -- they fail silently

Writing a custom producer for every data source gets old fast. Kafka Connect comes with pre-built connectors for Postgres, MySQL, S3, Elasticsearch, and hundreds more.

**At your job:** This is how most companies actually get data into Kafka. You don't write custom producers for your databases -- you deploy a Debezium connector, and every INSERT, UPDATE, and DELETE automatically shows up as a Kafka message. Zero code. This is the "change data capture" pattern that powers most real-time data pipelines in production.

### Adding Kafka Connect to Docker Compose

```yaml
kafka-connect:
    image: confluentinc/cp-kafka-connect:7.6.0
    ports:
      - "8083:8083"
    environment:
      CONNECT_BOOTSTRAP_SERVERS: kafka:9092
      CONNECT_REST_PORT: 8083
      CONNECT_GROUP_ID: connect-cluster
      CONNECT_CONFIG_STORAGE_TOPIC: _connect-configs
      CONNECT_OFFSET_STORAGE_TOPIC: _connect-offsets
      CONNECT_STATUS_STORAGE_TOPIC: _connect-status
      CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_STATUS_STORAGE_REPLICATION_FACTOR: 1
      CONNECT_KEY_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      CONNECT_VALUE_CONVERTER: org.apache.kafka.connect.json.JsonConverter
      CONNECT_PLUGIN_PATH: /usr/share/java,/usr/share/confluent-hub-components
    command:
      - bash
      - -c
      - |
        confluent-hub install --no-prompt debezium/debezium-connector-postgresql:2.5.0
        confluent-hub install --no-prompt confluentinc/kafka-connect-s3:10.5.7
        /etc/confluent/docker/run
    depends_on:
      - kafka
```

### Example: Postgres -> Kafka (CDC with Debezium)

Change Data Capture streams every INSERT, UPDATE, and DELETE from Postgres into Kafka in real-time:

```bash
# Deploy the connector via REST API
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "postgres-source",
    "config": {
      "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
      "database.hostname": "postgres",
      "database.port": "5432",
      "database.user": "postgres",
      "database.password": "postgres",
      "database.dbname": "warehouse",
      "database.server.name": "warehouse",
      "table.include.list": "public.orders,public.customers",
      "topic.prefix": "cdc",
      "plugin.name": "pgoutput",
      "slot.name": "debezium_slot"
    }
  }'
```

Now every change to `orders` or `customers` automatically appears in Kafka topics `cdc.public.orders` and `cdc.public.customers`. No code required.

### Example: Kafka -> S3 (Sink)

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "s3-sink",
    "config": {
      "connector.class": "io.confluent.connect.s3.S3SinkConnector",
      "tasks.max": "1",
      "topics": "orders",
      "s3.bucket.name": "my-data-lake",
      "s3.region": "us-east-1",
      "format.class": "io.confluent.connect.s3.format.parquet.ParquetFormat",
      "flush.size": "1000",
      "rotate.interval.ms": "60000",
      "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
      "path.format": "year=YYYY/month=MM/day=dd/hour=HH",
      "timestamp.extractor": "Record"
    }
  }'
```

This writes Kafka messages to S3 in Parquet format, partitioned by date/hour. This is how most companies build their data lake ingestion layer. The hot path (Kafka consumers) handles real-time needs, while the S3 sink builds the cold path for batch analytics.

### Managing Connectors

```bash
# List all connectors
curl http://localhost:8083/connectors

# Check status
curl http://localhost:8083/connectors/postgres-source/status

# Pause / Resume / Delete
curl -X PUT http://localhost:8083/connectors/postgres-source/pause
curl -X PUT http://localhost:8083/connectors/postgres-source/resume
curl -X DELETE http://localhost:8083/connectors/postgres-source
```

> **Common Mistake**
>
> **Not monitoring connector status** -- Connectors fail silently. Check status regularly or set up alerts. A connector in a "FAILED" state means data stopped flowing, and nobody tells you unless you check.
>
> **No dead letter queue** -- If a message can't be processed, it blocks the connector. Configure `errors.deadletterqueue.topic.name` to route bad messages aside. Without a DLQ, one malformed message can halt your entire pipeline.

### Checkpoint

1. What's the difference between a source connector and a sink connector?
2. What is CDC and why is Debezium useful?
3. How do you check if a connector is healthy?

---

## 6.6 Schema Registry and Avro -- Managing Data Contracts

> **TL;DR**
> - Without schemas, producer changes break consumers silently at 3 AM
> - Avro is a compact binary format with embedded schema -- smaller and faster than JSON
> - Schema Registry validates schemas before messages enter Kafka
> - Schema evolution rules (BACKWARD, FORWARD, FULL) prevent breaking changes

Here's a production horror story. Team A produces messages to the `orders` topic with a field called `price`. Team B's consumer reads `price` and does math with it. One day, Team A renames `price` to `unit_price` and deploys. Team B's consumer crashes on every message. No warning. No review. Just a 3 AM page.

Schema Registry prevents this.

### How It Works

**Avro** -- A binary serialization format with a schema. Messages are smaller, faster, and always match a defined structure. While JSON is human-readable, Avro is machine-optimized: field names aren't repeated in every message (they're in the schema), types are enforced, and serialization is faster.

**Schema Registry** -- Stores and validates Avro schemas. When a producer sends a message, the schema is validated. If it doesn't match, the message is rejected BEFORE it hits Kafka. This is a **data contract** -- producers and consumers agree on the shape of the data, and the registry enforces it.

**Schema Evolution** -- Rules for how schemas can change:
- **BACKWARD** -- new schema can read old data (add optional fields, remove fields)
- **FORWARD** -- old schema can read new data
- **FULL** -- both directions
- **NONE** -- no checks (don't do this)

### Setup

```yaml
  schema-registry:
    image: confluentinc/cp-schema-registry:7.6.0
    ports:
      - "8081:8081"
    environment:
      SCHEMA_REGISTRY_HOST_NAME: schema-registry
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:9092
    depends_on:
      - kafka
```

### Defining an Avro Schema

```python
# Define an Avro schema
ORDER_EVENT_SCHEMA = """
{
    "type": "record",
    "name": "OrderEvent",
    "namespace": "com.ecommerce.events",
    "fields": [
        {"name": "order_id", "type": "string"},
        {"name": "customer_id", "type": "string"},
        {"name": "product_id", "type": "string"},
        {"name": "quantity", "type": "int"},
        {"name": "unit_price", "type": "double"},
        {"name": "total_amount", "type": "double"},
        {"name": "currency", "type": {"type": "string", "default": "USD"}},
        {"name": "timestamp", "type": "string"},
        {"name": "event_type", "type": {
            "type": "enum",
            "name": "EventType",
            "symbols": ["ORDER_PLACED", "ORDER_SHIPPED", "ORDER_CANCELLED"]
        }}
    ]
}
"""
```

### Producer with Avro

```bash
pip install confluent-kafka[avro]
```

```python
# avro_producer.py
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import time
from datetime import datetime

# Connect to Schema Registry
schema_registry_client = SchemaRegistryClient({"url": "http://localhost:8081"})

# Create Avro serializer -- validates against the schema
avro_serializer = AvroSerializer(
    schema_registry_client,
    schema_str=ORDER_EVENT_SCHEMA,
    to_dict=lambda obj, ctx: obj,
)

producer = SerializingProducer({
    "bootstrap.servers": "localhost:9092",
    "key.serializer": lambda k, ctx: k.encode("utf-8") if k else None,
    "value.serializer": avro_serializer,
})

# This event matches the schema -- it will be accepted
event = {
    "order_id": f"ORD-{int(time.time())}",
    "customer_id": "CUST-0001",
    "product_id": "PROD-001",
    "quantity": 2,
    "unit_price": 79.99,
    "total_amount": 159.98,
    "currency": "USD",
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "event_type": "ORDER_PLACED",
}

producer.produce(topic="orders-avro", key=event["customer_id"], value=event)
producer.flush()
print(f"Sent: {event['order_id']}")

# This would FAIL -- "INVALID_STATUS" isn't in the enum:
# bad_event = {**event, "event_type": "INVALID_STATUS"}
# producer.produce(topic="orders-avro", value=bad_event)  # Schema violation!
```

### Consumer with Avro

```python
# avro_consumer.py
from confluent_kafka import DeserializingConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

schema_registry_client = SchemaRegistryClient({"url": "http://localhost:8081"})
avro_deserializer = AvroDeserializer(schema_registry_client)

consumer = DeserializingConsumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "avro-consumer-group",
    "auto.offset.reset": "earliest",
    "key.deserializer": lambda k, ctx: k.decode("utf-8") if k else None,
    "value.deserializer": avro_deserializer,
})
consumer.subscribe(["orders-avro"])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print(f"Error: {msg.error()}")
        continue

    # msg.value() is already a Python dict -- Avro handles deserialization
    event = msg.value()
    print(f"{event['order_id']}: {event['quantity']}x "
          f"{event['product_id']} = ${event['total_amount']}")
```

### Schema Evolution

Want to add a `discount_code` field? Add it with a default value:

```json
{"name": "discount_code", "type": ["null", "string"], "default": null}
```

This is **backward compatible** -- new consumers can read old messages (`discount_code` defaults to null). The Schema Registry validates this automatically. If you try to remove a required field or change a type, the registry rejects the new schema.

This is the data contract in action. Teams can evolve their schemas independently, and the registry ensures nobody breaks the contract.

> **Common Mistake**
>
> **Not using schemas at all** -- JSON in Kafka works but leads to the Team A/B scenario above. Use schemas for anything beyond prototyping.
>
> **Setting compatibility to NONE** -- Defeats the entire purpose. You might as well use JSON.

### Checkpoint

1. What problem does Schema Registry solve?
2. What does "backward compatible" mean for schema changes?
3. Why is Avro preferred over JSON for Kafka messages?

---

## 6.7 Stream Processing Patterns -- Filtering, Enrichment, Aggregation Windows

Understanding common stream processing patterns is just as important as knowing the Kafka API. These patterns show up in every real-time system.

### Pattern 1: Filtering

The simplest pattern -- read events from one topic, filter based on criteria, write matching events to another topic:

```python
# Only forward high-value orders to a separate topic
def filter_high_value(event: dict) -> bool:
    return event.get("total_amount", 0) > 100.0

# In your consumer loop:
if filter_high_value(event):
    producer.produce("high-value-orders", key=event["customer_id"],
                     value=json.dumps(event))
```

**At your job:** "Your manager says we need real-time fraud detection." The first step is a filter: flag transactions over $10,000, or transactions from new accounts, or transactions from unusual locations. You consume from the `transactions` topic, apply your rules, and produce flagged events to a `fraud-alerts` topic that triggers notifications.

### Pattern 2: Enrichment

Add context to events by looking up data from external sources:

```python
# Enrich order events with customer data from a database or cache
def enrich_event(event: dict, customer_cache: dict) -> dict:
    customer = customer_cache.get(event["customer_id"], {})
    event["customer_name"] = customer.get("name", "Unknown")
    event["customer_tier"] = customer.get("tier", "standard")
    event["is_vip"] = customer.get("tier") == "premium"
    return event
```

The trick with enrichment is keeping lookup data fast. Reading from a database on every event creates a bottleneck. Production systems typically use an in-memory cache (Redis) or a local lookup table that's periodically refreshed from the database.

### Pattern 3: Windowed Aggregation

This is the most powerful and most complex pattern. You accumulate events over a time window and compute metrics. The companion code's `stream_processor.py` implements this with a tumbling window:

```python
# From de-fast-track/modules/module-6/solution/stream_processor.py
class MetricsAggregator:
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.current_window_start = None
        self.metrics = defaultdict(float)
        self.event_counts = defaultdict(int)
        self.product_counts = defaultdict(int)

    def add_event(self, event: dict) -> dict | None:
        ts = datetime.fromisoformat(event["timestamp"])
        window_start = ts.replace(second=0, microsecond=0)

        if self.current_window_start is None:
            self.current_window_start = window_start

        # Window rolled over -- flush and return metrics
        if window_start > self.current_window_start:
            result = self._flush()
            self.current_window_start = window_start
            return result

        event_type = event["event_type"]
        self.event_counts[event_type] += 1
        self.metrics["total_events"] += 1

        if event_type == "purchase":
            self.metrics["revenue"] += event.get("total_amount", 0)
            self.metrics["purchases"] += 1
            for item in event.get("items", []):
                self.product_counts[item.get("product_id", 0)] += item.get("quantity", 1)

        return None

    def _flush(self) -> dict:
        total = self.metrics["total_events"]
        purchases = self.metrics["purchases"]
        result = {
            "window_start": self.current_window_start,
            "window_end": self.current_window_start + timedelta(seconds=self.window_seconds),
            "total_events": int(total),
            "revenue": round(self.metrics["revenue"], 2),
            "purchases": int(purchases),
            "conversion_rate": round(purchases / total * 100, 2) if total > 0 else 0,
            "event_breakdown": dict(self.event_counts),
            "top_products": sorted(self.product_counts.items(), key=lambda x: -x[1])[:5],
        }
        self.metrics.clear()
        self.event_counts.clear()
        self.product_counts.clear()
        return result
```

This is a **tumbling window** -- fixed-size, non-overlapping time windows. Every 60 seconds, the aggregator flushes its metrics and starts fresh. When the window rolls over, you get a summary: total events, revenue, conversion rate, and top products for that minute.

**Why windows matter:** Without windowing, you'd either aggregate everything ever (useless for "what happened in the last minute?") or nothing (useless for dashboards). Windows give you bounded aggregations over time -- the fundamental building block of real-time analytics.

There are three types of windows you'll encounter:

- **Tumbling windows** (what we're using): Fixed size, no overlap. Each event belongs to exactly one window. Simple and predictable.
- **Sliding (hopping) windows**: Fixed size but they overlap. A 5-minute window that slides every 1 minute gives you smoother metrics but uses more memory.
- **Session windows**: Defined by activity gaps. "Group all events from a user until they're inactive for 30 minutes." Perfect for web session analytics.

### Pattern 4: Dead Letter Queues

In production, some messages will be malformed, corrupt, or otherwise unprocessable. Instead of crashing your consumer or silently dropping them, route bad messages to a dead letter queue:

```python
def process_with_dlq(consumer, processor, dlq_producer):
    """Process messages with dead letter queue for failures."""
    msg = consumer.poll(1.0)
    if msg is None or msg.error():
        return

    try:
        event = json.loads(msg.value().decode("utf-8"))
        success = processor.process(event)
        if success:
            consumer.commit(msg)
        else:
            # Transient failure -- will retry on next poll
            pass
    except (json.JSONDecodeError, KeyError) as e:
        # Permanent failure -- send to DLQ, commit to move past it
        dlq_producer.produce(
            "orders-dlq",
            key=msg.key(),
            value=msg.value(),
            headers=[("error", str(e).encode("utf-8"))],
        )
        consumer.commit(msg)
```

The DLQ pattern separates transient failures (retry) from permanent failures (route aside and investigate later). Without it, one bad message can block your entire pipeline.

---

## 6.8 Real-Time Dashboards and Materialized Views

The companion code includes a complete dashboard that queries Postgres for the metrics written by the stream processor. The database schema (`de-fast-track/modules/module-6/starter/sql/init.sql`) defines three tables:

```sql
CREATE TABLE raw_events (
    event_id VARCHAR(50) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    customer_id INT,
    product_id INT,
    event_data JSONB,
    event_timestamp TIMESTAMP NOT NULL,
    processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE order_events (
    order_id VARCHAR(50) PRIMARY KEY,
    customer_id INT NOT NULL,
    items JSONB NOT NULL,
    total_amount NUMERIC(10,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE realtime_metrics (
    metric_id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC(12,2) NOT NULL,
    dimensions JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_events_type ON raw_events(event_type);
CREATE INDEX idx_events_timestamp ON raw_events(event_timestamp);
CREATE INDEX idx_metrics_window ON realtime_metrics(window_start, metric_name);
```

Notice the design: `raw_events` captures everything (the audit trail), `order_events` captures the business events (what finance cares about), and `realtime_metrics` captures windowed aggregations (what the dashboard displays). The indexes on `event_timestamp` and `window_start` ensure dashboard queries are fast even as data accumulates.

The dashboard (`de-fast-track/modules/module-6/solution/src/dashboard.py`) uses the Rich library for a live CLI display:

```python
"""Live CLI dashboard for streaming metrics using Rich."""
import time
import psycopg2
from rich.console import Console
from rich.table import Table
from rich.live import Live

DB_URL = "host=localhost port=5433 dbname=streaming user=dataeng password=dataeng"


def get_latest_metrics(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT window_start, metric_name, metric_value
        FROM realtime_metrics
        WHERE window_start >= NOW() - INTERVAL '10 minutes'
        ORDER BY window_start DESC
        LIMIT 20
    """)
    return [{"window": r[0], "name": r[1], "value": r[2]} for r in cur.fetchall()]


def get_recent_events(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, COUNT(*), MAX(event_timestamp)
        FROM raw_events
        WHERE event_timestamp >= NOW() - INTERVAL '5 minutes'
        GROUP BY event_type
        ORDER BY COUNT(*) DESC
    """)
    return [{"type": r[0], "count": r[1], "latest": r[2]} for r in cur.fetchall()]


def build_dashboard(conn) -> Table:
    metrics = get_latest_metrics(conn)
    events = get_recent_events(conn)

    table = Table(title="Real-Time E-Commerce Dashboard")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Window", style="dim")

    for m in metrics[:8]:
        table.add_row(m["name"], f"{m['value']:.2f}", str(m["window"])[:19])

    if events:
        table.add_section()
        table.add_row("[bold]Event Type[/]", "[bold]Count (5m)[/]", "[bold]Latest[/]")
        for e in events:
            table.add_row(e["type"], str(e["count"]), str(e["latest"])[:19])

    return table


def run():
    conn = psycopg2.connect(DB_URL)
    console = Console()

    console.print("[bold]Starting dashboard. Ctrl+C to stop.[/]")
    try:
        with Live(build_dashboard(conn), refresh_per_second=0.5, console=console) as live:
            while True:
                live.update(build_dashboard(conn))
                time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
```

This is a mini version of what Uber or DoorDash actually runs. The pattern is: events flow through Kafka, a stream processor computes windowed aggregations, a writer persists them to a database, and a dashboard polls the database. Each component is independent and can be scaled separately.

---

## 6.9 Building a Streaming Pipeline End-to-End

> **TL;DR**
> - A complete pipeline: event generator -> Kafka -> stream processor -> metrics topic -> DB writer -> dashboard
> - The stream processor computes sliding-window aggregations in real-time
> - The DB writer stores metrics in Postgres for querying
> - This is a mini version of what Uber or DoorDash actually runs

We've learned the pieces. Now let's assemble them into a real streaming pipeline.

```
Event Generator -> Kafka "raw-events" -> Stream Processor -> Kafka "metrics" -> DB Writer -> Postgres
                                                                                              |
                                                                                       Dashboard Query
```

### The Full Docker Compose Stack

```yaml
version: '3.8'

services:
  kafka:
    image: bitnami/kafka:3.7
    ports:
      - "9092:9092"
    environment:
      - KAFKA_CFG_NODE_ID=1
      - KAFKA_CFG_PROCESS_ROLES=controller,broker
      - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
      - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      - KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
      - KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
      - KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE=true
    volumes:
      - kafka-data:/bitnami/kafka

  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: streaming
      POSTGRES_USER: streaming
      POSTGRES_PASSWORD: streaming
    volumes:
      - pg-data:/var/lib/postgresql/data

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8080:8080"
    environment:
      - KAFKA_CLUSTERS_0_NAME=local
      - KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS=kafka:9092
    depends_on:
      - kafka

volumes:
  kafka-data:
  pg-data:
```

### Component 1: Event Generator

The event generator simulates a busy e-commerce website. It produces weighted events (mostly page views, some add-to-carts, fewer purchases) to mimic real traffic:

```python
# event_generator.py
"""Simulates a busy e-commerce website generating click and purchase events."""

from confluent_kafka import Producer
import json
import random
import time
from datetime import datetime

producer = Producer({"bootstrap.servers": "localhost:9092"})

PAGES = ["home", "search", "product/headphones", "product/keyboard",
         "product/monitor", "cart", "checkout"]
# Weighted toward page views (most common event)
EVENT_TYPES = ["page_view", "page_view", "page_view", "page_view", "add_to_cart", "purchase"]


def generate_event():
    user_id = f"user_{random.randint(1, 500)}"
    event_type = random.choice(EVENT_TYPES)

    event = {
        "user_id": user_id,
        "event_type": event_type,
        "page": random.choice(PAGES),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": f"sess_{random.randint(1, 1000)}",
    }

    if event_type == "purchase":
        event["amount"] = round(random.uniform(19.99, 299.99), 2)
        event["product_id"] = f"prod_{random.randint(1, 50)}"

    if event_type == "add_to_cart":
        event["product_id"] = f"prod_{random.randint(1, 50)}"

    return user_id, event


def main():
    print("Event generator started -- simulating website traffic")
    count = 0

    try:
        while True:
            key, event = generate_event()
            producer.produce("raw-events", key=key, value=json.dumps(event))
            producer.poll(0)

            count += 1
            if count % 100 == 0:
                print(f"  Generated {count} events")

            time.sleep(random.uniform(0.01, 0.1))  # Simulate bursty traffic

    except KeyboardInterrupt:
        producer.flush()
        print(f"\nGenerated {count} total events")


if __name__ == "__main__":
    main()
```

### Component 2: Stream Processor

The stream processor consumes raw events, maintains a sliding window of aggregations, and periodically emits computed metrics to a separate Kafka topic:

```python
# stream_processor.py
"""Consumes raw events, computes real-time aggregations, produces metrics."""

from confluent_kafka import Consumer, Producer
import json
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time


class RealTimeAggregator:
    """Maintains sliding window aggregations."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.events = []
        self.lock = threading.Lock()

    def add_event(self, event: dict):
        with self.lock:
            ts = datetime.fromisoformat(event["timestamp"].rstrip("Z"))
            self.events.append((ts, event))
            self._prune()

    def _prune(self):
        """Remove events outside the window."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.window_seconds)
        self.events = [(ts, e) for ts, e in self.events if ts > cutoff]

    def get_metrics(self) -> dict:
        with self.lock:
            self._prune()

            if not self.events:
                return {"window_seconds": self.window_seconds, "events": 0}

            events = [e for _, e in self.events]
            purchases = [e for e in events if e["event_type"] == "purchase"]
            unique_users = len(set(e["user_id"] for e in events))
            revenue = sum(e.get("amount", 0) for e in purchases)

            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "window_seconds": self.window_seconds,
                "total_events": len(events),
                "page_views": sum(1 for e in events if e["event_type"] == "page_view"),
                "cart_adds": sum(1 for e in events if e["event_type"] == "add_to_cart"),
                "purchases": len(purchases),
                "revenue": round(revenue, 2),
                "unique_users": unique_users,
                "conversion_rate": round(
                    len(purchases) / max(unique_users, 1) * 100, 2
                ),
                "events_per_second": round(
                    len(events) / self.window_seconds, 1
                ),
            }


def main():
    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": "stream-processor",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })

    metrics_producer = Producer({"bootstrap.servers": "localhost:9092"})
    aggregator = RealTimeAggregator(window_seconds=60)

    consumer.subscribe(["raw-events"])
    print("Stream processor started")

    last_emit = time.time()
    events_processed = 0

    try:
        while True:
            msg = consumer.poll(0.1)

            if msg and not msg.error():
                event = json.loads(msg.value().decode("utf-8"))
                aggregator.add_event(event)
                events_processed += 1

            # Emit metrics every 5 seconds
            if time.time() - last_emit >= 5:
                metrics = aggregator.get_metrics()
                metrics_producer.produce(
                    "metrics", key="realtime", value=json.dumps(metrics)
                )
                metrics_producer.poll(0)

                print(
                    f"[{metrics['timestamp'][:19]}] "
                    f"Events: {metrics['total_events']} | "
                    f"Users: {metrics['unique_users']} | "
                    f"Purchases: {metrics['purchases']} | "
                    f"Revenue: ${metrics['revenue']:.2f} | "
                    f"Conv: {metrics['conversion_rate']}%"
                )
                last_emit = time.time()

    except KeyboardInterrupt:
        print(f"\nProcessed {events_processed} total events")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
```

### Component 3: Database Writer

The database writer consumes from the `metrics` topic and persists aggregations to Postgres, where the dashboard can query them. This is the same pattern as the companion code's consumer -- it writes to the `realtime_metrics` table with the windowed aggregation data.

### Running the Full Pipeline

Open four terminal windows:

```bash
# Terminal 1: Start infrastructure
docker compose up -d

# Terminal 2: Start the event generator
python event_generator.py

# Terminal 3: Start the stream processor
python stream_processor.py

# Terminal 4: Start the dashboard
python src/dashboard.py
```

You should see events flowing in real-time: the generator produces events, the stream processor aggregates them into 60-second windows, the metrics get written to Postgres, and the dashboard displays live conversion rates, revenue, and event counts.

### When NOT to Use Streaming

Before you build all of this for your project, ask yourself honestly:

**Batch is better when:**
- Your data consumers look at dashboards once a day or less
- "Yesterday's data" is perfectly acceptable for decisions
- Your data volumes are manageable with hourly/daily jobs
- You don't have the team to operate streaming infrastructure 24/7
- You're optimizing for engineering simplicity and cost

**Streaming is better when:**
- Data value degrades rapidly with time (fraud, IoT, recommendations)
- You have event-driven architectures where systems react to events
- You need sub-minute visibility into operations
- You're building features that are inherently real-time (chat, live tracking)

Most companies need both. Start with batch. Add streaming for the use cases that genuinely require it. The worst outcome is building a complex streaming pipeline for something a cron job could handle.

---

## Module 6 Project: Real-Time E-Commerce Analytics Pipeline

Build a complete streaming pipeline that processes e-commerce events in real-time.

### Project Structure

```
module-6/
  starter/
    docker-compose.yml          # Kafka + Postgres + Kafka UI
    sql/init.sql                # Database schema
    producer_starter.py         # TODO: Implement
    consumer_starter.py         # TODO: Implement
  solution/
    producer.py                 # Complete producer with event generation
    consumer.py                 # Complete consumer with Postgres writes
    stream_processor.py         # Windowed aggregations
    src/dashboard.py            # Live CLI dashboard
```

### Step 1: Start Infrastructure

```bash
cd de-fast-track/modules/module-6/starter
docker compose up -d
```

### Step 2: Implement the Producer

Open `producer_starter.py` and implement:
- Configure the producer with `bootstrap.servers`
- Generate realistic e-commerce events (page_view, add_to_cart, purchase, search)
- Send events to the `ecommerce-events` topic using `customer_id` as the key
- Add a delivery callback for monitoring
- Run in a loop with configurable rate

### Step 3: Implement the Consumer

Open `consumer_starter.py` and implement:
- Configure the consumer with `group.id` and `auto.offset.reset`
- Subscribe to `ecommerce-events`
- Build an `OrderProcessor` class that writes events to Postgres
- Add graceful shutdown with signal handlers
- Use `ON CONFLICT DO NOTHING` for idempotent processing

### Step 4: Add Stream Processing

Build a stream processor that:
- Consumes from `ecommerce-events`
- Maintains 60-second tumbling windows
- Computes: total events, revenue, conversion rate, top products
- Writes window metrics to the `realtime_metrics` table

### Step 5: Build the Dashboard

Create a dashboard that queries Postgres and displays live metrics. The solution uses the Rich library, but a simple `while True` loop printing formatted SQL results works too.

### Expected Output

- Producer generating 5+ events/second across multiple event types
- Consumer writing all events to `raw_events` and purchases to `order_events`
- Stream processor computing per-minute metrics
- Dashboard showing live conversion rates, revenue, and event breakdowns

### Stretch Goals

1. **Multiple consumer groups** -- Run an analytics consumer AND a fraud detection consumer on the same topic
2. **Schema Registry** -- Add Avro schemas and validate events before they enter Kafka
3. **Dead letter queue** -- Route malformed events to a DLQ topic instead of dropping them
4. **Kafka Connect** -- Add an S3 sink connector to build the cold path alongside your hot path
5. **Alerting** -- Trigger an alert when conversion rate drops below a threshold

---

*End of Module 6*
