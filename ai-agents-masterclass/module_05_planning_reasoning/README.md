# Module 5: Planning & Reasoning

## What This Module Covers

LLMs are better at reasoning when you give them structure. This module covers three prompting and architecture patterns that dramatically improve agent reasoning quality: Chain of Thought, ReAct, and Plan-Execute.

## What You'll Build

| File | Pattern | When to Use |
|------|---------|-------------|
| `01_chain_of_thought.py` | CoT prompting | Single LLM call with complex reasoning |
| `02_react_pattern.py` | ReAct loop | Multi-step tasks with tool use |
| `03_plan_execute.py` | Plan-Execute | Long tasks with many steps |

## Key Concepts

### Chain of Thought (CoT)

Force the model to reason step-by-step before answering:

```
System: "Before providing your answer, show your reasoning step by step
         in a <thinking> block. Then provide your final answer."

User: "A customer on our Pro plan says they were charged twice this month.
       What should we do?"

Model:
<thinking>
Step 1: Is this a billing issue? Yes — duplicate charge.
Step 2: What information do I need? Customer ID, charge dates, amounts.
Step 3: What's the right action? Verify the duplicate, then issue refund.
Step 4: What's the priority? High — financial impact, trust issue.
</thinking>

This is a high-priority billing issue requiring immediate attention...
```

**Why it helps**: The model can't skip steps or jump to a conclusion. The reasoning process itself improves accuracy.

### ReAct Pattern

ReAct interleaves reasoning with actions in a loop:

```
Thought: I need to verify this is actually a duplicate charge
Action: get_billing_history(customer_id="abc-123", months=1)
Observation: [charge 2024-01-01 $79.00, charge 2024-01-15 $79.00]

Thought: Confirmed duplicate. Now I should check if there was a legitimate reason (plan change, etc.)
Action: get_account_changes(customer_id="abc-123", date_range="2024-01")
Observation: No plan changes in January

Thought: This is clearly a billing error. I should refund the duplicate charge.
Action: process_refund(customer_id="abc-123", amount=79.00, reason="duplicate_charge")
Observation: Refund processed, reference ID: REF-2024-001
```

### Plan-Execute Pattern

For complex multi-step tasks, separate planning from execution:

**Phase 1: Plan** (single LLM call)
```
Given this complex enterprise onboarding ticket, create a step-by-step plan:
1. Verify enterprise account status and tier
2. Check if SSO has been configured
3. Review team member count against plan limits
4. Check payment status
5. Identify blocking issues
6. Draft resolution addressing all issues
```

**Phase 2: Execute** (loop through each step)
Each step runs as its own mini-agent, using tools to gather data.

**Why separate planning from execution?**
- Better plans when not interrupted by tool calls
- Can review/modify the plan before execution
- Easier to resume if execution fails partway through

### Scratchpad Pattern

Give the model a private "scratchpad" for intermediate reasoning that isn't shown to users:

```python
SYSTEM = """
Use this format for every response:

<scratchpad>
[Your private reasoning and analysis here]
</scratchpad>

<response>
[Your final response to show the customer]
</response>
"""
```

Parse the `<response>` block for the actual output.

## How to Run the Examples

```bash
# All require OPENAI_API_KEY
python module_05_planning_reasoning/examples/01_chain_of_thought.py
python module_05_planning_reasoning/examples/02_react_pattern.py
python module_05_planning_reasoning/examples/03_plan_execute.py
```

## What's Next

Module 6 covers RAG (Retrieval-Augmented Generation) — giving the agent access to your knowledge base. This is what makes the agent actually knowledgeable about your product.
