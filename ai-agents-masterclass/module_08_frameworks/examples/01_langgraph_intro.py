"""
01_langgraph_intro.py - LangGraph Framework Introduction
=========================================================
Module 8: Agent Frameworks

LangGraph is a framework for building stateful, multi-step AI workflows
as directed graphs. It extends LangChain with explicit state management
and deterministic control flow.

Core concepts:
1. StateGraph — the graph container
2. State — a TypedDict shared across all nodes
3. Nodes — functions that transform state
4. Edges — connections between nodes
5. Conditional Edges — dynamic routing based on state
6. Checkpointing — persist state across runs (resumability)

Why LangGraph over raw Python?
- Visual graph structure makes workflows easy to understand
- Built-in state persistence (resume from any node after failure)
- Streaming support out of the box
- Human-in-the-loop: pause at any node for human approval
- Parallel branch execution

Run with: python module_08_frameworks/examples/01_langgraph_intro.py
"""

from __future__ import annotations

import os
from typing import TypedDict, Optional, Annotated
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Example 1: Minimal "Hello World" Graph
# ──────────────────────────────────────────────────────────────

class GreetingState(TypedDict):
    """State for the greeting graph."""
    name: str
    greeting: str
    farewell: str


def create_greeting_node(state: GreetingState) -> dict:
    """Node 1: Create a greeting."""
    return {"greeting": f"Hello, {state['name']}! Welcome to LangGraph."}


def create_farewell_node(state: GreetingState) -> dict:
    """Node 2: Create a farewell."""
    return {"farewell": f"Goodbye, {state['name']}! See you next time."}


def build_greeting_graph():
    """Build a minimal two-node graph."""
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        return None

    workflow = StateGraph(GreetingState)
    workflow.add_node("greet", create_greeting_node)
    workflow.add_node("farewell", create_farewell_node)

    workflow.set_entry_point("greet")
    workflow.add_edge("greet", "farewell")
    workflow.add_edge("farewell", END)

    return workflow.compile()


# ──────────────────────────────────────────────────────────────
# Example 2: Conditional Routing
# ──────────────────────────────────────────────────────────────

class TicketRouterState(TypedDict):
    """State for the ticket routing graph."""
    subject: str
    body: str
    route: str
    response: str


def analyze_ticket_node(state: TicketRouterState) -> dict:
    """Determine the ticket route based on content."""
    text = f"{state['subject']} {state['body']}".lower()

    if any(w in text for w in ["charge", "billing", "invoice", "refund"]):
        route = "billing"
    elif any(w in text for w in ["error", "bug", "crash", "broken"]):
        route = "technical"
    else:
        route = "general"

    return {"route": route}


def billing_response_node(state: TicketRouterState) -> dict:
    return {"response": "Billing team will review your account within 1 business day."}


def technical_response_node(state: TicketRouterState) -> dict:
    return {"response": "Technical team will investigate. Please share error details."}


def general_response_node(state: TicketRouterState) -> dict:
    return {"response": "Our support team will respond within 24 hours."}


def route_ticket(state: TicketRouterState) -> str:
    """Router function: returns the name of the next node."""
    return state["route"]  # "billing", "technical", or "general"


def build_router_graph():
    """Build a graph with conditional routing."""
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        return None

    workflow = StateGraph(TicketRouterState)

    # Add all nodes
    workflow.add_node("analyze", analyze_ticket_node)
    workflow.add_node("billing", billing_response_node)
    workflow.add_node("technical", technical_response_node)
    workflow.add_node("general", general_response_node)

    workflow.set_entry_point("analyze")

    # Conditional routing: after analyze, call route_ticket() to pick next node
    workflow.add_conditional_edges(
        "analyze",
        route_ticket,
        {
            "billing": "billing",
            "technical": "technical",
            "general": "general",
        }
    )

    # All response nodes go to END
    workflow.add_edge("billing", END)
    workflow.add_edge("technical", END)
    workflow.add_edge("general", END)

    return workflow.compile()


# ──────────────────────────────────────────────────────────────
# Example 3: Loop with Exit Condition
# ──────────────────────────────────────────────────────────────

class RetryState(TypedDict):
    """State for a retry loop graph."""
    query: str
    attempts: int
    max_attempts: int
    result: Optional[str]
    success: bool


def attempt_node(state: RetryState) -> dict:
    """
    Simulate an operation that might fail.

    In real use: this would call an LLM or external API.
    We simulate success on the 3rd attempt.
    """
    attempt_num = state.get("attempts", 0) + 1
    print(f"    Attempt {attempt_num}...")

    # Simulate: succeeds on attempt 3
    if attempt_num >= 3:
        return {
            "attempts": attempt_num,
            "result": f"Successfully processed '{state['query']}' on attempt {attempt_num}",
            "success": True,
        }
    else:
        return {
            "attempts": attempt_num,
            "result": None,
            "success": False,
        }


def should_retry(state: RetryState) -> str:
    """
    Decide: retry, or exit?

    This demonstrates how LangGraph handles loops — a conditional edge
    that routes back to the same node creates a loop.
    """
    if state.get("success", False):
        return "done"
    elif state.get("attempts", 0) >= state.get("max_attempts", 3):
        return "exhausted"
    else:
        return "retry"


def success_node(state: RetryState) -> dict:
    return {"result": state.get("result", "completed")}


def failure_node(state: RetryState) -> dict:
    return {"result": f"Failed after {state['attempts']} attempts"}


def build_retry_graph():
    """Build a graph with a retry loop."""
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        return None

    workflow = StateGraph(RetryState)

    workflow.add_node("attempt", attempt_node)
    workflow.add_node("success", success_node)
    workflow.add_node("failure", failure_node)

    workflow.set_entry_point("attempt")

    # Conditional edge that can loop back to "attempt"
    workflow.add_conditional_edges(
        "attempt",
        should_retry,
        {
            "retry": "attempt",      # Loop back!
            "done": "success",
            "exhausted": "failure",
        }
    )

    workflow.add_edge("success", END)
    workflow.add_edge("failure", END)

    return workflow.compile()


# ──────────────────────────────────────────────────────────────
# Pure-Python equivalents (fallback when LangGraph not installed)
# ──────────────────────────────────────────────────────────────

def run_greeting_fallback(name: str) -> dict:
    state = {"name": name, "greeting": "", "farewell": ""}
    state.update(create_greeting_node(state))
    state.update(create_farewell_node(state))
    return state


def run_router_fallback(subject: str, body: str) -> dict:
    state = {"subject": subject, "body": body, "route": "", "response": ""}
    state.update(analyze_ticket_node(state))
    route = route_ticket(state)
    if route == "billing":
        state.update(billing_response_node(state))
    elif route == "technical":
        state.update(technical_response_node(state))
    else:
        state.update(general_response_node(state))
    return state


def run_retry_fallback(query: str, max_attempts: int) -> dict:
    state = {"query": query, "attempts": 0, "max_attempts": max_attempts, "result": None, "success": False}
    while True:
        state.update(attempt_node(state))
        decision = should_retry(state)
        if decision == "retry":
            continue
        elif decision == "done":
            state.update(success_node(state))
            break
        else:
            state.update(failure_node(state))
            break
    return state


# ──────────────────────────────────────────────────────────────
# Main Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  LangGraph Framework Introduction")
    print("=" * 60)

    # Check if LangGraph is available
    try:
        import langgraph
        has_langgraph = True
        print(f"  LangGraph version: {langgraph.__version__}")
    except ImportError:
        has_langgraph = False
        print("  LangGraph not installed — using pure-Python equivalents")
        print("  (Install with: pip install langgraph)")

    # ── Example 1: Hello World Graph ──
    print("\n  [Example 1] Minimal Graph")
    if has_langgraph:
        graph = build_greeting_graph()
        result = graph.invoke({"name": "Alice", "greeting": "", "farewell": ""})
    else:
        result = run_greeting_fallback("Alice")
    print(f"    Greeting: {result['greeting']}")
    print(f"    Farewell: {result['farewell']}")

    # ── Example 2: Conditional Routing ──
    print("\n  [Example 2] Conditional Routing")
    tickets = [
        ("Double charge", "I was billed twice this month"),
        ("App crash", "The dashboard crashes when I export"),
        ("General question", "How do I invite team members?"),
    ]
    if has_langgraph:
        router = build_router_graph()

    for subject, body in tickets:
        if has_langgraph:
            result = router.invoke({"subject": subject, "body": body, "route": "", "response": ""})
        else:
            result = run_router_fallback(subject, body)
        print(f"    '{subject}' → [{result['route']}] {result['response'][:60]}...")

    # ── Example 3: Retry Loop ──
    print("\n  [Example 3] Retry Loop")
    if has_langgraph:
        retry_graph = build_retry_graph()
        result = retry_graph.invoke({"query": "classify ticket", "attempts": 0, "max_attempts": 5, "result": None, "success": False})
    else:
        result = run_retry_fallback("classify ticket", 5)
    print(f"    Result: {result['result']}")

    print("\n  Key LangGraph concepts demonstrated:")
    print("    - StateGraph: typed dict flows between nodes")
    print("    - Nodes: pure functions that return state updates")
    print("    - Edges: fixed connections between nodes")
    print("    - Conditional edges: dynamic routing at runtime")
    print("    - Loops: conditional edge routing back to earlier node")


if __name__ == "__main__":
    main()
