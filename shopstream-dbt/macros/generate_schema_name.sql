-- Override dbt's default schema naming behavior.
--
-- Default behavior:    <target_schema>_<custom_schema>  (e.g. dbt_alice_staging)
-- This override:       prod   → <custom_schema>         (e.g. staging)
--                      dev    → <target_schema>          (e.g. dbt_alice)
--
-- Why: In production we want clean schema names (staging, core, finance).
--      In dev each engineer gets a single personal schema so objects don't clash.

{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}

    {%- if target.name == 'prod' -%}

        {%- if custom_schema_name is none -%}
            {{ default_schema }}
        {%- else -%}
            {{ custom_schema_name | trim }}
        {%- endif -%}

    {%- else -%}

        {# In non-prod environments, all models land in the developer's personal schema #}
        {{ default_schema }}

    {%- endif -%}

{%- endmacro %}
