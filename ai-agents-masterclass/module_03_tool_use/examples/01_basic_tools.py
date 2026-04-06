"""
01_basic_tools.py - OpenAI Function Calling Basics
====================================================
Module 3: Tool Use & Function Calling

Function calling is how LLMs interact with the real world. The LLM doesn't
execute code — it returns a structured request to call a function, and your
code executes it and returns the result.

This file shows the complete end-to-end flow:
1. Define tools as JSON schemas
2. Send to LLM with user message
3. LLM returns a tool_call request
4. Execute the function with the LLM's arguments
5. Return result to LLM
6. LLM formulates final response

Run with: python module_03_tool_use/examples/01_basic_tools.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Step 1: Define tools in OpenAI function calling format
# The description is critical — the LLM decides which tool to use
# based on the description, not by reading the code.
# ──────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer_account",
            "description": (
                "Retrieve a customer's account details including their subscription plan, "
                "account status, and membership duration. Use this when you need to know "
                "if a customer is on a paid plan or has an active account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The customer's email address",
                    }
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_help_articles",
            "description": (
                "Search the help center and knowledge base for articles relevant to "
                "a customer question. Returns a list of relevant article titles and content. "
                "Use this before answering questions about product features or troubleshooting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing what the customer needs help with",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of articles to return (default: 3)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": (
                "Create a new support ticket in the ticketing system. Use this when "
                "the customer's issue requires follow-up or cannot be resolved immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_email": {
                        "type": "string",
                        "description": "Customer's email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Brief description of the issue",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Priority level of the ticket",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the issue",
                    },
                },
                "required": ["customer_email", "subject", "priority", "description"],
            },
        },
    },
]

# ──────────────────────────────────────────────────────────────
# Step 2: Implement the actual functions
# These are called when the LLM requests them.
# ──────────────────────────────────────────────────────────────

def get_customer_account(email: str) -> dict:
    """Look up customer account info (mock implementation)."""
    # In production: query your database
    MOCK_ACCOUNTS = {
        "alice@example.com": {
            "customer_id": "cust_001",
            "name": "Alice Johnson",
            "plan": "Pro",
            "status": "active",
            "member_since": "2022-03-15",
            "billing_cycle": "monthly",
        },
        "bob@example.com": {
            "customer_id": "cust_002",
            "name": "Bob Smith",
            "plan": "Free",
            "status": "active",
            "member_since": "2023-11-01",
            "billing_cycle": None,
        },
    }
    account = MOCK_ACCOUNTS.get(email.lower())
    if account:
        return account
    return {"error": f"No account found for email: {email}"}


def search_help_articles(query: str, max_results: int = 3) -> list[dict]:
    """Search help articles (mock implementation)."""
    ARTICLES = [
        {
            "id": "art_001",
            "title": "How to Reset Your Password",
            "content": "Go to the login page, click 'Forgot Password', enter your email, and check your inbox.",
            "tags": ["password", "login", "access"],
        },
        {
            "id": "art_002",
            "title": "Managing Your Subscription",
            "content": "Upgrade or downgrade at Settings > Billing. Changes take effect at next billing cycle.",
            "tags": ["billing", "subscription", "plan"],
        },
        {
            "id": "art_003",
            "title": "Exporting Your Data",
            "content": "Dashboard > Settings > Export Data. CSV and JSON formats available. Enterprise: unlimited rows.",
            "tags": ["export", "data", "csv"],
        },
        {
            "id": "art_004",
            "title": "Two-Factor Authentication Setup",
            "content": "Enable 2FA at Account Settings > Security. Supports authenticator apps and SMS.",
            "tags": ["2fa", "security", "authenticator"],
        },
        {
            "id": "art_005",
            "title": "API Rate Limits",
            "content": "Free: 30 req/min. Pro: 500 req/min. Enterprise: custom. 429 error = rate limited.",
            "tags": ["api", "rate limit", "integration"],
        },
    ]

    query_lower = query.lower()
    matches = [
        a for a in ARTICLES
        if any(tag in query_lower for tag in a["tags"])
        or any(word in query_lower for word in a["title"].lower().split())
    ]
    return matches[:max_results] or ARTICLES[:1]  # Return at least 1 result


def create_support_ticket(
    customer_email: str,
    subject: str,
    priority: str,
    description: str,
) -> dict:
    """Create a support ticket (mock implementation)."""
    import random
    ticket_id = f"TKT-{random.randint(10000, 99999)}"
    return {
        "ticket_id": ticket_id,
        "status": "created",
        "customer_email": customer_email,
        "subject": subject,
        "priority": priority,
        "eta": "24 hours" if priority in ("low", "medium") else "4 hours",
    }


# ──────────────────────────────────────────────────────────────
# Step 3: Tool execution router
# ──────────────────────────────────────────────────────────────

def execute_tool(name: str, arguments: dict) -> Any:
    """Route tool calls to the appropriate function."""
    if name == "get_customer_account":
        return get_customer_account(**arguments)
    elif name == "search_help_articles":
        return search_help_articles(**arguments)
    elif name == "create_support_ticket":
        return create_support_ticket(**arguments)
    else:
        return {"error": f"Unknown tool: {name}"}


# ──────────────────────────────────────────────────────────────
# Step 4: Agent loop with tool calling
# ──────────────────────────────────────────────────────────────

def run_with_tools(user_message: str, verbose: bool = True) -> str:
    """
    Run the LLM with tool calling enabled.

    The loop:
    1. Call LLM with message and available tools
    2. If response contains tool_calls, execute them and loop
    3. If response has content (no tool_calls), return it
    """
    try:
        from openai import OpenAI
    except ImportError:
        return "openai not installed. Run: pip install openai"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY not set in .env file"

    client = OpenAI(api_key=api_key)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful customer support agent. "
                "Use tools to gather information before responding. "
                "Always look up customer accounts and search help articles before answering."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    if verbose:
        print(f"\n{'─' * 55}")
        print(f"User: {user_message}")

    for _iteration in range(10):  # Safety limit
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0,
        )

        choice = response.choices[0]
        message = choice.message

        if choice.finish_reason == "tool_calls":
            # LLM wants to call tools
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
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # Execute each requested tool
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                if verbose:
                    print(f"\n  → Tool: {fn_name}({json.dumps(fn_args)})")

                result = execute_tool(fn_name, fn_args)
                result_str = json.dumps(result, indent=2)

                if verbose:
                    print(f"  ← Result: {result_str[:150]}...")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                })

        else:
            # LLM produced a final text response
            final = message.content
            if verbose:
                print(f"\nAgent: {final}")
            return final

    return "Reached max iterations"


# ──────────────────────────────────────────────────────────────
# Demonstrate different tool calling scenarios
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  Tool Use Demo: Function Calling")
    print("=" * 55)

    test_cases = [
        # Case 1: Requires KB search
        "How do I reset my password?",
        # Case 2: Requires account lookup + KB search
        "My email is alice@example.com and I can't export my data",
        # Case 3: Requires creating a ticket
        "I'm having a serious bug that's breaking my entire workflow. Email: bob@example.com. Nothing seems to work.",
    ]

    for case in test_cases:
        try:
            run_with_tools(case)
            print()
        except Exception as e:
            print(f"\n  Error: {e}")
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                print("  Fix: Set OPENAI_API_KEY in your .env file")
                break


if __name__ == "__main__":
    main()
