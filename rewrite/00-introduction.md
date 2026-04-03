# Introduction: Welcome to System & Data Design

## What This Course Is — and Who It's For

If you've ever wondered how Netflix serves personalized recommendations to 200 million people in under 100 milliseconds, or how Uber recalculates surge pricing across 10,000 cities every 30 seconds, you're in the right place.

This course is a complete guide to designing data-intensive systems at scale. It's written for software engineers, data engineers, and anyone who wants to understand how modern enterprise systems are built — from the ground up. You don't need prior system design experience. You just need curiosity and a willingness to think about *why* systems are built the way they are, not just *how*.

By the end of this course, you'll be able to:

- Design end-to-end data systems that handle millions of users and petabytes of data
- Choose the right storage, processing, and serving technologies for any use case
- Build reliable, scalable data pipelines that don't break at 3 AM
- Evaluate trade-offs like a senior engineer — because there are always trade-offs
- Ace system design interviews at top technology companies
- Speak confidently about architectures used by Netflix, Uber, Spotify, Airbnb, and Twitter

## How to Use This Course

This course is structured as a journey. Each module builds on the ones before it, like floors of a building. Here's the path:

**Modules 1-3** lay the foundation: how systems grow, how data is modeled, and how it's stored. These are the concepts everything else rests on.

**Modules 4-5** introduce the two fundamental processing paradigms: batch and stream. You'll understand when data can wait to be processed and when it can't.

**Modules 6-7** cover where processed data lives for analysis: data warehouses and data lakes, including the modern "lakehouse" that combines the best of both.

**Modules 8-9** tackle advanced patterns: ML platforms, feature stores, event-driven architectures, and distributed system design patterns like CQRS and Data Mesh.

**Modules 10-11** address the operational reality: monitoring, data quality, cost optimization, and capacity planning — because building a system is only half the job.

**Module 12** brings everything together with deep-dive case studies of five real-world systems at massive scale.

**Module 13** prepares you for interviews and helps you build a portfolio that demonstrates your skills.

**The best way to learn**: Read each module, study the code examples, then try the exercises. The code isn't meant to be copied into production — it's meant to teach concepts. When you see a Python snippet, focus on the *pattern* it demonstrates, not the specific syntax.

---

## What is System Design?

Writing code and designing systems are fundamentally different skills. Writing code is like being a bricklayer — you need to know how to lay each brick precisely. Designing systems is like being an architect — you need to decide *what* to build, *where* to put it, and *how* the pieces connect.

**System design is the process of defining the architecture, components, and data flow of a system to satisfy a set of requirements.**

Here's what makes it interesting: there's almost never one "right" answer. Every design decision involves trade-offs. Choosing a relational database over a document store isn't right or wrong — it depends on your data access patterns, consistency requirements, and team expertise. The mark of a great system designer isn't knowing every technology; it's knowing how to *choose* between them.

Consider a simple example. You're building a social media feed. Seems straightforward — users post content, followers see it. But immediately, questions cascade:

- When a user with 10 million followers posts, do you write that post to 10 million feeds immediately (fan-out on write), or do you assemble each user's feed when they open the app (fan-out on read)?
- How fresh does the feed need to be? Real-time? Within a minute? Within an hour?
- What happens if a server goes down mid-write? Do some followers see the post and others don't?
- How do you rank posts? Chronologically? By relevance? By a mix?

Every one of these questions changes the architecture. That's system design.

> **Key Takeaway:** System design is about making informed decisions under constraints. The goal isn't perfection — it's building something that works reliably for your specific requirements and can evolve as those requirements change.

---

## The System Design Thinking Framework

When faced with any system design challenge — whether in an interview or at work — follow this structured approach. It prevents you from jumping to solutions before understanding the problem.

### Step 1: Gather Requirements

Every system exists to solve a business problem. Before drawing a single box on a whiteboard, understand *what* the system needs to do.

**Functional requirements** are the features: "Users can upload photos," "The system sends email notifications," "Analysts can query sales data by region and date."

**Non-functional requirements** are the quality attributes: How fast? How reliable? How many users? These often matter more than features. A system that handles 100 users per second needs a very different architecture than one handling 100,000.

### Step 2: Estimate Scale with the 4 Vs

The **4 Vs of data** help you quantify the challenge:

- **Volume**: How much data? Gigabytes? Terabytes? Petabytes? This determines your storage strategy.
- **Velocity**: How fast does data arrive? 10 events per second? 10 million? This determines your processing approach.
- **Variety**: What forms does data take? Structured tables? JSON documents? Images? Videos? Log files? This influences your storage and processing choices.
- **Veracity**: How reliable is the data? Is it clean and validated, or messy and inconsistent? This drives your data quality strategy.

A system processing 1 GB of clean, structured data per day is a fundamentally different challenge than one processing 1 TB of messy, semi-structured data per second.

### Step 3: Design Top-Down

Start with the big picture, then zoom in:

1. **High-level design**: What are the major components? How does data flow between them?
2. **Component design**: How does each component work internally? What technology does it use?
3. **Detailed design**: What are the data models, APIs, algorithms, and configurations?

This top-down approach prevents you from getting lost in details before the overall picture is clear.

### Step 4: Analyze Trade-offs

Every design decision involves giving something up to get something else. The key trade-offs you'll encounter throughout this course:

| Trade-off | You Get | You Give Up |
|-----------|---------|-------------|
| Consistency vs. Availability | All users see the same data | System may be unavailable during failures |
| Latency vs. Throughput | Fast individual responses | Lower total processing capacity |
| Simplicity vs. Flexibility | Easy to understand and maintain | Harder to adapt to new requirements |
| Cost vs. Performance | Lower cloud bills | Slower queries or higher latency |

There is no universal "right" side. The answer depends on your specific requirements.

> **Key Takeaway:** Follow the framework — Requirements → Scale Estimation → High-Level Design → Component Design → Trade-offs. This structured approach works for interview questions, architecture reviews, and real production systems.

---

## The Building Blocks

Every complex system is built from a small set of fundamental components. Think of them as LEGO bricks — individually simple, but capable of creating anything when combined thoughtfully. Here's your vocabulary for the rest of the course:

**Databases** store your data persistently. Relational databases (PostgreSQL, MySQL) organize data in tables with strict schemas. NoSQL databases (MongoDB, Cassandra, Redis) trade some of that structure for flexibility or performance. We'll spend entire modules on these.

**Caches** store frequently accessed data in memory for fast retrieval. Instead of querying your database for the same popular product page 10,000 times per second, you query the cache — which responds in microseconds instead of milliseconds. Redis and Memcached are the most common.

**Message Queues and Event Streams** decouple producers from consumers. When a user places an order, instead of your order service directly calling the inventory service, the email service, and the analytics service, it publishes an "order placed" event to a queue. Each downstream service picks it up independently. Apache Kafka is the dominant technology here.

**Load Balancers** distribute incoming traffic across multiple servers. When one server isn't enough, you add more and put a load balancer in front. Requests are distributed across servers so no single one is overwhelmed.

**CDNs (Content Delivery Networks)** cache static content (images, CSS, JavaScript) at servers geographically close to users. A user in Tokyo shouldn't wait for data to travel from a server in Virginia.

**APIs (Application Programming Interfaces)** are the contracts between services. They define how one component communicates with another — what requests it accepts and what responses it returns. REST, GraphQL, and gRPC are the three main styles.

**Blob/Object Storage** (S3, GCS) stores large, unstructured data — files, images, videos, backups, data lake contents. It's extremely cheap and virtually unlimited in capacity.

---

## A Simple End-to-End Example: The URL Shortener

Let's tie these building blocks together by designing something concrete: a URL shortener like bit.ly. This is deliberately simple — the goal is to see how the pieces connect.

### Requirements

**Functional**: Users submit a long URL and get back a short one. When someone visits the short URL, they're redirected to the original. Users can optionally see how many times their link was clicked.

**Non-functional**: The system handles 1,000 new URLs per day and 100,000 redirects per day. Redirects must be fast (under 50ms). Short URLs should work forever (high durability). The system should be available 99.9% of the time.

### Scale Estimation

- **Write volume**: 1,000 URLs/day ≈ 0.01 writes/second. Tiny.
- **Read volume**: 100,000 redirects/day ≈ 1.2 reads/second. Still small, but 100x the writes. This is a read-heavy system.
- **Storage**: Each URL record is ~500 bytes. Over 10 years: 500 bytes × 1,000/day × 365 × 10 ≈ 1.8 GB. A single database can handle this easily.

### High-Level Architecture

```
User → Load Balancer → Web Server → Cache (Redis) → Database (PostgreSQL)
                                         ↓
                                   Analytics Store
```

1. User submits a long URL to the **Web Server** via the API
2. Server generates a short code, stores the mapping in **PostgreSQL**, and returns the short URL
3. When someone visits the short URL, the server checks **Redis** first (cache hit = fast redirect)
4. On cache miss, it queries PostgreSQL, caches the result, and redirects
5. Every redirect increments a counter in the **Analytics Store**

### Implementation

The following Python code implements the core of this system using Flask. It demonstrates how a web server, database, and cache work together. Notice how each component has a clear responsibility:

```python
import hashlib
import time
from flask import Flask, redirect, request, jsonify
import redis
import psycopg2

app = Flask(__name__)

# Redis cache for fast URL lookups (the "fast path")
cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# PostgreSQL for durable storage (the "source of truth")
db = psycopg2.connect(
    host='localhost', dbname='urlshortener', user='app', password='secret'
)

def generate_short_code(url: str) -> str:
    """Generate a 7-character short code from the URL.

    We hash the URL + timestamp to avoid collisions, then take the
    first 7 characters of the base62 encoding. This gives us 62^7 ≈
    3.5 trillion possible codes — plenty for our scale.
    """
    hash_input = f"{url}{time.time()}".encode()
    hash_hex = hashlib.sha256(hash_input).hexdigest()
    # Convert first 10 hex chars to base62 (simplified)
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    num = int(hash_hex[:10], 16)
    code = ""
    while len(code) < 7:
        code += chars[num % 62]
        num //= 62
    return code

@app.route('/shorten', methods=['POST'])
def shorten_url():
    """Create a new short URL.

    Writes to both the database (durability) and cache (performance).
    The database is our source of truth; the cache is an optimization.
    """
    long_url = request.json['url']
    short_code = generate_short_code(long_url)

    # Store in PostgreSQL (durable)
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO urls (short_code, long_url, created_at, click_count) "
        "VALUES (%s, %s, NOW(), 0)",
        (short_code, long_url)
    )
    db.commit()

    # Cache in Redis (fast reads) with 24-hour expiry
    cache.setex(f"url:{short_code}", 86400, long_url)

    return jsonify({
        'short_url': f'https://short.ly/{short_code}',
        'long_url': long_url
    })

@app.route('/<short_code>')
def redirect_url(short_code: str):
    """Redirect a short URL to its original destination.

    This is the hot path — it handles 100x more traffic than creation.
    We check the cache first (microseconds), falling back to the
    database (milliseconds) only on cache miss.
    """
    # Try cache first (fast path)
    long_url = cache.get(f"url:{short_code}")

    if not long_url:
        # Cache miss — query database (slow path)
        cursor = db.cursor()
        cursor.execute(
            "SELECT long_url FROM urls WHERE short_code = %s",
            (short_code,)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'URL not found'}), 404

        long_url = result[0]
        # Populate cache for next time
        cache.setex(f"url:{short_code}", 86400, long_url)

    # Increment click counter asynchronously
    # (In production, you'd publish to a message queue instead)
    cache.incr(f"clicks:{short_code}")

    return redirect(long_url, code=302)
```

Notice a few things about this code:

- **The cache is an optimization, not a requirement.** If Redis goes down, the system still works — it's just slower because every request hits PostgreSQL.
- **We write to both cache and database on creation**, so the first read is always a cache hit. This is called "write-through caching."
- **Click counting uses Redis `INCR`** for speed, but in a production system you'd publish click events to a message queue (like Kafka) for reliable analytics processing.
- **The 302 redirect** (temporary) is intentional — it ensures browsers always come back to our server, so we can track clicks. A 301 (permanent) would let browsers cache the redirect and skip us.

> **Key Takeaway:** Even a simple system like a URL shortener involves multiple components (web server, database, cache), clear data flow, and deliberate trade-off decisions. Every concept in this example — caching, read-heavy optimization, write-through patterns, async analytics — scales up to the massive systems we'll study in later modules.

---

## What Comes Next

In Module 1, we'll zoom in on the foundations: how systems evolve from a single server to a distributed architecture, the fundamentals of networking and APIs, and the critical skill of thinking in trade-offs. From there, we'll progressively build your understanding — data modeling, storage engines, batch and stream processing, warehouses and lakehouses, ML platforms, and distributed systems — until you can design systems like the ones powering the world's most demanding applications.

Let's get started.
