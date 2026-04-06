"""
triage_agent.py - AI Triage Agent
===================================
The triage agent is the first stage of the support pipeline.

It reads an incoming ticket and:
1. Classifies the category (account_access, billing, etc.)
2. Sets the priority (low, medium, high, critical)
3. Searches the knowledge base for relevant articles
4. Determines if it can auto-resolve or needs human escalation
5. Returns a structured TriageResult

The agent uses GPT-4o (or Claude) with structured output extraction.

Usage:
    from support_platform.agents.triage_agent import TriageAgent, TriageResult

    agent = TriageAgent()
    result = agent.triage(
        ticket_id="abc-123",
        subject="Can't log in after phone upgrade",
        body="I upgraded my iPhone and now my 2FA codes don't work...",
        customer_email="alice@example.com",
    )
    print(result.category, result.priority, result.can_auto_resolve)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from support_platform.config import settings
from support_platform.tools.knowledge_base import search_knowledge_base
from support_platform.tools.customer_db import get_customer_by_email, get_customer_tickets


# ──────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────

@dataclass
class TriageResult:
    """
    Structured output from the triage agent.

    Passed to the resolution agent as the starting state.
    """
    ticket_id: str
    category: str              # account_access, billing, technical_bug, feature_request, general_inquiry
    priority: str              # low, medium, high, critical
    confidence: float          # 0.0-1.0 confidence in the classification
    can_auto_resolve: bool     # Can we handle this without a human?
    escalation_reason: Optional[str]  # Why escalation is needed (if applicable)
    kb_articles: list[dict]    # Relevant KB articles found
    customer_context: dict     # Customer profile and history
    triage_reasoning: str      # Agent's reasoning (for audit log)
    suggested_response: Optional[str]  # Draft response if auto-resolvable

    # Performance tracking
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"TriageResult("
            f"category={self.category}, "
            f"priority={self.priority}, "
            f"confidence={self.confidence:.0%}, "
            f"auto_resolve={self.can_auto_resolve}"
            f")"
        )


# ──────────────────────────────────────────────────────────────
# Triage Agent
# ──────────────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """You are an expert customer support triage agent for a SaaS platform.

Your task is to analyze incoming support tickets and classify them accurately.

CATEGORIES:
- account_access: Login issues, password resets, 2FA problems, account locked/suspended
- billing: Charges, invoices, refunds, subscription changes, payment issues
- technical_bug: Software errors, crashes, features not working, data issues
- feature_request: Requests for new features or improvements
- general_inquiry: Questions about features, pricing, policies, how-to questions

PRIORITY LEVELS:
- critical: Production down, data loss, security breach, enterprise customer blocked
- high: Core feature broken, billing error, customer completely blocked
- medium: Feature degraded, billing question, account access issue
- low: Feature request, general question, minor inconvenience

AUTO-RESOLVE CRITERIA:
- Can auto-resolve: Has a clear answer in the knowledge base, standard troubleshooting
- Must escalate: Billing disputes over $50, data loss, legal/compliance, repeated escalations, angry customer

Return ONLY valid JSON with these exact fields:
{
  "category": "account_access",
  "priority": "high",
  "confidence": 0.92,
  "can_auto_resolve": true,
  "escalation_reason": null,
  "triage_reasoning": "Customer locked out after phone upgrade broke 2FA. Clear KB resolution exists.",
  "suggested_response": "Hi! I can help you recover your 2FA access..."
}"""


class TriageAgent:
    """
    The triage agent classifies incoming tickets and prepares them for resolution.

    This is the entry point of the multi-agent pipeline:

        Ticket → [TriageAgent] → TriageResult → [ResolutionAgent] → Resolution

    The agent uses:
    1. LLM (GPT-4o/Claude) for classification and reasoning
    2. knowledge_base tool for finding relevant articles
    3. customer_db tool for customer context

    Configured via support_platform/config.py settings.
    """

    def __init__(
        self,
        model: str = None,
        temperature: float = None,
    ):
        self.model = model or settings.default_model
        self.temperature = temperature or settings.default_temperature
        self._llm_client = None

    def _get_client(self):
        """Lazy-initialize the LLM client."""
        if self._llm_client is None:
            try:
                from openai import OpenAI
                self._llm_client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._llm_client

    def triage(
        self,
        ticket_id: str,
        subject: str,
        body: str,
        customer_email: str,
    ) -> TriageResult:
        """
        Triage a support ticket.

        1. Gather context (customer info, ticket history, KB articles)
        2. Call LLM with full context and structured output format
        3. Parse and validate the response
        4. Return TriageResult

        Args:
            ticket_id: Unique identifier for this ticket
            subject: Ticket subject line
            body: Full ticket body
            customer_email: Customer's email address

        Returns:
            TriageResult with classification, priority, KB articles, and response draft
        """
        start_time = time.time()

        # ── Step 1: Gather context ────────────────────────────
        # Get customer profile
        customer_context = get_customer_by_email(customer_email)

        # Get customer's ticket history (look for patterns)
        ticket_history = get_customer_tickets(email=customer_email, limit=5)

        # Search KB for relevant articles
        kb_query = f"{subject} {body[:200]}"
        kb_articles = search_knowledge_base(kb_query, n_results=3)

        # ── Step 2: Build prompt with context ─────────────────
        context_block = self._build_context_block(
            customer_context, ticket_history, kb_articles
        )

        user_message = f"""Triage this support ticket:

Subject: {subject}

Body:
{body}

---
{context_block}

Respond with JSON only."""

        # ── Step 3: Call LLM ──────────────────────────────────
        llm_result = self._call_llm_with_fallback(user_message)
        latency_ms = int((time.time() - start_time) * 1000)

        # ── Step 4: Parse and validate ────────────────────────
        classification = self._parse_classification(llm_result.get("content", ""))

        return TriageResult(
            ticket_id=ticket_id,
            category=classification.get("category", "general_inquiry"),
            priority=classification.get("priority", "medium"),
            confidence=float(classification.get("confidence", 0.7)),
            can_auto_resolve=bool(classification.get("can_auto_resolve", False)),
            escalation_reason=classification.get("escalation_reason"),
            kb_articles=kb_articles,
            customer_context=customer_context,
            triage_reasoning=classification.get("triage_reasoning", ""),
            suggested_response=classification.get("suggested_response"),
            input_tokens=llm_result.get("input_tokens", 0),
            output_tokens=llm_result.get("output_tokens", 0),
            cost_usd=llm_result.get("cost_usd", 0.0),
            latency_ms=latency_ms,
        )

    def _build_context_block(
        self,
        customer: dict,
        ticket_history: list[dict],
        kb_articles: list[dict],
    ) -> str:
        """Format gathered context for the LLM."""
        lines = ["CUSTOMER CONTEXT:"]

        if "error" not in customer:
            lines.append(f"  Name: {customer.get('name', 'Unknown')}")
            lines.append(f"  Plan: {customer.get('subscription_tier', 'unknown')}")
            lines.append(f"  Status: {customer.get('account_status', 'unknown')}")
        else:
            lines.append(f"  {customer['error']}")

        if ticket_history:
            lines.append(f"\nPREVIOUS TICKETS ({len(ticket_history)} found):")
            for t in ticket_history[:3]:
                lines.append(f"  - {t.get('subject', '?')[:50]} [{t.get('status', '?')}]")

        if kb_articles:
            lines.append(f"\nRELEVANT KB ARTICLES ({len(kb_articles)} found):")
            for article in kb_articles:
                score = article.get("relevance_score", 0)
                lines.append(f"  [{score:.0%}] {article['title']}")
                lines.append(f"       {article['content'][:100]}...")

        return "\n".join(lines)

    def _call_llm_with_fallback(self, user_message: str) -> dict:
        """
        Call the LLM and return a dict with content and token stats.
        Falls back to rule-based classification if LLM is unavailable.
        """
        if not settings.has_openai_key:
            return self._rule_based_fallback(user_message)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model if not self.model.startswith("claude") else "gpt-4o",
                messages=[
                    {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0,  # Triage should be deterministic
                max_tokens=1000,
            )

            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Calculate cost
            model_pricing = {
                "gpt-4o": (2.50, 10.00),
                "gpt-4o-mini": (0.15, 0.60),
            }
            pricing = model_pricing.get(self.model, (2.50, 10.00))
            cost = (input_tokens / 1_000_000 * pricing[0] +
                    output_tokens / 1_000_000 * pricing[1])

            return {
                "content": content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            }

        except Exception as e:
            return self._rule_based_fallback(user_message, error=str(e))

    def _rule_based_fallback(self, user_message: str, error: str = None) -> dict:
        """Rule-based classification fallback (used when LLM is unavailable)."""
        text = user_message.lower()

        if any(w in text for w in ["password", "login", "locked", "access", "2fa", "authenticator"]):
            category, priority = "account_access", "high"
        elif any(w in text for w in ["charge", "bill", "invoice", "refund", "payment"]):
            category, priority = "billing", "high"
        elif any(w in text for w in ["error", "crash", "bug", "broken", "not working"]):
            category, priority = "technical_bug", "high"
        elif any(w in text for w in ["feature", "would be", "request", "add", "improve"]):
            category, priority = "feature_request", "low"
        else:
            category, priority = "general_inquiry", "low"

        can_auto = category in ("general_inquiry", "account_access", "feature_request")

        fallback_json = json.dumps({
            "category": category,
            "priority": priority,
            "confidence": 0.65,
            "can_auto_resolve": can_auto,
            "escalation_reason": None if can_auto else "Rule-based: requires human review",
            "triage_reasoning": f"Rule-based classification. {'LLM error: ' + error if error else 'LLM unavailable.'}",
            "suggested_response": None,
        })

        return {"content": fallback_json, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    def _parse_classification(self, content: str) -> dict:
        """Parse and validate the LLM's JSON response."""
        if not content:
            return self._default_classification()

        try:
            data = json.loads(content)

            # Validate and normalize
            valid_categories = {
                "account_access", "billing", "technical_bug",
                "feature_request", "general_inquiry"
            }
            valid_priorities = {"low", "medium", "high", "critical"}

            if data.get("category") not in valid_categories:
                data["category"] = "general_inquiry"
            if data.get("priority") not in valid_priorities:
                data["priority"] = "medium"
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.7))))

            return data

        except (json.JSONDecodeError, ValueError):
            return self._default_classification()

    def _default_classification(self) -> dict:
        return {
            "category": "general_inquiry",
            "priority": "medium",
            "confidence": 0.5,
            "can_auto_resolve": False,
            "escalation_reason": "Could not parse LLM response",
            "triage_reasoning": "Defaulted due to parsing error",
            "suggested_response": None,
        }


# ──────────────────────────────────────────────────────────────
# Convenience function
# ──────────────────────────────────────────────────────────────

def triage_ticket(
    ticket_id: str,
    subject: str,
    body: str,
    customer_email: str,
) -> TriageResult:
    """
    Convenience function to triage a ticket using the default agent.

    Usage:
        result = triage_ticket("tkt-001", "Can't login", "I forgot...", "user@example.com")
    """
    agent = TriageAgent()
    return agent.triage(ticket_id, subject, body, customer_email)
