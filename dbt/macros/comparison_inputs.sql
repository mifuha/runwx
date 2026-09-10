{% macro comparison_datasets() %}
    {% set datasets = var('comparison_datasets', []) %}
    {% if datasets is string or datasets is mapping or datasets is not sequence %}
        {{ exceptions.raise_compiler_error('comparison_datasets must be a list of dataset IDs') }}
    {% endif %}
    {% for dataset in datasets %}
        {% if dataset is not string or not modules.re.fullmatch('[A-Za-z0-9_]+', dataset) %}
            {{ exceptions.raise_compiler_error('comparison_datasets contains an invalid dataset ID') }}
        {% endif %}
    {% endfor %}
    {% if datasets | unique | list | length != datasets | length %}
        {{ exceptions.raise_compiler_error('comparison_datasets must not repeat a snapshot dataset') }}
    {% endif %}
    {% if datasets and var('comparison_baseline', none) not in datasets %}
        {{ exceptions.raise_compiler_error('comparison_baseline must name one comparison dataset') }}
    {% endif %}
    {{ return(datasets) }}
{% endmacro %}

{% macro comparison_union(identifier) %}
    {% for dataset in comparison_datasets() %}
        {% if not loop.first %} union all {% endif %}
        select '{{ dataset }}' as snapshot_dataset, *
        from {{ api.Relation.create(database=target.project, schema=dataset, identifier=identifier) }}
    {% endfor %}
{% endmacro %}
