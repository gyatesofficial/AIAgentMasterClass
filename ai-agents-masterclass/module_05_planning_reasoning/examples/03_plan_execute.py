"""
03_plan_execute.py - Plan-and-Execute Pattern
=============================================
Module 5: Planning & Reasoning

Plan-Execute separates reasoning from acting into two distinct phases:
1. PLAN: Generate a complete plan upfront (single LLM call)
2. EXECUTE: Work through each step (LLM + tools for each step)

Advantages over standard ReAct:
- Better plans (no interruptions from tool calls during planning)
- Can review/modify the plan before execution
- Easier to resume if execution fails
- Better for long multi-step tasks

Run with: python module_05_planning_reasoning/examples/03_plan_execute.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class PlanStep:
    """A single step in the plan."""
    number: int
    description: str
    tool: Optional[str] = None
    tool_args: Optional[dict] = None
    result: Optional[str] = None
    status: str = "pending"  # pending, completed, failed, skipped


@dataclass
class ExecutionResult:
    """The final result of executing a plan."""
    plan: list[PlanStep]
    final_answer: str
    success: bool
    steps_completed: int
    steps_total: int


PLANNER_SYSTEM = """You are a planning agent for customer support.

Given a support request, create a step-by-step plan to resolve it.
The plan should specify exactly what tools to call and in what order.

Available tools:
- search_kb(query): Search knowledge base
- get_customer(email): Get customer info
- check_billing(email): Check billing status
- check_ticket_history(email): Get previous tickets

Return a JSON array of steps:
[
  {"step": 1, "description": "...", "tool": "search_kb", "args": {"query": "..."}},
  {"step": 2, "description": "...", "tool": "get_customer", "args": {"email": "..."}},
  {"step": 3, "description": "Synthesize information and draft response", "tool": null, "args": null}
]

Be specific about tool arguments. Include a synthesis step at the end."""

EXECUTOR_SYSTEM = """You are an execution agent. You have:
1. A plan step to execute
2. Results from previous steps
3. A tool result (if applicable)

Synthesize the information and execute this step.
If this is the final synthesis step, write the complete customer response."""


class PlanExecuteAgent:
    """
    Implements the Plan-Execute pattern for complex support tickets.

    Phase 1: Planner creates a structured plan
    Phase 2: Executor works through each step
    Phase 3: Final synthesis produces the customer response
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def _call_llm(self, messages: list[dict], as_json: bool = False) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        kwargs = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": 1000}
        if as_json:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _execute_tool(self, tool: str, args: dict) -> str:
        """Mock tool execution."""
        if tool == "search_kb":
            query = args.get("query", "").lower()
            KB = {
                "password reset": "Reset: click Forgot Password → enter email → check inbox.",
                "2fa": "2FA recovery: use backup codes or contact support.",
                "billing": "Billing: contact billing@example.com for disputes.",
                "export": "Export: Settings > Export Data. Large files emailed within 1h.",
            }
            results = [v for k, v in KB.items() if k in query]
            return "\n".join(results) if results else "No KB results found."
        elif tool == "get_customer":
            email = args.get("email", "").lower()
            CUSTOMERS = {
                "alice@example.com": {"name": "Alice", "plan": "Pro", "joined": "2022"},
                "bob@example.com": {"name": "Bob", "plan": "Free", "joined": "2023"},
            }
            return json.dumps(CUSTOMERS.get(email, {"error": f"Not found: {email}"}))
        elif tool == "check_billing":
            return json.dumps({"status": "current", "last_charge": "$79 on Jan 1", "next_charge": "Feb 1"})
        elif tool == "check_ticket_history":
            return json.dumps({"count": 2, "last_ticket": "Password reset - Resolved Jan 10"})
        return f"Unknown tool: {tool}"

    def plan(self, request: str) -> list[PlanStep]:
        """Phase 1: Generate a complete plan for the request."""
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": f"Create a plan to resolve:\n{request}"},
        ]

        response = self._call_llm(messages)

        # Parse plan from response
        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                steps_data = json.loads(json_match.group())
            else:
                steps_data = json.loads(response)

            return [
                PlanStep(
                    number=s.get("step", i + 1),
                    description=s.get("description", ""),
                    tool=s.get("tool"),
                    tool_args=s.get("args"),
                )
                for i, s in enumerate(steps_data)
            ]
        except Exception:
            # Fallback plan
            return [
                PlanStep(1, "Search KB for relevant info", "search_kb", {"query": request[:50]}),
                PlanStep(2, "Synthesize and respond", None, None),
            ]

    def execute(self, request: str, plan: list[PlanStep]) -> ExecutionResult:
        """Phase 2: Execute each step in the plan."""
        context_so_far = f"Original request: {request}\n\nPlan execution:\n"

        for step in plan:
            print(f"    Executing step {step.number}: {step.description[:60]}...")

            if step.tool:
                # Execute the tool
                tool_result = self._execute_tool(step.tool, step.tool_args or {})
                step.result = tool_result
                step.status = "completed"
                context_so_far += f"\nStep {step.number} ({step.tool}): {tool_result[:100]}\n"
            else:
                # Synthesis step — call LLM to produce the response
                synthesis_messages = [
                    {"role": "system", "content": EXECUTOR_SYSTEM},
                    {"role": "user", "content": f"{context_so_far}\n\nNow write the final response to the customer."},
                ]
                final_response = self._call_llm(synthesis_messages)
                step.result = final_response
                step.status = "completed"

                return ExecutionResult(
                    plan=plan,
                    final_answer=final_response,
                    success=True,
                    steps_completed=sum(1 for s in plan if s.status == "completed"),
                    steps_total=len(plan),
                )

        # If no synthesis step, use context as response
        return ExecutionResult(
            plan=plan,
            final_answer=context_so_far,
            success=True,
            steps_completed=len(plan),
            steps_total=len(plan),
        )

    def run(self, request: str) -> ExecutionResult:
        """Full Plan-Execute cycle."""
        print(f"\n  [PLAN PHASE]")
        plan = self.plan(request)
        print(f"  Generated {len(plan)}-step plan:")
        for step in plan:
            tool_info = f" → {step.tool}" if step.tool else " → synthesis"
            print(f"    {step.number}. {step.description[:60]}{tool_info}")

        print(f"\n  [EXECUTE PHASE]")
        result = self.execute(request, plan)
        return result


def demo():
    print("\n" + "=" * 60)
    print("  Plan-Execute Agent Demo")
    print("=" * 60)

    request = (
        "My email is alice@example.com. I can't log in because my 2FA app "
        "stopped working after I got a new phone. I also noticed a charge "
        "I don't recognize. Please help!"
    )

    print(f"\n  Complex request: {request[:80]}...")

    try:
        agent = PlanExecuteAgent()
        result = agent.run(request)

        print(f"\n  [RESULT]")
        print(f"  Steps: {result.steps_completed}/{result.steps_total} completed")
        print(f"\n  Final Response:\n  {result.final_answer[:400]}")

    except Exception as e:
        if "api" in str(e).lower() or "key" in str(e).lower():
            print(f"\n  Skipped — add OPENAI_API_KEY to .env")
        else:
            raise


if __name__ == "__main__":
    demo()
