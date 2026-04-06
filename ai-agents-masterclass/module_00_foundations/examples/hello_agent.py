"""
hello_agent.py - The Agent Loop: Perceive → Think → Act → Observe
==================================================================
Module 0: Foundations

This file demonstrates the core agent loop concept using MOCK responses
only — no LLM API keys or external services required.

The agent answers a customer support question about password resets by:
1. Perceiving the input (reading the support ticket)
2. Thinking about what to do (mock LLM reasoning)
3. Acting (searching a mock knowledge base)
4. Observing the result (reading KB response)
5. Thinking again (mock LLM formulates answer)
6. Acting (producing a final response)

Run with: python module_00_foundations/examples/hello_agent.py
"""

import time
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────

@dataclass
class Message:
    """A single message in the agent's internal state."""
    role: str      # "user", "assistant", "tool"
    content: str
    tool_name: Optional[str] = None


@dataclass
class AgentState:
    """Everything the agent knows and has done so far."""
    ticket: str                         # The incoming support ticket
    messages: list[Message] = field(default_factory=list)
    iteration: int = 0
    final_response: Optional[str] = None
    is_done: bool = False


@dataclass
class ToolCall:
    """A request to invoke a tool."""
    name: str
    args: dict


@dataclass
class ThinkResult:
    """What the LLM 'decided' to do next."""
    reasoning: str
    tool_call: Optional[ToolCall] = None
    final_answer: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Mock "tools" — functions the agent can call
# ──────────────────────────────────────────────────────────────

MOCK_KNOWLEDGE_BASE = {
    "password reset": (
        "To reset your password: 1) Go to the login page and click 'Forgot Password'. "
        "2) Enter your email address. 3) Check your inbox for a reset link. "
        "4) The link expires in 24 hours. If you don't receive it, check spam."
    ),
    "two factor authentication": (
        "To disable 2FA: Go to Account Settings → Security → Two-Factor Authentication "
        "and click 'Disable'. You'll need to enter a current code to confirm."
    ),
    "account locked": (
        "Accounts are automatically unlocked after 30 minutes. "
        "For immediate assistance, contact support@example.com with your account email."
    ),
}


def search_knowledge_base(query: str) -> str:
    """
    Tool: Search the knowledge base for relevant articles.

    In production, this would embed the query and search ChromaDB.
    Here, we use simple keyword matching as a stand-in.
    """
    query_lower = query.lower()
    for keyword, article in MOCK_KNOWLEDGE_BASE.items():
        if keyword in query_lower:
            return f"Found article: {article}"
    return "No relevant article found."


# Registry maps tool names to functions
AVAILABLE_TOOLS = {
    "search_knowledge_base": search_knowledge_base,
}


# ──────────────────────────────────────────────────────────────
# Mock "LLM" — in Module 1, this becomes a real LLM call
# ──────────────────────────────────────────────────────────────

def mock_llm_think(state: AgentState) -> ThinkResult:
    """
    Simulate what an LLM would decide to do given the current state.

    In production (Module 1+), this is replaced with:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=state.messages,
            tools=TOOL_SCHEMAS,
        )

    The mock returns different results based on the iteration number so we
    can demonstrate the multi-step loop without real API calls.
    """
    iteration = state.iteration

    if iteration == 0:
        # First pass: decide to search the KB
        return ThinkResult(
            reasoning=(
                "The customer can't log in. Before I can help, I should check "
                "the knowledge base for troubleshooting steps."
            ),
            tool_call=ToolCall(
                name="search_knowledge_base",
                args={"query": "password reset login"},
            ),
        )
    elif iteration == 1:
        # Second pass: we have KB results, now formulate a response
        # Find the last tool message
        tool_results = [m for m in state.messages if m.role == "tool"]
        kb_content = tool_results[-1].content if tool_results else "No results"

        return ThinkResult(
            reasoning=(
                f"I found relevant KB content: '{kb_content[:80]}...'. "
                "I have enough information to answer the customer."
            ),
            final_answer=(
                "Hi there! I can help you get back into your account. "
                "Here's how to reset your password:\n\n"
                "1. Go to the login page and click 'Forgot Password'\n"
                "2. Enter the email address for your account\n"
                "3. Check your inbox for a password reset link\n"
                "4. The link expires after 24 hours\n\n"
                "If you don't see the email within a few minutes, check your spam folder. "
                "Let me know if you need any further help!"
            ),
        )
    else:
        # Should not reach here in this demo
        return ThinkResult(
            reasoning="I've already provided an answer.",
            final_answer="I've already answered this question.",
        )


# ──────────────────────────────────────────────────────────────
# The Agent Loop
# ──────────────────────────────────────────────────────────────

def run_agent(ticket: str, max_iterations: int = 5) -> str:
    """
    The core agent loop: Perceive → Think → Act → Observe → repeat.

    This is the fundamental pattern used by every agent in this course.
    The framework (LangGraph, LangChain) just makes this more sophisticated.

    Args:
        ticket: The customer's support request
        max_iterations: Safety limit to prevent infinite loops

    Returns:
        The agent's final response to the customer
    """
    print("\n" + "=" * 60)
    print("AGENT LOOP STARTING")
    print("=" * 60)

    # ── PERCEIVE ──────────────────────────────────────────────
    # Read the input from the environment
    state = AgentState(ticket=ticket)
    state.messages.append(Message(role="user", content=ticket))
    print(f"\n[PERCEIVE] Received ticket:\n  '{ticket}'")

    # ── LOOP ──────────────────────────────────────────────────
    while not state.is_done and state.iteration < max_iterations:
        state.iteration += 1
        print(f"\n{'─' * 40}")
        print(f"Iteration {state.iteration}")

        # ── THINK ─────────────────────────────────────────────
        # Ask the LLM what to do next, given everything we know
        print("[THINK] Reasoning about next step...")
        time.sleep(0.2)  # Simulate LLM latency
        think_result = mock_llm_think(state)
        print(f"  Reasoning: {think_result.reasoning}")

        # ── ACT ───────────────────────────────────────────────
        if think_result.final_answer is not None:
            # The LLM decided it has enough info — produce a final response
            print(f"\n[ACT] Producing final response (no tool call needed)")
            state.final_response = think_result.final_answer
            state.is_done = True

        elif think_result.tool_call is not None:
            # The LLM wants to call a tool — execute it
            tool = think_result.tool_call
            print(f"\n[ACT] Calling tool: {tool.name}({tool.args})")
            time.sleep(0.1)  # Simulate tool execution time

            # Execute the tool
            tool_fn = AVAILABLE_TOOLS.get(tool.name)
            if tool_fn is None:
                tool_output = f"Error: Unknown tool '{tool.name}'"
            else:
                tool_output = tool_fn(**tool.args)

            # ── OBSERVE ───────────────────────────────────────
            # Add the tool result to state so the LLM sees it next iteration
            state.messages.append(
                Message(role="tool", content=tool_output, tool_name=tool.name)
            )
            print(f"\n[OBSERVE] Tool returned:\n  '{tool_output[:100]}...'")

        else:
            # The LLM returned neither a tool call nor a final answer
            # This shouldn't happen with a well-designed prompt
            print("[ERROR] LLM returned no action — stopping loop")
            state.is_done = True

    # ── FINAL OUTPUT ──────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if state.final_response:
        print(f"AGENT COMPLETED after {state.iteration} iteration(s)")
        print(f"\nFinal Response:\n{state.final_response}")
    else:
        print(f"AGENT STOPPED (hit max iterations or error)")
        state.final_response = "I wasn't able to find a complete answer. Please contact support directly."

    print("=" * 60)
    return state.final_response


# ──────────────────────────────────────────────────────────────
# Demonstration
# ──────────────────────────────────────────────────────────────

def demonstrate_agent_loop():
    """Run the agent on a few example tickets to illustrate the loop."""

    tickets = [
        "I can't log into my account. I keep getting 'invalid password' even though I know it's correct.",
        "How do I turn off two factor authentication on my account?",
    ]

    for ticket in tickets:
        response = run_agent(ticket)
        print(f"\n✓ Customer would receive: '{response[:60]}...'")
        print()


# ──────────────────────────────────────────────────────────────
# Key Takeaways (printed as comments when run)
# ──────────────────────────────────────────────────────────────

KEY_CONCEPTS = """
KEY TAKEAWAYS FROM MODULE 0:
─────────────────────────────
1. The agent loop is simple: while not done → Think → Act → Observe
2. "Think" = LLM call (mocked here, real in Module 1)
3. "Act" = tool execution (KB search, DB query, API call)
4. "Observe" = adding tool result to messages so LLM sees it
5. The loop terminates when the LLM produces a final answer (no tool call)
6. max_iterations prevents infinite loops — always include this!

WHAT CHANGES IN LATER MODULES:
────────────────────────────────
Module 1:  mock_llm_think() → real OpenAI/Anthropic API call
Module 3:  more tools (customer DB, ticket management, email)
Module 4:  state includes persistent memory (Redis, ChromaDB)
Module 6:  KB search uses embeddings instead of keyword matching
Module 7:  multiple agents collaborate (triage + resolution + QA)
Module 8:  LangGraph manages the loop and state for us
"""


if __name__ == "__main__":
    print(KEY_CONCEPTS)
    demonstrate_agent_loop()
