"""
01_basic_rag.py - Simple RAG Pipeline
======================================
Module 6: RAG for Agents

Retrieval-Augmented Generation (RAG) grounds the LLM's responses in
your actual documentation. Instead of relying on training data, the
agent retrieves relevant content and injects it into the context.

This file implements the simplest possible RAG:
1. Embed documents and store in ChromaDB
2. Embed a query
3. Find similar documents
4. Inject into LLM prompt

Run with: python module_06_rag/examples/01_basic_rag.py
Requires: OPENAI_API_KEY, ChromaDB running (docker compose up -d chromadb)
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))

# Sample knowledge base documents
SAMPLE_DOCUMENTS = [
    {
        "id": "doc_001",
        "title": "Password Reset Guide",
        "content": "To reset your password: 1. Go to login page 2. Click 'Forgot Password' 3. Enter your email 4. Check inbox for reset link (valid 24 hours) 5. Set new password. Accounts lock after 5 failed attempts.",
        "category": "account_access",
    },
    {
        "id": "doc_002",
        "title": "2FA Troubleshooting",
        "content": "If your 2FA codes stopped working after a new phone: use your backup codes saved during setup. If you lost backup codes, contact support@example.com with government ID for verification. We restore access within 1 business day.",
        "category": "account_access",
    },
    {
        "id": "doc_003",
        "title": "Billing and Refunds",
        "content": "Annual subscriptions are refundable within 30 days. Monthly subscriptions are non-refundable but you keep access until end of period. Duplicate charges are refunded within 48 hours of verification. Contact billing@example.com.",
        "category": "billing",
    },
    {
        "id": "doc_004",
        "title": "Export Data Guide",
        "content": "Export your data at Settings > Export Data. CSV and JSON formats available. Free plan: max 1,000 rows. Starter: 10,000 rows. Pro: 100,000 rows. Large exports are processed in background and emailed within 1 hour.",
        "category": "technical",
    },
    {
        "id": "doc_005",
        "title": "API Rate Limits",
        "content": "API rate limits by plan: Free: 30 requests/minute, 1,000/day. Pro: 500 requests/minute. Enterprise: custom limits. When rate limited, you receive a 429 error with Retry-After header. Implement exponential backoff.",
        "category": "technical",
    },
]


def get_embedding(text: str) -> Optional[list[float]]:
    """Get OpenAI embedding for text."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"  Embedding error: {e}")
        return None


def setup_chroma() -> Optional[object]:
    """Connect to ChromaDB and return a collection."""
    try:
        import chromadb
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        client.heartbeat()
        collection = client.get_or_create_collection(
            name="basic_rag_demo",
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
        return collection
    except Exception as e:
        print(f"  ChromaDB not available: {e}")
        return None


def index_documents(collection, documents: list[dict]) -> int:
    """Embed and store documents in ChromaDB."""
    print(f"\n  Indexing {len(documents)} documents...")
    ids = [d["id"] for d in documents]

    # Check if already indexed
    existing = collection.get(ids=ids)
    if len(existing["ids"]) == len(documents):
        print("  Documents already indexed.")
        return len(documents)

    texts = [f"{d['title']}\n\n{d['content']}" for d in documents]
    embeddings = []

    for i, text in enumerate(texts):
        emb = get_embedding(text)
        if emb:
            embeddings.append(emb)
            print(f"    Embedded doc {i+1}/{len(documents)}: {documents[i]['title'][:40]}")
        else:
            return i

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"title": d["title"], "category": d["category"]} for d in documents],
    )
    print(f"  Indexed {len(documents)} documents successfully.")
    return len(documents)


def retrieve(collection, query: str, n_results: int = 3) -> list[dict]:
    """Find documents similar to the query."""
    query_embedding = get_embedding(query)
    if not query_embedding:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    retrieved = []
    for i in range(len(results["ids"][0])):
        similarity = 1 - results["distances"][0][i]
        retrieved.append({
            "id": results["ids"][0][i],
            "title": results["metadatas"][0][i]["title"],
            "content": results["documents"][0][i],
            "similarity": round(similarity, 3),
        })

    return retrieved


def rag_answer(query: str, retrieved_docs: list[dict], model: str = "gpt-4o-mini") -> str:
    """Generate an answer using retrieved documents as context."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        context = "\n\n".join(
            f"[{doc['title']} - {doc['similarity']:.0%} relevant]\n{doc['content']}"
            for doc in retrieved_docs
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a customer support agent. Answer using ONLY the provided context. "
                        "If the context doesn't contain the answer, say so. "
                        "Be specific and cite the relevant section."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {query}",
                },
            ],
            temperature=0,
            max_tokens=400,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating answer: {e}"


def keyword_fallback_retrieve(query: str, n_results: int = 3) -> list[dict]:
    """Keyword-based retrieval fallback (no embedding needed)."""
    query_lower = query.lower()
    scored = []
    for doc in SAMPLE_DOCUMENTS:
        text = f"{doc['title']} {doc['content']}".lower()
        score = sum(1 for word in query_lower.split() if word in text and len(word) > 3)
        if score > 0:
            scored.append({**doc, "similarity": min(score * 0.2, 1.0)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:n_results]


def main():
    print("\n" + "=" * 60)
    print("  Basic RAG Demo")
    print("=" * 60)

    test_queries = [
        "I forgot my password and can't log in",
        "How do I get my data out of the system?",
    ]

    # Try ChromaDB first, fall back to keyword
    collection = setup_chroma()
    use_semantic = False

    if collection and os.environ.get("OPENAI_API_KEY"):
        indexed = index_documents(collection, SAMPLE_DOCUMENTS)
        use_semantic = indexed > 0

    for query in test_queries:
        print(f"\n  Query: '{query}'")

        if use_semantic:
            docs = retrieve(collection, query)
        else:
            docs = keyword_fallback_retrieve(query)
            print("  (Using keyword fallback — ChromaDB or API key not available)")

        print(f"\n  Retrieved {len(docs)} documents:")
        for doc in docs:
            print(f"    [{doc['similarity']:.0%}] {doc['title']}")

        if os.environ.get("OPENAI_API_KEY"):
            answer = rag_answer(query, docs)
            print(f"\n  Answer:\n  {answer}")
        else:
            print("\n  (Add OPENAI_API_KEY to generate answers)")
        print()


if __name__ == "__main__":
    main()
