# Module 9: Production Infrastructure

## What This Module Covers

Running an agent in a Jupyter notebook is very different from running it in production serving thousands of requests per day. This module covers the infrastructure patterns you need: HTTP APIs, async processing, streaming, and rate limiting.

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_fastapi_agent.py` | REST API wrapper for the agent |
| `02_async_agent.py` | Async agent for concurrent request handling |
| `03_rate_limiting.py` | Per-user and global rate limits |

## Key Concepts

### Why FastAPI?

FastAPI is the right choice for agent APIs because:
- **Async native**: LLM calls are I/O-bound — async lets you handle 10x more concurrent requests
- **Automatic validation**: Request/response schemas via Pydantic
- **Auto-generated docs**: `/docs` gives you a Swagger UI for free
- **Type safety**: Catches parameter errors before they reach the LLM

### The Ticket Submission Flow

```
POST /tickets
    │
    ├── Validate request (Pydantic)
    ├── Create ticket record in DB
    ├── Add to processing queue
    └── Return ticket ID immediately (202 Accepted)

Background task:
    ├── Run triage agent
    ├── Run resolution agent
    ├── Update ticket status
    └── Trigger notifications
```

**Why async + background tasks?** An LLM pipeline takes 5-30 seconds. You can't make the HTTP client wait that long. Return immediately with a ticket ID, process in the background, and let the client poll or use webhooks.

### Streaming Responses

For chat interfaces, stream the agent's thinking in real-time:

```python
@app.post("/tickets/{ticket_id}/chat")
async def chat_stream(ticket_id: str, message: ChatMessage):
    async def generate():
        async for chunk in agent.astream(message.content):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

The client receives tokens as they're generated, making the response feel instant.

### Health Checks

Production services need health endpoints for load balancers and monitoring:

```python
@app.get("/health")
async def health():
    # Check all dependencies
    checks = {
        "database": await check_db(),
        "redis": await check_redis(),
        "chromadb": await check_chroma(),
        "openai_api": await check_openai(),
    }
    status = "healthy" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks}
```

### Rate Limiting Architecture

```
Request ──▶ [Global Rate Limit] ──▶ [Per-User Rate Limit] ──▶ [Cost Limit] ──▶ Agent
```

| Limit Type | Value | Window |
|-----------|-------|--------|
| Global requests | 1,000 | per minute |
| Per-user requests | 10 | per minute |
| Per-user cost | $1.00 | per hour |
| Per-request cost | $0.50 | — |

Rate limits are stored in Redis using the sliding window algorithm.

### Error Handling

Never let agent errors bubble up as 500s:

```python
@app.exception_handler(AgentError)
async def agent_error_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "agent_failed", "message": str(exc)}
    )

@app.exception_handler(RateLimitError)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after": exc.retry_after}
    )
```

### Running the API

```bash
# Development
uvicorn module_09_production.examples.01_fastapi_agent:app --reload --port 8080

# Production (with workers)
uvicorn support_platform.main:app --workers 4 --port 8080
```

## How to Run the Examples

```bash
# Requires all services running
docker compose up -d

# Install requirements
pip install fastapi uvicorn

# Run the API
python -m uvicorn module_09_production.examples.01_fastapi_agent:app --reload

# In another terminal, test it
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "subject": "Help!", "body": "I cannot log in"}'
```

## What's Next

Module 10 covers evaluation — how do you know if your agent is actually working? You'll build an evaluation framework and run benchmarks against the support platform.
