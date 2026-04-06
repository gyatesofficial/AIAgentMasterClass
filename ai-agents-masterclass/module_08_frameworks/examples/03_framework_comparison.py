"""
03_framework_comparison.py - Framework Comparison
==================================================
Module 8: Agent Frameworks

Side-by-side comparison of three approaches to building the same agent:
1. Raw Python (no framework)
2. LangChain (high-level abstractions)
3. LangGraph (graph-based state machine)

All three implement the same support ticket handler with:
- KB search
- Customer lookup
- Draft response generation

This lets you see the tradeoffs clearly:
- Raw Python: maximum control, maximum boilerplate
- LangChain: fast to build, less control over flow
- LangGraph: explicit flow, best for complex multi-step workflows

Run with: python module_08_frameworks/examples/03_framework_comparison.py
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TypedDict, Optional, Any

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Shared: Mock Tools (used by all three approaches)
# ──────────────────────────────────────────────────────────────

MOCK_KB = {
    "password": "Reset at login > Forgot Password. 24h link. 5 fails = lock.",
    "billing": "Duplicate charges refunded 48h. billing@example.com.",
    "export": "Settings > Export Data. Pro: 100k rows.",
    "api": "Free: 30/min. Pro: 500/min. 429 = rate limited.",
}

MOCK_CUSTOMERS = {
    "alice@example.com": {"name": "Alice Smith", "plan": "Pro"},
    "bob@example.com": {"name": "Bob Jones", "plan": "Starter"},
}


def kb_search(query: str) -> str:
    """Search the knowledge base."""
    for key, content in MOCK_KB.items():
        if key in query.lower():
            return content
    return "No specific article found."


def customer_lookup(email: str) -> str:
    """Look up a customer by email."""
    c = MOCK_CUSTOMERS.get(email.lower())
    if c:
        return f"{c['name']} on {c['plan']} plan"
    return f"No customer found: {email}"


# ──────────────────────────────────────────────────────────────
# Approach 1: Raw Python
# ──────────────────────────────────────────────────────────────

@dataclass
class RawResult:
    approach: str
    answer: str
    steps: list[str]
    latency_ms: int


def raw_python_agent(subject: str, body: str, email: str) -> RawResult:
    """
    Pure Python implementation.

    Pros:
    + Zero dependencies
    + Complete control over flow
    + Easy to test and debug

    Cons:
    - All boilerplate written by hand
    - No built-in retry / error handling
    - Hard to add parallelism
    """
    start = time.time()
    steps = []

    # Step 1: Search KB
    query = f"{subject} {body}"
    kb_result = kb_search(query)
    steps.append(f"KB search: found {'result' if 'No specific' not in kb_result else 'nothing'}")

    # Step 2: Look up customer
    customer_info = customer_lookup(email)
    steps.append(f"Customer lookup: {customer_info[:40]}")

    # Step 3: Build response
    name = customer_info.split(" on ")[0] if " on " in customer_info else "Customer"
    if "No customer" not in customer_info:
        answer = f"Hi {name},\n\nBased on our KB: {kb_result}\n\nLet me know if you need more help!"
    else:
        answer = f"Thank you for contacting us. {kb_result}"

    latency = int((time.time() - start) * 1000)
    return RawResult("raw_python", answer, steps, latency)


# ──────────────────────────────────────────────────────────────
# Approach 2: LangChain (mock — shows structure without API call)
# ──────────────────────────────────────────────────────────────

def langchain_agent(subject: str, body: str, email: str) -> RawResult:
    """
    LangChain-style implementation (mocked without API key).

    In real LangChain:
        tools = [Tool(name="kb_search", func=kb_search, description="...")]
        agent = create_react_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools)
        result = executor.invoke({"input": f"{subject}: {body}"})

    Pros:
    + Minimal code once tools are defined
    + Built-in retry and error handling
    + LangSmith tracing out of the box
    + Easy tool management

    Cons:
    - Black-box flow (LLM decides order)
    - Harder to enforce strict sequences
    - More tokens spent on ReAct formatting
    """
    start = time.time()
    steps = []

    # Simulate what LangChain's AgentExecutor would do
    # (In real use, the LLM decides which tools to call)

    # The LLM would generate: "Thought: I need to look up the KB first"
    # "Action: kb_search"  "Action Input: password reset"
    kb_result = kb_search(f"{subject} {body}")
    steps.append(f"[LangChain] Tool call: kb_search → {kb_result[:40]}")

    # "Thought: I should look up the customer"
    # "Action: customer_lookup"
    customer_result = customer_lookup(email)
    steps.append(f"[LangChain] Tool call: customer_lookup → {customer_result[:40]}")

    # "Thought: I now have enough to answer"
    # "Final Answer: ..."
    name = customer_result.split(" on ")[0] if " on " in customer_result else "Customer"
    answer = f"Hi {name},\n\n{kb_result}\n\nIs there anything else I can help you with?"
    steps.append("[LangChain] Agent reached Final Answer")

    latency = int((time.time() - start) * 1000)
    return RawResult("langchain", answer, steps, latency)


# ──────────────────────────────────────────────────────────────
# Approach 3: LangGraph (mock — shows structure without LangGraph)
# ──────────────────────────────────────────────────────────────

class GraphState(TypedDict, total=False):
    """LangGraph state for the support workflow."""
    subject: str
    body: str
    email: str
    kb_result: str
    customer_info: str
    answer: str
    steps: list[str]


def lg_kb_search_node(state: GraphState) -> dict:
    """LangGraph node: search KB."""
    result = kb_search(f"{state['subject']} {state['body']}")
    steps = state.get("steps", []) + [f"[LangGraph] Node: kb_search → {result[:40]}"]
    return {"kb_result": result, "steps": steps}


def lg_customer_node(state: GraphState) -> dict:
    """LangGraph node: look up customer."""
    result = customer_lookup(state["email"])
    steps = state.get("steps", []) + [f"[LangGraph] Node: customer_lookup → {result[:40]}"]
    return {"customer_info": result, "steps": steps}


def lg_draft_node(state: GraphState) -> dict:
    """LangGraph node: draft the response."""
    customer_info = state.get("customer_info", "")
    name = customer_info.split(" on ")[0] if " on " in customer_info else "Customer"
    answer = (
        f"Hi {name},\n\n"
        f"Based on our records: {state.get('kb_result', 'No KB result')}\n\n"
        f"Please let us know if you need further assistance."
    )
    steps = state.get("steps", []) + ["[LangGraph] Node: draft_response"]
    return {"answer": answer, "steps": steps}


def langgraph_agent(subject: str, body: str, email: str) -> RawResult:
    """
    LangGraph-style implementation.

    In real LangGraph:
        workflow = StateGraph(GraphState)
        workflow.add_node("kb_search", lg_kb_search_node)
        workflow.add_node("customer_lookup", lg_customer_node)
        workflow.add_node("draft", lg_draft_node)
        workflow.set_entry_point("kb_search")
        workflow.add_edge("kb_search", "customer_lookup")
        workflow.add_edge("customer_lookup", "draft")
        workflow.add_edge("draft", END)
        graph = workflow.compile()
        result = graph.invoke({"subject": subject, "body": body, "email": email})

    Pros:
    + Explicit, deterministic flow
    + State is visible at every step
    + Easy to add conditional branches
    + Built-in checkpointing for resumability
    + Human-in-the-loop support

    Cons:
    - More boilerplate than LangChain for simple flows
    - TypedDict state can be verbose
    - Overkill for simple linear pipelines
    """
    start = time.time()

    # Simulate the graph execution
    state: GraphState = {"subject": subject, "body": body, "email": email, "steps": []}
    state.update(lg_kb_search_node(state))
    state.update(lg_customer_node(state))
    state.update(lg_draft_node(state))

    latency = int((time.time() - start) * 1000)
    return RawResult("langgraph", state["answer"], state.get("steps", []), latency)


# ──────────────────────────────────────────────────────────────
# Comparison Runner
# ──────────────────────────────────────────────────────────────

def compare_approaches(subject: str, body: str, email: str):
    """Run all three approaches and display side-by-side results."""
    print(f"\n  Ticket: '{subject}'")
    print(f"  Body: '{body[:60]}'")
    print(f"  Email: {email}")
    print()

    approaches = [
        ("Raw Python", raw_python_agent),
        ("LangChain", langchain_agent),
        ("LangGraph", langgraph_agent),
    ]

    for name, fn in approaches:
        result = fn(subject, body, email)
        print(f"  ── {name} ──")
        for step in result.steps:
            print(f"    {step}")
        print(f"    Answer: {result.answer[:100]}...")
        print(f"    Latency: {result.latency_ms}ms")
        print()


# ──────────────────────────────────────────────────────────────
# Framework Decision Guide
# ──────────────────────────────────────────────────────────────

DECISION_GUIDE = """
  When to use each framework:
  ─────────────────────────────────────────────────────────────
  Raw Python
    Use when: simple 1-2 step agents, learning, no dependencies allowed
    Avoid when: complex flows, need persistence, team collaboration

  LangChain
    Use when: rapid prototyping, standard ReAct loop, rich tool ecosystem
    Avoid when: strict flow control required, complex branching logic

  LangGraph
    Use when: multi-step workflows, conditional routing, human-in-the-loop,
              checkpointing/resumability, parallel execution needed
    Avoid when: simple single-step agents (overkill)

  Rule of thumb:
    Start with Raw Python to understand the pattern
    Move to LangChain for standard agent tasks
    Move to LangGraph when your flow has branches, loops, or human review
"""


def main():
    print("\n" + "=" * 60)
    print("  Framework Comparison Demo")
    print("=" * 60)
    print("  Running the same support agent with 3 different approaches")

    compare_approaches(
        subject="Can't reset my password",
        body="I tried forgot password but the link expired before I clicked it.",
        email="alice@example.com",
    )

    compare_approaches(
        subject="Billing question",
        body="I was charged twice. My account email is bob@example.com.",
        email="bob@example.com",
    )

    print(DECISION_GUIDE)


if __name__ == "__main__":
    main()
