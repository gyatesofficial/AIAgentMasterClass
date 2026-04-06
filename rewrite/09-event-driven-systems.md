# Module 9: Data Engineering for AI

*The hottest intersection in tech. Learn to build the data infrastructure that powers AI applications.*

---

## 9.1 How AI Changes the Data Engineer's Job

> **TL;DR:** AI doesn't replace data engineers -- it creates MORE work for us. Every AI application needs data pipelines feeding it. The new skills to learn: embeddings pipelines, vector database management, feature stores, RAG data layers, and LLM data preparation. These all build on top of the data engineering skills you already have.

In 2026, every company wants AI. But AI is useless without good data. That's where you come in as a DE.

If you've been watching job postings, you've noticed something: "data engineer" roles increasingly mention AI, LLMs, embeddings, and vector databases. This isn't a fad. AI is fundamentally changing what data engineers build.

But here's what nobody tells you: AI doesn't replace data engineers. It creates MORE work for us. Every AI application needs data pipelines feeding it. Every LLM needs clean, chunked, embedded data. Every ML model needs features computed and served.

### Traditional vs AI-Augmented Pipeline

**Traditional Pipeline:**

```
Source -> Extract -> Transform -> Load -> Dashboard
```

**AI-Augmented Pipeline:**

```
Source -> Extract -> Transform -> Load -> Dashboard
                       |
            Chunk -> Embed -> Vector DB -> RAG API
                       |
            Feature Store -> ML Model -> Predictions
```

Same pipeline, but with new branches. As a data engineer, you're building those branches.

### The New Things You'll Build

1. **Embeddings pipelines** -- converting text/images into vectors that ML models can use
2. **Vector database management** -- storing and indexing embeddings for similarity search
3. **Feature stores** -- pre-computing features for ML models
4. **RAG data layers** -- preparing and serving data for Retrieval-Augmented Generation
5. **LLM data prep** -- cleaning, chunking, and enriching data for fine-tuning or prompting

The AI Data Stack is a layered architecture. The bottom layers -- Ingestion, Storage, Data Lake -- are the same data engineering you've been learning this whole course. The top layers -- Vector DB, Feature Store, Embeddings, Feature Computation, Vector Search, Feature Serving -- are new, but they're built ON TOP of your existing skills. In every AI project, the ML/AI engineer builds the model. The data engineer builds everything that feeds it.

> **Key Concept: The AI Data Stack**
> The bottom layers of the AI stack are the same data engineering you've been learning this whole course. The top layers are new, but they're built ON TOP of your existing skills. In every AI project, the ML/AI engineer builds the model. The data engineer builds everything that feeds it.

> **Common Mistake**
> - Thinking you need to understand deep learning to do AI data engineering. You don't. You need to understand data formats, pipelines, and APIs.
> - Ignoring this trend. The DEs who learn these skills now will be the most valuable ones in 2-3 years.

### Checkpoint

1. How does an AI-augmented pipeline differ from a traditional data pipeline?
2. Name three new things data engineers build for AI workloads.
3. Why does AI create *more* work for data engineers, not less?

---

## 9.2 Feature Stores -- What They Are and When You Need One

> **TL;DR:** A feature store is a centralized system for computing, storing, and serving ML-ready features. Most teams don't need a full-blown feature store (like Feast) until they have 5+ ML models. For 1-2 models, well-organized SQL views and a simple API are enough. Build simple first.

An ML engineer says: *"I need the customer's average order value, their total orders in the last 30 days, and their most recent order date. Updated daily for batch predictions, and in real-time for the API."*

You could write a SQL query. But then another ML engineer needs different features. And another. And they all need the *exact same features* computed the *exact same way* so training and serving are consistent. This is the problem feature stores solve.

### What a Feature Store Does

1. **Computes features** -- running transformations that produce ML-ready values
2. **Stores features** -- persisting them for both batch (training) and online (serving) use
3. **Serves features** -- making them available with low latency for real-time predictions
4. **Ensures consistency** -- same feature definition used in training and serving

### Do You Actually Need One?

Honest answer: most teams don't need a full-blown feature store until they have 5+ ML models in production.

| Scenario | Recommendation |
|----------|---------------|
| 1-2 models, batch only | SQL views + scheduled materialization. No feature store needed. |
| 1-2 models, real-time | Pre-computed features in Redis. Still no formal feature store. |
| 5+ models, shared features | Feature store (Feast, Tecton, or custom). |
| Enterprise, 50+ models | Feast, Tecton, or Databricks Feature Store. |

### Building a Simple Feature Store

Here's what you'd build at a startup before you need Feast -- a minimal feature store in Postgres + Python:

```sql
-- Feature table: one row per customer, updated daily
CREATE TABLE IF NOT EXISTS feature_store.customer_features (
    customer_id INTEGER PRIMARY KEY,

    -- Order features
    total_orders INTEGER,
    total_revenue DECIMAL(12,2),
    avg_order_value DECIMAL(10,2),
    orders_last_30_days INTEGER,
    days_since_last_order INTEGER,

    -- Behavioral features
    favorite_category VARCHAR(100),
    distinct_products_purchased INTEGER,

    -- Metadata
    computed_at TIMESTAMP DEFAULT NOW(),
    feature_version VARCHAR(20) DEFAULT '1.0'
);

-- Materialization query: compute features from raw data
INSERT INTO feature_store.customer_features
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COALESCE(SUM(o.total_amount), 0) AS total_revenue,
    COALESCE(AVG(o.total_amount), 0) AS avg_order_value,
    COUNT(DISTINCT CASE
        WHEN o.order_date >= CURRENT_DATE - INTERVAL '30 days'
        THEN o.order_id
    END) AS orders_last_30_days,
    EXTRACT(DAY FROM NOW() - MAX(o.order_date))::INTEGER AS days_since_last_order,
    MODE() WITHIN GROUP (ORDER BY p.category) AS favorite_category,
    COUNT(DISTINCT li.product_id) AS distinct_products_purchased,
    NOW() AS computed_at,
    '1.0' AS feature_version
FROM dim_customers c
LEFT JOIN fact_orders o ON c.customer_id = o.customer_id
LEFT JOIN fact_line_items li ON o.order_id = li.order_id
LEFT JOIN dim_products p ON li.product_id = p.product_id
GROUP BY c.customer_id
ON CONFLICT (customer_id) DO UPDATE SET
    total_orders = EXCLUDED.total_orders,
    total_revenue = EXCLUDED.total_revenue,
    avg_order_value = EXCLUDED.avg_order_value,
    orders_last_30_days = EXCLUDED.orders_last_30_days,
    days_since_last_order = EXCLUDED.days_since_last_order,
    favorite_category = EXCLUDED.favorite_category,
    distinct_products_purchased = EXCLUDED.distinct_products_purchased,
    computed_at = EXCLUDED.computed_at;
```

Python class to serve features:

```python
# feature_store/store.py
import psycopg2
from dataclasses import dataclass
from typing import Optional


@dataclass
class CustomerFeatures:
    customer_id: int
    total_orders: int
    total_revenue: float
    avg_order_value: float
    orders_last_30_days: int
    days_since_last_order: Optional[int]
    favorite_category: Optional[str]
    distinct_products_purchased: int
    computed_at: str
    feature_version: str


class FeatureStore:
    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)

    def get_customer_features(self, customer_id: int) -> Optional[CustomerFeatures]:
        """Get features for a single customer (online serving)."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM feature_store.customer_features WHERE customer_id = %s",
                (customer_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return CustomerFeatures(*row)

    def get_batch_features(self, customer_ids: list[int]) -> list[CustomerFeatures]:
        """Get features for multiple customers (batch prediction)."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM feature_store.customer_features WHERE customer_id = ANY(%s)",
                (customer_ids,),
            )
            return [CustomerFeatures(*row) for row in cur.fetchall()]

    def get_training_dataset(self, feature_version: str = "1.0") -> list[CustomerFeatures]:
        """Get all features for model training."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM feature_store.customer_features WHERE feature_version = %s",
                (feature_version,),
            )
            return [CustomerFeatures(*row) for row in cur.fetchall()]


# Usage
store = FeatureStore("postgresql://postgres:postgres@localhost:5432/ecommerce")
features = store.get_customer_features(customer_id=42)
print(f"Customer 42: {features.total_orders} orders, ${features.avg_order_value} avg")
```

**Expected output:**

```
Customer 42: 17 orders, $84.32 avg
```

> **Common Mistake**
> - Over-engineering the feature store before you have any ML models in production. Build simple first.
> - Training-serving skew: computing features differently in training vs serving. Use the SAME SQL/code for both.
> - Not versioning features. When you change how a feature is computed, old models trained on the old version will break.

### Checkpoint

1. What problem does a feature store solve?
2. At what scale should you consider a formal feature store like Feast?
3. What is training-serving skew and why is it dangerous?

---

## 9.3 Embeddings Pipelines -- Turning Text Into Vectors

> **TL;DR:** An embedding is a list of numbers (vector) representing the "meaning" of text. Similar meanings produce similar vectors. Build pipelines that generate embeddings incrementally (only new/changed items), in batches (API rate limits), and store the original text alongside the vector. OpenAI's `text-embedding-3-small` is cheap (~$0.10 per 100K products); open-source `all-MiniLM-L6-v2` is free and runs locally.

How does ChatGPT "understand" that "dog" and "puppy" mean similar things? How does semantic search know that "cheap flights to Paris" should match "budget airline tickets to France"?

Embeddings.

### How Embeddings Work

An embedding is a list of numbers (a vector) that represents the "meaning" of a piece of text. Think of it as coordinates in a high-dimensional space, where proximity corresponds to semantic similarity:

```
"I love pizza"                -> [0.023, -0.156, 0.892, ..., 0.044]  # 1536 numbers
"Pizza is great"              -> [0.019, -0.148, 0.887, ..., 0.041]  # Similar numbers!
"The stock market crashed"    -> [-0.445, 0.312, -0.019, ..., 0.678]  # Very different
```

Similar meanings -> similar vectors -> similar numbers. Think of embeddings as coordinates on a map. "Pizza" and "pasta" are close together. "Pizza" and "stock market" are far apart.

> **Key Concept: Embeddings**
> An embedding converts unstructured data (text, images) into a fixed-length numerical vector. The key property: semantically similar inputs produce vectors that are close together in vector space. This enables similarity search, clustering, and classification without keyword matching.

### Why Cosine Similarity Works

When you have two embedding vectors, you need a way to measure "how similar are these?" The standard answer is cosine similarity. It measures the angle between two vectors, ignoring their magnitude. A cosine similarity of 1.0 means identical direction (identical meaning), 0.0 means orthogonal (unrelated), and -1.0 means opposite.

Why cosine and not Euclidean distance? Because embeddings can vary in magnitude based on text length and other factors. Cosine similarity normalizes for this -- it only cares about the *direction* the vector points, which corresponds to meaning. A short product title and a long product description about the same item will have similar cosine similarity even though their raw vectors have different magnitudes.

In pgvector, the `<=>` operator computes cosine *distance* (1 - cosine_similarity). Lower distance = more similar.

### Building an Embeddings Pipeline

A pipeline that generates embeddings for product descriptions -- used for "similar products" or semantic search:

```python
# embeddings/pipeline.py
import openai
import psycopg2
import time
from dataclasses import dataclass


@dataclass
class ProductEmbedding:
    product_id: int
    product_name: str
    description: str
    embedding: list[float]


class EmbeddingsPipeline:
    """Generate and store embeddings for product catalog."""

    def __init__(
        self,
        openai_api_key: str,
        db_connection_string: str,
        model: str = "text-embedding-3-small",  # Cheap and good
        batch_size: int = 100,
    ):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.conn = psycopg2.connect(db_connection_string)
        self.model = model
        self.batch_size = batch_size

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts using OpenAI API."""
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def get_products_without_embeddings(self) -> list[dict]:
        """Find products that don't have embeddings yet (incremental)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT p.product_id, p.product_name, p.description
                FROM dim_products p
                LEFT JOIN product_embeddings pe ON p.product_id = pe.product_id
                WHERE pe.product_id IS NULL
                    OR pe.updated_at < p.updated_at  -- Re-embed if product changed
                ORDER BY p.product_id
            """)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def store_embeddings(self, product_embeddings: list[ProductEmbedding]) -> None:
        """Store embeddings in Postgres with pgvector."""
        with self.conn.cursor() as cur:
            for pe in product_embeddings:
                cur.execute("""
                    INSERT INTO product_embeddings (product_id, embedding, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (product_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                """, (pe.product_id, pe.embedding))
        self.conn.commit()

    def run(self) -> int:
        """Run the full embeddings pipeline. Returns number processed."""
        products = self.get_products_without_embeddings()

        if not products:
            print("No products need embedding updates.")
            return 0

        print(f"Processing {len(products)} products...")
        total_processed = 0

        for i in range(0, len(products), self.batch_size):
            batch = products[i:i + self.batch_size]

            # Combine name + description for richer embeddings
            texts = [
                f"{p['product_name']}: {p['description']}"
                for p in batch
            ]

            embeddings = self.generate_embeddings(texts)

            product_embeddings = [
                ProductEmbedding(
                    product_id=p["product_id"],
                    product_name=p["product_name"],
                    description=p["description"],
                    embedding=emb,
                )
                for p, emb in zip(batch, embeddings)
            ]

            self.store_embeddings(product_embeddings)
            total_processed += len(batch)
            print(f"  Processed {total_processed}/{len(products)} products")

            # Rate limiting
            if i + self.batch_size < len(products):
                time.sleep(1)

        return total_processed


# Usage
if __name__ == "__main__":
    import os
    pipeline = EmbeddingsPipeline(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        db_connection_string=os.environ["DATABASE_URL"],
    )
    processed = pipeline.run()
    print(f"Done! Processed {processed} products.")
```

**Expected output:**

```
Processing 500 products...
  Processed 100/500 products
  Processed 200/500 products
  Processed 300/500 products
  Processed 400/500 products
  Processed 500/500 products
Done! Processed 500 products.
```

### Using Open-Source Models Instead

OpenAI is easy but costs money. For production at scale, use open-source models:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # 384 dimensions, fast

texts = [
    "Wireless Bluetooth Headphones: Premium sound quality with noise cancellation",
    "Running Shoes: Lightweight mesh with responsive cushioning",
]

embeddings = model.encode(texts)
print(f"Embedding shape: {embeddings.shape}")
print(f"Embedding sample: {embeddings[0][:5]}")
```

**Expected output:**

```
Embedding shape: (2, 384)
Embedding sample: [ 0.0234 -0.0891  0.1123 -0.0456  0.0789]
```

> **Companion code:** See `module-9/solution/src/embeddings_pipeline.py` for the sentence-transformers version that uses `all-MiniLM-L6-v2` instead of OpenAI. This runs entirely locally with no API key needed.

### Model Comparison

| Model | Dimensions | Cost | Quality | Speed |
|-------|-----------|------|---------|-------|
| OpenAI `text-embedding-3-small` | 1536 | $0.02/1M tokens | Best | API call required |
| `all-MiniLM-L6-v2` | 384 | Free | Good | Fast, runs locally |
| `e5-large-v2` | 1024 | Free | Near-OpenAI | Slower, runs locally |

### Cost Estimation

OpenAI `text-embedding-3-small` at ~$0.02 per 1M tokens:

- Average product description: ~50 tokens
- 100K products: ~5M tokens = **~$0.10**
- Even at 1M products, you're looking at **$1**

> **Common Mistake**
> - Embedding entire documents as one vector. Long documents should be chunked first (covered in Section 9.5).
> - Not storing the text alongside the embedding. You'll need it for debugging and returning results.
> - Re-embedding everything on every run. Use incremental logic -- only embed new or changed items.
> - Using the wrong model for your use case. Multilingual data? Use a multilingual model.

### Checkpoint

1. What is an embedding and what key property makes it useful?
2. Why should you combine product name + description before embedding?
3. When would you choose an open-source embedding model over OpenAI?

---

## 9.4 Vector Databases -- Storage and Retrieval

> **TL;DR:** A vector database stores and searches high-dimensional vectors efficiently using specialized indexes. Start with **pgvector** (Postgres extension) -- no new infrastructure needed. It handles millions of vectors easily. Use HNSW indexes for production (faster queries) and IVFFlat for simpler cases. Cosine similarity is the standard metric.

You've got 100,000 product embeddings -- each a list of 1,536 numbers. A customer searches for "comfortable shoes for running." You generate an embedding for that query. Now you need to find the 10 most similar products. Vector databases solve this with special indexes that make similarity search fast.

You already know Postgres. Vector search is just another index type. That is the key insight here -- pgvector turns your existing Postgres into a vector database without learning a new system.

### Choosing a Vector Database

| Database | Type | Best For |
|----------|------|----------|
| **pgvector** | Postgres extension | Teams already using Postgres -- no new infrastructure |
| **Pinecone** | Managed cloud | Quick start, no ops ($70+/month) |
| **Weaviate** | Open-source | Self-hosted, full-featured |
| **Qdrant** | Open-source | Performance-focused |
| **ChromaDB** | Open-source | Prototyping only (not production scale) |

**Recommendation: start with pgvector.** If you're already using Postgres, adding pgvector is one command. No new database to manage. It handles millions of vectors easily.

### Setting Up pgvector

```sql
-- Enable the extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the embeddings table
CREATE TABLE product_embeddings (
    product_id INTEGER PRIMARY KEY REFERENCES dim_products(product_id),
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    updated_at TIMESTAMP DEFAULT NOW()
);

-- HNSW index (recommended for production -- faster queries, more accurate)
CREATE INDEX ON product_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

> **Key Concept: Vector Index Types**
> - **IVFFlat** -- faster to build, slightly less accurate. Good for getting started. Set `lists = sqrt(num_rows)`.
> - **HNSW** -- slower to build, more accurate, faster queries. Better for production.
> Without an index, every query does a full table scan. Fine for 1,000 rows, terrible for 100K+.

> **Companion code:** See `module-9/starter/sql/init.sql` for the complete pgvector schema including both `product_embeddings` and `document_chunks` tables with HNSW indexes.

### Similarity Search in SQL

```sql
-- Find 10 most similar products to a given embedding
-- The <=> operator computes cosine distance (1 - cosine_similarity)
SELECT
    p.product_id,
    p.product_name,
    p.description,
    1 - (pe.embedding <=> '[0.023, -0.156, 0.892, ...]'::vector) AS similarity
FROM product_embeddings pe
JOIN dim_products p ON pe.product_id = p.product_id
ORDER BY pe.embedding <=> '[0.023, -0.156, 0.892, ...]'::vector
LIMIT 10;
```

### Python Integration

```python
# vector_search/search.py
import psycopg2
from dataclasses import dataclass


@dataclass
class SearchResult:
    product_id: int
    product_name: str
    description: str
    similarity: float


class VectorSearch:
    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)

    def search_similar_products(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_similarity: float = 0.5,
    ) -> list[SearchResult]:
        """Find products similar to the query embedding."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.product_id,
                    p.product_name,
                    p.description,
                    1 - (pe.embedding <=> %s::vector) AS similarity
                FROM product_embeddings pe
                JOIN dim_products p ON pe.product_id = p.product_id
                WHERE 1 - (pe.embedding <=> %s::vector) > %s
                ORDER BY pe.embedding <=> %s::vector
                LIMIT %s
            """, (str(query_embedding), str(query_embedding),
                  min_similarity, str(query_embedding), limit))

            return [
                SearchResult(
                    product_id=row[0],
                    product_name=row[1],
                    description=row[2],
                    similarity=round(row[3], 4),
                )
                for row in cur.fetchall()
            ]

    def find_similar_to_product(
        self,
        product_id: int,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Find products similar to a given product."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT embedding FROM product_embeddings WHERE product_id = %s",
                (product_id,),
            )
            row = cur.fetchone()
            if row is None:
                return []

            embedding = row[0]

            cur.execute("""
                SELECT
                    p.product_id,
                    p.product_name,
                    p.description,
                    1 - (pe.embedding <=> %s::vector) AS similarity
                FROM product_embeddings pe
                JOIN dim_products p ON pe.product_id = p.product_id
                WHERE pe.product_id != %s
                ORDER BY pe.embedding <=> %s::vector
                LIMIT %s
            """, (embedding, product_id, embedding, limit))

            return [
                SearchResult(
                    product_id=row[0],
                    product_name=row[1],
                    description=row[2],
                    similarity=round(row[3], 4),
                )
                for row in cur.fetchall()
            ]


# Usage
search = VectorSearch("postgresql://postgres:postgres@localhost:5432/ecommerce")
results = search.find_similar_to_product(42, limit=5)
for r in results:
    print(f"  {r.product_name} (similarity: {r.similarity})")
```

**Expected output:**

```
ProElite Running Max 72 (similarity: 0.9234)
ActiveGear Running Lite 18 (similarity: 0.9012)
NatureFit Training Pro 45 (similarity: 0.8756)
CoreBasics Running Essential 91 (similarity: 0.8543)
UrbanEdge Shoes Ultra 33 (similarity: 0.8201)
```

> **Companion code:** See `module-9/solution/src/vector_search.py` for the sentence-transformers version that accepts natural language queries directly (embedding the query text internally).

### Performance at Scale

| Rows | IVFFlat Query Time | HNSW Query Time |
|------|-------------------|-----------------|
| 100K | ~5ms | ~2ms |
| 1M | ~20ms | ~5ms |
| 10M | ~100ms | ~15ms |

For most applications, this is more than fast enough. Sub-millisecond at billions of vectors is when you'd look at Pinecone or a dedicated vector database.

> **Common Mistake**
> - Forgetting to create an index. Without one, queries do full table scans.
> - Not tuning index parameters. Adjust `lists` (IVFFlat) or `m` / `ef_construction` (HNSW) based on data size.
> - Mixing embedding dimensions. If you switch models (1536-dim to 384-dim), you need new columns or tables.

### At Your Job: Natural Language Product Search

Your ML team says "we need a product search that understands natural language." Here's how you build the data pipeline for that:

1. **Extract** product data from the catalog database (name, description, category, attributes)
2. **Transform** the text: combine name + category + description into a single embedding input
3. **Embed** each product using your chosen model (OpenAI API or sentence-transformers)
4. **Store** the embeddings in pgvector alongside the product_id
5. **Index** with HNSW for fast retrieval
6. **Serve** through a search API that embeds the user's query and runs a similarity search

The ML team handles the model selection. You handle steps 1-6 -- the entire data pipeline.

### Checkpoint

1. What's the difference between IVFFlat and HNSW indexes?
2. What does the `<=>` operator compute in pgvector?
3. Why should you start with pgvector instead of a dedicated vector database?

---

## 9.5 RAG Pipeline Architecture -- Building the Data Layer

> **TL;DR:** RAG (Retrieval-Augmented Generation) is ~20% LLM and ~80% data engineering. The data engineer builds the indexing pipeline (documents -> chunk -> embed -> store) and the retrieval layer (query -> embed -> vector search -> top K chunks). Chunking strategy has the biggest impact on quality. Use 300-500 token chunks with overlap.

RAG -- Retrieval-Augmented Generation -- is the pattern behind every "chat with your documents" application. And while the ML engineers get credit for the chatbot, guess who builds the entire data layer? Us.

Instead of fine-tuning an LLM (expensive, slow, requires ML expertise), you give it relevant context at query time. The DE builds the retrieval part. The LLM just reads the context you provide and generates an answer. Think of it like giving a smart intern the relevant pages from a manual before asking them a question -- they don't need to memorize the whole manual, they just need the right pages.

### The Two Phases of RAG

**Phase 1: Indexing (offline -- your job)**

```
Documents -> Chunk -> Embed -> Store in Vector DB
```

**Phase 2: Query (online -- real-time)**

```
User Question -> Embed -> Search Vector DB -> Top K Chunks -> LLM -> Answer
```

You build Phase 1 and the retrieval part of Phase 2.

### Step 1: Document Ingestion

```python
# rag/ingest.py
from pathlib import Path
import fitz  # PyMuPDF for PDF parsing
from dataclasses import dataclass


@dataclass
class Document:
    content: str
    metadata: dict  # source file, page number, etc.


def load_pdf(path: str) -> list[Document]:
    """Extract text from a PDF file."""
    doc = fitz.open(path)
    documents = []
    for page_num, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            documents.append(Document(
                content=text,
                metadata={
                    "source": Path(path).name,
                    "page": page_num + 1,
                    "type": "pdf",
                },
            ))
    return documents


def load_text(path: str) -> list[Document]:
    """Load a plain text or markdown file."""
    content = Path(path).read_text()
    return [Document(
        content=content,
        metadata={"source": Path(path).name, "type": "text"},
    )]


def load_documents(directory: str) -> list[Document]:
    """Load all supported documents from a directory."""
    docs = []
    dir_path = Path(directory)

    for pdf in dir_path.glob("**/*.pdf"):
        docs.extend(load_pdf(str(pdf)))
    for txt in dir_path.glob("**/*.txt"):
        docs.extend(load_text(str(txt)))
    for md in dir_path.glob("**/*.md"):
        docs.extend(load_text(str(md)))

    print(f"Loaded {len(docs)} document sections from {directory}")
    return docs
```

### Step 2: Chunking

This is the most underrated step in RAG. How you chunk documents has a massive impact on retrieval quality.

Why does chunking matter? If your chunks are too large, the embedding becomes a blurry average of many topics -- the vector doesn't represent any single idea well. If too small, you lose context -- a sentence fragment doesn't carry enough meaning on its own. The sweet spot is 300-500 tokens, where each chunk captures a coherent idea with enough surrounding context.

```python
# rag/chunker.py
from dataclasses import dataclass


@dataclass
class Chunk:
    content: str
    metadata: dict
    chunk_index: int


def chunk_by_tokens(
    text: str,
    chunk_size: int = 500,      # tokens per chunk
    chunk_overlap: int = 50,    # overlap between chunks
) -> list[str]:
    """Split text into overlapping chunks by approximate token count.

    Rule of thumb: 1 token ~ 4 characters for English text.
    """
    words = text.split()
    tokens_per_word = 1.3  # average
    words_per_chunk = int(chunk_size / tokens_per_word)
    overlap_words = int(chunk_overlap / tokens_per_word)

    chunks = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap_words

    return chunks


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Chunk]:
    """Chunk all documents with metadata preservation."""
    all_chunks = []

    for doc in documents:
        text_chunks = chunk_by_tokens(doc.content, chunk_size, chunk_overlap)

        for i, text in enumerate(text_chunks):
            chunk = Chunk(
                content=text,
                metadata={
                    **doc.metadata,
                    "chunk_index": i,
                    "chunk_count": len(text_chunks),
                },
                chunk_index=i,
            )
            all_chunks.append(chunk)

    print(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
    return all_chunks
```

> **Companion code:** See `module-9/solution/src/chunker.py` for a sentence-boundary-aware chunker that splits on `.!?` boundaries with overlap.

**Chunking strategies:**

| Strategy | When to Use |
|----------|------------|
| Fixed-size token chunks | Simple, works for most cases |
| Sentence-based | Better for Q&A use cases |
| Paragraph-based (split on `\n\n`) | Good for well-structured documents |
| Semantic chunking | Best quality, slowest (uses embedding model to find breakpoints) |

> **Pro Tip**
> The overlap between chunks is critical -- it prevents information from being split across chunk boundaries. 300-500 tokens per chunk with 50-100 token overlap is the sweet spot for most use cases.

### Step 3: Embed and Store

```python
# rag/indexer.py
import openai
import psycopg2
import json


class RAGIndexer:
    def __init__(self, openai_api_key: str, db_connection_string: str):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.conn = psycopg2.connect(db_connection_string)
        self._setup_table()

    def _setup_table(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                ON rag_chunks USING hnsw (embedding vector_cosine_ops)
            """)
            self.conn.commit()

    def index_chunks(self, chunks: list[Chunk]) -> int:
        """Embed and store chunks. Returns count indexed."""
        batch_size = 100
        total = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.content for c in batch]

            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]

            with self.conn.cursor() as cur:
                for chunk, embedding in zip(batch, embeddings):
                    cur.execute(
                        "INSERT INTO rag_chunks (content, metadata, embedding) VALUES (%s, %s, %s)",
                        (chunk.content, json.dumps(chunk.metadata), str(embedding)),
                    )
            self.conn.commit()
            total += len(batch)

        return total
```

> **Companion code:** See `module-9/solution/src/indexer.py` for the sentence-transformers version that uses the local `all-MiniLM-L6-v2` model and indexes documents from files on disk.

### Step 4: Retrieval

```python
# rag/retriever.py
import openai
import psycopg2
import os


class RAGRetriever:
    def __init__(self, openai_api_key: str, db_connection_string: str):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.conn = psycopg2.connect(db_connection_string)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve the most relevant chunks for a query."""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=[query],
        )
        query_embedding = response.data[0].embedding

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM rag_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (str(query_embedding), str(query_embedding), top_k))

            return [
                {
                    "content": row[0],
                    "metadata": row[1],
                    "similarity": round(row[2], 4),
                }
                for row in cur.fetchall()
            ]

    def query_with_context(self, question: str, top_k: int = 5) -> str:
        """Full RAG: retrieve context, then ask the LLM."""
        chunks = self.retrieve(question, top_k=top_k)

        context = "\n\n---\n\n".join([
            f"[Source: {c['metadata'].get('source', 'unknown')}, "
            f"Similarity: {c['similarity']}]\n{c['content']}"
            for c in chunks
        ])

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Answer the user's question "
                        "based ONLY on the provided context. If the context doesn't "
                        "contain enough information, say so. Cite your sources."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
            temperature=0,
        )

        return response.choices[0].message.content


# Usage
retriever = RAGRetriever(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    db_connection_string=os.environ["DATABASE_URL"],
)
answer = retriever.query_with_context("What is our return policy for electronics?")
print(answer)
```

> **Companion code:** See `module-9/solution/src/retriever.py` for the sentence-transformers version that builds augmented prompts without calling the LLM (returning the prompt string for you to send to any LLM of your choice).

> **Common Mistake**
> - Chunks too large (lose specificity) or too small (lose context). 300-500 tokens is the sweet spot.
> - No overlap between chunks -- you'll miss information at boundaries.
> - Not including metadata. Without source/page info, you can't tell users WHERE the answer came from.
> - Embedding the query with a different model than the documents. Must use the same model for both.

### Checkpoint

1. What are the two phases of RAG and who typically builds each?
2. Why is overlap between chunks important?
3. What system prompt instruction ensures the LLM only answers from the provided context?

---

## 9.6 LLM Data Preparation -- Cleaning, Chunking, Metadata

> **TL;DR:** Real-world documents are messy -- PDFs with headers/footers, HTML with navigation menus, broken formatting. Clean text before embedding by removing artifacts, normalizing whitespace, and stripping boilerplate. Enrich metadata for filtering (content type, source, language). Good metadata enables filtered retrieval, which dramatically improves search quality.

The RAG pipeline works great with clean text files. Real-world data is messy. If you feed garbage into your embeddings, you get garbage search results.

### Cleaning Techniques

```python
# rag/cleaner.py
import re


def clean_text(text: str) -> str:
    """Clean text for embedding. Order matters."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove common PDF artifacts
    text = re.sub(r'Page \d+ of \d+', '', text)
    text = re.sub(r'(?i)confidential|draft|internal use only', '', text)

    # Remove URLs (usually not useful for semantic meaning)
    text = re.sub(r'https?://\S+', '', text)

    # Remove email addresses
    text = re.sub(r'\S+@\S+\.\S+', '', text)

    # Normalize unicode
    text = text.encode('ascii', 'ignore').decode('ascii')

    # Remove very short lines (likely headers/footers)
    lines = text.split('\n')
    lines = [line for line in lines if len(line.strip()) > 20]
    text = '\n'.join(lines)

    return text.strip()


def clean_html(html: str) -> str:
    """Extract meaningful text from HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')

    # Remove non-content elements
    for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                     'aside', 'form', 'iframe']):
        tag.decompose()

    text = soup.get_text(separator='\n')
    return clean_text(text)


def enrich_metadata(content: str, source_metadata: dict) -> dict:
    """Add computed metadata useful for retrieval filtering."""
    metadata = {**source_metadata}

    # Approximate token count
    metadata['token_count'] = len(content.split()) * 1.3

    # Language detection (simple heuristic)
    common_english = {'the', 'is', 'at', 'which', 'on', 'a', 'an'}
    words = set(content.lower().split()[:100])
    metadata['likely_english'] = len(words & common_english) > 3

    # Content type heuristic
    if any(kw in content.lower() for kw in ['def ', 'class ', 'import ', 'function']):
        metadata['content_type'] = 'code'
    elif any(kw in content.lower() for kw in ['table', 'figure', 'chart']):
        metadata['content_type'] = 'structured'
    else:
        metadata['content_type'] = 'prose'

    return metadata
```

> **Companion code:** See `module-9/solution/src/cleaner.py` for additional utilities including `clean_markdown()` which strips markdown formatting while preserving the underlying text content.

### Metadata-Filtered Retrieval

Good metadata enables filtering, which dramatically improves retrieval quality:

```sql
-- Instead of searching ALL chunks, filter first
SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity
FROM rag_chunks
WHERE metadata->>'content_type' = 'prose'
  AND metadata->>'department' = 'customer_service'
ORDER BY embedding <=> %s::vector
LIMIT 5;
```

> **Common Mistake**
> - Over-cleaning. Don't remove formatting that carries meaning (bullet points, numbered lists).
> - Not deduplicating. Duplicate content produces duplicate chunks and skewed search results.
> - Ignoring tables. Tables in PDFs are hard to parse but often contain the most valuable information.

### Checkpoint

1. Why should you remove URLs and email addresses before embedding?
2. How does metadata filtering improve RAG retrieval quality?
3. What's the risk of over-cleaning document text?

---

## 9.7 Building an End-to-End AI Data Pipeline

> **TL;DR:** All the AI data components -- embeddings, vector search, RAG, feature stores -- connect in a production system orchestrated by Airflow. The pipeline ingests new documents, cleans/chunks them, generates embeddings, indexes them in pgvector, computes ML features, and runs quality checks.

### Pipeline Architecture

The Airflow DAG has two parallel branches:
- **Branch 1:** Ingest Docs -> Clean & Chunk -> Embed & Index
- **Branch 2:** Feature Computation -> Materialize to Store

Both branches converge at Quality Checks. Below the DAG: Postgres + pgvector serves both a FastAPI API (/search, /features, /ask) and direct analytics queries.

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ai", "embeddings", "rag"],
)
def ai_data_pipeline():

    @task()
    def ingest_new_documents():
        """Check S3 for new documents, download them."""
        pass

    @task()
    def clean_and_chunk(documents):
        """Clean documents and split into chunks."""
        pass

    @task()
    def generate_embeddings(chunks):
        """Generate embeddings for new chunks."""
        pass

    @task()
    def index_in_vector_db(embeddings):
        """Store embeddings in pgvector."""
        pass

    @task()
    def compute_features():
        """Compute ML features from latest data."""
        pass

    @task()
    def run_quality_checks():
        """Validate embedding quality and feature freshness."""
        pass

    docs = ingest_new_documents()
    chunks = clean_and_chunk(docs)
    embeddings = generate_embeddings(chunks)
    indexed = index_in_vector_db(embeddings)
    features = compute_features()

    [indexed, features] >> run_quality_checks()

ai_data_pipeline()
```

### Production Patterns: Batch vs Real-Time Embedding Updates

In production, you need to decide how to handle updates to your document corpus and product catalog:

**Batch updates (most common, simplest):**
- Run the embedding pipeline on a schedule (daily, hourly)
- New documents accumulate, then get processed in bulk
- Good for: product catalogs, documentation, knowledge bases
- Use Airflow or similar orchestrator

**Real-time updates (when freshness matters):**
- Trigger embedding generation when a document is created/updated
- Use a message queue (Kafka, SQS) to decouple ingestion from embedding
- Good for: support tickets, live chat logs, breaking news
- Higher operational complexity

**Handling document updates:**
- Track document versions with a hash or `updated_at` timestamp
- When a document changes, re-chunk and re-embed only that document
- Delete old chunks for that document before inserting new ones
- The companion code's `get_products_without_embeddings()` method shows this incremental pattern

**Embedding model versioning:**
- When you switch embedding models, ALL existing embeddings become incompatible
- You cannot compare embeddings from different models -- the vector spaces are different
- Strategy: create a new table/column, backfill all embeddings with the new model, then swap
- Store the model name and version in metadata so you can track what generated each embedding

### The Search and Retrieval API

```python
# src/api.py
from fastapi import FastAPI, Query
from pydantic import BaseModel

app = FastAPI(title="RAG Search API")


class SearchResult(BaseModel):
    content: str
    source: str
    similarity: float


class RAGResponse(BaseModel):
    answer: str
    sources: list[SearchResult]


@app.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
):
    """Semantic search over indexed documents."""
    # Use your retriever here
    pass


@app.get("/ask", response_model=RAGResponse)
async def ask(
    question: str = Query(..., description="Question to answer"),
):
    """RAG: retrieve context and generate an answer."""
    # Use your retriever.query_with_context() here
    pass


@app.get("/health")
async def health():
    return {"status": "healthy", "indexed_chunks": 0}  # TODO: actual count
```

> **Companion code:** See `module-9/solution/src/api.py` for the complete FastAPI application with `/search`, `/similar/{product_id}`, `/ask`, and `/health` endpoints, including lazy initialization of the search and retriever classes.

---

## 9.8 Module 9 Project -- RAG-Ready Data Pipeline

> **TL;DR:** Build a complete RAG pipeline: ingest documents from a local directory, clean and chunk them, generate embeddings, store in pgvector, and serve a retrieval/search API via FastAPI. Everything runs in Docker Compose.

### Overview

Build a RAG-ready data pipeline that:

1. Ingests documents from a local directory (simulating S3)
2. Cleans and chunks them
3. Generates embeddings (OpenAI or sentence-transformers)
4. Stores in Postgres + pgvector
5. Serves a retrieval/search API via FastAPI
6. Orchestrated by Airflow

### Project Structure

```
module-9-project/
|-- dags/
|   \-- rag_pipeline.py
|-- src/
|   |-- __init__.py
|   |-- ingest.py
|   |-- cleaner.py
|   |-- chunker.py
|   |-- embedder.py
|   |-- indexer.py
|   |-- retriever.py
|   \-- api.py
|-- data/
|   \-- documents/
|           |-- product-catalog.md
|           |-- return-policy.pdf
|           \-- faq.txt
|-- tests/
|   |-- test_chunker.py
|   |-- test_cleaner.py
|   \-- test_retriever.py
|-- docker-compose.yml
|-- Dockerfile
|-- pyproject.toml
\-- README.md
```

### Step 1: Prepare Sample Documents

Create 3-5 sample documents in `data/documents/`. Use at least 2 different formats (txt, md, pdf).

> **Companion code:** See `module-9/starter/data/documents/` for example documents including `faq.txt` (ShopFast FAQ with 15 Q&A pairs) and `product-catalog.md` (product listings across multiple categories).

### Step 2: Build the Pipeline Components

Use the code from Sections 9.3-9.6 as your starting point.

### Step 3: Build the API

See the FastAPI starter above, or use the companion code in `module-9/solution/src/api.py` as a reference.

### Step 4: Docker Compose

```yaml
version: "3.8"

services:
  api:
    build: .
    command: uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/ragdb
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./data:/app/data

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ragdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

> **Companion code:** See `module-9/starter/docker-compose.yml` for a minimal setup that maps port 5434 on the host to 5432 in the container and auto-runs `sql/init.sql` on first start.

### Step 5: Write Tests

```python
# tests/test_chunker.py
from src.chunker import chunk_by_tokens

def test_chunk_size():
    text = " ".join(["word"] * 1000)
    chunks = chunk_by_tokens(text, chunk_size=100, chunk_overlap=10)
    for chunk in chunks:
        word_count = len(chunk.split())
        assert word_count <= 120  # Allow some variance

def test_chunk_overlap():
    text = " ".join([f"word{i}" for i in range(200)])
    chunks = chunk_by_tokens(text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 1
```

> **Companion code:** See `module-9/solution/tests/test_chunker.py` and `module-9/solution/tests/test_cleaner.py` for additional test examples including metadata preservation tests and HTML/markdown cleaning tests.

### Try It Yourself

```bash
# Start the stack
docker-compose up -d

# Index documents
python -m src.indexer

# Test the API
curl "http://localhost:8000/search?q=return+policy&top_k=3"
curl "http://localhost:8000/ask?question=What+is+the+return+policy+for+electronics"
```

**Expected output:**

```
# /search returns top 3 matching chunks with similarity scores
# /ask returns an AI-generated answer with source citations
```

### Completion Checklist

- [ ] Document ingestion handles at least 2 file formats
- [ ] Text cleaning removes common artifacts
- [ ] Chunking uses overlap and preserves metadata
- [ ] Embeddings generated and stored in pgvector
- [ ] HNSW or IVFFlat index created on embedding column
- [ ] `/search` endpoint returns ranked results with similarity scores
- [ ] `/ask` endpoint returns RAG-generated answers with source citations
- [ ] Docker Compose starts full stack with one command
- [ ] At least 3 unit tests
- [ ] README with setup instructions and example queries

### Bonus Challenges

- Add a `/index` endpoint that accepts new documents via upload
- Implement metadata filtering (filter by source, content type)
- Add a simple web UI with Streamlit or Gradio
- Use sentence-transformers instead of OpenAI (no API key needed)
- Add an Airflow DAG that re-indexes documents on a schedule

---

## The DE's Role in ML/AI Teams

At your job, the lines between data engineering and ML engineering are blurring. But here's how the responsibilities typically break down:

**What the ML/AI engineer does:**
- Chooses the model architecture
- Trains and fine-tunes models
- Evaluates model performance
- Designs the prompt templates

**What you (the data engineer) do:**
- Builds the data pipelines that feed the models
- Manages the vector database and embedding infrastructure
- Handles document ingestion, cleaning, and chunking
- Builds and maintains the feature store
- Sets up the retrieval API
- Monitors data quality and pipeline health
- Handles scale -- batch processing, rate limiting, incremental updates

The ML engineer might prototype with 100 documents loaded into ChromaDB in a Jupyter notebook. You're the one who makes it work with 10 million documents in production, with automatic updates, monitoring, and a 99.9% uptime API.

That's the value you bring. The AI is only as good as the data infrastructure behind it.

---

## What's Next

Everything you've learned across 9 modules comes together in Module 10: the Capstone Project. You'll build a complete, production-grade Real-Time E-Commerce Analytics Platform with batch and streaming pipelines, data quality checks, and an AI component powered by embeddings and pgvector. This is the project you put on your resume and walk through in interviews.

---

*End of Module 9*
