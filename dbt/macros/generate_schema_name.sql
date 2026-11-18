{#
  Clean schema names (staging, intermediate, marts) instead of dbt's default analytics_staging.
  With --vars '{wap_suffix: __audit}' every layer is built into <schema>__audit instead, so a
  build can be tested before anything readers use is touched (see macros/wap.sql).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set base = target.schema if custom_schema_name is none else custom_schema_name | trim -%}
    {{ base }}{{ var('wap_suffix', '') }}
{%- endmacro %}
