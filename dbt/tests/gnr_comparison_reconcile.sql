{{ config(enabled=var('gnr_sample_tables', []) | length > 0, tags=['gnr']) }}
{% if var('gnr_sample_tables', []) | length > 0 %}
with summaries as (
    select * from {{ ref('mart_gnr_edition_summary') }}
), comparisons as (
    select * from {{ ref('mart_gnr_sample_comparison') }}
), baseline as (
    select median_pace_s_per_km from summaries
    where event_id = '{{ var("gnr_baseline_event_id") }}'
)
select 'wrong_comparison_count' as failing_table
from (select count(*) as n from comparisons)
where n != {{ gnr_sample_tables() | length }}
union all
select 'missing_or_repeated_baseline' as failing_table
from (select count(*) as n from baseline)
where n != 1
union all
select coalesce(s.snapshot_table, c.snapshot_table) as failing_table
from summaries as s
full outer join comparisons as c using (snapshot_table)
cross join baseline as b
where s.snapshot_table is null or c.snapshot_table is null
    or c.comparison_status is distinct from 'descriptive_sample'
    or c.baseline_event_id is distinct from '{{ var("gnr_baseline_event_id") }}'
    or c.median_pace_s_per_km is distinct from s.median_pace_s_per_km
    or c.median_temp_c is distinct from s.median_temp_c
    or c.chip_count is distinct from s.chip_count
    or c.gun_count is distinct from s.gun_count
    or c.unknown_count is distinct from s.unknown_count
    or c.median_pace_change_pct is null
    or abs(c.median_pace_change_pct
        - 100.0 * safe_divide(
            s.median_pace_s_per_km - b.median_pace_s_per_km,
            b.median_pace_s_per_km)) > 1e-9
{% endif %}
