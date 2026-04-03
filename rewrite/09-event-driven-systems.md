# Module 9: Event-Driven & Distributed Systems

## Microservices Data Architecture

When a monolithic application splits into microservices, data architecture becomes the hardest problem. In a monolith, different features share one database — they can join tables, use transactions, and maintain consistency easily. In microservices, each service owns its data. That shared database is gone, and with it goes the easy consistency.

**The database-per-service pattern** is the fundamental rule: each microservice owns its database and no other service accesses it directly. If the Order Service needs customer data, it asks the Customer Service through an API — it doesn't query the customers table.

This seems wasteful, but the alternative is worse. A shared database creates tight coupling: changing a column in the customers table can break the Order Service, the Billing Service, and the Analytics Service simultaneously. With database-per-service, each service can evolve its schema independently.

The challenge: how do services stay in sync without a shared database? The answer is **events**.

> **Key Takeaway:** Database-per-service is non-negotiable for true microservices. The cost is complexity in keeping data synchronized. The benefit is independent deployment, scaling, and evolution of each service.

---

## Event Sourcing Deep Dive

In Module 5, we introduced event sourcing briefly. Now let's go deeper, because it's one of the most powerful — and most misunderstood — patterns in distributed systems.

### The Core Idea

Traditional systems store **current state**: "The order status is 'shipped'." Event sourcing stores **every state change**: "Order was created → payment was received → order was packed → order was shipped." The current state is derived by replaying all events.

### Why This Matters

1. **Complete audit trail**: Regulators, compliance teams, and debuggers love this. You can answer "what happened to order #12345 and when?" by reading the event log.

2. **Time travel**: Reconstruct the state of any entity at any point in time. "What was this customer's subscription status on March 15th?" Just replay events up to that date.

3. **New projections**: When you need a new read model — say, a report that didn't exist when the system was designed — you can create it by replaying historical events through new logic. No data migration needed.

### Implementation

An event store is fundamentally an append-only log per entity. Here's a practical implementation:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any
from enum import Enum
import json

class OrderStatus(Enum):
    CREATED = "created"
    PAID = "paid"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

@dataclass
class DomainEvent:
    event_type: str
    aggregate_id: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version: int = 0

class EventStore:
    """Append-only store for domain events.

    In production, this would be backed by a database optimized for
    append-heavy workloads (PostgreSQL, EventStoreDB, or Kafka).
    """

    def __init__(self):
        self.events: Dict[str, List[DomainEvent]] = {}

    def append(self, event: DomainEvent):
        if event.aggregate_id not in self.events:
            self.events[event.aggregate_id] = []
        events = self.events[event.aggregate_id]
        event.version = len(events) + 1
        events.append(event)

    def get_events(self, aggregate_id: str,
                   after_version: int = 0) -> List[DomainEvent]:
        """Retrieve events, optionally after a specific version.

        Used for rebuilding state or catching up a projection.
        """
        events = self.events.get(aggregate_id, [])
        return [e for e in events if e.version > after_version]


class Order:
    """An event-sourced order aggregate.

    State is never stored directly — it's always derived by
    replaying events through the apply methods.
    """

    def __init__(self, order_id: str, event_store: EventStore):
        self.order_id = order_id
        self.store = event_store
        self._status = None
        self._items = []
        self._total = 0.0
        self._customer_id = None
        self._replay_events()

    def _replay_events(self):
        """Rebuild current state from the event history."""
        for event in self.store.get_events(self.order_id):
            self._apply(event)

    def _apply(self, event: DomainEvent):
        """Apply a single event to update internal state."""
        if event.event_type == "order_created":
            self._status = OrderStatus.CREATED
            self._customer_id = event.data["customer_id"]
            self._items = event.data["items"]
            self._total = event.data["total"]
        elif event.event_type == "payment_received":
            self._status = OrderStatus.PAID
        elif event.event_type == "order_shipped":
            self._status = OrderStatus.SHIPPED
        elif event.event_type == "order_cancelled":
            self._status = OrderStatus.CANCELLED

    def create(self, customer_id: str, items: list, total: float):
        event = DomainEvent(
            event_type="order_created",
            aggregate_id=self.order_id,
            data={"customer_id": customer_id, "items": items, "total": total},
        )
        self.store.append(event)
        self._apply(event)

    def pay(self, payment_id: str):
        if self._status != OrderStatus.CREATED:
            raise ValueError(f"Cannot pay order in status {self._status}")
        event = DomainEvent(
            event_type="payment_received",
            aggregate_id=self.order_id,
            data={"payment_id": payment_id},
        )
        self.store.append(event)
        self._apply(event)
```

### Snapshots

Replaying thousands of events to rebuild state gets slow. **Snapshots** are periodic checkpoints: "As of event #500, the state was X." To rebuild, load the latest snapshot and replay only events after it.

---

## CQRS: Command Query Responsibility Segregation

CQRS pairs naturally with event sourcing. The idea: use different models for reading and writing.

- **Command side** (writes): Accepts commands ("place order", "cancel order"), validates business rules, and emits events. Optimized for consistency.
- **Query side** (reads): Maintains one or more denormalized **projections** built from events. Optimized for fast queries.

```python
class OrderReadModel:
    """A denormalized read model built from order events.

    This projection is optimized for the dashboard's needs:
    fast lookups by order ID, filtering by status, and
    listing orders by customer. It's eventually consistent
    with the event store — there's a small delay.
    """

    def __init__(self):
        self.orders = {}  # order_id -> denormalized order dict

    def handle_event(self, event: DomainEvent):
        """Update the read model when a new event arrives."""
        if event.event_type == "order_created":
            self.orders[event.aggregate_id] = {
                "order_id": event.aggregate_id,
                "customer_id": event.data["customer_id"],
                "items": event.data["items"],
                "total": event.data["total"],
                "status": "created",
                "created_at": event.timestamp.isoformat(),
                "updated_at": event.timestamp.isoformat(),
            }
        elif event.event_type == "payment_received":
            if event.aggregate_id in self.orders:
                self.orders[event.aggregate_id]["status"] = "paid"
                self.orders[event.aggregate_id]["updated_at"] = (
                    event.timestamp.isoformat()
                )

    def get_order(self, order_id: str) -> dict:
        return self.orders.get(order_id)

    def get_orders_by_customer(self, customer_id: str) -> list:
        return [
            o for o in self.orders.values()
            if o["customer_id"] == customer_id
        ]

    def get_orders_by_status(self, status: str) -> list:
        return [o for o in self.orders.values() if o["status"] == status]
```

You can have multiple read models for different use cases: one optimized for the customer dashboard (orders by customer), one for the operations team (orders by status and date), one for analytics (aggregated metrics). All built from the same events.

> **Key Takeaway:** CQRS makes the most sense when reads and writes have very different requirements. If your app is simple CRUD, CQRS adds complexity without benefit. If reads need denormalized data across multiple aggregates while writes need strict validation, CQRS shines.

---

## Change Data Capture (CDC)

CDC captures every change (insert, update, delete) in a database and publishes it as an event. It's the bridge between your transactional database and the rest of your data infrastructure — without modifying application code.

**Debezium** is the leading open-source CDC platform. It reads the database's transaction log (WAL in PostgreSQL, binlog in MySQL) and publishes change events to Kafka.

Here's a Debezium connector configuration for capturing changes from a PostgreSQL database:

```json
{
  "name": "postgres-orders-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "orders-db.internal",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${DEBEZIUM_PASSWORD}",
    "database.dbname": "orders",
    "database.server.name": "orders-db",
    "table.include.list": "public.orders,public.order_items",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_orders",
    "publication.name": "dbz_publication",
    "topic.prefix": "cdc",
    "transforms": "route",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "([^.]+)\\.([^.]+)\\.([^.]+)",
    "transforms.route.replacement": "cdc.$3"
  }
}
```

This produces Kafka messages on topics like `cdc.orders` and `cdc.order_items`, each containing the before and after state of the changed row. Common CDC use cases:

- **Cache invalidation**: When a product's price changes in the database, invalidate the cache entry
- **Search index sync**: When a product is updated, update the Elasticsearch document
- **Cross-service sync**: When a customer updates their address in the Customer Service, the Shipping Service sees the change via CDC events
- **Data lake ingestion**: Capture all database changes for the analytics pipeline without querying the production database

---

## API Design for Data Services

When microservices need to exchange data synchronously (not through events), API design determines the developer experience and system performance.

**REST** remains the default for most service-to-service communication. Keep it simple: resources as nouns (`/orders`, `/customers`), HTTP methods as verbs (GET, POST, PUT, DELETE), consistent error format.

**GraphQL** excels when clients need flexibility. A mobile app might need a subset of the data that a web app needs. Instead of building separate REST endpoints, GraphQL lets clients specify exactly what they want.

**gRPC** wins for performance-critical internal communication. Binary serialization (Protocol Buffers) is 3-10x faster than JSON. HTTP/2 multiplexing reduces connection overhead. Streaming support for real-time data flows.

For data-intensive APIs, pay special attention to:

- **Pagination**: Never return unbounded lists. Use cursor-based pagination for large datasets (more stable than offset-based when data is being inserted).
- **Filtering**: Let consumers filter at the API level rather than fetching everything and filtering client-side.
- **Rate limiting**: Protect your data services from runaway consumers. Return `429 Too Many Requests` with a `Retry-After` header.

---

## Data Mesh Concepts

Data Mesh is an organizational and architectural approach that treats data as a product, owned by the domain teams that produce it.

### The Problem It Solves

In traditional centralized data architectures, one data engineering team is responsible for ingesting, cleaning, and serving data from every domain in the company. This team becomes a bottleneck — they don't understand the business context of each domain, yet they're responsible for its data quality and modeling.

### The Four Principles

1. **Domain-oriented data ownership**: The team that produces the data owns it. The Payments team owns payment data, not the data platform team. They're responsible for its quality, schema, and availability.

2. **Data as a product**: Each domain's data is treated like a product with consumers, SLAs, and documentation. It should be discoverable, addressable, trustworthy, and self-describing.

3. **Self-serve data infrastructure**: A platform team provides the tools and infrastructure that domain teams use to publish and consume data products. Think of it like Heroku for data — domain teams focus on their data, not on configuring Spark clusters.

4. **Federated computational governance**: Global standards (naming conventions, quality minimums, security requirements) that all domain teams follow, enforced by automation rather than central review.

### When Data Mesh Makes Sense

Data Mesh is an organizational pattern, not a technology. It makes sense for large organizations (100+ engineers) with clearly separated domains and mature data engineering practices. For smaller teams, a centralized data team with good communication is simpler and more effective.

> **Key Takeaway:** Data Mesh doesn't mean "no governance" or "every team for themselves." It means distributing ownership while maintaining standards. The platform team shifts from "building pipelines for everyone" to "building the platform that everyone uses to build their own pipelines."

---

## Case Study: Migrating a Monolith to Event-Driven Microservices

A mid-sized e-commerce company has a monolithic Django application with a single PostgreSQL database. As the team grew to 40 engineers, deployments became painful — changing the order logic risked breaking the inventory system, and database migrations were terrifying.

### The Strangler Fig Pattern

Instead of a risky "big bang" rewrite, they used the strangler fig pattern: gradually replacing pieces of the monolith with microservices, routing traffic to the new service as each piece is ready.

**Phase 1 — Extract the first service** (Month 1-2): The Notification Service is extracted first — it's the simplest, with clear boundaries. Events (`order.confirmed`, `shipment.dispatched`) are published to Kafka by the monolith. The Notification Service consumes them and sends emails/SMS. The monolith's notification code is disabled.

**Phase 2 — Extract the Inventory Service** (Month 3-4): Inventory management moves to its own service with its own database. CDC (Debezium) captures inventory changes from the monolith's database and publishes them. The new Inventory Service consumes these events and builds its own state. Once validated, the monolith's inventory code is redirected to call the new Inventory Service's API.

**Phase 3 — Extract the Order Service** (Month 5-8): The most complex extraction. The Order Service gets its own event-sourced store. A saga orchestrator handles the distributed transaction that was previously a single database transaction: reserve inventory → charge payment → confirm order. If any step fails, compensating actions undo the previous steps.

**Key lessons**:
- Start with the simplest, lowest-risk service
- Run old and new systems in parallel and compare results before cutting over
- Events are the glue — they decouple services and enable gradual migration
- Accept eventual consistency where possible; use sagas where you need coordination
- The migration took 8 months, not the 2 months originally estimated

> **Key Takeaway:** Migrating to microservices is a marathon, not a sprint. Use the strangler fig pattern, start with low-risk services, and use events as the communication backbone. Plan for 2-4x your initial time estimate.

---

## What's Next

Building distributed systems is only half the challenge — keeping them running is the other half. Module 10 covers monitoring, observability, and data quality: how to know when something is wrong, why it's wrong, and how to fix it before your users notice.
