with source_rows as (
    select * from {{ source('runwx', 'race_results') }}
), staged_rows as (
    select * from {{ ref('stg_race_results') }}
), differences as (
    select coalesce(raw.source_row_id, staged.source_row_id) as source_row_id
    from source_rows as raw
    full outer join staged_rows as staged using (source_row_id)
    where raw.source_row_id is null
        or staged.source_row_id is null
        or raw.source_row_number is distinct from staged.source_row_number
        or raw.validation_status is distinct from staged.validation_status
        or raw.validation_reason is distinct from staged.validation_reason
        or raw.duration_s is distinct from staged.duration_s
        or raw.weather_match_status is distinct from staged.weather_match_status
        or raw.race_sha256 is distinct from staged.race_sha256
        or raw.weather_sha256 is distinct from staged.weather_sha256
)
select source_row_id from differences
union all
select '__row_count__' as source_row_id
from (select count(*) as row_count from source_rows) as expected_count
cross join (select count(*) as row_count from staged_rows) as actual_count
where expected_count.row_count != actual_count.row_count
