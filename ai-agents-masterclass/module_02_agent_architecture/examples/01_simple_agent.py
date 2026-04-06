"""
01_simple_agent.py - The Minimal Agent Loop
============================================
Module 2: Agent Architecture Patterns

This is the minimal viable agent — the fewest lines of code that
still constitute a "real" agent with LLM calls and tool execution.

It answers support questions using:
1. An LLM call to decide what to do
2. Tool execution (knowledge base search)
3. Another LLM call to formulate the final response

Everything else in the course is an elaboration of this pattern.

Run with: python module_02_agent_architecture/examples/01_simple_agent.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Tool definitions (OpenAI function calling format)
# ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the knowledge base for articles relevant to a customer question",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_info",
            "description": "Look up a customer's account information by email",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Customer's email address",
                    }
                },
                "required": ["email"],
            },
        },
    },
]

# ──────────────────────────────────────────────────────────────
# Mock tool implementations
# ──────────────────────────────────────────────────────────────

MOCK_KB = {
    "password": "Reset password: 1) Click 'Forgot Password' on login page 2) Enter email 3) Check inbox for link 4) Link valid 24 hours",
    "login": "Login troubleshooting: Clear browser cache, try incognito mode, check Caps Lock, reset password if needed",
    "billing": "For billing issues, contact billing@support.io or go to Settings → Billing in your account",
    "export": "Export data: Dashboard → Data → Export → Choose CSV/JSON format → Download",
}

MOCK_CUSTOMERS = {
    "alice@example.com": {"name": "Alice Johnson", "plan": "Pro", "status": "active", "since": "2022-03-15"},
    "bob@example.com": {"name": "Bob Smith", "plan": "Starter", "status": "active", "since": "2023-07-22"},
}


def search_knowledge_base(query: str) -> str:
    """Search KB for relevant articles."""
    query_lower = query.lower()
    results = []
    for keyword, content in MOCK_KB.items():
        if keyword in query_lower:
            results.append(content)
    return "\n".join(results) if results else "No relevant articles found."


def get_customer_info(email: str) -> str:
    """Get customer account information."""
    customer = MOCK_CUSTOMERS.get(email)
    if customer:
        return json.dumps(customer)
    return json.dumps({"error": f"No customer found with email {email}"})


def execute_tool(name: str, arguments: dict) -> str:
    """Route tool calls to the appropriate function."""
    if name == "search_knowledge_base":
        return search_knowledge_base(**arguments)
    elif name == "get_customer_info":
        return get_customer_info(**arguments)
    else:
        return f"Error: Unknown tool '{name}'"


# ──────────────────────────────────────────────────────────────
# The Minimal Agent
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful customer support agent.
Use the available tools to find information before responding.
Always search the knowledge base first, then get customer info if you have an email.
Give concise, helpful responses."""


def run_simple_agent(user_message: str, max_iterations: int = 5) -> str:
    """
    The minimal agent loop.

    1. Send user message to LLM with available tools
    2. If LLM returns tool calls → execute them, append results, repeat
    3. If LLM returns text response → we're done, return it

    Args:
        user_message: The customer's support request
        max_iterations: Safety limit for the tool-calling loop

    Returns:
        The agent's final response
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    print(f"\n{'─' * 50}")
    print(f"Ticket: {user_message}")
    print(f"{'─' * 50}")

    for iteration in range(max_iterations):
        # Step 1: Call the LLM
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        message = response.choices[0].message

        # Step 2: Did the LLM want to call tools?
        if message.tool_calls:
            # Add the assistant's message (with tool calls) to history
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # Execute each tool call and add results to messages
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                print(f"\n[Tool Call #{iteration + 1}] {fn_name}({fn_args})")
                result = execute_tool(fn_name, fn_args)
                print(f"[Tool Result] {result[:100]}...")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        else:
            # Step 3: No tool calls = final response
            final_response = message.content
            print(f"\n[Final Response after {iteration + 1} iteration(s)]")
            print(f"{final_response}")
            return final_response

    return "Max iterations reached without a final response."


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

TEST_TICKETS = [
    "I can't log in to my account. I keep getting invalid password errors.",
    "How do I export my data? My email is alice@example.com",
    "Can you help me understand my billing options?",
]


def main():
    print("\n" + "=" * 55)
    print("  Minimal Agent Loop Demo")
    print("=" * 55)
    print("  Model: gpt-4o-mini")
    print("  Pattern: while tool_calls: execute_tools()")

    try:
        for ticket in TEST_TICKETS:
            run_simple_agent(ticket)
            print()

    except Exception as e:
        if "api_key" in str(e).lower() or "authentication" in str(e).lower():
            print(f"\n  Error: {e}")
            print("  Fix: Add OPENAI_API_KEY to your .env file")
        else:
            raise


if __name__ == "__main__":
    main()
