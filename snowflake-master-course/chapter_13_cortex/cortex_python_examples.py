"""
Chapter 13: Snowflake Cortex – Python Examples
===============================================
Snowflake Master Course
Demonstrates:
  - Cortex LLM functions via Snowpark SQL
  - Cortex Search Python client
  - Document AI invocation
  - Batch processing customer reviews
  - Simple RAG pipeline with Cortex Search + COMPLETE
"""

import os
import json
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, lit, udf
from snowflake.snowpark.types import StringType
import pandas as pd

# Cortex Search Python client (available in snowflake-ml-python >= 1.5)
from snowflake.core import Root


# ---------------------------------------------------------------------------
# Session builder helper
# ---------------------------------------------------------------------------
def get_session() -> Session:
    return Session.builder.configs({
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "password":  os.environ["SNOWFLAKE_PASSWORD"],
        "role":      os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database":  os.environ.get("SNOWFLAKE_DATABASE", "ANALYTICS"),
        "schema":    os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }).create()


# ===========================================================================
# Example 1 – Cortex LLM functions via Snowpark SQL
# ===========================================================================
def example_1_cortex_via_sql(session: Session) -> None:
    """
    Call Cortex functions directly through session.sql().
    This is the simplest integration method – no extra SDK needed.
    """
    print("\n--- Example 1: Cortex LLM via Snowpark SQL ---")

    # Simple COMPLETE call
    result = session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?) AS answer",
        params=["What is a Snowflake micro-partition in one sentence?"]
    ).collect()
    print("COMPLETE answer:", result[0]["ANSWER"])

    # SENTIMENT on a literal
    reviews = [
        "The product exceeded all my expectations – absolutely love it!",
        "Shipping took 3 weeks and the item arrived damaged. Very disappointed.",
        "Decent product, nothing special but it works fine.",
    ]
    for review in reviews:
        row = session.sql(
            "SELECT SNOWFLAKE.CORTEX.SENTIMENT(?) AS score",
            params=[review]
        ).collect()[0]
        print(f"  Score: {row['SCORE']:+.3f} | {review[:60]}")

    # TRANSLATE from French to English
    french_text = "La qualité du produit est excellente mais la livraison était lente."
    row = session.sql(
        "SELECT SNOWFLAKE.CORTEX.TRANSLATE(?, 'fr', 'en') AS translation",
        params=[french_text]
    ).collect()[0]
    print(f"  Translated: {row['TRANSLATION']}")


# ===========================================================================
# Example 2 – Cortex Search Python client
# ===========================================================================
def example_2_cortex_search_client(session: Session) -> None:
    """
    Use the Snowflake Core Root object to call Cortex Search services
    programmatically from Python.
    """
    print("\n--- Example 2: Cortex Search Python client ---")

    root = Root(session)

    # Access the search service created in cortex_exercises.sql
    search_service = (
        root
        .databases["ANALYTICS"]
        .schemas["PUBLIC"]
        .cortex_search_services["PRODUCT_SEARCH"]
    )

    # Perform a semantic search query
    response = search_service.search(
        query="comfortable running shoes for long distance",
        columns=["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PRICE"],
        limit=5,
    )

    print("Search results:")
    for item in response.results:
        print(f"  [{item['CATEGORY']}] {item['PRODUCT_NAME']} – ${item['PRICE']}")


# ===========================================================================
# Example 3 – Document AI invocation
# ===========================================================================
def example_3_document_ai(session: Session) -> None:
    """
    Use Snowflake Document AI to extract structured data from PDF files
    stored in a stage.

    Prerequisite: Create a Document AI model in Snowsight first, then use
    the generated function name below.
    """
    print("\n--- Example 3: Document AI ---")

    # Document AI generates a SQL function you call like any UDF.
    # Format: <DATABASE>.<SCHEMA>.<MODEL_NAME>!PREDICT(...)
    # The stage must contain PDF or image files.

    doc_ai_sql = """
        SELECT
            RELATIVE_PATH,
            ANALYTICS.PUBLIC.INVOICE_EXTRACTOR!PREDICT(
                GET_PRESIGNED_URL('@ANALYTICS.PUBLIC.INVOICES_STAGE', RELATIVE_PATH),
                1  -- model version
            ) AS extraction_result
        FROM DIRECTORY('@ANALYTICS.PUBLIC.INVOICES_STAGE')
        WHERE RELATIVE_PATH LIKE '%.pdf'
        LIMIT 5
    """
    results = session.sql(doc_ai_sql).to_pandas()

    for _, row in results.iterrows():
        extraction = json.loads(row["EXTRACTION_RESULT"])
        print(f"  File: {row['RELATIVE_PATH']}")
        print(f"    Vendor:       {extraction.get('vendor_name', {}).get('value', 'N/A')}")
        print(f"    Invoice #:    {extraction.get('invoice_number', {}).get('value', 'N/A')}")
        print(f"    Total:        {extraction.get('total_amount', {}).get('value', 'N/A')}")
        print(f"    Due Date:     {extraction.get('due_date', {}).get('value', 'N/A')}")


# ===========================================================================
# Example 4 – Batch processing reviews with Cortex
# ===========================================================================
def example_4_batch_review_processing(session: Session) -> pd.DataFrame:
    """
    Process all customer reviews in bulk:
      1. Compute sentiment score
      2. Classify review topic
      3. Generate a short summary for long reviews
      4. Write enriched results back to Snowflake
    """
    print("\n--- Example 4: Batch review processing ---")

    df_reviews = session.table("ANALYTICS.PUBLIC.CUSTOMER_REVIEWS").filter(
        col("REVIEW_DATE") >= lit("2024-01-01")
    )
    print(f"  Processing {df_reviews.count()} reviews...")

    # Snowflake processes Cortex functions server-side – no data leaves Snowflake
    enrichment_sql = """
        SELECT
            REVIEW_ID,
            CUSTOMER_ID,
            PRODUCT_ID,
            REVIEW_DATE,
            REVIEW_TEXT,
            SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT)           AS sentiment_score,
            CASE
                WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) >=  0.3 THEN 'POSITIVE'
                WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) <= -0.3 THEN 'NEGATIVE'
                ELSE 'NEUTRAL'
            END                                                AS sentiment_label,
            SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
                REVIEW_TEXT,
                ['Product Quality','Shipping Speed','Customer Service','Pricing','Other']
            )['label']::STRING                                 AS review_topic,
            CASE WHEN LENGTH(REVIEW_TEXT) > 300
                 THEN SNOWFLAKE.CORTEX.SUMMARIZE(REVIEW_TEXT)
                 ELSE REVIEW_TEXT
            END                                                AS review_summary
        FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS
        WHERE REVIEW_DATE >= '2024-01-01'
    """
    df_enriched = session.sql(enrichment_sql)

    # Write enriched results to a new table
    df_enriched.write.mode("overwrite").save_as_table(
        "ANALYTICS.PUBLIC.CUSTOMER_REVIEWS_ENRICHED"
    )
    print("  Written to ANALYTICS.PUBLIC.CUSTOMER_REVIEWS_ENRICHED")

    # Return a sample as Pandas for inspection
    return df_enriched.limit(10).to_pandas()


# ===========================================================================
# Example 5 – Simple RAG pipeline with Cortex Search + COMPLETE
# ===========================================================================
def example_5_rag_pipeline(session: Session, user_question: str) -> str:
    """
    Minimal RAG (Retrieval-Augmented Generation) pipeline:
      1. Use Cortex Search to retrieve the top-k relevant product documents
      2. Inject them as context into a COMPLETE call
      3. Return a grounded answer

    Args:
        session: Active Snowpark session
        user_question: Natural language question from the user

    Returns:
        LLM-generated answer grounded in retrieved product data
    """
    print(f"\n--- Example 5: RAG Pipeline ---")
    print(f"  Question: {user_question}")

    # Step 1: Retrieve relevant context via Cortex Search
    root = Root(session)
    search_service = (
        root
        .databases["ANALYTICS"]
        .schemas["PUBLIC"]
        .cortex_search_services["PRODUCT_SEARCH"]
    )

    search_response = search_service.search(
        query=user_question,
        columns=["PRODUCT_NAME", "DESCRIPTION", "CATEGORY", "PRICE"],
        limit=3,
    )

    # Step 2: Format retrieved docs as context
    context_blocks = []
    for i, item in enumerate(search_response.results, start=1):
        context_blocks.append(
            f"Product {i}: {item['PRODUCT_NAME']} (Category: {item['CATEGORY']}, "
            f"Price: ${item['PRICE']})\n{item['DESCRIPTION']}"
        )
    context_text = "\n\n".join(context_blocks)

    # Step 3: Build the augmented prompt
    augmented_prompt = f"""You are a helpful product assistant for an e-commerce store.
Use ONLY the product information below to answer the customer's question.
If the answer is not in the context, say "I don't have that information."

PRODUCT CONTEXT:
{context_text}

CUSTOMER QUESTION:
{user_question}

ANSWER:"""

    # Step 4: Call COMPLETE with the grounded prompt
    row = session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?) AS answer",
        params=[augmented_prompt]
    ).collect()[0]

    answer = row["ANSWER"]
    print(f"  Answer: {answer}")
    return answer


# ===========================================================================
# MAIN
# ===========================================================================
if __name__ == "__main__":
    session = get_session()

    try:
        example_1_cortex_via_sql(session)
        example_2_cortex_search_client(session)
        example_3_document_ai(session)
        sample_df = example_4_batch_review_processing(session)
        print("\nSample enriched reviews:")
        print(sample_df[["REVIEW_ID", "SENTIMENT_LABEL", "REVIEW_TOPIC"]].to_string())

        # RAG pipeline demo
        answer = example_5_rag_pipeline(
            session,
            "What headphones do you carry that are good for working out?"
        )

    finally:
        session.close()
        print("\n[COMPLETE] All Cortex Python examples finished.")
