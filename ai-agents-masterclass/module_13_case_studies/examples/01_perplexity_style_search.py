"""
01_perplexity_style_search.py - Research Agent with Parallel Search
====================================================================
Implements a simplified version of the Perplexity AI architecture:
1. Rewrite query for better retrieval
2. Run multiple searches in parallel
3. Compress and rank results
4. Synthesize a grounded answer with citations

This demonstrates the key patterns from the Module 13 case study:
- Parallel async tool calls for speed
- Context compression to fit within token limits
- Citation-based grounding to prevent hallucinations
- Strict latency budgeting

Run it:
    python module_13_case_studies/examples/01_perplexity_style_search.py

Note: Uses mock search results by default (no API key needed).
      Set OPENAI_API_KEY for real LLM synthesis.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Mock knowledge base (simulates web search results)
# ---------------------------------------------------------------------------

MOCK_SEARCH_DB: dict[str, list[dict]] = {
    "password reset": [
        {
            "title": "How to Reset Your Password",
            "url": "https://help.example.com/password-reset",
            "snippet": "To reset your password: 1. Click 'Forgot Password' on the login page. "
                       "2. Enter your email address. 3. Check your inbox for a reset link. "
                       "4. Click the link and set a new password. Links expire after 24 hours.",
        },
        {
            "title": "Password Reset Emails Not Arriving",
            "url": "https://help.example.com/email-troubleshoot",
            "snippet": "If you're not receiving the reset email: Check your spam folder. "
                       "Verify the email address in your account settings. "
                       "Add noreply@example.com to your safe senders list.",
        },
    ],
    "billing refund": [
        {
            "title": "Refund Policy",
            "url": "https://example.com/refund-policy",
            "snippet": "We offer full refunds within 30 days of purchase. "
                       "Partial refunds are available for annual plans within 60 days. "
                       "Contact billing@example.com to request a refund.",
        },
        {
            "title": "How to Cancel Your Subscription",
            "url": "https://help.example.com/cancel",
            "snippet": "You can cancel anytime from Account Settings > Billing > Cancel Plan. "
                       "Your access continues until the end of the billing period.",
        },
    ],
    "account locked": [
        {
            "title": "Locked Account Recovery",
            "url": "https://help.example.com/locked",
            "snippet": "Accounts are locked after 10 failed login attempts. "
                       "Wait 30 minutes for automatic unlock, or contact support. "
                       "For immediate access, verify your identity via email.",
        },
    ],
    "default": [
        {
            "title": "Help Center",
            "url": "https://help.example.com",
            "snippet": "Browse our help center for answers to common questions about "
                       "account management, billing, and technical issues.",
        },
    ],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    relevance_score: float = 1.0


@dataclass
class ResearchResult:
    query: str
    rewritten_query: str
    sources: list[SearchResult]
    answer: str
    citations: list[str]
    latency_ms: float
    used_llm: bool


# ---------------------------------------------------------------------------
# Async search tools (mock)
# ---------------------------------------------------------------------------

async def search_knowledge_base(query: str, n_results: int = 3) -> list[SearchResult]:
    """Simulate searching an internal knowledge base."""
    await asyncio.sleep(0.05)  # Simulate network latency

    # Simple keyword matching for the mock
    results = []
    query_lower = query.lower()
    for key, articles in MOCK_SEARCH_DB.items():
        if key != "default" and key in query_lower:
            for article in articles[:n_results]:
                results.append(SearchResult(**article, relevance_score=0.95))

    # Return defaults if nothing matches
    if not results:
        for article in MOCK_SEARCH_DB["default"]:
            results.append(SearchResult(**article, relevance_score=0.3))

    return results[:n_results]


async def search_faq(query: str, n_results: int = 2) -> list[SearchResult]:
    """Simulate searching a FAQ database."""
    await asyncio.sleep(0.04)  # Slightly faster

    faqs = [
        SearchResult(
            title="Frequently Asked Questions",
            url="https://example.com/faq",
            snippet="Common questions: How do I reset my password? How do I cancel? "
                    "What payment methods do you accept? See full FAQ for more answers.",
            relevance_score=0.5,
        )
    ]
    return faqs[:n_results]


async def search_community(query: str, n_results: int = 2) -> list[SearchResult]:
    """Simulate searching a community forum."""
    await asyncio.sleep(0.08)

    posts = [
        SearchResult(
            title="Community: Common Issues and Solutions",
            url="https://community.example.com/common-issues",
            snippet="Community-verified solutions for common issues. "
                    "Upvoted answers from experienced users and support staff.",
            relevance_score=0.4,
        )
    ]
    return posts[:n_results]


# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------

def rewrite_query_simple(query: str) -> str:
    """
    Simple rule-based query rewriting (no LLM needed).

    A production system would use an LLM here, but for demonstration
    we use simple keyword expansion.
    """
    rewrites = {
        "can't log in": "account login authentication issue",
        "forgot password": "password reset recovery",
        "won't let me": "unable to access account issue",
        "how do i cancel": "subscription cancellation process",
        "charged twice": "duplicate billing charge refund",
        "not working": "technical issue troubleshooting",
    }
    query_lower = query.lower()
    for phrase, expansion in rewrites.items():
        if phrase in query_lower:
            return expansion
    return query  # No rewrite needed


async def rewrite_query_llm(query: str, client) -> str:
    """Rewrite query using LLM for better search results."""
    prompt = f"""Rewrite this customer support query for better search results.
Keep it short (under 10 words). Focus on the core issue.

Original: {query}
Rewritten:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return rewrite_query_simple(query)


# ---------------------------------------------------------------------------
# Result compression and ranking
# ---------------------------------------------------------------------------

def rank_and_compress_results(
    results: list[SearchResult],
    max_results: int = 5,
    max_snippet_length: int = 200,
) -> list[SearchResult]:
    """
    Sort by relevance score and truncate snippets to save context window.

    In production, you'd use a reranker model here (Cohere Rerank, etc.)
    """
    # Sort by relevance
    sorted_results = sorted(results, key=lambda r: r.relevance_score, reverse=True)

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in sorted_results:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_results.append(r)

    # Compress snippets to save tokens
    compressed = []
    for r in unique_results[:max_results]:
        compressed.append(SearchResult(
            title=r.title,
            url=r.url,
            snippet=r.snippet[:max_snippet_length] + "..." if len(r.snippet) > max_snippet_length else r.snippet,
            relevance_score=r.relevance_score,
        ))

    return compressed


# ---------------------------------------------------------------------------
# Answer synthesis
# ---------------------------------------------------------------------------

def synthesize_answer_simple(query: str, sources: list[SearchResult]) -> tuple[str, list[str]]:
    """
    Rule-based answer synthesis (no LLM, always works).

    Returns (answer_text, list_of_citation_urls)
    """
    if not sources:
        return "I couldn't find specific information about this. Please contact support.", []

    # Build a simple answer from the top source
    top_source = sources[0]
    answer = f"Based on our documentation: {top_source.snippet}"
    citations = [s.url for s in sources[:3]]
    return answer, citations


def synthesize_answer_llm(
    query: str,
    sources: list[SearchResult],
    client,
) -> tuple[str, list[str]]:
    """
    LLM-synthesized answer grounded in sources.
    Returns (answer_text, list_of_citation_urls)
    """
    # Build context from sources
    context_parts = []
    for i, source in enumerate(sources, 1):
        context_parts.append(f"[{i}] {source.title}\n{source.snippet}")
    context = "\n\n".join(context_parts)

    prompt = f"""Answer the customer's question based ONLY on the provided sources.
Always cite sources using [1], [2] etc. If the sources don't contain the answer, say so.

SOURCES:
{context}

CUSTOMER QUESTION: {query}

ANSWER (cite sources inline):"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful customer support agent. Answer questions "
                               "based only on provided sources. Be concise and helpful.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.1,
        )
        answer = response.choices[0].message.content.strip()
        citations = [s.url for s in sources[:3]]
        return answer, citations
    except Exception as e:
        # Fallback to rule-based if LLM fails
        return synthesize_answer_simple(query, sources)


# ---------------------------------------------------------------------------
# Main research agent
# ---------------------------------------------------------------------------

class ResearchAgent:
    """
    Perplexity-style research agent with parallel search and grounded answers.

    Architecture:
        Query → Rewrite → Parallel Search → Rank/Compress → Synthesize → Answer
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self.client = None

        if use_llm:
            try:
                import openai
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    self.client = openai.OpenAI(api_key=api_key)
                else:
                    print("No OPENAI_API_KEY found — using rule-based fallback")
                    self.use_llm = False
            except ImportError:
                print("openai not installed — using rule-based fallback")
                self.use_llm = False

    async def research(self, query: str) -> ResearchResult:
        """
        Full research pipeline with latency tracking.

        This is the core method — notice how we:
        1. Rewrite the query first (improve search quality)
        2. Run all three searches IN PARALLEL (saves ~60% time)
        3. Rank and compress results (respect token limits)
        4. Generate a grounded answer with citations
        """
        start = time.time()

        # Step 1: Rewrite query for better search
        if self.use_llm and self.client:
            rewritten = await rewrite_query_llm(query, self.client)
        else:
            rewritten = rewrite_query_simple(query)

        # Step 2: Parallel search across all sources
        # asyncio.gather runs all three searches concurrently
        # Total time = max(search1, search2, search3), not sum
        kb_results, faq_results, community_results = await asyncio.gather(
            search_knowledge_base(rewritten, n_results=3),
            search_faq(rewritten, n_results=2),
            search_community(rewritten, n_results=2),
        )

        # Step 3: Merge, rank, and compress
        all_results = kb_results + faq_results + community_results
        top_sources = rank_and_compress_results(all_results, max_results=5)

        # Step 4: Synthesize answer
        if self.use_llm and self.client:
            answer, citations = synthesize_answer_llm(query, top_sources, self.client)
            used_llm = True
        else:
            answer, citations = synthesize_answer_simple(query, top_sources)
            used_llm = False

        latency_ms = (time.time() - start) * 1000

        return ResearchResult(
            query=query,
            rewritten_query=rewritten,
            sources=top_sources,
            answer=answer,
            citations=citations,
            latency_ms=latency_ms,
            used_llm=used_llm,
        )


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

async def demo():
    """Demonstrate the research agent with sample queries."""
    print("=" * 60)
    print("Perplexity-Style Research Agent Demo")
    print("=" * 60)

    agent = ResearchAgent(use_llm=True)

    queries = [
        "I can't log in to my account, I forgot my password",
        "I was charged twice last month, how do I get a refund?",
        "My account got locked, what should I do?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 40)

        result = await agent.research(query)

        print(f"Rewritten: {result.rewritten_query}")
        print(f"Sources found: {len(result.sources)}")
        print(f"\nAnswer:")
        print(result.answer)
        print(f"\nCitations:")
        for i, url in enumerate(result.citations, 1):
            print(f"  [{i}] {url}")
        print(f"\nLatency: {result.latency_ms:.0f}ms | LLM: {result.used_llm}")
        print()


if __name__ == "__main__":
    asyncio.run(demo())
