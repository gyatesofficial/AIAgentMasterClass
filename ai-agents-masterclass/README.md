# AI Agents: From Architecture to Production

A comprehensive course repository for building production-grade AI agent systems. You will build a real AI Customer Support Platform incrementally across 15 modules, learning each concept by applying it to a working system.

---

## What You Build

An AI Customer Support Agent Platform that:

- Receives support tickets via REST API
- Triages and classifies tickets automatically
- Searches a knowledge base with semantic RAG
- Generates grounded, accurate responses
- Escalates complex cases to human agents
- Tracks costs and enforces safety guardrails
- Runs as a production FastAPI service

---

## Prerequisites

- Python 3.11 or higher
- Docker Desktop (for PostgreSQL, Redis, ChromaDB)
- OpenAI API key (most examples have mock fallbacks)
- Anthropic API key (optional, for Claude examples)

---

## Quick Start

```bash
# 1. Clone and enter the repo
cd CourseFiles

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 5. Start infrastructure (optional — examples have fallbacks)
docker compose up -d

# 6. Verify setup
python scripts/verify_setup.py

# 7. Run your first example
python module_00_foundations/examples/hello_agent.py
```

---

## Module Guide

| Module | Topic | Key Concept | Run Without API Key |
|--------|-------|-------------|---------------------|
| 00 | Foundations | Agent loop: Perceive → Think → Act → Observe | Yes |
| 01 | LLM Foundations | Token budgets, cost estimation, LLM client | Partial |
| 02 | Agent Architecture | Simple agent, ReAct, stateful vs stateless | Partial |
| 03 | Tool Use | Function calling, tool registry, support tools | Partial |
| 04 | Memory Systems | Window, Redis, vector memory | Partial |
| 05 | Planning & Reasoning | Chain of Thought, ReAct pattern, Plan-Execute | Partial |
| 06 | RAG | Basic RAG, production pipeline, RAG agent | Partial |
| 07 | Multi-Agent Systems | Supervisor/worker, pipeline, LangGraph | Yes |
| 08 | Frameworks | LangGraph intro, LangChain agent, comparison | Yes |
| 09 | Production | FastAPI, async agents, rate limiting | Yes |
| 10 | Evaluation | Basic evals, LLM judge, benchmark suite | Yes |
| 11 | Safety | Input validation, output guardrails, cost controls | Yes |
| 12 | Cost Optimization | Model routing, semantic caching, batch processing | Yes |
| 13 | Case Studies | Real-world agent system dissections | Yes |
| 14 | Capstone | Full platform integration | Requires API key |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  FastAPI REST API                        │
│  POST /tickets  GET /tickets/{id}  GET /health          │
└────────────────────┬────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   Triage Agent      │  GPT-4o-mini (cheap)
          │   - Classify        │  Rule-based fallback
          │   - Route           │
          └──────────┬──────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────▼────┐   ┌──────▼──────┐  ┌───▼────────┐
│Billing  │   │ Technical   │  │ Account    │
│Specialist│  │ Specialist  │  │ Specialist │
└────┬────┘   └──────┬──────┘  └───┬────────┘
     │               │               │
     └───────────────┼───────────────┘
                     │
          ┌──────────▼──────────┐
          │  Resolution Agent   │  GPT-4o (complex)
          │  - RAG KB search    │  Semantic cache
          │  - Draft response   │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  Quality Agent      │  Output guardrails
          │  - Validate         │  Policy compliance
          │  - Approve/block    │
          └─────────────────────┘

Infrastructure:
  PostgreSQL  — ticket and customer storage
  Redis       — conversation memory, response cache
  ChromaDB    — KB embeddings for semantic search
```

---

## Project Structure

```
CourseFiles/
├── .env.example                    # Environment variable template
├── .gitignore
├── docker-compose.yml              # PostgreSQL, Redis, ChromaDB
├── requirements.txt                # All dependencies
├── README.md                       # This file
│
├── scripts/
│   ├── verify_setup.py             # Check your environment
│   ├── init_db.sql                 # Create database tables
│   └── seed_data.py                # Generate sample data
│
├── module_00_foundations/
│   └── examples/hello_agent.py    # Your first agent (no API key needed)
│
├── module_01_llm_foundations/
│   └── examples/
│       ├── 01_token_budget.py      # Count tokens, plan budgets
│       ├── 02_cost_estimator.py    # Estimate and project costs
│       ├── 03_llm_client.py        # Production LLM client
│       ├── 04_chat_agent.py        # Conversational agent with memory
│       └── 05_structured_outputs.py # JSON extraction, 4 approaches
│
├── module_02_agent_architecture/
│   └── examples/
│       ├── 01_simple_agent.py      # Minimal agent loop
│       ├── 02_react_agent.py       # ReAct with tool registry
│       └── 03_agent_states.py      # Stateless, stateful, persistent
│
├── module_03_tool_use/
│   └── examples/
│       ├── 01_basic_tools.py       # OpenAI function calling
│       ├── 02_tool_registry.py     # Auto-schema from docstrings
│       └── 03_support_tools.py     # All 5 platform tools
│
├── module_04_memory_systems/
│   └── examples/
│       ├── 01_conversation_memory.py # Window and summarizing memory
│       ├── 02_redis_memory.py        # Redis-persistent memory
│       └── 03_vector_memory.py       # Semantic memory with ChromaDB
│
├── module_05_planning_reasoning/
│   └── examples/
│       ├── 01_chain_of_thought.py  # Zero-shot, few-shot, scratchpad CoT
│       ├── 02_react_pattern.py     # Full ReAct with function calling
│       └── 03_plan_execute.py      # Separate plan and execute phases
│
├── module_06_rag/
│   └── examples/
│       ├── 01_basic_rag.py         # Embed, store, retrieve, generate
│       ├── 02_rag_pipeline.py      # Chunking, reranking, context compression
│       └── 03_rag_agent.py         # Agent that searches KB before answering
│
├── module_07_multi_agent/
│   └── examples/
│       ├── 01_supervisor_pattern.py # Supervisor routes to specialists
│       ├── 02_pipeline_pattern.py   # Sequential pipeline with shared state
│       └── 03_langgraph_graph.py    # LangGraph StateGraph implementation
│
├── module_08_frameworks/
│   └── examples/
│       ├── 01_langgraph_intro.py   # StateGraph, nodes, edges, loops
│       ├── 02_langchain_agent.py   # create_react_agent, AgentExecutor
│       └── 03_framework_comparison.py # Raw Python vs LangChain vs LangGraph
│
├── module_09_production/
│   └── examples/
│       ├── 01_fastapi_agent.py     # REST API with background processing
│       ├── 02_async_agent.py       # asyncio.gather, semaphores, pools
│       └── 03_rate_limiting.py     # Fixed window, sliding window, token bucket
│
├── module_10_evaluation/
│   └── examples/
│       ├── 01_basic_evals.py       # Test dataset, evaluators, report
│       ├── 02_llm_judge.py         # LLM-as-judge, pairwise comparison
│       └── 03_benchmark_suite.py   # Full benchmark with regression detection
│
├── module_11_safety/
│   └── examples/
│       ├── 01_input_validation.py  # Prompt injection, PII, length limits
│       ├── 02_output_guardrails.py # Hallucination, policy, tone checks
│       └── 03_cost_guardrails.py   # Iteration limits, circuit breakers
│
├── module_12_cost_optimization/
│   └── examples/
│       ├── 01_model_routing.py     # Rule-based, complexity scoring, cascade
│       ├── 02_caching.py           # Exact and semantic response caching
│       └── 03_batch_processing.py  # Parallel batching, OpenAI Batch API
│
└── support_platform/               # The complete production platform
    ├── __init__.py
    ├── config.py                   # Pydantic Settings with all env vars
    ├── main.py                     # FastAPI app entry point
    ├── database/
    │   └── models.py               # SQLAlchemy ORM models
    ├── tools/
    │   ├── knowledge_base.py       # ChromaDB semantic search
    │   └── customer_db.py          # PostgreSQL customer/ticket operations
    ├── agents/
    │   ├── triage_agent.py         # Classification with LLM + fallback
    │   └── resolution_agent.py     # Response generation with RAG
    └── api/
        └── routes.py               # FastAPI routes with background tasks
```

---

## Running Examples

Every example file is self-contained and can be run directly:

```bash
# Module 0: No API key needed
python module_00_foundations/examples/hello_agent.py

# Module 1: Token and cost estimation
python module_01_llm_foundations/examples/01_token_budget.py
python module_01_llm_foundations/examples/02_cost_estimator.py

# Module 6: RAG (with fallback if no ChromaDB)
python module_06_rag/examples/01_basic_rag.py

# Module 7: Multi-agent systems (no API key needed)
python module_07_multi_agent/examples/01_supervisor_pattern.py
python module_07_multi_agent/examples/02_pipeline_pattern.py

# Module 9: Production FastAPI
python module_09_production/examples/01_fastapi_agent.py
# For HTTP server mode:
cd module_09_production/examples && uvicorn 01_fastapi_agent:app --reload

# Module 11: Safety guardrails (no API key needed)
python module_11_safety/examples/01_input_validation.py
python module_11_safety/examples/02_output_guardrails.py
python module_11_safety/examples/03_cost_guardrails.py

# Run the complete support platform
python -m support_platform.main
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Required for LLM features
OPENAI_API_KEY=sk-...

# Optional
ANTHROPIC_API_KEY=sk-ant-...

# Infrastructure (defaults work with docker compose up -d)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/support_agent
REDIS_URL=redis://localhost:6379
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

---

## Docker Infrastructure

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop services
docker compose down

# Reset data
docker compose down -v
```

Services started:
- PostgreSQL on port 5432 (tickets, customers, KB articles)
- Redis on port 6379 (conversation memory, response cache)
- ChromaDB on port 8000 (vector embeddings for semantic search)

---

## Cost Estimates

Running all examples with an API key:

| Activity | Estimated Cost |
|----------|---------------|
| All module examples (one run) | ~$0.10 - $0.50 |
| Seeding the knowledge base | ~$0.05 |
| Benchmark suite (full run) | ~$0.01 |
| Production load (1000 tickets/day) | ~$2-5/day |

Most examples have mock fallbacks and run at zero cost without an API key.

---

## Key Technologies

| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Core language |
| FastAPI | 0.109+ | REST API server |
| LangChain | 0.1+ | Agent framework abstractions |
| LangGraph | 0.0.30+ | Graph-based agent orchestration |
| ChromaDB | 0.4+ | Vector database for RAG |
| SQLAlchemy | 2.0+ | PostgreSQL ORM |
| Pydantic | 2.5+ | Data validation and settings |
| Redis | 5.0+ | Caching and memory persistence |
| OpenAI | 1.10+ | GPT-4o and embeddings |
| Anthropic | 0.18+ | Claude API |
| tiktoken | 0.5+ | Token counting |

---

## Learning Path

**Week 1: Foundations**
Complete modules 0-3. Build intuition for the agent loop, LLM APIs, and tool use.

**Week 2: Memory and Reasoning**
Complete modules 4-6. Understand how agents remember context and retrieve knowledge.

**Week 3: Multi-Agent and Frameworks**
Complete modules 7-8. See how agents coordinate and use frameworks.

**Week 4: Production**
Complete modules 9-12. Harden the system for real-world deployment.

**Week 5: Capstone**
Complete modules 13-14. Integrate everything into the full production platform.
