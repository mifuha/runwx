{% macro context_columns() %}
    export_schema_version, event_id, source, source_event_id, course_id,
    started_at_utc, distance_m, race_sha256, weather_sha256, race_kind,
    weather_kind, course_id_input, timezone_name, max_gap_seconds, alignment,
    tie_break, duration_precision, timing_basis
    {% if var('enable_revision_preview', false) %}
        , revision_id, code_sha256, top_n_requested
    {% endif %}
{% endmacro %}

{% macro analysis_keys() %}
    event_id{% if var('enable_revision_preview', false) %}, revision_id{% endif %}
{% endmacro %}
