-- Weather coverage must never decide whether an accepted finisher survives.
-- Compare all original columns; pace is the only derived fact column.
with expected as (
    select * from {{ ref('stg_race_results') }}
    where validation_status = 'accepted'
), actual as (
    select * except (pace_s_per_km) from {{ ref('fct_race_results') }}
), differences as (
    select coalesce(expected.source_row_id, actual.source_row_id) as source_row_id
    from expected
    full outer join actual using (
        source_row_id{% if var('enable_revision_preview', false) %}, revision_id{% endif %}
    )
    where expected.source_row_id is null
        or actual.source_row_id is null
        or to_json_string(expected) is distinct from to_json_string(actual)
)
select source_row_id from differences
union all
select '__row_count__' as source_row_id
from (select count(*) as row_count from expected) as expected_count
cross join (select count(*) as row_count from actual) as actual_count
where expected_count.row_count != actual_count.row_count
