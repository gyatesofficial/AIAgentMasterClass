"""
02_langchain_agent.py - LangChain Agent with Tools
====================================================
Module 8: Agent Frameworks

LangChain provides high-level abstractions for building agents:
- create_react_agent() — builds a ReAct agent from prompt + tools
- AgentExecutor — runs the agent loop with tool execution
- Tool — wraps Python functions with descriptions for the LLM
- ChatOpenAI — LLM interface with standard API

The key difference from raw OpenAI function calling:
- LangChain handles the Thought/Action/Observation loop
- Tools are registered by description, not JSON schema
- The AgentExecutor manages iteration limits and error handling
- Callbacks give visibility into each step

Run with: python module_08_frameworks/examples/02_langchain_agent.py
Requires: OPENAI_API_KEY in .env (or runs in mock mode)
"""

from __future__ import annotations

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Tool Definitions
# ──────────────────────────────────────────────────────────────
# In LangChain, tools are Python functions with type hints and docstrings.
# The docstring IS the tool description — the LLM reads it to decide when
# and how to use the tool.

def search_knowledge_base(query: str) -> str:
    """
    Search the customer support knowledge base for relevant articles.

    Use this tool when you need to find information about:
    - Password resets and account access
    - Billing policies and refunds
    - Technical issues and error codes
    - Product features and pricing

    Args:
        query: Search terms describing what the customer needs help with

    Returns:
        Relevant knowledge base content, or a message if nothing found
    """
    # Mock KB for demo
    KB = {
        "password": "Reset password: login page → Forgot Password → email → link (24h). Lock after 5 fails.",
        "billing": "Refunds: annual=30 days, monthly=none. Duplicates refunded 48h. billing@example.com",
        "export": "Export: Settings > Export Data. CSV/JSON. Free=1k rows, Pro=100k rows. Large: emailed 1h.",
        "api": "API limits: Free=30/min, Pro=500/min. 429=rate limited. Use exponential backoff.",
        "account": "Account suspended: payment failure → 30-day grace. Locked: auto-unlock 30min.",
    }

    query_lower = query.lower()
    results = []
    for keyword, content in KB.items():
        if keyword in query_lower:
            results.append(content)

    if results:
        return "\n\n".join(results)
    return "No specific articles found. Escalate to human agent if needed."


def get_customer_info(email: str) -> str:
    """
    Look up customer account information by email address.

    Use this tool when you need to:
    - Verify a customer's account exists
    - Check their subscription plan
    - See their account status

    Args:
        email: The customer's email address

    Returns:
        Customer account details or an error message
    """
    # Mock customer database
    CUSTOMERS = {
        "alice@example.com": {"name": "Alice Smith", "plan": "Pro", "status": "active", "since": "2023-01"},
        "bob@example.com": {"name": "Bob Jones", "plan": "Starter", "status": "active", "since": "2024-03"},
        "charlie@example.com": {"name": "Charlie Brown", "plan": "Free", "status": "suspended", "since": "2024-06"},
    }

    customer = CUSTOMERS.get(email.lower())
    if customer:
        return (
            f"Customer: {customer['name']}\n"
            f"Plan: {customer['plan']}\n"
            f"Status: {customer['status']}\n"
            f"Customer since: {customer['since']}"
        )
    return f"No customer found with email: {email}"


def check_ticket_status(ticket_id: str) -> str:
    """
    Check the status of a support ticket by its ID.

    Use this tool when a customer asks about an existing ticket
    or wants to know if their issue has been resolved.

    Args:
        ticket_id: The ticket ID (e.g., TKT-123)

    Returns:
        Ticket status and most recent update
    """
    TICKETS = {
        "TKT-001": {"status": "resolved", "agent": "Sarah", "note": "Password reset email sent"},
        "TKT-002": {"status": "in_progress", "agent": "Mike", "note": "Billing team reviewing charge"},
        "TKT-003": {"status": "open", "agent": None, "note": "Awaiting assignment"},
    }

    ticket = TICKETS.get(ticket_id.upper())
    if ticket:
        agent_info = f"Assigned to: {ticket['agent']}" if ticket["agent"] else "Not yet assigned"
        return f"Status: {ticket['status']}\n{agent_info}\nLatest note: {ticket['note']}"
    return f"Ticket not found: {ticket_id}"


# ──────────────────────────────────────────────────────────────
# LangChain Agent Builder
# ──────────────────────────────────────────────────────────────

def build_langchain_agent(verbose: bool = True):
    """
    Build a LangChain ReAct agent with support tools.

    Returns (agent_executor, None) on success, or (None, error_msg).
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return None, "OPENAI_API_KEY not set — using mock mode"

    try:
        from langchain_openai import ChatOpenAI
        from langchain.agents import create_react_agent, AgentExecutor
        from langchain.tools import tool
        from langchain import hub

        # Wrap our Python functions as LangChain Tools
        # The @tool decorator uses the function docstring as the tool description
        kb_tool = tool(search_knowledge_base)
        customer_tool = tool(get_customer_info)
        ticket_tool = tool(check_ticket_status)

        tools = [kb_tool, customer_tool, ticket_tool]

        # Create the LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        # Pull the standard ReAct prompt from LangChain Hub
        # This prompt structures: Thought → Action → Action Input → Observation
        try:
            prompt = hub.pull("hwchase17/react")
        except Exception:
            # Fallback if hub is unavailable
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template(
                "Answer the following questions as best you can. You have access to the following tools:\n\n"
                "{tools}\n\n"
                "Use the following format:\n\n"
                "Question: the input question you must answer\n"
                "Thought: you should always think about what to do\n"
                "Action: the action to take, should be one of [{tool_names}]\n"
                "Action Input: the input to the action\n"
                "Observation: the result of the action\n"
                "... (this Thought/Action/Action Input/Observation can repeat N times)\n"
                "Thought: I now know the final answer\n"
                "Final Answer: the final answer to the original input question\n\n"
                "Begin!\n\n"
                "Question: {input}\n"
                "Thought:{agent_scratchpad}"
            )

        # Create the agent (combines LLM + prompt + tools)
        agent = create_react_agent(llm, tools, prompt)

        # AgentExecutor handles the tool execution loop
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,          # Prints each Thought/Action/Observation
            max_iterations=5,         # Prevents infinite loops
            handle_parsing_errors=True,  # Gracefully handles LLM output errors
            return_intermediate_steps=True,  # Include reasoning chain in output
        )

        return executor, None

    except ImportError as e:
        return None, f"LangChain not installed: {e}"
    except Exception as e:
        return None, f"Failed to build agent: {e}"


# ──────────────────────────────────────────────────────────────
# Mock Agent (no API key needed)
# ──────────────────────────────────────────────────────────────

def run_mock_agent(query: str) -> dict:
    """
    Simulate agent behavior without an API key.

    Shows what the agent WOULD do: which tools it would call,
    in what order, and why.
    """
    query_lower = query.lower()

    steps = []
    final_answer = ""

    # Simulate tool selection logic
    if "ticket" in query_lower and any(c.isdigit() for c in query):
        # Extract ticket ID
        words = query.split()
        ticket_id = next((w for w in words if w.upper().startswith("TKT")), "TKT-001")
        result = check_ticket_status(ticket_id)
        steps.append(("check_ticket_status", ticket_id, result))
        final_answer = f"I checked ticket {ticket_id}: {result}"

    elif "@" in query_lower:
        # Email lookup
        email = next((w for w in query.split() if "@" in w), "unknown@example.com")
        result = get_customer_info(email)
        steps.append(("get_customer_info", email, result))
        final_answer = f"Customer lookup result: {result}"

    else:
        # KB search
        result = search_knowledge_base(query)
        steps.append(("search_knowledge_base", query[:50], result))
        final_answer = f"Based on our knowledge base: {result[:100]}"

    return {
        "input": query,
        "output": final_answer,
        "intermediate_steps": steps,
        "mode": "mock",
    }


# ──────────────────────────────────────────────────────────────
# Main Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  LangChain Agent Demo")
    print("=" * 60)

    agent_executor, error = build_langchain_agent(verbose=False)

    if agent_executor:
        print("  Using LangChain ReAct Agent with GPT-4o-mini\n")
        mode = "langchain"
    else:
        print(f"  {error}")
        print("  Running in mock mode to demonstrate concepts\n")
        mode = "mock"

    queries = [
        "I can't log into my account. Can you help?",
        "What's the status of ticket TKT-002?",
        "Look up the account for alice@example.com",
    ]

    for query in queries:
        print(f"  Query: '{query}'")

        if mode == "langchain":
            try:
                result = agent_executor.invoke({"input": query})
                print(f"  Answer: {result['output'][:200]}")
                if result.get("intermediate_steps"):
                    print(f"  Steps taken: {len(result['intermediate_steps'])}")
            except Exception as e:
                print(f"  Error: {e}")
        else:
            result = run_mock_agent(query)
            for tool_name, tool_input, tool_output in result.get("intermediate_steps", []):
                print(f"    Tool: {tool_name}('{tool_input}')")
                print(f"    Result: {str(tool_output)[:80]}...")
            print(f"  Answer: {result['output'][:200]}")

        print()

    print("  LangChain framework concepts demonstrated:")
    print("    - tool() decorator: wraps Python functions for LLM use")
    print("    - Docstring as tool description: LLM reads it to decide")
    print("    - create_react_agent(): builds Thought→Action→Observation loop")
    print("    - AgentExecutor: handles tool calling, limits, error recovery")
    print("    - verbose=True: shows full reasoning chain for debugging")


if __name__ == "__main__":
    main()
