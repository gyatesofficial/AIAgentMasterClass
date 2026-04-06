"""
05_structured_outputs.py - Getting Structured JSON from LLMs
=============================================================
Module 1: LLM Foundations

Agents need structured data (category, priority, confidence score),
not unstructured prose. This module shows two reliable approaches:

1. OpenAI: response_format={"type": "json_object"} or JSON Schema
2. Anthropic: Tool trick — force the model to "call" a tool with the schema

Both approaches use Pydantic to validate the output, catching cases
where the model doesn't quite follow the schema.

Run with: python module_01_llm_foundations/examples/05_structured_outputs.py
Requires: OPENAI_API_KEY and/or ANTHROPIC_API_KEY in .env
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Import our LLMClient
# ──────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(__file__))
try:
    from llm_client_03 import LLMClient, LLMAuthError
except ImportError:
    # Fallback: define a minimal stub if the import fails
    class LLMAuthError(Exception): pass
    class LLMClient:
        def chat(self, *args, **kwargs):
            raise LLMAuthError("LLMClient not available")


# ──────────────────────────────────────────────────────────────
# Pydantic models for structured outputs
# These define exactly what we expect the LLM to return.
# ──────────────────────────────────────────────────────────────

class TicketTriage(BaseModel):
    """
    Structured triage result for a support ticket.
    The LLM must return data matching this schema.
    """
    category: str = Field(
        description="One of: account_access, billing, technical_bug, feature_request, general_inquiry"
    )
    priority: str = Field(
        description="One of: low, medium, high, critical"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the classification (0.0 to 1.0)"
    )
    reasoning: str = Field(
        description="Brief explanation of why this category and priority were assigned"
    )
    can_auto_resolve: bool = Field(
        description="Whether this ticket can likely be resolved without human intervention"
    )
    suggested_response: Optional[str] = Field(
        default=None,
        description="Draft response to send to the customer, if can_auto_resolve is true"
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid = {"account_access", "billing", "technical_bug", "feature_request", "general_inquiry"}
        if v not in valid:
            raise ValueError(f"category must be one of {valid}, got '{v}'")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        valid = {"low", "medium", "high", "critical"}
        if v not in valid:
            raise ValueError(f"priority must be one of {valid}, got '{v}'")
        return v


class SentimentAnalysis(BaseModel):
    """Sentiment analysis of a customer message."""
    sentiment: str = Field(description="One of: positive, neutral, negative, frustrated, angry")
    urgency: int = Field(ge=1, le=5, description="Urgency level 1 (low) to 5 (very high)")
    emotion_tags: list[str] = Field(description="List of detected emotions, e.g. ['frustrated', 'confused']")
    summary: str = Field(description="One-sentence summary of the customer's situation")


# ──────────────────────────────────────────────────────────────
# Approach 1: OpenAI JSON Mode
# ──────────────────────────────────────────────────────────────

def get_structured_output_openai_json_mode(
    ticket: str,
    client: LLMClient,
) -> Optional[TicketTriage]:
    """
    Use OpenAI's json_object response format.

    Pros: Simple, any modern OpenAI model supports it
    Cons: No schema enforcement — model might return valid JSON
          that doesn't match your schema (must validate with Pydantic)
    """
    system = """You are a customer support triage agent.
Analyze the support ticket and return a JSON object with these exact fields:
{
  "category": "account_access" | "billing" | "technical_bug" | "feature_request" | "general_inquiry",
  "priority": "low" | "medium" | "high" | "critical",
  "confidence": 0.0-1.0,
  "reasoning": "why you chose this category and priority",
  "can_auto_resolve": true | false,
  "suggested_response": "draft response if can_auto_resolve is true, else null"
}

Important: Return ONLY valid JSON, no other text."""

    from openai import OpenAI
    openai_client = OpenAI()

    messages = [{"role": "user", "content": f"Triage this ticket:\n\n{ticket}"}]

    try:
        import openai
        raw_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = raw_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system}] + messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=500,
        )
        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)
        return TicketTriage(**data)  # Validate with Pydantic

    except ValidationError as e:
        print(f"  Validation error — model returned wrong structure: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Approach 2: OpenAI Structured Outputs (JSON Schema enforcement)
# ──────────────────────────────────────────────────────────────

def get_structured_output_openai_schema(
    ticket: str,
) -> Optional[TicketTriage]:
    """
    Use OpenAI's strict JSON Schema enforcement (gpt-4o and newer).

    Pros: Schema is strictly enforced by the API — no validation surprises
    Cons: Requires gpt-4o or newer, schema must be a supported subset of JSON Schema
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Define the JSON schema for the response
        triage_schema = {
            "name": "ticket_triage",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["account_access", "billing", "technical_bug", "feature_request", "general_inquiry"]
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"]
                    },
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "can_auto_resolve": {"type": "boolean"},
                    "suggested_response": {"type": ["string", "null"]},
                },
                "required": ["category", "priority", "confidence", "reasoning", "can_auto_resolve", "suggested_response"],
                "additionalProperties": False,
            }
        }

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a customer support triage agent."},
                {"role": "user", "content": f"Triage this ticket:\n\n{ticket}"}
            ],
            response_format={"type": "json_schema", "json_schema": triage_schema},
            temperature=0,
        )

        data = json.loads(response.choices[0].message.content)
        return TicketTriage(**data)

    except Exception as e:
        print(f"  Error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Approach 3: Anthropic Tool Trick
# ──────────────────────────────────────────────────────────────

def get_structured_output_anthropic_tool_trick(
    ticket: str,
) -> Optional[TicketTriage]:
    """
    Use Anthropic's tool calling to get structured output.

    The trick: define a "tool" called "triage_ticket" with your schema,
    then force the model to call it. The tool call's arguments are
    your structured output.

    Anthropic doesn't have a native JSON mode (as of 2025), so this
    is the recommended pattern.
    """
    try:
        import anthropic as anthropic_sdk
        client = anthropic_sdk.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        triage_tool = {
            "name": "triage_ticket",
            "description": "Triage a customer support ticket and return structured analysis",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["account_access", "billing", "technical_bug", "feature_request", "general_inquiry"],
                        "description": "The category of the support ticket"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Priority level"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence in classification (0.0 to 1.0)"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation"
                    },
                    "can_auto_resolve": {
                        "type": "boolean",
                        "description": "Whether this can be auto-resolved"
                    },
                    "suggested_response": {
                        "type": "string",
                        "description": "Draft response if can_auto_resolve is true"
                    },
                },
                "required": ["category", "priority", "confidence", "reasoning", "can_auto_resolve"],
            },
        }

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=[triage_tool],
            tool_choice={"type": "tool", "name": "triage_ticket"},  # Force tool use
            messages=[
                {"role": "user", "content": f"Triage this support ticket:\n\n{ticket}"}
            ],
            system="You are a customer support triage agent.",
        )

        # Extract the tool use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "triage_ticket":
                data = block.input
                # Add None for optional field if missing
                data.setdefault("suggested_response", None)
                return TicketTriage(**data)

        print("  Model didn't call the expected tool")
        return None

    except ValidationError as e:
        print(f"  Validation error: {e}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Approach 4: LangChain .with_structured_output() (convenience wrapper)
# ──────────────────────────────────────────────────────────────

def get_structured_output_langchain(ticket: str) -> Optional[TicketTriage]:
    """
    Use LangChain's .with_structured_output() method.

    This is a convenience wrapper around approaches 1-3 above.
    LangChain figures out the best method for each model.
    """
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(TicketTriage)

        result = structured_llm.invoke(
            f"Triage this support ticket:\n\n{ticket}"
        )
        return result

    except ImportError:
        print("  LangChain not installed. Run: pip install langchain-openai")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Helper to print results
# ──────────────────────────────────────────────────────────────

def print_triage_result(result: Optional[TicketTriage], approach: str) -> None:
    if result is None:
        print(f"  {approach}: FAILED")
        return

    print(f"\n  {approach}:")
    print(f"  Category:         {result.category}")
    print(f"  Priority:         {result.priority}")
    print(f"  Confidence:       {result.confidence:.0%}")
    print(f"  Can Auto-Resolve: {result.can_auto_resolve}")
    print(f"  Reasoning:        {result.reasoning[:80]}...")
    if result.suggested_response:
        print(f"  Draft Response:   {result.suggested_response[:80]}...")


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

SAMPLE_TICKETS = [
    {
        "subject": "Can't log in — locked out",
        "body": "I've been trying to log in for 2 hours. It says my account is locked after too many attempts. I have an important presentation in 30 minutes and NEED access. My email is alice@example.com",
    },
    {
        "subject": "Charged twice this month",
        "body": "I see two charges of $79 on my credit card this month, once on the 1st and once on the 15th. I only have one account. Please refund the duplicate charge.",
    },
    {
        "subject": "Would be great to have dark mode",
        "body": "I use your app 8 hours a day and a dark mode option would really reduce eye strain. Any plans to add this? Would love it!",
    },
]


def demo_structured_outputs():
    """Compare structured output approaches on real tickets."""
    print("\n" + "=" * 65)
    print("  Structured Outputs Demo")
    print("=" * 65)

    ticket_text = f"{SAMPLE_TICKETS[0]['subject']}\n\n{SAMPLE_TICKETS[0]['body']}"
    print(f"\n  Test Ticket:\n  {ticket_text}\n")

    print("\n  Testing each approach:")
    print(f"  {'─' * 60}")

    # Approach 1: OpenAI JSON Mode
    print("\n  Approach 1: OpenAI json_object mode")
    if os.environ.get("OPENAI_API_KEY"):
        result = get_structured_output_openai_json_mode(ticket_text, None)
        print_triage_result(result, "OpenAI JSON Mode")
    else:
        print("  Skipped — OPENAI_API_KEY not set")

    # Approach 2: OpenAI JSON Schema
    print("\n  Approach 2: OpenAI JSON Schema (strict enforcement)")
    if os.environ.get("OPENAI_API_KEY"):
        result = get_structured_output_openai_schema(ticket_text)
        print_triage_result(result, "OpenAI JSON Schema")
    else:
        print("  Skipped — OPENAI_API_KEY not set")

    # Approach 3: Anthropic Tool Trick
    print("\n  Approach 3: Anthropic tool trick")
    if os.environ.get("ANTHROPIC_API_KEY"):
        result = get_structured_output_anthropic_tool_trick(ticket_text)
        print_triage_result(result, "Anthropic Tool Trick")
    else:
        print("  Skipped — ANTHROPIC_API_KEY not set")

    # Approach 4: LangChain
    print("\n  Approach 4: LangChain .with_structured_output()")
    if os.environ.get("OPENAI_API_KEY"):
        result = get_structured_output_langchain(ticket_text)
        print_triage_result(result, "LangChain")
    else:
        print("  Skipped — OPENAI_API_KEY not set")


def demo_validation():
    """Show Pydantic catching schema violations."""
    print("\n" + "=" * 65)
    print("  Demo: Pydantic Validation Catching Bad LLM Output")
    print("=" * 65)

    # Simulate a case where the LLM returned an invalid category
    bad_json = {
        "category": "login_problem",  # Invalid! Not in the enum
        "priority": "very_urgent",    # Invalid! Not in the enum
        "confidence": 1.5,            # Invalid! > 1.0
        "reasoning": "User can't log in",
        "can_auto_resolve": True,
        "suggested_response": None,
    }

    print("\n  Simulated LLM response with invalid fields:")
    print(f"  {json.dumps(bad_json, indent=2)}")

    print("\n  Running through Pydantic validation...")
    try:
        result = TicketTriage(**bad_json)
    except ValidationError as e:
        print(f"\n  Validation caught {len(e.errors())} error(s):")
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            print(f"    - {field}: {error['msg']}")
        print("\n  Without validation, these errors would silently corrupt downstream logic!")


if __name__ == "__main__":
    demo_validation()  # No API key needed
    demo_structured_outputs()  # Needs API keys
