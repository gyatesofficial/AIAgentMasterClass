"""
02_cost_estimator.py - LLM Cost Estimation
==========================================
Module 1: LLM Foundations

Before committing to a model, estimate what it will cost you.
A model that's 2x more accurate but 10x more expensive might not
be the right choice at scale.

This module shows how to:
1. Calculate cost for a single LLM call
2. Estimate cost per agent run
3. Project monthly costs at various traffic levels
4. Compare models for cost efficiency

Run with: python module_01_llm_foundations/examples/02_cost_estimator.py
"""

from __future__ import annotations

from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────
# Pricing data (USD per 1M tokens, as of April 2025)
# Check current prices at: https://openai.com/pricing and https://anthropic.com/pricing
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ModelPricing:
    """Pricing for a single model."""
    model_id: str
    display_name: str
    input_per_million: float    # USD per 1M input tokens
    output_per_million: float   # USD per 1M output tokens
    context_window: int         # Max tokens
    notes: str = ""

    def cost_for_tokens(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for a given number of tokens."""
        input_cost = (input_tokens / 1_000_000) * self.input_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_per_million
        return input_cost + output_cost


# Current pricing as of April 2025 — update these as prices change!
MODEL_PRICING: dict[str, ModelPricing] = {
    # ── OpenAI ──────────────────────────────────────────────
    "gpt-4o": ModelPricing(
        model_id="gpt-4o",
        display_name="GPT-4o",
        input_per_million=2.50,
        output_per_million=10.00,
        context_window=128_000,
        notes="Best reasoning, flagship model",
    ),
    "gpt-4o-mini": ModelPricing(
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        input_per_million=0.15,
        output_per_million=0.60,
        context_window=128_000,
        notes="Great for simple tasks, very cheap",
    ),
    "o3-mini": ModelPricing(
        model_id="o3-mini",
        display_name="o3-mini",
        input_per_million=1.10,
        output_per_million=4.40,
        context_window=200_000,
        notes="Reasoning model, good for complex analysis",
    ),
    # ── Anthropic ───────────────────────────────────────────
    "claude-opus-4-20250514": ModelPricing(
        model_id="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        input_per_million=15.00,
        output_per_million=75.00,
        context_window=200_000,
        notes="Most capable, most expensive",
    ),
    "claude-sonnet-4-20250514": ModelPricing(
        model_id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        input_per_million=3.00,
        output_per_million=15.00,
        context_window=200_000,
        notes="Balanced performance and cost",
    ),
    "claude-3-5-haiku-20241022": ModelPricing(
        model_id="claude-3-5-haiku-20241022",
        display_name="Claude Haiku 3.5",
        input_per_million=0.80,
        output_per_million=4.00,
        context_window=200_000,
        notes="Fast and cheap, good for simple tasks",
    ),
}


# ──────────────────────────────────────────────────────────────
# CostEstimator class
# ──────────────────────────────────────────────────────────────

@dataclass
class AgentRunProfile:
    """
    Describes the token usage of a typical agent run.
    Fill this in based on your use case.
    """
    name: str
    # Typical token counts for one agent execution
    system_prompt_tokens: int = 2_000
    conversation_tokens: int = 5_000
    kb_context_tokens: int = 10_000
    customer_data_tokens: int = 500
    ticket_tokens: int = 500
    output_tokens: int = 800
    # Number of LLM calls per run (multi-step agents make multiple calls)
    llm_calls_per_run: int = 2

    @property
    def input_tokens_per_call(self) -> int:
        """Total input tokens for each LLM call."""
        return (
            self.system_prompt_tokens
            + self.conversation_tokens
            + self.kb_context_tokens
            + self.customer_data_tokens
            + self.ticket_tokens
        )

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens across all LLM calls in one agent run."""
        return self.input_tokens_per_call * self.llm_calls_per_run

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens across all LLM calls in one agent run."""
        return self.output_tokens * self.llm_calls_per_run


class CostEstimator:
    """
    Estimates LLM costs for an agent system.

    Useful for:
    - Choosing between models
    - Setting per-request cost limits
    - Projecting monthly spend
    - Building cost alerts
    """

    def __init__(self, pricing: dict[str, ModelPricing] = None):
        self.pricing = pricing or MODEL_PRICING

    def cost_per_run(self, model_id: str, profile: AgentRunProfile) -> float:
        """
        Calculate the cost of one agent run.

        Args:
            model_id: Model identifier (must be in self.pricing)
            profile: Token usage profile for a typical run

        Returns:
            Cost in USD
        """
        if model_id not in self.pricing:
            raise ValueError(f"Unknown model: {model_id}. Available: {list(self.pricing.keys())}")

        pricing = self.pricing[model_id]
        return pricing.cost_for_tokens(
            input_tokens=profile.total_input_tokens,
            output_tokens=profile.total_output_tokens,
        )

    def monthly_cost(
        self,
        model_id: str,
        profile: AgentRunProfile,
        tickets_per_day: int,
        cache_hit_rate: float = 0.0,
        batch_discount: float = 0.0,
    ) -> dict:
        """
        Project monthly costs.

        Args:
            model_id: Model to use
            profile: Token usage profile
            tickets_per_day: Volume estimate
            cache_hit_rate: Fraction of requests served from cache (0.0 - 1.0)
            batch_discount: Discount from batch processing (e.g., 0.5 for 50% off)

        Returns:
            Dict with daily/monthly cost breakdowns
        """
        base_cost = self.cost_per_run(model_id, profile)

        # Effective cost per run accounting for caching and batching
        effective_cost = base_cost * (1 - cache_hit_rate) * (1 - batch_discount)

        daily_cost = effective_cost * tickets_per_day
        monthly_cost = daily_cost * 30

        # Cost if we'd used the cheapest model
        cheapest_id = min(
            self.pricing.keys(),
            key=lambda m: self.pricing[m].cost_for_tokens(
                profile.total_input_tokens, profile.total_output_tokens
            ),
        )
        cheapest_cost = self.cost_per_run(cheapest_id, profile)
        monthly_at_cheapest = cheapest_cost * (1 - cache_hit_rate) * tickets_per_day * 30

        return {
            "model": model_id,
            "base_cost_per_run": base_cost,
            "effective_cost_per_run": effective_cost,
            "daily_cost": daily_cost,
            "monthly_cost": monthly_cost,
            "cache_hit_rate": cache_hit_rate,
            "tickets_per_day": tickets_per_day,
            "monthly_at_cheapest_model": monthly_at_cheapest,
            "potential_savings_switching": monthly_cost - monthly_at_cheapest,
        }

    def compare_models(
        self,
        profile: AgentRunProfile,
        tickets_per_day: int = 1_000,
    ) -> None:
        """Print a comparison table for all models."""
        print(f"\n{'=' * 80}")
        print(f"  Model Cost Comparison — {profile.name}")
        print(f"  Token usage per run: {profile.total_input_tokens:,} input + {profile.total_output_tokens:,} output")
        print(f"  Volume: {tickets_per_day:,} tickets/day")
        print(f"{'=' * 80}")
        print(
            f"  {'Model':<32} {'$/run':>8}  {'$/day':>10}  {'$/month':>10}  "
            f"{'Input $/M':>10}  {'Notes'}"
        )
        print(f"  {'─' * 32} {'─' * 8}  {'─' * 10}  {'─' * 10}  {'─' * 10}")

        # Sort by cost per run
        models_sorted = sorted(
            self.pricing.values(),
            key=lambda p: p.cost_for_tokens(
                profile.total_input_tokens, profile.total_output_tokens
            ),
        )

        for model in models_sorted:
            cost = model.cost_for_tokens(profile.total_input_tokens, profile.total_output_tokens)
            daily = cost * tickets_per_day
            monthly = daily * 30
            print(
                f"  {model.display_name:<32} {cost:>8.4f}  {daily:>10.2f}  "
                f"{monthly:>10.2f}  {model.input_per_million:>10.2f}  {model.notes}"
            )

        print(f"{'─' * 80}")


# ──────────────────────────────────────────────────────────────
# Examples
# ──────────────────────────────────────────────────────────────

def example_single_call_cost():
    """Show cost for a single LLM call."""
    print("\n" + "=" * 60)
    print("  EXAMPLE 1: Cost for a Single LLM Call")
    print("=" * 60)

    estimator = CostEstimator()

    # Typical triage agent call
    input_tokens = 3_500   # system + ticket + KB articles
    output_tokens = 400    # JSON with category/priority/response

    print(f"\n  Scenario: Single triage call")
    print(f"  Input tokens:  {input_tokens:,}")
    print(f"  Output tokens: {output_tokens:,}")
    print()

    for model_id, pricing in MODEL_PRICING.items():
        cost = pricing.cost_for_tokens(input_tokens, output_tokens)
        print(f"  {pricing.display_name:<35} ${cost:.6f}")

    print("\n  Note: Output tokens are 3-5x more expensive per token than input!")
    print("  Keep your response format concise (JSON vs. prose)")


def example_agent_run_cost():
    """Show cost for a full multi-step agent run."""
    print("\n" + "=" * 60)
    print("  EXAMPLE 2: Cost for a Full Agent Run")
    print("=" * 60)

    # Profile for our support platform's triage + resolution pipeline
    profile = AgentRunProfile(
        name="Support Platform (Triage + Resolution)",
        system_prompt_tokens=2_000,
        conversation_tokens=3_000,
        kb_context_tokens=8_000,    # 3 KB articles retrieved by RAG
        customer_data_tokens=500,
        ticket_tokens=400,
        output_tokens=600,
        llm_calls_per_run=3,        # Triage + Resolution + Quality check
    )

    print(f"\n  Profile: {profile.name}")
    print(f"  LLM calls per ticket: {profile.llm_calls_per_run}")
    print(f"  Input tokens per call: {profile.input_tokens_per_call:,}")
    print(f"  Total input tokens:    {profile.total_input_tokens:,}")
    print(f"  Total output tokens:   {profile.total_output_tokens:,}")

    estimator = CostEstimator()
    estimator.compare_models(profile, tickets_per_day=1_000)


def example_monthly_projection():
    """Project costs at different traffic levels."""
    print("\n" + "=" * 60)
    print("  EXAMPLE 3: Monthly Cost Projection")
    print("=" * 60)

    profile = AgentRunProfile(
        name="Support Platform",
        system_prompt_tokens=2_000,
        kb_context_tokens=8_000,
        ticket_tokens=400,
        output_tokens=600,
        llm_calls_per_run=2,
    )
    estimator = CostEstimator()

    print("\n  Model: GPT-4o")
    print(f"  {'Volume':<25} {'No Cache':>12} {'30% Cache':>12} {'50% Cache':>12}")
    print(f"  {'─' * 25} {'─' * 12} {'─' * 12} {'─' * 12}")

    for daily_tickets in [100, 1_000, 10_000, 50_000]:
        base = estimator.monthly_cost("gpt-4o", profile, daily_tickets, 0.0)
        cached30 = estimator.monthly_cost("gpt-4o", profile, daily_tickets, 0.30)
        cached50 = estimator.monthly_cost("gpt-4o", profile, daily_tickets, 0.50)
        label = f"{daily_tickets:,} tickets/day"
        print(
            f"  {label:<25} ${base['monthly_cost']:>10,.2f}  "
            f"${cached30['monthly_cost']:>10,.2f}  ${cached50['monthly_cost']:>10,.2f}"
        )

    print("\n  Same analysis with model routing (GPT-4o-mini for simple tickets)")
    print(f"  {'Volume':<25} {'All GPT-4o':>12} {'Mix (est)':>12} {'Savings':>12}")
    print(f"  {'─' * 25} {'─' * 12} {'─' * 12} {'─' * 12}")

    for daily_tickets in [1_000, 10_000]:
        all_gpt4o = estimator.monthly_cost("gpt-4o", profile, daily_tickets)
        # Estimate: 60% of tickets go to mini, 40% to gpt-4o
        mini_cost = estimator.monthly_cost("gpt-4o-mini", profile, int(daily_tickets * 0.6))
        full_cost = estimator.monthly_cost("gpt-4o", profile, int(daily_tickets * 0.4))
        mixed_monthly = mini_cost["monthly_cost"] + full_cost["monthly_cost"]
        savings = all_gpt4o["monthly_cost"] - mixed_monthly
        savings_pct = savings / all_gpt4o["monthly_cost"] * 100

        print(
            f"  {f'{daily_tickets:,}/day':<25} ${all_gpt4o['monthly_cost']:>10,.2f}  "
            f"${mixed_monthly:>10,.2f}  ${savings:>7,.2f} ({savings_pct:.0f}%)"
        )


def example_set_cost_limit():
    """Show how to use cost estimates to set per-request limits."""
    print("\n" + "=" * 60)
    print("  EXAMPLE 4: Setting Cost Limits for Production")
    print("=" * 60)

    profile = AgentRunProfile(
        name="Typical support ticket",
        system_prompt_tokens=2_000,
        kb_context_tokens=8_000,
        ticket_tokens=400,
        output_tokens=600,
        llm_calls_per_run=3,
    )

    estimator = CostEstimator()
    typical_cost = estimator.cost_per_run("gpt-4o", profile)

    print(f"\n  Typical cost per agent run (GPT-4o): ${typical_cost:.4f}")
    print(f"\n  Recommended per-request cost limits:")
    print(f"  - Normal limit:    ${typical_cost * 3:.4f}  (3x typical cost)")
    print(f"  - Alert threshold: ${typical_cost * 5:.4f}  (5x typical cost)")
    print(f"  - Hard limit:      ${typical_cost * 10:.4f} (10x typical cost)")

    print(f"""
  Add to your agent:

    from support_platform.config import settings

    COST_LIMIT = {typical_cost * 5:.4f}  # Alert threshold

    if running_cost > COST_LIMIT:
        raise CostLimitExceeded(
            f"Cost ${{running_cost:.4f}} exceeded limit ${typical_cost * 5:.4f}"
        )
    """)


if __name__ == "__main__":
    example_single_call_cost()
    example_agent_run_cost()
    example_monthly_projection()
    example_set_cost_limit()
