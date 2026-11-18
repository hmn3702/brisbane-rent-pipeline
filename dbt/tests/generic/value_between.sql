{#
  Fails on rows whose value is outside [min_value, max_value]. Nulls pass (use not_null for those).
  For catching impossible values, not unusual ones: thresholds sit well outside what real data has done.
#}
{% test value_between(model, column_name, min_value=none, max_value=none) %}
select {{ column_name }} as bad_value, *
from {{ model }}
where {{ column_name }} is not null
  and (
    {% if min_value is not none %} {{ column_name }} < {{ min_value }} {% else %} false {% endif %}
    or
    {% if max_value is not none %} {{ column_name }} > {{ max_value }} {% else %} false {% endif %}
  )
{% endtest %}
