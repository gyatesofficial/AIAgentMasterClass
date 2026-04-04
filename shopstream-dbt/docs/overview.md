{% docs shopstream_overview %}
# ShopStream Analytics

ShopStream is a direct-to-consumer e-commerce platform selling electronics,
fitness equipment, kitchen goods, footwear, and accessories globally.

## Data Architecture

Our dbt project follows a three-layer architecture:

| Layer | Schema | Materialization | Purpose |
|-------|--------|-----------------|---------|
| Staging | `staging` | View | 1-to-1 with source tables; rename, cast, no business logic |
| Intermediate | *(ephemeral)* | Ephemeral (CTE) | Complex joins and aggregations hidden from BI tools |
| Marts | `core`, `finance`, `marketing` | Table | Clean, documented, tested tables for BI consumption |

## Key Metrics Definitions

**Gross Revenue**: Sum of `revenue` on all completed orders.

**Net Revenue**: Gross Revenue minus refunds (returned orders).

**Lifetime Value (LTV)**: Total gross revenue from completed orders per customer.

**Customer Tier**:
- `vip` — LTV ≥ $200
- `regular` — LTV $100–$199
- `new` — LTV > $0 (has completed at least one order)
- `never_purchased` — registered but no completed orders

{% enddocs %}
