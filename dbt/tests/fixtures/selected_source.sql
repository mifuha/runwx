-- Synthetic correction B after selection, not another historical race edition.
with candidates as (
    select * from unnest([
        struct(1 as row_number, 'accepted' as status, cast(null as string) as reason,
            1 as place, 3600 as duration_s),
        struct(2, 'accepted', null, 2, 6600),
        struct(3, 'accepted', null, 3, 14400),
        struct(4, 'skipped', 'missing finish time', null, null),
        struct(5, 'invalid', 'invalid finish time', null, null)
    ])
)
select
    'revision-b' as revision_id,
    repeat('c', 64) as code_sha256,
    '{"top_n":20}' as revision_settings_json,
    1 as export_schema_version,
    concat('eventrac:900001:a7da242b64691c302c03810c4f1c7ac8018ed9e325bfa5950e49117b5d2936eb:', cast(row_number as string)) as source_row_id,
    row_number as source_row_number,
    'eventrac:900001' as event_id,
    'eventrac' as source,
    '900001' as source_event_id,
    'runwx-synthetic-half' as course_id,
    timestamp '2022-03-06 10:00:00+00' as started_at_utc,
    21097 as distance_m,
    'a7da242b64691c302c03810c4f1c7ac8018ed9e325bfa5950e49117b5d2936eb' as race_sha256,
    '835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f' as weather_sha256,
    'synthetic' as race_kind,
    'synthetic' as weather_kind,
    struct('runwx-synthetic-half' as course_id_input, 'Europe/London' as timezone_name,
        1800.0 as max_gap_seconds, 'nearest observation to run midpoint' as alignment,
        'earlier observation' as tie_break, 'whole seconds; fractions truncated' as duration_precision,
        cast(null as string) as timing_basis) as settings,
    status as validation_status,
    reason as validation_reason,
    place,
    duration_s,
    case when row_number <= 2 then 'matched' when row_number = 3 then 'unmatched'
        else 'not_applicable' end as weather_match_status,
    if(row_number = 3, 'No weather within 0:30:00', null) as weather_match_reason,
    if(row_number <= 2,
        struct(if(row_number = 1, timestamp '2022-03-06 10:00:00+00', timestamp '2022-03-06 11:00:00+00') as observed_at_utc,
            if(row_number = 1, 8.5, 9.0) as temp_c, if(row_number = 1, 4.0, 4.2) as wind_mps,
            0.0 as precipitation_mm, if(row_number = 1, 72.0, 68.0) as humidity_pct),
        null) as weather
from candidates
