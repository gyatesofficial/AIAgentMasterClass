"""
01_chain_of_thought.py - Chain of Thought Prompting
=====================================================
Module 5: Planning & Reasoning

Chain of Thought (CoT) prompting forces the model to reason step-by-step
before producing an answer. This dramatically improves accuracy on complex
tasks like support ticket triage where multiple factors need to be weighed.

Patterns covered:
1. Zero-shot CoT ("Think step by step")
2. Few-shot CoT (examples in the prompt)
3. Scratchpad pattern (hidden reasoning)
4. Structured reasoning (specific steps to follow)

Run with: python module_05_planning_reasoning/examples/01_chain_of_thought.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import os
import re
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Pattern 1: Zero-shot Chain of Thought
# Simple and effective: just add "Think step by step"
# ──────────────────────────────────────────────────────────────

ZERO_SHOT_COT_SYSTEM = """You are a customer support triage expert.

Before classifying any ticket, think through it step by step:
1. What is the customer's core problem?
2. What category does this belong to?
3. How urgently does this need to be addressed?
4. Can this be resolved automatically?

Think step by step before giving your final answer."""


def zero_shot_cot(ticket: str, model: str = "gpt-4o-mini") -> str:
    """
    Zero-shot CoT: no examples, just instruction to reason step-by-step.

    Best for: novel situations where you don't have examples
    Works well when: the task is well-defined and the model is strong
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ZERO_SHOT_COT_SYSTEM},
                {"role": "user", "content": f"Triage this ticket:\n{ticket}"},
            ],
            temperature=0,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"


# ──────────────────────────────────────────────────────────────
# Pattern 2: Few-shot CoT (examples in prompt)
# Show the model how to reason with worked examples
# ──────────────────────────────────────────────────────────────

FEW_SHOT_EXAMPLES = """
Example 1:
Ticket: "I can't log in. Error says invalid credentials."

Reasoning:
- Core problem: Customer cannot access their account
- Category clues: "can't log in", "credentials" → account_access
- Urgency: No business context given, standard reset should work → medium
- Resolution: KB has password reset steps, this is auto-resolvable
- Conclusion: account_access / medium / auto-resolve

Output:
Category: account_access
Priority: medium
Auto-resolve: yes
Reasoning: Standard login issue with KB solution available.

---

Example 2:
Ticket: "I was charged $79 TWICE this month. This is the third time this has happened and I want a refund NOW."

Reasoning:
- Core problem: Duplicate billing charge, repeated occurrence
- Category clues: "charged twice", "refund" → billing
- Urgency: Financial impact + frustrated + repeated issue → high/critical
- Resolution: Billing disputes require human review, never auto-resolve
- Third occurrence = escalation pattern
- Conclusion: billing / high / escalate

Output:
Category: billing
Priority: high
Auto-resolve: no (escalate to billing team)
Reasoning: Duplicate charge + pattern of repeated billing issues requires human review.
"""

FEW_SHOT_COT_SYSTEM = f"""You are a customer support triage expert.

Use the examples below as a guide for how to reason through tickets.
Always follow the same Reasoning → Output format.

EXAMPLES:
{FEW_SHOT_EXAMPLES}"""


def few_shot_cot(ticket: str, model: str = "gpt-4o-mini") -> str:
    """
    Few-shot CoT: provide worked examples to guide reasoning.

    Best for: when you want consistent reasoning patterns
    Works well when: you have good examples that cover the space
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": FEW_SHOT_COT_SYSTEM},
                {"role": "user", "content": f"Triage this ticket:\n{ticket}"},
            ],
            temperature=0,
            max_tokens=600,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"


# ──────────────────────────────────────────────────────────────
# Pattern 3: Scratchpad pattern
# Hidden reasoning + public answer
# ──────────────────────────────────────────────────────────────

SCRATCHPAD_SYSTEM = """You are a customer support triage expert.

Use this exact format for EVERY response:

<scratchpad>
[Your private reasoning goes here. Be thorough.
Consider: category, priority, customer context, KB availability, escalation need]
</scratchpad>

<output>
{
  "category": "...",
  "priority": "...",
  "can_auto_resolve": true/false,
  "reasoning_summary": "one sentence for the audit log"
}
</output>

Only the content inside <output> is shown to humans."""


def scratchpad_cot(ticket: str, model: str = "gpt-4o-mini") -> dict:
    """
    Scratchpad pattern: separate private reasoning from public output.

    The model reasons freely in the scratchpad (not shown to users),
    then produces a clean structured output.

    Best for: when you want transparent reasoning but clean output
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SCRATCHPAD_SYSTEM},
                {"role": "user", "content": f"Triage:\n{ticket}"},
            ],
            temperature=0,
            max_tokens=800,
        )
        raw = response.choices[0].message.content

        # Parse scratchpad and output
        scratchpad_match = re.search(r"<scratchpad>(.*?)</scratchpad>", raw, re.DOTALL)
        output_match = re.search(r"<output>(.*?)</output>", raw, re.DOTALL)

        return {
            "scratchpad": scratchpad_match.group(1).strip() if scratchpad_match else "",
            "output": output_match.group(1).strip() if output_match else raw,
        }
    except Exception as e:
        return {"scratchpad": "", "output": f"Error: {e}"}


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

TEST_TICKETS = [
    "I can't log into my account. It says invalid credentials but I'm sure my password is right.",
    "You charged me twice in January! $79 both on the 1st and 15th. This is unacceptable. I want a refund IMMEDIATELY.",
    "Would love a dark mode option for the web app. My eyes get tired after long sessions.",
]


def main():
    print("\n" + "=" * 60)
    print("  Chain of Thought Prompting Demo")
    print("=" * 60)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or "your-key" in api_key:
        print("\n  API key not configured. Showing prompt patterns instead.\n")
        print("  Pattern 1 System Prompt (Zero-shot CoT):")
        print(ZERO_SHOT_COT_SYSTEM[:200] + "...")
        print("\n  Pattern 3 System Prompt (Scratchpad):")
        print(SCRATCHPAD_SYSTEM[:300] + "...")
        return

    ticket = TEST_TICKETS[1]  # Billing dispute (most interesting)
    print(f"\n  Ticket: '{ticket}'")

    print("\n  ── Pattern 1: Zero-shot CoT ──")
    result = zero_shot_cot(ticket)
    print(result[:400])

    print("\n  ── Pattern 2: Few-shot CoT ──")
    result = few_shot_cot(ticket)
    print(result[:400])

    print("\n  ── Pattern 3: Scratchpad ──")
    result = scratchpad_cot(ticket)
    print(f"  Private reasoning: {result['scratchpad'][:200]}...")
    print(f"\n  Public output: {result['output']}")


if __name__ == "__main__":
    main()
