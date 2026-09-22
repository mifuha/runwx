{% macro gnr_sample_tables() %}
    {% set tables = var('gnr_sample_tables', []) %}
    {% if tables is not string and tables is not mapping and tables is sequence and tables | length == 0 %}
        {{ return([]) }}
    {% endif %}
    {% if tables is string or tables is mapping or tables is not sequence or tables | length < 2 %}
        {{ exceptions.raise_compiler_error('gnr_sample_tables must list at least two exact GNR sample tables') }}
    {% endif %}
    {% if tables | unique | list | length != tables | length %}
        {{ exceptions.raise_compiler_error('gnr_sample_tables must not repeat a table') }}
    {% endif %}
    {% for table in tables %}
        {% if table is not string or not modules.re.fullmatch('[a-z][a-z0-9-]{4,61}[a-z0-9]\\.runwx_staging\\.gnr_[0-9]{4}_[0-9a-f]{12}', table) or table.split('.')[0] != target.project %}
            {{ exceptions.raise_compiler_error('gnr_sample_tables contains an invalid or foreign table ID') }}
        {% endif %}
    {% endfor %}
    {{ return(tables) }}
{% endmacro %}

{% macro gnr_sample_union() %}
    {% set tables = gnr_sample_tables() %}
    {% for table in tables %}
        {% if not loop.first %} union all {% endif %}
        select '{{ table }}' as snapshot_table, * from `{{ table }}`
    {% endfor %}
    {% if not tables %}
        select cast(null as string) as snapshot_table where false
    {% endif %}
{% endmacro %}
