{% set baseline_event_id = var('gnr_baseline_event_id', '') %}
{% if var('gnr_sample_tables', []) | length > 0 and not modules.re.fullmatch('greatrun:[0-9]+', baseline_event_id) %}
    {{ exceptions.raise_compiler_error('gnr_baseline_event_id must be one exact Great Run event ID') }}
{% endif %}

with editions as (
    select * from {{ ref('mart_gnr_edition_summary') }}
), baseline as (
    select * from editions
    where event_id = '{{ baseline_event_id }}'
    qualify count(*) over () = 1
), comparisons as (
    select
        e.*,
        b.event_id as baseline_event_id,
        b.median_pace_s_per_km as baseline_median_pace_s_per_km,
        case
            when e.course_id is distinct from b.course_id
                or e.distance_m is distinct from b.distance_m
                or e.distance_basis is distinct from b.distance_basis
                or e.race_kind is distinct from b.race_kind
                or e.weather_kind is distinct from b.weather_kind
                or e.export_schema is distinct from b.export_schema
                or e.sample_label is distinct from b.sample_label
                or e.sample_note is distinct from b.sample_note
                or e.sample_selection is distinct from b.sample_selection
                or e.declared_sample_size is distinct from b.declared_sample_size
                or e.source_count is distinct from b.source_count
                or e.timing_note is distinct from b.timing_note
                or e.weather_context_basis is distinct from b.weather_context_basis
                or e.weather_context_note is distinct from b.weather_context_note
                or e.weather_start_local is distinct from b.weather_start_local
                or e.weather_end_local is distinct from b.weather_end_local
                then 'different_course_or_scope'
            else 'descriptive_sample'
        end as comparison_status
    from editions as e
    cross join baseline as b
)
select
    *,
    if(comparison_status = 'descriptive_sample',
        median_pace_s_per_km - baseline_median_pace_s_per_km, null)
        as median_pace_difference_s_per_km,
    if(comparison_status = 'descriptive_sample',
        100.0 * safe_divide(
            median_pace_s_per_km - baseline_median_pace_s_per_km,
            baseline_median_pace_s_per_km), null)
        as median_pace_change_pct
from comparisons
