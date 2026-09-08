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
    cast(null as STRING) as timing_basis,
    cast(null as INTEGER) as place,
    cast(null as INTEGER) as duration_s,
    "not_applicable" as weather_match_status,
    cast(null as STRING) as weather_match_reason,
    cast(null as TIMESTAMP) as weather_observed_at_utc,
    cast(null as FLOAT64) as weather_temp_c,
    cast(null as FLOAT64) as weather_wind_mps,
    cast(null as FLOAT64) as weather_precipitation_mm,
    cast(null as FLOAT64) as weather_humidity_pct
), candidates as (
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:4" as source_row_id,
    4 as source_row_number,
    "skipped" as validation_status,
    "missing finish time" as validation_reason
union all
select
    "eventrac:900001:70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182:5" as source_row_id,
    5 as source_row_number,
    "invalid" as validation_status,
    "invalid finish time 'bad-time': unsupported duration format: 'bad-time'" as validation_reason
)
select context.*, candidates.* from context cross join candidates
