# Module 1: Foundations of System Design

## How Systems Grow: From Monolith to Distributed

Every large-scale system started as a small one. Understanding how systems evolve helps you recognize *why* certain architectural patterns exist — they're not arbitrary; each one solves a specific problem that appears at a specific stage of growth.

### Stage 1: The Single Server

Every application starts here. Your web server, application code, and database all live on one machine. It's simple, easy to deploy, and easy to debug. For a side project or an app with a few hundred users, this is perfectly fine.

```
[Users] → [Single Server: Web + App + Database]
```

### Stage 2: Separate the Database

Your first scaling bottleneck is almost always the database. Your application and database compete for the same CPU, memory, and disk I/O. Separating them onto different machines lets each be optimized independently — your app server can have lots of CPU and RAM, while your database server gets fast SSDs and extra memory for caching.

```
[Users] → [App Server] → [Database Server]
```

This is also where **backups** become critical. A single server failure shouldn't lose your data. You add database replication — a primary that handles writes and one or more replicas that handle reads.

### Stage 3: Add a Cache

As traffic grows, you notice your database is doing the same work over and over. The homepage shows the same trending products to every user. The user profile page loads the same data on every visit. A cache (Redis or Memcached) stores these frequently accessed results in memory, where lookups take microseconds instead of the milliseconds a database query requires.

```
[Users] → [App Server] → [Cache (Redis)] → [Database]
```

> **Key Takeaway:** Caching is the single most effective performance optimization in most systems. A well-designed cache can reduce database load by 80-90%. But caching introduces a new problem: cache invalidation — making sure the cache doesn't serve stale data. As Phil Karlton famously said, "There are only two hard things in Computer Science: cache invalidation and naming things."

### Stage 4: Horizontal Scaling and Load Balancing

One app server can handle perhaps 1,000-5,000 concurrent connections. When you need more, you add more servers and put a **load balancer** in front of them. The load balancer distributes incoming requests across your fleet of servers.

```
                    ┌→ [App Server 1]
[Users] → [LB] ────┼→ [App Server 2] → [Cache] → [Database]
                    └→ [App Server 3]
```

This is **horizontal scaling** (adding more machines), as opposed to **vertical scaling** (getting a bigger machine). Horizontal scaling has a key advantage: it has no theoretical limit. You can always add another server. Vertical scaling hits a ceiling — there's only so much RAM and CPU you can put in one box.

But horizontal scaling introduces a challenge: your app servers must be **stateless**. If user session data lives on Server 1, and the load balancer sends the next request to Server 2, the session is lost. Solution: store session state in the cache or database, not on the app server.

### Stage 5: CDN and Global Distribution

For users far from your servers, network latency dominates response time. A request from Tokyo to a server in Virginia takes ~150ms just for the round trip — before your server even starts processing. A **CDN** (Content Delivery Network) caches static assets (images, CSS, JavaScript) at edge servers worldwide, so users load them from a nearby location.

### Stage 6: Message Queues and Async Processing

Not everything needs an immediate response. When a user places an order, they need instant confirmation — but sending the receipt email, updating inventory, and notifying the warehouse can happen asynchronously. A **message queue** (Kafka, RabbitMQ, SQS) decouples these operations. The order service publishes an "order placed" event, and downstream services process it at their own pace.

This is where the transition from monolith to **distributed system** becomes real. You now have multiple independent services communicating through events rather than direct function calls.

---

## Reliability, Scalability, and Maintainability

These three properties define a well-designed system. They're the lens through which every architecture decision should be evaluated.

### Reliability: It Keeps Working When Things Go Wrong

Things *will* go wrong. Hard drives fail. Networks partition. Developers deploy bugs. A reliable system continues to function correctly even when components fail.

**Hardware faults** are solved with redundancy: RAID arrays for disks, dual power supplies, database replicas, multi-region deployment. The key insight is that hardware faults are *random and independent* — two hard drives rarely fail at the same moment, so having two copies of your data makes loss extremely unlikely.

**Software faults** are harder because they're *correlated* — a bug in your code affects every server running that code simultaneously. These are mitigated through testing, gradual rollouts (deploy to 1% of servers first), monitoring, and the ability to quickly roll back.

**Human errors** are the most common cause of outages. Mitigate them with good abstractions that make it easy to "do the right thing," sandbox environments for experimentation, thorough testing at all levels, easy rollback mechanisms, and clear monitoring with alerting.

### Scalability: It Handles Growth

Scalability isn't a binary yes/no — it's about answering specific questions: "If traffic doubles, what happens to response time?" or "If data volume grows 10x, what needs to change?"

**Describing load** requires picking the right metrics for your system. For a web app, it might be requests per second. For a database, it might be the read-to-write ratio. For a data pipeline, it might be events per second or data volume per day.

**Describing performance** means understanding percentiles. The *average* response time is almost useless — it hides the experience of your slowest users, who are often your most important (they may have the most data or the most complex queries).

The following Python code shows how to track and report p50, p95, and p99 latency in an application. These percentiles tell you: "50% of requests complete in X ms, 95% in Y ms, and 99% in Z ms." The p99 is especially important because it represents the experience of your most affected users:

```python
import time
import statistics
from collections import deque
from functools import wraps

class LatencyTracker:
    """Track request latencies and report percentiles.

    Uses a sliding window of the most recent 10,000 measurements
    to keep memory bounded while still capturing current behavior.
    """

    def __init__(self, window_size: int = 10_000):
        self.latencies = deque(maxlen=window_size)

    def record(self, latency_ms: float):
        self.latencies.append(latency_ms)

    def get_percentiles(self) -> dict:
        if not self.latencies:
            return {}
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        return {
            'p50': sorted_latencies[int(n * 0.50)],
            'p95': sorted_latencies[int(n * 0.95)],
            'p99': sorted_latencies[int(n * 0.99)],
            'max': sorted_latencies[-1],
            'count': n,
        }

    def report(self):
        p = self.get_percentiles()
        if p:
            print(
                f"Latency: p50={p['p50']:.1f}ms, "
                f"p95={p['p95']:.1f}ms, "
                f"p99={p['p99']:.1f}ms, "
                f"max={p['max']:.1f}ms "
                f"(n={p['count']})"
            )

# Use as a decorator to automatically track any function's latency
tracker = LatencyTracker()

def track_latency(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = func(*args, **kwargs)
        elapsed_ms = (time.monotonic() - start) * 1000
        tracker.record(elapsed_ms)
        return result
    return wrapper
```

In production, you'd integrate this with Prometheus, Datadog, or a similar monitoring system. The key insight is that **you should always monitor percentiles, not averages**.

### Maintainability: Future Engineers Can Work With It

The majority of software cost is not in initial development — it's in ongoing maintenance: fixing bugs, adapting to new requirements, adding features, and keeping it running. Maintainability has three facets:

- **Operability**: Making life easy for the operations team. Good monitoring, clear runbooks, predictable behavior.
- **Simplicity**: Removing accidental complexity. The system should be as simple as possible for what it does — but no simpler.
- **Evolvability**: Making it easy to change. Requirements *will* change. The system should accommodate new features without a rewrite.

> **Key Takeaway:** When evaluating any design, ask: "Is it reliable? Does it scale? Can my team maintain it?" If any answer is no, reconsider.

---

## Networking Fundamentals for System Designers

You don't need to be a networking expert, but you need to understand the basics — because network behavior drives many system design decisions.

### What Happens When You Type a URL

1. **DNS Resolution**: Your browser asks a DNS server to translate "example.com" into an IP address like 93.184.216.34. This might involve multiple DNS servers (recursive resolver → root → TLD → authoritative).
2. **TCP Connection**: Your browser opens a TCP connection to that IP address. This involves a three-way handshake (SYN → SYN-ACK → ACK) — that's 1.5 round trips before any data flows.
3. **TLS Handshake** (for HTTPS): Another 1-2 round trips to establish encryption.
4. **HTTP Request**: Your browser sends the actual request (GET /page HTTP/1.1).
5. **Server Processing**: The server runs your application logic, queries databases, etc.
6. **HTTP Response**: The server sends back HTML, which triggers further requests for CSS, JavaScript, and images.

### Latency Numbers Every Engineer Should Know

These approximate numbers shape system design decisions. Memorize the order of magnitude:

| Operation | Time |
|-----------|------|
| L1 cache reference | 1 ns |
| L2 cache reference | 4 ns |
| RAM reference | 100 ns |
| SSD random read | 16 μs |
| HDD random read | 2 ms |
| Network round trip (same datacenter) | 0.5 ms |
| Network round trip (cross-continent) | 150 ms |

The key insight: **memory is 100,000x faster than disk, and disk within the same datacenter is 300x faster than a cross-continent network call.** This is why caches (in-memory) are so effective, and why globally distributed systems are so challenging.

### TCP vs UDP

**TCP** guarantees delivery and ordering. Every packet is acknowledged; lost packets are retransmitted. Use it when correctness matters: web requests, database queries, file transfers.

**UDP** is fire-and-forget. Faster and lighter, but packets can be lost or arrive out of order. Use it when speed matters more than completeness: video streaming, real-time gaming, DNS lookups.

---

## APIs: The Contracts Between Systems

APIs define how services communicate. Choosing the right API style affects performance, developer experience, and system evolution.

### REST

The most common style. Uses HTTP methods (GET, POST, PUT, DELETE) on resource URLs. Stateless, cacheable, well-understood. Great for CRUD operations and public-facing APIs.

### GraphQL

Lets clients request exactly the data they need — no more, no less. Solves the over-fetching problem (REST endpoint returns 50 fields when you need 3) and under-fetching problem (you need data from 3 REST endpoints). Best for complex UIs with varying data needs.

### gRPC

Uses Protocol Buffers for binary serialization and HTTP/2 for transport. Extremely fast, supports streaming. Best for internal service-to-service communication where performance matters and you control both endpoints.

Here's a practical REST API in FastAPI. Notice how the framework handles validation, serialization, and documentation automatically — this is what good abstractions look like:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(title="Product API")

class Product(BaseModel):
    id: Optional[int] = None
    name: str
    price: float
    category: str
    in_stock: bool = True
    created_at: Optional[datetime] = None

# In-memory store (a real app would use a database)
products = {}
next_id = 1

@app.post("/products", response_model=Product, status_code=201)
def create_product(product: Product):
    """Create a new product.

    FastAPI automatically validates the request body against the
    Product model. If 'name' is missing or 'price' isn't a number,
    the client gets a clear 422 error — no manual validation needed.
    """
    global next_id
    product.id = next_id
    product.created_at = datetime.utcnow()
    products[next_id] = product
    next_id += 1
    return product

@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int):
    """Retrieve a product by ID.

    Returns 404 if the product doesn't exist. The response_model
    parameter ensures the response matches the Product schema,
    even if the internal representation has extra fields.
    """
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    return products[product_id]
```

> **Key Takeaway:** Choose REST for simplicity and broad compatibility, GraphQL when clients need flexibility over what data they fetch, and gRPC for high-performance internal service communication.

---

## Databases: A First Look

We'll devote entire modules to storage systems, but here's the vocabulary you need going forward.

### SQL vs NoSQL — Different Tools, Not a Religious War

**Relational databases** (PostgreSQL, MySQL) store data in tables with predefined schemas. They enforce relationships between tables through foreign keys and guarantee ACID properties: **A**tomicity (transactions are all-or-nothing), **C**onsistency (data always satisfies constraints), **I**solation (concurrent transactions don't interfere), **D**urability (committed data survives crashes).

**NoSQL databases** is an umbrella term for everything else:
- **Key-value stores** (Redis, DynamoDB): Simple lookup by key. Blazingly fast. Good for caches, sessions, leaderboards.
- **Document stores** (MongoDB, Couchbase): Store JSON-like documents. Flexible schemas. Good when data is naturally hierarchical.
- **Wide-column stores** (Cassandra, HBase): Store data in column families. Excellent write throughput and horizontal scaling. Good for time-series and IoT data.
- **Graph databases** (Neo4j, Neptune): Store nodes and edges. Optimized for traversing relationships. Good for social networks, recommendation engines, fraud detection.

### The CAP Theorem

The CAP theorem states that a distributed system can provide at most two of three guarantees simultaneously:

- **Consistency**: Every read returns the most recent write
- **Availability**: Every request receives a response
- **Partition tolerance**: The system continues to operate despite network failures

Since network partitions *will* happen in any distributed system, the real choice is between **CP** (consistent but sometimes unavailable — e.g., most relational databases) and **AP** (available but sometimes inconsistent — e.g., Cassandra, DynamoDB).

In practice, this means: if you need strong consistency (financial transactions, inventory counts), lean toward CP systems. If you need high availability and can tolerate brief inconsistency (social media feeds, analytics counters), lean toward AP systems.

> **Key Takeaway:** Don't choose a database because it's trendy. Choose it based on your access patterns (reads vs writes, point lookups vs range scans, simple queries vs complex joins), consistency requirements, and scale needs. When in doubt, start with PostgreSQL — it's remarkably capable and well-understood.

---

## Thinking in Trade-offs

The single most important skill in system design is recognizing and evaluating trade-offs. There is no free lunch. Every optimization creates a cost somewhere else.

**Consistency vs. Availability**: Strongly consistent systems must coordinate between nodes, which adds latency and creates failure modes. Eventually consistent systems respond faster but may return stale data. The right choice depends on what your users can tolerate — a bank balance should always be consistent; a social media "like" count can lag by a few seconds.

**Latency vs. Throughput**: You can process requests one at a time for minimum latency, or batch them together for maximum throughput. A real-time fraud detection system optimizes for latency (each transaction needs a fast answer). A data warehouse query optimizes for throughput (scan a billion rows efficiently).

**Cost vs. Performance**: You can always make a system faster by throwing more hardware at it. The question is whether the improvement justifies the cost. A 10x faster query that costs 100x more per month isn't a good trade-off unless that query is business-critical.

**Simplicity vs. Flexibility**: A simple system is easier to understand, debug, and maintain — but may not handle future requirements. A flexible system can adapt to anything — but may be over-engineered for what you actually need today. The sweet spot: build for what you know you need, with clean abstractions that allow extension.

**Build vs. Buy**: Building custom infrastructure gives you control and avoids vendor lock-in. Buying (or using managed services) saves engineering time and operational burden. Most teams should buy unless they have a genuinely unique requirement.

When evaluating trade-offs, ask yourself:
1. What are we optimizing for? (Speed? Cost? Reliability? Developer velocity?)
2. What's the cost of getting this wrong?
3. Is this decision reversible? (If yes, move fast. If no, deliberate carefully.)

> **Key Takeaway:** Great system designers don't have perfect knowledge of every technology. They have great judgment about trade-offs. Practice articulating "I chose X over Y because Z" — this is the skill that separates senior engineers from everyone else.

---

## What's Next

With these foundations in place, you're ready to dive into the first deep technical topic: how to model data effectively. In Module 2, we'll explore relational modeling, dimensional modeling, document and graph models, and event-driven schemas — the building blocks for every storage and processing decision that follows.
