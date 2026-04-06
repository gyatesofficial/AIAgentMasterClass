"""
02_async_agent.py - Async Agent with asyncio
=============================================
Module 9: Production Deployment

In production, agents need to handle multiple concurrent requests efficiently.
Python's asyncio enables this without threads:
- await instead of blocking calls
- Concurrent I/O operations with asyncio.gather()
- Semaphores to limit concurrency
- Async context managers for connection pooling

Key patterns demonstrated:
1. async/await for non-blocking LLM calls
2. asyncio.gather() to run KB search + customer lookup in parallel
3. Semaphore to limit concurrent agent runs (prevent overload)
4. asyncio.wait_for() for timeouts
5. Processing a batch of tickets concurrently

Run with: python module_09_production/examples/02_async_agent.py
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Async Tool Implementations
# ──────────────────────────────────────────────────────────────

async def async_kb_search(query: str) -> dict:
    """
    Async KB search — simulates a network call to a vector DB.

    In production: async chromadb client or async HTTP request.
    The 'await asyncio.sleep()' simulates I/O wait time.
    """
    await asyncio.sleep(0.05)  # Simulate 50ms network latency

    KB = {
        "password": "Reset at login > Forgot Password. 24h link.",
        "billing": "Billing disputes: billing@example.com. Refunds: 48h.",
        "export": "Export at Settings > Export Data. Pro: 100k rows.",
        "api": "API rate limits: Free 30/min, Pro 500/min.",
    }

    for keyword, content in KB.items():
        if keyword in query.lower():
            return {"found": True, "content": content, "topic": keyword}

    return {"found": False, "content": "No specific article found.", "topic": None}


async def async_customer_lookup(email: str) -> dict:
    """
    Async customer DB lookup — simulates a database query.

    In production: asyncpg or SQLAlchemy async session.
    """
    await asyncio.sleep(0.03)  # Simulate 30ms DB query

    CUSTOMERS = {
        "alice@example.com": {"name": "Alice Smith", "plan": "Pro", "status": "active"},
        "bob@example.com": {"name": "Bob Jones", "plan": "Starter", "status": "active"},
        "charlie@example.com": {"name": "Charlie Brown", "plan": "Free", "status": "suspended"},
    }

    customer = CUSTOMERS.get(email.lower())
    return customer or {"name": "Unknown", "plan": "Free", "status": "unknown"}


async def async_llm_call(prompt: str) -> str:
    """
    Async LLM call — simulates an API call to OpenAI/Anthropic.

    In production: use the async client:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.chat.completions.create(...)
    """
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful customer support agent. Keep responses under 100 words."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=150,
            )
            return response.choices[0].message.content
        except Exception as e:
            pass

    # Fallback: simulate LLM latency + template response
    await asyncio.sleep(0.2)  # Simulate 200ms LLM call

    if "account" in prompt.lower() or "password" in prompt.lower():
        return "Please reset your password via the Forgot Password link on the login page. The link is valid for 24 hours."
    elif "billing" in prompt.lower():
        return "Our billing team will review your account within 1 business day. For urgent issues, contact billing@example.com."
    else:
        return "Thank you for reaching out. Our team will respond within 24 hours."


# ──────────────────────────────────────────────────────────────
# Pattern 1: Sequential vs Parallel Tool Calls
# ──────────────────────────────────────────────────────────────

@dataclass
class ProcessingResult:
    ticket_id: str
    kb_result: dict
    customer_info: dict
    response: str
    total_time_ms: int
    parallel: bool


async def process_ticket_sequential(ticket_id: str, subject: str, body: str, email: str) -> ProcessingResult:
    """
    Process a ticket with sequential tool calls.

    Total time = KB search time + customer lookup time + LLM time
    (all tools run one after another)
    """
    start = time.time()

    # Step 1: KB search
    kb_result = await async_kb_search(f"{subject} {body}")

    # Step 2: Customer lookup (waits for KB search to finish)
    customer_info = await async_customer_lookup(email)

    # Step 3: LLM call
    prompt = (
        f"Customer: {customer_info['name']} ({customer_info['plan']} plan)\n"
        f"Issue: {subject}\n"
        f"KB Article: {kb_result['content']}\n"
        f"Write a helpful response."
    )
    response = await async_llm_call(prompt)

    total_ms = int((time.time() - start) * 1000)
    return ProcessingResult(ticket_id, kb_result, customer_info, response, total_ms, parallel=False)


async def process_ticket_parallel(ticket_id: str, subject: str, body: str, email: str) -> ProcessingResult:
    """
    Process a ticket with parallel tool calls using asyncio.gather().

    KB search and customer lookup don't depend on each other,
    so we can run them SIMULTANEOUSLY.

    Total time = max(KB search time, customer lookup time) + LLM time
    This is typically 40-60% faster than sequential.
    """
    start = time.time()

    # Run KB search AND customer lookup at the same time
    kb_result, customer_info = await asyncio.gather(
        async_kb_search(f"{subject} {body}"),
        async_customer_lookup(email),
    )

    # LLM call still happens after (it needs the results)
    prompt = (
        f"Customer: {customer_info['name']} ({customer_info['plan']} plan)\n"
        f"Issue: {subject}\n"
        f"KB Article: {kb_result['content']}\n"
        f"Write a helpful response."
    )
    response = await async_llm_call(prompt)

    total_ms = int((time.time() - start) * 1000)
    return ProcessingResult(ticket_id, kb_result, customer_info, response, total_ms, parallel=True)


# ──────────────────────────────────────────────────────────────
# Pattern 2: Semaphore for Concurrency Control
# ──────────────────────────────────────────────────────────────

class AsyncSupportAgent:
    """
    Async agent with built-in concurrency control.

    The semaphore prevents more than MAX_CONCURRENT tickets from
    being processed at once — protecting downstream services from
    being overwhelmed.
    """

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats = {"processed": 0, "errors": 0, "total_ms": 0}

    async def process(self, ticket_id: str, subject: str, body: str, email: str) -> ProcessingResult:
        """Process a ticket, respecting the concurrency limit."""
        async with self._semaphore:
            # Only MAX_CONCURRENT tickets execute here at once
            try:
                result = await asyncio.wait_for(
                    process_ticket_parallel(ticket_id, subject, body, email),
                    timeout=30.0,  # 30-second timeout
                )
                self._stats["processed"] += 1
                self._stats["total_ms"] += result.total_time_ms
                return result
            except asyncio.TimeoutError:
                self._stats["errors"] += 1
                raise TimeoutError(f"Ticket {ticket_id} processing timed out after 30 seconds")
            except Exception as e:
                self._stats["errors"] += 1
                raise

    async def process_batch(self, tickets: list[dict]) -> list[ProcessingResult]:
        """
        Process multiple tickets concurrently.

        asyncio.gather() runs all process() coroutines at once,
        but the semaphore limits how many actually execute simultaneously.
        """
        tasks = [
            self.process(
                t["ticket_id"],
                t["subject"],
                t["body"],
                t["email"],
            )
            for t in tickets
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def stats(self) -> dict:
        processed = self._stats["processed"]
        return {
            "processed": processed,
            "errors": self._stats["errors"],
            "avg_ms": self._stats["total_ms"] / processed if processed > 0 else 0,
        }


# ──────────────────────────────────────────────────────────────
# Pattern 3: Async Context Manager for Connection Pools
# ──────────────────────────────────────────────────────────────

class MockConnectionPool:
    """
    Demonstrates async context manager pattern for resource management.

    In production: asyncpg connection pool, aiohttp ClientSession,
    or redis.asyncio connection pool.
    """

    def __init__(self, name: str, size: int = 10):
        self.name = name
        self.size = size
        self._active = False

    async def __aenter__(self):
        print(f"    [{self.name}] Opening connection pool (size={self.size})")
        await asyncio.sleep(0.01)  # Simulate connection setup
        self._active = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print(f"    [{self.name}] Closing connection pool")
        self._active = False
        return False  # Don't suppress exceptions

    async def query(self, sql: str) -> list[dict]:
        if not self._active:
            raise RuntimeError("Pool not connected")
        await asyncio.sleep(0.01)  # Simulate query
        return [{"id": 1, "result": "mock data"}]


# ──────────────────────────────────────────────────────────────
# Main Demo
# ──────────────────────────────────────────────────────────────

async def demo_sequential_vs_parallel():
    """Show the speed difference between sequential and parallel tool calls."""
    print("\n  [1] Sequential vs Parallel Tool Calls")

    ticket = {
        "id": "TKT-001",
        "subject": "Can't log in",
        "body": "I forgot my password and the reset email isn't arriving",
        "email": "alice@example.com",
    }

    # Sequential
    seq_result = await process_ticket_sequential(
        ticket["id"], ticket["subject"], ticket["body"], ticket["email"]
    )
    print(f"    Sequential: {seq_result.total_time_ms}ms")

    # Parallel
    par_result = await process_ticket_parallel(
        ticket["id"], ticket["subject"], ticket["body"], ticket["email"]
    )
    print(f"    Parallel:   {par_result.total_time_ms}ms")
    print(f"    Speedup:    {seq_result.total_time_ms / max(par_result.total_time_ms, 1):.1f}x faster")
    print(f"    Response:   {par_result.response[:80]}...")


async def demo_concurrent_batch():
    """Show concurrent batch processing with a semaphore."""
    print("\n  [2] Concurrent Batch Processing (max 3 concurrent)")

    agent = AsyncSupportAgent(max_concurrent=3)

    tickets = [
        {"ticket_id": f"TKT-{i:03d}", "subject": s, "body": b, "email": e}
        for i, (s, b, e) in enumerate([
            ("Password help", "Can't reset my password", "alice@example.com"),
            ("Billing issue", "I was charged twice this month", "bob@example.com"),
            ("Export failing", "CSV export gives an error", "charlie@example.com"),
            ("API limits", "Getting 429 errors on the API", "alice@example.com"),
            ("General question", "How do I add a team member?", "bob@example.com"),
        ], 1)
    ]

    start = time.time()
    results = await agent.process_batch(tickets)
    elapsed = int((time.time() - start) * 1000)

    successful = [r for r in results if isinstance(r, ProcessingResult)]
    errors = [r for r in results if isinstance(r, Exception)]

    print(f"    Processed {len(successful)}/{len(tickets)} tickets in {elapsed}ms")
    print(f"    (Sequential would take ~{sum(r.total_time_ms for r in successful)}ms)")
    if errors:
        print(f"    Errors: {len(errors)}")

    stats = agent.stats()
    print(f"    Avg per ticket: {stats['avg_ms']:.0f}ms")


async def demo_connection_pool():
    """Show async context manager pattern."""
    print("\n  [3] Async Connection Pool Pattern")

    async with MockConnectionPool("PostgreSQL", size=10) as pool:
        # Run multiple queries concurrently using the pool
        results = await asyncio.gather(
            pool.query("SELECT * FROM tickets LIMIT 10"),
            pool.query("SELECT COUNT(*) FROM customers"),
        )
        print(f"    Ran {len(results)} queries concurrently within the pool")


async def main():
    print("\n" + "=" * 60)
    print("  Async Agent Patterns Demo")
    print("=" * 60)

    await demo_sequential_vs_parallel()
    await demo_concurrent_batch()
    await demo_connection_pool()

    print("\n  Key async patterns demonstrated:")
    print("    - await: non-blocking I/O (LLM calls, DB queries)")
    print("    - asyncio.gather(): run independent tasks in parallel")
    print("    - asyncio.Semaphore(): limit concurrent operations")
    print("    - asyncio.wait_for(): enforce timeouts")
    print("    - async with: manage connection pools safely")


if __name__ == "__main__":
    asyncio.run(main())
