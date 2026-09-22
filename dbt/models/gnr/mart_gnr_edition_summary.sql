{{ config(materialized='table') }}
{% set top_n = var('top_n', 20) %}
{% if top_n is not integer or top_n <= 0 %}
    {{ exceptions.raise_compiler_error('top_n must be a positive integer') }}
{% endif %}

with sample_rows as (
    select * from {{ ref('stg_gnr_sample_results') }}
), distribution as (
    select
        *,
        percentile_cont(cast(duration_s as float64), 0.25)
            over (partition by snapshot_table) as duration_p25_s,
        percentile_cont(cast(duration_s as float64), 0.5)
            over (partition by snapshot_table) as median_duration_s,
        percentile_cont(cast(duration_s as float64), 0.75)
            over (partition by snapshot_table) as duration_p75_s,
        percentile_cont(if(sample_rank <= {{ top_n }}, cast(duration_s as float64), null), 0.5)
            over (partition by snapshot_table) as top_n_median_duration_s
    from sample_rows
), edition as (
    select
        snapshot_table,
        any_value(export_schema) as export_schema,
        any_value(event_id) as event_id,
        any_value(race_date) as race_date,
        any_value(course_id) as course_id,
        any_value(distance_m) as distance_m,
        any_value(distance_basis) as distance_basis,
        any_value(race_kind) as race_kind,
        any_value(weather_kind) as weather_kind,
        any_value(race_sha256) as race_sha256,
        any_value(categories_sha256) as categories_sha256,
        any_value(weather_sha256) as weather_sha256,
        any_value(weather_request_sha256) as weather_request_sha256,
        any_value(sample.label) as sample_label,
        any_value(sample.note) as sample_note,
        any_value(sample.selection) as sample_selection,
        any_value(sample.size) as declared_sample_size,
        any_value(sample.source_count) as source_count,
        any_value(sample.excluded_count) as excluded_count,
        any_value(sample.timing_note) as timing_note,
        any_value(weather_context.basis) as weather_context_basis,
        any_value(weather_context.note) as weather_context_note,
        any_value(weather_context.start_local) as weather_start_local,
        any_value(weather_context.end_local) as weather_end_local,
        any_value(weather_context.median_temp_c) as median_temp_c,
        any_value(weather_context.median_wind_mps) as median_wind_mps,
        any_value(weather_context.median_humidity_pct) as median_humidity_pct,
        any_value(weather_context.precipitation_mm) as precipitation_mm,
        count(*) as sample_size,
        count(distinct source_row_id) as distinct_source_rows,
        count(distinct sample_rank) as distinct_sample_ranks,
        min(sample_rank) as min_sample_rank,
        max(sample_rank) as max_sample_rank,
        count(distinct to_json_string(struct(
            export_schema, event_id, race_date, course_id, distance_m,
            distance_basis, race_kind, weather_kind, race_sha256,
            categories_sha256, weather_sha256, weather_request_sha256,
            sample, weather_context
        ))) as distinct_contexts,
        countif(timing_basis = 'chip') as chip_count,
        countif(timing_basis = 'gun') as gun_count,
        countif(timing_basis = 'unknown') as unknown_count,
        min(duration_s) as best_duration_s,
        avg(duration_s) as mean_duration_s,
        max(duration_p25_s) as duration_p25_s,
        max(median_duration_s) as median_duration_s,
        max(duration_p75_s) as duration_p75_s,
        max(top_n_median_duration_s) as top_n_median_duration_s
    from distribution
    group by snapshot_table
)
select
    *,
    safe_divide(mean_duration_s, distance_m / 1000.0) as mean_pace_s_per_km,
    safe_divide(duration_p25_s, distance_m / 1000.0) as pace_p25_s_per_km,
    safe_divide(median_duration_s, distance_m / 1000.0) as median_pace_s_per_km,
    safe_divide(duration_p75_s, distance_m / 1000.0) as pace_p75_s_per_km,
    safe_divide(top_n_median_duration_s, distance_m / 1000.0) as top_n_median_pace_s_per_km,
    {{ top_n }} as top_n_requested,
    least({{ top_n }}, sample_size) as top_n_effective
from edition
