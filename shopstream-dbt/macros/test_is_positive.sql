-- Custom generic test: assert that a column's values are all positive (> 0).
--
-- Usage in schema.yml:
--   columns:
--     - name: quantity
--       tests:
--         - is_positive
--
-- Every generic test macro receives at minimum:
--   model       — the node being tested (use {{ model }} in FROM)
--   column_name — the column under test

{% test is_positive(model, column_name) %}

select *
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} <= 0

{% endtest %}
