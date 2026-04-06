# Module 6: RAG for Agents

## What This Module Covers

Retrieval-Augmented Generation (RAG) lets your agent answer questions using your actual knowledge base rather than just its training data. This is what separates a generic AI assistant from one that knows your product inside and out.

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_basic_rag.py` | Embed, store, and query documents in ChromaDB |
| `02_rag_pipeline.py` | Production pipeline with chunking, filtering, reranking |
| `03_rag_agent.py` | Full support agent backed by the KB |

## Key Concepts

### RAG Architecture

```
                    ┌─────────────────────────┐
                    │   Knowledge Base (KB)    │
                    │   50 articles            │
                    └──────────┬──────────────┘
                               │ Offline: embed and store
                               ▼
                    ┌─────────────────────────┐
                    │   ChromaDB Vector Store  │
                    │   50 article embeddings  │
                    └──────────┬──────────────┘
                               │
Support Ticket ──▶  [embed query] ──▶ similarity search ──▶ top-3 articles
                                                                │
                                                                ▼
                                              LLM + ticket + top-3 articles
                                                                │
                                                                ▼
                                                        Resolution draft
```

### Embedding and Indexing (Offline)

```python
from openai import OpenAI

client = OpenAI()

# Embed a KB article
def embed_text(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

# text-embedding-3-small: 1536 dimensions, $0.02 per million tokens
# text-embedding-3-large: 3072 dimensions, $0.13 per million tokens
```

### Chunking Strategy

For long documents, you need to split them into chunks:

| Strategy | Chunk Size | Overlap | Best For |
|----------|-----------|---------|----------|
| Fixed size | 512 tokens | 50 tokens | Simple, predictable |
| Sentence | 3-5 sentences | 1 sentence | Natural language |
| Section | By heading | None | Structured docs |

**The course uses section-based chunking** — KB articles are already split by heading, so each section becomes a chunk.

### Retrieval and Reranking

Simple retrieval returns the N most similar chunks by cosine similarity. **Reranking** improves quality by running a cross-encoder over the retrieved chunks:

```
Query: "customer can't log in after getting new phone"
                    │
              [similarity search]
                    │
    Top 10 by embedding similarity
                    │
              [cross-encoder reranker]
                    │
    Top 3 most relevant (better quality)
```

For most support use cases, simple similarity is sufficient. Reranking adds latency (~200ms) but improves accuracy by 10-20%.

### Hybrid Search

Combine vector search with keyword search for best results:

```python
# Vector search: finds semantically similar content
# BM25 keyword search: finds exact term matches
# Combined: takes the best of both
results = hybrid_search(query, alpha=0.7)  # 70% semantic, 30% keyword
```

### Filtering

Always filter by metadata before similarity search:

```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5,
    where={"category": "account_access"}  # Only search relevant category
)
```

Pre-filtering can dramatically reduce retrieved noise and improve relevance.

## How to Run the Examples

```bash
# Requires ChromaDB running
docker compose up -d chromadb

# Also requires OPENAI_API_KEY for embeddings
# First, generate sample data if you haven't
python scripts/seed_data.py

# Run examples
python module_06_rag/examples/01_basic_rag.py
python module_06_rag/examples/02_rag_pipeline.py
python module_06_rag/examples/03_rag_agent.py
```

## What's Next

Module 7 moves from single agents to multi-agent systems — where specialized agents collaborate to handle complex tickets that no single agent can resolve alone.
