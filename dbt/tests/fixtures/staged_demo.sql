-- Synthetic test input derived from the saved demo export.
with context as (
select
    1 as export_schema_version,
    "eventrac:900001" as event_id,
    "eventrac" as source,
    "900001" as source_event_id,
    "runwx-synthetic-half" as course_id,
    timestamp "2022-03-06T10:00:00+00:00" as started_at_utc,
    21097 as distance_m,
    "70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182" as race_sha256,
    "835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f" as weather_sha256,
    "synthetic" as race_kind,
    "synthetic" as weather_kind,
    "runwx-synthetic-half" as course_id_input,
    "Europe/London" as timezone_name,
    1800.0 as max_gap_seconds,
    "nearest observation to run midpoint" as alignment,
    "earlier observation" as tie_break,
    "whole seconds; fractions truncated" as duration_precision,
    cast(null as STRING) as timing_basis
), candidates as (
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:1" as source_row_id,
    1 as source_row_number,
    "accepted" as validation_status,
    cast(null as STRING) as validation_reason,
    1 as place,
    3600 as duration_s,
    "matched" as weather_match_status,
    cast(null as STRING) as weather_match_reason,
    timestamp "2022-03-06T10:00:00+00:00" as weather_observed_at_utc,
    8.5 as weather_temp_c,
    4.0 as weather_wind_mps,
    0.0 as weather_precipitation_mm,
    72.0 as weather_humidity_pct
union all
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:2" as source_row_id,
    2 as source_row_number,
    "accepted" as validation_status,
    cast(null as STRING) as validation_reason,
    2 as place,
    7200 as duration_s,
    "matched" as weather_match_status,
    cast(null as STRING) as weather_match_reason,
    timestamp "2022-03-06T11:00:00+00:00" as weather_observed_at_utc,
    9.0 as weather_temp_c,
    4.2 as weather_wind_mps,
    0.0 as weather_precipitation_mm,
    68.0 as weather_humidity_pct
union all
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:3" as source_row_id,
    3 as source_row_number,
    "accepted" as validation_status,
    cast(null as STRING) as validation_reason,
    3 as place,
    14400 as duration_s,
    "unmatched" as weather_match_status,
    "No weather within 0:30:00" as weather_match_reason,
    cast(null as TIMESTAMP) as weather_observed_at_utc,
    cast(null as FLOAT64) as weather_temp_c,
    cast(null as FLOAT64) as weather_wind_mps,
    cast(null as FLOAT64) as weather_precipitation_mm,
    cast(null as FLOAT64) as weather_humidity_pct
union all
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:4" as source_row_id,
    4 as source_row_number,
    "skipped" as validation_status,
    "missing finish time" as validation_reason,
    cast(null as INTEGER) as place,
    cast(null as INTEGER) as duration_s,
    "not_applicable" as weather_match_status,
    cast(null as STRING) as weather_match_reason,
    cast(null as TIMESTAMP) as weather_observed_at_utc,
    cast(null as FLOAT64) as weather_temp_c,
    cast(null as FLOAT64) as weather_wind_mps,
    cast(null as FLOAT64) as weather_precipitation_mm,
    cast(null as FLOAT64) as weather_humidity_pct
union all
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:5" as source_row_id,
    5 as source_row_number,
    "invalid" as validation_status,
    "invalid finish time 'bad-time': unsupported duration format: 'bad-time'" as validation_reason,
    cast(null as INTEGER) as place,
    cast(null as INTEGER) as duration_s,
    "not_applicable" as weather_match_status,
    cast(null as STRING) as weather_match_reason,
    cast(null as TIMESTAMP) as weather_observed_at_utc,
    cast(null as FLOAT64) as weather_temp_c,
    cast(null as FLOAT64) as weather_wind_mps,
    cast(null as FLOAT64) as weather_precipitation_mm,
    cast(null as FLOAT64) as weather_humidity_pct
)
select context.*, candidates.* from context cross join candidates
