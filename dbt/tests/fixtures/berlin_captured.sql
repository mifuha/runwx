-- Two equal anonymous results stay distinct; the held row has no usable duration.
with rows as (
    select 1 as source_row_number, 10800 as duration_s, 'accepted' as validation_status, 'normal' as edition
    union all select 2, 14400, 'accepted', 'normal'
    union all select 3, 14400, 'accepted', 'normal'
    union all select 4, 21600, 'accepted', 'normal'
    union all select 5, null, 'held', 'normal'
    union all select 6, null, 'held', 'empty'
    union all select 7, 10800, 'accepted', 'mixed'
    union all select 8, 14400, 'accepted', 'mixed'
)
select *,
    edition as snapshot_table,
    cast(source_row_number as string) as source_row_id,
    date '2012-09-30' as race_date,
    'berlin_research_v1' as export_schema,
    2 as dataset_version,
    'published_research_capture' as population_basis,
    'post_2003_course_era_not_identical_routes' as course_basis,
    42195 as distance_m,
    repeat('a', 64) as race_sha256,
    repeat('b', 64) as preparation_report_sha256,
    repeat('c', 64) as weather_sha256,
    repeat('d', 64) as weather_csv_sha256,
    case edition when 'normal' then 5 when 'empty' then 1 else 2 end as captured_count,
    cast(null as int64) as published_count,
    cast(null as string) as timing_basis,
    struct(
        'fixed_edition_window' as basis,
        'Europe/Berlin' as timezone,
        '09:00' as start_local, '15:00' as end_local,
        timestamp '2012-09-30 07:00:00+00' as start_utc,
        timestamp '2012-09-30 13:00:00+00' as end_utc,
        7 as observation_count,
        if(source_row_number = 8, 99.0, 18.0) as median_temp_c,
        3.0 as median_wind_mps, 60.0 as median_humidity_pct, 0.5 as precipitation_mm
    ) as weather_context
from rows
