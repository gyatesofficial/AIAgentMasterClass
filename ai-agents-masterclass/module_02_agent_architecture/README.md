# Module 2: Agent Architecture Patterns

## What This Module Covers

There are many ways to structure an agent. This module covers the three fundamental patterns you'll see in production systems: simple agents, ReAct agents, and stateful agents. Knowing when to use each pattern is as important as knowing how to implement them.

## What You'll Build

| File | Pattern | Use Case |
|------|---------|----------|
| `01_simple_agent.py` | Basic tool-calling loop | Simple single-task agents |
| `02_react_agent.py` | ReAct (Reason + Act) | Multi-step reasoning tasks |
| `03_agent_states.py` | Stateful patterns | Complex workflows |

## Key Concepts

### The Minimal Agent Loop

```python
while not done:
    response = llm.call(messages)
    if response.has_tool_call:
        result = execute_tool(response.tool_call)
        messages.append(tool_result(result))
    else:
        done = True
        return response.content
```

That's it. Everything else — memory, RAG, multi-agent coordination — is built on top of this.

### The ReAct Pattern

ReAct (Reasoning + Acting) structures each agent iteration explicitly:

```
Thought: I need to find information about this customer's account
Action: get_customer_info(email="alice@example.com")
Observation: Customer found: Alice Johnson, Pro plan, active since 2022
Thought: Customer is on Pro plan. Now check their ticket history.
Action: get_ticket_history(customer_id="abc-123")
Observation: 3 previous tickets, last was billing issue resolved in 2023
Thought: I have enough context to resolve this ticket.
Action: final_answer("Based on the customer's Pro plan account...")
```

**Why ReAct works**: Forcing the model to reason before each action reduces hallucination and creates an auditable decision trail.

### Agent State Patterns

| Pattern | State | Best For |
|---------|-------|----------|
| **Stateless** | No memory between calls | Single-turn classification |
| **Windowed** | Last N messages | Chat support conversations |
| **Summarizing** | Compressed history | Long-running sessions |
| **External** | Redis/DB backed | Multi-session continuity |

### Tool Registry Pattern

Tools should be registered declaratively, not hardcoded:

```python
registry = ToolRegistry()

@registry.tool
def search_knowledge_base(query: str, n_results: int = 3) -> list[dict]:
    """Search the knowledge base for relevant articles."""
    ...

# Registry auto-generates the JSON schema for the LLM
tools = registry.get_tool_schemas()  # OpenAI-compatible format
```

## How to Run the Examples

```bash
# Requires OPENAI_API_KEY in .env
python module_02_agent_architecture/examples/01_simple_agent.py
python module_02_agent_architecture/examples/02_react_agent.py
python module_02_agent_architecture/examples/03_agent_states.py
```

## What's Next

Module 3 dives deep into tools — the mechanism by which agents interact with the world. You'll build the actual support platform tools: knowledge base search, customer data lookup, ticket management.
