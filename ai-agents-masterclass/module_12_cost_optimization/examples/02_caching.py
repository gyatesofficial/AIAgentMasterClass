"""
02_caching.py - Semantic Response Caching
==========================================
Module 12: Cost Optimization

Caching LLM responses eliminates redundant API calls for similar questions.
Two types of caching:

1. Exact cache: Cache by literal text hash (fast, only hits exact duplicates)
2. Semantic cache: Cache by meaning (uses embeddings to find similar queries)

Semantic caching is much more powerful:
- "How do I reset my password?" == "I forgot my password, help"
- "Charge on my card" == "I was billed twice"
- Hit rates of 30-50% are common in production

Trade-off: Semantic cache requires one embedding call per query (~$0.0001)
vs the full LLM response cost (~$0.001-0.01). Still saves 10x on hits.

Run with: python module_12_cost_optimization/examples/02_caching.py
Requires: Redis for persistence (falls back to in-memory)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Cache Models
# ──────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    """A cached response."""
    query: str
    response: str
    embedding: Optional[list[float]]  # For semantic matching
    created_at: float
    hit_count: int = 0
    category: Optional[str] = None


@dataclass
class CacheResult:
    """Result of a cache lookup."""
    hit: bool
    response: Optional[str]
    similarity: float = 0.0      # 0.0 = miss, 1.0 = perfect match
    from_exact: bool = False     # True = exact match, False = semantic match
    cache_key: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Embedding Utilities
# ──────────────────────────────────────────────────────────────

def get_embedding(text: str) -> Optional[list[float]]:
    """Get a text embedding from OpenAI."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:2000],  # Cap input to control cost
        )
        return response.data[0].embedding
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(y * y for y in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def mock_embedding(text: str) -> list[float]:
    """
    Generate a deterministic mock embedding for testing.

    Real embeddings are dense vectors (1536 floats for text-embedding-3-small).
    This mock creates a sparse vector based on word presence — sufficient
    to demonstrate semantic similarity concepts without API calls.
    """
    keywords = [
        "password", "login", "access", "account",
        "billing", "charge", "refund", "payment",
        "error", "bug", "crash", "api",
        "export", "data", "download",
        "feature", "request", "suggestion",
    ]

    text_lower = text.lower()
    vector = [
        1.0 if kw in text_lower else 0.0
        for kw in keywords
    ]

    # Normalize
    magnitude = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / magnitude for x in vector]


# ──────────────────────────────────────────────────────────────
# Cache 1: Exact Match Cache
# ──────────────────────────────────────────────────────────────

class ExactCache:
    """
    Cache based on SHA-256 hash of normalized query text.

    Normalizes by:
    - Lowercasing
    - Stripping whitespace
    - Removing punctuation

    Extremely fast lookups (O(1) hash map), but only hits
    when queries are textually identical.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._stats = {"hits": 0, "misses": 0, "stores": 0}

    def _normalize(self, text: str) -> str:
        """Normalize query text for consistent hashing."""
        import re
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = " ".join(text.split())
        return text

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, query: str) -> CacheResult:
        """Look up a query in the exact cache."""
        key = self._hash(self._normalize(query))
        entry = self._cache.get(key)

        if entry and (time.time() - entry.created_at) < self.ttl:
            entry.hit_count += 1
            self._stats["hits"] += 1
            return CacheResult(hit=True, response=entry.response, similarity=1.0, from_exact=True, cache_key=key)

        self._stats["misses"] += 1
        return CacheResult(hit=False, response=None)

    def set(self, query: str, response: str, category: str = None):
        """Store a response in the exact cache."""
        # Evict oldest entries if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
            del self._cache[oldest_key]

        key = self._hash(self._normalize(query))
        self._cache[key] = CacheEntry(
            query=query,
            response=response,
            embedding=None,
            created_at=time.time(),
            category=category,
        )
        self._stats["stores"] += 1

    @property
    def hit_rate(self) -> float:
        total = self._stats["hits"] + self._stats["misses"]
        return self._stats["hits"] / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {**self._stats, "size": len(self._cache), "hit_rate": f"{self.hit_rate:.0%}"}


# ──────────────────────────────────────────────────────────────
# Cache 2: Semantic Cache
# ──────────────────────────────────────────────────────────────

class SemanticCache:
    """
    Cache based on semantic similarity using embeddings.

    When a new query arrives:
    1. Generate embedding for the query
    2. Compare against all cached embeddings
    3. If similarity > threshold → return cached response
    4. If no match → call LLM, cache the result

    This catches variations like:
    - "forgot password" ≈ "can't remember my password"
    - "charged twice" ≈ "duplicate billing charge"

    In production, use ChromaDB or Pinecone for efficient similarity search
    at scale (vector index search instead of brute-force).
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_size: int = 500,
        ttl_seconds: int = 7200,
        use_mock_embeddings: bool = True,
    ):
        self.threshold = similarity_threshold
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.use_mock = use_mock_embeddings
        self._entries: list[CacheEntry] = []
        self._stats = {"hits": 0, "misses": 0, "stores": 0, "embedding_calls": 0}

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding, using mock if no API key."""
        if self.use_mock or not os.environ.get("OPENAI_API_KEY"):
            return mock_embedding(text)
        self._stats["embedding_calls"] += 1
        result = get_embedding(text)
        return result or mock_embedding(text)  # Fall back to mock on error

    def _is_expired(self, entry: CacheEntry) -> bool:
        return (time.time() - entry.created_at) > self.ttl

    def get(self, query: str) -> CacheResult:
        """
        Find the most similar cached response.

        Returns a hit if similarity >= threshold.
        """
        query_embedding = self._get_embedding(query)

        best_match = None
        best_similarity = 0.0

        for entry in self._entries:
            if self._is_expired(entry):
                continue
            if not entry.embedding:
                continue

            sim = cosine_similarity(query_embedding, entry.embedding)
            if sim > best_similarity:
                best_similarity = sim
                best_match = entry

        if best_match and best_similarity >= self.threshold:
            best_match.hit_count += 1
            self._stats["hits"] += 1
            return CacheResult(
                hit=True,
                response=best_match.response,
                similarity=best_similarity,
                from_exact=best_similarity >= 0.99,
            )

        self._stats["misses"] += 1
        return CacheResult(hit=False, response=None, similarity=best_similarity)

    def set(self, query: str, response: str, category: str = None):
        """Store a response with its embedding."""
        # Evict expired entries
        self._entries = [e for e in self._entries if not self._is_expired(e)]

        # Evict oldest if at capacity
        if len(self._entries) >= self.max_size:
            self._entries.sort(key=lambda e: e.created_at)
            self._entries = self._entries[self.max_size // 4:]  # Remove oldest 25%

        embedding = self._get_embedding(query)
        self._entries.append(CacheEntry(
            query=query,
            response=response,
            embedding=embedding,
            created_at=time.time(),
            category=category,
        ))
        self._stats["stores"] += 1

    @property
    def hit_rate(self) -> float:
        total = self._stats["hits"] + self._stats["misses"]
        return self._stats["hits"] / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {**self._stats, "size": len(self._entries), "hit_rate": f"{self.hit_rate:.0%}"}


# ──────────────────────────────────────────────────────────────
# Redis-Backed Cache (production version)
# ──────────────────────────────────────────────────────────────

class RedisCacheBackend:
    """
    Persist cache entries in Redis for multi-process deployments.

    In production:
    - Multiple agent workers share the same cache
    - Cache survives process restarts
    - TTL is handled by Redis natively

    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, redis_url: str = None, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._redis = None
        self._memory_fallback: dict[str, dict] = {}

        redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            import redis
            self._redis = redis.Redis.from_url(redis_url, socket_timeout=2, decode_responses=True)
            self._redis.ping()
        except Exception:
            self._redis = None

    def get(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return self._redis.get(f"cache:{key}")
            except Exception:
                pass
        return self._memory_fallback.get(key, {}).get("value")

    def set(self, key: str, value: str):
        if self._redis:
            try:
                self._redis.setex(f"cache:{key}", self.ttl, value)
                return
            except Exception:
                pass
        self._memory_fallback[key] = {"value": value, "expires": time.time() + self.ttl}

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Semantic Response Caching Demo")
    print("=" * 60)
    print("  (Using mock embeddings — set OPENAI_API_KEY for real embeddings)\n")

    CACHED_RESPONSE = (
        "Hi there,\n\nTo reset your password:\n"
        "1. Go to the login page\n"
        "2. Click 'Forgot Password'\n"
        "3. Enter your email and check your inbox\n\n"
        "The reset link is valid for 24 hours."
    )

    # ── Demo 1: Exact Cache ──
    print("  [1] Exact Cache")
    exact = ExactCache(ttl_seconds=300)
    exact.set("forgot my password", CACHED_RESPONSE, "account_access")

    queries = [
        "forgot my password",
        "forgot my password",       # Exact match
        "Forgot My Password",       # Case insensitive match (normalized)
        "I can't log in",           # No match
    ]
    for q in queries:
        result = exact.get(q)
        status = f"HIT  (sim: {result.similarity:.0%})" if result.hit else "MISS"
        print(f"    '{q[:40]}' → {status}")
    print(f"    Stats: {exact.stats}")

    # ── Demo 2: Semantic Cache ──
    print("\n  [2] Semantic Cache (similarity threshold: 85%)")
    semantic = SemanticCache(similarity_threshold=0.85, use_mock_embeddings=True)

    # Seed the cache
    seed_pairs = [
        ("forgot my password", CACHED_RESPONSE, "account_access"),
        ("charged twice this month", "Our billing team will review your duplicate charge and process a refund within 48 hours.", "billing"),
    ]
    for query, response, cat in seed_pairs:
        semantic.set(query, response, cat)

    # Test with varying queries
    test_queries = [
        ("forgot my password", "Exact match expected"),
        ("can't remember my password", "Semantic match expected"),
        ("password reset help needed", "Semantic match expected"),
        ("double billed on my account", "Semantic match expected"),
        ("API integration webhook error", "Miss expected"),
    ]

    for query, expected in test_queries:
        result = semantic.get(query)
        status = f"HIT  (sim: {result.similarity:.0%})" if result.hit else f"MISS (best sim: {result.similarity:.0%})"
        print(f"    '{query[:45]}' → {status}")

    print(f"    Stats: {semantic.stats}")

    # ── Demo 3: Cost savings calculation ──
    print("\n  [3] Projected Cost Savings")
    hit_rate = 0.40          # Typical 40% semantic cache hit rate
    daily_requests = 1000
    llm_cost_per_call = 0.002  # ~$0.002 per support ticket response
    embedding_cost = 0.0001    # ~$0.0001 per embedding lookup

    without_cache = daily_requests * llm_cost_per_call
    with_cache = (
        daily_requests * embedding_cost +                           # All queries need embedding lookup
        daily_requests * (1 - hit_rate) * llm_cost_per_call         # Only misses need LLM call
    )
    savings = without_cache - with_cache

    print(f"    Daily requests: {daily_requests}")
    print(f"    Cache hit rate: {hit_rate:.0%}")
    print(f"    Without cache: ${without_cache:.2f}/day")
    print(f"    With cache:    ${with_cache:.2f}/day")
    print(f"    Daily savings: ${savings:.2f} ({savings/without_cache:.0%})")
    print(f"    Monthly:       ${savings * 30:.2f}")

    # ── Demo 4: Redis backend ──
    print("\n  [4] Redis Cache Backend")
    backend = RedisCacheBackend()
    print(f"    Using backend: {backend.backend}")
    backend.set("test_key", "test_value")
    result = backend.get("test_key")
    print(f"    Set/get test: {'passed' if result == 'test_value' else 'failed'}")


if __name__ == "__main__":
    main()
