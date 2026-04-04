"""
Chapter 11: Snowpark ML Pipeline Example
=========================================
Snowflake Master Course
Demonstrates a complete ML pipeline using Snowflake ML:
  - Load data from Snowflake table
  - Feature engineering with Snowpark
  - Train/test split
  - StandardScaler + OneHotEncoder preprocessing
  - RandomForestClassifier training
  - Model evaluation
  - Model Registry: log, load, and score
"""

import os
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, when, lit, sf_round

# Snowflake ML imports
from snowflake.ml.modeling.preprocessing import StandardScaler, OneHotEncoder
from snowflake.ml.modeling.pipeline import Pipeline
from snowflake.ml.modeling.ensemble import RandomForestClassifier
from snowflake.ml.modeling.model_selection import train_test_split
from snowflake.ml.modeling.metrics import accuracy_score, confusion_matrix
from snowflake.ml.registry import Registry


# ---------------------------------------------------------------------------
# Helper: build session from environment variables
# ---------------------------------------------------------------------------
def get_session() -> Session:
    return Session.builder.configs({
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "password":  os.environ["SNOWFLAKE_PASSWORD"],
        "role":      os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database":  os.environ.get("SNOWFLAKE_DATABASE", "ANALYTICS"),
        "schema":    os.environ.get("SNOWFLAKE_SCHEMA", "ML_FEATURES"),
    }).create()


# ===========================================================================
# Step 1 – Load training data from Snowflake
# ===========================================================================
def load_training_data(session: Session):
    """
    Expected table schema for CUSTOMER_CHURN_FEATURES:
      CUSTOMER_ID       VARCHAR
      AGE               NUMBER
      TOTAL_SPEND       FLOAT
      NUM_ORDERS        INTEGER
      AVG_ORDER_VALUE   FLOAT
      DAYS_SINCE_LAST   INTEGER
      SEGMENT           VARCHAR   (Bronze, Silver, Gold, Platinum)
      COUNTRY_CODE      VARCHAR
      IS_CHURNED        INTEGER   (target: 0 or 1)
    """
    print("[Step 1] Loading training data...")
    df = session.table("ANALYTICS.ML_FEATURES.CUSTOMER_CHURN_FEATURES")
    print(f"  Total rows: {df.count()}")
    df.show(5)
    return df


# ===========================================================================
# Step 2 – Feature engineering
# ===========================================================================
def engineer_features(df):
    """
    Derive additional features from raw columns before model training.
    """
    print("[Step 2] Engineering features...")

    df_features = (
        df
        # Bin total spend into buckets
        .with_column(
            "SPEND_BUCKET",
            when(col("TOTAL_SPEND") < 500,   lit("LOW"))
            .when(col("TOTAL_SPEND") < 2000,  lit("MEDIUM"))
            .when(col("TOTAL_SPEND") < 5000,  lit("HIGH"))
            .otherwise(lit("VIP"))
        )
        # Ratio feature: avg order value relative to total spend
        .with_column(
            "ORDER_VALUE_RATIO",
            sf_round(col("AVG_ORDER_VALUE") / (col("TOTAL_SPEND") + lit(1.0)), 4)
        )
        # Flag for recently inactive customers
        .with_column(
            "IS_INACTIVE_90D",
            when(col("DAYS_SINCE_LAST") > 90, lit(1)).otherwise(lit(0))
        )
        # Log-transform skewed spend column (use Snowpark SQL expression)
        .with_column(
            "LOG_TOTAL_SPEND",
            sf_round(col("TOTAL_SPEND").cast("float").log(), 4)
        )
        # Drop rows where target is null
        .filter(col("IS_CHURNED").is_not_null())
    )

    print(f"  Rows after feature engineering: {df_features.count()}")
    df_features.select(
        "CUSTOMER_ID", "SPEND_BUCKET", "ORDER_VALUE_RATIO",
        "IS_INACTIVE_90D", "LOG_TOTAL_SPEND", "IS_CHURNED"
    ).show(5)
    return df_features


# ===========================================================================
# Step 3 – Train / Test split
# ===========================================================================
def split_data(df):
    """80/20 stratified split using Snowflake ML train_test_split."""
    print("[Step 3] Splitting data 80/20...")
    df_train, df_test = train_test_split(
        df,
        test_size=0.20,
        random_state=42,
    )
    print(f"  Train rows: {df_train.count()}  |  Test rows: {df_test.count()}")
    return df_train, df_test


# ===========================================================================
# Step 4 – Build preprocessing + model pipeline
# ===========================================================================
def build_pipeline():
    """
    Define numeric features, categorical features, and the target label.
    Assemble a Pipeline with:
      1. StandardScaler   (numeric columns)
      2. OneHotEncoder    (categorical columns)
      3. RandomForestClassifier
    """
    print("[Step 4] Building ML pipeline...")

    NUMERIC_COLS = [
        "AGE", "TOTAL_SPEND", "NUM_ORDERS",
        "AVG_ORDER_VALUE", "DAYS_SINCE_LAST",
        "ORDER_VALUE_RATIO", "LOG_TOTAL_SPEND",
    ]
    CATEGORICAL_COLS = ["SEGMENT", "COUNTRY_CODE", "SPEND_BUCKET"]
    TARGET_COL       = "IS_CHURNED"

    # Each transformer specifies its own input/output columns
    scaler = StandardScaler(
        input_cols=NUMERIC_COLS,
        output_cols=[f"{c}_SCALED" for c in NUMERIC_COLS],
    )

    encoder = OneHotEncoder(
        input_cols=CATEGORICAL_COLS,
        output_cols=[f"{c}_OHE" for c in CATEGORICAL_COLS],
        drop_input_cols=True,
    )

    rf = RandomForestClassifier(
        input_cols=[f"{c}_SCALED" for c in NUMERIC_COLS]
                   + [f"{c}_OHE" for c in CATEGORICAL_COLS],
        label_cols=[TARGET_COL],
        output_cols=["PREDICTED_CHURN"],
        n_estimators=200,
        max_depth=8,
        random_state=42,
    )

    pipeline = Pipeline(steps=[("scaler", scaler), ("encoder", encoder), ("rf", rf)])
    return pipeline, TARGET_COL


# ===========================================================================
# Step 5 – Train the model
# ===========================================================================
def train_model(pipeline, df_train):
    print("[Step 5] Training RandomForest pipeline...")
    pipeline.fit(df_train)
    print("  Training complete.")
    return pipeline


# ===========================================================================
# Step 6 – Evaluate the model
# ===========================================================================
def evaluate_model(pipeline, df_test, target_col: str):
    print("[Step 6] Evaluating model on test set...")

    df_predictions = pipeline.predict(df_test)

    acc = accuracy_score(
        df=df_predictions,
        y_true_col_names=[target_col],
        y_pred_col_names=["PREDICTED_CHURN"],
    )
    print(f"  Accuracy: {acc:.4f}")

    cm = confusion_matrix(
        df=df_predictions,
        y_true_col_names=[target_col],
        y_pred_col_names=["PREDICTED_CHURN"],
    )
    print(f"  Confusion matrix:\n{cm}")

    # Feature importances (available on the RF step)
    rf_step = pipeline.named_steps["rf"]
    importances = rf_step.to_sklearn().feature_importances_
    feature_names = rf_step.input_cols
    importance_pairs = sorted(
        zip(feature_names, importances), key=lambda x: x[1], reverse=True
    )
    print("  Top 5 feature importances:")
    for feat, imp in importance_pairs[:5]:
        print(f"    {feat}: {imp:.4f}")

    return df_predictions, acc


# ===========================================================================
# Step 7 – Register model in Snowflake Model Registry
# ===========================================================================
def register_model(session: Session, pipeline, acc: float, version: str = "V1"):
    print(f"[Step 7] Registering model in Snowflake Model Registry (version={version})...")

    registry = Registry(
        session=session,
        database_name="ANALYTICS",
        schema_name="ML_REGISTRY",
    )

    model_ref = registry.log_model(
        model=pipeline,
        model_name="CUSTOMER_CHURN_CLASSIFIER",
        version_name=version,
        comment=f"RandomForest churn classifier | accuracy={acc:.4f}",
        metrics={"accuracy": acc},
        conda_dependencies=["scikit-learn"],
    )

    print(f"  Model registered: {model_ref.fully_qualified_model_name}")
    return model_ref


# ===========================================================================
# Step 8 – Load model from registry and score new data
# ===========================================================================
def score_new_data(session: Session, version: str = "V1"):
    print("[Step 8] Loading model from registry and scoring new customers...")

    registry = Registry(
        session=session,
        database_name="ANALYTICS",
        schema_name="ML_REGISTRY",
    )

    # Load the registered model
    model_ref = registry.get_model("CUSTOMER_CHURN_CLASSIFIER").version(version)

    # Load unseen data (e.g., prospects not in the training set)
    df_new = session.table("ANALYTICS.ML_FEATURES.NEW_CUSTOMERS_TO_SCORE")
    print(f"  Rows to score: {df_new.count()}")

    # Score
    df_scored = model_ref.run(df_new, function_name="predict")
    df_scored.select("CUSTOMER_ID", "PREDICTED_CHURN").show(10)

    # Persist scored results
    df_scored.write.mode("overwrite").save_as_table(
        "ANALYTICS.ML_FEATURES.CHURN_PREDICTIONS"
    )
    print("  Scored results written to ANALYTICS.ML_FEATURES.CHURN_PREDICTIONS")
    return df_scored


# ===========================================================================
# MAIN – Orchestrate full pipeline
# ===========================================================================
if __name__ == "__main__":
    session = get_session()

    try:
        # Load and prepare data
        df_raw      = load_training_data(session)
        df_features = engineer_features(df_raw)
        df_train, df_test = split_data(df_features)

        # Build, train, evaluate
        pipeline, target_col = build_pipeline()
        trained_pipeline     = train_model(pipeline, df_train)
        df_predictions, acc  = evaluate_model(trained_pipeline, df_test, target_col)

        # Register and score
        model_ref = register_model(session, trained_pipeline, acc, version="V1")
        score_new_data(session, version="V1")

        print("\n[COMPLETE] ML pipeline finished successfully.")

    except Exception as exc:
        print(f"[ERROR] Pipeline failed: {exc}")
        raise

    finally:
        session.close()
