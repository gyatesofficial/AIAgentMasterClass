# Module 11: Cost Optimization & Capacity Planning

## The Cost Problem

Here's a story that plays out at hundreds of companies: a startup launches their data platform on Snowflake. Month one costs $2,000. Easy to ignore. The team adds more data sources, more dashboards, more analysts. A year later, the bill is $50,000/month. Eighteen months in, it's $200,000/month — growing faster than revenue. The CEO asks: "Why are we spending more on data infrastructure than on marketing?"

Cloud data platforms make it dangerously easy to spend money. There's no upfront sticker shock — just a smooth ramp that accelerates until someone notices. And because data platform costs are distributed across many teams, queries, and pipelines, nobody feels individually responsible.

Cost optimization isn't about being cheap. It's an engineering discipline — like performance optimization or security. It requires measurement, analysis, and deliberate trade-offs.

> **Key Takeaway:** If you're not actively managing data platform costs, they will grow faster than your data. Treat cost as a first-class engineering concern, not an afterthought.

---

## Cloud Pricing Models

Understanding pricing is the foundation of cost optimization. Each warehouse has a fundamentally different model.

### Snowflake

**Compute**: Billed in "credits" per second of warehouse runtime. A warehouse size determines credits/hour:

| Size | Credits/Hour | Approximate $/Hour |
|------|-------------|---------------------|
| X-Small | 1 | $2-3 |
| Small | 2 | $4-6 |
| Medium | 4 | $8-12 |
| Large | 8 | $16-24 |
| X-Large | 16 | $32-48 |

Auto-suspend saves money when warehouses are idle. Auto-resume starts them on demand.

**Storage**: ~$23/TB/month for active storage, less for time travel and fail-safe.

**Key cost lever**: Warehouse size and runtime. A Large warehouse running 24/7 costs ~$12,000-17,000/month. The same warehouse auto-suspending after 1 minute of idle time might run only 8 hours/day: ~$4,000-6,000/month.

### BigQuery

**On-Demand**: $5 per TB scanned. Simple, predictable per-query, but expensive at scale. A single query scanning 10 TB costs $50.

**Flat-Rate (Editions)**: Purchase reserved "slots" (units of compute). Starts around $1,700/month for 100 slots. Better for predictable, heavy workloads. Queries don't incur per-TB costs.

**Storage**: $0.02/GB/month for active, $0.01/GB/month for long-term (>90 days, automatic).

**Key cost lever**: For on-demand, query efficiency (scan less data). For flat-rate, slot utilization (are you using what you're paying for?).

### Amazon Redshift

**Provisioned**: Pay per node per hour. RA3 nodes (storage-separated) start ~$3.26/node/hour. A 3-node cluster costs ~$7,000/month.

**Serverless**: Pay per RPU-hour (Redshift Processing Unit). $0.375/RPU-hour. Scales automatically.

**Reserved Instances**: 1-year or 3-year commitments for 30-75% discount on provisioned clusters.

---

## Compute Cost Optimization

### Auto-Scaling Strategies

Configure warehouses to scale based on demand rather than peak capacity:

```sql
-- Snowflake: Multi-cluster warehouse that scales with concurrency
CREATE WAREHOUSE analytics_wh
    WAREHOUSE_SIZE = 'MEDIUM'
    MIN_CLUSTER_COUNT = 1      -- Minimum 1 cluster
    MAX_CLUSTER_COUNT = 4      -- Scale up to 4 clusters
    SCALING_POLICY = 'STANDARD' -- Add clusters when queries queue
    AUTO_SUSPEND = 120          -- Suspend after 2 min idle
    AUTO_RESUME = TRUE;
```

### Spot and Preemptible Instances

For Spark, Flink, and other batch processing frameworks, use spot instances for worker nodes:

- **AWS Spot**: Up to 90% discount. Use for Spark executors, EMR task nodes.
- **GCP Preemptible**: 60-91% discount. Use for Dataproc workers.
- **Azure Spot**: Up to 90% discount. Use for HDInsight, Databricks.

**Best practice**: Use on-demand instances for the driver/coordinator node (must not be interrupted) and spot instances for worker nodes (can be replaced if interrupted).

### Workload Scheduling

Not all workloads need to run during business hours:

- **Night owl scheduling**: Run heavy batch jobs at night when competition for cloud resources is lower (often cheaper on shared infrastructure).
- **Weekend processing**: ML training, backfills, and reporting can run over the weekend.
- **Stagger pipelines**: Don't start all daily pipelines at the same time. Stagger them to smooth compute demand and avoid contention.

---

## Storage Cost Optimization

### Lifecycle Management

Data accessed daily costs 20x more per GB than data accessed yearly. Move data through storage tiers as it ages:

```python
# AWS S3 lifecycle policy — automatically tier data
lifecycle_rules = {
    "Rules": [
        {
            "ID": "data-tiering",
            "Status": "Enabled",
            "Filter": {"Prefix": "analytics/"},
            "Transitions": [
                # After 30 days: Standard → Infrequent Access (~50% savings)
                {"Days": 30, "StorageClass": "STANDARD_IA"},
                # After 180 days: IA → Glacier Instant Retrieval (~70% savings)
                {"Days": 180, "StorageClass": "GLACIER_INSTANT_RETRIEVAL"},
                # After 365 days: Glacier → Deep Archive (~95% savings)
                {"Days": 365, "StorageClass": "DEEP_ARCHIVE"},
            ],
            "Expiration": {"Days": 2555},  # Delete after 7 years
        }
    ]
}
```

### Format Optimization

The file format you choose has a massive impact on both storage cost and query cost:

| Format | 1 TB Raw CSV | Compressed Parquet | Savings |
|--------|-------------|-------------------|---------|
| Storage | $23/month | $4-6/month | 75-80% |
| BigQuery scan cost | $5/query | $0.50-1.50/query | 70-90% |

Converting from CSV/JSON to Parquet is often the single highest-ROI optimization for a data lake.

### Data Retention Policies

Not all data needs to live forever. Define retention policies by data category:

- **Raw event data**: 90 days in hot storage, 1 year in cold, then delete (unless regulatory requirements say otherwise)
- **Aggregated metrics**: Keep indefinitely (small footprint)
- **Development/staging data**: 7-30 days maximum
- **Backups**: Follow the 3-2-1 rule (3 copies, 2 media types, 1 offsite), retain per compliance requirements

---

## Query Cost Optimization

In pay-per-query systems like BigQuery on-demand, the most expensive part isn't storage — it's compute. A single bad query can cost more than a month of storage.

### Identify Expensive Queries

```sql
-- BigQuery: Find your most expensive queries in the last 30 days
SELECT
    user_email,
    query,
    total_bytes_processed / POW(10, 12) AS tb_scanned,
    total_bytes_processed / POW(10, 12) * 5 AS estimated_cost_usd,
    creation_time
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    AND job_type = 'QUERY'
    AND state = 'DONE'
ORDER BY total_bytes_processed DESC
LIMIT 20;
```

### Result Caching

Both Snowflake and BigQuery automatically cache query results. If the same query runs again and the underlying data hasn't changed, the cached result is returned instantly at zero cost. Design your dashboards to benefit from this — use consistent query patterns rather than dynamic SQL with changing parameters.

### Materialized Views

Pre-compute expensive aggregations so dashboards read from the materialized view (fast, cheap) instead of scanning raw data (slow, expensive):

```sql
-- Instead of this running every dashboard refresh (scans full table):
SELECT date, region, SUM(revenue) FROM orders GROUP BY 1, 2;

-- Create a materialized view (runs once, updated incrementally):
CREATE MATERIALIZED VIEW daily_revenue_by_region AS
SELECT
    DATE_TRUNC('day', order_date) AS date,
    region,
    SUM(revenue) AS total_revenue,
    COUNT(*) AS order_count
FROM orders
GROUP BY 1, 2;
```

### Workload Management

Implement priority-based query queues to prevent expensive ad-hoc queries from starving time-sensitive dashboard queries:

- **Critical** (dashboards, production APIs): Highest priority, smallest queue delay, dedicated compute
- **High** (scheduled reports, ETL): High priority, moderate limits
- **Medium** (analyst ad-hoc queries): Medium priority, cost limits per query
- **Low** (data science experiments, backfills): Lowest priority, strictest cost limits, can be cancelled

> **Key Takeaway:** The 80/20 rule applies: 20% of queries typically drive 80% of costs. Find and optimize those queries first — adding a partition filter, using a materialized view, or caching results can save thousands of dollars per month.

---

## Capacity Planning

Capacity planning is predicting future resource needs so you can scale proactively rather than reactively (scrambling during an outage) or wastefully (paying for resources you don't use).

### Growth Modeling

Model three scenarios for every major resource (storage, compute, cost):

**Conservative** (50% probability): Historical growth rate continues. No major new features or data sources.

**Baseline** (30% probability): Growth rate increases moderately. One or two new data sources. Moderate user growth.

**Aggressive** (15% probability): Rapid growth. New product launch. Major marketing push. 3-5x data volume increase.

**Explosive** (5% probability): Acquisition, viral moment, or regulatory change. 10x data volume. This scenario isn't likely but you need a plan for it.

For each scenario, project monthly storage, compute hours, and cost over the next 12-18 months. Compare against current capacity and budget.

### When to Optimize vs. When to Add Capacity

- **Average utilization below 40%**: You're over-provisioned. Rightsize down.
- **Average utilization 40-70%**: The sweet spot. Monitor trends.
- **Average utilization 70-85%**: Start planning expansion. You'll hit limits during peak periods.
- **Average utilization above 85%**: You're likely experiencing performance degradation during peaks. Scale up now.

The goal isn't 100% utilization — that leaves no headroom for traffic spikes. Target 60-70% average with the ability to handle 2-3x peak loads.

### The Capacity Planning Conversation

Capacity planning isn't a purely technical exercise. It requires input from:

- **Product managers**: What features are coming? Will they generate new data?
- **Sales teams**: What's the customer growth forecast?
- **Engineering teams**: Are there architecture changes that will affect resource usage?
- **Finance**: What's the budget? What's the cost of downtime vs. over-provisioning?

A single new feature (like adding real-time analytics or ML-powered recommendations) can change capacity needs more than six months of organic growth.

---

## Case Study: TechFlow SaaS Cost Optimization

TechFlow, a B2B SaaS company, saw their data platform costs grow from $20K/month to $200K/month in 18 months as they scaled from 1,000 to 50,000 customers. They used three platforms: Snowflake (primary warehouse), BigQuery (ML workloads), and Redshift (legacy reporting).

### The Analysis

They discovered:
- **40% of Snowflake costs** came from two dashboards that refreshed every 5 minutes, each running a full table scan. Changing the refresh to 15 minutes and adding materialized views cut those costs by 80%.
- **25% of costs** were from development and staging warehouses left running 24/7. Auto-suspend + scheduled scaling saved $50K/month.
- **15% of storage costs** were from raw data that was never queried after initial processing. Lifecycle policies moved it to cold storage.
- **Multi-cloud overhead**: Running three platforms had 30% overhead from data duplication and cross-cloud transfer. They consolidated ML workloads to Snowflake, eliminating BigQuery and the associated data movement.

### The Results

After a 90-day optimization sprint:
- Monthly cost: $200K → $130K (35% reduction)
- Query performance: 2x improvement (materialized views, better partitioning)
- Capacity headroom: Could handle 3x current load without proportional cost increase
- Ongoing governance: Automated cost alerts, per-team budgets, weekly cost review

> **Key Takeaway:** Cost optimization isn't a one-time project — it's an ongoing discipline. Set up automated monitoring, per-team accountability, and regular reviews. The biggest savings usually come from a few high-impact changes, not hundreds of small ones.

---

## What's Next

With the technical foundations, processing patterns, and operational practices covered, Module 12 brings it all together with deep-dive case studies of five real-world systems: Netflix, Uber, Spotify, Airbnb, and Twitter. You'll see how everything you've learned applies at massive scale.
