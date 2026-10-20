{% macro berlin_research_tables() %}
    {% set tables = var('berlin_research_tables', []) %}
    {% if tables is string or tables is mapping or tables is not sequence %}
        {{ exceptions.raise_compiler_error('berlin_research_tables must be a list of exact snapshot tables') }}
    {% endif %}
    {% if tables | length > 16 or tables | unique | list | length != tables | length %}
        {{ exceptions.raise_compiler_error('berlin_research_tables must contain at most 16 distinct editions') }}
    {% endif %}
    {% set years = [] %}
    {% for table in tables %}
        {% if table is not string or not modules.re.fullmatch('[a-z][a-z0-9-]{4,61}[a-z0-9]\\.runwx_staging\\.berlin_(200[3-9]|201[0-8])_research_[0-9a-f]{12}', table) or table.split('.')[0] != target.project %}
            {{ exceptions.raise_compiler_error('berlin_research_tables contains an invalid or foreign table ID') }}
        {% endif %}
        {% set year = table.split('.')[-1].split('_')[1] %}
        {% if year in years %}
            {{ exceptions.raise_compiler_error('Choose only one Berlin snapshot per edition') }}
        {% endif %}
        {% do years.append(year) %}
    {% endfor %}
    {{ return(tables) }}
{% endmacro %}

{% macro berlin_research_union() %}
    {% for table in berlin_research_tables() %}
        {% if not loop.first %} union all {% endif %}
        select '{{ table }}' as snapshot_table, * from `{{ table }}`
    {% endfor %}
{% endmacro %}
