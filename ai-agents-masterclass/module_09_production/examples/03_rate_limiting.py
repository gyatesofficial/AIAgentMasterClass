"""
03_rate_limiting.py - Rate Limiting for Production Agents
==========================================================
Module 9: Production Deployment

Rate limiting protects your agent API from:
- Abuse (too many requests from one client)
- Cost overruns (LLM calls are expensive)
- Overloading downstream services

Three rate limiting strategies demonstrated:
1. Fixed Window — simplest, allows burst at window boundaries
2. Sliding Window — smoother, prevents boundary bursts
3. Token Bucket — allows controlled bursting, best for APIs

Also shows:
- Per-client (IP/API key) limits
- Global system limits
- Cost-based rate limiting (track spend, not just requests)

Run with: python module_09_production/examples/03_rate_limiting.py
"""

from __future__ import annotations

import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Strategy 1: Fixed Window Rate Limiter
# ──────────────────────────────────────────────────────────────

class FixedWindowRateLimiter:
    """
    Fixed Window: count requests in fixed time windows.

    Simple and memory-efficient, but allows "burst" at window boundaries:
    - Window: 0-60s
    - Limit: 10 requests
    - Problem: 10 requests at t=59s + 10 at t=61s = 20 in 2 seconds

    Best for: internal services where burst is acceptable.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counts: dict[str, dict] = {}  # {client_id: {"count": n, "window_start": t}}
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        """
        Check if a request is allowed.

        Returns (allowed: bool, info: dict with limit details).
        """
        with self._lock:
            now = time.time()
            window_start = now - (now % self.window_seconds)

            if client_id not in self._counts:
                self._counts[client_id] = {"count": 0, "window_start": window_start}

            state = self._counts[client_id]

            # Reset if we're in a new window
            if state["window_start"] < window_start:
                state["count"] = 0
                state["window_start"] = window_start

            state["count"] += 1
            allowed = state["count"] <= self.max_requests

            return allowed, {
                "strategy": "fixed_window",
                "limit": self.max_requests,
                "remaining": max(0, self.max_requests - state["count"]),
                "reset_in": self.window_seconds - (now % self.window_seconds),
            }


# ──────────────────────────────────────────────────────────────
# Strategy 2: Sliding Window Rate Limiter
# ──────────────────────────────────────────────────────────────

class SlidingWindowRateLimiter:
    """
    Sliding Window: track timestamps of recent requests.

    More accurate than fixed window — no burst at boundaries.
    Uses a deque to store request timestamps for each client.

    Tradeoff: uses more memory (stores all request timestamps).
    Best for: customer-facing APIs where fair limits matter.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, dict]:
        with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Remove timestamps older than the window
            requests = self._requests[client_id]
            while requests and requests[0] < window_start:
                requests.popleft()

            count = len(requests)
            allowed = count < self.max_requests

            if allowed:
                requests.append(now)

            # Calculate when oldest request expires
            reset_in = (requests[0] + self.window_seconds - now) if requests else 0

            return allowed, {
                "strategy": "sliding_window",
                "limit": self.max_requests,
                "current": count + (1 if allowed else 0),
                "remaining": max(0, self.max_requests - count - (1 if allowed else 0)),
                "reset_in": round(reset_in, 1),
            }


# ──────────────────────────────────────────────────────────────
# Strategy 3: Token Bucket Rate Limiter
# ──────────────────────────────────────────────────────────────

class TokenBucketRateLimiter:
    """
    Token Bucket: tokens refill continuously at a steady rate.

    - Bucket starts full (capacity tokens)
    - Each request costs 1 token
    - Tokens refill at rate per second
    - Allows burst up to capacity, then enforces sustained rate

    Example: capacity=10, rate=1/s
    - Can burst 10 requests immediately
    - After burst, limited to 1 request/second
    - Unused capacity accumulates up to bucket size

    Best for: APIs that need to allow short bursts (e.g., user typing)
    but enforce a long-term average rate.
    """

    def __init__(self, capacity: float, refill_rate: float):
        """
        Args:
            capacity: Maximum tokens (burst size)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: dict[str, dict] = {}
        self._lock = Lock()

    def _get_bucket(self, client_id: str) -> dict:
        if client_id not in self._buckets:
            self._buckets[client_id] = {
                "tokens": self.capacity,
                "last_refill": time.time(),
            }
        return self._buckets[client_id]

    def is_allowed(self, client_id: str, cost: float = 1.0) -> tuple[bool, dict]:
        """
        Check if request is allowed, consuming 'cost' tokens.

        Cost can vary: simple queries cost 1, complex queries cost 5.
        """
        with self._lock:
            now = time.time()
            bucket = self._get_bucket(client_id)

            # Refill tokens based on elapsed time
            elapsed = now - bucket["last_refill"]
            refill_amount = elapsed * self.refill_rate
            bucket["tokens"] = min(self.capacity, bucket["tokens"] + refill_amount)
            bucket["last_refill"] = now

            # Check if we have enough tokens
            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                allowed = True
            else:
                allowed = False

            # Time until enough tokens are available
            if not allowed:
                wait_time = (cost - bucket["tokens"]) / self.refill_rate
            else:
                wait_time = 0.0

            return allowed, {
                "strategy": "token_bucket",
                "capacity": self.capacity,
                "tokens_remaining": round(bucket["tokens"], 2),
                "refill_rate": f"{self.refill_rate}/s",
                "wait_seconds": round(wait_time, 2),
            }


# ──────────────────────────────────────────────────────────────
# Cost-Based Rate Limiter
# ──────────────────────────────────────────────────────────────

@dataclass
class CostTracker:
    """
    Track API cost per client per time period.

    Instead of counting requests, track dollars spent.
    This is more meaningful for LLM APIs where costs vary by model/tokens.
    """
    max_cost_per_hour: float  # Maximum dollars per hour
    max_cost_per_day: float   # Maximum dollars per day

    _hourly: dict = field(default_factory=lambda: defaultdict(list))
    _daily: dict = field(default_factory=lambda: defaultdict(list))
    _lock: Lock = field(default_factory=Lock)

    def record_cost(self, client_id: str, cost_usd: float) -> tuple[bool, dict]:
        """
        Record an API call cost and check if limits are exceeded.

        Returns (within_limits, info_dict).
        """
        with self._lock:
            now = time.time()
            hour_ago = now - 3600
            day_ago = now - 86400

            # Add new cost record
            self._hourly[client_id].append((now, cost_usd))
            self._daily[client_id].append((now, cost_usd))

            # Clean old records
            self._hourly[client_id] = [
                (t, c) for t, c in self._hourly[client_id] if t > hour_ago
            ]
            self._daily[client_id] = [
                (t, c) for t, c in self._daily[client_id] if t > day_ago
            ]

            # Calculate totals
            hourly_total = sum(c for _, c in self._hourly[client_id])
            daily_total = sum(c for _, c in self._daily[client_id])

            within_limits = (
                hourly_total <= self.max_cost_per_hour and
                daily_total <= self.max_cost_per_day
            )

            return within_limits, {
                "hourly_cost": round(hourly_total, 4),
                "hourly_limit": self.max_cost_per_hour,
                "daily_cost": round(daily_total, 4),
                "daily_limit": self.max_cost_per_day,
                "within_limits": within_limits,
            }


# ──────────────────────────────────────────────────────────────
# FastAPI Middleware Integration
# ──────────────────────────────────────────────────────────────

def create_rate_limit_middleware(limiter: SlidingWindowRateLimiter):
    """
    Create a FastAPI middleware that applies rate limiting.

    Usage:
        app = FastAPI()
        limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60)
        app.middleware("http")(create_rate_limit_middleware(limiter))
    """
    async def rate_limit_middleware(request, call_next):
        # Identify client by IP (use API key in production)
        client_id = request.client.host if request.client else "unknown"

        allowed, info = limiter.is_allowed(client_id)

        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {info['limit']} per {60}s",
                    "retry_after": info.get("reset_in", 60),
                },
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": str(info["remaining"]),
                    "Retry-After": str(int(info.get("reset_in", 60))),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to all responses
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])

        return response

    return rate_limit_middleware


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def demo_rate_limiters():
    """Demonstrate all three rate limiting strategies."""

    print("\n  [1] Fixed Window (3 requests per 10 seconds)")
    limiter = FixedWindowRateLimiter(max_requests=3, window_seconds=10)
    for i in range(5):
        allowed, info = limiter.is_allowed("client_a")
        status = "✓" if allowed else "✗"
        print(f"    Request {i+1}: {status} (remaining: {info['remaining']})")

    print("\n  [2] Sliding Window (3 requests per 10 seconds)")
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=10)
    for i in range(5):
        allowed, info = limiter.is_allowed("client_b")
        status = "✓" if allowed else "✗"
        print(f"    Request {i+1}: {status} (remaining: {info['remaining']}, reset_in: {info['reset_in']}s)")

    print("\n  [3] Token Bucket (capacity=3, refill=1/s)")
    limiter = TokenBucketRateLimiter(capacity=3, refill_rate=1.0)
    for i in range(5):
        allowed, info = limiter.is_allowed("client_c")
        status = "✓" if allowed else "✗"
        print(f"    Request {i+1}: {status} (tokens: {info['tokens_remaining']}, wait: {info['wait_seconds']}s)")

    print("\n  [4] Cost-Based Limiting ($0.01/hr limit)")
    tracker = CostTracker(max_cost_per_hour=0.01, max_cost_per_day=0.10)
    costs = [0.003, 0.004, 0.005, 0.002]  # Simulated API call costs
    for i, cost in enumerate(costs):
        within, info = tracker.record_cost("client_d", cost)
        status = "✓" if within else "✗"
        print(f"    Call {i+1} (${cost:.3f}): {status} (hourly: ${info['hourly_cost']:.3f}/${info['hourly_limit']})")

    print("\n  [5] Multiple Clients with Sliding Window")
    shared = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    clients = ["alice", "bob", "alice", "charlie", "alice"]
    for client in clients:
        allowed, info = shared.is_allowed(client)
        status = "✓" if allowed else "✗"
        print(f"    {client}: {status} (remaining: {info['remaining']})")


def main():
    print("\n" + "=" * 60)
    print("  Rate Limiting Patterns Demo")
    print("=" * 60)

    demo_rate_limiters()

    print("\n  Rate limiting strategies comparison:")
    print("  ─────────────────────────────────────")
    print("  Fixed Window:    Simple, memory-efficient, allows boundary bursts")
    print("  Sliding Window:  Fair, smooth, slightly more memory usage")
    print("  Token Bucket:    Allows bursting, enforces sustained rate")
    print("  Cost-Based:      Track $ spent instead of requests (LLM-specific)")
    print()
    print("  Production recommendation:")
    print("    - Use Sliding Window for per-user API limits")
    print("    - Use Token Bucket for burst-friendly public APIs")
    print("    - Use Cost Tracker alongside request limits for LLM agents")
    print("    - Store rate limit state in Redis for multi-instance deployments")


if __name__ == "__main__":
    main()
