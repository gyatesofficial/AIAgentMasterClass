"""
02_pipeline_pattern.py - Sequential Pipeline Pattern
=====================================================
Module 7: Multi-Agent Systems

Sequential pipeline: each stage processes the ticket and passes an
enriched state object to the next stage.

Intake → Triage → Resolution → Quality Check

Each stage adds its output to the TicketState, building up a complete
picture of the ticket by the end.

Run with: python module_07_multi_agent/examples/02_pipeline_pattern.py
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class TicketState:
    """Shared state that flows through the pipeline."""
    # Input
    ticket_id: str
    subject: str
    body: str
    customer_email: str

    # Set by Intake
    customer_name: Optional[str] = None
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    # Set by Triage
    category: Optional[str] = None
    priority: Optional[str] = None
    kb_articles: list[dict] = field(default_factory=list)
    triage_confidence: float = 0.0

    # Set by Resolution
    draft_response: Optional[str] = None
    should_escalate: bool = False
    escalation_reason: Optional[str] = None
    resolution_confidence: float = 0.0

    # Set by Quality
    quality_score: float = 0.0
    quality_issues: list[str] = field(default_factory=list)
    final_response: Optional[str] = None
    approved: bool = False

    # Pipeline metadata
    stages_completed: list[str] = field(default_factory=list)
    total_latency_ms: int = 0


class IntakeAgent:
    """Validates and normalizes incoming tickets."""

    def process(self, state: TicketState) -> TicketState:
        # Validate email
        if "@" not in state.customer_email:
            state.is_valid = False
            state.validation_errors.append("Invalid email address")

        # Validate subject length
        if len(state.subject) < 5:
            state.is_valid = False
            state.validation_errors.append("Subject too short")

        # Validate body length
        if len(state.body) < 10:
            state.is_valid = False
            state.validation_errors.append("Body too short")

        # Truncate if too long
        if len(state.body) > 10000:
            state.body = state.body[:10000]

        # Try to extract customer name from email
        if "@" in state.customer_email:
            username = state.customer_email.split("@")[0]
            name = username.replace(".", " ").replace("_", " ").title()
            state.customer_name = name

        state.stages_completed.append("intake")
        return state


class TriageAgentPipeline:
    """Classifies tickets in the pipeline."""

    KB = {
        "password login": {"category": "account_access", "priority": "high",
                           "article": "Reset password at login page > Forgot Password."},
        "charge billing payment": {"category": "billing", "priority": "high",
                                   "article": "Billing disputes: billing@example.com."},
        "error bug crash": {"category": "technical_bug", "priority": "high",
                            "article": "Technical issues: share error message + browser version."},
        "feature request": {"category": "feature_request", "priority": "low",
                            "article": "Feature requests logged in our roadmap."},
    }

    def process(self, state: TicketState) -> TicketState:
        if not state.is_valid:
            return state

        text = f"{state.subject} {state.body}".lower()
        best_match = None
        best_score = 0

        for keywords, data in self.KB.items():
            score = sum(1 for k in keywords.split() if k in text)
            if score > best_score:
                best_score = score
                best_match = data

        if best_match:
            state.category = best_match["category"]
            state.priority = best_match["priority"]
            state.kb_articles = [{"title": "Relevant Article", "content": best_match["article"]}]
            state.triage_confidence = min(best_score * 0.3, 0.95)
        else:
            state.category = "general_inquiry"
            state.priority = "medium"
            state.triage_confidence = 0.6

        state.stages_completed.append("triage")
        return state


class ResolutionAgentPipeline:
    """Drafts a resolution based on triage output."""

    def process(self, state: TicketState) -> TicketState:
        if not state.is_valid:
            return state

        name = state.customer_name or "there"

        if state.category == "account_access":
            state.draft_response = (
                f"Hi {name},\n\nI understand you're having account access issues. "
                f"Here's how to resolve this:\n\n"
                f"1. Go to the login page and click 'Forgot Password'\n"
                f"2. Enter your email address\n"
                f"3. Check your inbox for a reset link\n\n"
                f"The link is valid for 24 hours. Let me know if you need further help!"
            )
            state.should_escalate = False
            state.resolution_confidence = 0.88
        elif state.category == "billing":
            state.draft_response = (
                f"Hi {name},\n\nThank you for contacting us about your billing. "
                f"Our billing team will review your account and respond within 1 business day.\n\n"
                f"For urgent billing issues, please email billing@example.com."
            )
            state.should_escalate = True
            state.escalation_reason = "Billing issues require human review"
            state.resolution_confidence = 0.75
        else:
            state.draft_response = (
                f"Hi {name},\n\nThank you for your message. "
                f"Our team will look into this and get back to you within 24 hours."
            )
            state.should_escalate = False
            state.resolution_confidence = 0.70

        state.stages_completed.append("resolution")
        return state


class QualityAgent:
    """Reviews the draft response and approves or requests changes."""

    def process(self, state: TicketState) -> TicketState:
        if not state.is_valid or not state.draft_response:
            return state

        issues = []
        score = 10.0

        # Check: has greeting
        if not any(state.draft_response.startswith(g) for g in ["Hi", "Hello", "Dear"]):
            issues.append("Missing greeting")
            score -= 2

        # Check: has actionable steps
        has_steps = ("1." in state.draft_response or "step" in state.draft_response.lower())
        if state.category == "account_access" and not has_steps:
            issues.append("Should include step-by-step instructions")
            score -= 2

        # Check: length appropriate
        word_count = len(state.draft_response.split())
        if word_count < 20:
            issues.append("Response too brief")
            score -= 3
        elif word_count > 500:
            issues.append("Response too long")
            score -= 1

        # Check: professional tone
        rude_words = ["unfortunately we can't", "this is not our problem"]
        for phrase in rude_words:
            if phrase in state.draft_response.lower():
                issues.append(f"Unprofessional phrasing: '{phrase}'")
                score -= 3

        state.quality_score = max(0, min(10, score)) / 10.0
        state.quality_issues = issues
        state.approved = state.quality_score >= 0.6
        state.final_response = state.draft_response
        state.stages_completed.append("quality")
        return state


class SupportPipeline:
    """Orchestrates the full support pipeline."""

    def __init__(self):
        self.intake = IntakeAgent()
        self.triage = TriageAgentPipeline()
        self.resolution = ResolutionAgentPipeline()
        self.quality = QualityAgent()

    def run(self, ticket_id: str, subject: str, body: str, email: str) -> TicketState:
        state = TicketState(
            ticket_id=ticket_id,
            subject=subject,
            body=body,
            customer_email=email,
        )

        start = time.time()

        for stage, agent in [
            ("Intake", self.intake),
            ("Triage", self.triage),
            ("Resolution", self.resolution),
            ("Quality", self.quality),
        ]:
            print(f"    [{stage}]...", end=" ")
            state = agent.process(state)
            print(f"done")

        state.total_latency_ms = int((time.time() - start) * 1000)
        return state


def main():
    print("\n" + "=" * 60)
    print("  Sequential Pipeline Multi-Agent Demo")
    print("=" * 60)

    pipeline = SupportPipeline()

    tickets = [
        ("TKT-001", "Can't log in", "I forgot my password and can't access my account", "alice@example.com"),
        ("TKT-002", "Billing question", "I was charged twice last month for $79 each", "bob@example.com"),
    ]

    for ticket_id, subject, body, email in tickets:
        print(f"\n  Processing: '{subject}'")
        state = pipeline.run(ticket_id, subject, body, email)

        print(f"\n  Pipeline Results:")
        print(f"    Stages: {' → '.join(state.stages_completed)}")
        print(f"    Category: {state.category} / Priority: {state.priority}")
        print(f"    Triage confidence: {state.triage_confidence:.0%}")
        print(f"    Quality score: {state.quality_score:.0%} (approved: {state.approved})")
        print(f"    Escalate: {state.should_escalate}")
        if state.quality_issues:
            print(f"    Quality issues: {state.quality_issues}")
        print(f"    Total latency: {state.total_latency_ms}ms")
        print(f"\n  Final Response:\n{state.final_response[:200]}...")


if __name__ == "__main__":
    main()
