# Module 1: LLM Foundations — Working With Language Models Directly

## What This Module Covers

Before using agent frameworks, you need to deeply understand how LLMs work at the API level. Frameworks like LangChain and LangGraph abstract away these details — but when something breaks (and it will), you need to know what's underneath.

### Key Questions We Answer
- How do tokens work and why does the context window matter?
- How do you estimate and control costs before they surprise you?
- How do you build a production-grade LLM client with retries and error handling?
- How do you get structured JSON output from both OpenAI and Anthropic?

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_token_budget.py` | Plan context window usage before building |
| `02_cost_estimator.py` | Estimate costs per run and per month |
| `03_llm_client.py` | Production LLM client with retry logic |
| `04_chat_agent.py` | Conversation management with history truncation |
| `05_structured_outputs.py` | Get validated JSON from LLMs |

## Key Concepts

### Token Budgets
The context window is a limited resource. A production agent needs to allocate it deliberately:

```
Total Context Window: 128,000 tokens
├── System Prompt:        2,000 tokens  (instructions)
├── Conversation History: 20,000 tokens (last N turns)
├── Retrieved Context:    40,000 tokens (KB articles, customer data)
├── Current Request:       5,000 tokens (the ticket being processed)
└── Reserved for Output:  10,000 tokens (the agent's response)
    ────────────────────────────────────
    Used:                 77,000 tokens
    Remaining buffer:     51,000 tokens
```

**Why this matters**: If you don't plan your token allocation, you'll hit context limits in production at 2 AM.

### Cost Estimation
GPT-4o costs ~$5/million input tokens. A typical support ticket resolution might use:
- 1,000 tokens (system prompt + ticket)
- 2,000 tokens (KB articles retrieved)
- 500 tokens (response)

= ~3,500 tokens = **$0.017 per ticket**

At 10,000 tickets/day = **$170/day = $5,100/month**

Knowing this upfront helps you make model routing decisions (Module 12).

### The LLM Client Pattern
Rather than calling the OpenAI SDK directly everywhere, we build a thin wrapper that:
- Handles retries with exponential backoff (transient errors are common)
- Normalizes the response format between OpenAI and Anthropic
- Tracks token usage and cost for every call
- Logs all interactions for debugging

### Structured Outputs
Agents need to extract structured data (category, priority, resolution) from LLM responses. Two approaches:
1. **OpenAI**: `response_format={"type": "json_object"}` or JSON Schema via tools
2. **Anthropic**: Tool trick — define a tool with the desired schema, force the model to call it

## How to Run the Examples

```bash
# Set up API keys first
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and ANTHROPIC_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run examples
python module_01_llm_foundations/examples/01_token_budget.py
python module_01_llm_foundations/examples/02_cost_estimator.py
python module_01_llm_foundations/examples/03_llm_client.py
python module_01_llm_foundations/examples/04_chat_agent.py
python module_01_llm_foundations/examples/05_structured_outputs.py
```

## Prerequisites
- `.env` file with `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`
- `pip install openai anthropic tiktoken python-dotenv`

## What's Next

Module 2 takes the LLM client and builds the agent loop on top of it, implementing the ReAct pattern (Reason + Act) that most production agents use.
