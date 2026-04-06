"""
03_cost_guardrails.py - Cost Controls & Circuit Breakers
=========================================================
Module 11: Safety & Guardrails

LLM agents can run up unexpected costs if not properly controlled:
- Infinite loops calling tools repeatedly
- Accidentally processing millions of tickets
- Runaway background jobs
- Prompt injection causing expensive operations

This file implements:
1. Iteration limits — stop agents that loop too long
2. Token budget enforcement — cap spending per request
3. Cost circuit breaker — pause when spending spikes
4. Daily budget limits — hard cap on total spending
5. Cost estimation before running expensive operations

Run with: python module_11_safety/examples/03_cost_guardrails.py
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Cost Models
# ──────────────────────────────────────────────────────────────

# OpenAI pricing (approximate, check openai.com/pricing for current rates)
MODEL_COSTS = {
    "gpt-4o": {"input": 5.00, "output": 15.00},           # per 1M tokens
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate the cost in USD for an LLM call."""
    pricing = MODEL_COSTS.get(model, MODEL_COSTS["gpt-4o-mini"])
    cost = (
        (input_tokens / 1_000_000) * pricing["input"] +
        (output_tokens / 1_000_000) * pricing["output"]
    )
    return round(cost, 6)


# ──────────────────────────────────────────────────────────────
# Guardrail 1: Iteration Limit
# ──────────────────────────────────────────────────────────────

class IterationLimitError(Exception):
    """Raised when an agent exceeds its allowed iterations."""
    pass


class IterationGuard:
    """
    Prevents agent loops from running indefinitely.

    An agent that loops 50+ times is almost certainly stuck.
    This guard raises an error when the limit is exceeded.

    Usage:
        guard = IterationGuard(max_iterations=10)
        while True:
            guard.tick()  # Raises after 10 iterations
            result = agent.step()
            if result.done:
                break
    """

    def __init__(self, max_iterations: int = 10, agent_id: str = "agent"):
        self.max_iterations = max_iterations
        self.agent_id = agent_id
        self._count = 0
        self._start_time = time.time()

    def tick(self, step_description: str = ""):
        """Record one iteration. Raises IterationLimitError if exceeded."""
        self._count += 1
        if self._count > self.max_iterations:
            elapsed = time.time() - self._start_time
            raise IterationLimitError(
                f"Agent '{self.agent_id}' exceeded {self.max_iterations} iterations "
                f"(ran {elapsed:.1f}s). Last step: {step_description}"
            )

    @property
    def iterations_used(self) -> int:
        return self._count

    @property
    def iterations_remaining(self) -> int:
        return max(0, self.max_iterations - self._count)


# ──────────────────────────────────────────────────────────────
# Guardrail 2: Token Budget
# ──────────────────────────────────────────────────────────────

@dataclass
class TokenBudget:
    """
    Tracks token usage for a single agent run.

    Sets a hard limit on how many tokens can be consumed in one request.
    Prevents accidental runaway costs from very long context windows.
    """
    max_tokens: int
    model: str = "gpt-4o-mini"
    _used_input: int = 0
    _used_output: int = 0

    @property
    def total_used(self) -> int:
        return self._used_input + self._used_output

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.total_used)

    @property
    def cost_so_far(self) -> float:
        return estimate_cost(self.model, self._used_input, self._used_output)

    def consume(self, input_tokens: int, output_tokens: int):
        """Record token usage from one LLM call."""
        if self.total_used + input_tokens + output_tokens > self.max_tokens:
            raise BudgetExceededError(
                f"Token budget exceeded: {self.total_used + input_tokens + output_tokens} > {self.max_tokens}"
            )
        self._used_input += input_tokens
        self._used_output += output_tokens

    def can_afford(self, input_tokens: int, estimated_output: int = 500) -> bool:
        """Check if we can afford another LLM call without raising."""
        return self.total_used + input_tokens + estimated_output <= self.max_tokens


class BudgetExceededError(Exception):
    """Raised when a token or cost budget is exceeded."""
    pass


# ──────────────────────────────────────────────────────────────
# Guardrail 3: Cost Circuit Breaker
# ──────────────────────────────────────────────────────────────

class CostCircuitBreaker:
    """
    Trips when spending rate exceeds a threshold.

    Inspired by electrical circuit breakers: when current (cost) exceeds
    a safe level, the breaker trips (opens) to prevent damage.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too much spending, requests are blocked
    - HALF_OPEN: Recovery mode, limited requests allowed to test

    The circuit opens when the rolling window spend exceeds the limit.
    It can be reset manually or automatically after a cooldown period.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        max_spend_per_window: float,     # Max dollars in the window
        window_seconds: int = 300,        # Rolling window duration (5 min)
        cooldown_seconds: int = 60,       # How long to stay open before half-open
        failure_threshold: int = 3,       # Consecutive failures to trip
    ):
        self.max_spend_per_window = max_spend_per_window
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.failure_threshold = failure_threshold

        self._state = self.CLOSED
        self._spend_window: deque = deque()  # (timestamp, cost) pairs
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._lock = Lock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == self.OPEN

    def _current_window_spend(self, now: float) -> float:
        """Calculate total spend in the current rolling window."""
        cutoff = now - self.window_seconds
        while self._spend_window and self._spend_window[0][0] < cutoff:
            self._spend_window.popleft()
        return sum(cost for _, cost in self._spend_window)

    def can_proceed(self) -> tuple[bool, str]:
        """Check if a new LLM call should be allowed."""
        with self._lock:
            now = time.time()

            if self._state == self.CLOSED:
                window_spend = self._current_window_spend(now)
                if window_spend >= self.max_spend_per_window:
                    self._state = self.OPEN
                    self._opened_at = now
                    return False, f"Circuit OPENED: ${window_spend:.3f} in {self.window_seconds}s window"
                return True, "Circuit closed — request allowed"

            elif self._state == self.OPEN:
                # Check if cooldown has elapsed
                if self._opened_at and (now - self._opened_at) >= self.cooldown_seconds:
                    self._state = self.HALF_OPEN
                    return True, "Circuit HALF-OPEN — testing recovery"
                elapsed = now - self._opened_at
                return False, f"Circuit OPEN — retry in {self.cooldown_seconds - elapsed:.0f}s"

            elif self._state == self.HALF_OPEN:
                # Allow one request through to test
                return True, "Circuit half-open — allowing test request"

            return False, "Unknown circuit state"

    def record_success(self, cost: float):
        """Record a successful (non-excessive) call."""
        with self._lock:
            now = time.time()
            self._spend_window.append((now, cost))
            self._consecutive_failures = 0
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                print("    Circuit CLOSED — recovery successful")

    def record_failure(self):
        """Record a failed or over-budget call."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                if self._state != self.OPEN:
                    self._state = self.OPEN
                    self._opened_at = time.time()

    def reset(self):
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = self.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._spend_window.clear()


# ──────────────────────────────────────────────────────────────
# Guardrail 4: Daily Budget Limiter
# ──────────────────────────────────────────────────────────────

class DailyBudgetLimiter:
    """
    Enforces a hard daily spending cap.

    When the daily budget is exhausted:
    - Expensive models (GPT-4o) are blocked
    - Cheap models (GPT-4o-mini) may still be allowed
    - New requests queue for the next day

    This prevents a runaway job from spending $1000 in a day.
    """

    def __init__(
        self,
        daily_budget_usd: float,
        cheap_model_threshold: float = 0.001,  # Under this cost = "cheap"
    ):
        self.daily_budget_usd = daily_budget_usd
        self.cheap_model_threshold = cheap_model_threshold
        self._today_spend = 0.0
        self._today_date = datetime.now(timezone.utc).date()
        self._lock = Lock()

    def _check_day_rollover(self):
        """Reset spend counter at midnight UTC."""
        today = datetime.now(timezone.utc).date()
        if today != self._today_date:
            self._today_spend = 0.0
            self._today_date = today

    def can_proceed(self, estimated_cost: float) -> tuple[bool, str]:
        """Check if a request with estimated cost can proceed."""
        with self._lock:
            self._check_day_rollover()

            remaining = self.daily_budget_usd - self._today_spend
            is_cheap = estimated_cost <= self.cheap_model_threshold

            if self._today_spend + estimated_cost > self.daily_budget_usd:
                if is_cheap:
                    # Allow cheap models even when budget is tight
                    return True, f"Budget tight (${remaining:.3f} left) but request is cheap"
                return False, (
                    f"Daily budget exceeded: ${self._today_spend:.3f}/${self.daily_budget_usd}. "
                    f"Resets at midnight UTC."
                )

            return True, f"${remaining:.3f} remaining today"

    def record_spend(self, cost: float):
        """Record actual spend after a call completes."""
        with self._lock:
            self._check_day_rollover()
            self._today_spend += cost

    @property
    def today_spend(self) -> float:
        with self._lock:
            self._check_day_rollover()
            return self._today_spend


# ──────────────────────────────────────────────────────────────
# Combined Cost Guard
# ──────────────────────────────────────────────────────────────

class CostGuard:
    """
    Combines all cost guardrails into a single interface.

    Use this as a wrapper around every LLM call in your agent.
    """

    def __init__(
        self,
        daily_budget: float = 10.0,
        max_per_window: float = 1.0,
        window_seconds: int = 300,
        default_max_iterations: int = 10,
    ):
        self.daily = DailyBudgetLimiter(daily_budget)
        self.circuit = CostCircuitBreaker(max_per_window, window_seconds)
        self.default_max_iterations = default_max_iterations

    def check_before_call(
        self,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int = 500,
    ) -> tuple[bool, str]:
        """
        Run all pre-call cost checks.

        Call this BEFORE every LLM call.
        Returns (allowed, reason).
        """
        estimated_cost = estimate_cost(model, estimated_input_tokens, estimated_output_tokens)

        # Check circuit breaker
        allowed, reason = self.circuit.can_proceed()
        if not allowed:
            return False, f"Circuit breaker: {reason}"

        # Check daily budget
        allowed, reason = self.daily.can_proceed(estimated_cost)
        if not allowed:
            return False, f"Daily budget: {reason}"

        return True, f"Allowed (estimated cost: ${estimated_cost:.5f})"

    def record_call(self, model: str, actual_input_tokens: int, actual_output_tokens: int):
        """
        Record actual usage after a call completes.

        Call this AFTER every successful LLM call.
        """
        cost = estimate_cost(model, actual_input_tokens, actual_output_tokens)
        self.circuit.record_success(cost)
        self.daily.record_spend(cost)

    def new_iteration_guard(self, agent_id: str = "agent") -> IterationGuard:
        """Create a new iteration guard for an agent run."""
        return IterationGuard(self.default_max_iterations, agent_id)


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def demo_iteration_guard():
    """Demonstrate iteration limits."""
    print("\n  [1] Iteration Limit Guard")

    guard = IterationGuard(max_iterations=5, agent_id="triage_agent")

    try:
        for i in range(10):  # Would loop forever without guard
            guard.tick(f"Processing step {i+1}")
            print(f"    Step {i+1}: {guard.iterations_remaining} iterations remaining")
    except IterationLimitError as e:
        print(f"    BLOCKED: {e}")


def demo_token_budget():
    """Demonstrate token budget enforcement."""
    print("\n  [2] Token Budget Enforcement")

    budget = TokenBudget(max_tokens=1000, model="gpt-4o-mini")

    calls = [
        (200, 300),   # Will succeed
        (150, 200),   # Will succeed
        (200, 200),   # Will exceed budget
    ]

    for i, (inp, out) in enumerate(calls, 1):
        if budget.can_afford(inp, out):
            budget.consume(inp, out)
            print(f"    Call {i}: {inp}+{out} tokens consumed (${budget.cost_so_far:.5f} so far)")
        else:
            print(f"    Call {i}: BLOCKED — would exceed budget ({budget.total_used}/{budget.max_tokens} used)")


def demo_circuit_breaker():
    """Demonstrate circuit breaker behavior."""
    print("\n  [3] Cost Circuit Breaker")

    breaker = CostCircuitBreaker(
        max_spend_per_window=0.005,  # $0.005 limit for demo
        window_seconds=10,
        cooldown_seconds=2,
    )

    # Simulate several API calls
    for i in range(6):
        allowed, reason = breaker.can_proceed()
        if allowed:
            # Simulate a call costing $0.002
            cost = 0.002
            breaker.record_success(cost)
            print(f"    Call {i+1}: allowed (state: {breaker.state})")
        else:
            print(f"    Call {i+1}: BLOCKED — {reason}")

        time.sleep(0.1)


def demo_daily_budget():
    """Demonstrate daily budget limit."""
    print("\n  [4] Daily Budget Limiter")

    limiter = DailyBudgetLimiter(daily_budget_usd=0.01)

    call_costs = [0.003, 0.003, 0.003, 0.005, 0.001]
    for i, cost in enumerate(call_costs, 1):
        allowed, reason = limiter.can_proceed(cost)
        if allowed:
            limiter.record_spend(cost)
            print(f"    Call {i} (${cost:.3f}): allowed — {reason}")
        else:
            print(f"    Call {i} (${cost:.3f}): BLOCKED — {reason}")


def main():
    print("\n" + "=" * 60)
    print("  Cost Guardrails & Circuit Breakers Demo")
    print("=" * 60)

    demo_iteration_guard()
    demo_token_budget()
    demo_circuit_breaker()
    demo_daily_budget()

    print("\n  Cost guardrail hierarchy:")
    print("    Per-call: Token budget (cap tokens per request)")
    print("    Per-agent: Iteration guard (cap loop iterations)")
    print("    Per-window: Circuit breaker (rate of spend)")
    print("    Per-day: Daily budget (absolute $ cap)")
    print()
    print("  Production recommendation:")
    print("    Set daily_budget = monthly_budget / 30")
    print("    Set window_limit = daily_budget / 48 (half-hour chunks)")
    print("    Set iteration_limit = 10-15 for most agents")
    print("    Alert (don't just block) when hitting 80% of limits")


if __name__ == "__main__":
    main()
