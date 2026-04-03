# Module 10: Monitoring, Observability & Data Quality

## Why Observability Matters

Building a system is the easy part. Keeping it running — and knowing when it's *not* running correctly — is where most engineering effort goes. The worst kind of failure isn't a crash; it's a system that keeps running while producing wrong results. A dashboard showing incorrect revenue for three weeks before anyone notices is far more damaging than an outage.

**Monitoring** tells you *something is wrong*: "CPU is at 95%," "Error rate spiked," "Pipeline failed."

**Observability** tells you *why it's wrong*: "CPU is at 95% because this specific query is doing a full table scan due to a missing partition filter, triggered by a code change deployed two hours ago."

The difference matters. Monitoring gives you alerts. Observability gives you answers.

> **Key Takeaway:** Invest in observability before you think you need it. By the time you're debugging a production incident at 2 AM, it's too late to add instrumentation.

---

## The Monitoring Pyramid

Think of monitoring as a pyramid with four levels. Each level builds on the one below it:

### Level 1: Infrastructure Metrics (Foundation)

CPU, memory, disk I/O, network throughput. These are the vital signs of your servers. If a machine runs out of memory, everything on it fails.

**Tools**: Prometheus + Grafana, CloudWatch, Datadog.

**Key metrics**: CPU utilization (alert at 80%), memory usage (alert at 85%), disk space (alert at 80%), network errors, container restarts.

### Level 2: Application Metrics

Request latency, error rates, throughput, queue depths. These tell you how your application is performing from the user's perspective.

**The RED method**: Rate (requests per second), Errors (failed requests per second), Duration (latency distribution — p50, p95, p99).

**Key metrics**: p99 latency (alert if >500ms), error rate (alert if >1%), request throughput (alert on sudden drops), connection pool utilization.

### Level 3: Data Pipeline Metrics

Pipeline completion times, data freshness, row counts, schema changes. These are specific to data systems and often overlooked.

**Key metrics**: Pipeline duration (alert if >2x normal), data freshness (alert if table hasn't been updated in expected window), row count (alert on >20% deviation from normal), failed quality checks.

### Level 4: Business Metrics (Top)

Revenue, conversion rates, user signups, churn. These are what actually matter to the business. Technical metrics are proxies; business metrics are the truth.

**Key metrics**: Vary by business, but examples include daily revenue (alert on >15% drop), conversion rate, active user count, order volume.

> **Key Takeaway:** Most teams over-invest in Level 1 (infrastructure) and under-invest in Levels 3-4 (pipeline and business). A data quality bug that silently corrupts revenue numbers is more damaging than a CPU spike that triggers auto-scaling.

---

## Data Quality Framework

Data quality has four levels, from basic to sophisticated:

### Level 1: Syntax — Are the values in the right format?

- Data types are correct (dates are dates, numbers are numbers)
- Required fields are not null
- Values match expected patterns (email format, phone format)

### Level 2: Semantic — Do the values make sense?

- Prices are positive
- Dates are in valid ranges (no orders from 1970 or 2099)
- Status values are from an expected set
- Foreign keys reference existing records

### Level 3: Temporal — Is the data fresh and consistent over time?

- Tables are updated within expected windows
- Row counts don't fluctuate wildly day-to-day
- No gaps in time-series data
- Late-arriving data is handled correctly

### Level 4: Contextual — Does the data match business expectations?

- Revenue totals are within expected ranges for the day/season
- Conversion rates haven't shifted suspiciously
- New data is consistent with historical patterns

Here's a practical data quality monitoring system that covers all four levels:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
import statistics

@dataclass
class QualityAlert:
    level: str        # syntax, semantic, temporal, contextual
    severity: str     # warning, critical
    table: str
    check: str
    message: str
    timestamp: datetime

class DataQualityMonitor:
    """Monitor data quality across all four levels.

    Run this after every pipeline completion. If any critical check
    fails, block downstream consumption and alert the team.
    """

    def __init__(self, db_connection):
        self.db = db_connection
        self.alerts: List[QualityAlert] = []

    def run_all_checks(self, table: str, date: str) -> List[QualityAlert]:
        self.alerts = []
        self.check_syntax(table, date)
        self.check_semantic(table, date)
        self.check_temporal(table, date)
        self.check_contextual(table, date)
        return self.alerts

    def check_syntax(self, table: str, date: str):
        """Level 1: Are values in the right format?"""
        # Check for null primary keys
        null_count = self.db.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE id IS NULL AND date = '{date}'"
        )
        if null_count > 0:
            self.alerts.append(QualityAlert(
                level="syntax", severity="critical", table=table,
                check="null_primary_key",
                message=f"{null_count} rows with null primary key",
                timestamp=datetime.utcnow(),
            ))

    def check_semantic(self, table: str, date: str):
        """Level 2: Do values make sense?"""
        # Check for negative revenue
        negative_count = self.db.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE amount < 0 AND date = '{date}'"
        )
        if negative_count > 0:
            self.alerts.append(QualityAlert(
                level="semantic", severity="warning", table=table,
                check="negative_amounts",
                message=f"{negative_count} rows with negative amounts",
                timestamp=datetime.utcnow(),
            ))

    def check_temporal(self, table: str, date: str):
        """Level 3: Is the data fresh and consistent over time?"""
        # Check row count vs historical average
        today_count = self.db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE date = '{date}'"
        )
        historical_counts = self.db.execute(
            f"SELECT COUNT(*) as cnt FROM {table} "
            f"WHERE date >= '{date}'::date - INTERVAL '30 days' "
            f"AND date < '{date}' GROUP BY date"
        )
        if historical_counts:
            avg_count = statistics.mean(historical_counts)
            deviation = abs(today_count - avg_count) / avg_count
            if deviation > 0.5:  # >50% deviation
                self.alerts.append(QualityAlert(
                    level="temporal", severity="critical", table=table,
                    check="row_count_anomaly",
                    message=(
                        f"Row count {today_count} deviates {deviation:.0%} "
                        f"from 30-day average {avg_count:.0f}"
                    ),
                    timestamp=datetime.utcnow(),
                ))

    def check_contextual(self, table: str, date: str):
        """Level 4: Does the data match business expectations?"""
        # Example: daily revenue should be within expected range
        daily_revenue = self.db.execute(
            f"SELECT SUM(amount) FROM {table} WHERE date = '{date}'"
        )
        # Revenue below $1,000 or above $10,000,000 is suspicious
        if daily_revenue < 1000 or daily_revenue > 10_000_000:
            self.alerts.append(QualityAlert(
                level="contextual", severity="critical", table=table,
                check="revenue_out_of_range",
                message=f"Daily revenue ${daily_revenue:,.2f} is outside expected range",
                timestamp=datetime.utcnow(),
            ))
```

---

## The Three Pillars of Observability

### Metrics

Numeric measurements collected at regular intervals. "Request count per second," "CPU usage percentage," "Queue depth."

**Prometheus** is the standard for collecting and querying metrics. It uses a pull model: Prometheus scrapes metrics endpoints that your services expose. **Grafana** visualizes Prometheus data as dashboards.

### Logs

Detailed records of individual events. "User X requested /api/orders at 14:30:05, response 200, 45ms."

**Structured logging** is essential — use JSON instead of plain text so logs can be searched and aggregated:

```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    """Structured JSON logger for data pipelines.

    Structured logs can be ingested by Elasticsearch, Loki, or
    CloudWatch Logs and queried by any field — much more useful
    than grep-ing through plain text.
    """

    def __init__(self, service_name: str):
        self.service = service_name
        self.logger = logging.getLogger(service_name)

    def log(self, level: str, message: str, **context):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service,
            "level": level,
            "message": message,
            **context,  # Add any context as top-level fields
        }
        self.logger.log(
            getattr(logging, level.upper()),
            json.dumps(entry)
        )

# Usage in a pipeline
log = StructuredLogger("etl-pipeline")

log.log("info", "Pipeline started",
        pipeline="daily_orders", run_date="2026-04-01")

log.log("info", "Extraction complete",
        pipeline="daily_orders", rows_extracted=50432,
        duration_seconds=12.5, source="postgres")

log.log("error", "Quality check failed",
        pipeline="daily_orders", check="null_primary_keys",
        failed_rows=3, severity="critical")
```

### Traces

Distributed traces follow a single request across multiple services. When a user's API call touches the API gateway, the order service, the inventory service, and the database, a trace connects all the spans (individual operations) into one timeline.

**OpenTelemetry** is the standard for instrumentation. Here's how to instrument a data pipeline:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Set up tracing
provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="otel-collector:4317"))
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("etl-pipeline")

def run_daily_pipeline(date: str):
    """A traced pipeline — each stage is a span in the trace.

    In Jaeger or Tempo, you'll see a timeline showing exactly
    how long each stage took and where bottlenecks are.
    """
    with tracer.start_as_current_span("daily_pipeline") as pipeline_span:
        pipeline_span.set_attribute("pipeline.date", date)

        with tracer.start_as_current_span("extract") as extract_span:
            rows = extract_data(date)
            extract_span.set_attribute("extract.row_count", rows)

        with tracer.start_as_current_span("transform"):
            transformed = transform_data(rows)

        with tracer.start_as_current_span("quality_check"):
            passed = run_quality_checks(transformed)
            if not passed:
                pipeline_span.set_status(
                    trace.Status(trace.StatusCode.ERROR, "Quality check failed")
                )
                raise Exception("Quality check failed")

        with tracer.start_as_current_span("load"):
            load_to_warehouse(transformed)
```

> **Key Takeaway:** Use all three pillars together. Metrics tell you *something* is wrong (alert). Logs tell you *what* happened (investigate). Traces tell you *where* in the system it happened (pinpoint).

---

## Data Lineage Tracking

Data lineage answers two critical questions:

**Impact analysis** (downstream): "If I change this table's schema, what breaks?" If `raw.orders` feeds `staging.clean_orders`, which feeds `analytics.fact_orders`, which feeds the Revenue Dashboard — you need to know the full chain before modifying anything.

**Root cause analysis** (upstream): "This dashboard is showing wrong numbers. Where did the bad data come from?" Trace backward from the dashboard through every transformation to find where the corruption was introduced.

**Tools**: Apache Atlas, OpenLineage, Marquez, and dbt (which generates lineage from model dependencies).

Lineage should be captured automatically by your orchestration and transformation tools — not manually maintained, because manual lineage documentation goes stale immediately.

---

## Anomaly Detection and Circuit Breakers

### Circuit Breakers for Data Pipelines

Just as electrical circuit breakers prevent fires by cutting power when current spikes, **data circuit breakers** stop bad data from propagating through your system.

The pattern: if a quality check detects an anomaly (row count dropped 80%, null rate spiked, unexpected schema change), the pipeline halts and serves the *last known good* data while alerting the team.

This is far better than the alternative: loading bad data into the warehouse, where it corrupts dashboards, feeds wrong data to ML models, and triggers incorrect business decisions. Stale-but-correct data is almost always better than fresh-but-wrong data.

---

## Cost Monitoring and Security Compliance

### Cost Attribution

Track costs by team, pipeline, and query so you know who's spending what:

```sql
-- Snowflake: query cost by user/team over the last 30 days
SELECT
    user_name,
    warehouse_name,
    COUNT(*) AS query_count,
    SUM(credits_used_cloud_services) AS total_credits,
    ROUND(SUM(credits_used_cloud_services) * 3.0, 2) AS estimated_cost_usd
FROM snowflake.account_usage.query_history
WHERE start_time > DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY user_name, warehouse_name
ORDER BY total_credits DESC;
```

### Security and Compliance Monitoring

For regulated industries, monitoring must cover:

- **PII detection**: Automatically scan new data for personally identifiable information (names, emails, SSNs, credit card numbers). Flag unencrypted PII in non-approved tables.
- **GDPR compliance**: Track data lineage to know where personal data flows. Ensure deletion requests are fully honored across all systems.
- **SOX compliance**: Maintain audit trails for financial data. All changes to revenue-affecting data must be logged with who, what, and when.
- **Access auditing**: Log every query against sensitive tables. Alert on unusual access patterns (new user querying the full customers table at 3 AM).

> **Key Takeaway:** Observability isn't just about performance and reliability — it's about trust. Data teams that invest in quality monitoring, lineage, and compliance build trust with stakeholders. Teams that don't eventually lose it, usually after a painful incident.

---

## What's Next

Observability tells you how your system is behaving. Module 11 tackles the financial side: cost optimization and capacity planning. You'll learn how to keep cloud data platform costs under control while ensuring the system can handle growth.
