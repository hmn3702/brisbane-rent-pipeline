{# Last day of the calendar quarter containing a date, matching RTA quarter_end values. #}
{% macro quarter_end(date_expr) -%}
    (date_trunc('quarter', {{ date_expr }}) + interval '3 months - 1 day')::date
{%- endmacro %}
