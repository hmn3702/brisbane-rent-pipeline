{# Geocodable label for Power BI / Azure Maps, e.g. 'West End, QLD 4101, Australia'. #}
{% macro location_label(name_col, postcode_col) -%}
    {{ name_col }} || ', QLD' || coalesce(' ' || {{ postcode_col }}, '') || ', Australia'
{%- endmacro %}
