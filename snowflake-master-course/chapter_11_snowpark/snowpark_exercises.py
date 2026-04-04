"""
Chapter 11: Snowpark for Python - Exercises
============================================
Snowflake Master Course
Demonstrates: Session creation, DataFrame operations, UDFs, UDTFs,
              Stored Procedures, Stage I/O, Window Functions, and more.
"""

import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from typing import Iterator

# ---------------------------------------------------------------------------
# Snowpark imports
# ---------------------------------------------------------------------------
from snowflake.snowpark import Session, Window
from snowflake.snowpark.functions import (
    col,
    lit,
    sum as sf_sum,
    avg as sf_avg,
    count,
    max as sf_max,
    min as sf_min,
    rank,
    dense_rank,
    row_number,
    lag,
    lead,
    ntile,
    when,
    coalesce,
    to_date,
    year,
    month,
    concat,
    upper,
    trim,
    round as sf_round,
    udf,
    udtf,
    sproc,
    pandas_udf,
)
from snowflake.snowpark.types import (
    IntegerType,
    StringType,
    FloatType,
    DoubleType,
    BooleanType,
    DateType,
    TimestampType,
    StructType,
    StructField,
    PandasSeries,
    PandasDataFrame,
)
import pandas as pd


# ===========================================================================
# EXERCISE 1 – Session creation from environment variables
# ===========================================================================
def create_session_from_env() -> Session:
    """
    Build a Snowpark Session using credentials stored in environment variables.
    Required env vars:
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or private key),
        SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA
    """
    connection_params = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "password":  os.environ.get("SNOWFLAKE_PASSWORD", ""),
        "role":      os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database":  os.environ.get("SNOWFLAKE_DATABASE", "ANALYTICS"),
        "schema":    os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }
    session = Session.builder.configs(connection_params).create()
    print(f"[Exercise 1] Connected. Current role: {session.get_current_role()}")
    return session


# ===========================================================================
# EXERCISE 2 – Session context manager (safe resource cleanup)
# ===========================================================================
@contextmanager
def snowpark_session():
    """Context manager that guarantees Session.close() is called."""
    session = create_session_from_env()
    try:
        yield session
    except Exception as exc:
        print(f"[Exercise 2] Session error: {exc}")
        raise
    finally:
        session.close()
        print("[Exercise 2] Session closed.")


# ===========================================================================
# EXERCISE 3 – Basic DataFrame operations: select, filter, alias
# ===========================================================================
def exercise_3_basic_dataframe(session: Session) -> None:
    print("\n--- Exercise 3: Basic DataFrame operations ---")

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    df_filtered = (
        df_orders
        .filter(col("STATUS") == "COMPLETED")
        .filter(col("AMOUNT") > 100)
        .select(
            col("ORDER_ID"),
            col("CUSTOMER_ID"),
            col("ORDER_DATE"),
            col("AMOUNT").alias("order_amount"),
            col("REGION"),
        )
    )

    df_filtered.show(10)
    print(f"Filtered row count: {df_filtered.count()}")


# ===========================================================================
# EXERCISE 4 – Joins: inner, left, and broadcast hint
# ===========================================================================
def exercise_4_joins(session: Session) -> None:
    print("\n--- Exercise 4: Joins ---")

    df_orders    = session.table("ANALYTICS.MARTS.FCT_ORDERS")
    df_customers = session.table("ANALYTICS.MARTS.DIM_CUSTOMERS")
    df_products  = session.table("ANALYTICS.MARTS.DIM_PRODUCTS")

    # Inner join orders ↔ customers
    df_joined = df_orders.join(
        df_customers,
        df_orders["CUSTOMER_ID"] == df_customers["CUSTOMER_ID"],
        join_type="inner",
    ).select(
        df_orders["ORDER_ID"],
        df_customers["FULL_NAME"].alias("customer_name"),
        df_customers["SEGMENT"],
        df_orders["AMOUNT"],
        df_orders["REGION"],
    )

    # Left join to bring in product name (broadcast small table)
    df_full = df_joined.join(
        df_products.hint("broadcast"),
        df_orders["PRODUCT_ID"] == df_products["PRODUCT_ID"],
        join_type="left",
    ).select(
        col("ORDER_ID"),
        col("customer_name"),
        col("SEGMENT"),
        col("AMOUNT"),
        col("REGION"),
        df_products["PRODUCT_NAME"],
    )

    df_full.show(10)


# ===========================================================================
# EXERCISE 5 – groupBy and aggregation
# ===========================================================================
def exercise_5_groupby_agg(session: Session) -> None:
    print("\n--- Exercise 5: groupBy and aggregation ---")

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    df_agg = (
        df_orders
        .group_by(col("REGION"), col("STATUS"))
        .agg(
            sf_sum("AMOUNT").alias("total_revenue"),
            count("ORDER_ID").alias("order_count"),
            sf_avg("AMOUNT").alias("avg_order_value"),
            sf_max("AMOUNT").alias("max_order_value"),
            sf_min("AMOUNT").alias("min_order_value"),
        )
        .sort(col("total_revenue").desc())
    )

    df_agg.show(20)


# ===========================================================================
# EXERCISE 6 – Window functions
# ===========================================================================
def exercise_6_window_functions(session: Session) -> None:
    print("\n--- Exercise 6: Window functions ---")

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    # Partition by REGION, order by ORDER_DATE
    window_spec = Window.partition_by("REGION").order_by(col("ORDER_DATE"))
    window_all  = Window.partition_by("REGION")

    df_windowed = df_orders.select(
        col("ORDER_ID"),
        col("REGION"),
        col("CUSTOMER_ID"),
        col("AMOUNT"),
        col("ORDER_DATE"),
        rank().over(window_spec).alias("rank_in_region"),
        dense_rank().over(window_spec).alias("dense_rank_in_region"),
        row_number().over(window_spec).alias("row_num"),
        lag(col("AMOUNT"), 1).over(window_spec).alias("prev_order_amount"),
        lead(col("AMOUNT"), 1).over(window_spec).alias("next_order_amount"),
        sf_sum("AMOUNT").over(window_all).alias("region_total"),
        ntile(4).over(window_spec).alias("quartile"),
    )

    df_windowed.show(15)


# ===========================================================================
# EXERCISE 7 – Writing DataFrames back to Snowflake
# ===========================================================================
def exercise_7_write_dataframe(session: Session) -> None:
    print("\n--- Exercise 7: Writing DataFrames to Snowflake ---")

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    df_summary = (
        df_orders
        .group_by("REGION")
        .agg(
            sf_sum("AMOUNT").alias("TOTAL_REVENUE"),
            count("ORDER_ID").alias("ORDER_COUNT"),
        )
    )

    # overwrite mode replaces existing data; "append" adds rows
    df_summary.write.mode("overwrite").save_as_table("ANALYTICS.MARTS.REGION_REVENUE_SUMMARY")
    print("[Exercise 7] Written to REGION_REVENUE_SUMMARY successfully.")


# ===========================================================================
# EXERCISE 8 – Scalar UDF (Python logic in Snowflake)
# ===========================================================================
def exercise_8_scalar_udf(session: Session) -> None:
    print("\n--- Exercise 8: Scalar UDF ---")

    @udf(
        name="categorize_order_value",
        input_types=[FloatType()],
        return_type=StringType(),
        replace=True,
        stage_location="@ANALYTICS.PUBLIC.PYTHON_STAGE",
    )
    def categorize_order_value(amount: float) -> str:
        """Classify an order as Small / Medium / Large / Enterprise."""
        if amount is None:
            return "UNKNOWN"
        if amount < 100:
            return "SMALL"
        elif amount < 500:
            return "MEDIUM"
        elif amount < 2000:
            return "LARGE"
        else:
            return "ENTERPRISE"

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")
    df_with_category = df_orders.with_column(
        "ORDER_CATEGORY",
        categorize_order_value(col("AMOUNT")),
    )
    df_with_category.select("ORDER_ID", "AMOUNT", "ORDER_CATEGORY").show(10)


# ===========================================================================
# EXERCISE 9 – Pandas (vectorized) UDF
# ===========================================================================
def exercise_9_pandas_udf(session: Session) -> None:
    print("\n--- Exercise 9: Pandas (vectorized) UDF ---")

    @pandas_udf(
        name="normalize_email",
        input_types=[StringType()],
        return_type=StringType(),
        replace=True,
    )
    def normalize_email(emails: PandasSeries) -> PandasSeries:
        """Lowercase and strip whitespace from email addresses."""
        return emails.str.lower().str.strip()

    df_customers = session.table("ANALYTICS.MARTS.DIM_CUSTOMERS")
    df_normalized = df_customers.with_column(
        "EMAIL_CLEAN",
        normalize_email(col("EMAIL")),
    )
    df_normalized.select("CUSTOMER_ID", "EMAIL", "EMAIL_CLEAN").show(10)


# ===========================================================================
# EXERCISE 10 – UDTF (User-Defined Table Function)
# ===========================================================================
def exercise_10_udtf(session: Session) -> None:
    print("\n--- Exercise 10: UDTF ---")

    class DateRangeGenerator:
        """
        Emit one row per day between start_date and end_date (inclusive).
        Example: date_range('2024-01-01', '2024-01-05') → 5 rows.
        """

        def process(self, start_date: str, end_date: str) -> Iterator[tuple]:
            from datetime import date, timedelta
            import datetime

            start = date.fromisoformat(start_date)
            end   = date.fromisoformat(end_date)
            delta = end - start
            for i in range(delta.days + 1):
                yield (start + timedelta(days=i),)

    date_range_udtf = udtf(
        DateRangeGenerator,
        output_schema=StructType([StructField("calendar_date", DateType())]),
        input_types=[StringType(), StringType()],
        name="date_range_generator",
        replace=True,
    )

    df_dates = session.table_function(
        date_range_udtf("2024-01-01", "2024-01-31")
    )
    df_dates.show(31)


# ===========================================================================
# EXERCISE 11 – Stored procedure registration and call
# ===========================================================================
def exercise_11_stored_procedure(session: Session) -> None:
    print("\n--- Exercise 11: Stored Procedure ---")

    def refresh_revenue_summary(sp_session: Session, target_table: str) -> str:
        """Rebuild the regional revenue summary table."""
        df = (
            sp_session.table("ANALYTICS.MARTS.FCT_ORDERS")
            .group_by("REGION")
            .agg(
                sf_sum("AMOUNT").alias("TOTAL_REVENUE"),
                count("ORDER_ID").alias("ORDER_COUNT"),
            )
        )
        df.write.mode("overwrite").save_as_table(target_table)
        return f"SUCCESS: {target_table} refreshed with {df.count()} regions."

    sp = sproc(
        func=refresh_revenue_summary,
        name="refresh_revenue_summary_sp",
        input_types=[StringType()],
        return_type=StringType(),
        packages=["snowflake-snowpark-python"],
        replace=True,
        stage_location="@ANALYTICS.PUBLIC.PYTHON_STAGE",
    )

    result = sp("ANALYTICS.MARTS.REGION_REVENUE_SUMMARY")
    print(f"[Exercise 11] Stored proc result: {result}")


# ===========================================================================
# EXERCISE 12 – Reading from and writing to a named stage
# ===========================================================================
def exercise_12_stage_io(session: Session) -> None:
    print("\n--- Exercise 12: Stage I/O ---")

    # Upload a local CSV to an internal stage
    local_path  = "/tmp/orders_export.csv"
    stage_path  = "@ANALYTICS.PUBLIC.DATA_STAGE/orders/"

    # Write a small Pandas DataFrame to disk first (simulate local file)
    sample_df = pd.DataFrame({
        "order_id":    [1001, 1002, 1003],
        "amount":      [150.0, 320.5, 75.25],
        "status":      ["COMPLETED", "PENDING", "COMPLETED"],
    })
    sample_df.to_csv(local_path, index=False)

    # PUT the file onto the stage
    put_result = session.file.put(local_path, stage_path, overwrite=True)
    print(f"[Exercise 12] PUT result: {put_result}")

    # Read it back as a Snowpark DataFrame using the CSV reader
    df_from_stage = session.read.option("header", True).option("inferSchema", True).csv(stage_path)
    df_from_stage.show()

    # GET (download) back to local disk
    get_result = session.file.get(stage_path + "orders_export.csv", "/tmp/downloaded_orders/")
    print(f"[Exercise 12] GET result: {get_result}")


# ===========================================================================
# EXERCISE 13 – Error handling patterns
# ===========================================================================
def exercise_13_error_handling(session: Session) -> None:
    print("\n--- Exercise 13: Error handling ---")

    from snowflake.snowpark.exceptions import (
        SnowparkSQLException,
        SnowparkJoinException,
        SnowparkPlanException,
    )

    try:
        # Intentionally reference a non-existent table
        session.table("ANALYTICS.MARTS.NONEXISTENT_TABLE").show()

    except SnowparkSQLException as sql_err:
        print(f"[Exercise 13] SQL error caught: {sql_err.message}")

    except SnowparkPlanException as plan_err:
        print(f"[Exercise 13] Plan error caught: {plan_err}")

    except Exception as generic_err:
        print(f"[Exercise 13] Unexpected error: {generic_err}")

    # Safe column access pattern using coalesce / try
    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")
    df_safe = df_orders.select(
        col("ORDER_ID"),
        coalesce(col("AMOUNT"), lit(0.0)).alias("safe_amount"),
    )
    df_safe.show(5)


# ===========================================================================
# EXERCISE 14 – Conditional expressions with when / otherwise
# ===========================================================================
def exercise_14_when_otherwise(session: Session) -> None:
    print("\n--- Exercise 14: when / otherwise ---")

    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    df_enriched = df_orders.with_column(
        "AMOUNT_BUCKET",
        when(col("AMOUNT") < 50, lit("XS"))
        .when(col("AMOUNT") < 200, lit("S"))
        .when(col("AMOUNT") < 500, lit("M"))
        .when(col("AMOUNT") < 1000, lit("L"))
        .otherwise(lit("XL"))
    ).with_column(
        "IS_HIGH_VALUE",
        when(col("AMOUNT") >= 1000, lit(True)).otherwise(lit(False))
    )

    df_enriched.group_by("AMOUNT_BUCKET").agg(
        count("ORDER_ID").alias("cnt"),
        sf_sum("AMOUNT").alias("bucket_revenue"),
    ).sort("AMOUNT_BUCKET").show()


# ===========================================================================
# EXERCISE 15 – End-to-end pipeline: load → transform → write
# ===========================================================================
def exercise_15_end_to_end_pipeline(session: Session) -> None:
    print("\n--- Exercise 15: End-to-end pipeline ---")

    # Step 1: Load raw tables
    df_orders    = session.table("ANALYTICS.MARTS.FCT_ORDERS")
    df_customers = session.table("ANALYTICS.MARTS.DIM_CUSTOMERS")

    # Step 2: Join and enrich
    df_joined = df_orders.join(
        df_customers,
        df_orders["CUSTOMER_ID"] == df_customers["CUSTOMER_ID"],
    ).select(
        df_orders["ORDER_ID"],
        df_orders["ORDER_DATE"],
        df_orders["AMOUNT"],
        df_orders["STATUS"],
        df_orders["REGION"],
        df_customers["FULL_NAME"].alias("CUSTOMER_NAME"),
        df_customers["SEGMENT"].alias("CUSTOMER_SEGMENT"),
        df_customers["COUNTRY_CODE"],
    )

    # Step 3: Apply window function (running total per customer)
    win = Window.partition_by("CUSTOMER_ID").order_by("ORDER_DATE")
    df_with_running_total = df_joined.with_column(
        "RUNNING_REVENUE",
        sf_sum("AMOUNT").over(win),
    )

    # Step 4: Add derived columns
    df_final = (
        df_with_running_total
        .with_column("ORDER_YEAR",  year(col("ORDER_DATE")))
        .with_column("ORDER_MONTH", month(col("ORDER_DATE")))
        .with_column(
            "SEGMENT_BUCKET",
            when(col("CUSTOMER_SEGMENT") == "PLATINUM", lit(4))
            .when(col("CUSTOMER_SEGMENT") == "GOLD",    lit(3))
            .when(col("CUSTOMER_SEGMENT") == "SILVER",  lit(2))
            .otherwise(lit(1))
        )
    )

    # Step 5: Write to target table
    df_final.write.mode("overwrite").save_as_table(
        "ANALYTICS.MARTS.CUSTOMER_ORDER_ENRICHED"
    )
    print(f"[Exercise 15] Pipeline complete. Rows written: {df_final.count()}")


# ===========================================================================
# MAIN – Run all exercises
# ===========================================================================
if __name__ == "__main__":
    with snowpark_session() as session:
        exercise_3_basic_dataframe(session)
        exercise_4_joins(session)
        exercise_5_groupby_agg(session)
        exercise_6_window_functions(session)
        exercise_7_write_dataframe(session)
        exercise_8_scalar_udf(session)
        exercise_9_pandas_udf(session)
        exercise_10_udtf(session)
        exercise_11_stored_procedure(session)
        exercise_12_stage_io(session)
        exercise_13_error_handling(session)
        exercise_14_when_otherwise(session)
        exercise_15_end_to_end_pipeline(session)
