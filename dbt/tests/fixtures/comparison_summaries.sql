-- Synthetic edition aggregates: four finishers each, plus an empty/small field.
with editions as (
    select 'baseline' as snapshot_dataset, 'course-a' as course_id, 'chip' as timing_basis,
        4 as finishers, 4 as matched, 3300.0 as median_s, 2700.0 as top_s, 2 as effective_n
    union all select 'later', 'course-a', 'chip', 4, 2, 6600.0, 5400.0, 2
    union all select 'different_course', 'course-b', 'chip', 4, 0, 3900.0, 3300.0, 2
    union all select 'unknown_timing', 'course-a', cast(null as string), 4, 0, 3900.0, 3300.0, 2
    union all select 'empty', 'course-a', 'chip', 0, 0, cast(null as float64), cast(null as float64), 0
    union all select 'small', 'course-a', 'chip', 1, 0, 6600.0, 6600.0, 1
)
select
    snapshot_dataset, 1 as export_schema_version, snapshot_dataset as event_id,
    course_id, 10000 as distance_m, timing_basis,
    concat('race-', snapshot_dataset) as race_sha256,
    concat('weather-', snapshot_dataset) as weather_sha256,
    'synthetic' as race_kind, 'synthetic' as weather_kind,
    'whole seconds' as duration_precision, 'Europe/London' as timezone_name,
    1800.0 as max_gap_seconds, 'midpoint' as alignment, 'earlier' as tie_break,
    finishers as finisher_count, finishers as candidate_count, finishers as accepted_count,
    0 as skipped_count, 0 as invalid_count, median_s as median_duration_s,
    median_s as mean_duration_s, top_s as top_n_median_duration_s,
    median_s / 10.0 as median_pace_s_per_km, top_s / 10.0 as top_n_median_pace_s_per_km,
    2 as top_n_requested, effective_n as top_n_effective,
    matched as weather_matched_count, finishers - matched as weather_unmatched_count,
    safe_divide(matched, finishers) as weather_coverage_fraction
from editions
