"""
knowledge_base.py - Knowledge Base Search Tool
===============================================
Provides the search_knowledge_base() function used by the triage
and resolution agents to find relevant KB articles.

Uses ChromaDB for semantic (vector) search.
Falls back to keyword search if ChromaDB is unavailable.

Usage:
    from support_platform.tools.knowledge_base import search_knowledge_base

    articles = search_knowledge_base(
        query="customer can't log in with authenticator app",
        n_results=3,
    )
    for article in articles:
        print(f"[{article['relevance_score']:.2%}] {article['title']}")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from support_platform.config import settings


# ──────────────────────────────────────────────────────────────
# ChromaDB client (lazy initialization)
# ──────────────────────────────────────────────────────────────

_chroma_client = None
_chroma_collection = None
_chroma_available = False

COLLECTION_NAME = "knowledge_base"


def _get_chroma_collection():
    """Get or initialize the ChromaDB collection."""
    global _chroma_client, _chroma_collection, _chroma_available

    if _chroma_collection is not None:
        return _chroma_collection

    try:
        import chromadb
        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        _chroma_client.heartbeat()
        _chroma_collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        _chroma_available = True
        return _chroma_collection
    except Exception as e:
        _chroma_available = False
        return None


# ──────────────────────────────────────────────────────────────
# Embedding function
# ──────────────────────────────────────────────────────────────

def _embed_text(text: str) -> list[float]:
    """
    Generate an embedding for the given text.

    Uses OpenAI text-embedding-3-small (1536 dimensions, $0.02/M tokens).
    This is the same model used to index the KB articles.
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Embedding failed: {e}")


# ──────────────────────────────────────────────────────────────
# Main search function
# ──────────────────────────────────────────────────────────────

def search_knowledge_base(
    query: str,
    n_results: int = 3,
    category_filter: Optional[str] = None,
    min_relevance: float = 0.3,
) -> list[dict]:
    """
    Search the knowledge base for articles relevant to a support query.

    Uses semantic search (vector similarity) when ChromaDB is available,
    falls back to keyword search otherwise.

    Args:
        query: Natural language query (e.g., "customer can't log in after new phone")
        n_results: Maximum number of articles to return
        category_filter: Optionally restrict search to a specific category
                         ('account_access', 'billing', 'technical_bug',
                          'feature_request', 'general_inquiry')
        min_relevance: Minimum relevance score (0.0-1.0) to include in results

    Returns:
        List of article dicts, sorted by relevance:
        [
            {
                "id": "...",
                "title": "How to Reset Your Password",
                "content": "...",
                "category": "account_access",
                "tags": ["password", "reset"],
                "relevance_score": 0.87
            },
            ...
        ]

    Example:
        articles = search_knowledge_base("I forgot my password")
        for article in articles:
            print(f"[{article['relevance_score']:.0%}] {article['title']}")
    """
    collection = _get_chroma_collection()

    if collection is not None:
        return _semantic_search(
            collection, query, n_results, category_filter, min_relevance
        )
    else:
        return _fallback_keyword_search(query, n_results, category_filter)


def _semantic_search(
    collection,
    query: str,
    n_results: int,
    category_filter: Optional[str],
    min_relevance: float,
) -> list[dict]:
    """Perform semantic search using ChromaDB."""
    try:
        query_embedding = _embed_text(query)
    except Exception as e:
        # If embedding fails, fall back to keyword search
        return _fallback_keyword_search(query, n_results, category_filter)

    where = {}
    if category_filter:
        where["category"] = category_filter

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where if where else None,
        include=["documents", "metadatas", "distances"],
    )

    articles = []
    for i, doc_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        # Convert cosine distance to similarity score (1 - distance for cosine space)
        similarity = max(0.0, 1.0 - distance)

        if similarity < min_relevance:
            continue

        metadata = results["metadatas"][0][i]
        articles.append({
            "id": doc_id,
            "title": metadata.get("title", "Untitled"),
            "content": results["documents"][0][i],
            "category": metadata.get("category", ""),
            "tags": json.loads(metadata.get("tags", "[]")),
            "relevance_score": round(similarity, 3),
        })

    return articles


def _fallback_keyword_search(
    query: str,
    n_results: int,
    category_filter: Optional[str],
) -> list[dict]:
    """
    Keyword-based fallback search when ChromaDB is unavailable.

    Also used when running without API keys for tests/demos.
    """
    BUILTIN_KB = [
        {
            "id": "builtin_001",
            "title": "How to Reset Your Password",
            "content": "Go to /forgot-password, enter your email, check inbox for reset link (valid 24h). If not received, check spam. Accounts lock after 5 failed attempts.",
            "category": "account_access",
            "tags": ["password", "reset", "login", "forgot"],
        },
        {
            "id": "builtin_002",
            "title": "Two-Factor Authentication Troubleshooting",
            "content": "If 2FA codes don't work on new phone: use backup codes from setup, or contact support with account verification. Emergency bypass at Settings > Security.",
            "category": "account_access",
            "tags": ["2fa", "authenticator", "security", "phone", "backup"],
        },
        {
            "id": "builtin_003",
            "title": "Billing and Refund Policy",
            "content": "Annual plans refundable within 30 days. Monthly plans non-refundable. Duplicate charges refunded immediately. Contact billing@support.io with charge details.",
            "category": "billing",
            "tags": ["refund", "billing", "charge", "duplicate", "payment"],
        },
        {
            "id": "builtin_004",
            "title": "Export Troubleshooting",
            "content": "Empty export: check filters, clear browser cache, try different browser. Large exports emailed within 1h. Free plan limited to 1,000 rows.",
            "category": "technical_bug",
            "tags": ["export", "csv", "download", "empty", "data"],
        },
        {
            "id": "builtin_005",
            "title": "Understanding Subscription Plans",
            "content": "Free: 1 user. Starter $29/mo: 5 users + integrations. Pro $79/mo: 25 users + analytics. Enterprise: unlimited users + SSO + SLA + custom pricing.",
            "category": "general_inquiry",
            "tags": ["plan", "pricing", "upgrade", "subscription", "features"],
        },
        {
            "id": "builtin_006",
            "title": "API Documentation and Rate Limits",
            "content": "API docs at api.example.com/docs. Rate limits: Free 30/min, Pro 500/min, Enterprise custom. 429 error = rate limited. Keys at Settings > API Keys.",
            "category": "technical_bug",
            "tags": ["api", "rate limit", "429", "integration", "developer"],
        },
        {
            "id": "builtin_007",
            "title": "Account Locked or Suspended",
            "content": "Accounts lock after 5 failed login attempts (auto-unlock after 30 min). Suspended accounts: contact support with payment details. Owner can appeal at account@example.com.",
            "category": "account_access",
            "tags": ["locked", "suspended", "access", "login", "account"],
        },
        {
            "id": "builtin_008",
            "title": "Requesting an Invoice or Receipt",
            "content": "Download invoices at Settings > Billing > History. For VAT invoices, add VAT number at Settings > Billing > Tax Info. Contact billing@example.com for reissues.",
            "category": "billing",
            "tags": ["invoice", "receipt", "vat", "tax", "billing"],
        },
    ]

    query_lower = query.lower()
    scored = []

    for article in BUILTIN_KB:
        if category_filter and article["category"] != category_filter:
            continue

        score = 0.0
        for tag in article["tags"]:
            if tag in query_lower:
                score += 0.25
        for word in article["title"].lower().split():
            if len(word) > 3 and word in query_lower:
                score += 0.1

        if score > 0:
            article_with_score = dict(article)
            article_with_score["relevance_score"] = round(min(score, 1.0), 2)
            scored.append(article_with_score)

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:n_results]


# ──────────────────────────────────────────────────────────────
# KB indexing (run once to populate ChromaDB)
# ──────────────────────────────────────────────────────────────

def index_kb_articles(articles: list[dict], batch_size: int = 50) -> int:
    """
    Index KB articles into ChromaDB.

    Call this once after populating the knowledge_base table.
    Each article is embedded and stored in ChromaDB for semantic search.

    Args:
        articles: List of article dicts from the database
        batch_size: Number of articles to embed per API call

    Returns:
        Number of articles indexed
    """
    collection = _get_chroma_collection()
    if not collection:
        raise RuntimeError("ChromaDB not available for indexing")

    indexed = 0
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]

        ids = [str(a["id"]) for a in batch]
        texts = [f"{a['title']}\n\n{a['content']}" for a in batch]
        metadatas = [
            {
                "title": a["title"],
                "category": a.get("category", ""),
                "tags": json.dumps(a.get("tags", [])),
            }
            for a in batch
        ]

        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]

            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            indexed += len(batch)
        except Exception as e:
            print(f"Error indexing batch {i}: {e}")

    return indexed
