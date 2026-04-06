# Module 4: Apache Airflow -- Orchestration

> **What you'll learn:** Build production-grade DAGs, not toy examples. Airflow is the most in-demand orchestration tool in data engineering, and by the end of this module you'll know how to use it like a practitioner.

Airflow is the most in-demand orchestration tool in data engineering. Roughly 70% of DE job postings mention it. When you interview, they WILL ask about DAGs -- what they are, how you structure them, how you handle failures. This module gives you those answers with real code, not abstract theory.

---

## 4.1 Why Orchestration Matters (Cron Is Not Enough)

> **TL;DR**
> - Cron jobs can't handle dependencies, retries, visibility, or backfills
> - Orchestrators manage the *flow* of your pipeline, not just the timing
> - Airflow is the industry standard (~70% of DE job postings mention it)
> - Don't wait for a production incident to migrate off cron -- start with Airflow

### The 3 AM Failure Story

You've got a Python script. It pulls data from an API, transforms it, dumps it into Postgres. Works great. So you throw it on a cron job -- `0 6 * * *` -- runs every morning at 6 AM. Life is good.

Then one morning, the API is down at 6 AM. Your script fails silently. Nobody knows until 2 PM when the VP of Sales asks why the dashboard is empty. You SSH into the server, check the logs, re-run it manually. Crisis averted.

But then next week, your script runs fine, but the *downstream* dbt model that depends on it didn't wait -- it ran at 6:15 AM like it always does, but your script took 45 minutes instead of 10 because the API was slow. Now your dashboard has yesterday's data and nobody knows.

**That's** why cron is not enough.

### The Four Problems Orchestration Solves

Orchestration addresses four problems that cron simply can't:

1. **Dependencies** -- "Don't run step 3 until steps 1 and 2 are done." Cron doesn't know about dependencies. It just fires at a time.
2. **Retries and error handling** -- If something fails, retry it 3 times with a 5-minute delay. If it still fails, alert someone. Cron? It either ran or it didn't.
3. **Visibility** -- A UI where you can see: what ran, when, did it succeed, how long did it take, what's running right now. Cron gives you... log files. If you remembered to set up logging.
4. **Backfills** -- "The API was returning wrong data for the last 3 days. Re-run everything for those dates." With cron, you're writing bash scripts. With orchestration, it's a button click.

> **Key Concept: Orchestration vs. Scheduling**
>
> Cron is a *scheduler* -- it fires jobs at specific times. An orchestrator like Airflow is a *workflow manager* -- it manages the flow of tasks, their dependencies, retries, and state. Think of the difference between a kitchen timer and a head chef who coordinates every dish to arrive at the table together.

### The Orchestration Landscape (2025-2026)

The most common orchestrators you'll encounter:

- **Apache Airflow** -- the industry standard, and what we're learning
- **Prefect** -- newer, more Pythonic, gaining traction
- **Dagster** -- asset-centric, great developer experience
- **Mage** -- newer, notebook-style, gaining popularity

We're teaching Airflow because ~70% of job postings mention it and it's what you'll most likely encounter in the real world.

> **Common Mistake**
>
> People build a pipeline with cron, it works for 3 months, then they spend 2 weeks migrating to Airflow in a panic after a major incident. Just start with Airflow. The learning curve is worth it.

**At your job:** When you join a team, one of your first questions should be "What orchestrator do we use?" If the answer is "cron jobs on an EC2 instance," that's a red flag -- and an opportunity for you to propose a migration to Airflow.

### Checkpoint

1. Name two problems that cron can't solve but Airflow can.
2. What does "backfill" mean in the context of orchestration?
3. Why would you choose Airflow over Prefect or Dagster for a new job?

---

## 4.2 Airflow Architecture -- Scheduler, Webserver, Workers, Metadata DB

> **TL;DR**
> - Airflow has four components: Metadata DB, Scheduler, Webserver, and Workers
> - The Scheduler is the engine -- it decides what runs and when
> - The Webserver is just a UI; it doesn't execute tasks
> - Use LocalExecutor for learning and small-to-medium production workloads

Before you write a single line of DAG code, you need a mental model of what's actually happening when Airflow runs your pipeline.

### The Four Components

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Scheduler     │────>│  Metadata DB    │<────│   Webserver     │
│   (Engine)      │     │  (Postgres)     │     │   (Flask UI)    │
│                 │     │                 │     │                 │
│ * Parses DAGs   │     │ * DAG state     │     │ * DAG list      │
│ * Triggers      │     │ * Task state    │     │ * Logs          │
│ * Queues        │     │ * Connections   │     │ * Triggers      │
└────────┬────────┘     └─────────────────┘     └─────────────────┘
         │
         v
┌─────────────────┐
│    Workers       │
│   (Executor)     │
│                  │
│  Runs your       │
│  actual code     │
└──────────────────┘
```

**1. The Metadata Database (Postgres)**

This is Airflow's brain. It stores everything: what DAGs exist, when they last ran, what state each task is in, connections, variables, user info. It's just a Postgres database (or MySQL, but use Postgres).

Every other component reads from and writes to this database. If the metadata DB goes down, Airflow is dead.

**2. The Scheduler**

This is the engine. The scheduler does three things in a loop:
- Scans your DAG files to find new/updated DAGs
- Checks if any DAG runs need to be triggered (based on schedule)
- Checks if any tasks are ready to run (dependencies met) and queues them

The scheduler is the *only* component that decides what runs and when. It's the most critical piece.

**3. The Webserver**

This is the UI -- the thing you open in your browser. It reads from the metadata DB and shows you DAG status, task logs, Gantt charts, and trigger buttons.

Important: the webserver does NOT run your tasks. It's just a Flask app showing you what's happening. You could turn it off and Airflow would still run pipelines. You just couldn't see them.

**4. The Workers (Executor)**

This is where your actual code runs. When the scheduler says "run this task," a worker picks it up and executes it. How workers behave depends on your *executor*:

| Executor | Description | When to Use |
|----------|-------------|-------------|
| SequentialExecutor | One task at a time | Development only. Never production. |
| LocalExecutor | Multiple tasks as separate processes | Small-to-medium scale. What we'll use. |
| CeleryExecutor | Distributes across machines via Redis/RabbitMQ | Production at scale. |
| KubernetesExecutor | Spins up a K8s pod per task | Modern cloud-native deployments. |

**At your job:** Ask what executor is in use. If someone says SequentialExecutor in production, that's a problem -- it runs one task at a time. LocalExecutor is fine for most teams. CeleryExecutor or KubernetesExecutor for large-scale operations.

### Setting Up Airflow with Docker Compose

Here's a complete Docker Compose file for a local Airflow environment:

```yaml
# docker-compose.yaml
# Airflow with LocalExecutor -- suitable for learning and small-to-medium workloads
version: '3.8'

x-airflow-common: &airflow-common
  image: apache/airflow:2.9.1-python3.11
  environment: &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: LocalExecutor                  # Multiple tasks in parallel
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__FERNET_KEY: ''                            # Encryption key (set in prod)
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: 'true'      # New DAGs start paused
    AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
    AIRFLOW__API__AUTH_BACKENDS:
      'airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session'
    _PIP_ADDITIONAL_REQUIREMENTS: ${_PIP_ADDITIONAL_REQUIREMENTS:-}
  volumes:
    - ./dags:/opt/airflow/dags          # Your DAG files
    - ./logs:/opt/airflow/logs          # Task logs
    - ./plugins:/opt/airflow/plugins    # Custom plugins
    - ./data:/opt/airflow/data          # Data staging area
  user: "${AIRFLOW_UID:-50000}:0"
  depends_on:
    postgres:
      condition: service_healthy

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s
      retries: 5
      start_period: 5s
    ports:
      - "5432:5432"

  airflow-init:
    <<: *airflow-common
    entrypoint: /bin/bash
    command:
      - -c
      - |
        airflow db migrate
        airflow users create \
          --username admin \
          --firstname Admin \
          --lastname User \
          --role Admin \
          --email admin@example.com \
          --password admin
    depends_on:
      postgres:
        condition: service_healthy

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    healthcheck:
      test: ["CMD-SHELL", "airflow jobs check --job-type SchedulerJob --hostname $(hostname)"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    depends_on:
      airflow-init:
        condition: service_completed_successfully

volumes:
  postgres-data:
```

Start it up:

```bash
# Set the Airflow UID (avoids permission issues on mounted volumes)
echo -e "AIRFLOW_UID=$(id -u)" > .env

# Create the required directories
mkdir -p dags logs plugins data

# Start everything
docker compose up -d

# Check that everything is running
docker compose ps
```

Expected output:

```
NAME                    SERVICE              STATUS
airflow-init            airflow-init         exited (0)
airflow-scheduler       airflow-scheduler    running (healthy)
airflow-webserver       airflow-webserver    running (healthy)
postgres                postgres             running (healthy)
```

Open `http://localhost:8080` -- username `admin`, password `admin`. You'll see an empty DAGs page.

> **Common Mistake**
>
> **Not setting AIRFLOW_UID** -- you'll get permission errors on the mounted volumes. Always create the `.env` file first.
>
> **Using SequentialExecutor in production** -- it runs one task at a time. Fine for dev, disaster for prod.
>
> **Forgetting `LOAD_EXAMPLES: 'false'`** -- you'll get 30+ example DAGs cluttering your UI.

### Checkpoint

1. Which component decides what tasks to run and when?
2. What happens if the metadata database goes down?
3. Why should you never use SequentialExecutor in production?

---

## 4.3 Your First DAG -- Tasks, Dependencies, Operators

> **TL;DR**
> - A DAG is a Directed Acyclic Graph -- your pipeline definition
> - Tasks are units of work; Operators define the *type* of task
> - The `>>` operator defines dependencies between tasks
> - Always set `catchup=False` during development

Time to write some code. By the end of this section, you'll have a working DAG in Airflow -- not a "hello world," but an actual pipeline that does something useful.

### What a DAG Actually Is

Before you see the code, let's understand the concept. DAG stands for **Directed Acyclic Graph**. Let's break that down:

- **Graph** -- a collection of nodes (tasks) connected by edges (dependencies)
- **Directed** -- the edges have a direction. Task A runs *before* Task B, not the other way around. (A -> B)
- **Acyclic** -- there are no loops. You can't have A -> B -> C -> A. Why? Because if A depends on C, and C depends on B, and B depends on A, nothing can ever start. It's a deadlock.

**Why "acyclic" matters in interviews:** Interviewers love asking "what does DAG stand for and why does 'acyclic' matter?" The answer is: cycles create deadlocks. If Task A waits for Task C, and Task C waits for Task B, and Task B waits for Task A, your pipeline never runs. Airflow validates this at parse time and rejects any DAG with cycles.

> **Key Concept: DAG Terminology**
>
> - **DAG** = Directed Acyclic Graph. Your pipeline definition -- what tasks to run and in what order.
> - **Task** = A single unit of work. "Extract data from API," "Transform the data," "Load into Postgres."
> - **Operator** = The *type* of task. `PythonOperator` runs a Python function. `BashOperator` runs a bash command. `PostgresOperator` runs SQL.
> - **Task Instance** = A specific run of a task at a specific time. Your "extract" task on February 19th at 6 AM is one task instance.

### Building an ETL DAG

This DAG will:
1. Create a JSON file with sample data (simulating an API extraction)
2. Validate the data quality
3. Transform it to CSV with computed fields
4. Create a Postgres table
5. Send a notification

Save this as `dags/my_first_dag.py`:

```python
"""
My First Airflow DAG
Demonstrates: tasks, dependencies, operators, and basic patterns.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
import csv
import os

# Default arguments applied to all tasks in this DAG
default_args = {
    "owner": "george",                  # Who owns this DAG
    "depends_on_past": False,           # Don't wait for previous runs to succeed
    "email_on_failure": False,          # We'll use callbacks instead
    "email_on_retry": False,
    "retries": 2,                       # Retry failed tasks twice
    "retry_delay": timedelta(minutes=2),  # Wait 2 min between retries
}

DATA_PATH = "/opt/airflow/data"


def extract_data(**kwargs):
    """Simulate extracting data from an API.
    In production, this would be requests.get("https://api.example.com/orders")
    """
    import json

    orders = [
        {"order_id": 1, "customer": "Alice", "amount": 99.99, "date": "2026-02-19"},
        {"order_id": 2, "customer": "Bob", "amount": 149.50, "date": "2026-02-19"},
        {"order_id": 3, "customer": "Charlie", "amount": 29.99, "date": "2026-02-19"},
        {"order_id": 4, "customer": "Diana", "amount": 199.00, "date": "2026-02-19"},
        {"order_id": 5, "customer": "Eve", "amount": 75.25, "date": "2026-02-19"},
    ]

    filepath = os.path.join(DATA_PATH, "raw_orders.json")
    with open(filepath, "w") as f:
        json.dump(orders, f)

    print(f"Extracted {len(orders)} orders to {filepath}")
    return filepath


def validate_data(**kwargs):
    """Check data quality before loading."""
    import json

    filepath = os.path.join(DATA_PATH, "raw_orders.json")
    with open(filepath, "r") as f:
        orders = json.load(f)

    # Quality checks
    assert len(orders) > 0, "No orders found!"
    for order in orders:
        assert "order_id" in order, f"Missing order_id in {order}"
        assert "amount" in order, f"Missing amount in {order}"
        assert order["amount"] > 0, f"Invalid amount: {order['amount']}"

    print(f"Validation passed: {len(orders)} orders, all valid")
    return len(orders)


def transform_data(**kwargs):
    """Transform raw data into a clean CSV for loading."""
    import json

    filepath = os.path.join(DATA_PATH, "raw_orders.json")
    with open(filepath, "r") as f:
        orders = json.load(f)

    # Add computed fields
    for order in orders:
        order["amount_with_tax"] = round(order["amount"] * 1.08, 2)
        order["processed_at"] = datetime.now().isoformat()

    # Write as CSV for Postgres COPY
    csv_path = os.path.join(DATA_PATH, "clean_orders.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
        writer.writeheader()
        writer.writerows(orders)

    print(f"Transformed {len(orders)} orders -> {csv_path}")
    return csv_path


# Define the DAG
with DAG(
    dag_id="my_first_pipeline",
    default_args=default_args,
    description="Extract, validate, transform, and load order data",
    schedule="@daily",                      # Runs once per day
    start_date=datetime(2026, 2, 1),
    catchup=False,                          # Don't backfill past dates
    tags=["tutorial", "etl"],
) as dag:

    extract = PythonOperator(
        task_id="extract_data",
        python_callable=extract_data,
    )

    validate = PythonOperator(
        task_id="validate_data",
        python_callable=validate_data,
    )

    transform = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    create_table = PostgresOperator(
        task_id="create_table",
        postgres_conn_id="postgres_default",
        sql="""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer VARCHAR(100),
                amount DECIMAL(10,2),
                date DATE,
                amount_with_tax DECIMAL(10,2),
                processed_at TIMESTAMP
            );
        """,
    )

    notify = BashOperator(
        task_id="notify_complete",
        bash_command='echo "Pipeline complete at $(date). Orders loaded successfully!"',
    )

    # Define dependencies -- this is the "graph" part of DAG
    extract >> validate >> transform >> create_table >> notify
```

> **Companion code:** See `modules/module-4/starter/dags/my_first_dag.py` for the starter skeleton with TODOs, and `modules/module-4/solution/dags/my_first_dag.py` for the complete solution.

Expected output (in Airflow task logs):

```
[extract_data] Extracted 5 orders to /opt/airflow/data/raw_orders.json
[validate_data] Validation passed: 5 orders, all valid
[transform_data] Transformed 5 orders -> /opt/airflow/data/clean_orders.csv
[notify_complete] Pipeline complete at Thu Feb 19 06:00:00 UTC 2026. Orders loaded successfully!
```

### Key Concepts Breakdown

`default_args` -- Applied to every task. `retries: 2` means if a task fails, Airflow tries again twice. `retry_delay` is the wait between retries.

`schedule="@daily"` -- Runs once per day. You can also use cron syntax: `"0 6 * * *"` for 6 AM daily.

`catchup=False` -- If your `start_date` is in the past and catchup is True, Airflow tries to run the DAG for every day since start_date. That's usually not what you want during development.

`>>` -- The bitshift operator defines dependencies. `extract >> validate` means "run extract first, then validate."

### Verify Your DAG

```bash
# Check that Airflow can parse your DAG (catches syntax errors)
docker compose exec airflow-scheduler airflow dags list
```

Expected output:

```
dag_id              | filepath           | owner   | paused
====================|====================|=========|=======
my_first_pipeline   | my_first_dag.py    | george  | True
```

Then go to the Airflow UI, find `my_first_pipeline`, unpause it, and trigger it manually. Watch the tasks go green one by one in the Graph view.

> **Common Mistake**
>
> **Import errors at the top level** -- If your DAG file has an import error, the ENTIRE file is silently skipped. Always verify with `airflow dags list`.
>
> **Heavy logic at module level** -- Don't do API calls or DB queries outside your task functions. The scheduler reads your DAG file every 30 seconds. A `requests.get()` at the top level hits the API every 30 seconds.
>
> **Forgetting `catchup=False`** -- You'll trigger hundreds of backfill runs and wonder why your Airflow is on fire.

**At your job:** When you see a DAG file for the first time, look at three things: (1) the schedule, (2) the dependencies (the `>>` chain), and (3) the default_args (especially retries and timeout). Those tell you 80% of what you need to know.

### Try It Yourself

Modify the DAG to add a sixth task that counts the rows in the CSV file and prints the total revenue. Chain it after `transform` but before `create_table`.

### Checkpoint

1. What does "acyclic" mean in DAG, and why does it matter?
2. What happens if you forget to set `catchup=False` with a `start_date` in the past?
3. Where should heavy logic (API calls, DB queries) live -- at the module level or inside task functions?

---

## 4.4 TaskFlow API -- The Modern Way to Write DAGs

> **TL;DR**
> - The TaskFlow API uses `@task` decorators instead of explicit Operator objects
> - Return values automatically become XComs (cross-task communication)
> - Dependencies are inferred from function calls -- no `>>` needed
> - XCom is for small data only (configs, paths, counts) -- never DataFrames

The DAG we just wrote works, but it's kind of verbose. Defining `PythonOperator` separately, passing `python_callable`, managing data between tasks with file paths... There's a cleaner way. Airflow 2.0 introduced the TaskFlow API, and once you use it, you'll never go back.

### The TaskFlow Rewrite

```python
"""
TaskFlow API version of our pipeline.
Cleaner, more Pythonic, and handles data passing automatically.
"""
from datetime import datetime, timedelta
from airflow.decorators import dag, task
import json
import os

DATA_PATH = "/opt/airflow/data"


@dag(
    dag_id="taskflow_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 2, 1),
    catchup=False,
    default_args={
        "owner": "george",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["tutorial", "taskflow"],
)
def my_taskflow_pipeline():
    """An ETL pipeline using the TaskFlow API."""

    @task()
    def extract() -> list[dict]:
        """Extract orders from source (simulated)."""
        orders = [
            {"order_id": 1, "customer": "Alice", "amount": 99.99, "date": "2026-02-19"},
            {"order_id": 2, "customer": "Bob", "amount": 149.50, "date": "2026-02-19"},
            {"order_id": 3, "customer": "Charlie", "amount": 29.99, "date": "2026-02-19"},
            {"order_id": 4, "customer": "Diana", "amount": 199.00, "date": "2026-02-19"},
            {"order_id": 5, "customer": "Eve", "amount": 75.25, "date": "2026-02-19"},
        ]
        print(f"Extracted {len(orders)} orders")
        return orders  # Automatically stored as XCom

    @task()
    def validate(orders: list[dict]) -> list[dict]:
        """Validate data quality."""
        assert len(orders) > 0, "No orders!"
        for order in orders:
            assert order["amount"] > 0, f"Bad amount: {order['amount']}"
        print(f"Validated {len(orders)} orders -- all clean")
        return orders  # Pass along to next task

    @task()
    def transform(orders: list[dict]) -> list[dict]:
        """Add computed fields."""
        for order in orders:
            order["amount_with_tax"] = round(order["amount"] * 1.08, 2)
            order["processed_at"] = datetime.now().isoformat()
        print(f"Transformed {len(orders)} orders")
        return orders

    @task()
    def load(orders: list[dict]):
        """Load into destination (simulated)."""
        filepath = os.path.join(DATA_PATH, "final_orders.json")
        with open(filepath, "w") as f:
            json.dump(orders, f, indent=2)
        print(f"Loaded {len(orders)} orders to {filepath}")

    # Just call functions -- Airflow infers dependencies from data flow
    raw_data = extract()
    validated_data = validate(raw_data)
    transformed_data = transform(validated_data)
    load(transformed_data)


# Don't forget this line! Instantiates the DAG.
my_taskflow_pipeline()
```

> **Companion code:** See `modules/module-4/solution/dags/taskflow_pipeline.py` for the complete solution.

Expected output (task logs):

```
[extract] Extracted 5 orders
[validate] Validated 5 orders -- all clean
[transform] Transformed 5 orders
[load] Loaded 5 orders to /opt/airflow/data/final_orders.json
```

### Old Style vs. TaskFlow -- Side by Side

| Old Style | TaskFlow |
|-----------|----------|
| Define function separately | Decorate function with `@task` |
| Create `PythonOperator(python_callable=func)` | Just call the function |
| Manual XCom push/pull | Return values = automatic XCom |
| `extract >> validate >> transform` | `validate(extract())` -- implicit |

### Understanding XCom (Cross-Communication)

> **Key Concept: XCom**
>
> XCom is how tasks pass data to each other. With TaskFlow, return values are automatically serialized to JSON and stored in the metadata database. The next task receives them as function arguments. Simple.
>
> **Size limits matter:** XCom stores data in Postgres. Small data (configs, file paths, row counts, small lists) is perfect. Large data (DataFrames, millions of rows) will either crash your metadata DB or make it enormous. For large datasets, write to a file and pass the *path* via XCom.

> **Common Mistake**
>
> **Passing DataFrames through XCom** -- A 1GB DataFrame serialized to JSON in Postgres is a recipe for disaster. Pass file paths instead.
>
> **Forgetting to instantiate the DAG** -- See that last line `my_taskflow_pipeline()`? Without it, the DAG won't appear. Easy to miss.

**At your job:** Most modern Airflow codebases use TaskFlow for Python-based tasks. If you see a legacy codebase with the old `PythonOperator` style, it works fine -- but new DAGs should use TaskFlow.

### Checkpoint

1. What does `@task()` replace in the old-style DAG definition?
2. Why shouldn't you pass a Pandas DataFrame through XCom?
3. What happens if you forget the `my_taskflow_pipeline()` call at the bottom?

---

## 4.5 Connections, Variables, and Secrets Management

> **TL;DR**
> - Use **Connections** for external credentials (databases, APIs, cloud)
> - Use **Variables** for non-sensitive config (thresholds, paths, flags)
> - Never call `Variable.get()` at the module level -- put it inside tasks
> - In production, use a secrets backend (AWS Secrets Manager, Vault, etc.)

Pop quiz: what's the fastest way to get fired as a data engineer? Hardcode your database password in a DAG file and push it to GitHub. Let's talk about how to manage credentials properly.

### Connections -- External System Credentials

```bash
# Set via CLI
docker compose exec airflow-scheduler airflow connections add 'postgres_warehouse' \
    --conn-type 'postgres' \
    --conn-host 'postgres' \
    --conn-schema 'warehouse' \
    --conn-login 'warehouse_user' \
    --conn-password 'warehouse_pass' \
    --conn-port 5432

# Or via environment variable (useful for Docker/K8s)
export AIRFLOW_CONN_POSTGRES_WAREHOUSE='postgresql://warehouse_user:warehouse_pass@postgres:5432/warehouse'
```

Then use it in your DAG:

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

@task()
def query_warehouse():
    # The Hook looks up credentials from the connection by ID
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")
    df = hook.get_pandas_df("SELECT COUNT(*) as cnt FROM orders")
    print(f"Row count: {df['cnt'].iloc[0]}")
    return df['cnt'].iloc[0]
```

### Variables -- Non-Sensitive Configuration

```python
from airflow.models import Variable

@task()
def check_threshold():
    # Variable.get() queries the metadata DB
    threshold = int(Variable.get("my_threshold", default_var=50))
    print(f"Using threshold: {threshold}")
```

Set variables via CLI: `airflow variables set my_threshold 100`

> **Common Mistake: Variable.get() at Module Level**
>
> The scheduler parses DAG files every 30 seconds. If `Variable.get()` is at the top level, that's a database query every 30 seconds per DAG.
>
> ```python
> # BAD -- runs every time scheduler parses the file (every 30 seconds)
> threshold = Variable.get("my_threshold")
>
> @task()
> def my_task():
>     # GOOD -- runs only when the task executes
>     threshold = Variable.get("my_threshold")
> ```

### Secrets Backend -- For Production

In production, use an external secrets manager instead of storing credentials in the Airflow metadata DB:

```bash
# In airflow.cfg or environment variables:
AIRFLOW__SECRETS__BACKEND=airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend
AIRFLOW__SECRETS__BACKEND_KWARGS={"connections_prefix": "airflow/connections", "variables_prefix": "airflow/variables"}
```

This pulls secrets from AWS Secrets Manager, HashiCorp Vault, or GCP Secret Manager transparently. Your DAG code doesn't change -- Airflow just looks up the credentials from a different place.

> **Pro Tip:** Use the "Test" button in the Airflow UI when setting up connections. It validates the connection immediately and saves you debugging time later.

**At your job:** On day one, ask where credentials are stored. If they're in environment variables on the Airflow server, that's okay for small teams. If they're hardcoded in DAG files, that's a security incident waiting to happen. Push for a secrets backend.

### Checkpoint

1. What's the difference between a Connection and a Variable in Airflow?
2. Why is `Variable.get()` at the module level dangerous?
3. What's a secrets backend, and when should you use one?

---

## 4.6 Error Handling -- Retries, SLAs, Alerting

> **TL;DR**
> - Always configure retries with exponential backoff for external calls
> - Set `execution_timeout` on every task to prevent stuck jobs
> - Use callbacks for Slack/PagerDuty alerts on final failure
> - SLA monitoring alerts you if a DAG isn't done by a deadline

Data pipelines break. APIs go down, databases timeout, files are malformed, services hit rate limits. The question isn't IF your pipeline will fail, it's HOW it handles failure.

### Retries with Exponential Backoff

```python
@task(
    retries=3,                                  # Try 3 more times after first failure
    retry_delay=timedelta(minutes=5),           # Start with 5 min delay
    retry_exponential_backoff=True,             # 5 min -> 10 min -> 20 min
    max_retry_delay=timedelta(minutes=30),
)
def flaky_api_call():
    """Call an API that sometimes fails."""
    import requests
    response = requests.get("https://api.example.com/data", timeout=30)
    response.raise_for_status()  # Raises on 4xx/5xx
    return response.json()
```

> **Pro Tip:** `retry_exponential_backoff=True` is essential for API calls. If an API is overloaded, hammering it every 5 minutes makes things worse. Exponential backoff gives it time to recover.

### Timeouts

```python
@task(
    execution_timeout=timedelta(minutes=30),  # Kill task if it runs > 30 min
)
def long_running_transform():
    """Transform that should complete in 30 minutes."""
    # ... processing code ...
    pass
```

Without a timeout, a stuck task can block your entire pipeline for hours.

### Alerting with Callbacks

This is how you actually get notified when things go wrong:

```python
from airflow.decorators import dag, task
from airflow.models import Variable
from datetime import datetime, timedelta
import requests


def send_slack_alert(context):
    """Send a Slack notification on task failure."""
    task_instance = context.get("task_instance")
    dag_id = context.get("dag").dag_id
    task_id = task_instance.task_id
    log_url = task_instance.log_url

    message = (
        f"*Task Failed*\n"
        f"DAG: `{dag_id}`\n"
        f"Task: `{task_id}`\n"
        f"Execution: {context.get('execution_date')}\n"
        f"<{log_url}|View Logs>"
    )

    webhook_url = Variable.get("slack_webhook_url")
    requests.post(webhook_url, json={"text": message})


def send_success_notification(context):
    """Notify on DAG success."""
    dag_id = context.get("dag").dag_id
    webhook_url = Variable.get("slack_webhook_url")
    requests.post(webhook_url, json={
        "text": f"DAG `{dag_id}` completed successfully!"
    })


@dag(
    dag_id="alerting_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 2, 1),
    catchup=False,
    default_args={
        "owner": "george",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "on_failure_callback": send_slack_alert,      # Per-task failure alert
    },
    on_success_callback=send_success_notification,     # DAG-level success
)
def alerting_pipeline():

    @task()
    def risky_extraction():
        """This might fail -- and that's okay, we have retries and alerts."""
        import random
        if random.random() < 0.3:
            raise Exception("API rate limited! (simulated)")
        return {"status": "success", "rows": 1000}

    @task()
    def process(data: dict):
        print(f"Processing {data['rows']} rows")

    data = risky_extraction()
    process(data)


alerting_pipeline()
```

### SLA Monitoring

SLAs alert you when a DAG isn't done by a certain time -- critical for the CFO's morning report that better be ready by 7 AM:

```python
@task(sla=timedelta(hours=1))  # Must complete within 1 hour of DAG start
def critical_task():
    pass
```

> **Common Mistake**
>
> **No retries on API calls** -- Always add retries. External APIs are unreliable.
>
> **No execution_timeout** -- A stuck task can silently block everything for hours.
>
> **Alerting on every retry** -- Don't spam Slack on retries. The `on_failure_callback` fires only on *final* failure (after all retries), which is the right behavior.

**At your job:** The first thing to set up on any production DAG is alerting. A pipeline that fails silently is worse than one that fails loudly. Slack alerts with log URLs are the minimum. PagerDuty for critical pipelines.

### Checkpoint

1. What does `retry_exponential_backoff=True` do, and why is it useful for API calls?
2. What's the difference between `on_failure_callback` on `default_args` vs. on the `@dag` decorator?
3. Why should you always set `execution_timeout`?

---

## 4.7 Dynamic DAGs and DAG Factories

> **TL;DR**
> - DAG factories generate multiple DAGs from a config -- no copy-pasting
> - Dynamic task mapping (`.expand()`) creates parallel tasks at runtime
> - Use factory functions (not bare loops) to avoid Python closure issues
> - Don't generate more than ~200 DAGs from a factory or you'll slow the scheduler

If you work at a company with 50 clients and each one gets the same ETL pipeline with different configs, you're not going to copy-paste a DAG file 50 times. You're going to use a DAG factory.

### Pattern 1: Config-Driven DAGs

```python
"""
dags/dag_factory.py
Generate one DAG per client from a configuration list.
"""
from datetime import datetime, timedelta
from airflow.decorators import dag, task

# Config could come from a file, database, or API
CLIENTS = [
    {
        "client_id": "acme_corp",
        "api_url": "https://api.acme.com/v1/orders",
        "schedule": "0 6 * * *",         # 6 AM daily
        "owner": "george",
    },
    {
        "client_id": "globex",
        "api_url": "https://api.globex.com/v2/data",
        "schedule": "0 8 * * *",         # 8 AM daily
        "owner": "george",
    },
    {
        "client_id": "initech",
        "api_url": "https://initech.io/api/reports",
        "schedule": "0 7 * * 1-5",       # 7 AM weekdays only
        "owner": "george",
    },
]


def create_client_dag(client_config: dict):
    """Factory function that creates a DAG for a single client."""

    client_id = client_config["client_id"]

    @dag(
        dag_id=f"client_pipeline_{client_id}",
        schedule=client_config["schedule"],
        start_date=datetime(2026, 2, 1),
        catchup=False,
        default_args={
            "owner": client_config["owner"],
            "retries": 3,
            "retry_delay": timedelta(minutes=5),
        },
        tags=["client", client_id],
    )
    def client_pipeline():

        @task()
        def extract(api_url: str) -> dict:
            print(f"Extracting from {api_url}")
            return {"client": client_id, "rows": 100}  # Simulated

        @task()
        def transform(data: dict) -> dict:
            data["transformed"] = True
            data["processed_at"] = datetime.now().isoformat()
            return data

        @task()
        def load(data: dict):
            print(f"Loading {data['rows']} rows for {data['client']}")

        raw = extract(api_url=client_config["api_url"])
        clean = transform(raw)
        load(clean)

    return client_pipeline()


# Generate a DAG for each client
for client in CLIENTS:
    create_client_dag(client)
```

When Airflow parses this file, it creates three DAGs: `client_pipeline_acme_corp`, `client_pipeline_globex`, and `client_pipeline_initech`. Each with its own schedule and config.

> **Companion code:** See `modules/module-4/solution/dags/dag_factory.py` for the complete solution.

### Pattern 2: Dynamic Task Mapping (Airflow 2.3+)

This is even more powerful -- expand tasks dynamically at runtime:

```python
@dag(
    dag_id="dynamic_mapping_example",
    schedule="@daily",
    start_date=datetime(2026, 2, 1),
    catchup=False,
)
def dynamic_pipeline():

    @task()
    def get_files() -> list[str]:
        """Discover files to process -- could be from S3, API, etc."""
        return ["file_a.csv", "file_b.csv", "file_c.csv"]

    @task()
    def process_file(filename: str) -> dict:
        """Process a single file."""
        print(f"Processing {filename}")
        return {"file": filename, "rows": 1000}

    @task()
    def summarize(results: list[dict]):
        """Aggregate results."""
        total = sum(r["rows"] for r in results)
        print(f"Total rows processed: {total}")

    files = get_files()
    # .expand() creates one task instance per item in the list -- in parallel!
    results = process_file.expand(filename=files)
    summarize(results)


dynamic_pipeline()
```

The `.expand()` call is the magic. If `get_files()` returns 3 files, Airflow creates 3 parallel `process_file` tasks. If tomorrow it returns 10 files, you get 10 tasks. No code changes needed.

> **Common Mistake**
>
> **Creating DAGs in a loop with mutable variables** -- Classic Python closure issue. Always use a factory function (like `create_client_dag` above) to capture the config properly.
>
> **Too many dynamic DAGs** -- 500 DAGs from a factory will slow down the scheduler. If you have that many, consider grouping them.

**At your job:** DAG factories are extremely common at companies with multi-tenant data -- one client per DAG, one data source per DAG, etc. If you see 50 nearly-identical DAG files, suggest a factory pattern.

### Checkpoint

1. Why do you need a factory *function* instead of creating DAGs directly in a loop?
2. What does `.expand()` do in dynamic task mapping?
3. At what point should you worry about having too many factory-generated DAGs?

---

## 4.8 Sensors and Triggers -- Waiting for Data and Events

> **TL;DR**
> - Sensors wait for a condition to be true before allowing downstream tasks to run
> - Always use `mode="reschedule"` or `deferrable=True` to avoid hogging worker slots
> - Always set a `timeout` -- sensors without timeouts wait forever
> - `soft_fail=True` marks as skipped instead of failed on timeout

What if your pipeline shouldn't run at 6 AM -- it should run when the data is *ready*? Maybe a vendor uploads a file to S3 sometime between 6 AM and 9 AM. A schedule won't work. You need a sensor.

> **Key Concept: Sensors**
>
> A sensor is a special type of operator that periodically checks ("pokes") for a condition. When the condition is met, it succeeds and allows downstream tasks to proceed. Think of it as a bouncer checking IDs -- nobody gets in until the condition is verified.

```python
from airflow.sensors.filesystem import FileSensor
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.sensors.external_task import ExternalTaskSensor
from datetime import datetime, timedelta
from airflow.decorators import dag, task


@dag(
    dag_id="sensor_pipeline",
    schedule="0 6 * * *",
    start_date=datetime(2026, 2, 1),
    catchup=False,
)
def sensor_pipeline():

    # Wait for a local file to appear
    wait_for_file = FileSensor(
        task_id="wait_for_file",
        filepath="/opt/airflow/data/incoming/daily_feed.csv",
        poke_interval=60,               # Check every 60 seconds
        timeout=3 * 60 * 60,            # Give up after 3 hours
        mode="reschedule",              # Free up the worker slot while waiting
        soft_fail=True,                 # Mark as skipped (not failed) on timeout
    )

    # Wait for a file in S3
    wait_for_s3 = S3KeySensor(
        task_id="wait_for_s3_file",
        bucket_name="my-data-lake",
        bucket_key="raw/{{ ds }}/orders.parquet",  # Jinja template for date
        aws_conn_id="aws_default",
        poke_interval=120,
        timeout=4 * 60 * 60,
        mode="reschedule",
    )

    # Wait for another DAG to finish
    wait_for_upstream = ExternalTaskSensor(
        task_id="wait_for_ingestion_dag",
        external_dag_id="data_ingestion_pipeline",
        external_task_id=None,          # None = wait for the entire DAG
        timeout=2 * 60 * 60,
        mode="reschedule",
    )

    @task()
    def process():
        print("All conditions met -- processing!")

    [wait_for_file, wait_for_s3, wait_for_upstream] >> process()


sensor_pipeline()
```

### Key Parameters

- `poke_interval` -- How often to check (seconds). Don't set too low or you'll hammer the external system.
- `timeout` -- Maximum wait time. After this, the sensor fails (or skips if `soft_fail=True`).
- `mode="reschedule"` -- Frees the worker slot between checks. The default `poke` mode keeps the slot occupied the entire time. Always use `reschedule` unless you have a specific reason not to.

### Deferrable Operators (Airflow 2.6+)

Even better than `reschedule` -- deferrable operators use almost zero resources while waiting:

```python
wait_for_s3 = S3KeySensor(
    task_id="wait_for_s3",
    bucket_name="my-bucket",
    bucket_key="data/{{ ds }}/file.parquet",
    deferrable=True,   # Uses the Triggerer -- minimal resource usage
)
```

> **Common Mistake**
>
> **`mode="poke"` on long-running sensors** -- Occupies a worker slot the entire time. A sensor waiting 3 hours in poke mode is a wasted worker for 3 hours.
>
> **No timeout** -- A sensor without a timeout waits forever. Always set one.
>
> **Poke interval too short** -- Checking S3 every 5 seconds is unnecessary and costly (S3 LIST operations aren't free at scale).

**At your job:** Sensors are how you coordinate pipelines that depend on external events. The most common pattern: an ExternalTaskSensor that waits for an upstream ingestion DAG to complete before running transformations.

### Checkpoint

1. What's the difference between `mode="poke"` and `mode="reschedule"`?
2. Why should you always set a `timeout` on sensors?
3. What does `deferrable=True` do that `reschedule` mode doesn't?

---

## 4.9 Testing DAGs Locally

> **TL;DR**
> - DAG integrity tests (does it parse?) should run in CI/CD -- catches 80% of deployment issues
> - Separate business logic from DAG files so you can unit test normally
> - Use `airflow dags test` for free integration testing
> - Don't test Airflow internals -- test YOUR logic

Would you deploy application code without tests? Then why do so many people deploy DAGs without tests? It's easier than you think.

### Level 1: DAG Integrity Tests

Does the DAG even parse? Run this in CI/CD:

```python
# tests/test_dag_integrity.py
import pytest
from airflow.models import DagBag


@pytest.fixture()
def dagbag():
    return DagBag(dag_folder="dags/", include_examples=False)


def test_no_import_errors(dagbag):
    """Verify no DAG import errors."""
    assert len(dagbag.import_errors) == 0, f"Import errors: {dagbag.import_errors}"


def test_dag_count(dagbag):
    """Verify expected number of DAGs."""
    assert len(dagbag.dags) >= 1, "No DAGs found!"


@pytest.mark.parametrize("dag_id", [
    "my_first_pipeline",
    "taskflow_pipeline",
])
def test_dag_exists(dagbag, dag_id):
    """Check that expected DAGs are loaded."""
    assert dag_id in dagbag.dags, f"DAG '{dag_id}' not found"


def test_no_cycles(dagbag):
    """Verify no DAGs have circular dependencies."""
    for dag_id, dag in dagbag.dags.items():
        assert dag.topological_sort()  # Raises if there's a cycle
```

> **Companion code:** See `modules/module-4/solution/tests/test_dag_integrity.py` for the complete test suite.

### Level 2: Task Logic Tests

> **Pro Tip: Separate Logic from DAGs**
>
> The biggest testing tip: **don't put business logic inside your DAG file.** Put it in separate Python modules, test those normally, and have your DAG tasks just call the functions.

```
project/
|-- dags/
|   |-- my_pipeline.py          # DAG definition -- thin, just wiring
|-- src/
|   |-- extractors.py           # API calls, file reads
|   |-- transforms.py           # Business logic
|   |-- validators.py           # Data quality checks
|   |-- loaders.py              # Database writes
|-- tests/
    |-- test_dag_integrity.py   # DAGs parse correctly
    |-- test_transforms.py      # Unit tests for logic
    |-- test_validators.py      # Unit tests for validation
```

```python
# src/transforms.py
def calculate_tax(amount: float, rate: float = 0.08) -> float:
    """Calculate amount with tax."""
    if amount < 0:
        raise ValueError(f"Amount cannot be negative: {amount}")
    return round(amount * (1 + rate), 2)


def validate_order(order: dict) -> bool:
    """Validate a single order record."""
    required_fields = ["order_id", "customer", "amount", "date"]
    return all(field in order for field in required_fields) and order["amount"] > 0
```

```python
# tests/test_transforms.py
import pytest
from src.transforms import calculate_tax, validate_order


def test_calculate_tax():
    assert calculate_tax(100.00) == 108.00
    assert calculate_tax(0) == 0.00


def test_calculate_tax_negative():
    with pytest.raises(ValueError):
        calculate_tax(-50.00)


def test_validate_order_valid():
    order = {"order_id": 1, "customer": "Alice", "amount": 99.99, "date": "2026-02-19"}
    assert validate_order(order) is True


def test_validate_order_missing_field():
    order = {"order_id": 1, "customer": "Alice"}
    assert validate_order(order) is False


def test_validate_order_negative_amount():
    order = {"order_id": 1, "customer": "Alice", "amount": -10, "date": "2026-02-19"}
    assert validate_order(order) is False
```

### Level 3: Integration Tests

```bash
# Test a specific task
docker compose exec airflow-scheduler \
  airflow tasks test my_first_pipeline extract_data 2026-02-19

# Test the whole DAG (one-off run without the scheduler)
docker compose exec airflow-scheduler \
  airflow dags test my_first_pipeline 2026-02-19
```

> **Common Mistake**
>
> **No tests at all** -- At minimum, run DAG integrity tests in CI. Takes 30 seconds, catches 80% of deployment issues.
>
> **Testing Airflow internals** -- Don't test that `PythonOperator` works. Airflow already tests that. Test YOUR business logic.

**At your job:** Push for DAG integrity tests in CI from day one. It's the single highest-value, lowest-effort testing investment you can make. One import error in a DAG file can silently break an entire pipeline.

### Checkpoint

1. What do DAG integrity tests verify?
2. Why should business logic live in separate modules, not inside DAG files?
3. What's the difference between `airflow tasks test` and `airflow dags test`?

---

## 4.10 Airflow in Production -- Best Practices at Scale

> **TL;DR**
> - Deploy DAGs via Git + CI/CD -- never edit files directly on the server
> - Every task must be idempotent (safe to run twice)
> - Use pools to prevent resource exhaustion on shared systems
> - Monitor the scheduler heartbeat -- if it dies, nothing runs

Running Airflow on your laptop is easy. Running it in production where hundreds of DAGs execute reliably every day -- that's where the real lessons are.

### 1. Git-Based DAG Deployment

Never edit DAG files directly on the Airflow server:

```yaml
# .github/workflows/deploy-dags.yml
name: DAG CI/CD

on:
  push:
    branches: [main]
    paths: ["dags/**", "src/**", "tests/**"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install apache-airflow==2.9.0 pytest
      - run: python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: echo "Deploy DAGs to production (replace with your deploy command)"
```

> **Companion code:** See `modules/module-4/solution/.github/workflows/deploy-dags.yml` for the complete CI/CD workflow.

### 2. Resource Management with Pools

```python
# Set pool slots to prevent resource exhaustion
@task(pool="api_calls", pool_slots=1)
def call_external_api():
    """Only N concurrent API calls across all DAGs."""
    pass

# Set priority for important DAGs
@task(priority_weight=10)  # Higher = runs first when resources are scarce
def critical_transform():
    pass
```

Pools are essential in production. If you have 20 DAGs that all call the same API, you'll rate-limit yourself instantly without pools.

### 3. Idempotency -- The Golden Rule

> **Key Concept: Idempotency**
>
> Every task should be **idempotent** -- running it twice with the same inputs produces the same output. Airflow WILL retry tasks. If your task inserts rows without checking for duplicates, you'll get double data.

```python
@task()
def idempotent_load(data: list[dict], execution_date: str):
    """Use MERGE/upsert, not INSERT, for idempotency."""
    hook = PostgresHook(postgres_conn_id="warehouse")

    # Delete-then-insert (atomic replace for a partition)
    hook.run(f"DELETE FROM orders WHERE date = '{execution_date}'")
    # ... insert new data ...

    # Or use upsert
    # INSERT INTO orders ... ON CONFLICT (order_id) DO UPDATE SET ...
```

**Why this matters:** Imagine your extract task succeeds but the transform fails. Airflow retries the entire chain. If your extract task appends data instead of replacing it, you now have duplicate rows. Idempotency prevents this.

### 4. Templating with Jinja

Airflow passes execution context as Jinja templates. Use them for date partitioning:

```python
from airflow.operators.bash import BashOperator

# {{ ds }} = execution date (YYYY-MM-DD)
# {{ ds_nodash }} = YYYYMMDD
# {{ data_interval_start }} / {{ data_interval_end }}
extract = BashOperator(
    task_id="extract",
    bash_command="python extract.py --date {{ ds }} --output /data/raw/{{ ds_nodash }}/",
)
```

### 5. Monitoring

Set up StatsD + Grafana for Airflow metrics:
- DAG/task success/failure rates
- Task duration trends (is something getting slower?)
- Scheduler heartbeat (is it alive?)
- Queue depth (are tasks piling up?)

### Production Checklist

```
[ ] LocalExecutor or CeleryExecutor (never Sequential)
[ ] External Postgres for metadata (not SQLite)
[ ] Secrets backend (AWS SM, Vault, etc.)
[ ] Git-based DAG deployment with CI/CD
[ ] DAG integrity tests in CI
[ ] All tasks are idempotent
[ ] Retries + timeouts on every task
[ ] Pools for shared resources
[ ] Alerting on failure (Slack/PagerDuty)
[ ] Monitoring (StatsD + Grafana)
[ ] Log rotation configured
[ ] Airflow upgraded regularly (security patches)
```

> **Common Mistake**
>
> **Not making tasks idempotent** -- The #1 cause of duplicate data in production.
>
> **Not monitoring the scheduler** -- If the scheduler dies, nothing runs. Monitor its heartbeat.
>
> **Massive DAGs** -- If a DAG has 100+ tasks, break it into smaller DAGs connected by sensors.

**At your job:** When you inherit an Airflow deployment, walk through this checklist. Most teams have 3-4 items missing. Fixing them before the next incident is how you build credibility fast.

### Checkpoint

1. Why must every Airflow task be idempotent?
2. What's the purpose of pools in Airflow?
3. What happens if the Airflow scheduler goes down?

---

## Common Airflow Gotchas -- A Reference

These are the mistakes that bite everyone at least once. Keep this list handy.

| Gotcha | What Happens | Fix |
|--------|-------------|-----|
| Top-level code in DAGs | `requests.get()` called every 30s by scheduler | Move all logic inside task functions |
| `Variable.get()` at module level | DB query every 30s per DAG file | Move inside `@task` functions |
| Forgetting `catchup=False` | Hundreds of backfill runs on deploy | Set `catchup=False` during development |
| No `execution_timeout` | Stuck task blocks pipeline for hours | Set timeout on every task |
| DataFrames in XCom | Metadata DB bloats, performance degrades | Write to file, pass path via XCom |
| Import errors in DAG file | DAG silently disappears | Run `airflow dags list` after changes |
| DAGs in a loop without factory function | Python closure captures last iteration's value | Use a factory function |
| `mode="poke"` on sensors | Worker slot occupied for hours | Use `mode="reschedule"` or `deferrable=True` |
| INSERT without idempotency | Duplicate rows on retry | Use UPSERT or DELETE-then-INSERT |
| Missing `my_pipeline()` call | TaskFlow DAG doesn't appear | Always call the decorated function |

---

## Module 4 Project: Multi-Step Production ETL Pipeline

Build a production-grade e-commerce ETL pipeline with extraction, validation, transformation, loading, and alerting.

### Project Overview

Your pipeline will:
1. Check for new data via a sensor
2. Extract data from a simulated API
3. Validate data quality
4. Transform using computed fields
5. Load to a warehouse table (with upserts for idempotency)
6. Run post-load quality checks
7. Send notification on success/failure

### Step 1: Set Up the Project Structure

```
module-4-project/
|-- docker-compose.yaml          # Airflow + Postgres (from Section 4.2)
|-- dags/
|   |-- ecommerce_pipeline.py    # Your main DAG
|-- src/
|   |-- __init__.py
|   |-- extractors.py            # API extraction logic
|   |-- validators.py            # Data quality checks
|   |-- transforms.py            # Transform functions
|-- sql/
|   |-- create_tables.sql
|-- tests/
|   |-- test_dag_integrity.py
|   |-- test_validators.py
|   |-- test_transforms.py
|-- data/                        # Mounted volume for file staging
|-- .env
```

### Step 2: Create the Warehouse Tables

```sql
-- sql/create_tables.sql
CREATE TABLE IF NOT EXISTS raw_orders (
    order_id INTEGER,
    customer_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    unit_price DECIMAL(10,2),
    order_date DATE,
    status VARCHAR(20),
    ingested_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    segment VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES dim_customers(customer_id),
    product_id INTEGER,
    quantity INTEGER,
    unit_price DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    order_date DATE,
    status VARCHAR(20),
    processed_at TIMESTAMP DEFAULT NOW()
);
```

> **Companion code:** See `modules/module-4/starter/sql/create_tables.sql` for the starter SQL.

### Step 3: Build the Extraction Logic

```python
# src/extractors.py
"""Simulated API extraction -- in production, this would call an actual API."""

import random
from datetime import datetime


def extract_orders(execution_date: str) -> list[dict]:
    """Simulate extracting orders for a given date."""
    customers = list(range(1, 21))
    products = list(range(100, 120))
    statuses = ["completed", "pending", "shipped", "cancelled"]

    num_orders = random.randint(10, 50)
    orders = []

    for i in range(num_orders):
        orders.append({
            "order_id": int(datetime.now().timestamp() * 1000) + i,
            "customer_id": random.choice(customers),
            "product_id": random.choice(products),
            "quantity": random.randint(1, 5),
            "unit_price": round(random.uniform(9.99, 199.99), 2),
            "order_date": execution_date,
            "status": random.choice(statuses),
        })

    return orders


def extract_customers() -> list[dict]:
    """Simulate customer dimension data."""
    segments = ["premium", "standard", "basic"]
    return [
        {
            "customer_id": i,
            "name": f"Customer_{i}",
            "email": f"customer_{i}@example.com",
            "segment": segments[i % 3],
        }
        for i in range(1, 21)
    ]
```

### Step 4: Build the Validation Logic

```python
# src/validators.py
"""Data quality validation functions."""


class DataQualityError(Exception):
    """Raised when data quality checks fail."""
    pass


def validate_orders(orders: list[dict]) -> list[dict]:
    """Validate order data. Returns valid orders, raises on critical issues."""
    if not orders:
        raise DataQualityError("No orders received -- extraction may have failed")

    required_fields = ["order_id", "customer_id", "product_id",
                       "quantity", "unit_price", "order_date"]
    valid_statuses = {"completed", "pending", "shipped", "cancelled"}

    valid_orders = []
    issues = []

    for order in orders:
        # Check required fields
        missing = [f for f in required_fields if f not in order]
        if missing:
            issues.append(f"Order {order.get('order_id', '?')}: missing {missing}")
            continue

        # Check value ranges
        if order["quantity"] <= 0:
            issues.append(f"Order {order['order_id']}: invalid quantity {order['quantity']}")
            continue

        if order["unit_price"] <= 0:
            issues.append(f"Order {order['order_id']}: invalid price {order['unit_price']}")
            continue

        if order.get("status") not in valid_statuses:
            issues.append(f"Order {order['order_id']}: unknown status {order.get('status')}")
            continue

        valid_orders.append(order)

    # Log issues
    if issues:
        print(f"Found {len(issues)} data quality issues:")
        for issue in issues[:10]:
            print(f"  - {issue}")

    # Fail if more than 20% of records are bad
    error_rate = len(issues) / len(orders) if orders else 0
    if error_rate > 0.2:
        raise DataQualityError(
            f"Error rate too high: {error_rate:.1%} ({len(issues)}/{len(orders)} records)"
        )

    print(f"Validation passed: {len(valid_orders)}/{len(orders)} orders valid")
    return valid_orders
```

### Step 5: Build the DAG

```python
# dags/ecommerce_pipeline.py
"""
E-Commerce ETL Pipeline
=======================
Production-grade pipeline: extract, validate, transform, load
with error handling and post-load quality checks.
"""
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.sensors.filesystem import FileSensor
import os
import sys

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def on_failure(context):
    """Called when any task fails (after retries exhausted)."""
    ti = context["task_instance"]
    print(f"ALERT: Task {ti.task_id} in DAG {ti.dag_id} failed!")
    print(f"  Execution date: {context['ds']}")
    print(f"  Log URL: {ti.log_url}")
    # In production: send to Slack, PagerDuty, etc.


def on_success(context):
    """Called when the entire DAG succeeds."""
    print(f"DAG {context['dag'].dag_id} completed for {context['ds']}")


@dag(
    dag_id="ecommerce_etl_pipeline",
    description="Extract, validate, transform, and load e-commerce order data",
    schedule="0 6 * * *",
    start_date=datetime(2026, 2, 1),
    catchup=False,
    default_args={
        "owner": "george",
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=15),
        "execution_timeout": timedelta(minutes=30),
        "on_failure_callback": on_failure,
    },
    on_success_callback=on_success,
    tags=["ecommerce", "etl", "production"],
)
def ecommerce_pipeline():

    @task()
    def extract_orders(execution_date: str = "{{ ds }}") -> list[dict]:
        from extractors import extract_orders as _extract
        orders = _extract(execution_date)
        print(f"Extracted {len(orders)} orders for {execution_date}")
        return orders

    @task()
    def extract_customers() -> list[dict]:
        from extractors import extract_customers as _extract
        customers = _extract()
        print(f"Extracted {len(customers)} customers")
        return customers

    @task()
    def validate(orders: list[dict]) -> list[dict]:
        from validators import validate_orders
        return validate_orders(orders)

    @task()
    def transform(orders: list[dict]) -> list[dict]:
        for order in orders:
            order["total_amount"] = round(order["quantity"] * order["unit_price"], 2)
            order["tax_amount"] = round(order["total_amount"] * 0.08, 2)
            order["processed_at"] = datetime.now().isoformat()
        print(f"Transformed {len(orders)} orders")
        return orders

    @task()
    def load_orders(orders: list[dict], execution_date: str = "{{ ds }}"):
        hook = PostgresHook(postgres_conn_id="postgres_default")
        # Idempotent: delete-then-insert for this date partition
        hook.run(f"DELETE FROM fact_orders WHERE order_date = '{execution_date}'")
        for order in orders:
            hook.run(
                """INSERT INTO fact_orders
                   (order_id, customer_id, product_id, quantity, unit_price,
                    total_amount, tax_amount, order_date, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                parameters=(
                    order["order_id"], order["customer_id"], order["product_id"],
                    order["quantity"], order["unit_price"], order["total_amount"],
                    order["tax_amount"], order["order_date"], order["status"],
                )
            )
        print(f"Loaded {len(orders)} orders for {execution_date}")

    @task()
    def post_load_checks(execution_date: str = "{{ ds }}"):
        hook = PostgresHook(postgres_conn_id="postgres_default")
        df = hook.get_pandas_df(
            f"SELECT COUNT(*) as cnt FROM fact_orders WHERE order_date = '{execution_date}'"
        )
        count = df['cnt'].iloc[0]
        print(f"Post-load check: {count} rows for {execution_date}")
        assert count > 0, f"No rows loaded for {execution_date}!"

    # Wire it up
    raw_orders = extract_orders()
    customers = extract_customers()
    valid_orders = validate(raw_orders)
    transformed = transform(valid_orders)
    load_orders(transformed) >> post_load_checks()


ecommerce_pipeline()
```

> **Companion code:** See `modules/module-4/solution/dags/ecommerce_pipeline.py` for the complete production DAG.

### Evaluation Criteria

- All tasks have retries and execution_timeout
- Load task is idempotent (safe to re-run)
- Validation rejects bad records with clear error messages
- Business logic lives in `src/`, not in the DAG file
- DAG integrity tests pass
- Alerting callbacks are configured
- Code follows the project structure from Section 4.9

---

## What's Next

You now know how to orchestrate data pipelines with Airflow -- from writing your first DAG to running production-grade workflows with error handling, testing, and CI/CD. Module 5 introduces stream processing -- how to handle data that arrives continuously and needs to be acted on immediately, using tools like Apache Kafka.
