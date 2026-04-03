# Module 8: ML Platforms & Feature Stores

## Why ML Infrastructure Matters

There's a well-known gap in machine learning: the distance between a model that works in a Jupyter notebook and a model that serves predictions reliably in production. Data scientists often joke that building the model is 10% of the work — the other 90% is getting it deployed, monitored, and maintained.

The core problem is **training-serving skew**: the features your model sees during training are different from what it sees in production. Maybe your training pipeline computes features using Pandas on a CSV dump, but your serving pipeline uses SQL queries against a live database. Subtle differences — timezone handling, null behavior, aggregation windows — cause the model to perform differently in production than it did in your notebook.

ML infrastructure exists to close this gap: ensuring that the same features, computed the same way, are used in both training and serving; that models are versioned and can be rolled back; and that you know when model performance degrades.

> **Key Takeaway:** The value of ML isn't in the model — it's in the system around it. Feature stores, model registries, serving infrastructure, and monitoring are what separate "cool demo" from "business impact."

---

## ML Pipelines

A production ML pipeline is a series of automated steps that turn raw data into deployed predictions:

```
Raw Data → Feature Engineering → Training → Evaluation → Registry → Deployment → Monitoring
                                                                         ↑
                                                                    Retraining ←─── Drift Alert
```

Each step must be reproducible, versioned, and observable. If a model's performance degrades next month, you need to know exactly what data it trained on, what features it used, and what hyperparameters were set.

**MLflow** is the most widely used platform for managing this lifecycle. It tracks experiments, packages models, and provides a registry for versioning:

```python
import mlflow
import mlflow.sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score

# Every experiment is tracked: parameters, metrics, artifacts
mlflow.set_experiment("churn_prediction_v3")

with mlflow.start_run(run_name="gradient_boosting_tuned"):
    # Log the parameters so we can reproduce this exact training run
    params = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.1,
        "min_samples_split": 20,
    }
    mlflow.log_params(params)

    # Train
    model = GradientBoostingClassifier(**params)
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42
    )
    model.fit(X_train, y_train)

    # Evaluate and log metrics
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    mlflow.log_metric("auc_roc", roc_auc_score(y_test, probabilities))
    mlflow.log_metric("precision", precision_score(y_test, predictions))
    mlflow.log_metric("recall", recall_score(y_test, predictions))

    # Save the model to the registry with versioning
    mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        registered_model_name="churn_predictor",
    )
```

After training, you can compare runs in MLflow's UI, promote the best model to "Production" stage, and your serving infrastructure automatically picks up the new version.

---

## Feature Engineering and Feature Stores

### The Problem

A "feature" is an input to an ML model — a numeric or categorical value computed from raw data. Examples: `avg_purchase_amount_30d`, `days_since_last_login`, `num_support_tickets_7d`.

The problem: different teams compute the same features differently. The fraud team calculates `transaction_velocity_1h` one way; the risk team calculates it another way. Both train models that work in notebooks but disagree in production.

A **feature store** is a centralized system that:
- Defines features once, uses them everywhere
- Serves features consistently for both training and inference
- Provides an **online store** (Redis/DynamoDB) for low-latency serving (<10ms)
- Provides an **offline store** (S3/warehouse) for training data generation
- Tracks lineage: which models use which features, computed from which data sources

### Feast: An Open-Source Feature Store

Here's how you define and use features with Feast. The feature definition serves as the single source of truth — both training and serving use this definition:

```python
from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64, String
from datetime import timedelta

# Define the entity (the "who" or "what" features are about)
customer = Entity(
    name="customer_id",
    join_keys=["customer_id"],
    description="Unique customer identifier",
)

# Define the data source
customer_features_source = FileSource(
    path="s3://feature-store/customer_features.parquet",
    timestamp_field="event_timestamp",
)

# Define features with metadata and types
customer_behavior = FeatureView(
    name="customer_behavior",
    entities=[customer],
    ttl=timedelta(days=1),  # Features expire after 1 day
    schema=[
        Field(name="total_purchases_30d", dtype=Int64),
        Field(name="avg_order_value_30d", dtype=Float32),
        Field(name="days_since_last_purchase", dtype=Int64),
        Field(name="support_tickets_7d", dtype=Int64),
        Field(name="preferred_category", dtype=String),
    ],
    source=customer_features_source,
)

# --- Using features for training ---
from feast import FeatureStore

store = FeatureStore(repo_path="./feature_repo")

# Get historical features for training — point-in-time correct
# This ensures no data leakage: for each training example at time T,
# only features available before T are used.
training_data = store.get_historical_features(
    entity_df=training_entities,  # DataFrame with customer_id + timestamp
    features=[
        "customer_behavior:total_purchases_30d",
        "customer_behavior:avg_order_value_30d",
        "customer_behavior:days_since_last_purchase",
    ],
).to_df()

# --- Using features for real-time inference ---
# Same features, same computation, consistent with training
online_features = store.get_online_features(
    features=[
        "customer_behavior:total_purchases_30d",
        "customer_behavior:avg_order_value_30d",
        "customer_behavior:days_since_last_purchase",
    ],
    entity_rows=[{"customer_id": "cust_12345"}],
).to_dict()
```

The critical function here is `get_historical_features` with **point-in-time correctness**. For each training example at time T, it only uses feature values that were available *before* T. Without this, your model trains on future data — a subtle but devastating form of data leakage that makes training metrics look great but production performance terrible.

---

## Model Serving

Once a model is trained and registered, it needs to serve predictions. There are two paradigms:

**Batch inference**: Score a large dataset all at once, store results in a table. Good for recommendations that update daily, risk scores computed overnight, or any prediction that doesn't need to be real-time.

**Real-time inference**: Score individual requests on demand with low latency. Required for fraud detection, search ranking, dynamic pricing — anything that needs a prediction in milliseconds.

Here's a real-time model serving endpoint using FastAPI. It loads the model from MLflow, retrieves features from the feature store, and returns predictions:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow.pyfunc
from feast import FeatureStore

app = FastAPI(title="Churn Prediction API")

# Load the production model from MLflow on startup
model = mlflow.pyfunc.load_model("models:/churn_predictor/Production")
feature_store = FeatureStore(repo_path="./feature_repo")

class PredictionRequest(BaseModel):
    customer_id: str

class PredictionResponse(BaseModel):
    customer_id: str
    churn_probability: float
    risk_level: str  # low, medium, high

@app.post("/predict", response_model=PredictionResponse)
def predict_churn(request: PredictionRequest):
    """Score a customer's churn risk in real-time.

    1. Retrieve features from the online feature store (<5ms)
    2. Run model inference (<10ms)
    3. Return prediction with risk categorization
    """
    # Get features — same features used in training, guaranteed consistent
    features = feature_store.get_online_features(
        features=[
            "customer_behavior:total_purchases_30d",
            "customer_behavior:avg_order_value_30d",
            "customer_behavior:days_since_last_purchase",
            "customer_behavior:support_tickets_7d",
        ],
        entity_rows=[{"customer_id": request.customer_id}],
    ).to_dict()

    if not features.get("total_purchases_30d"):
        raise HTTPException(status_code=404, detail="Customer not found")

    # Model inference
    probability = model.predict([features])[0]

    # Categorize risk
    if probability > 0.7:
        risk_level = "high"
    elif probability > 0.3:
        risk_level = "medium"
    else:
        risk_level = "low"

    return PredictionResponse(
        customer_id=request.customer_id,
        churn_probability=round(probability, 4),
        risk_level=risk_level,
    )
```

### A/B Testing Models

Never deploy a new model to 100% of traffic immediately. Use gradual rollouts:

1. **Shadow mode**: New model runs alongside the old one but doesn't serve results. Compare predictions offline.
2. **Canary deployment**: Route 5% of traffic to the new model. Monitor metrics closely.
3. **Gradual rollout**: Increase traffic to 25%, 50%, 100% over days, monitoring at each step.
4. **Automatic rollback**: If key metrics (prediction latency, error rate, business KPIs) degrade beyond a threshold, automatically revert to the previous model.

---

## ML Monitoring and Observability

A model that works today may not work tomorrow. The world changes — customer behavior shifts, product catalogs evolve, competitors enter the market. **Model drift** means your model's predictions are becoming less accurate over time.

Three types of drift to monitor:

**Data drift**: The distribution of input features has changed. Example: a model trained on US-only customers starts receiving international traffic with different purchasing patterns.

**Concept drift**: The relationship between features and the target has changed. Example: a fraud detection model trained pre-COVID sees a surge in online transactions that look "unusual" but aren't fraudulent.

**Prediction drift**: The distribution of model outputs has shifted. If your churn model suddenly predicts 50% of customers as high-risk (up from 10%), something has changed.

```python
from scipy import stats
import numpy as np

def detect_feature_drift(
    reference: np.ndarray,
    current: np.ndarray,
    threshold: float = 0.05
) -> dict:
    """Detect distribution drift using the Kolmogorov-Smirnov test.

    Compares the current feature distribution against the reference
    (typically the training distribution). A p-value below the threshold
    indicates statistically significant drift.
    """
    statistic, p_value = stats.ks_2samp(reference, current)
    return {
        "drifted": p_value < threshold,
        "p_value": p_value,
        "ks_statistic": statistic,
        "severity": "high" if p_value < 0.001 else
                    "medium" if p_value < 0.01 else
                    "low" if p_value < threshold else "none"
    }

# Check drift for each feature weekly
for feature_name in ["avg_order_value", "days_since_login", "session_count"]:
    result = detect_feature_drift(
        reference=training_data[feature_name].values,
        current=this_week_data[feature_name].values,
    )
    if result["drifted"]:
        alert(f"Drift detected in {feature_name}: {result['severity']}")
```

> **Key Takeaway:** Deploy monitoring *before* deploying the model. Track feature distributions, prediction distributions, and business metrics. Set up alerts so you know when the model degrades before your users or stakeholders notice.

---

## Vector Databases and RAG Systems

The rise of large language models has created a new class of data infrastructure: systems for storing and querying high-dimensional **vector embeddings**.

### What Are Vector Embeddings?

An embedding is a numeric representation of content — text, images, audio — as a list of numbers (typically 384-1536 dimensions). Similar content produces similar vectors, meaning you can find related items by computing vector distance (cosine similarity, Euclidean distance).

### Vector Databases

Traditional databases index by exact values (`WHERE id = 123`). Vector databases index by similarity (`find the 10 most similar vectors to this query vector`). This enables semantic search — finding documents by meaning, not keywords.

**Popular options**: Pinecone (managed, easy to start), Weaviate (open-source, hybrid search), Milvus (open-source, high performance), pgvector (PostgreSQL extension — good for smaller scale).

### Retrieval-Augmented Generation (RAG)

RAG combines a retrieval system with a language model. Instead of asking an LLM to answer from its training data (which may be outdated or wrong), you first retrieve relevant documents from your own data, then include them in the prompt:

```python
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class SimpleRAG:
    """A basic RAG system using FAISS for vector search.

    1. Embed your documents into vectors
    2. Store vectors in a FAISS index for fast similarity search
    3. At query time, find the most relevant documents
    4. Pass them as context to the LLM
    """

    def __init__(self):
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = None
        self.documents = []

    def add_documents(self, docs: list[str]):
        """Embed documents and add them to the vector index."""
        self.documents.extend(docs)
        embeddings = self.encoder.encode(docs)
        dimension = embeddings.shape[1]

        if self.index is None:
            self.index = faiss.IndexFlatIP(dimension)  # Inner product similarity

        # Normalize for cosine similarity
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings.astype('float32'))

    def query(self, question: str, top_k: int = 3) -> list[str]:
        """Find the most relevant documents for a question."""
        query_embedding = self.encoder.encode([question])
        faiss.normalize_L2(query_embedding)

        scores, indices = self.index.search(
            query_embedding.astype('float32'), top_k
        )
        return [self.documents[i] for i in indices[0]]

    def answer(self, question: str, llm_client) -> str:
        """Retrieve relevant context and generate an answer.

        The LLM only uses the retrieved documents as context,
        so it can answer questions about your specific data
        without having seen it during training.
        """
        relevant_docs = self.query(question, top_k=3)
        context = "\n\n".join(relevant_docs)

        prompt = f"""Answer the question based only on the provided context.
If the context doesn't contain enough information, say so.

Context:
{context}

Question: {question}

Answer:"""

        return llm_client.generate(prompt)
```

> **Key Takeaway:** RAG is the practical way to give LLMs access to your organization's data without fine-tuning. The quality of your retrieval (embedding model, chunking strategy, vector index) directly determines the quality of the generated answers.

---

## Case Study: Building a Recommendation System

Let's design a product recommendation system end-to-end — from data collection through serving.

**Requirements**: An e-commerce site with 1M products and 10M users. Generate "you might also like" recommendations on product pages, updated daily, served in <50ms.

**Architecture**:

```
User Events (Kafka) → Feature Pipeline (Spark) → Feature Store (Feast)
                                                       ↓
Training Data → Model Training (MLflow) → Model Registry → Serving API (FastAPI)
                                                                ↓
                                                       Product Page (<50ms)
```

1. **Data Collection**: Every user interaction (view, add-to-cart, purchase, wishlist) flows through Kafka. A Spark job computes daily features: user purchase history, product co-purchase matrix, category affinities, price sensitivity.

2. **Feature Store**: Feast manages two feature views — `user_preferences` (online + offline) and `product_signals` (popularity, average rating, view-to-purchase ratio). The online store (Redis) serves features in <5ms.

3. **Model Training**: Weekly training job using collaborative filtering (matrix factorization) plus content-based features. MLflow tracks experiments. Best model is promoted to Production stage.

4. **Serving**: FastAPI endpoint retrieves user features from the feature store, runs the model, applies business rules (filter out-of-stock items, boost sponsored products), and returns top 20 recommendations.

5. **Monitoring**: Track recommendation click-through rate, add-to-cart rate, and revenue attribution. Alert on drift in prediction distribution or feature values. A/B test new models against the current production model.

The total latency budget: feature lookup (5ms) + model inference (15ms) + business rules (5ms) + network (10ms) = 35ms, well within the 50ms target.

---

## What's Next

Module 9 explores event-driven and distributed systems — the architectural patterns that tie everything together when your system grows from a single application to a fleet of microservices communicating through events.
