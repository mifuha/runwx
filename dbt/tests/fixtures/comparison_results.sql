-- Unmatched rows deliberately contain weather values: they must not enter weather medians.
with finishers as (
    select 'baseline' as snapshot_dataset, 240.0 as pace_s_per_km, 'matched' as weather_match_status,
        8.0 as weather_temp_c, 1.0 as weather_wind_mps
    union all select 'baseline', 300.0, 'matched', 10.0, 3.0
    union all select 'baseline', 360.0, 'matched', 12.0, 5.0
    union all select 'baseline', 420.0, 'matched', 14.0, 7.0
    union all select 'later', 480.0, 'matched', 10.0, 2.0
    union all select 'later', 600.0, 'matched', 20.0, 4.0
    union all select 'later', 720.0, 'unmatched', 99.0, 99.0
    union all select 'later', 840.0, 'unmatched', 99.0, 99.0
    union all select 'different_course', 300.0, 'unmatched', 99.0, 99.0
    union all select 'different_course', 360.0, 'unmatched', 99.0, 99.0
    union all select 'different_course', 420.0, 'unmatched', 99.0, 99.0
    union all select 'different_course', 480.0, 'unmatched', 99.0, 99.0
    union all select 'unknown_timing', 300.0, 'unmatched', 99.0, 99.0
    union all select 'unknown_timing', 360.0, 'unmatched', 99.0, 99.0
    union all select 'unknown_timing', 420.0, 'unmatched', 99.0, 99.0
    union all select 'unknown_timing', 480.0, 'unmatched', 99.0, 99.0
    union all select 'small', 660.0, 'unmatched', 99.0, 99.0
)
select *, 0.0 as weather_precipitation_mm, 70.0 as weather_humidity_pct from finishers
