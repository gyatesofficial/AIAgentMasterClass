# Module 4: Memory Systems

## What This Module Covers

Memory is what separates a chatbot from an agent that can handle long, complex interactions. This module covers three types of memory: in-process conversation windows, Redis-backed persistent sessions, and semantic vector memory with ChromaDB.

## What You'll Build

| File | Memory Type | Persistence |
|------|------------|-------------|
| `01_conversation_memory.py` | Window + summarization | In-process only |
| `02_redis_memory.py` | Full history with TTL | Cross-session (Redis) |
| `03_vector_memory.py` | Semantic similarity | Long-term (ChromaDB) |

## Key Concepts

### The Memory Hierarchy

```
Short-term (in context window)
  └── Last N messages in the prompt

Working memory (Redis)
  └── Full conversation history, serialized
  └── TTL-managed sessions

Long-term semantic memory (ChromaDB)
  └── Important facts, preferences, past resolutions
  └── Retrieved by similarity, not recency
```

### Conversation Memory with Windowing

The simplest memory strategy: keep only the last N turns:

```python
class ConversationMemory:
    def __init__(self, max_messages: int = 20):
        self.messages = []
        self.max_messages = max_messages

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # Trim to window size, always keeping the system prompt
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[:1] + self.messages[-(self.max_messages-1):]
```

**Limitation**: Context before the window is completely lost.

### Memory with Summarization

When history gets long, summarize the oldest messages:

```
Recent messages (last 10): stored verbatim
Older messages: compressed into a summary paragraph
```

This preserves important context without consuming tokens.

### Redis Persistent Memory

For multi-session support conversations:
- Session key: `session:{ticket_id}` or `session:{customer_id}:{date}`
- TTL: 24 hours for support sessions, 7 days for ongoing issues
- Serialization: JSON (keep it simple and debuggable)

### Semantic (Vector) Memory

For retrieving relevant past interactions:
- "Customer has complained about billing 3 times before" — retrieved when handling a new billing ticket
- "Customer is an enterprise client with SLA requirements" — always included for enterprise customers

```python
# Store a memory
memory.remember(
    text="Customer escalated to manager over billing dispute on 2024-01-15",
    metadata={"customer_id": "abc-123", "type": "escalation_history"}
)

# Retrieve relevant memories
memories = memory.recall(
    query="customer is angry about billing",
    customer_id="abc-123",
    top_k=3
)
```

## How to Run the Examples

```bash
# 01 — no external services needed
python module_04_memory_systems/examples/01_conversation_memory.py

# 02 — requires Redis running
docker compose up -d redis
python module_04_memory_systems/examples/02_redis_memory.py

# 03 — requires ChromaDB running
docker compose up -d chromadb
python module_04_memory_systems/examples/03_vector_memory.py
```

## What's Next

Module 5 covers planning and reasoning — how agents tackle complex multi-step problems using Chain of Thought, ReAct, and Plan-Execute patterns.
