select source_row_id
from {{ ref('stg_race_results') }}
where source_row_number is null or source_row_number <= 0
    or distance_m is null or distance_m <= 0
    or (
        validation_status = 'accepted'
        and (
            duration_s is null or duration_s <= 0
            or validation_reason is not null
            or weather_match_status not in ('matched', 'unmatched')
        )
    )
    or (
        validation_status in ('skipped', 'invalid')
        and (
            duration_s is not null or place is not null
            or validation_reason is null
            or weather_match_status is distinct from 'not_applicable'
        )
    )
    or (
        weather_match_status = 'matched'
        and (
            weather_match_reason is not null
            or weather_observed_at_utc is null
            or weather_temp_c is null or weather_wind_mps is null
            or weather_precipitation_mm is null or weather_humidity_pct is null
        )
    )
    or (
        weather_match_status in ('unmatched', 'not_applicable')
        and (
            weather_observed_at_utc is not null
            or weather_temp_c is not null or weather_wind_mps is not null
            or weather_precipitation_mm is not null or weather_humidity_pct is not null
        )
    )
    or (weather_match_status = 'unmatched' and weather_match_reason is null)
    or (weather_match_status = 'not_applicable' and weather_match_reason is not null)
