"""
01_model_routing.py - Intelligent Model Routing
================================================
Module 12: Cost Optimization

Not every request needs GPT-4o. By routing requests to the
cheapest model that can handle the task, you can reduce costs
by 80-95% with minimal quality loss.

Routing strategies:
1. Rule-based routing — deterministic, zero latency
2. Complexity scoring — estimate difficulty before routing
3. Cascade routing — try cheap first, escalate if needed

Cost comparison (approximate):
- GPT-4o:      $5.00/$15.00 per 1M input/output tokens
- GPT-4o-mini: $0.15/$0.60 per 1M input/output tokens
- Ratio:       33x/25x cheaper for mini

Rule of thumb: use mini for 80% of requests, GPT-4o for the hard 20%.

Run with: python module_12_cost_optimization/examples/01_model_routing.py
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Model Registry
# ──────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """Configuration for an LLM model."""
    name: str
    input_cost_per_1m: float   # USD per 1M input tokens
    output_cost_per_1m: float  # USD per 1M output tokens
    context_window: int        # Max tokens
    strengths: list[str]
    tier: str                  # "fast", "standard", "premium"


MODEL_REGISTRY = {
    "gpt-4o-mini": ModelConfig(
        name="gpt-4o-mini",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        context_window=128_000,
        strengths=["classification", "simple_qa", "summarization", "extraction"],
        tier="fast",
    ),
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        input_cost_per_1m=5.00,
        output_cost_per_1m=15.00,
        context_window=128_000,
        strengths=["complex_reasoning", "nuanced_writing", "code_generation", "multi_step"],
        tier="premium",
    ),
    "gpt-3.5-turbo": ModelConfig(
        name="gpt-3.5-turbo",
        input_cost_per_1m=0.50,
        output_cost_per_1m=1.50,
        context_window=16_000,
        strengths=["simple_chat", "templates", "basic_qa"],
        tier="standard",
    ),
}


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate approximate cost for an LLM call."""
    model = MODEL_REGISTRY.get(model_name, MODEL_REGISTRY["gpt-4o-mini"])
    return (
        (input_tokens / 1_000_000) * model.input_cost_per_1m +
        (output_tokens / 1_000_000) * model.output_cost_per_1m
    )


# ──────────────────────────────────────────────────────────────
# Strategy 1: Rule-Based Router
# ──────────────────────────────────────────────────────────────

class RuleBasedRouter:
    """
    Route requests based on deterministic rules.

    Fastest and most predictable routing strategy.
    No extra LLM call needed to decide which model to use.

    Rules are defined based on task type and known complexity signals.
    """

    CHEAP_MODEL = "gpt-4o-mini"
    EXPENSIVE_MODEL = "gpt-4o"

    def route(self, task_type: str, subject: str, body: str) -> tuple[str, str]:
        """
        Returns (model_name, reason).
        """
        text = f"{subject} {body}".lower()

        # CHEAP model tasks (clear answers from KB)
        if task_type in ("classification", "triage"):
            return self.CHEAP_MODEL, "Classification tasks are straightforward"

        if task_type == "extraction":
            return self.CHEAP_MODEL, "Data extraction is well-suited for mini models"

        # Always cheap: short, templated responses
        if len(body.split()) < 20:
            return self.CHEAP_MODEL, "Short input — simple request"

        # Always expensive: legal/security/complex reasoning
        if any(w in text for w in ["legal", "lawsuit", "breach", "gdpr", "compliance"]):
            return self.EXPENSIVE_MODEL, "Legal/compliance topics require careful reasoning"

        if any(w in text for w in ["data loss", "security", "hacked", "compromised"]):
            return self.EXPENSIVE_MODEL, "Security incidents require expert handling"

        # Medium complexity: use cheap model
        return self.CHEAP_MODEL, "Standard support request — mini model sufficient"


# ──────────────────────────────────────────────────────────────
# Strategy 2: Complexity Scorer
# ──────────────────────────────────────────────────────────────

@dataclass
class ComplexityScore:
    """Scored complexity assessment for a request."""
    score: float          # 0.0 (trivial) to 1.0 (very complex)
    signals: list[str]    # What drove the score
    recommended_model: str
    estimated_cost: float


class ComplexityScorer:
    """
    Score request complexity to select the appropriate model.

    Complexity signals (each adds to the score):
    - Multi-issue ticket (mentions several problems)
    - Technical jargon (API, webhook, integration)
    - Escalation keywords (legal, urgent, executive)
    - Long input (more context = harder to process)
    - Customer frustration markers
    - Requires investigation (not just KB lookup)
    """

    THRESHOLD_CHEAP = 0.4    # Score ≤ 0.4 → cheap model
    THRESHOLD_STANDARD = 0.7  # Score ≤ 0.7 → standard model

    def score(self, subject: str, body: str) -> ComplexityScore:
        """Analyze a request and recommend the best model."""
        text = f"{subject} {body}".lower()
        signals = []
        score = 0.0

        # Signal: length (longer = more context to process)
        word_count = len(body.split())
        if word_count > 200:
            score += 0.2
            signals.append(f"Long message ({word_count} words)")
        elif word_count > 100:
            score += 0.1
            signals.append(f"Medium message ({word_count} words)")

        # Signal: technical complexity
        technical_words = ["api", "webhook", "integration", "sdk", "oauth", "saml", "sso", "endpoint"]
        tech_count = sum(1 for w in technical_words if w in text)
        if tech_count >= 2:
            score += 0.25
            signals.append(f"Technical jargon ({tech_count} terms)")
        elif tech_count == 1:
            score += 0.1
            signals.append("Some technical terminology")

        # Signal: urgency and escalation
        urgent_words = ["urgent", "immediately", "asap", "emergency", "critical", "down", "outage"]
        if any(w in text for w in urgent_words):
            score += 0.2
            signals.append("Urgency/escalation signal")

        # Signal: legal/compliance topics
        legal_words = ["legal", "lawyer", "lawsuit", "gdpr", "compliance", "regulation", "audit"]
        if any(w in text for w in legal_words):
            score += 0.4
            signals.append("Legal/compliance topic")

        # Signal: multiple issues mentioned
        issue_count = sum(text.count(sep) for sep in ["also", "additionally", "furthermore", "plus", "and also"])
        if issue_count >= 2:
            score += 0.15
            signals.append(f"Multiple issues ({issue_count} connectors)")

        # Signal: anger/frustration (requires more careful, nuanced response)
        frustration_words = ["unacceptable", "ridiculous", "terrible", "awful", "worst", "incompetent"]
        if any(w in text for w in frustration_words):
            score += 0.2
            signals.append("Customer frustration detected")

        score = min(1.0, score)

        # Select model based on score
        if score <= self.THRESHOLD_CHEAP:
            model = "gpt-4o-mini"
        elif score <= self.THRESHOLD_STANDARD:
            model = "gpt-3.5-turbo"  # Intermediate
        else:
            model = "gpt-4o"

        # Estimate cost (assuming ~500 input tokens, ~300 output tokens)
        cost = estimate_cost(model, 500, 300)

        return ComplexityScore(
            score=score,
            signals=signals or ["No complexity signals — simple request"],
            recommended_model=model,
            estimated_cost=cost,
        )


# ──────────────────────────────────────────────────────────────
# Strategy 3: Cascade Router
# ──────────────────────────────────────────────────────────────

@dataclass
class CascadeResult:
    """Result from cascade routing."""
    response: str
    model_used: str
    attempts: int
    total_cost: float
    reason: str


class CascadeRouter:
    """
    Try cheap model first; escalate to expensive if quality is low.

    This is the most sophisticated routing strategy:
    1. Run cheap model
    2. Evaluate the response quality
    3. If quality passes → return it (save money)
    4. If quality fails → run expensive model

    When to use cascade:
    - You want maximum cost savings
    - Request complexity is unpredictable
    - You have a reliable quality check

    Downside: doubles latency when escalation happens.
    """

    def _quick_quality_check(self, response: str, subject: str) -> tuple[bool, str]:
        """
        Fast heuristic quality check without another LLM call.

        Returns (passes_quality, reason).
        """
        # Too short
        if len(response.split()) < 20:
            return False, "Response too short"

        # No greeting
        if not any(response.startswith(g) for g in ["Hi", "Hello", "Dear", "Thank"]):
            return False, "Missing professional greeting"

        # Contains hedge phrases indicating uncertainty (cheap model struggling)
        uncertainty = ["I'm not sure", "I don't know", "you should contact someone", "I cannot help"]
        if any(phrase.lower() in response.lower() for phrase in uncertainty):
            return False, "Response contains uncertainty indicators"

        return True, "Quality check passed"

    def route_and_respond(
        self,
        subject: str,
        body: str,
        email: str,
        cheap_model: str = "gpt-4o-mini",
        expensive_model: str = "gpt-4o",
    ) -> CascadeResult:
        """
        Try cheap model, escalate if needed.
        """
        total_cost = 0.0
        attempts = 0
        name = email.split("@")[0].replace(".", " ").title()

        # Mock LLM responses for demo
        def mock_llm(model: str, prompt: str) -> str:
            # Simulate that expensive model gives better responses
            if "legal" in prompt.lower() or "breach" in prompt.lower():
                if model == cheap_model:
                    return "I'm not sure how to help with this legal matter."
                else:
                    return (
                        f"Hi {name},\n\nThis matter involves important legal and compliance considerations. "
                        f"Our legal team has been notified and will contact you within 4 business hours. "
                        f"Please do not take any action until you hear from them."
                    )
            else:
                return (
                    f"Hi {name},\n\nThank you for reaching out. "
                    f"I can help you with this. Please try the solution in our knowledge base first."
                )

        # Attempt 1: cheap model
        attempts += 1
        response = mock_llm(cheap_model, f"{subject}: {body}")
        total_cost += estimate_cost(cheap_model, 400, len(response.split()))

        passes, reason = self._quick_quality_check(response, subject)

        if passes:
            return CascadeResult(response, cheap_model, attempts, total_cost, f"Cheap model sufficient: {reason}")

        # Attempt 2: expensive model
        attempts += 1
        response = mock_llm(expensive_model, f"{subject}: {body}")
        total_cost += estimate_cost(expensive_model, 400, len(response.split()))

        return CascadeResult(response, expensive_model, attempts, total_cost, f"Escalated: {reason}")


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Model Routing for Cost Optimization")
    print("=" * 60)

    test_tickets = [
        ("Simple request", "Password reset", "Can't log in, forgot my password", "alice@example.com"),
        ("Technical", "API integration", "OAuth webhook integration failing with 403 errors on SAML endpoint", "bob@example.com"),
        ("Legal/urgent", "Compliance issue", "We need immediate GDPR compliance audit. Legal team is involved.", "cto@bigcorp.com"),
        ("Frustrated customer", "Absolutely terrible service", "This is unacceptable! I've been locked out for a week!", "charlie@example.com"),
    ]

    rule_router = RuleBasedRouter()
    scorer = ComplexityScorer()
    cascade = CascadeRouter()

    print("\n  Model cost comparison:")
    for name, model in [("GPT-4o-mini (1M tokens)", "gpt-4o-mini"), ("GPT-4o (1M tokens)", "gpt-4o")]:
        config = MODEL_REGISTRY[model]
        print(f"    {name}: ${config.input_cost_per_1m:.2f} input / ${config.output_cost_per_1m:.2f} output")

    print("\n  [1] Rule-Based Routing")
    for label, task, subject, body, email in [
        ("Triage task", "classification", "Support request", "billing issue", "a@ex.com"),
        ("Legal topic", "support", "Legal matter", "GDPR compliance breach", "b@ex.com"),
        ("Short request", "support", "Help", "Quick question", "c@ex.com"),
    ]:
        model, reason = rule_router.route(task, subject, body)
        print(f"    {label}: → {model} ({reason})")

    print("\n  [2] Complexity Scoring")
    for label, subject, body, email in test_tickets:
        result = scorer.score(subject, body)
        print(f"    {label}")
        print(f"      Score: {result.score:.0%} → {result.recommended_model}")
        print(f"      Signals: {result.signals[0]}")
        print(f"      Estimated cost: ${result.estimated_cost:.5f}/call")

    print("\n  [3] Cascade Routing")
    for label, subject, body, email in [("Simple", "Password help", "I forgot my password", "a@ex.com"), ("Complex", "Legal issue", "GDPR breach legal matter", "b@ex.com")]:
        result = cascade.route_and_respond(subject, body, email)
        print(f"    {label}: used {result.model_used} ({result.attempts} attempt(s))")
        print(f"      Cost: ${result.total_cost:.5f} | Reason: {result.reason}")

    print("\n  Cost optimization summary:")
    mini_cost = estimate_cost("gpt-4o-mini", 500, 300)
    full_cost = estimate_cost("gpt-4o", 500, 300)
    print(f"    1000 calls at gpt-4o-mini: ${mini_cost * 1000:.2f}")
    print(f"    1000 calls at gpt-4o:      ${full_cost * 1000:.2f}")
    print(f"    Savings (80/20 split):      ${(full_cost * 200 + mini_cost * 800) * 0 + (full_cost * 1000 - full_cost * 200 - mini_cost * 800):.2f}")


if __name__ == "__main__":
    main()
