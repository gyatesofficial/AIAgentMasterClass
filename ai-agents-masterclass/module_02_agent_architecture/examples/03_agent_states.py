"""
03_agent_states.py - Agent State Patterns
==========================================
Module 2: Agent Architecture Patterns

This module shows three different approaches to agent state management
and when to use each one. The right choice depends on whether you need
to remember context between turns, sessions, or users.

Pattern 1: Stateless / Single-Pass
- No memory between calls
- Best for: classification, one-shot Q&A, triage

Pattern 2: Stateful Single Session
- Remembers within one conversation
- Best for: multi-turn chat, guided troubleshooting

Pattern 3: Persistent / Multi-Session
- Remembers across sessions (requires external storage)
- Best for: ongoing customer relationships, learning preferences

Run with: python module_02_agent_architecture/examples/03_agent_states.py
Requires: OPENAI_API_KEY in .env (optional — demos work without it)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────────────────────
# Pattern 1: Stateless Agent
# ──────────────────────────────────────────────────────────────

@dataclass
class TriageResult:
    """Output of the triage agent — pure data, no state."""
    category: str
    priority: str
    can_auto_resolve: bool
    confidence: float
    reasoning: str


class StatelessTriageAgent:
    """
    A stateless agent that classifies each ticket independently.

    Characteristics:
    - No memory of previous calls
    - Each call is completely independent
    - Trivially parallelizable (no shared state)
    - Ideal for batch processing

    Use for: classification, scoring, extraction tasks where
    each input is independent of others.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def triage(self, ticket_subject: str, ticket_body: str) -> TriageResult:
        """
        Triage a single ticket.

        This is a pure function — same inputs always produce the same output.
        No state is read or modified.
        """
        # In production: real LLM call
        # For demo: rule-based mock
        text = f"{ticket_subject} {ticket_body}".lower()

        # Category classification (simplified rules)
        if any(w in text for w in ["password", "login", "access", "locked"]):
            category = "account_access"
            priority = "high" if "urgent" in text or "immediately" in text else "medium"
            can_auto = True
            confidence = 0.92
        elif any(w in text for w in ["charge", "bill", "payment", "refund"]):
            category = "billing"
            priority = "high" if "twice" in text or "duplicate" in text else "medium"
            can_auto = False  # Always involve human for billing disputes
            confidence = 0.88
        elif any(w in text for w in ["bug", "error", "broken", "crash", "not working"]):
            category = "technical_bug"
            priority = "high"
            can_auto = False
            confidence = 0.85
        elif any(w in text for w in ["feature", "would be great", "request", "add"]):
            category = "feature_request"
            priority = "low"
            can_auto = True
            confidence = 0.90
        else:
            category = "general_inquiry"
            priority = "low"
            can_auto = True
            confidence = 0.75

        return TriageResult(
            category=category,
            priority=priority,
            can_auto_resolve=can_auto,
            confidence=confidence,
            reasoning=f"Detected keywords matching {category} pattern",
        )


# ──────────────────────────────────────────────────────────────
# Pattern 2: Stateful Single-Session Agent
# ──────────────────────────────────────────────────────────────

@dataclass
class SessionState:
    """
    Mutable state for a single support session.

    This is the "working memory" for one conversation.
    It exists only in-process and is lost when the session ends.
    """
    session_id: str
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    current_ticket_id: Optional[str] = None
    issue_category: Optional[str] = None

    # Multi-turn conversation history
    conversation: list[dict] = field(default_factory=list)

    # Things the agent has learned about this issue in this session
    gathered_facts: list[str] = field(default_factory=list)

    # Actions taken this session
    actions_taken: list[str] = field(default_factory=list)

    # Session metadata
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    turn_count: int = 0

    def add_message(self, role: str, content: str) -> None:
        self.conversation.append({"role": role, "content": content})
        if role == "user":
            self.turn_count += 1

    def add_fact(self, fact: str) -> None:
        """Record something learned about the customer's issue."""
        self.gathered_facts.append(fact)

    def add_action(self, action: str) -> None:
        """Record an action taken (for transparency and audit)."""
        self.actions_taken.append(f"{datetime.utcnow().isoformat()}: {action}")

    def get_context_summary(self) -> str:
        """Summarize gathered context for the LLM."""
        parts = []
        if self.customer_name:
            parts.append(f"Customer: {self.customer_name}")
        if self.issue_category:
            parts.append(f"Issue type: {self.issue_category}")
        if self.gathered_facts:
            parts.append("Known facts:\n" + "\n".join(f"  - {f}" for f in self.gathered_facts))
        return "\n".join(parts) if parts else "No context gathered yet"


class StatefulSupportAgent:
    """
    A stateful agent that maintains a conversation session.

    The agent accumulates information across turns and uses it to
    give increasingly informed responses as the conversation progresses.

    Use for: multi-turn troubleshooting, onboarding flows,
    any scenario where context from earlier turns matters.
    """

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    def start_session(self, session_id: str, customer_email: str = None) -> SessionState:
        """Create a new session for a customer interaction."""
        state = SessionState(
            session_id=session_id,
            customer_email=customer_email,
        )
        self._sessions[session_id] = state
        return state

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve an existing session."""
        return self._sessions.get(session_id)

    def respond(self, session_id: str, user_message: str) -> str:
        """
        Process a user message within an existing session.

        The response is informed by all previous turns in the session.
        """
        state = self._sessions.get(session_id)
        if not state:
            return "Error: Session not found. Call start_session() first."

        state.add_message("user", user_message)

        # In production: real LLM call with state.conversation as history
        # For demo: rule-based mock that uses accumulated state
        response = self._mock_respond(state, user_message)

        state.add_message("assistant", response)
        return response

    def _mock_respond(self, state: SessionState, message: str) -> str:
        """Mock response generation using accumulated session state."""
        msg_lower = message.lower()
        turn = state.turn_count

        if turn == 1:
            # First turn: greet and ask about the issue
            state.add_fact("Issue reported: login problem")
            state.issue_category = "account_access"
            return ("Hi! I'm sorry to hear you're having trouble. "
                    "Can you tell me what error message you're seeing when you try to log in?")

        elif turn == 2:
            # Second turn: we have error details
            state.add_fact(f"Error: {message[:50]}")
            if "locked" in msg_lower:
                state.add_action("Identified: account locked")
                return ("Got it — your account is locked. This happens after too many failed login attempts. "
                        "Can I get your email address so I can unlock it?")
            else:
                return ("Thanks for the details. Let me check a few things. "
                        "Could you try resetting your password using the 'Forgot Password' link?")

        elif turn == 3:
            # Third turn: email provided or password reset response
            if "@" in message:
                email = message.strip()
                state.customer_email = email
                state.add_fact(f"Email confirmed: {email}")
                state.add_action(f"Account lookup for {email}")
                return (f"Thanks! I've looked up your account at {email}. "
                        "I've sent an unlock email — you should receive it within 5 minutes.")
            else:
                return "If you can't reset it yourself, please share your email and I'll send you a reset link."

        else:
            # Subsequent turns
            if any(word in msg_lower for word in ["thanks", "thank you", "got it", "works", "fixed"]):
                state.add_action("Issue resolved")
                return (f"Great! I'm glad that worked, {state.customer_name or 'there'}. "
                        f"Is there anything else I can help you with today?")
            else:
                return ("I'm here to help! Let me know if you need anything else, "
                        f"and I have all our previous context from this conversation.")

    def end_session(self, session_id: str) -> dict:
        """End a session and return a summary."""
        state = self._sessions.pop(session_id, None)
        if not state:
            return {"error": "Session not found"}

        return {
            "session_id": session_id,
            "turns": state.turn_count,
            "customer_email": state.customer_email,
            "issue_category": state.issue_category,
            "facts_gathered": state.gathered_facts,
            "actions_taken": state.actions_taken,
            "duration_estimate": f"{state.turn_count * 45}s",
        }


# ──────────────────────────────────────────────────────────────
# Pattern 3: Persistent Multi-Session Memory
# ──────────────────────────────────────────────────────────────

@dataclass
class CustomerMemory:
    """
    Long-term memory about a customer, persisted across sessions.

    In production: stored in Redis or PostgreSQL.
    Here: in-memory dict for demonstration.
    """
    customer_id: str
    email: str
    preferences: dict = field(default_factory=dict)
    issue_history: list[dict] = field(default_factory=list)
    escalation_count: int = 0
    last_contact: Optional[str] = None

    def add_issue(self, category: str, resolution: str):
        """Record a resolved issue for future reference."""
        self.issue_history.append({
            "date": datetime.utcnow().isoformat(),
            "category": category,
            "resolution": resolution,
        })
        self.last_contact = datetime.utcnow().isoformat()

    def get_context_for_agent(self) -> str:
        """Summarize memory for injection into the agent's prompt."""
        lines = [f"Customer: {self.email}"]
        if self.issue_history:
            recent = self.issue_history[-3:]  # Last 3 issues
            lines.append(f"Previous issues ({len(self.issue_history)} total):")
            for issue in recent:
                lines.append(f"  - {issue['category']}: {issue['resolution'][:50]}")
        if self.escalation_count > 0:
            lines.append(f"⚠️ Escalated {self.escalation_count}x before — handle carefully")
        if "preferred_channel" in self.preferences:
            lines.append(f"Prefers: {self.preferences['preferred_channel']}")
        return "\n".join(lines)


class PersistentMemoryAgent:
    """
    Agent that maintains customer memories across multiple sessions.

    This is how you build a support system that "knows" the customer
    and can reference their history, preferences, and patterns.

    In production:
    - Memories stored in Redis with TTL
    - Rich memories stored in PostgreSQL
    - Vector embeddings in ChromaDB for semantic retrieval

    See Module 4 for the production implementation.
    """

    def __init__(self):
        # In production, this would be Redis or a DB query
        self._memory_store: dict[str, CustomerMemory] = {}

    def get_or_create_memory(self, customer_email: str) -> CustomerMemory:
        """Get existing memory for a customer or create new."""
        if customer_email not in self._memory_store:
            self._memory_store[customer_email] = CustomerMemory(
                customer_id=f"cust_{len(self._memory_store) + 1}",
                email=customer_email,
            )
        return self._memory_store[customer_email]

    def respond(self, customer_email: str, message: str) -> str:
        """
        Respond to a customer using their historical context.

        The agent reads the customer's memory at the start of each
        interaction, giving it knowledge of past issues and preferences.
        """
        memory = self.get_or_create_memory(customer_email)
        context = memory.get_context_for_agent()

        # In production: inject context into LLM system prompt
        # For demo: personalized mock response
        if memory.issue_history:
            last_issue = memory.issue_history[-1]["category"]
            return (f"Welcome back! I can see you've contacted us {len(memory.issue_history)} time(s) before, "
                    f"most recently about {last_issue}. How can I help you today?")
        else:
            return "Welcome! I don't see any previous contact from you. How can I help you today?"

    def record_resolution(self, customer_email: str, category: str, resolution: str):
        """Record a resolved issue to the customer's long-term memory."""
        memory = self.get_or_create_memory(customer_email)
        memory.add_issue(category, resolution)


# ──────────────────────────────────────────────────────────────
# Demonstration
# ──────────────────────────────────────────────────────────────

def demo_stateless():
    print("\n" + "=" * 60)
    print("  Pattern 1: Stateless Triage Agent")
    print("=" * 60)
    print("\n  Each ticket is classified independently — no shared state\n")

    agent = StatelessTriageAgent()

    tickets = [
        ("Can't log in", "I forgot my password and can't get into my account"),
        ("Charged twice!", "There are two $79 charges on my card this month"),
        ("App crashes", "The mobile app crashes whenever I try to open it"),
        ("Dark mode?", "Would love to have a dark mode option in the UI"),
    ]

    for subject, body in tickets:
        result = agent.triage(subject, body)
        print(f"  Ticket: '{subject}'")
        print(f"    Category: {result.category}")
        print(f"    Priority: {result.priority}")
        print(f"    Auto-resolve: {result.can_auto_resolve}")
        print(f"    Confidence: {result.confidence:.0%}\n")


def demo_stateful():
    print("\n" + "=" * 60)
    print("  Pattern 2: Stateful Single-Session Agent")
    print("=" * 60)
    print("\n  Context accumulates across turns within one session\n")

    agent = StatefulSupportAgent()
    session_id = "session-abc-001"

    state = agent.start_session(session_id, customer_email=None)
    print(f"  Session started: {session_id}\n")

    conversation = [
        "I can't log into my account",
        "It says my account is locked",
        "My email is alice@example.com",
        "Yes I got the unlock email, it works now! Thanks!",
    ]

    for user_msg in conversation:
        print(f"  Customer: {user_msg}")
        response = agent.respond(session_id, user_msg)
        print(f"  Agent:    {response}\n")

    summary = agent.end_session(session_id)
    print("  Session Summary:")
    for key, value in summary.items():
        print(f"    {key}: {value}")


def demo_persistent():
    print("\n" + "=" * 60)
    print("  Pattern 3: Persistent Memory (Cross-Session)")
    print("=" * 60)
    print("\n  Customer history is remembered across separate sessions\n")

    agent = PersistentMemoryAgent()
    email = "alice@example.com"

    # Simulate first contact — no history
    print("  === First Contact (no history) ===")
    resp = agent.respond(email, "Hi, I need help with my account")
    print(f"  Agent: {resp}\n")
    agent.record_resolution(email, "account_access", "Password reset via email link")

    # Second contact — agent remembers previous issue
    print("  === Second Contact (1 previous issue) ===")
    resp = agent.respond(email, "I have another question")
    print(f"  Agent: {resp}\n")
    agent.record_resolution(email, "billing", "Explained Pro plan pricing")

    # Third contact — agent knows full history
    print("  === Third Contact (2 previous issues) ===")
    resp = agent.respond(email, "Having trouble again")
    print(f"  Agent: {resp}")
    print(f"\n  Customer memory: {agent._memory_store[email].issue_history}")


def demo_when_to_use_each():
    """Print a decision guide for choosing an agent state pattern."""
    print("\n" + "=" * 60)
    print("  Decision Guide: Which State Pattern to Use?")
    print("=" * 60)

    guide = """
  ┌─────────────────────────────────────────────────────────┐
  │ Does your agent need context from the same conversation?│
  │                                                         │
  │  NO → Pattern 1: Stateless                             │
  │    Examples: ticket classification, sentiment analysis,  │
  │    content moderation, one-shot Q&A                     │
  │    Pros: Simple, parallelizable, predictable            │
  │    Cons: No memory, can't handle follow-ups             │
  │                                                         │
  │  YES → Does it need context from past sessions?         │
  │                                                         │
  │    NO → Pattern 2: Stateful Single-Session              │
  │      Examples: troubleshooting chat, form filling,      │
  │      guided onboarding                                  │
  │      Pros: Natural conversation flow                    │
  │      Cons: State lost when session ends                 │
  │                                                         │
  │    YES → Pattern 3: Persistent Multi-Session            │
  │      Examples: customer support history, personalization,│
  │      learning from past interactions                    │
  │      Pros: Knows the customer, builds on history        │
  │      Cons: Requires external storage (Redis/DB)         │
  └─────────────────────────────────────────────────────────┘

  Our Support Platform uses ALL THREE:
  • Triage agent: Stateless (each ticket classified independently)
  • Resolution chat: Stateful (follows up within a ticket's conversation)
  • Customer profile: Persistent (references past issues and preferences)
    """
    print(guide)


if __name__ == "__main__":
    demo_stateless()
    demo_stateful()
    demo_persistent()
    demo_when_to_use_each()
