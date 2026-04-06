"""
02_rag_pipeline.py - Production RAG Pipeline
=============================================
Module 6: RAG for Agents

A production-grade RAG pipeline adds:
1. Document chunking (split large docs into semantic chunks)
2. Metadata filtering (only search relevant categories)
3. Reranking (cross-encoder to improve relevance)
4. Hybrid search (vector + keyword)
5. Context compression (trim irrelevant parts before injecting)

Run with: python module_06_rag/examples/02_rag_pipeline.py
Requires: OPENAI_API_KEY, ChromaDB running
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Chunk:
    """A chunk of a larger document."""
    id: str
    doc_id: str
    title: str
    content: str
    chunk_index: int
    category: str
    word_count: int


@dataclass
class RetrievedChunk:
    """A retrieved chunk with its relevance score."""
    chunk: Chunk
    similarity_score: float
    rerank_score: Optional[float] = None

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.similarity_score


class DocumentChunker:
    """
    Splits documents into overlapping chunks for indexing.

    Chunking strategy matters for RAG quality:
    - Too small: loses context
    - Too large: wastes tokens and reduces precision

    This implementation uses sentence-based chunking with overlap.
    """

    def __init__(self, max_words: int = 150, overlap_sentences: int = 1):
        self.max_words = max_words
        self.overlap_sentences = overlap_sentences

    def chunk(self, doc: dict) -> list[Chunk]:
        """Split a document into overlapping chunks."""
        content = doc.get("content", "")
        sentences = self._split_sentences(content)

        if not sentences:
            return []

        chunks = []
        chunk_idx = 0
        i = 0

        while i < len(sentences):
            chunk_sentences = []
            word_count = 0

            while i < len(sentences) and word_count < self.max_words:
                chunk_sentences.append(sentences[i])
                word_count += len(sentences[i].split())
                i += 1

            chunk_text = " ".join(chunk_sentences)
            if chunk_text.strip():
                chunks.append(Chunk(
                    id=f"{doc['id']}_chunk_{chunk_idx}",
                    doc_id=doc["id"],
                    title=doc.get("title", ""),
                    content=chunk_text,
                    chunk_index=chunk_idx,
                    category=doc.get("category", ""),
                    word_count=len(chunk_text.split()),
                ))
                chunk_idx += 1

            # Overlap: go back by overlap_sentences
            if i < len(sentences):
                i = max(i - self.overlap_sentences, 0)

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]


class ProductionRAGPipeline:
    """
    A production RAG pipeline with chunking, metadata filtering,
    and score-based reranking.
    """

    def __init__(
        self,
        collection_name: str = "production_rag",
        chroma_host: str = None,
        chroma_port: int = None,
    ):
        self.collection_name = collection_name
        self.chroma_host = chroma_host or os.environ.get("CHROMA_HOST", "localhost")
        self.chroma_port = chroma_port or int(os.environ.get("CHROMA_PORT", "8000"))
        self._collection = None
        self._chunker = DocumentChunker()

    def _get_collection(self):
        if self._collection:
            return self._collection
        try:
            import chromadb
            client = chromadb.HttpClient(host=self.chroma_host, port=self.chroma_port)
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception:
            return None

    def _embed(self, texts: list[str]) -> Optional[list[list[float]]]:
        """Batch embed texts using OpenAI."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            return None

    def index(self, documents: list[dict]) -> int:
        """Chunk, embed, and store documents."""
        collection = self._get_collection()
        if not collection:
            return 0

        all_chunks = []
        for doc in documents:
            chunks = self._chunker.chunk(doc)
            all_chunks.extend(chunks)

        print(f"  Created {len(all_chunks)} chunks from {len(documents)} documents")

        # Embed in batches
        batch_size = 100
        total_indexed = 0

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            texts = [c.content for c in batch]
            embeddings = self._embed(texts)

            if not embeddings:
                break

            collection.upsert(
                ids=[c.id for c in batch],
                embeddings=embeddings,
                documents=texts,
                metadatas=[{
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "category": c.category,
                    "chunk_index": c.chunk_index,
                    "word_count": c.word_count,
                } for c in batch],
            )
            total_indexed += len(batch)

        return total_indexed

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
        min_similarity: float = 0.3,
    ) -> list[RetrievedChunk]:
        """
        Retrieve relevant chunks with optional metadata filtering.

        1. Embed the query
        2. Search ChromaDB with optional category filter
        3. Apply minimum similarity threshold
        """
        collection = self._get_collection()
        if not collection:
            return self._keyword_fallback(query, n_results, category_filter)

        embeddings = self._embed([query])
        if not embeddings:
            return self._keyword_fallback(query, n_results, category_filter)

        where = {"category": category_filter} if category_filter else None

        results = collection.query(
            query_embeddings=embeddings,
            n_results=min(n_results * 2, 20),  # Over-retrieve for reranking
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for i, doc_id in enumerate(results["ids"][0]):
            similarity = 1 - results["distances"][0][i]
            if similarity < min_similarity:
                continue
            meta = results["metadatas"][0][i]
            chunk = Chunk(
                id=doc_id,
                doc_id=meta["doc_id"],
                title=meta["title"],
                content=results["documents"][0][i],
                chunk_index=meta["chunk_index"],
                category=meta["category"],
                word_count=meta["word_count"],
            )
            chunks.append(RetrievedChunk(chunk=chunk, similarity_score=similarity))

        return chunks[:n_results]

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """
        Rerank chunks using an LLM-based cross-encoder.

        A cross-encoder evaluates (query, document) pairs together,
        which is more accurate than embedding similarity but slower.

        For production: use a dedicated reranking model (e.g., Cohere Rerank).
        Here: use GPT to score relevance.
        """
        if not chunks or not os.environ.get("OPENAI_API_KEY"):
            return chunks

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            docs_text = "\n\n".join(
                f"Document {i+1}: {c.chunk.content[:200]}"
                for i, c in enumerate(chunks)
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Query: {query}\n\n{docs_text}\n\n"
                        f"Score each document's relevance to the query (0-10). "
                        f"Return JSON: {{\"scores\": [n, n, ...]}}"
                    ),
                }],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=100,
            )

            import json
            scores = json.loads(response.choices[0].message.content).get("scores", [])
            for i, score in enumerate(scores[:len(chunks)]):
                chunks[i].rerank_score = score / 10.0

            chunks.sort(key=lambda x: x.final_score, reverse=True)
        except Exception:
            pass

        return chunks

    def _keyword_fallback(self, query: str, n_results: int, category_filter: Optional[str]) -> list[RetrievedChunk]:
        """Fallback keyword search."""
        # Minimal fallback for when ChromaDB is unavailable
        return []

    def build_context(
        self,
        retrieved: list[RetrievedChunk],
        max_tokens: int = 2000,
    ) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        context_parts = []
        total_words = 0

        for item in retrieved:
            chunk = item.chunk
            score = item.final_score
            words = chunk.word_count

            if total_words + words > max_tokens * 0.75:  # Rough token/word ratio
                break

            context_parts.append(
                f"[Source: {chunk.title} | Relevance: {score:.0%}]\n{chunk.content}"
            )
            total_words += words

        return "\n\n---\n\n".join(context_parts)


def demo():
    print("\n" + "=" * 60)
    print("  Production RAG Pipeline Demo")
    print("=" * 60)

    # Show chunking
    doc = {
        "id": "doc_test",
        "title": "Password Reset Guide",
        "category": "account_access",
        "content": (
            "Resetting your password is easy. First, go to the login page. "
            "Click the 'Forgot Password' link below the login form. "
            "Enter the email address associated with your account. "
            "Check your inbox for the password reset email. "
            "If you don't see it within 5 minutes, check your spam folder. "
            "Click the secure reset link in the email. "
            "The link expires after 24 hours for security. "
            "Enter your new password and confirm it. "
            "Your new password must be at least 8 characters long. "
            "Include at least one uppercase letter and one number."
        ),
    }

    chunker = DocumentChunker(max_words=50, overlap_sentences=1)
    chunks = chunker.chunk(doc)

    print(f"\n  Chunking demo (max 50 words per chunk):")
    print(f"  Document: {len(doc['content'].split())} words → {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"\n  Chunk {i+1} ({chunk.word_count} words):")
        print(f"    {chunk.content[:100]}...")

    # Show pipeline
    print(f"\n  Full pipeline with ChromaDB:")
    pipeline = ProductionRAGPipeline()
    collection = pipeline._get_collection()

    if collection and os.environ.get("OPENAI_API_KEY"):
        documents = [doc]
        indexed = pipeline.index(documents)
        print(f"  Indexed {indexed} chunks")

        query = "I forgot my password"
        retrieved = pipeline.retrieve(query, n_results=3)
        print(f"\n  Retrieved {len(retrieved)} chunks for: '{query}'")

        if retrieved:
            reranked = pipeline.rerank(query, retrieved)
            context = pipeline.build_context(reranked)
            print(f"\n  Context for LLM:\n  {context[:300]}...")
    else:
        print("  (Requires ChromaDB + OPENAI_API_KEY)")
        print("  Chunker demo above shows the key concept.")


if __name__ == "__main__":
    demo()
