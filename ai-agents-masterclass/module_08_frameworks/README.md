# Module 8: Agent Frameworks Deep Dive

## What This Module Covers

LangChain and LangGraph are the dominant agent frameworks in Python. This module gives you a thorough understanding of both — when they add value, when they add unnecessary complexity, and how they compare to raw Python implementations.

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_langgraph_intro.py` | LangGraph fundamentals: nodes, edges, state |
| `02_langchain_agent.py` | LangChain's create_react_agent and AgentExecutor |
| `03_framework_comparison.py` | Same agent in raw Python, LangChain, and LangGraph |

## Key Concepts

### When to Use a Framework (and When Not To)

**Use LangGraph when:**
- Your agent has complex branching logic
- You need checkpoint/resume capabilities
- You're building multi-agent pipelines
- You want built-in streaming support

**Use LangChain when:**
- You want to swap models/providers easily
- You need pre-built document loaders and splitters
- You're building RAG pipelines
- You want integration with dozens of tools out of the box

**Use raw Python when:**
- The task is simple (single LLM call + 1-2 tools)
- You need maximum control over the exact API calls
- You're debugging a framework issue
- Performance is critical (frameworks add latency)

### LangGraph Core Concepts

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

# 1. Define the state
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # Messages accumulate
    next_step: str

# 2. Define nodes (functions that transform state)
def call_llm(state: AgentState) -> dict:
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def call_tool(state: AgentState) -> dict:
    tool_call = state["messages"][-1].tool_calls[0]
    result = execute_tool(tool_call)
    return {"messages": [ToolMessage(result, tool_call_id=tool_call["id"])]}

# 3. Build the graph
graph = StateGraph(AgentState)
graph.add_node("llm", call_llm)
graph.add_node("tool", call_tool)

# 4. Add edges
graph.add_conditional_edges("llm", should_call_tool, {
    True: "tool",
    False: END
})
graph.add_edge("tool", "llm")
graph.set_entry_point("llm")

app = graph.compile()
```

### LangChain AgentExecutor Pattern

```python
from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")

# Tools are defined using @tool decorator
from langchain.tools import tool

@tool
def search_kb(query: str) -> str:
    """Search the knowledge base for relevant articles."""
    return do_search(query)

# Create agent
agent = create_react_agent(llm, [search_kb], prompt)
executor = AgentExecutor(agent=agent, tools=[search_kb], verbose=True)
result = executor.invoke({"input": "How do I reset my password?"})
```

### Framework Comparison (Same Task)

The course builds the exact same support ticket triage agent three ways:

| Implementation | Lines of Code | Flexibility | Debuggability | Recommended For |
|----------------|--------------|-------------|---------------|-----------------|
| Raw Python | ~100 | Highest | Easiest | Learning, simple agents |
| LangChain | ~50 | Medium | Medium | Quick prototyping |
| LangGraph | ~80 | High | Excellent | Production systems |

Raw Python has more code but you control every decision. LangGraph adds more code than LangChain but gives you much better tooling for complex workflows.

### LangSmith Integration

LangGraph and LangChain integrate with LangSmith for tracing:

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your_key
LANGCHAIN_PROJECT=ai-agents-course
```

Every agent run is recorded with inputs, outputs, token counts, and latency at each step. Invaluable for debugging.

## How to Run the Examples

```bash
# All require OPENAI_API_KEY
pip install langgraph langchain langchain-openai

python module_08_frameworks/examples/01_langgraph_intro.py
python module_08_frameworks/examples/02_langchain_agent.py
python module_08_frameworks/examples/03_framework_comparison.py

# Optional: Enable LangSmith tracing
# Add LANGCHAIN_API_KEY to .env first
```

## What's Next

Module 9 takes your agent to production — FastAPI HTTP API, async processing, streaming responses, and rate limiting.
