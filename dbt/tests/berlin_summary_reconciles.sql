{{ config(enabled=var('berlin_research_tables', []) | length > 0, tags=['berlin']) }}
{% if var('berlin_research_tables', []) | length > 0 %}
with expected as (
    {% for table in berlin_research_tables() %}
        {% if not loop.first %} union all {% endif %}
        select '{{ table }}' as snapshot_table
    {% endfor %}
), actual as (
    select * from {{ ref('mart_berlin_edition_summary') }}
)
select coalesce(e.snapshot_table, a.snapshot_table) as failing_table
from expected as e
full outer join actual as a using (snapshot_table)
where e.snapshot_table is null or a.snapshot_table is null
    or a.captured_count != a.declared_captured_count
    or a.accepted_count + a.held_count != a.captured_count
    or a.finisher_count != a.accepted_count
    or a.distinct_source_rows != a.captured_count
    or a.distinct_source_locators != a.captured_count
    or a.unknown_timing_count != a.captured_count
    or a.distinct_contexts != 1
    or a.top_n_effective != least(a.top_n_requested, a.accepted_count)
    or (a.finisher_count > 0 and (
        a.best_duration_s is null or a.best_duration_s <= 0
        or a.mean_duration_s is null or a.median_duration_s is null
        or a.duration_p25_s is null or a.duration_p75_s is null
        or a.top_n_median_duration_s is null or a.top_n_mean_duration_s is null
        or a.best_duration_s > a.duration_p25_s
        or a.duration_p25_s > a.median_duration_s
        or a.median_duration_s > a.duration_p75_s
    ))
    or (a.finisher_count = 0 and (
        a.best_duration_s is not null or a.mean_duration_s is not null
        or a.median_duration_s is not null or a.top_n_median_duration_s is not null
        or a.top_n_mean_duration_s is not null
    ))
{% endif %}
