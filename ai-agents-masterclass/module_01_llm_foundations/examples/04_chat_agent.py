"""
04_chat_agent.py - Conversation History Management
====================================================
Module 1: LLM Foundations

A conversational agent needs to maintain state between turns. This module
shows how to manage conversation history, implement windowing (truncation),
and handle the system prompt lifecycle.

Key concepts:
- Messages list: the "working memory" for one conversation
- System prompt: the agent's persona and rules (always first)
- Windowing: keep last N messages to stay within context limits
- Role alternation: user → assistant → user (LLM APIs enforce this)

Run with: python module_01_llm_foundations/examples/04_chat_agent.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# Import the LLMClient from the previous example
import sys
sys.path.insert(0, os.path.dirname(__file__))
from llm_client_03 import LLMClient, LLMResponse, LLMAuthError

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Message dataclass
# ──────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str     # "user", "assistant", "system", "tool"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


# ──────────────────────────────────────────────────────────────
# ChatAgent
# ──────────────────────────────────────────────────────────────

class ChatAgent:
    """
    A conversational agent that maintains multi-turn history.

    Features:
    - Persistent conversation history
    - Window truncation (keeps last N messages)
    - System prompt management
    - Turn count and cost tracking

    Usage:
        agent = ChatAgent(
            model="gpt-4o",
            system_prompt="You are a helpful customer support agent.",
            max_history_messages=20,
        )

        while True:
            user_input = input("You: ")
            response = agent.chat(user_input)
            print(f"Agent: {response}")
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        system_prompt: str = "You are a helpful assistant.",
        max_history_messages: int = 20,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        llm_client: Optional[LLMClient] = None,
    ):
        """
        Initialize the chat agent.

        Args:
            model: LLM model to use
            system_prompt: The agent's persona and instructions
            max_history_messages: Maximum messages to keep in history.
                                  When exceeded, oldest messages are dropped.
                                  Always keeps the system prompt.
            temperature: Sampling temperature (0 = deterministic, 1 = creative)
            max_tokens: Maximum tokens in each response
            llm_client: Optional pre-configured LLMClient (creates one if not provided)
        """
        self.model = model
        self.system_prompt = system_prompt
        self.max_history_messages = max_history_messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = llm_client or LLMClient()

        # Conversation history (not including system prompt)
        # System prompt is passed separately to the API
        self._history: list[ChatMessage] = []

        # Stats
        self.turn_count = 0
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    # ── Main interface ──────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """
        Send a user message and get a response.

        This is the primary interface for the chat agent.
        Automatically manages history and truncation.

        Args:
            user_message: The user's input

        Returns:
            The agent's response as a string
        """
        # Add user message to history
        self._history.append(ChatMessage(role="user", content=user_message))

        # Trim history if over the window limit
        self._trim_history()

        # Call the LLM
        response = self.client.chat(
            messages=[m.to_dict() for m in self._history],
            model=self.model,
            system=self.system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Add assistant response to history
        self._history.append(
            ChatMessage(role="assistant", content=response.content)
        )

        # Update stats
        self.turn_count += 1
        self.total_cost_usd += response.cost_usd
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens

        return response.content

    def stream_chat(self, user_message: str):
        """
        Stream the agent's response.

        Yields string chunks as they arrive from the API.
        Updates history with the complete response when done.

        Usage:
            for chunk in agent.stream_chat("Hello"):
                print(chunk, end="", flush=True)
        """
        self._history.append(ChatMessage(role="user", content=user_message))
        self._trim_history()

        full_response = ""
        for chunk in self.client.stream(
            messages=[m.to_dict() for m in self._history],
            model=self.model,
            system=self.system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            full_response += chunk
            yield chunk

        # Add the complete response to history
        self._history.append(ChatMessage(role="assistant", content=full_response))
        self.turn_count += 1

    # ── History management ──────────────────────────────────

    def _trim_history(self) -> None:
        """
        Trim history to stay within max_history_messages.

        Strategy: Drop oldest messages (from the front) but never drop
        the most recent user message (we just added it).

        This is a sliding window — simple and predictable.
        See module_04 for more sophisticated approaches like summarization.
        """
        while len(self._history) > self.max_history_messages:
            # Remove the oldest message (front of list)
            removed = self._history.pop(0)
            # Log that we're truncating (useful for debugging)

    def clear_history(self) -> None:
        """Clear all conversation history. The system prompt remains."""
        self._history.clear()
        self.turn_count = 0

    def get_history(self) -> list[dict]:
        """Return conversation history as a list of dicts."""
        return [m.to_dict() for m in self._history]

    def get_history_length(self) -> int:
        """Return number of messages in history."""
        return len(self._history)

    # ── Context injection ────────────────────────────────────

    def inject_context(self, context: str) -> None:
        """
        Add context information that should persist throughout the conversation.

        Use this for things like:
        - Customer profile info
        - Ticket details being discussed
        - Retrieved KB articles

        The context is added as a user message followed by an
        acknowledgment, so it looks like a natural conversation start.
        """
        self._history.append(
            ChatMessage(
                role="user",
                content=f"[Context for this conversation]\n{context}"
            )
        )
        self._history.append(
            ChatMessage(
                role="assistant",
                content="Understood. I have this context and will use it to help you."
            )
        )

    # ── Stats ───────────────────────────────────────────────

    def print_stats(self) -> None:
        """Print conversation statistics."""
        print(f"\n  Conversation Stats:")
        print(f"  Turns:           {self.turn_count}")
        print(f"  History length:  {len(self._history)} messages")
        print(f"  Input tokens:    {self.total_input_tokens:,}")
        print(f"  Output tokens:   {self.total_output_tokens:,}")
        print(f"  Total cost:      ${self.total_cost_usd:.6f}")
        if self.turn_count > 0:
            avg = self.total_cost_usd / self.turn_count
            print(f"  Cost per turn:   ${avg:.6f}")


# ──────────────────────────────────────────────────────────────
# Example: Support Chat Agent
# ──────────────────────────────────────────────────────────────

SUPPORT_SYSTEM_PROMPT = """You are Alex, a friendly and knowledgeable customer support agent
for SaaStr Platform, a SaaS analytics tool.

Your role:
- Help customers resolve their support issues quickly and professionally
- Be empathetic — customers reaching out for support are often frustrated
- Ask clarifying questions when needed before jumping to solutions
- Escalate to human support if the issue is complex or the customer is very upset

What you can help with:
- Account access and password issues
- Billing questions and subscription management
- Technical troubleshooting
- Feature guidance

Limitations:
- You cannot process refunds directly — direct customers to billing@saastr.io
- You cannot access customer data — ask the customer for relevant information
- Do not make promises about future features

Keep responses concise and actionable."""


def demo_basic_conversation():
    """Show a simple multi-turn conversation."""
    print("\n" + "=" * 60)
    print("  Demo 1: Basic Multi-Turn Conversation")
    print("=" * 60)

    agent = ChatAgent(
        model="gpt-4o-mini",
        system_prompt=SUPPORT_SYSTEM_PROMPT,
        max_history_messages=10,
    )

    conversation = [
        "Hi, I can't log into my account",
        "I tried resetting my password but didn't get the email",
        "My email is alice@example.com",
        "OK I found the reset email! Got logged in. Thanks!",
    ]

    print("\n  Simulating a support conversation...\n")
    try:
        for user_msg in conversation:
            print(f"  Customer: {user_msg}")
            response = agent.chat(user_msg)
            print(f"  Agent:    {response}\n")
            print(f"  [History: {agent.get_history_length()} messages, "
                  f"Cost so far: ${agent.total_cost_usd:.4f}]")
            print()

        agent.print_stats()

    except LLMAuthError as e:
        print(f"\n  Skipped (no API key configured): {e}")
        print("  To run this demo: add OPENAI_API_KEY to your .env file")
    except Exception as e:
        print(f"\n  Error: {e}")


def demo_history_windowing():
    """
    Show how windowing works to stay within context limits.
    This demo doesn't require an API key — it just shows the data structure.
    """
    print("\n" + "=" * 60)
    print("  Demo 2: History Windowing (No API Key Needed)")
    print("=" * 60)

    # Small window for demonstration
    agent = ChatAgent(
        system_prompt="You are a test agent.",
        max_history_messages=6,
    )

    # Simulate adding messages to history directly
    for i in range(1, 11):
        agent._history.append(ChatMessage(role="user", content=f"Message {i} from user"))
        agent._history.append(ChatMessage(role="assistant", content=f"Response {i}"))

    print(f"\n  Added 10 user/assistant pairs = 20 messages total")
    print(f"  Max history: {agent.max_history_messages} messages")
    print(f"\n  Before trimming: {len(agent._history)} messages")

    agent._trim_history()

    print(f"  After trimming:  {len(agent._history)} messages")
    print(f"\n  Remaining messages (showing windowed history):")
    for msg in agent._history:
        print(f"    [{msg.role}]: {msg.content}")


def demo_context_injection():
    """Show how to inject customer context into a conversation."""
    print("\n" + "=" * 60)
    print("  Demo 3: Context Injection")
    print("=" * 60)

    agent = ChatAgent(
        model="gpt-4o-mini",
        system_prompt=SUPPORT_SYSTEM_PROMPT,
    )

    # Inject customer context before the conversation starts
    customer_context = """Customer Profile:
- Name: Bob Smith
- Email: bob@techstartup.com
- Plan: Pro ($79/month)
- Account status: Active
- Member since: January 2023
- Previous tickets: 2 (both resolved)
  - #001: Password reset - Resolved
  - #002: Export feature question - Resolved"""

    agent.inject_context(customer_context)
    print(f"\n  Injected customer profile (history: {agent.get_history_length()} messages)")

    print("\n  Now the agent knows about the customer before the first message...")
    try:
        response = agent.chat("I'm having trouble with the CSV export feature")
        print(f"\n  Customer: I'm having trouble with the CSV export feature")
        print(f"  Agent: {response}")
        print(f"\n  (Note: agent knows Bob is on Pro plan and had a previous export question)")
    except LLMAuthError as e:
        print(f"\n  Skipped (no API key): {e}")
    except Exception as e:
        print(f"\n  Error: {e}")


if __name__ == "__main__":
    # Rename the import for clarity
    import importlib, types
    # The file is named 03_llm_client.py which can't be imported directly
    # In real use, you'd put LLMClient in a package
    demo_history_windowing()  # No API key needed
    demo_basic_conversation()  # Needs API key
    demo_context_injection()   # Needs API key
