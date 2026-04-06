"""
02_react_pattern.py - Full ReAct Implementation
================================================
Module 5: Planning & Reasoning

A complete ReAct (Reasoning + Acting) implementation using the
OpenAI function calling API. Unlike the text-based version in Module 2,
this uses structured tool calls for more reliable parsing.

The key insight of ReAct: explicit Thought before each Action
dramatically improves decision quality because the model must
commit to a reasoning step before choosing an action.

Run with: python module_05_planning_reasoning/examples/02_react_pattern.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ReActStep:
    """A single step in the ReAct loop."""
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


class ReActAgent:
    """
    ReAct agent using OpenAI function calling with explicit Thought steps.

    Each iteration:
    1. Model produces a Thought (reasoning)
    2. Model decides on an Action (tool call) or Final Answer
    3. If action: execute tool, add Observation, repeat
    4. If final: return the answer
    """

    SYSTEM = """You are a customer support agent using the ReAct pattern.

For EVERY response, start with your reasoning:
"Thought: [your reasoning about what to do next]"

Then either:
- Call a tool to gather more information, OR
- Provide the final answer if you have enough information

When you have enough information to answer the customer, call the final_answer tool.

Always look up information in the knowledge base before answering.
Always check customer account status when relevant."""

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "search_kb",
                "description": "Search the knowledge base for relevant support articles",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thought": {"type": "string", "description": "Your reasoning for this search"},
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["thought", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_customer",
                "description": "Look up customer account details by email",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thought": {"type": "string", "description": "Why you need this info"},
                        "email": {"type": "string", "description": "Customer email"},
                    },
                    "required": ["thought", "email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "final_answer",
                "description": "Provide the final response to the customer when you have enough information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thought": {"type": "string", "description": "Your final reasoning"},
                        "answer": {"type": "string", "description": "The complete response to send to the customer"},
                    },
                    "required": ["thought", "answer"],
                },
            },
        },
    ]

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def _search_kb(self, thought: str, query: str) -> str:
        """Mock KB search."""
        KB = {
            "password": "Reset password: click 'Forgot Password', enter email, check inbox.",
            "2fa": "2FA recovery: use backup codes or contact support@example.com.",
            "billing": "Billing disputes: email billing@example.com within 30 days.",
            "export": "Export issues: clear cache, try incognito, check file size limits.",
            "locked": "Locked accounts auto-unlock in 30 minutes; contact support for immediate help.",
        }
        query_lower = query.lower()
        results = [v for k, v in KB.items() if k in query_lower]
        return "\n".join(results) if results else "No relevant articles found."

    def _get_customer(self, thought: str, email: str) -> str:
        """Mock customer lookup."""
        CUSTOMERS = {
            "alice@example.com": {"name": "Alice", "plan": "Pro", "status": "active"},
            "bob@example.com": {"name": "Bob", "plan": "Free", "status": "active"},
        }
        customer = CUSTOMERS.get(email.lower())
        return json.dumps(customer) if customer else f"No customer found for {email}"

    def _execute_tool(self, name: str, args: dict) -> str:
        if name == "search_kb":
            return self._search_kb(**args)
        elif name == "get_customer":
            return self._get_customer(**args)
        elif name == "final_answer":
            return "__FINAL__"
        return f"Unknown tool: {name}"

    def run(self, user_message: str, max_steps: int = 6) -> tuple[str, list[ReActStep]]:
        """
        Run the ReAct loop.

        Returns:
            (final_answer, steps) — the answer and the trace of steps taken
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        except Exception as e:
            return f"Error: {e}", []

        messages = [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user_message},
        ]

        steps = []
        final_answer = None

        for step_num in range(1, max_steps + 1):
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.TOOLS,
                tool_choice="auto",
                temperature=0,
                max_tokens=600,
            )

            choice = response.choices[0]
            message = choice.message

            if choice.finish_reason == "tool_calls" and message.tool_calls:
                tool_call = message.tool_calls[0]
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                thought = fn_args.get("thought", "")
                step = ReActStep(
                    step_number=step_num,
                    thought=thought,
                    action=fn_name,
                    action_input=fn_args,
                )

                if fn_name == "final_answer":
                    final_answer = fn_args.get("answer", "")
                    step.is_final = True
                    step.final_answer = final_answer
                    steps.append(step)
                    break

                # Execute the tool
                observation = self._execute_tool(fn_name, fn_args)
                step.observation = observation
                steps.append(step)

                # Add to conversation
                messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": tool_call.function.arguments},
                    }],
                    "content": message.content,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                })

            else:
                # Model chose to respond directly
                final_answer = message.content or ""
                steps.append(ReActStep(
                    step_number=step_num,
                    thought="Decided to answer directly",
                    is_final=True,
                    final_answer=final_answer,
                ))
                break

        return final_answer or "No answer produced", steps


def demo():
    print("\n" + "=" * 60)
    print("  ReAct Agent Demo")
    print("=" * 60)

    agent = ReActAgent()
    question = "My email is alice@example.com and I can't log into my account after too many wrong attempts."

    print(f"\n  Question: {question}\n")

    try:
        answer, steps = agent.run(question)

        for step in steps:
            print(f"  Step {step.step_number}:")
            print(f"    Thought: {step.thought[:100]}")
            if step.action:
                print(f"    Action:  {step.action}({json.dumps(step.action_input, ensure_ascii=False)[:60]}...)")
            if step.observation:
                print(f"    Observe: {step.observation[:80]}...")
            if step.is_final:
                print(f"    FINAL:   {step.final_answer[:100]}...")
            print()

        print(f"\n  Final Answer:\n  {answer}")

    except Exception as e:
        if "api" in str(e).lower() or "key" in str(e).lower():
            print(f"  Skipped — add OPENAI_API_KEY to .env ({e})")
        else:
            raise


if __name__ == "__main__":
    demo()
