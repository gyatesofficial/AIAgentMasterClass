"""
01_token_budget.py - Planning Context Window Usage
===================================================
Module 1: LLM Foundations

The context window is a finite resource. If you don't plan your token
allocation upfront, you'll hit context limits in production at the worst
possible moment.

This module shows how to think about token budgeting BEFORE building,
and how to measure actual usage to verify your assumptions.

Run with: python module_01_llm_foundations/examples/01_token_budget.py
Requires: pip install tiktoken
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# tiktoken is OpenAI's tokenizer — use it to count tokens without an API call
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    print("Warning: tiktoken not installed. Install with: pip install tiktoken")
    TIKTOKEN_AVAILABLE = False


# ──────────────────────────────────────────────────────────────
# Model context window limits (as of 2025)
# ──────────────────────────────────────────────────────────────

MODEL_CONTEXT_WINDOWS = {
    # OpenAI
    "gpt-4o":             128_000,
    "gpt-4o-mini":        128_000,
    "gpt-4-turbo":        128_000,
    "o1":                 200_000,
    "o3-mini":            200_000,
    # Anthropic
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022":  200_000,
    "claude-opus-4-20250514":     200_000,
}

# Recommended output reservation (don't use the full window for input)
DEFAULT_OUTPUT_RESERVATION = 4_096  # tokens reserved for the model's response


# ──────────────────────────────────────────────────────────────
# Token counting
# ──────────────────────────────────────────────────────────────

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count the number of tokens in a string for a given model.

    Uses tiktoken (OpenAI's tokenizer). Claude uses a similar but not
    identical tokenizer — tiktoken counts are a good approximation.

    Args:
        text: The text to count tokens for
        model: The model name (affects which tokenizer is used)

    Returns:
        Token count as an integer
    """
    if not TIKTOKEN_AVAILABLE:
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fall back to cl100k_base for unknown models
        enc = tiktoken.get_encoding("cl100k_base")

    return len(enc.encode(text))


# ──────────────────────────────────────────────────────────────
# TokenBudget class
# ──────────────────────────────────────────────────────────────

@dataclass
class BudgetItem:
    """A single component in the token budget."""
    name: str
    allocated: int           # Maximum tokens reserved for this component
    actual: Optional[int] = None  # Tokens actually used (set after filling)
    description: str = ""


@dataclass
class TokenBudget:
    """
    Plans and tracks token allocation across all components of a prompt.

    Think of this like a budget spreadsheet for your context window.
    Before writing any code, fill this out for your agent's typical case.

    Example usage:
        budget = TokenBudget(model="gpt-4o")
        budget.add("system_prompt", 2000, "Agent instructions and persona")
        budget.add("conversation_history", 20000, "Last 10 turns")
        budget.add("kb_articles", 40000, "3 retrieved KB articles")
        budget.add("current_ticket", 5000, "The ticket being processed")
        budget.add("output", 4096, "Agent response")
        budget.print_summary()
    """

    model: str = "gpt-4o"
    items: list[BudgetItem] = field(default_factory=list)

    @property
    def context_window(self) -> int:
        """Total context window size for this model."""
        return MODEL_CONTEXT_WINDOWS.get(self.model, 128_000)

    @property
    def total_allocated(self) -> int:
        """Sum of all allocated budgets."""
        return sum(item.allocated for item in self.items)

    @property
    def total_actual(self) -> Optional[int]:
        """Sum of actual token usage (None if not yet measured)."""
        if any(item.actual is None for item in self.items):
            return None
        return sum(item.actual for item in self.items)

    @property
    def remaining_budget(self) -> int:
        """Tokens not yet allocated."""
        return self.context_window - self.total_allocated

    def add(self, name: str, tokens: int, description: str = "") -> "TokenBudget":
        """Add a component to the budget. Returns self for chaining."""
        self.items.append(BudgetItem(
            name=name,
            allocated=tokens,
            description=description,
        ))
        return self

    def measure(self, name: str, text: str) -> int:
        """
        Measure actual token usage for a component.

        Use this in your code to verify your budget assumptions:
            budget.measure("system_prompt", actual_system_prompt)
        """
        actual = count_tokens(text, self.model)
        for item in self.items:
            if item.name == name:
                item.actual = actual
                return actual
        raise ValueError(f"Budget item '{name}' not found. Call .add() first.")

    def check(self) -> list[str]:
        """
        Return a list of budget warnings.

        Check this before sending to the LLM to catch problems early.
        """
        warnings = []

        if self.total_allocated > self.context_window:
            over = self.total_allocated - self.context_window
            warnings.append(
                f"OVER BUDGET: Allocated {self.total_allocated:,} tokens "
                f"exceeds context window of {self.context_window:,} "
                f"(over by {over:,})"
            )

        if self.remaining_budget < 0:
            warnings.append(f"Negative remaining budget: {self.remaining_budget:,}")
        elif self.remaining_budget < 1_000:
            warnings.append(
                f"Very tight budget: only {self.remaining_budget:,} tokens remaining"
            )

        # Check individual items that are close to or over allocation
        for item in self.items:
            if item.actual is not None and item.actual > item.allocated:
                over = item.actual - item.allocated
                warnings.append(
                    f"'{item.name}' over allocated by {over:,} tokens "
                    f"(allocated {item.allocated:,}, actual {item.actual:,})"
                )

        return warnings

    def print_summary(self) -> None:
        """Print a formatted token budget table."""
        print(f"\n{'─' * 65}")
        print(f"  Token Budget — {self.model}")
        print(f"  Context Window: {self.context_window:,} tokens")
        print(f"{'─' * 65}")
        print(f"  {'Component':<28} {'Allocated':>10}  {'Actual':>10}  {'%':>6}")
        print(f"  {'─' * 28} {'─' * 10}  {'─' * 10}  {'─' * 6}")

        for item in self.items:
            pct = f"{(item.allocated / self.context_window * 100):.1f}%"
            actual_str = f"{item.actual:,}" if item.actual is not None else "—"
            flag = " ⚠️" if item.actual and item.actual > item.allocated else ""
            print(
                f"  {item.name:<28} {item.allocated:>10,}  {actual_str:>10}  {pct:>6}{flag}"
            )

        print(f"  {'─' * 28} {'─' * 10}  {'─' * 10}  {'─' * 6}")
        total_pct = f"{(self.total_allocated / self.context_window * 100):.1f}%"
        actual_total = f"{self.total_actual:,}" if self.total_actual else "—"
        print(f"  {'TOTAL ALLOCATED':<28} {self.total_allocated:>10,}  {actual_total:>10}  {total_pct:>6}")
        print(f"  {'REMAINING':<28} {self.remaining_budget:>10,}")
        print(f"{'─' * 65}")

        warnings = self.check()
        if warnings:
            print(f"\n  ⚠️  Warnings:")
            for w in warnings:
                print(f"     {w}")
        else:
            print(f"\n  ✓ Budget looks healthy")


# ──────────────────────────────────────────────────────────────
# Example: Support Agent Token Budget
# ──────────────────────────────────────────────────────────────

def example_support_agent_budget():
    """
    Design the token budget for our support platform's triage agent.

    This is the FIRST thing you should do when designing a new agent —
    before writing any code. It forces you to think about what information
    the agent actually needs and whether it'll fit.
    """
    print("\n" + "=" * 65)
    print("  EXAMPLE 1: Support Triage Agent Token Budget")
    print("=" * 65)

    budget = TokenBudget(model="gpt-4o")

    # Plan each component
    budget.add("system_prompt",          2_000,  "Agent persona, rules, output format")
    budget.add("conversation_history",  10_000,  "Last 5 turns of chat history")
    budget.add("kb_articles",           40_000,  "3 retrieved KB articles (~3,000 words each)")
    budget.add("customer_profile",       1_000,  "Name, tier, account status, notes")
    budget.add("ticket_history",         5_000,  "Customer's last 5 tickets, summaries")
    budget.add("current_ticket",         2_000,  "Subject + body of ticket being triaged")
    budget.add("output_reservation",     4_096,  "Reserved for model's response")

    budget.print_summary()

    # Now measure actual token counts for real content
    print("\n  Measuring actual token counts for realistic content...")
    SAMPLE_SYSTEM_PROMPT = """You are an expert customer support triage agent for a SaaS platform.
Your job is to:
1. Classify the support ticket into one of: account_access, billing, technical_bug, feature_request, general_inquiry
2. Assign a priority: low, medium, high, critical
3. Determine if you can auto-resolve the ticket or need to escalate

Rules:
- Always search the knowledge base before responding
- For billing issues over $100, always escalate to a human
- Critical tickets (system down, data loss) must be escalated immediately
- Never promise refunds without manager approval

Respond in JSON format with fields: category, priority, can_auto_resolve, reasoning, response_draft"""

    SAMPLE_KB_ARTICLE = """## How to Reset Your Password

If you've forgotten your password, follow these steps:
1. Go to the login page and click "Forgot Password"
2. Enter your email address
3. Check your inbox for a reset link (check spam if not received)
4. Click the link — it expires after 24 hours
5. Enter and confirm your new password

Password Requirements: 8+ characters, 1 uppercase, 1 number.
Account Lock: Accounts lock after 5 failed attempts. Auto-unlocks in 30 minutes.
""" * 3  # Simulate 3 articles

    SAMPLE_TICKET = """Subject: Can't log in after updating my phone
I updated my iPhone yesterday and now I can't log in with 2FA. The codes from my old authenticator app don't work anymore. I've tried 5 times and now it says my account is locked. I have an important demo in 2 hours and need access urgently. My email is sarah@techcorp.com"""

    # Measure actual usage
    budget.measure("system_prompt", SAMPLE_SYSTEM_PROMPT)
    budget.measure("kb_articles", SAMPLE_KB_ARTICLE)
    budget.measure("current_ticket", SAMPLE_TICKET)

    print("\n  After measuring actual content:")
    budget.print_summary()


def example_budget_too_small():
    """
    Show what happens when you try to put too much in the context window.
    This is a common mistake — catching it early saves production incidents.
    """
    print("\n" + "=" * 65)
    print("  EXAMPLE 2: Over-Budget Warning")
    print("=" * 65)

    # gpt-4o-mini has 128k context but let's demonstrate the warning
    budget = TokenBudget(model="gpt-4o-mini")
    budget.add("system_prompt",        2_000)
    budget.add("full_conversation",   50_000,  "Full conversation history (mistake!)")
    budget.add("all_kb_articles",     80_000,  "ALL 50 KB articles (mistake!)")
    budget.add("customer_data",        5_000)
    budget.add("output",               4_096)

    budget.print_summary()
    print("\n  Fix: Use windowed conversation history + RAG instead of full KB dump")


def example_context_strategies():
    """
    Compare different strategies for fitting information in the context window.
    """
    print("\n" + "=" * 65)
    print("  EXAMPLE 3: Context Management Strategies")
    print("=" * 65)

    # Strategy 1: Naive (dump everything)
    print("\n  Strategy A: Naive — Include everything")
    print("  Problem: Will hit context limits for heavy users")
    budget_naive = TokenBudget(model="gpt-4o")
    budget_naive.add("system_prompt",        2_000)
    budget_naive.add("full_history",        50_000,  "Full conversation history")
    budget_naive.add("all_kb_articles",     80_000,  "All KB articles")
    budget_naive.print_summary()

    # Strategy 2: Smart (use RAG + windowing)
    print("\n  Strategy B: Smart — RAG + windowing")
    print("  Fix: Only include relevant KB articles and last N turns")
    budget_smart = TokenBudget(model="gpt-4o")
    budget_smart.add("system_prompt",        2_000,  "Instructions")
    budget_smart.add("windowed_history",    10_000,  "Last 5 turns only")
    budget_smart.add("rag_kb_articles",     15_000,  "Top-3 relevant articles (RAG)")
    budget_smart.add("customer_context",     2_000,  "Key customer info")
    budget_smart.add("current_ticket",       2_000,  "Current ticket")
    budget_smart.add("output",               4_096,  "Response")
    budget_smart.print_summary()

    print("\n  Smart strategy uses 27% of context vs 103% for naive approach")
    print("  This leaves room for complex tickets and long KB articles")


if __name__ == "__main__":
    example_support_agent_budget()
    example_budget_too_small()
    example_context_strategies()

    print("\n" + "=" * 65)
    print("  Key Takeaways")
    print("=" * 65)
    print("""
  1. Plan your token budget BEFORE writing agent code
  2. Reserve tokens for output (model can't respond if context is full)
  3. Use RAG instead of dumping your whole KB into the context
  4. Use windowed history instead of full conversation history
  5. Measure actual token counts — your estimates are usually wrong
  6. Add budget.check() to your agent's pre-flight validation
    """)
