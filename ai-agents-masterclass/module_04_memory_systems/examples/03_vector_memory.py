"""
03_vector_memory.py - Semantic Memory with ChromaDB
====================================================
Module 4: Memory Systems

Vector memory stores information as embeddings and retrieves it by
semantic similarity. Unlike window memory (recency) or exact-match
(keyword), it finds contextually relevant memories.

Use cases:
- "This customer has complained about billing before" (found when new billing ticket arrives)
- "Customer is enterprise with SLA requirements" (always surfaced for enterprise tickets)
- Long-term customer preference and history

Run with: python module_04_memory_systems/examples/03_vector_memory.py
Requires: ChromaDB running (docker compose up -d chromadb) and OPENAI_API_KEY
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))


@dataclass
class Memory:
    """A single stored memory."""
    id: str
    text: str
    customer_id: Optional[str]
    memory_type: str      # 'interaction', 'preference', 'fact', 'issue'
    importance: float     # 0.0 to 1.0
    created_at: str
    relevance_score: Optional[float] = None  # Set after retrieval


class VectorMemory:
    """
    Long-term semantic memory backed by ChromaDB.

    Stores memories as embeddings, retrieves by semantic similarity.
    Much more powerful than keyword search for finding relevant context.

    Usage:
        memory = VectorMemory()

        # Store a memory
        memory.remember(
            text="Customer escalated to manager after billing dispute. Very frustrated.",
            customer_id="cust_001",
            memory_type="interaction",
            importance=0.9,
        )

        # Retrieve relevant memories
        memories = memory.recall(
            query="customer is upset about billing",
            customer_id="cust_001",
        )
    """

    COLLECTION_NAME = "agent_memory"

    def __init__(self, use_mock: bool = None):
        """
        Initialize vector memory.

        Args:
            use_mock: Force mock mode (no ChromaDB). Auto-detected if None.
        """
        self._mock_store: list[dict] = []
        self._use_mock = True

        if use_mock is False or (use_mock is None):
            self._try_connect()

    def _try_connect(self) -> None:
        """Try to connect to ChromaDB."""
        try:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
            )
            # Test the connection
            client.heartbeat()

            self._chroma = client
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_mock = False
            print(f"  Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
        except Exception as e:
            print(f"  ChromaDB not available ({e}). Using mock vector store.")
            self._use_mock = True

    def _embed(self, text: str) -> list[float]:
        """
        Generate an embedding for the given text.

        In production: use OpenAI text-embedding-3-small.
        Here: return a mock embedding for demos without API key.
        """
        try:
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key or "your-key" in api_key:
                raise ValueError("No API key")
            client = OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception:
            # Mock embedding: hash-based (not semantically meaningful, just for demo)
            import hashlib
            hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
            # Create a 384-dim mock embedding
            return [(hash_val >> i & 0xFF) / 255.0 for i in range(0, 384)]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def remember(
        self,
        text: str,
        customer_id: Optional[str] = None,
        memory_type: str = "interaction",
        importance: float = 0.5,
    ) -> str:
        """
        Store a new memory.

        Args:
            text: The memory to store (natural language description)
            customer_id: Associate this memory with a specific customer
            memory_type: Type of memory ('interaction', 'preference', 'fact', 'issue')
            importance: Importance score 0.0-1.0 (affects retrieval ranking)

        Returns:
            Memory ID
        """
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        metadata = {
            "customer_id": customer_id or "",
            "memory_type": memory_type,
            "importance": importance,
            "created_at": now,
        }

        if not self._use_mock:
            embedding = self._embed(text)
            self._collection.add(
                ids=[memory_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
            )
        else:
            embedding = self._embed(text)
            self._mock_store.append({
                "id": memory_id,
                "text": text,
                "embedding": embedding,
                "metadata": metadata,
            })

        return memory_id

    def recall(
        self,
        query: str,
        customer_id: Optional[str] = None,
        top_k: int = 3,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0,
    ) -> list[Memory]:
        """
        Retrieve memories semantically similar to the query.

        Args:
            query: Natural language description of what you're looking for
            customer_id: Filter to memories for this customer
            top_k: Number of memories to return
            memory_type: Filter by memory type
            min_importance: Minimum importance score

        Returns:
            List of Memory objects sorted by relevance
        """
        query_embedding = self._embed(query)

        if not self._use_mock:
            # Build ChromaDB where filter
            where = {}
            if customer_id:
                where["customer_id"] = customer_id
            if memory_type:
                where["memory_type"] = memory_type

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where if where else None,
            )

            memories = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                if meta.get("importance", 0) < min_importance:
                    continue
                # ChromaDB returns distances, convert to similarity
                distance = results["distances"][0][i]
                similarity = 1 - distance  # For cosine space
                memories.append(Memory(
                    id=doc_id,
                    text=results["documents"][0][i],
                    customer_id=meta.get("customer_id") or None,
                    memory_type=meta.get("memory_type", ""),
                    importance=meta.get("importance", 0.5),
                    created_at=meta.get("created_at", ""),
                    relevance_score=round(similarity, 3),
                ))
            return memories

        else:
            # Mock retrieval: cosine similarity
            candidates = [
                item for item in self._mock_store
                if (not customer_id or item["metadata"]["customer_id"] == customer_id)
                and (not memory_type or item["metadata"]["memory_type"] == memory_type)
                and item["metadata"].get("importance", 0) >= min_importance
            ]

            scored = []
            for item in candidates:
                sim = self._cosine_similarity(query_embedding, item["embedding"])
                scored.append((sim, item))

            scored.sort(key=lambda x: x[0], reverse=True)

            return [
                Memory(
                    id=item["id"],
                    text=item["text"],
                    customer_id=item["metadata"]["customer_id"] or None,
                    memory_type=item["metadata"]["memory_type"],
                    importance=item["metadata"]["importance"],
                    created_at=item["metadata"]["created_at"],
                    relevance_score=round(sim, 3),
                )
                for sim, item in scored[:top_k]
            ]

    def forget(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        if not self._use_mock:
            self._collection.delete(ids=[memory_id])
            return True
        original_len = len(self._mock_store)
        self._mock_store = [m for m in self._mock_store if m["id"] != memory_id]
        return len(self._mock_store) < original_len

    def count(self, customer_id: Optional[str] = None) -> int:
        """Count stored memories."""
        if not self._use_mock:
            if customer_id:
                results = self._collection.get(where={"customer_id": customer_id})
                return len(results["ids"])
            return self._collection.count()
        if customer_id:
            return sum(1 for m in self._mock_store if m["metadata"]["customer_id"] == customer_id)
        return len(self._mock_store)

    def get_context_for_prompt(
        self,
        query: str,
        customer_id: Optional[str] = None,
        top_k: int = 3,
    ) -> str:
        """
        Get relevant memories formatted for injection into a prompt.

        Returns a string ready to insert into the agent's system prompt
        or context block.
        """
        memories = self.recall(query, customer_id=customer_id, top_k=top_k)
        if not memories:
            return ""

        lines = ["[Relevant customer memories:]"]
        for mem in memories:
            score_pct = f"{mem.relevance_score:.0%}" if mem.relevance_score else "?"
            lines.append(f"- [{mem.memory_type}, relevance {score_pct}] {mem.text}")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def demo_store_and_recall():
    """Show semantic memory store and retrieval."""
    print("\n" + "=" * 60)
    print("  Vector Memory Demo: Store and Recall")
    print("=" * 60)

    memory = VectorMemory()

    # Store memories about a customer
    print("\n  Storing memories about customer alice@example.com...")

    memory_ids = []
    memories_to_store = [
        ("Customer escalated to her manager after a billing dispute in January. Was very frustrated.", "interaction", 0.9),
        ("Customer prefers email over phone. She mentioned this explicitly.", "preference", 0.7),
        ("Customer is on the Pro plan, pays annually. $948/year contract.", "fact", 0.8),
        ("Customer complained about the CSV export feature twice. First time was Chrome issue, second time was filter bug.", "issue", 0.8),
        ("Customer expressed interest in upgrading to Enterprise if API limits can be increased.", "interaction", 0.7),
        ("Customer's company has 50+ employees, considering team rollout.", "fact", 0.6),
    ]

    for text, mem_type, importance in memories_to_store:
        mid = memory.remember(text, customer_id="alice@example.com", memory_type=mem_type, importance=importance)
        memory_ids.append(mid)
        print(f"  Stored [{mem_type}]: {text[:60]}...")

    print(f"\n  Total memories stored: {memory.count('alice@example.com')}")

    # Retrieve by semantic similarity
    queries = [
        "customer is angry about billing",
        "customer wants to upgrade their plan",
        "export issues",
    ]

    for query in queries:
        print(f"\n  Query: '{query}'")
        results = memory.recall(query, customer_id="alice@example.com", top_k=2)
        for result in results:
            print(f"    [{result.relevance_score:.2%}] {result.text[:70]}...")


def demo_prompt_injection():
    """Show how memory context is injected into prompts."""
    print("\n" + "=" * 60)
    print("  Demo: Memory-Enhanced Prompt")
    print("=" * 60)

    memory = VectorMemory()

    # Store some context
    memory.remember(
        "Customer contacted support 3 times about billing in the past 6 months",
        customer_id="repeat-customer",
        memory_type="interaction",
        importance=0.9,
    )
    memory.remember(
        "Customer expressed frustration with automated responses, prefers talking to humans",
        customer_id="repeat-customer",
        memory_type="preference",
        importance=0.8,
    )

    # Get context for a new billing ticket
    context = memory.get_context_for_prompt(
        query="customer has billing question",
        customer_id="repeat-customer",
        top_k=3,
    )

    system_prompt = f"""You are a customer support agent.

{context}

Use this customer history to provide a personalized response that acknowledges
their past experience and addresses their concerns empathetically."""

    print("\n  Generated system prompt with memory context:")
    print(f"  {'─' * 50}")
    print(f"  {system_prompt}")
    print(f"  {'─' * 50}")
    print("\n  The agent now 'knows' this customer's history before the first message!")


if __name__ == "__main__":
    demo_store_and_recall()
    demo_prompt_injection()
