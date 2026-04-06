"""
01_supervisor_pattern.py - Supervisor/Worker Multi-Agent Pattern
================================================================
Module 7: Multi-Agent Systems

The supervisor pattern uses one orchestrator agent to route tasks to
specialist worker agents. The supervisor doesn't do the work — it decides
which specialist should handle the request.

Architecture:
    Customer Ticket
         |
    [Supervisor Agent]
         |
    ┌────┼────┐
    |    |    |
 [Billing] [Technical] [Account]
 Specialist  Specialist  Specialist

Benefits:
- Each specialist has focused prompt + relevant tools
- Supervisor is simple (routing only)
- Easy to add new specialists
- Better quality than generalist agent

Run with: python module_07_multi_agent/examples/01_supervisor_pattern.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AgentResult:
    """Unified result from any worker agent."""
    specialist: str
    response: str
    confidence: float
    escalate: bool
    reasoning: str


# ──────────────────────────────────────────────────────────────
# Worker Agents (specialists)
# ──────────────────────────────────────────────────────────────

class BillingSpecialist:
    """Handles billing, charges, invoices, refunds."""
    SYSTEM = """You are a billing specialist for a SaaS platform.
You handle: charges, invoices, refunds, subscription changes, payment issues.
Rules:
- Refunds over $100 require manager approval (set escalate: true)
- Always get transaction reference numbers when discussing charges
- Be precise about amounts and dates
Return JSON: {"response": "...", "confidence": 0.9, "escalate": false, "reasoning": "..."}"""

    def handle(self, ticket: str) -> AgentResult:
        return self._call_or_mock(ticket, "BillingSpecialist")

    def _call_or_mock(self, ticket: str, name: str) -> AgentResult:
        if not os.environ.get("OPENAI_API_KEY"):
            # Mock for demo
            escalate = "refund" in ticket.lower() and "$" in ticket
            return AgentResult(
                specialist=name,
                response=f"I understand your billing concern. Our billing team will review your account within 1 business day. For duplicate charges, refunds are processed within 48 hours. Please email billing@example.com for urgent matters.",
                confidence=0.85,
                escalate=escalate,
                reasoning="Billing inquiry — standard resolution process",
            )
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM},
                    {"role": "user", "content": ticket},
                ],
                response_format={"type": "json_object"},
                temperature=0, max_tokens=300,
            )
            data = json.loads(response.choices[0].message.content)
            return AgentResult(
                specialist=name,
                response=data.get("response", ""),
                confidence=float(data.get("confidence", 0.8)),
                escalate=bool(data.get("escalate", False)),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            return AgentResult(name, f"Error: {e}", 0.5, True, "Error")


class TechnicalSpecialist:
    """Handles bugs, errors, integrations, performance."""
    SYSTEM = """You are a technical support specialist.
You handle: bugs, errors, crashes, API issues, integration problems.
Rules:
- Get browser/OS/version info for frontend issues
- Get error messages and request IDs for API issues
- Critical bugs (data loss, security) must be escalated
Return JSON: {"response": "...", "confidence": 0.9, "escalate": false, "reasoning": "..."}"""

    def handle(self, ticket: str) -> AgentResult:
        if not os.environ.get("OPENAI_API_KEY"):
            critical = any(w in ticket.lower() for w in ["data loss", "breach", "down"])
            return AgentResult(
                specialist="TechnicalSpecialist",
                response="I understand you're experiencing a technical issue. Let me help troubleshoot. Please share: 1) The exact error message, 2) Your browser and OS version, 3) When it started happening. In the meantime, try clearing your browser cache and using an incognito window.",
                confidence=0.82,
                escalate=critical,
                reasoning="Technical issue — needs diagnostic info",
            )
        # Real LLM call would go here
        return AgentResult("TechnicalSpecialist", "Technical response", 0.8, False, "Technical")


class AccountSpecialist:
    """Handles account access, passwords, settings."""
    SYSTEM = """You are an account support specialist.
You handle: login issues, password resets, 2FA, account settings, team management.
Return JSON: {"response": "...", "confidence": 0.9, "escalate": false, "reasoning": "..."}"""

    def handle(self, ticket: str) -> AgentResult:
        if not os.environ.get("OPENAI_API_KEY"):
            return AgentResult(
                specialist="AccountSpecialist",
                response="I can help you regain access to your account. Here are the steps: 1. Visit our login page and click 'Forgot Password'. 2. Enter your account email. 3. Check your inbox for a reset link (valid 24 hours). 4. If you have 2FA issues, use your backup codes or email support@example.com.",
                confidence=0.92,
                escalate=False,
                reasoning="Standard account access recovery — KB solution available",
            )
        return AgentResult("AccountSpecialist", "Account response", 0.9, False, "Account")


# ──────────────────────────────────────────────────────────────
# Supervisor
# ──────────────────────────────────────────────────────────────

class SupervisorAgent:
    """
    Routes support tickets to the appropriate specialist.

    The supervisor's ONLY job is routing — it doesn't solve problems,
    it decides who should solve them.
    """

    ROUTING_SYSTEM = """You are a support supervisor. Route tickets to the correct specialist.

Specialists:
- billing: charges, invoices, refunds, payments, subscriptions
- technical: bugs, errors, crashes, API issues, performance
- account: login, password, 2FA, account settings, team access

Return JSON: {"route_to": "billing|technical|account", "confidence": 0.9, "reason": "..."}"""

    def __init__(self):
        self.workers = {
            "billing": BillingSpecialist(),
            "technical": TechnicalSpecialist(),
            "account": AccountSpecialist(),
        }

    def route(self, ticket: str) -> str:
        """Determine which specialist should handle this ticket."""
        if not os.environ.get("OPENAI_API_KEY"):
            # Rule-based routing fallback
            ticket_lower = ticket.lower()
            if any(w in ticket_lower for w in ["charge", "billing", "invoice", "refund", "payment"]):
                return "billing"
            elif any(w in ticket_lower for w in ["error", "bug", "crash", "api", "broken", "not working"]):
                return "technical"
            else:
                return "account"

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.ROUTING_SYSTEM},
                    {"role": "user", "content": ticket},
                ],
                response_format={"type": "json_object"},
                temperature=0, max_tokens=100,
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("route_to", "account")
        except Exception:
            return "account"

    def handle(self, ticket: str) -> AgentResult:
        """Route and handle a ticket end-to-end."""
        specialist_name = self.route(ticket)
        worker = self.workers.get(specialist_name, self.workers["account"])
        result = worker.handle(ticket)
        print(f"  Routed to: {specialist_name} (confidence: {result.confidence:.0%})")
        return result


def main():
    print("\n" + "=" * 60)
    print("  Supervisor/Worker Multi-Agent Demo")
    print("=" * 60)

    supervisor = SupervisorAgent()

    test_tickets = [
        "I was charged twice this month — two $79 charges on Jan 1 and Jan 15.",
        "My export keeps failing with a 500 error. Request ID: req_abc123.",
        "I can't log in. My authenticator app broke after my phone reset.",
    ]

    for ticket in test_tickets:
        print(f"\n  Ticket: '{ticket[:60]}...'")
        result = supervisor.handle(ticket)
        print(f"  Specialist: {result.specialist}")
        print(f"  Escalate: {result.escalate}")
        print(f"  Response: {result.response[:100]}...")
        print()


if __name__ == "__main__":
    main()
