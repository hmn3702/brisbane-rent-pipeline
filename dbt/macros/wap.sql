{#
  Write-audit-publish for the dbt layers.

    dbt run-operation wap_prepare                       # drop leftovers from a failed run
    dbt build --vars '{wap_suffix: __audit}'            # write + audit into *__audit schemas
    dbt run-operation wap_publish                       # only if the build passed

  wap_publish swaps every layer in ONE statement (a DO block is atomic): readers see either the
  whole old set of tables or the whole new set, never a mix. Views keep working after a schema
  rename because Postgres stores their dependencies by object id, not by name.
#}

{% macro wap_layers() %}
    {{ return(var('wap_schemas', ['ref', 'staging', 'intermediate', 'marts'])) }}
{% endmacro %}


{% macro wap_prepare(suffix='__audit') %}
    {% set sql %}
        {% for s in wap_layers() %}
        drop schema if exists {{ adapter.quote(s ~ suffix) }} cascade;
        {% endfor %}
    {% endset %}
    {% do run_query(sql) %}
    {{ log("wap_prepare: dropped any " ~ suffix ~ " schemas", info=true) }}
{% endmacro %}


{% macro wap_publish(suffix='__audit') %}
    {% set sql %}
    do $wap$
    declare
        layers text[] := array[{% for s in wap_layers() %}'{{ s }}'{% if not loop.last %}, {% endif %}{% endfor %}];
        s text;
    begin
        -- refuse to publish a partial build
        foreach s in array layers loop
            if not exists (select 1 from pg_namespace where nspname = s || '{{ suffix }}') then
                raise exception 'wap_publish: schema %{{ suffix }} is missing; nothing was published', s;
            end if;
        end loop;

        foreach s in array layers loop
            execute format('drop schema if exists %I cascade', s || '__old');
            if exists (select 1 from pg_namespace where nspname = s) then
                execute format('alter schema %I rename to %I', s, s || '__old');
            end if;
            execute format('alter schema %I rename to %I', s || '{{ suffix }}', s);
        end loop;

        foreach s in array layers loop
            execute format('drop schema if exists %I cascade', s || '__old');
        end loop;
    end
    $wap$;
    {% endset %}
    {% do run_query(sql) %}
    {{ log("wap_publish: swapped " ~ wap_layers() | join(', ') ~ " in one transaction", info=true) }}
{% endmacro %}
