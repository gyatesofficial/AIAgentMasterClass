# Module 0: Foundations — What Is an AI Agent?

## What This Module Covers

Before writing a single line of LLM code, you need a mental model of what an AI agent actually *is*. This module builds that foundation so every pattern you encounter later has a name and a place.

### Key Questions We Answer
- What separates an AI agent from a plain chatbot or a simple LLM call?
- What is the agent loop and why does it matter?
- What are the core components every agent has?
- What are the categories of agents (reactive, deliberative, multi-agent)?

## What You'll Build

`examples/hello_agent.py` — A pure-Python agent loop with **no LLM calls**. Uses mock responses to demonstrate the Perceive → Think → Act → Observe cycle so you can see the control flow clearly before adding real models.

## Key Concepts

### The Agent Loop
```
┌─────────────────────────────────────────────┐
│                  AGENT LOOP                 │
│                                             │
│  ┌──────────┐   ┌──────────┐               │
│  │ Perceive │──▶│  Think   │               │
│  └──────────┘   └──────────┘               │
│       ▲               │                    │
│       │               ▼                    │
│  ┌──────────┐   ┌──────────┐               │
│  │ Observe  │◀──│   Act    │               │
│  └──────────┘   └──────────┘               │
└─────────────────────────────────────────────┘
```

| Phase | Description | In Support Platform |
|-------|-------------|---------------------|
| **Perceive** | Read inputs from the environment | Receive a support ticket |
| **Think** | Reason about what to do (LLM call) | Classify priority, choose action |
| **Act** | Execute an action in the world | Search KB, update ticket, send email |
| **Observe** | Read the result of the action | KB results come back, ticket updated |

### Why the Loop Matters
A single LLM call → response is **not** an agent. An agent can:
1. Use the result of one action to decide the next action
2. Iterate until it reaches a goal or stopping condition
3. Fail gracefully and try alternative approaches

### Agent Archetypes
| Type | Description | When to Use |
|------|-------------|-------------|
| **Simple Reflex** | Condition → Action, no memory | FAQ bots, classification |
| **Model-Based** | Maintains state, tracks world changes | Multi-turn support chats |
| **Goal-Based** | Plans sequences of actions to reach a goal | Ticket triage + resolution pipeline |
| **Utility-Based** | Maximizes a utility function | Cost-optimized routing |
| **Multi-Agent** | Multiple agents collaborating | Our full support platform |

## How to Run the Examples

```bash
# No API keys needed for module 0!
cd module_00_foundations
python examples/hello_agent.py
```

You should see the agent loop execute 3 iterations, demonstrating the perceive/think/act/observe cycle with mock data.

## What's Next

Module 1 moves from the concept to the real implementation: calling actual LLMs (OpenAI and Anthropic), managing tokens, estimating costs, and building a reusable LLM client that the rest of the course builds on.
