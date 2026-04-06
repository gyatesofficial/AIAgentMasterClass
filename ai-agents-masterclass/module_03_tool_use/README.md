# Module 3: Tool Use & Function Calling

## What This Module Covers

Tools are how agents interact with the world beyond generating text. This module covers everything about tools: how to define them, how to execute them safely, how to handle errors, and how to build the real support platform tools.

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_basic_tools.py` | OpenAI function calling format, end-to-end flow |
| `02_tool_registry.py` | Decorator-based registry with auto schema generation |
| `03_support_tools.py` | Real support platform tools (KB search, customer lookup, etc.) |

## Key Concepts

### The Tool Calling Flow

```
1. Define tools as JSON schemas
2. Send to LLM with the user message
3. LLM responds with a tool_call (name + arguments as JSON)
4. You execute the function with those arguments
5. Append the result as a "tool" message
6. Send back to LLM → it uses the result to respond
```

### Tool Definition Format (OpenAI)

```python
tool = {
    "type": "function",
    "function": {
        "name": "get_customer_info",
        "description": "Look up a customer record by email address",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Customer's email address"
                }
            },
            "required": ["email"]
        }
    }
}
```

**The description is critical** — the LLM decides which tool to use based on the description, not the code. Write descriptions like documentation for a human, because the LLM reads them that way.

### Tool Registry with Auto Schema Generation

```python
@registry.tool
def search_knowledge_base(query: str, n_results: int = 3) -> list[dict]:
    """
    Search the knowledge base for articles relevant to a support query.

    Args:
        query: Natural language search query
        n_results: Number of results to return (default: 3)

    Returns:
        List of relevant articles with title, content, and relevance score
    """
    pass
```

The registry generates the JSON schema by inspecting the function signature and docstring. No manual schema maintenance.

### The Support Platform Tools

| Tool | Purpose |
|------|---------|
| `search_knowledge_base` | Semantic search over KB articles |
| `get_customer_info` | Look up customer record by email or ID |
| `get_ticket_history` | Get a customer's previous tickets |
| `update_ticket_status` | Change status, add notes, set resolution |
| `send_email_notification` | Send an email to the customer |

### Error Handling in Tools

Tools MUST handle errors gracefully — returning an error message is better than raising an exception:

```python
def get_customer_info(email: str) -> dict:
    try:
        customer = db.query(Customer).filter_by(email=email).first()
        if not customer:
            return {"error": f"No customer found with email {email}"}
        return customer.to_dict()
    except Exception as e:
        return {"error": f"Database error: {str(e)}"}
```

If a tool raises an exception, the LLM gets no feedback and may hallucinate a result. Return errors as data.

## How to Run the Examples

```bash
# 01 and 02 require OPENAI_API_KEY
python module_03_tool_use/examples/01_basic_tools.py
python module_03_tool_use/examples/02_tool_registry.py

# 03 uses mock data — no API key needed
python module_03_tool_use/examples/03_support_tools.py
```

## What's Next

Module 4 covers memory systems — how agents remember information across turns, sessions, and users. You'll implement in-memory, Redis-backed, and vector-based memory.
