{% set datasets = comparison_datasets() %}
with summaries as (
    select * from {{ ref('int_comparison_summaries') }}
), baseline as (
    select * from summaries
    where snapshot_dataset = '{{ var("comparison_baseline", "") }}'
    -- A missing or duplicate baseline cannot multiply or invent comparison rows.
    qualify count(*) over () = 1
), distributions as (
    select
        snapshot_dataset,
        percentile_cont(pace_s_per_km, 0.25) over (partition by snapshot_dataset) as pace_p25_s_per_km,
        percentile_cont(pace_s_per_km, 0.75) over (partition by snapshot_dataset) as pace_p75_s_per_km,
        {% for field in ['temp_c', 'wind_mps', 'precipitation_mm', 'humidity_pct'] %}
        percentile_cont(if(weather_match_status = 'matched', weather_{{ field }}, null), 0.5)
            over (partition by snapshot_dataset) as median_{{ field }}{% if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref('int_comparison_results') }}
), weather_and_spread as (
    select snapshot_dataset,
        max(pace_p25_s_per_km) as pace_p25_s_per_km,
        max(pace_p75_s_per_km) as pace_p75_s_per_km,
        max(median_temp_c) as median_temp_c,
        max(median_wind_mps) as median_wind_mps,
        max(median_precipitation_mm) as median_precipitation_mm,
        max(median_humidity_pct) as median_humidity_pct
    from distributions
    group by snapshot_dataset
), comparisons as (
    select
        s.*,
        w.* except (snapshot_dataset),
        b.snapshot_dataset as baseline_dataset,
        b.event_id as baseline_event_id,
        b.race_sha256 as baseline_race_sha256,
        b.weather_sha256 as baseline_weather_sha256,
        b.median_duration_s as baseline_median_duration_s,
        b.median_pace_s_per_km as baseline_median_pace_s_per_km,
        b.top_n_median_pace_s_per_km as baseline_top_n_median_pace_s_per_km,
        b.top_n_requested as baseline_top_n_requested,
        b.top_n_effective as baseline_top_n_effective,
        safe_divide(s.mean_duration_s, s.distance_m / 1000.0) as mean_pace_s_per_km,
        -- Speed represented by median duration, not median of individual speeds.
        safe_divide(3600.0, s.median_pace_s_per_km) as speed_at_median_duration_kmh,
        case
            when s.course_id is null or s.distance_m <= 0
                or s.course_id is distinct from b.course_id
                or s.distance_m is distinct from b.distance_m then 'different_course_or_distance'
            when s.timing_basis is null or b.timing_basis is null then 'unknown_timing_basis'
            when s.timing_basis is distinct from b.timing_basis
                {% for field in ['export_schema_version', 'duration_precision', 'timezone_name',
                                 'max_gap_seconds', 'alignment', 'tie_break', 'race_kind',
                                 'weather_kind'] %}
                or s.{{ field }} is distinct from b.{{ field }}
                {% endfor %}
                then 'different_interpretation'
            when s.finisher_count = 0 or b.finisher_count = 0 then 'no_finishers'
            else 'comparable'
        end as comparison_status
    from summaries as s
    cross join baseline as b
    left join weather_and_spread as w on w.snapshot_dataset = s.snapshot_dataset
)
select
    *,
    if(comparison_status = 'comparable', median_duration_s - baseline_median_duration_s, null)
        as median_duration_difference_s,
    if(comparison_status = 'comparable', median_pace_s_per_km - baseline_median_pace_s_per_km, null)
        as median_pace_difference_s_per_km,
    if(comparison_status = 'comparable',
        100.0 * (safe_divide(median_pace_s_per_km, baseline_median_pace_s_per_km) - 1), null)
        as median_pace_change_pct,
    if(comparison_status = 'comparable',
        100.0 * (safe_divide(baseline_median_pace_s_per_km, median_pace_s_per_km) - 1), null)
        as speed_at_median_duration_change_pct,
    if(comparison_status = 'comparable' and top_n_requested = baseline_top_n_requested
        and top_n_effective = baseline_top_n_effective,
        top_n_median_pace_s_per_km - baseline_top_n_median_pace_s_per_km, null)
        as top_n_median_pace_difference_s_per_km,
    if(comparison_status = 'comparable' and top_n_requested = baseline_top_n_requested
        and top_n_effective = baseline_top_n_effective,
        100.0 * (safe_divide(top_n_median_pace_s_per_km, baseline_top_n_median_pace_s_per_km) - 1), null)
        as top_n_median_pace_change_pct
from comparisons
