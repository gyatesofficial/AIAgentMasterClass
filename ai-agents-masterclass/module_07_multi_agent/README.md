# Module 7: Multi-Agent Systems

## What This Module Covers

Some problems are too complex for a single agent. Multi-agent systems use specialized agents that collaborate, each handling what it does best. This module covers the three most important multi-agent patterns: supervisor/worker, sequential pipelines, and graph-based coordination.

## What You'll Build

| File | Pattern | Use Case |
|------|---------|----------|
| `01_supervisor_pattern.py` | Supervisor → Workers | Route to specialist |
| `02_pipeline_pattern.py` | Sequential pipeline | Triage → Resolution → QA |
| `03_langgraph_graph.py` | LangGraph StateGraph | Production orchestration |

## Key Concepts

### Why Multi-Agent?

A single GPT-4o call has constraints:
- **Context limit**: Can't hold all KB articles + full customer history + reasoning
- **Role conflict**: The same agent can't be both empathetic (customer-facing) and analytical (triage)
- **Quality**: Specialized prompts outperform generalist prompts
- **Cost**: Route simple tickets to cheaper models

### Pattern 1: Supervisor/Worker

```
                    ┌─────────────────┐
    Ticket ────────▶│   Supervisor    │
                    │  (router agent) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
    │  Billing    │  │  Technical  │  │   Account    │
    │  Specialist │  │  Specialist │  │   Specialist │
    └─────────────┘  └─────────────┘  └──────────────┘
```

The supervisor's only job is routing. Each specialist has a focused prompt and relevant tools.

### Pattern 2: Sequential Pipeline

```
Ticket ──▶ [Intake] ──▶ [Triage] ──▶ [Resolution] ──▶ [Quality] ──▶ Response
```

Each stage adds information:
- **Intake**: Validate, parse, extract customer info
- **Triage**: Classify category, set priority, search KB
- **Resolution**: Draft response using KB + customer history
- **Quality**: Check tone, accuracy, completeness

Each stage passes a growing `TicketState` object to the next stage.

### Pattern 3: LangGraph StateGraph

LangGraph makes multi-agent graphs explicit and debuggable:

```python
from langgraph.graph import StateGraph

graph = StateGraph(TicketState)

# Add nodes (agents)
graph.add_node("triage", triage_agent)
graph.add_node("resolution", resolution_agent)
graph.add_node("escalation", escalation_agent)

# Add conditional routing
graph.add_conditional_edges(
    "triage",
    route_after_triage,  # function that returns node name
    {
        "auto_resolve": "resolution",
        "escalate": "escalation",
    }
)

# Set entry and finish points
graph.set_entry_point("triage")
app = graph.compile()
```

**Why LangGraph?** It gives you:
- Explicit state management
- Conditional routing based on state
- Built-in cycle detection (prevents infinite loops)
- First-class streaming support
- Checkpoint/resume for long-running workflows

### State Management in Multi-Agent Systems

All agents share a `TicketState` TypedDict:

```python
class TicketState(TypedDict):
    # Input
    ticket_id: str
    subject: str
    body: str
    customer_email: str

    # Added by triage
    category: Optional[str]
    priority: Optional[str]
    kb_articles: list[dict]

    # Added by resolution
    proposed_resolution: Optional[str]
    auto_resolvable: bool

    # Added by quality
    quality_score: Optional[float]
    final_response: Optional[str]

    # Control flow
    should_escalate: bool
    escalation_reason: Optional[str]
```

Each agent reads the full state and writes its outputs to specific fields.

## How to Run the Examples

```bash
# Requires OPENAI_API_KEY
# Pattern 1 and 2 — no additional services
python module_07_multi_agent/examples/01_supervisor_pattern.py
python module_07_multi_agent/examples/02_pipeline_pattern.py

# Pattern 3 — uses LangGraph
pip install langgraph
python module_07_multi_agent/examples/03_langgraph_graph.py
```

## What's Next

Module 8 does a deep dive into agent frameworks (LangChain, LangGraph) — comparing them to raw Python and showing when each abstraction adds value vs. adds complexity.
