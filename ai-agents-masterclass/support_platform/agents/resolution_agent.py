"""
resolution_agent.py - AI Resolution Agent
==========================================
The resolution agent is the second stage of the support pipeline.

It takes the TriageResult and:
1. Searches the KB for solutions (using the triage category as a filter)
2. Gets the customer's full history for context
3. Drafts a resolution using KB content and customer context
4. Decides whether to auto-send or escalate to human support
5. Returns a ResolutionResult

Usage:
    from support_platform.agents.triage_agent import TriageResult
    from support_platform.agents.resolution_agent import ResolutionAgent

    # After triage:
    resolution = ResolutionAgent().resolve(triage_result)
    if resolution.auto_send:
        send_to_customer(resolution.response)
    else:
        escalate_to_human(resolution.escalation_reason)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from support_platform.config import settings
from support_platform.tools.knowledge_base import search_knowledge_base
from support_platform.tools.customer_db import get_customer_tickets


# ──────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────

@dataclass
class ResolutionResult:
    """
    Structured output from the resolution agent.

    Contains the drafted response and the decision about whether
    to auto-send it or escalate to a human.
    """
    ticket_id: str
    response: str              # The drafted response to send (or show to human)
    auto_send: bool            # True = send immediately, False = human review first
    escalation_reason: Optional[str]  # Why human review is needed
    resolution_approach: str   # Brief description of how the issue was resolved
    kb_articles_used: list[str]  # IDs of KB articles that informed the response
    confidence: float          # 0.0-1.0 confidence in the resolution

    # Performance tracking
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"ResolutionResult("
            f"auto_send={self.auto_send}, "
            f"confidence={self.confidence:.0%}, "
            f"response='{self.response[:50]}...'"
            f")"
        )


# ──────────────────────────────────────────────────────────────
# Resolution Agent
# ──────────────────────────────────────────────────────────────

RESOLUTION_SYSTEM_PROMPT = """You are an expert customer support resolution agent for a SaaS platform.

Your task is to draft a helpful, accurate, and empathetic response to a support ticket.

AVAILABLE INFORMATION:
- Ticket category and priority (from triage)
- Customer profile (plan, status, history)
- Relevant knowledge base articles
- Previous ticket history

RESPONSE GUIDELINES:
- Be empathetic and acknowledge the customer's frustration
- Provide specific, actionable steps (numbered list when appropriate)
- Reference KB articles when providing instructions
- For billing issues: never promise refunds without verification
- For enterprise customers: acknowledge their SLA and prioritize speed
- Keep responses under 300 words unless the issue requires more detail
- End with an offer to help further

AUTO-SEND CRITERIA (set auto_send: true):
- Standard troubleshooting with clear KB steps
- General inquiries with known answers
- Password reset, account unlock instructions

ESCALATE TO HUMAN (set auto_send: false):
- Billing disputes or refund requests over $50
- Data loss or security incidents
- Customer has escalated 3+ times previously
- Customer explicitly requests human agent
- Issue requires account-level changes

Return ONLY valid JSON with these exact fields:
{
  "response": "Full response text to send to the customer",
  "auto_send": true,
  "escalation_reason": null,
  "resolution_approach": "brief description of approach",
  "kb_articles_used": ["kb_001", "kb_002"],
  "confidence": 0.88
}"""


class ResolutionAgent:
    """
    The resolution agent drafts responses and decides on auto-send vs escalation.

    This is the second stage of the pipeline:

        TriageResult → [ResolutionAgent] → ResolutionResult → Send/Escalate

    The agent uses:
    1. The TriageResult for context (category, priority, KB articles already found)
    2. Additional KB search filtered by the ticket's category
    3. Full customer ticket history for personalization
    """

    def __init__(self, model: str = None):
        self.model = model or settings.default_model
        self._llm_client = None

    def _get_client(self):
        if self._llm_client is None:
            try:
                from openai import OpenAI
                self._llm_client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                raise RuntimeError("openai package not installed")
        return self._llm_client

    def resolve(self, triage_result, ticket_subject: str = "", ticket_body: str = "") -> ResolutionResult:
        """
        Draft a resolution for a triaged support ticket.

        Args:
            triage_result: TriageResult from the triage agent
            ticket_subject: Original ticket subject (for additional KB search)
            ticket_body: Original ticket body

        Returns:
            ResolutionResult with the drafted response and auto-send decision
        """
        from support_platform.agents.triage_agent import TriageResult

        start_time = time.time()

        # ── Step 1: Get additional context ────────────────────
        # Get more KB articles filtered by the identified category
        additional_articles = search_knowledge_base(
            query=ticket_subject or triage_result.triage_reasoning,
            n_results=3,
            category_filter=triage_result.category,
        )

        # Merge with articles already found by triage
        all_articles = {a["id"]: a for a in triage_result.kb_articles}
        for article in additional_articles:
            all_articles[article["id"]] = article

        kb_context = list(all_articles.values())[:4]  # Max 4 articles

        # Get full ticket history for personalization
        customer_email = triage_result.customer_context.get("email", "")
        ticket_history = get_customer_tickets(email=customer_email, limit=5)

        # ── Step 2: Build prompt ──────────────────────────────
        prompt = self._build_resolution_prompt(
            triage_result, kb_context, ticket_history, ticket_subject, ticket_body
        )

        # ── Step 3: Call LLM ──────────────────────────────────
        llm_result = self._call_llm_with_fallback(prompt, triage_result)
        latency_ms = int((time.time() - start_time) * 1000)

        # ── Step 4: Parse response ────────────────────────────
        parsed = self._parse_resolution(llm_result.get("content", ""))

        return ResolutionResult(
            ticket_id=triage_result.ticket_id,
            response=parsed.get("response", self._default_response(triage_result)),
            auto_send=bool(parsed.get("auto_send", False)),
            escalation_reason=parsed.get("escalation_reason"),
            resolution_approach=parsed.get("resolution_approach", ""),
            kb_articles_used=parsed.get("kb_articles_used", []),
            confidence=float(parsed.get("confidence", 0.7)),
            input_tokens=llm_result.get("input_tokens", 0),
            output_tokens=llm_result.get("output_tokens", 0),
            cost_usd=llm_result.get("cost_usd", 0.0),
            latency_ms=latency_ms,
        )

    def _build_resolution_prompt(
        self, triage_result, kb_articles, ticket_history, subject, body
    ) -> str:
        """Build the resolution prompt with all context."""
        customer = triage_result.customer_context
        lines = [
            f"TICKET DETAILS:",
            f"  Category: {triage_result.category}",
            f"  Priority: {triage_result.priority}",
            f"  Subject: {subject}",
            f"  Body: {body[:500]}",
            "",
            "CUSTOMER:",
            f"  Name: {customer.get('name', 'Customer')}",
            f"  Plan: {customer.get('subscription_tier', 'unknown')}",
            f"  Status: {customer.get('account_status', 'unknown')}",
        ]

        if ticket_history:
            lines.append(f"\nTICKET HISTORY ({len(ticket_history)} previous):")
            for t in ticket_history[:3]:
                lines.append(f"  - {t.get('subject', '?')[:60]} [{t.get('status', '?')}]")

        if kb_articles:
            lines.append(f"\nKNOWLEDGE BASE ARTICLES ({len(kb_articles)}):")
            for article in kb_articles:
                lines.append(f"\n  [{article.get('relevance_score', 0):.0%}] {article['title']}")
                lines.append(f"  {article['content']}")

        lines.append(f"\nTriage notes: {triage_result.triage_reasoning}")
        lines.append("\nDraft a resolution response. Return JSON only.")

        return "\n".join(lines)

    def _call_llm_with_fallback(self, prompt: str, triage_result) -> dict:
        """Call LLM with fallback to template-based resolution."""
        if not settings.has_openai_key:
            return self._template_fallback(triage_result)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model if not self.model.startswith("claude") else "gpt-4o",
                messages=[
                    {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1500,
            )

            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            model_pricing = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60)}
            pricing = model_pricing.get(self.model, (2.50, 10.00))
            cost = (input_tokens / 1_000_000 * pricing[0] +
                    output_tokens / 1_000_000 * pricing[1])

            return {"content": content, "input_tokens": input_tokens,
                    "output_tokens": output_tokens, "cost_usd": cost}

        except Exception as e:
            return self._template_fallback(triage_result, error=str(e))

    def _template_fallback(self, triage_result, error: str = None) -> dict:
        """Template-based fallback when LLM is unavailable."""
        customer_name = triage_result.customer_context.get("name", "there")
        category = triage_result.category

        templates = {
            "account_access": (
                f"Hi {customer_name},\n\nI understand you're having trouble accessing your account. "
                f"Here are the steps to resolve this:\n\n"
                f"1. Go to our login page and click 'Forgot Password'\n"
                f"2. Enter your email address\n"
                f"3. Check your inbox for a password reset link (check spam if not received)\n"
                f"4. Click the link and set a new password\n\n"
                f"If you're having 2FA issues, use your backup codes or contact us immediately.\n\n"
                f"Let me know if you need any additional help!"
            ),
            "billing": (
                f"Hi {customer_name},\n\nThank you for reaching out about your billing. "
                f"Our billing team will review your account and get back to you within 1 business day.\n\n"
                f"For immediate assistance, please email billing@support.io with your account email and charge details.\n\n"
                f"We're sorry for any inconvenience!"
            ),
            "general_inquiry": (
                f"Hi {customer_name},\n\nThank you for contacting us! "
                f"I'm happy to help answer your question.\n\n"
                f"Could you provide a bit more detail about what you're looking for? "
                f"I want to make sure I give you the most accurate and helpful information.\n\n"
                f"Best regards,\nSupport Team"
            ),
        }

        response = templates.get(category, templates["general_inquiry"])
        auto_send = category in ("account_access", "general_inquiry")

        return {
            "content": json.dumps({
                "response": response,
                "auto_send": auto_send,
                "escalation_reason": None if auto_send else "Billing issue requires human review",
                "resolution_approach": f"Template fallback for {category}",
                "kb_articles_used": [],
                "confidence": 0.6,
            }),
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        }

    def _parse_resolution(self, content: str) -> dict:
        """Parse the LLM's JSON response."""
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    def _default_response(self, triage_result) -> str:
        """Default response if parsing fails."""
        name = triage_result.customer_context.get("name", "there")
        return (
            f"Hi {name},\n\nThank you for contacting support. "
            f"We've received your message and will respond within 24 hours.\n\n"
            f"Best regards,\nSupport Team"
        )
