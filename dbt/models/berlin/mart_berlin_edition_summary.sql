{{ config(materialized='table') }}
{% set top_n = var('top_n', 20) %}
{% if top_n is not integer or top_n <= 0 %}
    {{ exceptions.raise_compiler_error('top_n must be a positive integer') }}
{% endif %}

with captured as (
    select * from {{ ref('stg_berlin_research_results') }}
), quality as (
    select
        snapshot_table,
        any_value(race_date) as race_date,
        any_value(export_schema) as export_schema,
        any_value(dataset_version) as dataset_version,
        any_value(population_basis) as population_basis,
        any_value(course_basis) as course_basis,
        any_value(distance_m) as distance_m,
        any_value(race_sha256) as race_sha256,
        any_value(preparation_report_sha256) as preparation_report_sha256,
        any_value(weather_sha256) as weather_sha256,
        any_value(weather_csv_sha256) as weather_csv_sha256,
        any_value(captured_count) as declared_captured_count,
        any_value(published_count) as published_count,
        any_value(weather_context) as weather_context,
        count(*) as captured_count,
        countif(validation_status = 'accepted') as accepted_count,
        countif(validation_status = 'held') as held_count,
        count(distinct source_row_id) as distinct_source_rows,
        count(distinct source_row_number) as distinct_source_locators,
        countif(timing_basis is null) as unknown_timing_count,
        count(distinct to_json_string(struct(
            race_date, export_schema, dataset_version, population_basis, course_basis,
            distance_m, race_sha256, preparation_report_sha256, weather_sha256,
            weather_csv_sha256, captured_count, published_count, weather_context
        ))) as distinct_contexts
    from captured
    group by snapshot_table
), ranked as (
    select *, row_number() over (
        partition by snapshot_table order by duration_s, source_row_number
    ) as duration_order
    from captured
    where validation_status = 'accepted'
), distribution as (
    select *,
        percentile_cont(cast(duration_s as float64), 0.25)
            over (partition by snapshot_table) as duration_p25_s,
        percentile_cont(cast(duration_s as float64), 0.5)
            over (partition by snapshot_table) as median_duration_s,
        percentile_cont(cast(duration_s as float64), 0.75)
            over (partition by snapshot_table) as duration_p75_s,
        percentile_cont(if(duration_order <= {{ top_n }}, cast(duration_s as float64), null), 0.5)
            over (partition by snapshot_table) as top_n_median_duration_s
    from ranked
), pace as (
    select snapshot_table,
        count(*) as finisher_count,
        min(duration_s) as best_duration_s,
        avg(duration_s) as mean_duration_s,
        max(duration_p25_s) as duration_p25_s,
        max(median_duration_s) as median_duration_s,
        max(duration_p75_s) as duration_p75_s,
        max(top_n_median_duration_s) as top_n_median_duration_s,
        avg(if(duration_order <= {{ top_n }}, duration_s, null)) as top_n_mean_duration_s
    from distribution
    group by snapshot_table
)
select q.*,
    coalesce(p.finisher_count, 0) as finisher_count,
    p.* except (snapshot_table, finisher_count),
    safe_divide(p.best_duration_s, q.distance_m / 1000.0) as best_pace_s_per_km,
    safe_divide(p.mean_duration_s, q.distance_m / 1000.0) as mean_pace_s_per_km,
    safe_divide(p.duration_p25_s, q.distance_m / 1000.0) as pace_p25_s_per_km,
    safe_divide(p.median_duration_s, q.distance_m / 1000.0) as median_pace_s_per_km,
    safe_divide(p.duration_p75_s, q.distance_m / 1000.0) as pace_p75_s_per_km,
    safe_divide(p.top_n_median_duration_s, q.distance_m / 1000.0) as top_n_median_pace_s_per_km,
    safe_divide(p.top_n_mean_duration_s, q.distance_m / 1000.0) as top_n_mean_pace_s_per_km,
    {{ top_n }} as top_n_requested,
    least({{ top_n }}, coalesce(p.finisher_count, 0)) as top_n_effective,
    q.captured_count - q.published_count as count_difference_from_published,
    q.weather_context.median_temp_c as median_temp_c,
    q.weather_context.median_wind_mps as median_wind_mps,
    q.weather_context.median_humidity_pct as median_humidity_pct,
    q.weather_context.precipitation_mm as precipitation_mm,
    'descriptive_research_capture' as comparison_status
from quality as q
left join pace as p using (snapshot_table)
-- Mixed settings must fail checks rather than produce blended statistics.
where q.distinct_contexts = 1
