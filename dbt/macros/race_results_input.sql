{% macro race_results_input() %}
    {% if var('enable_revision_preview', false) %}
        {{ ref('selected_revision_results') }}
    {% else %}
        {{ source('runwx', 'synthetic_results') }}
    {% endif %}
{% endmacro %}
