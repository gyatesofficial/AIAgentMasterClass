# Module 3: Python for Data Engineers

## The Reality of Data Engineering in Python

About half of data engineering is just getting data out of APIs. The other half is cleaning what you got, validating it, converting it to a format that does not make everyone downstream want to cry, and loading it into a warehouse. The APIs are never as clean as the docs suggest. Fields that the documentation calls "required" will be null. Dates will arrive in three different formats across the same endpoint. Pagination will behave differently under load than it does in the sandbox. Rate limits will kick in at the worst possible moment.

This module teaches you the Python patterns that production data pipelines actually use. Not toy scripts that fetch one page of results and print them -- real, structured projects with proper configuration, retry logic, data validation, and testing. By the end, you will have built a complete extract-validate-transform-load pipeline against a realistic API, using the same tools and patterns you will encounter on the job.

> **What we are building:** A pipeline called "ShopFast" that extracts product and order data from a vendor API, validates every record with Pydantic, transforms it with Polars, and loads it into a PostgreSQL warehouse. The companion code lives in `de-fast-track/modules/module-3/` with both `starter/` (TODO stubs for you to complete) and `solution/` (reference implementation).

---

## 3.1 Project Structure for Data Engineering Projects

Most data engineering code you encounter in the wild is a mess. Single scripts with hundreds of lines, hardcoded credentials, no tests, and `import sys; sys.path.append("../../..")` hacks scattered everywhere. Your first contribution to any team should be setting up a proper project structure. It costs almost nothing and prevents an enormous class of problems.

### The src/ Layout

The modern Python standard is the `src/` layout. Here is what the ShopFast project looks like:

```
shopfast-pipeline/
    pyproject.toml           # Project metadata and dependencies
    .env.example             # Template showing required env vars (committed to git)
    .env                     # Actual secrets (NEVER committed to git)
    .gitignore
    mock_api/
        app.py               # Fake API server for local development
    src/
        shopfast/
            __init__.py
            config.py         # Pydantic-settings configuration
            models.py         # Pydantic data models
            pipeline.py       # Main ETL orchestration
            extractors/
                __init__.py
                api_client.py # API extraction logic
            transformers/
                __init__.py
            loaders/
                __init__.py
            utils/
                __init__.py
    tests/
        conftest.py           # Shared pytest fixtures
        test_api_client.py
        test_models.py
```

**Why this layout matters.** The `src/` directory prevents a subtle but nasty bug: without it, Python might import your local package source instead of the installed version, leading to tests that pass locally but fail in CI. With the `src/` layout, you *must* install the package (even in editable mode with `pip install -e .`) before imports work. This guarantees that what you test is what you ship.

The `extractors/`, `transformers/`, `loaders/` split mirrors the ETL stages. When your pipeline grows from one API to five, you add new files under `extractors/` rather than inflating a single script. When a new team member joins, they can look at the directory structure and immediately understand where things live.

### pyproject.toml: The Modern Standard

The `pyproject.toml` file replaces the old `setup.py` and `requirements.txt` approach. Here is the one from the companion repo:

```toml
[project]
name = "shopfast-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.2",
    "polars>=0.20",
    "duckdb>=0.10",
    "pyarrow>=16",
    "tenacity>=8.3",
    "python-dotenv>=1.0",
    "rich>=13.7",
    "psycopg2-binary>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.2", "ruff>=0.4"]

[tool.ruff]
line-length = 100
```

Notice the dependency choices. Each one is deliberate, and we will cover why throughout this module. The `dev` extras keep test and lint tools separate from production dependencies -- your Docker image does not need `pytest`.

### Configuration with pydantic-settings

I have seen data engineers hardcode API keys in scripts checked into GitHub. I have seen database passwords in plain text in Jupyter notebooks that got shared in Slack. I have seen AWS credentials committed to public repos and exploited within minutes by bots that scan GitHub for exactly this. Here is why `pydantic-settings` exists.

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "dataeng"
    db_password: str = "dataeng"
    db_name: str = "warehouse"
    api_base_url: str = "http://localhost:5000"
    api_key: str = "dev-key-change-me"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "raw-data"
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"


settings = Settings()
```

This does several things at once:

1. **Type safety.** If someone sets `DB_PORT=not_a_number` in their environment, Pydantic raises a clear error at startup, not a cryptic `psycopg2` connection failure five minutes into a pipeline run.

2. **Environment variable loading.** `pydantic-settings` automatically reads environment variables matching the field names (case-insensitive). In production, you set `DB_PASSWORD` as a Kubernetes secret or a CI/CD variable. In development, you put it in a `.env` file.

3. **Sensible defaults.** The defaults point at local development services (localhost, default ports, dev credentials). A new developer clones the repo, runs `docker compose up`, and everything connects without configuration.

4. **Single source of truth.** Every part of the pipeline imports from `config.py`. There is exactly one place to look when you need to understand what configuration exists.

The `.env` / `.env.example` pattern is critical:

```bash
# .env.example -- committed to git, shows what variables are needed
DB_HOST=localhost
DB_PORT=5432
DB_USER=dataeng
DB_PASSWORD=changeme
API_BASE_URL=http://localhost:5000
API_KEY=your-api-key-here
```

```bash
# .env -- NEVER committed to git, contains actual secrets
DB_PASSWORD=real-production-password
API_KEY=sk-prod-abc123def456
```

Your `.gitignore` must include `.env` but NOT `.env.example`. The example file serves as documentation for what environment variables the project expects. When a new engineer joins, they copy `.env.example` to `.env` and fill in their values. No Slack messages asking "what environment variables do I need?"

> **At your job:** Your first day on a data engineering team, you will clone a repo. If there is a `.env.example`, you know exactly what to configure. If there is not, you will spend an hour reading code and asking teammates what secrets you need. Be the person who adds the `.env.example`.

---

## 3.2 Working with APIs

At your job, one of your first tasks will probably sound like this: "We signed a contract with VendorX. They have a REST API. Pull their data into our warehouse daily." This sounds simple until you discover that the API paginates with cursor tokens instead of offsets, returns dates as Unix timestamps in some endpoints and ISO strings in others, rate-limits you to 100 requests per minute, and occasionally returns 500 errors for no discernible reason.

Here is how you build an API client that handles all of that.

### Why httpx Over requests

The `requests` library is everywhere. It has been the default HTTP library in Python for over a decade. So why use `httpx`?

```python
import httpx

# httpx has an almost identical API to requests
response = httpx.get("https://api.example.com/data")
data = response.json()
```

The API is nearly identical, so switching is painless. But `httpx` gives you three things that matter for data engineering:

1. **Async support built in.** When you eventually need to hit 10 API endpoints in parallel (and you will), `httpx` supports `async/await` natively. With `requests`, you would have to rewrite your entire client using `aiohttp`, which has a completely different API. With `httpx`, you change `httpx.Client` to `httpx.AsyncClient` and add `async/await` keywords. The rest stays the same.

2. **HTTP/2 support.** Some modern APIs only support HTTP/2. More importantly, HTTP/2 multiplexing lets you send multiple requests over a single connection, which is faster when you are paginating through thousands of pages.

3. **Better timeout handling.** `httpx` has separate connect, read, write, and pool timeouts. `requests` has a single timeout that covers everything, which means you either set it too low (and timeout on large responses) or too high (and hang forever on connection issues).

### The Production API Client

Here is the complete API client from the companion repo. Study it carefully -- this pattern will serve you for years:

```python
import logging
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class ShopFastClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
    )
    def _get(self, path: str, params: dict | None = None) -> dict | list:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_products(self, limit: int = 100, offset: int = 0) -> list[dict]:
        all_products = []
        while True:
            batch = self._get("/products", params={"limit": limit, "offset": offset})
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            logger.info(f"Fetched {len(all_products)} products so far...")
        logger.info(f"Total products fetched: {len(all_products)}")
        return all_products

    def fetch_orders(self, since: datetime | None = None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since.isoformat()
        orders = self._get("/orders", params=params)
        logger.info(f"Fetched {len(orders)} orders")
        return orders

    def health_check(self) -> bool:
        try:
            result = self._get("/health")
            return result.get("status") == "ok"
        except Exception:
            return False

    def close(self):
        self.client.close()
```

Let us break down every design decision.

### The Client Pattern

```python
self.client = httpx.Client(
    base_url=self.base_url,
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=30.0,
)
```

We create a **persistent client** rather than making individual `httpx.get()` calls. This matters because:

- **Connection reuse.** The client maintains a connection pool. Instead of opening a new TCP connection (and doing a TLS handshake) for every request, it reuses existing connections. When you are making hundreds of paginated requests, this is dramatically faster.
- **Consistent headers.** The auth header is set once. You cannot accidentally forget it on one request.
- **Resource management.** The client has a `close()` method. In a production pipeline, you want to cleanly shut down connections when you are done, not leave them hanging.

A more robust version would use a context manager:

```python
class ShopFastClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

# Usage:
with ShopFastClient(base_url, api_key) as client:
    products = client.fetch_products()
# Connection is guaranteed to close, even if an exception occurs
```

### Retry Logic with tenacity

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
)
def _get(self, path: str, params: dict | None = None) -> dict | list:
    response = self.client.get(path, params=params)
    response.raise_for_status()
    return response.json()
```

This is where `tenacity` earns its place in every data engineer's toolkit. The decorator says: "If this function raises an `HTTPStatusError` or `ConnectError`, wait and try again. Try up to 3 times. Wait exponentially between attempts (2 seconds, then 4, then 8, capped at 30)."

**Why exponential backoff matters.** Imagine 100 pipeline instances all hitting an API that just returned a 500 error. If they all retry immediately, they slam the API with 100 simultaneous requests again. The API, already struggling, gets worse. All 100 retry again. This is the **thundering herd problem**.

Exponential backoff spreads the retries over time. The first retry waits 2 seconds. The second waits 4 seconds. The third waits 8 seconds. With some randomized jitter (which `tenacity` supports), the 100 instances end up retrying at different times, giving the API breathing room to recover.

```
Without backoff:  [100 requests] -> fail -> [100 requests] -> fail -> [100 requests]
With exp backoff: [100 requests] -> fail -> [scattered retries over 2-8s] -> [scattered retries over 4-16s]
```

**Why we only retry specific exceptions.** A `ConnectError` means the server is temporarily unreachable -- retrying makes sense. An `HTTPStatusError` from a 500 means the server had an internal error -- retrying often works. But a 400 Bad Request means our request is malformed -- retrying the same bad request will never work. The `retry_if_exception_type` filter prevents wasting time on unrecoverable errors.

In a production API client, you would also handle HTTP 429 (Too Many Requests) explicitly:

```python
from tenacity import retry_if_exception

def is_retryable(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, httpx.ConnectError):
        return True
    return False

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(is_retryable),
)
def _get(self, path, params=None):
    response = self.client.get(path, params=params)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 30))
        raise httpx.HTTPStatusError(
            f"Rate limited, retry after {retry_after}s",
            request=response.request,
            response=response,
        )
    response.raise_for_status()
    return response.json()
```

### Pagination

The `fetch_products` method demonstrates offset-based pagination:

```python
def fetch_products(self, limit: int = 100, offset: int = 0) -> list[dict]:
    all_products = []
    while True:
        batch = self._get("/products", params={"limit": limit, "offset": offset})
        if not batch:
            break
        all_products.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        logger.info(f"Fetched {len(all_products)} products so far...")
    logger.info(f"Total products fetched: {len(all_products)}")
    return all_products
```

This works fine for small datasets (hundreds or thousands of records). But what happens when an API returns 10 million records? You cannot hold them all in memory. This is where **generators** come in.

### Generators: The Memory-Efficient Alternative

A generator function uses `yield` instead of `return`. Instead of building a complete list in memory and returning it all at once, it produces one item (or one batch) at a time:

```python
def fetch_products_streaming(self, limit: int = 100) -> Iterator[list[dict]]:
    """Yield one page of products at a time, never holding all pages in memory."""
    offset = 0
    while True:
        batch = self._get("/products", params={"limit": limit, "offset": offset})
        if not batch:
            break
        yield batch  # Hand this batch to the caller, then pause here
        if len(batch) < limit:
            break
        offset += limit
```

**What `yield` actually does under the hood.** When Python encounters `yield`, it transforms the function into a generator. Calling the function does not execute it -- it returns a generator object. Each time you call `next()` on that generator (or iterate with `for`), the function runs until it hits `yield`, hands back the value, and *freezes its entire state* -- local variables, instruction pointer, everything. The next call to `next()` resumes from exactly where it left off.

```python
# Without generators: all 10M records in memory at once
all_products = client.fetch_products()  # Might use 8 GB of RAM
for product in all_products:
    process(product)

# With generators: only one page (100 records) in memory at a time
for page in client.fetch_products_streaming():
    for product in page:
        process(product)
    # When we loop back, the previous page can be garbage collected
```

This is not premature optimization. I have seen pipelines OOM-killed in production because someone called `.fetchall()` on a query returning 50 million rows or loaded every page of an API response into a list. Generators are how you handle data that might be larger than memory.

> **At your job:** When you see `all_results = []` followed by a loop that appends to it, ask yourself: "Could this list grow unbounded?" If the answer involves the words "depends on how much data" or "it should be fine," that is a generator waiting to happen.

---

## 3.3 File Formats: CSV, JSON, and Parquet

Data arrives in many formats. Understanding which format to use where -- and why -- is fundamental to data engineering.

### CSV: The Legacy Format

CSV is the cockroach of data formats. It has survived for decades because every tool can read it. But it is terrible for data engineering:

- **No type information.** Is `"123"` an integer, a float, or a string? Is `"2025-04-01"` a date or a string? The reader has to guess, and it will guess wrong.
- **No compression.** A 1 GB CSV file is 1 GB on disk and 1 GB to transfer.
- **Ambiguous parsing.** Does a comma in a value mean a delimiter or part of the data? What about newlines inside quoted fields? Every CSV parser handles edge cases differently.
- **Slow to read.** To find data in row 1,000,000, you must read through the previous 999,999 rows.
- **No schema.** If a column is renamed or removed between two CSV exports, you discover this at parse time, not at write time.

You will still encounter CSV constantly -- legacy systems export it, business users create it in Excel, vendors email it as attachments. The rule is: **receive as CSV, immediately convert to something better.**

### JSON and JSONL: The API Format

JSON is the native language of APIs. When you call a REST endpoint, you almost always get JSON back. It supports nested structures, which makes it natural for representing complex data like orders with line items.

**JSONL** (JSON Lines) puts one JSON object per line. This is better for data engineering than regular JSON because:

```jsonl
{"order_id": 1, "customer_id": 42, "status": "completed", "total": 79.97}
{"order_id": 2, "customer_id": 17, "status": "pending", "total": 149.50}
{"order_id": 3, "customer_id": 42, "status": "returned", "total": 33.00}
```

- You can process it line by line without loading the entire file into memory
- You can append new records by appending lines (no need to parse the whole file)
- Splittable -- distributed systems can split the file at newline boundaries

But JSON/JSONL still lacks types (everything is a string, number, boolean, or null -- no dates, no decimals), does not compress well, and is slow to parse at scale.

### Parquet: The Data Engineering Format

Parquet is where you want your data to end up. It is a **columnar, compressed, typed** binary format that was designed specifically for analytical workloads. Here is why it matters:

**Columnar storage.** In a row-based format (CSV, JSON), data is stored row by row:

```
Row 1: [order_id=1, customer_id=42, status="completed", amount=79.97, ...]
Row 2: [order_id=2, customer_id=17, status="pending", amount=149.50, ...]
```

To answer "what is the total amount across all orders?", you must read every field of every row, even though you only need the `amount` column. With a 50-column table, that is 49 columns of wasted I/O.

Parquet stores data column by column:

```
order_id column:   [1, 2, 3, ...]
customer_id column: [42, 17, 42, ...]
status column:     ["completed", "pending", "returned", ...]
amount column:     [79.97, 149.50, 33.00, ...]
```

Now the same query reads only the `amount` column -- a fraction of the data. **This is why Parquet queries are 5-20x faster than the same queries on CSV.** It is not a minor optimization; it is the difference between a query taking 30 seconds and taking 2 seconds.

**Why columnar compression works so well.** Adjacent values in a column tend to be similar. A `status` column with 10 million rows might have only 4 unique values (pending, completed, returned, cancelled). Parquet uses dictionary encoding to store those 10 million values as 10 million tiny integers plus a 4-entry lookup table. A `date` column in a daily-partitioned file might have the same date for every row -- run-length encoding compresses that to essentially zero overhead. A typical Parquet file is 5-10x smaller than the equivalent CSV.

**Built-in types and schema.** Every Parquet file embeds its schema in the file footer. When you open a Parquet file, you know immediately that `order_date` is a timestamp, `amount` is a decimal, and `quantity` is a 32-bit integer. No guessing, no coercion errors downstream.

**Predicate pushdown.** Parquet files contain metadata about each chunk of data: min/max values, null counts, etc. A query filtering `WHERE order_date = '2025-04-01'` can skip entire chunks where the max date is before April 2025 -- without reading the data itself.

### The Conversion Rule

Here is the rule that should be drilled into your muscle memory:

> **Receive as CSV or JSON. Immediately convert to Parquet. Store and process only Parquet from that point forward.**

```python
import polars as pl

# CSV arrives from a vendor
df = pl.read_csv("vendor_export.csv")

# Immediately convert and save as Parquet
df.write_parquet("vendor_export.parquet")

# From here on, only work with the Parquet file
df = pl.read_parquet("vendor_export.parquet")  # 5-20x faster to read back
```

Every minute you spend working with CSV at scale is wasted time. Convert once, benefit forever.

---

## 3.4 Data Validation with Pydantic

Raw API data is dirty. Fields will be missing. Types will be wrong. Values will violate business rules that nobody documented. If you load this data into your warehouse unchecked, you will spend your weekends debugging why revenue numbers do not match.

Pydantic models define what your data *should* look like and reject anything that does not match:

```python
from pydantic import BaseModel, field_validator, computed_field
from datetime import datetime


class OrderItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("unit_price must be >= 0")
        return v

    @computed_field
    @property
    def line_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class Order(BaseModel):
    order_id: int
    customer_id: int
    order_date: datetime
    status: str
    items: list[OrderItem]

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v):
        allowed = {"pending", "completed", "returned", "cancelled"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v

    @computed_field
    @property
    def total_amount(self) -> float:
        return round(sum(item.line_total for item in self.items), 2)
```

### What This Buys You

**Type coercion.** If the API returns `"order_date": "2025-06-15T10:30:00"` (a string), Pydantic automatically converts it to a `datetime` object. If it returns `"quantity": "3"` (a string), Pydantic converts it to `int`. If it returns `"quantity": "abc"`, Pydantic raises a clear validation error telling you exactly which field on which record failed.

**Business rule enforcement.** The `@field_validator` decorators encode rules that live in someone's head or in a Confluence page nobody reads: quantities must be positive, prices cannot be negative, status must be one of a known set. When the API starts returning `"status": "refunded"` because the vendor added a new status without telling you, your pipeline catches it immediately instead of silently loading garbage.

**Computed fields.** The `@computed_field` decorator on `line_total` and `total_amount` means these values are always derived from the source data, never from whatever the API claims they are. If the API says `line_total: 100` but `quantity: 2` and `unit_price: 29.99`, your computed field correctly produces `59.98`. You trust your math, not theirs.

**Validation in the pipeline.** Here is how the pipeline uses these models:

```python
def validate(self, raw_data: dict) -> list[Order]:
    logger.info("Validating orders...")
    valid_orders = []
    errors = []
    for raw_order in raw_data["orders"]:
        try:
            order = Order(**raw_order)
            valid_orders.append(order)
        except Exception as e:
            errors.append({"order_id": raw_order.get("order_id"), "error": str(e)})
    logger.info(f"Validated: {len(valid_orders)} valid, {len(errors)} errors")
    if errors:
        for err in errors[:5]:
            logger.warning(f"  Validation error: {err}")
    return valid_orders
```

Notice the pattern: do not fail the entire pipeline because one record is bad. Validate each record, collect the good ones, log the bad ones. In production, you would also write the bad records to a "dead letter" table or file for later investigation. The ratio of good to bad records tells you a lot -- if 0.1% of records fail validation, that is normal API messiness. If 30% fail, something changed upstream and you need to investigate.

> **At your job:** The first time a stakeholder asks "why are the numbers different from yesterday?", the answer is almost always bad data that was not validated. Pydantic models are your first line of defense. When you add a new data source, writing the Pydantic model should be the *first* thing you do, not an afterthought.

---

## 3.5 The Complete Pipeline

Here is the full pipeline that ties everything together -- extract, validate, transform, load:

```python
import logging

import polars as pl
import psycopg2

from shopfast.config import settings
from shopfast.extractors.api_client import ShopFastClient
from shopfast.models import Order

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class ShopFastPipeline:
    def __init__(self):
        self.api = ShopFastClient(settings.api_base_url, settings.api_key)
        self.conn = psycopg2.connect(settings.database_url)

    def extract(self) -> dict:
        logger.info("Extracting data from API...")
        products = self.api.fetch_products()
        orders = self.api.fetch_orders()
        logger.info(f"Extracted {len(products)} products, {len(orders)} orders")
        return {"products": products, "orders": orders}

    def validate(self, raw_data: dict) -> list[Order]:
        logger.info("Validating orders...")
        valid_orders = []
        errors = []
        for raw_order in raw_data["orders"]:
            try:
                order = Order(**raw_order)
                valid_orders.append(order)
            except Exception as e:
                errors.append({"order_id": raw_order.get("order_id"), "error": str(e)})
        logger.info(f"Validated: {len(valid_orders)} valid, {len(errors)} errors")
        if errors:
            for err in errors[:5]:
                logger.warning(f"  Validation error: {err}")
        return valid_orders

    def transform(self, orders: list[Order]) -> pl.DataFrame:
        logger.info("Transforming data with Polars...")
        rows = []
        for order in orders:
            for item in order.items:
                rows.append({
                    "order_id": order.order_id,
                    "customer_id": order.customer_id,
                    "order_date": order.order_date,
                    "status": order.status,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                })

        df = pl.DataFrame(rows)
        df = df.with_columns([
            pl.col("order_date").cast(pl.Date).alias("order_date_only"),
            pl.col("status").str.to_lowercase().alias("status_clean"),
        ])
        logger.info(f"Transformed DataFrame: {df.shape[0]} rows, {df.shape[1]} columns")
        return df

    def load(self, df: pl.DataFrame):
        logger.info(f"Loading {df.shape[0]} rows to warehouse...")
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS staging.order_items (
                order_id INT, customer_id INT, order_date TIMESTAMP,
                status VARCHAR(20), product_id INT, product_name VARCHAR(300),
                quantity INT, unit_price NUMERIC(10,2), line_total NUMERIC(12,2)
            )
        """)
        cur.execute("TRUNCATE staging.order_items")

        for row in df.iter_rows(named=True):
            cur.execute("""
                INSERT INTO staging.order_items
                (order_id, customer_id, order_date, status, product_id,
                 product_name, quantity, unit_price, line_total)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row["order_id"], row["customer_id"], row["order_date"],
                row["status"], row["product_id"], row["product_name"],
                row["quantity"], row["unit_price"], row["line_total"],
            ))
        self.conn.commit()
        logger.info("Load complete.")

    def run(self):
        try:
            raw = self.extract()
            valid = self.validate(raw)
            transformed = self.transform(valid)
            self.load(transformed)
            logger.info("Pipeline finished successfully.")
        finally:
            self.api.close()
            self.conn.close()


if __name__ == "__main__":
    pipeline = ShopFastPipeline()
    pipeline.run()
```

### Design Decisions Worth Noting

**The `try/finally` in `run()`.** This guarantees that the API client and database connection are closed even if the pipeline fails halfway through. Without this, a failed pipeline leaves open connections that eventually exhaust the database connection pool. I have seen production databases brought down because a retry loop kept opening connections without closing the failed ones.

**Staging table with TRUNCATE.** The load step writes to a `staging.order_items` table and truncates it first. This is the **full-refresh** pattern: every run replaces the entire staging table. It is simple and correct -- you never end up with duplicate records from a pipeline that ran twice. For incremental loads, you would use a merge/upsert pattern instead.

**Row-by-row inserts.** The current `load()` method inserts one row at a time. This works for small datasets but is slow for large ones. In production, you would use one of these approaches:

```python
# Option 1: COPY command (fastest for PostgreSQL)
import io
buffer = io.StringIO()
df.write_csv(buffer)
buffer.seek(0)
cur.copy_expert("COPY staging.order_items FROM STDIN WITH CSV HEADER", buffer)

# Option 2: executemany with page_size
from psycopg2.extras import execute_batch
execute_batch(cur, insert_sql, rows, page_size=1000)

# Option 3: Write Parquet, then use database's bulk import
df.write_parquet("/tmp/order_items.parquet")
# Then use COPY ... FROM ... (FORMAT PARQUET) if your DB supports it
```

**Polars over pandas.** The transform step uses Polars, not pandas. Polars is faster (it is written in Rust and uses all CPU cores), more memory-efficient, and has a more consistent API. For data engineering workloads -- especially transforming millions of rows -- the performance difference is significant. Polars is the new default for new data engineering projects.

---

## 3.6 Testing Data Pipelines

Data pipelines that are not tested break in production. Testing pipelines is different from testing web applications because the primary failure mode is not "the code crashes" but "the code runs fine and produces wrong numbers." Here are the patterns from the companion repo.

### Test Fixtures

Shared test data lives in `conftest.py`:

```python
import pytest


@pytest.fixture
def sample_order_data():
    return {
        "order_id": 1,
        "customer_id": 42,
        "order_date": "2025-06-15T10:30:00",
        "status": "completed",
        "items": [
            {"product_id": 1, "product_name": "Widget Pro", "quantity": 2, "unit_price": 29.99},
            {"product_id": 3, "product_name": "Gadget Lite", "quantity": 1, "unit_price": 19.99},
        ],
    }


@pytest.fixture
def sample_product_data():
    return {
        "id": 1,
        "product_name": "Widget Pro",
        "category": "Electronics",
        "subcategory": "Peripherals",
        "brand": "TechBrand",
        "unit_cost": 12.50,
        "unit_price": 29.99,
    }


@pytest.fixture
def sample_invalid_order():
    return {
        "order_id": 99,
        "customer_id": 1,
        "order_date": "2025-06-15T10:30:00",
        "status": "invalid_status",
        "items": [
            {"product_id": 1, "product_name": "Widget", "quantity": -1, "unit_price": 10.00},
        ],
    }
```

Notice the `sample_invalid_order` fixture: it has both an invalid status and a negative quantity. Testing the unhappy path is more important than testing the happy path for data engineering. You know your pipeline works when the data is clean. The question is what happens when the data is dirty.

### Testing Models

```python
import pytest
from shopfast.models import Order, OrderItem


def test_valid_order_item():
    item = OrderItem(product_id=1, product_name="Widget", quantity=2, unit_price=29.99)
    assert item.line_total == 59.98


def test_invalid_quantity():
    with pytest.raises(ValueError, match="quantity must be greater than 0"):
        OrderItem(product_id=1, product_name="Widget", quantity=0, unit_price=10.0)


def test_negative_price():
    with pytest.raises(ValueError, match="unit_price must be >= 0"):
        OrderItem(product_id=1, product_name="Widget", quantity=1, unit_price=-5.0)


def test_valid_order(sample_order_data):
    order = Order(**sample_order_data)
    assert order.total_amount == 79.97
    assert order.status == "completed"


def test_invalid_status():
    with pytest.raises(ValueError, match="status must be one of"):
        Order(
            order_id=1, customer_id=1, order_date="2025-01-01T00:00:00",
            status="bogus",
            items=[{"product_id": 1, "product_name": "X", "quantity": 1, "unit_price": 10}],
        )
```

These tests verify both the happy path (valid data produces correct computed fields) and the sad path (invalid data raises clear errors). The `match` parameter on `pytest.raises` ensures you are catching the *right* ValueError, not just any ValueError.

### Testing the API Client

```python
import pytest
from unittest.mock import patch
from shopfast.extractors.api_client import ShopFastClient


@pytest.fixture
def client():
    return ShopFastClient(base_url="http://localhost:5000", api_key="test-key")


def test_health_check(client):
    with patch.object(client, "_get", return_value={"status": "ok"}):
        assert client.health_check() is True


def test_health_check_failure(client):
    with patch.object(client, "_get", side_effect=Exception("connection refused")):
        assert client.health_check() is False


def test_fetch_products(client):
    mock_products = [{"id": i, "product_name": f"Product {i}"} for i in range(5)]
    with patch.object(client, "_get", return_value=mock_products):
        products = client.fetch_products()
        assert len(products) == 5


def test_fetch_orders(client):
    mock_orders = [{"order_id": i} for i in range(10)]
    with patch.object(client, "_get", return_value=mock_orders):
        orders = client.fetch_orders()
        assert len(orders) == 10
```

Key pattern here: **mock at the HTTP boundary, not higher.** We patch `_get` (the method that makes HTTP calls) rather than mocking the entire client. This lets us test the pagination logic, error handling, and data assembly without actually hitting a network. The tests run in milliseconds and never flake due to network issues.

### What Else to Test in Production

The companion tests cover the basics. In a production pipeline, you would also add:

- **Data quality assertions.** After transformation, check that row counts are within expected ranges, that no critical columns are entirely null, that dates fall within reasonable bounds.
- **Schema tests.** Verify that the output DataFrame has the expected columns and types before loading.
- **Integration tests.** Use the mock API server (`mock_api/app.py` in the starter code) to test the full extract-validate-transform flow end-to-end without touching the real API or database.

```python
# Example data quality test
def test_transform_output_quality():
    # ... set up pipeline and run transform ...
    assert df.shape[0] > 0, "Transform produced no rows"
    assert df["order_id"].null_count() == 0, "order_id has nulls"
    assert df["line_total"].min() >= 0, "Negative line totals found"
    assert df["order_date"].max() <= datetime.now(), "Future dates found"
```

---

## 3.7 The Mock API Server

The starter code includes a mock API server for local development. This is worth studying because it shows a pattern you will use constantly: building a fake version of an external dependency so you can develop and test without relying on the real thing.

```python
"""Mock ShopFast API for local development.
Run with: python -m mock_api.app
Serves fake product and order data on localhost:5000.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import random

PRODUCTS = [
    {"id": i, "product_name": f"Product {i}",
     "category": ["Electronics","Clothing","Home","Sports","Books"][i % 5],
     "unit_price": round(10 + random.random() * 190, 2)}
    for i in range(1, 51)
]

def generate_orders(count=100):
    orders = []
    for i in range(1, count + 1):
        num_items = random.randint(1, 4)
        items = [
            {"product_id": random.randint(1, 50),
             "product_name": f"Product {random.randint(1, 50)}",
             "quantity": random.randint(1, 5),
             "unit_price": round(10 + random.random() * 190, 2)}
            for _ in range(num_items)
        ]
        orders.append({
            "order_id": i,
            "customer_id": random.randint(1, 100),
            "order_date": (datetime.now() - timedelta(days=random.randint(0, 365))).isoformat(),
            "status": random.choice(["completed","completed","completed","pending","returned"]),
            "items": items,
        })
    return orders

ORDERS = generate_orders()
```

Notice how the mock data is not perfectly clean -- the status distribution is weighted toward "completed" (like real order data), prices are random floats (not round numbers), and dates span the last year. Good mock data mimics the messiness of real data, not the tidiness of documentation examples.

---

## Putting It All Together

Here is the mental model for this entire module. Every data engineering project you work on will follow this pattern, whether it takes a week or a year:

```
1. PROJECT STRUCTURE      Set up src/ layout, config, .env, .gitignore
        |
2. EXTRACT                Build API client with httpx + tenacity
        |                 Handle pagination, retries, rate limits
        |
3. VALIDATE               Define Pydantic models for every entity
        |                 Separate valid records from errors
        |
4. TRANSFORM              Convert to Parquet / Polars DataFrame
        |                 Add computed columns, clean data
        |
5. LOAD                   Write to warehouse (staging first)
        |
6. TEST                   Unit tests for models, mocked API tests,
                          data quality assertions
```

> **At your job:** Your first task might be: "Pull data from this vendor's API into our warehouse." Here is exactly how you would structure that. Start with the project layout and config (30 minutes). Write the Pydantic models based on the API docs (1 hour -- this forces you to understand the data before you write any pipeline code). Build the API client with retry logic (2 hours). Wire up the pipeline (1 hour). Write tests (1 hour). The entire thing takes a day, and you have a production-grade pipeline, not a script that works-on-my-machine.

---

## Companion Code

The full implementation lives in the course repository:

- **Starter code** (with TODOs for you to complete): `de-fast-track/modules/module-3/starter/`
- **Reference solution**: `de-fast-track/modules/module-3/solution/`

Work through the starter code in this order:
1. `src/shopfast/config.py` -- Fill in the Settings fields
2. `src/shopfast/models.py` -- Add validators and computed fields
3. `src/shopfast/extractors/api_client.py` -- Implement the HTTP client
4. `src/shopfast/pipeline.py` -- Wire up the full ETL pipeline
5. `tests/conftest.py` -- Create test fixtures matching the API format
6. Run `python -m mock_api.app` in one terminal, then `python -m shopfast.pipeline` in another

---

## What's Next

Now that you can extract data from APIs, validate it, and load it into a warehouse, Module 4 covers how data is *processed at scale*. We will move from single-machine pipelines to distributed batch processing, workflow orchestration, and the architectural patterns that determine how your pipelines run in production.
