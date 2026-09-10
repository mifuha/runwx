select
    *,
    duration_s / (distance_m / 1000.0) as pace_s_per_km
from {{ ref('stg_race_results') }}
where validation_status = 'accepted'
