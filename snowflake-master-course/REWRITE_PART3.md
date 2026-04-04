# Snowflake Master Course — Part 3: Snowpark, Streamlit, AI & Governance

---

# Chapter 11: Snowpark — Code in the Warehouse

## 11.1 The Problem Snowpark Solves

For most of Snowflake's early history, data engineers and scientists operated under an awkward split-brain workflow. Their data lived in Snowflake, but their processing logic lived somewhere else — on a laptop, on an EC2 instance, in a Databricks cluster, or inside a Jupyter notebook. The standard pattern looked like this: write a SQL query to extract what you need, pull the result set across the network into a Python process, do the actual transformation or analysis using pandas or numpy, then write the results back to Snowflake with another round trip. This worked fine when you were dealing with thousands of rows. It started to break down at millions of rows. And at tens or hundreds of millions of rows, it became genuinely unworkable.

The network transfer problem is more serious than it first appears. Moving 50 gigabytes of raw customer transaction data from Snowflake to your local machine means waiting potentially twenty minutes for the transfer to complete, paying real money in egress costs (cloud providers charge for data leaving their network), and — most critically for any team working with sensitive data — creating a situation where production-grade PII or financial records are sitting on someone's laptop or on a server outside Snowflake's security perimeter. Your Snowflake account might have column-level masking policies, row access policies, and comprehensive audit logging. None of that applies once the data has left the warehouse and landed in a pandas DataFrame on a machine you don't control.

The memory problem is equally serious. Pandas stores its entire dataset in RAM. If your dataset is 60 gigabytes, pandas needs 60 gigabytes of RAM — and usually more, because operations like merge and groupby create temporary copies. An EC2 r5.4xlarge instance with 128 GB of RAM costs roughly $1 per hour and still isn't enough for some analytics workloads. You end up either spending money on beefy servers to handle the data volume, or you process data in chunks and write complex batching code that's brittle and hard to maintain. Neither option is satisfying.

The compute mismatch problem is the least obvious but arguably the most wasteful. Snowflake is a massively parallel processing (MPP) warehouse. When you run a query on a multi-node warehouse, Snowflake distributes the work across dozens or hundreds of virtual CPUs, each processing a different partition of the data simultaneously. When you pull the same data out and process it in pandas on your local machine, you're running the computation on a single machine with 8 or 16 cores. You're paying for Snowflake's MPP infrastructure but doing the actual heavy lifting on your laptop. It's like paying for a factory and then doing all the work by hand in the parking lot.

Snowpark flips this model. Instead of pulling data to where your code runs, Snowpark sends your code to where the data lives. You write Python — familiar, flexible, with access to the full ecosystem of Python libraries — but the code executes inside Snowflake's warehouse infrastructure. The data never moves. The computation happens in the MPP engine. Your results are written back to Snowflake tables or returned to Python without massive data transfers. This is the core value proposition, and it's worth understanding at a deep level before diving into the API.

### The Compilation Model

There is a common misconception about how Snowpark works that's worth addressing directly. People sometimes assume that Snowpark embeds a Python interpreter into every warehouse node, so that when you write Python code, Python is literally executing inside the warehouse. This is not how it works — and understanding why matters for writing effective Snowpark code.

When you write a Snowpark Python DataFrame operation like `.filter(col("REGION") == "US").groupBy("PRODUCT_ID").agg(sf_sum("AMOUNT"))`, Snowpark does not execute this as Python. Instead, it compiles the operation into SQL: `SELECT PRODUCT_ID, SUM(AMOUNT) FROM ... WHERE REGION = 'US' GROUP BY PRODUCT_ID`. That SQL is then sent to Snowflake's query engine for execution. The Python code you write is essentially a type-safe, IDE-friendly way of constructing SQL queries. This is why the Snowpark DataFrame API supports a specific set of operations — only operations that have a SQL equivalent can be compiled and pushed down to the warehouse. You cannot write arbitrary Python control flow inside a DataFrame operation and expect it to execute in Snowflake.

For logic that genuinely requires Python — calling scikit-learn for scoring, invoking a custom algorithm, using Python's regex engine — Snowpark uses User-Defined Functions (UDFs). UDFs do run inside a sandboxed Python interpreter inside the warehouse nodes. The distinction is critical: DataFrame operations compile to SQL (fast, scalable, no Python overhead), while UDFs run Python inside the warehouse (flexible, supports any library, but with Python interpreter overhead). Great Snowpark code maximizes the use of DataFrame operations and uses UDFs only for logic that cannot be expressed as SQL.

---

## 11.2 Session Setup and the Entry Point into Snowpark

In the traditional Python Snowflake Connector, you create a connection object and then call `cursor.execute("SELECT ...")` to run SQL strings. The connection is thin — it's essentially a socket to the database. In Snowpark, the equivalent starting point is the `Session` object, which is substantially richer. The Session is your gateway to the entire Snowpark ecosystem: the DataFrame API, UDF and stored procedure registration, stage file operations, and ML model management. Everything in Snowpark flows through a Session.

Creating a Session requires a configuration dictionary that specifies your account identifier, credentials, role, warehouse, database, and schema. The decision to use environment variables for these values is not arbitrary — it reflects a real security practice that every production Snowpark deployment should follow. If you hardcode credentials as strings in your Python script, those credentials end up committed to your version control system. They appear in git history, get cloned to developer laptops, are exposed in CI/CD pipeline logs, and can be accidentally posted to GitHub. Credential leakage through source code is one of the most common causes of cloud security incidents. Environment variables separate credentials from code, allowing the same script to run in development against a sandbox account, in staging against a test account, and in production against the production account — all without a single line of code changing.

```python
import os
from snowflake.snowpark import Session

def create_session_from_env() -> Session:
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
    print(f"Connected. Current role: {session.get_current_role()}")
    return session
```

Once you have this function, you should almost never call it directly in application code. Instead, wrap your usage in a context manager that guarantees the session is closed regardless of whether an exception occurs:

```python
from contextlib import contextmanager

@contextmanager
def snowpark_session():
    session = create_session_from_env()
    try:
        yield session
    except Exception as exc:
        print(f"Session error: {exc}")
        raise
    finally:
        session.close()
        print("Session closed.")
```

The `Session.builder.configs(connection_params).create()` pattern deserves a note. The `builder` is a fluent interface — `configs()` sets parameters, and `create()` actually opens the connection. Snowflake validates the credentials and the role, warehouse, database, and schema at connection time; if any of these don't exist or you don't have permission to use them, `create()` raises an exception immediately. This fail-fast behavior is useful: your script won't proceed into data operations only to discover it can't access the required objects.

The `session.sql("SELECT ...")` method is an important escape hatch. The Snowpark DataFrame API is expressive and covers the vast majority of SQL operations, but there are cases where writing raw SQL is more natural — complex recursive CTEs, DDL statements like `CREATE TABLE`, stored procedure calls, or Snowflake-specific syntax that the DataFrame API doesn't yet expose. `session.sql()` returns a DataFrame, so you can chain further operations on top of it. Use it freely when it's the right tool, but prefer the DataFrame API when expressing straightforward SELECT/JOIN/GROUP BY logic, because the DataFrame API gives you type checking and compile-time feedback that raw SQL strings don't.

---

## 11.3 DataFrames and Lazy Evaluation

The most important concept in Snowpark — the one that explains most of the behavior you'll encounter and most of the performance characteristics — is lazy evaluation. Understanding this concept thoroughly will save you from hours of confusion and help you write efficient Snowpark code instinctively.

In pandas, every operation is eager. When you write `filtered_df = df[df['region'] == 'US']`, that line immediately executes. Snowflake evaluates the filter condition against every row in `df` and creates a new DataFrame containing only the matching rows in memory. The memory cost is real and immediate. If `df` has 100 million rows and 50 columns, filtering it might require a few gigabytes of memory. If you then do `selected_df = filtered_df[['product_id', 'amount', 'date']]`, pandas creates another copy with only those three columns. Each operation materializes a new in-memory object. This is intuitive — operations run immediately and you can inspect results at any point — but it's devastatingly inefficient at scale.

Snowpark DataFrames are lazy. When you write `df.filter(col("REGION") == "US")`, nothing executes. Not a single byte of data is read. What Snowpark does instead is record your intent in an internal query plan — a tree data structure that represents the transformations you've described. When you add `.select("PRODUCT_ID", "AMOUNT", "ORDER_DATE")`, Snowpark adds another node to the query plan. When you add `.groupBy("PRODUCT_ID").agg(sf_sum("AMOUNT"))`, another node is added. The data in Snowflake is completely untouched during all of this.

Execution is triggered only when you call an "action" — a method that needs to actually return data. The primary actions are: `.show(n)` (print n rows to the console), `.collect()` (return all rows as a list of Row objects), `.to_pandas()` (return a pandas DataFrame), `.count()` (return the row count as an integer), and `.write.save_as_table()` (write results to a Snowflake table). When you call any of these, Snowpark takes the entire accumulated query plan, compiles it into a single SQL statement, and sends that SQL to Snowflake for execution.

The performance advantage is significant. Consider a pipeline that filters 10 million rows to 50,000, then selects 5 columns from 30, then aggregates to 100 summary rows. If pandas executed this eagerly, it would: read 10M rows × 30 columns into memory, create a 50,000 × 30 filtered copy, create a 50,000 × 5 selected copy, and produce 100 aggregated rows. Three large materializations for what is ultimately a 100-row result. Snowpark compiles all three operations into one SQL statement — `SELECT PRODUCT_ID, SUM(AMOUNT) FROM ... WHERE REGION = 'US' GROUP BY 1` — and Snowflake executes the entire thing in one pass, with its query optimizer choosing the most efficient execution plan. No intermediate materializations. No data movement until the 100-row result is returned.

```python
from snowflake.snowpark.functions import col, sf_sum, sf_avg, count, sf_max, sf_min

def demonstrate_dataframe_operations(session: Session) -> None:
    # Reference the table — no data is loaded at this point
    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    # Build up a query plan — still no execution
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

    # .show() is an action — THIS triggers execution
    df_filtered.show(10)

    # Aggregation — another query plan, executed when .show() is called
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
```

After running this code, take a moment to examine the SQL that Snowpark generated. You can see it by calling `df_filtered.queries` — this property returns the SQL strings without executing them, which is invaluable for debugging and for understanding what Snowpark is actually sending to the warehouse. If the generated SQL looks wrong or inefficient, you can diagnose it before it runs on production data.

The distinction between `.show()`, `.collect()`, `.to_pandas()`, and `.write.save_as_table()` is worth understanding explicitly because each is appropriate in different situations. `.show(n)` is the debugging tool — quick visual inspection during development. It prints to stdout and discards the rows, so it's inappropriate for production code that needs to process results. `.collect()` returns a Python list of `Row` objects, each behaving like a dictionary; use it when you need to iterate over results in Python, but be cautious with large result sets since all rows land in Python memory. `.to_pandas()` converts the result to a pandas DataFrame — appropriate when you need pandas-specific functionality (certain visualization libraries, pandas-based ML libraries, or writing to non-Snowflake destinations). `.write.save_as_table()` is the production workhorse: it writes results directly to a Snowflake table without ever pulling data to Python. For ETL pipelines where the output stays in Snowflake, this is always the right choice.

### Joins and Query Optimization

Joining tables is where the difference between Snowpark and naive SQL becomes most visible. Snowflake's query optimizer is sophisticated — it understands table statistics (row counts, cardinality, data distribution), knows the available execution strategies (hash join, merge join, broadcast join), and chooses the optimal plan. When you express a join using the Snowpark DataFrame API, the optimizer makes these decisions based on live metadata from the Snowflake catalog.

A broadcast join is particularly valuable to understand. When you join a large table (say, 100 million orders) to a small dimension table (say, 5,000 products), the optimizer can broadcast the small table to every compute node — meaning every node gets a full copy of the product dimension in memory and can look up product details without any inter-node communication. The `.hint("broadcast")` call in the code tells the optimizer your intent explicitly, but in many cases Snowflake's auto-clustering and statistics will make this decision automatically.

```python
from snowflake.snowpark.functions import col

def demonstrate_joins(session: Session) -> None:
    df_orders    = session.table("ANALYTICS.MARTS.FCT_ORDERS")
    df_customers = session.table("ANALYTICS.MARTS.DIM_CUSTOMERS")
    df_products  = session.table("ANALYTICS.MARTS.DIM_PRODUCTS")

    # Inner join: orders to customers
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

    # Left join with broadcast hint: the small products table is broadcast
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
```

One important subtlety when joining DataFrames in Snowpark: column name ambiguity. When both DataFrames have a column called `CUSTOMER_ID`, referring to `col("CUSTOMER_ID")` after the join is ambiguous. The solution is to qualify column references with their source DataFrame, as shown above: `df_orders["CUSTOMER_ID"]` and `df_customers["CUSTOMER_ID"]`. This is more verbose than writing SQL aliases, but it eliminates an entire class of runtime errors. If you encounter an `SnowparkJoinException` about ambiguous column references, this is the fix.

### Window Functions

Window functions represent one of SQL's most powerful features, and Snowpark exposes them through a clean Python API. A window function computes a value for each row in relation to a partition of surrounding rows — without collapsing those rows into a single aggregate (which is what GROUP BY does). The `Window` object defines the partitioning and ordering logic, and window function calls reference that window specification.

```python
from snowflake.snowpark import Window
from snowflake.snowpark.functions import (
    col, rank, dense_rank, row_number, lag, lead, sf_sum, ntile
)

def demonstrate_window_functions(session: Session) -> None:
    df_orders = session.table("ANALYTICS.MARTS.FCT_ORDERS")

    window_spec = Window.partition_by("REGION").order_by(col("ORDER_DATE"))
    window_all  = Window.partition_by("REGION")

    df_windowed = df_orders.select(
        col("ORDER_ID"),
        col("REGION"),
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
```

The difference between `rank()` and `dense_rank()` is a perennial source of confusion. `rank()` assigns rank 1, 2, 3 but skips numbers for ties: if two rows tie at rank 2, the next rank is 4, not 3. `dense_rank()` never skips: tied rows get the same rank, and the next rank is always one higher. `row_number()` assigns a unique sequential integer regardless of ties — the ordering within ties is non-deterministic unless you include a fully unique column in the order specification. `lag()` and `lead()` are for time-series analysis: `lag(col("AMOUNT"), 1)` gives you the previous row's amount, enabling period-over-period comparisons without self-joins. `ntile(4)` divides rows into 4 equal-sized buckets (quartiles) — powerful for percentile analysis and customer segmentation.

---

## 11.4 User-Defined Functions (UDFs)

The DataFrame API covers most of what you need for data transformation, but there are situations where you genuinely need Python. Calling a machine learning model for scoring. Using Python's `re` module for complex regex operations. Invoking a third-party library like `spacy` for natural language processing. Implementing custom business logic with intricate branching that would produce unreadable SQL. For these cases, Snowpark provides User-Defined Functions.

The decision of when to use a UDF versus expressing logic in the DataFrame API is important to get right. SQL expressions — `when(col("AMOUNT") < 100, lit("SMALL")).when(...)` — compile to native SQL and execute with zero Python overhead. They run at the full speed of Snowflake's execution engine. A UDF, by contrast, requires invoking a Python interpreter inside the warehouse, which has overhead. For a table with 10 million rows, calling a scalar UDF means 10 million Python function invocations. The overhead per invocation is small, but 10 million small overheads add up. A UDF that takes 10 microseconds per call on a 10 million row table adds 100 seconds of pure Python overhead on top of whatever the actual computation takes. Save UDFs for logic that genuinely cannot be expressed as SQL.

With that context in mind, here is a scalar UDF that categorizes orders into business tiers:

```python
from snowflake.snowpark.functions import col, udf
from snowflake.snowpark.types import FloatType, StringType

def register_order_category_udf(session: Session):
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
```

Several parameters in the `@udf` decorator deserve explanation. The `name` parameter is the name the function will have in the Snowflake catalog — you can call it from SQL with `SELECT categorize_order_value(AMOUNT) FROM ...`. The `replace=True` flag is equivalent to `CREATE OR REPLACE` — it overwrites any existing function with this name rather than failing. The `stage_location` parameter is not optional for permanent UDFs: Snowflake needs a place to store the Python source code so that when any warehouse node needs to call the function, it can load the code. The stage serves as the distribution mechanism for the UDF code across warehouse nodes.

The permanence distinction is important for your deployment strategy. When you register a UDF without specifying `is_permanent=True` (which in newer Snowpark versions is the parameter controlling this), the UDF exists only for the current session and disappears when the session closes. This is fine for development and exploration. For production code, register permanent UDFs: they appear in `SHOW FUNCTIONS`, can be called from SQL by any authorized user, can be referenced from dbt models, and persist across connection lifecycles. Build a practice of developing UDFs interactively with temporary registration, then deploying them as permanent objects in your CI/CD pipeline.

---

## 11.5 Vectorized (Pandas) UDFs

The performance limitation of scalar UDFs — one Python function call per row — becomes a serious problem at large data volumes. If categorizing order values takes one microsecond per call and your table has 50 million rows, you're spending 50 seconds just on function call overhead. For numerical operations that pandas already implements in highly optimized C code (string operations, arithmetic, statistical functions), the per-row overhead is especially wasteful.

Vectorized UDFs (also called Pandas UDFs or `@pandas_udf`) address this by changing the execution model entirely. Instead of receiving one value and returning one value, a vectorized UDF receives an entire batch of rows as a `pandas.Series` and must return a `pandas.Series` of the same length. Inside the function, you operate on the entire series at once using pandas vectorized operations, which are implemented in C and can process millions of values with SIMD instructions. The overhead per element drops from "one Python function call" to "a tiny fraction of a function call, amortized over thousands of rows."

```python
from snowflake.snowpark.functions import col, pandas_udf
from snowflake.snowpark.types import StringType, PandasSeries

def register_email_normalizer_udf(session: Session):
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
```

The `emails.str.lower().str.strip()` call processes an entire batch of email addresses at once. Pandas' string accessor (`str.`) delegates to highly optimized C code. Compared to a scalar UDF that calls `email.lower().strip()` on each row individually, the vectorized version processes a batch of 10,000 emails in roughly the same time the scalar version takes for 100.

The choice between scalar and vectorized UDFs follows a clear heuristic. Use vectorized UDFs for numerical operations, string operations, or any computation that benefits from pandas vectorization — basically, anything where you'd naturally write `series.apply(some_function)` in pandas but want better performance. Use scalar UDFs for logic with complex Python branching where a vectorized version would be awkward to write, for operations that involve external API calls (where you don't want to batch 10,000 API calls at once), or for cases where you genuinely need per-row control flow that can't be expressed naturally with series operations. Avoid `series.apply(lambda x: ...)` inside a vectorized UDF — that just puts you back to per-row Python execution and defeats the purpose.

---

## 11.6 Stored Procedures

User-Defined Functions are called from SQL queries and return values — they're functions in the mathematical sense. A stored procedure is something different: it's a full program. Stored procedures can contain multiple SQL statements, conditional branches, loops, transaction management, and error handling with try/except blocks. They're callable by name, return a single result (often a status string or a summary JSON), and can take parameters. Think of them as named, reusable scripts that run inside Snowflake.

The most natural use case for a stored procedure is an ETL job that consists of multiple steps: truncate a staging table, insert new records, run some validations, update a target table, log the result. You could run these steps as separate SQL commands from Python, but then you're managing the orchestration externally — if your Python process fails partway through, the Snowflake warehouse state may be inconsistent. Encapsulating the logic in a stored procedure means the entire multi-step operation is atomic and self-contained inside Snowflake.

```python
from snowflake.snowpark.functions import col, sf_sum, count, sproc
from snowflake.snowpark.types import StringType

def register_refresh_procedure(session: Session):
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
    print(f"Stored proc result: {result}")
```

The procedure's inner function receives `sp_session` as its first argument — this is the Snowpark session that runs inside Snowflake when the procedure executes. You use this session to do all Snowflake operations within the procedure. The outer `session` is your Python-side session that you use to register the procedure. The `packages` list specifies which Python packages are available inside the procedure at runtime — this is important because Snowflake's sandbox doesn't have every Python package installed by default; you have to declare what you need.

The `EXECUTE AS OWNER` versus `EXECUTE AS CALLER` distinction is a significant security consideration. By default, stored procedures execute with the caller's privileges — the procedure can only do what the person calling it could do themselves. This is the safe default: no privilege escalation. But there's a powerful pattern called "owner's rights" stored procedures where you set the procedure to execute with the owner's privileges. This allows you to give users a narrow, controlled ability to perform a specific privileged operation — say, refreshing a specific table — without granting them broad write access to the database. The procedure acts as a safe, controlled elevation of privilege. Think of it like a `setuid` binary in Unix: a non-privileged user can run it, and it executes with elevated permissions, but only to do exactly what the procedure author intended.

To call a stored procedure from SQL: `CALL refresh_revenue_summary_sp('ANALYTICS.MARTS.REGION_REVENUE_SUMMARY')`. To call from Python: `session.call('refresh_revenue_summary_sp', 'ANALYTICS.MARTS.REGION_REVENUE_SUMMARY')`. The return value is always a single value — if you need to return multiple values (status, row count, error details), return a JSON string and parse it on the calling side.

---

## 11.7 Snowpark ML: Machine Learning Inside the Warehouse

Traditional machine learning workflows have a structural friction problem that goes beyond just slow data transfers. The problem is that the entire ML lifecycle — data preparation, feature engineering, model training, evaluation, and scoring — typically involves multiple different systems, multiple different languages, and multiple boundary crossings where data moves between them. Data lives in Snowflake. Feature engineering happens in Python on a Spark cluster or a big EC2 instance. Model training runs on the same cluster. Scoring new data means another extraction from Snowflake, another pass through the scoring code, another write back. Each step creates an opportunity for data inconsistency, security exposure, and operational failure.

The compliance dimension is particularly acute in regulated industries. Healthcare organizations training churn models on patient data, financial firms training fraud models on transaction records, insurance companies training risk models on claims data — all of them face the question: when training data leaves the data warehouse and lands on ML infrastructure, is that still within the security boundary? Snowflake ML eliminates this question by running the entire pipeline inside the warehouse. The training data never leaves Snowflake's security perimeter. Column masking policies remain in effect. Row access policies remain in effect. Audit logging captures every operation. Your compliance team gets a much simpler answer to "where did the sensitive training data go": it never went anywhere.

Snowflake ML implements a scikit-learn-compatible API. If you already know scikit-learn, the `StandardScaler`, `OneHotEncoder`, `Pipeline`, and `RandomForestClassifier` objects will look familiar. The critical difference is in what happens under the hood. A scikit-learn `StandardScaler.fit(X)` computes column means and standard deviations in Python. A Snowflake ML `StandardScaler.fit(df)` runs a SQL aggregation query (`SELECT AVG(col), STDDEV(col) FROM ...`) against your Snowflake table to compute the same statistics. The fit is happening in the warehouse, not in your Python process. Similarly, `scaler.transform(df)` runs `SELECT (col - mean) / stddev FROM ...` as SQL. The data stays in Snowflake throughout.

### Feature Engineering

Before training a model, you almost always need to transform raw data into features that ML algorithms can work with effectively. Snowpark's DataFrame API is the natural tool for this — you're essentially writing the transformation logic as SQL-compiled operations.

```python
from snowflake.snowpark.functions import col, when, lit, sf_round

def engineer_features(df):
    df_features = (
        df
        # Bin total spend into interpretable buckets
        .with_column(
            "SPEND_BUCKET",
            when(col("TOTAL_SPEND") < 500,   lit("LOW"))
            .when(col("TOTAL_SPEND") < 2000,  lit("MEDIUM"))
            .when(col("TOTAL_SPEND") < 5000,  lit("HIGH"))
            .otherwise(lit("VIP"))
        )
        # Ratio feature: order efficiency relative to total spend
        .with_column(
            "ORDER_VALUE_RATIO",
            sf_round(col("AVG_ORDER_VALUE") / (col("TOTAL_SPEND") + lit(1.0)), 4)
        )
        # Binary flag for recently inactive customers
        .with_column(
            "IS_INACTIVE_90D",
            when(col("DAYS_SINCE_LAST") > 90, lit(1)).otherwise(lit(0))
        )
        # Log-transform skewed spend (reduces impact of outliers)
        .with_column(
            "LOG_TOTAL_SPEND",
            sf_round(col("TOTAL_SPEND").cast("float").log(), 4)
        )
        # Drop rows with null target variable
        .filter(col("IS_CHURNED").is_not_null())
    )
    return df_features
```

Each of these transformations compiles to SQL, so the feature engineering happens entirely in the warehouse during query execution. The `+ lit(1.0)` in the ratio calculation is a defensive coding pattern to avoid division-by-zero errors (a customer with zero total spend would cause the denominator to be zero without this guard). The log transform on `TOTAL_SPEND` is a standard technique for features with right-skewed distributions (a few very high spenders would otherwise dominate distance-based or linear algorithms). Adding this one line of Snowpark code is equivalent to the preprocessing step that data scientists often spend hours on in pandas notebooks.

### Building a Pipeline

The most important concept to understand in any ML framework is why pipelines exist. Without a pipeline, you do preprocessing and training as separate, manual steps. During training: fit the scaler, transform training data, fit the encoder, transform training data, train the model. During scoring: remember to apply the scaler with the same parameters from training, apply the encoder with the same categories from training, then score. "Remember to apply the same transformations" is a human instruction that humans reliably forget or implement incorrectly. Production ML systems fail all the time because someone applied a scaler from the wrong training run, or forgot to apply encoding during inference, or used different scaling parameters for training and scoring. The resulting errors are insidious because the model still produces numbers — just wrong numbers.

A Pipeline binds preprocessing and modeling into a single object. When you call `pipeline.fit(df_train)`, it fits all preprocessing steps on the training data and then trains the model. When you call `pipeline.predict(df_new)`, it automatically applies the exact same preprocessing transformations (using the parameters learned during fit) before scoring. Training and inference are guaranteed to be consistent because there is only one object managing both.

```python
from snowflake.ml.modeling.preprocessing import StandardScaler, OneHotEncoder
from snowflake.ml.modeling.pipeline import Pipeline
from snowflake.ml.modeling.ensemble import RandomForestClassifier
from snowflake.ml.modeling.model_selection import train_test_split
from snowflake.ml.modeling.metrics import accuracy_score, confusion_matrix

NUMERIC_COLS    = ["AGE", "TOTAL_SPEND", "NUM_ORDERS", "AVG_ORDER_VALUE",
                   "DAYS_SINCE_LAST", "ORDER_VALUE_RATIO", "LOG_TOTAL_SPEND"]
CATEGORICAL_COLS = ["SEGMENT", "COUNTRY_CODE", "SPEND_BUCKET"]
TARGET_COL       = "IS_CHURNED"

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

# Train/test split
df_train, df_test = train_test_split(df_features, test_size=0.20, random_state=42)

# Fit — training data never leaves Snowflake
pipeline.fit(df_train)

# Evaluate
df_predictions = pipeline.predict(df_test)
acc = accuracy_score(df=df_predictions,
                     y_true_col_names=[TARGET_COL],
                     y_pred_col_names=["PREDICTED_CHURN"])
print(f"Accuracy: {acc:.4f}")
```

When interpreting the evaluation results, accuracy alone is often insufficient for churn models. Churn datasets are typically imbalanced — if only 5% of customers churn, a model that predicts "no churn" for everyone achieves 95% accuracy while being completely useless. Always examine the confusion matrix alongside accuracy. The confusion matrix shows true positives (correctly predicted churners), false positives (customers predicted to churn who didn't), true negatives (correctly predicted retained customers), and false negatives (churners the model missed). The business cost of each error type is different — missing a churner (false negative) means lost revenue, while incorrectly targeting a retained customer (false positive) means wasted retention spend.

### The Model Registry

Training a model produces a Python object in memory. That object is ephemeral — if your Python process ends, the trained model is gone. In production, you need models to be persistent, versioned, and discoverable. The Snowflake Model Registry provides exactly this.

```python
from snowflake.ml.registry import Registry

def register_and_score(session: Session, pipeline, acc: float):
    registry = Registry(
        session=session,
        database_name="ANALYTICS",
        schema_name="ML_REGISTRY",
    )

    # Register the trained model with metadata
    model_ref = registry.log_model(
        model=pipeline,
        model_name="CUSTOMER_CHURN_CLASSIFIER",
        version_name="V1",
        comment=f"RandomForest churn classifier | accuracy={acc:.4f}",
        metrics={"accuracy": acc},
        conda_dependencies=["scikit-learn"],
    )

    # Load back and score new data
    loaded_model = registry.get_model("CUSTOMER_CHURN_CLASSIFIER").version("V1")
    df_new = session.table("ANALYTICS.ML_FEATURES.NEW_CUSTOMERS_TO_SCORE")
    df_scored = loaded_model.run(df_new, function_name="predict")

    df_scored.write.mode("overwrite").save_as_table(
        "ANALYTICS.ML_FEATURES.CHURN_PREDICTIONS"
    )
```

The Model Registry stores the model as a Snowflake object in the specified schema — you can see it in Snowsight's UI and query metadata about it using SQL. The `metrics` parameter stores evaluation metrics alongside the model object, so you can query registry metadata to compare model versions: "what was the accuracy of V1 versus V2?" The `version_name` parameter is critical for production workflows — when you retrain a model with new data, you register it as V2 while V1 remains available for rollback. The `registry.get_model("CUSTOMER_CHURN_CLASSIFIER").version("V1")` pattern ensures you load the exact model version you registered, not just "the latest" (though `default_version()` is available for that). Model governance in regulated industries often requires proving that the model used for a specific decision was the one registered at a specific time — the Registry provides that audit trail.

---

## Chapter 11 Summary

Snowpark eliminates the data movement tax that made large-scale Python-based data processing expensive and risky. The key architectural insight is the compilation model: DataFrame operations compile to SQL (fast, no Python overhead, benefits from the query optimizer), while UDFs and stored procedures run Python inside the warehouse (flexible, supports any library, runs inside Snowflake's security boundary). Lazy evaluation means you build up query plans without executing them, and the optimizer sees the full plan before choosing an execution strategy. Vectorized UDFs dramatically outperform scalar UDFs for batch numerical and string operations by processing entire pandas Series rather than individual rows. Snowpark ML extends this model to machine learning, running the entire pipeline — feature engineering, training, evaluation, scoring — inside the warehouse with a scikit-learn-compatible API and a Model Registry for governance.

The next chapter builds on this foundation by introducing Streamlit in Snowflake — a way to turn Snowpark-powered queries into interactive web applications that live entirely inside your Snowflake account.

---

# Chapter 12: Streamlit in Snowflake

## 12.1 The Data App Problem

Data teams spend enormous energy producing insights that never reach the people who need to act on them. The traditional delivery mechanism is a dashboard in Tableau or Power BI, which works reasonably well for static metrics but has fundamental limitations. BI tools require a separate server infrastructure and licensing budget. They connect to Snowflake through an integration that pulls data out of the warehouse at query time, creating a data movement path that bypasses Snowflake's row access policies and column masking policies. Building interactive experiences in BI tools — filtering, parameter passing, conditional logic — requires learning the tool's proprietary expression language, which is often less powerful than Python. And for anything involving ML model inference, custom calculations, or external API calls, BI tools simply cannot do it.

The Jupyter notebook is the other common delivery mechanism. Data scientists love notebooks for exploration, and they can produce surprisingly rich visualizations. But a notebook is not a user interface for non-technical stakeholders. Business users cannot be expected to open a Jupyter environment, find the right notebook, run cells in the right order, and interpret code output. Notebooks also have the data movement problem: they typically run on a server outside Snowflake and pull data across the network.

Streamlit in Snowflake (SiS) addresses both problems simultaneously. Streamlit is an open-source Python framework that turns a Python script into a fully interactive web application with no HTML, CSS, or JavaScript required. You write Python; Streamlit renders it as a web app. Streamlit in Snowflake runs that web app inside Snowflake's infrastructure — on Snowflake's servers, with Snowflake's networking, governed by Snowflake's access controls. There is no separate server to provision. There is no deployment pipeline to build. There are no additional licensing costs beyond what you already pay for Snowflake. And because the app runs inside Snowflake, the data never leaves the warehouse to be displayed — the computation happens inside Snowflake and only the rendered output is sent to the user's browser.

The governance implications deserve emphasis. When an analyst builds a Streamlit in Snowflake app, the app executes with the session of the user who launches it. If that user doesn't have SELECT on the raw customer PII table, their app session cannot query it. Column masking policies apply to every query the app runs. Row access policies restrict which rows are returned. The app developer doesn't need to implement any of this — it's automatic because the app's session is the user's session. This is the "governance for free" value that makes SiS particularly compelling for organizations with strong data governance requirements.

---

## 12.2 Streamlit Fundamentals

Before examining the full dashboard application, it's worth understanding how Streamlit works at a conceptual level, because the reactive execution model is different from how most web applications behave.

A Streamlit app is a Python script. Streamlit executes this script from top to bottom, and as it encounters Streamlit commands — `st.slider(...)`, `st.selectbox(...)`, `st.text_input(...)` — it renders the corresponding UI widgets. `st.write("Hello")` renders text. `st.chart(df)` renders a chart. `st.dataframe(df)` renders an interactive table. So far this seems straightforward. The magic is in what happens when a user interacts with a widget.

Every time a user moves a slider, makes a selection, or types in an input box, Streamlit re-runs your entire Python script from the top. Not just the part that handles that widget — the whole script. The widget's new value is returned by the widget call (e.g., `year = st.slider("Year", 2020, 2024)` returns the current slider position), so as the script re-runs, downstream code that uses `year` automatically sees the new value. This means you describe your app's behavior as a function of inputs, and Streamlit handles all the re-rendering. You never write event handlers, you never manage component state, you never wire up callbacks. This reactive model is why Streamlit apps are so fast to build — the complexity of web UI state management is completely hidden.

The `get_active_session()` function is the bridge between your Streamlit app and Snowflake:

```python
from snowflake.snowpark.context import get_active_session

session = get_active_session()
```

Inside a Streamlit in Snowflake app, you don't configure a connection. Snowflake injects the session automatically. That session is the session of the user who opened the app in Snowsight. This means every query your app runs executes with that user's identity, role, and all associated access controls. It's identical to the user typing queries in a Snowflake worksheet — just with a much nicer interface.

---

## 12.3 The Complete Dashboard Application

The sales dashboard application demonstrates the patterns you'll use in virtually every SiS application you build. Let's walk through each section and understand both what it does and why it's structured the way it is.

### Caching

Before any of the dashboard logic, there is a caching decorator worth paying close attention to:

```python
import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session
import altair as alt

st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

session = get_active_session()

@st.cache_data(ttl=300, show_spinner="Querying Snowflake...")
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    try:
        return session.sql(sql, params).to_pandas()
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return pd.DataFrame()
```

The `@st.cache_data(ttl=300)` decorator is essential for performance. Remember that Streamlit re-runs your entire script on every user interaction. Without caching, every slider movement, every filter change, every button click would re-execute every Snowflake query — including queries for sidebar filter options that don't change from interaction to interaction. With caching, Streamlit stores the result of `run_query(sql, params)` keyed by the exact SQL string and parameters. If the same query is called again within 300 seconds, the cached result is returned immediately without hitting Snowflake. The `ttl=300` (time-to-live of 300 seconds) means cached results expire and are refreshed from Snowflake every five minutes. Adjust this based on how frequently your underlying data changes — for a dashboard showing daily metrics, a TTL of 3600 seconds (one hour) might be appropriate; for a real-time operational dashboard, you might use 30 seconds.

### Sidebar Filters

The sidebar filter pattern is the standard UX foundation for analytics dashboards. Users need the ability to narrow the scope of the data before they see results — otherwise a dashboard showing all regions, all products, all time periods becomes overwhelming and slow. The sidebar keeps filters visible and accessible without consuming space in the main content area.

```python
st.sidebar.header("Filters")

# Date range picker
min_date = pd.to_datetime("2024-01-01").date()
max_date = pd.to_datetime("2024-12-31").date()
date_range = st.sidebar.date_input(
    "Order Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
start_date, end_date = date_range if len(date_range) == 2 else (min_date, max_date)

# Region multiselect — options loaded dynamically from Snowflake
region_options_df = run_query(
    "SELECT DISTINCT REGION FROM ANALYTICS.MARTS.FCT_ORDERS ORDER BY 1"
)
region_options = region_options_df["REGION"].tolist() if not region_options_df.empty else []
selected_regions = st.sidebar.multiselect(
    "Region",
    options=region_options,
    default=[],
    placeholder="All regions",
)

# Customer segment, product category, order status filters follow the same pattern
segment_options  = ["Bronze", "Silver", "Gold", "Platinum"]
status_options   = ["COMPLETED", "PENDING", "CANCELLED", "REFUNDED"]
selected_segments = st.sidebar.multiselect("Customer Segment", options=segment_options, default=[])
selected_statuses = st.sidebar.multiselect("Order Status", options=status_options, default=["COMPLETED"])
```

Loading filter options dynamically from Snowflake (`run_query("SELECT DISTINCT REGION ...")`) rather than hardcoding them means the dashboard stays current automatically as new regions or categories appear in the data. The `@st.cache_data` wrapper ensures this query doesn't run on every user interaction — it runs once and caches the result for 300 seconds. The date range picker `date_input` returns a tuple of two dates when used with `value=(start, end)`, but you need the defensive `len(date_range) == 2` check because Streamlit briefly returns a single date while the user is in the middle of selecting the second date.

### Building Safe SQL Clauses

The filter values from the sidebar widgets need to become WHERE clause conditions. This is where careful SQL construction matters, even for internal applications:

```python
where_clauses = [
    f"o.ORDER_DATE BETWEEN '{start_date}' AND '{end_date}'"
]
if selected_regions:
    regions_in = ", ".join(f"'{r}'" for r in selected_regions)
    where_clauses.append(f"o.REGION IN ({regions_in})")
if selected_statuses:
    statuses_in = ", ".join(f"'{s}'" for s in selected_statuses)
    where_clauses.append(f"o.STATUS IN ({statuses_in})")
if selected_segments:
    segs_in = ", ".join(f"'{s}'" for s in selected_segments)
    where_clauses.append(f"c.SEGMENT IN ({segs_in})")

where_sql = " AND ".join(where_clauses)

BASE_JOIN = """
    FROM ANALYTICS.MARTS.FCT_ORDERS      o
    JOIN ANALYTICS.MARTS.DIM_CUSTOMERS   c ON o.CUSTOMER_ID = c.CUSTOMER_ID
    JOIN ANALYTICS.MARTS.DIM_PRODUCTS    p ON o.PRODUCT_ID  = p.PRODUCT_ID
"""
```

The list-append-then-join pattern for building WHERE clauses is worth noting. Starting with a mandatory date condition and appending additional conditions only when their filter has a non-empty selection means no filters results in just the date range condition — never a missing WHERE clause that would return all data regardless of date. The `if selected_regions:` guard ensures that an empty list (user selected "all regions") doesn't produce `o.REGION IN ()` which is invalid SQL.

### KPI Metrics

```python
kpi_sql = f"""
SELECT
    COALESCE(SUM(o.AMOUNT), 0)                             AS total_revenue,
    COUNT(o.ORDER_ID)                                      AS total_orders,
    COUNT(DISTINCT o.CUSTOMER_ID)                          AS unique_customers,
    COALESCE(AVG(o.AMOUNT), 0)                             AS avg_order_value
{BASE_JOIN}
WHERE {where_sql}
"""

kpi_df = run_query(kpi_sql)

if not kpi_df.empty:
    rev   = kpi_df["TOTAL_REVENUE"].iloc[0]
    ords  = int(kpi_df["TOTAL_ORDERS"].iloc[0])
    custs = int(kpi_df["UNIQUE_CUSTOMERS"].iloc[0])
    aov   = kpi_df["AVG_ORDER_VALUE"].iloc[0]

kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
kpi_col1.metric("Total Revenue",    f"${rev:,.2f}")
kpi_col2.metric("Total Orders",     f"{ords:,}")
kpi_col3.metric("Unique Customers", f"{custs:,}")
kpi_col4.metric("Avg Order Value",  f"${aov:,.2f}")
```

The four KPI cards at the top of the dashboard follow a standard analytics design principle: give users the "so what" before the "what happened." Business stakeholders who open a dashboard want to know the headline numbers immediately — are we up or down? — before diving into trend charts and breakdowns. `st.metric()` accepts an optional `delta` parameter: `st.metric("Total Revenue", f"${rev:,.2f}", delta="+12%")` adds a colored indicator showing change from a reference period. This is extremely effective for dashboards that show weekly or monthly comparisons — you see not just the absolute number but whether it's good or bad relative to expectations. `COALESCE(SUM(...), 0)` protects against NULL returns when no rows match the filter — without it, the `.iloc[0]` access would return a Python None and the `f"${rev:,.2f}"` formatting would fail with a TypeError.

### Charts

```python
chart_col1, chart_col2 = st.columns([3, 2])

with chart_col1:
    st.subheader("Revenue Trend")
    trend_sql = f"""
    SELECT
        DATE_TRUNC('week', o.ORDER_DATE)::DATE AS week_start,
        SUM(o.AMOUNT)                          AS weekly_revenue
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1
    ORDER BY 1
    """
    trend_df = run_query(trend_sql)
    if not trend_df.empty:
        trend_df.columns = trend_df.columns.str.lower()
        area_chart = (
            alt.Chart(trend_df)
            .mark_area(
                line={"color": "#1f77b4"},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color="#1f77b4", offset=1),
                        alt.GradientStop(color="white",   offset=0),
                    ],
                    x1=1, x2=1, y1=1, y2=0,
                ),
            )
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("weekly_revenue:Q", title="Revenue ($)"),
                tooltip=["week_start:T", "weekly_revenue:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(area_chart, use_container_width=True)
```

The `trend_df.columns = trend_df.columns.str.lower()` line is necessary because Snowflake returns column names in uppercase by default, but Altair expects the column names in the chart specification to match the DataFrame column names exactly (case-sensitive). Lowercasing everything is the simplest way to avoid the mismatch. The `alt.X("week_start:T")` type annotation `:T` tells Altair this is a temporal (date/time) field — Altair uses this to format axis labels appropriately and choose sensible tick intervals. `:Q` means quantitative (numeric), `:N` means nominal (categorical), `:O` means ordinal. Getting these type annotations right prevents Altair from rendering dates as numbers or treating continuous numeric data as discrete categories.

The `use_container_width=True` parameter makes charts fill their column width responsively. Without it, charts have fixed pixel widths that overflow or underflow depending on the user's browser window size. Always include this parameter for charts inside `st.columns()`.

### Donut Chart and Data Table

```python
with donut_col:
    st.subheader("Revenue by Region")
    region_sql = f"""
    SELECT o.REGION, SUM(o.AMOUNT) AS region_revenue
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1
    ORDER BY 2 DESC
    """
    region_df = run_query(region_sql)
    if not region_df.empty:
        region_df.columns = region_df.columns.str.lower()
        donut = (
            alt.Chart(region_df)
            .mark_arc(innerRadius=60)
            .encode(
                theta=alt.Theta("region_revenue:Q"),
                color=alt.Color("region:N", scale=alt.Scale(scheme="tableau10")),
                tooltip=["region:N", "region_revenue:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(donut, use_container_width=True)

with table_col:
    st.subheader("Top 15 Customers by Revenue")
    top_cust_sql = f"""
    SELECT
        c.CUSTOMER_ID, c.FULL_NAME, c.SEGMENT, c.COUNTRY_CODE,
        COUNT(o.ORDER_ID)  AS order_count,
        SUM(o.AMOUNT)      AS total_spent,
        MAX(o.ORDER_DATE)  AS last_order_date
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1, 2, 3, 4
    ORDER BY total_spent DESC
    LIMIT 15
    """
    cust_df = run_query(top_cust_sql)
    if not cust_df.empty:
        cust_df.columns = cust_df.columns.str.lower()
        cust_df["total_spent"] = cust_df["total_spent"].map("${:,.2f}".format)
        st.dataframe(
            cust_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "customer_id":     st.column_config.TextColumn("Customer ID"),
                "total_spent":     st.column_config.TextColumn("Total Spent"),
                "last_order_date": st.column_config.DateColumn("Last Order"),
            },
        )
```

The `mark_arc(innerRadius=60)` is the Altair idiom for a donut chart. A pie chart is `mark_arc()` with no inner radius; adding `innerRadius` creates the hole. The `tableau10` color scheme is a perceptually distinct 10-color palette that is one of the most widely used in data visualization — good default choice for categorical series with up to 10 members.

The `st.column_config` API is powerful for making data tables look professional. `DateColumn` formats timestamps nicely. `TextColumn` with a custom label renames column headers without requiring a rename in the DataFrame itself (keeping the SQL query results unchanged). `NumberColumn` adds formatting and optional sparklines. For public-facing dashboards, spending a few minutes on column config pays off in user trust and polish.

### CSV Export

```python
with st.expander("Raw Order Data", expanded=False):
    raw_sql = f"""
    SELECT o.ORDER_ID, o.ORDER_DATE, c.FULL_NAME AS customer_name,
           c.SEGMENT, p.PRODUCT_NAME, p.CATEGORY, o.AMOUNT, o.STATUS, o.REGION
    {BASE_JOIN}
    WHERE {where_sql}
    ORDER BY o.ORDER_DATE DESC
    LIMIT 1000
    """
    raw_df = run_query(raw_sql)
    if not raw_df.empty:
        raw_df.columns = raw_df.columns.str.lower()
        search_term = st.text_input("Search by customer name or product", "")
        if search_term:
            mask = (
                raw_df["customer_name"].str.contains(search_term, case=False, na=False)
                | raw_df["product_name"].str.contains(search_term, case=False, na=False)
            )
            raw_df = raw_df[mask]

        st.dataframe(raw_df, use_container_width=True, hide_index=True)

        csv_bytes = raw_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download as CSV",
            data=csv_bytes,
            file_name="orders_export.csv",
            mime="text/csv",
        )
```

The CSV download feature might seem like a minor convenience, but it serves an important operational function. Not every analysis can happen in Snowflake or in a Streamlit app. Financial analysts preparing board presentations need to copy numbers into PowerPoint. Operations teams need to import data into scheduling tools. Providing a controlled download button — with the same filters applied as the dashboard — is far better than these users setting up their own database connections and pulling arbitrary data sets. The `LIMIT 1000` in the SQL is a deliberate guard: this isn't meant for bulk exports (use Snowflake's COPY INTO for that), it's for ad-hoc review and light manipulation.

The `expanded=False` on the `st.expander` means the raw data table is collapsed by default. This keeps the dashboard visually clean — users who want the aggregate view see it immediately, while users who want raw rows can expand the section. Default collapsed also means the raw data query doesn't run on initial page load, which is a small but meaningful performance optimization.

---

## 12.4 Access Control for Streamlit Apps

Deploying a Streamlit app in Snowflake is a two-part authorization problem: who can see and launch the app, and what data can the app access.

The first part is controlled by Snowflake object privileges on the Streamlit object itself:

```sql
-- Create the app
CREATE STREAMLIT ANALYTICS.PUBLIC.SALES_DASHBOARD
    ROOT_LOCATION = '@ANALYTICS.PUBLIC.STREAMLIT_STAGE/sales_dashboard'
    MAIN_FILE = 'sales_dashboard_app.py'
    QUERY_WAREHOUSE = COMPUTE_WH;

-- Grant the ability to launch the app
GRANT USAGE ON STREAMLIT ANALYTICS.PUBLIC.SALES_DASHBOARD
    TO ROLE ANALYST_ROLE;
```

The second part is controlled by the role's existing privileges on the underlying tables. A user with `ANALYST_ROLE` who has been granted `USAGE ON STREAMLIT` can open the dashboard. But when the app runs SQL queries, those queries run with the user's active role. If the user's role doesn't have SELECT on `ANALYTICS.MARTS.FCT_ORDERS`, the queries fail and the dashboard shows error messages instead of charts. This is the intended behavior — the app cannot bypass data access controls.

This layered model enables a powerful access pattern. You can create a "dashboard viewers" role that has `USAGE ON STREAMLIT` but limited direct table access. Users in this role can use the curated dashboard experience but cannot connect to Snowflake directly and run arbitrary SQL. The dashboard presents data through the lens of filters and aggregations that the developer designed, with appropriate masking for sensitive fields. For organizations that want to give broad access to insights while restricting raw data access, this pattern provides exactly the right control.

---

## Chapter 12 Summary

Streamlit in Snowflake turns Snowpark queries into interactive web applications that live inside Snowflake's infrastructure, governed by Snowflake's access controls, with no external servers or deployment infrastructure required. The reactive execution model — re-run the script on every interaction, cache expensive queries with `@st.cache_data` — produces snappy dashboards with surprisingly little code. The key patterns are: sidebar filters with dynamic SQL clause construction, KPI metric cards for headline numbers, Altair charts for rich interactive visualizations, `st.dataframe()` with column config for polished data tables, and `st.download_button()` for controlled data export. Access to the app is separate from access to the underlying data — both layers use standard Snowflake RBAC.

Chapter 13 takes the next step: instead of querying and visualizing structured data, we'll use Snowflake Cortex to run large language model inference and machine learning functions directly inside the warehouse.

---

# Chapter 13: Snowflake Cortex AI

## 13.1 The AI Integration Problem

Adding AI capabilities to a data pipeline has historically required building a bridge between two worlds that were never designed to work together. Your data lives in Snowflake. Your AI lives in a cloud API — OpenAI, Anthropic, Google Vertex, or an open-source model deployed on GPU infrastructure. The integration pattern is always the same: extract data from Snowflake, call the AI API from Python (row by row or in batches), store results back in Snowflake. The problems with this pattern are well-documented among teams that have tried it.

Data movement and compliance is the first problem. The moment customer reviews, contract text, medical notes, or financial records leave your Snowflake account to be sent to an external AI API, you have a compliance event. GDPR requires knowing where personal data is processed. HIPAA requires Business Associate Agreements with every vendor that processes PHI. PCI DSS restricts where cardholder data can travel. Even where regulations don't technically prohibit external AI calls, your information security team will (correctly) flag them as risks. Building a defensible AI workflow on sensitive data using external APIs requires legal review, data processing agreements, and security assessments that can take months. Many teams have abandoned valuable AI use cases not because the AI didn't work, but because the compliance burden was too high.

API cost and scalability is the second problem. Running sentiment analysis on 1 million customer reviews using OpenAI's API at current pricing would cost hundreds of dollars and take hours, since the API is rate-limited. At 50 million reviews, the economics become entirely unworkable. External APIs are priced and designed for on-demand inference on moderate data volumes, not for bulk analysis of entire data warehouse tables.

Operational complexity is the third problem. The integration code that extracts data, batches it for the API, handles rate limits and retries, parses responses, handles malformed JSON, and writes results back is not trivial. It's custom infrastructure that your team has to build, test, and maintain. When the API changes its response format or rate limits change, your pipeline breaks. Teams often find they've spent more time maintaining the integration plumbing than they have on the actual AI use cases.

Cortex AI eliminates all three problems. Snowflake Cortex runs LLM inference inside Snowflake's infrastructure — the same infrastructure that executes your SQL queries. Your data never leaves. You call LLM functions with SQL syntax (`SNOWFLAKE.CORTEX.SENTIMENT(review_text)`), and Snowflake handles all the model invocation, scaling, and billing through the standard Snowflake credits system you're already using. For a data team that already knows SQL, this means adding AI to any query is literally adding one function call.

---

## 13.2 LLM Functions: COMPLETE, SUMMARIZE, SENTIMENT, TRANSLATE

### COMPLETE

COMPLETE is the most general Cortex function — it gives you direct access to large language models with a prompt and returns the model's response. Every other Cortex LLM function (SENTIMENT, SUMMARIZE, TRANSLATE) is essentially a specialized wrapper around COMPLETE with a pre-engineered prompt for its specific task. When the specialized functions fit your use case, prefer them — they're optimized and require no prompt engineering. Use COMPLETE for tasks that require custom logic: classification into your specific business categories, structured data extraction, content generation, code generation, or complex multi-step reasoning.

Model selection requires conscious thought. Smaller models (Llama 3.2-3B, Mistral 7B) are faster and consume fewer Snowflake credits. They handle straightforward tasks well: simple classification, basic Q&A, short text generation. Larger models (Llama 3.1-70B, Llama 3.1-405B, Mistral Large) are more capable for complex reasoning, nuanced understanding, and tasks requiring broad world knowledge. They cost more credits and take longer. The business decision is: what is the complexity of the task relative to the cost of the model? For routing 1 million support tickets to five categories, a small model is accurate enough and much cheaper. For analyzing complex legal contract language, a large model's nuanced understanding is worth the extra cost.

```sql
-- Simple completion: ask the LLM a direct question
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'mistral-large2',
    'Explain what a Snowflake Virtual Warehouse is in two sentences.'
) AS llm_response;

-- Structured extraction using system prompt + user message
SELECT
    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large2',
        [
            {
                'role': 'system',
                'content': 'You are a data extraction assistant. Always respond with valid JSON only, no prose.'
            },
            {
                'role': 'user',
                'content': 'Extract the company name, invoice number, and total amount from this text: "Invoice #INV-20240315 from Acme Corp for consulting services totaling $4,250.00 due March 31 2024."'
            }
        ],
        { 'temperature': 0, 'max_tokens': 200 }
    ) AS extracted_json;
```

The `temperature` parameter controls the randomness of the model's output. At `temperature: 0`, the model is deterministic — given the same prompt, it will always produce the same output. This is what you want for data pipelines: you need reproducible, consistent results. If you run the same invoice extraction query twice against the same data, you expect to get the same extracted values both times. At higher temperatures (0.7–1.0), the model introduces randomness — useful for creative tasks like generating marketing copy variations, where you want diversity in outputs. For any automated data processing, use `temperature: 0` or `temperature: 0.1`.

### Handling LLM Output as Structured Data

When you instruct an LLM to respond in JSON, it usually does — but "usually" is not "always." Even with a system prompt saying "respond only with valid JSON," LLMs occasionally prepend explanatory text, include trailing comments, or produce subtly malformed JSON. In a production pipeline processing millions of rows, a single malformed JSON response would cause `PARSE_JSON()` to throw an error and potentially fail the entire query. The solution is `TRY_PARSE_JSON()`:

```sql
WITH llm_output AS (
    SELECT
        ORDER_ID,
        SNOWFLAKE.CORTEX.COMPLETE(
            'mistral-large2',
            [
                {
                    'role': 'system',
                    'content': 'Respond only with a JSON object with fields: risk_level (LOW/MEDIUM/HIGH), reason (string), recommended_action (string).'
                },
                {
                    'role': 'user',
                    'content': 'Assess fraud risk for an order: amount=$' || AMOUNT::STRING
                        || ', country=' || COUNTRY_CODE
                        || ', is_new_customer=' || IS_NEW_CUSTOMER::STRING
                }
            ],
            { 'temperature': 0 }
        ) AS raw_json
    FROM ANALYTICS.PUBLIC.ORDERS_RISK_STAGING
    LIMIT 20
)
SELECT
    ORDER_ID,
    TRY_PARSE_JSON(raw_json)                         AS parsed,
    TRY_PARSE_JSON(raw_json)['risk_level']::STRING   AS risk_level,
    TRY_PARSE_JSON(raw_json)['reason']::STRING       AS reason
FROM llm_output;
```

`TRY_PARSE_JSON()` returns NULL instead of raising an error when the JSON is malformed. This means rows where the LLM produced invalid JSON show NULL in the structured columns rather than causing the entire query to fail. In production, wrap this with COALESCE: `COALESCE(TRY_PARSE_JSON(raw_json)['risk_level']::STRING, 'UNKNOWN')` to give a sensible default for failed extractions. Build a monitoring query that counts the NULL rate — if more than 1-2% of rows are failing JSON extraction, your prompt needs refinement.

### SENTIMENT

```sql
SELECT
    REVIEW_ID,
    CUSTOMER_ID,
    LEFT(REVIEW_TEXT, 80) || '...'               AS review_preview,
    SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT)      AS sentiment_score,
    CASE
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) >=  0.3 THEN 'POSITIVE'
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) <= -0.3 THEN 'NEGATIVE'
        ELSE 'NEUTRAL'
    END                                           AS sentiment_label
FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS
ORDER BY sentiment_score ASC
LIMIT 10;
```

SENTIMENT returns a float between -1.0 and 1.0. -1.0 represents maximally negative text; 1.0 represents maximally positive text; 0.0 represents neutral or ambiguous text. The thresholds you apply to bin this into POSITIVE/NEUTRAL/NEGATIVE are business decisions, not technical ones. In the code above, ±0.3 is used as the boundary. This means scores between -0.3 and 0.3 are classified as neutral — the "uncertain" zone. You might tighten this to ±0.1 if you want broader positive and negative classifications, or widen it to ±0.5 if you only want to flag very strong sentiment. Consider your use case: for a customer satisfaction program, you might define "at risk" as any review below 0.1 (slightly positive is still worth attention); for a simple pass/fail content moderation system, you might only flag scores below -0.7.

Note that SENTIMENT is called twice in the above query — once for the score and once for the label. This means two model invocations per row. The more efficient pattern is to compute SENTIMENT once in a CTE or subquery and reference the result:

```sql
WITH scored AS (
    SELECT *, SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) AS sentiment_score
    FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS
)
SELECT
    REVIEW_ID,
    sentiment_score,
    CASE
        WHEN sentiment_score >=  0.3 THEN 'POSITIVE'
        WHEN sentiment_score <= -0.3 THEN 'NEGATIVE'
        ELSE 'NEUTRAL'
    END AS sentiment_label
FROM scored;
```

### EXTRACT_ANSWER and the RAG Pattern

```sql
SELECT
    DOC_ID,
    SNOWFLAKE.CORTEX.EXTRACT_ANSWER(
        DOCUMENT_TEXT,
        'What is the payment due date?'
    ) AS due_date_answer,
    SNOWFLAKE.CORTEX.EXTRACT_ANSWER(
        DOCUMENT_TEXT,
        'What is the total invoice amount?'
    ) AS invoice_amount_answer
FROM ANALYTICS.PUBLIC.INVOICE_DOCUMENTS
LIMIT 5;
```

EXTRACT_ANSWER implements a simple but powerful pattern from the AI field called RAG — Retrieval-Augmented Generation. The idea is that you provide the model with a specific context document and a question, and the model extracts (or generates) an answer grounded in that context rather than drawing on its general training knowledge. This is important for factual accuracy: if you ask an LLM "what is the payment due date?" without providing a context document, it might confabulate a plausible-sounding date. When you provide the actual invoice text as context, the model is constrained to find the date that actually appears in that document. It cannot make up an answer that isn't there.

The return value from EXTRACT_ANSWER is a JSON object with `answer` and `score` fields. The `score` represents the model's confidence that its answer is correct based on the provided context. Low scores (below 0.4) indicate the model couldn't confidently identify the answer in the document — either the question is poorly phrased for that document, or the document doesn't contain the answer. Build a downstream workflow that routes low-confidence extractions to manual review rather than accepting them automatically.

---

## 13.3 Batch Processing and the Python Integration

For large-scale processing — enriching all reviews with sentiment, classification, and summaries — SQL views are the natural mechanism. A view wraps the LLM function calls and makes them transparently queryable:

```sql
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.REVIEWS_ENRICHED AS
SELECT
    REVIEW_ID,
    CUSTOMER_ID,
    PRODUCT_ID,
    REVIEW_DATE,
    REVIEW_TEXT,
    SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) AS sentiment_score,
    CASE
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) >=  0.3 THEN 'POSITIVE'
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(REVIEW_TEXT) <= -0.3 THEN 'NEGATIVE'
        ELSE 'NEUTRAL'
    END AS sentiment_label,
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        REVIEW_TEXT,
        ['Product Quality', 'Shipping Speed', 'Customer Service', 'Pricing', 'Other']
    )['label']::STRING AS review_topic,
    CASE
        WHEN LENGTH(REVIEW_TEXT) > 300
        THEN SNOWFLAKE.CORTEX.SUMMARIZE(REVIEW_TEXT)
        ELSE REVIEW_TEXT
    END AS review_summary
FROM ANALYTICS.PUBLIC.CUSTOMER_REVIEWS;
```

This view computes LLM enrichments lazily — they're computed when the view is queried, not when the view is created. For a table with 1 million reviews, materialize this view into a table (using `CREATE TABLE AS SELECT * FROM REVIEWS_ENRICHED`) to avoid re-running LLM inference on every downstream query. Use Snowflake Streams and Tasks to incrementally process new reviews as they arrive, rather than reprocessing the entire table on each run.

For programmatic access from Python, the Snowpark session bridges to Cortex functions naturally:

```python
def example_cortex_via_python(session: Session) -> None:
    # Direct SQL execution — simplest integration
    result = session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?) AS answer",
        params=["What is a Snowflake micro-partition in one sentence?"]
    ).collect()
    print("COMPLETE answer:", result[0]["ANSWER"])

    # Batch sentiment analysis — process a Python list of reviews
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
```

The `?` placeholder and `params=` pattern is the Snowflake parameterized query mechanism. It prevents SQL injection by separating SQL structure from data values — the value is never interpolated into the SQL string. This matters even for internal applications, because the values might contain apostrophes (customer names like "O'Brien") that would break naive string interpolation.

---

## 13.4 Cortex Search: Semantic Search

Standard database text search (`LIKE '%wireless headphones%'`) is keyword-based: it finds rows that contain the exact characters you searched for. This works well for known terminology but fails when users express their needs in natural language. A customer searching "audio device for commuting without wires" won't find product listings titled "Wireless Bluetooth Earbuds" with keyword search — none of the search words appear in the product name. Semantic search finds results based on meaning, not exact characters.

Cortex Search uses vector embeddings to implement semantic search. When you create a Cortex Search service, Snowflake generates numerical vector representations (embeddings) of every text in your table's search columns. These vectors encode semantic meaning — the word "wireless" and the phrase "without wires" map to nearby points in the vector space. Searching for a query generates an embedding of the query, and Snowflake finds the database entries with the most similar vectors using cosine similarity. Semantic similarity translates to physical proximity in the vector space.

```sql
-- Create a Cortex Search service on the product catalog
CREATE OR REPLACE CORTEX SEARCH SERVICE ANALYTICS.PUBLIC.PRODUCT_SEARCH
    ON PRODUCT_NAME, DESCRIPTION, CATEGORY
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            PRODUCT_ID,
            PRODUCT_NAME,
            DESCRIPTION,
            CATEGORY,
            PRICE
        FROM ANALYTICS.MARTS.DIM_PRODUCTS
        WHERE IS_ACTIVE = TRUE
    );

-- Query it via SQL
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'ANALYTICS.PUBLIC.PRODUCT_SEARCH',
        '{
            "query": "wireless noise cancelling headphones",
            "columns": ["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PRICE"],
            "limit": 5
        }'
    )
) AS search_results;
```

The `TARGET_LAG = '1 hour'` parameter controls how quickly the search index reflects data changes. When new products are inserted into `DIM_PRODUCTS`, Snowflake will update the search index within one hour. This means there's a brief window where new products are queryable via SQL but not yet findable via Cortex Search. For most product catalogs, one hour is acceptable. For high-frequency update scenarios (real-time news feeds, support ticket systems), you might reduce this to minutes.

From Python, you can query the search service through the Snowflake Core SDK:

```python
from snowflake.core import Root

def search_products(session: Session, query: str) -> None:
    root = Root(session)
    search_service = (
        root
        .databases["ANALYTICS"]
        .schemas["PUBLIC"]
        .cortex_search_services["PRODUCT_SEARCH"]
    )

    response = search_service.search(
        query=query,
        columns=["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PRICE"],
        limit=5,
    )

    for item in response.results:
        print(f"  [{item['CATEGORY']}] {item['PRODUCT_NAME']} – ${item['PRICE']}")
```

This Python client is particularly useful in Streamlit apps where you want a search bar that returns semantically relevant results. A user typing "earphones for gym" in a search box can find products tagged as "Workout Earbuds" or "Sport Headphones" even without exact keyword overlap. This dramatically improves product discovery experiences.

### RAG Pipeline

The most powerful pattern combining Cortex Search and COMPLETE is RAG — Retrieval-Augmented Generation. The idea: rather than asking an LLM to answer questions from its training knowledge (which is static, potentially outdated, and may hallucinate), you first retrieve relevant documents from your database, then inject them as context into the LLM prompt. The LLM is now answering from your actual, current, authoritative data.

```python
def rag_pipeline(session: Session, user_question: str) -> str:
    root = Root(session)
    search_service = (
        root.databases["ANALYTICS"].schemas["PUBLIC"]
        .cortex_search_services["PRODUCT_SEARCH"]
    )

    # Step 1: Retrieve semantically relevant products
    search_response = search_service.search(
        query=user_question,
        columns=["PRODUCT_NAME", "DESCRIPTION", "CATEGORY", "PRICE"],
        limit=3,
    )

    # Step 2: Format retrieved documents as LLM context
    context_blocks = []
    for i, item in enumerate(search_response.results, start=1):
        context_blocks.append(
            f"Product {i}: {item['PRODUCT_NAME']} "
            f"(Category: {item['CATEGORY']}, Price: ${item['PRICE']})\n"
            f"{item['DESCRIPTION']}"
        )
    context_text = "\n\n".join(context_blocks)

    # Step 3: Augmented prompt with context + question
    augmented_prompt = f"""You are a helpful product assistant.
Use ONLY the product information below to answer the customer's question.
If the answer is not in the context, say "I don't have that information."

PRODUCT CONTEXT:
{context_text}

CUSTOMER QUESTION:
{user_question}

ANSWER:"""

    # Step 4: LLM generates grounded answer
    row = session.sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?) AS answer",
        params=[augmented_prompt]
    ).collect()[0]

    return row["ANSWER"]
```

The key instruction in the prompt — "Use ONLY the product information below" — is the grounding instruction. Without it, the LLM will supplement the retrieved context with its training knowledge, which may be outdated or incorrect. With it, the LLM is constrained to what you've provided. The fallback instruction "If the answer is not in the context, say I don't have that information" is equally important: it prevents the model from hallucinating an answer when the context doesn't contain the relevant information.

---

## 13.5 Document AI

Enterprises store enormous quantities of valuable structured data in unstructured documents: invoices with amounts and vendor names, contracts with parties and expiry dates, forms with addresses and identification numbers, medical records with diagnoses and prescriptions. Extracting this structured data from PDFs and images has traditionally required either manual data entry (expensive, slow, error-prone) or brittle rule-based OCR pipelines (break when document formats change, require constant maintenance).

Document AI is Snowflake's fine-tunable extraction model for documents. Rather than using a general-purpose document understanding model and hoping it understands your specific invoice format, Document AI lets you train a custom model on your actual documents. You label samples — "this region is the vendor name, this region is the invoice number, this region is the total" — and Snowflake trains a model that learns your specific document layout.

```python
def extract_from_invoices(session: Session) -> None:
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
        import json
        extraction = json.loads(row["EXTRACTION_RESULT"])
        print(f"File: {row['RELATIVE_PATH']}")
        print(f"  Vendor: {extraction.get('vendor_name', {}).get('value', 'N/A')}")
        print(f"  Invoice #: {extraction.get('invoice_number', {}).get('value', 'N/A')}")
        print(f"  Total: {extraction.get('total_amount', {}).get('value', 'N/A')}")
        print(f"  Due Date: {extraction.get('due_date', {}).get('value', 'N/A')}")
```

Document AI models are created in Snowsight's Document AI UI. You upload sample PDFs, use the labeling interface to draw bounding boxes around the fields you want to extract, assign labels to those boxes (vendor_name, invoice_number, total_amount, due_date), and submit for training. Snowflake recommends at least 20–50 labeled samples for good accuracy; more labeled samples improve accuracy particularly for documents with high layout variation. Once trained, the model is callable as a SQL function: `<database>.<schema>.<model_name>!PREDICT(presigned_url, model_version)`.

Each extracted field comes with a confidence score in the JSON output (not shown in the simplified example above). Build a downstream workflow that routes low-confidence extractions to manual review — "auto-approve extractions above 0.9 confidence, human-review below 0.7." Over time, human-reviewed low-confidence cases can become new labeled training examples, creating a virtuous cycle that improves model accuracy.

---

## 13.6 ML Functions: Forecasting and Anomaly Detection

### Time Series Forecasting

Building a time series forecasting model has traditionally been a data science project: acquire historical data, clean it, choose between ARIMA, Prophet, LSTM, or other approaches, tune hyperparameters, evaluate multiple models, deploy the winner, set up a serving API, and maintain all of it. This might take weeks of engineering time and requires specialized knowledge of time series statistics.

Snowflake ML FORECAST provides a no-code path to time series forecasting. You provide historical data (a timestamp column and a target column), and Snowflake trains an ensemble model that automatically handles trend, seasonality, and noise. The model is created as a Snowflake object and called with a SQL CALL statement.

```sql
-- Define the training data source
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.DAILY_REVENUE_FOR_FORECAST AS
SELECT
    ORDER_DATE,
    SUM(AMOUNT) AS DAILY_REVENUE
FROM ANALYTICS.MARTS.FCT_ORDERS
WHERE STATUS = 'COMPLETED'
GROUP BY ORDER_DATE
ORDER BY ORDER_DATE;

-- Create (train) the forecast model
CREATE OR REPLACE SNOWFLAKE.ML.FORECAST ANALYTICS.PUBLIC.REVENUE_FORECAST (
    INPUT_DATA        => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_REVENUE_FOR_FORECAST'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_REVENUE'
);

-- Generate 30-day forecast
CALL ANALYTICS.PUBLIC.REVENUE_FORECAST!FORECAST(
    FORECASTING_PERIODS => 30,
    CONFIG_OBJECT       => { 'prediction_interval': 0.9 }
);

-- Retrieve results
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) ORDER BY TS;
```

The `prediction_interval: 0.9` configuration creates 90% confidence bands around the forecast. The output contains three key columns: `TS` (the forecasted timestamp), `FORECAST` (the point estimate), `LOWER_BOUND` (the lower 90% confidence bound), and `UPPER_BOUND` (the upper 90% confidence bound). Interpreting confidence bands requires understanding what they mean: a 90% confidence interval means that if you were to run this forecasting process many times over different historical data samples, 90% of the resulting intervals would contain the true future value. In practical terms, it means "we're fairly confident the true value will fall in this range."

Wide confidence bands are a signal worth paying attention to. If the forecasted daily revenue for next month ranges from $50,000 to $500,000, the model is telling you that the business process has high inherent variability — or that there isn't enough historical data to identify stable patterns. In this case, using the forecast for capacity planning might be premature. Consider whether adding more historical data, higher-granularity data, or exogenous variables (holiday calendars, marketing spend, weather) would narrow the confidence bands to a useful range.

### Anomaly Detection

Where forecasting predicts future values, anomaly detection flags existing data points that don't fit the expected pattern. The use cases are broad: detecting unusual spikes in transaction volumes (fraud signals), identifying equipment sensor readings outside normal ranges (predictive maintenance), spotting unexpectedly low revenue days that might indicate pipeline failures, and catching data quality issues like sudden drops in a metric that should be monotonically increasing.

The key advantage over threshold-based alerting is that anomaly detection learns the seasonal pattern. A simple threshold of "alert if daily orders < 1,000" fires incorrectly on every low-traffic Sunday (where 800 orders is normal) and misses anomalies on Fridays (where 2,500 orders is normal but 1,500 orders would indicate a problem). Anomaly detection compares each data point to what was expected at that time, accounting for day-of-week patterns, monthly trends, and yearly seasonality.

```sql
-- Define the training data
CREATE OR REPLACE VIEW ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS AS
SELECT
    ORDER_DATE,
    COUNT(*)       AS DAILY_ORDERS,
    NULL::BOOLEAN  AS IS_ANOMALY   -- NULL = unsupervised mode
FROM ANALYTICS.MARTS.FCT_ORDERS
GROUP BY ORDER_DATE;

-- Create (train) the anomaly detector
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION ANALYTICS.PUBLIC.ORDER_ANOMALY_DETECTOR (
    INPUT_DATA        => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_ORDERS',
    LABEL_COLNAME     => 'IS_ANOMALY'   -- NULL = unsupervised mode
);

-- Detect anomalies in the data
CALL ANALYTICS.PUBLIC.ORDER_ANOMALY_DETECTOR!DETECT_ANOMALIES(
    INPUT_DATA        => SYSTEM$REFERENCE('VIEW', 'ANALYTICS.PUBLIC.DAILY_ORDER_COUNTS'),
    TIMESTAMP_COLNAME => 'ORDER_DATE',
    TARGET_COLNAME    => 'DAILY_ORDERS'
);

-- Show only the anomalous dates
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE IS_ANOMALY = TRUE
ORDER BY TS;
```

The `LABEL_COLNAME => 'IS_ANOMALY'` set to NULL enables unsupervised mode — the model learns what "normal" looks like purely from the statistical patterns in your data, without you needing to label historical anomalies. If you have labeled historical data (say, you've manually identified past incidents), you can provide those labels and use supervised mode, which typically produces more accurate detectors for your specific anomaly types.

The output includes `IS_ANOMALY` (boolean), `DISTANCE` (how far the point is from the expected range, in standard deviations), and `PERCENTILE` (where the point falls in the distribution of expected values). Use `DISTANCE` to triage detected anomalies: a point 5 standard deviations from normal demands immediate investigation; a point 2 standard deviations from normal might be monitored but not paged.

---

## Chapter 13 Summary

Cortex AI brings large language model capabilities and automated ML directly into Snowflake's SQL interface. COMPLETE provides flexible LLM access for any generative or analytical task; SENTIMENT, SUMMARIZE, TRANSLATE, and CLASSIFY_TEXT are pre-optimized functions for their specific tasks. EXTRACT_ANSWER implements document Q&A with context grounding. Cortex Search provides semantic similarity search with automatic embedding maintenance. Document AI enables fine-tuned extraction from structured document types. ML FORECAST and ANOMALY_DETECTION provide no-code time series intelligence. The unifying theme is governance: because all of these capabilities run inside Snowflake, data never leaves the warehouse's security perimeter, billing is unified through Snowflake credits, and all operations are logged in Snowflake's audit infrastructure.

Chapter 14 builds the governance layer that makes all of this scale safely: tagging, classification, masking policies, access history, and compliance audit patterns.

---

# Chapter 14: Data Governance

## 14.1 Why Governance Matters More in Snowflake

There is a paradox at the heart of modern data infrastructure. The better you are at enabling data access — more users, more tools, self-service SQL, embedded analytics, Streamlit apps, Cortex AI functions — the greater your governance surface area becomes. Every new analyst who can write SELECT queries against customer tables is another person who can access PII. Every new ML model trained on sensitive data is another data flow to track. Every new Streamlit app that surfaces customer information is another interface that could inadvertently expose data to the wrong audience.

Traditional data teams managed this paradox by becoming the bottleneck. Data requests flowed through a small team of trusted analysts who hand-delivered reports and dashboards. Governance was implicit in the process — you couldn't access the data without going through people who understood what should and shouldn't be shared. This worked when data access was slow and painful by nature. It is completely incompatible with the modern aspiration of self-service analytics, where the goal is enabling hundreds or thousands of people to answer their own questions instantly.

Snowflake Horizon is Snowflake's framework for governance that scales with self-service. The core insight is that governance must be in the platform, not in the process. When governance lives in a process ("the analytics team reviews all data requests"), it fails the moment the process is bypassed or the team is overwhelmed. When governance lives in the platform — as tag propagation rules, masking policies, row access policies, and audit logging — it applies automatically to every query, by every user, through every tool, regardless of whether the governance team is watching. The policy is enforced at query execution time by the Snowflake engine itself.

The shift this represents for data teams is substantial. Instead of manually reviewing data requests, the governance team designs policies: "any column tagged as PII_CATEGORY='SSN' is automatically masked for roles below DATA_GOVERNANCE_ROLE." Once that policy is in place, no manual review is needed for queries touching SSN columns — the masking happens automatically. The governance team moves from a reactive bottleneck ("please submit a data access request and we'll review it within 5 business days") to a proactive policy designer ("we set the rules, the platform enforces them").

---

## 14.2 Object Tagging: Metadata That Scales

Imagine being the data governance lead at a company with a Snowflake account that has grown organically over three years. There are 8,000 tables and 120,000 columns spread across 50 databases and 200 schemas. A GDPR request arrives: "provide a list of all columns that may contain EU residents' personal data." Without systematic metadata, answering this question requires manually reviewing table definitions, reading data dictionaries that may not exist or may be outdated, and interviewing the data engineers who built each pipeline. A task that should take an hour takes three weeks, requires involving eight different teams, and still produces a result you can't fully trust.

Snowflake Tags solve this problem by embedding machine-queryable metadata directly into the catalog. A tag is a key-value pair that you attach to any Snowflake object: databases, schemas, tables, columns, or even the account itself. Tags have a name (defined in the catalog), optional allowed values (enforcing a controlled vocabulary), and a value (what you're asserting about this specific object). When you tag a column with `PII_CATEGORY = 'EMAIL'`, that assertion is stored in Snowflake's metadata layer and is queryable via SQL from `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`.

```sql
-- Create your governance tag taxonomy
CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.PII_CATEGORY
    ALLOWED_VALUES 'EMAIL', 'PHONE', 'SSN', 'DOB', 'FULL_NAME', 'ADDRESS', 'NONE';

CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION
    ALLOWED_VALUES 'PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED';

CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.DATA_OWNER;

CREATE TAG IF NOT EXISTS ANALYTICS.GOVERNANCE.RETENTION_DAYS
    ALLOWED_VALUES '30', '90', '365', '2555', 'INDEFINITE';
```

The `ALLOWED_VALUES` constraint is important for governance consistency. Without it, one engineer might tag a column as `CONFIDENTIAL`, another as `confidential`, another as `Confidential`, and a fourth as `conf`. These all mean the same thing to a human but are completely different values to a computer. Your compliance audit query filtering for `DATA_CLASSIFICATION = 'CONFIDENTIAL'` would miss 75% of the tagged objects. Controlled vocabularies enforce consistent tagging across the organization.

```sql
-- Apply tags to columns
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN EMAIL
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'EMAIL',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'CONFIDENTIAL';

ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN SSN
    SET TAG ANALYTICS.GOVERNANCE.PII_CATEGORY     = 'SSN',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'RESTRICTED';

-- Apply tags to tables and schemas
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    SET TAG ANALYTICS.GOVERNANCE.DATA_OWNER    = 'customer-data-team',
            ANALYTICS.GOVERNANCE.RETENTION_DAYS = '365';

ALTER SCHEMA ANALYTICS.MARTS
    SET TAG ANALYTICS.GOVERNANCE.DATA_OWNER          = 'data-engineering',
            ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'INTERNAL';

ALTER SCHEMA ANALYTICS.RAW
    SET TAG ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION = 'RESTRICTED',
            ANALYTICS.GOVERNANCE.DATA_OWNER          = 'data-platform';
```

Tag propagation provides a powerful efficiency when tagging at the schema level: objects created in a tagged schema inherit the schema's tags. If you tag the ANALYTICS.RAW schema with `DATA_CLASSIFICATION = 'RESTRICTED'`, new tables added to that schema automatically carry the RESTRICTED classification. You don't need to tag each new table individually — the schema-level tag flows down. This inheritance model lets you apply governance policies at the appropriate level of granularity without overwhelming tag maintenance overhead.

After tagging, the audit query becomes trivial:

```sql
-- Find every PII column in the account — answers GDPR data mapping in seconds
SELECT
    TAG_DATABASE, TAG_SCHEMA, TAG_NAME, TAG_VALUE,
    OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME,
    COLUMN_NAME, DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME   = 'PII_CATEGORY'
  AND TAG_VALUE != 'NONE'
  AND DOMAIN     = 'COLUMN'
ORDER BY OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, COLUMN_NAME;

-- PII column count per table — identify highest-risk tables
SELECT
    OBJECT_DATABASE AS database_name,
    OBJECT_SCHEMA   AS schema_name,
    OBJECT_NAME     AS table_name,
    COUNT(COLUMN_NAME) AS pii_column_count,
    LISTAGG(TAG_VALUE, ', ') WITHIN GROUP (ORDER BY TAG_VALUE) AS pii_categories
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME   = 'PII_CATEGORY'
  AND TAG_VALUE != 'NONE'
  AND DOMAIN     = 'COLUMN'
GROUP BY 1, 2, 3
ORDER BY pii_column_count DESC;
```

For a GDPR Article 30 data mapping exercise (required for all organizations processing EU personal data), the second query produces the core of the required record of processing activities: which tables contain which types of personal data, organized by database and schema. What used to require weeks of manual documentation takes seconds to generate, and stays current as your data landscape evolves.

---

## 14.3 Automatic Data Classification

The value of the tagging framework above depends entirely on people actually tagging objects. In a large, fast-moving organization, this is harder than it sounds. Data engineers focused on delivering new pipelines may not take time to tag each column. New tables appear daily. Columns get renamed and repurposed. Manual tagging inevitably falls behind reality.

`SYSTEM$CLASSIFY_SCHEMA` uses ML to analyze both column names and sample data values to identify likely PII categories. It doesn't replace human judgment — it accelerates it. Rather than asking someone to manually review 50,000 columns, you run automatic classification and get back a prioritized list of high-confidence findings: "column CUST_EMAIL_ADDR in table USER_PROFILES has 0.97 probability of being an EMAIL field." A human reviewer can approve high-confidence suggestions with a single click and focus their attention on low-confidence suggestions that need genuine judgment.

```sql
-- Classify all tables in a schema (may take several minutes for large schemas)
SELECT SYSTEM$CLASSIFY_SCHEMA(
    'ANALYTICS.MARTS',
    {
        'auto_tag': true,
        'use_cortex_classification': true
    }
);

-- Preview classification suggestions before auto-applying tags
SELECT SYSTEM$CLASSIFY(
    'ANALYTICS.MARTS.DIM_CUSTOMERS',
    { 'use_cortex_classification': true }
);
```

With `auto_tag: true`, high-confidence suggestions are automatically applied as tags. With `auto_tag: false` (or without this parameter), the function returns suggestions for human review without modifying any tags. In a mature governance workflow, you might run with `auto_tag: false` first, review the suggestions in a governance meeting, then selectively apply tags — preserving human oversight over what gets tagged as PII. The `use_cortex_classification: true` parameter enables the ML-based approach (using Cortex models to analyze content patterns) rather than purely rule-based detection.

Build a periodic job — weekly or monthly — that runs `SYSTEM$CLASSIFY_SCHEMA` on your most active schemas and routes low-confidence suggestions to your data stewards for review. New columns added since the last classification run are automatically included. This creates a lightweight continuous governance process that catches new PII data as it enters the warehouse rather than discovering it during an audit.

---

## 14.4 Dynamic Data Masking

Tagging identifies what data is sensitive. Masking policies control who can see it. A masking policy is a Snowflake object that defines a transformation: given a column value and the querying user's role, what value should they see? Privileged users see the real value. Other users see a masked version.

```sql
-- Email masking: show first 2 chars + **** + domain to data scientists
-- show full value to governance roles, mask completely for everyone else
CREATE OR REPLACE MASKING POLICY ANALYTICS.GOVERNANCE.PII_STRING_MASK
    AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'DATA_GOVERNANCE_ROLE') THEN val
        WHEN CURRENT_ROLE() = 'DATA_SCIENTIST' THEN
            REGEXP_REPLACE(val, '(.{2}).*(@.*)', '\\1****\\2')
        ELSE '***MASKED***'
    END;

-- SSN masking: show only last 4 digits
CREATE OR REPLACE MASKING POLICY ANALYTICS.GOVERNANCE.SSN_MASK
    AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'DATA_GOVERNANCE_ROLE') THEN val
        ELSE 'XXX-XX-' || RIGHT(val, 4)
    END;

-- Attach to columns
ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN EMAIL
    SET MASKING POLICY ANALYTICS.GOVERNANCE.PII_STRING_MASK;

ALTER TABLE ANALYTICS.MARTS.DIM_CUSTOMERS
    MODIFY COLUMN SSN
    SET MASKING POLICY ANALYTICS.GOVERNANCE.SSN_MASK;
```

The masking policy is evaluated at query execution time, not at data ingestion time. The real data is stored unchanged in Snowflake's micro-partitions. When a query selects the EMAIL column, the masking policy function is applied to each value before the result is returned. This means: the same data, the same table, the same query returns different results depending on who is running it. A SYSADMIN querying `SELECT EMAIL FROM DIM_CUSTOMERS` sees `john.doe@example.com`. An analyst running the exact same query sees `jo****@example.com`. A business operations user sees `***MASKED***`. The transformation happens transparently inside the query engine — the analyst doesn't know there's a masking policy; they just see the masked value.

Tag-based masking is even more powerful for governance at scale. Instead of attaching a masking policy to each column individually, you attach it to a tag. Every column that carries that tag automatically gets the masking policy applied:

```sql
-- Any column tagged DATA_CLASSIFICATION = RESTRICTED is automatically masked
ALTER TAG ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION
    SET MASKING POLICY ANALYTICS.GOVERNANCE.TAG_BASED_MASK
    USING (ANALYTICS.GOVERNANCE.DATA_CLASSIFICATION);
```

With this pattern, adding the `DATA_CLASSIFICATION = 'RESTRICTED'` tag to a new column automatically activates masking. No additional ALTER COLUMN statement is needed. The governance team manages tags; masking follows automatically. New tables and columns added by data engineers automatically get appropriate protection as soon as they're tagged, without requiring a separate governance workflow step.

---

## 14.5 Access History and Data Lineage

Tagging and masking are preventive governance controls — they shape what users can see. Access history is a detective control — it tells you what actually happened. `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` logs every query that ran against the account, including which tables were read (base objects), which objects were written (modified objects), and crucially, which columns within those objects were accessed.

The "who accessed our customer PII last week" question is one that arises regularly: during post-breach investigations, during regulatory audits, when a security team receives an alert about unusual query patterns, or when a data owner wants to understand who is consuming their data. Without access history, this question is essentially unanswerable. With access history, it's a single query:

```sql
-- Which users accessed PII columns in the last 7 days?
SELECT
    ah.USER_NAME,
    ah.ROLE_NAME,
    ah.QUERY_START_TIME,
    ah.QUERY_ID,
    objs.value['objectName']::STRING   AS object_accessed,
    cols.value['columnName']::STRING   AS column_accessed
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY       ah,
LATERAL FLATTEN(INPUT => ah.OBJECTS_MODIFIED)     objs,
LATERAL FLATTEN(INPUT => objs.value['columns'])   cols
WHERE ah.QUERY_START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND cols.value['columnName']::STRING IN ('EMAIL', 'PHONE', 'SSN')
ORDER BY ah.QUERY_START_TIME DESC
LIMIT 100;

-- Access count by role and column over the last 30 days
SELECT
    ah.ROLE_NAME,
    cols.value['columnName']::STRING   AS sensitive_column,
    COUNT(*)                           AS access_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY       ah,
LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED) objs,
LATERAL FLATTEN(INPUT => objs.value['columns'])    cols
WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND cols.value['columnName']::STRING IN ('EMAIL', 'PHONE', 'SSN', 'FULL_NAME')
GROUP BY 1, 2
ORDER BY access_count DESC;
```

The `LATERAL FLATTEN` pattern deserves explanation because it's uncommon outside of Snowflake. `ACCESS_HISTORY` stores the list of objects and columns as JSON arrays in VARIANT columns. `LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED)` unnests that JSON array into rows — each element of the array becomes a separate row in the result. The second `LATERAL FLATTEN(INPUT => objs.value['columns'])` unnests the columns array within each object. The result is a flat table where each row represents one column access in one query. Understanding this pattern unlocks all of Snowflake's semi-structured metadata queries.

### Data Lineage

Data lineage — understanding where data came from and where it goes — is critical for impact analysis ("if I change table X, what downstream objects are affected?"), data quality debugging ("this metric is wrong; what upstream sources contributed to it?"), and compliance documentation ("prove that the customer data in this report came from our CRM, not from a third-party list purchase").

Lineage is reconstructed from access history using the pattern of reading one object and writing another in the same query:

```sql
-- What downstream objects read from DIM_CUSTOMERS?
SELECT DISTINCT
    src.value['objectName']::STRING  AS source_object,
    tgt.value['objectName']::STRING  AS target_object,
    ah.QUERY_ID,
    ah.QUERY_START_TIME,
    ah.USER_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY        ah,
LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED) src,
LATERAL FLATTEN(INPUT => ah.OBJECTS_MODIFIED)      tgt
WHERE src.value['objectName']::STRING ILIKE '%DIM_CUSTOMERS%'
  AND ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
ORDER BY ah.QUERY_START_TIME DESC
LIMIT 50;
```

This query identifies every MERGE, INSERT, CREATE TABLE AS SELECT, or other write operation that read from DIM_CUSTOMERS. By joining multiple time ranges of this query (or by processing the full history in a single pass), you can build a directed graph: DIM_CUSTOMERS → CUSTOMER_ORDER_ENRICHED → CHURN_PREDICTION_FEATURES → CHURN_PREDICTIONS. This graph tells you that if you change the schema of DIM_CUSTOMERS, CHURN_PREDICTIONS will be affected, and lets you trace exactly which transformations are in the path.

Automated lineage is what compliance and data quality teams ask for repeatedly and traditionally get only through manual documentation that becomes stale within weeks. The ACCESS_HISTORY approach gives you automated, always-current lineage derived from actual query behavior rather than from what engineers wrote in a README.

---

## 14.6 Security Audit Queries

### Failed Login Monitoring

PCI DSS requirement 10.2.4 requires logging all invalid logical access attempts. Snowflake captures this automatically in `LOGIN_HISTORY`. Your quarterly PCI evidence package includes a screenshot of this query and its results during the audit period:

```sql
-- Failed login attempts in the last 24 hours (PCI DSS 10.2.4)
SELECT
    EVENT_TIMESTAMP,
    USER_NAME,
    CLIENT_IP,
    ERROR_MESSAGE,
    REPORTED_CLIENT_TYPE,
    FIRST_AUTHENTICATION_FACTOR,
    SECOND_AUTHENTICATION_FACTOR
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
  AND IS_SUCCESS = 'NO'
ORDER BY EVENT_TIMESTAMP DESC;

-- Login frequency report: successful vs failed per user this month
SELECT
    USER_NAME,
    COUNT(*)                                       AS login_count,
    SUM(CASE WHEN IS_SUCCESS = 'YES' THEN 1 END)  AS successful,
    SUM(CASE WHEN IS_SUCCESS = 'NO'  THEN 1 END)  AS failed,
    MIN(EVENT_TIMESTAMP)                           AS first_login,
    MAX(EVENT_TIMESTAMP)                           AS last_login
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY USER_NAME
ORDER BY login_count DESC
LIMIT 10;
```

The `CLIENT_IP` column is particularly useful during an active investigation — if multiple failed logins are coming from an unusual IP address (not matching known office ranges or VPN ranges), that's a strong signal of brute force or credential stuffing. The `FIRST_AUTHENTICATION_FACTOR` and `SECOND_AUTHENTICATION_FACTOR` columns show what authentication methods were used in each attempt, which is useful for verifying MFA is functioning and for identifying attempts made without MFA.

### MFA Compliance

HIPAA requires multifactor authentication for access to systems containing electronic protected health information (ePHI). SOC 2 Type II requires evidence of MFA enforcement. Many enterprise security policies mandate MFA for all Snowflake users. The following query identifies users who represent a compliance gap:

```sql
-- Users without MFA — compliance risk
SELECT
    NAME            AS user_name,
    EMAIL,
    HAS_MFA,
    LOGIN_NAME,
    DEFAULT_ROLE,
    DISABLED,
    LAST_SUCCESS_LOGIN
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE HAS_MFA    = FALSE
  AND DISABLED   = FALSE
  AND DELETED_ON IS NULL
ORDER BY LAST_SUCCESS_LOGIN DESC NULLS FIRST;

-- Highest risk: active users without MFA who logged in recently
SELECT
    u.NAME,
    u.EMAIL,
    u.DEFAULT_ROLE,
    MAX(lh.EVENT_TIMESTAMP) AS last_login
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS        u
JOIN SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY lh
  ON lh.USER_NAME   = u.NAME
 AND lh.IS_SUCCESS  = 'YES'
 AND lh.EVENT_TIMESTAMP >= DATEADD('day', -30, CURRENT_TIMESTAMP())
WHERE u.HAS_MFA  = FALSE
  AND u.DISABLED = FALSE
GROUP BY 1, 2, 3
ORDER BY last_login DESC;
```

The second query is more actionable than the first. It surfaces users who are both missing MFA and actively using Snowflake — these are the highest-priority accounts to remediate because the vulnerability is being actively exercised. Users without MFA who haven't logged in for 90+ days are still a risk but a lower priority. Sort your remediation by last_login to focus attention where it matters most. Schedule this query as a daily Task and route the output to your security team's Slack channel or ticket system to create automatic compliance follow-up.

### Comprehensive Classification Report

The most valuable output from a governance framework is a single report that shows every tagged column alongside its classification, its data owner, and whether a masking policy is protecting it. This is the "missing masking policy" report — any column tagged as CONFIDENTIAL or RESTRICTED that doesn't have a masking policy is a governance gap:

```sql
SELECT
    tr.OBJECT_DATABASE                               AS database_name,
    tr.OBJECT_SCHEMA                                 AS schema_name,
    tr.OBJECT_NAME                                   AS table_name,
    tr.COLUMN_NAME,
    MAX(CASE WHEN tr.TAG_NAME = 'PII_CATEGORY'        THEN tr.TAG_VALUE END) AS pii_category,
    MAX(CASE WHEN tr.TAG_NAME = 'DATA_CLASSIFICATION' THEN tr.TAG_VALUE END) AS classification,
    MAX(CASE WHEN tr.TAG_NAME = 'DATA_OWNER'          THEN tr.TAG_VALUE END) AS data_owner,
    mp.POLICY_NAME                                   AS masking_policy
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES       tr
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES mp
    ON  mp.REF_DATABASE_NAME = tr.OBJECT_DATABASE
    AND mp.REF_SCHEMA_NAME   = tr.OBJECT_SCHEMA
    AND mp.REF_ENTITY_NAME   = tr.OBJECT_NAME
    AND mp.REF_COLUMN_NAME   = tr.COLUMN_NAME
    AND mp.POLICY_KIND       = 'MASKING_POLICY'
WHERE tr.DOMAIN = 'COLUMN'
GROUP BY 1, 2, 3, 4, mp.POLICY_NAME
ORDER BY 1, 2, 3, 4;
```

This query joins tag metadata with policy metadata to produce one row per tagged column. The `masking_policy` column is NULL for columns that have tags but no masking policy. A WHERE clause of `WHERE masking_policy IS NULL AND classification IN ('CONFIDENTIAL', 'RESTRICTED')` immediately surfaces your governance gaps: sensitive tagged columns with no data protection. Run this report monthly. The number of unprotected sensitive columns should be trending toward zero over time. If it's increasing, your tagging is outpacing your masking policy deployment and remediation action is needed.

### Setting Up the Governance Role

```sql
-- Create a dedicated governance role
CREATE ROLE IF NOT EXISTS DATA_GOVERNANCE_ROLE;

-- Grant read access to audit metadata
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE DATA_GOVERNANCE_ROLE;

-- Grant ability to manage tags and masking policies
GRANT USAGE ON DATABASE  ANALYTICS                     TO ROLE DATA_GOVERNANCE_ROLE;
GRANT USAGE ON SCHEMA    ANALYTICS.GOVERNANCE          TO ROLE DATA_GOVERNANCE_ROLE;
GRANT ALL   ON ALL TAGS  IN SCHEMA ANALYTICS.GOVERNANCE TO ROLE DATA_GOVERNANCE_ROLE;
GRANT ALL   ON ALL MASKING POLICIES IN SCHEMA ANALYTICS.GOVERNANCE TO ROLE DATA_GOVERNANCE_ROLE;

-- Allow governance role to apply tags to any object in the account
GRANT APPLY TAG ON ACCOUNT TO ROLE DATA_GOVERNANCE_ROLE;

-- Assign to governance admin users
GRANT ROLE DATA_GOVERNANCE_ROLE TO USER your_governance_admin;
```

`GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` gives the role access to `SNOWFLAKE.ACCOUNT_USAGE`, enabling all the audit queries described in this chapter. This privilege is powerful — it gives read access to query history, login history, access history, and all object metadata for the entire account. Assign it only to users with legitimate governance responsibilities, not to general analysts. The `GRANT APPLY TAG ON ACCOUNT` privilege allows the governance role to tag any object across any database in the account, enabling centralized governance without requiring the governance team to be ACCOUNTADMIN.

A separate `INFORMATION_SCHEMA` note for investigation versus reporting: `SNOWFLAKE.ACCOUNT_USAGE` views have up to three hours of latency but contain up to one year of history, making them appropriate for compliance reports, trend analysis, and monthly audits. `INFORMATION_SCHEMA.QUERY_HISTORY` has near-real-time data but only retains seven days of history, making it appropriate for active investigations ("what queries ran against this table in the last hour?"). Design your governance workflows to use the appropriate source — don't use ACCOUNT_USAGE for active incident response (the lag may hide recent activity), and don't build INFORMATION_SCHEMA queries that need to look back six months (the data won't be there).

---

## Chapter 14 Summary

Data governance in Snowflake is a layered system where each layer reinforces the others. Object tagging creates a machine-queryable metadata catalog that enables systematic identification of sensitive data at scale. Automatic classification accelerates tag coverage by applying ML to identify likely PII before human review. Dynamic data masking translates tag classifications into automatic data protection, enforced at query time regardless of how the data is accessed. Access history provides the audit trail that proves governance is working — who accessed what, when, with what role. The compliance audit queries translate these mechanisms into the specific evidence packages that regulated industries require.

The governance framework described in this chapter scales because it lives in the platform. When a new table is added to the RAW schema, it inherits the RESTRICTED classification tag. When the masking policy is attached to that tag, the new table's sensitive columns are automatically protected. When a new analyst is granted a role and queries the table, their access is logged in ACCESS_HISTORY. No manual intervention is required for any of these governance mechanisms to function. The governance team sets policy; Snowflake enforces it continuously.

This concludes Part 3 of the Snowflake Master Course. The four chapters in this section — Snowpark, Streamlit in Snowflake, Cortex AI, and Data Governance — represent the capabilities that distinguish a mature Snowflake deployment from a basic SQL data warehouse. Together, they enable data teams to build complete, governed, AI-enhanced data products that live entirely inside Snowflake's security and operational boundary.
