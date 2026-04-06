"""
03_langgraph_graph.py - LangGraph Multi-Agent System
======================================================
Module 7: Multi-Agent Systems

LangGraph models agent workflows as directed graphs where:
- Nodes are functions that process state
- Edges define the flow between nodes
- Conditional edges enable dynamic routing
- State is a typed dict shared across all nodes

This demo implements the same support pipeline as 02_pipeline_pattern.py
but using LangGraph's StateGraph for comparison.

Key LangGraph concepts demonstrated:
1. TypedDict state schema
2. Node functions (pure functions that update state)
3. Conditional edges (route based on state)
4. Graph compilation and execution

Run with: python module_07_multi_agent/examples/03_langgraph_graph.py
"""

from __future__ import annotations

import os
from typing import Annotated, TypedDict, Optional
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# State Schema
# ──────────────────────────────────────────────────────────────

class SupportState(TypedDict, total=False):
    """
    The shared state that flows through the LangGraph pipeline.

    TypedDict gives us type safety without the overhead of dataclasses.
    LangGraph passes this dict between nodes; each node reads what it
    needs and writes its outputs back.

    Using total=False means all keys are optional — nodes only set
    the fields they're responsible for.
    """
    # Input fields (set at graph entry)
    ticket_id: str
    subject: str
    body: str
    customer_email: str

    # Set by intake node
    customer_name: str
    is_valid: bool
    validation_errors: list[str]

    # Set by triage node
    category: str
    priority: str
    triage_confidence: float

    # Set by resolution node
    draft_response: str
    should_escalate: bool
    escalation_reason: str

    # Set by quality node
    quality_score: float
    quality_issues: list[str]
    final_response: str
    approved: bool

    # Control flow
    error: Optional[str]
    stages_completed: list[str]


# ──────────────────────────────────────────────────────────────
# Node Functions
# ──────────────────────────────────────────────────────────────
# Each node is a plain function: SupportState -> dict
# The dict returned is MERGED into the state (not a replacement).
# This is the key LangGraph pattern: return only what you change.

def intake_node(state: SupportState) -> dict:
    """
    Validate and normalize the incoming ticket.

    Returns only the fields this node sets — LangGraph merges
    the return dict with the existing state automatically.
    """
    errors = []

    if "@" not in state.get("customer_email", ""):
        errors.append("Invalid email address")

    if len(state.get("subject", "")) < 5:
        errors.append("Subject too short")

    if len(state.get("body", "")) < 10:
        errors.append("Body too short")

    is_valid = len(errors) == 0

    # Extract name from email
    email = state.get("customer_email", "")
    customer_name = "Customer"
    if "@" in email:
        username = email.split("@")[0]
        customer_name = username.replace(".", " ").replace("_", " ").title()

    stages = state.get("stages_completed", []) + ["intake"]

    return {
        "is_valid": is_valid,
        "validation_errors": errors,
        "customer_name": customer_name,
        "stages_completed": stages,
    }


def triage_node(state: SupportState) -> dict:
    """
    Classify the ticket by category and priority.

    This node only runs if intake passed (controlled by conditional edge).
    """
    KB = {
        "password login": {"category": "account_access", "priority": "high", "confidence": 0.9},
        "charge billing payment": {"category": "billing", "priority": "high", "confidence": 0.85},
        "error bug crash": {"category": "technical_bug", "priority": "high", "confidence": 0.88},
        "feature request": {"category": "feature_request", "priority": "low", "confidence": 0.8},
    }

    text = f"{state.get('subject', '')} {state.get('body', '')}".lower()
    best_match = None
    best_score = 0

    for keywords, data in KB.items():
        score = sum(1 for k in keywords.split() if k in text)
        if score > best_score:
            best_score = score
            best_match = data

    if best_match:
        category = best_match["category"]
        priority = best_match["priority"]
        confidence = min(best_score * 0.3, 0.95)
    else:
        category = "general_inquiry"
        priority = "medium"
        confidence = 0.6

    stages = state.get("stages_completed", []) + ["triage"]

    return {
        "category": category,
        "priority": priority,
        "triage_confidence": confidence,
        "stages_completed": stages,
    }


def resolution_node(state: SupportState) -> dict:
    """
    Draft a response based on the triage classification.
    """
    name = state.get("customer_name", "there")
    category = state.get("category", "general_inquiry")

    if category == "account_access":
        draft = (
            f"Hi {name},\n\n"
            f"I understand you're having account access issues. Here's how to resolve this:\n\n"
            f"1. Go to the login page and click 'Forgot Password'\n"
            f"2. Enter your email address\n"
            f"3. Check your inbox for a reset link\n\n"
            f"The link is valid for 24 hours. Let me know if you need further help!"
        )
        should_escalate = False
        escalation_reason = None
    elif category == "billing":
        draft = (
            f"Hi {name},\n\n"
            f"Thank you for contacting us about your billing. "
            f"Our billing team will review your account and respond within 1 business day.\n\n"
            f"For urgent billing issues, please email billing@example.com."
        )
        should_escalate = True
        escalation_reason = "Billing issues require human review"
    elif category == "technical_bug":
        draft = (
            f"Hi {name},\n\n"
            f"I'm sorry to hear you're experiencing a technical issue. "
            f"To help me investigate, please share:\n\n"
            f"1. The exact error message you're seeing\n"
            f"2. Your browser and OS version\n"
            f"3. The steps that led to the error\n\n"
            f"Our technical team will prioritize this."
        )
        should_escalate = True
        escalation_reason = "Technical bugs need engineering review"
    else:
        draft = (
            f"Hi {name},\n\n"
            f"Thank you for your message. "
            f"Our team will look into this and get back to you within 24 hours."
        )
        should_escalate = False
        escalation_reason = None

    stages = state.get("stages_completed", []) + ["resolution"]

    result = {
        "draft_response": draft,
        "should_escalate": should_escalate,
        "stages_completed": stages,
    }
    if escalation_reason:
        result["escalation_reason"] = escalation_reason

    return result


def quality_node(state: SupportState) -> dict:
    """
    Review the draft response and compute a quality score.
    """
    draft = state.get("draft_response", "")
    category = state.get("category", "")

    issues = []
    score = 10.0

    if not any(draft.startswith(g) for g in ["Hi", "Hello", "Dear"]):
        issues.append("Missing greeting")
        score -= 2

    has_steps = "1." in draft or "step" in draft.lower()
    if category == "account_access" and not has_steps:
        issues.append("Should include step-by-step instructions")
        score -= 2

    word_count = len(draft.split())
    if word_count < 20:
        issues.append("Response too brief")
        score -= 3
    elif word_count > 500:
        issues.append("Response too long")
        score -= 1

    quality_score = max(0.0, min(10.0, score)) / 10.0
    approved = quality_score >= 0.6

    stages = state.get("stages_completed", []) + ["quality"]

    return {
        "quality_score": quality_score,
        "quality_issues": issues,
        "final_response": draft,
        "approved": approved,
        "stages_completed": stages,
    }


def invalid_ticket_node(state: SupportState) -> dict:
    """
    Handle tickets that failed intake validation.

    This is a terminal node — invalid tickets get a rejection response
    without going through triage, resolution, and quality.
    """
    errors = state.get("validation_errors", [])
    error_list = "\n".join(f"  - {e}" for e in errors)

    return {
        "final_response": (
            f"Your ticket could not be processed due to the following issues:\n"
            f"{error_list}\n\n"
            f"Please resubmit with the corrected information."
        ),
        "approved": False,
        "stages_completed": state.get("stages_completed", []) + ["rejected"],
    }


# ──────────────────────────────────────────────────────────────
# Routing Functions (for conditional edges)
# ──────────────────────────────────────────────────────────────

def route_after_intake(state: SupportState) -> str:
    """
    After intake, decide: proceed to triage, or reject.

    This function returns a string that LangGraph uses to select
    which edge to follow. The strings must match keys in the
    add_conditional_edges() mapping.
    """
    if state.get("is_valid", False):
        return "valid"
    else:
        return "invalid"


def route_after_quality(state: SupportState) -> str:
    """
    After quality check, decide: approve or flag for escalation.

    In a real system you might loop back for revision if quality is low.
    """
    if state.get("approved", False):
        return "approved"
    else:
        return "needs_revision"


# ──────────────────────────────────────────────────────────────
# Graph Construction
# ──────────────────────────────────────────────────────────────

def build_support_graph():
    """
    Build and compile the LangGraph support pipeline.

    The graph structure:
        START → intake → [route] → triage → resolution → quality → END
                              ↓
                        invalid_ticket → END

    Returns the compiled graph (ready to invoke) or None if LangGraph
    isn't installed.
    """
    try:
        from langgraph.graph import StateGraph, END, START
    except ImportError:
        return None

    # Create the graph with our state schema
    workflow = StateGraph(SupportState)

    # Add nodes (name → function)
    workflow.add_node("intake", intake_node)
    workflow.add_node("triage", triage_node)
    workflow.add_node("resolution", resolution_node)
    workflow.add_node("quality", quality_node)
    workflow.add_node("invalid_ticket", invalid_ticket_node)

    # Set entry point
    workflow.set_entry_point("intake")

    # Conditional edge: after intake, route based on validity
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "valid": "triage",        # valid tickets → triage
            "invalid": "invalid_ticket",  # invalid tickets → rejection
        },
    )

    # Linear edges: valid path
    workflow.add_edge("triage", "resolution")
    workflow.add_edge("resolution", "quality")

    # Conditional edge: after quality, decide final disposition
    # In this demo both paths go to END, but the routing logic
    # could loop back to resolution_node for revision
    workflow.add_conditional_edges(
        "quality",
        route_after_quality,
        {
            "approved": END,
            "needs_revision": END,  # Simplified: would loop in production
        },
    )

    # Terminal edge for invalid tickets
    workflow.add_edge("invalid_ticket", END)

    # Compile the graph (validates structure, returns a Runnable)
    return workflow.compile()


# ──────────────────────────────────────────────────────────────
# Pure-Python Fallback (no LangGraph)
# ──────────────────────────────────────────────────────────────

def run_pipeline_fallback(initial_state: SupportState) -> SupportState:
    """
    Run the same pipeline logic without LangGraph.

    This demonstrates that the node functions themselves are pure Python
    and testable in isolation — LangGraph is just the orchestrator.
    """
    state = dict(initial_state)

    # Intake
    state.update(intake_node(state))

    # Route after intake
    if state.get("is_valid", False):
        state.update(triage_node(state))
        state.update(resolution_node(state))
        state.update(quality_node(state))
    else:
        state.update(invalid_ticket_node(state))

    return state


# ──────────────────────────────────────────────────────────────
# Main Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  LangGraph Multi-Agent Pipeline Demo")
    print("=" * 60)

    graph = build_support_graph()
    if graph:
        print("  LangGraph available — using StateGraph\n")
        run_fn = lambda state: graph.invoke(state)
    else:
        print("  LangGraph not installed — using pure-Python fallback")
        print("  (Install with: pip install langgraph)\n")
        run_fn = run_pipeline_fallback

    tickets = [
        {
            "ticket_id": "TKT-001",
            "subject": "Can't log in",
            "body": "I forgot my password and can't access my account.",
            "customer_email": "alice@example.com",
            "stages_completed": [],
            "is_valid": False,  # Will be set by intake
        },
        {
            "ticket_id": "TKT-002",
            "subject": "Billing question",
            "body": "I was charged twice last month for $79 each.",
            "customer_email": "bob@example.com",
            "stages_completed": [],
            "is_valid": False,
        },
        {
            "ticket_id": "TKT-003",
            "subject": "Hi",  # Too short — will fail validation
            "body": "?",      # Too short — will fail validation
            "customer_email": "invalid-email",
            "stages_completed": [],
            "is_valid": False,
        },
    ]

    for ticket in tickets:
        print(f"  Processing: '{ticket['subject']}'")
        result = run_fn(ticket)

        print(f"    Stages: {' → '.join(result.get('stages_completed', []))}")
        print(f"    Valid: {result.get('is_valid', 'n/a')}")
        if result.get("category"):
            print(f"    Category: {result['category']} / Priority: {result['priority']}")
            print(f"    Confidence: {result.get('triage_confidence', 0):.0%}")
        if result.get("quality_score") is not None:
            print(f"    Quality: {result['quality_score']:.0%} (approved: {result['approved']})")
        if result.get("should_escalate"):
            print(f"    Escalate: {result['escalation_reason']}")
        if result.get("validation_errors"):
            print(f"    Errors: {result['validation_errors']}")
        response = result.get("final_response", "")
        if response:
            print(f"    Response: {response[:80]}...")
        print()


if __name__ == "__main__":
    main()
