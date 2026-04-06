# Module 12: Cost Optimization & Scaling

## What This Module Covers

LLM costs can grow faster than your revenue if you're not deliberate. This module covers three techniques that together can reduce your LLM costs by 60-80%: intelligent model routing, semantic response caching, and batch processing.

## What You'll Build

| File | Technique | Potential Savings |
|------|-----------|------------------|
| `01_model_routing.py` | Route to cheapest capable model | 40-60% |
| `02_caching.py` | Cache similar questions | 20-40% |
| `03_batch_processing.py` | Process off-peak in batches | 20-50% |

## Key Concepts

### The Cost Problem

At scale, LLM costs are significant:

| Scenario | Cost/Ticket | Monthly (10K tickets/day) |
|----------|------------|--------------------------|
| All GPT-4o | $0.017 | $5,100 |
| Model routing | $0.006 | $1,800 |
| + Caching (30% hit) | $0.004 | $1,260 |
| + Batch processing | $0.003 | $900 |
| **Total savings** | | **$4,200/month (82%)** |

### Technique 1: Intelligent Model Routing

Not every ticket needs GPT-4o. Route based on complexity:

```python
class ModelRouter:
    ROUTING_RULES = [
        # Simple questions → cheap model
        Rule(
            categories=["general_inquiry"],
            priorities=["low"],
            model="claude-haiku-3",     # $0.00025/1K input tokens
        ),
        # Standard support → mid-tier model
        Rule(
            categories=["billing", "account_access"],
            priorities=["low", "medium"],
            model="gpt-4o-mini",        # $0.00015/1K input tokens
        ),
        # Complex / high-priority → best model
        Rule(
            categories=["technical_bug"],
            priorities=["high", "critical"],
            model="gpt-4o",             # $0.005/1K input tokens
        ),
    ]
```

**Model pricing comparison (April 2025):**

| Model | Input | Output | Good For |
|-------|-------|--------|----------|
| gpt-4o-mini | $0.15/M | $0.60/M | Simple tasks |
| gpt-4o | $5.00/M | $15.00/M | Complex reasoning |
| claude-3-haiku | $0.25/M | $1.25/M | Fast, cheap |
| claude-3-5-sonnet | $3.00/M | $15.00/M | Balanced |
| claude-opus-4 | $15.00/M | $75.00/M | Hardest problems |

### Technique 2: Semantic Response Caching

Cache answers by meaning, not exact text:

```
"How do I reset my password?" ──▶ embed ──▶ similarity search ──▶ cache HIT
"I forgot my password"        ──▶ embed ──▶ similarity search ──▶ cache HIT
"password reset instructions" ──▶ embed ──▶ similarity search ──▶ cache HIT
```

All three questions get the same cached response — without an LLM call.

```python
class SemanticCache:
    SIMILARITY_THRESHOLD = 0.92  # Only return cache hit if very similar

    def get(self, query: str) -> Optional[str]:
        query_embedding = embed(query)
        similar = self.vector_store.search(query_embedding, top_k=1)
        if similar and similar[0].score > self.SIMILARITY_THRESHOLD:
            return similar[0].cached_response
        return None

    def set(self, query: str, response: str):
        embedding = embed(query)
        self.vector_store.upsert(query, embedding, response)
```

**Cache TTL strategy:**
- FAQ responses: 7 days
- Procedure guides: 24 hours
- Customer-specific responses: Never cache (contain PII)
- Incident-related responses: 1 hour (may change)

### Technique 3: Batch Processing

Non-urgent tickets can wait for off-peak processing:

```
Peak hours (9am-5pm):   Immediate processing → GPT-4o at full price
                                               Latency: 5-15 seconds

Off-peak (5pm-9am):     Batch processing → OpenAI Batch API
                                           50% discount on all models
                                           Latency: up to 24 hours
```

Classification by urgency:
- **Immediate**: Critical priority, enterprise customers, security issues
- **Next hour**: High priority
- **Batched**: Low/medium priority general inquiries

### Cost Monitoring

Track costs in real-time to catch anomalies:

```python
# Alert thresholds
DAILY_COST_ALERT = 100.00   # Alert if daily cost > $100
HOURLY_COST_ALERT = 20.00   # Alert if hourly cost > $20
PER_REQUEST_LIMIT = 0.50    # Reject requests that would cost > $0.50

# Cost dashboard metrics
- Total cost today/week/month
- Cost per ticket (p50, p95, p99)
- Cost by model
- Cost by category
- Cache hit rate
```

## How to Run the Examples

```bash
# Requires Redis for caching examples
docker compose up -d redis

# All require OPENAI_API_KEY
python module_12_cost_optimization/examples/01_model_routing.py
python module_12_cost_optimization/examples/02_caching.py
python module_12_cost_optimization/examples/03_batch_processing.py
```

## What's Next

Module 13 covers observability — tracing, logging, metrics, and dashboards. You can't optimize what you can't measure.
