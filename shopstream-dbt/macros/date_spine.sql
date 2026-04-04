-- date_spine macro: generates a contiguous series of dates between two bounds.
-- Used in reporting models where we need a row for every date even if no orders occurred.
--
-- Usage:
--   {{ date_spine(
--       datepart   = 'day',
--       start_date = "cast('2022-01-01' as date)",
--       end_date   = "current_date"
--   ) }}

{% macro date_spine(datepart, start_date, end_date) %}

{{ dbt_utils.date_spine(
    datepart   = datepart,
    start_date = start_date,
    end_date   = end_date
) }}

{% endmacro %}
