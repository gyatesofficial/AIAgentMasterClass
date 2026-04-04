-- customer_snapshot.sql
-- Tracks changes to customer records over time using SCD Type 2.
-- When a customer's email, country, or is_active status changes, dbt snapshot
-- closes the old record (sets dbt_valid_to) and inserts a new one.
--
-- This enables questions like:
--   "What country was this customer in when they placed their first order?"
--   "How many customers were deactivated in Q3?"

{% snapshot customer_snapshot %}

{{
    config(
      target_schema = 'snapshots',
      unique_key    = 'id',
      strategy      = 'timestamp',
      updated_at    = 'updated_at',
    )
}}

-- Snapshot the raw source directly, not the staging model.
-- Snapshots should capture the raw state; transformations happen downstream.
select * from {{ source('shopstream_raw', 'customers') }}

{% endsnapshot %}
